"""The agent's MuFerro acceptance (docs/design/agent-harness.md, "验收演示"): a real local Runtime with the synthetic
solver, a scripted planner and scripted answers to the session's own requests; nothing reaches a real model.

The agent proposes a sweep as a draft and stops; a person applies it on the session's card and runs the new rows; the
agent then analyses the results. The agent's thread never applies, prepares, starts, submits or labels anything.
"""
import hashlib
import json
import signal
import sys
import textwrap
import threading
import time
from pathlib import Path
from uuid import uuid4

import psutil
import pytest

from suan.agent import tools, wire
from suan.desktop_bridge import schema as bridge_schema
from suan.project.drafts import Drafts
from suan.project.labels import Labels
from suan.project.runs import Runs
from suan.project.store import ProjectStore
from suan.project.workflow_runs import WorkflowRuns
from suan.runtime.client import RuntimeClient
from suan.runtime.models import TERMINAL
from suan.workflows import muferro
from mupro_fake import _script, read_toml, write_outputs
from test_bridge_workflow_muferro import scan, settled  # noqa: F401
from test_desktop_bridge import ProcessBridge, _strict, bridge_env, inproc, second_opinion  # noqa: F401

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


# The stock strict stdio bridge (``python -m suan.desktop_bridge --stdio --strict``) with test-only hooks, run as its
# own Python process: an optional scripted planner on "this computer", a refusing (or recorded stock) analysis worker,
# an append-only record of this process's identity and of every start/recover/cancel/decide/analysis entry point, and
# optionally one withheld reply.
PROBE_BRIDGE = textwrap.dedent('''
    import json, os, sys, threading
    from pathlib import Path

    control = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    record_lock = threading.Lock()

    def record(name, value=None):
        with record_lock, open(control["record"], "a", encoding="utf-8") as out:
            out.write(json.dumps({"pid": os.getpid(), "name": name, "value": value}) + "\\n")
            out.flush()
            os.fsync(out.fileno())

    from suan.agent import wire
    from suan.agent.executor import AgentExecutor
    from suan.desktop_bridge import __main__ as entry, server
    from suan.desktop_bridge.workflow_runs import WorkflowRunExecutor
    from suan.project.workflow_runs import WorkflowRuns

    for owner, name in ((AgentExecutor, "decide_run"), (AgentExecutor, "recover"), (WorkflowRunExecutor, "start"),
                        (WorkflowRunExecutor, "recover"), (WorkflowRunExecutor, "cancel"), (WorkflowRuns, "start"),
                        (WorkflowRuns, "interrupt"), (WorkflowRuns, "request_cancel")):
        def watched(*args, _original=getattr(owner, name), _name=owner.__name__ + "." + name, **kwargs):
            record("call", _name)
            return _original(*args, **kwargs)
        setattr(owner, name, watched)

    class Planner:
        """Scripted planner turns; the probe makes no model requests."""
        def __init__(self, turns):
            self.turns = turns

        def prepare_turn(self, value):
            planner = self

            class Prepared:
                def send(self, frozen, cancel):
                    record("planner_turn")
                    return planner.turns.pop(0)
            return Prepared()

        def send(self, frozen, cancel):
            raise AssertionError("the probe sends no model request")

    class NoAnalysis:
        def evaluate(self, identity, work, cancel, events):
            record("call", "analysis")
            raise AssertionError("the probe runs no analysis")

    local = threading.local()

    class Withholding:
        """Drops the one line written while this thread withholds; every other line is written unchanged."""
        def __init__(self, writer):
            self.writer = writer

        def write(self, data):
            if getattr(local, "withhold", False):
                local.line = bytes(data)
                return len(data)
            return self.writer.write(data)

        def flush(self):
            if not getattr(local, "withhold", False):
                self.writer.flush()

    class ProbeBridge(server.Bridge):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.workflow_executor.poll_seconds = 0.02
            if control.get("real_analysis"):
                worker = self.analysis_executor.worker  # the stock GraphWorker; each evaluation is recorded
                evaluate = worker.evaluate

                def recorded(*args, **kwargs):
                    record("call", "analysis")
                    result = evaluate(*args, **kwargs)
                    import psutil
                    child = worker._child
                    process = None if child is None else psutil.Process(child.process.pid)
                    record("graph_worker", {"command": worker.command[1:3],
                                            "pid": None if process is None else process.pid,
                                            "parent": None if process is None else process.ppid(),
                                            "created_at": None if process is None else process.create_time()})
                    return result
                worker.evaluate = recorded
            else:
                self.analysis_executor.worker = NoAnalysis()
            self.withheld = threading.Event()
            if control["prepare"] is not None:
                usage = {"input_tokens": 100, "output_tokens": 20}
                arguments = control["prepare"]
                gateway = self.projects.models
                gateway.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["qwen"])
                gateway[control["adapter"]] = Planner([
                    wire.ModelTurn(None, {"id": None, "name": "prepare_muferro_run", "arguments": arguments,
                                          "raw_arguments": json.dumps(arguments)}, "tool_calls", usage),
                    wire.ModelTurn("Read the complete plan before approving.", None, "stop", usage)])
            if control["withhold"]:
                self.writer = Withholding(self.writer)
            record("identity", {"executor_id": self.workflow_executor.executor_id})

        def send(self, message, method=None):
            if not (control["withhold"] and method == "project.agent.run_decide" and "result" in message
                    and not self.withheld.is_set()):
                return super().send(message, method)
            self.withheld.set()
            local.withhold = True
            try:
                written = super().send(message, method)  # still validated strictly, never reaches stdout
            finally:
                local.withhold = False
            record("withheld", {"id": message["id"], "written": written, "line": json.loads(local.line)})
            return written

    server.Bridge = ProbeBridge
    entry.main(sys.argv[2:])
''')


def reap(bridge):
    """Force-reap a probe process that is still alive and close its pipes (idempotent; runs after any failure)."""
    if bridge.process.poll() is None:
        bridge.process.kill()
    bridge.process.wait(timeout=30)
    bridge.reader.join(timeout=5)
    for pipe in (bridge.process.stdin, bridge.process.stdout, bridge.stderr):
        try:
            pipe.close()
        except OSError:
            pass


def probe_bridge(request, s, state, name, *, prepare=None, withhold=False, real_analysis=False):
    """A strict desktop bridge in its own Python process (see ``PROBE_BRIDGE``) on ``state``, reaped at teardown,
    after a strict ``hello`` from the real child that resumed no transfers. Analyses are refused unless
    ``real_analysis``, which keeps the stock graph worker."""
    script, control = s["tmp"] / "probe_bridge.py", s["tmp"] / f"{name}.json"
    script.write_text(PROBE_BRIDGE, encoding="utf-8")
    control.write_text(json.dumps({"record": str(s["tmp"] / "probe-records.jsonl"), "adapter": ADAPTER,
                                   "prepare": prepare, "withhold": withhold, "real_analysis": real_analysis}),
                       encoding="utf-8")
    bridge = ProcessBridge(state, argv=[sys.executable, str(script), str(control), "--stdio", "--strict",
                                        "--state-dir", str(state)], stderr_path=s["tmp"] / f"{name}.err")
    request.addfinalizer(lambda: reap(bridge))
    hello = bridge.call("hello", {"protocol": 1})
    assert hello["protocol"] == 1 and hello["server"]["pid"] == bridge.process.pid
    assert "project.agent.run_observe" in hello["methods"] and hello["resumed_transfers"] == []
    return bridge


def probe_records(s, pid):
    """The complete records of process ``pid``; a line still being appended is not read."""
    path = s["tmp"] / "probe-records.jsonl"
    data = path.read_bytes() if path.exists() else b""
    lines = data[:data.rfind(b"\n") + 1].decode("utf-8").splitlines()
    return [r for r in map(json.loads, lines) if r["pid"] == pid]


