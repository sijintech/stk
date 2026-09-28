"""A file index built from ordinary project tables, fields and records.

Registration/refresh observes metadata only. It never copies, removes, executes or
reads file contents. Relative locations remain portable; external locations retain
the originating path syntax. All writes go through the shared revisioned edit API.
"""
from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
from uuid import NAMESPACE_URL, uuid4, uuid5

from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat


TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:project:files:1"))
FIELDS = {
    "name": ("Name", "text", None),
    "path": ("Path", "text", None),
    "location": ("Location", "text", None),
    "kind": ("Kind", "text", None),
    "size": ("Size", "integer", "B"),
    "modified": ("Modified (UTC)", "text", None),
    "state": ("State", "text", None),
    "checked": ("Checked (UTC)", "text", None),
}
FIELD_IDS = {key: str(uuid5(NAMESPACE_URL, "urn:stk:project:files:1:" + key)) for key in FIELDS}
MAX_FILES = 100
PLATFORM = "windows" if os.name == "nt" else "posix"
_UNSET = object()


def descriptor(snapshot):
    """Recognize the built-in view by IDs and types, irrespective of user-facing names."""
    table = next((item for item in snapshot["tables"] if item["id"] == TABLE_ID), None)
    if table is None:
        return None
    fields = {item["id"]: item for item in table["fields"]}
    compatible = all(FIELD_IDS[key] in fields and fields[FIELD_IDS[key]]["type"] == kind
                     and fields[FIELD_IDS[key]].get("unit") == unit for key, (_, kind, unit) in FIELDS.items())
    return {"table_id": TABLE_ID, "fields": FIELD_IDS.copy(), "compatible": compatible}


