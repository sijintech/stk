"""Revision-bound snapshot pages carry only bounded metadata, never complete manifests."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import sqlite3
from uuid import UUID, uuid4, uuid5

import pytest

from suan.agent.levels import OPERATIONS, TOOL_USES
from suan.desktop_bridge.schema import validate_params
from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import snapshots as module
from suan.scripting import API, Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


METHOD = "project.snapshots.list_summaries"
SUMMARY_KEYS = {"id", "kind", "revision", "sha256", "created_at", "file_count"}


@pytest.fixture
def captured(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Snapshot pages")
    path = store.directory / "report.md"
    path.write_text("# Frozen\n", encoding="utf-8")
    record = store.files.index([str(path)], expected_revision=0)["record_ids"][0]
    snapshot = store.snapshots.capture([record], expected_revision=1)["snapshot"]
    return store, snapshot


def append_rows(store, original, count):
    """Populate valid append-only historical metadata without repeatedly copying the same bytes."""
    result = [original["id"]]
    with sqlite3.connect(store.path) as db:
        for source_revision in range(2, count + 1):
            manifest = deepcopy(original["manifest"])
            manifest["source_revision"] = source_revision
            encoded = module._canonical(manifest)
            digest = hashlib.sha256(encoded.encode()).hexdigest()
            identity = str(uuid5(UUID(store._project_id), digest))
            db.execute("INSERT INTO project_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                       (identity, "files", digest, encoded, original["created_at"], source_revision + 1))
            result.append(identity)
        db.execute("UPDATE project SET revision=?", (count + 1,))
    return result


def test_empty_summary_reads_do_not_create_tables_or_advance_history(tmp_path):
    store = ProjectStore.create(tmp_path / "empty", "Empty")
    before = store.history()
    assert store.snapshots.list_summaries(expected_revision=0) == {
        "revision": 0, "offset": 0, "total": 0, "snapshots": []}
    assert store.history() == before and store.info()["revision"] == 0


def test_summary_is_exact_metadata_and_legacy_list_get_are_unchanged(captured, monkeypatch):
    store, snapshot = captured
    expected = {key: snapshot[key] for key in SUMMARY_KEYS - {"file_count"}}
    expected["file_count"] = 1
    before = store.history()
    old_list = store.snapshots.list()
    with monkeypatch.context() as patch:
        patch.setattr(module.Snapshots, "_decode", lambda *a: pytest.fail("summary decoded a complete manifest"))
        patch.setattr(module.Snapshots, "_object", lambda *a, **k: pytest.fail("summary opened an asset"))
        first = store.snapshots.list_summaries(expected_revision=2, limit=1)
        assert first == {"revision": 2, "offset": 0, "total": 1, "snapshots": [expected]}
        assert store.snapshots.list_summaries(expected_revision=2, limit=1) == first
        assert store.snapshots.list_summaries(expected_revision=2, offset=1)["snapshots"] == []
        assert store.snapshots.list_summaries(expected_revision=2, offset=2**63 - 1)["snapshots"] == []
    assert store.snapshots.list() == old_list and store.snapshots.get(snapshot["id"]) == snapshot
    assert store.history() == before and store.info()["revision"] == 2


@pytest.mark.parametrize("selection", [
    {"expected_revision": True}, {"expected_revision": -1}, {"expected_revision": 2.0},
    {"expected_revision": "2"}, {"expected_revision": 2**63},
    {"offset": True}, {"offset": -1}, {"offset": 1.0}, {"offset": 2**63},
    {"limit": True}, {"limit": 0}, {"limit": 65}, {"limit": 1.0}, {"limit": "1"},
])
def test_invalid_pages_are_rejected_before_opening_the_database(captured, monkeypatch, selection):
    store, _ = captured
    monkeypatch.setattr(store, "_connect", lambda **kw: pytest.fail("invalid pagination opened SQLite"))
    with pytest.raises(ProjectError):
        store.snapshots.list_summaries(**{"expected_revision": 2, **selection})


def test_stale_page_is_rejected_without_mutation(captured):
    store, _ = captured
    store.apply([{"op": "create_table", "id": str(uuid4()), "name": "Later"}], expected_revision=2)
    history = store.history()
    with pytest.raises(RevisionConflict):
        store.snapshots.list_summaries(expected_revision=2)
    assert store.info()["revision"] == 3 and store.history() == history


def test_large_collection_pages_are_stable_and_never_return_or_decode_manifests(captured, monkeypatch):
    store, snapshot = captured
    identities = append_rows(store, snapshot, 1025)
    connect = store._connect

    @contextmanager
    def bounded_rows(**kwargs):
        with connect(**kwargs) as db:
            def factory(cursor, row):
                assert all(column[0] != "manifest" for column in cursor.description)
                return sqlite3.Row(cursor, row)
            db.row_factory = factory
            yield db

    monkeypatch.setattr(store, "_connect", bounded_rows)
    monkeypatch.setattr(module.Snapshots, "_decode", lambda *a: pytest.fail("full manifest materialized"))
    observed = []
    for offset in range(0, 1025, 64):
        page = store.snapshots.list_summaries(expected_revision=1026, offset=offset)
        assert page["revision"] == 1026 and page["total"] == 1025 and page["offset"] == offset
        assert len(page["snapshots"]) <= 64
        assert all(set(item) == SUMMARY_KEYS for item in page["snapshots"])
        assert len(json.dumps(page).encode()) < 64 * 1024
        assert store.snapshots.list_summaries(expected_revision=1026, offset=offset) == page
        observed.extend(item["id"] for item in page["snapshots"])
    assert observed == identities and len(set(observed)) == 1025


def test_revision_count_and_page_share_one_sqlite_read_snapshot(captured, monkeypatch):
    store, snapshot = captured
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connect = store._connect
    changed = False

    class ConcurrentWriter:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, args=()):
            nonlocal changed
            cursor = self.db.execute(sql, args)
            if sql == "SELECT count(*) FROM project_snapshots" and not changed:
                changed = True
                append_rows(store, snapshot, 2)
            return cursor

    @contextmanager
    def connected(**kwargs):
        with connect(**kwargs) as db:
            yield ConcurrentWriter(db)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_connect", connected)
        page = store.snapshots.list_summaries(expected_revision=2)
    assert changed and page["revision"] == 2 and page["total"] == 1
    assert [item["id"] for item in page["snapshots"]] == [snapshot["id"]]
    with pytest.raises(RevisionConflict):
        store.snapshots.list_summaries(expected_revision=2)
    assert store.snapshots.list_summaries(expected_revision=3)["total"] == 2


@pytest.mark.parametrize("damage", ["json", "empty_files", "too_many_files", "foreign_project",
                                    "future_source", "oversized", "id", "uuid_mismatch", "sha256",
                                    "sha256_mismatch", "created_at", "revision"])
def test_corrupt_selected_row_fails_without_skipping_or_poisoning_other_pages(captured, damage):
    store, snapshot = captured
    ids = append_rows(store, snapshot, 3)
    with sqlite3.connect(store.path) as db:
        if damage in {"id", "uuid_mismatch", "sha256", "sha256_mismatch", "created_at", "revision"}:
            column = {"uuid_mismatch": "id", "sha256_mismatch": "sha256"}.get(damage, damage)
            value = {"id": "invalid", "uuid_mismatch": str(uuid4()), "sha256": "bad",
                     "sha256_mismatch": "0" * 64, "created_at": "not-a-date", "revision": 100}[damage]
            db.execute(f"UPDATE project_snapshots SET {column}=? WHERE id=?", (value, ids[1]))
        else:
            manifest = json.loads(db.execute("SELECT manifest FROM project_snapshots WHERE id=?", (ids[1],)).fetchone()[0])
            if damage == "empty_files": manifest["files"] = []
            elif damage == "too_many_files": manifest["files"] *= 101
            elif damage == "foreign_project": manifest["project_id"] = str(uuid4())
            elif damage == "future_source": manifest["source_revision"] = 100
            raw = "{" if damage == "json" else " " * (module.MAX_SUMMARY_MANIFEST_BYTES + 1) if damage == "oversized" else module._canonical(manifest)
            db.execute("UPDATE project_snapshots SET manifest=? WHERE id=?", (raw, ids[1]))
    assert store.snapshots.list_summaries(expected_revision=4, offset=0, limit=1)["snapshots"][0]["id"] == ids[0]
    with pytest.raises(ProjectError, match="Invalid input snapshot summary"):
        store.snapshots.list_summaries(expected_revision=4, offset=1, limit=1)
    page = store.snapshots.list_summaries(expected_revision=4, offset=2, limit=1)
    assert page["total"] == 3 and page["snapshots"][0]["id"] == ids[2]


def test_summary_is_not_a_full_manifest_checksum_verdict(captured):
    store, snapshot = captured
    manifest = deepcopy(snapshot["manifest"])
    manifest["files"][0]["name"] = "changed-name.md"
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_snapshots SET manifest=? WHERE id=?", (module._canonical(manifest), snapshot["id"]))
    assert store.snapshots.list_summaries(expected_revision=2)["snapshots"][0]["sha256"] == snapshot["sha256"]
    with pytest.raises(ProjectError, match="identity/checksum"):
        store.snapshots.get(snapshot["id"])


def test_real_bridge_and_facade_are_discoverable_read_only_and_handle_bound(captured, inproc):
    store, snapshot = captured
    harness = inproc()
    info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    project = Project(harness.call, info["handle"])
    assert METHOD in harness.call("hello", {"protocol": 1})["methods"]
    assert METHOD in harness.call("script.catalog")["operations"]
    assert OPERATIONS[METHOD][0] == "read" and not any(METHOD in uses for uses in TOOL_USES.values())
    history, events = store.history(), harness.events_of("project.changed")
    page = project.snapshots.list_summaries(expected_revision=2, limit=1)
    assert page == store.snapshots.list_summaries(expected_revision=2, limit=1)
    assert project.snapshots.get(snapshot["id"]) == snapshot
    assert harness.error(METHOD, {"handle": info["handle"], "expected_revision": 1})["code"] == "conflict"
    assert harness.error(METHOD, {"handle": info["handle"], "expected_revision": 2, "limit": 65})["code"] == "invalid_params"
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_snapshots SET manifest='{' WHERE id=?", (snapshot["id"],))
    assert harness.error(METHOD, {"handle": info["handle"], "expected_revision": 2})["code"] == "invalid_params"
    assert store.history() == history and harness.events_of("project.changed") == events
    assert project.close()
    assert harness.error(METHOD, {"handle": info["handle"], "expected_revision": 2})["code"] == "not_found"
    harness.assert_clean()


def test_facade_preserves_explicit_revision_and_original_opened_handle():
    calls = []
    api = API(lambda method, params: calls.append((method, params)) or {"snapshots": []})
    api._project_handle = "a" * 32
    frozen = api.project.snapshots
    frozen.list_summaries(expected_revision=7)
    api._project_handle = "b" * 32
    frozen.list_summaries(expected_revision=8, offset=64, limit=2)
    api.project.snapshots.list_summaries(expected_revision=1)
    assert calls == [(METHOD, {"handle": "a" * 32, "expected_revision": 7, "offset": 0, "limit": 64}),
                     (METHOD, {"handle": "a" * 32, "expected_revision": 8, "offset": 64, "limit": 2}),
                     (METHOD, {"handle": "b" * 32, "expected_revision": 1, "offset": 0, "limit": 64})]
    with pytest.raises(TypeError): frozen.list_summaries()
    with pytest.raises(TypeError): frozen.list_summaries(1)
    assert validate_params(METHOD, {"handle": "a" * 32, "expected_revision": 0}) == []
    for changed in ({"expected_revision": True}, {"offset": -1}, {"limit": 65}, {"extra": 1}):
        assert validate_params(METHOD, {"handle": "a" * 32, "expected_revision": 0, **changed})
