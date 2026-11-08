"""D1 Hub-restart slice (CL-D1-HUB-RESTART-13): the Hub dies after the Runtime accepted a submission but before
the Hub recorded its result; the same Hub restarts and the original queued action is delivered again.

One private loopback deployment on one Linux host, started through the helpers of ``offline.py`` and
``disconnect.py`` (both loaded by file path, read-only):

* ``suan server init/start`` -- one Runtime API and supervisor (they survive the whole run);
* ``suan-control init/serve`` -- a real HTTP + WebSocket Hub with the exact ``parity-wait`` template;
* the real ``suan-node run`` (``suan.control.cli:node``), started through a small test-only driver written into
  this run's private directory (``DRIVER`` below; its bytes are hashed in the manifest).

The driver wraps two real methods and changes no business state:

* ``NodeAgent.execute`` -- it always calls the real ``execute`` first (real ``Runtime.submit``, real action-cache
  write). For the first ``task.submit`` only, it then holds the return until the harness has killed the Hub and
  the agent's own ``_send`` is ``None`` (the agent noticed the disconnect). The real ``_perform`` then finds no
  connection and drops that first reply, so the Hub keeps the action queued.
* ``NodeAgent._perform`` and ``RuntimeClient.submit`` -- only counted and staged (call numbers, cache hit,
  returned task ID, whether ``_send`` was ``None``), never altered.

Scenario:

1. One workspace; one client submission of the template (its reply times out while the first result is held).
   The Runtime accepted it (one task; the driver staged the Runtime's task ID), the real program printed its
   ready line, and the program and worker identities and the single start marker are frozen. The Hub's public
   action record is still ``queued`` with no result.
2. SIGKILL only the Hub process group (frozen identity, alive right before) and reap it. During the outage the
   Runtime, the program, the worker and the NodeAgent process stay alive; Hub reads are refused, never a task
   state. The held result is released, ``_send`` is ``None``, and the first ``_perform`` finishes before the
   Hub restarts: the first reply was dropped, not delivered late.
3. Restart the same Hub command (same state directory, database, templates and port): no init, pairing,
   profile or workspace change. The same NodeAgent process reconnects, the Hub delivers the original queued
   action again, and the agent's persisted action cache answers it with the original task (``Runtime.submit``
   is not called again). The action succeeds with the original task; its ID and request digest are unchanged.
4. The original task is still the only task, with the same program and worker and one start marker. An
   explicit cancel through the recovered Hub path ends it; the original program and worker exit before cleanup.

The Hub's read-only action listing (newest 200 plus reviews) shows no action besides the workspace creation,
the submission and the cancel. Every process and directory of this run is then stopped and removed.

Evidence (``--evidence-dir``, new or empty): run-manifest.json, requests.jsonl, phases.json, assertions.json,
resources.json -- no tokens, pairing codes, environment values, absolute paths or raw exception text. This is a
software-behaviour check with a synthetic program. It is not a network partition, cross-host, failover, site,
licensed-software or scientific-validity test.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
DISCONNECT_FILE = HERE / "disconnect.py"


def load_disconnect():
    """disconnect.py (which loads offline.py by file path): one shared helper instance, read-only reuse."""
    spec = importlib.util.spec_from_file_location("backend_parity_disconnect_helpers", DISCONNECT_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dis = load_disconnect()
off = dis.off

TEMPLATE = "parity-wait"
READY = "waiting 等待".encode("utf-8")
WORKSPACE_KEY, SUBMIT_KEY, CANCEL_KEY = "hr-ws", "hr-wait", "hr-cancel"  # idempotency keys, not secrets
SUBMIT_REPLY_WAIT = 3  # the client's submission reply wait; it times out while the first result is held
STAGE_WAIT = 30
RECOVERY_WAIT = 60

DRIVER = r'''"""Test-only NodeAgent driver of hub_restart.py; it exists only in that run's private directory.

