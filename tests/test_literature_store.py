"""Explicit local import/index/revocation, durable evidence and literal retrieval."""
import copy
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from uuid import uuid4

import pytest

from suan.literature._io import LiteratureError, inspect_pdf
from suan.literature.store import Library
from test_literature_pdf import make_pdf, unicode_pdf, pdf_python


RIGHTS = {"basis": "self_authored", "evidence": "Self-authored software-validation fixture", "approved_by": "fixture owner"}


@pytest.mark.parametrize("field,value", [
    ("search", "\ud800"), ("title", "\udfff"),
    ("evidence", "\ud800"), ("approved_by", "\udfff"),
    ("basis", []), ("basis", {}), ("basis", set()), ("basis", None),
])
def test_public_text_and_authorization_guards_fail_safely_before_capture(tmp_path, monkeypatch, field, value):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Owned guard fixture"]]))
    reviewed = inspect_pdf(source); library = Library(tmp_path / "not-created")
    monkeypatch.setattr(library, "_publish_source", lambda *a: pytest.fail("Invalid request reached source capture"))
    rights, title = dict(RIGHTS), "Owned guard fixture"
    if field == "title": title = value
    elif field in rights: rights[field] = value
    with pytest.raises(LiteratureError) as caught:
        if field == "search": library.search(value)
        else:
            library.import_pdf(str(uuid4()), source, source_sha256=reviewed["sha256"], source_bytes=reviewed["bytes"],
                               document_id=str(uuid4()), title=title, authorization=rights)
    assert caught.value.code in {"invalid_data", "authorization_required"}
    assert len(caught.value.message) < 128
    assert not library.root.exists()


def _import(library, path, *, operation=None, document=None, authorization=None):
    selected = inspect_pdf(path)
    return library.import_pdf(operation or str(uuid4()), path, source_sha256=selected["sha256"], source_bytes=selected["bytes"],
                              document_id=document or str(uuid4()), title="Self-authored validation paper", authorization=authorization or RIGHTS)


def _ready(tmp_path, pdf_python, pages=None):
    path = tmp_path / "source.pdf"; path.write_bytes(make_pdf(pages or [["Alpha provenance in first page"], ["Last page zircon evidence unique"]]))
    library = Library(tmp_path / "library")
    imported = _import(library, path); identity = imported["receipt"]["version_id"]
    result = library.index_pdf(str(uuid4()), identity, python=pdf_python)
    assert result["state"] == "completed"
    return library, identity, path


def _paused_import_process(root, source, operation, document, published, release, result):
    """Real spawned importer paused after immutable bytes, before adoption."""
    library = Library(root)
    publish = library._publish_source
    def pause(*args):
        publish(*args)
        published.set()
        if not release.wait(30):
            raise RuntimeError("Import test synchronization timed out")
    library._publish_source = pause
    result.put(_import(library, source, operation=operation, document=document))


def _leave_foreign_hot_journal(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA synchronous=FULL"); db.execute("PRAGMA cache_size=2")
    db.execute("BEGIN IMMEDIATE")
    db.execute("UPDATE unrelated SET value=?", ("uncommitted fixture" + "z" * 2048,))
    os._exit(0)


def _crash_actual_import(root, source, operation, preimage):
    real_connect = sqlite3.connect
    def small_cache(*args, **kwargs):
        db = real_connect(*args, **kwargs); db.execute("PRAGMA cache_size=1"); return db
    sqlite3.connect = small_cache
    library = Library(root)
    publish, adopt = library._publish_source, library._adopt_import
    def capture_preimage(*args):
        publish(*args)
        # No SQLite connection is open at this publication boundary.
        Path(preimage).write_text(hashlib.sha256(library.path.read_bytes()).hexdigest())
    def crash_after_sql(*args):
        adopt(*args); os._exit(0)  # Normal adoption SQL, interrupted before commit.
    library._publish_source, library._adopt_import = capture_preimage, crash_after_sql
    _import(library, source, operation=operation)


def _run_child(target, *args):
    child = multiprocessing.get_context("spawn").Process(target=target, args=args)
    child.start(); child.join(20)
    if child.is_alive(): child.terminate(); child.join(5)
    assert child.exitcode == 0


def test_foreign_hot_journal_is_refused_without_mutating_originals(tmp_path):
    root = tmp_path / "foreign"; root.mkdir(); path = root / "literature.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")
        db.executemany("INSERT INTO unrelated VALUES(?)", [("original" + "x" * 2048,) for _ in range(512)])
        db.execute("PRAGMA application_id=1398033481"); db.execute("PRAGMA user_version=1")
    _run_child(_leave_foreign_hot_journal, path)
    journal = path.with_name(path.name + "-journal"); assert journal.stat().st_size > 512
    before = [(p.read_bytes(), p.stat().st_mode) for p in (path, journal)]
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Owned import"]]))
    for action in (lambda: Library(root).info(), lambda: _import(Library(root), source)):
        with pytest.raises(LiteratureError): action()
        assert [(p.read_bytes(), p.stat().st_mode) for p in (path, journal)] == before


