"""Regression tests of the WP11 security review (hub requests, frames, uploads, review policy, node reads).

Each test started as a repro of a finding and now asserts the safe behaviour. Everything runs
in-process (FastAPI TestClient) except the bridge review test, which binds 127.0.0.1 only.
"""
import asyncio
import hashlib
import json
import threading
import time
import uuid

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from suan.control.app import create_app  # noqa: E402
from suan.control.limits import (ACTION_BODY_BYTES, ACTION_REQUEST_BYTES, FRAME_LIMIT, IMPORT_MAX_FILES,  # noqa: E402
                                 IMPORT_REQUEST_BYTES, READ_QUEUE, READ_REQUEST_BYTES)
from suan.control.policy import RequestTooLarge, UnknownKeys, validate_action  # noqa: E402
from suan.control.store import encode  # noqa: E402
from suan.control.uploads import MAX_OPEN, MAX_PUTS, STRIPES, UploadBusy, UploadConflict  # noqa: E402
from test_desktop_bridge import bridge_env  # noqa: E402,F401 (fixture)

OWNER = "test-owner-credential-" + "x" * 32
AUTH = {"Authorization": "Bearer " + OWNER}
TASK = "d" * 32
WORKSPACE = "b" * 32
MIB = 1024 * 1024


def bearer(token):
    return {"Authorization": "Bearer " + token}


def pair(c, role="client", profile=None):
    body = {"role": role, **({"profile": profile} if profile else {})}
    code = c.post("/api/v1/pairings", json=body, headers=AUTH).json()["code"]
    return c.post("/api/v1/pairings/claim", json={"code": code, "name": "d"}).json()


def operation(node_id, kind, payload, identity=None):
    return {"id": identity or uuid.uuid4().hex, "node_id": node_id, "kind": kind, "payload": payload}


@pytest.fixture
def hub(tmp_path):
    made = []

    def make(**options):
        options.setdefault("upload_min_free_bytes", 0)
        app = create_app(tmp_path / f"control-{len(made)}", OWNER, **options)
        client = TestClient(app)
        client.__enter__()
        made.append(client)
        return app, client
    yield make
    for client in made:
        client.__exit__(None, None, None)


def upload(c, headers, data):
    digest = hashlib.sha256(data).hexdigest()
    began = c.post("/api/v1/uploads", json={"sha256": digest, "size": len(data)}, headers=headers)
    assert began.status_code == 200, began.text
    if not began.json()["completed"]:
        assert c.put(f"/api/v1/uploads/{began.json()['id']}?offset=0", content=data,
                     headers=headers).status_code == 200
        assert c.post(f"/api/v1/uploads/{began.json()['id']}/finish", headers=headers).status_code == 200
    return digest


def wait_features(app, node_id, features):
    deadline = time.monotonic() + 10
    while (app.state.store.device(node_id) or {}).get("snapshot", {}).get("features") != features:
        assert time.monotonic() < deadline
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# 1. Oversized requests and frames can no longer knock a node offline


def test_read_path_refuses_oversized_and_unknown_payloads(hub):
    app, c = hub()
    node, client = pair(c, "node"), pair(c)
    route = f"/api/v1/nodes/{node['device_id']}/read"
    with c.websocket_connect("/api/v1/nodes/connect", headers=bearer(node["token"])) as ws:
        ws.send_json({"type": "snapshot", "snapshot": {"features": ["read"]}})
        wait_features(app, node["device_id"], ["read"])
        huge = {"kind": "task.logs", "payload": {"task_id": TASK, "junk": "x" * (FRAME_LIMIT + 1024)}}
        assert c.post(route, json=huge, headers=bearer(client["token"])).status_code == 413
        small = {"kind": "task.logs", "payload": {"task_id": TASK, "junk": "x"}}
        refused = c.post(route, json=small, headers=bearer(client["token"]))
        assert refused.status_code == 422 and "junk" in refused.json()["detail"]
        assert c.post(route, json={**small, "extra": 1}, headers=bearer(client["token"])).status_code == 422
        big_body = {"kind": "task.logs", "payload": {"task_id": TASK}, "pad": "y" * READ_REQUEST_BYTES}
        assert c.post(route, json=big_body, headers=bearer(client["token"])).status_code == 413
        # Nothing reached the node: the next message it sees is the next valid read.
        out = {}
        thread = threading.Thread(target=lambda: out.setdefault("r", c.post(
            route, json={"kind": "task.logs", "payload": {"task_id": TASK, "stream": "stderr"}},
            headers=bearer(client["token"]))))
        thread.start()
        text = ws.receive_text()
        message = json.loads(text)
        assert message["type"] == "read" and message["payload"] == {"task_id": TASK, "stream": "stderr"}
        assert len(text.encode()) < READ_REQUEST_BYTES
        ws.send_json({"type": "read_result", "id": message["id"], "result": {"data": ""}})
        thread.join(30)
        assert out["r"].status_code == 200


