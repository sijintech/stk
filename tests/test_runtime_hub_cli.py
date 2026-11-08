"""CLI -> paired Hub -> outbound node -> Runtime; no external hosts or model calls."""
import json
import subprocess
import sys
import threading
import time
from urllib.error import URLError

import pytest
from click.testing import CliRunner

from suan.runtime.cli import connect, jobs
from suan.desktop_bridge.backends import HubBackend, action_id
from suan.desktop_bridge.hub import HubClient, HubResponseError
from suan.desktop_bridge.protocol import BridgeError
from test_hub_desktop_bridge import AUTH, live  # noqa: F401


def invoke(command, arguments, **kwargs):
    result = CliRunner().invoke(command, arguments, **kwargs)
    assert result.exit_code == 0, (result.output, result.exception)
    return result


def value(result):
    return json.loads(result.stdout[result.stdout.index("{"):])


@pytest.fixture(autouse=True)
def isolated_client_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("STK_STATE_DIR", str(tmp_path / "unused-runtime"))
    monkeypatch.setenv("STK_PROFILES_FILE", str(tmp_path / "unused-profiles.json"))


@pytest.fixture
def paired(live, tmp_path):  # noqa: F811
    state = tmp_path / "cli"
    result = invoke(connect, ["hub-pair", "lab", "--url", live.url, "--device-name", "CLI",
                              "--hub-state-dir", str(state)], input=live.code() + "\n")
    saved = value(result)
    assert saved["profile"] == ""  # CLI cannot grant itself the desktop profile.
    assert "token" not in saved
    assert (state / "hubs.json").stat().st_mode & 0o077 == 0
    return ["--hub", "lab", "--node", live.node_id, "--hub-state-dir", str(state)], state


def resolve(target, identity, timeout=15):
    deadline = time.monotonic() + timeout
    while True:
        result = value(invoke(jobs, target + ["action", identity]))
        if result["action"]["state"] in {"succeeded", "failed", "rejected", "review"}:
            return result
        assert time.monotonic() < deadline, result
        time.sleep(0.05)


def test_cli_template_trace_logs_events_artifact_download_and_original_key(live, paired, tmp_path):  # noqa: F811
    target, state = paired
    nodes = json.loads(invoke(connect, ["hub-nodes", "lab", "--hub-state-dir", str(state)]).stdout)
    assert nodes[0]["id"] == live.node_id and nodes[0]["online"] is True
    assert "task.get" in nodes[0]["features"]
    workspace = live.client.create_workspace("CLI inputs")["id"]
    key = "first-command"
    identity = action_id("task.submit", live.node_id, key)
    submitted = invoke(jobs, target + ["submit", "--workspace", workspace, "--template", "echo", "--key", key])
    assert key in submitted.stderr and identity in submitted.stderr
    assert value(submitted)["outcome"] in {"queued", "accepted"}
    task = resolve(target, identity)["task"]["id"]
    observations = invoke(jobs, target + ["watch", task, "--interval", "0.1", "--timeout", "15"])
    assert json.loads(observations.stdout.splitlines()[-1])["task"]["state"] == "succeeded"
    before = len(live.actions())
    shown = value(invoke(jobs, target + ["show", task]))
    assert shown["id"] == task and "spec" not in shown
    logs = invoke(jobs, target + ["logs", task, "--follow", "--show-offset"])
    assert logs.stdout == "读路径\n"
    assert f"Next offset: {len(logs.stdout.encode('utf-8'))}" in logs.stderr
    assert invoke(jobs, target + ["logs", task, "--offset", str(len(logs.stdout.encode("utf-8")))]).stdout == ""
    events = value(invoke(jobs, target + ["events", task]))
    assert "next_offset" in events and events["terminal"] is True
    artifacts = json.loads(invoke(jobs, target + ["artifacts", task]).stdout)
    assert [item["path"] for item in artifacts] == ["out.txt"]
    destination = tmp_path / "result.txt"
    invoke(jobs, target + ["download", task, "out.txt", str(destination)])
    assert destination.read_text(encoding="utf-8") == "结果"
    assert len(live.actions()) == before  # Reads never create action rows.
    retried = value(invoke(jobs, target + ["submit", "--workspace", workspace, "--template", "echo", "--key", key]))
    assert retried["task"]["id"] == task and len(live.client.tasks()) == 1


