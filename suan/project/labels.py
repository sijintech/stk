"""Data labels (project format 12, docs/design/model-gateway.md).

Project data is private unless a person labels it public: only public data may be sent to an external
model endpoint (owner decision 8, docs/design/sijin-platform-2026-10.md). Each change is one appended row
of ``project_labels`` (``kind, object_id, label, at, note``) and an object's current label is its last row;
no row means private. Format 13 adds ``structure`` for tables: the table's structure (name, field names, units,
row count) is public while its values stay private (owner decision 2026-10-09, docs/design/agent-harness.md).
Like archiving, labelling records a decision about the data, not an edit: it never advances the editable revision
or enters undo. Below format 12 everything is private: every read here answers so and only ``set`` asks for the upgrade.
"""
from datetime import datetime, timezone

from .store import ProjectError, UnsupportedProjectFormat, _id, _version

KINDS = ("table", "file")
LABELS = ("public", "structure", "private")
MAX_ITEMS = 100
MAX_NOTE_CHARS = 1000
_CURRENT = ("SELECT a.object_id FROM project_labels a WHERE a.kind=? AND a.label='public' AND a.id="
            "(SELECT max(b.id) FROM project_labels b WHERE b.kind=a.kind AND b.object_id=a.object_id)")


def available(db):
    return _version(db) >= 12


class Labels:
    def __init__(self, store):
        self.store = store

    def public_ids(self, kind):
        """The IDs currently labelled public of a kind."""
        if kind not in KINDS:
            raise ProjectError("Unknown label kind")
        with self.store._connect() as db:
            if not available(db):
                return set()
            return {row[0] for row in db.execute(_CURRENT, (kind,))}

    def is_public(self, kind, object_id):
        with self.store._connect() as db:
            return self._public(db, kind, object_id)

    def structure_public(self, kind, object_id):
        """The object's structure may leave this computer: it is labelled public or (a table) structure-public."""
        with self.store._connect() as db:
            return self._label(db, kind, object_id) in ("public", "structure")

    def label(self, kind, object_id):
        """``public``, ``structure`` or ``private`` (no label, or below format 12)."""
        with self.store._connect() as db:
            return self._label(db, kind, object_id)

    @staticmethod
    def _label(db, kind, object_id):
        if not available(db):
            return "private"
        row = db.execute("SELECT label FROM project_labels WHERE kind=? AND object_id=? ORDER BY id DESC LIMIT 1",
                         (kind, object_id)).fetchone()
        return row[0] if row else "private"

    @staticmethod
    def _public(db, kind, object_id):
        return Labels._label(db, kind, object_id) == "public"

    def list(self, kind=None, *, include_structure=False):
        """Every object currently labelled public (optionally of one kind) with when and why; with
        ``include_structure`` also the tables whose structure only is public. Each item names its ``label``."""
        if kind is not None and kind not in KINDS:
            raise ProjectError("Unknown label kind")
        labels = "('public','structure')" if include_structure else "('public')"
        with self.store._connect() as db:
            if not available(db):
                return {"items": []}
            rows = db.execute(f"SELECT a.kind, a.object_id, a.at, a.note, a.label FROM project_labels a WHERE a.label IN {labels} "
                              "AND a.id=(SELECT max(b.id) FROM project_labels b WHERE b.kind=a.kind AND b.object_id=a.object_id)"
                              + (" AND a.kind=?" if kind else "") + " ORDER BY a.id", (kind,) if kind else ()).fetchall()
        return {"items": [{"kind": row[0], "id": row[1], "labelled_at": row[2], "note": row[3], "label": row[4]} for row in rows]}

    def set(self, items, *, label, note=None):
        """Label 1-100 existing objects public or private; objects already so labelled are left alone.
        Returns the ones that changed."""
        if label not in LABELS:
            raise ProjectError("label is public, structure or private")
        if note is not None and (type(note) is not str or len(note) > MAX_NOTE_CHARS or "\0" in note):
            raise ProjectError(f"A label note is text of at most {MAX_NOTE_CHARS} characters")
        if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
            raise ProjectError(f"Label 1 to {MAX_ITEMS} objects at a time")
        wanted = []
        for item in items:
            if type(item) is not dict or set(item) != {"kind", "id"} or item["kind"] not in KINDS:
                raise ProjectError("Each labelled object is {kind, id} of a known kind")
            if label == "structure" and item["kind"] != "table":
                raise ProjectError("Only a table's structure can be labelled public on its own")
            key = (item["kind"], _id(item["id"]))
            if key not in wanted:
                wanted.append(key)
        now = datetime.now(timezone.utc).isoformat()
        with self.store._connect(write=True) as db:
            if not available(db):
                raise UnsupportedProjectFormat("Upgrade this project to format 12 before labelling data")
            if label == "structure" and _version(db) < 13:
                raise UnsupportedProjectFormat("Upgrade this project to format 13 before labelling a table's structure public")
            for kind, object_id in wanted:
                self._check(db, kind, object_id)
            changed = []
            for kind, object_id in wanted:
                if self._label(db, kind, object_id) == label:
                    continue
                db.execute("INSERT INTO project_labels(kind, object_id, label, at, note) VALUES (?,?,?,?,?)",
                           (kind, object_id, label, now, note))
                changed.append({"kind": kind, "id": object_id})
        return {"changed": len(changed), "items": changed}

    @staticmethod
    def _check(db, kind, object_id):
        from . import files
        if kind == "table":
            found = db.execute("SELECT 1 FROM tables WHERE id=?", (object_id,)).fetchone()
        else:
            found = db.execute("SELECT 1 FROM records WHERE id=? AND table_id=?", (object_id, files.TABLE_ID)).fetchone()
        if found is None:
            raise ProjectError(f"No {kind} {object_id} in this project")


__all__ = ["Labels", "KINDS", "LABELS", "available"]
