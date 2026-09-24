from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import json
import os
import shlex
import subprocess
import time

import pytest

from conftest import finish
from suan.runtime.backends import PBSBackend, SlurmBackend, SubmissionUnknown, scheduler_profile, validate_scheduler_profile
from suan.runtime.models import TaskSpec

pytestmark = pytest.mark.server


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
    ("sbatch: error: Batch job submission failed: Job violates accounting/QOS policy (job submit limit, user's size and/or time limits)", 'failed'),
    ('sbatch: error: Batch job submission failed: Socket timed out on send/recv operation', 'unknown'),
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


def recorder(calls):
    def command(args):
        calls.append(args)
        return CompletedProcess(args, 0, '42.server\n' if args[0] == 'qsub' else '42\n', '')
    return command


def test_mpi_layout_maps_ranks_and_threads_to_schedulers(tmp_path):
    calls = []
    resources = {'nodes': 2, 'ranks': 8, 'threads_per_rank': 2, 'memory_mb': 4096}
    slurm = SlurmBackend({'python': '/cluster/python'})
    slurm.command = recorder(calls)
    slurm.submit({'id': 'e' * 32, 'spec': {'backend': 'slurm', 'resources': resources}}, tmp_path)
    assert calls[-1][3:7] == ['--nodes=2', '--ntasks=8', '--ntasks-per-node=4', '--cpus-per-task=2']
    assert '--ntasks-per-node=1' not in calls[-1] and '--mem=4096' in calls[-1]
    pbs = PBSBackend({'python': '/cluster/python'})
    pbs.command = recorder(calls)
    pbs.submit({'id': 'e' * 32, 'spec': {'backend': 'pbs', 'resources': resources}}, tmp_path)
    assert 'select=2:ncpus=8:mpiprocs=4:ompthreads=2:mem=4096mb' in calls[-1]


def test_legacy_scheduler_argv_is_unchanged(tmp_path):
    calls = []
    record = {'id': 'd' * 32, 'spec': {'backend': 'slurm', 'resources': {'nodes': 2, 'cpus': 8, 'queue': 'q', 'walltime_seconds': 3661}}}
    slurm = SlurmBackend({'python': '/cluster/python'})
    slurm.command = recorder(calls)
    slurm.submit(record, tmp_path)
    assert calls[-1] == ['sbatch', '--parsable', '--job-name=stk-' + 'd' * 32,
                         '--ntasks-per-node=1', '--cpus-per-task=8', '--nodes=2',
                         f"--chdir={tmp_path / 'work'}", f"--output={tmp_path / 'scheduler.out'}",
                         f"--error={tmp_path / 'scheduler.err'}", '--partition=q', '--time=1:01:01', str(tmp_path / 'job.sh')]
    command = ['/cluster/python', str(tmp_path / 'worker.py'), str(tmp_path)]
    assert (tmp_path / 'job.sh').read_bytes() == ("#!/bin/sh\nexec " + shlex.join(command) + "\n").encode()
    pbs = PBSBackend({'python': '/cluster/python'})
    pbs.command = recorder(calls)
    pbs.submit({'id': 'd' * 32, 'spec': {'backend': 'pbs', 'resources': {'nodes': 2, 'cpus': 8}}}, tmp_path)
    assert calls[-1] == ['qsub', '-N', 's' + 'd' * 14, '-l', 'select=2:ncpus=8', '-o', str(tmp_path / 'scheduler.out'),
                         '-e', str(tmp_path / 'scheduler.err'), str(tmp_path / 'job.sh')]


def test_site_profile_job_script_defaults_and_extra_args(tmp_path):
    profile = {'queue': 'q', 'account': 'a', 'qos': 'x', 'job_shell': '/bin/bash',
               'preamble': ['source /public1/soft/modules/module.sh', 'module load mpi/intel/2021'],
               'submit_args': ['--exclusive']}
    calls = []
    slurm = SlurmBackend({'python': '/cluster/python', 'scheduler': profile})
    slurm.command = recorder(calls)
    slurm.submit({'id': 'f' * 32, 'spec': {'backend': 'slurm', 'resources': {'ranks': 4}}}, tmp_path)
    assert {'--partition=q', '--account=a', '--qos=x'} <= set(calls[-1])
    assert calls[-1][-2:] == ['--exclusive', str(tmp_path / 'job.sh')]
    command = ['/cluster/python', str(tmp_path / 'worker.py'), str(tmp_path)]
    assert (tmp_path / 'job.sh').read_text().split('\n') == ['#!/bin/bash', *profile['preamble'], 'exec ' + shlex.join(command), '']
    slurm.submit({'id': 'f' * 32, 'spec': {'backend': 'slurm', 'resources': {'queue': 'debug', 'account': 'b'}}}, tmp_path)
    assert {'--partition=debug', '--account=b'} <= set(calls[-1])
    assert '--partition=q' not in calls[-1] and '--account=a' not in calls[-1]
    pbs = PBSBackend({'python': '/cluster/python', 'scheduler': profile})
    pbs.command = recorder(calls)
    pbs.submit({'id': 'f' * 32, 'spec': {'backend': 'pbs', 'resources': {}}}, tmp_path)
    args = calls[-1]
    assert args[args.index('-q'):args.index('-q') + 4] == ['-q', 'q', '-A', 'a']
    assert 'x' not in args and not any('qos' in a for a in args)
    assert args[-2:] == ['--exclusive', str(tmp_path / 'job.sh')]


