from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

from conftest import finish
from suan.runtime.client import RuntimeClient, RuntimeErrorResponse
from suan.runtime.models import TaskSpec
from suan.runtime.common import atomic_json, read_json, sha256
from suan.runtime.supervisor import Supervisor


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
