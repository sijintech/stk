"""Private project preparation and original owner intent recovery over the bridge."""
from copy import deepcopy
import hashlib
import json
import shutil
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from suan.agent import levels
from suan.desktop_bridge import schema
from suan.desktop_bridge.backends import RuntimeBackend
from suan.federation import inputs
from suan.federation.node import NodeFederationService
from suan.federation.owner import NodeOwnerService, OwnerRequestRejected
from suan.project import ProjectStore
from suan.project.store import DATABASE_NAME
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_federation_owner import owner_http, settings  # noqa: F401


def uid():
    return str(uuid4())


@pytest.fixture
def prepared(inproc, tmp_path, monkeypatch, request):
    h = inproc()
    directory = tmp_path.resolve() / "numeric-project"
    project = h.call("project.create", {"directory": str(directory), "name": "Private numeric test"})["project"]
    table, feature, target, *rows = [uid() for _ in range(6)]
    field_type = getattr(request, "param", "number")
    commands = [{"op": "create_table", "id": table, "name": "Measurements"},
                {"op": "add_field", "id": feature, "table_id": table, "name": "x", "type": field_type, "unit": "K"},
                {"op": "add_field", "id": target, "table_id": table, "name": "y", "type": field_type, "unit": "Pa"}]
    for index, row in enumerate(rows):
        commands.extend([{"op": "add_record", "id": row, "table_id": table},
                         {"op": "set_cell", "table_id": table, "record_id": row, "field_id": feature,
                          "value": (918273 if field_type == "integer" else 918273.125) + index},
                         {"op": "set_cell", "table_id": table, "record_id": row, "field_id": target,
                          "value": (12 if field_type == "integer" else 12.5) + index}])
    h.call("project.apply", {"handle": project["handle"], "expected_revision": 0, "commands": commands})
    params = {"handle": project["handle"], "expected_revision": 1, "plan_id": uid(),
              "training_dataset_id": uid(), "holdout_dataset_id": uid(), "table_id": table,
              "feature_ids": [feature], "target_ids": [target], "training_rows": rows[:2], "holdout_rows": rows[2:]}
    monkeypatch.setattr(ProjectStore, "snapshot", lambda *_a, **_k: pytest.fail("Federation read a whole-project snapshot"))
    owner = NodeOwnerService(NodeFederationService(None, tmp_path.resolve() / "node-private", None))
    calls = []
    client = SimpleNamespace(url="http://127.0.0.1:12345", connection_identity="test-runtime-owner")
    def owner_call(method, request):
        calls.append((method, deepcopy(request)))
        return owner.call(method, request)
    client.federation_owner = owner_call
    monkeypatch.setattr(h.bridge.connections, "backend", lambda connection, *a: RuntimeBackend(connection, client))
    return h, directory, params, owner, client, calls


def register_params(params, owner):
    info = owner.info()
    return {"handle": params["handle"], "expected_revision": params["expected_revision"],
            "plan_id": params["plan_id"], "connection": "runtime:owner", "operation_id": uid(),
            "owner_id": info["owner_id"], "expected_generation": info["generation"]}


def test_prepare_is_private_bounded_revision_read_and_reopen_is_passive(prepared, inproc):
    h, directory, params, owner, client, calls = prepared
    private = h.bridge.federation.root
    assert not private.exists()
    empty = h.call("project.federation.list", {"handle": params["handle"], "offset": 0, "limit": 20})
    assert empty["plans"] == [] and not private.exists() and calls == []
    before = (directory / DATABASE_NAME).read_bytes()
    card = h.call("project.federation.prepare", params)["plan"]
    assert card["source"]["revision"] == 1 and card["source"]["features"][0]["unit"] == "K"
    assert [item["manifest"]["num_examples"] for item in card["datasets"]] == [2, 1]
    assert h.call("project.federation.prepare", params)["plan"] == card
    assert h.call("project.federation.get", {"handle": params["handle"], "plan_id": card["plan_id"]}) == {"plan": card}
    assert calls == [] and owner.info()["generation"] == 0 and not owner.node.root.exists()
    encoded = json.dumps(card)
    assert "918273.125" not in encoded and str(private) not in encoded and '"x":' not in encoded
    assert (directory / DATABASE_NAME).read_bytes() == before
    assert not h.violations
    h.close()
    reopened = inproc()
    project = reopened.call("project.open", {"directory": str(directory)})["project"]
    again = reopened.call("project.federation.get", {"handle": project["handle"], "plan_id": card["plan_id"]})
    assert again == {"plan": card} and calls == [] and not owner.node.root.exists()
    assert not reopened.violations


