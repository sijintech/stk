"""Private immutable PDF versions and exact local lexical citation evidence.

There is no shared/public corpus or semantic encoder here. Authorization is an
explicit owner's per-version assertion with its evidence, not an inferred legal
opinion, DOI lookup, public label, or permission to send content elsewhere.
"""
from contextlib import contextmanager
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
import threading
import time
from uuid import UUID, uuid4, uuid5

from ._io import LiteratureError, MAX_PDF_BYTES, directory, fail, inspect_pdf, opened, ordinary, stamp
from .pdf import canonical, checksum, extract_pdf, validate_extraction

MAX_VERSIONS = 128
MAX_OPERATIONS = 4096
MAX_DECLARED_SOURCE_BYTES = 256 * 1024 * 1024
MAX_PARAGRAPHS = 10000
MAX_DB_PAGES = 32768  # 128 MiB database pages; not a whole-directory/RSS claim.
APPLICATION_ID = 0x53544C49  # STLI; not the project or Runtime database format.
SCHEMA_VERSION = 1
MAX_DB_BYTES = 128 * 1024 * 1024
MAX_JOURNAL_BYTES = 2 * MAX_DB_BYTES + 1024 * 1024
MAX_CITATIONS = 256
MAX_CITATION_CHARACTERS = 65536
MAX_CITATION_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CITATION_EVIDENCE_BYTES = 16 * 1024 * 1024
_JOURNAL_MAGIC = bytes.fromhex("d9d505f920a163d7")
# Darwin's flock and fcntl locks share an inode lock list. A whole-file flock
# on the DB can therefore block SQLite's own byte-range locks in this process.
# Lease the stable corpus directory there; retain Linux's existing DB lease.
_DIRECTORY_LEASE = sys.platform == "darwin"
_SQL_TOKEN = re.compile(r''''(?:''|[^'])*'|"(?:""|[^"])*"|`(?:``|[^`])*`|\[[^\]]*\]|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]''')


class _DatabaseGate:
    def __init__(self):
        self.lock, self.connections, self.leased = threading.RLock(), 0, False


_DATABASE_GATE = _DatabaseGate()


def _schema(db):
    return tuple((kind, name, table, None if sql is None else tuple(_SQL_TOKEN.findall(sql)))
                 for kind, name, table, sql in db.execute(
                     "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE substr(lower(name),1,7) != 'sqlite_' ORDER BY type,name"))


@lru_cache(maxsize=1)
def _schemas():
    # Generate only SQLite's physical spelling of this fixed, versioned schema.
    # No corpus/model code or mutable file participates in the definition.
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(_SCHEMA_SQL)
        base = _schema(db)
        db.executescript("""
            CREATE TABLE dense_meta(id INTEGER PRIMARY KEY CHECK(id=1),current_generation TEXT NOT NULL);
            CREATE TABLE dense_generations(id TEXT PRIMARY KEY,manifest TEXT NOT NULL);
            CREATE TABLE dense_windows(generation TEXT NOT NULL REFERENCES dense_generations(id),
                key TEXT NOT NULL,position INTEGER NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(generation,key));
        """)
        return base, _schema(db)
    finally:
        db.close()
_SCHEMA_SQL = """
                    CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL, identity TEXT NOT NULL);
                    CREATE TABLE operations (id TEXT PRIMARY KEY, kind TEXT NOT NULL, request TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT);
                    CREATE TABLE versions (id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
                        source_sha256 TEXT NOT NULL, source_bytes INTEGER NOT NULL, title TEXT NOT NULL,
                        authorization TEXT NOT NULL, active INTEGER NOT NULL, current_extraction TEXT, import_operation TEXT NOT NULL);
                    CREATE TABLE extractions (version_id TEXT NOT NULL REFERENCES versions(id), id TEXT NOT NULL,
                        proof TEXT NOT NULL, PRIMARY KEY(version_id,id));
                    CREATE TABLE pages (version_id TEXT NOT NULL, extraction_id TEXT NOT NULL, page_index INTEGER NOT NULL,
                        evidence TEXT NOT NULL, PRIMARY KEY(version_id,extraction_id,page_index));
                    CREATE TABLE paragraphs (key TEXT PRIMARY KEY, version_id TEXT NOT NULL, extraction_id TEXT NOT NULL,
                        id TEXT NOT NULL, page_index INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
                        text TEXT NOT NULL, text_sha256 TEXT NOT NULL);
                    CREATE VIRTUAL TABLE paragraph_fts USING fts5(key UNINDEXED,text,tokenize='trigram');
"""
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _uuid(value):
    if type(value) is not str:
        fail()
    try:
        if str(UUID(value)) != value: fail()
    except (ValueError, AttributeError): fail()
    return value


def _text(value, maximum):
    if type(value) is not str or len(value) > maximum or not value.strip() or "\0" in value:
        fail()
    try:
        if len(value.encode("utf-8")) > maximum: fail()
    except UnicodeEncodeError:
        fail()
    return value


def _authorization(value):
    if (type(value) is not dict or set(value) != {"basis", "evidence", "approved_by"}
            or type(value["basis"]) is not str
            or value["basis"] not in {"open_access", "self_authored"}):
        fail("authorization_required", "Explicit open-access or self-authored authorization is required")
    _text(value["evidence"], 2048); _text(value["approved_by"], 128)
    return json.loads(canonical(value))


