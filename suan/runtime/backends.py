"""Local process, OpenPBS/PBS Professional, and Slurm execution adapters."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
import getpass
import json
import os
import re
import shlex
import subprocess

from .common import alive, atomic_json, identity, now, read_json


class SubmissionUnknown(RuntimeError):
    """A submission may have reached the scheduler; never blindly retry."""


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
        with open(root / "wrapper.log", "ab") as log:
            process = subprocess.Popen([self.config["python"], str(root / "worker.py"), str(root)],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=os.name != "nt",
                                       creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
        self.children[record["id"]] = process
        handle = identity(process.pid)
        return {"backend_id": str(process.pid), "process": handle}

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
        return {"state": "unknown", "reason": "Launch outcome unknown; no automatic resubmission"}

    def cancel(self, record, root):
        (root / "cancel").touch()
        if not alive(record.get('process') or read_json(root / 'worker.json')):
            program = read_json(root / 'program.json')
            if alive(program):
                import psutil
                from .worker import terminate_tree
                terminate_tree(psutil.Process(program['pid']), expected_created=program['create_time'])
                atomic_json(root / 'finished.json', {'state': 'cancelled', 'exit_code': None,
                            'reason': 'Program cancelled after worker loss', 'finished_at': now()})
        return {}


class SchedulerBackend(ExecutionBackend):
    def command(self, argv):
        env = os.environ.copy()
        env.update(LC_ALL="C")
        return subprocess.run(argv, capture_output=True, text=True, timeout=20, env=env)

    def job_name(self, record):
        return "s" + record["id"][:14] if record["spec"]["backend"] == "pbs" else "stk-" + record["id"]

    def script(self, record, root):
        path = root / "job.sh"
        command = [self.config["python"], str(root / "worker.py"), str(root)]
        path.write_text("#!/bin/sh\nexec " + shlex.join(command) + "\n", encoding="utf-8")
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
            if result.returncode > 0 and re.search(r"invalid (partition|account|qos|resource)|unknown queue|illegal .*value|requested node configuration is not available", message, re.I):
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
        res = record["spec"]["resources"]
        args = ["sbatch", "--parsable", "--job-name=" + self.job_name(record),
                '--ntasks-per-node=1', f"--cpus-per-task={res.get('cpus', 1)}", f"--nodes={res.get('nodes', 1)}",
                "--chdir=" + str(root / "work"), "--output=" + str(root / "scheduler.out"),
                "--error=" + str(root / "scheduler.err")]
        for key, flag in [("memory_mb", "--mem"), ("queue", "--partition"),
                          ("account", "--account"), ("gpus", "--gpus-per-node")]:
            if res.get(key):
                args.append(f"{flag}={res[key]}")
        if "walltime_seconds" in res:
            seconds = res["walltime_seconds"]
            args.append(f"--time={seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}")
        output = self.submit_command(args + [str(self.script(record, root))])
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
        res = record["spec"]["resources"]
        resource = f"select={res.get('nodes', 1)}:ncpus={res.get('cpus', 1)}"
        if "memory_mb" in res:
            resource += f":mem={res['memory_mb']}mb"
        if res.get("gpus"):
            resource += f":ngpus={res['gpus']}"
        args = ["qsub", "-N", self.job_name(record), "-l", resource,
                "-o", str(root / "scheduler.out"), "-e", str(root / "scheduler.err")]
        for key, flag in [("queue", "-q"), ("account", "-A")]:
            if key in res:
                args.extend([flag, res[key]])
        if "walltime_seconds" in res:
            seconds = res["walltime_seconds"]
            args.extend(["-l", f"walltime={seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"])
        output = self.submit_command(args + [str(self.script(record, root))])
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
