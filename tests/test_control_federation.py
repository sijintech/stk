"""Real Hub HTTP/WSS boundaries for private federation relay state and bytes."""
import asyncio
from copy import deepcopy
import hashlib
import json
import struct
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest
pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from suan.control.app import create_app
from suan.control import federation as relay_module
from suan.control.federation import FederationRelay
from suan.control.store import RESULT_INLINE_LIMIT
from suan.federation.updates import encode_arrays


OWNER = "abcdefghijklmnopqrstuvwx"
AUTH = {"Authorization": "Bearer " + OWNER}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def headers(device):
    return {"Authorization": "Bearer " + device["token"]}


def pair(http, role):
    response = http.post("/api/v1/pairings", json={"role": role}, headers=AUTH)
    assert response.status_code == 200
    response = http.post("/api/v1/pairings/claim", json={"code": response.json()["code"], "name": role})
    assert response.status_code == 200
    return response.json()


def bundle(kind="model", value=1.25):
    return encode_arrays([{"name": "weights", "dtype": "f64", "shape": [1],
                           "data": struct.pack("<d", value)}], kind=kind)


def setup_run(http):
    coordinator = pair(http, "client")
    outsider = pair(http, "client")
    nodes = [pair(http, "node") for _ in range(4)]
    manifest = {"format": "stk.federation-run/1", "run_id": str(uuid4()),
                "coordinator_device_id": coordinator["device_id"], "coordinator_id": "a" * 64,
                "spec_sha256": "b" * 64, "max_rounds": 10,
                "participants": [{"node_id": node["device_id"], "participant_id": str(i + 1) * 64,
                                  "grant_id": str(uuid4()), "dataset_sha256": "d" * 64}
                                 for i, node in enumerate(nodes[:3])]}
    return {"coordinator": coordinator, "outsider": outsider, "nodes": nodes, "manifest": manifest}


