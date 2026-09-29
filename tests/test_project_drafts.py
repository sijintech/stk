"""Durable proposals remain separate from editable state and cannot execute twice."""

from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.store import FORMAT_VERSION, UnsupportedProjectFormat


@pytest.fixture
def store(tmp_path):
    return ProjectStore.create(tmp_path / "project", "Drafts")


def save(store, commands=None, **kwargs):
    return store.drafts.save(commands if commands is not None else [{"op": "create_table", "name": "拟议参数"}],
                             **{"expected_revision": store.info()["revision"], "title": "待检查的修改",
                                "draft_id": str(uuid4()), **kwargs})


def test_save_reopens_with_stable_ids_without_editing_or_losing_redo(store):
    store.apply([{"op": "create_table", "name": "undo me"}], expected_revision=0)
    store.undo(expected_revision=1)
    before, history = store.snapshot(), store.history()
    commands = [{"op": "create_table", "name": "保存草案"}]
    draft = save(store, commands)
    assert "id" not in commands[0]
    assert draft["commands"][0]["id"]
    assert draft["base_revision"] == 2 and draft["project_id"] == before["project"]["id"]
    assert draft["status"] == "pending" and draft["applied_revision"] is None and draft["closed_at"] is None
    assert set(draft) == {"id", "project_id", "title", "base_revision", "commands", "created_at", "status", "applied_revision", "closed_at"}
    assert ProjectStore(store.directory).drafts.get(draft["id"]) == draft
    assert store.snapshot() == before and store.history() == history
    assert before["edit_history"]["redo_revision"] == 1
    assert store.drafts.list()["drafts"] == [{key: value for key, value in draft.items() if key != "commands"}]


def test_save_retry_uses_original_request_even_after_apply_and_revision_advance(store):
    original = [{"op": "create_table", "name": "Generated UUID"}]
    identity = str(uuid4())
    draft = save(store, original, draft_id=identity)
    assert save(store, original, draft_id=identity) == draft
    applied = store.drafts.apply(identity, expected_revision=0)
    assert save(store, original, draft_id=identity, expected_revision=0) == applied["draft"]
    for changed in ({"title": "changed"}, {"expected_revision": 1}):
        with pytest.raises(RevisionConflict, match="different request"):
            save(store, original, draft_id=identity, **changed)
    with pytest.raises(RevisionConflict, match="different request"):
        save(store, [{"op": "create_table", "name": "Other"}], draft_id=identity, expected_revision=0)
    assert len(store.drafts.list()["drafts"]) == 1


def test_lost_apply_response_recovers_after_reopen_and_undo_without_reexecuting(store):
    draft = save(store)
    first = store.drafts.apply(draft["id"], expected_revision=0)
    assert first["revision"] == 1 and first["replayed"] is False
    assert first["draft"]["status"] == "applied" and first["draft"]["applied_revision"] == 1
    assert store.snapshot()["tables"][0]["id"] == draft["commands"][0]["id"]
    assert store.history()[0]["commands"] == draft["commands"]
    reopened = ProjectStore(store.directory)
    assert reopened.drafts.apply(draft["id"], expected_revision=0) == {**first, "replayed": True}
    reopened.undo(expected_revision=1)
    assert reopened.snapshot()["tables"] == []
    history = reopened.history()
    assert reopened.drafts.apply(draft["id"], expected_revision=0) == {**first, "replayed": True}
    assert reopened.info()["revision"] == 2 and reopened.history() == history
    assert reopened.snapshot()["tables"] == []
    reopened.redo(expected_revision=2)
    assert reopened.drafts.get(draft["id"]) == first["draft"]
    with pytest.raises(RevisionConflict, match="base revision"):
        reopened.drafts.apply(draft["id"], expected_revision=3)
    with pytest.raises(RevisionConflict, match="cannot be discarded"):
        reopened.drafts.discard(draft["id"])


def test_discard_is_durable_idempotent_and_does_not_edit_project(store):
    draft = save(store)
    before, history = store.snapshot(), store.history()
    discarded = store.drafts.discard(draft["id"])
    assert discarded["status"] == "discarded" and discarded["closed_at"] and discarded["applied_revision"] is None
    assert ProjectStore(store.directory).drafts.discard(draft["id"]) == discarded
    with pytest.raises(RevisionConflict, match="discarded"):
        store.drafts.apply(draft["id"], expected_revision=0)
    assert store.snapshot() == before and store.history() == history


