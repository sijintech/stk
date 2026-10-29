"""Durable local training receipts and curves; reads never start or recover work."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time


class StorageError(RuntimeError):
    pass


class Locked(StorageError):
    pass


_GUARD = threading.Lock()
_HELD = set()
STATES = {"prepared", "running", "done", "rejected", "cancelled", "failed", "interrupted", "uncertain"}


def private_directory(path, *, create=True):
    """Reject linked directory components, including Windows junctions."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise StorageError("Training state paths must not contain traversal")
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if not create:
                raise
            try:
                part.mkdir(mode=0o700)
            except FileExistsError:
                pass
            info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or _linked(info):
            raise StorageError("Training state directories must be ordinary directories")
    if create and os.name != "nt":
        path.chmod(0o700)
    return path


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def ordinary(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or _linked(info):
        raise StorageError("Training state must use ordinary files")
    return info


class Lease:
    """A persistent lock file plus a same-process guard; never unlink lock files."""
    def __init__(self, path, *, timeout=0):
        self.path = Path(path).absolute()
        self.key = os.path.normcase(os.path.realpath(self.path))
        self.stream = None
        self.held = False
        deadline = time.monotonic() + timeout
        while True:
            with _GUARD:
                acquired = self.key not in _HELD
                if acquired:
                    _HELD.add(self.key)
                    self.held = True
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise Locked("Another materials operation holds this lease")
            time.sleep(0.025)
        try:
            private_directory(self.path.parent)
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o600)
            self.stream = os.fdopen(fd, "r+b", buffering=0)
            opened, named = os.fstat(fd), ordinary(self.path)
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                raise StorageError("Training lease changed while opening")
            if os.name == "nt" and opened.st_size == 0:
                self.stream.write(b"\0")
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        self.stream.seek(0)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise Locked("Another materials process holds this lease") from None
                    time.sleep(0.025)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.stream is not None:
            # Closing releases the operating system lease, even after a crash.
            self.stream.close()
            self.stream = None
        if self.held:
            with _GUARD:
                _HELD.discard(self.key)
            self.held = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _json(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 1024 * 1024:
        raise StorageError("Training receipt exceeds its metadata budget")
    return encoded


class Store:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.path = self.root / "training.sqlite3"

    @contextmanager
    def _connect(self, *, write=False):
        connection = None
        try:
            if not write and not self.path.exists() and not self.path.is_symlink():
                yield None
                return
            if write:
                private_directory(self.root)
            else:
                private_directory(self.root, create=False)
            if self.path.exists() or self.path.is_symlink():
                ordinary(self.path)
            uri = self.path.as_uri() + ("?mode=rwc" if write else "?mode=ro")
            connection = sqlite3.connect(uri, uri=True, timeout=15)
            connection.execute("PRAGMA foreign_keys=ON")
            if write:
                if os.name != "nt":
                    self.path.chmod(0o600)
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, definition TEXT NOT NULL, "
                                   "record TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS epochs (job TEXT NOT NULL REFERENCES jobs(id), "
                                   "epoch INTEGER NOT NULL CHECK(epoch BETWEEN 1 AND 5000), train REAL NOT NULL, "
                                   "validation REAL NOT NULL, PRIMARY KEY(job,epoch))")
            with connection:
                yield connection
        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            raise StorageError(f"Training state cannot be read or written: {type(exc).__name__}") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _record(row):
        if row is None:
            return None
        if len(row[0]) > 1024 * 1024:
            raise StorageError("Training receipt exceeds its metadata budget")
        result = json.loads(row[0])
        if not isinstance(result, dict) or result.get("state") not in STATES:
            raise StorageError("Training receipt is damaged")
        return result

    def get(self, job_id):
        with self._connect() as connection:
            if connection is None:
                return None
            return self._record(connection.execute("SELECT record FROM jobs WHERE id=?", (job_id,)).fetchone())

    def create(self, definition, record):
        with self._connect(write=True) as connection:
            connection.execute("INSERT INTO jobs VALUES (?,?,?)", (record["id"], _json(definition), _json(record)))

    def update(self, job_id, changes, *, epoch=None):
        with self._connect(write=True) as connection:
            # Serialize read/modify/write, including requests from another service process.
            connection.execute("BEGIN IMMEDIATE")
            record = self._record(connection.execute("SELECT record FROM jobs WHERE id=?", (job_id,)).fetchone())
            if record is None:
                raise StorageError("No such training receipt")
            record.update(changes)
            if record.get("state") not in STATES:
                raise StorageError("Invalid training state")
            connection.execute("UPDATE jobs SET record=? WHERE id=?", (_json(record), job_id))
            if epoch is not None:
                connection.execute("INSERT INTO epochs VALUES (?,?,?,?)", (job_id, *epoch))
            return record

    def list(self, *, offset=0, limit=50):
        with self._connect() as connection:
            if connection is None:
                return {"jobs": [], "offset": offset, "total": 0, "next_offset": None}
            connection.execute("BEGIN")
            total = connection.execute("SELECT count(*) FROM jobs").fetchone()[0]
            records = [self._record(row) for row in connection.execute(
                "SELECT record FROM jobs ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset))]
            end = offset + len(records)
            return {"jobs": records, "offset": offset, "total": total, "next_offset": end if end < total else None}

    def curves(self, job_id, *, after=0, limit=200):
        with self._connect() as connection:
            if connection is None:
                return 0, []
            connection.execute("BEGIN")
            job = self._record(connection.execute("SELECT record FROM jobs WHERE id=?", (job_id,)).fetchone())
            if job is None:
                raise StorageError("No such training receipt")
            values = [{"epoch": row[0], "train_loss": row[1], "validation_loss": row[2]} for row in connection.execute(
                "SELECT epoch,train,validation FROM epochs WHERE job=? AND epoch>? ORDER BY epoch LIMIT ?",
                (job_id, after, limit))]
            return job["epoch"], values
