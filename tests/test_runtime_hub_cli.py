"""CLI -> paired Hub -> outbound node -> Runtime; no external hosts or model calls."""
import json
import subprocess
import sys
import threading
import time
from urllib.error import URLError

import click
import pytest
from click.testing import CliRunner

from suan.runtime.cli import connect, jobs, workspaces
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


# --- workspaces through a paired hub ------------------------------------------------------------------------


def resolve_workspace(target, identity, timeout=15):
    deadline = time.monotonic() + timeout
    while True:
        result = value(invoke(workspaces, target + ["action", identity]))
        if result["action"]["state"] in {"succeeded", "failed", "rejected", "review"}:
            return result
        assert time.monotonic() < deadline, result
        time.sleep(0.05)


def runtime_workspaces(live):  # noqa: F811
    return {item["id"]: item["name"] for item in live.client.workspaces()}


def test_cli_hub_workspace_create_observe_list_files_and_key_semantics(live, paired, tmp_path):  # noqa: F811
    target, _ = paired
    key, name = "workspace-one", "CLI 工作区"
    identity = action_id("workspace.create", live.node_id, key)
    before = runtime_workspaces(live)
    created = invoke(workspaces, target + ["create", name, "--key", key])
    # The original key, then the deterministic action ID, are printed before the hub's reply is used.
    assert created.stderr.index(f"Idempotency key: {key}") < created.stderr.index(f"Hub action: {identity}")
    receipt = value(created)
    assert receipt["key"] == key and receipt["action"]["id"] == identity
    assert receipt["outcome"] in {"queued", "accepted"}
    workspace = resolve_workspace(target, identity)["workspace"]
    assert workspace["name"] == name and runtime_workspaces(live) == {**before, workspace["id"]: name}
    # The same key and request return the original workspace; the same key with another name is a conflict.
    replay = value(invoke(workspaces, target + ["create", name, "--key", key]))
    assert replay["outcome"] == "accepted" and replay["workspace"]["id"] == workspace["id"]
    conflict = CliRunner().invoke(workspaces, target + ["create", "another name", "--key", key])
    assert conflict.exit_code == 1 and "different request" in conflict.output
    assert runtime_workspaces(live) == {**before, workspace["id"]: name}
    # list is the node's bounded heartbeat snapshot, labelled as such.
    deadline = time.monotonic() + 15
    while True:
        listed = invoke(workspaces, target + ["list"])
        listing = value(listed)
        if workspace["id"] in {item["id"] for item in listing["workspaces"]}:
            break
        assert time.monotonic() < deadline, listing
        time.sleep(0.2)
    assert listing["observation"] == "heartbeat_snapshot" and listing["online"] is True
    assert "heartbeat snapshot" in listed.stderr and "may still exist" in listed.stderr
    # files reads the node live through the read path: no action row, no workspace, no task.
    source = tmp_path / "input.txt"
    source.write_text("公开输入\n", encoding="utf-8")
    live.client.upload(workspace["id"], source, "input.txt")
    actions, tasks = len(live.actions()), len(live.client.tasks())
    files = value(invoke(workspaces, target + ["files", workspace["id"]]))
    assert [item["path"] for item in files["files"]] == ["input.txt"]
    assert len(live.actions()) == actions and len(live.client.tasks()) == tasks
    assert runtime_workspaces(live) == {**before, workspace["id"]: name}


def test_cli_hub_workspace_review_waits_for_an_explicit_owner_decision(live, paired):  # noqa: F811
    """The current Hub policy never reviews workspace.create, so the reviewed state is seeded through the real
    store with exactly the request the CLI sends; the CLI must report it and never approve it itself."""
    target, _ = paired
    key, name = "reviewed-workspace", "复核工作区"
    identity = action_id("workspace.create", live.node_id, key)
    request = {"id": identity, "node_id": live.node_id, "kind": "workspace.create", "payload": {"name": name}}
    live.store.create_action(request, "seeded review for this test")
    before = runtime_workspaces(live)
    pending = value(invoke(workspaces, target + ["create", name, "--key", key]))
    assert pending["outcome"] == "pending_review" and "workspace" not in pending
    assert resolve_workspace(target, identity)["action"]["state"] == "review"
    assert runtime_workspaces(live) == before  # Nothing exists before the decision.
    approved = live.http.post(f"/api/v1/actions/{identity}/review", json={"approved": True}, headers=AUTH)
    assert approved.status_code == 200
    workspace = resolve_workspace(target, identity)["workspace"]
    assert runtime_workspaces(live) == {**before, workspace["id"]: name}
    assert value(invoke(workspaces, target + ["create", name, "--key", key]))["workspace"]["id"] == workspace["id"]


