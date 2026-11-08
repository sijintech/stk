"""prepare_muferro_run: a local MuFerro freeze offered for a person's first start (CL-S2C-PREPARE-09).

Real SQLite, real MuFerro case rows imported from the synthetic fake SDK example through the in-process
bridge. Nothing contacts a Runtime, prepares MuFerro inputs, starts a run, runs a solver or calls a model:
those entry points are replaced by failures for every test.
"""
from uuid import uuid4

import pytest

from mupro_fake import make_fake_sdk
from suan.agent.muferro_runs import TARGET_SERVICE, prepare_muferro_run
from suan.agent.run_approvals import PREPARE_TOOL, RunApprovals, run_identity
from suan.agent.tools import ToolContext
from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.agent_sessions import HARNESS, digest
from suan.scripting import API
from suan.workflows import muferro
from test_bridge_workflow_muferro import energy_document
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

TARGET = {"connection": "runtime:lab", "connection_identity": "0123456789abcdef", "options": {"launcher": "none"}}


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    """Any Runtime client, MuFerro input preparation or run start fails the test."""
    from suan.project.workflow_runs import WorkflowRuns
    from suan.runtime.client import RuntimeClient

    def forbidden(*args, **kwargs):
        pytest.fail("preparation must not contact a Runtime, prepare MuFerro inputs or start a run")

    monkeypatch.setattr(RuntimeClient, "__init__", forbidden)
    monkeypatch.setattr(muferro.MuFerro, "prepare", forbidden)
    monkeypatch.setattr(WorkflowRuns, "start", forbidden)


@pytest.fixture
def cases(inproc, tmp_path, monkeypatch):
    """Two existing MuFerro case rows (imported and cloned, not agent drafts) and a cases -> MuFerro ->
    saved analysis workflow."""
    sdk = make_fake_sdk(tmp_path / "fake-sdk")
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(sdk))
    h = inproc()
    store = ProjectStore.create(tmp_path / "project", "MuFerro agent")
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    api = API(lambda operation, params: h.call(operation, params))
    api._project_handle = handle
    source = sdk / "share/mupro/skills/mupro-muferro/examples"
    first = api.muferro.import_case(source, expected_revision=store.info()["revision"])["record_id"]
    second = api.muferro.clone_case(first, expected_revision=store.info()["revision"])["record_id"]
    analysis, workflow = str(uuid4()), str(uuid4())
    store.analyses.create("Energy", energy_document(), analysis_id=analysis, expected_revision=store.info()["revision"])
    store.workflows.create("MuFerro scan", muferro_document(analysis), workflow_id=workflow,
                           expected_revision=store.info()["revision"])
    return {"store": store, "rows": [first, second], "workflow": workflow, "analysis": analysis}


def muferro_document(analysis, simulate=None, extra=()):
    steps = [{"id": "cases", "kind": "table", "ref": {"table": muferro.TABLE_ID}},
             {"id": "simulate", "kind": "simulation", "ref": {"template": "muferro/1"},
              "inputs": {"rows": {"from": "cases.rows"}}, **(simulate or {})},
             {"id": "energy", "kind": "analysis", "ref": {"analysis": analysis}, "inputs": {"run": {"from": "simulate.files"}}}]
    return {"format": "stk.workflow/1", "ui": {}, "steps": steps + list(extra)}


def session(store):
    sid = str(uuid4())
    definition = {"name": PREPARE_TOOL, "version": 1, "level": "prepare_run"}
    store.agent_sessions.create(sid, {"id": sid, "harness": HARNESS, "tools": [definition]},
                                "Prepare the MuFerro rows", turn_id=str(uuid4()), request_sha256=digest(sid))
    return sid


