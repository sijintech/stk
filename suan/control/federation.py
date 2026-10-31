"""Owner-bound federation relay; no Flower imports, training or public blob access.

The owner's fingerprint-to-device mapping trusts this Hub. It is not proof of
private-key possession and does not replace a node owner's local dataset consent.
Federation bytes use a separate CAS, never the general client-readable blob store.
"""
import asyncio
from contextlib import ExitStack
import hashlib
import json
import threading
import time
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse

from suan.federation.protocol import validate_message, validate_run_manifest
from suan.materials.jobs import Lease, Locked, ordinary, private_directory
from .blobs import BlobMismatch, BlobStore, BlobTooLarge
from .store import encode

MIB = 1024 * 1024
BUNDLE_BYTES = 64 * MIB
TOTAL_BYTES = 4 * 1024 * MIB
RUN_BYTES = 512 * MIB
MAX_RUNS = 128
MAX_REFS = 16384
MAX_RUN_REFS = 4096
MAX_ACTIONS = 32768
MAX_RUN_ACTIONS = 8192
MAX_UPLOADS = 4
MAX_RUN_UPLOADS = 2
UPLOAD_SECONDS = 300
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                   "Content-Security-Policy": "default-src 'none'; sandbox"}
SNAPSHOT_FIELDS = {"cpu_percent", "memory_percent", "features", "error"}
HEALTH_FIELDS = {"api_version", "status", "backends", "resources", "argv_tokens", "features", "supervisor_running"}
TASK_FIELDS = {"id", "name", "workspace_id", "state", "created_at", "updated_at", "backend_id", "exit_code",
               "reason", "cancel_requested"}
WORKSPACE_FIELDS = {"id", "name", "created_at"}


class FederationNotFound(ValueError):
    pass


class FederationConflict(ValueError):
    pass


class FederationQuota(ValueError):
    pass


class FederationBusy(ValueError):
    pass


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError("Expected a canonical federation UUID") from None
    return value


