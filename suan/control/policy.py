"""Only registered exact command templates, reads, and graph evaluations within budget, bypass review.

Graph requests are validated here without NumPy (``suan.graph.schema`` and the
node catalog are standard library only), so a malformed graph never reaches a
node.

Desktop auto-run: a client device the owner paired with ``profile: "desktop"``
(``suan-control pair --role client --profile desktop``) may also run
``graph.evaluate`` requests of the ``desktop`` result profile without review, as
long as the expected transfer (``budget.max_output_bytes``, else the profile's
default delivery limit) stays within the hub's desktop cap (``desktop_bytes``,
default :data:`DESKTOP_AUTO_BYTES`). Time, image and unknown-node limits still
apply. Writes (``workspace.import``) and non-template submissions always go to
review, whoever asks.
"""
import json
import math
from pathlib import PurePosixPath
import re
from suan.runtime.models import TaskSpec, layout, relative_path

KINDS = {"workspace.create", "task.submit", "task.cancel", "task.logs", "task.artifacts",
         "file.read", "view.build", "view.probe", "graph.evaluate", "graph.meta", "task.events",
         "workspace.files", "workspace.import", "graph.cancel"}
# Reads the hub may forward to a node without an action row (POST /api/v1/nodes/{id}/read).
READ_KINDS = frozenset({"task.logs", "task.events", "task.artifacts", "file.read", "workspace.files"})
TASK_ID = re.compile(r"[a-f0-9]{32}")
SHA256 = re.compile(r"[a-f0-9]{64}")
MIB = 1024 * 1024
# Default expected-transfer cap of desktop auto-run; the hub owner changes it (suan-control serve
# --desktop-auto-mib, or "desktop_auto_mib" in control.json); 0 turns desktop auto-run off.
DESKTOP_AUTO_BYTES = 256 * MIB
# Payload counts a desktop device may request without review (the desktop profile of stk-render-payload-v2 §7).
GRAPH_DESKTOP_PAYLOAD = {"triangles": 20_000_000, "instances": 5_000_000, "points": 20_000_000, "voxels": 1024 ** 3}
IMPORT_MAX_FILES = 10_000
IMPORT_PATH_BYTES = 1024
IMPORT_REVIEW = "导入上传的文件会写入工作区（可能覆盖同名输入文件），请检查文件列表后批准。"
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


def validate_action(body, templates, *, desktop_bytes=None):
    """The review reason of an action (``""``: runs at once); raises ``ValueError`` for invalid actions.

    ``desktop_bytes`` is the hub's desktop auto-run cap when the requesting device holds the
    desktop profile (``None`` or 0 otherwise); it only widens what ``graph.evaluate`` may run.
    """
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
    if kind in {"task.cancel", "task.logs", "task.artifacts", "view.build", "view.probe"}:
        if not re.fullmatch(r"[a-f0-9]{32}", str(p.get("task_id", ""))):
            raise ValueError("Task ID required")
    if kind == "file.read":
        # A task artifact (task_id) or, since the hub upload path, a workspace input (workspace_id).
        owners = [key for key in ("task_id", "workspace_id") if key in p]
        if len(owners) != 1 or not TASK_ID.fullmatch(str(p[owners[0]])):
            raise ValueError("file.read needs exactly one of task_id or workspace_id")
        if "offset" in p:
            _count(p["offset"], "offset")
    if kind in {"file.read", "view.build", "view.probe"}:
        relative_path(p.get("path"))
    if kind == "task.events":
        return validate_task_events(p)
    if kind == "graph.meta":
        return validate_graph_meta(p)
    if kind == "graph.evaluate":
        return validate_graph_evaluate(p, desktop_bytes=desktop_bytes)
    if kind == "workspace.files":
        if set(p) != {"workspace_id"} or not TASK_ID.fullmatch(str(p["workspace_id"])):
            raise ValueError("workspace.files accepts only workspace_id")
        return ""
    if kind == "graph.cancel":
        if set(p) != {"action_id"} or not TASK_ID.fullmatch(str(p["action_id"])):
            raise ValueError("graph.cancel accepts only action_id (the graph.evaluate action)")
        return ""
    if kind == "workspace.import":
        return validate_workspace_import(p)
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


