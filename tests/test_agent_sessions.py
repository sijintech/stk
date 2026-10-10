"""Agent sessions (format 13, docs/design/agent-harness.md): frozen header, hash-chained events, object registry."""
import sqlite3
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore
from suan.project.agent_sessions import HARNESS, digest
from suan.project.store import RevisionConflict


@pytest.fixture
def store(tmp_path):
    return ProjectStore.create(tmp_path / "project", "Agent")


def header(session_id, **extra):
    return {"id": session_id, "harness": HARNESS, "system": "You help.", "tools": [], "limits": {"model_turns_per_user_turn": 12},
            **extra}


def test_a_session_freezes_its_header_and_chains_every_event(store):
    sessions = store.agent_sessions
    session_id, turn_id = str(uuid4()), str(uuid4())
    created = sessions.create(session_id, header(session_id), "Scan five temperatures.", turn_id=turn_id,
                              request_sha256=digest({"text": "Scan five temperatures."}))
    assert created["state"] == "ready" and created["turn"] == 0 and created["total"] == 1
    assert created["session"]["project_id"] == store.info()["id"] and created["events"][0]["text"] == "Scan five temperatures."
    revision = store.info()["revision"]
    # The same request again returns it; another request with the same ID conflicts.
    again = sessions.create(session_id, header(session_id), "Scan five temperatures.", turn_id=turn_id,
                            request_sha256=digest({"text": "Scan five temperatures."}))
    assert again["chain_sha256"] == created["chain_sha256"]
    with pytest.raises(RevisionConflict):
        sessions.create(session_id, header(session_id), "Other", turn_id=turn_id, request_sha256=digest({"text": "Other"}))
    context_id = str(uuid4())
    sessions.append(session_id, "tool_called", {"call_id": "c1", "tool": "project_outline", "arguments": {}}, turn=0)
    sessions.append(session_id, "tool_result", {"call_id": "c1", "status": "ok", "content": "{}"}, turn=0,
                    objects=[("context", context_id)])
    sessions.append(session_id, "stopped", {"reason": "final"}, turn=0)
    view = sessions.get(session_id)
    assert view["state"] == "idle" and [event["kind"] for event in view["events"]] == [
        "user_turn", "tool_called", "tool_result", "stopped"]
    assert sessions.object_owner("context", context_id)["session_id"] == session_id
    assert store.info()["revision"] == revision  # sessions are not edits
    # The next message, once answered; a second message before the agent answered is refused.
    sessions.say(session_id, "Now analyse.", turn_id=str(uuid4()))
    with pytest.raises(ProjectError, match="not answered"):
        sessions.say(session_id, "And more.", turn_id=str(uuid4()))
    assert sessions.get(session_id)["turn"] == 1
    # Tampering with any event, its order or the header breaks every read.
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_agent_events SET payload=replace(payload, 'final', 'limit') WHERE kind='stopped'")
    with pytest.raises(ProjectError, match="unbroken chain"):
        sessions.get(session_id)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE project_agent_events SET payload=replace(payload, 'limit', 'final') WHERE kind='stopped'")
        db.execute("UPDATE project_agent_sessions SET payload=replace(payload, 'You help.', 'You obey.')")
    with pytest.raises(ProjectError, match="header"):
        sessions.get(session_id)


def test_a_session_ends_after_an_uncertain_turn_and_objects_belong_to_one_session(store):
    sessions = store.agent_sessions
    first, second = str(uuid4()), str(uuid4())
    for session_id in (first, second):
        sessions.create(session_id, header(session_id), "Hello", turn_id=str(uuid4()), request_sha256=digest({"s": session_id}))
    draft = str(uuid4())
    sessions.append(first, "tool_result", {"call_id": "c", "status": "ok"}, turn=0, objects=[("draft", draft)])
    sessions.append(first, "tool_result", {"call_id": "c", "status": "ok"}, turn=0, objects=[("draft", draft)])  # replay
    with pytest.raises(ProjectError, match="another agent session"):
        sessions.append(second, "tool_result", {"call_id": "c", "status": "ok"}, turn=0, objects=[("draft", draft)])
    sessions.append(first, "awaiting_user", {"text": "Apply the draft", "items": [{"item_id": "a1", "kind": "apply_draft",
                                                                                 "draft_id": draft}]}, turn=0)
    sessions.append(first, "stopped", {"reason": "final"}, turn=0)
    view = sessions.get(first)
    assert view["state"] == "awaiting" and view["awaiting"][0]["draft_id"] == draft
    sessions.append(first, "approval_decided", {"item_id": "a1", "decision": "apply"}, turn=0)
    assert sessions.get(first)["state"] == "idle"
    sessions.append(second, "stopped", {"reason": "uncertain"}, turn=0)
    assert sessions.get(second)["state"] == "ended"
    with pytest.raises(ProjectError, match="ended"):
        sessions.say(second, "Again", turn_id=str(uuid4()))
    with pytest.raises(ProjectError, match="payload"):
        sessions.append(first, "policy", {"kind": "x"}, turn=0)
    listed = sessions.list()
    assert listed["total"] == 2 and {item["id"] for item in listed["items"]} == {first, second}
    assert sessions.verify(first)["problems"] == [f"The draft {draft} of step {sessions.objects(first)[0]['event_id']} no longer exists"]