It runs the real ``suan-node run`` after wrapping real methods. ``execute`` always runs the real
``NodeAgent.execute`` first; for the first ``task.submit`` only, its return is held until the harness writes
the release file and the agent's ``_send`` is ``None``. Counters and stages only; no result is changed.
"""
import json
from pathlib import Path
import sys
import threading
import time


def install(agent_class, client_class, control, gate_seconds):
    stages, release = Path(control) / "stages.jsonl", Path(control) / "release"
    lock = threading.Lock()
    state = {"gated": None, "first_perform_done": False, "execute_calls": {}, "runtime_submits": 0}
    deadline = time.monotonic() + gate_seconds

    def stage(name, **fields):
        with lock:
            with open(stages, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({"stage": name, "t": time.monotonic(), **fields}) + "\n")

    original_execute, original_perform, original_submit = agent_class.execute, agent_class._perform, client_class.submit

    def submit(self, spec, idempotency_key=None):
        with lock:
            state["runtime_submits"] += 1
            call = state["runtime_submits"]
        result = original_submit(self, spec, idempotency_key)
        stage("runtime_submit", call=call, key=idempotency_key,
              task_id=result.get("id") if isinstance(result, dict) else None)
        return result

    def execute(self, action):
        identity, kind = action.get("id"), action.get("kind")
        with lock:
            call = state["execute_calls"][identity] = state["execute_calls"].get(identity, 0) + 1
            gate = kind == "task.submit" and state["gated"] is None
            if gate:
                state["gated"] = identity
        cached = (Path(self.cache) / f"{identity}.json").exists()
        stage("execute", action=identity, kind=kind, call=call, cached_before=cached)
        result = original_execute(self, action)
        stage("returned", action=identity, kind=kind, call=call,
              task_id=result.get("id") if isinstance(result, dict) else None)
        if gate:
            stage("held", action=identity)
            while time.monotonic() < deadline and not release.exists():
                time.sleep(0.05)
            while time.monotonic() < deadline and self._send is not None:
                time.sleep(0.05)
            stage("released", action=identity, release_seen=release.exists(), send_none=self._send is None)
        return result

    async def _perform(self, action, lane):
        await original_perform(self, action, lane)
        if action.get("id") == state["gated"] and not state["first_perform_done"]:
            state["first_perform_done"] = True
            stage("first_perform_finished", action=action.get("id"), send_none=self._send is None)

    agent_class.execute, agent_class._perform, client_class.submit = execute, _perform, submit


def main():
    control, node_state, gate_seconds = sys.argv[1], sys.argv[2], float(sys.argv[3])
    from suan.control.agent import NodeAgent
    from suan.runtime.client import RuntimeClient
    install(NodeAgent, RuntimeClient, control, gate_seconds)
    from suan.control.cli import node
    node(["run", "--state-dir", node_state], prog_name="suan-node")


if __name__ == "__main__":
    main()
'''
DRIVER_SHA256 = hashlib.sha256(DRIVER.encode("utf-8")).hexdigest()
DRIVER_MISMATCH = "the private NodeAgent driver file does not have the expected bytes; it was not launched"


def driver_bound(facts):
    """The launched NodeAgent driver is the expected one: the private file was hashed when written and again right
    before launch, both equal to this harness's DRIVER digest, and it was launched. Missing proof is no proof."""
    driver = facts.get("driver")
    return (isinstance(driver, dict) and driver.get("expected_sha256") == DRIVER_SHA256
            and driver.get("written_sha256") == DRIVER_SHA256 and driver.get("launch_sha256") == DRIVER_SHA256
            and driver.get("launched") is True)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class DriverOwned(off.Owned):
    """``Owned`` that starts the NodeAgent through the driver and remembers each command (in memory only)."""

    def __init__(self, work):
        super().__init__(work)
        self.commands = {}
        self.cli_calls = []  # labels of short CLI calls (init, pair, start, stop), to show none follow the restart
        self.driver_command = None
        self.driver_launched = False

    def run(self, label, command, env, **kwargs):
        self.cli_calls.append(label)
        return super().run(label, command, env, **kwargs)

    def spawn(self, label, command, env, log):
        driver = label == "B node run" and self.driver_command is not None
        if driver:
            command = self.driver_command()  # checks the driver bytes; raises (nothing launched) on a mismatch
        self.commands[label] = list(command)
        process = super().spawn(label, command, env, log)
        if driver:
            self.driver_launched = True
        return process


def read_stages(control):
    try:
        lines = (Path(control) / "stages.jsonl").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    stages = []
    for line in lines:
        try:
            stages.append(json.loads(line))
        except ValueError:
            stages.append({"stage": "malformed"})
    return stages


