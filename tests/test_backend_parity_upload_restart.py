"""D1 upload restart (examples/backend_parity/upload_restart.py).

One real run: a real stdio Bridge is SIGKILLed after the Hub accepted an upload chunk whose ACK it had not
journaled; the same Bridge state resumes the original transfer at the held offset and the reviewed import lands
only after an explicit decision. Plus controlled counterexamples: a premature or non-SIGKILL Bridge exit, bytes
not really accepted, a changed transfer/session/request/key, a restart at zero, duplicate work, an unbound or
tampered driver, a late result and a bad cleanup can never pass. Both test drivers are exercised on their own.
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
SCRIPT = ROOT / "examples" / "backend_parity" / "upload_restart.py"
HELPERS = {"offline_helper_sha256": ROOT / "examples" / "backend_parity" / "offline.py",
           "disconnect_helper_sha256": ROOT / "examples" / "backend_parity" / "disconnect.py",
           "upload_restart_sha256": SCRIPT}
EVIDENCE_FILES = ("run-manifest.json", "requests.jsonl", "phases.json", "assertions.json", "resources.json")

pytestmark = pytest.mark.server


def harness():
    spec = importlib.util.spec_from_file_location("backend_parity_upload_restart", SCRIPT)
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
def test_bridge_crash_after_accepted_chunk_resumes_the_original_transfer(tmp_path):
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
    assert summary["ok"] and checks["ok"] and checks["cleanup_ok"] and checks["within_deadline"] and checks["drivers_bound"]
    assert len(checks["assertions"]) == 10 and {c["status"] for c in checks["assertions"]} == {"pass"}

    module = harness()
    phases = load(evidence, "phases.json")
    total = len(module.INPUT)
    accepted = phases["accepted"]
    assert accepted["hub_returned_offset"] == module.CHUNK < total and accepted["journal"]["bytes_done"] == 0
    assert accepted["hub_part"] == {"present": True, "bytes": module.CHUNK, "matches_input_prefix": True}
    assert phases["bridge_stop"]["exit_code"] == -9 and phases["bridge_stop"]["alive_before_kill"] is True
    assert [c["offset"] for c in phases["restart"]["chunks"]] == list(range(module.CHUNK, total, module.CHUNK))
    assert phases["completion"]["files"] == [{"path": module.REMOTE, "size": total, "sha256": module.DIGEST}]
    for name, digest in module.DRIVER_SHA256.items():
        assert phases["drivers"][name] == {"expected_sha256": digest, "written_sha256": digest,
                                           "launch_sha256": digest, "launched": True}

    manifest = load(evidence, "run-manifest.json")
    origins = manifest["module_origins"]
    assert origins["consistent"] and origins["services_base"] == "this source tree" and origins["driver_files_match"]
    for key, path in HELPERS.items():
        assert origins[key] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert origins["driver_sha256"] == module.DRIVER_SHA256
    assert {"suan.desktop_bridge.transfers", "suan.desktop_bridge.server", "suan.control.uploads"} <= set(origins["modules"])
    assert "schema" not in manifest and manifest["scenario_seconds"] <= 170

    resources = load(evidence, "resources.json")
    assert [p["label"] for p in resources["processes"]] == ["B runtime api", "B runtime supervisor", "B hub serve",
                                                           "B node run", "Bridge original", "Bridge restarted"]
    assert resources["leftover_pids_after_cleanup"] == [] and resources["removed_work_dir"] is True
    text = "".join((evidence / name).read_text(encoding="utf-8") for name in EVIDENCE_FILES) + result.stdout
    for forbidden in ("token", "Bearer", str(Path.home()), str(tmp_path)):
        assert forbidden not in text
    assert not any(tmp_path.glob("stk-upload-restart-*"))


# --- counterexamples on the assertions --------------------------------------------------------------------


KILLED = {"identity_valid": True, "running_before_kill": True, "alive_before_kill": True, "signal_sent": True,
          "exit_code": -9, "reaped": True, "killed_by_sigkill": True, "node_alive_after": False}


def passing_facts(module):
    total, chunk = len(module.INPUT), module.CHUNK
    offsets = list(range(chunk, total, chunk))
    chunks = [{"same_session": True, "offset": o, "length": min(chunk, total - o),
               "returned_offset": min(o + chunk, total)} for o in offsets]
    return {
        "drivers": {name: {"expected_sha256": d, "written_sha256": d, "launch_sha256": d, "launched": True}
                    for name, d in module.DRIVER_SHA256.items()},
        "accepted": {"transfer_is_keyed": True, "first_chunk_offset": 0, "first_chunk_length": chunk,
                     "hub_returned_offset": chunk, "hub_completed": False,
                     "hub_status": {"same_session": True, "offset": chunk, "completed": False, "size": total},
                     "hub_part": {"present": True, "bytes": chunk, "matches_input_prefix": True},
                     "journal": {"state": "running", "upload_id_is_session": True, "bytes_done": 0, "item_done": False,
                                 "request_is_original": True},
                     "bridge_alive": True, "total": total},
        "bridge_stop": dict(KILLED),
        "outage": {"services_alive": {"B hub serve": True, "B node run": True, "B runtime api": True,
                                      "B runtime supervisor": True},
                   "journal_state": "running", "journal_upload_id_kept": True, "hub_offset": chunk,
                   "hold_expired": False},
        "restart": {"recovered_state": "interrupted", "same_transfer": True, "same_hub_device": True,
                    "key_replay_same_transfer": True, "resumed_state": "queued",
                    "begins": [{"same_session": True, "returned_offset": chunk, "frozen_digest": True}],
                    "chunks": chunks, "expected_chunk_offsets": offsets,
                    "finishes": [{"same_session": True, "completed": True}]},
        "review": {"action_is_derived": True, "request_exact": True, "state_before": "review",
                   "transfer_before": "running", "workspace_files_before": 0, "tasks_before": 0},
        "completion": {"approved": True, "transfer_state": "completed", "same_transfer": True,
                       "action_after": "succeeded",
                       "files": [{"path": module.REMOTE, "size": total, "sha256": module.DIGEST}],
                       "bytes_match": True, "tasks": 0, "action_kinds": ["workspace.create", "workspace.import"],
                       "transfers": 1, "hub_session_after": 404},
    }


def requests():
    entries = [("Bridge original", "hello"), ("Bridge original", "connections.pair_hub"),
               ("Bridge original", "workspace.create"), ("Bridge original", "upload.start"),
               ("Bridge restarted", "hello"), ("Bridge restarted", "transfer.get"),
               ("Bridge restarted", "connections.list"), ("Bridge restarted", "upload.start"),
               ("Bridge restarted", "transfer.resume"), ("Bridge restarted", "transfer.get")]
    return [{"bridge": bridge, "method": method, "outcome": "ok"} for bridge, method in entries]


def failing(module, facts, log=None):
    log = requests() if log is None else log
    return {item["id"].split()[0] for item in module.assertions(facts, log) if item["status"] == "fail"}


def test_baseline_facts_pass():
    module = harness()
    assert failing(module, passing_facts(module)) == set()


def test_missing_facts_never_pass():
    module = harness()
    assert failing(module, {}, []) == {f"U{i}" for i in range(0, 10)}


@pytest.mark.parametrize("change, broken", [
    # Unbound or tampered drivers.
    (lambda f, r: f["drivers"]["crash"].update(launch_sha256="0" * 64), {"U0"}),
    (lambda f, r: f["drivers"]["observe"].update(written_sha256="0" * 64), {"U0"}),
    (lambda f, r: f["drivers"].pop("observe"), {"U0"}),
    (lambda f, r: f["drivers"]["crash"].update(launched=False), {"U0"}),
    # Bytes not really accepted by the Hub before the crash, or the ACK already journaled.
    (lambda f, r: f["accepted"].update(hub_returned_offset=0, first_chunk_length=0), {"U1", "U3", "U5"}),
    (lambda f, r: f["accepted"]["hub_status"].update(offset=0), {"U1"}),
    (lambda f, r: f["accepted"]["hub_part"].update(matches_input_prefix=False), {"U1"}),
    (lambda f, r: f["accepted"]["hub_part"].update(present=False, bytes=0), {"U1"}),
    (lambda f, r: f["accepted"].update(hub_completed=True), {"U1"}),
    (lambda f, r: f["accepted"]["journal"].update(bytes_done=f["accepted"]["hub_returned_offset"]), {"U1"}),
    (lambda f, r: f["accepted"]["journal"].update(upload_id_is_session=False), {"U1"}),
    (lambda f, r: f["accepted"]["journal"].update(request_is_original=False), {"U1"}),
    (lambda f, r: f["accepted"].update(transfer_is_keyed=False), {"U1"}),
    (lambda f, r: f["accepted"].update(bridge_alive=False), {"U1"}),
    # A premature, natural or non-SIGKILL Bridge exit; the hold expiring; a service going down too.
    (lambda f, r: f["bridge_stop"].update(running_before_kill=False, alive_before_kill=False, signal_sent=False,
                                          exit_code=75, killed_by_sigkill=False), {"U2"}),
    (lambda f, r: f["bridge_stop"].update(exit_code=-15, killed_by_sigkill=False), {"U2"}),
    (lambda f, r: f["bridge_stop"].update(exit_code=0, killed_by_sigkill=False), {"U2"}),
    (lambda f, r: f["outage"].update(hold_expired=True), {"U2"}),
    (lambda f, r: f["outage"]["services_alive"].update({"B hub serve": False}), {"U2"}),
    # A clean stop instead of a crash, or a lost session.
    (lambda f, r: f["outage"].update(journal_state="interrupted"), {"U3"}),
    (lambda f, r: f["outage"].update(journal_upload_id_kept=False), {"U3"}),
    (lambda f, r: f["outage"].update(hub_offset=0), {"U3"}),
    # A different transfer, a re-paired Hub, or a new key.
    (lambda f, r: f["restart"].update(same_transfer=False), {"U4"}),
    (lambda f, r: f["restart"].update(same_hub_device=False), {"U4"}),
    (lambda f, r: f["restart"].update(key_replay_same_transfer=False), {"U4"}),
    (lambda f, r: f["restart"].update(recovered_state="queued"), {"U4"}),
    # A restart from zero, another session, a changed request or a gap.
    (lambda f, r: f["restart"]["begins"][0].update(returned_offset=0), {"U5"}),
    (lambda f, r: f["restart"]["begins"][0].update(same_session=False), {"U5"}),
    (lambda f, r: f["restart"]["begins"][0].update(frozen_digest=False), {"U5"}),
    (lambda f, r: f["restart"]["chunks"].insert(0, {"same_session": True, "offset": 0, "length": f["accepted"]["hub_returned_offset"],
                                                    "returned_offset": f["accepted"]["hub_returned_offset"]}), {"U5"}),
    (lambda f, r: f["restart"]["chunks"][0].update(same_session=False), {"U5"}),
    (lambda f, r: f["restart"]["chunks"].pop(), {"U5"}),
    (lambda f, r: f["restart"]["finishes"].append({"same_session": True, "completed": True}), {"U5"}),
    (lambda f, r: f["restart"].update(begins=[]), {"U5"}),
    # The import not reviewed, a different request, or files landing before the decision.
    (lambda f, r: f["review"].update(state_before="queued"), {"U6"}),
    (lambda f, r: f["review"].update(request_exact=False), {"U6"}),
    (lambda f, r: f["review"].update(action_is_derived=False), {"U6"}),
    (lambda f, r: f["review"].update(workspace_files_before=1), {"U6"}),
    (lambda f, r: f["review"].update(tasks_before=1), {"U6"}),
    # The wrong bytes, another transfer, or a session left open.
    (lambda f, r: f["completion"].update(bytes_match=False), {"U7"}),
    (lambda f, r: f["completion"]["files"][0].update(sha256="0" * 64), {"U7"}),
    (lambda f, r: f["completion"].update(same_transfer=False), {"U7"}),
    (lambda f, r: f["completion"].update(hub_session_after="open"), {"U7"}),
    (lambda f, r: f["completion"].update(transfer_state="failed"), {"U7"}),
    # Duplicate work.
    (lambda f, r: f["completion"].update(transfers=2), {"U8"}),
    (lambda f, r: f["completion"].update(tasks=1), {"U8"}),
    (lambda f, r: f["completion"].update(action_kinds=["workspace.create", "workspace.import", "workspace.import"]),
     {"U8"}),
    # A second pairing, a second upload under another key, no explicit resume, a failed call.
    (lambda f, r: r.insert(5, {"bridge": "Bridge restarted", "method": "connections.pair_hub", "outcome": "ok"}), {"U9"}),
    (lambda f, r: r.insert(5, {"bridge": "Bridge restarted", "method": "upload.start", "outcome": "ok"}), {"U9"}),
    (lambda f, r: r.pop(8), {"U9"}),
    (lambda f, r: r[-1].update(outcome="unknown"), {"U9"}),
])
def test_wrong_boundary_changed_identity_or_duplicate_work_fails(change, broken):
    module = harness()
    facts, log = passing_facts(module), requests()
    change(facts, log)
    assert failing(module, facts, log) == broken


# --- the drivers, on their own -----------------------------------------------------------------------------


def test_crash_driver_calls_the_real_chunk_first_then_holds_and_exits_when_the_hold_expires(tmp_path):
    module = harness()
    driver = tmp_path / "crash_driver.py"
    driver.write_text(module.CRASH_DRIVER, encoding="utf-8")
    calls = tmp_path / "calls.txt"
    probe = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('driver', {str(driver)!r})\n"
        "driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)\n"
        "class Client:\n"
        "    def upload_chunk(self, upload_id, offset, data):\n"
        f"        open({str(calls)!r}, 'a').write(f'{{offset}}\\n')\n"
        "        return {'id': upload_id, 'offset': offset + len(data), 'completed': False}\n"
        f"driver.install(Client, {str(tmp_path)!r}, 0.3)\n"
        "Client().upload_chunk('u' * 32, 0, b'x' * 8)\n"
        "print('the held return came back')\n")
    started = time.monotonic()
    result = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=30)
    assert result.returncode == module.HOLD_EXPIRED and "came back" not in result.stdout
    assert time.monotonic() - started < 10
    assert calls.read_text() == "0\n"  # the real call ran before the hold
    stages = [json.loads(line) for line in (tmp_path / "stages.jsonl").read_text().splitlines()]
    assert [s["stage"] for s in stages] == ["accepted_held", "hold_expired"]
    assert stages[0]["returned_offset"] == 8 and stages[0]["offset"] == 0 and stages[0]["length"] == 8


def test_observe_driver_records_real_calls_and_changes_nothing(tmp_path):
    module = harness()
    namespace = {"__name__": "observe_driver_test"}
    exec(compile(module.OBSERVE_DRIVER, "bridge_driver.py", "exec"), namespace)  # noqa: S102 - the fixed text

    class Client:
        def upload_begin(self, digest, size):
            return {"id": "s" * 32, "offset": 5, "completed": False}

        def upload_status(self, upload_id):
            return {"id": upload_id, "offset": 5, "completed": False}

        def upload_chunk(self, upload_id, offset, data):
            return {"id": upload_id, "offset": offset + len(data), "completed": False}

        def upload_finish(self, upload_id):
            return {"id": upload_id, "offset": 9, "completed": True}

    namespace["install"](Client, str(tmp_path))
    client = Client()
    assert client.upload_begin("d" * 64, 9) == {"id": "s" * 32, "offset": 5, "completed": False}
    assert client.upload_chunk("s" * 32, 5, b"four") == {"id": "s" * 32, "offset": 9, "completed": False}
    assert client.upload_finish("s" * 32)["completed"] is True
    stages = [json.loads(line) for line in (tmp_path / "stages.jsonl").read_text().splitlines()]
    assert [s["stage"] for s in stages] == ["upload_begin", "upload_chunk", "upload_finish"]
    assert stages[1]["offset"] == 5 and stages[1]["length"] == 4 and stages[1]["returned_offset"] == 9


# --- run level: driver proof, cleanup, budget, late results --------------------------------------------------


def fake_scenario(module, delay=0.0, drivers=lambda d: None):
    def scenario(owned, env, facts, log, clients):
        time.sleep(delay)
        facts.update(passing_facts(module))
        drivers(facts["drivers"])
        log.extend(requests())
    return scenario


def run_fake(module, tmp_path, monkeypatch, deadline=30, **kwargs):
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setattr(module, "scenario", fake_scenario(module, **kwargs))
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=deadline)
    return ok, error, load(tmp_path / "evidence", "assertions.json")


def test_a_passing_scenario_passes_the_run_gate(tmp_path, monkeypatch):
    module = harness()
    ok, error, checks = run_fake(module, tmp_path, monkeypatch)
    assert ok is True and error is None and checks["drivers_bound"] is True


@pytest.mark.parametrize("change", [lambda d: d["crash"].update(launch_sha256="0" * 64), lambda d: d.clear()])
def test_wrong_or_missing_driver_proof_fails_the_run(tmp_path, monkeypatch, change):
    module = harness()
    ok, error, checks = run_fake(module, tmp_path, monkeypatch, drivers=change)
    assert error is None and checks["cleanup_ok"] and checks["within_deadline"]
    assert [c["id"].split()[0] for c in checks["assertions"] if c["status"] == "fail"] == ["U0"]
    assert ok is False and checks["drivers_bound"] is False


def test_driver_proof_is_required_even_if_the_assertions_are_bypassed(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module, "assertions", lambda facts, log: [{"id": "bypassed", "status": "pass"}])
    ok, error, checks = run_fake(module, tmp_path, monkeypatch, drivers=lambda d: d.clear())
    assert checks["assertions"] == [{"id": "bypassed", "status": "pass"}] and ok is False


def test_a_tampered_driver_is_never_launched(tmp_path, monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "module_origins", lambda env, mode: {"consistent": True})
    monkeypatch.setitem(module.DRIVERS, "crash", module.CRASH_DRIVER + "\n# tampered\n")  # the digest stays

    def must_not_start(*args):
        pytest.fail("a service started with a tampered driver")

    monkeypatch.setattr(module.off, "start_runtime", must_not_start)
    ok, error, _ = module.run(tmp_path / "evidence", work_root=tmp_path, mode="source", deadline_seconds=30)
    assert ok is False and error == {"kind": "error", "message": module.DRIVER_MISMATCH}
    assert load(tmp_path / "evidence", "resources.json")["processes"] == []


def test_a_driver_changed_before_launch_is_never_launched(tmp_path, monkeypatch):
    module = harness()
    facts = {"drivers": {}}
    owned = module.off.Owned(tmp_path / "work")
    owned.work.mkdir()
    path = module.write_driver(owned, "crash", facts)
    path.write_text("print('not the driver')\n", encoding="utf-8")
    with pytest.raises(module.off.HarnessError, match="was not launched"):
        module.launch_bridge(owned, "crash", "Bridge original", path, {}, tmp_path / "bridge", facts, [])
    assert owned.processes == [] and facts["drivers"]["crash"]["launched"] is False


def test_a_passing_scenario_with_a_cleanup_failure_is_not_ok(tmp_path, monkeypatch):
    module = harness()
    real = module.off.clean_up

    def failing_clean_up(owned, env, keep, clients):
        real(owned, env, keep, clients)
        owned.resources["cleanup"].append({"label": "Bridge restarted", "error": "PermissionError"})

    monkeypatch.setattr(module.off, "clean_up", failing_clean_up)
    ok, error, checks = run_fake(module, tmp_path, monkeypatch)
    assert {c["status"] for c in checks["assertions"]} == {"pass"} and ok is False and checks["cleanup_ok"] is False


def test_a_late_scenario_is_not_ok(tmp_path, monkeypatch):
    module = harness()
    ok, error, checks = run_fake(module, tmp_path, monkeypatch, deadline=0.3, delay=0.4)
    assert {c["status"] for c in checks["assertions"]} == {"pass"} and ok is False and checks["within_deadline"] is False


def test_a_late_value_cannot_pass_its_frozen_deadline(monkeypatch):
    module = harness()
    monkeypatch.setattr(module.off, "DEADLINE", time.monotonic() + 0.3)

    def late():
        time.sleep(0.5)  # the answer arrives after the frozen deadline
        return {"state": "completed"}

    with pytest.raises(module.off.Unknown):
        module.wait_until(late, 30, "a late value")


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
