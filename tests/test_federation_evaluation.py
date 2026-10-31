"""Synthetic exact arithmetic and frozen provenance; no model/network requests."""
from copy import deepcopy
import hashlib
import struct
from uuid import UUID

import pytest

from suan.federation import inputs
from suan.federation.coordinator import FederationCoordinator
from suan.federation.evaluation import EvaluationError, digest, rmse
from suan.federation.models import LinearModelRegistry, validate_result
from suan.federation.protocol import model_layout, training_spec_sha256
from suan.federation.updates import decode_arrays, encode_arrays
from test_federation_protocol import manifest, spec


def uid(number):
    return str(UUID(int=number))


def linear_model(settings, weights=2., bias=-1.):
    weights = weights if type(weights) is list else [weights]
    bias = bias if type(bias) is list else [bias]
    code = "f" if settings["dtype"] == "f32" else "d"
    return encode_arrays([{**layout, "data": struct.pack("<" + code * len(values), *values)}
                          for layout, values in zip(model_layout(settings), (weights, bias))], kind="model")


def environment(tmp_path, *, weights=2., bias=-1., settings=None, xs=None, ys=None):
    settings = settings or spec()
    xs, ys = xs or [[-2.], [0.], [3.]], ys or [[-5.], [-1.], [5.]]
    node, coord_root = tmp_path / "node", tmp_path / "coordinator"
    dataset_id = uid(30)
    frozen = inputs.capture(node / "datasets" / dataset_id, dataset_id, xs, ys,
                            feature_names=[c["name"] for c in settings["features"]],
                            target_names=[c["name"] for c in settings["targets"]])
    source = {"project_id": uid(40), "revision": 8, "table_id": uid(41),
              "features": [{"field_id": uid(100 + i), **c} for i, c in enumerate(settings["features"])],
              "targets": [{"field_id": uid(200 + i), **c} for i, c in enumerate(settings["targets"])],
              "training_rows": [uid(400), uid(401)], "holdout_rows": [uid(500 + i) for i in range(len(xs))]}
    registered = {"role": "holdout", "manifest": frozen, "source": source, "source_sha256": digest(source)}
    run = manifest()
    run["spec_sha256"] = training_spec_sha256(settings)
    coordinator = FederationCoordinator(coord_root, None, None)
    base = linear_model(settings, weights=[0.] * (len(settings["features"]) * len(settings["targets"])),
                        bias=[0.] * len(settings["targets"]))
    coordinator.create(run, settings, base)
    current = coordinator.prepare_round(run["run_id"])
    raw = linear_model(settings, weights, bias)
    receipt = {"format": "stk.federation-aggregate-result/1", "run_id": run["run_id"], "round": 1,
               "source_model_sha256": hashlib.sha256(base).hexdigest(), "spec_sha256": run["spec_sha256"],
               "participants": [p["participant_id"] for p in run["participants"]],
               "model_sha256": hashlib.sha256(raw).hexdigest(), "model_bytes": len(raw), "num_examples": 21,
               "framework": {"name": "flwr", "version": "1.42.0"}, "metrics": {"loss": .1}}
    path = coord_root / run["run_id"] / "1"
    inputs.write_bytes(path / "candidate.bin", raw)
    current.update(state="aggregated", receipt=receipt, candidate_sha256=receipt["model_sha256"])
    coordinator._save(path / "round.json", current)
    lookup = lambda identity: deepcopy(registered) if identity == dataset_id else None
    registry = LinearModelRegistry(node, coord_root, lookup_dataset=lookup)
    card = registry.read("candidates.get", {"run_id": run["run_id"], "round": 1})
    request = {"evaluation_id": uid(50), "run_id": run["run_id"], "round": 1, "dataset_id": dataset_id,
               "dataset_sha256": frozen["dataset_sha256"], "candidate_sha256": card["model"]["sha256"],
               "base_model_sha256": card["base_model"]["sha256"], "spec_sha256": run["spec_sha256"],
               "thresholds": [{**target, "max_rmse": .1} for target in settings["targets"]],
               "expected_active_version": None, "expected_active_generation": 0}
    return registry, request, registered, coordinator


def evaluated(registry, request, number=60):
    prepared = registry.execute("evaluations.prepare", request, uid(number))
    result = registry.execute("evaluations.evaluate", {"evaluation_id": request["evaluation_id"],
                              "plan_sha256": prepared["plan_sha256"]}, uid(number + 1))
    return prepared, result


