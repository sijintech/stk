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
from suan.project.drafts import Drafts
from suan.project.labels import Labels
from suan.project.runs import Runs
from suan.project.store import ProjectStore
from suan.project.workflow_runs import WorkflowRuns
from suan.workflows import muferro
from test_bridge_workflow_muferro import scan, settled  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

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
