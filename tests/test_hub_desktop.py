"""Hub additions of WP11 through the HTTP API: desktop pairing and auto-run, client uploads,
workspace.import blob access, graph.cancel, the node read path, and auth on every new endpoint.

Everything runs in-process (FastAPI TestClient); no socket is bound.
"""
import hashlib
import threading
import time
import uuid

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from suan.control.app import create_app  # noqa: E402
from suan.control.policy import IMPORT_REVIEW  # noqa: E402
from suan.control.uploads import CHUNK_MAX, MAX_OPEN  # noqa: E402
from test_control_graph import muferro_graph  # noqa: E402

OWNER = "test-owner-credential-" + "x" * 32
AUTH = {"Authorization": "Bearer " + OWNER}
TASK = "d" * 32
WORKSPACE = "b" * 32
MIB = 1024 * 1024


def bearer(token):
    return {"Authorization": "Bearer " + token}


def pair(c, role="client", profile=None):
    body = {"role": role, **({"profile": profile} if profile else {})}
    code = c.post("/api/v1/pairings", json=body, headers=AUTH)
    assert code.status_code == 200, code.text
    claimed = c.post("/api/v1/pairings/claim", json={"code": code.json()["code"], "name": "设备"})
    assert claimed.status_code == 200
    return claimed.json()


def operation(node_id, kind, payload, identity=None):
    return {"id": identity or uuid.uuid4().hex, "node_id": node_id, "kind": kind, "payload": payload}


def graph_request(**change):
    return {"graph": muferro_graph(), "bindings": {"run": {"task_id": TASK}}, "outputs": ["payload"], **change}


@pytest.fixture
def hub(tmp_path):
    def make(**options):
        options.setdefault("upload_min_free_bytes", 0)  # the disk floor has its own test
        app = create_app(tmp_path / f"control-{len(made)}", OWNER, **options)
        client = TestClient(app)
        client.__enter__()
        made.append(client)
        return app, client
    made = []
    yield make
    for client in made:
        client.__exit__(None, None, None)


def upload(c, headers, data):
    """Upload ``data`` as one blob through the resumable session API; returns its sha256."""
    digest = hashlib.sha256(data).hexdigest()
    began = c.post("/api/v1/uploads", json={"sha256": digest, "size": len(data)}, headers=headers)
    assert began.status_code == 200, began.text
    if not began.json()["completed"]:
        put = c.put(f"/api/v1/uploads/{began.json()['id']}?offset=0", content=data, headers=headers)
        assert put.status_code == 200, put.text
        done = c.post(f"/api/v1/uploads/{began.json()['id']}/finish", headers=headers)
        assert done.status_code == 200 and done.json()["completed"], done.text
    return digest


# ---------------------------------------------------------------------------
# Desktop pairing and auto-run


def test_desktop_pairing_is_granted_by_the_owner(hub):
    app, c = hub()
    desktop = pair(c, profile="desktop")
    assert desktop["role"] == "client" and desktop["profile"] == "desktop"
    assert pair(c)["profile"] == ""
    assert c.post("/api/v1/pairings", json={"role": "node", "profile": "desktop"}, headers=AUTH).status_code == 400
    assert c.post("/api/v1/pairings", json={"role": "client", "profile": "admin"}, headers=AUTH).status_code == 400
    # Only the owner issues codes: a client (even a desktop one) cannot mint itself a desktop code.
    assert c.post("/api/v1/pairings", json={"role": "client", "profile": "desktop"},
                  headers=bearer(desktop["token"])).status_code == 403
    listed = {d["id"]: d for d in c.get("/api/v1/devices", headers=AUTH).json()}
    assert listed[desktop["device_id"]]["profile"] == "desktop"
    policy = c.get("/api/v1/policy", headers=bearer(desktop["token"])).json()
    assert policy["device_profile"] == "desktop" and policy["desktop_auto"] is True
    assert policy["desktop_auto_bytes"] == 256 * MIB and policy["upload_chunk_bytes"] == CHUNK_MAX
    assert c.get("/api/v1/policy", headers=AUTH).json()["desktop_auto"] is False
    assert c.get("/api/v1/policy").status_code == 401


