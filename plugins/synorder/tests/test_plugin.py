"""Installed plugin integration. All stores, credentials and solver data are synthetic."""
import json
import os
import sys
import threading
import time
import uuid

import pytest

pytest.importorskip("synorder_gui.plugins")
pytest.importorskip("synorder_stk")

from fastapi.testclient import TestClient
from synorder_connectors.connections import bind
from synorder_connectors.execution import ExecutionWorker
from synorder_gui.native_views import panels, values, fields
from synorder_gui.plugins import validate_view
from synorder_interaction import InteractionStore
from synorder_interaction.contracts import InteractionError
from synorder_native.bridge import Bridge
from synorder_workbench.demo import ACTOR, demo_store
from synorder_workbench.hub.app import build_registry, create_app
from synorder_workspace import load_workspace, WorkspaceError
from synorder_workspace.packs import configure_pack, get_pack, install_pack

ORIGIN = "http://127.0.0.1:8766"


@pytest.fixture
def service():
    with demo_store() as work:
        install_pack(work.workspace, "synorder.stk")
        work.workspace = load_workspace(work.workspace.root, allow_test_storage=True)
        store = InteractionStore(work)
        store.initialize()
        app = create_app(store, origin=ORIGIN, local_actor=ACTOR, run_workers=False)
        with TestClient(app, base_url=ORIGIN) as client:
            csrf = client.get("/api/hub/session").json()["csrf"]
            client.headers.update({"Origin": ORIGIN, "X-Synorder-Token": csrf})
            yield store, client, app


def post(client, path, data):
    response = client.post("/api/hub" + path, json=data)
    assert response.status_code == 200, response.text
    return response.json()


def submit(store, client):
    chat = post(client, "/conversations", {"space_id": "project-space", "request_id": uuid.uuid4().hex, "title": "手机发起的解析场计算"})
    saved = post(client, "/proposals", {"conversation_id": chat["id"], "request_id": uuid.uuid4().hex, "name": "stk.configuration.save", "values": {
        "title": "解析场", "connector_id": "stk-local", "amplitudes": [2], "backend": "local", "cpus": 1, "walltime_seconds": 120,
    }})
    ref = saved["result"]
    request = {"conversation_id": chat["id"], "request_id": uuid.uuid4().hex, "name": "stk.submit", "values": {}, "target_id": ref["resource_id"], "expected_version": ref["version"]}
    proposed = post(client, "/proposals", request)
    assert post(client, "/proposals", request) == proposed
    result = post(client, "/proposals/" + proposed["proposal_id"] + "/confirm", {"preview_hash": proposed["preview_hash"]})
    assert post(client, "/proposals/" + proposed["proposal_id"] + "/confirm", {"preview_hash": proposed["preview_hash"]}) == result
    return result["executions"][0]["resource_id"]


class Connection:
    def __init__(self, client): self.client = client
    def call(self, path, body=None):
        response = self.client.get("/api/hub" + path) if body is None else self.client.post("/api/hub" + path, json=body)
        if response.status_code >= 400:
            from synorder_native.transport import RemoteError
            raise RemoteError(response.status_code, response.text)
        return response.json()


def test_installed_pack_and_shared_declarative_views(service):
    store, client, app = service
    pack = get_pack("stk")
    assert pack.id == "synorder.stk" and len(pack.digest) == 64
    session = client.get("/api/hub/session").json()
    assert any(c["id"] == pack.id for c in session["capabilities"])
    registry = build_registry(store.workspace)
    for surface in ("native", "web", "mobile"):
        response = client.get(f"/api/hub/views/stk.workbench?space_id=project-space&surface={surface}")
        assert response.status_code == 200, response.text
        view = validate_view(response.json(), registry.actions, registry.queries)
        assert panels(view)["inspector"]
        button = next(i for i in view["panels"]["inspector"] if i["kind"] == "button")
        assert values(button, fields(view), {"plugin_amplitude": "1.00000000000001"})["amplitudes"] == [1.00000000000001]
    assert client.get("/api/hub/views/stk.workbench?space_id=lin-private").status_code == 403
    assert client.post("/api/hub/queries/stk.scene", json={"space_id": "project-space", "values": {}}).status_code == 422