def test_cli_hub_workspace_lost_reply_is_observed_by_its_original_action(live, paired, monkeypatch):  # noqa: F811
    target, _ = paired
    key, name = "lost-workspace-reply", "丢失回复"
    original = HubClient.post_action
    sent = []

    def lost(self, body):
        sent.append(body["id"])
        original(self, body)
        raise URLError("reply lost")

    before = runtime_workspaces(live)
    monkeypatch.setattr(HubClient, "post_action", lost)
    unknown = CliRunner().invoke(workspaces, target + ["create", name, "--key", key])
    monkeypatch.setattr(HubClient, "post_action", original)
    assert unknown.exit_code == 1
    receipt = value(unknown)
    assert receipt["outcome"] == "unknown" and receipt["key"] == key
    assert receipt["action"] == {"id": action_id("workspace.create", live.node_id, key), "node_id": live.node_id,
                                 "kind": "workspace.create"}
    assert sent == [receipt["action"]["id"]]  # One request; no automatic retry under another key.
    workspace = resolve_workspace(target, receipt["action"]["id"])["workspace"]
    assert runtime_workspaces(live) == {**before, workspace["id"]: name}
    assert value(invoke(workspaces, target + ["create", name, "--key", key]))["workspace"]["id"] == workspace["id"]
    assert runtime_workspaces(live) == {**before, workspace["id"]: name}  # Not recreated.


def test_cli_hub_action_lookup_is_limited_to_its_node_and_kind(live, paired):  # noqa: F811
    target, state = paired
    created = value(invoke(workspaces, target + ["create", "kinds", "--key", "kinds"]))
    workspace_action = created["action"]["id"]
    workspace = resolve_workspace(target, workspace_action)["workspace"]["id"]
    submitted = value(invoke(jobs, target + ["submit", "--workspace", workspace, "--template", "echo", "--key", "kinds"]))
    task_action = submitted["action"]["id"]
    wrong_kind = CliRunner().invoke(workspaces, target + ["action", task_action])
    assert wrong_kind.exit_code == 1 and "not a workspace creation action" in wrong_kind.output
    other_kind = CliRunner().invoke(jobs, target + ["action", workspace_action])
    assert other_kind.exit_code == 1 and "not a task action" in other_kind.output
    other_node = ["--hub", "lab", "--node", "f" * 32, "--hub-state-dir", str(state)]
    wrong_node = CliRunner().invoke(workspaces, other_node + ["action", workspace_action])
    assert wrong_node.exit_code == 1 and "not a workspace creation action for the selected node" in wrong_node.output


def test_cli_hub_workspace_reads_during_a_real_node_disconnect(live, paired):  # noqa: F811
    target, _ = paired
    created = value(invoke(workspaces, target + ["create", "offline reads", "--key", "offline-reads"]))
    workspace = resolve_workspace(target, created["action"]["id"])["workspace"]["id"]
    live.agent_loop.call_soon_threadsafe(live.agent_task.cancel)
    live.agent_thread.join(timeout=10)
    assert not live.agent_thread.is_alive()
    try:
        actions, before = len(live.actions()), runtime_workspaces(live)
        offline = CliRunner().invoke(workspaces, target + ["files", workspace])
        assert offline.exit_code == 1 and "unavailable" in offline.output.lower()
        listed = value(invoke(workspaces, target + ["list"]))  # The last snapshot, never a live claim.
        assert listed["observation"] == "heartbeat_snapshot"
        assert len(live.actions()) == actions and runtime_workspaces(live) == before
    finally:
        live.agent_thread = threading.Thread(target=live._run_agent, daemon=True)
        live.agent_thread.start()
        deadline = time.monotonic() + 15
        while True:
            result = CliRunner().invoke(workspaces, target + ["files", workspace])
            if result.exit_code == 0:
                break
            assert time.monotonic() < deadline, result.output
            time.sleep(0.1)
    assert value(result)["files"] == []