@pytest.mark.parametrize("change", ["overlap", "duplicate_field", "foreign_row", "non_numeric", "wrong_revision"])
def test_invalid_selections_never_call_runtime_or_publish_a_plan(prepared, change):
    h, _, params, _, _, calls = prepared
    changed = deepcopy(params)
    if change == "overlap":
        changed["holdout_rows"] = params["training_rows"][:1]
    elif change == "duplicate_field":
        changed["target_ids"] = params["feature_ids"]
    elif change == "foreign_row":
        changed["holdout_rows"] = [uid()]
    elif change == "non_numeric":
        h.call("project.apply", {"handle": params["handle"], "expected_revision": 1,
                                 "commands": [{"op": "set_cell", "table_id": params["table_id"], "record_id": params["training_rows"][0],
                                               "field_id": params["feature_ids"][0], "value": None}]})
        changed["expected_revision"] = 2
    else:
        changed["expected_revision"] = 0
    error = h.error("project.federation.prepare", changed)
    assert error["code"] in {"invalid_params", "conflict"}
    assert calls == [] and list(h.bridge.federation.root.glob("plans/*.json")) == []
    assert not h.violations


def test_explicit_registration_original_intent_and_connection_binding(prepared):
    h, _, params, owner, client, calls = prepared
    card = h.call("project.federation.prepare", params)["plan"]
    request = register_params(params, owner)
    receipt = h.call("project.federation.register", request)
    assert receipt["state"] == "completed" and receipt["result"]["source_sha256"] == card["source_sha256"]
    assert [method for method, _ in calls] == ["datasets.register"]
    assert h.call("project.federation.register", request) == receipt and len(calls) == 1
    private_intent = h.bridge.federation._read("operations", request["operation_id"])
    assert receipt["request_sha256"] == hashlib.sha256(inputs.canonical(private_intent["params"])).hexdigest()
    local = h.call("federation.owner.operations.local", {"connection": request["connection"], "offset": 0, "limit": 50})
    assert local["operations"][0]["receipt"] == receipt and len(calls) == 1
    assert "918273.125" not in json.dumps(local) and '"request":' not in json.dumps(local)
    client.connection_identity = "replacement-runtime"
    assert h.error("federation.owner.operations.get", {"connection": request["connection"],
                   "operation_id": request["operation_id"]})["code"] == "conflict"
    assert len(calls) == 1 and not h.violations


def test_lost_registration_reply_never_resends_and_original_query_restores_receipt(prepared):
    h, _, params, owner, client, calls = prepared
    h.call("project.federation.prepare", params)
    request = register_params(params, owner)
    original = client.federation_owner
    def lost(method, data):
        original(method, data)
        raise OSError("Public test: lost reply after registration")
    client.federation_owner = lost
    error = h.error("project.federation.register", request)
    assert error["code"] == "unavailable" and error["retryable"] is False
    assert len(calls) == 1 and owner.info()["generation"] == 1
    client.federation_owner = original
    assert h.error("project.federation.register", request)["code"] == "conflict"
    assert len(calls) == 1
    observed = h.call("federation.owner.operations.get", {"connection": request["connection"],
                      "operation_id": request["operation_id"]})["operation"]
    assert observed["state"] == "completed" and len(calls) == 2
    assert h.call("project.federation.register", request) == observed and len(calls) == 2
    assert owner.call("datasets.list", {"offset": 0, "limit": 10})["total"] == 2
    assert not h.violations