def test_cli_review_and_lost_reply_are_recovered_without_resubmission(live, paired, monkeypatch):  # noqa: F811
    target, _ = paired
    workspace = live.client.create_workspace("review")["id"]
    key = "review-command"
    arguments = target + ["submit", "--workspace", workspace, "--key", key, "--", "@python", "-c", "raise SystemExit(5)"]
    submitted = value(invoke(jobs, arguments))
    assert submitted["outcome"] == "pending_review" and "task" not in submitted
    identity = submitted["action"]["id"]
    assert len(live.client.tasks()) == 0
    assert resolve(target, identity)["action"]["state"] == "review"
    response = live.http.post(f"/api/v1/actions/{identity}/review", json={"approved": True}, headers=AUTH)
    assert response.status_code == 200
    first_task = resolve(target, identity)["task"]["id"]
    failed = CliRunner().invoke(jobs, target + ["watch", first_task, "--interval", "0.1", "--timeout", "15"])
    assert failed.exit_code == 1
    assert json.loads(failed.stdout.splitlines()[-1])["task"]["state"] == "failed"
    assert value(invoke(jobs, arguments))["task"]["id"] == first_task

    original = HubClient.post_action
    sent = []
    def lost(self, body):
        sent.append(body["id"])
        original(self, body)
        raise URLError("reply lost")
    monkeypatch.setattr(HubClient, "post_action", lost)
    unknown_key = "lost-response"
    unknown = CliRunner().invoke(jobs, target + ["submit", "--workspace", workspace,
        "--template", "echo", "--key", unknown_key])
    assert unknown.exit_code == 1
    receipt = value(unknown)
    assert receipt["outcome"] == "unknown" and receipt["key"] == unknown_key
    assert sent == [receipt["action"]["id"]]
    monkeypatch.setattr(HubClient, "post_action", original)
    resolved = resolve(target, receipt["action"]["id"])
    assert resolved["action"]["state"] == "succeeded"
    assert len(live.client.tasks()) == 2
    assert value(invoke(jobs, target + ["submit", "--workspace", workspace,
        "--template", "echo", "--key", unknown_key]))["task"]["id"] == resolved["task"]["id"]
    assert len(live.client.tasks()) == 2


def test_cli_failed_and_rejected_actions_keep_their_real_outcome(live, paired):  # noqa: F811
    target, _ = paired
    workspace = live.client.create_workspace("reject")["id"]
    arguments = target + ["submit", "--workspace", workspace, "--key", "reject", "--", "@python", "-c", "print('custom')"]
    submitted = value(invoke(jobs, arguments))
    identity = submitted["action"]["id"]
    assert live.http.post(f"/api/v1/actions/{identity}/review", json={"approved": False}, headers=AUTH).status_code == 200
    rejected = CliRunner().invoke(jobs, arguments)
    assert rejected.exit_code == 1 and value(rejected)["outcome"] == "rejected"
    query = CliRunner().invoke(jobs, target + ["action", identity])
    assert query.exit_code == 1 and value(query)["action"]["state"] == "rejected"
    arguments = target + ["cancel", "e" * 32, "--key", "missing-task"]
    CliRunner().invoke(jobs, arguments)
    identity = action_id("task.cancel", live.node_id, "missing-task")
    deadline = time.monotonic() + 10
    while live.store.action(identity)["state"] == "queued":
        assert time.monotonic() < deadline
        time.sleep(0.05)
    failed = CliRunner().invoke(jobs, arguments)
    assert failed.exit_code == 1 and value(failed)["outcome"] == "failed"


def test_cli_cancel_and_revoked_client(live, paired):  # noqa: F811
    target, state = paired
    workspace = live.client.create_workspace("cancel")["id"]
    submitted = value(invoke(jobs, target + ["submit", "--workspace", workspace, "--key", "sleep", "--",
        "@python", "-c", "import time; time.sleep(30)"]))
    identity = submitted["action"]["id"]
    assert live.http.post(f"/api/v1/actions/{identity}/review", json={"approved": True}, headers=AUTH).status_code == 200
    task = resolve(target, identity)["task"]["id"]
    cancelled = value(invoke(jobs, target + ["cancel", task, "--key", "cancel-once"]))
    assert cancelled["action"]["id"] == action_id("task.cancel", live.node_id, "cancel-once")
    assert resolve(target, cancelled["action"]["id"])["action"]["state"] == "succeeded"
    watched = CliRunner().invoke(jobs, target + ["watch", task, "--interval", "0.1", "--timeout", "15"])
    assert watched.exit_code == 1
    assert json.loads(watched.stdout.splitlines()[-1])["task"]["state"] == "cancelled"
    from suan.runtime.common import read_json
    device_id = read_json(state / "hubs.json")["lab"]["device_id"]
    live.store.revoke(device_id)
    denied = CliRunner().invoke(jobs, target + ["show", task])
    assert denied.exit_code != 0 and "refused this device" in denied.output


