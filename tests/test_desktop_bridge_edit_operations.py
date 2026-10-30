"""Permanent edit receipts through strict NDJSON, real workers and the public operation catalog."""

from copy import deepcopy
import hashlib
import json
import sqlite3
import threading
from uuid import UUID, uuid4

import pytest

from suan.agent.levels import AGENT_LEVELS, OPERATIONS, TOOL_USES
from suan.desktop_bridge import schema as bridge_schema
from suan.desktop_bridge.protocol import decode_line
from suan.project import ProjectStore
from suan.project.store import DATABASE_NAME
from test_desktop_bridge import bridge_env, inproc, ProcessBridge  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401


APPLY = "project.edit_operations.apply_once"
GET = "project.edit_operations.get"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def test_receipt_binds_the_original_request_and_notifies_only_the_first_apply(inproc, tmp_path):  # noqa: F811
    harness = inproc()
    info = harness.call("project.create", {"directory": str(tmp_path / "project"), "name": "Receipts"})["project"]
    commands = [{"op": "create_table", "name": "原始请求"}]
    params = {"handle": info["handle"], "operation_id": str(uuid4()), "expected_revision": 0, "commands": commands}
    first = harness.call(APPLY, params)
    receipt = first["receipt"]
    assert not first["replayed"]
    assert receipt["format"] == "stk.project-edit-receipt/1" and receipt["scope"] == "local"
    assert receipt["project_id"] == info["id"] and receipt["operation_id"] == params["operation_id"]
    assert receipt["base_revision"] == 0 and receipt["applied_revision"] == 1
    generated = receipt["commands"][0]["id"]
    assert str(UUID(generated)) == generated and "id" not in commands[0]
    request = {"project_id": info["id"], "scope": "local", "operation_id": params["operation_id"],
               "expected_revision": 0, "commands": commands}
    assert receipt["request_sha256"] == hashlib.sha256(canonical(request)).hexdigest()
    assert receipt["sha256"] == hashlib.sha256(canonical({k: v for k, v in receipt.items() if k != "sha256"})).hexdigest()
    assert len(canonical(receipt)) <= 512 * 1024
    harness.wait_event(lambda e: e["event"] == "project.changed")
    assert harness.events_of("project.changed") == [{"handle": info["handle"], "revision": 1}]
    assert harness.call(GET, {"handle": info["handle"], "operation_id": params["operation_id"]}) == {"receipt": receipt}
    # A later ordinary edit keeps its old result shape and cannot retarget the original operation.
    ordinary = harness.call("project.apply", {"handle": info["handle"], "expected_revision": 1,
                                            "commands": [{"op": "create_table", "name": "Later"}]})
    assert set(ordinary) == {"revision", "commands"} and ordinary["revision"] == 2
    assert harness.call(APPLY, params) == {"receipt": receipt, "replayed": True}
    assert harness.error(APPLY, {**params, "expected_revision": 2})["code"] == "conflict"
    assert harness.error(APPLY, {**params, "commands": [{"op": "create_table", "name": "Other"}]})["code"] == "conflict"
    assert harness.call("project.snapshot", {"handle": info["handle"]})["snapshot"]["tables"][0]["id"] == generated
    assert harness.events_of("project.changed") == [{"handle": info["handle"], "revision": 1},
                                                    {"handle": info["handle"], "revision": 2}]
    assert len(harness.call("project.history", {"handle": info["handle"]})["history"]) == 2
    # Both independent schema validators enforce the new response envelope and receipt.
    for change in ({"scope": "bad scope"}, {"sha256": "wrong"}, {"unexpected": True}):
        malformed = deepcopy(first)
        malformed["receipt"].update(change)
        assert bridge_schema.validate_outgoing({"id": 1, "result": malformed}, APPLY)
    assert harness.error(GET, {"handle": info["handle"], "operation_id": str(uuid4())})["code"] == "not_found"
    harness.call("project.close", {"handle": info["handle"]})
    assert harness.error(GET, {"handle": info["handle"], "operation_id": params["operation_id"]})["code"] == "not_found"
    harness.close()