def test_workspace_import_requests_stay_far_below_the_frame_limit(hub):
    app, c = hub()
    node, client = pair(c, "node"), pair(c, profile="desktop")
    headers = bearer(client["token"])
    digest = upload(c, headers, b"")
    seg = '"' * 250
    files = []
    for i in range(IMPORT_MAX_FILES):  # the most files allowed, each path escaping to ~2 KiB
        path = "/".join([f"{i:05d}" + seg, seg, seg, seg[:1024 - 3 - (5 + 250) - 500]])
        files.append({"path": path, "sha256": digest, "size": 0})
    body = operation(node["device_id"], "workspace.import", {"workspace_id": WORKSPACE, "files": files})
    response = c.post("/api/v1/actions", json=body, headers=headers)
    assert response.status_code == 413  # the HTTP body is over the action body cap
    with pytest.raises(RequestTooLarge):
        validate_action(body, {})
    too_many = operation(node["device_id"], "workspace.import", {"workspace_id": WORKSPACE, "files": [
        {"path": f"f{i}", "sha256": digest, "size": 0} for i in range(IMPORT_MAX_FILES + 1)]})
    assert c.post("/api/v1/actions", json=too_many, headers=headers).status_code == 400
    # The largest request that is accepted still fits the node connection several times over.
    assert IMPORT_REQUEST_BYTES * 3 < FRAME_LIMIT and ACTION_BODY_BYTES < FRAME_LIMIT
    ok = operation(node["device_id"], "workspace.import", {"workspace_id": WORKSPACE, "files": [
        {"path": f"dir/f{i}", "sha256": digest, "size": 0} for i in range(IMPORT_MAX_FILES)]})
    accepted = c.post("/api/v1/actions", json=ok, headers=headers)
    assert accepted.status_code == 202 and accepted.json()["state"] == "review"
    assert len(json.dumps(ok, ensure_ascii=False).encode()) <= IMPORT_REQUEST_BYTES


def test_file_read_and_other_actions_refuse_unknown_keys_and_large_requests(hub):
    app, c = hub()
    node, client = pair(c, "node"), pair(c)
    headers = bearer(client["token"])
    junk = operation(node["device_id"], "file.read", {"workspace_id": WORKSPACE, "path": "a", "junk": "x" * 100})
    response = c.post("/api/v1/actions", json=junk, headers=headers)
    assert response.status_code == 422 and "Unknown request key" in response.json()["detail"]
    huge = operation(node["device_id"], "file.read",
                     {"workspace_id": WORKSPACE, "path": "a" * (ACTION_REQUEST_BYTES + 1)})
    assert c.post("/api/v1/actions", json=huge, headers=headers).status_code == 413
    body = b'{"id": "' + b"a" * 32 + b'", "pad": "' + b"z" * (ACTION_BODY_BYTES + 10) + b'"}'
    assert c.post("/api/v1/actions", content=body, headers={**headers, "Content-Type": "application/json"}
                  ).status_code == 413
    assert c.post("/api/v1/actions", content=b"{not json", headers=headers).status_code == 400
    nan = operation(node["device_id"], "view.probe", {"task_id": TASK, "path": "a.vti", "position": [0, 0, 0]})
    text = json.dumps(nan).replace("[0, 0, 0]", "[NaN, 0, 0]")
    assert c.post("/api/v1/actions", content=text, headers=headers).status_code == 400
    assert app.state.store.actions() == []


