"""Selected immutable context snapshots do not read or mutate the complete model."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.contexts import MAX_CONTEXT_BYTES, _encode
from suan.project.store import FORMAT_VERSION, UnsupportedProjectFormat


@pytest.fixture
def model(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Context capture")
    ids = {key: str(uuid4()) for key in ("table", "temperature", "note", "derived", "json", "first", "second")}
    commands = [{"op": "create_table", "id": ids["table"], "name": "Cases"}]
    for key, kind, unit in (("temperature", "number", "K"), ("note", "text", None),
                            ("derived", "number", "K"), ("json", "json", None)):
        commands.append({"op": "add_field", "id": ids[key], "table_id": ids["table"], "name": key, "type": kind, "unit": unit})
    commands.extend({"op": "add_record", "id": ids[key], "table_id": ids["table"]} for key in ("first", "second"))
    commands.extend([cell(ids, "temperature", 300), cell(ids, "note", None),
        {"op": "set_expression", "table_id": ids["table"], "record_id": ids["first"], "field_id": ids["derived"],
         "expression": 'base + quantity(10, "K")', "bindings": {"base": {"record_id": ids["first"], "field_id": ids["temperature"]}}}])
    store.apply(commands, expected_revision=0)
    return store, ids


def cell(ids, field, value, record="first"):
    return {"op": "set_cell", "table_id": ids["table"], "record_id": ids[record], "field_id": ids[field], "value": value}


def capture(model, **kwargs):
    store, ids = model
    return store.contexts.capture(**{"table_id": ids["table"], "record_ids": [ids["first"], ids["second"]],
        "field_ids": [ids["temperature"], ids["note"], ids["derived"]], "expected_revision": store.info()["revision"],
        "title": "检查参数", "context_id": str(uuid4()), **kwargs})


def test_explicit_capture_keeps_absence_null_definitions_and_cached_values(model, monkeypatch):
    store, ids = model
    before, history = store.snapshot(), store.history()
    def forbidden(*args, **kwargs):
        raise AssertionError("capture must not read the complete model or evaluate dependencies")
    monkeypatch.setattr(store, "_snapshot", forbidden)
    monkeypatch.setattr(store, "_model", forbidden)
    context = capture(model)
    assert context["source_revision"] == 1 and context["project_id"] == store.info()["id"]
    content = context["content"]["value"]
    assert content["table"] == {"id": ids["table"], "name": "Cases"}
    assert [field["id"] for field in content["fields"]] == context["selection"]["field_ids"]
    first, second = content["records"]
    assert first["literals"][ids["note"]] == {"state": "included", "value": None}
    assert second["literals"] == {} and ids["derived"] not in first["literals"]
    assert first["definitions"][ids["derived"]]["value"]["kind"] == "expression"
    assert first["evaluations"][ids["derived"]]["value"]["value"] == 310
    assert context["diagnostics"] == {"table_missing": False, "record_ids": [], "field_ids": []}
    assert context["omitted_values"] == 0
    assert context["content"]["size_bytes"] == len(_encode(content))
    assert context["content"]["sha256"] == hashlib.sha256(_encode(content)).hexdigest()
    assert ProjectStore(store.directory).snapshot() == before and store.history() == history


def test_capture_is_immutable_across_edits_reopen_and_same_request_retry(model):
    store, ids = model
    identity = str(uuid4())
    context = capture(model, context_id=identity)
    store.apply([cell(ids, "temperature", 350), {"op": "rename_table", "id": ids["table"], "name": "Renamed"}], expected_revision=1)
    reopened = ProjectStore(store.directory)
    assert reopened.contexts.get(identity) == context
    assert capture((reopened, ids), context_id=identity, expected_revision=1) == context
    assert context["content"]["value"]["records"][0]["literals"][ids["temperature"]]["value"] == 300
    with pytest.raises(RevisionConflict, match="different request"):
        capture(model, context_id=identity, expected_revision=1, title="Other")
    with pytest.raises(RevisionConflict, match="current revision"):
        capture(model, expected_revision=1)
    assert len(reopened.contexts.list()["contexts"]) == 1


def test_capture_missing_objects_reports_exact_ids_without_guessing(model):
    store, ids = model
    missing_record, missing_field, missing_table = (str(uuid4()) for _ in range(3))
    context = capture(model, record_ids=[ids["first"], missing_record], field_ids=[ids["temperature"], missing_field])
    assert context["diagnostics"] == {"table_missing": False, "record_ids": [missing_record], "field_ids": [missing_field]}
    assert len(context["content"]["value"]["records"]) == len(context["content"]["value"]["fields"]) == 1
    missing = capture(model, table_id=missing_table, record_ids=[missing_record], field_ids=[missing_field])
    assert missing["content"]["value"] == {"table": None, "fields": [], "records": []}
    assert missing["diagnostics"]["table_missing"] is True
    with pytest.raises(ProjectError, match="different table"):
        capture(model, table_id=missing_table)


def test_unselected_field_values_are_not_read_or_embedded(model):
    store, ids = model
    store.apply([cell(ids, "json", "UNSELECTED CONFIDENTIAL DATA")], expected_revision=1)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE cells SET value='{broken' WHERE field_id=?", (ids["json"],))
    context = capture(model, field_ids=[ids["temperature"]])
    serialized = _encode(context)
    assert b"CONFIDENTIAL" not in serialized and ids["json"].encode() not in serialized
    with pytest.raises(ProjectError, match="Invalid selected"):
        capture(model, field_ids=[ids["json"]])


def test_unselected_reference_dependency_is_not_read_but_saved_evaluation_is_captured(model):
    store, ids = model
    context = capture(model, field_ids=[ids["derived"]], record_ids=[ids["first"]])
    row = context["content"]["value"]["records"][0]
    assert row["literals"] == {}
    assert row["evaluations"][ids["derived"]]["value"]["value"] == 310
    # Invalidating a cache never causes context capture to traverse the input.
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE cells SET value='{broken' WHERE field_id=?", (ids["temperature"],))
        db.execute("DELETE FROM evaluations WHERE field_id=?", (ids["derived"],))
    missing = capture(model, field_ids=[ids["derived"]])
    assert missing["omitted_values"] == 1
    assert missing["content"]["value"]["records"][0]["evaluations"][ids["derived"]] == {
        "state": "omitted", "reason": "evaluation_unavailable", "size_bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}


@pytest.mark.parametrize("cached", ['{broken', 'null', '{"state":"ok","value":100}',
                                   '{"state":"error","error":{},"engine_version":1,"evaluated_revision":1}'])
def test_bad_evaluation_cache_is_an_explicit_omission(model, cached):
    store, ids = model
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE evaluations SET result=? WHERE field_id=?", (cached, ids["derived"]))
    context = capture(model, field_ids=[ids["derived"]])
    part = context["content"]["value"]["records"][0]["evaluations"][ids["derived"]]
    assert part == {"state": "omitted", "reason": "evaluation_unavailable", "size_bytes": len(cached.encode()),
                    "sha256": hashlib.sha256(cached.encode()).hexdigest()}
    assert context["omitted_values"] == 1 and store.info()["revision"] == 1


def test_formula_error_is_preserved_as_a_valid_observation(model):
    store, ids = model
    store.apply([{"op": "set_expression", "table_id": ids["table"], "record_id": ids["first"], "field_id": ids["derived"],
                  "expression": "base / 0", "bindings": {"base": {"record_id": ids["first"], "field_id": ids["temperature"]}}}],
                expected_revision=1)
    context = capture(model, field_ids=[ids["derived"]])
    evaluation = context["content"]["value"]["records"][0]["evaluations"][ids["derived"]]
    assert evaluation["state"] == "included" and evaluation["value"]["state"] == "error"
    assert evaluation["value"]["error"]["code"] == "division_by_zero"
    assert context["omitted_values"] == 0


def test_large_value_omission_has_original_stored_size_and_digest(model):
    store, ids = model
    store.apply([cell(ids, "json", {"payload": "汉" * 80000})], expected_revision=1)
    with sqlite3.connect(store.path) as db:
        raw = db.execute("SELECT value FROM cells WHERE field_id=?", (ids["json"],)).fetchone()[0].encode()
    context = capture(model, field_ids=[ids["json"]])
    part = context["content"]["value"]["records"][0]["literals"][ids["json"]]
    assert part == {"state": "omitted", "reason": "value_limit", "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert context["omitted_values"] == 1 and len(_encode(context)) <= MAX_CONTEXT_BYTES


def test_total_context_budget_omits_whole_content_with_identity_not_truncated_text(model):
    store, ids = model
    rows = [ids["first"]] + [str(uuid4()) for _ in range(30)]
    commands = [{"op": "add_record", "table_id": ids["table"], "id": identity} for identity in rows[1:]]
    commands += [{"op": "set_cell", "table_id": ids["table"], "record_id": identity, "field_id": ids["note"],
                  "value": "x" * 12000} for identity in rows]
    store.apply(commands, expected_revision=1)
    context = capture(model, record_ids=rows, field_ids=[ids["note"]])
    assert context["content"]["state"] == "omitted" and context["content"]["reason"] == "context_limit"
    assert context["content"]["size_bytes"] > MAX_CONTEXT_BYTES and len(context["content"]["sha256"]) == 64
    assert "value" not in context["content"] and context["omitted_values"] == 0
    assert context["selection"]["record_ids"] == rows and len(_encode(context)) <= MAX_CONTEXT_BYTES
    assert ProjectStore(store.directory).contexts.get(context["id"]) == context


@pytest.mark.parametrize("kwargs", [{"record_ids": []}, {"field_ids": []}, {"record_ids": [str(uuid4())] * 2},
    {"field_ids": [str(uuid4()) for _ in range(65)]}, {"record_ids": [str(uuid4()) for _ in range(101)]},
    {"record_ids": [str(uuid4()) for _ in range(100)], "field_ids": [str(uuid4()) for _ in range(11)]},
    {"expected_revision": True}, {"context_id": "invalid"}, {"title": "x" * 1025}, {"title": "\ud800"}])
def test_selection_and_metadata_limits_reject_without_new_context(model, kwargs):
    store, _ = model
    with pytest.raises(ProjectError):
        capture(model, **kwargs)
    assert store.contexts.list()["contexts"] == [] and store.info()["revision"] == 1


def test_concurrent_capture_retries_keep_one_identity_and_do_not_edit(model):
    store, ids = model
    identity, barrier = str(uuid4()), threading.Barrier(2)
    def create(_):
        other = ProjectStore(store.directory)
        barrier.wait(timeout=5)
        return capture((other, ids), context_id=identity)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, range(2)))
    assert outcomes[0] == outcomes[1] and len(store.contexts.list()["contexts"]) == 1
    assert store.info()["revision"] == 1


def test_paginated_context_summaries_retain_descriptors_but_exclude_values(model):
    store, _ = model
    contexts = [capture(model, title=str(i)) for i in range(3)]
    page = store.contexts.list(limit=2)
    assert [item["id"] for item in page["contexts"]] == [item["id"] for item in contexts[:2]]
    assert page["next_offset"] == 2
    assert all("value" not in item["content"] for item in page["contexts"])
    assert page["contexts"][0]["content"]["sha256"] == contexts[0]["content"]["sha256"]
    assert store.contexts.list(offset=2)["contexts"][0]["id"] == contexts[2]["id"]
    for kwargs in ({"offset": -1}, {"offset": 2**63}, {"limit": 101}, {"limit": False}):
        with pytest.raises(ProjectError):
            store.contexts.list(**kwargs)


def test_context_corruption_missing_ids_and_replacement_are_reported(model):
    store, _ = model
    context = capture(model)
    with pytest.raises(ProjectError, match="not found"):
        store.contexts.get(str(uuid4()))
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_contexts SET payload='{}'")
    with pytest.raises(ProjectError, match="stored project context"):
        store.contexts.get(context["id"])
    with pytest.raises(ProjectError, match="stored project context"):
        store.contexts.list()
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project SET id=?", (str(uuid4()),))
    with pytest.raises(ProjectError, match="replaced"):
        store.contexts.get(context["id"])


def test_format_six_explicit_upgrade_preserves_drafts_and_verified_backup(model, tmp_path):
    store, ids = model
    draft = store.drafts.save([cell(ids, "temperature", 350)], expected_revision=1, title="Keep draft", draft_id=str(uuid4()))
    before, history = store.snapshot(), store.history()
    with sqlite3.connect(store.path) as db:
        for name in ("workflow_run_events", "workflow_run_plans", "analysis_run_events", "analysis_run_plans", "project_requests", "project_proposals", "project_messages", "project_contexts"):
            db.execute(f"DROP TABLE {name}")
        db.execute("PRAGMA user_version=6")
    with pytest.raises(UnsupportedProjectFormat, match="format 7"):
        capture(model)
    result = store.upgrade(expected_revision=1)
    assert result["format_version"] == FORMAT_VERSION == 10 and result["revision"] == 2
    assert store.drafts.get(draft["id"]) == draft and store.snapshot()["tables"] == before["tables"]
    assert store.snapshot()["edit_history"] == before["edit_history"] and store.history()[:-1] == history
    restored = tmp_path / "old"
    restored.mkdir()
    shutil.copyfile(result["backup"]["path"], restored / "project.sqlite3")
    old = ProjectStore(restored)
    assert old.info()["format_version"] == 6 and old.drafts.get(draft["id"]) == draft
    with pytest.raises(UnsupportedProjectFormat):
        old.contexts.list()
    assert capture(model)["source_revision"] == 2


def test_context_capture_insert_failure_leaves_no_edit_or_partial_metadata(model):
    store, _ = model
    before, history = store.snapshot(), store.history()
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER block_capture BEFORE INSERT ON project_contexts
                      BEGIN SELECT RAISE(ABORT, 'capture unavailable'); END""")
    with pytest.raises(ProjectError, match="capture unavailable"):
        capture(model)
    assert store.snapshot() == before and store.history() == history and store.contexts.list()["contexts"] == []


def test_failed_format_seven_upgrade_rolls_back_all_metadata_tables(model, monkeypatch):
    import suan.project.store as storage
    store, _ = model
    with sqlite3.connect(store.path) as db:
        for name in ("workflow_run_events", "workflow_run_plans", "analysis_run_events", "analysis_run_plans", "project_requests", "project_proposals", "project_messages", "project_contexts"):
            db.execute(f"DROP TABLE {name}")
        db.execute("PRAGMA user_version=6")
    before, history = store.snapshot(), store.history()
    monkeypatch.setattr(storage, "_DDL_V7", (*storage._DDL_V7, "invalid SQL"))
    with pytest.raises(ProjectError):
        store.upgrade(expected_revision=1)
    assert store.snapshot() == before and store.history() == history
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name IN ('project_contexts','project_messages','project_proposals')").fetchall() == []
    backups = list((store.directory / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 6
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