class OldHub:
    """A stand-in hub whose node has no read path (501): reads fall back to a read action that is queued when
    posted and changes only when polled, in the given order of states (the last one repeats)."""
    url = "http://127.0.0.1:4"

    def __init__(self, states, result=None):
        self.states, self.result, self.posts, self.polls = list(states), result, [], []

    def read(self, *args):
        raise HubResponseError(501, "This node agent has no read path; upgrade suan-node")

    def _record(self, body, state):
        return {"id": body["id"], "node_id": body["node_id"], "request": body, "state": state,
                "result": self.result if state == "succeeded" else None,
                "error": "the node failed the read" if state == "failed" else ""}

    def post_action(self, body):
        self.posts.append(body)
        return self._record(body, "review" if body["kind"] == "task.submit" and "spec" in body["payload"] else "queued")

    def action(self, identity):
        self.polls.append(identity)
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return self._record(self.posts[-1], state)


def old_hub_cli(monkeypatch, hub, wait=5.0):
    """The CLI's own Hub client over a real HubBackend (with its own bounded wait) on the stand-in hub."""
    from suan.desktop_bridge.backends import _NO_READ_PATH

    class Store:
        def __init__(self, *args):
            pass

        def backend(self, connection, node):
            return HubBackend(connection, hub, node, wait=wait)

        def close(self):
            pass

    monkeypatch.delitem(_NO_READ_PATH, (hub.url, "a" * 32), raising=False)
    monkeypatch.setattr("suan.desktop_bridge.connections.ConnectionStore", Store)
    return ["--hub", "lab", "--node", "a" * 32]  # Real (short) polling sleeps inside HubBackend.run_action.


def test_old_node_read_fallback_polls_its_one_read_action_to_success(monkeypatch):
    """An old node answers the read path with 501; the existing fallback posts one read action, which the CLI
    must poll within the backend's bounded wait (not acknowledge and abandon, which a rerun would duplicate)."""
    from suan.runtime.cli import HubCLIClient
    hub = OldHub(["queued", "queued", "succeeded"], result=[{"path": "a.txt", "size": 1}])
    target = old_hub_cli(monkeypatch, hub)
    result = value(invoke(workspaces, target + ["files", "b" * 32]))
    assert result == {"files": [{"path": "a.txt", "size": 1}]}
    assert [body["kind"] for body in hub.posts] == ["workspace.files"] and len(hub.polls) == 3
    assert set(hub.polls) == {hub.posts[0]["id"]}  # The same read action, never a second one.
    client = HubCLIClient("lab", "a" * 32, "/unused")
    assert client.backend.wait == 5.0  # Reads keep the backend's own wait.
    hub.states = ["succeeded"]
    client.files("b" * 32)
    assert client.backend.wait == 5.0


@pytest.mark.parametrize("states,wait,message", [(["queued", "failed"], 5.0, "failed"),
                                                  (["queued"], 0.2, "has not finished")])
def test_old_node_read_fallback_failure_or_timeout_is_not_a_result(monkeypatch, states, wait, message):
    hub = OldHub(states, result=[{"path": "never.txt", "size": 1}])
    target = old_hub_cli(monkeypatch, hub, wait=wait)  # wait 0.2: the action stays queued past it
    result = CliRunner().invoke(workspaces, target + ["files", "b" * 32])
    assert result.exit_code == 1 and message in result.output and "never.txt" not in result.output
    assert len(hub.posts) == 1 and hub.polls  # It was polled, and still not reported as files.


def test_hub_writes_are_acknowledged_without_polling_and_restore_the_read_wait(monkeypatch):
    from suan.runtime.cli import HubCLIClient
    hub = OldHub(["succeeded"])
    target = old_hub_cli(monkeypatch, hub)
    created = value(invoke(workspaces, target + ["create", "acknowledged", "--key", "ack"]))
    assert created["outcome"] == "queued" and "workspace" not in created and hub.polls == []
    submitted = value(invoke(jobs, target + ["submit", "--workspace", "b" * 32, "--key", "ack", "--",
                                             "@python", "-c", "print(1)"]))
    assert submitted["outcome"] == "pending_review" and "task" not in submitted and hub.polls == []
    client = HubCLIClient("lab", "a" * 32, "/unused")
    client.create_workspace("again", "again")
    assert client.backend.wait == 5.0 and hub.polls == []

    def lost(body):
        raise URLError("reply lost")

    hub.post_action = lost
    with pytest.raises(click.exceptions.Exit):
        client.create_workspace("lost", "lost")
    assert client.backend.wait == 5.0  # Restored even when the write fails.


