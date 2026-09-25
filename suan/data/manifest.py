"""Manifests: ``stk.dataset/1``, ``stk.series/1`` and ``stk.result/1`` (build and validate). Standard library only.

The JSON Schemas in ``suan/contracts/schemas`` are the published contract;
these hand-written checks mirror them (``jsonschema`` is not a dependency) and
return readable problems as ``"<json pointer>: <message>"`` strings.

* ``stk.dataset/1`` -- one dataset's descriptor (``Dataset.descriptor()``);
* ``stk.series/1`` -- the frames of a batch evaluation or a time series:
  ``{"schema", "parameter": "step", "frames": [{"step", "time"?, "outputs"?:
  {name: path | file}, "path"?, "sha256"?, "size"?}]}`` (stk-graph-v1.md §6);
* ``stk.result/1`` -- a run's index, produced by ``Connector.describe``
  (stk-data-format-v1.md §11).
"""
from datetime import datetime, timezone
import math
import re

__all__ = [
    "CHECK_STATUSES", "FILE_ROLES", "RESULT_STATES", "VERIFICATION_STATUSES", "ManifestError",
    "check", "dataset_manifest", "file_entry", "now", "qoi_entry", "result_manifest", "series_manifest", "validate",
    "validate_dataset", "validate_result", "validate_series",
]

RESULT_STATES = ("prepared", "queued", "running", "succeeded", "failed", "cancelled", "interrupted", "unknown")
VERIFICATION_STATUSES = ("passed", "failed", "pending", "skipped", "unknown")
CHECK_STATUSES = ("pass", "fail", "warn", "skip")
FILE_ROLES = ("input", "output", "log", "checkpoint", "manifest", "other")
KINDS = ("image", "rectilinear", "structured", "unstructured", "polydata", "particles", "table", "collection")

_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_READER = re.compile(r"^[a-z0-9_.-]+@[0-9]+$")
_REL_PATH = re.compile(r"^(?![/\\])(?![A-Za-z]:)(?!.*(^|/)\.\.(/|$))[^\\\u0000]+$")
_FIELD_KEYS = {"name", "association", "dtype", "components", "tensor", "component_names", "quantity", "unit",
               "normalization", "categories", "palette", "range", "magnitude_range", "role", "description", "lossy"}
_GEOMETRY_KEYS = {
    "image": {"frame", "length_unit", "dimensions", "origin", "spacing", "direction"},
    "polydata": {"frame", "length_unit", "points", "verts", "lines", "polys", "bounds"},
    "table": {"rows"},
}


class ManifestError(ValueError):
    """A manifest breaks its schema; ``problems`` lists every issue."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems[:5]) + (f" (+{len(self.problems) - 5} more)"
                                                          if len(self.problems) > 5 else ""))


def now():
    """RFC 3339 UTC timestamp with second precision (``2026-09-24T10:00:00Z``)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Small checkers


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(value, minimum=None):
    return isinstance(value, int) and not isinstance(value, bool) and (minimum is None or value >= minimum)


def _object(value, path, problems, *, required=(), allowed=None):
    if not isinstance(value, dict):
        problems.append(f"{path or '/'}: must be an object")
        return False
    for key in required:
        if key not in value:
            problems.append(f"{path}/{key}: is required")
    if allowed is not None:
        for key in value:
            if key not in allowed and not key.startswith("x-"):
                problems.append(f"{path}/{key}: unknown key")
    return True


def _string(value, path, problems, *, nullable=False, pattern=None):
    if value is None and nullable:
        return
    if not isinstance(value, str):
        problems.append(f"{path}: must be a string" + (" or null" if nullable else ""))
    elif pattern is not None and not pattern.match(value):
        problems.append(f"{path}: {value!r} does not match {pattern.pattern}")


def _vector(value, path, problems, size, *, positive=False, integers=False, minimum=None):
    if not isinstance(value, list) or len(value) != size:
        problems.append(f"{path}: must be a list of {size} numbers")
        return
    for i, item in enumerate(value):
        ok = _integer(item, minimum) if integers else _number(item)
        if not ok or (positive and item <= 0):
            problems.append(f"{path}/{i}: invalid value {item!r}")


