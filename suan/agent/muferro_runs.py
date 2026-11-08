"""Internal handler: freeze one MuFerro workflow run for a person to approve (CL-S2C-PREPARE-09).

``prepare_muferro_run(context, arguments)`` is the body of the agent's ``prepare_muferro_run`` step. Root
owns its registration, level, bridge route and desktop card; nothing here grants a permission.

* ``arguments`` are exactly ``{workflow_id, rows, expected_revision}``: 1-100 distinct canonical row UUIDs
  of the workflow's MuFerro case table (existing case rows as well as rows added by drafts) and a
  non-boolean integer revision. The model never chooses a host, connection or resources.
* Where it would run comes only from the trusted desktop service
  ``context.services["agent_run_target"](store, session_id)``, which returns the person's frozen
  ``{connection, connection_identity, options}``; there is no default and no fallback.
* The saved workflow (after expanding a composite one) must take its rows from exactly one table, the
  MuFerro case table; have at least one simulation step, all of them ``muferro/1``; and otherwise only
  saved-analysis steps. LAMMPS, PET, LaTeX, local templates and file steps are refused.
* The run ID is ``RunApprovals.run_identity(session, turn, call)``. Only
  ``store.workflow_runs.prepare`` is called, a local freeze: no ``MuFerro.prepare``, no Runtime upload,
  submission or start. Then ``RunApprovals.offer`` binds the run to its recorded ``tool_called`` event.
* Replaying the same call reuses the original run and offer. A run already saved under that ID is read
  and checked against the call's arguments and a MuFerro-only frozen plan, and keeps its frozen target:
  a later change of the desktop selection never re-freezes it. Another session or call cannot borrow it
  (its ID would differ, and ``offer`` checks the recorded call).

The result is a bounded summary; the full plan stays in the project for the desktop review. The run is
never listed among the session's objects (it is not an agent object kind).
"""
import json

from suan.project.store import ProjectError, RevisionConflict, _id

TEMPLATE = "muferro/1"
TARGET_SERVICE = "agent_run_target"
MAX_ROWS = 100
MAX_OPTIONS_BYTES = 4096


