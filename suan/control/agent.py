"""Outbound-only node agent. Runtime remains the authority for execution.

Actions run concurrently: a fast lane for Runtime calls and views, and a graph
lane (1-2 evaluations at a time) for ``graph.evaluate``. An action that is
still running when the hub dispatches it again (for example after a
reconnect) is not started twice; its result goes out on whichever connection
is open when it finishes. Graph outputs (payload buffers, images, plots)
travel to the hub's blob store over outbound HTTPS (``HEAD`` before ``PUT``).

Since WP11 the hub may also send ``{"type": "read", "id", "kind", "payload"}``: a
review-free read (logs, events, artifacts, file chunks, workspace inputs) that
the agent answers with ``{"type": "read_result", "id", "result" | "error"}``
without an action row; the agent advertises it as the ``read`` feature, so a hub
only sends it to agents that understand it. ``workspace.import`` fetches client
uploads from the hub (``GET /api/v1/actions/<id>/blobs/<sha256>``, only blobs of
that queued action), verifies their sha256 on the node and uploads them into the
Runtime workspace. ``graph.cancel`` cancels a running or pending ``graph.evaluate``.
"""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from suan.runtime.client import RuntimeClient
from suan.runtime.common import atomic_json, read_json
from suan.runtime.models import relative_path

# muFerro writes field frames as <Stem>.<kt:08d>.dat with stems of at most 8 characters.
MUPRO_FRAME = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9_]{0,7})\.(\d{8})\.dat$")
# Operations this agent implements beyond the first release (advertised in the snapshot).
FEATURES = ["graph.evaluate", "graph.meta", "task.events", "graph.cancel", "read", "workspace.files",
            "workspace.import"]
# Pure reads: re-running them is harmless, so their results are not kept in the action cache.
UNCACHED = {"task.events", "graph.meta", "graph.cancel", "workspace.files"}
GRAPH_KINDS = {"graph.evaluate"}
# Kinds the hub may send as reads (no action row); the hub checks them with the action policy first.
READ_KINDS = {"task.logs", "task.events", "task.artifacts", "file.read", "workspace.files"}
RESULT_LIMIT = 12 * 1024 * 1024
FAST_LANE = 4
READ_LANE = 4
CANCELLED_BY_CLIENT = "Cancelled by a client (graph.cancel)"


def endpoint(url, websocket=False):
    p = urlsplit(url)
    if (p.username or p.password or p.query or p.fragment or p.path not in {"", "/"}
            or p.scheme not in {"https", "http"} or not p.hostname):
        raise ValueError("Use an HTTPS control origin without credentials or path")
    if p.scheme == "http" and p.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote control connections require HTTPS/WSS")
    return urlunsplit((("wss" if p.scheme == "https" else "ws") if websocket else p.scheme,
                       p.netloc, "/api/v1/nodes/connect" if websocket else "", "", ""))


def frame_metadata(path):
    match = MUPRO_FRAME.search(path)
    return {"field": match[1], "timestep": int(match[2])} if match else None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Control redirects are not allowed; configure the final HTTPS origin")


def _open(request, timeout):
    """urllib without proxies or redirects: the node credential is only ever sent to the control origin."""
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        with exc:
            return exc.code, exc.read()


def hub_features(control_url, timeout=30):
    """Features the control hub advertises in ``GET /api/v1/health`` (empty for a first-release hub)."""
    status, body = _open(Request(endpoint(control_url) + "/api/v1/health", method="GET"), timeout)
    if status != 200:
        raise ValueError(f"Control health check answered HTTP {status}")
    features = json.loads(body).get("features", [])
    return set(features) if isinstance(features, list) else set()


class BlobUploadError(RuntimeError):
    pass