def test_desktop_devices_run_desktop_graphs_under_the_cap(hub):
    app, c = hub()
    node = pair(c, "node")["device_id"]
    desktop, plain = pair(c, profile="desktop"), pair(c)
    cheap = graph_request(profile="desktop", budget={"max_output_bytes": 64 * MIB})
    large = graph_request(profile="desktop", budget={"max_output_bytes": 1024 * MIB})

    def state(headers, payload):
        response = c.post("/api/v1/actions", json=operation(node, "graph.evaluate", payload), headers=headers)
        assert response.status_code == 202, response.text
        return response.json()["state"], response.json()["review_reason"]
    assert state(bearer(desktop["token"]), cheap) == ("queued", "")
    assert state(bearer(plain["token"]), cheap)[0] == "review"  # other clients: unchanged
    assert state(AUTH, cheap)[0] == "review"  # the owner token is not a desktop device
    over = state(bearer(desktop["token"]), large)
    assert over[0] == "review" and "预计传输超过桌面自动执行上限" in over[1]
    # Writes stay reviewed for desktop devices.
    digest = upload(c, bearer(desktop["token"]), b"input")
    imported = c.post("/api/v1/actions", headers=bearer(desktop["token"]), json=operation(
        node, "workspace.import", {"workspace_id": WORKSPACE, "files": [{"path": "a.txt", "sha256": digest,
                                                                         "size": 5}]})).json()
    assert imported["state"] == "review" and imported["review_reason"] == IMPORT_REVIEW
    spec = {"workspace_id": WORKSPACE, "argv": ["@python", "-c", "print(1)"]}
    assert c.post("/api/v1/actions", json=operation(node, "task.submit", {"spec": spec}),
                  headers=bearer(desktop["token"])).json()["state"] == "review"


def test_the_desktop_cap_is_configured_by_the_owner(hub, tmp_path):
    for cap, expected in ((0, "review"), (512 * MIB, "queued"), (128 * MIB, "review")):
        app, c = hub(desktop_auto_bytes=cap)
        node = pair(c, "node")["device_id"]
        desktop = pair(c, profile="desktop")
        payload = graph_request(profile="desktop", budget={"max_output_bytes": 400 * MIB})
        response = c.post("/api/v1/actions", json=operation(node, "graph.evaluate", payload),
                          headers=bearer(desktop["token"]))
        assert response.json()["state"] == expected, cap
        assert c.get("/api/v1/policy", headers=bearer(desktop["token"])).json()["desktop_auto_bytes"] == cap
    with pytest.raises(ValueError):
        create_app(tmp_path / "refused", OWNER, desktop_auto_bytes=-1)


def test_a_revoked_desktop_device_is_refused_everywhere(hub):
    app, c = hub()
    node = pair(c, "node")["device_id"]
    desktop = pair(c, profile="desktop")
    headers = bearer(desktop["token"])
    digest = hashlib.sha256(b"abc").hexdigest()
    began = c.post("/api/v1/uploads", json={"sha256": digest, "size": 3}, headers=headers).json()
    c.delete("/api/v1/devices/" + desktop["device_id"], headers=AUTH)
    payload = graph_request(profile="desktop", budget={"max_output_bytes": MIB})
    requests = [("post", "/api/v1/actions", {"json": operation(node, "graph.evaluate", payload)}),
                ("get", "/api/v1/policy", {}),
                ("post", "/api/v1/uploads", {"json": {"sha256": digest, "size": 3}}),
                ("get", f"/api/v1/uploads/{began['id']}", {}),
                ("put", f"/api/v1/uploads/{began['id']}?offset=0", {"content": b"abc"}),
                ("post", f"/api/v1/uploads/{began['id']}/finish", {}),
                ("delete", f"/api/v1/uploads/{began['id']}", {}),
                ("post", f"/api/v1/nodes/{node}/read", {"json": {"kind": "task.artifacts",
                                                                 "payload": {"task_id": TASK}}})]
    for method, path, extra in requests:
        assert getattr(c, method)(path, headers=headers, **extra).status_code == 401, path
    assert app.state.store.actions() == []


