"""Real project/bridge/Runtime workflow; the CI solver fixture is explicitly synthetic."""
import json
from pathlib import Path
import os
import stat
import subprocess
from types import SimpleNamespace

import pytest

from conftest import finish
from mupro_fake import make_fake_sdk, write_case
from suan.mupro import muferro_spec
from suan.scripting import API
from suan.workflows.muferro import TABLE_ID, FIELD_IDS, LABEL, RESULT_TABLE_ID, describe_case, native_action
from suan.workflows.native import native_action as desktop_action
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_desktop_bridge import bridge_env, inproc, BridgeCallError  # noqa: F401
from test_desktop_bridge_runtime import add_profile


@pytest.fixture
def project(scripts, tmp_path):
    api = API(scripts.call)
    p = api.projects.create(tmp_path / '项目 project', 'MuFerro workflow')
    api._project_handle = p.handle
    return api, p


def revision(p):
    return p.snapshot()['project']['revision']


def edit(p, row, key, value):
    p.apply([{'op': 'set_cell', 'table_id': TABLE_ID, 'record_id': row,
              'field_id': FIELD_IDS[key], 'value': value}], expected_revision=revision(p))


def test_import_freezes_source_and_runs_in_isolated_python(project, scripts, tmp_path):
    api, p = project
    source = tmp_path / '原始 case'
    write_case(source)
    # Included defaults and material includes must survive freezing and source removal.
    (source / 'base.toml').write_text((source / 'input.toml').read_text())
    (source / 'input.toml').write_text("include = 'base.toml'\n[system]\ntemperature = 315\n")
    session = scripts.call('script.open')['session']
    result = execute(scripts, session,
        f"imported = stk.muferro.import_case({str(source)!r}, expected_revision=0)\nprint(imported)",
        project_handle=p.handle)
    assert result['run']['state'] == 'succeeded', scripts.call('script.read', {'session': session})['text']
    table = next(t for t in p.snapshot()['tables'] if t['id'] == TABLE_ID)
    assert table['records'][0]['values'][FIELD_IDS['temperature']] == 315
    frozen = table['records'][0]['values'][FIELD_IDS['source']]
    (source / 'base.toml').unlink()
    path = p.snapshots.resolve(frozen['snapshot_id'], frozen['bindings']['base.toml'])['path']
    assert 'temperature = 298' in Path(path).read_text()
    assert not p.runs.list()['runs']


@pytest.mark.parametrize('name', ['machine.lic', 'key', 'energy_out.dat', 'Polar.00000000.dat'])
def test_import_refuses_outputs_and_licences_before_reading(project, tmp_path, name):
    api, p = project
    source = tmp_path / 'case'
    write_case(source)
    (source / name).write_text('must not be copied')
    with pytest.raises(ValueError):
        api.muferro.import_case(source, expected_revision=0)
    assert revision(p) == 0
    assert not (tmp_path / '项目 project' / 'inputs').exists()


def test_import_refuses_project_input_junction_before_writing(project, tmp_path, monkeypatch):
    api, p = project
    source = tmp_path / 'case'
    write_case(source)
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'keep.txt'
    sentinel.write_text('synthetic fixture', encoding='utf-8')
    junction = (tmp_path / '项目 project').resolve() / 'inputs' / 'muferro'
    junction.parent.mkdir()
    if os.name == 'nt':
        created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(outside)],
                                 capture_output=True, check=False, timeout=10)
        assert created.returncode == 0, created.stderr
    else:
        junction.symlink_to(outside, target_is_directory=True)
        is_symlink, lstat = Path.is_symlink, Path.lstat

        def junction_stat(path, *args, **kwargs):
            if path == junction:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return lstat(path, *args, **kwargs)

        # Exercise the Windows metadata distinction on hosts without native junctions.
        monkeypatch.setattr(Path, 'is_symlink', lambda path: path != junction and is_symlink(path))
        monkeypatch.setattr(Path, 'lstat', junction_stat)

    try:
        with pytest.raises(ValueError, match='symbolic links or reparse points'):
            api.muferro.import_case(source, expected_revision=0)
        assert list(outside.iterdir()) == [sentinel]
        assert sentinel.read_text(encoding='utf-8') == 'synthetic fixture'
        assert revision(p) == 0 and p.snapshot()['tables'] == []
    finally:
        if os.name == 'nt':
            junction.rmdir()
        else:
            junction.unlink()


