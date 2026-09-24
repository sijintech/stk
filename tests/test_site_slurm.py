"""Slurm site preparation: the doctor validates the site profile and probes the
scheduler without ever submitting a job."""

import json
import os
import shlex
import subprocess
import sys

from click.testing import CliRunner
import pytest

from suan.runtime import diagnostics
from suan.runtime.backends import scheduler_profile
from suan.runtime.cli import server
from suan.runtime.common import atomic_json, init_config

pytestmark = pytest.mark.server

# Fake Slurm client: logs its argv and answers from STK_FAKE_SLURM, keyed by
# command name ("sbatch --version" for the version query). stderr is written in
# the reply's encoding, UTF-8 by default.
FAKE = """#!{python}
import json, os, sys
argv = [os.path.basename(sys.argv[0])] + sys.argv[1:]
with open(os.environ["STK_FAKE_SLURM_LOG"], "a") as log:
    log.write(json.dumps(argv) + "\\n")
key = "sbatch --version" if argv == ["sbatch", "--version"] else argv[0]
reply = json.loads(os.environ["STK_FAKE_SLURM"]).get(key, {{}})
sys.stdout.write(reply.get("stdout", ""))
sys.stderr.buffer.write(reply.get("stderr", "").encode(reply.get("encoding", "utf-8")))
sys.exit(reply.get("rc", 0))
"""

REPLIES = {
    "sbatch --version": {"stdout": "slurm 23.02.7\n"},
    # The default partition carries sinfo's '*'; two node shapes give two rows.
    "sinfo": {"stdout": "p*|up|2-00:00:00|8|64|256000\np*|up|2-00:00:00|2|32|128000\n"},
    "sbatch": {
        "stderr": "sbatch: Job 99 to start at 2026-09-24T10:00:00 using 1 processors on nodes c1 in partition p\n"
    },
    "sacct": {"stdout": "12345\n"},
}


