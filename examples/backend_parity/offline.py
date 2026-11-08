"""D1 two-deployment task parity harness (CL-D1-PARITY-11, d1-compatibility-gates.md §1.1(a)).

Starts, from one STK installation (``--mode installed``) or this source tree (``--mode source``), two private
Linux deployments with existing entry points only:

* **A** -- ``suan server init/start`` (its own API and supervisor processes), driven directly through
  ``suan.desktop_bridge.backends.RuntimeBackend``;
* **B** -- ``suan-control init/serve`` (real HTTP + WebSocket Hub), ``suan-node pair/run`` (outbound
  NodeAgent) and another ``suan server`` Runtime, driven through ``HubClient`` + ``HubBackend``.

Both run the same public synthetic programs with the identical ``{python}`` argv; B registers them as
exact operator templates, so the Hub's existing review rules let them run without review. The run
compares: completed submission, same-path replay of the same key, conflict on a different request,
live exact ``task.get``, artifact list and downloaded bytes, UTF-8 logs by byte cursor, and an explicit
cancel. Each side keeps the IDs of its own authority; no ID is expected to match across paths and no
recovery ever switches paths. Waits have hard deadlines: an unanswered wait is reported ``unknown`` and
nothing is resubmitted. Only processes and directories created by this run are stopped or removed.

Evidence (``--evidence-dir``): run-manifest.json, requests.jsonl, assertions.json, backend-parity.json,
resources.json. They hold no tokens, pairing codes, environment or personal paths.

This is a software-behaviour check of task semantics on one Linux host. It does not cover project
semantics, a minimal-extras install, other operating systems, real solvers or scientific validity.
Nothing here is registered as a product command or started automatically.
"""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = ("succeeded", "failed", "cancelled")

# Fixed public synthetic programs (no inputs, no network): UTF-8 text on stdout and one small artifact.
# Each program first appends one line to START_MARKER with a single O_APPEND write, in its task's run
# directory (the parent of its working directory: the Runtime publishes every file of the working directory as
# an artifact, so the marker stays out of the compared artifact list). Every real execution adds exactly one
# line; a replay or a second launch would show up as a second line or a second run directory.
START_MARKER = "parity-start.marker"
EXPECTED_OUT = "parity 结果\n".encode("utf-8")
_MARK = ("import os\n"
         f"fd = os.open(os.path.join('..', {START_MARKER!r}), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)\n"
         "os.write(fd, f'start {os.getpid()}\\n'.encode())\n"
         "os.close(fd)\n")
DONE_PROGRAM = (_MARK +
                "import sys\n"
                "for i in range(3):\n"
                "    sys.stdout.write(f'第{i}行 parity ✓ ü\\n')\n"
                "sys.stdout.flush()\n"
                "open('out.txt', 'w', encoding='utf-8').write('parity 结果\\n')\n")
WAIT_PROGRAM = (_MARK +
                "import sys, time\n"
                "print('waiting 等待', flush=True)\n"
                "deadline = time.monotonic() + 120\n"
                "while time.monotonic() < deadline:\n"
                "    time.sleep(0.2)\n")
TEMPLATES = {
    "parity-done": {"argv": ["{python}", "-c", DONE_PROGRAM], "outputs": ["out.txt"]},
    "parity-wait": {"argv": ["{python}", "-c", WAIT_PROGRAM], "outputs": []},
}


INHERITED = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TZ")
KEY_MODULES = ("suan.runtime.server", "suan.runtime.service", "suan.runtime.supervisor", "suan.runtime.worker",
               "suan.runtime.store", "suan.runtime.cli", "suan.control.app", "suan.control.agent", "suan.control.policy",
               "suan.control.cli", "suan.desktop_bridge.backends", "suan.desktop_bridge.hub")
DEADLINE = None  # monotonic time by which the whole run must end (set by run())


class HarnessError(Exception):
    """A failure whose message this harness wrote itself (labels and counts only; never a path or argument)."""


def exported_error(exc):
    """The error as written to evidence and stdout: a fixed kind/code and only harness-written messages.
    Raw exception text from libraries, services or the OS (which may hold paths or secrets) is never exported."""
    try:
        from suan.desktop_bridge.protocol import BridgeError
    except ImportError:  # pragma: no cover - a broken install still gets a controlled record
        BridgeError = ()
    if isinstance(exc, Unknown):
        return {"kind": "unknown", "message": exc.args[0] if exc.args else "unknown"}
    if isinstance(exc, HarnessError):
        return {"kind": "error", "message": exc.args[0] if exc.args else "error"}
    if isinstance(exc, BridgeError):
        return {"kind": "error", "code": exc.code, "message": "a backend call failed"}
    return {"kind": "error", "code": type(exc).__name__, "message": "unexpected error (details withheld from evidence)"}


class Unknown(Exception):
    """A wait reached its deadline: the remote state is unknown, never assumed failed."""


CLEANUP_GRACE = 60  # seconds each cleanup step may take after the budget (stopping services, removing files)
HTTP_TIMEOUT = 10  # seconds per HTTP request; every wait loop is also bounded by the run budget


def remaining(limit):
    """Seconds left for a wait: its own limit, never past the run's global deadline."""
    if DEADLINE is None:
        return limit
    return max(0.0, min(limit, DEADLINE - time.monotonic()))


def budget(limit):
    """Time for one call within the run's budget; a spent budget is ``Unknown`` (the call is not made)."""
    left = remaining(limit)
    if left <= 0:
        raise Unknown("the run's time budget is spent; the remaining steps were not attempted")
    return left


