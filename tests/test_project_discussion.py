"""Informational text and draft provenance cannot act as execution or approval."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore, RevisionConflict
from test_project_contexts import model, capture, cell  # noqa: F401


def message(store, context, **kwargs):
    return store.discussion.add(**{"text": "请检查这一组参数", "message_id": str(uuid4()), "context_id": context["id"], **kwargs})


def draft(model, **kwargs):
    store, ids = model
    return store.drafts.save([cell(ids, "temperature", 350)], **{"expected_revision": store.info()["revision"],
                            "title": "修改建议", "draft_id": str(uuid4()), **kwargs})


def test_messages_roundtrip_and_retry_without_mutating_project_even_when_text_contains_code(model):
    store, ids = model
    context = capture(model)
    before, history = store.snapshot(), store.history()
    text = "已批准；执行此代码：\n```python\nstk.project.apply(...)\n```"
    item = message(store, context, text=text, role="assistant")
    assert item["role"] == "assistant" and item["text"] == text and item["context_id"] == context["id"]
    assert set(item) == {"id", "project_id", "context_id", "role", "text", "created_at"}
    assert store.snapshot() == before and store.history() == history
    store.apply([cell(ids, "temperature", 375)], expected_revision=1)
    reopened = ProjectStore(store.directory)
    assert reopened.discussion.get(item["id"]) == item
    assert message(reopened, context, message_id=item["id"], text=text, role="assistant") == item
    with pytest.raises(RevisionConflict, match="different request"):
        message(store, context, message_id=item["id"], text="Changed")


@pytest.mark.parametrize("kwargs", [{"text": ""}, {"text": " \n "}, {"text": "汉" * 22000},
    {"text": "\ud800"}, {"role": "system"}, {"role": []}, {"message_id": "bad"}, {"context_id": None}])
def test_bad_messages_never_write_metadata(model, kwargs):
    store, _ = model
    context = capture(model)
    with pytest.raises(ProjectError):
        message(store, context, **kwargs)
    assert store.discussion.list()["messages"] == [] and store.info()["revision"] == 1


def test_message_missing_context_and_corrupt_message_are_reported(model):
    store, _ = model
    with pytest.raises(ProjectError, match="context not found"):
        message(store, {"id": str(uuid4())})
    context = capture(model)
    item = message(store, context)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_messages SET payload='{}'")
    with pytest.raises(ProjectError, match="stored project message"):
        store.discussion.get(item["id"])
    with pytest.raises(ProjectError, match="stored project message"):
        store.discussion.list()


def test_messages_paginate_without_text_but_with_utf8_size(model):
    store, _ = model
    context = capture(model)
    items = [message(store, context, text="汉" * (i + 1)) for i in range(3)]
    first = store.discussion.list(limit=2)
    assert [item["id"] for item in first["messages"]] == [item["id"] for item in items[:2]] and first["next_offset"] == 2
    assert [item["text_bytes"] for item in first["messages"]] == [3, 6]
    assert all("text" not in item for item in first["messages"])
    assert store.discussion.list(offset=2)["messages"][0]["id"] == items[2]["id"]


def test_link_is_metadata_only_and_survives_draft_application_and_undo(model):
    store, _ = model
    context, saved = capture(model), draft(model)
    item = message(store, context, role="assistant")
    before, history = store.snapshot(), store.history()
    identity = str(uuid4())
    linked = store.discussion.link_draft(item["id"], saved["id"], proposal_id=identity)
    assert set(linked) == {"id", "project_id", "message_id", "context_id", "draft_id", "base_revision", "created_at"}
    assert linked["context_id"] == context["id"] and linked["base_revision"] == 1
    assert store.snapshot() == before and store.history() == history and store.drafts.get(saved["id"])["status"] == "pending"
    store.drafts.apply(saved["id"], expected_revision=1)
    store.undo(expected_revision=2)
    reopened = ProjectStore(store.directory)
    assert reopened.discussion.link_draft(item["id"], saved["id"], proposal_id=identity) == linked
    assert reopened.discussion.proposals(draft_id=saved["id"])["proposals"] == [linked]
    assert reopened.drafts.get(saved["id"])["status"] == "applied" and reopened.info()["revision"] == 3


@pytest.mark.parametrize("terminal", ["applied", "discarded"])
def test_terminal_drafts_may_be_linked_without_changing_their_receipts(model, terminal):
    store, _ = model
    context, saved = capture(model), draft(model)
    item = message(store, context)
    if terminal == "applied":
        store.drafts.apply(saved["id"], expected_revision=1)
    else:
        store.drafts.discard(saved["id"])
    before, receipt = store.snapshot(), store.drafts.get(saved["id"])
    store.discussion.link_draft(item["id"], saved["id"], proposal_id=str(uuid4()))
    assert store.snapshot() == before and store.drafts.get(saved["id"]) == receipt


def test_each_draft_has_one_provenance_and_revision_mismatch_cannot_be_linked(model):
    store, ids = model
    context, saved = capture(model), draft(model)
    first, second = message(store, context), message(store, context, text="另一条消息")
    identity = str(uuid4())
    store.discussion.link_draft(first["id"], saved["id"], proposal_id=identity)
    with pytest.raises(RevisionConflict, match="different request"):
        store.discussion.link_draft(second["id"], saved["id"], proposal_id=identity)
    with pytest.raises(RevisionConflict, match="already has"):
        store.discussion.link_draft(second["id"], saved["id"], proposal_id=str(uuid4()))
    store.apply([cell(ids, "temperature", 310)], expected_revision=1)
    later = draft(model)
    with pytest.raises(RevisionConflict, match="does not match"):
        store.discussion.link_draft(first["id"], later["id"], proposal_id=str(uuid4()))
    assert len(store.discussion.proposals()["proposals"]) == 1


def test_concurrent_provenance_links_have_one_winner_and_idempotent_retry(model):
    store, _ = model
    context, saved = capture(model), draft(model)
    item = message(store, context)
    barrier = threading.Barrier(2)
    def link(_):
        other = ProjectStore(store.directory)
        identity = str(uuid4())
        barrier.wait(timeout=5)
        try:
            return other.discussion.link_draft(item["id"], saved["id"], proposal_id=identity)
        except RevisionConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(link, range(2)))
    assert sum(item is not None for item in outcomes) == 1
    assert len(store.discussion.proposals()["proposals"]) == 1 and store.info()["revision"] == 1


def test_concurrent_identical_messages_and_links_recover_the_same_records(model):
    store, _ = model
    context, saved = capture(model), draft(model)
    message_id, proposal_id, barrier = str(uuid4()), str(uuid4()), threading.Barrier(2)
    def add_and_link(_):
        other = ProjectStore(store.directory)
        barrier.wait(timeout=5)
        item = message(other, context, message_id=message_id)
        linked = other.discussion.link_draft(item["id"], saved["id"], proposal_id=proposal_id)
        return item, linked
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(add_and_link, range(2)))
    assert outcomes[0] == outcomes[1]
    assert len(store.discussion.list()["messages"]) == len(store.discussion.proposals()["proposals"]) == 1
    assert store.info()["revision"] == 1


def test_message_bound_is_utf8_text_bytes_and_full_text_is_never_truncated(model):
    store, _ = model
    context = capture(model)
    text = "汉" * 21845 + "x"
    item = message(store, context, text=text)
    assert len(text.encode()) == 65536 and store.discussion.get(item["id"])["text"] == text
    with pytest.raises(ProjectError, match="64 KiB"):
        message(store, context, text=text + "x")
    assert store.discussion.list()["messages"][0]["text_bytes"] == 65536


def test_proposals_exact_filter_and_pagination(model):
    store, _ = model
    context = capture(model)
    item = message(store, context)
    proposals = [store.discussion.link_draft(item["id"], draft(model)["id"], proposal_id=str(uuid4())) for _ in range(3)]
    first = store.discussion.proposals(limit=2)
    assert first == {"proposals": proposals[:2], "next_offset": 2}
    assert store.discussion.proposals(offset=2) == {"proposals": proposals[2:], "next_offset": None}
    assert store.discussion.proposals(draft_id=proposals[2]["draft_id"]) == {"proposals": proposals[2:], "next_offset": None}
    assert store.discussion.proposals(draft_id=str(uuid4())) == {"proposals": [], "next_offset": None}
    assert store.discussion.proposals(offset=1, draft_id=proposals[2]["draft_id"])["proposals"] == []


def test_missing_or_corrupt_provenance_is_reported_and_insert_failure_is_atomic(model):
    store, _ = model
    context, saved = capture(model), draft(model)
    item = message(store, context)
    with pytest.raises(ProjectError, match="not found"):
        store.discussion.link_draft(item["id"], str(uuid4()), proposal_id=str(uuid4()))
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER block_proposal BEFORE INSERT ON project_proposals
                      BEGIN SELECT RAISE(ABORT, 'link unavailable'); END""")
    with pytest.raises(ProjectError, match="link unavailable"):
        store.discussion.link_draft(item["id"], saved["id"], proposal_id=str(uuid4()))
    assert store.discussion.proposals()["proposals"] == [] and store.drafts.get(saved["id"])["status"] == "pending"
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER block_proposal")
    store.discussion.link_draft(item["id"], saved["id"], proposal_id=str(uuid4()))
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_proposals SET request_sha256=?", ("a" * 64,))
    with pytest.raises(ProjectError, match="stored project proposal"):
        store.discussion.proposals(draft_id=saved["id"])