def test_a_lost_reply_is_queried_after_a_real_bridge_process_restart(bridge_env, tmp_path, monkeypatch):  # noqa: F811
    state, directory = bridge_env / "receipt-bridge", tmp_path / "project"
    first = ProcessBridge(state)
    restarted = None
    try:
        first.call("hello", {"protocol": 1})
        info = first.call("project.create", {"directory": str(directory), "name": "Lost reply"})["project"]
        original = first.receive
        dropped = threading.Event()

        def lose_apply_reply(raw):
            message = decode_line(raw)
            original(raw)  # Keep the real strict NDJSON and second-opinion validation.
            if "result" in message and first.methods.get(message.get("id")) == APPLY:
                with first.cond:
                    first.responses.pop(message["id"], None)
                dropped.set()

        monkeypatch.setattr(first, "receive", lose_apply_reply)
        params = {"handle": info["handle"], "operation_id": str(uuid4()), "expected_revision": 0,
                  "commands": [{"op": "create_table", "name": "Accepted once"}]}
        pending = first.request(APPLY, params)
        assert dropped.wait(10)
        first.wait_event(lambda e: e["event"] == "project.changed")
        assert pending not in first.responses  # Caller never consumes the accepted edit's reply.
        first.kill()
        first.assert_clean()
        restarted = ProcessBridge(state)
        reopened = restarted.call("project.open", {"directory": str(directory), "expected_id": info["id"]})["project"]
        receipt = restarted.call(GET, {"handle": reopened["handle"], "operation_id": params["operation_id"]})["receipt"]
        assert receipt["project_id"] == info["id"] and receipt["applied_revision"] == 1
        snapshot = restarted.call("project.snapshot", {"handle": reopened["handle"]})["snapshot"]
        assert snapshot["project"]["revision"] == 1 and len(snapshot["tables"]) == 1
        assert receipt["commands"][0]["id"] == snapshot["tables"][0]["id"]
        assert restarted.call(APPLY, {**params, "handle": reopened["handle"]}) == {"receipt": receipt, "replayed": True}
        assert restarted.events_of("project.changed") == []
    finally:
        if first.process.poll() is None:
            first.kill()
        if restarted is not None:
            assert restarted.close() == 0


@pytest.mark.parametrize("method, change, missing", [
    (APPLY, {"scope": "remote"}, None),
    (GET, {"scope": "local"}, None),
    (APPLY, {}, "operation_id"),
    (APPLY, {}, "expected_revision"),
    (APPLY, {"operation_id": None}, None),
    (APPLY, {"operation_id": "ABCDEFAB-ABCD-4ABC-8ABC-ABCDEFABCDEF"}, None),
    (GET, {"operation_id": "not-a-uuid"}, None),
    (GET, {"expected_revision": 0}, None),
    (APPLY, {"expected_revision": True}, None),
    (APPLY, {"commands": []}, None),
    (APPLY, {"commands": [{"op": "create_table", "name": "A", "typo": True}]}, None),
])
def test_edit_operation_params_are_strict_and_do_not_write(inproc, tmp_path, method, change, missing):  # noqa: F811
    harness = inproc()
    info = harness.call("project.create", {"directory": str(tmp_path / "project"), "name": "Invalid"})["project"]
    params = {"handle": info["handle"], "operation_id": str(uuid4())}
    if method == APPLY:
        params.update(expected_revision=0, commands=[{"op": "create_table", "name": "A"}])
    params.update(change)
    if missing:
        params.pop(missing)
    assert harness.error(method, params)["code"] == "invalid_params"
    assert harness.call("project.snapshot", {"handle": info["handle"]})["snapshot"]["project"]["revision"] == 0
    assert harness.call("project.history", {"handle": info["handle"]})["history"] == []
    assert harness.events_of("project.changed") == []
    harness.close()


def test_bridge_rejects_an_oversize_utf8_request_without_a_receipt(inproc, tmp_path):  # noqa: F811
    harness = inproc()
    info = harness.call("project.create", {"directory": str(tmp_path / "project"), "name": "Budget"})["project"]
    operation_id = str(uuid4())
    # Individual names and command count satisfy the schema; the canonical UTF-8 request does not fit.
    commands = [{"op": "create_table", "name": "字" * 100} for _ in range(1000)]
    assert len(canonical(commands)) > 256 * 1024
    error = harness.error(APPLY, {"handle": info["handle"], "operation_id": operation_id,
                                 "expected_revision": 0, "commands": commands})
    assert error["code"] == "invalid_params"
    assert harness.error(GET, {"handle": info["handle"], "operation_id": operation_id})["code"] == "not_found"
    assert harness.call("project.history", {"handle": info["handle"]})["history"] == []
    assert harness.events_of("project.changed") == []
    harness.close()


