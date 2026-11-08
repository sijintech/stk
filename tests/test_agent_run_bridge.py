"""S2c desktop admission and strict wire contracts over real project/session/run stores.

The background workflow body is a controlled waiting thread; no solver, Runtime or model runs.
"""
from uuid import uuid4

import pytest

from suan.agent import AgentBusy, AgentExecutor, levels
from suan.agent.run_approvals import RunApprovals, run_identity
from suan.desktop_bridge import workflow_runs
from suan.desktop_bridge.protocol import BridgeError
from suan.models import ModelGateway
from suan.project import ProjectError, RevisionConflict
from suan.project.agent_sessions import digest
from test_agent_run_approvals import project, session  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_workflow_run_executor_approval import Controlled

TARGET = {"connection": "runtime:lab", "connection_identity": "endpoint-A", "options": {"launcher": "none"}}
PERSON = {"user": "local-user", "host": "test-host"}


def freeze(value):
    return {**value, "connection_identity": "endpoint-A"}


def offered(store, ids, sid=None):
    sid = sid or session(store)
    args = {"workflow_id": ids["workflow"], "rows": [ids["rows"][0]], "expected_revision": store.info()["revision"]}
    store.agent_sessions.append(sid, "tool_called", {"call_id": "c1", "tool": "prepare_muferro_run", "version": 1,
        "level": "prepare_run", "arguments": args, "arguments_sha256": digest(args)}, turn=0)
    rid = run_identity(sid, 0, "c1")
    store.workflow_runs.prepare(**args, run_id=rid, simulation=TARGET)
    item = RunApprovals(store).offer(sid, turn=0, call_id="c1", run_id=rid)
    store.agent_sessions.append(sid, "stopped", {"reason": "final"}, turn=0)
    return sid, item


@pytest.fixture
def adapter(project):
    store, ids = project
    controlled = Controlled(workflow_runs.WorkflowRunExecutor(None))
    agents = AgentExecutor(ModelGateway(), services={"freeze_run_target": freeze,
                                                    "workflow_executor": controlled.executor})
    sid = session(store)
    agents.configure_run_target(store, sid, TARGET, by=PERSON)
    sid, item = offered(store, ids, sid)
    yield agents, controlled, store, ids, sid, item
    controlled.finish()
    controlled.executor.shutdown(wait=True)
    agents.shutdown(wait=True)


def decide(agents, store, sid, item, decision="start"):
    return agents.decide_run(store, sid, item["item_id"], decision, plan_sha256=item["plan_sha256"],
                             expected_revision=item["expected_revision"], by=PERSON)


def test_first_start_is_single_use_and_history_is_not_current_execution(adapter):
    agents, controlled, store, _, sid, item = adapter
    before = store.info()["revision"]
    result = decide(agents, store, sid, item)
    assert controlled.entered.wait(5)
    assert result["receipt"]["outcome"] == "started"
    controlled.finish()
    again = decide(agents, store, sid, item)
    assert again["receipt"]["outcome"] == "started" and again["receipt"]["run_status"] == "stopped"
    assert controlled.bodies == [item["run_id"]] and store.info()["revision"] == before
    assert RunApprovals(store).cards(sid)[0]["decision"]["decision"] == "start"


@pytest.mark.parametrize("reason", ["capacity", "closing", "target", "revision", "busy"])
def test_admission_rejects_before_consumption(adapter, monkeypatch, reason):
    agents, controlled, store, ids, sid, item = adapter
    if reason == "capacity":
        monkeypatch.setattr(workflow_runs, "MAX_ACTIVE_RUNS", 0)
    elif reason == "closing":
        controlled.executor._closing.set()
    elif reason == "target":
        agents.services["freeze_run_target"] = lambda v: {**v, "connection_identity": "endpoint-B"}
    elif reason == "revision":
        store.apply([{"op": "rename_table", "id": ids["cases"], "name": "Changed"}],
                    expected_revision=store.info()["revision"])
    else:
        agents._runs[(str(store.directory), sid)] = object()
    try:
        with pytest.raises((ProjectError, BridgeError)):
            decide(agents, store, sid, item)
    finally:
        agents._runs.clear()
    assert RunApprovals(store).decision(sid, item["item_id"]) is None
    assert controlled.bodies == [] and store.workflow_runs.get(item["run_id"])["status"] == "prepared"


