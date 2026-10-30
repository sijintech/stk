"""Typed cells and views share the real project transaction, history and identities."""
from copy import deepcopy
import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest

from suan.project import ProjectStore, ProjectError, RevisionConflict
from suan.project.store import FORMAT_VERSION, UnsupportedProjectFormat
from suan.project.field_types import OBJECT_KINDS
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_analyses import document as analysis_document


def uid():
    return str(uuid4())


@pytest.fixture
def table(tmp_path):
    store = ProjectStore.create(tmp_path / 'project', 'Typed grid')
    ids = {key: uid() for key in ('table', 'text', 'number', 'a', 'b', 'c')}
    store.apply([
        {'op': 'create_table', 'id': ids['table'], 'name': 'Cases'},
        {'op': 'add_field', 'id': ids['text'], 'table_id': ids['table'], 'name': 'Text', 'type': 'text'},
        {'op': 'add_field', 'id': ids['number'], 'table_id': ids['table'], 'name': 'Count', 'type': 'integer'},
        *[{'op': 'add_record', 'id': ids[k], 'table_id': ids['table']} for k in ('a', 'b', 'c')],
    ], expected_revision=0)
    return store, ids


def cell(ids, row, field, value):
    return {'op': 'set_cell', 'table_id': ids['table'], 'record_id': ids[row], 'field_id': ids[field], 'value': value}


def add_type(store, ids, kind, config=None):
    identity = uid()
    command = {'op': 'add_field', 'table_id': ids['table'], 'id': identity, 'name': kind, 'type': kind}
    if config is not None:
        command['options'] = config
    store.apply([command], expected_revision=store.info()['revision'])
    return identity


@pytest.mark.parametrize('kind,valid,invalid', [
    ('date', '2024-02-29', '2023-02-29'), ('date', '2026-01-02', '20260102'),
    ('url', 'https://example.org/a?q=1', 'file:///etc/passwd'),
    ('url', 'http://localhost:8000/a', 'https://name:credential@example.org'),
    ('url', 'https://example.org/a', '\0https://example.org/a'),
    ('url', 'https://example.org/a', 'https://example.org/\x7f'),
])
def test_typed_literals_reopen_and_invalid_batch_is_atomic(table, kind, valid, invalid):
    store, ids = table
    field = add_type(store, ids, kind)
    good = {**cell(ids, 'a', 'text', valid), 'field_id': field}
    store.apply([good], expected_revision=2)
    assert ProjectStore(store.directory).snapshot()['tables'][0]['records'][0]['values'][field] == valid
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError):
        store.apply([cell(ids, 'a', 'text', 'must roll back'), {**good, 'value': invalid}], expected_revision=3)
    assert store.snapshot() == before and store.history() == history
    store.undo(expected_revision=3)
    assert field not in store.snapshot()['tables'][0]['records'][0]['values']


def test_choices_keep_ids_on_rename_reject_used_removal_and_undo_schema_with_cells(table):
    store, ids = table
    one, two = uid(), uid()
    config = {'version': 1, 'choices': [{'id': one, 'label': 'Ready', 'color': '#123abc'},
                                      {'id': two, 'label': 'Done', 'color': '#345678'}]}
    field = add_type(store, ids, 'single_select', config)
    store.apply([{**cell(ids, 'a', 'text', one), 'field_id': field}], expected_revision=2)
    changed = deepcopy(config); changed['choices'][0]['label'] = 'Prepared'
    command = {'op': 'set_field_schema', 'id': field, 'type': 'single_select', 'unit': None, 'options': changed}
    store.apply([command], expected_revision=3)
    current = store.snapshot()['tables'][0]
    assert current['records'][0]['values'][field] == one
    assert next(f for f in current['fields'] if f['id'] == field)['options'] == changed
    bad = deepcopy(command); bad['options']['choices'].pop(0)
    before = store.snapshot()
    with pytest.raises(ProjectError, match='choice'):
        store.apply([bad], expected_revision=4)
    assert store.snapshot() == before
    store.undo(expected_revision=4)
    assert next(f for f in store.snapshot()['tables'][0]['fields'] if f['id'] == field)['options'] == config
    multi = add_type(store, ids, 'multi_select', config)
    with pytest.raises(ProjectError):
        store.apply([{**cell(ids, 'a', 'text', [one, one]), 'field_id': multi}], expected_revision=6)


