import asyncio
import sys
import time
import uuid

import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from suan.control.app import create_app
from suan.control.agent import NodeAgent, endpoint
from suan.control.store import ControlStore
from suan.control.policy import DEMO_TEMPLATE
from conftest import finish

OWNER = "test-owner-credential-" + "x"*32
AUTH = {"Authorization": "Bearer " + OWNER}


def paired(client, role="node"):
    pair = client.post("/api/v1/pairings", json={"role": role}, headers=AUTH).json()
    result = client.post("/api/v1/pairings/claim", json={"code": pair["code"], "name": "测试节点"})
    assert result.status_code == 200
    return result.json(), pair


def operation(node_id, kind, payload):
    return {"id": uuid.uuid4().hex, "node_id": node_id, "kind": kind, "payload": payload}


def test_pairing_auth_revocation_and_replay(tmp_path):
    app = create_app(tmp_path, OWNER)
    with TestClient(app) as c:
        assert c.get("/api/v1/devices").status_code == 401
        credentials, pair = paired(c)
        assert c.post("/api/v1/pairings/claim", json={"code": pair["code"], "name": "replay"}).status_code == 400
        assert c.get("/api/v1/devices", headers={"Authorization": "Bearer " + credentials["token"]}).status_code == 403
        assert credentials["token"].encode() not in (tmp_path / "control.sqlite3").read_bytes()
        c.delete("/api/v1/devices/" + credentials["device_id"], headers=AUTH)
        assert app.state.store.authenticate(credentials["token"]) is None
        events = app.state.store.events()
        assert [e["id"] for e in app.state.store.events(events[0]["id"])] == [e["id"] for e in events[1:]]
        reopened = ControlStore(tmp_path)
        assert reopened.events() == events


def test_action_review_and_idempotency(tmp_path):
    with TestClient(create_app(tmp_path, OWNER, {"demo-field": DEMO_TEMPLATE})) as c:
        node, _ = paired(c)
        spec = {"workspace_id": "a"*32, **DEMO_TEMPLATE}
        a = operation(node["device_id"], "task.submit", {"spec": spec, "template": "demo-field"})
        assert c.post("/api/v1/actions", headers=AUTH, json=a).json()["state"] == "queued"
        assert c.post("/api/v1/actions", headers=AUTH, json=a).json()["id"] == a["id"]
        a["payload"]["spec"]["argv"] = ["arbitrary-program"]
        assert c.post("/api/v1/actions", headers=AUTH, json=a).status_code == 400
        a["id"] = uuid.uuid4().hex
        assert c.post("/api/v1/actions", headers=AUTH, json=a).json()["state"] == "review"
        assert c.post(f"/api/v1/actions/{a['id']}/review", headers=AUTH, json={"approved": True}).json()["state"] == "queued"
        a["id"] = uuid.uuid4().hex
        a["payload"]["spec"] = {**spec, "argv": DEMO_TEMPLATE["argv"], "resources": {"cpus": 64}}
        assert c.post("/api/v1/actions", headers=AUTH, json=a).json()["state"] == "review"


def test_agent_runtime_roundtrip_reconnect_and_original_probe(runtime, tmp_path):
    runtime_client, supervisor, _, _ = runtime
    app = create_app(tmp_path / "control", OWNER, {"demo-field": DEMO_TEMPLATE})
    agent = NodeAgent(runtime_client, tmp_path / "agent")
    with TestClient(app) as c:
        node, _ = paired(c)
        ws_auth = {"Authorization": "Bearer " + node["token"]}
        workspace = operation(node["device_id"], "workspace.create", {"name": "中文项目"})
        c.post("/api/v1/actions", json=workspace, headers=AUTH)
        # Execute but lose the acknowledgement. Runtime + restarted agent deduplicate.
        with c.websocket_connect("/api/v1/nodes/connect", headers=ws_auth) as ws:
            sent = ws.receive_json()["action"]
            first = agent.execute(sent)
        agent = NodeAgent(runtime_client, tmp_path / "new-agent-cache")
        with c.websocket_connect("/api/v1/nodes/connect", headers=ws_auth) as ws:
            sent = ws.receive_json()["action"]
            second = agent.execute(sent)
            assert first["id"] == second["id"]
            ws.send_json({"type": "result", "id": sent["id"], "result": second})
            submit = operation(node["device_id"], "task.submit", {"spec": {"workspace_id": first["id"], **DEMO_TEMPLATE}, "template": "demo-field"})
            c.post("/api/v1/actions", json=submit, headers=AUTH)
            task = agent.execute(ws.receive_json()["action"])
            ws.send_json({"type": "result", "id": submit["id"], "result": task})
        # Both GUI/control transport can be gone; Runtime keeps executing.
        result = finish(runtime_client, supervisor, task["id"], timeout=40)
        assert result["state"] == "succeeded", result
        again = NodeAgent(runtime_client, tmp_path / "another-cache").execute(submit)
        assert again["id"] == task["id"]
        scene = agent.execute(operation(node["device_id"], "view.build", {"task_id": task["id"], "path": "scalar-0.vti"}))
        assert scene["manifest"]["origin"] == [-2.,3.,10.]
        assert scene["mesh"]["indices"]
        probe = agent.execute(operation(node["device_id"], "view.probe", {"task_id": task["id"], "path": "scalar-0.vti", "position": [-1.9,3.15,10.2]}))
        assert probe["values"][0] == pytest.approx(-.7)
        assert len(runtime_client.tasks()) == 1


def test_chat_fake_model_policy_session_restore(tmp_path):
    class FakeModel:
        calls = 0
        async def reply(self, messages, context):
            self.calls += 1
            assert "snapshot" not in str(context)
            return {"content": "请复核计算命令。", "actions": [{"node_id": context["devices"][0]["id"], "kind": "task.submit", "payload": {
                "spec": {"workspace_id": "b"*32, "argv": ["new-script"]}}}]}
    model = FakeModel()
    with TestClient(create_app(tmp_path, OWNER, model=model)) as c:
        paired(c)
        session = uuid.uuid4().hex
        body = {"id": uuid.uuid4().hex, "content": "帮我运行新任务"}
        route = f"/api/v1/sessions/{session}/messages"
        first = c.post(route, json=body, headers=AUTH)
        assert first.status_code == 200, first.text
        assert c.post(route, json=body, headers=AUTH).json() == first.json()
        assert model.calls == 1
        assert c.get("/api/v1/actions", headers=AUTH).json()[0]["state"] == "review"
        assert len(c.get(f"/api/v1/sessions/{session}", headers=AUTH).json()["messages"]) == 2


def test_remote_agent_requires_tls():
    assert endpoint("https://control.example", True) == "wss://control.example/api/v1/nodes/connect"
    for url in ["http://remote.example", "https://user:secret@example.com", "https://example.com/?token=secret"]:
        with pytest.raises(ValueError): endpoint(url)
