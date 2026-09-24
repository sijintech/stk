"""``suan graph`` (and ``python -m suan.graph``): catalog, schema, validate, run and doctor.

``catalog``, ``schema`` and ``validate`` need neither NumPy nor VTK. ``run``
evaluates a graph next to the data (bindings name local directories or Runtime
tasks), writes the requested outputs into ``--out`` and, with ``--param
step=all``, one set of files per step plus an ``stk.series/1`` manifest
(SimViz batch re-render). ``doctor`` checks the optional dependencies, the
node modules against the spec catalog and offscreen rendering (in a
subprocess, because a missing EGL/OSMesa aborts the interpreter).
"""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import click

__all__ = ["default_cache_dir", "graph", "main", "probe_offscreen"]

MEDIA_EXTENSIONS = {"image/png": ".png", "image/svg+xml": ".svg", "application/pdf": ".pdf",
                    "application/json": ".json"}
PROFILES = ("phone", "web", "desktop")


def default_cache_dir():
    """``$STK_GRAPH_CACHE``, else the user cache directory (``~/.cache/stk/graph``, ``%LOCALAPPDATA%\\stk\\graph``)."""
    if os.environ.get("STK_GRAPH_CACHE"):
        return Path(os.environ["STK_GRAPH_CACHE"]).expanduser()
    if sys.platform.startswith("win") and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "stk" / "graph"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base).expanduser() / "stk" / "graph"


def probe_offscreen(timeout=120):
    """Run ``python -m suan.render.offscreen --probe`` in a child process.

    Returns ``{"ok", "missing", "reason", "returncode"}``; ``missing`` is True
    when the offscreen renderer is not installed.
    """
    try:
        found = importlib.util.find_spec("suan.render.offscreen")
    except ModuleNotFoundError:
        found = None
    if found is None:
        return {"ok": False, "missing": True, "returncode": None,
                "reason": "suan.render.offscreen is not installed"}
    # The renderer picks its interpreter (STK_RENDER_PYTHON) and isolates VTK in a child process.
    from suan.render import offscreen
    info = offscreen.probe(timeout=timeout)
    if info["ok"]:
        detail = ", ".join(str(info[k]) for k in ("vtk", "window", "renderer") if info.get(k))
        return {"ok": True, "missing": False, "returncode": 0,
                "reason": f"offscreen rendering works in {info['python']}" + (f" ({detail})" if detail else "")}
    return {"ok": False, "missing": False, "returncode": None,
            "reason": f"the offscreen probe failed in {info['python']}: {info.get('error')}"}


def _print_json(value):
    click.echo(json.dumps(value, indent=1, ensure_ascii=False, allow_nan=False))


