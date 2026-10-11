"""Project helpers shared by the engine workflows (MuFerro, LAMMPS): bounded input copies, frozen snapshots,
owned tables and output folders. All project changes use the public revisioned facade."""
import hashlib
import json
import os
from pathlib import Path
import stat


def _copy_input(source, target, remaining):
    """Bound source reads and reject replacement with a link, FIFO, or changing file."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(source, flags), "rb") as inp, target.open("xb") as out:
        before = os.fstat(inp.fileno())
        if not stat.S_ISREG(before.st_mode) or source.is_symlink() or before.st_size > remaining:
            raise ValueError("Input is not a regular file within the input budget")
        count = 0
        while True:
            block = inp.read(min(1024 * 1024, remaining - count + 1))
            if not block:
                break
            count += len(block)
            if count > remaining:
                raise ValueError("Case exceeds the 256 MiB input limit")
            out.write(block)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        after = os.fstat(inp.fileno())
        # As in project.snapshots: Windows 3.12 can use change time for fstat and
        # creation time for path stat. Compare ctime only within the same API.
        if (signature(before) != signature(after) or count != after.st_size
                or signature(after)[:4] != signature(source.lstat())[:4]):
            raise ValueError("Case input changed while importing; import a stable case directory")
    return count


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _table(model, table_id, fields, ids, label="MuFerro"):
    table = next((t for t in model["tables"] if t["id"] == table_id), None)
    if table is not None:
        actual = {f["id"]: (f["type"], f.get("unit")) for f in table["fields"]}
        if any(actual.get(ids[key]) != (kind, unit) for key, (_, kind, unit) in fields.items()):
            raise ValueError(f"{label} table fields were removed or changed; restore their types before continuing")
    return table


def _create_table(table_id, name, fields, ids):
    return [{"op": "create_table", "id": table_id, "name": name}] + [
        {"op": "add_field", "id": ids[key], "table_id": table_id, "name": label, "type": kind,
         **({"unit": unit} if unit else {})} for key, (label, kind, unit) in fields.items()]


def _cells(table_id, row_id, values, ids):
    return [{"op": "set_cell", "table_id": table_id, "record_id": row_id,
             "field_id": ids[key], "value": value} for key, value in values.items()]


def _capture(project, paths, expected_hashes, revision):
    indexed = project.files.index(paths, expected_revision=revision)
    captured = project.snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    actual = {f["record_id"]: f["sha256"] for f in captured["snapshot"]["manifest"]["files"]}
    if actual != dict(zip(indexed["record_ids"], expected_hashes)):
        raise ValueError("Input files changed between generation and freezing; no run was prepared")
    return indexed, captured


def _revision(project, expected):
    model = project.snapshot()
    if type(expected) is not int or model["project"]["revision"] != expected:
        raise ValueError("Project changed; refresh it and inspect the current parameters before continuing")
    return model


def _directory(stk, project):
    info = next((p for p in stk.projects.list() if p["handle"] == project.handle), None)
    if info is None:
        raise ValueError("This project is no longer open")
    return Path(info["directory"])


def _folder(root, *parts):
    """Owned project output directories cannot redirect writes outside the project."""
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Workflow directories must not be symbolic links")
        path.mkdir(exist_ok=True)
    return path
