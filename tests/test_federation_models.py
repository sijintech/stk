"""Explicit linear admission, retained publication receipts and ABA protection."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

from suan.federation import inputs
from suan.federation.evaluation import EvaluationError
from suan.federation.models import LinearModelRegistry, validate_result
from test_federation_evaluation import environment, evaluated, uid


def admission(request, evaluated_result):
    return {"evaluation_id": request["evaluation_id"], "receipt_sha256": evaluated_result["receipt_sha256"],
            "expected_active_version": request["expected_active_version"],
            "expected_active_generation": request["expected_active_generation"]}


def admit_first(registry, request, number=60):
    _, result = evaluated(registry, request, number)
    original = admission(request, result)
    accepted = registry.execute("models.admit", original, uid(number + 2))
    registry.execute("models.activate", activate_request(request["spec_sha256"], accepted["version"],
                     request["expected_active_version"], request["expected_active_generation"]), uid(number + 3))
    return original, accepted


def activate_request(spec_sha, version, active, generation):
    return {"spec_sha256": spec_sha, "version": version, "expected_active_version": active,
            "expected_active_generation": generation}


def test_passed_evaluation_only_enables_explicit_admit(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    _, measured = evaluated(registry, request)
    before = registry.read("models.list", {"spec_sha256": request["spec_sha256"]})
    assert before["versions"] == [] and before["active_version"] is None
    original = admission(request, measured)
    result = registry.execute("models.admit", original, uid(62))
    assert result["version"] == "v1" and result["active_generation"] == 0
    assert result["model"] == measured["plan"]["candidate"]["model"]
    assert validate_result("models.admit", original, result) == result
    after = registry.read("models.list", {"spec_sha256": request["spec_sha256"]})
    assert after["active_version"] is None and after["generation"] == 0
    assert after["versions"][0]["admission_operation_id"] == uid(62)
    assert b"model.bin" not in inputs.canonical(after) and str(tmp_path).encode() not in inputs.canonical(after)
    activated = registry.execute("models.activate", activate_request(request["spec_sha256"], "v1", None, 0), uid(63))
    assert activated["version"] == "v1" and activated["generation"] == 1
    current = registry.read("models.list", {"spec_sha256": request["spec_sha256"]})
    assert current["active_version"] == "v1" and current["generation"] == 1


def test_failed_gate_cannot_admit_even_with_valid_receipt(tmp_path):
    registry, request, _, _ = environment(tmp_path, weights=-2., bias=3.)
    _, measured = evaluated(registry, request)
    assert measured["state"] == "failed"
    with pytest.raises(EvaluationError, match="successful"):
        registry.execute("models.admit", admission(request, measured), uid(62))
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]})["versions"] == []


def test_multiple_admissions_do_not_change_active_cas_until_explicit_activation(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    _, measured = evaluated(registry, request)
    first = registry.execute("models.admit", admission(request, measured), uid(62))
    second = {**deepcopy(request), "evaluation_id": uid(51)}
    # Adding a version did not alter the active baseline/generation frozen by
    # this independently requested second evaluation and admission.
    _, later = evaluated(registry, second, 70)
    admitted = registry.execute("models.admit", admission(second, later), uid(72))
    current = registry.read("models.list", {"spec_sha256": request["spec_sha256"]})
    assert [x["version"] for x in current["versions"]] == ["v1", "v2"]
    assert current["active_version"] is None and current["generation"] == 0
    assert first["active_generation"] == admitted["active_generation"] == 0
    registry.execute("models.activate", activate_request(request["spec_sha256"], "v2", None, 0), uid(73))
    after = registry.read("models.list", {"spec_sha256": request["spec_sha256"]})
    assert after["active_version"] == "v2" and after["generation"] == 1
    # Recovering either old admission keeps the explicitly selected v2 active.
    assert registry.recover("models.admit", admission(request, measured), uid(62)) == first
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]}) == after


def test_admission_rejects_changed_frozen_model_or_receipt(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    _, measured = evaluated(registry, request)
    original = admission(request, measured)
    bad = {**original, "receipt_sha256": "f" * 64}
    with pytest.raises(EvaluationError):
        registry.execute("models.admit", bad, uid(62))
    path = registry._evaluation_path(request["evaluation_id"]) / "candidate.bin"
    inputs.write_bytes(path, b"substituted", replace=True)
    with pytest.raises(EvaluationError):
        registry.execute("models.admit", original, uid(63))
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]})["active_version"] is None


def test_baseline_aba_blocks_old_evaluation_and_explicit_rollback_is_cas(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    original, first = admit_first(registry, request)
    # A fresh plan freezes v1 at generation 1 and must retain that exact epoch.
    second = deepcopy(request)
    second.update(evaluation_id=uid(51), expected_active_version="v1", expected_active_generation=1)
    _, measured = evaluated(registry, second, 70)
    assert measured["metrics"]["baseline"][0]["rmse"] == 0
    second_admit = admission(second, measured)
    second_receipt = registry.execute("models.admit", second_admit, uid(72))
    assert second_receipt["version"] == "v2" and second_receipt["active_generation"] == 1
    registry.execute("models.activate", activate_request(request["spec_sha256"], "v2", "v1", 1), uid(73))
    rollback = activate_request(request["spec_sha256"], "v1", "v2", 2)
    rolled_back = registry.execute("models.activate", rollback, uid(74))
    assert rolled_back["version"] == "v1" and rolled_back["generation"] == 3
    # The visible active version is back to v1, but generation 1 is stale.
    stale = deepcopy(second_admit)
    with pytest.raises(EvaluationError, match="generation changed"):
        registry.execute("models.admit", stale, uid(75))
    with pytest.raises(EvaluationError, match="generation changed"):
        registry.execute("models.activate", rollback, uid(76))
    # Re-query/recover of the historical admission never reactivates v2.
    assert registry.execute("models.admit", second_admit, uid(72)) == second_receipt
    assert registry.recover("models.admit", second_admit, uid(72)) == second_receipt
    current = registry.read("models.list", {"spec_sha256": request["spec_sha256"]})
    assert current["active_version"] == "v1" and current["generation"] == 3
    assert registry.execute("models.admit", original, uid(62)) == first


def test_candidate_must_not_regress_any_target_against_frozen_active_baseline(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    admit_first(registry, request)
    # A candidate's absolute gate can pass yet fail against an exact zero-error active baseline.
    other, worse, _, _ = environment(tmp_path / "second", weights=1.99, bias=-1.)
    # Keep this registry and active model; use the second coherent candidate source.
    registry.coordinator_root = other.coordinator_root
    # This synthetic fixture uses the same exact heldout identities and values;
    # only the coherent coordinator candidate differs.
    worse.update(evaluation_id=uid(51), expected_active_version="v1", expected_active_generation=1)
    _, measured = evaluated(registry, worse, 70)
    assert measured["state"] == "failed"
    assert measured["gate"][0]["absolute_ok"] and not measured["gate"][0]["baseline_ok"]


def test_lost_admit_ack_recovers_exact_postimage_without_new_publication(tmp_path, monkeypatch):
    registry, request, _, _ = environment(tmp_path)
    _, measured = evaluated(registry, request)
    original = admission(request, measured)
    finish = registry._finish
    def lost(operation, result):
        if operation["method"] == "models.admit":
            raise OSError("ack lost after registry commit")
        return finish(operation, result)
    monkeypatch.setattr(registry, "_finish", lost)
    with pytest.raises(EvaluationError):
        registry.execute("models.admit", original, uid(62))
    reopened = LinearModelRegistry(registry.node_root)
    current = reopened.read("models.list", {"spec_sha256": request["spec_sha256"]})
    assert len(current["versions"]) == 1 and current["generation"] == 0 and current["active_version"] is None
    with pytest.raises(EvaluationError, match="uncertain"):
        reopened.execute("models.admit", original, uid(62))
    receipt = reopened.recover("models.admit", original, uid(62))
    assert receipt["version"] == "v1"
    assert reopened.read("models.list", {"spec_sha256": request["spec_sha256"]}) == current


def test_crash_before_publication_leaves_orphan_and_cannot_replay(tmp_path, monkeypatch):
    registry, request, _, _ = environment(tmp_path)
    _, measured = evaluated(registry, request)
    original = admission(request, measured)
    write = registry._write
    def fail_registry(path, value, **kwargs):
        if path.name == "registry.json" and value["versions"]:
            raise OSError("injected publication crash")
        return write(path, value, **kwargs)
    monkeypatch.setattr(registry, "_write", fail_registry)
    with pytest.raises(EvaluationError):
        registry.execute("models.admit", original, uid(62))
    reopened = LinearModelRegistry(registry.node_root)
    with pytest.raises(EvaluationError):
        reopened.recover("models.admit", original, uid(62))
    assert reopened.read("models.list", {"spec_sha256": request["spec_sha256"]})["active_version"] is None
    # A new explicitly reviewed operation may publish, but may never reuse orphan v1.
    result = reopened.execute("models.admit", original, uid(63))
    assert result["version"] == "v2"


def test_concurrent_active_cas_only_accepts_one_explicit_activation(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    admit_first(registry, request)
    activation = activate_request(request["spec_sha256"], "v1", "v1", 1)
    def act(index):
        other = LinearModelRegistry(registry.node_root)
        try:
            return other.execute("models.activate", activation, uid(80 + index))
        except EvaluationError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(act, (0, 1)))
    assert sum(x is not None for x in results) == 1
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]})["generation"] == 2


def test_same_operation_identity_cannot_bind_another_request(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    registry.execute("evaluations.prepare", request, uid(60))
    changed = deepcopy(request)
    changed["thresholds"][0]["max_rmse"] = .5
    with pytest.raises(EvaluationError, match="different linear request"):
        registry.execute("evaluations.prepare", changed, uid(60))


def test_activation_response_is_closed_and_pinned_to_original_cas(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    admit_first(registry, request)
    activation = activate_request(request["spec_sha256"], "v1", "v1", 1)
    receipt = registry.execute("models.activate", activation, uid(80))
    assert validate_result("models.activate", activation, receipt) == receipt
    for key, value in (("generation", True), ("spec_sha256", "f" * 64), ("version", "v2"), ("path", "private")):
        damaged = {**receipt, key: value}
        with pytest.raises(EvaluationError):
            validate_result("models.activate", activation, damaged)


def test_actual_process_exit_after_publication_recovers_without_reactivation(tmp_path):
    import json
    import os
    import subprocess
    import sys
    registry, request, _, _ = environment(tmp_path)
    _, measured = evaluated(registry, request)
    original = admission(request, measured)
    script = '''
import json, os, sys
from suan.federation.models import LinearModelRegistry
registry = LinearModelRegistry(sys.argv[1])
write = registry._write
def crash_after_publication(path, value, **kwargs):
    result = write(path, value, **kwargs)
    if path.name == "registry.json" and value["versions"]:
        os._exit(73)
    return result
registry._write = crash_after_publication
registry.execute("models.admit", json.loads(sys.argv[2]), sys.argv[3])
'''
    environment_vars = {"STK_TOKEN_PLAN_API_KEY": ""}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"):
        if key in os.environ:
            environment_vars[key] = os.environ[key]
    process = subprocess.run([sys.executable, "-c", script, str(registry.node_root), json.dumps(original), uid(62)],
                             env=environment_vars, capture_output=True, timeout=15)
    assert process.returncode == 73 and process.stdout == process.stderr == b""
    reopened = LinearModelRegistry(registry.node_root)
    receipt = reopened.recover("models.admit", original, uid(62))
    assert receipt["version"] == "v1"
    rollback = activate_request(request["spec_sha256"], "v1", None, 0)
    reopened.execute("models.activate", rollback, uid(63))
    assert reopened.recover("models.admit", original, uid(62)) == receipt
    assert reopened.read("models.list", {"spec_sha256": request["spec_sha256"]})["generation"] == 1


def test_model_only_recovery_and_rpc_get_can_validate_shape_without_original_request(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    original, receipt = admit_first(registry, request)
    assert validate_result("models.admit", None, receipt) == receipt
    value = registry.read("evaluations.get", {"evaluation_id": request["evaluation_id"]})
    assert validate_result("evaluations.get", None, value) == value
    candidate = registry.read("candidates.get", {"run_id": request["run_id"], "round": 1})
    assert validate_result("candidates.get", None, candidate) == candidate
    damaged = deepcopy(value)
    damaged["gate"][0]["passed"] = 1
    # Even a coherently recomputed outer receipt cannot turn an integer into a boolean.
    from suan.federation.evaluation import digest
    damaged["receipt_sha256"] = digest(LinearModelRegistry._evaluation_receipt(damaged["plan"], damaged))
    with pytest.raises(EvaluationError):
        validate_result("evaluations.get", None, damaged)


def test_missing_registry_cannot_silently_reset_admitted_generation(tmp_path):
    registry, request, _, _ = environment(tmp_path)
    admit_first(registry, request)
    registry._registry_path(request["spec_sha256"]).unlink()
    with pytest.raises(EvaluationError, match="history is missing"):
        registry.read("models.list", {"spec_sha256": request["spec_sha256"]})


def test_cross_process_activation_cas_accepts_only_one_original_generation(tmp_path):
    import json
    import os
    import subprocess
    import sys
    registry, request, _, _ = environment(tmp_path)
    admit_first(registry, request)
    activation = activate_request(request["spec_sha256"], "v1", "v1", 1)
    script = '''
import json, sys
from suan.federation.models import LinearModelRegistry
from suan.federation.evaluation import EvaluationError
registry = LinearModelRegistry(sys.argv[1])
assert sys.stdin.readline() == "go\\n"
try:
    registry.execute("models.activate", json.loads(sys.argv[2]), sys.argv[3])
    print("accepted")
except EvaluationError:
    print("conflict")
'''
    environment_vars = {"STK_TOKEN_PLAN_API_KEY": ""}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"):
        if key in os.environ:
            environment_vars[key] = os.environ[key]
    processes = [subprocess.Popen([sys.executable, "-c", script, str(registry.node_root),
                                  json.dumps(activation), uid(90 + i)], env=environment_vars,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(2)]
    try:
        for process in processes:
            process.stdin.write(b"go\n")
            process.stdin.flush()
        results = [process.communicate(timeout=15) for process in processes]
        assert sorted(out.strip() for out, _ in results) == [b"accepted", b"conflict"]
        assert all(process.returncode == 0 for process in processes)
        assert all(error == b"" for _, error in results)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]})["generation"] == 2


def test_storage_budget_rejects_new_effect_but_preserves_admitted_read(tmp_path, monkeypatch):
    registry, request, _, _ = environment(tmp_path)
    admit_first(registry, request)
    current = registry.read("models.list", {"spec_sha256": request["spec_sha256"]})
    import suan.federation.models as models
    monkeypatch.setattr(models, "MAX_STORAGE_BYTES", 1)
    activation = activate_request(request["spec_sha256"], "v1", "v1", 1)
    with pytest.raises(EvaluationError, match="capacity"):
        registry.execute("models.activate", activation, uid(90))
    assert registry.read("models.list", {"spec_sha256": request["spec_sha256"]}) == current