def test_disabled_pack_keeps_accepted_methods_and_blocks_old_app_writes(service):
    store, client, app = service
    bind(store, "stk-local", "project-space", "stk", {"url": "http://127.0.0.1:12345", "token_env": "SYNORDER_STK_TEST_TOKEN"})
    rid = submit(store, client)
    with pytest.raises(WorkspaceError, match="active execution"):
        configure_pack(store.workspace, "stk", command="remove")
    configure_pack(store.workspace, "stk", command="disable")
    old = client.post("/api/hub/proposals", json={"conversation_id": store.conversations(ACTOR, "project-space")[0]["id"], "request_id": uuid.uuid4().hex, "name": "stk.submit", "values": {}})
    assert old.status_code == 422
    store.work.workspace = load_workspace(store.workspace.root, allow_test_storage=True)
    new_registry = build_registry(store.work.workspace)
    assert "synorder.stk" not in new_registry.capabilities
    assert "stk.analytic-field.v1" in new_registry.methods
    # Disable is not a task cancellation and cannot erase its result history.
    assert store.resource(ACTOR, rid)["body"]["plugin"]["version"] == "0.1.0"
    with store.connect() as db:
        assert db.execute("SELECT cancel_requested FROM executions WHERE id=?", (rid,)).fetchone()[0] == 0


def test_lock_checked_before_provider_import(service, monkeypatch):
    store, client, app = service
    from synorder_workspace.files import write_yaml, read_yaml
    lock = read_yaml(store.workspace.root / "synorder.lock")
    lock["packs"]["synorder.stk"]["sha256"] = "0" * 64
    write_yaml(store.workspace.root / "synorder.lock", lock)
    import importlib
    original = importlib.import_module
    def guarded(name, *args):
        assert not name.startswith("synorder_stk"), "Unlocked provider executed"
        return original(name, *args)
    monkeypatch.setattr(importlib, "import_module", guarded)
    with pytest.raises(WorkspaceError, match="lock mismatch"):
        build_registry(store.workspace)


@pytest.mark.parametrize("widget", [
    {"kind": "html", "label": "<script>bad()</script>"},
    {"kind": "button", "label": "run", "action": "arbitrary.shell"},
    {"kind": "number", "label": "NaN", "field": "x", "value": float("nan")},
    {"kind": "table", "label": "bad row", "columns": ["one"], "rows": [{"resource_id": "x", "version": 1, "cells": []}]},
])
def test_inert_view_contract_rejects_unbounded_or_executable_data(widget):
    with pytest.raises(InteractionError):
        validate_view({"version": 1, "id": "test", "title": "test", "panels": {"content": [widget]}}, {})


