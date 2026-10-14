"""Explicit native PET study buttons, pinned to the visible project and revision."""
import json


_ARGS = {
    "create": ({"connection"}, {"recipe", "options", "name", "study_id", "wait_seconds"}),
    **{name: ({"study_id"}, set()) for name in ("get", "start", "cancel", "recover")},
}


def native_action(stk, action, params):
    if type(action) is not str or action not in _ARGS or type(params) is not dict:
        raise ValueError("Unknown PET study action or invalid parameters")
    required, optional = _ARGS[action]
    required = required | {"project_id", "expected_revision"}
    if not required <= params.keys() or params.keys() - required - optional:
        raise ValueError("Missing or unknown PET study action parameters")
    params = dict(params)
    project_id, revision = params.pop("project_id"), params.pop("expected_revision")
    from uuid import UUID
    if type(project_id) is not str or type(revision) is not int:
        raise ValueError("PET study actions require a project UUID and integer revision")
    try:
        UUID(project_id)
    except ValueError:
        raise ValueError("PET study actions require a project UUID") from None
    project = stk.project
    model = project.snapshot()
    if model["project"]["id"] != project_id or type(revision) is not int or model["project"]["revision"] != revision:
        raise ValueError("The PET study project changed; refresh and inspect it before continuing")
    service = stk.lammps.studies
    if action == "get":
        result = service.get(project=project, **params)
    else:
        result = getattr(service, action)(project=project, expected_revision=revision, **params)
    # The action above is a fixed whitelist; project text never selects Python modules.
    summary = {key: result[key] for key in ("study_id", "run_id", "status", "complete", "definition_changed")}
    summary["stages"] = {name: {key: value for key, value in stage.items() if key in ("run_id", "status", "counts", "error")}
                         for name, stage in result["stages"].items()}
    print("PET study:", json.dumps(summary, ensure_ascii=False, allow_nan=False), flush=True)
    return result
