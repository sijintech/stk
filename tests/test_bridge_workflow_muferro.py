"""MuFerro steps in per-row workflow runs (W5): a real local Runtime and the synthetic CI solver.

Every row's task is submitted before any finishes; results are collected and the final state reaches
the row's analysis; a changed row is refused; a run STK stopped following adopts its Runtime task on
the next start; a failed task is retried as a new task; cancelling the run cancels the Runtime task."""
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from mupro_fake import make_fake_sdk
from suan.desktop_bridge import workflow_runs
from suan.project import ProjectStore
from suan.runtime.server import Handler
from suan.scripting import API, ProjectRuns
from suan.workflows import muferro
from test_analysis_run_executor import value_result
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile


class RecordingWorker:
    """Stands in for the graph worker: records which files each analysis run received."""
    def __init__(self):
        self.files = []

    def evaluate(self, identity, work, cancel, events):
        from pathlib import Path
        root = Path(work["local_bindings"]["run"])
        self.files.append(sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()))
        return value_result(work["request"]["graph"])


def energy_document():
    return {"format": "stk.analysis-document/1", "graph": {"schema": "stk.graph/1", "parameters": [],
            "nodes": [{"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
                      {"id": "n", "type": "fixture.test.value@1"}],
            "outputs": {"value": "n.value"}}, "parameters": {}, "outputs": ["value"]}


@pytest.fixture
def scan(inproc, runtime, tmp_path, monkeypatch):
    """Two MuFerro rows (300 K, 325 K) and a workflow cases -> MuFerro -> energy analysis."""
    client, supervisor, _, _ = runtime
    sdk = make_fake_sdk(tmp_path / "fake-sdk")
    for name in ("STK_MUPRO_ENV_SCRIPTS", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI", "STK_ALLOW_LOCAL_MPI", "SLURM_JOB_ID", "PBS_JOBID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(sdk))
    h = inproc()
    connection = add_profile(h, runtime)
    store = ProjectStore.create(tmp_path / "project", "MuFerro scan")
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    api = API(lambda operation, params: h.call(operation, params))
    api._project_handle = handle
    source = sdk / "share/mupro/skills/mupro-muferro/examples"
    first = api.muferro.import_case(source, expected_revision=store.info()["revision"])["record_id"]
    second = api.muferro.clone_case(first, expected_revision=store.info()["revision"])["record_id"]
    store.apply([{"op": "set_cell", "table_id": muferro.TABLE_ID, "record_id": row, "field_id": muferro.FIELD_IDS["temperature"],
                  "value": value} for row, value in ((first, 300), (second, 325))], expected_revision=store.info()["revision"])
    analysis, workflow = str(uuid4()), str(uuid4())
    store.analyses.create("Energy", energy_document(), analysis_id=analysis, expected_revision=store.info()["revision"])
    store.workflows.create("MuFerro scan", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": muferro.TABLE_ID}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "muferro/1"}, "inputs": {"rows": {"from": "cases.rows"}}},
        {"id": "energy", "kind": "analysis", "ref": {"analysis": analysis}, "inputs": {"run": {"from": "simulate.files"}}}]},
        workflow_id=workflow, expected_revision=store.info()["revision"])
    worker = RecordingWorker()
    h.bridge.analysis_executor.worker = worker
    h.bridge.workflow_executor.poll_seconds = 0.02
    return {"h": h, "store": store, "handle": handle, "client": client, "supervisor": supervisor, "api": api,
            "connection": connection, "rows": [first, second], "workflow": workflow, "worker": worker, "tmp": tmp_path}


def prepare(s, rows=None):
    return s["h"].call("project.workflow_runs.prepare", {
        "handle": s["handle"], "workflow_id": s["workflow"], "rows": rows or s["rows"], "run_id": str(uuid4()),
        "expected_revision": s["store"].info()["revision"],
        "simulation": {"connection": s["connection"], "options": {"launcher": "none"}}})["run"]


def get(s, run_id):
    return s["h"].call("project.workflow_runs.get", {"handle": s["handle"], "run_id": run_id})["run"]