def test_reference_into_typed_date_validates_result_and_keeps_error_diagnostics(table):
    store, ids = table
    field = add_type(store, ids, 'date')
    store.apply([cell(ids, 'a', 'text', '2026-10-15'), {'op': 'set_reference', 'table_id': ids['table'],
                 'record_id': ids['a'], 'field_id': field, 'source': {'record_id': ids['a'], 'field_id': ids['text']}}], expected_revision=2)
    record = store.snapshot()['tables'][0]['records'][0]
    assert record['values'][field] == '2026-10-15' and record['evaluations'][field]['state'] == 'ok'
    store.apply([cell(ids, 'a', 'text', 'not a date')], expected_revision=3)
    assert store.snapshot()['tables'][0]['records'][0]['evaluations'][field]['error']['code'] == 'type'


def test_view_type_and_options_delete_cascade_restore_all_original_ids(table):
    store, ids = table
    field = add_type(store, ids, 'date')
    view_id = uid()
    view = {'op': 'put_table_view', 'id': view_id, 'table_id': ids['table'], 'name': 'Calendar data',
            'definition': {'version': 1, 'kind': 'gallery', 'columns': [{'field_id': field, 'width': 200}]}}
    store.apply([view], expected_revision=2)
    before = store.snapshot()['tables']
    saved = store.table.views_get(view_id, expected_revision=3)['view']
    store.apply([{'op': 'delete_table', 'id': ids['table']}], expected_revision=3)
    assert store.snapshot()['tables'] == []
    store.undo(expected_revision=4)
    assert store.snapshot()['tables'] == before
    assert store.table.views_get(view_id, expected_revision=5)['view'] == saved
    store.redo(expected_revision=5)
    assert store.snapshot()['tables'] == []


def test_format13_explicit_backup_upgrade_preserves_old_journal_row_shapes(table):
    store, ids = table
    with sqlite3.connect(store.path) as db:
        db.execute('DROP TABLE field_options'); db.execute('DROP TABLE table_views')
        db.execute('DROP TABLE project_edit_operations')
        db.execute('PRAGMA user_version=13')
    before = store.snapshot()['tables']
    assert store.table.views_list(ids['table'], expected_revision=1)['views'] == []
    assert store.table.query(ids['table'], expected_revision=1)['total'] == 3
    with pytest.raises(UnsupportedProjectFormat):
        add_type(store, ids, 'date')
    upgraded = store.upgrade(expected_revision=1)
    assert upgraded['format_version'] == FORMAT_VERSION == 15 and upgraded['backup']['format_version'] == 13
    assert [f['id'] for f in store.snapshot()['tables'][0]['fields']] == [f['id'] for f in before[0]['fields']]
    store.undo(expected_revision=2)
    assert store.snapshot()['tables'] == []
    store.redo(expected_revision=3)
    assert store.table.query(ids['table'], expected_revision=4)['total'] == 3


def test_format14_opens_without_upgrade_and_explicit_upgrade_keeps_verified_backup(table):
    store, ids = table
    with sqlite3.connect(store.path) as db:
        db.execute('DROP TABLE project_edit_operations')
        db.execute('PRAGMA user_version=14')
    old = ProjectStore(store.directory)
    before = old.snapshot()['tables']
    assert old.info()['format_version'] == 14
    assert old.table.query(ids['table'], expected_revision=1)['total'] == 3
    assert ProjectStore(store.directory).info()['format_version'] == 14

    upgraded = old.upgrade(expected_revision=1)
    assert upgraded['format_version'] == FORMAT_VERSION == 15
    assert upgraded['revision'] == 2 and upgraded['backup']['format_version'] == 14
    assert old.snapshot()['tables'] == before
    assert old.table.query(ids['table'], expected_revision=2)['total'] == 3
    with sqlite3.connect(upgraded['backup']['path']) as backup:
        assert backup.execute('PRAGMA user_version').fetchone()[0] == 14
        assert backup.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert backup.execute("SELECT name FROM sqlite_master WHERE name='project_edit_operations'").fetchall() == []
    assert ProjectStore(store.directory).info()['format_version'] == 15