def _digest(data):
    if isinstance(data, (bytes, bytearray, memoryview)):
        view = memoryview(data).cast("B")
        return hashlib.sha256(view).hexdigest(), len(view)
    result, size = hashlib.sha256(), 0
    with open(data, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
            size += len(block)
    return result.hexdigest(), size


class BlobUploader:
    """``blob_sink`` of :func:`suan.graph.service.evaluate_request` that stores bytes in the hub.

    ``HEAD /api/v1/blobs/<sha256>`` first; ``PUT`` only what the hub lacks. The
    hub verifies the hash before the blob becomes visible. ``transport`` (tests)
    is ``transport(method, path, body, headers) -> HTTP status``, where ``body``
    is ``None``, bytes or a binary file object.
    """

    RECENT = 4096
    RECENT_SECONDS = 600

    def __init__(self, control_url, token, *, timeout=300, transport=None):
        self.origin = endpoint(control_url)
        self.token = token
        self.timeout = timeout
        self.transport = transport or self._urllib
        self._recent = {}
        self._lock = threading.Lock()

    def _urllib(self, method, path, body, headers):
        request = Request(self.origin + path, data=body, method=method, headers=headers)
        return _open(request, self.timeout)[0]

    def _headers(self, extra=None):
        return {"Authorization": "Bearer " + self.token, **(extra or {})}

    def _seen(self, digest):
        with self._lock:
            stamp = self._recent.get(digest)
            return stamp is not None and time.monotonic() - stamp < self.RECENT_SECONDS

    def _remember(self, digest):
        with self._lock:
            if len(self._recent) >= self.RECENT:
                self._recent.clear()
            self._recent[digest] = time.monotonic()

    def __call__(self, data):
        is_bytes = isinstance(data, (bytes, bytearray, memoryview))
        digest, size = _digest(data)
        if self._seen(digest):
            return digest
        path = "/api/v1/blobs/" + digest
        status = self.transport("HEAD", path, None, self._headers())
        if status == 404:
            headers = self._headers({"Content-Type": "application/octet-stream", "Content-Length": str(size)})
            if is_bytes:
                status = self.transport("PUT", path, bytes(memoryview(data).cast("B")), headers)
            else:
                with open(data, "rb") as stream:
                    status = self.transport("PUT", path, stream, headers)
            if status not in (200, 201):
                raise BlobUploadError(f"Control hub refused blob upload (HTTP {status})")
        elif status != 200:
            raise BlobUploadError(f"Control hub blob check failed (HTTP {status})")
        self._remember(digest)
        return digest


class HubBlobSource:
    """``blob_source`` of :class:`NodeAgent`: streams a ``workspace.import`` blob from the hub into a file.

    Only blobs listed by a queued import action addressed to this node are served. At most ``size``
    bytes are accepted; the agent verifies the sha256 of the staged file itself.
    """

    def __init__(self, control_url, token, *, timeout=300):
        self.origin = endpoint(control_url)
        self.token = token
        self.timeout = timeout

    def __call__(self, action_id, digest, target, size):
        request = Request(f"{self.origin}/api/v1/actions/{action_id}/blobs/{digest}", method="GET",
                          headers={"Authorization": "Bearer " + self.token})
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        try:
            response = opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            with exc:
                raise BlobUploadError(f"The control hub refused the import blob (HTTP {exc.code})") from None
        received = 0
        with response, open(target, "wb") as stream:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                received += len(block)
                if received > size:
                    raise ValueError("The hub sent more bytes than the import declares")
                stream.write(block)


def _graph_error(exc):
    """A readable, bounded message for a GraphError (issues first, then hints)."""
    text = exc.message
    issues = getattr(exc, "issues", None)
    if issues:
        text = "; ".join(f"{i.code} {i.path}: {i.message}" + (f" (hint: {i.hint})" if i.hint else "")
                         for i in issues[:5])
    elif exc.hint:
        text += f" (hint: {exc.hint})"
    if exc.node and not issues:
        text = f"node '{exc.node}': {text}"
    return f"{exc.code}: {text}"[:2000]


class NodeAgent:
    def __init__(self, runtime, cache_dir, *, blob_sink=None, blob_source=None, graph_workers=1):
        self.runtime = runtime
        self.blob_source = blob_source  # workspace.import: blob_source(action_id, sha256, target, size)
        self._graph_tokens = {}         # graph.evaluate action id -> CancelToken while it evaluates
        self._cancel_lock = threading.Lock()
        self._reads = set()
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        from suan.plot import ensure_mplconfigdir
        ensure_mplconfigdir(self.cache / "graph")  # before graph.evaluate imports matplotlib (plots)
        self.blob_sink = blob_sink
        self.graph_workers = max(1, min(2, int(graph_workers)))
        self.hub_features = None  # None: unknown (not connected through run())
        self._inflight = {}
        self._send = None
        self._lanes = None
        self._graph_probe = None

    def snapshot(self):
        import psutil
        tasks = self.runtime.tasks()
        # Credentials and arbitrary environment variables never leave the node.
        tasks = [{k: v for k, v in t.items() if k != "spec"} | {"name": t["spec"]["name"],
                  "workspace_id": t["spec"]["workspace_id"]} for t in tasks[:200]]
        return {"health": self.runtime.health(), "workspaces": self.runtime.workspaces(), "tasks": tasks,
                "cpu_percent": psutil.cpu_percent(), "memory_percent": psutil.virtual_memory().percent,
                "features": FEATURES}

    def execute(self, action):
        identity = action["id"]
        if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid action ID")
        kind, p = action["kind"], action["payload"]
        cacheable = kind not in UNCACHED
        if cacheable:
            cached = read_json(self.cache / (identity + ".json"))
            if cached:
                if cached["request"] != action:
                    raise ValueError("Action ID reused with a different request")
                return cached["result"]
        result = self._operation(identity, kind, p)
        if cacheable:
            atomic_json(self.cache / (identity + ".json"), {"request": action, "result": result})
        return result

    def read(self, kind, payload):
        """A review-free read the hub forwards without an action row (never cached)."""
        if kind not in READ_KINDS or not isinstance(payload, dict):
            raise ValueError("Unknown read")
        from .policy import validate_action
        validate_action({"id": "0" * 32, "node_id": "0" * 32, "kind": kind, "payload": payload}, {})  # as the hub did
        return self._operation(None, kind, payload)

    def _operation(self, identity, kind, p):
        if kind == "workspace.create":
            result = self.runtime.create_workspace(p["name"], identity)
        elif kind == "task.submit":
            spec = {**p["spec"], "argv": list(p["spec"]["argv"])}
            if spec["argv"][0] == "@python":
                spec["argv"][0] = sys.executable
            result = self.runtime.submit(spec, identity)
        elif kind == "task.cancel":
            result = self.runtime.cancel(p["task_id"])
        elif kind == "task.logs":
            result = self.runtime.logs(p["task_id"], p.get("stream", "stdout"), int(p.get("offset", 0)))
            result.pop("bytes", None)
        elif kind == "task.artifacts":
            result = self.runtime.artifacts(p["task_id"])
        elif kind == "task.events":
            result = self.task_events(p)
        elif kind == "file.read":
            query = urlencode({"path": relative_path(p["path"]), "offset": int(p.get("offset", 0)), "limit": 1024*1024})
            route = f"tasks/{p['task_id']}/file" if "task_id" in p else f"workspaces/{p['workspace_id']}/file"
            data = self.runtime.request("GET", f"{route}?{query}", binary=True)
            result = {"data": base64.b64encode(data).decode(), "offset": int(p.get("offset", 0))+len(data)}
        elif kind == "workspace.files":
            result = self.runtime.files(p["workspace_id"])
        elif kind == "workspace.import":
            result = self.workspace_import(identity, p)
        elif kind == "graph.cancel":
            result = self.graph_cancel(p)
        elif kind in {"view.build", "view.probe"}:
            from suan.visualization.scene import build_scene, load_grid, probe
            relative_path(p["path"])
            artifact = next((a for a in self.runtime.artifacts(p["task_id"]) if a["path"] == p["path"]), None)
            if artifact is None:
                raise ValueError("Select a completed task's published field artifact")
            if artifact["size"] > 1024**3:
                raise ValueError("First-release regular field limit is 1 GiB")
            path = self.cache / "fields" / (artifact["sha256"] + Path(p["path"]).suffix)
            self.runtime.download(p["task_id"], p["path"], path)
            metadata = p.get("metadata", {})
            if set(metadata) - {"origin", "spacing", "units", "coordinate_units", "field"}:
                raise ValueError("Unknown scientific metadata")
            metadata = dict(metadata)
            # The cached copy is named by content hash, so identity comes from the artifact path.
            frame = frame_metadata(p["path"])
            if frame:
                metadata.setdefault("field", frame["field"])
                metadata["timestep"] = frame["timestep"]
                if "coordinate_units" not in metadata and "spacing" not in metadata:
                    metadata["coordinate_units"] = "grid index"
            grid = load_grid(path, **metadata)
            if kind == "view.probe":
                result = probe(grid, p["position"])
            else:
                options = p.get("options", {})
                if set(options) - {"mode", "component", "axis", "index", "level", "timestep", "max_vertices"}:
                    raise ValueError("Unknown view option")
                result = build_scene(grid, dataset_id=artifact["sha256"], **options)
                result["manifest"]["source"] = {"task_id": p["task_id"], "path": p["path"]}
        elif kind == "graph.evaluate":
            result = self.graph_evaluate(p, identity)
        elif kind == "graph.meta":
            result = self.graph_meta(p)
        else:
            raise ValueError("Unknown node operation")
        if len(json.dumps(result)) > RESULT_LIMIT:
            raise ValueError("Result exceeds 12 MiB preview budget; reduce view resolution")
        return result

    # -- uploads ---------------------------------------------------------------------------------

    def workspace_import(self, identity, p):
        """Fetch each blob from the hub, verify it here, and upload it into the Runtime workspace.

        Staged files are named by their index, never by the client's path; the path is checked
        again here and by the Runtime, which keeps it inside the workspace inputs.
        """
        from .policy import validate_workspace_import
        validate_workspace_import(p)
        if self.blob_source is None:
            raise ValueError("This agent has no blob channel to the control hub")
        staging = self.cache / "imports" / identity
        staging.mkdir(parents=True, exist_ok=True, mode=0o700)
        imported = []
        try:
            for index, item in enumerate(p["files"]):
                staged = staging / f"{index:05d}.part"
                self.blob_source(identity, item["sha256"], staged, item["size"])
                if _digest(staged) != (item["sha256"], item["size"]):
                    raise ValueError(f"The bytes of {item['path']} do not match their sha256; nothing more was "
                                     "imported")
                meta = self.runtime.upload(p["workspace_id"], staged, item["path"])
                imported.append({"path": meta["path"], "size": meta["size"], "sha256": meta["sha256"]})
                staged.unlink()
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return {"workspace_id": p["workspace_id"], "files": imported}

    # -- graph and monitoring operations ---------------------------------------------------

    def task_events(self, p):
        from suan.runtime.client import RuntimeErrorResponse
        options = {"offset": int(p.get("offset", 0))}
        if "limit" in p:
            options["limit"] = int(p["limit"])
        try:
            return self.runtime.events(p["task_id"], **options)
        except RuntimeErrorResponse as exc:
            if exc.status == 404 and "events" not in (self.runtime.health().get("features") or ()):
                raise ValueError("This Runtime does not publish monitoring events; upgrade the node's STK Runtime") from None
            raise

    def _cancel_marker(self, identity):
        return self.cache / "cancelled" / identity

    def graph_evaluate(self, p, identity=None):
        from suan.graph.registry import CancelToken, GraphError
        from suan.graph.resolve import RuntimeResolver
        from suan.graph.service import evaluate_request
        sink = self.blob_sink
        if sink is None:
            raise ValueError("This agent has no blob upload channel to the control hub")
        if self.hub_features is not None and "blobs" not in self.hub_features:
            raise ValueError("The control hub does not accept result blobs; upgrade the STK control service")
        root = self.cache / "graph"
        resolver = RuntimeResolver(self.runtime, root / "downloads")
        token = CancelToken()
        if identity is not None:
            with self._cancel_lock:
                self._graph_tokens[identity] = token
                if self._cancel_marker(identity).exists():  # cancelled before it started (also across restarts)
                    token.cancel(CANCELLED_BY_CLIENT)
        try:
            return evaluate_request(p, resolver=resolver, cache_dir=root / "cache", blob_sink=sink, cancel=token)
        except GraphError as exc:
            raise ValueError(_graph_error(exc)) from None
        finally:
            if identity is not None:
                with self._cancel_lock:
                    if self._graph_tokens.get(identity) is token:
                        self._graph_tokens.pop(identity)

    def graph_cancel(self, p):
        """Cancel a ``graph.evaluate`` action: running now, waiting for the graph lane, or not yet received."""
        target = p["action_id"]
        if len(target) != 32 or any(c not in "0123456789abcdef" for c in target):
            raise ValueError("Invalid action ID")
        with self._cancel_lock:
            token = self._graph_tokens.get(target)
            if token is not None:
                token.cancel(CANCELLED_BY_CLIENT)
                return {"cancelled": True, "running": True}
            if (self.cache / (target + ".json")).exists():
                return {"cancelled": False, "finished": True}
            marker = self._cancel_marker(target)
            marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            marker.touch()
        return {"cancelled": True, "running": False}

    def graph_meta(self, p):
        from suan.graph.catalog import catalog_document, default_registry, list_presets
        include = p.get("include") or ["catalog", "presets", "features"]
        result = {"schema": "stk.graph-meta/1"}
        if "catalog" in include:
            result["catalog"] = catalog_document()
            result["load_errors"] = [{"entry_point": name, "error": error}
                                     for name, error in getattr(default_registry(), "load_errors", ())]
        if "presets" in include:
            result["presets"] = [{key: preset[key] for key in ("id", "name", "description", "bindings", "parameters")}
                                 for preset in list_presets()]
        if "features" in include:
            result["features"] = {"agent": FEATURES, "graph_workers": self.graph_workers,
                                  "hub": sorted(self.hub_features) if self.hub_features is not None else None}
        if "render" in include:
            if self._graph_probe is None:
                from suan.graph.cli import probe_offscreen
                self._graph_probe = probe_offscreen()
            result["render"] = self._graph_probe
        return result

    # -- connection --------------------------------------------------------------------------

    def _ensure_lanes(self):
        loop = asyncio.get_running_loop()
        if self._lanes is None or self._lanes["loop"] is not loop:
            # Lanes and in-flight tasks belong to one event loop (a new asyncio.run starts afresh).
            self._lanes = {"loop": loop, "fast": asyncio.Semaphore(FAST_LANE),
                           "graph": asyncio.Semaphore(self.graph_workers), "read": asyncio.Semaphore(READ_LANE)}
            self._inflight = {}

    def dispatch(self, action):
        """Start one action unless it is already running (a re-dispatch after a reconnect)."""
        identity = action.get("id") if isinstance(action, dict) else None
        self._ensure_lanes()
        running = self._inflight.get(identity) if isinstance(identity, str) else None
        if not isinstance(identity, str) or (running is not None and not running.done()):
            return None
        lane = self._lanes["graph" if action.get("kind") in GRAPH_KINDS else "fast"]
        task = asyncio.create_task(self._perform(action, lane))
        self._inflight[identity] = task
        inflight = self._inflight

        def finished(_):
            if inflight.get(identity) is task:
                inflight.pop(identity)
        task.add_done_callback(finished)
        return task

    def public_error(self, exc):
        """Error text for the hub: file-system errors without their paths, and no host path of the agent cache."""
        if isinstance(exc, OSError) and (getattr(exc, "filename", None) is not None
                                         or getattr(exc, "filename2", None) is not None):
            text = f"{type(exc).__name__}: {exc.strerror or 'file system error'}"
        else:
            text = str(exc)
        roots = {str(self.cache)}
        try:
            roots.add(str(self.cache.resolve()))
        except OSError:
            pass
        for root in sorted(roots, key=len, reverse=True):
            text = text.replace(root, "<agent cache>")
        return text[:2000]

    async def _read(self, message, send):
        """Answer one hub read (``type: read``) on the read lane."""
        async with self._lanes["read"]:
            try:
                result = await asyncio.to_thread(self.read, message.get("kind"), message.get("payload"))
                if len(json.dumps(result)) > RESULT_LIMIT:
                    raise ValueError("Result exceeds 12 MiB; read less at a time")
                reply = {"type": "read_result", "id": message["id"], "result": result}
            except Exception as exc:
                reply = {"type": "read_result", "id": message["id"], "error": self.public_error(exc)}
        try:
            await send(reply)
        except Exception:
            pass  # the connection is closing; the client retries the read

    async def _perform(self, action, lane):
        async with lane:
            try:
                result = await asyncio.to_thread(self.execute, action)
                reply = {"type": "result", "id": action["id"], "result": result}
            except Exception as exc:
                reply = {"type": "result", "id": action["id"], "error": self.public_error(exc)}
        send = self._send
        if send is None:
            return  # disconnected: the action stays queued and the hub dispatches it again
        try:
            await send(reply)
        except Exception:
            pass  # the connection is closing; the same applies

    async def serve(self, ws):
        """Serve one open hub connection until it closes."""
        lock = asyncio.Lock()

        async def send(message):
            # One writer at a time: heartbeats and results come from different tasks.
            async with lock:
                await ws.send(json.dumps(message, allow_nan=False))

        async def heartbeat():
            while True:
                try:
                    snapshot = await asyncio.to_thread(self.snapshot)
                except Exception:
                    snapshot = {"error": "Runtime unavailable"}
                await send({"type": "snapshot", "snapshot": snapshot})
                await asyncio.sleep(3)

        self._send = send
        pulse = asyncio.create_task(heartbeat())
        try:
            async for raw in ws:
                data = json.loads(raw)
                if data.get("type") == "action" and isinstance(data.get("action"), dict):
                    self.dispatch(data["action"])
                elif data.get("type") == "read" and isinstance(data.get("id"), str):
                    self._ensure_lanes()
                    task = asyncio.create_task(self._read(data, send))
                    self._reads.add(task)
                    task.add_done_callback(self._reads.discard)
        finally:
            if self._send is send:
                self._send = None
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)

    async def run(self, control_url, token):
        from websockets.asyncio.client import connect
        url = endpoint(control_url, websocket=True)
        if self.blob_sink is None:
            self.blob_sink = BlobUploader(control_url, token)
        if self.blob_source is None:
            self.blob_source = HubBlobSource(control_url, token)
        delay = 1
        while True:
            try:
                try:
                    self.hub_features = await asyncio.to_thread(hub_features, control_url)
                except Exception:
                    if self.hub_features is None:
                        self.hub_features = set()  # unknown hub: no blob uploads until a health check succeeds
                async with connect(url, additional_headers={"Authorization": "Bearer " + token},
                                   max_size=16*1024*1024, proxy=None) as ws:
                    delay = 1
                    await self.serve(ws)
            except Exception as exc:
                # Log the type only: transport exception text can contain headers.
                print(f"Control disconnected ({type(exc).__name__}); retrying in {delay}s", file=sys.stderr)
                await asyncio.sleep(delay)
                delay = min(30, delay*2)
