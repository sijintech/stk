import asyncio
import base64
import hashlib
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

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


@pytest.mark.parametrize(("revoked_role", "expected_status"), [("client", 401), ("node", 404)])
def test_live_read_checks_revocation_before_returning_a_reply(tmp_path, monkeypatch, revoked_role, expected_status):
    placeholders = iter(character * 32 for character in "abcd")
    monkeypatch.setattr("suan.control.store.secrets.token_urlsafe", lambda _: next(placeholders))
    with TestClient(create_app(tmp_path, OWNER)) as http:
        node, _ = paired(http)
        viewer, _ = paired(http, "client")
        node_auth = {"Authorization": "Bearer " + node["token"]}
        viewer_auth = {"Authorization": "Bearer " + viewer["token"]}
        route = f"/api/v1/nodes/{node['device_id']}/read"
        task = {"id": "e" * 32, "workspace_id": "f" * 32, "state": "succeeded"}
        body = {"kind": "task.get", "payload": {"task_id": task["id"]}}

        with http.websocket_connect("/api/v1/nodes/connect", headers=node_auth) as ws, ThreadPoolExecutor(1) as pool:
            ws.send_json({"type": "snapshot", "snapshot": {"features": ["read", "task.get"]}})
            deadline = time.monotonic() + 5
            while not any("task.get" in device["snapshot"].get("features", [])
                          for device in http.get("/api/v1/devices", headers=AUTH).json()):
                assert time.monotonic() < deadline
                time.sleep(0.01)

            def read_reply(headers, revoked_device=None):
                pending = pool.submit(http.post, route, headers=headers, json=body)
                sent = ws.receive_json()
                assert sent == {"type": "read", "id": sent["id"], **body}
                if revoked_device is not None:
                    revoked = http.delete(f"/api/v1/devices/{revoked_device}", headers=AUTH)
                    assert revoked.status_code == 200
                ws.send_json({"type": "read_result", "id": sent["id"], "result": task})
                return pending.result(timeout=10)

            before = read_reply(viewer_auth)
            assert before.status_code == 200 and before.json() == {"result": task}
            revoked_device = viewer if revoked_role == "client" else node
            late = read_reply(viewer_auth, revoked_device["device_id"])
            after = http.post(route, headers=viewer_auth, json=body)
            assert late.status_code == after.status_code == expected_status
            assert late.json() == after.json() and "result" not in late.json()
            if revoked_role == "client":
                owner_read = read_reply(AUTH)
                assert owner_read.status_code == 200 and owner_read.json() == {"result": task}
        assert http.get("/api/v1/actions", headers=AUTH).json() == []


