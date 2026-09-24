"""Monitoring events writer: disabled mode, ranks, seq recovery, coalescing, limits, never raising."""

import json
import math
import os
import subprocess
import sys

import pytest

from suan.monitor import emit as emit_module
from suan.monitor.emit import Emitter, detect_rank
from suan.monitor.events import MAX_LINE, MAX_TEXT, RANK_ENV, decode_line
from suan.monitor.reader import read_all


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def test_unset_path_or_other_rank_is_a_no_op(tmp_path):
    silent = Emitter(environ={})
    assert not silent.enabled and silent.error is None
    assert silent.started("app") is False and silent.progress(1, 2) is False and silent.metrics({"a": 1}) is False
    assert silent.completed() is False and silent.flush() is False
    silent.close()
    path = tmp_path / "events.jsonl"
    for name in RANK_ENV:
        other = Emitter(environ={"STK_MONITOR_PATH": str(path), name: "3"})
        assert not other.enabled and other.message("info", "x") is False
    assert not path.exists()
    # The first set variable wins, so a scheduler's rank 0 cannot hide an MPI rank.
    assert detect_rank({"PMI_RANK": "2", "SLURM_PROCID": "0"}) == 2
    assert detect_rank({"PMIX_RANK": " ", "OMPI_COMM_WORLD_RANK": "0", "SLURM_PROCID": "5"}) == 0
    assert detect_rank({"MV2_COMM_WORLD_RANK": "zero"}) == -1 and detect_rank({}) == 0
    assert not Emitter(environ={"STK_MONITOR_PATH": str(path), "PMI_RANK": "zero"}).enabled
    assert Emitter(environ={"STK_MONITOR_PATH": str(path), "SLURM_PROCID": "0"}).enabled
    # An explicit rank overrides the environment either way.
    assert Emitter(path, rank=0, environ={"PMI_RANK": "1"}).enabled
    assert not Emitter(path, rank=1, environ={}).enabled


