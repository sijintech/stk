"""Paged reads preserve snapshot semantics without materializing unrelated data."""
from contextlib import contextmanager
import json
import sqlite3
import tracemalloc
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from test_project_values import command, derived, legacy, model, reference  # noqa: F401


def assert_snapshot_page(store, table_id, **kwargs):
    table = next(table for table in store.snapshot()['tables'] if table['id'] == table_id)
    reply = store.table.query(table_id, expected_revision=store.info()['revision'], **kwargs)
    records = {record['id']: record for record in table['records']}
    # Equality alone would equate integer/float and lose negative zero evidence.
    assert json.dumps(reply['records'], sort_keys=True) == json.dumps(
        [records[identity] for identity in reply['record_ids']], sort_keys=True)
    return reply


@pytest.mark.parametrize('damage', ['missing', 'json', 'future_revision', 'wrong_type'])
def test_cross_table_ancestor_cache_rebuild_is_read_only(model, damage):
    store, ids = derived(model)
    with sqlite3.connect(store.path) as db:
        if damage == 'missing':
            db.execute('DELETE FROM evaluations WHERE field_id=?', (ids['copy'],))
        else:
            result = json.loads(db.execute('SELECT result FROM evaluations WHERE field_id=?', (ids['copy'],)).fetchone()[0])
            if damage == 'future_revision':
                result['evaluated_revision'] = 100
            elif damage == 'wrong_type':
                result['value'] = 'invalid numeric cache'
            db.execute('UPDATE evaluations SET result=? WHERE field_id=?',
                       ('{' if damage == 'json' else json.dumps(result), ids['copy']))
    before = store.path.read_bytes()
    reply = assert_snapshot_page(store, ids['results'], definition={
        'version': 1, 'kind': 'grid', 'columns': [],
        'filters': {'field_id': ids['derived'], 'op': 'gt', 'value': 309},
        'sorts': [{'field_id': ids['derived'], 'direction': 'desc'}]})
    assert reply['fields'] == [] and reply['total'] == 1
    assert reply['records'][0]['values'][ids['derived']] == 310
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('state', ['cycle', 'missing_record', 'wrong_table', 'unset', 'null', 'negative_zero'])
def test_dependency_errors_and_sparse_typed_values_match_snapshot(model, state):
    store, ids = derived(model)
    if state == 'cycle':
        change = command(ids, 'temperature', 'set_reference', source=reference(ids, 'derived'))
    elif state == 'missing_record':
        change = {'op': 'delete_record', 'id': ids['input_row']}
    elif state == 'wrong_table':
        change = command(ids, 'copy', 'set_reference', source={'record_id': ids['input_row'], 'field_id': ids['derived']})
    elif state == 'unset':
        change = command(ids, 'temperature', 'unset_cell')
    else:
        change = command(ids, 'temperature', 'set_cell', value=None if state == 'null' else -0.0)
    store.apply([change], expected_revision=2)
    # Force evaluation to exercise the full cross-table closure, including SCCs.
    with sqlite3.connect(store.path) as db:
        db.execute('DELETE FROM evaluations')
    reply = assert_snapshot_page(store, ids['results'])
    assert reply['total'] == 1
    if state not in {'null', 'negative_zero'}:
        filtered = assert_snapshot_page(store, ids['results'], definition={
            'version': 1, 'kind': 'grid', 'filters': {'field_id': ids['derived'], 'op': 'is_error'}})
        assert filtered['total'] == 1


def test_legacy_format_one_query_does_not_need_definition_tables(model):
    store, ids = model
    store = legacy(store)
    reply = assert_snapshot_page(store, ids['inputs'])
    assert reply['records'][0]['values'][ids['temperature']] == 300
    assert all('options' not in field for field in reply['fields'])


