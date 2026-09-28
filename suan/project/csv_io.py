"""Bounded CSV/TSV exchange through ordinary project edits; not a project backup format."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from uuid import uuid4

from .store import FIELD_TYPES, ProjectError, RevisionConflict, _check_value, _expected_revision, _text

MAX_BYTES = 8 * 1024 * 1024
MAX_FIELDS = 64
MAX_EXPORT_ROWS = 10000


def _delimiter(value):
    if value not in (",", "\t"):
        raise ProjectError("CSV delimiter must be comma or tab")
    return value


def _path(store, path):
    path = Path(path).expanduser()
    return (store.directory / path if not path.is_absolute() else path).absolute()


def _read(path):
    # O_NONBLOCK keeps a replaced FIFO from hanging a project session on POSIX.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ProjectError("CSV source must be a regular file")
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(data) > MAX_BYTES:
        raise ProjectError("CSV source exceeds 8 MiB")
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if identity(before) != identity(after):
        raise ProjectError("CSV source changed while reading; retry after checking the file")
    try:
        return data.decode("utf-8-sig"), hashlib.sha256(data).hexdigest()
    except UnicodeError:
        raise ProjectError("CSV source must use UTF-8 (an optional BOM is accepted)") from None


def _headers(values):
    if not values or len(values) > MAX_FIELDS:
        raise ProjectError("CSV needs between 1 and 64 named columns")
    for value in values:
        _text(value, "CSV column name")
    if len(set(values)) != len(values):
        raise ProjectError("CSV column names must be unique")


def _constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def _literal(text, kind, row, name):
    if kind == "text":
        return text  # Never guess that a text value is a number, boolean or formula.
    stripped = text.strip()
    if not stripped:
        return None
    try:
        value = json.loads(stripped, parse_constant=_constant)
        _check_value(value, kind)
        return value
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProjectError(f"CSV record {row}, column {name!r}: invalid {kind} value ({exc})") from None


class TableCSV:
    def __init__(self, store):
        self.store = store

    def import_file(self, source, *, name, expected_revision, types=None, units=None, delimiter=","):
        """Create one new table in one undoable edit batch; no inference or partial import."""
        _expected_revision(expected_revision)
        _text(name, "Table name")
        delimiter = _delimiter(delimiter)
        types, units = {} if types is None else types, {} if units is None else units
        if not isinstance(types, dict) or not isinstance(units, dict):
            raise ProjectError("CSV types and units must map column names to declarations")
        source = _path(self.store, source)
        text, digest = _read(source)
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        try:
            headers = next(reader, None)
            _headers(headers)
            if set(types) - set(headers) or set(units) - set(headers):
                raise ProjectError("CSV types/units contain names that are not in the header")
            table_id = str(uuid4())
            fields = [str(uuid4()) for _ in headers]
            commands = [{"op": "create_table", "id": table_id, "name": name}]
            for column, identity in zip(headers, fields):
                kind = types.get(column, "text")
                if not isinstance(kind, str) or kind not in FIELD_TYPES:
                    raise ProjectError(f"Unsupported CSV type for {column!r}")
                unit = units.get(column)
                if unit is not None:
                    _text(unit, "Unit")
                    if kind not in {"integer", "number"}:
                        raise ProjectError("Only numeric CSV columns may declare a unit")
                commands.append({"op": "add_field", "table_id": table_id, "id": identity,
                                 "name": column, "type": kind, "unit": unit})
            records = []
            for index, values in enumerate(reader, 1):
                if len(values) != len(headers):
                    raise ProjectError(f"CSV record {index} has {len(values)} values; expected {len(headers)}")
                if len(commands) + 1 + len(fields) > 1000:
                    raise ProjectError("CSV import exceeds one atomic edit batch (1000 table/field/record/cell commands)")
                record = str(uuid4())
                records.append(record)
                commands.append({"op": "add_record", "table_id": table_id, "id": record})
                for column, identity, value in zip(headers, fields, values):
                    commands.append({"op": "set_cell", "table_id": table_id, "record_id": record,
                                     "field_id": identity, "value": _literal(value, types.get(column, "text"), index, column)})
        except csv.Error as exc:
            raise ProjectError(f"Invalid CSV: {exc}") from None
        result = self.store.apply(commands, expected_revision=expected_revision)
        return {"revision": result["revision"], "table_id": table_id, "field_ids": fields,
                "record_ids": records, "rows": len(records), "columns": len(fields), "source_sha256": digest}

    def export_file(self, table_id, destination, *, expected_revision, delimiter=","):
        """Export evaluated values from one consistent revision, never replace an existing file."""
        _expected_revision(expected_revision)
        delimiter = _delimiter(delimiter)
        snapshot = self.store.snapshot()
        revision = snapshot["project"]["revision"]
        if revision != expected_revision:
            raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {revision}")
        table = next((table for table in snapshot["tables"] if table["id"] == table_id), None)
        if table is None:
            raise ProjectError("CSV table does not exist")
        fields = table["fields"]
        headers = [field["name"] for field in fields]
        _headers(headers)
        if len(table["records"]) > MAX_EXPORT_ROWS:
            raise ProjectError("CSV export supports at most 10000 records")
        buffer = io.BytesIO(b"\xef\xbb\xbf")
        buffer.seek(0, io.SEEK_END)

        def write_row(values):
            row = io.StringIO(newline="")
            csv.writer(row, delimiter=delimiter, lineterminator="\r\n").writerow(values)
            data = row.getvalue().encode("utf-8")
            if buffer.tell() + len(data) > MAX_BYTES:
                raise ProjectError("CSV export exceeds 8 MiB")
            buffer.write(data)

        write_row(headers)
        for record in table["records"]:
            values = []
            for field in fields:
                evaluation = record.get("evaluations", {}).get(field["id"], {})
                if evaluation.get("state") == "error":
                    raise ProjectError(f"Cannot export formula error at record {record['id']}, field {field['id']}")
                value = record["values"].get(field["id"])
                if field["type"] == "json":
                    values.append(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
                elif value is None:
                    values.append("")
                elif field["type"] == "text":
                    values.append(value)
                else:
                    values.append(json.dumps(value, allow_nan=False))
            write_row(values)
        data = buffer.getvalue()
        destination = _path(self.store, destination)
        temporary = None
        try:
            # A hard-link publication is atomic and cannot replace an existing target, including
            # a symlink. The temporary file is closed before publication for Windows support.
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".stk-csv-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {"revision": revision, "table_id": table_id, "path": str(destination), "rows": len(table["records"]),
                "columns": len(fields), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
