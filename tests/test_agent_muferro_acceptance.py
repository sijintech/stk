"""The agent's MuFerro acceptance (docs/design/agent-harness.md, "验收演示"): a real local Runtime with the synthetic
solver, a scripted planner and scripted answers to the session's own requests; nothing reaches a real model.

The agent proposes a sweep as a draft and stops; a person applies it on the session's card and runs the new rows; the
agent then analyses the results. The agent's thread never applies, prepares, starts, submits or labels anything.
"""
import json
import threading
import time
from uuid import uuid4

import pytest

from suan.agent import tools, wire
from suan.desktop_bridge import schema as bridge_schema
from suan.project.drafts import Drafts
from suan.project.labels import Labels
from suan.project.runs import Runs
from suan.project.store import ProjectStore
from suan.project.workflow_runs import WorkflowRuns
from suan.runtime.client import RuntimeClient
from suan.workflows import muferro
from test_bridge_workflow_muferro import scan, settled  # noqa: F401
from test_desktop_bridge import _strict, bridge_env, inproc, second_opinion  # noqa: F401

ADAPTER = "openai-compatible/1:laptop"
TEMPERATURE = muferro.FIELD_IDS["temperature"]


class Model:
    """The model on "this computer": scripted planner turns, and scripted answers to the session's requests."""

    def __init__(self):
        self.turns, self.answers, self.sent, self.asked = [], [], [], []

    def prepare_turn(self, value):
        model = self

        class Prepared:
            def send(self, frozen, cancel):
                model.sent.append(frozen)
                reply = model.turns.pop(0)
                return reply(frozen) if callable(reply) else reply
        return Prepared()

    def send(self, frozen_input, cancel):
        self.asked.append(frozen_input)
        answer = self.answers.pop(0)
        return answer(frozen_input) if callable(answer) else answer


def call(name, arguments=None, text=None):
    return wire.ModelTurn(text, {"id": None, "name": name, "arguments": arguments or {},
                                 "raw_arguments": json.dumps(arguments or {})}, "tool_calls",
                          {"input_tokens": 100, "output_tokens": 20})


def last_result(frozen):
    return json.loads(frozen["messages"][-1]["content"])["data"]


def final(text):
    return wire.ModelTurn(text, None, "stop", {"input_tokens": 50, "output_tokens": 10})


@pytest.fixture
def monitor(monkeypatch):
    """Every call the agent's own thread makes to an operation above draft level (it must make none)."""
    calls = []
    for owner, name in ((ProjectStore, "apply"), (Drafts, "apply"), (Drafts, "discard"), (WorkflowRuns, "prepare"),
                        (WorkflowRuns, "start"), (Runs, "prepare"), (Labels, "set")):
        original = getattr(owner, name)

        def watched(*args, _original=original, _name=f"{owner.__name__}.{name}", **kwargs):
            if threading.current_thread().name == "stk-agent":
                calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(owner, name, watched)
    return calls


def wait(h, handle, session_id, timeout=60):
    deadline = time.monotonic() + timeout
    view = h.call("project.agent.get", {"handle": handle, "session_id": session_id})
    while (view["running"] or view["state"] == "ready") and time.monotonic() < deadline:
        time.sleep(0.05)
        view = h.call("project.agent.get", {"handle": handle, "session_id": session_id})
    assert not view["running"] and view["state"] != "ready", view["events"][-3:]
    return view


