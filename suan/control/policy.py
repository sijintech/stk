"""Only registered exact command templates, and graph evaluations within budget, bypass review.

Graph requests are validated here without NumPy (``suan.graph.schema`` and the
node catalog are standard library only), so a malformed graph never reaches a
node.
"""
import json
from pathlib import PurePosixPath
import re
from suan.runtime.models import TaskSpec, layout, relative_path

KINDS = {"workspace.create", "task.submit", "task.cancel", "task.logs", "task.artifacts",
         "file.read", "view.build", "view.probe", "graph.evaluate", "graph.meta", "task.events"}
TASK_ID = re.compile(r"[a-f0-9]{32}")
EVENTS_LIMIT = 1024 * 1024
GRAPH_META_PARTS = ("catalog", "presets", "features", "render")
# Automatic execution budget of graph.evaluate (m1-plan section 7): 300 s, 128 MiB of output and the
# phone/web payload profiles, whose volume budget is at most 256^3 voxels.
GRAPH_AUTO_SECONDS = 300
GRAPH_AUTO_OUTPUT_BYTES = 128 * 1024 * 1024
GRAPH_AUTO_PROFILES = {"phone", "web"}
GRAPH_AUTO_PAYLOAD = {"triangles": 2_000_000, "instances": 500_000, "points": 2_000_000, "voxels": 256 ** 3,
                      "bytes": 128 * 1024 * 1024}
GRAPH_AUTO_PIXELS = 7680 * 4320
GRAPH_REQUEST_BYTES = 512 * 1024
GRAPH_REVIEW = "图谱计算超过自动执行额度"
DEMO_TEMPLATE = {"argv": ["@python", "-m", "suan.control.demo_job"],
                 "outputs": ["scalar-0.vti", "scalar-1.vti", "vector.vti"]}


def validate_action(body, templates):
    if set(body) - {"id", "node_id", "kind", "payload"}:
        raise ValueError("Unknown action property")
    for key in ("id", "node_id"):
        if not isinstance(body.get(key), str) or not re.fullmatch(r"[a-f0-9]{32}", body[key]):
            raise ValueError("Action and node IDs must be 32 lowercase hexadecimal characters")
    if body.get("kind") not in KINDS or not isinstance(body.get("payload"), dict):
        raise ValueError("Unknown action kind or invalid payload")
    p = body["payload"]
    kind = body["kind"]
    if kind == "workspace.create":
        if set(p) != {"name"} or not isinstance(p["name"], str) or not 1 <= len(p["name"].strip()) <= 200:
            raise ValueError("Workspace name is required")
    if kind in {"task.cancel", "task.logs", "task.artifacts", "file.read", "view.build", "view.probe"}:
        if not re.fullmatch(r"[a-f0-9]{32}", str(p.get("task_id", ""))):
            raise ValueError("Task ID required")
    if kind in {"file.read", "view.build", "view.probe"}:
        relative_path(p.get("path"))
    if kind == "task.events":
        return validate_task_events(p)
    if kind == "graph.meta":
        return validate_graph_meta(p)
    if kind == "graph.evaluate":
        return validate_graph_evaluate(p)
    if kind != "task.submit":
        return ""
    if set(p) - {"spec", "template"}:
        raise ValueError("Unknown submission property")
    spec = TaskSpec(**p.get("spec", {})).to_dict()
    template = templates.get(p.get("template"))
    r = spec["resources"]
    shape = layout(r)
    # MPI layouts count ranks x threads; legacy layouts count cpus (ranks is 1).
    cores = shape["ranks"] * shape["threads_per_rank"]
    # A cluster job without a time limit runs to the partition default, which may be unlimited.
    high = (cores > 8 or r.get("nodes", 1) > 1 or r.get("gpus", 0) > 0
            or r.get("memory_mb", 0) > 16384 or r.get("walltime_seconds", 0) > 3600
            or (spec["backend"] != "local" and "walltime_seconds" not in r))
    if high:
        return "资源请求超过自动执行额度，请检查 CPU、内存、时长与 GPU。"
    # Only an exact template run bypasses review: every field but the workspace and name must match.
    if not template or TaskSpec(**{**template, "workspace_id": spec["workspace_id"], "name": spec["name"]}).to_dict() != spec:
        return "新命令或模板变更：请检查完整参数后批准执行。"
    return ""


