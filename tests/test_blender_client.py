import copy
import json
from pathlib import Path
import shutil
import subprocess
from urllib.error import URLError
import uuid

import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from suan.blender_client.bridge import Bridge
from suan.blender_client.scene import demo_scene, validate_scene
from suan.control.agent import NodeAgent
from suan.control.app import create_app
from suan.control.policy import DEMO_TEMPLATE
from suan.runtime.common import atomic_json, read_json
from conftest import finish

OWNER = "blender-test-owner-token-1234567890"


class Connection:
    def __init__(self, client):
        self.client, self.lose_response = client, False

    def request(self, method, path, body=None):
        response = self.client.request(method, "/api/v1/" + path, json=body,
                                       headers={"Authorization": "Bearer " + OWNER})
        if response.status_code >= 400:
            raise ValueError(response.json().get("detail"))
        if self.lose_response and method == "POST" and path == "actions":
            self.lose_response = False
            raise URLError("response lost after server accepted operation")
        return response.json()


def command(kind, payload, **extra):
    return {"id": uuid.uuid4().hex, "kind": kind, "payload": payload, **extra}


def test_native_camera_and_original_coordinate_picking(tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler is not available")
    root = Path(__file__).resolve().parents[1] / "blender"
    binary = tmp_path / "scene-test"
    subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root / "source/blender/editors/space_stk"),
                    str(root / "tests/scene_test.cc"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


@pytest.mark.parametrize("mutation", [
    lambda s: s["mesh"]["indices"].append(999999),
    lambda s: s["mesh"]["positions"][0].__setitem__(0, float("nan")),
    lambda s: s["manifest"].__setitem__("spacing", [0,1,1]),
    lambda s: s["manifest"].__setitem__("value_range", [5,-5]),
])
def test_reject_invalid_native_scene(mutation):
    scene = demo_scene()
    validate_scene(scene)
    mutation(scene)
    with pytest.raises(ValueError):
        validate_scene(scene)


def test_bridge_reconnect_and_scientific_loop(runtime, tmp_path):
    client, supervisor, _, _ = runtime
    app = create_app(tmp_path / "control", OWNER, {"demo-field": DEMO_TEMPLATE})
    with TestClient(app) as http:
        connection = Connection(http)
        pairing = connection.request("POST", "pairings", {"role": "node"})
        node = connection.request("POST", "pairings/claim", {"code": pairing["code"], "name": "科学节点"})
        node_id = node["device_id"]
        bridge = Bridge(tmp_path / "desktop", connection)
        bridge.execute(command("select", {"node_id": node_id}))
        create = command("workspace.create", {"name": "解析场项目"})
        atomic_json(bridge.root / "commands" / (create["id"] + ".json"), create)
        connection.lose_response = True
        bridge.tick()
        assert (bridge.root / "commands" / (create["id"] + ".json")).exists()
        # Simulate the entire GUI/bridge restarting after a lost HTTP response.
        bridge = Bridge(bridge.root, connection)
        bridge.tick()
        actions = connection.request("GET", "actions")
        assert len(actions) == 1 and actions[0]["id"] == create["id"]
        agent = NodeAgent(client, tmp_path / "agent")

        def execute(cmd):
            bridge.execute(cmd)
            record = connection.request("GET", "actions/" + cmd["id"])
            result = agent.execute(record["request"])
            # Replaying a node command must also return the same result.
            assert agent.execute(record["request"]) == result
            app.state.store.complete(cmd["id"], node_id, result=result)
            bridge.refresh()
            return result

        result = execute(create)
        assert len(client.workspaces()) == 1
        assert bridge.state["selection"]["workspace_id"] == result["id"]
        submitted = execute(command("task.submit", {"workspace_id": result["id"], "template": "demo-field"}))
        assert finish(client, supervisor, submitted["id"])["state"] == "succeeded"
        assert len(client.tasks()) == 1
        execute(command("task.artifacts", {"task_id": submitted["id"]}))
        assert {a["path"] for a in bridge.state["artifacts"]} >= {"scalar-0.vti", "scalar-1.vti"}
        bridge.execute(command("select", {"path": "scalar-0.vti"}))
        view = command("view.build", {"task_id": submitted["id"], "path": "scalar-0.vti",
                                        "options": {"mode": "slice", "axis": 2, "index": 3}})
        execute(view)
        scene = validate_scene(read_json(bridge.root / "scene.json"))
        assert scene["manifest"]["source"]["node_id"] == node_id
        assert scene["manifest"]["units"] == "Pa"
        assert scene["manifest"]["coordinate_units"] == "m"
        assert scene["manifest"]["timestep"] == 0
        point = [-1.5, 3.6, 11.2]
        probe = execute(command("view.probe", {"task_id": submitted["id"], "path": "scalar-0.vti", "position": point}))
        assert probe["values"][0] == pytest.approx(point[0] + 2*point[1] - .5*point[2])
        # A late result for an older camera/view request cannot replace the new view.
        bridge.state["view_request"] = uuid.uuid4().hex
        original = (bridge.root / "scene.json").read_bytes()
        old = connection.request("GET", "actions/" + view["id"])
        bridge.apply_result(old)
        assert (bridge.root / "scene.json").read_bytes() == original
        bridge.execute(command("select", {"path": "scalar-1.vti"}))
        later = execute(command("view.build", {"task_id": submitted["id"], "path": "scalar-1.vti",
                                               "options": {"mode": "slice", "axis": 2, "index": 3}}))
        assert later["manifest"]["timestep"] == 1
        assert later["mesh"]["values"] == pytest.approx([v+2 for v in scene["mesh"]["values"]])
        with pytest.raises(ValueError, match="time step"):
            agent.execute({"id": uuid.uuid4().hex, "node_id": node_id, "kind": "view.build",
                           "payload": {"task_id": submitted["id"], "path": "scalar-1.vti", "options": {"timestep": 0}}})
        # Discarding desktop state has no ownership over the running Runtime.
        del bridge
        assert client.task(submitted["id"])["state"] == "succeeded"


def test_selection_clears_stale_task_and_receipt_conflicts(tmp_path):
    bridge = Bridge(tmp_path, connection=object())
    bridge.state["selection"].update(node_id="a"*32, workspace_id="b"*32, task_id="c"*32, path="old.vti")
    bridge.state.update(artifacts=[{"path": "old.vti"}], logs="old task log")
    select = command("select", {"workspace_id": "d"*32})
    bridge.execute(select)
    assert bridge.state["selection"]["task_id"] == ""
    assert bridge.state["artifacts"] == [] and bridge.state["logs"] == ""
    bridge.execute(select)
    changed = copy.deepcopy(select)
    changed["payload"]["workspace_id"] = "e"*32
    with pytest.raises(ValueError, match="reused"):
        bridge.execute(changed)


def test_review_requires_inspecting_concrete_request(tmp_path):
    bridge = Bridge(tmp_path, connection=object())
    with pytest.raises(ValueError, match="先查看"):
        bridge.execute(command("review", {"action_id": "a"*32, "approved": True}))


def test_sse_resumes_cursor_and_ignores_already_seen_events(monkeypatch):
    import io
    import threading
    from suan.blender_client.bridge import ControlConnection
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return io.BytesIO(b"id: 2\ndata: {}\n\nid: 3\ndata: {}\n\n: heartbeat\n\nid: 4\ndata: {}\n\n")

    monkeypatch.setattr("suan.blender_client.bridge.build_opener", lambda *args: Opener())
    connection = ControlConnection("http://127.0.0.1:8790", "test-token")
    assert list(connection.events(2, threading.Event())) == [3, 4]
    assert requests[0].get_header("Last-event-id") == "2"


def test_closing_launcher_keeps_runtime_job_alive(runtime, tmp_path, monkeypatch):
    from suan.blender_client.launcher import main
    import sys
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace("GUI lifetime")
    job = client.submit({"workspace_id": workspace["id"],
                         "argv": [sys.executable, "-c", "import time; time.sleep(30)"]})
    supervisor.tick()
    assert client.task(job["id"])["state"] == "running"
    # Exercise the real bridge process owner; simulate an immediately closed
    # native window so this test also runs on machines without a display server.
    monkeypatch.setattr("suan.blender_client.launcher.shutil.which", lambda name: sys.executable)
    monkeypatch.setattr("suan.blender_client.launcher.subprocess.call", lambda *args, **kwargs: 0)
    assert main(["--state-dir", str(tmp_path / "launcher")]) == 0
    supervisor.tick()
    assert client.task(job["id"])["state"] == "running"
    client.cancel(job["id"])
