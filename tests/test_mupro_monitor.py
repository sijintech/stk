"""muFerro legacy adapter: native outputs of the fake muFerro to monitoring events (adapt mode).

The launcher tests use the fake SDK from mupro_fake.py and never start a real MPI launcher.
"""

from pathlib import Path
import json
import math
import os
import sys
import threading
import time

import pytest

from conftest import finish
from mupro_fake import make_fake_sdk, write_case, write_outputs
from suan.monitor.emit import Emitter
from suan.monitor.events import decode_line
from suan.monitor.reader import read_all
from suan.mupro import monitor as monitor_module
from suan.mupro import muferro_spec
from suan.mupro.monitor import (DEFAULT_LABELS, ENERGY_METRICS, MuferroAdapter, MuferroMonitor, header_labels,
                                parse_energy, parse_progress, replay)
from suan.mupro.run import main
from suan.runtime.models import TaskSpec

TESTS = Path(__file__).resolve().parent
NODE_ENV = ("STK_MUPRO_ENV_SCRIPTS", "MUPRO_SDK_PREFIX", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID",
            "PBS_JOBID", "SRUN_CPUS_PER_TASK", "STK_MONITOR_PATH", "STK_TASK_ID", "STK_MONITOR_FAKE_TIME",
            "PMI_RANK", "PMIX_RANK", "OMPI_COMM_WORLD_RANK", "SLURM_PROCID", "MV2_COMM_WORLD_RANK")
HEADER = "    " + "step".rjust(6) + " " * 9 + "".join(label.rjust(18) for label in DEFAULT_LABELS)


def events_of(path):
    result = read_all(path)
    assert result["invalid"] == [] and result["next_offset"] == Path(path).stat().st_size
    for raw in Path(path).read_bytes().splitlines():
        decode_line(raw, strict=True)
    return result["events"]


def kinds(events):
    return [e["type"] for e in events]


def frames(events):
    return [(e["data"]["dataset"], e["data"]["step"]) for e in events if e["type"] == "frame"]


def test_parsers():
    assert parse_progress('{"step":12,"completed_steps":2,"total_steps":4}') == {
        "step": 12, "completed_steps": 2, "total_steps": 4, "fraction": 0.5}
    assert parse_progress('{"step":1}') == {"step": 1}
    assert parse_progress("not json") is None and parse_progress("[1]") is None
    assert parse_progress('{"step":-1,"total_steps":true}') is None
    step, values = parse_energy("kt:      7 energy:  0.1500000000D+01  0.25E+00 -0.3E+01 NaN ******************")
    assert step == 7 and list(values) == list(ENERGY_METRICS)
    assert values["elastic_energy"] == 1.5 and values["landau_energy"] == -3.0
    assert math.isnan(values["gradient_energy"]) and math.isnan(values["total_energy"])
    # Fortran e18.10 drops the exponent letter when |exponent| > 99.
    step, values = parse_energy("kt:      8 energy:  0.1500000000+102 -0.2000000000-119  0.1E+01 0.30000000x0+100 1")
    assert step == 8 and values["elastic_energy"] == 1.5e101 and values["electric_energy"] == -2e-120
    assert math.isnan(values["gradient_energy"]) and values["total_energy"] == 1.0
    assert parse_energy("kt: 3 energy: 1 2 3") == (3, None)
    assert parse_energy(HEADER) is None and parse_energy("") is None
    assert header_labels(HEADER) == DEFAULT_LABELS
    custom = "    " + "step".rjust(6) + " " * 9 + "".join(f"E{n}".rjust(18) for n in range(5))
    assert header_labels(custom) == ("E0", "E1", "E2", "E3", "E4")
    assert header_labels("step energies") == DEFAULT_LABELS
    assert header_labels("x" * 200) == DEFAULT_LABELS


