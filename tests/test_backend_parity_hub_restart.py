"""D1 Hub-restart slice (examples/backend_parity/hub_restart.py).

One real run: the Hub is SIGKILLed after the Runtime accepted the one submission (its program runs) and before
the Hub recorded the result; the same Hub restarts and the original queued action is delivered again. Plus
controlled counterexamples: no accepted-before-loss proof, a wrong fault boundary (the first reply not
dropped), a premature or non-SIGKILL Hub exit, a second start, a changed action or worker identity, a
re-pairing, a cleanup failure and a spent or late budget can never pass. The test driver's gate is checked on
its own as well.

The ``hub-offline-completion`` scenario (X7) has its own real run -- the original task completes while the Hub
process is dead, and is read back succeeded after the same Hub state restarts -- and its own counterexamples: a
premature completion or release, a Hub that was still alive, restarted early or answered with a state, replaced
NodeAgent or Runtime processes, a cached or non-live state after the restart, an extra delivery, Runtime.submit,
action or cancel, and unknown or extra artifacts can never pass. A second same-key RuntimeClient.submit that
raises is still counted at its entry, a malformed driver stage line is never filtered away, and a request digest
needs a request that is really there and bound to the original action, node, kind and workspace.
"""
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "backend_parity" / "hub_restart.py"
HELPERS = {"offline_helper_sha256": ROOT / "examples" / "backend_parity" / "offline.py",
           "disconnect_helper_sha256": ROOT / "examples" / "backend_parity" / "disconnect.py",
           "hub_restart_sha256": SCRIPT}
EVIDENCE_FILES = ("run-manifest.json", "requests.jsonl", "phases.json", "assertions.json", "resources.json")

pytestmark = pytest.mark.server


