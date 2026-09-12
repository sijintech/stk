"""Adopt an existing Runtime task by ID; never upload or submit it again."""
import time
from synorder_connectors.connections import connection, StkClient
from synorder_interaction.contracts import Action, ExecutionMethod, InteractionError, canonical, digest, object_schema, STRING

NAME = "stk.existing-task.v1"


def attach(ctx, values):
    conn = connection(ctx.store, ctx.actor, values["connector_id"], kind="stk")
    if conn["space_id"] != ctx.space:
        raise PermissionError("Runtime 连接不在当前空间")
    factory = getattr(ctx.service.registry, "runtime_client", StkClient)
    client = factory(conn["config"])
    try:
        remote = client.call("GET", "tasks/" + values["task_id"])
    finally:
        client.close()
    previous = ctx.db.execute("SELECT id FROM executions WHERE connector_id=? AND remote_id=?", (conn["id"], remote["id"])).fetchone()
    if previous:
        obj = ctx.store.resource(ctx.actor, previous["id"], db=ctx.db)
        return {"resource_id": obj["id"], "version": obj["version"], "attached": True}
    detail = {"actor": ctx.actor, "engine": NAME, "plugin": {"id": "synorder.stk", "version": "0.1.0"},
        "imported": True, "source_conversation": ctx.conversation["id"], "remote_workspace": remote["spec"]["workspace_id"],
        "verification": "pending", "acceptance": "pending", "results": []}
    ref = ctx.store.put_resource(ctx.db, ctx.actor, ctx.space, "execution", remote["spec"].get("name") or remote["id"], detail, conversation=ctx.conversation, permission="submit")
    from synorder_connectors.execution import ExecutionWorker
    state = "collecting_results" if remote["state"] == "succeeded" else ExecutionWorker.remote_state(remote)
    ctx.db.execute("INSERT INTO executions(id,connector_id,request_key,spec,state,remote_id,started_at,deadline,detail) VALUES (?,?,?,?,?,?,?,?,?)",
        (ref["resource_id"], conn["id"], "synorder-import-" + digest([ctx.store.workspace.id, conn["id"], remote["id"]]), canonical(remote["spec"]), state, remote["id"], time.time(), time.time(), canonical(detail)))
    return {**ref, "attached": True}


def prepare(_detail):
    raise InteractionError("已有任务只能对账或取消，不能重新提交")


def verify(_detail, _contents):
    return {"verification": "not_applicable", "scientific_validation": "not_evaluated", "acceptance": "pending"}


def action():
    return Action("stk.attach", "收录已有 Runtime 任务", object_schema({"connector_id": STRING,
        "task_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,128}$"}}), attach, permission="submit")


def method():
    return ExecutionMethod(NAME, prepare, verify)