def test_constructor_and_empty_registry_reads_are_passive(tmp_path):
    registry = LinearModelRegistry(tmp_path / "absent")
    expected = {"format": "stk.federation-linear-models/1", "spec_sha256": "a" * 64,
                "active_version": None, "generation": 0, "versions": []}
    assert registry.read("models.list", {"spec_sha256": "a" * 64}) == expected
    with pytest.raises(EvaluationError):
        registry.read("candidates.get", {"run_id": uid(1), "round": 1})
    assert not registry.node_root.exists()


@pytest.mark.parametrize("dtype", ["f32", "f64"])
def test_exact_linear_heldout_metrics_do_not_fit_or_activate(tmp_path, dtype):
    settings = spec()
    settings["dtype"] = dtype
    registry, request, _, _ = environment(tmp_path, settings=settings)
    prepared, result = evaluated(registry, request)
    assert prepared["state"] == "prepared" and prepared["metrics"] is None
    assert result["state"] == "passed" and result["metrics"]["candidate"][0]["rmse"] == 0
    assert result["metrics"]["base"][0]["rmse"] == pytest.approx((51 / 3) ** .5)
    assert result["metrics"]["baseline"] == result["metrics"]["base"]
    assert result["gate"] == [{"name": "y", "unit": "1", "max_rmse": .1,
                                "absolute_ok": True, "baseline_ok": True, "passed": True}]
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]})["active_version"] is None
    wire = inputs.canonical(result)
    assert str(tmp_path).encode() not in wire and b"data.bin" not in wire and b'"x":' not in wire


def test_multi_target_units_and_independent_per_target_gate(tmp_path):
    settings = spec()
    settings["targets"] = [{"name": "y", "unit": "K"}, {"name": "z", "unit": "Pa"}]
    registry, request, _, _ = environment(tmp_path, settings=settings, weights=[2., 3.], bias=[-1., 0.],
                                           ys=[[-5., -5.], [-1., 1.], [5., 10.]])
    request["thresholds"] = [{"name": "y", "unit": "K", "max_rmse": 0.}, {"name": "z", "unit": "Pa", "max_rmse": .5}]
    _, result = evaluated(registry, request)
    assert result["state"] == "failed"
    assert [t["rmse"] for t in result["metrics"]["candidate"]] == pytest.approx([0., 1.])
    assert [t["passed"] for t in result["gate"]] == [True, False]


@pytest.mark.parametrize("change", ["units", "overlap", "role", "source_sha", "capsule_sha", "candidate", "threshold_order"])
def test_prepare_rejects_substituted_or_nonindependent_inputs(tmp_path, change):
    registry, request, registered, coordinator = environment(tmp_path)
    if change == "units":
        registered["source"]["features"][0]["unit"] = "K"
        registered["source_sha256"] = digest(registered["source"])
    elif change == "overlap":
        registered["source"]["holdout_rows"][0] = registered["source"]["training_rows"][0]
        registered["source_sha256"] = digest(registered["source"])
    elif change == "role":
        registered["role"] = "training"
    elif change == "source_sha":
        registered["source_sha256"] = "f" * 64
    elif change == "capsule_sha":
        request["dataset_sha256"] = "f" * 64
    elif change == "candidate":
        path = coordinator.root / request["run_id"] / "1" / "candidate.bin"
        inputs.write_bytes(path, linear_model(spec(), 9., 2.), replace=True)
    else:
        request["thresholds"][0]["name"] = "unreviewed"
    with pytest.raises(EvaluationError):
        registry.execute("evaluations.prepare", request, uid(70))
    assert not registry._evaluation_path(request["evaluation_id"]).exists()