def harness():
    spec = importlib.util.spec_from_file_location("backend_parity_hub_restart", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child_env():
    env = {k: v for k, v in os.environ.items() if k not in ("STK_TOKEN_PLAN_MODEL", "DISPLAY", "WAYLAND_DISPLAY")}
    env["STK_TOKEN_PLAN_API_KEY"] = ""
    return env


def load(directory, name):
    return json.loads((directory / name).read_text(encoding="utf-8"))


# --- one real run -----------------------------------------------------------------------------------------


@pytest.mark.skipif(platform.system() != "Linux", reason="the Runtime and control service are Linux-only")
def test_hub_restart_after_accepted_submit_recovers_the_original_task(tmp_path):
    for name in ("fastapi", "uvicorn", "httpx", "psutil", "websockets"):
        pytest.importorskip(name)
    evidence = tmp_path / "evidence"
    started = time.monotonic()
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--mode", "source", "--deadline", "170",
                             "--evidence-dir", str(evidence), "--work-root", str(tmp_path)],
                            capture_output=True, text=True, env=child_env(), cwd=tmp_path, timeout=200)
    assert time.monotonic() - started < 180
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    checks = load(evidence, "assertions.json")
    assert result.returncode == 0, (summary, checks)
    assert summary["ok"] and checks["ok"] and checks["cleanup_ok"] and checks["within_deadline"]
    assert len(checks["assertions"]) == 11 and {c["status"] for c in checks["assertions"]} == {"pass"}
    assert checks["driver_bound"] is True

    phases = load(evidence, "phases.json")
    module = harness()
    digest = module.DRIVER_SHA256
    assert phases["driver"] == {"expected_sha256": digest, "written_sha256": digest, "launch_sha256": digest,
                                "launched": True}
    assert phases["submit"]["action_before_fault"]["state"] == "queued"
    assert phases["submit"]["action_before_fault"]["result_present"] is False
    assert phases["hub_stop"]["exit_code"] == -9 and phases["hub_stop"]["alive_before_kill"] is True
    assert phases["outage"]["released"]["send_none"] and phases["outage"]["first_perform_finished"]["send_none"]
    replay = phases["replay"]
    assert [d["call"] for d in replay["deliveries"]] == [1, 2]  # two deliveries of the same action ...
    assert [d["cached_before"] for d in replay["deliveries"]] == [False, True]
    assert replay["runtime_submit_calls"] == 1 and replay["recovery_path"] == "node action cache"  # ... one start
    task = replay["action_after"]["result_task_id"]
    assert {r["task_id"] for r in replay["returns"]} == {task} and replay["request_unchanged"]
    frozen = phases["baseline"]["execution"]
    for phase in ("outage", "recovered"):
        assert phases[phase]["execution"]["program"] == frozen["program"]
        assert phases[phase]["execution"]["worker"] == frozen["worker"]
    assert phases["cancel"]["original_program_exited"] and phases["cancel"]["original_worker_exited"]

    requests = [json.loads(line) for line in (evidence / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["operation"] for r in requests] == ["workspace.create", "task.submit", "task.cancel"]
    assert requests[1]["outcome"] == "timeout" and requests[2]["task_id"] == task

    manifest = load(evidence, "run-manifest.json")
    origins = manifest["module_origins"]
    assert origins["consistent"] and origins["services_base"] == "this source tree" and origins["driver_file_matches"]
    for key, path in HELPERS.items():
        assert origins[key] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert origins["driver_sha256"] == digest == manifest["driver"]["sha256"]
    assert "schema" not in manifest and manifest["within_deadline"] and manifest["scenario_seconds"] <= 170

    resources = load(evidence, "resources.json")
    assert [p["label"] for p in resources["processes"]] == ["B runtime api", "B runtime supervisor", "B hub serve",
                                                           "B node run", "B hub serve (restarted)"]
    assert resources["leftover_pids_after_cleanup"] == [] and resources["removed_work_dir"] is True
    text = "".join((evidence / name).read_text(encoding="utf-8") for name in EVIDENCE_FILES) + result.stdout
    for forbidden in ("token", "Bearer", str(Path.home()), str(tmp_path)):
        assert forbidden not in text
    assert not any(tmp_path.glob("stk-hub-restart-*"))


# --- counterexamples on the assertions --------------------------------------------------------------------


PROGRAM = {"pid": 4194301, "create_time": 1.0}
WORKER = {"pid": 4194299, "create_time": 1.0}
ACTION, TASK, DIGEST = "a" * 32, "t" * 32, "d" * 64
KILLED = {"identity_valid": True, "running_before_kill": True, "alive_before_kill": True, "signal_sent": True,
          "exit_code": -9, "reaped": True, "killed_by_sigkill": True, "node_alive_after": False}


def running():
    return {"run_directories": 1, "run_dir_is_task": True, "program": dict(PROGRAM), "worker": dict(WORKER),
            "program_alive": True, "worker_alive": True, "start_markers": 1, "marker_pid_is_program": True}


def passing_facts(module):
    refused = {"outcome": "refused", "code": "unavailable", "hub_reported_online": None}
    delivery = {"stage": "execute", "action": ACTION, "kind": "task.submit"}
    returned = {"stage": "returned", "action": ACTION, "kind": "task.submit", "task_id": TASK}
    digest = module.DRIVER_SHA256
    return {
        "driver": {"expected_sha256": digest, "written_sha256": digest, "launch_sha256": digest, "launched": True},
        "submit": {"client_outcome": "timeout", "client_reply_task": False, "tasks_in_workspace": 1,
                   "direct_state": "running", "held_stage": True, "accepted_task_is_runtime_task": True,
                   "action_before_fault": {"id_same": True, "state": "queued", "result_present": False,
                                           "result_task_id": None, "request_sha256": DIGEST}},
        "baseline": {"execution": running(), "alive": {"B hub serve": True, "B node run": True, "B runtime api": True,
                                                       "B runtime supervisor": True}},
        "hub_stop": dict(KILLED),
        "outage": {"released": {"stage": "released", "action": ACTION, "release_seen": True, "send_none": True},
                   "first_perform_finished": {"stage": "first_perform_finished", "action": ACTION, "send_none": True},
                   "deliveries_before_restart": 1, "hub_reads": [dict(refused), dict(refused)],
                   "direct_task": {"same_task": True, "state": "running"}, "execution": running(),
                   "alive": {"B node run": True, "B runtime api": True, "B runtime supervisor": True}},
        "restart": {"restart_reused_serve_command": True, "hub_process_new": True, "cli_calls_after_restart": [],
                    "first_delivery_finished_before_restart": True, "node_device_same": True, "node_devices": 1,
                    "node_process_same_alive": True},
        "replay": {"deliveries": [dict(delivery, call=1, cached_before=False), dict(delivery, call=2, cached_before=True)],
                   "returns": [dict(returned, call=1), dict(returned, call=2)],
                   "runtime_submits": [{"stage": "runtime_submit", "call": 1, "key": ACTION, "task_id": TASK}],
                   "redelivered_after_restart": True, "recovered_from_node_cache": True,
                   "recovery_path": "node action cache", "runtime_submit_calls": 1, "every_return_is_original": True,
                   "every_runtime_submit_is_original": True,
                   "action_after": {"id_same": True, "state": "succeeded", "result_present": True,
                                    "result_task_id": TASK, "request_sha256": DIGEST},
                   "request_unchanged": True},
        "recovered": {"live_task": {"same_task": True, "state": "running"}, "execution": running(),
                      "tasks_in_workspace": 1, "ledger_ids_same": True, "ledger_changed": ["task.submit"],
                      "submit_state": "succeeded"},
        "cancel": {"state": "cancelled", "cancel_requested": True, "direct_state": "cancelled", "same_program": True,
                   "same_worker": True, "original_program_exited": True, "original_worker_exited": True,
                   "runs": [dict(module.off.EXPECTED_RUN)], "tasks_in_workspace": 1},
        "actions": {"before": ["task.submit", "workspace.create"], "after_recovery": ["task.submit", "workspace.create"],
                    "final": ["task.cancel", "task.submit", "workspace.create"], "added_by_cancel": ["task.cancel"],
                    "before_kept": True},
    }


REQUESTS = [{"operation": "workspace.create"}, {"operation": "task.submit"}, {"operation": "task.cancel"}]


def failing(module, facts, requests=REQUESTS):
    return {item["id"].split()[0] for item in module.assertions(facts, requests) if item["status"] == "fail"}


def test_baseline_facts_pass():
    module = harness()
    assert failing(module, passing_facts(module)) == set()


def test_missing_facts_never_pass():
    module = harness()
    assert failing(module, {}, []) == {f"H{i}" for i in range(0, 11)}


@pytest.mark.parametrize("change", [
    lambda d: d.update(written_sha256="0" * 64),  # the written file was not the expected driver
    lambda d: d.update(launch_sha256="0" * 64),  # changed between writing and launch
    lambda d: d.update(launch_sha256=None),  # never checked at launch
    lambda d: d.pop("written_sha256"),  # no record of the check at all
    lambda d: d.update(expected_sha256="0" * 64),  # bound to another driver text
    lambda d: d.update(launched=False),  # the checked file was never launched
    lambda d: d.clear(),
])
def test_wrong_or_missing_driver_proof_fails(change):
    module = harness()
    facts = passing_facts(module)
    change(facts["driver"])
    assert failing(module, facts) == {"H0"}
    del facts["driver"]
    assert failing(module, facts) == {"H0"}


@pytest.mark.parametrize("change, broken", [
    # No accepted-before-loss proof: the reply reached the client, nothing was held, the Hub already had the
    # result, or the Runtime task is not the one the node accepted.
    (lambda f, r: f["submit"].update(client_outcome="accepted", client_reply_task=True), {"H1"}),
    (lambda f, r: f["submit"]["action_before_fault"].update(state="succeeded", result_present=True), {"H1"}),
    (lambda f, r: f["submit"].update(accepted_task_is_runtime_task=False), {"H1"}),
    (lambda f, r: f["submit"].update(tasks_in_workspace=0), {"H1"}),
    # The program was not really running before the fault.
    (lambda f, r: f["baseline"]["execution"].update(program_alive=False), {"H2"}),
    (lambda f, r: f["baseline"]["alive"].update({"B node run": False}), {"H2"}),
    # A premature, natural or non-SIGKILL Hub exit is not the injected fault.
    (lambda f, r: f["hub_stop"].update(running_before_kill=False, alive_before_kill=False, signal_sent=False,
                                       exit_code=0, killed_by_sigkill=False), {"H3"}),
    (lambda f, r: f["hub_stop"].update(exit_code=-15, killed_by_sigkill=False), {"H3"}),
    (lambda f, r: f["hub_stop"].update(exit_code=1, killed_by_sigkill=False, signal_sent=False), {"H3"}),
    (lambda f, r: f["hub_stop"].update(identity_valid=False), {"H3"}),
    (lambda f, r: f["hub_stop"].update(node_alive_after=True), {"H3"}),
    # A bogus state while the Hub was down, or a service that went down with it.
    (lambda f, r: f["outage"]["hub_reads"].__setitem__(0, {"outcome": "answered", "state": "failed"}), {"H4"}),
    (lambda f, r: f["outage"].update(hub_reads=[]), {"H4"}),
    (lambda f, r: f["outage"]["alive"].update({"B node run": False}), {"H4"}),
    # The wrong fault boundary: the first reply was not dropped while disconnected, or a delivery reached the
    # node again before the restart (an in-flight re-dispatch instead of a recovery).
    (lambda f, r: f["outage"]["released"].update(send_none=False), {"H5"}),
    (lambda f, r: f["outage"]["released"].update(release_seen=False), {"H5"}),
    (lambda f, r: f["outage"]["first_perform_finished"].update(send_none=False), {"H5"}),
    (lambda f, r: f["outage"].update(deliveries_before_restart=2), {"H5"}),
    (lambda f, r: f["restart"].update(first_delivery_finished_before_restart=False), {"H5"}),
    # Not the same Hub, or a re-paired node.
    (lambda f, r: f["restart"].update(hub_process_new=False), {"H6"}),
    (lambda f, r: f["restart"].update(cli_calls_after_restart=["B pair node"]), {"H6"}),
    (lambda f, r: f["restart"].update(node_device_same=False), {"H6"}),
    (lambda f, r: f["restart"].update(node_devices=2), {"H6"}),
    (lambda f, r: f["restart"].update(node_process_same_alive=False), {"H6"}),
    # No redelivery, a changed action, a different task, or an unclassified recovery.
    (lambda f, r: f["replay"].update(redelivered_after_restart=False), {"H7"}),
    (lambda f, r: f["replay"].update(request_unchanged=False), {"H7"}),
    (lambda f, r: f["replay"]["action_after"].update(id_same=False), {"H7"}),
    (lambda f, r: f["replay"]["action_after"].update(result_task_id="o" * 32), {"H7"}),
    (lambda f, r: f["replay"].update(every_return_is_original=False), {"H7"}),
    (lambda f, r: f["replay"].update(every_runtime_submit_is_original=False), {"H7"}),
    (lambda f, r: f["replay"].update(recovery_path="unclassified"), {"H7"}),
    (lambda f, r: f["replay"]["action_after"].update(state="failed"), {"H7"}),
    # A second start or a changed worker identity at any point.
    (lambda f, r: f["outage"]["execution"].update(worker={"pid": 4194298, "create_time": 1.0}), {"H4"}),
    (lambda f, r: f["recovered"]["execution"].update(start_markers=2), {"H8"}),
    (lambda f, r: f["recovered"]["execution"].update(run_directories=2), {"H8"}),
    (lambda f, r: f["recovered"].update(tasks_in_workspace=2), {"H8"}),
    (lambda f, r: f["recovered"].update(ledger_ids_same=False), {"H8"}),
    (lambda f, r: f["recovered"].update(ledger_changed=["task.submit", "workspace.create"]), {"H8"}),
    (lambda f, r: f["cancel"].update(runs=[dict(f["cancel"]["runs"][0], start_markers=2)]), {"H9"}),
    (lambda f, r: f["cancel"].update(original_worker_exited=False), {"H9"}),
    (lambda f, r: f["cancel"].update(same_worker=False), {"H9"}),
    (lambda f, r: f["actions"].update(added_by_cancel=["task.cancel", "task.submit"]), {"H9"}),
    # A caller resubmission.
    (lambda f, r: r.insert(2, {"operation": "task.submit"}), {"H10"}),
])
def test_wrong_boundary_or_duplicate_execution_fails(change, broken):
    module = harness()
    facts, requests = passing_facts(module), copy.deepcopy(REQUESTS)
    change(facts, requests)
    assert failing(module, facts, requests) == broken


def test_a_runtime_idempotent_replay_is_also_accepted_but_labelled():
    """If the node had re-run Runtime.submit with the same identity, the same task must come back; the evidence
    then says so instead of claiming a cache recovery."""
    module = harness()
    facts = passing_facts(module)
    facts["replay"].update(recovered_from_node_cache=False, recovery_path="Runtime idempotent replay",
                           runtime_submit_calls=2)
    facts["replay"]["runtime_submits"].append({"stage": "runtime_submit", "call": 2, "key": ACTION, "task_id": TASK})
    assert failing(module, facts) == set()


# --- the driver's gate, on its own ------------------------------------------------------------------------


def driver_namespace():
    namespace = {"__name__": "hub_restart_driver_test"}
    exec(compile(harness().DRIVER, "node_driver.py", "exec"), namespace)  # noqa: S102 - the fixed driver text
    return namespace


class Agent:
    """A stand-in with the attributes the driver reads; the real NodeAgent is used by the integration run."""

    def __init__(self, cache):
        self.cache, self._send = cache, object()
        self.results = []

    def execute(self, action):
        self.results.append(action["id"])
        return {"id": "task-1"}

    async def _perform(self, action, lane):
        await asyncio.to_thread(self.execute, action)


class Client:
    def submit(self, spec, idempotency_key=None):
        return {"id": "task-1"}


def stage_names(control):
    return [json.loads(line)["stage"] for line in (control / "stages.jsonl").read_text(encoding="utf-8").splitlines()]


def test_driver_holds_only_the_first_submit_until_released_and_disconnected(tmp_path):
    namespace, agent_class, client_class = driver_namespace(), type("A", (Agent,), {}), type("C", (Client,), {})
    namespace["install"](agent_class, client_class, tmp_path, 10)
    agent = agent_class(tmp_path)
    done = []
    thread = threading.Thread(target=lambda: done.append(agent.execute({"id": "x" * 32, "kind": "task.submit"})))
    thread.start()
    time.sleep(0.3)
    assert not done and stage_names(tmp_path)[-1] == "held"  # held while not released
    (tmp_path / "release").write_text("", encoding="ascii")
    time.sleep(0.3)
    assert not done  # released, but still connected: the reply is not given back yet
    agent._send = None
    thread.join(5)
    assert done == [{"id": "task-1"}]
    released = [json.loads(line) for line in (tmp_path / "stages.jsonl").read_text(encoding="utf-8").splitlines()][-1]
    assert released["stage"] == "released" and released["release_seen"] and released["send_none"]
    started = time.monotonic()
    assert agent.execute({"id": "x" * 32, "kind": "task.submit"}) == {"id": "task-1"}  # second delivery: not held
    assert time.monotonic() - started < 1
    assert client_class().submit({}, "k") == {"id": "task-1"} and stage_names(tmp_path)[-1] == "runtime_submit"


def test_driver_gate_is_bounded_and_reports_no_release(tmp_path):
    namespace, agent_class, client_class = driver_namespace(), type("A", (Agent,), {}), type("C", (Client,), {})
    namespace["install"](agent_class, client_class, tmp_path, 0.3)
    agent = agent_class(tmp_path)
    started = time.monotonic()
    agent.execute({"id": "y" * 32, "kind": "task.submit"})
    assert time.monotonic() - started < 3
    released = json.loads((tmp_path / "stages.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert released == {"stage": "released", "t": released["t"], "action": "y" * 32, "release_seen": False,
                        "send_none": False}


def test_driver_reports_whether_the_first_delivery_had_a_connection(tmp_path):
    namespace, agent_class, client_class = driver_namespace(), type("A", (Agent,), {}), type("C", (Client,), {})
    namespace["install"](agent_class, client_class, tmp_path, 5)
    agent = agent_class(tmp_path)
    (tmp_path / "release").write_text("", encoding="ascii")
    agent._send = None
    asyncio.run(agent._perform({"id": "z" * 32, "kind": "task.submit"}, None))
    finished = json.loads((tmp_path / "stages.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert finished["stage"] == "first_perform_finished" and finished["send_none"] is True


# --- run level: cleanup failure, spent or late budget, controlled errors -----------------------------------


def fake_scenario(module, delay=0.0, driver=lambda d: None):
    def scenario(owned, env, facts, log, clients):
        time.sleep(delay)
        facts.update(passing_facts(module))
        driver(facts["driver"])
        log.extend(copy.deepcopy(REQUESTS))
    return scenario


def test_a_passing_scenario_passes_the_run_gate(tmp_path, monkeypatch):
    """The run-level baseline for the counterexamples below: the same facts with correct driver proof pass."""
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "scenario", fake_scenario(module))
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    checks = load(tmp_path / "evidence", "assertions.json")
    assert ok is True and error is None and checks["driver_bound"] is True
    assert load(tmp_path / "evidence", "run-manifest.json")["module_origins"]["driver_file_matches"] is True


@pytest.mark.parametrize("change", [lambda d: d.update(launch_sha256="0" * 64), lambda d: d.clear()])
def test_wrong_or_missing_driver_proof_fails_the_run(tmp_path, monkeypatch, change):
    """Every other check and cleanup pass, yet the run is not ok without the driver proof."""
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "scenario", fake_scenario(module, driver=change))
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    checks = load(tmp_path / "evidence", "assertions.json")
    assert error is None and checks["cleanup_ok"] and checks["within_deadline"]
    assert [c["id"].split()[0] for c in checks["assertions"] if c["status"] == "fail"] == ["H0"]
    assert ok is False and checks["ok"] is False and checks["driver_bound"] is False
    assert load(tmp_path / "evidence", "run-manifest.json")["module_origins"]["driver_file_matches"] is False


def test_a_tampered_driver_is_refused_before_any_service_starts(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "DRIVER", module.DRIVER + "\n# tampered\n")  # the digest stays the original

    def must_not_start(*args):
        pytest.fail("a service started with a tampered driver")

    monkeypatch.setattr(module.off, "start_runtime", must_not_start)
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    assert ok is False and error == {"kind": "error", "message": module.DRIVER_MISMATCH}
    assert load(tmp_path / "evidence", "resources.json")["processes"] == []
    assert load(tmp_path / "evidence", "phases.json")["driver"]["launched"] is False


def test_a_driver_changed_before_launch_is_never_launched(tmp_path, monkeypatch):
    """The real launch check: the file is changed after it was written; the NodeAgent spawn is refused."""
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module.off, "start_runtime", lambda owned, state, env, label: (None, 1, tmp_path))

    def start_hub(owned, base, env, runtime_state):
        (owned.work / "driver" / "node_driver.py").write_text("print('not the driver')\n", encoding="utf-8")
        owned.spawn("B node run", [sys.executable, "-c", "pass"], env, owned.work / "node.log")
        pytest.fail("the tampered driver was launched")

    monkeypatch.setattr(module.off, "start_hub", start_hub)
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    assert ok is False and error == {"kind": "error", "message": module.DRIVER_MISMATCH}
    assert load(tmp_path / "evidence", "resources.json")["processes"] == []
    driver = load(tmp_path / "evidence", "phases.json")["driver"]
    assert driver["written_sha256"] == module.DRIVER_SHA256 != driver["launch_sha256"] and driver["launched"] is False


def test_a_passing_scenario_with_a_cleanup_failure_is_not_ok(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "scenario", fake_scenario(module))
    real = module.off.clean_up

    def failing_clean_up(owned, env, keep, clients):
        real(owned, env, keep, clients)
        owned.resources["cleanup"].append({"label": "B hub serve (restarted)", "error": "PermissionError"})

    monkeypatch.setattr(module.off, "clean_up", failing_clean_up)
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    checks = load(tmp_path / "evidence", "assertions.json")
    assert error is None and {c["status"] for c in checks["assertions"]} == {"pass"}
    assert ok is False and checks["cleanup_ok"] is False and checks["ok"] is False


def test_a_late_scenario_is_not_ok(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "scenario", fake_scenario(module, delay=0.4))
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=0.3)
    checks = load(tmp_path / "evidence", "assertions.json")
    assert {c["status"] for c in checks["assertions"]} == {"pass"}  # every check passed, but too late
    assert ok is False and checks["within_deadline"] is False


