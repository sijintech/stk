"""Actual owner withdrawal, durable intents and independently reopened audits."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import threading
from uuid import uuid4

import pytest

from suan.federation.consent import (
    ConsentConflict, ConsentDenied, ConsentError, ConsentOutcomeUncertain,
    ConsentQuota, ConsentRegistry,
)
from suan.federation.updates import FederationValidationError, decode_arrays, encode_arrays


COORDINATOR = "a" * 64
PARTICIPANT = "b" * 64
DATASET = "c" * 64
SPEC = "d" * 64
MODEL = "e" * 64


def create(root, *, rounds=3, max_audit_bytes=512 * 1024 * 1024, model_layout=None):
    store = ConsentRegistry(root, max_audit_bytes=max_audit_bytes)
    grant = store.grant(str(uuid4()), coordinator_id=COORDINATOR,
                        participant_id=PARTICIPANT, dataset_id=str(uuid4()),
                        dataset_sha256=DATASET, spec_sha256=SPEC,
                        model_layout=([{"name": "weight", "dtype": "f64", "shape": [2]}]
                                      if model_layout is None else model_layout), max_rounds=rounds)
    return store, grant


def update(grant, *, round=1, values=(1.25, -2.5), kind="delta", array_name="weight", metric_name="loss"):
    payload = encode_arrays([{"name": array_name, "dtype": "f64", "shape": [len(values)],
                              "data": struct.pack("<" + "d" * len(values), *values)}], kind=kind)
    metadata = {"format": "stk.federation-update/1", "run_id": grant.run_id,
                "round": round, "participant_id": grant.participant_id,
                "model_sha256": MODEL, "spec_sha256": SPEC, "dataset_sha256": DATASET,
                "grant_id": grant.grant_id, "update_sha256": hashlib.sha256(payload).hexdigest(),
                "update_bytes": len(payload), "num_examples": 7, "metrics": {metric_name: 0.5},
                "masked": False}
    return metadata, payload


def authorization(grant, **changes):
    return {"coordinator_id": grant.coordinator_id, "run_id": grant.run_id, "round": 1,
            "participant_id": grant.participant_id, "dataset_sha256": grant.dataset_sha256,
            "spec_sha256": grant.spec_sha256, **changes}


def prepared(root):
    store, grant = create(root)
    metadata, payload = update(grant)
    return store, grant, store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)


def test_construct_read_and_recover_never_create_state(tmp_path):
    path = tmp_path / "not-created"
    store = ConsentRegistry(path)
    identity = str(uuid4())
    assert store.get_grant(identity) is None
    assert store.get_update(identity) is None
    assert store.list_grants()["grants"] == ()
    assert store.list_updates()["updates"] == ()
    assert store.recover(identity) is None
    assert not path.exists()


def test_owner_grant_is_frozen_dataset_is_opaque_and_withdrawal_survives_reopen(tmp_path):
    store, grant = create(tmp_path / "private")
    with pytest.raises(FrozenInstanceError):
        grant.active = False
    assert not (tmp_path / grant.dataset_id).exists()
    with store.authorized(grant.grant_id, **authorization(grant)) as lease:
        assert lease == grant
    revoked = store.revoke(grant.grant_id)
    assert not revoked.active
    reopened = ConsentRegistry(store.root)
    assert reopened.get_grant(grant.grant_id) == revoked
    with pytest.raises(ConsentDenied):
        with reopened.authorized(grant.grant_id, **authorization(grant)):
            pytest.fail("Withdrawn grant dispatched work")
    assert reopened.list_grants()["grants"] == (revoked,)


@pytest.mark.parametrize("changes", [
    {"coordinator_id": "f" * 64}, {"participant_id": "f" * 64},
    {"run_id": str(uuid4())}, {"dataset_sha256": "f" * 64},
    {"spec_sha256": "f" * 64}, {"round": 4}, {"round": True},
])
def test_each_local_binding_and_round_must_match(tmp_path, changes):
    store, grant = create(tmp_path / "state")
    with pytest.raises(ConsentDenied):
        with store.authorized(grant.grant_id, **authorization(grant, **changes)):
            pytest.fail("Mismatched authorization was accepted")


def test_same_original_idempotent_changed_original_conflicts_and_audit_is_immutable(tmp_path):
    store, grant = create(tmp_path / "state")
    metadata, payload = update(grant)
    record = store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    assert store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL) == record
    metadata["metrics"]["loss"] = 99
    with pytest.raises(TypeError):
        record.metadata["metrics"]["loss"] = 8
    with pytest.raises(TypeError):
        record.layout[0]["shape"][0] = 8
    with pytest.raises(FrozenInstanceError):
        record.state = "delivered"
    detached = record.as_dict()
    detached["metadata"]["metrics"]["loss"] = 30
    assert record.metadata["metrics"]["loss"] == 0.5
    with pytest.raises(ConsentConflict):
        store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    changed_metadata, changed_payload = update(grant, values=(2.0, 3.0))
    with pytest.raises(ConsentConflict):
        store.prepare_update(grant.grant_id, changed_metadata, changed_payload, model_sha256=MODEL)
    reopened = ConsentRegistry(store.root)
    assert reopened.get_update(record.update_id, include_payload=True) == record
    assert reopened.get_update(record.update_id).payload is None
    assert reopened.list_updates()["updates"][0].payload is None


@pytest.mark.parametrize("case", ["model", "dataset", "digest", "length", "kind", "masked", "path"])
def test_prepare_rejects_wrong_binding_bytes_kind_and_extra_path(tmp_path, case):
    store, grant = create(tmp_path / "state")
    metadata, payload = update(grant, kind="model" if case == "kind" else "delta")
    if case == "model":
        metadata["model_sha256"] = "f" * 64
    elif case == "dataset":
        metadata["dataset_sha256"] = "f" * 64
    elif case == "digest":
        metadata["update_sha256"] = "f" * 64
    elif case == "length":
        metadata["update_bytes"] += 1
    elif case == "masked":
        metadata["masked"] = True
    elif case == "path":
        metadata["source_path"] = str(tmp_path / "private.txt")
    with pytest.raises((ConsentError, FederationValidationError)):
        store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    assert store.list_updates()["total"] == 0


def test_revoke_prevents_prepare_and_send_but_owner_audit_remains_readable(tmp_path):
    store, grant, record = prepared(tmp_path / "state")
    store.revoke(grant.grant_id)
    calls = []
    with pytest.raises(ConsentDenied):
        store.send_update(record.update_id, coordinator_id=COORDINATOR, deliver=lambda *_: calls.append(1))
    metadata, payload = update(grant, round=2)
    with pytest.raises(ConsentDenied):
        store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    assert not calls
    assert store.get_update(record.update_id, include_payload=True) == record


def test_explicit_send_once_with_detached_callback_arguments(tmp_path):
    store, grant, record = prepared(tmp_path / "state")
    calls = []
    def deliver(metadata, payload):
        # A separate read sees the committed intent while callback holds the
        # write lease. The callback cannot alter authoritative audit metadata.
        seen = ConsentRegistry(store.root).get_update(record.update_id)
        assert seen.state == "sending"
        assert payload == record.payload
        calls.append(metadata)
        metadata["metrics"]["loss"] = 99
    delivered = store.send_update(record.update_id, coordinator_id=COORDINATOR, deliver=deliver)
    assert delivered.state == "delivered"
    assert delivered.metadata["metrics"]["loss"] == 0.5
    assert len(calls) == 1
    again = ConsentRegistry(store.root).send_update(record.update_id, coordinator_id=COORDINATOR,
                                                   deliver=lambda *_: pytest.fail("Duplicate send"))
    assert again.state == "delivered"
    store.revoke(grant.grant_id)
    assert store.get_update(record.update_id).state == "delivered"


def test_wire_metadata_does_not_choose_the_trusted_coordinator(tmp_path):
    store, _, record = prepared(tmp_path / "state")
    with pytest.raises(ConsentDenied):
        store.send_update(record.update_id, coordinator_id="f" * 64,
                          deliver=lambda *_: pytest.fail("Wrong coordinator received update"))
    assert store.get_update(record.update_id).state == "prepared"


@pytest.mark.parametrize("failure", ["callback", "bookkeeping"])
def test_callback_or_post_delivery_bookkeeping_failure_never_replays(tmp_path, monkeypatch, failure):
    store, _, record = prepared(tmp_path / "state")
    calls = []
    def deliver(*_):
        calls.append(1)
        if failure == "callback":
            raise OSError("publisher lost the reply")
    original = store._mark
    def mark(db, identity, state):
        if failure == "bookkeeping" and state == "delivered":
            raise sqlite3.OperationalError("injected post-send failure")
        return original(db, identity, state)
    monkeypatch.setattr(store, "_mark", mark)
    with pytest.raises(ConsentOutcomeUncertain) as failure_info:
        store.send_update(record.update_id, coordinator_id=COORDINATOR, deliver=deliver)
    assert failure_info.value.update_id == record.update_id
    assert calls == [1]
    reopened = ConsentRegistry(store.root)
    assert reopened.get_update(record.update_id).state == "uncertain"
    assert reopened.recover(record.update_id).state == "uncertain"
    with pytest.raises(ConsentOutcomeUncertain):
        reopened.send_update(record.update_id, coordinator_id=COORDINATOR, deliver=deliver)
    assert calls == [1]


def test_actual_process_death_retains_sending_and_explicit_recover_only_marks_uncertain(tmp_path):
    store, _, record = prepared(tmp_path / "state")
    code = """import os,sys