def test_cli_exact_task_survives_more_than_200_heartbeat_tasks(live, paired, monkeypatch):  # noqa: F811
    target, _ = paired
    workspace = live.client.create_workspace("history")["id"]
    task = live.client.submit({"workspace_id": workspace, "argv": ["@python", "-c", "print('old')"]}, "old")["id"]
    original = live.agent.runtime.tasks
    # The fixture retains a real persisted task, then presents 201 newer task DTOs
    # to the real heartbeat code. Lookup still goes through HTTP/WSS to Runtime.
    historic = original()[0]
    def many_tasks():
        return [{**historic, "id": f"{index:032x}"} for index in range(201)] + original()
    with monkeypatch.context() as patch:
        patch.setattr(live.agent.runtime, "tasks", many_tasks)
        snapshot = live.agent.snapshot()
        assert len(snapshot["tasks"]) == 200 and task not in {item["id"] for item in snapshot["tasks"]}
        live.store.heartbeat(live.node_id, snapshot)
        listing = value(invoke(jobs, target + ["list"]))
        assert listing["observation"] == "heartbeat_snapshot" and len(listing["tasks"]) == 200
        assert task not in {item["id"] for item in listing["tasks"]}
        assert value(invoke(jobs, target + ["show", task]))["id"] == task


def test_cli_observes_real_outbound_node_disconnect_and_reconnect(live, paired):  # noqa: F811
    target, _ = paired
    workspace = live.client.create_workspace("offline")["id"]
    submitted = value(invoke(jobs, target + ["submit", "--workspace", workspace, "--template", "echo", "--key", "offline"]))
    task = resolve(target, submitted["action"]["id"])["task"]["id"]
    invoke(jobs, target + ["watch", task, "--interval", "0.1", "--timeout", "15"])
    live.agent_loop.call_soon_threadsafe(live.agent_task.cancel)
    live.agent_thread.join(timeout=10)
    assert not live.agent_thread.is_alive()
    try:
        result = CliRunner().invoke(jobs, target + ["watch", task, "--interval", "0.1", "--timeout", "0.2"])
        assert result.exit_code == 1
        observations = [json.loads(line) for line in result.stdout.splitlines()]
        assert observations[0]["observation"] == "unavailable" and observations[0]["last_state"] is None
        assert live.client.task(task)["state"] == "succeeded"
    finally:
        live.agent_thread = threading.Thread(target=live._run_agent, daemon=True)
        live.agent_thread.start()
        deadline = time.monotonic() + 10
        while True:
            result = CliRunner().invoke(jobs, target + ["show", task])
            if result.exit_code == 0:
                break
            assert time.monotonic() < deadline, result.output
            time.sleep(0.05)
    assert value(result)["state"] == "succeeded"


@pytest.mark.parametrize("node_features,read_kinds", [([], ["task.get"]), (["task.get"], ["task.get"]),
    (["read", "task.get"], []), (["read", "task.get"], None)])
def test_old_hub_or_node_never_claims_exact_task_lookup(node_features, read_kinds):
    class Hub:
        url = "http://127.0.0.1:1"
        def devices(self):
            return [{"id": "a" * 32, "role": "node", "online": True,
                     "snapshot": {"features": node_features, "tasks": [{"id": "b" * 32, "state": "queued"}]}}]
        def policy(self):
            if read_kinds is None:
                raise HubResponseError(404, "Not Found")
            return {"read_kinds": read_kinds}
        def read(self, *args):
            pytest.fail("Old capability must not be probed as supported")
    backend = HubBackend("hub:old", Hub(), "a" * 32)
    assert backend.task("b" * 32)["task"]["state"] == "queued"  # Existing desktop fallback.
    with pytest.raises(BridgeError, match="requires task.get"):
        backend.task("b" * 32, require_live=True)


def test_watch_distinguishes_offline_from_task_state_and_reconnects(monkeypatch):
    import suan.runtime.cli as module
    values = iter([{"id": "b" * 32, "state": "running"}, None, {"id": "b" * 32, "state": "succeeded"}])
    closed = []
    class Backend:
        def task(self, identity, require_live):
            item = next(values)
            if item is None:
                raise BridgeError("unavailable", "node disconnected")
            return {"task": item}
    class Store:
        def __init__(self, *args):
            pass
        def backend(self, *args):
            return Backend()
        def close(self):
            closed.append(True)
    monkeypatch.setattr("suan.desktop_bridge.connections.ConnectionStore", Store)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    result = invoke(jobs, ["--hub", "lab", "--node", "a" * 32, "watch", "b" * 32])
    observations = [json.loads(line) for line in result.stdout.splitlines()]
    assert [item["observation"] for item in observations] == ["current", "unavailable", "current"]
    assert observations[1]["last_state"] == "running" and "task" not in observations[1]
    assert observations[2]["task"]["state"] == "succeeded"
    assert closed == [True]


