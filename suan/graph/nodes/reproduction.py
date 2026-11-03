"""Explicit scalar/curve comparison of supplied Tables, without source authority.

NumPy is loaded only during node execution. Published declaration lives in
``docs/specs/catalog/m1_nodes.py``; changing numerical/adapter semantics requires
an impl_version increment as well as core contract review.
"""
import json
import math
from fractions import Fraction

from suan.graph.registry import NodeExecutionError, Port, enum, json_param, node, number, string

DOMAIN = {"anyOf": [{"type": "null"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}]}


def _failure(message="Invalid reproduction comparison table or parameters", code="invalid_param"):
    raise NodeExecutionError(message, code=code)


def _column(table, name, *, status=False):
    import numpy as np
    from suan.data.model import Field
    if name not in table.fields: _failure("A selected comparison column is absent")
    field = table.field(name); values = field.values
    if (field.association != "row" or field.components != 1 or not isinstance(values, np.ndarray)
            or values.ndim != 1 or len(values) != table.n_rows):
        _failure("Comparison columns require complete scalar row arrays")
    field.validate()
    if field.dtype != Field.dtype_name(values):
        _failure("Comparison field dtype differs from its actual array", "invalid_result")
    if status:
        if field.dtype != "string": _failure("A comparison row-status column must contain strings")
    elif field.dtype == "string" or values.dtype.kind not in "iuf":
        _failure("A comparison value or coordinate column must be numeric")
    return field


def _original(values):
    result = []
    for value in values.tolist():
        if type(value) is float and not math.isfinite(value):
            result.append("NaN" if math.isnan(value) else "Inf" if value > 0 else "-Inf")
        else: result.append(value)
    return result


def _numeric(value):
    if type(value) is float:
        if math.isnan(value): return None
        if not math.isfinite(value): _failure("Infinite comparison values are not valid observations", "invalid_result")
    return value


def _side(ctx, table, params, side):
    from suan.data.model import Provenance, Table
    from suan.reproduction.comparison import MAX_NODES, MAX_POINTS
    if not isinstance(table, Table): _failure("Comparison inputs must be Tables", "kind_mismatch")
    if table.n_rows > MAX_POINTS: _failure("Comparison input exceeds 4096 rows", "budget_exceeded")
    value_name = params[side + "_value"]; x_name = params[side + "_x"]; status_name = params[side + "_row_status"]
    names = [value_name] + ([x_name] if x_name is not None else []) + ([status_name] if status_name is not None else [])
    if len(set(names)) != len(names): _failure("Comparison value, coordinate and status columns must be distinct")
    fields = {name: _column(table, name, status=name == status_name) for name in names}
    raw = {name: fields[name].values.tolist() for name in names}
    provenance = table.provenance
    if provenance is not None and not isinstance(provenance, Provenance):
        _failure("Comparison input provenance is not representable", "invalid_result")
    if provenance is not None:
        if (type(provenance.used) is not list or type(provenance.derived_from) is not list
                or any(value is not None and type(value) is not dict for value in (provenance.activity, provenance.agent))
                or provenance.generated_at is not None and type(provenance.generated_at) is not str):
            _failure("Comparison input provenance is not representable", "invalid_result")
        if len(provenance.used) > MAX_NODES or len(provenance.derived_from) > MAX_NODES:
            _failure("Comparison provenance exceeds its structural budget", "budget_exceeded")
    source = {"kind": "upstream_table_metadata", "authority": "unverified", "table_id": table.id,
              "selection": {"value": value_name, "x": x_name, "row_status": status_name},
              "columns": {name: {"descriptor": fields[name].to_json(), "values": _original(fields[name].values)} for name in names},
              "provenance": None if provenance is None else provenance.to_json(), "attrs": table.attrs,
              "supplied_run_status": params[side + "_status"]}
    status = params[side + "_status"]
    if params["kind"] == "scalar":
        if x_name is not None or status_name is not None: _failure("Scalar comparison has no coordinate or row-status columns")
        if table.n_rows != 1 and not (table.n_rows == 0 and status in ("failed", "missing")):
            _failure("Scalar comparison requires one row, or an explicitly failed/missing empty source")
        return {"status": status, "unit": fields[value_name].unit,
                "value": None if not table.n_rows else _numeric(raw[value_name][0]), "source": source}
    if x_name is None: _failure("Curve comparison requires explicit coordinate columns")
    points = []
    for index in range(table.n_rows):
        if index % 128 == 0: ctx.check()
        row_status = "ok" if status_name is None else raw[status_name][index]
        if type(row_status) is not str or row_status not in ("ok", "failed", "missing"):
            _failure("Curve row status must be ok, failed or missing", "invalid_result")
        points.append({"x": _numeric(raw[x_name][index]), "y": _numeric(raw[value_name][index]), "status": row_status})
    return {"status": status, "x_unit": fields[x_name].unit, "y_unit": fields[value_name].unit,
            "points": points, "source": source}


