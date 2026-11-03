"""Independent analytic comparisons; no papers, solvers, models or network."""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from suan.reproduction import ComparisonError, compare, verify
from suan.reproduction.comparison import FORMAT, PLAN_FORMAT, MAX_POINTS


def scalar(reference=10, actual=10, absolute=0, relative=0):
    return {"format": PLAN_FORMAT, "kind": "scalar",
            "reference": {"status": "succeeded", "unit": "K", "value": reference, "source": {"label": "self-authored reference"}},
            "actual": {"status": "succeeded", "unit": "K", "value": actual, "source": {"label": "self-authored result"}},
            "tolerance": {"absolute": absolute, "relative": relative}, "rule": {"criterion": "absolute_plus_relative"}}


def curve(reference=((0, 0), (1, 2), (2, 4)), actual=((0, 0), (1, 2), (2, 4)), *, alignment="exact", domain=(0, 2), absolute=0, relative=0):
    def series(values):
        return {"status": "succeeded", "x_unit": "s", "y_unit": "m", "source": {},
                "points": [{"x": x, "y": y, "status": "ok"} for x, y in values]}
    return {"format": PLAN_FORMAT, "kind": "curve", "reference": series(reference), "actual": series(actual),
            "tolerance": {"absolute": absolute, "relative": relative},
            "rule": {"criterion": "all_reference_points_and_full_domain", "alignment": alignment,
                     "domain": list(domain), "extrapolation": "forbid"}}


def test_scalar_boundary_uses_absolute_plus_reference_relative_error():
    result = compare(scalar(10, 11.5, absolute=0.5, relative=0.1))["result"]
    assert result["status"] == "passed" and result["complete"]
    assert result["points"][0]["allowed_error"] == 1.5
    assert result["metrics"]["max_absolute_error"] == result["metrics"]["rmse"] == 1.5
    assert compare(scalar(10, 11.500000000000002, 0.5, 0.1))["result"]["status"] == "failed"


def test_zero_reference_relative_tolerance_cannot_hide_error():
    result = compare(scalar(0, 0.25, absolute=0.2, relative=100))["result"]
    assert result["status"] == "failed" and result["points"][0]["allowed_error"] == 0.2
    assert compare(scalar(0, 0, relative=100))["result"]["status"] == "passed"


def test_negative_reference_uses_absolute_magnitude_for_relative_tolerance():
    result = compare(scalar(-10, -9, relative=0.1))["result"]
    assert result["status"] == "passed"
    assert result["points"][0]["signed_error"] == result["points"][0]["allowed_error"] == 1


@pytest.mark.parametrize("field,value,reason", [
    ("status", "failed", "actual_run_failed"), ("status", "missing", "actual_run_missing"),
    ("value", None, "actual_value_missing"), ("unit", None, "unit_unknown"),
    ("unit", "unspecified", "unit_unknown"), ("unit", "normalized", "unit_unknown"),
    ("unit", "degC", "unit_mismatch")])
def test_missing_failed_or_incompatible_scalar_is_indeterminate(field, value, reason):
    plan = scalar(); plan["actual"][field] = value
    result = compare(plan)["result"]
    assert result["status"] == "indeterminate" and not result["complete"]
    assert result["metrics"]["compared_samples"] == 0 and result["metrics"]["rmse"] is None
    assert reason in result["reasons"] and result["points"][0]["actual"] == plan["actual"]["value"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "10", 2**1024])
def test_invalid_scalar_numbers_fail_before_comparison(value):
    with pytest.raises(ComparisonError): compare(scalar(actual=value))


@pytest.mark.parametrize("absolute,relative", [(-1, 0), (0, -1), (False, 0), (0, None)])
def test_invalid_tolerances_are_input_errors(absolute, relative):
    with pytest.raises(ComparisonError): compare(scalar(absolute=absolute, relative=relative))


