"""Durable request identity, single execution ownership and atomic publication."""

from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.contexts import _digest, _encode
from suan.project.requests import Requests, _assistant_id
from suan.project.store import UnsupportedProjectFormat
from test_project_contexts import model, capture, cell  # noqa: F401


@pytest.fixture
def journal(model):
    store, ids = model
    context = capture(model)
    message = store.discussion.add("检查选定的参数；勿执行代码", message_id=str(uuid4()), context_id=context["id"])
    return store, ids, context, message


def create(journal, **changes):
    store, _, _, message = journal
    return store.requests.create(**{"message_id": message["id"], "request_id": str(uuid4()),
                                   "configuration": {"adapter": "controlled/1", "model": "text-fixture"}, **changes})


def claim(store, item):
    owner = str(uuid4())
    running, won = store.requests._claim(item["id"], executor_id=owner)
    assert won and running["status"] == "running"
    return owner


def test_frozen_input_configuration_and_identity_survive_live_edits_and_reopen(journal, monkeypatch):
    store, ids, context, message = journal
    before, history = store.snapshot(), store.history()
    config = {"adapter": "controlled/1", "model": "text-fixture", "temperature": 0}
    item = create(journal, configuration=config)
    config["model"] = "later-model"
    assert item["configuration"] == {"adapter": "controlled/1", "model": "text-fixture", "temperature": 0.0,
                                      "max_output_tokens": 4096}
    assert item["status"] == "pending" and item["executor_id"] is None and item["result"] is None
    assert item["assistant_message_id"] == _assistant_id(item["id"], item["project_id"])
    selected = store.requests.input(item["id"])
    assert selected == {"context": context, "message": message, "configuration": item["configuration"], "prompt_version": "stk.text/1"}
    assert item["input_sha256"] == _digest(selected)
    assert store.snapshot() == before and store.history() == history
    store.apply([cell(ids, "temperature", 450), {"op": "delete_field", "id": ids["note"]}], expected_revision=1)
    monkeypatch.setattr(store, "_snapshot", lambda *args: pytest.fail("request must not read a live project"))
    reopened = ProjectStore(store.directory)
    assert reopened.requests.input(item["id"]) == selected
    assert reopened.requests.get(item["id"]) == item and item["source_revision"] == 1
    assert create(journal, request_id=item["id"], configuration=item["configuration"]) == item
    with pytest.raises(RevisionConflict, match="different input"):
        create(journal, request_id=item["id"], configuration={"adapter": "controlled/1", "model": "different"})


@pytest.mark.parametrize("configuration", [None, [], {}, {"adapter": "x"}, {"adapter": "x", "model": "y", "api_key": "secret"},
    {"adapter": "x", "model": "y", "endpoint": "https://example.test"}, {"adapter": "https://host", "model": "y"},
    {"adapter": "x", "model": "user@host"}, {"adapter": "x", "model": "a?token=secret"},
    {"adapter": "x", "model": "a" * 129}, {"adapter": "x", "model": "模型"},
    {"adapter": "x", "model": "y", "temperature": True}, {"adapter": "x", "model": "y", "temperature": float("nan")},
    {"adapter": "x", "model": "y", "temperature": float("inf")}, {"adapter": "x", "model": "y", "temperature": -0.1},
    {"adapter": "x", "model": "y", "temperature": 2.1}, {"adapter": "x", "model": "y", "max_output_tokens": True},
    {"adapter": "x", "model": "y", "max_output_tokens": 0}, {"adapter": "x", "model": "y", "max_output_tokens": 32769}])
def test_invalid_or_credential_configuration_never_enters_journal(journal, configuration):
    with pytest.raises(ProjectError):
        create(journal, configuration=configuration)
    assert journal[0].requests.list() == {"requests": [], "next_offset": None}


