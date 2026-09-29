"""Explicit, single-attempt execution of saved text requests.

No adapter is installed by default. Callers may inject trusted adapter objects with
``send(frozen_input, cancel_event)`` returning text or :class:`TextResponse`.
Adapters must not retry a submission themselves. A cancellation event only conveys
local intent; :class:`ConfirmedCancellation` requires proof of a terminal outcome.

The claim is committed before ``send``. A per-request OS lock stays held for the
entire worker lifetime, including after shutdown fences its result. Recovery only
marks abandoned work uncertain; neither opening a project nor recovery sends it.
"""

from copy import deepcopy
from dataclasses import dataclass
import os
import stat
import threading
from uuid import uuid4

from .discussion import _message_text
from .requests import _validate_metadata
from .store import ProjectError, _id


class RequestBusy(ProjectError):
    """Another live executor still holds this request's local execution lock."""


class DefinitiveFailure(Exception):
    """An adapter has evidence that this attempt failed; details are never stored."""


class ConfirmedCancellation(Exception):
    """An adapter has evidence that remote cancellation reached a terminal state."""


@dataclass(frozen=True)
class TextResponse:
    text: str
    metadata: dict | None = None


_HELD_LOCKS = set()
_HELD_LOCKS_GUARD = threading.Lock()


class _RequestLock:
    """Persistent lock files are never removed or replaced by this service."""

    def __init__(self, store, request_id):
        _id(request_id)
        directory = store.directory
        for name in (".stk", "request-locks"):
            directory = directory / name
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                raise ProjectError("Request lock directories must not be files or symbolic links")
            directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / (request_id + ".lock")
        if path.is_symlink():
            raise ProjectError("Request lock files must not be symbolic links")
        self.key = os.path.normcase(str(path))
        self.stream = None
        with _HELD_LOCKS_GUARD:
            if self.key in _HELD_LOCKS:
                raise RequestBusy("A live executor still owns this request")
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
                         | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
            stream = os.fdopen(fd, "r+b", buffering=0)
            try:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ProjectError("Request locks must be regular files")
                if os.name == "nt":
                    import msvcrt
                    if info.st_size == 0:
                        stream.write(b"0")
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                stream.close()
                raise RequestBusy("A live executor still owns this request") from None
            except BaseException:
                stream.close()
                raise
            self.stream = stream
            _HELD_LOCKS.add(self.key)

    def release(self):
        with _HELD_LOCKS_GUARD:
            if self.stream is not None:
                # Closing releases both flock and Windows byte-range locks.
                self.stream.close()
                self.stream = None
                _HELD_LOCKS.discard(self.key)


@dataclass
class _Job:
    store: object
    request_id: str
    lock: _RequestLock
    cancel: threading.Event