def test_adapter_maps_a_finished_fake_run(tmp_path):
    work = tmp_path / "work"
    case = work / "case"
    write_case(case)
    write_outputs(case)
    path = tmp_path / "events.jsonl"
    emitter = Emitter(path, src="adapter", environ={})
    adapter = MuferroAdapter(emitter, case, "case")
    adapter.poll()
    adapter.poll()  # frames must keep their size over two polls
    emitter.close()
    events = events_of(path)
    assert kinds(events)[:9] == ["progress"] + ["metric.declare"] * 5 + ["metrics"] * 3
    assert events[0]["data"] == {"step": 3, "completed_steps": 3, "total_steps": 3, "fraction": 1.0}
    declares = [e["data"] for e in events if e["type"] == "metric.declare"]
    assert declares == [{"name": name, "unit": "normalized", "label": label, "group": "energy"}
                        for name, label in zip(ENERGY_METRICS, DEFAULT_LABELS)]
    metrics = [e["data"] for e in events if e["type"] == "metrics"]
    assert metrics[2] == {"step": 3, "values": {"elastic_energy": 4.5, "electric_energy": 0.25, "landau_energy": -9.0,
                                                "gradient_energy": 0.125, "total_energy": -3.375}}
    published = [e["data"] for e in events if e["type"] == "frame"]
    assert len(published) == 30 and frames(events)[:2] == [("Polar", 0), ("Charges", 1)]
    assert published[0] == {"dataset": "Polar", "step": 0, "path": "case/Polar.00000000.dat", "reader": "mupro.dat@1",
                            "components": 3, "size": (case / "Polar.00000000.dat").stat().st_size}
    assert {e["components"] for e in published if e["dataset"] == "Strain"} == {6}
    assert ("Polar", 2) in frames(events) and frames(events)[-1] == ("Stress", 3)
    completion = [e["data"] for e in events if e["type"] == "message"]
    assert completion == [{"level": "info", "text": "muFerro wrote mupro_completion.json: completed_steps=3, final_step=3",
                           "code": "native_completion"}]
    assert {e["src"] for e in events} == {"adapter"}


def test_adapter_tails_incrementally(tmp_path):
    case = tmp_path / "case"
    case.mkdir()
    path = tmp_path / "events.jsonl"
    emitter = Emitter(path, environ={}, min_interval=0)
    adapter = MuferroAdapter(emitter, case)
    energy, progress = case / "energy_out.dat", case / "mupro_progress.jsonl"

    def append(target, text):
        with open(target, "a") as stream:
            stream.write(text)

    def new():
        seen = new.seen
        events = events_of(path)
        new.seen = len(events)
        return events[seen:]
    new.seen = 0

    adapter.poll()
    assert new() == []
    append(energy, HEADER + "\nkt:      1 energy:  0.15E+01  0.25E+00 -0.3E+01  0.125E+00 -0.1125E+0")
    adapter.poll()
    assert kinds(new()) == ["metric.declare"] * 5  # the row is still being written
    append(energy, "1\n")
    adapter.poll()
    assert [e["data"] for e in new()] == [{"step": 1, "values": {"elastic_energy": 1.5, "electric_energy": 0.25,
                                                                 "landau_energy": -3.0, "gradient_energy": 0.125,
                                                                 "total_energy": -1.125}}]
    (case / "Charges.00000001.dat").write_text("     4     3     2\n")
    (case / "Custom.00000001.dat").write_text("     4     3     2     2\n")
    adapter.poll()
    assert new() == []  # frames seen once, and progress has not reached step 1
    adapter.poll()
    assert new() == []  # stable, but progress has not reached step 1
    append(progress, '{"step":1,"completed_steps":1,"total_steps":4}\n')
    adapter.poll()
    events = new()
    assert kinds(events) == ["progress", "frame", "frame"]
    assert events[0]["data"] == {"step": 1, "completed_steps": 1, "total_steps": 4, "fraction": 0.25}
    assert [(e["data"]["dataset"], e["data"]["components"]) for e in events[1:]] == [("Charges", 1), ("Custom", 2)]
    polar = case / "Polar.00000002.dat"
    polar.write_text("     4     3     2     3\n")
    append(progress, '{"step":2,"completed_steps":2,"total_steps":4}\n')
    adapter.poll()
    append(polar, "     1     1     1     1  1.0E+00\n")  # still growing
    adapter.poll()
    assert kinds(new()) == ["progress"]
    adapter.poll()
    assert frames(new()) == [("Polar", 2)]
    (case / "Polar.00000004.dat").write_text("partial")
    adapter.poll()
    adapter.poll()
    assert new() == []
    # After a failed exit, frames beyond the last progress step may be cut off: never published.
    adapter.poll(final=True, exit_code=1)
    assert new() == []
    adapter.poll(final=True, exit_code=0)
    assert frames(new()) == [("Polar", 4)]
    emitter.close()