def call(store, arguments, *, sid=None, call_id="c1", target=TARGET, record=True):
    """Record the tool call as the executor would, then run the handler for it."""
    sid = sid or session(store)
    if record:
        store.agent_sessions.append(sid, "tool_called", {"call_id": call_id, "tool": PREPARE_TOOL, "version": 1,
                                    "level": "prepare_run", "arguments": arguments,
                                    "arguments_sha256": digest(arguments)}, turn=0)
    services = {} if target is None else {TARGET_SERVICE: target if callable(target) else (lambda s, i: dict(target))}
    context = ToolContext(store=store, session_id=sid, turn=0, call_id=call_id, services=services)
    return sid, context, prepare_muferro_run(context, arguments)


def arguments(c, rows=None, **changes):
    value = {"workflow_id": c["workflow"], "rows": rows or c["rows"], "expected_revision": c["store"].info()["revision"]}
    value.update(changes)
    return value


# --- the local freeze and its offer -------------------------------------------------------------------


def test_existing_case_rows_are_frozen_locally_and_offered(cases):
    store = cases["store"]
    before = store.info()["revision"]
    sid, context, result = call(store, arguments(cases))
    run_id = run_identity(sid, 0, "c1")
    assert run_id == context.object_id("workflow_run")
    run = store.workflow_runs.get(run_id)
    assert run["status"] == "prepared" and [row["id"] for row in run["rows"]] == cases["rows"]
    assert run["simulation"] == TARGET  # exactly the desktop selection, frozen
    assert store.info()["revision"] == before  # a local freeze: no edit, no snapshot, no upload
    item = result["item"]
    assert item["kind"] == "start_run" and item["run_id"] == run_id and item["plan_sha256"] == run["plan_sha256"]
    assert store.agent_sessions.get(sid)["awaiting"] == [item]
    summary = result["run"]
    assert summary == {"run_id": run_id, "plan_sha256": run["plan_sha256"], "request_sha256": item["request_sha256"],
                       "workflow_id": cases["workflow"], "workflow_name": "MuFerro scan", "rows": 2,
                       "tasks": len(run["tasks"]), "status": "prepared", "connection": "runtime:lab",
                       "options": {"launcher": "none"}}
    assert "document" not in summary and "steps" not in summary  # a bounded summary, not the plan
    assert [o for o in store.agent_sessions.objects(sid)] == []  # never an agent object kind


def test_replay_reuses_the_run_and_offer_even_if_the_desktop_target_changed(cases):
    store = cases["store"]
    args = arguments(cases)
    sid, context, first = call(store, args)
    chain = store.agent_sessions.get(sid)["chain_sha256"]
    changed = {**TARGET, "connection": "runtime:other", "options": {"launcher": "none", "ranks": 2}}
    replay = prepare_muferro_run(ToolContext(store=store, session_id=sid, turn=0, call_id="c1",
                                             services={TARGET_SERVICE: lambda s, i: dict(changed)}), args)
    assert replay["item"] == first["item"] and replay["run"]["connection"] == "runtime:lab"
    assert store.agent_sessions.get(sid)["chain_sha256"] == chain  # no second offer
    assert store.workflow_runs.list()["runs"][0]["id"] == first["run"]["run_id"]
    assert len(store.workflow_runs.list()["runs"]) == 1
    # a replay needs no target service at all
    again = prepare_muferro_run(ToolContext(store=store, session_id=sid, turn=0, call_id="c1"), args)
    assert again["item"] == first["item"]


def test_replay_with_different_arguments_is_a_conflict(cases):
    store = cases["store"]
    sid, context, first = call(store, arguments(cases))
    with pytest.raises(RevisionConflict, match="differs"):
        prepare_muferro_run(context, arguments(cases, rows=[cases["rows"][1]]))


def test_another_session_or_call_cannot_borrow_the_run(cases):
    store = cases["store"]
    args = arguments(cases)
    sid, _, first = call(store, args)
    other_sid, _, other = call(store, args)  # an independent session prepares its own run
    assert other["run"]["run_id"] != first["run"]["run_id"]
    with pytest.raises(ProjectError):  # an unrecorded call of the first session
        prepare_muferro_run(ToolContext(store=store, session_id=sid, turn=0, call_id="c2",
                                        services={TARGET_SERVICE: lambda s, i: dict(TARGET)}), args)


