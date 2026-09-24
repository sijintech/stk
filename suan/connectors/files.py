"""File sources (``suan.connectors.api.FileSource``): a local directory and a Runtime task's files.

This is the one implementation of STK's file sources; graph bindings
(``suan.graph.resolve``) use these classes too. Paths are POSIX, relative to
the source root, never absolute and never ``..``; a path whose real location
leaves the root (a symbolic link pointing outside) is refused, so a binding can
read nothing else.

* :class:`LocalFiles` -- a directory on this host (zero-copy ``local_path``).
  sha256 values are memoized by (path, size, mtime_ns, inode) in a
  :class:`HashMemo` (process-wide by default, optionally persisted in SQLite).
* :class:`RuntimeFiles` -- the published files of a Runtime task, listed with
  their sizes and sha256 by the Runtime API. Files are downloaded on first use
  into a content-addressed cache ``<cache_dir>/objects/<aa>/<sha256><suffix>``,
  verified by ``RuntimeClient.download`` and capped at 1 GiB per file (the
  ``view.build`` limit); later reads reuse the verified copy. The Runtime
  publishes a task's files when it finishes, so running tasks list nothing yet.

Errors: a missing file raises :class:`MissingFile` (a ``ConnectorError`` with
code ``missing_file`` *and* a ``FileNotFoundError``); a path that would leave
the source raises :class:`PathNotAllowed` (code ``invalid_path``, also a
``PermissionError``); a file over the download cap raises ``ConnectorError``
code ``budget_exceeded``. Subclasses may raise their own classes
(``path_error``, ``_too_large``), as ``suan.graph.resolve`` does for graph
error codes.

``list(prefix)`` returns the regular files whose path starts with ``prefix`` and
continues after it: a directory (``"case16"`` or ``"case16/"``; listed
recursively) or a file-name prefix inside one (``"case16/Polar."``). Paths are
reported as requested, also when the prefix is a symbolic link to a directory
inside the root; links that leave the root, and link loops, are skipped.
"""
from contextlib import closing
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat as _stat
import tempfile
import threading

from .api import ConnectorError, FileInfo

__all__ = ["MAX_DOWNLOAD_BYTES", "HashMemo", "LocalFiles", "MissingFile", "PathNotAllowed", "RuntimeFiles",
           "check_path", "materialize"]

MAX_DOWNLOAD_BYTES = 1024**3  # same first-release field limit as view.build
_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9_]{1,16}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_BLOCK = 1 << 20


class MissingFile(ConnectorError, FileNotFoundError):
    """A file that does not exist in its source: ``ConnectorError`` code ``missing_file`` and a ``FileNotFoundError``."""

    def __init__(self, message, code="missing_file"):
        ConnectorError.__init__(self, message, code)


class PathNotAllowed(ConnectorError, PermissionError):
    """A path that would leave its source (absolute, ``..``, backslash, drive letter, NUL or an escaping link)."""

    def __init__(self, message, code="invalid_path"):
        ConnectorError.__init__(self, message, code)


def check_path(path):
    """Normalize a relative POSIX path (``"."`` -> ``""``); :class:`PathNotAllowed` for anything else."""
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise PathNotAllowed(f"Invalid relative path {path!r}")
    posix = PurePosixPath(path)
    if posix.is_absolute() or re.match(r"^[A-Za-z]:", path) or ".." in posix.parts:
        raise PathNotAllowed(f"Path {path!r} must stay inside the binding")
    text = str(posix)
    return "" if text == "." else text


def _matches(path, prefix, directory):
    """``list`` selection: under ``directory`` (``prefix`` names a directory), else a longer name with that prefix."""
    if directory:
        return not prefix or path.startswith(prefix + "/")
    return path.startswith(prefix) and path != prefix


# ---------------------------------------------------------------------------
# Content hashes of local files


class HashMemo:
    """sha256 of local files memoized by (real path, size, mtime_ns, inode), optionally persisted in SQLite.

    The in-memory part keeps at most ``max_entries`` hashes (oldest dropped first).
    """

    def __init__(self, path=None, *, max_entries=65536):
        self.path = Path(path) if path is not None else None
        self.max_entries = max_entries
        self._memory = {}
        self._lock = threading.Lock()
        self._ready = False

    @staticmethod
    def _key(path):
        info = Path(path).stat()
        return (str(path), info.st_size, info.st_mtime_ns, getattr(info, "st_ino", 0))

    def known(self, path):
        """The memoized sha256 of ``path`` in its current state, or ``None`` (never reads the file)."""
        try:
            key = self._key(path)
        except OSError:
            return None
        with self._lock:
            if key in self._memory:
                return self._memory[key]
        return self._load(key)

    def sha256(self, path):
        path = Path(path)
        key = self._key(path)
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
            if len(self._memory) >= self.max_entries:
                self._memory.pop(next(iter(self._memory)))
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


_PROCESS_MEMO = HashMemo(max_entries=4096)