def test_nan_and_malformed_rows_are_flagged(tmp_path):
    case = tmp_path / "case"
    write_case(case)
    write_outputs(case, mode="nan")
    with open(case / "energy_out.dat", "a") as stream:
        stream.write("kt: 3 energy: 1 2 3\ngarbage\n")
        stream.write("".join(f"kt: {n} energy: 1 1 1 1 ****************\n" for n in range(4, 12)))
    path = tmp_path / "events.jsonl"
    emitter = Emitter(path, environ={})
    adapter = MuferroAdapter(emitter, case)
    adapter.poll(final=True, exit_code=0)
    emitter.close()
    events = events_of(path)
    metrics = [e["data"] for e in events if e["type"] == "metrics"]
    assert [m["step"] for m in metrics] == [1, 2, *range(4, 12)]
    assert metrics[1]["values"]["total_energy"] == "NaN" and metrics[1]["values"]["landau_energy"] == -6.0
    assert metrics[2]["values"]["total_energy"] == "NaN"
    warnings = [(e["data"]["code"], e["data"]["text"]) for e in events if e["type"] == "message"]
    assert warnings[0] == ("nonfinite_energy", "Non-finite energy at step 2: total_energy")
    assert [code for code, _ in warnings].count("malformed_energy_row") == 2
    assert [text for code, text in warnings if code == "nonfinite_energy"][-1] == \
        "Further nonfinite_energy warnings are suppressed"
    assert len([1 for code, _ in warnings if code == "nonfinite_energy"]) == monitor_module.MAX_WARNINGS + 1
    progress = [e["data"] for e in events if e["type"] == "progress"]
    assert progress == [{"step": 1, "completed_steps": 1, "total_steps": 3, "fraction": 1 / 3}]
    # muFerro stopped at step 2 with exit code 0, so that step's frames are complete.
    assert ("Polar", 2) in frames(events) and ("Charges", 1) in frames(events)
    assert not any(e["data"].get("code") == "native_completion" for e in events if e["type"] == "message")


def test_replay_of_a_finished_directory(tmp_path):
    work = tmp_path / "work"
    write_case(work / "case")
    write_outputs(work / "case")
    path = tmp_path / "events.jsonl"
    result = replay(Emitter(path, src="adapter", environ={"STK_MONITOR_FAKE_TIME": "5"}), work, "case")
    assert result["verification"]["status"] == "passed"
    events = events_of(path)
    assert kinds(events)[0] == "run.started" and kinds(events)[-2:] == ["verification", "run.completed"]
    assert events[0]["data"]["app"] == "muFerro" and events[0]["data"]["total_steps"] == 3
    assert events[-2]["data"] == {"verifier": "stk-mupro-1", "status": "passed", "failed_checks": []}
    assert events[-1]["data"] == {"status": "succeeded"} and {e["src"] for e in events} == {"adapter"}
    assert len(frames(events)) == 30 and [e["seq"] for e in events] == list(range(len(events)))


def test_disabled_monitor_is_inert(tmp_path):
    monitor = MuferroMonitor(Emitter(environ={}))
    assert not monitor.enabled
    monitor.started(tmp_path, ".", {"steps": 1}, 1)
    monitor.watch()
    monitor.stop(0)
    monitor.finish({"state": "succeeded"})
    assert monitor.adapter is None and monitor._thread is None


# --- the launcher (python -m suan.mupro run) in adapt mode ------------------------------------------------------


@pytest.fixture
def node(tmp_path, monkeypatch):
    """A task work dir as CWD, a clean MPI/monitoring environment and a fake bin dir first on PATH."""
    for key in [*NODE_ENV, *(key for key in os.environ if key.startswith("I_MPI_"))]:
        monkeypatch.delenv(key, raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.defpath)
    work = tmp_path / "task" / "work"
    work.mkdir(parents=True)
    monkeypatch.chdir(work)
    return work


def recording_sdk(root, mode="ok", wait_for=None):
    """The fake SDK whose muFerro records the monitoring variables it received, and can wait for a file."""
    sdk = make_fake_sdk(root, mode=mode)
    wait = (f"deadline = time.monotonic() + 30\nwhile not os.path.exists({wait_for!r}) and time.monotonic() < deadline:\n"
            f"    time.sleep(0.02)\n") if wait_for else ""
    script = sdk / "bin" / "muFerro"
    script.write_text(
        f"#!{sys.executable}\nimport json, os, sys, time\nsys.path.insert(0, {str(TESTS)!r})\n"
        "from mupro_fake import fake_muferro\n"
        "open('solver-env.json', 'w').write(json.dumps({k: os.environ.get(k) for k in "
        "('STK_MONITOR_PATH', 'STK_TASK_ID')}))\n"
        f"code = fake_muferro({mode!r})\n{wait}sys.exit(code)\n")
    return sdk


