"""Owner-only federation consent and an explicit, non-replaying update outbox.

This registry belongs in private machine state outside shared projects. Opening,
reading and recovering do not train or send anything. A publisher passed to
``send_update`` receives a detached metadata dict and immutable payload bytes;
its success means transport delivery only, never model admission or aggregation.
"""
from contextlib import contextmanager
from dataclasses import dataclass, fields
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from types import MappingProxyType
from uuid import UUID, uuid4

from suan.materials.jobs import StorageError, ordinary, private_directory
from .updates import decode_arrays, validate_layout, validate_update


MAX_GRANTS = 1024
MAX_UPDATES = 4096
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_AUDIT_BYTES = 512 * 1024 * 1024
PAGE_BYTES = 1024 * 1024
_APPLICATION_ID = 0x53544643
_STATES = {"prepared", "sending", "delivered", "uncertain"}


class ConsentError(RuntimeError):
    """The private registry is unavailable, damaged or exceeds a read budget."""


class ConsentDenied(ConsentError, PermissionError):
    """No current owner grant matches the requested local operation."""


class ConsentConflict(ConsentError):
    """A retained grant/round already contains a different original update."""


class ConsentQuota(ConsentError):
    """Retained audit capacity is exhausted; existing records remain readable."""


class ConsentOutcomeUncertain(ConsentError):
    """A sending intent exists: inspect this update; do not resend it."""
    def __init__(self, update_id):
        self.update_id = update_id
        super().__init__("Update delivery is uncertain; retain its original identity")


def _uuid(value):
    if not isinstance(value, str):
        raise ConsentDenied("Expected a canonical UUID")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise ConsentDenied("Expected a canonical UUID") from None
    return value