# ---------------------------------------------------------------------------
# Local directories


class LocalFiles:
    """A local directory as a :class:`~suan.connectors.api.FileSource` (``binding`` names it in messages)."""

    path_error = PathNotAllowed

    def __init__(self, root, *, binding=None, hash_memo=None):
        self.binding = binding
        root = Path(root).expanduser()
        if not root.is_dir():
            raise MissingFile(f"Binding {binding + ' ' if binding else ''}directory not found: {root}")
        self.root = root.resolve()
        self._memo = hash_memo if hash_memo is not None else _PROCESS_MEMO

    def __repr__(self):
        return f"{type(self).__name__}({str(self.root)!r})"

    def _where(self):
        return f" in binding '{self.binding}'" if self.binding else ""

    def _missing(self, path):
        return MissingFile(f"File not found: {path}{self._where()}")

    def _inside(self, target):
        return target == self.root or self.root in target.parents

    def _resolve(self, path):
        """The real path of a checked relative path (``""``/``"."`` = the root); refuses escaping links."""
        try:
            relative = check_path(path) if path not in ("", "./") else ""
        except PathNotAllowed as exc:
            raise self.path_error(str(exc)) from None
        if not relative:
            return self.root
        try:
            target = (self.root / relative).resolve()
        except (OSError, RuntimeError):  # a symbolic link loop
            raise self._missing(path) from None
        if not self._inside(target):
            raise self.path_error(f"Path {path!r} leaves the binding directory (symbolic link)")
        return target

    def exists(self, path):
        try:
            return self._resolve(path).is_file()
        except ConnectorError:
            return False

    def stat(self, path):
        target = self._resolve(path)
        try:
            info = target.stat()
        except OSError:
            raise self._missing(path) from None
        if not _stat.S_ISREG(info.st_mode):
            raise MissingFile(f"Not a regular file: {path}{self._where()}")
        return FileInfo(check_path(path), info.st_size, info.st_mtime)

    def list(self, prefix=""):
        """Regular files under ``prefix`` (see the module docstring), sorted by path."""
        prefix = prefix or ""
        wanted = "" if prefix in (".", "./") else prefix
        if wanted:
            try:
                wanted = check_path(wanted)
            except PathNotAllowed as exc:
                raise self.path_error(str(exc)) from None
        target = self._resolve(wanted) if wanted else self.root
        directory = not wanted or prefix.endswith("/") or target.is_dir()
        walk_from = wanted if directory else wanted.rpartition("/")[0]
        base = self.root / walk_from if walk_from else self.root
        if walk_from:
            self._resolve(walk_from)  # refuses a directory link that leaves the binding
        if not base.is_dir():
            return []
        found = []
        for current, dirs, files in os.walk(base):  # linked subdirectories are not descended
            dirs.sort()
            current = Path(current)
            for name in files:
                full = current / name
                relative = (PurePosixPath(walk_from) / full.relative_to(base).as_posix()).as_posix() \
                    if walk_from else full.relative_to(base).as_posix()
                if not _matches(relative, wanted, directory):
                    continue
                try:
                    if not self._inside(full.resolve()):
                        continue  # a link that leaves the binding
                    info = full.stat()
                except (OSError, RuntimeError):  # broken links and link loops
                    continue
                if _stat.S_ISREG(info.st_mode):
                    found.append(FileInfo(relative, info.st_size, info.st_mtime))
        return sorted(found, key=lambda item: item.path)

    def open(self, path):
        target = self._resolve(path)
        if not target.is_file():
            raise self._missing(path)
        try:
            return open(target, "rb")
        except FileNotFoundError:
            raise self._missing(path) from None

    def local_path(self, path):
        """The confined local path (``""``/``"."`` = the directory itself), or ``None`` if it does not exist."""
        target = self._resolve(path)
        return target if target.exists() else None

    def sha256(self, path):
        target = self._resolve(path)
        if not target.is_file():
            raise self._missing(path)
        try:
            return self._memo.sha256(target)
        except FileNotFoundError:
            raise self._missing(path) from None

    def known_sha256(self, path):
        """The memoized sha256 when already computed, else ``None`` (never reads the file)."""
        try:
            return self._memo.known(self._resolve(path))
        except (ConnectorError, OSError):
            return None


# ---------------------------------------------------------------------------
# STK Runtime tasks


