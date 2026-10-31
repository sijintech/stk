"""Frozen specification and transport-bound receipt admission, without a model call."""
from copy import deepcopy
from uuid import UUID

import pytest

from suan.federation.protocol import (MESSAGE_FORMAT, RESULT_FORMAT, RUN_FORMAT, SPEC_FORMAT,
    TRAINER, model_layout, training_spec_sha256, validate_message, validate_node_result,
    validate_run_manifest, validate_training_spec)
from suan.federation.updates import FederationValidationError


def spec():
    return {"format": SPEC_FORMAT, "trainer": TRAINER, "features": [{"name": "x", "unit": "1"}],
            "targets": [{"name": "y", "unit": "1"}], "dtype": "f64", "normalization": "none",
            "steps": 4, "learning_rate": .1, "strategy": "fedavg", "proximal_mu": 0}


def manifest():
    return {"format": RUN_FORMAT, "run_id": str(UUID(int=1)), "coordinator_device_id": "a"*32,
            "coordinator_id": "a"*64, "spec_sha256": training_spec_sha256(spec()), "max_rounds": 4,
            "participants": [{"node_id": str(i)*32, "participant_id": str(i)*64,
                              "grant_id": str(UUID(int=10+i)), "dataset_sha256": str(i+3)*64}
                             for i in range(1,4)]}


def message(operation="train"):
    run = manifest()
    return {"format": MESSAGE_FORMAT, "operation": operation, "run_id": run["run_id"], "round": 1,
            "coordinator_id": run["coordinator_id"], "spec_sha256": run["spec_sha256"],
            **{k:run["participants"][0][k] for k in ("participant_id", "grant_id", "dataset_sha256")},
            "model": {"sha256": "b"*64, "bytes": 128}}


def receipt(operation="status"):
    request = message(operation)
    return {"format": RESULT_FORMAT, **{k:request[k] for k in ("run_id", "round", "participant_id", "grant_id")},
            "state": "running", "task_id": "c"*32, "update_id": None, "update": None}


def test_spec_identity_layout_and_detached_values():
    value = spec()
    result = validate_training_spec(value)
    assert result == value
    value["features"][0]["name"] = "other"
    assert result["features"][0]["name"] == "x"
    assert training_spec_sha256(result) != training_spec_sha256(value)
    assert model_layout(result) == [{"name":"weights", "dtype":"f64", "shape":[1,1]},
                                    {"name":"bias", "dtype":"f64", "shape":[1]}]


@pytest.mark.parametrize("key,value", [("steps", True),("steps",0),("steps",1001),
    ("learning_rate", float("nan")),("learning_rate",True),("learning_rate",0),
    ("proximal_mu",1),("normalization","node-fitted"),("strategy",[]),
    ("dtype",{}),("features",[{"name":"x","unit":"1"}]*2)])
def test_unapproved_training_options_are_rejected(key,value):
    source=spec(); source[key]=value
    with pytest.raises(FederationValidationError): validate_training_spec(source)


@pytest.mark.parametrize("operation", [None, True, 1, [], {}, "train ", "exec"])
def test_bad_operation_always_has_stable_validation_error(operation):
    source=message(); source["operation"]=operation
    with pytest.raises(FederationValidationError): validate_message(source)


@pytest.mark.parametrize("operation", ["train","status","collect","cancel"])
def test_every_operation_is_fully_bound_and_rejects_path_overrides(operation):
    source=message(operation)
    assert validate_message(source) == source
    for key in ("model","grant_id","dataset_sha256"):
        bad=deepcopy(source); bad.pop(key)
        with pytest.raises(FederationValidationError): validate_message(bad)
    for key in ("task_id","path","argv","env","module","options"):
        bad=deepcopy(source); bad[key]="forbidden"
        with pytest.raises(FederationValidationError): validate_message(bad)


@pytest.mark.parametrize("change", ["device_as_peer","duplicate_node","duplicate_peer","duplicate_grant","two_nodes","coordinator_peer"])
def test_run_identity_map_cannot_be_inferred_from_bearer_or_duplicates(change):
    value=manifest()
    if change=="device_as_peer": value["coordinator_id"]=value["coordinator_device_id"]
    elif change=="two_nodes": value["participants"].pop()
    elif change=="coordinator_peer": value["coordinator_id"]=value["participants"][0]["participant_id"]
    else:
        key={"duplicate_node":"node_id","duplicate_peer":"participant_id","duplicate_grant":"grant_id"}[change]
        value["participants"][1][key]=value["participants"][0][key]
    with pytest.raises(FederationValidationError): validate_run_manifest(value)


def test_result_binds_original_identity_and_rejects_runtime_paths():
    value=receipt()
    assert validate_node_result(value,message=message("status"))==value
    for key in ("run_id","round","participant_id","grant_id"):
        bad=deepcopy(value); bad[key]=2 if key=="round" else "wrong"
        with pytest.raises(FederationValidationError): validate_node_result(bad,message=message("status"))
    value["spec"]={"argv":["private"]}
    with pytest.raises(FederationValidationError): validate_node_result(value,message=message("status"))


def test_only_collect_delivered_can_return_bound_update_metadata():
    request=message("collect"); value=receipt("collect")
    value.update(state="delivered",update_id=str(UUID(int=20)))
    metadata={"format":"stk.federation-update/1", **{k:request[k] for k in ("run_id","round","participant_id","spec_sha256","dataset_sha256","grant_id")},
              "model_sha256":request["model"]["sha256"],"update_sha256":"d"*64,"update_bytes":128,
              "num_examples":10,"metrics":{"loss":.5},"masked":False}
    with pytest.raises(FederationValidationError): validate_node_result(value,message=request)
    value["update"]=metadata
    assert validate_node_result(value,message=request)["update"]==metadata
    with pytest.raises(FederationValidationError): validate_node_result(value,message=message("status"))
    value["update"]["dataset_sha256"]="e"*64
    with pytest.raises(FederationValidationError): validate_node_result(value,message=request)
