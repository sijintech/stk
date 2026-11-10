"""Durable preflight intents, using real Runtime acceptance and worker execution."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from conftest import finish
from suan.desktop_bridge.backends import RuntimeBackend
from suan.desktop_bridge import mupro_preflight as adapter
from suan.desktop_bridge.mupro_preflight_journal import MAX_RECORD_BYTES, MuproPreflightService
from suan.desktop_bridge.protocol import BridgeError
from suan.mupro.preflight import MAX_OBSERVATION_BYTES, OBSERVATION_NAME
from suan.runtime.client import RuntimeClient


PROJECT = "11111111-1111-4111-8111-111111111111"
OTHER_PROJECT = "22222222-2222-4222-8222-222222222222"
KEY = "a" * 32
TOKEN = "abcdefghijklmnopqrstu"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONPATH": str(REPO),
           "PYTHONPYCACHEPREFIX": str(tmp_path / "bytecode"), "STK_TOKEN_PLAN_API_KEY": ""}
    monkeypatch.setattr(os, "environ", env)
    return env


def request(identity, **changes):
    return {"project_id": PROJECT, "connection": "runtime:pilot", "expected_connection_identity": identity,
            "workspace_id": None, "options": {}, "idempotency_key": KEY, **changes}


def ref(key=KEY, project=PROJECT):
    return {"project_id": project, "id": key}


class RecordingClient(RuntimeClient):
    def __init__(self, url):
        super().__init__(url, TOKEN)
        self.requests = []
        self.drop_submit = self.drop_workspace = False

    def request(self, method, path, *args, **kwargs):
        self.requests.append((method, path, deepcopy(args)))
        return super().request(method, path, *args, **kwargs)

    def submit(self, spec, idempotency_key=None):
        value = super().submit(spec, idempotency_key)
        if self.drop_submit:
            self.drop_submit = False
            raise TimeoutError("Synthetic accepted task reply loss")
        return value

    def create_workspace(self, name, idempotency_key=None):
        value = super().create_workspace(name, idempotency_key)
        if self.drop_workspace:
            self.drop_workspace = False
            raise TimeoutError("Synthetic accepted workspace reply loss")
        return value


@pytest.fixture
def remote(runtime, monkeypatch, tmp_path, clean_environment):
    original, supervisor, server, config = runtime
    original.token = config["token"] = TOKEN
    sdk, tools, licence = tmp_path / "sdk", tmp_path / "tools", tmp_path / "licence"
    for folder in (sdk / "bin", tools, licence):
        folder.mkdir(parents=True)
    forbidden = tmp_path / "solver-or-mpi-started"
    for path in (sdk / "bin/muFerro", tools / "mpiexec"):
        path.write_text("#!/bin/sh\nprintf forbidden > " + shlex.quote(str(forbidden)) + "\nexit 17\n")
        path.chmod(0o700)
    counter, script = tmp_path / "collected", tmp_path / "worker-env.sh"
    script.write_text("printf '%s\\n' \"$PPID\" >> " + shlex.quote(str(counter)) + "\n")
    worker_env = {**clean_environment, "PATH": str(tools) + os.pathsep + os.defpath,
                  "MUPRO_SDK_PREFIX": str(sdk), "MUPROROOT": str(licence), "STK_MUPRO_ENV_SCRIPTS": str(script)}
    interpreter = tmp_path / "worker-python"
    interpreter.write_text("#!/bin/sh\nexec /usr/bin/env -i " +
        shlex.join([*(f"{key}={value}" for key, value in worker_env.items()), sys.executable]) + ' "$@"\n')
    interpreter.chmod(0o700)
    config["python"] = str(interpreter)
    client = RecordingClient(original.url)
    backend = RuntimeBackend("runtime:pilot", client)
    resolutions = []

    def resolve(params):
        resolutions.append(deepcopy(params))
        return backend

    state = tmp_path / "desktop-state"
    service = MuproPreflightService(resolve, state)
    yield SimpleNamespace(service=service, resolve=resolve, state=state, backend=backend, client=client,
        supervisor=supervisor, server=server, sdk=sdk, counter=counter, resolutions=resolutions,
        params=request(backend.server_key), env=clean_environment, forbidden=forbidden)
    service.close()
    assert not forbidden.exists()


def posts(client, path):
    return [row for row in client.requests if row[0:2] == ("POST", path)]


def cold_list(remote):
    # No Runtime URL/token/resolver configuration: this process can only list local state.
    script = ("import json,sys\nfrom suan.desktop_bridge.mupro_preflight_journal import MuproPreflightService\n"
        "def forbidden(params): raise AssertionError('list must never resolve a backend')\n"
        "service=MuproPreflightService(forbidden,sys.argv[1])\n"
        "print(json.dumps(service.list({'project_id':sys.argv[2]})))\nservice.close()\n")
    result = subprocess.run([sys.executable, "-B", "-c", script, str(remote.state), PROJECT],
                            env=remote.env, cwd=remote.state, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.server
def test_lost_task_ack_is_durable_and_explicit_retry_reads_the_single_original_task(remote):
    remote.client.drop_submit = True
    unknown = remote.service.submit(remote.params)["record"]
    assert unknown["phase"] == "unknown" and unknown["error"]["code"] == "unavailable"
    assert unknown["workspace_id"] and unknown["task_id"] is None
    assert unknown["request"]["workspace_id"] is None
    if os.name != "nt":
        assert (remote.state / "mupro-preflight").stat().st_mode & 0o777 == 0o700
        assert (remote.state / "mupro-preflight" / (KEY + ".json")).stat().st_mode & 0o777 == 0o600
    original = remote.client.tasks()[0]
    remote.service.close()
    before = len(remote.client.requests)
    assert cold_list(remote)["records"] == [unknown]
    assert len(remote.client.requests) == before and not remote.counter.exists()
    service = MuproPreflightService(remote.resolve, remote.state)
    assert service.list({"project_id": OTHER_PROJECT}) == {"records": []}
    accepted = service.retry(ref())["record"]
    assert accepted["phase"] == "accepted" and accepted["task_id"] == original["id"]
    assert len(posts(remote.client, "tasks")) == 2 and len(posts(remote.client, "workspaces")) == 1
    before = len(remote.client.requests)
    assert service.retry(ref())["record"] == accepted
    assert len(remote.client.requests) == before  # Known task retries do not even read remotely.
    finish(remote.client, remote.supervisor, original["id"])
    finished = service.refresh(ref())["record"]
    assert finished["phase"] == "finished" and finished["result"]["observation"]["summary"] == "checks_incomplete"
    pid = finished["result"]["observation"]["process_id"]
    task_dir = remote.server.service.task_dir(original["id"])
    assert pid == json.loads((task_dir / "program.json").read_text())["pid"]
    assert remote.counter.read_text().splitlines() == [str(pid)]
    assert service.refresh(ref())["record"]["result"] == finished["result"]
    assert len(remote.client.tasks()) == len(remote.client.workspaces()) == 1
    assert remote.counter.read_text().splitlines() == [str(pid)]
    assert finished["request"] == unknown["request"]
    assert not any("upload" in path for _, path, _ in remote.client.requests)
    assert len(posts(remote.client, "tasks")) == 2
    service.close()


@pytest.mark.server
def test_lost_workspace_ack_reuses_derived_key_and_never_creates_another_workspace(remote):
    remote.client.drop_workspace = True
    record = remote.service.submit(remote.params)["record"]
    assert record["phase"] == "unknown" and record["workspace_id"] is record["task_id"] is None
    assert remote.client.tasks() == [] and len(remote.client.workspaces()) == 1
    remote.service.close()
    service = MuproPreflightService(remote.resolve, remote.state)
    before = len(remote.client.requests)
    assert service.list({"project_id": PROJECT})["records"][0]["id"] == KEY
    assert service.refresh(ref())["record"] == record
    assert len(remote.client.requests) == before
    record = service.retry(ref())["record"]
    assert record["phase"] == "accepted" and record["workspace_id"] and record["task_id"]
    creates = posts(remote.client, "workspaces")
    assert len(creates) == 2 and creates[0][2] == creates[1][2]
    assert creates[0][2][0]["idempotency_key"] == "mupro-preflight:" + KEY + ":workspace"
    assert len(remote.client.workspaces()) == len(remote.client.tasks()) == len(posts(remote.client, "tasks")) == 1
    service.close()


@pytest.mark.server
def test_selected_existing_workspace_submits_once_without_creating_a_container_or_reading_results(remote):
    workspace = remote.client.create_workspace("Explicit existing workspace")["id"]
    before = len(remote.client.requests)
    assert remote.service.describe({"connection": "runtime:pilot"})["connection_identity"] == remote.backend.server_key
    assert len(remote.client.requests) == before
    record = remote.service.submit({**remote.params, "workspace_id": workspace})["record"]
    assert record["phase"] == "accepted" and record["workspace_id"] == record["request"]["workspace_id"] == workspace
    assert record["result"] is None and not remote.counter.exists()
    assert [path for method, path, _ in remote.client.requests[before:] if method == "POST"] == ["tasks"]
    assert not any("artifacts" in path for _, path, _ in remote.client.requests)


@pytest.mark.server
def test_active_same_key_is_deduplicated_across_services_and_list_never_waits_for_http(remote, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    submit = remote.client.submit

    def hold(*args, **kwargs):
        answer = submit(*args, **kwargs)
        entered.set()
        assert release.wait(10)
        return answer

    monkeypatch.setattr(remote.client, "submit", hold)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(remote.service.submit, remote.params)
        try:
            assert entered.wait(5)
            other = MuproPreflightService(remote.resolve, remote.state)
            local = pool.submit(other.list, {"project_id": PROJECT}).result(timeout=2)["records"][0]
            assert local["phase"] == "submitting"  # A live owner must not be recovered as unknown.
            assert cold_list(remote)["records"][0]["phase"] == "submitting"
            duplicate = pool.submit(other.submit, remote.params).result(timeout=2)["record"]
            assert duplicate["id"] == local["id"] and duplicate["phase"] == "submitting"
            assert other.retry(ref())["record"]["phase"] == "submitting"
            assert other.refresh(ref())["record"]["task_id"] is None
            assert len(posts(remote.client, "tasks")) == 1
        finally:
            release.set()
        assert first.result(timeout=5)["record"]["phase"] == "accepted"
        other.close()
    assert len(remote.client.tasks()) == 1


@pytest.mark.server
def test_interrupted_submit_is_recovered_without_any_automatic_execution(remote, monkeypatch):
    submit = remote.client.submit

    def crash(*args, **kwargs):
        submit(*args, **kwargs)
        raise SystemExit("Synthetic process interruption after Runtime acceptance")

    monkeypatch.setattr(remote.client, "submit", crash)
    with pytest.raises(SystemExit):
        remote.service.submit(remote.params)
    remote.service.close()
    before = len(remote.client.requests)
    service = MuproPreflightService(remote.resolve, remote.state)
    record = service.list({"project_id": PROJECT})["records"][0]
    assert record["phase"] == "unknown" and record["task_id"] is None
    assert len(remote.client.requests) == before
    monkeypatch.setattr(remote.client, "submit", submit)
    assert service.retry(ref())["record"]["task_id"] == remote.client.tasks()[0]["id"]
    assert len(remote.client.tasks()) == 1
    service.close()


@pytest.mark.server
def test_failed_checks_are_a_valid_result_and_corrupt_artifact_is_retryable_read_only(remote):
    (remote.sdk / "bin/muFerro").unlink()
    record = remote.service.submit(remote.params)["record"]
    finish(remote.client, remote.supervisor, record["task_id"])
    finished = remote.service.refresh(ref())["record"]
    assert finished["phase"] == "finished" and finished["task_state"] == "failed" and finished["task_exit_code"] == 1
    assert finished["result"]["observation"]["summary"] == "checks_failed"
    artifact = remote.server.service.task_dir(record["task_id"]) / "work" / OBSERVATION_NAME
    good = artifact.read_bytes()
    artifact.write_bytes(b"[]")
    invalid = remote.service.refresh(ref())["record"]
    assert invalid["phase"] == "error" and invalid["result"] is None and invalid["task_id"] == record["task_id"]
    assert invalid["error"]["code"] == "remote_error"
    artifact.write_bytes(good)
    assert remote.service.refresh(ref())["record"]["result"] == finished["result"]
    unicode_observation = json.loads(good)
    unicode_observation["producer"]["distribution_version"] = "中文" * 10000
    encoded = json.dumps(unicode_observation, ensure_ascii=False, separators=(",", ":")).encode()
    unicode_observation["producer"]["distribution_version"] += "x" * (MAX_OBSERVATION_BYTES - len(encoded))
    encoded = json.dumps(unicode_observation, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(encoded) == MAX_OBSERVATION_BYTES
    artifact.write_bytes(encoded)
    # This separate synthetic version fixture has a coherent manifest, so it tests
    # valid UTF-8 caching rather than the checksum rejection exercised above.
    manifest_path = artifact.parents[1] / "artifacts.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[0].update(size=artifact.stat().st_size, sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest_path.write_text(json.dumps(manifest))
    unicode_result = remote.service.refresh(ref())["record"]
    assert unicode_result["phase"] == "finished"  # Exact-limit UTF-8 must survive cache re-encoding.
    reopened = MuproPreflightService(remote.resolve, remote.state)
    assert reopened.list({"project_id": PROJECT})["records"][0]["result"] == unicode_result["result"]
    reopened.close()
    assert len(posts(remote.client, "tasks")) == len(posts(remote.client, "workspaces")) == 1
    assert len(remote.counter.read_text().splitlines()) == 1


@pytest.mark.server
def test_queued_unknown_and_cancelled_refresh_never_submits_a_replacement(remote, monkeypatch):
    accepted = remote.service.submit(remote.params)["record"]
    queued = remote.service.refresh(ref())["record"]
    assert queued["phase"] == "accepted" and queued["task_state"] == "queued" and queued["result"] is None
    task = remote.client.task
    monkeypatch.setattr(remote.client, "task", lambda task_id: {**task(task_id), "state": "running"})
    assert remote.service.refresh(ref())["record"]["phase"] == "running"
    monkeypatch.setattr(remote.client, "task", lambda task_id: {**task(task_id), "state": "unknown"})
    unknown = remote.service.refresh(ref())["record"]
    assert unknown["phase"] == "unknown" and unknown["task_id"] == accepted["task_id"]
    monkeypatch.setattr(remote.client, "task", task)
    remote.client.cancel(accepted["task_id"])
    finish(remote.client, remote.supervisor, accepted["task_id"])
    cancelled = remote.service.refresh(ref())["record"]
    assert cancelled["phase"] == "error" and cancelled["task_state"] == "cancelled"
    assert cancelled["error"]["code"] == "cancelled" and cancelled["task_id"] == accepted["task_id"]
    assert remote.service.retry(ref())["record"] == cancelled
    assert len(posts(remote.client, "tasks")) == 1 and not remote.counter.exists()


@pytest.mark.server
def test_worker_execution_fault_is_not_a_failed_checks_observation_or_a_replacement_task(remote):
    accepted = remote.service.submit(remote.params)["record"]
    output = remote.server.service.task_dir(accepted["task_id"]) / "work" / OBSERVATION_NAME
    output.write_bytes(b"{}")  # Runner must reject occupied output before sourcing trusted scripts.
    task = finish(remote.client, remote.supervisor, accepted["task_id"])
    assert task["state"] == "failed" and task["exit_code"] == 2
    record = remote.service.refresh(ref())["record"]
    assert record["phase"] == "error" and record["result"] is None
    assert record["task_id"] == accepted["task_id"] and record["task_exit_code"] == 2
    assert remote.service.retry(ref())["record"] == record
    assert len(posts(remote.client, "tasks")) == 1 and not remote.counter.exists()


@pytest.mark.server
def test_close_during_workspace_ack_stops_before_task_post_and_preserves_the_workspace(remote, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    create = remote.backend.create_workspace

    def hold(*args):
        answer = create(*args)
        entered.set()
        assert release.wait(10)
        return answer

    monkeypatch.setattr(remote.backend, "create_workspace", hold)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(remote.service.submit, remote.params)
        try:
            assert entered.wait(5)
            remote.service.close()
        finally:
            release.set()
        record = future.result(timeout=5)["record"]
    assert record["phase"] == "unknown" and record["workspace_id"] and record["task_id"] is None
    assert posts(remote.client, "tasks") == []
    with pytest.raises(BridgeError, match="closed"):
        remote.service.retry(ref())
    assert len(remote.service.list({"project_id": PROJECT})["records"]) == 1
    monkeypatch.setattr(remote.backend, "create_workspace", create)
    service = MuproPreflightService(remote.resolve, remote.state)
    assert service.retry(ref())["record"]["phase"] == "accepted"
    assert len(posts(remote.client, "workspaces")) == len(posts(remote.client, "tasks")) == 1
    service.close()


@pytest.mark.server
@pytest.mark.parametrize("binding_count", [2, 4])
def test_close_during_binding_prevents_the_next_execution_admission(remote, monkeypatch, binding_count):
    describe = adapter.describe
    calls = []

    def closing(backend):
        value = describe(backend)
        calls.append(None)
        if len(calls) == binding_count:
            remote.service.close()
        return value

    monkeypatch.setattr(adapter, "describe", closing)
    record = remote.service.submit(remote.params)["record"]
    assert record["phase"] == "unknown" and record["error"]["code"] == "shutting_down"
    assert posts(remote.client, "tasks") == []
    assert len(posts(remote.client, "workspaces")) == (0 if binding_count == 2 else 1)


@pytest.mark.parametrize("change", [{"project_id": "invalid"}, {"idempotency_key": "../key"},
    {"workspace_id": "bad"}, {"options": {"env_scripts": ["private-fixture"]}},
    {"options": {"backend": []}}, {"options": {"memory_mb": True}}, {"options": {"backend": "pbs"}},
    {"unexpected": "low-entropy-fixture"}])
def test_invalid_requests_have_no_resolution_or_record_effect(tmp_path, change):
    calls = []

    def forbidden(params):
        calls.append(params)
        raise AssertionError("Invalid requests cannot resolve a backend")

    service = MuproPreflightService(forbidden, tmp_path)
    with pytest.raises(BridgeError) as caught:
        service.submit(request("1" * 16, **change))
    assert caught.value.code == "invalid_params" and calls == []
    assert list((tmp_path / "mupro-preflight").glob("*.json")) == []


def test_describe_is_passive_and_wrong_target_never_executes_a_prepared_intent(tmp_path):
    client = SimpleNamespace(connection_identity="owned-test-runtime")
    backend = RuntimeBackend("runtime:pilot", client)
    service = MuproPreflightService(lambda params: backend, tmp_path)
    assert service.describe({"connection": "runtime:pilot"}) == {
        "connection": "runtime:pilot", "connection_identity": backend.server_key}
    record = service.reserve(request("0" * 16))["record"]
    assert record["phase"] == "prepared"
    with pytest.raises(BridgeError) as caught:
        service.retry(ref())
    assert caught.value.code == "conflict"
    assert service.list({"project_id": PROJECT})["records"] == [record]


def test_reserve_is_pure_local_durable_idempotent_and_rejects_changes_or_close(tmp_path):
    calls = []

    def forbidden(params):
        calls.append(params)
        raise AssertionError("Reservation must never resolve, describe or contact a backend")

    service = MuproPreflightService(forbidden, tmp_path)
    params = request("1" * 16)
    prepared = service.reserve(params)["record"]
    assert prepared["phase"] == "prepared"
    assert all(prepared[field] is None for field in ("workspace_id", "task_id", "task_state", "task_exit_code", "result", "error"))
    assert service.reserve({**params, "options": {"backend": "local", "name": ""}})["record"] == prepared
    for changes in ({"project_id": OTHER_PROJECT}, {"options": {"name": "different"}}):
        with pytest.raises(BridgeError) as caught:
            service.reserve({**params, **changes})
        assert caught.value.code == "conflict"
    service.close()
    with pytest.raises(BridgeError) as caught:
        service.reserve(params)
    assert caught.value.code == "shutting_down"
    reopened = MuproPreflightService(forbidden, tmp_path)
    assert reopened.list({"project_id": PROJECT})["records"] == [prepared]
    assert reopened.refresh(ref())["record"] == prepared
    assert calls == []
    reopened.close()


@pytest.mark.server
@pytest.mark.parametrize("lost_ack", [False, True])
def test_reservation_without_current_scope_or_ack_never_executes_until_explicit_recovery(remote, lost_ack):
    before = len(remote.client.requests)
    resolutions = len(remote.resolutions)

    def reserve_reply():
        reply = remote.service.reserve(remote.params)
        if lost_ack:
            raise TimeoutError("Synthetic native reservation acknowledgement loss")
        return reply

    if lost_ack:
        with pytest.raises(TimeoutError):
            reserve_reply()
    else:
        # Model a changed UI epoch after the durable ACK: the initiating action
        # stops here, deliberately issuing no execution RPC.
        assert reserve_reply()["record"]["phase"] == "prepared"
    remote.service.close()
    assert cold_list(remote)["records"][0]["phase"] == "prepared"
    reopened = MuproPreflightService(remote.resolve, remote.state)
    prepared = reopened.list({"project_id": PROJECT})["records"][0]
    assert prepared["id"] == KEY and prepared["task_id"] is None
    assert reopened.refresh(ref())["record"] == prepared
    assert reopened.reserve(remote.params)["record"] == prepared
    assert len(remote.client.requests) == before and len(remote.resolutions) == resolutions
    assert not remote.counter.exists()
    assert remote.client.tasks() == remote.client.workspaces() == []
    accepted = reopened.retry(ref())["record"]  # A later explicit recovery uses the durable original ID.
    assert accepted["id"] == KEY and accepted["phase"] == "accepted"
    assert accepted["request"] == prepared["request"]
    assert len(remote.client.tasks()) == len(remote.client.workspaces()) == 1
    assert len(posts(remote.client, "tasks")) == len(posts(remote.client, "workspaces")) == 1
    reopened.close()


@pytest.mark.server
def test_missing_intent_during_active_submit_cannot_be_redefined_by_reservation(remote, monkeypatch):
    prepared = remote.service.reserve(remote.params)["record"]
    other = MuproPreflightService(remote.resolve, remote.state)
    entered, release = threading.Event(), threading.Event()
    submit = remote.client.submit

    def hold(*args, **kwargs):
        answer = submit(*args, **kwargs)
        entered.set()
        assert release.wait(10)
        return answer

    monkeypatch.setattr(remote.client, "submit", hold)
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(remote.service.retry, ref())
        try:
            assert entered.wait(5)
            path = remote.state / "mupro-preflight" / (KEY + ".json")
            path.unlink()  # Storage damage while the original Runtime ACK is held.
            with pytest.raises(BridgeError) as caught:
                other.reserve({**remote.params, "project_id": OTHER_PROJECT, "options": {"name": "different"}})
            assert caught.value.code in {"busy", "unavailable"} and not path.exists()
        finally:
            release.set()
        with pytest.raises(BridgeError) as caught:
            active.result(timeout=5)
        assert caught.value.code == "unavailable"
    with pytest.raises(BridgeError):
        other.list({"project_id": PROJECT})
    assert len(remote.client.tasks()) == len(posts(remote.client, "tasks")) == 1
    assert prepared["request"]["options"]["name"] == ""
    other.close()


def test_list_returns_twenty_project_records_but_does_not_hide_older_corruption(tmp_path):
    class QueueClient:
        connection_identity = "owned-portable-runtime-fixture"

        def submit(self, spec, key):
            return {"id": key, "spec": deepcopy(spec), "state": "queued", "exit_code": None}

    backend = RuntimeBackend("runtime:pilot", QueueClient())
    service = MuproPreflightService(lambda params: backend, tmp_path)
    keys = [f"{index:032x}" for index in range(21)]
    for key in keys:
        service.submit(request(backend.server_key, workspace_id="b" * 32, idempotency_key=key))
    service.submit(request(backend.server_key, workspace_id="b" * 32, idempotency_key="c" * 32,
                           project_id=OTHER_PROJECT))
    records = service.list({"project_id": PROJECT})["records"]
    assert len(records) == 20 and {record["id"] for record in records} == set(keys[1:])
    assert len(service.list({"project_id": OTHER_PROJECT})["records"]) == 1
    # Damage the excluded oldest record. A bounded response must not silently turn
    # corrupted history into permission to guess/re-execute an intent.
    (tmp_path / "mupro-preflight" / (keys[0] + ".json")).write_text("{}")
    with pytest.raises(BridgeError) as caught:
        service.list({"project_id": PROJECT})
    assert caught.value.code == "unavailable"
    service.close()


@pytest.mark.server
def test_key_is_bound_to_project_and_canonical_request_and_wrong_target_does_not_retry(remote):
    accepted = remote.service.submit(remote.params)["record"]
    count = len(remote.client.requests)
    assert remote.service.submit({**remote.params, "options": {"backend": "local", "name": ""}})["record"] == accepted
    for params in ({**remote.params, "project_id": OTHER_PROJECT}, {**remote.params, "options": {"name": "different"}}):
        with pytest.raises(BridgeError) as caught:
            remote.service.submit(params)
        assert caught.value.code == "conflict"
    with pytest.raises(BridgeError) as caught:
        remote.service.refresh(ref(project=OTHER_PROJECT))
    assert caught.value.code == "conflict"
    assert len(remote.client.requests) == count
    original_url = remote.client.url
    remote.client.url = "http://127.0.0.1:1"
    with pytest.raises(BridgeError) as caught:
        remote.service.refresh(ref())
    assert caught.value.code == "conflict" and len(remote.client.requests) == count
    remote.client.url = original_url


@pytest.mark.server
@pytest.mark.parametrize("damage", ["duplicate", "private_extra", "oversize"])
def test_corrupt_journal_never_guesses_an_executable_recovery(remote, damage):
    remote.client.drop_workspace = True
    record = remote.service.submit(remote.params)["record"]
    path = remote.state / "mupro-preflight" / (KEY + ".json")
    if damage == "duplicate":
        path.write_text('{"id":"' + KEY + '","id":"' + KEY + '"}')
    elif damage == "private_extra":
        path.write_text(json.dumps({**record, "unexpected_private_path": "low-entropy-test-fixture"}))
    else:
        path.write_bytes(b" " * (MAX_RECORD_BYTES + 1))
    count = len(remote.client.requests)
    with pytest.raises(BridgeError) as caught:
        remote.service.retry(ref())
    assert caught.value.code == "unavailable" and not caught.value.retryable
    with pytest.raises(BridgeError):
        MuproPreflightService(remote.resolve, remote.state)
    assert len(remote.client.requests) == count and posts(remote.client, "tasks") == []
