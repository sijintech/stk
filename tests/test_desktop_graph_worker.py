"""Local graph process isolation, cancellation, recovery and private-pipe hygiene."""
from concurrent.futures import ThreadPoolExecutor
import os
import sys
import threading
import time

import pytest

from suan.desktop_bridge.graph_worker import GraphWorker
from suan.desktop_bridge.protocol import BridgeError
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.fixture
def worker_command(tmp_path):
    # Exercise the real worker transport with deterministic slow/crashing native-work stand-ins.
    script = tmp_path / "worker.py"
    script.write_text('''
import os
import subprocess
import sys
import threading
from suan.desktop_bridge import graph_worker_main as worker
from suan.desktop_bridge.protocol import BridgeError

count = 0
def evaluate(params, cache_dir, progress, cancel):
    global count
    count += 1
    progress({"type": "progress", "pid": os.getpid()})
    mode = params["request"].get("parameters", {}).get("mode", "ok")
    if mode == "block":
        threading.Event().wait(120)
    if mode == "cooperative":
        while not cancel.cancelled:
            threading.Event().wait(0.01)
        raise BridgeError("cancelled", "cancelled in worker")
    if mode == "descendant":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                 stdin=subprocess.DEVNULL, start_new_session=os.name == "posix")
        progress({"type": "progress", "child_pid": child.pid})
        threading.Event().wait(120)
    if mode == "crash":
        os._exit(17)
    if mode == "error":
        raise BridgeError("graph_error", "test error", data={"graph_code": "test_error"})
    print("stray Python output")
    os.write(1, b"stray native output\\n")
    subprocess.run([sys.executable, "-c", "import sys; assert sys.stdin.read() == ''; print('child output')"],
                   check=True)
    return {"pid": os.getpid(), "count": count}

worker.evaluate = evaluate
worker.main()
''', encoding="utf-8", newline="\n")
    return [sys.executable, str(script), "--cache-dir", str(tmp_path / "cache")]


@pytest.fixture
def worker(tmp_path, worker_command):
    instance = GraphWorker(tmp_path / "cache", command=worker_command)
    yield instance
    instance.close()


def work(mode="ok"):
    return {"request": {"preset": "slice", "parameters": {"mode": mode}}}


def test_reuses_process_and_preserves_errors_and_protocol_hygiene(worker):
    events = []
    first = worker.evaluate("one", work(), threading.Event(), events.append)
    assert first["pid"] != os.getpid() and first["count"] == 1
    with pytest.raises(BridgeError) as error:
        worker.evaluate("error", work("error"), threading.Event(), events.append)
    assert error.value.code == "graph_error"
    assert error.value.data == {"graph_code": "test_error"}
    again = worker.evaluate("two", work(), threading.Event(), events.append)
    assert again == {"pid": first["pid"], "count": 3}
    assert len(events) == 3 and {event["pid"] for event in events} == {first["pid"]}


def test_queued_cancel_leaves_active_work_then_active_cancel_reaps_and_restarts(worker):
    active_cancel, queued_cancel, started = threading.Event(), threading.Event(), threading.Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(worker.evaluate, "active", work("block"), active_cancel, lambda event: started.set())
        try:
            assert started.wait(10)
            child = worker._child
            queued = pool.submit(worker.evaluate, "queued", work(), queued_cancel, lambda event: None)
            queued_cancel.set()
            with pytest.raises(BridgeError, match="cancelled"):
                queued.result(timeout=5)
            assert child.process.poll() is None and not active.done()
            active_cancel.set()
            with pytest.raises(BridgeError, match="cancelled"):
                active.result(timeout=5)
            assert child.process.poll() is not None
            assert not child.reader.is_alive() and not child.writer.is_alive()
            again = worker.evaluate("after", work(), threading.Event(), lambda event: None)
            assert again["pid"] != child.process.pid and again["count"] == 1
        finally:
            worker.close()


def test_crash_fails_once_without_replay_and_next_request_starts_fresh(worker):
    events = []
    with pytest.raises(BridgeError) as error:
        worker.evaluate("crash", work("crash"), threading.Event(), events.append)
    assert error.value.code == "unavailable" and error.value.retryable
    assert len(events) == 1 and worker._child is None
    after = worker.evaluate("next", work(), threading.Event(), events.append)
    assert after["count"] == 1 and after["pid"] != events[0]["pid"]


