"""Source nodes ``stk.source.*@1``: read run files through graph bindings (docs/specs/stk-graph-v1.md §14).

Declarations are copied from ``docs/specs/catalog/m1_nodes.py`` (the frozen
catalog). Graphs never contain filesystem paths: every source names a
``binding`` that the caller resolves (``ctx.resolve``) to a
``suan.connectors.api.FileSource``, plus paths relative to it. Heavy imports
stay inside the functions (the hub imports catalogs without NumPy).

Fingerprints describe the file content a node reads, so cache keys follow the
data: ``muferro_run`` lists the frame files (path, size) and hashes the small
run outputs; ``muferro_frame``, ``file`` and ``table`` give the path and
sha256 of the file they read.
"""
from suan.graph.registry import (NodeExecutionError, Port, binding, enum, integer, json_param, node, rel_path, step,
                                 string, string_list, vector3)

RUN_FILES = ("energy_out.dat", "mupro_progress.jsonl", "mupro_completion.json")
TABLE_LIMIT = 256 * 1024 * 1024


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


def _failure(exc):
    """A connector/reader error as the node error the evaluator reports (stable code)."""
    return NodeExecutionError(str(exc), code=getattr(exc, "code", None) or "node_failed")


def _source(ctx, name):
    return ctx.resolve(name)


def _prefix(case_dir):
    from suan.connectors.mupro import case_prefix
    return case_prefix(case_dir)


def _muferro():
    """The active ``mupro.muferro`` connector (a private higher-priority package wins)."""
    from suan.connectors.registry import default_registry
    return default_registry().get("mupro.muferro")


# ---------------------------------------------------------------------------
# stk.source.muferro_run


def _muferro_run_fingerprint(ctx, inputs, params):
    from suan.connectors.api import ConnectorError
    from suan.mupro.run import FRAME, RESULT
    source = _source(ctx, params["binding"])
    prefix = _prefix(params["case_dir"])
    from suan.connectors.mupro import run_files
    names = run_files(source, prefix)
    frames = sorted([path, item.size] for path, item in names.items()
                    if path.startswith(prefix) and "/" not in path[len(prefix):] and FRAME.search(path))
    try:
        hashed = {path: source.sha256(path) for path in [prefix + name for name in RUN_FILES] + [RESULT]
                  if path in names}
    except ConnectorError as exc:
        raise _failure(exc) from None
    connector = _muferro()
    return {"connector": f"{connector.id}@{connector.version}", "case_dir": params["case_dir"], "frames": frames,
            "sha256": hashed}


def _frames_table(result, attrs):
    import numpy as np
    from suan.connectors.mupro import frame_rows
    from suan.data.model import Table
    rows = frame_rows(result)
    table = Table(id="frames", attrs=attrs)
    table.add_column("dataset", np.array([r["dataset"] for r in rows], dtype=str))
    table.add_column("step", np.array([r["step"] for r in rows], dtype=np.int64), role="index", quantity="step",
                     unit="1")
    table.add_column("time", np.array([np.nan if r["time"] is None else r["time"] for r in rows], dtype=np.float64))
    table.add_column("path", np.array([r["path"] for r in rows], dtype=str))
    table.add_column("size", np.array([r["size"] or 0 for r in rows], dtype=np.int64), unit="By")
    table.add_column("sha256", np.array([r["sha256"] or "" for r in rows], dtype=str))
    table.add_column("reader", np.array([r["reader"] for r in rows], dtype=str))
    table.add_column("components", np.array([r["components"] or 0 for r in rows], dtype=np.int64), unit="1")
    return table


def _empty_table(table_id, columns, index="step"):
    import numpy as np
    from suan.data.model import Table
    table = Table(id=table_id, index=index)
    for name in columns:
        dtype = np.int64 if name in ("step", "completed_steps", "total_steps") else np.float64
        table.add_column(name, np.zeros(0, dtype=dtype), unit="1" if dtype is np.int64 else "normalized",
                         role="index" if name == index else None)
    return table


@node("stk.source.muferro_run", title={"en": "muFerro run", "zh": "muFerro 计算"},
      description={"en": "Index of a muFerro run directory: published field frames, the energy trace, "
                         "the progress log and the derived stk.result/1 manifest."},
      outputs=[Port("frames", "table", kind="frames"), Port("energy", "table"), Port("progress", "table"),
               Port("result", "value", value_type="json")],
      params={
          "binding": binding(title="Run binding",
                             description="Binding name resolved by the caller to {task_id} or a local directory."),
          "case_dir": rel_path(".", title="Case directory",
                               description="Directory inside the binding holding input.toml and the outputs."),
      },
      time_dependent=True, fingerprint=_muferro_run_fingerprint)
