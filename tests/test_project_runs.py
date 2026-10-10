"""Frozen row provenance, explicit execution and durable recovery across project/bridge lifetimes."""
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from conftest import finish
from suan.project import ProjectStore, ProjectError, RevisionConflict
from suan.project.store import FORMAT_VERSION
from suan.desktop_bridge.backends import RuntimeBackend
from suan.desktop_bridge.project_runs import ProjectRuns
from suan.desktop_bridge.projects import ProjectSessions
from suan.desktop_bridge.protocol import BridgeError
from test_project_values import model, derived, command  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_bridge_runtime import add_profile


def entry(ids, **extra):
    return {"table_id": ids["inputs"], "record_id": ids["input_row"],
            "spec": {"workspace_id": "a" * 32, "argv": ["{python}", "-c", "pass"]}, **extra}


def prepare(store, entries, **kwargs):
    return store.runs.prepare(entries, connection="runtime:Test", connection_identity="a" * 16,
                              expected_revision=store.info()["revision"], **kwargs)["run_ids"]


def test_frozen_plan_survives_edits_rename_undo_and_reopen(model):
    store, ids = model
    run_id = prepare(store, [entry(ids)])[0]
    run = store.runs.get(run_id)
    assert run["parameter_state"] == "current" and run["status"] == {"submission": "prepared"}
    assert run["plan"]["parameters"]["values"][ids["temperature"]] == 300
    assert run["plan"]["spec"]["inputs"] == [] and run["plan"]["spec"]["input_hashes"] == {}
    store.apply([{"op": "rename_table", "id": ids["inputs"], "name": "参数"},
                 {"op": "rename_field", "id": ids["temperature"], "name": "温度"}], expected_revision=2)
    assert store.runs.get(run_id)["parameter_state"] == "current"
    store.apply([command(ids, "temperature", "set_cell", value=400)], expected_revision=3)
    assert store.runs.get(run_id)["parameter_state"] == "changed"
    store.undo(expected_revision=4)
    assert store.runs.get(run_id)["parameter_state"] == "current"
    store.apply([{"op": "delete_record", "id": ids["input_row"]}], expected_revision=5)
    reopened = ProjectStore(store.directory).runs.get(run_id)
    assert reopened["parameter_state"] == "missing"
    assert reopened["plan"] == run["plan"] and reopened["sha256"] == run["sha256"]
    assert store.history()[1]["commands"] == [{"op": "prepare_runs", "run_ids": [run_id]}]


def test_formula_dependency_changes_mark_old_run_and_errors_cannot_be_prepared(model):
    store, ids = derived(model)
    case = entry(ids, table_id=ids["results"], record_id=ids["result_row"])
    run_id = prepare(store, [case])[0]
    store.apply([command(ids, "temperature", "set_cell", value=400)], expected_revision=3)
    assert store.runs.get(run_id)["parameter_state"] == "changed"
    store.apply([{"op": "delete_record", "id": ids["input_row"]}], expected_revision=4)
    assert store.runs.get(run_id)["parameter_state"] == "error"
    with pytest.raises(ProjectError, match="formula error"):
        prepare(store, [case])
    assert len(store.runs.list()["runs"]) == 1


def test_batch_is_atomic_revision_checked_and_summaries_paginate_without_specs(model):
    store, ids = model
    with pytest.raises(ProjectError):
        prepare(store, [entry(ids), entry(ids, record_id=str(uuid4()))])
    assert store.runs.list()["runs"] == [] and store.info()["revision"] == 1
    with pytest.raises(RevisionConflict):
        store.runs.prepare([entry(ids)], connection="local", connection_identity="a" * 16, expected_revision=0)
    runs = prepare(store, [entry(ids, label=str(i)) for i in range(3)])
    first = store.runs.list(limit=2)
    assert [r["id"] for r in first["runs"]] == runs[:2] and first["next_offset"] == 2
    assert all("plan" not in r for r in first["runs"])
    last = store.runs.list(offset=first["next_offset"], limit=2)
    assert last["runs"][0]["id"] == runs[2] and last["next_offset"] is None
    assert store.info()["revision"] == 2


