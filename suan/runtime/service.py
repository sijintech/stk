"""Workspace, transfer, snapshot and task operations behind every frontend."""

from dataclasses import asdict
from pathlib import Path
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import threading
import uuid

from .common import atomic_json, inside, now, read_json, sha256
from .models import Artifact, TaskSpec, Workspace, TERMINAL, relative_path
from .store import Store

CHUNK_SIZE = 1024 * 1024


class RuntimeService:
    def __init__(self, config):
        self.config = config
        self.store = Store(config["state_dir"])
        self.lock = threading.RLock()

    def workspace_dir(self, workspace_id):
        self.store.workspace(workspace_id)
        return inside(self.config["workspace_root"], workspace_id)

    def task_dir(self, task_id):
        record = self.store.task(task_id)
        return inside(self.workspace_dir(record["spec"]["workspace_id"]) / "runs", task_id)

    def create_workspace(self, name, idempotency_key=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Workspace name must contain 1–200 characters")
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200):
            raise ValueError("Invalid workspace idempotency key")
        identity = hashlib.sha256(("workspace:" + idempotency_key).encode()).hexdigest()[:32] if idempotency_key else uuid.uuid4().hex
        with self.lock:
            try:
                old = self.store.workspace(identity)
            except KeyError:
                old = None
            if old:
                if old["name"] != name.strip():
                    raise ValueError("Workspace idempotency key reused with a different name")
                return old
            record = asdict(Workspace(identity, name.strip(), now()))
            root = Path(self.config["workspace_root"]) / record["id"]
            for folder in ("inputs", "uploads", "runs"):
                (root / folder).mkdir(parents=True, mode=0o700)
            self.store.add_workspace(record)
            return record

    def list_files(self, workspace_id):
        root = self.workspace_dir(workspace_id) / "inputs"
        return [self.describe(root, p.relative_to(root).as_posix())
                for p in sorted(root.rglob("*")) if p.is_file()]

    def describe(self, root, name):
        path = inside(root, name)
        if not path.is_file():
            raise KeyError("File not found")
        return asdict(Artifact(name, path.stat().st_size, sha256(path),
                              mimetypes.guess_type(name)[0] or "application/octet-stream"))

    def begin_upload(self, workspace_id, path, size, digest):
        import re
        relative_path(path)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("Upload size must be a nonnegative integer")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("A SHA-256 digest is required")
        root = self.workspace_dir(workspace_id)
        target = inside(root / "inputs", path)
        upload_id = hashlib.sha256((path + "\0" + digest).encode()).hexdigest()
        meta_path = root / "uploads" / (upload_id + ".json")
        part = root / "uploads" / (upload_id + ".part")
        with self.lock:
            # Explicitly uploading a new revision supersedes unfinished revisions.
            for old in (root / "uploads").glob("*.json"):
                data = read_json(old)
                if data["path"] == path and old != meta_path:
                    old.with_suffix(".part").unlink(missing_ok=True)
                    old.unlink()
            completed = target.is_file() and target.stat().st_size == size and sha256(target) == digest
            old = read_json(meta_path)
            if not old or old["size"] != size or old.get("completed"):
                part.unlink(missing_ok=True)
            offset = size if completed else part.stat().st_size if part.exists() else 0
            meta = {"id": upload_id, "path": path, "size": size, "sha256": digest,
                    "completed": completed, "offset": offset}
            atomic_json(meta_path, meta)
        return meta

    def upload_status(self, workspace_id, upload_id):
        root = self.workspace_dir(workspace_id) / "uploads"
        path = inside(root, upload_id + ".json")
        data = read_json(path)
        if data is None:
            raise KeyError("Upload not found")
        part = path.with_suffix(".part")
        data["offset"] = data["size"] if data["completed"] else part.stat().st_size if part.exists() else 0
        return data

    def upload_chunk(self, workspace_id, upload_id, offset, body):
        with self.lock:
            meta = self.upload_status(workspace_id, upload_id)
            if meta["completed"] or offset != meta["offset"] or len(body) > CHUNK_SIZE or offset + len(body) > meta["size"]:
                raise ValueError("Upload offset/size conflict; query upload status before retrying")
            part = inside(self.workspace_dir(workspace_id) / "uploads", upload_id + ".part")
            with open(part, "ab") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            return self.upload_status(workspace_id, upload_id)

    def finish_upload(self, workspace_id, upload_id):
        with self.lock:
            meta = self.upload_status(workspace_id, upload_id)
            if meta["completed"]:
                return meta
            root = self.workspace_dir(workspace_id)
            part = inside(root / "uploads", upload_id + ".part")
            if not part.exists() and meta["size"] == 0:
                part.touch()
            if not part.exists() or part.stat().st_size != meta["size"] or sha256(part) != meta["sha256"]:
                raise ValueError("Upload is incomplete or checksum does not match")
            target = inside(root / "inputs", meta["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(part, target)
            meta.update(completed=True, offset=meta["size"])
            atomic_json(root / "uploads" / (upload_id + ".json"), meta)
            return meta

    def abort_upload(self, workspace_id, upload_id):
        with self.lock:
            self.upload_status(workspace_id, upload_id)
            root = self.workspace_dir(workspace_id) / "uploads"
            inside(root, upload_id + ".part").unlink(missing_ok=True)
            inside(root, upload_id + ".json").unlink()
        return {"aborted": True}

    def submit(self, spec, key):
        if not isinstance(spec, TaskSpec):
            spec = TaskSpec(**spec)
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ValueError("An idempotency key of 1–200 characters is required")
        workspace = self.workspace_dir(spec.workspace_id)
        payload = spec.to_dict()
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock:
            record, created = self.store.reserve(uuid.uuid4().hex, key, digest, payload)
            if not created:
                return record
            root = workspace / "runs" / record["id"]
            try:
                for path in (workspace / "uploads").glob("*.json"):
                    meta = read_json(path)
                    if not meta["completed"] and (spec.inputs is None or meta["path"] in spec.inputs):
                        raise ValueError("Finish or abort pending uploads before submitting")
                work = root / "work"
                work.mkdir(parents=True, mode=0o700)
                inputs = workspace / "inputs"
                names = spec.inputs if spec.inputs is not None else [p.relative_to(inputs).as_posix() for p in sorted(inputs.rglob("*")) if p.is_file() or p.is_symlink()]
                manifest = []
                for name in names:
                    source = inside(inputs, name)
                    if not source.is_file():
                        raise ValueError(f"Input file not found: {name}")
                    target = inside(work, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    manifest.append(self.describe(work, name))
                atomic_json(root / "inputs.json", manifest)
                atomic_json(root / "launch.json", {"task_id": record["id"], "spec": payload, "python": self.config["python"]})
                shutil.copyfile(Path(__file__).with_name("worker.py"), root / "worker.py")
                return self.store.update(record["id"], state="queued", input_manifest=manifest)
            except Exception as exc:
                self.store.update(record["id"], state="failed", reason=f"Input preparation failed: {exc}")
                raise

    def cancel(self, task_id):
        with self.lock:
            record = self.store.task(task_id)
            if record["state"] in TERMINAL:
                return record
            root = self.task_dir(task_id)
            root.mkdir(parents=True, exist_ok=True)
            (root / "cancel").touch()
            record = self.store.update(task_id, cancel_requested=True)
            if not record.get("attempted_at"):
                record = self.store.update(task_id, expected={"queued", "preparing"}, state="cancelled", reason="Cancelled before dispatch")
            return record

    def logs(self, task_id, stream="stdout", offset=0, limit=CHUNK_SIZE):
        if stream not in {"stdout", "stderr", "scheduler.out", "scheduler.err", "wrapper"}:
            raise ValueError("Unknown log stream")
        if offset < 0 or not 1 <= limit <= CHUNK_SIZE:
            raise ValueError("Invalid log range")
        name = stream if stream.startswith("scheduler.") else stream + ".log"
        path = inside(self.task_dir(task_id), name)
        if not path.exists():
            data = b""
        else:
            if offset > path.stat().st_size:
                raise ValueError("Offset exceeds log size")
            with open(path, "rb") as file:
                file.seek(offset)
                data = file.read(limit)
        # Byte offsets + base64 preserve UTF-8 characters split across chunks.
        return {"data": base64.b64encode(data).decode("ascii"), "offset": offset,
                "next_offset": offset + len(data), "terminal": self.store.task(task_id)["state"] in TERMINAL}

    def artifacts(self, task_id):
        record = self.store.task(task_id)
        if record["state"] not in TERMINAL:
            return []
        root = self.task_dir(task_id)
        cached = read_json(root / 'artifacts.json')
        if cached is not None:
            return cached
        work = root / "work"
        originals = {x["path"]: x["sha256"] for x in record.get("input_manifest", [])}
        items = []
        for path in sorted(work.rglob("*")):
            if path.is_file():
                try:
                    item = self.describe(work, path.relative_to(work).as_posix())
                except ValueError:
                    continue
                if originals.get(item["path"]) != item["sha256"] or item["path"] in record["spec"]["outputs"]:
                    items.append(item)
        atomic_json(root / 'artifacts.json', items)
        return items

    def file_chunk(self, root, name, offset, limit):
        if offset < 0 or not 1 <= limit <= CHUNK_SIZE:
            raise ValueError("Invalid file range")
        path = inside(root, name)
        if not path.is_file():
            raise KeyError("File not found")
        if offset > path.stat().st_size:
            raise ValueError("Offset exceeds file size")
        with open(path, "rb") as stream:
            stream.seek(offset)
            return stream.read(limit)