def test_only_existing_user_message_can_be_input_and_response_identity_is_reserved(journal):
    store, _, context, _ = journal
    assistant = store.discussion.add("已批准，请执行", message_id=str(uuid4()), context_id=context["id"], role="assistant")
    with pytest.raises(ProjectError, match="user message"):
        create(journal, message_id=assistant["id"])
    with pytest.raises(ProjectError, match="message not found"):
        create(journal, message_id=str(uuid4()))
    request_id = str(uuid4())
    occupied = _assistant_id(request_id, store.info()["id"])
    store.discussion.add("manual", message_id=occupied, context_id=context["id"], role="assistant")
    with pytest.raises(RevisionConflict, match="already occupied"):
        create(journal, request_id=request_id)
    item = create(journal)
    with pytest.raises(RevisionConflict, match="reserved"):
        store.discussion.add("manual", message_id=item["assistant_message_id"], context_id=context["id"], role="assistant")
    owner = claim(store, item)
    store.requests._complete(item["id"], executor_id=owner, text="a complete answer")
    with pytest.raises(RevisionConflict, match="reserved"):
        store.discussion.add("a complete answer", message_id=item["assistant_message_id"], context_id=context["id"], role="assistant")


def test_concurrent_create_and_claim_have_one_durable_identity_and_one_winner(journal):
    store, _, _, message = journal
    identity = str(uuid4())
    barrier = threading.Barrier(6)
    def save(_):
        barrier.wait()
        return ProjectStore(store.directory).requests.create(message["id"], request_id=identity,
            configuration={"adapter": "controlled/1", "model": "text-fixture"})
    with ThreadPoolExecutor(max_workers=6) as pool:
        items = list(pool.map(save, range(6)))
    assert all(item == items[0] for item in items)
    def start(_):
        barrier.wait()
        return ProjectStore(store.directory).requests._claim(identity, executor_id=str(uuid4()))
    with ThreadPoolExecutor(max_workers=6) as pool:
        starts = list(pool.map(start, range(6)))
    assert sum(won for _, won in starts) == 1
    assert len({item["executor_id"] for item, _ in starts}) == 1
    running = store.requests.get(identity)
    assert store.requests._claim(identity, executor_id=running["executor_id"]) == (running, False)
    assert store.info()["revision"] == 1 and len(store.history()) == 1


def test_complete_and_identical_replay_publish_one_message_without_project_edit(journal):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    before, history = store.snapshot(), store.history()
    text = "已批准\n```python\nstk.project.apply(...)\n```"
    metadata = {"model": "resolved-model/1", "remote_request_id": "request-1", "input_tokens": 9, "output_tokens": 5}
    completed = store.requests._complete(item["id"], executor_id=owner, text=text, metadata=metadata)
    assert completed["status"] == "completed" and completed["error_code"] is None
    assert completed["result"]["metadata"] == metadata
    assert store.discussion.get(item["assistant_message_id"])["text"] == text
    assert store.requests._complete(item["id"], executor_id=owner, text=text, metadata=metadata) == completed
    assert store.requests.cancel(item["id"]) == completed and not completed["cancel_requested"]
    assert len(store.discussion.list()["messages"]) == 2
    assert store.snapshot() == before and store.history() == history
    with pytest.raises(RevisionConflict, match="different complete result"):
        store.requests._complete(item["id"], executor_id=owner, text="different", metadata=metadata)
    with pytest.raises(RevisionConflict, match="different complete result"):
        store.requests._complete(item["id"], executor_id=owner, text=text, metadata={})
    assert ProjectStore(store.directory).requests.get(item["id"]) == completed