class RequestExecutor:
    """A trusted local adapter coordinator with no automatic replay or network setup.

    ``start`` returns the durable claim immediately. Read the saved request for its
    result. ``cancel`` records intent before notifying a local adapter; cancellation
    by another process cannot signal this process's event. ``shutdown`` never waits
    for a stuck adapter or releases its execution lock early.
    """

    def __init__(self, adapters=None):
        self.executor_id = str(uuid4())
        self._adapters = dict(adapters or {})
        self._lock = threading.RLock()
        self._active = {}
        self._closed = False

    @staticmethod
    def _key(store, request_id):
        return str(store.path), store._project_id, request_id

    def _check_open(self):
        if self._closed:
            raise ProjectError("Request executor is closed")

    def start(self, store, request_id):
        """Start a pending request once; repeated starts never resend it."""
        with self._lock:
            self._check_open()
            record = store.requests.get(request_id)
            if record["status"] != "pending":
                return record
            adapter = self._adapters.get(record["configuration"]["adapter"])
            if adapter is None or not callable(getattr(adapter, "send", None)):
                raise ProjectError("No trusted adapter is configured for this request")
            try:
                lease = _RequestLock(store, request_id)
            except RequestBusy:
                # A simultaneous start may have claimed it while we acquired the lock.
                record = store.requests.get(request_id)
                if record["status"] != "pending":
                    return record
                raise
            try:
                frozen_input = deepcopy(store.requests.input(request_id))
                record, claimed = store.requests._claim(request_id, executor_id=self.executor_id)
                if not claimed:
                    lease.release()
                    return record
                job = _Job(store, request_id, lease, threading.Event())
                key = self._key(store, request_id)
                self._active[key] = job
                try:
                    thread = threading.Thread(target=self._run, args=(job, adapter, frozen_input),
                                              name="stk-text-request", daemon=True)
                    thread.start()
                except Exception:
                    self._active.pop(key, None)
                    return store.requests._settle(request_id, executor_id=self.executor_id,
                                                  status="failed", code="dispatch_failed")
                return record
            except BaseException:
                lease.release()
                raise
            finally:
                if self._key(store, request_id) not in self._active:
                    lease.release()

    def _settle(self, job, status, code):
        return job.store.requests._settle(job.request_id, executor_id=self.executor_id,
                                          status=status, code=code)

    def _run(self, job, adapter, frozen_input):
        try:
            with self._lock:
                if self._closed:
                    return
                # An explicit cancellation can race the claim before send has begun.
                if job.cancel.is_set() or job.store.requests.get(job.request_id)["cancel_requested"]:
                    self._settle(job, "cancelled", "cancel_confirmed")
                    return
            try:
                response = adapter.send(frozen_input, job.cancel)
            except ConfirmedCancellation:
                status, code = "cancelled", "cancel_confirmed"
            except DefinitiveFailure:
                status, code = "failed", "adapter_failed"
            except BaseException:
                status, code = "uncertain", "transport_uncertain"
            else:
                try:
                    if isinstance(response, str):
                        response = TextResponse(response)
                    if not isinstance(response, TextResponse):
                        raise ProjectError("Adapter did not return a complete text response")
                    text = _message_text(response.text)
                    metadata = _validate_metadata(response.metadata)
                except Exception:
                    status, code = "failed", "response_invalid"
                else:
                    with self._lock:
                        if not self._closed:
                            try:
                                job.store.requests._complete(job.request_id, executor_id=self.executor_id,
                                                             text=text, metadata=metadata)
                            except (ProjectError, OSError):
                                self._settle(job, "uncertain", "local_save_failed")
                    return
            with self._lock:
                if not self._closed:
                    self._settle(job, status, code)
        except BaseException:
            # A removed/replaced/temporarily unavailable original database cannot be
            # redirected to the current project. Its claim remains recoverable locally.
            with self._lock:
                if not self._closed:
                    try:
                        self._settle(job, "uncertain", "local_save_failed")
                    except BaseException:
                        pass
        finally:
            with self._lock:
                self._active.pop(self._key(job.store, job.request_id), None)
                job.lock.release()

    def cancel(self, store, request_id):
        """Persist cancellation intent, then notify this executor's worker if any."""
        with self._lock:
            self._check_open()
            record = store.requests.cancel(request_id)
            job = self._active.get(self._key(store, request_id))
            if job is not None:
                job.cancel.set()
            return record

    def recover(self, store, request_id):
        """Mark a lost execution uncertain only after proving its lock is free."""
        with self._lock:
            self._check_open()
            record = store.requests.get(request_id)
            if record["status"] != "running":
                return record
            lease = _RequestLock(store, request_id)
            try:
                record = store.requests.get(request_id)
                if record["status"] == "running":
                    return store.requests._settle(request_id, executor_id=record["executor_id"],
                                                  status="uncertain", code="executor_lost")
                return record
            finally:
                lease.release()

    def shutdown(self):
        """Fence late responses, retain live-worker locks, and never replay a send."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for job in self._active.values():
                job.cancel.set()
                try:
                    self._settle(job, "uncertain", "executor_lost")
                except (ProjectError, OSError):
                    pass  # A later explicit recover can reconcile an unavailable file.
