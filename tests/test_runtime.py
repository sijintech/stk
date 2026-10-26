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
from suan.runtime.common import alive, atomic_json, instance_lock, read_json, sha256
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
    from suan.runtime.worker import terminate_tree
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('worker loss')['id']
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', "import time; print('ready', flush=True); time.sleep(20)"]))
    root, program = server.service.task_dir(task['id']), None
    try:
        supervisor.tick()
        deadline = time.monotonic() + 5
        while True:
            program = read_json(root / 'program.json')
            if client.logs(task['id'])['bytes'] == b'ready\n' and alive(program):
                break
            assert time.monotonic() < deadline, 'program readiness and durable identity were not both observed'
            time.sleep(.01)
        wrapper = psutil.Process(int(client.task(task['id'])['backend_id']))
        assert any(child.pid == program['pid'] for child in wrapper.children())
        wrapper.kill()
        wrapper.wait(timeout=5)
        assert alive(program)
        supervisor.tick()
        assert client.task(task['id'])['state'] == 'unknown'
        client.cancel(task['id'])
        assert finish(client, supervisor, task['id'])['state'] == 'cancelled'
        assert not alive(program)
    finally:
        client.cancel(task['id'])
        program = program or read_json(root / 'program.json')
        if alive(program):
            terminate_tree(psutil.Process(program['pid']), expected_created=program['create_time'])


@pytest.mark.skipif(os.name == 'nt', reason='POSIX exec authorization pipe')
@pytest.mark.parametrize('failure', ['worker_killed', 'publication_failed'])
def test_program_never_executes_without_published_identity(runtime, failure, tmp_path):
    import psutil
    from suan.runtime.worker import terminate_tree
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('program identity publication')['id']
    command = ("from pathlib import Path; import time; Path('executed').write_text('yes'); "
               "print('ready', flush=True); time.sleep(20)")
    (tmp_path / 'sitecustomize.py').write_text(
        "from pathlib import Path; Path('python-environment-executed').write_text('yes')", encoding='utf-8')
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', command], env={'PYTHONPATH': str(tmp_path)}))
    root = server.service.task_dir(task['id'])
    copied_worker = root / 'worker.py'
    source = copied_worker.read_text(encoding='utf-8')
    entry = 'if __name__ == "__main__":'
    assert source.count(entry) == 1
    # Interpose only in this task's standalone copy. The child PID must match the
    # parent's live PID/create_time, so no elapsed-time guess selects the crash window.
    probe = '''
_original_write_json, _original_run_program = write_json, run_program
def write_json(path, data):
    if path.name == 'program.json':
        _original_write_json(path.parent / 'publication-pending.json', data)
        deadline = time.monotonic() + 15
        while not (path.parent / 'release-publication').exists():
            if time.monotonic() >= deadline:
                raise RuntimeError('test publication handshake timed out')
            time.sleep(.01)
        raise OSError('controlled program identity publication failure')
    return _original_write_json(path, data)
def run_program(gate, exec_confirmation, argv):
    _original_write_json(Path.cwd().parent / 'gate-waiting.json',
                         {'pid': os.getpid()})
    return _original_run_program(gate, exec_confirmation, argv)

'''
    copied_worker.write_text(source.replace(entry, probe + entry), encoding='utf-8')
    program = wrapper_identity = None
    try:
        supervisor.tick()
        wrapper = psutil.Process(int(client.task(task['id'])['backend_id']))
        wrapper_identity = {'pid': wrapper.pid, 'create_time': wrapper.create_time()}
        deadline = time.monotonic() + 5
        while True:
            program = read_json(root / 'publication-pending.json')
            gate = read_json(root / 'gate-waiting.json')
            if program and gate == {'pid': program['pid']} and alive(program):
                break
            assert time.monotonic() < deadline, 'parent and gated child did not reach the publication boundary'
            time.sleep(.01)
        assert not (root / 'program.json').exists()
        assert not (root / 'work' / 'executed').exists()
        assert not (root / 'work' / 'python-environment-executed').exists()
        assert client.logs(task['id'])['bytes'] == b''
        if failure == 'worker_killed':
            wrapper.kill()
            wrapper.wait(timeout=5)
        else:
            (root / 'release-publication').touch()
        deadline = time.monotonic() + 5
        while alive(program):
            assert time.monotonic() < deadline, 'unauthorized program gate remained alive'
            time.sleep(.01)
        result = finish(client, supervisor, task['id'])
        assert result['state'] == 'failed'
        assert ('without a completion record' if failure == 'worker_killed' else
                'controlled program identity publication failure') in result['reason']
        assert not (root / 'program.json').exists()
        assert not (root / 'work' / 'executed').exists()
        assert not (root / 'work' / 'python-environment-executed').exists()
        assert client.logs(task['id'])['bytes'] == b''
    finally:
        (root / 'release-publication').touch()
        client.cancel(task['id'])
        for identity in (program, wrapper_identity):
            if alive(identity):
                terminate_tree(psutil.Process(identity['pid']), expected_created=identity['create_time'])