def test_snapshot_bindings_freeze_program_and_data_hashes(model):
    store, ids = model
    file = store.directory / "input.txt"
    file.write_bytes(b"frozen")
    file_id = store.files.index([str(file)], expected_revision=1)["record_ids"][0]
    snapshot = store.snapshots.capture([file_id], expected_revision=2)["snapshot"]
    case = entry(ids, input_snapshot_id=snapshot["id"], input_bindings={"nested/input.txt": file_id})
    run_id = prepare(store, [case])[0]
    file.unlink()
    plan = store.runs.get(run_id)["plan"]
    assert plan["spec"]["inputs"] == ["nested/input.txt"]
    assert plan["spec"]["input_hashes"] == {"nested/input.txt": hashlib.sha256(b"frozen").hexdigest()}
    assert plan["input_snapshot_id"] == snapshot["id"] and plan["inputs"][0]["record_id"] == file_id
    for bad in ({"../bad": file_id}, {"x": str(uuid4())}, {}):
        with pytest.raises(ProjectError):
            prepare(store, [{**case, "input_bindings": bad}])
    with pytest.raises(ProjectError, match="exactly match"):
        prepare(store, [{**case, "spec": {**case["spec"], "inputs": ["different.txt"]}}])


def test_observations_preserve_identity_and_terminal_state_without_edit_revision(model):
    store, ids = model
    run_id = prepare(store, [entry(ids)])[0]
    task = {"id": "a" * 32, "state": "succeeded"}
    store.runs.observe(run_id, {"task": task, "submission": "accepted"})
    store.runs.observe(run_id, {"task": {**task, "state": "running"}, "submission": "submitting"})
    assert store.runs.get(run_id)["status"] == {"task": task, "submission": "accepted"}
    assert store.info()["revision"] == 2 and store.snapshot()["edit_history"]["undo_revision"] == 1
    with pytest.raises(ProjectError, match="cannot change"):
        store.runs.observe(run_id, {"task": {**task, "id": "b" * 32}})
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM run_observations").fetchone()[0] == 1
        db.execute("UPDATE run_plans SET plan='{}'")
    with pytest.raises(ProjectError, match="stored run plan"):
        store.runs.get(run_id)