def register(http, state):
    response = http.post("/api/v1/federation/runs", json=state["manifest"], headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def model_route(state, data, round=1):
    return f"/api/v1/federation/runs/{state['manifest']['run_id']}/rounds/{round}/model/{sha(data)}"


def update_route(state, data, update_id, participant=0, round=1):
    peer = state["manifest"]["participants"][participant]["participant_id"]
    return (f"/api/v1/federation/runs/{state['manifest']['run_id']}/rounds/{round}/updates/"
            f"{peer}/{update_id}/{sha(data)}")


def upload_model(http, state, data=None, round=1):
    data = data if data is not None else bundle()
    response = http.put(model_route(state, data, round), content=data, headers=headers(state["coordinator"]))
    assert response.status_code == 200, response.text
    return data


def action(state, model, operation="train", participant=0, round=1):
    manifest = state["manifest"]
    peer = manifest["participants"][participant]
    return {"id": uuid4().hex, "node_id": peer["node_id"], "kind": "fl.message", "payload": {
        "format": "stk.federation-message/1", "operation": operation, "run_id": manifest["run_id"],
        "round": round, "coordinator_id": manifest["coordinator_id"], "spec_sha256": manifest["spec_sha256"],
        **{key: peer[key] for key in ("participant_id", "grant_id", "dataset_sha256")},
        "model": {"sha256": sha(model), "bytes": len(model)}}}


@pytest.fixture
def hub(tmp_path):
    app = create_app(tmp_path / "hub", OWNER)
    with TestClient(app) as http:
        state = setup_run(http)
        yield app, http, state


def test_only_owner_can_bind_current_devices_and_manifest_is_immutable(hub):
    app, http, state = hub
    route = "/api/v1/federation/runs"
    assert http.post(route, json=state["manifest"]).status_code == 401
    for device in (state["coordinator"], state["outsider"], state["nodes"][0]):
        assert http.post(route, json=state["manifest"], headers=headers(device)).status_code == 403
    first = register(http, state)
    assert first == {"manifest": state["manifest"], "active": True}
    assert register(http, state) == first
    changed = deepcopy(state["manifest"])
    changed["spec_sha256"] = "c" * 64
    assert http.post(route, json=changed, headers=AUTH).status_code == 409
    changed["run_id"] = str(uuid4())
    changed["coordinator_device_id"] = state["nodes"][0]["device_id"]
    assert http.post(route, json=changed, headers=AUTH).status_code == 400
    read = route + "/" + state["manifest"]["run_id"]
    assert http.get(read, headers=headers(state["coordinator"])).json() == first
    for device in (state["outsider"], *state["nodes"]):
        assert http.get(read, headers=headers(device)).status_code == 404
    assert len(app.state.store.events()) > 0


def test_model_acl_and_separate_cas_resist_sha_guessing_and_import(hub):
    app, http, state = hub
    register(http, state)
    data = bundle()
    route = model_route(state, data)
    for device in (state["outsider"], *state["nodes"]):
        assert http.put(route, content=data, headers=headers(device)).status_code == 404
    upload_model(http, state, data)
    for device in (state["coordinator"], *state["nodes"][:3]):
        response = http.get(route, headers=headers(device))
        assert response.status_code == 200 and response.content == data
        assert response.headers["cache-control"] == "private, no-store"
        response = http.head(route, headers=headers(device))
        assert response.status_code == 200 and response.content == b""
        assert response.headers["content-length"] == str(len(data))
    for device in (state["outsider"], state["nodes"][3]):
        assert http.get(route, headers=headers(device)).status_code == 404
        assert http.head(route, headers=headers(device)).status_code == 404
    for auth in (AUTH, headers(state["outsider"]), headers(state["coordinator"])):
        assert http.get("/api/v1/blobs/" + sha(data), headers=auth).status_code == 404
        assert http.head("/api/v1/blobs/" + sha(data), headers=auth).status_code == 404
    request = {"id": uuid4().hex, "node_id": state["nodes"][0]["device_id"], "kind": "workspace.import",
               "payload": {"workspace_id": "c" * 32, "files": [{"path": "guess.bin", "sha256": sha(data), "size": len(data)}]}}
    assert http.post("/api/v1/actions", json=request, headers=AUTH).status_code == 400
    assert app.state.store.blobs.size(sha(data)) is None
    assert app.state.federation.blobs.read(sha(data)) == data
    assert app.state.store.collect_client_blobs(time.time() + 1) == []


def test_updates_are_one_original_per_participant_and_never_shared_between_runs(hub):
    app, http, state = hub
    register(http, state)
    upload_model(http, state)
    data = bundle("delta", 0.25)
    update_id = str(uuid4())
    route = update_route(state, data, update_id)
    for device in (state["coordinator"], state["outsider"], *state["nodes"][1:]):
        assert http.put(route, content=data, headers=headers(device)).status_code == 404
    first = http.put(route, content=data, headers=headers(state["nodes"][0]))
    assert first.status_code == 200
    assert first.json()["update_id"] == update_id
    assert http.put(route, content=data, headers=headers(state["nodes"][0])).json() == first.json()
    assert http.get(route, headers=headers(state["coordinator"])).content == data
    for device in (state["outsider"], *state["nodes"]):
        assert http.get(route, headers=headers(device)).status_code == 404
        assert http.head(route, headers=headers(device)).status_code == 404
    assert http.put(update_route(state, data, str(uuid4())), content=data,
                    headers=headers(state["nodes"][0])).status_code == 409
    changed = bundle("delta", 0.5)
    assert http.put(update_route(state, changed, update_id), content=changed,
                    headers=headers(state["nodes"][0])).status_code == 409
    other = deepcopy(state)
    other["manifest"]["run_id"] = str(uuid4())
    register(http, other)
    assert http.get(model_route(other, bundle()), headers=headers(other["nodes"][0])).status_code == 404
    assert http.get(update_route(other, data, update_id), headers=headers(other["coordinator"])).status_code == 404
    assert app.state.store.blobs.size(sha(data)) is None


def test_actual_sha_and_declared_length_checked_before_publication(hub):
    app, http, state = hub
    register(http, state)
    data = bundle()
    route = model_route(state, data)
    auth = headers(state["coordinator"])
    assert http.put(route, content=b"x" * len(data), headers=auth).status_code == 400
    assert http.head(route, headers=headers(state["nodes"][0])).status_code == 404
    assert http.put(route, content=data[:-1], headers={**auth, "Content-Length": str(len(data))}).status_code == 400
    assert http.put(route, content=data + b"x", headers={**auth, "Content-Length": str(len(data))}).status_code == 400
    assert http.put(route, content=data, headers=auth).status_code == 200
    assert http.put(route, content=b"x" * len(data), headers=auth).status_code == 400
    assert http.get(route, headers=headers(state["nodes"][0])).content == data
    assert list(app.state.federation.blobs.incoming.iterdir()) == []


@pytest.mark.parametrize("scope", ["total", "run"])
def test_quota_counts_original_reservations_without_charging_replays(hub, scope):
    app, http, state = hub
    register(http, state)
    data = bundle()
    relay = app.state.federation
    if scope == "total":
        relay.quota_bytes = len(data)
    else:
        relay.run_quota_bytes = len(data)
    upload_model(http, state, data)
    upload_model(http, state, data)  # same reference is free, even at the exact quota
    assert http.put(model_route(state, data, 2), content=data,
                    headers=headers(state["coordinator"])).status_code == 413
    with app.state.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM federation_refs").fetchone()[0] == 1
    reopened = FederationRelay(app.state.store)
    path, descriptor = reopened.read_blob(state["manifest"]["run_id"], 1, "model", "", "", sha(data),
                                         {"id": state["nodes"][0]["device_id"], "role": "node"})
    assert path.read_bytes() == data and descriptor["bytes"] == len(data)


def test_actions_bind_authenticated_coordinator_and_fixed_model(hub):
    app, http, state = hub
    register(http, state)
    model = upload_model(http, state)
    request = action(state, model)
    route = "/api/v1/actions"
    assert http.post(route, json=request, headers=headers(state["outsider"])).status_code == 404
    assert http.post(route, json=request, headers=AUTH).status_code == 404
    first = http.post(route, json=request, headers=headers(state["coordinator"]))
    assert first.status_code == 202 and first.json()["state"] == "queued"
    assert http.post(route, json=request, headers=headers(state["coordinator"])).json() == first.json()
    changed = deepcopy(request)
    changed["payload"]["operation"] = "collect"
    assert http.post(route, json=changed, headers=headers(state["coordinator"])).status_code == 409
    for key in ("coordinator_id", "participant_id", "spec_sha256", "dataset_sha256"):
        bad = deepcopy(request)
        bad["id"] = uuid4().hex
        bad["payload"][key] = "e" * 64
        assert http.post(route, json=bad, headers=headers(state["coordinator"])).status_code == 404
    bad = deepcopy(request)
    bad["id"] = uuid4().hex
    bad["payload"]["model"]["bytes"] += 1
    assert http.post(route, json=bad, headers=headers(state["coordinator"])).status_code == 409
    read = route + "/" + request["id"]
    assert http.get(read, headers=headers(state["outsider"])).status_code == 404
    assert http.post(read + "/review", json={"approved": False}, headers=headers(state["outsider"])).status_code == 404
    assert http.post(read + "/fail", json={"reason": "guess"}, headers=headers(state["outsider"])).status_code == 403
    assert http.get(route, headers=headers(state["outsider"])).json() == []
    assert http.get(read, headers=AUTH).status_code == 200
    assert len(app.state.store.actions()) == 1


def test_websocket_dispatch_result_identity_and_large_receipt_stays_out_of_public_cas(hub):
    app, http, state = hub
    register(http, state)
    model = upload_model(http, state)
    request = action(state, model)
    assert http.post("/api/v1/actions", json=request, headers=headers(state["coordinator"])).status_code == 202
    with http.websocket_connect("/api/v1/nodes/connect", headers=headers(state["nodes"][0])) as ws:
        received = ws.receive_json()
        assert received == {"type": "action", "action": request}
        app.state.store.complete(request["id"], state["nodes"][1]["device_id"], {"state": "spoof"})
        assert app.state.store.action(request["id"])["state"] == "queued"
        large = {"receipt": "x" * (RESULT_INLINE_LIMIT + 1)}
        ws.send_json({"type": "result", "id": request["id"], "result": large})
        deadline = time.monotonic() + 3
        while app.state.store.action(request["id"])["state"] == "queued":
            assert time.monotonic() < deadline
            time.sleep(.01)
    result = http.get("/api/v1/actions/" + request["id"], headers=headers(state["coordinator"])).json()
    assert result["state"] == "failed" and result["result"] is None
    assert "inline receipt" in result["error"]
    assert list(app.state.store.blobs.root.glob("*/*")) == []


def test_revoke_fails_queued_actions_rejects_future_work_and_never_reactivates(hub):
    app, http, state = hub
    register(http, state)
    model = upload_model(http, state)
    request = action(state, model)
    http.post("/api/v1/actions", json=request, headers=headers(state["coordinator"]))
    route = "/api/v1/federation/runs/" + state["manifest"]["run_id"]
    assert http.post(route + "/revoke", headers=headers(state["outsider"])).status_code == 404
    result = http.post(route + "/revoke", headers=headers(state["coordinator"]))
    assert result.json() == {"run_id": state["manifest"]["run_id"], "active": False, "tasks_stopped": False}
    assert app.state.store.action(request["id"])["state"] == "failed"
    app.state.store.complete(request["id"], request["node_id"], {"state": "late"})
    assert app.state.store.action(request["id"])["state"] == "failed"
    assert http.post("/api/v1/actions", json=request, headers=headers(state["coordinator"])).status_code == 404
    assert http.get(model_route(state, model), headers=headers(state["nodes"][0])).status_code == 404
    assert register(http, state)["active"] is False
    assert http.get(route, headers=AUTH).json()["active"] is False


@pytest.mark.parametrize("revocation", ["run", "device"])
def test_action_registration_rechecks_after_http_identity_was_authenticated(hub, monkeypatch, revocation):
    app, http, state = hub
    register(http, state)
    model = upload_model(http, state)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = app.state.federation.create_action
    response = {}
    def paused(request, who):
        entered.set()
        assert release.wait(5)
        return original(request, who)
    monkeypatch.setattr(app.state.federation, "create_action", paused)
    def submit():
        try:
            response["value"] = http.post("/api/v1/actions", json=action(state, model), headers=headers(state["coordinator"]))
        finally:
            finished.set()
    worker = threading.Thread(target=submit, daemon=True)
    worker.start()
    try:
        assert entered.wait(5)
        if revocation == "run":
            result = http.post("/api/v1/federation/runs/" + state["manifest"]["run_id"] + "/revoke", headers=AUTH)
        else:
            result = http.delete("/api/v1/devices/" + state["coordinator"]["device_id"], headers=AUTH)
        assert result.status_code == 200
    finally:
        release.set()
        worker.join(timeout=5)
    assert finished.is_set() and response["value"].status_code == 404
    assert app.state.store.actions() == []


@pytest.mark.parametrize("revocation", ["run", "device"])
def test_upload_rechecks_authority_at_commit_after_revocation(hub, revocation):
    app, _, state = hub
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as client:
            assert (await client.post("/api/v1/federation/runs", json=state["manifest"], headers=AUTH)).status_code == 200
            data, entered, release = bundle(), asyncio.Event(), asyncio.Event()
            async def body():
                yield data[:8]
                entered.set()
                await release.wait()
                yield data[8:]
            sending = asyncio.create_task(client.put(model_route(state, data), content=body(), headers={
                **headers(state["coordinator"]), "Content-Length": str(len(data))}))
            await asyncio.wait_for(entered.wait(), 3)
            if revocation == "run":
                result = await client.post("/api/v1/federation/runs/" + state["manifest"]["run_id"] + "/revoke", headers=AUTH)
            else:
                result = await client.delete("/api/v1/devices/" + state["coordinator"]["device_id"], headers=AUTH)
            assert result.status_code == 200
            release.set()
            assert (await asyncio.wait_for(sending, 3)).status_code == 404
            assert app.state.federation.blobs.size(sha(data)) is None
            assert list(app.state.federation.blobs.incoming.iterdir()) == []
    asyncio.run(scenario())


@pytest.mark.parametrize("limit", ["global", "run"])
def test_http_upload_concurrency_is_bounded_without_holding_sqlite_during_network_wait(hub, monkeypatch, limit):
    app, _, state = hub
    monkeypatch.setattr(relay_module, "MAX_UPLOADS" if limit == "global" else "MAX_RUN_UPLOADS", 1)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as client:
            await client.post("/api/v1/federation/runs", json=state["manifest"], headers=AUTH)
            data, entered, release = bundle(), asyncio.Event(), asyncio.Event()
            async def body():
                yield data[:8]
                entered.set()
                await release.wait()
                yield data[8:]
            task = asyncio.create_task(client.put(model_route(state, data), content=body(), headers={
                **headers(state["coordinator"]), "Content-Length": str(len(data))}))
            await asyncio.wait_for(entered.wait(), 3)
            duplicate = await client.put(model_route(state, data), content=data, headers=headers(state["coordinator"]))
            assert duplicate.status_code == 429
            second = await client.put(model_route(state, data, 2), content=data, headers=headers(state["coordinator"]))
            assert second.status_code == 429
            assert (await client.get("/api/v1/federation/runs/" + state["manifest"]["run_id"], headers=AUTH)).status_code == 200
            release.set()
            assert (await asyncio.wait_for(task, 3)).status_code == 200
            assert (await client.put(model_route(state, data, 2), content=data,
                                     headers=headers(state["coordinator"]))).status_code == 200
    asyncio.run(scenario())


def test_upload_slots_are_shared_between_independent_hub_instances(hub, monkeypatch):
    app, http, state = hub
    monkeypatch.setattr(relay_module, "MAX_UPLOADS", 1)
    register(http, state)
    other_app = create_app(app.state.store.directory, OWNER)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as first:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=other_app), base_url="http://hub") as second:
                data, entered, release = bundle(), asyncio.Event(), asyncio.Event()
                async def body():
                    yield data[:8]
                    entered.set()
                    await release.wait()
                    yield data[8:]
                upload = asyncio.create_task(first.put(model_route(state, data), content=body(), headers={
                    **headers(state["coordinator"]), "Content-Length": str(len(data))}))
                await asyncio.wait_for(entered.wait(), 3)
                assert (await second.put(model_route(state, data, 2), content=data,
                                         headers=headers(state["coordinator"]))).status_code == 429
                release.set()
                assert (await asyncio.wait_for(upload, 3)).status_code == 200
                assert (await second.put(model_route(state, data, 2), content=data,
                                         headers=headers(state["coordinator"]))).status_code == 200
    asyncio.run(scenario())