@pytest.mark.skipif(os.name == 'nt', reason='POSIX exec authorization pipe')
def test_authorized_program_exec_failure_keeps_a_failure_diagnostic(runtime, tmp_path):
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('missing executable')['id']
    task = client.submit(TaskSpec(workspace, [str(tmp_path / 'missing-public-test-program')],
                                  resources={'memory_mb': 1}))
    result = finish(client, supervisor, task['id'])
    assert result['state'] == 'failed' and result['exit_code'] == 127
    root = server.service.task_dir(task['id'])
    assert 'Program exec failed: FileNotFoundError:' in (root / 'stderr.log').read_text(encoding='utf-8')
    assert not alive(read_json(root / 'program.json'))


@pytest.mark.skipif(os.name == 'nt', reason='POSIX exec confirmation pipe')
@pytest.mark.parametrize('completion', ['execute', 'cancel', 'signal'])
def test_program_exec_confirmation_excludes_helper_memory_and_remains_cancellable(runtime, completion):
    import psutil
    import signal
    from suan.runtime.worker import terminate_tree
    sleep = shutil.which('sleep')
    if not sleep:
        pytest.skip('requires a native sleep executable')
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('exec confirmation')['id']
    task = client.submit(TaskSpec(workspace, [sleep, '.2'], resources={'memory_mb': 16}))
    root = server.service.task_dir(task['id'])
    copied_worker = root / 'worker.py'
    source = copied_worker.read_text(encoding='utf-8')
    entry = 'if __name__ == "__main__":'
    assert source.count(entry) == 1
    # Hold the actual helper after authorization but before exec, with RSS above
    # the task limit. The native target fits; a monitor started before exec cannot
    # distinguish this wrapper allocation from the program's own memory.
    probe = '''
_original_execvpe = os.execvpe
def delayed_exec(file, argv, env):
    allocation = bytearray(32 * 1024 * 1024)
    for offset in range(0, len(allocation), 4096):
        allocation[offset] = 1
    root = Path.cwd().parent
    write_json(root / 'exec-waiting.json', {'pid': os.getpid()})
    deadline = time.monotonic() + 15
    while not (root / 'release-exec').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('test exec handshake timed out')
        time.sleep(.01)
    return _original_execvpe(file, argv, env)
os.execvpe = delayed_exec

'''
    copied_worker.write_text(source.replace(entry, probe + entry), encoding='utf-8')
    program = wrapper_identity = None
    try:
        supervisor.tick()
        wrapper = psutil.Process(int(client.task(task['id'])['backend_id']))
        wrapper_identity = {'pid': wrapper.pid, 'create_time': wrapper.create_time()}
        deadline = time.monotonic() + 5
        while True:
            witness = read_json(root / 'exec-waiting.json')
            program = read_json(root / 'program.json')
            if witness and program and alive(program):
                break
            assert time.monotonic() < deadline, 'authorized helper did not reach the exec boundary'
            time.sleep(.01)
        assert witness['pid'] == program['pid']
        assert psutil.Process(program['pid']).memory_info().rss > 16 * 1024 * 1024
        # Keep the known oversized helper across several resource-monitor cycles.
        # This delay checks an established barrier; it does not select a crash race.
        time.sleep(.35)
        assert alive(program) and not (root / 'finished.json').exists()
        if completion == 'execute':
            (root / 'release-exec').touch()
        elif completion == 'cancel':
            client.cancel(task['id'])
        else:
            os.kill(wrapper.pid, signal.SIGTERM)
        result = finish(client, supervisor, task['id'])
        expected = {'execute': ('succeeded', ''), 'cancel': ('cancelled', 'Cancelled by user'),
                    'signal': ('failed', 'Worker interrupted by signal')}
        assert (result['state'], result['reason']) == expected[completion]
        assert not alive(program)
        if completion == 'execute':
            assert result['exit_code'] == 0
        else:
            assert not (root / 'release-exec').exists()
    finally:
        client.cancel(task['id'])
        for identity in (program, wrapper_identity):
            if alive(identity):
                terminate_tree(psutil.Process(identity['pid']), expected_created=identity['create_time'])
        (root / 'release-exec').touch()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX isolated program bootstrap')