def _arguments(arguments):
    if type(arguments) is not dict or set(arguments) != {"workflow_id", "rows", "expected_revision"}:
        raise ProjectError("prepare_muferro_run takes exactly workflow_id, rows and expected_revision")
    _id(arguments["workflow_id"])
    rows = arguments["rows"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS or len(set(map(str, rows))) != len(rows):
        raise ProjectError(f"Choose 1 to {MAX_ROWS} distinct case rows")
    for row in rows:
        _id(row)
    revision = arguments["expected_revision"]
    if type(revision) is not int or revision < 0:
        raise ProjectError("expected_revision must be a nonnegative integer")
    return {"workflow_id": arguments["workflow_id"], "rows": list(rows), "expected_revision": revision}


def _target(context):
    service = context.services.get(TARGET_SERVICE)
    if service is None:
        raise ProjectError("No Runtime target was selected on the desktop for this session")
    target = service(context.store, context.session_id)
    if (type(target) is not dict or set(target) != {"connection", "connection_identity", "options"}
            or type(target["connection"]) is not str or not 1 <= len(target["connection"]) <= 256
            or type(target["connection_identity"]) is not str or not 1 <= len(target["connection_identity"]) <= 256
            or type(target["options"]) is not dict):
        raise ProjectError("The desktop Runtime target must be exactly {connection, connection_identity, options}")
    try:
        encoded = json.dumps(target["options"], allow_nan=False, sort_keys=True)
    except (TypeError, ValueError):
        raise ProjectError("The desktop Runtime options must be plain JSON") from None
    if len(encoded.encode("utf-8")) > MAX_OPTIONS_BYTES:
        raise ProjectError("The desktop Runtime options are too large")
    return {"connection": target["connection"], "connection_identity": target["connection_identity"],
            "options": json.loads(encoded)}


def _check_domain(store, workflow_id):
    """The saved (expanded) workflow is a MuFerro case run: one case table, MuFerro steps, saved analyses."""
    from suan.workflows import muferro
    saved = store.workflows.get(workflow_id)["workflow"]
    if saved["state"] != "readable":
        raise ProjectError("The workflow cannot be read")
    checked, composition = store.workflows._validated(saved["document"])
    if not checked["ok"]:
        raise ProjectError("The workflow has problems; fix them before preparing a run")
    steps = (composition["document"] if composition is not None else saved["document"])["steps"]
    tables = [step for step in steps if step["kind"] == "table"]
    if len(tables) != 1 or tables[0]["ref"].get("table") != muferro.TABLE_ID:
        raise ProjectError("A MuFerro run takes its rows from exactly one table: the MuFerro case table")
    simulations = [step for step in steps if step["kind"] == "simulation"]
    if not simulations or any(step["ref"].get("template") != TEMPLATE for step in simulations):
        raise ProjectError("Every simulation step of a MuFerro run must be muferro/1, and it needs at least one")
    others = sorted({step["kind"] for step in steps} - {"table", "simulation", "analysis"})
    if others:
        raise ProjectError(f"A MuFerro run only takes saved analysis steps besides MuFerro ({', '.join(others)} refused)")


def _check_frozen(plan, request):
    """A run already saved under this call's ID must be the MuFerro run this call asked for."""
    from suan.workflows import muferro
    if (plan["workflow_id"] != request["workflow_id"] or [row["id"] for row in plan["rows"]] != request["rows"]
            or plan["source_revision"] != request["expected_revision"]):
        raise RevisionConflict("The saved run differs from this preparation's arguments")
    simulation = plan.get("simulation")
    if (type(simulation) is not dict or set(simulation) != {"connection", "connection_identity", "options"}
            or plan["table_id"] != muferro.TABLE_ID):
        raise ProjectError("The saved run is not a MuFerro run with a frozen Runtime target")
    remote = [step for step in plan["steps"].values() if step.get("kind") == "simulation"]
    if any(step.get("kind") not in ("simulation", "analysis") for step in plan["steps"].values()):
        raise ProjectError("The saved MuFerro run contains a forbidden step kind")
    if not remote or any(step.get("template") != TEMPLATE or not step.get("remote") for step in remote):
        raise ProjectError("The saved run is not a MuFerro-only run")
    return simulation


def prepare_muferro_run(context, arguments):
    """Freeze (or find again) this call's MuFerro workflow run and offer it for a person's first start."""
    from suan.project.workflow_runs import WorkflowRunNotFound
    from .run_approvals import RunApprovals, run_identity
    request = _arguments(arguments)
    store = context.store
    run_id = run_identity(context.session_id, context.turn, context.call_id)
    try:
        existing = store.workflow_runs.get(run_id)
    except WorkflowRunNotFound:
        existing = None
    if existing is not None:
        simulation = _check_frozen(existing, request)
        run = existing
    else:
        _check_domain(store, request["workflow_id"])
        simulation = _target(context)
        run = store.workflow_runs.prepare(request["workflow_id"], request["rows"], run_id=run_id,
                                          expected_revision=request["expected_revision"], simulation=simulation)
        _check_frozen(run, request)
    item = RunApprovals(store).offer(context.session_id, turn=context.turn, call_id=context.call_id, run_id=run_id)
    return {"item": item,
            "run": {"run_id": run_id, "plan_sha256": item["plan_sha256"], "request_sha256": item["request_sha256"],
                    "workflow_id": run["workflow_id"], "workflow_name": run["workflow_name"][:200],
                    "rows": len(run["rows"]), "tasks": len(run["tasks"]), "status": run["status"],
                    "connection": simulation["connection"], "options": simulation["options"]},
            "note": "Prepared locally only; nothing was uploaded or submitted. A person must approve the start."}


__all__ = ["TARGET_SERVICE", "TEMPLATE", "prepare_muferro_run"]
