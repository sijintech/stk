"""Standalone per-task wrapper, copied to shared storage for compute nodes.

The configured Python interpreter must provide psutil. This file deliberately
does not import STK or Qt. Metadata is outside the program's working directory.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import platform
import signal
import subprocess
import sys
import time
import uuid

import psutil


def write_json(path, data):
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def terminate_tree(process, expected_created=None):
    try:
        parent = psutil.Process(process.pid)
        if expected_created is not None and parent.create_time() != expected_created:
            return
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for child in children + [parent]:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    _, remaining = psutil.wait_procs(children + [parent], timeout=3)
    for child in remaining:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    process.wait()


def run(task_dir):
    root = Path(task_dir).resolve()
    # A duplicate scheduler dispatch cannot start the same task twice.
    lock = open(root / "worker.lock", "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return 1
    if (root / "finished.json").exists():
        lock.close()
        return 0
    stopping = [False]
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.__setitem__(0, True))
    result = {"state": "failed", "exit_code": None, "reason": "Worker did not finish", "started_at": datetime.now(timezone.utc).isoformat()}
    process = None
    try:
        me = psutil.Process()
        write_json(root / "worker.json", {"pid": me.pid, "create_time": me.create_time(), "host": platform.node()})
        launch = json.loads((root / "launch.json").read_text(encoding="utf-8"))
        spec = launch["spec"]
        env = os.environ.copy()
        env.pop("STK_RUNTIME_TOKEN", None)
        env.update(spec["env"])
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("OMP_NUM_THREADS", str(spec["resources"].get("cpus", 1)))
        argv = [launch["python"] if a == "{python}" else a for a in spec["argv"]]
        write_json(root / "environment.json", {"python": sys.version, "interpreter": sys.executable,
                   "platform": platform.platform(), "argv": argv, "env_overrides": spec["env"]})
        if (root / "cancel").exists():
            result.update(state="cancelled", reason="Cancelled before execution")
        else:
            with open(root / "stdout.log", "ab", buffering=0) as stdout, open(root / "stderr.log", "ab", buffering=0) as stderr:
                process = subprocess.Popen(argv, cwd=root / "work", env=env, stdin=subprocess.DEVNULL,
                                           stdout=stdout, stderr=stderr, start_new_session=os.name != "nt")
                try:
                    child = psutil.Process(process.pid)
                    write_json(root / 'program.json', {'pid': child.pid, 'create_time': child.create_time()})
                except psutil.NoSuchProcess:
                    pass  # A short program can exit before its identity is read.
                started = time.monotonic()
                reason = ""
                while process.poll() is None:
                    cancelled = (root / "cancel").exists()
                    if cancelled:
                        reason = "Cancelled by user"
                    elif stopping[0]:
                        reason = "Worker interrupted by signal"
                    walltime = spec["resources"].get("walltime_seconds")
                    if walltime and time.monotonic() - started > walltime:
                        reason = "Walltime limit exceeded"
                    memory = spec["resources"].get("memory_mb")
                    if memory:
                        try:
                            parent = psutil.Process(process.pid)
                            rss = sum(p.memory_info().rss for p in [parent] + parent.children(recursive=True))
                            if rss > memory * 1024 * 1024:
                                reason = "Memory limit exceeded"
                        except psutil.NoSuchProcess:
                            pass
                    if reason:
                        terminate_tree(process)
                        result.update(state="cancelled" if cancelled else "failed", reason=reason)
                        break
                    time.sleep(0.1)
                result["exit_code"] = process.wait()
                if not reason:
                    result.update(state="succeeded" if result["exit_code"] == 0 else "failed",
                                  reason="" if result["exit_code"] == 0 else f"Program exited with code {result['exit_code']}")
                if result["state"] == "succeeded":
                    work = (root / "work").resolve()
                    for name in spec["outputs"]:
                        path = work / name
                        if not path.is_file() or any(p.is_symlink() for p in [path, *path.parents] if p != work and work in p.parents) or work not in path.resolve().parents:
                            result.update(state="failed", reason=f"Expected output is missing or invalid: {name}")
                            break
    except Exception as exc:
        if process and process.poll() is None:
            terminate_tree(process)
        result.update(state="failed", reason=f"{type(exc).__name__}: {exc}")
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(root / "finished.json", result)
        lock.close()
    return 0 if result["state"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