def test_query_numeric_sort_int64_formula_null_unset_and_filters_are_typed(table):
    store, ids = table
    store.apply([cell(ids, 'a', 'number', 9007199254740993), cell(ids, 'b', 'number', 9007199254740992),
                 cell(ids, 'c', 'number', None)], expected_revision=1)
    definition = {'version': 1, 'kind': 'grid', 'sorts': [{'field_id': ids['number'], 'direction': 'asc'}]}
    result = store.table.query(ids['table'], expected_revision=2, definition=definition, limit=2)
    assert result['record_ids'] == [ids['b'], ids['a']] and result['next_offset'] == 2
    definition['filters'] = {'op': 'or', 'conditions': [
        {'field_id': ids['number'], 'op': 'gt', 'value': 9007199254740992},
        {'field_id': ids['number'], 'op': 'is_null'}]}
    assert store.table.query(ids['table'], expected_revision=2, definition=definition)['record_ids'] == [ids['a'], ids['c']]
    with pytest.raises(RevisionConflict):
        store.table.query(ids['table'], expected_revision=1)


def test_view_default_columns_and_frozen_count_use_the_explicit_column_rectangle(table):
    store, ids = table
    result = store.table.query(ids['table'], expected_revision=1,
                               definition={'version': 1, 'kind': 'grid', 'frozen_columns': 2})
    assert result['definition']['columns'] == [
        {'field_id': ids['text'], 'width': 160, 'hidden': False},
        {'field_id': ids['number'], 'width': 160, 'hidden': False}]
    assert result['definition']['frozen_columns'] == 2
    empty = {'version': 1, 'kind': 'grid', 'columns': []}
    assert store.table.query(ids['table'], expected_revision=1, definition=empty)['fields'] == []
    for invalid in ({**empty, 'frozen_columns': 1},
                    {'version': 1, 'kind': 'grid', 'frozen_columns': 3},
                    {'version': 1, 'kind': 'grid', 'frozen_columns': True}):
        with pytest.raises(ProjectError, match='frozen'):
            store.table.query(ids['table'], expected_revision=1, definition=invalid)
    blank = uid()
    store.apply([{'op': 'create_table', 'id': blank, 'name': 'No fields'}], expected_revision=1)
    assert store.table.query(blank, expected_revision=2)['definition']['frozen_columns'] == 0
    with pytest.raises(ProjectError, match='frozen'):
        store.table.query(blank, expected_revision=2,
                          definition={'version': 1, 'kind': 'grid', 'frozen_columns': 1})


def test_grouped_query_orders_before_pagination_and_sorts_within_each_group(table):
    store, ids = table
    ids.update({name: uid() for name in ('d', 'e', 'f')})
    store.apply([
        *[{'op': 'add_record', 'id': ids[name], 'table_id': ids['table']} for name in ('d', 'e', 'f')],
        cell(ids, 'a', 'number', 2), cell(ids, 'a', 'text', 'z'),
        cell(ids, 'b', 'number', 1), cell(ids, 'b', 'text', 'a'),
        cell(ids, 'c', 'number', 2), cell(ids, 'c', 'text', 'b'),
        cell(ids, 'd', 'number', 1), cell(ids, 'd', 'text', 'y'),
        cell(ids, 'e', 'number', None), cell(ids, 'e', 'text', 'x'),
        cell(ids, 'f', 'text', 'w'),
    ], expected_revision=1)
    definition = {'version': 1, 'kind': 'grid', 'group_field_id': ids['number'],
                  'sorts': [{'field_id': ids['text'], 'direction': 'desc', 'nulls': 'last'}]}
    first = store.table.query(ids['table'], expected_revision=2, definition=definition, limit=3)
    second = store.table.query(ids['table'], expected_revision=2, definition=definition, offset=first['next_offset'], limit=3)
    assert first['record_ids'] == [ids['d'], ids['b'], ids['a']]
    assert second['record_ids'] == [ids['c'], ids['e'], ids['f']]
    assert first['total'] == 6 and second['next_offset'] is None
    assert first['definition']['sorts'] == definition['sorts']


