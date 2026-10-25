"""Measure CPU or live-window desktop opening with a real bridge and public data (Linux).

Build stk-project-open-benchmark explicitly, then run with the installed STK Python:
  python tools/benchmark_project_open.py --binary /path/to/bin/stk-project-open-benchmark --rows 10000
The baseline suppresses only the new paging capabilities in hello; both modes use the same
native editors, bridge implementation and SQLite database. No models or simulations run.

For the opt-in stk-project-open-window-benchmark binary, add --gpu-backend opengl|vulkan and
--artifacts-dir DIR. Run this entire driver inside run_with_display.py --size 1440x1200;
wrapping each native process instead would sample the display runner's RSS by mistake.
"""
import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import platform
import queue
import shutil
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from uuid import UUID

from suan.project import ProjectStore


_cleanup_spec = importlib.util.spec_from_file_location(
    "stk_benchmark_process_tree", Path(__file__).resolve().parents[1] / "desktop/tests/wm/process_tree.py")
_cleanup = importlib.util.module_from_spec(_cleanup_spec)
_cleanup_spec.loader.exec_module(_cleanup)


WRAPPER = r'''
import json
import sys
import threading
from pathlib import Path
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
control = Path(sys.argv.pop(1))
legacy = (control / 'legacy').exists()
hello, send = Bridge.hello, Bridge.send
lock = threading.Lock()
def measured_hello(self, params, context):
    result = hello(self, params, context)
    if legacy:
        result['methods'] = [name for name in result['methods'] if name not in {'project.catalog', 'project.table.read'}]
    return result
def measured_send(self, message, method=None):
    if (control / 'measure').exists():
        size = len(json.dumps(message, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')) + 1
        with lock, (control / 'responses.jsonl').open('a') as stream:
            stream.write(json.dumps({'method': method or message.get('event', ''), 'utf8_bytes': size}) + '\n')
    return send(self, message, method)
Bridge.hello, Bridge.send = measured_hello, measured_send
main()
'''


def seed(directory, rows):
    store = ProjectStore.create(directory, 'Public synthetic native opening benchmark')
    serial = 0

    def identity():
        nonlocal serial
        serial += 1
        return str(UUID(int=serial))

    # Fixture creation is outside all read timings. No user database is opened.
    with store._connect(write=True) as db:
        for title in ('Synthetic A', 'Synthetic B'):
            table, fields = identity(), [identity() for _ in range(8)]
            db.execute('INSERT INTO tables VALUES (?,?)', (table, title))
            db.executemany('INSERT INTO fields VALUES (?,?,?,?,?)', [
                (field, table, str(index), 'integer' if index == 0 else 'text', None)
                for index, field in enumerate(fields)])
            for index in range(rows):
                record = identity()
                db.execute('INSERT INTO records VALUES (?,?)', (record, table))
                db.executemany('INSERT INTO cells VALUES (?,?,?,?)', [
                    (table, record, field, json.dumps(index if column == 0 else 'synthetic'))
                    for column, field in enumerate(fields)])


def memory(pid):
    """Sample RSS only; never read process environments, command lines or private memory."""
    try:
        values = {}
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith(('VmRSS:', 'VmHWM:')):
                key, value, _ = line.split()
                values[key[:-1]] = int(value) * 1024
        return values.get('VmRSS', 0), values.get('VmHWM', 0)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return 0, 0


def children(pid):
    result = set()
    try:
        for path in Path(f'/proc/{pid}/task').glob('*/children'):
            try:
                result.update(int(value) for value in path.read_text().split())
            except (FileNotFoundError, ProcessLookupError):
                pass
    except (FileNotFoundError, ProcessLookupError):
        pass
    return result


def sample(pid):
    seen, pending = set(), {pid}
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.update(children(current) - seen)
    own, hwm = memory(pid)
    return own, hwm, sum(memory(child)[0] for child in seen)


