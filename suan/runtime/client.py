"""The same transport client is used by CLI, MCP and Qt worker threads."""

from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import base64
import json
import os
import time
import uuid

from .common import atomic_json, read_json, sha256
from .models import TaskSpec, TERMINAL
from .service import CHUNK_SIZE


class RuntimeErrorResponse(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeErrorResponse(302, "Runtime redirects are not allowed")


class RuntimeClient:
    def __init__(self, url, token, timeout=30):
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("Use a loopback HTTP endpoint, directly or through an SSH tunnel")
        if not token:
            raise ValueError("A runtime token is required")
        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout

    def request(self, method, path, data=None, binary=False):
        body = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
        request = Request(self.url + "/v1/" + path, data=body, method=method,
                          headers={"Authorization": "Bearer " + self.token,
                                   "Content-Type": "application/octet-stream" if isinstance(data, bytes) else "application/json"})
        # No proxy or redirects: a local token must never be forwarded elsewhere.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=self.timeout) as response:
                result = response.read()
        except HTTPError as exc:
            try:
                message = json.loads(exc.read())["error"]
            except (ValueError, KeyError):
                message = str(exc)
            raise RuntimeErrorResponse(exc.code, message) from exc
        return result if binary else json.loads(result)

    def health(self):
        return self.request("GET", "health")

    def create_workspace(self, name, idempotency_key=None):
        return self.request("POST", "workspaces", {"name": name, "idempotency_key": idempotency_key})

    def workspaces(self):
        return self.request("GET", "workspaces")

    def files(self, workspace_id):
        return self.request("GET", f"workspaces/{workspace_id}/files")

    def submit(self, spec, idempotency_key=None):
        if isinstance(spec, TaskSpec):
            spec = spec.to_dict()
        return self.request("POST", "tasks", {"spec": spec, "idempotency_key": idempotency_key or uuid.uuid4().hex})

    def tasks(self, workspace_id=None):
        return self.request("GET", "tasks" + ("?" + urlencode({"workspace_id": workspace_id}) if workspace_id else ""))

    def task(self, task_id):
        return self.request("GET", f"tasks/{task_id}")

    def cancel(self, task_id):
        return self.request("POST", f"tasks/{task_id}/cancel", {})

    def logs(self, task_id, stream="stdout", offset=0):
        response = self.request("GET", f"tasks/{task_id}/logs?" + urlencode({"stream": stream, "offset": offset}))
        response["bytes"] = base64.b64decode(response["data"])
        return response

    def events(self, task_id, offset=0, limit=CHUNK_SIZE):
        """Monitoring events from byte ``offset``: {events, offset, next_offset, size, terminal, invalid}.

        Needs a Runtime whose health lists the "events" feature.
        """
        return self.request("GET", f"tasks/{task_id}/events?" + urlencode({"offset": offset, "limit": limit}))

    def artifacts(self, task_id):
        return self.request("GET", f"tasks/{task_id}/artifacts")

    def upload(self, workspace_id, local_file, remote_path=None):
        path = Path(local_file)
        if not path.is_file() or path.is_symlink():
            raise ValueError("Upload source must be a regular file")
        digest = sha256(path)
        prefix = f"workspaces/{workspace_id}/uploads"
        meta = self.request("POST", prefix, {"path": remote_path or path.name, "size": path.stat().st_size, "sha256": digest})
        if not meta["completed"]:
            with open(path, "rb") as stream:
                stream.seek(meta["offset"])
                for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
                    meta = self.request("PUT", f"{prefix}/{meta['id']}?offset={meta['offset']}", chunk)
            meta = self.request("POST", f"{prefix}/{meta['id']}/finish", {})
        return meta

    def download(self, task_id, remote_path, destination):
        items = self.artifacts(task_id)
        item = next((a for a in items if a["path"] == remote_path), None)
        if item is None:
            raise ValueError("Artifact not found; wait for the task to finish")
        return self._download(f"tasks/{task_id}/file", item, destination)

    def download_input(self, workspace_id, remote_path, destination):
        item = next((a for a in self.files(workspace_id) if a["path"] == remote_path), None)
        if item is None:
            raise ValueError("Workspace file not found")
        return self._download(f"workspaces/{workspace_id}/file", item, destination)

    def _download(self, route, item, destination):
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and sha256(path) == item["sha256"]:
            return path
        part = path.with_name(path.name + ".part")
        meta = path.with_name(path.name + ".part.json")
        if read_json(meta) != item or (part.exists() and part.stat().st_size > item["size"]):
            part.unlink(missing_ok=True)
        atomic_json(meta, item)
        offset = part.stat().st_size if part.exists() else 0
        with open(part, "ab") as stream:
            while offset < item["size"]:
                query = urlencode({"path": item["path"], "offset": offset, "limit": CHUNK_SIZE})
                chunk = self.request("GET", route + "?" + query, binary=True)
                if not chunk:
                    raise RuntimeError("Download ended before the declared file size")
                stream.write(chunk)
                stream.flush()
                offset += len(chunk)
            os.fsync(stream.fileno())
        if part.stat().st_size != item["size"] or sha256(part) != item["sha256"]:
            part.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            raise RuntimeError("Downloaded file checksum mismatch; retry the download")
        os.replace(part, path)
        meta.unlink()
        return path

    def wait(self, task_id, timeout=300, interval=0.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.task(task_id)
            if record["state"] in TERMINAL:
                return record
            time.sleep(interval)
        raise TimeoutError(f"Task {task_id} is still active; waiting timed out without cancelling it")
