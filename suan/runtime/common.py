"""Private files, process identities, and cross-platform instance locks."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import secrets
import uuid

from .models import relative_path


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with open(tmp, "x", encoding="utf-8") as stream:
            os.chmod(tmp, 0o600)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def sha256(path):
    result = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inside(root, name):
    if Path(root).is_symlink():
        raise ValueError("Symbolic links are not allowed in managed directories")
    root = Path(root).resolve()
    name = relative_path(name)
    path = root / name
    # Never traverse symlinks, including links whose current target is inside root.
    current = root
    for part in Path(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links are not allowed in managed files")
    resolved = path.resolve()
    if root not in resolved.parents:
        raise ValueError("Path escapes workspace")
    return path


def identity(pid=None):
    import psutil
    process = psutil.Process(pid or os.getpid())
    return {"pid": process.pid, "create_time": process.create_time()}


def alive(record):
    import psutil
    if not record:
        return False
    try:
        process = psutil.Process(record["pid"])
        return process.create_time() == record["create_time"] and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.Error, KeyError):
        return False


@contextmanager
def instance_lock(path):
    """OS releases this lock after crashes; PID files alone are not locks."""
    stream = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        stream.close()


def init_config(state_dir, workspace_root=None, port=8765, concurrency=1):
    state = Path(state_dir).expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with instance_lock(state / "config.lock"):
        existing = read_json(state / "config.json")
        if existing:
            return existing
        if not 0 <= port <= 65535 or concurrency < 1:
            raise ValueError("Invalid port or concurrency")
        root = Path(workspace_root).expanduser().resolve() if workspace_root else state / "workspaces"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        import sys
        config = {"state_dir": str(state), "workspace_root": str(root), "port": port,
                  "concurrency": concurrency, "poll_interval": 1.0, "scheduler_interval": 10.0,
                  "token": secrets.token_urlsafe(32), "python": sys.executable}
        atomic_json(state / "config.json", config)
        return config


def load_config(state_dir):
    config = read_json(Path(state_dir).expanduser().resolve() / "config.json")
    if config is None:
        raise ValueError("Runtime is not initialized; run suan server init")
    return config