def test_a_spent_budget_stops_the_scenario_as_unknown(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})

    def slow(owned, env, facts, log, clients):
        time.sleep(0.3)
        module.wait_stage(owned.work, lambda s: True, 30, "anything")  # budgeted: the budget is already spent

    monkeypatch.setattr(module, "scenario", slow)
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=0.2)
    assert ok is False and error["kind"] == "unknown"
    assert load(tmp_path / "evidence", "assertions.json")["assertions"] == []


def test_earlier_evidence_is_never_overwritten(tmp_path):
    module = harness()
    earlier = tmp_path / "trial"
    earlier.mkdir()
    (earlier / "assertions.json").write_text('{"ok": false}', encoding="utf-8")
    assert module.main(["--mode", "source", "--evidence-dir", str(earlier), "--work-root", str(tmp_path)]) == 2
    assert (earlier / "assertions.json").read_text(encoding="utf-8") == '{"ok": false}'


def test_startup_failure_is_controlled(tmp_path, monkeypatch, capsys):
    module = harness()
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})

    def leaking(*args):
        raise FileNotFoundError("/home/someone-else/manufactured-secret-0000")

    monkeypatch.setattr(module.off, "start_runtime", leaking)
    evidence = tmp_path / "evidence"
    assert module.main(["--mode", "source", "--evidence-dir", str(evidence), "--work-root", str(tmp_path)]) == 1
    printed = capsys.readouterr()
    text = "".join((evidence / name).read_text(encoding="utf-8") for name in EVIDENCE_FILES) + printed.out + printed.err
    assert "someone-else" not in text and "manufactured-secret" not in text
    assert load(evidence, "assertions.json")["assertions"] == []
    assert not any(tmp_path.glob("stk-hub-restart-*"))


