"""Desktop bridge through a loopback control hub: pairing, the review flow, hub reads, graph.evaluate.

The hub (``suan.control.app``) runs under uvicorn on 127.0.0.1; a node loop in the test executes
queued actions with the real :class:`suan.control.agent.NodeAgent` against the loopback Runtime
fixture and completes them in the hub store, exactly as a connected agent would. This node never
opens the WebSocket, so its heartbeat leaves out the ``read`` feature and the bridge falls back to
read actions (``tests/test_hub_desktop*.py`` cover the read path with a connected agent).
"""
import hashlib
from pathlib import Path
import shutil
import threading
import time

import pytest

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")

from test_desktop_bridge import bridge_env, inproc  # noqa: E402,F401,F811 (fixtures)

OWNER = "desktop-bridge-hub-owner-" + "k" * 32
AUTH = {"Authorization": "Bearer " + OWNER}
TESTS = Path(__file__).resolve().parent
ECHO_PROGRAM = "from pathlib import Path; print('模板运行'); Path('out.txt').write_text('模板结果', encoding='utf-8')"
ECHO_TEMPLATE = {"argv": ["@python", "-c", ECHO_PROGRAM], "outputs": ["out.txt"]}


class Hub:
    """A loopback hub, a paired node and a node loop running actions on the Runtime fixture."""

    def __init__(self, runtime, tmp_path):
        from suan.control.agent import NodeAgent
        from suan.control.app import create_app
        self.client, self.supervisor, _, _ = runtime
        self.app = create_app(tmp_path / "control", OWNER, {"echo": ECHO_TEMPLATE}, upload_min_free_bytes=0)
        self.store = self.app.state.store
        config = uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning", access_log=False)
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
        node = self.http.post("/api/v1/pairings/claim", json={"code": code, "name": "计算节点"}).json()
        self.node_id, self.node_token = node["device_id"], node["token"]

        def sink(data):
            return self.store.blobs.put(data if isinstance(data, (bytes, bytearray, memoryview))
                                        else Path(data).read_bytes())
        def source(action_id, digest, target, size):
            shutil.copyfile(self.store.blobs.path(digest), target)
        self.agent = NodeAgent(self.client, tmp_path / "agent", blob_sink=sink, blob_source=source)
        self.stop = threading.Event()
        self.executed = []
        self.loop = threading.Thread(target=self.run_node, daemon=True)
        self.loop.start()

    def client_code(self, profile="desktop"):
        # Desktop devices: the only clients that may upload (the review flow uploads a file).
        body = {"role": "client", **({"profile": profile} if profile else {})}
        return self.http.post("/api/v1/pairings", json=body, headers=AUTH).json()["code"]

    def run_node(self):
        beat = 0.0
        while not self.stop.is_set():
            try:
                self.supervisor.tick()
                if time.monotonic() - beat > 0.3:
                    snapshot = self.agent.snapshot()
                    snapshot["features"] = [f for f in snapshot["features"] if f != "read"]  # not connected
                    self.store.heartbeat(self.node_id, snapshot)
                    beat = time.monotonic()
                for action in reversed(self.store.actions(self.node_id, pending=True)):
                    try:
                        result, error = self.agent.execute(action["request"]), ""
                    except Exception as exc:
                        result, error = None, self.agent.public_error(exc)
                    self.executed.append(action["request"]["kind"])
                    self.store.complete(action["id"], self.node_id, result, error)
            except Exception as exc:  # keep serving; the test sees the missing result
                print("node loop:", type(exc).__name__, exc)
            self.stop.wait(0.05)

    def close(self):
        self.stop.set()
        self.loop.join(timeout=10)
        self.http.close()
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def hub(runtime, tmp_path):
    hub = Hub(runtime, tmp_path)
    yield hub
    hub.close()


def pair(harness, hub, name="lab"):
    connection = harness.call("connections.pair_hub", {"name": name, "url": hub.url, "code": hub.client_code(),
                                                       "device_name": "桌面客户端"})["connection"]
    assert connection["id"] == "hub:" + name and connection["kind"] == "hub" and connection["url"] == hub.url
    deadline = time.monotonic() + 20
    while True:
        devices = harness.call("hub.devices", {"connection": connection["id"]})["devices"]
        node = next((d for d in devices if d["id"] == hub.node_id), None)
        if node and node["online"] and node["snapshot"].get("tasks") is not None:
            return connection["id"]
        assert time.monotonic() < deadline, devices
        time.sleep(0.1)


