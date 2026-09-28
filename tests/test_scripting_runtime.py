"""Python automation uses the same accepted jobs, transfer journals and review results as Jobs."""
import base64
import time

import pytest

from conftest import finish
from suan.scripting import API, ScriptError
from suan.desktop_bridge import schema
from test_desktop_scripts import scripts, execute, settled  # noqa: F401
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_bridge_runtime import add_profile


def test_console_upload_submit_logs_download_and_idempotent_retries(scripts, runtime, tmp_path):  # noqa: F811
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    source = tmp_path / "输入.txt"
    source.write_text("temperature = 300\n", encoding="utf-8")
    session = scripts.call("script.open", {"directory": str(tmp_path)})["session"]
    setup = f"""
from suan.scripting import ScriptError
r = stk.runtime({connection!r})
assert stk.connections.check({connection!r})['ok']
assert any(c['id'] == {connection!r} for c in stk.connections.list())
w = r.workspaces.create('Python 批次', idempotency_key='script-workspace')['workspace']['id']
assert r.workspaces.create('Python 批次', idempotency_key='script-workspace')['workspace']['id'] == w
t = r.upload(w, '输入.txt', remote='input.txt', idempotency_key='script-input')
assert stk.transfers.wait(t['id'], timeout=20)['state'] == 'completed'
assert r.upload(w, '输入.txt', remote='input.txt', idempotency_key='script-input')['id'] == t['id']
assert r.workspaces.files(w)[0]['path'] == 'input.txt'
spec = {{'workspace_id': w, 'argv': ['{{python}}', '-c', "from pathlib import Path; print('温度结果'); Path('result.txt').write_bytes(Path('input.txt').read_bytes())"], 'outputs': ['result.txt']}}
job = r.tasks.submit(spec, idempotency_key='script-task')['task']
assert r.tasks.submit(spec, idempotency_key='script-task')['task']['id'] == job['id']
try:
    r.tasks.submit({{**spec, 'name': 'different'}}, idempotency_key='script-task')
except ScriptError as error:
    assert error.code == 'conflict'
else:
    raise AssertionError('changed retry must conflict')
assert len(r.tasks.list(workspace_id=w)) == 1
print('submitted', job['id'])
"""
    result = execute(scripts, session, setup)
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    tasks = client.tasks()
    assert len(tasks) == 1
    assert finish(client, supervisor, tasks[0]["id"])["state"] == "succeeded"
    complete = """
assert r.tasks.wait(job['id'], timeout=0)['state'] == 'succeeded'
offset, chunks = 0, []
while True:
    chunk = r.tasks.logs(job['id'], offset=offset, limit=2)
    assert chunk['offset'] == offset and len(chunk['data']) <= 2
    assert chunk['next_offset'] == offset + len(chunk['data'])
    assert chunk['terminal']
    if not chunk['data']:
        break
    chunks.append(chunk['data'])
    offset = chunk['next_offset']
assert b''.join(chunks).decode('utf-8').strip() == '温度结果'
assert any(a['path'] == 'result.txt' for a in r.tasks.artifacts(job['id']))
download = r.download('result.txt', task_id=job['id'], dest='结果.txt', idempotency_key='script-result')
assert stk.transfers.wait(download['id'], timeout=20)['state'] == 'completed'
assert len(stk.transfers.list()) == 2
"""
    result = execute(scripts, session, complete)
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    assert (tmp_path / "结果.txt").read_bytes() == source.read_bytes()
    params = {"connection": connection, "task_id": tasks[0]["id"]}
    for invalid in ({"limit": 0}, {"limit": 1048577}, {"offset": -1}, {"stream": "file.log"}):
        assert scripts.error("task.logs", {**params, **invalid})["code"] == "invalid_params"
    assert scripts.error("task.logs", {**params, "offset": 1000})["code"] == "remote_error"


def test_interrupt_wait_keeps_accepted_task_and_new_worker_can_cancel(scripts, runtime):  # noqa: F811
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    workspace = client.create_workspace("Keep job")["id"]
    session = scripts.call("script.open")["session"]
    spec = {"workspace_id": workspace, "argv": ["{python}", "-c", "pass"]}
    assert execute(scripts, session, f"r = stk.runtime({connection!r})\njob = r.tasks.submit({spec!r}, idempotency_key='keep-job')['task']")["run"]["state"] == "succeeded"
    task = client.tasks()[0]
    cursor = scripts.call("script.read", {"session": session})["cursor"]
    scripts.call("script.execute", {"session": session, "source": "print('waiting', flush=True)\nr.tasks.wait(job['id'], timeout=600)"})
    deadline = time.monotonic() + 10
    while "waiting" not in scripts.call("script.read", {"session": session, "cursor": cursor})["text"]:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert scripts.call("script.interrupt", {"session": session})["interrupted"]
    assert settled(scripts, session)["run"]["state"] == "cancelled"
    assert client.task(task["id"])["state"] == "queued"
    code = f"stk.runtime({connection!r}).tasks.cancel({task['id']!r}, idempotency_key='cancel-kept-job')"
    assert execute(scripts, session, code)["run"]["state"] == "succeeded"
    assert finish(client, supervisor, task["id"])["state"] == "cancelled"


