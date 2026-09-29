"""The local project extension over the real bridge envelope and strict shared schema."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from suan.project.store import DATABASE_NAME, FORMAT_VERSION
from test_desktop_bridge import bridge_env, inproc, ProcessBridge  # noqa: F401
from test_project_values import model, legacy, command, reference  # noqa: F401
from test_project_files import files  # noqa: F401


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


def test_files_bridge_metadata_edits_resolution_and_undo_follow_shared_contract(inproc, files):
    store, inside, _ = files
    harness = inproc()
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    result = harness.call("project.files.index", {"handle": handle, "paths": [str(inside)], "expected_revision": 0})
    identity = result["record_ids"][0]
    assert result["revision"] == 1
    assert harness.wait_event(lambda event: event["event"] == "project.changed")["data"] == {"handle": handle, "revision": 1}
    snapshot = harness.call("project.snapshot", {"handle": handle})["snapshot"]
    assert snapshot["file_index"]["compatible"]
    assert harness.call("project.files.list", {"handle": handle})["records"][0]["id"] == identity
    assert harness.call("project.files.resolve", {"handle": handle, "record_id": identity, "expected_revision": 1})["path"] == str(inside)
    assert harness.error("project.files.resolve", {"handle": handle, "record_id": identity, "expected_revision": 0})["code"] == "conflict"
    inside.unlink()
    assert harness.call("project.files.refresh", {"handle": handle, "record_ids": [identity], "expected_revision": 1})["revision"] == 2
    assert harness.call("project.files.list", {"handle": handle})["records"][0]["state"] == "missing"
    harness.call("project.undo", {"handle": handle, "expected_revision": 2})
    assert harness.call("project.files.list", {"handle": handle})["records"][0]["state"] == "present"
    assert not inside.exists()
    assert not harness.violations


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


def test_preview_uses_strict_contract_without_changed_events_until_apply(inproc, tmp_path):
    harness = inproc()
    info = harness.call("project.create", {"directory": str(tmp_path / "preview"), "name": "Preview"})["project"]
    assert "project.preview" in harness.call("hello", {"protocol": 1})["methods"]
    params = {"handle": info["handle"], "expected_revision": 0, "commands": [{"op": "create_table", "name": "Proposal"}]}
    preview = harness.call("project.preview", params)
    assert preview["persisted"] is False and preview["base_revision"] == 0
    assert preview["snapshot"]["project"]["revision"] == 1
    assert harness.call("project.snapshot", {"handle": info["handle"]})["snapshot"]["tables"] == []
    assert harness.events_of("project.changed") == []
    assert harness.call("project.history", {"handle": info["handle"]})["history"] == []
    harness.call("project.apply", {**params, "commands": preview["commands"]})
    assert harness.call("project.snapshot", {"handle": info["handle"]})["snapshot"] == preview["snapshot"]
    assert harness.wait_event(lambda event: event["event"] == "project.changed")["data"]["revision"] == 1
    assert harness.error("project.preview", params)["code"] == "conflict"
    harness.call("project.close", {"handle": info["handle"]})
    assert harness.error("project.preview", params)["code"] == "not_found"
    assert not harness.violations


def test_saved_drafts_keep_revision_and_ids_across_reopen_and_apply_only_once(inproc, tmp_path):
    harness = inproc()
    directory = tmp_path / "drafts"
    project = harness.call("project.create", {"directory": str(directory), "name": "Drafts"})["project"]
    handle = project["handle"]
    assert {f"project.drafts.{action}" for action in ("save", "get", "list", "apply", "discard")} <= set(
        harness.call("hello", {"protocol": 1})["methods"])
    before = harness.call("project.snapshot", {"handle": handle})["snapshot"]
    params = {"handle": handle, "draft_id": str(uuid4()), "title": "参数表草案", "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Cases"}]}
    draft = harness.call("project.drafts.save", params)["draft"]
    assert draft["project_id"] == project["id"] and draft["base_revision"] == 0
    assert draft["status"] == "pending" and draft["applied_revision"] is None and draft["closed_at"] is None
    table_id = draft["commands"][0]["id"]
    assert harness.call("project.drafts.save", params)["draft"] == draft
    assert harness.call("project.snapshot", {"handle": handle})["snapshot"] == before
    assert harness.call("project.history", {"handle": handle})["history"] == []
    assert harness.events_of("project.changed") == []
    summary = {key: value for key, value in draft.items() if key != "commands"}
    assert harness.call("project.drafts.list", {"handle": handle}) == {"drafts": [summary], "next_offset": None}
    assert harness.error("project.drafts.save", {**params, "title": "Different intent"})["code"] == "conflict"

    harness.call("project.close", {"handle": handle})
    assert harness.error("project.drafts.get", {"handle": handle, "draft_id": draft["id"]})["code"] == "not_found"
    reopened = harness.call("project.open", {"directory": str(directory)})["project"]
    identity = {"handle": reopened["handle"], "draft_id": draft["id"]}
    assert harness.call("project.drafts.get", identity)["draft"] == draft
    applied = harness.call("project.drafts.apply", {**identity, "expected_revision": 0})
    assert applied["revision"] == 1 and applied["replayed"] is False
    assert applied["draft"]["status"] == "applied" and applied["draft"]["applied_revision"] == 1
    assert applied["draft"]["closed_at"]
    harness.wait_event(lambda event: event["event"] == "project.changed")
    assert ProjectStore(directory).snapshot()["tables"][0]["id"] == table_id
    harness.call("project.undo", {"handle": reopened["handle"], "expected_revision": 1})
    harness.wait_event(lambda event: event["event"] == "project.changed" and event["data"]["revision"] == 2)
    changed = harness.events_of("project.changed")
    replay = harness.call("project.drafts.apply", {**identity, "expected_revision": 0})
    assert replay["replayed"] is True and replay["draft"] == applied["draft"]
    assert harness.call("project.snapshot", {"handle": reopened["handle"]})["snapshot"]["tables"] == []
    assert ProjectStore(directory).info()["revision"] == 2
    assert harness.events_of("project.changed") == changed
    assert not harness.violations


def test_saved_draft_pagination_discard_and_invalid_requests(inproc, tmp_path):
    harness = inproc()
    info = harness.call("project.create", {"directory": str(tmp_path / "drafts"), "name": "Drafts"})["project"]
    handle = info["handle"]
    params = {"handle": handle, "draft_id": str(uuid4()), "title": "Pending", "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Cases"}]}
    first = harness.call("project.drafts.save", params)["draft"]
    second = harness.call("project.drafts.save", {**params, "draft_id": str(uuid4()), "title": "Other"})["draft"]
    page = harness.call("project.drafts.list", {"handle": handle, "limit": 1})
    assert len(page["drafts"]) == 1 and page["next_offset"] == 1
    rest = harness.call("project.drafts.list", {"handle": handle, "offset": page["next_offset"], "limit": 1})
    assert rest["next_offset"] is None
    assert {draft["id"] for draft in page["drafts"] + rest["drafts"]} == {first["id"], second["id"]}
    identity = {"handle": handle, "draft_id": first["id"]}
    discarded = harness.call("project.drafts.discard", identity)["draft"]
    assert discarded["status"] == "discarded" and discarded["closed_at"] and discarded["applied_revision"] is None
    assert harness.call("project.drafts.discard", identity)["draft"] == discarded
    assert harness.error("project.drafts.apply", {**identity, "expected_revision": 0})["code"] == "conflict"
    assert harness.call("project.snapshot", {"handle": handle})["snapshot"]["project"]["revision"] == 0
    assert harness.call("project.history", {"handle": handle})["history"] == []
    assert harness.events_of("project.changed") == []
    for invalid in ({"commands": []}, {"commands": [{"op": "submit_job"}]}, {"draft_id": "invalid"},
                    {"title": ""}, {"title": "x" * 1025}, {"expected_revision": True}):
        assert harness.error("project.drafts.save", {**params, "draft_id": str(uuid4()), **invalid})["code"] == "invalid_params"
    assert harness.error("project.drafts.list", {"handle": handle, "limit": 101})["code"] == "invalid_params"
    assert harness.error("project.drafts.list", {"handle": handle, "offset": -1})["code"] == "invalid_params"


def test_saved_drafts_require_explicit_format_upgrade(inproc, model):
    store, _ = model
    legacy(store)
    harness = inproc()
    info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    identity = {"handle": info["handle"], "draft_id": str(uuid4())}
    requests = {"list": {"handle": info["handle"]}, "get": identity, "discard": identity,
                "apply": {**identity, "expected_revision": 1},
                "save": {**identity, "commands": [{"op": "create_table", "name": "Cases"}],
                         "expected_revision": 1, "title": "Upgrade first"}}
    for action, params in requests.items():
        assert harness.error(f"project.drafts.{action}", params)["code"] == "unsupported"
    assert store.info()["format_version"] == 1 and store.info()["revision"] == 1
    assert harness.events_of("project.changed") == []
    assert not harness.violations


def test_context_discussion_metadata_freezes_selection_and_links_without_applying(inproc, model):
    store, ids = model
    harness = inproc()
    info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    handle = info["handle"]
    baseline, history = store.snapshot(), store.history()
    params = {"handle": handle, "context_id": str(uuid4()), "title": "选定温度",
              "table_id": ids["inputs"], "record_ids": [ids["input_row"]], "field_ids": [ids["temperature"]],
              "expected_revision": 1}
    captured = harness.call("project.contexts.capture", params)["context"]
    assert captured["project_id"] == info["id"] and captured["source_revision"] == 1
    assert captured["selection"] == {key: params[key] for key in ("table_id", "record_ids", "field_ids")}
    record = captured["content"]["value"]["records"][0]
    assert record["literals"] == {ids["temperature"]: {"state": "included", "value": 300}}
    assert harness.call("project.contexts.capture", params)["context"] == captured
    summary = harness.call("project.contexts.list", {"handle": handle})
    assert len(summary["contexts"]) == 1 and summary["next_offset"] is None
    assert "value" not in summary["contexts"][0]["content"]
    message_params = {"handle": handle, "message_id": str(uuid4()), "context_id": captured["id"],
                      "text": "请检查温度；`stk.project.apply(...)` 只是讨论文本。"}
    message = harness.call("project.discussion.add", message_params)["message"]
    assert message["role"] == "user" and message["text"] == message_params["text"]
    assert harness.call("project.discussion.add", message_params)["message"] == message
    second = harness.call("project.discussion.add", {**message_params, "message_id": str(uuid4()),
        "role": "assistant", "text": "建议先核对参数，再明确应用。"})["message"]
    page = harness.call("project.discussion.list", {"handle": handle, "limit": 1})
    assert page["next_offset"] == 1 and page["messages"][0]["id"] == message["id"]
    assert "text" not in page["messages"][0]
    assert page["messages"][0]["text_bytes"] == len(message["text"].encode("utf-8"))
    assert harness.call("project.discussion.list", {"handle": handle, "offset": 1})["messages"][0]["id"] == second["id"]
    draft = harness.call("project.drafts.save", {"handle": handle, "draft_id": str(uuid4()), "title": "Temperature change",
        "commands": [command(ids, "temperature", "set_cell", value=350)], "expected_revision": 1})["draft"]
    link_params = {"handle": handle, "proposal_id": str(uuid4()), "message_id": second["id"], "draft_id": draft["id"]}
    proposal = harness.call("project.discussion.link_draft", link_params)["proposal"]
    assert proposal["context_id"] == captured["id"] and proposal["base_revision"] == 1
    assert harness.call("project.discussion.link_draft", link_params)["proposal"] == proposal
    assert harness.call("project.discussion.proposals", {"handle": handle, "draft_id": draft["id"]}) == {
        "proposals": [proposal], "next_offset": None}
    assert harness.call("project.discussion.proposals", {"handle": handle, "draft_id": str(uuid4())})["proposals"] == []
    assert store.snapshot() == baseline and store.history() == history
    assert harness.events_of("project.changed") == []

    store.apply([command(ids, "temperature", "set_cell", value=500)], expected_revision=1)
    assert harness.call("project.contexts.get", {"handle": handle, "context_id": captured["id"]})["context"] == captured
    assert harness.call("project.contexts.capture", params)["context"] == captured
    assert harness.error("project.contexts.capture", {**params, "context_id": str(uuid4())})["code"] == "conflict"
    newer = harness.call("project.drafts.save", {"handle": handle, "draft_id": str(uuid4()), "title": "Current",
        "commands": [command(ids, "temperature", "set_cell", value=550)], "expected_revision": 2})["draft"]
    assert harness.error("project.discussion.link_draft", {**link_params, "proposal_id": str(uuid4()),
        "draft_id": newer["id"]})["code"] == "conflict"
    harness.call("project.close", {"handle": handle})
    assert harness.error("project.contexts.get", {"handle": handle, "context_id": captured["id"]})["code"] == "not_found"
    opened = harness.call("project.open", {"directory": str(store.directory)})["project"]
    assert harness.call("project.discussion.get", {"handle": opened["handle"], "message_id": message["id"]})["message"] == message
    assert harness.call("project.discussion.proposals", {"handle": opened["handle"]})["proposals"] == [proposal]
    assert store.drafts.get(draft["id"])["status"] == "pending"
    assert harness.events_of("project.changed") == []
    assert not harness.violations


def test_context_discussion_rejects_ambiguous_ranges_and_excessive_text(inproc, model):
    store, ids = model
    harness = inproc()
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    params = {"handle": handle, "context_id": str(uuid4()), "title": "Selected",
              "table_id": ids["inputs"], "record_ids": [ids["input_row"]], "field_ids": [ids["temperature"]],
              "expected_revision": 1}
    for invalid in ({"record_ids": []}, {"field_ids": []}, {"record_ids": [ids["input_row"]] * 2},
                    {"field_ids": [ids["temperature"]] * 2}, {"title": ""}, {"expected_revision": True},
                    {"record_ids": [str(uuid4()) for _ in range(100)], "field_ids": [str(uuid4()) for _ in range(11)]}):
        assert harness.error("project.contexts.capture", {**params, **invalid})["code"] == "invalid_params"
    context = harness.call("project.contexts.capture", params)["context"]
    assert harness.error("project.contexts.capture", {**params, "title": "Different"})["code"] == "conflict"
    message = {"handle": handle, "context_id": context["id"], "message_id": str(uuid4()), "text": "hello"}
    for invalid in ({"text": ""}, {"text": "中" * 22000}, {"role": "tool"}, {"execute": True}):
        assert harness.error("project.discussion.add", {**message, **invalid})["code"] == "invalid_params"
    saved = harness.call("project.discussion.add", message)["message"]
    assert harness.error("project.discussion.add", {**message, "text": "Different"})["code"] == "conflict"
    assert harness.call("project.discussion.get", {"handle": handle, "message_id": saved["id"]})["message"] == saved
    for method in ("project.contexts.list", "project.discussion.list", "project.discussion.proposals"):
        assert harness.error(method, {"handle": handle, "limit": 101})["code"] == "invalid_params"
        assert harness.error(method, {"handle": handle, "offset": -1})["code"] == "invalid_params"
    assert store.info()["revision"] == 1 and harness.events_of("project.changed") == []
    assert not harness.violations


def test_context_discussion_requires_explicit_upgrade_from_format_six(inproc, tmp_path):
    from suan.project import store as storage

    directory = tmp_path / "format-six"
    directory.mkdir()
    with sqlite3.connect(directory / DATABASE_NAME) as db:
        for statement in (*storage._DDL, *storage._DDL_V2, *storage._DDL_V3, *storage._DDL_V4,
                          *storage._DDL_V5, *storage._DDL_V6):
            db.execute(statement)
        db.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        db.execute("PRAGMA user_version=6")
        db.execute("INSERT INTO project VALUES (?, 'Format six', 0)", (str(uuid4()),))
    harness = inproc()
    project = harness.call("project.open", {"directory": str(directory)})["project"]
    assert project["format_version"] == 6
    handle = project["handle"]
    context, message, draft, proposal = (str(uuid4()) for _ in range(4))
    requests = {
        "project.contexts.capture": {"context_id": context, "title": "Selected", "expected_revision": 0,
            "table_id": str(uuid4()), "record_ids": [str(uuid4())], "field_ids": [str(uuid4())]},
        "project.contexts.get": {"context_id": context}, "project.contexts.list": {},
        "project.discussion.add": {"context_id": context, "message_id": message, "text": "Notes"},
        "project.discussion.get": {"message_id": message}, "project.discussion.list": {},
        "project.discussion.link_draft": {"message_id": message, "draft_id": draft, "proposal_id": proposal},
        "project.discussion.proposals": {},
    }
    for method, params in requests.items():
        assert harness.error(method, {"handle": handle, **params})["code"] == "unsupported"
    assert ProjectStore(directory).info()["revision"] == 0
    assert harness.events_of("project.changed") == []
    upgraded = harness.call("project.upgrade", {"handle": handle, "expected_revision": 0})
    assert upgraded["format_version"] == 7 and upgraded["revision"] == 1 and upgraded["backup"]
    assert harness.call("project.contexts.list", {"handle": handle}) == {"contexts": [], "next_offset": None}
    assert harness.call("project.discussion.list", {"handle": handle}) == {"messages": [], "next_offset": None}
    assert harness.call("project.discussion.proposals", {"handle": handle}) == {"proposals": [], "next_offset": None}
    assert not harness.violations


def test_context_schema_preserves_omissions_missing_ids_and_unavailable_evaluations(inproc, model):
    store, ids = model
    oversized, derived = str(uuid4()), str(uuid4())
    bulk = [str(uuid4()) for _ in range(21)]
    commands = []
    for identity in [oversized, *bulk]:
        commands.extend([
            {"op": "add_field", "id": identity, "table_id": ids["inputs"], "name": identity, "type": "text"},
            {"op": "set_cell", "table_id": ids["inputs"], "record_id": ids["input_row"], "field_id": identity,
             "value": "x" * (17000 if identity == oversized else 13000)},
        ])
    commands.extend([
        {"op": "add_field", "id": derived, "table_id": ids["inputs"], "name": "Derived", "type": "number", "unit": "K"},
        {"op": "set_expression", "table_id": ids["inputs"], "record_id": ids["input_row"], "field_id": derived,
         "expression": "base * 2", "bindings": {"base": reference(ids, "temperature")}},
    ])
    store.apply(commands, expected_revision=1)
    with sqlite3.connect(store.path) as db:
        db.execute("DELETE FROM evaluations WHERE field_id=?", (derived,))
    harness = inproc()
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    missing_record, missing_field = str(uuid4()), str(uuid4())
    base = {"handle": handle, "table_id": ids["inputs"], "title": "Omissions", "expected_revision": 2}
    context = harness.call("project.contexts.capture", {**base, "context_id": str(uuid4()),
        "record_ids": [ids["input_row"], missing_record], "field_ids": [oversized, derived, missing_field]})["context"]
    assert context["content"]["state"] == "included"
    assert context["diagnostics"] == {"table_missing": False, "record_ids": [missing_record], "field_ids": [missing_field]}
    record = context["content"]["value"]["records"][0]
    assert record["literals"][oversized]["reason"] == "value_limit"
    assert record["evaluations"][derived]["reason"] == "evaluation_unavailable"
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluations WHERE field_id=?", (derived,)).fetchone()[0] == 0
    omitted = harness.call("project.contexts.capture", {**base, "context_id": str(uuid4()),
        "record_ids": [ids["input_row"]], "field_ids": bulk})["context"]
    assert omitted["content"]["state"] == "omitted" and omitted["content"]["reason"] == "context_limit"
    assert "value" not in omitted["content"] and omitted["content"]["size_bytes"] > 262144
    summaries = harness.call("project.contexts.list", {"handle": handle})["contexts"]
    assert len(summaries) == 2 and all("value" not in item["content"] for item in summaries)
    assert harness.events_of("project.changed") == []
    assert not harness.violations