def test_event_stream_ends_before_publishing_the_rest_of_a_batch_after_revocation(tmp_path, monkeypatch):
    monkeypatch.setattr("suan.control.store.secrets.token_urlsafe", lambda _: "a" * 32)
    app = create_app(tmp_path, OWNER)
    store = app.state.store
    with TestClient(app) as http:
        viewer, _ = paired(http, "client")
    cursor = store.events()[-1]["id"]
    with store.db() as db:
        store.event(db, "devices.changed", {"device_id": "before-revocation"})
        store.event(db, "devices.changed", {"device_id": "after-revocation"})

    async def revoke_after_first(scope, receive, send):
        async def on_send(message):
            await send(message)
            if message["type"] == "http.response.body" and b"before-revocation" in message.get("body", b""):
                store.revoke(viewer["device_id"])
        await app(scope, receive, on_send)

    auth = {"Authorization": "Bearer " + viewer["token"]}
    with TestClient(revoke_after_first) as http:
        response = http.get("/api/v1/events", params={"after": cursor}, headers=auth)
        assert response.status_code == 200
        assert "before-revocation" in response.text and "after-revocation" not in response.text
        assert http.get("/api/v1/events", headers=auth).status_code == 401


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
    class Model:
        async def reply(self, messages, context):
            return {"content": "Prepared the demo", "actions": [{"node_id": node["device_id"], "kind": "task.submit",
                    "payload": {"workspace_id": first["id"], "template": "demo-field"}}]}

    app = create_app(tmp_path / "control", OWNER, {"demo-field": DEMO_TEMPLATE}, model=Model())
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
            session = "a" * 32
            route = f"/api/v1/sessions/{session}"
            sent = c.post(route + "/messages", json={"id": "b" * 32, "content": "Run the demo"}, headers=AUTH)
            assert sent.status_code == 200, sent.text
            submit = ws.receive_json()["action"]
            task = agent.execute(submit)
            ws.send_json({"type": "result", "id": submit["id"], "result": task})
            deadline = time.monotonic() + 5
            while True:
                refs = c.get(route + "/tasks", headers=AUTH).json()["tasks"]
                assert len(refs) == 1
                if refs[0]["state"] == "succeeded":
                    assert refs[0]["task_id"] == task["id"]
                    assert refs[0]["workspace_id"] == first["id"]
                    assert refs[0]["message_id"] == sent.json()["messages"][-1]["id"]
                    break
                assert time.monotonic() < deadline
                time.sleep(.01)
        # Both GUI/control transport can be gone; Runtime keeps executing.
        result = finish(runtime_client, supervisor, task["id"], timeout=40)
        assert result["state"] == "succeeded", result
        files_path = f"{route}/tasks/{submit['id']}/files"
        assert c.get(files_path, headers=AUTH).status_code == 501
        with c.websocket_connect("/api/v1/nodes/connect", headers=ws_auth) as ws, ThreadPoolExecutor(1) as pool:
            ws.send_json({"type": "snapshot", "snapshot": {"features": ["read", "task.artifacts"]}})
            deadline = time.monotonic() + 5
            while "task.artifacts" not in app.state.store.device(node["device_id"])["snapshot"].get("features", []):
                assert time.monotonic() < deadline
                time.sleep(.01)
            assert c.get(files_path.replace(session, "c" * 32, 1), headers=AUTH).status_code == 404
            events = app.state.store.events()
            pending = pool.submit(c.get, files_path, headers=AUTH)
            read = ws.receive_json()
            assert read == {"type": "read", "id": read["id"], "kind": "task.artifacts",
                            "payload": {"task_id": task["id"]}}
            artifacts = agent.execute({"id": read["id"], "node_id": node["device_id"],
                                       "kind": read["kind"], "payload": read["payload"]})
            ws.send_json({"type": "read_result", "id": read["id"], "result": artifacts})
            published = pending.result(timeout=10)
            assert published.status_code == 200, published.text
            assert published.json() == {"id": session, "action_id": submit["id"], "task_id": task["id"], "more": False,
                                        "files": [{k: row[k] for k in ("path", "size", "sha256")} for row in artifacts]}
            assert app.state.store.events() == events
            pending = pool.submit(c.get, files_path, headers=AUTH)
            read = ws.receive_json()
            ws.send_json({"type": "read_result", "id": read["id"], "result": [
                {"path": "../other.h5", "size": 8, "sha256": "a" * 64},
            ]})
            assert pending.result(timeout=10).status_code == 502
            selected = next(row for row in artifacts if row["path"] == "scalar-0.vti")
            download_path = files_path.removesuffix("s")
            def download_listing(digest):
                future = pool.submit(c.get, download_path, headers=AUTH,
                                     params={"path": selected["path"], "sha256": digest})
                listing = ws.receive_json()
                assert listing["kind"] == "task.artifacts"
                ws.send_json({"type": "read_result", "id": listing["id"], "result": artifacts})
                return future

            assert download_listing("0" * 64).result(timeout=10).status_code == 404
            for corrupt in (False, True):
                pending = download_listing(selected["sha256"])
                read = ws.receive_json()
                assert read["kind"] == "file.read" and read["payload"] == {
                    "task_id": task["id"], "path": selected["path"], "offset": 0,
                }
                chunk = agent.execute({"id": read["id"], "node_id": node["device_id"],
                                       "kind": read["kind"], "payload": read["payload"]})
                raw = base64.b64decode(chunk["data"])
                if corrupt:
                    chunk["data"] = base64.b64encode(bytes([raw[0] ^ 1]) + raw[1:]).decode()
                ws.send_json({"type": "read_result", "id": read["id"], "result": chunk})
                response = pending.result(timeout=10)
                if corrupt:
                    assert response.status_code == 409
                else:
                    assert response.status_code == 200
                    assert response.content == raw
                    assert response.headers["content-disposition"] == "attachment"
            assert app.state.store.events() == events
        assert c.get(files_path, headers=AUTH).status_code == 503
        again = NodeAgent(runtime_client, tmp_path / "another-cache").execute(submit)
        assert again["id"] == task["id"]
        scene = agent.execute(operation(node["device_id"], "view.build", {"task_id": task["id"], "path": "scalar-0.vti"}))
        assert scene["manifest"]["origin"] == [-2.,3.,10.]
        assert scene["mesh"]["indices"]
        probe = agent.execute(operation(node["device_id"], "view.probe", {"task_id": task["id"], "path": "scalar-0.vti", "position": [-1.9,3.15,10.2]}))
        assert probe["values"][0] == pytest.approx(-.7)
        assert len(runtime_client.tasks()) == 1