# ---------------------------------------------------------------------------
# stk.dataset/1


def dataset_manifest(dataset):
    """The stk.dataset/1 descriptor of an in-memory dataset (or a copy of a descriptor dict)."""
    document = dict(dataset) if isinstance(dataset, dict) else dataset.descriptor()
    document.setdefault("schema", "stk.dataset/1")
    return document


def _field(value, path, problems, association=None):
    if not _object(value, path, problems, required=("name", "association", "dtype", "components", "tensor", "unit"),
                   allowed=_FIELD_KEYS):
        return
    from .model import Field
    try:
        Field.from_json(value).validate()
    except (TypeError, ValueError) as exc:
        problems.append(f"{path}: {exc}")
    if association is not None and value.get("association") != association:
        problems.append(f"{path}/association: table columns must be 'row'")


def _source(value, path, problems):
    if not _object(value, path, problems, required=("path",),
                   allowed={"path", "reader", "selector", "size", "sha256", "media_type"}):
        return
    _string(value.get("path"), f"{path}/path", problems, pattern=_REL_PATH)
    if "reader" in value:
        _string(value["reader"], f"{path}/reader", problems, pattern=_READER)
    if value.get("size") is not None and not _integer(value["size"], 0):
        problems.append(f"{path}/size: must be an integer >= 0 or null")
    if value.get("sha256") is not None:
        _string(value["sha256"], f"{path}/sha256", problems, pattern=_SHA256)
    if "selector" in value and not isinstance(value["selector"], (str, dict, type(None))):
        problems.append(f"{path}/selector: must be a string, an object or null")


def _frame(value, path, problems):
    if not _object(value, path, problems, required=("sources",), allowed={"step", "time", "index", "sources"}):
        return
    if value.get("step") is not None and not _integer(value["step"], 0):
        problems.append(f"{path}/step: must be an integer >= 0 or null")
    if value.get("time") is not None and not _number(value["time"]):
        problems.append(f"{path}/time: must be a number or null")
    if "index" in value and not _integer(value["index"], 0):
        problems.append(f"{path}/index: must be an integer >= 0")
    if _object(value.get("sources"), f"{path}/sources", problems):
        for name, source in value["sources"].items():
            _source(source, f"{path}/sources/{name}", problems)


def _provenance(value, path, problems):
    if not _object(value, path, problems, allowed={"activity", "agent", "used", "derived_from", "generated_at"}):
        return
    if "activity" in value and _object(value["activity"], f"{path}/activity", problems, allowed={"kind", "id"}):
        if value["activity"].get("kind") not in (None, "run", "graph", "import", "convert"):
            problems.append(f"{path}/activity/kind: must be run, graph, import or convert")
    if "agent" in value:
        _object(value["agent"], f"{path}/agent", problems, allowed={"connector", "reader", "node", "stk"})
    for i, item in enumerate(value.get("used") or ()):
        if _object(item, f"{path}/used/{i}", problems, required=("path",), allowed={"path", "sha256", "role"}):
            if item.get("sha256") is not None:
                _string(item["sha256"], f"{path}/used/{i}/sha256", problems, pattern=_SHA256)