def test_paged_reference_crosses_more_than_a_thousand_off_page_rows(model):
    store, ids = model
    previous = reference(ids, 'temperature')
    with store._connect(write=True) as db:
        for _ in range(1100):
            record = str(uuid4())
            db.execute('INSERT INTO records VALUES (?,?)', (record, ids['inputs']))
            db.execute('INSERT INTO definitions VALUES (?,?,?,?)',
                       (ids['inputs'], record, ids['temperature'], json.dumps({'kind': 'reference', 'source': previous})))
            previous = {'record_id': record, 'field_id': ids['temperature']}
        db.execute('INSERT INTO definitions VALUES (?,?,?,?)',
                   (ids['results'], ids['result_row'], ids['copy'], json.dumps({'kind': 'reference', 'source': previous})))
    reply = assert_snapshot_page(store, ids['results'], limit=1)
    assert reply['records'][0]['values'][ids['copy']] == 300
    with store._connect() as db:
        assert db.execute('SELECT count(*) FROM evaluations').fetchone()[0] == 0


def test_query_uses_one_database_revision_during_concurrent_writer(model, monkeypatch):
    store, ids = derived(model)
    # WAL lets the external writer commit while the query holds its old snapshot.
    with sqlite3.connect(store.path) as db:
        db.execute('PRAGMA journal_mode=WAL')
    original = store._connect
    fired = False

    @contextmanager
    def connect(**kwargs):
        nonlocal fired
        with original(**kwargs) as db:
            def trace(sql):
                nonlocal fired
                if not fired and sql.startswith('SELECT count(*) FROM records'):
                    fired = True
                    other = ProjectStore(store.directory)
                    other.apply([command(ids, 'temperature', 'set_cell', value=400)], expected_revision=2)
            db.set_trace_callback(trace)
            yield db
    monkeypatch.setattr(store, '_connect', connect)
    page = store.table.query(ids['results'], expected_revision=2)
    assert fired and page['revision'] == 2
    assert page['records'][0]['values'][ids['derived']] == 310
    assert store.info()['revision'] == 3


@pytest.mark.parametrize('mode', ['page', 'filter', 'sort'])
def test_query_memory_excludes_off_page_and_unrelated_large_cells(tmp_path, mode):
    store = ProjectStore.create(tmp_path / 'large', 'Synthetic query fixture')
    tables = [str(uuid4()) for _ in range(2)]
    fields = [[str(uuid4()) for _ in range(2)] for _ in tables]
    rows = [[str(uuid4()) for _ in range(512)] for _ in tables]
    # Bulk seed ordinary literal rows; setup cost/history is not the read under test.
    with store._connect(write=True) as db:
        for table, (number, text), identities in zip(tables, fields, rows):
            db.execute('INSERT INTO tables VALUES (?,?)', (table, 'Synthetic'))
            db.executemany('INSERT INTO fields VALUES (?,?,?,?,?)', [
                (number, table, 'Number', 'integer', None), (text, table, 'Text', 'text', None)])
            db.executemany('INSERT INTO records VALUES (?,?)', [(identity, table) for identity in identities])
            db.executemany('INSERT INTO cells VALUES (?,?,?,?)',
                           ((table, identity, field, json.dumps(value)) for index, identity in enumerate(identities)
                            for field, value in [(number, index), (text, 'public fixture; ' * 1024)]))
    definition = {'version': 1, 'kind': 'grid'}
    expected = rows[0][100:103]
    if mode == 'filter':
        definition['filters'] = {'field_id': fields[0][0], 'op': 'gte', 'value': 11}
        expected = rows[0][111:114]
    elif mode == 'sort':
        definition['sorts'] = [{'field_id': fields[0][0], 'direction': 'desc'}]
        expected = list(reversed(rows[0]))[100:103]
    tracemalloc.start()
    try:
        reply = store.table.query(tables[0], expected_revision=0, definition=definition, offset=100, limit=3)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert reply['record_ids'] == expected
    assert reply['total'] == (501 if mode == 'filter' else 512)
    assert all(len(record['values'][fields[0][1]]) == 16384 for record in reply['records'])
    # 16 MiB of text exists across the two tables. A three-row page must not
    # materialize it, even when filtering/sorting requires inspecting every ID.
    assert peak < 4 * 1024 * 1024
