"""Filter nodes ``stk.filter.*@1`` (docs/specs/stk-graph-v1.md §13-§14, domain-classifiers.md §7).

The algorithms live in :mod:`suan.data.filters` (NumPy + VTK); these nodes
validate their inputs, translate filter errors into node errors with stable
codes and forward warnings (``empty_result``, ``stride_increased``, ...). Every
node returns a new dataset: the evaluator's input arrays are read-only and
shared with its cache, and are never written.

Declarations are copied from ``docs/specs/catalog/m1_nodes.py`` (the frozen
catalog). Heavy imports stay inside the functions: the hub imports catalogs
without NumPy or VTK.
"""
from suan.graph.registry import (FIELD_NAME, NodeExecutionError, Port, array, boolean, enum, field_ref, int3, integer,
                                 interval, json_param, node, number, string, string_list, vector3)

FIELD_PATTERN = FIELD_NAME["pattern"]


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


def _warner(ctx):
    def warn(message, *, code="node_warning", **details):
        ctx.warn(message, code=code, **details)
    return warn


def _check(ctx):
    return getattr(ctx, "check", None)


def _run(function, *args, **kwargs):
    """Call a filter; its ``FilterError`` becomes a ``NodeExecutionError`` with the same code."""
    from suan.data.filters import FilterError
    try:
        return function(*args, **kwargs)
    except FilterError as exc:
        raise NodeExecutionError(str(exc), code=exc.code, hint=exc.hint) from None


@node("stk.filter.crop", title={"en": "Crop (VOI)", "zh": "裁剪"},
      description={"en": "Extract a volume of interest by inclusive point-index ranges. Origin moves to the first "
                         "kept point; spacing, fields and categories are kept."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind_from="in")],
      params={
          "extent": array({"type": ["integer", "null"], "minimum": 0}, [None] * 6, min_items=6, max_items=6,
                          title="[i0, i1, j0, j1, k0, k1]",
                          description="Inclusive point indices; null = axis start/end. Clipped to the grid."),
      },
      cache="memory")
def crop(ctx, inputs, params):
    from suan.data import filters
    return _run(filters.crop, inputs["in"], params["extent"])


@node("stk.filter.sample", title={"en": "Sample (stride)", "zh": "抽样"},
      description={"en": "Keep every n-th point along each axis (spacing multiplied by the stride). With "
                         "max_points the stride grows uniformly until the point count fits."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind_from="in")],
      params={
          "stride": int3([1, 1, 1], minimum=1),
          "max_points": integer(None, nullable=True, minimum=1),
      })
def sample(ctx, inputs, params):
    from suan.data import filters
    result, steps = _run(filters.sample, inputs["in"], params["stride"], params["max_points"])
    if list(steps) != list(params["stride"]):
        ctx.warn(f"The stride grew to {list(steps)} to keep at most {params['max_points']} points",
                 code="stride_increased", stride=list(steps))
    return result


@node("stk.filter.calculator", title={"en": "Calculator", "zh": "计算器"},
      description={"en": "Fixed operations that add one field: magnitude, component, scale, normalize, compose. "
                         "No expression language in M1."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind_from="in")],
      params={
          "operation": enum(["magnitude", "component", "scale", "normalize", "compose"]),
          "field": field_ref(None, nullable=True, component=False, title="Input field"),
          "fields": string_list(None, nullable=True, min_items=2, max_items=16, title="compose: input fields"),
          "component": integer(0, minimum=0),
          "factor": number(1.0),
          "compose_as": enum(["array", "vector"], "array"),
          "result": _nullable_string(pattern=FIELD_PATTERN, title="Result field name"),
          "unit": _nullable_string(min_length=1, title="Result unit"),
          "keep_input": boolean(True),
      })
def calculator(ctx, inputs, params):
    from suan.data import filters
    return _run(filters.calculator, inputs["in"], params["operation"], field=params["field"],
                fields=params["fields"], component=params["component"], factor=params["factor"],
                compose_as=params["compose_as"], result=params["result"], unit=params["unit"],
                keep_input=params["keep_input"])


@node("stk.filter.slice", title={"en": "Slice", "zh": "切片"},
      description={"en": "axis mode: the grid plane at an index (exact samples, a 2D image with that axis of "
                         "size 1; label fields kept). plane mode: an arbitrary plane cut (triangulated polydata, "
                         "trilinear point data, nearest for label fields)."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind=["image", "labels", "polydata"])],
      params={
          "mode": enum(["axis", "plane"], "axis"),
          "axis": enum(["x", "y", "z"], "z"),
          "index": integer(None, nullable=True, minimum=0, title="Index (null = middle)"),
          "origin": vector3(None, nullable=True, title="Plane origin (null = centre)"),
          "normal": vector3([0.0, 0.0, 1.0], title="Plane normal"),
          "fields": string_list(None, nullable=True, max_items=64),
      })
def slice_filter(ctx, inputs, params):
    from suan.data import filters
    if params["mode"] == "axis":
        return _run(filters.slice_axis, inputs["in"], params["axis"], params["index"], params["fields"])
    return _run(filters.slice_plane, inputs["in"], params["origin"], params["normal"], params["fields"],
                warn=_warner(ctx))


@node("stk.filter.threshold", title={"en": "Threshold", "zh": "阈值"},
      description={"en": "Add a uint8 label field (1 inside, 0 outside) selecting lower <= value <= upper "
                         "(null = unbounded; component null on a vector = magnitude), or a set of labels."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind="labels")],
      params={
          "field": field_ref(title="Field"),
          "lower": number(None, nullable=True),
          "upper": number(None, nullable=True),
          "labels": array({"type": "integer"}, None, nullable=True, min_items=1, max_items=256),
          "invert": boolean(False),
          "output": string("mask", pattern=FIELD_PATTERN),
      })