def prepared_session(s, monitor):
    """The scripted planner freezes a plan for the first saved row; the desktop selected its Runtime target."""
    h, store, handle = s["h"], s["store"], s["handle"]
    gateway = h.bridge.projects.models
    gateway.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["qwen"])
    model = Model()
    gateway[ADAPTER] = model
    sid = str(uuid4())
    params = {"handle": handle, "session_id": sid}
    model.turns = [call("prepare_muferro_run", {"workflow_id": s["workflow"], "rows": [s["rows"][0]],
                    "expected_revision": store.info()["revision"]}), final("请读取完整计划，再批准开始运行。")]
    h.call("project.agent.create", {**params, "turn_id": str(uuid4()), "text": "运行已保存的第一个 MuFerro 算例。",
           "configuration": {"adapter": ADAPTER, "model": "qwen"}})
    h.call("project.agent.run_target", {**params, "simulation": {"connection": s["connection"],
                                                               "options": {"launcher": "none"}}})
    h.call("project.agent.start", params)
    view = wait(h, handle, sid)
    assert len(view["run_approvals"]) == 1 and len(view["awaiting"]) == 1
    item = view["run_approvals"][0]["item"]
    assert s["client"].tasks() == [] and monitor == ["WorkflowRuns.prepare"]
    assert not store.agent_sessions.objects(sid)
    sources = next(e["sources"] for e in view["events"] if e["kind"] == "tool_result")
    assert sources[0]["kind"] == "workflow_run" and sources[0]["label"] == "private"
    return sid, view, item


def count_starts(h, monkeypatch):
    """Every call to this bridge's workflow executor ``start``, forwarded unchanged."""
    starts = []
    start = h.bridge.workflow_executor.start

    def record_start(store, run_id, **kwargs):
        starts.append(run_id)
        return start(store, run_id, **kwargs)

    monkeypatch.setattr(h.bridge.workflow_executor, "start", record_start)
    return starts


def fresh_bridge(s, inproc, monkeypatch):
    """Orderly close, then a fresh strict bridge on the same state directory reopens the same project."""
    h, handle = s["h"], s["handle"]
    assert h.call("project.close", {"handle": handle})["closed"] is True
    h.close()
    h = inproc()
    h.bridge.analysis_executor.worker = s["worker"]
    h.bridge.workflow_executor.poll_seconds = 0.02
    starts = count_starts(h, monkeypatch)
    reopened = h.call("project.open", {"directory": str(s["store"].directory)})["project"]["handle"]
    assert reopened != handle
    s["h"], s["handle"] = h, reopened  # settled() follows the fresh bridge
    return h, reopened, starts


def lose_first_run_decide_result(h):
    """The bridge writes its first successful ``run_decide`` reply, still checked strictly; the desktop never
    receives it. One controlled drop: later lines are delivered unchanged."""
    lost, receive = {"done": threading.Event()}, h.receive

    def deliver(raw):
        message = _strict(raw)
        method = None if "event" in message else h.methods.get(message.get("id"))
        if method == "project.agent.run_decide" and "result" in message and not lost["done"].is_set():
            issues = bridge_schema.validate_outgoing(message, method) + second_opinion(message, method)
            if issues:
                h.violations.append((method, issues))
            lost["message"] = message
            lost["done"].set()
            return
        receive(raw)

    h.receive = deliver
    return lost


def started_events(store, run_id):
    """The run-level ``started`` events of the workflow run, read from the project file."""
    with store._connect() as db:
        _, events = store.workflow_runs._read(db, run_id)
    return [e for e in events if e["step"] == "" and e["status"] == "started"]


