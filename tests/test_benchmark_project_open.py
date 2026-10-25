"""Benchmark protocol failures clean up real children without invoking a display or GPU."""
import importlib.util
import errno
import json
import os
from pathlib import Path
import subprocess
import signal
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("opening_benchmark", ROOT / "tools/benchmark_project_open.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux pidfd process-tree cleanup")
def test_failed_native_protocol_stops_a_separate_session_and_preserves_diagnostics(tmp_path):
    program = tmp_path / "native"
    program.write_text(f"#!{sys.executable}\n" + '''
import json, os, subprocess, sys, time
from pathlib import Path
control = Path(sys.argv[3])
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
(control / 'child.json').write_text(json.dumps({'pid': child.pid}))
print(json.dumps({'event': 'ready', 'bridge_pid': child.pid}), flush=True)
sys.stdin.readline()
print(json.dumps({'event': 'result', 'ok': False, 'error': 'fixture failure'}), flush=True)
time.sleep(30)
''')
    program.chmod(0o700)
    control, artifacts = tmp_path / "control", tmp_path / "artifacts"
    with pytest.raises(RuntimeError, match="fixture failure"):
        benchmark.measure(program, tmp_path / "unused_wrapper", tmp_path / "unused_project", control,
                          False, 1, artifacts_dir=artifacts)
    pid = json.loads((control / "child.json").read_text())["pid"]
    status = Path(f"/proc/{pid}/stat")
    assert not status.exists() or status.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    assert "fixture failure" in (artifacts / "stdout.log").read_text()
    assert (artifacts / "stderr.log").is_file()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux pidfd process identity")
def test_cleanup_rejects_an_unrelated_parent_identity():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with pytest.raises(ProcessLookupError):
            benchmark._cleanup._Process(child.pid, os.getpid() + 1)
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()


@pytest.mark.parametrize("failure", ["missing_api", "unsupported_kernel", "permission_denied"])
@pytest.mark.parametrize("runner", ["display", "benchmark"])
def test_missing_cleanup_capability_refuses_to_start_the_command(tmp_path, monkeypatch, runner, failure):
    # Exercise both real entrypoints. If the preflight regresses, Popen really executes a marker
    # command; the recorded children are always reaped before this test reports the regression.
    started = tmp_path / "started"
    program = tmp_path / "command"
    program.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(started)!r}).touch()\n")
    program.chmod(0o700)
    opened = []
    original = subprocess.Popen

    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        opened.append(child)
        return child

    def denied(*args, **kwargs):
        raise PermissionError(errno.EPERM, "pidfd operation denied by test policy")

    def unsupported(*args, **kwargs):
        raise OSError(errno.ENOSYS, "pidfd operation unsupported by test kernel")

    monkeypatch.setattr(subprocess, "Popen", spawn)
    if failure == "missing_api":
        monkeypatch.delattr(os, "pidfd_open", raising=False)
    elif failure == "unsupported_kernel":
        monkeypatch.setattr(os, "pidfd_open", unsupported, raising=False)
    else:
        monkeypatch.setattr(signal, "pidfd_send_signal", denied, raising=False)
    try:
        with pytest.raises(RuntimeError, match="pidfd"):
            if runner == "display":
                monkeypatch.syspath_prepend(str(ROOT / "desktop/tests/wm"))
                display_spec = importlib.util.spec_from_file_location("display_capability_test", ROOT / "desktop/tests/wm/run_with_display.py")
                display = importlib.util.module_from_spec(display_spec)
                display_spec.loader.exec_module(display)
                display.run_command([sys.executable, str(program)], dict(os.environ), 1)
            else:
                benchmark.measure(program, tmp_path / "wrapper", tmp_path / "project", tmp_path / "control", False, 1)
        assert opened == [] and not started.exists()
    finally:
        for child in opened:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