def _count(value, name, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or (maximum is not None and value > maximum):
        bound = f" and at most {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be an integer of at least {minimum}{bound}")


def validate_task_events(p):
    """``{task_id, offset?, limit?}``: a read of the task's monitoring events; never reviewed."""
    if set(p) - {"task_id", "offset", "limit"}:
        raise ValueError("task.events accepts only task_id, offset and limit")
    if not TASK_ID.fullmatch(str(p.get("task_id", ""))):
        raise ValueError("Task ID required")
    if "offset" in p:
        _count(p["offset"], "offset")
    if "limit" in p:
        _count(p["limit"], "limit", 1, EVENTS_LIMIT)
    return ""


def validate_graph_meta(p):
    """``{include?: [catalog|presets|features|render]}``: the node's graph capabilities; never reviewed."""
    if set(p) - {"include"}:
        raise ValueError("graph.meta accepts only include")
    include = p.get("include", [])
    if not isinstance(include, list) or any(item not in GRAPH_META_PARTS for item in include):
        raise ValueError("graph.meta include lists catalog, presets, features or render")
    return ""


def _issue_text(issue):
    where = f"{issue.path}: " if issue.path else ""
    hint = f" (hint: {issue.hint})" if issue.hint else ""
    return f"{issue.code} {where}{issue.message}{hint}"


def _binding_path(value, where):
    """Relative paths inside a binding only: graphs never carry filesystem paths."""
    if value in ("", "."):
        return
    if ("\\" in value or "\x00" in value or value.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", value)
            or ".." in PurePosixPath(value).parts):
        raise ValueError(f"{where} must be a path relative to its binding (no absolute paths, '~', '..', "
                         "backslashes or drive letters)")


def _graph_paths(graph, registry, values):
    from suan.graph.schema import substitute_params
    for index, node in enumerate(graph.get("nodes") or ()):
        node_type = registry.get(node.get("type")) if isinstance(node, dict) else None
        if node_type is None:
            continue
        for name, raw in (node.get("params") or {}).items():
            spec = node_type.params.get(name)
            if spec is None or spec.schema.get("x-stk-widget") != "path":
                continue
            try:
                value = substitute_params(raw, values)
            except (KeyError, TypeError):
                continue  # an unset parameter: the node refuses it at evaluation
            if isinstance(value, str):
                _binding_path(value, f"/nodes/{index}/params/{name}")


def _payload_budget_reasons(graph, values):
    from suan.graph.schema import substitute_params

    def params_of(node):
        try:
            params = substitute_params(node.get("params") or {}, values)
        except (KeyError, TypeError):
            return {}
        return params if isinstance(params, dict) else {}

    nodes = {node.get("id"): node for node in graph.get("nodes") or () if isinstance(node, dict)}
    reasons = []
    for node in nodes.values():
        node_type = str(node.get("type", ""))
        params = params_of(node)
        if node_type.startswith("stk.output.payload@"):
            # "auto" (the default) is the request profile, which is checked on its own.
            if params.get("profile", "auto") not in GRAPH_AUTO_PROFILES | {"auto"}:
                reasons.append("桌面级渲染数据包")
            budget = params.get("budget") or {}
            if isinstance(budget, dict) and any(not isinstance(budget.get(key), int) or budget[key] > limit
                                                for key, limit in GRAPH_AUTO_PAYLOAD.items() if key in budget):
                reasons.append("渲染数据包预算")
        elif node_type.startswith("stk.output.image@"):
            # An image without its own size takes the scene's viewport (1600 x 1200 by default).
            link = (node.get("inputs") or {}).get("source")
            source = nodes.get(str(link.get("from", "")).split(".")[0]) if isinstance(link, dict) else None
            viewport = params_of(source) if source and str(source.get("type", "")).startswith("stk.view.scene@") else {}
            size = [params.get("width") or viewport.get("width") or 1600,
                    params.get("height") or viewport.get("height") or 1200, params.get("magnification") or 1]
            if all(isinstance(v, int) and not isinstance(v, bool) for v in size):
                if size[0] * size[1] * size[2] ** 2 > GRAPH_AUTO_PIXELS:
                    reasons.append("图像像素")
    return reasons


