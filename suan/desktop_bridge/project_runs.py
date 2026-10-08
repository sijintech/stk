"""Explicit project run commands over the existing Runtime/Hub transport.

No background submission or retry. A durable intent and immutable idempotency key allow the
caller to recover a lost response by explicitly submitting the same run again.
"""
from .backends import FINISHED_ACTIONS, summary
from .protocol import BridgeError


class ProjectRuns:
    def __init__(self, projects, backend_for):
        self.projects, self.backend_for = projects, backend_for

    def call(self, action, params):
        with self.projects.use(params["handle"]) as store:
            runs = store.runs
            if action == "prepare":
                backend = self.backend_for(params["connection"], params.get("node"))
                return runs.prepare(params["entries"], connection=params["connection"], node=params.get("node"),
                                    connection_identity=backend.server_key, expected_revision=params["expected_revision"])
            if action == "list":
                return runs.list(offset=params.get("offset", 0), limit=params.get("limit", 100), archived=params.get("archived"))
            run_id = params["run_id"]
            run = runs.get(run_id)
            if action == "get":
                return {"run": run}
            plan, status = run["plan"], run["status"]
            backend = self.backend_for(plan["connection"], plan["node"])
            if backend.server_key != plan["connection_identity"]:
                raise BridgeError("conflict", "The saved connection points to a different endpoint; restore its profile before accessing this run")
            task = status.get("task")
            if action == "submit":
                if task:
                    return {"run": run}
                if store.archive.is_archived("simulation_run", run_id):
                    raise BridgeError("conflict", "This simulation run is archived; restore it to submit it")
                # An interrupted submission already accepted the frozen plan. An explicit retry
                # recovers that intent even if the editable parameter row has since changed.
                if status["submission"] == "prepared" and run["parameter_state"] != "current" and not params.get("allow_stale", False):
                    raise BridgeError("conflict", "Parameters changed since preparation; prepare a new run or explicitly allow_stale")
                runs.observe(run_id, {"submission": "submitting", "last_operation": action, "error": None})
            elif action == "cancel" and not task:
                raise BridgeError("conflict", "Recover the accepted task ID before cancelling; pending Hub reviews remain in Jobs")
            elif action == "refresh" and not task and not status.get("action"):
                # Do not turn a read into submission, including recovery after response loss.
                return {"run": run}
            try:
                if action == "submit":
                    result = backend.submit(plan["spec"], plan["idempotency_key"])
                elif action == "cancel":
                    result = backend.cancel(task["id"], plan["idempotency_key"] + ":cancel")
                else:
                    result = {}
                    pending = status.get("action")
                    if pending and (not task or pending["state"] not in FINISHED_ACTIONS):
                        record = backend.action_record(pending["id"])
                        result["action"] = summary(record)
                        if record["state"] == "succeeded":
                            result["task"] = record["result"]
                    if task and "task" not in result:
                        result.update(backend.task(task["id"]))
                patch = {"last_operation": action, "error": None}
                if "task" in result:
                    patch.update(task=result["task"], submission="accepted")
                if "action" in result:
                    patch["action"] = result["action"]
                    if not task and "task" not in result:
                        patch["submission"] = result["action"]["state"]
                runs.observe(run_id, patch)
            except BridgeError as exc:
                patch = {"last_operation": action, "error": exc.to_json()}
                if action == "submit":
                    patch["submission"] = "uncertain"
                if isinstance(exc.data, dict) and "action" in exc.data:
                    patch["action"] = exc.data["action"]
                runs.observe(run_id, patch)
                raise
            return {"run": runs.get(run_id)}
