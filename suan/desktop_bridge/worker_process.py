"""Private JSON subprocess transport shared by graph and scripting workers."""
import queue
import subprocess
import threading

import psutil

from .protocol import BridgeError, MAX_LINE_BYTES, decode_line


class WorkerProcess:
    def __init__(self, command, *, cwd=None, max_line=MAX_LINE_BYTES):
        self.max_line = max_line
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=None, close_fds=True, cwd=cwd)
        try:
            self.tree = psutil.Process(self.process.pid)
        except psutil.NoSuchProcess:
            self.tree = None
        self.incoming = queue.Queue(maxsize=16)
        self.outgoing = queue.Queue()
        self.stopped = threading.Event()
        self.stop_lock = threading.Lock()
        self.reader = threading.Thread(target=self._read, daemon=True, name="stk-worker-reader")
        self.writer = threading.Thread(target=self._write, daemon=True, name="stk-worker-writer")
        self.reader.start()
        self.writer.start()

    def _deliver(self, message):
        while not self.stopped.is_set():
            try:
                self.incoming.put(message, timeout=0.05)
                return
            except queue.Full:
                pass

    def _read(self):
        try:
            while not self.stopped.is_set():
                line = self.process.stdout.readline(self.max_line + 1)
                if not line or len(line) > self.max_line or not line.endswith(b"\n"):
                    break
                self._deliver(decode_line(line))
        except (OSError, ValueError, BridgeError):
            pass
        finally:
            self._deliver(None)

    def _write(self):
        try:
            while not self.stopped.is_set():
                line = self.outgoing.get()
                if line is None:
                    return
                self.process.stdin.write(line)
                self.process.stdin.flush()
        except (OSError, ValueError):
            self._deliver(None)

    def stop(self):
        with self.stop_lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            self.outgoing.put(None)
            # User code may have its own subprocess/session. Stop only this worker's tree,
            # including those descendants, before dropping the worker that owns them.
            descendants = set()
            if self.tree is not None:
                try:
                    self.tree.suspend()
                    for _ in range(2):
                        for process in self.tree.children(recursive=True):
                            descendants.add(process)
                            try:
                                process.suspend()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            for process in descendants:
                try:
                    process.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if self.process.poll() is None:
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
            self.process.wait(timeout=5)
            psutil.wait_procs(descendants, timeout=1)
            self.reader.join(timeout=1)
            self.writer.join(timeout=1)
            for stream in (self.process.stdin, self.process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
