"""Internal persistence for a person's first-start decision; no execution or authentication.

The preparation tool owns a deterministic workflow run. Its frozen request and
plan are bound into the existing agent hash chain. A decision is consumed before
dispatch, even if dispatch or its receipt is lost. Only the caller that commits a
new start decision receives ``dispatch=True``. Observing never dispatches.

This ledger does not grant a tool permission or validate the MuPRO domain. The
trusted preparation handler and desktop decision adapter must do that separately.
"""
from uuid import UUID, uuid5

from suan.project.agent_sessions import _now, digest
from suan.project.archive import Archive, Archived
from suan.project.store import ProjectError, RevisionConflict, _id
from suan.project.workflow_runs import _hash

PREPARE_TOOL = "prepare_muferro_run"
MAX_PENDING = 20


def run_identity(session_id, turn, call_id):
    _id(session_id)
    if type(turn) is not int or turn < 0 or type(call_id) is not str or not 1 <= len(call_id) <= 128:
        raise ProjectError("A preparation needs its original turn and bounded tool call ID")
    return str(uuid5(UUID(session_id), f"{turn}:{call_id}:workflow_run"))


def _offers(events):
    return [e["item"] for e in events if e["kind"] == "policy" and e.get("action") == "run_prepared"]


def _item(events, item_id):
    _id(item_id)
    found = [item for item in _offers(events) if item["item_id"] == item_id]
    if len(found) != 1:
        raise ProjectError("No unique prepared run approval belongs to this session")
    return found[0]


def _decision(events, item_id):
    found = [e for e in events if e["kind"] == "approval_decided" and e.get("item_id") == item_id]
    if len(found) > 1:
        raise ProjectError("A run approval has conflicting decision records")
    return found[0] if found else None


def _envelope(item):
    return {"approval_id": item["item_id"], "plan_sha256": item["plan_sha256"],
            "request_sha256": item["request_sha256"], "expected_revision": item["expected_revision"]}


def _active(db, run_id):
    if Archive._archived(db, "workflow_run", run_id):
        raise Archived("This prepared workflow run is archived")