def test_invalid_site_profile_fails_without_submitting(runtime):
    client, supervisor, _, config = runtime
    calls = []
    supervisor.backends['slurm'].command = recorder(calls)
    config['scheduler'] = {'preamble': 'not-a-list'}
    workspace = client.create_workspace('site profile')['id']
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', 'pass'], backend='slurm'))
    supervisor.tick()
    record = client.task(task['id'])
    assert record['state'] == 'failed' and 'Invalid scheduler profile' in record['reason']
    assert calls == []


@pytest.mark.parametrize('profile', [
    'q', [], '', 0, False, {'partition': 'q'}, {'queue': 'bad queue'}, {'qos': 3}, {'job_shell': 'bash'},
    {'job_shell': '/bin/sh\n'}, {'preamble': ['module load a\nsbatch evil.sh']}, {'preamble': [1]},
    {'submit_args': '--exclusive'}, {'submit_args': ['exclusive']}, {'submit_args': ['-']},
    # Directives before the first command are scheduler options that would bypass the submit_args checks.
    {'preamble': ['#SBATCH --export=NONE']}, {'preamble': ['module load a', '  #PBS -h']},
])
def test_invalid_site_profile_values(profile):
    with pytest.raises(ValueError, match='^Invalid scheduler profile: '):
        validate_scheduler_profile(profile)
    with pytest.raises(RuntimeError, match='^Invalid scheduler profile: '):
        scheduler_profile({'scheduler': profile})


@pytest.mark.parametrize('arg', [
    '--job-name=x', '--job=x', '-J', '-Jx', '--parsable', '--chdir=/tmp', '-D/tmp', '--output=o', '--out=o',
    '-o', '-oout', '--error=e', '-e', '--wrap=hostname', '--array=1-4', '-a1-4', '--test-only', '--wait', '-W',
    '--export=NONE', '--export', '--', '-N', '-Nname', '-Wblock=true', '-I', '-J1-4', '--test', '--outp=x',
    '--help', '-h', '--usage', '-V', '--version',
    # Slurm -M/--clusters submits where squeue/sacct/scancel do not look; -Q and PBS -z print no job ID.
    '--clusters=b', '--cluster=b', '-Mb', '-M', '--quiet', '--qu', '-Q', '-z',
])
def test_site_profile_rejects_options_stk_relies_on(arg):
    with pytest.raises(ValueError, match='^Invalid scheduler profile: .*STK'):
        validate_scheduler_profile({'submit_args': ['--exclusive', arg]})


def test_scheduler_specific_options_are_checked_per_scheduler(tmp_path):
    mail = {'submit_args': ['-Muser@example.org', '-mabe']}  # PBS -M is a mail list
    assert validate_scheduler_profile(mail, 'pbs') is mail
    for kind in ('slurm', None):
        with pytest.raises(ValueError, match='must not set -M'):
            validate_scheduler_profile(mail, kind)
    with pytest.raises(ValueError, match='must not set -z'):
        validate_scheduler_profile({'submit_args': ['-z']}, 'pbs')
    assert validate_scheduler_profile({'submit_args': ['--cluster-constraint=ib']}, 'slurm')
    calls = []
    pbs = PBSBackend({'python': '/cluster/python', 'scheduler': mail})
    pbs.command = recorder(calls)
    pbs.submit({'id': 'f' * 32, 'spec': {'backend': 'pbs', 'resources': {}}}, tmp_path)
    assert calls[-1][-3:] == ['-Muser@example.org', '-mabe', str(tmp_path / 'job.sh')]
    slurm = SlurmBackend({'python': '/cluster/python', 'scheduler': mail})
    slurm.command = recorder(calls)
    with pytest.raises(RuntimeError, match='must not set -M'):
        slurm.submit({'id': 'f' * 32, 'spec': {'backend': 'slurm', 'resources': {}}}, tmp_path)
    assert calls[-1][0] == 'qsub'


def test_site_profile_accepts_site_options():
    profile = {'queue': 'cpu', 'job_shell': '/bin/bash', 'preamble': [],
               'submit_args': ['--exclusive', '--constraint=ib', '--wait-all-nodes=1', '-lplace=scatter',
                               '--hint=nomultithread', '--verbose', '--use-min-nodes']}
    assert validate_scheduler_profile(profile) is profile
    assert scheduler_profile({'python': '/cluster/python'}) == {}
    assert scheduler_profile({'python': '/cluster/python', 'scheduler': None}) == {}