@pytest.fixture
def site(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("sbatch", "sinfo", "sacct", "squeue", "scancel"):
        path = bin_dir / name
        path.write_text(FAKE.format(python=sys.executable), encoding="utf-8")
        path.chmod(0o755)
    log = tmp_path / "slurm.log"
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("STK_FAKE_SLURM_LOG", str(log))
    monkeypatch.setenv("STK_FAKE_SLURM", json.dumps(REPLIES))
    monkeypatch.setattr(
        diagnostics.RuntimeClient,
        "health",
        lambda _: {"api_version": 1, "status": "ok", "supervisor_running": True},
    )
    state = tmp_path / "state"
    init_config(state)
    return state, log


def configure(state, profile):
    config = json.loads((state / "config.json").read_text(encoding="utf-8"))
    config["scheduler"] = profile
    atomic_json(state / "config.json", config)
    return config


def reply(monkeypatch, **replies):
    monkeypatch.setenv("STK_FAKE_SLURM", json.dumps({**REPLIES, **replies}))


def logged(log):
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def by_id(report):
    return {item["id"]: item for item in report["checks"]}


@pytest.mark.parametrize(
    "profile",
    [
        ["--exclusive"],
        {"preamble": "module load intel"},
        {"preamble": ["module load intel\nsbatch job.sh"]},
        {"job_shell": "bin/bash"},
        {"submit_args": ["exclusive"]},
        {"submit_args": "--exclusive"},
        {"partition": "p"},
        {"queue": "p q"},
        {"account": 7},
        # Options STK sets itself or relies on to find and reconcile jobs.
        *(
            {"submit_args": [arg]}
            for arg in (
                "--job-name=x",
                "-Jx",
                "--parsable",
                "--chdir=/tmp",
                "-D/tmp",
                "--output=o",
                "-o",
                "--error",
                "-ee",
                "--wrap=true",
                "--array=1-2",
                "-a1",
                "--test-only",
                "--wait",
                "-W",
                "--export=NONE",
                "-N",
                "-Nname",
                "-I",
                "-Wblock=true",
                # sbatch accepts unambiguous prefixes of long options.
                "--test",
                "--outp=x",
                "--job=x",
                "--",
                "-",
                # These make sbatch exit 0 without submitting; PBS -h holds.
                "--help",
                "-h",
                "--usage",
                "-V",
                "--version",
            )
        ),
    ],
)
def test_scheduler_profile_is_validated_in_doctor(site, profile):
    state, log = site
    configure(state, profile)
    report = diagnostics.diagnose_server(state, "slurm")
    assert not report["ok"]
    assert [item["id"] for item in report["checks"]] == ["config"]
    assert report["checks"][0]["status"] == "fail"
    assert report["checks"][0]["message"].startswith("Invalid scheduler profile: ")
    # One validator: the doctor reports exactly what would fail a submitted task.
    with pytest.raises(RuntimeError) as raised:
        scheduler_profile({"scheduler": profile})
    assert report["checks"][0]["message"] == str(raised.value)
    assert logged(log) == []


def test_valid_scheduler_profile_is_reported_for_schedulers(site):
    state, _ = site
    profile = {
        "queue": "p",
        "account": "proj@site",
        "qos": "normal",
        "job_shell": "/bin/bash",
        "preamble": ["module load intel/2021", "export I_MPI_FABRICS=shm:ofi"],
        "submit_args": ["--exclusive", "--constraint=amd", "--wait-all-nodes=1"],
    }
    config = configure(state, profile)
    local = diagnostics.diagnose_server(state)
    assert local["checks"][0]["status"] == "pass"
    assert "scheduler_profile" not in by_id(local)
    for backend in ("pbs", "slurm"):
        checks = by_id(diagnostics.diagnose_server(state, backend))
        assert checks["config"]["status"] == "pass"
        details = checks["scheduler_profile"]
        assert details["status"] == "pass"
        assert {key: details[key] for key in profile} == profile
    assert "slurm_version" not in by_id(diagnostics.diagnose_server(state, "pbs"))
    del config["scheduler"]
    atomic_json(state / "config.json", config)
    details = by_id(diagnostics.diagnose_server(state, "pbs", account="a"))[
        "scheduler_profile"
    ]
    assert details["status"] == "pass"
    assert (details["queue"], details["account"], details["job_shell"]) == (
        None,
        "a",
        "/bin/sh",
    )


def test_slurm_site_probes_never_submit_jobs(site):
    state, log = site
    config = configure(
        state,
        {
            "queue": "default",
            "account": "a",
            "qos": "q",
            "submit_args": ["--exclusive"],
        },
    )
    report = diagnostics.diagnose_server(state, "slurm", partition="p")
    checks = by_id(report)
    assert report["ok"], report
    for check_id in (
        "scheduler_profile",
        "scheduler_commands",
        "slurm_version",
        "slurm_partition",
        "slurm_submit_test",
        "slurm_accounting",
    ):
        assert checks[check_id]["status"] == "pass", checks[check_id]
    assert checks["scheduler_profile"]["queue"] == "p"
    assert checks["scheduler_commands"]["message"] == (
        "Required scheduler commands are on PATH."
    )
    assert checks["slurm_version"]["version"] == "slurm 23.02.7"
    partition = checks["slurm_partition"]
    assert (partition["time_limit"], partition["nodes"]) == ("2-00:00:00", 10)
    assert (partition["cpus_per_node"], partition["memory_mb"]) == (32, 128000)
    assert "Job 99 to start" in checks["slurm_submit_test"]["message"]
    assert "scheduler_preamble" not in checks
    assert checks["compute_nodes"]["status"] == "warn"
    assert config["token"] not in json.dumps(report)

    calls = logged(log)
    sbatch = [argv for argv in calls if argv[0] == "sbatch"]
    assert len(sbatch) == 2
    assert all("--test-only" in argv or "--version" in argv for argv in sbatch)
    test_only = next(argv for argv in sbatch if "--test-only" in argv)
    assert test_only[:2] == ["sbatch", "--test-only"]
    assert {"--partition=p", "--account=a", "--qos=q"} <= set(test_only)
    assert "--partition=default" not in test_only
    assert test_only[-2:] == ["--exclusive", "--wrap=true"]
    assert ["sinfo", "-h", "-p", "p", "-o", "%P|%a|%l|%D|%c|%m"] in calls
    assert not any(argv[0] in {"squeue", "scancel"} for argv in calls)


@pytest.mark.parametrize(
    "replies,check_id,status,text",
    [
        (
            {"sinfo": {"stdout": "p|down|1:00:00|2|64|256000\n"}},
            "slurm_partition",
            "fail",
            "is down, not up",
        ),
        ({"sinfo": {"stdout": ""}}, "slurm_partition", "fail", "not found"),
        (
            {"sinfo": {"stdout": "q|up|1:00:00|2|64|256000\n"}},
            "slurm_partition",
            "fail",
            "not found",
        ),
        (
            {"sinfo": {"rc": 1, "stderr": "sinfo: error: Unable to contact slurm\n"}},
            "slurm_partition",
            "fail",
            "Unable to contact slurm",
        ),
        (
            {
                "sbatch": {
                    "rc": 1,
                    "stderr": "sbatch: error: Batch job submission failed: Invalid account or account/partition combination specified\n",
                }
            },
            "slurm_submit_test",
            "fail",
            "Invalid account",
        ),
        # Site messages may not be UTF-8, e.g. GBK on Chinese clusters.
        (
            {
                "sbatch": {
                    "rc": 1,
                    "stderr": "sbatch: error: 账户余额不足\n",
                    "encoding": "gbk",
                }
            },
            "slurm_submit_test",
            "fail",
            "sbatch: error: ",
        ),
        ({"sbatch --version": {"rc": 1}}, "slurm_version", "fail", "exit code 1"),
        (
            {"sacct": {"rc": 1, "stderr": "sacct: error: accounting disabled\n"}},
            "slurm_accounting",
            "warn",
            "reconciliation after supervisor restarts is degraded",
        ),
    ],
)
def test_slurm_probe_failures_are_reported(
    site, monkeypatch, replies, check_id, status, text
):
    state, _ = site
    configure(state, {"queue": "p"})
    reply(monkeypatch, **replies)
    report = diagnostics.diagnose_server(state, "slurm")
    result = by_id(report)[check_id]
    assert result["status"] == status
    assert text in result["message"]
    assert report["ok"] is (status != "fail")


def test_silent_submit_test_message(site, monkeypatch):
    state, _ = site
    # sbatch may print nothing for --test-only. (--quiet, which also does that, is reserved:
    # sbatch then prints no job ID either.)
    configure(state, {"queue": "p"})
    reply(monkeypatch, sbatch={})
    checks = by_id(diagnostics.diagnose_server(state, "slurm"))
    assert checks["slurm_submit_test"]["status"] == "pass"
    assert checks["slurm_submit_test"]["message"] == (
        "sbatch --test-only accepted the request; nothing was submitted."
    )


def test_slurm_probe_timeouts_and_missing_partition(site, monkeypatch):
    state, log = site
    report = by_id(diagnostics.diagnose_server(state, "slurm"))
    assert report["slurm_partition"]["status"] == "warn"
    assert report["slurm_partition"]["message"] == (
        "No partition: pass --partition or set scheduler.queue"
    )
    assert not any(argv[0] == "sinfo" for argv in logged(log))
    test_only = next(argv for argv in logged(log) if "--test-only" in argv)
    assert not any(arg.startswith("--partition") for arg in test_only)

    run = subprocess.run

    def slow(argv, **kwargs):
        if argv[0] in {"sbatch", "sinfo", "sacct"}:
            assert kwargs["timeout"] == 0.5
            assert kwargs["env"]["LC_ALL"] == "C"
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return run(argv, **kwargs)

    monkeypatch.setattr(diagnostics.subprocess, "run", slow)
    report = diagnostics.diagnose_server(state, "slurm", timeout=0.5, partition="p")
    checks = by_id(report)
    assert not report["ok"]
    for check_id in (
        "slurm_version",
        "slurm_partition",
        "slurm_submit_test",
        "slurm_accounting",
    ):
        assert checks[check_id]["status"] == "fail"
        assert "timed out" in checks[check_id]["message"]


def test_doctor_checks_scheduler_specific_options_for_its_backend(site):
    state, _ = site
    configure(state, {"submit_args": ["-Muser@example.org"]})  # a PBS mail list; Slurm --clusters
    assert by_id(diagnostics.diagnose_server(state, "pbs"))["config"]["status"] == "pass"
    for backend in ("slurm", "local"):
        config = by_id(diagnostics.diagnose_server(state, backend))["config"]
        assert config["status"] == "fail" and "must not set -M" in config["message"]


def test_preamble_dry_run(site, tmp_path):
    state, _ = site
    marker = tmp_path / "preamble-ran"

    def preamble(lines, shell="/bin/sh", run=True):
        configure(state, {"job_shell": shell, "preamble": lines})
        report = diagnostics.diagnose_server(state, "slurm", probe_preamble=run)
        return by_id(report)["scheduler_preamble"]

    assert preamble(["export X=1", 'test "$X" = 1'])["status"] == "pass"
    failed = preamble(["echo module not found >&2", "false"])
    assert failed["status"] == "fail"
    assert "module not found" in failed["message"]
    assert preamble(["false", "touch " + shlex.quote(str(marker))])["status"] == "fail"
    assert not marker.exists()
    # 'source' is not POSIX; it only works where /bin/sh happens to be bash.
    for shell in ("/bin/sh", "/usr/bin/dash"):
        warned = preamble(["source /x"], shell)
        assert warned["status"] == "warn"
        assert "source" in warned["message"]
    assert preamble(["source /dev/null"], "/bin/bash")["status"] == "pass"
    # job_shell is a '#!' line, so the interpreter may take one argument, which the kernel passes whole.
    assert preamble(["source /dev/null"], "/bin/bash -e")["status"] == "pass"
    assert preamble(["source /x"], "/usr/bin/env sh")["status"] == "warn"
    assert preamble(["true"], "/usr/bin/env bash -e")["status"] == "fail"
    # Operator commands run on this host only when explicitly requested.
    skipped = preamble(["touch " + shlex.quote(str(marker))], run=False)
    assert skipped["status"] == "warn"
    assert "--probe-preamble" in skipped["message"]
    assert not marker.exists()


def test_doctor_cli_passes_site_options(site):
    state, log = site
    config = configure(state, {"queue": "default"})
    runner = CliRunner()
    result = runner.invoke(
        server,
        [
            "--state-dir",
            str(state),
            "doctor",
            "--backend",
            "slurm",
            "--partition",
            "p",
            "--account",
            "a",
            "--qos",
            "q",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    ids = {item["id"] for item in report["checks"]}
    assert {
        "scheduler_profile",
        "slurm_version",
        "slurm_partition",
        "slurm_submit_test",
        "slurm_accounting",
    } <= ids
    assert config["token"] not in result.output
    test_only = next(argv for argv in logged(log) if "--test-only" in argv)
    assert {"--partition=p", "--account=a", "--qos=q"} <= set(test_only)

    doctor = ["--state-dir", str(state), "doctor", "--backend", "slurm", "--json"]
    configure(state, {"preamble": ["true"]})
    result = runner.invoke(server, doctor)
    assert by_id(json.loads(result.output))["scheduler_preamble"]["status"] == "warn"
    result = runner.invoke(server, doctor + ["--probe-preamble"])
    assert by_id(json.loads(result.output))["scheduler_preamble"]["status"] == "pass"

    calls = len(logged(log))
    for option in ("--partition", "--account", "--qos"):
        result = runner.invoke(server, doctor + [option, "p;true"])
        assert result.exit_code == 2
        assert "Invalid value" in result.output
    assert len(logged(log)) == calls
    with pytest.raises(ValueError, match="partition"):
        diagnostics.diagnose_server(state, "slurm", partition="p q")
