"""D1 node-disconnect slice (CL-D1-DISCONNECT-12): a real outbound NodeAgent goes offline while its Runtime
task keeps running; the same node profile reconnects and the Hub observes the same task exactly once.

One private loopback deployment, started with existing entry points through the helpers of ``offline.py``
(loaded by file path, never by putting a source tree on ``sys.path``):

* ``suan server init/start`` -- one Runtime API and supervisor;
* ``suan-control init/serve`` -- a real HTTP + WebSocket Hub with the exact ``parity-wait`` template;
* ``suan-node pair/run`` -- one outbound NodeAgent.

Scenario, through ``HubBackend`` unless stated:

1. Create one workspace and submit the waiting program once; wait until the program itself prints its ready
   line; record its program PID/create time and its single start marker.
2. Stop only the NodeAgent process group (SIGKILL) and reap it. The Hub, the Runtime and the program keep
   running. Wait (bounded) until the Hub reports the node offline. Exact live reads (``require_live``) must be
   refused as unavailable; the heartbeat snapshot is never taken as "missing" or "failed". No write is made.
3. Read the same task directly from this run's own Runtime (observation only, not a change of authority):
   still running, the same program process alive, still one start marker.
4. Restart the same NodeAgent with the same node state (no new pairing, workspace or submission). Wait for it
   to come online with exact reads and read the original task live. An unanswered read ends ``unknown``;
   nothing is resubmitted, cancelled or retried under another key.
5. Explicitly cancel the original task: it ends cancelled, the program and worker exit, the marker still has
   exactly one start, and the workspace has had exactly one task and one run directory throughout.

The Hub's read-only action listing is compared before the disconnect, while offline, after the reconnect
and after the cancel: only the explicit cancel adds an action. Then every process and directory of this run
is stopped and removed; a failed cleanup fails the run.

``--scenario offline-completion`` (CL-D1-X7-OFFLINE-COMPLETION-38; the default stays ``cancel`` above) runs the
same deployment with the release-gated synthetic program ``parity-release``, registered as one extra exact
template in this run's Hub only. The task completes while the NodeAgent is down:

1. As above: one workspace, one submission, the ready line, frozen program/worker identities, one start marker;
   the private release flag is absent and the task has no result. The Hub's heartbeat snapshot lists the task
   as running (the cached view exact reads must later refuse to serve).
2. SIGKILL and reap only the original NodeAgent; the Hub reports it offline. The one read between the kill and
   that report is recorded on its own (refused, never a state). After the report, exact live reads are refused
   ``unavailable`` because the node is offline, with the Hub answering its health (offline) right before and
   after each read; a timeout or an unanswered read does not count. The owned Runtime still runs the task (no
   result, no output file, the original program and worker alive).
3. Only after the Hub reported the node offline, the harness writes the program's private release flag in the
   run directory (outside the published working directory). With the NodeAgent still down, the owned Runtime
   reports the original task ``succeeded``; the original program and worker exit before any reconnect or
   cleanup. Exact Hub reads are still refused in the same strict way (never ``succeeded``, nor the stale
   heartbeat snapshot, nor a timeout or unknown read).
4. Restart the same node state. The first answered exact live read, whatever its state, is the original task,
   ``succeeded`` (only ``unavailable`` is retried; ``not_found`` or any other refusal fails at once). The fixed
   stdout (byte cursor) is read through the Hub; the artifact listing is compared with the fixed ``out.txt``
   path, size and SHA-256 before any content is read, then that file is downloaded and hash-checked. Both
   match the fixed bytes and the owned Runtime.
5. Throughout: one workspace, one submission, no cancel, one task, one run directory, one start; the action
   listing never changes after the submission.

Evidence (``--evidence-dir``, which must be new or empty): run-manifest.json, requests.jsonl, phases.json,
assertions.json, resources.json -- no tokens, pairing codes, environment values, absolute paths or raw
exception text. This is a software-behaviour check on one Linux host with a synthetic program. It does not
cover sites, licensed software, scientific validity, other hosts, or any failover.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
OFFLINE_FILE = HERE / "offline.py"


def load_offline():
    """The parity helpers of offline.py, loaded from this directory by file path (read-only reuse)."""
    spec = importlib.util.spec_from_file_location("backend_parity_offline_helpers", OFFLINE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


off = load_offline()

TEMPLATE = "parity-wait"  # the fixed public synthetic program: prints a ready line, then waits up to 120 s
READY = "waiting 等待".encode("utf-8")
WORKSPACE_KEY, SUBMIT_KEY, CANCEL_KEY = "disc-ws", "disc-wait", "disc-cancel"  # idempotency keys, not secrets
OFFLINE_WAIT = 40  # the Hub reports a node offline 20 s after its last heartbeat (sent every 3 s)
OFFLINE_READS = 3  # exact live reads attempted while the node is down
REFUSED_OFFLINE = ("unavailable", "timeout")  # the only acceptable answers to a live read of an offline node
SCENARIOS = ("cancel", "offline-completion")

# The offline-completion scenario's own public synthetic program. Like parity-wait it appends its start marker
# and prints the ready line; it then waits (up to 120 s) for a private release flag that the harness writes in the
# task's run directory -- the parent of its working directory, so the flag is never a published artifact. Only
# once released does it write the fixed out.txt and the fixed final line and exit 0; never released, it exits 3
# (failed), so it can never succeed on its own.
RELEASE_TEMPLATE = "parity-release"
RELEASE_FLAG = "parity-release.flag"
RELEASE_PROGRAM = (off._MARK +
                   "import sys, time\n"
                   "print('waiting 等待', flush=True)\n"
                   f"flag = os.path.join('..', {RELEASE_FLAG!r})\n"
                   "deadline = time.monotonic() + 120\n"
                   "while not os.path.exists(flag):\n"
                   "    if time.monotonic() >= deadline:\n"
                   "        print('never released 未释放', flush=True)\n"
                   "        sys.exit(3)\n"
                   "    time.sleep(0.1)\n"
                   "with open('out.txt', 'w', encoding='utf-8') as stream:\n"
                   "    stream.write('parity 结果\\n')\n"
                   "print('released 已释放 ✓', flush=True)\n")
RELEASE_TEMPLATES = {RELEASE_TEMPLATE: {"argv": ["{python}", "-c", RELEASE_PROGRAM], "outputs": ["out.txt"]}}
RELEASED_STDOUT = "waiting 等待\nreleased 已释放 ✓\n".encode("utf-8")
COMPLETION_KEYS = ("x7-ws", "x7-release")  # workspace and submission idempotency keys, not secrets
COMPLETION_WAIT = 30  # the released program ends within a second; the owned Runtime records it within this


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def budgeted_hub_backend():
    from suan.desktop_bridge.backends import HubBackend

    class BudgetedHubBackend(HubBackend):
        """Each Hub action waits at most its own limit and never past the run budget."""
        @property
        def wait(self):
            return off.budget(self._wait)

        @wait.setter
        def wait(self, value):
            self._wait = value

    return BudgetedHubBackend


# ----------------------------------------------------------------------------------------------------
# Observations


def identity_of(pid):
    """``{pid, create_time}`` of a live process, or None."""
    import psutil
    try:
        return {"pid": pid, "create_time": psutil.Process(pid).create_time()}
    except psutil.Error:
        return None


def alive(identity):
    from suan.runtime.common import alive as runtime_alive
    return identity is not None and runtime_alive(identity)


def running_execution(workspace_root, workspace, task_id):
    """The task's run directory while it should be running: the program and worker identities the Runtime
    recorded (validated), whether they are alive, and the start marker (strict ``start <pid>`` lines)."""
    runs = Path(workspace_root) / workspace / "runs"
    names = sorted(path.name for path in runs.iterdir() if path.is_dir()) if runs.is_dir() else []
    run_dir = runs / task_id

    def load(name):
        try:
            return off.process_identity(json.loads((run_dir / name).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    program, worker = load("program.json"), load("worker.json")
    try:
        pids = off.marker_pids((run_dir / off.START_MARKER).read_text(encoding="ascii"))
    except FileNotFoundError:
        pids = []
    except (OSError, ValueError):
        pids = None
    return {"run_directories": len(names), "run_dir_is_task": names == [task_id], "program": program,
            "worker": worker, "program_alive": alive(program), "worker_alive": alive(worker),
            "start_markers": len(pids) if pids is not None else None,
            "marker_pid_is_program": bool(pids) and len(pids) == 1 and program is not None and pids[0] == program["pid"]}


def classify_read(side, task_id):
    """One exact live read: refused (with its code), unknown, or answered (with the state it reported)."""
    from suan.desktop_bridge.protocol import BridgeError
    try:
        online = bool(side.backend.health().get("online"))
    except BridgeError:
        online = None
    try:
        task = side.task(task_id)
    except BridgeError as exc:
        return {"outcome": "refused", "code": exc.code, "hub_reported_online": online}
    except off.Unknown:
        return {"outcome": "unknown", "hub_reported_online": online}
    return {"outcome": "answered", "same_task": task.get("id") == task_id, "state": task.get("state"),
            "hub_reported_online": online}


def offline_read_ok(read):
    """A live read of an offline node may only be refused as unreachable or end unknown -- never a state."""
    return read.get("outcome") == "unknown" or (read.get("outcome") == "refused" and read.get("code") in REFUSED_OFFLINE)


def wait_offline(backend, timeout):
    """Seconds until the Hub reports the node offline (bounded). A Hub that cannot be reached proves nothing."""
    from suan.desktop_bridge.protocol import BridgeError
    started = time.monotonic()
    deadline = started + off.remaining(timeout)
    while time.monotonic() < deadline:
        try:
            if not backend.health().get("online"):
                return time.monotonic() - started
        except BridgeError:
            pass
        time.sleep(0.5)
    raise off.Unknown("the Hub did not report the node offline before the deadline")


def observe_live(side, task_id, timeout):
    """Read the original task live after the reconnect until it answers (running or terminal). Unreachable
    reads are retried within the deadline; an unanswered read is ``unknown``. Never writes.

    The default ``cancel`` scenario's reading: answered states other than running or terminal (``queued``)
    are skipped. The offline-completion scenario uses :func:`first_live_read` instead."""
    return off.wait_terminal(side, task_id, timeout, until=("running", *off.TERMINAL))


def first_live_read(side, task_id, timeout):
    """The first answered exact live read after the reconnect, whatever its state (X7). Only ``unavailable``
    (the node or Hub not reachable yet) is retried within the deadline; any other refusal -- ``not_found``,
    ``remote_error``, ``unsupported`` -- is raised at once and fails the run. Unanswered is ``unknown``.
    Never writes; the assertions judge the task and state of this one answer."""
    from suan.desktop_bridge.protocol import BridgeError
    deadline = time.monotonic() + off.remaining(timeout)
    unavailable = 0
    while time.monotonic() < deadline:
        try:
            answer = side.task(task_id)
        except BridgeError as exc:
            if exc.code != "unavailable":
                raise
            unavailable += 1
        else:
            if time.monotonic() >= deadline:
                break
            return answer, unavailable
        time.sleep(max(0, min(0.2, deadline - time.monotonic())))
    raise off.Unknown(f"{side.name}: no exact live read answered before the deadline "
                      f"(unavailable reads {unavailable})")


# HubBackend's own refusal of an exact read when the Hub's device listing (answered just now) reports the node
# offline. It is raised before any read is forwarded, so it is never a timeout of the Hub or the node.
NODE_OFFLINE_REFUSAL = "The execution node is offline"


def refusal_cause(exc):
    """A label for why an exact live read was refused; the message itself is never exported."""
    message = str(getattr(exc, "message", ""))
    if exc.code != "unavailable":
        return "other"
    if message.startswith(NODE_OFFLINE_REFUSAL):
        return "node_offline"  # the Hub answered and lists the node offline
    if "(503)" in message:
        return "hub_node_link_closed"  # the Hub has no link to the node yet still lists it online
    if "(504)" in message or "in time" in message:
        return "timeout"
    return "unreachable"


def offline_read(side, task_id):
    """One exact live read of the offline-completion scenario, with the Hub's node status read right before and
    right after it: refused (code and cause), unknown, or answered (with the state it reported)."""
    from suan.desktop_bridge.protocol import BridgeError

    def online():
        try:
            value = side.backend.device().get("online")
        except BridgeError:
            return None  # the Hub did not answer: nothing about the node is proven
        return value if type(value) is bool else None

    before = online()
    try:
        task = side.task(task_id)
    except BridgeError as exc:
        read = {"outcome": "refused", "code": exc.code, "cause": refusal_cause(exc)}
    except off.Unknown:
        read = {"outcome": "unknown"}
    else:
        read = {"outcome": "answered", "same_task": task.get("id") == task_id, "state": task.get("state")}
    return {**read, "hub_reported_online": before, "hub_reported_online_after": online()}


def node_offline_refusal(read):
    """The strict X7 refusal: the Hub answered its health right before and right after the read, both times
    reporting the node offline, and the read was refused ``unavailable`` because the node is offline. A
    timeout, an unreachable Hub or an unanswered (unknown) read never counts."""
    return (read.get("outcome") == "refused" and read.get("code") == "unavailable"
            and read.get("cause") == "node_offline" and read.get("hub_reported_online") is False
            and read.get("hub_reported_online_after") is False)


def fixture_listing(items):
    """The Hub's artifact list compared with the fixed public fixture before any content is read: exactly one
    item, ``out.txt`` with the fixed size, SHA-256 and media type. Anything else -- an unknown path, an extra
    or duplicate item, a malformed or oversized size -- raises a fixed message; the listed values are never
    exported. Returns the fixture's own descriptions (downloads use these, never the Hub's)."""
    expected = off.EXPECTED_ARTIFACTS
    if not isinstance(items, list) or len(items) != len(expected):
        raise off.HarnessError("the artifact list is not exactly the fixed out.txt fixture")
    for item, want in zip(items, expected):
        if not isinstance(item, dict):
            raise off.HarnessError("the artifact list is not exactly the fixed out.txt fixture")
        listed = {key: item.get(key) for key in want}
        if type(listed["size"]) is not int or type(listed["path"]) is not str or listed != want:
            raise off.HarnessError("the artifact list is not exactly the fixed out.txt fixture")
    return [dict(item) for item in expected]


def download_fixture(side, task_id, items):
    """Download the listed fixture only after :func:`fixture_listing` accepted the list."""
    listed = fixture_listing(items)
    return listed, {item["path"]: off.download(side, task_id, item) for item in listed}


def action_ledger(backend):
    """Every Hub action this client can see, from the read-only listing: {id: {kind, state}}."""
    return {item["id"]: {"kind": (item.get("request") or {}).get("kind"), "state": item.get("state")}
            for item in backend.call(backend.hub.actions)}


def kinds(ledger):
    return sorted(entry["kind"] for entry in ledger.values())


def stop_node(process, identity):
    """The fault injection: SIGKILL the NodeAgent's process group and reap it; nothing else is signalled.

    ``identity`` is the NodeAgent's ``{pid, create_time}`` frozen when it came online. The record shows whether
    that same process was still running immediately before the kill, whether the signal was delivered, the
    exit status, and whether the frozen identity is gone afterwards. A node that had already exited or
    crashed is not this scenario's fault and never counts as the intentional stop."""
    valid = off.process_identity(identity) is not None and identity["pid"] == process.pid
    running_before = process.poll() is None
    alive_before = valid and running_before and alive(identity)
    signal_sent = False
    if alive_before:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            signal_sent = True
        except ProcessLookupError:
            pass
    if signal_sent:
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            pass
    exit_code = process.poll()  # reaps a node that had already exited; never waits on one not signalled here
    return {"identity_valid": valid, "running_before_kill": running_before, "alive_before_kill": alive_before,
            "signal_sent": signal_sent, "exit_code": exit_code, "reaped": exit_code is not None,
            "killed_by_sigkill": exit_code == -signal.SIGKILL, "node_alive_after": alive(identity) if valid else None}


