"""WorkflowRunExecutor.start(..., approval=...) over real SQLite (CL-S2C-EXECUTOR-08).

The executor passes a person's first-start envelope unchanged to the store's atomic first claim.
Each executor's background body is replaced by a controllable local thread, so nothing executes a
step, contacts a Runtime or a model.
"""
import threading
import types
from uuid import uuid4

import pytest

from suan.desktop_bridge import workflow_runs as executor_module
from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.workflow_runs import MAX_ACTIVE_RUNS, WorkflowRunExecutor
from suan.project import ProjectError, ProjectStore, RevisionConflict
from test_workflow_run_approval import approval_for, prepare, project, run_events, started  # noqa: F401 - real SQLite


class Controlled:
    """An executor whose background body only waits on a gate and then releases the run like the real one."""

    def __init__(self, executor):
        self.executor, self.gate, self.entered = executor, threading.Event(), threading.Event()
        self.bodies = []
        executor._run = self.run

    def run(self, job):
        self.bodies.append(job.run_id)
        self.entered.set()
        try:
            self.gate.wait(10)
        finally:
            try:
                job.store.workflow_runs.stop(job.run_id, executor_id=self.executor.executor_id)
            except ProjectError:
                pass
            with self.executor._lock:
                self.executor._jobs.pop(self.executor._key(job.store, job.run_id), None)

    def finish(self):
        self.gate.set()
        for job in list(self.executor._jobs.values()):
            job.thread.join(10)


@pytest.fixture
def executor():
    made = []

    def build():
        controlled = Controlled(WorkflowRunExecutor(None))
        made.append(controlled)
        return controlled

    yield build
    for controlled in made:
        controlled.finish()
        controlled.executor.shutdown(wait=True)


def start_events(store, run_id):
    return started(store, run_id)


def test_approval_reaches_the_started_event(project, executor):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    controlled = executor()
    record = controlled.executor.start(store, run["id"], approval=approval)
    assert record["status"] == "running" and record["executor_id"] == controlled.executor.executor_id
    assert controlled.entered.wait(10) and controlled.bodies == [run["id"]]
    events = start_events(store, run["id"])
    assert len(events) == 1 and events[0]["approval"] == approval
    assert events[0]["owner"]["pid"] > 0


@pytest.mark.parametrize("field", ["plan_sha256", "request_sha256", "expected_revision", "approval_id"])
def test_wrong_binding_creates_no_job_and_no_started_event(project, executor, field):
    store, ids = project
    run = prepare(store, ids)
    good = approval_for(store, run["id"])
    bad = {"plan_sha256": "0" * 64, "request_sha256": "a" * 64, "expected_revision": good["expected_revision"] + 1,
           "approval_id": "not-a-uuid"}[field]
    controlled = executor()
    with pytest.raises(ProjectError):
        controlled.executor.start(store, run["id"], approval={**good, field: bad})
    assert not controlled.executor.active(store, run["id"]) and controlled.bodies == []
    assert start_events(store, run["id"]) == [] and store.workflow_runs.get(run["id"])["status"] == "prepared"


def test_live_manual_job_is_not_reported_as_an_approved_start(project, executor):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    controlled = executor()
    controlled.executor.start(store, run["id"])  # a person's ordinary start: the job is live here
    assert controlled.entered.wait(10)
    with pytest.raises(BridgeError) as excinfo:
        controlled.executor.start(store, run["id"], approval=approval)
    assert excinfo.value.code == "conflict"
    events = start_events(store, run["id"])
    assert len(events) == 1 and "approval" not in events[0]
    # the ordinary call still returns the live record, as before
    assert controlled.executor.start(store, run["id"])["status"] == "running"
    assert len(start_events(store, run["id"])) == 1


def test_omitted_approval_keeps_restart_behavior(project, executor):
    store, ids = project
    run = prepare(store, ids)
    controlled = executor()
    controlled.executor.start(store, run["id"])
    controlled.finish()
    assert store.workflow_runs.get(run["id"])["status"] == "stopped"
    second = executor()
    assert second.executor.start(store, run["id"])["status"] == "running"  # a stopped run restarts without approval
    assert len(start_events(store, run["id"])) == 2


