"""Bounded scalar/curve comparison; caller evidence remains caller evidence."""
from bisect import bisect_left
from fractions import Fraction
import hashlib
import json
import math

PLAN_FORMAT = "stk.reproduction-comparison-plan/1"
FORMAT = "stk.reproduction-comparison/1"
MAX_POINTS = 4096
MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 12
MAX_NODES = 300000
_UNKNOWN_UNITS = {"", "unknown", "unspecified", "normalized", "none"}


class ComparisonError(ValueError):
    """Invalid input shape, budgets or unsupported comparison rule."""
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _error(code="invalid_input", message="Invalid reproduction comparison input"):
    raise ComparisonError(code, message)


def _number(value):
    if type(value) not in (int, float): _error()
    if type(value) is int and value.bit_length() > 1024: _error("numeric_input", "Numeric input is outside the finite binary64 range")
    try: finite = math.isfinite(float(value))
    except OverflowError: finite = False
    if not finite: _error("numeric_input", "Numeric inputs must be finite binary64 values")
    return Fraction(str(value))


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _clone(value):
    # Bound caller-owned JSON before encoding; cycles are rejected by depth and
    # unsupported objects never invoke caller-defined serialization hooks.
    pending = [(value, 0)]; count = 0; string_bytes = 0
    while pending:
        item, depth = pending.pop(); count += 1
        if depth > MAX_DEPTH or count > MAX_NODES: _error("budget", "Comparison JSON exceeds its structural budget")
        if type(item) is dict:
            if len(item) > MAX_NODES: _error("budget", "Comparison object is too large")
            for key, child in item.items():
                if type(key) is not str: _error()
                pending.append((key, depth + 1)); pending.append((child, depth + 1))
        elif type(item) is list:
            if len(item) > MAX_NODES: _error("budget", "Comparison list is too large")
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > MAX_BYTES: _error("budget", "Comparison text is too large")
            try: string_bytes += len(item.encode("utf-8"))
            except UnicodeEncodeError: _error()
            if string_bytes > MAX_BYTES: _error("budget", "Comparison text is too large")
        elif type(item) in (int, float): _number(item)
        elif item is None or type(item) is bool: pass
        else: _error()
    encoded = _canonical(value)
    if len(encoded) > MAX_BYTES: _error("budget", "Comparison JSON exceeds its byte budget")
    return json.loads(encoded)


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys): _error()


def _unit(value):
    if value is None: return None
    if type(value) is not str or len(value) > 128 or any(ord(c) < 32 for c in value): _error()
    return value


def _status(value):
    if value not in ("succeeded", "failed", "missing") or type(value) is not str: _error()


def _source(value):
    if type(value) is not dict: _error()
    # Arbitrary bounded JSON is retained for later authenticated integration.
    # Its DOI, digest, label or locator is never treated as authority here.


def _series(value):
    _shape(value, ("status", "x_unit", "y_unit", "points", "source"))
    _status(value["status"]); _unit(value["x_unit"]); _unit(value["y_unit"]); _source(value["source"])
    points = value["points"]
    if type(points) is not list or len(points) > MAX_POINTS: _error("budget", "A curve supports at most 4096 points")
    previous = None
    for point in points:
        _shape(point, ("x", "y", "status"))
        if type(point["status"]) is not str or point["status"] not in ("ok", "failed", "missing"): _error()
        if point["x"] is not None:
            x = _number(point["x"])
            if previous is not None and x <= previous: _error("curve_order", "Curve coordinates must be strictly increasing without duplicates")
            previous = x
        if point["y"] is not None: _number(point["y"])