def test_hub_review_flow(hub, inproc, tmp_path):  # noqa: F811
    harness = inproc()
    hub_id = pair(harness, hub)
    target = {"connection": hub_id, "node": hub.node_id}
    assert harness.error("connections.pair_hub", {"name": "again", "url": hub.url, "code": "x" * 20})["code"] == \
        "remote_error"  # a used or unknown pairing code
    created = harness.call("workspace.create", {**target, "name": "中心项目", "idempotency_key": "hub-ws"})
    assert created["action"]["state"] == "succeeded"
    workspace = created["workspace"]["id"]
    assert harness.call("workspace.create", {**target, "name": "中心项目", "idempotency_key": "hub-ws"})[
        "workspace"]["id"] == workspace
    # A registered template runs without review.
    templated = harness.call("task.submit", {**target, "idempotency_key": "tpl", "template": "echo",
                                             "workspace_id": workspace})
    assert templated["action"]["state"] == "succeeded" and templated["action"]["kind"] == "task.submit"
    assert set(harness.call("hub.templates", {"connection": hub_id})["templates"]) == {"echo"}
    # A new command waits for review; approving needs the full request to have been read first.
    spec = {"workspace_id": workspace, "argv": ["@python", "-c", "print('审核后运行')"], "name": "自定义"}
    params = {**target, "idempotency_key": "custom", "spec": spec}
    pending = harness.call("task.submit", params)
    assert pending["action"]["state"] == "review" and "task" not in pending
    action_id = pending["action"]["id"]
    assert pending["action"]["review_reason"]
    listed = harness.call("hub.actions", {"connection": hub_id})["actions"]
    assert any(a["id"] == action_id and a["state"] == "review" for a in listed)
    error = harness.error("hub.review", {"connection": hub_id, "action_id": action_id, "approved": True})
    assert error["code"] == "review_not_inspected"
    inspected = harness.call("hub.action", {"connection": hub_id, "action_id": action_id})["action"]
    assert inspected["request"]["payload"]["spec"]["argv"] == spec["argv"]
    approved = harness.call("hub.review", {"connection": hub_id, "action_id": action_id, "approved": True})
    assert approved["action"]["state"] == "queued"
    done = harness.call("task.submit", params)  # the same key waits for the same action
    assert done["action"]["id"] == action_id and done["action"]["state"] == "succeeded"
    task_id = done["task"]["id"]
    assert harness.call("task.submit", params)["task"]["id"] == task_id
    assert hub.executed.count("task.submit") == 2
    conflict = harness.error("task.submit", {**params, "spec": {**spec, "argv": ["@python", "-c", "pass"]}})
    assert conflict["code"] == "conflict"
    # Rejection.
    rejected = harness.call("task.submit", {**target, "idempotency_key": "nope", "spec": {**spec, "name": "拒绝"}})
    harness.call("hub.action", {"connection": hub_id, "action_id": rejected["action"]["id"]})
    record = harness.call("hub.review", {"connection": hub_id, "action_id": rejected["action"]["id"],
                                         "approved": False})["action"]
    assert record["state"] == "rejected"
    error = harness.error("task.submit", {**target, "idempotency_key": "nope", "spec": {**spec, "name": "拒绝"}})
    assert error["code"] == "remote_error" and error["data"]["action"]["state"] == "rejected"
    # Snapshot reads, logs and a verified download through the hub.
    watch = harness.call("watch", {**target, "workspace_id": workspace, "interval": 0.5})["sub"]
    snapshot = harness.wait_event(lambda e: e["event"] == "watch.snapshot" and e["data"]["sub"] == watch and all(
        t["state"] == "succeeded" for t in e["data"]["tasks"]) and len(e["data"]["tasks"]) == 2)
    assert {t["id"] for t in snapshot["data"]["tasks"]} == {task_id, templated["task"]["id"]}
    assert harness.call("task.get", {**target, "task_id": task_id})["task"]["state"] == "succeeded"
    logs = harness.call("logs.subscribe", {**target, "task_id": task_id, "streams": ["stdout"]})["sub"]
    harness.wait_event(lambda e: e["event"] == "logs.end" and e["data"]["sub"] == logs)
    assert "".join(c["text"] for c in harness.events_of("logs.chunk", logs)) == "审核后运行\n"
    templated_id = templated["task"]["id"]
    artifacts = harness.call("task.artifacts", {**target, "task_id": templated_id})["artifacts"]
    assert [a["path"] for a in artifacts] == ["out.txt"]
    transfer = harness.call("download.start", {**target, "task_id": templated_id, "path": "out.txt"})["transfer"]
    done = harness.wait_transfer(transfer["id"])
    assert done["state"] == "completed" and Path(done["local"]).read_text(encoding="utf-8") == "模板结果"
    assert hashlib.sha256(Path(done["local"]).read_bytes()).hexdigest() == artifacts[0]["sha256"]
    # An upload goes into the hub's blob store, then a reviewed workspace.import (read actions here).
    source = tmp_path / "up.txt"
    source.write_bytes(b"x")
    mark = harness.mark()
    upload = harness.call("upload.start", {**target, "workspace_id": workspace, "source": str(source)})["transfer"]
    waiting = harness.wait_event(lambda e: e["event"] == "transfer.updated" and e["data"]["transfer"]["id"] ==
                                 upload["id"] and e["data"]["transfer"].get("action", {}).get("state") == "review",
                                 start=mark)["data"]["transfer"]
    assert waiting["state"] == "running" and waiting["action"]["kind"] == "workspace.import"
    harness.call("hub.action", {"connection": hub_id, "action_id": waiting["action"]["id"]})
    harness.call("hub.review", {"connection": hub_id, "action_id": waiting["action"]["id"], "approved": True})
    assert harness.wait_transfer(upload["id"], start=mark)["state"] == "completed"
    files = harness.call("workspace.files", {**target, "workspace_id": workspace})["files"]
    assert [(f["path"], f["sha256"]) for f in files] == [("up.txt", hashlib.sha256(b"x").hexdigest())]
    # Hub events stream into the app.
    events = harness.call("hub.subscribe", {"connection": hub_id})["sub"]
    harness.wait_event(lambda e: e["event"] == "hub.event" and e["data"]["sub"] == events)
    assert harness.call("connections.check", {"id": hub_id})["nodes"] == 1
    assert harness.error("task.list", {"connection": hub_id})["code"] == "invalid_params"  # no node
    # The device credential never leaves the bridge.
    token = next(iter(__import__("json").loads((harness.bridge.state_dir / "hubs.json").read_text(
        encoding="utf-8")).values()))["token"]
    assert token not in harness.output_text() and OWNER not in harness.output_text()
    harness.close()