def test_dispatch_failure_stays_consumed_and_replay_does_not_dispatch(adapter, monkeypatch):
    agents, controlled, store, _, sid, item = adapter
    calls = []

    def lost(*args, **kwargs):
        calls.append(kwargs)
        raise OSError("lost local dispatch reply")

    monkeypatch.setattr(controlled.executor, "start", lost)
    assert decide(agents, store, sid, item)["receipt"]["outcome"] == "uncertain"
    assert decide(agents, store, sid, item)["receipt"]["outcome"] == "uncertain"
    assert len(calls) == 1 and RunApprovals(store).cards(sid)[0]["decision"] is not None
    assert store.agent_sessions.get(sid)["awaiting"] == []


def test_lost_reply_after_started_is_observed_without_restarting(adapter, monkeypatch):
    agents, controlled, store, _, sid, item = adapter
    start = controlled.executor.start

    def lost(*args, **kwargs):
        start(*args, **kwargs)
        raise OSError("reply lost after claim")

    monkeypatch.setattr(controlled.executor, "start", lost)
    assert decide(agents, store, sid, item)["receipt"]["outcome"] == "started"
    assert decide(agents, store, sid, item)["receipt"]["outcome"] == "started"
    assert controlled.entered.wait(5) and controlled.bodies == [item["run_id"]]


def test_explicit_target_changes_preserve_types_and_do_not_prepare(adapter):
    agents, controlled, store, _, sid, item = adapter
    from suan.agent.run_targets import selected
    target = {**TARGET, "options": {"nodes": 1, "threads_per_rank": 1, "signed": -0.0}}
    before = store.info()["revision"]
    agents.configure_run_target(store, sid, target, by=PERSON)
    assert digest(selected(store, sid)) == digest(target)
    with pytest.raises(RevisionConflict):
        decide(agents, store, sid, item)
    agents.configure_run_target(store, sid, None, by=PERSON)
    assert selected(store, sid) is None
    with pytest.raises(ProjectError, match="Choose"):
        agents.run_target(store, sid)
    assert controlled.bodies == [] and store.info()["revision"] == before


@pytest.fixture
def service(project, inproc, monkeypatch):
    store, ids = project
    h = inproc()
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    monkeypatch.setattr(h.bridge, "_simulation_identity", lambda p: {"simulation": freeze(p["simulation"])})
    sid = session(store)
    params = {"handle": handle, "session_id": sid}
    h.call("project.agent.run_target", {**params, "simulation": {"connection": TARGET["connection"], "options": TARGET["options"]}})
    sid, item = offered(store, ids, sid)
    return h, store, params, item


def test_desktop_complete_review_and_decline_have_strict_wire_shapes(service):
    h, store, params, item = service
    args = {**params, "item_id": item["item_id"]}
    decision = {**args, "decision": "start", "plan_sha256": item["plan_sha256"], "expected_revision": item["expected_revision"]}
    assert h.error("project.agent.run_decide", decision)["code"] == "conflict"
    assert RunApprovals(store).decision(params["session_id"], item["item_id"]) is None
    reviewed = h.call("project.agent.run_plan", args)
    assert reviewed["run"]["plan_sha256"] == item["plan_sha256"] and reviewed["run"]["simulation"] == TARGET
    result = h.call("project.agent.run_decide", {**decision, "decision": "decline"})
    assert result["receipt"]["outcome"] == "declined" and result["receipt"]["ok"] is True
    assert result["receipt"]["run_id"] == item["run_id"]
    assert h.call("project.agent.run_observe", args)["receipt"]["outcome"] == "declined"
    view = h.call("project.agent.get", params)
    assert view["run_approvals"][0]["decision"]["decision"] == "decline" and view["awaiting"] == []
    names = {"project.agent.run_" + name for name in ("target", "plan", "decide", "observe")}
    assert names <= set(h.bridge.methods) and names <= set(levels.DESKTOP_ONLY)
    assert not names & set(h.bridge.script_catalog()["operations"])


def test_oversize_plan_is_not_marked_reviewed(service, monkeypatch):
    h, store, params, item = service
    monkeypatch.setattr(h.bridge, "max_line", 1024)
    assert h.error("project.agent.run_plan", {**params, "item_id": item["item_id"]})["code"] == "result_too_large"
    assert not h.bridge._agent_run_reviews
    assert RunApprovals(store).decision(params["session_id"], item["item_id"]) is None


def test_target_schema_rejects_model_selected_identity_and_hub(service):
    h, store, params, _ = service
    assert h.error("project.agent.run_target", {**params, "simulation": TARGET})["code"] == "invalid_params"
    assert h.error("project.agent.run_target", {**params, "simulation": {"connection": "hub:other", "options": {}}})["code"] == "invalid_params"
    assert h.call("project.agent.run_target", params)["run_target"] == TARGET
