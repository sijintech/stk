"""Admission precedes optional Flower; explicit native dependency enables math acceptance."""
from copy import deepcopy
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

from suan.federation.flower import FlowerAggregator, FlowerAggregationError
from suan.federation.updates import (FederationValidationError, decode_arrays,
                                     encode_arrays)


RUN = str(UUID(int=1))
SPEC = "a" * 64


def bundle(values, *, dtype="f64", kind="model"):
    code = "d" if dtype == "f64" else "f"
    return encode_arrays([
        {"name": "weights", "dtype": dtype, "shape": [2], "data": struct.pack("<2" + code, *values[:2])},
        {"name": "bias", "dtype": dtype, "shape": [1], "data": struct.pack("<" + code, values[2])},
    ], kind=kind)


def request(dtype="f64"):
    model = bundle([1, -1, .5], dtype=dtype)
    source = decode_arrays(model)
    updates, participants = [], {}
    for index, (count, values) in enumerate(zip((8, 12, 20), ((.5, 1, -.5), (1.5, -.5, .25), (-.5, .25, 1))), 1):
        peer = str(index) * 64
        grant = str(UUID(int=100 + index))
        dataset = str(index + 3) * 64
        raw = bundle(values, dtype=dtype, kind="delta")
        delta = decode_arrays(raw)
        metadata = {"format": "stk.federation-update/1", "run_id": RUN, "round": 1,
            "participant_id": peer, "model_sha256": source["sha256"], "spec_sha256": SPEC,
            "dataset_sha256": dataset, "grant_id": grant, "update_sha256": delta["sha256"],
            "update_bytes": len(raw), "num_examples": count, "metrics": {"loss": index * .3}, "masked": False}
        updates.append((metadata, raw))
        participants[peer] = {"dataset_sha256": dataset, "grant_id": grant}
    return model, updates, {"participants": participants, "run_id": RUN, "round": 1, "spec_sha256": SPEC}


def no_process(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected input launched the optional framework")
    monkeypatch.setattr(subprocess, "run", forbidden)


def test_constructor_is_passive(monkeypatch):
    no_process(monkeypatch)
    assert FlowerAggregator("/not-installed/python").timeout == 30


@pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf"), 301, "30"])
def test_process_deadline_must_be_finite_and_bounded(timeout):
    with pytest.raises(ValueError):
        FlowerAggregator(sys.executable, timeout=timeout)


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_run", "negative_weight", "boolean_weight",
    "wrong_base", "wrong_spec", "wrong_dataset", "wrong_grant", "wrong_sha", "wrong_size", "unknown_node",
    "metric_names", "reserved_weight", "masked", "nonfinite_metric"])
def test_bad_round_is_rejected_before_starting_framework(monkeypatch, change):
    model, rows, arguments = request()
    item = rows[0][0]
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[1] = deepcopy(rows[0])
    elif change == "wrong_run":
        item["run_id"] = str(UUID(int=2))
    elif change == "negative_weight":
        item["num_examples"] = -1
    elif change == "boolean_weight":
        item["num_examples"] = True
    elif change == "wrong_base":
        item["model_sha256"] = "b" * 64
    elif change == "wrong_spec":
        item["spec_sha256"] = "b" * 64
    elif change == "wrong_dataset":
        item["dataset_sha256"] = "b" * 64
    elif change == "wrong_grant":
        item["grant_id"] = str(UUID(int=2))
    elif change == "wrong_sha":
        item["update_sha256"] = "b" * 64
    elif change == "wrong_size":
        item["update_bytes"] += 1
    elif change == "unknown_node":
        item["participant_id"] = "e" * 64
    elif change == "metric_names":
        item["metrics"] = {"other": 1}
    elif change == "reserved_weight":
        for row, _ in rows:
            row["metrics"] = {"num-examples": 1}
    elif change == "masked":
        item["masked"] = True
    elif change == "nonfinite_metric":
        item["metrics"]["loss"] = float("nan")
    no_process(monkeypatch)
    with pytest.raises(FederationValidationError):
        FlowerAggregator("/not-installed/python").aggregate(model, rows, **arguments)


def test_delta_layout_is_checked_before_framework(monkeypatch):
    model, rows, arguments = request()
    wrong = encode_arrays([{"name": "unrelated", "dtype": "f64", "shape": [1], "data": struct.pack("<d", 1)}], kind="delta")
    rows[0] = (rows[0][0], wrong)
    no_process(monkeypatch)
    with pytest.raises(FederationValidationError):
        FlowerAggregator("/not-installed/python").aggregate(model, rows, **arguments)


@pytest.mark.parametrize("mutable", ["model", "delta"])
def test_aggregation_copies_no_mutable_input_past_validation(monkeypatch, mutable):
    model, rows, arguments = request()
    if mutable == "model":
        model = bytearray(model)
    else:
        rows[0] = (rows[0][0], bytearray(rows[0][1]))
    no_process(monkeypatch)
    with pytest.raises(FederationValidationError):
        FlowerAggregator("/not-installed/python").aggregate(model, rows, **arguments)


