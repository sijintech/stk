"""Authenticated control API. Deploy behind HTTPS; workers connect outbound."""
import asyncio
import hmac
import json
from pathlib import Path
import re
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .policy import validate_action
from .store import ControlStore, encode


class Pairing(BaseModel):
    role: str = "client"


class Claim(BaseModel):
    code: str = Field(min_length=16, max_length=200)
    name: str = Field(min_length=1, max_length=100)


class Review(BaseModel):
    approved: bool


class Chat(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    content: str = Field(min_length=1, max_length=12000)


def create_app(state_dir, owner_token, templates=None, model=None, web_dir=None):
    if not owner_token or len(owner_token) < 24:
        raise ValueError("Control owner token must contain at least 24 characters")
    app = FastAPI(title="STK Control", version="1.0", docs_url=None, redoc_url=None)
    store = ControlStore(state_dir)
    app.state.store = store
    templates = templates or {}
    connections = {}
    chat_locks = {}

    def identity(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Authentication required")
        token = authorization[7:]
        if hmac.compare_digest(token.encode(), owner_token.encode()):
            return {"id": "owner", "role": "owner"}
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

    def prepare_action(body):
        try:
            if body.get("kind") == "task.submit" and "spec" not in body.get("payload", {}):
                payload = body["payload"]
                template = templates.get(payload.get("template"))
                if not template or set(payload) - {"template", "workspace_id"}:
                    raise ValueError("Select a registered template and workspace")
                body = {**body, "payload": {"template": payload["template"], "spec": {
                    **template, "workspace_id": payload["workspace_id"], "name": payload["template"]}}}
            reason = validate_action(body, templates)
            if not any(d["id"] == body["node_id"] and d["role"] == "node" and not d["revoked"] for d in store.devices()):
                raise ValueError("Execution node not found")
            return body, reason
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    def action(body):
        request, reason = prepare_action(body)
        try:
            return store.create_action(request, reason)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/v1/health")
    def health():
        return {"api_version": 1, "status": "ok"}

    @app.post("/api/v1/pairings", dependencies=[Depends(owner)])
    def pairing(body: Pairing):
        if body.role not in {"node", "client"}:
            raise HTTPException(400, "Role must be node or client")
        return store.pairing(body.role)

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

    @app.post("/api/v1/actions", dependencies=[Depends(client)], status_code=202)
    def post_action(body: dict):
        return action(body)

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

    @app.post("/api/v1/actions/{action_id}/review", dependencies=[Depends(client)])
    def review(action_id: str, body: Review):
        try:
            return store.approve(action_id, body.approved)
        except KeyError as exc:
            raise HTTPException(404, "Action not found") from exc

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

    @app.post("/api/v1/sessions/{session_id}/messages", dependencies=[Depends(client)])
    async def message(session_id: str, body: Chat):
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
                store.publish_reply(answer_id, session_id, content, accepted)
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
        # Register first: closing a replaced socket that is already gone must not end this one.
        previous, connections[node_id] = connections.get(node_id), ws
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
                        await ws.send_json({"type": "action", "action": item["request"]})
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
                else:
                    await ws.close(code=1008)
                    break
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            pass
        finally:
            sender.cancel()
            # Deregister before any await, so a cancelled handler cannot leave a stale socket.
            if connections.get(node_id) is ws:
                connections.pop(node_id)
                with store.db() as db:
                    # Keep the last known task snapshot and its timestamp.
                    store.event(db, "devices.changed", {"device_id": node_id})
            await asyncio.wait([sender])

    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
