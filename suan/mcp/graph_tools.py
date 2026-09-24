"""Graph, plot and monitoring tools of the STK MCP server (no MCP dependency).

``suan/mcp/server.py`` registers thin async wrappers around these functions;
they can be called (and tested) directly. Evaluation is local to the MCP host:

* bindings name Runtime tasks (``{"task_id": "..."}`` or ``"task:<id>"``,
  resolved with :class:`suan.graph.resolve.RuntimeResolver` against the
  configured Runtime: ``STK_RUNTIME_URL``/``STK_RUNTIME_TOKEN`` or the local
  service) or, like ``suan graph run --bind``, a directory on this host
  (``{"dir": "/path"}``);
* outputs are written as files under ``output_dir`` (default
  ``$STK_MCP_OUTPUT_DIR`` or ``<tmp>/stk-mcp``) and returned as paths plus a
  compact JSON summary (payload manifests in the ``.stkp`` directory form:
  ``manifest.json`` + ``<sha256>.bin``);
* ``graph_render`` renders a scene offscreen (VTK in a subprocess) and fails
  with a clear message when this host cannot render.
"""
import json
import os
from pathlib import Path
import re
import tempfile

__all__ = ["GraphToolError", "get_task_events", "graph_catalog", "graph_evaluate", "graph_render", "graph_validate",
           "plot_table"]

TASK_ID = re.compile(r"^[a-f0-9]{32}$")
INLINE_ROWS = 200
PLOT_KINDS = ("line", "scatter", "bar", "hist")


class GraphToolError(ValueError):
    """A request the tools cannot serve; the message says what to change."""


def _registry():
    from suan.graph.catalog import default_registry
    return default_registry()


def _issue(issue):
    return issue if isinstance(issue, dict) else issue.to_dict()


def _load(graph, preset):
    from suan.graph.catalog import load_preset
    from suan.graph.schema import GraphError
    if (graph is None) == (preset is None):
        raise GraphToolError("Give exactly one of 'graph' (an stk.graph/1 object) or 'preset' (a preset id)")
    if preset is not None:
        try:
            return load_preset(preset)
        except GraphError as exc:
            raise GraphToolError(f"{exc.message}" + (f" ({exc.hint})" if exc.hint else "")) from None
    if isinstance(graph, str):
        try:
            graph = json.loads(graph)
        except ValueError as exc:
            raise GraphToolError(f"'graph' is not JSON: {exc}") from None
    if not isinstance(graph, dict):
        raise GraphToolError("'graph' must be an stk.graph/1 object")
    return graph


# ---------------------------------------------------------------------------
# Catalog and validation


def _compact(entry):
    params = {}
    for name, schema in ((entry.get("params") or {}).get("properties") or {}).items():
        item = {key: schema[key] for key in ("type", "enum", "default", "minimum", "maximum", "title")
                if key in schema}
        item["stage"] = schema.get("x-stk-stage", "data")
        if schema.get("x-stk-widget"):
            item["widget"] = schema["x-stk-widget"]
        params[name] = item
    return {"id": entry["id"], "title": (entry.get("title") or {}).get("en"),
            "description": (entry.get("description") or {}).get("en"),
            "inputs": [{k: port[k] for k in ("name", "type", "accepts", "required", "multi") if k in port}
                       for port in entry.get("inputs") or ()],
            "outputs": [{k: port[k] for k in ("name", "type", "kinds") if k in port} for port in entry.get("outputs") or ()],
            "params": params, "required": (entry.get("params") or {}).get("required") or []}


def graph_catalog(family=None, node_type=None):
    """Node types and presets. ``node_type`` returns one full declaration; ``family`` filters the list."""
    from suan.graph.catalog import catalog_document, list_presets
    document = catalog_document()
    if node_type:
        entry = next((n for n in document["nodes"] if n["id"] == node_type or n["id"].split("@")[0] == node_type),
                     None)
        if entry is None:
            raise GraphToolError(f"Unknown node type {node_type!r}; call graph_catalog without node_type for the list")
        return entry
    nodes = [n for n in document["nodes"] if family is None or n["id"].split(".")[1] == family]
    presets = [{key: p[key] for key in ("id", "name", "description", "bindings", "parameters")} for p in list_presets()]
    return {"schema": "stk.catalog-summary/1", "namespaces": document.get("namespaces"),
            "port_types": sorted(document.get("port_types") or ()), "nodes": [_compact(n) for n in nodes],
            "presets": presets,
            "notes": ["Graph documents are stk.graph/1; links are written on the input side as {\"from\": \"node.port\"}.",
                      "Params tagged stage 'client' change appearance only; 'data' params re-run the node.",
                      "Sources name a binding (e.g. 'run'); bindings are given at evaluation, never paths in graphs."]}


