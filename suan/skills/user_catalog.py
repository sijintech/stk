"""Local, immutable user skill versions and publication receipts.

The caller chooses the state directory explicitly. Reads never create it, inspect source projects,
load node plugins, or evaluate a method. SQLite serializes version allocation and receipt insertion;
project history remains a separate, undoable store.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3

from .catalog import MAX_VERSION, SkillCatalogError, _canonical, _summary, describe_snapshot, unchecked_availability


MAX_VERSIONS = 1024
MAX_COLLECTION_BYTES = 64 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_SUMMARY_BYTES = 16 * 1024
MAX_PUBLICATIONS = 4096
MAX_RECEIPT_BYTES = 4096
APPLICATION_ID = 0x53544B53
DATABASE_VERSION = 1


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _uuid(value):
    from suan.project.store import ProjectError, _id
    try:
        return _id(value)
    except ProjectError as exc:
        raise SkillCatalogError("invalid_params", str(exc)) from None


def _source(value):
    from suan.project.store import ProjectError, _expected_revision
    if type(value) is not dict or set(value) != {"project_id", "project_skill_id", "revision", "content_sha256"}:
        raise SkillCatalogError("invalid_params", "Publication source requires project and record IDs, revision and digest")
    _uuid(value["project_id"])
    _uuid(value["project_skill_id"])
    try:
        _expected_revision(value["revision"])
    except ProjectError as exc:
        raise SkillCatalogError("invalid_params", str(exc)) from None
    if type(value["content_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["content_sha256"]):
        raise SkillCatalogError("invalid_params", "Publication source requires a lowercase SHA-256")
    return dict(value)


def _snapshot(value):
    from suan.project.managed import clone
    from suan.project.skills import _snapshot as check_snapshot
    from suan.project.store import ProjectError
    try:
        value = clone(value, "User skill", max_bytes=MAX_SNAPSHOT_BYTES)
        if len(_canonical(value).encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise ProjectError("User skill snapshot exceeds 8 MiB")
        check_snapshot(value)
        if value["definition"]["entry"]["kind"] not in ("graph.document", "workflow.document"):
            raise ProjectError("The user library accepts published analysis and workflow documents")
        return value
    except ProjectError as exc:
        raise SkillCatalogError("invalid_params", str(exc)) from None


def _decode(raw, limit):
    from suan.project.managed import strict_decode
    from suan.project.store import ProjectError
    if type(raw) is not str:
        raise SkillCatalogError("invalid_definition", "User library record exceeds its byte limit or is not text")
    try:
        return strict_decode(raw.encode("utf-8"), "User library record", max_bytes=limit)
    except (ProjectError, UnicodeError) as exc:
        raise SkillCatalogError("invalid_definition", str(exc)) from None


class UserSkillLibrary:
    def __init__(self, *, root):
        self.root = Path(root)
        self.path = self.root / "catalog.sqlite"

    @contextmanager
    def _connect(self, *, write=False):
        db = None
        try:
            if write:
                self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            elif self.path.exists():
                db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True,
                                     timeout=10, isolation_level=None)
            else:
                yield None
                return
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            app = db.execute("PRAGMA application_id").fetchone()[0]
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if write and app == 0 and version == 0 and not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
                db.execute("CREATE TABLE versions (skill_id TEXT NOT NULL, version INTEGER NOT NULL, "
                           "kind TEXT NOT NULL, sha TEXT NOT NULL, payload TEXT NOT NULL, payload_bytes INTEGER NOT NULL, "
                           "summary TEXT NOT NULL, summary_sha TEXT NOT NULL, PRIMARY KEY(skill_id, version))")
                db.execute("CREATE TABLE publications (id TEXT PRIMARY KEY, request_sha TEXT NOT NULL, "
                           "receipt TEXT NOT NULL, receipt_sha TEXT NOT NULL)")
                db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                db.execute(f"PRAGMA user_version={DATABASE_VERSION}")
            elif app != APPLICATION_ID or version != DATABASE_VERSION:
                raise SkillCatalogError("invalid_definition", "Unsupported user skill library database")
            yield db
            db.commit()
        except (sqlite3.Error, OSError) as exc:
            raise SkillCatalogError("invalid_definition", f"Cannot access user skill library: {exc}") from None
        finally:
            if db is not None:
                db.close()  # Rolls back every unsuccessful write, including receipt insertion.

    @staticmethod
    def _receipt(db, publication_id):
        row = db.execute("SELECT request_sha, CASE WHEN length(CAST(receipt AS BLOB)) <= ? THEN receipt END AS receipt, "
                         "receipt_sha FROM publications WHERE id=?", (MAX_RECEIPT_BYTES, publication_id)).fetchone()
        if row is None:
            return None
        receipt = _decode(row["receipt"], MAX_RECEIPT_BYTES)
        if (type(receipt) is not dict or set(receipt) != {"publication_id", "source", "mode", "skill", "created"} or
                receipt["publication_id"] != publication_id or receipt["mode"] not in ("exact", "new_version") or
                type(receipt["created"]) is not bool or _digest(receipt) != row["receipt_sha"]):
            raise SkillCatalogError("invalid_definition", "Invalid user skill publication receipt")
        _source(receipt["source"])
        skill = receipt["skill"]
        if (type(skill) is not dict or set(skill) != {"id", "version", "ref", "content_sha256", "source"} or
                type(skill["id"]) is not str or type(skill["version"]) is not int or
                not 1 <= skill["version"] <= MAX_VERSION or skill["source"] != "user" or
                skill["ref"] != f"{skill['id']}@{skill['version']}"):
            raise SkillCatalogError("invalid_definition", "Invalid published skill reference")
        stored = db.execute("SELECT sha FROM versions WHERE skill_id=? AND version=?",
                            (skill["id"], skill["version"])).fetchone()
        if stored is None or stored[0] != skill["content_sha256"]:
            raise SkillCatalogError("invalid_definition", "Publication refers to missing or changed user skill content")
        return row["request_sha"], receipt

    def publication(self, publication_id):
        _uuid(publication_id)
        with self._connect() as db:
            item = self._receipt(db, publication_id) if db is not None else None
            if item is None:
                raise SkillCatalogError("not_found", "User skill publication not found")
            return item[1]

    @staticmethod
    def _read_version(db, skill_id, version):
        row = db.execute("SELECT skill_id, version, kind, sha, CASE WHEN length(CAST(payload AS BLOB)) <= ? "
                         "THEN payload END AS payload FROM versions WHERE skill_id=? AND version=?",
                         (MAX_SNAPSHOT_BYTES, skill_id, version)).fetchone()
        if row is None:
            raise SkillCatalogError("not_found", "User skill version not found")
        try:
            value = _snapshot(_decode(row["payload"], MAX_SNAPSHOT_BYTES))
        except SkillCatalogError as exc:
            raise SkillCatalogError("invalid_definition", str(exc)) from None
        definition = value["definition"]
        if (definition["id"] != row["skill_id"] or definition["version"] != row["version"] or
                definition["entry"]["kind"] != row["kind"] or value["content_sha256"] != row["sha"]):
            raise SkillCatalogError("invalid_definition", "Stored user skill identity or digest changed")
        return value

    def snapshot(self, skill_id, version):
        with self._connect() as db:
            if db is None:
                raise SkillCatalogError("not_found", "User skill version not found")
            return self._read_version(db, skill_id, version)

    def summaries(self):
        """At most 1024 bounded projections; deliberately never select snapshot payloads."""
        from suan.graph.schema import check_value
        from .catalog import DEFINITION_SCHEMA
        items, problems = [], []
        with self._connect() as db:
            if db is None:
                return items, problems
            rows = db.execute("SELECT skill_id, version, kind, sha, summary_sha, "
                              "CASE WHEN length(CAST(summary AS BLOB)) <= ? THEN summary END AS summary "
                              "FROM versions ORDER BY skill_id, version LIMIT ?", (MAX_SUMMARY_BYTES, MAX_VERSIONS + 1))
            for index, row in enumerate(rows):
                if index >= MAX_VERSIONS:
                    raise SkillCatalogError("invalid_definition", "User skill library exceeds its version count limit")
                try:
                    item = _decode(row["summary"], MAX_SUMMARY_BYTES)
                    if (type(item) is not dict or set(item) != {"id", "version", "ref", "content_sha256", "source",
                                                              "title", "summary", "availability", "entry"} or
                            _digest(item) != row["summary_sha"] or item["id"] != row["skill_id"] or
                            item["version"] != row["version"] or item["content_sha256"] != row["sha"] or
                            item["ref"] != f"{row['skill_id']}@{row['version']}" or item["source"] != "user" or
                            item["entry"] != {"kind": row["kind"]} or row["kind"] not in ("graph.document", "workflow.document") or
                            type(item["content_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", item["content_sha256"]) or
                            item["availability"] != unchecked_availability() or
                            check_value({"schema": "stk.skill/1", **{key: item[key] for key in
                                ("id", "version", "title", "summary", "entry")}}, DEFINITION_SCHEMA)):
                        raise SkillCatalogError("invalid_definition", "Invalid user skill summary")
                    items.append(item)
                except SkillCatalogError as exc:
                    problems.append({"source": "user", "file": "catalog.sqlite", "code": "invalid_definition",
                                     "message": str(exc), "path": ""})
        return items, problems

    def publish(self, snapshot, *, publication_id, source, mode, minimum_version):
        _uuid(publication_id)
        source = _source(source)
        if mode not in ("exact", "new_version"):
            raise SkillCatalogError("invalid_params", "Publication mode must be exact or new_version")
        if type(minimum_version) is not int or not 1 <= minimum_version <= MAX_VERSION + 1:
            raise SkillCatalogError("invalid_params", "minimum_version must be a supported positive version")
        if minimum_version > MAX_VERSION:
            raise SkillCatalogError("conflict" if mode == "new_version" else "invalid_params",
                                    "User skill has exhausted its supported version range")
        snapshot = _snapshot(snapshot)
        if snapshot["content_sha256"] != source["content_sha256"]:
            raise SkillCatalogError("conflict", "Publication source digest does not match the captured skill")
        request_sha = _digest({"source": source, "mode": mode, "minimum_version": minimum_version,
                               "snapshot_sha256": snapshot["content_sha256"]})
        definition = snapshot["definition"]
        skill_id, kind = definition["id"], definition["entry"]["kind"]
        with self._connect(write=True) as db:
            previous = self._receipt(db, publication_id)
            if previous is not None:
                if previous[0] != request_sha:
                    raise SkillCatalogError("conflict", "Publication ID is already bound to a different request")
                return previous[1]
            if db.execute("SELECT 1 FROM versions WHERE skill_id=? AND kind<>? LIMIT 1", (skill_id, kind)).fetchone():
                raise SkillCatalogError("conflict", "A user skill cannot change its entry kind between versions")
            if mode == "new_version":
                maximum = db.execute("SELECT max(version) FROM versions WHERE skill_id=?", (skill_id,)).fetchone()[0] or 0
                definition["version"] = max(maximum + 1, minimum_version, definition["version"] + 1)
                if definition["version"] > MAX_VERSION:
                    raise SkillCatalogError("conflict", "User skill has exhausted its supported version range")
                snapshot["content_sha256"] = _digest({"definition": definition, "template": snapshot["template"]})
            version, sha = definition["version"], snapshot["content_sha256"]
            existing = db.execute("SELECT sha FROM versions WHERE skill_id=? AND version=?", (skill_id, version)).fetchone()
            if existing is not None:
                if existing[0] != sha:
                    raise SkillCatalogError("conflict", "This skill version already has different content; publish a new version")
                self._read_version(db, skill_id, version)
            else:
                payload = _canonical(snapshot)
                size = len(payload.encode("utf-8"))
                count, total = db.execute("SELECT count(*), coalesce(sum(length(CAST(payload AS BLOB))), 0) FROM versions").fetchone()
                if size > MAX_SNAPSHOT_BYTES or count >= MAX_VERSIONS or total + size > MAX_COLLECTION_BYTES:
                    raise SkillCatalogError("invalid_params", "User skill library exceeds 1024 versions or 64 MiB of snapshots")
                summary = _summary(describe_snapshot(snapshot))
                encoded = _canonical(summary)
                if len(encoded.encode("utf-8")) > MAX_SUMMARY_BYTES:
                    raise SkillCatalogError("invalid_params", "User skill summary exceeds 16 KiB")
                db.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (skill_id, version, kind, sha, payload, size, encoded, _digest(summary)))
            if db.execute("SELECT count(*) FROM publications").fetchone()[0] >= MAX_PUBLICATIONS:
                raise SkillCatalogError("invalid_params", "User skill library exceeds 4096 publication receipts")
            receipt = {"publication_id": publication_id, "source": source, "mode": mode,
                       "skill": {"id": skill_id, "version": version, "ref": f"{skill_id}@{version}",
                                 "content_sha256": sha, "source": "user"}, "created": existing is None}
            db.execute("INSERT INTO publications VALUES (?, ?, ?, ?)",
                       (publication_id, request_sha, _canonical(receipt), _digest(receipt)))
            return receipt