def threshold(ctx, inputs, params):
    from suan.data import filters
    return _run(filters.threshold, inputs["in"], params["field"], lower=params["lower"], upper=params["upper"],
                labels=params["labels"], invert=params["invert"], output=params["output"])


@node("stk.filter.contour", title={"en": "Contour", "zh": "等值面"},
      description={"en": "Isosurfaces at one or more values (marching cubes / flying edges). Output point field "
                         "'iso_value' plus interpolated probe_fields."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind="polydata")],
      params={
          "field": field_ref(title="Field"),
          "values": array({"type": "number"}, None, nullable=True, min_items=1, max_items=32,
                          title="Isovalues (null = range midpoint)"),
          "compute_normals": boolean(True),
          "probe_fields": string_list(None, nullable=True, max_items=16),
      },
      cache="disk")
def contour(ctx, inputs, params):
    from suan.data import filters
    return _run(filters.contour, inputs["in"], params["field"], params["values"],
                compute_normals=params["compute_normals"], probe_fields=params["probe_fields"], warn=_warner(ctx))


@node("stk.filter.glyph_source", title={"en": "Glyph source", "zh": "箭头采样"},
      description={"en": "Sample points of a vector field for glyphs: stride or seeded random sampling, "
                         "magnitude range and label mask, capped at max_points. Point fields: the vector field, "
                         "'magnitude' and the listed attributes."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind="points")],
      params={
          "field": field_ref(None, nullable=True, component=False, title="Vector field"),
          "sampling": enum(["stride", "random"], "stride"),
          "stride": int3([1, 1, 1], minimum=1),
          "max_points": integer(5000, minimum=1, maximum=5000000),
          "seed": integer(0, minimum=0),
          "magnitude_range": interval([None, None]),
          "mask_field": _nullable_string(pattern=FIELD_PATTERN),
          "mask_labels": array({"type": "integer"}, None, nullable=True, min_items=1, max_items=256),
          "attributes": string_list(None, nullable=True, max_items=16),
      })
def glyph_source(ctx, inputs, params):
    from suan.data import filters
    poly, steps = _run(filters.glyph_source, inputs["in"], params["field"], sampling=params["sampling"],
                       stride=params["stride"], max_points=params["max_points"], seed=params["seed"],
                       magnitude_range=params["magnitude_range"], mask_field=params["mask_field"],
                       mask_labels=params["mask_labels"], attributes=params["attributes"])
    if list(steps) != list(params["stride"]):
        ctx.warn(f"The glyph stride grew to {list(steps)} to keep at most {params['max_points']} points",
                 code="stride_increased", stride=list(steps))
    if poly.n_points == 0:
        ctx.warn("No glyph points (check magnitude_range and the mask)", code="empty_result")
    return poly


@node("stk.filter.label_surfaces", title={"en": "Label surfaces", "zh": "畴界面"},
      description={"en": "One closed, smoothed surface per label: indicator (label == v) -> contour at 0.5 -> "
                         "smoothing -> normals. Cell field 'label' (int32) carries the categories."},
      inputs=[Port("in", "dataset", accepts=["labels"])],
      outputs=[Port("out", "dataset", kind="polydata")],
      params={
          "field": _nullable_string(pattern=FIELD_PATTERN, title="Label field (null = first)"),
          "labels": json_param({"anyOf": [{"const": "present"},
                                          {"type": "array", "items": {"type": "integer"}, "minItems": 1,
                                           "maxItems": 256}]}, "present"),
          "exclude": array({"type": "integer"}, [-1, 0], max_items=256),
          "smoothing": enum(["windowed_sinc", "laplacian", "none"], "windowed_sinc"),
          "smooth_iterations": integer(30, minimum=0, maximum=500),
          "smooth_factor": number(0.1, exclusive_minimum=0, maximum=2),
          "compute_normals": boolean(True),
          "close_boundaries": boolean(True),
      },
      cache="disk")
def label_surfaces(ctx, inputs, params):
    from suan.data import filters
    return _run(filters.label_surfaces, inputs["in"], params["field"], params["labels"], params["exclude"],
                smoothing=params["smoothing"], smooth_iterations=params["smooth_iterations"],
                smooth_factor=params["smooth_factor"], compute_normals=params["compute_normals"],
                close_boundaries=params["close_boundaries"], check=_check(ctx), warn=_warner(ctx))


@node("stk.filter.streamlines", title={"en": "Streamlines", "zh": "流线"},
      description={"en": "Stretch goal. Integrate streamlines of a vector field from seed points on a sphere."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind="polydata")],
      params={
          "field": field_ref(None, nullable=True, component=False),
          "seed_center": vector3(None, nullable=True),
          "seed_radius": number(None, nullable=True, exclusive_minimum=0),
          "seed_count": integer(100, minimum=1, maximum=100000),
          "direction": enum(["forward", "backward", "both"], "forward"),
          "max_length": number(None, nullable=True, exclusive_minimum=0),
          "seed": integer(0, minimum=0),
      },
      stretch=True)
def streamlines(ctx, inputs, params):
    from suan.data import filters
    return _run(filters.streamlines, inputs["in"], params["field"], seed_center=params["seed_center"],
                seed_radius=params["seed_radius"], seed_count=params["seed_count"], direction=params["direction"],
                max_length=params["max_length"], seed=params["seed"], warn=_warner(ctx))
