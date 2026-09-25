from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import base64
import errno
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

import pytest

from conftest import finish
from suan.runtime.client import RuntimeClient, RuntimeErrorResponse
from suan.runtime.models import TaskSpec
from suan.runtime.common import atomic_json, instance_lock, read_json, sha256
from suan.runtime.supervisor import Supervisor

pytestmark = pytest.mark.server


def test_snapshot_isolation_idempotency_and_outputs(runtime, tmp_path):
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('参数计算')['id']
    file = tmp_path / 'input.txt'
    file.write_text('original')
    client.upload(workspace, file, '子目录/input.txt')
    program = "from pathlib import Path; print('计算完成'); Path('answer.txt').write_text(Path('子目录/input.txt').read_text())"
    spec = TaskSpec(workspace, ['{python}', '-c', program], outputs=['answer.txt'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda _: client.submit(spec, 'one-key'), range(4)))
    assert len({r['id'] for r in records}) == 1
    with pytest.raises(RuntimeErrorResponse, match='different task'):
        client.submit(TaskSpec(workspace, ['{python}', '-c', 'pass']), 'one-key')
    file.write_text('changed after submission')
    client.upload(workspace, file, '子目录/input.txt')
    task = finish(client, supervisor, records[0]['id'])
    assert task['state'] == 'succeeded'
    assert client.logs(task['id'])['bytes'].decode().strip() == '计算完成'
    items = client.artifacts(task['id'])
    assert [i['path'] for i in items] == ['answer.txt']
    target = client.download(task['id'], 'answer.txt', tmp_path / 'download.txt')
    assert target.read_text() == 'original'
    assert sha256(target) == items[0]['sha256']
    subprocess.run([sys.executable, '-c', 'import suan.runtime.client, sys; assert "PySide6" not in sys.modules'], check=True)


def test_upload_resume_and_pending_snapshot(runtime, tmp_path):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('upload')['id']
    data = b'x' * (1024 * 1024 + 31)
    digest = hashlib.sha256(data).hexdigest()
    prefix = f'workspaces/{ws}/uploads'
    meta = client.request('POST', prefix, {'path': 'large.bin', 'size': len(data), 'sha256': digest})
    client.request('PUT', f"{prefix}/{meta['id']}?offset=0", data[:1000])
    with pytest.raises(RuntimeErrorResponse, match='offset'):
        client.request('PUT', f"{prefix}/{meta['id']}?offset=0", b'bad')
    with pytest.raises(RuntimeErrorResponse, match='pending uploads'):
        client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']), 'pending')
    source = tmp_path / 'large.bin'
    source.write_bytes(data)
    assert client.upload(ws, source)['completed']
    assert client.files(ws)[0]['sha256'] == digest
    task = client.submit(TaskSpec(ws, ['{python}', '-c', "from pathlib import Path; Path('copy.bin').write_bytes(Path('large.bin').read_bytes())"]), 'ready')
    assert finish(client, supervisor, task['id'])['state'] == 'succeeded'
    item = client.artifacts(task['id'])[0]
    target = tmp_path / 'copy.bin'
    target.with_name('copy.bin.part').write_bytes(data[:1234])
    atomic_json(target.with_name('copy.bin.part.json'), item)
    calls = []
    original = client.request
    def traced(method, route, *args, **kwargs):
        calls.append(route)
        return original(method, route, *args, **kwargs)
    client.request = traced
    client.download(task['id'], 'copy.bin', target)
    assert target.read_bytes() == data
    assert any('offset=1234' in route for route in calls)


def test_authentication_and_path_boundaries(runtime, tmp_path):
    client, supervisor, server, _ = runtime
    with pytest.raises(RuntimeErrorResponse) as exc:
        RuntimeClient(client.url, 'wrong').health()
    assert exc.value.status == 401
    ws = client.create_workspace('files')['id']
    for name in ['../escape', '/absolute', 'C:/file', 'dir/../../escape', 'a\\b']:
        with pytest.raises(RuntimeErrorResponse):
            client.request('POST', f'workspaces/{ws}/uploads', {'path': name, 'size': 0, 'sha256': hashlib.sha256(b'').hexdigest()})
    if os.name != 'nt':
        outside = tmp_path / 'outside'
        outside.write_text('private')
        (server.service.workspace_dir(ws) / 'inputs' / 'link').symlink_to(outside)
        with pytest.raises(RuntimeErrorResponse, match='Symbolic'):
            client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']), 'symlink')


