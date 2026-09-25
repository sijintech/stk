"""Local process, OpenPBS/PBS Professional, and Slurm execution adapters."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
import errno
import getpass
import json
import os
import re
import shlex
import subprocess

from .common import alive, atomic_json, identity, instance_lock, now, read_json
from .models import layout

PROFILE_KEYS = frozenset({"queue", "account", "qos", "job_shell", "preamble", "submit_args"})
# Options STK sets itself or needs to find the job again. sbatch also accepts
# unambiguous prefixes of long options, so those are refused too. sbatch prints
# help/usage/version and exits 0 without submitting; PBS -h holds the job.
RESERVED_LONG_OPTIONS = ("--job-name", "--parsable", "--chdir", "--output", "--error", "--wrap",
                         "--array", "--test-only", "--wait", "--export", "--help", "--usage", "--version",
                         "--clusters", "--quiet")
RESERVED_SHORT_OPTIONS = frozenset("JDoeaWNIhV")  # Slurm -J -D -o -e -a -W -h -V; PBS -N -o -e -J -W -I -h
# Slurm -M runs the job on another cluster, which squeue/sacct/scancel would not query, and
# -Q/PBS -z print no job ID. PBS -M is a mail list, so these are checked per scheduler.
SCHEDULER_SHORT_OPTIONS = {"slurm": frozenset("MQ"), "pbs": frozenset("z")}


class SubmissionUnknown(RuntimeError):
    """A submission may have reached the scheduler; never blindly retry."""


class SubmissionFailed(RuntimeError):
    """Launch definitely created nothing; the task is terminal unless the cause is transient."""

    @property
    def transient(self):
        # Process, memory or descriptor exhaustion may clear; a retry cannot duplicate anything.
        return getattr(self.__cause__, "errno", None) in {errno.EAGAIN, errno.ENOMEM, errno.EMFILE, errno.ENFILE}


def validate_scheduler_profile(profile, kind=None):
    """Check the operator-only site profile, the "scheduler" object in config.json.

    kind ("slurm" or "pbs") selects that scheduler's own reserved options; None refuses both.
    """
    def invalid(detail):
        return ValueError("Invalid scheduler profile: " + detail)
    if not isinstance(profile, dict):
        raise invalid("expected an object")
    unknown = set(profile) - PROFILE_KEYS
    if unknown:
        raise invalid("unknown keys " + ", ".join(sorted(unknown)))
    for key in ("queue", "account", "qos"):
        if key in profile and (not isinstance(profile[key], str) or not re.fullmatch(r"[A-Za-z0-9_.@/-]+", profile[key])):
            raise invalid(f"invalid {key}")
    shell = profile.get("job_shell", "/bin/sh")
    if not isinstance(shell, str) or not shell.startswith("/") or re.search(r"[\n\r\x00]", shell):
        raise invalid("job_shell must be an absolute path")
    preamble = profile.get("preamble", [])
    if not isinstance(preamble, list) or any(not isinstance(line, str) or re.search(r"[\n\r\x00]", line) for line in preamble):
        raise invalid("preamble must be a list of single-line strings")
    # Directives before the first command are scheduler options, which submit_args checks.
    if any(line.lstrip().startswith(("#SBATCH", "#PBS")) for line in preamble):
        raise invalid("preamble must not contain scheduler directives; use submit_args")
    extra = profile.get("submit_args", [])
    if not isinstance(extra, list) or any(not isinstance(arg, str) or not re.fullmatch(r"-[^\x00]+", arg) for arg in extra):
        raise invalid("submit_args must be a list of options starting with '-'")
    short = RESERVED_SHORT_OPTIONS.union(*(v for k, v in SCHEDULER_SHORT_OPTIONS.items() if kind in (None, k)))
    for arg in extra:
        if arg.startswith("--"):
            name = arg.split("=", 1)[0]
            reserved = any(option.startswith(name) for option in RESERVED_LONG_OPTIONS)
        else:
            name = arg[:2]
            reserved = arg[1] in short
        if reserved:
            raise invalid(f"submit_args must not set {name}; STK sets or relies on it")
    return profile


def scheduler_profile(config, kind=None):
    profile = config.get("scheduler")
    try:
        return validate_scheduler_profile({} if profile is None else profile, kind)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from None


class ExecutionBackend(ABC):
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def submit(self, record, root):
        """Return durable backend handle; raise SubmissionUnknown if ambiguous."""

    @abstractmethod
    def query(self, record, root):
        """Return a state observation; unknown does not mean failed/succeeded."""

    @abstractmethod
    def cancel(self, record, root):
        """Request cancellation without claiming the program has already exited."""


class LocalBackend(ExecutionBackend):
    def __init__(self, config):
        super().__init__(config)
        self.children = {}

    def submit(self, record, root):
        try:
            log = open(root / "wrapper.log", "ab")
        except OSError as exc:
            raise SubmissionFailed(f"Task worker could not be started: {exc}") from exc
        with log:
            try:
                process = subprocess.Popen([self.config["python"], str(root / "worker.py"), str(root)],
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           start_new_session=os.name != "nt",
                                           creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
            except (OSError, ValueError) as exc:
                # Popen reaps a child whose exec failed, so nothing is left running.
                raise SubmissionFailed(f"Task worker could not be started: {exc}") from exc
        # A child exists from here on; later failures stay unknown for reconciliation.
        self.children[record["id"]] = process
        handle = identity(process.pid)
        return {"backend_id": str(process.pid), "process": handle}

    def reap(self):
        """Wait for exited workers; a finished task is not queried again, so query never polls them."""
        for task_id, child in list(self.children.items()):
            if child.poll() is not None:
                del self.children[task_id]

    def query(self, record, root):
        child = self.children.get(record["id"])
        if child is not None and child.poll() is not None:
            del self.children[record["id"]]
        handle = record.get("process") or read_json(root / "worker.json")
        if alive(handle):
            return {"state": "running", "backend_id": str(handle["pid"]), "process": handle, "reason": ""}
        if handle:
            if alive(read_json(root / 'program.json')):
                return {"state": "unknown", "reason": "Worker lost while the task program is still running; cancellation is available"}
            return {"state": "failed", "reason": "Worker exited without a completion record"}
        # No worker recorded itself: the launch failed or the supervisor stopped
        # before persisting the handle. Keep the original dispatch error.
        reason = record.get("reason")
        if record["id"] in self.children:
            # Our own worker is still starting and will record itself.
            return {"state": "unknown", "reason": reason or "Launch outcome unknown; no automatic resubmission"}
        return (self.tombstone(root, "failed", f"No task worker was started ({reason})" if reason else "No task worker was started")
                or {"state": "unknown", "reason": reason or "Launch outcome unknown; no automatic resubmission"})

    def cancel(self, record, root):
        (root / "cancel").touch()
        handle = record.get('process') or read_json(root / 'worker.json')
        if not alive(handle):
            program = read_json(root / 'program.json')
            if alive(program):
                import psutil
                from .worker import terminate_tree
                terminate_tree(psutil.Process(program['pid']), expected_created=program['create_time'])
                atomic_json(root / 'finished.json', {'state': 'cancelled', 'exit_code': None,
                            'reason': 'Program cancelled after worker loss', 'finished_at': now()})
            elif handle is None and program is None:
                self.tombstone(root, 'cancelled', 'Cancelled; no task worker was started')
        return {}

    @staticmethod
    def tombstone(root, state, reason):
        """Finish a task whose worker never started; None once one has started.

        This holds the worker's own lock, so a worker that starts later finds
        finished.json and exits without running the program.
        """
        try:
            with instance_lock(root / "worker.lock"):
                if (root / "finished.json").exists() or (root / "worker.json").exists():
                    return None
                result = {"state": state, "exit_code": None, "reason": reason, "finished_at": now()}
                atomic_json(root / "finished.json", result)
                return result
        except BlockingIOError:
            return None  # a starting worker holds the lock and will see the cancel file
        except FileNotFoundError:
            # Without the run directory there is no worker.py, so nothing can start.
            return {"state": state, "exit_code": None, "reason": reason, "finished_at": now()}


class SchedulerBackend(ExecutionBackend):
    def command(self, argv):
        env = os.environ.copy()
        env.update(LC_ALL="C")
        return subprocess.run(argv, capture_output=True, text=True, timeout=20, env=env)

    def job_name(self, record):
        return "s" + record["id"][:14] if record["spec"]["backend"] == "pbs" else "stk-" + record["id"]

    def script(self, record, root):
        profile = scheduler_profile(self.config, record["spec"]["backend"])
        path = root / "job.sh"
        command = [self.config["python"], str(root / "worker.py"), str(root)]
        lines = ["#!" + profile.get("job_shell", "/bin/sh"), *profile.get("preamble", []), "exec " + shlex.join(command)]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def submit_command(self, argv):
        try:
            result = self.command(argv)
        except subprocess.TimeoutExpired as exc:
            raise SubmissionUnknown("Scheduler submission timed out; reconciliation required") from exc
        if result.returncode:
            message = result.stderr.strip() or "Scheduler submission command failed"
            # Connection loss or a killed client can happen after acceptance.
            # Only explicit validation rejections are known to be unsubmitted.
            if result.returncode > 0 and re.search(r"invalid (partition|account|qos|resource)|unknown queue|illegal .*value|requested node configuration is not available|violates accounting/qos policy", message, re.I):
                raise RuntimeError(message)
            raise SubmissionUnknown(message + "; reconciliation required before retrying")
        return result.stdout.strip()

    def cancel(self, record, root):
        (root / "cancel").touch()
        job_id = record.get("backend_id")
        if not job_id:
            return {}
        result = self.command(["qdel" if record["spec"]["backend"] == "pbs" else "scancel", job_id])
        if result.returncode:
            return {"reason": "Cancellation pending: " + result.stderr.strip()}
        return {"cancellation_sent": True}

    @staticmethod
    def terminal(raw, code=None):
        raw = raw.split()[0].rstrip("+")
        if raw in {"COMPLETED", "F", "C"}:
            if code is None:
                return "unknown"
            return "succeeded" if code == 0 else "failed"
        if raw in {"CANCELLED", "X"}:
            return "cancelled"
        if raw in {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL", "PREEMPTED", "DEADLINE", "REVOKED"}:
            return "failed"
        if raw in {"RUNNING", "COMPLETING", "R", "E"}:
            return "running"
        if raw in {"PENDING", "CONFIGURING", "SUSPENDED", "REQUEUED", "REQUEUE_HOLD", "RESIZING", "Q", "H", "W", "S", "T", "B", "U"}:
            return "queued"
        return "unknown"


class SlurmBackend(SchedulerBackend):
    def submit(self, record, root):
        profile = scheduler_profile(self.config, "slurm")
        res = record["spec"]["resources"]
        shape = layout(res)
        if shape["mpi"]:
            tasks = [f"--nodes={shape['nodes']}", f"--ntasks={shape['ranks']}",
                     f"--ntasks-per-node={shape['ranks_per_node']}", f"--cpus-per-task={shape['threads_per_rank']}"]
        else:
            tasks = ['--ntasks-per-node=1', f"--cpus-per-task={res.get('cpus', 1)}", f"--nodes={res.get('nodes', 1)}"]
        args = ["sbatch", "--parsable", "--job-name=" + self.job_name(record), *tasks,
                "--chdir=" + str(root / "work"), "--output=" + str(root / "scheduler.out"),
                "--error=" + str(root / "scheduler.err")]
        for key, flag in [("memory_mb", "--mem"), ("queue", "--partition"),
                          ("account", "--account"), ("gpus", "--gpus-per-node")]:
            value = res.get(key) or profile.get(key)
            if value:
                args.append(f"{flag}={value}")
        if profile.get("qos"):
            args.append("--qos=" + profile["qos"])
        if "walltime_seconds" in res:
            seconds = res["walltime_seconds"]
            args.append(f"--time={seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}")
        output = self.submit_command(args + profile.get("submit_args", []) + [str(self.script(record, root))])
        if not re.fullmatch(r"\d+(;[\w.-]+)?", output):
            raise SubmissionUnknown("Unrecognized sbatch response; reconciliation required")
        return {"backend_id": output.split(";")[0]}

    def query(self, record, root):
        job_id = record.get("backend_id")
        select = ["--jobs=" + job_id] if job_id else ["--name=" + self.job_name(record), "--user=" + getpass.getuser()]
        result = self.command(["squeue", "--noheader", "--format=%i|%T|%j"] + select)
        rows = [line.strip().split("|") for line in result.stdout.splitlines() if line.strip()]
        rows = [r for r in rows if len(r) == 3 and (r[0] == job_id if job_id else r[2] == self.job_name(record))]
        queue_empty = result.returncode == 0 and not rows
        if result.returncode == 0 and len(rows) == 1:
            return {"backend_id": rows[0][0], "state": self.terminal(rows[0][1]), "raw_state": rows[0][1], "reason": ""}
        select = ["--jobs=" + job_id] if job_id else ["--name=" + self.job_name(record), "--user=" + getpass.getuser()]
        # Include the prior UTC day to cover the scheduler's local calendar date.
        start_date = (datetime.fromisoformat(record['created_at']) - timedelta(days=1)).date().isoformat()
        result = self.command(["sacct", "--noheader", "--parsable2", "--format=JobIDRaw,State,ExitCode,JobName",
                               "--starttime=" + start_date] + select)
        rows = [line.strip().rstrip("|").split("|") for line in result.stdout.splitlines() if line.strip()]
        rows = [r for r in rows if len(r) == 4 and re.fullmatch(r"\d+", r[0])
                and (r[0] == job_id if job_id else r[3] == self.job_name(record))]
        if result.returncode == 0 and len(rows) == 1:
            row = rows[0]
            code = None
            if re.fullmatch(r"\d+:\d+", row[2]):
                exit_status, signum = map(int, row[2].split(":"))
                code = exit_status or (128 + signum if signum else 0)
            return {"backend_id": row[0], "state": self.terminal(row[1], code), "exit_code": code,
                    "raw_state": row[1], "reason": row[1]}
        if queue_empty and result.returncode == 0 and not rows and record.get('cancellation_sent'):
            return {"state": "cancelled", "reason": "Cancellation acknowledged; job no longer present in queue/accounting"}
        return {"state": "unknown", "reason": "No unambiguous scheduler record; awaiting accounting/reconciliation"}


class PBSBackend(SchedulerBackend):
    def submit(self, record, root):
        profile = scheduler_profile(self.config, "pbs")
        res = record["spec"]["resources"]
        shape = layout(res)
        if shape["mpi"]:
            # ompthreads also stops PBS exporting OMP_NUM_THREADS=ncpus to every rank.
            resource = (f"select={shape['nodes']}:ncpus={shape['cpus_per_node']}"
                        f":mpiprocs={shape['ranks_per_node']}:ompthreads={shape['threads_per_rank']}")
        else:
            resource = f"select={res.get('nodes', 1)}:ncpus={res.get('cpus', 1)}"
        if "memory_mb" in res:
            resource += f":mem={res['memory_mb']}mb"
        if res.get("gpus"):
            resource += f":ngpus={res['gpus']}"
        args = ["qsub", "-N", self.job_name(record), "-l", resource,
                "-o", str(root / "scheduler.out"), "-e", str(root / "scheduler.err")]
        for key, flag in [("queue", "-q"), ("account", "-A")]:
            value = res.get(key) or profile.get(key)
            if value:
                args.extend([flag, value])
        if "walltime_seconds" in res:
            seconds = res["walltime_seconds"]
            args.extend(["-l", f"walltime={seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"])
        output = self.submit_command(args + profile.get("submit_args", []) + [str(self.script(record, root))])
        if not re.fullmatch(r"\d+(\.[\w.-]+)?", output):
            raise SubmissionUnknown("Unrecognized qsub response; reconciliation required")
        return {"backend_id": output}

    def query(self, record, root):
        job_id = record.get("backend_id")
        args = ["qstat", "-x", "-f", "-F", "json"] + ([job_id] if job_id else ["-u", getpass.getuser()])
        result = self.command(args)
        if result.returncode:
            # History may be disabled, but active records may still be available.
            result = self.command([a for a in args if a != "-x"])
        if result.returncode == 0:
            jobs = json.loads(result.stdout).get("Jobs", {})
            rows = [(key, val) for key, val in jobs.items() if key == job_id or
                    (job_id is None and val.get("Job_Name") == self.job_name(record))]
            if len(rows) == 1:
                key, job = rows[0]
                raw = job.get("job_state", "?")
                code = int(job["Exit_status"]) if "Exit_status" in job else None
                return {"backend_id": key, "state": self.terminal(raw, code), "exit_code": code,
                        "raw_state": raw, "reason": job.get("comment", "")}
        if record.get('cancellation_sent') and 'Unknown Job Id' in (result.stdout + result.stderr):
            return {"state": "cancelled", "reason": "Cancellation acknowledged; PBS reports the job was removed"}
        return {"state": "unknown", "reason": "PBS job/history unavailable; awaiting reconciliation"}


def backends(config):
    return {"local": LocalBackend(config), "pbs": PBSBackend(config), "slurm": SlurmBackend(config)}
