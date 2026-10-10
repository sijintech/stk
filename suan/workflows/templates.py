"""Explicitly registered, versioned workflow templates. Project data never imports code.

A **remote** template (a simulation engine run on a Runtime per row, docs/design/multiscale-engines.md) provides:

- ``id``, ``name``, ``table_id`` (the case table its rows come from, or None), ``remote = True``;
- ``field_ids``: the row's fields a run freezes (a change of any of them makes the row stale);
- ``describe(model, record_id, connection, options)`` -> {record_id, label, values} (batches) and
  ``describe_values(model, record_id, connection, options)`` -> the frozen values (per-row workflow runs);
- ``prepare(stk, project, record_id, connection, options, revision, identity=None)`` -> the prepared project run;
- ``collect(stk, project, run_id)`` -> {record_id (its results-table row), files: [{path}], ...};
- ``results_prefix(run_id)``: the project folder ``collect`` writes to; ``final_state(names)``: the files passed on;
- ``validate_run(plan, entry, intent)`` (batches adopting a saved run).

Engines outside STK register templates through the ``stk.engines`` entry-point group (an instance or a class);
built-in identities cannot be replaced. Loading problems are reported by ``engine_diagnostics()``.
"""
import math
import threading

from . import muferro
from suan.runtime.models import TaskSpec
from suan.mupro.spec import muferro_spec


class MuFerroTemplate:
    id = "muferro/1"
    table_id = muferro.TABLE_ID
    name = "MuFerro"
    remote = True  # workflow runs execute it on a Runtime connection frozen in the run (W5)
    field_ids = tuple(muferro.FIELD_IDS.values())  # a MuFerro step takes every case field of its row

    def describe(self, model, record_id, connection, options):
        values, _, label = muferro.describe_case(model, record_id, connection, options)
        return {"record_id": record_id, "label": label, "values": values}

    def describe_values(self, model, record_id, connection, options):
        return muferro.describe_case(model, record_id, connection, options)[0]

    def prepare(self, stk, project, record_id, connection, options, revision, identity=None):
        extra = {"identity": identity} if identity is not None else {}
        return stk.muferro.prepare(record_id, connection, expected_revision=revision, project=project, **extra, **options)

    def collect(self, stk, project, run_id):
        return stk.muferro.collect(run_id, project=project)

    @staticmethod
    def results_prefix(run_id):
        return f"results/muferro/{run_id}/"

    @staticmethod
    def final_state(names):
        return muferro.final_state(names)

    def validate_run(self, plan, entry, intent):
        parameters = plan["parameters"]
        frozen = {"project": {"id": plan["project_id"]}, "tables": [{"id": self.table_id,
            "fields": parameters["fields"], "records": [{"id": parameters["record_id"],
            "values": parameters["values"], "definitions": parameters["definitions"]}]}]}
        described = self.describe(frozen, entry["record_id"], intent["connection"], intent["options"])
        expected = TaskSpec(**muferro_spec("0" * 32, case_dir="case", name="MuFerro", **intent["options"])).to_dict()
        ignored = {"workspace_id", "inputs", "input_hashes", "outputs"}
        if (described != entry or
                {k: v for k, v in expected.items() if k not in ignored} !=
                {k: v for k, v in plan["spec"].items() if k not in ignored}):
            raise ValueError("Saved run parameters or command do not match the batch template")


BUILTIN_TEMPLATES = {MuFerroTemplate.id: MuFerroTemplate()}
TEMPLATES = dict(BUILTIN_TEMPLATES)  # remote (batch-capable) templates, plus engines registered through entry points


class DemoSyntheticTemplate:
    """The example project's synthetic solver as a local workflow step (no Runtime, not physics).

    Workflow runs execute it on this computer for each row: ``temperature`` (K) scales a smooth 3D
    field written as ``field.vtk`` plus ``metrics.json``. Batches cannot prepare it, so it is not in
    TEMPLATES (``stk.batches.templates()``)."""
    id = "demo-synthetic/1"
    name = "Synthetic demo solver"
    table_id = None  # rows of any parameter table
    local = True
    parameters = [{"name": "temperature", "type": "number", "unit": "K", "label": "Temperature", "default": 300}]
    outputs = ["field.vtk", "metrics.json"]

    def run(self, parameters, directory):
        from .demo import synthetic_field
        temperature = parameters.get("temperature")
        if type(temperature) not in (int, float) or not math.isfinite(temperature) or not 0 < temperature <= 1e6:
            raise ValueError("The synthetic solver needs a finite positive temperature in K")
        return synthetic_field(temperature, directory)


LOCAL_TEMPLATES = {DemoSyntheticTemplate.id: DemoSyntheticTemplate()}
ENTRY_POINT_GROUP = "stk.engines"
_REMOTE_PROTOCOL = ("id", "name", "table_id", "field_ids", "describe", "describe_values", "prepare", "collect",
                    "results_prefix", "final_state")
_loaded = False
_problems = []
_lock = threading.Lock()


def _load_entry_points():
    """Add the templates of installed engine packages once (built-in identities win; problems are recorded)."""
    global _loaded
    with _lock:
        if _loaded:
            return
        try:
            _load_locked()
        finally:
            _loaded = True


def _load_locked():
    from importlib.metadata import entry_points
    try:
        found = entry_points(group=ENTRY_POINT_GROUP)
    except Exception as exc:  # noqa: BLE001 - a broken environment must not break workflows
        _problems.append({"entry_point": "*", "error": str(exc)[:500]})
        return
    for point in found:
        try:
            value = point.load()
            instance = value() if isinstance(value, type) else value
            missing = [name for name in _REMOTE_PROTOCOL if not hasattr(instance, name)] if getattr(instance, "remote", False) \
                else [name for name in ("id", "name", "run", "parameters", "outputs") if not hasattr(instance, name)]
            if missing:
                raise TypeError("missing " + ", ".join(missing))
            if not isinstance(instance.id, str) or instance.id in TEMPLATES or instance.id in LOCAL_TEMPLATES:
                raise ValueError(f"{instance.id} is already registered")
            (TEMPLATES if getattr(instance, "remote", False) else LOCAL_TEMPLATES)[instance.id] = instance
        except Exception as exc:  # noqa: BLE001 - reported, the rest still load
            _problems.append({"entry_point": point.name, "error": f"{type(exc).__name__}: {exc}"[:500]})


def engine_diagnostics():
    """Problems met while loading engine templates from entry points."""
    _load_entry_points()
    return list(_problems)


def workflow_templates():
    """Every template a workflow step can name: batch templates and local ones."""
    _load_entry_points()
    return {**TEMPLATES, **LOCAL_TEMPLATES}


def remote_templates():
    """The batch-capable (remote) templates: built-in engines and those registered through entry points."""
    _load_entry_points()
    return dict(TEMPLATES)


def template(identity):
    _load_entry_points()
    if identity not in TEMPLATES:
        raise ValueError("Unknown workflow template version")
    return TEMPLATES[identity]
