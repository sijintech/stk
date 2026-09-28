"""Read-only proposals reuse the committed edit engine, but never alter its database or files."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
import threading

from click.testing import CliRunner
import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.cli import project
from test_project_values import model, derived, command, reference, legacy  # noqa: F401


def fingerprint(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file()}


def test_preview_preserves_files_history_and_generated_ids_until_explicit_apply(tmp_path):
    store = ProjectStore.create(tmp_path / 'project', 'Preview')
    (store.directory / 'keep.txt').write_text('original', encoding='utf-8')
    before = fingerprint(store.directory)
    commands = [{'op': 'create_table', 'name': '拟议参数'}]
    proposal = store.preview(commands, expected_revision=0)
    assert proposal['persisted'] is False and proposal['base_revision'] == 0 and proposal['proposed_revision'] == 1
    assert 'id' not in commands[0]
    assert fingerprint(store.directory) == before
    assert store.snapshot()['tables'] == [] and store.history() == []
    assert proposal['snapshot']['tables'][0]['id'] == proposal['commands'][0]['id']
    store.apply(proposal['commands'], expected_revision=proposal['base_revision'])
    assert store.snapshot() == proposal['snapshot']
    store.undo(expected_revision=1)
    assert store.snapshot()['tables'] == []


def test_derived_preview_recomputes_only_the_proposal_and_keeps_redo(model):
    store, ids = derived(model)
    store.apply([command(ids, 'temperature', 'set_cell', value=350)], expected_revision=2)
    store.undo(expected_revision=3)
    before, history, files = store.snapshot(), store.history(), fingerprint(store.directory)
    proposal = store.preview([command(ids, 'temperature', 'set_cell', value=400)], expected_revision=4)
    row = proposal['snapshot']['tables'][1]['records'][0]
    assert row['values'][ids['derived']] == 410
    assert proposal['snapshot']['edit_history']['redo_revision'] is None
    assert store.snapshot() == before and store.history() == history
    assert fingerprint(store.directory) == files
    assert before['edit_history']['redo_revision'] == 3
    store.apply(proposal['commands'], expected_revision=4)
    assert store.snapshot() == proposal['snapshot']


def test_formula_errors_are_visible_and_do_not_become_persisted_errors(model):
    store, ids = derived(model)
    proposal = store.preview([command(ids, 'temperature', 'set_reference', source=reference(ids, 'copy'))], expected_revision=2)
    results = [result for table in proposal['snapshot']['tables'] for row in table['records']
               for result in row.get('evaluations', {}).values()]
    assert any(result['state'] == 'error' and result['error']['code'] == 'cycle' for result in results)
    assert all(result['state'] == 'ok' for table in store.snapshot()['tables'] for row in table['records']
               for result in row.get('evaluations', {}).values())
    assert store.info()['revision'] == 2


@pytest.mark.parametrize('commands', [[], [{'op': 'task.submit'}], [{'op': 'create_table', 'name': 'partial'}, {'op': 'bad'}],
                                      [{'op': 'create_table', 'name': 'x'}] * 1001])
def test_rejected_preview_has_no_partial_edit(tmp_path, commands):
    store = ProjectStore.create(tmp_path / 'project', 'Preview')
    before = fingerprint(store.directory)
    with pytest.raises(ProjectError):
        store.preview(commands, expected_revision=0)
    assert fingerprint(store.directory) == before
    assert store.history() == []


def test_preview_old_format_does_not_upgrade_and_rejects_its_unsupported_operations(model):
    store, ids = model
    legacy(store)
    before = fingerprint(store.directory)
    proposal = store.preview([command(ids, 'temperature', 'set_cell', value=325)], expected_revision=1)
    assert proposal['snapshot']['format_version'] == 1
    with pytest.raises(ProjectError, match='format 2'):
        store.preview([command(ids, 'copy', 'set_reference', source=reference(ids, 'temperature'))], expected_revision=1)
    assert fingerprint(store.directory) == before
    assert store.info()['format_version'] == 1


def test_preview_budget_and_stale_revision_do_not_copy_or_modify(tmp_path, monkeypatch):
    store = ProjectStore.create(tmp_path / 'project', 'Preview')
    before = fingerprint(store.directory)
    with pytest.raises(RevisionConflict):
        store.preview([{'op': 'create_table', 'name': 'stale'}], expected_revision=1)
    monkeypatch.setattr('suan.project.store.MAX_PREVIEW_BYTES', 1)
    with pytest.raises(ProjectError, match='preview copy limit'):
        store.preview([{'op': 'create_table', 'name': 'too big'}], expected_revision=0)
    assert fingerprint(store.directory) == before


def test_source_writer_can_advance_during_preview_and_later_apply_conflicts(tmp_path, monkeypatch):
    store = ProjectStore.create(tmp_path / 'project', 'Preview')
    original = store._apply
    entered, release = threading.Event(), threading.Event()
    def blocked(db, commands, revision):
        entered.set()
        assert release.wait(10)
        return original(db, commands, revision)
    monkeypatch.setattr(store, '_apply', blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.preview, [{'op': 'create_table', 'name': 'proposal'}], expected_revision=0)
        try:
            assert entered.wait(5)
            other = ProjectStore(store.directory)
            other.apply([{'op': 'create_table', 'name': 'another editor'}], expected_revision=0)
        finally:
            release.set()
        proposal = future.result(timeout=5)
    assert proposal['snapshot']['tables'][0]['name'] == 'proposal'
    assert store.snapshot()['tables'][0]['name'] == 'another editor'
    with pytest.raises(RevisionConflict):
        store.apply(proposal['commands'], expected_revision=proposal['base_revision'])


def test_preview_reads_committed_wal_state_and_cli_does_not_apply(tmp_path):
    store = ProjectStore.create(tmp_path / 'project', 'Preview')
    with sqlite3.connect(store.path) as keeper:
        assert keeper.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        store.apply([{'op': 'create_table', 'name': 'committed'}], expected_revision=0)
        proposed = store.preview([{'op': 'create_table', 'name': 'preview'}], expected_revision=1)
        assert [table['name'] for table in proposed['snapshot']['tables']] == ['committed', 'preview']
        assert len(store.snapshot()['tables']) == 1
    result = CliRunner().invoke(project, ['preview', str(store.directory), '--commands', '-', '--expected-revision', '1'],
                                input=json.dumps([{'op': 'create_table', 'name': 'CLI preview'}]))
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value['persisted'] is False
    assert store.info()['revision'] == 1


def test_preview_accepts_read_only_source_and_rejects_a_replaced_identity(tmp_path):
    store = ProjectStore.create(tmp_path / 'project', 'Original')
    before = store.path.read_bytes()
    store.path.chmod(0o400)
    try:
        proposal = store.preview([{'op': 'create_table', 'name': 'read only'}], expected_revision=0)
        assert proposal['persisted'] is False and store.path.read_bytes() == before
    finally:
        store.path.chmod(0o600)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project SET id='11111111-1111-4111-8111-111111111111'")
    with pytest.raises(ProjectError, match='replaced'):
        store.preview([{'op': 'create_table', 'name': 'wrong project'}], expected_revision=0)
