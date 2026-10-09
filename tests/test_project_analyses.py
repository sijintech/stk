"""Analysis definitions: offline literal reads, safe drafts, CAS, undo and bounded writes."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import analyses
from suan.project.analyses import AnalysisNotFound, DOCUMENT_FORMAT, FIELD_IDS, TABLE_ID
from suan.project.store import UnsupportedProjectFormat


def document():
    return {"format": DOCUMENT_FORMAT, "graph": {
        "schema": "stk.graph/1", "id": "saved-example", "name": "Saved analysis",
        "parameters": [{"name": "level", "type": "number", "default": 0.1}],
        "nodes": [{"id": "source", "type": "missing.source.node@1", "params": {"level": {"$param": "level"}}}],
        "outputs": {"view": "source.payload"}}, "parameters": {"level": 0.25}, "outputs": ["view"]}


@pytest.fixture
def store(tmp_path):
    return ProjectStore.create(tmp_path / "project", "Analyses")


def create(store, value=None, name="分析", identity=None, revision=None):
    return store.analyses.create(name, document() if value is None else value,
        analysis_id=identity or str(uuid4()), expected_revision=store.info()["revision"] if revision is None else revision)


def literal(store, identity, key, value):
    return store.apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": identity,
        "field_id": FIELD_IDS[key], "value": value}], expected_revision=store.info()["revision"])


def raw_literal(store, identity, key, text):
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE cells SET value=? WHERE record_id=? AND field_id=?", (text, identity, FIELD_IDS[key]))


def saved(store, identity):
    return store.analyses.get(identity)["analysis"]


def test_absent_index_is_a_pure_empty_read_and_missing_id_is_distinct(store):
    before = store.snapshot()
    assert store.analyses.list() == {"revision": 0, "table_id": TABLE_ID, "compatible": True, "error": "",
                                    "offset": 0, "total": 0, "analyses": []}
    with pytest.raises(AnalysisNotFound):
        store.analyses.get(str(uuid4()))
    assert store.snapshot() == before and store.history() == []


def test_create_uses_fixed_fields_and_one_revision_and_undo_batch(store):
    identity = str(uuid4())
    answer = create(store, identity=identity)
    assert set(answer) == {"revision", "commands", "table_id", "record_id"}
    assert answer["revision"] == 1 and answer["record_id"] == identity and answer["table_id"] == TABLE_ID
    assert {c["op"] for c in answer["commands"]} == {"create_table", "add_field", "add_record", "set_cell"}
    snapshot = store.snapshot()
    assert snapshot["format_version"] == 12
    assert "analysis_index" not in snapshot
    table = snapshot["tables"][0]
    assert table["id"] == TABLE_ID and {f["id"] for f in table["fields"]} == set(FIELD_IDS.values())
    assert all(field["unit"] is None for field in table["fields"])
    assert saved(store, identity) == {"id": identity, "name": "分析", "format": DOCUMENT_FORMAT,
        "state": "readable", "error": "", "document": document()}
    assert store.analyses.list()["analyses"] == [{k: v for k, v in saved(store, identity).items() if k != "document"}]
    store.undo(expected_revision=1)
    assert store.snapshot()["tables"] == [] and store.analyses.list()["analyses"] == []
    store.redo(expected_revision=2)
    assert saved(store, identity)["document"] == document()
    assert ProjectStore(store.directory).analyses.get(identity) == store.analyses.get(identity)


def test_update_replaces_definition_keeps_identity_and_supports_reopen_undo_redo(store):
    identity = create(store)["record_id"]
    value = document()
    value["parameters"] = {"level": 0.9, "unknown_override": True}
    value["outputs"] = []
    value["graph"]["ui"] = {"positions": {"source": [100, 200]}}
    result = store.analyses.update(identity, "Changed", value, expected_revision=1)
    assert result["revision"] == 2 and result["record_id"] == identity
    assert {c["op"] for c in result["commands"]} == {"set_cell"}
    assert saved(ProjectStore(store.directory), identity)["document"] == value
    store.undo(expected_revision=2)
    assert saved(store, identity)["document"] == document()
    store.redo(expected_revision=3)
    assert saved(store, identity)["name"] == "Changed"
    assert saved(store, identity)["document"] == value
    store.apply([{"op": "delete_record", "id": identity}], expected_revision=4)
    assert store.analyses.list()["total"] == 0
    store.undo(expected_revision=5)
    assert saved(store, identity)["document"] == value


def test_drafts_allow_unknown_types_duplicate_ids_cycles_and_dangling_links(store):
    value = document()
    value["graph"]["nodes"] = [
        {"id": "a", "type": "missing.type.node@1", "inputs": {"in": {"from": "b.out"}}},
        {"id": "b", "type": "missing.type.node@1", "inputs": {"in": {"from": "a.out"}}},
        {"id": "b", "type": "missing.type.node@2", "inputs": {"in": [{"from": "missing.out", "as": "missing"}]}}]
    value["graph"]["outputs"] = {"view": "missing.output"}
    value["graph"]["nodes"][0]["params"] = {"bad_reference": {"$param": "undeclared"}, "$arbitrary": False}
    identity = create(store, value)["record_id"]
    assert saved(store, identity)["state"] == "readable"
    assert saved(store, identity)["document"] == value


@pytest.mark.parametrize("bad", [None, [], {}, {"format": DOCUMENT_FORMAT},
    {**document(), "source": {}}, {**document(), "parameters": []}, {**document(), "outputs": None},
    {**document(), "outputs": ["view", "view"]}, {**document(), "outputs": ["absent"]},
    {**document(), "outputs": [{}]}, {**document(), "graph": []},
    {**document(), "graph": {**document()["graph"], "nodes": []}},
    {**document(), "graph": {**document()["graph"], "nodes": [{"id": "source", "type": "broken"}]}},
    {**document(), "graph": {**document()["graph"], "nodes": [{"id": "source", "type": "missing.source.node@1",
        "inputs": {"in": {"from": "missing slash"}}}]}},
], ids=["null", "array", "empty", "missing", "extra", "parameters-array", "outputs-null", "duplicate-output",
         "missing-output", "object-output", "graph-array", "empty-nodes", "bad-type", "bad-link"])
def test_invalid_structure_rolls_back_everything(store, bad):
    with pytest.raises(ProjectError):
        store.analyses.create("Bad", bad, analysis_id=str(uuid4()), expected_revision=0)
    assert store.info()["revision"] == 0 and store.snapshot()["tables"] == [] and store.history() == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 2**64, -(2**63)-1,
    {1: "not a string key"}, (1, 2), {1, 2}, object(), "\ud800"],
    ids=["nan", "inf", "negative-inf", "large-int", "small-int", "key", "tuple", "set", "object", "surrogate"])
def test_nonplain_or_lossy_json_is_rejected_before_writes(store, value):
    doc = document()
    doc["parameters"]["value"] = value
    with pytest.raises(ProjectError):
        create(store, doc)
    assert store.info()["revision"] == 0 and store.history() == []


def test_json_depth_cycles_and_native_integer_boundaries(store):
    cyclic = document()
    cyclic["parameters"]["self"] = cyclic
    with pytest.raises(ProjectError, match="cycles"):
        create(store, cyclic)
    nested = []
    for _ in range(24000):
        nested = [nested]
    value = document()
    value["parameters"]["nested"] = nested
    with pytest.raises(ProjectError, match="depth"):
        create(store, value)
    valid = document()
    valid["parameters"] = {"min": -(2**63), "max": 2**64-1, "int": 1, "float": 1.0, "bool": True}
    identity = create(store, valid)["record_id"]
    values = saved(store, identity)["document"]["parameters"]
    assert values == valid["parameters"]
    assert type(values["int"]) is int and type(values["float"]) is float and type(values["bool"]) is bool


@pytest.mark.parametrize("name", [None, 123, "", " \t", "a" * 257, "a\0b", "\udfff"],
                         ids=["null", "number", "empty", "blank", "long", "nul", "surrogate"])
def test_names_require_bounded_utf8_text(store, name):
    with pytest.raises(ProjectError):
        create(store, name=name)
    assert store.info()["revision"] == 0


def test_graph_node_parameter_and_collection_component_limits(store):
    for part in ("graph", "node", "parameters", "nodes", "declarations", "overrides", "outputs"):
        value = document()
        if part == "graph":
            value["graph"]["x-large"] = "x" * analyses.MAX_GRAPH_BYTES
        elif part == "node":
            value["graph"]["nodes"][0]["params"] = {"large": "x" * analyses.MAX_PARAMETERS_BYTES}
        elif part == "parameters":
            value["parameters"] = {"large": "x" * analyses.MAX_PARAMETERS_BYTES}
        elif part == "nodes":
            value["graph"]["nodes"] *= 201
        elif part == "declarations":
            value["graph"]["parameters"] *= 65
        elif part == "overrides":
            value["parameters"] = {str(i): i for i in range(65)}
        else:
            value["graph"]["outputs"] = {"v" + str(i): "source.payload" for i in range(257)}
            value["outputs"] = list(value["graph"]["outputs"])
        with pytest.raises(ProjectError):
            create(store, value)
        assert store.info()["revision"] == 0, part


def test_ids_cas_duplicate_and_missing_updates_leave_history_unchanged(store):
    identity = create(store)["record_id"]
    snapshot, history = store.snapshot(), store.history()
    with pytest.raises(RevisionConflict):
        create(store, identity=identity)
    with pytest.raises(RevisionConflict):
        store.analyses.update(identity, "Stale", document(), expected_revision=0)
    with pytest.raises(AnalysisNotFound):
        store.analyses.update(str(uuid4()), "Missing", document(), expected_revision=1)
    for identity_value in ("", identity.upper(), 123):
        with pytest.raises(ProjectError):
            create(store, identity=identity_value or "bad")
    for revision in (True, -1, 1.0, "1"):
        with pytest.raises(ProjectError):
            create(store, revision=revision)
    assert store.snapshot() == snapshot and store.history() == history


def test_two_independent_writers_arbitrate_in_sqlite(store):
    first, second = ProjectStore(store.directory), ProjectStore(store.directory)
    barrier = threading.Barrier(2)

    def write(target):
        barrier.wait(timeout=10)
        try:
            return create(target, revision=0)
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (first, second)))
    assert sum(result == "conflict" for result in results) == 1
    assert store.info()["revision"] == 1 and store.analyses.list()["total"] == 1 and len(store.history()) == 1


def test_caller_mutation_cannot_change_frozen_write_or_later_read(store, monkeypatch):
    value = document()
    expected = deepcopy(value)
    apply = store._apply

    def change_caller(*args):
        value["graph"]["nodes"].clear()
        value["parameters"]["level"] = 99
        return apply(*args)

    monkeypatch.setattr(store, "_apply", change_caller)
    identity = create(store, value)["record_id"]
    read = saved(store, identity)
    assert read["document"] == expected
    read["document"]["graph"]["nodes"].clear()
    assert saved(store, identity)["document"] == expected


def test_names_are_not_reserved_and_extra_fields_survive_updates(store):
    store.apply([{"op": "create_table", "name": "Analyses"}], expected_revision=0)
    identity = create(store)["record_id"]
    extra = str(uuid4())
    store.apply([{"op": "rename_table", "id": TABLE_ID, "name": "Renamed"},
        {"op": "rename_field", "id": FIELD_IDS["graph"], "name": "流程"},
        {"op": "add_field", "table_id": TABLE_ID, "id": extra, "name": "Notes", "type": "text"},
        {"op": "set_cell", "table_id": TABLE_ID, "record_id": identity, "field_id": extra, "value": "Keep"}], expected_revision=2)
    store.analyses.update(identity, "New", document(), expected_revision=3)
    table = next(t for t in store.snapshot()["tables"] if t["id"] == TABLE_ID)
    assert table["name"] == "Renamed" and table["records"][0]["values"][extra] == "Keep"
    assert store.analyses.list()["compatible"] and saved(store, identity)["state"] == "readable"


def test_missing_or_wrong_fields_are_diagnosed_without_automatic_repair(store):
    identity = create(store)["record_id"]
    store.apply([{"op": "delete_field", "id": FIELD_IDS["graph"]}], expected_revision=1)
    before = store.snapshot()
    assert not store.analyses.list()["compatible"]
    assert not store.analyses.get(identity)["compatible"]
    assert saved(store, identity)["document"] is None
    with pytest.raises(ProjectError, match="incompatible"):
        create(store)
    assert store.snapshot() == before
    store.undo(expected_revision=2)
    assert saved(store, identity)["state"] == "readable"
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE fields SET type='text' WHERE id=?", (FIELD_IDS["graph"],))
    assert not store.analyses.list()["compatible"]


def test_reserved_field_uuid_collision_never_partially_creates_the_index(store):
    table = str(uuid4())
    store.apply([{"op": "create_table", "id": table, "name": "Other"},
        {"op": "add_field", "table_id": table, "id": FIELD_IDS["graph"], "name": "Occupied", "type": "json"}], expected_revision=0)
    before, history = store.snapshot(), store.history()
    assert store.analyses.list()["compatible"]  # No managed table exists.
    with pytest.raises(ProjectError, match="Reserved"):
        create(store)
    assert store.snapshot() == before and store.history() == history


def test_managed_references_are_not_evaluated_by_reads_or_silently_overwritten(store, monkeypatch):
    identity = create(store)["record_id"]
    other = create(store)["record_id"]
    store.apply([{"op": "set_reference", "table_id": TABLE_ID, "record_id": identity,
        "field_id": FIELD_IDS["graph"], "source": {"record_id": other, "field_id": FIELD_IDS["graph"]}}], expected_revision=2)

    def forbidden(*args, **kwargs):
        raise AssertionError("Read must not evaluate project formulas or build a snapshot")

    monkeypatch.setattr(store, "_snapshot", forbidden)
    monkeypatch.setattr(store, "_evaluate", forbidden)
    assert saved(store, identity)["document"] is None
    assert "literals" in saved(store, identity)["error"]
    assert saved(store, other)["document"] == document()
    assert store.analyses.list()["analyses"][0]["state"] == "invalid"
    with pytest.raises(ProjectError, match="literals"):
        store.analyses.update(identity, "Replacement", document(), expected_revision=3)
    assert store.info()["revision"] == 3


@pytest.mark.parametrize("text", ['{"schema":1,"schema":2}', '{"bad":NaN}', '{"bad":1e400}',
    '{"bad":18446744073709551616}', '{"bad":"\\ud800"}', '{"broken":', '[] trailing',
    '[' * 24000 + '0' + ']' * 24000, '"' + 'x' * (2 * analyses.MAX_DOCUMENT_BYTES) + '"'],
    ids=["duplicate", "nan", "infinite-exponent", "integer", "surrogate", "broken", "trailing", "depth", "size"])
def test_bad_hand_edited_cells_are_bounded_diagnostics_and_can_be_explicitly_replaced(store, text):
    identity = create(store)["record_id"]
    raw_literal(store, identity, "graph", text)
    entry = saved(store, identity)
    assert entry["state"] == "invalid" and entry["document"] is None and entry["error"]
    assert len(entry["error"].encode("utf-8")) <= 512
    assert store.analyses.list()["analyses"][0]["state"] == "invalid"
    store.analyses.update(identity, "Repaired", document(), expected_revision=1)
    assert saved(store, identity)["state"] == "readable"


def test_future_format_is_visible_and_cannot_be_downgraded(store):
    identity = create(store)["record_id"]
    literal(store, identity, "format", "stk.analysis-document/999")
    answer = saved(store, identity)
    assert answer["format"] == "stk.analysis-document/999" and answer["state"] == "unsupported"
    assert answer["document"] is None
    assert store.analyses.list()["analyses"][0]["format"] == answer["format"]
    with pytest.raises(UnsupportedProjectFormat):
        store.analyses.update(identity, "Downgrade", document(), expected_revision=2)
    assert store.info()["revision"] == 2
    value = document()
    value["format"] = "stk.analysis-document/2"
    with pytest.raises(UnsupportedProjectFormat):
        create(store, value)


def test_format_two_is_not_implicitly_upgraded(store):
    with sqlite3.connect(store.path) as db:
        db.execute("PRAGMA user_version=2")
    for action in (lambda: store.analyses.list(), lambda: store.analyses.get(str(uuid4())), lambda: create(store)):
        with pytest.raises(UnsupportedProjectFormat):
            action()
    assert store.info()["format_version"] == 2 and store.info()["revision"] == 0


@pytest.mark.parametrize("offset,limit", [(True, 10), (-1, 10), (2**63, 10), (0, False), (0, 0), (0, 101)])
def test_pagination_rejects_invalid_bounds(store, offset, limit):
    with pytest.raises(ProjectError):
        store.analyses.list(offset=offset, limit=limit)


def test_collection_row_limit_and_paginated_reads_after_generic_edits(store):
    identity = create(store)["record_id"]
    extra = [str(uuid4()) for _ in range(127)]
    store.apply([{"op": "add_record", "table_id": TABLE_ID, "id": key} for key in extra], expected_revision=1)
    assert store.analyses.list()["total"] == 128
    with pytest.raises(ProjectError, match="128"):
        create(store)
    store.analyses.update(identity, "Allowed", document(), expected_revision=2)
    last = str(uuid4())
    store.apply([{"op": "add_record", "table_id": TABLE_ID, "id": last}], expected_revision=3)
    assert store.analyses.list(offset=100, limit=100)["analyses"][-1]["id"] == last
    assert store.analyses.list(offset=129)["analyses"] == []
    before = store.info()["revision"]
    with pytest.raises(ProjectError, match="128"):
        store.analyses.update(identity, "Strict cap", document(), expected_revision=before)
    assert store.info()["revision"] == before


def test_collection_byte_limit_counts_all_managed_json_and_replacements(store, monkeypatch):
    identity = create(store)["record_id"]
    with sqlite3.connect(store.path) as db:
        used = db.execute("SELECT sum(length(CAST(value AS BLOB))) FROM cells WHERE table_id=?", (TABLE_ID,)).fetchone()[0]
    monkeypatch.setattr(analyses, "MAX_COLLECTION_BYTES", used)
    store.analyses.update(identity, "分析", document(), expected_revision=1)  # Replacement is subtracted.
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError, match="4 MiB"):
        create(store)
    with pytest.raises(ProjectError, match="4 MiB"):
        store.analyses.update(identity, "Longer name", document(), expected_revision=2)
    assert store.snapshot() == before and store.history() == history


def test_full_snapshot_guard_rolls_back_tables_revision_journal_and_redo(store, monkeypatch):
    identity = create(store)["record_id"]
    store.analyses.update(identity, "Second", document(), expected_revision=1)
    store.undo(expected_revision=2)
    before, history = store.snapshot(), store.history()
    size = len(json.dumps(before, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    monkeypatch.setattr(analyses, "MAX_SNAPSHOT_BYTES", size)
    with pytest.raises(ProjectError, match="snapshot limit"):
        create(store)
    assert store.snapshot() == before and store.history() == history
    assert store.snapshot()["edit_history"]["redo_revision"] == 2
    store.redo(expected_revision=3)
    assert saved(store, identity)["name"] == "Second"


def test_actual_twelve_mib_snapshot_guard_accounts_for_other_tables(store):
    table, field, record = (str(uuid4()) for _ in range(3))
    store.apply([{"op": "create_table", "id": table, "name": "Existing data"},
        {"op": "add_field", "table_id": table, "id": field, "name": "Large", "type": "text"},
        {"op": "add_record", "table_id": table, "id": record},
        {"op": "set_cell", "table_id": table, "record_id": record, "field_id": field,
         "value": "x" * (12 * 1024 * 1024)}], expected_revision=0)
    with pytest.raises(ProjectError, match="12 MiB"):
        create(store)
    assert store.info()["revision"] == 1
    assert store.analyses.list()["total"] == 0
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM changes").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM tables WHERE id=?", (TABLE_ID,)).fetchone()[0] == 0


def test_reads_stay_available_when_generic_edits_exceed_collection_budget(store, monkeypatch):
    identity = create(store)["record_id"]
    monkeypatch.setattr(analyses, "MAX_COLLECTION_BYTES", 1)
    assert saved(store, identity)["state"] == "readable"
    assert store.analyses.list()["total"] == 1
    with pytest.raises(ProjectError, match="4 MiB"):
        store.analyses.update(identity, "Even identical", document(), expected_revision=1)


def test_storage_does_not_load_registry_plugins_or_execute_graphs(store, monkeypatch):
    from suan.graph import catalog

    def forbidden(*args, **kwargs):
        raise AssertionError("Analysis storage must not load a runtime registry")

    monkeypatch.setattr(catalog, "default_registry", forbidden)
    monkeypatch.setattr(catalog, "build_registry", forbidden)
    identity = create(store)["record_id"]
    assert saved(store, identity)["state"] == "readable"
    assert store.analyses.list()["total"] == 1
    store.analyses.update(identity, "Changed", document(), expected_revision=1)
