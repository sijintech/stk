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
    reads are retried within the deadline; an unanswered read is ``unknown``. Never writes."""
    return off.wait_terminal(side, task_id, timeout, until=("running", *off.TERMINAL))


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


def run(evidence, work_root=None, keep=False, mode="installed", deadline_seconds=170):
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
        scenario(owned, env, facts, log, clients)
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
    checks = assertions(facts, log) if error is None else []
    within_deadline = scenario_seconds is not None and scenario_seconds <= deadline_seconds
    ok = error is None and bool(checks) and all(c["status"] == "pass" for c in checks) and cleanup_ok and within_deadline
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    ports = {f"B_{name}": port for name, port in (facts.get("ports") or {}).items()}
    phases = {key: value for key, value in facts.items() if key != "ports"}
    (evidence / "run-manifest.json").write_text(json.dumps({
        **manifest(origins, ports), "deadline_seconds": deadline_seconds, "scenario_seconds": scenario_seconds,
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
        ok, error, elapsed = run(args.evidence_dir, args.work_root, args.keep, args.mode, args.deadline)
    except Exception as exc:  # noqa: BLE001 - never print raw exception text
        ok, error, elapsed = False, off.exported_error(exc), None
    print(json.dumps({"ok": ok, "error": error, "elapsed_seconds": elapsed}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
