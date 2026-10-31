"""Closed, local held-out evaluation for the fixed linear federation adapter.

This is deliberately separate from the Materials curve MLP contract. It does
not fit a model, import an algorithm framework, contact a service, or decide a
scientific threshold. Numeric inference uses the frozen raw-number space.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
import struct

from . import inputs
from .protocol import model_layout, training_spec_sha256, validate_run_manifest, validate_training_spec
from .updates import decode_arrays


class EvaluationError(ValueError):
    """A path-free failure suitable for the owner API."""


def fields(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise EvaluationError("Object fields do not match the linear evaluation contract")


def sha(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise EvaluationError("Expected a lower-case SHA-256 identity")
    return value


def integer(value, low=0, high=10000):
    if type(value) is not int or not low <= value <= high:
        raise EvaluationError("Integer is outside the linear evaluation bound")
    return value


def version(value, *, nullable=False):
    if nullable and value is None:
        return value
    if type(value) is not str or re.fullmatch(r"v[1-9][0-9]{0,7}", value) is None:
        raise EvaluationError("Expected an admitted linear model version")
    return value


def text(value, maximum):
    try:
        valid = (type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= maximum
                 and not any(ord(c) < 32 or ord(c) == 127 for c in value))
    except UnicodeError:
        valid = False
    if not valid:
        raise EvaluationError("Invalid linear evaluation text")
    return value


def digest(value):
    return hashlib.sha256(inputs.canonical(value)).hexdigest()


def descriptor(bundle):
    return {"sha256": bundle["sha256"], "bytes": bundle["bytes"]}


def validate_thresholds(value, targets=None):
    if type(value) is not list or not 1 <= len(value) <= 16:
        raise EvaluationError("Each target needs an explicit RMSE threshold")
    result = []
    for item in value:
        fields(item, {"name", "unit", "max_rmse"})
        name, unit, maximum = text(item["name"], 128), text(item["unit"], 64), item["max_rmse"]
        if type(maximum) not in (int, float):
            raise EvaluationError("RMSE thresholds must be finite nonnegative numbers")
        try:
            if not math.isfinite(maximum) or maximum < 0:
                raise ValueError
        except (ValueError, OverflowError):
            raise EvaluationError("RMSE thresholds must be finite nonnegative numbers") from None
        result.append({"name": name, "unit": unit, "max_rmse": maximum})
    if len({x["name"] for x in result}) != len(result):
        raise EvaluationError("RMSE threshold target names must be distinct")
    if targets is not None and [{k: t[k] for k in ("name", "unit")} for t in result] != targets:
        raise EvaluationError("Threshold order and units must match the frozen targets")
    return result


def validate_request(method, value):
    """Validate a detached closed request, without touching any storage."""
    if method == "candidates.get":
        fields(value, {"run_id", "round"})
        inputs.uuid(value["run_id"]), integer(value["round"], 1)
    elif method == "evaluations.prepare":
        fields(value, {"evaluation_id", "run_id", "round", "dataset_id", "dataset_sha256",
                       "candidate_sha256", "base_model_sha256", "spec_sha256", "thresholds",
                       "expected_active_version", "expected_active_generation"})
        for key in ("evaluation_id", "run_id", "dataset_id"):
            inputs.uuid(value[key])
        for key in ("dataset_sha256", "candidate_sha256", "base_model_sha256", "spec_sha256"):
            sha(value[key])
        integer(value["round"], 1)
        version(value["expected_active_version"], nullable=True)
        integer(value["expected_active_generation"], 0, 10**9)
        validate_thresholds(value["thresholds"])
    elif method == "evaluations.evaluate":
        fields(value, {"evaluation_id", "plan_sha256"})
        inputs.uuid(value["evaluation_id"]), sha(value["plan_sha256"])
    elif method == "evaluations.get":
        fields(value, {"evaluation_id"})
        inputs.uuid(value["evaluation_id"])
    elif method == "models.list":
        fields(value, {"spec_sha256"})
        sha(value["spec_sha256"])
    elif method == "models.admit":
        fields(value, {"evaluation_id", "receipt_sha256", "expected_active_version",
                       "expected_active_generation"})
        inputs.uuid(value["evaluation_id"]), sha(value["receipt_sha256"])
        version(value["expected_active_version"], nullable=True)
        integer(value["expected_active_generation"], 0, 10**9)
    elif method == "models.activate":
        fields(value, {"spec_sha256", "version", "expected_active_version", "expected_active_generation"})
        sha(value["spec_sha256"]), version(value["version"])
        version(value["expected_active_version"], nullable=True)
        integer(value["expected_active_generation"], 0, 10**9)
    else:
        raise EvaluationError("Unsupported linear registry method")
    # Also bound nested values/Unicode before a journal copies the request.
    if len(inputs.canonical(value)) > inputs.MAX_METADATA_BYTES:
        raise EvaluationError("Linear registry request exceeds its byte budget")
    return value


def candidate(root, run_id, number):
    """Read a candidate only from a trusted coordinator root and frozen identity."""
    if root is None:
        raise EvaluationError("A trusted coordinator registry is not configured")
    inputs.uuid(run_id), integer(number, 1)
    path = Path(root) / run_id
    run = inputs.read_json(path / "run.json")
    fields(run, {"format", "manifest", "spec", "initial_model_sha256", "rounds"})
    if run["format"] != "stk.federation-coordinator/1":
        raise EvaluationError("Unsupported coordinator record")
    manifest, spec = validate_run_manifest(run["manifest"]), validate_training_spec(run["spec"])
    spec_sha = training_spec_sha256(spec)
    if manifest["run_id"] != run_id or manifest["spec_sha256"] != spec_sha or number > run["rounds"]:
        raise EvaluationError("Candidate differs from the frozen coordinator run")
    integer(run["rounds"], 0, manifest["max_rounds"])
    directory = path / str(number)
    state = inputs.read_json(directory / "round.json")
    fields(state, {"format", "run_id", "round", "model", "state", "model_phase", "actions",
                   "receipt", "candidate_sha256"})
    if (state["format"] != "stk.federation-round/1" or state["state"] != "aggregated"
            or state["run_id"] != run_id or type(state["round"]) is not int or state["round"] != number):
        raise EvaluationError("Only a completed immutable round candidate can be evaluated")
    base_raw, raw = inputs.read_bytes(directory / "model.bin"), inputs.read_bytes(directory / "candidate.bin")
    base = decode_arrays(base_raw, expected_kind="model", expected_layout=model_layout(spec))
    model = decode_arrays(raw, expected_kind="model", expected_layout=model_layout(spec))
    if state["model"] != descriptor(base) or state["candidate_sha256"] != model["sha256"]:
        raise EvaluationError("Candidate or source model bytes differ from the frozen round")
    if number == 1:
        previous = decode_arrays(inputs.read_bytes(path / "initial.bin"), expected_kind="model",
                                 expected_layout=model_layout(spec))
        expected = sha(run["initial_model_sha256"])
    else:
        previous_state = inputs.read_json(path / str(number - 1) / "round.json")
        if (previous_state["state"] != "aggregated" or previous_state["run_id"] != run_id
                or type(previous_state["round"]) is not int or previous_state["round"] != number - 1):
            raise EvaluationError("Round predecessor is not the retained completed candidate")
        previous = decode_arrays(inputs.read_bytes(path / str(number - 1) / "candidate.bin"),
                                 expected_kind="model", expected_layout=model_layout(spec))
        expected = sha(previous_state["candidate_sha256"])
    if previous["sha256"] != expected or base["sha256"] != expected:
        raise EvaluationError("Round base differs from its retained predecessor")
    receipt = state["receipt"]
    fields(receipt, {"format", "run_id", "round", "source_model_sha256", "spec_sha256", "participants",
                     "model_sha256", "model_bytes", "num_examples", "framework", "metrics"})
    expected_receipt = {"format": "stk.federation-aggregate-result/1", "run_id": run_id, "round": number,
                        "source_model_sha256": base["sha256"], "spec_sha256": spec_sha,
                        "model_sha256": model["sha256"], "model_bytes": model["bytes"],
                        "framework": {"name": "flwr", "version": "1.42.0"}}
    for key, value in expected_receipt.items():
        if type(receipt[key]) is not type(value) or receipt[key] != value:
            raise EvaluationError("Aggregation receipt does not bind this exact candidate")
    approved = {p["participant_id"] for p in manifest["participants"]}
    peers = receipt["participants"]
    if (type(peers) is not list or not 3 <= len(peers) <= 20 or len(set(peers)) != len(peers)
            or any(p not in approved for p in peers)):
        raise EvaluationError("Candidate receipt does not identify an approved quorum")
    integer(receipt["num_examples"], 1, 20 * 10**9)
    metrics = receipt["metrics"]
    if (type(metrics) is not dict or len(metrics) > 32
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in metrics.values())):
        raise EvaluationError("Candidate aggregation metrics are invalid")
    card = {"format": "stk.federation-candidate/1", "run_id": run_id, "round": number,
            "spec_sha256": spec_sha, "spec": spec, "model": descriptor(model),
            "base_model": descriptor(base), "receipt_sha256": digest(receipt),
            "participants": list(peers), "num_examples": receipt["num_examples"]}
    return card, base_raw, raw


def heldout(node_root, dataset_id, lookup, spec):
    """Verify the registered immutable source mapping and actual held-out bytes."""
    if lookup is None:
        raise EvaluationError("A trusted owner dataset catalog is required")
    value = lookup(inputs.uuid(dataset_id))
    fields(value, {"role", "manifest", "source_sha256", "source"})
    if value["role"] != "holdout":
        raise EvaluationError("Evaluation requires a separately registered held-out role")
    source = value["source"]
    fields(source, {"project_id", "revision", "table_id", "features", "targets", "training_rows", "holdout_rows"})
    inputs.uuid(source["project_id"]), inputs.uuid(source["table_id"]), integer(source["revision"], 0, 2**53 - 1)
    if sha(value["source_sha256"]) != digest(source):
        raise EvaluationError("Held-out source plan differs from its registered identity")
    for role in ("training_rows", "holdout_rows"):
        rows = source[role]
        if type(rows) is not list or not 1 <= len(rows) <= 1000:
            raise EvaluationError("Held-out source rows are outside their bound")
        for row in rows:
            inputs.uuid(row)
        if len(set(rows)) != len(rows):
            raise EvaluationError("Source rows must have distinct stable identities")
    if (len(source["training_rows"]) + len(source["holdout_rows"]) > 1000
            or set(source["training_rows"]) & set(source["holdout_rows"])):
        raise EvaluationError("Training and held-out source row identities must be disjoint")
    for key in ("features", "targets"):
        if type(source[key]) is not list:
            raise EvaluationError("Invalid registered column mapping")
        for column in source[key]:
            fields(column, {"field_id", "name", "unit"})
            inputs.uuid(column["field_id"])
        if [{k: c[k] for k in ("name", "unit")} for c in source[key]] != spec[key]:
            raise EvaluationError("Held-out ordered columns and units differ from the frozen specification")
    manifest, raw = inputs.load(Path(node_root) / "datasets" / dataset_id)
    if (manifest != value["manifest"] or manifest["dataset_id"] != dataset_id
            or manifest["num_examples"] != len(source["holdout_rows"])
            or manifest["feature_names"] != [c["name"] for c in spec["features"]]
            or manifest["target_names"] != [c["name"] for c in spec["targets"]]):
        raise EvaluationError("Held-out capsule differs from its registered source plan")
    return value, raw


def rmse(spec, model_raw, dataset_raw):
    """Per-target f64 accumulation; values retain explicitly declared target units."""
    model = decode_arrays(model_raw, expected_kind="model", expected_layout=model_layout(spec))
    data = decode_arrays(dataset_raw, expected_kind="model")
    nf, nt = len(spec["features"]), len(spec["targets"])
    arrays = data["arrays"]
    if (len(arrays) != 2 or [a["name"] for a in arrays] != ["x", "y"]
            or any(a["dtype"] != "f64" or len(a["shape"]) != 2 for a in arrays)
            or arrays[0]["shape"][0] != arrays[1]["shape"][0]
            or arrays[0]["shape"][1] != nf or arrays[1]["shape"][1] != nt
            or not 1 <= arrays[0]["shape"][0] <= 1000):
        raise EvaluationError("Held-out matrix layout differs from the frozen specification")
    def values(array):
        return [x[0] for x in struct.iter_unpack("<f" if array["dtype"] == "f32" else "<d", array["data"])]
    weights, biases = (values(a) for a in model["arrays"])
    xs, ys = (values(a) for a in arrays)
    count = arrays[0]["shape"][0]
    scale, norms = math.sqrt(count), [0.] * nt
    try:
        for row in range(count):
            for target in range(nt):
                prediction = math.fsum(weights[feature * nt + target] * xs[row * nf + feature]
                                       for feature in range(nf)) + biases[target]
                error = prediction - ys[row * nt + target]
                if not math.isfinite(error):
                    raise ValueError
                norms[target] = math.hypot(norms[target], error / scale)
        if not all(math.isfinite(value) for value in norms):
            raise ValueError
    except (ValueError, OverflowError):
        raise EvaluationError("Linear inference produced a nonfinite result") from None
    return [{**column, "rmse": value} for column, value in zip(spec["targets"], norms)]