def test_crashed_process_releases_upload_slot_and_exact_retry_discards_its_partial(hub, monkeypatch):
    app, http, state = hub
    register(http, state)
    data = bundle()
    monkeypatch.setattr(relay_module, "MAX_UPLOADS", 1)
    code = """
import sys, time
from suan.control.store import ControlStore
from suan.control import federation
federation.MAX_UPLOADS = 1
relay = federation.FederationRelay(ControlStore(sys.argv[1]))
handle = relay.begin(sys.argv[2], 1, 'model', '', '', sys.argv[4], int(sys.argv[5]),
                     {'id': sys.argv[3], 'role': 'client'})
handle['upload'].write(b'partial')
print('upload-slot-held', flush=True)
time.sleep(30)
"""
    process = subprocess.Popen([sys.executable, "-c", code, str(app.state.store.directory),
                                state["manifest"]["run_id"], state["coordinator"]["device_id"], sha(data), str(len(data))],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        assert process.stdout.readline().strip() == "upload-slot-held"
        assert http.put(model_route(state, data, 2), content=data,
                        headers=headers(state["coordinator"])).status_code == 429
    finally:
        process.kill()
        process.wait(timeout=5)
        process.stdout.close()
    assert list(app.state.federation.blobs.incoming.glob("*/*.part"))
    assert http.head(model_route(state, data), headers=headers(state["nodes"][0])).status_code == 404
    upload_model(http, state, data)
    assert http.get(model_route(state, data), headers=headers(state["nodes"][0])).content == data
    assert list(app.state.federation.blobs.incoming.iterdir()) == []


def test_failed_upload_reserves_original_quota_and_size_limits_are_explicit(hub):
    app, http, state = hub
    register(http, state)
    data = bundle()
    app.state.federation.quota_bytes = len(data)
    auth = headers(state["coordinator"])
    assert http.put(model_route(state, data), content=b"x" * len(data), headers=auth).status_code == 400
    assert http.put(model_route(state, data, 2), content=data, headers=auth).status_code == 413
    assert http.put(model_route(state, data), content=data, headers=auth).status_code == 200
    assert http.put(model_route(state, data, 11), content=data, headers=auth).status_code == 404
    assert http.put(model_route(state, data, 3), content=b"", headers={
        **auth, "Content-Length": str(relay_module.BUNDLE_BYTES + 1)}).status_code == 413


def test_json_duplicate_keys_and_nonfinite_constants_never_create_fl_actions(hub):
    app, http, state = hub
    register(http, state)
    model = upload_model(http, state)
    request = action(state, model)
    raw = json.dumps(request)
    duplicate = raw[:-1] + ', "id": "' + request["id"] + '"}'
    nonfinite = raw.replace('"round": 1', '"round": NaN')
    for body in (duplicate, nonfinite):
        result = http.post("/api/v1/actions", content=body,
                           headers={**headers(state["coordinator"]), "Content-Type": "application/json"})
        assert result.status_code == 400
    assert app.state.store.actions() == []


def test_action_quota_keeps_same_request_recoverable(hub, monkeypatch):
    app, http, state = hub
    monkeypatch.setattr(relay_module, "MAX_ACTIONS", 1)
    register(http, state)
    model = upload_model(http, state)
    request = action(state, model)
    auth = headers(state["coordinator"])
    assert http.post("/api/v1/actions", json=request, headers=auth).status_code == 202
    assert http.post("/api/v1/actions", json=action(state, model, "status"), headers=auth).status_code == 413
    assert http.post("/api/v1/actions", json=request, headers=auth).status_code == 202
    assert len(app.state.store.actions()) == 1


def test_upload_deadline_releases_slots_and_original_can_be_retried(hub, monkeypatch):
    app, http, state = hub
    register(http, state)
    monkeypatch.setattr(relay_module, "UPLOAD_SECONDS", .02)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as client:
            data = bundle()
            async def body():
                yield data[:8]
                await asyncio.sleep(1)
                yield data[8:]
            result = await client.put(model_route(state, data), content=body(), headers={
                **headers(state["coordinator"]), "Content-Length": str(len(data))})
            assert result.status_code == 408
            assert (await client.put(model_route(state, data), content=data,
                                     headers=headers(state["coordinator"]))).status_code == 200
    asyncio.run(scenario())
    assert list(app.state.federation.blobs.incoming.iterdir()) == []


def test_heartbeat_projects_public_dto_in_storage_and_device_reads(hub):
    app, http, state = hub
    snapshot = {"features": ["read"], "health": {"status": "ok", "federation": "private-metadata"},
                "federation": {"run_id": state["manifest"]["run_id"]},
                "tasks": [{"id": "1" * 32, "name": "public", "spec": {"argv": ["/private/synthetic"]},
                           "dataset_sha256": "d" * 64}],
                "workspaces": [{"id": "2" * 32, "name": "public", "capsule": "/private/synthetic"}]}
    with http.websocket_connect("/api/v1/nodes/connect", headers=headers(state["nodes"][0])) as ws:
        ws.send_json({"type": "snapshot", "snapshot": snapshot})
        deadline = time.monotonic() + 3
        while not app.state.store.device(state["nodes"][0]["device_id"])["snapshot"]:
            assert time.monotonic() < deadline
            time.sleep(.01)
    text = json.dumps(http.get("/api/v1/devices", headers=headers(state["outsider"])).json())
    assert "private-metadata" not in text and "/private/synthetic" not in text and "d" * 64 not in text
    assert state["manifest"]["run_id"] not in text
    assert app.state.store.device(state["nodes"][0]["device_id"])["snapshot"]["tasks"] == [{"id": "1" * 32, "name": "public"}]
    # Old databases might retain earlier snapshots; reads project those too.
    app.state.store.heartbeat(state["nodes"][0]["device_id"], snapshot)
    assert "/private/synthetic" not in http.get("/api/v1/devices", headers=AUTH).text


def test_model_proposals_cannot_create_fl_actions_and_context_has_no_run_metadata(hub):
    app, http, state = hub
    register(http, state)
    model = upload_model(http, state)
    request = action(state, model)
    http.post("/api/v1/actions", json=request, headers=headers(state["coordinator"]))
    app.state.store.heartbeat(state["nodes"][0]["device_id"], {
        "federation": {"run_id": state["manifest"]["run_id"]},
        "workspaces": [{"id": "1" * 32, "name": "synthetic", "private_job": "/private/synthetic"}],
        "tasks": [{"id": "2" * 32, "workspace_id": "1" * 32, "name": "synthetic", "state": "queued",
                   "spec": {"argv": ["/private/synthetic"]}, "dataset_sha256": "d" * 64}]})
    class FakeModel:
        async def reply(self, messages, context):
            text = json.dumps(context)
            assert "/private/synthetic" not in text and "d" * 64 not in text
            for value in (state["manifest"]["run_id"], state["manifest"]["spec_sha256"],
                          state["manifest"]["coordinator_id"], state["manifest"]["participants"][0]["grant_id"]):
                assert value not in text
            return {"content": "synthetic", "actions": [request]}
    # The separately created app reuses the same database and HTTP identities.
    app = create_app(app.state.store.directory, OWNER, model=FakeModel())
    with TestClient(app) as client:
        result = client.post(f"/api/v1/sessions/{uuid4().hex}/messages", headers=headers(state["coordinator"]),
                             json={"id": uuid4().hex, "content": "synthetic request"})
        assert result.status_code == 400
        assert len(app.state.store.actions()) == 1


@pytest.fixture
def live_hub(tmp_path):
    import uvicorn
    app = create_app(tmp_path / "live", OWNER)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False,
                                           ws_max_size=16 * 1024 * 1024))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline and thread.is_alive()
            time.sleep(.01)
        url = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
        with httpx.Client(base_url=url, timeout=5, trust_env=False) as http:
            yield app, http, setup_run(http)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_real_sse_filters_private_action_ids_but_preserves_public_events(live_hub):
    app, http, state = live_hub
    register(http, state)
    model = upload_model(http, state)
    cursor = app.state.store.events()[-1]["id"]
    request = action(state, model)
    http.post("/api/v1/actions", json=request, headers=headers(state["coordinator"]))
    public = {"id": uuid4().hex, "node_id": request["node_id"], "kind": "workspace.create", "payload": {"name": "public"}}
    http.post("/api/v1/actions", json=public, headers=headers(state["outsider"]))
    def received(auth):
        lines = []
        with http.stream("GET", "/api/v1/events", params={"after": cursor}, headers=auth) as stream:
            assert stream.status_code == 200
            for line in stream.iter_lines():
                lines.append(line)
                if public["id"] in line:
                    return "\n".join(lines)
        raise AssertionError("Public event was not delivered")
    assert request["id"] not in received(headers(state["outsider"]))
    assert request["id"] in received(headers(state["coordinator"]))