def muferro_run(ctx, inputs, params):
    from suan.connectors.api import ConnectorError
    from suan.connectors.mupro.tables import ENERGY_COLUMNS
    from suan.connectors.mupro import MuFerroConnector
    source = _source(ctx, params["binding"])
    connector = _muferro()
    # A replacement connector (e.g. the private stk-mupro package) implements the plain protocol.
    ours = isinstance(connector, MuFerroConnector)
    if params["case_dir"] != "." and not ours:
        raise NodeExecutionError(f"Connector {connector.id} does not take a case directory", code="unsupported")
    extra = {"case_dir": params["case_dir"]} if ours else {}
    try:
        result = connector.describe(source, live=True, **extra)
        datasets = {d["id"] for d in result["datasets"]}
        extra = {**extra, "result": result} if ours else {}
        energy = connector.open(source, "energy", **extra).read(frame=None) if "energy" in datasets else None
        progress = connector.open(source, "progress", **extra).read(frame=None) if "progress" in datasets else None
    except ConnectorError as exc:
        raise _failure(exc) from None
    if energy is None:
        energy = _empty_table("energy", ("step",) + ENERGY_COLUMNS)
        ctx.warn("The run has no energy_out.dat yet", code="empty_result")
    if progress is None:
        progress = _empty_table("progress", ("step", "completed_steps", "total_steps"))
    files = {f["path"] for f in result.get("files", ())}
    extension = (result.get("extensions") or {}).get("mupro") or {}
    complete = _prefix(params["case_dir"]) + "mupro_completion.json" in files and not extension.get("missing_frames")
    frames = _frames_table(result, {"binding": params["binding"], "case_dir": params["case_dir"],
                                    "complete": bool(complete)})
    if not frames.n_rows:
        ctx.warn("The run has no field frames yet", code="empty_result")
    return {"frames": frames, "energy": energy, "progress": progress, "result": result}


# ---------------------------------------------------------------------------
# stk.source.muferro_frame


def _frame_rows(frames, stem):
    table = frames
    if "binding" not in (table.attrs or {}):
        raise NodeExecutionError("The frames table does not name its binding (link stk.source.muferro_run)",
                                 code="invalid_input")
    datasets = table.column("dataset")
    rows = []
    for i in range(table.n_rows):
        if str(datasets[i]) == stem:
            rows.append({"step": int(table.column("step")[i]), "path": str(table.column("path")[i]),
                         "sha256": str(table.column("sha256")[i]) or None, "reader": str(table.column("reader")[i]),
                         "components": int(table.column("components")[i]) or None})
    return rows


def _resolve_frame(ctx, inputs, params):
    """The frames-table row the ``step``/``policy`` params select; reports the steps as choices."""
    from suan.connectors.api import ConnectorError
    from suan.connectors.builtin import select_frame
    frames = inputs["frames"]
    rows = _frame_rows(frames, params["dataset"])
    steps = sorted({row["step"] for row in rows})
    wanted = params["step"]
    selector = {"latest": True} if wanted == "latest" else {"first": True} if wanted == "first" else \
        {"step": int(wanted), "policy": params["policy"]}
    try:
        chosen = select_frame(rows, selector)
    except ConnectorError as exc:
        ctx.report_choices("step", steps)
        raise NodeExecutionError(f"{params['dataset']}: {exc}", code=exc.code) from None
    ctx.report_choices("step", steps, value=chosen["step"])
    source = _source(ctx, frames.attrs["binding"])
    if not chosen["sha256"]:
        try:
            chosen = dict(chosen, sha256=source.sha256(chosen["path"]))
        except ConnectorError as exc:
            raise _failure(exc) from None
    return source, chosen


def _muferro_frame_fingerprint(ctx, inputs, params):
    _, chosen = _resolve_frame(ctx, inputs, params)
    return {"path": chosen["path"], "sha256": chosen["sha256"], "reader": chosen["reader"]}


@node("stk.source.muferro_frame", title={"en": "muFerro frame", "zh": "muFerro 帧"},
      description={"en": "Read one published field frame '<dataset>.<step:08d>.dat' of a muFerro run as an "
                         "image dataset (VTK order (z,y,x,c)). Reports the available steps as choices."},
      inputs=[Port("frames", "table", accepts=["frames"])],
      outputs=[Port("out", "dataset", kind="image")],
      params={
          "dataset": string("Polar", pattern=r"^[A-Za-z][A-Za-z0-9_]{0,7}$", title="Field stem"),
          "step": step("latest", title="Step"),
          "policy": enum(["latest_at_or_before", "exact"], "latest_at_or_before", title="Step policy"),
          "spacing": vector3(None, nullable=True, title="Spacing override"),
          "origin": vector3(None, nullable=True, title="Origin override"),
          "length_unit": string("grid_index", min_length=1, title="Length unit"),
          "unit": string("unspecified", min_length=1, title="Field unit"),
          "quantity": _nullable_string(pattern=r"^([a-z0-9_]+:)?[a-z0-9_]+$", title="Quantity override"),
          "precision": enum(["float64", "float32"], "float64"),
      },
      time_dependent=True, cache="disk", fingerprint=_muferro_frame_fingerprint)