def validate_dataset(document, path=""):
    """Problems of an stk.dataset/1 descriptor (empty list = valid)."""
    problems = []
    allowed = {"schema", "id", "label", "kind", "geometry", "fields", "columns", "time", "frames", "provenance",
               "attrs", "extensions"}
    if not _object(document, path, problems, required=("id", "kind"), allowed=allowed):
        return problems
    if document.get("schema", "stk.dataset/1") != "stk.dataset/1":
        problems.append(f"{path}/schema: must be 'stk.dataset/1'")
    _string(document.get("id"), f"{path}/id", problems, pattern=_ID)
    kind = document.get("kind")
    if kind not in KINDS:
        problems.append(f"{path}/kind: must be one of {', '.join(KINDS)}")
    geometry = document.get("geometry")
    if kind == "image" and geometry is None:
        problems.append(f"{path}/geometry: is required for images")
    if geometry is not None and _object(geometry, f"{path}/geometry", problems, allowed=_GEOMETRY_KEYS.get(kind)):
        if kind == "image":
            for key in ("dimensions", "origin", "spacing"):
                if key not in geometry:
                    problems.append(f"{path}/geometry/{key}: is required")
            if "dimensions" in geometry:
                _vector(geometry["dimensions"], f"{path}/geometry/dimensions", problems, 3, integers=True, minimum=1)
            if "origin" in geometry:
                _vector(geometry["origin"], f"{path}/geometry/origin", problems, 3)
            if "spacing" in geometry:
                _vector(geometry["spacing"], f"{path}/geometry/spacing", problems, 3, positive=True)
            if "direction" in geometry:
                _vector(geometry["direction"], f"{path}/geometry/direction", problems, 9)
        elif kind == "polydata":
            for key in ("points", "verts", "lines", "polys"):
                if key in geometry and not _integer(geometry[key], 0):
                    problems.append(f"{path}/geometry/{key}: must be an integer >= 0")
        elif kind == "table" and geometry.get("rows") is not None and not _integer(geometry["rows"], 0):
            problems.append(f"{path}/geometry/rows: must be an integer >= 0 or null")
    if kind == "table" and document.get("fields"):
        problems.append(f"{path}/fields: tables use 'columns'")
    for key in ("fields", "columns"):
        if key in document:
            if not isinstance(document[key], list):
                problems.append(f"{path}/{key}: must be a list")
                continue
            names = set()
            for i, entry in enumerate(document[key]):
                _field(entry, f"{path}/{key}/{i}", problems, "row" if key == "columns" else None)
                name = entry.get("name") if isinstance(entry, dict) else None
                if name in names:
                    problems.append(f"{path}/{key}/{i}/name: duplicate name {name!r}")
                names.add(name)
    if "time" in document and _object(document["time"], f"{path}/time", problems,
                                      allowed={"index", "step", "value", "physical"}):
        time = document["time"]
        if time.get("index") not in (None, "step", "time"):
            problems.append(f"{path}/time/index: must be 'step', 'time' or null")
        if time.get("step") is not None and not _integer(time["step"], 0):
            problems.append(f"{path}/time/step: must be an integer >= 0 or null")
        if time.get("value") is not None and not _number(time["value"]):
            problems.append(f"{path}/time/value: must be a number or null")
        if "physical" in time:
            _object(time["physical"], f"{path}/time/physical", problems, allowed={"unit", "known"})
    if "frames" in document:
        if not isinstance(document["frames"], list):
            problems.append(f"{path}/frames: must be a list")
        else:
            for i, frame in enumerate(document["frames"]):
                _frame(frame, f"{path}/frames/{i}", problems)
    if "provenance" in document:
        _provenance(document["provenance"], f"{path}/provenance", problems)
    for key in ("attrs", "extensions"):
        if key in document and not isinstance(document[key], dict):
            problems.append(f"{path}/{key}: must be an object")
    return problems


# ---------------------------------------------------------------------------
# stk.series/1


def series_manifest(frames, *, parameter="step", **extra):
    """An stk.series/1 document: ``frames`` = ``[{"step", "time"?, "outputs"?, "path"?, "sha256"?, "size"?}]``
    sorted by step. ``extra`` keys (``dataset``, ``geometry``, ``producer``, ``generated_at``, ...) are kept."""
    document = {"schema": "stk.series/1", "parameter": parameter,
                "frames": sorted((dict(f) for f in frames), key=lambda f: (f.get("step") is None, f.get("step")))}
    document.update(extra)
    return document


