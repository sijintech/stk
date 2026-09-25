"""Authenticated control API. Deploy behind HTTPS; workers connect outbound."""
import asyncio
import hmac
import json
from pathlib import Path
import re
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .blobs import BlobError, BlobMismatch, BlobTooLarge
from .limits import (ACTION_BODY_BYTES, ACTION_REQUEST_BYTES, FRAME_LIMIT, IMPORT_MAX_FILES, IMPORT_REQUEST_BYTES,
                     READ_REQUEST_BYTES, READ_TIMEOUT, frame)
from .policy import (DESKTOP_AUTO_BYTES, GRAPH_AUTO_SECONDS, READ_KINDS, REVIEW_POLICIES, RequestTooLarge,
                     UnknownKeys, validate_action)
from .store import ControlStore, encode
from .uploads import (CHUNK_MAX, DEFAULT_MIN_FREE_BYTES, DEFAULT_QUOTA_BYTES, DEFAULT_TTL_SECONDS, DiskFull,
                      UploadBusy, UploadConflict, UploadLimit, UploadQuota, UploadSessions)

# Advertised in GET /api/v1/health so agents and clients can detect additive hub features.
FEATURES = ["blobs", "graph", "task.events", "desktop.profile", "graph.cancel", "node.read", "uploads",
            "workspace.import"]
READ_INFLIGHT = 16
BLOB_HEADERS = {"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; sandbox"}


class Pairing(BaseModel):
    role: str = "client"
    profile: str = ""


class UploadBegin(BaseModel):
    sha256: str
    size: int


class Stop(BaseModel):
    reason: str = Field(default="", max_length=500)


class NodeLink:
    """One open node WebSocket: serialized sends and the node's outstanding reads."""

    def __init__(self, ws):
        self.ws = ws
        self.lock = asyncio.Lock()
        self.pending = {}

    async def send(self, message):
        await self.send_text(frame(message))

    async def send_text(self, text):
        async with self.lock:
            await self.ws.send_text(text)

    def resolve(self, message):
        future = self.pending.get(message.get("id")) if isinstance(message.get("id"), str) else None
        if future is not None and not future.done():
            future.set_result(message)

    def close(self):
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ConnectionError("The execution node disconnected"))


class Claim(BaseModel):
    code: str = Field(min_length=16, max_length=200)
    name: str = Field(min_length=1, max_length=100)


class Review(BaseModel):
    approved: bool