def muferro_frame(ctx, inputs, params):
    from suan.connectors.files import materialize
    from suan.connectors.mupro import CONNECTOR_ID, READER, VERSION, stem_field
    from suan.data.dat import DatError, read_dat_image
    from suan.data.model import Provenance
    source, chosen = _resolve_frame(ctx, inputs, params)
    stem = params["dataset"]
    try:
        entry = stem_field(stem, chosen["components"])
    except Exception as exc:
        raise _failure(exc) from None
    provenance = Provenance(activity={"kind": "run", "id": None},
                            agent={"connector": f"{CONNECTOR_ID}@{VERSION}", "reader": READER, "node": ctx.node_id},
                            used=[{"path": chosen["path"], "sha256": chosen["sha256"], "role": "input"}])
    try:
        image = read_dat_image(materialize(source, chosen["path"]), name=stem, id=stem, dtype=params["precision"],
                               spacing=params["spacing"], origin=params["origin"], length_unit=params["length_unit"],
                               unit=params["unit"], quantity=params["quantity"] or entry.get("quantity"),
                               tensor=entry["tensor"], component_names=entry.get("component_names"),
                               step=chosen["step"], provenance=provenance, check=ctx.check)
    except DatError as exc:
        raise NodeExecutionError(f"{chosen['path']}: {exc}", code="invalid_data") from None
    except Exception as exc:
        if getattr(exc, "code", None):
            raise _failure(exc) from None
        raise
    if image.field(stem).components != entry["components"]:
        raise NodeExecutionError(f"{chosen['path']} has {image.field(stem).components} components; muFerro's "
                                 f"{stem} has {entry['components']}", code="invalid_data")
    return image


# ---------------------------------------------------------------------------
# stk.source.file


def _file_fingerprint(ctx, inputs, params):
    from suan.connectors.api import ConnectorError
    from suan.connectors.builtin import detect_format
    source = _source(ctx, params["binding"])
    try:
        return {"path": params["path"], "sha256": source.sha256(params["path"]),
                "format": detect_format(params["path"], params["format"])}
    except ConnectorError as exc:
        raise _failure(exc) from None


def _with_geometry(image, origin, spacing, length_unit):
    from suan.data.model import ImageData
    result = ImageData(image.dimensions, origin if origin is not None else image.origin,
                       spacing if spacing is not None else image.spacing, image.direction, frame=image.frame,
                       length_unit=length_unit or image.length_unit, id=image.id, time=image.time, frames=image.frames,
                       provenance=image.provenance, attrs=image.attrs, label=image.label)
    for field in image.fields.values():
        result.add(field)
    return result


@node("stk.source.file", title={"en": "Field file", "zh": "场文件"},
      description={"en": "Read a field file inside a binding: MuPRO DAT, NPY, VTI, legacy VTK STRUCTURED_POINTS "
                         "or VTKHDF (image or polydata)."},
      outputs=[Port("out", "dataset", kind=["image", "polydata"])],
      params={
          "binding": binding(),
          "path": rel_path(title="Relative path"),
          "format": enum(["auto", "dat", "npy", "vti", "vtk", "vtkhdf"], "auto"),
          "fields": string_list(None, nullable=True, max_items=64, title="Arrays to load (default all)"),
          "association": enum(["auto", "point", "cell"], "auto"),
          "spacing": vector3(None, nullable=True),
          "origin": vector3(None, nullable=True),
          "length_unit": _nullable_string(min_length=1),
          "unit": _nullable_string(min_length=1),
          "quantity": _nullable_string(pattern=r"^([a-z0-9_]+:)?[a-z0-9_]+$"),
          "step": integer(None, nullable=True, minimum=0, title="Time step metadata"),
      },
      cache="disk", fingerprint=_file_fingerprint)