def test_curve_errors_match_analytic_rmse_and_keep_failed_points():
    plan = curve(reference=((0, 0), (1, 1), (2, 2)), actual=((0, 1), (1, -1), (2, 5)), absolute=2)
    result = compare(plan)["result"]
    assert result["status"] == "failed" and result["complete"]
    assert [p["signed_error"] for p in result["points"]] == [1, -2, 3]
    assert [p["status"] for p in result["points"]] == ["passed", "passed", "failed"]
    assert result["metrics"]["rmse"] == pytest.approx(math.sqrt(14/3))
    assert result["metrics"]["coverage"] == 1 and result["metrics"]["max_absolute_error"] == 3


def test_explicit_linear_alignment_recovers_known_line_without_extrapolation():
    result = compare(curve(actual=((0, 0), (2, 4)), alignment="linear"))["result"]
    assert result["status"] == "passed" and result["metrics"]["compared_samples"] == 3
    assert result["points"][1]["actual"] == 2
    assert result["points"][1]["actual_indices"] == [0, 1]
    assert result["metrics"]["rmse"] == 0


def test_exact_alignment_does_not_silently_interpolate():
    result = compare(curve(actual=((0, 0), (2, 4))))["result"]
    assert result["status"] == "indeterminate" and result["metrics"]["coverage"] == pytest.approx(2/3)
    assert result["points"][1]["reason"] == "actual_sample_missing"


def test_partial_overlap_cannot_pass_whole_requested_domain():
    plan = curve(reference=((0, 0), (1, 2), (2, 4)), actual=((1, 2), (2, 4)), alignment="linear")
    result = compare(plan)["result"]
    assert result["status"] == "indeterminate" and not result["complete"]
    assert "actual_domain_incomplete" in result["reasons"]
    assert result["points"][0]["reason"] == "extrapolation_forbidden"
    assert result["metrics"]["compared_samples"] == 2


def test_reference_samples_covering_only_subset_cannot_prove_whole_domain():
    result = compare(curve(reference=((1, 2), (2, 4)), actual=((0, 0), (2, 4)), alignment="linear"))["result"]
    assert result["metrics"]["coverage"] == 1
    assert result["status"] == "indeterminate" and "reference_domain_incomplete" in result["reasons"]


@pytest.mark.parametrize("axis,unit", [("x_unit", "ms"), ("y_unit", "unspecified")])
def test_curve_axis_units_require_explicit_identical_known_labels(axis, unit):
    plan = curve(); plan["actual"][axis] = unit
    result = compare(plan)["result"]
    assert result["status"] == "indeterminate" and result["metrics"]["compared_samples"] == 0
    assert ("unit_mismatch" if axis == "x_unit" else "unit_unknown") in result["reasons"]


def test_singleton_domain_is_an_explicit_single_sample_comparison():
    result = compare(curve(reference=((3, 6),), actual=((3, 6),), domain=(3, 3)))["result"]
    assert result["status"] == "passed" and result["metrics"]["compared_samples"] == 1


def test_explicit_subdomain_excludes_outside_points_without_discarding_frozen_inputs():
    plan = curve(actual=((0, 100), (1, 2), (2, 4)), domain=(1, 2))
    document = compare(plan)
    assert document["result"]["status"] == "passed"
    assert document["result"]["metrics"]["reference_samples"] == 2
    assert document["plan"]["actual"]["points"][0]["y"] == 100


def test_failed_unsampled_actual_point_still_blocks_full_domain_pass():
    plan = curve(reference=((0, 0), (2, 4)))
    plan["actual"]["points"][1]["status"] = "failed"
    result = compare(plan)["result"]
    assert result["metrics"]["coverage"] == 1
    assert result["status"] == "indeterminate" and "actual_point_failed" in result["reasons"]


def test_linear_alignment_does_not_bridge_failed_or_missing_measurements():
    plan = curve(reference=((0, 0), (0.5, 1), (2, 4)), alignment="linear")
    plan["actual"]["points"][1]["y"] = None
    result = compare(plan)["result"]
    assert result["points"][1]["status"] == "indeterminate"
    assert result["points"][1]["reason"] == "actual_value_missing"
    assert result["metrics"]["compared_samples"] == 2