def test_deleted_field_keeps_named_view_diagnostic_and_undo_repairs_it(table):
    store, ids = table
    view_id = uid()
    store.apply([{'op': 'put_table_view', 'id': view_id, 'table_id': ids['table'], 'name': 'Saved',
                  'definition': {'version': 1, 'kind': 'board', 'group_field_id': ids['text']}}], expected_revision=1)
    store.apply([{'op': 'delete_field', 'id': ids['text']}], expected_revision=2)
    result = store.table.query(ids['table'], expected_revision=3, view_id=view_id)
    assert result['issues'] and not result['records']
    store.undo(expected_revision=3)
    assert store.table.query(ids['table'], expected_revision=4, view_id=view_id)['total'] == 3


def test_paste_plan_complete_tsv_sorted_uuid_mapping_append_single_undo_and_conflict(table):
    store, ids = table
    before, history = store.snapshot(), store.history()
    plan = store.table.paste_plan(ids['table'], [ids['b']], [ids['text'], ids['number']],
                                '"quoted\n中文"\t9007199254740993\nnext\t2\n', expected_revision=1, append_rows=True)
    assert store.snapshot() == before and store.history() == history
    assert plan['command_count'] == 5 and len(plan['record_ids']) == 2
    store.apply(plan['commands'], expected_revision=plan['base_revision'])
    got = store.table.query(ids['table'], expected_revision=2)
    record = next(r for r in got['records'] if r['id'] == ids['b'])
    assert record['values'][ids['text']] == 'quoted\n中文'
    assert record['values'][ids['number']] == 9007199254740993
    with pytest.raises(RevisionConflict):
        store.apply(plan['commands'], expected_revision=1)
    store.undo(expected_revision=2)
    assert store.snapshot()['tables'] == before['tables']
    store.redo(expected_revision=3)
    assert plan['record_ids'][1] in store.table.query(ids['table'], expected_revision=4)['record_ids']


@pytest.mark.parametrize('text,kwargs', [('x\tbad', {}), ('a\t1\nb\t2', {}), ('x\t1\n'*501, {'append_rows': True}), ('x\t1\textra', {})])
def test_invalid_paste_never_partially_edits_or_advances_history(table, text, kwargs):
    store, ids = table
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError):
        store.table.paste_plan(ids['table'], [ids['a']], [ids['text'], ids['number']], text, expected_revision=1, **kwargs)
    assert store.snapshot() == before and store.history() == history


def test_paste_fit_targets_parses_quoted_multiline_once_and_uses_only_the_uuid_prefix(table):
    store, ids = table
    plan = store.table.paste_plan(ids['table'], [ids['c'], ids['b'], ids['a']], [ids['text'], ids['number']],
                                '"full\nquoted 中文"\nnext\n', expected_revision=1, fit_targets=True)
    assert plan['record_ids'] == [ids['c'], ids['b']] and plan['field_ids'] == [ids['text']]
    assert plan['rows'] == 2 and plan['columns'] == 1 and plan['command_count'] == 2
    store.apply(plan['commands'], expected_revision=1)
    records = {r['id']: r for r in store.snapshot()['tables'][0]['records']}
    assert records[ids['c']]['values'][ids['text']] == 'full\nquoted 中文'
    assert records[ids['b']]['values'][ids['text']] == 'next' and records[ids['a']]['values'] == {}
    with pytest.raises(ProjectError):
        store.table.paste_plan(ids['table'], [ids['a']], [ids['text']], 'too\twide',
                               expected_revision=2, fit_targets=True)