@pytest.mark.parametrize("kind, payload", [
    ("workspace.create", {"name": "w", "junk": 1}),
    ("task.cancel", {"task_id": TASK, "junk": 1}),
    ("task.logs", {"task_id": TASK, "junk": 1}),
    ("task.artifacts", {"task_id": TASK, "junk": 1}),
    ("file.read", {"task_id": TASK, "path": "a", "junk": 1}),
    ("view.build", {"task_id": TASK, "path": "a", "junk": 1}),
    ("view.probe", {"task_id": TASK, "path": "a", "position": [0, 0, 0], "junk": 1}),
    ("task.events", {"task_id": TASK, "junk": 1}),
    ("graph.meta", {"junk": 1}),
    ("workspace.files", {"workspace_id": WORKSPACE, "junk": 1}),
    ("graph.cancel", {"action_id": TASK, "junk": 1}),
    ("workspace.import", {"workspace_id": WORKSPACE, "files": [], "junk": 1}),
    ("workspace.import", {"workspace_id": WORKSPACE, "files": [{"path": "a", "sha256": "a" * 64, "size": 1,
                                                                 "junk": 1}]}),
    ("task.submit", {"spec": {"workspace_id": WORKSPACE, "argv": ["x"]}, "junk": 1}),
    ("graph.evaluate", {"preset": "muferro-domains", "junk": 1}),
])
def test_every_kind_has_exact_payload_keys(kind, payload):
    with pytest.raises(UnknownKeys):
        validate_action(operation("c" * 32, kind, payload), {})


@pytest.mark.parametrize("kind, payload", [
    ("task.logs", {"task_id": TASK, "stream": "stdout", "offset": 5}),
    ("view.build", {"task_id": TASK, "path": "a.vti", "options": {"mode": "slice"}, "metadata": {"field": "P"}}),
    ("view.probe", {"task_id": TASK, "path": "a.vti", "position": [0.5, 1, 2], "metadata": {}}),
    ("task.submit", {"template": "demo-field", "spec": {"workspace_id": WORKSPACE, "argv": ["x"]}}),
])
def test_existing_client_payloads_are_still_accepted(kind, payload):
    validate_action(operation("c" * 32, kind, payload), {})  # the web app and workbench send these


@pytest.mark.parametrize("kind, payload", [
    ("task.logs", {"task_id": TASK, "stream": "../etc"}),
    ("task.logs", {"task_id": TASK, "offset": -1}),
    ("view.probe", {"task_id": TASK, "path": "a", "position": [0, 0]}),
    ("view.build", {"task_id": TASK, "path": "a", "options": []}),
])
def test_payload_values_are_checked(kind, payload):
    with pytest.raises(ValueError):
        validate_action(operation("c" * 32, kind, payload), {})


def test_the_hub_fails_stored_actions_that_do_not_fit_a_frame(hub):
    app, c = hub()
    node = pair(c, "node")
    store = app.state.store
    # Rows written before these checks (or by any other path): too large, and not strict JSON.
    huge = operation(node["device_id"], "task.logs", {"task_id": TASK, "junk": "x" * FRAME_LIMIT})
    nan = operation(node["device_id"], "view.probe", {"task_id": TASK, "path": "a", "position": [0, 0, 0]})
    for request in (huge, nan):
        with store.db() as db:
            db.execute("INSERT INTO actions(id,request,node_id,state,result,error,created,updated,review_reason) "
                       "VALUES(?,?,?,'queued',NULL,'',?,?,'')",
                       (request["id"], encode(request).replace("[0,0,0]", "[NaN,0,0]"), request["node_id"],
                        time.time(), time.time()))
        time.sleep(0.01)
    good = c.post("/api/v1/actions", json=operation(node["device_id"], "task.artifacts", {"task_id": TASK}),
                  headers=AUTH).json()
    with c.websocket_connect("/api/v1/nodes/connect", headers=bearer(node["token"])) as ws:
        text = ws.receive_text()
        assert json.loads(text)["action"]["id"] == good["id"] and len(text.encode()) < FRAME_LIMIT
    for request in (huge, nan):
        record = store.action(request["id"])
        assert record["state"] == "failed" and "frame limit" in record["error"]