def test_changed_project_and_hub_connection_cannot_register_old_plan(prepared):
    h, _, params, owner, _, calls = prepared
    h.call("project.federation.prepare", params)
    request = register_params(params, owner)
    assert h.error("project.federation.register", {**request, "connection": "hub:paired"})["code"] == "invalid_params"
    h.call("project.apply", {"handle": params["handle"], "expected_revision": 1,
                             "commands": [{"op": "rename_table", "id": params["table_id"], "name": "New name"}]})
    assert h.error("project.federation.register", {**request, "expected_revision": 2})["code"] == "conflict"
    assert calls == [] and owner.info()["generation"] == 0 and not h.violations


def test_all_owner_methods_are_closed_desktop_only_and_do_not_unlock_agent(prepared):
    h, _, params, _, _, _ = prepared
    names = {name for name in schema.method_names() if name.startswith(("project.federation.", "federation.owner."))}
    assert len(names) == 20
    assert names <= levels.DESKTOP_ONLY.keys()
    assert not names & h.bridge.script_catalog()["operations"].keys()
    assert not names & {operation for uses in levels.TOOL_USES.values() for operation in uses}
    assert schema.validate_params("project.federation.prepare", {**params, "root": "/private/raw"})
    assert not h.violations


def test_corrupt_private_values_are_rejected_by_get_list_and_registration(prepared):
    h, _, params, owner, _, calls = prepared
    h.call("project.federation.prepare", params)
    path = h.bridge.federation._path("plans", params["plan_id"])
    value = json.loads(path.read_text())
    value["registration"]["roles"]["training"]["x"][0][0] += 1
    path.write_bytes(inputs.canonical(value))
    assert h.error("project.federation.get", {"handle": params["handle"], "plan_id": params["plan_id"]})["code"] == "invalid_params"
    assert h.error("project.federation.list", {"handle": params["handle"], "offset": 0, "limit": 20})["code"] == "invalid_params"
    assert h.error("project.federation.register", register_params(params, owner))["code"] == "invalid_params"
    assert calls == [] and not h.violations


def test_invalid_remote_original_binding_is_not_cached_or_replayed(prepared):
    h, _, params, owner, client, calls = prepared
    h.call("project.federation.prepare", params)
    request = register_params(params, owner)
    original = client.federation_owner
    def forged(method, data):
        receipt = original(method, data)
        receipt["request_sha256"] = "a" * 64
        return receipt
    client.federation_owner = forged
    assert h.error("project.federation.register", request)["code"] == "invalid_params"
    assert not h.bridge.federation._exists("receipts", request["operation_id"])
    assert h.error("project.federation.register", request)["code"] == "conflict" and len(calls) == 1
    client.federation_owner = original
    receipt = h.call("federation.owner.operations.get", {"connection": request["connection"],
                     "operation_id": request["operation_id"]})["operation"]
    assert receipt["state"] == "completed" and len(calls) == 2 and not h.violations


def test_explicit_owner_approval_revoke_and_audit_preserve_original_grant(prepared):
    h, _, params, owner, _, calls = prepared
    card = h.call("project.federation.prepare", params)["plan"]
    h.call("project.federation.register", register_params(params, owner))
    spec = {"format": "stk.federation-training-spec/1", "trainer": "linear-regression/1",
            "features": [{"name": "x", "unit": "K"}], "targets": [{"name": "y", "unit": "Pa"}],
            "dtype": "f64", "normalization": "none", "steps": 2, "learning_rate": .01,
            "strategy": "fedavg", "proximal_mu": 0.0}
    manifest = card["datasets"][0]["manifest"]
    info = h.call("federation.owner.info", {"connection": "runtime:owner"})
    approve = {"connection": "runtime:owner", "operation_id": uid(), "owner_id": info["owner_id"],
               "expected_generation": info["generation"], "request": {
                   "dataset_id": manifest["dataset_id"], "dataset_sha256": manifest["dataset_sha256"],
                   "source_sha256": card["source_sha256"], "spec": spec, "run_id": uid(),
                   "coordinator_id": "a"*64, "participant_id": "b"*64, "max_rounds": 3}}
    granted = h.call("federation.owner.grants.approve", approve)
    assert granted["result"]["grant_id"] == approve["operation_id"] and granted["result"]["active"]
    revoke = {"connection": approve["connection"], "operation_id": uid(), "owner_id": info["owner_id"],
              "expected_generation": granted["generation"], "request": {"grant_id": approve["operation_id"]}}
    withdrawn = h.call("federation.owner.grants.revoke", revoke)
    assert not withdrawn["result"]["active"]
    count = len(calls)
    assert h.call("federation.owner.grants.approve", approve) == granted and len(calls) == count
    page = h.call("federation.owner.grants.list", {"connection": approve["connection"], "offset": 0, "limit": 50})
    assert page["total"] == 1 and page["items"][0]["active"] is False
    assert h.call("federation.owner.audit.list", {"connection": approve["connection"], "offset": 0, "limit": 50})["items"] == []
    assert not h.violations