def launch(sdk, *args):
    code = main(["run", "--sdk-prefix", str(sdk), *args])
    return code, json.loads(Path("stk-mupro.json").read_text(encoding="utf-8"))


def comparable(record):
    return {key: value for key, value in record.items() if key not in {"started_at", "finished_at"}}


@pytest.mark.server
def test_launcher_adapts_and_the_solver_never_gets_the_path(node, tmp_path, monkeypatch):
    work = node
    sdk = recording_sdk(tmp_path / "sdk")
    plain_code, plain = launch(sdk, "--example")  # without STK_MONITOR_PATH: no events, no thread
    assert plain_code == 0 and plain["state"] == "succeeded"
    other = tmp_path / "task2" / "work"
    other.mkdir(parents=True)
    monkeypatch.chdir(other)
    path = tmp_path / "task2" / "events.jsonl"
    monkeypatch.setenv("STK_MONITOR_PATH", str(path))
    monkeypatch.setenv("STK_TASK_ID", "c" * 32)
    code, record = launch(sdk, "--example")
    assert code == plain_code and comparable(record) == comparable(plain)
    assert json.loads((other / "solver-env.json").read_text()) == {"STK_MONITOR_PATH": None, "STK_TASK_ID": "c" * 32}
    assert not (work.parent / "events.jsonl").exists()
    events = events_of(path)
    assert events[0]["type"] == "run.started" and events[0]["src"] == "launcher"
    assert {k: events[0]["data"][k] for k in ("app", "total_steps", "ranks")} == {"app": "muFerro", "total_steps": 3,
                                                                                    "ranks": 1}
    assert kinds(events)[-2:] == ["verification", "run.completed"]
    assert events[-2]["data"] == {"verifier": "stk-mupro-1", "status": "passed", "failed_checks": []}
    assert events[-1]["data"] == {"status": "succeeded"} and events[-1]["src"] == "launcher"
    assert kinds(events).count("metric.declare") == 5 and kinds(events).count("metrics") == 3
    assert len(frames(events)) == 30 and ("Polar", 2) in frames(events)
    assert [e["data"]["step"] for e in events if e["type"] == "progress"][-1] == 3
    assert {e["data"]["path"] for e in events if e["type"] == "frame"} == {f["path"] for f in record["frames"]}


def new_task(tmp_path, monkeypatch, name):
    """A fresh <task_dir>/work as CWD with STK_MONITOR_PATH=<task_dir>/events.jsonl, as the worker sets."""
    work = tmp_path / name / "work"
    work.mkdir(parents=True)
    monkeypatch.chdir(work)
    monkeypatch.setenv("STK_MONITOR_PATH", str(work.parent / "events.jsonl"))
    return work.parent / "events.jsonl"


@pytest.mark.server
def test_launcher_events_for_failures(node, tmp_path, monkeypatch):
    path = new_task(tmp_path, monkeypatch, "nan")
    code, record = launch(recording_sdk(tmp_path / "nan-sdk", mode="nan"), "--example")
    assert (code, record["classification"]) == (3, "invalid_result")
    events = events_of(path)
    assert events[-2]["data"] == {"verifier": "stk-mupro-1", "status": "failed",
                                  "failed_checks": ["completion", "energy", "progress", "frames"]}
    assert events[-1]["data"]["status"] == "failed" and events[-1]["data"]["classification"] == "invalid_result"
    assert any(e["type"] == "message" and e["data"]["code"] == "nonfinite_energy" for e in events)

    path = new_task(tmp_path, monkeypatch, "fail")
    code, record = launch(recording_sdk(tmp_path / "fail-sdk", mode="fail"), "--example")
    assert (code, record["classification"], record["exit_code"]) == (3, "solver_failed", 5)
    events = events_of(path)
    assert events[-2]["data"] == {"verifier": "stk-mupro-1", "status": "skipped", "failed_checks": []}
    assert events[-1]["data"] == {"status": "failed", "classification": "solver_failed", "reason": record["reason"]}
    assert frames(events)  # frames up to the last progress step are still published

    path = new_task(tmp_path, monkeypatch, "bound")
    code, record = launch(recording_sdk(tmp_path / "bound-sdk"), "--example", "--ranks", "5")  # refused before launch
    assert (code, record["classification"]) == (2, "configuration")
    assert [(e["type"], e["data"]["status"]) for e in events_of(path)] == [("run.completed", "failed")]