def wait_stage(control, predicate, timeout, what):
    deadline = time.monotonic() + off.remaining(timeout)
    while time.monotonic() < deadline:
        found = [s for s in read_stages(control) if predicate(s)]
        if found:
            return found[0]
        time.sleep(0.1)
    raise off.Unknown(f"the driver did not report {what} before the deadline")


def public_action(backend, identity):
    """The Hub's public record of one action (GET, read-only): state, whether a result exists, the task it
    names, and the digest of its request."""
    record = backend.call(backend.hub.action, identity)
    result = record.get("result")
    return {"id_same": record.get("id") == identity, "state": record.get("state"),
            "result_present": result is not None,
            "result_task_id": result.get("id") if isinstance(result, dict) else None,
            "request_sha256": digest(record.get("request"))}


def wait_action(backend, identity, states, timeout):
    from suan.desktop_bridge.protocol import BridgeError
    deadline = time.monotonic() + off.remaining(timeout)
    last = None
    while time.monotonic() < deadline:
        try:
            last = public_action(backend, identity)
            if last["state"] in states:
                return last
        except BridgeError as exc:
            if exc.code not in ("unavailable", "timeout"):
                raise
        time.sleep(0.25)
    raise off.Unknown("the original Hub action did not finish before the deadline")


def drop_stage_times(stage):
    return {k: v for k, v in stage.items() if k != "t"} if stage else None


# ----------------------------------------------------------------------------------------------------
# Scenario


