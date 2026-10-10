"""Checking an agent session (docs/design/agent-harness.md, "审计与核对"): beyond the chain that every read checks,
rebuild each planner turn's input from the log and compare it with the digest recorded before sending, and recompute
the deterministic tools. Never calls a model.
"""
from suan.project.agent_sessions import digest

from . import tools as tools_module, wire

RECOMPUTED = ("table_statistics",)


def verify(store, session_id, *, snapshot=False):
    """The check of one session (``snapshot``: with the header and events it checked, read once)."""
    report, header, events = store.agent_sessions.verify(session_id, snapshot=True)
    result = _check(store, session_id, report, header, events)
    return (result, header, events) if snapshot else result


def _check(store, session_id, report, header, events):
    problems = list(report["problems"])
    if digest(header["system"]) != header.get("system_sha256"):
        problems.append("The frozen system prompt does not match its digest")
    if digest(header["tools"]) != header.get("tools_sha256"):
        problems.append("The frozen tool definitions do not match their digest")
    for skill in header.get("skills", []):
        if wire.hashlib.sha256(skill["text"].encode("utf-8")).hexdigest() != skill["sha256"]:
            problems.append(f"The frozen skill {skill['id']} does not match its digest")
    turns = 0
    for index, event in enumerate(events):
        if event["kind"] == "model_claimed":
            turns += 1
            before = events[:event["transcript_events"]]
            value = wire.turn_input(header, before, event["configuration"], tool_choice=event.get("tool_choice", "auto"))
            if wire.input_digest(value) != event["input_sha256"]:
                problems.append(f"Planner turn {event['call']} of message {event['turn']}: its input cannot be rebuilt "
                                "from the log")
        elif event["kind"] == "tool_result" and event["status"] == "ok":
            call = next((item for item in reversed(events[:index]) if item["kind"] == "tool_called"
                         and item["call_id"] == event["call_id"]), None)
            if call is None:
                problems.append(f"Tool result {event['call_id']} has no recorded call")
                continue
            if digest(event["content"]) != event["content_sha256"]:
                problems.append(f"Tool result {event['call_id']} does not match its digest")
            if call["tool"] in RECOMPUTED:
                tool = tools_module.REGISTRY[call["tool"]]
                context = tools_module.ToolContext(store, session_id, event["turn"], call["call_id"])
                again, _ = tools_module.content(call["tool"], tool.handler(context, call["arguments"]))
                if again != event["content"]:
                    problems.append(f"Recomputing {call['tool']} ({call['call_id']}) gives a different result")
    return {**report, "planner_turns": turns, "problems": problems, "ok": not problems}


__all__ = ["verify"]