def _page(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50: fail()


class Library:
    """One explicit app-owned corpus; reads never replay logical operations.

    All Library processes cooperate through an inode lease on POSIX. Direct
    SQLite writers during a Library operation are unsupported, not sandboxed.
    A known interrupted database can undergo physical rollback after private
    verification; platforms without the proven lease fail closed on recovery.
    No process gate or lease spans PDF parsing or model inference.
    """
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or ".." in self.root.parts: fail()
        self.path = self.root / "literature.sqlite3"
        self._active, self._lock = set(), threading.Lock()
        # Global within this process: aliases/case-insensitive volumes cannot
        # open/close a raw DB descriptor while another Library holds SQLite locks.
        self._gate = _DATABASE_GATE
        self._database_identity = None

    def _file_identity(self, *, initializing=False, header=True):
        """Check format before SQLite may recover, create journals or write DDL."""
        directory(self.root)
        named = ordinary(self.path)
        if named.st_nlink != 1 or named.st_size > MAX_DB_BYTES:
            fail("storage_error", "Unsupported local literature database file")
        if not header:
            return named.st_dev, named.st_ino
        if self._gate.connections:
            fail("busy", "Local literature database is already open")
        self._journal_paths()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags | getattr(os, "O_NONBLOCK", 0))
        try:
            handle = os.fstat(fd)
            physical = (handle.st_dev, handle.st_ino)
            if not stat.S_ISREG(handle.st_mode) or physical != (named.st_dev, named.st_ino):
                fail("storage_error", "Local literature database identity changed")
            header = os.read(fd, 100)
            if not initializing and (len(header) != 100 or header[:16] != b"SQLite format 3\0"
                    or header[18:20] != b"\1\1"
                    or int.from_bytes(header[68:72], "big") != APPLICATION_ID
                    or int.from_bytes(header[60:64], "big") != SCHEMA_VERSION):
                fail("storage_error", "Unrecognized local literature database format")
            after = ordinary(self.path)
            if physical != (after.st_dev, after.st_ino):
                fail("storage_error", "Local literature database identity changed")
            return physical
        finally:
            os.close(fd)

    def _journal_paths(self):
        for suffix in ("-wal", "-shm"):
            path = self.path.with_name(self.path.name + suffix)
            if path.exists() or path.is_symlink():
                fail("storage_error", "Unsupported local literature journal mode")
        journal = self.path.with_name(self.path.name + "-journal")
        if journal.exists() or journal.is_symlink():
            info = ordinary(journal)
            if info.st_nlink != 1 or info.st_size > MAX_JOURNAL_BYTES:
                fail("storage_error", "Unsupported local literature journal file")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(journal, flags), "rb") as stream:
                initial = os.fstat(stream.fileno())
                if not stat.S_ISREG(initial.st_mode) or stamp(initial)[:-1] != stamp(info)[:-1]: fail()
                header = stream.read(8)
                tail = b""
                if initial.st_size >= 8:
                    stream.seek(-8, os.SEEK_END); tail = stream.read(8)
                if tail == _JOURNAL_MAGIC or header not in (b"", b"\0" * 8, _JOURNAL_MAGIC):
                    fail("storage_error", "Unsupported local literature recovery journal")
                if stamp(initial) != stamp(os.fstat(stream.fileno())): fail()
            if stamp(info) != stamp(ordinary(journal)): fail()
        return journal

    def _copy_file(self, source, maximum, target=None):
        # The process gate excludes ALL Library connections to this path. A
        # separate raw descriptor close must never release SQLite's POSIX locks.
        if self._gate.connections: fail("busy", "Local literature database is already open")
        before = ordinary(source)
        if before.st_nlink != 1 or before.st_size > maximum: fail()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(source, flags), "rb") as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode) or stamp(before)[:-1] != stamp(initial)[:-1]: fail()
            output = None if target is None else target.open("xb")
            try:
                digest, count = hashlib.sha256(), 0
                while block := stream.read(1024 * 1024):
                    count += len(block)
                    if count > maximum: fail()
                    digest.update(block)
                    if output is not None: output.write(block)
                if output is not None: output.flush()
                if stamp(initial) != stamp(os.fstat(stream.fileno())): fail()
            finally:
                if output is not None: output.close()
        if stamp(before) != stamp(ordinary(source)) or count != before.st_size: fail()
        return stamp(before), digest.hexdigest(), count

    def _acquire_lease(self):
        if os.name != "posix":
            return None  # Cold SQLite operations work; physical recovery is unproven.
        import fcntl
        target = self.root if _DIRECTORY_LEASE else self.path
        if _DIRECTORY_LEASE:
            directory(target)
            named = target.lstat()
        else:
            named = ordinary(target)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if _DIRECTORY_LEASE:
            flags |= getattr(os, "O_DIRECTORY", 0)
        fd = os.open(target, flags)
        try:
            opened = os.fstat(fd)
            valid = stat.S_ISDIR(opened.st_mode) if _DIRECTORY_LEASE else (
                stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1)
            if (not valid
                    or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)): fail()
            until = time.monotonic() + 15
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); break
                except BlockingIOError:
                    if time.monotonic() >= until: fail("busy", "Local literature database is busy")
                    time.sleep(.01)
            if _DIRECTORY_LEASE:
                directory(target)
                after = target.lstat()
            else:
                after = ordinary(target)
            if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino): fail()
            self._gate.leased = True
            return fd
        except BaseException:
            os.close(fd); raise

    def _same_pair(self, physical, ticket):
        self._journal_paths()
        journal = self.path.with_name(self.path.name + "-journal")
        if (self._file_identity() != physical
                or self._copy_file(self.path, MAX_DB_BYTES) != ticket[0]
                or self._copy_file(journal, MAX_JOURNAL_BYTES) != ticket[1]):
            fail("storage_error", "Local literature recovery inputs changed")

    def _preflight(self, physical):
        probe = None
        try:
            probe = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=15)
            self._gate.connections += 1; probe.row_factory = sqlite3.Row
            probe.execute("BEGIN")
            self._bind_database(probe, physical)
            return False
        except sqlite3.Error as error:
            if getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_READONLY_ROLLBACK:
                raise
        finally:
            if probe is not None:
                probe.close(); self._gate.connections -= 1
        # Only SQLite's exact cold rollback-required signal reaches this path.
        # BUSY, WAL, malformed data and normal readonly failures never do.
        if not self._gate.leased:
            fail("unsupported_recovery", "Local literature recovery requires a supported exclusive lease")
        journal = self._journal_paths()
        with tempfile.TemporaryDirectory(prefix="stk-literature-recovery-") as name:
            copied = Path(name) / self.path.name
            db_before = self._copy_file(self.path, MAX_DB_BYTES, copied)
            copied_journal = copied.with_name(journal.name)
            journal_before = self._copy_file(journal, MAX_JOURNAL_BYTES, copied_journal)
            if (self._copy_file(copied, MAX_DB_BYTES)[1:] != db_before[1:]
                    or self._copy_file(copied_journal, MAX_JOURNAL_BYTES)[1:] != journal_before[1:]):
                fail("storage_error", "Local literature recovery copy changed")
            with copied_journal.open("rb") as stream:
                header = stream.read(28); stream.seek(-8, os.SEEK_END); tail = stream.read(8)
            if len(header) != 28 or header[:8] != _JOURNAL_MAGIC or tail == _JOURNAL_MAGIC:
                fail("storage_error", "Unsupported local literature recovery journal")
            # A super-journal trailer can name files outside the private copy.
            # Never ask SQLite to recover such a journal or a WAL family.
            sector, page = int.from_bytes(header[20:24], "big"), int.from_bytes(header[24:28], "big")
            with copied.open("rb") as stream:
                stream.seek(16); size = int.from_bytes(stream.read(2), "big")
            database_page = 65536 if size == 1 else size
            if (sector < 512 or sector > 65536 or sector & (sector - 1)
                    or page < 512 or page > 65536 or page & (page - 1)
                    or page != database_page or int.from_bytes(header[8:12], "big") == 0
                    or int.from_bytes(header[16:20], "big") * page > MAX_DB_BYTES): fail()
            def unchanged():
                self._same_pair(physical, (db_before, journal_before))
            unchanged()
            # Recovery is first confined to a cold, bounded, checked private pair.
            # No immutable=1 assertion and no original SQLite connection is open.
            db = sqlite3.connect(copied.as_uri() + "?mode=rw", uri=True, timeout=15)
            try:
                db.row_factory = sqlite3.Row
                self._bind_database(db, physical)
                if [r[0] for r in db.execute("PRAGMA quick_check")] != ["ok"]: fail()
            finally:
                db.close()
            unchanged()
        # The caller may now permit SQLite's own original-file rollback and must
        # revalidate the same physical/logical identity before any logical write.
        return db_before, journal_before

    def _bind_database(self, db, physical):
        if (db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION):
            fail("storage_error", "Unrecognized local literature database format")
        if _schema(db) not in _schemas():
            fail("storage_error", "Unrecognized local literature database schema")
        row = db.execute("SELECT identity,generation FROM meta WHERE id=1").fetchone()
        if row is None or type(row["generation"]) is not int or row["generation"] < 0:
            fail("storage_error", "Local literature database metadata is inconsistent")
        identity = (*physical, _uuid(row["identity"]))
        with self._lock:
            if self._database_identity is not None and self._database_identity != identity:
                fail("storage_error", "Local literature database identity changed; reopen explicitly")
            self._database_identity = identity

    @contextmanager
    def _db(self, *, write=False):
        with self._gate.lock:
            if self._gate.connections: fail("busy", "Local literature database is already open")
            with self._db_locked(write=write) as db:
                yield db

    @contextmanager
    def _db_locked(self, *, write=False):
        db = lease = None
        try:
            created = False
            if not self.path.exists() and not self.path.is_symlink():
                with self._lock:
                    if self._database_identity is not None:
                        fail("storage_error", "Known local literature database is missing")
                if not write:
                    yield None; return
                directory(self.root, create=True)
                try:
                    fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600)
                except FileExistsError:
                    pass  # Another creator owns initialization; never adopt an empty file.
                else:
                    try:
                        info = os.fstat(fd); expected = (info.st_dev, info.st_ino)
                    finally:
                        os.close(fd)
                    created = True
            lease = self._acquire_lease()
            physical = self._file_identity(initializing=created)
            if created and physical != expected:
                fail("storage_error", "New local literature database was replaced")
            with self._lock:
                if self._database_identity is not None and physical != self._database_identity[:2]:
                    fail("storage_error", "Local literature database identity changed; reopen explicitly")
            recover = False if created else self._preflight(physical)
            if self._file_identity(initializing=created) != physical:
                fail("storage_error", "Local literature database identity changed")
            if recover:
                self._same_pair(physical, recover)
            # Never implicitly create/reset a database through SQLite's rwc mode.
            # Preflight proved identity even if a read needs physical rollback.
            mode = "rw" if write or recover else "ro"
            db = sqlite3.connect(self.path.as_uri() + "?mode=" + mode, uri=True, timeout=15)
            self._gate.connections += 1
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            if created:
                db.execute("PRAGMA synchronous=FULL")
                pages = min(MAX_DB_PAGES, MAX_DB_BYTES // db.execute("PRAGMA page_size").fetchone()[0])
                db.execute(f"PRAGMA max_page_count={pages}")
                db.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA_SQL)
                db.execute("INSERT INTO meta VALUES(1,0,?)", (str(uuid4()),))
                db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                if self._file_identity(header=False) != physical:
                    fail("storage_error", "New local literature database was replaced")
                db.commit()
            if self._file_identity(header=False) != physical:
                fail("storage_error", "Local literature database identity changed")
            # Validate metadata before any existing database receives write settings.
            self._bind_database(db, physical)
            if write:
                db.execute("PRAGMA synchronous=FULL")
                pages = min(MAX_DB_PAGES, MAX_DB_BYTES // db.execute("PRAGMA page_size").fetchone()[0])
                db.execute(f"PRAGMA max_page_count={pages}")
            else:
                db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if self._file_identity(header=False) != physical:
                fail("storage_error", "Local literature database identity changed")
            self._bind_database(db, physical)
            yield db
            if self._file_identity(header=False) != physical:
                fail("storage_error", "Local literature database identity changed")
            self._bind_database(db, physical)
            if write: db.commit()
            if self._file_identity(header=False) != physical:
                fail("storage_error", "Local literature database identity changed")
        except LiteratureError:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            fail("storage_error", "Local literature state is unavailable or inconsistent")
        finally:
            if db is not None:
                db.close(); self._gate.connections -= 1
            if lease is not None:
                # Keep the corpus lease through SQLite close. On Linux this also
                # avoids closing any raw DB descriptor while SQLite owns locks.
                os.close(lease); self._gate.leased = False

    @staticmethod
    def _generation(db, *, advance=False):
        if db is None: return 0
        if advance: db.execute("UPDATE meta SET generation=generation+1 WHERE id=1")
        return db.execute("SELECT generation FROM meta WHERE id=1").fetchone()[0]

    def info(self):
        with self._db() as db:
            return {"generation": self._generation(db), "versions": 0 if db is None else db.execute("SELECT count(*) FROM versions").fetchone()[0],
                    "database_id": None if db is None else db.execute("SELECT identity FROM meta WHERE id=1").fetchone()[0],
                    "corpus": "local", "semantic_retrieval": False}

    def _operation(self, db, identity):
        row = None if db is None else db.execute("SELECT * FROM operations WHERE id=?", (identity,)).fetchone()
        if row is None: return None
        request = json.loads(row["request"])
        if checksum({"kind": row["kind"], "request": request}) != row["request_sha256"]: fail()
        with self._lock: active = identity in self._active
        return {"operation_id": identity, "kind": row["kind"], "request_sha256": row["request_sha256"],
                "state": "uncertain" if row["state"] == "running" and not active else row["state"],
                "receipt": None if row["receipt"] is None else json.loads(row["receipt"])}

    def operation(self, operation_id):
        _uuid(operation_id)
        with self._db() as db: return self._operation(db, operation_id)

    def _reserve(self, operation_id, kind, request):
        _uuid(operation_id)
        encoded = canonical(request)
        if len(encoded) > 8192: fail()
        digest = checksum({"kind": kind, "request": request})
        with self._db(write=True) as db:
            previous = self._operation(db, operation_id)
            if previous is not None:
                if previous["kind"] != kind or previous["request_sha256"] != digest:
                    fail("operation_conflict", "Operation identity is already bound to another request")
                return previous
            if db.execute("SELECT count(*) FROM operations").fetchone()[0] >= MAX_OPERATIONS:
                fail("operation_budget", "Literature operation journal is full")
            if kind == "import":
                reserved = db.execute("SELECT coalesce(sum(json_extract(request,'$.source_bytes')),0) FROM operations WHERE kind='import'").fetchone()[0]
                if reserved + request["source_bytes"] > MAX_DECLARED_SOURCE_BYTES:
                    fail("source_budget", "Literature source reservation budget is full")
            db.execute("INSERT INTO operations VALUES(?,?,?,?,?,NULL)", (operation_id, kind, encoded.decode(), digest, "running"))
        with self._lock: self._active.add(operation_id)
        return None

    def _finish(self, db, operation_id, receipt):
        encoded = canonical(receipt).decode()
        row = db.execute("SELECT state,receipt FROM operations WHERE id=?", (operation_id,)).fetchone()
        if row is None: fail()
        if row["state"] == "completed":
            if row["receipt"] != encoded:
                fail("operation_conflict", "Completed literature receipt cannot be replaced")
            return
        if row["state"] != "running" or row["receipt"] is not None: fail()
        db.execute("UPDATE operations SET state='completed',receipt=? WHERE id=?", (encoded, operation_id))

    def _inactive(self, operation_id):
        with self._lock: self._active.discard(operation_id)

    def _object(self, sha):
        if type(sha) is not str or not _SHA.fullmatch(sha): fail()
        return self.root / "objects" / (sha + ".pdf")

    def _verify_object(self, sha, size):
        if inspect_pdf(self._object(sha)) != {"sha256": sha, "bytes": size}:
            fail("source_changed", "Frozen PDF bytes are missing or changed")

    def _publish_source(self, source, sha, size):
        objects = directory(self.root / "objects", create=True)
        fd, name = tempfile.mkstemp(prefix="capture-", suffix=".part", dir=objects)
        temporary = Path(name)
        try:
            h, count = hashlib.sha256(), 0
            with os.fdopen(fd, "wb") as output, opened(source) as (input_stream, initial):
                while block := input_stream.read(1024 * 1024):
                    if count == 0 and not block.startswith(b"%PDF-"): fail("invalid_pdf", "Input has no supported PDF header")
                    count += len(block)
                    if count > MAX_PDF_BYTES: fail("file_budget", "PDF input exceeds its byte budget")
                    h.update(block); output.write(block)
                output.flush(); os.fsync(output.fileno())
                if count != initial.st_size or count != size or h.hexdigest() != sha:
                    fail("source_changed", "PDF bytes differ from the reviewed source")
            target = self._object(sha)
            try:
                os.link(temporary, target)
            except FileExistsError:
                self._verify_object(sha, size)
            if os.name == "posix":
                handle = os.open(objects, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(handle)
                finally: os.close(handle)
        finally:
            temporary.unlink(missing_ok=True)

    def _adopt_import(self, db, operation_id, request):
        original = self._operation(db, operation_id)
        if (original is None or original["kind"] != "import"
                or original["request_sha256"] != checksum({"kind": "import", "request": request})):
            fail("operation_conflict", "Import identity does not match its original request")
        if original["state"] == "completed":
            # Recovery may have adopted this exact source while the original
            # process was alive. Its immutable receipt never follows later edits.
            return original["receipt"]
        version_id = str(uuid5(UUID(request["document_id"]), request["source_sha256"]))
        existing = db.execute("SELECT * FROM versions WHERE id=?", (version_id,)).fetchone()
        if existing is not None:
            # A second operation cannot silently revise/revive an existing
            # version's authorization, title or withdrawn status.
            if (existing["import_operation"] != operation_id or existing["source_bytes"] != request["source_bytes"]
                    or existing["title"] != request["title"] or existing["authorization"] != canonical(request["authorization"]).decode()):
                fail("version_conflict", "PDF version already has an independent import receipt")
        else:
            if db.execute("SELECT count(*) FROM versions").fetchone()[0] >= MAX_VERSIONS:
                fail("version_budget", "Local literature version budget is full")
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,1,NULL,?)", (version_id, request["document_id"],
                request["source_sha256"], request["source_bytes"], request["title"], canonical(request["authorization"]).decode(), operation_id))
        result = {"version_id": version_id, "document_id": request["document_id"], "source_sha256": request["source_sha256"],
                  "source_bytes": request["source_bytes"], "generation": self._generation(db, advance=existing is None)}
        self._finish(db, operation_id, result)
        return result

    def import_pdf(self, operation_id, source, *, source_sha256, source_bytes, document_id, title, authorization):
        """Explicitly capture reviewed local bytes; importing never parses or indexes."""
        _uuid(document_id); _text(title, 1024)
        if type(source_sha256) is not str or not _SHA.fullmatch(source_sha256) or type(source_bytes) is not int or not 5 <= source_bytes <= MAX_PDF_BYTES: fail()
        request = {"document_id": document_id, "source_sha256": source_sha256, "source_bytes": source_bytes,
                   "title": title, "authorization": _authorization(authorization)}
        previous = self._reserve(operation_id, "import", request)
        if previous is not None: return previous
        try:
            self._publish_source(Path(source), source_sha256, source_bytes)
            with self._db(write=True) as db: self._adopt_import(db, operation_id, request)
        finally:
            self._inactive(operation_id)
        return self.operation(operation_id)

    def recover_import(self, operation_id, original_operation_id):
        """Adopt an exact already-published source, never recopy or parse it."""
        _uuid(original_operation_id)
        previous = self._reserve(operation_id, "recover_import", {"original_operation_id": original_operation_id})
        if previous is not None: return previous
        try:
            with self._db() as db:
                original = self._operation(db, original_operation_id)
                if original is None or original["kind"] != "import": fail()
                if original["state"] == "running": fail("busy", "Original import is still active")
                request = json.loads(db.execute("SELECT request FROM operations WHERE id=?", (original_operation_id,)).fetchone()[0])
            self._verify_object(request["source_sha256"], request["source_bytes"])
            with self._db(write=True) as db:
                # Import receipt and logical publication are one transaction.
                original = self._operation(db, original_operation_id)
                if original["state"] == "completed": result = original["receipt"]
                else: result = self._adopt_import(db, original_operation_id, request)
                self._finish(db, operation_id, {"original_operation_id": original_operation_id, "import": result})
        finally: self._inactive(operation_id)
        return self.operation(operation_id)

    def _version(self, db, version_id, *, active=False):
        row = None if db is None else db.execute("SELECT * FROM versions WHERE id=?", (version_id,)).fetchone()
        if row is None: fail("not_found", "Literature version was not found")
        if active and not row["active"]: fail("authorization_revoked", "Literature version authorization was withdrawn")
        _authorization(json.loads(row["authorization"]))
        return row

    def versions(self, *, offset=0, limit=20):
        _page(offset, limit)
        with self._db() as db:
            rows = [] if db is None else db.execute("SELECT * FROM versions ORDER BY id LIMIT ? OFFSET ?", (limit, offset))
            return [{"version_id": row["id"], "document_id": row["document_id"], "title": row["title"],
                     "source_sha256": row["source_sha256"], "source_bytes": row["source_bytes"], "active": bool(row["active"]),
                     "authorization": json.loads(row["authorization"]), "extraction_id": row["current_extraction"]} for row in rows]

    def index_pdf(self, operation_id, version_id, *, python, timeout=60):
        """Parse the selected immutable version only on this explicit action."""
        _uuid(version_id)
        request = {"version_id": version_id, "python": str(python), "timeout": timeout}
        previous = self._reserve(operation_id, "index", request)
        if previous is not None: return previous
        try:
            with self._db() as db:
                version_row = self._version(db, version_id, active=True)
                sha, size = version_row["source_sha256"], version_row["source_bytes"]
            # No SQLite write transaction or authorization lease spans parsing.
            evidence = extract_pdf(self._object(sha), python=python, expected_sha256=sha, expected_bytes=size, timeout=timeout)
            validate_extraction(evidence, sha, size)
            extraction = evidence["extraction_id"]
            proof = {k: v for k, v in evidence.items() if k not in {"pages", "paragraphs"}}
            proof["page_sha256"] = [checksum(p) for p in evidence["pages"]]
            proof["paragraph_sha256"] = {p["paragraph_id"]: checksum(p) for p in evidence["paragraphs"]}
            with self._db(write=True) as db:
                self._version(db, version_id, active=True)
                exists = db.execute("SELECT 1 FROM extractions WHERE version_id=? AND id=?", (version_id, extraction)).fetchone()
                if exists is None:
                    if db.execute("SELECT count(*) FROM paragraphs").fetchone()[0] + len(evidence["paragraphs"]) > MAX_PARAGRAPHS:
                        fail("index_budget", "Local literature paragraph budget is full")
                    db.execute("INSERT INTO extractions VALUES(?,?,?)", (version_id, extraction, canonical(proof).decode()))
                    db.executemany("INSERT INTO pages VALUES(?,?,?,?)", [(version_id, extraction, p["page_index"], canonical(p).decode()) for p in evidence["pages"]])
                    for p in evidence["paragraphs"]:
                        key = checksum({"version_id": version_id, "extraction_id": extraction, "paragraph_id": p["paragraph_id"]})
                        db.execute("INSERT INTO paragraphs VALUES(?,?,?,?,?,?,?,?,?)", (key, version_id, extraction, p["paragraph_id"], p["page_index"], p["start"], p["end"], p["text"], p["text_sha256"]))
                        db.execute("INSERT INTO paragraph_fts(key,text) VALUES(?,?)", (key, p["text"]))
                db.execute("UPDATE versions SET current_extraction=? WHERE id=?", (extraction, version_id))
                receipt = {"version_id": version_id, "source_sha256": sha, "extraction_id": extraction,
                           "page_count": evidence["page_count"], "character_count": evidence["character_count"],
                           "text_status": evidence["text_status"], "structure_status": "unreviewed",
                           "generation": self._generation(db, advance=True)}
                self._finish(db, operation_id, receipt)
        finally: self._inactive(operation_id)
        return self.operation(operation_id)

    @staticmethod
    def _citation(row, source_sha256):
        return {"format": "stk.literature-citation/1", "version_id": row["version_id"], "source_sha256": source_sha256,
                "extraction_id": row["extraction_id"], "paragraph_id": row["id"], "text_sha256": row["text_sha256"],
                "page_index": row["page_index"], "start": row["start"], "end": row["end"]}

    def search(self, query, *, limit=10):
        """Literal local lexical lookup, with no FTS operators/model/network calls."""
        _text(query, 256)
        if type(limit) is not int or not 1 <= limit <= 20: fail()
        with self._db() as db:
            generation = self._generation(db)
            if db is None: return {"generation": generation, "retriever": "local_fts5_trigram", "hits": []}
            if len(query) >= 3:
                # Quoted phrase treats punctuation and Boolean syntax as text.
                phrase = '"' + query.replace('"', '""') + '"'
                rows = db.execute("""SELECT p.*,v.source_sha256,v.title,json_extract(e.proof,'$.text_status') AS text_status FROM paragraph_fts f
                    JOIN paragraphs p ON p.key=f.key JOIN versions v ON v.id=p.version_id JOIN extractions e ON e.version_id=p.version_id AND e.id=p.extraction_id
                    WHERE paragraph_fts MATCH ? AND v.active=1 AND v.current_extraction=p.extraction_id
                    ORDER BY bm25(paragraph_fts),p.key LIMIT ?""", (phrase, limit)).fetchall()
            else:
                # Trigram cannot match 1/2-codepoint phrases. The corpus is hard
                # bounded; literal LIKE handles these without claiming tokens.
                phrase = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                rows = db.execute("""SELECT p.*,v.source_sha256,v.title,json_extract(e.proof,'$.text_status') AS text_status FROM paragraphs p JOIN versions v ON v.id=p.version_id
                    JOIN extractions e ON e.version_id=p.version_id AND e.id=p.extraction_id
                    WHERE p.text LIKE ? ESCAPE '\\' AND v.active=1 AND v.current_extraction=p.extraction_id
                    ORDER BY p.key LIMIT ?""", (phrase, limit)).fetchall()
            return {"generation": generation, "retriever": "local_fts5_trigram" if len(query) >= 3 else "bounded_literal",
                    "hits": [{"title": row["title"], "text": row["text"], "text_status":row["text_status"],"structure_status":"unreviewed",
                              "citation": self._citation(row, row["source_sha256"])} for row in rows]}

    def resolve(self, citation):
        """Return exact verified page/paragraph geometry; no generic PDF URL claim."""
        if type(citation) is not dict or set(citation) != {"format", "version_id", "source_sha256", "extraction_id", "paragraph_id", "text_sha256", "page_index", "start", "end"}: fail()
        if (citation["format"] != "stk.literature-citation/1"
                or any(type(citation[k]) is not str or not _SHA.fullmatch(citation[k]) for k in ("source_sha256", "extraction_id", "paragraph_id", "text_sha256"))
                or any(type(citation[k]) is not int for k in ("page_index", "start", "end"))): fail()
        _uuid(citation["version_id"])
        with self._db() as db:
            version_row = self._version(db, citation["version_id"], active=True)
            row = db.execute("SELECT * FROM paragraphs WHERE version_id=? AND extraction_id=? AND id=?", (citation["version_id"], citation["extraction_id"], citation["paragraph_id"])).fetchone()
            if row is None or citation != self._citation(row, version_row["source_sha256"]):
                fail("citation_mismatch", "Citation does not match a frozen evidence span")
            proof_row = db.execute("SELECT proof FROM extractions WHERE version_id=? AND id=?", (row["version_id"], row["extraction_id"])).fetchone()
            page_row = db.execute("SELECT evidence FROM pages WHERE version_id=? AND extraction_id=? AND page_index=?", (row["version_id"], row["extraction_id"], row["page_index"])).fetchone()
            proof, page = json.loads(proof_row[0]), json.loads(page_row[0])
            paragraph = {k: row[k] for k in ("page_index", "start", "end", "text", "text_sha256")}
            paragraph["paragraph_id"] = row["id"]
            if (checksum(page) != proof["page_sha256"][row["page_index"]]
                    or checksum(paragraph) != proof["paragraph_sha256"][row["id"]]
                    or paragraph["text"] != page["text"][row["start"]:row["end"]]
                    or hashlib.sha256(paragraph["text"].encode()).hexdigest() != row["text_sha256"]): fail("citation_mismatch", "Frozen citation evidence changed")
            sha, size = version_row["source_sha256"], version_row["source_bytes"]
            result = {"citation": dict(citation), "text": row["text"], "parser": proof["parser"], "text_status": proof["text_status"],
                      "structure_status": proof["structure_status"], "page": {k: page[k] for k in ("page_index", "width", "height", "page_box", "rotation", "status")},
                      "characters": [c for c in page["characters"] if row["start"] <= c["text_start"] and c["text_end"] <= row["end"]]}
        self._verify_object(sha, size)
        # Recheck current approval after potentially long whole-source hashing.
        with self._db() as db: self._version(db, citation["version_id"], active=True)
        return result

    def resolve_many(self, citations):
        """Resolve a bounded ordered batch, sharing verification only this call.

        Duplicate positions are retained as independent JSON values. A corrupt,
        revoked or over-budget item rejects the whole batch. Empty reads remain
        passive; unrelated corpus generations do not invalidate retained spans.
        """
        if type(citations) is not list: fail()
        if len(citations) > MAX_CITATIONS:
            fail("citation_budget", "Citation batch exceeds its bound")
        supplied = citations[:]
        if len(supplied) > MAX_CITATIONS:
            fail("citation_budget", "Citation batch exceeds its bound")
        selected = []
        fields = {"format", "version_id", "source_sha256", "extraction_id", "paragraph_id", "text_sha256", "page_index", "start", "end"}
        for citation in supplied:
            if (type(citation) is not dict or len(citation) != len(fields)
                    or any(type(key) is not str for key in citation) or set(citation) != fields): fail()
            if (type(citation["format"]) is not str or citation["format"] != "stk.literature-citation/1"
                    or type(citation["version_id"]) is not str or len(citation["version_id"]) != 36
                    or any(type(citation[key]) is not str or not _SHA.fullmatch(citation[key])
                           for key in ("source_sha256", "extraction_id", "paragraph_id", "text_sha256"))
                    or any(type(citation[key]) is not int for key in ("page_index", "start", "end"))
                    or not 0 <= citation["page_index"] < 256
                    or not 0 <= citation["start"] < citation["end"] <= 250000): fail()
            _uuid(citation["version_id"])
            selected.append(dict(citation))
        if not selected: return []
        try:
            return self._resolve_many(selected)
        except LiteratureError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError, UnicodeError):
            fail("citation_mismatch", "Frozen citation evidence is inconsistent")

    def _resolve_many(self, selected):
        versions, paragraphs, raw_proofs, raw_pages, sources = {}, {}, {}, {}, {}
        captured = set()
        raw_bytes, characters = 0, 0
        with self._db() as db:
            # Preserve this identity across all unlocked parsing and file hashes.
            identity = None if db is None else db.execute("SELECT identity FROM meta WHERE id=1").fetchone()[0]
            def capture(table, column, where, parameters, cache, key):
                nonlocal raw_bytes
                binding = (table, column, parameters)
                if binding in captured: return
                row = db.execute("SELECT length(CAST(" + column + " AS BLOB)) FROM " + table + " WHERE " + where, parameters).fetchone()
                if row is None: fail("citation_mismatch", "Frozen citation evidence is unavailable")
                size = row[0]
                if type(size) is not int or size < 0: fail()
                if size > MAX_CITATION_EVIDENCE_BYTES or (key not in cache and raw_bytes + size > MAX_CITATION_EVIDENCE_BYTES):
                    fail("citation_budget", "Citation evidence exceeds its byte bound")
                raw = db.execute("SELECT " + column + " FROM " + table + " WHERE " + where, parameters).fetchone()[0]
                if type(raw) is not str: fail()
                if key in cache:
                    if cache[key] != raw: fail("citation_mismatch", "Shared citation evidence differs")
                else:
                    cache[key] = raw; raw_bytes += size
                captured.add(binding)
            for citation in selected:
                version = citation["version_id"]
                if version not in versions:
                    row = self._version(db, version, active=True)
                    versions[version] = (row["source_sha256"], row["source_bytes"])
                sha, size = versions[version]
                if sha in sources and sources[sha] != size: fail("citation_mismatch", "Frozen source declarations differ")
                sources[sha] = size
                key = (version, citation["extraction_id"], citation["paragraph_id"])
                if key not in paragraphs:
                    where = "version_id=? AND extraction_id=? AND id=?"
                    row = db.execute("SELECT version_id,extraction_id,id,page_index,start,end,text_sha256,length(text) AS text_length,length(CAST(text AS BLOB)) AS text_bytes FROM paragraphs WHERE " + where, key).fetchone()
                    if row is None or citation != self._citation(row, sha):
                        fail("citation_mismatch", "Citation does not match a frozen evidence span")
                    if (type(row["text_length"]) is not int or not 0 < row["text_length"] <= 2048
                            or type(row["text_bytes"]) is not int or not 0 < row["text_bytes"] <= 8192):
                        fail("citation_budget", "Citation paragraph exceeds its bound")
                    paragraph = {k: row[k] for k in ("page_index", "start", "end", "text_sha256")}
                    paragraph["paragraph_id"] = row["id"]
                    paragraph["text"] = db.execute("SELECT text FROM paragraphs WHERE " + where, key).fetchone()[0]
                    if type(paragraph["text"]) is not str or len(paragraph["text"]) != row["text_length"]: fail()
                    paragraphs[key] = paragraph
                    extraction = citation["extraction_id"]
                    capture("extractions", "proof", "version_id=? AND id=?", (version, extraction), raw_proofs, extraction)
                    page = citation["page_index"]
                    capture("pages", "evidence", "version_id=? AND extraction_id=? AND page_index=?", (version, extraction, page), raw_pages, (extraction, page))
                else:
                    paragraph = paragraphs[key]
                    if (citation["source_sha256"] != sha or citation["page_index"] != paragraph["page_index"]
                            or citation["start"] != paragraph["start"] or citation["end"] != paragraph["end"]
                            or citation["text_sha256"] != paragraph["text_sha256"]):
                        fail("citation_mismatch", "Citation does not match a frozen evidence span")
                characters += len(paragraphs[key]["text"])
                if characters > MAX_CITATION_CHARACTERS:
                    fail("citation_budget", "Citation response exceeds its character bound")
        # JSON decoding/checking and PDF hashing never retain the DB lease.
        proofs = {key: json.loads(raw) for key, raw in raw_proofs.items()}
        pages = {key: json.loads(raw) for key, raw in raw_pages.items()}
        for (extraction, page), evidence in pages.items():
            if checksum(evidence) != proofs[extraction]["page_sha256"][page]:
                fail("citation_mismatch", "Frozen citation evidence changed")
        for (_, extraction, _), paragraph in paragraphs.items():
            page, proof = pages[(extraction, paragraph["page_index"])], proofs[extraction]
            if (checksum(paragraph) != proof["paragraph_sha256"][paragraph["paragraph_id"]]
                    or paragraph["text"] != page["text"][paragraph["start"]:paragraph["end"]]
                    or hashlib.sha256(paragraph["text"].encode()).hexdigest() != paragraph["text_sha256"]):
                fail("citation_mismatch", "Frozen citation evidence changed")
        results = []
        for citation in selected:
            extraction = citation["extraction_id"]
            paragraph = paragraphs[(citation["version_id"], extraction, citation["paragraph_id"])]
            page, proof = pages[(extraction, citation["page_index"])], proofs[extraction]
            results.append({"citation": dict(citation), "text": paragraph["text"], "parser": proof["parser"],
                            "text_status": proof["text_status"], "structure_status": proof["structure_status"],
                            "page": {k: page[k] for k in ("page_index", "width", "height", "page_box", "rotation", "status")},
                            "characters": [c for c in page["characters"] if paragraph["start"] <= c["text_start"] and c["text_end"] <= paragraph["end"]]})
        output = bytearray()
        encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        for chunk in encoder.iterencode(results):
            encoded = chunk.encode("utf-8")
            if len(output) + len(encoded) > MAX_CITATION_RESPONSE_BYTES:
                fail("citation_budget", "Citation response exceeds its byte bound")
            output.extend(encoded)
        # Independent JSON values prevent duplicate/page cache aliases escaping.
        results = json.loads(output)
        for sha, size in sources.items(): self._verify_object(sha, size)
        with self._db() as db:
            if db is None or db.execute("SELECT identity FROM meta WHERE id=1").fetchone()[0] != identity:
                fail("storage_error", "Local literature database identity changed")
            for version, original in versions.items():
                row = self._version(db, version, active=True)
                if (row["source_sha256"], row["source_bytes"]) != original:
                    fail("citation_mismatch", "Frozen source declarations changed")
        return results

    def revoke(self, operation_id, version_id):
        _uuid(version_id)
        previous = self._reserve(operation_id, "revoke", {"version_id": version_id})
        if previous is not None: return previous
        try:
            with self._db(write=True) as db:
                self._version(db, version_id)
                db.execute("UPDATE versions SET active=0 WHERE id=?", (version_id,))
                self._finish(db, operation_id, {"version_id": version_id, "active": False, "generation": self._generation(db, advance=True)})
        finally: self._inactive(operation_id)
        return self.operation(operation_id)
