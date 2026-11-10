"""The registered ``mupro.preflight.*`` desktop RPC over the real strict stdio Bridge.

Every Bridge here is a separate ``python -m suan.desktop_bridge --stdio --strict`` child
process (:class:`StreamBridge`), so reservation, SIGKILL and reopening use the real
transport, process boundary, journal locks and profile file. The Runtime is the real
loopback HTTP server and supervisor of ``conftest.runtime``; its worker runs the actual
``suan.mupro.preflight`` task through a private ``env -i`` interpreter. An owned loopback
proxy in front of that Runtime records every request the Bridge sends and can hold or drop
exactly one reply *after* the Runtime has accepted it. No product code is replaced.

Fixtures are synthetic: an SDK directory, a program that records any execution as a
forbidden marker, an empty licence directory and one trusted environment script that only
appends its parent PID. Nothing contacts a model, MPI, MuPRO or a non-loopback address.
Native panel binding, view lifecycle and click flows are outside this module.
"""
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shlex
import sys
import threading
import uuid

import pytest

from conftest import finish
from suan.agent.tools import REGISTRY as AGENT_TOOLS
from suan.desktop_bridge import schema as bridge_schema
from suan.desktop_bridge.protocol import ERROR_CODES
from suan.mupro.preflight import OBSERVATION_NAME
from suan.mupro.spec import preflight_spec
from suan.runtime.models import TaskSpec
from test_desktop_bridge import ProcessBridge, _strict


REPO = Path(__file__).resolve().parents[1]
TOKEN = "abcdefghijklmnopqrstu"  # low-entropy synthetic Runtime credential
PROJECT = "79797979-7979-4979-8979-797979797979"
OTHER_PROJECT = "22222222-2222-4222-8222-222222222222"
KEY = "7" * 32
CONNECTION = "runtime:pilot"
METHODS = {"mupro.preflight." + name for name in ("describe", "list", "reserve", "retry", "refresh")}
HELLO = {"protocol": 1, "client": {"name": "pytest-preflight-rpc", "version": "1"}}
MARKER = "private-sdk-marker-79"
HEX16, HEX32 = re.compile(r"[a-f0-9]{16}"), re.compile(r"[a-f0-9]{32}")
WAIT = 30

# The Bridge child imports this worktree's package and nothing from the parent's sys.path.
LAUNCH = """import sys
from pathlib import Path
import suan
assert Path(suan.__file__).resolve().is_relative_to(Path(sys.argv[2]).resolve()), suan.__file__
from suan.desktop_bridge.__main__ import main
main(["--stdio", "--strict", "--state-dir", sys.argv[1]])
"""


class StreamBridge(ProcessBridge):
    """ProcessBridge that also keeps every raw stdout line and any reader-thread failure.

    The shared reader decodes in a daemon thread, where a bad line would only end that
    thread; here a violation becomes an assertion of :meth:`check_stream`.
    """

    def __init__(self, *args, **kwargs):
        self.raw, self.reader_errors = [], []
        super().__init__(*args, **kwargs)

    def _read(self):
        try:
            for raw in self.process.stdout:
                self.raw.append(raw)
                self.receive(raw)
        except BaseException as error:  # noqa: B902 - reported by check_stream
            self.reader_errors.append(repr(error))

    def check_stream(self):
        assert self.reader_errors == []
        for raw in self.raw:
            message = _strict(raw)
            assert set(message) in ({"id", "result"}, {"id", "error"}, {"event", "data"})
        self.assert_clean()

    def kill(self):
        super().kill()
        self.check_stream()

    def close(self, timeout=30):
        code = super().close(timeout)
        self.check_stream()
        return code

    def preflight_text(self):
        """Every preflight response, as emitted (results and errors)."""
        with self.cond:
            return "\n".join(json.dumps(message) for identity, messages in self.responses.items()
                             for message in messages if self.methods.get(identity, "").startswith("mupro.preflight."))


