"""D1 node-disconnect slice (examples/backend_parity/disconnect.py).

One real run: a Hub, a Runtime and an outbound NodeAgent on loopback; the node is killed while its task
runs, the same node profile reconnects, and the original task is observed and cancelled. Plus focused
counterexamples: an offline read taken as a task failure or not-found, a resubmission, a second start, a
re-paired node or an unanswered reconnect read can never pass. Budget, cleanup, origin and error-export
behaviour is the shared offline.py code, tested in test_backend_parity.py.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "backend_parity" / "disconnect.py"
OFFLINE = ROOT / "examples" / "backend_parity" / "offline.py"
EVIDENCE_FILES = ("run-manifest.json", "requests.jsonl", "phases.json", "assertions.json", "resources.json")

pytestmark = pytest.mark.server


def harness():
    spec = importlib.util.spec_from_file_location("backend_parity_disconnect", SCRIPT)
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
def test_node_disconnect_keeps_the_task_and_reconnects_to_it(tmp_path):
    for name in ("fastapi", "uvicorn", "httpx", "psutil"):
        pytest.importorskip(name)
    evidence = tmp_path / "evidence"
    started = time.monotonic()
    result = subprocess.run([sys.executable, str(SCRIPT), "--mode", "source", "--deadline", "170",
                             "--evidence-dir", str(evidence), "--work-root", str(tmp_path)],
                            capture_output=True, text=True, env=child_env(), cwd=tmp_path, timeout=200)
    assert time.monotonic() - started < 180
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    checks = load(evidence, "assertions.json")
    assert result.returncode == 0, (summary, checks)
    assert summary["ok"] and checks["ok"] and checks["cleanup_ok"] and checks["within_deadline"]
    assert len(checks["assertions"]) == 10 and {c["status"] for c in checks["assertions"]} == {"pass"}

    phases = load(evidence, "phases.json")
    program, worker = phases["baseline"]["execution"]["program"], phases["baseline"]["execution"]["worker"]
    assert phases["node_stop"] == {"identity_valid": True, "running_before_kill": True, "alive_before_kill": True,
                                   "signal_sent": True, "exit_code": -9, "reaped": True, "killed_by_sigkill": True,
                                   "node_alive_after": False}
    assert phases["cancel"]["original_program_exited"] and phases["cancel"]["original_worker_exited"]
    reads = phases["offline"]["reads"]
    assert [r["outcome"] for r in reads] == ["refused"] * 3 and {r["code"] for r in reads} == {"unavailable"}
    assert reads[-1]["hub_reported_online"] is False  # read after the Hub itself reported the node offline
    for phase in ("offline", "reconnect"):
        execution = phases[phase]["execution"]
        assert execution["program"] == program and execution["worker"] == worker
        assert execution["program_alive"] and execution["worker_alive"]
    assert phases["cancel"]["seconds_since_submit"] < 100  # cancelled well before the program's own 120 s end
    assert phases["actions"]["final"] == ["task.cancel", "task.submit", "workspace.create"]

    requests = [json.loads(line) for line in (evidence / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["operation"] for r in requests] == ["workspace.create", "task.submit", "task.cancel"]
    assert requests[1]["task_id"] == requests[2]["task_id"]

    manifest = load(evidence, "run-manifest.json")
    origins = manifest["module_origins"]
    assert origins["consistent"] and origins["services_base"] == "this source tree"
    assert origins["disconnect_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert origins["offline_helper_sha256"] == hashlib.sha256(OFFLINE.read_bytes()).hexdigest()
    assert "schema" not in manifest and manifest["within_deadline"] and manifest["scenario_seconds"] <= 170

    resources = load(evidence, "resources.json")
    assert [p["label"] for p in resources["processes"]] == ["B runtime api", "B runtime supervisor", "B hub serve",
                                                           "B node run", "B node run (restarted)"]
    assert resources["leftover_pids_after_cleanup"] == [] and resources["removed_work_dir"] is True
    text = "".join((evidence / name).read_text(encoding="utf-8") for name in EVIDENCE_FILES) + result.stdout
    for forbidden in ("token", "Bearer", str(Path.home()), str(tmp_path)):
        assert forbidden not in text
    assert not any(tmp_path.glob("stk-disconnect-*"))


# --- counterexamples on the assertions --------------------------------------------------------------------


PROGRAM = {"pid": 4194301, "create_time": 1.0}
WORKER = {"pid": 4194299, "create_time": 1.0}
STOPPED = {"identity_valid": True, "running_before_kill": True, "alive_before_kill": True, "signal_sent": True,
           "exit_code": -9, "reaped": True, "killed_by_sigkill": True, "node_alive_after": False}


def running(program=PROGRAM, worker=WORKER):
    return {"run_directories": 1, "run_dir_is_task": True, "program": dict(program), "worker": dict(worker),
            "program_alive": True, "worker_alive": True, "start_markers": 1, "marker_pid_is_program": True}


def passing_facts(module):
    refused = {"outcome": "refused", "code": "unavailable"}
    return {
        "baseline": {"state": "running", "ready": True, "execution": running()},
        "node_stop": dict(STOPPED),
        "offline": {"observed": True, "seconds_to_offline": 18.0,
                    "reads": [dict(refused, hub_reported_online=True), dict(refused, hub_reported_online=False)],
                    "services_alive": {"B hub serve": True, "B runtime api": True, "B runtime supervisor": True},
                    "direct_task": {"same_task": True, "state": "running"}, "execution": running()},
        "reconnect": {"same_node_device": True, "node_devices": 1,
                      "live_task": {"same_task": True, "state": "running"}, "execution": running()},
        "cancel": {"seconds_since_submit": 20.0, "state": "cancelled", "cancel_requested": True,
                   "direct_state": "cancelled", "same_program": True, "same_worker": True,
                   "original_program_exited": True, "original_worker_exited": True,
                   "runs": [dict(module.off.EXPECTED_RUN)],
                   "tasks_in_workspace": 1},
        "actions": {"before": ["task.submit", "workspace.create"], "offline": ["task.submit", "workspace.create"],
                    "reconnect": ["task.submit", "workspace.create"],
                    "final": ["task.cancel", "task.submit", "workspace.create"], "offline_unchanged": True,
                    "reconnect_unchanged": True, "before_kept": True, "added_by_cancel": ["task.cancel"]},
    }


REQUESTS = [{"operation": "workspace.create"}, {"operation": "task.submit"}, {"operation": "task.cancel"}]


def failing(module, facts, requests=REQUESTS):
    return {item["id"].split()[0] for item in module.assertions(facts, requests) if item["status"] == "fail"}


def test_baseline_facts_pass():
    module = harness()
    assert failing(module, passing_facts(module)) == set()


def test_missing_facts_never_pass():
    module = harness()
    assert failing(module, {}, []) == {f"D{i}" for i in range(1, 11)}


@pytest.mark.parametrize("read", [
    {"outcome": "answered", "same_task": True, "state": "failed"},  # the offline node's task taken as failed
    {"outcome": "answered", "same_task": True, "state": "running"},  # a stale state presented as live
    {"outcome": "refused", "code": "not_found"},  # an offline node's task taken as missing
    {"outcome": "refused", "code": "remote_error"},
])
def test_offline_read_taken_as_a_state_or_missing_fails(read):
    module = harness()
    facts = passing_facts(module)
    facts["offline"]["reads"][1] = dict(read, hub_reported_online=False)  # the Hub did report it offline
    assert failing(module, facts) == {"D4"}


def test_too_few_offline_reads_fail():
    module = harness()
    facts = passing_facts(module)
    facts["offline"]["reads"] = facts["offline"]["reads"][:1]  # only the read before the Hub noticed
    assert failing(module, facts) == {"D3", "D4"}
    facts["offline"]["reads"] = []
    assert failing(module, facts) == {"D3", "D4"}


def test_offline_never_seen_by_the_hub_fails():
    """Refused reads alone are not offline proof: one must be made while the Hub itself reports the node offline."""
    module = harness()
    facts = passing_facts(module)
    for read in facts["offline"]["reads"]:
        read["hub_reported_online"] = True
    assert failing(module, facts) == {"D3"}


@pytest.mark.parametrize("change, broken", [
    # A resubmission: a new Hub action during the outage or reconnect, a second task, a second request.
    (lambda f, r: f["actions"].update(reconnect_unchanged=False), {"D6"}),
    (lambda f, r: f["actions"].update(offline_unchanged=False), {"D6"}),
    (lambda f, r: f["cancel"].update(tasks_in_workspace=2), {"D8"}),
    (lambda f, r: f["actions"].update(added_by_cancel=["task.cancel", "task.submit"]), {"D9"}),
    (lambda f, r: r.insert(2, {"operation": "task.submit"}), {"D10"}),
    # A second start: two markers, another program process, a second run directory.
    (lambda f, r: f["offline"]["execution"].update(start_markers=2), {"D5"}),
    (lambda f, r: f["reconnect"]["execution"].update(program={"pid": 4194300, "create_time": 1.0}), {"D7"}),
    (lambda f, r: f["reconnect"]["execution"].update(run_directories=2), {"D7"}),
    (lambda f, r: f["cancel"].update(same_program=False), {"D8"}),
    # The program stopped during the outage, or another service went down with the node.
    (lambda f, r: f["offline"]["execution"].update(program_alive=False), {"D5"}),
    (lambda f, r: f["offline"]["services_alive"].update({"B runtime supervisor": False}), {"D2"}),
    (lambda f, r: f["node_stop"].update(node_alive_after=True), {"D2"}),
    # The node was not stopped by this scenario's SIGKILL: a clean exit, a crash, or already gone / unknown.
    (lambda f, r: f["node_stop"].update(exit_code=0, killed_by_sigkill=False), {"D2"}),
    (lambda f, r: f["node_stop"].update(exit_code=1, killed_by_sigkill=False), {"D2"}),
    (lambda f, r: f["node_stop"].update(running_before_kill=False, alive_before_kill=False, signal_sent=False),
     {"D2"}),
    (lambda f, r: f["node_stop"].update(identity_valid=False, alive_before_kill=False, signal_sent=False,
                                        node_alive_after=None), {"D2"}),
    (lambda f, r: f["node_stop"].update(signal_sent=False), {"D2"}),
    # The worker metadata was replaced: another worker recorded during the outage or after the reconnect.
    (lambda f, r: f["offline"]["execution"].update(worker={"pid": 4194298, "create_time": 1.0}), {"D5"}),
    (lambda f, r: f["reconnect"]["execution"].update(worker={"pid": 4194298, "create_time": 1.0}), {"D7"}),
    (lambda f, r: f["baseline"]["execution"].update(worker=None), {"D1", "D5", "D7"}),
    # The original worker or program outlived the cancel (only a later sweep would stop it).
    (lambda f, r: f["cancel"].update(original_worker_exited=False), {"D8"}),
    (lambda f, r: f["cancel"].update(original_program_exited=False), {"D8"}),
    (lambda f, r: f["cancel"].update(same_worker=False), {"D8"}),
    # A re-paired or different node, or a reconnect read of another task.
    (lambda f, r: f["reconnect"].update(same_node_device=False), {"D7"}),
    (lambda f, r: f["reconnect"].update(node_devices=2), {"D7"}),
    (lambda f, r: f["reconnect"].update(live_task={"same_task": False, "state": "running"}), {"D7"}),
    # The task finished on its own instead of by the cancel.
    (lambda f, r: f["cancel"].update(state="succeeded", cancel_requested=False), {"D8"}),
])
def test_resubmission_second_start_or_wrong_node_fails(change, broken):
    module = harness()
    facts, requests = passing_facts(module), copy.deepcopy(REQUESTS)
    change(facts, requests)
    assert failing(module, facts, requests) == broken


def fake_run(root, workspace, task_id, marker, alive_pid=None):
    run = root / workspace / "runs" / task_id
    (run / "work").mkdir(parents=True)
    (run / "parity-start.marker").write_text(marker, encoding="ascii")
    pid = alive_pid or PROGRAM["pid"]
    record = {"pid": pid, "create_time": 1.0}
    if alive_pid:
        import psutil
        record["create_time"] = psutil.Process(alive_pid).create_time()
    for name in ("program.json", "worker.json"):
        (run / name).write_text(json.dumps(record), encoding="utf-8")
    return run


def test_running_execution_reads_markers_strictly(tmp_path):
    """The running-phase observation needs live, valid identities and exactly one start with the program PID."""
    module = harness()
    me = os.getpid()
    fake_run(tmp_path, "w", "t1", f"start {me}\n", alive_pid=me)
    seen = module.running_execution(tmp_path, "w", "t1")
    assert seen["program_alive"] and seen["worker_alive"] and seen["start_markers"] == 1 and seen["marker_pid_is_program"]
    for index, marker in enumerate((f"start {me}\nstart {me}\n", "start garbage\n", f"start {me + 1}\n", "")):
        root = tmp_path / f"case-{index}"
        fake_run(root, "w", "t1", marker, alive_pid=me)
        seen = module.running_execution(root, "w", "t1")
        assert not (seen["start_markers"] == 1 and seen["marker_pid_is_program"])
    fake_run(tmp_path, "w", "t2", f"start {me}\n", alive_pid=me)  # a second run directory in the workspace
    assert module.running_execution(tmp_path, "w", "t1")["run_directories"] == 2


def test_duplicate_marker_after_the_cancel_fails(tmp_path):
    module = harness()
    fake_run(tmp_path, "w", "t1", f"start {PROGRAM['pid']}\nstart {PROGRAM['pid']}\n")
    (tmp_path / "w" / "runs" / "t1" / "finished.json").write_text("{}", encoding="utf-8")
    runs = module.off.executions(type("S", (), {"workspace_root": tmp_path})(), "w", timeout=0)
    facts = passing_facts(module)
    facts["cancel"]["runs"] = runs
    assert runs[0]["start_markers"] == 2 and failing(module, facts) == {"D8"}


# --- reads and waits never write --------------------------------------------------------------------------


class Node:
    """A Hub side whose node never answers; any write is recorded (and must not happen)."""
    name = "stub"

    def __init__(self, online=True, codes=("unavailable",)):
        self.online, self.codes, self.writes = online, list(codes), []
        self.backend = self

    def health(self):
        return {"online": self.online}

    def task(self, task_id):
        from suan.desktop_bridge.protocol import BridgeError
        raise BridgeError(self.codes[0] if len(self.codes) == 1 else self.codes.pop(0), "manufactured")

    def submit(self, *args, **kwargs):  # pragma: no cover - the assertion is that it never runs
        self.writes.append("submit")

    def cancel(self, *args, **kwargs):  # pragma: no cover
        self.writes.append("cancel")


def test_classify_read_reports_refusals_without_a_state():
    module = harness()
    assert module.classify_read(Node(online=False), "t") == {"outcome": "refused", "code": "unavailable",
                                                            "hub_reported_online": False}
    read = module.classify_read(Node(codes=("not_found",)), "t")
    assert read["code"] == "not_found" and not module.offline_read_ok(read)


def test_unanswered_reconnect_read_is_unknown_and_writes_nothing(monkeypatch):
    module = harness()
    side = Node()
    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 0.6)
    with pytest.raises(module.off.Unknown):
        module.observe_live(side, "t", 30)
    assert side.writes == []


def test_a_node_that_never_goes_offline_is_unknown(monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 0.6)
    with pytest.raises(module.off.Unknown, match="offline"):
        module.wait_offline(Node(online=True), 40)


def test_an_unreachable_hub_is_not_offline_proof(monkeypatch):
    module = harness()
    from suan.desktop_bridge.protocol import BridgeError

    class Unreachable:
        def health(self):
            raise BridgeError("unavailable", "manufactured")

    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 0.6)
    with pytest.raises(module.off.Unknown):
        module.wait_offline(Unreachable(), 40)


# --- entry point ---------------------------------------------------------------------------------------------


def test_earlier_evidence_is_never_overwritten(tmp_path):
    module = harness()
    earlier = tmp_path / "trial"
    earlier.mkdir()
    (earlier / "assertions.json").write_text('{"ok": false}', encoding="utf-8")
    assert module.main(["--mode", "source", "--evidence-dir", str(earlier), "--work-root", str(tmp_path)]) == 2
    assert (earlier / "assertions.json").read_text(encoding="utf-8") == '{"ok": false}'
    assert not any(tmp_path.glob("stk-disconnect-*"))


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
    assert load(evidence, "assertions.json")["assertions"] == []  # no pass without a scenario
    assert not any(tmp_path.glob("stk-disconnect-*"))


# --- the fault injection and the original identities, with real processes ---------------------------------


def sleeper(seconds=30, code=0):
    return subprocess.Popen([sys.executable, "-c", f"import sys, time; time.sleep({seconds}); sys.exit({code})"],
                            start_new_session=True)


def d2_with(module, record):
    facts = passing_facts(module)
    facts["node_stop"] = record
    return "D2" in failing(module, facts)


def test_intentional_sigkill_of_the_live_node_passes_d2():
    module = harness()
    process = sleeper()
    identity = module.identity_of(process.pid)
    record = module.stop_node(process, identity)
    assert record == {"identity_valid": True, "running_before_kill": True, "alive_before_kill": True,
                      "signal_sent": True, "exit_code": -9, "reaped": True, "killed_by_sigkill": True,
                      "node_alive_after": False}
    assert not d2_with(module, record)


@pytest.mark.parametrize("code", [0, 1])
def test_a_node_that_already_exited_or_crashed_fails_d2(code):
    """A clean exit (0) or a crash (1) before the intentional stop is not this scenario's fault injection."""
    module = harness()
    process = sleeper(0.2, code)
    identity = module.identity_of(process.pid)
    process.wait(10)
    record = module.stop_node(process, identity)
    assert record["exit_code"] == code and not record["alive_before_kill"] and not record["signal_sent"]
    assert d2_with(module, record)