def test_object_record_source_binding_missing_after_delete_and_foreign_rejection(table):
    store, ids = table
    field = add_type(store, ids, 'object', {'version': 1, 'kinds': ['record']})
    candidate = store.table.objects_list_candidates('record', table_id=ids['table'], expected_revision=2)['items'][0]
    ref = candidate['reference']
    assert ref['id'] == ids['a'] and candidate['state'] == 'available'
    store.apply([{**cell(ids, 'b', 'text', ref), 'field_id': field}], expected_revision=2)
    store.apply([cell(ids, 'a', 'text', 'changed')], expected_revision=3)
    assert store.table.objects_resolve(ref, expected_revision=4)['state'] == 'stale'
    store.apply([{'op': 'delete_record', 'id': ids['a']}], expected_revision=4)
    assert store.table.objects_resolve(ref, expected_revision=5)['state'] == 'missing'
    bad = {**ref, 'project_id': uid()}
    before = store.snapshot()
    with pytest.raises(ProjectError):
        store.apply([{**cell(ids, 'b', 'text', bad), 'field_id': field}], expected_revision=5)
    assert store.snapshot() == before


def test_record_candidates_prefer_readable_literal_text_and_bound_labels_without_evaluation(table):
    store, ids = table
    extra = uid()
    store.apply([
        {'op': 'add_field', 'id': extra, 'table_id': ids['table'], 'name': 'Sample ID', 'type': 'text'},
        cell(ids, 'a', 'text', 'Batch A'), cell(ids, 'a', 'number', 42),
        cell(ids, 'b', 'text', '  '), cell(ids, 'b', 'number', 0),
        {**cell(ids, 'b', 'text', 'Second sample'), 'field_id': extra},
        {'op': 'set_reference', 'table_id': ids['table'], 'record_id': ids['c'], 'field_id': ids['text'],
         'source': {'record_id': ids['a'], 'field_id': ids['text']}},
    ], expected_revision=1)
    items = store.table.objects_list_candidates('record', table_id=ids['table'], expected_revision=2)['items']
    assert [item['label'] for item in items] == ['Cases / Batch A', 'Cases / Second sample', 'Cases / ' + ids['c'][:8]]
    assert [item['reference']['id'] for item in items] == [ids['a'], ids['b'], ids['c']]
    value = 'Useful\n\0' + 'sample' * 1000
    store.apply([cell(ids, 'a', 'text', value)], expected_revision=2)
    item = store.table.objects_list_candidates('record', table_id=ids['table'], expected_revision=3)['items'][0]
    assert item['label'].startswith('Cases / Useful sample') and len(item['label']) <= 195
    assert '\0' not in item['label'] and '\n' not in item['label']
    assert store.snapshot()['tables'][0]['records'][0]['values'][ids['text']] == value
    assert store.table.objects_resolve(item['reference'], expected_revision=3)['state'] == 'available'