def test_the_owner_can_stop_a_stuck_action(hub):
    app, c = hub()
    node, client = pair(c, "node"), pair(c)
    queued = c.post("/api/v1/actions", json=operation(node["device_id"], "task.artifacts", {"task_id": TASK}),
                    headers=bearer(client["token"])).json()
    route = f"/api/v1/actions/{queued['id']}/fail"
    assert c.post(route, json={}).status_code == 401
    assert c.post(route, json={}, headers=bearer(client["token"])).status_code == 403
    assert c.post(route, json={}, headers=bearer(node["token"])).status_code == 403
    stopped = c.post(route, json={"reason": "stuck"}, headers=AUTH)
    assert stopped.status_code == 200 and stopped.json()["state"] == "failed"
    assert stopped.json()["error"] == "Stopped by the hub owner: stuck"
    assert c.post(route, json={}, headers=AUTH).status_code == 409
    assert c.post(f"/api/v1/actions/{'e' * 32}/fail", json={}, headers=AUTH).status_code == 404
    app.state.store.complete(queued["id"], node["device_id"], {"late": True})  # a late node result is ignored
    assert app.state.store.action(queued["id"])["state"] == "failed"
    assert queued["id"] not in {a["id"] for a in app.state.store.actions(node["device_id"], pending=True)}


# ---------------------------------------------------------------------------
# 2. Uploads: desktop devices only, per-device quota, garbage collection, disk floor


def test_only_desktop_devices_upload(hub):
    app, c = hub()
    plain = pair(c)
    digest = hashlib.sha256(b"x").hexdigest()
    for headers in (bearer(plain["token"]), AUTH):
        assert c.post("/api/v1/uploads", json={"sha256": digest, "size": 1}, headers=headers).status_code == 403
    assert list(app.state.store.blobs.root.glob("??/*")) == []


def test_upload_quota_counts_open_sessions_and_unimported_blobs(hub):
    app, c = hub(upload_quota_bytes=100_000)
    node = pair(c, "node")["device_id"]
    device = pair(c, profile="desktop")
    headers = bearer(device["token"])
    first = upload(c, headers, b"a" * 60_000)
    over = c.post("/api/v1/uploads", json={"sha256": "e" * 64, "size": 50_000}, headers=headers)
    assert over.status_code == 413 and "quota" in over.json()["detail"]
    pending = c.post("/api/v1/uploads", json={"sha256": "f" * 64, "size": 30_000}, headers=headers)
    assert pending.status_code == 200  # 60 000 + 30 000 declared
    assert c.post("/api/v1/uploads", json={"sha256": "9" * 64, "size": 20_000}, headers=headers).status_code == 413
    c.delete(f"/api/v1/uploads/{pending.json()['id']}", headers=headers)
    # An import in review still counts; an approved (queued) one frees the quota.
    action = c.post("/api/v1/actions", headers=headers, json=operation(node, "workspace.import", {
        "workspace_id": WORKSPACE, "files": [{"path": "a.bin", "sha256": first, "size": 60_000}]})).json()
    assert c.post("/api/v1/uploads", json={"sha256": "e" * 64, "size": 50_000}, headers=headers).status_code == 413
    c.post(f"/api/v1/actions/{action['id']}/review", json={"approved": True}, headers=AUTH)
    assert app.state.uploads.usage(device["device_id"]) == 0
    assert c.post("/api/v1/uploads", json={"sha256": "e" * 64, "size": 50_000}, headers=headers).status_code == 200
    # The quota is per device.
    other = bearer(pair(c, profile="desktop")["token"])
    assert c.post("/api/v1/uploads", json={"sha256": "8" * 64, "size": 90_000}, headers=other).status_code == 200