def graph_validate(graph=None, preset=None, parameters=None):
    """Validate without evaluating (no NumPy needed): ``{valid, errors, warnings, graph_sha256, outputs, parameters}``."""
    from suan.graph.schema import graph_hash, validate_graph
    document = _load(graph, preset)
    issues = [_issue(i) for i in validate_graph(document, _registry(), parameters=parameters or {})]
    errors = [i for i in issues if i["severity"] == "error"]
    result = {"valid": not errors, "errors": errors, "warnings": [i for i in issues if i["severity"] != "error"],
              "outputs": document.get("outputs") if isinstance(document.get("outputs"), dict) else {},
              "parameters": document.get("parameters") or []}
    if not errors:
        result["graph_sha256"] = graph_hash(document).split(":", 1)[-1]
    return result


# ---------------------------------------------------------------------------
# Evaluation


def _output_root(output_dir, name):
    base = Path(output_dir) if output_dir else Path(os.environ.get("STK_MCP_OUTPUT_DIR")
                                                     or Path(tempfile.gettempdir()) / "stk-mcp")
    root = base.expanduser() / name if not output_dir else base.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolver(bindings, cache_root):
    from suan.graph.resolve import BindingResolver, HashMemo, LocalDirResolver, RuntimeResolver
    from suan.graph.schema import GraphError
    local, tasks = {}, {}
    for name, value in (bindings or {}).items():
        if isinstance(value, dict) and set(value) == {"task_id"}:
            tasks[name] = value["task_id"]
        elif isinstance(value, dict) and set(value) == {"dir"}:
            local[name] = value["dir"]
        elif isinstance(value, str) and value.startswith("task:"):
            tasks[name] = value[len("task:"):]
        elif isinstance(value, str) and TASK_ID.match(value):
            tasks[name] = value
        else:
            raise GraphToolError(f"Binding {name!r} must be {{\"task_id\": \"<Runtime task>\"}}, \"task:<id>\" or "
                                 "{\"dir\": \"<directory on this host>\"}")
    try:
        resolvers = [LocalDirResolver(local, hash_memo=HashMemo(cache_root / "hashes.sqlite"))]
        if tasks:
            from suan.runtime.cli import LazyClient
            resolvers.append(RuntimeResolver(LazyClient(None, None), cache_root / "downloads", tasks))
    except (FileNotFoundError, GraphError) as exc:
        raise GraphToolError(str(exc)) from None
    return BindingResolver(*resolvers)


def _run(document, *, bindings, parameters, outputs, profile, plot_format, budget):
    from suan.graph.cli import _CollectSink, default_cache_dir
    from suan.graph.schema import GraphError, GraphValidationError
    from suan.graph.service import evaluate_request, shared_cache
    from suan.plot import ensure_mplconfigdir
    cache_root = default_cache_dir()
    ensure_mplconfigdir(cache_root)  # before plots import matplotlib
    sink = _CollectSink()
    request = {"graph": document, "parameters": parameters or {}, "outputs": outputs, "profile": profile,
               "plot_format": plot_format}
    if budget:
        request["budget"] = budget
    try:
        result = evaluate_request(request, resolver=_resolver(bindings, cache_root), cache_dir=None, blob_sink=sink,
                                  cache=shared_cache(cache_root))
    except GraphValidationError as exc:
        raise GraphToolError("Invalid graph: " + "; ".join(
            f"[{i.code}] {i.path}: {i.message}" + (f" (hint: {i.hint})" if i.hint else "") for i in exc.issues[:8])
        ) from None
    except GraphError as exc:
        details = getattr(exc, "errors", None) or []
        text = "; ".join(f"[{e.get('code')}] {e.get('node') or ''}: {e.get('message')}" for e in details[:5]) \
            if details else f"[{exc.code}] {exc.message}" + (f" (hint: {exc.hint})" if exc.hint else "")
        raise GraphToolError("Evaluation failed: " + text) from None
    return result, sink