def test_events_are_whole_lines_with_increasing_seq(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    monkeypatch.setenv("STK_MONITOR_PATH", str(path))
    monkeypatch.setenv("STK_MONITOR_FAKE_TIME", "1790000000.5")
    for name in RANK_ENV:
        monkeypatch.delenv(name, raising=False)
    with Emitter(src="adapter") as mon:
        assert mon.enabled and mon.path == str(path)
        assert mon.started("muFerro", total_steps=1000, ranks=4, host="node1", pid=42)
        assert mon.declare("total_energy", "normalized", label="Total Energy")
        assert mon.progress(step=120, total_steps=1000)
        assert mon.metrics({"total_energy": -1.4, "elastic_energy": math.nan}, step=120)
        assert mon.frame("Polar", 1000, "Polar.00001000.dat", reader="mupro.dat@1", components=3)
        assert mon.checkpoint(1000, "restart/Polar.in", restartable=True)
        assert mon.artifact("report.pdf", "report")
        assert mon.phase("solve", "end", elapsed_s=math.inf)
        assert mon.usage(cpu_s=2.5, rss_peak_bytes=1024)
        assert mon.verification("stk-mupro-1", "passed")
        assert mon.emit("x.custom", {"k": [1, 2]})
        assert mon.completed(True)
    assert (os.stat(path).st_mode & 0o777) == 0o600
    events = lines(path)
    assert [e["seq"] for e in events] == list(range(12))
    assert {e["ts"] for e in events} == {1790000000.5} and {e["src"] for e in events} == {"adapter"}
    assert events[0] == {"v": 1, "seq": 0, "ts": 1790000000.5, "type": "run.started", "src": "adapter",
                         "data": {"app": "muFerro", "total_steps": 1000, "ranks": 4, "host": "node1", "pid": 42}}
    assert events[3]["data"] == {"step": 120, "values": {"total_energy": -1.4, "elastic_energy": "NaN"}}
    assert events[7]["data"] == {"name": "solve", "state": "end", "elapsed_s": "Inf"}
    assert events[-1]["type"] == "run.completed" and events[-1]["data"] == {"status": "succeeded"}
    assert path.read_bytes().count(b"\n") == 12
    for raw in path.read_bytes().splitlines(keepends=True):
        decode_line(raw, strict=True)


def test_seq_continues_after_the_last_complete_line(tmp_path):
    path = tmp_path / "events.jsonl"
    with Emitter(path, environ={}) as first:
        for n in range(3):
            first.message("info", f"line {n}")
    assert Emitter(path, environ={}).seq == 3
    # A crashed writer's partial line is ended so the next events stay whole; readers report it.
    with open(path, "ab") as stream:
        stream.write(b'{"v":1,"seq":3,"ts":1,"type":"mess')
    with Emitter(path, environ={}) as second:
        assert second.seq == 3
        second.message("info", "after crash")
    result = read_all(path)
    assert [e["seq"] for e in result["events"]] == [0, 1, 2, 3]
    assert len(result["invalid"]) == 1 and result["next_offset"] == path.stat().st_size
    # Garbage after the last event does not reset seq; recovery scans past a large unreadable tail.
    with open(path, "ab") as stream:
        stream.write(b"not json\n" * 10000)
    assert Emitter(path, environ={}).seq == 4
    with open(path, "ab") as stream:
        stream.write(b"q" * 300_000 + b"\n" + b"r" * 200_000)  # huge lines, the last one unfinished
    assert emit_module.recover(path, path.stat().st_size) == (4, False)
    assert emit_module.recover(tmp_path / "unused", 0) == (0, True)
    (tmp_path / "garbage").write_bytes(b"x" * 100_000)
    assert emit_module.recover(tmp_path / "garbage", 100_000) == (0, False)


def test_progress_is_coalesced_and_the_final_value_is_always_written(tmp_path):
    path = tmp_path / "events.jsonl"
    clock = Clock()
    mon = Emitter(path, environ={}, clock=clock)
    assert mon.progress(1, 100)  # the first value is written
    clock.now += 0.2
    assert mon.progress(2, 100) and mon.progress(3, 100)  # accepted, pending
    mon.metrics({"e": 1.0}, step=3)  # other events are never held back and do not flush early
    clock.now += 0.9
    mon.metrics({"e": 2.0}, step=4)  # a pending value that is due goes out before the next event
    assert mon.progress(5, 100)
    assert mon.progress(completed_steps=100, total_steps=100)  # final: written at once
    clock.now += 0.1
    assert mon.progress(6, 100, fraction=math.nan)  # pending; a NaN fraction is dropped, not the event
    mon.close()  # flushes the pending value
    events = [(e["type"], e["data"].get("step"), e["data"].get("completed_steps")) for e in lines(path)]
    assert events == [("progress", 1, None), ("metrics", 3, None), ("progress", 3, None), ("metrics", 4, None),
                      ("progress", None, 100), ("progress", 6, None)]
    # run.completed always follows the latest progress value.
    path2 = tmp_path / "second.jsonl"
    mon = Emitter(path2, environ={}, clock=clock)
    mon.progress(1, 10)
    mon.progress(2, 10)
    mon.completed("failed", classification="numerical_failure", reason="NaN")
    assert [(e["type"], e["data"].get("step")) for e in lines(path2)] == [
        ("progress", 1), ("progress", 2), ("run.completed", None)]
    assert lines(path2)[-1]["data"] == {"status": "failed", "classification": "numerical_failure", "reason": "NaN"}


def test_line_cap_truncates_messages_and_drops_other_events(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    mon = Emitter(path, environ={})
    assert mon.message("warning", "x" * 20000, code="long")
    assert mon.message("error", "中文" * 3000)  # 18000 bytes of text: truncated to fit the line
    assert mon.message("info", "\x01" * 8000)  # control characters expand six-fold when escaped
    assert not mon.emit("x.big", {"blob": "y" * MAX_LINE})
    assert not mon.metrics({f"m{n}": 1.0 for n in range(2000)})
    assert mon.message("info", "still enabled")
    mon.close()
    events = lines(path)
    assert [e["data"]["text"][-1:] for e in events[:3]] == ["…"] * 3
    assert len(events[0]["data"]["text"]) == MAX_TEXT
    # Truncation keeps nearly a full line of text, whatever the characters' encoded size.
    assert len(events[1]["data"]["text"]) > (MAX_LINE - 200) // 3
    assert len(events[2]["data"]["text"]) > (MAX_LINE - 200) // 6
    assert all(len(raw) + 1 <= MAX_LINE for raw in path.read_bytes().splitlines())
    assert events[-1]["data"]["text"] == "still enabled" and [e["seq"] for e in events] == [0, 1, 2, 3]
    err = capsys.readouterr().err
    assert "dropped x.big event" in err and "dropped metrics event" in err


def test_invalid_events_are_dropped_and_never_raise(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    mon = Emitter(path, environ={})
    assert not mon.metrics(None)
    assert not mon.metrics({"a": object()})
    assert not mon.metrics({})
    assert not mon.declare("bad name", "1")
    assert not mon.frame("Polar", 1, "../escape.dat")
    assert not mon.message("fatal", "x")
    assert not mon.emit("unknown.type", {})
    assert not mon.completed("done")
    assert not mon.verification("v", "passed", failed_checks=5)
    assert mon.enabled and mon.message("info", "ok")
    mon.close()
    assert [e["seq"] for e in lines(path)] == [0]
    assert "stk-monitor: dropped" in capsys.readouterr().err


def test_io_errors_disable_the_emitter_once(tmp_path, monkeypatch, capsys):
    missing = Emitter(tmp_path / "no-such-dir" / "events.jsonl", environ={})
    assert not missing.enabled and "FileNotFoundError" in missing.error
    assert missing.message("info", "x") is False
    directory = Emitter(tmp_path, environ={})
    assert not directory.enabled and directory.error
    if hasattr(os, "mkfifo"):
        os.mkfifo(tmp_path / "fifo")
        fifo = Emitter(tmp_path / "fifo", environ={})  # must not block
        assert not fifo.enabled
    path = tmp_path / "events.jsonl"
    mon = Emitter(path, environ={})
    assert mon.message("info", "before")

    def failing(fd, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Emitter, "_write", staticmethod(failing))
    assert mon.message("info", "lost") is False
    assert not mon.enabled and "No space left" in mon.error
    assert mon.message("info", "after") is False and mon.progress(1, 2) is False
    mon.close()
    err = capsys.readouterr().err
    assert err.count("monitoring disabled") == 3 + hasattr(os, "mkfifo")
    monkeypatch.undo()
    assert [e["data"]["text"] for e in lines(path)] == ["before"]


def test_partial_writes_are_completed(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    mon = Emitter(path, environ={})
    real = os.write
    monkeypatch.setattr(emit_module.os, "write", lambda fd, data: real(fd, bytes(data[:7])))
    assert mon.message("info", "written in pieces")
    monkeypatch.undo()
    mon.close()
    assert lines(path)[0]["data"]["text"] == "written in pieces"


def test_emitter_is_standard_library_only(tmp_path):
    code = ("import sys; import suan.monitor.emit, suan.monitor.reader, suan.monitor.tail; "
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in {'numpy', 'psutil', 'suan'} "
            "and not m.startswith('suan.monitor') and m != 'suan'); print(bad); assert not bad")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=tmp_path,
                   env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})


def test_threads_share_one_emitter_without_interleaving(tmp_path):
    import threading
    path = tmp_path / "events.jsonl"
    mon = Emitter(path, environ={})

    def work(n):
        for step in range(200):
            mon.metrics({f"t{n}": float(step)}, step=step)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    mon.close()
    events = lines(path)
    assert len(events) == 800 and [e["seq"] for e in events] == list(range(800))
