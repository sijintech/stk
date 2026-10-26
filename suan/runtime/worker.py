"""Standalone per-task wrapper, copied to shared storage for compute nodes.

The configured Python interpreter must provide psutil. This file deliberately
does not import STK or Qt. Metadata is outside the program's working directory.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import errno
import os
import platform
import select
import signal
import subprocess
import sys
import time
import uuid


def write_json(path, data):
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def terminate_tree(process, expected_created=None):
    import psutil
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


def run_program(gate, exec_confirmation, argv):
    """Keep the future program PID inert until its identity has been published."""
    try:
        try:
            # pass_fds made this inheritable. EOF must mean exec (or helper exit),
            # so the target program must never inherit this confirmation endpoint.
            os.set_inheritable(exec_confirmation, False)
            with os.fdopen(gate, "rb", closefd=False) as stream:
                if stream.read(1) != b"\x01":
                    return 1  # Parent loss before authorization: never execute on EOF.
                encoded = stream.read(environment_limit() + 1)
            if len(encoded) > environment_limit():
                raise OSError(errno.E2BIG, "Program environment exceeds operating system argument limit")
            env = json.loads(encoded)
        finally:
            os.close(gate)
        # Python startup ignores these; preserve Popen's default restore_signals
        # behavior for the native target after this intermediate interpreter.
        for name in ("SIGPIPE", "SIGXFZ", "SIGXFSZ"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), signal.SIG_DFL)
        try:
            os.execvpe(argv[0], argv, env)
        except OSError as exc:
            os.write(exec_confirmation, b"\x00")
            print(f"Program exec failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return 127
    finally:
        os.close(exec_confirmation)


def environment_limit():
    # JSON can expand each environment byte to six ASCII bytes. This transport
    # bound therefore does not reject environments that fit the OS exec budget.
    return 6 * os.sysconf("SC_ARG_MAX")


def run(task_dir):
    import psutil
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
        res = spec["resources"]
        # Mirrors suan.runtime.models.layout(); this file must not import STK.
        mpi = "ranks" in res or "threads_per_rank" in res
        threads = res.get("threads_per_rank", 1) if mpi else res.get("cpus", 1)
        env = os.environ.copy()
        env.pop("STK_RUNTIME_TOKEN", None)
        if mpi:
            # Replace whole-node counts inherited from a login shell or PBS.
            env["OMP_NUM_THREADS"] = env["MKL_NUM_THREADS"] = str(threads)
        env.update(spec["env"])
        # Mirrors models.RESERVED_ENV as defense in depth for tasks run by this copy; the
        # supervisor fails older queued specs that set these before dispatch.
        for key in ("SLURM_JOB_ID", "PBS_JOBID", "STK_ALLOW_LOCAL_MPI", "STK_MUPRO_ALLOW_LOCAL_MPI"):
            if key in os.environ:
                env[key] = os.environ[key]
            else:
                env.pop(key, None)
        # Monitoring events (docs/specs/stk-events-v1.md), set after the spec's env so a
        # TaskSpec cannot redirect them; the file sits outside work/, next to stdout.log.
        env["STK_MONITOR_PATH"] = str(root / "events.jsonl")
        env["STK_TASK_ID"] = str(launch.get("task_id") or root.name)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("OMP_NUM_THREADS", str(threads))
        # Only whole arguments are replaced; user arguments are never formatted.
        tokens = {"{python}": launch["python"], "{ranks}": str(res.get("ranks", 1)),
                  "{threads_per_rank}": str(threads), "{nodes}": str(res.get("nodes", 1))}
        argv = [tokens.get(a, a) for a in spec["argv"]]
        write_json(root / "environment.json", {"python": sys.version, "interpreter": sys.executable,
                   "platform": platform.platform(), "argv": argv, "env_overrides": spec["env"],
                   "layout": {"nodes": res.get("nodes", 1), "ranks": res.get("ranks", 1), "threads_per_rank": threads},
                   "threads": {k: env.get(k) for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS")}})
        if (root / "cancel").exists():
            result.update(state="cancelled", reason="Cancelled before execution")
        else:
            with open(root / "stdout.log", "ab", buffering=0) as stdout, open(root / "stderr.log", "ab", buffering=0) as stderr:
                gate_read = gate_write = exec_read = exec_write = None
                reason = ""
                try:
                    command, options, launch_env = argv, {}, env
                    if os.name != "nt":
                        # Task-controlled loader/Python variables belong only to the
                        # authorized target, never to this interpreter's bootstrap.
                        launch_env = os.environ.copy()
                        launch_env.pop("STK_RUNTIME_TOKEN", None)
                        encoded_env = json.dumps(env).encode("ascii")
                        if len(encoded_env) > environment_limit():
                            raise OSError(errno.E2BIG, "Program environment exceeds operating system argument limit")
                        gate_read, gate_write = os.pipe()
                        exec_read, exec_write = os.pipe()
                        command = [sys.executable, "-I", "-S", str(Path(__file__).resolve()), "--program",
                                   str(gate_read), str(exec_write), *argv]
                        options["pass_fds"] = (gate_read, exec_write)
                    process = subprocess.Popen(command, cwd=root / "work", env=launch_env, stdin=subprocess.DEVNULL,
                                               stdout=stdout, stderr=stderr, start_new_session=os.name != "nt",
                                               **options)
                    if gate_read is not None:
                        os.close(gate_read)
                        gate_read = None
                        os.close(exec_write)
                        exec_write = None
                    try:
                        child = psutil.Process(process.pid)
                        write_json(root / 'program.json', {'pid': child.pid, 'create_time': child.create_time()})
                    except psutil.NoSuchProcess:
                        if gate_write is not None:
                            raise RuntimeError("Program gate exited before its identity was published") from None
                        # Windows retains the direct launch path; a short program can already exit.
                    if gate_write is not None:
                        # write_json fsyncs the file before atomic rename. Only then may this
                        # exact PID exec the program; a killed parent before this point sends EOF.
                        pending = memoryview(b"\x01" + encoded_env)
                        os.set_blocking(gate_write, False)
                        while pending:
                            cancelled = (root / "cancel").exists()
                            if cancelled or stopping[0]:
                                reason = "Cancelled by user" if cancelled else "Worker interrupted by signal"
                                terminate_tree(process)
                                result.update(state="cancelled" if cancelled else "failed", reason=reason)
                                break
                            _, writable, _ = select.select([], [gate_write], [], 0.1)
                            if writable:
                                pending = pending[os.write(gate_write, pending):]
                        os.close(gate_write)
                        gate_write = None
                        # Do not charge helper startup RSS or walltime to the target.
                        # The target's exec closes its endpoint; failed exec also exits.
                        # Keep cancellation and wrapper signals responsive during startup.
                        while not reason:
                            cancelled = (root / "cancel").exists()
                            if cancelled or stopping[0]:
                                reason = "Cancelled by user" if cancelled else "Worker interrupted by signal"
                                terminate_tree(process)
                                result.update(state="cancelled" if cancelled else "failed", reason=reason)
                                break
                            readable, _, _ = select.select([exec_read], [], [], 0.1)
                            if readable:
                                confirmation = os.read(exec_read, 1)
                                if confirmation == b"\x00":
                                    # Failed exec is still the Python helper: reap it
                                    # without attributing its final RSS to the target.
                                    process.wait()
                                elif confirmation:
                                    raise RuntimeError("Invalid program exec confirmation")
                                break
                finally:
                    for descriptor in (gate_read, gate_write, exec_read, exec_write):
                        if descriptor is not None:
                            os.close(descriptor)
                started = time.monotonic()
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
    if len(sys.argv) >= 5 and sys.argv[1] == "--program":
        sys.exit(run_program(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:]))
    sys.exit(run(sys.argv[1]))