def _plan(value):
    plan = _clone(value)
    _shape(plan, ("format", "kind", "reference", "actual", "tolerance", "rule"))
    if plan["format"] != PLAN_FORMAT or plan["kind"] not in ("scalar", "curve"): _error()
    _shape(plan["tolerance"], ("absolute", "relative"))
    for key in ("absolute", "relative"):
        if _number(plan["tolerance"][key]) < 0: _error("tolerance", "Tolerances must be nonnegative")
    if plan["kind"] == "scalar":
        _shape(plan["rule"], ("criterion",))
        if plan["rule"]["criterion"] != "absolute_plus_relative": _error("rule", "Unsupported scalar comparison rule")
        for side in ("reference", "actual"):
            item = plan[side]; _shape(item, ("status", "unit", "value", "source"))
            _status(item["status"]); _unit(item["unit"]); _source(item["source"])
            if item["value"] is not None: _number(item["value"])
    else:
        _shape(plan["rule"], ("criterion", "alignment", "domain", "extrapolation"))
        rule = plan["rule"]
        if (rule["criterion"] != "all_reference_points_and_full_domain" or rule["alignment"] not in ("exact", "linear")
                or rule["extrapolation"] != "forbid"): _error("rule", "Unsupported curve comparison rule")
        if type(rule["domain"]) is not list or len(rule["domain"]) != 2: _error()
        if _number(rule["domain"][0]) > _number(rule["domain"][1]): _error("domain", "Comparison domain must be increasing")
        _series(plan["reference"]); _series(plan["actual"])
    return plan


def _units(reference, actual):
    if reference is None or actual is None or reference.strip().casefold() in _UNKNOWN_UNITS or actual.strip().casefold() in _UNKNOWN_UNITS:
        return "unit_unknown"
    if reference != actual: return "unit_mismatch"
    return None


def _float(value):
    try: number = float(value)
    except (OverflowError, ValueError): return None
    if not math.isfinite(number) or (value != 0 and number == 0): return None
    return number


def _point(index, x, reference, actual, indices, tolerance, reason=None):
    point = {"reference_index": index, "x": x, "reference": reference, "actual": actual,
             "actual_indices": indices, "status": "indeterminate", "reason": reason,
             "signed_error": None, "absolute_error": None, "allowed_error": None}
    if reason is not None: return point
    expected, observed = _number(reference), actual if isinstance(actual, Fraction) else _number(actual)
    error = observed - expected
    allowed = _number(tolerance["absolute"]) + _number(tolerance["relative"]) * abs(expected)
    values = [_float(observed), _float(error), _float(abs(error)), _float(allowed)]
    if any(v is None for v in values):
        point.update(actual=None if isinstance(actual, Fraction) else actual, reason="numeric_out_of_range")
        return point
    point.update(actual=values[0], signed_error=values[1], absolute_error=values[2], allowed_error=values[3],
                 status="passed" if abs(error) <= allowed else "failed", reason=None)
    return point


def _global_reason(reference, actual, units):
    for name, item in (("reference", reference), ("actual", actual)):
        if item["status"] != "succeeded": return name + "_run_" + item["status"]
    for ref_unit, actual_unit in units:
        reason = _units(ref_unit, actual_unit)
        if reason: return reason
    return None


def _point_reason(point, side):
    if point["status"] != "ok": return side + "_point_" + point["status"]
    if point["y"] is None: return side + "_value_missing"
    return None