def test_linear_alignment_cannot_bridge_an_unlocated_intervening_sample():
    plan = curve(alignment="linear")
    plan["actual"]["points"][1] = {"x": None, "y": None, "status": "missing"}
    result = compare(plan)["result"]
    assert result["status"] == "indeterminate"
    assert result["points"][1]["status"] == "indeterminate"
    assert result["points"][1]["reason"] == "actual_segment_unavailable"
    assert result["metrics"]["compared_samples"] == 2


@pytest.mark.parametrize("side", ["reference", "actual"])
def test_unlocated_points_and_empty_curves_remain_indeterminate(side):
    plan = curve(); plan[side]["points"][1]["x"] = None
    result = compare(plan)["result"]
    assert result["status"] == "indeterminate" and "point_position_missing" in result["reasons"]
    if side == "reference":
        assert result["metrics"]["reference_samples"] == 3
        assert result["points"][1]["reason"] == "reference_position_missing"
    plan[side]["points"] = []
    assert compare(plan)["result"]["status"] == "indeterminate"


@pytest.mark.parametrize("coordinates", [[(0, 0), (0, 1)], [(1, 1), (0, 0)]])
def test_duplicate_or_descending_coordinates_are_rejected(coordinates):
    with pytest.raises(ComparisonError) as caught: compare(curve(actual=coordinates))
    assert caught.value.code == "curve_order"


@pytest.mark.parametrize("change", [
    lambda p:p["rule"].update(extrapolation="linear"),
    lambda p:p["rule"].update(alignment="nearest"),
    lambda p:p["rule"].update(domain=[2, 0]),
    lambda p:p["rule"].update(criterion="any_point"),
    lambda p:p["rule"].update(allow_partial=True),
])
def test_unsupported_rules_do_not_weaken_full_domain_requirement(change):
    plan = curve(); change(plan)
    with pytest.raises(ComparisonError): compare(plan)


def test_large_values_use_safe_interpolation_and_scaled_rmse():
    plan = curve(reference=((0, 1e300), (1, 1e300), (2, 1e300)), actual=((0, 0), (2, 0)), alignment="linear")
    result = compare(plan)["result"]
    assert result["status"] == "failed"
    assert result["metrics"]["rmse"] == pytest.approx(1e300)
    assert math.isfinite(result["metrics"]["rmse"])
    # Slope/division intermediates are rational: huge opposite endpoints and
    # tiny x spacing must not overflow before reaching their finite midpoint.
    midpoint = curve(reference=((0, -1e300), (1e-300, 0), (2e-300, 1e300)),
                     actual=((0, -1e300), (2e-300, 1e300)), alignment="linear", domain=(0, 2e-300))
    assert compare(midpoint)["result"]["status"] == "passed"


@pytest.mark.parametrize("reference,actual,relative", [(-1e308, 1e308, 0), (1e308, 1e308, 1e308), (5e-324, 5e-324, 5e-324)])
def test_unrepresentable_error_or_tolerance_is_visible_not_infinity(reference, actual, relative):
    result = compare(scalar(reference, actual, relative=relative))["result"]
    assert result["status"] == "indeterminate" and "numeric_out_of_range" in result["reasons"]
    json.dumps(result, allow_nan=False)