def test_hub_review_envelopes_are_preserved_without_approval_or_retry():
    calls = []
    pending = {"action": {"id": "a" * 32, "state": "review"}}
    def call(name, params):
        calls.append((name, params))
        return pending
    runtime = API(call).runtime("hub:research", node="b" * 32)
    assert runtime.workspaces.create("Cases", idempotency_key="workspace") is pending
    assert runtime.tasks.submit(template="solver", workspace_id="c" * 32, idempotency_key="submit") is pending
    assert runtime.tasks.cancel("d" * 32, idempotency_key="cancel") is pending
    assert [name for name, _ in calls] == ["workspace.create", "task.submit", "task.cancel"]
    assert all(p["connection"] == "hub:research" and p["node"] == "b" * 32 for _, p in calls)
    with pytest.raises(TypeError):
        runtime.tasks.submit({})  # No hidden random key when the caller omitted it.
    assert len(calls) == 3


def test_wait_returns_review_interruption_failure_and_unknown_without_mutation():
    records = [{"state": "running", "action": {"state": "review"}}, {"state": "interrupted"},
               {"state": "failed"}, {"state": "cancelled"}, {"state": "completed"}]
    for record in records:
        calls = []
        def call(name, params):
            calls.append(name)
            return {"transfer": record}
        assert API(call).transfers.wait("a" * 32, timeout=0) is record
        assert calls == ["transfer.get"]
    for state in ("succeeded", "failed", "cancelled", "unknown"):
        assert API(lambda *_: {"task": {"state": state}}).runtime("local").tasks.wait("id", timeout=0)["state"] == state


def test_wait_timeout_and_transport_failure_never_cancel_or_retry():
    calls = []
    def call(name, params):
        calls.append(name)
        return {"task": {"state": "running"}}
    tasks = API(call).runtime("local").tasks
    with pytest.raises(TimeoutError, match="not cancelled"):
        tasks.wait("id", timeout=0)
    assert calls == ["task.get"]
    def fail(name, params):
        calls.append(name)
        raise ScriptError({"code": "unavailable", "message": "offline", "retryable": True})
    with pytest.raises(ScriptError):
        API(fail).runtime("local").tasks.wait("id")
    assert calls == ["task.get", "task.get"]
    for kwargs in ({"timeout": -1}, {"timeout": float("inf")}, {"timeout": True}, {"interval": 0}, {"interval": float("nan")}):
        with pytest.raises(ValueError):
            tasks.wait("id", **kwargs)
    assert calls == ["task.get", "task.get"]


def test_log_schema_and_old_hub_limit_clamp():
    from suan.desktop_bridge.server import Bridge
    class Backend:
        def logs(self, task_id, stream, offset, limit):
            return {"data": "温度".encode(), "offset": offset, "next_offset": offset + 6, "terminal": True}
    class Service:
        def _backend(self, params):
            return Backend()
    result = Bridge.task_logs(Service(), {"task_id": "id", "offset": 7, "limit": 2}, None)
    assert base64.b64decode(result["data"]) == "温".encode()[:2]
    assert result["offset"] == 7 and result["next_offset"] == 9
    assert schema.validate_outgoing({"id": 1, "result": result}, "task.logs") == []


def test_local_path_normalization_preserves_symlink_checks_and_download_owner(tmp_path):
    calls = []
    def call(name, params):
        calls.append((name, params))
        return {"transfer": {"id": "id"}}
    runtime = API(call).runtime("local")
    # Path.absolute does not replace the user's source with a symlink target before bridge checks.
    source = tmp_path / "link.txt"
    runtime.upload("w", source, idempotency_key="upload")
    assert calls[-1][1]["source"] == str(source)
    for params in ({}, {"task_id": "t", "workspace_id": "w"}):
        with pytest.raises(ValueError, match="exactly one"):
            runtime.download("result", idempotency_key="download", **params)
    assert len(calls) == 1