def test_a_missing_or_foreign_node_identity_fails_d2():
    module = harness()
    for identity in (None, {"pid": 1, "create_time": 1.0}, {"pid": "x", "create_time": 1.0}):
        process = sleeper()
        try:
            record = module.stop_node(process, identity)
            assert not record["signal_sent"] and d2_with(module, record)
        finally:
            process.kill()
            process.wait(10)


def test_replaced_worker_metadata_and_a_surviving_original_worker_fail(tmp_path):
    """Original worker A stays alive while worker.json is rewritten to a worker B that has exited (with the
    program). The frozen identity catches the swap during the outage, and the cancel check sees A alive."""
    module = harness()
    me = os.getpid()
    original = sleeper()  # worker A
    replacement = sleeper(0)  # worker B, which exits
    try:
        worker_a = module.identity_of(original.pid)
        worker_b = module.identity_of(replacement.pid) or {"pid": replacement.pid, "create_time": 2.0}
        replacement.wait(10)
        run = fake_run(tmp_path, "w", "t1", f"start {me}\n", alive_pid=me)
        (run / "worker.json").write_text(json.dumps(worker_a), encoding="utf-8")
        baseline = module.running_execution(tmp_path, "w", "t1")
        assert baseline["worker"] == worker_a and baseline["worker_alive"]
        (run / "worker.json").write_text(json.dumps(worker_b), encoding="utf-8")
        swapped = module.running_execution(tmp_path, "w", "t1")
        assert swapped["worker"] == worker_b and not swapped["worker_alive"]

        facts = passing_facts(module)
        program = baseline["program"]
        facts["baseline"]["execution"] = baseline
        facts["offline"]["execution"] = swapped
        facts["reconnect"]["execution"] = dict(swapped, worker_alive=True)  # even if B looked alive, B is not A
        facts["cancel"]["original_worker_exited"] = module.exited(worker_a, 0)
        assert facts["cancel"]["original_worker_exited"] is False and module.exited(program, 0) is False
        assert failing(module, facts) >= {"D5", "D7", "D8"}
        assert module.exited(worker_b, 0) is True and module.exited(None, 0) is False
    finally:
        original.kill()
        original.wait(10)