def test_approved_start_after_any_start_is_refused_by_any_executor(project, executor):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    first = executor()
    first.executor.start(store, run["id"], approval=approval)
    first.finish()
    for controlled in (first, executor()):  # the same service, or another one
        with pytest.raises(RevisionConflict, match="already been started"):
            controlled.executor.start(store, run["id"], approval=approval)
        assert not controlled.executor.active(store, run["id"])
    assert len(start_events(store, run["id"])) == 1 and first.bodies == [run["id"]]


def test_concurrent_approved_starts_on_independent_services_make_one_started_event(project, executor):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])
    services = [executor() for _ in range(4)]
    barrier, outcomes = threading.Barrier(len(services)), []

    def attempt(controlled, envelope):
        own = ProjectStore(store.directory)  # each service has its own store and SQLite connection
        barrier.wait(10)
        try:
            controlled.executor.start(own, run["id"], approval=envelope)
            outcomes.append("ok")
        except (ProjectError, BridgeError) as exc:
            outcomes.append(type(exc).__name__)

    threads = [threading.Thread(target=attempt, args=(c, {**approval, "approval_id": str(uuid4())}))
               for c in services]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert outcomes.count("ok") == 1 and sorted(set(outcomes) - {"ok"}) == ["RevisionConflict"], outcomes
    assert len(start_events(store, run["id"])) == 1
    assert sum(len(c.bodies) for c in services) == 1


def test_thread_start_failure_keeps_stop_and_forbids_approved_restart(project, executor, monkeypatch):
    store, ids = project
    run = prepare(store, ids)
    approval = approval_for(store, run["id"])

    class FailingThread(threading.Thread):
        def start(self):
            raise RuntimeError("cannot start thread")

    controlled = executor()
    monkeypatch.setattr(executor_module, "threading",
                        types.SimpleNamespace(Thread=FailingThread, Event=threading.Event, RLock=threading.RLock))
    with pytest.raises(RuntimeError):
        controlled.executor.start(store, run["id"], approval=approval)
    monkeypatch.undo()
    assert not controlled.executor.active(store, run["id"]) and controlled.bodies == []
    state = store.workflow_runs.get(run["id"])
    assert state["status"] == "stopped"  # the existing stop bookkeeping stays; never back to prepared
    assert [event["status"] for event in run_events(store, run["id"])] == ["prepared", "started", "stopped"]
    for retry in (controlled, executor()):
        with pytest.raises(RevisionConflict, match="already been started"):
            retry.executor.start(store, run["id"], approval=approval)
        with pytest.raises(RevisionConflict, match="already been started"):
            retry.executor.start(store, run["id"], approval={**approval, "approval_id": str(uuid4())})
    assert len(start_events(store, run["id"])) == 1


def test_closing_and_capacity_checks_still_come_first(project, executor):
    store, ids = project
    runs = [prepare(store, ids) for _ in range(MAX_ACTIVE_RUNS + 1)]
    controlled = executor()
    for run in runs[:MAX_ACTIVE_RUNS]:
        controlled.executor.start(store, run["id"])
    extra = runs[-1]
    with pytest.raises(BridgeError) as excinfo:
        controlled.executor.start(store, extra["id"], approval=approval_for(store, extra["id"]))
    assert excinfo.value.code == "busy" and start_events(store, extra["id"]) == []
    closing = executor()
    closing.executor.shutdown()
    with pytest.raises(BridgeError) as excinfo:
        closing.executor.start(store, extra["id"], approval=approval_for(store, extra["id"]))
    assert excinfo.value.code == "shutting_down" and start_events(store, extra["id"]) == []
    # the busy/closing refusals spent nothing: the run can still take its first approved start
    controlled.finish()
    fresh = executor()
    assert fresh.executor.start(store, extra["id"], approval=approval_for(store, extra["id"]))["status"] == "running"