def check_deadline(value):
    """A finite, positive number of seconds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("--deadline must be a finite positive number of seconds")
    return float(value)


# ----------------------------------------------------------------------------------------------------
# Processes owned by this run


class Owned:
    """Every process and directory this run created, and only those, for evidence and cleanup."""

    def __init__(self, work):
        self.work = work
        self.processes = []  # (label, Popen)
        self.resources = {"processes": [], "directories": [], "cleanup": []}

    def env(self, mode):
        """A minimal explicit environment: only the variables named here are inherited (HOME is kept as is,
        never repurposed); credentials, model settings, proxies, displays and profiles are not. STK state,
        client profiles, XDG and temporary directories are this run's own."""
        private = self.work / "private"
        env = {key: os.environ[key] for key in INHERITED if key in os.environ}
        env.update({"STK_TOKEN_PLAN_API_KEY": "", "STK_STATE_DIR": str(private / "stk-state"),
                    "STK_PROFILES_FILE": str(private / "profiles.json"),
                    "XDG_CONFIG_HOME": str(private / "config"), "XDG_CACHE_HOME": str(private / "cache"),
                    "XDG_DATA_HOME": str(private / "data"), "XDG_STATE_HOME": str(private / "state"),
                    "TMPDIR": str(private / "tmp"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
        for name in ("config", "cache", "data", "state", "tmp"):
            (private / name).mkdir(parents=True, exist_ok=True)
        if mode == "source":
            env["PYTHONPATH"] = str(ROOT)  # explicitly run this source tree, not an installed package
        return env

    def run(self, label, command, env, *, stdin=None, timeout=60, cleanup=False):
        """A short CLI call; its output is returned to the caller, never logged (it may hold a code).
        Its timeout is the remaining run budget, except for cleanup steps, which get CLEANUP_GRACE."""
        limit = min(timeout, CLEANUP_GRACE) if cleanup else budget(timeout)
        # A new session has no controlling terminal, so a hidden prompt reads the code from stdin.
        try:
            result = subprocess.run(command, input=stdin, capture_output=True, text=True, env=env, timeout=limit,
                                    cwd=self.work, start_new_session=True)
        except subprocess.TimeoutExpired:
            if cleanup:
                raise
            raise Unknown(f"{label} did not finish within the run budget") from None
        if result.returncode != 0:
            raise HarnessError(f"{label} failed with exit code {result.returncode}")
        return result.stdout

    def spawn(self, label, command, env, log):
        with open(log, "ab") as stream:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, env=env,
                                       cwd=self.work, start_new_session=True)
        self.processes.append((label, process))
        self.resources["processes"].append({"label": label, "pid": process.pid, "how": "spawned by this run"})
        return process

    def adopt(self, label, pid):
        self.resources["processes"].append({"label": label, "pid": pid, "how": "started by `suan server start` of this run"})

    def stop_spawned(self):
        """Stop each spawned process group. A process that exits between the poll and the signal is not an
        error; any other failure is recorded by type and the remaining processes are still stopped."""
        def signal_group(process, number):
            try:
                os.killpg(process.pid, number)
            except ProcessLookupError:
                pass  # the group already exited
        for label, process in reversed(self.processes):
            entry = {"label": label, "pid": process.pid}
            try:
                if process.poll() is None:
                    signal_group(process, signal.SIGTERM)
                    try:
                        process.wait(15)
                    except subprocess.TimeoutExpired:
                        signal_group(process, signal.SIGKILL)
                        process.wait(5)
            except Exception as exc:  # noqa: BLE001 - recorded; cleanup of the others continues
                entry["error"] = type(exc).__name__
            entry["exit_code"] = process.poll()
            self.resources["cleanup"].append(entry)

    def leftovers(self, *, terminate):
        """Processes still running inside this run's private directory (task workers, services); only these
        are ever signalled."""
        import psutil
        found = []
        for process in psutil.process_iter(["pid", "cwd"]):
            try:
                cwd = process.info["cwd"]
            except (psutil.Error, KeyError):
                continue
            if cwd and (cwd == str(self.work) or cwd.startswith(str(self.work) + os.sep)) and process.pid != os.getpid():
                found.append(process)
        if terminate:
            for process in found:
                try:
                    process.terminate()
                except psutil.Error:
                    pass
            psutil.wait_procs(found, timeout=10)
        return [process.pid for process in found]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_port(port, deadline):
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise Unknown(f"port {port} did not open before the deadline")


def python_cli(entry, prog):
    module, name = entry.rsplit(":", 1)
    return [sys.executable, "-c", f"from {module} import {name}; {name}(prog_name={prog!r})"]


# ----------------------------------------------------------------------------------------------------
# Deployments


def start_runtime(owned, state, env, label):
    port = free_port()
    cli = python_cli("suan.runtime.cli:server", "suan server")
    owned.run(f"{label} init", cli + ["--state-dir", str(state), "init", "--port", str(port)], env)
    owned.resources["directories"].append(f"{label}/runtime")
    owned.run(f"{label} start", cli + ["--state-dir", str(state), "start"], env, timeout=60)
    config = json.loads((state / "config.json").read_text(encoding="utf-8"))
    for component in ("api", "supervisor"):
        info = json.loads((state / f"{component}.pid").read_text(encoding="utf-8"))
        owned.adopt(f"{label} runtime {component}", info["pid"])
    wait_port(port, time.monotonic() + budget(20))
    from suan.runtime.client import RuntimeClient
    return (RuntimeClient(f"http://127.0.0.1:{port}", config["token"], timeout=HTTP_TIMEOUT), port,
            Path(config["workspace_root"]))


def stop_runtime(owned, state, env, label):
    cli = python_cli("suan.runtime.cli:server", "suan server")
    try:
        owned.run(f"{label} stop", cli + ["--state-dir", str(state), "stop", "--supervisor"], env, timeout=60,
                  cleanup=True)
        owned.resources["cleanup"].append({"label": f"{label} runtime", "stopped": True})
    except (HarnessError, subprocess.TimeoutExpired, OSError) as exc:
        owned.resources["cleanup"].append({"label": f"{label} runtime", "stopped": False, "error": type(exc).__name__})


def start_hub(owned, base, env, runtime_state):
    from suan.desktop_bridge.hub import HubClient
    control_state, node_state = base / "control", base / "node"
    templates = base / "templates.json"
    templates.write_text(json.dumps(TEMPLATES, ensure_ascii=False), encoding="utf-8")
    control = python_cli("suan.control.cli:control", "suan-control")
    node = python_cli("suan.control.cli:node", "suan-node")
    owned.run("B control init", control + ["init", "--state-dir", str(control_state)], env)
    owned.resources["directories"] += ["B/control", "B/node"]
    port = free_port()
    owned.spawn("B hub serve", control + ["serve", "--state-dir", str(control_state), "--port", str(port),
                                          "--template-file", str(templates), "--upload-min-free-mib", "0"],
                env, base / "control.log")
    wait_port(port, time.monotonic() + budget(30))
    url = f"http://127.0.0.1:{port}"
    code = json.loads(owned.run("B pair node", control + ["pair", "--state-dir", str(control_state), "--role", "node"],
                                env))["code"]
    owned.run("B node pair", node + ["pair", "--control-url", url, "--name", "parity-node", "--runtime-state-dir",
                                     str(runtime_state), "--state-dir", str(node_state)], env, stdin=code + "\n")
    owned.spawn("B node run", node + ["run", "--state-dir", str(node_state)], env, base / "node.log")
    code = json.loads(owned.run("B pair client", control + ["pair", "--state-dir", str(control_state), "--role",
                                                             "client"], env))["code"]
    claimed = HubClient(url, timeout=HTTP_TIMEOUT).request("POST", "pairings/claim",
                                                           {"code": code, "name": "parity-client"})
    node_id = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    return HubClient(url, claimed["token"], timeout=HTTP_TIMEOUT), node_id, port


def wait_node_live(backend, deadline):
    """The outbound node is online and advertises exact task reads (heartbeat snapshot)."""
    while time.monotonic() < deadline:
        try:
            health = backend.health()
            if health.get("online") and {"read", "task.get"} <= set(health.get("node_features") or ()):
                return health
        except Exception:  # noqa: BLE001 - the node may not have reported yet
            pass
        time.sleep(0.2)
    raise Unknown("the node did not come online with exact task reads before the deadline")


# ----------------------------------------------------------------------------------------------------
# One side's task semantics


class Side:
    def __init__(self, name, backend, observer, workspace_root, log):
        """``observer`` and ``workspace_root`` are this deployment's own Runtime (owned by this run): the
        authority whose task records and run directories count real executions."""
        self.name, self.backend, self.observer, self.log = name, backend, observer, log
        self.workspace_root = workspace_root

    def record(self, operation, **fields):
        self.log.append({"side": self.name, "operation": operation, **fields})

    def submit(self, template, key, workspace_id):
        from suan.desktop_bridge.protocol import BridgeError
        started = time.monotonic()
        try:
            if self.backend.kind == "runtime":
                spec = {**TEMPLATES[template], "workspace_id": workspace_id, "name": template}
                result = self.backend.submit(spec, key)
            else:
                result = self.backend.submit(None, key, template=template, workspace_id=workspace_id)
        except BridgeError as exc:
            self.record("task.submit", key=key, template=template, outcome="error", code=exc.code,
                        elapsed_ms=round(1000 * (time.monotonic() - started)))
            raise
        task = result.get("task")
        self.record("task.submit", key=key, template=template, outcome="accepted" if task else "pending",
                    task_id=task and task["id"], action_state=(result.get("action") or {}).get("state"),
                    elapsed_ms=round(1000 * (time.monotonic() - started)))
        if not task:
            raise Unknown(f"{self.name}: submission was not accepted before the action deadline")
        return task

    def task(self, task_id):
        if self.backend.kind == "runtime":
            return self.backend.task(task_id)["task"]
        return self.backend.task(task_id, require_live=True)["task"]


def wait_terminal(side, task_id, timeout, *, until=TERMINAL):
    """Poll the exact task until it reaches ``until`` or the deadline; never resubmits. Unreachable reads
    (a node or service restarting) are retried, not treated as task failure."""
    from suan.desktop_bridge.protocol import BridgeError
    deadline = time.monotonic() + remaining(timeout)
    last, unreachable = None, 0
    while time.monotonic() < deadline:
        try:
            last = side.task(task_id)
        except BridgeError as exc:
            if exc.code not in ("unavailable", "timeout", "remote_error"):
                raise
            unreachable += 1
        else:
            if last["state"] in until:
                return last
        time.sleep(0.2)
    raise Unknown(f"{side.name}: task did not reach {until} before the deadline "
                  f"(last state {last and last['state']}, unreachable reads {unreachable})")


def read_logs(side, task_id, stream="stdout"):
    """The whole stream by byte cursor (offset/next_offset), after the task is terminal."""
    data, offset = b"", 0
    for _ in range(200):
        page = side.backend.logs(task_id, stream, offset, 4096)
        if page["offset"] != offset:
            raise AssertionError(f"{side.name}: log page starts at {page['offset']}, expected {offset}")
        data += page["data"]
        if page["next_offset"] != offset + len(page["data"]):
            raise AssertionError(f"{side.name}: next_offset is not offset + bytes")
        offset = page["next_offset"]
        if page["terminal"] and not page["data"]:
            return data
    raise Unknown(f"{side.name}: the log did not end within 200 pages")


def wait_output(side, task_id, marker, timeout):
    """Whether ``marker`` appears on stdout before the deadline (byte-cursor reads; a timeout is unknown)."""
    from suan.desktop_bridge.protocol import BridgeError
    deadline = time.monotonic() + remaining(timeout)
    seen = b""
    while time.monotonic() < deadline:
        try:
            page = side.backend.logs(task_id, "stdout", 0, 4096)
            seen = page["data"]
        except BridgeError as exc:
            if exc.code not in ("unavailable", "timeout", "remote_error"):
                raise
        if marker in seen:
            return True
        time.sleep(0.2)
    raise Unknown(f"{side.name}: the waiting program printed nothing before the deadline")


def download(side, task_id, item):
    data, offset = b"", 0
    while offset < item["size"]:
        chunk = side.backend.read_chunk("task", task_id, item["path"], offset)
        if not chunk:
            break
        data += chunk
        offset += len(chunk)
    return data


def normalized(task):
    keys = ("state", "cancel_requested", "reason")
    return {key: task.get(key) for key in keys}


TIME_FIELDS = ("created_at", "updated_at", "attempted_at", "started_at", "finished_at")


def utc_timestamp(value):
    """An aware UTC ISO timestamp. Invalid metadata is never copied into exported evidence."""
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return False
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)
    except ValueError:
        return False


def timestamp_fields(task):
    """Keep missing/null/invalid distinct; only valid timestamps may retain their actual string value."""
    result = {}
    for key in TIME_FIELDS:
        value = task.get(key)
        kind = "missing" if key not in task else "null" if value is None else "utc" if utc_timestamp(value) else "invalid"
        result[key] = {"kind": kind, **({"value": value} if kind == "utc" else {})}
    return result


def time_proof(observed, authority, task_id):
    """Terminal metadata compared with this task's own Runtime, never the other deployment's clock."""
    return {"same_task": observed.get("id") == authority.get("id") == task_id,
            "same_state": observed.get("state") == authority.get("state"),
            "observed": timestamp_fields(observed), "authority": timestamp_fields(authority)}


def valid_timestamp_field(field):
    return isinstance(field, dict) and field.get("kind") == "utc" and utc_timestamp(field.get("value"))


def matching_task_times(proof):
    """All five fields are required only for these fixtures, which ran before completing/cancelling.
    Queued, pre-dispatch cancelled and deferred tasks are allowed different shapes by the product contract.
    No ordering between wall-clock times is assumed, even within one host.
    """
    if not isinstance(proof, dict) or proof.get("same_task") is not True or proof.get("same_state") is not True:
        return False
    observed, authority = proof.get("observed"), proof.get("authority")
    return (isinstance(observed, dict) and isinstance(authority, dict)
            and set(observed) == set(authority) == set(TIME_FIELDS)
            and all(valid_timestamp_field(value) for value in observed.values()) and observed == authority)


def stable_created_at(observations):
    if not isinstance(observations, dict) or set(observations) != {"submitted", "replayed", "final"}:
        return False
    return (all(valid_timestamp_field(value) for value in observations.values())
            and observations["submitted"] == observations["replayed"] == observations["final"])


def artifact_facts(items):
    """This public fixture only expects text/plain. Reject unexpected metadata before evidence retains it."""
    result = []
    for item in items:
        if item.get("media_type") != "text/plain":
            raise HarnessError("artifact media type differs from the fixed text/plain fixture")
        result.append({key: item.get(key) for key in ("path", "size", "sha256", "media_type")})
    return sorted(result, key=lambda item: item["path"])


def exercise(side):
    """The fixed scenario on one side; returns comparable facts and that side's own identities."""
    from suan.desktop_bridge.protocol import BridgeError
    facts = {"identities": {}}
    created = side.backend.create_workspace("parity", key="parity-workspace")
    workspace = (created.get("workspace") or {}).get("id")
    if not workspace:
        raise Unknown(f"{side.name}: workspace creation did not finish")
    facts["identities"]["workspace_id"] = workspace
    side.record("workspace.create", key="parity-workspace", outcome="created", workspace_id=workspace)

    task = side.submit("parity-done", "parity-done-1", workspace)
    facts["identities"]["done_task_id"] = task["id"]
    final = wait_terminal(side, task["id"], 60)
    facts["done"] = normalized(final)
    facts["time_observations"] = {"done": time_proof(final, side.observer.task(task["id"]), task["id"])}

    replay = side.submit("parity-done", "parity-done-1", workspace)
    facts["replay_same_task"] = replay["id"] == task["id"]
    facts["created_at_replay"] = {name: timestamp_fields(value)["created_at"]
                                 for name, value in (("submitted", task), ("replayed", replay), ("final", final))}

    try:
        side.submit("parity-wait", "parity-done-1", workspace)  # same key, a different request
        facts["conflict"] = {"refused": False}
    except BridgeError as exc:
        facts["conflict"] = {"refused": True, "code": exc.code}

    exact = side.task(task["id"])
    facts["exact_get"] = normalized(exact)
    facts["exact_get_has_spec"] = "spec" in exact
    facts["time_observations"]["exact"] = time_proof(exact, side.observer.task(task["id"]), task["id"])

    artifacts = artifact_facts(side.backend.artifacts(task["id"])["artifacts"])
    facts["artifacts"] = artifacts
    facts["downloads"] = {a["path"]: hashlib.sha256(download(side, task["id"], a)).hexdigest() for a in artifacts}

    log = read_logs(side, task["id"])
    facts["stdout_sha256"], facts["stdout_bytes"] = hashlib.sha256(log).hexdigest(), len(log)
    middle = log.index("✓".encode("utf-8")) + 1  # inside a three-byte character
    page = side.backend.logs(task["id"], "stdout", middle, 4096)
    data = page["data"]
    facts["log_cursor_inside_character"] = {
        "offset": page["offset"], "bytes": len(data),
        "is_raw_suffix": bool(data) and data == log[middle:middle + len(data)]
        and page["next_offset"] == middle + len(data)}

    waiting = side.submit("parity-wait", "parity-wait-1", workspace)
    facts["identities"]["wait_task_id"] = waiting["id"]
    running = wait_terminal(side, waiting["id"], 60, until=("running", *TERMINAL))
    facts["wait_reached"] = running["state"]
    # A "running" record can precede the program's launch; cancel only once the program itself has
    # written its first line, so the cancel stops a real running process.
    facts["program_started_before_cancel"] = wait_output(side, waiting["id"], "waiting 等待".encode("utf-8"), 60)
    cancelled = side.backend.cancel(waiting["id"], key="parity-cancel")
    side.record("task.cancel", key="parity-cancel", task_id=waiting["id"],
                outcome=((cancelled.get("task") or {}).get("state")) or (cancelled.get("action") or {}).get("state"))
    after = wait_terminal(side, waiting["id"], 60)
    facts["cancel"] = normalized(after)
    facts["time_observations"]["cancel"] = time_proof(after, side.observer.task(waiting["id"]), waiting["id"])
    # Repeating the cancel: a direct Runtime returns the current record; a Hub replays the original
    # action's result (the record as it was when that cancel ran). Both keep the task cancelled.
    again = side.backend.cancel(waiting["id"], key="parity-cancel")
    facts["cancel_replay_state"] = (again.get("task") or {}).get("state")
    after_replay = side.task(waiting["id"])
    facts["cancel_after_replay"] = normalized(after_replay)
    facts["time_observations"]["cancel_after_replay"] = time_proof(
        after_replay, side.observer.task(waiting["id"]), waiting["id"])

    # Execution count from this deployment's own Runtime (the authority of these tasks): its task records
    # and the run directories its workers created, with the real program/worker process identities.
    facts["executions_in_workspace"] = len(side.observer.tasks(workspace))
    facts["executions"] = executions(side, workspace)
    return facts


MARKER_LINE = re.compile(r"start ([1-9][0-9]{0,9})")


def process_identity(record):
    """A recorded process identity ``{pid, create_time}`` with a positive integer PID and a finite positive
    create time, or None (a missing, malformed or forged record never counts as an exited process)."""
    if not isinstance(record, dict):
        return None
    pid, created = record.get("pid"), record.get("create_time")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if isinstance(created, bool) or not isinstance(created, (int, float)) or not math.isfinite(created) or created <= 0:
        return None
    return {"pid": pid, "create_time": created}


def marker_pids(text):
    """The PIDs of a start marker; None if any line is not exactly ``start <positive pid>``."""
    pids = []
    for line in text.split("\n")[:-1] if text.endswith("\n") else text.split("\n"):
        match = MARKER_LINE.fullmatch(line)
        if not match:
            return None
        pids.append(int(match.group(1)))
    return pids


def executions(side, workspace, timeout=15):
    """Per run directory of the workspace: the start markers the program itself appended in that run
    directory (one per real execution), whether that single marker carries the PID of the program process the
    Runtime recorded (the worker execs the program in place, so it is the same PID), and whether the recorded
    worker and program processes have exited (valid PID plus create time, no longer alive)."""
    from suan.runtime.common import alive
    runs = side.workspace_root / workspace / "runs"
    result = []
    for run_dir in sorted(path for path in runs.iterdir() if path.is_dir()):
        def load(name):
            try:
                return process_identity(json.loads((run_dir / name).read_text(encoding="utf-8")))
            except (OSError, ValueError):
                return None
        program, worker = load("program.json"), load("worker.json")
        deadline = time.monotonic() + remaining(timeout)
        while (alive(program) or alive(worker)) and time.monotonic() < deadline:
            time.sleep(0.2)
        try:
            pids = marker_pids((run_dir / START_MARKER).read_text(encoding="ascii"))
        except FileNotFoundError:
            pids = []
        except (OSError, ValueError):
            pids = None
        result.append({"start_markers": len(pids) if pids is not None else None,
                       "marker_lines_valid": pids is not None,
                       "marker_pid_is_program": bool(pids) and len(pids) == 1 and program is not None
                       and pids[0] == program["pid"],
                       "program_recorded": program is not None,
                       "program_exited": program is not None and not alive(program),
                       "worker_exited": worker is not None and not alive(worker),
                       "finished_record": (run_dir / "finished.json").exists()})
    return result


# ----------------------------------------------------------------------------------------------------
# Comparison and evidence


def compare(a, b):
    rows = []

    def row(command, rule, value_a, value_b, category, equal=None):
        same = (value_a == value_b) if equal is None else equal
        rows.append({"command": command, "rule": rule, "A": value_a, "B": value_b, "category": category, "equal": same})

    row("task.submit+wait", "terminal state of the completed task", a["done"], b["done"], "business")
    row("task.submit replay", "same key on the same path returns the original task", a["replay_same_task"],
        b["replay_same_task"], "business")
    row("task.submit conflict", "same key with a different request is refused as conflict",
        a["conflict"], b["conflict"], "business")
    row("task.get", "exact state fields (B: live read, require_live)", a["exact_get"], b["exact_get"], "business")
    row("task.get spec", "A returns the spec; B's projection omits it", a["exact_get_has_spec"],
        b["exact_get_has_spec"], "projection", equal=a["exact_get_has_spec"] and not b["exact_get_has_spec"])
    row("task.artifacts", "{path,size,sha256,media_type} list", a["artifacts"], b["artifacts"], "business")
    row("file.read", "downloaded bytes match the listed sha256", a["downloads"], b["downloads"], "business",
        equal=a["downloads"] == b["downloads"] == {x["path"]: x["sha256"] for x in a["artifacts"]})
    row("task.logs", "the same stdout bytes", [a["stdout_sha256"], a["stdout_bytes"]],
        [b["stdout_sha256"], b["stdout_bytes"]], "business")
    row("task.logs cursor", "an offset inside a UTF-8 character returns raw bytes from that offset",
        a["log_cursor_inside_character"], b["log_cursor_inside_character"], "business")
    row("task.cancel", "terminal state after an explicit cancel", a["cancel"], b["cancel"], "business")
    row("task.cancel replay", "repeating the cancel keeps the task cancelled (exact read afterwards)",
        a["cancel_after_replay"], b["cancel_after_replay"], "business")
    row("task.cancel replay reply", "A answers with the current record; B replays the original action result",
        a["cancel_replay_state"], b["cancel_replay_state"], "projection", equal=True)
    row("executions", "tasks in the workspace after replay and conflict (no duplicate start)",
        a["executions_in_workspace"], b["executions_in_workspace"], "business")
    row("executions on disk", "each run directory: exactly one start marker, program and worker exited, finished",
        a["executions"], b["executions"], "business")
    row("identities", "each path keeps its own authority's IDs; equality is not required",
        sorted(a["identities"]), sorted(b["identities"]), "projection")
    row("task times", "each terminal live observation preserves its own Runtime's exact UTC time fields; "
        "absolute timestamps are not compared across deployments", a.get("time_observations"), b.get("time_observations"),
        "business", equal=all(matching_task_times(side.get("time_observations", {}).get(name))
                              for side in (a, b) for name in ("done", "exact", "cancel", "cancel_after_replay")))
    row("task created_at replay", "same-path submit replay preserves the original creation timestamp",
        a.get("created_at_replay"), b.get("created_at_replay"), "business",
        equal=all(stable_created_at(side.get("created_at_replay")) for side in (a, b)))
    return rows


EXPECTED_ARTIFACTS = [{"path": "out.txt", "size": len(EXPECTED_OUT), "sha256": hashlib.sha256(EXPECTED_OUT).hexdigest(),
                       "media_type": "text/plain"}]
EXPECTED_RUN = {"start_markers": 1, "marker_lines_valid": True, "marker_pid_is_program": True,
                "program_recorded": True, "program_exited": True, "worker_exited": True, "finished_record": True}


def assertions(a, b, rows):
    expected_downloads = {item["path"]: item["sha256"] for item in EXPECTED_ARTIFACTS}
    checks = [
        ("A1 completed", a["done"]["state"] == "succeeded" and b["done"]["state"] == "succeeded"),
        ("A2 same-path replay returns the original task", a["replay_same_task"] and b["replay_same_task"]),
        ("A3 different request with a used key is a conflict",
         a["conflict"] == {"refused": True, "code": "conflict"} == b["conflict"]),
        ("A4 exact live task.get matches", a["exact_get"] == b["exact_get"]),
        ("A5 exactly out.txt with the fixed expected bytes, listed and downloaded, on both sides",
         a["artifacts"] == EXPECTED_ARTIFACTS == b["artifacts"]
         and a["downloads"] == expected_downloads == b["downloads"]),
        ("A6 identical non-empty stdout bytes and a byte cursor inside a UTF-8 character on both sides",
         a["stdout_bytes"] > 0 and (a["stdout_sha256"], a["stdout_bytes"]) == (b["stdout_sha256"], b["stdout_bytes"])
         and a["log_cursor_inside_character"]["is_raw_suffix"] and b["log_cursor_inside_character"]["is_raw_suffix"]),
        ("A7 explicit cancel ends cancelled and stays cancelled after a repeated cancel",
         a["cancel"]["state"] == "cancelled" == b["cancel"]["state"]
         and a["cancel_after_replay"]["state"] == "cancelled" == b["cancel_after_replay"]["state"]),
        ("A8 two task records per workspace: no duplicate start", a["executions_in_workspace"] == 2 == b["executions_in_workspace"]),
        ("A9 exactly two run directories per workspace, each with exactly one well-formed start marker whose PID "
         "is the recorded program's, and valid recorded worker and program identities that have exited",
         all(len(side["executions"]) == 2 and all(run == EXPECTED_RUN for run in side["executions"])
             for side in (a, b))),
        ("A10 completed live observations preserve all five UTC timestamps from their own Runtime",
         all(matching_task_times(side.get("time_observations", {}).get(name))
             for side in (a, b) for name in ("done", "exact"))),
        ("A11 same-path submit replay preserves the original created_at",
         all(stable_created_at(side.get("created_at_replay")) for side in (a, b))),
        ("A12 post-ready cancellation and repeated-cancel live reads preserve their own Runtime's timestamps",
         all(matching_task_times(side.get("time_observations", {}).get(name))
             for side in (a, b) for name in ("cancel", "cancel_after_replay"))),
    ]
    return [{"id": name, "status": "pass" if ok else "fail"} for name, ok in checks]


# The same probe runs inside this harness and in a child with the services' environment.
PROBE_FUNCTION = """
def probe(names):
    import hashlib, importlib.util
    from pathlib import Path
    import suan
    base = Path(suan.__file__).resolve().parent.parent
    modules = {}
    for name in names:
        origin = Path(importlib.util.find_spec(name).origin).resolve()
        modules[name] = {"path": origin.relative_to(base).as_posix(),
                         "sha256": hashlib.sha256(origin.read_bytes()).hexdigest()}
    return {"base": str(base), "modules": modules}
"""


def probe_here(names):
    namespace = {}
    exec(PROBE_FUNCTION, namespace)  # noqa: S102 - fixed local code, identical to the child probe
    return namespace["probe"](list(names))


def base_kind(base, root=ROOT):
    """``this source tree``, ``site-packages`` (an installed wheel) or ``other directory`` (another checkout,
    an editable install pointing elsewhere, or anything else)."""
    base = Path(base)
    if base == Path(root).resolve():
        return "this source tree"
    if base.name in ("site-packages", "dist-packages"):
        return "site-packages"
    return "other directory"


def classify_origins(mode, harness, services, root=ROOT):
    """Consistent only when the harness and the services resolve the same base directory and identical files
    (path and sha256) for every key module, and that base is what ``mode`` claims: this source tree for
    ``source``, an installed site-packages for ``installed``. Absolute paths are compared, never emitted."""
    same_base = Path(harness["base"]) == Path(services["base"])
    same_modules = harness["modules"] == services["modules"]
    kind = base_kind(services["base"], root)
    claimed = {"source": "this source tree", "installed": "site-packages"}[mode]
    return {"mode": mode, "services_base": kind, "harness_base": base_kind(harness["base"], root),
            "same_base": same_base, "same_module_files": same_modules,
            "consistent": same_base and same_modules and kind == claimed,
            "modules": services["modules"]}


def module_origins(env, mode):
    """Where the services and this harness import STK from (relative paths and sha256 only)."""
    code = PROBE_FUNCTION + "\nimport json, sys\nprint(json.dumps(probe(sys.argv[1:])))\n"
    output = subprocess.run([sys.executable, "-c", code, *KEY_MODULES], capture_output=True, text=True,
                            env=env, timeout=budget(60), cwd=env["TMPDIR"], check=True).stdout
    origins = classify_origins(mode, probe_here(KEY_MODULES), json.loads(output))
    origins["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return origins


def manifest(work_label, ports, origins):
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None
    versions = {}
    for name in ("suan_toolkits", "fastapi", "uvicorn", "httpx", "websockets", "psutil"):
        try:
            from importlib.metadata import version
            versions[name] = version(name)
        except Exception:  # noqa: BLE001
            versions[name] = None
    return {"schema": "stk-backend-parity-run/1",
            "checkout_head_for_reference": git("rev-parse", "HEAD"),
            "checkout_has_uncommitted_changes": bool(git("status", "--porcelain")),
            "module_origins": origins,
            "python": platform.python_version(), "platform": platform.system(), "machine": platform.machine(),
            "interpreter_is_venv": sys.prefix != sys.base_prefix,
            "packages": versions, "work_dir": work_label, "ports": ports,
            "deployments": {"A": ["A/runtime (api, supervisor)"],
                            "B": ["B/control (hub serve)", "B/node (node run)", "B/runtime (api, supervisor)"]},
            "templates": {k: {"argv_sha256": hashlib.sha256(json.dumps(v["argv"]).encode()).hexdigest(),
                              "outputs": v["outputs"]} for k, v in TEMPLATES.items()},
            "verified": ["task lifecycle semantics on one Linux host through two deployments"],
            "not_verified": ["project/conversation semantics (no cloud project service exists)",
                             "that this interpreter has only the minimal extras (run it with such a venv to check)",
                             "GUI-free imports inside the service processes (not inspected here)",
                             "Windows/macOS, other hosts or clusters", "real solvers, licensed software or scientific validity",
                             "authority identity beyond configuration fingerprints"]}


def remove_work(work):
    """Remove the private directory; True only when it is really gone."""
    shutil.rmtree(work, ignore_errors=True)
    return not Path(work).exists()


def cleanup_status(resources, keep):
    """Clean when the leftover scan ran and found no process of this run, every cleanup step succeeded (every
    Runtime stopped, every spawned process exited, no step failed) and, unless kept on request, the private
    directory is really gone (or was never created)."""
    steps = resources.get("cleanup", ())
    removed = resources.get("removed_work_dir") is True or resources.get("work_dir_created") is False
    return (resources.get("leftover_pids_after_cleanup") == []
            and all(item.get("stopped", True) and "error" not in item for item in steps)
            and all(item.get("exit_code", 0) is not None for item in steps)
            and (keep or removed))


def clean_up(owned, env, keep, clients):
    """Stop and remove only what this run created. Every step runs even if an earlier one failed; a failed
    step is recorded by type only and makes cleanup unclean."""
    resources = owned.resources

    def step(label, action):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - recorded; the remaining steps still run
            resources["cleanup"].append({"label": label, "error": type(exc).__name__})
            return None

    def cancel_open(client):
        for task in client.tasks():
            if task["state"] not in TERMINAL:
                client.cancel(task["id"])

    for label, client in clients:
        if client is not None:
            try:
                cancel_open(client)  # best effort; the owned-process sweeps below handle leftovers
            except Exception:  # noqa: BLE001
                pass
    step("spawned processes", owned.stop_spawned)

    def stop_one_runtime(label):
        state = owned.work / label / "runtime"
        if (state / "config.json").exists():
            stop_runtime(owned, state, env, label)

    for label in ("A", "B"):
        step(f"{label} runtime", lambda label=label: stop_one_runtime(label))
    resources["leftover_pids_after_stop"] = step("leftover scan", lambda: owned.leftovers(terminate=True))
    resources["leftover_pids_after_cleanup"] = step("leftover scan", lambda: owned.leftovers(terminate=False))
    resources["removed_work_dir"] = False if keep else bool(step("remove private directory",
                                                                 lambda: remove_work(owned.work)))
    resources["kept_work_dir"] = keep


def run(evidence, work_root=None, keep=False, mode="installed", deadline_seconds=170):
    global DEADLINE
    deadline_seconds = check_deadline(deadline_seconds)
    started = time.monotonic()
    DEADLINE = started + deadline_seconds
    owned, env = None, None
    resources = {"processes": [], "directories": [], "cleanup": [], "work_dir_created": False}
    log, result, error, origins, scenario_seconds = [], {}, None, None, None
    try:
        # Setup failures (an unusable --work-root, a broken install) are exported like any other error.
        owned = Owned(Path(tempfile.mkdtemp(prefix="stk-parity-", dir=work_root)))
        owned.resources.update({"work_dir_created": True})
        resources = owned.resources
        env = owned.env(mode)
        origins = module_origins(env, mode)
        if not origins["consistent"]:
            raise HarnessError(f"--mode {mode} does not match where STK is imported from (services: "
                               f"{origins['services_base']}, harness: {origins['harness_base']}, same base: "
                               f"{origins['same_base']}, same module files: {origins['same_module_files']})")
        work = owned.work
        client_a, port_a, root_a = start_runtime(owned, work / "A" / "runtime", env, "A")
        client_b, port_b, root_b = start_runtime(owned, work / "B" / "runtime", env, "B")
        hub, node_id, port_hub = start_hub(owned, work / "B", env, work / "B" / "runtime")
        from suan.desktop_bridge.backends import HubBackend, RuntimeBackend

        class BudgetedHubBackend(HubBackend):
            """Each Hub action waits at most 60 s and never past the run budget (a spent budget is Unknown)."""
            @property
            def wait(self):
                return budget(self._wait)

            @wait.setter
            def wait(self, value):
                self._wait = value

        side_a = Side("A", RuntimeBackend("runtime:parity-a", client_a), client_a, root_a, log)
        side_b = Side("B", BudgetedHubBackend("hub:parity-b", hub, node_id, wait=60), client_b, root_b, log)
        wait_node_live(side_b.backend, time.monotonic() + budget(30))
        a, b = exercise(side_a), exercise(side_b)
        rows = compare(a, b)
        result = {"rows": rows, "assertions": assertions(a, b, rows)}
        scenario_seconds = time.monotonic() - started
    except Exception as exc:  # noqa: BLE001 - evidence must still be written and owned processes stopped
        error = exported_error(exc)
    finally:
        if owned is None:
            resources["leftover_pids_after_cleanup"] = []  # nothing was created, so nothing can be left
        else:
            clean_up(owned, env, keep, (("A", locals().get("client_a")), ("B", locals().get("client_b"))))
    elapsed = round(time.monotonic() - started, 1)
    cleanup_ok = cleanup_status(resources, keep)
    checks = result.get("assertions", [])
    # The scenario must have finished within the budget; cleanup then has its own grace (CLEANUP_GRACE per step).
    within_deadline = scenario_seconds is not None and scenario_seconds <= deadline_seconds
    ok = (error is None and bool(checks) and all(item["status"] == "pass" for item in checks) and cleanup_ok
          and within_deadline)
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    ports = {k: v for k, v in (("A_runtime", locals().get("port_a")), ("B_runtime", locals().get("port_b")),
                               ("B_hub", locals().get("port_hub"))) if v}
    (evidence / "run-manifest.json").write_text(json.dumps({
        **manifest("<private temporary directory>", ports, origins), "deadline_seconds": deadline_seconds,
        "scenario_seconds": scenario_seconds, "within_deadline": within_deadline,
        "elapsed_seconds_including_cleanup": elapsed, "cleanup_grace_seconds_per_step": CLEANUP_GRACE,
        "error": error, "cleanup_ok": cleanup_ok, "ok": ok}, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(evidence / "requests.jsonl", "w", encoding="utf-8") as stream:
        for entry in log:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    (evidence / "backend-parity.json").write_text(json.dumps(result.get("rows", []), indent=1, ensure_ascii=False),
                                                  encoding="utf-8")
    (evidence / "assertions.json").write_text(json.dumps({"error": error, "assertions": checks, "cleanup_ok": cleanup_ok,
                                                          "within_deadline": within_deadline, "ok": ok},
                                                         indent=1, ensure_ascii=False), encoding="utf-8")
    (evidence / "resources.json").write_text(json.dumps(resources, indent=1), encoding="utf-8")
    return ok, error, elapsed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare task semantics of a direct Runtime and a Hub-node Runtime.")
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=("installed", "source"), default="installed",
                        help="installed: the interpreter's installed STK (nothing injected); source: this source tree "
                             "through PYTHONPATH. The run fails if the actual import origin differs.")
    parser.add_argument("--deadline", type=float, default=170,
                        help="Budget in seconds for setup and the scenario (finite, positive). Every wait and call is "
                             "bounded by it and a scenario that ends after it fails. Cleanup afterwards gets up to "
                             f"{CLEANUP_GRACE} s per step; use an external watchdog for an absolute limit.")
    parser.add_argument("--work-root", type=Path, default=None, help="Parent of the private temporary directory.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary deployments' state for inspection.")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        print("The STK Runtime and control service run on Linux only.", file=sys.stderr)
        return 2
    try:
        check_deadline(args.deadline)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.mode == "source" and str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        ok, error, elapsed = run(args.evidence_dir, args.work_root, args.keep, args.mode, args.deadline)
    except Exception as exc:  # noqa: BLE001 - e.g. an unwritable --evidence-dir; never print raw exception text
        ok, error, elapsed = False, exported_error(exc), None
    print(json.dumps({"ok": ok, "error": error, "elapsed_seconds": elapsed}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
