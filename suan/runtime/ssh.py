"""Process-owned OpenSSH forwards shared by CLI and desktop connection profiles.

Profiles keep the *remote loopback* URL. Ephemeral local ports and SSH diagnostics
are runtime state only. Requests are never retried here, including after a lost reply.
"""
import atexit
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import psutil

from .client import RuntimeClient
from .ssh_worker import stop_tree


class SSHError(OSError):
    pass


def _launch(command, env, options):
    process = subprocess.Popen([sys.executable, "-m", "suan.runtime.ssh_worker"], stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env, **options)
    try:
        process.stdin.write(json.dumps(command).encode("utf-8") + b"\n")
        process.stdin.flush()
    except OSError:
        process.kill()
        process.wait(timeout=5)
        process.stdin.close()
        process.stderr.close()
        raise
    return process


def validate_ssh(url, config):
    RuntimeClient(url, "validation")
    parsed = urlsplit(url)
    if not isinstance(config, dict) or set(config) != {"host"}:
        raise ValueError("SSH configuration must contain only 'host'")
    host = config["host"]
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,254}", host):
        raise ValueError("Use an SSH Host alias or user@hostname (without spaces or options)")
    port = parsed.port
    if port is None or not 1 <= port <= 65535:
        raise ValueError("An SSH Runtime URL needs an explicit remote port from 1 to 65535")
    # Forward to precisely the loopback address named by the profile, including IPv6.
    destination = "[::1]" if parsed.hostname == "::1" else parsed.hostname
    return host, destination, port


class Tunnel:
    def __init__(self, url, config, *, timeout=15):
        self.host, self.destination, self.remote_port = validate_ssh(url, config)
        self.identity = "ssh:" + self.host + ":" + url.rstrip("/")
        self.timeout = timeout
        self.lock = threading.RLock()
        self.output_lock = threading.Lock()
        self.authenticated = threading.Event()
        self.process = None
        self.tree = None
        self.reader = None
        self.local_port = None
        self.diagnostic = ""
        self.error = ""
        self.disabled = False
        self.closed = False
        self.retry_at = 0

    def status(self):
        with self.lock:
            alive = self.process is not None and self.process.poll() is None
            state = "ready" if alive and self.local_port else "failed" if self.error or self.process else "stopped"
            if self.disabled or self.closed:
                state = "stopped"
            return {"host": self.host, "state": state,
                    "url": f"http://127.0.0.1:{self.local_port}" if state == "ready" else None,
                    "error": self.error or ("SSH process exited; reconnect to retry" if state == "failed" else "")}

    def _read(self, process):
        pending = b""
        try:
            while True:
                chunk = os.read(process.stderr.fileno(), 2048)
                if not chunk:
                    break
                with self.output_lock:
                    self.diagnostic = (self.diagnostic + chunk.decode("utf-8", "replace"))[-4096:]
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    # OpenSSH enters client_loop only after authentication and successful
                    # forwarding setup (ExitOnForwardFailure). A TCP listener alone could
                    # belong to somebody who took the released ephemeral port during login.
                    if line.strip() == b"debug1: Entering interactive session.":
                        self.authenticated.set()
                pending = pending[-4096:]
        except (OSError, ValueError):
            pass

    def _stop(self):
        process = self.process
        if process is None:
            return
        process.stdin.close()
        try:
            process.wait(timeout=1.5)  # guardian normally reaps SSH on parent EOF
        except subprocess.TimeoutExpired:
            stop_tree(process, self.tree)
        if self.reader:
            self.reader.join(timeout=1)
        process.stderr.close()
        process.stdin.close()
        self.process = None
        self.tree = None
        self.local_port = None

    def disconnect(self, *, permanent=False):
        with self.lock:
            self.disabled = True
            self.closed = self.closed or permanent
            self._stop()
            self.error = ""

    def endpoint(self, *, reconnect=False):
        with self.lock:
            if self.closed:
                raise SSHError("This SSH connection was removed or replaced")
            if reconnect:
                self.disabled = False
                self.retry_at = 0
            if self.disabled:
                raise SSHError("SSH is disconnected; explicitly reconnect before using this profile")
            if self.process is not None and self.process.poll() is None:
                return f"http://127.0.0.1:{self.local_port}"
            if time.monotonic() < self.retry_at:
                raise SSHError(self.error)
            self._stop()
            executable = shutil.which("ssh")
            if not executable:
                self.error = "OpenSSH client 'ssh' was not found on PATH"
                self.retry_at = time.monotonic() + 2
                raise SSHError(self.error)
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            command = [executable, "-v", "-N", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                       "-o", "ExitOnForwardFailure=yes", "-o", "ControlMaster=no", "-o", "ControlPath=none",
                       "-o", "ClearAllForwardings=no",
                       "-o", "ControlPersist=no", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3",
                       "-o", "ConnectTimeout=10", "-o", "PermitLocalCommand=no", "-o", "ForkAfterAuthentication=no",
                       "-L", f"127.0.0.1:{port}:{self.destination}:{self.remote_port}", self.host]
            self.diagnostic = self.error = ""
            self.authenticated.clear()
            env = dict(os.environ, SSH_ASKPASS_REQUIRE="never")
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            try:
                self.process = _launch(command, env, options)
            except OSError as exc:
                self.error = f"SSH guardian could not start ({type(exc).__name__})"
                self.retry_at = time.monotonic() + 2
                raise SSHError(self.error) from None
            try:
                self.tree = psutil.Process(self.process.pid)
            except psutil.NoSuchProcess:
                self.tree = None
            self.reader = threading.Thread(target=self._read, args=(self.process,), daemon=True, name="stk-ssh-stderr")
            self.reader.start()
            deadline = time.monotonic() + self.timeout
            listening_since = None
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    break
                if not self.authenticated.is_set():
                    time.sleep(0.025)
                    continue
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        listening_since = listening_since or time.monotonic()
                except OSError:
                    listening_since = None
                # Let immediate process failures arrive before publishing the endpoint.
                if listening_since and time.monotonic() - listening_since >= 0.2:
                    if self.process.poll() is None:
                        self.local_port = port
                        return f"http://127.0.0.1:{port}"
                time.sleep(0.025)
            self._stop()
            with self.output_lock:
                detail = self.diagnostic.strip()[-2000:]
            self.error = "SSH tunnel failed to start" + (": " + detail if detail else " (timed out)")
            self.retry_at = time.monotonic() + 2
            raise SSHError(self.error)


