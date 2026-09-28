"""First project-storage slice: typed tables, stable IDs and atomic revisioned edits.

This experimental format is distinct from the Runtime database and graph-v1.
Only bounded scalar expressions are evaluated; persistence never submits work.
Each operation opens its own connection, so callers may use separate threads.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from .evaluation import dependencies, evaluate
from .expressions import MAX_BINDINGS, MAX_EXPRESSION
from .journal import Capture, restore


APPLICATION_ID = 0x53544B50  # STKP
FORMAT_VERSION = 3
DATABASE_NAME = "project.sqlite3"
FIELD_TYPES = {"text", "integer", "number", "boolean", "json"}

_DDL = (
    "CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL)",
    "CREATE TABLE tables (id TEXT PRIMARY KEY, name TEXT NOT NULL)",
    """CREATE TABLE fields (
        id TEXT PRIMARY KEY, table_id TEXT NOT NULL REFERENCES tables(id), name TEXT NOT NULL,
        type TEXT NOT NULL, unit TEXT, UNIQUE(table_id, id))""",
    """CREATE TABLE records (
        id TEXT PRIMARY KEY, table_id TEXT NOT NULL REFERENCES tables(id), UNIQUE(table_id, id))""",
    """CREATE TABLE cells (
        table_id TEXT NOT NULL, record_id TEXT NOT NULL, field_id TEXT NOT NULL, value TEXT NOT NULL,
        PRIMARY KEY(record_id, field_id),
        FOREIGN KEY(table_id, record_id) REFERENCES records(table_id, id),
        FOREIGN KEY(table_id, field_id) REFERENCES fields(table_id, id))""",
    """CREATE TABLE changes (
        revision INTEGER PRIMARY KEY, created_at TEXT NOT NULL, commands TEXT NOT NULL)""",
)

_DDL_V2 = (
    """CREATE TABLE definitions (
        table_id TEXT NOT NULL, record_id TEXT NOT NULL, field_id TEXT NOT NULL, definition TEXT NOT NULL,
        PRIMARY KEY(record_id, field_id),
        FOREIGN KEY(table_id, record_id) REFERENCES records(table_id, id),
        FOREIGN KEY(table_id, field_id) REFERENCES fields(table_id, id))""",
    """CREATE TABLE evaluations (
        record_id TEXT NOT NULL, field_id TEXT NOT NULL, result TEXT NOT NULL,
        PRIMARY KEY(record_id, field_id),
        FOREIGN KEY(record_id, field_id) REFERENCES definitions(record_id, field_id) ON DELETE CASCADE)""",
)

_DDL_V3 = (
    """CREATE TABLE edit_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        revision INTEGER NOT NULL UNIQUE REFERENCES changes(revision),
        delta TEXT NOT NULL, applied INTEGER NOT NULL CHECK(applied IN (0, 1)))""",
)


class ProjectError(ValueError):
    """Invalid project, unsupported format or rejected mutation."""


class RevisionConflict(ProjectError):
    """The caller edited an older revision; reload before trying again."""


class UnsupportedProjectFormat(ProjectError):
    """A recognized project uses a format this version cannot open or migrate."""


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ProjectError(f"{label} must be a nonempty string of at most 1024 characters")
    return value


def _id(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise ProjectError("IDs must be canonical UUID strings") from None
    return value


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProjectError(f"Expected finite JSON data: {exc}") from None


def _check_value(value, kind):
    # Unset cells are absent from snapshots; explicit JSON null is a stored empty value.
    if value is None:
        return
    valid = {
        "text": isinstance(value, str),
        "integer": type(value) is int and -(2**63) <= value < 2**63,
        "number": type(value) in (int, float),
        "boolean": type(value) is bool,
        "json": True,
    }[kind]
    if kind == "number" and valid:
        try:
            valid = math.isfinite(value)
        except OverflowError:
            valid = False
    if not valid:
        raise ProjectError(f"Value does not match field type {kind}")


def _reference(value):
    if not isinstance(value, dict) or set(value) != {"record_id", "field_id"}:
        raise ProjectError("A cell reference contains exactly record_id and field_id")
    _id(value["record_id"])
    _id(value["field_id"])


def _expected_revision(value):
    if type(value) is not int or value < 0:
        raise ProjectError("expected_revision must be a nonnegative integer")


def _version(db):
    return db.execute("PRAGMA user_version").fetchone()[0]


class ProjectStore:
    """Open an existing project directory; use create() to initialize one explicitly."""

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / DATABASE_NAME
        self._project_id = None
        with self._connect() as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ProjectError("Project database integrity check failed")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ProjectError("Project database contains invalid references")
            if db.execute("SELECT count(*) FROM project").fetchone()[0] != 1:
                raise ProjectError("Project database must contain exactly one project")
            self._project_id = db.execute("SELECT id FROM project").fetchone()[0]

    @classmethod
    def create(cls, directory, name):
        name = _text(name, "Project name")
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / DATABASE_NAME
        # Do not truncate another project, including a zero-byte or invalid database.
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            db = sqlite3.connect(path)
            try:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    for statement in (*_DDL, *_DDL_V2, *_DDL_V3):
                        db.execute(statement)
                    db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    db.execute(f"PRAGMA user_version={FORMAT_VERSION}")
                    db.execute("INSERT INTO project VALUES (?, ?, 0)", (str(uuid4()), name))
            finally:
                db.close()
        except Exception as exc:
            path.unlink(missing_ok=True)
            if isinstance(exc, sqlite3.Error):
                raise ProjectError(f"Cannot create project database: {exc}") from None
            raise
        return cls(directory)

    @contextmanager
    def _connect(self, *, write=False):
        db = None
        try:
            # URI mode avoids silently creating a database when a path is misspelled.
            db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                 uri=True, timeout=10, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise ProjectError("Not an STK project database")
            version = _version(db)
            if version not in (1, 2, FORMAT_VERSION):
                raise UnsupportedProjectFormat(f"Unsupported project format {version}; supported: 1–{FORMAT_VERSION}")
            if self._project_id is not None:
                row = db.execute("SELECT id FROM project").fetchone()
                if row is None or row[0] != self._project_id:
                    raise ProjectError("Project database was replaced; close and reopen it")
            yield db
            db.commit()
        except sqlite3.Error as exc:
            raise ProjectError(f"Cannot access project database: {exc}") from None
        finally:
            if db is not None:
                db.close()  # Also rolls back uncommitted mutations on any exception.

    def info(self):
        """Read project identity/revision without loading all records or values."""
        with self._connect() as db:
            return {**dict(db.execute("SELECT * FROM project").fetchone()), "format_version": _version(db)}

    def _backup(self, db):
        """Online SQLite backup of an already established *read* snapshot, published atomically."""
        project = dict(db.execute("SELECT * FROM project").fetchone())
        version = _version(db)
        folder = self.directory / "backups"
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise ProjectError("Project backups path must be a directory, not a symbolic link or file")
        folder.mkdir(mode=0o700, exist_ok=True)
        name = f"format-{version}-revision-{project['revision']}-{uuid4().hex}.sqlite3"
        target = folder / name
        temporary = folder / (name + ".tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            copied = sqlite3.connect(temporary)
            try:
                db.backup(copied)
                if copied.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ProjectError("Backup integrity check failed")
                if copied.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ProjectError("Backup contains invalid references")
                if copied.execute("SELECT id, revision FROM project").fetchone() != (project["id"], project["revision"]):
                    raise ProjectError("Backup does not match the selected project revision")
            finally:
                copied.close()
            with temporary.open("rb+") as stream:
                os.fsync(stream.fileno())
            # Both names contain a newly generated UUID; never reuse a previous backup name.
            if target.exists():
                raise ProjectError("Backup target unexpectedly exists; retry with a new backup name")
            temporary.rename(target)
            if os.name != "nt":
                fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)
        return {"path": str(target), "project_id": project["id"], "revision": project["revision"],
                "format_version": version}

    def backup(self):
        """Back up the database, not external files/resources; leaves project revision unchanged."""
        with self._connect() as db:
            return self._backup(db)

    def upgrade(self, *, expected_revision):
        """Explicit versioned migration; backup completes before any schema change."""
        _expected_revision(expected_revision)
        with self._connect(write=True) as db:
            project = dict(db.execute("SELECT * FROM project").fetchone())
            if project["revision"] != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {project['revision']}")
            version = _version(db)
            if version == FORMAT_VERSION:
                return {"upgraded": False, "format_version": version, "revision": expected_revision, "backup": None}
            # A RESERVED writer lock blocks other writers; a separate reader sees the exact
            # pre-migration state. SQLite backup must not run on a connection in a write txn.
            with self._connect() as source:
                identity = source.execute("SELECT id, revision FROM project").fetchone()
                if tuple(identity) != (project["id"], expected_revision) or _version(source) != version:
                    raise ProjectError("Project changed while preparing the migration backup")
                backup = self._backup(source)
            for source_version, statements in ((1, _DDL_V2), (2, _DDL_V3)):
                if version <= source_version:
                    for statement in statements:
                        db.execute(statement)
            db.execute(f"PRAGMA user_version={FORMAT_VERSION}")
            revision = expected_revision + 1
            db.execute("UPDATE project SET revision=?", (revision,))
            command = {"op": "upgrade_format", "from_version": version, "to_version": FORMAT_VERSION}
            db.execute("INSERT INTO changes VALUES (?, ?, ?)",
                       (revision, datetime.now(timezone.utc).isoformat(), _json([command])))
            return {"upgraded": True, "format_version": FORMAT_VERSION, "revision": revision, "backup": backup}

    @staticmethod
    def _model(db):
        fields = {row["id"]: dict(row) for row in db.execute("SELECT * FROM fields")}
        records = {row["id"]: dict(row) for row in db.execute("SELECT * FROM records")}
        literals = {(row["record_id"], row["field_id"]): json.loads(row["value"]) for row in db.execute("SELECT * FROM cells")}
        definitions, cache = {}, {}
        if _version(db) >= 2:
            definitions = {(row["record_id"], row["field_id"]): json.loads(row["definition"])
                           for row in db.execute("SELECT * FROM definitions")}
            for row in db.execute("SELECT * FROM evaluations"):
                try:
                    cache[(row["record_id"], row["field_id"])] = json.loads(row["result"])
                except (ValueError, RecursionError):
                    pass  # Derived data can be rebuilt; a corrupt cache is not a project definition.
        return fields, records, literals, definitions, cache

    @classmethod
    def _evaluate(cls, db, revision, changed=(), *, persist=False):
        fields, records, literals, definitions, cache = cls._model(db)
        cells = {marker[1:] for marker in changed if marker[0] == "cell"}
        record_ids = {marker[1] for marker in changed if marker[0] == "record"}
        field_ids = {marker[1] for marker in changed if marker[0] == "field"}
        universe = set(literals) | definitions.keys()
        for definition in definitions.values():
            universe.update(dependencies(definition))
        cells.update(key for key in universe if key[0] in record_ids or key[1] in field_ids)
        cache, affected = evaluate(fields, records, literals, definitions, cache, cells, revision)
        if persist:
            for key in affected:
                db.execute("""INSERT INTO evaluations VALUES (?, ?, ?)
                    ON CONFLICT(record_id, field_id) DO UPDATE SET result=excluded.result""", (*key, _json(cache[key])))
        return definitions, cache, affected

    def snapshot(self):
        """Read all tables at one revision; UUID keys do not depend on names or display order."""
        with self._connect() as db:
            project = dict(db.execute("SELECT * FROM project").fetchone())
            definitions, cache, _ = self._evaluate(db, project["revision"]) if _version(db) >= 2 else ({}, {}, set())
            tables = [dict(row) for row in db.execute("SELECT * FROM tables ORDER BY rowid")]
            for table in tables:
                table["fields"] = [dict(row) for row in db.execute(
                    "SELECT id, name, type, unit FROM fields WHERE table_id=? ORDER BY rowid", (table["id"],))]
                records = {row["id"]: {"id": row["id"], "values": {}} for row in db.execute(
                    "SELECT id FROM records WHERE table_id=? ORDER BY rowid", (table["id"],))}
                for cell in db.execute("SELECT * FROM cells WHERE table_id=?", (table["id"],)):
                    records[cell["record_id"]]["values"][cell["field_id"]] = json.loads(cell["value"])
                for (record_id, field_id), definition in definitions.items():
                    if record_id not in records:
                        continue
                    record = records[record_id]
                    record.setdefault("definitions", {})[field_id] = definition
                    result = cache[(record_id, field_id)]
                    record.setdefault("evaluations", {})[field_id] = result
                    if result["state"] == "ok":
                        record["values"][field_id] = result["value"]
                table["records"] = list(records.values())
            result = {"format_version": _version(db), "project": project, "tables": tables}
            if _version(db) >= 3:
                result["edit_history"] = self._edit_history(db)
            return result

    @staticmethod
    def _edit_history(db):
        undo = db.execute("SELECT revision FROM edit_journal WHERE applied=1 ORDER BY id DESC LIMIT 1").fetchone()
        redo = db.execute("SELECT revision FROM edit_journal WHERE applied=0 ORDER BY id LIMIT 1").fetchone()
        return {"undo_revision": undo[0] if undo else None, "redo_revision": redo[0] if redo else None}

    def undo(self, *, expected_revision):
        return self._restore_edit(expected_revision, redo=False)

    def redo(self, *, expected_revision):
        return self._restore_edit(expected_revision, redo=True)

    def _restore_edit(self, expected_revision, *, redo):
        _expected_revision(expected_revision)
        with self._connect(write=True) as db:
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            if _version(db) < 3:
                raise UnsupportedProjectFormat("Upgrade this project to format 3 before undo/redo")
            order = "ASC" if redo else "DESC"
            entry = db.execute(f"SELECT * FROM edit_journal WHERE applied=? ORDER BY id {order} LIMIT 1",
                               (0 if redo else 1,)).fetchone()
            if entry is None:
                raise ProjectError("Nothing to redo" if redo else "Nothing to undo")
            try:
                changed = restore(db, json.loads(entry["delta"]), "after" if redo else "before")
            except (ValueError, TypeError, RecursionError) as exc:
                raise ProjectError(f"Cannot restore edit: {exc}") from None
            self._evaluate(db, revision + 1, changed, persist=True)
            db.execute("UPDATE edit_journal SET applied=? WHERE id=?", (1 if redo else 0, entry["id"]))
            db.execute("UPDATE project SET revision=?", (revision + 1,))
            command = {"op": "redo" if redo else "undo", "target_revision": entry["revision"]}
            db.execute("INSERT INTO changes VALUES (?, ?, ?)",
                       (revision + 1, datetime.now(timezone.utc).isoformat(), _json([command])))
            return {"revision": revision + 1, "target_revision": entry["revision"]}

    def history(self):
        with self._connect() as db:
            return [{"revision": row["revision"], "created_at": row["created_at"],
                     "commands": json.loads(row["commands"])}
                    for row in db.execute("SELECT * FROM changes ORDER BY revision")]

    def apply(self, commands, *, expected_revision):
        """Apply a JSON command list atomically, returning assigned IDs and the new revision."""
        _expected_revision(expected_revision)
        if not isinstance(commands, list) or not commands or len(commands) > 1000:
            raise ProjectError("Expected between 1 and 1000 commands")
        # Detach from caller-owned values before validation/transaction/history serialization.
        commands = json.loads(_json(commands))
        with self._connect(write=True) as db:
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            changed = set()
            capture = Capture(db) if _version(db) >= 3 else None
            applied = []
            for command in commands:
                if capture:
                    capture.command(command)
                applied.append(self._apply_command(db, command, changed))
                if capture:
                    capture.created(command)
            if _version(db) >= 2:
                self._evaluate(db, revision + 1, changed, persist=True)
            db.execute("UPDATE project SET revision=?", (revision + 1,))
            db.execute("INSERT INTO changes VALUES (?, ?, ?)",
                       (revision + 1, datetime.now(timezone.utc).isoformat(), _json(applied)))
            if capture:
                db.execute("DELETE FROM edit_journal WHERE applied=0")
                delta = capture.delta()
                if delta:
                    db.execute("INSERT INTO edit_journal (revision, delta, applied) VALUES (?, ?, 1)",
                               (revision + 1, _json(delta)))
            return {"revision": revision + 1, "commands": applied}

    @staticmethod
    def _apply_command(db, command, changed):
        specs = {
            "create_table": ({"op", "name"}, {"id"}),
            "add_field": ({"op", "table_id", "name", "type"}, {"id", "unit"}),
            "add_record": ({"op", "table_id"}, {"id"}),
            "set_cell": ({"op", "table_id", "record_id", "field_id", "value"}, set()),
            "rename_table": ({"op", "id", "name"}, set()),
            "rename_field": ({"op", "id", "name"}, set()),
            "set_reference": ({"op", "table_id", "record_id", "field_id", "source"}, set()),
            "set_expression": ({"op", "table_id", "record_id", "field_id", "expression", "bindings"}, set()),
            "unset_cell": ({"op", "table_id", "record_id", "field_id"}, set()),
            "delete_record": ({"op", "id"}, set()),
            "delete_field": ({"op", "id"}, set()),
            "delete_table": ({"op", "id"}, set()),
        }
        if not isinstance(command, dict) or not isinstance(command.get("op"), str) or command["op"] not in specs:
            raise ProjectError("Unknown project command")
        op = command["op"]
        if op in {"set_reference", "set_expression", "unset_cell", "delete_record", "delete_field", "delete_table"} and _version(db) < 2:
            raise UnsupportedProjectFormat("Upgrade this project to format 2 before editing references/expressions or deleting objects")
        required, optional = specs[op]
        if not required <= command.keys() or command.keys() - required - optional:
            raise ProjectError(f"Invalid fields for command {op}")
        for key in ("id", "table_id", "record_id", "field_id"):
            if key in command:
                _id(command[key])
        if "name" in command:
            _text(command["name"], "Name")
        if op in {"create_table", "add_field", "add_record"}:
            command.setdefault("id", str(uuid4()))
        if op == "create_table":
            db.execute("INSERT INTO tables VALUES (?, ?)", (command["id"], command["name"]))
        elif op == "add_field":
            kind, unit = command["type"], command.get("unit")
            if not isinstance(kind, str) or kind not in FIELD_TYPES:
                raise ProjectError("Unsupported field type")
            if unit is not None:
                _text(unit, "Unit")
                if kind not in {"integer", "number"}:
                    raise ProjectError("Only numeric fields may declare a unit")
            db.execute("INSERT INTO fields VALUES (?, ?, ?, ?, ?)",
                       (command["id"], command["table_id"], command["name"], kind, unit))
            changed.add(("field", command["id"]))
        elif op == "add_record":
            db.execute("INSERT INTO records VALUES (?, ?)", (command["id"], command["table_id"]))
            changed.add(("record", command["id"]))
        elif op in {"set_cell", "set_reference", "set_expression", "unset_cell"}:
            field = db.execute("SELECT * FROM fields WHERE table_id=? AND id=?",
                               (command["table_id"], command["field_id"])).fetchone()
            if field is None:
                raise ProjectError("Field does not belong to the requested table")
            if db.execute("SELECT 1 FROM records WHERE table_id=? AND id=?", (command["table_id"], command["record_id"])).fetchone() is None:
                raise ProjectError("Record does not belong to the requested table")
            key = (command["record_id"], command["field_id"])
            changed.add(("cell", *key))
            definition = None
            if op == "set_reference":
                _reference(command["source"])
                definition = {"kind": "reference", "source": command["source"]}
            elif op == "set_expression":
                if not isinstance(command["expression"], str) or not 1 <= len(command["expression"]) <= MAX_EXPRESSION:
                    raise ProjectError("Expression must contain 1–4096 characters")
                if not isinstance(command["bindings"], dict) or len(command["bindings"]) > MAX_BINDINGS:
                    raise ProjectError("Expression needs an object of up to 64 bindings")
                for reference in command["bindings"].values():
                    _reference(reference)
                definition = {"kind": "expression", "expression": command["expression"], "bindings": command["bindings"]}
            if op == "set_cell":
                _check_value(command["value"], field["type"])
            db.execute("DELETE FROM cells WHERE record_id=? AND field_id=?", key)
            if _version(db) >= 2:
                db.execute("DELETE FROM definitions WHERE record_id=? AND field_id=?", key)
            if definition is not None:
                db.execute("INSERT INTO definitions VALUES (?, ?, ?, ?)",
                           (command["table_id"], *key, _json(definition)))
            elif op == "set_cell":
                db.execute("INSERT INTO cells VALUES (?, ?, ?, ?)", (command["table_id"], *key, _json(command["value"])))
        elif op in {"delete_record", "delete_field", "delete_table"}:
            kind = op.removeprefix("delete_")
            table = {"record": "records", "field": "fields", "table": "tables"}[kind]
            if db.execute(f"SELECT 1 FROM {table} WHERE id=?", (command["id"],)).fetchone() is None:
                raise ProjectError("Cannot delete a missing object")
            if kind == "table":
                for record in db.execute("SELECT id FROM records WHERE table_id=?", (command["id"],)):
                    changed.add(("record", record[0]))
                for field in db.execute("SELECT id FROM fields WHERE table_id=?", (command["id"],)):
                    changed.add(("field", field[0]))
            else:
                changed.add((kind, command["id"]))
            column = kind + "_id"
            db.execute(f"DELETE FROM definitions WHERE {column}=?", (command["id"],))
            db.execute(f"DELETE FROM cells WHERE {column}=?", (command["id"],))
            if kind == "table":
                db.execute("DELETE FROM records WHERE table_id=?", (command["id"],))
                db.execute("DELETE FROM fields WHERE table_id=?", (command["id"],))
            db.execute(f"DELETE FROM {table} WHERE id=?", (command["id"],))
        else:
            table = "tables" if op == "rename_table" else "fields"  # Fixed identifiers, never caller SQL.
            if db.execute(f"UPDATE {table} SET name=? WHERE id=?", (command["name"], command["id"])).rowcount != 1:
                raise ProjectError("Cannot rename a missing object")
        return command