def _sha(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ConsentDenied("Expected a lowercase SHA-256 identity")
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ConsentDenied("Integer is outside the declared consent bounds")
    return value


def _json(value, *, budget=MAX_METADATA_BYTES):
    try:
        result = json.dumps(value, allow_nan=False, ensure_ascii=False,
                            sort_keys=True, separators=(",", ":"))
        if len(result.encode("utf-8")) > budget:
            raise ValueError
        return result
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ConsentError("Audit metadata exceeds its format or byte budget") from None


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value):
    if isinstance(value, MappingProxyType):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class Grant:
    grant_id: str
    run_id: str
    coordinator_id: str
    participant_id: str
    dataset_id: str
    dataset_sha256: str
    spec_sha256: str
    model_layout: tuple
    max_rounds: int
    active: bool

    def as_dict(self):
        return {field.name: _thaw(getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True)
class UpdateRecord:
    update_id: str
    grant_id: str
    round: int
    model_sha256: str
    state: str
    metadata: object
    layout: tuple
    payload: bytes | None = None

    def as_dict(self):
        """Return detached JSON metadata; payloads are deliberately excluded."""
        return {"update_id": self.update_id, "grant_id": self.grant_id,
                "round": self.round, "model_sha256": self.model_sha256,
                "state": self.state, "metadata": _thaw(self.metadata),
                "layout": _thaw(self.layout)}


class ConsentRegistry:
    """Private, bounded owner registry; construction itself performs no I/O.

    Authorization holds an RLock and SQLite BEGIN IMMEDIATE across the accepted
    short dispatch/publication. It must not enclose training. Revocation on
    another registry instance/process waits for accepted work, then blocks all
    subsequent work. There is no automatic garbage collection or retry.
    """
    def __init__(self, root, *, max_audit_bytes=MAX_AUDIT_BYTES):
        self.root = Path(root).absolute()
        self.path = self.root / "federation-consent.sqlite3"
        self.max_audit_bytes = _integer(max_audit_bytes, 1, MAX_AUDIT_BYTES)
        self._lock = threading.RLock()
        self._identity = None
        self._registry_id = None

    def _directory(self, *, create):
        # Dataset identifiers are opaque. Registry placement is a local owner
        # decision, never a path accepted from update metadata.
        for parent in (self.root, *self.root.parents):
            marker = parent / "project.sqlite3"
            if marker.exists() or marker.is_symlink():
                raise ConsentError("Federation consent must be outside shared projects")
        return private_directory(self.root, create=create)

    @contextmanager
    def _connect(self, *, write=False, create=False):
        with self._lock:
            db = None
            try:
                try:
                    self._directory(create=create)
                except FileNotFoundError:
                    yield None
                    return
                created = False
                if create:
                    try:
                        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
                        os.close(fd)
                        created = True
                    except FileExistsError:
                        pass
                try:
                    info = ordinary(self.path)
                except FileNotFoundError:
                    yield None
                    return
                if os.name != "nt" and info.st_mode & 0o077:
                    raise ConsentError("Federation consent registry must be owner-private")
                identity = (info.st_dev, info.st_ino)
                if self._identity is not None and identity != self._identity:
                    raise ConsentError("Federation consent registry was replaced")
                db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                     uri=True, timeout=15, isolation_level=None)
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys=ON")
                if write:
                    db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                if created:
                    self._initialize(db)
                if (db.execute("PRAGMA application_id").fetchone()[0] != _APPLICATION_ID
                        or db.execute("PRAGMA user_version").fetchone()[0] != 1):
                    raise ConsentError("Unsupported federation consent registry")
                rows = db.execute("SELECT registry_id FROM registry").fetchall()
                if len(rows) != 1:
                    raise ConsentError("Invalid federation consent registry identity")
                registry_id = _uuid(rows[0][0])
                if self._registry_id is not None and registry_id != self._registry_id:
                    raise ConsentError("Federation consent registry was replaced")
                now = ordinary(self.path)
                if (now.st_dev, now.st_ino) != identity:
                    raise ConsentError("Federation consent registry changed while opening")
                self._identity, self._registry_id = identity, registry_id
                yield db
                now = ordinary(self.path)
                if (now.st_dev, now.st_ino) != identity:
                    raise ConsentError("Federation consent registry changed during operation")
                db.commit()
            except ConsentError:
                raise
            except (sqlite3.Error, OSError, StorageError) as exc:
                raise ConsentError("Federation consent storage failed: " + type(exc).__name__) from None
            finally:
                if db is not None:
                    if db.in_transaction:
                        db.rollback()
                    db.close()

    @staticmethod
    def _initialize(db):
        db.execute("CREATE TABLE registry (registry_id TEXT NOT NULL)")
        db.execute("INSERT INTO registry VALUES (?)", (str(uuid4()),))
        db.execute("CREATE TABLE grants (grant_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, "
                   "coordinator_id TEXT NOT NULL, participant_id TEXT NOT NULL, dataset_id TEXT NOT NULL, "
                   "dataset_sha256 TEXT NOT NULL, spec_sha256 TEXT NOT NULL, model_layout TEXT NOT NULL, "
                   "layout_sha256 TEXT NOT NULL, max_rounds INTEGER NOT NULL, "
                   "active INTEGER NOT NULL CHECK(active IN (0,1)))")
        db.execute("CREATE TABLE updates (update_id TEXT PRIMARY KEY, grant_id TEXT NOT NULL "
                   "REFERENCES grants(grant_id), round INTEGER NOT NULL, model_sha256 TEXT NOT NULL, "
                   "metadata TEXT NOT NULL, layout TEXT NOT NULL, payload BLOB NOT NULL, "
                   "original_sha256 TEXT NOT NULL, state TEXT NOT NULL, UNIQUE(grant_id,round))")
        db.execute(f"PRAGMA application_id={_APPLICATION_ID}")
        db.execute("PRAGMA user_version=1")

    @staticmethod
    def _grant(db, grant_id):
        row = None if db is None else db.execute(
            "SELECT grant_id,run_id,coordinator_id,participant_id,dataset_id,dataset_sha256,spec_sha256,"
            "max_rounds,active,layout_sha256,length(CAST(model_layout AS BLOB)) AS layout_length,"
            f"CASE WHEN length(CAST(model_layout AS BLOB))<={MAX_METADATA_BYTES} THEN model_layout END "
            "AS model_layout FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
        if row is None:
            return None
        _uuid(row["grant_id"]), _uuid(row["run_id"]), _uuid(row["dataset_id"])
        for name in ("coordinator_id", "participant_id", "dataset_sha256", "spec_sha256"):
            _sha(row[name])
        _integer(row["max_rounds"], 1, 10000)
        if row["active"] not in (0, 1):
            raise ConsentError("Invalid grant state")
        try:
            if row["layout_length"] > MAX_METADATA_BYTES:
                raise ConsentError("Owner model layout exceeds its byte budget")
            layout = validate_layout(json.loads(row["model_layout"]))
            encoded_layout = _json(layout)
            if hashlib.sha256(encoded_layout.encode("utf-8")).hexdigest() != _sha(row["layout_sha256"]):
                raise ConsentError("Retained owner model layout is damaged")
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ConsentError("Retained owner model layout is damaged") from None
        return Grant(**{field.name: (_freeze(layout) if field.name == "model_layout"
                                     else bool(row[field.name]) if field.name == "active"
                                     else row[field.name]) for field in fields(Grant)})

    @staticmethod
    def _authorize(grant, *, coordinator_id, run_id, round, participant_id,
                   dataset_sha256, spec_sha256):
        _integer(round, 1, 10000)
        if (grant is None or not grant.active or grant.coordinator_id != _sha(coordinator_id)
                or grant.run_id != _uuid(run_id) or round > grant.max_rounds
                or grant.participant_id != _sha(participant_id)
                or grant.dataset_sha256 != _sha(dataset_sha256)
                or grant.spec_sha256 != _sha(spec_sha256)):
            raise ConsentDenied("No current grant matches this update")
        return grant

    def grant(self, run_id, *, coordinator_id, participant_id, dataset_id,
              dataset_sha256, spec_sha256, model_layout, max_rounds):
        """Explicit owner consent binds exact ordered array names, dtypes and shapes."""
        layout = _json(validate_layout(model_layout))
        grant = Grant(str(uuid4()), _uuid(run_id), _sha(coordinator_id), _sha(participant_id),
                      _uuid(dataset_id), _sha(dataset_sha256), _sha(spec_sha256),
                      _freeze(json.loads(layout)), _integer(max_rounds, 1, 10000), True)
        with self._connect(write=True, create=True) as db:
            if db.execute("SELECT count(*) FROM grants").fetchone()[0] >= MAX_GRANTS:
                raise ConsentQuota("Retained grant quota is exhausted")
            db.execute("INSERT INTO grants VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (grant.grant_id, grant.run_id, grant.coordinator_id, grant.participant_id,
                        grant.dataset_id, grant.dataset_sha256, grant.spec_sha256, layout,
                        hashlib.sha256(layout.encode("utf-8")).hexdigest(), grant.max_rounds, grant.active))
        return grant

    def get_grant(self, grant_id):
        with self._connect() as db:
            return self._grant(db, _uuid(grant_id))

    def revoke(self, grant_id):
        with self._connect(write=True) as db:
            grant = self._grant(db, _uuid(grant_id))
            if grant is None:
                raise ConsentDenied("No such owner grant")
            db.execute("UPDATE grants SET active=0 WHERE grant_id=?", (grant_id,))
            return self._grant(db, grant_id)

    @contextmanager
    def authorized(self, grant_id, *, coordinator_id, run_id, round, participant_id,
                   dataset_sha256, spec_sha256):
        with self._connect(write=True) as db:
            yield self._authorize(self._grant(db, _uuid(grant_id)), coordinator_id=coordinator_id,
                                  run_id=run_id, round=round, participant_id=participant_id,
                                  dataset_sha256=dataset_sha256, spec_sha256=spec_sha256)

    @staticmethod
    def _original(metadata, layout, model_sha256):
        return hashlib.sha256(_json({"metadata": metadata, "layout": layout,
                                     "model_sha256": model_sha256},
                                    budget=2 * MAX_METADATA_BYTES + 256).encode("utf-8")).hexdigest()

    def _record(self, db, row, *, include_payload=False):
        if row is None:
            return None
        grant = self._grant(db, row["grant_id"])
        if grant is None or row["state"] not in _STATES:
            raise ConsentError("Invalid retained update")
        try:
            metadata, layout = json.loads(row["metadata"]), validate_layout(json.loads(row["layout"]))
            metadata = validate_update(metadata, run_id=grant.run_id, round=row["round"],
                                       participant_id=grant.participant_id, model_sha256=row["model_sha256"],
                                       spec_sha256=grant.spec_sha256, dataset_sha256=grant.dataset_sha256,
                                       grant_id=grant.grant_id)
            if (layout != _thaw(grant.model_layout) or self._original(metadata, layout, row["model_sha256"])
                    != row["original_sha256"]):
                raise ConsentError("Retained audit binding is damaged")
            payload = row["payload"] if include_payload else None
            if include_payload:
                self._check_payload(metadata, payload, expected_layout=_thaw(grant.model_layout))
            return UpdateRecord(_uuid(row["update_id"]), grant.grant_id, row["round"],
                                row["model_sha256"], row["state"], _freeze(metadata),
                                _freeze(layout), payload)
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ConsentError("Retained audit data is damaged") from None

    @staticmethod
    def _select(db, update_id, *, payload=False):
        if db is None:
            return None
        payload_column = (f"CASE WHEN length(payload)<={MAX_PAYLOAD_BYTES} THEN payload END"
                          if payload else "NULL")
        metadata_column = (f"CASE WHEN length(CAST(metadata AS BLOB))<={MAX_METADATA_BYTES} "
                           "THEN metadata END AS metadata")
        layout_column = (f"CASE WHEN length(CAST(layout AS BLOB))<={MAX_METADATA_BYTES} "
                         "THEN layout END AS layout")
        columns = ("update_id,grant_id,round,model_sha256," + metadata_column + "," + layout_column
                   + ",original_sha256,state,"
                   + payload_column + " AS payload")
        row = db.execute(f"SELECT {columns},length(CAST(metadata AS BLOB)) AS metadata_length,"
                         "length(CAST(layout AS BLOB)) AS layout_length,length(payload) AS payload_length "
                         "FROM updates WHERE update_id=?", (update_id,)).fetchone()
        if row is not None and (row["metadata_length"] > MAX_METADATA_BYTES
                                or row["layout_length"] > MAX_METADATA_BYTES
                                or row["payload_length"] > MAX_PAYLOAD_BYTES):
            raise ConsentError("Retained audit exceeds its byte budget")
        return row

    @staticmethod
    def _check_payload(metadata, payload, *, expected_layout):
        if type(payload) is not bytes or len(payload) > MAX_PAYLOAD_BYTES:
            raise ConsentError("Update payload exceeds its byte budget")
        decoded = decode_arrays(payload, expected_kind="delta", expected_layout=expected_layout)
        if (decoded["sha256"] != metadata["update_sha256"]
                or decoded["bytes"] != metadata["update_bytes"]):
            raise ConsentError("Actual update bytes do not match the metadata")
        return decoded["layout"]

    def prepare_update(self, grant_id, metadata, payload, *, model_sha256):
        """Freeze one locally validated delta per grant/round before any send.

        ``model_sha256`` is the trusted local expected model, supplied separately
        from wire metadata and retained as a binding. No model or dataset paths
        are read here. Deltas must match the exact layout frozen by the owner,
        not a layout claimed by the delta. A withdrawn grant never permits a new
        prepare operation.
        """
        model_sha256 = _sha(model_sha256)
        if not isinstance(metadata, dict):
            raise ConsentError("Expected detached update metadata")
        _json(metadata)
        with self._connect(write=True) as db:
            grant = self._grant(db, _uuid(grant_id))
            if grant is None:
                raise ConsentDenied("No such owner grant")
            metadata = validate_update(metadata, run_id=grant.run_id, round=metadata.get("round"),
                                       participant_id=grant.participant_id, model_sha256=model_sha256,
                                       spec_sha256=grant.spec_sha256, dataset_sha256=grant.dataset_sha256,
                                       grant_id=grant.grant_id)
            self._authorize(grant, coordinator_id=grant.coordinator_id, run_id=grant.run_id,
                            round=metadata["round"], participant_id=grant.participant_id,
                            dataset_sha256=grant.dataset_sha256, spec_sha256=grant.spec_sha256)
            layout = self._check_payload(metadata, payload, expected_layout=_thaw(grant.model_layout))
            encoded, encoded_layout = _json(metadata), _json(layout)
            original = self._original(metadata, layout, model_sha256)
            existing = db.execute("SELECT update_id,original_sha256 FROM updates WHERE grant_id=? AND round=?",
                                  (grant_id, metadata["round"])).fetchone()
            if existing is not None:
                if existing["original_sha256"] != original:
                    raise ConsentConflict("This grant/round already has another original update")
                return self._record(db, self._select(db, existing["update_id"], payload=True), include_payload=True)
            count, size = db.execute("SELECT count(*),coalesce(sum(length(payload)+length(CAST(metadata AS BLOB))"
                                     "+length(CAST(layout AS BLOB))),0) "
                                     "FROM updates").fetchone()
            if (count >= MAX_UPDATES or size + len(payload) + len(encoded.encode("utf-8"))
                    + len(encoded_layout.encode("utf-8")) > self.max_audit_bytes):
                raise ConsentQuota("Retained update audit quota is exhausted")
            update_id = str(uuid4())
            db.execute("INSERT INTO updates VALUES (?,?,?,?,?,?,?,?,?)", (update_id, grant_id,
                       metadata["round"], model_sha256, encoded, encoded_layout, payload, original, "prepared"))
            return self._record(db, self._select(db, update_id, payload=True), include_payload=True)

    def get_update(self, update_id, *, include_payload=False):
        with self._connect() as db:
            return self._record(db, self._select(db, _uuid(update_id), payload=include_payload),
                                include_payload=include_payload)

    def _sending_grant(self, db, record, coordinator_id):
        metadata = record.metadata
        return self._authorize(self._grant(db, record.grant_id), coordinator_id=coordinator_id,
                               run_id=metadata["run_id"], round=record.round,
                               participant_id=metadata["participant_id"],
                               dataset_sha256=metadata["dataset_sha256"], spec_sha256=metadata["spec_sha256"])

    def _mark(self, db, update_id, state):
        db.execute("UPDATE updates SET state=? WHERE update_id=?", (state, update_id))

    def send_update(self, update_id, *, coordinator_id, deliver):
        """Explicitly call a trusted short publisher at most once for this ID.

        The separately committed sending intent survives process death. A new
        transaction rechecks the current grant and exact audit bytes, and spans
        the accepted callback so revoke waits. Callback/bookkeeping failures
        remain uncertain; neither repeat calls nor recover invoke the publisher.
        """
        update_id, coordinator_id = _uuid(update_id), _sha(coordinator_id)
        if not callable(deliver):
            raise ConsentError("Expected a trusted publisher callback")
        intent_started = False
        try:
            with self._connect(write=True) as db:
                record = self._record(db, self._select(db, update_id, payload=True), include_payload=True)
                if record is None:
                    raise ConsentDenied("No such retained update")
                if self._grant(db, record.grant_id).coordinator_id != coordinator_id:
                    raise ConsentDenied("Publisher coordinator does not match owner consent")
                if record.state == "delivered":
                    return record
                if record.state != "prepared":
                    raise ConsentOutcomeUncertain(update_id)
                self._sending_grant(db, record, coordinator_id)
                intent_started = True
                self._mark(db, update_id, "sending")
        except Exception:
            if intent_started:
                raise ConsentOutcomeUncertain(update_id) from None
            raise
        try:
            with self._connect(write=True) as db:
                record = self._record(db, self._select(db, update_id, payload=True), include_payload=True)
                if record is None or record.state != "sending":
                    raise ConsentOutcomeUncertain(update_id)
                self._sending_grant(db, record, coordinator_id)
                deliver(_thaw(record.metadata), record.payload)
                self._mark(db, update_id, "delivered")
                result = self._record(db, self._select(db, update_id), include_payload=False)
            return result
        except Exception:
            try:
                with self._connect(write=True) as db:
                    record = self._record(db, self._select(db, update_id))
                    if record is not None and record.state == "sending":
                        self._mark(db, update_id, "uncertain")
            except Exception:
                pass
            raise ConsentOutcomeUncertain(update_id) from None

    def recover(self, update_id):
        """Mark an interrupted sending intent uncertain; never call a publisher."""
        with self._connect(write=True) as db:
            record = self._record(db, self._select(db, _uuid(update_id)))
            if record is not None and record.state == "sending":
                self._mark(db, update_id, "uncertain")
                return self._record(db, self._select(db, update_id))
            return record

    def list_grants(self, *, offset=0, limit=50):
        return self._page("grants", offset, limit)

    def list_updates(self, *, offset=0, limit=50):
        return self._page("updates", offset, limit)

    def _page(self, table, offset, limit):
        _integer(offset, 0, MAX_UPDATES)
        _integer(limit, 1, 100)
        records, used = [], 0
        with self._connect() as db:
            total = 0 if db is None else db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            key = "grant_id" if table == "grants" else "update_id"
            ids = [] if db is None else db.execute(f"SELECT {key} FROM {table} ORDER BY rowid LIMIT ? OFFSET ?",
                                                   (limit, offset)).fetchall()
            for row in ids:
                record = (self._grant(db, row[0]) if table == "grants"
                          else self._record(db, self._select(db, row[0])))
                size = len(json.dumps(record.as_dict(), ensure_ascii=False, allow_nan=False).encode("utf-8"))
                if used + size + 1024 > PAGE_BYTES:
                    break
                records.append(record)
                used += size
        next_offset = offset + len(records)
        return {table: tuple(records), "offset": offset, "total": total,
                "next_offset": next_offset if next_offset < total else None}
