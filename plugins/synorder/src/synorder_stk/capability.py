import json
import time

from synorder_connectors.connections import connection
from synorder_interaction.contracts import (
    STRING,
    Action,
    Capability,
    Conflict,
    ExecutionMethod,
    InteractionError,
    canonical,
    digest,
    object_schema,
)

from . import method

CONFIG = object_schema(
    {
        "title": {**STRING, "maxLength": 200},
        "connector_id": {**STRING, "maxLength": 100},
        "amplitudes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": {"type": "number", "minimum": -1000000, "maximum": 1000000},
        },
        "backend": {"enum": ["local", "pbs", "slurm"]},
        "cpus": {"type": "integer", "minimum": 1, "maximum": 1024},
        "walltime_seconds": {"type": "integer", "minimum": 1, "maximum": 604800},
    }
)


def check_config(ctx, values):
    conn = connection(ctx.store, ctx.actor, values["connector_id"], kind="stk")
    if conn["space_id"] != ctx.space:
        raise PermissionError("计算连接不在当前空间")
    config = conn["config"]
    if (
        len(values["amplitudes"]) > config.get("max_jobs", 8)
        or values["cpus"] > config.get("max_cpus", 4)
        or values["walltime_seconds"] > config.get("max_walltime_seconds", 3600)
        or values["backend"] not in config.get("backends", ["local"])
    ):
        raise InteractionError("参数超过连接器允许的任务、CPU、时长或后端范围")
    return conn


def save(ctx, values):
    check_config(ctx, values)
    if ctx.target and ctx.target["type"] != "configuration":
        raise InteractionError("目标不是计算配置")
    import hashlib
    from importlib.resources import files

    source_hash = hashlib.sha256(
        files("synorder_stk").joinpath("examples", "simulate.py").read_bytes()
    ).hexdigest()
    return ctx.store.put_resource(
        ctx.db,
        ctx.actor,
        ctx.space,
        "configuration",
        values["title"],
        {
            **values,
            "engine": "stk.analytic-field.v1",
            "script_sha256": source_hash,
            "unit": "无量纲",
            "status": "draft",
        },
        rid=ctx.target["id"] if ctx.target else None,
        expected_version=ctx.target["version"] if ctx.target else None,
        conversation=ctx.conversation,
        pinned=True,
    )


def submit(ctx, values):
    config = ctx.target
    if config is None or config["type"] != "configuration":
        raise InteractionError("请选择配置及确切版本后再提交")
    conn = check_config(ctx, config["body"])
    import hashlib
    from importlib.resources import files

    if (
        hashlib.sha256(
            files("synorder_stk").joinpath("examples", "simulate.py").read_bytes()
        ).hexdigest()
        != config["body"]["script_sha256"]
    ):
        raise Conflict("示例方法已变化，请保存新版本后再提交")
    previous = ctx.db.execute(
        "SELECT id FROM executions WHERE json_extract(detail,'$.configuration_id')=? AND json_extract(detail,'$.configuration_version')=? LIMIT 1",
        (config["id"], config["version"]),
    ).fetchone()
    if previous:
        raise Conflict("此配置版本已提交；重跑请修订为新版本")
    active = ctx.db.execute(
        "SELECT count(*) FROM executions WHERE connector_id=? AND state NOT IN ('succeeded','failed','cancelled','timed_out')",
        (conn["id"],),
    ).fetchone()[0]
    if active + len(config["body"]["amplitudes"]) > conn["config"].get(
        "max_active_jobs", 8
    ):
        raise Conflict("此连接的未完成任务已达到上限；请等待或核对已有任务")
    results = []
    for index, amplitude in enumerate(config["body"]["amplitudes"]):
        request_key = "synorder-" + digest(
            {
                "workspace": ctx.store.workspace.id,
                "proposal": ctx.proposal_id,
                "index": index,
            }
        )
        title = f"{config['title']} · {amplitude}"
        detail = {
            "plugin": {"id": "synorder.stk", "version": "0.1.0"},
            "actor": ctx.actor,
            "configuration_id": config["id"],
            "configuration_version": config["version"],
            "engine": method.NAME,
            "script_sha256": config["body"]["script_sha256"],
            "amplitude": amplitude,
            "unit": "无量纲",
            "source_conversation": ctx.conversation["id"],
            "verification": "pending",
            "acceptance": "pending",
            "results": [],
        }
        ref = ctx.store.put_resource(
            ctx.db,
            ctx.actor,
            ctx.space,
            "execution",
            title,
            detail,
            conversation=ctx.conversation,
            permission="submit",
        )
        spec = {
            "backend": config["body"]["backend"],
            "name": request_key,
            "argv": ["{python}", "simulate.py"],
            "inputs": ["simulate.py", "input.json"],
            "outputs": [
                "field.dat",
                "field.vtk",
                "preview.png",
                "summary.json",
                "environment.json",
            ],
            "env": {},
            "resources": {
                "cpus": config["body"]["cpus"],
                "walltime_seconds": config["body"]["walltime_seconds"],
            },
        }
        ctx.db.execute(
            "INSERT INTO executions(id,connector_id,request_key,spec,state,started_at,deadline,detail) VALUES (?,?,?,?,?,?,?,?)",
            (
                ref["resource_id"],
                conn["id"],
                request_key,
                canonical(spec),
                "pending_start",
                time.time(),
                time.time() + config["body"]["walltime_seconds"],
                canonical(detail),
            ),
        )
        results.append(ref)
    return {"executions": results, "space_id": ctx.space}


