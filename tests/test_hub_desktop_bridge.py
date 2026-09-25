"""WP11 end to end: the desktop bridge, a loopback hub and a node agent connected over its WebSocket.

The hub (``suan.control.app``) runs under uvicorn on 127.0.0.1; the real
:class:`suan.control.agent.NodeAgent` connects to it with ``run()`` (outbound WebSocket, blob
uploads over HTTP, import blobs fetched over HTTP) and drives the loopback Runtime fixture. Covers
the read path (no action rows for polling), uploads through the hub with resume and a reviewed
``workspace.import``, hub-side ``graph.cancel``, desktop auto-run, node-side import checks, and
the bridge's state-directory lock.
"""
import asyncio
import hashlib
from pathlib import Path
import random
import threading
import time

import pytest

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")
pytest.importorskip("websockets")

from suan.desktop_bridge.hub import HubClient  # noqa: E402
from test_control_graph import muferro_graph  # noqa: E402
from test_desktop_bridge import ProcessBridge, bridge_env, inproc  # noqa: E402,F401,F811 (fixtures)

OWNER = "desktop-hub-live-owner-" + "q" * 32
AUTH = {"Authorization": "Bearer " + OWNER}
MIB = 1024 * 1024
ECHO_PROGRAM = "from pathlib import Path; print('读路径'); Path('out.txt').write_text('结果', encoding='utf-8')"
ECHO_TEMPLATE = {"argv": ["@python", "-c", ECHO_PROGRAM], "outputs": ["out.txt"]}


class LiveHub:
    """A loopback hub with one node agent connected through ``NodeAgent.run`` (WebSocket + HTTP)."""

    def __init__(self, runtime, tmp_path):
        from suan.control.agent import NodeAgent
        from suan.control.app import create_app
        self.client, self.supervisor, _, _ = runtime
        self.app = create_app(tmp_path / "control", OWNER, {"echo": ECHO_TEMPLATE}, upload_min_free_bytes=0)
        self.store = self.app.state.store
        config = uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning", access_log=False,
                                ws_max_size=16 * MIB)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 20
        while not self.server.started:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        self.url = f"http://127.0.0.1:{self.server.servers[0].sockets[0].getsockname()[1]}"
        self.http = httpx.Client(base_url=self.url, timeout=30)
        code = self.http.post("/api/v1/pairings", json={"role": "node"}, headers=AUTH).json()["code"]
        node = self.http.post("/api/v1/pairings/claim", json={"code": code, "name": "节点"}).json()
        self.node_id, self.node_token = node["device_id"], node["token"]
        self.agent = NodeAgent(self.client, tmp_path / "agent")
        self.stop = threading.Event()
        self.ticker = threading.Thread(target=self._tick, daemon=True)
        self.ticker.start()
        self.agent_loop = None
        self.agent_task = None
        self.agent_thread = threading.Thread(target=self._run_agent, daemon=True)
        self.agent_thread.start()
        deadline = time.monotonic() + 30
        while True:
            device = self.store.device(self.node_id)
            if device and device["online"] and "read" in (device["snapshot"].get("features") or ()):
                break
            assert time.monotonic() < deadline, device
            time.sleep(0.05)

    def _tick(self):
        while not self.stop.is_set():
            try:
                self.supervisor.tick()
            except Exception as exc:  # keep ticking; the test sees the task state
                print("supervisor:", type(exc).__name__, exc)
            self.stop.wait(0.05)

    def _run_agent(self):
        self.agent_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.agent_loop)
        self.agent_task = self.agent_loop.create_task(self.agent.run(self.url, self.node_token))
        try:
            self.agent_loop.run_until_complete(self.agent_task)
        except BaseException:
            pass
        finally:
            self.agent_loop.close()

    def code(self, profile=None):
        body = {"role": "client", **({"profile": profile} if profile else {})}
        return self.http.post("/api/v1/pairings", json=body, headers=AUTH).json()["code"]

    def actions(self, kind=None):
        return [a for a in self.store.actions() if kind is None or a["request"]["kind"] == kind]

    def close(self):
        self.stop.set()
        if self.agent_loop is not None and self.agent_task is not None:
            self.agent_loop.call_soon_threadsafe(self.agent_task.cancel)
        self.agent_thread.join(timeout=10)
        self.ticker.join(timeout=10)
        self.http.close()
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def live(runtime, tmp_path):
    hub = LiveHub(runtime, tmp_path)
    yield hub
    hub.close()