def test_agent_prepares_existing_case_then_human_first_start_runs_once(scan, monitor, inproc, monkeypatch):
    """Real Runtime and manufactured MuFerro, with scripted planner replies and strict bridge messages.

    The desktop bridge is closed in order and a fresh strict bridge reopens the same state, project and session
    before approval: the persisted plan and hashes survive, but the earlier process's inspection does not.
    """
    s = scan
    h, store, handle = s["h"], s["store"], s["handle"]
    sid, view, item = prepared_session(s, monitor)
    params = {"handle": handle, "session_id": sid}
    args = {**params, "item_id": item["item_id"]}
    decision = {**args, "decision": "start", "plan_sha256": item["plan_sha256"],
                "expected_revision": item["expected_revision"]}
    assert h.error("project.agent.run_decide", decision)["code"] == "conflict"
    plan = h.call("project.agent.run_plan", args)["run"]
    assert [r["id"] for r in plan["rows"]] == [s["rows"][0]]
    assert plan["simulation"]["connection"] == s["connection"] and s["client"].tasks() == []
    target = view["run_target"]
    assert target is not None

    # Cold reopen before approval: orderly close, then a fresh strict bridge on the same state directory.
    old_handle = handle
    h, handle, starts = fresh_bridge(s, inproc, monkeypatch)
    params = {"handle": handle, "session_id": sid}
    args = {**params, "item_id": item["item_id"]}
    decision = {**args, "decision": "start", "plan_sha256": item["plan_sha256"],
                "expected_revision": item["expected_revision"]}
    # The earlier handle is gone; its start is refused at this bridge's review gate before any project lookup.
    assert h.error("project.agent.get", {**params, "handle": old_handle})["code"] == "not_found"
    assert h.error("project.agent.run_decide", {**decision, "handle": old_handle})["code"] == "conflict"
    reopened = h.call("project.agent.get", params)
    assert [card["item"] for card in reopened["run_approvals"]] == [item]
    assert reopened["run_approvals"][0]["decision"] is None and reopened["run_approvals"][0]["receipt"] is None
    assert len(reopened["awaiting"]) == 1 and reopened["run_target"] == target
    assert h.call("project.agent.verify", params)["ok"]
    # Observing is not a review: the earlier process's inspection cannot authorize this bridge's start.
    assert h.call("project.agent.run_observe", args)["receipt"] == {"outcome": "pending", "item": item}
    refused = h.error("project.agent.run_decide", decision)
    assert refused["code"] == "conflict" and "Read the complete frozen run plan" in refused["message"]
    assert s["client"].tasks() == []
    assert h.call("project.agent.get", params)["run_approvals"][0]["decision"] is None
    reviewed = h.call("project.agent.run_plan", args)
    assert reviewed["item"] == item and reviewed["run"] == plan
    assert reviewed["run"]["plan_sha256"] == item["plan_sha256"] and s["client"].tasks() == []
    assert starts == []

    first = h.call("project.agent.run_decide", decision)
    assert first["receipt"]["outcome"] == "started"
    completed = settled(s, item["run_id"], timeout=90)
    assert all(t["status"] == "succeeded" for t in completed["tasks"])
    count = len(s["client"].tasks())
    assert count == 1 and len(s["worker"].files) == 1
    observed = h.call("project.agent.run_observe", args)["receipt"]
    assert observed["outcome"] == "started" and observed["run_id"] == item["run_id"]
    assert observed["approval"]["approval_id"] == item["item_id"]
    assert observed["approval"]["plan_sha256"] == item["plan_sha256"]
    replay = h.call("project.agent.run_decide", decision)
    assert replay["receipt"]["run_status"] == "stopped" and len(s["client"].tasks()) == count
    assert replay["receipt"]["outcome"] == "started" and replay["receipt"]["run_id"] == item["run_id"]
    assert replay["receipt"]["executor_id"] == observed["executor_id"]
    assert starts == [item["run_id"]]
    final_view = h.call("project.agent.get", params)
    assert final_view["awaiting"] == []
    decided = [e for e in final_view["events"] if e["kind"] == "approval_decided"]
    assert len(decided) == 1 and decided[0]["item_id"] == item["item_id"]
    assert h.call("project.agent.verify", params)["ok"]
    assert not h.violations