def visualize(ctx, values):
    points, sources = [], []
    for rid in values["execution_ids"]:
        obj = ctx.store.resource(ctx.actor, rid, db=ctx.db)
        row = ctx.db.execute("SELECT * FROM executions WHERE id=?", (rid,)).fetchone()
        if obj["space_id"] != ctx.space or obj["type"] != "execution" or row is None:
            raise InteractionError("请选择当前空间中的计算")
        detail = json.loads(row["detail"])
        if row["state"] != "succeeded" or detail.get("verification") != "passed":
            raise InteractionError("计算尚无经过核对的数值结果")
        points.append(
            {
                "label": str(detail["amplitude"]),
                "value": detail["summary"]["mean"],
                "unit": "无量纲",
                "source": rid,
            }
        )
        sources.append({"resource_id": rid, "version": obj["version"]})
    return ctx.store.put_resource(
        ctx.db,
        ctx.actor,
        ctx.space,
        "visualization",
        values["title"],
        {
            "points": points,
            "sources": sources,
            "metric": "mean",
            "scientific_validation": "not_applicable",
            "expert": "pending",
        },
        conversation=ctx.conversation,
        pinned=True,
    )


def accept(ctx, values):
    obj = ctx.target
    if not obj or obj["type"] != "execution":
        raise InteractionError("请选择确切的执行结果版本")
    row = ctx.db.execute(
        "SELECT state,detail FROM executions WHERE id=?", (obj["id"],)
    ).fetchone()
    detail = json.loads(row["detail"])
    if (
        row["state"] != "succeeded"
        or detail.get("verification") != "passed"
        or detail.get("acceptance") == "accepted"
    ):
        raise InteractionError("只有经过核对且尚未验收的结果可以验收")
    detail.update(
        acceptance="accepted",
        accepted_by=ctx.actor,
        acceptance_evidence=values["reason"],
    )
    ctx.db.execute(
        "UPDATE executions SET detail=? WHERE id=?", (canonical(detail), obj["id"])
    )
    return ctx.store.put_resource(
        ctx.db,
        ctx.actor,
        ctx.space,
        "execution",
        obj["title"],
        {**obj["body"], **detail},
        rid=obj["id"],
        expected_version=obj["version"],
        conversation=ctx.conversation,
        pinned=True,
        permission="accept",
    )


def capability():
    from .science import queries
    from . import history
    return Capability(
        "synorder.stk",
        "科研计算",
        "0.1.0",
        ("configuration", "execution", "visualization", "research-object"),
        (
            history.action(),
            Action(
                "stk.configuration.save",
                "保存参数扫描配置",
                CONFIG,
                save,
                confirmation=False,
            ),
            Action(
                "stk.submit",
                "确认提交参数扫描",
                object_schema({}),
                submit,
                permission="submit",
            ),
            Action(
                "stk.visualize",
                "生成结果图表",
                object_schema(
                    {
                        "title": STRING,
                        "execution_ids": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 32,
                            "uniqueItems": True,
                            "items": STRING,
                        },
                    }
                ),
                visualize,
                confirmation=False,
            ),
            Action(
                "stk.accept",
                "验收示例读写结果",
                object_schema({"reason": STRING}),
                accept,
                permission="accept",
            ),
        ),
        (
            {
                "id": "stk.workbench",
                "title": "STK 科学工作台",
                "types": ["configuration", "execution", "visualization"],
                "presentation": True,
            },
        ),
        connections=("stk",),
        methods=(ExecutionMethod(method.NAME, method.prepare, method.verify), history.method()),
        queries=queries(),
    )