@pytest.mark.skipif(os.name != "posix", reason="Physical recovery requires the proven POSIX lease")
def test_legitimate_hot_journal_recovers_exact_preimage_before_explicit_import_recovery(tmp_path):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Established version"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    interrupted = tmp_path / "interrupted.pdf"; interrupted.write_bytes(make_pdf([["Explicit interrupted version"]]))
    operation, preimage = str(uuid4()), tmp_path / "preimage.txt"
    physical = (library.path.stat().st_dev, library.path.stat().st_ino)
    _run_child(_crash_actual_import, library.root, interrupted, operation, preimage)
    journal = library.path.with_name(library.path.name + "-journal"); assert journal.stat().st_size > 512
    assert Library(library.root).info()["generation"] == 1
    assert hashlib.sha256(library.path.read_bytes()).hexdigest() == preimage.read_text()
    assert (library.path.stat().st_dev, library.path.stat().st_ino) == physical
    assert not journal.exists()
    assert len(library.versions()) == 1
    assert library.operation(operation)["state"] == "uncertain"
    interrupted.unlink()
    assert library.recover_import(str(uuid4()), operation)["state"] == "completed"
    assert library.operation(operation)["state"] == "completed"
    assert library.info()["generation"] == 2


@pytest.mark.skipif(os.name != "posix", reason="Actual POSIX SQLite descriptor-lock behavior")
def test_library_transaction_keeps_sqlite_write_lock_against_real_process(tmp_path):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Writer exclusion"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    child = """import sqlite3,sys
db=sqlite3.connect(sys.argv[1],timeout=.1)
try:db.execute('BEGIN IMMEDIATE')
except sqlite3.OperationalError as e:
 if e.sqlite_errorcode==sqlite3.SQLITE_BUSY:sys.exit(0)
 raise
