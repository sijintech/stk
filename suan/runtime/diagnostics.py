"""Bounded deployment checks without starting services or submitting tasks."""

from pathlib import Path
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time

import psutil

from . import API_VERSION
from .backends import validate_scheduler_profile
from .client import RuntimeClient
from .common import alive, atomic_json, instance_lock, load_config, now, read_json
from .models import BACKENDS

SCHEDULER_NAME = re.compile(r"[A-Za-z0-9_.@/-]+")


def check(check_id, status, message, **details):
    return {"id": check_id, "status": status, "message": message, **details}


def connection_checks(client):
    """Check the authenticated API and its supervisor, including SSH endpoints."""
    try:
        health = client.health()
        if (
            not isinstance(health, dict)
            or type(health.get("api_version")) is not int
            or health["api_version"] != API_VERSION
            or health.get("status") != "ok"
        ):
            return [
                check(
                    "api",
                    "fail",
                    "Endpoint did not return a compatible healthy runtime API.",
                )
            ]
    except (OSError, RuntimeError, ValueError) as exc:
        message = (
            "Runtime authentication failed; check the saved token."
            if getattr(exc, "status", None) == 401
            else (
                "Cannot reach the runtime API; check the service, endpoint and SSH tunnel."
            )
        )
        return [check("api", "fail", message)]
    return [
        check(
            "api",
            "pass",
            "Authenticated runtime API is reachable.",
            api_version=API_VERSION,
        ),
        check(
            "supervisor",
            "pass" if health.get("supervisor_running") is True else "fail",
            "Supervisor is running."
            if health.get("supervisor_running") is True
            else "Supervisor is stopped; start it on the server to dispatch and reconcile tasks.",
        ),
    ]


def validate_config(config, state, kind=None):
    if not isinstance(config, dict):
        raise ValueError("config.json must contain an object")
    for key in ("state_dir", "workspace_root", "python"):
        value = config.get(key)
        if (
            not isinstance(value, str)
            or not value
            or "\x00" in value
            or not Path(value).is_absolute()
        ):
            raise ValueError(f"{key} must be an absolute path")
    if Path(config["state_dir"]).resolve() != state:
        raise ValueError("state_dir must match the directory containing config.json")
    if not isinstance(config.get("token"), str) or not config["token"].strip():
        raise ValueError("A nonempty runtime token is required")
    for key, minimum, maximum in (("port", 0, 65535), ("concurrency", 1, None)):
        value = config.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            raise ValueError(f"Invalid {key}")
    for key in ("poll_interval", "scheduler_interval"):
        value = config.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or (key == "poll_interval" and value == 0)
        ):
            raise ValueError(f"Invalid {key}")
    profile = config.get("scheduler")
    validate_scheduler_profile({} if profile is None else profile, kind)


def directory_check(check_id, path):
    try:
        # Exercise the same private atomic files and locks as the runtime. All
        # probe files are confined to a disposable directory and cleaned up.
        with tempfile.TemporaryDirectory(prefix=".stk-doctor-", dir=path) as probe:
            root = Path(probe)
            with instance_lock(root / "probe.lock"):
                atomic_json(root / "probe.json", {"probe": True})
                if read_json(root / "probe.json") != {"probe": True}:
                    raise OSError("Probe contents changed")
        return check(
            check_id,
            "pass",
            "Directory supports temporary writes, atomic replacement and locks.",
            path=str(path),
        )
    except OSError:
        return check(
            check_id,
            "fail",
            "Directory is missing or cannot write, replace and lock files; check its permissions and mount.",
            path=str(path),
        )


