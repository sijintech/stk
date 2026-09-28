"""Owned loopback Runtime for native workflow tests; fake SDK by default, real SDK only by opt-in."""
import atexit
import os
from pathlib import Path
import sys
import threading
import time

from suan.runtime.client import RuntimeClient
from suan.runtime.common import init_config
from suan.runtime.models import TERMINAL
from suan.runtime.server import RuntimeHTTPServer
from suan.runtime.supervisor import Supervisor


class SimulationRuntime:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True)
        prefix = os.environ.get('STK_TEST_MUPRO_PREFIX')
        if not prefix:
            sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
            from mupro_fake import make_fake_sdk
            prefix = str(make_fake_sdk(self.root / 'sdk'))
            for name in ('STK_MUPRO_ENV_SCRIPTS', 'MUPROROOT'):
                os.environ.pop(name, None)
        # This helper lives only in the test's disposable, trusted Python worker.
        os.environ['MUPRO_SDK_PREFIX'] = prefix
        for name in ('STK_MUPRO_ALLOW_LOCAL_MPI', 'SLURM_JOB_ID', 'PBS_JOBID'):
            os.environ.pop(name, None)
        self.source = str(Path(prefix) / 'share/mupro/skills/mupro-muferro/examples')
        (self.root / 'source.txt').write_text(self.source, encoding='utf-8')
        self.config = init_config(self.root / 'state', self.root / 'shared', port=0)
        self.config['scheduler_interval'] = 0
        self.server = RuntimeHTTPServer(self.config)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.client = RuntimeClient(self.url, self.config['token'])
        self.supervisor = Supervisor(self.config)
        self.stop = threading.Event()
        self.closed = False
        self.http = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        self.scheduler = threading.Thread(target=self._tick, daemon=True)
        self.http.start()
        self.scheduler.start()
        atexit.register(self.close)

    def _tick(self):
        while not self.stop.wait(.025):
            self.supervisor.tick()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            for task in self.client.tasks():
                if task['state'] not in TERMINAL:
                    self.client.cancel(task['id'])
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if all(task['state'] in TERMINAL for task in self.client.tasks()):
                    break
                time.sleep(.05)
        finally:
            self.stop.set()
            self.scheduler.join(5)
            self.server.shutdown()
            self.server.server_close()
            self.http.join(5)