def _kind(path):
    extension = Path(path).suffix.lower()
    groups = {
        "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".svg", ".bmp"},
        "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
        "document": {".md", ".markdown", ".pdf", ".html", ".htm", ".tex", ".rst"},
        "code": {".py", ".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".f", ".f90", ".f95", ".sh", ".ps1", ".bat", ".js", ".ts"},
        "data": {".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".npy", ".npz", ".vtk", ".vti", ".vtu", ".dat", ".h5", ".hdf5"},
    }
    return next((kind for kind, extensions in groups.items() if extension in extensions), "file")


def _location(root, value):
    if not isinstance(value, str) or not value.strip() or "\0" in value or len(value) > 32768:
        raise ProjectError("A file path must be a nonempty string without NUL, at most 32768 characters")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate = candidate.resolve()
    except (OSError, RuntimeError) as exc:
        raise ProjectError(f"Cannot resolve file path: {exc}") from None
    try:
        return "project", candidate.relative_to(root).as_posix()
    except ValueError:
        return "external:" + PLATFORM, str(candidate)


def _resolve(root, location, path):
    if not isinstance(path, str) or not path or "\0" in path or len(path) > 32768:
        raise ProjectError("File index path is invalid")
    if location == "project":
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in path or path in {".", ""}:
            raise ProjectError("Project file paths must be relative POSIX paths without '..'")
        candidate = (root / Path(*relative.parts)).resolve()
        if not candidate.is_relative_to(root):
            raise ProjectError("Project file path now resolves outside the project; register the external file explicitly")
    elif location in {"external:posix", "external:windows"}:
        if location != "external:" + PLATFORM:
            raise ProjectError("External file path belongs to another platform; register its current local location")
        syntax = PureWindowsPath(path) if PLATFORM == "windows" else PurePosixPath(path)
        if not syntax.is_absolute():
            raise ProjectError("External file paths must be absolute")
        candidate = Path(path).resolve()
    else:
        raise ProjectError("File index location must be project, external:posix or external:windows")
    name = candidate.name.casefold() if PLATFORM == "windows" else candidate.name
    if candidate.parent == root and name in {"project.sqlite3", "project.sqlite3-wal", "project.sqlite3-shm", "project.sqlite3-journal"}:
        raise ProjectError("The live project database and its transaction files are not indexable resources")
    return candidate


def _observe(root, location, path):
    checked = datetime.now(timezone.utc).isoformat()
    values = {"kind": _kind(path), "size": None, "modified": None, "state": "missing", "checked": checked}
    try:
        target = _resolve(root, location, path)
        info = target.stat()
        if not stat.S_ISREG(info.st_mode):
            values["state"] = "not_file"
        else:
            values.update(state="present", size=info.st_size,
                          modified=datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat())
    except FileNotFoundError:
        pass
    except ProjectError:
        values["state"] = "invalid_location"
    except (OSError, RuntimeError, OverflowError, ValueError):
        values["state"] = "unavailable"
    return values


class FileIndex:
    def __init__(self, store):
        self.store = store

    def _read(self, expected_revision=_UNSET):
        snapshot = self.store.snapshot()
        if expected_revision is not _UNSET:
            if type(expected_revision) is not int or expected_revision < 0:
                raise ProjectError("expected_revision must be a nonnegative integer")
            if snapshot["project"]["revision"] != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {snapshot['project']['revision']}")
        if snapshot["format_version"] < 3:
            raise UnsupportedProjectFormat("Upgrade this project to format 3 before using the file index")
        return snapshot

    @staticmethod
    def _table(snapshot):
        return next((table for table in snapshot["tables"] if table["id"] == TABLE_ID), None)

    @staticmethod
    def _fields(table):
        if table is None:
            return
        fields = {field["id"]: field for field in table["fields"]}
        for key, (_, kind, unit) in FIELDS.items():
            field = fields.get(FIELD_IDS[key])
            if field is None or field["type"] != kind or field.get("unit") != unit:
                raise ProjectError("The file index has missing or incompatible fields; undo the structural edit or restore a backup")

    @staticmethod
    def _values(row):
        return {name: row["values"].get(identity) for name, identity in FIELD_IDS.items()}

    @staticmethod
    def _commands(record, values):
        return [{"op": "set_cell", "table_id": TABLE_ID, "record_id": record, "field_id": FIELD_IDS[key], "value": value}
                for key, value in values.items()]

    def list(self):
        snapshot = self._read()
        table = self._table(snapshot)
        self._fields(table)
        return {"revision": snapshot["project"]["revision"], "table_id": TABLE_ID,
                "records": [{"id": row["id"], **self._values(row)} for row in table["records"]] if table else []}

    def index(self, paths, *, expected_revision):
        if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FILES:
            raise ProjectError("Register between 1 and 100 explicit file paths per batch")
        snapshot = self._read(expected_revision)
        table = self._table(snapshot)
        self._fields(table)
        commands, existing = [], {}
        if table is None:
            commands.append({"op": "create_table", "id": TABLE_ID, "name": "Files"})
            for key, (name, kind, unit) in FIELDS.items():
                field = {"op": "add_field", "table_id": TABLE_ID, "id": FIELD_IDS[key], "name": name, "type": kind}
                if unit is not None:
                    field["unit"] = unit
                commands.append(field)
        else:
            for row in table["records"]:
                values = self._values(row)
                location, path = values["location"], values["path"]
                if not isinstance(location, str) or not isinstance(path, str):
                    continue
                key = (location, os.path.normcase(path) if location == "external:windows" or PLATFORM == "windows" else path)
                if key in existing:
                    raise ProjectError("The file index contains duplicate locations; remove or repair the duplicate record")
                existing[key] = row["id"]
        selected = []
        for value in paths:
            location, path = _location(self.store.directory, value)
            target = _resolve(self.store.directory, location, path)
            if target.is_dir():
                raise ProjectError("Register explicit files, not directories; recursive scanning is not enabled")
            key = (location, os.path.normcase(path) if PLATFORM == "windows" else path)
            record = existing.get(key)
            if record in selected:
                continue
            values = _observe(self.store.directory, location, path)
            if record is None:
                record = str(uuid4())
                existing[key] = record
                commands.append({"op": "add_record", "table_id": TABLE_ID, "id": record})
                values.update(name=target.name, path=path, location=location)
            commands.extend(self._commands(record, values))
            selected.append(record)
        result = self.store.apply(commands, expected_revision=expected_revision)
        return {**result, "table_id": TABLE_ID, "record_ids": selected}

    def refresh(self, record_ids, *, expected_revision):
        if not isinstance(record_ids, list) or not 1 <= len(record_ids) <= MAX_FILES or not all(isinstance(key, str) for key in record_ids):
            raise ProjectError("Refresh between 1 and 100 file record IDs per batch")
        snapshot = self._read(expected_revision)
        table = self._table(snapshot)
        self._fields(table)
        rows = {row["id"]: row for row in table["records"]} if table else {}
        selected = list(dict.fromkeys(record_ids))
        if any(key not in rows for key in selected):
            raise ProjectError("File record not found")
        commands = []
        for identity in selected:
            values = self._values(rows[identity])
            # Invalid or unresolved formula paths remain inspectable, with a saved diagnostic state.
            path = values["path"] if isinstance(values["path"], str) else ""
            commands.extend(self._commands(identity, _observe(self.store.directory, values["location"], path)))
        result = self.store.apply(commands, expected_revision=expected_revision)
        return {**result, "table_id": TABLE_ID, "record_ids": selected}

    def resolve(self, record_id, *, expected_revision):
        snapshot = self._read(expected_revision)
        table = self._table(snapshot)
        self._fields(table)
        row = next((row for row in table["records"] if row["id"] == record_id), None) if table else None
        if row is None:
            raise ProjectError("File record not found")
        values = self._values(row)
        target = _resolve(self.store.directory, values["location"], values["path"])
        if not target.is_file():
            raise ProjectError("Indexed file is missing or is not a regular file; refresh its metadata")
        return {"revision": snapshot["project"]["revision"], "record_id": record_id,
                "path": str(target), "kind": _kind(str(target))}