@pytest.mark.parametrize('program,outputs,expected,reason', [
    ('import sys; sys.exit(7)', [], 'failed', 'code 7'),
    ('pass', ['missing.dat'], 'failed', 'Expected output'),
    ('import time; time.sleep(8)', [], 'failed', 'Walltime'),
])
def test_failures(runtime, program, outputs, expected, reason):
    client, supervisor, _, _ = runtime
    ws = client.create_workspace('failures')['id']
    task = client.submit(TaskSpec(ws, ['{python}', '-c', program], outputs=outputs, resources={'walltime_seconds': 1}))
    record = finish(client, supervisor, task['id'])
    assert record['state'] == expected
    assert reason in record['reason']


def test_cancel_queued_and_running_and_concurrency(runtime):
    client, supervisor, _, _ = runtime
    ws = client.create_workspace('queue')['id']
    spec = TaskSpec(ws, ['{python}', '-c', 'import time; print("ready", flush=True); time.sleep(20)'])
    first, second = client.submit(spec), client.submit(spec)
    supervisor.tick()
    assert client.task(first['id'])['state'] == 'running'
    assert client.task(second['id'])['state'] == 'queued'
    assert client.cancel(second['id'])['state'] == 'cancelled'
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not client.logs(first['id'])['bytes']:
        time.sleep(.05)
    client.cancel(first['id'])
    assert finish(client, supervisor, first['id'])['state'] == 'cancelled'


def test_reconnect_and_supervisor_reconstruction(runtime):
    client, supervisor, server, config = runtime
    ws = client.create_workspace('reconnect')['id']
    task = client.submit(TaskSpec(ws, ['{python}', '-c', "import time; print('before', flush=True); time.sleep(.5); print('after', flush=True)"]))
    supervisor.tick()
    original_pid = client.task(task['id'])['backend_id']
    # No client/poller is needed while the worker runs.
    time.sleep(.8)
    reconnected = RuntimeClient(client.url, config['token'])
    restored = Supervisor(config)
    result = finish(reconnected, restored, task['id'])
    assert result['backend_id'] == original_pid
    assert result['state'] == 'succeeded'
    logs = reconnected.logs(task['id'])
    assert logs['bytes'] == b'before\nafter\n'
    assert reconnected.logs(task['id'], offset=logs['next_offset'])['bytes'] == b''


def test_memory_limit_and_input_checksum_rejection(runtime, tmp_path):
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace('memory')['id']
    task = client.submit(TaskSpec(workspace, ['{python}', '-c',
        "import time; data = bytearray(64*1024*1024); time.sleep(5)"], resources={'memory_mb': 16}))
    result = finish(client, supervisor, task['id'])
    assert result['state'] == 'failed' and 'Memory limit' in result['reason']
    prefix = f'workspaces/{workspace}/uploads'
    upload = client.request('POST', prefix, {'path': 'input.bin', 'size': 3,
                                             'sha256': hashlib.sha256(b'yes').hexdigest()})
    client.request('PUT', f"{prefix}/{upload['id']}?offset=0", b'bad')
    with pytest.raises(RuntimeErrorResponse, match='checksum'):
        client.request('POST', f"{prefix}/{upload['id']}/finish", {})
    assert client.files(workspace) == []
    client.request('DELETE', f"{prefix}/{upload['id']}")