def test_hub_graph_evaluate_blobs_and_probe(hub, inproc):  # noqa: F811
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    from conftest import finish
    from mupro_fake import domain_polarization
    from suan.render.payload import decode
    client, supervisor = hub.client, hub.supervisor
    workspace = client.create_workspace("图谱")["id"]
    program = (f"import sys; sys.path.insert(0, {str(TESTS)!r}); from mupro_fake import write_domain_run; "
               "write_domain_run('.', grid=(12, 10, 8), steps=2, interval=1)")
    task_id = client.submit({"workspace_id": workspace, "argv": ["{python}", "-c", program]})["id"]
    hub.stop.set()  # tick the supervisor here, then let the node loop run again
    hub.loop.join(timeout=10)
    assert finish(client, supervisor, task_id, timeout=60)["state"] == "succeeded"
    hub.stop.clear()
    hub.loop = threading.Thread(target=hub.run_node, daemon=True)
    hub.loop.start()
    harness = inproc()
    hub_id = pair(harness, hub)
    request = {"preset": "muferro-domains", "bindings": {"run": {"task_id": task_id}},
               "outputs": ["view", "fractions"], "parameters": {"step": "latest"}, "profile": "web"}
    evaluated = harness.call("graph.evaluate", {"eval_id": "hub-eval", "mode": "hub", "connection": hub_id,
                                                "node": hub.node_id, "request": request}, timeout=180)
    assert evaluated["action"]["state"] == "succeeded"
    result = evaluated["result"]
    blob_dir = Path(evaluated["blob_dir"])
    manifest = result["outputs"]["view"]["manifest"]
    payload = decode(manifest, lambda digest: (blob_dir / digest[:2] / digest).read_bytes())
    assert payload.manifest["schema"] == "stk.payload/2"
    digests = [b["sha256"] for b in manifest["buffers"]]
    assert harness.call("blob.ensure", {"sha256": digests})["missing"] == []
    fresh = harness.call("blob.ensure", {"sha256": digests, "connection": hub_id})
    assert set(fresh["blobs"]) == set(digests)
    unknown = "e" * 64
    assert harness.call("blob.ensure", {"sha256": [unknown], "connection": hub_id})["missing"] == [unknown]
    # The same eval_id is the same hub action: repeating it answers from the hub.
    again = harness.call("graph.evaluate", {"eval_id": "hub-eval", "mode": "hub", "connection": hub_id,
                                            "node": hub.node_id, "request": request})
    assert again["action"]["id"] == evaluated["action"]["id"] and again["result"] == result
    layer = next(item for item in manifest["layers"] if item["id"] == "surface_layer")
    probe = harness.call("probe", {"preset": "muferro-domains", "pick": layer["pick"]["probe"],
                                   "context": {"bindings": {"run": task_id}, "result": result},
                                   "connection": hub_id, "node": hub.node_id, "position": [2.0, 3.0, 4.0]})
    assert probe["target"] == {"binding": "run", "task_id": task_id, "path": "Polar.00000002.dat", "node": "polar"}
    expected = np.asarray(domain_polarization((12, 10, 8), step=2))[2, 3, 4]
    assert np.allclose(probe["sample"]["values"], expected)
    harness.close()
