"""Revision-bound structure and record pages for opening large projects.

Structure reads never materialize cell values or evaluate definitions. Record
pages share the table query's dependency reader, including off-page references.
Neither operation updates a project, reads resource files, or executes work.
"""
from .store import ProjectError, RevisionConflict, _expected_revision, _id, _json, _version
from .table_reader import TableReader


MAX_READ_BYTES = 8 * 1024 * 1024


def _page(offset, limit, maximum):
    if (type(offset) is not int or not 0 <= offset < 2**63 or
            type(limit) is not int or not 1 <= limit <= maximum):
        raise ProjectError(f"Read requires offset >= 0 and limit 1 to {maximum}")


def _project(db, expected_revision):
    project = dict(db.execute("SELECT * FROM project").fetchone())
    if expected_revision is not None:
        _expected_revision(expected_revision)
        if project["revision"] != expected_revision:
            raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {project['revision']}")
    return project


def _bounded(result):
    if len(_json(result).encode("utf-8")) > MAX_READ_BYTES:
        raise ProjectError("Project read exceeds 8 MiB; reduce the page size")
    return result


def _table(db, value, revision, version):
    table = dict(value)
    table["fields"] = TableReader(db, table["id"], revision, version).fields
    table["record_count"] = db.execute("SELECT count(*) FROM records WHERE table_id=?", (table["id"],)).fetchone()[0]
    first = db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT 1", (table["id"],)).fetchone()
    table["first_record_id"] = first[0] if first else None
    return table


def catalog(store, *, expected_revision=None, offset=0, limit=200):
    """Read one structure page. Pin subsequent pages to its project revision.

    Counts and first-record identities describe all records without transferring
    them. A missing file-index descriptor means the managed table does not exist,
    independently of which catalog page contains that table.
    """
    _page(offset, limit, 200)
    if offset and expected_revision is None:
        raise ProjectError("Subsequent catalog pages require expected_revision")
    with store._connect() as db:
        project = _project(db, expected_revision)
        version = _version(db)
        total = db.execute("SELECT count(*) FROM tables").fetchone()[0]
        tables = [_table(db, row, project["revision"], version) for row in db.execute(
            "SELECT * FROM tables ORDER BY rowid LIMIT ? OFFSET ?", (limit, offset))]
        result = {"format_version": version, "project": project, "tables": tables,
                  "total": total, "offset": offset, "next_offset": offset + len(tables) if offset + len(tables) < total else None}
        if version >= 3:
            result["edit_history"] = store._edit_history(db)
        from .files import TABLE_ID, descriptor
        file_table = next((table for table in tables if table["id"] == TABLE_ID), None)
        if file_table is None:
            row = db.execute("SELECT * FROM tables WHERE id=?", (TABLE_ID,)).fetchone()
            if row is not None:
                file_table = {**dict(row), "fields": TableReader(db, TABLE_ID, project["revision"], version).fields}
        if file_table is not None:
            result["file_index"] = descriptor({"tables": [file_table]})
        return _bounded(result)


def read_table(store, table_id, *, expected_revision, offset=0, limit=200, record_id=None):
    """Read a complete typed record page in insertion order at one revision.

    record_id selects the page containing that exact identity; a missing or
    foreign record is an error, never a fallback to the first row. Page positions
    are observations of this revision, not persistent record identities.
    """
    _id(table_id)
    _expected_revision(expected_revision)
    _page(offset, limit, 500)
    if record_id is not None:
        _id(record_id)
        if offset:
            raise ProjectError("Use either record_id or a nonzero offset")
    with store._connect() as db:
        project = _project(db, expected_revision)
        row = db.execute("SELECT * FROM tables WHERE id=?", (table_id,)).fetchone()
        if row is None:
            raise FileNotFoundError("Project table is missing")
        version = _version(db)
        reader = TableReader(db, table_id, project["revision"], version)
        total = db.execute("SELECT count(*) FROM records WHERE table_id=?", (table_id,)).fetchone()[0]
        if record_id is not None:
            selected = db.execute("SELECT rowid FROM records WHERE table_id=? AND id=?", (table_id, record_id)).fetchone()
            if selected is None:
                raise FileNotFoundError("Record is missing or belongs to another table")
            position = db.execute("SELECT count(*) FROM records WHERE table_id=? AND rowid<?", (table_id, selected[0])).fetchone()[0]
            offset = position // limit * limit
        ids = [item[0] for item in db.execute(
            "SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT ? OFFSET ?", (table_id, limit, offset))]
        table = {**dict(row), "fields": reader.fields, "records": reader.records(ids)}
        return _bounded({"project_id": project["id"], "revision": project["revision"], "format_version": version,
                         "table": table, "total": total, "offset": offset,
                         "next_offset": offset + len(ids) if offset + len(ids) < total else None})