@pytest.mark.server
def test_launcher_publishes_while_the_solver_runs(node, tmp_path, monkeypatch):
    path = node.parent / "events.jsonl"
    monkeypatch.setenv("STK_MONITOR_PATH", str(path))
    monkeypatch.setattr(monitor_module, "POLL_INTERVAL", 0.05)
    sdk = recording_sdk(tmp_path / "sdk", wait_for="go")
    outcome = {}
    launcher = threading.Thread(target=lambda: outcome.update(code=main(["run", "--sdk-prefix", str(sdk), "--example"])))
    launcher.start()
    try:
        deadline = time.monotonic() + 30
        while True:
            events = events_of(path) if path.exists() else []
            if len(frames(events)) == 30 and "message" in kinds(events):
                break
            assert launcher.is_alive() and time.monotonic() < deadline, kinds(events)
            time.sleep(0.05)
        assert "run.completed" not in kinds(events) and "verification" not in kinds(events)
    finally:
        (node / "go").touch()
        launcher.join(30)
    assert outcome == {"code": 0}
    events = events_of(path)
    assert kinds(events)[-2:] == ["verification", "run.completed"] and len(frames(events)) == 30


@pytest.mark.server
def test_monitoring_problems_never_change_the_run(node, tmp_path, monkeypatch, capsys):
    from suan.monitor import tail
    monkeypatch.setattr(tail, "_REPORTED", set())  # adapter notes are printed once per process
    sdk = recording_sdk(tmp_path / "sdk")
    monkeypatch.setenv("STK_MONITOR_PATH", str(tmp_path / "missing" / "events.jsonl"))
    code, record = launch(sdk, "--example")
    assert code == 0 and record["state"] == "succeeded"
    assert "stk-monitor: monitoring disabled" in capsys.readouterr().err

    def broken(*args, **kwargs):
        raise RuntimeError("muFerro adapter test failure")

    for name in ("poll", "_poll_frames"):
        path = new_task(tmp_path, monkeypatch, name)
        with monkeypatch.context() as patch:
            patch.setattr(MuferroAdapter, name, broken)
            code, record = launch(sdk, "--example")
        assert code == 0 and record["state"] == "succeeded"
        assert kinds(events_of(path))[-1] == "run.completed"
    assert "adapter error: RuntimeError: muFerro adapter test failure" in capsys.readouterr().err


@pytest.mark.server
def test_unexpected_launcher_errors_kill_the_solver(node, tmp_path, monkeypatch):
    import psutil
    monkeypatch.setenv("STK_MONITOR_PATH", str(node.parent / "events.jsonl"))
    sdk = recording_sdk(tmp_path / "sdk", wait_for="never")
    children = []

    def solver(process):
        try:
            return str(sdk) in " ".join(process.cmdline())
        except psutil.Error:
            return False

    def watch(self):
        deadline = time.monotonic() + 10
        while not children and time.monotonic() < deadline:
            children.extend(filter(solver, psutil.Process().children()))
        raise RuntimeError("launcher bug")

    monkeypatch.setattr(MuferroMonitor, "watch", watch)
    started = time.monotonic()
    code, record = launch(sdk, "--example")
    assert time.monotonic() - started < 20
    assert (code, record["state"], record["reason"]) == (2, "failed", "RuntimeError: launcher bug")
    assert children and not any(child.is_running() and child.status() != psutil.STATUS_ZOMBIE for child in children)


def test_task_through_the_runtime_exposes_muferro_events(runtime, tmp_path, monkeypatch):
    for key in [*NODE_ENV, *(key for key in os.environ if key.startswith("I_MPI_"))]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PATH", os.defpath)
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(make_fake_sdk(tmp_path / "sdk")))
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace("muFerro events")["id"]
    task = client.submit(TaskSpec(**muferro_spec(workspace, example=True)))
    assert finish(client, supervisor, task["id"], timeout=60)["state"] == "succeeded"
    result = client.events(task["id"])
    assert result["terminal"] and result["invalid"] == [] and result["next_offset"] == result["size"]
    assert kinds(result["events"])[0] == "run.started" and kinds(result["events"])[-1] == "run.completed"
    assert len(frames(result["events"])) == 30
    assert client.task(task["id"])["monitor"]["last_progress"]["completed_steps"] == 3
