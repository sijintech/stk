"""Large-project opening reads structure and exact record pages, never a full snapshot."""
from contextlib import contextmanager
import json
import sqlite3
import tracemalloc
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import catalog
from test_project_values import command, derived, legacy, model  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def fail_snapshot(*args, **kwargs):
    raise AssertionError("Opening pages must not materialize a project snapshot")


def test_catalog_reads_no_cells_definitions_or_evaluations(model, monkeypatch):
    store, ids = derived(model)
    expected = store.snapshot()
    before = store.path.read_bytes()
    original = store._connect

    @contextmanager
    def connect(**kwargs):
        with original(**kwargs) as db:
            def allow(action, table, column, database, trigger):
                if action == sqlite3.SQLITE_READ and table in {"cells", "definitions", "evaluations", "changes"}:
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            db.set_authorizer(allow)
            yield db
    monkeypatch.setattr(store, '_connect', connect)
    monkeypatch.setattr(store, 'snapshot', fail_snapshot)
    page = store.catalog(limit=1)
    assert page['project'] == expected['project']
    assert page['edit_history'] == expected['edit_history']
    assert page['total'] == 2 and page['offset'] == 0 and page['next_offset'] == 1
    table = page['tables'][0]
    assert table['id'] == ids['inputs'] and table['fields'] == expected['tables'][0]['fields']
    assert table['record_count'] == 1 and table['first_record_id'] == ids['input_row']
    assert 'records' not in table
    second = store.catalog(expected_revision=2, offset=page['next_offset'], limit=1)
    assert second['tables'][0]['id'] == ids['results'] and second['next_offset'] is None
    assert store.catalog(expected_revision=2, offset=100)['tables'] == []
    assert store.path.read_bytes() == before


def test_empty_catalog_and_explicit_missing_record(model):
    store, ids = model
    empty = str(uuid4())
    store.apply([{'op': 'create_table', 'id': empty, 'name': 'Empty'}], expected_revision=1)
    table = store.catalog()['tables'][-1]
    assert table['record_count'] == 0 and table['first_record_id'] is None
    page = store.read_table(empty, expected_revision=2)
    assert page['total'] == 0 and page['next_offset'] is None and page['table']['records'] == []
    for table_id, record_id in [(empty, ids['input_row']), (ids['inputs'], ids['result_row']), (ids['inputs'], str(uuid4()))]:
        with pytest.raises(FileNotFoundError):
            store.read_table(table_id, record_id=record_id, expected_revision=2)
    with pytest.raises(FileNotFoundError):
        store.read_table(str(uuid4()), expected_revision=2)


def test_catalog_file_descriptor_does_not_depend_on_page(model, tmp_path):
    store, ids = model
    resource = tmp_path / 'public.txt'
    resource.write_text('public fixture', encoding='utf-8')
    store.files.index([str(resource)], expected_revision=1)
    snapshot = store.snapshot()
    first = store.catalog(limit=1)
    assert all(table['id'] != snapshot['file_index']['table_id'] for table in first['tables'])
    assert first['file_index'] == snapshot['file_index']
    assert store.catalog(expected_revision=2, offset=2)['file_index'] == snapshot['file_index']


@pytest.mark.parametrize('old_format', [False, True])
def test_record_page_matches_full_snapshot_and_preserves_numeric_types(model, old_format, monkeypatch):
    store, ids = model
    store.apply([command(ids, 'temperature', 'set_cell', value=-0.0)], expected_revision=1)
    if old_format:
        store = legacy(store)
    expected = store.snapshot()
    before = store.path.read_bytes()
    monkeypatch.setattr(store, 'snapshot', fail_snapshot)
    for table in expected['tables']:
        page = store.read_table(table['id'], expected_revision=expected['project']['revision'], limit=1)
        assert json.dumps(page['table'], sort_keys=True) == json.dumps(table, sort_keys=True)
        assert page['format_version'] == expected['format_version']
    assert store.path.read_bytes() == before


