"""Light half of the muFerro connector: case files <-> stk.case/1. Standard library (+ tomllib/tomli) only.

Public STK ships a *minimal* parameter schema for the keys STK itself reads
(``[system].simulation_grid``, ``timestep_start``, ``timestep_total``,
``[output].interval``, the ``material`` file). The full muFerro schema belongs
to MuPRO: when the SDK installs ``share/mupro/schemas/muferro-input-1.schema.json``
under ``MUPRO_SDK_PREFIX`` it is used instead. Solver defaults are shown in the
schema (``x-stk-default-source: "solver"``), never silently applied.
"""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from ..api import API_VERSION, ConnectorError

__all__ = ["MINIMAL_SCHEMA", "MuFerroInputs", "dump_toml"]

APP = "mupro.muferro"
SCHEMA_ID = "mupro.muferro/input@1"
SDK_SCHEMA = Path("share/mupro/schemas/muferro-input-1.schema.json")
MAX_INCLUDE_DEPTH = 16
OUTPUT_NAMES = ("energy_out.dat", "mupro_progress.jsonl", "mupro_completion.json")

MINIMAL_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:stk:schema:" + SCHEMA_ID,
    "title": "muFerro input (minimal public subset)",
    "description": "Only the keys STK reads. The full parameter schema is installed with the MuPRO SDK.",
    "type": "object",
    "required": ["system", "output"],
    "properties": {
        "material": {"type": "string", "title": "Material file", "x-stk-widget": "file", "x-stk-group": "material"},
        "system": {
            "type": "object", "title": "System", "required": ["simulation_grid"],
            "properties": {
                "simulation_grid": {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 3,
                                    "maxItems": 3, "title": "Simulation grid (nx, ny, nz)", "x-stk-widget": "int3",
                                    "x-stk-unit": "grid_index", "x-stk-group": "system"},
                "timestep_start": {"type": "integer", "minimum": 0, "default": 0, "title": "First step",
                                   "x-stk-default-source": "solver", "x-stk-group": "system"},
                "timestep_total": {"type": "integer", "minimum": 1, "default": 1000, "title": "Steps",
                                   "x-stk-default-source": "solver", "x-stk-group": "system"},
            },
            "additionalProperties": True,
        },
        "output": {
            "type": "object", "title": "Output", "required": ["interval"],
            "properties": {"interval": {"type": "integer", "minimum": 1, "title": "Frame interval (steps)",
                                        "x-stk-group": "output"}},
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}


def _canonical(value):
    from suan.graph.schema import canonical_json
    return canonical_json(value)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Inf" if value > 0 else "-Inf")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)  # TOML dates and times


def _merge_under(destination, included):
    """The including file wins; sub-tables merge per key (MuPRO's include rule)."""
    for key, value in included.items():
        if key not in destination:
            destination[key] = value
        elif isinstance(destination[key], dict) and isinstance(value, dict):
            _merge_under(destination[key], value)


def _load(source, path, chain, files):
    if len(chain) > MAX_INCLUDE_DEPTH:
        raise ConnectorError(f"TOML includes are nested more than {MAX_INCLUDE_DEPTH} deep", "invalid_data")
    try:
        with source.open(path) as stream:
            raw = stream.read()
    except ConnectorError:
        raise ConnectorError(f"Case file not found: {path}", "missing_file") from None
    files.setdefault(path, _sha(raw))
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConnectorError(f"Cannot read {path}: {exc}", "invalid_data") from None
    includes = data.pop("include", [])
    includes = [includes] if isinstance(includes, str) else includes
    if not isinstance(includes, list) or not all(isinstance(i, str) and i for i in includes):
        raise ConnectorError(f"include in {path} requires a path or a list of paths", "invalid_data")
    for include in includes:
        from ..files import check_path
        if "\\" in include or include.startswith("/"):
            raise ConnectorError(f"TOML include {include!r} in {path} must be a relative POSIX path", "invalid_data")
        target = check_path(posixpath.normpath(posixpath.join(posixpath.dirname(path), include)))
        if target in chain:
            raise ConnectorError(f"Cyclic TOML include: {include}", "invalid_data")
        _merge_under(data, _load(source, target, chain + (target,), files))
    return data


class MuFerroInputs:
    """``suan.connectors.api.InputConnector`` for muFerro cases (TOML ``input.toml`` + includes + material)."""

    id = APP
    version = "0.1.0"
    api = API_VERSION

    def input_schema(self, app=APP, *, sdk_prefix=None):
        if app != APP:
            raise ConnectorError(f"This connector describes {APP}, not {app}", "unsupported")
        prefix = sdk_prefix or os.environ.get("MUPRO_SDK_PREFIX")
        if prefix and (Path(prefix) / SDK_SCHEMA).is_file():
            return json.loads((Path(prefix) / SDK_SCHEMA).read_text(encoding="utf-8"))
        return json.loads(json.dumps(MINIMAL_SCHEMA))

    def read_case(self, case, *, case_dir="."):
        """Native files of a case directory (a FileSource) -> stk.case/1."""
        base = "" if case_dir in (".", "", None) else case_dir.rstrip("/") + "/"
        files = {}
        entry = base + "input.toml"
        parameters = _load(case, entry, (entry,), files)
        material = parameters.get("material")
        if isinstance(material, str) and material:
            from ..files import check_path
            path = check_path(str(PurePosixPath(entry).parent / material))
            try:
                with case.open(path) as stream:
                    files.setdefault(path, _sha(stream.read()))
            except ConnectorError:
                pass  # validate_case reports a missing material file
        schema = self.input_schema()
        native = [{"path": path, "sha256": digest, "generated": False} for path, digest in sorted(files.items())]
        grid = (parameters.get("system") or {}).get("simulation_grid")
        constraints = [{"rule": "ranks <= min(grid[0], grid[1])", "message": "MuPRO splits x/y slabs"}]
        return {
            "schema": "stk.case/1", "app": APP, "connector": {"id": self.id, "version": self.version},
            "parameters_schema": {"id": SCHEMA_ID, "sha256": _sha(_canonical(schema)),
                                  "source": "sdk" if schema.get("$id") != MINIMAL_SCHEMA["$id"] else "stk:minimal"},
            "parameters": _json_safe(parameters), "inputs": [],
            "native": {"format": "toml", "entry": entry, "files": native},
            "case_id": self.case_id(native),
            "resources": {"suggested": {"ranks": 1}, "constraints": constraints,
                          **({"max_ranks": min(grid[:2])} if isinstance(grid, list) and len(grid) == 3
                             and all(isinstance(n, int) for n in grid) else {})},
            "provenance": {"created_by": None, "derived_from": None},
        }

    @staticmethod
    def case_id(native_files, app=APP):
        """``"sha256:" + sha256(canonical({"app", "files": sorted [{path, sha256}]}))`` (STK's own formula)."""
        files = sorted(({"path": f["path"], "sha256": f["sha256"]} for f in native_files), key=lambda f: f["path"])
        return "sha256:" + _sha(_canonical({"app": app, "files": files}))

    def write_case(self, case, out_dir):
        """Write ``input.toml`` from ``case["parameters"]``; returns ``[{"path", "sha256", "generated": True}]``."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        parameters = case.get("parameters")
        if not isinstance(parameters, dict):
            raise ConnectorError("stk.case/1 needs a 'parameters' object", "invalid_param")
        text = dump_toml(parameters).encode("utf-8")
        (out_dir / "input.toml").write_bytes(text)
        return [{"path": "input.toml", "sha256": _sha(text), "generated": True}]

    def validate_case(self, case_dir):
        """Checks only (never runs anything): ``[{"id", "status": "pass|fail|warn", "message"}]``."""
        from suan.mupro.run import FRAME, MuproError, read_case
        case_dir = Path(case_dir)
        checks = []
        try:
            case = read_case(case_dir)
            checks.append({"id": "input", "status": "pass",
                           "message": f"grid {case['grid']}, {case['steps']} steps, "
                                      f"interval {case['output_interval']}"})
        except MuproError as exc:
            return [{"id": "input", "status": "fail", "message": str(exc)}]
        try:
            with open(case_dir / "input.toml", "rb") as stream:
                material = tomllib.load(stream).get("material")
        except (OSError, tomllib.TOMLDecodeError):
            material = None
        if isinstance(material, str) and material:
            ok = (case_dir / material).is_file()
            checks.append({"id": "material", "status": "pass" if ok else "fail",
                           "message": f"{material} {'found' if ok else 'is missing'}"})
        else:
            checks.append({"id": "material", "status": "warn", "message": "input.toml names no material file"})
        stale = sorted(p.name for p in case_dir.iterdir() if p.name in OUTPUT_NAMES or FRAME.search(p.name))
        checks.append({"id": "clean", "status": "warn" if stale else "pass",
                       "message": ("The case directory already holds muFerro outputs: " + ", ".join(stale[:5]))
                       if stale else "No muFerro outputs yet"})
        return checks

    def task_spec(self, case, resources, **opts):
        """Runtime TaskSpec keyword arguments (``suan.mupro.spec.muferro_spec``); ``workspace_id`` is required."""
        from suan.mupro.spec import muferro_spec
        opts = dict(opts)
        workspace_id = opts.pop("workspace_id", None)
        if not workspace_id:
            raise ConnectorError("task_spec needs workspace_id", "invalid_param")
        resources = dict(resources or {})
        ranks = int(resources.pop("ranks", 1))
        grid = ((case or {}).get("parameters", {}).get("system") or {}).get("simulation_grid")
        if isinstance(grid, list) and len(grid) == 3 and all(isinstance(n, int) for n in grid) \
                and ranks > min(grid[:2]):
            raise ConnectorError(f"ranks must be at most min(nx, ny) = {min(grid[:2])} for this grid",
                                 "invalid_param")
        allowed = {"threads_per_rank", "nodes", "walltime_seconds", "memory_mb", "queue", "account"}
        unknown = set(resources) - allowed
        if unknown:
            raise ConnectorError(f"Unknown resources: {', '.join(sorted(unknown))}", "invalid_param")
        try:
            return muferro_spec(workspace_id, ranks=ranks, **resources, **opts)
        except ValueError as exc:
            raise ConnectorError(str(exc), "invalid_param") from None


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_key(k)} = {_toml_value(v)}" for k, v in value.items()) + "}"
    raise ConnectorError(f"Cannot write {type(value).__name__} values to TOML", "invalid_param")


def _key(key):
    return key if key and all(c.isalnum() or c in "_-" for c in key) and key.isascii() else json.dumps(key)


def dump_toml(document, _prefix=()):
    """A small TOML writer for case parameters: scalars, arrays and (nested) tables."""
    scalars = [(k, v) for k, v in document.items() if not (isinstance(v, dict) and v)]
    tables = [(k, v) for k, v in document.items() if isinstance(v, dict) and v]
    lines = ["[" + ".".join(_key(k) for k in _prefix) + "]"] if _prefix else []
    lines += [f"{_key(k)} = {_toml_value(v)}" for k, v in scalars]
    blocks = ["\n".join(lines)] if lines else []
    blocks += [dump_toml(value, (*_prefix, key)).rstrip("\n") for key, value in tables]
    return "\n\n".join(block for block in blocks if block) + "\n"