def exited(identity, timeout):
    """Whether a frozen original process identity is gone, waiting at most ``timeout`` (within the budget).
    A missing or malformed identity is never proof of an exit."""
    if off.process_identity(identity) is None:
        return False
    deadline = time.monotonic() + off.remaining(timeout)
    while alive(identity) and time.monotonic() < deadline:
        time.sleep(0.2)
    return not alive(identity)


# ----------------------------------------------------------------------------------------------------
# Scenario


def scenario(owned, env, facts, log, clients):
    from suan.desktop_bridge.backends import RuntimeBackend
    work = owned.work
    client, port_runtime, workspace_root = off.start_runtime(owned, work / "B" / "runtime", env, "B")
    clients.append(("B", client))
    hub, node_id, port_hub = off.start_hub(owned, work / "B", env, work / "B" / "runtime")
    facts["ports"] = {"runtime": port_runtime, "hub": port_hub}
    backend = budgeted_hub_backend()("hub:disconnect", hub, node_id, wait=60)
    direct = RuntimeBackend("runtime:disconnect-direct", client)  # this run's own Runtime, read-only here
    side = off.Side("B", backend, client, workspace_root, log)
    off.wait_node_live(backend, time.monotonic() + off.budget(30))
    node_state = work / "B" / "node"
    device_before = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    pids = {item["label"]: item["pid"] for item in owned.resources["processes"]}
    services = {label: identity_of(pids[label]) for label in ("B hub serve", "B runtime api", "B runtime supervisor")}
    node_process = next(process for label, process in owned.processes if label == "B node run")
    node_identity = identity_of(node_process.pid)  # the original NodeAgent, frozen once it is online

    # 1. One workspace, one submission, the program really running.
    created = backend.create_workspace("disconnect", key=WORKSPACE_KEY)
    workspace = (created.get("workspace") or {}).get("id")
    if not workspace:
        raise off.Unknown("workspace creation did not finish")
    side.record("workspace.create", key=WORKSPACE_KEY, outcome="created", workspace_id=workspace)
    task = side.submit(TEMPLATE, SUBMIT_KEY, workspace)
    task_id, submitted = task["id"], time.monotonic()
    state = off.wait_terminal(side, task_id, 60, until=("running", *off.TERMINAL))["state"]
    ready = off.wait_output(side, task_id, READY, 60)
    baseline = running_execution(workspace_root, workspace, task_id)
    program, worker = baseline["program"], baseline["worker"]  # the original identities, frozen here
    ledger_before = action_ledger(backend)
    facts["baseline"] = {"state": state, "ready": ready, "execution": baseline}

    # 2. Only the NodeAgent stops; reads while it is down.
    facts["node_stop"] = stop_node(node_process, node_identity)
    reads = [classify_read(side, task_id)]  # before the Hub has noticed: the read path itself is gone
    seconds_to_offline = wait_offline(backend, OFFLINE_WAIT)
    reads += [classify_read(side, task_id) for _ in range(OFFLINE_READS - 1)]

    # 3. Direct observation on the owned Runtime.
    direct_task = direct.task(task_id)["task"]
    during = running_execution(workspace_root, workspace, task_id)
    ledger_offline = action_ledger(backend)
    facts["offline"] = {"observed": True, "seconds_to_offline": round(seconds_to_offline, 1), "reads": reads,
                        "services_alive": {label: alive(identity) for label, identity in services.items()},
                        "direct_task": {"same_task": direct_task.get("id") == task_id, "state": direct_task.get("state")},
                        "execution": during}

    # 4. The same NodeAgent profile reconnects; the original task is read live.
    owned.spawn("B node run (restarted)", off.python_cli("suan.control.cli:node", "suan-node")
                + ["run", "--state-dir", str(node_state)], env, work / "B" / "node.log")
    off.wait_node_live(backend, time.monotonic() + off.budget(30))
    device_after = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    nodes = [d for d in backend.call(backend.hub.devices) if d.get("role") == "node" and not d.get("revoked")]
    live = observe_live(side, task_id, 30)
    after_reconnect = running_execution(workspace_root, workspace, task_id)
    ledger_reconnect = action_ledger(backend)
    facts["reconnect"] = {"same_node_device": device_after == device_before and [d["id"] for d in nodes] == [device_before],
                          "node_devices": len(nodes),
                          "live_task": {"same_task": live.get("id") == task_id, "state": live.get("state")},
                          "execution": after_reconnect}

    # 5. The explicit cancel of the original task.
    seconds_since_submit = time.monotonic() - submitted
    cancelled = backend.cancel(task_id, key=CANCEL_KEY)
    side.record("task.cancel", key=CANCEL_KEY, task_id=task_id,
                outcome=((cancelled.get("task") or {}).get("state")) or (cancelled.get("action") or {}).get("state"))
    final = off.wait_terminal(side, task_id, 60)
    # Before any cleanup: the cancel itself must have stopped the original processes (frozen identities, not
    # whatever the run directory's metadata says now). The final sweep stopping them would prove nothing.
    original_program_exited, original_worker_exited = exited(program, 15), exited(worker, 15)
    final_direct = direct.task(task_id)["task"]
    final_execution = running_execution(workspace_root, workspace, task_id)
    runs = off.executions(side, workspace)
    tasks_in_workspace = len(direct.tasks(workspace)["tasks"])
    ledger_final = action_ledger(backend)
    facts["cancel"] = {"seconds_since_submit": round(seconds_since_submit, 1), "state": final.get("state"),
                       "cancel_requested": final.get("cancel_requested"), "direct_state": final_direct.get("state"),
                       "same_program": final_execution["program"] == program,
                       "same_worker": final_execution["worker"] == worker,
                       "original_program_exited": original_program_exited,
                       "original_worker_exited": original_worker_exited, "runs": runs,
                       "tasks_in_workspace": tasks_in_workspace}
    added = {key: value for key, value in ledger_final.items() if key not in ledger_before}
    facts["actions"] = {"before": kinds(ledger_before), "offline": kinds(ledger_offline),
                        "reconnect": kinds(ledger_reconnect), "final": kinds(ledger_final),
                        "offline_unchanged": ledger_offline == ledger_before,
                        "reconnect_unchanged": ledger_reconnect == ledger_before,
                        "before_kept": set(ledger_before) <= set(ledger_final),
                        "added_by_cancel": kinds(added)}


