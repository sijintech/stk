"""Analysis nodes ``stk.analysis.*@1`` (docs/specs/domain-classifiers.md §3-§5, stk-graph-v1.md §14).

* ``orientation_classify`` -> :func:`suan.analysis.orientation.classify_image`
  (the label field carries its categories with colours, so render nodes and
  legends need no palette code);
* ``film_detect`` -> :func:`suan.analysis.labels.film_detect_image`;
* ``label_fractions`` -> :func:`suan.analysis.labels.fractions_tables`;
* ``statistics``: per field and component count, nan_count, min, max, mean,
  std (population) and unit (NumPy).

Label values: -1 unclassified / no data / air, 0 substrate, 1..N variants.
Nodes never write into their inputs (the evaluator shares read-only arrays).
Declarations are copied from ``docs/specs/catalog/m1_nodes.py`` (frozen);
NumPy is imported inside the functions.
"""
from suan.graph.registry import (FIELD_NAME, NodeExecutionError, Port, array, boolean, enum, field_ref, integer, node,
                                 number, string, string_list)

FIELD_PATTERN = FIELD_NAME["pattern"]


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


def _orientation_error(exc):
    return NodeExecutionError(str(exc), code=getattr(exc, "code", None) or "invalid_param")


@node("stk.analysis.orientation_classify", title={"en": "Orientation classify", "zh": "畴取向分类"},
      description={"en": "Label each point with the nearest reference direction (docs/specs/domain-classifiers.md): "
                         "-1 unclassified/no data, 0 substrate (film detection), 1..N variants."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind="labels")],
      params={
          "field": field_ref(None, nullable=True, component=False, title="Vector field"),
          "component_offset": integer(0, minimum=0, maximum=4093),
          "direction_set": enum(["stk:cubic-26", "stk:cubic-100", "stk:cubic-110", "stk:cubic-111", "custom"],
                                "stk:cubic-26"),
          "directions": array({"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}, None,
                              nullable=True, min_items=1, max_items=64, title="custom: directions"),
          "numbering": enum(["stk", "stk-legacy"], "stk"),
          "min_magnitude": number(0.1, minimum=0),
          "max_angle_deg": number(180.0, exclusive_minimum=0, maximum=180),
          "film_detection": boolean(False),
          "film_epsilon": number(1e-6, minimum=0),
          "output": string("domain", pattern=FIELD_PATTERN),
      },
      cache="disk")
def orientation_classify(ctx, inputs, params):
    from suan.analysis.orientation import OrientationError, classify_image
    if params["directions"] is not None and params["direction_set"] != "custom":
        ctx.warn(f"'directions' is only used with direction_set 'custom' (not {params['direction_set']})",
                 code="ignored_param")
    try:
        result = classify_image(inputs["in"], field=params["field"], component_offset=params["component_offset"],
                                direction_set=params["direction_set"], directions=params["directions"],
                                numbering=params["numbering"], min_magnitude=params["min_magnitude"],
                                max_angle_deg=params["max_angle_deg"], film_detection=params["film_detection"],
                                film_epsilon=params["film_epsilon"], output=params["output"],
                                check=getattr(ctx, "check", None))
    except OrientationError as exc:
        raise _orientation_error(exc) from None
    film = result.attrs.get("film")
    if film is not None and not film["detected"]:
        ctx.warn("Film detection found no polarized layer; every point is unclassified", code="no_film")
    return result


@node("stk.analysis.film_detect", title={"en": "Film detection", "zh": "薄膜检测"},
      description={"en": "Find substrate, film and air layers along z from where the vector field is nonzero. "
                         "Adds int8 label field (-1 air, 0 substrate, 1 film); 'info' reports the layer indices."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind="labels"), Port("info", "value", value_type="json")],
      params={
          "field": field_ref(None, nullable=True, component=False),
          "component_offset": integer(0, minimum=0, maximum=4093),
          "epsilon": number(1e-6, minimum=0),
          "output": string("film", pattern=FIELD_PATTERN),
      })
def film_detect(ctx, inputs, params):
    from suan.analysis.labels import film_detect_image
    from suan.analysis.orientation import OrientationError
    try:
        result, info = film_detect_image(inputs["in"], field=params["field"],
                                         component_offset=params["component_offset"], epsilon=params["epsilon"],
                                         output=params["output"])
    except OrientationError as exc:
        raise _orientation_error(exc) from None
    except ValueError as exc:
        raise NodeExecutionError(str(exc), code="invalid_param") from None
    if not info["detected"]:
        ctx.warn("No polarized layer: no film detected", code="no_film")
    return {"out": result, "info": dict(info)}


