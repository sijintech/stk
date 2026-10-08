"""Find names and text in one project (UX package U3).

A read-only, case-insensitive substring search over parameter tables (table and field names, text
cells), saved workflow and analysis names, indexed file names and paths, AI draft titles and
discussion messages. Each result carries structured fields for the interface to word and a
navigation target; nothing is run, prepared or changed. Results are grouped by kind in a fixed
order, at most PER_KIND of each, newest data as stored (table order, row order).
"""
import json

from . import analyses, files, workflows
from .store import ProjectError, _version

MAX_QUERY_CHARS = 200
MAX_RESULTS = 200
PER_KIND = 50
SNIPPET_CHARS = 80
KINDS = ("table", "field", "cell", "workflow", "analysis", "file", "draft", "message")
_MANAGED = {analyses.TABLE_ID, workflows.TABLE_ID, files.TABLE_ID}


def _snippet(text, needle):
    """One line of at most SNIPPET_CHARS around the first match."""
    flat = " ".join(text.split())
    at = flat.casefold().find(needle)
    if len(flat) <= SNIPPET_CHARS or at < 0:
        return flat[:SNIPPET_CHARS] + ("…" if len(flat) > SNIPPET_CHARS else "")
    start = max(0, min(at - SNIPPET_CHARS // 3, len(flat) - SNIPPET_CHARS))
    return ("…" if start else "") + flat[start:start + SNIPPET_CHARS] + ("…" if start + SNIPPET_CHARS < len(flat) else "")


def search(store, query, *, limit=100):
    """Results for `query` (1-200 characters after trimming), at most `limit` (1-200) in total."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= MAX_QUERY_CHARS:
        raise ProjectError(f"A search needs 1 to {MAX_QUERY_CHARS} characters")
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ProjectError(f"Search limit must be between 1 and {MAX_RESULTS}")
    needle = query.strip().casefold()
    model = store.snapshot()
    with store._connect() as db:
        version = _version(db)
    found = {kind: [] for kind in KINDS}
    counts = dict.fromkeys(KINDS, 0)
    # Archived objects are found too, marked and listed after the others of their kind (format 11).
    archived = {kind: store.archive.ids(kind) for kind in ("workflow", "analysis", "draft", "context")}

    def add(kind, identity, *, shelved=False, **fields):
        counts[kind] += 1
        found[kind].append({"kind": kind, "id": identity, **fields, **({"archived": True} if shelved else {})})

    def matches(value):
        return isinstance(value, str) and needle in value.casefold()

    tables = {table["id"]: table for table in model["tables"]}
    for table in model["tables"]:
        if table["id"] in _MANAGED:
            continue
        target = {"page": "data", "table_id": table["id"]}
        if matches(table["name"]):
            add("table", table["id"], name=table["name"], target=target)
        for field in table["fields"]:
            if matches(field["name"]):
                add("field", field["id"], name=field["name"], table=table["name"], target=target)
        for row, record in enumerate(table["records"], 1):
            for field in table["fields"]:
                value = record["values"].get(field["id"])
                if matches(value):
                    add("cell", f"{record['id']}:{field['id']}", name=field["name"], table=table["name"], row=row,
                        text=_snippet(value, needle), target={**target, "record_id": record["id"]})
    for kind, module, editor, key in (("workflow", workflows, "workflow", "workflow_id"),
                                      ("analysis", analyses, "analysis_graph", "analysis_id")):
        table = tables.get(module.TABLE_ID)
        for record in table["records"] if table else ():
            name = record["values"].get(module.FIELD_IDS["name"])
            if matches(name):
                add(kind, record["id"], name=name, target={"editor": editor, key: record["id"]},
                    shelved=record["id"] in archived[kind])
    table = tables.get(files.TABLE_ID)
    for record in table["records"] if table else ():
        name, path = (record["values"].get(files.FIELD_IDS[key]) for key in ("name", "path"))
        if matches(name) or matches(path):
            add("file", record["id"], name=name if isinstance(name, str) else None, text=path if isinstance(path, str) else None,
                target={"page": "files", "record_id": record["id"]})
    if version >= 6:
        offset = 0
        while offset is not None:
            page = store.drafts.list(offset=offset, limit=100)
            for draft in page["drafts"]:
                if matches(draft.get("title")):
                    add("draft", draft["id"], name=draft["title"], status=draft.get("status"),
                        target={"page": "review", "draft_id": draft["id"]}, shelved=draft["id"] in archived["draft"])
            offset = page["next_offset"]
    if version >= 7:
        with store._connect() as db:
            rows = db.execute("SELECT id, context_id, payload FROM project_messages ORDER BY rowid").fetchall()
        for row in rows:
            try:
                message = json.loads(row["payload"])
                text, role = message["text"], message["role"]
            except (KeyError, TypeError, ValueError, RecursionError):
                continue  # an unreadable record is not a match; reading it reports the problem
            if matches(text):
                add("message", row["id"], role=role if role in ("user", "assistant") else None,
                    text=_snippet(text, needle), at=message.get("created_at"),
                    target={"page": "conversation", "message_id": row["id"]}, shelved=row["context_id"] in archived["context"])
    results = [item for kind in KINDS
               for item in sorted(found[kind], key=lambda entry: entry.get("archived", False))[:PER_KIND]]
    return {"revision": model["project"]["revision"], "query": query.strip(), "results": results[:limit],
            "counts": counts, "truncated": sum(counts.values()) > min(len(results), limit)}


__all__ = ["search", "KINDS", "MAX_QUERY_CHARS", "MAX_RESULTS"]