class RuntimeFiles:
    """The published files of a Runtime task, read through ``suan.runtime.client.RuntimeClient``.

    ``client`` needs ``artifacts(task_id)`` (``[{"path", "size", "sha256", ...}]``)
    and ``download(task_id, path, destination)`` (resumable, verifies size and
    sha256). The listing is cached; call :meth:`refresh` to re-read it. Listed
    paths that are not plain relative paths are ignored.
    """

    path_error = PathNotAllowed
    objects_dir = "objects"  # downloads go to <cache_dir>/<objects_dir>/<aa>/<sha256><suffix>
    _locks = {}
    _locks_guard = threading.Lock()
    # Downloads verified by this process: path -> (size, mtime_ns). A new source (e.g. per request) must not
    # re-hash an existing (up to 1 GiB) copy every time; a copy changed since is downloaded again.
    _verified = {}

    def __init__(self, client, task_id, cache_dir, *, max_bytes=MAX_DOWNLOAD_BYTES, binding=None):
        self.client = client
        self.task_id = task_id
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.max_bytes = max_bytes
        self.binding = binding
        self._items = None
        self._lock = threading.Lock()

    def __repr__(self):
        return f"{type(self).__name__}(task_id={self.task_id!r})"

    def refresh(self):
        with self._lock:
            self._items = None

    def _listing(self):
        with self._lock:
            if self._items is None:
                items = {}
                for item in self.client.artifacts(self.task_id) or ():
                    try:
                        items[check_path(item["path"])] = item
                    except (PathNotAllowed, KeyError, TypeError):
                        continue
                self._items = items
            return self._items

    def _check(self, path):
        try:
            return check_path(path)
        except PathNotAllowed as exc:
            raise self.path_error(str(exc)) from None

    def _item(self, path):
        item = self._listing().get(self._check(path))
        if item is None:
            raise MissingFile(f"Task {self.task_id} has no published file {path!r} (files are listed once the task "
                              "has finished)")
        return item

    def _too_large(self, message):
        return ConnectorError(message, "budget_exceeded")

    def exists(self, path):
        try:
            self._item(path)
            return True
        except ConnectorError:
            return False

    def stat(self, path):
        item = self._item(path)
        return FileInfo(check_path(item["path"]), int(item["size"]), None)

    def list(self, prefix=""):
        """Listed files under ``prefix`` (see the module docstring), sorted by path."""
        prefix = prefix or ""
        wanted = "" if prefix in (".", "./") else (self._check(prefix) if prefix else "")
        items = self._listing()
        directory = not wanted or prefix.endswith("/") or any(p.startswith(wanted + "/") for p in items)
        return [FileInfo(path, int(item["size"]), None) for path, item in sorted(items.items())
                if _matches(path, wanted, directory)]

    def sha256(self, path):
        return self._item(path)["sha256"]

    def known_sha256(self, path):
        try:
            return self._item(path)["sha256"]
        except ConnectorError:
            return None

    def local_path(self, path):
        """``None``: remote files are not on this host until :meth:`fetch` downloads them."""
        return None

    def fetch(self, path):
        """Download (once, sha256-verified) into the content-addressed cache and return the local copy."""
        item = self._item(path)
        size, digest = int(item["size"]), str(item.get("sha256") or "")
        if not _SHA_RE.match(digest):
            raise ConnectorError(f"The Runtime listed no sha256 for {path}", "invalid_data")
        if self.max_bytes is not None and size > self.max_bytes:
            raise self._too_large(f"{path!r} is {size} bytes; the per-file download limit is {self.max_bytes} bytes "
                                  "(first-release regular field limit is 1 GiB)")
        suffix = PurePosixPath(item["path"]).suffix
        folder = self.cache_dir / self.objects_dir if self.objects_dir else self.cache_dir
        target = folder / digest[:2] / (digest + (suffix if _SUFFIX_RE.match(suffix) else ""))
        with self._target_lock(target):
            try:
                info = target.stat()
                if self._verified.get(str(target)) == (size, info.st_mtime_ns) and info.st_size == size:
                    return target
            except FileNotFoundError:
                pass
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.client.download(self.task_id, item["path"], target)  # resumable; verifies size and sha256
            if not target.is_file() or target.stat().st_size != size:
                raise MissingFile(f"Download of {path!r} from task {self.task_id} failed")
            self._verified[str(target)] = (size, target.stat().st_mtime_ns)
        return target

    def open(self, path):
        return open(self.fetch(path), "rb")

    @classmethod
    def _target_lock(cls, target):
        with cls._locks_guard:
            return cls._locks.setdefault(str(target), threading.Lock())


def materialize(source, path, cache_dir=None):
    """A local filesystem path for ``path`` of any file source (zero copy when local).

    Sources with ``fetch`` (e.g. :class:`RuntimeFiles`) use their cache; other
    sources are copied once into ``cache_dir`` (default: a temporary directory),
    named by sha256.
    """
    local = source.local_path(path)
    if local is not None:
        if not Path(local).is_file():
            raise MissingFile(f"File not found: {path}")
        return Path(local)
    if hasattr(source, "fetch"):
        return Path(source.fetch(path))
    digest = source.sha256(path)
    base = Path(cache_dir) if cache_dir is not None else Path(tempfile.gettempdir()) / "stk-files"
    target = base / "objects" / digest[:2] / (digest + PurePosixPath(path).suffix)
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + f".{os.getpid()}.part")
        with source.open(path) as stream, open(temporary, "wb") as out:
            shutil.copyfileobj(stream, out, 1 << 20)
        os.replace(temporary, target)
    return target