def test_unreferenced_client_blobs_are_garbage_collected(hub):
    app, c = hub(upload_ttl_seconds=3600)
    node = pair(c, "node")
    headers = bearer(pair(c, profile="desktop")["token"])
    store, blobs, uploads = app.state.store, app.state.store.blobs, app.state.uploads
    orphan = upload(c, headers, b"never imported")
    reviewed = upload(c, headers, b"import in review")
    shared = upload(c, headers, b"also a node result")
    c.post("/api/v1/actions", headers=headers, json=operation(node["device_id"], "workspace.import", {
        "workspace_id": WORKSPACE, "files": [{"path": "r.bin", "sha256": reviewed, "size": 16}]}))
    # A node stores the same bytes as a result blob: they are no longer only a client upload.
    assert c.put(f"/api/v1/blobs/{shared}", content=b"also a node result",
                 headers=bearer(node["token"])).status_code == 200
    assert uploads.gc(now=time.time()) == []  # younger than the lifetime
    collected = uploads.gc(now=time.time() + 3601)
    assert collected == [orphan]
    assert not blobs.exists(orphan) and blobs.exists(reviewed) and blobs.exists(shared)
    # Rejecting the import makes its blobs collectible too.
    action = next(a for a in store.actions() if a["request"]["kind"] == "workspace.import")
    c.post(f"/api/v1/actions/{action['id']}/review", json={"approved": False}, headers=AUTH)
    assert uploads.gc(now=time.time() + 3601) == [reviewed] and not blobs.exists(reviewed)


def test_uploads_stop_below_the_free_disk_floor(hub):
    app, c = hub(upload_min_free_bytes=1 << 60)
    headers = bearer(pair(c, profile="desktop")["token"])
    digest = hashlib.sha256(b"x").hexdigest()
    response = c.post("/api/v1/uploads", json={"sha256": digest, "size": 1}, headers=headers)
    assert response.status_code == 507 and "disk space" in response.json()["detail"]


