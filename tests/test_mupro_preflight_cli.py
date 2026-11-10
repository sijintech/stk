"""Remote CLI behavior through real Runtime workers and bounded result transfers."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from click.testing import CliRunner
import pytest

from conftest import finish
from suan.mupro import cli
from suan.mupro.preflight import MAX_OBSERVATION_BYTES, OBSERVATION_NAME
from suan.mupro.spec import preflight_spec
from suan.runtime.client import RuntimeClient
from suan.runtime.models import TaskSpec


WORKSPACE, OTHER_WORKSPACE, TASK = "a" * 32, "c" * 32, "b" * 32
TOKEN = "abcdefghijklmnopqrstu"
PRIVATE_MARKER = "low_entropy_private_fixture_abcdefghijklmnopqrstu"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    # Never inspect or inherit the operator's SDK, profile, credentials or scheduler state.
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONPATH": str(REPO),
           "PYTHONPYCACHEPREFIX": str(tmp_path / "bytecode"), "STK_TOKEN_PLAN_API_KEY": ""}
    monkeypatch.setattr(os, "environ", env)
    return env


def invoke(client, monkeypatch, args):
    monkeypatch.setattr(cli, "get_client", lambda *_: client)
    return CliRunner().invoke(cli.mupro, args)


class RecordedRuntime(RuntimeClient):
    def __init__(self, url, drive=None):
        super().__init__(url, TOKEN)
        self.drive, self.drop_reply = drive, False
        self.submissions, self.waits, self.reads = [], [], []

    def request(self, method, path, *args, **kwargs):
        self.reads.append((method, path, kwargs.get("max_response_bytes")))
        return super().request(method, path, *args, **kwargs)

    def submit(self, spec, idempotency_key=None):
        self.submissions.append((deepcopy(spec), idempotency_key))
        record = super().submit(spec, idempotency_key)
        if self.drop_reply:
            self.drop_reply = False
            raise TimeoutError("Synthetic accepted submission reply was lost")
        return record

    def wait(self, task_id, timeout=300, interval=0.5):
        self.waits.append((task_id, timeout))
        assert self.drive is not None, "A result-only client must not wait or start work"
        return self.drive(self, task_id, timeout)


@pytest.fixture
def remote(runtime, monkeypatch, tmp_path, isolated_environment):
    original, supervisor, server, config = runtime
    # This is a new, private fixture Runtime; use a low-entropy test credential only.
    original.token = config["token"] = TOKEN
    sdk, tools, licence = tmp_path / "worker-sdk", tmp_path / "worker-bin", tmp_path / "empty-worker-licence"
    for folder in (sdk / "bin", sdk / "share/mupro/skills/mupro-muferro/examples", tools, licence):
        folder.mkdir(parents=True)
    solver_marker, mpi_marker = tmp_path / "solver-started", tmp_path / "mpi-started"
    for path, marker in ((sdk / "bin/muFerro", solver_marker), (tools / "mpiexec", mpi_marker)):
        path.write_text(f"#!/bin/sh\nprintf started > {shlex.quote(str(marker))}\nexit 17\n")
        path.chmod(0o700)
    for name in ("input.toml", "material.toml"):
        (sdk / "share/mupro/skills/mupro-muferro/examples" / name).write_text("")
    counter, worker_script = tmp_path / "worker-sourced", tmp_path / "worker-env.sh"
    worker_script.write_text(f"printf '%s\\n' \"$PPID\" >> {shlex.quote(str(counter))}\n")
    worker_env = {**isolated_environment, "PATH": str(tools) + os.pathsep + os.defpath,
                  "MUPRO_SDK_PREFIX": str(sdk), "MUPROROOT": str(licence),
                  "STK_MUPRO_ENV_SCRIPTS": str(worker_script)}
    # LocalBackend starts the configured interpreter with ordinary process inheritance.
    # Give this private Runtime its own launcher so no operator environment reaches it,
    # while the client below retains the opposite, deliberately broken configuration.
    interpreter = tmp_path / "worker-python"
    exports = [f"{key}={value}" for key, value in worker_env.items()]
    interpreter.write_text("#!/bin/sh\nexec /usr/bin/env -i " +
                           shlex.join([*exports, sys.executable]) + ' "$@"\n')
    interpreter.chmod(0o700)
    config["python"] = str(interpreter)
    fallback, client_script = tmp_path / "client-fallback-started", tmp_path / "client-env.sh"
    client_script.write_text(f"printf forbidden > {shlex.quote(str(fallback))}\n")
    isolated_environment.update(MUPRO_SDK_PREFIX=str(tmp_path / "missing-client-sdk"),
                                MUPROROOT=str(tmp_path / "missing-client-licence"),
                                STK_MUPRO_ENV_SCRIPTS=str(client_script))
    accepted = []
    submit = server.service.submit

    def counted(spec, key=None):
        accepted.append((deepcopy(spec), key))
        return submit(spec, key)

    monkeypatch.setattr(server.service, "submit", counted)

    def drive(client, task_id, timeout=20):
        return finish(client, supervisor, task_id, timeout=min(timeout, 20))

    client = RecordedRuntime(original.url, drive)
    workspace = client.create_workspace("Owned preflight CLI fixture")["id"]
    yield SimpleNamespace(client=client, drive=drive, server=server, supervisor=supervisor, workspace=workspace,
                          sdk=sdk, counter=counter, fallback=fallback, accepted=accepted,
                          solver_marker=solver_marker, mpi_marker=mpi_marker, client_env=isolated_environment)
    assert not fallback.exists(), "No local check may substitute for an unavailable remote result"
    assert not solver_marker.exists() and not mpi_marker.exists()


@pytest.mark.server
@pytest.mark.parametrize("configured", [True, False])
def test_wait_uses_worker_configuration_and_cold_client_reads_the_same_artifact(remote, monkeypatch, tmp_path, configured):
    if not configured:
        (remote.sdk / "bin/muFerro").unlink()
    result = invoke(remote.client, monkeypatch, ["preflight", "--profile", "pilot", "--workspace", remote.workspace,
        "--key", "one-preflight", "--wait", "--timeout", "20"])
    assert result.exit_code == (0 if configured else 1), result.output
    envelope = json.loads(result.stdout)
    task_id = envelope["task"]["id"]
    assert envelope["schema"] == "stk.mupro-preflight-result/1" and envelope["scope"] == "runtime_task"
    assert envelope["task"] == {"id": task_id, "workspace_id": remote.workspace, "backend": "local",
                                "state": "succeeded" if configured else "failed", "exit_code": 0 if configured else 1}
    observation = envelope["observation"]
    statuses = {item["id"]: item["status"] for item in observation["checks"]}
    assert statuses["sdk_prefix"] == statuses["license_dir"] == statuses["env_scripts"] == "pass"
    assert statuses["program"] == ("pass" if configured else "fail")
    assert observation["summary"] == ("checks_incomplete" if configured else "checks_failed")
    assert observation["scope"] == "local_process" and observation["process_id"] != os.getpid()
    task_dir = remote.server.service.task_dir(task_id)
    assert observation["process_id"] == json.loads((task_dir / "program.json").read_text())["pid"]
    assert remote.counter.read_text().splitlines() == [str(observation["process_id"])]
    data = (task_dir / "work" / OBSERVATION_NAME).read_bytes()
    assert envelope["artifact"] == {"path": OBSERVATION_NAME, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    assert json.loads(data) == observation
    assert len(remote.client.submissions) == len(remote.accepted) == 1
    assert remote.client.waits == [(task_id, 20.0)]
    spec = remote.client.submissions[0][0]
    assert spec["argv"] == ["{python}", "-m", "suan.mupro.preflight"]
    assert spec["env"] == {} and spec["inputs"] == [] and spec["resources"] == {"cpus": 1}
    assert str(tmp_path) not in json.dumps(spec) and str(tmp_path) not in json.dumps(envelope)
    reads = [row for row in remote.client.reads if row[0] == "GET" and row[1].startswith(f"tasks/{task_id}/file?")]
    assert len(reads) == 1 and reads[0][2] == len(data)

    # A genuinely new process uses the real top-level CLI and transport, not the patched factory.
    output = tmp_path / "cold-result.json"
    env = {**remote.client_env, "STK_RUNTIME_URL": remote.client.url, "STK_RUNTIME_TOKEN": TOKEN}
    cold = subprocess.run([sys.executable, "-B", "-m", "suan.cli.main", "mupro", "preflight-result", task_id,
                           "--output", str(output)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert cold.returncode == (0 if configured else 1), cold.stderr
    reread = json.loads(cold.stdout)
    assert reread == json.loads(output.read_text())
    assert reread["task"] == envelope["task"] and reread["observation"] == observation
    assert reread["artifact"] == envelope["artifact"]
    assert reread["target"] == {"profile": None, "connection_sha256": envelope["target"]["connection_sha256"]}
    assert len(remote.accepted) == 1 and len(remote.client.tasks()) == 1
    assert remote.counter.read_text().splitlines() == [str(observation["process_id"])]


@pytest.mark.server
def test_lost_submission_requires_explicit_same_key_retry_and_executes_once(remote, monkeypatch):
    args = ["preflight", "--workspace", remote.workspace, "--key", "original-preflight"]
    remote.client.drop_reply = True
    lost = invoke(remote.client, monkeypatch, args)
    assert lost.exit_code != 0 and "Idempotency key: original-preflight" in lost.stderr
    assert len(remote.client.submissions) == len(remote.accepted) == 1
    assert not remote.counter.exists()
    original = remote.client.tasks()[0]
    retry = invoke(remote.client, monkeypatch, args)
    assert retry.exit_code == 0, retry.output
    assert json.loads(retry.stdout)["id"] == original["id"]
    assert remote.client.waits == [] and not remote.counter.exists(), "Default submission must not run a client-side check"
    changed = invoke(remote.client, monkeypatch, args + ["--name", "different request"])
    assert changed.exit_code != 0 and len(remote.client.tasks()) == 1
    assert len(remote.client.submissions) == len(remote.accepted) == 3
    remote.drive(remote.client, original["id"])
    reread = invoke(remote.client, monkeypatch, ["preflight-result", original["id"]])
    assert reread.exit_code == 0, reread.output
    assert remote.counter.read_text().splitlines() == [str(json.loads(reread.stdout)["observation"]["process_id"])]
    assert len(remote.client.submissions) == 3 and len(remote.client.tasks()) == 1


@pytest.mark.server
def test_cancelled_queued_preflight_cannot_produce_a_verified_result(remote, monkeypatch, tmp_path):
    submitted = invoke(remote.client, monkeypatch, ["preflight", "--workspace", remote.workspace, "--key", "cancel-before-start"])
    assert submitted.exit_code == 0, submitted.output
    task_id = json.loads(submitted.stdout)["id"]
    assert remote.client.task(task_id)["state"] == "queued"
    remote.client.cancel(task_id)
    remote.drive(remote.client, task_id)
    output = tmp_path / "cancelled.json"
    result = invoke(remote.client, monkeypatch, ["preflight-result", task_id, "--output", str(output)])
    assert result.exit_code != 0 and not output.exists()
    assert remote.client.task(task_id)["state"] == "cancelled"
    assert not remote.counter.exists() and len(remote.client.tasks()) == len(remote.accepted) == 1


def observation_bytes():
    return json.dumps({"schema": "stk.mupro-preflight/1", "scope": "local_process",
        "producer": {"component": "suan.mupro", "distribution_version": None}, "process_id": 123,
        "started_at": "2026-11-09T00:00:00+00:00", "observed_at": "2026-11-09T00:00:01+00:00",
        "summary": "checks_incomplete", "checks": [{"id": name, "status": status} for name, status in (
            ("env_scripts", "not_configured"), ("sdk_prefix", "pass"), ("program", "pass"),
            ("shared_libraries", "skip"), ("mpi_launcher", "pass"), ("license_dir", "pass"), ("example_case", "pass"))],
        "unverified": {"program_version": "unobserved", "license_checkout": "not_checked", "solver_execution": "not_run"}}).encode()


class ReceiptClient:
    """Controlled transport DTOs only; the production spec and parser remain real."""
    def __init__(self):
        self.record = {"id": TASK, "state": "succeeded", "exit_code": 0,
                       "spec": TaskSpec(**preflight_spec(WORKSPACE)).to_dict()}
        self.ack, self.latest = None, None
        self.body = observation_bytes()
        self.identity, self.change_identity = "owned-runtime-fixture", False
        self.submissions, self.waits, self.tasks, self.gets = [], [], [], []
        self.listings = 0
        self.listed = None

    @property
    def connection_identity(self):
        return self.identity

    def submit(self, spec, key):
        self.submissions.append((deepcopy(spec), key))
        return deepcopy(self.ack if self.ack is not None else self.record)

    def wait(self, task_id, timeout):
        self.waits.append((task_id, timeout))
        return deepcopy(self.record)

    def task(self, task_id):
        self.tasks.append(task_id)
        if len(self.tasks) > 1:
            if self.change_identity:
                self.identity = "different-runtime-fixture"
            if self.latest is not None:
                return deepcopy(self.latest)
        return deepcopy(self.record)

    def artifacts(self, task_id):
        self.listings += 1
        return deepcopy(self.listed if self.listed is not None else [
            {"path": OBSERVATION_NAME, "size": len(self.body), "sha256": hashlib.sha256(self.body).hexdigest()}])

    def request(self, method, path, *, binary=False, max_response_bytes=None):
        self.gets.append((method, path, binary, max_response_bytes))
        return self.body


def test_result_reads_once_with_the_listed_budget_and_ignores_dynamic_monitoring(monkeypatch, tmp_path):
    client = ReceiptClient()
    client.latest = {**deepcopy(client.record), "monitor": {"progress": "newer observation"}}
    output = tmp_path / "verified.json"
    result = invoke(client, monkeypatch, ["preflight-result", "--profile", "pilot", TASK, "--output", str(output)])
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope == json.loads(output.read_text())
    assert envelope["target"] == {"profile": "pilot", "connection_sha256": hashlib.sha256(client.identity.encode()).hexdigest()}
    assert client.tasks == [TASK, TASK] and client.listings == len(client.gets) == 1
    method, path, binary, limit = client.gets[0]
    assert method == "GET" and binary is True and limit == len(client.body)
    assert urlsplit(path).path == f"tasks/{TASK}/file"
    assert parse_qs(urlsplit(path).query) == {"path": [OBSERVATION_NAME], "offset": ["0"], "limit": [str(len(client.body))]}
    assert client.submissions == client.waits == []


@pytest.mark.parametrize("fault", ["argv", "malformed_spec", "wrong_task", "queued", "unknown", "cancelled",
    "wrong_exit", "boolean_exit", "digest", "oversize", "boolean_size", "body_size", "missing", "ambiguous", "truncated", "private_extra",
    "summary_list", "target_drift", "final_spec_drift", "final_boolean_exit"])
def test_result_rejects_invalid_artifact_without_file_or_resubmission(monkeypatch, tmp_path, fault):
    client = ReceiptClient()
    if fault == "argv":
        client.record["spec"]["argv"].append("--unapproved")
    elif fault == "malformed_spec":
        client.record["spec"]["resources"] = True
    elif fault == "wrong_task":
        client.record["id"] = "d" * 32
    elif fault in {"queued", "unknown", "cancelled"}:
        client.record["state"] = fault
    elif fault == "wrong_exit":
        client.record["exit_code"] = 1
    elif fault == "boolean_exit":
        client.record["exit_code"] = False
    elif fault in {"digest", "oversize", "boolean_size", "body_size", "missing", "ambiguous"}:
        client.listed = [{"path": OBSERVATION_NAME, "size": len(client.body), "sha256": hashlib.sha256(client.body).hexdigest()}]
        if fault == "digest":
            client.listed[0]["sha256"] = "a" * 64
        elif fault == "body_size":
            client.listed[0]["size"] += 1  # Valid JSON and digest still cannot satisfy this declared length.
        elif fault == "missing":
            client.listed = []
        elif fault == "ambiguous":
            client.listed *= 2
        else:
            client.listed[0]["size"] = MAX_OBSERVATION_BYTES + 1 if fault == "oversize" else True
    elif fault == "truncated":
        client.body = client.body[:-1]  # Matching listing digest, invalid complete JSON.
    elif fault in {"private_extra", "summary_list"}:
        value = json.loads(client.body)
        if fault == "private_extra":
            value["private_path"] = PRIVATE_MARKER
        else:
            value["summary"] = []
        client.body = json.dumps(value).encode()
    elif fault == "target_drift":
        client.change_identity = True
    else:
        client.latest = deepcopy(client.record)
        if fault == "final_spec_drift":
            client.latest["spec"]["workspace_id"] = OTHER_WORKSPACE
        else:
            client.latest["exit_code"] = False
    output = tmp_path / "must-not-exist.json"
    result = invoke(client, monkeypatch, ["preflight-result", TASK, "--output", str(output)])
    assert result.exit_code != 0 and not output.exists()
    assert client.submissions == client.waits == [] and PRIVATE_MARKER not in result.output
    assert result.output
    if fault == "summary_list":
        assert "invalid" in result.output.lower()
    if fault in {"argv", "malformed_spec", "wrong_task", "queued", "unknown", "cancelled"}:
        assert client.listings == 0 and client.gets == []
    if fault in {"oversize", "boolean_size", "missing", "ambiguous"}:
        assert client.gets == []


@pytest.mark.parametrize("phase", ["submission_ack", "result_read"])
def test_wait_never_accepts_another_valid_preflight_task(monkeypatch, phase):
    client = ReceiptClient()
    original = deepcopy(client.record)
    client.record["spec"] = TaskSpec(**preflight_spec(OTHER_WORKSPACE)).to_dict()
    if phase == "submission_ack":
        client.record["id"] = "d" * 32
    else:
        client.ack = original
    result = invoke(client, monkeypatch, ["preflight", "--workspace", WORKSPACE, "--key", "original-request", "--wait"])
    assert result.exit_code != 0, "A different valid task is not the task requested by this command"
    assert len(client.submissions) == 1
    assert not result.stdout.strip()
    if phase == "submission_ack":
        assert client.waits == client.tasks == []


def test_existing_output_is_never_overwritten(monkeypatch, tmp_path):
    client = ReceiptClient()
    output = tmp_path / "existing.json"
    output.write_bytes(b"owned previous output\n")
    result = invoke(client, monkeypatch, ["preflight-result", TASK, "--output", str(output)])
    assert result.exit_code != 0 and output.read_bytes() == b"owned previous output\n"
    assert client.submissions == []


@pytest.mark.parametrize("extra", [["--backend", "slurm"], ["--sdk-prefix", "client-path"], ["--license-dir", "client-path"]])
def test_invalid_or_client_local_configuration_is_rejected_before_connect(monkeypatch, extra):
    connections = []

    def no_client(*args):
        connections.append(args)
        pytest.fail("Invalid preflight options must not construct a client")
    monkeypatch.setattr(cli, "get_client", no_client)
    result = CliRunner().invoke(cli.mupro, ["preflight", "--workspace", WORKSPACE, *extra])
    assert result.exit_code != 0 and connections == []