@pytest.mark.parametrize("prepared", ["integer"], indirect=True)
def test_integer_columns_are_valid_numeric_sources(prepared):
    h, _, params, owner, _, calls = prepared
    card = h.call("project.federation.prepare", params)["plan"]
    receipt = h.call("project.federation.register", register_params(params, owner))
    assert receipt["state"] == "completed" and card["source"]["features"][0]["unit"] == "K"
    manifest, arrays = inputs.load(owner.node.root / "datasets" / params["training_dataset_id"])
    assert manifest["num_examples"] == 2 and len(calls) == 1 and not h.violations


def test_original_origin_is_required_before_a_new_recovery_intent(prepared):
    h, _, params, owner, client, calls = prepared
    h.call("project.federation.prepare", params)
    registered = register_params(params, owner)
    h.call("project.federation.register", registered)
    client.connection_identity = "another-runtime"
    request = {"connection": registered["connection"], "operation_id": uid(),
               "owner_id": owner.info()["owner_id"], "expected_generation": owner.info()["generation"],
               "request": {"operation_id": registered["operation_id"]}}
    error = h.error("federation.owner.operations.recover", request)
    assert error["code"] == "conflict" and len(calls) == 1
    assert not h.bridge.federation._exists("operations", request["operation_id"])
    assert not h.violations


def test_delayed_uncertain_query_cannot_replace_a_completed_owner_receipt(prepared):
    h, _, params, owner, client, _ = prepared
    h.call("project.federation.prepare", params)
    request = register_params(params, owner)
    completed = h.call("project.federation.register", request)
    client.federation_owner = lambda *_a: {**deepcopy(completed), "state": "uncertain", "result": None}
    observed = h.call("federation.owner.operations.get", {"connection": request["connection"],
                      "operation_id": request["operation_id"]})["operation"]
    assert observed == completed
    local = h.call("federation.owner.operations.local", {"connection": request["connection"], "offset": 0, "limit": 50})
    assert local["operations"][0]["receipt"] == completed and not h.violations


def test_private_intent_filename_and_embedded_operation_identity_must_match(prepared):
    h, _, params, owner, _, calls = prepared
    h.call("project.federation.prepare", params)
    request = register_params(params, owner)
    h.call("project.federation.register", request)
    path = h.bridge.federation._path("operations", request["operation_id"])
    changed = json.loads(path.read_text())
    changed["operation_id"] = changed["params"]["operation_id"] = uid()
    path.write_bytes(inputs.canonical(changed))
    assert h.error("federation.owner.operations.local", {"connection": request["connection"], "offset": 0, "limit": 50})["code"] == "invalid_params"
    assert h.error("federation.owner.operations.get", {"connection": request["connection"], "operation_id": request["operation_id"]})["code"] == "invalid_params"
    assert len(calls) == 1 and not h.violations


def test_frozen_selection_cannot_be_rebound_while_card_bytes_stay_unchanged(prepared):
    h, _, params, _, _, calls = prepared
    h.call("project.federation.prepare", params)
    path = h.bridge.federation._path("plans", params["plan_id"])
    changed = json.loads(path.read_text())
    changed["selection"]["table_id"] = uid()
    path.write_bytes(inputs.canonical(changed))
    assert h.error("project.federation.get", {"handle": params["handle"], "plan_id": params["plan_id"]})["code"] == "invalid_params"
    request = {**params, "table_id": changed["selection"]["table_id"]}
    assert h.error("project.federation.prepare", request)["code"] == "invalid_params"
    assert calls == [] and not h.violations


