"""Client of the STK control hub (``suan.control.app``) for a paired desktop client device.

urllib without proxies or redirects, so the device credential is only ever sent to the hub origin
it was paired with (HTTPS, or HTTP on loopback; ``suan.control.agent.endpoint``). The credential
stays inside the bridge: it never appears in results, events or error messages.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from suan.control.agent import endpoint

from .protocol import BridgeError

__all__ = ["HubClient", "HubResponseError"]

BLOB_CHUNK = 1024 * 1024


class HubResponseError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise HubResponseError(302, "Control hub redirects are not allowed; pair with the final HTTPS origin")


def _detail(body):
    try:
        detail = json.loads(body).get("detail", "Control hub request rejected")
    except (ValueError, AttributeError):
        return "Control hub request rejected"
    if isinstance(detail, list):  # FastAPI validation errors
        detail = "; ".join(str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail[:5])
    return str(detail)[:2000]


class HubClient:
    def __init__(self, url, token="", timeout=30):
        self.url = endpoint(url)
        self.token = token
        self.timeout = timeout

    def _open(self, request, timeout=None):
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        return opener.open(request, timeout=timeout or self.timeout)

    def _headers(self, extra=None):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        headers.update(extra or {})
        return headers

    def request(self, method, path, body=None):
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8") if body is not None else None
        request = Request(self.url + "/api/v1/" + path, data=data, method=method, headers=self._headers())
        try:
            with self._open(request) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            with exc:
                raise HubResponseError(exc.code, _detail(exc.read())) from None

    # -- API ----------------------------------------------------------------------------------

    def health(self):
        return self.request("GET", "health")

    def claim(self, code, name):
        return self.request("POST", "pairings/claim", {"code": code, "name": name})

    def devices(self):
        return self.request("GET", "devices")

    def templates(self):
        return self.request("GET", "templates")

    def actions(self):
        return self.request("GET", "actions")

    def action(self, action_id):
        return self.request("GET", "actions/" + action_id)

    def post_action(self, body):
        return self.request("POST", "actions", body)

    def review(self, action_id, approved):
        return self.request("POST", f"actions/{action_id}/review", {"approved": bool(approved)})

    def blob(self, digest, target, check=None):
        """Download blob ``digest`` into ``target`` (atomic; sha256 verified); returns its size."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = target.with_name(f".{digest}.{uuid.uuid4().hex}.part")
        request = Request(self.url + "/api/v1/blobs/" + digest, method="GET", headers=self._headers())
        result, size = hashlib.sha256(), 0
        try:
            try:
                response = self._open(request, timeout=max(self.timeout, 120))
            except HTTPError as exc:
                with exc:
                    raise HubResponseError(exc.code, _detail(exc.read())) from None
            with response, open(tmp, "wb") as stream:
                while True:
                    if check is not None:
                        check()
                    block = response.read(BLOB_CHUNK)
                    if not block:
                        break
                    result.update(block)
                    size += len(block)
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
            if result.hexdigest() != digest:
                raise BridgeError("checksum_mismatch", f"Blob {digest} from the hub does not match its sha256")
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return size

    def events(self, after, stop):
        """Server-sent hub events after cursor ``after``: yields ``(cursor, kind, payload)``."""
        request = Request(self.url + "/api/v1/events?after=" + str(int(after)), method="GET", headers=self._headers({
            "Accept": "text/event-stream", "Last-Event-ID": str(int(after))}))
        try:
            response = self._open(request, timeout=30)
        except HTTPError as exc:
            with exc:
                raise HubResponseError(exc.code, _detail(exc.read())) from None
        with response:
            cursor, kind, data = None, "message", []
            for raw in response:
                if stop.is_set():
                    return
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith(":"):
                    continue
                if not line:
                    if cursor is not None and cursor > after:
                        try:
                            payload = json.loads("\n".join(data)) if data else {}
                        except ValueError:
                            payload = {}
                        yield cursor, kind, payload
                        after = cursor
                    cursor, kind, data = None, "message", []
                    continue
                field, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if field == "id":
                    try:
                        cursor = int(value)
                    except ValueError:
                        cursor = None
                elif field == "event":
                    kind = value
                elif field == "data":
                    data.append(value)


def hub_error(exc):
    """A :class:`BridgeError` for a hub transport or response failure (never carrying the credential)."""
    if isinstance(exc, BridgeError):
        return exc
    if isinstance(exc, HubResponseError):
        status, message = exc.status, exc.message
        if status in (401, 403):
            return BridgeError("unauthorized", f"The control hub refused this device ({status}): {message}")
        if status == 404:
            return BridgeError("not_found", message)
        if status in (408, 429) or status >= 500:
            return BridgeError("unavailable", f"The control hub is unavailable ({status}); retry", retryable=True)
        if "already used for a different" in message or "reused" in message:
            return BridgeError("conflict", message)
        return BridgeError("remote_error", message)
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return BridgeError("unavailable", "The control hub did not answer in time; retry")
    if isinstance(exc, (URLError, OSError)):
        return BridgeError("unavailable", f"The control hub cannot be reached ({type(exc).__name__}); retry")
    if isinstance(exc, ValueError):
        return BridgeError("invalid_params", str(exc))
    return BridgeError("internal_error", f"{type(exc).__name__}: {exc}")
