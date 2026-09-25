"""Desktop bridge against a loopback STK Runtime: transfers, idempotent submit, logs, events, lifecycle.

Uses the in-process Runtime fixture of the Runtime tests (``conftest.runtime``, bound to
127.0.0.1); the Runtime is Linux-only, so these tests are marked ``server`` automatically.
"""
import hashlib
import os
from pathlib import Path
import random
import sys
import threading
import time

from conftest import finish
from test_desktop_bridge import ProcessBridge, bridge_env, inproc  # noqa: F401,F811 (fixtures)

MiB = 1024 * 1024
CONNECTION = "runtime:rt"


def add_profile(harness, runtime):
    client, _, _, config = runtime
    added = harness.call("connections.add_runtime", {"name": "rt", "url": client.url, "token": config["token"]})
    assert added["connection"]["id"] == CONNECTION
    return CONNECTION


def gated_uploads(server, block_from):
    """Patch the Runtime so upload chunks at offsets >= block_from wait for ``gate``; records offsets."""
    gate, offsets = threading.Event(), []
    original = server.service.upload_chunk

    def upload_chunk(workspace_id, upload_id, offset, body):
        offsets.append(offset)
        if offset >= block_from:
            gate.wait(60)
        return original(workspace_id, upload_id, offset, body)
    server.service.upload_chunk = upload_chunk
    return gate, offsets


def wait_for(predicate, timeout=30, what="condition"):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.02)


def test_upload_resumes_after_a_bridge_restart(runtime, bridge_env, tmp_path):  # noqa: F811
    client, _, server, config = runtime
    workspace = client.create_workspace("上传续传")["id"]
    data = random.Random(7).randbytes(5 * MiB + 123)
    source = tmp_path / "输入数据.bin"
    source.write_bytes(data)
    gate, offsets = gated_uploads(server, block_from=2 * MiB)
    state = bridge_env / "bridge"
    first = ProcessBridge(state)
    try:
        first.call("hello", {"protocol": 1})
        add_profile(first, runtime)
        transfer = first.call("upload.start", {"connection": CONNECTION, "workspace_id": workspace,
                                               "source": str(source), "remote": "data/输入数据.bin"})["transfer"]
        assert transfer["kind"] == "upload" and transfer["bytes_total"] == len(data) and transfer["files_total"] == 1
        wait_for(lambda: 2 * MiB in offsets, what="the third chunk")
        # The bridge dies (crash or closed app) in the middle of the upload.
        first.kill()
    finally:
        gate.set()
    before = len(offsets)
    second = ProcessBridge(state)
    hello = second.call("hello", {"protocol": 1})
    assert hello["resumed_transfers"] == [transfer["id"]]
    done = second.wait_transfer(transfer["id"])
    assert done["state"] == "completed", done
    assert done["bytes_done"] == len(data) and done["files_done"] == 1
    resumed = offsets[before:]
    assert resumed and 0 not in resumed and resumed[0] >= 2 * MiB  # continued, not restarted
    files = client.files(workspace)
    assert [(f["path"], f["sha256"]) for f in files] == [("data/输入数据.bin", hashlib.sha256(data).hexdigest())]
    assert second.call("transfer.get", {"id": transfer["id"]})["transfer"]["state"] == "completed"
    assert second.close() == 0
    assert config["token"] not in first.output_text() + second.output_text()


