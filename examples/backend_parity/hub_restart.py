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

``--scenario hub-offline-completion`` (CL-D1-X7-HUB-OFFLINE-COMPLETION-39; the default stays ``lost-result``
above) uses the same deployment and driver, with the driver's hold set to zero (it only counts and stages), and
``disconnect.py``'s release-gated synthetic program ``parity-release`` registered in this run's Hub only. The
original task completes while the Hub process is dead:

1. One workspace; one client submission whose receipt arrives normally, naming the Runtime's one task. The Hub
   action is ``succeeded`` with that task; the node executed it once and entered ``RuntimeClient.submit`` once,
   which returned once. The action's request is present and bound to the original action, node and workspace. The
   program printed its ready line, waits unreleased; program/worker identities and the one start are frozen.
2. SIGKILL and reap only the original Hub. Only after the harness confirmed that the Hub is still dead and was
   never restarted (its port refuses connections), that the original NodeAgent, Runtime API and supervisor are
   alive and not replaced, that exact reads are refused because the Hub cannot be reached, and that the owned
   Runtime still runs the original unreleased task, does it write the program's private release flag.
3. With the Hub still dead and never restarted: the owned Runtime reports the original task ``succeeded``; its
   program and worker exit; exact reads through the Hub are still refused (never a state).
4. Rerun the recorded ``serve`` command (same state directory, database and port); no init, pairing or
   resubmission. The original NodeAgent process reconnects by itself. The first answered exact live read is
   the original task, ``succeeded``; the fixed stdout and the single fixed ``out.txt`` are read through the Hub
   and match the owned Runtime. The action record, its bound request digest and listing are unchanged; the node
   saw no further delivery and entered ``RuntimeClient.submit`` no further time; no cancel, one task, run, start.

Evidence (``--evidence-dir``, new or empty): run-manifest.json, requests.jsonl, phases.json, assertions.json,
resources.json -- no tokens, pairing codes, environment values, absolute paths or raw exception text. This is a
software-behaviour check with a synthetic program. It is not a network partition, cross-host, failover, site,
licensed-software or scientific-validity test.
"""
import argparse
import errno
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import socket
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
SCENARIOS = ("lost-result", "hub-offline-completion")
COMPLETION_KEYS = ("x7h-ws", "x7h-release")  # workspace and submission idempotency keys, not secrets
COUNT_ONLY_GATE = 0  # the driver's hold in hub-offline-completion: none (its loops end at once); it only counts
# The NodeAgent retries a lost Hub connection with an exponential backoff up to 30 s, so its first attempt after
# the restart can be that far away. Bounded by the run budget like every other wait; the restart renews nothing.
RECONNECT_WAIT = 60

DRIVER = r'''"""Test-only NodeAgent driver of hub_restart.py; it exists only in that run's private directory.

It runs the real ``suan-node run`` after wrapping real methods. ``execute`` always runs the real
``NodeAgent.execute`` first; for the first ``task.submit`` only, its return is held until the harness writes
the release file and the agent's ``_send`` is ``None``. Counters and stages only; no result is changed.
With a zero hold (count-only), every ``RuntimeClient.submit`` call is also staged at its entry, before the real
call, so a call that raises is still counted; its successful return keeps the same call number.
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
    count_only = gate_seconds == 0

    def stage(name, **fields):
        with lock:
            with open(stages, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({"stage": name, "t": time.monotonic(), **fields}) + "\n")

    original_execute, original_perform, original_submit = agent_class.execute, agent_class._perform, client_class.submit

    def submit(self, spec, idempotency_key=None):
        with lock:
            state["runtime_submits"] += 1
            call = state["runtime_submits"]
        if count_only:
            stage("runtime_submit_called", call=call, key=idempotency_key)
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