def test_stale_draft_is_not_rebased_and_rejected_apply_keeps_it_pending(store):
    draft = save(store)
    with pytest.raises(RevisionConflict, match="base revision"):
        store.drafts.apply(draft["id"], expected_revision=1)
    store.apply([{"op": "create_table", "name": "Another edit"}], expected_revision=0)
    before, history = store.snapshot(), store.history()
    with pytest.raises(RevisionConflict, match="current revision"):
        store.drafts.apply(draft["id"], expected_revision=0)
    assert store.drafts.get(draft["id"]) == draft
    with pytest.raises(RevisionConflict):
        save(store, expected_revision=0)
    assert store.snapshot() == before and store.history() == history


def test_two_connections_apply_once(store):
    draft = save(store)
    ready = threading.Barrier(2)
    def apply(_):
        other = ProjectStore(store.directory)
        ready.wait(timeout=5)
        return other.drafts.apply(draft["id"], expected_revision=0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, range(2)))
    assert sorted(result["replayed"] for result in results) == [False, True]
    assert results[0]["draft"] == results[1]["draft"]
    assert store.info()["revision"] == 1 and len(store.history()) == 1
    assert len(store.snapshot()["tables"]) == 1


def test_concurrent_save_same_request_returns_one_frozen_command_set(store, monkeypatch):
    ready = threading.Barrier(2)
    original = ProjectStore.preview
    def preview(instance, *args, **kwargs):
        result = original(instance, *args, **kwargs)
        ready.wait(timeout=5)
        return result
    monkeypatch.setattr(ProjectStore, "preview", preview)
    identity = str(uuid4())
    def create(_):
        return save(ProjectStore(store.directory), draft_id=identity)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, range(2)))
    assert results[0] == results[1]
    assert len(store.drafts.list()["drafts"]) == 1 and store.info()["revision"] == 0