def _parse_value(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def _parse_pairs(items, what):
    result = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise click.BadParameter(f"{item!r} is not NAME=VALUE", param_hint=what)
        result[name.strip()] = value
    return result


def _load_graph(source):
    from .catalog import PRESET_ID_RE, load_preset
    from .schema import GraphError
    path = Path(source)
    if path.is_file():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise click.ClickException(f"Cannot read {source}: {exc}") from None
        if isinstance(document, dict) and "schema" not in document and isinstance(document.get("graph"), dict):
            document = document["graph"]  # a preset wrapper
        return document
    if PRESET_ID_RE.match(source):
        try:
            return load_preset(source)
        except GraphError as exc:
            raise click.ClickException(f"{exc.message}{' (' + exc.hint + ')' if exc.hint else ''}") from None
    raise click.ClickException(f"No such graph file or preset: {source}")


def _issue_text(issue):
    issue = issue if isinstance(issue, dict) else issue.to_dict()
    where = " ".join(part for part in (issue.get("path") or "", f"({issue['node']})" if issue.get("node") else "")
                     if part)
    text = f"{issue.get('severity', 'error')} [{issue['code']}] {where + ': ' if where else ''}{issue['message']}"
    if issue.get("hint"):
        text += f"\n  hint: {issue['hint']}"
    return text


def _fail(exc):
    """Print a GraphError (with every validation issue or node error) and exit with status 1."""
    from .schema import GraphValidationError
    if isinstance(exc, GraphValidationError):
        for issue in exc.issues:
            click.echo(_issue_text(issue), err=True)
    elif getattr(exc, "errors", None):
        for issue in exc.errors:
            click.echo(_issue_text(issue), err=True)
    else:
        click.echo(_issue_text({"code": exc.code, "message": exc.message, "path": exc.path, "node": exc.node,
                                "hint": exc.hint}), err=True)
    sys.exit(1)


@click.group("graph")
def graph():
    """STK node graphs (stk.graph/1): catalog, validation and headless evaluation."""


@graph.command("catalog")
@click.option("--json", "as_json", is_flag=True, help="Print the stk.catalog/1 document.")
def catalog_command(as_json):
    """List the installed node types."""
    from .catalog import default_registry
    from .nodes import missing_modules
    registry = default_registry()
    if as_json:
        _print_json(registry.catalog())
        return
    for node_type in registry:
        title = node_type.title.get("en", "")
        if node_type.title.get("zh"):
            title += f" / {node_type.title['zh']}"
        click.echo(f"{node_type.id:<40} {node_type.stage:<15} {title}")
    missing = missing_modules()
    if missing:
        click.echo(f"({len(registry)} node types; built-in modules not installed: {', '.join(missing)})", err=True)
    for name, error in getattr(registry, "load_errors", ()):
        click.echo(f"warning: node plugin {name!r} failed to load: {error}", err=True)


@graph.command("schema")
def schema_command():
    """Print the JSON Schema of stk.graph/1 documents."""
    from suan.contracts import load_schema
    _print_json(load_schema("graph-1"))


@graph.command("validate")
@click.argument("source", metavar="FILE")
@click.option("--param", "params", multiple=True, metavar="NAME=VALUE", help="Graph parameter override (JSON value).")
@click.option("--json", "as_json", is_flag=True, help="Print the issues as JSON.")
def validate_command(source, params, as_json):
    """Validate a graph document (or a preset id) against the installed catalog."""
    from .catalog import default_registry
    from .schema import validate_graph
    document = _load_graph(source)
    overrides = {name: _parse_value(value) for name, value in _parse_pairs(params, "--param").items()}
    issues = validate_graph(document, default_registry(), parameters=overrides or None)
    errors = [issue for issue in issues if issue.severity == "error"]
    if as_json:
        _print_json({"valid": not errors, "issues": [issue.to_dict() for issue in issues]})
    else:
        for issue in issues:
            click.echo(_issue_text(issue), err=True)
        if not errors:
            nodes = len(document.get("nodes") or ())
            click.echo(f"ok: {source} is a valid stk.graph/1 document ({nodes} nodes; outputs: "
                       f"{', '.join(document.get('outputs') or {})})")
    if errors:
        sys.exit(1)


class _CollectSink:
    """Blob sink of the CLI: remembers bytes (or local files) by sha256 until they are written out."""

    def __init__(self):
        self.blobs = {}

    def __call__(self, data):
        import hashlib
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = bytes(data)
            digest = hashlib.sha256(data).hexdigest()
        else:
            data = Path(data)
            result = hashlib.sha256()
            with open(data, "rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    result.update(block)
            digest = result.hexdigest()
        self.blobs.setdefault(digest, data)
        return digest

    def write(self, digest, target):
        data = self.blobs[digest]
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        if isinstance(data, Path):
            import shutil
            shutil.copyfile(data, tmp)
        else:
            tmp.write_bytes(data)
        os.replace(tmp, target)

    def json(self, digest):
        data = self.blobs[digest]
        return json.loads(data.read_bytes() if isinstance(data, Path) else data)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(value, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _suffix(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return f".{value:08d}"
    text = value if isinstance(value, str) else json.dumps(value)
    return "." + re.sub(r"[^A-Za-z0-9_-]", lambda m: "%{:02X}".format(ord(m.group())), text)


def _write_outputs(result, sink, out_dir, suffix=""):
    """Write each delivered output under ``out_dir``; returns ``{output: relative path}``.

    ``result<suffix>.json`` and ``series.json`` belong to the CLI: an output whose file would take
    one of these names is written as ``<name><suffix>.output.json`` instead.
    """
    reserved = {f"result{suffix}.json", "series.json"}

    def target_of(stem, extension):
        name = stem + extension
        return out_dir / (f"{stem}.output{extension}" if name in reserved else name)

    files = {}
    for name, entry in result["outputs"].items():
        kind, stem = entry["type"], f"{name}{suffix}"
        if kind == "payload":
            directory = out_dir / stem
            for buffer in entry["manifest"].get("buffers") or ():
                sink.write(buffer["sha256"], directory / f"{buffer['sha256']}.bin")
            _write_json(directory / "manifest.json", entry["manifest"])
            if "scene_v1" in entry:
                _write_json(directory / "scene_v1.json", entry["scene_v1"])
            files[name] = f"{stem}/manifest.json"
        elif kind in ("image", "plot"):
            target = target_of(stem, MEDIA_EXTENSIONS.get(entry.get("media_type"), ".bin"))
            sink.write(entry["blob"], target)
            files[name] = target.name
            if entry.get("data_blob"):
                _write_json(out_dir / f"{stem}.data.json", sink.json(entry["data_blob"]))
        elif kind == "file":
            ext = Path(entry.get("name") or "").suffix
            target = target_of(stem, ext if re.fullmatch(r"\.[A-Za-z0-9_]{1,16}", ext) else ".bin")
            sink.write(entry["blob"], target)
            files[name] = target.name
        else:  # table, value, dataset
            target = target_of(stem, ".json")
            if entry.get("blob"):
                sink.write(entry["blob"], target)
            elif kind == "table":
                _write_json(target, {key: entry[key] for key in ("columns", "units", "attrs") if key in entry})
            elif kind == "value":
                _write_json(target, entry["value"])
            else:
                _write_json(target, entry["descriptor"])
            files[name] = target.name
    return files


def _resolver(bindings, cache_root, connection, state_dir, tmp):
    from .resolve import BindingResolver, HashMemo, LocalDirResolver, RuntimeResolver
    from .schema import GraphError
    local, tasks = {}, {}
    for name, value in bindings.items():
        if value.startswith("task:"):
            tasks[name] = value[len("task:"):]
        else:
            local[name] = Path(value)
    memo = HashMemo(cache_root / "hashes.sqlite") if cache_root is not None else HashMemo()
    try:
        resolvers = [LocalDirResolver(local, hash_memo=memo)]
        if tasks:
            from suan.runtime.cli import LazyClient
            downloads = (cache_root if cache_root is not None else Path(tmp)) / "downloads"
            resolvers.append(RuntimeResolver(LazyClient(connection, state_dir), downloads, tasks))
    except (FileNotFoundError, GraphError) as exc:
        raise click.ClickException(str(exc)) from None
    return BindingResolver(*resolvers)


def _series_values(graph_doc, name, first):
    declared = next((p for p in graph_doc.get("parameters") or () if isinstance(p, dict) and p.get("name") == name),
                    None)
    if declared is not None and declared.get("type") == "enum":
        return list(declared.get("choices") or ())
    entry = (first or {}).get("parameters", {}).get(name) or {}
    return list(entry.get("choices") or ())


@graph.command("run")
@click.argument("source", metavar="FILE")
@click.option("--bind", "binds", multiple=True, metavar="NAME=DIR|task:ID",
              help="Bind a graph binding to a local directory or a Runtime task.")
@click.option("--param", "params", multiple=True, metavar="NAME=VALUE",
              help="Graph parameter (JSON value); NAME=all renders every step/choice.")
@click.option("--output", "outputs", multiple=True, metavar="NAME", help="Graph output to deliver (default: all).")
@click.option("--out", "out_dir", required=True, type=click.Path(path_type=Path, file_okay=False),
              help="Directory for the output files.")
@click.option("--cache", "cache_dir", type=click.Path(path_type=Path, file_okay=False), default=None,
              help="Disk cache directory (default: $STK_GRAPH_CACHE or the user cache directory).")
@click.option("--no-cache", is_flag=True, help="Keep results in memory only.")
@click.option("--profile", type=click.Choice(PROFILES), default="web", show_default=True,
              help="Payload budget profile.")
@click.option("--plot-format", type=click.Choice(["png", "svg"]), default="png", show_default=True)
@click.option("--connection", default=None, help="Saved Runtime connection (for task: bindings).")
@click.option("--state-dir", type=click.Path(path_type=Path), default=None, help="Local Runtime state directory.")
@click.option("--json", "as_json", is_flag=True, help="Print the stk.graph-result/1 (or stk.series/1) document.")
@click.option("-v", "--verbose", is_flag=True, help="Print node events.")
def run_command(source, binds, params, outputs, out_dir, cache_dir, no_cache, profile, plot_format, connection,
                state_dir, as_json, verbose):
    """Evaluate a graph (file or preset id) and write its outputs."""
    from .cache import GraphCache
    from .catalog import default_registry
    from .schema import GraphError
    from .service import evaluate_request
    graph_doc = _load_graph(source)
    parameters = {name: _parse_value(value) for name, value in _parse_pairs(params, "--param").items()}
    bindings = _parse_pairs(binds, "--bind")
    kinds = {p.get("name"): p.get("type") for p in (graph_doc.get("parameters") or ()) if isinstance(p, dict)}
    series = [name for name, value in parameters.items() if value == "all" and kinds.get(name) in ("step", "enum")]
    if len(series) > 1:
        raise click.BadParameter("Only one parameter can be 'all'", param_hint="--param")
    cache_root = None if no_cache else (cache_dir or default_cache_dir())
    cache = GraphCache(cache_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    def on_event(event):
        if verbose and event["type"] in ("node.started", "node.finished", "node.cached", "node.failed", "warning"):
            details = {k: v for k, v in event.items() if k not in ("type", "node", "key")}
            click.echo(f"{event['type']:<14} {event.get('node') or '':<24} {json.dumps(details)}", err=True)

    with tempfile.TemporaryDirectory(prefix="stk-graph-") as tmp:
        resolver = _resolver(bindings, cache_root, connection, state_dir, tmp)
        request = {"graph": graph_doc, "outputs": list(outputs) or None, "profile": profile, "plot_format": plot_format,
                   "budget": {"max_seconds": None, "max_output_bytes": None}}

        def run_once(values):
            sink = _CollectSink()
            try:
                result = evaluate_request({**request, "parameters": values}, resolver=resolver, cache_dir=None,
                                          blob_sink=sink, registry=default_registry(), cache=cache, on_event=on_event)
            except GraphError as exc:
                _fail(exc)
            return result, sink

        if not series:
            result, sink = run_once(parameters)
            result["files"] = _write_outputs(result, sink, out_dir)
            _write_json(out_dir / "result.json", result)
            document = result
            failed = bool(result.get("errors"))
        else:
            name = series[0]
            base = {k: v for k, v in parameters.items() if k != name}
            first = None
            if kinds[name] != "enum":
                first, _ = run_once(base)  # discovers the choices reported by the source nodes
            values = _series_values(graph_doc, name, first)
            if not values:
                raise click.ClickException(f"Parameter {name!r} reported no choices; nothing to render")
            frames, failed, frame_errors = [], False, []
            for value in values:
                result, sink = run_once({**base, name: value})
                suffix = _suffix(value)
                result["files"] = _write_outputs(result, sink, out_dir, suffix)
                _write_json(out_dir / f"result{suffix}.json", result)
                frames.append({name: value, "outputs": result["files"], "result": f"result{suffix}.json"})
                failed = failed or bool(result.get("errors"))
                frame_errors += [(value, issue) for issue in result.get("errors") or ()]
                if verbose:
                    click.echo(f"{name}={value}: {result['cache']}", err=True)
            document = {"schema": "stk.series/1", "parameter": name, "graph_hash": result["graph_hash"],
                        "frames": frames}
            _write_json(out_dir / "series.json", document)
    if as_json:
        _print_json(document)
    else:
        if series:
            click.echo(f"wrote {len(document['frames'])} frames of {document['parameter']} to {out_dir} (series.json)")
        else:
            for name, path in document["files"].items():
                click.echo(f"{name:<20} {out_dir / path}")
            click.echo(f"cache: {document['cache']['hits']} hits, {document['cache']['misses']} misses")
        for issue in document.get("warnings", ()) if not series else ():
            click.echo(_issue_text(issue), err=True)
    if failed:
        if series:
            for value, issue in frame_errors:
                click.echo(f"{series[0]}={json.dumps(value)}: {_issue_text(issue)}", err=True)
        else:
            for issue in document.get("errors") or ():
                click.echo(_issue_text(issue), err=True)
        sys.exit(1)


@graph.command("doctor")
@click.option("--json", "as_json", is_flag=True)
@click.option("--timeout", default=120, show_default=True, help="Seconds allowed for the offscreen probe.")
def doctor_command(as_json, timeout):
    """Check dependencies, node modules and offscreen rendering (in a subprocess)."""
    checks = []

    def add(name, status, detail, hint=None):
        checks.append({"check": name, "status": status, "detail": detail, **({"hint": hint} if hint else {})})

    version = ".".join(map(str, sys.version_info[:3]))
    add("python", "ok" if sys.version_info >= (3, 10) else "fail", version)
    for label, module, hint in (("numpy", "numpy", "pip install 'suan_toolkits[visualization]'"),
                                ("vtk", "vtkmodules.vtkCommonCore", "pip install 'suan_toolkits[visualization]'"),
                                ("h5py", "h5py", "pip install 'suan_toolkits[visualization]'"),
                                ("matplotlib", "matplotlib", "pip install 'suan_toolkits[science]'")):
        try:
            imported = importlib.import_module(module)
        except Exception as exc:
            add(label, "warn", f"not available ({type(exc).__name__})", hint)
            continue
        if label == "vtk":
            detail = imported.vtkVersion.GetVTKVersion()
        else:
            detail = getattr(imported, "__version__", "installed")
        add(label, "ok", str(detail))
    try:
        from .catalog import build_registry, compare_catalog, present_families, spec_catalog
        from .nodes import missing_modules
        registry = build_registry()
        missing = missing_modules()
        add("node modules", "ok" if not missing else "warn",
            f"{len(registry)} node types" + (f"; not installed: {', '.join(missing)}" if missing else ""))
        for name, error in getattr(registry, "load_errors", ()):
            add(f"plugin {name}", "warn", error)
        spec = spec_catalog()
        if spec is not None:
            problems = compare_catalog(build_registry(entry_points=False).catalog(), spec,
                                       families=present_families())
            add("catalog", "ok" if not problems else "fail",
                "built-in node types match docs/specs/catalog/stk-catalog-m1.json" if not problems
                else "; ".join(problems[:10]))
    except Exception as exc:
        add("node modules", "fail", f"{type(exc).__name__}: {exc}")
    cache_root = default_cache_dir()
    parent = next((p for p in [cache_root, *cache_root.parents] if p.exists()), None)
    writable = parent is not None and os.access(parent, os.W_OK)
    add("cache", "ok" if writable else "warn", str(cache_root),
        None if writable else "Set STK_GRAPH_CACHE or pass --cache to a writable directory")
    probe = probe_offscreen(timeout=timeout)
    hint = None if probe["ok"] else ("Install the render package" if probe["missing"] else
                                     "Install EGL (libegl1 libgl1-mesa-dri) or OSMesa (libosmesa6); for OSMesa set "
                                     "VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow")
    add("offscreen rendering", "ok" if probe["ok"] else "warn", probe["reason"], hint)
    if as_json:
        _print_json({"checks": checks, "ok": all(c["status"] != "fail" for c in checks)})
    else:
        for check in checks:
            click.echo(f"{check['status']:<5} {check['check']:<22} {check['detail']}")
            if check.get("hint"):
                click.echo(f"      hint: {check['hint']}")
    if any(check["status"] == "fail" for check in checks):
        sys.exit(1)


def _utf8_stdio():
    """Same rule as ``suan.cli.main.utf8_stdio`` (without importing the whole CLI)."""
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, "encoding", None)
        if encoding is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            "算".encode(encoding)
        except (UnicodeEncodeError, LookupError):
            stream.reconfigure(encoding="utf-8")


def main(argv=None):
    _utf8_stdio()
    graph.main(args=argv, prog_name="python -m suan.graph")