def validate_series(document, path=""):
    problems = []
    allowed = {"schema", "parameter", "frames", "dataset", "geometry", "producer", "generated_at", "graph_sha256",
               "extensions"}
    if not _object(document, path, problems, required=("schema", "parameter", "frames"), allowed=allowed):
        return problems
    if document.get("schema") != "stk.series/1":
        problems.append(f"{path}/schema: must be 'stk.series/1'")
    _string(document.get("parameter"), f"{path}/parameter", problems)
    frames = document.get("frames")
    if not isinstance(frames, list):
        problems.append(f"{path}/frames: must be a list")
        return problems
    steps = []
    for i, frame in enumerate(frames):
        where = f"{path}/frames/{i}"
        if not _object(frame, where, problems, required=("step",),
                       allowed={"step", "time", "outputs", "path", "sha256", "size", "media_type"}):
            continue
        if not _integer(frame.get("step"), 0):
            problems.append(f"{where}/step: must be an integer >= 0")
        steps.append(frame.get("step"))
        if frame.get("time") is not None and not _number(frame["time"]):
            problems.append(f"{where}/time: must be a number or null")
        if "path" in frame:
            _string(frame["path"], f"{where}/path", problems, pattern=_REL_PATH)
        if frame.get("sha256") is not None:
            _string(frame["sha256"], f"{where}/sha256", problems, pattern=_SHA256)
        if "outputs" in frame and _object(frame["outputs"], f"{where}/outputs", problems):
            for name, output in frame["outputs"].items():
                if isinstance(output, str):
                    _string(output, f"{where}/outputs/{name}", problems, pattern=_REL_PATH)
                elif _object(output, f"{where}/outputs/{name}", problems, required=("path",),
                             allowed={"path", "sha256", "size", "media_type"}):
                    _string(output["path"], f"{where}/outputs/{name}/path", problems, pattern=_REL_PATH)
    if len(set(steps)) != len(steps):
        problems.append(f"{path}/frames: steps must be unique")
    return problems


# ---------------------------------------------------------------------------
# stk.result/1


def file_entry(path, *, size=None, sha256=None, media_type=None, role="output"):
    """One ``files[]`` entry of stk.result/1."""
    entry = {"path": path, "sha256": sha256, "size": size, "role": role}
    if media_type is not None:
        entry["media_type"] = media_type
    return entry


def qoi_entry(name, value, unit, *, quantity=None, step=None, time=None, source=None, definition=None):
    """One ``qoi[]`` entry; non-finite values become ``"NaN"``/``"Inf"``/``"-Inf"``."""
    if isinstance(value, float) and not math.isfinite(value):
        value = "NaN" if math.isnan(value) else ("Inf" if value > 0 else "-Inf")
    entry = {"name": name, "value": value, "unit": unit, "quantity": quantity, "step": step, "time": time}
    if source is not None:
        entry["source"] = dict(source)
    if definition is not None:
        entry["definition"] = definition
    return entry


def result_manifest(*, connector, app, connector_version=None, stk=None, state="unknown", complete=False,
                    datasets=(), files=(), qoi=(), verification=None, run=None, outcome=None,
                    scientific_status=None, frames_of_reference=None, native=(), extensions=None, generated_at=None):
    """An stk.result/1 document. ``app`` is ``{"id", ...}`` or an app id; ``run`` adds runtime/case/layout keys."""
    app = {"id": app} if isinstance(app, str) else dict(app)
    document = {
        "schema": "stk.result/1",
        "producer": {"connector": connector, "connector_version": connector_version, "stk": stk,
                     "generated_at": generated_at or now()},
        "complete": bool(complete),
        "run": {"app": app, **(run or {})},
        "state": state,
        "outcome": dict(outcome or {"classification": None, "retryable": False, "reason": ""}),
        "verification": verification,
        "frames_of_reference": dict(frames_of_reference or {"grid": {"length_unit": "grid_index"}}),
        "qoi": list(qoi),
        "datasets": [dataset_manifest(d) for d in datasets],
        "files": list(files),
        "native": list(native),
    }
    if scientific_status is not None:
        document["scientific_status"] = scientific_status
    if extensions:
        document["extensions"] = dict(extensions)
    return document