@pytest.mark.parametrize("state,exit_code", [("succeeded", 0), ("failed", 1), ("cancelled", 1), ("unknown", 1)])
def test_watch_exit_status_preserves_runtime_state(state, exit_code, monkeypatch):
    class Client:
        def task(self, identity):
            return {"id": identity, "state": state}
    monkeypatch.setattr("suan.runtime.cli.get_client", lambda *args: Client())
    result = CliRunner().invoke(jobs, ["watch", "b" * 32])
    assert result.exit_code == exit_code
    assert json.loads(result.stdout)["task"]["state"] == state


@pytest.mark.parametrize("times", [
    {},
    {"created_at": "2026-11-08T12:00:00+00:00", "updated_at": "2026-11-08T12:00:01+00:00"},
    {"created_at": "2026-11-08T12:00:00+00:00", "updated_at": "2026-11-08T12:00:01+00:00",
     "attempted_at": None},
    {key: "2026-11-08T12:00:02.123456+00:00"
     for key in ("created_at", "updated_at", "attempted_at", "started_at", "finished_at")},
])
def test_task_get_policy_private_reservations_and_public_projection(tmp_path, times):
    from suan.control.agent import NodeAgent
    from suan.control.policy import validate_action
    task_id, workspace = "a" * 32, "b" * 32
    action = {"id": "c" * 32, "node_id": "d" * 32, "kind": "task.get", "payload": {"task_id": task_id}}
    assert validate_action(action, {}) == ""
    with pytest.raises(ValueError):
        validate_action({**action, "payload": {"task_id": task_id, "path": "secret"}}, {})
    class Runtime:
        def task(self, identity):
            return {"id": task_id, "state": "running", **times, "spec": {"name": "public", "workspace_id": workspace,
                    "argv": ["private argv"], "env": {"TEST_VALUE": "abcdefghijklmnopqrstu"}}}
    class Federation:
        private = False
        def private_identities(self):
            return {"tasks": set(), "workspaces": {workspace} if self.private else set()}
    federation = Federation()
    agent = NodeAgent(Runtime(), tmp_path / "agent", federation=federation)
    assert agent.read("task.get", action["payload"]) == {
        "id": task_id, "state": "running", "name": "public", "workspace_id": workspace, **times}
    federation.private = True
    with pytest.raises(ValueError, match="private federation"):
        agent.read("task.get", action["payload"])
    assert not list((tmp_path / "agent").glob("*.json"))  # Exact reads do not cache stale task state.


def test_artifact_media_types_survive_actual_node_and_backend_adapters(tmp_path, monkeypatch):
    from suan.control.agent import NodeAgent
    from suan.desktop_bridge.backends import RuntimeBackend, _NO_READ_PATH
    task_id, node_id = "b" * 32, "a" * 32
    artifacts = [{"path": "out.txt", "size": 8, "sha256": "1" * 64, "media_type": "text/plain"},
                 {"path": "raw.unknown-stk-format", "size": 9, "sha256": "2" * 64,
                  "media_type": "application/octet-stream"}]
    calls = []

    class Runtime:
        def artifacts(self, identity):
            assert identity == task_id
            calls.append("runtime.artifacts")
            return artifacts

    runtime = Runtime()
    agent = NodeAgent(runtime, tmp_path / "agent")

    class Hub:
        url = "http://127.0.0.1:3"

        def read(self, node, kind, payload):
            assert (node, kind, payload) == (node_id, "task.artifacts", {"task_id": task_id})
            calls.append("hub.read")
            return agent.read(kind, payload)

        def action(self, *args):
            pytest.fail("The read must not create an action")

    monkeypatch.delitem(_NO_READ_PATH, (Hub.url, node_id), raising=False)
    assert RuntimeBackend("runtime:metadata", runtime).artifacts(task_id) == {"artifacts": artifacts}
    assert HubBackend("hub:metadata", Hub(), node_id).artifacts(task_id) == {"artifacts": artifacts}
    assert calls == ["runtime.artifacts", "hub.read", "runtime.artifacts"]
    assert not list((tmp_path / "agent").glob("*.json"))


def test_hub_cli_import_remains_lightweight():
    code = "import sys; from suan.runtime.cli import jobs; assert not any(m in sys.modules for m in ('numpy', 'vtk', 'PySide6', 'fastapi', 'suan.desktop_bridge.server'))"
    subprocess.run([sys.executable, "-c", code], check=True, timeout=10)


@pytest.mark.parametrize("arguments", [["--hub", "lab", "list"], ["--node", "a" * 32, "list"],
    ["--hub", "lab", "--node", "a" * 32, "--profile", "direct", "list"]])
def test_invalid_target_never_loads_credentials(arguments):
    result = CliRunner().invoke(jobs, arguments)
    assert result.exit_code == 2