def scenario(owned, env, facts, log, clients):
    from suan.desktop_bridge.backends import RuntimeBackend, action_id
    from suan.desktop_bridge.protocol import BridgeError
    work = owned.work
    control = work / "driver"
    control.mkdir()
    driver_file = control / "node_driver.py"
    driver_file.write_bytes(DRIVER.encode("utf-8"))
    node_state = work / "B" / "node"
    facts["driver"] = {"expected_sha256": DRIVER_SHA256, "written_sha256": sha256_file(driver_file),
                       "launch_sha256": None, "launched": False}
    if facts["driver"]["written_sha256"] != DRIVER_SHA256:  # before any service starts
        raise off.HarnessError(DRIVER_MISMATCH)

    def launch_driver():
        """The NodeAgent command, only after the private driver file is checked again right before launch."""
        facts["driver"]["launch_sha256"] = sha256_file(driver_file)
        if facts["driver"]["launch_sha256"] != DRIVER_SHA256:
            raise off.HarnessError(DRIVER_MISMATCH)
        return [sys.executable, str(driver_file), str(control), str(node_state), str(off.budget(170))]

    owned.driver_command = launch_driver
    client, port_runtime, workspace_root = off.start_runtime(owned, work / "B" / "runtime", env, "B")
    clients.append(("B", client))
    hub, node_id, port_hub = off.start_hub(owned, work / "B", env, work / "B" / "runtime")
    facts["ports"] = {"runtime": port_runtime, "hub": port_hub}
    facts["driver"]["launched"] = owned.driver_launched
    Budgeted = dis.budgeted_hub_backend()
    backend = Budgeted("hub:hub-restart", hub, node_id, wait=60)
    direct = RuntimeBackend("runtime:hub-restart-direct", client)  # this run's own Runtime, read-only here
    side = off.Side("B", backend, client, workspace_root, log)  # Hub path: exact reads use require_live
    direct_side = off.Side("R", direct, client, workspace_root, [])
    off.wait_node_live(backend, time.monotonic() + off.budget(30))
    device_before = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    processes = dict(owned.processes)
    pids = {item["label"]: item["pid"] for item in owned.resources["processes"]}
    hub_identity = dis.identity_of(processes["B hub serve"].pid)
    node_identity = dis.identity_of(processes["B node run"].pid)
    runtime = {label: dis.identity_of(pids[label]) for label in ("B runtime api", "B runtime supervisor")}

    # 1. One workspace and one client submission; the Runtime accepts it while its first reply is held.
    created = backend.create_workspace("hub-restart", key=WORKSPACE_KEY)
    workspace = (created.get("workspace") or {}).get("id")
    if not workspace:
        raise off.Unknown("workspace creation did not finish")
    log.append({"side": "B", "operation": "workspace.create", "key": WORKSPACE_KEY, "outcome": "created",
                "workspace_id": workspace})
    original_action = action_id("task.submit", node_id, SUBMIT_KEY)
    submitter = Budgeted("hub:hub-restart-submit", hub, node_id, wait=SUBMIT_REPLY_WAIT)
    try:
        reply = submitter.submit(None, SUBMIT_KEY, template=TEMPLATE, workspace_id=workspace)
        outcome, reply_task = "accepted", (reply.get("task") or {}).get("id")
    except BridgeError as exc:
        outcome, reply_task = exc.code, None
    log.append({"side": "B", "operation": "task.submit", "key": SUBMIT_KEY, "template": TEMPLATE,
                "outcome": outcome, "action_id": original_action, "task_id": reply_task})
    held = wait_stage(control, lambda s: s["stage"] == "held" and s.get("action") == original_action, STAGE_WAIT,
                      "the held first result")
    first_return = next((s for s in read_stages(control) if s["stage"] == "returned"
                         and s.get("action") == original_action and s.get("call") == 1), None)
    tasks = direct.tasks(workspace)["tasks"]
    task_id = tasks[0]["id"] if len(tasks) == 1 else None
    if task_id is None:
        raise off.Unknown("the Runtime did not hold exactly one task for the submission")
    off.wait_output(direct_side, task_id, READY, 60)
    baseline = dis.running_execution(workspace_root, workspace, task_id)
    program, worker = baseline["program"], baseline["worker"]
    action_before = public_action(backend, original_action)
    ledger_before = dis.action_ledger(backend)
    facts["submit"] = {"client_outcome": outcome, "client_reply_task": reply_task is not None,
                       "tasks_in_workspace": len(tasks), "direct_state": tasks[0].get("state"),
                       "held_stage": held is not None,
                       "accepted_task_is_runtime_task": bool(first_return) and first_return.get("task_id") == task_id,
                       "action_before_fault": action_before}
    facts["baseline"] = {"execution": baseline,
                         "alive": {"B hub serve": dis.alive(hub_identity), "B node run": dis.alive(node_identity),
                                   **{label: dis.alive(identity) for label, identity in runtime.items()}}}

    # 2. Only the Hub dies; the first reply is dropped while the agent is disconnected.
    facts["hub_stop"] = dis.stop_node(processes["B hub serve"], hub_identity)
    (control / "release").write_text("", encoding="ascii")
    released = wait_stage(control, lambda s: s["stage"] == "released" and s.get("action") == original_action,
                          STAGE_WAIT, "the release of the first result")
    finished = wait_stage(control, lambda s: s["stage"] == "first_perform_finished"
                          and s.get("action") == original_action, STAGE_WAIT, "the end of the first delivery")
    reads = [dis.classify_read(side, task_id) for _ in range(2)]
    direct_task = direct.task(task_id)["task"]
    during = dis.running_execution(workspace_root, workspace, task_id)
    executes_before_restart = [s for s in read_stages(control) if s["stage"] == "execute"
                               and s.get("action") == original_action]
    facts["outage"] = {"released": drop_stage_times(released), "first_perform_finished": drop_stage_times(finished),
                       "deliveries_before_restart": len(executes_before_restart), "hub_reads": reads,
                       "direct_task": {"same_task": direct_task.get("id") == task_id, "state": direct_task.get("state")},
                       "execution": during,
                       "alive": {"B node run": dis.alive(node_identity),
                                 **{label: dis.alive(identity) for label, identity in runtime.items()}}}

    # 3. The same Hub restarts; the original queued action is delivered again and recovers.
    restarted_at = time.monotonic()
    calls_at_restart = len(owned.cli_calls)
    owned.spawn("B hub serve (restarted)", owned.commands["B hub serve"], env, work / "B" / "control.log")
    off.wait_port(port_hub, time.monotonic() + off.budget(30))
    recovered = wait_action(backend, original_action, ("succeeded", "failed", "rejected"), RECOVERY_WAIT)
    stages = read_stages(control)
    deliveries = [s for s in stages if s["stage"] == "execute" and s.get("action") == original_action]
    returns = [s for s in stages if s["stage"] == "returned" and s.get("action") == original_action]
    submits = [s for s in stages if s["stage"] == "runtime_submit"]
    nodes = [d for d in backend.call(backend.hub.devices) if d.get("role") == "node" and not d.get("revoked")]
    device_after = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    live = dis.observe_live(side, task_id, 30)
    after = dis.running_execution(workspace_root, workspace, task_id)
    ledger_after = dis.action_ledger(backend)
    changed = sorted(key for key in ledger_before if ledger_after.get(key) != ledger_before[key])
    restarted_hub = dict(owned.processes)["B hub serve (restarted)"]
    facts["restart"] = {
        # A description of what the harness did (it reran the recorded serve command: the same state directory,
        # templates and port), not proof. The proof that the same Hub state came back is in the restarted Hub's
        # own answers: the pre-fault node device (node_device_same) and the pre-fault action with its request
        # digest (H7).
        "restart_reused_serve_command": owned.commands["B hub serve (restarted)"] == owned.commands["B hub serve"],
        "hub_process_new": dis.identity_of(restarted_hub.pid) not in (None, hub_identity),
        "cli_calls_after_restart": owned.cli_calls[calls_at_restart:],  # no init, pairing or profile change
        # The driver's stage time and the harness clock are both time.monotonic(), the system-wide CLOCK_MONOTONIC
        # on Linux (the only supported host), so they compare across the two processes.
        "first_delivery_finished_before_restart": isinstance(finished.get("t"), (int, float))
        and finished["t"] < restarted_at,
        "node_device_same": device_after == device_before and [d["id"] for d in nodes] == [device_before],
        "node_devices": len(nodes), "node_process_same_alive": dis.alive(node_identity)}
    redelivered = [d for d in deliveries[1:] if isinstance(d.get("t"), (int, float)) and d["t"] > restarted_at]
    from_cache = bool(redelivered) and all(d.get("cached_before") is True for d in redelivered)
    facts["replay"] = {
        "deliveries": [drop_stage_times(s) for s in deliveries], "returns": [drop_stage_times(s) for s in returns],
        "runtime_submits": [drop_stage_times(s) for s in submits],
        "redelivered_after_restart": bool(redelivered) and len(redelivered) == len(deliveries) - 1,
        "recovered_from_node_cache": from_cache,
        "recovery_path": ("node action cache" if from_cache and len(submits) == 1 else
                          "Runtime idempotent replay" if not from_cache and len(submits) > 1 else "unclassified"),
        "runtime_submit_calls": len(submits),
        "every_return_is_original": bool(returns) and all(r.get("task_id") == task_id for r in returns),
        "every_runtime_submit_is_original": bool(submits) and all(s.get("task_id") == task_id
                                                                  and s.get("key") == original_action for s in submits),
        "action_after": recovered,
        "request_unchanged": recovered["request_sha256"] == action_before["request_sha256"]}
    facts["recovered"] = {"live_task": {"same_task": live.get("id") == task_id, "state": live.get("state")},
                          "execution": after, "tasks_in_workspace": len(direct.tasks(workspace)["tasks"]),
                          "ledger_ids_same": set(ledger_after) == set(ledger_before),
                          "ledger_changed": [ledger_before[key]["kind"] for key in changed],
                          "submit_state": (ledger_after.get(original_action) or {}).get("state")}

    # 4. The explicit cancel through the recovered Hub path.
    cancelled = backend.cancel(task_id, key=CANCEL_KEY)
    log.append({"side": "B", "operation": "task.cancel", "key": CANCEL_KEY, "task_id": task_id,
                "outcome": ((cancelled.get("task") or {}).get("state")) or (cancelled.get("action") or {}).get("state")})
    final = off.wait_terminal(side, task_id, 60)
    program_exited, worker_exited = dis.exited(program, 15), dis.exited(worker, 15)
    final_direct = direct.task(task_id)["task"]
    final_execution = dis.running_execution(workspace_root, workspace, task_id)
    runs = off.executions(side, workspace)
    ledger_final = dis.action_ledger(backend)
    added = {key: value for key, value in ledger_final.items() if key not in ledger_after}
    facts["cancel"] = {"state": final.get("state"), "cancel_requested": final.get("cancel_requested"),
                       "direct_state": final_direct.get("state"),
                       "same_program": final_execution["program"] == program,
                       "same_worker": final_execution["worker"] == worker,
                       "original_program_exited": program_exited, "original_worker_exited": worker_exited,
                       "runs": runs, "tasks_in_workspace": len(direct.tasks(workspace)["tasks"])}
    facts["actions"] = {"before": dis.kinds(ledger_before), "after_recovery": dis.kinds(ledger_after),
                        "final": dis.kinds(ledger_final), "added_by_cancel": dis.kinds(added),
                        "before_kept": set(ledger_before) <= set(ledger_final)}


