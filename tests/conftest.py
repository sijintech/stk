from pathlib import Path
import os
import threading
import time

import pytest

from suan.runtime.client import RuntimeClient
from suan.runtime.common import init_config
from suan.runtime.server import RuntimeHTTPServer
from suan.runtime.supervisor import Supervisor


@pytest.fixture
def runtime(tmp_path):
    config = init_config(tmp_path / 'state', tmp_path / 'shared', port=0)
    config['scheduler_interval'] = 0
    server = RuntimeHTTPServer(config)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = RuntimeClient(f'http://127.0.0.1:{server.server_port}', config['token'])
    supervisor = Supervisor(config)
    yield client, supervisor, server, config
    for task in client.tasks():
        if task['state'] not in {'succeeded', 'failed', 'cancelled'}:
            client.cancel(task['id'])
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        supervisor.tick()
        if all(t['state'] in {'succeeded', 'failed', 'cancelled', 'unknown'} for t in client.tasks()):
            break
        time.sleep(.1)
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def finish(client, supervisor, task_id, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        supervisor.tick()
        record = client.task(task_id)
        if record['state'] in {'succeeded', 'failed', 'cancelled'}:
            return record
        time.sleep(.05)
    raise AssertionError(client.task(task_id))
