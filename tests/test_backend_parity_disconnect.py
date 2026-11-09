"""D1 node-disconnect slice (examples/backend_parity/disconnect.py).

One real run: a Hub, a Runtime and an outbound NodeAgent on loopback; the node is killed while its task
runs, the same node profile reconnects, and the original task is observed and cancelled. Plus focused
counterexamples: an offline read taken as a task failure or not-found, a resubmission, a second start, a
re-paired node or an unanswered reconnect read can never pass. Budget, cleanup, origin and error-export
behaviour is the shared offline.py code, tested in test_backend_parity.py.

The X7 offline-completion scenario (``--scenario offline-completion``) has its own real run and
counterexamples: a task that finished before the disconnect, a cached or completed state served as live
while the node is offline, a duplicate start or submission, and any cancel can never pass. Also: a timeout or
unknown read is never taken as the node-offline refusal; an answered queued before succeeded after the
reconnect fails (the cancel scenario's shared reading would skip it); and a listing other than the fixed
out.txt fixture is refused before any content is read.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import select
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


# --- X7: the task completes while the node is offline (--scenario offline-completion) ------------------------


@pytest.mark.skipif(platform.system() != "Linux", reason="the Runtime and control service are Linux-only")
def test_task_completes_while_the_node_is_offline_and_is_read_after_the_reconnect(tmp_path):
    for name in ("fastapi", "uvicorn", "httpx", "psutil"):
        pytest.importorskip(name)
    module = harness()
    evidence = tmp_path / "evidence"
    started = time.monotonic()
    result = subprocess.run([sys.executable, str(SCRIPT), "--mode", "source", "--deadline", "170",
                             "--scenario", "offline-completion", "--evidence-dir", str(evidence),
                             "--work-root", str(tmp_path)],
                            capture_output=True, text=True, env=child_env(), cwd=tmp_path, timeout=200)
    assert time.monotonic() - started < 180
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    checks = load(evidence, "assertions.json")
    assert result.returncode == 0, (summary, checks)
    assert summary["ok"] and checks["ok"] and checks["cleanup_ok"] and checks["within_deadline"]
    assert [c["id"].split()[0] for c in checks["assertions"]] == [f"C{i}" for i in range(1, 13)]
    assert {c["status"] for c in checks["assertions"]} == {"pass"}

    phases = load(evidence, "phases.json")
    assert phases["node_stop"]["killed_by_sigkill"] and phases["node_stop"]["node_alive_after"] is False
    assert phases["baseline"]["snapshot_running"] is True
    assert phases["offline"]["direct_task"]["state"] == "running"
    assert phases["offline"]["files"] == {"release_flag": False, "finished_record": False, "output_file": False}
    done = phases["completed_offline"]
    assert done["released_after_offline_observed"] and done["node_runs"] == ["B node run"]
    assert done["direct_task"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
    assert done["original_program_exited"] and done["original_worker_exited"]
    # Strict: the Hub answered offline right before and after each read, and refused it because the node is offline.
    assert phases["offline"]["reads"] == [NODE_OFFLINE] * 2 and done["reads"] == [NODE_OFFLINE] * 2
    assert phases["offline"]["read_before_offline_report"]["outcome"] in ("refused", "unknown")
    assert done["snapshot_state"] == "running"  # the cache was stale, and it was not served
    assert phases["reconnect"]["first_live"] == {"same_task": True, "state": "succeeded", "cancel_requested": False}
    outputs = phases["outputs"]
    assert outputs["stdout_sha256"] == hashlib.sha256(module.RELEASED_STDOUT).hexdigest()
    assert outputs["artifacts"] == module.off.EXPECTED_ARTIFACTS
    assert outputs["downloads"] == {"out.txt": hashlib.sha256(module.off.EXPECTED_OUT).hexdigest()}
    assert phases["final"]["runs"] == [module.off.EXPECTED_RUN] and phases["final"]["tasks_in_workspace"] == 1
    assert phases["actions"]["final"] == ["task.submit", "workspace.create"]

    requests = [json.loads(line) for line in (evidence / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["operation"] for r in requests] == ["workspace.create", "task.submit"]
    assert requests[1]["template"] == "parity-release"

    manifest = load(evidence, "run-manifest.json")
    origins = manifest["module_origins"]
    assert origins["consistent"] and origins["services_base"] == "this source tree"
    assert origins["disconnect_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert origins["offline_helper_sha256"] == hashlib.sha256(OFFLINE.read_bytes()).hexdigest()
    assert manifest["scenario"] == "offline-completion" and list(manifest["templates"]) == ["parity-release"]
    assert "schema" not in manifest and manifest["within_deadline"]

    resources = load(evidence, "resources.json")
    assert [p["label"] for p in resources["processes"]] == ["B runtime api", "B runtime supervisor", "B hub serve",
                                                           "B node run", "B node run (restarted)"]
    assert resources["leftover_pids_after_cleanup"] == [] and resources["removed_work_dir"] is True
    text = "".join((evidence / name).read_text(encoding="utf-8") for name in EVIDENCE_FILES) + result.stdout
    for forbidden in ("token", "Bearer", str(Path.home()), str(tmp_path), module.RELEASE_FLAG):
        assert forbidden not in text
    assert not any(tmp_path.glob("stk-disconnect-*"))


def ended(program=PROGRAM, worker=WORKER):
    return dict(running(program, worker), program_alive=False, worker_alive=False)


UNRELEASED = {"release_flag": False, "finished_record": False, "output_file": False}
SERVICES = {"B hub serve": True, "B runtime api": True, "B runtime supervisor": True}


NODE_OFFLINE = {"outcome": "refused", "code": "unavailable", "cause": "node_offline", "hub_reported_online": False,
                "hub_reported_online_after": False}  # the strict X7 offline refusal


def passing_completion_facts(module):
    out_sha = hashlib.sha256(module.off.EXPECTED_OUT).hexdigest()
    return {
        "baseline": {"state": "running", "ready": True, "execution": running(), "snapshot_running": True,
                     "files": dict(UNRELEASED)},
        "node_stop": dict(STOPPED),
        "offline": {"observed": True, "seconds_to_offline": 18.0,
                    "read_before_offline_report": dict(NODE_OFFLINE, cause="hub_node_link_closed",
                                                       hub_reported_online=True, hub_reported_online_after=True),
                    "reads": [dict(NODE_OFFLINE), dict(NODE_OFFLINE)],
                    "services_alive": dict(SERVICES), "direct_task": {"same_task": True, "state": "running"},
                    "execution": running(), "files": dict(UNRELEASED)},
        "completed_offline": {
            "released_after_offline_observed": True,
            "direct_task": {"same_task": True, "state": "succeeded", "cancel_requested": False},
            "original_program_exited": True, "original_worker_exited": True, "execution": ended(),
            "files": {"release_flag": True, "finished_record": True, "output_file": True},
            "reads": [dict(NODE_OFFLINE), dict(NODE_OFFLINE)],
            "snapshot_state": "running", "node_runs": ["B node run"], "node_exit_code": -9,
            "services_alive": dict(SERVICES)},
        "reconnect": {"same_node_device": True, "node_devices": 1,
                      "first_live": {"same_task": True, "state": "succeeded", "cancel_requested": False},
                      "unavailable_before_answer": 0,
                      "confirm": {"outcome": "answered", "same_task": True, "state": "succeeded",
                                  "hub_reported_online": True}},
        "outputs": {"stdout_sha256": hashlib.sha256(module.RELEASED_STDOUT).hexdigest(),
                    "stdout_bytes": len(module.RELEASED_STDOUT), "stdout_is_fixed": True,
                    "stdout_same_as_runtime": True, "artifacts": copy.deepcopy(module.off.EXPECTED_ARTIFACTS),
                    "artifacts_same_as_runtime": True, "downloads": {"out.txt": out_sha},
                    "downloads_are_fixed": {"out.txt": True}},
        "final": {"direct_state": "succeeded", "cancel_requested": False, "same_program": True, "same_worker": True,
                  "runs": [dict(module.off.EXPECTED_RUN)], "tasks_in_workspace": 1},
        "actions": {"before": ["task.submit", "workspace.create"], "final": ["task.submit", "workspace.create"],
                    "unchanged": {"offline": True, "completed_offline": True, "reconnect": True, "final": True}},
    }


COMPLETION_REQUESTS = [{"operation": "workspace.create"}, {"operation": "task.submit"}]


def completion_failing(module, facts, requests=COMPLETION_REQUESTS):
    return {item["id"].split()[0] for item in module.completion_assertions(facts, requests) if item["status"] == "fail"}


def test_completion_baseline_facts_pass_and_missing_facts_never_pass():
    module = harness()
    assert completion_failing(module, passing_completion_facts(module)) == set()
    assert completion_failing(module, {}, []) == {f"C{i}" for i in range(1, 13)}


@pytest.mark.parametrize("change, broken", [
    # The task finished before the disconnect (or before the release), so the outage proves nothing.
    (lambda f, r: f["baseline"].update(state="succeeded"), {"C1"}),
    (lambda f, r: f["baseline"]["files"].update(release_flag=True), {"C1"}),
    (lambda f, r: f["offline"]["direct_task"].update(state="succeeded"), {"C4"}),
    (lambda f, r: f["offline"]["files"].update(finished_record=True), {"C4"}),
    (lambda f, r: f["offline"]["files"].update(output_file=True), {"C4"}),
    (lambda f, r: f["offline"]["execution"].update(program_alive=False), {"C4"}),
    (lambda f, r: f["completed_offline"].update(released_after_offline_observed=False), {"C5"}),
    # The node came back (or another node ran) before the completion was checked.
    (lambda f, r: f["completed_offline"].update(node_runs=["B node run", "B node run (restarted)"]), {"C5"}),
    (lambda f, r: f["completed_offline"].update(node_exit_code=None), {"C5"}),
    # The task did not succeed on its own Runtime, or was cancelled.
    (lambda f, r: f["completed_offline"]["direct_task"].update(state="failed"), {"C5"}),
    (lambda f, r: f["completed_offline"]["direct_task"].update(state="cancelled", cancel_requested=True), {"C5"}),
    (lambda f, r: f["completed_offline"]["files"].update(output_file=False), {"C5"}),
    # The original processes outlived the completion (only a reconnect or the cleanup would stop them).
    (lambda f, r: f["completed_offline"].update(original_program_exited=False), {"C6"}),
    (lambda f, r: f["completed_offline"].update(original_worker_exited=False), {"C6"}),
    (lambda f, r: f["completed_offline"]["execution"].update(worker_alive=True), {"C6"}),
    # A stale or completed state served as live while the node is offline, or a vacuous cache check.
    (lambda f, r: f["offline"]["reads"].__setitem__(1, {"outcome": "answered", "same_task": True, "state": "running",
                                                         "hub_reported_online": False}), {"C3"}),
    (lambda f, r: f["completed_offline"]["reads"].__setitem__(0, {"outcome": "answered", "same_task": True,
                                                                   "state": "succeeded",
                                                                   "hub_reported_online": False}), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"].__setitem__(1, {"outcome": "answered", "same_task": True,
                                                                   "state": "running",
                                                                   "hub_reported_online": False}), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"][1].update(hub_reported_online=True), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"].__setitem__(0, {"outcome": "refused", "code": "not_found",
                                                                   "hub_reported_online": False}), {"C7"}),
    (lambda f, r: f["completed_offline"].update(reads=f["completed_offline"]["reads"][:1]), {"C7"}),
    # A timeout, an unreachable Hub or an unanswered read is not a proven node-offline refusal (C3 and C7).
    (lambda f, r: f["offline"]["reads"].__setitem__(0, {"outcome": "unknown", "hub_reported_online": False,
                                                         "hub_reported_online_after": False}), {"C3"}),
    (lambda f, r: f["offline"]["reads"][1].update(cause="timeout"), {"C3"}),
    (lambda f, r: f["offline"]["reads"][1].update(hub_reported_online_after=None), {"C3"}),
    (lambda f, r: f["offline"].update(reads=f["offline"]["reads"][:1]), {"C3"}),
    (lambda f, r: f["offline"].update(read_before_offline_report={"outcome": "answered", "same_task": True,
                                                                  "state": "running", "hub_reported_online": True}),
     {"C3"}),
    (lambda f, r: f["offline"].update(read_before_offline_report={"outcome": "refused", "code": "not_found",
                                                                  "cause": "other", "hub_reported_online": True}),
     {"C3"}),
    (lambda f, r: f["completed_offline"]["reads"].__setitem__(0, {"outcome": "unknown", "hub_reported_online": False,
                                                                   "hub_reported_online_after": False}), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"][0].update(cause="timeout"), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"][1].update(cause="hub_node_link_closed"), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"][0].update(cause="unreachable", hub_reported_online=None), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"][1].update(code="timeout"), {"C7"}),
    (lambda f, r: f["completed_offline"]["reads"][1].update(hub_reported_online_after=True), {"C7"}),
    (lambda f, r: f["completed_offline"].update(snapshot_state="succeeded"), {"C7"}),
    (lambda f, r: f["completed_offline"].update(snapshot_state=None), {"C7"}),
    (lambda f, r: f["baseline"].update(snapshot_running=False), {"C1"}),
    (lambda f, r: f["reconnect"]["first_live"].update(state="running"), {"C8"}),
    (lambda f, r: f["reconnect"]["first_live"].update(state="queued"), {"C8"}),
    (lambda f, r: f["reconnect"].pop("unavailable_before_answer"), {"C8"}),
    (lambda f, r: f["reconnect"]["confirm"].update(hub_reported_online=False), {"C8"}),
    (lambda f, r: f["reconnect"].update(same_node_device=False), {"C8"}),
    # The outputs differ from the fixed bytes or from the owned Runtime.
    (lambda f, r: f["outputs"].update(stdout_is_fixed=False), {"C9"}),
    (lambda f, r: f["outputs"].update(stdout_same_as_runtime=False), {"C9"}),
    (lambda f, r: f["outputs"].update(downloads={"out.txt": "0" * 64}), {"C10"}),
    (lambda f, r: f["outputs"].update(downloads_are_fixed={"out.txt": False}), {"C10"}),
    (lambda f, r: f["outputs"]["artifacts"].append({"path": "extra.txt", "size": 1, "sha256": "0" * 64,
                                                    "media_type": "text/plain"}), {"C10"}),
    # A duplicate start, run directory, task or submission.
    (lambda f, r: f["completed_offline"]["execution"].update(start_markers=2), {"C6"}),
    (lambda f, r: f["completed_offline"]["execution"].update(run_directories=2), {"C6"}),
    (lambda f, r: f["completed_offline"]["execution"].update(program={"pid": 4194300, "create_time": 1.0}), {"C6"}),
    (lambda f, r: f["final"]["runs"][0].update(start_markers=2), {"C11"}),
    (lambda f, r: f["final"]["runs"].append(dict(f["final"]["runs"][0])), {"C11"}),
    (lambda f, r: f["final"].update(tasks_in_workspace=2), {"C11"}),
    (lambda f, r: f["final"].update(same_program=False), {"C11"}),
    (lambda f, r: r.append({"operation": "task.submit"}), {"C12"}),
    (lambda f, r: f["actions"]["unchanged"].update(reconnect=False), {"C12"}),
    (lambda f, r: f["actions"].update(final=["task.submit", "task.submit", "workspace.create"]), {"C12"}),
    # Any cancel.
    (lambda f, r: r.append({"operation": "task.cancel"}), {"C12"}),
    (lambda f, r: f["actions"].update(final=["task.cancel", "task.submit", "workspace.create"]), {"C12"}),
    (lambda f, r: f["final"].update(direct_state="cancelled", cancel_requested=True), {"C11"}),
    (lambda f, r: f["reconnect"]["first_live"].update(cancel_requested=True), {"C8"}),
])
def test_early_completion_cached_live_duplicate_start_or_cancel_fails(change, broken):
    module = harness()
    facts, requests = passing_completion_facts(module), copy.deepcopy(COMPLETION_REQUESTS)
    change(facts, requests)
    assert completion_failing(module, facts, requests) == broken


def release_layout(root):
    work = root / "w" / "runs" / "t" / "work"
    work.mkdir(parents=True)
    return work


def launch(program, work):
    return subprocess.Popen([sys.executable, "-c", program], cwd=work, stdout=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, start_new_session=True)


def ready_line(process, timeout=20):
    readable, _, _ = select.select([process.stdout], [], [], timeout)
    assert readable, "the program printed no ready line"
    return process.stdout.readline()


def test_the_release_program_cannot_finish_until_released(tmp_path):
    """The real program text: it waits for its private flag, then writes the fixed output and exits 0."""
    module = harness()
    work = release_layout(tmp_path)
    process = launch(module.RELEASE_PROGRAM, work)
    try:
        assert ready_line(process) == "waiting 等待\n".encode("utf-8")
        time.sleep(1.0)
        assert process.poll() is None and not (work / "out.txt").exists()
        assert module.result_files(tmp_path, "w", "t") == UNRELEASED
        assert module.release(tmp_path, "w", "t") is True
        assert process.wait(15) == 0
        rest = process.stdout.read()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(10)
        process.stdout.close()
    assert "waiting 等待\n".encode("utf-8") + rest == module.RELEASED_STDOUT
    assert (work / "out.txt").read_bytes() == module.off.EXPECTED_OUT
    marker = (work.parent / module.off.START_MARKER).read_text(encoding="ascii")
    assert module.off.marker_pids(marker) == [process.pid]
    assert module.result_files(tmp_path, "w", "t") == {"release_flag": True, "finished_record": False,
                                                       "output_file": True}
    with pytest.raises(module.off.HarnessError):  # a second release is refused, never silently repeated
        module.release(tmp_path, "w", "t")


def test_a_never_released_program_fails_instead_of_succeeding(tmp_path):
    """The same program with only its own wait shortened: without the flag it exits 3 and writes no output."""
    module = harness()
    program = module.RELEASE_PROGRAM.replace("time.monotonic() + 120", "time.monotonic() + 0.5")
    assert program != module.RELEASE_PROGRAM
    work = release_layout(tmp_path)
    process = launch(program, work)
    try:
        assert process.wait(15) == 3
        output = process.stdout.read()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(10)
        process.stdout.close()
    assert output == "waiting 等待\nnever released 未释放\n".encode("utf-8")
    assert not (work / "out.txt").exists()


class StopBeforeInit(Exception):
    pass


class NoProcesses:
    """An owned-run stand-in that stops start_hub at its first command, after the template file is written."""
    resources = {"processes": [], "directories": [], "cleanup": []}

    def run(self, *args, **kwargs):
        raise StopBeforeInit

    def spawn(self, *args, **kwargs):  # pragma: no cover - never reached
        raise AssertionError("nothing may be started")


def test_the_extra_template_is_registered_only_when_asked_and_never_replaces_a_fixed_one(tmp_path):
    module = harness()
    off = module.off
    fixed = copy.deepcopy(off.TEMPLATES)
    with pytest.raises(StopBeforeInit):
        off.start_hub(NoProcesses(), tmp_path, {}, tmp_path / "runtime")
    assert json.loads((tmp_path / "templates.json").read_text(encoding="utf-8")) == fixed  # default unchanged
    with pytest.raises(StopBeforeInit):
        off.start_hub(NoProcesses(), tmp_path, {}, tmp_path / "runtime", extra_templates=module.RELEASE_TEMPLATES)
    assert json.loads((tmp_path / "templates.json").read_text(encoding="utf-8")) == {**fixed,
                                                                                    **module.RELEASE_TEMPLATES}
    (tmp_path / "templates.json").unlink()
    with pytest.raises(off.HarnessError):
        off.start_hub(NoProcesses(), tmp_path, {}, tmp_path / "runtime",
                      extra_templates={"parity-wait": module.RELEASE_TEMPLATES["parity-release"]})
    assert not (tmp_path / "templates.json").exists() and off.TEMPLATES == fixed


class Snapshot:
    def __init__(self, tasks):
        self._tasks = tasks

    def tasks(self):
        return {"tasks": self._tasks}


def test_snapshot_reads_are_exact_and_a_missing_snapshot_is_unknown(monkeypatch):
    module = harness()
    assert module.snapshot_state(Snapshot([{"id": "t", "state": "running"}, {"id": "u", "state": "failed"}]),
                                 "t") == "running"
    assert module.snapshot_state(Snapshot([{"id": "u", "state": "running"}]), "t") is None
    assert module.snapshot_state(Snapshot([{"id": "t", "state": "running"}] * 2), "t") is None
    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 0.6)
    with pytest.raises(module.off.Unknown, match="snapshot"):
        module.wait_snapshot(Snapshot([]), "t", "running", 15)


class Answers:
    """A Hub side whose exact reads give the scripted answers (dicts) or refusals (codes) in order, the last
    repeating; every read is counted and any write is recorded (and must not happen)."""
    name = "stub"

    def __init__(self, *script):
        self.script, self.reads, self.writes = list(script), 0, []
        self.backend = self

    def task(self, task_id):
        from suan.desktop_bridge.protocol import BridgeError
        self.reads += 1
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, str):
            raise BridgeError(step, "manufactured")
        return dict(step, id=task_id)

    def submit(self, *args, **kwargs):  # pragma: no cover - the assertion is that it never runs
        self.writes.append("submit")

    def cancel(self, *args, **kwargs):  # pragma: no cover
        self.writes.append("cancel")


QUEUED = {"state": "queued", "cancel_requested": False}
SUCCEEDED = {"state": "succeeded", "cancel_requested": False}


def first_live_fact(task):
    return {"same_task": task.get("id") == "t", "state": task.get("state"),
            "cancel_requested": task.get("cancel_requested")}


def test_an_answered_queued_read_before_succeeded_is_kept_and_fails_c8(monkeypatch):
    """The shared observe_live (kept for the cancel scenario) skips an answered queued; X7's first_live_read keeps
    the first answer, so a queued answer before succeeded fails C8 instead of passing."""
    module = harness()
    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 10)
    old = module.observe_live(Answers(QUEUED, SUCCEEDED), "t", 5)
    assert old["state"] == "succeeded"  # the old reading skipped the answered queued
    facts = passing_completion_facts(module)
    facts["reconnect"]["first_live"] = first_live_fact(old)
    assert completion_failing(module, facts) == set()  # ... so with it C8 would have passed

    side = Answers(QUEUED, SUCCEEDED)
    task, unavailable = module.first_live_read(side, "t", 5)
    assert task["state"] == "queued" and unavailable == 0 and side.reads == 1 and side.writes == []
    facts["reconnect"].update(first_live=first_live_fact(task), unavailable_before_answer=unavailable)
    assert completion_failing(module, facts) == {"C8"}

    side = Answers("unavailable", "unavailable", SUCCEEDED)  # only a transport non-answer is retried
    task, unavailable = module.first_live_read(side, "t", 5)
    assert task["state"] == "succeeded" and unavailable == 2 and side.reads == 3


@pytest.mark.parametrize("code", ["not_found", "remote_error", "unsupported", "unauthorized", "timeout"])
def test_a_meaningful_refusal_after_the_reconnect_fails_at_once(monkeypatch, code):
    module = harness()
    from suan.desktop_bridge.protocol import BridgeError
    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 10)
    side = Answers(code, SUCCEEDED)
    with pytest.raises(BridgeError) as refused:
        module.first_live_read(side, "t", 5)
    assert refused.value.code == code and side.reads == 1 and side.writes == []  # never retried
    assert module.off.exported_error(refused.value) == {"kind": "error", "code": code,
                                                        "message": "a backend call failed"}


def test_an_unanswered_first_live_read_is_unknown_and_writes_nothing(monkeypatch):
    module = harness()
    side = Answers("unavailable")
    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 0.6)
    with pytest.raises(module.off.Unknown):
        module.first_live_read(side, "t", 30)
    assert side.reads >= 2 and side.writes == []


@pytest.mark.parametrize("answer_delay", [5.0, 5.1])
def test_first_live_answer_at_or_after_deadline_is_unknown(monkeypatch, answer_delay):
    module = harness()
    clock = 100.0

    class LateAnswer(Answers):
        def task(self, task_id):
            nonlocal clock
            clock += answer_delay
            return super().task(task_id)

    monkeypatch.setattr(module.time, "monotonic", lambda: clock)
    monkeypatch.setattr(module.off, "DEADLINE", clock + 30)
    side = LateAnswer(SUCCEEDED)
    with pytest.raises(module.off.Unknown):
        module.first_live_read(side, "t", 5)
    assert side.reads == 1 and side.writes == []


class FakeHub:
    """The parts of HubClient that HubBackend.task and .health use: one node with exact reads, either listed
    offline or online with a scripted failure of the forwarded read."""
    url = "http://127.0.0.1:1"

    def __init__(self, online, failure=None):
        self.online, self.failure, self.forwarded = online, failure, 0

    def devices(self):
        return [{"id": "n", "role": "node", "online": self.online, "revoked": False,
                 "snapshot": {"features": ["read", "task.get"]}}]

    def policy(self):
        return {"read_kinds": ["task.get"]}

    def read(self, node_id, kind, payload):
        self.forwarded += 1
        raise self.failure


def test_only_the_products_node_offline_refusal_is_a_strict_offline_read():
    """The real HubBackend: its own refusal of a node the Hub lists offline is distinguished from the Hub's 503
    (no link yet), a 504 or HTTP timeout, and an unreachable Hub -- all of which share the code unavailable."""
    import socket
    from urllib.error import URLError
    from suan.desktop_bridge.backends import HubBackend
    from suan.desktop_bridge.hub import HubResponseError
    module = harness()

    def read(hub):
        return module.offline_read(module.off.Side("B", HubBackend("hub:test", hub, "n"), None, None, []), "t0")

    offline = FakeHub(online=False)
    assert read(offline) == NODE_OFFLINE and offline.forwarded == 0  # refused before anything is forwarded
    assert module.node_offline_refusal(read(offline))
    for failure, cause in [(HubResponseError(503, "The execution node is offline"), "hub_node_link_closed"),
                           (HubResponseError(504, "The execution node did not answer in time; retry"), "timeout"),
                           (socket.timeout("timed out"), "timeout"),
                           (URLError("refused"), "unreachable")]:
        hub = FakeHub(online=True, failure=failure)
        result = read(hub)
        assert hub.forwarded == 1 and result == {"outcome": "refused", "code": "unavailable", "cause": cause,
                                                 "hub_reported_online": True, "hub_reported_online_after": True}
        assert not module.node_offline_refusal(result)
        # Even with the Hub reporting the node offline around it, a timeout is never the node-offline refusal.
        assert not module.node_offline_refusal(dict(result, hub_reported_online=False, hub_reported_online_after=False))
    lost = read(FakeHub(online=True, failure=HubResponseError(404, "Task not found")))
    assert lost["code"] == "not_found" and lost["cause"] == "other" and not module.node_offline_refusal(lost)


@pytest.mark.parametrize("online", [{}, {"online": None}, {"online": 0}, {"online": ""}])
def test_missing_or_nonboolean_hub_state_is_not_offline_proof(online):
    from suan.desktop_bridge.backends import HubBackend
    module = harness()

    class MalformedHub(FakeHub):
        def devices(self):
            device, = super().devices()
            device.pop("online")
            return [{**device, **online}]

    hub = MalformedHub(online=False)
    side = module.off.Side("B", HubBackend("hub:test", hub, "n"), None, None, [])
    read = module.offline_read(side, "t0")
    assert read["hub_reported_online"] is None and read["hub_reported_online_after"] is None
    assert not module.node_offline_refusal(read) and hub.forwarded == 0


class Chunks:
    """A Hub side that serves out.txt and records every content read."""
    name = "stub"

    def __init__(self, module):
        self.module, self.chunk_reads = module, []
        self.backend = self

    def read_chunk(self, owner, owner_id, path, offset):
        self.chunk_reads.append(path)
        return self.module.off.EXPECTED_OUT[offset:] if path == "out.txt" else b"\x00" * 4096


def fixture_item(module, **change):
    return dict(module.off.EXPECTED_ARTIFACTS[0], **change)


@pytest.mark.parametrize("listing", [
    lambda m: [fixture_item(m, path="../stk-leak/out.txt")],  # unknown or escaping path
    lambda m: [fixture_item(m, path="secret-run-dir/out.txt")],
    lambda m: [fixture_item(m, path="OUT.TXT")],
    lambda m: [fixture_item(m), fixture_item(m, path="stk-extra.bin")],  # an extra item
    lambda m: [fixture_item(m), fixture_item(m)],  # a duplicate
    lambda m: [fixture_item(m, path="stk-extra.bin"), fixture_item(m)],
    lambda m: [],
    lambda m: [fixture_item(m, size=10 ** 12)],  # oversized
    lambda m: [fixture_item(m, size=len(m.off.EXPECTED_OUT) + 1)],
    lambda m: [fixture_item(m, size=-1)],
    lambda m: [fixture_item(m, size="14")],  # malformed sizes
    lambda m: [fixture_item(m, size=float(len(m.off.EXPECTED_OUT)))],
    lambda m: [fixture_item(m, size=None)],
    lambda m: [{key: value for key, value in fixture_item(m).items() if key != "size"}],
    lambda m: [fixture_item(m, sha256="0" * 64)],
    lambda m: [fixture_item(m, media_type="application/octet-stream")],
    lambda m: ["out.txt"],
    lambda m: {"out.txt": fixture_item(m)},
    lambda m: None,
])
def test_a_listing_other_than_the_fixed_fixture_is_refused_before_any_download(monkeypatch, listing):
    module = harness()
    side, downloads = Chunks(module), []
    monkeypatch.setattr(module.off, "download", lambda *args: downloads.append(args) or b"")
    items = listing(module)
    with pytest.raises(module.off.HarnessError) as refused:
        module.download_fixture(side, "t", items)
    assert downloads == [] and side.chunk_reads == []  # no content was read
    exported = json.dumps(module.off.exported_error(refused.value))
    assert exported == json.dumps({"kind": "error", "message": "the artifact list is not exactly the fixed out.txt "
                                                               "fixture"})
    for leaked in ("stk-leak", "secret-run-dir", "stk-extra", "OUT.TXT", "0" * 64, "octet"):
        assert leaked not in exported


def test_the_earlier_reading_downloaded_an_unknown_listed_path():
    """The reading before this gate (artifact_facts, then a download per listed path and size) read content of
    an unknown path; download_fixture refuses the same listing without reading anything."""
    module = harness()
    items = [fixture_item(module, path="../stk-leak/out.txt", size=10 ** 4)]
    side = Chunks(module)
    for item in module.off.artifact_facts(items):
        module.off.download(side, "t", item)
    assert side.chunk_reads and set(side.chunk_reads) == {"../stk-leak/out.txt"}
    side = Chunks(module)
    with pytest.raises(module.off.HarnessError):
        module.download_fixture(side, "t", items)
    assert side.chunk_reads == []


def test_the_exact_fixture_listing_is_downloaded_from_the_fixture_description():
    module = harness()
    side = Chunks(module)
    hub_item = dict(fixture_item(module), modified_at="2026-11-09T00:00:00Z")  # unrelated metadata is not exported
    listed, downloaded = module.download_fixture(side, "t", [hub_item])
    assert listed == module.off.EXPECTED_ARTIFACTS and listed is not module.off.EXPECTED_ARTIFACTS
    assert downloaded == {"out.txt": module.off.EXPECTED_OUT} and side.chunk_reads == ["out.txt"]


def test_an_unknown_scenario_is_refused(tmp_path, capsys):
    module = harness()
    with pytest.raises(SystemExit) as exited:
        module.main(["--scenario", "failover", "--evidence-dir", str(tmp_path / "e")])
    assert exited.value.code == 2 and not (tmp_path / "e").exists()
    with pytest.raises(ValueError):
        module.run(tmp_path / "e", tmp_path, scenario_name="failover")
    assert not any(tmp_path.glob("stk-disconnect-*"))