def _round(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000:
        raise ValueError("Federation round must be an integer from 1 to 10000")
    return value


def _http(exc):
    if isinstance(exc, FederationNotFound):
        return HTTPException(404, "Federation object not found")
    if isinstance(exc, FederationConflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, FederationQuota):
        return HTTPException(413, str(exc))
    if isinstance(exc, FederationBusy):
        return HTTPException(429, "Too many federation uploads in flight")
    if isinstance(exc, BlobTooLarge):
        return HTTPException(413, str(exc))
    return HTTPException(400, str(exc))


class FederationRelay:
    def __init__(self, store, *, quota_bytes=TOTAL_BYTES, run_quota_bytes=RUN_BYTES):
        self.store = store
        self.quota_bytes = quota_bytes
        self.run_quota_bytes = run_quota_bytes
        self.blobs = BlobStore(store.directory / "federation-blobs", max_bytes=BUNDLE_BYTES)
        self._lock = threading.RLock()
        self._active = set()
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS federation_runs(
                    run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, active INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS federation_refs(
                    run_id TEXT NOT NULL, round INTEGER NOT NULL, kind TEXT NOT NULL,
                    participant_id TEXT NOT NULL, update_id TEXT NOT NULL, sha256 TEXT NOT NULL,
                    bytes INTEGER NOT NULL, ready INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(run_id,round,kind,participant_id),
                    UNIQUE(run_id,round,kind,participant_id,update_id));
                CREATE INDEX IF NOT EXISTS federation_refs_run ON federation_refs(run_id);
                CREATE TABLE IF NOT EXISTS federation_actions(
                    action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS federation_actions_run ON federation_actions(run_id);
            """)

    @staticmethod
    def _device(db, device_id, role):
        row = db.execute("SELECT role,revoked FROM devices WHERE id=?", (device_id,)).fetchone()
        return row is not None and row["role"] == role and not row["revoked"]

    def _run(self, db, run_id, *, active=True):
        row = db.execute("SELECT manifest,active FROM federation_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None or (active and not row["active"]):
            raise FederationNotFound()
        manifest = json.loads(row["manifest"])
        return manifest, bool(row["active"])

    def _coordinator(self, db, manifest, who):
        return (who.get("id") == manifest["coordinator_device_id"] and who.get("role") == "client"
                and self._device(db, who["id"], "client"))

    def register(self, body, who):
        if who.get("role") != "owner":
            raise FederationNotFound()
        manifest = validate_run_manifest(body)
        text = encode(manifest)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self._device(db, manifest["coordinator_device_id"], "client"):
                raise ValueError("The coordinator must be a current paired client device")
            if any(not self._device(db, p["node_id"], "node") for p in manifest["participants"]):
                raise ValueError("Every participant must be a current paired node device")
            old = db.execute("SELECT manifest FROM federation_runs WHERE run_id=?", (manifest["run_id"],)).fetchone()
            if old is not None and old["manifest"] != text:
                raise FederationConflict("Federation run identity already binds a different manifest")
            if old is None:
                if db.execute("SELECT COUNT(*) FROM federation_runs").fetchone()[0] >= MAX_RUNS:
                    raise FederationQuota("Federation run quota reached")
                db.execute("INSERT INTO federation_runs VALUES(?,?,1,?)", (manifest["run_id"], text, time.time()))
        return self.get(manifest["run_id"], who)

    def get(self, run_id, who):
        with self.store.db() as db:
            manifest, active = self._run(db, run_id, active=False)
            if who.get("role") != "owner" and not self._coordinator(db, manifest, who):
                raise FederationNotFound()
        return {"manifest": manifest, "active": active}

    def revoke(self, run_id, who):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            manifest, _ = self._run(db, run_id, active=False)
            if who.get("role") != "owner" and not self._coordinator(db, manifest, who):
                raise FederationNotFound()
            db.execute("UPDATE federation_runs SET active=0 WHERE run_id=?", (run_id,))
            rows = db.execute("SELECT a.id FROM actions a JOIN federation_actions f ON f.action_id=a.id "
                              "WHERE f.run_id=? AND a.state IN ('queued','review')", (run_id,)).fetchall()
            for row in rows:
                db.execute("UPDATE actions SET state='failed',error=?,updated=? WHERE id=?",
                           ("Federation run revoked; this does not prove a Runtime task has stopped", time.time(), row[0]))
                self.store.event(db, "actions.changed", {"action_id": row[0]})
        return {"run_id": run_id, "active": False, "tasks_stopped": False}

    def _blob_access(self, db, run_id, round, kind, participant_id, who, *, write=False):
        manifest, _ = self._run(db, run_id)
        if not 1 <= round <= manifest["max_rounds"]:
            raise FederationNotFound()
        coordinator = self._coordinator(db, manifest, who)
        participant = next((p for p in manifest["participants"] if p["node_id"] == who.get("id")
                            and who.get("role") == "node" and self._device(db, p["node_id"], "node")), None)
        if kind == "model":
            allowed = coordinator if write else coordinator or participant is not None
        else:
            expected = next((p for p in manifest["participants"] if p["participant_id"] == participant_id), None)
            allowed = (participant is not None and participant == expected) if write else coordinator and expected is not None
        if not allowed:
            raise FederationNotFound()
        return manifest

    def authorize_blob(self, run_id, round, kind, participant_id, who, *, write=False):
        with self.store.db() as db:
            self._blob_access(db, run_id, round, kind, participant_id, who, write=write)

    @staticmethod
    def descriptor(row):
        return {key: row[key] for key in ("run_id", "round", "kind", "participant_id", "update_id", "sha256", "bytes")}

    def read_blob(self, run_id, round, kind, participant_id, update_id, sha256, who):
        with self.store.db() as db:
            self._blob_access(db, run_id, round, kind, participant_id, who)
            row = db.execute("SELECT * FROM federation_refs WHERE run_id=? AND round=? AND kind=? "
                             "AND participant_id=? AND update_id=? AND sha256=? AND ready=1",
                             (run_id, round, kind, participant_id, update_id, sha256)).fetchone()
            if row is None:
                raise FederationNotFound()
            if self.blobs.size(row["sha256"]) != row["bytes"]:
                raise FederationNotFound()
            return self.blobs.path(row["sha256"]), self.descriptor(row)

    def _upload_guards(self, key, guards):
        """Hold upload slots and the immutable identity across Hub instances/processes.

        Lease files are never unlinked. A crashed uploader releases the OS lock;
        its next authorized retry can discard only that identity's partial bytes.
        """
        directory = self.store.directory / "federation-locks"
        def slot(prefix, count):
            for index in range(count):
                try:
                    guards.enter_context(Lease(directory / f"{prefix}.{index}"))
                    return
                except Locked:
                    continue
            raise FederationBusy()
        slot("global", MAX_UPLOADS)
        slot("run-" + key[0], MAX_RUN_UPLOADS)
        identity = hashlib.sha256(encode(key).encode("utf-8")).hexdigest()
        try:
            guards.enter_context(Lease(directory / ("identity-" + identity)))
        except Locked:
            raise FederationBusy() from None
        staging = private_directory(self.blobs.incoming / identity)
        for partial in staging.iterdir():
            ordinary(partial)
            if not partial.name.endswith(".part"):
                raise ValueError("Unexpected federation staging entry")
            partial.unlink()
        return staging

    def begin(self, run_id, round, kind, participant_id, update_id, sha256, size, who):
        key = (run_id, round, kind, participant_id)
        guards, upload, staging, active_added = ExitStack(), None, None, False
        try:
            with self._lock, self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                self._blob_access(db, run_id, round, kind, participant_id, who, write=True)
                _uuid(run_id)
                _round(round)
                BlobStore.check(sha256)
                if kind == "update":
                    _uuid(update_id)
                    if db.execute("SELECT 1 FROM federation_refs WHERE run_id=? AND round=? AND kind='model' "
                                  "AND ready=1", (run_id, round)).fetchone() is None:
                        raise FederationConflict("The round's model must be registered before its updates")
                if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= BUNDLE_BYTES:
                    raise BlobTooLarge("A federation bundle must contain 1 to 64 MiB of bytes")
                if (key in self._active or len(self._active) >= MAX_UPLOADS
                        or sum(k[0] == run_id for k in self._active) >= MAX_RUN_UPLOADS):
                    raise FederationBusy()
                row = db.execute("SELECT * FROM federation_refs WHERE run_id=? AND round=? AND kind=? "
                                 "AND participant_id=?", key).fetchone()
                if row is not None:
                    if (row["update_id"], row["sha256"], row["bytes"]) != (update_id, sha256, size):
                        raise FederationConflict("This round identity already binds different original bytes")
                else:
                    total = db.execute("SELECT COALESCE(SUM(bytes),0),COUNT(*) FROM federation_refs").fetchone()
                    run = db.execute("SELECT COALESCE(SUM(bytes),0),COUNT(*) FROM federation_refs WHERE run_id=?",
                                     (run_id,)).fetchone()
                    if (total[0] + size > self.quota_bytes or run[0] + size > self.run_quota_bytes
                            or total[1] >= MAX_REFS or run[1] >= MAX_RUN_REFS):
                        raise FederationQuota("Federation blob quota reached; incomplete original uploads also reserve space")
                staging = self._upload_guards(key, guards)
                if row is None:
                    db.execute("INSERT INTO federation_refs VALUES(?,?,?,?,?,?,?,0)",
                               (*key, update_id, sha256, size))
                sink = BlobStore(self.blobs.root, max_bytes=BUNDLE_BYTES)
                sink.incoming = staging
                upload = sink.begin(sha256, size)
                self._active.add(key)
                active_added = True
            return {"key": key, "update_id": update_id, "sha256": sha256, "size": size,
                    "who": dict(who), "upload": upload, "guards": guards, "staging": staging}
        except BaseException:
            try:
                if upload is not None:
                    upload.abort()
                if staging is not None:
                    try:
                        staging.rmdir()
                    except OSError:
                        pass  # never remove unexpected files just to release an upload lease
            finally:
                if active_added:
                    with self._lock:
                        self._active.discard(key)
                guards.close()
            raise

    def commit(self, handle):
        run_id, round, kind, participant_id = handle["key"]
        with self._lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._blob_access(db, run_id, round, kind, participant_id, handle["who"], write=True)
            upload = handle["upload"]
            if upload.size != handle["size"]:
                raise BlobMismatch("Federation upload length does not match Content-Length")
            upload.commit()
            db.execute("UPDATE federation_refs SET ready=1 WHERE run_id=? AND round=? AND kind=? AND participant_id=?",
                       handle["key"])
            row = db.execute("SELECT * FROM federation_refs WHERE run_id=? AND round=? AND kind=? AND participant_id=?",
                             handle["key"]).fetchone()
            return self.descriptor(row)

    def close_upload(self, handle):
        try:
            handle["upload"].abort()
            handle["staging"].rmdir()
        finally:
            with self._lock:
                self._active.discard(handle["key"])
            handle["guards"].close()

    def _message(self, db, request, who):
        message = validate_message(request["payload"])
        manifest, _ = self._run(db, message["run_id"])
        if not self._coordinator(db, manifest, who):
            raise FederationNotFound()
        participant = next((p for p in manifest["participants"] if p["node_id"] == request["node_id"]), None)
        if participant is None or not self._device(db, request["node_id"], "node"):
            raise FederationNotFound()
        bindings = {"coordinator_id": manifest["coordinator_id"], "spec_sha256": manifest["spec_sha256"],
                    **{key: participant[key] for key in ("participant_id", "grant_id", "dataset_sha256")}}
        if (any(message[key] != value for key, value in bindings.items())
                or message["round"] > manifest["max_rounds"]):
            raise FederationNotFound()
        model = db.execute("SELECT sha256,bytes FROM federation_refs WHERE run_id=? AND round=? AND kind='model' "
                           "AND ready=1", (message["run_id"], message["round"])).fetchone()
        if model is None or dict(model) != message["model"]:
            raise FederationConflict("The message must bind the round's registered model bytes")
        return message

    def create_action(self, request, who):
        def authorize(db):
            message = self._message(db, request, who)
            old = db.execute("SELECT request FROM actions WHERE id=?", (request["id"],)).fetchone()
            if old is not None and old["request"] != encode(request):
                raise FederationConflict("Federation action identity already binds a different request")
            if db.execute("SELECT 1 FROM federation_actions WHERE action_id=?", (request["id"],)).fetchone() is None:
                total = db.execute("SELECT COUNT(*) FROM federation_actions").fetchone()[0]
                count = db.execute("SELECT COUNT(*) FROM federation_actions WHERE run_id=?", (message["run_id"],)).fetchone()[0]
                if total >= MAX_ACTIONS or count >= MAX_RUN_ACTIONS:
                    raise FederationQuota("Federation action quota reached")
                db.execute("INSERT INTO federation_actions VALUES(?,?)", (request["id"], message["run_id"]))
        return self.store.create_action(request, submitted_by=who["id"], authorize=authorize)

    def visible_action(self, request, who):
        if request.get("kind") != "fl.message":
            return True
        try:
            self.get(request["payload"]["run_id"], who)
            return True
        except (FederationNotFound, KeyError):
            return False

    def visible_event(self, event, who):
        if event["kind"] != "actions.changed":
            return True
        with self.store.db() as db:
            row = db.execute("SELECT request FROM actions WHERE id=?", (event["payload"].get("action_id"),)).fetchone()
        return row is None or self.visible_action(json.loads(row["request"]), who)

    @staticmethod
    def public_snapshot(snapshot):
        """Keep the existing public Runtime DTO, excluding new private FL metadata.

        A node must also omit private FL task/workspace identities and deny their
        use in ordinary Runtime operations. Projection alone is not authorization.
        """
        result = {key: value for key, value in snapshot.items() if key in SNAPSHOT_FIELDS}
        health = snapshot.get("health")
        if isinstance(health, dict):
            result["health"] = {key: value for key, value in health.items() if key in HEALTH_FIELDS}
        for key, allowed in (("tasks", TASK_FIELDS), ("workspaces", WORKSPACE_FIELDS)):
            values = snapshot.get(key)
            if isinstance(values, list):
                result[key] = [{k: value for k, value in item.items() if k in allowed}
                               for item in values if isinstance(item, dict)]
        return result

    def dispatchable(self, request):
        if request.get("kind") != "fl.message":
            return True
        try:
            with self.store.db() as db:
                manifest, _ = self._run(db, request["payload"]["run_id"])
                self._message(db, request, {"id": manifest["coordinator_device_id"], "role": "client"})
            return True
        except (ValueError, KeyError):
            return False


def install_federation_routes(app, store, any_device, json_body):
    relay = FederationRelay(store)
    app.state.federation = relay
    base = "/api/v1/federation/runs"

    @app.post(base)
    async def register(request: Request, who=Depends(any_device)):
        if who.get("role") != "owner":
            raise HTTPException(403, "Owner credential required")
        body = await json_body(request, 64 * 1024)
        try:
            return relay.register(body, who)
        except ValueError as exc:
            raise _http(exc) from None

    @app.get(base + "/{run_id}")
    def get(run_id: str, who=Depends(any_device)):
        try:
            return relay.get(run_id, who)
        except ValueError as exc:
            raise _http(exc) from None

    @app.post(base + "/{run_id}/revoke")
    def revoke(run_id: str, who=Depends(any_device)):
        try:
            return relay.revoke(run_id, who)
        except ValueError as exc:
            raise _http(exc) from None

    async def put(request, run_id, round, kind, participant_id, update_id, sha256, who):
        handle = None
        try:
            relay.authorize_blob(run_id, round, kind, participant_id, who, write=True)
            try:
                size = int(request.headers.get("content-length", "-1"))
            except ValueError:
                raise ValueError("Invalid Content-Length") from None
            if size < 0:
                raise HTTPException(411, "Federation uploads require Content-Length")
            handle = relay.begin(run_id, round, kind, participant_id, update_id, sha256, size, who)
            async with asyncio.timeout(UPLOAD_SECONDS):
                async for chunk in request.stream():
                    if handle["upload"].size + len(chunk) > size:
                        raise BlobMismatch("Federation upload exceeds Content-Length")
                    handle["upload"].write(chunk)
                return relay.commit(handle)
        except TimeoutError:
            raise HTTPException(408, "Federation upload deadline exceeded") from None
        except ValueError as exc:
            raise _http(exc) from None
        finally:
            if handle is not None:
                relay.close_upload(handle)

    def read(run_id, round, kind, participant_id, update_id, sha256, who):
        try:
            path, descriptor = relay.read_blob(run_id, round, kind, participant_id, update_id, sha256, who)
            return FileResponse(path, media_type="application/octet-stream",
                                headers={**PRIVATE_HEADERS, "ETag": '"' + descriptor["sha256"] + '"'})
        except ValueError as exc:
            raise _http(exc) from None

    model_path = base + "/{run_id}/rounds/{round}/model/{sha256}"
    update_path = base + "/{run_id}/rounds/{round}/updates/{participant_id}/{update_id}/{sha256}"

    @app.put(model_path)
    async def put_model(run_id: str, round: int, sha256: str, request: Request, who=Depends(any_device)):
        return await put(request, run_id, round, "model", "", "", sha256, who)

    @app.api_route(model_path, methods=["GET", "HEAD"])
    def get_model(run_id: str, round: int, sha256: str, who=Depends(any_device)):
        return read(run_id, round, "model", "", "", sha256, who)

    @app.put(update_path)
    async def put_update(run_id: str, round: int, participant_id: str, update_id: str, sha256: str,
                         request: Request, who=Depends(any_device)):
        return await put(request, run_id, round, "update", participant_id, update_id, sha256, who)

    @app.api_route(update_path, methods=["GET", "HEAD"])
    def get_update(run_id: str, round: int, participant_id: str, update_id: str, sha256: str,
                   who=Depends(any_device)):
        return read(run_id, round, "update", participant_id, update_id, sha256, who)

    return relay