# ---------------------------------------------------------------------------
# Client uploads


def test_upload_endpoints_need_the_right_device(hub):
    app, c = hub()
    node = pair(c, "node")
    first, second, plain = pair(c, profile="desktop"), pair(c, profile="desktop"), pair(c)
    data = b"resumable bytes"
    digest = hashlib.sha256(data).hexdigest()
    began = c.post("/api/v1/uploads", json={"sha256": digest, "size": len(data)}, headers=bearer(first["token"]))
    upload_id = began.json()["id"]
    routes = [("post", "/api/v1/uploads", {"json": {"sha256": digest, "size": len(data)}}),
              ("get", f"/api/v1/uploads/{upload_id}", {}),
              ("put", f"/api/v1/uploads/{upload_id}?offset=0", {"content": data}),
              ("post", f"/api/v1/uploads/{upload_id}/finish", {}),
              ("delete", f"/api/v1/uploads/{upload_id}", {})]
    for method, path, extra in routes:
        assert getattr(c, method)(path, **extra).status_code == 401, path  # unauthenticated
        assert getattr(c, method)(path, headers=bearer("x" * 40), **extra).status_code == 401, path
        assert getattr(c, method)(path, headers=bearer(node["token"]), **extra).status_code == 403, path
        # Uploads take disk space: ordinary clients and the owner token are refused.
        assert getattr(c, method)(path, headers=bearer(plain["token"]), **extra).status_code == 403, path
        assert getattr(c, method)(path, headers=AUTH, **extra).status_code == 403, path
    # Another desktop device never sees the first device's session.
    for method, path, extra in routes[1:]:
        assert getattr(c, method)(path, headers=bearer(second["token"]), **extra).status_code == 404, path
    assert c.get(f"/api/v1/uploads/{upload_id}", headers=bearer(first["token"])).json()["offset"] == 0
    assert c.get("/api/v1/uploads/" + "Z" * 32, headers=bearer(first["token"])).status_code == 404