def test_frozen_inputs_hashes_and_result_are_recomputable_and_detached():
    plan = scalar(0.1, 0.3, absolute=0.2)
    document = compare(plan)
    assert document["format"] == FORMAT and document["result"]["status"] == "passed"
    assert verify(document)
    encoded = json.dumps(document["plan"], sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    assert document["plan_sha256"] == hashlib.sha256(encoded).hexdigest()
    plan["actual"]["value"] = 99
    assert document["plan"]["actual"]["value"] == 0.3
    assert verify(json.loads(json.dumps(document)))


@pytest.mark.parametrize("target", ["input", "outcome", "point", "plan_hash", "result_hash", "format"])
def test_reopen_rejects_tampering_even_if_one_outer_hash_is_recomputed(target):
    document = compare(scalar())
    if target == "input": document["plan"]["actual"]["value"] = 11
    elif target == "outcome": document["result"]["status"] = "failed"
    elif target == "point": document["result"]["points"][0]["actual"] = 11
    elif target == "plan_hash": document["plan_sha256"] = "a"*64
    elif target == "result_hash": document["result_sha256"] = "a"*64
    else: document["format"] = "stk.reproduction-comparison/2"
    if target != "result_hash":
        body = {k:document[k] for k in ("format", "plan_sha256", "result")}
        document["result_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(ComparisonError): verify(document)


def test_source_strings_are_frozen_but_not_authenticated_by_comparison_hash():
    plan = scalar(); plan["reference"]["source"] = {"doi": "10.example/unverified", "approved": True}
    document = compare(plan)
    assert verify(document) and document["plan"]["reference"]["source"] == plan["reference"]["source"]
    # A new plan with a different caller claim is a new comparison, not a proof
    # that either claim or an external source has been verified.
    changed = copy.deepcopy(plan); changed["reference"]["source"]["doi"] = "10.example/another"
    assert compare(changed)["plan_sha256"] != document["plan_sha256"]


def test_recomputing_both_hashes_cannot_preserve_a_false_numeric_verdict():
    document = compare(scalar())
    document["plan"]["actual"]["value"] = 11
    encode = lambda value:json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    document["plan_sha256"] = hashlib.sha256(encode(document["plan"])).hexdigest()
    document["result_sha256"] = hashlib.sha256(encode({k:document[k] for k in ("format", "plan_sha256", "result")})).hexdigest()
    with pytest.raises(ComparisonError) as caught: verify(document)
    assert caught.value.code == "comparison_mismatch"


def test_maximum_supported_point_count_can_be_compared_and_reopened():
    plan = curve(reference=[(i, i) for i in range(MAX_POINTS)],
                 actual=[(i, i+1) for i in range(MAX_POINTS)], domain=(0, MAX_POINTS-1), absolute=1)
    document = compare(plan)
    assert document["result"]["status"] == "passed"
    assert document["result"]["metrics"]["compared_samples"] == MAX_POINTS
    assert document["result"]["metrics"]["rmse"] == 1
    assert verify(document)


def test_structural_numeric_and_point_budgets_fail_without_partial_result():
    with pytest.raises(ComparisonError) as count: compare(curve(actual=[(i, i) for i in range(MAX_POINTS+1)]))
    assert count.value.code == "budget"
    plan = scalar(); plan["reference"]["source"]["cycle"] = plan
    with pytest.raises(ComparisonError) as cycle: compare(plan)
    assert cycle.value.code == "budget"
    plan = scalar(); plan["actual"]["source"] = {"large": "a"*(2*1024*1024+1)}
    with pytest.raises(ComparisonError) as size: compare(plan)
    assert size.value.code == "budget"


def test_import_and_compare_do_not_load_scientific_or_execution_modules():
    script = '''import sys, builtins, json
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'numpy','torch','transformers'} or name.startswith(('suan.runtime','suan.models','suan.desktop_bridge')):
        raise AssertionError('Comparison imported a scientific or execution dependency')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
def audit(event, arguments):
    if event in {'socket.connect','subprocess.Popen','os.system'}:
        raise AssertionError('Comparison performed an external action')
sys.addaudithook(audit)
from suan.reproduction import compare, verify
assert verify(compare(json.loads(sys.argv[2])))
print('pure comparison passed')
'''
    completed = subprocess.run([sys.executable, '-I', '-c', script, str(Path(__file__).parents[1]), json.dumps(scalar())],
                               capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "pure comparison passed"