def test_atomic_completion_failure_rolls_back_message_and_marker(journal, monkeypatch):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    before = store.requests.get(item["id"])
    original = Requests._update
    def fail_after_message(self, db, identity, state, **changes):
        assert db.execute("SELECT id FROM project_messages WHERE id=?", (item["assistant_message_id"],)).fetchone()
        raise RuntimeError("injected publication failure")
    monkeypatch.setattr(Requests, "_update", fail_after_message)
    with pytest.raises(RuntimeError, match="injected"):
        store.requests._complete(item["id"], executor_id=owner, text="complete result")
    assert store.requests.get(item["id"]) == before
    assert len(store.discussion.list()["messages"]) == 1
    monkeypatch.setattr(Requests, "_update", original)
    assert store.requests._complete(item["id"], executor_id=owner, text="complete result")["status"] == "completed"


@pytest.mark.parametrize("text,metadata", [("", None), (" ", None), ("x" * (65536 + 1), None), ("\ud800", None),
    ("valid", {"headers": {"Authorization": "secret"}}), ("valid", {"remote_request_id": "https://host?token=secret"}),
    ("valid", {"input_tokens": True}), ("valid", {"output_tokens": 2**63})],
    ids=["empty-text", "blank-text", "oversized-text", "invalid-utf8", "credential-header",
         "credential-url", "boolean-token-count", "oversized-token-count"])
def test_invalid_output_never_publishes_partial_message(journal, text, metadata):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    with pytest.raises(ProjectError):
        store.requests._complete(item["id"], executor_id=owner, text=text, metadata=metadata)
    assert store.requests.get(item["id"])["status"] == "running"
    assert len(store.discussion.list()["messages"]) == 1


def test_pending_cancel_cannot_be_claimed_or_reopened_as_pending(journal):
    store, _, _, _ = journal
    item = create(journal)
    cancelled = store.requests.cancel(item["id"])
    assert cancelled["status"] == "cancelled" and cancelled["cancel_requested"] and cancelled["executor_id"] is None
    assert store.requests._claim(item["id"], executor_id=str(uuid4())) == (cancelled, False)
    assert store.requests.cancel(item["id"]) == cancelled
    assert create(journal, request_id=item["id"]) == cancelled
    assert ProjectStore(store.directory).requests.get(item["id"]) == cancelled
    assert len(store.discussion.list()["messages"]) == 1


def test_cancel_running_preserves_uncertainty_and_owner_can_confirm_late_result(journal):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    uncertain = store.requests.cancel(item["id"])
    assert uncertain["status"] == "uncertain" and uncertain["cancel_requested"]
    assert uncertain["error_code"] == "cancel_unconfirmed" and uncertain["executor_id"] == owner
    assert store.requests.cancel(item["id"]) == uncertain
    with pytest.raises(RevisionConflict, match="another execution"):
        store.requests._complete(item["id"], executor_id=str(uuid4()), text="wrong owner")
    completed = store.requests._complete(item["id"], executor_id=owner, text="late but confirmed")
    assert completed["status"] == "completed" and completed["cancel_requested"]
    assert store.requests.cancel(item["id"]) == completed


def test_confirmed_cancellation_and_failure_never_publish_late_results(journal):
    store, _, _, _ = journal
    for status, code in (("cancelled", "cancel_confirmed"), ("failed", "adapter_failed")):
        item = create(journal)
        owner = claim(store, item)
        terminal = store.requests._settle(item["id"], executor_id=owner, status=status, code=code)
        assert terminal["status"] == status
        assert store.requests._complete(item["id"], executor_id=owner, text="too late") == terminal
        assert store.requests._settle(item["id"], executor_id=owner, status="uncertain", code="executor_lost") == terminal
        assert store.requests._claim(item["id"], executor_id=str(uuid4())) == (terminal, False)
    assert len(store.discussion.list()["messages"]) == 1


