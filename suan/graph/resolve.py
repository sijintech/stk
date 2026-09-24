"""Binding resolvers: graph binding names -> file sources (``suan.connectors.api.FileSource``).

Graphs never contain filesystem paths. A source node names a *binding* (for
example ``"run"``) plus a relative path inside it; the caller decides what the
binding means:

* :class:`LocalDirResolver` (CLI, desktop): binding -> a local directory. Every
  path is confined to that directory: absolute paths, ``..``, backslashes, drive
  letters and symbolic links that leave the directory are refused.
* :class:`RuntimeResolver` (node agent, MCP): binding -> ``{"task_id"}`` of an
  STK Runtime task. Files come from ``RuntimeClient.artifacts`` and
  ``RuntimeClient.download`` into a content-addressed cache, verified by
  sha256 and capped at 1 GiB per file (the ``view.build`` limit).

Resolvers raise ``KeyError`` for unknown bindings (the evaluator reports
``unknown_binding``); file sources raise ``FileNotFoundError`` for missing files
(``missing_file``) and :class:`PathNotAllowed` for paths outside the binding.
Standard library only.
"""
from collections.abc import Mapping
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import threading
from contextlib import closing

from suan.connectors.api import FileInfo

from .registry import BudgetExceeded, GraphError
from .schema import ID_RE

__all__ = [
    "MAX_DOWNLOAD_BYTES", "BindingResolver", "HashMemo", "LocalDirResolver", "LocalDirSource", "PathNotAllowed",
    "RuntimeResolver", "RuntimeTaskSource", "check_relative_path",
]

MAX_DOWNLOAD_BYTES = 1024**3  # same first-release field limit as view.build
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9_]{1,16}$")
_BLOCK = 1024 * 1024


class PathNotAllowed(GraphError, PermissionError):
    """A path that would leave its binding (absolute, ``..``, backslash, drive letter or an escaping link)."""

    def __init__(self, message, **kw):
        GraphError.__init__(self, "path_not_allowed", message, **kw)
        self.args = (message,)

    def __str__(self):
        return self.message


def check_relative_path(path, *, allow_root=False):
    """Validate a POSIX path relative to a binding root and return it normalized (``"a/b"``).

    ``""`` and ``"."`` mean the root (only with ``allow_root``). Rejects absolute
    paths, drive letters, ``..`` segments, backslashes and NUL characters.
    """
    if not isinstance(path, str):
        raise PathNotAllowed(f"A path inside a binding must be a string, got {type(path).__name__}")
    if path in ("", ".", "./"):
        if allow_root:
            return ""
        raise PathNotAllowed("A file path inside the binding is required")
    if "\\" in path or "\x00" in path:
        raise PathNotAllowed(f"Path {path!r} must use '/' separators and no NUL characters")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise PathNotAllowed(f"Path {path!r} must be relative to the binding")
    parts = [part for part in PurePosixPath(path).parts if part != "."]
    if any(part == ".." for part in parts):
        raise PathNotAllowed(f"Path {path!r} must not contain '..'")
    if not parts:
        if allow_root:
            return ""
        raise PathNotAllowed("A file path inside the binding is required")
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Content hashes of local files


