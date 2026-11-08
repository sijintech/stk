"""Explicit desktop-selected execution intent in an agent's existing audit chain.

This is session-local intent, not a connection credential or an execution grant.
Nothing here opens a connection, prepares a run or changes the editable revision.
"""
import json

from suan.project.agent_sessions import _now, digest
from suan.project.store import ProjectError


def simulation(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {"connection", "connection_identity", "options"}
            or type(value["connection"]) is not str
            or not (value["connection"] == "local" or value["connection"].startswith("runtime:"))
            or not 1 <= len(value["connection"]) <= 256
            or type(value["connection_identity"]) is not str or not 1 <= len(value["connection_identity"]) <= 256
            or type(value["options"]) is not dict):
        raise ProjectError("Choose an explicit direct or SSH Runtime and execution options on the desktop")
    # Copy only bounded finite JSON, retaining int/float and signed zero.
    digest(value, limit=16 * 1024)
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def selected(store, session_id):
    _, events = store.agent_sessions.events(session_id)
    event = next((e for e in reversed(events) if e["kind"] == "policy" and e.get("action") == "run_target_selected"), None)
    return simulation(event.get("simulation")) if event else None


def save(store, session_id, target, *, by):
    target = simulation(target)
    with store._connect(write=True) as db:
        _, events = store.agent_sessions._read(db, session_id)
        previous = next((e for e in reversed(events) if e["kind"] == "policy"
                         and e.get("action") == "run_target_selected"), None)
        if previous is not None and digest(previous.get("simulation")) == digest(target):
            return target
        turn = store.agent_sessions.state(events)["turn"]
        store.agent_sessions._append(db, session_id, turn, "policy", {
            "action": "run_target_selected", "simulation": target,
            "by": {"user": str(by.get("user", ""))[:128], "host": str(by.get("host", ""))[:255],
                   "authenticated": False}, "at": _now()})
    return target