def until_true(condition, timeout, what):
    deadline = time.monotonic() + timeout
    while True:
        value = condition()
        if value:
            return value
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.05)


def first_dispatch_killed(s, runtime, monkeypatch, request, held):
    """A genuine first human start in a strict probe bridge process, killed (SIGKILL) once its single Runtime task is
    recorded on the run, the start's approval is durable, its reply was withheld from the desktop and ``held(task)``
    returns evidence for the current Runtime task (it is polled until then and may advance the Runtime). Returns what
    the test observed at the interruption, including Runtime ``submissions`` and ``cancels`` recorded from here on."""
    monkeypatch.setenv("STK_TOKEN_PLAN_API_KEY", "")
    monkeypatch.delenv("STK_TOKEN_PLAN_MODEL", raising=False)
    store, client, server = s["store"], s["client"], runtime[2]
    # The in-process bridge only built the project and the Runtime profile; the desktop processes use them from here.
    assert s["h"].call("project.close", {"handle": s["handle"]})["closed"] is True
    s["h"].close()
    submissions, cancels = [], []
    submit, cancel = server.service.submit, server.service.cancel

    def record_submit(spec, key):
        submissions.append(key)
        return submit(spec, key)

    def record_cancel(task_id):
        cancels.append(task_id)
        return cancel(task_id)
    monkeypatch.setattr(server.service, "submit", record_submit)
    monkeypatch.setattr(server.service, "cancel", record_cancel)
    state = s["tmp"] / "desktop-state"
    prepare = {"workflow_id": s["workflow"], "rows": [s["rows"][0]], "expected_revision": store.info()["revision"]}

    first = probe_bridge(request, s, state, "first", prepare=prepare, withhold=True)
    first_pid = first.process.pid
    handle = first.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    sid = str(uuid4())
    params = {"handle": handle, "session_id": sid}
    first.call("project.agent.create", {**params, "turn_id": str(uuid4()), "text": "运行已保存的第一个 MuFerro 算例。",
                                        "configuration": {"adapter": ADAPTER, "model": "qwen"}})
    first.call("project.agent.run_target", {**params, "simulation": {"connection": s["connection"],
                                                                   "options": {"launcher": "none"}}})
    first.call("project.agent.start", params)
    view = wait(first, handle, sid)
    assert len(view["run_approvals"]) == 1 and len(view["awaiting"]) == 1
    item = view["run_approvals"][0]["item"]
    run_id = item["run_id"]
    envelope = {key: item[key] for key in ("plan_sha256", "request_sha256", "expected_revision")}
    envelope["approval_id"] = item["item_id"]
    args = {**params, "item_id": item["item_id"]}
    assert first.call("project.agent.run_plan", args)["run"]["plan_sha256"] == item["plan_sha256"]
    assert client.tasks() == [] and submissions == [] and started_events(store, run_id) == []
    sent = first.request("project.agent.run_decide", {**args, "decision": "start", "plan_sha256": item["plan_sha256"],
                                                      "expected_revision": item["expected_revision"]})

    def boundary():
        """Exactly one held Runtime task, recorded on the run, and one durable started event; the reply withheld."""
        withheld = [r["value"] for r in probe_records(s, first_pid) if r["name"] == "withheld"]
        current = client.tasks()
        run = store.workflow_runs.get(run_id)
        progress = next(t for t in run["tasks"] if t["step"] == "simulate")["progress"]
        if not (withheld and len(current) == 1 and progress and progress.get("task_id") == current[0]["id"]):
            return None
        evidence = held(current[0])
        if not evidence:
            return None
        return withheld, client.tasks(), store.workflow_runs.get(run_id), started_events(store, run_id), evidence

    withheld, interrupted_tasks, run, started, evidence = until_true(boundary, 60,
                                                                     "the first dispatch and its held Runtime task")
    assert len(interrupted_tasks) == 1 and held(interrupted_tasks[0]) == evidence
    assert len(started) == 1 and started[0]["approval"] == envelope
    assert run["owner"]["pid"] == first_pid and run["status"] == "running"
    with first.cond:
        assert sent not in first.responses  # the desktop never received the decision reply
    first.kill()  # SIGKILL: no orderly close, shutdown or flush
    assert first.process.returncode == -signal.SIGKILL and not psutil.pid_exists(first_pid)
    with first.cond:
        assert sent not in first.responses
    assert not first.violations, first.violations
    identity = next(r["value"] for r in probe_records(s, first_pid) if r["name"] == "identity")
    first_calls = [r["value"] for r in probe_records(s, first_pid) if r["name"] == "call"]
    assert first_calls.count("AgentExecutor.decide_run") == 1 and first_calls.count("WorkflowRuns.start") == 1
    assert "analysis" not in first_calls
    assert not any(c.endswith(("recover", "cancel", "interrupt")) for c in first_calls)
    reply = withheld[0]["line"]
    assert withheld[0]["id"] == sent and withheld[0]["written"] is True and len(withheld) == 1
    assert reply["result"]["receipt"]["outcome"] == "started" and reply["result"]["receipt"]["run_id"] == run_id
    assert reply["result"]["receipt"]["executor_id"] == identity["executor_id"]
    # The durable identity at the interruption: one start by the killed process, with the person's exact approval.
    assert started[0]["executor_id"] == identity["executor_id"] == run["executor_id"]
    assert len(submissions) == 1 and submissions[0] and cancels == []
    with store._connect() as db:
        _, run_events = store.workflow_runs._read(db, run_id)
    at_interruption = store.workflow_runs.get(run_id)["status"]
    return {"state": state, "first": first, "first_pid": first_pid, "sid": sid, "item": item, "run_id": run_id,
            "envelope": envelope, "identity": identity, "first_calls": first_calls, "reply": reply,
            "interrupted_tasks": interrupted_tasks, "run": run, "started": started, "evidence": evidence,
            "run_events": run_events, "at_interruption": at_interruption, "submissions": submissions,
            "cancels": cancels}