def _summary(result, files, root):
    outputs = {}
    for name, entry in result["outputs"].items():
        item = {"type": entry["type"], "file": str(root / files[name])}
        if entry["type"] == "payload":
            manifest = entry["manifest"]
            item["layers"] = [{k: layer.get(k) for k in ("id", "type", "name") if k in layer}
                              for layer in manifest.get("layers") or ()]
            item["buffers"] = len(manifest.get("buffers") or ())
        elif entry["type"] in ("image", "plot"):
            item.update({k: entry[k] for k in ("media_type", "width", "height") if k in entry})
            if entry.get("data_blob"):
                item["data_file"] = str(root / (Path(files[name]).stem + ".data.json"))
        elif entry["type"] == "table" and "columns" in entry:
            rows = max((len(v) for v in entry["columns"].values()), default=0)
            item["rows"], item["units"] = rows, entry.get("units", {})
            if rows <= INLINE_ROWS:
                item["columns"] = entry["columns"]
            if entry.get("attrs"):
                item["attrs"] = entry["attrs"]
        elif entry["type"] == "value" and "value" in entry:
            item["value"] = entry["value"]
        outputs[name] = item
    summary = {"graph_sha256": result["graph_sha256"], "output_dir": str(root), "outputs": outputs,
               "parameters": result.get("parameters"), "warnings": result.get("warnings"),
               "cache": result.get("cache"), "seconds": round(sum((result.get("timings") or {}).values()), 3)}
    if result.get("errors"):
        summary["errors"] = result["errors"]
    return summary


def graph_evaluate(graph=None, preset=None, bindings=None, parameters=None, outputs=None, profile="web",
                   plot_format="svg", budget=None, output_dir=None):
    """Evaluate on this host and write the outputs; returns a summary with absolute file paths."""
    from suan.graph.cli import _write_json, _write_outputs
    document = _load(graph, preset)
    result, sink = _run(document, bindings=bindings, parameters=parameters, outputs=outputs, profile=profile,
                        plot_format=plot_format, budget=budget)
    root = _output_root(output_dir, result["graph_sha256"][:16])
    files = _write_outputs(result, sink, root)
    _write_json(root / "result.json", {**result, "files": files})
    summary = _summary(result, files, root)
    summary["result_file"] = str(root / "result.json")
    return summary


def _image_target(document, output):
    """(graph to evaluate, image output name, whether a scene is rendered offscreen)."""
    nodes = {n.get("id"): n for n in document.get("nodes") or () if isinstance(n, dict)}
    declared = document.get("outputs") or {}

    def node_of(ref):
        return nodes.get(str(ref).split(".")[0])

    def source_is_scene(node):
        source = node_of(((node.get("inputs") or {}).get("source") or {}).get("from", ""))
        return bool(source) and str(source.get("type", "")).startswith("stk.view.scene@")

    names = [output] if output else list(declared)
    if output and output not in declared:
        raise GraphToolError(f"The graph has no output {output!r}; outputs: {', '.join(declared) or 'none'}")
    for name in names:  # an image output of the graph
        node = node_of(declared[name])
        if node and str(node.get("type", "")).startswith("stk.output.image@"):
            return document, name, source_is_scene(node)
    for name in names:  # else render the first scene output
        node = node_of(declared[name])
        if node and str(node.get("type", "")).startswith("stk.view.scene@"):
            extra = {"id": "mcp_render", "type": "stk.output.image@1",
                     "inputs": {"source": {"from": declared[name]}}}
            while extra["id"] in nodes:
                extra["id"] += "_"
            graph = {**document, "nodes": [*document["nodes"], extra],
                     "outputs": {**declared, "mcp_render": f"{extra['id']}.image"}}
            return graph, "mcp_render", True
    raise GraphToolError("The graph has no image or scene output to render; add stk.output.image@1 or name an output")