def import_path(value):
    """A normalized POSIX path relative to the workspace inputs (checked on the hub and again on the node)."""
    if not isinstance(value, str) or any(ord(c) < 0x20 or ord(c) == 0x7f for c in value):
        raise ValueError("Import paths are nonempty strings without control characters")
    if relative_path(value) != value or value.endswith("/"):
        raise ValueError(f"Import path {value!r} must be a normalized relative path (no '.', '..', '//', "
                         "absolute paths, backslashes or drive letters)")
    if len(value.encode("utf-8")) > IMPORT_PATH_BYTES or any(len(part.encode("utf-8")) > 255
                                                              for part in value.split("/")):
        raise ValueError(f"Import path {value[:80]!r} is too long")
    return value


def validate_workspace_import(p):
    """``{workspace_id, files: [{path, sha256, size}]}``: hub blobs into workspace inputs; always reviewed."""
    if not isinstance(p, dict) or set(p) != {"workspace_id", "files"}:
        raise ValueError("workspace.import accepts only workspace_id and files")
    if not TASK_ID.fullmatch(str(p["workspace_id"])):
        raise ValueError("Workspace ID required")
    files = p["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= IMPORT_MAX_FILES:
        raise ValueError(f"workspace.import imports 1 to {IMPORT_MAX_FILES} files")
    paths = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise ValueError("Each imported file is {path, sha256, size}")
        path = import_path(item["path"])
        if path in paths:
            raise ValueError(f"Duplicate import path {path!r}")
        paths.add(path)
        if not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
            raise ValueError("Each imported file names its blob by sha256")
        _count(item["size"], "size")
    # A path cannot be both a file and the folder of another file.
    for path in paths:
        parts = path.split("/")
        if any("/".join(parts[:i]) in paths for i in range(1, len(parts))):
            raise ValueError(f"Import path {path!r} lies inside another imported file")
    return IMPORT_REVIEW


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


def _finite(value):
    """``float(value)`` for a finite JSON number, else ``None`` (booleans, strings, NaN and infinities)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _pixels(width, height, magnification=1):
    """Raster pixels of ``width x height`` at ``magnification`` (per axis); ``None`` when not computable.

    Values are compared as floats, so integral floats (``16384.0``, accepted for integer params and
    rendered as integers) count like integers, and anything that is not a finite number fails closed.
    """
    size = [_finite(v) for v in (width, height, magnification)]
    if any(v is None or v < 0 for v in size):
        return None
    return size[0] * size[1] * size[2] ** 2


def _plot_size(params):
    """``(width_px, height_px)`` of a ``stk.plot.*`` node's figure (``size_in`` x ``dpi``), or ``None``."""
    size_in = params.get("size_in", [6.0, 4.0])
    dpi = _finite(params.get("dpi", 200))
    if not isinstance(size_in, (list, tuple)) or len(size_in) != 2 or dpi is None:
        return None
    inches = [_finite(v) for v in size_in]
    if any(v is None for v in inches):
        return None
    return inches[0] * dpi, inches[1] * dpi


def _payload_budget_reasons(graph, values, outputs=None, plot_format="svg", desktop_bytes=None):
    """Review reasons of the graph's payload, image and plot budgets (fail closed on uncomputable sizes).

    ``outputs`` are the requested graph outputs (``None``: all) and ``plot_format`` the format plot
    outputs are delivered in: a plot delivered as PNG is a raster of ``size_in x dpi`` pixels.
    ``desktop_bytes`` (desktop devices): payloads may use the desktop profile and its counts, with
    ``bytes`` up to the cap.
    """
    payload_limits = {**GRAPH_DESKTOP_PAYLOAD, "bytes": desktop_bytes} if desktop_bytes else GRAPH_AUTO_PAYLOAD
    from suan.graph.schema import substitute_params

    def params_of(node):
        try:
            params = substitute_params(node.get("params") or {}, values)
        except (KeyError, TypeError):
            return {}
        return params if isinstance(params, dict) else {}

    def linked(node, port):
        link = (node.get("inputs") or {}).get(port)
        if isinstance(link, list) and len(link) == 1:
            link = link[0]
        return nodes.get(str(link.get("from", "")).split(".")[0]) if isinstance(link, dict) else None

    def too_many(pixels):
        return pixels is None or pixels > GRAPH_AUTO_PIXELS

    nodes = {node.get("id"): node for node in graph.get("nodes") or () if isinstance(node, dict)}
    reasons = []
    for node in nodes.values():
        node_type = str(node.get("type", ""))
        params = params_of(node)
        if node_type.startswith("stk.output.payload@"):
            # "auto" (the default) is the request profile, which is checked on its own.
            if params.get("profile", "auto") not in GRAPH_AUTO_PROFILES | {"auto"} and not (
                    desktop_bytes and params.get("profile") == "desktop"):
                reasons.append("桌面级渲染数据包")
            budget = params.get("budget") or {}
            if isinstance(budget, dict) and any(not isinstance(budget.get(key), int) or budget[key] > limit
                                                for key, limit in payload_limits.items() if key in budget):
                reasons.append("渲染数据包预算")
        elif node_type.startswith("stk.output.image@"):
            source = linked(node, "source")
            source_type = str(source.get("type", "")) if source else ""
            magnification = params.get("magnification", 1)
            if source_type.startswith("stk.plot."):
                # A plot image is size_in x dpi unless the image sets its own size; SVG/PDF are vector output.
                if params.get("format", "png") == "png":
                    figure = _plot_size(params_of(source))
                    if figure is None:
                        reasons.append("图像像素")
                    elif too_many(_pixels(params.get("width") or figure[0], params.get("height") or figure[1],
                                          magnification)):
                        reasons.append("图像像素")
            else:
                # A scene image without its own size takes the scene's viewport (1600 x 1200 by default).
                viewport = params_of(source) if source_type.startswith("stk.view.scene@") else {}
                if too_many(_pixels(params.get("width") or viewport.get("width") or 1600,
                                    params.get("height") or viewport.get("height") or 1200, magnification)):
                    reasons.append("图像像素")
    # Plot outputs delivered by the service itself (plot_format png) are rasters too.
    if plot_format == "png":
        declared = graph.get("outputs") if isinstance(graph.get("outputs"), dict) else {}
        for name in (outputs if outputs is not None else list(declared)):
            node = nodes.get(str(declared.get(name, "")).split(".")[0])
            if node and str(node.get("type", "")).startswith("stk.plot."):
                figure = _plot_size(params_of(node))
                if figure is None or too_many(_pixels(*figure)):
                    reasons.append("图像像素")
    return reasons


def validate_graph_evaluate(p, desktop_bytes=None):
    """``{graph | preset, bindings: {name: {task_id}}, parameters, outputs, profile, budget, plot_format, accept}``.

    Returns a review reason when the request exceeds the automatic budget, ``""``
    otherwise; raises ``ValueError`` for invalid requests and graphs. ``desktop_bytes``
    (a desktop device's cap) replaces the output-size and profile rules by the
    expected-transfer rule (see the module docstring).
    """
    from suan.graph.catalog import default_registry, load_preset
    from suan.graph.schema import GraphError, parameter_values, validate_graph
    from suan.graph.service import PROFILE_OUTPUT_BYTES, parse_request
    if isinstance(desktop_bytes, bool) or not isinstance(desktop_bytes, int) or desktop_bytes <= 0:
        desktop_bytes = None
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
    if desktop_bytes:
        # The node refuses to deliver more than max_output_bytes (default: the profile's limit).
        expected = budget["max_output_bytes"] if "max_output_bytes" in budget else PROFILE_OUTPUT_BYTES[
            request["profile"]]
        if expected is None or expected > desktop_bytes:
            reasons.append(f"预计传输超过桌面自动执行上限 {desktop_bytes // MIB} MiB（请设置 budget.max_output_bytes）")
    else:
        if "max_output_bytes" in budget and (budget["max_output_bytes"] is None
                                             or budget["max_output_bytes"] > GRAPH_AUTO_OUTPUT_BYTES):
            reasons.append("输出大小")
        if request["profile"] not in GRAPH_AUTO_PROFILES:
            reasons.append("桌面级结果配置")
    reasons += _payload_budget_reasons(graph, values, request["outputs"], request["plot_format"], desktop_bytes)
    notes = []
    if reasons:
        notes.append(f"{GRAPH_REVIEW}（{'、'.join(dict.fromkeys(reasons))}），请检查图谱与预算后批准执行。")
    if errors:
        # The hub cannot check these nodes' parameters (e.g. a private plugin installed only on the node).
        notes.append(f"图谱包含控制服务未安装的节点类型（{'、'.join(unknown or ['?'])}），"
                     "请确认执行节点已安装对应插件并检查其参数后批准执行。")
    return "".join(notes)