def assertions(facts, requests):
    """D1-D10 over the recorded facts; any missing or malformed fact fails its check."""
    def check(predicate):
        try:
            return bool(predicate())
        except (KeyError, TypeError, AttributeError, IndexError):
            return False

    def running(execution, program, worker):
        """The original program and worker (frozen identities) are the ones recorded now, and both are alive."""
        return (execution["run_directories"] == 1 and execution["run_dir_is_task"]
                and off.process_identity(program) is not None and off.process_identity(worker) is not None
                and execution["program"] == program and execution["worker"] == worker
                and execution["program_alive"] and execution["worker_alive"] and execution["start_markers"] == 1
                and execution["marker_pid_is_program"])

    frozen = (facts.get("baseline") or {}).get("execution") or {}
    program, worker = frozen.get("program"), frozen.get("worker")
    stop, offline, again, cancel, actions = (facts.get(name) or {} for name in
                                             ("node_stop", "offline", "reconnect", "cancel", "actions"))
    checks = [
        ("D1 one submission; the program printed its ready line and runs with one start marker",
         lambda: facts["baseline"]["state"] == "running" and facts["baseline"]["ready"] is True
         and running(facts["baseline"]["execution"], program, worker)),
        ("D2 only the original NodeAgent was stopped: alive right before the intentional SIGKILL, killed by it, "
         "reaped and gone; the Hub, Runtime API and supervisor stayed alive",
         lambda: stop["identity_valid"] is True and stop["running_before_kill"] is True
         and stop["alive_before_kill"] is True and stop["signal_sent"] is True
         and stop["exit_code"] == -signal.SIGKILL and stop["killed_by_sigkill"] is True and stop["reaped"] is True
         and stop["node_alive_after"] is False
         and len(offline["services_alive"]) == 3 and all(offline["services_alive"].values())),
        ("D3 the Hub reported the node offline, and a live read was made while it did",
         lambda: offline["observed"] is True and any(read["hub_reported_online"] is False for read in offline["reads"])),
        ("D4 live exact reads while offline were refused as unavailable (never a task state or not-found)",
         lambda: len(offline["reads"]) >= 2 and all(offline_read_ok(read) for read in offline["reads"])),
        ("D5 the owned Runtime still ran the same task with the original program and worker and one start marker",
         lambda: offline["direct_task"] == {"same_task": True, "state": "running"}
         and running(offline["execution"], program, worker)),
        ("D6 no Hub action was created while offline or by the reconnect",
         lambda: actions["offline_unchanged"] is True and actions["reconnect_unchanged"] is True
         and actions["before"] == ["task.submit", "workspace.create"]),
        ("D7 the same node profile reconnected and the live read returned the original running task",
         lambda: again["same_node_device"] is True and again["node_devices"] == 1
         and again["live_task"] == {"same_task": True, "state": "running"}
         and running(again["execution"], program, worker)),
        ("D8 the explicit cancel ended the original task; the original program and worker exited before cleanup; "
         "one task, one run, one start",
         lambda: cancel["state"] == "cancelled" and cancel["cancel_requested"] is True
         and cancel["direct_state"] == "cancelled" and cancel["same_program"] is True
         and cancel["same_worker"] is True and cancel["original_program_exited"] is True
         and cancel["original_worker_exited"] is True
         and cancel["runs"] == [off.EXPECTED_RUN] and cancel["tasks_in_workspace"] == 1),
        ("D9 only the explicit cancel added a Hub action",
         lambda: actions["added_by_cancel"] == ["task.cancel"] and actions["before_kept"] is True),
        ("D10 requests: one workspace creation, one submission, one cancel",
         lambda: [entry["operation"] for entry in requests] == ["workspace.create", "task.submit", "task.cancel"]),
    ]
    return [{"id": name, "status": "pass" if check(predicate) else "fail"} for name, predicate in checks]