def test_uploads_resume_verify_and_limit_sizes(hub):
    app, c = hub(blob_max_bytes=64 * 1024)
    device = bearer(pair(c, profile="desktop")["token"])
    data = bytes(range(256)) * 200  # 51200 bytes
    digest = hashlib.sha256(data).hexdigest()
    began = c.post("/api/v1/uploads", json={"sha256": digest, "size": len(data)}, headers=device).json()
    assert began == {"id": began["id"], "sha256": digest, "size": len(data), "offset": 0, "completed": False}
    upload_id = began["id"]
    first = c.put(f"/api/v1/uploads/{upload_id}?offset=0", content=data[:20000], headers=device)
    assert first.json()["offset"] == 20000
    # A client that lost its state begins again and continues where the hub stopped.
    again = c.post("/api/v1/uploads", json={"sha256": digest, "size": len(data)}, headers=device).json()
    assert again["id"] == upload_id and again["offset"] == 20000
    wrong = c.put(f"/api/v1/uploads/{upload_id}?offset=0", content=data[:10], headers=device)
    assert wrong.status_code == 409 and "20000" in wrong.json()["detail"]
    early = c.post(f"/api/v1/uploads/{upload_id}/finish", headers=device)
    assert early.status_code == 409
    past = c.put(f"/api/v1/uploads/{upload_id}?offset=20000", content=data[20000:] + b"!", headers=device)
    assert past.status_code == 413
    assert c.put(f"/api/v1/uploads/{upload_id}?offset=20000", content=data[20000:], headers=device).status_code == 200
    done = c.post(f"/api/v1/uploads/{upload_id}/finish", headers=device).json()
    assert done["completed"] is True and app.state.store.blobs.read(digest) == data
    # A blob the hub holds completes at once; the finished session is gone.
    assert c.post("/api/v1/uploads", json={"sha256": digest, "size": len(data)}, headers=device).json()[
        "completed"] is True
    assert c.get(f"/api/v1/uploads/{upload_id}", headers=device).status_code == 404
    assert c.post("/api/v1/uploads", json={"sha256": digest, "size": 5}, headers=device).status_code == 400
    # Size limits: the declared size, the chunk size, and the blob cap.
    assert c.post("/api/v1/uploads", json={"sha256": "e" * 64, "size": 64 * 1024 + 1},
                  headers=device).status_code == 413
    assert c.post("/api/v1/uploads", json={"sha256": "e" * 64, "size": -1}, headers=device).status_code == 400
    assert c.post("/api/v1/uploads", json={"sha256": "E" * 64, "size": 1}, headers=device).status_code == 400
    big = c.post("/api/v1/uploads", json={"sha256": "f" * 64, "size": 1000}, headers=device).json()
    assert c.put(f"/api/v1/uploads/{big['id']}?offset=0", content=b"\0" * (CHUNK_MAX + 1),
                 headers=device).status_code == 413
    # Bytes that do not hash to the declared sha256 are discarded.
    assert c.put(f"/api/v1/uploads/{big['id']}?offset=0", content=b"\0" * 1000, headers=device).status_code == 200
    mismatch = c.post(f"/api/v1/uploads/{big['id']}/finish", headers=device)
    assert mismatch.status_code == 400 and "sha256" in mismatch.json()["detail"]
    assert not app.state.store.blobs.exists("f" * 64)
    assert c.get(f"/api/v1/uploads/{big['id']}", headers=device).status_code == 404
    # Abort, and the per-device limit of open sessions.
    opened = [c.post("/api/v1/uploads", json={"sha256": f"{i:064x}", "size": 10}, headers=device)
              for i in range(MAX_OPEN)]
    assert all(r.status_code == 200 for r in opened)
    assert c.post("/api/v1/uploads", json={"sha256": "9" * 64, "size": 10}, headers=device).status_code == 429
    assert c.delete(f"/api/v1/uploads/{opened[0].json()['id']}", headers=device).json() == {"aborted": True}
    assert c.post("/api/v1/uploads", json={"sha256": "9" * 64, "size": 10}, headers=device).status_code == 200


def test_empty_file_upload(hub):
    app, c = hub()
    device = bearer(pair(c, profile="desktop")["token"])
    digest = hashlib.sha256(b"").hexdigest()
    began = c.post("/api/v1/uploads", json={"sha256": digest, "size": 0}, headers=device).json()
    assert c.post(f"/api/v1/uploads/{began['id']}/finish", headers=device).json()["completed"] is True
    assert app.state.store.blobs.read(digest) == b""


# ---------------------------------------------------------------------------
# workspace.import and its blob route


def test_workspace_import_needs_uploaded_blobs_and_safe_paths(hub):
    app, c = hub()
    node = pair(c, "node")["device_id"]
    device = bearer(pair(c, profile="desktop")["token"])
    digest = upload(c, device, b"12345")

    def post(files):
        return c.post("/api/v1/actions", headers=device, json=operation(
            node, "workspace.import", {"workspace_id": WORKSPACE, "files": files}))
    missing = post([{"path": "a.txt", "sha256": "e" * 64, "size": 5}])
    assert missing.status_code == 400 and "before importing" in missing.json()["detail"]
    assert post([{"path": "a.txt", "sha256": digest, "size": 6}]).status_code == 400  # wrong size
    for bad in ("../a.txt", "/etc/passwd", "a/../../b", "C:/a", "a\\b", "a//b"):
        assert post([{"path": bad, "sha256": digest, "size": 5}]).status_code == 400, bad
    ok = post([{"path": "数据/a.txt", "sha256": digest, "size": 5}])
    assert ok.status_code == 202 and ok.json()["state"] == "review"