def test_lost_first_start_reply_is_observed_from_a_fresh_bridge_without_another_start(scan, monitor, inproc,
                                                                                      monkeypatch):
    """The reply to a genuine first start is lost (spec "Review, consumption and dispatch"). The desktop never sends
    the decision again: after an orderly close, a fresh strict bridge reopens the same project and session, and only
    an explicit ``run_observe`` reads the original historical receipt. Nothing starts or reaches the Runtime again."""
    s = scan
    h, store = s["h"], s["store"]
    sid, _, item = prepared_session(s, monitor)
    run_id = item["run_id"]
    args = {"handle": s["handle"], "session_id": sid, "item_id": item["item_id"]}
    assert h.call("project.agent.run_plan", args)["run"]["plan_sha256"] == item["plan_sha256"]
    starts = count_starts(h, monkeypatch)
    submissions = []
    submit = RuntimeClient.submit

    def record_submit(client, spec, idempotency_key=None):
        submissions.append(idempotency_key)
        return submit(client, spec, idempotency_key)

    monkeypatch.setattr(RuntimeClient, "submit", record_submit)
    lost = lose_first_run_decide_result(h)
    sent = h.request("project.agent.run_decide", {**args, "decision": "start", "plan_sha256": item["plan_sha256"],
                                                  "expected_revision": item["expected_revision"]})
    assert lost["done"].wait(60), "the bridge wrote no successful run_decide reply"
    # The bridge started the run and wrote its reply; the desktop received nothing and does not send it again.
    assert lost["message"]["id"] == sent and lost["message"]["result"]["receipt"]["outcome"] == "started"
    with h.cond:
        assert sent not in h.responses
    assert starts == [run_id]
    executor_id = h.bridge.workflow_executor.executor_id
    completed = settled(s, run_id, timeout=90)  # settled before closing: closing the project stops following
    assert all(t["status"] == "succeeded" for t in completed["tasks"])
    runtime_tasks = sorted(t["id"] for t in s["client"].tasks())
    assert len(runtime_tasks) == 1 and len(s["worker"].files) == 1
    original = started_events(store, run_id)
    assert len(original) == 1 and original[0]["executor_id"] == executor_id
    assert original[0]["approval"] == {"approval_id": item["item_id"], "plan_sha256": item["plan_sha256"],
                                       "request_sha256": item["request_sha256"],
                                       "expected_revision": item["expected_revision"]}

    h, handle, fresh_starts = fresh_bridge(s, inproc, monkeypatch)
    assert h.bridge.workflow_executor.executor_id != executor_id
    params = {"handle": handle, "session_id": sid}
    args = {**params, "item_id": item["item_id"]}
    reopened = h.call("project.agent.get", params)
    assert [card["item"] for card in reopened["run_approvals"]] == [item] and reopened["awaiting"] == []
    assert reopened["run_approvals"][0]["decision"]["decision"] == "start"
    receipt = h.call("project.agent.run_observe", args)["receipt"]
    assert receipt["outcome"] == "started" and receipt["ok"] is True
    assert receipt["item_id"] == item["item_id"] and receipt["run_id"] == run_id
    assert receipt["approval"] == original[0]["approval"] and receipt["executor_id"] == executor_id
    assert receipt["run_status"] == "stopped"  # the current workflow state, separate from the historical start
    # Observation started, recovered and submitted nothing.
    assert fresh_starts == [] and not h.bridge.workflow_executor.active(h.bridge.projects._stores[handle], run_id)
    assert len(submissions) == 1 and submissions[0]
    assert sorted(t["id"] for t in s["client"].tasks()) == runtime_tasks and len(s["worker"].files) == 1
    assert started_events(store, run_id) == original
    assert h.call("project.workflow_runs.get", {"handle": handle, "run_id": run_id})["run"]["status"] == "stopped"
    final_view = h.call("project.agent.get", params)
    decided = [e for e in final_view["events"] if e["kind"] == "approval_decided"]
    assert len(decided) == 1 and decided[0]["item_id"] == item["item_id"]
    assert final_view["run_approvals"][0]["receipt"]["run_status"] == "stopped"  # the observation is saved
    assert h.call("project.agent.verify", params)["ok"]
    assert monitor == ["WorkflowRuns.prepare"] and not h.violations


