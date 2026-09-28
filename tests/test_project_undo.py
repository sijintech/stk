"""Persistent atomic undo/redo across literals, formulas, object deletion and migration."""
from concurrent.futures import ThreadPoolExecutor
import json
import random
import sqlite3
import threading
from uuid import uuid4

from click.testing import CliRunner

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.store import FORMAT_VERSION
from suan.project.cli import project
from test_project_values import model, derived, result, command, reference


def tables(store):
    # Evaluation timestamps intentionally advance after undo; definitions and values must match.
    value = store.snapshot()["tables"]
    for table in value:
        for row in table["records"]:
            for cache in row.get("evaluations", {}).values():
                cache.pop("evaluated_revision", None)
    return value


def test_whole_batch_undo_redo_survives_reopen_and_keeps_monotonic_history(model):
    store, ids = derived(model)
    before = tables(store)
    store.apply([command(ids, "temperature", "set_cell", value=500),
                 {"op": "rename_table", "id": ids["inputs"], "name": "热输入"}], expected_revision=2)
    after = tables(store)
    assert result(store)["values"][ids["derived"]] == 510
    store = ProjectStore(store.directory)
    assert store.undo(expected_revision=3) == {"revision": 4, "target_revision": 3}
    assert tables(store) == before
    assert store.snapshot()["edit_history"] == {"undo_revision": 2, "redo_revision": 3}
    store = ProjectStore(store.directory)
    assert store.redo(expected_revision=4) == {"revision": 5, "target_revision": 3}
    assert tables(store) == after
    assert store.snapshot()["edit_history"] == {"undo_revision": 3, "redo_revision": None}
    assert store.history()[-2]["commands"] == [{"op": "undo", "target_revision": 3}]
    assert store.history()[-1]["commands"] == [{"op": "redo", "target_revision": 3}]


@pytest.mark.parametrize("kind,identity", [("table", "inputs"), ("field", "temperature"), ("record", "input_row")])
def test_delete_restore_original_identity_order_and_reference_dependencies(model, kind, identity):
    store, ids = derived(model)
    before = tables(store)
    store.apply([{"op": "delete_" + kind, "id": ids[identity]}], expected_revision=2)
    deleted = tables(store)
    assert store.snapshot()["tables"][-1]["records"][0]["evaluations"][ids["copy"]]["error"]["code"] == "missing_reference"
    store.undo(expected_revision=3)
    assert tables(store) == before
    assert result(store)["values"][ids["derived"]] == 310
    store.redo(expected_revision=4)
    assert tables(store) == deleted


def test_all_edits_undo_to_empty_then_redo_in_original_order(model):
    store, ids = derived(model)
    before = tables(store)
    store.undo(expected_revision=2)
    assert "definitions" not in result(store)
    store.undo(expected_revision=3)
    assert tables(store) == []
    assert store.snapshot()["edit_history"] == {"undo_revision": None, "redo_revision": 1}
    with pytest.raises(ProjectError, match="Nothing to undo"):
        store.undo(expected_revision=4)
    assert store.info()["revision"] == 4
    store.redo(expected_revision=4)
    store.redo(expected_revision=5)
    assert tables(store) == before
    with pytest.raises(ProjectError, match="Nothing to redo"):
        store.redo(expected_revision=6)


def test_failed_or_conflicting_edit_keeps_redo_but_new_edit_discards_it(model):
    store, ids = derived(model)
    store.undo(expected_revision=2)
    before = store.snapshot()
    with pytest.raises(ProjectError):
        store.apply([command(ids, "temperature", "set_cell", value=500), {"op": "invalid"}], expected_revision=3)
    with pytest.raises(RevisionConflict):
        store.redo(expected_revision=2)
    assert store.snapshot() == before
    store.apply([command(ids, "temperature", "set_cell", value=400)], expected_revision=3)
    assert store.snapshot()["edit_history"] == {"undo_revision": 4, "redo_revision": None}
    with pytest.raises(ProjectError, match="Nothing to redo"):
        store.redo(expected_revision=4)
    store.undo(expected_revision=4)
    assert result(store)["values"] == {}


@pytest.mark.parametrize("op,params", [("unset_cell", {}), ("set_cell", {"value": None}),
    ("set_cell", {"value": 17}), ("set_expression", {"expression": "1 / 0", "bindings": {}})])
def test_replacing_a_definition_restores_original_formula_or_reference(model, op, params):
    store, ids = derived(model)
    before = tables(store)
    store.apply([command(ids, "copy", op, **params)], expected_revision=2)
    after = tables(store)
    store.undo(expected_revision=3)
    assert tables(store) == before
    store.redo(expected_revision=4)
    assert tables(store) == after


def test_multiple_changes_to_same_cell_capture_one_before_and_final_after(model):
    store, ids = derived(model)
    before = tables(store)
    store.apply([command(ids, "copy", "set_cell", value=None), command(ids, "copy", "unset_cell"),
                 command(ids, "copy", "set_expression", expression='quantity(7, "K")', bindings={})], expected_revision=2)
    assert result(store)["values"][ids["derived"]] == 17
    store.undo(expected_revision=3)
    assert tables(store) == before
    store.redo(expected_revision=4)
    assert result(store)["values"][ids["derived"]] == 17


def test_delete_recreate_with_same_ids_and_exchanged_rowids_is_reversible(model):
    store, ids = model
    before = tables(store)
    store.apply([{"op": "delete_table", "id": ids["inputs"]},
                 {"op": "delete_table", "id": ids["results"]},
                 {"op": "create_table", "id": ids["results"], "name": "Second first"},
                 {"op": "create_table", "id": ids["inputs"], "name": "First second"}], expected_revision=1)
    after = tables(store)
    store.undo(expected_revision=2)
    assert tables(store) == before
    store.redo(expected_revision=3)
    assert tables(store) == after


