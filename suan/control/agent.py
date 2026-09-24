"""Outbound-only node agent. Runtime remains the authority for execution.

Actions run concurrently: a fast lane for Runtime calls and views, and a graph
lane (1-2 evaluations at a time) for ``graph.evaluate``. An action that is
still running when the hub dispatches it again (for example after a
reconnect) is not started twice; its result goes out on whichever connection
is open when it finishes. Graph outputs (payload buffers, images, plots)
travel to the hub's blob store over outbound HTTPS (``HEAD`` before ``PUT``);
the hub-agent WebSocket carries no new message types.
"""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
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
FEATURES = ["graph.evaluate", "graph.meta", "task.events"]
# Pure reads: re-running them is harmless, so their results are not kept in the action cache.
UNCACHED = {"task.events", "graph.meta"}
GRAPH_KINDS = {"graph.evaluate"}
RESULT_LIMIT = 12 * 1024 * 1024
FAST_LANE = 4


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
    def __init__(self, runtime, cache_dir, *, blob_sink=None, graph_workers=1):
        self.runtime = runtime
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
            data = self.runtime.request("GET", f"tasks/{p['task_id']}/file?{query}", binary=True)
            result = {"data": base64.b64encode(data).decode(), "offset": int(p.get("offset", 0))+len(data)}
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
            result = self.graph_evaluate(p)
        elif kind == "graph.meta":
            result = self.graph_meta(p)
        else:
            raise ValueError("Unknown node operation")
        if len(json.dumps(result)) > RESULT_LIMIT:
            raise ValueError("Result exceeds 12 MiB preview budget; reduce view resolution")
        if cacheable:
            atomic_json(self.cache / (identity + ".json"), {"request": action, "result": result})
        return result

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

    def graph_evaluate(self, p):
        from suan.graph.registry import GraphError
        from suan.graph.resolve import RuntimeResolver
        from suan.graph.service import evaluate_request
        sink = self.blob_sink
        if sink is None:
            raise ValueError("This agent has no blob upload channel to the control hub")
        if self.hub_features is not None and "blobs" not in self.hub_features:
            raise ValueError("The control hub does not accept result blobs; upgrade the STK control service")
        root = self.cache / "graph"
        resolver = RuntimeResolver(self.runtime, root / "downloads")
        try:
            return evaluate_request(p, resolver=resolver, cache_dir=root / "cache", blob_sink=sink)
        except GraphError as exc:
            raise ValueError(_graph_error(exc)) from None

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

    def dispatch(self, action):
        """Start one action unless it is already running (a re-dispatch after a reconnect)."""
        identity = action.get("id") if isinstance(action, dict) else None
        loop = asyncio.get_running_loop()
        if self._lanes is None or self._lanes["loop"] is not loop:
            # Lanes and in-flight tasks belong to one event loop (a new asyncio.run starts afresh).
            self._lanes = {"loop": loop, "fast": asyncio.Semaphore(FAST_LANE),
                           "graph": asyncio.Semaphore(self.graph_workers)}
            self._inflight = {}
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

    async def _perform(self, action, lane):
        async with lane:
            try:
                result = await asyncio.to_thread(self.execute, action)
                reply = {"type": "result", "id": action["id"], "result": result}
            except Exception as exc:
                reply = {"type": "result", "id": action["id"], "error": str(exc)[:2000]}
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