def test_cooperative_cancel_preserves_the_warm_worker(worker):
    started, cancel = threading.Event(), threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(worker.evaluate, "active", work("cooperative"), cancel, lambda event: started.set())
        try:
            assert started.wait(10)
            child = worker._child
            cancel.set()
            with pytest.raises(BridgeError) as error:
                active.result(timeout=5)
            assert error.value.code == "cancelled" and child.process.poll() is None
            again = worker.evaluate("next", work(), threading.Event(), lambda event: None)
            assert again == {"pid": child.process.pid, "count": 2}
        finally:
            worker.close()


def test_hard_cancel_stops_render_descendants_in_other_sessions(worker):
    import psutil
    started, cancel, events = threading.Event(), threading.Event(), []

    def progress(event):
        if "child_pid" in event:
            events.append(event)
            started.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(worker.evaluate, "tree", work("descendant"), cancel, progress)
        try:
            assert started.wait(10)
            descendant = psutil.Process(events[0]["child_pid"])
            cancel.set()
            with pytest.raises(BridgeError) as error:
                active.result(timeout=5)
            assert error.value.code == "cancelled"
            assert not descendant.is_running() or descendant.status() == psutil.STATUS_ZOMBIE
        finally:
            worker.close()


def test_cancel_during_a_blocked_request_write(tmp_path):
    instance = GraphWorker(tmp_path, command=[sys.executable, "-c", "import time; time.sleep(60)"])
    cancel = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(instance.evaluate, "blocked-write", {"padding": "x" * (1024 * 1024)},
                             cancel, lambda event: None)
        try:
            deadline = time.monotonic() + 5
            while instance._child is None:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            child = instance._child
            cancel.set()
            with pytest.raises(BridgeError) as error:
                active.result(timeout=5)
            assert error.value.code == "cancelled"
            assert child.process.poll() is not None
            assert not child.writer.is_alive() and not child.reader.is_alive()
        finally:
            instance.close()


def test_shutdown_reaps_busy_worker_and_refuses_new_work(worker):
    started = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(worker.evaluate, "active", work("block"), threading.Event(),
                             lambda event: started.set())
        try:
            assert started.wait(10)
            child = worker._child
        finally:
            worker.close()
        with pytest.raises(BridgeError) as error:
            active.result(timeout=5)
        assert error.value.code == "shutting_down"
        assert child.process.poll() is not None
        assert not child.reader.is_alive() and not child.writer.is_alive()
    worker.close()
    with pytest.raises(BridgeError) as error:
        worker.evaluate("closed", work(), threading.Event(), lambda event: None)
    assert error.value.code == "shutting_down"


@pytest.mark.parametrize("output", ["{}\n", "not-json\n", "x" * 256 + "\n"])
def test_bad_worker_output_is_bounded_and_reaped(tmp_path, monkeypatch, output):
    import suan.desktop_bridge.graph_worker as module
    monkeypatch.setattr(module, "MAX_LINE_BYTES", 128)
    script = tmp_path / "bad.py"
    script.write_text(f"import sys, time\nsys.stdout.write({output!r}); sys.stdout.flush(); time.sleep(60)\n",
                      encoding="utf-8", newline="\n")
    instance = GraphWorker(tmp_path, command=[sys.executable, str(script)])
    try:
        with pytest.raises(BridgeError) as error:
            instance.evaluate("one", {}, threading.Event(), lambda event: None)
        assert error.value.code == "unavailable"
        assert instance._child is None
    finally:
        instance.close()


