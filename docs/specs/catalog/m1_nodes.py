"""Frozen Milestone-1 node catalog (declarations only), written with suan.graph.registry.

This file is the machine-readable form of the node tables in
``docs/specs/stk-graph-v1.md``. Implementers copy each declaration into the
module that owns it (sources -> suan/graph/nodes/sources.py, filters/analysis ->
suan/graph/nodes/{filters,analysis}.py, render/view/output/plot ->
suan/graph/nodes/{render,view,output,plot}.py) and replace the stub bodies.
The exported catalog of the real registry must equal ``stk-catalog-m1.json``
(ignoring ``impl``; nodes marked ``stretch`` may be absent).

    python docs/specs/catalog/m1_nodes.py --write         # regenerate stk-catalog-m1.json
    python docs/specs/catalog/m1_nodes.py --update-spec   # regenerate the tables in stk-graph-v1.md
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
try:  # an installed suan wins; a bare checkout works too
    import suan.graph.registry  # noqa: F401
except ImportError:
    sys.path.insert(0, str(ROOT))

from suan.graph.registry import (  # noqa: E402
    FIELD_NAME, Port, Registry, array, binding, boolean, color, enum, field_ref, int3, integer, interval,
    json_param, number, rel_path, step, string, string_list, vector3,
)

REGISTRY = Registry(namespaces={"stk": 1})
node = REGISTRY.node

FIELD_PATTERN = FIELD_NAME["pattern"]
ANCHORS = ["top_left", "top", "top_right", "left", "center", "right", "bottom_left", "bottom", "bottom_right"]
RGB = {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1}, "minItems": 3, "maxItems": 4}
INTERVAL = {"type": "array", "prefixItems": [{"type": ["number", "null"]}, {"type": ["number", "null"]}],
            "minItems": 2, "maxItems": 2}
COMPONENT = {"anyOf": [{"type": "integer", "minimum": 0}, {"const": "magnitude"}, {"type": "null"}]}
COLOR_SPEC = {
    "type": "object",
    "required": ["by"],
    "properties": {
        "by": {"enum": ["solid", "field", "orientation"]},
        "solid": RGB,
        "field": {"type": ["string", "null"]},
        "component": COMPONENT,
        "colormap": {"type": ["string", "null"]},
        "palette": {"type": ["string", "null"]},
        "range": INTERVAL,
        "range_mode": {"enum": ["data", "symmetric", "fixed", "global"]},
        "lightness_range": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1},
                            "minItems": 2, "maxItems": 2},
    },
    "additionalProperties": False,
}
ATTRIBUTES = {"anyOf": [{"const": "all"}, {"type": "array", "items": FIELD_NAME, "maxItems": 64}]}
SIZE_IN = {"type": "array", "items": {"type": "number", "exclusiveMinimum": 0, "maximum": 100},
           "minItems": 2, "maxItems": 2}
STYLE = {
    "type": "object",
    "properties": {
        "color": {"type": "string"}, "linestyle": {"enum": ["-", "--", "-.", ":", "none"]},
        "linewidth": {"type": "number", "minimum": 0}, "marker": {"type": ["string", "null"]},
        "markersize": {"type": "number", "minimum": 0}, "alpha": {"type": "number", "minimum": 0, "maximum": 1},
        "label": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}
ROW_FILTER = {"type": "object", "required": ["column", "op", "value"],
              "properties": {"column": {"type": "string"}, "op": {"enum": ["==", "!=", ">", ">=", "<", "<="]},
                             "value": {"type": ["number", "string"]}},
              "additionalProperties": False}


def _todo(*_):
    raise NotImplementedError("Declaration only; the implementation lives in suan/graph/nodes/*")


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


def _plot_common():
    return {
        "title": _nullable_string(stage="client", title="Title"),
        "size_in": json_param(SIZE_IN, [6.0, 4.0], stage="client", title="Figure size (inches)"),
        "dpi": integer(200, minimum=30, maximum=1200, stage="client"),
    }


# ---------------------------------------------------------------------------
# Sources


@node("stk.source.muferro_run", title={"en": "muFerro run", "zh": "muFerro 计算"},
      description={"en": "Index of a muFerro run directory: published field frames, the energy trace, "
                         "the progress log and the derived stk.result/1 manifest."},
      outputs=[Port("frames", "table", kind="frames"), Port("energy", "table"), Port("progress", "table"),
               Port("result", "value", value_type="json")],
      params={
          "binding": binding(title="Run binding",
                             description="Binding name resolved by the caller to {task_id} or a local directory."),
          "case_dir": rel_path("auto", title="Case directory",
                               description="Directory inside the binding holding input.toml and the outputs; "
                                           "\"auto\" = the case_dir recorded by the STK launcher in stk-mupro.json "
                                           "(runs submitted with --input DIR), else the binding root."),
      },
      time_dependent=True, fingerprint=_todo)
def muferro_run(ctx, inputs, params):
    _todo()


@node("stk.source.muferro_frame", title={"en": "muFerro frame", "zh": "muFerro 帧"},
      description={"en": "Read one published field frame '<dataset>.<step:08d>.dat' of a muFerro run as an "
                         "image dataset (VTK order (z,y,x,c)). Reports the available steps as choices."},
      inputs=[Port("frames", "table", accepts=["frames"])],
      outputs=[Port("out", "dataset", kind="image")],
      params={
          "dataset": string("Polar", pattern=r"^[A-Za-z][A-Za-z0-9_]{0,7}$", title="Field stem"),
          "step": step("latest", title="Step"),
          "policy": enum(["latest_at_or_before", "exact"], "latest_at_or_before", title="Step policy"),
          "spacing": vector3(None, nullable=True, title="Spacing override"),
          "origin": vector3(None, nullable=True, title="Origin override"),
          "length_unit": string("grid_index", min_length=1, title="Length unit"),
          "unit": string("unspecified", min_length=1, title="Field unit"),
          "quantity": _nullable_string(pattern=r"^([a-z0-9_]+:)?[a-z0-9_]+$", title="Quantity override"),
          "precision": enum(["float64", "float32"], "float64"),
      },
      time_dependent=True, cache="disk", fingerprint=_todo, selectors=("step", "policy"))
def muferro_frame(ctx, inputs, params):
    _todo()


@node("stk.source.file", title={"en": "Field file", "zh": "场文件"},
      description={"en": "Read a field file inside a binding: MuPRO DAT, NPY, VTI, legacy VTK STRUCTURED_POINTS "
                         "or VTKHDF (image or polydata)."},
      outputs=[Port("out", "dataset", kind=["image", "polydata"])],
      params={
          "binding": binding(),
          "path": rel_path(title="Relative path"),
          "format": enum(["auto", "dat", "npy", "vti", "vtk", "vtkhdf"], "auto"),
          "fields": string_list(None, nullable=True, max_items=64, title="Arrays to load (default all)"),
          "association": enum(["auto", "point", "cell"], "auto"),
          "spacing": vector3(None, nullable=True),
          "origin": vector3(None, nullable=True),
          "length_unit": _nullable_string(min_length=1),
          "unit": _nullable_string(min_length=1),
          "quantity": _nullable_string(pattern=r"^([a-z0-9_]+:)?[a-z0-9_]+$"),
          "step": integer(None, nullable=True, minimum=0, title="Time step metadata"),
      },
      cache="disk", fingerprint=_todo)
def file_source(ctx, inputs, params):
    _todo()


@node("stk.source.table", title={"en": "Table file", "zh": "表格文件"},
      description={"en": "Read a table file inside a binding: muFerro energy_out.dat, whitespace columns "
                         "(optional header), CSV or a progress JSONL log."},
      outputs=[Port("out", "table")],
      params={
          "binding": binding(),
          "path": rel_path(),
          "format": enum(["auto", "muferro_energy", "columns", "csv", "progress_jsonl"], "auto"),
          "columns": string_list(None, nullable=True, max_items=256, title="Columns to keep (default all)"),
          "units": json_param({"type": "object", "additionalProperties": {"type": "string", "minLength": 1}}, {},
                              title="Column units"),
      },
      fingerprint=_todo)
def table_source(ctx, inputs, params):
    _todo()


# ---------------------------------------------------------------------------
# Filters


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
    _todo()


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
    _todo()


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
    _todo()


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
    _todo()


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
    _todo()


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
    _todo()


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
    _todo()


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
    _todo()


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
    _todo()


# ---------------------------------------------------------------------------
# Analysis


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
    _todo()


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
    _todo()


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
    _todo()


@node("stk.analysis.statistics", title={"en": "Statistics", "zh": "统计"},
      description={"en": "Per field and component: count, nan_count, min, max, mean, std (and magnitude)."},
      inputs=[Port("in", "dataset", accepts=["image", "polydata", "table"])],
      outputs=[Port("out", "table")],
      params={
          "fields": string_list(None, nullable=True, max_items=64),
          "components": enum(["each", "magnitude", "both"], "both"),
      })
def statistics(ctx, inputs, params):
    _todo()


# ---------------------------------------------------------------------------
# Render (representation)


@node("stk.render.surface", title={"en": "Surface", "zh": "表面"},
      description={"en": "Polydata -> triangles (or lines/points) layer; a planar image (one axis of size 1) -> "
                         "slice_image layer. Attributes travel raw; colouring is client-side."},
      inputs=[Port("in", "dataset", accepts=["polydata", "image"])],
      outputs=[Port("layer", "layer")],
      params={
          "attributes": json_param(ATTRIBUTES, "all", title="Attributes to send"),
          "color": json_param(COLOR_SPEC, {"by": "solid", "solid": [0.8, 0.8, 0.8]}, stage="client"),
          "opacity": number(1.0, minimum=0, maximum=1, stage="client"),
          "shading": enum(["smooth", "flat"], "smooth", stage="client"),
          "edges": boolean(False, stage="client"),
          "lighting": boolean(True, stage="client"),
          "name": _nullable_string(stage="client"),
      })
def surface(ctx, inputs, params):
    _todo()


@node("stk.render.glyphs", title={"en": "Glyphs", "zh": "箭头"},
      description={"en": "Instanced glyphs (arrow/cone/sphere/line/cube) at the input points, oriented by a "
                         "vector field; scale and colour are client-side."},
      inputs=[Port("in", "dataset", accepts=["polydata"])],
      outputs=[Port("layer", "layer")],
      params={
          "vectors": field_ref(None, nullable=True, component=False, title="Direction field"),
          "attributes": json_param(ATTRIBUTES, "all"),
          "shape": enum(["arrow", "cone", "sphere", "line", "cube"], "arrow", stage="client"),
          "resolution": integer(8, minimum=3, maximum=64, stage="client"),
          "center": boolean(True, stage="client"),
          "scale": json_param({"type": "object", "required": ["by", "factor"],
                               "properties": {"by": {"enum": ["uniform", "magnitude", "field"]},
                                              "field": {"type": ["string", "null"]},
                                              "factor": {"anyOf": [{"type": "number", "exclusiveMinimum": 0},
                                                                   {"const": "auto"}]}},
                               "additionalProperties": False},
                              {"by": "magnitude", "factor": "auto"}, stage="client"),
          "color": json_param(COLOR_SPEC, {"by": "orientation"}, stage="client"),
          "opacity": number(1.0, minimum=0, maximum=1, stage="client"),
          "name": _nullable_string(stage="client"),
      })
def glyphs(ctx, inputs, params):
    _todo()


@node("stk.render.volume", title={"en": "Volume", "zh": "体渲染"},
      description={"en": "Dense volume texture with colour and opacity transfer functions (client-side)."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("layer", "layer")],
      params={
          "field": field_ref(None, nullable=True),
          "encoding": enum(["auto", "u8", "u16", "f32"], "auto"),
          "colormap": string("viridis", min_length=1, stage="client", widget="colormap"),
          "range": interval([None, None], stage="client"),
          "opacity": json_param({"type": "array", "minItems": 2, "maxItems": 64,
                                 "items": {"type": "array", "prefixItems": [
                                     {"type": "number", "minimum": 0, "maximum": 1},
                                     {"type": "number", "minimum": 0, "maximum": 1}], "minItems": 2, "maxItems": 2}},
                                None, nullable=True, stage="client", widget="transfer_function",
                                title="Opacity points [x, alpha], x normalized over range",
                                description="null = automatic: a ramp [[0, 0], [1, 0.8]] for scalars; 0.8 for "
                                            "every label of a categorical field (0 for -1)"),
          "sampling": enum(["linear", "nearest"], "linear", stage="client"),
          "shade": boolean(False, stage="client"),
          "name": _nullable_string(stage="client"),
      })
def volume(ctx, inputs, params):
    _todo()


@node("stk.render.outline", title={"en": "Outline", "zh": "外框"},
      description={"en": "Bounding-box edges of the input as a lines layer."},
      inputs=[Port("in", "dataset", accepts=["image", "polydata"])],
      outputs=[Port("layer", "layer")],
      params={
          "color": color([0.0, 0.0, 0.0], stage="client"),
          "width_px": number(1.0, minimum=0, maximum=32, stage="client"),
          "name": _nullable_string(stage="client"),
      })
def outline(ctx, inputs, params):
    _todo()


@node("stk.render.axes", title={"en": "Axes triad", "zh": "坐标轴"},
      description={"en": "Orientation triad overlay (axes_triad)."},
      outputs=[Port("layer", "layer")],
      params={
          "labels": string_list(["x", "y", "z"], min_items=3, max_items=3, stage="client"),
          "anchor": enum(ANCHORS, "bottom_left", stage="client"),
          "size_px": integer(80, minimum=16, maximum=512, stage="client"),
      })
def axes(ctx, inputs, params):
    _todo()


@node("stk.render.scalar_bar", title={"en": "Scalar bar", "zh": "色标"},
      description={"en": "Scalar bar overlay explaining the continuous colouring of the linked layer."},
      inputs=[Port("source", "layer")],
      outputs=[Port("layer", "layer")],
      params={
          "title": _nullable_string(stage="client", title="Title (null = field and unit)"),
          "anchor": enum(ANCHORS, "right", stage="client"),
          "orientation": enum(["vertical", "horizontal"], "vertical", stage="client"),
          "label_count": integer(5, minimum=2, maximum=20, stage="client"),
          "format": string(".3g", min_length=1, max_length=16, stage="client",
                           pattern=r"^[+\- ]?#?0?(?:[1-9][0-9]?)?,?(?:(?:\.[0-9]{1,2})?[eEfFgG%]?|d)$"),
      })
def scalar_bar(ctx, inputs, params):
    _todo()


@node("stk.render.categorical_legend", title={"en": "Categorical legend", "zh": "分类图例"},
      description={"en": "Legend of category names and colours, from a categorical layer or a labels dataset."},
      inputs=[Port("source", ["layer", "dataset"], accepts=["labels"])],
      outputs=[Port("layer", "layer")],
      params={
          "field": _nullable_string(pattern=FIELD_PATTERN),
          "only_present": boolean(True),
          "title": _nullable_string(stage="client"),
          "anchor": enum(ANCHORS, "right", stage="client"),
          "columns": integer(1, minimum=1, maximum=8, stage="client"),
      })
def categorical_legend(ctx, inputs, params):
    _todo()


@node("stk.render.orientation_legend", title={"en": "Orientation legend", "zh": "取向色球"},
      description={"en": "The stk:orientation-hsl colour sphere overlay (SimViz orientation legend)."},
      outputs=[Port("layer", "layer")],
      params={
          "title": _nullable_string(stage="client"),
          "anchor": enum(ANCHORS, "bottom_right", stage="client"),
          "size_px": integer(120, minimum=32, maximum=512, stage="client"),
          "lightness_range": json_param({"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1},
                                         "minItems": 2, "maxItems": 2}, [0.0, 1.0], stage="client"),
      })
def orientation_legend(ctx, inputs, params):
    _todo()


# ---------------------------------------------------------------------------
# View


@node("stk.view.camera", title={"en": "Camera", "zh": "相机"},
      description={"en": "A preset (fit to the scene bounds) or a numeric camera in physical coordinates."},
      outputs=[Port("camera", "camera")],
      params={
          "preset": enum(["iso", "+x", "-x", "+y", "-y", "+z", "-z", None], "iso"),
          "position": vector3(None, nullable=True),
          "focal_point": vector3(None, nullable=True),
          "view_up": vector3(None, nullable=True),
          "projection": enum(["perspective", "parallel"], "perspective"),
          "view_angle_deg": number(30.0, exclusive_minimum=0, exclusive_maximum=180),
          "zoom": number(1.0, exclusive_minimum=0),
          "parallel_scale": number(None, nullable=True, exclusive_minimum=0),
      })
def camera(ctx, inputs, params):
    _todo()


@node("stk.view.scene", title={"en": "Scene", "zh": "场景"},
      description={"en": "Ordered layers plus the view (camera, viewport, background, lighting)."},
      inputs=[Port("layers", "layer", multi=True), Port("camera", "camera", required=False)],
      outputs=[Port("scene", "scene")],
      params={
          "background": color([1.0, 1.0, 1.0]),
          "lighting": enum(["three_point", "headlight", "none"], "three_point"),
          "width": integer(1600, minimum=16, maximum=16384),
          "height": integer(1200, minimum=16, maximum=16384),
          "render_origin": json_param({"anyOf": [{"const": "auto"},
                                                 {"type": "array", "items": {"type": "number"}, "minItems": 3,
                                                  "maxItems": 3}]}, "auto"),
          "title": _nullable_string(),
      })
def scene(ctx, inputs, params):
    _todo()


# ---------------------------------------------------------------------------
# Output


@node("stk.output.payload", title={"en": "Render payload", "zh": "渲染数据包"},
      description={"en": "Encode a scene as stk.payload/2 within the profile budget (optionally with a scene v1 "
                         "downgrade)."},
      inputs=[Port("scene", "scene")],
      outputs=[Port("payload", "payload")],
      params={
          "profile": enum(["auto", "phone", "web", "desktop"], "auto",
                          description="Payload budget profile; auto = the request profile (Budget.profile)"),
          "budget": json_param({"anyOf": [{"type": "null"}, {
              "type": "object", "additionalProperties": False,
              "properties": {key: {"type": "integer", "minimum": 0}
                             for key in ("triangles", "instances", "points", "voxels", "bytes")}}]}, None),
          "v1_fallback": boolean(False),
      })
def payload_output(ctx, inputs, params):
    _todo()


@node("stk.output.image", title={"en": "Image", "zh": "图片"},
      description={"en": "Render a scene (offscreen VTK in a subprocess) or a plot (matplotlib) to PNG; plots "
                         "also to SVG/PDF."},
      inputs=[Port("source", ["scene", "plot"])],
      outputs=[Port("image", "image")],
      params={
          "width": integer(None, nullable=True, minimum=16, maximum=16384),
          "height": integer(None, nullable=True, minimum=16, maximum=16384),
          "magnification": integer(1, minimum=1, maximum=8),
          "transparent": boolean(False),
          "format": enum(["png", "svg", "pdf"], "png"),
      })
def image_output(ctx, inputs, params):
    _todo()


@node("stk.output.dataset", title={"en": "Dataset export", "zh": "数据导出"},
      description={"en": "Write a dataset to VTKHDF (STK profile), VTI or NPY, or a table to CSV/JSON."},
      inputs=[Port("in", "dataset")],
      outputs=[Port("file", "file")],
      params={
          "format": enum(["vtkhdf", "vti", "npy", "csv", "json"], "vtkhdf", stage="data"),
          "name": _nullable_string(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$", stage="data",
                                   title="File stem (null = node id)"),
          "fields": string_list(None, nullable=True, max_items=64, stage="data"),
          "precision": enum(["float64", "float32"], "float64", stage="data"),
      })
def dataset_output(ctx, inputs, params):
    _todo()


# ---------------------------------------------------------------------------
# Plot


@node("stk.plot.line", title={"en": "Line plot", "zh": "曲线图"},
      description={"en": "Columns against x with an optional second y axis (from 'table2' when linked), row "
                         "filters and per-column styles (SimViz 1D page)."},
      inputs=[Port("table", "table"), Port("table2", "table", required=False)],
      outputs=[Port("plot", "plot")],
      params={
          "x": _nullable_string(title="x column (null = index column)"),
          "y": string_list(min_items=1, max_items=16),
          "y2": string_list([], max_items=16),
          "filters": array(ROW_FILTER, [], max_items=16),
          "stride": integer(1, minimum=1),
          "last_n": integer(None, nullable=True, minimum=1),
          "x_label": _nullable_string(stage="client"),
          "y_label": _nullable_string(stage="client"),
          "y2_label": _nullable_string(stage="client"),
          "x_scale": enum(["linear", "log", "symlog"], "linear", stage="client"),
          "y_scale": enum(["linear", "log", "symlog"], "linear", stage="client"),
          "y2_scale": enum(["linear", "log", "symlog"], "linear", stage="client"),
          "styles": json_param({"type": "object", "additionalProperties": STYLE}, {}, stage="client"),
          "legend": boolean(True, stage="client"),
          "grid": boolean(True, stage="client"),
          "stats": boolean(False, stage="client"),
          **_plot_common(),
      })
def line(ctx, inputs, params):
    _todo()


@node("stk.plot.heatmap", title={"en": "Heatmap", "zh": "热图"},
      description={"en": "2D slice of an image field as a heatmap (label fields use their categorical palette)."},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("plot", "plot")],
      params={
          "field": field_ref(None, nullable=True),
          "axis": enum(["x", "y", "z"], "z"),
          "index": integer(None, nullable=True, minimum=0),
          "colormap": string("viridis", min_length=1, stage="client", widget="colormap"),
          "range": interval([None, None], stage="client"),
          "aspect": enum(["equal", "auto"], "equal", stage="client"),
          "colorbar": boolean(True, stage="client"),
          **_plot_common(),
      })
def heatmap(ctx, inputs, params):
    _todo()


@node("stk.plot.histogram", title={"en": "Histogram", "zh": "直方图"},
      description={"en": "Histogram of a field (image/polydata) or a column (table)."},
      inputs=[Port("in", "dataset", accepts=["image", "polydata", "table"])],
      outputs=[Port("plot", "plot")],
      params={
          "field": field_ref(None, nullable=True),
          "bins": integer(64, minimum=1, maximum=10000),
          "range": interval([None, None]),
          "density": boolean(False),
          "log": boolean(False, stage="client"),
          "color": string("C0", min_length=1, stage="client"),
          **_plot_common(),
      })
def histogram(ctx, inputs, params):
    _todo()


@node("stk.plot.bar", title={"en": "Bar chart", "zh": "柱状图"},
      description={"en": "Bars of value columns per category row (e.g. label fractions)."},
      inputs=[Port("table", "table")],
      outputs=[Port("plot", "plot")],
      params={
          "x": string(min_length=1, title="Category column"),
          "y": string_list(min_items=1, max_items=8),
          "color_column": _nullable_string(title="Column of '#rrggbb' colours"),
          "orientation": enum(["vertical", "horizontal"], "vertical", stage="client"),
          "log": boolean(False, stage="client"),
          **_plot_common(),
      })
def bar(ctx, inputs, params):
    _todo()


# ---------------------------------------------------------------------------
# Export


CATALOG_PATH = Path(__file__).with_name("stk-catalog-m1.json")
SPEC_PATH = ROOT / "docs" / "specs" / "stk-graph-v1.md"
BEGIN, END = "<!-- catalog:begin (generated by docs/specs/catalog/m1_nodes.py) -->", "<!-- catalog:end -->"


def catalog():
    return REGISTRY.catalog(include_impl=False)


def catalog_text():
    return json.dumps(catalog(), indent=1, ensure_ascii=False) + "\n"


def _short(value):
    return json.dumps(value, ensure_ascii=False).replace("|", "\\|")


def _schema_label(fragment):
    if fragment.get("x-stk-widget") == "field":
        text = json.dumps(fragment)
        label = f"field of `{fragment.get('x-stk-field-of', 'in')}`"
        label += " (name or {name, component})" if '"component"' in text else " (name)"
        return label + (" \\| null" if '{"type": "null"}' in text else "")
    fragment = {k: v for k, v in fragment.items() if not k.startswith("x-stk") and k not in
                ("default", "title", "description")}
    if "enum" in fragment:
        return "enum " + " \\| ".join(_short(v) for v in fragment["enum"])
    if "anyOf" in fragment:
        parts = []
        for sub in fragment["anyOf"]:
            parts.append(_schema_label(sub) if isinstance(sub, dict) else _short(sub))
        return " \\| ".join(parts)
    if "const" in fragment:
        return _short(fragment["const"])
    kind = fragment.get("type")
    if kind == "array":
        items = fragment.get("items")
        count = ""
        if fragment.get("minItems") == fragment.get("maxItems") and "minItems" in fragment:
            count = f"[{fragment['minItems']}]"
        elif "minItems" in fragment or "maxItems" in fragment:
            count = f"[{fragment.get('minItems', 0)}..{fragment.get('maxItems', '')}]"
        if "prefixItems" in fragment:
            return "[" + ", ".join(_schema_label(p) for p in fragment["prefixItems"]) + "]"
        return f"{_schema_label(items) if isinstance(items, dict) else 'any'}{count}"
    if kind == "object":
        return "object"
    label = kind if isinstance(kind, str) else " \\| ".join(kind or ["any"])
    bounds = []
    for key, sign in (("minimum", ">="), ("exclusiveMinimum", ">"), ("maximum", "<="), ("exclusiveMaximum", "<")):
        if key in fragment:
            bounds.append(f"{sign}{fragment[key]}")
    if "pattern" in fragment:
        bounds.append("pattern")
    return label + (f" ({', '.join(bounds)})" if bounds else "")


def _port_text(port, output):
    types = port["type"] if isinstance(port["type"], str) else " \\| ".join(port["type"])
    kinds = port.get("kind") if output else port.get("accepts")
    if kinds:
        types += "<" + (kinds if isinstance(kinds, str) else ", ".join(kinds)) + ">"
    if port.get("kind_from"):
        types += f"<kind of `{port['kind_from']}`>"
    if port.get("value_type"):
        types += f"<{port['value_type']}>"
    flags = []
    if not output:
        flags.append("required" if port.get("required", True) else "optional")
        if port.get("multi"):
            flags.append("multi")
    return f"`{port['name']}`: {types}" + (f" ({', '.join(flags)})" if flags else "")


def markdown():
    lines = []
    for entry in catalog()["nodes"]:
        title = entry["title"]
        heading = f"#### `{entry['id']}` — {title['en']}" + (f" / {title['zh']}" if "zh" in title else "")
        if entry.get("stretch"):
            heading += " (stretch)"
        lines += [heading, ""]
        if entry.get("description"):
            lines += [entry["description"]["en"], ""]
        lines.append(f"- stage `{entry['stage']}`, cache `{entry['cache']}`, "
                     f"time_dependent `{str(entry['time_dependent']).lower()}`")
        inputs = ", ".join(_port_text(p, False) for p in entry["inputs"]) or "none"
        outputs = ", ".join(_port_text(p, True) for p in entry["outputs"])
        lines += [f"- inputs: {inputs}", f"- outputs: {outputs}", ""]
        props = entry["params"]["properties"]
        if props:
            lines += ["| param | type | default | stage |", "|---|---|---|---|"]
            required = set(entry["params"].get("required", ()))
            for name, fragment in props.items():
                default = "**required**" if name in required else f"`{_short(fragment.get('default'))}`"
                lines.append(f"| `{name}` | {_schema_label(fragment)} | {default} | {fragment['x-stk-stage']} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def update_spec(text):
    start, end = text.index(BEGIN) + len(BEGIN), text.index(END)
    return text[:start] + "\n\n" + markdown() + "\n" + text[end:]


if __name__ == "__main__":
    if "--write" in sys.argv:
        CATALOG_PATH.write_text(catalog_text(), encoding="utf-8")
    if "--update-spec" in sys.argv:
        SPEC_PATH.write_text(update_spec(SPEC_PATH.read_text(encoding="utf-8")), encoding="utf-8")
    if len(sys.argv) == 1:
        sys.stdout.write(catalog_text())
