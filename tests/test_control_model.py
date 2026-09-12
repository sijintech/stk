import uuid

import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from suan.control.app import create_app
from suan.control.policy import DEMO_TEMPLATE

OWNER = "model-mock-owner-12345678901234567890"
HEADERS = {"Authorization": "Bearer " + OWNER}


class Model:
    def __init__(self):
        self.calls = 0
        self.proposals = []
        self.context = None

    async def reply(self, messages, context):
        self.calls += 1
        self.context = context
        return {"content": "已准备结构化操作，等待执行结果。", "actions": self.proposals}


def test_mock_model_atomic_tools_retry_and_metadata_only(tmp_path):
    model = Model()
    app = create_app(tmp_path, OWNER, {"demo-field": DEMO_TEMPLATE}, model=model)
    store = app.state.store
    pairing = store.pairing("node")
    node = store.claim(pairing["code"], "计算节点")
    node_id = node["device_id"]
    store.heartbeat(node_id, {"tasks": [{"id": "a"*32, "name": "测试", "state": "running",
                                       "argv": ["SECRET"], "env": {"TOKEN": "SECRET"}}],
                              "workspaces": [{"id": "b"*32, "name": "项目", "path": "/SECRET"}],
                              "raw_data": "SECRET"})
    good = {"node_id": node_id, "kind": "workspace.create", "payload": {"name": "新项目"}}
    model.proposals = [good, {"node_id": node_id, "kind": "arbitrary.shell", "payload": {}}]
    session, identity = uuid.uuid4().hex, uuid.uuid4().hex
    path = f"/api/v1/sessions/{session}/messages"
    with TestClient(app) as client:
        rejected = client.post(path, headers=HEADERS, json={"id": identity, "content": "创建项目"})
        assert rejected.status_code == 400
        assert store.actions() == []
        model.proposals = [good]
        result = client.post(path, headers=HEADERS, json={"id": identity, "content": "创建项目"})
        assert result.status_code == 200
        assert len(store.actions()) == 1 and store.actions()[0]["state"] == "queued"
        calls = model.calls
        assert client.post(path, headers=HEADERS, json={"id": identity, "content": "创建项目"}).json() == result.json()
        assert model.calls == calls and len(store.actions()) == 1
        assert "SECRET" not in str(model.context)
        assert model.context["devices"][0]["tasks"][0]["id"] == "a"*32
        conflict = client.post(f"/api/v1/sessions/{uuid.uuid4().hex}/messages", headers=HEADERS,
                               json={"id": identity, "content": "创建项目"})
        assert conflict.status_code == 409


def test_mock_model_new_script_requires_review(tmp_path):
    model = Model()
    app = create_app(tmp_path, OWNER, model=model)
    store = app.state.store
    pair = store.pairing("node")
    node = store.claim(pair["code"], "计算节点")
    model.proposals = [{"node_id": node["device_id"], "kind": "task.submit",
                        "payload": {"spec": {"workspace_id": "a"*32, "argv": ["python", "new.py"]}}}]
    with TestClient(app) as client:
        response = client.post(f"/api/v1/sessions/{uuid.uuid4().hex}/messages", headers=HEADERS,
                               json={"id": uuid.uuid4().hex, "content": "运行一个新脚本"})
        assert response.status_code == 200
        assert store.actions()[0]["state"] == "review"
        assert store.actions(node["device_id"], pending=True) == []