def test_object_file_snapshot_analysis_workflow_and_simulation_resolve_actual_metadata(table, monkeypatch):
    store, ids = table
    source = store.directory / 'input.dat'; source.write_bytes(b'not executed')
    indexed = store.files.index([str(source)], expected_revision=1)
    frozen = store.snapshots.capture(indexed['record_ids'], expected_revision=2)
    analysis = uid(); store.analyses.create('Saved analysis', analysis_document(), analysis_id=analysis, expected_revision=3)
    workflow = uid()
    store.workflows.create('Saved workflow', {'format': 'stk.workflow/1', 'steps': [
        {'id': 'cases', 'kind': 'table', 'ref': {'table': ids['table']}}], 'ui': {}}, workflow_id=workflow, expected_revision=4)
    run = store.runs.prepare([{'table_id': ids['table'], 'record_id': ids['a'], 'spec': {
        'workspace_id': 'a'*32, 'argv': ['never-run']}}], connection='runtime:Test',
        connection_identity='a'*16, expected_revision=5)['run_ids'][0]
    revision = store.info()['revision']
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('object metadata must not execute'))
    for kind in OBJECT_KINDS - {'record'}:
        found = store.table.objects_list_candidates(kind, expected_revision=revision)['items']
        assert found and found[0]['state'] == 'available', (kind, found)
        resolved = store.table.objects_resolve(found[0]['reference'], expected_revision=revision)
        assert resolved['state'] == 'available' and resolved['summary']
    assert run and frozen['snapshot']['id']


def test_snapshot_file_candidates_bind_source_record_even_when_bytes_are_identical(table, inproc):
    from suan.scripting import API
    store, ids = table
    paths = [store.directory / name for name in ('first.txt', 'second.txt')]
    for path in paths:
        path.write_bytes(b'identical public fixture bytes')
    indexed = store.files.index([str(path) for path in paths], expected_revision=1)
    store.snapshots.capture(indexed['record_ids'], expected_revision=2)
    h = inproc()
    project = API(h.call).projects.open(store.directory)
    items = project.table.objects_list_candidates('snapshot_file', expected_revision=3)['items']
    assert [item['label'] for item in items] == ['first.txt', 'second.txt']
    refs = [item['reference'] for item in items]
    assert refs[0]['path'] == refs[1]['path'] and refs[0]['id'] == refs[1]['id']
    assert refs[0]['record_id'] != refs[1]['record_id']
    for ref, name in zip(refs, ('first.txt', 'second.txt')):
        resolved = project.table.objects_resolve(ref, expected_revision=3)
        assert resolved['state'] == 'available' and resolved['label'] == name
        assert resolved['summary']['record_id'] == ref['record_id']
    legacy = {key: value for key, value in refs[0].items() if key != 'record_id'}
    assert project.table.objects_resolve(legacy, expected_revision=3)['state'] == 'stale'
    wrong = {**refs[0], 'record_id': uid()}
    assert project.table.objects_resolve(wrong, expected_revision=3)['state'] == 'stale'
    wrong = {**refs[0], 'source_sha256': '0' * 64}
    assert project.table.objects_resolve(wrong, expected_revision=3)['state'] == 'stale'
    assert not h.violations


