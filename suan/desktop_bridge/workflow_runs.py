"""Explicit local execution of prepared workflow runs (P3 W4a, docs/design/workflow-runs.md).

One background thread per started run goes through its rows in order and, within a row, through the
frozen step order. Each step x row is a task; every execution is a numbered attempt recorded in the
project (suan/project/workflow_runs.py), and only the latest attempt can finish. A local simulation
template writes its declared outputs into an attempt directory; those files are registered and frozen
as that row's input snapshot (ordinary, undoable project edits, announced as project changes). An
analysis step prepares one analysis run over that snapshot with the row's frozen parameter values,
refusing if the saved analysis changed after the workflow run was frozen, and executes it through
the local analysis executor. A failed task stops only its row. Starting again (retry) runs the tasks
that have not succeeded. Nothing here calls a model or contacts a Runtime.
"""
import logging
import os
from pathlib import Path
import socket
import threading
import time
from uuid import uuid4

from suan.project.analysis_runs import AnalysisChanged
from suan.project.store import ProjectError, RevisionConflict

from .protocol import BridgeError

MAX_ACTIVE_RUNS = 4
_ANALYSIS_WAIT_SECONDS = 330  # the analysis budget (300 s) plus archiving
_EDIT_RETRIES = 8


class _Cancelled(Exception):
    pass


def _owner_alive(owner):
    """Whether the service process recorded as a run's owner may still be running (same host, pid exists)."""
    if not owner:
        return False
    if owner.get("host") != socket.gethostname():
        return True  # cannot tell from here: assume it runs
    pid = owner.get("pid")
    if type(pid) is not int or pid <= 0:
        return True  # unreadable: assume it runs (recover can still be forced)
    if pid == os.getpid():
        return False  # this process: its live jobs are known to the executor
    try:
        import psutil  # a base dependency
    except ImportError:  # pragma: no cover
        if os.name == "nt":
            return True  # os.kill(pid, 0) would send CTRL_C_EVENT on Windows
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True
    try:
        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001 - when in doubt, the run is not recovered implicitly
        return True


class _Job:
    def __init__(self, store, run_id):
        self.store, self.run_id = store, run_id
        self.cancel = threading.Event()
        self.analysis_run = None
        self.thread = None


def _code(error):
    if isinstance(error, AnalysisChanged):
        return "analysis_changed"
    if isinstance(error, RevisionConflict):
        return "conflict"
    if isinstance(error, BridgeError):
        return error.code
    return "failed"


