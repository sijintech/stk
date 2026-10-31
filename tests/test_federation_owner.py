"""Owner-only producer, durable identities, recovery and authenticated HTTP."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import struct
import sys
import threading
from uuid import UUID
from urllib.error import HTTPError

import pytest

from suan.federation import inputs
from suan.federation.node import NodeFederationService
from suan.federation.owner import (NodeOwnerService, OwnerConflict, OwnerError,
                                   OwnerRequestRejected, decode_request, prepare_registration,
                                   validate_owner_rejection, validate_owner_result)
from suan.runtime.client import RuntimeClient, RuntimeErrorResponse
from suan.runtime.common import federation_owner_config, init_config
from suan.runtime.server import RuntimeHTTPServer


def uid(n):
    return str(UUID(int=n))


def registration(n=0):
    source = {"project_id": uid(1), "revision": 3, "table_id": uid(2),
              "features": [{"field_id": uid(3), "name": "x", "unit": "K"}],
              "targets": [{"field_id": uid(4), "name": "y", "unit": "Pa"}],
              "training_rows": [uid(10+n*10), uid(11+n*10)], "holdout_rows": [uid(12+n*10)]}
    return prepare_registration(source, {"dataset_id": uid(100+n*2), "x": [[1.], [2.]], "y": [[3.], [5.]]},
                                {"dataset_id": uid(101+n*2), "x": [[4.]], "y": [[9.]]})


def settings():
    return {"format": "stk.federation-training-spec/1", "trainer": "linear-regression/1",
            "features": [{"name": "x", "unit": "K"}], "targets": [{"name": "y", "unit": "Pa"}],
            "dtype": "f64", "normalization": "none", "steps": 2, "learning_rate": .01,
            "strategy": "fedavg", "proximal_mu": 0.0}


def linear_owner(tmp_path):
    """Real owner journal/capsules and registry, synthetic coordinator candidate."""
    from test_federation_evaluation import environment
    _, candidate_request, _, coordinator = environment(tmp_path / "fixture", settings=settings(),
                                                       weights=2., bias=1., xs=[[4.]], ys=[[9.]])
    service = NodeOwnerService(NodeFederationService(None, tmp_path / "owner-private", None),
                               coordinator_root=coordinator.root)
    numbers = iter(range(4000, 5000))
    def write(method, request):
        params = envelope(service, request, next(numbers))
        return service.call(method, params), params
    plan = registration()
    write("datasets.register", plan)
    manifest = plan["roles"]["holdout"]["manifest"]
    request = {**candidate_request, "dataset_id": manifest["dataset_id"],
               "dataset_sha256": manifest["dataset_sha256"],
               "thresholds": [{"name": "y", "unit": "Pa", "max_rmse": 0.}]}
    def evaluate(request):
        prepared, _ = write("evaluations.prepare", request)
        assert prepared["state"] == "completed"
        measured, _ = write("evaluations.evaluate", {"evaluation_id": request["evaluation_id"],
                                                     "plan_sha256": prepared["result"]["plan_sha256"]})
        assert measured["state"] == "completed" and measured["result"]["state"] == "passed"
        return {"evaluation_id": request["evaluation_id"],
                "receipt_sha256": measured["result"]["receipt_sha256"],
                "expected_active_version": request["expected_active_version"],
                "expected_active_generation": request["expected_active_generation"]}
    return service, request, write, evaluate


def envelope(service, request, n):
    info = service.info()
    return {"operation_id": uid(1000+n), "owner_id": info["owner_id"],
            "expected_generation": info["generation"], "request": request}


def approval(plan):
    manifest = plan["roles"]["training"]["manifest"]
    return {"dataset_id": manifest["dataset_id"], "dataset_sha256": manifest["dataset_sha256"],
            "source_sha256": plan["source_sha256"], "spec": settings(), "run_id": uid(200),
            "coordinator_id": "a"*64, "participant_id": "b"*64, "max_rounds": 3}


@pytest.fixture
def owner(tmp_path):
    node = NodeFederationService(None, tmp_path / "private", None)
    return NodeOwnerService(node)


def test_pure_producer_and_passive_reads_do_not_create_state(owner):
    before = owner.root.exists()
    plan = registration()
    assert plan["source_sha256"] == hashlib.sha256(inputs.canonical(plan["source"])).hexdigest()
    assert owner.info()["owner_id"] is None and owner.info()["generation"] == 0
    assert owner.call("datasets.list", {"offset": 0, "limit": 10})["items"] == []
    assert owner.call("grants.list", {"offset": 0, "limit": 10})["items"] == []
    assert owner.call("audit.list", {"offset": 0, "limit": 10})["items"] == []
    assert owner.call("operations.get", {"operation_id": uid(1000)}) is None
    assert not before and not owner.node.root.exists()


@pytest.mark.parametrize("change", ["rows", "fields", "units", "bytes", "extra"])
def test_registration_rejects_changed_plan_before_reservation(owner, change):
    plan = registration()
    if change == "rows":
        plan["source"]["holdout_rows"] = plan["source"]["training_rows"][:1]
    elif change == "fields":
        plan["source"]["targets"][0]["field_id"] = plan["source"]["features"][0]["field_id"]
    elif change == "units":
        plan["source"]["targets"][0]["unit"] = "K"
    elif change == "bytes":
        plan["roles"]["holdout"]["x"][0][0] += 1
    else:
        plan["path"] = "/private/raw"
    request = envelope(owner, plan, 1)
    with pytest.raises(OwnerRequestRejected) as failure:
        owner.call("datasets.register", request)
    rejection = validate_owner_rejection("datasets.register", request, failure.value.rejection)
    assert rejection["reason"] == "invalid_request" and rejection["generation"] == 0
    assert owner.info()["owner_id"] == rejection["owner_id"]
    assert owner.operation(request["operation_id"]) is None
    assert not (owner.node.root / "datasets").exists() and not (owner.node.root / "jobs").exists()


@pytest.mark.parametrize("value", [2**53+1, -(2**53+1)])
def test_project_integer_values_cannot_be_silently_rounded(value):
    original = registration()
    train = {k: original["roles"]["training"][k] for k in ("x", "y")}
    train["dataset_id"] = uid(100)
    train["x"][0][0] = value
    heldout = {k: original["roles"]["holdout"][k] for k in ("x", "y")}
    heldout["dataset_id"] = uid(101)
    with pytest.raises(OwnerError, match="exactly representable"):
        prepare_registration(original["source"], train, heldout)


def test_exact_large_project_integer_is_preserved_in_private_f64_bytes(owner):
    original = registration()
    train = {"dataset_id": uid(100), "x": [[2**60], [2.]], "y": [[3.], [5.]]}
    heldout = {"dataset_id": uid(101), "x": [[4.]], "y": [[9.]]}
    plan = prepare_registration(original["source"], train, heldout)
    receipt = owner.call("datasets.register", envelope(owner, plan, 1))
    assert receipt["state"] == "completed"
    from suan.federation.updates import decode_arrays
    _manifest, raw = inputs.load(owner.node.root / "datasets" / uid(100))
    actual = decode_arrays(raw)["arrays"][0]["data"]
    assert struct.unpack_from("<d", actual)[0] == 2**60


def test_registration_reopen_duplicate_cas_and_private_capsules(owner):
    plan = registration()
    request = envelope(owner, plan, 1)
    first = owner.call("datasets.register", request)
    assert first["state"] == "completed"
    assert first["request_sha256"] == hashlib.sha256(inputs.canonical(request)).hexdigest()
    assert set(first["result"]) == {"format", "source", "source_sha256", "datasets"}
    reopened = NodeOwnerService(NodeFederationService(None, owner.node.root, None))
    assert reopened.call("datasets.register", request) == first
    assert reopened.info()["generation"] == 1
    page = reopened.call("datasets.list", {"offset": 0, "limit": 10})
    assert page["total"] == 2 and page["next_offset"] is None
    for role in ("training", "holdout"):
        expected = plan["roles"][role]["manifest"]
        assert inputs.load(owner.node.root / "datasets" / expected["dataset_id"])[0] == expected
    changed = deepcopy(request)
    changed["request"] = registration(1)
    with pytest.raises(OwnerConflict):
        reopened.call("datasets.register", changed)
    stale = {**request, "operation_id": uid(1002)}
    with pytest.raises(OwnerRequestRejected) as failure:
        reopened.call("datasets.register", stale)
    assert failure.value.rejection["reason"] == "stale_owner"
    assert reopened.operation(stale["operation_id"]) is None


def test_pre_reservation_rejection_is_bound_and_old_identity_lookup_precedes_validation(owner, monkeypatch):
    request = envelope(owner, registration(), 1)
    first = owner.call("datasets.register", request)
    def invalid(*_):
        raise ValueError("A semantic validator has no side effects")
    monkeypatch.setattr(owner, "_validate", invalid)
    assert owner.call("datasets.register", request) == first
    changed = deepcopy(request)
    changed["request"] = {"invalid": True}
    with pytest.raises(OwnerConflict):
        owner.call("datasets.register", changed)
    stale = {**request, "operation_id": uid(1002)}
    with pytest.raises(OwnerRequestRejected) as rejected:
        owner.call("datasets.register", stale)
    proof = validate_owner_rejection("datasets.register", stale, rejected.value.rejection)
    assert set(proof) == {"format", "operation_id", "method", "request_sha256", "owner_id", "generation", "reason"}
    assert proof["reason"] == "stale_owner" and proof["generation"] == 1
    assert owner.operation(stale["operation_id"]) is None
    for field, value in (("operation_id", uid(888)), ("method", "models.activate"),
                         ("request_sha256", "f"*64), ("owner_id", None),
                         ("generation", True), ("reason", "any_http_error"), ("path", "/private")):
        bad = {**proof, field: value}
        with pytest.raises(OwnerError):
            validate_owner_rejection("datasets.register", stale, bad)


def test_post_reservation_validation_failure_never_claims_zero_effect(owner, monkeypatch):
    request = envelope(owner, registration(), 1)
    def interrupted(*_):
        raise ValueError("Failure after the durable reservation")
    monkeypatch.setattr(owner, "_execute", interrupted)
    result = owner.call("datasets.register", request)
    assert result["state"] == "uncertain" and result["result"] is None
    assert owner.operation(request["operation_id"]) == result
    assert owner.info()["generation"] == 1


@pytest.mark.parametrize("method", ["evaluations.prepare", "models.admit", "models.activate"])
@pytest.mark.parametrize("stale", ["version", "generation", "aba"])
def test_known_linear_cas_refusal_precedes_owner_reservation_and_allows_reviewed_new_action(tmp_path, method, stale):
    service, request, write, evaluate = linear_owner(tmp_path)
    admitted, _ = write("models.admit", evaluate(request))
    spec_sha = request["spec_sha256"]
    activation = {"spec_sha256": spec_sha, "version": admitted["result"]["version"],
                  "expected_active_version": None, "expected_active_generation": 0}
    original_activation, original_params = write("models.activate", activation)
    current_request = {**request, "evaluation_id": uid(6001),
                       "expected_active_version": "v1", "expected_active_generation": 1}
    pending_admission = evaluate(current_request)
    if stale == "aba":
        # Return to the same version after an intervening activation: UUID and
        # pointer equality alone must not authorize the old baseline.
        second_request = {**current_request, "evaluation_id": uid(6002)}
        second, _ = write("models.admit", evaluate(second_request))
        write("models.activate", {**activation, "version": second["result"]["version"],
                                  "expected_active_version": "v1", "expected_active_generation": 1})
        write("models.activate", {**activation, "expected_active_version": "v2", "expected_active_generation": 2})
    if method == "evaluations.prepare":
        refused_request = {**current_request, "evaluation_id": uid(6003)}
    elif method == "models.admit":
        refused_request = pending_admission
    else:
        refused_request = {**activation, "expected_active_version": "v1", "expected_active_generation": 1}
    if stale == "version":
        refused_request = {**refused_request, "expected_active_version": None}
    elif stale == "generation":
        refused_request = {**refused_request, "expected_active_generation": 0}
    before = service.info()
    models_before = service.call("models.list", {"spec_sha256": spec_sha})
    params = envelope(service, refused_request, 7000)
    with pytest.raises(OwnerRequestRejected) as rejected:
        service.call(method, params)
    proof = validate_owner_rejection(method, params, rejected.value.rejection)
    assert proof["reason"] == "invalid_request" and proof["generation"] == before["generation"]
    assert service.operation(params["operation_id"]) is None and service.info() == before
    assert not service._linear()._operation_path(params["operation_id"]).exists()
    assert service.call("models.list", {"spec_sha256": spec_sha}) == models_before
    # Historical accepted originals still return before preflight, without
    # changing the active pointer, even after its baseline has become stale.
    assert service.call("models.activate", original_params) == original_activation
    assert service.call("models.list", {"spec_sha256": spec_sha}) == models_before
    fresh = service.call("models.list", {"spec_sha256": spec_sha})
    reviewed = {"expected_active_version": fresh["active_version"], "expected_active_generation": fresh["generation"]}
    if method == "evaluations.prepare":
        corrected = {**refused_request, **reviewed, "evaluation_id": uid(6004)}
    elif method == "models.admit":
        # A changed baseline requires a newly frozen evaluation, not changing
        # the original evaluation's CAS fields to force its admission.
        corrected = evaluate({**current_request, **reviewed, "evaluation_id": uid(6004)})
    else:
        corrected = {**refused_request, **reviewed}
    accepted, new_params = write(method, corrected)
    assert new_params["operation_id"] != params["operation_id"]
    assert accepted["state"] == "completed" and service.operation(params["operation_id"]) is None


def test_linear_preflight_does_not_create_state_for_an_absent_registry(tmp_path):
    service, request, write, _ = linear_owner(tmp_path)
    root = service._linear().root
    assert not root.exists()
    before = service.info()
    params = envelope(service, {**request, "candidate_sha256": "f"*64}, 7000)
    with pytest.raises(OwnerRequestRejected) as rejected:
        service.call("evaluations.prepare", params)
    assert rejected.value.rejection["reason"] == "invalid_request"
    assert service.info() == before and service.operation(params["operation_id"]) is None
    assert not root.exists()
    accepted, _ = write("evaluations.prepare", request)
    assert accepted["state"] == "completed" and root.exists()


def test_linear_change_after_preflight_remains_uncertain_without_a_rejection(tmp_path, monkeypatch):
    service, request, write, evaluate = linear_owner(tmp_path)
    admitted, _ = write("models.admit", evaluate(request))
    activation = {"spec_sha256": request["spec_sha256"], "version": admitted["result"]["version"],
                  "expected_active_version": None, "expected_active_generation": 0}
    registry = service._linear()
    original = registry.preflight
    def race(method, value):
        original(method, value)
        # Another trusted writer takes the same baseline after preflight has
        # released its lease. It is not evidence about the later outer intent.
        registry.execute("models.activate", value, uid(9000))
    monkeypatch.setattr(registry, "preflight", race)
    before = service.info()
    receipt, params = write("models.activate", activation)
    assert receipt["state"] == "uncertain" and receipt["result"] is None
    assert service.info()["generation"] == before["generation"] + 1
    assert service.operation(params["operation_id"]) == receipt
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]})["generation"] == 1
    assert registry._operation(params["operation_id"])["state"] == "intent"


def test_partial_registration_only_explicit_recovery_fills_missing_publication(owner, monkeypatch):
    plan = registration()
    request = envelope(owner, plan, 1)
    target_id = plan["roles"]["holdout"]["manifest"]["dataset_id"]
    original = inputs.write_json
    def stop_manifest(path, *args, **kwargs):
        if Path(path).parent.name == target_id:
            raise OSError("private dataset path must never appear in a receipt")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(inputs, "write_json", stop_manifest)
    first = owner.call("datasets.register", request)
    assert first["state"] == "uncertain" and first["result"] is None
    assert owner.call("datasets.list", {"offset": 0, "limit": 10})["total"] == 0
    monkeypatch.setattr(inputs, "write_json", original)
    reopened = NodeOwnerService(NodeFederationService(None, owner.node.root, None))
    assert reopened.call("datasets.register", request) == first
    assert not (owner.node.root / "datasets" / target_id / "manifest.json").exists()
    assert reopened.call("operations.get", {"operation_id": request["operation_id"]}) == first
    recover = envelope(reopened, {"operation_id": request["operation_id"]}, 2)
    receipt = reopened.call("operations.recover", recover)
    assert receipt["state"] == "completed"
    assert receipt["result"]["operation"]["state"] == "completed"
    assert reopened.call("datasets.list", {"offset": 0, "limit": 10})["total"] == 2
    assert list((owner.node.root / "jobs").iterdir()) == []


def test_grant_lost_reply_recovery_and_withdrawal_do_not_duplicate_or_reactivate(owner, monkeypatch):
    plan = registration()
    owner.call("datasets.register", envelope(owner, plan, 1))
    approve = envelope(owner, approval(plan), 2)
    original = owner.node.approve
    def committed_then_lost(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("lost owner reply")
    monkeypatch.setattr(owner.node, "approve", committed_then_lost)
    first = owner.call("grants.approve", approve)
    assert first["state"] == "uncertain"
    monkeypatch.setattr(owner.node, "approve", lambda *_a, **_k: pytest.fail("approval replayed"))
    assert owner.call("grants.approve", approve) == first
    recovery = owner.call("operations.recover", envelope(owner, {"operation_id": approve["operation_id"]}, 3))
    assert recovery["result"]["operation"]["state"] == "completed"
    assert "result" not in recovery["result"]["operation"]
    assert owner.operation(approve["operation_id"])["result"]["grant_id"] == approve["operation_id"]
    revoked = owner.call("grants.revoke", envelope(owner, {"grant_id": approve["operation_id"]}, 4))
    assert revoked["state"] == "completed" and revoked["result"]["active"] is False
    assert owner.node.consent.list_grants()["total"] == 1
    again = original(approval(plan)["spec"], approval(plan)["dataset_id"], grant_id=approve["operation_id"],
                     **{k: approval(plan)[k] for k in ("run_id", "coordinator_id", "participant_id", "max_rounds")})
    assert again.active is False and owner.node.consent.list_grants()["total"] == 1


def test_approval_must_bind_registered_training_role_and_exact_units(owner):
    plan = registration()
    owner.call("datasets.register", envelope(owner, plan, 1))
    for change in ("unit", "role", "source"):
        value = approval(plan)
        if change == "unit":
            value["spec"]["features"][0]["unit"] = "unspecified"
        elif change == "role":
            value["dataset_id"] = plan["roles"]["holdout"]["manifest"]["dataset_id"]
            value["dataset_sha256"] = plan["roles"]["holdout"]["manifest"]["dataset_sha256"]
        else:
            value["source_sha256"] = "f"*64
        with pytest.raises(OwnerError):
            owner.call("grants.approve", envelope(owner, value, 2))
    assert owner.node.consent.list_grants()["total"] == 0


def test_registration_raw_quota_is_shared_with_node_writers(owner, monkeypatch):
    raw_size = registration()["roles"]["training"]["manifest"]["bytes"]
    monkeypatch.setattr(inputs, "MAX_PRIVATE_BYTES", raw_size*2)
    request = envelope(owner, registration(), 1)
    result = owner.call("datasets.register", request)
    assert result["state"] == "completed"
    next_request = envelope(owner, registration(1), 2)
    assert owner.call("datasets.register", next_request)["state"] == "uncertain"
    total = sum(p.stat().st_size for p in (owner.node.root / "datasets").rglob("*.bin"))
    assert total <= raw_size*2


def test_concurrent_direct_node_writer_and_owner_share_raw_budget(owner, monkeypatch):
    plan = registration()
    limit = sum(item["manifest"]["bytes"] for item in plan["roles"].values())
    monkeypatch.setattr(inputs, "MAX_PRIVATE_BYTES", limit)
    request = envelope(owner, plan, 1)
    def register_direct():
        try:
            return owner.node.register_dataset(uid(500), [[8.], [9.]], [[1.], [2.]])
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        direct = pool.submit(register_direct)
        result = pool.submit(owner.call, "datasets.register", request)
        direct.result(), result.result()
    total = sum(path.stat().st_size for path in (owner.node.root / "datasets").rglob("*.bin"))
    assert total <= limit


def test_actual_process_crash_after_capsules_before_receipt_is_only_recovered_explicitly(owner, tmp_path):
    plan = registration()
    request = envelope(owner, plan, 1)
    request_path = tmp_path / "frozen-request.json"
    request_path.write_bytes(inputs.canonical(request))
    script = '''import json,os,sys
from suan.federation.node import NodeFederationService
from suan.federation.owner import NodeOwnerService
owner=NodeOwnerService(NodeFederationService(None,sys.argv[1],None))
def interrupted(*args): os._exit(73)
owner._complete=interrupted
owner.call("datasets.register",json.load(open(sys.argv[2])))
'''
    env = {**os.environ, "STK_TOKEN_PLAN_API_KEY": ""}
    env.pop("STK_TOKEN_PLAN_MODEL", None)
    completed = subprocess.run([sys.executable, "-c", script, str(owner.node.root), str(request_path)], env=env,
                               capture_output=True, timeout=15)
    assert completed.returncode == 73
    reopened = NodeOwnerService(NodeFederationService(None, owner.node.root, None))
    retained = reopened.call("operations.get", {"operation_id": request["operation_id"]})
    assert retained["state"] == "uncertain" and retained["result"] is None
    assert reopened.call("datasets.register", request) == retained
    recovered = reopened.call("operations.recover", envelope(reopened, {"operation_id": request["operation_id"]}, 2))
    assert recovered["result"]["operation"]["state"] == "completed"
    assert reopened.call("datasets.list", {"offset": 0, "limit": 10})["total"] == 2


def test_recovery_of_recovery_is_flat_and_never_expands_original_receipts(owner):
    first = owner.call("datasets.register", envelope(owner, registration(), 1))
    for n in range(2, 8):
        request = envelope(owner, {"operation_id": first["operation_id"]}, n)
        first = owner.call("operations.recover", request)
        assert first["state"] == "completed"
        validate_owner_result("operations.recover", request, first)
        assert set(first["result"]["operation"]) == {"owner_id", "generation", "operation_id", "method", "request_sha256", "state"}
        assert len(inputs.canonical(first)) < 1100


def test_client_result_validator_rejects_foreign_ids_hash_generation_and_private_extras(owner):
    request = envelope(owner, registration(), 1)
    result = owner.call("datasets.register", request)
    assert validate_owner_result("datasets.register", request, result) == result
    for key, value in (("operation_id", uid(999)), ("request_sha256", "f"*64), ("generation", 9), ("path", "/private/owner")):
        changed = deepcopy(result)
        changed[key] = value
        with pytest.raises(ValueError):
            validate_owner_result("datasets.register", request, changed)


def test_get_validator_binds_approval_uuid_even_without_original_request(owner):
    plan = registration()
    owner.call("datasets.register", envelope(owner, plan, 1))
    request = envelope(owner, approval(plan), 2)
    granted = owner.call("grants.approve", request)
    changed = deepcopy(granted)
    changed["result"]["grant_id"] = uid(999)
    with pytest.raises(OwnerError):
        validate_owner_result("operations.get", {"operation_id": request["operation_id"]}, changed)


def test_corrupt_oversize_registration_descriptor_is_rejected_bounded(owner):
    plan = registration()
    owner.call("datasets.register", envelope(owner, plan, 1))
    with owner._connect(write=True) as db:
        db.execute("UPDATE datasets SET descriptor=zeroblob(?)", (inputs.MAX_METADATA_BYTES+1,))
    with pytest.raises(OwnerError, match="damaged"):
        owner.dataset(plan["roles"]["training"]["manifest"]["dataset_id"])
    retried = owner.call("datasets.register", envelope(owner, plan, 2))
    assert retried["state"] == "uncertain"  # old data/source identities are never replaced


def test_strict_owner_decoder_rejects_duplicates_nonfinite_and_nested_input():
    for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e400}', b'[]', b'{"x":"\\ud800"}',
                b'{"x":'+b'['*65+b'0'+b']'*65+b'}'):
        with pytest.raises(ValueError):
            decode_request(raw)


@pytest.fixture
def owner_http(tmp_path):
    if not sys.platform.startswith("linux"):
        pytest.skip("Authenticated owner HTTP service runs on Linux; this platform is client-only")
    config = init_config(tmp_path / "runtime", port=0, federation_node_root=tmp_path / "node" / "federation",
                         federation_coordinator_root=tmp_path / "coordinator")
    config["token"] = "abcdefghijklmnopqrstuvwx"
    server = RuntimeHTTPServer(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = RuntimeClient(f"http://127.0.0.1:{server.server_port}", config["token"])
    yield client, server, config
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


def test_authenticated_http_fixed_root_is_actual_node_registry(owner_http, tmp_path):
    client, server, config = owner_http
    root = Path(config["federation_node_root"])
    assert "federation_owner" in client.health()["features"] and not root.exists()
    info = client.federation_owner("info", {})
    assert info["owner_id"] is None and not root.exists()
    plan = registration()
    request = {"operation_id": uid(1001), "owner_id": None, "expected_generation": 0, "request": plan}
    first = client.federation_owner("datasets.register", request)
    assert first["state"] == "completed"
    node = NodeFederationService(client, root, None, workspace_root=config["workspace_root"])
    same_owner = NodeOwnerService(node)
    grant = client.federation_owner("grants.approve", envelope(same_owner, approval(plan), 2))
    assert node.consent.get_grant(grant["operation_id"]).as_dict() == grant["result"]
    assert client.tasks() == [] and client.workspaces() == []
    assert not list(Path(config["workspace_root"]).rglob("*.bin"))
    for body in (b'{"owner_id":null,"owner_id":"different"}', b'{"root":"/private/model"}', b'{"x":1e400}'):
        with pytest.raises(RuntimeErrorResponse) as error:
            client.request("POST", "federation/owner/info", body)
        assert error.value.status == 400 and "/private/" not in str(error.value)
    with pytest.raises(RuntimeErrorResponse) as error:
        RuntimeClient(client.url, "incorrect").federation_owner("info", {})
    assert error.value.status == 401


def test_http_stale_owner_returns_only_a_verified_pre_reservation_rejection(owner_http):
    client, server, _config = owner_http
    owner = server.service.federation_owner
    original = envelope(owner, registration(), 1)
    client.federation_owner("datasets.register", original)
    stale = {**original, "operation_id": uid(1002), "request": registration(1)}
    with pytest.raises(OwnerRequestRejected) as failure:
        client.federation_owner("datasets.register", stale)
    proof = validate_owner_rejection("datasets.register", stale, failure.value.rejection)
    assert proof["reason"] == "stale_owner" and proof["generation"] == 1
    assert client.federation_owner("operations.get", {"operation_id": stale["operation_id"]}) is None
    assert owner.info()["generation"] == 1 and owner.node.consent.list_grants()["total"] == 0
    assert client.federation_owner("datasets.list", {"offset": 0, "limit": 10})["total"] == 2
    invalid = envelope(owner, {"unexpected": "/private/path"}, 3)
    with pytest.raises(OwnerRequestRejected) as failure:
        client.federation_owner("datasets.register", invalid)
    assert failure.value.rejection["reason"] == "invalid_request"
    assert b"/private/" not in inputs.canonical(failure.value.rejection)
    assert owner.operation(invalid["operation_id"]) is None


def test_http_existing_id_conflict_and_failure_after_effects_do_not_claim_rejection(owner_http, monkeypatch):
    client, server, _config = owner_http
    owner = server.service.federation_owner
    request = envelope(owner, registration(), 1)
    accepted = client.federation_owner("datasets.register", request)
    conflict = {**request, "request": registration(1)}
    with pytest.raises(RuntimeErrorResponse) as failure:
        client.federation_owner("datasets.register", conflict)
    assert failure.value.status == 409 and set(failure.value.body) == {"error"}
    query = owner.operation
    def fail_final_lookup(_):
        raise OwnerError("A final lookup error does not undo published capsules")
    next_request = envelope(owner, registration(1), 2)
    monkeypatch.setattr(owner, "operation", fail_final_lookup)
    with pytest.raises(RuntimeErrorResponse) as failure:
        client.federation_owner("datasets.register", next_request)
    assert failure.value.status == 400 and set(failure.value.body) == {"error"}
    monkeypatch.setattr(owner, "operation", query)
    assert query(next_request["operation_id"])["state"] == "completed"
    assert owner.call("datasets.list", {"offset": 0, "limit": 10})["total"] == 4
    assert owner.operation(request["operation_id"]) == accepted


@pytest.mark.parametrize("change", ["foreign_id", "foreign_hash", "extra_field", "wrong_status", "duplicate_key"])
def test_client_does_not_trust_unbound_or_malformed_http_rejection(owner, monkeypatch, change):
    request = envelope(owner, {"invalid": True}, 1)
    with pytest.raises(OwnerRequestRejected) as failure:
        owner.call("datasets.register", request)
    proof = failure.value.rejection
    if change == "foreign_id":
        proof["operation_id"] = uid(777)
    elif change == "foreign_hash":
        proof["request_sha256"] = "f"*64
    elif change == "extra_field":
        proof["path"] = "/private/path"
    document = {"error": "Public test rejection", "rejection": proof}
    raw = inputs.canonical(document)
    if change == "duplicate_key":
        raw = raw.replace(b'"generation":0', b'"generation":1,"generation":0')
    calls = []
    class Opener:
        def open(self, transport_request, **_kwargs):
            calls.append(1)
            raise HTTPError(transport_request.full_url, 400 if change == "wrong_status" else 409,
                            "public fixture", {}, io.BytesIO(raw))
    monkeypatch.setattr("suan.runtime.client.build_opener", lambda *_a: Opener())
    client = RuntimeClient("http://127.0.0.1:8765", "abcdefghijklmnopqrstuvwx")
    with pytest.raises(RuntimeErrorResponse):
        client.federation_owner("datasets.register", request)
    assert len(calls) == 1


def test_actual_http_lost_reply_only_queries_the_retained_original(owner_http, monkeypatch):
    client, server, _config = owner_http
    owner = server.service.federation_owner
    request = envelope(owner, registration(), 1)
    original = owner.call
    def lost_after_commit(method, params):
        result = original(method, params)
        if method == "datasets.register":
            raise BrokenPipeError("disconnected after private commit")
        return result
    monkeypatch.setattr(owner, "call", lost_after_commit)
    with pytest.raises(OSError):
        client.federation_owner("datasets.register", request)
    monkeypatch.setattr(owner, "call", original)
    receipt = client.federation_owner("operations.get", {"operation_id": request["operation_id"]})
    assert receipt["state"] == "completed" and receipt["generation"] == 1
    assert client.federation_owner("info", {})["generation"] == 1
    assert client.federation_owner("datasets.list", {"offset": 0, "limit": 10})["total"] == 2


def test_http_registration_evaluation_explicit_admission_rollback_and_old_receipt(owner_http, tmp_path):
    """Synthetic coordinator fixture; actual authenticated owner/registry routes."""
    from test_federation_evaluation import environment
    client, _server, config = owner_http
    _registry, _request, _registered, coordinator = environment(tmp_path / "fixture", settings=settings(),
                                                               weights=2., bias=1., xs=[[4.]], ys=[[9.]])
    shutil.copytree(coordinator.root, config["federation_coordinator_root"])
    def write(method, request, number):
        info = client.federation_owner("info", {})
        params = {"operation_id": uid(2000+number), "owner_id": info["owner_id"],
                  "expected_generation": info["generation"], "request": request}
        return client.federation_owner(method, params), params
    plan = registration()
    registered, _ = write("datasets.register", plan, 1)
    assert registered["state"] == "completed"
    run_id = _request["run_id"]
    candidate = client.federation_owner("candidates.get", {"run_id": run_id, "round": 1})
    capsule = plan["roles"]["holdout"]["manifest"]
    prepare = {"evaluation_id": uid(2200), "run_id": run_id, "round": 1,
               "dataset_id": capsule["dataset_id"], "dataset_sha256": capsule["dataset_sha256"],
               "candidate_sha256": candidate["model"]["sha256"], "base_model_sha256": candidate["base_model"]["sha256"],
               "spec_sha256": candidate["spec_sha256"], "thresholds": [{"name": "y", "unit": "Pa", "max_rmse": 0.}],
               "expected_active_version": None, "expected_active_generation": 0}
    prepared, _ = write("evaluations.prepare", prepare, 2)
    assert prepared["state"] == "completed", prepared
    evaluate = {"evaluation_id": prepare["evaluation_id"], "plan_sha256": prepared["result"]["plan_sha256"]}
    measured, _ = write("evaluations.evaluate", evaluate, 3)
    assert measured["state"] == "completed" and measured["result"]["state"] == "passed"
    listing = {"spec_sha256": candidate["spec_sha256"]}
    assert client.federation_owner("models.list", listing)["active_version"] is None
    admit = {"evaluation_id": prepare["evaluation_id"], "receipt_sha256": measured["result"]["receipt_sha256"],
             "expected_active_version": None, "expected_active_generation": 0}
    accepted, _ = write("models.admit", admit, 4)
    assert accepted["state"] == "completed" and accepted["result"]["version"] == "v1"
    assert accepted["result"]["active_generation"] == 0
    assert client.federation_owner("models.list", listing)["active_version"] is None
    activated, _ = write("models.activate", {**listing, "version": "v1", "expected_active_version": None, "expected_active_generation": 0}, 5)
    assert activated["state"] == "completed" and activated["result"]["generation"] == 1
    prepare.update(evaluation_id=uid(2201), expected_active_version="v1", expected_active_generation=1)
    prepared, _ = write("evaluations.prepare", prepare, 6)
    measured, _ = write("evaluations.evaluate", {"evaluation_id": uid(2201), "plan_sha256": prepared["result"]["plan_sha256"]}, 7)
    admit.update(evaluation_id=uid(2201), receipt_sha256=measured["result"]["receipt_sha256"],
                 expected_active_version="v1", expected_active_generation=1)
    second, original = write("models.admit", admit, 8)
    assert second["state"] == "completed" and second["result"]["version"] == "v2"
    assert second["result"]["active_generation"] == 1
    assert client.federation_owner("models.list", listing)["active_version"] == "v1"
    activated, _ = write("models.activate", {**listing, "version": "v2", "expected_active_version": "v1", "expected_active_generation": 1}, 9)
    assert activated["state"] == "completed" and activated["result"]["generation"] == 2
    rolled, _ = write("models.activate", {**listing, "version": "v1", "expected_active_version": "v2", "expected_active_generation": 2}, 10)
    assert rolled["state"] == "completed" and rolled["result"]["generation"] == 3
    assert client.federation_owner("models.admit", original) == second
    current = client.federation_owner("models.list", listing)
    assert current["active_version"] == "v1" and current["generation"] == 3 and len(current["versions"]) == 2
    wire = inputs.canonical(current)
    assert str(tmp_path).encode() not in wire and b'"x":' not in wire and b'"data":' not in wire
    assert client.tasks() == [] and client.workspaces() == []


def test_feature_is_opt_in_and_fixed_roots_cannot_overlap(runtime, tmp_path):
    client, _supervisor, _server, config = runtime
    assert "federation_owner" not in client.health()["features"]
    with pytest.raises(RuntimeErrorResponse) as error:
        client.federation_owner("info", {})
    assert error.value.status == 404
    for root in (config["workspace_root"], str(Path(config["workspace_root"]) / "private"), str(Path(config["workspace_root"]).parent)):
        with pytest.raises(ValueError):
            federation_owner_config({**config, "federation_node_root": root})
    with pytest.raises(ValueError):
        federation_owner_config({**config, "federation_node_root": "relative"})