def test_lost_worker_does_not_hide_live_program_and_can_cancel(runtime):
    import psutil
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('worker loss')['id']
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', "import time; print('ready', flush=True); time.sleep(20)"]))
    supervisor.tick()
    deadline = time.monotonic() + 5
    while not client.logs(task['id'])['bytes']:
        assert time.monotonic() < deadline
        time.sleep(.05)
    wrapper = psutil.Process(int(client.task(task['id'])['backend_id']))
    wrapper.kill()
    wrapper.wait(timeout=5)
    supervisor.tick()
    assert client.task(task['id'])['state'] == 'unknown'
    client.cancel(task['id'])
    assert finish(client, supervisor, task['id'])['state'] == 'cancelled'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX scheduler signals')
def test_external_worker_signal_is_failure_not_user_cancellation(runtime):
    import signal
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace('scheduler termination')['id']
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', "import time; print('ready', flush=True); time.sleep(20)"]))
    supervisor.tick()
    deadline = time.monotonic() + 5
    while not client.logs(task['id'])['bytes']:
        assert time.monotonic() < deadline
        time.sleep(.05)
    os.kill(int(client.task(task['id'])['backend_id']), signal.SIGTERM)
    result = finish(client, supervisor, task['id'])
    assert result['state'] == 'failed' and 'signal' in result['reason']


def test_local_launch_failure_is_terminal_and_frees_the_slot(runtime, tmp_path):
    client, supervisor, _, config = runtime
    ws = client.create_workspace('launch failure')['id']
    python = config['python']
    broken = tmp_path / 'not-executable'
    broken.write_text('x')
    broken.chmod(0o644)
    config['python'] = str(broken)  # shared by the service and the supervisor
    first = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    supervisor.tick()
    record = client.task(first['id'])
    assert record['state'] == 'failed'
    assert 'could not be started' in record['reason'] and 'Permission denied' in record['reason']
    config['python'] = python
    second = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    assert finish(client, supervisor, second['id'])['state'] == 'succeeded'


def test_unopenable_wrapper_log_fails_the_launch(runtime):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('wrapper log')['id']
    task = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    (server.service.task_dir(task['id']) / 'wrapper.log').mkdir()
    supervisor.tick()
    record = client.task(task['id'])
    assert record['state'] == 'failed'
    assert 'could not be started' in record['reason'] and 'Is a directory' in record['reason']


def test_transient_launch_failure_is_requeued(runtime, monkeypatch, caplog):
    client, supervisor, _, _ = runtime
    ws = client.create_workspace('fork limit')['id']
    popen = subprocess.Popen
    cancel = []
    def exhausted(argv, *args, **kwargs):
        if cancel:
            client.cancel(Path(argv[-1]).name)  # arrives while the launch is attempted
        raise BlockingIOError(errno.EAGAIN, 'Resource temporarily unavailable')
    monkeypatch.setattr(subprocess, 'Popen', exhausted)
    task = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    supervisor.tick()
    record = client.task(task['id'])
    assert record['state'] == 'queued' and not record['attempted_at']
    assert 'temporarily unavailable' in record['reason']
    supervisor.tick()
    # The supervisor journal shows the deferral once per task, not once per tick.
    assert [r.levelname for r in caplog.records if 'deferred' in r.getMessage()] == ['WARNING']
    monkeypatch.setattr(subprocess, 'Popen', popen)
    assert finish(client, supervisor, task['id'])['state'] == 'succeeded'
    monkeypatch.setattr(subprocess, 'Popen', exhausted)
    cancel.append(True)
    task = client.submit(TaskSpec(ws, ['{python}', '-c', 'print(1)']))
    supervisor.tick()
    assert client.task(task['id'])['state'] == 'cancelled'


def test_finished_local_workers_are_reaped(runtime):
    import psutil
    client, supervisor, _, config = runtime
    config['concurrency'] = 4
    ws = client.create_workspace('reaping')['id']
    tasks = [client.submit(TaskSpec(ws, ['{python}', '-c', f'print({n})'])) for n in range(6)]
    for task in tasks:
        assert finish(client, supervisor, task['id'])['state'] == 'succeeded'
    # A finished task is never queried again; the tick itself must wait for its worker.
    local = supervisor.backends['local']
    deadline = time.monotonic() + 5
    while local.children and time.monotonic() < deadline:
        supervisor.tick()
        time.sleep(.05)
    assert local.children == {}
    pids = {int(client.task(task['id'])['backend_id']) for task in tasks}
    assert [c for c in psutil.Process().children() if c.pid in pids and c.status() == psutil.STATUS_ZOMBIE] == []


