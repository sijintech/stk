"""Managed tunnel lifecycle, transport and bridge contracts (no external SSH hosts)."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import getpass
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

import pytest
import psutil

from suan.runtime import ssh
from suan.runtime.ssh import SSHError, Tunnel, TunnelManager, validate_ssh
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.fixture
def endpoint():
    class Handler(BaseHTTPRequestHandler):
        calls = []

        def do_GET(self):
            self.calls.append((self.path, self.headers.get("Authorization")))
            body = json.dumps({"ok": True, "api_version": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.calls.append((self.path, self.headers.get("Authorization")))
            self.connection.shutdown(socket.SHUT_RDWR)  # lost response must never replay a mutation
            self.connection.close()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"url": f"http://127.0.0.1:{server.server_port}", "token": "private-test-token",
           "ssh": {"host": "test-cluster"}}, Handler.calls
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def fake_ssh(tmp_path, monkeypatch):
    script = tmp_path / "fake_ssh.py"
    script.write_text('''import os, socket, sys, threading, time
mode = os.environ.get("STK_TEST_SSH_MODE", "forward")
if mode == "fail":
    sys.stderr.write("Permission denied (publickey).\\n")
    sys.exit(255)
if mode == "hang":
    time.sleep(60)
args = sys.argv[1:]
host, port, target, remote = args[args.index("-L") + 1].split(":")
server = socket.socket()
server.bind((host, int(port)))
server.listen()
sys.stderr.write("debug1: Entering interactive session.\\n")
sys.stderr.flush()
def copy(source, destination):
    try:
        while True:
            data = source.recv(65536)
            if not data: break
            destination.sendall(data)
    except OSError: pass
    finally:
        try: destination.shutdown(socket.SHUT_WR)
        except OSError: pass
def forward(client):
    try:
        upstream = socket.create_connection((target, int(remote)))
        worker = threading.Thread(target=copy, args=(client, upstream))
        worker.start()
        copy(upstream, client)
        worker.join()
        upstream.close()
    except OSError: pass
    finally: client.close()
while True:
    client, address = server.accept()
    threading.Thread(target=forward, args=(client,), daemon=True).start()
''')
    original = ssh._launch
    calls = []

    def launch(command, env, options):
        calls.append(list(command))
        return original([sys.executable, str(script), *command[1:]], env, options)

    monkeypatch.setattr(ssh.shutil, "which", lambda name: "ssh-test")
    monkeypatch.setattr(ssh, "_launch", launch)
    return calls


@pytest.mark.parametrize("url,config", [
    ("http://example.com:8765", {"host": "cluster"}),
    ("http://localhost", {"host": "cluster"}),
    ("http://localhost:0", {"host": "cluster"}),
    ("http://localhost:8765", {"host": "-oProxyCommand=bad"}),
    ("http://localhost:8765", {"host": "host; command"}),
    ("http://localhost:8765", {"host": "host", "command": "bad"}),
])
def test_invalid_configuration(url, config):
    with pytest.raises(ValueError):
        validate_ssh(url, config)


def test_shared_tunnel_reconnect_disconnect_and_replacement(endpoint, fake_ssh):
    config, calls = endpoint
    manager = TunnelManager()
    try:
        clients = [manager.client("cluster", config) for _ in range(6)]
        assert len({id(c.tunnel) for c in clients}) == 1
        assert clients[0].tunnel.status()["state"] == "stopped"
        with ThreadPoolExecutor(6) as pool:
            assert all(pool.map(lambda c: c.health()["ok"], clients))
        assert len(fake_ssh) == 1
        assert len(calls) == 6 and all(token == "Bearer private-test-token" for _, token in calls)
        command = fake_ssh[0]
        assert "private-test-token" not in " ".join(command)
        assert "BatchMode=yes" in command and "StrictHostKeyChecking=yes" in command
        client = clients[0]
        process = client.tunnel.process
        for child in psutil.Process(process.pid).children():
            child.kill()
        process.wait(timeout=5)
        assert client.tunnel.status()["state"] == "failed"
        assert client.health()["ok"] and len(fake_ssh) == 2
        client.tunnel.disconnect()
        with pytest.raises(SSHError, match="explicitly reconnect"):
            client.health()
        assert len(fake_ssh) == 2
        client.tunnel.endpoint(reconnect=True)
        assert client.health()["ok"] and len(fake_ssh) == 3
        replacement = manager.client("cluster", dict(config, token="new-token"))
        with pytest.raises(SSHError, match="removed or replaced"):
            client.health()
        assert replacement.health()["ok"]
        assert calls[-1][1] == "Bearer new-token"
        direct = manager.client("cluster", {k: v for k, v in config.items() if k != "ssh"})
        assert direct.health()["ok"]
        assert replacement.tunnel.status()["state"] == "stopped"
    finally:
        manager.close()


def test_failed_start_bounded_timeout_and_no_request_replay(endpoint, fake_ssh, monkeypatch):
    config, calls = endpoint
    tunnel = Tunnel(config["url"], config["ssh"], timeout=0.3)
    try:
        monkeypatch.setenv("STK_TEST_SSH_MODE", "fail")
        with pytest.raises(SSHError, match="Permission denied"):
            tunnel.endpoint()
        assert tunnel.status()["state"] == "failed"
        with pytest.raises(SSHError):
            tunnel.endpoint()
        assert len(fake_ssh) == 1  # failed polling backs off
        monkeypatch.setenv("STK_TEST_SSH_MODE", "hang")
        with pytest.raises(SSHError, match="timed out"):
            tunnel.endpoint(reconnect=True)
        assert tunnel.process is None
    finally:
        tunnel.disconnect(permanent=True)
    monkeypatch.delenv("STK_TEST_SSH_MODE")
    manager = TunnelManager()
    try:
        client = manager.client("cluster", config)
        with pytest.raises(Exception):
            client.request("POST", "tasks", {"test": True})
        assert [path for path, _ in calls].count("/v1/tasks") == 1
    finally:
        manager.close()


def test_bridge_manages_profile_without_exposing_token(inproc, endpoint, fake_ssh):
    config, _ = endpoint
    harness = inproc()
    result = harness.call("connections.add_runtime", dict(name="cluster", check=False, **config))
    assert result["connection"]["ssh"]["state"] == "stopped"
    assert not fake_ssh
    params = {"id": "runtime:cluster", "action": "connect"}
    assert harness.call("connections.ssh", params)["ssh"]["state"] == "ready"
    assert harness.call("connections.check", {"id": "runtime:cluster"})["ok"]
    params["action"] = "disconnect"
    assert harness.call("connections.ssh", params)["ssh"]["state"] == "stopped"
    assert not harness.call("connections.check", {"id": "runtime:cluster"})["ok"]
    assert config["token"] not in b"".join(harness.lines).decode()
    assert harness.call("connections.remove", {"id": "runtime:cluster"})["removed"] == "runtime:cluster"
    assert not harness.violations


@pytest.fixture
def real_ssh(tmp_path, monkeypatch):
    """Disposable local sshd, keys/config/known_hosts only inside pytest's private directory."""
    sshd = shutil.which("sshd")
    keygen = shutil.which("ssh-keygen")
    if sys.platform != "linux" or not sshd or not keygen or not shutil.which("ssh"):
        if os.environ.get("STK_REQUIRE_SSH_TEST") == "1":
            pytest.fail("Required local OpenSSH integration prerequisites are missing")
        pytest.skip("local OpenSSH integration needs Linux ssh, sshd and ssh-keygen")
    root = tmp_path / "ssh"
    root.mkdir(mode=0o700)
    host_key, client_key = root / "host", root / "client"
    for key in (host_key, client_key):
        subprocess.run([keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = root / "sshd_config"
    config.write_text(f'''Port {port}
ListenAddress 127.0.0.1
HostKey {host_key}
PidFile {root / "pid"}
AuthorizedKeysFile {client_key}.pub
StrictModes no
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM yes
AllowTcpForwarding local
PermitRootLogin yes
''')
    known_hosts = root / "known_hosts"
    public_key = host_key.with_suffix(".pub").read_text().split()
    known_hosts.write_text(f"[127.0.0.1]:{port} {public_key[0]} {public_key[1]}\n")
    client_config = root / "ssh_config"
    client_config.write_text(f'''Host test-cluster
  HostName 127.0.0.1
  Port {port}
  User {getpass.getuser()}
  IdentityFile {client_key}
  IdentitiesOnly yes
  UserKnownHostsFile {known_hosts}
  GlobalKnownHostsFile /dev/null
''')
    original = subprocess.Popen
    with (root / "server.log").open("wb") as log:
        process = original([sshd, "-D", "-e", "-f", str(config)], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 5
            while True:
                assert process.poll() is None, (root / "server.log").read_text()
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    assert time.monotonic() < deadline
                    time.sleep(0.02)

            launch = ssh._launch

            def configured_launch(command, env, options):
                return launch([command[0], "-F", str(client_config), *command[1:]], env, options)

            monkeypatch.setattr(ssh, "_launch", configured_launch)
            yield root
        finally:
            process.terminate()
            process.wait(timeout=5)


def test_real_openssh_runtime_requests_and_host_verification(real_ssh, endpoint):
    config, calls = endpoint
    manager = TunnelManager()
    try:
        client = manager.client("real", config)
        assert client.health()["ok"]
        process = client.tunnel.process
        assert process.poll() is None
        assert calls == [("/v1/health", "Bearer private-test-token")]
        manager.remove("real")
        assert process.poll() is not None
        (real_ssh / "known_hosts").write_text("")
        client = manager.client("real", config)
        with pytest.raises(SSHError, match="Host key verification failed"):
            client.health()
        assert len(calls) == 1  # no Runtime token sent to an unverified host
    finally:
        manager.close()


def test_guardian_closes_ssh_when_parent_pipe_disappears(endpoint, fake_ssh):
    config, _ = endpoint
    manager = TunnelManager()
    try:
        client = manager.client("cluster", config)
        assert client.health()["ok"]
        guardian = client.tunnel.process
        descendants = psutil.Process(guardian.pid).children(recursive=True)
        assert descendants
        guardian.stdin.close()  # identical EOF when the desktop bridge crashes
        guardian.wait(timeout=5)
        # Windows can retain descendant PIDs briefly after process termination (including
        # venv redirectors). Wait for the whole tree instead of sampling is_running once.
        _, alive = psutil.wait_procs(descendants, timeout=5)
        assert not alive, [child.pid for child in alive]
    finally:
        manager.close()


def test_unrelated_listener_is_not_mistaken_for_authenticated_ssh(endpoint, fake_ssh, monkeypatch):
    config, _ = endpoint
    original = ssh._launch
    listener = socket.socket()

    def occupied(command, env, options):
        port = int(command[command.index("-L") + 1].split(":")[1])
        listener.bind(("127.0.0.1", port))
        listener.listen()
        listener.setblocking(False)
        return original(command, dict(env, STK_TEST_SSH_MODE="hang"), options)

    monkeypatch.setattr(ssh, "_launch", occupied)
    tunnel = Tunnel(config["url"], config["ssh"], timeout=0.4)
    try:
        with pytest.raises(SSHError, match="timed out"):
            tunnel.endpoint()
        with pytest.raises(BlockingIOError):
            listener.accept()  # no connection/token to the port's unrelated owner
    finally:
        tunnel.disconnect(permanent=True)
        listener.close()


def test_cli_saves_and_uses_ssh_profile(endpoint, fake_ssh, bridge_env, tmp_path):
    from click.testing import CliRunner
    from suan.runtime.cli import connect, get_client, profiles_path
    config, _ = endpoint
    token_file = tmp_path / "token"
    token_file.write_text(config["token"])
    runner = CliRunner()
    result = runner.invoke(connect, ["add", "cluster", "--ssh-host", "test-cluster", "--url", config["url"],
                                     "--token-file", str(token_file)])
    assert result.exit_code == 0, result.output
    profiles = json.loads(profiles_path().read_text())
    assert profiles["cluster"] == config
    listing = runner.invoke(connect, ["list"])
    assert listing.exit_code == 0
    assert config["token"] not in listing.output
    assert json.loads(listing.output)["cluster"]["ssh"] == config["ssh"]
    client = get_client("cluster")
    try:
        assert client.health()["ok"]
    finally:
        ssh._default_manager.remove(str(profiles_path().absolute()) + ":cluster")


def test_failed_candidate_preserves_existing_connection(inproc, endpoint, fake_ssh, monkeypatch):
    config, _ = endpoint
    harness = inproc()
    harness.call("connections.add_runtime", dict(name="cluster", check=False, **config))
    harness.call("connections.ssh", {"id": "runtime:cluster", "action": "connect"})
    old = harness.bridge.connections.runtime_client("runtime:cluster")
    identity = old.connection_identity
    process = old.tunnel.process
    monkeypatch.setenv("STK_TEST_SSH_MODE", "fail")
    result = harness.error("connections.add_runtime", dict(name="cluster", **dict(config, token="different")))
    assert result["code"] == "unavailable"
    assert old.tunnel.process is process and process.poll() is None
    assert old.health()["ok"]
    assert old.connection_identity == identity
    assert harness.error("connections.ssh", {"id": "local", "action": "status"})["code"] == "invalid_params"


def test_missing_openssh_has_actionable_status(endpoint, monkeypatch):
    config, _ = endpoint
    monkeypatch.setattr(ssh.shutil, "which", lambda name: None)
    tunnel = Tunnel(config["url"], config["ssh"])
    with pytest.raises(SSHError, match="PATH"):
        tunnel.endpoint()
    assert tunnel.status()["state"] == "failed"
    assert "ssh" in tunnel.status()["error"]


def test_real_openssh_runtime_job_survives_disconnect(real_ssh, runtime, tmp_path):
    from conftest import finish
    direct, supervisor, _, config = runtime
    profile = {"url": direct.url, "token": config["token"], "ssh": {"host": "test-cluster"}}
    manager = TunnelManager()
    try:
        client = manager.client("cluster", profile)
        workspace = client.create_workspace("SSH integration")["id"]
        source = tmp_path / "input.txt"
        source.write_text("远程输入\n", encoding="utf-8")
        client.upload(workspace, source)
        task = client.submit({"workspace_id": workspace, "argv": [sys.executable, "-c",
                              "from pathlib import Path; Path('output.txt').write_text(Path('input.txt').read_text())"]})
        supervisor.tick()
        manager.close()
        assert finish(direct, supervisor, task["id"])["state"] == "succeeded"
        manager = TunnelManager()
        client = manager.client("cluster", profile)
        destination = tmp_path / "download.txt"
        client.download(task["id"], "output.txt", destination)
        assert destination.read_bytes() == source.read_bytes()
        assert len(client.tasks(workspace)) == 1
    finally:
        manager.close()