def test_format_four_upgrade_keeps_snapshots_and_preupgrade_backup(model):
    store, ids = model
    path = store.directory / "input"
    path.write_bytes(b"keep")
    file_id = store.files.index([str(path)], expected_revision=1)["record_ids"][0]
    snapshot = store.snapshots.capture([file_id], expected_revision=2)["snapshot"]
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS project_agent_objects")
        db.execute("DROP TABLE IF EXISTS project_agent_events")
        db.execute("DROP TABLE IF EXISTS project_agent_sessions")
        db.execute("DROP TABLE IF EXISTS project_labels")
        db.execute("DROP TABLE IF EXISTS project_archive")
        db.execute("DROP TABLE IF EXISTS workflow_run_events")
        db.execute("DROP TABLE IF EXISTS workflow_run_plans")
        db.execute("DROP TABLE IF EXISTS analysis_run_events")
        db.execute("DROP TABLE IF EXISTS analysis_run_plans")
        db.execute("DROP TABLE IF EXISTS project_requests")
        db.execute("DROP TABLE IF EXISTS project_proposals")
        db.execute("DROP TABLE IF EXISTS project_messages")
        db.execute("DROP TABLE IF EXISTS project_contexts")
        db.execute("DROP TABLE project_drafts")
        db.execute("DROP TABLE run_observations")
        db.execute("DROP TABLE run_plans")
        db.execute("PRAGMA user_version=4")
    assert store.snapshots.get(snapshot["id"]) == snapshot
    with pytest.raises(ProjectError, match="format 5"):
        prepare(store, [entry(ids)])
    result = store.upgrade(expected_revision=3)
    assert result["upgraded"] and store.snapshot()["format_version"] == FORMAT_VERSION
    assert store.snapshots.verify(snapshot["id"])["ok"]
    assert store.runs.list()["runs"] == []
    assert store.snapshot()["edit_history"]["undo_revision"] == 2
    with sqlite3.connect(result["backup"]["path"]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert db.execute("SELECT id FROM project_snapshots").fetchone()[0] == snapshot["id"]


def service(store, backend):
    sessions = ProjectSessions()
    handle = sessions.open({"directory": str(store.directory)})["project"]["handle"]
    return ProjectRuns(sessions, lambda connection, node: backend), {"handle": handle}


def test_response_loss_recovers_one_remote_task_even_after_parameter_change(model, runtime):
    store, ids = model
    client, supervisor, _, _ = runtime
    backend = RuntimeBackend("local", client)
    svc, p = service(store, backend)
    case = entry(ids, spec={"workspace_id": client.create_workspace("recover")["id"], "argv": ["{python}", "-c", "pass"]})
    run_id = svc.call("prepare", {**p, "connection": "local", "entries": [case], "expected_revision": 1})["run_ids"][0]
    original = backend.submit
    def lost(*args):
        original(*args)
        raise BridgeError("unavailable", "response lost")
    backend.submit = lost
    with pytest.raises(BridgeError):
        svc.call("submit", {**p, "run_id": run_id})
    assert store.runs.get(run_id)["status"]["submission"] == "uncertain"
    store.apply([command(ids, "temperature", "set_cell", value=500)], expected_revision=2)
    backend.submit = original
    assert svc.call("refresh", {**p, "run_id": run_id})["run"]["status"]["submission"] == "uncertain"
    # A new session recovers precisely the already accepted frozen request.
    svc, p = service(ProjectStore(store.directory), backend)
    run = svc.call("submit", {**p, "run_id": run_id})["run"]
    task_id = run["status"]["task"]["id"]
    assert len(client.tasks()) == 1 and run["parameter_state"] == "changed"
    assert finish(client, supervisor, task_id)["state"] == "succeeded"
    assert svc.call("refresh", {**p, "run_id": run_id})["run"]["status"]["task"]["state"] == "succeeded"
    assert store.info()["revision"] == 3


def test_new_stale_intent_and_changed_endpoint_are_refused_before_submission(model, runtime):
    store, ids = model
    client, _, _, _ = runtime
    backend = RuntimeBackend("local", client)
    svc, p = service(store, backend)
    case = entry(ids, spec={"workspace_id": client.create_workspace("stale")["id"], "argv": ["{python}", "-c", "pass"]})
    run_id = svc.call("prepare", {**p, "connection": "local", "entries": [case], "expected_revision": 1})["run_ids"][0]
    store.apply([command(ids, "temperature", "set_cell", value=400)], expected_revision=2)
    with pytest.raises(BridgeError, match="Parameters changed"):
        svc.call("submit", {**p, "run_id": run_id})
    assert client.tasks() == []
    original_url = client.url
    client.url = "http://127.0.0.1:1"
    with pytest.raises(BridgeError, match="different endpoint"):
        svc.call("submit", {**p, "run_id": run_id, "allow_stale": True})
    client.url = original_url
    assert client.tasks() == []
    run = svc.call("submit", {**p, "run_id": run_id, "allow_stale": True})["run"]
    assert run["status"]["task"]["state"] == "queued"
    cancelled = svc.call("cancel", {**p, "run_id": run_id})["run"]
    assert cancelled["status"]["task"]["state"] == "cancelled"


def test_hub_review_refresh_recovers_approved_task_without_posting_or_approving(model):
    store, ids = model
    class Backend:
        server_key = "a" * 16
        accepted = False
        def submit(self, spec, key):
            return {"action": {"id": "b" * 32, "state": "review"}}
        def action_record(self, identity):
            assert identity == "b" * 32
            return {"id": identity, "state": "succeeded" if self.accepted else "review",
                    "result": {"id": "c" * 32, "state": "queued"}, "request": {"kind": "task.submit"}}
    backend = Backend()
    svc, p = service(store, backend)
    run_id = svc.call("prepare", {**p, "connection": "hub:Test", "node": "d" * 32, "entries": [entry(ids)], "expected_revision": 1})["run_ids"][0]
    assert svc.call("submit", {**p, "run_id": run_id})["run"]["status"]["submission"] == "review"
    assert svc.call("refresh", {**p, "run_id": run_id})["run"]["status"]["submission"] == "review"
    backend.accepted = True
    run = svc.call("refresh", {**p, "run_id": run_id})["run"]
    assert run["status"]["submission"] == "accepted" and run["status"]["task"]["id"] == "c" * 32


def test_console_frozen_input_run_persists_after_close_and_validates_history(scripts, runtime, tmp_path):
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    session = scripts.call("script.open", {"directory": str(tmp_path)})["session"]
    source = tmp_path / "input.txt"
    source.write_bytes(b"temperature=300")
    code = f'''
from uuid import uuid4
p = stk.projects.create({str(tmp_path / 'project')!r}, 'Run provenance')
table, field, row = [str(uuid4()) for _ in range(3)]
p.apply([{{'op':'create_table','id':table,'name':'Cases'}},
         {{'op':'add_field','id':field,'table_id':table,'name':'T','type':'number','unit':'K'}},
         {{'op':'add_record','id':row,'table_id':table}},
         {{'op':'set_cell','table_id':table,'record_id':row,'field_id':field,'value':300}}], expected_revision=0)
file_id = p.files.index([{str(source)!r}], expected_revision=1)['record_ids'][0]
snapshot = p.snapshots.capture([file_id], expected_revision=2)['snapshot']
r = stk.runtime({connection!r})
w = r.workspaces.create('Run test', idempotency_key='run-workspace')['workspace']['id']
transfer = r.upload(w, p.snapshots.resolve(snapshot['id'], file_id)['path'], remote='input.txt', idempotency_key='frozen-upload')
assert stk.transfers.wait(transfer['id'], timeout=20)['state'] == 'completed'
spec = {{'workspace_id':w, 'argv':['{{python}}','-c',"from pathlib import Path; Path('result.txt').write_bytes(Path('input.txt').read_bytes())"], 'outputs':['result.txt']}}
run_id = p.runs.prepare([{{'table_id':table,'record_id':row,'spec':spec,'input_snapshot_id':snapshot['id']}}], connection={connection!r}, expected_revision=3)['run_ids'][0]
assert p.history()[-1]['commands'][0]['op'] == 'prepare_runs'
assert p.runs.list()['runs'][0]['submission'] == 'prepared'
assert p.runs.refresh(run_id)['status']['submission'] == 'prepared'
assert r.tasks.list() == []
run = p.runs.submit(run_id)
assert run['status']['submission'] == 'accepted'
assert p.runs.submit(run_id)['status']['task']['id'] == run['status']['task']['id']
p.close()
'''
    result = execute(scripts, session, code)
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    task = client.tasks()[0]
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    source.unlink()
    result = execute(scripts, session, f"p = stk.projects.open({str(tmp_path / 'project')!r})\nassert p.runs.refresh(run_id)['status']['task']['state'] == 'succeeded'\nassert p.snapshot()['project']['revision'] == 4\nassert p.runs.get(run_id)['plan']['parameters']['values'][field] == 300")
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    event = scripts.wait_event(lambda e: e["event"] == "project.runs.changed" and e["data"]["observation_id"] > 0)
    assert event["data"]["observation_id"] > 0