from suan.federation.consent import ConsentRegistry
ConsentRegistry(sys.argv[1]).send_update(sys.argv[2], coordinator_id=sys.argv[3], deliver=lambda *_: os._exit(73))
"""
    environment = {**os.environ, "STK_TOKEN_PLAN_API_KEY": ""}
    environment.pop("STK_TOKEN_PLAN_MODEL", None)
    child = subprocess.run([sys.executable, "-c", code, str(store.root), record.update_id, COORDINATOR],
                           cwd=Path(__file__).resolve().parents[1], env=environment,
                           capture_output=True, timeout=20)
    assert child.returncode == 73, child.stderr.decode("utf-8", "replace")
    reopened = ConsentRegistry(store.root)
    assert reopened.get_update(record.update_id).state == "sending"
    assert reopened.list_updates()["updates"][0].state == "sending"
    with pytest.raises(ConsentOutcomeUncertain):
        reopened.send_update(record.update_id, coordinator_id=COORDINATOR,
                             deliver=lambda *_: pytest.fail("Interrupted send replayed"))
    assert reopened.recover(record.update_id).state == "uncertain"


@pytest.mark.parametrize("operation", ["authorized", "send"])
def test_accepted_lease_serializes_cross_instance_revocation(tmp_path, operation):
    store, grant, record = prepared(tmp_path / "state")
    other = ConsentRegistry(store.root)
    accepted, release, revoking = threading.Event(), threading.Event(), threading.Event()
    def accepted_call():
        if operation == "send":
            def deliver(*_):
                accepted.set()
                assert release.wait(5)
            store.send_update(record.update_id, coordinator_id=COORDINATOR, deliver=deliver)
        else:
            with store.authorized(grant.grant_id, **authorization(grant)):
                accepted.set()
                assert release.wait(5)
    def revoke():
        revoking.set()
        return other.revoke(grant.grant_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(accepted_call)
        assert accepted.wait(5)
        second = pool.submit(revoke)
        assert revoking.wait(5)
        try:
            with pytest.raises(TimeoutError):
                second.result(timeout=0.1)
        finally:
            release.set()
        first.result(timeout=5)
        assert not second.result(timeout=5).active
    with pytest.raises(ConsentDenied):
        with store.authorized(grant.grant_id, **authorization(grant)):
            pytest.fail("Call accepted after withdrawal")


def test_audit_quota_retains_existing_record_and_never_sends(tmp_path):
    store, grant, record = prepared(tmp_path / "state")
    limited = ConsentRegistry(store.root, max_audit_bytes=1)
    metadata, payload = update(grant, round=2)
    with pytest.raises(ConsentQuota):
        limited.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    assert limited.get_update(record.update_id, include_payload=True) == record
    first_metadata, first_payload = update(grant)
    assert limited.prepare_update(grant.grant_id, first_metadata, first_payload, model_sha256=MODEL) == record
    assert limited.list_updates()["total"] == 1


def test_retained_audit_quota_counts_existing_utf8_bytes_not_characters(tmp_path):
    store, grant = create(tmp_path / "state", model_layout=[{"name": "权重", "dtype": "f64", "shape": [2]}])
    metadata, payload = update(grant, array_name="权重", metric_name="损失")
    store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    with sqlite3.connect(store.path) as db:
        actual, characters = db.execute(
            "SELECT length(payload)+length(CAST(metadata AS BLOB))+length(CAST(layout AS BLOB)),"
            "length(payload)+length(metadata)+length(layout) FROM updates").fetchone()
    assert actual > characters
    limited = ConsentRegistry(store.root, max_audit_bytes=2 * actual - 1)
    metadata, payload = update(grant, round=2, array_name="权重", metric_name="损失")
    with pytest.raises(ConsentQuota):
        limited.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    assert limited.list_updates()["total"] == 1


def test_metadata_pages_are_bounded_and_do_not_include_payload(tmp_path):
    store, grant = create(tmp_path / "state")
    for round_number in range(1, 4):
        metadata, payload = update(grant, round=round_number)
        store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    first = store.list_updates(limit=2)
    second = store.list_updates(offset=first["next_offset"], limit=2)
    assert len(first["updates"]) == 2 and len(second["updates"]) == 1
    assert first["total"] == second["total"] == 3
    assert second["next_offset"] is None
    assert all(item.payload is None for item in first["updates"])
    with pytest.raises(ConsentDenied):
        store.list_updates(limit=101)
    with pytest.raises(ConsentDenied):
        store.list_grants(offset=True)


def test_registry_rejects_project_placement_and_symlinked_state(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.sqlite3").touch()
    store = ConsentRegistry(project / "private")
    with pytest.raises(ConsentError):
        create(store.root)
    assert not store.root.exists()
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    with pytest.raises(ConsentError):
        create(linked / "private")
    assert not (target / "private").exists()


def test_payload_tampering_rejected_before_callback_and_original_audit_not_replaced(tmp_path):
    store, _, record = prepared(tmp_path / "state")
    with sqlite3.connect(store.path) as db:
        payload = bytearray(record.payload)
        payload[-1] ^= 1
        db.execute("UPDATE updates SET payload=? WHERE update_id=?", (bytes(payload), record.update_id))
    with pytest.raises((ConsentError, FederationValidationError)):
        store.send_update(record.update_id, coordinator_id=COORDINATOR,
                          deliver=lambda *_: pytest.fail("Damaged audit bytes sent"))
    assert store.get_update(record.update_id).state == "prepared"


def test_revocation_wins_after_committed_intent_before_callback_lease(tmp_path, monkeypatch):
    store, grant, record = prepared(tmp_path / "state")
    other = ConsentRegistry(store.root)
    connect, writes = store._connect, []
    @contextmanager
    def revoke_after_intent(**options):
        with connect(**options) as db:
            yield db
        if options.get("write"):
            writes.append(1)
            if len(writes) == 1:
                assert other.get_update(record.update_id).state == "sending"
                other.revoke(grant.grant_id)
    monkeypatch.setattr(store, "_connect", revoke_after_intent)
    with pytest.raises(ConsentOutcomeUncertain):
        store.send_update(record.update_id, coordinator_id=COORDINATOR,
                          deliver=lambda *_: pytest.fail("Revoked grant published an update"))
    assert other.get_update(record.update_id).state == "uncertain"
    assert not other.get_grant(grant.grant_id).active


def test_committed_intent_then_storage_error_is_uncertain_without_callback(tmp_path, monkeypatch):
    store, _, record = prepared(tmp_path / "state")
    connect, writes = store._connect, []
    @contextmanager
    def fail_after_commit(**options):
        with connect(**options) as db:
            yield db
        if options.get("write"):
            writes.append(1)
            if len(writes) == 1:
                raise ConsentError("injected commit acknowledgement failure")
    monkeypatch.setattr(store, "_connect", fail_after_commit)
    with pytest.raises(ConsentOutcomeUncertain):
        store.send_update(record.update_id, coordinator_id=COORDINATOR,
                          deliver=lambda *_: pytest.fail("Callback reached after failed intent acknowledgement"))
    assert ConsentRegistry(store.root).get_update(record.update_id).state == "sending"


def test_reads_and_import_do_not_load_network_training_or_model_settings(tmp_path):
    root = Path(__file__).resolve().parents[1]
    code = """import importlib.abc,sys
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] in {'numpy','flwr','socket','torch'} or fullname.startswith(('suan.models','suan.materials.service')):
   raise AssertionError('Unexpected side-effect dependency')