def test_cancelled_queued_task_without_dispatch_is_finalized(runtime):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('interrupted cancel')['id']
    task = client.submit(TaskSpec(ws, ['{python}', '-c', "open('ran', 'w').close()"]))
    # As if the API or supervisor died between setting cancel_requested and cancelling.
    server.service.store.update(task['id'], cancel_requested=True)
    supervisor.tick()
    record = client.task(task['id'])
    assert (record['state'], record['reason']) == ('cancelled', 'Cancelled before dispatch')
    assert not record.get('attempted_at') and not (server.service.task_dir(task['id']) / 'work' / 'ran').exists()


def test_task_env_cannot_set_scheduler_markers_or_local_mpi_opt_in(runtime, monkeypatch):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('reserved env')['id']
    program = ("import os; print(*(os.environ.get(k) for k in "
               "('SLURM_JOB_ID', 'PBS_JOBID', 'STK_MUPRO_ALLOW_LOCAL_MPI')))")
    for key in ('SLURM_JOB_ID', 'PBS_JOBID', 'STK_MUPRO_ALLOW_LOCAL_MPI'):
        with pytest.raises(ValueError, match=key):
            TaskSpec(ws, ['{python}', '-c', program], env={key: '1'})
        with pytest.raises(RuntimeErrorResponse, match=key):
            client.submit({'workspace_id': ws, 'argv': ['{python}', '-c', program], 'env': {key: '1'}})
    # A spec stored before the refusal would run the worker.py copied back then, so it never dispatches.
    store = server.service.store
    task = client.submit(TaskSpec(ws, ['{python}', '-c', "open('ran', 'w').close()"]))
    store.update(task['id'], spec={**store.task(task['id'])['spec'],
                                   'env': {'SLURM_JOB_ID': '1', 'STK_MUPRO_ALLOW_LOCAL_MPI': '1'}})
    supervisor.tick()
    record = client.task(task['id'])
    assert record['state'] == 'failed' and not record.get('attempted_at')
    assert record['reason'].startswith('Resubmit without SLURM_JOB_ID, STK_MUPRO_ALLOW_LOCAL_MPI in env')
    assert not (server.service.task_dir(task['id']) / 'work' / 'ran').exists()
    # Defense in depth: the current worker keeps the Runtime's own values even if launch.json sets them.
    monkeypatch.delenv('SLURM_JOB_ID', raising=False)
    monkeypatch.delenv('PBS_JOBID', raising=False)
    monkeypatch.setenv('STK_MUPRO_ALLOW_LOCAL_MPI', '0')
    task = client.submit(TaskSpec(ws, ['{python}', '-c', program]))
    launch = server.service.task_dir(task['id']) / 'launch.json'
    data = read_json(launch)
    data['spec']['env'] = {'SLURM_JOB_ID': '1', 'PBS_JOBID': 'x', 'STK_MUPRO_ALLOW_LOCAL_MPI': '1'}
    atomic_json(launch, data)
    assert finish(client, supervisor, task['id'])['state'] == 'succeeded'
    assert client.logs(task['id'])['bytes'].strip() == b'None None 0'


def test_cancel_finishes_handle_less_unknown_task_without_running_it(runtime):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('handle-less')['id']
    stuck = client.submit(TaskSpec(ws, ['{python}', '-c', "open('ran', 'w').close()"]))
    waiting = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    store = server.service.store
    store.claim(stuck['id'])  # as if the supervisor died between Popen and persistence
    store.update(stuck['id'], state='unknown', reason='Dispatch failed: simulated crash')
    root = server.service.task_dir(stuck['id'])
    with instance_lock(root / 'worker.lock'):  # a worker that is still starting
        for _ in range(3):
            supervisor.tick()
    record = client.task(stuck['id'])
    assert record['state'] == 'unknown' and record['reason'] == 'Dispatch failed: simulated crash'
    assert client.task(waiting['id'])['state'] == 'queued'  # the unknown task holds the slot
    client.cancel(stuck['id'])
    assert finish(client, supervisor, stuck['id'])['state'] == 'cancelled'
    assert finish(client, supervisor, waiting['id'])['state'] == 'succeeded'
    # A late worker finds the tombstone and exits without running the program.
    assert subprocess.run([sys.executable, str(root / 'worker.py'), str(root)]).returncode == 0
    assert not (root / 'work' / 'ran').exists() and not (root / 'program.json').exists()