def test_upload_folders_cancel_and_workspace_files(runtime, inproc, tmp_path):  # noqa: F811
    client, _, server, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    workspace = harness.call("workspace.create", {"connection": CONNECTION, "name": "输入", "idempotency_key": "w"})
    workspace = workspace["workspace"]["id"]
    folder = tmp_path / "case"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "b.txt").write_text("乙", encoding="utf-8", newline="\n")
    (folder / "c.toml").write_text("x = 1\n", encoding="utf-8", newline="\n")
    if os.name == "posix":
        (folder / "link.txt").symlink_to(folder / "c.toml")  # links are never followed
    transfer = harness.call("upload.start", {"connection": CONNECTION, "workspace_id": workspace,
                                             "source": str(folder)})["transfer"]
    assert harness.wait_transfer(transfer["id"])["state"] == "completed"
    files = harness.call("workspace.files", {"connection": CONNECTION, "workspace_id": workspace})["files"]
    assert [f["path"] for f in files] == ["case/c.toml", "case/sub/b.txt"]
    # Cancelling aborts the Runtime's upload session, so it cannot block submissions.
    big = tmp_path / "big.bin"
    big.write_bytes(b"z" * (3 * MiB))
    gate, offsets = gated_uploads(server, block_from=MiB)
    try:
        transfer = harness.call("upload.start", {"connection": CONNECTION, "workspace_id": workspace,
                                                 "source": str(big)})["transfer"]
        wait_for(lambda: MiB in offsets, what="the second chunk")
        request = harness.request("transfer.cancel", {"id": transfer["id"]})
    finally:
        gate.set()
    assert harness.response(request)["result"]["transfer"]["state"] == "cancelled"
    uploads = server.service.workspace_dir(workspace) / "uploads"
    assert not [p for p in uploads.glob("*.json") if "big.bin" in p.read_text(encoding="utf-8")]
    spec = {"workspace_id": workspace, "argv": ["{python}", "-c", "pass"]}
    assert harness.call("task.submit", {"connection": CONNECTION, "idempotency_key": "after-cancel",
                                        "spec": spec})["task"]["state"] == "queued"
    error = harness.error("upload.start", {"connection": CONNECTION, "workspace_id": workspace,
                                           "source": "relative/path"})
    assert error["code"] == "invalid_params"
    assert harness.error("transfer.get", {"id": "f" * 32})["code"] == "not_found"
    listed = harness.call("transfer.list")["transfers"]
    assert {t["state"] for t in listed} == {"completed", "cancelled"}
    harness.close()


def test_a_source_changed_while_uploading_is_rejected_then_retried(runtime, inproc, tmp_path):  # noqa: F811
    client, _, server, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    workspace = client.create_workspace("改动")["id"]
    source = tmp_path / "changing.bin"
    source.write_bytes(b"a" * (3 * MiB))
    gate, offsets = gated_uploads(server, block_from=MiB)
    try:
        transfer = harness.call("upload.start", {"connection": CONNECTION, "workspace_id": workspace,
                                                 "source": str(source)})["transfer"]
        wait_for(lambda: MiB in offsets, what="the second chunk")
        source.write_bytes(b"b" * (3 * MiB))  # same size, new content: the third chunk reads it
    finally:
        gate.set()
    failed = harness.wait_transfer(transfer["id"])
    assert failed["state"] == "failed" and failed["error"]["code"] == "checksum_mismatch"
    assert client.files(workspace) == []
    mark = harness.mark()
    harness.call("transfer.resume", {"id": transfer["id"]})
    assert harness.wait_transfer(transfer["id"], start=mark)["state"] == "completed"
    assert client.files(workspace)[0]["sha256"] == hashlib.sha256(b"b" * (3 * MiB)).hexdigest()
    harness.close()


def test_submit_is_idempotent_across_bridge_restarts(runtime, inproc):  # noqa: F811
    client, supervisor, _, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    created = [harness.call("workspace.create", {"connection": CONNECTION, "name": "幂等", "idempotency_key": "ws-1"})
               for _ in range(2)]
    assert created[0]["workspace"]["id"] == created[1]["workspace"]["id"]
    workspace = created[0]["workspace"]["id"]
    spec = {"workspace_id": workspace, "argv": ["{python}", "-c", "print('一次')"], "name": "一次",
            "resources": {"cpus": 1, "walltime_seconds": 60}}
    params = {"connection": CONNECTION, "idempotency_key": "submit-1", "spec": spec}
    # Concurrent retries of the same submission name one task.
    requests = [harness.request("task.submit", params) for _ in range(4)]
    ids = {harness.response(r)["result"]["task"]["id"] for r in requests}
    assert len(ids) == 1
    task_id = ids.pop()
    changed = {**params, "spec": {**spec, "argv": ["{python}", "-c", "print('二次')"]}}
    error = harness.error("task.submit", changed)
    assert error["code"] == "conflict" and "different task" in error["message"]
    error = harness.error("task.submit", {**params, "idempotency_key": "bad", "spec": {**spec, "argv": "echo hi"}})
    assert error["code"] == "invalid_params"
    harness.close()
    restarted = inproc()  # same state directory: a new bridge after a crash
    assert restarted.call("task.submit", params)["task"]["id"] == task_id
    assert len(client.tasks()) == 1
    watch = restarted.call("watch", {"connection": CONNECTION, "workspace_id": workspace})["sub"]
    assert finish(client, supervisor, task_id)["state"] == "succeeded"
    snapshot = restarted.wait_event(lambda e: e["event"] == "watch.snapshot" and e["data"]["sub"] == watch
                                    and e["data"]["tasks"][0]["state"] == "succeeded", timeout=20)
    assert [t["id"] for t in snapshot["data"]["tasks"]] == [task_id]
    assert restarted.call("task.get", {"connection": CONNECTION, "task_id": task_id})["task"]["state"] == "succeeded"
    listed = restarted.call("task.list", {"connection": CONNECTION, "workspace_id": workspace})["tasks"]
    assert [t["id"] for t in listed] == [task_id]
    assert restarted.call("unsubscribe", {"sub": watch}) == {"ok": True}
    assert restarted.error("unsubscribe", {"sub": watch})["code"] == "not_found"
    restarted.close()