def pair(harness, hub, name="lab", profile="desktop"):
    connection = harness.call("connections.pair_hub", {"name": name, "url": hub.url, "code": hub.code(profile),
                                                       "device_name": "桌面"})["connection"]
    assert connection["profile"] == (profile or "")
    return connection["id"], {"connection": connection["id"], "node": hub.node_id}


def template_task(harness, target, hub):
    workspace = harness.call("workspace.create", {**target, "name": "读", "idempotency_key": "w"})["workspace"]["id"]
    task = harness.call("task.submit", {**target, "idempotency_key": "t", "template": "echo",
                                        "workspace_id": workspace})["task"]["id"]
    deadline = time.monotonic() + 60
    while hub.client.task(task)["state"] not in ("succeeded", "failed"):
        assert time.monotonic() < deadline
        time.sleep(0.1)
    assert hub.client.task(task)["state"] == "succeeded"
    return workspace, task


# ---------------------------------------------------------------------------
# Read path


def test_polling_reads_through_the_hub_create_no_action_rows(live, inproc):  # noqa: F811
    harness = inproc()
    hub_id, target = pair(harness, live)
    workspace, task = template_task(harness, target, live)
    before = len(live.actions())
    changes = len([e for e in live.store.events() if e["kind"] == "actions.changed"])
    logs = harness.call("logs.subscribe", {**target, "task_id": task, "streams": ["stdout", "stderr"]})["sub"]
    harness.wait_event(lambda e: e["event"] == "logs.end" and e["data"]["sub"] == logs)
    assert "".join(c["text"] for c in harness.events_of("logs.chunk", logs)) == "读路径\n"
    events = harness.call("events.subscribe", {**target, "task_id": task})["sub"]
    harness.wait_event(lambda e: e["event"] == "events.end" and e["data"]["sub"] == events)
    artifacts = harness.call("task.artifacts", {**target, "task_id": task})["artifacts"]
    assert [a["path"] for a in artifacts] == ["out.txt"]
    transfer = harness.call("download.start", {**target, "task_id": task, "path": "out.txt"})["transfer"]
    done = harness.wait_transfer(transfer["id"])
    assert done["state"] == "completed" and Path(done["local"]).read_text(encoding="utf-8") == "结果"
    assert harness.call("workspace.files", {**target, "workspace_id": workspace})["files"] == []
    missing = harness.error("task.artifacts", {**target, "task_id": "e" * 32})
    assert missing["code"] == "remote_error"  # the node's error, still without an action row
    assert len(live.actions()) == before
    assert len([e for e in live.store.events() if e["kind"] == "actions.changed"]) == changes
    policy = harness.call("hub.policy", {"connection": hub_id})["policy"]
    assert policy["desktop_auto"] is True and policy["desktop_auto_bytes"] == 256 * MIB
    assert "file.read" in policy["read_kinds"]
    harness.close()


# ---------------------------------------------------------------------------
# Uploads through the hub


