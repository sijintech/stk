"""Outbound Synorder transport for the independent, loopback-only STK Runtime."""
import argparse
import asyncio
import base64
import json
import os
import re
from urllib.parse import urlsplit, urlunsplit

from .client import RuntimeClient, RuntimeErrorResponse
from .common import read_json


class SynorderNode:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, request):
        path, method = request.get("path", ""), request.get("method")
        # Only the v1 Runtime protocol, never a filesystem path or arbitrary URL.
        if not isinstance(path, str) or not re.fullmatch(r"(?:health|tasks|workspaces)(?:/[A-Za-z0-9_/-]+)?(?:\?[A-Za-z0-9_%=&.+-]*)?", path) or method not in {"GET", "POST", "PUT"}:
            raise ValueError("Unsupported Runtime request")
        data = base64.b64decode(request.get("data", ""), validate=True)
        if len(data) > 1024 * 1024:
            raise ValueError("Request exceeds upload chunk budget")
        try:
            raw = self.runtime.request(method, path, data or None, binary=True)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("Response exceeds relay budget")
            status = 200
        except RuntimeErrorResponse as exc:
            status, raw = exc.status, json.dumps({"error": str(exc)}).encode()
        return {"type": "response", "id": request["id"], "status": status, "data": base64.b64encode(raw).decode()}

    async def connect(self, server, node_id, token):
        from websockets.asyncio.client import connect
        origin = urlsplit(server)
        if origin.scheme not in {"http", "https"} or not origin.hostname or origin.username or origin.password or origin.path not in {"", "/"} or origin.query or origin.fragment or origin.scheme == "http" and origin.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use an HTTPS Hub origin (HTTP is limited to loopback)")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", node_id) or not token:
            raise ValueError("Node ID and credential are required")
        url = urlunsplit(("wss" if origin.scheme == "https" else "ws", origin.netloc, "/api/hub/nodes/" + node_id, "", ""))
        async with connect(url, additional_headers={"Authorization": "Bearer " + token}, max_size=24 * 1024 * 1024, proxy=None) as ws:
            async def heartbeat():
                while True:
                    await ws.send('{"type":"heartbeat"}')
                    await asyncio.sleep(10)
            pulse = asyncio.create_task(heartbeat())
            try:
                async for raw in ws:
                    request = json.loads(raw)
                    if request.get("type") != "request":
                        raise ValueError("Unsupported node message")
                    response = await asyncio.to_thread(self.execute, request)
                    await ws.send(json.dumps(response, allow_nan=False))
            finally:
                pulse.cancel()
                await asyncio.gather(pulse, return_exceptions=True)

    async def run(self, *args):
        delay = 1
        while True:
            try:
                await self.connect(*args)
                delay = 1
            except Exception:
                pass
            await asyncio.sleep(delay)
            delay = min(30, delay * 2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--token-env", required=True)
    parser.add_argument("--runtime-config", required=True)
    args = parser.parse_args(argv)
    config = read_json(args.runtime_config)
    client = RuntimeClient(f"http://127.0.0.1:{config['port']}", config["token"])
    token = os.environ.get(args.token_env)
    if not token:
        parser.error("Node credential environment variable is not configured")
    try:
        asyncio.run(SynorderNode(client).run(args.server, args.node_id, token))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