class Proxy:
    """Owned loopback forwarder to the Runtime: records requests; one armed reply may be lost.

    An armed ``(method, path)`` is forwarded to completion first, so the Runtime has durably
    accepted it; then ``accepted`` is set and the reply is never written: ``drop`` closes the
    connection immediately, ``hold`` waits for ``release`` (or the test's teardown) first.
    """

    def __init__(self, upstream_port):
        self.upstream = upstream_port
        self.log, self.lock = [], threading.Lock()
        self.rule = None
        self.accepted, self.release = threading.Event(), threading.Event()
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def forward(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    document = json.loads(body) if body else None
                except ValueError:
                    document = None
                with proxy.lock:
                    proxy.log.append((self.command, self.path, document))
                    rule, armed = proxy.rule, (self.command, self.path) == (proxy.rule or (None, None, None))[:2]
                    if armed:
                        proxy.rule = None
                upstream = http.client.HTTPConnection("127.0.0.1", proxy.upstream, timeout=WAIT)
                try:
                    headers = {name: self.headers[name] for name in ("Authorization", "Content-Type")
                               if self.headers.get(name) is not None}
                    upstream.request(self.command, self.path, body or None, headers)
                    reply = upstream.getresponse()
                    data, status = reply.read(), reply.status
                    kind = reply.getheader("Content-Type") or "application/json"
                finally:
                    upstream.close()
                if armed:
                    proxy.accepted.set()
                    if rule[2] == "hold":
                        proxy.release.wait(WAIT * 2)
                    self.close_connection = True
                    return  # The accepted reply is lost: no status line, no body.
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = forward

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()

    def arm(self, method, path, mode):
        with self.lock:
            self.rule = (method, path, mode)

    def requests(self, start=0):
        with self.lock:
            return list(self.log[start:])

    def posts(self, path, start=0):
        return [document for method, request_path, document in self.requests(start)
                if (method, request_path) == ("POST", path)]

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def identity(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def reserve_params(stack, **changes):
    return {"project_id": PROJECT, "connection": CONNECTION, "expected_connection_identity": identity(stack.proxy.url),
            "workspace_id": None, "options": {}, "idempotency_key": KEY, **changes}


def ref(key=KEY, project=PROJECT):
    return {"project_id": project, "id": key}


def journal(stack):
    return stack.state / "mupro-preflight"


def on_disk(stack, key=KEY):
    return json.loads((journal(stack) / (key + ".json")).read_text(encoding="utf-8"))


class Stack:
    def __init__(self, runtime, tmp_path):
        self.client, self.supervisor, self.server, config = runtime
        self.client.token = config["token"] = TOKEN
        self.tmp = tmp_path
        self.sdk, tools, self.licence = tmp_path / "sdk", tmp_path / "tools", tmp_path / "licence"
        for folder in (self.sdk / "bin", tools, self.licence):
            folder.mkdir(parents=True)
        self.forbidden = tmp_path / "solver-or-mpi-started"
        for path in (self.sdk / "bin/muFerro", tools / "mpiexec"):
            path.write_text("#!/bin/sh\nprintf forbidden > " + shlex.quote(str(self.forbidden)) + "\nexit 17\n")
            path.chmod(0o700)
        self.counter, script = tmp_path / "trusted-env-sourced", tmp_path / "worker-env.sh"
        script.write_text("printf '%s\\n' \"$PPID\" >> " + shlex.quote(str(self.counter)) + "\n")
        bytecode = tmp_path / "bytecode"
        worker_env = {"PATH": str(tools) + os.pathsep + os.defpath, "LANG": "C.UTF-8", "PYTHONPATH": str(REPO),
                      "PYTHONPYCACHEPREFIX": str(bytecode / "worker"), "STK_TOKEN_PLAN_API_KEY": "",
                      "MUPRO_SDK_PREFIX": str(self.sdk), "MUPROROOT": str(self.licence),
                      "STK_MUPRO_ENV_SCRIPTS": str(script)}
        # Replacing os.environ in this process would not change what Popen children inherit:
        # the worker interpreter itself starts from an empty environment.
        interpreter = tmp_path / "worker-python"
        interpreter.write_text("#!/bin/sh\nexec /usr/bin/env -i " +
            shlex.join([*(f"{k}={v}" for k, v in worker_env.items()), sys.executable]) + ' "$@"\n')
        interpreter.chmod(0o700)
        config["python"] = str(interpreter)
        home = tmp_path / "home"
        self.state = tmp_path / "desktop-state"
        self.bridge_env = {"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": str(home),
            "XDG_CACHE_HOME": str(home / "cache"), "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"), "XDG_STATE_HOME": str(home / "state"),
            "STK_PROFILES_FILE": str(tmp_path / "profiles" / "connections.json"),
            "STK_STATE_DIR": str(tmp_path / "no-local-runtime"), "STK_TOKEN_PLAN_API_KEY": "",
            "STK_GRAPH_CACHE": str(tmp_path / "graph-cache"), "MPLCONFIGDIR": str(tmp_path / "matplotlib"),
            "PYTHONPYCACHEPREFIX": str(bytecode / "bridge")}
        self.bytecode = bytecode
        self.proxy = Proxy(self.server.server_port)
        self.proxies = [self.proxy]
        self.bridges = []

    def bridge(self):
        bridge = StreamBridge(self.state, env=self.bridge_env, stderr_path=self.tmp / f"bridge-{len(self.bridges)}.err",
            argv=[sys.executable, "-X", f"pycache_prefix={self.bytecode / 'bridge'}", "-c", LAUNCH,
                  str(self.state), str(REPO)])
        self.bridges.append(bridge)
        hello = bridge.call("hello", HELLO)
        bridge.hello = hello
        for value in hello["paths"].values():
            assert Path(value).resolve().is_relative_to(self.tmp.resolve()), value
        assert Path(hello["paths"]["state_dir"]).resolve() == self.state.resolve()
        assert hello["server"]["pid"] == bridge.process.pid != os.getpid()
        return bridge

    def connect(self, bridge, url=None):
        added = bridge.call("connections.add_runtime", {"name": "pilot", "url": url or self.proxy.url,
                                                        "token": TOKEN, "check": False})
        assert added["connection"]["id"] == CONNECTION

    def new_proxy(self):
        proxy = Proxy(self.server.server_port)
        self.proxies.append(proxy)
        return proxy

    def close(self):
        for bridge in self.bridges:
            if bridge.process.poll() is None:
                bridge.process.kill()
                bridge.process.wait(timeout=30)
        for proxy in self.proxies:
            proxy.close()


@pytest.fixture
def stack(runtime, tmp_path):
    stack = Stack(runtime, tmp_path)
    try:
        yield stack
        assert not stack.forbidden.exists()  # No synthetic solver or MPI launcher ever ran.
        for bridge in stack.bridges:
            assert TOKEN not in bridge.output_text() and MARKER not in bridge.output_text()
            assert TOKEN not in bridge.stderr_text()
            preflight = bridge.preflight_text()
            for private in (str(stack.tmp), stack.proxy.url, "127.0.0.1", str(stack.sdk), str(stack.licence)):
                assert private not in preflight
    finally:
        stack.close()


def check_record(record, *, phase):
    assert set(record) == {"id", "project_id", "request", "workspace_id", "task_id", "phase", "task_state",
                           "task_exit_code", "result", "error", "created_at", "updated_at"}
    assert HEX32.fullmatch(record["id"]) and str(uuid.UUID(record["project_id"])) == record["project_id"]
    assert HEX16.fullmatch(record["request"]["expected_connection_identity"])
    assert record["request"]["idempotency_key"] == record["id"] and record["phase"] == phase
    for field in ("workspace_id", "task_id"):
        assert record[field] is None or HEX32.fullmatch(record[field])
    return record


def worker_pid(stack, task_id):
    return json.loads((stack.server.service.task_dir(task_id) / "program.json").read_text())["pid"]


def expected_spec(workspace_id, options):
    return TaskSpec(**preflight_spec(workspace_id, **options)).to_dict()


# ---------------------------------------------------------------------------------------------


def test_hello_advertises_exactly_the_five_methods_and_no_agent_tool(stack):
    bridge = stack.bridge()
    advertised = {name for name in bridge.hello["methods"] if name.startswith("mupro.preflight.")}
    assert advertised == METHODS and "mupro.preflight.submit" not in bridge.hello["methods"]
    assert {name for name in bridge_schema.method_names() if name.startswith("mupro.preflight.")} == METHODS
    assert bridge.error("mupro.preflight.submit", reserve_params(stack))["code"] == "unknown_method"
    assert not (stack.state / "mupro-preflight").exists()  # Advertising methods opens no journal.
    # The diagnostic methods are a desktop action only: no Agent tool reaches them.
    assert not any("preflight" in name or "mupro" in name for name in AGENT_TOOLS)
    assert stack.proxy.requests() == []
    assert bridge.close() == 0


def test_reserve_list_and_reopen_after_sigkill_are_local_without_any_runtime_io(stack):
    bridge = stack.bridge()
    stack.connect(bridge)
    described = bridge.call("mupro.preflight.describe", {"connection": CONNECTION})
    assert described == {"connection": CONNECTION, "connection_identity": identity(stack.proxy.url)}
    prepared = check_record(bridge.call("mupro.preflight.reserve", reserve_params(stack))["record"], phase="prepared")
    assert prepared["request"] == {"connection": CONNECTION, "expected_connection_identity": identity(stack.proxy.url),
        "workspace_id": None, "options": {"backend": "local", "name": ""}, "idempotency_key": KEY}
    assert all(prepared[field] is None for field in
               ("workspace_id", "task_id", "task_state", "task_exit_code", "result", "error"))
    defaults = reserve_params(stack, options={"backend": "local", "name": ""})
    assert bridge.call("mupro.preflight.reserve", defaults)["record"] == prepared
    changed = reserve_params(stack, options={"name": "different"})
    assert bridge.error("mupro.preflight.reserve", changed)["code"] == "conflict"
    assert bridge.call("mupro.preflight.list", {"project_id": PROJECT}) == {"records": [prepared]}
    assert bridge.call("mupro.preflight.list", {"project_id": OTHER_PROJECT}) == {"records": []}
    assert on_disk(stack) == prepared
    assert (journal(stack) / (KEY + ".json")).stat().st_mode & 0o777 == 0o600
    assert journal(stack).stat().st_mode & 0o777 == 0o700
    # The native caller drops the acknowledged reservation (view changed, then crash).
    bridge.kill()
    reopened = stack.bridge()
    assert reopened.call("mupro.preflight.list", {"project_id": PROJECT}) == {"records": [prepared]}
    assert reopened.call("mupro.preflight.refresh", ref())["record"] == prepared
    assert reopened.call("mupro.preflight.reserve", reserve_params(stack))["record"] == prepared
    assert stack.proxy.requests() == []  # Not even a health check or describe probe.
    assert stack.client.tasks() == stack.client.workspaces() == [] and not stack.counter.exists()
    assert reopened.close() == 0


@pytest.mark.parametrize("change", [
    {"client_sdk": "/tmp/" + MARKER},
    {"options": {"sdk_prefix": "/tmp/" + MARKER}},
    {"options": {"env_scripts": ["/tmp/" + MARKER]}},
    {"options": {"program": "/tmp/" + MARKER}},
    {"options": {"license_dir": "/tmp/" + MARKER}},
    {"options": {"env": {"MUPRO_SDK_PREFIX": "/tmp/" + MARKER}}},
    {"options": {"cpus": 64}},
    {"options": {"queue": "/tmp/" + MARKER + " ; true"}},
    {"workspace_id": "/tmp/" + MARKER},
    {"idempotency_key": "../" + MARKER},
    {"project_id": MARKER},
    {"expected_connection_identity": MARKER},
    {"connection": "runtime:" + MARKER + "\n"},
])
def test_unknown_or_private_request_fields_are_rejected_before_any_effect(stack, change):
    bridge = stack.bridge()
    stack.connect(bridge)
    error = bridge.error("mupro.preflight.reserve", reserve_params(stack, **change))
    assert error["code"] == "invalid_params"
    for method in ("mupro.preflight.retry", "mupro.preflight.refresh"):
        assert bridge.error(method, {**ref(), "connection": "runtime:" + MARKER})["code"] == "invalid_params"
    assert not journal(stack).exists() or list(journal(stack).glob("*.json")) == []
    assert stack.proxy.requests() == [] and stack.client.workspaces() == []
    assert MARKER not in bridge.output_text()  # Not echoed through messages or data.errors.
    assert bridge.close() == 0


def test_hub_and_changed_frozen_target_are_refused_at_retry_before_runtime_io(stack):
    bridge = stack.bridge()
    stack.connect(bridge)
    other_key = "8" * 32
    # Reservation is purely local and does not resolve the connection, so both intents
    # are recorded; the refusal happens when an explicit retry resolves the target.
    hub = check_record(bridge.call("mupro.preflight.reserve", reserve_params(
        stack, connection="hub:lab", expected_connection_identity="1" * 16))["record"], phase="prepared")
    pinned = check_record(bridge.call("mupro.preflight.reserve", reserve_params(stack, idempotency_key=other_key))[
        "record"], phase="prepared")
    # Retry resolves only {connection, expected identity}: a hub without a node is refused by
    # connection resolution itself, before the adapter or any Runtime/hub request.
    assert bridge.error("mupro.preflight.retry", ref())["code"] == "invalid_params"
    # The saved profile now names a different loopback Runtime endpoint (a second proxy).
    moved = stack.new_proxy()
    stack.connect(bridge, moved.url)
    assert bridge.call("mupro.preflight.describe", {"connection": CONNECTION})["connection_identity"] == identity(moved.url)
    assert bridge.error("mupro.preflight.retry", ref(other_key))["code"] == "conflict"
    assert bridge.error("mupro.preflight.refresh", ref(other_key, OTHER_PROJECT))["code"] == "conflict"
    assert bridge.error("mupro.preflight.retry", ref("9" * 32))["code"] == "not_found"
    rebound = reserve_params(stack, idempotency_key=other_key, expected_connection_identity=identity(moved.url))
    assert bridge.error("mupro.preflight.reserve", rebound)["code"] == "conflict"
    records = {record["id"]: record for record in bridge.call("mupro.preflight.list", {"project_id": PROJECT})["records"]}
    assert records == {KEY: hub, other_key: pinned}
    assert stack.proxy.requests() == moved.requests() == []
    assert stack.client.tasks() == stack.client.workspaces() == []
    assert bridge.close() == 0


def test_real_bridge_runtime_worker_failed_checks_are_one_verified_original_task(stack):
    (stack.sdk / "bin/muFerro").unlink()  # The configured program is missing: checks fail.
    bridge = stack.bridge()
    stack.connect(bridge)
    options = {"name": "environment check 79", "walltime_seconds": 120}
    prepared = bridge.call("mupro.preflight.reserve", reserve_params(stack, options=options))["record"]
    assert prepared["request"]["options"] == {"backend": "local", "name": "environment check 79",
                                              "walltime_seconds": 120}
    assert stack.proxy.requests() == []
    accepted = check_record(bridge.call("mupro.preflight.retry", ref())["record"], phase="accepted")
    workspace, task_id = accepted["workspace_id"], accepted["task_id"]
    assert accepted["request"] == prepared["request"] and accepted["task_state"] == "queued"
    created, submitted = stack.proxy.posts("/v1/workspaces"), stack.proxy.posts("/v1/tasks")
    assert created == [{"name": "STK MuPRO preflight", "idempotency_key": "mupro-preflight:" + KEY + ":workspace"}]
    spec = expected_spec(workspace, options)
    assert len(submitted) == 1 and submitted[0]["idempotency_key"] == KEY
    assert TaskSpec(**submitted[0]["spec"]).to_dict() == spec
    assert [task["id"] for task in stack.client.tasks()] == [task_id]
    assert TaskSpec(**stack.client.task(task_id)["spec"]).to_dict() == spec  # The Runtime's own record.
    mark = len(stack.proxy.requests())
    assert bridge.call("mupro.preflight.retry", ref())["record"] == accepted
    assert stack.proxy.requests(mark) == []  # A known task is returned without Runtime I/O.
    first_pid = bridge.hello["server"]["pid"]
    bridge.kill()  # The accepted identity is durable across a Bridge crash.
    bridge = stack.bridge()
    assert bridge.call("mupro.preflight.list", {"project_id": PROJECT})["records"] == [accepted]
    assert bridge.call("mupro.preflight.retry", ref())["record"] == accepted
    assert stack.proxy.requests(mark) == []

    task = finish(stack.client, stack.supervisor, task_id)
    assert task["state"] == "failed" and task["exit_code"] == 1
    mark = len(stack.proxy.requests())
    finished = check_record(bridge.call("mupro.preflight.refresh", ref())["record"], phase="finished")
    assert finished["task_state"] == "failed" and finished["task_exit_code"] == 1 and finished["error"] is None
    result = finished["result"]
    artifact = stack.server.service.task_dir(task_id) / "work" / OBSERVATION_NAME
    data = artifact.read_bytes()
    assert result["artifact"] == {"path": OBSERVATION_NAME, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    assert result["task"] == {"id": task_id, "workspace_id": workspace, "backend": "local",
                              "state": "failed", "exit_code": 1}
    assert result["target"] == {"profile": None, "connection_sha256": hashlib.sha256(stack.proxy.url.encode()).hexdigest()}
    observation = result["observation"]
    assert observation == json.loads(data) and observation["summary"] == "checks_failed"
    assert {check["id"]: check["status"] for check in observation["checks"]}["program"] == "fail"
    assert observation["unverified"] == {"program_version": "unobserved", "license_checkout": "not_checked",
                                         "solver_execution": "not_run"}
    pid = observation["process_id"]
    assert pid == worker_pid(stack, task_id) and pid not in {first_pid, bridge.hello["server"]["pid"], os.getpid()}
    assert stack.counter.read_text().splitlines() == [str(pid)]

    assert bridge.call("mupro.preflight.refresh", ref())["record"]["result"] == result
    assert bridge.call("mupro.preflight.retry", ref())["record"]["result"] == result
    # Refresh reads only the original task (record, artifact listing, ranged file); no health or listing.
    reads = stack.proxy.requests(mark)
    assert reads and all(method == "GET" and path.startswith("/v1/tasks/" + task_id) for method, path, _ in reads)
    assert not any("upload" in path or "/cancel" in path for _, path, _ in stack.proxy.requests())
    assert len(stack.proxy.posts("/v1/tasks")) == len(stack.proxy.posts("/v1/workspaces")) == 1
    assert len(stack.client.tasks()) == len(stack.client.workspaces()) == 1
    assert stack.counter.read_text().splitlines() == [str(pid)]
    assert bridge.call("mupro.preflight.list", {"project_id": PROJECT})["records"][0]["result"] == result
    assert bridge.close() == 0


def test_selected_existing_workspace_is_used_without_creating_a_container(stack):
    workspace = stack.client.create_workspace("Explicit existing workspace")["id"]  # Directly, not proxied.
    bridge = stack.bridge()
    stack.connect(bridge)
    prepared = bridge.call("mupro.preflight.reserve", reserve_params(stack, workspace_id=workspace))["record"]
    assert prepared["workspace_id"] == prepared["request"]["workspace_id"] == workspace
    accepted = check_record(bridge.call("mupro.preflight.retry", ref())["record"], phase="accepted")
    assert accepted["workspace_id"] == workspace and accepted["result"] is None
    assert [(method, path) for method, path, _ in stack.proxy.requests()] == [("POST", "/v1/tasks")]
    (submitted,) = stack.proxy.posts("/v1/tasks")
    assert submitted["idempotency_key"] == KEY and TaskSpec(**submitted["spec"]).to_dict() == expected_spec(workspace, {})
    assert [task["id"] for task in stack.client.tasks()] == [accepted["task_id"]]
    assert len(stack.client.workspaces()) == 1 and not stack.counter.exists()
    assert bridge.close() == 0


@pytest.mark.parametrize("boundary, mode", [("/v1/tasks", "kill"), ("/v1/workspaces", "kill"), ("/v1/tasks", "drop")])
def test_lost_runtime_ack_then_reopen_never_replays_and_original_id_recovers_one_task(stack, boundary, mode):
    bridge = stack.bridge()
    stack.connect(bridge)
    prepared = bridge.call("mupro.preflight.reserve", reserve_params(stack))["record"]  # ACKed before retry.
    stack.proxy.arm("POST", boundary, "hold" if mode == "kill" else "drop")
    if mode == "kill":
        pending = bridge.request("mupro.preflight.retry", ref())
        assert stack.proxy.accepted.wait(WAIT)  # The Runtime accepted; its reply is held.
        durable = on_disk(stack)
        assert durable["phase"] == ("submitting" if boundary == "/v1/tasks" else "creating_workspace")
        assert durable["request"] == prepared["request"] and durable["task_id"] is None
        bridge.kill()
        assert pending not in bridge.responses
        stack.proxy.release.set()
    else:
        lost = check_record(bridge.call("mupro.preflight.retry", ref())["record"], phase="unknown")
        assert lost["task_id"] is None and lost["error"]["code"] in ERROR_CODES
        assert lost["error"]["retryable"] is False
        assert bridge.close() == 0
    assert len(stack.client.workspaces()) == 1
    assert len(stack.client.tasks()) == (1 if boundary == "/v1/tasks" else 0)
    first_workspace, first_tasks = stack.proxy.posts("/v1/workspaces"), stack.proxy.posts("/v1/tasks")

    mark = len(stack.proxy.requests())
    reopened = stack.bridge()
    (unknown,) = reopened.call("mupro.preflight.list", {"project_id": PROJECT})["records"]
    check_record(unknown, phase="unknown")
    assert unknown["request"] == prepared["request"] and unknown["task_id"] is None
    assert (unknown["workspace_id"] is None) == (boundary == "/v1/workspaces")
    assert unknown["error"]["code"] in ERROR_CODES and unknown["result"] is None
    assert reopened.call("mupro.preflight.refresh", ref())["record"] == unknown
    assert stack.proxy.requests(mark) == []  # Reopen, list and refresh never POST or even read.
    assert not stack.counter.exists()

    recovered = check_record(reopened.call("mupro.preflight.retry", ref())["record"], phase="accepted")
    (task,) = stack.client.tasks()
    assert recovered["task_id"] == task["id"] and recovered["request"] == prepared["request"]
    replay = [(method, path) for method, path, _ in stack.proxy.requests(mark) if method == "POST"]
    if boundary == "/v1/tasks":
        assert replay == [("POST", "/v1/tasks")]
        assert recovered["workspace_id"] == unknown["workspace_id"]
        assert stack.proxy.posts("/v1/tasks", mark) == first_tasks  # Same frozen spec and original key.
    else:
        assert replay == [("POST", "/v1/workspaces"), ("POST", "/v1/tasks")]
        assert stack.proxy.posts("/v1/workspaces", mark) == first_workspace  # Derived workspace key.
    assert stack.proxy.posts("/v1/tasks")[-1]["idempotency_key"] == KEY
    assert len(stack.client.workspaces()) == len(stack.client.tasks()) == 1

    finish(stack.client, stack.supervisor, task["id"])
    finished = check_record(reopened.call("mupro.preflight.refresh", ref())["record"], phase="finished")
    assert finished["result"]["task"]["id"] == task["id"]
    assert finished["result"]["observation"]["summary"] == "checks_incomplete"
    assert stack.counter.read_text().splitlines() == [str(worker_pid(stack, task["id"]))]
    mark = len(stack.proxy.requests())
    assert reopened.call("mupro.preflight.retry", ref())["record"] == finished
    assert stack.proxy.requests(mark) == []
    assert len(stack.client.workspaces()) == len(stack.client.tasks()) == 1
    assert reopened.close() == 0


def test_corrupt_journal_disables_only_diagnostics_and_is_never_deleted(stack):
    journal(stack).mkdir(parents=True, mode=0o700)
    damaged = journal(stack) / (KEY + ".json")
    damaged.write_bytes(b'{"id": "' + KEY.encode() + b'", "phase": ')
    damaged.chmod(0o600)
    before = damaged.read_bytes()
    bridge = stack.bridge()  # hello already succeeded inside stack.bridge().
    assert bridge.call("project.list") == {"projects": []}
    stack.connect(bridge)
    for method, params in (("mupro.preflight.list", {"project_id": PROJECT}),
                           ("mupro.preflight.describe", {"connection": CONNECTION}),
                           ("mupro.preflight.reserve", reserve_params(stack, idempotency_key="8" * 32)),
                           ("mupro.preflight.retry", ref()), ("mupro.preflight.refresh", ref())):
        error = bridge.error(method, params)
        assert error["code"] == "unavailable" and error["retryable"] is False, (method, error)
    assert bridge.call("connections.list")["connections"][-1]["id"] == CONNECTION  # Other methods still work.
    assert damaged.read_bytes() == before
    assert sorted(path.name for path in journal(stack).glob("*.json")) == [KEY + ".json"]
    assert stack.proxy.requests() == [] and stack.client.workspaces() == []
    assert bridge.close() == 0