def test_record_page_rebuilds_cross_table_dependencies_without_writes(model):
    store, ids = derived(model)
    with sqlite3.connect(store.path) as db:
        db.execute('DELETE FROM evaluations')
    before = store.path.read_bytes()
    expected = store.snapshot()['tables'][1]
    page = store.read_table(ids['results'], expected_revision=2, record_id=ids['result_row'])
    assert json.dumps(page['table'], sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert page['table']['records'][0]['values'][ids['derived']] == 310
    assert store.path.read_bytes() == before


def test_record_location_uses_insertion_order_and_survives_renaming(model):
    store, ids = model
    rows = [str(uuid4()) for _ in range(11)]
    store.apply([{'op': 'add_record', 'id': row, 'table_id': ids['inputs']} for row in rows], expected_revision=1)
    store.apply([{'op': 'rename_table', 'id': ids['inputs'], 'name': 'Renamed'},
                 {'op': 'delete_record', 'id': rows[1]}], expected_revision=2)
    expected = [ids['input_row'], *rows[:1], *rows[2:]]
    page = store.read_table(ids['inputs'], expected_revision=3, record_id=rows[7], limit=3)
    assert page['offset'] == 6 and page['next_offset'] == 9 and page['total'] == 11
    assert [row['id'] for row in page['table']['records']] == expected[6:9]
    assert page['table']['name'] == 'Renamed'
    assert store.read_table(ids['inputs'], expected_revision=3, offset=9, limit=3)['next_offset'] is None
    store.undo(expected_revision=3)
    with pytest.raises(RevisionConflict):
        store.read_table(ids['inputs'], expected_revision=3, record_id=rows[7])


@pytest.mark.parametrize('operation', ['catalog', 'read_table'])
def test_read_is_consistent_during_concurrent_writer(model, monkeypatch, operation):
    store, ids = model
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
                if not fired and sql.startswith('SELECT count(*) FROM'):
                    fired = True
                    ProjectStore(store.directory).apply([command(ids, 'temperature', 'set_cell', value=400)], expected_revision=1)
            db.set_trace_callback(trace)
            yield db
    monkeypatch.setattr(store, '_connect', connect)
    if operation == 'catalog':
        page = store.catalog(expected_revision=1, limit=1)
        assert page['project']['revision'] == 1
        with pytest.raises(RevisionConflict):
            store.catalog(expected_revision=1, offset=1)
    else:
        page = store.read_table(ids['inputs'], expected_revision=1)
        assert page['revision'] == 1 and page['table']['records'][0]['values'][ids['temperature']] == 300
    assert fired and store.info()['revision'] == 2


@pytest.mark.parametrize('kwargs', [{'offset': True}, {'offset': -1}, {'offset': 2**63}, {'limit': True}, {'limit': 0}, {'limit': 501}])
def test_bad_page_boundaries_rejected(model, kwargs):
    store, ids = model
    with pytest.raises(ProjectError):
        store.catalog(**kwargs)
    with pytest.raises(ProjectError):
        store.read_table(ids['inputs'], expected_revision=1, **kwargs)


def test_read_requires_revision_and_unambiguous_position(model):
    store, ids = model
    with pytest.raises(ProjectError):
        store.catalog(offset=1)
    with pytest.raises(ProjectError):
        store.read_table(ids['inputs'], expected_revision=1, record_id=ids['input_row'], offset=1)
    for revision in [None, True, -1, 1.0]:
        with pytest.raises(ProjectError):
            store.read_table(ids['inputs'], expected_revision=revision)
    with pytest.raises(RevisionConflict):
        store.catalog(expected_revision=0)


def test_utf8_budget_is_bytes_and_does_not_return_partial_success(model, monkeypatch):
    store, ids = model
    store.apply([{'op': 'rename_table', 'id': ids['inputs'], 'name': '中文' * 100}], expected_revision=1)
    result = store.catalog(limit=1)
    text = json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True)
    monkeypatch.setattr(catalog, 'MAX_READ_BYTES', len(text))
    with pytest.raises(ProjectError, match='reduce the page size'):
        store.catalog(limit=1)
    monkeypatch.setattr(catalog, 'MAX_READ_BYTES', 1)
    with pytest.raises(ProjectError):
        store.read_table(ids['inputs'], expected_revision=2)


def test_first_reads_do_not_decode_unrelated_or_off_page_cells(model, monkeypatch):
    store, ids = model
    rows = [str(uuid4()) for _ in range(1000)]
    with store._connect(write=True) as db:
        db.executemany('INSERT INTO records VALUES (?,?)', [(row, ids['inputs']) for row in rows])
        # Invalid JSON is deliberate: no off-page cell may be decoded. A whole
        # snapshot fails, while the first page remains well-defined and usable.
        db.executemany('INSERT INTO cells VALUES (?,?,?,?)',
                       ((ids['inputs'], row, ids['temperature'], '{') for row in rows))
        db.execute('INSERT INTO cells VALUES (?,?,?,?)', (ids['results'], ids['result_row'], ids['copy'], '{'))
    monkeypatch.setattr(store, 'snapshot', fail_snapshot)
    tracemalloc.start()
    try:
        structure = store.catalog(limit=1)
        page = store.read_table(ids['inputs'], expected_revision=1, limit=1)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert structure['tables'][0]['record_count'] == 1001 and peak < 2 * 1024 * 1024
    assert page['total'] == 1001 and page['table']['records'][0]['values'][ids['temperature']] == 300


def test_bridge_and_python_use_same_paged_contract(model, inproc):
    from suan.scripting import Project
    store, ids = model
    harness = inproc()
    hello = harness.call('hello', {'protocol': 1})
    assert {'project.catalog', 'project.table.read'} <= set(hello['methods'])
    handle = harness.call('project.open', {'directory': str(store.directory)})['project']['handle']
    project = Project(harness.call, handle)
    first = project.catalog(limit=1)
    assert first['tables'][0]['id'] == ids['inputs']
    assert project.catalog(expected_revision=1, offset=1)['tables'][0]['id'] == ids['results']
    page = project.table.read(ids['inputs'], expected_revision=1, record_id=ids['input_row'], limit=1)
    assert page['table']['records'][0]['values'][ids['temperature']] == 300
    params = {'handle': handle, 'table_id': ids['inputs'], 'expected_revision': 1, 'record_id': ids['result_row']}
    assert harness.error('project.table.read', params)['code'] == 'not_found'
    assert not harness.events_of('project.changed') and harness.violations == []