def test_generated_ids_and_net_zero_batch_do_not_make_unrestorable_entries(tmp_path):
    store = ProjectStore.create(tmp_path, "Generated IDs")
    added = store.apply([{"op": "create_table", "name": "A"}], expected_revision=0)
    identity = added["commands"][0]["id"]
    store.apply([{"op": "rename_table", "id": identity, "name": "B"},
                 {"op": "rename_table", "id": identity, "name": "A"}], expected_revision=1)
    assert store.snapshot()["edit_history"]["undo_revision"] == 1
    store.undo(expected_revision=2)
    assert tables(store) == []
    store.redo(expected_revision=3)
    assert tables(store)[0]["id"] == identity


def test_concurrent_undo_and_edit_at_one_revision_have_one_winner(model):
    store, ids = derived(model)
    barrier = threading.Barrier(2)

    def execute(undo):
        other = ProjectStore(store.directory)
        barrier.wait(timeout=5)
        try:
            return other.undo(expected_revision=2) if undo else other.apply(
                [command(ids, "temperature", "set_cell", value=450)], expected_revision=2)
        except RevisionConflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(execute, (True, False)))
    assert sum(value is not None for value in outcomes) == 1
    assert store.info()["revision"] == 3


@pytest.mark.parametrize("damage", ["json", "mismatch"])
def test_damaged_journal_fails_without_mutation(model, damage):
    store, ids = derived(model)
    with sqlite3.connect(store.path) as db:
        if damage == "json":
            db.execute("UPDATE edit_journal SET delta='{}' WHERE revision=2")
        else:
            db.execute("UPDATE definitions SET definition=? WHERE field_id=?",
                       (json.dumps({"kind": "reference", "source": reference(ids, "temperature")}), ids["derived"]))
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError, match="Cannot restore edit"):
        store.undo(expected_revision=2)
    assert store.snapshot() == before and store.history() == history


def test_format_two_upgrade_preserves_formulas_and_starts_a_new_undo_boundary(model):
    store, ids = derived(model)
    before = tables(store)
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE project_snapshots")
        db.execute("DROP TABLE edit_journal")
        db.execute("PRAGMA user_version=2")
    store = ProjectStore(store.directory)
    assert "edit_history" not in store.snapshot()
    with pytest.raises(ProjectError, match="Upgrade"):
        store.undo(expected_revision=2)
    store.apply([command(ids, "temperature", "set_cell", value=300)], expected_revision=2)
    upgraded = store.upgrade(expected_revision=3)
    assert upgraded["backup"]["format_version"] == 2 and upgraded["format_version"] == FORMAT_VERSION
    assert tables(store) == before
    assert store.snapshot()["edit_history"] == {"undo_revision": None, "redo_revision": None}
    store.apply([command(ids, "temperature", "set_cell", value=400)], expected_revision=4)
    store.undo(expected_revision=5)
    assert tables(store) == before
    with pytest.raises(ProjectError, match="Nothing to undo"):
        store.undo(expected_revision=6)


def test_cli_undo_redo_require_revision_and_preserve_state(model):
    store, _ = model
    before = tables(store)
    runner = CliRunner()
    response = runner.invoke(project, ["undo", str(store.directory), "--expected-revision", "1"])
    assert response.exit_code == 0, response.output
    assert json.loads(response.output) == {"revision": 2, "target_revision": 1}
    assert tables(store) == []
    response = runner.invoke(project, ["redo", str(store.directory), "--expected-revision", "1"])
    assert response.exit_code != 0 and "Expected revision" in response.output
    response = runner.invoke(project, ["redo", str(store.directory), "--expected-revision", "2"])
    assert response.exit_code == 0, response.output
    assert tables(store) == before


def test_mixed_edit_sequence_round_trips_every_persistent_undo_and_redo_state(model):
    store, _ = derived(model)
    rng = random.Random(1729)
    checkpoints = []
    for iteration in range(80):
        before = tables(store)
        table = rng.choice(before) if before else None
        choice = rng.randrange(8) if table else 0
        if choice == 0:
            edit = {"op": "create_table", "name": f"Table {iteration}"}
        elif choice == 1:
            edit = {"op": "add_field", "table_id": table["id"], "name": f"Field {iteration}", "type": "number", "unit": "1"}
        elif choice == 2:
            edit = {"op": "add_record", "table_id": table["id"]}
        elif choice == 3:
            edit = {"op": "rename_table", "id": table["id"], "name": f"Renamed {iteration}"}
        elif choice in (4, 5) and table["fields"] and table["records"]:
            field, row = rng.choice(table["fields"]), rng.choice(table["records"])
            edit = {"op": "set_cell", "table_id": table["id"], "record_id": row["id"], "field_id": field["id"], "value": iteration}
            if choice == 5:
                edit.pop("value")
                edit.update(op="set_reference", source={"record_id": row["id"], "field_id": rng.choice(table["fields"])["id"]})
        elif choice == 6 and table["fields"]:
            edit = {"op": "delete_field", "id": rng.choice(table["fields"])["id"]}
        elif choice == 7:
            edit = {"op": "delete_table", "id": table["id"]}
        else:
            continue
        revision = store.info()["revision"]
        store.apply([edit], expected_revision=revision)
        if store.snapshot()["edit_history"]["undo_revision"] == revision + 1:
            checkpoints.append((before, tables(store)))
    assert len(checkpoints) >= 50
    for before, _ in reversed(checkpoints):
        store = ProjectStore(store.directory)
        store.undo(expected_revision=store.info()["revision"])
        assert tables(store) == before
    for _, after in checkpoints:
        store = ProjectStore(store.directory)
        store.redo(expected_revision=store.info()["revision"])
        assert tables(store) == after
