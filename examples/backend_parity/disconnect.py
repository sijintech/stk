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

``--scenario socket-partition`` (CL-D1-X7-SOCKET-PARTITION-64) is the offline-completion scenario with another fault:
nothing is signalled. The NodeAgent is paired with, and so connects through, a small loopback relay of this run
(``socket_partition.py``, loaded by file path); the harness's Hub and Runtime clients stay direct. The relay closes
the task's live control link and rejects every new tunnel; the Hub reports the node offline; the task is released
and completes; then the same relay, on the same address, forwards again and the same NodeAgent process reconnects by
itself with its unchanged profile. The NodeAgent, Hub, Runtime API and supervisor keep their PID and create time
throughout. The client is the in-process ``HubBackend`` (no strict stdio bridge subprocess). Checks P1-P15.

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
SCENARIOS = ("cancel", "offline-completion", "socket-partition")

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


def judged(checks):
    """Each ``(id, predicate)`` as pass/fail; a missing or malformed fact fails its check."""
    def check(predicate):
        try:
            return bool(predicate())
        except (KeyError, TypeError, AttributeError, IndexError):
            return False

    return [{"id": name, "status": "pass" if check(predicate) else "fail"} for name, predicate in checks]


def completion_assertions(facts, requests):
    """C1-C12 of the offline-completion scenario; any missing or malformed fact fails its check."""
    return judged(completion_checks(facts, requests))


def completion_checks(facts, requests):
    """The named C1-C12 predicates (also reused, under their own names, by the socket-partition scenario)."""
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
    return checks


# ----------------------------------------------------------------------------------------------------
# The socket-partition scenario


PARTITION_FILE = HERE / "socket_partition.py"
PARTITION_KEYS = ("x7p-ws", "x7p-release")  # workspace and submission idempotency keys, not secrets
RECONNECT_WAIT = 45  # the NodeAgent's own retry delay doubles up to 30 s while the relay rejects its tunnels
IDENTITIES = ("B node run", "B hub serve", "B runtime api", "B runtime supervisor")


