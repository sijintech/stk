"""Bounded deployment checks without starting services or submitting tasks."""

from pathlib import Path
import json
import math
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time

import psutil

from . import API_VERSION
from .client import RuntimeClient
from .common import alive, atomic_json, instance_lock, load_config, now, read_json
from .models import BACKENDS


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


def validate_config(config, state):
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


def diagnose_server(state_dir, backend="local", science=False, timeout=5):
    if backend not in BACKENDS:
        raise ValueError("backend must be local, pbs or slurm")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
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
        validate_config(config, state)
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
                else "Required scheduler commands are on PATH; scheduler connectivity has not been tested.",
            )
        )
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