def test_conversation_download_verifies_multichunk_offsets_and_revocation(tmp_path, monkeypatch):
    monkeypatch.setattr("suan.control.app.CHUNK_SIZE", 3)
    data = b"several chunks"
    sha = hashlib.sha256(data).hexdigest()
    session, task = "a" * 32, "b" * 32

    with TestClient(create_app(tmp_path, OWNER)) as c:
        node, _ = paired(c)
        client, _ = paired(c, "client")
        headers = {"Authorization": "Bearer " + client["token"]}
        node_headers = {"Authorization": "Bearer " + node["token"]}
        store = c.app.state.store
        store.session(session)
        spec = {"workspace_id": "c" * 32}
        submit = operation(node["device_id"], "task.submit", {"spec": spec})
        store.publish_reply("d" * 32, session, "Task created", [(submit, "")])
        store.complete(submit["id"], node["device_id"], {"id": task, "spec": spec})
        store.heartbeat(node["device_id"], {"features": ["read", "task.artifacts", "file.read"]})
        path = f"/api/v1/sessions/{session}/tasks/{submit['id']}/file"
        params = {"path": "result.dat", "sha256": sha}
        with c.websocket_connect("/api/v1/nodes/connect", headers=node_headers) as ws, ThreadPoolExecutor(1) as pool:
            for mode in ("complete", "bad-offset", "revoked"):
                pending = pool.submit(c.get, path, headers=headers, params=params)
                read = ws.receive_json()
                assert read["kind"] == "task.artifacts"
                ws.send_json({"type": "read_result", "id": read["id"], "result": [
                    {"path": "result.dat", "size": len(data), "sha256": sha},
                ]})
                for offset in range(0, len(data), 3):
                    read = ws.receive_json()
                    assert read["kind"] == "file.read" and read["payload"]["offset"] == offset
                    raw = data[offset:offset+3]
                    if offset and mode == "revoked":
                        store.revoke(client["device_id"])
                    next_offset = offset + len(raw) + (1 if offset and mode == "bad-offset" else 0)
                    ws.send_json({"type": "read_result", "id": read["id"], "result": {
                        "data": base64.b64encode(raw).decode(), "offset": next_offset,
                    }})
                    if offset and mode != "complete":
                        break
                result = pending.result(timeout=10)
                assert result.status_code == {"complete": 200, "bad-offset": 502, "revoked": 401}[mode]
                if mode == "complete":
                    assert result.content == data


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


