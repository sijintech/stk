"""Real project/bridge/Runtime workflow; the CI solver fixture is explicitly synthetic."""
from pathlib import Path

import pytest

from conftest import finish
from mupro_fake import make_fake_sdk, write_case
from suan.scripting import API
from suan.workflows.muferro import TABLE_ID, FIELD_IDS, RESULT_TABLE_ID
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_desktop_bridge import bridge_env, BridgeCallError  # noqa: F401
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
    assert result['run']['state'] == 'succeeded', scripts.call('script.read', {'session': session})
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
    from suan.workflows.muferro import native_action
    api, p = project
    source = tmp_path / 'case'
    write_case(source)
    expected = p.snapshot()['project']['id']
    other = api.projects.create(tmp_path / 'other', 'Other')
    api._project_handle = other.handle
    with pytest.raises(ValueError, match='selected project changed'):
        native_action(api, 'import', {'source': str(source), 'project_id': expected, 'expected_revision': 0})
    assert revision(p) == revision(other) == 0


@pytest.mark.server
def test_real_muferro_project_workflow(project, scripts, runtime, tmp_path, monkeypatch):
    """Opt-in installed Release solver; never reads or copies its licence files."""
    import os
    import json
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