def load_partition():
    """The relay of socket_partition.py, loaded from this directory by file path (stdlib only)."""
    spec = importlib.util.spec_from_file_location("backend_parity_socket_partition", PARTITION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def port_of(url):
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return parts.port if parts.hostname == "127.0.0.1" else None


def all_alive(identities):
    """The four frozen identities (PID plus create time) are all still the live processes."""
    return set(identities) == set(IDENTITIES) and all(value is True for value in identities.values())


def scenario_partition(owned, env, facts, log, clients):
    relay_module, relays = load_partition(), []

    def route(hub_port):
        relay = relay_module.Relay(hub_port)
        relays.append(relay)
        return relay.url

    try:
        play_partition(owned, env, facts, log, clients, route, relays)
    finally:
        for relay in relays:
            entry = {"label": "B socket relay"}
            try:
                entry["stopped"] = relay.close()
            except Exception as exc:  # noqa: BLE001 - recorded by type; cleanup is then unclean
                entry.update(stopped=False, error=type(exc).__name__)
            owned.resources["cleanup"].append(entry)


def play_partition(owned, env, facts, log, clients, route, relays):
    from suan.desktop_bridge.backends import RuntimeBackend
    work = owned.work
    client, port_runtime, workspace_root = off.start_runtime(owned, work / "B" / "runtime", env, "B")
    clients.append(("B", client))
    hub, node_id, port_hub = off.start_hub(owned, work / "B", env, work / "B" / "runtime",
                                           extra_templates=RELEASE_TEMPLATES, node_route=route)
    relay, = relays
    facts["ports"] = {"runtime": port_runtime, "hub": port_hub, "relay": relay.port}
    backend = budgeted_hub_backend()("hub:x7-partition", hub, node_id, wait=60)
    direct = RuntimeBackend("runtime:x7-partition-direct", client)  # this run's own Runtime, read-only here
    side = off.Side("B", backend, client, workspace_root, log)
    authority = off.Side("B-direct", direct, client, workspace_root, [])  # reads only; never logged as requests
    off.wait_node_live(backend, time.monotonic() + off.budget(30))
    node_state = work / "B" / "node"
    profile_bytes = (node_state / "node.json").read_bytes()
    profile = json.loads(profile_bytes)
    device_before = profile["device_id"]
    pids = {item["label"]: item["pid"] for item in owned.resources["processes"]}
    identities = {label: identity_of(pids[label]) for label in IDENTITIES}  # frozen once the node is online
    node_process = next(process for label, process in owned.processes if label == "B node run")

    def node_runs():
        return [label for label, _ in owned.processes if label.startswith("B node run")]

    def continuity():
        return {label: alive(identity) for label, identity in identities.items()}

    before_cut = relay.stats()
    facts["route"] = {"relay_loopback": relay.server_address[0] == "127.0.0.1",
                      "node_profile_via_relay": port_of(profile.get("control_url", "")) == relay.port,
                      "hub_client_direct": port_of(hub.url) == port_hub != relay.port,
                      "runtime_client_direct": port_of(client.url) == port_runtime != relay.port,
                      "node_identity_valid": (off.process_identity(identities["B node run"]) is not None
                                              and identities["B node run"]["pid"] == node_process.pid),
                      "tunnels_before_submission": before_cut["accepted"]}

    # 1. One workspace, one submission, the program really running and waiting for its release.
    workspace_key, submit_key = PARTITION_KEYS
    created = backend.create_workspace("x7-partition", key=workspace_key)
    workspace = (created.get("workspace") or {}).get("id")
    if not workspace:
        raise off.Unknown("workspace creation did not finish")
    side.record("workspace.create", key=workspace_key, outcome="created", workspace_id=workspace)
    submitted_at = time.monotonic()
    task_id = side.submit(RELEASE_TEMPLATE, submit_key, workspace)["id"]
    state = off.wait_terminal(side, task_id, 60, until=("running", *off.TERMINAL))["state"]
    ready = off.wait_output(side, task_id, READY, 60)
    baseline = running_execution(workspace_root, workspace, task_id)
    program, worker = baseline["program"], baseline["worker"]  # the original identities, frozen here
    ledger_before = action_ledger(backend)
    cached = wait_snapshot(backend, task_id, "running", 15)  # heartbeats every 3 s, through the relay
    facts["baseline"] = {"state": state, "ready": ready, "execution": baseline, "snapshot_running": cached,
                         "files": result_files(workspace_root, workspace, task_id)}

    # 2. The partition: the relay closes the live control link and rejects new tunnels. Nothing is signalled.
    cut = relay.cut(submitted_at)
    facts["partition"] = {**cut, "active_before_cut": cut["closed"],
                          "node_process_running": node_process.poll() is None, "identities_alive": continuity()}
    before_offline_report = offline_read(side, task_id)
    seconds_to_offline = wait_offline(backend, OFFLINE_WAIT)
    reads = [offline_read(side, task_id) for _ in range(OFFLINE_READS - 1)]
    before_release = direct.task(task_id)["task"]
    facts["offline"] = {"observed": True, "seconds_to_offline": round(seconds_to_offline, 1),
                        "read_before_offline_report": before_offline_report, "reads": reads,
                        "identities_alive": continuity(),
                        "direct_task": {"same_task": before_release.get("id") == task_id,
                                        "state": before_release.get("state")},
                        "execution": running_execution(workspace_root, workspace, task_id),
                        "files": result_files(workspace_root, workspace, task_id)}
    ledger_offline = action_ledger(backend)

    # 3. Release only now; the task completes on the owned Runtime while the partition holds. The original
    #    program and worker must exit before the relay is reopened.
    offline_confirmed = (backend.device().get("online") is False and node_runs() == ["B node run"]
                         and node_process.poll() is None and relay.stats()["forwarding"] is False)
    released = offline_confirmed and release(workspace_root, workspace, task_id)
    if not released:
        raise off.HarnessError("the node was not confirmed offline behind the partition; the program was not released")
    done = off.wait_terminal(authority, task_id, COMPLETION_WAIT)
    program_exited, worker_exited = exited(program, 15), exited(worker, 15)
    after_reads = [offline_read(side, task_id) for _ in range(2)]
    held = relay.stats()
    facts["completed_offline"] = {
        "released_after_offline_observed": released is True and offline_confirmed,
        "direct_task": {"same_task": done.get("id") == task_id, "state": done.get("state"),
                        "cancel_requested": done.get("cancel_requested")},
        "original_program_exited": program_exited, "original_worker_exited": worker_exited,
        "execution": running_execution(workspace_root, workspace, task_id),
        "files": result_files(workspace_root, workspace, task_id),
        "reads": after_reads, "snapshot_state": snapshot_state(backend, task_id),
        "node_runs": node_runs(), "node_exit_code": node_process.poll(), "identities_alive": continuity(),
        "relay": {"forwarding": held["forwarding"], "active": held["active"],
                  "accepted_during_partition": held["accepted"] - cut["accepted_before_cut"],
                  "rejected_during_partition": held["rejected"] - cut["rejected_before_cut"]}}
    ledger_completed = action_ledger(backend)

    # 4. Reopen the same relay; the same NodeAgent process reconnects by itself with the same profile.
    reopened, reopened_at = relay.reopen(), time.monotonic()
    off.wait_node_live(backend, time.monotonic() + off.budget(RECONNECT_WAIT))
    seconds_to_online = time.monotonic() - reopened_at
    nodes = [d for d in backend.call(backend.hub.devices) if d.get("role") == "node" and not d.get("revoked")]
    live, unavailable_before_answer = first_live_read(side, task_id, 30)
    confirm = classify_read(side, task_id)
    after = relay.stats()
    facts["reopen"] = {**reopened, "seconds_to_online": round(seconds_to_online, 1),
                       "accepted_after_reopen": after["accepted"] - held["accepted"], "active": after["active"],
                       "profile_unchanged": (node_state / "node.json").read_bytes() == profile_bytes,
                       "node_runs": node_runs(), "node_exit_code": node_process.poll(),
                       "identities_alive": continuity()}
    facts["reconnect"] = {"same_node_device": [d["id"] for d in nodes] == [device_before],
                          "node_devices": len(nodes),
                          "first_live": {"same_task": live.get("id") == task_id, "state": live.get("state"),
                                         "cancel_requested": live.get("cancel_requested")},
                          "unavailable_before_answer": unavailable_before_answer, "confirm": confirm}
    stdout = off.read_logs(side, task_id)
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

    # 5. One task, one run, one start; no cancel; the same four processes; the action listing never changed.
    final_direct = direct.task(task_id)["task"]
    final_execution = running_execution(workspace_root, workspace, task_id)
    facts["final"] = {"direct_state": final_direct.get("state"),
                      "cancel_requested": final_direct.get("cancel_requested"),
                      "same_program": final_execution["program"] == program,
                      "same_worker": final_execution["worker"] == worker,
                      "runs": off.executions(side, workspace),
                      "tasks_in_workspace": len(direct.tasks(workspace)["tasks"]),
                      "node_runs": node_runs(), "identities_alive": continuity()}
    ledger_final = action_ledger(backend)
    facts["actions"] = {"before": kinds(ledger_before), "final": kinds(ledger_final),
                        "unchanged": {"offline": ledger_offline == ledger_before,
                                      "completed_offline": ledger_completed == ledger_before,
                                      "reconnect": ledger_reconnect == ledger_before,
                                      "final": ledger_final == ledger_before}}


def partition_assertions(facts, requests):
    """P1-P15 of the socket-partition scenario: the offline-completion predicates that do not depend on how the
    node was cut off, under their own names, plus the partition's own route, cut, rejection, release and reopen
    checks. Any missing or malformed fact fails its check."""
    shared = {name.split()[0]: predicate for name, predicate in completion_checks(facts, requests)}
    route, cut, offline, done, reopen, final = (facts.get(name) or {} for name in (
        "route", "partition", "offline", "completed_offline", "reopen", "final"))
    return judged([
        ("P1 one submission; the program printed its ready line and runs unreleased with one start marker; the "
         "heartbeat snapshot lists it running", shared["C1"]),
        ("P2 only the NodeAgent's control link runs through this run's loopback relay, from its pairing onward; the "
         "harness's Hub and Runtime clients are direct",
         lambda: route["relay_loopback"] is True and route["node_profile_via_relay"] is True
         and route["hub_client_direct"] is True and route["runtime_client_direct"] is True
         and route["node_identity_valid"] is True and route["tunnels_before_submission"] >= 2),
        ("P3 the relay forcibly closed the task's live control link (opened before the submission, carrying node "
         "traffic after it); the NodeAgent was never signalled, and it, the Hub, the Runtime API and the supervisor "
         "kept their original PID and create time",
         lambda: cut["closed"] >= 1 and cut["active_before_cut"] >= 1 and cut["closed_opened_before_submission"] >= 1
         and cut["live_link_closed"] is True and cut["drained"] is True and cut["node_process_running"] is True
         and all_alive(cut["identities_alive"])),
        ("P4 the Hub reported the node offline, and exact live reads while it did were refused unavailable because "
         "the node is offline, the Hub answering offline right before and after each (never a timeout or unknown); "
         "the first post-cut read did not return a state", shared["C3"]),
        ("P5 while partitioned and before the release, the owned Runtime still ran the task with the original "
         "program and worker, no result and no output; the four original processes were alive",
         lambda: shared["C4"]() and all_alive(offline["identities_alive"])),
        ("P6 while the partition held, every new tunnel was rejected and none was forwarded",
         lambda: done["relay"]["forwarding"] is False and done["relay"]["active"] == 0
         and done["relay"]["accepted_during_partition"] == 0 and done["relay"]["rejected_during_partition"] >= 1),
        ("P7 released only after the offline report, with the partition holding and the original NodeAgent still "
         "running; the owned Runtime reports the original task succeeded, not cancelled",
         lambda: done["released_after_offline_observed"] is True and done["node_runs"] == ["B node run"]
         and done["node_exit_code"] is None and all_alive(done["identities_alive"])
         and done["direct_task"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
         and done["files"] == {"release_flag": True, "finished_record": True, "output_file": True}),
        ("P8 the original program and worker exited before the relay was reopened; still one start", shared["C6"]),
        ("P9 after the offline completion, exact Hub reads were still the strict node-offline refusal while the "
         "heartbeat snapshot still cached the task as running: neither the completed state nor the cache was served",
         shared["C7"]),
        ("P10 the same relay reopened on the same address; the same NodeAgent process, never restarted, reconnected "
         "by itself through a new tunnel with its unchanged node profile; the four original processes alive",
         lambda: reopen["same_port"] is True and reopen["listening"] is True and reopen["accepted_after_reopen"] >= 1
         and reopen["active"] >= 1 and reopen["profile_unchanged"] is True and reopen["node_runs"] == ["B node run"]
         and reopen["node_exit_code"] is None and all_alive(reopen["identities_alive"])),
        ("P11 the same node device and the first answered exact live read, whatever its state, is the original "
         "task, succeeded", shared["C8"]),
        ("P12 the fixed stdout bytes, read through the Hub by byte cursor, equal the owned Runtime's", shared["C9"]),
        ("P13 exactly out.txt with the fixed bytes, listed and downloaded through the Hub and hash-checked",
         shared["C10"]),
        ("P14 one task, one run directory with one start whose program and worker exited; never cancelled; the same "
         "four processes at the end",
         lambda: shared["C11"]() and final["node_runs"] == ["B node run"] and all_alive(final["identities_alive"])),
        ("P15 one workspace creation and one submission; no Hub action after the submission and no cancel",
         shared["C12"]),
    ])


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


def partition_manifest(origins, ports):
    record = completion_manifest(origins, ports)
    record.update({
        "record": "D1 X7 socket-partition trial evidence (informal)",
        "scenario": "socket-partition",
        "deployments": {"B": ["B/runtime (api, supervisor)", "B/control (hub serve)",
                              "B/node (node run; paired and connected through this run's loopback relay; its control "
                              "link closed and new tunnels rejected, then the same relay reopened; never signalled "
                              "or restarted)"]},
        "client_boundary": ("in-process suan.desktop_bridge HubBackend over a direct HubClient, and a direct "
                            "RuntimeClient; the strict stdio bridge subprocess is not exercised by this harness"),
        "verified": ["on one Linux host: while a loopback relay closes the outbound NodeAgent's live control link and "
                     "rejects new tunnels, with no process signalled, the task completes normally on its original "
                     "Runtime; exact Hub reads stay unavailable until the same relay reopens and the same NodeAgent "
                     "process reconnects with its unchanged profile, then read the same task succeeded with its fixed "
                     "log and artifact bytes, without a second submission, start or cancel"],
        "not_verified": ["partitions that silently drop packets or leave half-open sockets (the relay closes and "
                         "rejects), asymmetric or intermittent links, or long outages",
                         "the strict desktop stdio bridge subprocess (covered separately, not by this harness)",
                         "native desktop clients, cross-host networks, sites or clusters, Windows/macOS",
                         "Hub restart, Runtime restart, or NodeAgent restart",
                         "completion timing other than one release after the Hub reported the node offline",
                         "failover to another node or Runtime (none is attempted)",
                         "that no Hub action exists outside the client-visible listing (newest 200, plus reviews)",
                         "real solvers, licensed software or scientific validity"]})
    return record


PLAYS = {"cancel": (scenario, assertions, manifest),
         "offline-completion": (scenario_completion, completion_assertions, completion_manifest),
         "socket-partition": (scenario_partition, partition_assertions, partition_manifest)}


def run(evidence, work_root=None, keep=False, mode="installed", deadline_seconds=170, scenario_name="cancel"):
    if scenario_name not in SCENARIOS:
        raise ValueError("unknown scenario")
    play, judge, describe = PLAYS[scenario_name]
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
        if scenario_name == "socket-partition":
            origins["socket_partition_sha256"] = sha256_file(PARTITION_FILE)
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
    details = describe(origins, ports)
    if scenario_name == "socket-partition" and not ok:
        details["verified"] = []
    (evidence / "run-manifest.json").write_text(json.dumps({
        **details, "deadline_seconds": deadline_seconds, "scenario_seconds": scenario_seconds,
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
                             "after the reconnect, with no cancel; socket-partition: the same, but the node is cut "
                             "off by closing its control link in a loopback relay instead of being killed.")
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
