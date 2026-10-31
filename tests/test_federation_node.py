"""Node persistence and real Runtime routes; optional installed ClientApp execution."""
from copy import deepcopy
import os
from pathlib import Path
import time
from uuid import UUID

import pytest

from conftest import finish
from test_federation_training import model, spec
from suan.federation import inputs
from suan.federation.node import NodeFederationService, NodeFederationError
from suan.federation.protocol import training_spec_sha256
from suan.runtime.client import RuntimeErrorResponse


def prepare(runtime, tmp_path, python=None):
    client = runtime[0]
    service = NodeFederationService(client, tmp_path / "private", python or os.sys.executable)
    settings = spec()
    dataset = service.register_dataset(str(UUID(int=10)), [[-1.], [0.], [1.], [2.]], [[-3.], [-1.], [1.], [3.]])
    grant = service.approve(settings, dataset["dataset_id"], run_id=str(UUID(int=20)), coordinator_id="a"*64,
                            participant_id="b"*64, max_rounds=6)
    raw = model(settings)
    from suan.federation.updates import decode_arrays
    message = {"format": "stk.federation-message/1", "operation": "train", "run_id": grant.run_id,
               "round": 1, "coordinator_id": grant.coordinator_id, "participant_id": grant.participant_id,
               "grant_id": grant.grant_id, "spec_sha256": training_spec_sha256(settings),
               "dataset_sha256": dataset["dataset_sha256"], "model": {"sha256": decode_arrays(raw)["sha256"], "bytes": len(raw)}}
    return service, message, raw


def execute(service, message, raw, operation=None, publisher=None):
    message = {**message, "operation": operation or message["operation"]}
    return service.execute(message, fetch_model=lambda descriptor: raw,
                           publish_update=publisher or (lambda *_: pytest.fail("read/dispatch sent an update")))


def test_constructor_is_passive_and_private_queries_do_not_create_state(tmp_path):
    service = NodeFederationService(None, tmp_path / "absent", None)
    assert not service.is_private_task("a"*32) and not service.is_private_workspace("b"*32)
    assert not service.root.exists()


def test_actual_runtime_client_rejects_private_root_overlap(runtime, tmp_path):
    public = Path(runtime[3]["workspace_root"])
    for root in (public, public / "dataset", public.parent):
        with pytest.raises(ValueError, match="disjoint"):
            NodeFederationService(runtime[0], root, None, workspace_root=public)
    service = NodeFederationService(runtime[0], tmp_path / "separate", None, workspace_root=public)
    assert not service.root.exists()