def test_session_history_is_read_only_and_keeps_legacy_creation(tmp_path):
    with TestClient(create_app(tmp_path, OWNER)) as c:
        session, legacy = "a" * 32, "b" * 32
        route = f"/api/v1/sessions/{session}"
        history = route + "/history"
        assert c.get(history).status_code == 401
        assert c.get("/api/v1/sessions/invalid/history", headers=AUTH).status_code == 400
        assert c.get(history, headers=AUTH).status_code == 404
        assert c.get("/api/v1/sessions", headers=AUTH).json() == []

        legacy_route = f"/api/v1/sessions/{legacy}"
        empty = {"id": legacy, "messages": []}
        assert c.get(legacy_route, headers=AUTH).json() == empty
        assert c.get(legacy_route + "/history", headers=AUTH).json() == empty

        sent = c.post(route + "/messages", headers=AUTH, json={"id": "c" * 32, "content": "Read-only history"})
        assert sent.status_code == 200
        before = c.get("/api/v1/sessions", headers=AUTH).json()
        events = c.app.state.store.events()
        saved = c.get(history, headers=AUTH)
        assert saved.status_code == 200
        assert saved.json() == sent.json()
        assert c.get("/api/v1/sessions", headers=AUTH).json() == before
        assert c.app.state.store.events() == events


def test_session_tasks_use_reply_and_runtime_receipts(tmp_path):
    workspace = "b" * 32
    good, wrong, unrelated = "c" * 32, "d" * 32, "e" * 32
    session, other, reply = "1" * 32, "2" * 32, "3" * 32
    spec = {"workspace_id": workspace, "argv": ["private-script"], "name": "private name"}

    class Model:
        async def reply(self, messages, context):
            return {"content": f"Unrelated action {unrelated}", "actions": [
                {"node_id": context["devices"][0]["id"], "kind": "task.submit", "payload": {"spec": spec}},
                {"node_id": context["devices"][0]["id"], "kind": "task.submit", "payload": {"spec": spec}},
                {"node_id": context["devices"][0]["id"], "kind": "task.submit", "payload": {"spec": spec}},
            ]}

    with TestClient(create_app(tmp_path, OWNER, model=Model())) as c:
        node, _ = paired(c)
        node_id = node["device_id"]
        client, _ = paired(c, "client")
        headers = {"Authorization": "Bearer " + client["token"]}
        path = f"/api/v1/sessions/{session}"
        store = c.app.state.store
        assert c.get(path + "/tasks").status_code == 401
        assert c.get(path + "/tasks", headers=headers).status_code == 404
        assert c.get("/api/v1/sessions", headers=headers).json() == []
        c.get(f"/api/v1/sessions/{other}", headers=headers).raise_for_status()
        c.post("/api/v1/actions", headers=AUTH, json={"id": unrelated, "node_id": node_id,
               "kind": "task.submit", "payload": {"spec": spec}}).raise_for_status()
        body = {"id": reply, "content": "Submit two tasks"}
        sent = c.post(path + "/messages", headers=headers, json=body)
        assert sent.status_code == 200, sent.text
        assert c.post(path + "/messages", headers=headers, json=body).json() == sent.json()
        message_id = sent.json()["messages"][-1]["id"]
        tasks = c.get(path + "/tasks", headers=headers).json()
        assert tasks["id"] == session and tasks["more"] is False
        assert len(tasks["tasks"]) == 3
        first, second, third = tasks["tasks"]
        assert first == {"message_id": message_id, "action_id": first["action_id"], "node_id": node_id,
                         "workspace_id": workspace, "state": "review", "task_id": None}
        assert second["action_id"] != first["action_id"]
        assert c.get(f"/api/v1/sessions/{other}/tasks", headers=headers).json()["tasks"] == []
        for item, task_id, target in [(first, good, workspace), (second, wrong, "f" * 32)]:
            action_id = item["action_id"]
            c.post(f"/api/v1/actions/{action_id}/review", headers=AUTH, json={"approved": True}).raise_for_status()
            store.complete(action_id, node_id, {"id": task_id, "spec": {"workspace_id": target}})
        c.post(f"/api/v1/actions/{third['action_id']}/review", headers=AUTH, json={"approved": False}).raise_for_status()
        store.complete(third["action_id"], node_id, {"id": good, "spec": {"workspace_id": workspace}})
        events = store.events()
        receipt = c.get(path + "/tasks", headers=headers).json()["tasks"]
        assert [(item["state"], item["task_id"]) for item in receipt] == [
            ("succeeded", good), ("succeeded", None), ("rejected", None),
        ]
        assert store.events() == events
        store.revoke(node_id)
        assert c.get(path + "/tasks", headers=headers).json()["tasks"] == []
        store.revoke(client["device_id"])
        assert c.get(path + "/tasks", headers=headers).status_code == 401


