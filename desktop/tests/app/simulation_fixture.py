"""Owned loopback Runtime for native workflow tests; fake SDK by default, real SDK only by opt-in.

Run as a script, this module is instead a strict bridge that logs collected-result lookups (see lookup_bridge).
"""
import atexit
import json
import os
from pathlib import Path
import sys
import threading
import time

from suan.runtime.client import RuntimeClient
from suan.runtime.common import atomic_json, init_config
from suan.runtime.models import TERMINAL
from suan.runtime.server import RuntimeHTTPServer
from suan.runtime.supervisor import Supervisor


class SimulationRuntime:
    def __init__(self, directory, hdf5=False):
        self.root = Path(directory)
        self.root.mkdir(parents=True)
        prefix = os.environ.get('STK_TEST_MUPRO_PREFIX')
        if prefix and hdf5:
            raise ValueError('The synthetic run.h5 is written only by the fake MuFerro SDK')
        if not prefix:
            sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
            from mupro_fake import make_fake_sdk
            prefix = str(make_fake_sdk(self.root / 'sdk', **({'steps': 4} if hdf5 else {})))
            if hdf5:
                self._write_hdf5(Path(prefix))
            for name in ('STK_MUPRO_ENV_SCRIPTS', 'MUPROROOT'):
                os.environ.pop(name, None)
        # This helper lives only in the test's disposable, trusted Python worker.
        os.environ['MUPRO_SDK_PREFIX'] = prefix
        for name in ('STK_MUPRO_ALLOW_LOCAL_MPI', 'SLURM_JOB_ID', 'PBS_JOBID'):
            os.environ.pop(name, None)
        self.source = str(Path(prefix) / 'share/mupro/skills/mupro-muferro/examples')
        self._start()

    def _write_hdf5(self, sdk):
        """Let the fake solver also leave a small synthetic vector and scalar run.h5 in its case."""
        import h5py
        import numpy as np
        sidecar = self.root / 'synthetic-run.h5'
        polar = np.arange(72, dtype=np.uint64).reshape(4, 3, 2, 3)
        polar[2, 1, 0, 0] = 9223372036854775931
        with h5py.File(sidecar, 'w') as file:
            file.create_dataset('t00000002/Polar', data=polar)
            file.create_dataset('t00000004/Polar', data=polar + 100)
            file.create_dataset('t00000002/Scalar', data=np.arange(24, dtype=np.float32).reshape(4, 3, 2, 1))
        program = sdk / 'bin/muFerro'
        solver = program.read_text()
        needle = "sys.exit(fake_muferro('ok'))"
        assert solver.count(needle) == 1
        program.write_text(solver.replace(needle, "result = fake_muferro('ok')\nimport shutil\n"
                           f"shutil.copyfile({str(sidecar)!r}, 'run.h5')\nsys.exit(result)"))

    def _start(self):
        (self.root / 'source.txt').write_text(self.source, encoding='utf-8')
        self.config = init_config(self.root / 'state', self.root / 'shared', port=0)
        self.config['token'] = 'abcdefghijklmnopqrstu'
        self.config['scheduler_interval'] = 0
        atomic_json(self.root / 'state' / 'config.json', self.config)
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


# A real, intentionally short LJ calculation is also understood by the fake
# executable. No PET or molecular-toolkit dependency is needed by native CI.
LAMMPS_SCRIPT = '''# 108 Ar atoms; software-path acceptance, not equilibrated material properties
units real
atom_style atomic
boundary p p p
variable temperature index 300
variable steps index 20
variable timestep index 1
variable seed index 4928459
lattice fcc 4.6
region cell block 0 3 0 3 0 3
create_box 1 cell
create_atoms 1 box
mass 1 39.948
pair_style lj/cut 5.5
pair_coeff 1 1 0.2381 3.405
neighbor 0.3 bin
neigh_modify every 1 delay 0 check yes
timestep ${timestep}
velocity all create ${temperature} ${seed} dist gaussian
fix ensemble all nvt temp ${temperature} ${temperature} 100
thermo 5
thermo_style custom step temp press density pe
thermo_modify format float %.15g
run ${steps}
'''