def test_real_outbound_websocket_reconnect_preserves_action_and_private_blob_routes(live_hub):
    from websockets.sync.client import connect
    app, http, state = live_hub
    register(http, state)
    model = upload_model(http, state)
    request = action(state, model)
    auth = headers(state["coordinator"])
    assert http.post("/api/v1/actions", json=request, headers=auth).status_code == 202
    url = str(http.base_url).rstrip("/").replace("http:", "ws:") + "/api/v1/nodes/connect"
    options = {"additional_headers": headers(state["nodes"][0]), "proxy": None,
               "open_timeout": 3, "close_timeout": 3}
    with connect(url, **options) as ws:
        assert json.loads(ws.recv(timeout=3)) == {"type": "action", "action": request}
        # Disconnect before acknowledging; the action remains the same queued request.
    assert http.get("/api/v1/actions/" + request["id"], headers=auth).json()["state"] == "queued"
    delta, update_id = bundle("delta", .125), str(uuid4())
    with connect(url, **options) as ws:
        assert json.loads(ws.recv(timeout=3))["action"] == request
        assert http.get(model_route(state, model), headers=headers(state["nodes"][0])).content == model
        result = http.put(update_route(state, delta, update_id), content=delta, headers=headers(state["nodes"][0]))
        assert result.status_code == 200
        receipt = {"state": "delivered", "update_id": update_id, "sha256": sha(delta), "bytes": len(delta)}
        ws.send(json.dumps({"type": "result", "id": request["id"], "result": receipt}))
        deadline = time.monotonic() + 3
        while http.get("/api/v1/actions/" + request["id"], headers=auth).json()["state"] == "queued":
            assert time.monotonic() < deadline
            time.sleep(.01)
    retried = http.post("/api/v1/actions", json=request, headers=auth).json()
    assert retried["state"] == "succeeded" and retried["result"] == receipt
    assert http.get(update_route(state, delta, update_id), headers=auth).content == delta
    assert http.get("/api/v1/blobs/" + sha(delta), headers=auth).status_code == 404
    assert len(app.state.store.actions()) == 1


def test_hub_import_and_construction_do_not_load_flower(tmp_path):
    code = """
import sys
from suan.control.app import create_app
app = create_app(sys.argv[1], 'abcdefghijklmnopqrstuvwx')
assert not any(name == 'flwr' or name.startswith('flwr.') for name in sys.modules)
print('Hub construction does not import Flower')
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path / "import")], capture_output=True, text=True,
                            timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Hub construction does not import Flower"
