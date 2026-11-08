"""D1 backend parity harness (examples/backend_parity/offline.py).

One real two-deployment run, plus focused false-positive checks: an unanswered wait never becomes a
resubmission or a pass, and a missing artifact, a duplicate start, a mixed import origin, a spent budget, a
failed cleanup or an exception holding a path or secret can never yield ``ok``.

The integration test starts real local processes (two Runtimes, a Hub and an outbound node) on loopback;
no model, licensed software or external network is used.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "examples" / "backend_parity" / "offline.py"
EVIDENCE_FILES = ("run-manifest.json", "requests.jsonl", "assertions.json", "backend-parity.json", "resources.json")

pytestmark = pytest.mark.server


def harness():
    spec = importlib.util.spec_from_file_location("backend_parity_offline", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child_env():
    env = {k: v for k, v in os.environ.items() if k not in ("STK_TOKEN_PLAN_MODEL", "DISPLAY", "WAYLAND_DISPLAY")}
    env["STK_TOKEN_PLAN_API_KEY"] = ""
    return env


def evidence_text(directory):
    return "".join((directory / name).read_text(encoding="utf-8") for name in EVIDENCE_FILES)


# --- one real run -------------------------------------------------------------------------------------


@pytest.mark.skipif(platform.system() != "Linux", reason="the Runtime and control service are Linux-only")
def test_two_real_deployments_agree_on_task_semantics(tmp_path):
    for name in ("fastapi", "uvicorn", "httpx", "psutil"):
        pytest.importorskip(name)
    evidence = tmp_path / "evidence"
    started = time.monotonic()
    result = subprocess.run([sys.executable, str(HARNESS), "--mode", "source", "--deadline", "170",
                             "--evidence-dir", str(evidence), "--work-root", str(tmp_path)],
                            capture_output=True, text=True, env=child_env(), cwd=tmp_path, timeout=200)
    assert time.monotonic() - started < 180
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    checks = json.loads((evidence / "assertions.json").read_text(encoding="utf-8"))
    assert result.returncode == 0, (summary, checks)
    assert summary["ok"] and checks["ok"] and checks["cleanup_ok"] and checks["within_deadline"]
    assert len(checks["assertions"]) == 12 and {c["status"] for c in checks["assertions"]} == {"pass"}

    rows = {row["command"]: row for row in json.loads((evidence / "backend-parity.json").read_text(encoding="utf-8"))}
    assert rows["task.submit conflict"]["A"] == rows["task.submit conflict"]["B"] == {"refused": True, "code": "conflict"}
    assert rows["task.get spec"]["A"] is True and rows["task.get spec"]["B"] is False  # B is a projection
    assert [a["path"] for a in rows["task.artifacts"]["A"]] == ["out.txt"] == [a["path"] for a in rows["task.artifacts"]["B"]]
    for side in ("A", "B"):
        disk = rows["executions on disk"][side]
        assert len(disk) == 2 and all(run["start_markers"] == 1 and run["marker_pid_is_program"]
                                      and run["program_exited"] and run["worker_exited"] for run in disk)
    # Each path kept its own authority's IDs; replays returned the original task on their own path.
    requests = [json.loads(line) for line in (evidence / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    ids = {side: {r["task_id"] for r in requests if r["side"] == side and r.get("task_id")} for side in "AB"}
    assert ids["A"] and ids["B"] and not ids["A"] & ids["B"]
    for side in "AB":
        replays = [r["task_id"] for r in requests if r["side"] == side and r["operation"] == "task.submit"
                   and r["key"] == "parity-done-1" and r.get("task_id")]
        assert len(replays) == 2 and len(set(replays)) == 1

    manifest = json.loads((evidence / "run-manifest.json").read_text(encoding="utf-8"))
    origins = manifest["module_origins"]
    assert origins["consistent"] and origins["services_base"] == "this source tree" and origins["same_module_files"]
    assert origins["harness_sha256"] == __import__("hashlib").sha256(HARNESS.read_bytes()).hexdigest()
    assert manifest["within_deadline"] and manifest["scenario_seconds"] <= 170
    resources = json.loads((evidence / "resources.json").read_text(encoding="utf-8"))
    assert resources["leftover_pids_after_cleanup"] == [] and resources["removed_work_dir"] is True
    assert {p["label"] for p in resources["processes"]} >= {"A runtime api", "A runtime supervisor", "B runtime api",
                                                            "B runtime supervisor", "B hub serve", "B node run"}
    text = evidence_text(evidence) + result.stdout
    for forbidden in ("token", "Bearer", str(Path.home()), str(tmp_path)):
        assert forbidden not in text
    assert not any(tmp_path.glob("stk-parity-*"))  # the private deployments are gone


# --- waits ----------------------------------------------------------------------------------------------


class Stuck:
    """A side whose task never finishes and whose submit must never be called again."""
    name = "stub"

    def __init__(self, states):
        self.states, self.reads, self.submits = list(states), 0, 0

    def task(self, task_id):
        from suan.desktop_bridge.protocol import BridgeError
        self.reads += 1
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if state == "unavailable":
            raise BridgeError("unavailable", "node offline")
        return {"id": task_id, "state": state}

    def submit(self, *args, **kwargs):  # pragma: no cover - the assertion is that this never runs
        self.submits += 1


def test_unanswered_wait_is_unknown_and_never_resubmits(monkeypatch):
    module = harness()
    side = Stuck(["running"])
    monkeypatch.setattr(module, "DEADLINE", time.monotonic() + 0.6)  # the global budget bounds a 60 s wait
    started = time.monotonic()
    with pytest.raises(module.Unknown, match="did not reach"):
        module.wait_terminal(side, "t1", 60)
    assert time.monotonic() - started < 3
    assert side.reads >= 1 and side.submits == 0


def test_unreachable_reads_are_not_task_failure(monkeypatch):
    module = harness()
    monkeypatch.setattr(module, "DEADLINE", None)
    side = Stuck(["unavailable", "unavailable", "succeeded"])
    assert module.wait_terminal(side, "t1", 10)["state"] == "succeeded"
    assert side.submits == 0


# --- false positives on the assertions -------------------------------------------------------------------


def passing_facts(module):
    """Facts of one side that pass every assertion (used as a baseline to break one fact at a time)."""
    run = dict(module.EXPECTED_RUN)
    stamp = {"kind": "utc", "value": "2026-11-08T12:00:00.123456+00:00"}
    times = {key: dict(stamp) for key in ("created_at", "updated_at", "attempted_at", "started_at", "finished_at")}
    proof = {"same_task": True, "same_state": True, "observed": times, "authority": copy.deepcopy(times)}
    return {"done": {"state": "succeeded", "cancel_requested": False, "reason": ""}, "replay_same_task": True,
            "conflict": {"refused": True, "code": "conflict"},
            "exact_get": {"state": "succeeded", "cancel_requested": False, "reason": ""}, "exact_get_has_spec": True,
            "artifacts": copy.deepcopy(module.EXPECTED_ARTIFACTS),
            "downloads": {a["path"]: a["sha256"] for a in module.EXPECTED_ARTIFACTS},
            "stdout_sha256": "0" * 64, "stdout_bytes": 10,
            "log_cursor_inside_character": {"offset": 5, "bytes": 5, "is_raw_suffix": True},
            "cancel": {"state": "cancelled", "cancel_requested": True, "reason": ""},
            "cancel_after_replay": {"state": "cancelled", "cancel_requested": True, "reason": ""},
            "cancel_replay_state": "cancelled", "executions_in_workspace": 2, "executions": [dict(run), dict(run)],
            "identities": {"workspace_id": "w"},
            "time_observations": {key: copy.deepcopy(proof) for key in ("done", "exact", "cancel", "cancel_after_replay")},
            "created_at_replay": {key: dict(stamp) for key in ("submitted", "replayed", "final")}}


def statuses(module, a, b):
    return {item["id"].split()[0]: item["status"] for item in module.assertions(a, b, module.compare(a, b))}


def test_baseline_facts_pass(monkeypatch):
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    assert set(statuses(module, a, b).values()) == {"pass"}


@pytest.mark.parametrize("artifacts, downloads", [
    ([], {}),  # nothing published or downloaded on either side
    ([{"path": "other.txt", "size": 1, "sha256": "1" * 64}], {"other.txt": "1" * 64}),  # wrong file
    (None, {"out.txt": "2" * 64}),  # listed correctly but downloaded different bytes
])
def test_missing_or_wrong_artifact_fails(artifacts, downloads):
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    for side in (a, b):
        if artifacts is not None:
            side["artifacts"] = artifacts
        side["downloads"] = downloads
    assert statuses(module, a, b)["A5"] == "fail"


@pytest.mark.parametrize("media_type", [None, "application/octet-stream", "image/png", 1])
def test_missing_or_wrong_media_type_cannot_pass_on_either_path(media_type):
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    for side in (a, b):
        if media_type is None:
            side["artifacts"][0].pop("media_type", None)
        else:
            side["artifacts"][0]["media_type"] = media_type
    assert statuses(module, a, b)["A5"] == "fail"


@pytest.mark.parametrize("field", ["created_at", "updated_at", "attempted_at", "started_at", "finished_at"])
@pytest.mark.parametrize("change", ["missing", "null", "invalid", "changed"])
def test_dropped_or_changed_terminal_time_cannot_pass(field, change):
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    for side in (a, b):
        for name in ("done", "exact", "cancel", "cancel_after_replay"):
            observed = side["time_observations"][name]["observed"]
            if change == "missing":
                observed.pop(field)
            elif change in ("null", "invalid"):
                observed[field] = {"kind": change}
            else:
                observed[field]["value"] = "2026-11-08T12:00:01.123456+00:00"
    found = statuses(module, a, b)
    assert found.get("A10") == "fail" and found.get("A12") == "fail"


@pytest.mark.parametrize("value", [True, 1, 1.0, [], {}, "", "not-a-time", "2026-11-08T12:00:00",
                                 "2026-11-08T12:00:00+01:00"])
def test_invalid_timestamp_values_cannot_pass_even_if_both_projections_match(value):
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    for side in (a, b):
        proof = side["time_observations"]["exact"]
        for kind in ("observed", "authority"):
            proof[kind]["updated_at"]["value"] = value
    assert statuses(module, a, b).get("A10") == "fail"


def test_original_created_at_must_survive_same_path_replay():
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    b["created_at_replay"]["replayed"]["value"] = "2026-11-08T12:00:01+00:00"
    assert statuses(module, a, b).get("A11") == "fail"


def test_each_deployment_keeps_its_own_valid_times_without_cross_clock_ordering():
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    for proof in b["time_observations"].values():
        for kind in ("observed", "authority"):
            for stamp in proof[kind].values():
                stamp["value"] = "2026-11-09T08:00:00Z"
            # A host wall clock can move backwards; this check is preservation, not clock ordering.
            proof[kind]["finished_at"]["value"] = "2026-11-09T07:00:00Z"
    for stamp in b["created_at_replay"].values():
        stamp["value"] = "2026-11-09T08:00:00Z"
    assert set(statuses(module, a, b).values()) == {"pass"}
    rows = {row["command"]: row for row in module.compare(a, b)}
    assert rows["task times"]["equal"] and rows["task created_at replay"]["equal"]
    assert rows["task times"]["A"] != rows["task times"]["B"]


@pytest.mark.parametrize("mismatch", ["same_task", "same_state"])
def test_time_proof_must_belong_to_the_original_task_and_state(mismatch):
    module = harness()
    a, b = passing_facts(module), passing_facts(module)
    b["time_observations"]["exact"][mismatch] = False
    assert statuses(module, a, b)["A10"] == "fail"


def test_invalid_time_metadata_is_not_copied_to_evidence():
    module = harness()
    values = {"created_at": "/home/manufactured/private-file", "updated_at": None,
              "started_at": True, "finished_at": "2026-11-08T12:00:00+00:00"}
    found = module.timestamp_fields(values)
    assert found == {"created_at": {"kind": "invalid"}, "updated_at": {"kind": "null"},
                     "attempted_at": {"kind": "missing"}, "started_at": {"kind": "invalid"},
                     "finished_at": {"kind": "utc", "value": values["finished_at"]}}
    assert "/home/" not in json.dumps(found)


@pytest.mark.parametrize("value", [None, "image/png", "/home/manufactured/private-license-directory"])
def test_unexpected_media_type_is_rejected_before_failure_evidence(tmp_path, monkeypatch, value):
    module = harness()
    monkeypatch.setattr(module, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "start_runtime", lambda owned, state, env, label: (None, 1, owned.work / label))
    monkeypatch.setattr(module, "start_hub", lambda *args: (object(), "a" * 32, 2))
    monkeypatch.setattr(module, "wait_node_live", lambda *args: None)

    def exercise(side):
        module.artifact_facts([{"path": "out.txt", "size": 1, "sha256": "1" * 64, "media_type": value}])
        pytest.fail("The invalid media type was accepted")

    monkeypatch.setattr(module, "exercise", exercise)
    evidence = tmp_path / "evidence"
    ok, error, _ = module.run(evidence, mode="source", work_root=tmp_path)
    assert not ok and error == {"kind": "error", "message": "artifact media type differs from the fixed text/plain fixture"}
    assert json.loads((evidence / "backend-parity.json").read_text()) == []
    assert value is None or value not in evidence_text(evidence)


PID = 4194301  # a recorded identity that is never alive: create time 1.0 cannot match any live process
VALID = {"pid": PID, "create_time": 1.0}


def fake_runs(root, workspace, runs):
    """Run directories as a worker would leave them: ``runs`` is a list of (marker text, program, worker)."""
    for index, (marker, program, worker) in enumerate(runs):
        run = root / workspace / "runs" / f"task-{index}"
        (run / "work").mkdir(parents=True)
        if marker is not None:
            (run / "parity-start.marker").write_text(marker, encoding="ascii")
        (run / "finished.json").write_text("{}", encoding="utf-8")
        for name, record in (("program.json", program), ("worker.json", worker)):
            if record is not None:
                (run / name).write_text(json.dumps(record), encoding="utf-8")
    return type("S", (), {"workspace_root": root})()


def a9_with(module, found):
    a, b = passing_facts(module), passing_facts(module)
    a["executions"] = found
    return statuses(module, a, b)["A9"]


def test_valid_run_directories_pass(tmp_path):
    module = harness()
    side = fake_runs(tmp_path, "w", [(f"start {PID}\n", VALID, VALID)] * 2)
    found = module.executions(side, "w", timeout=0)
    assert found == [module.EXPECTED_RUN] * 2 and a9_with(module, found) == "pass"


@pytest.mark.parametrize("marker, program, worker", [
    (f"start {PID}\nstart {PID}\n", VALID, VALID),  # a second start in the same run directory
    ("start garbage\n", VALID, VALID),  # not a PID
    (f"start {PID}\nnoise\n", VALID, VALID),  # an extra non-marker line
    ("start 0\n", {"pid": 0, "create_time": 1.0}, VALID),  # not a positive PID
    (f"start {PID + 1}\n", VALID, VALID),  # another process's PID
    (None, VALID, VALID),  # never started
    ("", VALID, VALID),  # empty marker
    (f"start {PID}\n", None, VALID),  # no recorded program
    (f"start {PID}\n", {"pid": str(PID), "create_time": 1.0}, VALID),  # malformed program PID
    (f"start {PID}\n", {"pid": True, "create_time": 1.0}, VALID),  # a boolean is not a PID
    (f"start {PID}\n", {"pid": PID, "create_time": float("nan")}, VALID),  # no usable create time
    (f"start {PID}\n", {"pid": PID}, VALID),  # no create time at all
    (f"start {PID}\n", VALID, {"pid": -5, "create_time": 1.0}),  # malformed worker identity
    (f"start {PID}\n", VALID, None),  # no recorded worker
])
def test_bad_marker_or_identity_fails(tmp_path, marker, program, worker):
    module = harness()
    side = fake_runs(tmp_path, "w", [(f"start {PID}\n", VALID, VALID), (marker, program, worker)])
    found = module.executions(side, "w", timeout=0)
    assert found[0] == module.EXPECTED_RUN and found[1] != module.EXPECTED_RUN
    assert a9_with(module, found) == "fail"


def test_a_third_run_directory_fails(tmp_path):
    module = harness()
    side = fake_runs(tmp_path, "w", [(f"start {PID}\n", VALID, VALID)] * 3)
    assert a9_with(module, module.executions(side, "w", timeout=0)) == "fail"


# --- origins -----------------------------------------------------------------------------------------------


def probe(base, digest="a"):
    return {"base": str(base), "modules": {"suan.runtime.server": {"path": "suan/runtime/server.py",
                                                                    "sha256": digest * 64}}}


def test_mixed_origins_are_never_consistent(tmp_path):
    module = harness()
    site = tmp_path / "venv" / "lib" / "site-packages"
    other = tmp_path / "another-checkout"
    # Same installed base for both, identical files: the only consistent installed case.
    assert module.classify_origins("installed", probe(site), probe(site), root=ROOT)["consistent"]
    # Harness from another checkout while the services use the installed wheel.
    assert not module.classify_origins("installed", probe(other), probe(site), root=ROOT)["consistent"]
    # Same base but a different file under it.
    assert not module.classify_origins("installed", probe(site, "a"), probe(site, "b"), root=ROOT)["consistent"]
    # Both from another checkout (an editable install elsewhere) claiming "installed".
    assert not module.classify_origins("installed", probe(other), probe(other), root=ROOT)["consistent"]
    # Source mode is only this tree.
    assert module.classify_origins("source", probe(ROOT), probe(ROOT), root=ROOT)["consistent"]
    assert not module.classify_origins("source", probe(other), probe(other), root=ROOT)["consistent"]
    assert not module.classify_origins("source", probe(ROOT), probe(site), root=ROOT)["consistent"]
    record = module.classify_origins("installed", probe(other), probe(site), root=ROOT)
    assert str(tmp_path) not in json.dumps(record)  # absolute bases are compared, never exported


def test_mode_mismatch_starts_nothing(tmp_path):
    """Claiming the installed package while running this source tree fails before any process starts."""
    module = harness()
    evidence = tmp_path / "evidence"
    original = list(sys.path)
    try:
        sys.path.insert(0, str(ROOT))
        ok, error, _ = module.run(evidence, work_root=tmp_path, mode="installed", deadline_seconds=30)
    finally:
        sys.path[:] = original
    assert ok is False and error is not None
    assert json.loads((evidence / "resources.json").read_text(encoding="utf-8"))["processes"] == []


# --- budget, cleanup and exported errors ---------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "170"])
def test_invalid_deadline_is_refused(tmp_path, value):
    module = harness()
    with pytest.raises(ValueError):
        module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=value)
    if not isinstance(value, (bool, str)):
        assert module.main(["--evidence-dir", str(tmp_path / "e2"), "--deadline", str(value)]) == 2


def test_spent_budget_cannot_pass(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module, "module_origins", lambda env, mode: {"consistent": True})
    calls = []

    def slow_start(owned, state, env, label):
        time.sleep(0.3)  # setup outlives the 0.2 s budget
        owned.run(f"{label} init", [sys.executable, "-c", "print('ran')"], env)  # a budgeted call
        calls.append(label)

    monkeypatch.setattr(module, "start_runtime", slow_start)
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=0.2)
    checks = json.loads((tmp_path / "evidence" / "assertions.json").read_text(encoding="utf-8"))
    assert calls == []  # the call after the budget was not made
    assert ok is False and error["kind"] == "unknown" and checks["within_deadline"] is False and not checks["ok"]
    assert json.loads((tmp_path / "evidence" / "resources.json").read_text(encoding="utf-8"))["processes"] == []


def test_failed_removal_is_not_clean(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module, "module_origins", lambda env, mode: {"consistent": True})
    # Removal silently fails (as rmtree(ignore_errors=True) may); only the harness's own reference is replaced.
    monkeypatch.setattr(module, "shutil", type("NoRemoval", (), {"rmtree": staticmethod(lambda *a, **k: None)}))

    def no_deployment(*args):
        raise module.Unknown("no deployment in this test")

    monkeypatch.setattr(module, "start_runtime", no_deployment)
    ok, _, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    resources = json.loads((tmp_path / "evidence" / "resources.json").read_text(encoding="utf-8"))
    assert ok is False and resources["removed_work_dir"] is False
    assert json.loads((tmp_path / "evidence" / "assertions.json").read_text(encoding="utf-8"))["cleanup_ok"] is False
    assert module.cleanup_status({"leftover_pids_after_cleanup": [], "cleanup": [], "removed_work_dir": False}, False) is False
    assert module.cleanup_status({"leftover_pids_after_cleanup": [], "cleanup": [], "removed_work_dir": True}, False) is True
    assert module.cleanup_status({"leftover_pids_after_cleanup": [123], "cleanup": [], "removed_work_dir": True}, False) is False


def test_exception_text_with_a_path_or_secret_never_reaches_evidence(tmp_path, monkeypatch, capsys):
    module = harness()
    # Manufactured, low-entropy placeholders; nothing real.
    secret_path, secret = "/home/someone-else/.ssh/private_key", "manufactured-secret-0000"
    monkeypatch.setattr(module, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(sys, "path", list(sys.path))  # main() may prepend this tree in source mode

    def leaking(*args):
        raise FileNotFoundError(f"{secret_path} {secret}")

    monkeypatch.setattr(module, "start_runtime", leaking)
    evidence = tmp_path / "evidence"
    assert module.main(["--mode", "source", "--evidence-dir", str(evidence), "--work-root", str(tmp_path)]) == 1
    printed = capsys.readouterr()
    text = evidence_text(evidence) + printed.out + printed.err
    assert secret_path not in text and secret not in text and "someone-else" not in text
    exported = json.loads((evidence / "assertions.json").read_text(encoding="utf-8"))["error"]
    assert exported == {"kind": "error", "code": "FileNotFoundError",
                        "message": "unexpected error (details withheld from evidence)"}
    # A harness-written Unknown keeps its controlled message.
    assert module.exported_error(module.Unknown("A: task did not reach ('succeeded',) before the deadline")) == {
        "kind": "unknown", "message": "A: task did not reach ('succeeded',) before the deadline"}


# --- cleanup races and setup failures ---------------------------------------------------------------------


class Exiting:
    """A spawned process that exits between the poll and the signal."""

    def __init__(self, pid):
        self.pid, self.returncode, self.polls = pid, None, 0

    def poll(self):
        self.polls += 1
        if self.polls > 1:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


def test_process_exiting_before_its_signal_is_a_clean_stop(tmp_path, monkeypatch):
    module = harness()
    owned = module.Owned(tmp_path)
    owned.processes = [("B hub serve", Exiting(PID)), ("B node run", Exiting(PID - 1))]

    def gone(pid, number):
        raise ProcessLookupError

    monkeypatch.setattr(module.os, "killpg", gone)
    owned.stop_spawned()
    assert owned.resources["cleanup"] == [{"label": "B node run", "pid": PID - 1, "exit_code": 0},
                                          {"label": "B hub serve", "pid": PID, "exit_code": 0}]


def test_a_failing_cleanup_step_does_not_skip_the_others(tmp_path, monkeypatch):
    module = harness()
    owned = module.Owned(tmp_path / "work")
    for label in ("A", "B"):
        (owned.work / label / "runtime").mkdir(parents=True)
        (owned.work / label / "runtime" / "config.json").write_text("{}", encoding="utf-8")
    stopped = []

    def broken_stop():
        raise PermissionError("/home/someone-else/manufactured")

    monkeypatch.setattr(owned, "stop_spawned", broken_stop)
    monkeypatch.setattr(module, "stop_runtime", lambda owned, state, env, label: stopped.append(label))
    module.clean_up(owned, {}, False, (("A", None), ("B", None)))
    resources = owned.resources
    assert stopped == ["A", "B"] and resources["leftover_pids_after_cleanup"] == []
    assert resources["removed_work_dir"] is True and not owned.work.exists()
    assert resources["cleanup"] == [{"label": "spawned processes", "error": "PermissionError"}]
    assert module.cleanup_status(resources, False) is False  # removed, but the failed step is unclean


def test_a_failing_leftover_scan_is_not_clean(tmp_path, monkeypatch):
    module = harness()
    owned = module.Owned(tmp_path / "work")
    owned.work.mkdir()

    def broken_scan(*, terminate):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(owned, "leftovers", broken_scan)
    module.clean_up(owned, {}, False, ())
    assert owned.resources["leftover_pids_after_cleanup"] is None and owned.resources["removed_work_dir"] is True
    assert module.cleanup_status(owned.resources, False) is False


def test_unusable_work_root_is_a_controlled_failure(tmp_path, monkeypatch, capsys):
    module = harness()
    monkeypatch.setattr(sys, "path", list(sys.path))
    missing = tmp_path / "manufactured-missing-root" / "below"
    evidence = tmp_path / "evidence"
    code = module.main(["--mode", "source", "--evidence-dir", str(evidence), "--work-root", str(missing)])
    printed = capsys.readouterr()
    assert code == 1 and "Traceback" not in printed.err
    text = evidence_text(evidence) + printed.out + printed.err
    assert "manufactured-missing-root" not in text and str(tmp_path) not in text
    checks = json.loads((evidence / "assertions.json").read_text(encoding="utf-8"))
    assert checks["error"] == {"kind": "error", "code": "FileNotFoundError",
                               "message": "unexpected error (details withheld from evidence)"}
    assert checks["ok"] is False and checks["assertions"] == []
    resources = json.loads((evidence / "resources.json").read_text(encoding="utf-8"))
    assert resources["work_dir_created"] is False and resources["processes"] == []


def test_unwritable_evidence_dir_is_a_controlled_failure(tmp_path, monkeypatch, capsys):
    module = harness()
    monkeypatch.setattr(sys, "path", list(sys.path))

    def no_deployment(*args):
        raise module.Unknown("no deployment in this test")

    monkeypatch.setattr(module, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "start_runtime", no_deployment)
    blocker = tmp_path / "manufactured-file"
    blocker.write_text("", encoding="utf-8")
    code = module.main(["--mode", "source", "--evidence-dir", str(blocker / "evidence"), "--work-root", str(tmp_path)])
    printed = capsys.readouterr()
    assert code == 1 and "Traceback" not in printed.err and "manufactured-file" not in printed.out + printed.err
    assert json.loads(printed.out)["error"]["kind"] == "error"
    assert not any(tmp_path.glob("stk-parity-*"))  # its private directory was still removed


def test_subsecond_budget_overrun_cannot_round_into_success(tmp_path, monkeypatch):
    module = harness()
    clock, calls = [0.0], [0]
    monkeypatch.setattr(module, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(module, "module_origins", lambda *args: {"consistent": True})
    monkeypatch.setattr(module, "manifest", lambda *args: {})

    class Client:
        def tasks(self):
            return []

    class Backend:
        def __init__(self, *args, **kwargs):
            pass

    backends = types.ModuleType("suan.desktop_bridge.backends")
    backends.RuntimeBackend = backends.HubBackend = Backend
    monkeypatch.setitem(sys.modules, "suan.desktop_bridge.backends", backends)
    monkeypatch.setattr(module, "start_runtime", lambda owned, *args: (Client(), 1, owned.work))
    monkeypatch.setattr(module, "start_hub", lambda *args: (None, "node", 2))
    monkeypatch.setattr(module, "wait_node_live", lambda *args: None)
    monkeypatch.setattr(module.Owned, "leftovers", lambda *args, **kwargs: [])

    def completed_scenario(*args):
        calls[0] += 1
        if calls[0] == 2:
            clock[0] = 1.04
        return passing_facts(module)

    monkeypatch.setattr(module, "exercise", completed_scenario)
    evidence = tmp_path / "evidence"
    ok, error, _ = module.run(evidence, work_root=tmp_path, mode="source", deadline_seconds=1)
    checks = json.loads((evidence / "assertions.json").read_text())
    assert error is None and checks["cleanup_ok"]
    assert {item["status"] for item in checks["assertions"]} == {"pass"}
    assert not ok and not checks["within_deadline"]


def test_config_probe_failure_does_not_skip_cleanup_or_evidence(tmp_path, monkeypatch):
    module = harness()
    stopped, scans, blocked = [], [], [None]
    original_exists = Path.exists
    monkeypatch.setattr(module, "module_origins", lambda *args: {"consistent": True})
    monkeypatch.setattr(module, "manifest", lambda *args: {})

    def setup_then_stop(owned, *args):
        for label in ("A", "B"):
            state = owned.work / label / "runtime"
            state.mkdir(parents=True)
            (state / "config.json").write_text("{}")
        blocked[0] = owned.work / "A" / "runtime" / "config.json"
        raise module.Unknown("no service started in this test")

    def inaccessible(path):
        if path == blocked[0]:
            raise PermissionError("manufactured-private-path")
        return original_exists(path)

    def scan(owned, *, terminate):
        scans.append(terminate)
        return []

    monkeypatch.setattr(module, "start_runtime", setup_then_stop)
    monkeypatch.setattr(Path, "exists", inaccessible)
    monkeypatch.setattr(module, "stop_runtime", lambda owned, state, env, label: stopped.append(label))
    monkeypatch.setattr(module.Owned, "leftovers", scan)
    evidence = tmp_path / "evidence"
    ok, error, _ = module.run(evidence, work_root=tmp_path, mode="source")
    assert not ok and error["kind"] == "unknown"
    assert stopped == ["B"] and scans == [True, False]
    assert set(path.name for path in evidence.iterdir()) == set(EVIDENCE_FILES)
    resources = json.loads((evidence / "resources.json").read_text())
    assert resources["removed_work_dir"] and resources["leftover_pids_after_cleanup"] == []
    assert {"label": "A runtime", "error": "PermissionError"} in resources["cleanup"]
    assert not json.loads((evidence / "assertions.json").read_text())["cleanup_ok"]
    assert "manufactured-private-path" not in evidence_text(evidence)
    assert not any(tmp_path.glob("stk-parity-*"))