def state_filesystem_check(state):
    try:
        mounts = [
            p
            for p in psutil.disk_partitions(all=True)
            if state == Path(p.mountpoint) or Path(p.mountpoint) in state.parents
        ]
    except (OSError, psutil.Error):
        mounts = []
    if not mounts:
        return check(
            "state_filesystem",
            "warn",
            "Filesystem type could not be detected; verify SQLite state is on local storage.",
        )
    mount = max(mounts, key=lambda p: len(Path(p.mountpoint).parts))
    filesystem = mount.fstype.lower()
    network = filesystem in {
        "nfs",
        "nfs4",
        "cifs",
        "smbfs",
        "smb3",
        "sshfs",
        "fuse.sshfs",
        "lustre",
        "gpfs",
        "ceph",
        "fuse.ceph",
        "glusterfs",
        "fuse.glusterfs",
        "afs",
        "9p",
    }
    return check(
        "state_filesystem",
        "fail" if network else "pass",
        "SQLite state is on network storage; move state-dir to a local disk."
        if network
        else "No known network filesystem detected for SQLite state.",
        filesystem=mount.fstype,
    )


def database_check(state, timeout):
    path = state / "runtime.sqlite3"
    if not path.exists():
        return check(
            "database",
            "warn",
            "Runtime database does not exist yet; start the runtime to create it.",
        )
    try:
        connection = sqlite3.connect(
            path.as_uri() + "?mode=ro", uri=True, timeout=timeout
        )
        try:
            deadline = time.monotonic() + timeout
            connection.set_progress_handler(
                lambda: int(time.monotonic() >= deadline), 1000
            )
            result = connection.execute("PRAGMA quick_check").fetchall()
            # Verify the metadata tables exist without creating or migrating them.
            connection.execute("SELECT id, data FROM workspaces LIMIT 0")
            connection.execute(
                "SELECT id, request_key, spec_hash, data FROM tasks LIMIT 0"
            )
        finally:
            connection.close()
        if result != [("ok",)]:
            raise sqlite3.DatabaseError("quick_check failed")
        return check(
            "database", "pass", "SQLite quick_check and runtime metadata tables passed."
        )
    except sqlite3.Error:
        return check(
            "database",
            "fail",
            "SQLite check failed or timed out; inspect database access, integrity and runtime schema.",
        )