@node("stk.analysis.label_fractions", title={"en": "Label fractions", "zh": "畴体积分数"},
      description={"en": "Point (or cell) counts and fractions per category; the denominator excludes 'exclude'. "
                         "'families' aggregates by category family (e.g. R/O/T)."},
      inputs=[Port("in", "dataset", accepts=["labels"])],
      outputs=[Port("out", "table"), Port("families", "table")],
      params={
          "field": _nullable_string(pattern=FIELD_PATTERN),
          "exclude": array({"type": "integer"}, [-1, 0], max_items=256),
          "include_empty": boolean(True),
      })
def label_fractions(ctx, inputs, params):
    from suan.analysis.labels import fractions_tables
    dataset = inputs["in"]
    if params["field"] is not None and params["field"] not in dataset.fields:
        raise NodeExecutionError(f"No field {params['field']!r}; label fields: "
                                 f"{', '.join(f.name for f in dataset.label_fields()) or 'none'}",
                                 code="invalid_param")
    try:
        out, families, warnings = fractions_tables(dataset, field=params["field"], exclude=params["exclude"],
                                                   include_empty=params["include_empty"])
    except ValueError as exc:
        raise NodeExecutionError(str(exc), code="kind_mismatch") from None
    for warning in warnings:
        ctx.warn(warning["message"], code=warning["code"])
    return {"out": out, "families": families}


def _summary(values):
    """``(count, nan_count, min, max, mean, std)`` of the finite values of a 1-D array."""
    import numpy as np
    values = np.asarray(values).reshape(-1)
    if values.dtype.kind in "iub":
        good = values
    else:
        good = values[np.isfinite(values)]
    count, nan_count = int(good.size), int(values.size - good.size)
    if not count:
        return count, nan_count, np.nan, np.nan, np.nan, np.nan
    good = good.astype(np.float64, copy=False)
    return count, nan_count, float(good.min()), float(good.max()), float(good.mean()), float(good.std())


def statistics_table(dataset, fields=None, components="both"):
    """``stk.analysis.statistics@1``: one row per field and component (and magnitude of multi-component fields)."""
    import numpy as np
    from suan.data.model import Table
    if fields is None:
        chosen = [f for f in dataset.fields.values() if f.values is not None and f.dtype != "string"]
    else:
        missing = [name for name in fields if name not in dataset.fields]
        if missing:
            raise NodeExecutionError(f"No field(s) {', '.join(missing)}; fields: {', '.join(dataset.fields) or 'none'}",
                                     code="invalid_param")
        chosen = [dataset.fields[name] for name in dict.fromkeys(fields)
                  if dataset.fields[name].values is not None and dataset.fields[name].dtype != "string"]
    rows = []
    for field in chosen:
        values = np.asarray(field.values).reshape(-1, field.components)
        multi = field.components > 1
        if components in ("each", "both") or not multi:
            for c in range(field.components):
                label = field.component_names[c] if field.component_names else str(c)
                rows.append((field.name, label, *_summary(values[:, c]), field.unit))
        if multi and components in ("magnitude", "both"):
            v = values.astype(np.float64)
            rows.append((field.name, "magnitude", *_summary(np.sqrt(np.einsum("ij,ij->i", v, v))), field.unit))
    table = Table(id="statistics", attrs={"components": components})
    table.add_column("field", np.array([r[0] for r in rows], dtype=str))
    table.add_column("component", np.array([r[1] for r in rows], dtype=str))
    table.add_column("count", np.array([r[2] for r in rows], dtype=np.int64), unit="1")
    table.add_column("nan_count", np.array([r[3] for r in rows], dtype=np.int64), unit="1")
    for index, name in enumerate(("min", "max", "mean", "std"), start=4):
        table.add_column(name, np.array([r[index] for r in rows], dtype=np.float64))
    table.add_column("unit", np.array([r[8] for r in rows], dtype=str))
    return table


@node("stk.analysis.statistics", title={"en": "Statistics", "zh": "统计"},
      description={"en": "Per field and component: count, nan_count, min, max, mean, std (and magnitude)."},
      inputs=[Port("in", "dataset", accepts=["image", "polydata", "table"])],
      outputs=[Port("out", "table")],
      params={
          "fields": string_list(None, nullable=True, max_items=64),
          "components": enum(["each", "magnitude", "both"], "both"),
      })
def statistics(ctx, inputs, params):
    table = statistics_table(inputs["in"], params["fields"], params["components"])
    if not table.n_rows:
        ctx.warn("No numeric fields to summarize", code="empty_result")
    return table
