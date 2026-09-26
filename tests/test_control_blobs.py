"""Hub blob store: node-only uploads, client downloads, verification, caps, result offloading, migration."""
import hashlib
import json
import sqlite3
import threading
import time
import uuid

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from suan.control import store as store_module  # noqa: E402
from suan.control.agent import BlobUploadError, BlobUploader, hub_features  # noqa: E402
from suan.control.app import create_app  # noqa: E402
from suan.control.store import RESULT_INLINE_LIMIT, ControlStore  # noqa: E402

OWNER = "test-owner-credential-" + "x" * 32
AUTH = {"Authorization": "Bearer " + OWNER}


def bearer(token):
    return {"Authorization": "Bearer " + token}


def paired(http, role):
    code = http.post("/api/v1/pairings", json={"role": role}, headers=AUTH).json()["code"]
    return http.post("/api/v1/pairings/claim", json={"code": code, "name": role}).json()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def leftovers(root):
    return [p for p in (root / "blobs" / ".incoming").iterdir()]


def test_blob_upload_is_node_only_verified_and_idempotent(tmp_path):
    with TestClient(create_app(tmp_path, OWNER)) as http:
        node, client = paired(http, "node"), paired(http, "client")
        data = b"payload buffer \x00\x01" * 100
        digest = sha(data)
        route = "/api/v1/blobs/" + digest
        assert http.put(route, content=data).status_code == 401
        assert http.put(route, content=data, headers=bearer("not-a-credential")).status_code == 401
        assert http.put(route, content=data, headers=AUTH).status_code == 403  # the owner is not a node
        assert http.put(route, content=data, headers=bearer(client["token"])).status_code == 403
        assert http.head(route, headers=bearer(node["token"])).status_code == 404

        created = http.put(route, content=data, headers=bearer(node["token"]))
        assert created.status_code == 201 and created.json() == {"sha256": digest, "size": len(data), "created": True}
        again = http.put(route, content=data, headers=bearer(node["token"]))
        assert again.status_code == 200 and again.json()["created"] is False

        # Nodes may check existence; only clients and the owner read bytes.
        head = http.head(route, headers=bearer(node["token"]))
        assert head.status_code == 200 and head.headers["content-length"] == str(len(data))
        assert http.get(route, headers=bearer(node["token"])).status_code == 403
        assert http.get(route).status_code == 401
        for who in (AUTH, bearer(client["token"])):
            response = http.get(route, headers=who)
            assert response.status_code == 200 and response.content == data
            assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
            assert response.headers["content-type"] == "application/octet-stream"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["etag"] == f'"{digest}"'
        partial = http.get(route, headers={**AUTH, "Range": "bytes=2-9"})
        if partial.status_code == 206:  # Range support comes from Starlette's FileResponse
            assert partial.content == data[2:10]

        missing = "0" * 64
        assert http.get("/api/v1/blobs/" + missing, headers=AUTH).status_code == 404
        for bad in ("A" * 64, "abc", "../" + "0" * 61):
            assert http.get("/api/v1/blobs/" + bad, headers=AUTH).status_code in (400, 404)
            assert http.put("/api/v1/blobs/" + bad, content=b"x", headers=bearer(node["token"])).status_code in (400, 404)

        # A revoked node can no longer upload.
        http.delete("/api/v1/devices/" + node["device_id"], headers=AUTH)
        assert http.put("/api/v1/blobs/" + sha(b"late"), content=b"late",
                        headers=bearer(node["token"])).status_code == 401
    assert leftovers(tmp_path) == []
    stored = tmp_path / "blobs" / digest[:2] / digest
    assert stored.read_bytes() == data and oct(stored.stat().st_mode & 0o777) == "0o600"