def assertions(facts, requests):
    """H0-H10 over the recorded facts; any missing or malformed fact fails its check."""
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
                and execution["program_alive"] and execution["worker_alive"] and execution["start_markers"] == 1
                and execution["marker_pid_is_program"])

    submit, base, stop, outage, restart, replay, recovered, cancel, actions = (
        facts.get(name) or {} for name in ("submit", "baseline", "hub_stop", "outage", "restart", "replay",
                                           "recovered", "cancel", "actions"))
    checks = [
        ("H0 the launched NodeAgent driver had the expected bytes (hashed when written and right before launch)",
         lambda: driver_bound(facts)),
        ("H1 accepted before the loss: the Runtime accepted the one submission (the driver held that real result) "
         "while the Hub's original action stayed queued with no result",
         lambda: submit["client_outcome"] == "timeout" and submit["client_reply_task"] is False
         and submit["tasks_in_workspace"] == 1 and submit["accepted_task_is_runtime_task"] is True
         and submit["action_before_fault"]["state"] == "queued" and submit["action_before_fault"]["result_present"] is False
         and submit["action_before_fault"]["id_same"] is True),
        ("H2 before the fault the original program was ready and ran with its worker and one start marker; the Hub, "
         "NodeAgent, Runtime API and supervisor were alive",
         lambda: running(base["execution"]) and len(base["alive"]) == 4 and all(base["alive"].values())),
        ("H3 only the original Hub was killed: alive right before the SIGKILL, killed by it, reaped and gone",
         lambda: stop["identity_valid"] is True and stop["running_before_kill"] is True
         and stop["alive_before_kill"] is True and stop["signal_sent"] is True and stop["exit_code"] == -9
         and stop["killed_by_sigkill"] is True and stop["reaped"] is True and stop["node_alive_after"] is False),
        ("H4 during the outage the original task, program, worker, NodeAgent and Runtime stayed alive, and Hub reads "
         "were refused (never a task state)",
         lambda: outage["direct_task"] == {"same_task": True, "state": "running"} and running(outage["execution"])
         and len(outage["alive"]) == 3 and all(outage["alive"].values())
         and len(outage["hub_reads"]) >= 1 and all(dis.offline_read_ok(read) for read in outage["hub_reads"])),
        ("H5 the first reply was dropped: released only after the disconnect, and the first delivery finished with "
         "no connection, before the Hub restarted",
         lambda: outage["released"]["release_seen"] is True and outage["released"]["send_none"] is True
         and outage["first_perform_finished"]["send_none"] is True and outage["deliveries_before_restart"] == 1
         and restart["first_delivery_finished_before_restart"] is True),
        ("H6 a new Hub process came back with the pre-fault state (it lists the same, only node device) and the same "
         "NodeAgent process reconnected, with no init, pairing or profile call after the restart",
         lambda: restart["cli_calls_after_restart"] == []
         and restart["hub_process_new"] is True and restart["node_device_same"] is True and restart["node_devices"] == 1
         and restart["node_process_same_alive"] is True),
        ("H7 the original action was delivered again and recovered with the original task, ID and request digest "
         "unchanged; every Runtime submission and every node result named the original task",
         lambda: replay["redelivered_after_restart"] is True and len(replay["deliveries"]) >= 2
         and replay["every_return_is_original"] is True and replay["every_runtime_submit_is_original"] is True
         and replay["action_after"]["state"] == "succeeded" and replay["action_after"]["id_same"] is True
         and replay["action_after"]["result_task_id"] is not None
         and all(r.get("task_id") == replay["action_after"]["result_task_id"] for r in replay["returns"])
         and replay["request_unchanged"] is True
         and replay["recovery_path"] in ("node action cache", "Runtime idempotent replay")),
        ("H8 after the recovery: still one task with the original program and worker and one start marker; reads "
         "created no action and only the submission's state changed",
         lambda: recovered["live_task"] == {"same_task": True, "state": "running"} and running(recovered["execution"])
         and recovered["tasks_in_workspace"] == 1 and recovered["ledger_ids_same"] is True
         and recovered["ledger_changed"] == ["task.submit"] and recovered["submit_state"] == "succeeded"),
        ("H9 the explicit cancel through the recovered path ended the original task; the original program and worker "
         "exited before cleanup; one task, one run, one start; only the cancel added an action",
         lambda: cancel["state"] == "cancelled" and cancel["cancel_requested"] is True
         and cancel["direct_state"] == "cancelled" and cancel["same_program"] is True and cancel["same_worker"] is True
         and cancel["original_program_exited"] is True and cancel["original_worker_exited"] is True
         and cancel["runs"] == [off.EXPECTED_RUN] and cancel["tasks_in_workspace"] == 1
         and actions["added_by_cancel"] == ["task.cancel"] and actions["before_kept"] is True
         and actions["before"] == ["task.submit", "workspace.create"]),
        ("H10 requests: one workspace creation, one client submission, one cancel",
         lambda: [entry["operation"] for entry in requests] == ["workspace.create", "task.submit", "task.cancel"]),
    ]
    return [{"id": name, "status": "pass" if check(predicate) else "fail"} for name, predicate in checks]