def test_damaged_private_read_quota_is_checked_before_json_loading(prepared, monkeypatch):
    h, _, params, _, _, _ = prepared
    h.call("project.federation.prepare", params)
    path = h.bridge.federation._path("plans", params["plan_id"])
    with path.open("wb") as stream:
        stream.truncate(64*1024*1024+1)
    monkeypatch.setattr(h.bridge.federation, "_read", lambda *_a: pytest.fail("Oversized state reached JSON loading"))
    assert h.error("project.federation.list", {"handle": params["handle"], "offset": 0, "limit": 20})["code"] == "invalid_params"
    assert not h.violations


def test_plan_list_cannot_redirect_a_corrupt_filename_to_another_valid_plan(prepared):
    h, _, params, _, _, _ = prepared
    h.call("project.federation.prepare", params)
    other = {**params, "plan_id": uid(), "training_dataset_id": uid(), "holdout_dataset_id": uid()}
    h.call("project.federation.prepare", other)
    path = h.bridge.federation._path("plans", params["plan_id"])
    changed = json.loads(path.read_text())
    changed["card"]["plan_id"] = other["plan_id"]
    path.write_bytes(inputs.canonical(changed))
    assert h.error("project.federation.list", {"handle": params["handle"], "offset": 0, "limit": 20})["code"] == "invalid_params"
    assert not h.violations


def test_absent_operation_is_an_object_wrapper_and_does_not_claim_rejection(prepared):
    h, _, _, owner, _, calls = prepared
    observed = h.call("federation.owner.operations.get", {
        "connection": "runtime:owner", "operation_id": uid()})
    assert observed == {"operation": None, "rejection": None}
    assert len(calls) == 1 and not owner.node.root.exists()
    assert not h.bridge.federation.root.exists() and not h.violations


def test_stale_owner_proof_survives_reopen_without_resending_the_rejected_request(prepared, inproc):
    h, _, params, owner, _, calls = prepared
    h.call("project.federation.prepare", params)
    request = {**register_params(params, owner), "expected_generation": 1}
    error = h.error("project.federation.register", request)
    proof = error["data"]["rejection"]
    intent = h.bridge.federation._read("operations", request["operation_id"])
    assert error["code"] == "conflict" and error["retryable"] is False
    assert proof["reason"] == "stale_owner" and proof["method"] == "datasets.register"
    assert proof["request_sha256"] == hashlib.sha256(inputs.canonical(intent["params"])).hexdigest()
    assert owner.operation(request["operation_id"]) is None and owner.info()["generation"] == 0
    assert h.error("project.federation.register", request)["data"]["rejection"] == proof
    assert len(calls) == 1
    observed = h.call("federation.owner.operations.get", {
        "connection": request["connection"], "operation_id": request["operation_id"]})
    assert observed == {"operation": None, "rejection": proof}
    assert "918273.125" not in json.dumps(observed)
    assert len(calls) == 2 and not h.violations
    h.close()
    reopened = inproc()
    local = reopened.call("federation.owner.operations.local", {
        "connection": request["connection"], "offset": 0, "limit": 50})["operations"]
    assert len(local) == 1 and local[0]["state"] == "rejected"
    assert local[0]["receipt"] is None and local[0]["rejection"] == proof and len(calls) == 2
    assert not reopened.violations