def test_bridge_remains_responsive_and_duplicate_eval_ids_are_rejected(inproc, worker_command):  # noqa: F811
    harness = inproc()
    harness.bridge.graphs.worker.close()
    harness.bridge.graphs.worker = GraphWorker(harness.bridge.cache_dir, command=worker_command)
    params = {"eval_id": "slow", **work("block")}
    pending = harness.request("graph.evaluate", params)
    harness.wait_event(lambda e: e["event"] == "graph.progress" and e["data"]["eval_id"] == "slow")
    child = harness.bridge.graphs.worker._child
    assert harness.call("hello", {"protocol": 1}, timeout=5)["protocol"] == 1
    assert harness.error("graph.evaluate", params, timeout=5)["code"] == "conflict"
    assert harness.call("graph.cancel", {"eval_id": "slow"}, timeout=5) == {"cancelled": True}
    assert harness.response(pending, timeout=5)["error"]["code"] == "cancelled"
    assert child.process.poll() is not None
    harness.close()


def test_eof_reaps_even_a_busy_worker(worker_command):
    import subprocess
    from suan.desktop_bridge.protocol import decode_line, encode_message
    process = subprocess.Popen(worker_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        process.stdin.write(encode_message({"id": "busy", "params": work("block")}))
        process.stdin.flush()
        assert decode_line(process.stdout.readline())["event"]["pid"] == process.pid
        process.stdin.close()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


def test_real_worker_reads_runtime_binding_and_exports_verified_blob(runtime, inproc, tmp_path):  # noqa: F811
    import hashlib
    import io
    from pathlib import Path
    from conftest import finish
    from test_desktop_bridge_runtime import add_profile, CONNECTION

    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    client, supervisor, _, config = runtime
    source = tmp_path / "field.npy"
    values = np.arange(24, dtype=np.float64).reshape(2, 3, 4)
    np.save(source, values)
    workspace = client.create_workspace("worker binding")["id"]
    client.upload(workspace, source)
    task = client.submit({"workspace_id": workspace, "argv": ["{python}", "-c", "pass"],
                          "outputs": ["field.npy"]})["id"]
    assert finish(client, supervisor, task)["state"] == "succeeded"
    harness = inproc()
    add_profile(harness, runtime)
    graph = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "src", "type": "stk.source.file@1", "params": {"binding": "data", "path": "field.npy"}},
        {"id": "exp", "type": "stk.output.dataset@1", "inputs": {"in": {"from": "src.out"}},
         "params": {"format": "npy"}}], "outputs": {"export": "exp.file"}}
    result = harness.call("graph.evaluate", {"eval_id": "runtime", "connection": CONNECTION,
                          "request": {"graph": graph, "bindings": {"data": {"task_id": task}}}})
    digest = result["result"]["outputs"]["export"]["blob"]
    blob = (Path(result["blob_dir"]) / digest[:2] / digest).read_bytes()
    assert hashlib.sha256(blob).hexdigest() == digest
    assert np.array_equal(np.load(io.BytesIO(blob), allow_pickle=False), values)
    assert config["token"] not in harness.output_text()
    assert config["token"] not in " ".join(harness.bridge.graphs.worker.command)
    harness.close()


def test_worker_exits_when_the_bridge_is_killed(bridge_env):  # noqa: F811
    import psutil
    from test_desktop_bridge import ProcessBridge

    harness = ProcessBridge(bridge_env / "process")
    try:
        error = harness.error("graph.evaluate", {"eval_id": "warm", "request": {"preset": "no-such"}})
        assert error["code"] == "graph_error"
        children = [p for p in psutil.Process(harness.process.pid).children()
                    if "suan.desktop_bridge.graph_worker_main" in p.cmdline()]
        assert len(children) == 1
        worker = children[0]
        harness.kill()
        deadline = time.monotonic() + 5
        while worker.is_running() and worker.status() != psutil.STATUS_ZOMBIE:
            assert time.monotonic() < deadline, "worker survived bridge EOF"
            time.sleep(0.02)
    finally:
        if harness.process.poll() is None:
            harness.kill()


def test_worker_start_failure_is_retryable_and_does_not_hold_the_lane(tmp_path):
    instance = GraphWorker(tmp_path, command=[str(tmp_path / "missing-python")])
    try:
        for identity in ("first", "second"):
            with pytest.raises(BridgeError) as error:
                instance.evaluate(identity, {}, threading.Event(), lambda event: None)
            assert error.value.code == "unavailable" and error.value.retryable
    finally:
        instance.close()