def _nullable(value, path, problems, kind):
    if value is None:
        return
    ok = {"string": isinstance(value, str), "integer": _integer(value), "number": _number(value)}[kind]
    if not ok:
        problems.append(f"{path}: must be a {kind} or null")


def validate_result(document, path=""):
    """Problems of an stk.result/1 manifest (mirrors result-1.schema.json)."""
    problems = []
    allowed = {"schema", "producer", "complete", "run", "state", "outcome", "scientific_status", "verification",
               "frames_of_reference", "qoi", "datasets", "files", "native", "extensions"}
    if not _object(document, path, problems, required=("schema", "producer", "complete", "run", "state", "datasets"),
                   allowed=allowed):
        return problems
    if document.get("schema") != "stk.result/1":
        problems.append(f"{path}/schema: must be 'stk.result/1'")
    producer = document.get("producer")
    if producer is not None and _object(producer, f"{path}/producer", problems, required=("connector",),
                                        allowed={"connector", "connector_version", "stk", "generated_at"}):
        _string(producer.get("connector"), f"{path}/producer/connector", problems)
        for key in ("connector_version", "stk", "generated_at"):
            _nullable(producer.get(key), f"{path}/producer/{key}", problems, "string")
    if "complete" in document and not isinstance(document["complete"], bool):
        problems.append(f"{path}/complete: must be a boolean")
    run = document.get("run")
    if run is not None and _object(run, f"{path}/run", problems,
                                   allowed={"app", "runtime", "case", "layout", "started_at", "finished_at",
                                            "exit_code"}):
        if "app" in run and _object(run["app"], f"{path}/run/app", problems, required=("id",),
                                    allowed={"id", "name", "version", "executable_sha256"}):
            _string(run["app"].get("id"), f"{path}/run/app/id", problems)
        for key, keys in (("runtime", {"node_id", "task_id", "workspace_id"}), ("case", {"case_id", "dir", "manifest"}),
                          ("layout", {"ranks", "threads_per_rank", "launcher"})):
            if key in run and _object(run[key], f"{path}/run/{key}", problems, allowed=keys):
                for name, value in run[key].items():
                    kind = "integer" if name in ("ranks", "threads_per_rank") else "string"
                    _nullable(value, f"{path}/run/{key}/{name}", problems, kind)
                    if kind == "integer" and value is not None and _integer(value) and value < 1:
                        problems.append(f"{path}/run/{key}/{name}: must be >= 1")
        for key in ("started_at", "finished_at"):
            _nullable(run.get(key), f"{path}/run/{key}", problems, "string")
        _nullable(run.get("exit_code"), f"{path}/run/exit_code", problems, "integer")
    if document.get("state") not in RESULT_STATES:
        problems.append(f"{path}/state: must be one of {', '.join(RESULT_STATES)}")
    outcome = document.get("outcome")
    if outcome is not None and _object(outcome, f"{path}/outcome", problems,
                                       allowed={"classification", "retryable", "reason"}):
        _nullable(outcome.get("classification"), f"{path}/outcome/classification", problems, "string")
        if "retryable" in outcome and not isinstance(outcome["retryable"], bool):
            problems.append(f"{path}/outcome/retryable: must be a boolean")
        if "reason" in outcome and not isinstance(outcome["reason"], str):
            problems.append(f"{path}/outcome/reason: must be a string")
    if "scientific_status" in document and not isinstance(document["scientific_status"], str):
        problems.append(f"{path}/scientific_status: must be a string")
    verification = document.get("verification")
    if verification is not None and _object(verification, f"{path}/verification", problems,
                                            required=("verifier", "status"),
                                            allowed={"verifier", "status", "checks"}):
        if verification.get("status") not in VERIFICATION_STATUSES:
            problems.append(f"{path}/verification/status: must be one of {', '.join(VERIFICATION_STATUSES)}")
        for i, item in enumerate(verification.get("checks") or ()):
            where = f"{path}/verification/checks/{i}"
            if _object(item, where, problems, required=("id", "status"),
                       allowed={"id", "status", "message", "classification"}):
                if item.get("status") not in CHECK_STATUSES:
                    problems.append(f"{where}/status: must be one of {', '.join(CHECK_STATUSES)}")
    frames = document.get("frames_of_reference")
    if frames is not None and _object(frames, f"{path}/frames_of_reference", problems):
        for name, frame in frames.items():
            where = f"{path}/frames_of_reference/{name}"
            if _object(frame, where, problems, required=("length_unit",),
                       allowed={"length_unit", "parent", "transform", "description"}):
                transform = frame.get("transform")
                if transform is not None and (not isinstance(transform, list) or len(transform) != 4 or not all(
                        isinstance(row, list) and len(row) == 4 and all(_number(v) for v in row) for row in transform)):
                    problems.append(f"{where}/transform: must be a 4x4 list of numbers")
    for i, item in enumerate(document.get("qoi") or ()):
        where = f"{path}/qoi/{i}"
        if _object(item, where, problems, required=("name", "value", "unit"),
                   allowed={"name", "value", "unit", "quantity", "step", "time", "source", "definition"}):
            value = item.get("value")
            if value is not None and not _number(value) and value not in ("NaN", "Inf", "-Inf"):
                problems.append(f"{where}/value: must be a number, 'NaN', 'Inf', '-Inf' or null")
            _nullable(item.get("step"), f"{where}/step", problems, "integer")
            _nullable(item.get("time"), f"{where}/time", problems, "number")
            if "source" in item:
                _object(item["source"], f"{where}/source", problems, allowed={"dataset", "column", "field", "path"})
    datasets = document.get("datasets")
    if not isinstance(datasets, list):
        problems.append(f"{path}/datasets: must be a list")
    else:
        ids = set()
        for i, dataset in enumerate(datasets):
            problems += validate_dataset(dataset, f"{path}/datasets/{i}")
            if isinstance(dataset, dict):
                if dataset.get("id") in ids:
                    problems.append(f"{path}/datasets/{i}/id: duplicate dataset id {dataset.get('id')!r}")
                ids.add(dataset.get("id"))
    for i, item in enumerate(document.get("files") or ()):
        where = f"{path}/files/{i}"
        if _object(item, where, problems, required=("path",), allowed={"path", "sha256", "size", "media_type", "role"}):
            _string(item.get("path"), f"{where}/path", problems, pattern=_REL_PATH)
            if item.get("sha256") is not None:
                _string(item["sha256"], f"{where}/sha256", problems, pattern=_SHA256)
            if item.get("size") is not None and not _integer(item["size"], 0):
                problems.append(f"{where}/size: must be an integer >= 0 or null")
            if "role" in item and item["role"] not in FILE_ROLES:
                problems.append(f"{where}/role: must be one of {', '.join(FILE_ROLES)}")
    for i, item in enumerate(document.get("native") or ()):
        if _object(item, f"{path}/native/{i}", problems, required=("path",), allowed={"path", "schema"}):
            _string(item.get("path"), f"{path}/native/{i}/path", problems)
    if "extensions" in document and not isinstance(document["extensions"], dict):
        problems.append(f"{path}/extensions: must be an object")
    return problems


def validate(document):
    """Problems of a manifest, by its ``schema`` tag (dataset, series or result)."""
    schema = document.get("schema") if isinstance(document, dict) else None
    if schema == "stk.result/1":
        return validate_result(document)
    if schema == "stk.series/1":
        return validate_series(document)
    if schema in ("stk.dataset/1", None) and isinstance(document, dict) and "kind" in document:
        return validate_dataset(document)
    return [f"/schema: unknown manifest {schema!r} (expected stk.dataset/1, stk.series/1 or stk.result/1)"]


def check(document):
    """Raise :class:`ManifestError` unless the manifest is valid; return it otherwise."""
    problems = validate(document)
    if problems:
        raise ManifestError(problems)
    return document
