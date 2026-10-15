"""Same-project object references over existing stores; metadata reads never execute work."""
import hashlib
import json

from .field_types import OBJECT_KINDS, reference
from .store import ProjectError, _id, _version


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def blob_path(sha):
    return f".stk/objects/sha256/{sha[:2]}/{sha[2:]}"


def record_label(db, table_id, identity, table_name, values):
    """Readable, bounded literal metadata; never evaluate formulas or dereference values."""
    fields = list(db.execute("SELECT id,type FROM fields WHERE table_id=? ORDER BY rowid", (table_id,)))
    for prefer_text in (True, False):
        for field in fields:
            if (field["type"] == "text") != prefer_text:
                continue
            value = values.get(field["id"])
            if type(value) is str:
                text = value[:512]
            elif type(value) in (int, float, bool):
                text = json.dumps(value, allow_nan=False)
            else:
                continue
            text = " ".join("".join(c if c.isprintable() else " " for c in text).split())
            if text:
                text = text if len(text) <= 128 else text[:127] + "…"
                return f"{table_name[:64]} / {text}"
    return f"{table_name[:64]} / {identity[:8]}"


def resolve(store, db, value):
    value = reference(value, store._project_id)
    kind, identity = value["kind"], value["id"]
    result = {"reference": value, "state": "missing", "label": identity,
              "summary": {}, "reason": "Referenced object is missing"}
    observed = None
    if kind == "record":
        row = db.execute("SELECT table_id FROM records WHERE id=?", (identity,)).fetchone()
        if row is not None and row[0] == value["table_id"]:
            table = db.execute("SELECT name FROM tables WHERE id=?", (row[0],)).fetchone()[0]
            values = {r[0]: json.loads(r[1]) for r in db.execute("SELECT field_id,value FROM cells WHERE record_id=?", (identity,))}
            definitions = {r[0]: json.loads(r[1]) for r in db.execute("SELECT field_id,definition FROM definitions WHERE record_id=?", (identity,))} if _version(db) >= 2 else {}
            observed = {"table_id": row[0], "values": values, "definitions": definitions}
            result.update(label=record_label(db, row[0], identity, table, values),
                          summary={"table_id": row[0], "fields": len(values)})
    elif kind == "file":
        from .files import TABLE_ID, FIELD_IDS
        row = db.execute("SELECT table_id FROM records WHERE id=?", (identity,)).fetchone()
        if row is not None and row[0] == TABLE_ID:
            values = {r[0]: json.loads(r[1]) for r in db.execute("SELECT field_id,value FROM cells WHERE record_id=?", (identity,))}
            data = {key: values.get(field) for key, field in FIELD_IDS.items()}
            observed = data
            result.update(label=data.get("name") or identity, summary=data)
            if data.get("state") != "present":
                result["reason"] = "Last saved file observation is missing or unavailable; refresh the file index explicitly"
                return result
    elif kind == "snapshot_file" and _version(db) >= 4:
        row = db.execute("SELECT * FROM project_snapshots WHERE id=?", (identity,)).fetchone()
        if row is not None:
            snapshot = store.snapshots._decode(row)
            files = snapshot["manifest"]["files"]
            matches = [f for f in files if value["path"] in {f["path"], blob_path(f["sha256"])}]
            if "record_id" in value:
                matches = [f for f in matches if f["record_id"] == value["record_id"]]
                if not matches:
                    result.update(state="stale", reason="Snapshot path and source record differ from the reference")
                    return result
            elif len(matches) > 1:
                result.update(state="stale", reason="Snapshot resource is ambiguous; select its source record explicitly")
                return result
            selected = next(iter(matches), None)
            if selected is not None:
                result.update(label=selected["name"], summary={"snapshot_id": identity, "content_verified": False, **selected})
                if selected["sha256"] != value["source_sha256"]:
                    result.update(state="stale", reason="Snapshot entry checksum differs from the reference")
                    return result
                path = store.snapshots._object(selected["sha256"])
                if path.is_symlink() or not path.is_file() or path.stat().st_size != selected["size"]:
                    result["reason"] = "Frozen snapshot resource is missing or has a changed file size/type"
                    return result
                result.update(state="available", reason=None)
                return result
    elif kind in {"analysis", "workflow"}:
        from . import analyses, workflows
        module = analyses if kind == "analysis" else workflows
        row = db.execute("SELECT table_id FROM records WHERE id=?", (identity,)).fetchone()
        if row is not None and row[0] == module.TABLE_ID:
            _, compatible, error = module._schema(db) if kind == "analysis" else module._TABLE.schema(db)
            entry = module._record(db, identity, compatible, error)
            if entry["state"] != "readable":
                result.update(state="stale", reason=entry["error"] or "Object schema is unreadable")
                return result
            observed = {"name": entry["name"], "document": entry["document"]}
            result.update(label=entry["name"], summary={"format": entry["format"]})
    elif kind == "simulation" and _version(db) >= 5:
        row = db.execute("SELECT * FROM run_plans WHERE id=?", (identity,)).fetchone()
        if row is not None:
            decoded = store.runs._decode(row)
            observed = decoded["plan"]
            result.update(label=observed["label"], summary={"plan_sha256": decoded["sha256"],
                          "source_revision": observed["source_revision"]})
    if observed is not None:
        source = digest(observed)
        result["summary"]["source_sha256"] = source
        if value.get("source_sha256", source) != source:
            result.update(state="stale", reason="Object contents changed since the reference was captured")
        else:
            result.update(state="available", reason=None)
    return result


def candidates(store, db, kind, table_id=None, offset=0, limit=100):
    if type(kind) is not str or kind not in OBJECT_KINDS:
        raise ProjectError("Unknown object kind")
    if table_id is not None and kind != "record":
        raise ProjectError("Only record candidates accept a target table_id")
    if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 200:
        raise ProjectError("Object pagination requires offset >= 0 and limit 1 to 200")
    refs = []
    base = {"version": 1, "project_id": store._project_id, "kind": kind}
    if kind == "snapshot_file":
        if _version(db) >= 4:
            for row in db.execute("SELECT * FROM project_snapshots ORDER BY rowid"):
                for file in store.snapshots._decode(row)["manifest"]["files"]:
                    refs.append({**base, "id": row["id"], "record_id": file["record_id"],
                                 "path": blob_path(file["sha256"]), "source_sha256": file["sha256"]})
    elif kind == "simulation":
        if _version(db) >= 5:
            refs = [{**base, "id": row[0]} for row in db.execute("SELECT id FROM run_plans ORDER BY rowid")]
    else:
        if kind == "record":
            _id(table_id)
            wanted = table_id
        elif kind == "file":
            from .files import TABLE_ID
            wanted = TABLE_ID
        elif kind == "analysis":
            from .analyses import TABLE_ID
            wanted = TABLE_ID
        else:
            from .workflows import TABLE_ID
            wanted = TABLE_ID
        refs = [{**base, "id": row[0], **({"table_id": wanted} if kind == "record" else {})}
                for row in db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid", (wanted,))]
    items = []
    for ref in refs[offset:offset + limit]:
        item = resolve(store, db, ref)
        if kind not in {"file", "snapshot_file"} and item["state"] == "available":
            ref = {**ref, "source_sha256": item["summary"]["source_sha256"]}
        items.append({"reference": ref, "label": item["label"], "state": item["state"], "summary": item["summary"]})
    return {"items": items, "total": len(refs), "next_offset": offset + limit if offset + limit < len(refs) else None}
