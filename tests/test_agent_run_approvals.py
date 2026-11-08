"""Persistent approval decisions over real SQLite; no model, Runtime or solver execution."""
import multiprocessing
from uuid import uuid4

import pytest

from suan.agent.run_approvals import PREPARE_TOOL, RunApprovals, run_identity
from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.agent_sessions import HARNESS, digest
from test_workflow_runs import project  # noqa: F401 - real saved manufactured workflow fixture


def session(store, *, tool=True):
    sid = str(uuid4())
    definition = {"name": PREPARE_TOOL, "version": 1, "level": "prepare_run"}
    store.agent_sessions.create(sid, {"id": sid, "harness": HARNESS, "tools": [definition] if tool else []},
                                "Prepare the selected rows", turn_id=str(uuid4()), request_sha256=digest(sid))
    return sid


def prepared(store, ids, *, sid=None, call="c1", record=True, tool=True):
    sid = sid or session(store, tool=tool)
    arguments = {"workflow_id": ids["workflow"], "rows": [ids["rows"][0]],
                 "expected_revision": store.info()["revision"]}
    if record:
        store.agent_sessions.append(sid, "tool_called", {"call_id": call, "tool": PREPARE_TOOL, "version": 1,
                                    "level": "prepare_run", "arguments": arguments,
                                    "arguments_sha256": digest(arguments)}, turn=0)
    rid = run_identity(sid, 0, call)
    store.workflow_runs.prepare(**arguments, run_id=rid)
    return sid, rid


def offered(store, ids):
    sid, rid = prepared(store, ids)
    ledger = RunApprovals(store)
    item = ledger.offer(sid, turn=0, call_id="c1", run_id=rid)
    store.agent_sessions.append(sid, "stopped", {"reason": "final"}, turn=0)
    return ledger, sid, item


def consume(ledger, sid, item, decision="start", **changes):
    params = {"plan_sha256": item["plan_sha256"], "expected_revision": item["expected_revision"], "by": "local-user"}
    params.update(changes)
    return ledger.consume(sid, item["item_id"], decision, **params)


def test_offer_is_atomic_bounded_and_replays_original_binding(project):
    store, ids = project
    sid, rid = prepared(store, ids)
    before = store.info()["revision"]
    ledger = RunApprovals(store)
    item = ledger.offer(sid, turn=0, call_id="c1", run_id=rid)
    view = store.agent_sessions.get(sid)
    assert view["awaiting"] == [item]
    assert [e["kind"] for e in view["events"]][-2:] == ["policy", "awaiting_user"]
    assert ledger.offer(sid, turn=0, call_id="c1", run_id=rid) == item
    assert store.agent_sessions.get(sid)["chain_sha256"] == view["chain_sha256"]
    assert store.info()["revision"] == before
    assert store.workflow_runs.get(rid)["status"] == "prepared"


@pytest.mark.parametrize("record,tool", [(False, True), (True, False)])
def test_unrecorded_or_unfrozen_preparation_cannot_offer_a_run(project, record, tool):
    store, ids = project
    sid, rid = prepared(store, ids, record=record, tool=tool)
    with pytest.raises(ProjectError, match="frozen preparation"):
        RunApprovals(store).offer(sid, turn=0, call_id="c1", run_id=rid)
    assert store.agent_sessions.get(sid)["awaiting"] == []


def test_foreign_session_or_call_cannot_borrow_run(project):
    store, ids = project
    sid, rid = prepared(store, ids)
    for target, call in [(session(store), "c1"), (sid, "c2")]:
        with pytest.raises(ProjectError, match="belong"):
            RunApprovals(store).offer(target, turn=0, call_id=call, run_id=rid)


def test_different_recorded_rows_are_not_adopted(project):
    store, ids = project
    sid, rid = prepared(store, ids, record=False)
    args = {"workflow_id": ids["workflow"], "rows": [ids["rows"][1]], "expected_revision": store.info()["revision"]}
    store.agent_sessions.append(sid, "tool_called", {"call_id": "c1", "tool": PREPARE_TOOL, "version": 1,
                                "level": "prepare_run", "arguments": args, "arguments_sha256": digest(args)}, turn=0)
    with pytest.raises(RevisionConflict, match="arguments"):
        RunApprovals(store).offer(sid, turn=0, call_id="c1", run_id=rid)


