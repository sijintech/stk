"""Explicit, single-attempt execution of saved text requests.

No adapter is installed by default. Callers may inject trusted adapter objects with
``send(frozen_input, cancel_event)`` returning text or :class:`TextResponse`.
An optional ``send_stream(frozen_input, cancel_event, on_text)`` reports text
deltas to a bounded in-memory buffer and still returns the complete response.
Adapters must not retry a submission themselves. A cancellation event only conveys
local intent; :class:`ConfirmedCancellation` requires proof of a terminal outcome.

The claim is committed before ``send``. A per-request OS lock stays held for the
entire worker lifetime, including after shutdown fences its result. Recovery only
marks abandoned work uncertain; neither opening a project nor recovery sends it.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import os
import stat
import threading
from uuid import uuid4

from .discussion import MAX_TEXT_BYTES, _message_text
from .requests import _validate_metadata
from .store import ProjectError, _id


class RequestBusy(ProjectError):
    """An execution lock is held or this executor has reached its active-job limit."""


class DefinitiveFailure(Exception):
    """An adapter has evidence that this attempt failed; details are never stored."""


class ConfirmedCancellation(Exception):
    """An adapter has evidence that remote cancellation reached a terminal state."""


class InvalidResponse(Exception):
    """A received response is incomplete or cannot be published as valid text."""


@dataclass(frozen=True)
class TextResponse:
    text: str
    metadata: dict | None = None


_HELD_LOCKS = set()
_HELD_LOCKS_GUARD = threading.Lock()
MAX_ACTIVE_REQUESTS = 8


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
    streaming: bool = False
    accepting: threading.Event = field(default_factory=threading.Event)
    text: bytearray = field(default_factory=bytearray)
    sequence: int = 0
    invalid_text: bool = False


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
        self._closing = threading.Event()

    @staticmethod
    def _key(store, request_id):
        return str(store.path), store._project_id, request_id

    def _check_open(self):
        if self._closing.is_set():
            raise ProjectError("Request executor is closed")

    @staticmethod
    def _can_send(adapter):
        return callable(getattr(adapter, "send_stream", None)) or callable(getattr(adapter, "send", None))

    def start(self, store, request_id):
        """Start a pending request once; repeated starts never resend it."""
        with self._lock:
            self._check_open()
            record = store.requests.get(request_id)
            if record["status"] != "pending":
                return record
            if len(self._active) >= MAX_ACTIVE_REQUESTS:
                raise RequestBusy("The local request executor already has 8 active requests")
            adapter = self._adapters.get(record["configuration"]["adapter"])
            if adapter is None or not (self._can_send(adapter) or callable(getattr(adapter, "prepare", None))):
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
                prepare = getattr(adapter, "prepare", None)
                if callable(prepare):
                    adapter = prepare(deepcopy(frozen_input))
                    if not self._can_send(adapter):
                        raise ProjectError("Adapter preparation did not produce a text sender")
                self._check_open()
                record, claimed = store.requests._claim(request_id, executor_id=self.executor_id)
                if not claimed:
                    lease.release()
                    return record
                job = _Job(store, request_id, lease, threading.Event(),
                           streaming=callable(getattr(adapter, "send_stream", None)))
                if job.streaming:
                    job.accepting.set()
                key = self._key(store, request_id)
                self._active[key] = job
                try:
                    thread = threading.Thread(target=self._run, args=(job, adapter, frozen_input),
                                              name="stk-text-request", daemon=True)
                    thread.start()
                except Exception:
                    job.accepting.clear()
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

    def _on_text(self, job, delta):
        """Accept only live deltas; a retained callback cannot revive a finished job."""
        if self._closing.is_set() or not job.accepting.is_set():
            return
        with self._lock:
            if (self._closing.is_set() or not job.accepting.is_set()
                    or self._active.get(self._key(job.store, job.request_id)) is not job):
                return
            try:
                # Check code points before encoding so an arbitrary oversized
                # callback cannot allocate an unbounded temporary UTF-8 buffer.
                if job.invalid_text or not isinstance(delta, str) or len(delta) > MAX_TEXT_BYTES:
                    raise ValueError
                encoded = delta.encode("utf-8")
                if len(job.text) + len(encoded) > MAX_TEXT_BYTES:
                    raise ValueError
            except (ValueError, UnicodeError):
                job.invalid_text = True
                raise InvalidResponse("Stream text exceeds its limit or is not valid UTF-8") from None
            if encoded:
                job.text.extend(encoded)
                job.sequence += 1

    def progress(self, store, request_id):
        """Read validated saved state and this owner's ephemeral text without sending.

        A missing snapshot makes no assertion about remote execution. The original
        database and request lineage are checked even when an in-memory job exists.
        """
        with self._lock:
            record = store.requests.get(request_id)
            job = self._active.get(self._key(store, request_id))
            progress = None
            if (not self._closing.is_set() and job is not None and job.streaming
                    and job.accepting.is_set() and not job.invalid_text
                    and record["executor_id"] == self.executor_id
                    and record["status"] == "running" and not record["cancel_requested"]):
                progress = {"executor_id": self.executor_id, "sequence": job.sequence,
                            "text": job.text.decode("utf-8"), "text_bytes": len(job.text)}
            return {"request": record, "progress": progress}

    def _run(self, job, adapter, frozen_input):
        try:
            with self._lock:
                if self._closing.is_set():
                    return
                # An explicit cancellation can race the claim before send has begun.
                if job.cancel.is_set() or job.store.requests.get(job.request_id)["cancel_requested"]:
                    self._settle(job, "cancelled", "cancel_confirmed")
                    return
            try:
                try:
                    response = (adapter.send_stream(frozen_input, job.cancel, lambda delta: self._on_text(job, delta))
                                if job.streaming else adapter.send(frozen_input, job.cancel))
                finally:
                    # Fence callbacks before validating or persisting completion,
                    # including callbacks retained by an adapter-owned thread.
                    job.accepting.clear()
            except ConfirmedCancellation:
                status, code = "cancelled", "cancel_confirmed"
            except DefinitiveFailure:
                status, code = "failed", "adapter_failed"
            except InvalidResponse:
                status, code = "failed", "response_invalid"
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
                    with self._lock:
                        if job.streaming and (job.invalid_text or job.text != text.encode("utf-8")):
                            raise InvalidResponse("Complete text does not match the received stream")
                except Exception:
                    status, code = "failed", "response_invalid"
                else:
                    with self._lock:
                        if not self._closing.is_set():
                            try:
                                job.store.requests._complete(job.request_id, executor_id=self.executor_id,
                                                             text=text, metadata=metadata)
                            except (ProjectError, OSError):
                                self._settle(job, "uncertain", "local_save_failed")
                    return
            with self._lock:
                if not self._closing.is_set():
                    self._settle(job, status, code)
        except BaseException:
            # A removed/replaced/temporarily unavailable original database cannot be
            # redirected to the current project. Its claim remains recoverable locally.
            with self._lock:
                if not self._closing.is_set():
                    try:
                        self._settle(job, "uncertain", "local_save_failed")
                    except BaseException:
                        pass
        finally:
            job.accepting.clear()
            with self._lock:
                if self._closing.is_set() and not self._closed:
                    # The worker can finish before asynchronous shutdown acquires
                    # this lock. Preserve its observation before removing the job.
                    try:
                        self._settle(job, "uncertain", "executor_lost")
                    except (ProjectError, OSError):
                        pass
                self._active.pop(self._key(job.store, job.request_id), None)
                job.text.clear()
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

    def shutdown(self, *, wait=True):
        """Fence late responses, retain live-worker locks, and never replay a send."""
        self._closing.set()
        if not wait:
            # Bridge exit must not wait on a locked/unavailable project database.
            threading.Thread(target=self.shutdown, name="stk-request-shutdown", daemon=True).start()
            return
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for job in self._active.values():
                job.accepting.clear()
                job.text.clear()
                job.cancel.set()
                try:
                    self._settle(job, "uncertain", "executor_lost")
                except (ProjectError, OSError):
                    pass  # A later explicit recover can reconcile an unavailable file.