def _errors(document):
    import numpy as np
    from suan.data.model import Table
    plan, result = document["plan"], document["result"]; points = result["points"]
    ref_unit = plan["reference"]["unit" if plan["kind"] == "scalar" else "y_unit"]
    actual_unit = plan["actual"]["unit" if plan["kind"] == "scalar" else "y_unit"]
    x_unit = "unspecified" if plan["kind"] == "scalar" else plan["reference"]["x_unit"]
    table = Table(id="reproduction_errors", index="reference_index",
                  attrs={"comparison_plan_sha256": document["plan_sha256"], "comparison_result_sha256": document["result_sha256"],
                         "comparison_status": result["status"], "source_authority": "unverified"})
    table.add_column("reference_index", np.array([p["reference_index"] for p in points], dtype=np.int64), unit="1", role="index")
    originals = {"x": [p["x"] for p in points], "reference": [p["reference"] for p in points], "actual": []}
    def upstream_lossy(side, role):
        source = plan[side]["source"]; selected = source["selection"][role]
        return False if selected is None else bool(source["columns"][selected]["descriptor"].get("lossy", False))
    ref_loss = upstream_lossy("reference", "value")
    actual_loss = upstream_lossy("actual", "value")
    x_loss = upstream_lossy("reference", "x")
    interpolation_loss = any(len(point["actual_indices"]) == 2 for point in points) and (x_loss or upstream_lossy("actual", "x"))
    inherited_loss = {"x": x_loss, "reference": ref_loss, "actual": actual_loss or interpolation_loss,
                      "signed_error": ref_loss or actual_loss or interpolation_loss,
                      "absolute_error": ref_loss or actual_loss or interpolation_loss, "allowed_error": ref_loss}
    actual_targets = []
    for point in points:
        indices = point["actual_indices"]
        if not indices:
            original = None; target = None
        elif plan["kind"] == "scalar":
            original = plan["actual"]["value"]; target = None if original is None else Fraction(str(original))
        elif len(indices) == 1:
            original = plan["actual"]["points"][indices[0]]["y"]
            target = None if original is None else Fraction(str(original))
        else:
            endpoints = [plan["actual"]["points"][i] for i in indices]
            original = {"alignment": "linear", "reference_x": point["x"], "points": endpoints}
            target = None
            if point["actual"] is not None:
                left, right = endpoints
                x0, x1, y0, y1, x = (Fraction(str(v)) for v in (left["x"], right["x"], left["y"], right["y"], point["x"]))
                target = y0 + (x-x0)*(y1-y0)/(x1-x0)
        originals["actual"].append(original); actual_targets.append(target)
    for name in ("x", "reference", "actual", "signed_error", "absolute_error", "allowed_error"):
        values = [p[name] for p in points]
        targets = actual_targets if name == "actual" else [None if value is None else Fraction(str(value)) for value in values]
        lossy = any(value is not None and target is not None and Fraction(str(float(value))) != target
                    for value, target in zip(values, targets))
        lossy = lossy or inherited_loss[name]
        unit = x_unit if name == "x" else actual_unit if name == "actual" else ref_unit
        table.add_column(name, np.array([np.nan if value is None else float(value) for value in values], dtype=np.float64),
                         unit=unit or "unspecified", lossy=lossy)
        if name in ("x", "reference", "actual"):
            table.add_column(name + "_exact", np.array([json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) for value in originals[name]], dtype=str))
    table.add_column("status", np.array([p["status"] for p in points], dtype=str))
    table.add_column("reason", np.array([p["reason"] or "" for p in points], dtype=str))
    table.add_column("actual_indices", np.array([json.dumps(p["actual_indices"], separators=(",", ":")) for p in points], dtype=str))
    return table


@node("stk.analysis.reproduction_compare", impl_version=1,
      title={"en": "Reproduction comparison", "zh": "复现数值对比"},
      description={"en": "Compare explicitly selected Table columns with declared units, statuses, tolerances and domain; source metadata is not authenticated."},
      inputs=[Port("reference", "table"), Port("actual", "table")],
      outputs=[Port("comparison", "value", value_type="json"), Port("errors", "table")],
      params={
          "kind": enum(["scalar", "curve"]),
          "reference_value": string(min_length=1, max_length=128), "actual_value": string(min_length=1, max_length=128),
          "reference_status": enum(["succeeded", "failed", "missing"]), "actual_status": enum(["succeeded", "failed", "missing"]),
          "absolute": number(minimum=0), "relative": number(minimum=0), "alignment": enum(["exact", "linear"]),
          "domain": json_param(DOMAIN, None),
          "reference_x": string(None, nullable=True, min_length=1, max_length=128),
          "actual_x": string(None, nullable=True, min_length=1, max_length=128),
          "reference_row_status": string(None, nullable=True, min_length=1, max_length=128),
          "actual_row_status": string(None, nullable=True, min_length=1, max_length=128),
      }, cache="disk")
def reproduction_compare(ctx, inputs, params):
    from suan.reproduction import ComparisonError, compare
    from suan.reproduction.comparison import PLAN_FORMAT
    ctx.check()
    if params["kind"] == "scalar":
        if params["alignment"] != "exact" or params["domain"] is not None:
            _failure("Scalar comparison requires exact alignment and no curve domain")
        rule = {"criterion": "absolute_plus_relative"}
    else:
        if params["domain"] is None: _failure("Curve comparison requires an explicit domain")
        rule = {"criterion": "all_reference_points_and_full_domain", "alignment": params["alignment"],
                "domain": params["domain"], "extrapolation": "forbid"}
    try:
        plan = {"format": PLAN_FORMAT, "kind": params["kind"],
                "reference": _side(ctx, inputs["reference"], params, "reference"),
                "actual": _side(ctx, inputs["actual"], params, "actual"),
                "tolerance": {"absolute": params["absolute"], "relative": params["relative"]}, "rule": rule}
        document = compare(plan)
    except ComparisonError as error:
        raise NodeExecutionError(str(error), code="invalid_result") from None
    except (TypeError, ValueError, OverflowError, RecursionError, AttributeError):
        _failure("Comparison input metadata or numeric values are not representable", "invalid_result")
    ctx.check()
    return {"comparison": document, "errors": _errors(document)}
