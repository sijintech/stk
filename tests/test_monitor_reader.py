"""Monitoring events reader (offsets, whole lines, invalid lines) and the legacy-adapter tail framework."""

import json
import os
import re
import threading
import time

import pytest

from suan.monitor.emit import Emitter
from suan.monitor.events import MAX_LINE, READ_LIMIT, encode_line, make_event
from suan.monitor.reader import monitor_summary, read_all, read_events
from suan.monitor import tail as tail_module
from suan.monitor.tail import LineTail, PollThread, StableFiles


def write_events(path, count, start=0):
    with Emitter(path, environ={}) as mon:
        for n in range(start, start + count):
            mon.metrics({"e": float(n)}, step=n)
    return path.read_bytes()


def test_missing_file_and_range_checks(tmp_path):
    path = tmp_path / "events.jsonl"
    assert read_events(path) == {"events": [], "offset": 0, "next_offset": 0, "size": 0, "invalid": []}
    assert read_events(path, 5)["next_offset"] == 5  # like logs(): nothing to read yet
    write_events(path, 2)
    for offset, limit in [(-1, 10), (0, 0), (0, READ_LIMIT + 1), (True, 10), (0, 1.5), ("0", 10)]:
        with pytest.raises(ValueError, match="Invalid events range"):
            read_events(path, offset, limit)
    with pytest.raises(ValueError, match="exceeds"):
        read_events(path, path.stat().st_size + 1)
    size = path.stat().st_size
    assert read_events(path, size) == {"events": [], "offset": size, "next_offset": size, "size": size, "invalid": []}


def test_offsets_return_whole_lines_only(tmp_path):
    path = tmp_path / "events.jsonl"
    data = write_events(path, 10)
    ends = [n + 1 for n, byte in enumerate(data) if byte == ord("\n")]
    first = read_events(path, 0, ends[2] + 5)  # three whole lines and part of the fourth
    assert [e["seq"] for e in first["events"]] == [0, 1, 2] and first["next_offset"] == ends[2]
    assert first["size"] == len(data) and first["invalid"] == []
    second = read_events(path, first["next_offset"], ends[3] - ends[2])  # exactly one line
    assert [e["seq"] for e in second["events"]] == [3] and second["next_offset"] == ends[3]
    # A limit smaller than the next line still returns that line alone, so readers make progress.
    third = read_events(path, second["next_offset"], 1)
    assert [e["seq"] for e in third["events"]] == [4] and third["next_offset"] == ends[4]
    rest = read_all(path, third["next_offset"])
    assert [e["seq"] for e in rest["events"]] == [5, 6, 7, 8, 9] and rest["next_offset"] == len(data)
    assert rest["events"][0] == {"v": 1, "seq": 5, "ts": rest["events"][0]["ts"], "type": "metrics",
                                 "src": "program", "data": {"step": 5, "values": {"e": 5.0}}}


def test_a_line_being_written_waits(tmp_path):
    path = tmp_path / "events.jsonl"
    write_events(path, 1)
    size = path.stat().st_size
    line = encode_line(make_event(1, "progress", {"step": 3}, "program", 1.0))
    with open(path, "ab") as stream:
        stream.write(line[:20])
    result = read_events(path)
    assert len(result["events"]) == 1 and result["next_offset"] == size and result["invalid"] == []
    assert read_events(path, size, 5)["next_offset"] == size  # incomplete, however small the limit
    with open(path, "ab") as stream:
        stream.write(line[20:])
    result = read_events(path, size)
    assert result["events"][0]["data"] == {"step": 3} and result["next_offset"] == path.stat().st_size