class WorkflowRunExecutor:
    def __init__(self, analysis_executor, *, changed=None):
        """``changed(store)`` announces the project edits a run makes (registered outputs)."""
        self.analysis = analysis_executor
        self.changed = changed or (lambda store: None)
        self.executor_id = str(uuid4())
        self._lock, self._closing = threading.RLock(), threading.Event()
        self._jobs = {}

    @staticmethod
    def _key(store, run_id):
        return os.path.normcase(str(store.path)), store._project_id, run_id

    # ---- service methods ----

    def start(self, store, run_id):
        """Claim a prepared or stopped run and execute its unfinished tasks in the background."""
        with self._lock:
            if self._closing.is_set():
                raise BridgeError("shutting_down", "Workflow executor is closed")
            key = self._key(store, run_id)
            if key in self._jobs:
                return store.workflow_runs.get(run_id)
            if len(self._jobs) >= MAX_ACTIVE_RUNS:
                raise BridgeError("busy", "The local executor has reached its 4-workflow-run limit")
            record = store.workflow_runs.start(run_id, executor_id=self.executor_id,
                                               owner={"host": socket.gethostname(), "pid": os.getpid()})
            job = _Job(store, run_id)
            job.thread = threading.Thread(target=self._run, args=(job,), daemon=True, name="stk-workflow-" + run_id)
            self._jobs[key] = job
            try:
                job.thread.start()
            except BaseException:
                self._jobs.pop(key, None)
                store.workflow_runs.stop(run_id, executor_id=self.executor_id)
                raise
            return record

    def cancel(self, store, run_id):
        """Stop after the current task; an analysis in flight is cancelled too. Finished tasks stay."""
        with self._lock:
            job = self._jobs.get(self._key(store, run_id))
            record = store.workflow_runs.request_cancel(run_id)
            if job is not None:
                job.cancel.set()
                if job.analysis_run is not None:
                    try:
                        self.analysis.cancel(store, job.analysis_run)
                    except (ProjectError, BridgeError):
                        pass
            return record

    def recover(self, store, run_id, *, force=False):
        """After a service restart: attempts no live executor owns become interrupted and the run stops.
        A run whose recorded service process still exists (another desktop or a headless session) is
        refused unless ``force``: interrupting it would orphan attempts that are still being written."""
        with self._lock:
            if self._key(store, run_id) in self._jobs:
                return store.workflow_runs.get(run_id)
            run = store.workflow_runs.get(run_id)
            if (not force and run["status"] in ("running", "cancel_requested")
                    and run["executor_id"] != self.executor_id and _owner_alive(run.get("owner"))):
                owner = run["owner"]
                raise BridgeError("busy", f"Another STK service (pid {owner.get('pid')} on {owner.get('host')}) may still be "
                                          "running this workflow run; cancel it there, or recover once it has stopped")
            return store.workflow_runs.interrupt(run_id)

    def active(self, store, run_id):
        with self._lock:
            return self._key(store, run_id) in self._jobs

    def close_project(self, store):
        with self._lock:
            for key, job in self._jobs.items():
                if key[:2] == self._key(store, "")[:2]:
                    job.cancel.set()

    def shutdown(self, *, wait=False):
        self._closing.set()
        if not self._lock.acquire(blocking=wait):
            return
        try:
            jobs = list(self._jobs.values())
            for job in jobs:
                job.cancel.set()
        finally:
            self._lock.release()
        if wait:
            deadline = time.monotonic() + 2
            for job in jobs:
                job.thread.join(max(0, deadline - time.monotonic()))

    # ---- execution ----

    def _run(self, job):
        store, runs = job.store, job.store.workflow_runs
        failure = None
        try:
            plan = runs.get(job.run_id)
            needs = self._needs(plan)
            for row in plan["rows"]:
                for step in plan["order"]:
                    if job.cancel.is_set() or self._closing.is_set():
                        return
                    state = runs.get(job.run_id)
                    if state["status"] == "cancel_requested":
                        return  # requested here or by another service process sharing the project
                    tasks = {(t["step"], t["row"]): t for t in state["tasks"]}
                    if tasks[(step, row["id"])]["status"] == "succeeded":
                        continue
                    if any(tasks[(before, row["id"])]["status"] != "succeeded" for before in needs[step]):
                        continue  # an earlier step of this row did not succeed: leave this one pending
                    self._attempt(job, plan, step, row, tasks)
        except Exception as error:  # noqa: BLE001 - the run must stop and stay readable whatever went wrong
            logging.getLogger(__name__).exception("Workflow run %s stopped unexpectedly", job.run_id)
            failure = {"code": "executor_failed", "message": f"{type(error).__name__}: {error}"[:2000]}
        finally:
            try:
                runs.stop(job.run_id, executor_id=self.executor_id, error=failure)
            except (ProjectError, BridgeError):
                pass
            with self._lock:
                self._jobs.pop(self._key(store, job.run_id), None)

    @staticmethod
    def _needs(plan):
        """For each executed step, the executed steps it waits for (links and after)."""
        executed = set(plan["order"])
        needs = {}
        for step in plan["document"]["steps"]:
            if step["id"] not in executed:
                continue
            before = {link["from"].split(".", 1)[0] for link in step.get("inputs", {}).values()} | set(step.get("after", []))
            needs[step["id"]] = sorted(before & executed)
        return needs

    def _attempt(self, job, plan, step, row, tasks):
        runs = job.store.workflow_runs
        attempt = runs.begin_attempt(job.run_id, step, row["id"], executor_id=self.executor_id)
        frozen = plan["steps"][step]
        try:
            if frozen["kind"] == "simulation":
                produced = self._simulate(job, plan, step, row, attempt)
            elif frozen["kind"] == "files":
                produced = {"snapshot_id": frozen["snapshot_id"], "files": frozen["files"]}
            else:
                source = tasks.get((frozen["source"], row["id"])) if frozen["source"] else None
                produced = self._analyze(job, plan, step, row, (source or {}).get("produced"))
        except _Cancelled:
            runs.finish_attempt(job.run_id, step, row["id"], attempt, "cancelled", executor_id=self.executor_id,
                                error={"code": "cancelled", "message": "The run was cancelled"})
            return
        except Exception as error:  # noqa: BLE001 - recorded on the task; other rows continue
            runs.finish_attempt(job.run_id, step, row["id"], attempt, "failed", executor_id=self.executor_id,
                                error={"code": _code(error), "message": str(error) or type(error).__name__})
            return
        runs.finish_attempt(job.run_id, step, row["id"], attempt, "succeeded", executor_id=self.executor_id,
                            produced=produced)

    def _edit(self, job, apply):
        """An ordinary project edit at the current revision, retried when another edit got there first."""
        for _ in range(_EDIT_RETRIES):
            if job.cancel.is_set():
                raise _Cancelled()
            try:
                return apply(job.store.info()["revision"])
            except RevisionConflict:
                time.sleep(0.05)
        raise RevisionConflict("The project kept changing; try this task again")

    def _simulate(self, job, plan, step, row, attempt):
        from suan.workflows.templates import workflow_templates
        frozen = plan["steps"][step]
        template = workflow_templates()[frozen["template"]]
        relative = Path(plan["directory"], f"row-{row['number']}", step, f"attempt-{attempt}")
        directory = job.store.directory / relative
        directory.parent.mkdir(parents=True, exist_ok=True)
        template.run(plan["parameters"][step][row["id"]], directory)
        paths = [directory / name for name in frozen["outputs"]]
        missing = [path.name for path in paths if not path.is_file()]
        if missing:
            raise ProjectError("The template did not write " + ", ".join(missing))
        if job.cancel.is_set():
            raise _Cancelled()
        indexed = self._edit(job, lambda revision: job.store.files.index([str(path) for path in paths], expected_revision=revision))
        self.changed(job.store)
        captured = self._edit(job, lambda revision: job.store.snapshots.capture(indexed["record_ids"], expected_revision=revision))
        self.changed(job.store)
        return {"directory": relative.as_posix(), "snapshot_id": captured["snapshot"]["id"],
                "files": dict(zip(frozen["outputs"], indexed["record_ids"]))}

    def _analyze(self, job, plan, step, row, source):
        frozen = plan["steps"][step]
        if not source or "snapshot_id" not in source or not source.get("files"):
            raise ProjectError("The analysis input step produced no files for this row")
        files = source["files"]
        bindings = {binding: dict(files) for binding in frozen["bindings"]}
        if not bindings:
            raise ProjectError("The analysis step has no linked input")
        overrides = plan["parameters"][step][row["id"]] or None
        run_id = str(uuid4())
        self._edit(job, lambda revision: job.store.analysis_runs.prepare(
            frozen["analysis_id"], source["snapshot_id"], bindings, run_id=run_id, expected_revision=revision,
            parameter_overrides=overrides, expected_document_sha256=frozen["sha256"]))
        job.analysis_run = run_id
        try:
            self.analysis.start(job.store, run_id)
            deadline = time.monotonic() + _ANALYSIS_WAIT_SECONDS
            while True:
                run = job.store.analysis_runs.get(run_id)
                if run["status"] in ("succeeded", "failed", "cancelled", "unknown"):
                    break
                if job.cancel.is_set() and run["status"] in ("prepared", "running"):
                    self.analysis.cancel(job.store, run_id)
                if time.monotonic() > deadline:
                    self.analysis.cancel(job.store, run_id)
                    raise ProjectError("The analysis run did not finish in time")
                time.sleep(0.1)
        finally:
            job.analysis_run = None
        if run["status"] == "cancelled":
            raise _Cancelled()
        if run["status"] != "succeeded":
            error = run.get("error") or {}
            raise ProjectError(f"Analysis run {run_id} {run['status']}: {error.get('message', 'no detail')}")
        return {"analysis_run_id": run_id, "snapshot_id": source["snapshot_id"]}