def test_old_format_is_not_upgraded_by_receipt_access(inproc, tmp_path):  # noqa: F811
    directory = tmp_path / "old-project"
    ProjectStore.create(directory, "Old format")
    with sqlite3.connect(directory / DATABASE_NAME) as db:
        db.execute("DROP TABLE project_edit_operations")
        db.execute("PRAGMA user_version=14")
    harness = inproc()
    info = harness.call("project.open", {"directory": str(directory)})["project"]
    assert info["format_version"] == 14 and info["revision"] == 0
    params = {"handle": info["handle"], "operation_id": str(uuid4()), "expected_revision": 0,
              "commands": [{"op": "create_table", "name": "Needs explicit upgrade"}]}
    assert harness.error(APPLY, params)["code"] == "unsupported"
    assert harness.error(GET, {"handle": info["handle"], "operation_id": params["operation_id"]})["code"] == "unsupported"
    with sqlite3.connect(directory / DATABASE_NAME) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14
        assert db.execute("SELECT name FROM sqlite_master WHERE name='project_edit_operations'").fetchone() is None
    # The original apply still operates on a format-14 project without creating new receipt storage.
    assert harness.call("project.apply", {"handle": info["handle"], "expected_revision": 0,
                                          "commands": [{"op": "create_table", "name": "Old apply"}]})["revision"] == 1
    upgraded = harness.call("project.upgrade", {"handle": info["handle"], "expected_revision": 1})
    assert upgraded["upgraded"] and upgraded["format_version"] == 15 and upgraded["backup"]
    assert harness.call("project.history", {"handle": info["handle"]})["history"][-1]["commands"] == [
        {"op": "upgrade_format", "from_version": 14, "to_version": 15}]
    result = harness.call(APPLY, {**params, "expected_revision": upgraded["revision"]})
    assert not result["replayed"] and result["receipt"]["base_revision"] == upgraded["revision"]
    harness.close()


def test_public_bridge_fixes_the_scope_and_cannot_read_another_adapter_scope(inproc, tmp_path):  # noqa: F811
    store = ProjectStore.create(tmp_path / "project", "Scopes")
    operation_id = str(uuid4())
    foreign = store.edit_operations.apply_once([{"op": "create_table", "name": "Other adapter"}],
        operation_id=operation_id, expected_revision=0, scope="peer:verified-test-caller")
    harness = inproc()
    info = harness.call("project.open", {"directory": str(store.directory)})["project"]
    assert harness.error(GET, {"handle": info["handle"], "operation_id": operation_id})["code"] == "not_found"
    local = harness.call(APPLY, {"handle": info["handle"], "operation_id": operation_id, "expected_revision": 1,
                                "commands": [{"op": "create_table", "name": "Local caller"}]})
    assert local["receipt"]["scope"] == "local" and not local["replayed"]
    assert local["receipt"]["commands"][0]["id"] != foreign["receipt"]["commands"][0]["id"]
    assert harness.call(GET, {"handle": info["handle"], "operation_id": operation_id}) == {"receipt": local["receipt"]}
    harness.close()


def test_real_python_worker_requires_explicit_ids_and_queries_without_writing(scripts, tmp_path):  # noqa: F811
    info = scripts.call("project.create", {"directory": str(tmp_path / "project"), "name": "Python"})["project"]
    session = scripts.call("script.open")["session"]
    operation_id = str(uuid4())
    source = f'''
p = stk.project
commands = [{{"op": "create_table", "name": "Python receipt"}}]
operation_id = {operation_id!r}
first = p.edit_operations.apply_once(commands, operation_id=operation_id, expected_revision=0)
assert first['replayed'] is False
assert p.edit_operations.get(operation_id) == first['receipt']
assert p.edit_operations.apply_once(commands, operation_id=operation_id, expected_revision=0) == {{'receipt': first['receipt'], 'replayed': True}}
try:
    p.edit_operations.apply_once(commands, expected_revision=1)
except TypeError:
    pass
else:
    raise AssertionError('an operation identity was silently generated')
try:
    p.edit_operations.apply_once(commands, operation_id=operation_id)
except TypeError:
    pass
else:
    raise AssertionError('a base revision was silently selected')
assert p.snapshot()['project']['revision'] == 1
'''
    result = execute(scripts, session, source, project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    receipt = scripts.call(GET, {"handle": info["handle"], "operation_id": operation_id})["receipt"]
    assert scripts.events_of("project.changed") == [{"handle": info["handle"], "revision": 1}]
    scripts.call("script.close", {"session": session})
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, f"p = stk.project\nassert p.edit_operations.get({operation_id!r}) == {receipt!r}\n"
                     "assert p.snapshot()['project']['revision'] == 1", project_handle=info["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert scripts.events_of("project.changed") == [{"handle": info["handle"], "revision": 1}]


def test_edit_receipts_are_discoverable_but_do_not_expand_agent_tools(inproc):  # noqa: F811
    harness = inproc()
    hello = harness.call("hello", {"protocol": 1})
    catalog = harness.call("script.catalog")["operations"]
    assert {APPLY, GET} <= set(hello["methods"]) & set(catalog)
    assert OPERATIONS[APPLY][0] == "project_edit" and OPERATIONS[GET][0] == "read"
    assert AGENT_LEVELS == ("read", "record", "model", "draft")
    assert not {APPLY, GET} & {operation for operations in TOOL_USES.values() for operation in operations}
    assert "scope" not in catalog[APPLY]["params"]["properties"]
    assert "scope" not in catalog[GET]["params"]["properties"]
    harness.close()
