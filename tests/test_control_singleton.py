"""The supported Hub CLI has one serving owner per canonical state directory."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest
from click.testing import CliRunner

from suan.control.cli import control
from suan.runtime.common import instance_lock

pytestmark = [pytest.mark.server, pytest.mark.skipif(sys.platform != "linux", reason="Hub servers are Linux-only")]
ROOT = Path(__file__).resolve().parents[1]
BUSY = "Control service is already running for this state directory"


@pytest.fixture(autouse=True)
def no_model_configuration(monkeypatch):
    for key in ("STK_MODEL_URL", "STK_MODEL_NAME", "STK_MODEL_KEY", "STK_TOKEN_PLAN_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("STK_TOKEN_PLAN_API_KEY", "")


def state_at(path):
    path.mkdir(mode=0o700)
    # Low-entropy manufactured credential; never a user credential.
    (path / "control.json").write_text(json.dumps({"owner_token": "abcdefghijklmnopqrstuvwxyz"}), encoding="utf-8")
    return path


def child_env():
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "USER") if key in os.environ}
    env.update(PYTHONPATH=str(ROOT), STK_TOKEN_PLAN_API_KEY="", PYTHONDONTWRITEBYTECODE="1")
    return env


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def command(state, port, verb="serve"):
    base = [sys.executable, "-c", "from suan.control.cli import control; control(prog_name='suan-control')",
            verb, "--state-dir", str(state)]
    return base + (["--port", str(port)] if verb == "serve" else ["--role", "client"])


def healthy(port):
    try:
        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/api/v1/health", timeout=0.3) as response:
            return response.status == 200
    except (URLError, TimeoutError, OSError):
        return False


@contextmanager
def process(state, port, log):
    with log.open("wb") as stream:
        child = subprocess.Popen(command(state, port), env=child_env(), cwd=state.parent,
                                 stdout=stream, stderr=stream, start_new_session=True)
        try:
            yield child
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(5)
                except subprocess.TimeoutExpired:
                    child.kill()
            child.wait(5)


def ready(child, port):
    deadline = time.monotonic() + 15
    while child.poll() is None and time.monotonic() < deadline:
        if healthy(port):
            return
        time.sleep(0.05)
    pytest.fail("The owned Hub did not start before the deadline")


@pytest.mark.parametrize("signal_name", ["SIGTERM", "SIGKILL"])
def test_second_hub_is_refused_through_an_alias_and_crash_releases_the_same_lock(tmp_path, signal_name):
    # Resolve Linux-only signals after collection and the platform skip.
    exit_signal = getattr(signal, signal_name)
    state = state_at(tmp_path / "state")
    alias = tmp_path / "alias"
    alias.symlink_to(state, target_is_directory=True)
    port = free_port()
    with process(state, port, tmp_path / "first.log") as first:
        ready(first, port)
        with process(alias, free_port(), tmp_path / "second.log") as second:
            try:
                assert second.wait(4) == 1
            except subprocess.TimeoutExpired:
                pytest.fail("A second Hub with the same state remained running on another port")
        assert BUSY in (tmp_path / "second.log").read_text()
        assert first.poll() is None and healthy(port)
        lock = state / "control.lock"
        inode = lock.stat().st_ino
        # The owner can still issue a pairing while the serving lifecycle owns its separate lock.
        paired = subprocess.run(command(state, port, "pair"), env=child_env(), cwd=tmp_path,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5)
        assert paired.returncode == 0
        first.send_signal(exit_signal)
        first.wait(5)
        assert lock.stat().st_ino == inode  # no unlink/replace, including after a crash
        with process(alias, port, tmp_path / "restarted.log") as restarted:
            ready(restarted, port)
            assert lock.stat().st_ino == inode


def test_independent_state_directories_can_both_serve(tmp_path):
    a, b = state_at(tmp_path / "a"), state_at(tmp_path / "b")
    port_a = free_port()
    with process(a, port_a, tmp_path / "a.log") as first:
        ready(first, port_a)
        port_b = free_port()
        with process(b, port_b, tmp_path / "b.log") as second:
            ready(second, port_b)
            assert first.poll() is None and healthy(port_a)


def test_contention_fails_before_configuration_or_database_construction(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "control.json").write_text("not JSON")
    with instance_lock(state / "control.lock"):
        result = CliRunner().invoke(control, ["serve", "--state-dir", str(state)])
    assert result.exit_code == 1 and BUSY in result.output
    assert not (state / "control.sqlite3").exists()


@pytest.mark.parametrize("outcome,exit_code", [(None, 0), (RuntimeError("manufactured serving failure"), 1),
                                               (BlockingIOError("manufactured serving failure"), 1),
                                               (SystemExit(6), 6), (KeyboardInterrupt(), 1)])
def test_serve_return_or_exception_releases_the_lock_without_relabelling(tmp_path, monkeypatch, outcome, exit_code):
    state = state_at(tmp_path / "state")
    held = []

    def serve(*args, **kwargs):
        with pytest.raises(BlockingIOError):
            with instance_lock(state / "control.lock"):
                pytest.fail("The service did not hold its lifetime lock")
        held.append(True)
        if outcome is not None:
            raise outcome

    monkeypatch.setattr("uvicorn.run", serve)
    result = CliRunner().invoke(control, ["serve", "--state-dir", str(state)])
    assert held == [True]
    assert result.exit_code == exit_code and BUSY not in result.output
    if isinstance(outcome, (RuntimeError, BlockingIOError)):
        assert result.exception is outcome
    with instance_lock(state / "control.lock"):
        assert (state / "control.lock").is_file()


@pytest.mark.parametrize("phase", ["configuration", "application"])
def test_startup_failure_releases_the_lock(tmp_path, phase):
    state = state_at(tmp_path / "state")
    (state / "control.json").write_text("not JSON" if phase == "configuration" else
                                       json.dumps({"owner_token": "short"}), encoding="utf-8")
    result = CliRunner().invoke(control, ["serve", "--state-dir", str(state)])
    assert result.exit_code == 1 and isinstance(result.exception, ValueError) and BUSY not in result.output
    assert (state / "control.lock").is_file()
    with instance_lock(state / "control.lock"):
        pass
