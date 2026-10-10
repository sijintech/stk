"""The agent loop (docs/design/agent-harness.md): plan with a model on this computer or the organization's network,
call one tool at a time, record every step before and after it acts, and stop at the limits.

Rules this module keeps:

- A planner turn is claimed (``model_claimed`` committed) before anything is sent, and sent once: an uncertain outcome
  ends the session (owner decision 5), never a second send. Only a turn that definitely was not sent
  (``adapter_failed``) moves to the next candidate on another endpoint, and only to one the session showed at its start
  that is as near or nearer.
- A tool call is recorded (``tool_called``) before it runs and its result (``tool_result``) after; a tool's objects and
  data sources are computed by the tool, never taken from the model.
- Every planner turn is checked against the network setting and the data boundary (``ModelGateway.admit_planner``):
  in v1 planner turns stay on this computer or the organization's network.
- Nothing here applies drafts, prepares or starts runs, labels data or changes settings: no tool does.
"""
from dataclasses import dataclass, field
import threading
import time
from uuid import UUID, uuid5

from suan.graph.schema import check_value
from suan.models.routing import candidates
from suan.project.agent_sessions import HARNESS, AgentSessions, digest
from suan.project.aliyun import InvalidResponse
from suan.project.request_executor import ConfirmedCancellation, DefinitiveFailure, RequestBusy, _RequestLock
from suan.project.store import ProjectError, RevisionConflict

from . import tools as tools_module, wire

LIMITS = {"model_turns_per_user_turn": 12, "consecutive_tool_errors": 3, "tokens_per_user_turn": 200_000,
          "wall_seconds_per_user_turn": 1800, "transcript_bytes": wire.MAX_TRANSCRIPT_BYTES,
          "tool_result_bytes": tools_module.MAX_RESULT_BYTES}
MIN_PLANNER_CONTEXT = 16384
MAX_SESSIONS_PER_PROJECT = 1
MAX_SESSIONS = 2
_NEAR = {"local": 0, "internal": 1, "external": 2}


class AgentBusy(RequestBusy):
    """Another session of this project, or the service's limit of running sessions, is in the way."""


