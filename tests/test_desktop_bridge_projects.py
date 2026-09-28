"""The local project extension over the real bridge envelope and strict shared schema."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

import pytest

from suan.project import ProjectStore
from suan.project.store import DATABASE_NAME, FORMAT_VERSION
from test_desktop_bridge import bridge_env, inproc, ProcessBridge  # noqa: F401
from test_project_values import model, legacy, command, reference  # noqa: F401


def test_project_lifecycle_edits_events_and_reopen(inproc, tmp_path):  # noqa: F811
    harness = inproc()
    hello = harness.call("hello", {"protocol": 1})
    assert "project.apply" in hello["methods"] and "project.changed" in hello["events"]
    directory = tmp_path / "项目 with spaces"
    project = harness.call("project.create", {"directory": str(directory), "name": "批次"})["project"]
    handle = project["handle"]
    assert project["revision"] == 0 and project["format_version"] == FORMAT_VERSION
    assert harness.call("project.open", {"directory": str(directory)})["project"] == project
    assert harness.call("project.list")["projects"] == [project]
    result = harness.call("project.apply", {"handle": handle, "expected_revision": 0,
                                          "commands": [{"op": "create_table", "name": "Cases"}]})
    changed = harness.wait_event(lambda e: e["event"] == "project.changed")
    assert changed["data"] == {"handle": handle, "revision": 1}
    snapshot = harness.call("project.snapshot", {"handle": handle})["snapshot"]
    assert snapshot["project"]["revision"] == 1
    assert snapshot["tables"][0]["id"] == result["commands"][0]["id"]
    assert harness.call("project.history", {"handle": handle})["history"][0]["commands"] == result["commands"]
    assert harness.call("project.close", {"handle": handle}) == {"closed": True}
    assert harness.wait_event(lambda e: e["event"] == "project.closed")["data"] == {"handle": handle}
    assert harness.call("project.close", {"handle": handle}) == {"closed": False}
    assert harness.call("project.list")["projects"] == []
    assert harness.error("project.snapshot", {"handle": handle})["code"] == "not_found"
    reopened = harness.call("project.open", {"directory": str(directory)})["project"]
    assert reopened["id"] == project["id"] and reopened["handle"] != handle
    assert reopened["revision"] == 1
    harness.close()


def test_bridge_upgrade_backup_and_derived_values_use_the_shared_contract(inproc, model):
    store, ids = model
    legacy(store)
    harness = inproc()
    info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    handle = info["handle"]
    assert info["format_version"] == 1
    upgraded = harness.call("project.upgrade", {"handle": handle, "expected_revision": 1})
    assert upgraded["upgraded"] and upgraded["revision"] == 2 and upgraded["backup"]["revision"] == 1
    assert harness.wait_event(lambda event: event["event"] == "project.changed")["data"] == {"handle": handle, "revision": 2}
    assert harness.call("project.history", {"handle": handle})["history"][-1]["commands"][0]["op"] == "upgrade_format"
    assert harness.error("project.upgrade", {"handle": handle, "expected_revision": 1})["code"] == "conflict"
    edits = [command(ids, "copy", "set_reference", source=reference(ids, "temperature")),
             command(ids, "derived", "set_expression", expression="base * 2", bindings={"base": reference(ids, "copy")})]
    assert harness.call("project.apply", {"handle": handle, "expected_revision": 2, "commands": edits})["revision"] == 3
    snapshot = harness.call("project.snapshot", {"handle": handle})["snapshot"]
    row = snapshot["tables"][1]["records"][0]
    assert row["values"][ids["derived"]] == 600
    assert row["definitions"][ids["derived"]]["bindings"] == {"base": reference(ids, "copy")}
    assert harness.call("project.backup", {"handle": handle})["revision"] == 3
    assert harness.call("project.list")["projects"][0]["format_version"] == FORMAT_VERSION
    assert not harness.violations


def test_revision_conflict_invalid_batch_and_external_edits(inproc, tmp_path):  # noqa: F811
    harness = inproc()
    directory = tmp_path / "run"
    project = harness.call("project.create", {"directory": str(directory), "name": "A"})["project"]
    params = {"handle": project["handle"], "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "A"}]}
    first = harness.call("project.apply", params)
    assert harness.error("project.apply", params)["code"] == "conflict"
    bad = {**params, "expected_revision": 1, "commands": [
        {"op": "create_table", "name": "Must roll back"},
        {"op": "create_table", "id": first["commands"][0]["id"], "name": "Duplicate"},
    ]}
    assert harness.error("project.apply", bad)["code"] == "invalid_params"
    assert len(harness.call("project.history", {"handle": project["handle"]})["history"]) == 1
    store = ProjectStore(directory)
    store.apply([{"op": "create_table", "name": "CLI"}], expected_revision=1)
    snapshot = harness.call("project.snapshot", {"handle": project["handle"]})["snapshot"]
    assert snapshot["project"]["revision"] == 2
    assert len(snapshot["tables"]) == 2
    assert harness.call("project.list")["projects"][0]["revision"] == 2
    harness.close()


def test_undo_redo_emit_revisions_and_reject_replays_over_the_strict_contract(inproc, model):
    store, ids = model
    harness = inproc()
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    before = harness.call("project.snapshot", {"handle": handle})["snapshot"]
    assert before["edit_history"] == {"undo_revision": 1, "redo_revision": None}
    mark = harness.mark()
    assert harness.call("project.undo", {"handle": handle, "expected_revision": 1}) == {"revision": 2, "target_revision": 1}
    assert harness.wait_event(lambda event: event["event"] == "project.changed", start=mark)["data"] == {"handle": handle, "revision": 2}
    assert harness.error("project.undo", {"handle": handle, "expected_revision": 1})["code"] == "conflict"
    assert harness.call("project.snapshot", {"handle": handle})["snapshot"]["tables"] == []
    assert harness.call("project.redo", {"handle": handle, "expected_revision": 2}) == {"revision": 3, "target_revision": 1}
    assert harness.call("project.snapshot", {"handle": handle})["snapshot"]["tables"] == before["tables"]
    assert harness.call("project.history", {"handle": handle})["history"][-1]["commands"] == [{"op": "redo", "target_revision": 1}]
    assert not harness.violations


def test_project_error_codes_and_schema_reject_invalid_requests(inproc, tmp_path):  # noqa: F811
    harness = inproc()
    missing = tmp_path / "missing"
    assert harness.error("project.open", {"directory": str(missing)})["code"] == "not_found"
    assert not missing.exists()
    assert harness.error("project.create", {"directory": "relative", "name": "A"})["code"] == "invalid_params"
    project = harness.call("project.create", {"directory": str(missing), "name": "A"})["project"]
    assert harness.error("project.create", {"directory": str(missing), "name": "B"})["code"] == "conflict"
    for params in (
        {"handle": "no-such"},
        {"handle": project["handle"], "expected_revision": 0, "commands": []},
        {"handle": project["handle"], "expected_revision": True, "commands": [{"op": "create_table", "name": "A"}]},
        {"handle": project["handle"], "expected_revision": 0, "commands": [{"op": "submit_job"}]},
        {"handle": project["handle"], "expected_revision": 0, "commands": [{"op": "create_table", "name": "A", "typo": 1}]},
    ):
        assert harness.error("project.apply", params)["code"] == "invalid_params"
    with sqlite3.connect(missing / DATABASE_NAME) as db:
        db.execute("PRAGMA user_version=999")
    assert harness.error("project.open", {"directory": str(missing)})["code"] == "unsupported"
    harness.close()


def test_close_serializes_with_an_accepted_edit(inproc, tmp_path, monkeypatch):  # noqa: F811
    harness = inproc()
    project = harness.call("project.create", {"directory": str(tmp_path / "run"), "name": "A"})["project"]
    handle = project["handle"]
    original = ProjectStore.apply
    started, release = threading.Event(), threading.Event()

    def slow_apply(self, *args, **kwargs):
        started.set()
        assert release.wait(5)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ProjectStore, "apply", slow_apply)
    try:
        pending = harness.request("project.apply", {"handle": handle, "expected_revision": 0,
                                                   "commands": [{"op": "create_table", "name": "A"}]})
        assert started.wait(5)
        closed = harness.request("project.close", {"handle": handle})
        with harness.cond:
            assert closed not in harness.responses
        release.set()
        assert harness.response(pending)["result"]["revision"] == 1
        assert harness.response(closed)["result"]["closed"]
        assert ProjectStore(tmp_path / "run").info()["revision"] == 1
    finally:
        release.set()
        harness.close()


def test_two_projects_keep_edits_separate_and_concurrent_open_deduplicates(inproc, tmp_path):  # noqa: F811
    harness = inproc()
    projects = [harness.call("project.create", {"directory": str(tmp_path / name), "name": name})["project"]
                for name in ("a", "b")]
    harness.call("project.apply", {"handle": projects[0]["handle"], "expected_revision": 0,
                                   "commands": [{"op": "create_table", "name": "Only A"}]})
    assert harness.call("project.snapshot", {"handle": projects[1]["handle"]})["snapshot"]["tables"] == []
    with ThreadPoolExecutor(max_workers=2) as pool:
        handles = list(pool.map(lambda _: harness.call("project.open", {"directory": str(tmp_path / "b")})["project"]["handle"], range(2)))
    assert handles == [projects[1]["handle"]] * 2
    assert len(harness.call("project.list")["projects"]) == 2
    harness.close()


def test_shutdown_does_not_wait_again_on_an_inflight_database_operation():
    from suan.desktop_bridge.projects import ProjectSessions
    from suan.desktop_bridge.protocol import BridgeError

    sessions = ProjectSessions()
    acquired, release = threading.Event(), threading.Event()

    def hold():
        with sessions._operation():
            acquired.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(hold)
        assert acquired.wait(5)
        try:
            sessions.shutdown()
        finally:
            release.set()
        pending.result(timeout=5)
    with pytest.raises(BridgeError, match="closed"):
        sessions.list({})


def test_process_restart_keeps_data_but_invalidates_handles(bridge_env, tmp_path):  # noqa: F811
    state = bridge_env / "process-project"
    directory = tmp_path / "project"
    harness = ProcessBridge(state)
    try:
        project = harness.call("project.create", {"directory": str(directory), "name": "Persistent"})["project"]
        harness.call("project.apply", {"handle": project["handle"], "expected_revision": 0,
                                       "commands": [{"op": "create_table", "name": "Saved"}]})
        harness.kill()
    finally:
        harness.close()
    restarted = ProcessBridge(state)
    try:
        assert restarted.call("project.list")["projects"] == []
        assert restarted.error("project.snapshot", {"handle": project["handle"]})["code"] == "not_found"
        opened = restarted.call("project.open", {"directory": str(directory)})["project"]
        assert opened["id"] == project["id"] and opened["revision"] == 1
        assert opened["handle"] != project["handle"]
    finally:
        restarted.close()
