"""The agent harness (S2a, docs/design/agent-harness.md): planner turns with tools, every step recorded and checked.

The planner is scripted: an adapter installed in the model gateway returns prepared replies, so nothing reaches a model.
"""
import json
import threading
import time
from uuid import uuid4

import pytest

from suan.agent import AgentExecutor, audit, levels, tools, wire
from suan.models import ModelGateway
from suan.project import ProjectStore
from suan.project.agent_sessions import AgentSessions
from suan.project.aliyun import InvalidResponse
from suan.project.request_executor import ConfirmedCancellation, DefinitiveFailure
from suan.project.store import ProjectError
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

PLANNER = "test-planner/1"


class Planner:
    """A scripted planner: each send returns the next reply (a ModelTurn) or raises the next exception."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def prepare_turn(self, value):
        planner = self

        class Prepared:
            def send(self, frozen, cancel):
                planner.sent.append(frozen)
                reply = planner.replies.pop(0) if planner.replies else wire.ModelTurn("Done.", None, "stop")
                if callable(reply):
                    reply = reply(frozen, cancel)
                if isinstance(reply, BaseException):
                    raise reply
                return reply
        return Prepared()


def call(name, arguments=None, text=None):
    return wire.ModelTurn(text, {"id": None, "name": name, "arguments": arguments or {},
                                 "raw_arguments": json.dumps(arguments or {})}, "tool_calls",
                          {"input_tokens": 100, "output_tokens": 10})


@pytest.fixture
def project(tmp_path):
    """A parameter table: temperature (K) and energy (J), y = 2x + 1 on five rows."""
    store = ProjectStore.create(tmp_path / "project", "Agent")
    table, x, y = str(uuid4()), str(uuid4()), str(uuid4())
    rows = [str(uuid4()) for _ in range(5)]
    commands = [{"op": "create_table", "id": table, "name": "Cases"},
                {"op": "add_field", "id": x, "table_id": table, "name": "temperature", "type": "number", "unit": "K"},
                {"op": "add_field", "id": y, "table_id": table, "name": "energy", "type": "number", "unit": "J"}]
    for index, row in enumerate(rows):
        commands += [{"op": "add_record", "id": row, "table_id": table},
                     {"op": "set_cell", "table_id": table, "record_id": row, "field_id": x, "value": 300 + 10 * index},
                     {"op": "set_cell", "table_id": table, "record_id": row, "field_id": y, "value": 2 * (300 + 10 * index) + 1}]
    store.apply(commands, expected_revision=0)
    return store, {"table": table, "x": x, "y": y, "rows": rows}


def executor(planner, **options):
    gateway = ModelGateway()
    gateway[PLANNER] = planner
    return AgentExecutor(gateway, **options)


def session(agents, store, text="Analyse the energy against temperature."):
    session_id = str(uuid4())
    agents.create(store, session_id, text, turn_id=str(uuid4()), configuration={"adapter": PLANNER, "model": "m"})
    return session_id


def test_the_agent_outlines_captures_and_computes_then_answers_without_changing_the_project(project):
    store, ids = project
    revision = store.info()["revision"]
    planner = Planner(call("project_outline"),
                      lambda frozen, cancel: call("capture_rows", {"table_id": ids["table"]}),
                      None, None)

    def statistics(frozen, cancel):  # the context ID comes from the previous tool result, as a model would read it
        result = json.loads(frozen["messages"][-1]["content"])
        return call("table_statistics", {"context_id": result["data"]["context_id"], "fields": [ids["y"]],
                                         "x_field": ids["x"], "fit": "linear"})
    planner.replies[2] = statistics
    planner.replies[3] = wire.ModelTurn("Energy grows linearly: E = 2 T + 1 (R² = 1).", None, "stop", {"input_tokens": 5})
    agents = executor(planner)
    session_id = session(agents, store)
    view = agents.start(store, session_id, wait=True)
    kinds = [event["kind"] for event in view["events"]]
    assert kinds == ["user_turn"] + ["model_claimed", "model_completed", "tool_called", "tool_result"] * 3 + [
        "model_claimed", "model_completed", "stopped"]
    assert view["state"] == "idle" and view["stop_reason"] == "final"
    assert store.info()["revision"] == revision  # nothing the agent did is an edit
    results = [json.loads(event["content"]) for event in view["events"] if event["kind"] == "tool_result"]
    outline, captured, computed = (result["data"] for result in results)
    assert outline["tables"][0]["label"] == "private" and outline["tables"][0]["rows"] == 5
    assert "values" not in json.dumps(outline) and "301" not in json.dumps(outline)  # structure only, no values
    assert len(captured["rows"]) == 5
    fit = computed["fit"]
    assert fit["coefficients"] == pytest.approx([1.0, 2.0]) and fit["r2"] == pytest.approx(1.0)
    assert computed["fields"][ids["y"]]["n"] == 5 and computed["fields"][ids["y"]]["mean"] == pytest.approx(641.0)
    # The context the agent captured is registered as its own, and the session's sources are the table (and its outline).
    context_id = captured["context_id"]
    assert store.agent_sessions.object_owner("context", context_id)["session_id"] == session_id
    claims = [event for event in view["events"] if event["kind"] == "model_claimed"]
    assert claims[-1]["sources"] == [{"kind": "table_structure", "id": ids["table"]}, {"kind": "table", "id": ids["table"]}]
    # Each turn sent what the log rebuilds: the check recomputes inputs and the statistics.
    report = audit.verify(store, session_id)
    assert report["ok"] and report["planner_turns"] == 4, report["problems"]
    assert planner.sent[1]["messages"][-1]["role"] == "tool" and planner.sent[0]["tools"][0]["function"]["name"] == "project_outline"


def test_tool_errors_limits_and_unknown_tools_are_recorded_and_stop_the_turn(project):
    store, ids = project
    agents = executor(Planner(call("drafts_apply", {"draft_id": "x"}), call("capture_rows", {"table_id": "nope"}),
                              call("table_statistics", {"context_id": str(uuid4())})))
    view = agents.start(store, session(agents, store), wait=True)
    results = [json.loads(event["content"]) for event in view["events"] if event["kind"] == "tool_result"]
    assert results[0]["data"]["error"] == "There is no tool named drafts_apply"
    assert results[1]["data"]["error"] == "Invalid arguments"
    assert view["stop_reason"] == "error" and view["events"][-1]["code"] == "tool_errors"
    # At the limit the planner gets one last turn without tools, then the session stops for the limit.
    looping = executor(Planner(*[call("project_outline")] * 3, wire.ModelTurn("Summary so far.", None, "stop")),
                       limits={"model_turns_per_user_turn": 3})
    view = looping.start(store, session(looping, store), wait=True)
    claims = [event for event in view["events"] if event["kind"] == "model_claimed"]
    assert [claim["tool_choice"] for claim in claims] == ["auto", "auto", "auto", "none"]
    assert view["stop_reason"] == "limit"


def test_an_uncertain_turn_ends_the_session_and_is_never_resent(project):
    store, _ = project
    planner = Planner(RuntimeError("transport outcome is uncertain"))
    agents = executor(planner)
    session_id = session(agents, store)
    view = agents.start(store, session_id, wait=True)
    assert view["state"] == "ended" and view["stop_reason"] == "uncertain" and len(planner.sent) == 1
    settled = next(event for event in view["events"] if event["kind"] == "model_settled")
    assert settled["status"] == "uncertain" and settled["code"] == "transport_uncertain"
    assert agents.start(store, session_id, wait=True)["state"] == "ended" and len(planner.sent) == 1
    with pytest.raises(ProjectError, match="ended"):
        store.agent_sessions.say(session_id, "Try again", turn_id=str(uuid4()))
    # An invalid reply and a definite failure (with no other candidate) stop without ending the session.
    for failure, code in ((InvalidResponse("bad"), "response_invalid"), (DefinitiveFailure("refused"), "adapter_failed")):
        agents = executor(Planner(failure))
        view = agents.start(store, session(agents, store), wait=True)
        assert view["state"] == "idle" and view["stop_reason"] == "error" and view["events"][-1]["code"] == code


def test_cancelling_stops_the_current_turn_and_recovery_settles_a_lost_one(project):
    store, _ = project
    started = threading.Event()

    def wait_for_cancel(frozen, cancel):
        started.set()
        assert cancel.wait(10)
        return ConfirmedCancellation("stopped")
    agents = executor(Planner(wait_for_cancel))
    session_id = session(agents, store)
    agents.start(store, session_id)
    assert started.wait(10)
    agents.cancel(store, session_id)
    deadline = time.monotonic() + 10
    while agents.running(store, session_id) and time.monotonic() < deadline:
        time.sleep(0.02)
    view = store.agent_sessions.get(session_id)
    assert view["stop_reason"] == "cancelled" and "cancel_requested" in [event["kind"] for event in view["events"]]
    # A claim with no outcome (the service died while sending) becomes uncertain and ends the session, without resending.
    lost = session(agents, store)
    store.agent_sessions.append(lost, "model_claimed", {"call": 0, "configuration": {"adapter": PLANNER, "model": "m"},
                                                        "input_sha256": "0" * 64, "transcript_events": 1}, turn=0)
    view = agents.recover(store, lost)
    assert view["state"] == "ended" and [event["kind"] for event in view["events"]][-2:] == ["model_settled", "stopped"]
    assert view["events"][-2]["code"] == "executor_lost"


def test_the_planner_stays_on_this_computer_or_the_organizations_network(project, tmp_path):
    store, _ = project
    gateway = ModelGateway(tmp_path / "state")
    gateway.endpoints.add("cloud", "Cloud", "https://api.example.com/v1", ["big"])  # external
    agents = AgentExecutor(gateway)
    route = agents.route()
    assert route["choice"] is None and ("cloud", "private_data") in {(item["endpoint"], item["reason"]) for item in route["excluded"]}
    with pytest.raises(ProjectError, match="No model on this computer"):
        agents.create(store, str(uuid4()), "Hello", turn_id=str(uuid4()))
    # Pinned to the external endpoint anyway: refused before anything is claimed or sent.
    session_id = str(uuid4())
    agents.create(store, session_id, "Hello", turn_id=str(uuid4()),
                  configuration={"adapter": "openai-compatible/1:cloud", "model": "big"})
    view = agents.start(store, session_id, wait=True)
    assert "model_claimed" not in [event["kind"] for event in view["events"]] and view["stop_reason"] == "error"
    assert "organization's network" in view["events"][-1]["message"]
    # A local model served with a short context is not a planner candidate.
    gateway.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["small"])
    assert agents.route()["choice"]["endpoint"] == "laptop"


def test_a_definite_failure_moves_to_the_next_endpoint_the_session_showed(project, tmp_path):
    store, ids = project
    gateway = ModelGateway(tmp_path / "state")
    gateway.endpoints.add("a-gone", "A gone", "http://127.0.0.1:9/v1", ["m"])
    gateway.endpoints.add("b-live", "B live", "http://127.0.0.1:9/v1", ["m"])
    live = Planner(wire.ModelTurn("Answered by B.", None, "stop"))
    gateway["openai-compatible/1:a-gone"] = Planner(DefinitiveFailure("refused"))
    gateway["openai-compatible/1:b-live"] = live
    agents = AgentExecutor(gateway)
    session_id = str(uuid4())
    created = agents.create(store, session_id, "Hello", turn_id=str(uuid4()))
    assert created["session"]["configuration"]["adapter"] == "openai-compatible/1:a-gone"  # first in the frozen route
    view = agents.start(store, session_id, wait=True)
    assert view["stop_reason"] == "final" and live.sent
    policy = next(event for event in view["events"] if event["kind"] == "policy")
    assert policy["fallback"]["endpoint"] == "b-live"


def test_the_wire_accepts_one_tool_call_and_refuses_everything_else():
    def body(message, finish="tool_calls", choices=1):
        return json.dumps({"object": "chat.completion", "id": "chatcmpl-1", "model": "m", "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                           "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", **message}}] * choices}).encode()
    one = {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "project_outline", "arguments": "{}"}}]}
    turn = wire.turn_response(body(one))
    assert turn.tool_call["name"] == "project_outline" and turn.tool_call["arguments"] == {} and turn.metadata["input_tokens"] == 3
    assert wire.turn_response(body({"content": "Plain answer."}, "stop")).text == "Plain answer."
    two = {"content": None, "tool_calls": one["tool_calls"] * 2}
    as_object = {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "x", "arguments": {}}}]}
    for broken in (body(two), body(as_object), body({"content": "cut"}, "length"), body({"content": None}, "stop"),
                   body(one, choices=2), b"not json"):
        with pytest.raises(InvalidResponse):
            wire.turn_response(broken)


def test_every_scripting_operation_has_a_level_and_tools_stay_at_agent_levels():
    from suan.desktop_bridge.server import Bridge
    catalog = set(Bridge.script_catalog(Bridge.__new__(Bridge))["operations"])
    assert catalog == set(levels.OPERATIONS)
    assert not set(levels.DESKTOP_ONLY) & catalog
    for tool in tools.REGISTRY.values():
        assert tool.level in levels.AGENT_LEVELS and tool.name in levels.TOOL_USES
    for name, operations in levels.TOOL_USES.items():
        assert all(levels.OPERATIONS[operation][1] == "" for operation in operations), name
    assert all(level != "" for level, _ in levels.OPERATIONS.values())


def test_the_service_runs_agent_sessions_for_scripts_and_the_desktop(inproc, project):
    store, ids = project
    h = inproc()
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    planner = Planner(call("project_outline"), wire.ModelTurn("One table, Cases.", None, "stop"))
    h.bridge.projects.models[PLANNER] = planner
    assert {tool["name"] for tool in h.call("project.agent.tools", {"handle": handle})["tools"]} == {
        "project_outline", "capture_rows", "table_statistics"}
    session_id, turn_id = str(uuid4()), str(uuid4())
    created = h.call("project.agent.create", {"handle": handle, "session_id": session_id, "turn_id": turn_id,
                                              "text": "What is in this project?",
                                              "configuration": {"adapter": PLANNER, "model": "m"}})
    assert created["state"] == "ready" and not created["running"]
    h.call("project.agent.start", {"handle": handle, "session_id": session_id})
    deadline = time.monotonic() + 10
    view = h.call("project.agent.get", {"handle": handle, "session_id": session_id})
    while (view["running"] or view["state"] == "ready") and time.monotonic() < deadline:
        time.sleep(0.02)
        view = h.call("project.agent.get", {"handle": handle, "session_id": session_id})
    assert view["state"] == "idle" and view["stop_reason"] == "final"
    assert h.call("project.agent.verify", {"handle": handle, "session_id": session_id})["ok"]
    exported = h.call("project.agent.export", {"handle": handle, "session_id": session_id})
    assert exported["format"] == "stk.agent-log/1" and exported["chain_sha256"] == view["chain_sha256"]
    assert h.call("project.agent.list", {"handle": handle})["total"] == 1
    assert h.call("project.agent.objects", {"handle": handle, "kind": "draft", "object_id": str(uuid4())})["owner"] is None
    catalog = set(h.call("script.catalog")["operations"])
    assert "project.agent.start" in catalog and "project.agent.decide" not in catalog
    assert not h.violations


def test_a_planner_turn_on_an_openai_compatible_server_sends_tools_and_reads_one_call(project, tmp_path):
    """The real adapter against a local HTTP server: tools in the request, one call back, its result in the next turn."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import socketserver
    store, ids = project
    bodies = []
    replies = [{"content": None, "tool_calls": [{"id": "call-1", "type": "function",
                                                  "function": {"name": "project_outline", "arguments": "{}"}}]},
               {"content": "The project has one table, Cases."}]

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            message = replies[len(bodies) - 1]
            data = json.dumps({"object": "chat.completion", "id": f"r{len(bodies)}", "model": body["model"],
                               "choices": [{"index": 0, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                                            "message": {"role": "assistant", **message}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    class Server(ThreadingHTTPServer):
        def server_bind(self):
            socketserver.TCPServer.server_bind(self)
            self.server_name, self.server_port = self.server_address[:2]
    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        gateway = ModelGateway(tmp_path / "state")
        gateway.endpoints.add("laptop", "Laptop", f"http://127.0.0.1:{server.server_address[1]}/v1", ["qwen"])
        agents = AgentExecutor(gateway)
        session_id = str(uuid4())
        agents.create(store, session_id, "What is here?", turn_id=str(uuid4()))
        view = agents.start(store, session_id, wait=True)
    finally:
        server.shutdown()
        server.server_close()
    assert view["stop_reason"] == "final", view["events"][-1]
    first, second = bodies
    assert first["stream"] is False and first["parallel_tool_calls"] is False and first["tool_choice"] == "auto"
    assert [tool["function"]["name"] for tool in first["tools"]] == ["project_outline", "capture_rows", "table_statistics"]
    assert first["messages"][0]["role"] == "system" and json.loads(first["messages"][1]["content"]) == {"message": "What is here?"}
    # The call's ID in the conversation is the executor's (servers may repeat theirs); the server's is kept in the log.
    sent_id = second["messages"][-2]["tool_calls"][0]["id"]
    assert sent_id != "call-1" and second["messages"][-1] == {**second["messages"][-1], "role": "tool", "tool_call_id": sent_id}
    completed = next(event for event in store.agent_sessions.get(session_id)["events"] if event["kind"] == "model_completed")
    assert completed["tool_call"]["model_id"] == "call-1"
    assert json.loads(second["messages"][-1]["content"])["data"]["tables"][0]["name"] == "Cases"
    assert audit.verify(store, session_id)["ok"]


def roles_answered(messages):
    """Every tool call sent has its tool message right after it."""
    for index, message in enumerate(messages):
        for item in message.get("tool_calls", []):
            if messages[index + 1] != {**messages[index + 1], "role": "tool", "tool_call_id": item["id"]}:
                return False
    return True


def test_a_claim_left_open_by_a_lost_executor_is_never_sent_again(project):
    store, _ = project
    planner = Planner()
    agents = executor(planner)
    # Lost on the first message: starting again settles it as uncertain and ends the session, sending nothing.
    lost = session(agents, store)
    store.agent_sessions.append(lost, "model_claimed", {"call": 0, "configuration": {"adapter": PLANNER, "model": "m"},
                                                        "input_sha256": "0" * 64, "transcript_events": 1}, turn=0)
    view = agents.start(store, lost, wait=True)
    assert planner.sent == [] and view["state"] == "ended" and view["stop_reason"] == "interrupted"
    # Lost on a later message, after an answered one with the same call number: recovery still finds it.
    later = session(agents, store)
    assert agents.start(store, later, wait=True)["stop_reason"] == "final"
    store.agent_sessions.say(later, "And now?", turn_id=str(uuid4()))
    store.agent_sessions.append(later, "model_claimed", {"call": 0, "configuration": {"adapter": PLANNER, "model": "m"},
                                                         "input_sha256": "0" * 64, "transcript_events": 4}, turn=1)
    view = agents.recover(store, later)
    assert view["state"] == "ended" and view["events"][-2] == {**view["events"][-2], "kind": "model_settled", "turn": 1,
                                                               "code": "executor_lost"}
    assert len(planner.sent) == 1


def test_a_run_lost_between_steps_continues_with_new_call_numbers(project):
    store, ids = project
    agents = executor(Planner(call("project_outline"), wire.ModelTurn("Done.", None, "stop")))
    session_id = session(agents, store)
    # A run that died after a tool call was recorded (no result): the call gets an unknown result and the message is
    # answered by a new run whose planner turns continue the numbering.
    store.agent_sessions.append(session_id, "model_claimed", {"call": 0, "configuration": {"adapter": PLANNER, "model": "m"},
                                                              "input_sha256": "0" * 64, "transcript_events": 1}, turn=0)
    store.agent_sessions.append(session_id, "model_completed", {"call": 0, "text": None, "finish_reason": "tool_calls",
                                                                "tool_call": {"id": "lost", "name": "project_outline",
                                                                              "model_id": None, "raw_arguments": "{}"},
                                                                "metadata": {}}, turn=0)
    store.agent_sessions.append(session_id, "tool_called", {"call_id": "lost", "tool": "project_outline", "arguments": {}},
                                turn=0)
    view = agents.start(store, session_id, wait=True)
    assert view["stop_reason"] == "final"
    unknown = next(event for event in view["events"] if event["kind"] == "tool_result")
    assert unknown["call_id"] == "lost" and unknown["status"] == "unknown"
    assert [event["call"] for event in view["events"] if event["kind"] == "model_claimed"] == [0, 1, 2]
    assert roles_answered(wire.transcript(view["session"], view["events"]))


def test_a_tool_that_fails_or_overflows_still_records_a_result(project, monkeypatch):
    store, ids = project
    huge = str(uuid4())
    store.apply([{"op": "add_field", "id": huge, "table_id": ids["table"], "name": "huge", "type": "number", "unit": None}]
                + [{"op": "set_cell", "table_id": ids["table"], "record_id": row, "field_id": huge, "value": 1e300 * (index + 1)}
                   for index, row in enumerate(ids["rows"])], expected_revision=store.info()["revision"])
    planner = Planner(lambda frozen, cancel: call("capture_rows", {"table_id": ids["table"]}), None,
                      call("project_outline"), wire.ModelTurn("Done.", None, "stop"))

    def statistics(frozen, cancel):
        context = json.loads(frozen["messages"][-1]["content"])["data"]["context_id"]
        return call("table_statistics", {"context_id": context, "fields": [huge]})
    planner.replies[1] = statistics
    agents = executor(planner)
    original = tools.REGISTRY["project_outline"]
    broken = tools.Tool(original.name, original.version, original.description, original.parameters,
                        lambda context, arguments: 1 / 0, original.annotations)
    monkeypatch.setitem(tools.REGISTRY, "project_outline", broken)
    session_id = session(agents, store)
    view = agents.start(store, session_id, wait=True)
    assert view["stop_reason"] == "final"
    results = [json.loads(event["content"]) for event in view["events"] if event["kind"] == "tool_result"]
    assert results[1]["status"] == "ok" and results[1]["data"]["fields"][huge]["reason"] == "overflow"
    assert results[2] == {**results[2], "status": "error", "data": {"error": "The tool failed (ZeroDivisionError)"}}
    store.agent_sessions.say(session_id, "Thanks.", turn_id=str(uuid4()))
    assert roles_answered(wire.transcript(view["session"], store.agent_sessions.get(session_id)["events"]))


def test_a_reply_too_large_to_record_or_a_tool_call_at_the_limit_keeps_the_log_sendable(project):
    store, _ = project
    # Control characters take six bytes each once recorded: the reply is refused, and its claim settled.
    agents = executor(Planner(wire.ModelTurn("\x01" * 15000, None, "stop")))
    view = agents.start(store, session(agents, store), wait=True)
    assert [event["kind"] for event in view["events"]][-3:] == ["model_claimed", "model_settled", "stopped"]
    assert view["events"][-2]["code"] == "response_invalid" and view["state"] == "idle"
    # The summary turn at the limit has no tools; a tool call it returns anyway is not run and not sent back.
    agents = executor(Planner(call("project_outline"), call("project_outline", text="Summary.")),
                      limits={"model_turns_per_user_turn": 1})
    session_id = session(agents, store)
    view = agents.start(store, session_id, wait=True)
    assert view["stop_reason"] == "limit" and [event["kind"] for event in view["events"]].count("tool_called") == 1
    store.agent_sessions.say(session_id, "Go on.", turn_id=str(uuid4()))
    messages = wire.transcript(view["session"], store.agent_sessions.get(session_id)["events"])
    assert roles_answered(messages) and messages[-2] == {"role": "assistant", "content": "Summary."}


def test_repeated_model_call_ids_still_make_distinct_objects_and_are_checked(project):
    store, ids = project

    def same_id(turn):
        return wire.ModelTurn(None, {**turn.tool_call, "id": "call_0"}, "tool_calls", {})
    planner = Planner(same_id(call("capture_rows", {"table_id": ids["table"], "record_ids": ids["rows"][:2]})),
                      same_id(call("capture_rows", {"table_id": ids["table"], "record_ids": ids["rows"][2:]})), None)

    def statistics(frozen, cancel):
        context = json.loads(frozen["messages"][-1]["content"])["data"]["context_id"]
        return same_id(call("table_statistics", {"context_id": context}))
    planner.replies[2] = statistics
    agents = executor(planner)
    session_id = session(agents, store)
    view = agents.start(store, session_id, wait=True)
    results = [json.loads(event["content"]) for event in view["events"] if event["kind"] == "tool_result"]
    assert [result["status"] for result in results] == ["ok", "ok", "ok"]
    assert results[0]["data"]["context_id"] != results[1]["data"]["context_id"]
    assert audit.verify(store, session_id)["ok"]
    # The audit recomputes the statistics of the call each result belongs to: a different result is found.
    original = tools.REGISTRY["table_statistics"]
    changed = tools.Tool(original.name, original.version, original.description, original.parameters,
                         lambda context, arguments: tools.ToolResult("ok", {"rows": -1}), original.annotations)
    tools.REGISTRY["table_statistics"] = changed
    try:
        problems = audit.verify(store, session_id)["problems"]
    finally:
        tools.REGISTRY["table_statistics"] = original
    assert len(problems) == 1 and "Recomputing table_statistics" in problems[0]


def test_tool_results_record_the_label_their_data_had(project):
    store, ids = project
    agents = executor(Planner(call("capture_rows", {"table_id": ids["table"]})))
    session_id = session(agents, store)
    view = agents.start(store, session_id, wait=True)
    result = next(event for event in view["events"] if event["kind"] == "tool_result")
    assert result["sources"] == [{"kind": "table", "id": ids["table"], "label": "private"}]
    store.labels.set([{"kind": "table", "id": ids["table"]}], label="public")
    result = next(event for event in store.agent_sessions.get(session_id)["events"] if event["kind"] == "tool_result")
    assert result["sources"][0]["label"] == "private"  # the log keeps the label at the time


def test_creating_again_returns_the_session_whatever_the_route_says_now(project, tmp_path):
    store, _ = project
    gateway = ModelGateway(tmp_path / "state")
    gateway.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["m"])
    agents = AgentExecutor(gateway)
    session_id, turn_id = str(uuid4()), str(uuid4())
    first = agents.create(store, session_id, "Hello", turn_id=turn_id)
    gateway.endpoints.remove("laptop")
    assert agents.create(store, session_id, "Hello", turn_id=turn_id)["chain_sha256"] == first["chain_sha256"]
    with pytest.raises(Exception, match="already used"):
        agents.create(store, session_id, "Other", turn_id=turn_id)


def test_a_message_sent_as_the_previous_run_finishes_is_answered(project, monkeypatch):
    store, _ = project
    stopped, release = threading.Event(), threading.Event()
    agents = executor(Planner(wire.ModelTurn("First.", None, "stop"), wire.ModelTurn("Second.", None, "stop")))
    session_id = session(agents, store)
    sessions = store.agent_sessions
    append = AgentSessions.append

    def held(self, session_id_, kind, payload, **options):  # the first run stops, then pauses before it is gone
        event_id = append(self, session_id_, kind, payload, **options)
        if kind == "stopped" and not stopped.is_set():
            stopped.set()
            release.wait(10)
        return event_id
    monkeypatch.setattr(AgentSessions, "append", held)
    agents.start(store, session_id)
    assert stopped.wait(10) and agents.running(store, session_id)
    sessions.say(session_id, "Again.", turn_id=str(uuid4()))
    threading.Timer(0.2, release.set).start()
    view = agents.start(store, session_id, wait=True)  # waits for the finishing run, then answers
    assert view["state"] == "idle" and view["events"][-2]["text"] == "Second."


def test_long_sessions_are_read_in_pages(project):
    store, _ = project
    agents = executor(Planner())
    session_id = session(agents, store)
    for _ in range(1001):
        store.agent_sessions.append(session_id, "policy", {"note": "x"}, turn=0)
    view = store.agent_sessions.get(session_id)
    assert view["total"] == 1002 and len(view["events"]) == 1000 and view["events"][-1]["id"] == view["total"] + view["events"][0]["id"] - 3
    assert len(store.agent_sessions.get(session_id, offset=0, limit=5)["events"]) == 5
    assert store.agent_sessions.get(session_id, offset=1000)["events"][0]["kind"] == "policy"


def test_malformed_tool_calls_are_invalid_replies_not_uncertain_ones():
    raw = json.dumps({"object": "chat.completion", "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [{"id": "a", "type": "function", "function": "x"}]}}]}).encode()
    with pytest.raises(InvalidResponse):
        wire.turn_response(raw)


def test_the_service_names_agent_limits_and_checks_handles(inproc, project):
    store, _ = project
    h = inproc()
    assert h.error("project.agent.tools", {"handle": "0" * 32})["code"] == "not_found"
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    started, release = threading.Event(), threading.Event()

    def hold(frozen, cancel):
        started.set()
        release.wait(10)
        return wire.ModelTurn("Done.", None, "stop")
    h.bridge.projects.models[PLANNER] = Planner(hold, hold)
    ids = []
    for _ in range(2):
        ids.append(str(uuid4()))
        h.call("project.agent.create", {"handle": handle, "session_id": ids[-1], "turn_id": str(uuid4()), "text": "Hi",
                                        "configuration": {"adapter": PLANNER, "model": "m"}})
    h.call("project.agent.start", {"handle": handle, "session_id": ids[0]})
    try:
        assert started.wait(10)
        error = h.error("project.agent.start", {"handle": handle, "session_id": ids[1]})
        assert error["code"] == "busy" and "agent session" in error["message"]
    finally:
        release.set()