def test_upload_through_the_hub_resumes_waits_for_review_and_imports(live, inproc, tmp_path, monkeypatch):  # noqa: F811
    folder = tmp_path / "输入"
    (folder / "sub").mkdir(parents=True)
    big = random.Random(11).randbytes(2 * MIB + 321)
    (folder / "sub" / "场.bin").write_bytes(big)
    (folder / "config.json").write_bytes(b'{"step": 1}\n')
    offsets, dropped = [], []
    original = HubClient.upload_chunk

    def flaky(self, upload_id, offset, data):
        offsets.append(offset)
        if offset >= MIB and not dropped:
            dropped.append(offset)
            raise ConnectionResetError("simulated network drop")
        return original(self, upload_id, offset, data)
    monkeypatch.setattr(HubClient, "upload_chunk", flaky)

    harness = inproc()
    hub_id, target = pair(harness, live)
    workspace = harness.call("workspace.create", {**target, "name": "上传", "idempotency_key": "u"})["workspace"]["id"]
    mark = harness.mark()
    transfer = harness.call("upload.start", {**target, "workspace_id": workspace, "source": str(folder),
                                             "remote": "run"})["transfer"]
    failed = harness.wait_transfer(transfer["id"], start=mark)
    assert failed["state"] == "failed" and failed["error"]["code"] == "unavailable", failed
    held = offsets[-1]
    mark = harness.mark()
    harness.call("transfer.resume", {"id": transfer["id"]})
    waiting = harness.wait_event(lambda e: e["event"] == "transfer.updated" and e["data"]["transfer"]["id"] ==
                                 transfer["id"] and e["data"]["transfer"].get("action", {}).get("state") ==
                                 "review", start=mark)["data"]["transfer"]
    resumed = offsets[offsets.index(held) + 1:]
    assert resumed[0] == held >= MIB and 0 not in resumed  # continued from the hub's bytes
    assert waiting["state"] == "running" and waiting["bytes_done"] == waiting["bytes_total"] == len(big) + 12
    action_id = waiting["action"]["id"]
    # The bridge closes while the import waits for review; a new bridge resumes the same action.
    harness.close()
    restarted = inproc()
    hello = restarted.call("hello", {"protocol": 1})
    assert hello["resumed_transfers"] == [transfer["id"]]
    request = restarted.call("hub.action", {"connection": hub_id, "action_id": action_id})["action"]["request"]
    assert sorted(f["path"] for f in request["payload"]["files"]) == ["run/config.json", "run/sub/场.bin"]
    restarted.call("hub.review", {"connection": hub_id, "action_id": action_id, "approved": True})
    done = restarted.wait_transfer(transfer["id"])
    assert done["state"] == "completed" and done["action"]["state"] == "succeeded"
    assert len(live.actions("workspace.import")) == 1
    files = {f["path"]: f["sha256"] for f in restarted.call("workspace.files", {**target, "workspace_id": workspace})[
        "files"]}
    assert files == {"run/config.json": hashlib.sha256(b'{"step": 1}\n').hexdigest(),
                     "run/sub/场.bin": hashlib.sha256(big).hexdigest()}
    # The uploaded input comes back through the read path, verified.
    fetched = restarted.call("download.start", {**target, "workspace_id": workspace, "path": "run/sub/场.bin"})
    fetched = restarted.wait_transfer(fetched["transfer"]["id"])
    assert fetched["state"] == "completed" and Path(fetched["local"]).read_bytes() == big
    restarted.close()


def test_cancelling_an_upload_rejects_its_pending_import(live, inproc, tmp_path):  # noqa: F811
    source = tmp_path / "a.txt"
    source.write_bytes(b"abc")
    harness = inproc()
    hub_id, target = pair(harness, live)
    workspace = harness.call("workspace.create", {**target, "name": "取消", "idempotency_key": "c"})["workspace"]["id"]
    transfer = harness.call("upload.start", {**target, "workspace_id": workspace, "source": str(source)})["transfer"]
    harness.wait_event(lambda e: e["event"] == "transfer.updated" and e["data"]["transfer"]["id"] == transfer["id"]
                       and e["data"]["transfer"].get("action", {}).get("state") == "review")
    cancelled = harness.call("transfer.cancel", {"id": transfer["id"]})["transfer"]
    assert cancelled["state"] == "cancelled" and cancelled["action"]["state"] == "rejected"
    assert [a["state"] for a in live.actions("workspace.import")] == ["rejected"]
    assert live.client.files(workspace) == []
    harness.close()


# ---------------------------------------------------------------------------
# graph.cancel and desktop auto-run


@pytest.fixture
def slow_graphs(monkeypatch):
    """Replace the node's evaluator by one that runs until cancelled (or returns an empty result)."""
    import suan.graph.service as service
    started = threading.Event()
    mode = {"slow": True}

    def evaluate_request(payload, *, resolver, cache_dir, blob_sink, cancel=None, **kw):
        started.set()
        deadline = time.monotonic() + 60
        while mode["slow"] and time.monotonic() < deadline:
            cancel.raise_if_cancelled()
            time.sleep(0.02)
        return {"schema": "stk.graph-result/1", "outputs": {}, "profile": payload.get("profile", "web")}
    monkeypatch.setattr(service, "evaluate_request", evaluate_request)
    return started, mode


def graph_request(**change):
    return {"graph": muferro_graph(), "bindings": {"run": {"task_id": "d" * 32}}, "outputs": ["energy"], **change}


