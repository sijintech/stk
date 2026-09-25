"""Outbound-only node agent. Runtime remains the authority for execution."""
import asyncio
import base64
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlsplit, urlunsplit

from suan.runtime.client import RuntimeClient
from suan.runtime.common import atomic_json, read_json
from suan.runtime.models import relative_path

# muFerro writes field frames as <Stem>.<kt:08d>.dat with stems of at most 8 characters.
MUPRO_FRAME = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9_]{0,7})\.(\d{8})\.dat$")


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


class NodeAgent:
    def __init__(self, runtime, cache_dir):
        self.runtime = runtime
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)

    def snapshot(self):
        import psutil
        tasks = self.runtime.tasks()
        # Credentials and arbitrary environment variables never leave the node.
        tasks = [{k: v for k, v in t.items() if k != "spec"} | {"name": t["spec"]["name"],
                  "workspace_id": t["spec"]["workspace_id"]} for t in tasks[:200]]
        return {"health": self.runtime.health(), "workspaces": self.runtime.workspaces(), "tasks": tasks,
                "cpu_percent": psutil.cpu_percent(), "memory_percent": psutil.virtual_memory().percent}

    def execute(self, action):
        identity = action["id"]
        if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid action ID")
        cached = read_json(self.cache / (identity + ".json"))
        if cached:
            if cached["request"] != action:
                raise ValueError("Action ID reused with a different request")
            return cached["result"]
        kind, p = action["kind"], action["payload"]
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
        else:
            raise ValueError("Unknown node operation")
        if len(json.dumps(result)) > 12*1024*1024:
            raise ValueError("Result exceeds 12 MiB preview budget; reduce view resolution")
        atomic_json(self.cache / (identity + ".json"), {"request": action, "result": result})
        return result

    async def run(self, control_url, token):
        from websockets.asyncio.client import connect
        url = endpoint(control_url, websocket=True)
        delay = 1
        while True:
            try:
                async with connect(url, additional_headers={"Authorization": "Bearer " + token},
                                   max_size=16*1024*1024, proxy=None) as ws:
                    delay = 1

                    async def heartbeat():
                        while True:
                            try:
                                snapshot = await asyncio.to_thread(self.snapshot)
                            except Exception:
                                snapshot = {"error": "Runtime unavailable"}
                            await ws.send(json.dumps({"type": "snapshot", "snapshot": snapshot}, allow_nan=False))
                            await asyncio.sleep(3)

                    pulse = asyncio.create_task(heartbeat())
                    try:
                        async for raw in ws:
                            data = json.loads(raw)
                            if data.get("type") != "action":
                                continue
                            action = data["action"]
                            try:
                                result = await asyncio.to_thread(self.execute, action)
                                reply = {"type": "result", "id": action["id"], "result": result}
                            except Exception as exc:
                                reply = {"type": "result", "id": action["id"], "error": str(exc)[:2000]}
                            await ws.send(json.dumps(reply, allow_nan=False))
                    finally:
                        pulse.cancel()
                        await asyncio.gather(pulse, return_exceptions=True)
            except Exception as exc:
                # Log the type only: transport exception text can contain headers.
                print(f"Control disconnected ({type(exc).__name__}); retrying in {delay}s", file=sys.stderr)
                await asyncio.sleep(delay)
                delay = min(30, delay*2)