# --- hub-offline-completion: one real run ------------------------------------------------------------------


@pytest.mark.skipif(platform.system() != "Linux", reason="the Runtime and control service are Linux-only")
def test_task_completes_while_the_hub_is_dead_and_is_read_back_after_the_restart(tmp_path):
    for name in ("fastapi", "uvicorn", "httpx", "psutil", "websockets"):
        pytest.importorskip(name)
    evidence = tmp_path / "evidence"
    started = time.monotonic()
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--mode", "source", "--deadline", "170",
                             "--scenario", "hub-offline-completion", "--evidence-dir", str(evidence),
                             "--work-root", str(tmp_path)],
                            capture_output=True, text=True, env=child_env(), cwd=tmp_path, timeout=200)
    assert time.monotonic() - started < 180
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    checks = load(evidence, "assertions.json")
    assert result.returncode == 0, (summary, checks)
    assert summary["ok"] and checks["ok"] and checks["cleanup_ok"] and checks["within_deadline"]
    assert [c["id"].split()[0] for c in checks["assertions"]] == [f"K{i}" for i in range(13)]
    assert {c["status"] for c in checks["assertions"]} == {"pass"} and checks["driver_bound"] is True

    module = harness()
    phases = load(evidence, "phases.json")
    task, action = phases["submit"]["task_id"], phases["original_action"]
    assert phases["submit"]["action_before_fault"]["state"] == "succeeded"
    assert phases["submit"]["action_before_fault"]["result_task_id"] == task
    assert phases["submit"]["first_delivery"]["released"]["release_seen"] is False  # nothing was held
    assert phases["hub_stop"]["exit_code"] == -9 and phases["hub_stop"]["alive_before_kill"] is True
    for phase in ("outage", "completed_hub_down"):
        assert phases[phase]["hub"] == {"original_exit_code": -9, "original_alive": False,
                                        "hub_serves": ["B hub serve"], "port_refused": True}
        assert all(module.hub_down_refusal(read) for read in phases[phase]["reads"])
        assert phases[phase]["node_runs"] == ["B node run"] and all(phases[phase]["survivors"].values())
    assert phases["outage"]["direct_task"]["state"] == "running" and phases["outage"]["files"] == module.UNRELEASED
    assert phases["completed_hub_down"]["direct_task"]["state"] == "succeeded"
    assert phases["recovered"]["first_live"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
    assert phases["recovered"]["action_after"] == phases["submit"]["action_before_fault"]
    stages = phases["final"]["stages"]
    assert [s["kind"] for s in stages["executes"]] == ["workspace.create", "task.submit"]
    assert stages["runtime_submit_calls"] == [{"stage": "runtime_submit_called", "call": 1, "key": action}]
    assert stages["runtime_submits"] == [{"stage": "runtime_submit", "call": 1, "key": action, "task_id": task}]
    assert stages["malformed"] == 0 and phases["final"]["stages"] == phases["submit"]["stages"]
    for record in (phases["submit"]["action_before_fault"], phases["recovered"]["action_after"]):
        assert module.request_bound(record) and "request" not in record  # only the digest is exported
    assert phases["final"]["executes_after_restart"] == 0
    frozen = phases["baseline"]["execution"]
    for phase in ("outage", "completed_hub_down"):
        assert phases[phase]["execution"]["program"] == frozen["program"]
        assert phases[phase]["execution"]["worker"] == frozen["worker"]
    assert phases["outputs"]["downloads"] == {"out.txt": hashlib.sha256(module.off.EXPECTED_OUT).hexdigest()}

    requests = [json.loads(line) for line in (evidence / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["operation"] for r in requests] == ["workspace.create", "task.submit"]
    assert requests[1]["outcome"] == "accepted" and requests[1]["task_id"] == task

    manifest = load(evidence, "run-manifest.json")
    assert manifest["scenario"] == "hub-offline-completion" and manifest["driver"]["gate_seconds"] == 0
    origins = manifest["module_origins"]
    assert origins["consistent"] and origins["services_base"] == "this source tree" and origins["driver_file_matches"]
    for key, path in HELPERS.items():
        assert origins[key] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest["within_deadline"] and manifest["scenario_seconds"] <= 170

    resources = load(evidence, "resources.json")
    assert [p["label"] for p in resources["processes"]] == ["B runtime api", "B runtime supervisor", "B hub serve",
                                                           "B node run", "B hub serve (restarted)"]
    assert resources["leftover_pids_after_cleanup"] == [] and resources["removed_work_dir"] is True
    text = "".join((evidence / name).read_text(encoding="utf-8") for name in EVIDENCE_FILES) + result.stdout
    for forbidden in ("token", "Bearer", str(Path.home()), str(tmp_path)):
        assert forbidden not in text
    assert not any(tmp_path.glob("stk-hub-restart-*"))


# --- hub-offline-completion: counterexamples on the assertions ---------------------------------------------


SUBMIT_ACTION, WS_ACTION = "s" * 32, "w" * 32
DEAD_READ = {"outcome": "refused", "code": "unavailable", "cause": "unreachable", "hub_reported_online": None,
             "hub_reported_online_after": None, "port_refused_before": True, "port_refused_after": True}
HUB_DEAD = {"original_exit_code": -9, "original_alive": False, "hub_serves": ["B hub serve"], "port_refused": True}
SURVIVING = {"survivors": {"B node run": True, "B runtime api": True, "B runtime supervisor": True},
             "node_runs": ["B node run"]}


def ended():
    return dict(running(), program_alive=False, worker_alive=False)


def completion_stages():
    return {"executes": [{"stage": "execute", "action": WS_ACTION, "kind": "workspace.create", "call": 1,
                          "cached_before": False},
                         {"stage": "execute", "action": SUBMIT_ACTION, "kind": "task.submit", "call": 1,
                          "cached_before": False}],
            "runtime_submit_calls": [{"stage": "runtime_submit_called", "call": 1, "key": SUBMIT_ACTION}],
            "runtime_submits": [{"stage": "runtime_submit", "call": 1, "key": SUBMIT_ACTION, "task_id": TASK}],
            "malformed": 0}


BOUND = {"action_id": True, "node_id": True, "kind_task_submit": True, "workspace": True}


def completion_facts(module):
    digest = module.DRIVER_SHA256
    action = {"id_same": True, "state": "succeeded", "result_present": True, "result_task_id": TASK,
              "request_present": True, "request_bound": dict(BOUND), "request_sha256": DIGEST}
    return {
        "driver": {"expected_sha256": digest, "written_sha256": digest, "launch_sha256": digest, "launched": True},
        "original_action": SUBMIT_ACTION,
        "submit": {"task_id": TASK, "tasks_in_workspace": 1, "reply_task_is_runtime_task": True,
                   "action_before_fault": copy.deepcopy(action),
                   "first_delivery": {"released": {"stage": "released", "action": SUBMIT_ACTION, "release_seen": False,
                                                   "send_none": False},
                                      "finished": {"stage": "first_perform_finished", "action": SUBMIT_ACTION,
                                                   "send_none": False}},
                   "stages": completion_stages()},
        "baseline": {"state": "running", "ready": True, "execution": running(), "snapshot_running": True,
                     "files": dict(module.UNRELEASED),
                     "alive": {"B hub serve": True, "B node run": True, "B runtime api": True,
                               "B runtime supervisor": True}},
        "hub_stop": dict(KILLED),
        "outage": {"reads": [dict(DEAD_READ), dict(DEAD_READ)], "hub": dict(HUB_DEAD), **copy.deepcopy(SURVIVING),
                   "direct_task": {"same_task": True, "state": "running"}, "execution": running(),
                   "files": dict(module.UNRELEASED), "released_after_outage_confirmed": True},
        "completed_hub_down": {"direct_task": {"same_task": True, "state": "succeeded", "cancel_requested": False},
                               "original_program_exited": True, "original_worker_exited": True, "execution": ended(),
                               "files": {"release_flag": True, "finished_record": True, "output_file": True},
                               "reads": [dict(DEAD_READ), dict(DEAD_READ)], "hub": dict(HUB_DEAD),
                               **copy.deepcopy(SURVIVING)},
        "restart": {"restart_reused_serve_command": True, "hub_process_new": True, "cli_calls_after_restart": [],
                    "node_device_same": True, "node_devices": 1, "node_log_disconnects": 1,
                    **copy.deepcopy(SURVIVING)},
        "recovered": {"first_live": {"same_task": True, "state": "succeeded", "cancel_requested": False},
                      "unavailable_before_answer": 0,
                      "confirm": {"outcome": "answered", "same_task": True, "state": "succeeded",
                                  "hub_reported_online": True},
                      "snapshot_after_restart": "running", "action_after": copy.deepcopy(action),
                      "request_unchanged": True},
        "outputs": {"stdout_sha256": hashlib.sha256(module.dis.RELEASED_STDOUT).hexdigest(),
                    "stdout_bytes": len(module.dis.RELEASED_STDOUT), "stdout_is_fixed": True,
                    "stdout_same_as_runtime": True, "artifacts": copy.deepcopy(module.off.EXPECTED_ARTIFACTS),
                    "artifacts_same_as_runtime": True,
                    "downloads": {i["path"]: i["sha256"] for i in module.off.EXPECTED_ARTIFACTS},
                    "downloads_are_fixed": {i["path"]: True for i in module.off.EXPECTED_ARTIFACTS}},
        "final": {"direct_state": "succeeded", "cancel_requested": False, "execution": ended(),
                  "runs": [dict(module.off.EXPECTED_RUN)], "tasks_in_workspace": 1, "stages": completion_stages(),
                  "executes_after_restart": 0},
        "actions": {"before": ["task.submit", "workspace.create"], "final": ["task.submit", "workspace.create"],
                    "unchanged": {"restart": True, "final": True}},
    }


COMPLETION_REQUESTS = [{"operation": "workspace.create"},
                       {"operation": "task.submit", "outcome": "accepted", "task_id": TASK}]


def completion_failing(module, facts, requests=COMPLETION_REQUESTS):
    return {item["id"].split()[0] for item in module.completion_assertions(facts, requests)
            if item["status"] == "fail"}


def test_completion_baseline_facts_pass():
    module = harness()
    assert completion_failing(module, completion_facts(module)) == set()


def test_completion_missing_facts_never_pass():
    module = harness()
    assert completion_failing(module, {}, []) == {f"K{i}" for i in range(13)}


SECOND_SUBMIT = {"stage": "runtime_submit", "call": 2, "key": SUBMIT_ACTION, "task_id": TASK}
REDELIVERY = {"stage": "execute", "action": SUBMIT_ACTION, "kind": "task.submit", "call": 2, "cached_before": True}
SECOND_CALL = {"stage": "runtime_submit_called", "call": 2, "key": SUBMIT_ACTION}


@pytest.mark.parametrize("change, broken", [
    # The receipt did not arrive, the action had no result, or the driver held the reply (the lost-result fault).
    (lambda f, r: f["submit"].update(reply_task_is_runtime_task=False), {"K1"}),
    (lambda f, r: f["submit"]["action_before_fault"].update(state="queued", result_present=False,
                                                            result_task_id=None), {"K1", "K9"}),
    (lambda f, r: f["submit"]["first_delivery"]["released"].update(release_seen=True), {"K1"}),
    (lambda f, r: f["submit"]["first_delivery"]["finished"].update(send_none=True), {"K1"}),
    # A premature completion: the program was released or done before the fault, or before the outage was proven.
    (lambda f, r: f["baseline"].update(files={"release_flag": True, "finished_record": False,
                                              "output_file": False}), {"K2"}),
    (lambda f, r: f["baseline"]["execution"].update(program_alive=False), {"K2"}),
    (lambda f, r: f["outage"]["direct_task"].update(state="succeeded"), {"K4"}),
    (lambda f, r: f["outage"].update(files={"release_flag": False, "finished_record": True,
                                            "output_file": True}), {"K4"}),
    (lambda f, r: f["outage"].update(released_after_outage_confirmed=False), {"K4"}),
    # Not the injected fault: the Hub exited on its own, by another signal, or was never reaped.
    (lambda f, r: f["hub_stop"].update(running_before_kill=False, alive_before_kill=False, signal_sent=False,
                                       exit_code=0, killed_by_sigkill=False), {"K3", "K4"}),
    (lambda f, r: f["hub_stop"].update(exit_code=-15, killed_by_sigkill=False), {"K3", "K4"}),
    (lambda f, r: f["hub_stop"].update(reaped=False), {"K3", "K4"}),
    # The Hub was not dead during the outage, or was restarted before the completion.
    (lambda f, r: f["outage"]["hub"].update(port_refused=False), {"K4"}),
    (lambda f, r: f["outage"]["hub"].update(original_alive=True), {"K4"}),
    (lambda f, r: f["completed_hub_down"]["hub"].update(hub_serves=["B hub serve", "B hub serve (restarted)"]),
     {"K5"}),
    (lambda f, r: f["completed_hub_down"]["hub"].update(port_refused=False), {"K5"}),
    # A read during the outage answered with a state, or was refused for another reason (a live Hub that lists
    # the node offline, a timeout, an unknown read, an open port).
    (lambda f, r: f["outage"]["reads"].__setitem__(0, {**DEAD_READ, "outcome": "answered", "state": "running"}),
     {"K4"}),
    (lambda f, r: f["outage"]["reads"].__setitem__(1, {**DEAD_READ, "cause": "node_offline",
                                                       "hub_reported_online": False,
                                                       "hub_reported_online_after": False}), {"K4"}),
    (lambda f, r: f["outage"]["reads"].__setitem__(0, {**DEAD_READ, "cause": "timeout"}), {"K4"}),
    (lambda f, r: f["outage"]["reads"].__setitem__(0, {"outcome": "unknown"}), {"K4"}),
    (lambda f, r: f["outage"]["reads"].__setitem__(0, {**DEAD_READ, "port_refused_after": False}), {"K4"}),
    (lambda f, r: f["outage"].update(reads=[dict(DEAD_READ)]), {"K4"}),
    (lambda f, r: f["completed_hub_down"]["reads"].__setitem__(0, {**DEAD_READ, "outcome": "answered",
                                                                   "state": "succeeded"}), {"K7"}),
    (lambda f, r: f["completed_hub_down"].update(reads=[]), {"K7"}),
    # A replaced or lost NodeAgent or Runtime process at any point.
    (lambda f, r: f["outage"]["survivors"].update({"B node run": False}), {"K4"}),
    (lambda f, r: f["outage"].update(node_runs=["B node run", "B node run (restarted)"]), {"K4"}),
    (lambda f, r: f["completed_hub_down"]["survivors"].update({"B runtime supervisor": False}), {"K5"}),
    (lambda f, r: f["restart"]["survivors"].update({"B node run": False}), {"K8"}),
    (lambda f, r: f["restart"].update(node_runs=["B node run", "B node run (restarted)"]), {"K8"}),
    (lambda f, r: f["outage"]["execution"].update(worker={"pid": 4194298, "create_time": 1.0}), {"K4"}),
    # The completion itself: not succeeded, cancelled, without its result, or the processes still running.
    (lambda f, r: f["completed_hub_down"]["direct_task"].update(state="failed"), {"K5"}),
    (lambda f, r: f["completed_hub_down"]["direct_task"].update(state="cancelled", cancel_requested=True), {"K5"}),
    (lambda f, r: f["completed_hub_down"]["files"].update(output_file=False), {"K5"}),
    (lambda f, r: f["completed_hub_down"].update(original_worker_exited=False), {"K6"}),
    (lambda f, r: f["completed_hub_down"]["execution"].update(program_alive=True), {"K6"}),
    # Not the same Hub state or endpoint, or a re-paired node.
    (lambda f, r: f["restart"].update(restart_reused_serve_command=False), {"K8"}),
    (lambda f, r: f["restart"].update(hub_process_new=False), {"K8"}),
    (lambda f, r: f["restart"].update(cli_calls_after_restart=["B pair node"]), {"K8"}),
    (lambda f, r: f["restart"].update(node_device_same=False), {"K8"}),
    (lambda f, r: f["restart"].update(node_log_disconnects=0), {"K8"}),
    (lambda f, r: f["restart"].update(node_log_disconnects=None), {"K8"}),
    # A cached, stale or other task's state served as the first live answer, or a changed action.
    (lambda f, r: f["recovered"]["first_live"].update(state="running"), {"K9"}),
    (lambda f, r: f["recovered"]["first_live"].update(same_task=False), {"K9"}),
    (lambda f, r: f["recovered"]["confirm"].update(hub_reported_online=False), {"K9"}),
    (lambda f, r: f["recovered"].update(unavailable_before_answer=None), {"K9"}),
    (lambda f, r: f["recovered"]["action_after"].update(request_sha256="e" * 64), {"K9"}),
    (lambda f, r: f["recovered"]["action_after"].update(result_task_id="o" * 32), {"K9"}),
    # A request that is missing, or not bound to the original action, node, kind or workspace.
    (lambda f, r: [record.update(request_present=False, request_sha256=None,
                                 request_bound=dict.fromkeys(BOUND, False))
                   for record in (f["submit"]["action_before_fault"], f["recovered"]["action_after"])], {"K1", "K9"}),
    (lambda f, r: [record["request_bound"].update(workspace=False)
                   for record in (f["submit"]["action_before_fault"], f["recovered"]["action_after"])], {"K1", "K9"}),
    (lambda f, r: f["recovered"]["action_after"]["request_bound"].update(node_id=False), {"K9"}),
    (lambda f, r: f["submit"]["action_before_fault"]["request_bound"].update(kind_task_submit=False), {"K1", "K9"}),
    # Wrong log bytes, or an unknown or extra artifact.
    (lambda f, r: f["outputs"].update(stdout_is_fixed=False), {"K10"}),
    (lambda f, r: f["outputs"].update(stdout_same_as_runtime=False), {"K10"}),
    (lambda f, r: f["outputs"]["artifacts"].append({"path": "extra.txt", "size": 1, "sha256": "0" * 64,
                                                    "media_type": "text/plain"}), {"K10"}),
    (lambda f, r: f["outputs"]["downloads"].update({"extra.txt": "0" * 64}), {"K10"}),
    (lambda f, r: f["outputs"].update(artifacts_same_as_runtime=False), {"K10"}),
    # A redelivery, a second Runtime.submit, a cancel, a second start or task, or a new Hub action.
    (lambda f, r: f["final"].update(executes_after_restart=1), {"K11"}),
    (lambda f, r: f["final"]["stages"]["executes"].append(dict(REDELIVERY)), {"K11"}),
    (lambda f, r: f["final"]["stages"]["runtime_submits"].append(dict(SECOND_SUBMIT)), {"K11"}),
    (lambda f, r: f["submit"]["stages"]["runtime_submits"].append(dict(SECOND_SUBMIT)), {"K1", "K11"}),
    (lambda f, r: f["submit"]["stages"]["executes"][1].update(cached_before=True), {"K1", "K11"}),
    # A second RuntimeClient.submit entry (e.g. one that raised, so it has no return), or a malformed stage line.
    (lambda f, r: f["final"]["stages"]["runtime_submit_calls"].append(dict(SECOND_CALL)), {"K11"}),
    (lambda f, r: f["submit"]["stages"]["runtime_submit_calls"].append(dict(SECOND_CALL)), {"K1", "K11"}),
    (lambda f, r: f["final"]["stages"]["runtime_submit_calls"].clear(), {"K11"}),
    (lambda f, r: f["final"]["stages"]["runtime_submits"][0].update(call=2), {"K11"}),
    (lambda f, r: f["final"]["stages"].update(malformed=1), {"K11"}),
    (lambda f, r: f["submit"]["stages"].update(malformed=1), {"K1", "K11"}),
    (lambda f, r: f["final"].update(cancel_requested=True), {"K11"}),
    (lambda f, r: f["final"].update(runs=[dict(f["final"]["runs"][0], start_markers=2)]), {"K11"}),
    (lambda f, r: f["final"].update(tasks_in_workspace=2), {"K11"}),
    (lambda f, r: f["actions"].update(final=["task.cancel", "task.submit", "workspace.create"]), {"K11"}),
    (lambda f, r: f["actions"]["unchanged"].update(restart=False), {"K11"}),
    # A caller cancel or resubmission, or a submission without its receipt.
    (lambda f, r: r.append({"operation": "task.cancel"}), {"K12"}),
    (lambda f, r: r.insert(2, {"operation": "task.submit"}), {"K12"}),
    (lambda f, r: r[1].update(outcome="pending", task_id=None), {"K12"}),
])
def test_completion_wrong_boundary_or_duplicate_execution_fails(change, broken):
    module = harness()
    facts, requests = completion_facts(module), copy.deepcopy(COMPLETION_REQUESTS)
    change(facts, requests)
    assert completion_failing(module, facts, requests) == broken


@pytest.mark.parametrize("change", [
    lambda s, o: s.update(signal_sent=False),
    lambda s, o: s.update(node_alive_after=True),
    lambda s, o: o["hub"].update(hub_serves=["B hub serve", "B hub serve (restarted)"]),
    lambda s, o: o["survivors"].update({"B runtime api": False}),
    lambda s, o: o["survivors"].pop("B node run"),
    lambda s, o: o["reads"].__setitem__(0, {**DEAD_READ, "hub_reported_online": True}),
    lambda s, o: o["direct_task"].update(state="succeeded"),
    lambda s, o: o["files"].update(release_flag=True),
    lambda s, o: o.pop("execution"),
    lambda s, o: o.clear(),
])
def test_the_release_gate_refuses_an_unconfirmed_outage(change):
    """The scenario writes the release flag only if ``hub_outage_confirmed`` holds (also judged as K4)."""
    module = harness()
    facts = completion_facts(module)
    assert module.hub_outage_confirmed(facts["hub_stop"], facts["outage"], PROGRAM, WORKER) is True
    change(facts["hub_stop"], facts["outage"])
    assert module.hub_outage_confirmed(facts["hub_stop"], facts["outage"], PROGRAM, WORKER) is False


def test_a_dead_hub_read_is_classified_unreachable(tmp_path):
    """Against a real closed loopback port: the exact read is refused because the Hub cannot be reached, neither
    health check answers, and the port refuses connections -- the only refusal K4/K7 accept."""
    pytest.importorskip("psutil")
    module = harness()
    from suan.desktop_bridge.hub import HubClient
    port = module.off.free_port()  # bound and released at once: nothing listens there now
    hub = HubClient(f"http://127.0.0.1:{port}", "abcdefghijklmnopqrstu", timeout=2)
    backend = module.dis.budgeted_hub_backend()("hub:dead", hub, "n" * 32, wait=2)
    side = module.off.Side("B", backend, None, tmp_path, [])
    read = module.hub_down_read(side, TASK, port)
    assert read == DEAD_READ and module.hub_down_refusal(read)


def test_an_extra_or_unknown_artifact_is_refused_before_any_download():
    module = harness()
    fixture = copy.deepcopy(module.off.EXPECTED_ARTIFACTS)
    assert module.dis.fixture_listing(fixture) == fixture
    for listing in (fixture + [{"path": "extra.txt", "size": 1, "sha256": "0" * 64, "media_type": "text/plain"}],
                    [dict(fixture[0], path="../out.txt")], []):
        with pytest.raises(module.off.HarnessError):
            module.dis.fixture_listing(listing)


def test_the_count_only_driver_holds_nothing(tmp_path):
    namespace, agent_class, client_class = driver_namespace(), type("A", (Agent,), {}), type("C", (Client,), {})
    module = harness()
    namespace["install"](agent_class, client_class, tmp_path, float(str(module.COUNT_ONLY_GATE)))
    agent = agent_class(tmp_path)  # connected (_send is set) and no release file: a held reply would wait
    started = time.monotonic()
    assert agent.execute({"id": "x" * 32, "kind": "task.submit"}) == {"id": "task-1"}
    assert time.monotonic() - started < 0.5
    released = [json.loads(line) for line in (tmp_path / "stages.jsonl").read_text(encoding="utf-8").splitlines()][-1]
    assert released["stage"] == "released" and released["release_seen"] is False and released["send_none"] is False
    asyncio.run(agent._perform({"id": "x" * 32, "kind": "task.submit"}, None))
    finished = json.loads((tmp_path / "stages.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert finished["stage"] == "first_perform_finished" and finished["send_none"] is False


class SecondCallRaises:
    """A RuntimeClient stand-in whose second submit (same key) raises after the driver saw the call."""

    def __init__(self):
        self.calls = 0

    def submit(self, spec, idempotency_key=None):
        self.calls += 1
        if self.calls > 1:
            raise ConnectionError("manufactured second-call failure")
        return {"id": TASK}


def test_a_second_runtime_submit_that_raises_is_counted_at_its_entry(tmp_path):
    """The real driver text, count-only: a second same-key RuntimeClient.submit raises. The success stage alone
    still shows one call (the old evidence), but the entry stages show two, and K1/K11 fail."""
    module, namespace = harness(), driver_namespace()
    agent_class, client_class = type("A", (Agent,), {}), type("C", (SecondCallRaises,), {})
    namespace["install"](agent_class, client_class, tmp_path, float(str(module.COUNT_ONLY_GATE)))
    client = client_class()
    assert client.submit({}, SUBMIT_ACTION) == {"id": TASK}
    with pytest.raises(ConnectionError):
        client.submit({}, SUBMIT_ACTION)
    snapshot = module.stage_snapshot(module.read_stages(tmp_path))
    assert snapshot["runtime_submits"] == completion_stages()["runtime_submits"]  # one success: looks like one call
    assert snapshot["runtime_submit_calls"] == [{"stage": "runtime_submit_called", "call": n, "key": SUBMIT_ACTION}
                                                for n in (1, 2)] and snapshot["malformed"] == 0
    facts = completion_facts(module)
    seen = {k: snapshot[k] for k in ("runtime_submit_calls", "runtime_submits", "malformed")}
    facts["final"]["stages"].update(copy.deepcopy(seen))
    assert completion_failing(module, facts) == {"K11"}
    facts["submit"]["stages"].update(copy.deepcopy(seen))
    assert completion_failing(module, facts) == {"K1", "K11"}


def test_the_lost_result_driver_stages_no_submit_entry(tmp_path):
    """With a non-zero hold (lost-result) the driver's stages stay as before: only the successful return."""
    namespace, agent_class, client_class = driver_namespace(), type("A", (Agent,), {}), type("C", (Client,), {})
    namespace["install"](agent_class, client_class, tmp_path, 5)
    assert client_class().submit({}, "k") == {"id": "task-1"}
    assert stage_names(tmp_path) == ["runtime_submit"]


def test_a_malformed_stage_line_is_counted_not_filtered(tmp_path):
    """Reject invalid JSON, invalid stage objects and booleans used as call numbers."""
    module = harness()
    good = completion_stages()
    lines = [json.dumps({**s, "t": 1.0}) for s in good["executes"] + good["runtime_submit_calls"]
             + good["runtime_submits"]]
    malformed = ['{"stage": "runtime_submit_called", "call": 2', "[1]"] + [
        json.dumps({"stage": "returned", "t": 1.0}),
        json.dumps({"stage": "held", "t": 1.0}),
        json.dumps({**good["runtime_submit_calls"][0], "call": True, "t": 1.0}),
    ]
    (tmp_path / "stages.jsonl").write_text("\n".join(lines + malformed) + "\n", encoding="utf-8")
    snapshot = module.stage_snapshot(module.read_stages(tmp_path))
    assert {k: v for k, v in snapshot.items() if k != "malformed"} == {k: v for k, v in good.items()
                                                                        if k != "malformed"}
    assert snapshot["malformed"] == len(malformed)
    facts = completion_facts(module)
    facts["final"]["stages"] = snapshot
    assert completion_failing(module, facts) == {"K11"}


class RecordBackend:
    """Returns one fixed Hub action record through the same ``call(hub.action, id)`` path the harness uses."""

    def __init__(self, record):
        self.hub = type("Hub", (), {"action": lambda _, identity: copy.deepcopy(record)})()

    def call(self, function, *args):
        return function(*args)


NODE, WORKSPACE = "n" * 32, "w" * 16


def submit_record(**request):
    base = {"id": SUBMIT_ACTION, "node_id": NODE, "kind": "task.submit",
            "payload": {"template": "parity-release", "spec": {"workspace_id": WORKSPACE, "name": "parity-release"}}}
    return {"id": SUBMIT_ACTION, "state": "succeeded", "result": {"id": TASK}, "request": {**base, **request}}


def test_the_request_digest_comes_only_from_a_present_bound_request():
    module = harness()
    bound = module.completion_action(RecordBackend(submit_record()), SUBMIT_ACTION, NODE, WORKSPACE)
    assert module.request_bound(bound) and bound["request_sha256"] == module.digest(submit_record()["request"])
    assert "request" not in bound  # only the digest leaves the harness
    for wrong in ({"id": "o" * 32}, {"node_id": "o" * 32}, {"kind": "task.cancel"},
                  {"payload": {"template": "parity-release", "spec": {"workspace_id": "other"}}}):
        record = module.completion_action(RecordBackend(submit_record(**wrong)), SUBMIT_ACTION, NODE, WORKSPACE)
        assert record["request_present"] is True and not module.request_bound(record)


def test_a_request_missing_before_and_after_fails_k1_and_k9():
    """The old digest was taken of JSON null when the request was missing, so a request missing both before and
    after compared equal. Now the record says the request is absent, has no digest, and K1/K9 fail."""
    module = harness()
    record = submit_record()
    del record["request"]
    missing = module.completion_action(RecordBackend(record), SUBMIT_ACTION, NODE, WORKSPACE)
    assert module.public_action(RecordBackend(record), SUBMIT_ACTION)["request_sha256"] == module.digest(None)
    assert missing["request_present"] is False and missing["request_sha256"] is None
    facts = completion_facts(module)
    facts["submit"]["action_before_fault"] = dict(missing)
    facts["recovered"].update(action_after=dict(missing), request_unchanged=True)  # equal, and claimed unchanged
    assert completion_failing(module, facts) == {"K1", "K9"}


def fake_completion(module, driver=lambda d: None):
    def scenario(owned, env, facts, log, clients):
        facts.update(completion_facts(module))
        driver(facts["driver"])
        log.extend(copy.deepcopy(COMPLETION_REQUESTS))
    return scenario


@pytest.mark.parametrize("change, ok", [(lambda d: None, True), (lambda d: d.update(launch_sha256="0" * 64), False)])
def test_the_completion_run_gate_requires_the_driver_proof(tmp_path, monkeypatch, change, ok):
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "scenario_completion", fake_completion(module, change))
    monkeypatch.setattr(module, "scenario", lambda *args: pytest.fail("the lost-result scenario ran"))
    passed, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30,
                                  scenario_name="hub-offline-completion")
    checks = load(tmp_path / "evidence", "assertions.json")
    assert error is None and checks["cleanup_ok"] and passed is ok and checks["ok"] is ok
    assert [c["id"].split()[0] for c in checks["assertions"] if c["status"] == "fail"] == ([] if ok else ["K0"])
    assert load(tmp_path / "evidence", "run-manifest.json")["scenario"] == "hub-offline-completion"


def test_the_default_scenario_is_still_lost_result(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "scenario", fake_scenario(module))
    monkeypatch.setattr(module, "scenario_completion", lambda *args: pytest.fail("the completion scenario ran"))
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    assert ok is True and error is None
    assert "scenario" not in load(tmp_path / "evidence", "run-manifest.json")
    assert [c["id"].split()[0] for c in load(tmp_path / "evidence", "assertions.json")["assertions"]] == \
        [f"H{i}" for i in range(11)]


def test_an_unknown_scenario_is_refused(tmp_path):
    module = harness()
    with pytest.raises(ValueError):
        module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", scenario_name="hub-restart-other")
    with pytest.raises(SystemExit) as exited:
        module.main(["--mode", "source", "--scenario", "other", "--evidence-dir", str(tmp_path / "e")])
    assert exited.value.code == 2 and not (tmp_path / "evidence").exists()
