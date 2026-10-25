# SPDX-License-Identifier: GPL-2.0-or-later
"""Stop an owned Linux subprocess tree, including other process groups and sessions.

Like STK's worker cleanup, freeze parents before collecting and freezing their children. pidfds
bind every signal to the observed process, and parent/start-time checks reject a reused PID. This
does not recover descendants that had already detached from the parent tree before cleanup began.
In particular, if the root has already exited, this helper does not discover its reparented children.
Only /proc process metadata is read; environments, command lines and process memory are untouched.
"""
import os
from pathlib import Path
import select
import signal
import time


def require_process_tree_support():
    """Fail before launching a command if this interpreter/kernel denies pidfd operations."""
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("PID-safe subprocess-tree cleanup requires Linux pidfd support")
    descriptor = None
    try:
        descriptor = os.pidfd_open(os.getpid())
        signal.pidfd_send_signal(descriptor, 0)  # Permission check; never stops or kills the caller.
    except OSError as error:
        raise RuntimeError(f"PID-safe subprocess-tree cleanup is unavailable: {error}") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _metadata(pid):
    try:
        # comm can contain spaces and ')'; the remaining fields start with state (field 3).
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(fields[1]), int(fields[19]), fields[0]  # ppid, starttime, state
    except (FileNotFoundError, ProcessLookupError):
        return None


def _children(pid):
    found = set()
    for path in Path(f"/proc/{pid}/task").glob("*/children"):
        try:
            found.update(int(value) for value in path.read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


class _Process:
    def __init__(self, pid, parent):
        self.pid, self.fd = pid, None
        before = _metadata(pid)
        if before is None or before[0] != parent:
            raise ProcessLookupError(pid)
        self.fd = os.pidfd_open(pid)
        after = _metadata(pid)
        if after is None or after[:2] != before[:2]:
            self.close()
            raise ProcessLookupError(pid)
        self.identity = after[:2]

    def exited(self):
        return bool(select.select([self.fd], [], [], 0)[0])

    def send(self, value):
        try:
            signal.pidfd_send_signal(self.fd, value)
        except ProcessLookupError:
            pass

    def freeze(self, deadline):
        self.send(signal.SIGSTOP)
        while not self.exited():
            state = _metadata(self.pid)
            if state is None or state[:2] != self.identity:
                return False
            if state[2] in ("T", "t", "Z", "X"):
                return True
            if time.monotonic() >= deadline:
                raise TimeoutError("Could not stop the owned subprocess tree before cleanup")
            time.sleep(0.001)
        return False

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def stop_process_tree(process, timeout=5):
    """Kill and wait for this live Popen's tree, without signaling arbitrary process groups.

    The root must still be our unreaped child. Successfully exited commands retain their ordinary
    status. Call require_process_tree_support before launching the command so unsupported or
    restricted pidfd environments cannot leave an already-started command without cleanup support.
    """
    if process.poll() is not None:
        return
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("PID-safe subprocess-tree cleanup requires Linux pidfd support")
    deadline = time.monotonic() + timeout
    owned = []
    try:
        try:
            root = _Process(process.pid, os.getpid())
        except ProcessLookupError:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            return
        owned.append(root)
        seen = {root.pid}
        for parent in owned:
            if not parent.freeze(deadline):
                continue
            for pid in _children(parent.pid):
                if pid in seen:
                    continue
                try:
                    child = _Process(pid, parent.pid)
                except ProcessLookupError:
                    continue
                owned.append(child)
                seen.add(pid)
    finally:
        # Descendants first; parents were stopped and cannot fork or reap/reuse their IDs.
        try:
            for child in reversed(owned):
                child.send(signal.SIGKILL)
            if owned:
                process.wait(timeout=max(0, deadline - time.monotonic()))
                for child in owned:
                    if not child.exited() and not select.select(
                            [child.fd], [], [], max(0, deadline - time.monotonic()))[0]:
                        raise TimeoutError("An owned subprocess did not exit after cleanup")
        finally:
            for child in owned:
                child.close()