@dataclass
class _Run:
    store: object
    session_id: str
    lock: object
    turn: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class AgentExecutor:
    def __init__(self, gateway, requests=None, local=None, *, tool_names=None, limits=None, services=None):
        self.gateway = gateway
        self.requests = requests
        self.local = local
        self.tool_names = tool_names
        self.limits = {**LIMITS, **(limits or {})}
        self.services = services or {}
        self._runs = {}
        self._guard = threading.Lock()
        self._closing = threading.Event()

    # ---- route and creation ----

    def route(self):
        """Planner candidates: models on this computer or the organization's network (v1), local ones served with at
        least a 16K context; every external endpoint is ruled out (as for private data)."""
        try:
            local = self.local.routing_view() if self.local is not None else []
        except (ProjectError, OSError):
            local = []
        result = candidates(self.gateway.describe()["endpoints"], local, task="complex", public=False,
                            min_context=MIN_PLANNER_CONTEXT)
        result["choice"] = result["candidates"][0] if result["candidates"] else None
        return result

    def create(self, store, session_id, text, *, turn_id, configuration=None):
        """Freeze a session (system prompt, skills, tools, model, route, policy, limits) with its first message.
        Nothing is sent: call ``start``. The same request again returns the session it made, whatever the route says
        now (the digest covers what the caller sent, not the model the route chose)."""
        request = digest({"text": text, "turn_id": turn_id, "configuration": configuration})
        existing = store.agent_sessions.replay(session_id, request)
        if existing is not None:
            return existing
        route = self.route()
        if configuration is None:
            choice = route["choice"]
            if choice is None:
                raise ProjectError("No model on this computer or the organization's network can run the agent: install a "
                                   "local model (16K context or more) or add an organization endpoint")
            configuration = {"adapter": choice["adapter"], "model": choice["model"], "max_output_tokens": 4096}
        tools = tools_module.registry(self.tool_names)
        definitions = [tool.definition() for tool in tools]
        skills = wire.skills_for([tool.name for tool in tools])
        header = {"id": session_id, "harness": HARNESS, "system": wire.SYSTEM, "system_sha256": digest(wire.SYSTEM),
                  "skills": skills, "tools": definitions, "tools_sha256": digest(definitions), "configuration": configuration,
                  "route": {"task": "complex", "candidates": route["candidates"][:5], "excluded": route["excluded"][:20]},
                  "policy": {"network": self.gateway.policy.get()["network"], "planner_locations": ["local", "internal"]},
                  "limits": self.limits}
        return store.agent_sessions.create(session_id, header, text, turn_id=turn_id, request_sha256=request)

    # ---- running ----

    def start(self, store, session_id, *, wait=False):
        """Answer the session's unanswered message in the background (``wait``: here). Repeated calls never resend."""
        key = (str(store.directory), session_id)
        while True:
            view = store.agent_sessions.get(session_id, limit=1)
            if view["state"] != "ready":
                return store.agent_sessions.get(session_id)
            with self._guard:
                if self._closing.is_set():
                    raise ProjectError("The agent service is shutting down")
                previous = self._runs.get(key)
                if previous is None:
                    same_project = sum(1 for (directory, _) in self._runs if directory == str(store.directory))
                    if same_project >= MAX_SESSIONS_PER_PROJECT or len(self._runs) >= MAX_SESSIONS:
                        raise AgentBusy("Another agent session is running; wait for it or cancel it")
                    run = _Run(store, session_id, _RequestLock(store, session_id, "agent-locks"), turn=view["turn"])
                    self._runs[key] = run
                    break
                if previous.turn == view["turn"]:
                    return store.agent_sessions.get(session_id)
            # The run for the previous message has stopped and is finishing: wait for it, then answer this one.
            if previous.thread is not None:
                previous.thread.join()
        run.thread = threading.Thread(target=self._run, args=(run,), name="stk-agent", daemon=True)
        run.thread.start()
        if wait:
            run.thread.join()
        return store.agent_sessions.get(session_id)

    def running(self, store, session_id):
        return (str(store.directory), session_id) in self._runs

    def cancel(self, store, session_id):
        """Record the intent, then stop the current model turn (a local model confirms; others become uncertain) and
        any request the session is waiting for."""
        view = store.agent_sessions.get(session_id)
        run = self._runs.get((str(store.directory), session_id))
        if run is None:
            return view
        store.agent_sessions.append(session_id, "cancel_requested", {"at": time.time()}, turn=view["turn"])
        run.cancel.set()
        return store.agent_sessions.get(session_id)

    def recover(self, store, session_id):
        """Settle what a lost executor left open, explicitly: a claimed turn without its outcome is uncertain (never
        resent) and ends the session; a tool call without its result is recorded as unknown."""
        with self._guard:
            if (str(store.directory), session_id) in self._runs:
                raise AgentBusy("This agent session is running in this service")
            lock = _RequestLock(store, session_id, "agent-locks")
        try:
            self._settle_lost(store, session_id)
            return store.agent_sessions.get(session_id)
        finally:
            lock.release()

    @staticmethod
    def _settle_lost(store, session_id):
        """Record what a lost executor left open (with the session's lock held). True when a planner turn was open:
        its outcome is unknown, so it is never resent and the session ends."""
        sessions = store.agent_sessions
        _, events = sessions.events(session_id)
        claims, calls = AgentSessions.open_steps(events)
        for event in calls:
            content = '{"status":"unknown"}'
            sessions.append(session_id, "tool_result", {
                "call_id": event["call_id"], "status": "unknown", "content": content, "content_sha256": digest(content),
                "truncated": False, "objects": [], "sources": []}, turn=event["turn"])
        for event in claims:
            sessions.append(session_id, "model_settled", {"call": event["call"], "status": "uncertain",
                                                          "code": "executor_lost"}, turn=event["turn"])
        if claims and AgentSessions.state(sessions.events(session_id)[1])["state"] != "ended":
            sessions.append(session_id, "stopped", {"reason": "interrupted"}, turn=claims[-1]["turn"])
        return bool(claims)

    def shutdown(self, *, wait=False):
        self._closing.set()
        with self._guard:
            runs = list(self._runs.values())
        for run in runs:
            run.cancel.set()
        if wait:
            for run in runs:
                if run.thread is not None:
                    run.thread.join(30)

    # ---- the loop ----

    def _run(self, run):
        store, session_id = run.store, run.session_id
        sessions = store.agent_sessions
        try:
            if self._settle_lost(store, session_id):
                return  # a planner turn of this message was claimed by a lost executor: never send it again
            header, events = sessions.events(session_id)
            state = AgentSessions.state(events)
            if state["state"] != "ready":
                return
            turn = state["turn"]
            started = time.monotonic()
            # Calls are numbered within the message, across runs (a run lost between steps leaves the message ready).
            calls = sum(1 for event in events if event["kind"] == "model_claimed" and event["turn"] == turn)
            errors = tokens = 0
            configuration = dict(header["configuration"])
            tried = {self._endpoint_of(configuration)}
            names = {tool["name"]: tool for tool in header["tools"]}
            while True:
                _, events = sessions.events(session_id)
                if run.cancel.is_set() or self._closing.is_set():
                    sessions.append(session_id, "stopped", {"reason": "cancelled"}, turn=turn)
                    return
                over = (calls >= header["limits"]["model_turns_per_user_turn"]
                        or tokens >= header["limits"]["tokens_per_user_turn"]
                        or time.monotonic() - started >= header["limits"]["wall_seconds_per_user_turn"])
                outcome = self._turn(run, header, events, configuration, turn, calls, "none" if over else "auto")
                calls += 1
                if outcome["kind"] == "settled":
                    if outcome["code"] == "adapter_failed" and not over:
                        nearer = self._next_candidate(header, configuration, tried)
                        if nearer is not None:
                            tried.add(nearer["endpoint"])
                            configuration = {**configuration, "adapter": nearer["adapter"], "model": nearer["model"]}
                            sessions.append(session_id, "policy", {"fallback": {"endpoint": nearer["endpoint"],
                                                                                "model": nearer["model"]}}, turn=turn)
                            continue
                    reason = {"uncertain": "uncertain", "cancelled": "cancelled"}.get(outcome["status"], "error")
                    sessions.append(session_id, "stopped", {"reason": reason, "code": outcome["code"]}, turn=turn)
                    return
                if outcome["kind"] == "refused":
                    sessions.append(session_id, "stopped", {"reason": outcome["reason"], "message": outcome["message"][:1000]},
                                    turn=turn)
                    return
                reply = outcome["reply"]
                tokens += int(reply.metadata.get("input_tokens", 0)) + int(reply.metadata.get("output_tokens", 0))
                if reply.tool_call is None or over:
                    awaiting = self._awaiting(store, session_id)
                    if awaiting:
                        sessions.append(session_id, "awaiting_user", {"text": reply.text or "", "items": awaiting}, turn=turn)
                    sessions.append(session_id, "stopped", {"reason": "limit" if over else "final"}, turn=turn)
                    return
                ok = self._tool(run, header, names, reply.tool_call, turn)
                errors = 0 if ok else errors + 1
                if errors >= header["limits"]["consecutive_tool_errors"]:
                    sessions.append(session_id, "stopped", {"reason": "error", "code": "tool_errors"}, turn=turn)
                    return
        except Exception as exc:  # noqa: BLE001 - a session must end recorded, never silently
            try:
                sessions.append(session_id, "stopped", {"reason": "error", "code": "executor",
                                                        "message": str(exc)[:1000]},
                                turn=AgentSessions.state(sessions.events(session_id)[1])["turn"])
            except Exception:  # noqa: BLE001
                pass
        finally:
            run.lock.release()
            with self._guard:
                self._runs.pop((str(store.directory), session_id), None)

    def _endpoint_of(self, configuration):
        endpoint = self.gateway.endpoints.by_adapter(configuration["adapter"])
        return endpoint["id"] if endpoint else configuration["adapter"]

    def _next_candidate(self, header, configuration, tried):
        """The next candidate the session showed at its start, on another endpoint, as near or nearer."""
        current = self.gateway.endpoints.by_adapter(configuration["adapter"])
        limit = _NEAR.get(current["location"], 2) if current else 2
        for item in header["route"]["candidates"]:
            if item["endpoint"] not in tried and _NEAR.get(item["location"], 2) <= limit and item["location"] != "external":
                return item
        return None

    def _turn(self, run, header, events, configuration, turn, call, tool_choice):
        """One planner turn: check, claim, send once, record its outcome."""
        sessions, session_id = run.store.agent_sessions, run.session_id
        sources = self._sources(events)
        all_public = self._all_public(run.store, sources)
        try:
            self.gateway.admit_planner(configuration, all_public=all_public)
            adapter = self.gateway.get(configuration["adapter"])
            if adapter is None or not hasattr(adapter, "prepare_turn"):
                raise ProjectError("This model endpoint cannot run the agent (it does not take tool calls)")
            value = wire.turn_input(header, events, configuration, tool_choice=tool_choice)
            prepared = adapter.prepare_turn(value)
        except ProjectError as exc:
            reason = "network" if "network setting" in str(exc) else "private_data" if "private" in str(exc) else "error"
            return {"kind": "refused", "reason": reason, "message": str(exc)}
        endpoint = self.gateway.endpoints.by_adapter(configuration["adapter"])
        sessions.append(session_id, "model_claimed", {
            "call": call, "configuration": configuration, "endpoint": endpoint["id"] if endpoint else None,
            "location": endpoint["location"] if endpoint else None, "sources": sources, "tool_choice": tool_choice,
            "input_sha256": wire.input_digest(value), "transcript_events": len(events)}, turn=turn)
        try:
            reply = prepared.send(value, run.cancel)
        except ConfirmedCancellation:
            return self._settle(run, turn, call, "cancelled", "cancel_confirmed")
        except DefinitiveFailure:
            return self._settle(run, turn, call, "failed", "adapter_failed")
        except InvalidResponse:
            return self._settle(run, turn, call, "failed", "response_invalid")
        except BaseException:  # noqa: BLE001 - anything else after the claim may have reached the model
            return self._settle(run, turn, call, "uncertain", "transport_uncertain")
        tool_call = recorded = None
        if reply.tool_call is not None:
            # The call's identity is the executor's (unique per session), never the model's: some servers repeat IDs,
            # and object IDs, results and the audit are keyed by it. The model's ID is kept for the record.
            tool_call = {**reply.tool_call, "id": str(uuid5(UUID(session_id), f"call:{turn}:{call}")),
                         "model_id": reply.tool_call["id"]}
            reply = wire.ModelTurn(reply.text, tool_call, reply.finish_reason, reply.metadata)
            recorded = {key: tool_call[key] for key in ("id", "model_id", "name", "raw_arguments")}
        try:
            sessions.append(session_id, "model_completed", {"call": call, "text": reply.text, "tool_call": recorded,
                                                            "finish_reason": reply.finish_reason,
                                                            "metadata": reply.metadata}, turn=turn)
        except ProjectError:  # a reply too large to record is not used, and its claim still gets an outcome
            return self._settle(run, turn, call, "failed", "response_invalid")
        return {"kind": "completed", "reply": reply}

    def _settle(self, run, turn, call, status, code):
        run.store.agent_sessions.append(run.session_id, "model_settled", {"call": call, "status": status, "code": code},
                                        turn=turn)
        return {"kind": "settled", "status": status, "code": code}

    def _tool(self, run, header, names, tool_call, turn):
        """Run one tool call: record the call, check it against the frozen definition, run it, record its result."""
        sessions, session_id = run.store.agent_sessions, run.session_id
        definition = names.get(tool_call["name"])
        sessions.append(session_id, "tool_called", {
            "call_id": tool_call["id"], "tool": tool_call["name"], "version": definition["version"] if definition else None,
            "level": definition["level"] if definition else None, "arguments": tool_call["arguments"],
            "arguments_sha256": digest(tool_call["arguments"])}, turn=turn)
        if definition is None:
            result = tools_module.ToolResult("error", {"error": f"There is no tool named {tool_call['name']}"})
        else:
            errors = check_value(tool_call["arguments"], definition["parameters"])
            if errors:
                result = tools_module.ToolResult("error", {"error": "Invalid arguments", "details": errors[:5]})
            else:
                tool = tools_module.REGISTRY[tool_call["name"]]
                context = tools_module.ToolContext(run.store, session_id, turn, tool_call["id"], self.services)
                try:
                    result = tool.handler(context, tool_call["arguments"])
                except (ProjectError, RevisionConflict) as exc:
                    result = tools_module.ToolResult("error", {"error": str(exc)[:1000]})
                except Exception as exc:  # noqa: BLE001 - every recorded call gets a result
                    result = tools_module.ToolResult("error", {"error": f"The tool failed ({type(exc).__name__})"})
        try:
            text, truncated = tools_module.content(tool_call["name"], result)
        except (TypeError, ValueError, RecursionError) as exc:
            result = tools_module.ToolResult("error", {"error": f"The tool's result is not JSON ({type(exc).__name__})"},
                                             result.objects, result.sources)
            text, truncated = tools_module.content(tool_call["name"], result)
        # Each source with its label as it was when the data entered the session (the boundary is checked with the
        # labels as they are when each planner turn is sent).
        sources = [{**source, "label": run.store.labels.label("table", source["id"])} for source in result.sources]
        sessions.append(session_id, "tool_result", {
            "call_id": tool_call["id"], "status": result.status, "content": text, "content_sha256": digest(text),
            "truncated": truncated, "objects": [{"kind": kind, "id": identity} for kind, identity in result.objects],
            "sources": sources}, turn=turn, objects=result.objects)
        return result.status == "ok"

    @staticmethod
    def _sources(events):
        """Every data source the session has read so far (only ever grows: history is resent each turn)."""
        seen, result = set(), []
        for event in events:
            if event["kind"] == "tool_result":
                for source in event.get("sources", []):
                    key = (source["kind"], source["id"])
                    if key not in seen:
                        seen.add(key)
                        result.append({"kind": source["kind"], "id": source["id"]})
        return result

    @staticmethod
    def _all_public(store, sources):
        """With the labels as they are now: a table's values are public only when labelled public; its structure
        when labelled public or structure; anything else counts as private."""
        for source in sources:
            if source["kind"] == "table":
                if not store.labels.is_public("table", source["id"]):
                    return False
            elif source["kind"] == "table_structure":
                if not store.labels.structure_public("table", source["id"]):
                    return False
            else:
                return False
        return True

    def _awaiting(self, store, session_id):
        """What a person must do after this turn (drafts the session saved and nobody applied or discarded yet)."""
        items = []
        for entry in store.agent_sessions.objects(session_id):
            if entry["kind"] != "draft":
                continue
            try:
                draft = store.drafts.get(entry["id"])
            except ProjectError:
                continue
            if draft.get("status") == "pending":
                items.append({"item_id": f"draft:{entry['id']}", "kind": "apply_draft", "draft_id": entry["id"],
                              "draft_sha256": draft.get("sha256"), "base_revision": draft.get("base_revision")})
        return items


__all__ = ["AgentBusy", "AgentExecutor", "LIMITS", "MIN_PLANNER_CONTEXT"]
