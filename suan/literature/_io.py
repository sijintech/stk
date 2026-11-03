"""Bounded ordinary-file reads for explicit local literature actions."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat

MAX_PDF_BYTES = 32 * 1024 * 1024


class LiteratureError(ValueError):
    """Path-free failure suitable for a future local adapter."""
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def fail(code="invalid_data", message="Invalid literature data"):
    raise LiteratureError(code, message)


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def ordinary(path):
    info = Path(path).lstat()
    if linked(info) or not stat.S_ISREG(info.st_mode):
        fail("invalid_file", "Literature inputs must be ordinary files")
    return info


def directory(path, *, create=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        fail("invalid_path", "An absolute ordinary local path is required")
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
        if linked(info) or not stat.S_ISDIR(info.st_mode):
            fail("invalid_path", "Literature directories must be ordinary directories")
    if create and os.name != "nt":
        path.chmod(0o700)
    return path


@contextmanager
def opened(path):
    path = Path(path)
    directory(path.parent)
    before = ordinary(path)
    if not 5 <= before.st_size <= MAX_PDF_BYTES:
        fail("file_budget", "PDF input exceeds the supported byte budget")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        initial = os.fstat(stream.fileno())
        # Windows can report change time through fstat and creation time
        # through path stat. Compare ctime only within the same API family.
        if not stat.S_ISREG(initial.st_mode) or stamp(initial)[:-1] != stamp(before)[:-1]:
            fail("source_changed", "Literature input changed during reading")
        yield stream, initial
        directory(path.parent)
        after, named = os.fstat(stream.fileno()), ordinary(path)
        if (stamp(initial) != stamp(after) or stamp(before) != stamp(named)
                or stamp(after)[:-1] != stamp(named)[:-1]):
            fail("source_changed", "Literature input changed during reading")


def inspect_pdf(path):
    """Read every byte and return a review identity; no library or parser is opened."""
    try:
        with opened(path) as (stream, initial):
            h, count = hashlib.sha256(), 0
            while block := stream.read(1024 * 1024):
                if count == 0 and not block.startswith(b"%PDF-"):
                    fail("invalid_pdf", "Input has no supported PDF header")
                count += len(block)
                if count > MAX_PDF_BYTES:
                    fail("file_budget", "PDF input exceeds the supported byte budget")
                h.update(block)
            if count != initial.st_size:
                fail("source_changed", "Literature input changed during reading")
            return {"sha256": h.hexdigest(), "bytes": count}
    except LiteratureError:
        raise
    except OSError:
        fail("invalid_file", "Literature input is unavailable")
