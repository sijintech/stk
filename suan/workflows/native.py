"""Fixed desktop simulation actions, with JSON data and built-in engine identities.

This is a button dispatcher, not a plugin loader or an agent tool. Preparation and
collection never submit tasks; only the explicitly named batch run/submit actions do.
The historical ``muferro.native_action`` remains available to existing callers.
"""
import json

from . import batches, lammps, muferro
from .common import _table


_ENGINES = {"muferro/1": muferro, "lammps/1": lammps}
_PARAMETERS = {
    "import": ({"source"}, {"script", "table_id"}),
    "clone": ({"record_id"}, {"table_id"}),
    "prepare": ({"record_id", "connection"}, {"options", "identity", "table_id"}),
    "collect": ({"run_id"}, {"max_bytes"}),
    "view": ({"run_id"}, set()),
    "logs": ({"run_id"}, set()),
    "batch_create": ({"record_ids", "connection"}, {"template_id", "options"}),
    "batch_run": ({"record_ids", "connection"}, {"template_id", "options"}),
    **{f"batch_{operation}": ({"batch_id"}, {"record_ids"})
       for operation in ("prepare", "submit", "refresh", "cancel", "collect")},
}


def _run(project, model, module, run_id):
    """Reject another engine's saved run before refresh, download or log access."""
    run = project.runs.get(run_id)
    plan = run["plan"]
    argv = plan.get("spec", {}).get("argv", [])
    runner = "suan.lammps" if module is lammps else "suan.mupro"
    if (plan.get("project_id") != model["project"]["id"]
            or plan.get("parameters", {}).get("table_id") != module.TABLE_ID
            or not isinstance(plan.get("label"), str) or not plan["label"].startswith(module.LABEL)
            or argv[:4] != ["{python}", "-m", runner, "run"]
            or "--case-dir" not in argv or argv[argv.index("--case-dir") + 1:][:1] != ["case"]):
        raise ValueError(f"Select a run prepared by the {module.NAME if module is lammps else 'MuFerro'} project workflow")
    return run


def _batch(model, engine, batch_id):
    """Check the selected engine before the existing batch helper reads its template."""
    table = _table(model, batches.TABLE_ID, batches.FIELDS, batches.FIELD_IDS, "Batch")
    row = next((row for row in table["records"] if row["id"] == batch_id), None) if table else None
    intent = row["values"].get(batches.FIELD_IDS["intent"]) if row else None
    if not isinstance(intent, dict) or intent.get("template") != engine:
        raise ValueError("Select a saved batch for this engine")
    batches._batch(model, batch_id)  # existing content-derived identity and project checks


def _options(options):
    if not isinstance(options, dict):
        raise ValueError("Execution options must be an object")
    if set(options) & {"project", "record_id", "connection", "expected_revision", "identity"}:
        raise ValueError("Execution options cannot override the selected project, row or revision")
    return dict(options)


def native_action(stk, engine, action, params):
    """Perform one explicit desktop action pinned to a project and observed revision.

    ``engine`` is exactly ``muferro/1`` or ``lammps/1``. Every action, including
    view/logs/collect, supplies ``project_id`` and ``expected_revision``. LAMMPS
    import can also specify ``script`` when several input scripts exist.
    """
    if not isinstance(engine, str) or engine not in _ENGINES:
        raise ValueError("Unknown built-in simulation engine")
    if not isinstance(action, str) or action not in _PARAMETERS:
        raise ValueError("Unknown simulation workflow action")
    if not isinstance(params, dict):
        raise ValueError("Simulation action parameters must be an object")
    params = dict(params)
    required, optional = _PARAMETERS[action]
    required = required | {"project_id", "expected_revision"}
    if not required <= params.keys() or params.keys() - required - optional:
        raise ValueError("Missing or unknown simulation action parameters")
    module = _ENGINES[engine]
    project_id, expected = params.pop("project_id"), params.pop("expected_revision")
    p = stk.project
    model = p.snapshot()
    if model["project"]["id"] != project_id:
        raise ValueError("The selected project changed; inspect the current project before continuing")
    if type(expected) is not int or model["project"]["revision"] != expected:
        raise ValueError("Project changed; refresh it and inspect the current parameters before continuing")
    if "table_id" in params and params.pop("table_id") != module.TABLE_ID:
        raise ValueError("Select a case table for this engine")
    service = stk.lammps if module is lammps else stk.muferro
    if action == "import":
        if module is muferro and "script" in params:
            raise ValueError("MuFerro import does not take a LAMMPS input script")
        return service.import_case(project=p, expected_revision=expected, **params)
    if action == "clone":
        return service.clone_case(project=p, expected_revision=expected, **params)
    if action == "prepare":
        options = _options(params.pop("options", {}))
        return service.prepare(project=p, expected_revision=expected, **params, **options)
    if action.startswith("batch_"):
        operation = action.removeprefix("batch_")
        if operation in {"create", "run"}:
            if params.pop("template_id", engine) != engine:
                raise ValueError("Batch template does not match the selected engine")
            params["template_id"] = engine
            if "options" in params:
                params["options"] = _options(params["options"])
        else:
            _batch(model, engine, params["batch_id"])
        return batches.native_action(stk, operation, {**params, "expected_revision": expected}, project=p)
    _run(p, model, module, params["run_id"])
    if action == "collect":
        return service.collect(project=p, **params)
    if action == "view":
        result = service.view(project=p, **params)
        if module is lammps:
            summary = {key: value for key, value in result.items() if key != "files"}
            summary["file_count"] = len(result["files"])
            print("LAMMPS collected results:", json.dumps(summary, ensure_ascii=False, allow_nan=False), flush=True)
        return result
    run = p.runs.refresh(params["run_id"])
    task = run["status"].get("task")
    if not task:
        raise ValueError("This run has not been accepted by the Runtime")
    runtime = stk.runtime(run["plan"]["connection"], node=run["plan"]["node"])
    streams = {}
    for stream in ("stdout", "stderr"):
        data = runtime.tasks.logs(task["id"], stream=stream, limit=65536)["data"]
        streams[stream] = data.decode("utf-8", errors="replace")
        print(f"{module.NAME if module is lammps else 'MuFerro'} {run['id']} — {stream} (first 64 KiB)", flush=True)
        print(streams[stream], flush=True)
    return {"run_id": run["id"], "streams": streams}