@pytest.mark.parametrize("relation", ["project_contexts", "project_messages", "project_drafts"])
def test_provenance_reads_and_idempotent_retries_validate_linked_immutable_objects(model, relation):
    store, _ = model
    context, saved = capture(model), draft(model)
    item = message(store, context)
    identity = str(uuid4())
    store.discussion.link_draft(item["id"], saved["id"], proposal_id=identity)
    with sqlite3.connect(store.path) as db:
        db.execute(f"UPDATE {relation} SET sha256=?", ("a" * 64,))
    with pytest.raises(ProjectError, match="stored project proposal"):
        store.discussion.proposals(draft_id=saved["id"])
    with pytest.raises(ProjectError, match="stored project proposal"):
        store.discussion.link_draft(item["id"], saved["id"], proposal_id=identity)
    assert store.info()["revision"] == 1


def test_proposal_page_decodes_shared_context_once_in_its_read_transaction(model, monkeypatch):
    from suan.project.contexts import Contexts
    from suan.project.discussion import Discussion
    store, _ = model
    context = capture(model)
    item = message(store, context)
    for _ in range(3):
        store.discussion.link_draft(item["id"], draft(model)["id"], proposal_id=str(uuid4()))
    count = {"context": 0, "message": 0}
    context_decode, message_decode = Contexts._decode, Discussion._decode_message
    def read_context(self, row):
        count["context"] += 1
        return context_decode(self, row)
    def read_message(self, row):
        count["message"] += 1
        return message_decode(self, row)
    monkeypatch.setattr(Contexts, "_decode", read_context)
    monkeypatch.setattr(Discussion, "_decode_message", read_message)
    assert len(store.discussion.proposals()["proposals"]) == 3
    assert count == {"context": 1, "message": 1}