def test_frozen_plan_is_independent_of_later_working_dataset_changes(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    prepared = registry.execute("evaluations.prepare", request, uid(60))
    path = registry.node_root / "datasets" / request["dataset_id"] / "data.bin"
    inputs.write_bytes(path, b"changed working capsule", replace=True)
    result = registry.execute("evaluations.evaluate", {"evaluation_id": request["evaluation_id"],
                              "plan_sha256": prepared["plan_sha256"]}, uid(61))
    assert result["state"] == "passed"


def test_eval_checks_frozen_bytes_and_does_not_repeat_interrupted_attempt(tmp_path, monkeypatch):
    registry, request, _, _ = environment(tmp_path)
    prepared = registry.execute("evaluations.prepare", request, uid(60))
    evaluate = {"evaluation_id": request["evaluation_id"], "plan_sha256": prepared["plan_sha256"]}
    import suan.federation.models as models
    calls = []
    def crash(*args):
        calls.append(1)
        raise OSError("private path must not escape")
    monkeypatch.setattr(models, "rmse", crash)
    with pytest.raises(EvaluationError) as failure:
        registry.execute("evaluations.evaluate", evaluate, uid(61))
    assert "private path" not in str(failure.value)
    reopened = LinearModelRegistry(registry.node_root)
    assert reopened.read("evaluations.get", {"evaluation_id": request["evaluation_id"]})["state"] == "uncertain"
    with pytest.raises(EvaluationError):
        reopened.execute("evaluations.evaluate", evaluate, uid(61))
    with pytest.raises(EvaluationError):
        reopened.recover("evaluations.evaluate", evaluate, uid(61))
    assert len(calls) == 1


def test_nonfinite_inference_is_failed_evaluation_not_admissible_metrics(tmp_path):
    registry, request, _, _ = environment(tmp_path, weights=1e308)
    _, result = evaluated(registry, request)
    assert result["state"] == "failed" and result["metrics"] is None and result["gate"] == []
    assert result["receipt_sha256"]


def test_result_validator_rejects_private_fields_wrong_types_and_rebinding(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    _, result = evaluated(registry, request)
    get = {"evaluation_id": request["evaluation_id"]}
    assert validate_result("evaluations.get", get, result) == result
    for field, value in (("path", "private"), ("evaluation_id", uid(999)), ("state", [])):
        damaged = deepcopy(result)
        damaged[field] = value
        with pytest.raises(EvaluationError):
            validate_result("evaluations.get", get, damaged)
    damaged = deepcopy(result)
    damaged["gate"][0]["passed"] = 1
    with pytest.raises(EvaluationError):
        validate_result("evaluations.get", get, damaged)


def test_request_schema_rejects_remote_paths_without_creating_state(tmp_path):
    registry = LinearModelRegistry(tmp_path / "absent")
    for name in ("path", "root", "argv", "module"):
        with pytest.raises(EvaluationError):
            registry.execute("models.activate", {"spec_sha256": "a" * 64, "version": "v1",
                             "expected_active_version": None, "expected_active_generation": 0, name: "forbidden"}, uid(1))
    assert not registry.node_root.exists()


def test_frozen_payload_symlink_is_rejected_without_private_path_error(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    prepared = registry.execute("evaluations.prepare", request, uid(60))
    path = registry._evaluation_path(request["evaluation_id"]) / "dataset.bin"
    other = tmp_path / "private-original.bin"
    other.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(other)
    except OSError:
        pytest.skip("symlink unavailable on this host")
    with pytest.raises(EvaluationError) as failure:
        registry.execute("evaluations.evaluate", {"evaluation_id": request["evaluation_id"],
                         "plan_sha256": prepared["plan_sha256"]}, uid(61))
    assert str(tmp_path) not in str(failure.value)


def test_evaluation_retention_quota_keeps_existing_readable(tmp_path, monkeypatch):
    registry, request, _, _ = environment(tmp_path)
    import suan.federation.models as models
    monkeypatch.setattr(models, "MAX_EVALUATIONS", 1)
    first = registry.execute("evaluations.prepare", request, uid(60))
    second = {**request, "evaluation_id": uid(51)}
    with pytest.raises(EvaluationError, match="quota"):
        registry.execute("evaluations.prepare", second, uid(61))
    assert registry.read("evaluations.get", {"evaluation_id": request["evaluation_id"]}) == first


def test_evaluation_and_registry_imports_need_no_algorithm_or_network_libraries(tmp_path):
    import os
    import subprocess
    import sys
    script = '''
import pathlib, sys
from suan.federation.models import LinearModelRegistry
value = LinearModelRegistry(pathlib.Path(sys.argv[1]))
assert value.read("models.list", {"spec_sha256":"a"*64})["generation"] == 0
assert not value.node_root.exists()
assert not {"torch", "flwr", "numpy", "httpx"}.intersection(sys.modules)
'''
    environment_vars = {"STK_TOKEN_PLAN_API_KEY": ""}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"):
        if key in os.environ:
            environment_vars[key] = os.environ[key]
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "absent")],
                            env=environment_vars, capture_output=True, timeout=15)
    assert result.returncode == 0 and result.stdout == result.stderr == b""


def test_approved_training_capsule_cannot_be_reused_as_heldout(tmp_path):
    registry, request, _, coordinator = environment(tmp_path)
    path = coordinator.root / request["run_id"] / "run.json"
    run = inputs.read_json(path)
    run["manifest"]["participants"][0]["dataset_sha256"] = request["dataset_sha256"]
    inputs.write_json(path, run, replace=True)
    with pytest.raises(EvaluationError, match="training capsule"):
        registry.execute("evaluations.prepare", request, uid(60))