# ----------------------------------------------------------------------------------------------------
# Run


def manifest(origins, ports):
    record = off.manifest("<private temporary directory>", ports, origins)
    record.pop("schema", None)  # informal trial evidence, not a published format
    record.update({
        "record": "D1 Hub-restart trial evidence (informal)",
        "deployments": {"B": ["B/runtime (api, supervisor; survive)", "B/control (hub serve; killed, then restarted "
                              "with the same command and state)", "B/node (real suan-node run through the test "
                              "driver; survives and reconnects)"]},
        "templates": {TEMPLATE: record["templates"][TEMPLATE]},
        "driver": {"sha256": DRIVER_SHA256, "wraps": ["NodeAgent.execute (holds the first task.submit return)",
                                                      "NodeAgent._perform (stage only)",
                                                      "RuntimeClient.submit (count only)"]},
        "verified": ["on one Linux host: after the Runtime accepted a submission and its program runs, the Hub is "
                     "killed before recording the result; the same Hub restarts, the original queued action is "
                     "delivered again and answered with the original task, with one start"],
        "not_verified": ["a second Runtime.submit with the same identity: the NodeAgent's persisted action cache "
                         "answers the second delivery, so Runtime idempotency is not exercised here",
                         "the Hub dying at other points (before the dispatch, after recording the result)",
                         "NodeAgent or Runtime restarts, network partitions without a process exit, long outages",
                         "Hub actions outside the client-visible listing (newest 200, plus reviews)",
                         "failover, other hosts, sites or clusters, Windows/macOS",
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
        owned = DriverOwned(Path(tempfile.mkdtemp(prefix="stk-hub-restart-", dir=work_root)))
        owned.resources["work_dir_created"] = True
        resources = owned.resources
        env = owned.env(mode)
        origins = off.module_origins(env, mode)
        origins["offline_helper_sha256"] = origins.pop("harness_sha256", None)
        origins["disconnect_helper_sha256"] = sha256_file(DISCONNECT_FILE)
        origins["hub_restart_sha256"] = sha256_file(__file__)
        origins["driver_sha256"] = DRIVER_SHA256
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
    driver_ok = driver_bound(facts)  # required explicitly, besides H0: no run passes without the driver proof
    ok = (error is None and bool(checks) and all(c["status"] == "pass" for c in checks) and cleanup_ok
          and within_deadline and driver_ok)
    if origins is not None:
        origins["driver_file_matches"] = driver_ok
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
                                                          "within_deadline": within_deadline,
                                                          "driver_bound": driver_ok, "ok": ok},
                                                         indent=1, ensure_ascii=False), encoding="utf-8")
    (evidence / "resources.json").write_text(json.dumps(resources, indent=1), encoding="utf-8")
    return ok, error, elapsed


def main(argv=None):
    parser = argparse.ArgumentParser(description="The Hub dies after the Runtime accepted a submission; it restarts.")
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