def test_graph_cancel_stops_the_evaluation_on_the_node(live, inproc, slow_graphs):  # noqa: F811
    started, _ = slow_graphs
    harness = inproc()
    hub_id, target = pair(harness, live)
    params = {"eval_id": "slow-1", "mode": "hub", **target, "request": graph_request()}
    pending = harness.request("graph.evaluate", params)
    assert started.wait(30)
    cancelled = harness.call("graph.cancel", {"eval_id": "slow-1"})
    assert cancelled["cancelled"] is True and cancelled["action"]["kind"] == "graph.cancel"
    assert cancelled["action"]["state"] == "succeeded"
    error = harness.response(pending)["error"]
    assert error["code"] == "cancelled"
    evaluation = next(a for a in live.actions("graph.evaluate"))
    deadline = time.monotonic() + 30
    while live.store.action(evaluation["id"])["state"] != "failed":  # the node stopped and reported it
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert live.store.action(evaluation["id"])["error"].startswith("cancelled:")
    assert not live.agent._graph_tokens
    again = harness.error("graph.evaluate", params)
    assert again["code"] == "cancelled"  # the same eval_id names the cancelled action
    harness.close()


def test_graph_cancel_of_a_reviewed_evaluation_by_eval_id(live, inproc, slow_graphs):  # noqa: F811
    harness = inproc()
    hub_id, target = pair(harness, live, profile=None)  # an ordinary client: desktop results need review
    params = {"eval_id": "later", "mode": "hub", **target, "request": graph_request(profile="desktop")}
    review = harness.call("graph.evaluate", params)
    assert review["action"]["state"] == "review" and review["result"] is None
    assert harness.call("graph.cancel", {"eval_id": "unknown"}) == {"cancelled": False}
    cancelled = harness.call("graph.cancel", {"eval_id": "later", **target})
    assert cancelled["cancelled"] is True
    assert live.store.action(review["action"]["id"])["state"] == "failed"
    assert harness.error("graph.evaluate", params)["code"] == "cancelled"
    missing = harness.call("graph.cancel", {"eval_id": "never-started", **target})
    assert missing["cancelled"] is False and missing["error"]["code"] == "remote_error"
    harness.close()


def test_desktop_devices_evaluate_desktop_results_without_review(live, inproc, slow_graphs):  # noqa: F811
    _, mode = slow_graphs
    mode["slow"] = False
    harness = inproc()
    _, desktop = pair(harness, live, "desk")
    _, plain = pair(harness, live, "plain", profile=None)
    request = graph_request(profile="desktop", budget={"max_output_bytes": 64 * MIB})
    ran = harness.call("graph.evaluate", {"eval_id": "d1", "mode": "hub", **desktop, "request": request})
    assert ran["action"]["state"] == "succeeded" and ran["result"]["profile"] == "desktop"
    assert not ran["action"].get("review_reason")
    reviewed = harness.call("graph.evaluate", {"eval_id": "p1", "mode": "hub", **plain, "request": request})
    assert reviewed["action"]["state"] == "review"
    over = harness.call("graph.evaluate", {"eval_id": "d2", "mode": "hub", **desktop,
                                           "request": graph_request(profile="desktop")})  # 2 GiB default
    assert over["action"]["state"] == "review" and "预计传输" in over["action"]["review_reason"]
    harness.close()


# ---------------------------------------------------------------------------
# Node-side checks (unit level)


class _NoRuntime:
    def __init__(self):
        self.uploads = []

    def upload(self, workspace_id, path, remote):
        self.uploads.append((workspace_id, remote))
        return {"path": remote, "size": Path(path).stat().st_size, "sha256": "0" * 64}


def test_node_import_refuses_traversal_and_verifies_sha256(tmp_path):
    from suan.control.agent import NodeAgent
    fetched = []

    def source(action_id, digest, target, size):
        fetched.append(digest)
        Path(target).write_bytes(b"tampered")
    runtime = _NoRuntime()
    agent = NodeAgent(runtime, tmp_path / "agent", blob_source=source)
    digest = hashlib.sha256(b"original").hexdigest()
    for bad in ("../../etc/cron.d/x", "/abs", "a/../../b", "a\\b"):
        action = {"id": "1" * 32, "node_id": "2" * 32, "kind": "workspace.import",
                  "payload": {"workspace_id": "3" * 32, "files": [{"path": bad, "sha256": digest, "size": 8}]}}
        with pytest.raises(ValueError):
            agent.execute(action)
    assert fetched == [] and runtime.uploads == []
    action = {"id": "4" * 32, "node_id": "2" * 32, "kind": "workspace.import",
              "payload": {"workspace_id": "3" * 32, "files": [{"path": "ok.bin", "sha256": digest, "size": 8}]}}
    with pytest.raises(ValueError, match="do not match their sha256"):
        agent.execute(action)
    assert fetched == [digest] and runtime.uploads == []  # nothing reached the workspace
    assert not (tmp_path / "agent" / "imports" / ("4" * 32)).exists()  # staging removed


