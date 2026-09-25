"""Monitoring events v1 writer (standard library only).

``Emitter()`` appends events to ``$STK_MONITOR_PATH``, which the STK Runtime worker sets
to ``<task_dir>/events.jsonl``. Without that variable, or on an MPI rank other than 0,
every call is a no-op, so programs behave the same outside STK. The file is opened once
with ``O_APPEND`` and every event is one ``write()`` of one whole line; there is no fsync
except once after ``run.completed``. ``seq`` continues after the last complete line of an
existing file. ``progress`` is coalesced to at most one line per second, and the latest
value is always written before ``run.completed`` and on ``close()``.

The emitter never raises into its caller: an I/O error disables it (reported once on
stderr), and an event that is invalid or would not fit in 16 KiB is dropped with a stderr
note (``message`` text is truncated to fit instead). Every method returns ``True`` when
the event was written (or, for ``progress``, accepted for coalescing) and ``False``
otherwise.
"""

import json
import math
import os
import platform
import stat
import sys
import threading
import time

from .events import (ENV_FAKE_TIME, ENV_PATH, MAX_LINE, MAX_TEXT, RANK_ENV, SOURCE, TAIL_WINDOW, EventError,
                     encode_line, encode_number, make_event, validate_event)

MAX_REPORTS = 50  # distinct stderr notes per emitter


def detect_rank(environ=None):
    """MPI rank from the first set launcher variable (RANK_ENV); 0 when none is set, -1 when unreadable."""
    environ = os.environ if environ is None else environ
    for name in RANK_ENV:
        value = environ.get(name)
        if value is not None and value.strip():
            try:
                return int(value)
            except ValueError:
                return -1
    return 0


def _last_seq(lines):
    for line in reversed(lines):
        try:
            seq = json.loads(line).get("seq")
        except (ValueError, AttributeError, RecursionError):
            continue
        if type(seq) is int and seq >= 0:
            return seq
    return None


def _last_newline(stream, size):
    position = size
    while position > 0:
        start = max(0, position - TAIL_WINDOW)
        stream.seek(start)
        found = stream.read(position - start).rfind(b"\n")
        if found >= 0:
            return start + found
        position = start
    return -1


def recover(path, size):
    """``(next_seq, ends_with_newline)`` for an existing events file of ``size`` bytes.

    Whole lines are examined backwards in TAIL_WINDOW blocks until one carries a valid
    ``seq`` (normally within the first block); memory stays bounded whatever the file holds.
    """
    if size <= 0:
        return 0, True
    with open(path, "rb") as stream:
        last = _last_newline(stream, size)
        complete = last == size - 1
        # [0, position) holds whole lines; `rest` is the part of a line that starts before it.
        position, rest = last + 1, b""
        while position > 0:
            start = max(0, position - TAIL_WINDOW)
            stream.seek(start)
            lines = (stream.read(position - start) + rest).split(b"\n")[:-1]
            if start:
                head, lines = lines[0], lines[1:]
                rest = (head if len(head) <= MAX_LINE else b"\xff") + b"\n"  # an oversized line is invalid anyway
            seq = _last_seq(lines)
            if seq is not None:
                return seq + 1, complete
            position = start
    return 0, complete


