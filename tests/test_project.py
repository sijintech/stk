"""Project persistence, stable cell identity, transaction isolation and CLI round trips."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from click.testing import CliRunner
import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.cli import project
from suan.project.store import DATABASE_NAME, FORMAT_VERSION


@pytest.fixture
def populated(tmp_path):
    store = ProjectStore.create(tmp_path / "项目 #1", "温度扫描")
    table, field, record = (str(uuid4()) for _ in range(3))
    store.apply([
        {"op": "create_table", "id": table, "name": "Cases"},
        {"op": "add_field", "id": field, "table_id": table, "name": "Temperature", "type": "number", "unit": "K"},
        {"op": "add_record", "id": record, "table_id": table},
        {"op": "set_cell", "table_id": table, "record_id": record, "field_id": field, "value": 300},
    ], expected_revision=0)
    return store, table, field, record


def test_round_trip_rename_and_history_preserve_cell_identity(populated):
    store, table, field, record = populated
    before = store.snapshot()
    assert before["project"]["revision"] == 1
    assert before["tables"][0]["fields"][0]["unit"] == "K"
    assert ProjectStore(store.directory).snapshot() == before
    store.apply([
        {"op": "rename_table", "id": table, "name": "模拟"},
        {"op": "rename_field", "id": field, "name": "温度"},
    ], expected_revision=1)
    reopened = ProjectStore(store.directory)
    after = reopened.snapshot()
    assert after["project"]["id"] == before["project"]["id"]
    assert after["tables"][0]["name"] == "模拟"
    assert after["tables"][0]["fields"][0]["id"] == field
    assert after["tables"][0]["records"] == [{"id": record, "values": {field: 300}}]
    assert [change["revision"] for change in reopened.history()] == [1, 2]
    assert reopened.history()[0]["commands"][3]["value"] == 300


def test_invalid_batch_rolls_back_values_names_and_revision(populated):
    store, table, field, record = populated
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError, match="field type"):
        store.apply([
            {"op": "rename_table", "id": table, "name": "Must roll back"},
            {"op": "set_cell", "table_id": table, "record_id": record, "field_id": field, "value": "hot"},
        ], expected_revision=1)
    assert store.snapshot() == before
    assert store.history() == history


def test_concurrent_edits_at_one_revision_have_exactly_one_winner(populated):
    store, table, _, _ = populated
    barrier = threading.Barrier(2)

    def edit(name):
        other = ProjectStore(store.directory)
        barrier.wait(timeout=5)
        try:
            other.apply([{"op": "rename_table", "id": table, "name": name}], expected_revision=1)
            return name
        except RevisionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["First", "Second"]))
    winners = [name for name in results if name is not None]
    assert len(winners) == 1
    assert store.snapshot()["tables"][0]["name"] == winners[0]
    assert store.snapshot()["project"]["revision"] == 2
    assert len(store.history()) == 2


def test_cells_cannot_cross_tables_and_duplicate_ids_do_not_overwrite(populated):
    store, table, field, record = populated
    other = str(uuid4())
    store.apply([{"op": "create_table", "id": other, "name": "Other"}], expected_revision=1)
    before = store.snapshot()
    for command in (
        {"op": "set_cell", "table_id": other, "record_id": record, "field_id": field, "value": 400},
        {"op": "set_cell", "table_id": table, "record_id": str(uuid4()), "field_id": field, "value": 400},
        {"op": "create_table", "id": table, "name": "Duplicate"},
        {"op": "add_record", "table_id": str(uuid4())},
    ):
        with pytest.raises(ProjectError):
            store.apply([command], expected_revision=2)
        assert store.snapshot() == before


@pytest.mark.parametrize("kind,value", [
    ("text", "中文"), ("integer", 42), ("number", 1.5), ("boolean", True),
    ("json", {"image": "assets/a.png", "tags": ["result"], "other": None}),
])
def test_typed_values_and_explicit_null_round_trip(populated, kind, value):
    store, table, _, record = populated
    result = store.apply([{"op": "add_field", "table_id": table, "name": kind, "type": kind}], expected_revision=1)
    field = result["commands"][0]["id"]
    assert field not in store.snapshot()["tables"][0]["records"][0]["values"]
    command = {"op": "set_cell", "table_id": table, "record_id": record, "field_id": field, "value": value}
    store.apply([command], expected_revision=2)
    assert ProjectStore(store.directory).snapshot()["tables"][0]["records"][0]["values"][field] == value
    command["value"] = None
    store.apply([command], expected_revision=3)
    assert field in store.snapshot()["tables"][0]["records"][0]["values"]
    assert store.snapshot()["tables"][0]["records"][0]["values"][field] is None


@pytest.mark.parametrize("kind,value", [
    ("integer", True), ("integer", 1.5), ("integer", 2**63), ("boolean", 1),
    ("text", 7), ("number", True), ("number", float("inf")), ("number", float("nan")),
    ("json", {"bad": float("nan")}),
])
def test_invalid_values_do_not_create_fields_or_revisions(populated, kind, value):
    store, table, _, record = populated
    field = str(uuid4())
    before = store.snapshot()
    with pytest.raises(ProjectError):
        store.apply([
            {"op": "add_field", "id": field, "table_id": table, "name": "Invalid", "type": kind},
            {"op": "set_cell", "table_id": table, "record_id": record, "field_id": field, "value": value},
        ], expected_revision=1)
    assert store.snapshot() == before


@pytest.mark.parametrize("commands", [
    [], [None], [{"op": "execute"}], [{"op": "create_table"}],
    [{"op": "create_table", "name": "A", "extra": "typo"}],
    [{"op": "create_table", "name": "A", "id": "row-1"}],
    [{"op": "create_table", "name": " "}],
])
def test_invalid_commands_have_no_side_effects(populated, commands):
    store, *_ = populated
    before = store.snapshot()
    with pytest.raises(ProjectError):
        store.apply(commands, expected_revision=1)
    assert store.snapshot() == before


def test_open_never_initializes_missing_unknown_or_newer_databases(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ProjectError):
        ProjectStore(missing)
    assert not missing.exists()
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    path = unrelated / DATABASE_NAME
    path.write_bytes(b"not a database")
    before = path.read_bytes()
    with pytest.raises(ProjectError):
        ProjectStore(unrelated)
    assert path.read_bytes() == before
    with pytest.raises(FileExistsError):
        ProjectStore.create(unrelated, "Must not replace")
    assert path.read_bytes() == before
    store = ProjectStore.create(tmp_path / "newer", "Newer")
    with sqlite3.connect(store.path) as db:
        db.execute(f"PRAGMA user_version={FORMAT_VERSION + 1}")
    before = store.path.read_bytes()
    with pytest.raises(ProjectError, match="Unsupported project format"):
        ProjectStore(store.directory)
    with pytest.raises(ProjectError, match="Unsupported project format"):
        store.apply([{"op": "create_table", "name": "No"}], expected_revision=0)
    assert store.path.read_bytes() == before


def test_create_does_not_overwrite_existing_project(populated):
    store, *_ = populated
    before = store.snapshot()
    with pytest.raises(FileExistsError):
        ProjectStore.create(store.directory, "Replacement")
    assert store.snapshot() == before


def test_open_store_does_not_edit_a_replaced_project(tmp_path):
    store = ProjectStore.create(tmp_path / "original", "Original")
    replacement = ProjectStore.create(tmp_path / "replacement", "Replacement")
    replacement.path.replace(store.path)
    for operation in (store.info, store.snapshot, store.history,
                      lambda: store.apply([{"op": "create_table", "name": "Wrong project"}], expected_revision=0)):
        with pytest.raises(ProjectError, match="was replaced"):
            operation()
    reopened = ProjectStore(store.directory)
    assert reopened.info()["name"] == "Replacement"
    assert reopened.info()["revision"] == 0


def test_cli_create_apply_reopen_conflict_and_invalid_json(tmp_path):
    runner = CliRunner()
    directory = str(tmp_path / "CLI 项目")
    created = runner.invoke(project, ["create", directory, "--name", "Test"])
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["project"]["revision"] == 0
    argv = ["apply", directory, "--expected-revision", "0", "--commands", "-"]
    applied = runner.invoke(project, argv, input='[{"op":"create_table","name":"Cases"}]')
    assert applied.exit_code == 0, applied.output
    table = json.loads(applied.output)["commands"][0]["id"]
    shown = runner.invoke(project, ["show", directory])
    assert json.loads(shown.output)["tables"][0]["id"] == table
    conflict = runner.invoke(project, argv, input='[{"op":"create_table","name":"Cases"}]')
    assert conflict.exit_code != 0 and "current revision is 1" in conflict.output
    invalid = runner.invoke(project, argv, input='[broken')
    assert invalid.exit_code != 0 and "Error:" in invalid.output
    assert len(json.loads(runner.invoke(project, ["history", directory]).output)) == 1
    assert not (Path(directory) / "runtime.sqlite3").exists()
