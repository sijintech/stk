"""A small framework for legacy adapters (standard library only).

A legacy adapter turns a program's native output files into monitoring events while the
program runs ("adapt" mode: the wrapper removes ``STK_MONITOR_PATH`` from the program's
environment and is the file's only writer). The pieces here are generic:

- ``LineTail`` returns the complete lines appended to a growing text file since the last
  poll, reopening the file on every poll (NFS gives fresh data only on open).
- ``StableFiles`` finds files matching a pattern whose size and mtime stayed the same over
  a number of consecutive polls: candidates for publication once the adapter's own gate
  (for example "the program's progress passed this step") also holds.
- ``PollThread`` calls an adapter's ``poll()`` periodically on a daemon thread; errors are
  reported on stderr and never reach the program or the launcher.
"""

from pathlib import Path
import os
import stat
import sys
import threading

MAX_TAIL_LINE = 1024 * 1024  # longer native lines are skipped
POLL_BYTES = 8 * 1024 * 1024  # bytes read per poll; the rest waits for the next poll


_REPORTED = set()


def report(text):
    """Write an adapter note to stderr once per distinct text (never raises)."""
    if text in _REPORTED or len(_REPORTED) >= 200:
        return
    _REPORTED.add(text)
    try:
        print(f"stk-monitor: {text}", file=sys.stderr, flush=True)
    except Exception:
        pass


class LineTail:
    """Complete lines appended to a text file, read incrementally by byte offset.

    ``poll()`` returns the new lines without their newline, decoded as UTF-8 (invalid bytes
    replaced). A trailing line without a newline waits for a later poll. If the file shrinks
    (it was truncated or replaced) reading starts again at 0. ``line_number`` counts the
    lines returned so far (0-based index of the next line).
    """

    def __init__(self, path, max_line=MAX_TAIL_LINE):
        self.path = Path(path)
        self.max_line = max_line
        self.offset = 0
        self.line_number = 0
        self.restarts = 0
        self._skipping = False

    def poll(self, max_bytes=POLL_BYTES):
        try:
            stream = open(self.path, "rb")
        except FileNotFoundError:
            return []
        with stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return []
            if info.st_size < self.offset:
                self.offset, self.line_number, self._skipping = 0, 0, False
                self.restarts += 1
            stream.seek(self.offset)
            data = stream.read(min(max_bytes, info.st_size - self.offset))
        lines = []
        start = 0
        while True:
            newline = data.find(b"\n", start)
            if newline < 0:
                break
            if self._skipping:
                self._skipping = False
            else:
                lines.append(data[start:newline].decode("utf-8", "replace").rstrip("\r"))
            start = newline + 1
        rest = len(data) - start
        if rest >= self.max_line:
            self._skipping = True  # an oversized line: drop it up to its newline
            start = len(data)
        self.offset += start
        self.line_number += len(lines)
        return lines

    def drain(self):
        """Every complete line available now, however many polls that takes."""
        lines = []
        while True:
            before = self.offset
            lines += self.poll()
            if self.offset == before:
                return lines


class StableFiles:
    """Files in ``directory`` whose names match ``pattern``, stable over ``polls`` observations."""

    def __init__(self, directory, pattern, polls=2):
        self.directory = Path(directory)
        self.pattern = pattern
        self.polls = max(1, polls)
        self.published = set()
        self._history = {}

    def candidates(self, force=False):
        """``[(name, match, size)]`` not yet published, sorted by name.

        A file qualifies when its (size, mtime) was identical in the last ``polls``
        consecutive calls, or at once with ``force`` (the writer has exited). Only
        unpublished names are stat'ed.
        """
        found = {}
        try:
            entries = list(os.scandir(self.directory))
        except FileNotFoundError:
            entries = []
        for entry in entries:
            if entry.name in self.published:
                continue
            match = self.pattern.search(entry.name)
            if not match:
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            key = (info.st_size, info.st_mtime_ns)
            previous = self._history.get(entry.name)
            count = previous[1] + 1 if previous and previous[0] == key else 1
            found[entry.name] = (key, count, match)
        self._history = {name: (key, count) for name, (key, count, _) in found.items()}
        return [(name, match, key[0]) for name, (key, count, match) in sorted(found.items())
                if force or count >= self.polls]

    def publish(self, name):
        self.published.add(name)
        self._history.pop(name, None)


class PollThread:
    """Run ``poll()`` every ``interval`` seconds on a daemon thread until ``stop()``."""

    def __init__(self, poll, interval, name="stk-monitor-adapter"):
        self._poll = poll
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def _run(self):
        while not self._stop.wait(self.interval):
            safe_call(self._poll)

    def start(self):
        self._thread.start()
        return self

    def stop(self, timeout=30.0):
        """Stop and join; True when the thread has ended (a poll stuck in I/O may outlive the timeout)."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout)
        return not self._thread.is_alive()


def safe_call(function, *args, **kwargs):
    """Call an adapter function; any exception is reported on stderr and swallowed."""
    try:
        return function(*args, **kwargs)
    except Exception as exc:
        report(f"adapter error: {type(exc).__name__}: {exc}")
        return None