# ----------------------------------------------------------------------------------------------------
# The offline-completion scenario


def result_files(workspace_root, workspace, task_id):
    """Whether the run directory holds the private release flag, the worker's result record and the output."""
    run_dir = Path(workspace_root) / workspace / "runs" / task_id
    return {"release_flag": (run_dir / RELEASE_FLAG).exists(), "finished_record": (run_dir / "finished.json").exists(),
            "output_file": (run_dir / "work" / "out.txt").exists()}


def release(workspace_root, workspace, task_id):
    """Write the program's private release flag once (exclusive create; an existing flag is an error)."""
    path = Path(workspace_root) / workspace / "runs" / task_id / RELEASE_FLAG
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise off.HarnessError("the release flag already existed before this run released the program") from None
    try:
        os.write(fd, b"release\n")
    finally:
        os.close(fd)
    return True


def snapshot_state(backend, task_id):
    """The task's state in the Hub's last heartbeat snapshot (a cached view, never an authority), or None."""
    from suan.desktop_bridge.protocol import BridgeError
    try:
        found = [task for task in backend.tasks()["tasks"] if task.get("id") == task_id]
    except BridgeError:
        return None
    return found[0].get("state") if len(found) == 1 else None


def wait_snapshot(backend, task_id, state, timeout):
    """Wait (bounded) until a heartbeat snapshot lists the task in ``state``: the cached view that exact reads
    must later refuse to serve. Never writes; a snapshot that never shows it is unknown."""
    deadline = time.monotonic() + off.remaining(timeout)
    while time.monotonic() < deadline:
        if snapshot_state(backend, task_id) == state:
            return True
        time.sleep(0.5)
    raise off.Unknown("the heartbeat snapshot did not list the running task before the deadline")