def until(condition, s, timeout=60, tick=True):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tick:
            s["supervisor"].tick()
        value = condition()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail("condition not reached")


def settled(s, run_id, tick=True, timeout=60):
    executor, store = s["h"].bridge.workflow_executor, s["h"].bridge.projects._stores[s["handle"]]
    return until(lambda: (lambda run: run if run["status"] == "stopped" and not executor.active(store, run_id) else None)(
        get(s, run_id)), s, timeout=timeout, tick=tick)


def tasks(run):
    return {(task["step"], task["row"]): task for task in run["tasks"]}


def submitted(s, run_id):
    """The first row's simulation step has a Runtime task recorded (submitted, then queued)."""
    progress = tasks(get(s, run_id))[("simulate", s["rows"][0])]["progress"]
    return progress is not None and "task_id" in progress


def test_every_row_is_submitted_at_once_then_collected_and_analysed(scan):
    s = scan
    run = prepare(s)
    assert run["simulation"]["connection"] == s["connection"] and run["simulation"]["options"] == {"launcher": "none"}
    assert len(run["simulation"]["connection_identity"]) == 16
    frozen = run["parameters"]["simulate"]
    assert [frozen[row]["temperature"] for row in s["rows"]] == [300, 325]
    assert s["client"].tasks() == []  # preparing submits nothing
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    # Both rows reach the Runtime before either finishes (the scheduler has not run yet).
    # reserve() exposes each task as 'preparing' while its input files are copied. Task count
    # alone does not mean both submit requests have finished. Keep the scheduler stopped until
    # both complete submissions are queued; this still proves no row waits for another to finish.
    until(lambda: (lambda current: len(current) == 2 and all(task["state"] == "queued" for task in current))(
        s["client"].tasks()), s, tick=False)
    assert all(task["state"] == "queued" for task in s["client"].tasks())
    done = settled(s, run["id"])
    assert done["complete"], done["tasks"]
    by_task = tasks(done)
    for number, row in enumerate(s["rows"], 1):
        simulate = by_task[("simulate", row)]
        assert simulate["attempt"] == 1 and simulate["progress"]["stage"] == "collecting"
        produced = simulate["produced"]
        assert produced["simulation_run_id"] == simulate["progress"]["simulation_run_id"]
        assert produced["directory"] == f"results/muferro/{produced['simulation_run_id']}"
        assert "case/Polar.00000002.dat" in produced["files"] and "case/Polar.00000000.dat" not in produced["files"]
        assert {"stk-mupro.json", "case/energy_out.dat", "case/input.toml"} <= set(produced["files"])
        assert by_task[("energy", row)]["produced"]["snapshot_id"] == produced["snapshot_id"]
    assert len(s["worker"].files) == 2 and s["worker"].files[0] == sorted(produced["files"])
    results = next(t for t in s["store"].snapshot()["tables"] if t["id"] == muferro.RESULT_TABLE_ID)
    assert len(results["records"]) == 2
    temperatures = sorted(s["store"].runs.get(by_task[("simulate", row)]["produced"]["simulation_run_id"])["plan"]["parameters"]
                          ["values"][muferro.FIELD_IDS["temperature"]] for row in s["rows"])
    assert temperatures == [300, 325]
    assert len(s["client"].tasks()) == 2
    assert not s["h"].violations


def test_a_row_changed_after_freezing_is_refused_without_submitting(scan):
    s = scan
    run = prepare(s, rows=[s["rows"][0]])
    s["store"].apply([{"op": "set_cell", "table_id": muferro.TABLE_ID, "record_id": s["rows"][0],
                       "field_id": muferro.FIELD_IDS["temperature"], "value": 350}], expected_revision=s["store"].info()["revision"])
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    done = settled(s, run["id"])
    simulate = tasks(done)[("simulate", s["rows"][0])]
    assert simulate["status"] == "failed" and simulate["error"]["code"] == "row_changed"
    assert tasks(done)[("energy", s["rows"][0])]["status"] == "pending"
    assert s["client"].tasks() == [] and s["store"].runs.list()["runs"] == []
    stale = s["h"].call("project.workflow_runs.stale", {"handle": s["handle"], "run_id": run["id"]})
    reasons = stale["rows"][0]["steps"]["simulate"]
    assert {"code": "value_changed", "field": muferro.FIELD_IDS["temperature"], "name": "Temperature / 温度",
            "before": 300, "after": 350} in reasons