@pytest.mark.parametrize('variable', ['PYTHONHOME', 'PYTHONPATH'])
def test_native_program_environment_does_not_initialize_the_helper(runtime, tmp_path, variable):
    sleep = shutil.which('sleep')
    if not sleep:
        pytest.skip('requires a native sleep executable')
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('native environment')['id']
    (tmp_path / 'sitecustomize.py').write_text(
        "from pathlib import Path; Path('site-executed').write_text('yes')", encoding='utf-8')
    value = str(tmp_path / 'not-a-python-home') if variable == 'PYTHONHOME' else str(tmp_path)
    task = client.submit(TaskSpec(workspace, [sleep, '.1'], env={variable: value}))
    result = finish(client, supervisor, task['id'])
    assert result['state'] == 'succeeded' and result['exit_code'] == 0
    assert not (server.service.task_dir(task['id']) / 'work' / 'site-executed').exists()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX isolated program bootstrap')
def test_python_target_receives_its_environment_only_after_identity_publication(runtime, tmp_path):
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('authorized Python environment')['id']
    (tmp_path / 'sitecustomize.py').write_text(
        "import json, os; from pathlib import Path; root = Path.cwd().parent; "
        "identity = json.loads((root / 'program.json').read_text()); "
        "assert identity['pid'] == os.getpid(); "
        "Path('site-executed').write_text('identity published')", encoding='utf-8')
    task = client.submit(TaskSpec(workspace, ['{python}', '-c', "print('ready', flush=True)"],
                                  env={'PYTHONPATH': str(tmp_path)}))
    result = finish(client, supervisor, task['id'])
    assert result['state'] == 'succeeded'
    assert client.logs(task['id'])['bytes'] == b'ready\n'
    assert (server.service.task_dir(task['id']) / 'work' / 'site-executed').read_text() == 'identity published'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX signal inheritance')
def test_native_program_restores_sigpipe_default_after_helper(runtime):
    import signal
    shell = shutil.which('sh')
    if not shell:
        pytest.skip('requires a native shell executable')
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace('native signal inheritance')['id']
    task = client.submit(TaskSpec(workspace, [shell, '-c', 'kill -PIPE $$; echo continued > after-pipe']))
    result = finish(client, supervisor, task['id'])
    assert result['state'] == 'failed' and result['exit_code'] == -signal.SIGPIPE
    assert not (server.service.task_dir(task['id']) / 'work' / 'after-pipe').exists()


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
