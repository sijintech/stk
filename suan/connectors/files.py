"""File sources (``suan.connectors.api.FileSource``): a local directory and a Runtime task's files.

Paths are POSIX, relative to the source root, never absolute and never
``..``; a path whose real location leaves the root (a symbolic link pointing
outside) is refused, so a graph binding can read nothing else.

* :class:`LocalFiles` -- a directory on this host (zero-copy ``local_path``);
  sha256 values are cached by (path, size, mtime, inode) for the process.
* :class:`RuntimeFiles` -- the published files of a Runtime task, listed with
  their sizes and sha256 by the Runtime API. Files are downloaded on first use
  into a content-addressed cache ``<cache_dir>/objects/<aa>/<sha256><suffix>``
  and verified by ``RuntimeClient.download``; later reads reuse it. The Runtime
  publishes a task's files when it finishes, so running tasks list nothing yet.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat as _stat
import tempfile
import threading

from .api import ConnectorError, FileInfo

__all__ = ["LocalFiles", "RuntimeFiles", "check_path", "materialize"]

_SHA_CACHE = {}
_SHA_LOCK = threading.Lock()
_SHA_CACHE_SIZE = 4096


def check_path(path):
    """Normalize a relative POSIX path; ``ConnectorError(code="invalid_path")`` for anything else."""
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ConnectorError(f"Invalid relative path {path!r}", "invalid_path")
    posix = PurePosixPath(path)
    if posix.is_absolute() or re.match(r"^[A-Za-z]:", path) or ".." in posix.parts:
        raise ConnectorError(f"Path {path!r} must stay inside the binding", "invalid_path")
    text = str(posix)
    return "" if text == "." else text


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class LocalFiles:
    """A local directory as a :class:`~suan.connectors.api.FileSource`."""

    def __init__(self, root):
        root = Path(root)
        if not root.is_dir():
            raise ConnectorError(f"Binding directory not found: {root}", "not_found")
        self.root = root.resolve()

    def __repr__(self):
        return f"LocalFiles({str(self.root)!r})"

    def _resolve(self, path):
        relative = check_path(path)
        target = (self.root / relative).resolve() if relative else self.root
        if target != self.root and self.root not in target.parents:
            raise ConnectorError(f"Path {path!r} leaves the binding directory", "invalid_path")
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
        except FileNotFoundError:
            raise ConnectorError(f"File not found: {path}", "missing_file") from None
        if not _stat.S_ISREG(info.st_mode):
            raise ConnectorError(f"Not a regular file: {path}", "missing_file")
        return FileInfo(check_path(path), info.st_size, info.st_mtime)

    def list(self, prefix=""):
        """Regular files under ``prefix`` (a path prefix such as ``"case16/"`` or ``"Polar."``), sorted."""
        prefix = prefix or ""
        directory = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
        try:
            base = self._resolve(directory) if directory else self.root
        except ConnectorError:
            return []
        if not base.is_dir():
            return []
        found = []
        for current, dirs, files in os.walk(base):
            current = Path(current)
            dirs[:] = sorted(d for d in dirs if not (current / d).is_symlink())
            for name in files:
                full = current / name
                relative = full.relative_to(self.root).as_posix()
                if not relative.startswith(prefix):
                    continue
                try:
                    real = full.resolve()
                    if self.root not in real.parents:
                        continue
                    info = full.stat()
                except OSError:
                    continue
                if _stat.S_ISREG(info.st_mode):
                    found.append(FileInfo(relative, info.st_size, info.st_mtime))
        return sorted(found, key=lambda item: item.path)

    def open(self, path):
        target = self._resolve(path)
        try:
            return open(target, "rb")
        except FileNotFoundError:
            raise ConnectorError(f"File not found: {path}", "missing_file") from None

    def local_path(self, path):
        target = self._resolve(path)
        return target if target.exists() else None

    def sha256(self, path):
        target = self._resolve(path)
        try:
            info = target.stat()
        except FileNotFoundError:
            raise ConnectorError(f"File not found: {path}", "missing_file") from None
        key = (str(target), info.st_size, info.st_mtime_ns, info.st_ino)
        with _SHA_LOCK:
            cached = _SHA_CACHE.get(key)
        if cached is None:
            cached = _sha256_file(target)
            with _SHA_LOCK:
                if len(_SHA_CACHE) >= _SHA_CACHE_SIZE:
                    _SHA_CACHE.pop(next(iter(_SHA_CACHE)))
                _SHA_CACHE[key] = cached
        return cached

    def known_sha256(self, path):
        """The cached sha256 when already computed, else ``None`` (never reads the file)."""
        try:
            target = self._resolve(path)
            info = target.stat()
        except (ConnectorError, OSError):
            return None
        with _SHA_LOCK:
            return _SHA_CACHE.get((str(target), info.st_size, info.st_mtime_ns, info.st_ino))


class RuntimeFiles:
    """The published files of a Runtime task, read through ``suan.runtime.client.RuntimeClient``.

    ``client`` needs ``artifacts(task_id)`` (``[{"path", "size", "sha256", ...}]``)
    and ``download(task_id, path, destination)``. The listing is cached; call
    :meth:`refresh` to re-read it.
    """

    def __init__(self, client, task_id, cache_dir):
        self.client = client
        self.task_id = task_id
        self.cache_dir = Path(cache_dir)
        self._items = None
        self._lock = threading.Lock()

    def __repr__(self):
        return f"RuntimeFiles(task_id={self.task_id!r})"

    def refresh(self):
        with self._lock:
            self._items = None

    def _listing(self):
        with self._lock:
            if self._items is None:
                items = self.client.artifacts(self.task_id)
                self._items = {item["path"]: item for item in items}
            return self._items

    def _item(self, path):
        relative = check_path(path)
        item = self._listing().get(relative)
        if item is None:
            raise ConnectorError(f"File not found in task {self.task_id}: {path}", "missing_file")
        return item

    def exists(self, path):
        try:
            self._item(path)
            return True
        except ConnectorError:
            return False

    def stat(self, path):
        item = self._item(path)
        return FileInfo(item["path"], int(item["size"]), None)

    def list(self, prefix=""):
        prefix = prefix or ""
        return [FileInfo(path, int(item["size"]), None) for path, item in sorted(self._listing().items())
                if path.startswith(prefix)]

    def sha256(self, path):
        return self._item(path)["sha256"]

    def known_sha256(self, path):
        try:
            return self._item(path)["sha256"]
        except ConnectorError:
            return None

    def local_path(self, path):
        return None

    def fetch(self, path):
        """Download (once) into the content-addressed cache and return the local copy."""
        item = self._item(path)
        digest = item["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            raise ConnectorError(f"The Runtime listed no sha256 for {path}", "invalid_data")
        target = self.cache_dir / "objects" / digest[:2] / (digest + PurePosixPath(item["path"]).suffix)
        if target.is_file() and target.stat().st_size == int(item["size"]):
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        self.client.download(self.task_id, item["path"], target)
        return target

    def open(self, path):
        return open(self.fetch(path), "rb")


def materialize(source, path, cache_dir=None):
    """A local filesystem path for ``path`` of any file source (zero copy when local).

    Sources with ``fetch`` (e.g. :class:`RuntimeFiles`) use their cache; other
    sources are copied once into ``cache_dir`` (default: a temporary directory),
    named by sha256.
    """
    local = source.local_path(path)
    if local is not None:
        if not Path(local).is_file():
            raise ConnectorError(f"File not found: {path}", "missing_file")
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