def test_semantic_rejection_does_not_reserve_operation_or_approve_unregistered_data(prepared):
    h, _, params, owner, _, calls = prepared
    request = {"connection": "runtime:owner", "operation_id": uid(), "owner_id": None,
               "expected_generation": 0, "request": {
                   "dataset_id": params["training_dataset_id"], "dataset_sha256": "a"*64,
                   "source_sha256": "b"*64, "spec": settings(), "run_id": uid(),
                   "coordinator_id": "c"*64, "participant_id": "d"*64, "max_rounds": 2}}
    proof = h.error("federation.owner.grants.approve", request)["data"]["rejection"]
    assert proof["reason"] == "invalid_request"
    assert owner.operation(request["operation_id"]) is None and owner.info()["generation"] == 0
    assert owner.call("grants.list", {"offset": 0, "limit": 10})["total"] == 0
    # A fresh explicit read and a NEW operation can still register the reviewed plan.
    h.call("project.federation.prepare", params)
    fresh = h.call("federation.owner.info", {"connection": request["connection"]})
    registered = h.call("project.federation.register", {
        **register_params(params, owner), "owner_id": fresh["owner_id"],
        "expected_generation": fresh["generation"]})
    assert registered["state"] == "completed" and registered["generation"] == 1
    assert len(calls) == 3 and not h.violations


@pytest.mark.parametrize("status", [400, 409])
def test_generic_runtime_errors_and_null_lookup_keep_original_intent_uncertain(prepared, status):
    from suan.runtime.client import RuntimeErrorResponse
    h, _, params, owner, client, calls = prepared
    h.call("project.federation.prepare", params)
    request = register_params(params, owner)
    def generic(method, data):
        calls.append((method, deepcopy(data)))
        raise RuntimeErrorResponse(status, "Public fixture: no bound rejection proof")
    client.federation_owner = generic
    error = h.error("project.federation.register", request)
    assert "rejection" not in error.get("data", {})
    assert h.error("project.federation.register", request)["code"] == "conflict" and len(calls) == 1
    client.federation_owner = lambda *_a: None
    assert h.call("federation.owner.operations.get", {
        "connection": request["connection"], "operation_id": request["operation_id"]}) == {
            "operation": None, "rejection": None}
    item = h.call("federation.owner.operations.local", {
        "connection": request["connection"], "offset": 0, "limit": 50})["operations"][0]
    assert item["state"] == "uncertain" and item["rejection"] is None and not h.violations


@pytest.mark.parametrize("damage", ["operation_id", "method", "request_sha256", "extra"])
def test_forged_rejection_proof_is_not_cached_or_used_to_unlock_an_intent(prepared, damage):
    h, _, params, owner, client, calls = prepared
    h.call("project.federation.prepare", params)
    request = {**register_params(params, owner), "expected_generation": 1}
    def forged(method, data):
        calls.append((method, deepcopy(data)))
        with pytest.raises(OwnerRequestRejected) as rejected:
            owner.call(method, data)
        proof = rejected.value.rejection
        proof[damage] = {"operation_id": uid(), "method": "grants.revoke",
                         "request_sha256": "a"*64, "extra": True}[damage]
        raise OwnerRequestRejected(proof)
    client.federation_owner = forged
    assert h.error("project.federation.register", request)["code"] == "invalid_params"
    assert not h.bridge.federation._exists("rejections", request["operation_id"])
    assert h.error("project.federation.register", request)["code"] == "conflict" and len(calls) == 1
    item = h.call("federation.owner.operations.local", {
        "connection": request["connection"], "offset": 0, "limit": 50})["operations"][0]
    assert item["state"] == "uncertain" and item["rejection"] is None and not h.violations


def test_post_reservation_failure_remains_uncertain_without_a_rejection(prepared, monkeypatch):
    h, _, params, owner, _, calls = prepared
    h.call("project.federation.prepare", params)
    request = register_params(params, owner)
    def failed(*_a):
        raise OSError("Public fixture: failure after durable reservation")
    monkeypatch.setattr(owner, "_execute", failed)
    receipt = h.call("project.federation.register", request)
    assert receipt["state"] == "uncertain" and receipt["result"] is None
    assert owner.info()["generation"] == 1 and owner.operation(request["operation_id"]) == receipt
    observed = h.call("federation.owner.operations.get", {
        "connection": request["connection"], "operation_id": request["operation_id"]})
    assert observed == {"operation": receipt, "rejection": None}
    assert h.call("project.federation.register", request) == receipt and len(calls) == 2
    assert not h.bridge.federation._exists("rejections", request["operation_id"])
    assert not h.violations