class HashMemo:
    """sha256 of local files memoized by (real path, size, mtime_ns, inode), optionally persisted in SQLite."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self._memory = {}
        self._lock = threading.Lock()
        self._ready = False

    def sha256(self, path):
        path = Path(path)
        info = path.stat()
        key = (str(path), info.st_size, info.st_mtime_ns, getattr(info, "st_ino", 0))
        with self._lock:
            if key in self._memory:
                return self._memory[key]
        digest = self._load(key)
        if digest is None:
            result = hashlib.sha256()
            with open(path, "rb") as stream:
                for block in iter(lambda: stream.read(_BLOCK), b""):
                    result.update(block)
            digest = result.hexdigest()
            self._store(key, digest)
        with self._lock:
            self._memory[key] = digest
        return digest

    def _connect(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        if not self._ready:
            conn.execute("CREATE TABLE IF NOT EXISTS hashes (path TEXT, size INTEGER, mtime_ns INTEGER, inode INTEGER, "
                         "sha256 TEXT, PRIMARY KEY (path, size, mtime_ns, inode))")
            self._ready = True
        return conn

    def _load(self, key):
        if self.path is None:
            return None
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT sha256 FROM hashes WHERE path = ? AND size = ? AND mtime_ns = ? "
                                   "AND inode = ?", key).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def _store(self, key, digest):
        if self.path is None:
            return
        try:
            with closing(self._connect()) as conn:
                conn.execute("DELETE FROM hashes WHERE path = ?", (key[0],))
                conn.execute("INSERT OR REPLACE INTO hashes VALUES (?, ?, ?, ?, ?)", (*key, digest))
        except sqlite3.Error:
            pass


# ---------------------------------------------------------------------------
# Local directories


class LocalDirSource:
    """A local directory as a :class:`suan.connectors.api.FileSource`, confined to ``root``."""

    def __init__(self, root, *, hash_memo=None, binding=None):
        root = Path(root).expanduser()
        if not root.is_dir():
            raise FileNotFoundError(f"Binding {binding or ''} directory not found: {root}".replace("  ", " "))
        self.root = root.resolve()
        self.binding = binding
        self._memo = hash_memo or HashMemo()

    def __repr__(self):
        return f"LocalDirSource({str(self.root)!r})"

    def _path(self, path, *, allow_root=False):
        relative = check_relative_path(path, allow_root=allow_root)
        candidate = self.root / relative if relative else self.root
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise PathNotAllowed(f"Path {path!r} leaves the binding directory (symbolic link)")
        return resolved

    def list(self, prefix=""):
        base = self._path(prefix, allow_root=True)
        if not base.is_dir():
            return []
        found = []
        # os.walk does not descend into linked directories, so only a listed entry itself can be a link.
        for directory, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                full = Path(directory) / name
                try:
                    if os.path.islink(full):
                        resolved = full.resolve()
                        if resolved != self.root and self.root not in resolved.parents:
                            continue  # a link leaving the binding
                        info = resolved.stat()
                    else:
                        info = full.stat()
                except OSError:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    continue
                found.append(FileInfo(full.relative_to(self.root).as_posix(), info.st_size, info.st_mtime))
        return found

    def open(self, path):
        resolved = self._path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"No file {path!r} in the binding{self._name()}")
        return open(resolved, "rb")

    def local_path(self, path):
        """The confined local path; ``""``/``"."`` is the binding directory itself."""
        resolved = self._path(path, allow_root=True)
        if not resolved.exists():
            raise FileNotFoundError(f"No file {path!r} in the binding{self._name()}")
        return resolved

    def sha256(self, path):
        resolved = self._path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"No file {path!r} in the binding{self._name()}")
        return self._memo.sha256(resolved)

    def _name(self):
        return f" '{self.binding}'" if self.binding else ""


class LocalDirResolver:
    """Bindings to local directories: ``LocalDirResolver({"run": "/data/run1"})``."""

    def __init__(self, bindings, *, hash_memo=None):
        self._memo = hash_memo if isinstance(hash_memo, HashMemo) else HashMemo(hash_memo)
        self._sources = {}
        for name, root in dict(bindings).items():
            _check_binding_name(name)
            self._sources[name] = LocalDirSource(root, hash_memo=self._memo, binding=name)

    def names(self):
        return sorted(self._sources)

    def resolve(self, binding):
        try:
            return self._sources[binding]
        except KeyError:
            raise KeyError(binding) from None


# ---------------------------------------------------------------------------
# STK Runtime tasks


class RuntimeTaskSource:
    """The published artifacts of one Runtime task as a :class:`suan.connectors.api.FileSource`.

    Listing and hashes come from ``client.artifacts(task_id)`` (only files of
    finished tasks are listed in API v1). ``open``/``local_path`` download a file
    once into ``<cache_dir>/<sha[:2]>/<sha><suffix>`` (verified by
    ``RuntimeClient.download``); files over ``max_bytes`` are refused.
    """

    _locks = {}
    _locks_guard = threading.Lock()
    # Downloads verified by this process: path -> (size, mtime_ns). Requests bind new sources, and
    # RuntimeClient.download would otherwise re-hash an existing (up to 1 GiB) file every time.
    _verified = {}

    def __init__(self, client, task_id, cache_dir, *, max_bytes=MAX_DOWNLOAD_BYTES, binding=None):
        if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
            raise GraphError("unknown_binding", f"Invalid task id {task_id!r} for binding '{binding}'")
        self.client = client
        self.task_id = task_id
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.max_bytes = max_bytes
        self.binding = binding
        self._items = None

    def __repr__(self):
        return f"RuntimeTaskSource(task_id={self.task_id!r})"

    def _artifacts(self):
        if self._items is None:
            items = {}
            for item in self.client.artifacts(self.task_id) or ():
                try:
                    items[check_relative_path(item["path"])] = item
                except (PathNotAllowed, KeyError, TypeError):
                    continue
            self._items = items
        return self._items

    def _item(self, path):
        relative = check_relative_path(path)
        item = self._artifacts().get(relative)
        if item is None:
            raise FileNotFoundError(f"Task {self.task_id} has no published file {relative!r} "
                                    "(files are listed once the task has finished)")
        return item

    def list(self, prefix=""):
        base = check_relative_path(prefix, allow_root=True)
        result = []
        for relative, item in sorted(self._artifacts().items()):
            if base and not relative.startswith(base + "/"):
                continue
            result.append(FileInfo(relative, int(item["size"]), None))
        return result

    def sha256(self, path):
        return self._item(path)["sha256"]

    def local_path(self, path):
        """Download (once, sha256-verified) and return the cached local copy; directories are not available."""
        if check_relative_path(path, allow_root=True) == "":
            return None
        item = self._item(path)
        size, digest = int(item["size"]), item["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
            raise GraphError("missing_file", f"Task {self.task_id} lists {path!r} without a sha256")
        if self.max_bytes is not None and size > self.max_bytes:
            raise BudgetExceeded(f"{path!r} is {size} bytes; the per-file download limit is {self.max_bytes} bytes "
                                 "(first-release regular field limit is 1 GiB)")
        suffix = PurePosixPath(item["path"]).suffix
        target = self.cache_dir / digest[:2] / (digest + (suffix if _SUFFIX_RE.match(suffix) else ""))
        with self._lock(target):
            try:
                info = target.stat()
                if self._verified.get(str(target)) == (size, info.st_mtime_ns) and info.st_size == size:
                    return target
            except FileNotFoundError:
                pass
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.client.download(self.task_id, item["path"], target)  # resumable; verifies size and sha256
            if not target.is_file() or target.stat().st_size != size:
                raise GraphError("missing_file", f"Download of {path!r} from task {self.task_id} failed")
            self._verified[str(target)] = (size, target.stat().st_mtime_ns)
        return target

    def open(self, path):
        return open(self.local_path(path), "rb")

    @classmethod
    def _lock(cls, target):
        with cls._locks_guard:
            return cls._locks.setdefault(str(target), threading.Lock())


class RuntimeResolver:
    """Bindings to Runtime tasks: ``RuntimeResolver(client, cache_dir).bind({"run": {"task_id": "..."}})``."""

    def __init__(self, client, cache_dir, bindings=None, *, max_bytes=MAX_DOWNLOAD_BYTES):
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.max_bytes = max_bytes
        self._tasks = {}
        self._sources = {}
        for name, value in (bindings or {}).items():
            _check_binding_name(name)
            if isinstance(value, Mapping):
                if set(value) != {"task_id"}:
                    raise GraphError("unknown_binding", f"Binding '{name}' must be {{\"task_id\": \"...\"}}; "
                                     "paths are never accepted from requests")
                value = value["task_id"]
            if not isinstance(value, str) or not TASK_ID_RE.match(value):
                raise GraphError("unknown_binding", f"Binding '{name}' has an invalid task id")
            self._tasks[name] = value

    def bind(self, bindings):
        """A resolver for request bindings ``{name: {"task_id": id}}`` sharing this client and cache."""
        return RuntimeResolver(self.client, self.cache_dir, {**self._tasks, **dict(bindings or {})},
                               max_bytes=self.max_bytes)

    def names(self):
        return sorted(self._tasks)

    def resolve(self, binding):
        if binding not in self._tasks:
            raise KeyError(binding)
        if binding not in self._sources:
            self._sources[binding] = RuntimeTaskSource(self.client, self._tasks[binding], self.cache_dir,
                                                       max_bytes=self.max_bytes, binding=binding)
        return self._sources[binding]


class BindingResolver:
    """Several resolvers (or a mapping of binding -> FileSource) combined; the first that knows a binding wins."""

    def __init__(self, *resolvers):
        self.resolvers = [r for r in resolvers if r is not None]

    def names(self):
        names = set()
        for resolver in self.resolvers:
            names.update(resolver.keys() if isinstance(resolver, Mapping) else resolver.names())
        return sorted(names)

    def resolve(self, binding):
        for resolver in self.resolvers:
            try:
                return resolver[binding] if isinstance(resolver, Mapping) else resolver.resolve(binding)
            except KeyError:
                continue
        raise KeyError(binding)

    def bind(self, bindings):
        bound = [r.bind(bindings) if hasattr(r, "bind") else r for r in self.resolvers]
        return BindingResolver(*bound)


def _check_binding_name(name):
    if not isinstance(name, str) or not ID_RE.match(name):
        raise GraphError("unknown_binding", f"Binding name {name!r} must match ^[a-z][a-z0-9_]{{0,63}}$")
