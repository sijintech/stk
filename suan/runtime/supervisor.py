"""A single durable dispatcher, independent of HTTP and client lifetimes."""

from datetime import datetime
from pathlib import Path
import logging
import signal
import time

from .backends import SubmissionFailed, SubmissionUnknown, backends
from .common import alive, atomic_json, identity, instance_lock, load_config, read_json
from .models import RESERVED_ENV, TERMINAL
from .service import RuntimeService

log = logging.getLogger(__name__)


class Supervisor:
    def __init__(self, config):
        self.config = config
        self.service = RuntimeService(config)
        self.store = self.service.store
        self.backends = backends(config)
        self.queried = {}
        self.deferred = set()
        self.stopping = False

    def tick(self):
        # Unreaped workers count against the user's process limit until launches fail with EAGAIN.
        self.backends["local"].reap()
        records = self.store.tasks()
        for record in records:
            if record["state"] in TERMINAL:
                continue
            try:
                self.refresh(record)
            except Exception as exc:
                log.exception("Cannot reconcile task %s", record["id"])
                changes = {"reason": f"Reconciliation unavailable: {exc}"}
                if record.get('attempted_at'):
                    changes['state'] = 'unknown'
                self.store.update(record["id"], **changes)
        records = self.store.tasks()
        used = sum(r["state"] not in TERMINAL and r.get("attempted_at") is not None
                   and r["spec"]["backend"] == "local" for r in records)
        for record in reversed(records):
            if record["state"] != "queued" or record.get("attempted_at") or record["cancel_requested"]:
                continue
            # A spec stored before TaskSpec refused these runs the worker.py copied at submission,
            # which would pass them through.
            reserved = [key for key in RESERVED_ENV if key in record["spec"].get("env", {})]
            if reserved:
                self.store.update(record["id"], expected={"queued"}, state="failed",
                                  reason=f"Resubmit without {', '.join(reserved)} in env; they come from the "
                                         "Runtime service or scheduler environment")
                continue
            kind = record["spec"]["backend"]
            if kind == "local" and used >= self.config["concurrency"]:
                continue
            claimed = self.store.claim(record["id"])
            if not claimed:
                continue
            try:
                root = self.service.task_dir(record["id"])
            except (KeyError, ValueError, OSError) as exc:
                self.store.update(record["id"], state="failed", reason=f"Dispatch failed: {exc}")
                continue
            try:
                handle = self.backends[kind].submit(claimed, root)
                self.store.update(record["id"], state="queued" if kind != "local" else "running", **handle)
            except SubmissionUnknown as exc:
                self.store.update(record["id"], state="unknown", reason=str(exc))
            except SubmissionFailed as exc:
                # Nothing was started, so resource exhaustion is retried and any
                # other error is terminal. Local dispatch pauses for this tick
                # rather than failing the whole queue at once.
                if exc.transient:
                    if record["id"] not in self.deferred:
                        self.deferred.add(record["id"])
                        log.warning("Dispatch of task %s deferred until resources free up: %s", record["id"], exc)
                    retry = self.store.update(record["id"], state="queued", attempted_at=None, reason=f"Dispatch deferred: {exc}")
                    if retry["cancel_requested"]:
                        self.store.update(record["id"], expected={"queued"}, state="cancelled", reason="Cancelled before dispatch")
                else:
                    self.store.update(record["id"], state="failed", reason=f"Dispatch failed: {exc}")
                if kind == "local":
                    used = self.config["concurrency"]
                continue
            except Exception as exc:
                # Once local launch was attempted a crash could have happened
                # between Popen and handle persistence. Leave it to reconciliation.
                state = "unknown" if kind == "local" and not isinstance(exc, FileNotFoundError) else "failed"
                self.store.update(record["id"], state=state, reason=f"Dispatch failed: {exc}")
            if kind == "local":
                used += 1

    def refresh(self, record):
        root = self.service.task_dir(record["id"])
        finished = read_json(root / "finished.json")
        if finished:
            self.store.update(record["id"], **finished)
            return
        if record["state"] == "preparing":
            # Preparation is synchronous in the API. A stale incomplete snapshot
            # is retained for inspection; it is never dispatched automatically.
            age = time.time() - datetime.fromisoformat(record["created_at"]).timestamp()
            if (record.get('preparer') and not alive(record['preparer'])) or (not record.get('preparer') and age > 3600):
                self.store.update(record["id"], expected={"preparing"}, state="failed", reason="Input preparation interrupted; resubmit with a new request key")
            return
        if not record.get("attempted_at"):
            if record["state"] == "queued" and record["cancel_requested"]:
                # A crash between a cancel or requeue and its second update; claim never takes it.
                self.store.update(record["id"], expected={"queued"}, state="cancelled", reason="Cancelled before dispatch")
            return
        kind = record["spec"]["backend"]
        backend = self.backends[kind]
        if record["cancel_requested"] and not record.get('cancellation_sent'):
            result = backend.cancel(record, root)
            if result:
                record = self.store.update(record["id"], **result)
        interval = 0 if kind == "local" else self.config.get("scheduler_interval", 10)
        if time.monotonic() - self.queried.get(record["id"], 0) < interval:
            return
        self.queried[record["id"]] = time.monotonic()
        observation = backend.query(record, root)
        # Prefer wrapper completion if it appeared while the query was in flight.
        finished = read_json(root / "finished.json")
        if finished:
            observation = finished
        elif observation["state"] == "succeeded":
            observation = {**observation, "state": "unknown", "reason": "Scheduler completed but worker result/output validation is missing"}
        self.store.update(record["id"], **observation)

    def run(self):
        state = Path(self.config["state_dir"])
        with instance_lock(state / "supervisor.lock"):
            atomic_json(state / "supervisor.pid", identity())
            for signum in (signal.SIGTERM, signal.SIGINT):
                signal.signal(signum, lambda *_: setattr(self, "stopping", True))
            while not self.stopping:
                try:
                    self.tick()
                except Exception:
                    log.exception("Supervisor tick failed; retrying")
                time.sleep(self.config.get("poll_interval", 1))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    Supervisor(load_config(args.state_dir)).run()


if __name__ == "__main__":
    main()