class Chat(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    content: str = Field(min_length=1, max_length=12000)


def _nonnegative(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a nonnegative number")
    return value


async def json_body(request, limit):
    """The request's JSON body, read at most ``limit`` bytes (413 beyond, before parsing)."""
    try:
        declared = int(request.headers.get("content-length", "-1"))
    except ValueError as exc:
        raise HTTPException(400, "Invalid Content-Length") from exc
    if declared > limit:
        raise HTTPException(413, f"The request body is limited to {limit} bytes")
    data = bytearray()
    async for part in request.stream():
        data += part
        if len(data) > limit:
            raise HTTPException(413, f"The request body is limited to {limit} bytes")
    try:
        return json.loads(bytes(data))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(400, "The request body is not JSON") from exc


def create_app(state_dir, owner_token, templates=None, model=None, web_dir=None, blob_max_bytes=None,
               desktop_auto_bytes=DESKTOP_AUTO_BYTES, upload_quota_bytes=DEFAULT_QUOTA_BYTES,
               upload_ttl_seconds=DEFAULT_TTL_SECONDS, upload_min_free_bytes=DEFAULT_MIN_FREE_BYTES,
               review_policy="any"):
    """The control API.

    ``desktop_auto_bytes``: expected-transfer cap of desktop auto-run (0 turns it off).
    ``upload_quota_bytes``, ``upload_ttl_seconds``, ``upload_min_free_bytes``: client upload quota per
    device, lifetime of uploaded blobs no import references, free-disk floor of the blob store.
    ``review_policy``: who may approve reviewed actions: ``any`` client (default), ``not-self`` (not
    the submitting device; the owner always may) or ``owner`` (the owner token only).
    """
    if not owner_token or len(owner_token) < 24:
        raise ValueError("Control owner token must contain at least 24 characters")
    if isinstance(desktop_auto_bytes, bool) or not isinstance(desktop_auto_bytes, int) or desktop_auto_bytes < 0:
        raise ValueError("desktop_auto_bytes must be a nonnegative integer")
    for name, value in (("upload_quota_bytes", upload_quota_bytes), ("upload_ttl_seconds", upload_ttl_seconds),
                        ("upload_min_free_bytes", upload_min_free_bytes)):
        _nonnegative(name, value)
    if review_policy not in REVIEW_POLICIES:
        raise ValueError("review_policy must be one of " + ", ".join(REVIEW_POLICIES))
    app = FastAPI(title="STK Control", version="1.0", docs_url=None, redoc_url=None)
    store = ControlStore(state_dir, blob_max_bytes=blob_max_bytes)
    blobs = store.blobs
    uploads = UploadSessions(blobs, store, quota_bytes=upload_quota_bytes, ttl_seconds=upload_ttl_seconds,
                             min_free_bytes=upload_min_free_bytes)
    app.state.store = store
    app.state.uploads = uploads
    app.state.desktop_auto_bytes = desktop_auto_bytes
    app.state.review_policy = review_policy
    graph_documents = {}
    templates = templates or {}
    connections = {}
    links = {}
    chat_locks = {}

    def identity(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Authentication required")
        token = authorization[7:]
        if hmac.compare_digest(token.encode(), owner_token.encode()):
            return {"id": "owner", "role": "owner", "profile": ""}
        device = store.authenticate(token)
        if device is None:
            raise HTTPException(401, "Device credential invalid or revoked")
        return device

    def client(authorization: str = Header(default="")):
        who = identity(authorization)
        if who["role"] not in {"owner", "client"}:
            raise HTTPException(403, "Client credential required")
        return who

    def owner(who=Depends(client)):
        if who["role"] != "owner":
            raise HTTPException(403, "Owner credential required")

    def uploader(who=Depends(client)):
        # Uploads take hub disk space: only devices the owner paired with the desktop profile.
        if who["role"] != "client" or who.get("profile") != "desktop":
            raise HTTPException(403, "Uploads need a desktop device (pair with a --profile desktop code)")
        return who

    def node_device(authorization: str = Header(default="")):
        who = identity(authorization)
        if who["role"] != "node":
            raise HTTPException(403, "Node credential required")
        return who

    def any_device(authorization: str = Header(default="")):
        return identity(authorization)

    def blob_path(sha256):
        try:
            return blobs.path(sha256)
        except BlobError as exc:
            raise HTTPException(400, str(exc)) from exc

    def blob_file(sha256):
        path = blob_path(sha256)
        if not path.is_file():
            raise HTTPException(404, "Blob not found")
        # Served as opaque bytes: clients know each blob's media type from the result that references it.
        return FileResponse(path, media_type="application/octet-stream",
                            headers={**BLOB_HEADERS, "ETag": '"' + sha256 + '"'})

    def desktop_cap(who):
        """The desktop auto-run cap for this requester (``None``: the ordinary rules)."""
        if who is not None and who.get("role") == "client" and who.get("profile") == "desktop":
            return desktop_auto_bytes or None
        return None

    def prepare_action(body, who=None):
        if not isinstance(body, dict):
            raise HTTPException(400, "An action is a JSON object")
        if who is None and body.get("kind") == "graph.cancel":
            raise HTTPException(400, "graph.cancel is a client request")  # never a model proposal
        try:
            if (body.get("kind") == "task.submit" and isinstance(body.get("payload"), dict)
                    and "spec" not in body["payload"]):
                payload = body["payload"]
                template = templates.get(payload.get("template"))
                if not template or set(payload) - {"template", "workspace_id"}:
                    raise ValueError("Select a registered template and workspace")
                body = {**body, "payload": {"template": payload["template"], "spec": {
                    **template, "workspace_id": payload["workspace_id"], "name": payload["template"]}}}
            reason = validate_action(body, templates, desktop_bytes=desktop_cap(who))
            node = store.device(body["node_id"])
            if node is None or node["role"] != "node" or node["revoked"]:
                raise ValueError("Execution node not found")
            if body["kind"] == "workspace.import":
                for item in body["payload"]["files"]:
                    if blobs.size(item["sha256"]) != item["size"]:
                        raise ValueError(f"Upload the bytes of {item['path']} (POST /api/v1/uploads) before "
                                         "importing them")
            return body, reason
        except RecursionError:
            # A request nested too deeply for the validators (JSON, graphs): a client error, never a 500.
            raise HTTPException(400, "The request is nested too deeply") from None
        except (ValueError, TypeError, KeyError) as exc:
            raise request_error(exc) from exc

    def request_error(exc):
        if isinstance(exc, UnknownKeys):
            return HTTPException(422, str(exc))
        if isinstance(exc, RequestTooLarge):
            return HTTPException(413, str(exc))
        return HTTPException(400, str(exc))

    def action(body, who=None):
        request, reason = prepare_action(body, who)
        submitted_by = who["id"] if who else ""
        try:
            if request["kind"] == "graph.cancel":
                return store.create_cancel(request, submitted_by)
            return store.create_action(request, reason, submitted_by)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def upload_error(exc):
        if isinstance(exc, KeyError):
            return HTTPException(404, "Upload not found")
        if isinstance(exc, BlobTooLarge):
            return HTTPException(413, str(exc))
        if isinstance(exc, UploadConflict):
            return HTTPException(409, str(exc))
        if isinstance(exc, (UploadLimit, UploadBusy)):
            return HTTPException(429, str(exc))
        if isinstance(exc, UploadQuota):
            return HTTPException(413, str(exc))
        if isinstance(exc, DiskFull):
            return HTTPException(507, str(exc))
        return HTTPException(400, str(exc))

    @app.get("/api/v1/health")
    def health():
        return {"api_version": 1, "status": "ok", "features": FEATURES}

    @app.post("/api/v1/pairings", dependencies=[Depends(owner)])
    def pairing(body: Pairing):
        if body.role not in {"node", "client"}:
            raise HTTPException(400, "Role must be node or client")
        try:
            return store.pairing(body.role, body.profile)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/pairings/claim")
    def claim(body: Claim):
        try:
            return store.claim(body.code, body.name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/v1/devices", dependencies=[Depends(client)])
    def devices():
        return store.devices()

    @app.delete("/api/v1/devices/{device_id}", dependencies=[Depends(owner)])
    async def revoke(device_id: str):
        store.revoke(device_id)
        if device_id in connections:
            try:
                await connections[device_id].close(code=1008)
            except Exception:  # the socket may already be gone
                pass
        return {"revoked": device_id}

    @app.get("/api/v1/templates", dependencies=[Depends(client)])
    def get_templates():
        return templates

    @app.get("/api/v1/policy")
    def get_policy(who=Depends(client)):
        """The limits a client plans its requests with (desktop auto-run cap, upload sizes)."""
        return {"device_profile": who.get("profile") or "", "desktop_auto_bytes": desktop_auto_bytes,
                "desktop_auto": desktop_cap(who) is not None, "graph_auto_seconds": GRAPH_AUTO_SECONDS,
                "upload_max_bytes": blobs.max_bytes, "upload_chunk_bytes": CHUNK_MAX,
                "upload_quota_bytes": uploads.quota_bytes, "uploads": who.get("profile") == "desktop",
                "import_max_files": IMPORT_MAX_FILES, "import_request_bytes": IMPORT_REQUEST_BYTES,
                "action_request_bytes": ACTION_REQUEST_BYTES, "read_kinds": sorted(READ_KINDS),
                "review_policy": review_policy}

    @app.post("/api/v1/actions", status_code=202)
    async def post_action(request: Request, who=Depends(client)):
        body = await json_body(request, ACTION_BODY_BYTES)
        return await asyncio.to_thread(action, body, who)

    @app.get("/api/v1/actions", dependencies=[Depends(client)])
    def actions():
        # Results, especially geometry, are loaded separately on demand.
        return [{k: v for k, v in a.items() if k != "result"} for a in store.actions()]

    @app.get("/api/v1/actions/{action_id}", dependencies=[Depends(client)])
    def get_action(action_id: str):
        try:
            return store.action(action_id)
        except KeyError as exc:
            raise HTTPException(404, "Action not found") from exc

    @app.post("/api/v1/actions/{action_id}/review")
    def review(action_id: str, body: Review, who=Depends(client)):
        try:
            if body.approved and review_policy != "any" and who["role"] != "owner":
                # Rejections are always allowed (a device may withdraw its own action).
                if review_policy == "owner":
                    raise HTTPException(403, "This hub's review policy (owner) lets only the owner approve actions")
                if store.submitter(action_id) == who["id"]:
                    raise HTTPException(403, "This hub's review policy (not-self) does not let a device approve "
                                        "its own action; approve it from another device or as the owner")
            return store.approve(action_id, body.approved)
        except KeyError as exc:
            raise HTTPException(404, "Action not found") from exc

    @app.post("/api/v1/actions/{action_id}/fail", dependencies=[Depends(owner)])
    def stop_action(action_id: str, body: Stop):
        """The owner fails a queued or reviewed action (e.g. one stuck on a node); a late result is ignored."""
        try:
            store.action(action_id)
        except KeyError as exc:
            raise HTTPException(404, "Action not found") from exc
        reason = "Stopped by the hub owner" + (f": {body.reason}" if body.reason else "")
        if not store.fail(action_id, reason):
            raise HTTPException(409, "Only queued actions and actions in review can be stopped")
        return store.action(action_id)

    @app.put("/api/v1/blobs/{sha256}", dependencies=[Depends(node_device)])
    async def put_blob(sha256: str, request: Request):
        """Node agents upload content-addressed bytes; they become visible only after the sha256 matched."""
        blob_path(sha256)
        size = blobs.size(sha256)
        if size is not None:
            store.forget_client_blob(sha256)  # a node result now: never collected as a client upload
            return {"sha256": sha256, "size": size, "created": False}
        try:
            declared = int(request.headers.get("content-length", "-1"))
        except ValueError as exc:
            raise HTTPException(400, "Invalid Content-Length") from exc
        try:
            upload = blobs.begin(sha256, declared if declared >= 0 else None)
        except BlobTooLarge as exc:
            raise HTTPException(413, str(exc)) from exc
        try:
            async for chunk in request.stream():
                upload.write(chunk)
            created = await asyncio.to_thread(upload.commit)
        except BlobTooLarge as exc:
            raise HTTPException(413, str(exc)) from exc
        except BlobMismatch as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            upload.abort()
        store.forget_client_blob(sha256)
        return JSONResponse({"sha256": sha256, "size": upload.size, "created": created},
                            status_code=201 if created else 200)

    # -- client uploads (suan.control.uploads) ---------------------------------------------------

    @app.post("/api/v1/uploads")
    def begin_upload(body: UploadBegin, who=Depends(uploader)):
        try:
            return uploads.begin(who["id"], body.sha256, body.size)
        except (KeyError, BlobError) as exc:
            raise upload_error(exc) from exc

    @app.get("/api/v1/uploads/{upload_id}")
    def upload_status(upload_id: str, who=Depends(uploader)):
        try:
            return uploads.status(who["id"], upload_id)
        except (KeyError, BlobError) as exc:
            raise upload_error(exc) from exc

    @app.put("/api/v1/uploads/{upload_id}")
    async def upload_chunk(upload_id: str, request: Request, offset: int, who=Depends(uploader)):
        """Session, owner, offset and declared length are checked before the body is read; the body then
        streams into the session's part file (never buffered whole)."""
        try:
            declared = int(request.headers.get("content-length", "-1"))
        except ValueError as exc:
            raise HTTPException(400, "Invalid Content-Length") from exc
        try:
            append = await asyncio.to_thread(uploads.open_chunk, who["id"], upload_id, offset,
                                             declared if declared >= 0 else None)
        except (KeyError, BlobError) as exc:
            raise upload_error(exc) from exc
        try:
            async for part in request.stream():
                append.write(part)
        except BaseException as exc:
            append.abort()
            if isinstance(exc, BlobError):
                raise upload_error(exc) from exc
            raise
        return append.commit()

    @app.post("/api/v1/uploads/{upload_id}/finish")
    def finish_upload(upload_id: str, who=Depends(uploader)):
        try:
            return uploads.finish(who["id"], upload_id)
        except (KeyError, BlobError) as exc:
            raise upload_error(exc) from exc

    @app.delete("/api/v1/uploads/{upload_id}")
    def abort_upload(upload_id: str, who=Depends(uploader)):
        try:
            return uploads.abort(who["id"], upload_id)
        except (KeyError, BlobError) as exc:
            raise upload_error(exc) from exc

    @app.get("/api/v1/actions/{action_id}/blobs/{sha256}")
    def import_blob(action_id: str, sha256: str, who=Depends(node_device)):
        """A node fetches the blobs of a queued workspace.import action addressed to it (nothing else)."""
        blob_path(sha256)
        try:
            record = store.action(action_id)
        except KeyError as exc:
            raise HTTPException(404, "Blob not found") from exc
        request = record["request"]
        if (record["node_id"] != who["id"] or record["state"] != "queued" or request.get("kind") != "workspace.import"
                or sha256 not in {item.get("sha256") for item in request["payload"].get("files", ())}):
            raise HTTPException(404, "Blob not found")
        return blob_file(sha256)

    # -- reads forwarded to a node without an action row ---------------------------------------

    @app.post("/api/v1/nodes/{node_id}/read")
    async def node_read(node_id: str, request: Request, who=Depends(client)):
        """A review-free read (logs, events, artifacts, file chunks, workspace inputs) answered by the node live.

        No action row and no hub event: polling clients do not grow the action table. 503 when the
        node is offline, 501 when its agent predates the read path (clients then use an action).
        The body is at most READ_REQUEST_BYTES and its payload keys are exact (422 otherwise).
        """
        body = await json_body(request, READ_REQUEST_BYTES)
        if not isinstance(body, dict) or set(body) - {"kind", "payload"}:
            raise HTTPException(422, "A read is {kind, payload}")
        kind, payload = body.get("kind"), body.get("payload")
        if kind not in READ_KINDS or not isinstance(payload, dict):
            raise HTTPException(400, "Reads are " + ", ".join(sorted(READ_KINDS)) + " with an object payload")
        try:
            validate_action({"id": "0" * 32, "node_id": node_id, "kind": kind, "payload": payload}, templates)
        except RecursionError:
            raise HTTPException(400, "The request is nested too deeply") from None
        except (ValueError, TypeError, KeyError) as exc:
            raise request_error(exc) from exc
        node = store.device(node_id)
        if node is None or node["role"] != "node" or node["revoked"]:
            raise HTTPException(404, "Execution node not found")
        if "read" not in (node["snapshot"].get("features") or ()):
            raise HTTPException(501, "This node agent has no read path; upgrade suan-node")
        link = links.get(node_id)
        if link is None:
            raise HTTPException(503, "The execution node is offline")
        if len(link.pending) >= READ_INFLIGHT:
            raise HTTPException(429, "Too many reads in flight on this node; retry")
        read_id = uuid.uuid4().hex
        text = frame({"type": "read", "id": read_id, "kind": kind, "payload": payload})
        if len(text.encode("utf-8")) >= FRAME_LIMIT:
            raise HTTPException(413, "The read does not fit the node connection")
        future = asyncio.get_running_loop().create_future()
        link.pending[read_id] = future
        try:
            await link.send_text(text)
            reply = await asyncio.wait_for(future, READ_TIMEOUT)
        except asyncio.TimeoutError as exc:
            try:  # the node drops the read if it has not started (older agents ignore this message)
                await link.send({"type": "read_cancel", "id": read_id})
            except Exception:
                pass
            raise HTTPException(504, "The execution node did not answer in time; retry") from exc
        except (ConnectionError, RuntimeError, WebSocketDisconnect) as exc:
            raise HTTPException(503, "The execution node disconnected; retry") from exc
        finally:
            link.pending.pop(read_id, None)
        if reply.get("error"):
            raise HTTPException(422, str(reply["error"])[:2000])
        return {"result": reply.get("result")}

    @app.head("/api/v1/blobs/{sha256}", dependencies=[Depends(any_device)])
    def head_blob(sha256: str):
        """Existence and size; node agents check before uploading."""
        return blob_file(sha256)

    @app.get("/api/v1/blobs/{sha256}", dependencies=[Depends(client)])
    def get_blob(sha256: str):
        """Immutable bytes (payload buffers, images, plots, offloaded results) for clients."""
        return blob_file(sha256)

    def graph_document(name):
        # Built once per process: the catalog and presets ship with the installed package.
        if name not in graph_documents:
            from suan.graph.catalog import catalog_document, list_presets
            graph_documents[name] = catalog_document() if name == "catalog" else list_presets()
        return graph_documents[name]

    @app.get("/api/v1/graphs/catalog", dependencies=[Depends(client)])
    def graph_catalog():
        return graph_document("catalog")

    @app.get("/api/v1/graphs/presets", dependencies=[Depends(client)])
    def graph_presets():
        return graph_document("presets")

    @app.get("/api/v1/events", dependencies=[Depends(client)])
    async def events(request: Request, after: int = 0, last_event_id: str = Header(default="")):
        try:
            cursor = max(0, int(last_event_id or after))
        except ValueError as exc:
            raise HTTPException(400, "Invalid event cursor") from exc

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                identity(request.headers.get("authorization", ""))
                rows = store.events(cursor)
                for row in rows:
                    cursor = row["id"]
                    yield f'id: {cursor}\nevent: {row["kind"]}\ndata: {encode(row["payload"])}\n\n'
                if not rows:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(2)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/sessions", dependencies=[Depends(client)])
    def sessions():
        with store.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY created DESC")]

    @app.get("/api/v1/sessions/{session_id}", dependencies=[Depends(client)])
    def get_session(session_id: str):
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(400, "Invalid session ID")
        return store.session(session_id)

    @app.post("/api/v1/sessions/{session_id}/messages")
    async def message(session_id: str, body: Chat, who=Depends(client)):
        get_session(session_id)
        lock = chat_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            previous = store.session(session_id)["messages"]
            old = next((m for m in previous if m["id"] == body.id), None)
            if old and old["content"] != body.content:
                raise HTTPException(409, "Message ID reused with different content")
            answer_id = uuid.uuid5(uuid.NAMESPACE_URL, session_id + body.id).hex
            if any(m["id"] == answer_id for m in previous):
                return store.session(session_id)
            try:
                store.message(body.id, session_id, "user", body.content)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            if model is None:
                response = {"content": "模型尚未配置。任务管理与科学视图可直接使用；配置服务端模型后可通过对话操作。", "actions": []}
            else:
                # Do not send file contents, logs, task argv, env or credentials.
                context = {"devices": [{"id": d["id"], "name": d["name"], "online": d["online"],
                                         "workspaces": [{k: w.get(k) for k in ("id", "name")}
                                                        for w in d["snapshot"].get("workspaces", [])],
                                         "tasks": [{k: t.get(k) for k in ("id", "name", "state", "workspace_id")}
                                                   for t in d["snapshot"].get("tasks", [])]} for d in store.devices() if d["role"] == "node"],
                           "templates": list(templates)}
                try:
                    response = await model.reply(store.session(session_id)["messages"][-12:], context)
                except Exception:
                    raise HTTPException(502, "Model request failed; retry this message")
            if not isinstance(response, dict):
                raise HTTPException(502, "Model returned invalid response")
            proposals = response.get("actions", [])
            if not isinstance(proposals, list) or len(proposals) > 8:
                raise HTTPException(502, "Model returned invalid actions")
            accepted = []
            for i, proposal in enumerate(proposals):
                if not isinstance(proposal, dict):
                    raise HTTPException(502, "Model returned invalid action")
                proposal = {**proposal, "id": uuid.uuid5(uuid.NAMESPACE_URL, answer_id + str(i)).hex}
                accepted.append(prepare_action(proposal))
            content = str(response.get("content", ""))[:24000]
            try:
                store.publish_reply(answer_id, session_id, content, accepted, submitted_by=who["id"])
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return store.session(session_id)

    @app.websocket("/api/v1/nodes/connect")
    async def node(ws: WebSocket):
        try:
            who = identity(ws.headers.get("authorization", ""))
            if who["role"] != "node" or ws.headers.get("origin"):
                raise HTTPException(403)
        except HTTPException:
            await ws.close(code=1008)
            return
        node_id = who["id"]
        await ws.accept()
        link = NodeLink(ws)
        # Register first: closing a replaced socket that is already gone must not end this one.
        previous, connections[node_id] = connections.get(node_id), ws
        replaced, links[node_id] = links.get(node_id), link
        if replaced is not None:
            replaced.close()
        if previous is not None:
            try:
                await previous.close(code=1012)
            except Exception:
                pass

        async def dispatch():
            sent = set()
            while True:
                identity(ws.headers.get("authorization", ""))
                for item in reversed(store.actions(node_id, pending=True)):
                    if item["id"] not in sent:
                        try:
                            text = frame({"type": "action", "action": item["request"]})
                            size = len(text.encode("utf-8"))
                        except ValueError:  # non-finite numbers from before the stricter checks
                            text, size = "", FRAME_LIMIT
                        if size >= FRAME_LIMIT:
                            # Sending it would disconnect the node on every reconnect; it can never run.
                            store.fail(item["id"], f"The request ({size} bytes) exceeds the node connection's "
                                       f"{FRAME_LIMIT}-byte frame limit; it was not sent", states=("queued",))
                        else:
                            await link.send_text(text)
                        sent.add(item["id"])
                await asyncio.sleep(.5)

        sender = asyncio.create_task(dispatch())
        try:
            while True:
                data = await asyncio.wait_for(ws.receive_json(), timeout=30)
                if data.get("type") == "snapshot" and isinstance(data.get("snapshot"), dict):
                    store.heartbeat(node_id, data["snapshot"])
                elif data.get("type") == "result":
                    store.complete(data.get("id"), node_id, data.get("result"), str(data.get("error", "")))
                elif data.get("type") == "read_result":
                    link.resolve(data)
                else:
                    await ws.close(code=1008)
                    break
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            pass
        finally:
            sender.cancel()
            # Deregister before any await, so a cancelled handler cannot leave a stale socket.
            if links.get(node_id) is link:
                links.pop(node_id)
            link.close()
            if connections.get(node_id) is ws:
                connections.pop(node_id)
                with store.db() as db:
                    # Keep the last known task snapshot and its timestamp.
                    store.event(db, "devices.changed", {"device_id": node_id})
            await asyncio.wait([sender])

    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