def deploy(owned, env, facts, clients, gate_seconds=None, extra_templates=None):
    """The deployment both scenarios share, in this order: the private driver is written and hashed (before any
    service starts), then the Runtime, then the Hub and the NodeAgent, launched through the driver only after its
    file is hashed again. ``gate_seconds`` is the driver's hold of the first ``task.submit`` result (default: the
    time left in the run budget; ``COUNT_ONLY_GATE`` holds nothing). ``extra_templates`` go to this Hub only."""
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
        gate = off.budget(170) if gate_seconds is None else gate_seconds
        return [sys.executable, str(driver_file), str(control), str(node_state), str(gate)]

    owned.driver_command = launch_driver
    client, port_runtime, workspace_root = off.start_runtime(owned, work / "B" / "runtime", env, "B")
    clients.append(("B", client))
    extra = {"extra_templates": extra_templates} if extra_templates else {}
    hub, node_id, port_hub = off.start_hub(owned, work / "B", env, work / "B" / "runtime", **extra)
    facts["ports"] = {"runtime": port_runtime, "hub": port_hub}
    facts["driver"]["launched"] = owned.driver_launched
    return control, node_state, client, workspace_root, hub, node_id, port_hub


def scenario(owned, env, facts, log, clients):
    from suan.desktop_bridge.backends import RuntimeBackend, action_id
    from suan.desktop_bridge.protocol import BridgeError
    work = owned.work
    control, node_state, client, workspace_root, hub, node_id, port_hub = deploy(owned, env, facts, clients)
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
# The hub-offline-completion scenario (X7: the task completes while the Hub process is dead)


def port_refused(port):
    """Whether a TCP connection to the Hub's loopback port is refused right now (nothing listens there). A
    timeout or any other error is not proof that the Hub is gone."""
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == errno.ECONNREFUSED


def hub_down_read(side, task_id, port):
    """One exact live read while the Hub should be dead: its port probed right before and after, plus
    ``disconnect.offline_read`` (the Hub's health right before and after, the read's outcome and refusal cause)."""
    before = port_refused(port)
    read = dis.offline_read(side, task_id)
    return {**read, "port_refused_before": before, "port_refused_after": port_refused(port)}


def hub_down_refusal(read):
    """The strict refusal while the Hub process is dead: refused ``unavailable`` because the Hub cannot be reached,
    neither health check answered, and the Hub's port refused connections right before and after. A running Hub
    that lists the node offline, a timeout, an answer or an unknown read never counts."""
    return (read.get("outcome") == "refused" and read.get("code") == "unavailable"
            and read.get("cause") == "unreachable" and read.get("hub_reported_online") is None
            and read.get("hub_reported_online_after") is None
            and read.get("port_refused_before") is True and read.get("port_refused_after") is True)


def _running(execution, program, worker):
    """The frozen original program and worker are the ones recorded, both alive; one run directory, one start."""
    return (execution["run_directories"] == 1 and execution["run_dir_is_task"] is True
            and off.process_identity(program) is not None and off.process_identity(worker) is not None
            and execution["program"] == program and execution["worker"] == worker
            and execution["program_alive"] is True and execution["worker_alive"] is True
            and execution["start_markers"] == 1 and execution["marker_pid_is_program"] is True)


def _ended(execution, program, worker):
    """The same original program and worker are recorded and neither is alive; still one run, one start."""
    return (execution["run_directories"] == 1 and execution["run_dir_is_task"] is True
            and off.process_identity(program) is not None and off.process_identity(worker) is not None
            and execution["program"] == program and execution["worker"] == worker
            and execution["program_alive"] is False and execution["worker_alive"] is False
            and execution["start_markers"] == 1 and execution["marker_pid_is_program"] is True)


UNRELEASED = {"release_flag": False, "finished_record": False, "output_file": False}
SURVIVORS = ("B node run", "B runtime api", "B runtime supervisor")


def hub_still_dead(hub):
    """The original Hub exited by the SIGKILL, its frozen identity is gone, no other Hub was started and its
    port refuses connections."""
    return (hub["original_exit_code"] == -9 and hub["original_alive"] is False
            and hub["hub_serves"] == ["B hub serve"] and hub["port_refused"] is True)


def survivors_ok(record):
    """The original NodeAgent, Runtime API and supervisor (frozen identities) alive; only the original node run."""
    return (sorted(record["survivors"]) == sorted(SURVIVORS) and all(v is True for v in record["survivors"].values())
            and record["node_runs"] == ["B node run"])


