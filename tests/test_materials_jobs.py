"""Durability, concurrency and admission contracts, independent of torch availability."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import pytest

from suan.materials import datasets, inputs, jobs, service, training


@pytest.fixture
def data(tmp_path):
    root = tmp_path.resolve()
    datasets.write_synthetic(root / 'data', 'capacity_fade', 30, seed=2)
    return root / 'data'


@pytest.fixture
def local(data, monkeypatch):
    monkeypatch.setattr(training, 'torch_module', lambda: None)
    return service.MaterialsService(data.parent / 'state')


def wait(local, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = local.job(job_id)
        if job['state'] != 'running':
            # A terminal state can become visible immediately before lease cleanup.
            while local._workers and time.monotonic() < deadline:
                time.sleep(.005)
            return job
        time.sleep(.005)
    raise AssertionError('trainer did not finish')


def fake_trainer(monkeypatch, *, score=.05, baseline=.06, before=None):
    def train(directory, output, *, frozen, progress, cancel):
        assert frozen is True
        manifest, description, samples = inputs.load(directory)
        if before:
            before(cancel)
        for epoch in range(1, 4):
            if cancel.is_set():
                raise training.Cancelled('cancelled')
            progress(epoch, 1 / epoch, 2 / epoch)
        metric = {'normalized_rmse': score, 'rmse': score, 'mae': score}
        meta = {'format': 'stk.curve-model/1', 'kind': manifest['kind'],
                'inputs': description['inputs'], 'grid': description['target']['grid'],
                'created_at': '2026-10-29T00:00:00+00:00', 'dataset': {
                    'name': 'synthetic test', 'synthetic': True, 'sha256': manifest['dataset']['sha256'],
                    'license': 'test', 'sensitivity': 'private', 'samples': len(samples)},
                'metrics': {'train': metric, 'test': metric},
                'comparison': {'format': 'stk.materials-training-comparison/1',
                    'test_sha256': training._digest(manifest['split']['test']),
                    'test_samples': len(manifest['split']['test']), 'candidate': metric, 'base': None,
                    'baseline': dict(metric, normalized_rmse=baseline) if manifest['baseline_model'] else None},
                'training_input': {'capsule_sha256': manifest['sha256'],
                    'split_sha256': training._digest(manifest['split']),
                    'split_counts': {k: len(v) for k, v in manifest['split'].items()},
                    'base_model': manifest['base_model'], 'baseline_model': manifest['baseline_model']},
                'weights_sha256': hashlib.sha256(b'ordinary test weights').hexdigest()}
        output = Path(output)
        output.mkdir()
        (output / 'model.pt').write_bytes(b'ordinary test weights')
        (output / 'model.json').write_text(json.dumps(meta, allow_nan=False), encoding='utf-8')
        return meta
    monkeypatch.setattr(training, 'train', train)
    return train


def test_reading_an_unused_service_creates_nothing(tmp_path):
    path = tmp_path / 'state'
    local = service.MaterialsService(path)
    assert local.jobs()['jobs'] == []
    assert local.models()['kinds']['capacity_fade']['active'] is None
    for call in (local.job, local.job_curves, local.recover, local.cancel, local.start):
        with pytest.raises(service.MaterialsNotFound):
            call('absent')
    assert not path.exists()


def test_prepare_freezes_without_torch_and_reopens_without_training(data, local, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('read/preparation executed training')
    monkeypatch.setattr(training, 'torch_module', forbidden)
    monkeypatch.setattr(training, 'train', forbidden)
    first = local.prepare(data, 'frozen', options={'epochs': 5})
    assert first['state'] == 'prepared' and first['started_at'] is None
    assert first['split_counts'] == {'train': 21, 'validation': 4, 'test': 5}
    assert not {'request', 'owner', 'admission', 'baseline_generation'} & first.keys()
    shutil.rmtree(data)
    reopened = service.MaterialsService(local.root)
    assert reopened.job('frozen') == first
    assert reopened.prepare(data, 'frozen', options={'epochs': 5}) == first
    assert reopened.jobs()['jobs'] == [first]
    assert reopened.job_curves('frozen')['curves'] == []
    assert reopened.recover('frozen') == first
    with pytest.raises(service.MaterialsError, match='different frozen'):
        reopened.prepare(data, 'frozen', options={'epochs': 6})
    assert inputs.verify(local.root / 'jobs/frozen/inputs')['sha256'] == first['input_sha256']


def test_frozen_training_history_curves_and_registration_survive_reopen(data, local, monkeypatch):
    fake_trainer(monkeypatch)
    local.prepare(data, 'frozen')
    shutil.rmtree(data)
    local.start('frozen')
    done = wait(local, 'frozen')
    assert done['state'] == 'done' and done['version'] == 'v1'
    reopened = service.MaterialsService(local.root)
    assert reopened.job('frozen') == done
    assert reopened.start('frozen') == done
    page = reopened.job_curves('frozen', limit=2)
    assert [x['epoch'] for x in page['curves']] == [1, 2] and page['next_after'] == 2
    tail = reopened.job_curves('frozen', after=2)
    assert [x['epoch'] for x in tail['curves']] == [3] and tail['next_after'] is None
    registered = reopened.models('capacity_fade')['kinds']['capacity_fade']
    assert registered['active'] == 'v1'
    assert registered['versions'][0]['input_sha256'] == done['input_sha256']


def test_baseline_regression_is_rejected_even_below_absolute_gate(data, local, monkeypatch):
    fake_trainer(monkeypatch)
    local.train(data, 'first')
    assert wait(local, 'first')['version'] == 'v1'
    fake_trainer(monkeypatch, score=.08, baseline=.04)
    local.train(data, 'worse')
    result = wait(local, 'worse')
    assert result['state'] == 'rejected' and result['reason'] == 'baseline_regression'
    assert result['metrics']['test']['normalized_rmse'] < result['gate']
    assert local.models('capacity_fade')['kinds']['capacity_fade']['active'] == 'v1'
    assert local.job_curves('worse')['recorded_epochs'] == 3


def test_base_version_can_be_older_than_active_comparison_model(data, local, monkeypatch):
    fake_trainer(monkeypatch)
    for name in ('first', 'second'):
        local.train(data, name)
        assert wait(local, name)['state'] == 'done'
    task = local.prepare(data, 'transfer', base_version='v1')
    assert task['base_version'] == 'v1' and task['baseline_version'] == 'v2'
    manifest = inputs.verify(local.root / 'jobs/transfer/inputs')
    for role, version in (('base', 'v1'), ('baseline', 'v2')):
        expected = (local.root / 'models/capacity_fade' / version / 'model.json').read_bytes()
        assert manifest[role + '_model']['model_sha256'] == hashlib.sha256(expected).hexdigest()


def test_manual_activation_even_of_same_version_invalidates_prepared_admission(data, local, monkeypatch):
    fake_trainer(monkeypatch)
    local.train(data, 'first')
    assert wait(local, 'first')['state'] == 'done'
    local.prepare(data, 'prepared')
    local.activate('capacity_fade', 'v1')
    local.start('prepared')
    result = wait(local, 'prepared')
    assert result['state'] == 'rejected' and result['reason'] == 'active_model_changed'
    assert len(local.models('capacity_fade')['kinds']['capacity_fade']['versions']) == 1


@pytest.mark.parametrize('score', [None, float('nan'), float('inf'), -.01, .2])
def test_invalid_or_over_gate_score_never_activates(data, local, monkeypatch, score):
    # Nonfinite values fail JSON serialization in this fake producer, just as in
    # the real trainer; finite invalid/over-gate scores exercise admission.
    fake_trainer(monkeypatch, score=score)
    local.train(data, 'bad')
    result = wait(local, 'bad')
    assert result['state'] in ('rejected', 'failed') and result['version'] is None
    assert local.models('capacity_fade')['kinds']['capacity_fade']['versions'] == []


def test_another_service_cancels_running_task_and_cannot_recover_or_train(data, local, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def blocked(cancel):
        started.set()
        assert release.wait(5)
    fake_trainer(monkeypatch, before=blocked)
    local.train(data, 'running')
    assert started.wait(5)
    another = service.MaterialsService(local.root)
    another.prepare(data, 'next')
    for call, argument in ((another.start, 'next'), (another.recover, 'running')):
        with pytest.raises(service.MaterialsBusy):
            call(argument)
    assert another.cancel('running')['cancel_requested']
    release.set()
    assert wait(local, 'running')['state'] == 'cancelled'
    assert another.job('running')['state'] == 'cancelled'
    assert another.models('capacity_fade')['kinds']['capacity_fade']['active'] is None
    assert another.cancel('next')['state'] == 'cancelled'
    assert another.start('next')['state'] == 'cancelled'


def test_explicit_recovery_marks_abandoned_claim_without_restarting(data, local, monkeypatch):
    local.prepare(data, 'stopped')
    local._store.update('stopped', {'state': 'running', 'started_at': 'old claim'})
    monkeypatch.setattr(training, 'train', lambda *a, **k: pytest.fail('recovery retrained'))
    reopened = service.MaterialsService(local.root)
    assert reopened.job('stopped')['state'] == 'running'
    assert reopened.recover('stopped')['state'] == 'interrupted'
    assert reopened.start('stopped')['state'] == 'interrupted'


@pytest.mark.parametrize('point', ['before_registry', 'after_registry'])
def test_publication_crash_receipt_is_recovered_without_republishing(data, local, monkeypatch, point):
    fake_trainer(monkeypatch)
    original = local._save
    def fail(registry):
        if point == 'after_registry':
            original(registry)
        raise OSError('injected process interruption')
    monkeypatch.setattr(local, '_save', fail)
    local.train(data, 'crash')
    assert wait(local, 'crash')['state'] == 'uncertain'
    folder = local.root / 'models/capacity_fade/v1'
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    reopened = service.MaterialsService(local.root)
    result = reopened.recover('crash')
    assert result['state'] == ('done' if point == 'after_registry' else 'interrupted')
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    active = reopened.models('capacity_fade')['kinds']['capacity_fade']['active']
    assert active == ('v1' if point == 'after_registry' else None)
    # Even an orphan model number is never reused.
    reopened.train(data, 'next')
    assert wait(reopened, 'next')['version'] == 'v2'


def test_recovery_never_reactivates_a_model_after_user_rollback(data, local, monkeypatch):
    fake_trainer(monkeypatch)
    local.train(data, 'first')
    assert wait(local, 'first')['version'] == 'v1'
    original = local._save
    def published_then_lost(registry):
        original(registry)
        raise OSError('lost completion')
    monkeypatch.setattr(local, '_save', published_then_lost)
    local.train(data, 'second')
    assert wait(local, 'second')['state'] == 'uncertain'
    another = service.MaterialsService(local.root)
    another.activate('capacity_fade', 'v1')
    assert another.recover('second')['state'] == 'done'
    assert another.models('capacity_fade')['kinds']['capacity_fade']['active'] == 'v1'


def test_recovery_detects_admitted_weights_corruption(data, local, monkeypatch):
    fake_trainer(monkeypatch)
    original = local._save
    def published(registry):
        original(registry)
        raise OSError('lost completion')
    monkeypatch.setattr(local, '_save', published)
    local.train(data, 'crash')
    assert wait(local, 'crash')['state'] == 'uncertain'
    (local.root / 'models/capacity_fade/v1/model.pt').write_bytes(b'changed test weights')
    assert service.MaterialsService(local.root).recover('crash')['state'] == 'uncertain'


def test_lease_serializes_processes_and_close_is_idempotent(tmp_path):
    path = tmp_path.resolve() / 'lease'
    with jobs.Lease(path):
        code = ('import sys\nfrom suan.materials.jobs import Lease,Locked\n'
                'try:\n Lease(sys.argv[1])\nexcept Locked:\n sys.exit(7)\n')
        result = subprocess.run([sys.executable, '-c', code, str(path)], check=False, timeout=10)
        assert result.returncode == 7
    old = jobs.Lease(path)
    old.close()
    with jobs.Lease(path):
        old.close()
        with pytest.raises(jobs.Locked):
            jobs.Lease(path)
    assert path.is_file()


@pytest.mark.parametrize('job_id', ['../escape', '', 'a/b', 'x'*65])
def test_invalid_job_ids_never_write_state(local, data, job_id):
    with pytest.raises(service.MaterialsError):
        local.prepare(data, job_id)
    assert not local.root.exists()


def test_shutting_down_cancels_and_refuses_new_training(data, local, monkeypatch):
    local.prepare(data, 'prepared')
    local.shutdown()
    with pytest.raises(service.MaterialsUnavailable):
        local.start('prepared')
    with pytest.raises(service.MaterialsUnavailable):
        local.prepare(data, 'new')
    assert local.job('prepared')['state'] == 'prepared'


def test_frozen_input_tamper_is_not_trained(data, local, monkeypatch):
    local.prepare(data, 'tampered')
    (local.root / 'jobs/tampered/inputs/samples.jsonl').write_text('{}\n')
    monkeypatch.setattr(training, 'train', lambda *a, **k: pytest.fail('tampered input trained'))
    with pytest.raises(inputs.InputsError):
        local.start('tampered')
    assert local.job('tampered')['state'] == 'prepared'


@pytest.mark.parametrize('missing', ['model.json', 'model.pt', 'input'])
def test_recovery_persists_uncertain_if_published_evidence_disappears(data, local, monkeypatch, missing):
    fake_trainer(monkeypatch)
    original = local._save
    def published(registry):
        original(registry)
        raise OSError('lost completion')
    monkeypatch.setattr(local, '_save', published)
    local.train(data, 'crash')
    assert wait(local, 'crash')['state'] == 'uncertain'
    # Model an abrupt process death before even recording uncertainty.
    local._store.update('crash', {'state': 'running'})
    if missing == 'input':
        (local.root / 'jobs/crash/inputs/manifest.json').unlink()
    else:
        (local.root / 'models/capacity_fade/v1' / missing).unlink()
    reopened = service.MaterialsService(local.root)
    observed = reopened.recover('crash')
    assert observed['state'] == 'uncertain' and observed['reason'] == 'admitted_evidence_unavailable'
    assert not {'admission', 'request', 'owner', 'baseline_generation'} & observed.keys()
    assert reopened.job('crash')['state'] == 'uncertain'
    assert reopened.models('capacity_fade')['kinds']['capacity_fade']['active'] == 'v1'


@pytest.mark.parametrize('change', ['test_sha256', 'test_samples', 'role', 'split'])
def test_output_must_bind_the_exact_heldout_set_and_frozen_roles(data, local, monkeypatch, change):
    original = fake_trainer(monkeypatch)
    def unbound(*args, **kwargs):
        meta = original(*args, **kwargs)
        if change == 'test_sha256':
            meta['comparison']['test_sha256'] = '0' * 64
        elif change == 'test_samples':
            meta['comparison']['test_samples'] += 1
        elif change == 'role':
            meta['training_input']['baseline_model'] = {'weights_sha256': '0' * 64}
        else:
            meta['training_input']['split_sha256'] = '0' * 64
        return meta
    monkeypatch.setattr(training, 'train', unbound)
    local.train(data, 'unbound')
    assert wait(local, 'unbound')['state'] == 'failed'
    assert local.models('capacity_fade')['kinds']['capacity_fade']['active'] is None


@pytest.mark.parametrize('name', ['model.json', 'model.pt'])
def test_changed_trained_artifact_never_activates(data, local, monkeypatch, name):
    original = fake_trainer(monkeypatch)
    def changed(directory, output, **kwargs):
        meta = original(directory, output, **kwargs)
        (Path(output) / name).write_bytes(b'changed artifact')
        return meta
    monkeypatch.setattr(training, 'train', changed)
    local.train(data, 'changed')
    assert wait(local, 'changed')['state'] in ('failed', 'uncertain')
    assert local.models('capacity_fade')['kinds']['capacity_fade']['active'] is None


def test_broken_state_symlink_is_reported_as_unavailable(tmp_path):
    state = tmp_path.resolve() / 'state'
    state.mkdir()
    path = state / 'training.sqlite3'
    try:
        path.symlink_to(state / 'missing')
    except OSError:
        pytest.skip('host cannot create test symlinks')
    with pytest.raises(service.MaterialsUnavailable):
        service.MaterialsService(state).jobs()
    assert path.is_symlink()


def test_registry_readers_share_the_publication_lease(data, local, monkeypatch):
    fake_trainer(monkeypatch)
    local.train(data, 'first')
    assert wait(local, 'first')['state'] == 'done'
    another = service.MaterialsService(local.root)
    with local._registry_read() as registry:
        assert registry['kinds']['capacity_fade']['active'] == 'v1'
        with pytest.raises(service.MaterialsBusy):
            another.activate('capacity_fade', 'v1')
    assert another.activate('capacity_fade', 'v1')['active'] == 'v1'


@pytest.mark.parametrize('budget', ['bytes', 'versions'])
def test_registry_publication_never_exceeds_its_own_read_budget(local, budget):
    original = {'kinds': {}}
    local._save(original)
    before = (local.root / 'registry.json').read_bytes()
    if budget == 'bytes':
        oversized = {'kinds': {}, 'padding': 'x' * service.MAX_REGISTRY_BYTES}
    else:
        oversized = {'kinds': {'capacity_fade': {'active': None,
            'versions': [{'version': f'v{i}'} for i in range(1, 10002)]}}}
    with pytest.raises(service.MaterialsUnavailable, match='budget'):
        local._save(oversized)
    assert (local.root / 'registry.json').read_bytes() == before
    assert local._registry() == original