def scenario_completion(owned, env, facts, log, clients):
    from suan.desktop_bridge.backends import RuntimeBackend
    work = owned.work
    client, port_runtime, workspace_root = off.start_runtime(owned, work / "B" / "runtime", env, "B")
    clients.append(("B", client))
    hub, node_id, port_hub = off.start_hub(owned, work / "B", env, work / "B" / "runtime",
                                           extra_templates=RELEASE_TEMPLATES)
    facts["ports"] = {"runtime": port_runtime, "hub": port_hub}
    backend = budgeted_hub_backend()("hub:x7-completion", hub, node_id, wait=60)
    direct = RuntimeBackend("runtime:x7-completion-direct", client)  # this run's own Runtime, read-only here
    side = off.Side("B", backend, client, workspace_root, log)
    authority = off.Side("B-direct", direct, client, workspace_root, [])  # reads only; never logged as requests
    off.wait_node_live(backend, time.monotonic() + off.budget(30))
    node_state = work / "B" / "node"
    device_before = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    pids = {item["label"]: item["pid"] for item in owned.resources["processes"]}
    services = {label: identity_of(pids[label]) for label in ("B hub serve", "B runtime api", "B runtime supervisor")}
    node_process = next(process for label, process in owned.processes if label == "B node run")
    node_identity = identity_of(node_process.pid)

    def node_runs():
        return [label for label, _ in owned.processes if label.startswith("B node run")]

    # 1. One workspace, one submission, the program really running and waiting for its release.
    workspace_key, submit_key = COMPLETION_KEYS
    created = backend.create_workspace("x7-completion", key=workspace_key)
    workspace = (created.get("workspace") or {}).get("id")
    if not workspace:
        raise off.Unknown("workspace creation did not finish")
    side.record("workspace.create", key=workspace_key, outcome="created", workspace_id=workspace)
    task = side.submit(RELEASE_TEMPLATE, submit_key, workspace)
    task_id = task["id"]
    state = off.wait_terminal(side, task_id, 60, until=("running", *off.TERMINAL))["state"]
    ready = off.wait_output(side, task_id, READY, 60)
    baseline = running_execution(workspace_root, workspace, task_id)
    program, worker = baseline["program"], baseline["worker"]  # the original identities, frozen here
    ledger_before = action_ledger(backend)
    cached = wait_snapshot(backend, task_id, "running", 15)  # heartbeats every 3 s
    facts["baseline"] = {"state": state, "ready": ready, "execution": baseline, "snapshot_running": cached,
                         "files": result_files(workspace_root, workspace, task_id)}

    # 2. Only the NodeAgent stops; reads while it is down; the owned Runtime still runs the unreleased task.
    facts["node_stop"] = stop_node(node_process, node_identity)
    # Between the kill and the Hub's heartbeat timeout the Hub still lists the node online; this read is
    # recorded on its own and never counts as an offline refusal.
    before_offline_report = offline_read(side, task_id)
    seconds_to_offline = wait_offline(backend, OFFLINE_WAIT)
    reads = [offline_read(side, task_id) for _ in range(OFFLINE_READS - 1)]
    before_release = direct.task(task_id)["task"]
    facts["offline"] = {"observed": True, "seconds_to_offline": round(seconds_to_offline, 1),
                        "read_before_offline_report": before_offline_report, "reads": reads,
                        "services_alive": {label: alive(identity) for label, identity in services.items()},
                        "direct_task": {"same_task": before_release.get("id") == task_id,
                                        "state": before_release.get("state")},
                        "execution": running_execution(workspace_root, workspace, task_id),
                        "files": result_files(workspace_root, workspace, task_id)}
    ledger_offline = action_ledger(backend)

    # 3. Release only now (the Hub has reported the node offline); the task completes on the owned Runtime while
    #    the NodeAgent stays down. The original processes must exit before any reconnect or cleanup.
    offline_confirmed = backend.device().get("online") is False and node_runs() == ["B node run"]
    released = offline_confirmed and release(workspace_root, workspace, task_id)
    if not released:
        raise off.HarnessError("the node was not confirmed offline; the program was not released")
    done = off.wait_terminal(authority, task_id, COMPLETION_WAIT)
    program_exited, worker_exited = exited(program, 15), exited(worker, 15)
    after_reads = [offline_read(side, task_id) for _ in range(2)]
    facts["completed_offline"] = {
        "released_after_offline_observed": released is True and offline_confirmed,
        "direct_task": {"same_task": done.get("id") == task_id, "state": done.get("state"),
                        "cancel_requested": done.get("cancel_requested")},
        "original_program_exited": program_exited, "original_worker_exited": worker_exited,
        "execution": running_execution(workspace_root, workspace, task_id),
        "files": result_files(workspace_root, workspace, task_id),
        "reads": after_reads, "snapshot_state": snapshot_state(backend, task_id),
        "node_runs": node_runs(), "node_exit_code": node_process.poll(),
        "services_alive": {label: alive(identity) for label, identity in services.items()}}
    ledger_completed = action_ledger(backend)

    # 4. The same node state reconnects; the first answered exact read, the logs and the artifact.
    owned.spawn("B node run (restarted)", off.python_cli("suan.control.cli:node", "suan-node")
                + ["run", "--state-dir", str(node_state)], env, work / "B" / "node.log")
    off.wait_node_live(backend, time.monotonic() + off.budget(30))
    device_after = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    nodes = [d for d in backend.call(backend.hub.devices) if d.get("role") == "node" and not d.get("revoked")]
    # The first answer, whatever its state (queued or a stale running fail C8); only unavailable is retried.
    live, unavailable_before_answer = first_live_read(side, task_id, 30)
    confirm = classify_read(side, task_id)
    facts["reconnect"] = {"same_node_device": device_after == device_before and [d["id"] for d in nodes] == [device_before],
                          "node_devices": len(nodes),
                          "first_live": {"same_task": live.get("id") == task_id, "state": live.get("state"),
                                         "cancel_requested": live.get("cancel_requested")},
                          "unavailable_before_answer": unavailable_before_answer, "confirm": confirm}
    stdout = off.read_logs(side, task_id)
    # The listing must be exactly the fixed fixture before any content is read (nothing is downloaded otherwise).
    listed, downloaded = download_fixture(side, task_id, backend.artifacts(task_id)["artifacts"])
    direct_stdout = off.read_logs(authority, task_id)
    direct_listed = off.artifact_facts(direct.artifacts(task_id)["artifacts"])
    facts["outputs"] = {
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(), "stdout_bytes": len(stdout),
        "stdout_is_fixed": stdout == RELEASED_STDOUT, "stdout_same_as_runtime": stdout == direct_stdout,
        "artifacts": listed, "artifacts_same_as_runtime": listed == direct_listed,
        "downloads": {path: hashlib.sha256(data).hexdigest() for path, data in downloaded.items()},
        "downloads_are_fixed": {path: data == off.EXPECTED_OUT for path, data in downloaded.items()}}
    ledger_reconnect = action_ledger(backend)

    # 5. One task, one run, one start; no cancel; the action listing never changed after the submission.
    final_direct = direct.task(task_id)["task"]
    final_execution = running_execution(workspace_root, workspace, task_id)
    facts["final"] = {"direct_state": final_direct.get("state"),
                      "cancel_requested": final_direct.get("cancel_requested"),
                      "same_program": final_execution["program"] == program,
                      "same_worker": final_execution["worker"] == worker,
                      "runs": off.executions(side, workspace), "tasks_in_workspace": len(direct.tasks(workspace)["tasks"])}
    ledger_final = action_ledger(backend)
    facts["actions"] = {"before": kinds(ledger_before), "final": kinds(ledger_final),
                        "unchanged": {"offline": ledger_offline == ledger_before,
                                      "completed_offline": ledger_completed == ledger_before,
                                      "reconnect": ledger_reconnect == ledger_before,
                                      "final": ledger_final == ledger_before}}