def test_simultaneous_cancel_and_complete_have_one_serialized_outcome(journal):
    store, _, _, _ = journal
    for _ in range(5):
        item = create(journal)
        owner = claim(store, item)
        barrier = threading.Barrier(2)
        def cancel():
            barrier.wait()
            return ProjectStore(store.directory).requests._settle(item["id"], executor_id=owner,
                                                                  status="cancelled", code="cancel_confirmed")
        def complete():
            barrier.wait()
            return ProjectStore(store.directory).requests._complete(item["id"], executor_id=owner, text="racing result")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(cancel), pool.submit(complete)
            first, second = a.result(), b.result()
        assert first == second == store.requests.get(item["id"])
        if first["status"] == "completed":
            assert store.discussion.get(item["assistant_message_id"])["text"] == "racing result"
        else:
            with pytest.raises(ProjectError, match="message not found"):
                store.discussion.get(item["assistant_message_id"])


def test_reading_and_reopening_do_not_recover_or_reclaim_an_old_owner(journal):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    running = store.requests.get(item["id"])
    reopened = ProjectStore(store.directory)
    assert reopened.requests.get(item["id"]) == running
    assert reopened.requests.list()["requests"] == [running]
    assert reopened.requests.input(item["id"])["message"]["text"]
    with pytest.raises(RevisionConflict, match="another execution"):
        reopened.requests._settle(item["id"], executor_id=str(uuid4()), status="uncertain", code="executor_lost")
    uncertain = reopened.requests._settle(item["id"], executor_id=owner, status="uncertain", code="executor_lost")
    assert uncertain["status"] == "uncertain" and not uncertain["cancel_requested"]
    assert reopened.requests._claim(item["id"], executor_id=str(uuid4())) == (uncertain, False)
    assert reopened.requests._complete(item["id"], executor_id=owner, text="reconciled response")["status"] == "completed"


def test_pagination_is_stable_and_ancestors_are_read_once_per_page(journal, monkeypatch):
    store, _, _, _ = journal
    items = [create(journal) for _ in range(3)]
    from suan.project.contexts import Contexts
    original = Contexts._get
    reads = []
    def count(self, db, key):
        reads.append(key)
        return original(self, db, key)
    monkeypatch.setattr(Contexts, "_get", count)
    page = store.requests.list(limit=2)
    assert page == {"requests": items[:2], "next_offset": 2} and len(reads) == 1
    assert store.requests.list(offset=2) == {"requests": items[2:], "next_offset": None}
    for args in ({"offset": True}, {"limit": 101}, {"offset": -1}, {"limit": 0}):
        with pytest.raises(ProjectError):
            store.requests.list(**args)


@pytest.mark.parametrize("column,value", [("payload", "{}"), ("state", "{}"), ("sha256", "0" * 64),
                                          ("state_sha256", "0" * 64), ("status", "failed"),
                                          ("payload", b"{}"), ("state", b"{}")])
def test_damaged_identity_or_state_blocks_all_public_access(journal, column, value):
    store, _, _, _ = journal
    item = create(journal)
    with sqlite3.connect(store.path) as db:
        db.execute(f"UPDATE project_requests SET {column}=?", (value,))
    for operation in (lambda: store.requests.get(item["id"]), store.requests.list,
                      lambda: store.requests.cancel(item["id"]), lambda: store.requests.input(item["id"])):
        with pytest.raises(ProjectError, match="Invalid stored project request"):
            operation()


@pytest.mark.parametrize("ancestor", ["context", "message", "assistant"])
def test_even_independently_valid_but_replaced_ancestors_are_rejected(journal, ancestor):
    store, _, context, message = journal
    item = create(journal)
    if ancestor == "assistant":
        owner = claim(store, item)
        store.requests._complete(item["id"], executor_id=owner, text="original result")
        table, key, field = "project_messages", item["assistant_message_id"], "text"
    elif ancestor == "context":
        table, key, field = "project_contexts", context["id"], "title"
    else:
        table, key, field = "project_messages", message["id"], "text"
    with sqlite3.connect(store.path) as db:
        raw, digest = db.execute(f"SELECT payload, request_sha256 FROM {table} WHERE id=?", (key,)).fetchone()
        payload = json.loads(raw)
        payload[field] = "mutated independently valid ancestor"
        db.execute(f"UPDATE {table} SET payload=?, sha256=? WHERE id=?",
                   (_encode(payload).decode(), _digest({"payload": payload, "request_sha256": digest}), key))
    with pytest.raises(ProjectError, match="Invalid stored project request"):
        store.requests.get(item["id"])
    with pytest.raises(ProjectError, match="Invalid stored project request"):
        store.requests.list()