def test_invalid_and_oversized_lines_are_skipped_and_reported(tmp_path):
    path = tmp_path / "events.jsonl"
    good = [encode_line(make_event(n, "message", {"level": "info", "text": str(n)}, "program", 1.0)) for n in range(4)]
    future = encode_line({"v": 1, "seq": 9, "ts": 1.0, "type": "run.heartbeat", "src": "program", "data": {}})
    oversized = b'{"pad":"' + b"x" * MAX_LINE + b'"}\n'
    newer = b'{"v":2,"seq":0,"ts":1,"type":"progress","src":"program","data":{}}\n'
    body = [good[0], b"garbage\n", good[1], oversized, good[2], newer, future, b"\xff\xfe\n", good[3]]
    path.write_bytes(b"".join(body))
    offsets = [sum(len(part) for part in body[:n]) for n in range(len(body))]
    result = read_events(path)
    assert [e["data"].get("text") for e in result["events"]] == ["0", "1", "2", None, "3"]
    assert result["events"][3]["type"] == "run.heartbeat"  # a newer writer's type is passed on
    assert [item["offset"] for item in result["invalid"]] == [offsets[1], offsets[3], offsets[5], offsets[7]]
    assert "exceeds" in result["invalid"][1]["reason"] and "version" in result["invalid"][2]["reason"]
    assert result["next_offset"] == path.stat().st_size
    # With a small limit the oversized line is skipped on its own and reading continues after it.
    skipped = read_events(path, offsets[3], 100)
    assert skipped["events"] == []
    assert skipped["invalid"] == [{"offset": offsets[3], "reason": f"Line exceeds {MAX_LINE} bytes"}]
    assert skipped["next_offset"] == offsets[4]
    assert read_events(path, offsets[4], 100)["events"][0]["data"]["text"] == "2"


def test_an_oversized_line_is_skipped_once_it_ends(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"y" * (3 * MAX_LINE))
    for limit in (10, READ_LIMIT):
        result = read_events(path, 0, limit)
        assert result["events"] == [] and result["invalid"] == [] and result["next_offset"] == 0
    with open(path, "ab") as stream:
        stream.write(b"\n" + encode_line(make_event(0, "progress", {}, "program", 1.0)))
    for limit in (10, READ_LIMIT):
        result = read_events(path, 0, limit)
        assert result["invalid"] == [{"offset": 0, "reason": f"Line exceeds {MAX_LINE} bytes"}]
    assert result["next_offset"] == path.stat().st_size and [e["type"] for e in result["events"]] == ["progress"]
    small = read_events(path, 0, 10)
    assert small["events"] == [] and small["next_offset"] == 3 * MAX_LINE + 1
    assert [e["type"] for e in read_all(path)["events"]] == ["progress"]


def test_skipping_a_huge_line_is_bounded_per_call(tmp_path, monkeypatch):
    from suan.monitor import reader
    monkeypatch.setattr(reader, "SCAN_LIMIT", 100_000)
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"z" * 350_000 + b"\n" + encode_line(make_event(0, "progress", {"step": 1}, "program", 1.0)))
    offsets, events = [0], []
    while offsets[-1] < path.stat().st_size:
        result = read_events(path, offsets[-1], 10)
        assert result["next_offset"] > offsets[-1] and result["next_offset"] - offsets[-1] <= 100_000 + 2 * MAX_LINE
        assert [item["offset"] for item in result["invalid"]] in ([offsets[-1]], [])
        events += result["events"]
        offsets.append(result["next_offset"])
    assert [e["data"] for e in events] == [{"step": 1}] and len(offsets) > 4


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks and FIFOs")
def test_only_regular_files_are_read(tmp_path):
    target = tmp_path / "secret.json"
    target.write_text('{"token": "x"}\n')
    link = tmp_path / "events.jsonl"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        read_events(link)
    fifo = tmp_path / "fifo.jsonl"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular file"):
        read_events(fifo)  # returns at once instead of waiting for a writer
    with pytest.raises(ValueError):
        monitor_summary(link)


