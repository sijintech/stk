"""Format 2 references/formulas, exact units, selective persistence and explicit migration."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sqlite3
import threading
from uuid import uuid4

import pytest
from click.testing import CliRunner

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.cli import project
from suan.project import store as storage


@pytest.fixture
def model(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Derived values")
    ids = {name: str(uuid4()) for name in ("inputs", "results", "input_row", "result_row", "temperature", "copy", "derived", "independent")}
    store.apply([
        {"op": "create_table", "id": ids["inputs"], "name": "Inputs"},
        {"op": "create_table", "id": ids["results"], "name": "Results"},
        {"op": "add_record", "id": ids["input_row"], "table_id": ids["inputs"]},
        {"op": "add_record", "id": ids["result_row"], "table_id": ids["results"]},
        *[{"op": "add_field", "id": ids[name], "table_id": ids[table], "name": name,
           "type": "number", "unit": unit} for name, table, unit in
          (("temperature", "inputs", "K"), ("copy", "results", "K"), ("derived", "results", "K"), ("independent", "results", "1"))],
        {"op": "set_cell", "table_id": ids["inputs"], "record_id": ids["input_row"], "field_id": ids["temperature"], "value": 300},
    ], expected_revision=0)
    return store, ids


def command(ids, field, op, **params):
    source = field == "temperature"
    return dict(op=op, table_id=ids["inputs" if source else "results"],
                record_id=ids["input_row" if source else "result_row"], field_id=ids[field], **params)


def reference(ids, field):
    return {"record_id": ids["input_row" if field == "temperature" else "result_row"], "field_id": ids[field]}


def result(store):
    return store.snapshot()["tables"][1]["records"][0]


def derived(model):
    store, ids = model
    store.apply([
        command(ids, "copy", "set_reference", source=reference(ids, "temperature")),
        command(ids, "derived", "set_expression", expression='base + quantity(10, "K")', bindings={"base": reference(ids, "copy")}),
        command(ids, "independent", "set_expression", expression="6 * 7", bindings={}),
    ], expected_revision=1)
    return store, ids


def test_cross_table_reference_formula_reopen_and_selective_cache(model):
    store, ids = derived(model)
    row = result(store)
    assert row["values"] == {ids["copy"]: 300, ids["derived"]: 310, ids["independent"]: 42}
    assert ProjectStore(store.directory).snapshot() == store.snapshot()
    store.apply([{"op": "rename_table", "id": ids["inputs"], "name": "重命名"},
                 {"op": "rename_field", "id": ids["temperature"], "name": "温度"}], expected_revision=2)
    assert result(store) == row  # labels and project revision are outside the cache dependency key
    store.apply([command(ids, "temperature", "set_cell", value=400)], expected_revision=3)
    changed = result(store)
    assert changed["values"][ids["derived"]] == 410
    assert changed["evaluations"][ids["copy"]]["evaluated_revision"] == 4
    assert changed["evaluations"][ids["derived"]]["evaluated_revision"] == 4
    assert changed["evaluations"][ids["independent"]] == row["evaluations"][ids["independent"]]
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM cells").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM definitions").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM evaluations").fetchone()[0] == 3


@pytest.mark.parametrize("operation,identity", [("delete_field", "temperature"), ("delete_record", "input_row"), ("delete_table", "inputs")])
def test_deleted_sources_keep_definitions_and_diagnose_missing_references(model, operation, identity):
    store, ids = derived(model)
    store.apply([{"op": operation, "id": ids[identity]}], expected_revision=2)
    row = store.snapshot()["tables"][-1]["records"][0]
    assert ids["copy"] not in row["values"] and ids["derived"] not in row["values"]
    assert row["evaluations"][ids["copy"]]["error"]["code"] == "missing_reference"
    assert row["evaluations"][ids["derived"]]["error"]["code"] == "dependency_error"
    assert row["definitions"][ids["copy"]]["source"] == reference(ids, "temperature")
    assert row["values"][ids["independent"]] == 42


def test_unset_null_literal_replacement_and_cycle_repair(model):
    store, ids = derived(model)
    store.apply([command(ids, "temperature", "set_cell", value=None)], expected_revision=2)
    assert result(store)["values"][ids["copy"]] is None
    assert result(store)["evaluations"][ids["derived"]]["error"]["code"] == "type"
    store.apply([command(ids, "temperature", "unset_cell")], expected_revision=3)
    assert result(store)["evaluations"][ids["copy"]]["error"]["code"] == "missing_value"
    store.apply([command(ids, "copy", "set_reference", source=reference(ids, "derived"))], expected_revision=4)
    row = result(store)
    assert row["evaluations"][ids["copy"]]["error"]["code"] == "cycle"
    assert row["evaluations"][ids["derived"]]["error"]["code"] == "cycle"
    store.apply([command(ids, "copy", "set_cell", value=7)], expected_revision=5)
    row = result(store)
    assert ids["copy"] not in row["definitions"]
    assert row["values"][ids["derived"]] == 17


def test_expression_errors_persist_but_bad_batches_roll_back_cache_and_history(model):
    store, ids = derived(model)
    for expression, code in (("1 / 0", "division_by_zero"), ("1 +", "syntax"), ("open('file')", "unsupported"), ("1 + 2", "unit")):
        revision = store.info()["revision"]
        store.apply([command(ids, "derived", "set_expression", expression=expression, bindings={})], expected_revision=revision)
        row = result(store)
        assert row["definitions"][ids["derived"]]["expression"] == expression
        assert row["evaluations"][ids["derived"]]["error"]["code"] == code
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError):
        store.apply([command(ids, "temperature", "set_cell", value=800),
                     command(ids, "copy", "set_reference", source={"record_id": "invalid", "field_id": ids["temperature"]})],
                    expected_revision=store.info()["revision"])
    assert store.snapshot() == before and store.history() == history


def test_missing_cache_is_rebuilt_from_definitions_without_changing_project_revision(model):
    store, ids = derived(model)
    with sqlite3.connect(store.path) as db:
        db.execute("DELETE FROM evaluations")
    assert result(store)["values"][ids["derived"]] == 310
    assert store.info()["revision"] == 2
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM evaluations").fetchone()[0] == 0  # read-only snapshot
    store.apply([{"op": "rename_table", "id": ids["inputs"], "name": "Inputs renamed"}], expected_revision=2)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM evaluations").fetchone()[0] == 3


@pytest.mark.parametrize("cache", ['{broken', 'null', '{"engine_version":1}',
                                  '{"engine_version":999,"state":"ok","value":999,"unit":"K","evaluated_revision":2}'])
def test_invalid_or_obsolete_derived_cache_is_discarded(model, cache):
    store, ids = derived(model)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE evaluations SET result=? WHERE field_id=?", (cache, ids["copy"]))
    assert result(store)["values"][ids["derived"]] == 310
    assert store.info()["revision"] == 2


def legacy(store):
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS analysis_run_events")
        db.execute("DROP TABLE IF EXISTS analysis_run_plans")
        db.execute("DROP TABLE IF EXISTS project_requests")
        db.execute("DROP TABLE IF EXISTS project_proposals")
        db.execute("DROP TABLE IF EXISTS project_messages")
        db.execute("DROP TABLE IF EXISTS project_contexts")
        db.execute("DROP TABLE IF EXISTS project_drafts")
        db.execute("DROP TABLE run_observations")
        db.execute("DROP TABLE run_plans")
        db.execute("DROP TABLE project_snapshots")
        db.execute("DROP TABLE edit_journal")
        db.execute("DROP TABLE evaluations")
        db.execute("DROP TABLE definitions")
        db.execute("PRAGMA user_version=1")
    return ProjectStore(store.directory)


def test_explicit_upgrade_backups_and_restore_preserve_old_project(model, tmp_path):
    store, ids = model
    store = legacy(store)
    before = store.snapshot()
    assert before["format_version"] == 1
    assert ProjectStore(store.directory).snapshot() == before
    assert not (store.directory / "backups").exists()
    with pytest.raises(ProjectError, match="Upgrade"):
        store.apply([command(ids, "copy", "set_reference", source=reference(ids, "temperature"))], expected_revision=1)
    assert store.snapshot() == before
    upgrade = store.upgrade(expected_revision=1)
    assert upgrade["upgraded"] and upgrade["revision"] == 2 and upgrade["format_version"] == storage.FORMAT_VERSION
    backup = Path(upgrade["backup"]["path"])
    assert backup.is_file() and upgrade["backup"]["revision"] == 1
    restored = tmp_path / "restored"
    restored.mkdir()
    shutil.copy2(backup, restored / storage.DATABASE_NAME)
    assert ProjectStore(restored).snapshot() == before
    assert store.history()[-1]["commands"] == [{"op": "upgrade_format", "from_version": 1, "to_version": storage.FORMAT_VERSION}]
    assert not store.upgrade(expected_revision=2)["upgraded"]
    assert len(list((store.directory / "backups").glob("*.sqlite3"))) == 1
    store.apply([command(ids, "copy", "set_reference", source=reference(ids, "temperature"))], expected_revision=2)
    assert result(store)["values"][ids["copy"]] == 300
    assert store.backup()["revision"] == 3
    assert store.info()["revision"] == 3


def test_failed_upgrade_rolls_back_schema_and_keeps_a_valid_backup(model, monkeypatch, tmp_path):
    store, _ = model
    store = legacy(store)
    before = store.snapshot()
    monkeypatch.setattr(storage, "_DDL_V2", (*storage._DDL_V2, "INVALID SQL"))
    with pytest.raises(ProjectError):
        store.upgrade(expected_revision=1)
    assert store.snapshot() == before
    with sqlite3.connect(store.path) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='definitions'").fetchall()
    backups = list((store.directory / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    restored = tmp_path / "failed-upgrade-backup"
    restored.mkdir()
    shutil.copy2(backups[0], restored / storage.DATABASE_NAME)
    assert ProjectStore(restored).snapshot() == before


def test_concurrent_upgrade_has_one_winner_and_no_backup_for_conflict(model):
    store, _ = model
    store = legacy(store)
    barrier = threading.Barrier(2)

    def upgrade(_):
        instance = ProjectStore(store.directory)
        barrier.wait(timeout=5)
        try:
            return instance.upgrade(expected_revision=1)
        except RevisionConflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(upgrade, range(2)))
    assert sum(outcome is not None for outcome in outcomes) == 1
    assert len(list((store.directory / "backups").glob("*.sqlite3"))) == 1
    assert store.info()["revision"] == 2


def test_cli_backup_and_explicit_upgrade(model):
    store, _ = model
    store = legacy(store)
    runner = CliRunner()
    result = runner.invoke(project, ["upgrade", str(store.directory), "--expected-revision", "1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["upgraded"]
    result = runner.invoke(project, ["backup", str(store.directory)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["revision"] == 2