def test_private_identity_snapshot_reads_each_reservation_once(tmp_path, monkeypatch):
    service = NodeFederationService(None, tmp_path / "private", None)
    for index in range(20):
        inputs.write_json(service.root / "jobs" / f"{index:064x}" / "state.json",
                          {"task_id": f"{index:032x}", "workspace_id": f"{index+100:032x}"})
    calls = []
    original = inputs.read_json
    def counted(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(inputs, "read_json", counted)
    identities = service.private_identities()
    assert len(identities["tasks"]) == len(identities["workspaces"]) == len(calls) == 20
    assert f"{1:032x}" in identities["tasks"]


def test_private_identity_snapshot_rejects_linked_state(tmp_path):
    service = NodeFederationService(None, tmp_path / "private", None)
    folder = service.root / "jobs" / ("a"*64)
    folder.mkdir(parents=True)
    try:
        (folder / "state.json").symlink_to(tmp_path / "absent")
    except OSError:
        pytest.skip("symlink unavailable on this host")
    with pytest.raises((ValueError, OSError)):
        service.private_identities()


def test_dispatch_reopen_exact_retry_and_conflicting_model(runtime, tmp_path):
    service, message, raw = prepare(runtime, tmp_path)
    first = execute(service, message, raw)
    assert first["state"] == "queued" and first["update"] is None
    reopened = NodeFederationService(runtime[0], service.root, None)
    assert execute(reopened, message, raw) == first
    assert execute(reopened, message, raw, "status") == first
    assert len(runtime[0].tasks()) == 1
    changed = deepcopy(message)
    changed["model"]["sha256"] = "f"*64
    with pytest.raises(NodeFederationError):
        execute(service, changed, raw)
    assert reopened.is_private_task(first["task_id"])
    task = runtime[0].task(first["task_id"])
    assert reopened.is_private_workspace(task["spec"]["workspace_id"])
    assert runtime[0].files(task["spec"]["workspace_id"]) == []


def test_cancel_queued_does_not_execute_and_revocation_blocks_dispatch(runtime, tmp_path):
    service, message, raw = prepare(runtime, tmp_path)
    receipt = execute(service, message, raw)
    assert execute(service, message, raw, "cancel")["state"] == "cancelled"
    assert runtime[0].task(receipt["task_id"])["cancel_requested"]
    assert not list((service.root / "jobs").glob("*/attempt.json"))
    service.consent.revoke(message["grant_id"])
    later = {**message, "round": 2}
    with pytest.raises(NodeFederationError):
        execute(service, later, raw)
    assert len(runtime[0].tasks()) == 1


def test_cancel_intent_precedes_runtime_authority_without_private_exit_race(runtime, tmp_path, monkeypatch):
    service, message, raw = prepare(runtime, tmp_path)
    execute(service, message, raw)
    directory = service._directory(message)
    original = runtime[0].cancel
    def checked(task_id):
        assert inputs.read_json(directory / "state.json")["cancel_requested"] is True
        assert not (directory / "cancel").exists()
        return original(task_id)
    monkeypatch.setattr(runtime[0], "cancel", checked)
    assert execute(service, message, raw, "cancel")["state"] == "cancelled"
    assert (directory / "cancel").exists()


def test_lost_submit_reply_retains_workspace_and_resolves_original_key(runtime, tmp_path, monkeypatch):
    service, message, raw = prepare(runtime, tmp_path)
    original = runtime[0].submit
    def lost(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("private path that must not escape")
    monkeypatch.setattr(runtime[0], "submit", lost)
    with pytest.raises(NodeFederationError) as error:
        execute(service, message, raw)
    assert "private path" not in str(error.value)
    task = runtime[0].tasks()[0]
    reopened = NodeFederationService(runtime[0], service.root, None)
    assert reopened.is_private_task(task["id"])
    assert reopened.is_private_workspace(task["spec"]["workspace_id"])
    assert execute(reopened, message, raw, "status")["state"] == "queued"
    monkeypatch.setattr(runtime[0], "submit", original)
    restored = NodeFederationService(runtime[0], service.root, os.sys.executable)
    assert execute(restored, message, raw)["task_id"] == task["id"]
    assert len(runtime[0].tasks()) == 1


def test_interpreter_is_required_only_for_new_dispatch(runtime, tmp_path):
    service, message, raw = prepare(runtime, tmp_path)
    reopened = NodeFederationService(runtime[0], service.root, None)
    with pytest.raises(NodeFederationError, match="unavailable"):
        execute(reopened, message, raw)
    assert runtime[0].tasks() == []


@pytest.mark.parametrize("dtype", ["f32", "f64"])
@pytest.mark.parametrize("strategy", ["fedavg", "fedprox"])
def test_real_installed_clientapp_runtime_and_private_outputs(runtime, tmp_path, dtype, strategy):
    python = os.environ.get("STK_FEDERATION_TEST_PYTHON")
    if not python:
        pytest.skip("explicit installed Flower interpreter required")
    service, message, raw = prepare(runtime, tmp_path, python)
    settings = spec(dtype, strategy)
    if dtype != "f64" or strategy != "fedavg":
        grant = service.approve(settings, str(UUID(int=10)), run_id=message["run_id"],
                                coordinator_id="a"*64, participant_id="b"*64, max_rounds=6)
        raw = model(settings)
        from suan.federation.updates import decode_arrays
        message.update(grant_id=grant.grant_id, spec_sha256=grant.spec_sha256,
                       model={"sha256": decode_arrays(raw)["sha256"], "bytes": len(raw)})
    receipt = execute(service, message, raw)
    task = finish(runtime[0], runtime[1], receipt["task_id"], timeout=60)
    assert task["state"] == "succeeded", task
    public = runtime[0].artifacts(task["id"])
    assert [item["path"] for item in public] == ["receipt.json"]
    assert runtime[0].files(task["spec"]["workspace_id"]) == []
    for name in ("data.bin", "model.bin", "delta.bin", "job.json", "result.json"):
        with pytest.raises(RuntimeErrorResponse):
            runtime[0].request("GET", f"tasks/{task['id']}/file?path={name}", binary=True)
    status = execute(service, message, raw, "status")
    assert status["state"] == "ready" and status["update_id"] and status["update"] is None
    published = []
    def publish(update_id, meta, payload):
        assert update_id == status["update_id"]
        published.append((meta, payload))
    delivered = execute(service, message, raw, "collect", publish)
    assert delivered["state"] == "delivered" and len(published) == 1
    assert delivered["update"]["num_examples"] == 4
    # Independent scalar per-example reference also checks actual ClientApp
    # serialization and the Runtime worker's delta, rather than just completion.
    import struct
    from suan.federation.updates import decode_arrays
    code = "f" if dtype == "f32" else "d"
    def rounded(value):
        return struct.unpack("<" + code, struct.pack("<" + code, value))[0]
    w0, b0 = rounded(.25), rounded(-.2)
    w, b = w0, b0
    xs, ys = [-1., 0., 1., 2.], [-3., -1., 1., 3.]
    for _ in range(settings["steps"]):
        errors = [w*x+b-y for x,y in zip(xs,ys)]
        gw = 2*sum(e*x for e,x in zip(errors,xs))/4 + settings["proximal_mu"]*(w-w0)
        gb = 2*sum(errors)/4 + settings["proximal_mu"]*(b-b0)
        w, b = rounded(w-.15*gw), rounded(b-.15*gb)
    actual = [struct.unpack("<"+code, array["data"])[0] for array in decode_arrays(published[0][1])["arrays"]]
    assert actual == pytest.approx([rounded(w-w0), rounded(b-b0)], rel=1e-6 if dtype == "f32" else 1e-14)
    assert execute(service, message, raw, "collect", publish) == delivered
    assert len(published) == 1
    assert execute(NodeFederationService(runtime[0], service.root, None), message, raw, "status")["update"] is None
    assert len(list((service.root / "jobs").glob("*/attempt.json"))) == 1


def test_status_detects_runtime_identity_drift_without_dispatch(runtime, tmp_path, monkeypatch):
    service, message, raw = prepare(runtime, tmp_path)
    started = execute(service, message, raw)
    original = runtime[0].task
    def drift(task_id):
        result = deepcopy(original(task_id))
        result["spec"]["argv"] = ["unrelated"]
        return result
    monkeypatch.setattr(runtime[0], "task", drift)
    with pytest.raises(NodeFederationError, match="differs"):
        execute(service, message, raw, "status")
    assert len(runtime[0].tasks()) == 1


@pytest.mark.parametrize("action", ["revoke", "cancel", "uncertain"])
def test_real_result_cannot_bypass_withdrawal_cancellation_or_uncertain_send(runtime, tmp_path, action):
    python = os.environ.get("STK_FEDERATION_TEST_PYTHON")
    if not python:
        pytest.skip("explicit installed Flower interpreter required")
    service, message, raw = prepare(runtime, tmp_path, python)
    started = execute(service, message, raw)
    assert finish(runtime[0], runtime[1], started["task_id"], timeout=60)["state"] == "succeeded"
    ready = execute(service, message, raw, "status")
    assert ready["state"] == "ready"
    calls = []
    def publisher(*args):
        calls.append(args)
        raise OSError("an uncertain network reply")
    if action == "revoke":
        service.consent.revoke(message["grant_id"])
    elif action == "cancel":
        execute(service, message, raw, "cancel")
    if action == "uncertain":
        assert execute(service, message, raw, "collect", publisher)["state"] == "uncertain"
        assert execute(service, message, raw, "collect", publisher)["state"] == "uncertain"
        assert len(calls) == 1
    else:
        with pytest.raises(NodeFederationError):
            execute(service, message, raw, "collect", publisher)
        assert not calls
    assert len(list((service.root / "jobs").glob("*/attempt.json"))) == 1


def test_real_queued_revocation_prevents_clientapp_start(runtime, tmp_path):
    python = os.environ.get("STK_FEDERATION_TEST_PYTHON")
    if not python:
        pytest.skip("explicit installed Flower interpreter required")
    service, message, raw = prepare(runtime, tmp_path, python)
    started = execute(service, message, raw)
    service.consent.revoke(message["grant_id"])
    assert finish(runtime[0], runtime[1], started["task_id"], timeout=60)["state"] == "failed"
    assert not list((service.root / "jobs").glob("*/attempt.json"))
    assert execute(service, message, raw, "status")["state"] == "failed"


def test_real_running_cancellation_stops_the_original_task(runtime, tmp_path):
    python = os.environ.get("STK_FEDERATION_TEST_PYTHON")
    if not python:
        pytest.skip("explicit installed Flower interpreter required")
    service, message, raw = prepare(runtime, tmp_path, python)
    settings = spec(steps=1000)
    identity = str(UUID(int=11))
    dataset = service.register_dataset(identity, [[float(i)/10000] for i in range(10000)], [[1.] for _ in range(10000)])
    grant = service.approve(settings, identity, run_id=message["run_id"], coordinator_id="a"*64,
                            participant_id="b"*64, max_rounds=6)
    message.update(grant_id=grant.grant_id, spec_sha256=grant.spec_sha256, dataset_sha256=dataset["dataset_sha256"])
    started = execute(service, message, raw)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not list((service.root / "jobs").glob("*/attempt.json")):
        runtime[1].tick()
        time.sleep(.02)
    assert list((service.root / "jobs").glob("*/attempt.json"))
    execute(service, message, raw, "cancel")
    assert finish(runtime[0], runtime[1], started["task_id"], timeout=15)["state"] == "cancelled"
    assert not list((service.root / "jobs").glob("*/result.json"))