def test_killed_bridge_process_after_first_dispatch_is_only_observed_by_a_fresh_process(
        scan, runtime, monkeypatch, request):
    """A genuine first human start in a strict bridge process, which is killed (SIGKILL) once its single Runtime task
    is queued and the start's approval is durable, before the desktop receives the decision reply (spec "Review,
    consumption and dispatch"). The Runtime scheduler is held and no worker starts, so at the interruption the task
    is queued in the Runtime and the workflow run is running. A fresh bridge process on the same state directory
    reopens the project; an explicit ``run_observe`` reads the original approval, run and executor and the current
    workflow status, and nothing decides, starts, recovers, cancels or submits again."""
    s = scan
    store, client = s["store"], s["client"]
    k = first_dispatch_killed(s, runtime, monkeypatch, request, lambda task: task["state"] == "queued")
    state, first, first_pid, sid, item, run_id = (k[key] for key in ("state", "first", "first_pid", "sid", "item",
                                                                      "run_id"))
    envelope, identity, first_calls, reply = k["envelope"], k["identity"], k["first_calls"], k["reply"]
    interrupted_tasks, started, run_events, at_interruption = (k[key] for key in (
        "interrupted_tasks", "started", "run_events", "at_interruption"))
    submissions, cancels = k["submissions"], k["cancels"]

    fresh = probe_bridge(request, s, state, "fresh")
    fresh_pid = fresh.process.pid
    assert fresh_pid != first_pid
    handle = fresh.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    params = {"handle": handle, "session_id": sid}
    args = {**params, "item_id": item["item_id"]}
    reopened = fresh.call("project.agent.get", params)
    assert [card["item"] for card in reopened["run_approvals"]] == [item] and reopened["awaiting"] == []
    assert reopened["run_approvals"][0]["decision"]["decision"] == "start"
    receipt = fresh.call("project.agent.run_observe", args)["receipt"]
    current = fresh.call("project.workflow_runs.get", {"handle": handle, "run_id": run_id})["run"]
    assert receipt["outcome"] == "started" and receipt["ok"] is True
    assert receipt["item_id"] == item["item_id"] and receipt["run_id"] == run_id
    assert receipt["approval"] == envelope and receipt["executor_id"] == identity["executor_id"]
    assert receipt["run_status"] == current["status"] == at_interruption  # current state, not a historical one
    assert current["executor_id"] == identity["executor_id"] and current["owner"]["pid"] == first_pid
    assert fresh.call("project.agent.verify", params)["ok"]
    final_view = fresh.call("project.agent.get", params)
    assert [e["item_id"] for e in final_view["events"] if e["kind"] == "approval_decided"] == [item["item_id"]]
    saved = final_view["run_approvals"][0]["receipt"]  # the observation is saved; no other execution evidence
    assert saved["outcome"] == "started" and saved["run_status"] == receipt["run_status"]
    assert fresh.close() == 0  # orderly close of the fresh process, strict messages clean

    fresh_records = probe_records(s, fresh_pid)
    fresh_identity = next(r["value"] for r in fresh_records if r["name"] == "identity")
    assert fresh_identity["executor_id"] != identity["executor_id"]
    assert [r for r in fresh_records if r["name"] != "identity"] == []  # nothing decided, started, recovered, cancelled
    # The Runtime saw exactly one submission and no cancel; its task is unchanged; the run's history is unchanged.
    assert len(submissions) == 1 and cancels == []
    assert [(t["id"], t["state"]) for t in client.tasks()] == [(interrupted_tasks[0]["id"], "queued")]
    with store._connect() as db:
        _, after = store.workflow_runs._read(db, run_id)
    assert after == run_events and started_events(store, run_id) == started
    (s["tmp"] / "probe-summary.json").write_text(json.dumps({
        "first_pid": first_pid, "first_returncode": first.process.returncode, "fresh_pid": fresh_pid,
        "first_executor_id": identity["executor_id"], "fresh_executor_id": fresh_identity["executor_id"],
        "run_id": run_id, "item_id": item["item_id"], "runtime_task": interrupted_tasks[0]["id"],
        "runtime_state_at_interruption": interrupted_tasks[0]["state"], "run_status_at_interruption": at_interruption,
        "withheld_reply_outcome": reply["result"]["receipt"]["outcome"], "observe": receipt,
        "runtime_submissions": len(submissions), "runtime_cancels": len(cancels), "first_calls": first_calls,
        "fresh_calls": [r["value"] for r in fresh_records if r["name"] == "call"]}, indent=2), encoding="utf-8")


# The synthetic solver behind a test-owned gate: it announces itself, waits for the release file (bounded, so a failed
# test cannot hang the Runtime fixture's teardown), then writes the usual manufactured MuFerro outputs.
GATED_SOLVER = textwrap.dedent('''
    import json, os, sys, time
    from pathlib import Path
    import psutil

    held, release = Path({held!r}), Path({release!r})
    process = psutil.Process()
    pending = held.with_suffix(".tmp")
    with pending.open("x", encoding="utf-8") as stream:
        json.dump({{"pid": process.pid, "created_at": process.create_time(), "cwd": os.getcwd()}}, stream)
    os.link(pending, held)  # Publish a complete identity that another solver cannot replace.
    deadline = time.monotonic() + 120
    while not release.exists():
        if time.monotonic() > deadline:
            print("gated fake muFerro: never released", file=sys.stderr, flush=True)
            sys.exit(3)
        time.sleep(0.02)
    sys.path.insert(0, {tests!r})
    from mupro_fake import fake_muferro
    sys.exit(fake_muferro("ok"))
''')


def solver_alive(identity):
    """Whether the held solver ``{pid, created_at}`` is still that exact live process (a reused PID is not)."""
    try:
        process = psutil.Process(identity["pid"])
        return process.create_time() == identity["created_at"] and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def held_solver_killed(s, runtime, monkeypatch, request):
    """``first_dispatch_killed`` while the Runtime already runs the synthetic solver, held at a test-owned gate: the
    held solver is this task's and outlived the bridge. Adds the gate, the held solver's identity, the Runtime task and
    the killed process's stored run at the interruption."""
    store, client, supervisor = s["store"], s["client"], s["supervisor"]
    gate = s["tmp"] / "solver-gate"
    gate.mkdir()
    marker, release = gate / "held.json", gate / "release"
    _script(s["tmp"] / "fake-sdk" / "bin" / "muFerro", GATED_SOLVER.format(
        held=str(marker), release=str(release), tests=str(Path(__file__).parent)))
    request.addfinalizer(release.touch)  # never leave the solver held, whatever fails

    def solver_running(task):
        """The Runtime runs the task and the held solver process is alive (the scheduler advances only here)."""
        supervisor.tick()
        task = client.task(task["id"])
        if task["state"] != "running" or not marker.exists() or release.exists():
            return None
        held = json.loads(marker.read_text(encoding="utf-8"))
        return held if solver_alive(held) else None

    k = first_dispatch_killed(s, runtime, monkeypatch, request, solver_running)
    first_pid, run_id, identity = k["first_pid"], k["run_id"], k["identity"]
    envelope, started, held = k["envelope"], k["started"], k["evidence"]
    task_id = k["interrupted_tasks"][0]["id"]
    assert [(t["id"], t["state"]) for t in k["interrupted_tasks"]] == [(task_id, "running")]
    work = (runtime[2].service.task_dir(task_id) / "work").resolve()
    assert work in Path(held["cwd"]).resolve().parents  # the held solver is this task's, in its work directory
    # The bridge died; the Runtime task and its solver did not. The stored run is the killed process's.
    assert solver_alive(held) and client.task(task_id)["state"] == "running"
    stored = store.workflow_runs.get(run_id)
    assert k["at_interruption"] == stored["status"] == "running" and stored["owner"]["pid"] == first_pid
    assert stored["executor_id"] == identity["executor_id"] and started[0]["approval"] == envelope
    simulate = next(t for t in stored["tasks"] if t["step"] == "simulate")
    assert simulate["progress"]["task_id"] == task_id
    return {**k, "gate": gate, "marker": marker, "release": release, "held": held, "task_id": task_id, "work": work,
            "stored_run": stored, "simulate": simulate}