class RunApprovals:
    def __init__(self, store):
        self.store = store

    def offer(self, session_id, *, turn, call_id, run_id):
        """Bind an existing run to its original frozen tool call, atomically and idempotently."""
        if run_id != run_identity(session_id, turn, call_id):
            raise ProjectError("The run does not belong to this preparation call")
        sessions, runs = self.store.agent_sessions, self.store.workflow_runs
        with self.store._connect(write=True) as db:
            header, events = sessions._read(db, session_id)
            definitions = [t for t in header.get("tools", []) if t.get("name") == PREPARE_TOOL]
            calls = [e for e in events if e["kind"] == "tool_called" and e["turn"] == turn
                     and e.get("call_id") == call_id]
            if (len(definitions) != 1 or type(definitions[0].get("version")) is not int
                    or definitions[0].get("version") != 1
                    or definitions[0].get("level") != "prepare_run" or len(calls) != 1
                    or calls[0].get("tool") != PREPARE_TOOL or calls[0].get("level") != "prepare_run"
                    or calls[0].get("version") != 1):
                raise ProjectError("No frozen preparation tool call belongs to this session")
            arguments = calls[0].get("arguments")
            if (type(arguments) is not dict or set(arguments) != {"workflow_id", "rows", "expected_revision"}
                    or type(arguments["expected_revision"]) is not int
                    or calls[0].get("arguments_sha256") != digest(arguments)):
                raise ProjectError("The preparation call must bind workflow, rows and revision")
            plan, run_events = runs._read(db, run_id)
            request = {"workflow_id": plan["workflow_id"], "rows": [r["id"] for r in plan["rows"]],
                       "expected_revision": plan["source_revision"]}
            if arguments != request:
                raise RevisionConflict("The run differs from its recorded preparation arguments")
            if "simulation" in plan:
                request["simulation"] = plan["simulation"]
            stored = db.execute("SELECT sha256, request_sha256 FROM workflow_run_plans WHERE id=?", (run_id,)).fetchone()
            if _hash(request) != stored["request_sha256"]:
                raise ProjectError("The frozen preparation request does not match its checksum")
            item = {"item_id": str(uuid5(UUID(run_id), "agent-first-start")), "kind": "start_run", "run_id": run_id,
                    "plan_sha256": stored["sha256"], "request_sha256": stored["request_sha256"],
                    "expected_revision": plan["source_revision"], "source_event_id": calls[0]["id"],
                    "source_turn": turn, "source_call_id": call_id}
            existing = [i for i in _offers(events) if i["item_id"] == item["item_id"]]
            if existing:
                if existing != [item]:
                    raise RevisionConflict("This preparation already has a different approval binding")
                return item
            _active(db, run_id)
            if any(e["step"] == "" and e["status"] == "started" for e in run_events):
                raise RevisionConflict("A previously started run cannot be offered for first start")
            revision = db.execute("SELECT revision FROM project").fetchone()[0]
            if revision != item["expected_revision"]:
                raise RevisionConflict("The project changed after run preparation")
            if sum(_decision(events, i["item_id"]) is None for i in _offers(events)) >= MAX_PENDING:
                raise ProjectError("Resolve pending run approvals before preparing more")
            sessions._append(db, session_id, turn, "policy", {"action": "run_prepared", "item": item, "at": _now()})
            sessions._append(db, session_id, turn, "awaiting_user", {"items": [item], "at": _now()})
            return item

    def consume(self, session_id, item_id, decision, *, plan_sha256, expected_revision, by):
        """Commit one local human decision before dispatch; an identical replay never dispatches."""
        if decision not in ("start", "decline") or type(decision) is not str:
            raise ProjectError("A run decision is start or decline")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ProjectError("A run decision needs a nonnegative integer revision")
        if type(by) is not str or not by.strip() or len(by) > 255 or "\0" in by:
            raise ProjectError("A run decision needs a bounded local user label")
        sessions, runs = self.store.agent_sessions, self.store.workflow_runs
        with self.store._connect(write=True) as db:
            _, events = sessions._read(db, session_id)
            item = _item(events, item_id)
            if plan_sha256 != item["plan_sha256"] or expected_revision != item["expected_revision"]:
                raise RevisionConflict("The decision differs from the displayed frozen run")
            previous = _decision(events, item_id)
            if previous:
                if previous["decision"] != decision:
                    raise RevisionConflict("This run approval has already been consumed")
                return {"dispatch": False, "item": item, "decision": previous}
            if decision == "start":
                plan, run_events = runs._read(db, item["run_id"])
                stored = db.execute("SELECT request_sha256 FROM workflow_run_plans WHERE id=?", (item["run_id"],)).fetchone()
                if _hash(plan) != plan_sha256 or stored[0] != item["request_sha256"]:
                    raise RevisionConflict("The frozen run no longer matches this approval")
                _active(db, item["run_id"])
                if db.execute("SELECT revision FROM project").fetchone()[0] != expected_revision:
                    raise RevisionConflict("The project changed after run preparation")
                if any(e["step"] == "" and e["status"] == "started" for e in run_events):
                    raise RevisionConflict("The run has already been started")
            payload = {"item_id": item_id, "item_kind": "start_run", "decision": decision,
                       "approval": _envelope(item), "by": {"user": by, "authenticated": False}, "at": _now()}
            event_id = sessions._append(db, session_id, item["source_turn"], "approval_decided", payload)
            if decision == "decline":
                sessions._append(db, session_id, item["source_turn"], "approval_receipt",
                                 {"item_id": item_id, "run_id": item["run_id"], "approval": _envelope(item),
                                  "ok": True, "decision": "decline", "outcome": "declined", "at": _now()})
            return {"dispatch": decision == "start", "item": item, "decision": {**payload, "id": event_id}}

    def observe(self, session_id, item_id):
        """Read original evidence and optionally save its receipt; never start, recover or cancel a run."""
        sessions = self.store.agent_sessions
        with self.store._connect(write=True) as db:
            _, events = sessions._read(db, session_id)
            item = _item(events, item_id)
            decided = _decision(events, item_id)
            if decided is None:
                return {"outcome": "pending", "item": item}
            if decided["decision"] == "decline":
                return {"outcome": "declined", "item": item}
            plan, run_events = self.store.workflow_runs._read(db, item["run_id"])
            stored = db.execute("SELECT request_sha256 FROM workflow_run_plans WHERE id=?", (item["run_id"],)).fetchone()
            if _hash(plan) != item["plan_sha256"] or stored[0] != item["request_sha256"]:
                raise ProjectError("The original run approval evidence no longer matches")
            starts = [e for e in run_events if e["step"] == "" and e["status"] == "started"]
            matches = [e for e in starts if e.get("approval") == _envelope(item)]
            outcome = "started" if len(matches) == 1 else "other_start" if starts else "uncertain"
            result = {"outcome": outcome, "item_id": item_id, "run_id": item["run_id"],
                      "approval": _envelope(item), "ok": outcome == "started",
                      "run_status": self.store.workflow_runs._state(plan, run_events)["status"]}
            if matches:
                result["executor_id"] = matches[0]["executor_id"]
            receipts = [e for e in events if e["kind"] == "approval_receipt" and e.get("item_id") == item_id]
            if not receipts or any(receipts[-1].get(k) != v for k, v in result.items()):
                sessions._append(db, session_id, item["source_turn"], "approval_receipt", {**result, "at": _now()})
            return result