def validate_graph_evaluate(p):
    """``{graph | preset, bindings: {name: {task_id}}, parameters, outputs, profile, budget, plot_format, accept}``.

    Returns a review reason when the request exceeds the automatic budget, ``""``
    otherwise; raises ``ValueError`` for invalid requests and graphs.
    """
    from suan.graph.catalog import default_registry, load_preset
    from suan.graph.schema import GraphError, parameter_values, validate_graph
    from suan.graph.service import parse_request
    if len(json.dumps(p, ensure_ascii=False, allow_nan=False).encode("utf-8")) > GRAPH_REQUEST_BYTES:
        raise ValueError(f"graph.evaluate requests are limited to {GRAPH_REQUEST_BYTES // 1024} KiB")
    try:
        request = parse_request(p)
    except GraphError as exc:
        raise ValueError(exc.message + (f" ({exc.hint})" if exc.hint else "")) from None
    for name, binding in request["bindings"].items():
        if not TASK_ID.fullmatch(binding["task_id"]):
            raise ValueError(f"Binding '{name}' must name a task ID (32 lowercase hexadecimal characters)")
    accept = p.get("accept", [])
    if not isinstance(accept, list) or len(accept) > 8 or not all(isinstance(a, str) and len(a) <= 64 for a in accept):
        raise ValueError("accept must be a short list of schema names")
    graph = request["graph"]
    if graph is None:
        try:
            graph = load_preset(request["preset"])
        except GraphError as exc:
            raise ValueError(exc.message + (f" ({exc.hint})" if exc.hint else "")) from None
    registry = default_registry()
    errors = [i for i in validate_graph(graph, registry, parameters=request["parameters"]) if i.severity == "error"]
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    types = {n.get("id"): n.get("type") for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)}
    unknown = sorted({str(types.get(i.node)) for i in errors if i.code == "unknown_type"})
    if errors and not all(i.code in {"unknown_type", "catalog_version"} for i in errors):
        shown = [i for i in errors if i.code not in {"unknown_type", "catalog_version"}][:5]
        raise ValueError("Invalid graph: " + "; ".join(_issue_text(i) for i in shown)
                         + (f" (+{len(errors) - len(shown)} more)" if len(errors) > len(shown) else ""))
    declared = graph.get("outputs") or {}
    missing = [name for name in request["outputs"] or () if name not in declared]
    if missing:
        raise ValueError(f"Unknown graph output(s): {', '.join(missing)}; the graph declares {', '.join(declared)}")
    values = parameter_values(graph, request["parameters"])
    _graph_paths(graph, registry, values)
    reasons = []
    budget = request["budget"]
    if "max_seconds" in budget and (budget["max_seconds"] is None or budget["max_seconds"] > GRAPH_AUTO_SECONDS):
        reasons.append("计算时长")
    if "max_output_bytes" in budget and (budget["max_output_bytes"] is None
                                         or budget["max_output_bytes"] > GRAPH_AUTO_OUTPUT_BYTES):
        reasons.append("输出大小")
    if request["profile"] not in GRAPH_AUTO_PROFILES:
        reasons.append("桌面级结果配置")
    reasons += _payload_budget_reasons(graph, values)
    notes = []
    if reasons:
        notes.append(f"{GRAPH_REVIEW}（{'、'.join(dict.fromkeys(reasons))}），请检查图谱与预算后批准执行。")
    if errors:
        # The hub cannot check these nodes' parameters (e.g. a private plugin installed only on the node).
        notes.append(f"图谱包含控制服务未安装的节点类型（{'、'.join(unknown or ['?'])}），"
                     "请确认执行节点已安装对应插件并检查其参数后批准执行。")
    return "".join(notes)