else:db.rollback();sys.exit(1)
finally:db.close()
"""
    with library._db(write=True):
        result = subprocess.run([sys.executable, "-c", child, str(library.path)], timeout=5)
        assert result.returncode == 0, "Another process entered our active write transaction"


@pytest.mark.parametrize("changed", ["database_copy", "journal_copy", "original_journal"])
@pytest.mark.skipif(os.name != "posix", reason="Physical recovery requires the proven POSIX lease")
def test_recovery_refuses_torn_pair_and_concurrent_journal_change(tmp_path, monkeypatch, changed):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Existing local version"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    second = tmp_path / "second.pdf"; second.write_bytes(make_pdf([["Interrupted local version"]]))
    _run_child(_crash_actual_import, library.root, second, str(uuid4()), tmp_path / "preimage")
    journal = library.path.with_name(library.path.name + "-journal")
    def originals(): return [(p.read_bytes(), p.stat().st_mode) for p in (library.path, journal)]
    expected, injected = originals(), False
    copy_file = library._copy_file
    def race(path, maximum, target=None):
        nonlocal expected, injected
        result = copy_file(path, maximum, target)
        selected = library.path if changed == "database_copy" else journal
        if not injected and target is not None and path == selected:
            injected = True
            if changed == "original_journal":
                with journal.open("ab") as stream: stream.write(b"concurrent partial journal")
                expected = originals()  # Only the external fault changed originals.
            else:
                with target.open("r+b") as stream:
                    stream.seek(100); stream.write(b"torn-copy")
        return result
    monkeypatch.setattr(library, "_copy_file", race)
    with pytest.raises(LiteratureError): library.info()
    assert injected
    assert originals() == expected


@pytest.mark.parametrize("kind", ["wal", "journal_symlink", "super_journal", "hardlink"])
def test_unsafe_journal_families_and_aliases_are_refused_before_sqlite_open(tmp_path, monkeypatch, kind):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Known private database"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    journal = library.path.with_name(library.path.name + "-journal")
    outside = tmp_path / "outside-journal"; outside.write_bytes(b"public sentinel, never a journal target")
    if kind == "wal": library.path.with_name(library.path.name + "-wal").write_bytes(b"unsupported WAL")
    elif kind == "journal_symlink":
        try: journal.symlink_to(outside)
        except OSError: pytest.skip("Platform does not permit test symlinks")
    elif kind == "hardlink": os.link(library.path, journal)
    else:
        magic = bytes.fromhex("d9d505f920a163d7"); name = str(outside).encode()
        journal.write_bytes(magic + b"\0" * 504 + name + len(name).to_bytes(4,"big") + sum(name).to_bytes(4,"big") + magic)
    before = library.path.read_bytes(), outside.read_bytes()
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("Unsafe family reached SQLite"))
    with pytest.raises(LiteratureError): library.info()
    assert (library.path.read_bytes(), outside.read_bytes()) == before


@pytest.mark.parametrize("kind", ["complete", "partial", "mismatch", "extra"])
def test_only_complete_recognized_dense_schema_extension_reopens(tmp_path, kind):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Dense schema compatibility only"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    with sqlite3.connect(library.path) as db:
        db.execute("CREATE TABLE dense_meta(id INTEGER PRIMARY KEY CHECK(id=1),current_generation TEXT NOT NULL)")
        if kind != "partial":
            db.execute("CREATE TABLE dense_generations(id TEXT PRIMARY KEY,manifest TEXT NOT NULL)")
            db.execute("CREATE TABLE dense_windows(generation TEXT NOT NULL REFERENCES dense_generations(id),key TEXT NOT NULL,position INTEGER NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(generation,key))")
        if kind == "mismatch": db.execute("ALTER TABLE dense_meta ADD COLUMN unrecognized TEXT")
        if kind == "extra": db.execute("CREATE TABLE unrelated(data TEXT)")
    before = library.path.read_bytes()
    if kind == "complete":
        assert Library(library.root).info()["versions"] == 1
        assert len(Library(library.root).versions()) == 1
    else:
        with pytest.raises(LiteratureError): Library(library.root).info()
        with pytest.raises(LiteratureError): _import(Library(library.root), source)
    assert library.path.read_bytes() == before


@pytest.mark.parametrize("kind", ["sqliteXtable", "sqliteXtrigger", "SqliteXtrigger"])
def test_sqlite_like_prefix_is_not_trusted_internal_schema(tmp_path, kind):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Base schema guard"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    with sqlite3.connect(library.path) as db:
        if kind == "sqliteXtable": db.execute("CREATE TABLE sqliteXshadow(data TEXT)")
        else: db.execute("CREATE TRIGGER " + kind + " AFTER INSERT ON operations BEGIN DELETE FROM versions; END")
    before = library.path.read_bytes()
    with pytest.raises(LiteratureError): Library(library.root).info()
    with pytest.raises(LiteratureError): _import(Library(library.root), source)
    assert library.path.read_bytes() == before


def test_same_process_library_instances_serialize_connection_lifetimes(tmp_path):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Shared process transaction guard"]]))
    first = Library(tmp_path / "library"); _import(first, source)
    second = Library(first.root); entered, done = threading.Event(), threading.Event(); errors = []
    def read_other():
        entered.set()
        try: second.info()
        except Exception as error: errors.append(error)
        finally: done.set()
    with first._db(write=True):
        worker = threading.Thread(target=read_other); worker.start(); assert entered.wait(5)
        assert not done.wait(.1), "Another Library opened the same database during our transaction"
    worker.join(5); assert not worker.is_alive(); assert not errors; assert done.is_set()


def _hot_library(tmp_path):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Recovery guard baseline"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    second = tmp_path / "second.pdf"; second.write_bytes(make_pdf([["Interrupted import"]]))
    _run_child(_crash_actual_import, library.root, second, str(uuid4()), tmp_path / "preimage")
    return library, library.path.with_name(library.path.name + "-journal")


@pytest.mark.skipif(os.name != "posix", reason="Physical recovery requires the proven POSIX lease")
def test_recovery_open_rechecks_exact_pair_after_private_preflight_returns(tmp_path, monkeypatch):
    library, journal = _hot_library(tmp_path); preflight = library._preflight; expected = None
    def race(physical):
        nonlocal expected
        ticket = preflight(physical)
        with journal.open("ab") as stream: stream.write(b"external change after completed private validation")
        expected = library.path.read_bytes(), journal.read_bytes()
        return ticket
    monkeypatch.setattr(library, "_preflight", race)
    with pytest.raises(LiteratureError): library.info()
    assert expected is not None
    assert (library.path.read_bytes(), journal.read_bytes()) == expected


def test_physical_recovery_without_supported_exclusive_lease_fails_closed(tmp_path, monkeypatch):
    library, journal = _hot_library(tmp_path)
    before = library.path.read_bytes(), journal.read_bytes()
    monkeypatch.setattr(library, "_acquire_lease", lambda: None)
    with pytest.raises(LiteratureError) as caught: library.info()
    assert caught.value.code == "unsupported_recovery"
    assert (library.path.read_bytes(), journal.read_bytes()) == before


@pytest.mark.skipif(os.name != "posix", reason="Actual POSIX independent recovery lease")
def test_recovery_copy_holds_cross_process_lease_without_sqlite_connection(tmp_path, monkeypatch):
    library, _ = _hot_library(tmp_path); copy_file = library._copy_file; checked = False
    child = """import fcntl,os,sys
fd=os.open(sys.argv[1],os.O_RDONLY)
try:
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:sys.exit(0)
 else:sys.exit(1)