def test_upload_limits_are_configurable_in_control_json(tmp_path, monkeypatch):
    pytest.importorskip("uvicorn")
    from click.testing import CliRunner
    from suan.control import cli
    captured = {}
    monkeypatch.setattr(cli, "linux_server", lambda: None)
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: captured.update(app=app, **kw))
    (tmp_path / "control.json").write_text(json.dumps({
        "owner_token": OWNER, "upload_quota_mib": 7, "upload_gc_hours": 2, "upload_min_free_mib": 3,
        "review_policy": "not-self", "desktop_auto_mib": 64}), encoding="utf-8")
    result = CliRunner().invoke(cli.control, ["serve", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    app = captured["app"]
    assert captured["ws_max_size"] == FRAME_LIMIT
    assert (app.state.uploads.quota_bytes, app.state.uploads.ttl_seconds, app.state.uploads.min_free_bytes) == (
        7 * MIB, 7200, 3 * MIB)
    assert app.state.review_policy == "not-self" and app.state.desktop_auto_bytes == 64 * MIB
    result = CliRunner().invoke(cli.control, ["serve", "--state-dir", str(tmp_path), "--review-policy", "owner",
                                              "--upload-quota-mib", "1"])
    assert result.exit_code == 0 and captured["app"].state.review_policy == "owner"
    assert captured["app"].state.uploads.quota_bytes == MIB
    (tmp_path / "control.json").write_text(json.dumps({"owner_token": OWNER, "review_policy": "nobody"}),
                                           encoding="utf-8")
    assert CliRunner().invoke(cli.control, ["serve", "--state-dir", str(tmp_path)]).exit_code != 0


# ---------------------------------------------------------------------------
# 3. Review policy


def submitted(c, node_id, headers):
    spec = {"workspace_id": WORKSPACE, "argv": ["@python", "-c", "print(1)"]}
    action = c.post("/api/v1/actions", json=operation(node_id, "task.submit", {"spec": spec}), headers=headers).json()
    assert action["state"] == "review"
    return action["id"]


@pytest.mark.parametrize("policy, self_ok, other_ok", [("any", True, True), ("not-self", False, True),
                                                       ("owner", False, False)])
def test_review_policy(hub, policy, self_ok, other_ok):
    app, c = hub(review_policy=policy)
    node = pair(c, "node")["device_id"]
    mine, other = bearer(pair(c, profile="desktop")["token"]), bearer(pair(c)["token"])

    def approve(action_id, headers):
        return c.post(f"/api/v1/actions/{action_id}/review", json={"approved": True}, headers=headers)
    first = approve(submitted(c, node, mine), mine)
    assert first.status_code == (200 if self_ok else 403)
    if not self_ok:
        assert f"review policy ({policy})" in first.json()["detail"]
    assert approve(submitted(c, node, mine), other).status_code == (200 if other_ok else 403)
    assert approve(submitted(c, node, mine), AUTH).json()["state"] == "queued"  # the owner always may
    # Rejecting (withdrawing) is always allowed, also one's own action.
    rejected = c.post(f"/api/v1/actions/{submitted(c, node, mine)}/review", json={"approved": False}, headers=mine)
    assert rejected.json()["state"] == "rejected"
    assert c.get("/api/v1/policy", headers=mine).json()["review_policy"] == policy
    with pytest.raises(ValueError):
        create_app(app.state.store.directory / "other", OWNER, review_policy="nobody")


def test_bridge_reports_a_review_refused_by_policy_as_unauthorized(tmp_path, bridge_env):  # noqa: F811
    uvicorn = pytest.importorskip("uvicorn")
    httpx = pytest.importorskip("httpx")
    from test_desktop_bridge import InProcessBridge
    app = create_app(tmp_path / "control", OWNER, review_policy="not-self", upload_min_free_bytes=0)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    url = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    harness = InProcessBridge(bridge_env / "bridge")
    try:
        with httpx.Client(base_url=url, timeout=30) as http:
            node_code = http.post("/api/v1/pairings", json={"role": "node"}, headers=AUTH).json()["code"]
            node = http.post("/api/v1/pairings/claim", json={"code": node_code, "name": "n"}).json()["device_id"]
            code = http.post("/api/v1/pairings", json={"role": "client", "profile": "desktop"},
                             headers=AUTH).json()["code"]
        hub_id = harness.call("connections.pair_hub", {"name": "lab", "url": url, "code": code})["connection"]["id"]
        spec = {"workspace_id": WORKSPACE, "argv": ["@python", "-c", "print(1)"]}
        pending = harness.call("task.submit", {"connection": hub_id, "node": node, "idempotency_key": "k",
                                               "spec": spec})["action"]
        assert pending["state"] == "review"
        harness.call("hub.action", {"connection": hub_id, "action_id": pending["id"]})
        error = harness.error("hub.review", {"connection": hub_id, "action_id": pending["id"], "approved": True})
        assert error["code"] == "unauthorized" and "not-self" in error["message"]
        assert error["data"] == {"action_id": pending["id"], "reason": "review_policy"}
        assert harness.call("hub.policy", {"connection": hub_id})["policy"]["review_policy"] == "not-self"
        rejected = harness.call("hub.review", {"connection": hub_id, "action_id": pending["id"], "approved": False})
        assert rejected["action"]["state"] == "rejected"
    finally:
        harness.close()
        server.should_exit = True
        thread.join(timeout=10)


# ---------------------------------------------------------------------------
# 4-6. Upload session internals


def test_bogus_upload_ids_take_no_lock_state(hub):
    app, c = hub()
    headers = bearer(pair(c, profile="desktop")["token"])
    uploads = app.state.uploads
    for i in range(200):
        assert c.put(f"/api/v1/uploads/bogus-{i}-{'z' * 2000}?offset=0", content=b"", headers=headers
                     ).status_code == 404
        assert c.get(f"/api/v1/uploads/{i:032x}", headers=headers).status_code == 404
    assert len(uploads._stripes) == STRIPES and not uploads._writing and not uploads._puts
    assert not hasattr(uploads, "_locks")


def test_chunks_are_checked_before_the_body_and_writers_are_capped(hub):
    app, c = hub()
    device = pair(c, profile="desktop")
    headers = bearer(device["token"])
    uploads = app.state.uploads
    began = [c.post("/api/v1/uploads", json={"sha256": f"{i:064x}", "size": 100}, headers=headers).json()
             for i in range(MAX_PUTS + 1)]
    # Wrong session, wrong offset and an over-long declared chunk fail before any byte is read.
    assert c.put(f"/api/v1/uploads/{'e' * 32}?offset=0", content=b"x" * 10, headers=headers).status_code == 404
    assert c.put(f"/api/v1/uploads/{began[0]['id']}?offset=5", content=b"x", headers=headers).status_code == 409
    assert c.put(f"/api/v1/uploads/{began[0]['id']}?offset=0", content=b"x" * 101, headers=headers).status_code == 413
    assert uploads.status(device["device_id"], began[0]["id"])["offset"] == 0  # nothing kept
    # At most MAX_PUTS chunks per device stream at once; one session takes one writer.
    writers = [uploads.open_chunk(device["device_id"], b["id"], 0, 10) for b in began[:MAX_PUTS]]
    with pytest.raises(UploadConflict):
        uploads.open_chunk(device["device_id"], began[0]["id"], 0, 10)
    with pytest.raises(UploadBusy):
        uploads.open_chunk(device["device_id"], began[MAX_PUTS]["id"], 0, 10)
    assert c.put(f"/api/v1/uploads/{began[MAX_PUTS]['id']}?offset=0", content=b"x" * 10,
                 headers=headers).status_code == 429
    assert c.post(f"/api/v1/uploads/{began[0]['id']}/finish", headers=headers).status_code == 409  # still writing
    writers[0].write(b"y" * 10)
    assert writers[0].commit()["offset"] == 10
    writers[1].write(b"z" * 5)
    writers[1].abort()  # a failed chunk leaves the session as it was
    assert uploads.status(device["device_id"], began[1]["id"])["offset"] == 0
    for writer in writers[2:]:
        writer.abort()
    assert not uploads._puts and not uploads._writing


def test_concurrent_begins_cannot_exceed_the_open_session_limit(hub):
    app, c = hub()
    device = pair(c, profile="desktop")["device_id"]
    uploads = app.state.uploads
    results, barrier = [], threading.Barrier(MAX_OPEN * 2)

    def begin(i):
        barrier.wait()
        try:
            uploads.begin(device, f"{i:064x}", 10)
            results.append("ok")
        except Exception as exc:
            results.append(type(exc).__name__)
    threads = [threading.Thread(target=begin, args=(i,)) for i in range(MAX_OPEN * 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert results.count("ok") == MAX_OPEN and results.count("UploadLimit") == MAX_OPEN


# ---------------------------------------------------------------------------
# 7. The node drops reads the hub gave up on


class _SlowRuntime:
    def __init__(self):
        self.release = threading.Event()
        self.calls = 0

    def files(self, workspace_id):
        self.calls += 1
        self.release.wait(10)
        return []


def test_node_bounds_and_drops_stale_reads(tmp_path, monkeypatch):
    import suan.control.agent as agent_module
    runtime = _SlowRuntime()
    agent = agent_module.NodeAgent(runtime, tmp_path / "agent")
    replies = []

    async def send(message):
        replies.append(message)

    async def scenario():
        read = {"type": "read", "kind": "workspace.files", "payload": {"workspace_id": WORKSPACE}}
        tasks = [agent._accept_read({**read, "id": f"r{i}"}, send) for i in range(READ_QUEUE + 1)]
        await asyncio.sleep(0.2)
        # The queue is full: the extra read is answered at once instead of waiting.
        assert [r for r in replies if r["id"] == f"r{READ_QUEUE}"][0]["error"].startswith("The node is busy")
        agent._cancel_read("r10")  # the hub timed out on a read that has not started: dropped
        agent._cancel_read("r0")   # already running: left alone
        monkeypatch.setattr(agent_module, "READ_TIMEOUT", 0)  # everything still waiting is now stale
        runtime.release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0.05)
    asyncio.run(scenario())
    answered = {r["id"] for r in replies if "result" in r}
    assert answered == {"r0", "r1", "r2", "r3"}  # the four on the read lane; the stale ones were skipped
    assert runtime.calls == 4 and not agent._reads