def test_concurrent_editor_advance_during_save_preview_prevents_insert(store, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = store.preview
    def preview(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(10)
        return result
    monkeypatch.setattr(store, "preview", preview)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(save, store)
        try:
            assert entered.wait(5)
            ProjectStore(store.directory).apply([{"op": "create_table", "name": "Another edit"}], expected_revision=0)
        finally:
            release.set()
        with pytest.raises(RevisionConflict):
            pending.result(timeout=5)
    assert store.drafts.list()["drafts"] == []
    assert [table["name"] for table in store.snapshot()["tables"]] == ["Another edit"]


def test_save_recovers_identical_request_applied_just_before_its_preview(store, monkeypatch):
    identity = str(uuid4())
    original = store.preview
    winner = None
    def preview(*args, **kwargs):
        nonlocal winner
        other = ProjectStore(store.directory)
        save(other, draft_id=identity)
        winner = other.drafts.apply(identity, expected_revision=0)["draft"]
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "preview", preview)
    assert save(store, draft_id=identity) == winner
    assert store.info()["revision"] == 1 and len(store.drafts.list()["drafts"]) == 1


def test_failed_terminal_write_rolls_back_model_revision_history_and_undo(store):
    draft = save(store)
    before, history = store.snapshot(), store.history()
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER reject_resolution BEFORE UPDATE ON project_drafts
                    BEGIN SELECT RAISE(ABORT, 'resolution unavailable'); END""")
    with pytest.raises(ProjectError, match="resolution unavailable"):
        store.drafts.apply(draft["id"], expected_revision=0)
    assert store.snapshot() == before and store.history() == history
    assert store.drafts.get(draft["id"]) == draft
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER reject_resolution")
    assert store.drafts.apply(draft["id"], expected_revision=0)["replayed"] is False


@pytest.mark.parametrize("commands", [[], [{"op": "task.submit"}],
    [{"op": "create_table", "name": "partial"}, {"op": "bad"}],
    [{"op": "create_table", "name": "x"}] * 1001,
    [{"op": "create_table", "name": "x", "payload": "汉" * 90000}],
    [{"op": "create_table", "name": "x", "payload": float("nan")}],
    [{"op": "create_table", "name": "\ud800"}]])
def test_invalid_or_oversize_commands_never_save_or_edit(store, commands):
    with pytest.raises(ProjectError):
        save(store, commands)
    assert store.drafts.list()["drafts"] == [] and store.snapshot()["tables"] == [] and store.history() == []


def test_normalized_commands_also_respect_storage_budget(store):
    # Raw JSON is below the limit; freezing 1000 generated UUIDs takes it over.
    commands = [{"op": "create_table", "name": "x" * 225}] * 1000
    assert len(json.dumps(commands, separators=(",", ":")).encode()) < 256 * 1024
    with pytest.raises(ProjectError, match="256 KiB"):
        save(store, commands)
    assert store.info()["revision"] == 0 and store.drafts.list()["drafts"] == []


@pytest.mark.parametrize("kwargs", [{"draft_id": "not-a-uuid"}, {"title": ""}, {"title": "x" * 1025},
                                   {"title": "\ud800"}, {"expected_revision": True}, {"expected_revision": -1}])
def test_invalid_identity_title_or_revision_is_rejected(store, kwargs):
    with pytest.raises(ProjectError):
        save(store, **kwargs)
    assert store.drafts.list()["drafts"] == []


def test_list_paginates_creation_order_without_commands(store):
    drafts = [save(store, title=str(i)) for i in range(3)]
    store.drafts.discard(drafts[0]["id"])
    first = store.drafts.list(limit=2)
    assert [row["id"] for row in first["drafts"]] == [row["id"] for row in drafts[:2]]
    assert all("commands" not in row for row in first["drafts"])
    assert first["next_offset"] == 2
    last = store.drafts.list(offset=2, limit=2)
    assert [row["id"] for row in last["drafts"]] == [drafts[2]["id"]] and last["next_offset"] is None
    assert store.drafts.list(offset=3) == {"drafts": [], "next_offset": None}
    for kwargs in ({"offset": -1}, {"offset": True}, {"limit": 0}, {"limit": 101}, {"limit": False}):
        with pytest.raises(ProjectError):
            store.drafts.list(**kwargs)


@pytest.mark.parametrize("column,value", [("commands", "[]"), ("title", "tampered"),
                                         ("commands", '[{"op":"create_table","name":"Missing frozen ID"}]'),
                                         ("request_sha256", "a" * 64), ("sha256", "b" * 64)])
def test_corrupt_immutable_draft_is_rejected_without_edits(store, column, value):
    draft = save(store)
    with sqlite3.connect(store.path) as db:
        db.execute(f"UPDATE project_drafts SET {column}=? WHERE id=?", (value, draft["id"]))
    for operation in (lambda: store.drafts.get(draft["id"]), lambda: store.drafts.list(),
                      lambda: store.drafts.apply(draft["id"], expected_revision=0)):
        with pytest.raises(ProjectError, match="stored project draft"):
            operation()
    assert store.info()["revision"] == 0 and store.history() == []


def test_replaced_project_identity_cannot_resolve_prior_draft(store):
    draft = save(store)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project SET id=?", (str(uuid4()),))
    with pytest.raises(ProjectError, match="replaced"):
        store.drafts.apply(draft["id"], expected_revision=0)


def test_missing_draft_is_reported_without_creating_any_metadata(store):
    missing = str(uuid4())
    for operation in (lambda: store.drafts.get(missing), lambda: store.drafts.discard(missing),
                      lambda: store.drafts.apply(missing, expected_revision=0)):
        with pytest.raises(ProjectError, match="not found"):
            operation()
    assert store.drafts.list()["drafts"] == []


def legacy_five(store):
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS project_requests")
        db.execute("DROP TABLE project_proposals")
        db.execute("DROP TABLE project_messages")
        db.execute("DROP TABLE project_contexts")
        db.execute("DROP TABLE project_drafts")
        db.execute("PRAGMA user_version=5")


def test_format_five_upgrade_backs_up_and_preserves_existing_state(store, tmp_path):
    store.apply([{"op": "create_table", "name": "Keep"}], expected_revision=0)
    before, history = store.snapshot(), store.history()
    legacy_five(store)
    with pytest.raises(UnsupportedProjectFormat, match="format 6"):
        save(store)
    with pytest.raises(UnsupportedProjectFormat, match="format 6"):
        store.drafts.list()
    result = store.upgrade(expected_revision=1)
    assert result["format_version"] == FORMAT_VERSION and result["revision"] == 2
    assert store.snapshot()["tables"] == before["tables"] and store.history()[:-1] == history
    assert store.snapshot()["edit_history"] == before["edit_history"]
    restored = tmp_path / "old-project"
    restored.mkdir()
    shutil.copyfile(result["backup"]["path"], restored / "project.sqlite3")
    old = ProjectStore(restored)
    assert old.info()["format_version"] == 5 and old.info()["revision"] == 1
    assert old.snapshot()["tables"] == before["tables"] and old.history() == history
    with sqlite3.connect(old.path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='project_drafts'").fetchone() is None
    assert store.drafts.list()["drafts"] == [] and save(store)["base_revision"] == 2
    store.undo(expected_revision=2)
    assert store.snapshot()["tables"] == []


def test_failed_format_six_upgrade_rolls_back_new_schema_and_keeps_verified_backup(store, monkeypatch):
    import suan.project.store as storage
    legacy_five(store)
    monkeypatch.setattr(storage, "_DDL_V6", (*storage._DDL_V6, "invalid SQL"))
    with pytest.raises(ProjectError):
        store.upgrade(expected_revision=0)
    assert store.info()["format_version"] == 5 and store.history() == []
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='project_drafts'").fetchone() is None
    backups = list((store.directory / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA user_version").fetchone()[0] == 5