finally:os.close(fd)
"""
    def check(path, maximum, target=None):
        nonlocal checked
        if not checked and target is not None and path == library.path:
            checked = True; assert library._gate.connections == 0
            result = subprocess.run([sys.executable, "-c", child, str(library.path)], timeout=5)
            assert result.returncode == 0, "Recovery pair was not held under its cross-process lease"
        return copy_file(path, maximum, target)
    monkeypatch.setattr(library, "_copy_file", check)
    assert library.info()["generation"] == 1; assert checked


@pytest.mark.parametrize("fragment", ["value TEXT DEFAULT '{value}'", '"{value}" TEXT'])
def test_schema_tokens_preserve_quoted_literal_and_identifier_contents(fragment):
    from suan.literature.store import _schema
    left, right = sqlite3.connect(":memory:"), sqlite3.connect(":memory:")
    try:
        left.execute("CREATE TABLE quoted(" + fragment.format(value="a , b") + ")")
        right.execute("CREATE TABLE quoted(" + fragment.format(value="a,b") + ")")
        assert _schema(left) != _schema(right)
    finally: left.close(); right.close()


def test_database_id_is_persistent_opaque_and_distinguishes_identical_local_corpora(tmp_path):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Same version, distinct owner corpus"]]))
    first, second = Library(tmp_path / "first"), Library(tmp_path / "second")
    document = str(uuid4())
    version1 = _import(first, source, document=document)["receipt"]["version_id"]
    version2 = _import(second, source, document=document)["receipt"]["version_id"]
    assert version1 == version2
    assert first.info()["database_id"] != second.info()["database_id"]
    assert Library(first.root).info()["database_id"] == first.info()["database_id"]
    assert str(first.root) not in json.dumps(first.info())


@pytest.mark.parametrize("kind", ["database", "journal"])
def test_database_and_recovery_copy_byte_budgets_precede_sqlite_open(tmp_path, monkeypatch, kind):
    import suan.literature.store as module
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Bounded storage fixture"]]))
    library = Library(tmp_path / "library"); _import(library, source)
    path = library.path if kind == "database" else library.path.with_name(library.path.name + "-journal")
    with path.open("ab") as stream:
        stream.truncate((module.MAX_DB_BYTES if kind == "database" else module.MAX_JOURNAL_BYTES) + 1)
    before = path.stat()
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("Oversized original reached SQLite"))
    with pytest.raises(LiteratureError): library.info()
    after = path.stat()
    assert (after.st_dev,after.st_ino,after.st_size,after.st_mode) == (before.st_dev,before.st_ino,before.st_size,before.st_mode)


@pytest.mark.parametrize("kind", ["unmarked", "empty", "future_version", "foreign_schema"])
def test_unrecognized_database_is_refused_without_changing_bytes_or_permissions(tmp_path, kind):
    root = tmp_path / "foreign"; root.mkdir()
    path = root / "literature.sqlite3"
    if kind == "empty":
        path.touch()
    else:
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE unrelated(value TEXT)")
            db.execute("INSERT INTO unrelated VALUES('independent local data')")
            if kind in {"future_version", "foreign_schema"}:
                db.execute("PRAGMA application_id=1398033481")  # STLI, not a credential.
                db.execute("PRAGMA user_version=" + ("2" if kind == "future_version" else "1"))
    path.chmod(0o644)
    before, mode = path.read_bytes(), path.stat().st_mode
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Owned import"]]))
    library = Library(root)
    with pytest.raises(LiteratureError):
        library.info()
    with pytest.raises(LiteratureError):
        _import(library, source)
    assert path.read_bytes() == before
    assert path.stat().st_mode == mode


@pytest.mark.parametrize("kind", ["replace", "delete", "in_place"])
def test_known_library_refuses_database_replacement_or_reset(tmp_path, kind):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Original local corpus"]]))
    library = Library(tmp_path / "library")
    _import(library, source)
    replacement = Library(tmp_path / "other-library")
    _import(replacement, source)
    if kind == "delete":
        library.path.unlink()
    elif kind == "replace":
        replacement.path.replace(library.path)
    else:
        library.path.write_bytes(replacement.path.read_bytes())
    before = library.path.read_bytes() if library.path.exists() else None
    with pytest.raises(LiteratureError):
        library.info()
    with pytest.raises(LiteratureError):
        _import(library, source)
    assert (library.path.read_bytes() if library.path.exists() else None) == before


def test_recovered_import_receipt_stays_exact_when_original_process_finishes(tmp_path):
    source = tmp_path / "source.pdf"; source.write_bytes(make_pdf([["Original owned version"]]))
    root = tmp_path / "library"; original, document = str(uuid4()), str(uuid4())
    context = multiprocessing.get_context("spawn")
    published, release, result = context.Event(), context.Event(), context.Queue()
    child = context.Process(target=_paused_import_process,
                            args=(root, source, original, document, published, release, result))
    child.start()
    try:
        assert published.wait(20), "Importer did not publish its frozen source"
        assert child.is_alive()
        library = Library(root)
        assert library.operation(original)["state"] == "uncertain"
        recovered = library.recover_import(str(uuid4()), original)
        assert recovered["state"] == "completed"
        retained = library.operation(original)
        assert retained["receipt"]["generation"] == 1
        other = tmp_path / "other.pdf"; other.write_bytes(make_pdf([["Later independent version"]]))
        _import(library, other)
        library.revoke(str(uuid4()), retained["receipt"]["version_id"])
        assert library.info()["generation"] == 3
        release.set()
        finished = result.get(timeout=20)
        child.join(20)
        assert child.exitcode == 0
        assert finished == retained
        assert Library(root).operation(original) == retained
        assert library.info()["generation"] == 3
        assert next(v for v in library.versions() if v["version_id"] == retained["receipt"]["version_id"])["active"] is False
    finally:
        release.set()
        child.join(5)
        if child.is_alive():
            child.terminate(); child.join(5)
        result.close(); result.join_thread()


def test_reads_and_reopening_are_passive_without_directories_or_pdfium(tmp_path, monkeypatch):
    import suan.literature.store as module
    monkeypatch.setattr(module, "extract_pdf", lambda *a, **k:pytest.fail("Read triggered parsing"))
    root = tmp_path / "not-created"
    for library in (Library(root), Library(root)):
        assert library.info() == {"generation": 0, "versions": 0, "database_id": None, "corpus": "local", "semantic_retrieval": False}
        assert library.versions() == []
        assert library.operation(str(uuid4())) is None
        assert library.search("query")["hits"] == []
    assert not root.exists()


@pytest.mark.parametrize("authorization", [None, {}, {**RIGHTS,"basis":"paid"},{**RIGHTS,"basis":"unknown"},
                                           {**RIGHTS,"evidence":""},{**RIGHTS,"public":True}])
def test_explicit_per_version_permission_required_before_any_capture(tmp_path, authorization):
    path = tmp_path / "source.pdf";path.write_bytes(make_pdf([["Local rights evidence"]]))
    selected = inspect_pdf(path); root = tmp_path / "library"
    with pytest.raises(LiteratureError):
        Library(root).import_pdf(str(uuid4()),path,source_sha256=selected["sha256"],source_bytes=selected["bytes"],
                                document_id=str(uuid4()),title="Owned",authorization=authorization)
    assert not root.exists()


def test_capture_is_immutable_idempotent_and_never_parses_or_revives_withdrawal(tmp_path, monkeypatch):
    import suan.literature.store as module
    monkeypatch.setattr(module,"extract_pdf",lambda *a,**k:pytest.fail("Import parsed PDF"))
    path=tmp_path/"source.pdf";path.write_bytes(make_pdf([["First version"]]));library=Library(tmp_path/"library")
    op,document=str(uuid4()),str(uuid4());selected=inspect_pdf(path)
    def capture():
        return library.import_pdf(op,path,source_sha256=selected["sha256"],source_bytes=selected["bytes"],document_id=document,title="Owned",authorization=RIGHTS)
    first=capture();version=first["receipt"]["version_id"]
    path.unlink()
    assert capture()==first
    library.revoke(str(uuid4()),version)
    assert capture()==first
    assert library.versions()[0]["active"] is False
    assert Library(library.root).operation(op)==first
    with pytest.raises(LiteratureError) as caught:
        library.import_pdf(op,path,source_sha256=selected["sha256"],source_bytes=selected["bytes"],document_id=document,title="Changed",authorization=RIGHTS)
    assert caught.value.code=="operation_conflict"


def test_source_change_symlink_and_failed_capture_preserve_uncertain_original(tmp_path):
    source=tmp_path/"source.pdf";source.write_bytes(make_pdf([["Original"]]));selected=inspect_pdf(source)
    source.write_bytes(make_pdf([["Replacement"]]));library=Library(tmp_path/"library");op=str(uuid4())
    with pytest.raises(LiteratureError):
        library.import_pdf(op,source,source_sha256=selected["sha256"],source_bytes=selected["bytes"],document_id=str(uuid4()),title="Owned",authorization=RIGHTS)
    assert library.operation(op)["state"]=="uncertain"
    assert library.versions()==[]
    assert not list((library.root/"objects").glob("*.pdf"))
    link=tmp_path/"link.pdf"
    try:link.symlink_to(source)
    except OSError:pytest.skip("Symlink permission unavailable")
    with pytest.raises(LiteratureError):inspect_pdf(link)


def test_explicit_recover_adopts_exact_published_bytes_only_without_recopied_source(tmp_path, monkeypatch):
    path=tmp_path/"source.pdf";path.write_bytes(make_pdf([["Recover exact already-copied object"]]));library=Library(tmp_path/"library")
    original=library._adopt_import
    monkeypatch.setattr(library,"_adopt_import",lambda *a,**k:(_ for _ in ()).throw(RuntimeError("local post-copy fault")))
    op=str(uuid4());document=str(uuid4())
    with pytest.raises(RuntimeError):_import(library,path,operation=op,document=document)
    assert library.operation(op)["state"]=="uncertain"
    path.unlink();monkeypatch.setattr(library,"_adopt_import",original)
    receipt=library.recover_import(str(uuid4()),op)
    assert receipt["state"]=="completed"
    assert library.operation(op)["state"]=="completed"
    assert len(library.versions())==1


def test_real_index_search_exact_citation_and_reopen_keep_last_page_and_geometry(tmp_path,pdf_python,monkeypatch):
    library,identity,path=_ready(tmp_path,pdf_python)
    found=library.search("zircon evidence")
    assert len(found["hits"])==1
    hit=found["hits"][0];assert hit["citation"]["page_index"]==1
    resolved=library.resolve(hit["citation"])
    assert resolved["text"]==hit["text"]
    assert resolved["page"]["page_index"]==1
    assert any(c["box"] for c in resolved["characters"])
    import suan.literature.store as module
    monkeypatch.setattr(module,"extract_pdf",lambda *a,**k:pytest.fail("Read/reopen re-parsed"))
    assert Library(library.root).search("zircon evidence")==found
    assert Library(library.root).resolve(hit["citation"])==resolved
    # Mutating the working source does not rebind a frozen citation.
    path.write_bytes(make_pdf([["new work"]]))
    assert library.resolve(hit["citation"])==resolved
    for key,value in [("source_sha256","a"*64),("extraction_id","a"*64),("paragraph_id","a"*64),
                      ("text_sha256","a"*64),("page_index",0),("start",False),("extra",True)]:
        invalid=copy.deepcopy(hit["citation"]);invalid[key]=value
        with pytest.raises(LiteratureError):library.resolve(invalid)


def test_local_fts_unicode_short_queries_and_operator_text_are_literal(tmp_path,pdf_python):
    source=tmp_path/"unicode.pdf";source.write_bytes(unicode_pdf());library=Library(tmp_path/"library")
    identity=_import(library,source)["receipt"]["version_id"]
    library.index_pdf(str(uuid4()),identity,python=pdf_python)
    assert len(library.search("汉字α")["hits"])==1
    assert len(library.search("汉字")["hits"])==1
    assert library.search('" OR * NOT zircon')["hits"]==[]


def test_withdrawal_blocks_search_prior_citation_and_inflight_index_publication(tmp_path,pdf_python,monkeypatch):
    import suan.literature.store as module
    library,identity,path=_ready(tmp_path,pdf_python)
    citation=library.search("zircon")["hits"][0]["citation"]
    ready,release=threading.Event(),threading.Event();real=module.extract_pdf;errors=[]
    def delay(*a,**k):
        result=real(*a,**k);ready.set();assert release.wait(5);return result
    monkeypatch.setattr(module,"extract_pdf",delay)
    def index():
        try:library.index_pdf(str(uuid4()),identity,python=pdf_python)
        except LiteratureError as e:errors.append(e.code)
    worker=threading.Thread(target=index);worker.start();assert ready.wait(15)
    Library(library.root).revoke(str(uuid4()),identity)
    assert library.search("zircon")["hits"]==[]
    with pytest.raises(LiteratureError) as caught:library.resolve(citation)
    assert caught.value.code=="authorization_revoked"
    release.set();worker.join(10);assert not worker.is_alive()
    assert errors==["authorization_revoked"]
    with sqlite3.connect(library.path) as db:assert db.execute("SELECT count(*) FROM extractions").fetchone()[0]==1


def test_changed_frozen_pdf_or_geometry_is_not_rebound_to_existing_citation(tmp_path,pdf_python):
    library,identity,_=_ready(tmp_path,pdf_python);citation=library.search("zircon")["hits"][0]["citation"]
    with sqlite3.connect(library.path) as db:
        row=db.execute("SELECT evidence FROM pages WHERE page_index=1").fetchone()[0]
        page=json.loads(row);page["characters"][0]["box"][0]+=1
        db.execute("UPDATE pages SET evidence=? WHERE page_index=1",(json.dumps(page),))
    with pytest.raises(LiteratureError) as caught:library.resolve(citation)
    assert caught.value.code=="citation_mismatch"


def test_failed_parser_does_not_publish_partial_generation_and_same_id_never_restarts(tmp_path,pdf_python,monkeypatch):
    import suan.literature.store as module
    source=tmp_path/"damaged.pdf";source.write_bytes(b"%PDF-1.7\ninvalid")
    library=Library(tmp_path/"library");identity=_import(library,source)["receipt"]["version_id"]
    before=library.info();op=str(uuid4())
    with pytest.raises(LiteratureError):library.index_pdf(op,identity,python=pdf_python)
    assert library.info()==before
    assert library.operation(op)["state"]=="uncertain"
    monkeypatch.setattr(module,"extract_pdf",lambda *a,**k:pytest.fail("Unknown operation replayed"))
    assert library.index_pdf(op,identity,python=pdf_python)["state"]=="uncertain"


def test_index_capacity_rejection_is_atomic_after_actual_parser(tmp_path,pdf_python,monkeypatch):
    import suan.literature.store as module
    source=tmp_path/"owned.pdf";source.write_bytes(make_pdf([["Index all or publish none"]]))
    library=Library(tmp_path/"library");identity=_import(library,source)["receipt"]["version_id"];before=library.info()
    monkeypatch.setattr(module,"MAX_PARAGRAPHS",0)
    with pytest.raises(LiteratureError) as caught:library.index_pdf(str(uuid4()),identity,python=pdf_python)
    assert caught.value.code=="index_budget"
    assert library.info()==before
    assert library.search("publish")["hits"]==[]
    with sqlite3.connect(library.path) as db:
        assert all(db.execute("SELECT count(*) FROM "+table).fetchone()[0]==0 for table in ("extractions","pages","paragraphs","paragraph_fts"))


def test_withdrawn_version_cannot_be_revived_by_duplicate_new_import(tmp_path):
    source=tmp_path/"owned.pdf";source.write_bytes(make_pdf([["No implicit authorization revival"]]))
    library=Library(tmp_path/"library");document=str(uuid4());first=_import(library,source,document=document)
    identity=first["receipt"]["version_id"];library.revoke(str(uuid4()),identity)
    with pytest.raises(LiteratureError) as caught:_import(library,source,document=document)
    assert caught.value.code=="version_conflict"
    assert library.versions()[0]["active"] is False


def test_frozen_source_bytes_are_verified_on_every_citation_open(tmp_path,pdf_python):
    library,identity,_=_ready(tmp_path,pdf_python);citation=library.search("zircon")["hits"][0]["citation"]
    source=library._object(citation["source_sha256"])
    source.write_bytes(make_pdf([["Replaced frozen bytes"]]))
    with pytest.raises(LiteratureError) as caught:library.resolve(citation)
    assert caught.value.code=="source_changed"


def test_no_text_page_incompleteness_remains_visible_in_search(tmp_path,pdf_python):
    library,identity,_=_ready(tmp_path,pdf_python,pages=[["Incomplete paper still has this evidence"],[]])
    hit=library.search("Incomplete paper")["hits"][0]
    assert hit["text_status"]=="incomplete"
    assert hit["structure_status"]=="unreviewed"


def _batch_citations(library):
    with library._db() as db:
        rows = db.execute("""SELECT p.*,v.source_sha256 FROM paragraphs p JOIN versions v ON v.id=p.version_id
            WHERE v.active=1 AND v.current_extraction=p.extraction_id ORDER BY p.version_id,p.page_index,p.start""").fetchall()
        return [library._citation(row, row["source_sha256"]) for row in rows]


def test_resolve_many_matches_single_geometry_order_duplicates_and_distinct_hashes(tmp_path, pdf_python, monkeypatch):
    import suan.literature.store as module
    library, _, source = _ready(tmp_path, pdf_python, pages=[["First evidence span", "Second evidence span"], ["Last page exact geometry"]])
    # An independent version can share a frozen source/extraction; a second PDF cannot.
    shared = _import(library, source)["receipt"]["version_id"]
    library.index_pdf(str(uuid4()), shared, python=pdf_python)
    other = tmp_path / "other.pdf"; other.write_bytes(make_pdf([["Distinct source evidence"]]))
    different = _import(library, other)["receipt"]["version_id"]
    library.index_pdf(str(uuid4()), different, python=pdf_python)
    citations = _batch_citations(library)
    selected = [citations[-1], citations[0], *citations, citations[0]]
    expected = [library.resolve(citation) for citation in selected]
    with library._db() as db:
        raw = {row[0] for row in db.execute("SELECT proof FROM extractions")}
        raw.update(row[0] for row in db.execute("SELECT evidence FROM pages"))
    decoded, verified = dict.fromkeys(raw, 0), []
    loads, verify = module.json.loads, library._verify_object
    def count_decode(value, *args, **kwargs):
        if type(value) is str and value in decoded: decoded[value] += 1
        return loads(value, *args, **kwargs)
    def count_hash(sha, size):
        assert library._gate.connections == 0
        verified.append((sha, size)); return verify(sha, size)
    monkeypatch.setattr(module.json, "loads", count_decode)
    monkeypatch.setattr(library, "_verify_object", count_hash)
    resolved = library.resolve_many(selected)
    assert resolved == expected
    assert len(verified) == len(set(verified)) == 2
    assert set(decoded.values()) == {1}
    resolved[1]["page"]["page_box"][0] += 1
    assert resolved[-1] == expected[-1], "Duplicate output positions must not share mutable page values"
    assert library.resolve_many(selected) == expected
    assert len(verified) == 4, "A later call must perform fresh complete source validation"


def test_resolve_many_rechecks_withdrawal_after_actual_hash_without_database_lease(tmp_path, pdf_python, monkeypatch):
    library, identity, _ = _ready(tmp_path, pdf_python)
    citations = _batch_citations(library); ready, release, revoked = threading.Event(), threading.Event(), threading.Event()
    verify = library._verify_object; results, errors, withdrawal_errors = [], [], []
    def pause(sha, size):
        assert library._gate.connections == 0
        verify(sha, size); ready.set(); assert release.wait(10)
    def resolve():
        try: results.append(library.resolve_many(citations))
        except LiteratureError as error: errors.append(error.code)
    def withdraw():
        try: Library(library.root).revoke(str(uuid4()), identity)
        except Exception as error: withdrawal_errors.append(type(error).__name__)
        finally: revoked.set()
    monkeypatch.setattr(library, "_verify_object", pause)
    resolver = threading.Thread(target=resolve); resolver.start(); assert ready.wait(15)
    revoker = threading.Thread(target=withdraw); revoker.start()
    try:
        assert revoked.wait(5), "A source-hashing wait retained a database lease"
        assert not withdrawal_errors
    finally:
        release.set(); resolver.join(10); revoker.join(10)
    assert not resolver.is_alive() and not revoker.is_alive()
    assert results == [] and errors == ["authorization_revoked"]


@pytest.mark.parametrize("kind", ["replace", "in_place"])
def test_resolve_many_rechecks_original_database_after_actual_hash(tmp_path, pdf_python, monkeypatch, kind):
    library, _, source = _ready(tmp_path, pdf_python)
    citations = _batch_citations(library)
    replacement = Library(tmp_path / "replacement"); _import(replacement, source)
    assert library.info()["database_id"] != replacement.info()["database_id"]
    verify = library._verify_object
    def replace(sha, size):
        verify(sha, size)
        assert library._gate.connections == 0
        if kind == "replace": replacement.path.replace(library.path)
        else: library.path.write_bytes(replacement.path.read_bytes())
    monkeypatch.setattr(library, "_verify_object", replace)
    with pytest.raises(LiteratureError) as caught: library.resolve_many(citations)
    assert caught.value.code == "storage_error"


def test_resolve_many_rejects_changed_frozen_source_for_whole_batch(tmp_path, pdf_python, monkeypatch):
    library, _, _ = _ready(tmp_path, pdf_python); citations = _batch_citations(library)
    verify = library._verify_object
    def change(sha, size):
        library._object(sha).write_bytes(make_pdf([["Changed captured source"]]))
        verify(sha, size)
    monkeypatch.setattr(library, "_verify_object", change)
    with pytest.raises(LiteratureError) as caught: library.resolve_many(citations)
    assert caught.value.code == "source_changed"


def test_resolve_many_rejects_corrupted_shared_page_for_whole_batch(tmp_path, pdf_python, monkeypatch):
    library, _, _ = _ready(tmp_path, pdf_python, pages=[["First exact span", "Second exact span"]])
    citations = _batch_citations(library); assert len(citations) == 2
    with library._db(write=True) as db:
        page = json.loads(db.execute("SELECT evidence FROM pages WHERE page_index=0").fetchone()[0])
        page["characters"][0]["box"][0] += 1
        db.execute("UPDATE pages SET evidence=? WHERE page_index=0", (json.dumps(page),))
    monkeypatch.setattr(library, "_verify_object", lambda *args: pytest.fail("Corrupt page reached source hashing"))
    with pytest.raises(LiteratureError) as caught: library.resolve_many(citations)
    assert caught.value.code == "citation_mismatch"


def test_resolve_many_retains_exact_citations_after_unrelated_generation_advances(tmp_path, pdf_python):
    library, _, _ = _ready(tmp_path, pdf_python); citations = _batch_citations(library)
    expected = [library.resolve(citation) for citation in citations]; generation = library.info()["generation"]
    other = tmp_path / "new.pdf"; other.write_bytes(make_pdf([["Unrelated later approved document"]]))
    identity = _import(library, other)["receipt"]["version_id"]
    library.index_pdf(str(uuid4()), identity, python=pdf_python)
    assert library.info()["generation"] > generation
    assert Library(library.root).resolve_many(citations) == expected


@pytest.mark.parametrize("kind", ["none", "tuple", "count", "deep", "surrogate", "boolean", "extra", "dict_subclass", "list_subclass"])
def test_resolve_many_closed_input_guards_precede_any_storage(tmp_path, monkeypatch, kind):
    citation = {"format": "stk.literature-citation/1", "version_id": str(uuid4()), "source_sha256": "a"*64,
                "extraction_id": "b"*64, "paragraph_id": "c"*64, "text_sha256": "d"*64, "page_index": 0, "start": 0, "end": 1}
    supplied = [citation]
    if kind == "none": supplied = None
    elif kind == "tuple": supplied = (citation,)
    elif kind == "count": supplied = [citation]*257
    elif kind == "deep":
        nested = []; nested.append(nested); citation["source_sha256"] = nested
    elif kind == "surrogate": citation["version_id"] = "\ud800"*36
    elif kind == "boolean": citation["start"] = False
    elif kind == "extra": citation["extra"] = True
    elif kind == "dict_subclass":
        class CallerDictionary(dict): pass
        supplied = [CallerDictionary(citation)]
    else:
        class CallerList(list): pass
        supplied = CallerList(supplied)
    library = Library(tmp_path / "absent")
    monkeypatch.setattr(library, "_db", lambda *args, **kwargs: pytest.fail("Invalid citation opened storage"))
    with pytest.raises(LiteratureError) as caught: library.resolve_many(supplied)
    assert caught.value.code == ("citation_budget" if kind == "count" else "invalid_data")
    assert not library.root.exists()


@pytest.mark.parametrize("kind", ["characters", "response_bytes", "evidence_bytes"])
def test_resolve_many_aggregate_budgets_precede_hashing_and_preserve_state(tmp_path, pdf_python, monkeypatch, kind):
    import suan.literature.store as module
    library, _, _ = _ready(tmp_path, pdf_python, pages=[["Retained exact evidence "*24]])
    citation = _batch_citations(library)[0]
    expected = library.resolve(citation); before = library.path.read_bytes()
    selected = [citation]
    if kind == "characters":
        assert len(expected["text"])*256 > 65536
        selected *= 256
    elif kind == "response_bytes": monkeypatch.setattr(module, "MAX_CITATION_RESPONSE_BYTES", len(module.canonical([expected]))-1)
    else: monkeypatch.setattr(module, "MAX_CITATION_EVIDENCE_BYTES", 32)
    monkeypatch.setattr(library, "_verify_object", lambda *args: pytest.fail("Over-budget response reached PDF hashing"))
    with pytest.raises(LiteratureError) as caught: library.resolve_many(selected)
    assert caught.value.code == "citation_budget"
    assert library.path.read_bytes() == before


def test_resolve_many_empty_is_passive_and_later_permission_is_not_cached(tmp_path, pdf_python, monkeypatch):
    absent = Library(tmp_path / "absent")
    monkeypatch.setattr(absent, "_db", lambda *args, **kwargs: pytest.fail("Empty batch opened storage"))
    assert absent.resolve_many([]) == [] and not absent.root.exists()
    populated = tmp_path / "populated"; populated.mkdir()
    library, identity, _ = _ready(populated, pdf_python)
    citations = _batch_citations(library); verify = library._verify_object; hashes = []
    def count(sha, size): hashes.append(sha); return verify(sha, size)
    monkeypatch.setattr(library, "_verify_object", count)
    first = library.resolve_many(citations); assert library.resolve_many(citations) == first
    assert len(hashes) == 2
    Library(library.root).revoke(str(uuid4()), identity)
    with pytest.raises(LiteratureError) as caught: library.resolve_many(citations)
    assert caught.value.code == "authorization_revoked" and len(hashes) == 2