sys.meta_path.insert(0,Deny())
sys.path.insert(0,sys.argv[1])
from suan.federation.consent import ConsentRegistry
r=ConsentRegistry(sys.argv[2]); assert r.list_grants()['total']==0; assert r.list_updates()['total']==0
"""
    environment = {**os.environ, "STK_TOKEN_PLAN_API_KEY": ""}
    environment.pop("STK_TOKEN_PLAN_MODEL", None)
    child = subprocess.run([sys.executable, "-I", "-c", code, str(root), str(tmp_path / "absent")],
                           env=environment, capture_output=True, timeout=20)
    assert child.returncode == 0, child.stderr.decode("utf-8", "replace")
    assert not (tmp_path / "absent").exists()


def test_owner_model_layout_detaches_inputs_and_returned_nested_values(tmp_path):
    layout = [{"name": "weight", "dtype": "f64", "shape": [2]}]
    store, grant = create(tmp_path / "state", model_layout=layout)
    layout[0]["name"] = "another"
    layout[0]["shape"][0] = 3
    layout.append({"name": "extra", "dtype": "f32", "shape": [1]})
    assert grant.model_layout[0]["name"] == "weight"
    assert grant.model_layout[0]["shape"] == (2,)
    with pytest.raises(TypeError):
        grant.model_layout[0]["shape"][0] = 7
    detached = grant.as_dict()
    detached["model_layout"][0]["shape"][0] = 8
    assert ConsentRegistry(store.root).get_grant(grant.grant_id) == grant
    metadata, payload = update(grant)
    assert store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL).state == "prepared"


@pytest.mark.parametrize("mismatch", ["name", "shape", "dtype", "order"])
def test_authorized_metadata_cannot_publish_another_actual_delta_layout(tmp_path, mismatch):
    layout = [{"name": "weight", "dtype": "f64", "shape": [2]},
              {"name": "bias", "dtype": "f32", "shape": [1]}]
    store, grant = create(tmp_path / "state", model_layout=layout)
    arrays = [{**layout[0], "data": struct.pack("<dd", 1.25, -2.5)},
              {**layout[1], "data": struct.pack("<f", 0.5)}]
    if mismatch == "name":
        arrays[0]["name"] = "未授权数组"
    elif mismatch == "shape":
        arrays[0]["shape"] = [1, 2]
    elif mismatch == "dtype":
        arrays[0]["dtype"] = "f32"
        arrays[0]["data"] = struct.pack("<ff", 1.25, -2.5)
    else:
        arrays.reverse()
    payload = encode_arrays(arrays, kind="delta")
    metadata, _ = update(grant)
    metadata.update(update_sha256=hashlib.sha256(payload).hexdigest(), update_bytes=len(payload))
    # Every value is finite and all wire identities/digests are otherwise valid.
    assert decode_arrays(payload, expected_kind="delta")["bytes"] == len(payload)
    with pytest.raises(FederationValidationError):
        store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    assert store.list_updates()["total"] == 0


@pytest.mark.parametrize("corruption", ["invalid_json", "different_valid_shape", "digest"])
def test_corrupt_persisted_owner_layout_fails_closed_before_send(tmp_path, corruption):
    store, grant, record = prepared(tmp_path / "state")
    with sqlite3.connect(store.path) as db:
        if corruption == "invalid_json":
            db.execute("UPDATE grants SET model_layout='broken' WHERE grant_id=?", (grant.grant_id,))
        elif corruption == "different_valid_shape":
            db.execute("UPDATE grants SET model_layout=? WHERE grant_id=?",
                       (json.dumps([{"name": "weight", "dtype": "f64", "shape": [1, 2]}]), grant.grant_id))
        else:
            db.execute("UPDATE grants SET layout_sha256=? WHERE grant_id=?", ("f" * 64, grant.grant_id))
    with pytest.raises(ConsentError):
        ConsentRegistry(store.root).get_grant(grant.grant_id)
    with pytest.raises(ConsentError):
        store.send_update(record.update_id, coordinator_id=COORDINATOR,
                          deliver=lambda *_: pytest.fail("Corrupt owner layout published an update"))
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT state FROM updates WHERE update_id=?", (record.update_id,)).fetchone()[0] == "prepared"


def test_self_consistent_replaced_audit_layout_still_cannot_override_owner_grant(tmp_path):
    store, grant, record = prepared(tmp_path / "state")
    payload = encode_arrays([{"name": "different", "dtype": "f64", "shape": [2],
                              "data": struct.pack("<dd", 1.25, -2.5)}], kind="delta")
    metadata = record.as_dict()["metadata"]
    metadata.update(update_sha256=hashlib.sha256(payload).hexdigest(), update_bytes=len(payload))
    layout = decode_arrays(payload, expected_kind="delta")["layout"]
    def canonical(value):
        return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    original = hashlib.sha256(canonical({"metadata": metadata, "layout": layout,
                                        "model_sha256": MODEL}).encode("utf-8")).hexdigest()
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE updates SET metadata=?,layout=?,payload=?,original_sha256=? WHERE update_id=?",
                   (canonical(metadata), canonical(layout), payload, original, record.update_id))
    with pytest.raises(ConsentError):
        store.get_update(record.update_id)
    with pytest.raises(ConsentError):
        store.send_update(record.update_id, coordinator_id=COORDINATOR,
                          deliver=lambda *_: pytest.fail("Audit layout overrode owner consent"))


def test_payload_budget_includes_wire_header_and_utf8_layout(tmp_path, monkeypatch):
    from suan.federation import consent
    store, grant = create(tmp_path / "state", model_layout=[{"name": "权重", "dtype": "f64", "shape": [2]}])
    metadata, payload = update(grant, array_name="权重", metric_name="损失")
    assert len(payload) > len(struct.pack("<dd", 1.25, -2.5))
    monkeypatch.setattr(consent, "MAX_PAYLOAD_BYTES", len(payload) - 1)
    with pytest.raises(ConsentError):
        store.prepare_update(grant.grant_id, metadata, payload, model_sha256=MODEL)
    assert store.list_updates()["total"] == 0