def test_handle_less_unknown_task_fails_with_its_dispatch_error(runtime):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('handle-less failure')['id']
    stuck = client.submit(TaskSpec(ws, ['{python}', '-c', "open('ran', 'w').close()"]))
    waiting = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    store = server.service.store
    store.claim(stuck['id'])
    store.update(stuck['id'], state='unknown', reason='Dispatch failed: simulated crash')
    record = finish(client, supervisor, stuck['id'])
    assert record['state'] == 'failed'
    assert 'No task worker was started' in record['reason'] and 'simulated crash' in record['reason']
    assert finish(client, supervisor, waiting['id'])['state'] == 'succeeded'
    root = server.service.task_dir(stuck['id'])
    assert subprocess.run([sys.executable, str(root / 'worker.py'), str(root)]).returncode == 0
    assert not (root / 'work' / 'ran').exists()
    assert client.task(stuck['id'])['reason'] == record['reason']


def test_handle_less_submitting_task_left_by_a_crash_fails(runtime):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('interrupted claim')['id']
    stuck = client.submit(TaskSpec(ws, ['{python}', '-c', "open('ran', 'w').close()"]))
    waiting = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    server.service.store.claim(stuck['id'])  # the supervisor died before launching or persisting a handle
    assert client.task(stuck['id'])['state'] == 'submitting'
    record = finish(client, supervisor, stuck['id'])
    assert record['state'] == 'failed' and record['reason'] == 'No task worker was started'
    assert finish(client, supervisor, waiting['id'])['state'] == 'succeeded'
    root = server.service.task_dir(stuck['id'])
    assert subprocess.run([sys.executable, str(root / 'worker.py'), str(root)]).returncode == 0
    assert not (root / 'work' / 'ran').exists()


def test_handle_less_task_without_run_directory_fails(runtime):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('missing run directory')['id']
    stuck = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    waiting = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    store = server.service.store
    store.claim(stuck['id'])
    store.update(stuck['id'], state='unknown', reason='Dispatch failed: simulated crash')
    shutil.rmtree(server.service.task_dir(stuck['id']))
    record = finish(client, supervisor, stuck['id'])
    assert record['state'] == 'failed' and record['reason'] == 'No task worker was started (Dispatch failed: simulated crash)'
    assert finish(client, supervisor, waiting['id'])['state'] == 'succeeded'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX shell wrapper')
def test_starting_worker_is_not_tombstoned_after_a_post_launch_error(runtime, monkeypatch, tmp_path):
    import suan.runtime.backends as backends
    client, supervisor, _, config = runtime
    ws = client.create_workspace('slow worker start')['id']
    task = client.submit(TaskSpec(ws, ['{python}', '-c', "open('ran', 'w').close()"]))
    slow = tmp_path / 'slow-python'
    slow.write_text(f'#!/bin/sh\nsleep 1\nexec {shlex.quote(config["python"])} "$@"\n')
    slow.chmod(0o755)
    config['python'] = str(slow)  # the worker is alive but has not taken its lock yet
    def lost(pid):
        raise RuntimeError('identity unavailable')
    monkeypatch.setattr(backends, 'identity', lost)
    supervisor.tick()
    supervisor.tick()
    record = client.task(task['id'])
    assert record['state'] == 'unknown' and record['reason'] == 'Dispatch failed: identity unavailable'
    record = finish(client, supervisor, task['id'])
    assert record['state'] == 'succeeded'
    assert (supervisor.service.task_dir(task['id']) / 'work' / 'ran').exists()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX symbolic links')