def _curve(plan):
    reference, actual, rule = plan["reference"], plan["actual"], plan["rule"]
    reason = _global_reason(reference, actual, ((reference["x_unit"], actual["x_unit"]), (reference["y_unit"], actual["y_unit"])))
    left, right = map(_number, rule["domain"])
    reasons = [reason] if reason else []
    if any(p["x"] is None for side in (reference, actual) for p in side["points"]): reasons.append("point_position_missing")
    for name, side in (("reference", reference), ("actual", actual)):
        xs = [_number(p["x"]) for p in side["points"] if p["x"] is not None]
        if not xs or xs[0] > left or xs[-1] < right: reasons.append(name + "_domain_incomplete")
    actual_points = [(i, p) for i, p in enumerate(actual["points"]) if p["x"] is not None]
    actual_x = [_number(p["x"]) for _, p in actual_points]
    points = []
    for index, ref in enumerate(reference["points"]):
        if ref["x"] is None:
            points.append(_point(index, None, ref["y"], None, [], plan["tolerance"], reason or "reference_position_missing"))
            continue
        if not left <= _number(ref["x"]) <= right: continue
        x = _number(ref["x"]); position = bisect_left(actual_x, x)
        failure = reason or _point_reason(ref, "reference")
        observed, indices = None, []
        if position < len(actual_x) and actual_x[position] == x:
            i, found = actual_points[position]; indices = [i]
            failure = failure or _point_reason(found, "actual")
            observed = found["y"]
        elif rule["alignment"] == "exact": failure = failure or "actual_sample_missing"
        elif position == 0 or position == len(actual_x): failure = failure or "extrapolation_forbidden"
        else:
            i0, p0 = actual_points[position-1]; i1, p1 = actual_points[position]; indices = [i0, i1]
            failure = failure or _point_reason(p0, "actual") or _point_reason(p1, "actual")
            if i1 != i0 + 1: failure = failure or "actual_segment_unavailable"
            if failure is None:
                x0, x1 = actual_x[position-1], actual_x[position]
                observed = _number(p0["y"]) + (x-x0)*(_number(p1["y"])-_number(p0["y"]))/ (x1-x0)
        points.append(_point(index, ref["x"], ref["y"], observed, indices, plan["tolerance"], failure))
    if not points: reasons.append("reference_samples_missing")
    # Failed actual samples remain in the frozen plan, and make the whole-domain
    # verdict indeterminate even when the reference grid did not sample them.
    for p in actual["points"]:
        if p["x"] is not None and left <= _number(p["x"]) <= right:
            failure = _point_reason(p, "actual")
            if failure: reasons.append(failure)
    return _summary(points, reasons)


def _summary(points, reasons):
    reasons = sorted(set(reasons + [p["reason"] for p in points if p["reason"] is not None]))
    known = [p for p in points if p["status"] != "indeterminate"]
    errors = [p["absolute_error"] for p in known]
    maximum = max(errors) if errors else None
    rmse = None if not errors else 0.0 if maximum == 0 else maximum * math.sqrt(math.fsum((e/maximum)**2 for e in errors)/len(errors))
    failed = sum(p["status"] == "failed" for p in points)
    incomplete = bool(reasons) or len(known) != len(points) or not points
    return {"status": "indeterminate" if incomplete else "failed" if failed else "passed",
            "complete": not incomplete, "reasons": reasons, "points": points,
            "metrics": {"reference_samples": len(points), "compared_samples": len(known),
                        "coverage": len(known)/len(points) if points else 0.0,
                        "passed_samples": sum(p["status"] == "passed" for p in points), "failed_samples": failed,
                        "indeterminate_samples": len(points)-len(known), "max_absolute_error": maximum, "rmse": rmse}}


def compare(value):
    """Freeze and compare caller-supplied evidence, without file/network/model I/O."""
    plan = _plan(value)
    if plan["kind"] == "curve": result = _curve(plan)
    else:
        reference, actual = plan["reference"], plan["actual"]
        reason = _global_reason(reference, actual, ((reference["unit"], actual["unit"]),))
        if reference["value"] is None: reason = reason or "reference_value_missing"
        if actual["value"] is None: reason = reason or "actual_value_missing"
        result = _summary([_point(0, None, reference["value"], actual["value"], [0], plan["tolerance"], reason)], [])
    plan_hash = hashlib.sha256(_canonical(plan)).hexdigest()
    body = {"format": FORMAT, "plan_sha256": plan_hash, "result": result}
    # A successful result must itself fit the same read/verify budget; never
    # publish an artifact that verify cannot subsequently load.
    return _clone({**body, "plan": plan, "result_sha256": hashlib.sha256(_canonical(body)).hexdigest()})


def verify(value):
    """Recompute a stored comparison; hashes do not authenticate supplied sources."""
    document = _clone(value)
    _shape(document, ("format", "plan", "plan_sha256", "result", "result_sha256"))
    if _canonical(compare(document["plan"])) != _canonical(document):
        _error("comparison_mismatch", "Stored comparison differs from its frozen inputs or numeric result")
    return True