class SSHRuntimeClient(RuntimeClient):
    def __init__(self, tunnel, token, timeout=30):
        self.tunnel = tunnel
        super().__init__("http://127.0.0.1:1", token, timeout)

    @property
    def url(self):
        return self.tunnel.endpoint()

    @url.setter
    def url(self, value):
        pass  # RuntimeClient validates its placeholder; the actual endpoint belongs to the tunnel.

    @property
    def connection_identity(self):
        return self.tunnel.identity


class TunnelManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.entries = {}
        self.closed = False

    def client(self, key, config):
        if "ssh" not in config:
            self.remove(key)
            return RuntimeClient(config["url"], config["token"])
        validate_ssh(config["url"], config["ssh"])
        RuntimeClient(config["url"], config["token"])
        signature = (config["url"], config["ssh"]["host"], config["token"])
        with self.lock:
            if self.closed:
                raise SSHError("SSH connection manager has closed")
            previous = self.entries.get(key)
            if previous and previous[0] != signature:
                previous[1].disconnect(permanent=True)
                previous = None
            if previous is None:
                previous = (signature, Tunnel(config["url"], config["ssh"]))
                self.entries[key] = previous
            return SSHRuntimeClient(previous[1], config["token"])

    def remove(self, key):
        with self.lock:
            entry = self.entries.pop(key, None)
            if entry:
                entry[1].disconnect(permanent=True)

    def close(self):
        with self.lock:
            self.closed = True
            for key in list(self.entries):
                self.remove(key)


# CLI and legacy Python callers share process ownership; the bridge owns a separate manager.
_default_manager = TunnelManager()
atexit.register(_default_manager.close)


def profile_client(key, config):
    return _default_manager.client(key, config)
