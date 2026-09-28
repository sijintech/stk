"""Real isolated Python workers, revisioned edits and explicit desktop reverse requests."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import psutil
import pytest

from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.ui_requests import UIRequests
from suan.project import ProjectStore
from test_desktop_bridge import bridge_env, ProcessBridge  # noqa: F401


@pytest.fixture
def scripts(bridge_env):  # noqa: F811
    harness = ProcessBridge(bridge_env / "scripts")
    try:
        yield harness
    finally:
        harness.close()


def settled(harness, session, *, state="ready", timeout=20):
    deadline = time.monotonic() + timeout
    while True:
        result = harness.call("script.status", {"session": session})
        if result["state"] == state:
            return result
        assert time.monotonic() < deadline, result
        with harness.cond:
            harness.cond.wait(0.02)


def execute(harness, session, source=None, **params):
    if source is not None:
        params["source"] = source
    run = harness.call("script.execute", {"session": session, **params})["run"]
    result = settled(harness, session)
    assert result["run"]["id"] == run
    return result


def test_persistent_namespace_multiline_tracebacks_and_protocol_isolation(scripts, tmp_path):
    session = scripts.call("script.open", {"directory": str(tmp_path)})["session"]
    assert scripts.call("script.open")["session"] == session
    first = execute(scripts, session, "values = []\nfor i in range(4):\n    values.append(i ** 2)\nsum(values)")
    assert first["run"]["state"] == "succeeded"
    assert scripts.call("script.read", {"session": session})["text"] == "14\n"
    second = execute(scripts, session, "import os, subprocess, sys\nprint('中文 output')\nos.write(1, b'native output\\n')\nsubprocess.run([sys.executable, '-c', 'print(\"child output\")'])\nprint(values)\n1 / 0")
    assert first["kernel"] == second["kernel"]
    assert second["run"]["state"] == "failed"
    text = scripts.call("script.read", {"session": session})["text"]
    assert "中文 output" in text and "[0, 1, 4, 9]" in text and "ZeroDivisionError" in text
    assert "native output" not in text and "child output" not in text
    assert "native output" in scripts.stderr_text() and "child output" in scripts.stderr_text()
    assert execute(scripts, session, "values[-1]")["run"]["state"] == "succeeded"
    assert scripts.call("hello", {"protocol": 1})["protocol"] == 1


def test_scripts_share_project_commands_conflicts_and_changed_notifications(scripts, tmp_path):
    directory = tmp_path / "project"
    project = scripts.call("project.create", {"directory": str(directory), "name": "Simulation"})["project"]
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, "p = stk.project\ns = p.snapshot()\np.apply([{'op': 'create_table', 'name': 'Cases'}], expected_revision=s['project']['revision'])", project_handle=project["handle"])
    assert result["run"]["state"] == "succeeded"
    assert scripts.wait_event(lambda e: e["event"] == "project.changed")["data"] == {"handle": project["handle"], "revision": 1}
    assert ProjectStore(directory).snapshot()["tables"][0]["name"] == "Cases"
    failed = execute(scripts, session, "p.apply([{'op': 'create_table', 'name': 'Stale'}], expected_revision=0)")
    assert failed["run"]["state"] == "failed"
    assert "conflict" in scripts.call("script.read", {"session": session})["text"]
    assert ProjectStore(directory).info()["revision"] == 1
    assert execute(scripts, session, "stk.call('shutdown')")["run"]["state"] == "failed"
    assert scripts.call("hello", {"protocol": 1})["protocol"] == 1
    assert execute(scripts, session, "recent = stk.projects.recent()['projects']\nassert len(recent) == 1\nassert stk.projects.open(recent[0]['directory'], expected_id=recent[0]['id']).snapshot()['project']['id'] == recent[0]['id']\nassert stk.projects.forget(recent[0]['directory'])\nassert stk.projects.recent()['projects'] == []")["run"]["state"] == "succeeded"
    operations = set(scripts.call("script.catalog")["operations"])
    assert {name for name in operations if name.startswith("project.") and not name.startswith(("project.snapshots.", "project.runs."))} == {
        "project.create", "project.open", "project.list", "project.recent", "project.forget", "project.close", "project.snapshot", "project.apply", "project.history",
        "project.backup", "project.upgrade", "project.undo", "project.redo", "project.csv.import", "project.csv.export",
        "project.files.list", "project.files.index", "project.files.refresh", "project.files.resolve"}
    assert {"workspace.create", "task.submit", "task.logs", "upload.start", "transfer.get", "connections.ssh"} <= operations
    assert not operations & {"shutdown", "script.execute", "ui.attach", "watch", "logs.subscribe", "hub.review"}
    assert scripts.call("script.close", {"session": session})["closed"]
    assert scripts.call("project.list")["projects"][0]["revision"] == 1
    assert scripts.error("script.status", {"session": session})["code"] == "not_found"


def test_python_project_facade_undo_redo_uses_shared_persistent_history(scripts, tmp_path):
    info = scripts.call("project.create", {"directory": str(tmp_path / "undo"), "name": "Undo"})["project"]
    session = scripts.call("script.open")["session"]
    source = ("p = stk.project\np.apply([{'op':'create_table','name':'Cases'}], expected_revision=0)\n"
              "assert p.undo(expected_revision=1)['revision'] == 2\nassert p.snapshot()['tables'] == []\n"
              "assert p.redo(expected_revision=2)['revision'] == 3\nassert p.snapshot()['tables'][0]['name'] == 'Cases'")
    assert execute(scripts, session, source, project_handle=info["handle"])["run"]["state"] == "succeeded"
    assert scripts.call("project.snapshot", {"handle": info["handle"]})["snapshot"]["edit_history"] == {"undo_revision": 1, "redo_revision": None}
    assert execute(scripts, session, "p.undo(expected_revision=2)")["run"]["state"] == "failed"
    assert scripts.call("project.list")["projects"][0]["revision"] == 3


def test_python_files_facade_indexes_refreshes_and_resolves_without_launching(scripts, tmp_path):
    directory = tmp_path / "files"
    info = scripts.call("project.create", {"directory": str(directory), "name": "Files"})["project"]
    path = directory / "notes.md"
    path.write_text("# Notes", encoding="utf-8")
    session = scripts.call("script.open")["session"]
    source = ("p = stk.project\nindexed = p.files.index(['notes.md'], expected_revision=0)\n"
              "record = indexed['record_ids'][0]\nassert p.files.list()['records'][0]['name'] == 'notes.md'\n"
              "assert p.files.resolve(record, expected_revision=1)['kind'] == 'document'\n"
              "assert p.files.refresh([record], expected_revision=1)['revision'] == 2")
    assert execute(scripts, session, source, project_handle=info["handle"])["run"]["state"] == "succeeded"
    assert path.read_text(encoding="utf-8") == "# Notes"


def test_interrupt_stops_worker_tree_resets_namespace_and_keeps_bridge_usable(scripts, tmp_path):
    session = scripts.call("script.open")["session"]
    pidfile = tmp_path / "child.pid"
    code = ("import subprocess, sys, os\nfrom pathlib import Path\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
            f"Path({str(pidfile)!r}).write_text(str(child.pid))\n"
            "answer = 42\nprint('started', flush=True)\nwhile True:\n    pass")
    run = scripts.call("script.execute", {"session": session, "source": code})["run"]
    deadline = time.monotonic() + 20
    cursor = 0
    while True:
        output = scripts.call("script.read", {"session": session, "cursor": cursor})
        cursor = output["cursor"]
        if "started" in output["text"]:
            break
        assert time.monotonic() < deadline
        with scripts.cond:
            scripts.cond.wait(0.02)
    assert scripts.error("script.execute", {"session": session, "source": "pass"})["code"] == "busy"
    assert scripts.call("hello", {"protocol": 1})["protocol"] == 1
    child = psutil.Process(int(pidfile.read_text()))
    assert scripts.call("script.interrupt", {"session": session})["interrupted"]
    result = settled(scripts, session)
    assert result["run"]["id"] == run and result["run"]["state"] == "cancelled" and result["kernel"] is None
    try:
        assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        pass
    assert execute(scripts, session, "answer")["run"]["state"] == "failed"
    assert "NameError" in scripts.call("script.read", {"session": session, "cursor": cursor})["text"]
    assert execute(scripts, session, "6 * 7")["run"]["state"] == "succeeded"


def test_unicode_output_ring_and_file_execution(scripts, tmp_path):
    session = scripts.call("script.open", {"directory": str(tmp_path)})["session"]
    path = tmp_path / "脚本.py"
    path.write_text("from pathlib import Path\nprint(Path.cwd())\nprint(__file__)\nprint('温' * 1100000)", encoding="utf-8")
    result = execute(scripts, session, path=str(path))
    assert result["run"]["state"] == "succeeded" and result["run"]["filename"] == str(path)
    output = scripts.call("script.read", {"session": session, "limit": 10})
    assert output["truncated"] and output["text"] == "温" * 10
    assert output["cursor"] == output["output_start"] + 10
    assert output["output_end"] - output["output_start"] == 1024 * 1024
    tail = scripts.call("script.read", {"session": session, "cursor": output["output_end"] - 4})
    assert tail["text"] == "温温温\n" and tail["cursor"] == tail["output_end"]
    assert len(scripts.events_of("script.changed")) <= 4  # hints coalesce until read acknowledges
    assert scripts.error("script.read", {"session": session, "cursor": tail["cursor"] + 1})["code"] == "invalid_params"
    assert scripts.error("script.execute", {"session": session, "source": "pass", "path": str(path)})["code"] == "invalid_params"
    assert scripts.error("script.execute", {"session": session, "path": str(tmp_path / "missing")})["code"] == "not_found"


def test_reverse_layout_call_matching_errors_detach_and_recovery(scripts):
    session = scripts.call("script.open")["session"]
    assert execute(scripts, session, "stk.ui.layout()")["run"]["state"] == "failed"
    ui = scripts.call("ui.attach", {"operations": ["layout.get", "layout.apply"]})["session"]
    assert scripts.call("ui.attach", {"operations": ["layout.get", "layout.apply"]})["session"] == ui
    mark = scripts.mark()
    scripts.call("script.execute", {"session": session, "source": "saved = stk.ui.layout()\nprint(saved)"})
    request = scripts.wait_event(lambda e: e["event"] == "ui.request", start=mark)["data"]
    assert request["session"] == ui and request["operation"] == "layout.get"
    reply = {"session": ui, "request": request["request"], "result": {"layout": {"areas": ["viewer"]}}}
    assert scripts.call("ui.reply", {**reply, "session": "0" * 32}) == {"accepted": False}
    assert scripts.call("ui.reply", reply) == {"accepted": True}
    assert scripts.call("ui.reply", reply) == {"accepted": False}
    assert settled(scripts, session)["run"]["state"] == "succeeded"
    assert "viewer" in scripts.call("script.read", {"session": session})["text"]
    mark = scripts.mark()
    scripts.call("script.execute", {"session": session, "source": "stk.ui.apply_layout(saved)"})
    request = scripts.wait_event(lambda e: e["event"] == "ui.request", start=mark)["data"]
    assert request["params"] == {"layout": {"areas": ["viewer"]}}
    assert scripts.call("ui.detach", {"session": ui})["detached"]
    assert settled(scripts, session)["run"]["state"] == "failed"
    new = scripts.call("ui.attach", {"operations": ["layout.get"]})["session"]
    assert new != ui
    assert scripts.call("ui.reply", {"session": ui, "request": request["request"], "result": {}}) == {"accepted": False}
    assert execute(scripts, session, "stk.ui.apply_layout(saved)")["run"]["state"] == "failed"


def test_reverse_request_timeout_and_cancellation_drop_late_replies():
    emitted = []
    service = UIRequests(lambda event, data: emitted.append(data))
    session = service.attach({"operations": ["layout.get"]})["session"]
    with pytest.raises(BridgeError) as info:
        service.call("layout.get", {}, threading.Event(), timeout=0)
    assert info.value.code == "timeout"
    request = emitted[-1]
    assert service.reply({"session": session, "request": request["request"], "result": {}}) == {"accepted": False}
    ready, cancel = threading.Event(), threading.Event()
    service.emit = lambda *args: ready.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.call, "layout.get", {}, cancel)
        assert ready.wait(5)
        cancel.set()
        with pytest.raises(BridgeError) as info:
            pending.result(timeout=5)
        assert info.value.code == "cancelled"
    assert not service.pending
    service.close()


def test_worker_crash_and_system_exit_are_recoverable(scripts):
    session = scripts.call("script.open")["session"]
    assert execute(scripts, session, "raise SystemExit(3)")["run"]["state"] == "failed"
    result = execute(scripts, session, "import os\nos._exit(9)")
    assert result["run"]["state"] == "failed" and result["run"]["error"]["code"] == "unavailable"
    assert result["kernel"] is None
    assert execute(scripts, session, "print('recovered')")["run"]["state"] == "succeeded"


def test_file_main_guard_and_sibling_imports_use_standard_script_context(scripts, tmp_path):
    directory = tmp_path / "scripts"
    directory.mkdir()
    (directory / "helper.py").write_text("answer = 42\n", encoding="utf-8")
    path = directory / "main.py"
    path.write_text("import helper, sys\nfrom pathlib import Path\n"
                    "if __name__ == '__main__':\n"
                    "    print('file answer', helper.answer)\n"
                    "    assert sys.argv == [__file__]\n"
                    f"    assert Path.cwd() == Path({str(tmp_path)!r})\n"
                    "99\n", encoding="utf-8")
    session = scripts.call("script.open", {"directory": str(tmp_path)})["session"]
    assert execute(scripts, session, path=str(path))["run"]["state"] == "succeeded"
    output = scripts.call("script.read", {"session": session})
    assert output["text"] == "file answer 42\n" # file expressions do not auto-echo
    assert execute(scripts, session, "assert __name__ == '__console__'\nassert '__file__' not in globals()\nhelper.answer")["run"]["state"] == "succeeded"
    assert scripts.call("script.read", {"session": session, "cursor": output["cursor"]})["text"] == "42\n"