def test_prepare_collect_retry_and_reopen(project, scripts, runtime, tmp_path, monkeypatch):
    api, p = project
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    sdk = make_fake_sdk(tmp_path / 'fake-sdk')
    for name in ('STK_MUPRO_ENV_SCRIPTS', 'MUPROROOT', 'STK_MUPRO_ALLOW_LOCAL_MPI', 'SLURM_JOB_ID', 'PBS_JOBID'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MUPRO_SDK_PREFIX', str(sdk))
    source = sdk / 'share/mupro/skills/mupro-muferro/examples'
    row = api.muferro.import_case(source, expected_revision=revision(p))['record_id']
    edit(p, row, 'temperature', 325)
    run = api.muferro.prepare(row, connection, expected_revision=revision(p), launcher='none')
    assert not client.tasks()
    assert run['parameter_state'] == 'current'
    assert api.muferro.prepare(row, connection, expected_revision=revision(p), launcher='none')['id'] == run['id']
    assert len(client.workspaces()) == 1
    with pytest.raises(ValueError, match='successfully finished'):
        api.muferro.collect(run['id'])
    first = p.runs.submit(run['id'])
    task_id = first['status']['task']['id']
    assert p.runs.submit(run['id'])['status']['task']['id'] == task_id
    task = finish(client, supervisor, task_id)
    assert task['state'] == 'succeeded', task
    collected = api.muferro.collect(run['id'])
    assert collected['qoi'] == {'total_energy': -3.375, 'step': 3}
    assert 'temperature = 325' in (Path(collected['directory']) / 'input.toml').read_text()
    assert api.muferro.collect(run['id']) == collected
    assert len(next(t for t in p.snapshot()['tables'] if t['id'] == RESULT_TABLE_ID)['records']) == 1
    assert len(client.tasks()) == 1
    directory = tmp_path / '项目 project'
    p.close()
    p = api.projects.open(directory)
    api._project_handle = p.handle
    assert api.muferro.collect(run['id']) == collected

    case_folder = Path(collected['directory'])
    (case_folder / 'notes.txt').write_text('synthetic notes', encoding='utf-8')
    opened = []
    monkeypatch.setattr(api.viewer, 'open', lambda path, *, preset: opened.append((path, preset)))
    api.muferro.view(run['id'])
    assert opened == [(case_folder, 'muferro-collected-domains')]
    before = revision(p)
    for name, content in (
        ('Polar.00000099.dat', (case_folder / 'Polar.00000000.dat').read_bytes()),
        ('stk-mupro.json', b'{"case_dir":"nested"}'),
        ('run.h5', b'synthetic unregistered container'),
    ):
        extra = case_folder / name
        extra.write_bytes(content)
        with pytest.raises(ValueError, match='unregistered result file'):
            api.muferro.view(run['id'])
        with pytest.raises(ValueError, match='unregistered result file'):
            api.muferro.collect(run['id'])
        assert opened == [(case_folder, 'muferro-collected-domains')] and revision(p) == before
        extra.unlink()
    api.muferro.view(run['id'])
    assert opened == [(case_folder, 'muferro-collected-domains')] * 2

    edit(p, row, 'attempt', 2)
    second = api.muferro.prepare(row, connection, expected_revision=revision(p), launcher='none')
    assert second['id'] != run['id']
    assert p.runs.get(run['id'])['parameter_state'] == 'changed'
    assert len(client.tasks()) == 1
    (Path(collected['directory']) / 'Polar.00000000.dat').write_text('changed')
    with pytest.raises(ValueError, match='changed locally'):
        api.muferro.collect(run['id'])
    with pytest.raises(ValueError, match='changed locally'):
        api.muferro.view(run['id'])
    assert len(client.tasks()) == 1


@pytest.mark.parametrize('changes', [
    pytest.param({'exit_code': 7}, id='solver-exit'),
    pytest.param({'exit_code': False}, id='boolean-exit'),
    pytest.param({'classification': 'solver_failed', 'reason': 'synthetic fixture'}, id='failure-classification'),
    pytest.param({'program': {'sha256': 'synthetic-invalid'}}, id='invalid-program-digest'),
])
def test_collect_rejects_inconsistent_success_report_before_registering_results(
        project, scripts, runtime, tmp_path, monkeypatch, changes):
    api, p = project
    client, supervisor, server, _ = runtime
    connection = add_profile(scripts, runtime)
    sdk = make_fake_sdk(tmp_path / 'synthetic-sdk')
    for name in ('STK_MUPRO_ENV_SCRIPTS', 'MUPROROOT', 'STK_MUPRO_ALLOW_LOCAL_MPI', 'SLURM_JOB_ID', 'PBS_JOBID'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MUPRO_SDK_PREFIX', str(sdk))
    source = sdk / 'share/mupro/skills/mupro-muferro/examples'
    row = api.muferro.import_case(source, expected_revision=revision(p))['record_id']
    run = api.muferro.prepare(row, connection, expected_revision=revision(p), launcher='none')
    task_id = p.runs.submit(run['id'])['status']['task']['id']
    assert finish(client, supervisor, task_id)['state'] == 'succeeded'

    # Publish the synthetic bad report before Runtime first hashes its artifact bytes.
    task_root = server.service.task_dir(task_id)
    assert not (task_root / 'artifacts.json').exists()
    path = task_root / 'work' / 'stk-mupro.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    assert report['exit_code'] == 0 and report['classification'] is None
    assert report['verification']['status'] == 'passed'
    path.write_text(json.dumps({**report, **changes}), encoding='utf-8')
    before = revision(p)
    with pytest.raises(ValueError, match='Collected MuFerro output does not match'):
        api.muferro.collect(run['id'])
    assert revision(p) == before and not any(table['id'] == RESULT_TABLE_ID for table in p.snapshot()['tables'])
    assert [task['id'] for task in client.tasks()] == [task_id]


def test_bad_parameters_and_revision_fail_before_remote_side_effects(project, scripts, runtime, tmp_path):
    api, p = project
    client, _, _, _ = runtime
    connection = add_profile(scripts, runtime)
    source = tmp_path / 'case'
    write_case(source)
    row = api.muferro.import_case(source, expected_revision=0)['record_id']
    with pytest.raises(ValueError, match='Project changed'):
        api.muferro.prepare(row, connection, expected_revision=0)
    edit(p, row, 'dt', -1)
    with pytest.raises(ValueError, match='dt must'):
        api.muferro.prepare(row, connection, expected_revision=revision(p))
    edit(p, row, 'dt', .1)
    with pytest.raises(ValueError, match='at most|exceed'):
        api.muferro.prepare(row, connection, expected_revision=revision(p), ranks=100)
    with pytest.raises(ValueError, match='walltime'):
        api.muferro.prepare(row, connection, expected_revision=revision(p), backend='slurm')
    assert client.workspaces() == [] and client.tasks() == []


def test_lost_prepare_response_recovers_the_same_plan(project, scripts, runtime, tmp_path):
    api, p = project
    client, _, _, _ = runtime
    connection = add_profile(scripts, runtime)
    source = tmp_path / 'case'
    write_case(source)
    row = api.muferro.import_case(source, expected_revision=0)['record_id']
    call = api._call
    lost = False

    def lose_response(operation, params):
        nonlocal lost
        result = call(operation, params)
        if operation == 'project.runs.prepare' and not lost:
            lost = True
            raise ConnectionError('simulated response loss after durable preparation')
        return result

    api._call = lose_response
    with pytest.raises(ConnectionError, match='response loss'):
        api.muferro.prepare(row, connection, expected_revision=revision(p))
    run = api.muferro.prepare(row, connection, expected_revision=revision(p))
    assert len(p.runs.list()['runs']) == 1
    assert run['id'] == p.runs.list()['runs'][0]['id']
    assert len(client.workspaces()) == 1 and client.tasks() == []


def test_edit_during_upload_cannot_freeze_new_row_with_old_inputs(project, scripts, runtime, tmp_path):
    api, p = project
    client, _, _, _ = runtime
    connection = add_profile(scripts, runtime)
    source = tmp_path / 'case'
    write_case(source)
    row = api.muferro.import_case(source, expected_revision=0)['record_id']
    call = api._call
    edited = False

    def concurrent_edit(operation, params):
        nonlocal edited
        result = call(operation, params)
        if operation == 'upload.start' and not edited:
            edited = True
            edit(p, row, 'temperature', 350)
        return result

    api._call = concurrent_edit
    with pytest.raises(BridgeCallError, match='conflict'):
        api.muferro.prepare(row, connection, expected_revision=revision(p))
    assert p.runs.list()['runs'] == [] and client.tasks() == []
    run = api.muferro.prepare(row, connection, expected_revision=revision(p))
    assert run['plan']['parameters']['values'][FIELD_IDS['temperature']] == 350
    assert len(client.workspaces()) == 2  # abandoned preparation is retained; neither task was submitted


def test_native_action_rejects_a_switched_project(project, tmp_path):
    api, p = project
    source = tmp_path / 'case'
    write_case(source)
    expected = p.snapshot()['project']['id']
    other = api.projects.create(tmp_path / 'other', 'Other')
    api._project_handle = other.handle
    with pytest.raises(ValueError, match='selected project changed'):
        native_action(api, 'import', {'source': str(source), 'project_id': expected, 'expected_revision': 0})
    assert revision(p) == revision(other) == 0


@pytest.mark.parametrize('switch_after', [None, 'project.runs.refresh', 'task.logs'],
                         ids=['stable', 'after-refresh', 'between-streams'])
@pytest.mark.parametrize('entry', ['desktop', 'legacy'])
def test_native_logs_check_the_frozen_endpoint_for_each_stream(inproc, tmp_path, monkeypatch, capsys, switch_after,
                                                              entry):
    h = inproc()
    profile, node, task = 'hub:fixture', 'b' * 32, 'c' * 32
    observed = []

    class Backend:
        def __init__(self, name, server_key):
            self.name, self.server_key = name, server_key

        def task(self, task_id):
            assert task_id == task
            return {'task': {'id': task_id, 'state': 'succeeded'}}

        def logs(self, task_id, stream, offset, limit):
            assert task_id == task and offset == 0 and limit == 65536
            observed.append((self.name, stream))
            return {'data': f'{self.name} {stream} fixture'.encode(), 'offset': 0, 'terminal': True}

    active = Backend('original', '1' * 16)
    replacement = Backend('replacement', '2' * 16)

    def backend(connection, selected_node=None):
        assert (connection, selected_node) == (profile, node)
        return active

    def call(operation, params):
        nonlocal active
        response = h.call(operation, params)
        if operation == switch_after:
            active = replacement
        return response

    monkeypatch.setattr(h.bridge.connections, 'backend', backend)
    api = API(call)
    p = api.projects.create(tmp_path / 'fixture-project', 'MuFerro logs')
    api._project_handle = p.handle
    source = tmp_path / 'case'
    write_case(source)
    row = api.muferro.import_case(source, expected_revision=0)['record_id']
    run = p.runs.prepare([{'table_id': TABLE_ID, 'record_id': row, 'label': LABEL + 'Fixture',
                           'spec': muferro_spec('a' * 32, case_dir='case')}],
                         connection=profile, node=node, expected_revision=revision(p))['run_ids'][0]
    h.bridge.projects._stores[p.handle].runs.observe(run, {'task': {'id': task, 'state': 'succeeded'}})
    params = {'project_id': p.snapshot()['project']['id'], 'run_id': run}

    def show_logs():
        if entry == 'desktop':
            return desktop_action(api, 'muferro/1', 'logs', {**params, 'expected_revision': revision(p)})
        return native_action(api, 'logs', params)

    if switch_after is None:
        result = show_logs()
        assert observed == [('original', 'stdout'), ('original', 'stderr')]
        if entry == 'desktop':
            assert result == {'run_id': run, 'streams': {'stdout': 'original stdout fixture',
                                                         'stderr': 'original stderr fixture'}}
        else:
            assert result is None
    else:
        with pytest.raises(BridgeCallError) as error:
            show_logs()
        assert error.value.code == 'conflict'
        assert observed == ([('original', 'stdout')] if switch_after == 'task.logs' else [])
    output = capsys.readouterr().out
    assert ('original stdout fixture' in output) == (switch_after != 'project.runs.refresh')
    assert ('original stderr fixture' in output) == (switch_after is None)
    assert 'replacement' not in output


@pytest.mark.server
def test_real_muferro_project_workflow(project, scripts, runtime, tmp_path, monkeypatch):
    """Opt-in installed Release solver; never reads or copies its licence files."""
    prefix = os.environ.get('STK_TEST_MUPRO_PREFIX')
    if not prefix:
        pytest.skip('Set STK_TEST_MUPRO_PREFIX for the real installed MuFerro workflow')
    import numpy as np
    api, p = project
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    for name in ('STK_MUPRO_ALLOW_LOCAL_MPI', 'SLURM_JOB_ID', 'PBS_JOBID'):
        monkeypatch.delenv(name, raising=False)
    source = Path(prefix) / 'share/mupro/skills/mupro-muferro/examples'
    row = api.muferro.import_case(source, expected_revision=revision(p))['record_id']
    run = api.muferro.prepare(row, connection, expected_revision=revision(p), sdk_prefix=prefix, launcher='none')
    assert client.tasks() == []
    task_id = p.runs.submit(run['id'])['status']['task']['id']
    assert p.runs.submit(run['id'])['status']['task']['id'] == task_id
    task = finish(client, supervisor, task_id, timeout=120)
    assert task['state'] == 'succeeded', task
    result = api.muferro.collect(run['id'])
    folder = Path(result['directory'])
    report = json.loads((folder.parent / 'stk-mupro.json').read_text())
    assert report['layout'] == {'ranks': 1, 'threads_per_rank': 1, 'launcher': 'none'}
    assert report['case'] == {'grid': [16, 16, 16], 'start_step': 0, 'steps': 101, 'output_interval': 100}
    assert len(report['frames']) == 30
    # Independent parser of every numeric field record (the runtime verifier checks headers only).
    for frame in report['frames']:
        data = np.loadtxt(folder.parent / frame['path'], skiprows=1)
        components = frame['components']
        indexed = components > 1 and data.shape == (4096 * components, 5)
        assert indexed or data.shape == (4096, 3 + components)
        assert np.isfinite(data).all()
        assert len(np.unique(data[:, :4] if indexed else data[:, :3], axis=0)) == len(data)
        assert ((data[:, :3] >= 1) & (data[:, :3] <= 16)).all()
        if indexed:
            assert ((data[:, 3] >= 1) & (data[:, 3] <= components)).all()
    assert result['qoi']['step'] == 101 and np.isfinite(result['qoi']['total_energy'])
    if report['program']['sha256'] == 'c0c1f3454f5ff5384c76e70455b0441bb8ebeeb40b711b2360f2f0f1d099683a':
        assert result['qoi']['total_energy'] == pytest.approx(-727.9144455, rel=1e-8)
    directory = folder.parents[3]
    p.close()
    p = api.projects.open(directory)
    api._project_handle = p.handle
    assert api.muferro.collect(run['id']) == result
    edit(p, row, 'temperature', 310)
    newer = api.muferro.prepare(row, connection, expected_revision=revision(p), sdk_prefix=prefix, launcher='none')
    assert newer['id'] != run['id'] and p.runs.get(run['id'])['parameter_state'] == 'changed'
    next_task = p.runs.submit(newer['id'])['status']['task']['id']
    assert finish(client, supervisor, next_task, timeout=120)['state'] == 'succeeded'
    second = api.muferro.collect(newer['id'])
    assert second['qoi']['total_energy'] != result['qoi']['total_energy']
    assert len(client.tasks()) == 2
    evidence = {'directory': str(directory), 'first': result, 'changed_temperature': second,
                'program_sha256': report['program']['sha256'], 'task_ids': [task_id, next_task]}
    (tmp_path / 'real-evidence.json').write_text(json.dumps(evidence, indent=2))
    print('REAL_MUFERRO_EVIDENCE:', tmp_path / 'real-evidence.json', flush=True)


def test_generated_inputs_are_checked_again_after_freezing(project, scripts, runtime, tmp_path):
    api, p = project
    client, _, _, _ = runtime
    connection = add_profile(scripts, runtime)
    source = tmp_path / 'case'
    write_case(source)
    row = api.muferro.import_case(source, expected_revision=0)['record_id']
    call = api._call

    def edit_generated_file(operation, params):
        result = call(operation, params)
        if operation == 'project.files.index':
            path = next(Path(path) for path in params['paths'] if Path(path).name == 'input.toml')
            path.write_text(path.read_text().replace('temperature = 298', 'temperature = 999'))
        return result

    api._call = edit_generated_file
    with pytest.raises(ValueError, match='between generation and freezing'):
        api.muferro.prepare(row, connection, expected_revision=revision(p))
    assert p.runs.list()['runs'] == [] and client.workspaces() == [] and client.tasks() == []


def test_prepare_checks_the_bytes_copied_from_the_frozen_snapshot(project, scripts, runtime, tmp_path):
    api, p = project
    client, _, _, _ = runtime
    connection = add_profile(scripts, runtime)
    source = tmp_path / 'case'
    write_case(source)
    row = api.muferro.import_case(source, expected_revision=0)['record_id']
    call = api._call
    restored = []

    def replace_material_after_resolve(operation, params):
        result = call(operation, params)
        if operation == 'project.snapshots.resolve' and result['name'] == 'material.toml' and not restored:
            path = Path(result['path'])
            data, info = path.read_bytes(), path.stat()
            changed = data.replace(b'-7.3e7', b'-9.3e7')
            assert len(data) == len(changed) and data != changed
            path.chmod(0o600)
            path.write_bytes(changed)
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
            restored.append(path)
        return result

    api._call = replace_material_after_resolve
    before = revision(p)
    with pytest.raises(ValueError, match='Frozen MuFerro input changed'):
        api.muferro.prepare(row, connection, expected_revision=before)
    assert len(restored) == 1 and revision(p) == before
    assert p.runs.list()['runs'] == [] and client.workspaces() == [] and client.tasks() == []


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='Named pipes are tested on POSIX')
def test_prepare_refuses_a_fifo_in_the_existing_prepared_directory(project, scripts, runtime, tmp_path, monkeypatch):
    api, p = project
    client, _, _, _ = runtime
    connection = add_profile(scripts, runtime)
    source = tmp_path / 'case'
    write_case(source)
    row = api.muferro.import_case(source, expected_revision=0)['record_id']
    _, _, label = describe_case(p.snapshot(), row, connection, {})
    fingerprint = label.rsplit(' / ', 1)[1]
    target = tmp_path / '项目 project' / 'inputs' / 'muferro-prepared' / fingerprint / 'input.toml'
    target.parent.mkdir(parents=True)
    os.mkfifo(target)
    original_open = Path.open

    def guard_fifo(path, *args, **kwargs):
        if path == target:
            pytest.fail('Prepare attempted a blocking open on the existing input FIFO')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guard_fifo)
    before = revision(p)
    with pytest.raises(ValueError, match='Prepared input changed locally'):
        api.muferro.prepare(row, connection, expected_revision=before)
    assert revision(p) == before
    assert p.runs.list()['runs'] == [] and client.workspaces() == [] and client.tasks() == []


def test_copy_allows_windows_path_creation_time_but_rejects_descriptor_changes(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    from suan.workflows.muferro import _copy_input
    source = tmp_path / 'input.toml'
    source.write_text('x = 1\n')
    lstat = Path.lstat
    fields = ('st_mode', 'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')

    def creation_time(path, *args, **kwargs):
        info = lstat(path, *args, **kwargs)
        if path == source:
            return SimpleNamespace(**{key: getattr(info, key) - (100 if key == 'st_ctime_ns' else 0) for key in fields})
        return info

    monkeypatch.setattr(Path, 'lstat', creation_time)
    assert _copy_input(source, tmp_path / 'copy.toml', 1024) == source.stat().st_size
    fstat = os.fstat
    calls = 0

    def changed_descriptor(fd):
        nonlocal calls
        calls += 1
        info = fstat(fd)
        return SimpleNamespace(**{key: getattr(info, key) + (calls if key == 'st_ctime_ns' else 0) for key in fields})

    monkeypatch.setattr(os, 'fstat', changed_descriptor)
    with pytest.raises(ValueError, match='changed while importing'):
        _copy_input(source, tmp_path / 'changed.toml', 1024)