def hub_outage_confirmed(stop, outage, program, worker):
    """The release gate, used by the scenario before it writes the flag and again by K4: only the original Hub
    was SIGKILLed and reaped and is still dead (never restarted); the original NodeAgent and Runtime processes
    are alive and not replaced; at least two exact reads were refused because the Hub cannot be reached; the
    owned Runtime still runs the original unreleased task. Any missing or malformed fact is not confirmed."""
    try:
        return bool(stop["identity_valid"] is True and stop["alive_before_kill"] is True
                    and stop["signal_sent"] is True and stop["killed_by_sigkill"] is True and stop["reaped"] is True
                    and stop["node_alive_after"] is False
                    and hub_still_dead(outage["hub"]) and survivors_ok(outage)
                    and len(outage["reads"]) >= 2 and all(hub_down_refusal(read) for read in outage["reads"])
                    and outage["direct_task"] == {"same_task": True, "state": "running"}
                    and _running(outage["execution"], program, worker) and outage["files"] == UNRELEASED)
    except (KeyError, TypeError, AttributeError):
        return False


def node_log_disconnects(path):
    """How many times the NodeAgent process logged a lost Hub connection (it logs only the exception type).
    Only the count is exported, never the log text."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return sum(1 for line in text.splitlines() if line.startswith("Control disconnected ("))


DRIVER_STAGE_FIELDS = {
    "execute": {"action": (str,), "kind": (str,), "call": (int,), "cached_before": (bool,)},
    "returned": {"action": (str,), "kind": (str,), "call": (int,), "task_id": (str, type(None))},
    "held": {"action": (str,)},
    "released": {"action": (str,), "release_seen": (bool,), "send_none": (bool,)},
    "first_perform_finished": {"action": (str,), "send_none": (bool,)},
    "runtime_submit_called": {"call": (int,), "key": (str, type(None))},
    "runtime_submit": {"call": (int,), "key": (str, type(None)), "task_id": (str, type(None))},
}


def stage_snapshot(stages):
    """One read of the driver's stages (hub-offline-completion only): every delivery, every RuntimeClient.submit
    entry and every successful return, and how many lines fail the driver record shape."""
    def valid(record):
        if not isinstance(record, dict) or type(record.get("t")) not in (int, float):
            return False
        stage = record.get("stage")
        fields = DRIVER_STAGE_FIELDS.get(stage) if isinstance(stage, str) else None
        # Exact types keep a boolean from satisfying an integer call counter.
        return fields is not None and all(field in record and type(record[field]) in types
                                          for field, types in fields.items())

    accepted = [stage for stage in stages if valid(stage)]

    def of(name):
        return [drop_stage_times(stage) for stage in accepted if stage["stage"] == name]

    return {"executes": of("execute"), "runtime_submit_calls": of("runtime_submit_called"),
            "runtime_submits": of("runtime_submit"), "malformed": len(stages) - len(accepted)}


def completion_action(backend, identity, node_id, workspace):
    """The Hub's public record of the original submission (GET, read-only), hub-offline-completion only. The
    request digest is taken only from a request object that is really there, and that request is checked
    against the original action ID, Node ID, the ``task.submit`` kind and the workspace binding. Only booleans
    and the digest are exported, never the request itself."""
    record = backend.call(backend.hub.action, identity)
    result, request = record.get("result"), record.get("request")
    present = isinstance(request, dict)
    payload = request.get("payload") if present else None
    spec = payload.get("spec") if isinstance(payload, dict) else None
    return {"id_same": record.get("id") == identity, "state": record.get("state"),
            "result_present": result is not None,
            "result_task_id": result.get("id") if isinstance(result, dict) else None,
            "request_present": present,
            "request_bound": {"action_id": present and request.get("id") == identity,
                              "node_id": present and request.get("node_id") == node_id,
                              "kind_task_submit": present and request.get("kind") == "task.submit",
                              "workspace": isinstance(spec, dict) and spec.get("workspace_id") == workspace},
            "request_sha256": digest(request) if present else None}


def request_bound(record):
    """A real request object, bound to the original action, node, kind and workspace, with its digest."""
    sha = record["request_sha256"]
    return (record["request_present"] is True and isinstance(sha, str) and len(sha) == 64
            and record["request_bound"] == {"action_id": True, "node_id": True, "kind_task_submit": True,
                                            "workspace": True})


def scenario_completion(owned, env, facts, log, clients):
    from suan.desktop_bridge.backends import RuntimeBackend, action_id
    work = owned.work
    control, node_state, client, workspace_root, hub, node_id, port_hub = deploy(
        owned, env, facts, clients, gate_seconds=COUNT_ONLY_GATE, extra_templates=dis.RELEASE_TEMPLATES)
    backend = dis.budgeted_hub_backend()("hub:x7-hub-completion", hub, node_id, wait=60)
    direct = RuntimeBackend("runtime:x7-hub-completion-direct", client)  # this run's own Runtime, read-only here
    side = off.Side("B", backend, client, workspace_root, log)  # Hub path: exact reads use require_live
    authority = off.Side("B-direct", direct, client, workspace_root, [])  # reads only; never logged as requests
    off.wait_node_live(backend, time.monotonic() + off.budget(30))
    device_before = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    processes = dict(owned.processes)
    pids = {item["label"]: item["pid"] for item in owned.resources["processes"]}
    hub_process = processes["B hub serve"]
    hub_identity = dis.identity_of(hub_process.pid)
    survivors = {"B node run": dis.identity_of(processes["B node run"].pid),
                 **{label: dis.identity_of(pids[label]) for label in ("B runtime api", "B runtime supervisor")}}

    def labelled(prefix):
        return [label for label, _ in owned.processes if label.startswith(prefix)]

    def standing():
        return {"survivors": {label: dis.alive(identity) for label, identity in survivors.items()},
                "node_runs": labelled("B node run")}

    def hub_state():
        return {"original_exit_code": hub_process.poll(), "original_alive": dis.alive(hub_identity),
                "hub_serves": labelled("B hub serve"), "port_refused": port_refused(port_hub)}

    # 1. One workspace and one submission with a normal receipt; the program runs unreleased.
    workspace_key, submit_key = COMPLETION_KEYS
    created = backend.create_workspace("x7-hub-completion", key=workspace_key)
    workspace = (created.get("workspace") or {}).get("id")
    if not workspace:
        raise off.Unknown("workspace creation did not finish")
    side.record("workspace.create", key=workspace_key, outcome="created", workspace_id=workspace)
    original_action = action_id("task.submit", node_id, submit_key)
    task = side.submit(dis.RELEASE_TEMPLATE, submit_key, workspace)
    task_id = task["id"]
    state = off.wait_terminal(side, task_id, 60, until=("running", *off.TERMINAL))["state"]
    ready = off.wait_output(side, task_id, READY, 60)
    baseline = dis.running_execution(workspace_root, workspace, task_id)
    program, worker = baseline["program"], baseline["worker"]  # the original identities, frozen here
    tasks = direct.tasks(workspace)["tasks"]
    finished = wait_stage(control, lambda s: s["stage"] == "first_perform_finished"
                          and s.get("action") == original_action, STAGE_WAIT, "the end of the first delivery")
    released_stage = next((s for s in read_stages(control) if s["stage"] == "released"
                           and s.get("action") == original_action), None)
    action_before = completion_action(backend, original_action, node_id, workspace)
    ledger_before = dis.action_ledger(backend)
    cached = dis.wait_snapshot(backend, task_id, "running", 15)  # the cached view exact reads must never serve
    facts["submit"] = {"task_id": task_id, "tasks_in_workspace": len(tasks),
                       "reply_task_is_runtime_task": len(tasks) == 1 and tasks[0].get("id") == task_id,
                       "action_before_fault": action_before,
                       "first_delivery": {"released": drop_stage_times(released_stage),
                                          "finished": drop_stage_times(finished)},
                       "stages": stage_snapshot(read_stages(control))}
    facts["baseline"] = {"state": state, "ready": ready, "execution": baseline, "snapshot_running": cached,
                         "files": dis.result_files(workspace_root, workspace, task_id),
                         "alive": {"B hub serve": dis.alive(hub_identity), **standing()["survivors"]}}

    # 2. Only the Hub dies. The program is released only once the outage is confirmed in every respect.
    facts["hub_stop"] = dis.stop_node(hub_process, hub_identity)
    reads = [hub_down_read(side, task_id, port_hub) for _ in range(2)]
    before_release = direct.task(task_id)["task"]
    facts["outage"] = {"reads": reads, "hub": hub_state(), **standing(),
                       "direct_task": {"same_task": before_release.get("id") == task_id,
                                       "state": before_release.get("state")},
                       "execution": dis.running_execution(workspace_root, workspace, task_id),
                       "files": dis.result_files(workspace_root, workspace, task_id)}
    confirmed = hub_outage_confirmed(facts["hub_stop"], facts["outage"], program, worker)
    facts["outage"]["released_after_outage_confirmed"] = confirmed and dis.release(workspace_root, workspace, task_id)
    if not confirmed:
        raise off.HarnessError("the Hub outage was not confirmed; the program was not released")

    # 3. The original task completes on the owned Runtime while the Hub is still dead and never restarted.
    done = off.wait_terminal(authority, task_id, dis.COMPLETION_WAIT)
    program_exited, worker_exited = dis.exited(program, 15), dis.exited(worker, 15)
    after_reads = [hub_down_read(side, task_id, port_hub) for _ in range(2)]
    facts["completed_hub_down"] = {
        "direct_task": {"same_task": done.get("id") == task_id, "state": done.get("state"),
                        "cancel_requested": done.get("cancel_requested")},
        "original_program_exited": program_exited, "original_worker_exited": worker_exited,
        "execution": dis.running_execution(workspace_root, workspace, task_id),
        "files": dis.result_files(workspace_root, workspace, task_id),
        "reads": after_reads, "hub": hub_state(), **standing()}

    # 4. The recorded serve command again (same state directory, database and port); the original NodeAgent
    #    reconnects by itself. The first answered exact read, the logs and the one artifact.
    restarted_at = time.monotonic()
    calls_at_restart = len(owned.cli_calls)
    owned.spawn("B hub serve (restarted)", owned.commands["B hub serve"], env, work / "B" / "control.log")
    off.wait_port(port_hub, time.monotonic() + off.budget(30))
    snapshot_after_restart = dis.snapshot_state(backend, task_id)  # recorded only: it depends on heartbeat timing
    live, unavailable_before_answer = dis.first_live_read(side, task_id, RECONNECT_WAIT)
    confirm = dis.classify_read(side, task_id)
    nodes = [d for d in backend.call(backend.hub.devices) if d.get("role") == "node" and not d.get("revoked")]
    device_after = json.loads((node_state / "node.json").read_text(encoding="utf-8"))["device_id"]
    action_after = completion_action(backend, original_action, node_id, workspace)
    restarted_hub = dict(owned.processes)["B hub serve (restarted)"]
    facts["restart"] = {
        "restart_reused_serve_command": owned.commands["B hub serve (restarted)"] == owned.commands["B hub serve"],
        "hub_process_new": dis.identity_of(restarted_hub.pid) not in (None, hub_identity),
        "cli_calls_after_restart": owned.cli_calls[calls_at_restart:],
        "node_device_same": device_after == device_before and [d["id"] for d in nodes] == [device_before],
        "node_devices": len(nodes), "node_log_disconnects": node_log_disconnects(work / "B" / "node.log"),
        **standing()}
    facts["recovered"] = {"first_live": {"same_task": live.get("id") == task_id, "state": live.get("state"),
                                         "cancel_requested": live.get("cancel_requested")},
                          "unavailable_before_answer": unavailable_before_answer, "confirm": confirm,
                          "snapshot_after_restart": snapshot_after_restart, "action_after": action_after,
                          "request_unchanged": action_before["request_sha256"] is not None
                          and action_after["request_sha256"] == action_before["request_sha256"]}
    stdout = off.read_logs(side, task_id)
    # The listing must be exactly the fixed fixture before any content is read (nothing is downloaded otherwise).
    listed, downloaded = dis.download_fixture(side, task_id, backend.artifacts(task_id)["artifacts"])
    direct_stdout = off.read_logs(authority, task_id)
    direct_listed = off.artifact_facts(direct.artifacts(task_id)["artifacts"])
    facts["outputs"] = {
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(), "stdout_bytes": len(stdout),
        "stdout_is_fixed": stdout == dis.RELEASED_STDOUT, "stdout_same_as_runtime": stdout == direct_stdout,
        "artifacts": listed, "artifacts_same_as_runtime": listed == direct_listed,
        "downloads": {path: hashlib.sha256(data).hexdigest() for path, data in downloaded.items()},
        "downloads_are_fixed": {path: data == off.EXPECTED_OUT for path, data in downloaded.items()}}
    ledger_restart = dis.action_ledger(backend)

    # 5. One task, run and start; no cancel; no new delivery, Runtime.submit or Hub action after the submission.
    final_direct = direct.task(task_id)["task"]
    final_execution = dis.running_execution(workspace_root, workspace, task_id)
    stages = read_stages(control)  # one read: the snapshot and the count after the restart come from it
    facts["final"] = {"direct_state": final_direct.get("state"),
                      "cancel_requested": final_direct.get("cancel_requested"),
                      "execution": final_execution, "runs": off.executions(side, workspace),
                      "tasks_in_workspace": len(direct.tasks(workspace)["tasks"]),
                      "stages": stage_snapshot(stages),
                      "executes_after_restart": sum(1 for s in stages if isinstance(s, dict)
                                                    and s.get("stage") == "execute"
                                                    and isinstance(s.get("t"), (int, float))
                                                    and s["t"] > restarted_at)}
    ledger_final = dis.action_ledger(backend)
    facts["actions"] = {"before": dis.kinds(ledger_before), "final": dis.kinds(ledger_final),
                        "unchanged": {"restart": ledger_restart == ledger_before, "final": ledger_final == ledger_before}}
    facts["original_action"] = original_action


def completion_assertions(facts, requests):
    """K0-K12 of the hub-offline-completion scenario; any missing or malformed fact fails its check."""
    def check(predicate):
        try:
            return bool(predicate())
        except (KeyError, TypeError, AttributeError, IndexError):
            return False

    frozen = (facts.get("baseline") or {}).get("execution") or {}
    program, worker = frozen.get("program"), frozen.get("worker")
    submit, base, stop, outage, done, restart, recovered, outputs, final, actions = (
        facts.get(name) or {} for name in ("submit", "baseline", "hub_stop", "outage", "completed_hub_down",
                                           "restart", "recovered", "outputs", "final", "actions"))
    original = facts.get("original_action")
    expected_downloads = {item["path"]: item["sha256"] for item in off.EXPECTED_ARTIFACTS}

    def one_submit(stages):
        """From one stage snapshot with no malformed line: exactly one delivery of each action the client made,
        with the original submission executed once (no cached result before it); exactly one RuntimeClient.submit
        entry, keyed by the original action, and exactly one successful return with the same call number and
        key, returning the original task. A second call that raised shows as a second entry with no return."""
        submits = [s for s in stages["executes"] if s.get("kind") == "task.submit"]
        return (isinstance(original, str) and stages["malformed"] == 0
                and sorted(s.get("kind") for s in stages["executes"]) == ["task.submit", "workspace.create"]
                and len(submits) == 1 and submits[0].get("action") == original and submits[0].get("call") == 1
                and submits[0].get("cached_before") is False
                and stages["runtime_submit_calls"] == [{"stage": "runtime_submit_called", "call": 1, "key": original}]
                and stages["runtime_submits"] == [{"stage": "runtime_submit", "call": 1, "key": original,
                                                   "task_id": submit["task_id"]}])

    checks = [
        ("K0 the launched NodeAgent driver had the expected bytes (hashed when written and right before launch)",
         lambda: driver_bound(facts)),
        ("K1 one submission with a normal receipt naming the Runtime's one task; the Hub action, whose request is "
         "present and bound to the original action, node, task.submit and workspace, succeeded with it before the "
         "fault; the driver held nothing; one delivery, one RuntimeClient.submit entry and one matching return",
         lambda: submit["reply_task_is_runtime_task"] is True and submit["tasks_in_workspace"] == 1
         and submit["action_before_fault"] == {**submit["action_before_fault"], "id_same": True, "state": "succeeded",
                                               "result_present": True, "result_task_id": submit["task_id"]}
         and request_bound(submit["action_before_fault"])
         and submit["first_delivery"]["released"]["release_seen"] is False
         and submit["first_delivery"]["finished"]["send_none"] is False and one_submit(submit["stages"])),
        ("K2 before the fault the original program was ready and ran unreleased with its worker and one start "
         "marker, the heartbeat snapshot listed it running, and the Hub, NodeAgent, Runtime API and supervisor were "
         "alive",
         lambda: base["state"] == "running" and base["ready"] is True and _running(base["execution"], program, worker)
         and base["files"] == UNRELEASED and base["snapshot_running"] is True
         and len(base["alive"]) == 4 and all(v is True for v in base["alive"].values())),
        ("K3 only the original Hub was killed: alive right before the SIGKILL, killed by it, reaped and gone",
         lambda: stop["identity_valid"] is True and stop["running_before_kill"] is True
         and stop["alive_before_kill"] is True and stop["signal_sent"] is True and stop["exit_code"] == -9
         and stop["killed_by_sigkill"] is True and stop["reaped"] is True and stop["node_alive_after"] is False),
        ("K4 released only after the outage was confirmed: the Hub dead and never restarted (port refused), the "
         "original NodeAgent and Runtime alive and not replaced, exact reads refused because the Hub cannot be "
         "reached, and the owned Runtime still running the original unreleased task",
         lambda: hub_outage_confirmed(stop, outage, program, worker)
         and outage["released_after_outage_confirmed"] is True),
        ("K5 with the Hub still dead and never restarted, the owned Runtime reports the original task succeeded "
         "(not cancelled) with its result and output; the original NodeAgent and Runtime stayed alive",
         lambda: done["direct_task"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
         and done["files"] == {"release_flag": True, "finished_record": True, "output_file": True}
         and hub_still_dead(done["hub"]) and survivors_ok(done)),
        ("K6 the original program and worker exited before the restart; still one run and one start",
         lambda: done["original_program_exited"] is True and done["original_worker_exited"] is True
         and _ended(done["execution"], program, worker)),
        ("K7 after the completion exact reads through the dead Hub were still refused because it cannot be reached "
         "(never succeeded, a cached state, a timeout or an unknown read)",
         lambda: len(done["reads"]) >= 2 and all(hub_down_refusal(read) for read in done["reads"])),
        ("K8 a new Hub process from the recorded serve command (same state, database and port) with the pre-fault "
         "state; no init, pairing or profile call; the original NodeAgent process, which logged the lost "
         "connection, reconnected as the same, only node device",
         lambda: restart["restart_reused_serve_command"] is True and restart["hub_process_new"] is True
         and restart["cli_calls_after_restart"] == [] and restart["node_device_same"] is True
         and restart["node_devices"] == 1 and type(restart["node_log_disconnects"]) is int
         and restart["node_log_disconnects"] >= 1 and survivors_ok(restart)),
        ("K9 the first answered exact live read after the restart, whatever its state, is the original task, "
         "succeeded; the original action record is unchanged (same ID, succeeded with the original task, a present "
         "and bound request with the same digest)",
         lambda: recovered["first_live"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
         and type(recovered["unavailable_before_answer"]) is int and recovered["unavailable_before_answer"] >= 0
         and recovered["confirm"] == {"outcome": "answered", "same_task": True, "state": "succeeded",
                                      "hub_reported_online": True}
         and recovered["action_after"] == submit["action_before_fault"] and request_bound(recovered["action_after"])
         and recovered["action_after"]["request_sha256"] == submit["action_before_fault"]["request_sha256"]
         and recovered["request_unchanged"] is True),
        ("K10 the fixed stdout and exactly the fixed out.txt, read and downloaded through the Hub, equal the fixture "
         "and the owned Runtime",
         lambda: outputs["stdout_is_fixed"] is True and outputs["stdout_same_as_runtime"] is True
         and outputs["stdout_sha256"] == hashlib.sha256(dis.RELEASED_STDOUT).hexdigest()
         and outputs["stdout_bytes"] == len(dis.RELEASED_STDOUT)
         and outputs["artifacts"] == off.EXPECTED_ARTIFACTS and outputs["artifacts_same_as_runtime"] is True
         and outputs["downloads"] == expected_downloads
         and outputs["downloads_are_fixed"] == {path: True for path in expected_downloads}),
        ("K11 one task, one run directory with one start whose program and worker exited, never cancelled; no "
         "delivery after the restart, still one RuntimeClient.submit entry and one matching return, the same stage "
         "snapshot as before the fault; the action listing never changed",
         lambda: final["direct_state"] == "succeeded" and final["cancel_requested"] is False
         and _ended(final["execution"], program, worker) and final["runs"] == [off.EXPECTED_RUN]
         and final["tasks_in_workspace"] == 1 and final["executes_after_restart"] == 0
         and final["stages"] == submit["stages"] and one_submit(final["stages"])
         and actions["before"] == ["task.submit", "workspace.create"] == actions["final"]
         and actions["unchanged"] == {"restart": True, "final": True}),
        ("K12 requests: one workspace creation and one accepted submission of the original task; no cancel",
         lambda: [entry["operation"] for entry in requests] == ["workspace.create", "task.submit"]
         and requests[1]["outcome"] == "accepted" and requests[1]["task_id"] == submit["task_id"]),
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


def completion_manifest(origins, ports):
    record = manifest(origins, ports)
    template = dis.RELEASE_TEMPLATES[dis.RELEASE_TEMPLATE]
    record.update({
        "record": "D1 X7 Hub offline-completion trial evidence (informal)",
        "scenario": "hub-offline-completion",
        "deployments": {"B": ["B/runtime (api, supervisor; survive)", "B/control (hub serve; killed, then restarted "
                              "with the same command and state after the task completed)", "B/node (real suan-node "
                              "run through the test driver, count-only; survives and reconnects)"]},
        "templates": {dis.RELEASE_TEMPLATE: {
            "argv_sha256": hashlib.sha256(json.dumps(template["argv"]).encode()).hexdigest(),
            "outputs": template["outputs"], "registered": "this run's Hub only"}},
        "driver": {"sha256": DRIVER_SHA256, "gate_seconds": COUNT_ONLY_GATE,
                   "wraps": ["NodeAgent.execute (count and stage only: the gate is zero, nothing is held)",
                             "NodeAgent._perform (stage only)",
                             "RuntimeClient.submit (count only: staged at each call's entry and at its successful "
                             "return, with the same call number)"]},
        "verified": ["on one Linux host: after one submission with a normal receipt, only the Hub is killed; the "
                     "original task completes on its original Runtime while the Hub is dead and never restarted; "
                     "the same Hub state restarts, the original NodeAgent process reconnects, and the first exact "
                     "live read is the original task succeeded with its fixed log and artifact bytes, with one "
                     "delivery, one RuntimeClient.submit entry with one matching return (counted by the driver in "
                     "the node), one task, run and start, and no cancel"],
        "not_verified": ["Runtime-side counting of submit calls: the one Runtime.submit is counted by the test "
                         "driver inside the NodeAgent; the Runtime itself shows one task and one start",
                         "the Hub dying at other points (before the dispatch, while recording the result), or "
                         "completion before the Hub's death",
                         "that the restarted Hub's heartbeat snapshot is stale or fresh (recorded, not asserted)",
                         "NodeAgent or Runtime restarts, network partitions without a process exit, long outages",
                         "Hub actions outside the client-visible listing (newest 200, plus reviews)",
                         "failover, other hosts, sites or clusters, Windows/macOS",
                         "real solvers, licensed software or scientific validity"]})
    return record


def run(evidence, work_root=None, keep=False, mode="installed", deadline_seconds=170, scenario_name="lost-result"):
    if scenario_name not in SCENARIOS:
        raise ValueError("unknown scenario")
    # Looked up at call time, so a replaced module attribute is the one that runs.
    play, judge, describe = ((scenario, assertions, manifest) if scenario_name == "lost-result"
                             else (scenario_completion, completion_assertions, completion_manifest))
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
    # Each wait and call starts with at most the time left, but a real synchronous HTTP call already in flight is
    # bounded by its client timeout, not cut off at the deadline, so it can end past a local limit. This final
    # gate is what rejects a late run; no hard limit on a single synchronous call is claimed.
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
        **describe(origins, ports), "deadline_seconds": deadline_seconds, "scenario_seconds": scenario_seconds,
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
    parser.add_argument("--scenario", choices=SCENARIOS, default="lost-result",
                        help="lost-result (default): the Hub dies before recording an accepted submission's result, "
                             "restarts, recovers the action, and the running task is cancelled; "
                             "hub-offline-completion: the task completes while the Hub is dead and is read back after "
                             "the restart, with no cancel.")
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