class LammpsRuntime(SimulationRuntime):
    """Owned loopback Runtime; opt into a real executable with a non-secret path."""
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True)
        program = os.environ.get('STK_TEST_LAMMPS_PROGRAM')
        if program:
            self.program = str(Path(program).resolve(strict=True))
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
            from lammps_fake import make_fake_lammps
            self.program = str(make_fake_lammps(self.root / 'program'))
        source = self.root / 'case'
        source.mkdir()
        (source / 'in.lammps').write_text(LAMMPS_SCRIPT, encoding='utf-8')
        self.source = str(source)
        (self.root / 'program.txt').write_text(self.program, encoding='utf-8')
        self._start()


def lookup_bridge(control):
    """Run the real strict bridge, logging collected MuFerro result lookups and graph requests to control/wire.jsonl.

    While control/refuse-lookup exists, the next lookup (a one-row query of the result table filtered by run) is
    answered with a retryable "unavailable" error instead of its rows, and the file is removed.
    """
    import threading
    from suan.desktop_bridge import server
    from suan.desktop_bridge.__main__ import main
    from suan.desktop_bridge.protocol import decode_line
    from suan.workflows.muferro import RESULT_FIELD_IDS, RESULT_TABLE_ID

    control = Path(control)
    lock = threading.Lock()
    refused = set()

    def record(entry):
        with lock, (control / 'wire.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(entry, sort_keys=True) + '\n')

    class LookupBridge(server.Bridge):
        def handle_line(self, raw):
            try:
                message = decode_line(raw)
            except Exception:  # the real bridge answers malformed lines itself
                message = {}
            params = message.get('params') if isinstance(message.get('params'), dict) else {}
            method = message.get('method')
            entry = {'kind': 'request', 'id': message.get('id'), 'method': method}
            if method == 'project.table.query' and params.get('table_id') == RESULT_TABLE_ID:
                filters = (params.get('definition') or {}).get('filters')
                lookup = params.get('limit') == 1 and isinstance(filters, dict) and \
                    filters.get('field_id') == RESULT_FIELD_IDS['run'] and filters.get('op') == 'eq'
                entry.update(table_id=RESULT_TABLE_ID, lookup=lookup, handle=params.get('handle'),
                             expected_revision=params.get('expected_revision'),
                             run=filters.get('value') if lookup else None)
                with lock:
                    if lookup and (control / 'refuse-lookup').exists():
                        (control / 'refuse-lookup').unlink()
                        refused.add(message.get('id'))
            if method == 'graph.evaluate':
                request = params.get('request') or {}
                nodes = (request.get('graph') or {}).get('nodes', [])
                entry.update(outputs=request.get('outputs'),
                             nodes=[node.get('type') for node in nodes])
                if (request.get('outputs') == ['view'] and len(nodes) >= 2
                        and nodes[0].get('type') == 'stk.source.mupro_hdf5@1'):
                    entry.update(frame_source=nodes[0]['params'], component=nodes[1]['params']['component'])
                if request.get('outputs') == ['source', 'voxel']:
                    entry.update(voxel_source=nodes[0]['params'], component=nodes[1]['params']['component'],
                                 local_proofs=params.get('local_proofs'))
            record(entry)
            return super().handle_line(raw)

        def send(self, message, method=None):
            if method == 'project.table.query' and message.get('id') in refused:
                refused.discard(message['id'])
                message = {'id': message['id'], 'error': {
                    'code': 'unavailable', 'message': 'Fixture transient result lookup failure', 'retryable': True}}
                record({'kind': 'refused', 'id': message['id']})
            elif method == 'project.table.query' and (message.get('result') or {}).get('table_id') == RESULT_TABLE_ID:
                record({'kind': 'reply', 'id': message.get('id'), 'records': len(message['result'].get('records', []))})
            elif method == 'graph.evaluate':
                record({'kind': 'reply', 'id': message.get('id'), 'method': method})
            return super().send(message, method)

    server.Bridge = LookupBridge
    return main()


if __name__ == '__main__':
    raise SystemExit(lookup_bridge(sys.argv.pop(1)))
