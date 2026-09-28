"""First project-storage slice: typed tables, stable IDs and atomic revisioned edits.

This experimental format is distinct from the Runtime database and graph-v1.
Only literal cells are implemented; persistence never evaluates or submits work.
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


APPLICATION_ID = 0x53544B50  # STKP
FORMAT_VERSION = 1
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
                    for statement in _DDL:
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
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version != FORMAT_VERSION:
                raise UnsupportedProjectFormat(f"Unsupported project format {version}; expected {FORMAT_VERSION}")
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
            return {**dict(db.execute("SELECT * FROM project").fetchone()), "format_version": FORMAT_VERSION}

    def snapshot(self):
        """Read all tables at one revision; UUID keys do not depend on names or display order."""
        with self._connect() as db:
            project = dict(db.execute("SELECT * FROM project").fetchone())
            tables = [dict(row) for row in db.execute("SELECT * FROM tables ORDER BY rowid")]
            for table in tables:
                table["fields"] = [dict(row) for row in db.execute(
                    "SELECT id, name, type, unit FROM fields WHERE table_id=? ORDER BY rowid", (table["id"],))]
                records = {row["id"]: {"id": row["id"], "values": {}} for row in db.execute(
                    "SELECT id FROM records WHERE table_id=? ORDER BY rowid", (table["id"],))}
                for cell in db.execute("SELECT * FROM cells WHERE table_id=?", (table["id"],)):
                    records[cell["record_id"]]["values"][cell["field_id"]] = json.loads(cell["value"])
                table["records"] = list(records.values())
            return {"format_version": FORMAT_VERSION, "project": project, "tables": tables}

    def history(self):
        with self._connect() as db:
            return [{"revision": row["revision"], "created_at": row["created_at"],
                     "commands": json.loads(row["commands"])}
                    for row in db.execute("SELECT * FROM changes ORDER BY revision")]

    def apply(self, commands, *, expected_revision):
        """Apply a JSON command list atomically, returning assigned IDs and the new revision."""
        if type(expected_revision) is not int or expected_revision < 0:
            raise ProjectError("expected_revision must be a nonnegative integer")
        if not isinstance(commands, list) or not commands or len(commands) > 1000:
            raise ProjectError("Expected between 1 and 1000 commands")
        # Detach from caller-owned values before validation/transaction/history serialization.
        commands = json.loads(_json(commands))
        with self._connect(write=True) as db:
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
            applied = [self._apply_command(db, command) for command in commands]
            db.execute("UPDATE project SET revision=?", (revision + 1,))
            db.execute("INSERT INTO changes VALUES (?, ?, ?)",
                       (revision + 1, datetime.now(timezone.utc).isoformat(), _json(applied)))
            return {"revision": revision + 1, "commands": applied}

    @staticmethod
    def _apply_command(db, command):
        specs = {
            "create_table": ({"op", "name"}, {"id"}),
            "add_field": ({"op", "table_id", "name", "type"}, {"id", "unit"}),
            "add_record": ({"op", "table_id"}, {"id"}),
            "set_cell": ({"op", "table_id", "record_id", "field_id", "value"}, set()),
            "rename_table": ({"op", "id", "name"}, set()),
            "rename_field": ({"op", "id", "name"}, set()),
        }
        if not isinstance(command, dict) or not isinstance(command.get("op"), str) or command["op"] not in specs:
            raise ProjectError("Unknown project command")
        op = command["op"]
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
        elif op == "add_record":
            db.execute("INSERT INTO records VALUES (?, ?)", (command["id"], command["table_id"]))
        elif op == "set_cell":
            field = db.execute("SELECT type FROM fields WHERE table_id=? AND id=?",
                               (command["table_id"], command["field_id"])).fetchone()
            if field is None:
                raise ProjectError("Field does not belong to the requested table")
            _check_value(command["value"], field["type"])
            db.execute("""INSERT INTO cells VALUES (?, ?, ?, ?)
                ON CONFLICT(record_id, field_id) DO UPDATE SET value=excluded.value""",
                       (command["table_id"], command["record_id"], command["field_id"], _json(command["value"])))
        else:
            table = "tables" if op == "rename_table" else "fields"  # Fixed identifiers, never caller SQL.
            if db.execute(f"UPDATE {table} SET name=? WHERE id=?", (command["name"], command["id"])).rowcount != 1:
                raise ProjectError("Cannot rename a missing object")
        return command