def test_hash_mismatch_and_size_cap_leave_nothing_behind(tmp_path):
    with TestClient(create_app(tmp_path, OWNER, blob_max_bytes=1024)) as http:
        node = paired(http, "node")
        data = b"x" * 100
        wrong = http.put("/api/v1/blobs/" + sha(b"other bytes"), content=data, headers=bearer(node["token"]))
        assert wrong.status_code == 400 and "sha256" in wrong.json()["detail"]
        assert http.head("/api/v1/blobs/" + sha(b"other bytes"), headers=AUTH).status_code == 404
        big = b"y" * 2048
        assert http.put("/api/v1/blobs/" + sha(big), content=big, headers=bearer(node["token"])).status_code == 413

        def chunks():  # no Content-Length: the cap applies while streaming
            for _ in range(4):
                yield b"z" * 512
        streamed = http.put("/api/v1/blobs/" + sha(b"z" * 2048), content=chunks(), headers=bearer(node["token"]))
        assert streamed.status_code == 413
        assert http.put("/api/v1/blobs/" + sha(data), content=data, headers=bearer(node["token"])).status_code == 201
        # The upload cap limits nodes, not results the hub offloads itself (bounded by the WebSocket frame).
        store = http.app.state.store
        identity = _complete(http, store, node, {"text": "r" * (RESULT_INLINE_LIMIT * 2)})
        assert http.get("/api/v1/actions/" + identity, headers=AUTH).json()["result"]["text"] == "r" * (
            RESULT_INLINE_LIMIT * 2)
    assert leftovers(tmp_path) == []
    assert not (tmp_path / "blobs" / sha(big)[:2] / sha(big)).exists()


def test_health_advertises_features_and_graph_documents_need_a_client(tmp_path):
    with TestClient(create_app(tmp_path, OWNER)) as http:
        health = http.get("/api/v1/health").json()
        assert health["api_version"] == 1 and {"blobs", "graph", "task.events"} <= set(health["features"])
        node = paired(http, "node")
        for route in ("/api/v1/graphs/catalog", "/api/v1/graphs/presets"):
            assert http.get(route).status_code == 401
            assert http.get(route, headers=bearer(node["token"])).status_code == 403
        catalog = http.get("/api/v1/graphs/catalog", headers=AUTH).json()
        assert catalog["schema"] == "stk.catalog/1"
        assert "stk.source.muferro_run@1" in {entry["id"] for entry in catalog["nodes"]}
        presets = http.get("/api/v1/graphs/presets", headers=AUTH).json()
        assert isinstance(presets, list)
        assert all({"id", "name", "description", "graph", "bindings", "parameters"} <= set(p) for p in presets)


def _complete(http, store, node, result):
    action = {"id": uuid.uuid4().hex, "node_id": node["device_id"], "kind": "task.logs",
              "payload": {"task_id": "a" * 32}}
    assert http.post("/api/v1/actions", json=action, headers=AUTH).json()["state"] == "queued"
    store.complete(action["id"], node["device_id"], result)
    return action["id"]


def test_large_results_are_offloaded_and_listings_never_decode_results(tmp_path, monkeypatch):
    app = create_app(tmp_path, OWNER)
    store = app.state.store
    with TestClient(app) as http:
        node = paired(http, "node")
        small = {"data": "short", "offset": 5}
        large = {"mesh": ["网格" * 10] * 2000, "offset": 1}
        assert len(json.dumps(large, ensure_ascii=False).encode()) > RESULT_INLINE_LIMIT
        small_id, large_id = _complete(http, store, node, small), _complete(http, store, node, large)
        with store.db() as db:
            rows = {r["id"]: r for r in db.execute("SELECT id,result,result_ref FROM actions")}
        assert rows[small_id]["result_ref"] is None and json.loads(rows[small_id]["result"]) == small
        assert rows[large_id]["result"] is None and store.blobs.exists(rows[large_id]["result_ref"])

        calls = []
        original = store_module.decode_result
        monkeypatch.setattr(store_module, "decode_result", lambda text: calls.append(1) or original(text))
        listed = http.get("/api/v1/actions", headers=AUTH).json()
        assert {a["id"] for a in listed} == {small_id, large_id}
        assert all("result" not in a and "result_ref" not in a for a in listed)
        assert all(set(a) == {"id", "request", "node_id", "state", "error", "created", "updated", "review_reason"}
                   for a in listed)
        assert store.actions(node["device_id"], pending=True) == []  # the node dispatch poll
        assert calls == []
        # One action at a time returns the full result, inline or from the blob store, unchanged.
        record = http.get("/api/v1/actions/" + large_id, headers=AUTH).json()
        assert record["result"] == large and record["state"] == "succeeded" and "result_ref" not in record
        assert http.get("/api/v1/actions/" + small_id, headers=AUTH).json()["result"] == small
        assert len(calls) == 2
        # The offloaded result is itself an immutable blob a client may fetch.
        reference = rows[large_id]["result_ref"]
        assert json.loads(http.get("/api/v1/blobs/" + reference, headers=AUTH).content) == large