def test_import_blobs_are_served_only_to_the_importing_node(hub):
    app, c = hub()
    node, other = pair(c, "node"), pair(c, "node")
    device = bearer(pair(c, profile="desktop")["token"])
    digest = upload(c, device, b"import me")
    unrelated = upload(c, device, b"not part of the import")
    action = c.post("/api/v1/actions", headers=device, json=operation(
        node["device_id"], "workspace.import",
        {"workspace_id": WORKSPACE, "files": [{"path": "x.bin", "sha256": digest, "size": 9}]})).json()
    route = f"/api/v1/actions/{action['id']}/blobs/{digest}"
    assert c.get(route, headers=bearer(node["token"])).status_code == 404  # still in review
    c.post(f"/api/v1/actions/{action['id']}/review", json={"approved": True}, headers=AUTH)
    served = c.get(route, headers=bearer(node["token"]))
    assert served.status_code == 200 and served.content == b"import me"
    assert c.get(route).status_code == 401
    assert c.get(route, headers=device).status_code == 403  # clients use GET /api/v1/blobs
    assert c.get(route, headers=AUTH).status_code == 403
    assert c.get(route, headers=bearer(other["token"])).status_code == 404  # another node
    assert c.get(f"/api/v1/actions/{action['id']}/blobs/{unrelated}",
                 headers=bearer(node["token"])).status_code == 404  # not listed by this import
    assert c.get(f"/api/v1/actions/{action['id']}/blobs/xyz", headers=bearer(node["token"])).status_code == 400
    app.state.store.complete(action["id"], node["device_id"], {"files": []})
    assert c.get(route, headers=bearer(node["token"])).status_code == 404  # finished
    c.delete("/api/v1/devices/" + node["device_id"], headers=AUTH)
    assert c.get(route, headers=bearer(node["token"])).status_code == 401


# ---------------------------------------------------------------------------
# graph.cancel


def test_graph_cancel_states(hub):
    app, c = hub()
    node, other = pair(c, "node")["device_id"], pair(c, "node")["device_id"]
    device = bearer(pair(c)["token"])
    review = c.post("/api/v1/actions", headers=device,
                    json=operation(node, "graph.evaluate", graph_request(profile="desktop"))).json()
    assert review["state"] == "review"
    cancel = operation(node, "graph.cancel", {"action_id": review["id"]})
    assert c.post("/api/v1/actions", json=cancel).status_code == 401
    done = c.post("/api/v1/actions", json=cancel, headers=device).json()
    assert done["state"] == "succeeded" and done["result"] == {"cancelled": True, "state": "failed"}
    target = c.get(f"/api/v1/actions/{review['id']}", headers=device).json()
    assert target["state"] == "failed" and target["error"].startswith("cancelled:")
    assert c.post("/api/v1/actions", json=cancel, headers=device).json()["id"] == cancel["id"]  # idempotent
    # Approving a cancelled evaluation does nothing.
    assert c.post(f"/api/v1/actions/{review['id']}/review", json={"approved": True},
                  headers=AUTH).json()["state"] == "failed"
    queued = c.post("/api/v1/actions", headers=device, json=operation(node, "graph.evaluate", graph_request())).json()
    assert queued["state"] == "queued"
    pending = c.post("/api/v1/actions", headers=device,
                     json=operation(node, "graph.cancel", {"action_id": queued["id"]})).json()
    assert pending["state"] == "queued"  # the node cancels it
    assert pending["id"] in {a["id"] for a in app.state.store.actions(node, pending=True)}
    app.state.store.complete(queued["id"], node, {"schema": "stk.graph-result/1", "outputs": {}})
    late = c.post("/api/v1/actions", headers=device,
                  json=operation(node, "graph.cancel", {"action_id": queued["id"]})).json()
    assert late["state"] == "succeeded" and late["result"] == {"cancelled": False, "state": "succeeded"}
    # Only graph evaluations of the same node.
    assert c.post("/api/v1/actions", headers=device,
                  json=operation(other, "graph.cancel", {"action_id": queued["id"]})).status_code == 400
    workspace = c.post("/api/v1/actions", headers=device,
                       json=operation(node, "workspace.create", {"name": "w"})).json()
    assert c.post("/api/v1/actions", headers=device,
                  json=operation(node, "graph.cancel", {"action_id": workspace["id"]})).status_code == 400
    assert c.post("/api/v1/actions", headers=device,
                  json=operation(node, "graph.cancel", {"action_id": "e" * 32})).status_code == 400