@pytest.mark.parametrize("change_at", ["after_check", "retry"])
def test_row_is_rechecked_at_the_revision_used_to_prepare(scan, monkeypatch, change_at):
    s = scan
    row = s["rows"][0]
    run = prepare(s, rows=[row])
    assert run["parameters"]["simulate"][row]["temperature"] == 300
    executor = s["h"].bridge.workflow_executor
    original_bind = executor.bound_scripting
    original_prepare = muferro.MuFerro.prepare
    edits, prepare_calls = [], []

    def edit_row():
        revision = s["store"].info()["revision"]
        edits.append(s["store"].apply([{"op": "set_cell", "table_id": muferro.TABLE_ID, "record_id": row,
            "field_id": muferro.FIELD_IDS["temperature"], "value": 350}], expected_revision=revision)["revision"])

    def bind(store, cancel, **options):
        if change_at == "after_check" and not edits:
            edit_row()
        return original_bind(store, cancel, **options)

    def prepare_child(self, *args, **options):
        prepare_calls.append(options["expected_revision"])
        if change_at == "retry" and not edits:
            edit_row()  # MuFerro.prepare now receives a stale revision and asks for a retry.
        return original_prepare(self, *args, **options)

    monkeypatch.setattr(executor, "bound_scripting", bind)
    monkeypatch.setattr(muferro.MuFerro, "prepare", prepare_child)
    workspaces = s["client"].workspaces()
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    until(lambda: get(s, run["id"])["status"] == "stopped" or s["client"].tasks(), s, tick=False)
    assert s["client"].tasks() == [] and s["client"].workspaces() == workspaces
    done = settled(s, run["id"], tick=False)
    simulate = tasks(done)[("simulate", row)]
    assert simulate["status"] == "failed" and simulate["error"]["code"] == "row_changed"
    assert tasks(done)[("energy", row)]["status"] == "pending"
    assert s["store"].runs.list()["runs"] == []
    assert len(edits) == 1
    assert prepare_calls == ([] if change_at == "after_check" else [edits[0] - 1])


def test_a_task_stk_stopped_following_is_adopted_on_the_next_start(scan):
    s = scan
    run = prepare(s, rows=[s["rows"][0]])
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    store = s["h"].bridge.projects._stores[s["handle"]]
    until(lambda: submitted(s, run["id"]), s, tick=False)
    s["h"].bridge.workflow_executor.close_project(store)  # STK stops following (as when the project closes)
    stopped = settled(s, run["id"], tick=False)
    simulate = tasks(stopped)[("simulate", s["rows"][0])]
    assert simulate["status"] == "interrupted" and simulate["error"]["code"] == "detached"
    first_run = simulate["progress"]["simulation_run_id"]
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    done = settled(s, run["id"])
    simulate = tasks(done)[("simulate", s["rows"][0])]
    assert done["complete"] and simulate["attempt"] == 2
    assert simulate["produced"]["simulation_run_id"] == first_run  # adopted, not submitted again
    assert len(s["client"].tasks()) == 1


def test_a_failed_task_is_retried_as_a_new_runtime_task(scan, monkeypatch):
    s = scan
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(make_fake_sdk(s["tmp"] / "failing-sdk", mode="fail")))
    run = prepare(s, rows=[s["rows"][0]])
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    failed = settled(s, run["id"])
    simulate = tasks(failed)[("simulate", s["rows"][0])]
    assert simulate["status"] == "failed" and simulate["error"]["code"] == "runtime_failed"
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(s["tmp"] / "fake-sdk"))
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    done = settled(s, run["id"])
    simulate = tasks(done)[("simulate", s["rows"][0])]
    assert done["complete"] and simulate["attempt"] == 2
    assert simulate["produced"]["simulation_run_id"] != tasks(failed)[("simulate", s["rows"][0])]["progress"]["simulation_run_id"]
    assert len(s["client"].tasks()) == 2