def test_session_list_labels_are_optional_and_read_only(tmp_path, monkeypatch):
    class ForbiddenModel:
        async def reply(self, messages, context):
            pytest.fail("Listing sessions must not call the model")

    app = create_app(tmp_path, OWNER, model=ForbiddenModel())
    store = app.state.store
    short, long, hidden, empty = (digit * 32 for digit in "abcd")
    for session in (short, long, hidden, empty):
        store.session(session, name=f"Session {session[0]}")
    store.message("1" * 32, short, "assistant", "Assistant text is not a title")
    store.message("2" * 32, short, "user", "  First\tquestion\u200e\u202e\u2067\n details  ")
    text = " \t问题\r\n观察\u2028样品\u202e\0" + "磁畴🙂" * 30
    store.message("3" * 32, long, "user", text)
    store.message("4" * 32, long, "assistant", "The answer should not rename the session")
    store.message("5" * 32, long, "user", "Neither should a later question")
    store.message("6" * 32, hidden, "user", "\t\0\u202e")
    # A wall clock correction must not make the later question the first saved one.
    with store.db() as db:
        db.execute("UPDATE messages SET created = 0 WHERE id = ?", ("5" * 32,))

    path = "/api/v1/sessions"
    labeled_path = path + "?include_labels=true"
    with TestClient(app) as c:
        client, _ = paired(c, role="client")
        node, _ = paired(c)
        client_headers = {"Authorization": "Bearer " + client["token"]}
        assert c.get(labeled_path).status_code == 401
        assert c.get(labeled_path, headers={"Authorization": "Bearer " + node["token"]}).status_code == 403

        legacy = c.get(path, headers=client_headers).json()
        assert [row["id"] for row in legacy] == [empty, hidden, long, short]
        assert all(set(row) == {"id", "name", "created"} for row in legacy)
        assert c.get(path + "?include_labels=false", headers=client_headers).json() == legacy
        before = {row["id"]: store.session_history(row["id"]) for row in legacy}
        events = store.events()

        statements = []
        original_db = store.db

        @contextmanager
        def trace_db():
            with original_db() as db:
                db.set_trace_callback(statements.append)
                yield db

        # The owner credential adds no database authentication query.
        with monkeypatch.context() as patch:
            patch.setattr(store, "db", trace_db)
            response = c.get(labeled_path, headers=AUTH)
        assert response.status_code == 200
        assert len(statements) == 1 and statements[0].lstrip().startswith("SELECT")

        expected_long = ("问题 观察 样品 " + "磁畴🙂" * 30)[:79] + "…"
        labels = {short: "First question details", long: expected_long, hidden: "", empty: ""}
        expected = [{**row, "label": labels[row["id"]]} for row in legacy]
        assert response.json() == c.get(labeled_path, headers=client_headers).json() == expected
        assert len(expected_long) == 80 and len(expected_long.encode("utf-8")) > 80
        assert c.get(path, headers=client_headers).json() == legacy
        assert {row["id"]: store.session_history(row["id"]) for row in legacy} == before
        assert store.events() == events

        store.message("7" * 32, long, "assistant", "Later answer")
        store.message("8" * 32, long, "user", "Still later question")
        assert c.get(labeled_path, headers=client_headers).json() == expected


def test_remote_agent_requires_tls():
    assert endpoint("https://control.example", True) == "wss://control.example/api/v1/nodes/connect"
    for url in ["http://remote.example", "https://user:secret@example.com", "https://example.com/?token=secret"]:
        with pytest.raises(ValueError): endpoint(url)
