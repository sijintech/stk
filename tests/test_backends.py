from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import json
import os
import subprocess
import time

import pytest

from conftest import finish
from suan.runtime.backends import PBSBackend, SlurmBackend, SubmissionUnknown
from suan.runtime.models import TaskSpec


@pytest.mark.parametrize('kind', ['pbs', 'slurm'])
@pytest.mark.skipif(os.name == 'nt', reason='PBS/Slurm submit hosts use POSIX shell')
def test_cluster_adapter_runs_same_worker_and_preserves_exit_status(runtime, tmp_path, kind):
    """Protocol simulator executes actual job.sh/worker/program, not canned outputs."""
    client, supervisor, server, config = runtime
    processes = {}
    calls = []
    def command(argv):
        calls.append(argv)
        job_id = '123.server' if kind == 'pbs' else '123'
        if argv[0] in {'qsub', 'sbatch'}:
            processes[job_id] = subprocess.Popen(['/bin/sh', argv[-1]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return CompletedProcess(argv, 0, job_id + '\n', '')
        process = processes[job_id]
        code = process.poll()
        if argv[0] == 'squeue':
            text = f'{job_id}|RUNNING|name\n' if code is None else ''
        elif argv[0] == 'sacct':
            text = f'{job_id}|COMPLETED|{code or 0}:0|name\n'
        elif argv[0] == 'qstat':
            job = {'job_state': 'R' if code is None else 'F'}
            if code is not None:
                job['Exit_status'] = code
            text = json.dumps({'Jobs': {job_id: job}})
        else:
            text = ''
        return CompletedProcess(argv, 0, text, '')
    supervisor.backends[kind].command = command
    ws = client.create_workspace(kind)['id']
    spec = TaskSpec(ws, ['{python}', '-c', "from pathlib import Path; import time; time.sleep(.2); Path('answer.txt').write_text(str(sum(range(20)))); print('done')"],
                    backend=kind, outputs=['answer.txt'], resources={'cpus': 2, 'nodes': 1, 'walltime_seconds': 30})
    record = client.submit(spec)
    try:
        supervisor.tick()
        assert client.task(record['id'])['state'] == 'queued'
        final = finish(client, supervisor, record['id'])
        assert final['state'] == 'succeeded'
        assert final['backend_id'] == ('123.server' if kind == 'pbs' else '123')
        output = client.download(record['id'], 'answer.txt', tmp_path / 'answer.txt')
        assert output.read_text() == '190'
        assert calls[0][0] == ('qsub' if kind == 'pbs' else 'sbatch')
    finally:
        for process in processes.values():
            process.wait(timeout=5)


def test_ambiguous_submission_is_not_repeated(runtime):
    client, supervisor, _, _ = runtime
    ws = client.create_workspace('ambiguous')['id']
    calls = []
    def command(argv):
        calls.append(argv)
        if argv[0] == 'sbatch':
            raise TimeoutExpired(argv, 20)
        return CompletedProcess(argv, 0, '', '')
    supervisor.backends['slurm'].command = command
    record = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass'], backend='slurm'), 'stable')
    for _ in range(4):
        supervisor.tick()
    assert client.task(record['id'])['state'] == 'unknown'
    assert sum(args[0] == 'sbatch' for args in calls) == 1
    assert client.submit(TaskSpec(ws, ['{python}', '-c', 'pass'], backend='slurm'), 'stable')['id'] == record['id']


@pytest.mark.parametrize('raw,code,state', [('COMPLETED', 0, 'succeeded'), ('COMPLETED', 2, 'failed'),
    ('COMPLETED', None, 'unknown'), ('F', 0, 'succeeded'), ('F', 271, 'failed'), ('F', None, 'unknown'),
    ('OUT_OF_MEMORY', None, 'failed'), ('TIMEOUT', None, 'failed'), ('CANCELLED by 1000', None, 'cancelled'),
    ('PENDING', None, 'queued'), ('R', None, 'running')])
def test_scheduler_state_mapping(raw, code, state):
    assert SlurmBackend.terminal(raw, code) == state


def test_slurm_accounting_uses_signal_exit_and_unknown_history(runtime):
    _, _, server, config = runtime
    backend = SlurmBackend(config)
    record = {'id': 'b'*32, 'created_at': '2026-09-09T00:00:00+00:00', 'backend_id': '42', 'spec': {'backend': 'slurm'}}
    def command(argv):
        return CompletedProcess(argv, 0, '42|FAILED|0:9|name\n' if argv[0] == 'sacct' else '', '')
    backend.command = command
    result = backend.query(record, Path('/unused'))
    assert result['state'] == 'failed' and result['exit_code'] == 137
    backend.command = lambda args: CompletedProcess(args, 1, '', 'accounting unavailable')
    assert backend.query(record, Path('/unused'))['state'] == 'unknown'


def test_pbs_history_and_cancellation_commands(runtime):
    _, _, _, config = runtime
    backend = PBSBackend(config)
    record = {'id': 'b'*32, 'backend_id': '42.server', 'spec': {'backend': 'pbs'}}
    calls = []
    def command(argv):
        calls.append(argv)
        if '-x' in argv:
            return CompletedProcess(argv, 1, '', 'history disabled')
        return CompletedProcess(argv, 0, json.dumps({'Jobs': {'42.server': {'job_state': 'R'}}}), '')
    backend.command = command
    assert backend.query(record, Path('/unused'))['state'] == 'running'
    assert '-x' in calls[0] and '-x' not in calls[1]


@pytest.mark.parametrize('message,expected', [
    ('Invalid partition name', 'failed'),
    ('Connection reset by peer', 'unknown'),
])
def test_submission_rejection_and_uncertain_transport(runtime, message, expected):
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace('submission failure')['id']
    supervisor.backends['slurm'].command = lambda args: CompletedProcess(args, 1, '', message)
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', 'pass'], backend='slurm'))
    supervisor.tick()
    assert client.task(task['id'])['state'] == expected


def test_cancel_never_reports_success_during_scheduler_outage(runtime):
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('cancel outage')['id']
    backend = supervisor.backends['slurm']
    def command(args):
        if args[0] == 'sbatch':
            return CompletedProcess(args, 0, '42\n', '')
        if args[0] == 'scancel':
            return CompletedProcess(args, 0, '', '')
        if args[0] == 'squeue':
            return CompletedProcess(args, 1, '', 'connection unavailable')
        return CompletedProcess(args, 0, '', '')
    backend.command = command
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', 'pass'], backend='slurm'))
    supervisor.tick()
    client.cancel(task['id'])
    supervisor.tick()
    assert client.task(task['id'])['state'] == 'unknown'
    # Once both queue and accounting confirm absence after acknowledged cancel,
    # it can leave the uncertain state.
    backend.command = lambda args: CompletedProcess(args, 0, '', '')
    supervisor.tick()
    assert client.task(task['id'])['state'] == 'cancelled'


def test_slurm_multinode_resources_and_accounting_calendar(tmp_path):
    backend = SlurmBackend({'python': '/cluster/python'})
    calls = []
    record = {'id': 'c'*32, 'created_at': '2026-09-09T01:00:00+00:00', 'backend_id': '42',
              'spec': {'backend': 'slurm', 'resources': {'nodes': 2, 'cpus': 8, 'gpus': 1, 'memory_mb': 4096}}}
    def command(args):
        calls.append(args)
        return CompletedProcess(args, 0, '42\n' if args[0] == 'sbatch' else '', '')
    backend.command = command
    backend.submit(record, tmp_path)
    assert {'--nodes=2', '--ntasks-per-node=1', '--cpus-per-task=8', '--gpus-per-node=1', '--mem=4096'} <= set(calls[0])
    backend.query(record, tmp_path)
    assert '--starttime=2026-09-08' in calls[-1]