def test_one_row_of_an_existing_case_is_enough(cases):
    store = cases["store"]
    _, _, result = call(store, arguments(cases, rows=[cases["rows"][1]]))
    assert result["run"]["rows"] == 1


# --- refusals: target, arguments, revision, domain --------------------------------------------------------


def test_missing_or_malformed_desktop_target_freezes_nothing(cases):
    store = cases["store"]
    for target in (None, {"connection": "runtime:lab", "options": {}},
                   {**TARGET, "options": "launcher=none"}, {**TARGET, "extra": 1}, {**TARGET, "connection": ""}):
        with pytest.raises(ProjectError, match="target"):
            call(store, arguments(cases), target=target)
    assert store.workflow_runs.list()["runs"] == []


def test_the_model_cannot_supply_a_host_or_resources(cases):
    store = cases["store"]
    for extra in ({"connection": "runtime:evil"}, {"options": {"ranks": 512}}, {"simulation": TARGET}):
        with pytest.raises(ProjectError, match="exactly"):
            call(store, {**arguments(cases), **extra})
    assert store.workflow_runs.list()["runs"] == []


@pytest.mark.parametrize("change", [
    {"rows": []}, {"rows": "all"}, {"rows": ["not-a-uuid"]}, {"expected_revision": True},
    {"expected_revision": -1}, {"expected_revision": 1.0}, {"workflow_id": "nope"}])
def test_invalid_arguments_freeze_nothing(cases, change):
    store = cases["store"]
    with pytest.raises(ProjectError):
        call(store, {**arguments(cases), **change})
    assert store.workflow_runs.list()["runs"] == []


def test_duplicate_too_many_or_foreign_rows_are_refused(cases):
    store = cases["store"]
    row = cases["rows"][0]
    for rows in ([row, row], [str(uuid4()) for _ in range(101)], [row, str(uuid4())]):
        with pytest.raises(ProjectError):
            call(store, arguments(cases, rows=rows))
    assert store.workflow_runs.list()["runs"] == []


def test_stale_revision_is_refused(cases):
    store = cases["store"]
    args = arguments(cases)
    store.apply([{"op": "set_cell", "table_id": muferro.TABLE_ID, "record_id": cases["rows"][1],
                  "field_id": muferro.FIELD_IDS["temperature"], "value": 333}], expected_revision=store.info()["revision"])
    with pytest.raises(RevisionConflict):
        call(store, args)
    assert store.workflow_runs.list()["runs"] == []


def _replace_workflow(cases, document):
    store = cases["store"]
    store.workflows.update(cases["workflow"], "MuFerro scan", document, expected_revision=store.info()["revision"])


def _foreign_table(store):
    table, field = str(uuid4()), str(uuid4())
    store.apply([{"op": "create_table", "id": table, "name": "Other"},
                 {"op": "add_field", "id": field, "table_id": table, "name": "T", "type": "number", "unit": "K"}],
                expected_revision=store.info()["revision"])
    return table, field