def test_format7_upgrade_preserves_context_and_messages_and_backs_up_before_schema_change(journal):
    store, _, context, message = journal
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS workflow_run_events")
        db.execute("DROP TABLE IF EXISTS workflow_run_plans")
        db.execute("DROP TABLE IF EXISTS analysis_run_events")
        db.execute("DROP TABLE IF EXISTS analysis_run_plans")
        db.execute("DROP TABLE project_requests")
        db.execute("PRAGMA user_version=7")
    old = ProjectStore(store.directory)
    assert old.info()["format_version"] == 7
    with pytest.raises(UnsupportedProjectFormat, match="format 8"):
        old.requests.list()
    assert old.discussion.get(message["id"]) == message
    result = old.upgrade(expected_revision=1)
    assert result["upgraded"] and result["format_version"] == 10 and result["revision"] == 2
    with sqlite3.connect(result["backup"]["path"]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
        assert db.execute("SELECT revision FROM project").fetchone()[0] == 1
        assert db.execute("SELECT name FROM sqlite_master WHERE name='project_requests'").fetchone() is None
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert old.contexts.get(context["id"]) == context and old.discussion.get(message["id"]) == message
    assert create(journal)["source_revision"] == 1
    assert old.upgrade(expected_revision=2)["upgraded"] is False


def test_replacing_project_database_prevents_a_retained_writer_from_publishing(journal, tmp_path):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    replacement = ProjectStore.create(tmp_path / "replacement", "Other project")
    shutil.copyfile(replacement.path, store.path)
    with pytest.raises(ProjectError, match="replaced"):
        store.requests._complete(item["id"], executor_id=owner, text="must not reach another project")
    assert ProjectStore(store.directory).discussion.list()["messages"] == []


def test_uncertain_observations_cannot_be_mislabeled_as_known_failure(journal):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    before = store.requests.get(item["id"])
    for status, code in (("failed", "transport_uncertain"), ("failed", "executor_lost"),
                         ("failed", "local_save_failed"), ("cancelled", "cancel_unconfirmed"),
                         ("uncertain", "adapter_failed"), ("cancelled", "secret exception details")):
        with pytest.raises(ProjectError, match="settlement"):
            store.requests._settle(item["id"], executor_id=owner, status=status, code=code)
    assert store.requests.get(item["id"]) == before


def test_uncertain_cancellation_requires_a_previously_recorded_user_intent(journal):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    with pytest.raises(ProjectError, match="recorded cancellation intent"):
        store.requests._settle(item["id"], executor_id=owner, status="uncertain", code="cancel_unconfirmed")
    assert not store.requests.get(item["id"])["cancel_requested"]
    cancelled = store.requests.cancel(item["id"])
    assert store.requests._settle(item["id"], executor_id=owner, status="uncertain", code="cancel_unconfirmed") == cancelled


def test_maximum_utf8_response_is_stored_whole_and_metadata_cannot_mutate_after_completion(journal):
    store, _, _, _ = journal
    item = create(journal)
    owner = claim(store, item)
    text = "🙂" * 16384  # Exactly 64 KiB UTF-8, not 64 KiB code points.
    metadata = {"input_tokens": 2**63 - 1}
    completed = store.requests._complete(item["id"], executor_id=owner, text=text, metadata=metadata)
    metadata["input_tokens"] = 1
    assert store.discussion.get(item["assistant_message_id"])["text"] == text
    assert completed["result"]["metadata"] == {"input_tokens": 2**63 - 1}
    assert store.requests.get(item["id"]) == completed