class Emitter:
    """Append-only JSONL event writer; see the module docstring for the rules.

    ``path`` defaults to ``$STK_MONITOR_PATH``; ``rank`` defaults to the detected MPI rank.
    ``environ`` replaces ``os.environ`` for those lookups; ``clock`` (monotonic seconds)
    drives progress coalescing.
    """

    def __init__(self, path=None, *, src="program", rank=None, environ=None, min_interval=1.0, clock=None):
        environ = os.environ if environ is None else environ
        self.src = src
        self.path = None
        self.error = None
        self._fd = None
        self._seq = 0
        self._lock = threading.RLock()
        self._reported = set()
        self._pending = None
        self._last_progress = None
        self._min_interval = min_interval
        self._clock = clock or time.monotonic
        self._fake_time = None
        try:
            fake = environ.get(ENV_FAKE_TIME)
            if fake:
                self._fake_time = float(fake)
            if not isinstance(src, str) or not SOURCE.fullmatch(src):
                raise EventError(f"Invalid event source {src!r}")
            target = environ.get(ENV_PATH) if path is None else path
            if not target:
                return
            if (detect_rank(environ) if rank is None else rank) != 0:
                return
            self._open(os.fspath(target))
        except Exception as exc:
            self._disable(exc)

    # -- state -------------------------------------------------------------------------

    @property
    def enabled(self):
        return self._fd is not None

    @property
    def seq(self):
        """The ``seq`` of the next event."""
        return self._seq

    def _report(self, text):
        if text in self._reported or len(self._reported) >= MAX_REPORTS:
            return
        self._reported.add(text)
        try:
            print(f"stk-monitor: {text}", file=sys.stderr, flush=True)
        except Exception:
            pass

    def _disable(self, exc):
        self.error = f"{type(exc).__name__}: {exc}"
        fd, self._fd, self._pending = self._fd, None, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        self._report(f"monitoring disabled: {self.error}")

    def _open(self, target):
        # O_NONBLOCK only keeps a FIFO from blocking the open; it does not affect regular files.
        flags = (os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NONBLOCK", 0))
        fd = os.open(target, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise OSError(f"{target} is not a regular file")
            self._seq, complete = recover(target, info.st_size)
            if not complete:
                # A writer died mid-line: end that line so ours stay whole (readers report it as invalid).
                self._write(fd, b"\n")
        except BaseException:
            os.close(fd)
            raise
        self._fd, self.path = fd, target

    @staticmethod
    def _write(fd, line):
        view = memoryview(line)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("write() made no progress")
            view = view[written:]

    def _ts(self):
        return self._fake_time if self._fake_time is not None else round(time.time(), 6)

    # -- writing ------------------------------------------------------------------------

    def _emit(self, event_type, data, src=None):
        """Write one event; the caller holds the lock and has checked ``enabled``."""
        try:
            event = make_event(self._seq, event_type, data, src or self.src, self._ts())
            if event_type == "message" and isinstance(event["data"].get("text"), str) \
                    and len(event["data"]["text"]) > MAX_TEXT:
                event["data"]["text"] = event["data"]["text"][:MAX_TEXT - 1] + "…"
            validate_event(event)
            line = self._encode(event)
        except EventError as exc:
            self._report(f"dropped {event_type} event: {exc}")
            return False
        try:
            self._write(self._fd, line)
        except OSError as exc:
            self._disable(exc)
            return False
        self._seq += 1
        if event_type == "run.completed":
            try:
                os.fsync(self._fd)
            except OSError:
                pass  # durability is best effort; the Runtime's finished.json decides
        return True

    @staticmethod
    def _encode(event):
        try:
            return encode_line(event)
        except EventError:
            if event["type"] != "message":
                raise
        # Truncate message text until the line fits, cutting by the text's average encoded size per
        # character (escapes and multi-byte characters take more than one byte); "…" takes three.
        body = event["data"]["text"]
        while body:
            size = len(json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
            if size <= MAX_LINE:
                break
            per_char = max(1.0, (len(json.dumps(body, ensure_ascii=False).encode("utf-8")) - 2) / len(body))
            body = body[:max(0, len(body) - max(1, math.ceil((size - MAX_LINE + 3) / per_char)))]
            event["data"]["text"] = body + "…"
        return encode_line(event)

    def _flush_due(self, force=False):
        if self._pending is None or self._fd is None:
            return
        now = self._clock()
        if force or self._last_progress is None or now - self._last_progress >= self._min_interval:
            data, self._pending = self._pending, None
            if self._emit("progress", data):
                self._last_progress = now

    def _progress(self, data, force=False):
        now = self._clock()
        if not force and not _final(data) and self._last_progress is not None \
                and now - self._last_progress < self._min_interval:
            self._pending = data  # the newest value replaces an older unwritten one
            return True
        self._pending = None
        if self._emit("progress", data):
            self._last_progress = now
            return True
        return False

    def emit(self, event_type, data=None, *, src=None):
        """Write an event of any type (``x.*`` for custom types); ``src`` overrides the default source."""
        if self._fd is None:
            return False
        try:
            with self._lock:
                if self._fd is None:
                    return False
                if event_type == "progress":
                    return self._progress(dict(data or {}))
                self._flush_due(force=event_type == "run.completed")
                return self._emit(event_type, data, src)
        except Exception as exc:  # never raise into the program
            self._report(f"dropped {event_type} event: {type(exc).__name__}: {exc}")
            return False

    def flush(self):
        """Write a coalesced progress value that is still pending."""
        if self._fd is None:
            return False
        try:
            with self._lock:
                self._flush_due(force=True)
            return self._fd is not None
        except Exception as exc:
            self._report(f"flush failed: {type(exc).__name__}: {exc}")
            return False

    def close(self):
        """Write any pending progress and close the file; later calls are no-ops."""
        try:
            with self._lock:
                if self._fd is None:
                    return
                self._flush_due(force=True)
                fd, self._fd = self._fd, None
                if fd is not None:
                    os.close(fd)
        except Exception as exc:
            self._report(f"close failed: {type(exc).__name__}: {exc}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # -- event types (docs/specs/stk-events-v1.md §3) -------------------------------------

    def started(self, app, version=None, total_steps=None, ranks=None, host=None, pid=None):
        if self._fd is None:
            return False
        return self.emit("run.started", _compact(app=app, version=version, total_steps=total_steps, ranks=ranks,
                                                 host=host if host is not None else platform.node() or None,
                                                 pid=pid if pid is not None else os.getpid()))

    def phase(self, name, state, elapsed_s=None):
        return self.emit("run.phase", _compact(name=name, state=state, elapsed_s=elapsed_s))

    def progress(self, step=None, total_steps=None, *, completed_steps=None, fraction=None, time=None,
                 time_end=None, time_unit=None, phase=None, eta_s=None, indeterminate=None, force=False):
        """Coalesced to one line per ``min_interval``; a final value (completed >= total) is written at once."""
        if self._fd is None:
            return False
        if isinstance(fraction, float) and isinstance(encode_number(fraction), str):
            fraction = None  # the schema allows only 0..1 or null here
        data = _compact(step=step, completed_steps=completed_steps, total_steps=total_steps, fraction=fraction,
                        time=time, time_end=time_end, time_unit=time_unit, phase=phase, eta_s=eta_s,
                        indeterminate=indeterminate)
        try:
            with self._lock:
                return self._fd is not None and self._progress(data, force)
        except Exception as exc:
            self._report(f"dropped progress event: {type(exc).__name__}: {exc}")
            return False

    def declare(self, name, unit="unspecified", label=None, quantity=None, group=None):
        return self.emit("metric.declare", _compact(name=name, unit=unit, quantity=quantity, label=label, group=group))

    def metrics(self, values, step=None, time=None):
        return self.emit("metrics", _compact(step=step, time=time, values=values))

    def frame(self, dataset, step, path, *, time=None, reader=None, components=None, selector=None, fields=None,
              size=None, sha256=None):
        return self.emit("frame", _compact(dataset=dataset, step=step, path=path, time=time, selector=selector,
                                           fields=fields, reader=reader,
                                           components=components, size=size, sha256=sha256))

    def checkpoint(self, step, path, restartable=None):
        return self.emit("checkpoint", _compact(step=step, path=path, restartable=restartable))

    def artifact(self, path, role, media_type=None):
        return self.emit("artifact", _compact(path=path, role=role, media_type=media_type))

    def message(self, level, text, code=None):
        return self.emit("message", _compact(level=level, text=text, code=code))

    def usage(self, cpu_s=None, rss_peak_bytes=None, gpu=None):
        return self.emit("usage", _compact(cpu_s=cpu_s, rss_peak_bytes=rss_peak_bytes, gpu=gpu))

    def verification(self, verifier, status, failed_checks=()):
        return self.emit("verification", {"verifier": verifier, "status": status, "failed_checks": failed_checks})

    def completed(self, status="succeeded", classification=None, reason=None):
        """``run.completed``; ``status`` may be a bool (True: succeeded, False: failed)."""
        if isinstance(status, bool):
            status = "succeeded" if status else "failed"
        return self.emit("run.completed", _compact(status=status, classification=classification, reason=reason))


def _compact(**data):
    return {key: value for key, value in data.items() if value is not None}


def _final(data):
    total = data.get("total_steps")
    done = data.get("completed_steps", data.get("step"))
    fraction = data.get("fraction")
    return (isinstance(total, int) and isinstance(done, int) and done >= total) \
        or (isinstance(fraction, (int, float)) and fraction >= 1)
