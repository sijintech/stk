"""Private SSH process guardian. Parent-pipe EOF also closes the owned process tree."""
import json
import os
import subprocess
import sys

import psutil


def stop_tree(process, tree):
    children = set()
    try:
        tree.suspend()
        for _ in range(2):
            for child in tree.children(recursive=True):
                children.add(child)
                try:
                    child.suspend()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
        pass
    for child in children:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    psutil.wait_procs(children, timeout=1)


def main():
    line = sys.stdin.buffer.readline(65537)
    if not line or len(line) > 65536:
        return 2
    command = json.loads(line)
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        return 2
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=None, close_fds=True,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        tree = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        tree = None
    # Detect both SSH exit and parent EOF without a blocking main-thread wait on either pipe.
    import threading
    closed = threading.Event()

    def parent_reader():
        try:
            while sys.stdin.buffer.read(1):
                pass
        finally:
            closed.set()

    threading.Thread(target=parent_reader, daemon=True).start()
    try:
        while not closed.wait(0.05):
            if process.poll() is not None:
                return process.returncode
    finally:
        stop_tree(process, tree)
    return 0


if __name__ == "__main__":
    # A daemon reader can still hold Python's stdin lock when SSH exits first.
    # All owned children are already reaped; avoid interpreter finalization on that lock.
    import os
    try:
        result = main()
    except Exception as exc:
        print(f"SSH guardian: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        result = 1
    os._exit(result if 0 <= result <= 255 else 1)