def test_cancelling_the_run_cancels_its_runtime_task(scan):
    s = scan
    run = prepare(s, rows=[s["rows"][0]])
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    until(lambda: submitted(s, run["id"]), s, tick=False)
    s["h"].call("project.workflow_runs.cancel", {"handle": s["handle"], "run_id": run["id"]})
    done = settled(s, run["id"])
    simulate = tasks(done)[("simulate", s["rows"][0])]
    assert simulate["status"] == "cancelled"
    until(lambda: all(task["state"] == "cancelled" for task in s["client"].tasks()), s)
    assert len(s["client"].tasks()) == 1


def test_lost_runtime_cancel_reply_is_confirmed_without_sending_another_cancel(scan, runtime, monkeypatch):
    s = scan
    _, _, server, _ = runtime
    run = prepare(s, rows=[s["rows"][0]])
    params = {"handle": s["handle"], "run_id": run["id"]}
    s["h"].call("project.workflow_runs.start", params)
    until(lambda: submitted(s, run["id"]), s, tick=False)
    progress = tasks(get(s, run["id"]))[("simulate", s["rows"][0])]["progress"]
    task_id = progress["task_id"]
    assert s["client"].task(task_id)["state"] == "queued"
    cancel_replies = []
    respond = Handler.respond

    def drop_cancel_reply(handler, data, code=200):
        if handler.server is server and handler.command == "POST" and handler.path == f"/v1/tasks/{task_id}/cancel":
            cancel_replies.append(data)
            handler.close_connection = True
            return
        return respond(handler, data, code)

    monkeypatch.setattr(Handler, "respond", drop_cancel_reply)
    s["h"].call("project.workflow_runs.cancel", params)
    done = settled(s, run["id"], tick=False)
    simulation = tasks(done)[("simulate", s["rows"][0])]
    assert len(cancel_replies) == 1 and cancel_replies[0]["state"] == "cancelled"
    assert simulation["status"] == "cancelled" and simulation["progress"]["task_id"] == task_id
    child = s["store"].runs.get(progress["simulation_run_id"])["status"]
    assert child["last_operation"] == "refresh" and child["task"]["state"] == "cancelled"
    assert [task["id"] for task in s["client"].tasks()] == [task_id] and not s["worker"].files


def test_malformed_cancel_reply_does_not_stop_cancellation_of_other_rows(scan, runtime, monkeypatch):
    s = scan
    _, _, server, _ = runtime
    run = prepare(s)
    params = {"handle": s["handle"], "run_id": run["id"]}
    s["h"].call("project.workflow_runs.start", params)
    until(lambda: all((task["progress"] or {}).get("task_id") for task in get(s, run["id"])["tasks"]
                      if task["step"] == "simulate"), s, tick=False)
    task_ids = {task["id"] for task in s["client"].tasks()}
    assert len(task_ids) == 2 and all(task["state"] == "queued" for task in s["client"].tasks())
    sent = []
    respond = Handler.respond

    def corrupt_first_cancel_reply(handler, data, code=200):
        if handler.server is server and handler.command == "POST" and handler.path.endswith("/cancel"):
            sent.append(handler.path.split("/")[-2])
            if len(sent) == 1:
                data = {"state": "cancelled"}  # the Runtime applied it, but the reply lost its task identity
        return respond(handler, data, code)

    monkeypatch.setattr(Handler, "respond", corrupt_first_cancel_reply)
    s["h"].call("project.workflow_runs.cancel", params)
    done = settled(s, run["id"], tick=False)
    assert len(sent) == 2 and set(sent) == task_ids
    assert done["counts"] == {"cancelled": 2, "pending": 2} and not done["stop_error"]
    assert {task["id"] for task in s["client"].tasks() if task["state"] == "cancelled"} == task_ids
    assert not s["worker"].files


