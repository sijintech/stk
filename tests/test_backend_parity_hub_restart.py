"""D1 Hub-restart slice (examples/backend_parity/hub_restart.py).

One real run: the Hub is SIGKILLed after the Runtime accepted the one submission (its program runs) and before
the Hub recorded the result; the same Hub restarts and the original queued action is delivered again. Plus
controlled counterexamples: no accepted-before-loss proof, a wrong fault boundary (the first reply not
dropped), a premature or non-SIGKILL Hub exit, a second start, a changed action or worker identity, a
re-pairing, a cleanup failure and a spent or late budget can never pass. The test driver's gate is checked on
its own as well.
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
