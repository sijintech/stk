"""Batch intent/recovery tests use the real project bridge and isolated Linux Runtime."""
import pytest

from conftest import finish
from mupro_fake import make_fake_sdk, write_case
from suan.workflows.batches import TABLE_ID as BATCH_TABLE, FIELD_IDS as BATCH_FIELDS
from suan.workflows.muferro import TABLE_ID, FIELD_IDS, RESULT_TABLE_ID, native_action
from test_workflow_muferro import project, scripts, bridge_env, revision, edit  # noqa: F401
from test_desktop_bridge_runtime import add_profile


def rows(api, p, source, count=3):
    first = api.muferro.import_case(source, expected_revision=revision(p))["record_id"]
    result = [first]
    for i in range(1, count):
        row = api.muferro.clone_case(first, expected_revision=revision(p))["record_id"]
        edit(p, row, "temperature", 298 + i * 10)
        result.append(row)
    return result


@pytest.fixture
def batch_runtime(project, scripts, runtime, tmp_path, monkeypatch):
    api, p = project
    sdk = make_fake_sdk(tmp_path / "sdk")
    for key in ("STK_MUPRO_ENV_SCRIPTS", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID", "PBS_JOBID"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(sdk))
    connection = add_profile(scripts, runtime)
    members = rows(api, p, sdk / "share/mupro/skills/mupro-muferro/examples")
    return api, p, runtime[0], runtime[1], connection, members


def create(api, p, members, connection):
    return api.batches.create("muferro/1", members, connection, expected_revision=revision(p), options={"launcher": "none"})["id"]


def operate(api, p, batch, operation, **kwargs):
    return api.batches.execute(batch, operation, expected_revision=revision(p), **kwargs)


def test_batch_intent_is_idempotent_order_independent_and_offline(project, tmp_path):
    api, p = project
    source = tmp_path / "source"
    write_case(source)
    members = rows(api, p, source)
    batch = create(api, p, members, "runtime:offline")
    before = revision(p)
    assert create(api, p, list(reversed(members)), "runtime:offline") == batch
    assert revision(p) == before
    assert {i['record_id'] for i in api.batches.inspect(batch)['items']} == set(members)
    assert {i['state'] for i in api.batches.inspect(batch)['items']} == {'unprepared'}
    assert p.runs.list()['runs'] == []
    directory = tmp_path / '项目 project'
    p.close()
    p = api.projects.open(directory)
    api._project_handle = p.handle
    assert api.batches.inspect(batch)['id'] == batch
    assert len(api.batches.templates()) == 1
    with pytest.raises(ValueError, match='template'):
        api.batches.create('untrusted.module:run', members, 'runtime:offline', expected_revision=revision(p))
    with pytest.raises(ValueError, match='distinct'):
        create(api, p, [members[0], members[0]], 'runtime:offline')
    with pytest.raises(ValueError, match='options'):
        api.batches.create('muferro/1', members, 'runtime:offline', options=[], expected_revision=revision(p))
    with pytest.raises(ValueError, match='Runtime profile'):
        create(api, p, members, 'http://unsaved-host')
    intent = next(t for t in p.snapshot()['tables'] if t['id'] == BATCH_TABLE)['records'][0]['values'][BATCH_FIELDS['intent']]
    intent['entries'].pop()
    p.apply([{'op':'set_cell','table_id':BATCH_TABLE,'record_id':batch,'field_id':BATCH_FIELDS['intent'],'value':intent}], expected_revision=revision(p))
    with pytest.raises(ValueError, match='intent changed'):
        api.batches.inspect(batch)


@pytest.mark.server
def test_batch_partial_preparation_reopen_submit_cancel_retry_and_collect(batch_runtime, tmp_path):
    api, p, client, supervisor, connection, members = batch_runtime
    batch = create(api, p, members, connection)
    # The frozen batch does not silently adopt a later table edit.
    edit(p, members[1], 'temperature', 999)
    result = operate(api, p, batch, 'prepare')
    assert not result['ok'] and sum(i['ok'] for i in result['items']) == 2
    assert not client.tasks()
    assert len(p.runs.list()['runs']) == 2
    edit(p, members[1], 'temperature', 308)
    assert operate(api, p, batch, 'prepare', record_ids=[members[1]])['ok']
    assert operate(api, p, batch, 'prepare')['ok']
    assert len(p.runs.list()['runs']) == len(client.workspaces()) == 3
    directory = tmp_path / '项目 project'
    p.close()
    p = api.projects.open(directory)
    api._project_handle = p.handle
    assert operate(api, p, batch, 'submit')['ok']
    assert operate(api, p, batch, 'submit')['ok']
    assert len(client.tasks()) == 3
    assert operate(api, p, batch, 'cancel', record_ids=[members[0]])['ok']
    for item in api.batches.inspect(batch)['items']:
        if item['record_id'] != members[0]:
            assert finish(client, supervisor, item['task_id'])['state'] == 'succeeded'
    assert operate(api, p, batch, 'refresh')['ok']
    result = operate(api, p, batch, 'collect')
    assert not result['ok'] and sum(i['ok'] for i in result['items']) == 2
    states = {i['record_id']:i for i in api.batches.inspect(batch)['items']}
    assert states[members[0]]['state'] == 'cancelled'
    assert states[members[0]]['last_operation']['error']
    # Explicit independent retry: only the cancelled row, with a new Attempt; never auto-submit.
    edit(p, members[0], 'attempt', 2)
    retry = create(api, p, [members[0]], connection)
    assert retry != batch and operate(api, p, retry, 'prepare')['ok']
    assert len(client.tasks()) == 3
    assert operate(api, p, retry, 'submit')['ok']
    item = api.batches.inspect(retry)['items'][0]
    assert finish(client, supervisor, item['task_id'])['state'] == 'succeeded'
    assert operate(api, p, retry, 'collect')['ok']
    assert len(client.tasks()) == 4
    assert len(next(t for t in p.snapshot()['tables'] if t['id'] == RESULT_TABLE_ID)['records']) == 3
    assert api.batches.inspect(batch)['items'] != api.batches.inspect(retry)['items']


@pytest.mark.server
def test_lost_prepare_and_submit_responses_resume_without_duplicate_tasks(batch_runtime):
    api, p, client, supervisor, connection, members = batch_runtime
    batch = create(api, p, members, connection)
    original, lost = api._call, set()
    def call(operation, params):
        result = original(operation, params)
        if operation in {'project.runs.prepare', 'project.runs.submit'} and operation not in lost:
            lost.add(operation)
            raise ConnectionError('response lost after durable write')
        return result
    api._call = call
    assert not operate(api, p, batch, 'prepare')['ok']
    assert len(p.runs.list()['runs']) == 3
    assert operate(api, p, batch, 'prepare')['ok']
    assert not operate(api, p, batch, 'submit')['ok']
    assert len(client.tasks()) == 3
    assert operate(api, p, batch, 'submit')['ok']
    assert len(client.tasks()) == 3
    for task in client.tasks():
        assert finish(client, supervisor, task['id'])['state'] == 'succeeded'


@pytest.mark.server
def test_stale_clicks_and_interruption_do_not_expand_or_replay_batch(batch_runtime):
    api, p, client, _, connection, members = batch_runtime
    batch = create(api, p, members, connection)
    old_revision = revision(p)
    edit(p, members[0], 'temperature', 400)
    with pytest.raises(ValueError, match='Project changed'):
        api.batches.execute(batch, 'prepare', expected_revision=old_revision)
    with pytest.raises(ValueError, match='not part'):
        operate(api, p, batch, 'submit', record_ids=['missing'])
    assert not client.tasks() and not client.workspaces()
    edit(p, members[0], 'temperature', 298)
    original = api._call
    def interrupt(operation, params):
        result = original(operation, params)
        if operation == 'project.runs.prepare':
            raise KeyboardInterrupt()
        return result
    api._call = interrupt
    with pytest.raises(KeyboardInterrupt):
        operate(api, p, batch, 'prepare')
    assert len(p.runs.list()['runs']) == 1 and not client.tasks()
    api._call = original
    assert operate(api, p, batch, 'prepare')['ok']
    assert len(p.runs.list()['runs']) == len(client.workspaces()) == 3


@pytest.mark.server
def test_lost_progress_write_stops_and_resumes_the_same_plans(batch_runtime):
    api, p, client, _, connection, members = batch_runtime
    batch = create(api, p, members, connection)
    original, lost = api._call, False
    def call(operation, params):
        nonlocal lost
        result = original(operation, params)
        if operation == 'project.apply' and not lost and any(c.get('field_id') == BATCH_FIELDS['outcomes'] for c in params['commands']):
            lost = True
            raise ConnectionError('progress write response lost')
        return result
    api._call = call
    with pytest.raises(ConnectionError, match='progress write'):
        operate(api, p, batch, 'prepare')
    assert len(p.runs.list()['runs']) == 1 and not client.tasks()
    assert operate(api, p, batch, 'prepare')['ok']
    assert len(p.runs.list()['runs']) == len(client.workspaces()) == 3


@pytest.mark.server
def test_copied_batch_label_cannot_authorize_a_different_command(batch_runtime):
    api, p, client, _, connection, members = batch_runtime
    batch = create(api, p, members, connection)
    entry = api.batches.inspect(batch)['items'][0]
    workspace = client.create_workspace('different-command')['id']
    p.runs.prepare([{'table_id':TABLE_ID, 'record_id':entry['record_id'], 'label':entry['label'],
                     'spec':{'workspace_id':workspace,'argv':['{python}','-c','print(123)']}}],
                   connection=connection, expected_revision=revision(p))
    result = operate(api, p, batch, 'submit', record_ids=[entry['record_id']])
    assert not result['ok'] and 'command' in result['items'][0]['error']
    assert not client.tasks()


def test_batch_native_action_pins_project(project, tmp_path):
    api, p = project
    identity = p.snapshot()['project']['id']
    other = api.projects.create(tmp_path/'other', 'Other')
    api._project_handle = other.handle
    with pytest.raises(ValueError, match='selected project changed'):
        native_action(api, 'batch_submit', {'project_id':identity,'batch_id':'unused','expected_revision':0})


@pytest.mark.server
def test_real_muferro_temperature_batch(project, scripts, runtime, monkeypatch, tmp_path):
    """Opt-in scientific acceptance using the installed solver and its existing licence."""
    import os
    import json
    from pathlib import Path
    prefix = os.environ.get('STK_TEST_MUPRO_PREFIX')
    if not prefix:
        pytest.skip('Set STK_TEST_MUPRO_PREFIX to test the real MuFerro batch')
    monkeypatch.setenv('MUPRO_SDK_PREFIX', prefix)
    for key in ('STK_MUPRO_ALLOW_LOCAL_MPI', 'SLURM_JOB_ID', 'PBS_JOBID'):
        monkeypatch.delenv(key, raising=False)
    api, p = project
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    members = rows(api, p, Path(prefix)/'share/mupro/skills/mupro-muferro/examples', count=2)
    edit(p, members[1], 'temperature', 310)
    batch = create(api, p, members, connection)
    assert operate(api, p, batch, 'prepare')['ok']
    assert not client.tasks()
    assert operate(api, p, batch, 'submit')['ok']
    assert operate(api, p, batch, 'submit')['ok']
    assert len(client.tasks()) == 2
    for task in client.tasks():
        assert finish(client, supervisor, task['id'], timeout=120)['state'] == 'succeeded'
    assert operate(api, p, batch, 'collect')['ok']
    assert operate(api, p, batch, 'collect')['ok']
    from suan.workflows.muferro import RESULT_FIELD_IDS
    result = next(t for t in p.snapshot()['tables'] if t['id'] == RESULT_TABLE_ID)
    assert len(result['records']) == 2
    energies = {row['values'][RESULT_FIELD_IDS['temperature']]:row['values'][RESULT_FIELD_IDS['energy']] for row in result['records']}
    assert energies[298] == pytest.approx(-727.9144455, rel=1e-8)
    assert energies[310] == pytest.approx(-691.5580935, rel=1e-8)
    evidence = {'project':str(tmp_path/'项目 project'),'batch':api.batches.inspect(batch),'energies':energies}
    (tmp_path/'batch-evidence.json').write_text(json.dumps(evidence, indent=2))
    print('REAL_BATCH_EVIDENCE:', tmp_path/'batch-evidence.json')