def test_missing_explicit_interpreter_fails_without_install_or_retry(tmp_path):
    model, rows, arguments = request()
    with pytest.raises(FlowerAggregationError, match="unavailable"):
        FlowerAggregator(tmp_path / "missing-python").aggregate(model, rows, **arguments)


def test_timeout_is_single_attempt_with_sanitized_environment(monkeypatch):
    model, rows, arguments = request()
    seen = []
    def timeout(command, **kwargs):
        seen.append((command, kwargs))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setenv("UNRELATED_TEST_CREDENTIAL", "abcdefghijklmnopqrstu")
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(FlowerAggregationError, match="deadline"):
        FlowerAggregator(sys.executable, timeout=.1).aggregate(model, rows, **arguments)
    assert len(seen) == 1
    command, kwargs = seen[0]
    assert command[1:4] == ["-I", "-m", "suan.federation.flower_worker"]
    assert kwargs["env"]["STK_TOKEN_PLAN_API_KEY"] == ""
    assert "STK_TOKEN_PLAN_MODEL" not in kwargs["env"]
    assert "UNRELATED_TEST_CREDENTIAL" not in kwargs["env"]
    assert kwargs["env"]["FLWR_TELEMETRY_ENABLED"] == "0"
    assert kwargs["env"]["FLWR_DISABLE_UPDATE_CHECK"] == "1"


@pytest.mark.parametrize("corruption", ["bool_round", "float_round", "float_bytes", "float_examples",
                                       "oversize_metric_integer", "deep_json"])
def test_malformed_child_receipt_has_a_fixed_public_failure(monkeypatch, corruption):
    model, rows, arguments = request()

    def result(command, **kwargs):
        directory = Path(command[-1])
        job = json.loads((directory / "job.json").read_text())
        decoded = decode_arrays(model)
        receipt = {"format": "stk.federation-aggregate-result/1", "run_id": RUN, "round": 1,
            "source_model_sha256": decoded["sha256"], "spec_sha256": SPEC,
            "participants": [x["participant_id"] for x in job["updates"]],
            "model_sha256": decoded["sha256"], "model_bytes": len(model), "num_examples": 40,
            "framework": {"name": "flwr", "version": "1.42.0"}, "metrics": {"loss": 1}}
        if corruption == "bool_round":
            receipt["round"] = True
        elif corruption == "float_round":
            receipt["round"] = 1.0
        elif corruption == "float_bytes":
            receipt["model_bytes"] = float(len(model))
        elif corruption == "float_examples":
            receipt["num_examples"] = 40.0
        elif corruption == "oversize_metric_integer":
            receipt["metrics"]["loss"] = 10**1000
        raw = json.dumps(receipt).encode()
        if corruption == "deep_json":
            raw = b"[" * 3000 + b"0" + b"]" * 3000
        (directory / "result.json").write_bytes(raw)
        (directory / "result.bin").write_bytes(model)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", result)
    with pytest.raises(FlowerAggregationError, match="could not be verified"):
        FlowerAggregator(sys.executable).aggregate(model, rows, **arguments)


@pytest.fixture
def algorithm_python():
    path = os.environ.get("STK_FEDERATION_TEST_PYTHON")
    if not path:
        pytest.skip("Explicit isolated Flower interpreter is required for algorithm acceptance")
    assert sys.platform == "linux", "Initial algorithm acceptance requires Linux"
    assert Path(path).is_file(), "Explicit Flower interpreter is missing"
    return path


@pytest.mark.server
@pytest.mark.parametrize("dtype", ["f32", "f64"])
def test_real_isolated_flower_aggregates_exact_admitted_deltas(algorithm_python, dtype):
    model, rows, arguments = request(dtype)
    result = FlowerAggregator(algorithm_python).aggregate(model, rows, **arguments)
    output = decode_arrays(result["model"], expected_kind="model")
    code = "f" if dtype == "f32" else "d"
    actual = [number for x in output["arrays"] for number in struct.unpack("<" + str(len(x["data"]) // struct.calcsize(code)) + code, x["data"])]
    # Independent unequal-sample weighted reference, not another Flower call.
    assert actual == pytest.approx([1.3, -.825, .975], rel=0, abs=1e-6 if dtype == "f32" else 1e-14)
    receipt = result["receipt"]
    assert receipt["num_examples"] == 40
    assert receipt["metrics"] == {"loss": pytest.approx(.69)}
    assert receipt["framework"] == {"name": "flwr", "version": "1.42.0"}
    assert receipt["model_sha256"] == output["sha256"]
    assert output["layout"] == decode_arrays(model)["layout"]
