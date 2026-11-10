"""Unregistered desktop-bridge preflight adapter over a real loopback Runtime and worker."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from conftest import finish
from suan.desktop_bridge import mupro_preflight as adapter
from suan.desktop_bridge.backends import HubBackend, RuntimeBackend
from suan.desktop_bridge.protocol import BridgeError
from suan.mupro.preflight import OBSERVATION_NAME
from suan.mupro.spec import preflight_spec
from suan.runtime.client import RuntimeClient, RuntimeErrorResponse
from suan.runtime.models import TaskSpec


WORKSPACE, OTHER_WORKSPACE, TASK = "a" * 32, "c" * 32, "b" * 32
TOKEN = "abcdefghijklmnopqrstu"
PRIVATE_MARKER = "low_entropy_private_fixture_abcdefghijklmnopqrstu"
CONNECTION = "runtime:pilot"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    # Never inspect or inherit the operator's SDK, profile, credentials or scheduler state.
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONPATH": str(REPO),
           "PYTHONPYCACHEPREFIX": str(tmp_path / "bytecode"), "STK_TOKEN_PLAN_API_KEY": ""}
    monkeypatch.setattr(os, "environ", env)
    return env


def target(backend):
    return {"connection": backend.connection_id, "expected_connection_identity": backend.server_key}


def submit_params(backend, workspace=WORKSPACE, key="bridge-preflight", **options):
    return {**target(backend), "workspace_id": workspace, "idempotency_key": key, "options": options}


def result_params(backend, task_id=TASK):
    return {**target(backend), "task_id": task_id}


def bridge_error(function, *args):
    with pytest.raises(BridgeError) as caught:
        function(*args)
    return caught.value


class RecordedRuntime(RuntimeClient):
    def __init__(self, url):
        super().__init__(url, TOKEN)
        self.drop_reply = False
        self.submissions, self.reads = [], []

    def request(self, method, path, *args, **kwargs):
        self.reads.append((method, path))
        return super().request(method, path, *args, **kwargs)

    def submit(self, spec, idempotency_key=None):
        self.submissions.append((deepcopy(spec), idempotency_key))
        record = super().submit(spec, idempotency_key)
        if self.drop_reply:
            self.drop_reply = False
            raise TimeoutError("Synthetic accepted submission reply was lost")
        return record

    def wait(self, *args, **kwargs):
        pytest.fail("The bridge adapter must never wait for a task")


@pytest.fixture
def remote(runtime, monkeypatch, tmp_path, isolated_environment):
    original, supervisor, server, config = runtime
    original.token = config["token"] = TOKEN  # private fixture Runtime; low-entropy test credential
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
    # The private Runtime starts this explicit interpreter; no operator environment reaches it.
    interpreter = tmp_path / "worker-python"
    exports = [f"{key}={value}" for key, value in worker_env.items()]
    interpreter.write_text("#!/bin/sh\nexec /usr/bin/env -i " + shlex.join([*exports, sys.executable]) + ' "$@"\n')
    interpreter.chmod(0o700)
    config["python"] = str(interpreter)
    # The bridge process deliberately has a broken local configuration: it must never be used.
    fallback, client_script = tmp_path / "client-fallback-started", tmp_path / "client-env.sh"
    client_script.write_text(f"printf forbidden > {shlex.quote(str(fallback))}\n")
    isolated_environment.update(MUPRO_SDK_PREFIX=str(tmp_path / "missing-client-sdk"),
                                MUPROROOT=str(tmp_path / "missing-client-licence"),
                                STK_MUPRO_ENV_SCRIPTS=str(client_script))
    accepted = []
    service_submit = server.service.submit

    def counted(spec, key=None):
        accepted.append((deepcopy(spec), key))
        return service_submit(spec, key)

    monkeypatch.setattr(server.service, "submit", counted)
    client = RecordedRuntime(original.url)
    workspace = client.create_workspace("Owned preflight bridge fixture")["id"]
    client.reads.clear()
    yield SimpleNamespace(client=client, backend=RuntimeBackend(CONNECTION, client), server=server,
                          supervisor=supervisor, workspace=workspace, sdk=sdk, counter=counter,
                          accepted=accepted, tmp_path=tmp_path)
    assert not fallback.exists(), "No local check may substitute for a remote result"
    assert not solver_marker.exists() and not mpi_marker.exists()


def collections(remote):
    return remote.counter.read_text().splitlines() if remote.counter.exists() else []


@pytest.mark.server
@pytest.mark.parametrize("configured", [True, False])
def test_submit_then_result_reads_the_worker_observation_without_repeating_it(remote, configured):
    if not configured:
        (remote.sdk / "bin/muFerro").unlink()
    backend = remote.backend
    assert adapter.describe(backend) == {"connection": CONNECTION, "connection_identity": backend.server_key}
    assert remote.client.reads == [] and remote.accepted == []

    submitted = adapter.submit(backend, submit_params(backend, remote.workspace, "bridge-one"))
    assert set(submitted) == {"task"}
    task = submitted["task"]
    assert task["state"] == "queued" and task["spec"] == TaskSpec(**preflight_spec(remote.workspace)).to_dict()
    assert remote.client.submissions == remote.accepted == [(preflight_spec(remote.workspace), "bridge-one")]
    assert collections(remote) == [], "Submission alone neither waits nor runs a check"

    finish(remote.client, remote.supervisor, task["id"])
    reply = adapter.result(backend, result_params(backend, task["id"]))
    assert set(reply) == {"result", "connection", "connection_identity"}
    assert reply["connection"] == CONNECTION and reply["connection_identity"] == backend.server_key
    envelope = reply["result"]
    assert envelope["schema"] == "stk.mupro-preflight-result/1" and envelope["scope"] == "runtime_task"
    assert envelope["target"] == {"profile": None,
        "connection_sha256": hashlib.sha256(remote.client.url.encode()).hexdigest()}
    assert envelope["task"] == {"id": task["id"], "workspace_id": remote.workspace, "backend": "local",
        "state": "succeeded" if configured else "failed", "exit_code": 0 if configured else 1}
    observation = envelope["observation"]
    statuses = {item["id"]: item["status"] for item in observation["checks"]}
    assert statuses["program"] == ("pass" if configured else "fail")
    assert observation["summary"] == ("checks_incomplete" if configured else "checks_failed")
    task_dir = remote.server.service.task_dir(task["id"])
    assert observation["process_id"] == json.loads((task_dir / "program.json").read_text())["pid"] != os.getpid()
    data = (task_dir / "work" / OBSERVATION_NAME).read_bytes()
    assert envelope["artifact"] == {"path": OBSERVATION_NAME, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    assert collections(remote) == [str(observation["process_id"])]

    # Repeated reads verify the same artifact: no submission, collection, or task creation.
    for _ in range(2):
        assert adapter.result(backend, result_params(backend, task["id"])) == reply
    assert len(remote.client.submissions) == len(remote.accepted) == 1 and len(remote.client.tasks()) == 1
    assert collections(remote) == [str(observation["process_id"])]
    assert [row for row in remote.client.reads if row[0] != "GET"] == [("POST", "tasks")]
    text = json.dumps([submitted, reply])
    assert remote.client.url not in text and str(remote.tmp_path) not in text and TOKEN not in text


@pytest.mark.server
def test_lost_reply_is_recovered_only_by_an_explicit_same_key_request(remote):
    backend = remote.backend
    params = submit_params(backend, remote.workspace, "uncertain-preflight")
    remote.client.drop_reply = True
    lost = bridge_error(adapter.submit, backend, params)
    assert lost.code == "unavailable"
    assert len(remote.client.submissions) == len(remote.accepted) == 1, "No automatic retry or replacement"
    original = remote.client.tasks()[0]
    replay = adapter.submit(backend, deepcopy(params))
    assert replay["task"]["id"] == original["id"] and len(remote.client.tasks()) == 1
    changed = bridge_error(adapter.submit, backend, {**params, "options": {"name": "different request"}})
    assert changed.code == "conflict" and len(remote.client.tasks()) == 1
    assert len(remote.client.submissions) == len(remote.accepted) == 3
    unfinished = bridge_error(adapter.result, backend, result_params(backend, original["id"]))
    assert unfinished.code == "remote_error" and "finish" in unfinished.message
    assert collections(remote) == [] and len(remote.accepted) == 3


class StrictClient:
    """A Runtime client stand-in that fails any transport use; identity is local metadata."""
    connection_identity = "owned-runtime-fixture"

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        self.calls.append(name)
        raise AssertionError(f"Rejected requests must not reach the Runtime ({name})")


def without(mapping, key):
    return {k: v for k, v in mapping.items() if k != key}


SUBMIT_REJECTIONS = {
    "not_object": (lambda p: [p], "invalid_params"),
    "unknown_key": (lambda p: {**p, "node": "d" * 32}, "invalid_params"),
    "spec_key": (lambda p: {**p, "spec": {}}, "invalid_params"),
    "missing_options": (lambda p: without(p, "options"), "invalid_params"),
    "missing_identity": (lambda p: without(p, "expected_connection_identity"), "invalid_params"),
    "missing_connection": (lambda p: without(p, "connection"), "invalid_params"),
    "null_identity": (lambda p: {**p, "expected_connection_identity": None}, "invalid_params"),
    "options_list": (lambda p: {**p, "options": []}, "invalid_params"),
    **{f"option_{name}": (lambda p, name=name: {**p, "options": {name: "client-path"}}, "invalid_params")
       for name in ("sdk_prefix", "license_dir", "env_scripts", "program", "case_dir", "env", "argv", "inputs")},
    "boolean_walltime": (lambda p: {**p, "options": {"walltime_seconds": True}}, "invalid_params"),
    "zero_memory": (lambda p: {**p, "options": {"memory_mb": 0}}, "invalid_params"),
    "cluster_without_walltime": (lambda p: {**p, "options": {"backend": "slurm"}}, "invalid_params"),
    "local_queue": (lambda p: {**p, "options": {"queue": "batch"}}, "invalid_params"),
    "unknown_backend": (lambda p: {**p, "options": {"backend": "ssh"}}, "invalid_params"),
    "empty_key": (lambda p: {**p, "idempotency_key": ""}, "invalid_params"),
    "long_key": (lambda p: {**p, "idempotency_key": "k" * 201}, "invalid_params"),
    "integer_key": (lambda p: {**p, "idempotency_key": 7}, "invalid_params"),
    "bad_workspace": (lambda p: {**p, "workspace_id": "../workspace"}, "invalid_params"),
    "integer_workspace": (lambda p: {**p, "workspace_id": 7}, "invalid_params"),
    "wrong_connection": (lambda p: {**p, "connection": "runtime:other"}, "conflict"),
    "wrong_identity": (lambda p: {**p, "expected_connection_identity": "0" * 16}, "conflict"),
    "full_digest_identity": (lambda p: {**p, "expected_connection_identity":
        hashlib.sha256(StrictClient.connection_identity.encode()).hexdigest()}, "conflict"),
}


@pytest.mark.parametrize("case", sorted(SUBMIT_REJECTIONS))
def test_submit_rejects_invalid_or_retargeted_requests_before_any_effect(case):
    client = StrictClient()
    backend = RuntimeBackend(CONNECTION, client)
    mutate, code = SUBMIT_REJECTIONS[case]
    error = bridge_error(adapter.submit, backend, mutate(submit_params(backend)))
    assert error.code == code and client.calls == []


RESULT_REJECTIONS = {
    "unknown_key": (lambda p: {**p, "profile": None}, "invalid_params"),
    "missing_identity": (lambda p: without(p, "expected_connection_identity"), "invalid_params"),
    "bad_task": (lambda p: {**p, "task_id": "../" + TASK}, "invalid_params"),
    "upper_task": (lambda p: {**p, "task_id": TASK.upper()}, "invalid_params"),
    "wrong_connection": (lambda p: {**p, "connection": "runtime:other"}, "conflict"),
    "wrong_identity": (lambda p: {**p, "expected_connection_identity": "0" * 16}, "conflict"),
}


@pytest.mark.parametrize("case", sorted(RESULT_REJECTIONS))
def test_result_rejects_invalid_or_retargeted_requests_before_any_read(case):
    client = StrictClient()
    backend = RuntimeBackend(CONNECTION, client)
    mutate, code = RESULT_REJECTIONS[case]
    error = bridge_error(adapter.result, backend, mutate(result_params(backend)))
    assert error.code == code and client.calls == []


def test_describe_is_metadata_only():
    client = StrictClient()
    backend = RuntimeBackend(CONNECTION, client)
    assert adapter.describe(backend) == {"connection": CONNECTION,
        "connection_identity": hashlib.sha256(client.connection_identity.encode()).hexdigest()[:16]}
    assert client.calls == []


class TrapHub:
    def __init__(self):
        self.accessed = []

    def __getattr__(self, name):
        self.accessed.append(name)
        raise AssertionError("A hub preflight must not reach the hub")


def test_hub_and_duck_typed_backends_are_unsupported_before_io():
    hub = TrapHub()
    hub_backend = HubBackend("hub:lab", hub, "d" * 32)
    lookalike = SimpleNamespace(kind="runtime", connection_id=CONNECTION, server_key="0" * 16,
                                client=StrictClient(), call=lambda *a, **k: pytest.fail("no fallback call"))
    for backend in (hub_backend, lookalike):
        params = {"connection": backend.connection_id, "expected_connection_identity": "0" * 16}
        for function, extra in ((adapter.submit, {"workspace_id": WORKSPACE, "idempotency_key": "k", "options": {}}),
                                (adapter.result, {"task_id": TASK})):
            assert bridge_error(function, backend, {**params, **extra}).code == "unsupported"
        assert bridge_error(adapter.describe, backend).code == "unsupported"
    assert hub.accessed == [] and lookalike.client.calls == []


def observation_bytes(**changes):
    value = {"schema": "stk.mupro-preflight/1", "scope": "local_process",
        "producer": {"component": "suan.mupro", "distribution_version": None}, "process_id": 123,
        "started_at": "2026-11-09T00:00:00+00:00", "observed_at": "2026-11-09T00:00:01+00:00",
        "summary": "checks_incomplete", "checks": [{"id": name, "status": status} for name, status in (
            ("env_scripts", "not_configured"), ("sdk_prefix", "pass"), ("program", "pass"),
            ("shared_libraries", "skip"), ("mpi_launcher", "pass"), ("license_dir", "pass"), ("example_case", "pass"))],
        "unverified": {"program_version": "unobserved", "license_checkout": "not_checked", "solver_execution": "not_run"}}
    return json.dumps({**value, **changes}).encode()


class ReceiptClient:
    """Controlled transport replies inside a real RuntimeBackend; the shared checks stay real."""
    def __init__(self):
        self.record = {"id": TASK, "state": "succeeded", "exit_code": 0,
                       "spec": TaskSpec(**preflight_spec(WORKSPACE)).to_dict()}
        self.ack, self.submit_error, self.read_error = None, None, None
        self.body = observation_bytes()
        self.connection_identity, self.drift = "owned-runtime-fixture", False
        self.submissions, self.tasks, self.gets = [], [], []

    def submit(self, spec, key):
        self.submissions.append((deepcopy(spec), key))
        if self.submit_error is not None:
            raise self.submit_error
        return deepcopy(self.record if self.ack is None else self.ack)

    def task(self, task_id):
        self.tasks.append(task_id)
        if len(self.tasks) > 1 and self.drift:
            self.connection_identity = "different-runtime-fixture"
        return deepcopy(self.record)

    def artifacts(self, task_id):
        return [{"path": OBSERVATION_NAME, "size": len(self.body), "sha256": hashlib.sha256(self.body).hexdigest()}]

    def request(self, method, path, *, binary=False, max_response_bytes=None):
        self.gets.append((method, path, max_response_bytes))
        if self.read_error is not None:
            raise self.read_error
        return self.body


def test_verified_receipt_returns_the_shared_envelope_with_the_frozen_target():
    client = ReceiptClient()
    backend = RuntimeBackend(CONNECTION, client)
    reply = adapter.result(backend, result_params(backend))
    assert reply["connection"] == CONNECTION and reply["connection_identity"] == backend.server_key
    assert reply["result"]["target"] == {"profile": None,
        "connection_sha256": hashlib.sha256(client.connection_identity.encode()).hexdigest()}
    assert reply["result"]["observation"] == json.loads(client.body)
    assert client.tasks == [TASK, TASK] and len(client.gets) == 1 and client.submissions == []


@pytest.mark.parametrize("fault", ["other_workspace", "other_task_id", "invalid_task_id", "not_object",
                                   "modified_argv", "private_spec", "undecodable_reply"])
def test_submission_reply_mismatch_is_a_safe_remote_error_without_retry(fault):
    client = ReceiptClient()
    ack = deepcopy(client.record)
    if fault == "other_workspace":
        ack["spec"] = TaskSpec(**preflight_spec(OTHER_WORKSPACE)).to_dict()
    elif fault == "other_task_id":
        ack["id"] = "d" * 32  # Accepted as a task, but its spec still has to match the request.
        ack["spec"]["name"] = "another preflight"
    elif fault == "invalid_task_id":
        ack["id"] = PRIVATE_MARKER
    elif fault == "not_object":
        ack = [PRIVATE_MARKER]
    elif fault == "modified_argv":
        ack["spec"]["argv"].append("--unapproved")
    elif fault == "private_spec":
        ack["spec"]["env"] = {"PRIVATE": PRIVATE_MARKER}
    else:
        client.submit_error = ValueError(f"Expecting value: {PRIVATE_MARKER}")  # e.g. a non-JSON reply
    client.ack = ack
    backend = RuntimeBackend(CONNECTION, client)
    error = bridge_error(adapter.submit, backend, submit_params(backend, key="original-request"))
    assert error.code == "remote_error" and PRIVATE_MARKER not in error.message + json.dumps(error.data)
    if fault != "undecodable_reply":
        assert "observe the original idempotency key" in error.message
    assert client.submissions == [(preflight_spec(WORKSPACE), "original-request")]
    assert client.tasks == client.gets == []


@pytest.mark.parametrize("fault", ["private_extra", "failed_summary_mismatch", "digest", "undecodable_body",
                                   "queued", "cancelled", "foreign_spec"])
def test_malformed_result_is_a_safe_remote_error(fault):
    client = ReceiptClient()
    if fault == "private_extra":
        client.body = observation_bytes(private_path=PRIVATE_MARKER)
    elif fault == "failed_summary_mismatch":
        client.body = observation_bytes(summary="checks_failed")
    elif fault == "digest":
        client.artifacts = lambda task_id: [{"path": OBSERVATION_NAME, "size": len(client.body), "sha256": "a" * 64}]
    elif fault == "undecodable_body":
        client.read_error = UnicodeDecodeError("utf-8", PRIVATE_MARKER.encode(), 0, 1, PRIVATE_MARKER)
    elif fault in {"queued", "cancelled"}:
        client.record["state"] = fault
    else:
        client.record["spec"]["env"] = {"PRIVATE": PRIVATE_MARKER}
    backend = RuntimeBackend(CONNECTION, client)
    error = bridge_error(adapter.result, backend, result_params(backend))
    assert error.code == "remote_error" and PRIVATE_MARKER not in error.message + json.dumps(error.data)
    assert client.submissions == []


def test_endpoint_change_while_reading_is_a_conflict():
    client = ReceiptClient()
    client.drift = True
    backend = RuntimeBackend(CONNECTION, client)
    error = bridge_error(adapter.result, backend, result_params(backend))
    assert error.code == "conflict" and client.submissions == []


@pytest.mark.parametrize("failure, code", [
    (URLError("connection refused"), "unavailable"), (TimeoutError("synthetic"), "unavailable"),
    (RuntimeErrorResponse(404, "Task not found"), "not_found"),
    (RuntimeErrorResponse(401, "synthetic refusal"), "unauthorized"),
    (RuntimeErrorResponse(502, "Runtime response exceeds its byte budget"), "remote_error")])
def test_transport_failures_use_the_existing_runtime_mapping(failure, code):
    client = ReceiptClient()
    client.read_error = failure
    backend = RuntimeBackend(CONNECTION, client)
    assert bridge_error(adapter.result, backend, result_params(backend)).code == code
    client.submit_error = failure
    assert bridge_error(adapter.submit, backend, submit_params(backend)).code == code
    assert len(client.submissions) == 1, "A transport failure is never retried automatically"
