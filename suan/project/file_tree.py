"""Bounded, metadata-only views of one explicitly opened project's directories.

This is a live directory view, separate from the ordinary-table file index. No file
contents are opened, links are never followed, and browsing never registers a file.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat

from .store import ProjectError

MAX_ENTRIES = 4096
MAX_PAGE = 200
MAX_REGISTRATIONS = 200
_INTERNAL = {".stk", ".git", "backups", "__pycache__"}


def _private(name):
    value = name.casefold()
    return value.startswith(".") or value in _INTERNAL or value.startswith("project.sqlite3")


def _parts(path):
    if not isinstance(path, str) or len(path) > 4096 or "\\" in path or any(ord(c) < 32 for c in path):
        raise ProjectError("Tree paths must be relative POSIX paths without control characters")
    if path == "":
        return ()
    parts = path.split("/")
    if len(parts) > 32 or any(not part or part in {".", ".."} or ":" in part or _private(part) for part in parts):
        raise ProjectError("Tree paths cannot escape the project or enter hidden/internal locations")
    return tuple(parts)


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) &
                                             getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mode


@contextmanager
def _directory(root, parts):
    """Pin POSIX directory descriptors; check every component on other platforms."""
    target = root
    chain = [(root, _identity(root.lstat()))]
    for part in parts:
        target /= part
        info = target.lstat()
        if _link(info) or not stat.S_ISDIR(info.st_mode):
            raise ProjectError("Tree directories must be real directories without links or reparse points")
        chain.append((target, _identity(info)))
    if _link(root.lstat()):
        raise ProjectError("The project directory cannot be a symbolic link")
    descriptors = []
    try:
        if os.scandir in os.supports_fd and os.open in os.supports_dir_fd:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            descriptor = os.open(root, flags)
            descriptors.append(descriptor)
            for part in parts:
                descriptor = os.open(part, flags, dir_fd=descriptor)
                descriptors.append(descriptor)
            yield descriptor
        else:
            yield target
        if any(_identity(path.lstat()) != identity or _link(path.lstat()) for path, identity in chain):
            raise ProjectError("Project directory changed while browsing; refresh the tree")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _records(index, snapshot):
    table = index._table(snapshot)
    index._fields(table)
    return [{"id": row["id"], **index._values(row)} for row in table["records"]] if table else []


def children(index, path="", *, expected_revision, offset=0, limit=MAX_PAGE):
    """List one directory, with explicit caps and separate last-observed registrations."""
    parts = _parts(path)
    if type(offset) is not int or not 0 <= offset <= MAX_ENTRIES:
        raise ProjectError("Tree offset must be between 0 and 4096")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise ProjectError("Tree page size must be between 1 and 200")
    snapshot = index._read(expected_revision)
    records = _records(index, snapshot)
    registered = {}
    for row in records:
        if row["location"] != "project" or not isinstance(row["path"], str):
            continue
        try:
            location = _parts(row["path"])
        except ProjectError:
            continue
        if location[:-1] == parts and location:
            registered.setdefault(location[-1], []).append(row["id"])
    entries, seen, truncated = [], set(), False
    with _directory(index.store.directory, parts) as directory:
        with os.scandir(directory) as listing:
            for number, entry in enumerate(listing):
                if number == MAX_ENTRIES:
                    truncated = True
                    break
                name = entry.name
                if _private(name):
                    continue
                relative = "/".join((*parts, name))
                try:
                    _parts(relative)
                except ProjectError:
                    truncated = True
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                    kind = "link" if _link(info) else "directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "other"
                    state, size = "present", info.st_size if kind == "file" else None
                except FileNotFoundError:
                    kind, state, size = "other", "missing", None
                except OSError:
                    kind, state, size = "other", "unavailable", None
                ids = registered.get(name, [])
                entries.append({"name": name, "path": relative, "kind": kind, "state": state,
                                "size": size, "registered": bool(ids), "record_id": ids[0] if ids else None})
                seen.add(name)
    # Missing indexed children are observable only after a complete directory listing.
    if not truncated:
        for name, ids in registered.items():
            if name not in seen:
                if len(entries) >= MAX_ENTRIES:
                    truncated = True
                    break
                entries.append({"name": name, "path": "/".join((*parts, name)), "kind": "file", "state": "missing",
                                "size": None, "registered": True, "record_id": ids[0]})
    entries.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold(), item["name"]))
    page = entries[offset:offset + limit]
    # The index section is deliberately labelled last-observed: no external path is probed.
    registrations = []
    if not parts:
        for row in records[:MAX_REGISTRATIONS]:
            summary = {"id": row["id"], "display_truncated": False}
            for key in ("name", "path", "location", "state", "kind"):
                value = row[key] if isinstance(row[key], str) else None
                cap = 4096 if key == "path" else 512
                if value is not None and len(value) > cap:
                    value = value[:cap]
                    summary["display_truncated"] = True
                summary[key] = value
            registrations.append(summary)
    return {"revision": snapshot["project"]["revision"], "directory": path, "entries": page,
            "next_offset": offset + len(page) if offset + len(page) < len(entries) else None,
            "truncated": truncated, "registrations": registrations,
            "registrations_truncated": not parts and len(records) > MAX_REGISTRATIONS}


def resolve_path(index, path, *, expected_revision):
    """Recheck a public project path for an explicit open; no contents or execution."""
    parts = _parts(path)
    snapshot = index._read(expected_revision)
    if not parts:
        with _directory(index.store.directory, ()):
            pass
        kind = "directory"
    else:
        with _directory(index.store.directory, parts[:-1]) as directory:
            info = (os.stat(parts[-1], dir_fd=directory, follow_symlinks=False) if isinstance(directory, int)
                    else (directory / parts[-1]).lstat())
            if _link(info) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ProjectError("Only regular files and real directories can be opened from the tree")
            kind = "directory" if stat.S_ISDIR(info.st_mode) else "file"
    return {"revision": snapshot["project"]["revision"], "path": str(index.store.directory / Path(*parts)), "kind": kind}