def test_listing_keeps_reviews_visible_behind_frequent_polls(tmp_path):
    store = ControlStore(tmp_path)

    def request(kind, payload):
        return {"id": uuid.uuid4().hex, "node_id": "2" * 32, "kind": kind, "payload": payload}
    review = store.create_action(request("graph.evaluate", {"preset": "x"}), "图谱计算超过自动执行额度")
    polls = [store.create_action(request("task.events", {"task_id": "3" * 32}))["id"] for _ in range(205)]
    listed = store.actions()
    assert len(listed) == 201 and listed[-1]["id"] == review["id"] and listed[0]["id"] == polls[-1]
    assert [a["created"] for a in listed] == sorted((a["created"] for a in listed), reverse=True)
    assert review["id"] not in {a["id"] for a in store.actions("2" * 32, pending=True)}
    assert review["id"] in {a["id"] for a in store.actions("2" * 32)}
    assert store.actions("9" * 32) == []


def test_old_database_migrates_in_place(tmp_path):
    path = tmp_path / "control.sqlite3"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE devices(id TEXT PRIMARY KEY, name TEXT, role TEXT,
            token_hash TEXT UNIQUE, revoked INTEGER DEFAULT 0, last_seen REAL, snapshot TEXT);
        CREATE TABLE pairings(code_hash TEXT PRIMARY KEY, role TEXT, expires REAL);
        CREATE TABLE actions(id TEXT PRIMARY KEY, request TEXT, node_id TEXT,
            state TEXT, result TEXT, error TEXT, created REAL, updated REAL, review_reason TEXT);
        CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, payload TEXT, created REAL);
        CREATE TABLE sessions(id TEXT PRIMARY KEY, name TEXT, created REAL);
        CREATE TABLE messages(id TEXT PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created REAL);
    """)
    old = {"id": "1" * 32, "node_id": "2" * 32, "kind": "task.logs", "payload": {"task_id": "3" * 32}}
    db.execute("INSERT INTO actions VALUES(?,?,?,?,?,'',?,?,'')", (
        old["id"], json.dumps(old), old["node_id"], "succeeded", json.dumps({"data": "old"}), 1.0, 2.0))
    db.commit()
    db.close()
    store = ControlStore(tmp_path)
    with store.db() as db:
        columns = [r["name"] for r in db.execute("PRAGMA table_info(actions)")]
    assert columns[-2:] == ["result_ref", "submitted_by"]  # additive migrations, in order
    assert store.action(old["id"])["result"] == {"data": "old"}
    assert store.actions()[0]["id"] == old["id"]
    new = {**old, "id": "4" * 32}
    assert store.create_action(new)["state"] == "queued"
    store.complete(new["id"], new["node_id"], {"blob": "b" * (RESULT_INLINE_LIMIT + 1)})
    assert store.action(new["id"])["result"] == {"blob": "b" * (RESULT_INLINE_LIMIT + 1)}
    ControlStore(tmp_path)  # a second open is a no-op


@pytest.fixture
def live_hub(tmp_path):
    """The control app on a loopback port (real HTTP for the agent's urllib uploader)."""
    uvicorn = pytest.importorskip("uvicorn")
    app = create_app(tmp_path / "live", OWNER)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False,
                                           ws_max_size=16 * 1024 * 1024))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline and thread.is_alive(), "control server did not start"
        time.sleep(.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield app, f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_blob_uploader_heads_before_put_over_real_http(live_hub):
    httpx = pytest.importorskip("httpx")
    app, url = live_hub
    assert {"blobs", "graph"} <= hub_features(url)
    with httpx.Client(base_url=url, timeout=30) as http:
        node = paired(http, "node")
    calls = []
    uploader = BlobUploader(url, node["token"])
    real = uploader.transport
    uploader.transport = lambda method, path, body, headers: calls.append(method) or real(method, path, body, headers)
    data = b"\x89PNG fake image" * 1000
    digest = uploader(data)
    assert digest == sha(data) and calls == ["HEAD", "PUT"]
    assert app.state.store.blobs.read(digest) == data
    assert uploader(data) == digest and calls == ["HEAD", "PUT"]  # remembered: no request at all
    fresh = BlobUploader(url, node["token"])
    assert fresh(bytearray(data)) == digest  # already stored: HEAD only
    file = app.state.store.blobs.root.parent / "export.bin"
    file.write_bytes(b"file body" * 5000)
    assert fresh(file) == sha(file.read_bytes()) and app.state.store.blobs.exists(sha(file.read_bytes()))
    with pytest.raises(BlobUploadError, match="HTTP 401"):
        BlobUploader(url, "revoked-or-wrong-token")(b"anything")
    with pytest.raises(ValueError, match="HTTPS"):
        BlobUploader("http://control.example", node["token"])