def fixed_outputs(s, k):
    """The released solver's succeeded task: its frozen inputs, then its fixed manufactured outputs byte for byte in
    the Runtime's artifact digests and in three downloads. Returns the artifacts, expected digests, case prefix and
    downloaded digests."""
    client, gate, held, task_id = s["client"], k["gate"], k["held"], k["task_id"]
    artifacts = {a["path"]: a for a in client.artifacts(task_id)}
    case = Path(held["cwd"]).resolve().relative_to(k["work"]).as_posix()
    prefix = "" if case == "." else case + "/"
    inputs = gate / "inputs"
    client.download(task_id, prefix + "input.toml", inputs / "input.toml")
    frozen = read_toml(inputs / "input.toml")
    system = frozen["system"]
    assert system["simulation_grid"] == [4, 3, 2] and system["temperature"] == 300
    assert (system["timestep_start"], system["timestep_total"], frozen["output"]["interval"]) == (0, 3, 2)
    reference = gate / "reference"
    reference.mkdir()
    write_outputs(reference)
    expected = {prefix + p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(reference.iterdir())}
    assert len(expected) > 3 and {prefix + "energy_out.dat", prefix + "mupro_completion.json"} <= set(expected)
    assert set(expected) <= set(artifacts)
    assert {p: artifacts[p]["sha256"] for p in expected} == expected  # fixed manufactured outputs, byte for byte
    downloaded = {}
    for name in ("energy_out.dat", "mupro_completion.json", "Polar.00000002.dat"):
        path = gate / "downloaded" / name
        client.download(task_id, prefix + name, path)
        downloaded[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert downloaded[name] == expected[prefix + name]
    assert "stk-mupro.json" in artifacts
    return artifacts, expected, prefix, downloaded


def observed_only(request, s, k, runtime_state):
    """A fresh strict bridge process on the same state reopens the session and explicitly observes the original item
    while the Runtime task is ``runtime_state``. It reads the historical start and the stored workflow state (still the
    killed process's running run, never refreshed), not the actual Runtime state; nothing is decided, started,
    recovered, cancelled, collected or submitted, and the process closes cleanly."""
    store, client = s["store"], s["client"]
    sid, item, run_id, task_id = k["sid"], k["item"], k["run_id"], k["task_id"]
    identity, submissions, cancels = k["identity"], k["submissions"], k["cancels"]
    artifacts = {a["path"]: a for a in client.artifacts(task_id)}
    fresh = probe_bridge(request, s, k["state"], "fresh")
    fresh_pid = fresh.process.pid
    handle = fresh.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    params = {"handle": handle, "session_id": sid}
    args = {**params, "item_id": item["item_id"]}
    reopened = fresh.call("project.agent.get", params)
    assert [card["item"] for card in reopened["run_approvals"]] == [item] and reopened["awaiting"] == []
    receipt = fresh.call("project.agent.run_observe", args)["receipt"]
    current = fresh.call("project.workflow_runs.get", {"handle": handle, "run_id": run_id})["run"]
    runtime_task = client.task(task_id)
    # Historical start: the person's exact approval, executed by the killed process.
    assert receipt["outcome"] == "started" and receipt["ok"] is True and receipt["run_id"] == run_id
    assert receipt["item_id"] == item["item_id"] and receipt["approval"] == k["envelope"]
    assert receipt["executor_id"] == identity["executor_id"]
    # Stored workflow state: still the killed process's running run, never refreshed by observation or reopening.
    assert receipt["run_status"] == current["status"] == "running" and current["owner"]["pid"] == k["first_pid"]
    assert next(t for t in current["tasks"] if t["step"] == "simulate")["progress"] == k["simulate"]["progress"]
    # Actual Runtime state. Only an explicit, separate person's action may follow it.
    assert runtime_task["state"] == runtime_state and runtime_task["id"] == task_id
    assert fresh.call("project.agent.verify", params)["ok"]
    final_view = fresh.call("project.agent.get", params)
    assert [e["item_id"] for e in final_view["events"] if e["kind"] == "approval_decided"] == [item["item_id"]]
    saved = final_view["run_approvals"][0]["receipt"]
    assert saved["outcome"] == "started" and saved["run_status"] == "running"
    assert fresh.close() == 0

    fresh_records = probe_records(s, fresh_pid)
    fresh_identity = next(r["value"] for r in fresh_records if r["name"] == "identity")
    assert fresh_identity["executor_id"] != identity["executor_id"]
    assert [r for r in fresh_records if r["name"] != "identity"] == []  # no decide/start/recover/cancel/analysis
    assert len(submissions) == 1 and cancels == []
    assert [(t["id"], t["state"]) for t in client.tasks()] == [(task_id, runtime_state)]
    assert {a["path"]: a for a in client.artifacts(task_id)} == artifacts
    with store._connect() as db:
        _, after = store.workflow_runs._read(db, run_id)
    assert after == k["run_events"] and started_events(store, run_id) == k["started"]
    return {"observe": receipt, "fresh_pid": fresh_pid, "fresh_identity": fresh_identity,
            "stored_run_status": current["status"], "runtime_state_at_observe": runtime_task["state"],
            "fresh_calls": [r["value"] for r in fresh_records if r["name"] == "call"]}


def offline_finish_observed(s, runtime, monkeypatch, request):
    """The offline-finish case below up to its observation-only checks; returns what later steps compare against."""
    store, client, supervisor = s["store"], s["client"], s["supervisor"]
    k = held_solver_killed(s, runtime, monkeypatch, request)
    run_id, task_id, held, stored = k["run_id"], k["task_id"], k["held"], k["stored_run"]
    submissions, cancels = k["submissions"], k["cancels"]

    # Release the solver with no bridge process alive; the Runtime finishes the task on its own.
    k["release"].touch()

    def terminal_task():
        supervisor.tick()
        task = client.task(task_id)
        return task if task["state"] in TERMINAL else None

    finished = until_true(terminal_task, 60, "the released solver's Runtime task")
    assert finished["state"] == "succeeded" and finished["exit_code"] == 0, finished
    assert not solver_alive(held)
    artifacts, expected, prefix, downloaded = fixed_outputs(s, k)
    # Exactly one submission and no cancel; no other task; the stored run did not follow the task's completion.
    assert len(submissions) == 1 and cancels == [] and [t["id"] for t in client.tasks()] == [task_id]
    with store._connect() as db:
        _, events = store.workflow_runs._read(db, run_id)
    assert events == k["run_events"] and store.workflow_runs.get(run_id) == stored

    f = observed_only(request, s, k, "succeeded")
    identity = k["identity"]
    (s["tmp"] / "probe-summary.json").write_text(json.dumps({
        "first_pid": k["first_pid"], "first_returncode": k["first"].process.returncode, "fresh_pid": f["fresh_pid"],
        "first_executor_id": identity["executor_id"], "fresh_executor_id": f["fresh_identity"]["executor_id"],
        "run_id": run_id, "item_id": k["item"]["item_id"], "runtime_task": task_id, "held_solver": held,
        "runtime_state_at_interruption": k["interrupted_tasks"][0]["state"],
        "run_status_at_interruption": k["at_interruption"], "runtime_terminal": {
            key: finished.get(key) for key in ("state", "exit_code", "reason", "finished_at")},
        "fixed_outputs_sha256": expected, "downloaded_outputs_sha256": downloaded,
        "withheld_reply_outcome": k["reply"]["result"]["receipt"]["outcome"],
        "observe": f["observe"], "stored_run_status": f["stored_run_status"],
        "runtime_state_at_observe": f["runtime_state_at_observe"],
        "runtime_submissions": len(submissions), "runtime_cancels": len(cancels), "first_calls": k["first_calls"],
        "fresh_calls": f["fresh_calls"]}, indent=2), encoding="utf-8")
    return {**k, "artifacts": artifacts, "expected": expected, "prefix": prefix, "offline_run": stored,
            "observe": f["observe"], "fresh_identity": f["fresh_identity"]}


def test_killed_bridge_process_while_its_solver_runs_then_the_task_finishes_without_a_bridge(
        scan, runtime, monkeypatch, request):
    """As the queued case above, but the Runtime has already started the synthetic solver, held at a test-owned gate,
    when the strict bridge process is killed before its first successful start reply reaches the desktop. The solver
    is released with no bridge alive and its Runtime task succeeds with fixed outputs. A fresh strict bridge's explicit
    ``run_observe`` then reports the historical start and the stored workflow state, which is not the actual Runtime
    state: nothing adopted, collected, decided, started, recovered, cancelled or submitted the task again."""
    offline_finish_observed(scan, runtime, monkeypatch, request)


def energy_trace_document():
    """A saved analysis the stock graph worker evaluates: the energy trace of the row's MuFerro final state."""
    return {"format": "stk.analysis-document/1", "graph": {"schema": "stk.graph/1", "parameters": [],
            "nodes": [{"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}}],
            "outputs": {"energy": "run.energy"}}, "parameters": {}, "outputs": ["energy"]}


def use_energy_trace(s):
    """The workflow's saved analysis becomes the energy trace, before preparation freezes its content."""
    store = s["store"]
    document = store.workflows.get(s["workflow"])["workflow"]["document"]
    analysis_id = next(step["ref"]["analysis"] for step in document["steps"] if step["kind"] == "analysis")
    store.analyses.update(analysis_id, "Energy", energy_trace_document(), expected_revision=store.info()["revision"])


def no_collected_result(store, directory):
    """Nothing of the simulation run under ``directory`` was collected, indexed, tabulated or analysed."""
    assert not (store.directory / directory).exists()
    assert all(table["id"] != muferro.RESULT_TABLE_ID for table in store.snapshot()["tables"])
    assert not any(row["path"].startswith(directory + "/") for row in store.files.list()["records"])
    assert store.analysis_runs.list()["runs"] == []


def manual_bridge(request, s, k):
    """A third strict bridge process, with the stock graph worker, reopens the original session. A repeat agent
    approval is not a workflow control: this desktop has not reviewed the plan, so it is refused and records nothing."""
    bridge = probe_bridge(request, s, k["state"], "manual", real_analysis=True)
    pid, item = bridge.process.pid, k["item"]
    handle = bridge.call("project.open", {"directory": str(s["store"].directory)})["project"]["handle"]
    params = {"handle": handle, "session_id": k["sid"]}
    args = {**params, "item_id": item["item_id"]}
    m = {"bridge": bridge, "pid": pid, "handle": handle, "params": params, "args": args,
         "run_args": {"handle": handle, "run_id": k["run_id"]},
         "decision": {**args, "decision": "start", "plan_sha256": item["plan_sha256"],
                      "expected_revision": item["expected_revision"]},
         "calls": lambda: [r["value"] for r in probe_records(s, pid) if r["name"] == "call"]}
    m["refused"] = bridge.error("project.agent.run_decide", m["decision"])
    assert m["refused"]["code"] == "conflict" and "Read the complete frozen run plan" in m["refused"]["message"]
    assert m["calls"]() == [] and len(k["submissions"]) == 1 and k["cancels"] == []
    return m


def recovered_by_hand(s, k, m, runtime_state):
    """Manual recover, without force: the vanished executor's attempt becomes interrupted and the run stops, with the
    original remote work still recorded. Observation then reads the original approval on the stopped run. Neither
    contacts the Runtime for a new action; its task stays ``runtime_state`` and nothing is collected."""
    store, client, manual, calls = s["store"], s["client"], m["bridge"], m["calls"]
    run_id, task_id, original_run = k["run_id"], k["task_id"], k["simulate"]["progress"]["simulation_run_id"]
    artifacts = {a["path"]: a for a in client.artifacts(task_id)}
    with store._connect() as db:
        _, before = store.workflow_runs._read(db, run_id)
    assert before == k["run_events"]  # neither the fresh observation, reopening nor the refusal changed the run
    assert not psutil.pid_exists(k["first_pid"])
    recovered = manual.call("project.workflow_runs.recover", m["run_args"])["run"]
    assert calls() == ["WorkflowRunExecutor.recover", "WorkflowRuns.interrupt"]
    assert recovered["status"] == "stopped" and recovered["executor_id"] is None  # no executor owns a stopped run
    by_step = {t["step"]: t for t in recovered["tasks"]}
    assert by_step["simulate"]["status"] == "interrupted" and by_step["simulate"]["attempt"] == 1
    assert by_step["simulate"]["error"]["code"] == "interrupted"
    assert by_step["simulate"]["progress"] == k["simulate"]["progress"]  # the original remote work, still recorded
    assert by_step["energy"]["status"] == "pending" and by_step["energy"]["attempt"] == 0
    with store._connect() as db:
        _, recover_events = store.workflow_runs._read(db, run_id)
    added = recover_events[len(before):]
    assert recover_events[:len(before)] == before
    assert [(e["step"], e["attempt"], e["status"]) for e in added] == [("simulate", 1, "interrupted"), ("", 0, "stopped")]
    assert added[1]["executor_id"] == k["identity"]["executor_id"]
    observed = manual.call("project.agent.run_observe", m["args"])["receipt"]
    assert observed["outcome"] == "started" and observed["approval"] == k["envelope"]
    assert observed["run_status"] == "stopped" and observed["executor_id"] == k["identity"]["executor_id"]
    assert len(k["submissions"]) == 1 and k["cancels"] == []
    assert calls() == ["WorkflowRunExecutor.recover", "WorkflowRuns.interrupt"]
    assert [(t["id"], t["state"]) for t in client.tasks()] == [(task_id, runtime_state)]
    assert {a["path"]: a for a in client.artifacts(task_id)} == artifacts
    assert store.runs.get(original_run)["status"]["task"]["id"] == task_id
    no_collected_result(store, f"results/muferro/{original_run}")
    return {"recovered": {"status": recovered["status"], "tasks": [{key: t[key] for key in (
                "step", "status", "attempt", "error", "progress")} for t in recovered["tasks"]]},
            "recover_events": [{key: e.get(key) for key in ("step", "attempt", "status", "executor_id")} for e in added],
            "observe_after_recover": observed}


def until_complete(s, m, timeout, what):
    """The stopped, complete workflow run; the Runtime scheduler advances only here (no bridge ticks it)."""
    def complete():
        s["supervisor"].tick()
        run = m["bridge"].call("project.workflow_runs.get", m["run_args"])["run"]
        return run if run["status"] == "stopped" and run["complete"] else None
    return until_true(complete, timeout, what)


def adopted_and_analysed(s, k, m, done, stages, artifacts, expected, prefix):
    """The manual start's attempt 2 adopted the original simulation run and Runtime task (its progress ``stages``),
    froze the Runtime's verified result bytes as the row's snapshot and ran the row's analysis on that snapshot in the
    stock graph worker. The person's approved start stays first; the manual start is a separate, unapproved one."""
    store, client, manual = s["store"], s["client"], m["bridge"]
    run_id, task_id = k["run_id"], k["task_id"]
    original_run = k["simulate"]["progress"]["simulation_run_id"]
    manual_identity = next(r["value"] for r in probe_records(s, m["pid"]) if r["name"] == "identity")
    started = started_events(store, run_id)
    assert len(started) == 2 and started[0] == k["started"][0] and started[0]["approval"] == k["envelope"]
    assert "approval" not in started[1] and started[1]["executor_id"] == manual_identity["executor_id"]
    assert started[1]["owner"]["pid"] == m["pid"] and manual_identity["executor_id"] != k["identity"]["executor_id"]
    by_step = {t["step"]: t for t in done["tasks"]}
    simulate, energy = by_step["simulate"], by_step["energy"]
    assert simulate["status"] == "succeeded" and simulate["attempt"] == 2 and energy["status"] == "succeeded"
    produced = simulate["produced"]
    assert produced["simulation_run_id"] == original_run and produced["task_id"] == task_id
    with store._connect() as db:
        _, final_events = store.workflow_runs._read(db, run_id)
    adopted = [e for e in final_events if e["step"] == "simulate" and e["attempt"] == 2 and "progress" in e]
    assert adopted[0]["progress"] == {"stage": "adopted", "simulation_run_id": original_run, "adopted_from": 1}
    assert [e["progress"]["stage"] for e in adopted] == stages
    assert len(k["submissions"]) == 1 and k["cancels"] == [] and [(t["id"], t["state"]) for t in client.tasks()] == [
        (task_id, "succeeded")]

    # The collected result files are the Runtime's verified bytes, frozen as the row's snapshot.
    directory = store.directory / produced["directory"]
    assert produced["directory"] == f"results/muferro/{original_run}"
    on_disk = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in produced["files"]}
    assert {name: artifacts[name]["sha256"] for name in on_disk} == on_disk  # the Runtime's own digests
    fixed = {path[len(prefix):]: digest for path, digest in expected.items()}
    case_files = {name[len(prefix):]: digest for name, digest in on_disk.items() if name.startswith(prefix)}
    compared = set(case_files) & set(fixed)
    assert {"energy_out.dat", "mupro_completion.json", "Polar.00000002.dat"} <= compared
    assert {name: case_files[name] for name in compared} == {name: fixed[name] for name in compared}
    snapshot = store.snapshots.get(produced["snapshot_id"])
    assert {f["path"]: (f["record_id"], f["sha256"]) for f in snapshot["manifest"]["files"]} == {
        f"{produced['directory']}/{name}": (produced["files"][name], on_disk[name]) for name in produced["files"]}
    assert energy["produced"]["snapshot_id"] == produced["snapshot_id"]
    analysis = manual.call("project.analysis_runs.get", {"handle": m["handle"],
                                                         "run_id": energy["produced"]["analysis_run_id"]})["run"]
    assert analysis["status"] == "succeeded", analysis
    assert analysis["snapshot_id"] == produced["snapshot_id"] and analysis["snapshot_sha256"] == snapshot["sha256"]
    result = manual.call("project.analysis_runs.result", {"handle": m["handle"], "run_id": analysis["id"]})["result"]
    trace = result["outputs"]["energy"]
    assert trace["type"] == "table" and trace["columns"]["step"] == [1, 2, 3] and result["warnings"] == []
    assert trace["columns"]["Total Energy"] == [-1.125, -2.25, -3.375]
    workers = [r["value"] for r in probe_records(s, m["pid"]) if r["name"] == "graph_worker"]
    assert [(w["command"], w["parent"]) for w in workers] == [(["-m", "suan.desktop_bridge.graph_worker_main"],
                                                               m["pid"])]  # the stock worker, this bridge's child
    return {"manual_identity": manual_identity, "started": started, "adopted_progress": [e["progress"] for e in adopted],
            "simulate": {key: simulate[key] for key in ("status", "attempt", "produced")},
            "energy": {key: energy[key] for key in ("status", "attempt", "produced")},
            "snapshot": {"id": snapshot["id"], "sha256": snapshot["sha256"], "files": len(snapshot["manifest"]["files"])},
            "result_files_sha256": on_disk, "analysis_run": {key: analysis.get(key) for key in (
                "id", "status", "snapshot_id", "snapshot_sha256", "result", "error")},
            "analysis_energy_output": trace, "graph_workers": workers}


def closed_with_original_approval(s, k, m, a):
    """The original approval still accounts for the run: observation reads it and a reviewed repeat agent decision
    replays that historical receipt without dispatching. The manual bridge then closes cleanly and reaps its worker."""
    manual, calls, item = m["bridge"], m["calls"], k["item"]
    receipt = manual.call("project.agent.run_observe", m["args"])["receipt"]
    assert receipt["outcome"] == "started" and receipt["approval"] == k["envelope"]
    assert receipt["executor_id"] == k["identity"]["executor_id"] and receipt["run_status"] == "stopped"
    assert manual.call("project.agent.run_plan", m["args"])["item"] == item
    replay = manual.call("project.agent.run_decide", m["decision"])["receipt"]
    assert replay == receipt  # a reviewed repeat decision replays the historical receipt; nothing is dispatched
    assert calls()[-1] == "AgentExecutor.decide_run" and calls().count("WorkflowRuns.start") == 1
    view = manual.call("project.agent.get", m["params"])
    assert [e["item_id"] for e in view["events"] if e["kind"] == "approval_decided"] == [item["item_id"]]
    assert manual.call("project.agent.verify", m["params"])["ok"]
    assert started_events(s["store"], k["run_id"]) == a["started"]
    assert len(k["submissions"]) == 1 and k["cancels"] == []
    assert manual.close() == 0
    assert not manual.violations, manual.violations
    worker = a["graph_workers"][0]
    try:
        worker_birth = psutil.Process(worker["pid"]).create_time()
    except psutil.NoSuchProcess:
        worker_birth = None
    assert worker_birth != worker["created_at"]
    return {"observe_after_start": receipt, "repeat_decision_replay": replay, "manual_calls": calls()}


def test_offline_finished_task_is_recovered_by_hand_then_adopted_by_an_explicit_workflow_start(
        scan, runtime, monkeypatch, request):
    """The offline-finish case above, with its observation-only checks unchanged, then the existing manual workflow
    controls in a third strict bridge process that uses the stock graph worker (docs/project-workflows.md "按行运行",
    "MuFerro 步骤"). An explicit ``recover`` without ``force`` marks the vanished executor's attempt interrupted and stops
    the run; an explicit ``start`` adopts the original succeeded simulation run and Runtime task (no new submission),
    collects and freezes its verified outputs, then runs the row's downstream analysis. The person's original approval
    stays the only one: a repeat agent decision is refused before review and replays the historical receipt after it,
    and neither recover, observation nor the repeat decision submits, cancels or starts anything."""
    s = scan
    use_energy_trace(s)
    o = offline_finish_observed(s, runtime, monkeypatch, request)
    no_collected_result(s["store"], f"results/muferro/{o['simulate']['progress']['simulation_run_id']}")
    m = manual_bridge(request, s, o)
    r = recovered_by_hand(s, o, m, "succeeded")

    # An explicit manual start (no approval) adopts the original simulation run and its succeeded Runtime task.
    m["bridge"].call("project.workflow_runs.start", m["run_args"])
    done = until_complete(s, m, 120, "the adopted run to collect and analyse")
    a = adopted_and_analysed(s, o, m, done, ["adopted", "collecting"], o["artifacts"], o["expected"], o["prefix"])
    assert m["calls"]() == ["WorkflowRunExecutor.recover", "WorkflowRuns.interrupt", "WorkflowRunExecutor.start",
                            "WorkflowRuns.start", "analysis"]
    c = closed_with_original_approval(s, o, m, a)
    (s["tmp"] / "adopt-summary.json").write_text(json.dumps({
        "manual_pid": m["pid"], "manual_executor_id": a["manual_identity"]["executor_id"],
        "first_executor_id": o["identity"]["executor_id"], "run_id": o["run_id"], "item_id": o["item"]["item_id"],
        "runtime_task": o["task_id"], "simulation_run_id": o["simulate"]["progress"]["simulation_run_id"],
        "refused_repeat_before_review": m["refused"], **r, "started_events": a["started"],
        **{key: a[key] for key in ("adopted_progress", "simulate", "energy", "snapshot", "result_files_sha256",
                                   "analysis_run", "analysis_energy_output", "graph_workers")}, **c,
        "runtime_submissions": len(o["submissions"]), "runtime_cancels": len(o["cancels"])},
        indent=2, default=str), encoding="utf-8")


def still_held(s, k):
    """The original solver process, unreleased and unreplaced; its Runtime task running; nothing new submitted,
    cancelled or collected."""
    held, task_id = k["held"], k["task_id"]
    assert solver_alive(held) and not k["release"].exists()
    assert json.loads(k["marker"].read_text(encoding="utf-8")) == held
    assert [(t["id"], t["state"]) for t in s["client"].tasks()] == [(task_id, "running")]
    assert len(k["submissions"]) == 1 and k["cancels"] == []
    no_collected_result(s["store"], f"results/muferro/{k['simulate']['progress']['simulation_run_id']}")


def followed_live(request, s, k):
    """After ``held_solver_killed``: a fresh bridge only observes; in a third bridge a non-forced ``recover`` and an
    explicit ``start`` make attempt 2 follow the same running Runtime task, simulation run and held solver process,
    and a repeated manual start claims nothing. The gate stays held. Returns the fresh observation, the manual bridge,
    its recovery and what the desktop saw while attempt 2 followed the task."""
    store = s["store"]
    run_id, task_id, envelope = k["run_id"], k["task_id"], k["envelope"]
    original_run = k["simulate"]["progress"]["simulation_run_id"]
    still_held(s, k)
    f = observed_only(request, s, k, "running")
    still_held(s, k)
    m = manual_bridge(request, s, k)
    r = recovered_by_hand(s, k, m, "running")
    still_held(s, k)

    # An explicit manual start (no approval): attempt 2 adopts the original simulation run and follows its task.
    manual, calls = m["bridge"], m["calls"]
    manual.call("project.workflow_runs.start", m["run_args"])

    def following():
        """Attempt 2's own running progress (until it records one, the task shows attempt 1's last progress)."""
        run = manual.call("project.workflow_runs.get", m["run_args"])["run"]
        progress = next(t for t in run["tasks"] if t["step"] == "simulate")["progress"] or {}
        return run if (progress.get("attempt"), progress.get("stage")) == (2, "running") else None

    running = until_true(following, 60, "attempt 2 to follow the running Runtime task")
    manual_identity = next(r["value"] for r in probe_records(s, m["pid"]) if r["name"] == "identity")
    assert running["status"] == "running" and running["executor_id"] == manual_identity["executor_id"]
    assert running["owner"]["pid"] == m["pid"]
    by_step = {t["step"]: t for t in running["tasks"]}
    following_progress = {"stage": "running", "simulation_run_id": original_run, "state": "running", "task_id": task_id}
    assert by_step["simulate"]["status"] == "running" and by_step["simulate"]["attempt"] == 2
    assert by_step["simulate"]["progress"] == {"attempt": 2, **following_progress}
    assert by_step["energy"]["status"] == "pending" and by_step["energy"]["attempt"] == 0
    with store._connect() as db:
        _, events = store.workflow_runs._read(db, run_id)
    live = [e["progress"] for e in events if e["step"] == "simulate" and e["attempt"] == 2 and "progress" in e]
    assert live == [{"stage": "adopted", "simulation_run_id": original_run, "adopted_from": 1}, following_progress]
    started = started_events(store, run_id)
    assert len(started) == 2 and started[0] == k["started"][0] and "approval" not in started[1]
    assert started[1]["executor_id"] == manual_identity["executor_id"]
    assert store.runs.get(original_run)["status"]["task"]["id"] == task_id
    assert calls() == ["WorkflowRunExecutor.recover", "WorkflowRuns.interrupt", "WorkflowRunExecutor.start",
                       "WorkflowRuns.start"]
    observed = manual.call("project.agent.run_observe", m["args"])["receipt"]
    assert observed["outcome"] == "started" and observed["approval"] == envelope
    assert observed["run_status"] == "running" and observed["executor_id"] == k["identity"]["executor_id"]
    # A repeated manual start while attempt 2 follows the task returns the executing run and claims nothing.
    again = manual.call("project.workflow_runs.start", m["run_args"])["run"]
    assert again["status"] == "running" and again["executor_id"] == manual_identity["executor_id"]
    assert calls()[-1] == "WorkflowRunExecutor.start" and calls().count("WorkflowRuns.start") == 1
    assert started_events(store, run_id) == started
    still_held(s, k)
    return f, m, r, {"manual_identity": manual_identity, "running": running, "live": live, "started": started,
                     "observed": observed, "again": again}


def test_running_task_is_recovered_by_hand_then_followed_live_by_an_explicit_workflow_start(
        scan, runtime, monkeypatch, request):
    """The live counterpart of the offline case above: the strict bridge process is killed after the person's approval
    is durable and the Runtime runs the gated synthetic solver, which stays held throughout. A fresh bridge only
    observes. In a third bridge, a non-forced ``recover`` and an explicit ``start`` make attempt 2 follow the same
    running Runtime task, simulation run and solver process (exact PID and birth) without submitting, cancelling or
    collecting; a repeated manual start while it follows claims nothing. Only after the desktop observed the running
    phase is the gate opened: the run collects once and binds output, snapshot and analysis to the original task, with
    one Runtime submission in total and the original approval envelope."""
    s = scan
    client = s["client"]
    use_energy_trace(s)
    k = held_solver_killed(s, runtime, monkeypatch, request)
    run_id, task_id, held = k["run_id"], k["task_id"], k["held"]
    submissions, cancels = k["submissions"], k["cancels"]
    original_run = k["simulate"]["progress"]["simulation_run_id"]
    f, m, r, w = followed_live(request, s, k)
    calls, manual_identity, started, live = m["calls"], w["manual_identity"], w["started"], w["live"]
    observed, again = w["observed"], w["again"]

    # Only now is the gate opened: the Runtime finishes the same task and this bridge collects it once.
    k["release"].touch()
    done = until_complete(s, m, 120, "the followed run to collect and analyse")
    assert not solver_alive(held)
    finished = client.task(task_id)
    assert finished["state"] == "succeeded" and finished["exit_code"] == 0, finished
    artifacts, expected, prefix, downloaded = fixed_outputs(s, k)
    a = adopted_and_analysed(s, k, m, done, ["adopted", "running", "collecting"], artifacts, expected, prefix)
    assert a["started"] == started
    assert calls() == ["WorkflowRunExecutor.recover", "WorkflowRuns.interrupt", "WorkflowRunExecutor.start",
                       "WorkflowRuns.start", "WorkflowRunExecutor.start", "analysis"]
    c = closed_with_original_approval(s, k, m, a)
    (s["tmp"] / "live-adopt-summary.json").write_text(json.dumps({
        "first_pid": k["first_pid"], "first_returncode": k["first"].process.returncode, "fresh_pid": f["fresh_pid"],
        "manual_pid": m["pid"], "first_executor_id": k["identity"]["executor_id"],
        "fresh_executor_id": f["fresh_identity"]["executor_id"], "manual_executor_id": manual_identity["executor_id"],
        "run_id": run_id, "item_id": k["item"]["item_id"], "runtime_task": task_id, "simulation_run_id": original_run,
        "held_solver": held, "withheld_reply_outcome": k["reply"]["result"]["receipt"]["outcome"],
        "fresh_observe": f["observe"], "fresh_calls": f["fresh_calls"],
        "refused_repeat_before_review": m["refused"], **r, "following_progress": live,
        "observe_while_following": observed, "repeat_start_while_following": {
            key: again[key] for key in ("status", "executor_id")},
        "runtime_terminal": {key: finished.get(key) for key in ("state", "exit_code", "reason", "finished_at")},
        "fixed_outputs_sha256": expected, "downloaded_outputs_sha256": downloaded, "started_events": started,
        **{key: a[key] for key in ("adopted_progress", "simulate", "energy", "snapshot", "result_files_sha256",
                                   "analysis_run", "analysis_energy_output", "graph_workers")}, **c,
        "runtime_submissions": len(submissions), "runtime_cancels": len(cancels)}, indent=2, default=str),
        encoding="utf-8")


def test_running_task_followed_after_recovery_is_cancelled_by_hand_without_collecting(
        scan, runtime, monkeypatch, request):
    """The live adoption above up to attempt 2 following the same held solver and Runtime task, then an explicit
    person's ``project.workflow_runs.cancel`` from that bridge, with the gate never opened (docs/project-workflows.md
    "MuFerro 步骤": cancelling a workflow run cancels its followed Runtime task). Exactly one Runtime cancel names the
    original task, the held solver process exits, attempt 2 ends cancelled and the run stops without collecting: no
    output snapshot, result, analysis or new submission. A repeated cancel makes no Runtime action. The person's
    original first-start approval and executor stay distinct from the cancellation; repeated observation, a reviewed
    repeat decision and a cold reopen read them without starting, cancelling or submitting anything."""
    s = scan
    store, client, supervisor = s["store"], s["client"], s["supervisor"]
    use_energy_trace(s)
    k = held_solver_killed(s, runtime, monkeypatch, request)
    run_id, task_id, held, envelope, item = k["run_id"], k["task_id"], k["held"], k["envelope"], k["item"]
    submissions, cancels = k["submissions"], k["cancels"]
    original_run = k["simulate"]["progress"]["simulation_run_id"]
    f, m, r, w = followed_live(request, s, k)
    manual, calls, manual_identity, started = m["bridge"], m["calls"], w["manual_identity"], w["started"]
    followed_calls = ["WorkflowRunExecutor.recover", "WorkflowRuns.interrupt", "WorkflowRunExecutor.start",
                      "WorkflowRuns.start", "WorkflowRunExecutor.start"]
    assert calls() == followed_calls
    snapshots = store.snapshots.list()["snapshots"]
    with store._connect() as db:
        _, before = store.workflow_runs._read(db, run_id)

    # The person cancels the workflow run from this bridge while the solver is still held at its gate.
    requested = manual.call("project.workflow_runs.cancel", m["run_args"])["run"]
    assert requested["status"] in ("cancel_requested", "stopped")

    def stopped():
        supervisor.tick()
        run = manual.call("project.workflow_runs.get", m["run_args"])["run"]
        return run if run["status"] == "stopped" else None

    cancelled = until_true(stopped, 60, "the cancelled workflow run to stop")

    def solver_exited():
        supervisor.tick()
        task = client.task(task_id)
        return task if task["state"] in TERMINAL and not solver_alive(held) else None

    terminal = until_true(solver_exited, 60, "the Runtime task's held solver to exit")
    assert not k["release"].exists()  # the gate was never opened: the solver exited because the task was cancelled
    assert terminal["state"] == "cancelled" and terminal["reason"] == "Cancelled by user", terminal
    assert cancels == [task_id] and len(submissions) == 1  # one Runtime cancel, naming the original task
    assert [(t["id"], t["state"]) for t in client.tasks()] == [(task_id, "cancelled")]
    assert calls() == followed_calls + ["WorkflowRunExecutor.cancel", "WorkflowRuns.request_cancel"]

    # Attempt 2 ends cancelled; nothing is collected, frozen or analysed.
    assert cancelled["executor_id"] is None and cancelled["complete"] is False
    by_step = {t["step"]: t for t in cancelled["tasks"]}
    simulate, energy = by_step["simulate"], by_step["energy"]
    assert simulate["status"] == "cancelled" and simulate["attempt"] == 2 and simulate["error"]["code"] == "cancelled"
    assert simulate["progress"]["task_id"] == task_id and simulate["progress"]["simulation_run_id"] == original_run
    assert not simulate.get("produced")
    assert energy["status"] == "pending" and energy["attempt"] == 0 and not energy.get("produced")
    with store._connect() as db:
        _, after = store.workflow_runs._read(db, run_id)
    added = after[len(before):]
    assert after[:len(before)] == before
    assert [(e["step"], e["attempt"], e["status"]) for e in added] == [
        ("", 0, "cancel_requested"), ("simulate", 2, "cancelled"), ("", 0, "stopped")]
    assert "approval" not in added[0] and added[2]["executor_id"] == manual_identity["executor_id"]
    assert not any(e.get("progress", {}).get("stage") == "collecting" for e in after)
    assert store.snapshots.list()["snapshots"] == snapshots
    no_collected_result(store, f"results/muferro/{original_run}")
    assert store.runs.get(original_run)["status"]["task"]["id"] == task_id
    assert not any(a["path"].endswith(("energy_out.dat", "mupro_completion.json")) for a in client.artifacts(task_id))

    # A repeated cancel on the stopped run records nothing and makes no Runtime action.
    repeated = manual.call("project.workflow_runs.cancel", m["run_args"])["run"]
    assert repeated["status"] == "stopped" and repeated["tasks"] == cancelled["tasks"]
    supervisor.tick()
    assert cancels == [task_id] and len(submissions) == 1 and [t["id"] for t in client.tasks()] == [task_id]
    with store._connect() as db:
        _, repeat_events = store.workflow_runs._read(db, run_id)
    assert repeat_events == after
    cancel_calls = followed_calls + ["WorkflowRunExecutor.cancel", "WorkflowRuns.request_cancel"] * 2
    assert calls() == cancel_calls

    # The original approval and executor, distinct from the present cancellation, read repeatedly and observationally.
    assert started_events(store, run_id) == started and started[0] == k["started"][0]
    assert started[0]["approval"] == envelope and "approval" not in started[1]
    observed = [manual.call("project.agent.run_observe", m["args"])["receipt"] for _ in range(2)]
    assert observed[0] == observed[1]
    receipt = observed[0]
    assert receipt["outcome"] == "started" and receipt["approval"] == envelope and receipt["run_id"] == run_id
    assert receipt["executor_id"] == k["identity"]["executor_id"] != manual_identity["executor_id"]
    assert receipt["run_status"] == "stopped"
    assert manual.call("project.agent.run_plan", m["args"])["item"] == item
    replay = manual.call("project.agent.run_decide", m["decision"])["receipt"]
    assert replay == receipt  # the approval is spent: a reviewed repeat replays it and restarts nothing
    assert calls() == cancel_calls + ["AgentExecutor.decide_run"]
    view = manual.call("project.agent.get", m["params"])
    assert [e["item_id"] for e in view["events"] if e["kind"] == "approval_decided"] == [item["item_id"]]
    assert manual.call("project.agent.verify", m["params"])["ok"]
    assert manual.close() == 0
    assert not manual.violations, manual.violations

    # A cold reopen in a fourth bridge process reads the same history and changes nothing.
    cold = probe_bridge(request, s, k["state"], "cold")
    cold_pid = cold.process.pid
    handle = cold.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    params = {"handle": handle, "session_id": k["sid"]}
    reopened = cold.call("project.agent.get", params)
    assert [card["item"] for card in reopened["run_approvals"]] == [item] and reopened["awaiting"] == []
    cold_receipt = cold.call("project.agent.run_observe", {**params, "item_id": item["item_id"]})["receipt"]
    assert cold_receipt == receipt
    cold_run = cold.call("project.workflow_runs.get", {"handle": handle, "run_id": run_id})["run"]
    assert cold_run["status"] == "stopped" and cold_run["tasks"] == cancelled["tasks"]
    assert cold.call("project.agent.verify", params)["ok"]
    assert cold.close() == 0
    cold_records = probe_records(s, cold_pid)
    cold_identity = next(r["value"] for r in cold_records if r["name"] == "identity")
    assert [r for r in cold_records if r["name"] != "identity"] == []  # nothing decided, started, recovered, cancelled
    supervisor.tick()
    assert cancels == [task_id] and len(submissions) == 1
    assert [(t["id"], t["state"]) for t in client.tasks()] == [(task_id, "cancelled")]
    with store._connect() as db:
        _, cold_events = store.workflow_runs._read(db, run_id)
    assert cold_events == after and started_events(store, run_id) == started
    assert store.snapshots.list()["snapshots"] == snapshots
    no_collected_result(store, f"results/muferro/{original_run}")
    (s["tmp"] / "live-cancel-summary.json").write_text(json.dumps({
        "first_pid": k["first_pid"], "first_returncode": k["first"].process.returncode, "fresh_pid": f["fresh_pid"],
        "manual_pid": m["pid"], "cold_pid": cold_pid, "first_executor_id": k["identity"]["executor_id"],
        "fresh_executor_id": f["fresh_identity"]["executor_id"], "manual_executor_id": manual_identity["executor_id"],
        "cold_executor_id": cold_identity["executor_id"], "run_id": run_id, "item_id": item["item_id"],
        "runtime_task": task_id, "simulation_run_id": original_run, "held_solver": held,
        "fresh_observe": f["observe"], **r, "following_progress": w["live"], "observe_while_following": w["observed"],
        "cancel_reply_status": requested["status"], "runtime_cancels": cancels,
        "runtime_terminal": {key: terminal.get(key) for key in ("state", "exit_code", "reason", "finished_at")},
        "gate_released": k["release"].exists(), "cancel_events": [
            {key: e.get(key) for key in ("step", "attempt", "status", "executor_id", "error")} for e in added],
        "cancelled_tasks": [{key: t.get(key) for key in ("step", "status", "attempt", "error", "progress", "produced")}
                            for t in cancelled["tasks"]], "repeat_cancel_status": repeated["status"],
        "started_events": started, "observe_after_cancel": receipt, "repeat_decision_replay": replay,
        "cold_observe": cold_receipt, "manual_calls": calls(),
        "cold_calls": [r["value"] for r in cold_records if r["name"] == "call"],
        "snapshots": len(snapshots), "runtime_submissions": len(submissions)}, indent=2, default=str),
        encoding="utf-8")


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
