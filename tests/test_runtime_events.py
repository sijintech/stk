"""Runtime exposure of monitoring events: worker environment, events endpoint, task summary, health."""

from pathlib import Path
import ast
import time

import pytest

from conftest import finish
from suan.runtime.client import RuntimeErrorResponse
from suan.runtime.common import atomic_json, read_json
from suan.runtime.models import RESERVED_ENV, TaskSpec

pytestmark = pytest.mark.server

# Emits, then waits for a 'go' file in its work dir, then finishes; prints what the worker set.
PROGRAM = r"""
import os, time
from pathlib import Path
from suan.monitor.emit import Emitter
print(os.environ.get("STK_MONITOR_PATH"), os.environ.get("STK_TASK_ID"), flush=True)
with Emitter() as mon:
    mon.started("demo", total_steps=3)
    mon.progress(step=1, total_steps=3)
    mon.metrics({"e": float("nan")}, step=1)
    deadline = time.monotonic() + 30
    while not Path("go").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    mon.progress(step=3, total_steps=3)
    mon.completed(True)
"""
PRINT_ENV = "import os; print(os.environ.get('STK_MONITOR_PATH'), os.environ.get('STK_TASK_ID'))"


def wait_for_events(client, task_id, count, timeout=20):
    deadline = time.monotonic() + timeout
    while True:
        result = client.events(task_id)
        if len(result["events"]) >= count:
            return result
        assert time.monotonic() < deadline, result
        time.sleep(0.05)


def test_events_are_visible_while_the_task_runs(runtime):
    client, supervisor, server, _ = runtime
    assert client.health()["features"] == ["events"]
    ws = client.create_workspace("events")["id"]
    task = client.submit(TaskSpec(ws, ["{python}", "-c", PROGRAM]))
    supervisor.tick()
    result = wait_for_events(client, task["id"], 3)
    assert client.task(task["id"])["state"] == "running" and result["terminal"] is False
    assert [e["type"] for e in result["events"]] == ["run.started", "progress", "metrics"]
    assert [e["seq"] for e in result["events"]] == [0, 1, 2] and {e["src"] for e in result["events"]} == {"program"}
    assert result["events"][2]["data"] == {"step": 1, "values": {"e": "NaN"}}
    assert (result["offset"], result["next_offset"], result["invalid"]) == (0, result["size"], [])
    record = client.task(task["id"])
    assert record["monitor"] == {"events_size": result["size"], "last_progress": {"step": 1, "total_steps": 3},
                                 "last_ts": result["events"][-1]["ts"]}
    # Byte offsets: nothing new at the end; a one-byte limit still returns one whole line.
    assert client.events(task["id"], offset=result["next_offset"])["events"] == []
    first = client.events(task["id"], limit=1)
    assert [e["seq"] for e in first["events"]] == [0]
    second = client.events(task["id"], offset=first["next_offset"], limit=1)
    assert [e["seq"] for e in second["events"]] == [1] and second["offset"] == first["next_offset"]

    root = server.service.task_dir(task["id"])
    (root / "work" / "go").touch()
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    rest = client.events(task["id"], offset=result["next_offset"])
    assert rest["terminal"] is True and rest["next_offset"] == rest["size"]
    assert [(e["seq"], e["type"]) for e in rest["events"]] == [(3, "progress"), (4, "run.completed")]
    assert client.task(task["id"])["monitor"]["last_progress"] == {"step": 3, "total_steps": 3}
    # The worker set the path outside work/, so the file is never an artifact.
    assert client.logs(task["id"])["bytes"].decode().split() == [str(root / "events.jsonl"), task["id"]]
    assert (root / "events.jsonl").is_file() and "events.jsonl" not in [a["path"] for a in client.artifacts(task["id"])]


def test_events_route_errors_and_tasks_without_events(runtime):
    client, supervisor, _, _ = runtime
    ws = client.create_workspace("no events")["id"]
    task = client.submit(TaskSpec(ws, ["{python}", "-c", "pass"]))
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    assert client.events(task["id"]) == {"events": [], "offset": 0, "next_offset": 0, "size": 0, "invalid": [],
                                         "terminal": True}
    assert "monitor" not in client.task(task["id"])
    assert client.events(task["id"], offset=7)["next_offset"] == 7  # as logs(): a missing file has nothing yet
    emit_one = "from suan.monitor import Emitter; Emitter().message('info', 'hi')"
    task = client.submit(TaskSpec(ws, ["{python}", "-c", emit_one]))
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    size = client.events(task["id"])["size"]
    assert size > 0 and client.events(task["id"], offset=size)["events"] == []
    for query in (f"offset={size + 1}", "offset=-1", "limit=0", f"limit={1024 * 1024 + 1}", "offset=x"):
        with pytest.raises(RuntimeErrorResponse) as info:
            client.request("GET", f"tasks/{task['id']}/events?{query}")
        assert info.value.status == 400, query
    with pytest.raises(RuntimeErrorResponse) as info:
        client.events("f" * 32)
    assert info.value.status == 404


def test_task_env_cannot_set_or_spoof_the_monitoring_variables(runtime, monkeypatch):
    client, supervisor, server, _ = runtime
    assert {"STK_MONITOR_PATH", "STK_TASK_ID"} <= set(RESERVED_ENV)
    ws = client.create_workspace("reserved monitor env")["id"]
    for key in ("STK_MONITOR_PATH", "STK_TASK_ID"):
        with pytest.raises(ValueError, match=key):
            TaskSpec(ws, ["{python}", "-c", PRINT_ENV], env={key: "/tmp/elsewhere"})
        with pytest.raises(RuntimeErrorResponse, match=key):
            client.submit({"workspace_id": ws, "argv": ["{python}", "-c", PRINT_ENV], "env": {key: "x"}})
    # A spec stored before the refusal would run an older worker copy that passes it through.
    store = server.service.store
    task = client.submit(TaskSpec(ws, ["{python}", "-c", "open('ran', 'w').close()"]))
    store.update(task["id"], spec={**store.task(task["id"])["spec"], "env": {"STK_MONITOR_PATH": "/tmp/elsewhere"}})
    supervisor.tick()
    record = client.task(task["id"])
    assert record["state"] == "failed" and record["reason"].startswith("Resubmit without STK_MONITOR_PATH in env")
    assert not (server.service.task_dir(task["id"]) / "work" / "ran").exists()
    # The worker sets both after the spec's env, even when launch.json or its own environment has them.
    monkeypatch.setenv("STK_MONITOR_PATH", "/tmp/inherited.jsonl")
    monkeypatch.setenv("STK_TASK_ID", "inherited")
    task = client.submit(TaskSpec(ws, ["{python}", "-c", PRINT_ENV]))
    root = server.service.task_dir(task["id"])
    data = read_json(root / "launch.json")
    data["spec"]["env"] = {"STK_MONITOR_PATH": "/tmp/spoofed.jsonl", "STK_TASK_ID": "spoofed"}
    atomic_json(root / "launch.json", data)
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    assert client.logs(task["id"])["bytes"].decode().split() == [str(root / "events.jsonl"), task["id"]]


def test_worker_still_imports_nothing_from_stk():
    source = Path(__file__).resolve().parents[1] / "suan" / "runtime" / "worker.py"
    modules = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add("." if node.level else node.module.split(".")[0])
    assert not modules & {"suan", "."} and "psutil" in modules