def measure(binary, wrapper, project, control, legacy, rows, *, gpu_backend=None, artifacts_dir=None):
    _cleanup.require_process_tree_support()
    control.mkdir()
    if artifacts_dir:
        artifacts_dir.mkdir()
    if legacy:
        (control / 'legacy').touch()
    env = dict(os.environ, STK_TOKEN_PLAN_API_KEY='')
    env.pop('STK_TOKEN_PLAN_MODEL', None)
    messages = queue.Queue()
    command = [str(binary), sys.executable, str(wrapper), str(control), str(project)]
    if gpu_backend:
        command.extend(['--gpu-backend', gpu_backend])
    with (control / 'stderr.log').open('w') as errors:
        process = subprocess.Popen(command,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, env=env, start_new_session=True)
        def receive():
            try:
                with (control / 'stdout.log').open('w') as output:
                    for line in process.stdout:
                        output.write(line)
                        output.flush()
                        if gpu_backend:
                            # GHOST/driver diagnostics may use stdout. Only benchmark-prefixed
                            # lines participate in the protocol; retain the other lines as evidence.
                            if not line.startswith('STK_BENCHMARK '):
                                continue
                            line = line.removeprefix('STK_BENCHMARK ')
                        messages.put(json.loads(line))
            except (ValueError, UnicodeError) as exc:
                messages.put({'event': 'protocol_error', 'ok': False, 'error': str(exc)})
            finally:
                messages.put(None)
        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        try:
            ready = messages.get(timeout=90)
            if not ready or ready.get('event') != 'ready':
                raise RuntimeError('Native benchmark did not initialize; inspect the isolated stderr log')
            if gpu_backend and ready.get('measurement_kind') != 'native_window':
                raise RuntimeError('Window benchmark did not identify a real native window')
            baseline = sample(process.pid)
            (control / 'measure').touch()
            process.stdin.write('open\n'); process.stdin.flush()
            peaks = list(baseline)
            deadline = time.monotonic() + 150
            while True:
                peaks = [max(a, b) for a, b in zip(peaks, sample(process.pid))]
                try:
                    result = messages.get(timeout=0.005)
                    break
                except queue.Empty:
                    if time.monotonic() > deadline:
                        raise TimeoutError('Native opening exceeded 150 seconds')
            if gpu_backend and result and result.get('event') == 'measurement_complete' and result.get('ok'):
                opening = result
                # Stop sampling before GPU readback/PNG allocations. Native code waits for this
                # acknowledgment, so evidence collection cannot inflate the opening RSS peak.
                process.stdin.write('capture\n'); process.stdin.flush()
                result = messages.get(timeout=60)
                if not result or any(result.get(key) != value for key, value in opening.items()
                                     if key not in {'event', 'ok'}):
                    raise RuntimeError('Window capture changed the completed opening measurement')
            if not result or result.get('event') != 'result' or not result.get('ok') or process.wait(timeout=30) != 0:
                raise RuntimeError(f'Native opening failed: {result}')
            reader.join(timeout=2)
            if reader.is_alive():
                raise RuntimeError('Native benchmark stdout did not finish after process exit')
            for key, expected in {'tables': 2, 'total_records': 2 * rows, 'first_value': 0,
                                  'project_revision': 0, 'script_runs': 0, 'viewer_evaluations': 0,
                                  'schema_violations': 0, 'protocol_errors': 0, 'restarts': 0}.items():
                assert result[key] == expected, (key, result)
            assert result['shared_loaded_records'] == (2 * rows if legacy else min(rows, 200)), result
            # The existing grid requests 500 rows independently of the 200-row shared cache.
            assert result['visible_rows'] == min(rows, 500), result
            if gpu_backend:
                assert result['measurement_kind'] == 'native_window', result
                assert result['timing_boundary'] == 'post_data_ready_draw_and_swap_release_return', result
                assert result['frames_at_first_visible'] > result['frames_at_data_ready'] >= result['frames_before_open'], result
                assert (result['window_width'], result['window_height'], result['ui_scale']) == (1440, 1200, 1.0), result
                assert result['screenshot_ok'] and (control / 'window.png').is_file(), result
                assert result['gpu_device'] and result['rendering_class'] in {'software', 'unverified'}, result
            responses = [json.loads(line) for line in (control / 'responses.jsonl').read_text().splitlines()]
            result.update(mode='snapshot' if legacy else 'paged', native_rss_before=baseline[0],
                          native_sampled_peak_rss=peaks[0], native_peak_rss_since_start=peaks[1],
                          process_tree_rss_before=baseline[2], process_tree_sampled_peak_rss=peaks[2],
                          response_utf8_bytes=sum(item['utf8_bytes'] for item in responses),
                          response_methods=dict(Counter(item['method'] for item in responses)))
            if artifacts_dir:
                if gpu_backend:
                    result['screenshot'] = str(artifacts_dir / 'window.png')
                (artifacts_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            return result
        finally:
            try:
                _cleanup.stop_process_tree(process)
            finally:
                reader.join(timeout=2)
                if artifacts_dir:
                    # Preserve diagnostics on failed measurements too. Never copy bridge state,
                    # profiles, display authorization files or project files into public evidence.
                    for filename in ('stdout.log', 'stderr.log', 'responses.jsonl', 'window.png'):
                        source = control / filename
                        if source.is_file():
                            shutil.copyfile(source, artifacts_dir / filename)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=10000)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--gpu-backend', choices=('opengl', 'vulkan'),
                        help='use the live-window binary; omitted preserves the CPU fixture protocol')
    parser.add_argument('--artifacts-dir', type=Path,
                        help='new evidence directory for per-run logs, screenshots and combined report')
    args = parser.parse_args()
    if not sys.platform.startswith('linux') or not args.binary.is_file() or not 1 <= args.rows <= 10000 or not 1 <= args.repeat <= 10:
        parser.error('Requires Linux, a built binary, 1–10000 rows per table and 1–10 repetitions')
    if args.gpu_backend and args.artifacts_dir is None:
        parser.error('Window measurements require --artifacts-dir so screenshots survive fixture cleanup')
    if args.artifacts_dir:
        args.artifacts_dir = args.artifacts_dir.resolve()
        if args.artifacts_dir.exists():
            parser.error('--artifacts-dir must name a new directory; existing evidence is never overwritten')
        args.artifacts_dir.mkdir(parents=True)
    with TemporaryDirectory(prefix='stk-native-open-') as temporary:
        root = Path(temporary)
        seed(root / 'project', args.rows)
        wrapper = root / 'bridge.py'; wrapper.write_text(WRAPPER)
        results = []
        for iteration in range(args.repeat):
            for legacy in ((True, False) if iteration % 2 == 0 else (False, True)):
                results.append(measure(args.binary.resolve(), wrapper, root / 'project',
                                       root / f'{iteration}-{legacy}', legacy, args.rows,
                                       gpu_backend=args.gpu_backend,
                                       artifacts_dir=(args.artifacts_dir / f'{iteration}-{"snapshot" if legacy else "paged"}'
                                                      if args.artifacts_dir else None)))
        fields = ('first_visible_seconds', 'native_sampled_peak_rss', 'process_tree_sampled_peak_rss', 'response_utf8_bytes')
        summary = {mode: {field: statistics.median(r[field] for r in results if r['mode'] == mode) for field in fields}
                   for mode in ('snapshot', 'paged')}
        limits = ('Native GHOST window with real fonts and the recorded GPU device; timing_boundary is '
                  'post_data_ready_draw_and_swap_release_return: drawing and the swap-release call have returned '
                  'after observing a data-ready grid, including one explicit redraw. This proves neither successful '
                  'presentation nor scan-out timing. '
                  'Screenshot readback re-renders the window offscreen after opening timing/RSS sampling; '
                  'unrecognized device strings do not prove hardware acceleration. '
                  if args.gpu_backend else 'CPU UI with fake text measurement, no GPU/native window/IME; ')
        limits += ('Warm OS caches; excludes bridge/display startup. RSS sums shared pages and is sampled every ~5 ms; '
                   'response bytes use compact UTF-8 JSON through bridge closure, including any later UI metadata responses.')
        report = {'python': platform.python_version(), 'platform': platform.platform(),
                          'rows_per_table': args.rows, 'fields_per_table': 8, 'layout': 'default 1440x1200 en 1x',
                          'measurement_kind': 'native_window' if args.gpu_backend else 'cpu_fixture',
                          'limits': limits, 'runs': results, 'medians': summary}
        if args.artifacts_dir:
            (args.artifacts_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