def file_source(ctx, inputs, params):
    from dataclasses import replace
    from suan.connectors.api import ConnectorError
    from suan.connectors.builtin import READERS, detect_format, read_file
    from suan.data.model import Provenance, TimeInfo
    source = _source(ctx, params["binding"])
    path = params["path"]
    try:
        kind = detect_format(path, params["format"])
        dataset = read_file(source, path, format=kind, fields=params["fields"], association=params["association"],
                            check=ctx.check)
        sha = source.sha256(path)
    except (ConnectorError, ValueError) as exc:
        raise _failure(exc) from None
    if dataset.kind not in ("image", "polydata"):
        raise NodeExecutionError(f"{path} holds a {dataset.kind}; use stk.source.table@1", code="kind_mismatch")
    if dataset.kind == "image" and (params["spacing"] is not None or params["origin"] is not None
                                   or params["length_unit"]):
        dataset = _with_geometry(dataset, params["origin"], params["spacing"], params["length_unit"])
    elif dataset.kind == "polydata":
        if params["spacing"] is not None or params["origin"] is not None:
            raise NodeExecutionError("spacing/origin overrides apply to images only", code="invalid_param")
        if params["length_unit"]:
            dataset.length_unit = params["length_unit"]
    for name, field in list(dataset.fields.items()):
        changes = {}
        if params["unit"]:
            changes["unit"] = params["unit"]
        if params["quantity"]:
            changes["quantity"] = params["quantity"]
        if changes:
            dataset.fields[name] = replace(field, **changes)
    if params["step"] is not None:
        dataset.time = TimeInfo(step=params["step"])
    dataset.provenance = Provenance(activity={"kind": "import", "id": None},
                                    agent={"reader": READERS[kind], "node": ctx.node_id},
                                    used=[{"path": path, "sha256": sha, "role": "input"}])
    return dataset


# ---------------------------------------------------------------------------
# stk.source.table


def _table_format(path, text, wanted):
    from pathlib import PurePosixPath
    from suan.mupro.run import ENERGY_ROW
    if wanted != "auto":
        return wanted
    name = PurePosixPath(path).name.lower()
    if name == "energy_out.dat" or any(ENERGY_ROW.fullmatch(line) for line in text.splitlines()[:3]):
        return "muferro_energy"
    if name.endswith((".jsonl", ".ndjson")):
        return "progress_jsonl"
    if name.endswith(".csv"):
        return "csv"
    return "columns"


def _table_fingerprint(ctx, inputs, params):
    from suan.connectors.api import ConnectorError
    source = _source(ctx, params["binding"])
    try:
        return {"path": params["path"], "sha256": source.sha256(params["path"]), "format": params["format"]}
    except ConnectorError as exc:
        raise _failure(exc) from None


@node("stk.source.table", title={"en": "Table file", "zh": "表格文件"},
      description={"en": "Read a table file inside a binding: muFerro energy_out.dat, whitespace columns "
                         "(optional header), CSV or a progress JSONL log."},
      outputs=[Port("out", "table")],
      params={
          "binding": binding(),
          "path": rel_path(),
          "format": enum(["auto", "muferro_energy", "columns", "csv", "progress_jsonl"], "auto"),
          "columns": string_list(None, nullable=True, max_items=256, title="Columns to keep (default all)"),
          "units": json_param({"type": "object", "additionalProperties": {"type": "string", "minLength": 1}}, {},
                              title="Column units"),
      },
      fingerprint=_table_fingerprint)
def table_source(ctx, inputs, params):
    from dataclasses import replace
    from pathlib import PurePosixPath
    import re
    from suan.connectors.api import ConnectorError
    from suan.connectors.builtin.tables import read_columns, read_csv, read_jsonl
    from suan.connectors.mupro.tables import read_energy
    from suan.data.model import Provenance
    source = _source(ctx, params["binding"])
    path = params["path"]
    try:
        with source.open(path) as stream:
            raw = stream.read(TABLE_LIMIT + 1)
        if len(raw) > TABLE_LIMIT:
            raise NodeExecutionError(f"{path} is larger than {TABLE_LIMIT} bytes", code="budget_exceeded")
        text = raw.decode("utf-8", "replace")
        kind = _table_format(path, text, params["format"])
        table_id = re.sub(r"[^A-Za-z0-9_]", "_", PurePosixPath(path).name.split(".")[0]) or "table"
        if kind == "muferro_energy":
            table = read_energy(text, id="energy" if table_id == "energy_out" else table_id, keep=params["columns"])
            for name, unit in params["units"].items():
                if name not in table.fields:
                    raise ConnectorError(f"Units given for unknown column {name!r}", "invalid_param")
                table.fields[name] = replace(table.fields[name], unit=unit)
        else:
            reader = {"columns": read_columns, "csv": read_csv, "progress_jsonl": read_jsonl}[kind]
            table = reader(text, id=table_id, units=params["units"], keep=params["columns"])
        sha = source.sha256(path)
    except ConnectorError as exc:
        raise _failure(exc) from None
    reader_id = {"muferro_energy": "mupro.energy@1", "progress_jsonl": "stk.jsonl@1", "csv": "stk.csv@1",
                 "columns": "stk.columns@1"}[kind]
    table.provenance = Provenance(activity={"kind": "import", "id": None},
                                  agent={"reader": reader_id, "node": ctx.node_id},
                                  used=[{"path": path, "sha256": sha, "role": "input"}])
    return table