def test_decision_is_consumed_before_dispatch_and_survives_lost_receipt(project):
    store, ids = project
    ledger, sid, item = offered(store, ids)
    first = consume(ledger, sid, item)
    assert first["dispatch"] is True
    assert first["decision"]["by"] == {"user": "local-user", "authenticated": False}
    assert store.agent_sessions.get(sid)["awaiting"] == []
    # Crash here: no WorkflowRuns.start and no receipt. Reopen must not dispatch.
    reopened = ProjectStore(store.directory)
    again = consume(RunApprovals(reopened), sid, item)
    assert again["dispatch"] is False
    for _ in range(3):
        assert RunApprovals(reopened).observe(sid, item["item_id"])["outcome"] == "uncertain"
    assert reopened.workflow_runs.get(item["run_id"])["status"] == "prepared"
    receipts = [e for e in reopened.agent_sessions.events(sid)[1] if e["kind"] == "approval_receipt"]
    assert len(receipts) == 1 and receipts[0]["ok"] is False
    assert reopened.agent_sessions.get(sid)["awaiting"] == []
    with pytest.raises(RevisionConflict, match="consumed"):
        consume(ledger, sid, item, "decline")


def test_decline_never_starts_and_cannot_be_changed_to_start(project):
    from suan.agent.executor import AgentExecutor
    store, ids = project
    ledger, sid, item = offered(store, ids)
    assert consume(ledger, sid, item, "decline")["dispatch"] is False
    assert ledger.observe(sid, item["item_id"])["outcome"] == "declined"
    with pytest.raises(RevisionConflict, match="consumed"):
        consume(ledger, sid, item)
    assert store.workflow_runs.get(item["run_id"])["status"] == "prepared"
    view = store.agent_sessions.get(sid)
    AgentExecutor(None)._observe(store, sid, view, view["events"], 1)
    facts = store.agent_sessions.events(sid)[1][-1]["facts"]
    assert facts["run_id"] == item["run_id"] and facts["outcome"] == "declined"


@pytest.mark.parametrize("change", [{"plan_sha256": "0" * 64}, {"expected_revision": True}, {"by": ""}])
def test_invalid_decision_does_not_consume_card(project, change):
    store, ids = project
    ledger, sid, item = offered(store, ids)
    before = store.agent_sessions.get(sid)["chain_sha256"]
    with pytest.raises(ProjectError):
        consume(ledger, sid, item, **change)
    assert store.agent_sessions.get(sid)["chain_sha256"] == before


def test_current_revision_and_manual_start_are_rechecked_but_stale_decline_is_allowed(project):
    store, ids = project
    ledger, sid, item = offered(store, ids)
    executor = str(uuid4())
    store.workflow_runs.start(item["run_id"], executor_id=executor)
    store.workflow_runs.stop(item["run_id"], executor_id=executor)
    with pytest.raises(RevisionConflict, match="already been started"):
        consume(ledger, sid, item)
    assert consume(ledger, sid, item, "decline")["dispatch"] is False
    ledger, sid, item = offered(store, ids)
    store.apply([{"op": "set_cell", "table_id": ids["cases"], "record_id": ids["rows"][1],
                  "field_id": ids["label"], "value": "magma"}], expected_revision=store.info()["revision"])
    with pytest.raises(RevisionConflict, match="project changed"):
        consume(ledger, sid, item)
    assert consume(ledger, sid, item, "decline")["dispatch"] is False


def test_unrelated_manual_start_is_not_a_success_receipt(project):
    store, ids = project
    ledger, sid, item = offered(store, ids)
    consume(ledger, sid, item)
    store.workflow_runs.start(item["run_id"], executor_id=str(uuid4()))
    result = ledger.observe(sid, item["item_id"])
    assert result["outcome"] == "other_start" and result["ok"] is False


def test_original_started_event_recovers_receipt_without_restarting(project):
    store, ids = project
    ledger, sid, item = offered(store, ids)
    approved = consume(ledger, sid, item)
    executor = str(uuid4())
    store.workflow_runs.start(item["run_id"], executor_id=executor, approval=approved["decision"]["approval"])
    # The service lost its reply after started committed. Observation recovers
    # that evidence, including after the original run has already stopped.
    store.workflow_runs.stop(item["run_id"], executor_id=executor)
    reopened = ProjectStore(store.directory)
    result = RunApprovals(reopened).observe(sid, item["item_id"])
    assert result["outcome"] == "started" and result["ok"] is True
    assert result["run_status"] == "stopped" and result["executor_id"] == executor
    assert consume(RunApprovals(reopened), sid, item)["dispatch"] is False
    assert reopened.workflow_runs.get(item["run_id"])["status"] == "stopped"
    before = reopened.agent_sessions.get(sid)["chain_sha256"]
    assert RunApprovals(reopened).observe(sid, item["item_id"]) == result
    assert reopened.agent_sessions.get(sid)["chain_sha256"] == before