def test_unresolvable_task_dir_fails_task_and_tick_continues(runtime, tmp_path):
    client, supervisor, server, _ = runtime
    ws = client.create_workspace('task directory')['id']
    task = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    root = server.service.task_dir(task['id'])
    root.rename(tmp_path / 'moved')
    root.symlink_to(tmp_path / 'moved', target_is_directory=True)
    supervisor.tick()
    record = client.task(task['id'])
    assert record['state'] == 'failed' and 'Symbolic links' in record['reason']
    other = client.submit(TaskSpec(ws, ['{python}', '-c', 'pass']))
    assert finish(client, supervisor, other['id'])['state'] == 'succeeded'


def test_supervisor_loop_survives_a_failing_tick(runtime, monkeypatch):
    import signal
    _, _, _, config = runtime
    config['poll_interval'] = 0
    supervisor = Supervisor(config)
    calls = []
    def tick():
        calls.append(len(calls))
        if len(calls) == 1:
            raise OSError('database is locked')
        supervisor.stopping = True
    supervisor.tick = tick
    monkeypatch.setattr(signal, 'signal', lambda *args: None)  # keep pytest's handlers
    supervisor.run()
    assert calls == [0, 1]


def test_mpi_layout_threads_and_argv_tokens(runtime, monkeypatch):
    client, supervisor, server, _ = runtime
    monkeypatch.setenv('OMP_NUM_THREADS', '48')  # e.g. inherited from a login shell or PBS
    monkeypatch.delenv('MKL_NUM_THREADS', raising=False)
    ws = client.create_workspace('mpi layout')['id']
    program = "import os, sys; print(os.environ['OMP_NUM_THREADS'], os.environ.get('MKL_NUM_THREADS'), *sys.argv[1:])"
    cases = [({'ranks': 2}, {}, b'1 1 2 1'),
             ({'ranks': 2, 'threads_per_rank': 3}, {}, b'3 3 2 3'),
             ({'ranks': 2}, {'OMP_NUM_THREADS': '5'}, b'5 1 2 1'),  # an explicit task env wins
             ({'cpus': 4}, {}, b'48 None 1 4')]  # the legacy layout is unchanged
    for resources, env, expected in cases:
        spec = TaskSpec(ws, ['{python}', '-c', program, '{ranks}', '{threads_per_rank}'], resources=resources, env=env)
        task = finish(client, supervisor, client.submit(spec)['id'])
        assert task['state'] == 'succeeded'
        assert client.logs(task['id'])['bytes'].strip() == expected
    environment = read_json(server.service.task_dir(task['id']) / 'environment.json')
    assert environment['layout'] == {'nodes': 1, 'ranks': 1, 'threads_per_rank': 4}
    assert environment['threads'] == {'OMP_NUM_THREADS': '48', 'MKL_NUM_THREADS': None}
    spec = TaskSpec(ws, ['{python}', '-c', 'pass', '{nodes}', '-n={ranks}', '{python} '],
                    resources={'ranks': 2, 'threads_per_rank': 3})
    task = finish(client, supervisor, client.submit(spec)['id'])
    environment = read_json(server.service.task_dir(task['id']) / 'environment.json')
    assert environment['argv'][3:] == ['1', '-n={ranks}', '{python} ']  # whole arguments only
    assert environment['layout'] == {'nodes': 1, 'ranks': 2, 'threads_per_rank': 3}
    assert environment['threads'] == {'OMP_NUM_THREADS': '3', 'MKL_NUM_THREADS': '3'}


def test_health_advertises_mpi_resources_and_tokens(runtime):
    client, _, _, _ = runtime
    health = client.health()
    assert health['api_version'] == 1
    assert {'ranks', 'threads_per_rank', 'cpus'} <= set(health['resources'])
    assert health['resources'] == sorted(health['resources'])
    assert health['argv_tokens'] == ['{python}', '{ranks}', '{threads_per_rank}', '{nodes}']