def test_mobile_submit_runtime_survives_desktop_close_and_scene_probe(service, tmp_path, monkeypatch):
    from suan.runtime.common import init_config
    from suan.runtime.server import RuntimeHTTPServer
    from suan.runtime.supervisor import Supervisor
    store, client, app = service
    config = init_config(tmp_path / "runtime", tmp_path / "workspaces", port=0)
    config["python"] = os.environ.get("STK_TEST_RUNTIME_PYTHON", sys.executable)
    server, supervisor = RuntimeHTTPServer(config), Supervisor(config)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    monkeypatch.setenv("SYNORDER_STK_TEST_TOKEN", config["token"])
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    bind(store, "stk-local", "project-space", "stk", {"url": f"http://127.0.0.1:{server.server_port}", "token_env": "SYNORDER_STK_TEST_TOKEN"})
    try:
        rid = submit(store, client)
        desktop = Bridge(tmp_path / "desktop", ORIGIN, connection=Connection(client))
        desktop.ui.update(space_id="project-space", view="stk.workbench", resource_id=rid)
        assert desktop.tick()["title"] == "STK 科学工作台"
        desktop.close()
        worker = app.state.executions
        worker.tick()
        # Recreate the worker while an accepted Runtime job exists.
        worker = ExecutionWorker(store, methods=build_registry(store.workspace).methods.values())
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            supervisor.tick(); worker.tick()
            obj = store.resource(ACTOR, rid)
            if obj["body"].get("state") in {"succeeded", "failed", "cancelled", "timed_out"}:
                break
            time.sleep(.1)
        assert obj["body"]["state"] == "succeeded", obj["body"]
        assert obj["body"]["verification"] == "passed"
        assert len(supervisor.store.tasks()) == 1
        source = {"resource_id": rid, "version": obj["version"], "artifact": "field.vtk"}
        scene = post(client, "/queries/stk.scene", {"space_id": "project-space", "values": {**source, "mode": "slice", "axis": 2, "index": 1}})
        assert scene["manifest"]["dimensions"] == [8, 6, 4]
        probe = post(client, "/queries/stk.probe", {"space_id": "project-space", "values": {**source, "position": [1.25, 2.5, 1.5]}})
        assert probe["values"] == pytest.approx([21.5], rel=0, abs=1e-12)
        assert probe["units"] == "无量纲"
        resumed = Bridge(tmp_path / "desktop", ORIGIN, connection=Connection(client))
        state = resumed.tick()
        assert state["title"] == "STK 科学工作台"
        assert any(i.get("command") == "presentation.scene" for i in state["panels"]["content"])
        resumed.close()
        # A task created by the previous client is adopted by remote ID, with no replay.
        from suan.runtime.client import RuntimeClient
        runtime = RuntimeClient(f"http://127.0.0.1:{server.server_port}", config["token"])
        workspace = runtime.create_workspace("legacy-client")
        legacy = runtime.submit({"workspace_id": workspace["id"], "name": "legacy-task", "backend": "local", "argv": [config["python"], "-c", "print('legacy result')"], "outputs": []})
        cid = store.conversations(ACTOR, "project-space")[0]["id"]
        proposed = post(client, "/proposals", {"conversation_id": cid, "request_id": uuid.uuid4().hex, "name": "stk.attach", "values": {"connector_id": "stk-local", "task_id": legacy["id"]}})
        attached = post(client, "/proposals/" + proposed["proposal_id"] + "/confirm", {"preview_hash": proposed["preview_hash"]})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            supervisor.tick(); worker.tick()
            imported = store.resource(ACTOR, attached["resource_id"])
            if imported["body"].get("state") == "succeeded": break
            time.sleep(.1)
        assert imported["body"]["state"] == "succeeded", imported["body"]
        assert imported["body"]["remote_id"] == legacy["id"]
        assert len(runtime.tasks()) == 2
    finally:
        for task in supervisor.store.tasks():
            if task["state"] not in {"succeeded", "failed", "cancelled", "timed_out"}:
                supervisor.service.cancel(task["id"])
        supervisor.tick()
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_outbound_node_transport_reconnect_and_no_runtime_token_leak(service, tmp_path, monkeypatch):
    from suan.runtime.common import init_config
    from suan.runtime.server import RuntimeHTTPServer
    from suan.runtime.client import RuntimeClient
    from suan.runtime.synorder_node import SynorderNode
    from synorder_connectors.connections import StkClient
    from synorder_interaction.contracts import Unavailable
    store, client, app = service
    config = init_config(tmp_path / "runtime", tmp_path / "workspaces", port=0)
    server = RuntimeHTTPServer(config)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    node = SynorderNode(RuntimeClient(f"http://127.0.0.1:{server.server_port}", config["token"]))
    token = uuid.uuid4().hex
    monkeypatch.setenv("SYNORDER_NODE_TEST", token)
    binding = {"transport": "node", "node_id": "test-node", "token_env": "SYNORDER_NODE_TEST"}
    bind(store, "node-runtime", "project-space", "stk", binding)
    remote = StkClient(binding, transport=app.state.nodes.transport("test-node"))
    errors, requests = [], []
    try:
        with pytest.raises(Unavailable, match="离线"):
            remote.call("GET", "health")
        # Two independently paired transport sessions see the same Runtime state.
        for reconnect in range(2):
            with TestClient(app, base_url=ORIGIN) as agent_client:
                with agent_client.websocket_connect("ws://127.0.0.1:8766/api/hub/nodes/test-node", headers={"Authorization": "Bearer " + token}) as ws:
                    def perform():
                        try:
                            assert remote.call("GET", "health")["api_version"] == 1
                            remote.call("POST", "workspaces", {"name": "outbound-node", "idempotency_key": "test-node-workspace"})
                            assert len(remote.call("GET", "workspaces")) == 1
                        except Exception as exc:
                            errors.append(exc)
                    caller = threading.Thread(target=perform)
                    caller.start()
                    for _ in range(3):
                        request = ws.receive_json()
                        requests.append(request)
                        assert config["token"] not in json.dumps(request)
                        ws.send_json(node.execute(request))
                    caller.join(timeout=5)
                    assert not caller.is_alive()
                    assert not errors, errors
        assert len(node.runtime.workspaces()) == 1
        with pytest.raises(Unavailable, match="离线"):
            remote.call("GET", "health")
        with pytest.raises(ValueError):
            node.execute({"path": "http://other-host/secrets", "method": "GET", "data": "", "id": "x"})
    finally:
        remote.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