# ---------------------------------------------------------------------------
# The node read path


def wait_snapshot(app, node_id, features):
    deadline = time.monotonic() + 10
    while (app.state.store.device(node_id) or {}).get("snapshot", {}).get("features") != features:
        assert time.monotonic() < deadline
        time.sleep(0.02)


def test_node_reads_need_a_client_and_a_live_node(hub):
    app, c = hub()
    node = pair(c, "node")
    client = pair(c)
    route = f"/api/v1/nodes/{node['device_id']}/read"
    body = {"kind": "task.artifacts", "payload": {"task_id": TASK}}
    assert c.post(route, json=body).status_code == 401
    assert c.post(route, json=body, headers=bearer("y" * 40)).status_code == 401
    assert c.post(route, json=body, headers=bearer(node["token"])).status_code == 403
    assert c.post(f"/api/v1/nodes/{client['device_id']}/read", json=body,
                  headers=bearer(client["token"])).status_code == 404  # not a node
    assert c.post("/api/v1/nodes/" + "e" * 32 + "/read", json=body, headers=AUTH).status_code == 404
    for kind, payload in (("task.submit", {"spec": {}}), ("workspace.import", {}), ("graph.evaluate", {}),
                          ("task.artifacts", {"task_id": "nope"}), ("file.read", {"task_id": TASK, "path": "../x"})):
        assert c.post(route, json={"kind": kind, "payload": payload}, headers=AUTH).status_code == 400, kind
    assert c.post(route, json=body, headers=AUTH).status_code == 501  # no heartbeat with the read feature yet
    ws_headers = bearer(node["token"])
    with c.websocket_connect("/api/v1/nodes/connect", headers=ws_headers) as ws:
        ws.send_json({"type": "snapshot", "snapshot": {"features": ["graph.evaluate"]}})
        wait_snapshot(app, node["device_id"], ["graph.evaluate"])
        assert c.post(route, json=body, headers=AUTH).status_code == 501  # an older agent
        ws.send_json({"type": "snapshot", "snapshot": {"features": ["read"]}})
        wait_snapshot(app, node["device_id"], ["read"])
        answers = {}

        def read(name, request):
            answers[name] = c.post(route, json=request, headers=bearer(client["token"]))
        for name, reply in (("ok", {"result": [{"path": "a.vti", "size": 1}]}), ("error", {"error": "Task not found"})):
            thread = threading.Thread(target=read, args=(name, body))
            thread.start()
            message = ws.receive_json()
            assert message["type"] == "read" and message["kind"] == "task.artifacts"
            assert message["payload"] == {"task_id": TASK}
            ws.send_json({"type": "read_result", "id": message["id"], **reply})
            thread.join(timeout=30)
        assert answers["ok"].status_code == 200 and answers["ok"].json() == {"result": [{"path": "a.vti", "size": 1}]}
        assert answers["error"].status_code == 422 and answers["error"].json()["detail"] == "Task not found"
    # The node went away: reads fail fast instead of queuing.
    assert c.post(route, json=body, headers=AUTH).status_code == 503
    assert app.state.store.actions() == []  # no action rows, no action events
    assert not [e for e in app.state.store.events() if e["kind"] == "actions.changed"]
    c.delete("/api/v1/devices/" + client["device_id"], headers=AUTH)
    assert c.post(route, json=body, headers=bearer(client["token"])).status_code == 401


def test_health_advertises_the_wp11_features(hub):
    app, c = hub()
    features = set(c.get("/api/v1/health").json()["features"])
    assert {"blobs", "graph", "task.events", "desktop.profile", "graph.cancel", "node.read", "uploads",
            "workspace.import"} <= features