@pytest.mark.parametrize("domain, message", [
    # valid workflows of another domain: refused by the MuFerro rule itself
    ("lammps", "MuFerro case table"),
    ("demo_on_other_table", "MuFerro case table"),
    ("local_template_beside_muferro", "must be muferro/1"),
    ("no_simulation", "must be muferro/1"),
    # mixed shapes the saved-workflow validation already reports as problems
    ("lammps_beside_muferro", "problems"),
    ("files_step", "problems"),
])
def test_non_muferro_workflows_are_refused(cases, domain, message):
    from suan.workflows import lammps
    store = cases["store"]
    analysis = cases["analysis"]
    if domain == "lammps":
        store.apply([{"op": "create_table", "id": lammps.TABLE_ID, "name": "LAMMPS cases"}],
                    expected_revision=store.info()["revision"])
        document = {"format": "stk.workflow/1", "ui": {}, "steps": [
            {"id": "cases", "kind": "table", "ref": {"table": lammps.TABLE_ID}},
            {"id": "md", "kind": "simulation", "ref": {"template": "lammps/1"}, "inputs": {"rows": {"from": "cases.rows"}}}]}
    elif domain == "demo_on_other_table":
        table, field = _foreign_table(store)
        document = {"format": "stk.workflow/1", "ui": {}, "steps": [
            {"id": "cases", "kind": "table", "ref": {"table": table}},
            {"id": "s", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
             "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": field}}}]}
    elif domain == "local_template_beside_muferro":
        document = muferro_document(analysis, extra=[
            {"id": "demo", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
             "inputs": {"rows": {"from": "cases.rows"}}}])
    elif domain == "no_simulation":
        document = {"format": "stk.workflow/1", "ui": {}, "steps": [
            {"id": "cases", "kind": "table", "ref": {"table": muferro.TABLE_ID}}]}
    elif domain == "lammps_beside_muferro":
        document = muferro_document(analysis, extra=[
            {"id": "md", "kind": "simulation", "ref": {"template": "lammps/1"}, "inputs": {"rows": {"from": "cases.rows"}}}])
    else:
        document = muferro_document(analysis, extra=[{"id": "files", "kind": "files", "ref": {"table": muferro.TABLE_ID}}])
    _replace_workflow(cases, document)
    with pytest.raises(ProjectError, match=message):
        call(store, arguments(cases))
    assert store.workflow_runs.list()["runs"] == []


def test_a_saved_run_from_another_domain_is_not_adopted(cases):
    """A non-MuFerro run saved under this call's ID (however it got there) is refused, never offered."""
    store = cases["store"]
    sid = session(store)
    args = arguments(cases)
    # freeze a plan for this exact ID without a Runtime target: not a MuFerro-target run
    run_id = run_identity(sid, 0, "c1")
    other = str(uuid4())
    revision = store.workflows.create("Plain", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": muferro.TABLE_ID}}]}, workflow_id=other,
        expected_revision=store.info()["revision"])["revision"]
    store.workflow_runs.prepare(other, args["rows"], run_id=run_id, expected_revision=revision)
    with pytest.raises(ProjectError):
        call(store, {**args, "expected_revision": revision}, sid=sid)
    assert store.agent_sessions.get(sid)["awaiting"] == []


def test_unrecorded_call_is_not_offered(cases):
    store = cases["store"]
    sid = session(store)
    with pytest.raises(ProjectError, match="frozen preparation"):
        call(store, arguments(cases), sid=sid, record=False)
    # the local plan may exist, but no approval item was offered
    assert store.agent_sessions.get(sid)["awaiting"] == []


@pytest.mark.parametrize("kind", ["files", "latex", "template"])
def test_replay_validation_refuses_mixed_frozen_step_kinds(cases, kind):
    from suan.agent.muferro_runs import _check_frozen
    store = cases["store"]
    request = arguments(cases)
    _, _, result = call(store, request)
    plan = store.workflow_runs.get(result["item"]["run_id"])
    plan["steps"]["foreign"] = {"kind": kind}
    with pytest.raises(ProjectError, match="forbidden step kind"):
        _check_frozen(plan, request)


def test_import_stays_lazy():
    import subprocess
    import sys
    # The suan.agent package already loads its executor and tools; this module must add nothing beyond itself.
    code = ("import sys, json\nimport suan.agent\nbase = set(sys.modules)\nimport suan.agent.muferro_runs\n"
            "print(json.dumps(sorted(set(sys.modules) - base - {'suan.agent.muferro_runs'})))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                            env={k: v for k, v in __import__("os").environ.items() if k != "STK_TOKEN_PLAN_MODEL"}
                            | {"STK_TOKEN_PLAN_API_KEY": ""})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
