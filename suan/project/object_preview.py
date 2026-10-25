"""Explicit, bounded attachment reads; metadata resolution remains content-free."""
import base64
import hashlib
import os
from pathlib import Path
import stat

from .file_tree import _directory, _link
from .files import _resolve
from .object_refs import resolve
from .snapshots import _signature
from .store import ProjectError

MAX_BYTES = 1024 * 1024
TEXT_BYTES = 64 * 1024
TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
                           ".toml", ".xml", ".html", ".htm", ".tex", ".rst", ".py", ".log"})


def read_attachment(path):
    """Read from one pinned descriptor, checking size, type and identity before publishing."""
    root = Path(path.anchor)
    with _directory(root, path.parent.parts[1:]) as parent:
        kwargs = {"dir_fd": parent} if isinstance(parent, int) else {}
        target = path.name if kwargs else path
        before_path = os.stat(target, follow_symlinks=False, **kwargs)
        if _link(before_path) or not stat.S_ISREG(before_path.st_mode):
            raise ProjectError("Attachment must be a regular file without links")
        if before_path.st_size > MAX_BYTES:
            raise ProjectError("Attachment preview is limited to 1 MiB")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(target, flags, **kwargs), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or _signature(before)[:4] != _signature(before_path)[:4]:
                raise ProjectError("Attachment changed before preview")
            data = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        after_path = os.stat(target, follow_symlinks=False, **kwargs)
        if (len(data) != before.st_size or len(data) > MAX_BYTES or _signature(before) != _signature(after)
                or _link(after_path) or _signature(after_path)[:4] != _signature(after)[:4]):
            raise ProjectError("Attachment changed while being read")
    return data


def preview(store, db, value):
    resolved = resolve(store, db, value)
    ref, summary = resolved["reference"], resolved["summary"]
    if resolved["state"] != "available":
        raise ProjectError(resolved["reason"])
    if ref["kind"] == "file":
        path = _resolve(store.directory, summary["location"], summary["path"])
    elif ref["kind"] == "snapshot_file":
        path = store.snapshots._object(summary["sha256"])
    else:
        raise ProjectError("Attachment preview requires a file or frozen snapshot file")
    suffix = Path(summary["name"]).suffix.lower()
    if suffix != ".png" and suffix not in TEXT_SUFFIXES:
        raise ProjectError("Preview supports PNG and UTF-8 text attachments")
    try:
        data = read_attachment(path)
    except (OSError, RuntimeError):
        raise ProjectError("Attachment is unavailable or changed; refresh its source") from None
    checksum = hashlib.sha256(data).hexdigest()
    if ref["kind"] == "snapshot_file" and (checksum != summary["sha256"] or len(data) != summary["size"]):
        raise ProjectError("Frozen attachment checksum does not match its manifest")
    if suffix == ".png":
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise ProjectError("Attachment is not a PNG image")
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 4 * 1024 * 1024:
            raise ProjectError("PNG preview is limited to 4096 per axis and 4 megapixels")
        content, truncated, kind = base64.b64encode(data).decode("ascii"), False, "png"
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise ProjectError("Text preview requires valid UTF-8") from None
        if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
            raise ProjectError("Text preview does not accept binary control characters")
        content, truncated, kind = data[:TEXT_BYTES].decode("utf-8", errors="ignore"), len(data) > TEXT_BYTES, "text"
    return {"version": 1, "reference": ref, "label": resolved["label"], "kind": kind,
            "content_sha256": checksum, "size": len(data), "data": content, "truncated": truncated}