@pytest.mark.skipif(sys.platform != "linux", reason="The authenticated Runtime server is Linux-only")
def test_real_bridge_http_registration_evaluation_admission_and_separate_activation(prepared, owner_http, tmp_path, monkeypatch):
    """Synthetic candidate provenance fixture; real bridge/HTTP/owner/evaluation/registry."""
    from test_federation_evaluation import environment
    h, _, params, _, _, _ = prepared
    client, _server, config = owner_http
    monkeypatch.setattr(h.bridge.connections, "backend", lambda connection, *a: RuntimeBackend(connection, client))
    _, fixture_request, _, coordinator = environment(tmp_path.resolve() / "candidate-fixture", settings=settings(),
                                                    weights=1., bias=-918260.625)
    shutil.copytree(coordinator.root, config["federation_coordinator_root"])
    card = h.call("project.federation.prepare", params)["plan"]
    connection = "runtime:owner"
    def write(method, request):
        info = h.call("federation.owner.info", {"connection": connection})
        envelope = {"connection": connection, "operation_id": uid(), "owner_id": info["owner_id"],
                    "expected_generation": info["generation"], "request": request}
        return h.call("federation.owner." + method, envelope)
    info = h.call("federation.owner.info", {"connection": connection})
    rejected_id = uid()
    rejected = h.error("project.federation.register", {
        "handle": params["handle"], "expected_revision": 1, "plan_id": params["plan_id"], "connection": connection,
        "operation_id": rejected_id, "owner_id": info["owner_id"], "expected_generation": 1})
    assert rejected["data"]["rejection"]["reason"] == "stale_owner"
    observed = h.call("federation.owner.operations.get", {"connection": connection, "operation_id": rejected_id})
    assert observed == {"operation": None, "rejection": rejected["data"]["rejection"]}
    info = h.call("federation.owner.info", {"connection": connection})
    registered = h.call("project.federation.register", {
        "handle": params["handle"], "expected_revision": 1, "plan_id": params["plan_id"], "connection": connection,
        "operation_id": uid(), "owner_id": info["owner_id"], "expected_generation": info["generation"]})
    assert registered["state"] == "completed"
    candidate = h.call("federation.owner.candidates.get", {"connection": connection,
                       "run_id": fixture_request["run_id"], "round": 1})
    heldout = card["datasets"][1]["manifest"]
    request = {"evaluation_id": uid(), "run_id": candidate["run_id"], "round": candidate["round"],
               "dataset_id": heldout["dataset_id"], "dataset_sha256": heldout["dataset_sha256"],
               "candidate_sha256": candidate["model"]["sha256"], "base_model_sha256": candidate["base_model"]["sha256"],
               "spec_sha256": candidate["spec_sha256"], "thresholds": [{"name": "y", "unit": "Pa", "max_rmse": 0.}],
               "expected_active_version": None, "expected_active_generation": 0}
    frozen = write("evaluations.prepare", request)["result"]
    measured = write("evaluations.evaluate", {"evaluation_id": request["evaluation_id"], "plan_sha256": frozen["plan_sha256"]})["result"]
    assert measured["state"] == "passed" and measured["metrics"]["candidate"][0]["rmse"] == 0.
    admitted = write("models.admit", {"evaluation_id": request["evaluation_id"], "receipt_sha256": measured["receipt_sha256"],
                                    "expected_active_version": None, "expected_active_generation": 0})
    assert admitted["result"]["version"] == "v1" and admitted["result"]["active_generation"] == 0
    listing = {"connection": connection, "spec_sha256": candidate["spec_sha256"]}
    models = h.call("federation.owner.models.list", listing)
    assert models["active_version"] is None and models["generation"] == 0 and len(models["versions"]) == 1
    activated = write("models.activate", {"spec_sha256": candidate["spec_sha256"], "version": "v1",
                                          "expected_active_version": None, "expected_active_generation": 0})
    assert activated["result"]["generation"] == 1
    assert h.call("federation.owner.models.list", listing)["active_version"] == "v1"
    assert not h.violations