def test_csv_preview_and_changed_bytes_refuse_import_without_mutation(table):
    store, ids = table
    source = store.directory / 'parameters.csv'; source.write_bytes(b'Name,Count\r\na,1\r\nb,2\r\n')
    preview = store.csv.preview(source, expected_revision=1, limit=1)
    assert preview['rows'] == [['a', '1']] and preview['truncated'] and preview['can_import']
    assert preview['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_bytes(b'Name,Count\na,9\n')
    before = store.snapshot()
    with pytest.raises(RevisionConflict):
        store.csv.import_file(source, name='CSV', expected_revision=1, expected_sha256=preview['source_sha256'])
    assert store.snapshot() == before


def test_export_current_view_materializes_exact_filtered_sorted_visible_column_order(table):
    import csv
    store, ids = table
    store.apply([cell(ids, 'a', 'text', 'exclude'), cell(ids, 'a', 'number', 1),
                 cell(ids, 'b', 'text', 'second'), cell(ids, 'b', 'number', 2),
                 cell(ids, 'c', 'text', 'first'), cell(ids, 'c', 'number', 3)], expected_revision=1)
    definition = {'version': 1, 'kind': 'grid', 'columns': [
        {'field_id': ids['number'], 'hidden': True}, {'field_id': ids['text']}],
        'sorts': [{'field_id': ids['number'], 'direction': 'desc'}],
        'filters': {'field_id': ids['number'], 'op': 'gt', 'value': 1}}
    output = store.directory / 'view.csv'
    result = store.csv.export_file(ids['table'], output, expected_revision=2, definition=definition)
    with output.open(encoding='utf-8-sig', newline='') as stream:
        assert list(csv.reader(stream)) == [['Text'], ['first'], ['second']]
    assert result['rows'] == 2 and result['columns'] == 1 and store.info()['revision'] == 2
    with pytest.raises(FileExistsError):
        store.csv.export_file(ids['table'], output, expected_revision=2, definition=definition)


@pytest.mark.parametrize('definition', [
    {'version': 1, 'kind': 'grid', 'unrecognized': True},
    {'version': 1, 'kind': 'grid', 'filters': {'op': 'eval', 'value': '__import__("os")'}},
    {'version': 1, 'kind': 'grid', 'sorts': [{'field_id': uid(), 'direction': 'asc'}]},
])
def test_view_validation_rejects_unknown_fields_code_and_foreign_sources_atomically(table, definition):
    store, ids = table
    before, history = store.snapshot(), store.history()
    with pytest.raises(ProjectError):
        store.apply([cell(ids, 'a', 'text', 'must not persist'), {'op': 'put_table_view', 'id': uid(),
            'table_id': ids['table'], 'name': 'Bad', 'definition': definition}], expected_revision=1)
    assert store.snapshot() == before and store.history() == history


def test_bridge_read_plan_schema_and_mutation_notifications_remain_separate(inproc, tmp_path):
    bridge = inproc()
    opened = bridge.call('project.create', {'directory': str(tmp_path / 'bridge-project'), 'name': 'Grid'})['project']
    handle = opened['handle']; table_id, field, record = uid(), uid(), uid()
    bridge.call('project.apply', {'handle': handle, 'expected_revision': 0, 'commands': [
        {'op': 'create_table', 'id': table_id, 'name': 'Cases'},
        {'op': 'add_field', 'table_id': table_id, 'id': field, 'name': 'Value', 'type': 'integer'},
        {'op': 'add_record', 'table_id': table_id, 'id': record}]})
    params = {'handle': handle, 'expected_revision': 1, 'table_id': table_id}
    assert bridge.call('project.table.views.list', params)['views'] == []
    before = len(bridge.events_of('project.changed'))
    plan = bridge.call('project.table.paste.plan', {**params, 'record_ids': [record], 'field_ids': [field], 'text': '42'})
    assert len(bridge.events_of('project.changed')) == before
    assert bridge.call('project.table.query', params)['records'][0]['values'] == {}
    bridge.call('project.apply', {'handle': handle, 'expected_revision': 1, 'commands': plan['commands']})
    assert bridge.call('project.table.query', {**params, 'expected_revision': 2})['records'][0]['values'][field] == 42
    assert not bridge.violations


def test_all_table_read_endpoints_use_strict_schema_and_pinned_revision(inproc, tmp_path):
    bridge = inproc()
    project = bridge.call('project.create', {'directory': str(tmp_path / 'api-project'), 'name': 'API'})['project']
    handle, table_id, field, record, view_id = project['handle'], uid(), uid(), uid(), uid()
    bridge.call('project.apply', {'handle': handle, 'expected_revision': 0, 'commands': [
        {'op': 'create_table', 'id': table_id, 'name': 'Cases'},
        {'op': 'add_field', 'id': field, 'table_id': table_id, 'name': 'Date', 'type': 'date'},
        {'op': 'add_record', 'id': record, 'table_id': table_id},
        {'op': 'set_cell', 'table_id': table_id, 'record_id': record, 'field_id': field, 'value': '2026-10-15'},
        {'op': 'put_table_view', 'id': view_id, 'table_id': table_id, 'name': 'View', 'definition': {'version': 1, 'kind': 'grid'}}]})
    base = {'handle': handle, 'expected_revision': 1}
    assert bridge.call('project.table.views.get', {**base, 'id': view_id})['view']['id'] == view_id
    assert bridge.call('project.table.views.list', {**base, 'table_id': table_id})['views'][0]['id'] == view_id
    refs = bridge.call('project.table.objects.list_candidates', {**base, 'kind': 'record', 'table_id': table_id})
    assert bridge.call('project.table.objects.resolve', {**base, 'reference': refs['items'][0]['reference']})['state'] == 'available'
    query = bridge.call('project.table.query', {**base, 'table_id': table_id, 'view_id': view_id})
    assert query['fields'][0]['options'] == {'version': 1}
    source = tmp_path / 'preview.csv'; source.write_bytes(b'A\r\n1\r\n')
    preview = bridge.call('project.table.csv.preview', {**base, 'source': str(source)})
    assert preview['rows'] == [['1']] and preview['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_bytes(b'A\r\n2\r\n')
    assert bridge.error('project.csv.import', {**base, 'source': str(source), 'name': 'Changed',
                         'expected_sha256': preview['source_sha256']})['code'] == 'conflict'
    assert bridge.error('project.table.query', {**base, 'table_id': table_id, 'expected_revision': 0})['code'] == 'conflict'
    assert not bridge.violations


def test_used_derived_choice_cannot_be_removed_by_option_reconfiguration(table):
    store, ids = table
    choice = uid()
    config = {'version': 1, 'choices': [{'id': choice, 'label': 'Used', 'color': '#123456'}]}
    field = add_type(store, ids, 'single_select', config)
    store.apply([cell(ids, 'a', 'text', choice), {'op': 'set_reference', 'table_id': ids['table'],
        'record_id': ids['a'], 'field_id': field, 'source': {'record_id': ids['a'], 'field_id': ids['text']}}], expected_revision=2)
    assert store.snapshot()['tables'][0]['records'][0]['evaluations'][field]['state'] == 'ok'
    replacement = {'version': 1, 'choices': [{'id': uid(), 'label': 'New', 'color': '#abcdef'}]}
    before = store.snapshot()
    with pytest.raises(ProjectError, match='used choice'):
        store.apply([{'op': 'set_field_schema', 'id': field, 'type': 'single_select', 'unit': None, 'options': replacement}], expected_revision=3)
    assert store.snapshot() == before


def test_options_only_undo_redo_invalidates_typed_reference_cache(table):
    store, ids = table
    file = store.directory / 'attachment.txt'; file.write_bytes(b'plain fixture')
    file_id = store.files.index([str(file)], expected_revision=1)['record_ids'][0]
    source = add_type(store, ids, 'object', {'version': 1, 'kinds': ['file']})
    target = add_type(store, ids, 'object', {'version': 1, 'kinds': ['file']})
    ref = {'version': 1, 'project_id': store.info()['id'], 'kind': 'file', 'id': file_id}
    store.apply([{**cell(ids, 'a', 'text', ref), 'field_id': source},
                 {'op': 'set_reference', 'table_id': ids['table'], 'record_id': ids['a'], 'field_id': target,
                  'source': {'record_id': ids['a'], 'field_id': source}}], expected_revision=4)
    def state():
        return store.snapshot()['tables'][0]['records'][0]['evaluations'][target]['state']
    assert state() == 'ok'
    store.apply([{'op': 'set_field_schema', 'id': target, 'type': 'object', 'unit': None,
                  'options': {'version': 1, 'kinds': ['record']}}], expected_revision=5)
    assert state() == 'error'
    store.undo(expected_revision=6)
    assert state() == 'ok'
    store.redo(expected_revision=7)
    assert state() == 'error'


@pytest.mark.parametrize('definition', [False, [], {}])
def test_public_query_does_not_replace_explicit_invalid_definition_with_defaults(table, definition):
    store, ids = table
    before = store.snapshot()
    with pytest.raises(ProjectError, match='view'):
        store.table.query(ids['table'], expected_revision=1, definition=definition)
    assert store.snapshot() == before