@pytest.mark.parametrize("source_exists", [True, False])
def test_hub_upload_is_refused_before_any_file_or_hub_access(tmp_path, monkeypatch, source_exists):
    import pathlib

    source = tmp_path / "inputs"
    if source_exists:
        source.mkdir()
        (source / "a.txt").write_text("a", encoding="utf-8")
    else:
        source = tmp_path / "missing"

    import os
    touched = []

    def store(*args, **kwargs):
        touched.append("hub connection store")
        raise AssertionError("the hub connection store was opened")

    def spy(name, original):
        def call(self, *args, **kwargs):
            if str(self).startswith(str(source)):
                touched.append(f"Path.{name}")
            return original(self, *args, **kwargs)
        return call

    def spy_os(name, original):
        def call(path, *args, **kwargs):
            if str(path).startswith(str(source)):
                touched.append(f"os.{name}")
            return original(path, *args, **kwargs)
        return call

    # Record-only spies, active just for this CLI call: the refusal must come before any of them sees the source.
    with monkeypatch.context() as patch:
        patch.setattr("suan.desktop_bridge.connections.ConnectionStore", store)
        for name in ("rglob", "is_dir", "is_file", "open", "read_bytes", "stat", "exists", "iterdir"):
            patch.setattr(pathlib.Path, name, spy(name, getattr(pathlib.Path, name)))
        for name in ("stat", "scandir", "open", "listdir"):
            patch.setattr(os, name, spy_os(name, getattr(os, name)))
        result = CliRunner().invoke(workspaces, ["--hub", "lab", "--node", "a" * 32, "upload", "b" * 32, str(source)])
    assert result.exit_code == 2 and "not supported with --hub" in result.output
    assert "does not exist" not in result.output  # click's existence check of the source never ran
    assert touched == []


def test_direct_workspace_commands_keep_their_calls_and_output(tmp_path, monkeypatch):
    calls = []

    class Client:
        def create_workspace(self, *args):
            calls.append(("create",) + args)
            return {"id": "w" * 32, "name": args[0]}

        def workspaces(self):
            calls.append(("list",))
            return [{"id": "w" * 32, "name": "direct"}]

        def files(self, workspace_id):
            calls.append(("files", workspace_id))
            return []

        def upload(self, workspace_id, path, remote):
            calls.append(("upload", workspace_id, remote))
            return {"path": remote}

    monkeypatch.setattr("suan.runtime.cli.get_client", lambda *args: Client())
    plain = invoke(workspaces, ["create", "direct"])
    assert json.loads(plain.stdout) == {"id": "w" * 32, "name": "direct"} and plain.stderr == ""
    invoke(workspaces, ["create", "keyed", "--key", "direct-key"])
    assert json.loads(invoke(workspaces, ["list"]).stdout) == [{"id": "w" * 32, "name": "direct"}]
    invoke(workspaces, ["files", "w" * 32])
    folder = tmp_path / "inputs"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.txt").write_text("a", encoding="utf-8")
    (folder / "sub" / "b.txt").write_text("b", encoding="utf-8")
    invoke(workspaces, ["upload", "w" * 32, str(folder)])
    assert calls == [("create", "direct"), ("create", "keyed", "direct-key"), ("list",), ("files", "w" * 32),
                     ("upload", "w" * 32, "a.txt"), ("upload", "w" * 32, "sub/b.txt")]


@pytest.mark.parametrize("arguments", [["--hub", "lab", "list"], ["--node", "a" * 32, "list"],
    ["--hub", "lab", "--node", "a" * 32, "--profile", "direct", "list"],
    ["--hub", "lab", "--node", "a" * 32, "--state-dir", "/unused", "list"], ["action", "a" * 32]])
def test_invalid_workspace_target_never_loads_credentials(arguments, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("credentials were loaded")

    monkeypatch.setattr("suan.desktop_bridge.connections.ConnectionStore", forbidden)
    monkeypatch.setattr("suan.runtime.cli.get_client", forbidden)
    result = CliRunner().invoke(workspaces, arguments)
    assert result.exit_code == 2


def test_hub_workspace_cli_closes_its_own_connection(monkeypatch):
    closed = []

    class Backend:
        node_id = "a" * 32
        wait = 30

        def workspaces(self):
            return {"workspaces": []}

        def device(self):
            return {"online": False}

    class Store:
        def __init__(self, *args):
            pass

        def backend(self, *args):
            return Backend()

        def close(self):
            closed.append(True)

    monkeypatch.setattr("suan.desktop_bridge.connections.ConnectionStore", Store)
    result = invoke(workspaces, ["--hub", "lab", "--node", "a" * 32, "list"])
    assert value(result) == {"workspaces": [], "observation": "heartbeat_snapshot", "online": False}
    assert closed == [True]