def test_workflow_cancel_does_not_use_confirmation_after_the_observation_window(monkeypatch):
    clock = [0]
    reads = []

    def refresh(run_id):
        reads.append(run_id)
        clock[0] = workflow_runs._CANCEL_CONFIRM_SECONDS + 1
        return {"status": {"task": {"state": "cancelled"}}}

    def cancel(run_id):
        return {"status": {"task": {"state": "running", "cancel_requested": True}}}

    runs = SimpleNamespace(cancel=cancel, refresh=refresh)
    api = SimpleNamespace(project=SimpleNamespace(runs=runs))
    job = SimpleNamespace(remote={("simulate", "row"): {"simulation_run_id": "original"}})
    executor = workflow_runs.WorkflowRunExecutor(None)
    monkeypatch.setattr(executor, "_api", lambda *args, **kwargs: api)
    monkeypatch.setattr(workflow_runs, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    assert executor._cancel_remote_tasks(job) == {} and reads == ["original"]


def test_cancel_recorded_before_collection_leaves_completed_original_task_for_explicit_start(scan, monkeypatch):
    s = scan
    run = prepare(s, rows=[s["rows"][0]])
    params = {"handle": s["handle"], "run_id": run["id"]}
    ready, resume = threading.Event(), threading.Event()
    refresh = ProjectRuns.refresh

    def hold_completed_reply(project_runs, run_id):
        record = refresh(project_runs, run_id)
        if not ready.is_set() and (record["status"].get("task") or {}).get("state") == "succeeded":
            ready.set()
            assert resume.wait(10), "test did not release the completed Runtime reply"
        return record

    monkeypatch.setattr(ProjectRuns, "refresh", hold_completed_reply)
    s["h"].call("project.workflow_runs.start", params)
    try:
        until(ready.is_set, s)
        # An independently opened store can record cancellation while the executor handles the prior read.
        cancelled = ProjectStore(s["store"].directory).workflow_runs.request_cancel(run["id"])
        assert cancelled["status"] == "cancel_requested"
    finally:
        resume.set()

    stopped = settled(s, run["id"])
    simulation = tasks(stopped)[("simulate", s["rows"][0])]
    assert simulation["status"] == "interrupted" and simulation["error"]["code"] == "runtime_finished_before_cancel"
    assert stopped["stop_error"] == simulation["error"] and not simulation["produced"]
    original = simulation["progress"]["simulation_run_id"]
    task_id = simulation["progress"]["task_id"]
    assert simulation["progress"]["stage"] != "collecting"
    assert s["client"].task(task_id)["state"] == "succeeded"
    assert not (s["store"].directory / "results" / "muferro" / original).exists()
    assert s["worker"].files == []

    s["h"].call("project.workflow_runs.start", params)
    resumed = settled(s, run["id"])
    simulation = tasks(resumed)[("simulate", s["rows"][0])]
    assert resumed["complete"] and simulation["attempt"] == 2
    assert simulation["produced"]["simulation_run_id"] == original and simulation["produced"]["task_id"] == task_id
    assert [task["id"] for task in s["client"].tasks()] == [task_id] and len(s["worker"].files) == 1


def test_preparing_needs_a_runtime_connection_and_valid_rows(scan):
    s = scan
    with pytest.raises(Exception, match="Choose where to run"):
        s["h"].call("project.workflow_runs.prepare", {"handle": s["handle"], "workflow_id": s["workflow"], "rows": s["rows"],
                    "run_id": str(uuid4()), "expected_revision": s["store"].info()["revision"]})
    s["store"].apply([{"op": "set_cell", "table_id": muferro.TABLE_ID, "record_id": s["rows"][1],
                       "field_id": muferro.FIELD_IDS["dt"], "value": -1}], expected_revision=s["store"].info()["revision"])
    with pytest.raises(Exception, match="Row 2: dt must"):
        prepare(s)
    assert s["store"].workflow_runs.list()["runs"] == [] and s["client"].tasks() == []