def graph_render(graph=None, preset=None, bindings=None, parameters=None, output=None, width=None, height=None,
                 output_dir=None):
    """Render one image output (or the first scene) to PNG: ``{"png": bytes, "summary": {...}}``."""
    document, name, offscreen = _image_target(_load(graph, preset), output)
    if offscreen:
        from suan.graph.cli import probe_offscreen
        probe = probe_offscreen()
        if not probe["ok"]:
            raise GraphToolError("Offscreen rendering is unavailable on this host: " + probe["reason"]
                                 + ". Use graph_evaluate for the payload, plots and tables, or point STK_RENDER_PYTHON "
                                   "at a Python with VTK and EGL/OSMesa.")
    if width or height:
        document = dict(document)
        target = document["outputs"][name].split(".")[0]
        document["nodes"] = [{**n, "params": {**(n.get("params") or {}),
                                              **({"width": int(width)} if width else {}),
                                              **({"height": int(height)} if height else {})}}
                             if n.get("id") == target else n for n in document["nodes"]]
    summary = graph_evaluate(document, bindings=bindings, parameters=parameters, outputs=[name],
                             output_dir=output_dir)
    item = summary["outputs"][name]
    if item.get("media_type") != "image/png":
        raise GraphToolError(f"Output {name!r} is {item.get('media_type')}, not a PNG image")
    return {"png": Path(item["file"]).read_bytes(), "summary": summary}


# ---------------------------------------------------------------------------
# Plots and monitoring


def plot_table(columns=None, y=None, x=None, kind="line", units=None, title=None, x_label=None, y_label=None,
               spec=None, format="png", output_dir=None):
    """Plot table columns (or a full ``stk.plot/1`` ``spec``) with matplotlib; writes the image and plotted data."""
    from suan.graph.cli import default_cache_dir
    from suan.plot import ensure_mplconfigdir
    ensure_mplconfigdir(default_cache_dir())  # before matplotlib is imported
    from suan.plot.mpl import render_plot
    from suan.plot.spec import PlotSpecError, check
    if spec is None:
        if not isinstance(columns, dict) or not columns or not all(isinstance(v, list) for v in columns.values()):
            raise GraphToolError("'columns' must be an object {name: [values]} (or pass a full stk.plot/1 'spec')")
        if kind not in PLOT_KINDS:
            raise GraphToolError(f"'kind' must be one of {', '.join(PLOT_KINDS)}")
        ys = [y] if isinstance(y, str) else list(y or [c for c in columns if c != x][:1])
        missing = [c for c in [*ys, *([x] if x else [])] if c not in columns]
        if missing or not ys:
            raise GraphToolError(f"Unknown column(s) {', '.join(missing) or '(none given)'}; columns: {', '.join(columns)}")
        units = dict(units or {})
        table = {"columns": columns, "units": {c: str(units.get(c, "unspecified")) for c in columns}}
        marks = []
        for name in ys:
            data = {"table": "t", "y": name}
            if kind == "hist":
                data = {"table": "t", "x": name}
            elif x:
                data["x"] = x
            marks.append({"type": kind, "axes": "a0", "data": data, "style": {"label": name}})

        def axis(label, names):
            if label:
                return {"label": label}
            if len(names) == 1:
                return {"label": names[0], "unit": table["units"][names[0]]}
            return {}
        axes = {"id": "a0", "grid": [0, 0], "legend": {"loc": "best"} if len(ys) > 1 else False,
                "x": axis(x_label, [x] if x else ([ys[0]] if kind == "hist" else [])),
                "y": axis(y_label, ys if kind != "hist" else [])}
        spec = {"schema": "stk.plot/1", "figure": {"title": title}, "axes": [axes], "marks": marks,
                "tables": {"t": table}}
    try:
        spec = check(spec)
        rendered = render_plot(spec, format=format)
    except (PlotSpecError, ValueError) as exc:
        raise GraphToolError(f"Invalid plot: {exc}") from None
    import hashlib
    digest = hashlib.sha256(rendered["bytes"]).hexdigest()
    root = _output_root(output_dir, "plots")
    target = root / f"plot-{digest[:16]}.{format}"
    target.write_bytes(rendered["bytes"])
    data_file = root / f"plot-{digest[:16]}.data.json"
    data_file.write_text(json.dumps(rendered["data"], ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return {"bytes": rendered["bytes"], "summary": {"file": str(target), "data_file": str(data_file),
                                                    "media_type": rendered["media_type"]}}


def get_task_events(task_id, offset=0, limit=None, client=None):
    """Monitoring events (docs/specs/stk-events-v1.md) of a Runtime task from byte ``offset``."""
    if client is None:
        from suan.runtime.cli import get_client
        client = get_client()
    options = {"offset": int(offset)}
    if limit:
        options["limit"] = int(limit)
    return client.events(task_id, **options)