def completion_assertions(facts, requests):
    """C1-C12 of the offline-completion scenario; any missing or malformed fact fails its check."""
    def check(predicate):
        try:
            return bool(predicate())
        except (KeyError, TypeError, AttributeError, IndexError):
            return False

    frozen = (facts.get("baseline") or {}).get("execution") or {}
    program, worker = frozen.get("program"), frozen.get("worker")

    def running(execution):
        return (execution["run_directories"] == 1 and execution["run_dir_is_task"]
                and off.process_identity(program) is not None and off.process_identity(worker) is not None
                and execution["program"] == program and execution["worker"] == worker
                and execution["program_alive"] is True and execution["worker_alive"] is True
                and execution["start_markers"] == 1 and execution["marker_pid_is_program"] is True)

    def ended(execution):
        """The same original program and worker are recorded, and neither is alive; still one start."""
        return (execution["run_directories"] == 1 and execution["run_dir_is_task"]
                and off.process_identity(program) is not None and off.process_identity(worker) is not None
                and execution["program"] == program and execution["worker"] == worker
                and execution["program_alive"] is False and execution["worker_alive"] is False
                and execution["start_markers"] == 1 and execution["marker_pid_is_program"] is True)

    unreleased = {"release_flag": False, "finished_record": False, "output_file": False}
    stop, offline, done, again, outputs, final, actions = (facts.get(name) or {} for name in (
        "node_stop", "offline", "completed_offline", "reconnect", "outputs", "final", "actions"))
    expected_downloads = {item["path"]: item["sha256"] for item in off.EXPECTED_ARTIFACTS}
    checks = [
        ("C1 one submission; the program printed its ready line and runs unreleased with one start marker",
         lambda: facts["baseline"]["state"] == "running" and facts["baseline"]["ready"] is True
         and running(facts["baseline"]["execution"]) and facts["baseline"]["files"] == unreleased
         and facts["baseline"]["snapshot_running"] is True),
        ("C2 only the original NodeAgent was stopped by the intentional SIGKILL and reaped; the Hub, Runtime API "
         "and supervisor stayed alive",
         lambda: stop["identity_valid"] is True and stop["running_before_kill"] is True
         and stop["alive_before_kill"] is True and stop["signal_sent"] is True
         and stop["exit_code"] == -signal.SIGKILL and stop["killed_by_sigkill"] is True and stop["reaped"] is True
         and stop["node_alive_after"] is False
         and len(offline["services_alive"]) == 3 and all(offline["services_alive"].values())
         and len(done["services_alive"]) == 3 and all(done["services_alive"].values())),
        ("C3 the Hub reported the node offline, and exact live reads while it did were refused unavailable because "
         "the node is offline, the Hub answering offline right before and after each (never a timeout or unknown); "
         "the read between the kill and the offline report did not return a state",
         lambda: offline["observed"] is True and offline_read_ok(offline["read_before_offline_report"])
         and len(offline["reads"]) >= 2 and all(node_offline_refusal(read) for read in offline["reads"])),
        ("C4 the task had not finished before the disconnect: while offline and before the release, the owned "
         "Runtime still ran it with the original program and worker, no result and no output",
         lambda: offline["direct_task"] == {"same_task": True, "state": "running"}
         and running(offline["execution"]) and offline["files"] == unreleased),
        ("C5 released only after the Hub reported the node offline; with the NodeAgent still down the owned Runtime "
         "reports the original task succeeded, not cancelled",
         lambda: done["released_after_offline_observed"] is True
         and done["node_runs"] == ["B node run"] and done["node_exit_code"] == -signal.SIGKILL
         and done["direct_task"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
         and done["files"] == {"release_flag": True, "finished_record": True, "output_file": True}),
        ("C6 the original program and worker exited before any reconnect or cleanup; still one start",
         lambda: done["original_program_exited"] is True and done["original_worker_exited"] is True
         and ended(done["execution"])),
        ("C7 after the offline completion, exact Hub reads were still refused unavailable because the node is "
         "offline, the Hub answering offline right before and after each (a timeout or unknown read never counts), "
         "although its heartbeat snapshot still cached the task as running: neither the completed state nor the "
         "cache was served",
         lambda: len(done["reads"]) >= 2 and all(node_offline_refusal(read) for read in done["reads"])
         and done["snapshot_state"] == "running"),
        ("C8 the same node profile reconnected and the first answered exact live read, whatever its state, is the "
         "original task, succeeded",
         lambda: again["same_node_device"] is True and again["node_devices"] == 1
         and again["first_live"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
         and type(again["unavailable_before_answer"]) is int and again["unavailable_before_answer"] >= 0
         and again["confirm"] == {"outcome": "answered", "same_task": True, "state": "succeeded",
                                  "hub_reported_online": True}),
        ("C9 the fixed stdout bytes, read through the Hub by byte cursor, equal the owned Runtime's",
         lambda: outputs["stdout_is_fixed"] is True and outputs["stdout_same_as_runtime"] is True
         and outputs["stdout_sha256"] == hashlib.sha256(RELEASED_STDOUT).hexdigest()
         and outputs["stdout_bytes"] == len(RELEASED_STDOUT)),
        ("C10 exactly out.txt with the fixed bytes, listed and downloaded through the Hub and hash-checked",
         lambda: outputs["artifacts"] == off.EXPECTED_ARTIFACTS and outputs["artifacts_same_as_runtime"] is True
         and outputs["downloads"] == expected_downloads
         and outputs["downloads_are_fixed"] == {path: True for path in expected_downloads}),
        ("C11 one task, one run directory with one start whose program and worker exited; never cancelled",
         lambda: final["direct_state"] == "succeeded" and final["cancel_requested"] is False
         and final["same_program"] is True and final["same_worker"] is True
         and final["runs"] == [off.EXPECTED_RUN] and final["tasks_in_workspace"] == 1),
        ("C12 one workspace creation and one submission; no Hub action after the submission and no cancel",
         lambda: [entry["operation"] for entry in requests] == ["workspace.create", "task.submit"]
         and actions["before"] == ["task.submit", "workspace.create"] == actions["final"]
         and actions["unchanged"] == {"offline": True, "completed_offline": True, "reconnect": True, "final": True}),
    ]
    return [{"id": name, "status": "pass" if check(predicate) else "fail"} for name, predicate in checks]


# ----------------------------------------------------------------------------------------------------
# Run


def manifest(origins, ports):
    record = off.manifest("<private temporary directory>", ports, origins)
    record.pop("schema", None)  # informal trial evidence, not a published format
    record.update({
        "record": "D1 node-disconnect trial evidence (informal)",
        "deployments": {"B": ["B/runtime (api, supervisor)", "B/control (hub serve)",
                              "B/node (node run; killed, then restarted with the same node state)"]},
        "templates": {TEMPLATE: record["templates"][TEMPLATE]},
        "verified": ["on one Linux host: a Runtime task keeps running while its outbound NodeAgent is offline, and "
                     "the same node profile reconnects and observes the same task without a second start"],
        "not_verified": ["Hub restart, Runtime restart, network partitions without a process exit, or long outages",
                         "failover to another node or Runtime (none is attempted)",
                         "that no Hub action exists outside the client-visible listing (newest 200, plus reviews)",
                         "Windows/macOS, other hosts, sites or clusters",
                         "real solvers, licensed software or scientific validity"]})
    return record


def completion_manifest(origins, ports):
    record = manifest(origins, ports)
    template = RELEASE_TEMPLATES[RELEASE_TEMPLATE]
    record.update({
        "record": "D1 X7 offline-completion trial evidence (informal)",
        "scenario": "offline-completion",
        "templates": {RELEASE_TEMPLATE: {"argv_sha256": hashlib.sha256(json.dumps(template["argv"]).encode()).hexdigest(),
                                         "outputs": template["outputs"], "registered": "this run's Hub only"}},
        "verified": ["on one Linux host: a Runtime task completes normally on its original Runtime while its outbound "
                     "NodeAgent is killed and offline; exact Hub reads stay unavailable until the same node profile "
                     "reconnects, then read the same task succeeded with its fixed log and artifact bytes, without a "
                     "second submission, start or cancel"],
        "not_verified": ["Hub restart, Runtime restart, network partitions without a process exit, or long outages",
                         "completion timing other than one release after the Hub reported the node offline",
                         "failover to another node or Runtime (none is attempted)",
                         "that no Hub action exists outside the client-visible listing (newest 200, plus reviews)",
                         "Windows/macOS, other hosts, sites or clusters",
                         "real solvers, licensed software or scientific validity"]})
    return record


def run(evidence, work_root=None, keep=False, mode="installed", deadline_seconds=170, scenario_name="cancel"):
    if scenario_name not in SCENARIOS:
        raise ValueError("unknown scenario")
    play, judge, describe = ((scenario, assertions, manifest) if scenario_name == "cancel"
                             else (scenario_completion, completion_assertions, completion_manifest))
    deadline_seconds = off.check_deadline(deadline_seconds)
    started = time.monotonic()
    off.DEADLINE = started + deadline_seconds
    owned, env = None, None
    resources = {"processes": [], "directories": [], "cleanup": [], "work_dir_created": False}
    log, facts, clients, error, origins, scenario_seconds = [], {}, [], None, None, None
    try:
        owned = off.Owned(Path(tempfile.mkdtemp(prefix="stk-disconnect-", dir=work_root)))
        owned.resources["work_dir_created"] = True
        resources = owned.resources
        env = owned.env(mode)
        origins = off.module_origins(env, mode)
        origins["offline_helper_sha256"] = origins.pop("harness_sha256", None)
        origins["disconnect_sha256"] = sha256_file(__file__)
        if not origins["consistent"]:
            raise off.HarnessError(f"--mode {mode} does not match where STK is imported from")
        play(owned, env, facts, log, clients)
        scenario_seconds = time.monotonic() - started
    except Exception as exc:  # noqa: BLE001 - evidence is still written and owned processes stopped
        error = off.exported_error(exc)
    finally:
        if owned is None:
            resources["leftover_pids_after_cleanup"] = []
        else:
            off.clean_up(owned, env, keep, clients)
    elapsed = time.monotonic() - started
    cleanup_ok = off.cleanup_status(resources, keep)
    checks = judge(facts, log) if error is None else []
    within_deadline = scenario_seconds is not None and scenario_seconds <= deadline_seconds
    ok = error is None and bool(checks) and all(c["status"] == "pass" for c in checks) and cleanup_ok and within_deadline
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    ports = {f"B_{name}": port for name, port in (facts.get("ports") or {}).items()}
    phases = {key: value for key, value in facts.items() if key != "ports"}
    (evidence / "run-manifest.json").write_text(json.dumps({
        **describe(origins, ports), "deadline_seconds": deadline_seconds, "scenario_seconds": scenario_seconds,
        "within_deadline": within_deadline, "elapsed_seconds_including_cleanup": elapsed,
        "cleanup_grace_seconds_per_step": off.CLEANUP_GRACE, "error": error, "cleanup_ok": cleanup_ok, "ok": ok},
        indent=1, ensure_ascii=False), encoding="utf-8")
    with open(evidence / "requests.jsonl", "w", encoding="utf-8") as stream:
        for entry in log:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    (evidence / "phases.json").write_text(json.dumps(phases, indent=1, ensure_ascii=False), encoding="utf-8")
    (evidence / "assertions.json").write_text(json.dumps({"error": error, "assertions": checks, "cleanup_ok": cleanup_ok,
                                                          "within_deadline": within_deadline, "ok": ok},
                                                         indent=1, ensure_ascii=False), encoding="utf-8")
    (evidence / "resources.json").write_text(json.dumps(resources, indent=1), encoding="utf-8")
    return ok, error, elapsed


def main(argv=None):
    parser = argparse.ArgumentParser(description="A NodeAgent goes offline and reconnects while its task runs.")
    parser.add_argument("--evidence-dir", required=True, type=Path, help="A new or empty directory for this trial.")
    parser.add_argument("--mode", choices=("installed", "source"), default="installed",
                        help="installed: the interpreter's installed STK (nothing injected); source: this source tree "
                             "through PYTHONPATH. The run fails if the actual import origin differs.")
    parser.add_argument("--deadline", type=float, default=170,
                        help="Budget in seconds for setup and the scenario (finite, positive). Cleanup afterwards "
                             f"gets its own bounded grace per step (up to {off.CLEANUP_GRACE} s); use an external "
                             "watchdog for an absolute limit.")
    parser.add_argument("--work-root", type=Path, default=None, help="Parent of the private temporary directory.")
    parser.add_argument("--keep", action="store_true", help="Keep the deployment's state for inspection.")
    parser.add_argument("--scenario", choices=SCENARIOS, default="cancel",
                        help="cancel (default): the task still runs after the reconnect and is cancelled explicitly; "
                             "offline-completion: the task completes while the node is offline and is read back "
                             "after the reconnect, with no cancel.")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        print("The STK Runtime and control service run on Linux only.", file=sys.stderr)
        return 2
    try:
        off.check_deadline(args.deadline)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        if args.evidence_dir.exists() and any(args.evidence_dir.iterdir()):
            print("--evidence-dir must be a new or empty directory (earlier trials are never overwritten).",
                  file=sys.stderr)
            return 2
    except OSError:
        print("--evidence-dir cannot be inspected.", file=sys.stderr)
        return 2
    if args.mode == "source":
        root = str(HERE.parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        ok, error, elapsed = run(args.evidence_dir, args.work_root, args.keep, args.mode, args.deadline,
                                 args.scenario)
    except Exception as exc:  # noqa: BLE001 - never print raw exception text
        ok, error, elapsed = False, off.exported_error(exc), None
    print(json.dumps({"ok": ok, "error": error, "elapsed_seconds": elapsed}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