LOG_PROGRAM = (
    "import sys\n"
    "for i in range(40):\n"
    "    sys.stdout.write(f'第{i}步 计算完成：能量 −1.5e-3 🧲\\n')\n"
    "sys.stdout.write('结束')\n"
    "sys.stderr.write('错误输出 ✓\\n')\n"
)


def test_logs_split_mid_character_decode_exactly(runtime, inproc):  # noqa: F811
    client, supervisor, _, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    workspace = client.create_workspace("日志")["id"]
    task = harness.call("task.submit", {"connection": CONNECTION, "idempotency_key": "logs",
                                        "spec": {"workspace_id": workspace, "argv": ["{python}", "-c", LOG_PROGRAM]}})
    task_id = task["task"]["id"]
    assert finish(client, supervisor, task_id)["state"] == "succeeded"
    expected = "".join(f"第{i}步 计算完成：能量 −1.5e-3 🧲\n" for i in range(40)) + "结束"
    sub = harness.call("logs.subscribe", {"connection": CONNECTION, "task_id": task_id, "chunk_bytes": 5})["sub"]
    end = harness.wait_event(lambda e: e["event"] == "logs.end" and e["data"]["sub"] == sub)
    chunks = harness.events_of("logs.chunk", sub)
    stdout = [c for c in chunks if c["stream"] == "stdout"]
    assert "".join(c["text"] for c in stdout) == expected
    assert "".join(c["text"] for c in chunks if c["stream"] == "stderr") == "错误输出 ✓\n"
    data = expected.encode("utf-8")
    assert end["data"]["offsets"] == {"stdout": len(data), "stderr": len("错误输出 ✓\n".encode("utf-8"))}
    position = 0
    for chunk in stdout:  # contiguous, on character boundaries
        assert chunk["offset"] == position and chunk["text"] == data[position:chunk["next_offset"]].decode("utf-8")
        assert chunk["bytes"] == chunk["next_offset"] - chunk["offset"] == len(chunk["text"].encode("utf-8"))
        position = chunk["next_offset"]
    assert any(len(c["text"].encode("utf-8")) != 5 for c in stdout)  # characters really were split by chunks
    # Replaying the subscription from a reported offset (a restarted bridge) continues exactly.
    middle = stdout[len(stdout) // 2]["next_offset"]
    again = harness.call("logs.subscribe", {"connection": CONNECTION, "task_id": task_id, "streams": ["stdout"],
                                            "offsets": {"stdout": middle}, "chunk_bytes": 7})["sub"]
    harness.wait_event(lambda e: e["event"] == "logs.end" and e["data"]["sub"] == again)
    assert "".join(c["text"] for c in harness.events_of("logs.chunk", again)) == data[middle:].decode("utf-8")
    harness.close()


INVALID_PROGRAM = (
    "import sys\n"
    "sys.stdout.buffer.write(b'ok \\xff\\xfe bad \\xe8\\xae cut ' + '完成'.encode() + b'\\n')\n"
)


def test_log_chunks_count_source_bytes_when_invalid_utf8_was_replaced(runtime, inproc):  # noqa: F811
    client, supervisor, _, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    workspace = client.create_workspace("无效字节")["id"]
    spec = {"workspace_id": workspace, "argv": ["{python}", "-c", INVALID_PROGRAM]}
    task = harness.call("task.submit", {"connection": CONNECTION, "idempotency_key": "invalid-utf8", "spec": spec})
    task_id = task["task"]["id"]
    assert finish(client, supervisor, task_id)["state"] == "succeeded"
    raw = b"ok \xff\xfe bad \xe8\xae cut " + "完成".encode() + b"\n"
    sub = harness.call("logs.subscribe", {"connection": CONNECTION, "task_id": task_id, "streams": ["stdout"],
                                          "chunk_bytes": 4})["sub"]
    end = harness.wait_event(lambda e: e["event"] == "logs.end" and e["data"]["sub"] == sub)
    chunks = harness.events_of("logs.chunk", sub)
    assert "".join(c["text"] for c in chunks) == raw.decode("utf-8", "replace")
    # Replacement characters make the text longer than the bytes it came from; `bytes` (and the
    # offsets) count the source bytes, so a client can resume or trim by byte count.
    assert sum(c["bytes"] for c in chunks) == len(raw) == end["data"]["offsets"]["stdout"]
    assert any(len(c["text"].encode("utf-8")) != c["bytes"] for c in chunks)
    position = 0
    for chunk in chunks:
        assert chunk["offset"] == position and chunk["bytes"] == chunk["next_offset"] - chunk["offset"]
        position = chunk["next_offset"]
    harness.close()


def test_transfers_with_an_idempotency_key_are_started_once(runtime, inproc, tmp_path):  # noqa: F811
    client, supervisor, _, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    workspace = client.create_workspace("幂等传输")["id"]
    source = tmp_path / "数据.txt"
    source.write_text("一次", encoding="utf-8")
    params = {"connection": CONNECTION, "workspace_id": workspace, "source": str(source),
              "idempotency_key": "upload-1"}
    first = harness.call("upload.start", params)["transfer"]
    again = harness.call("upload.start", params)["transfer"]
    assert again["id"] == first["id"]
    assert harness.wait_transfer(first["id"])["state"] == "completed"
    other = tmp_path / "other.txt"
    other.write_text("二", encoding="utf-8")
    error = harness.error("upload.start", {**params, "source": str(other)})
    assert error["code"] == "conflict" and error["data"]["transfer_id"] == first["id"]
    harness.close()
    # A restarted bridge (same state directory) answers the key with the journaled transfer.
    restarted = inproc()
    repeated = restarted.call("upload.start", params)["transfer"]
    assert repeated["id"] == first["id"] and repeated["state"] == "completed"
    assert [f["path"] for f in client.files(workspace)] == ["数据.txt"]
    # Downloads likewise; the key spaces of uploads and downloads are separate.
    spec = {"workspace_id": workspace, "argv": ["{python}", "-c", RESULT_PROGRAM], "outputs": ["结果.txt", "big.bin"]}
    task = restarted.call("task.submit", {"connection": CONNECTION, "idempotency_key": "keyed-dl",
                                          "spec": spec})["task"]
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    download = {"connection": CONNECTION, "task_id": task["id"], "path": "结果.txt",
                "dest": str(tmp_path / "out" / "结果.txt"), "idempotency_key": "upload-1"}
    started = restarted.call("download.start", download)["transfer"]
    assert started["id"] != first["id"]
    assert restarted.call("download.start", download)["transfer"]["id"] == started["id"]
    assert restarted.wait_transfer(started["id"])["state"] == "completed"
    assert restarted.error("download.start", {**download, "path": "big.bin"})["code"] == "conflict"
    assert len(restarted.call("transfer.list")["transfers"]) == 2
    restarted.close()


RESULT_PROGRAM = (
    "import random\n"
    "from pathlib import Path\n"
    "Path('结果.txt').write_text('计算结果', encoding='utf-8')\n"
    "Path('big.bin').write_bytes(random.Random(3).randbytes(2 * 1024 * 1024 + 77))\n"
)


def test_downloads_are_resumed_and_verified(runtime, inproc, tmp_path):  # noqa: F811
    client, supervisor, server, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    workspace = client.create_workspace("下载")["id"]
    (tmp_path / "in.txt").write_text("输入", encoding="utf-8", newline="\n")
    client.upload(workspace, tmp_path / "in.txt")
    task = harness.call("task.submit", {"connection": CONNECTION, "idempotency_key": "dl",
                                        "spec": {"workspace_id": workspace, "argv": ["{python}", "-c", RESULT_PROGRAM],
                                                 "outputs": ["结果.txt", "big.bin"]}})["task"]
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    artifacts = harness.call("task.artifacts", {"connection": CONNECTION, "task_id": task["id"]})["artifacts"]
    expected = {a["path"]: a["sha256"] for a in artifacts}
    assert set(expected) == {"结果.txt", "big.bin"}
    transfer = harness.call("download.start", {"connection": CONNECTION, "task_id": task["id"],
                                               "path": "结果.txt"})["transfer"]
    done = harness.wait_transfer(transfer["id"])
    assert done["state"] == "completed" and done["sha256"] == expected["结果.txt"]
    local = Path(done["local"])
    assert local.read_text(encoding="utf-8") == "计算结果"
    assert Path(harness.call("hello", {"protocol": 1})["paths"]["download_dir"]) in local.parents
    # A partial download resumes from its .part file.
    reads = []
    original = server.service.file_chunk

    def file_chunk(root, name, offset, limit):
        reads.append(offset)
        return original(root, name, offset, limit)
    server.service.file_chunk = file_chunk
    work = server.service.task_dir(task["id"]) / "work"
    content = (work / "big.bin").read_bytes()
    dest = tmp_path / "downloads" / "big.bin"
    dest.parent.mkdir()
    dest.with_name("big.bin.part").write_bytes(content[:1234])
    from suan.runtime.common import atomic_json
    atomic_json(dest.with_name("big.bin.part.json"), {"path": "big.bin", "size": len(content),
                                                      "sha256": expected["big.bin"]})
    transfer = harness.call("download.start", {"connection": CONNECTION, "task_id": task["id"], "path": "big.bin",
                                               "dest": str(dest)})["transfer"]
    assert harness.wait_transfer(transfer["id"])["state"] == "completed"
    assert reads[0] == 1234 and dest.read_bytes() == content
    assert not dest.with_name("big.bin.part").exists()
    # Bytes that do not match the published sha256 are rejected and never land at the destination.
    tampered = bytearray(content)
    tampered[100] ^= 0xFF
    (work / "big.bin").write_bytes(bytes(tampered))
    bad = tmp_path / "downloads" / "bad.bin"
    transfer = harness.call("download.start", {"connection": CONNECTION, "task_id": task["id"], "path": "big.bin",
                                               "dest": str(bad)})["transfer"]
    failed = harness.wait_transfer(transfer["id"])
    assert failed["state"] == "failed" and failed["error"]["code"] == "checksum_mismatch"
    assert failed["error"]["retryable"] is True
    assert not bad.exists() and not list(bad.parent.glob("bad.bin.part*"))
    (work / "big.bin").write_bytes(content)
    mark = harness.mark()
    assert harness.call("transfer.resume", {"id": transfer["id"]})["transfer"]["id"] == transfer["id"]
    assert harness.wait_transfer(transfer["id"], start=mark)["state"] == "completed"
    assert hashlib.sha256(bad.read_bytes()).hexdigest() == expected["big.bin"]
    # Workspace inputs download the same way.
    transfer = harness.call("download.start", {"connection": CONNECTION, "workspace_id": workspace, "path": "in.txt",
                                               "dest": str(tmp_path / "in-copy.txt")})["transfer"]
    assert harness.wait_transfer(transfer["id"])["state"] == "completed"
    assert (tmp_path / "in-copy.txt").read_text(encoding="utf-8") == "输入"
    error = harness.error("download.start", {"connection": CONNECTION, "task_id": task["id"], "path": "../x"})
    assert error["code"] == "invalid_params"
    missing = harness.call("download.start", {"connection": CONNECTION, "task_id": task["id"], "path": "none.txt",
                                              "dest": str(tmp_path / "none.txt")})["transfer"]
    assert harness.wait_transfer(missing["id"])["error"]["code"] == "not_found"
    harness.close()


EVENTS_PROGRAM = (
    "from suan.monitor.emit import Emitter\n"
    "with Emitter() as mon:\n"
    "    mon.started('demo', total_steps=2)\n"
    "    mon.progress(step=1, total_steps=2)\n"
    "    mon.metrics({'e': float('nan')}, step=1)\n"
    "    mon.progress(step=2, total_steps=2)\n"
    "    mon.completed(True)\n"
)


def test_monitoring_events_and_task_snapshots(runtime, inproc):  # noqa: F811
    client, supervisor, _, _ = runtime
    harness = inproc()
    add_profile(harness, runtime)
    workspace = client.create_workspace("监控")["id"]
    task_id = harness.call("task.submit", {"connection": CONNECTION, "idempotency_key": "ev", "spec": {
        "workspace_id": workspace, "argv": ["{python}", "-c", EVENTS_PROGRAM]}})["task"]["id"]
    sub = harness.call("events.subscribe", {"connection": CONNECTION, "task_id": task_id})["sub"]
    watch = harness.call("watch", {"connection": CONNECTION, "task_ids": [task_id], "interval": 0.5})["sub"]
    assert finish(client, supervisor, task_id)["state"] == "succeeded"
    end = harness.wait_event(lambda e: e["event"] == "events.end" and e["data"]["sub"] == sub)
    batches = harness.events_of("events.batch", sub)
    types = [event["type"] for batch in batches for event in batch["events"]]
    assert types[0] == "run.started" and types[-1] == "run.completed" and "progress" in types
    metrics = next(event for batch in batches for event in batch["events"] if event["type"] == "metrics")
    assert metrics["data"]["values"]["e"] == "NaN"
    assert end["data"]["next_offset"] == batches[-1]["next_offset"]
    snapshot = harness.wait_event(lambda e: e["event"] == "watch.snapshot" and e["data"]["sub"] == watch
                                  and e["data"]["tasks"] and e["data"]["tasks"][0]["state"] == "succeeded")
    assert [t["id"] for t in snapshot["data"]["tasks"]] == [task_id]
    record = harness.call("task.get", {"connection": CONNECTION, "task_id": task_id})["task"]
    assert record["monitor"]["last_progress"]["step"] == 2
    harness.close()


def test_closing_the_app_keeps_jobs_running(runtime, bridge_env):  # noqa: F811
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace("关闭")["id"]
    bridge = ProcessBridge(bridge_env / "bridge")
    bridge.call("hello", {"protocol": 1})
    add_profile(bridge, runtime)
    task_id = bridge.call("task.submit", {"connection": CONNECTION, "idempotency_key": "long", "spec": {
        "workspace_id": workspace, "argv": [sys.executable, "-c", "import time; time.sleep(60)"]}})["task"]["id"]
    supervisor.tick()
    assert client.task(task_id)["state"] == "running"
    bridge.call("watch", {"connection": CONNECTION, "workspace_id": workspace})
    bridge.call("logs.subscribe", {"connection": CONNECTION, "task_id": task_id})
    started = time.monotonic()
    assert bridge.close() == 0  # EOF: subscriptions stop, the process exits
    assert time.monotonic() - started < 15
    supervisor.tick()
    assert client.task(task_id)["state"] == "running"
    again = ProcessBridge(bridge_env / "bridge")
    cancelled = again.call("task.cancel", {"connection": CONNECTION, "task_id": task_id})["task"]
    assert cancelled["cancel_requested"] is True
    assert finish(client, supervisor, task_id)["state"] == "cancelled"
    assert again.close() == 0


def test_local_runtime_connection(runtime, inproc, monkeypatch):  # noqa: F811
    from suan.runtime.common import atomic_json, identity
    client, _, server, config = runtime
    workspace = client.create_workspace("本机")["id"]
    monkeypatch.setenv("STK_STATE_DIR", config["state_dir"])
    atomic_json(Path(config["state_dir"]) / "api.pid", {**identity(), "port": server.server_port})
    harness = inproc()
    listed = harness.call("connections.list")["connections"]
    assert listed == [{"id": "local", "kind": "local", "name": "local", "url": client.url}]
    status = harness.call("connections.local")
    assert status["initialized"] and status["api_running"] and status["url"] == client.url
    assert [w["id"] for w in harness.call("workspace.list", {"connection": "local"})["workspaces"]] == [workspace]
    checked = harness.call("connections.check", {"id": "local"})
    assert checked["ok"] and checked["health"]["api_version"] == 1 and "events" in checked["health"]["features"]
    assert config["token"] not in harness.output_text()
    harness.close()
