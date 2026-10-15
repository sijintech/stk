"""Explicit, bounded local Python-file editing; none of these operations executes code.

The SHA token implements optimistic concurrency, including a final reread before replacement.
Atomic replacement prevents partial saves; it is not a filesystem lock against unrelated editors.
No source text is written to a bridge journal or included in an error message.
"""
from hashlib import sha256
import os
from pathlib import Path
import stat
import tempfile
import threading

from .protocol import BridgeError

FILE_LIMIT = 262144
_SAVE_LOCK = threading.RLock()


def _path(value):
    if not isinstance(value, str) or "\x00" in value:
        raise BridgeError("invalid_params", "Python file path must be an absolute .py path")
    path = Path(value)
    if not path.is_absolute() or path.suffix.lower() != ".py":
        raise BridgeError("invalid_params", "Python file path must be an absolute .py path")
    # Reject links in every component, rather than unexpectedly writing through a selected link.
    try:
        for part in (path, *path.parents):
            try:
                info = part.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) &
                                             getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise BridgeError("invalid_params", "Python file paths must not contain symbolic links or reparse points")
        if not path.parent.is_dir():
            raise BridgeError("not_found", "Python file parent directory does not exist")
    except OSError:
        raise BridgeError("unavailable", "Cannot access the selected Python file path") from None
    return path


def _read(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise BridgeError("invalid_params", "Python source must be a regular file")
            raw = stream.read(FILE_LIMIT + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > FILE_LIMIT:
            raise BridgeError("invalid_params", "Python source exceeds 256 KiB")
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise BridgeError("conflict", "Python file changed while it was being read; reload it")
        source = raw.decode("utf-8-sig")
        if "\x00" in source:
            raise BridgeError("invalid_params", "Python source must not contain NUL characters")
        return {"path": str(path), "source": source, "version": sha256(raw).hexdigest(), "size": len(raw)}, before
    except FileNotFoundError:
        raise BridgeError("not_found", "Python file does not exist") from None
    except UnicodeError:
        raise BridgeError("invalid_params", "Python source must be valid UTF-8") from None
    except OSError:
        raise BridgeError("unavailable", "Cannot read the selected Python file") from None


def read_file(params):
    return _read(_path(params["path"]))[0]


def write_file(params):
    path, source, expected = _path(params["path"]), params["source"], params["expected_version"]
    try:
        raw = source.encode("utf-8")
    except UnicodeError:
        raise BridgeError("invalid_params", "Python source must be valid UTF-8") from None
    if len(raw) > FILE_LIMIT or "\x00" in source:
        raise BridgeError("invalid_params", "Python source must be UTF-8 without NUL and at most 256 KiB")
    temporary = None
    with _SAVE_LOCK:
        try:
            current = None
            if path.exists():
                current, info = _read(path)
                if expected is None or current["version"] != expected:
                    raise BridgeError("conflict", "Python file changed externally; reload or save to a new path")
            elif expected is not None:
                raise BridgeError("conflict", "Python file was removed externally; save to a new path")
            with tempfile.NamedTemporaryFile(prefix=".stk-python-", suffix=".tmp", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                if current is not None:
                    os.chmod(temporary, stat.S_IMODE(info.st_mode))
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _path(str(path))  # Recheck link boundaries after writing the temporary file.
            if current is not None:
                latest, latest_info = _read(path)
                if latest["version"] != expected or (latest_info.st_dev, latest_info.st_ino) != (info.st_dev, info.st_ino):
                    raise BridgeError("conflict", "Python file changed externally; the draft was not saved")
                os.replace(temporary, path)
            else:
                # A link is an atomic create-if-absent; never overwrite a file created meanwhile.
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    raise BridgeError("conflict", "Python destination now exists; choose a new path") from None
            return {"path": str(path), "version": sha256(raw).hexdigest(), "size": len(raw)}
        except BridgeError:
            raise
        except OSError:
            raise BridgeError("unavailable", "Cannot save the selected Python file") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