def test_node_cancels_an_evaluation_before_it_starts(tmp_path, slow_graphs):
    from suan.control.agent import NodeAgent
    started, _ = slow_graphs
    agent = NodeAgent(_NoRuntime(), tmp_path / "agent", blob_sink=lambda data: "0" * 64)
    target = "5" * 32
    assert agent.execute({"id": "6" * 32, "node_id": "2" * 32, "kind": "graph.cancel",
                          "payload": {"action_id": target}}) == {"cancelled": True, "running": False}
    action = {"id": target, "node_id": "2" * 32, "kind": "graph.evaluate", "payload": graph_request()}
    with pytest.raises(ValueError, match="^cancelled:"):
        agent.execute(action)
    # A restarted agent (new object, same cache) still honours the cancellation.
    again = NodeAgent(_NoRuntime(), tmp_path / "agent", blob_sink=lambda data: "0" * 64)
    with pytest.raises(ValueError, match="^cancelled:"):
        again.execute(action)
    # A finished evaluation cannot be cancelled any more.
    finished = {"id": "7" * 32, "node_id": "2" * 32, "kind": "graph.evaluate", "payload": graph_request()}
    _, mode = slow_graphs
    mode["slow"] = False
    agent.execute(finished)
    assert agent.execute({"id": "8" * 32, "node_id": "2" * 32, "kind": "graph.cancel",
                          "payload": {"action_id": "7" * 32}}) == {"cancelled": False, "finished": True}


def test_node_read_answers_only_read_kinds(tmp_path):
    from suan.control.agent import NodeAgent
    agent = NodeAgent(_NoRuntime(), tmp_path / "agent")
    for kind in ("task.submit", "workspace.import", "graph.evaluate", "workspace.create", "task.cancel"):
        with pytest.raises(ValueError, match="Unknown read"):
            agent.read(kind, {})


# ---------------------------------------------------------------------------
# One bridge per state directory


def test_a_second_bridge_on_the_same_state_dir_is_refused(bridge_env):  # noqa: F811
    from suan.desktop_bridge.protocol import BridgeError
    from suan.desktop_bridge.server import Bridge

    class Sink:
        def write(self, data):
            pass

        def flush(self):
            pass
    state = bridge_env / "shared"
    first = Bridge(state, writer=Sink())
    with pytest.raises(BridgeError) as refused:
        Bridge(state, writer=Sink())
    assert refused.value.code == "busy" and str(state) in refused.value.message
    assert Bridge(bridge_env / "other", writer=Sink()).shutdown() is None  # other directories are independent
    first.shutdown()
    second = Bridge(state, writer=Sink())  # released on shutdown
    second.shutdown()


def test_a_second_bridge_process_answers_busy_and_exits(bridge_env):  # noqa: F811
    state = bridge_env / "bridge"
    first = ProcessBridge(state)
    assert first.call("hello", {"protocol": 1})["protocol"] == 1
    second = ProcessBridge(state)
    error = second.error("hello", {"protocol": 1})
    assert error["code"] == "busy" and error["retryable"] is True and error["data"]["state_dir"] == str(state)
    assert second.error("transfer.list")["code"] == "busy"  # every request, until EOF
    assert second.close() == 3
    assert "Another STK desktop bridge" in second.stderr_text()
    assert first.call("transfer.list") == {"transfers": []}  # the first bridge is unaffected
    assert first.close() == 0
    third = ProcessBridge(state)  # the lock went with the first process
    assert third.call("hello", {"protocol": 1})["protocol"] == 1
    third.kill()  # a crashed bridge never blocks the next one
    fourth = ProcessBridge(state)
    assert fourth.call("hello", {"protocol": 1})["protocol"] == 1
    assert fourth.close() == 0