def test_monitor_summary_reads_the_tail(tmp_path):
    path = tmp_path / "events.jsonl"
    assert monitor_summary(path) is None
    with Emitter(path, environ={"STK_MONITOR_FAKE_TIME": "1790000000.25"}) as mon:
        mon.progress(4, 10)
        mon.metrics({"e": 1.0}, step=4)
    assert monitor_summary(path) == {"events_size": path.stat().st_size, "last_progress": {"step": 4, "total_steps": 10},
                                     "last_ts": 1790000000.25}
    # Only the last 64 KiB are read: a progress event before them is not reported.
    with Emitter(path, environ={"STK_MONITOR_FAKE_TIME": "1790000001"}) as mon:
        for n in range(1000):
            mon.metrics({"e": float(n)}, step=n)
    with open(path, "ab") as stream:
        stream.write(b'{"partial')
    summary = monitor_summary(path)
    assert summary == {"events_size": path.stat().st_size, "last_progress": None, "last_ts": 1790000001}


def test_line_tail_returns_new_complete_lines(tmp_path):
    path = tmp_path / "native.log"
    tail = LineTail(path)
    assert tail.poll() == []
    path.write_bytes(b"one\ntwo\nthr")
    assert tail.poll() == ["one", "two"] and tail.line_number == 2
    assert tail.poll() == []
    with open(path, "ab") as stream:
        stream.write(b"ee\r\nfour\n")
    assert tail.poll() == ["three", "four"] and tail.line_number == 4
    path.write_bytes(b"new\n")  # replaced by a shorter file: start again
    assert tail.poll() == ["new"] and tail.restarts == 1 and tail.line_number == 1
    small = LineTail(path, max_line=8)
    path.write_bytes(b"x" * 20)
    assert small.poll() == []
    with open(path, "ab") as stream:
        stream.write(b"xx\nok\n")
    assert small.poll() == ["ok"]  # the oversized line is dropped, the next one kept
    chunked = LineTail(path)
    path.write_bytes(b"".join(b"%d\n" % n for n in range(100)))
    assert chunked.poll(max_bytes=50)[:2] == ["0", "1"] and chunked.drain()[-1] == "99"


def test_stable_files_need_unchanged_size_over_polls(tmp_path):
    pattern = re.compile(r"^(\w+)\.(\d{8})\.dat$")
    files = StableFiles(tmp_path, pattern, polls=2)
    frame = tmp_path / "Polar.00000001.dat"
    frame.write_text("a")
    (tmp_path / "notes.txt").write_text("ignored")
    assert files.candidates() == []  # seen once
    names = [(name, size) for name, _, size in files.candidates()]
    assert names == [("Polar.00000001.dat", 1)]
    frame.write_text("abc")  # still growing: stability starts again
    assert files.candidates() == []
    assert [name for name, _, _ in files.candidates()] == ["Polar.00000001.dat"]
    files.publish("Polar.00000001.dat")
    assert files.candidates() == [] and files.candidates(force=True) == []
    (tmp_path / "Strain.00000002.dat").write_text("s")
    assert [(name, match[1], int(match[2])) for name, match, _ in files.candidates(force=True)] == [
        ("Strain.00000002.dat", "Strain", 2)]
    (tmp_path / "sub.00000003.dat").mkdir()
    assert all(name != "sub.00000003.dat" for name, _, _ in files.candidates(force=True))
    assert StableFiles(tmp_path / "missing", pattern).candidates(force=True) == []


def test_poll_thread_runs_until_stopped_and_contains_errors(capsys, monkeypatch):
    monkeypatch.setattr(tail_module, "_REPORTED", set())  # notes are printed once per process
    calls = []

    def poll():
        calls.append(time.monotonic())
        if len(calls) == 2:
            raise RuntimeError("adapter bug")

    thread = PollThread(poll, 0.01).start()
    deadline = time.monotonic() + 5
    while len(calls) < 4 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert thread.stop() is True
    count = len(calls)
    time.sleep(0.05)
    assert len(calls) == count >= 4
    assert "adapter error: RuntimeError: adapter bug" in capsys.readouterr().err
    blocked = threading.Event()
    stuck = PollThread(lambda: blocked.wait(5), 0.001).start()
    time.sleep(0.05)
    assert stuck.stop(timeout=0.05) is False
    blocked.set()
    assert stuck.stop() is True