def python_check(config, science, timeout):
    script = (
        "import json, sys, psutil\n"
        "if not (3, 10) <= sys.version_info[:2] < (3, 15):\n"
        "    raise RuntimeError('Unsupported Python')\n"
        "result = {'python': sys.version.split()[0], 'psutil': psutil.__version__}\n"
    )
    if science:
        script += (
            "import numpy, matplotlib, toolkits.sviz.field; "
            "result.update(numpy=numpy.__version__, matplotlib=matplotlib.__version__); "
        )
    script += "print(json.dumps(result))"
    try:
        result = subprocess.run(
            [config["python"], "-c", script],
            cwd=config["workspace_root"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode:
            return check(
                "worker_python",
                "fail",
                "Configured Python cannot import required worker dependencies; install psutil"
                + (" and STK science extras." if science else "."),
                exit_code=result.returncode,
            )
        versions = json.loads(result.stdout)
        if not isinstance(versions, dict):
            raise ValueError("Unexpected interpreter output")
        return check(
            "worker_python",
            "pass",
            "Configured worker interpreter and dependencies are usable on this host.",
            versions=versions,
        )
    except subprocess.TimeoutExpired:
        return check(
            "worker_python", "fail", "Configured worker interpreter check timed out."
        )
    except (OSError, ValueError):
        return check(
            "worker_python",
            "fail",
            "Cannot run the configured worker interpreter from workspace-root; check its path and environment.",
        )


def probe(argv, timeout):
    env = os.environ.copy()
    env.update(LC_ALL="C")
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        # Site tools and preambles may print non-UTF-8 text, such as GBK.
        errors="replace",
        timeout=timeout,
        env=env,
    )


def excerpt(result):
    return result.stderr.strip()[:500] or f"exit code {result.returncode}"


def partition_check(partition, result):
    if result.returncode:
        return check("slurm_partition", "fail", "sinfo failed: " + excerpt(result))
    rows = [line.strip().split("|") for line in result.stdout.splitlines()]
    # sinfo marks the default partition with a trailing '*'.
    rows = [r for r in rows if len(r) == 6 and r[0].rstrip("*") == partition]
    up = [r for r in rows if r[1] == "up"]
    if not up:
        return check(
            "slurm_partition",
            "fail",
            f"Partition {partition} is {rows[0][1]}, not up."
            if rows
            else f"Partition {partition} was not found by sinfo.",
        )

    # Nodes of different shapes print separate rows. Report the smallest, so a
    # layout that fits these values fits any node of the partition.
    def smallest(column):
        values = [r[column].rstrip("+") for r in up]
        return min((int(v) for v in values if v.isdigit()), default=None)

    return check(
        "slurm_partition",
        "pass",
        f"Partition {partition} is up.",
        time_limit=up[0][2],
        nodes=sum(int(r[3]) for r in up if r[3].isdigit()),
        cpus_per_node=smallest(4),
        memory_mb=smallest(5),
    )


def slurm_checks(site, probe_preamble, timeout):
    """Probe a Slurm site without submitting: sbatch only runs with --version or
    --test-only, and the preamble runs on this host only when requested."""
    checks = []

    def run(check_id, argv):
        try:
            return probe(argv, timeout)
        except subprocess.TimeoutExpired:
            message = f"{check_id} timed out after {timeout:g} s."
        except OSError:
            message = f"{check_id} unavailable: cannot run {argv[0]}."
        checks.append(check(check_id, "fail", message))
        return None

    result = run("slurm_version", ["sbatch", "--version"])
    if result is not None:
        version = result.stdout.strip()
        checks.append(
            check("slurm_version", "pass", "Slurm client: " + version, version=version)
            if result.returncode == 0 and version
            else check(
                "slurm_version", "fail", "sbatch --version failed: " + excerpt(result)
            )
        )

    partition = site["queue"]
    if not partition:
        checks.append(
            check(
                "slurm_partition",
                "warn",
                "No partition: pass --partition or set scheduler.queue",
            )
        )
    else:
        result = run(
            "slurm_partition",
            ["sinfo", "-h", "-p", partition, "-o", "%P|%a|%l|%D|%c|%m"],
        )
        if result is not None:
            checks.append(partition_check(partition, result))

    argv = ["sbatch", "--test-only", "--job-name=stk-doctor", "--nodes=1"]
    argv += ["--ntasks=1", "--time=1"]
    for key, flag in (
        ("queue", "--partition"),
        ("account", "--account"),
        ("qos", "--qos"),
    ):
        if site[key]:
            argv.append(f"{flag}={site[key]}")
    result = run("slurm_submit_test", argv + site["submit_args"] + ["--wrap=true"])
    if result is not None:
        first_line = (result.stderr.strip().splitlines() or [""])[0]
        checks.append(
            check(
                "slurm_submit_test",
                "pass",
                f"sbatch --test-only accepted the request; nothing was submitted. {first_line}".rstrip(),
            )
            if result.returncode == 0
            else check("slurm_submit_test", "fail", excerpt(result))
        )

    result = run(
        "slurm_accounting",
        ["sacct", "-X", "-n", "-P", "-S", "now-1days", "-o", "JobIDRaw"],
    )
    if result is not None:
        checks.append(
            check("slurm_accounting", "pass", "Slurm accounting history is available.")
            if result.returncode == 0
            else check(
                "slurm_accounting",
                "warn",
                "Slurm accounting history unavailable; reconciliation after supervisor restarts is degraded.",
            )
        )

    shell, preamble = site["job_shell"], site["preamble"]
    if not preamble:
        return checks
    # job_shell is a '#!' line: the kernel passes everything after the interpreter as one argument.
    interpreter, *argument = shell.split(None, 1)
    name = Path(argument[0] if argument and Path(interpreter).name == "env" else interpreter).name
    if name in {"sh", "dash"} and any(
        line.lstrip().startswith("source ") for line in preamble
    ):
        checks.append(
            check(
                "scheduler_preamble",
                "warn",
                f"Preamble uses 'source', which {shell} may not support; use '.' or set scheduler.job_shell to /bin/bash.",
            )
        )
    elif not probe_preamble:
        checks.append(
            check(
                "scheduler_preamble",
                "warn",
                "Preamble was not run; pass --probe-preamble to dry-run it on this host.",
            )
        )
    else:
        result = run(
            "scheduler_preamble",
            [interpreter, *argument, "-c", "set -e\n" + "\n".join(preamble)],
        )
        if result is not None:
            checks.append(
                check(
                    "scheduler_preamble",
                    "pass",
                    f"Preamble ran under {shell} on this host; compute nodes may differ.",
                )
                if result.returncode == 0
                else check(
                    "scheduler_preamble",
                    "fail",
                    f"Preamble failed under {shell}: " + excerpt(result),
                )
            )
    return checks


def diagnose_server(
    state_dir,
    backend="local",
    science=False,
    timeout=5,
    *,
    partition=None,
    account=None,
    qos=None,
    probe_preamble=False,
):
    if backend not in BACKENDS:
        raise ValueError("backend must be local, pbs or slurm")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    for key, value in (("partition", partition), ("account", account), ("qos", qos)):
        if value is not None and not (
            isinstance(value, str) and SCHEDULER_NAME.fullmatch(value)
        ):
            raise ValueError(f"{key} must match {SCHEDULER_NAME.pattern}")
    state = Path(state_dir).expanduser().resolve()
    report = {
        "schema_version": 1,
        "checked_at": now(),
        "scope": "server-host",
        "backend": backend,
        "state_dir": str(state),
        "checks": [],
    }
    checks = report["checks"]
    try:
        config = load_config(state)
        validate_config(config, state, None if backend == "local" else backend)
    except (ValueError, OSError) as exc:
        checks.append(check("config", "fail", str(exc)))
        report["ok"] = False
        return report
    checks.append(check("config", "pass", "Runtime configuration is valid."))
    checks.append(directory_check("state_directory", state))
    checks.append(state_filesystem_check(state))
    checks.append(
        directory_check("workspace_directory", Path(config["workspace_root"]))
    )
    checks.append(database_check(state, timeout))
    checks.append(python_check(config, science, timeout))
    if backend != "local":
        profile = config.get("scheduler") or {}
        # Command-line options override the profile defaults, as task resources do.
        site = {
            "queue": partition or profile.get("queue"),
            "account": account or profile.get("account"),
            "qos": qos or profile.get("qos"),
            "job_shell": profile.get("job_shell", "/bin/sh"),
            "preamble": profile.get("preamble", []),
            "submit_args": profile.get("submit_args", []),
        }
        checks.append(
            check(
                "scheduler_profile",
                "pass",
                "Scheduler site profile is valid."
                if profile
                else "No scheduler site profile; the scheduler's defaults apply.",
                **site,
            )
        )
        commands = (
            ("qsub", "qstat", "qdel")
            if backend == "pbs"
            else ("sbatch", "squeue", "sacct", "scancel")
        )
        missing = [name for name in commands if shutil.which(name) is None]
        checks.append(
            check(
                "scheduler_commands",
                "fail" if missing or os.name == "nt" else "pass",
                "PBS/Slurm require a POSIX submit host."
                if os.name == "nt"
                else "Missing scheduler commands: " + ", ".join(missing)
                if missing
                # The Slurm probes below test connectivity.
                else "Required scheduler commands are on PATH."
                if backend == "slurm"
                else "Required scheduler commands are on PATH; scheduler connectivity has not been tested.",
            )
        )
        if backend == "slurm" and not missing and os.name != "nt":
            checks.extend(slurm_checks(site, probe_preamble, timeout))
        checks.append(
            check(
                "compute_nodes",
                "warn",
                "Run the acceptance demo through the target queue to verify compute-node Python, shared files and scheduler history.",
            )
        )
    try:
        api = read_json(state / "api.pid")
        port = api["port"] if alive(api) else config["port"]
        checks.extend(
            connection_checks(
                RuntimeClient(
                    f"http://127.0.0.1:{port}", config["token"], timeout=timeout
                )
            )
        )
    except (ValueError, OSError, KeyError, TypeError, psutil.Error):
        checks.append(
            check(
                "api",
                "fail",
                "Cannot read API process metadata; inspect api.pid and restart the API if needed.",
            )
        )
    report["ok"] = not any(item["status"] == "fail" for item in checks)

    # Reports are suitable for sharing; never serialize configuration or tokens.
    def redact(value):
        if isinstance(value, str):
            return value.replace(config["token"], "[redacted]")
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        return value

    return redact(report)