def test_manual_start_between_consumption_and_dispatch_cannot_be_restarted(project):
    store, ids = project
    ledger, sid, item = offered(store, ids)
    approved = consume(ledger, sid, item)
    executor = str(uuid4())
    store.workflow_runs.start(item["run_id"], executor_id=executor)
    store.workflow_runs.stop(item["run_id"], executor_id=executor)
    with pytest.raises(RevisionConflict, match="already been started"):
        store.workflow_runs.start(item["run_id"], executor_id=str(uuid4()), approval=approved["decision"]["approval"])
    assert ledger.observe(sid, item["item_id"])["outcome"] == "other_start"
    assert consume(ledger, sid, item)["dispatch"] is False


def test_archive_after_offer_is_rechecked_and_decline_remains_available(project):
    store, ids = project
    ledger, sid, item = offered(store, ids)
    store.archive.set([{"kind": "workflow_run", "id": item["run_id"]}], archived=True)
    with pytest.raises(ProjectError, match="archived"):
        consume(ledger, sid, item)
    assert consume(ledger, sid, item, "decline")["dispatch"] is False


def test_offer_transaction_rolls_back_when_awaiting_append_fails(project, monkeypatch):
    from suan.project.agent_sessions import AgentSessions
    store, ids = project
    sid, rid = prepared(store, ids)
    original = AgentSessions._append

    def failed(self, db, session_id, turn, kind, payload):
        if kind == "awaiting_user":
            raise ProjectError("injected append failure")
        return original(self, db, session_id, turn, kind, payload)

    before = store.agent_sessions.get(sid)["chain_sha256"]
    monkeypatch.setattr(AgentSessions, "_append", failed)
    with pytest.raises(ProjectError, match="injected"):
        RunApprovals(store).offer(sid, turn=0, call_id="c1", run_id=rid)
    assert store.agent_sessions.get(sid)["chain_sha256"] == before


def test_next_agent_turn_observes_run_card_without_treating_it_as_a_draft(project):
    from suan.agent.executor import AgentExecutor
    store, ids = project
    _, sid, item = offered(store, ids)
    view = store.agent_sessions.get(sid)
    AgentExecutor(None)._observe(store, sid, view, view["events"], 1)
    assert store.agent_sessions.get(sid)["awaiting"] == [item]
    assert store.workflow_runs.get(item["run_id"])["status"] == "prepared"
    observed = store.agent_sessions.events(sid)[1][-1]
    assert observed["facts"]["kind"] == "run_approval" and observed["facts"]["outcome"] == "pending"


def test_next_agent_turn_keeps_original_run_identity_in_receipt_observation(project):
    from suan.agent.executor import AgentExecutor
    store, ids = project
    ledger, sid, item = offered(store, ids)
    approved = consume(ledger, sid, item)
    store.workflow_runs.start(item["run_id"], executor_id=str(uuid4()), approval=approved["decision"]["approval"])
    ledger.observe(sid, item["item_id"])
    view = store.agent_sessions.get(sid)
    AgentExecutor(None)._observe(store, sid, view, view["events"], 1)
    observed = store.agent_sessions.events(sid)[1][-1]
    assert observed["facts"]["kind"] == "run_decision" and observed["facts"]["run_id"] == item["run_id"]
    assert observed["facts"]["approval"] == approved["decision"]["approval"]


def _consume_process(directory, sid, item, gate, results):
    store = ProjectStore(directory)
    gate.wait(20)
    results.put(consume(RunApprovals(store), sid, item)["dispatch"])


def test_cross_process_same_decision_dispatches_only_once(project):
    store, ids = project
    _, sid, item = offered(store, ids)
    context = multiprocessing.get_context("spawn")
    gate, results = context.Event(), context.Queue()
    processes = [context.Process(target=_consume_process, args=(str(store.directory), sid, item, gate, results))
                 for _ in range(4)]
    for p in processes:
        p.start()
    gate.set()
    try:
        outcomes = [results.get(timeout=30) for _ in processes]
        assert outcomes.count(True) == 1 and outcomes.count(False) == 3
    finally:
        for p in processes:
            p.join(15)
            if p.is_alive():
                p.terminate()
                p.join(5)
    assert all(p.exitcode == 0 for p in processes)
