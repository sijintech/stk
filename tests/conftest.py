from pathlib import Path
import os
import sys
import threading
import time

import pytest

from suan.runtime.client import RuntimeClient
from suan.runtime.common import init_config
from suan.runtime.server import RuntimeHTTPServer
from suan.runtime.supervisor import Supervisor


@pytest.hookimpl(tryfirst=True)  # before -m deselection reads the markers
def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason='STK server Runtime is Linux-only; this platform runs client tests')
    for item in items:
        if {'runtime', 'deployed'} & set(getattr(item, 'fixturenames', ())):
            item.add_marker(pytest.mark.server)
        if not sys.platform.startswith('linux') and item.get_closest_marker('server'):
            item.add_marker(skip)


@pytest.fixture(autouse=True, scope='session')
def _private_graph_cache(tmp_path_factory):
    """`suan graph run` defaults to the user cache directory; tests never write there."""
    previous = os.environ.get('STK_GRAPH_CACHE')
    os.environ['STK_GRAPH_CACHE'] = str(tmp_path_factory.mktemp('stk-graph-cache'))
    yield
    if previous is None:
        os.environ.pop('STK_GRAPH_CACHE', None)
    else:
        os.environ['STK_GRAPH_CACHE'] = previous


_RENDER_PROBE = {}


def render_probe():
    """Offscreen GL capability, probed once per session in a child process (VTK aborts without EGL/OSMesa)."""
    if not _RENDER_PROBE:
        from suan.graph.cli import probe_offscreen
        _RENDER_PROBE.update(probe_offscreen())
    return dict(_RENDER_PROBE)


def pytest_runtest_setup(item):
    if item.get_closest_marker('render'):
        probe = render_probe()
        if not probe['ok']:
            pytest.skip(f"offscreen rendering unavailable: {probe['reason']}")


@pytest.fixture(scope='session')
def offscreen_probe():
    """``{"ok", "missing", "reason", "returncode"}`` of ``python -m suan.render.offscreen --probe``."""
    return render_probe()


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