def test_the_agent_proposes_a_scan_a_person_runs_it_and_the_agent_analyses_the_results(scan, monitor):
    s = scan
    h, store, handle = s["h"], s["store"], s["handle"]
    gateway = h.bridge.projects.models
    gateway.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["qwen"])
    model = Model()
    gateway[ADAPTER] = model
    first = s["rows"][0]

    # 1. Propose: outline, capture the base row, try a tool that does not exist, propose the sweep, then stop.
    model.turns += [
        call("project_outline"),
        call("capture_rows", {"table_id": muferro.TABLE_ID, "record_ids": [first], "field_ids": [TEMPERATURE]}),
        lambda frozen: call("drafts_apply", {"draft_id": str(uuid4())}),
        lambda frozen: call("propose_sweep", {"context_id": json.loads(frozen["messages"][-3]["content"])["data"]["context_id"],
                                              "instruction": "Five temperatures from 300 K to 400 K, based on this case."}),
        final("I saved a draft of 5 new cases. Review and apply it, then run the new rows from the workflow editor."),
    ]

    def sweep(frozen_input):
        context = frozen_input["context"]
        return json.dumps({"format": "stk.parameter-sweep/1", "context_id": context["id"],
                           "base_revision": context["source_revision"], "summary": "Five temperatures.",
                           "base_record_id": first, "axes": [{"field_id": TEMPERATURE, "start": 300, "stop": 400, "count": 5}],
                           "mode": "product"})
    model.answers.append(sweep)
    revision = store.info()["revision"]
    route = h.call("project.agent.route", {"handle": handle})
    assert route["choice"]["endpoint"] == "laptop"
    session_id = str(uuid4())
    h.call("project.agent.create", {"handle": handle, "session_id": session_id, "turn_id": str(uuid4()),
                                    "text": "Scan the first case between 300 K and 400 K with 5 temperatures."})
    h.call("project.agent.start", {"handle": handle, "session_id": session_id})
    view = wait(h, handle, session_id)
    assert view["state"] == "awaiting" and view["stop_reason"] == "final"
    results = [json.loads(event["content"]) for event in view["events"] if event["kind"] == "tool_result"]
    assert [result["status"] for result in results] == ["ok", "ok", "error", "ok"]
    outline = results[0]["data"]
    cases = next(table for table in outline["tables"] if table["id"] == muferro.TABLE_ID)
    assert cases["role"] == "muferro_cases" and cases["rows"] == 2 and cases["label"] == "private"
    assert outline["workflows"][0]["steps"] == ["table", "simulation", "analysis"]
    assert results[2]["data"]["error"] == "There is no tool named drafts_apply"
    proposed = results[3]["data"]
    draft = store.drafts.get(proposed["draft_id"])
    assert draft["status"] == "pending" and proposed["new_rows"] == 5
    assert store.info()["revision"] == revision  # nothing applied
    assert s["client"].tasks() == []  # nothing submitted
    item = view["awaiting"][0]
    assert item["kind"] == "apply_draft" and item["draft_id"] == draft["id"]
    assert h.call("project.agent.verify", {"handle": handle, "session_id": session_id})["ok"]
    assert store.agent_sessions.object_owner("draft", draft["id"])["session_id"] == session_id
    assert monitor == []

    # A script cannot approve: the decision is the person's, on the desktop.
    scripts = h.call("script.catalog")["operations"]
    assert "project.agent.decide" not in scripts and "project.agent.start" in scripts

    # 2. A different draft, a stale card or an unknown item is a conflict; the person applies the one on the card.
    card = {"handle": handle, "session_id": session_id, "item_id": item["item_id"], "decision": "apply",
            "draft_sha256": item["draft_sha256"], "expected_revision": revision}
    for change, message in (({"draft_sha256": "0" * 64}, "not the one shown"), ({"expected_revision": revision + 1}, "changed"),
                            ({"item_id": "draft:" + str(uuid4())}, "not waiting")):
        error = h.error("project.agent.decide", {**card, **change})
        assert error["code"] == "conflict" and message in error["message"]
    assert h.error("project.agent.decide", {**card, "session_id": str(uuid4())})["code"] == "not_found"
    decided = h.call("project.agent.decide", {"handle": handle, "session_id": session_id, "item_id": item["item_id"],
                                              "decision": "apply", "draft_sha256": item["draft_sha256"],
                                              "expected_revision": revision})
    assert decided["receipt"] == {"ok": True, "applied_revision": revision + 1}
    view = h.call("project.agent.get", {"handle": handle, "session_id": session_id})
    decision = next(event for event in view["events"] if event["kind"] == "approval_decided")
    assert decision["by"]["authenticated"] is False and decision["decision"] == "apply"
    kinds = [event["kind"] for event in view["events"]]
    assert kinds.index("approval_decided") < kinds.index("approval_receipt")
    rows = [command["id"] for command in draft["commands"] if command["op"] == "add_record"]
    assert view["state"] == "awaiting" and view["awaiting"][0]["kind"] == "run_rows" and view["awaiting"][0]["rows"] == rows

    # 3. The person runs the 5 new rows.
    run = h.call("project.workflow_runs.prepare", {
        "handle": handle, "workflow_id": s["workflow"], "rows": rows, "run_id": str(uuid4()),
        "expected_revision": store.info()["revision"],
        "simulation": {"connection": s["connection"], "options": {"launcher": "none"}}})["run"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled(s, run["id"], timeout=300)  # five rows, one after another on the synthetic solver
    assert done["complete"], done["tasks"]
    after_run = store.info()["revision"]

    # 4. Analyse: the draft, its run, the results, a fit of energy against temperature, then a question.
    energy, temperature = muferro.RESULT_FIELD_IDS["energy"], muferro.RESULT_FIELD_IDS["temperature"]
    model.turns += [
        call("draft_status", {"draft_id": draft["id"]}),
        call("find_runs", {"draft_id": draft["id"]}),
        lambda frozen: call("capture_run_results", {"run_id": last_result(frozen)["runs"][0]["run_id"]}),
        lambda frozen: call("table_statistics", {"context_id": last_result(frozen)["context_id"], "fields": [energy],
                                                 "x_field": temperature, "fit": "linear"}),
        lambda frozen: call("ask_about_context", {"context_id": last_result(frozen)["context_id"],
                                                  "question": "What does the energy trend with temperature suggest?"}),
        final("Energy changes linearly with temperature across the 5 cases."),
    ]
    model.answers.append("The energy trend is smooth; no phase change appears in this range.")
    h.call("project.agent.say", {"handle": handle, "session_id": session_id, "turn_id": str(uuid4()),
                                 "text": "Analyse the results."})
    h.call("project.agent.start", {"handle": handle, "session_id": session_id})
    view = wait(h, handle, session_id)
    assert view["state"] == "idle" and view["stop_reason"] == "final", view["events"][-3:]
    observed = [event for event in view["events"] if event["kind"] == "observed"]
    assert [(event["facts"]["kind"], event["resolved"]) for event in observed] == [("decision", True), ("run_rows", True)]
    assert observed[0]["facts"]["decision"] == "apply" and observed[0]["facts"]["applied_revision"] == revision + 1
    observed = observed[1]
    assert observed["facts"]["runs"][0]["run_id"] == run["id"]
    assert observed["facts"]["runs"][0]["options"] == {"launcher": "none"}
    turn = [event for event in view["events"] if event["turn"] == 1]
    results = [json.loads(event["content"])["data"] for event in turn if event["kind"] == "tool_result"]
    status, found, captured, computed, answered = results
    assert status["status"] == "applied" and status["applied_revision"] == revision + 1
    assert found["runs"][0]["complete"] and sorted(found["runs"][0]["rows"]) == sorted(rows)
    assert len(captured["rows"]) == 5
    values = [(row[temperature], row[energy]) for row in captured["rows"]]
    mean = sum(value for _, value in values) / 5
    assert computed["fields"][energy]["mean"] == pytest.approx(mean) and computed["fit"]["n"] == 5
    assert answered["answer"].startswith("The energy trend")
    assert view["events"][-2]["text"].startswith("Energy changes linearly")
    # The planner saw what the person did before it answered.
    assert "stk_observations" in json.loads(model.sent[-6]["messages"][-1]["content"])
    report = h.call("project.agent.verify", {"handle": handle, "session_id": session_id})
    assert report["ok"], report["problems"]
    usage = view["usage"]
    assert usage["planner"]["turns"] == 11 and usage["requests"]["requests"] == 2
    assert usage["input_tokens"] == usage["planner"]["input_tokens"] + usage["requests"]["input_tokens"]
    assert store.info()["revision"] == after_run  # analysing changed nothing
    assert monitor == []
    assert not h.violations


def test_private_data_keeps_the_agent_and_its_requests_on_this_computer(scan, monitor):
    s = scan
    h, store, handle = s["h"], s["store"], s["handle"]
    gateway = h.bridge.projects.models
    # Only an external endpoint: no planner can be chosen (every table is private by default), nothing is sent.
    gateway.endpoints.add("cloud", "Cloud", "https://api.example.com/v1", ["big"], tier="large")
    gateway.keys.set("cloud", "abcdefghijklmnopqrstu")
    cloud = Model()
    gateway["openai-compatible/1:cloud"] = cloud
    route = h.call("project.agent.route", {"handle": handle})
    assert route["choice"] is None
    assert {item["reason"] for item in route["excluded"] if item["endpoint"] == "cloud"} == {"private_data"}
    error = h.error("project.agent.create", {"handle": handle, "session_id": str(uuid4()), "turn_id": str(uuid4()),
                                             "text": "Hello"})
    assert "No model on this computer" in error["message"]
    # With a local model added, the session plans there.
    gateway.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["qwen"])
    laptop = Model()
    gateway[ADAPTER] = laptop
    h.call("project.labels.set", {"handle": handle, "items": [{"kind": "table", "id": muferro.TABLE_ID}], "label": "public"})
    other = str(uuid4())
    store.apply([{"op": "create_table", "id": other, "name": "Notes"},
                 {"op": "add_field", "id": str(uuid4()), "table_id": other, "name": "x", "type": "number"}],
                expected_revision=store.info()["revision"])

    def plan_scan(model):
        model.turns += [
            call("project_outline"),
            call("capture_rows", {"table_id": muferro.TABLE_ID, "record_ids": [s["rows"][0]], "field_ids": [TEMPERATURE]}),
            lambda frozen: call("propose_sweep", {"context_id": last_result(frozen)["context_id"],
                                                  "instruction": "Three temperatures from 300 K to 350 K."}),
            final("Review the draft."),
        ]

    def sweep(frozen_input):
        context = frozen_input["context"]
        return json.dumps({"format": "stk.parameter-sweep/1", "context_id": context["id"],
                           "base_revision": context["source_revision"], "summary": "Three.", "base_record_id": s["rows"][0],
                           "axes": [{"field_id": TEMPERATURE, "start": 300, "stop": 350, "count": 3}], "mode": "product"})

    def ask(text):
        session_id = str(uuid4())
        h.call("project.agent.create", {"handle": handle, "session_id": session_id, "turn_id": str(uuid4()), "text": text})
        h.call("project.agent.start", {"handle": handle, "session_id": session_id})
        view = wait(h, handle, session_id)
        assert view["stop_reason"] == "final", view["events"][-3:]
        request_id = next(entry["id"] for entry in store.agent_sessions.objects(session_id) if entry["kind"] == "request")
        return view, store.requests.get(request_id)

    # A parameter proposal goes to the most capable model (the external one) only when everything the session read is
    # public. Here the outline read the private notes table's structure, so the proposal stays on this computer.
    plan_scan(laptop)
    laptop.answers.append(sweep)
    view, request = ask("Propose a scan of the first case.")
    assert request["configuration"]["adapter"] == ADAPTER and cloud.asked == [] and cloud.sent == []
    sources = [event for event in view["events"] if event["kind"] == "tool_result"][0]["sources"]
    assert {"kind": "table_structure", "id": other, "label": "private"} in sources
    # Once the notes table's structure is public too, the same proposal goes to the external model.
    h.call("project.labels.set", {"handle": handle, "items": [{"kind": "table", "id": other}], "label": "structure"})
    plan_scan(laptop)
    cloud.answers.append(sweep)
    view, request = ask("Propose a scan of the first case again.")
    assert request["configuration"]["adapter"] == "openai-compatible/1:cloud" and len(cloud.asked) == 1
    assert cloud.sent == []  # the planner itself never leaves this computer
    # Pinned to the external endpoint anyway, a request of this session is refused before it is made or sent.
    from suan.models.gateway import PolicyDenied
    with pytest.raises(PolicyDenied, match="read private data"):
        gateway.admit_sources({"adapter": "openai-compatible/1:cloud", "model": "big"},
                              all_public=tools.all_public(store, [{"kind": "table", "id": other}]))  # values stay private
    assert monitor == []
