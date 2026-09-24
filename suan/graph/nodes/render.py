"""Representation nodes ``stk.render.*@1`` (docs/specs/stk-graph-v1.md §13-§14).

The evaluator runs ``impl`` with the data-stage params only: it prepares
geometry and raw attributes as a :class:`suan.render.layers.Layer` in physical
float64 coordinates. Client-stage params (colours, opacity, glyph shape and
scale, legend placement) are attached afterwards by ``finalize``
(``Layer.with_appearance``), so an appearance change never re-runs data nodes.
Categorical colours come from ``Field.categories`` (set by the analysis nodes);
continuous colormaps live in ``suan.render.colormaps``. Glyphs stay instances
(never expanded meshes) and planar images become ``slice_image`` layers.

Declarations are copied from docs/specs/catalog/m1_nodes.py (frozen). Heavy
imports stay inside the functions: the hub imports catalogs without NumPy.
"""
from suan.graph.registry import (
    FIELD_NAME, NodeExecutionError, Port, boolean, color, enum, field_ref, integer, interval, json_param, node,
    number, string, string_list,
)

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
SHUFFLE_SEED = 0


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


def _np():
    import numpy
    return numpy


def _fail(message, code="invalid_param", hint=None):
    raise NodeExecutionError(message, code=code, hint=hint)


def _layer_id(ctx):
    return getattr(ctx, "node_id", None) or "layer"


def _common_props(dataset):
    props = {"length_unit": getattr(dataset, "length_unit", None)}
    time = getattr(dataset, "time", None)
    if time is not None and (time.step is not None or time.time is not None):
        props["time"] = {"step": time.step, "time": time.time}
    return props


def _pick(ctx, dataset):
    """``pick {probe: {node, dataset}}`` (payload §6): where ``view.probe`` reads for this layer.

    The node is the graph source that read the data (``provenance.agent.node``, set by
    the source nodes and carried by filters and analysis nodes); clients walk upstream
    from it to the frame file. Without provenance it is this layer's own node.
    """
    agent = getattr(getattr(dataset, "provenance", None), "agent", None)
    source = agent.get("node") if isinstance(agent, dict) else None
    probe = {"node": source or _layer_id(ctx)}
    if source and getattr(dataset, "id", None):
        probe["dataset"] = dataset.id
    return {"probe": probe}


def image_grid(image):
    """Grid description of an ImageData (used for outlines, volumes and the scene's render origin)."""
    return {"bounds": image.bounds(), "dimensions": list(image.dimensions), "origin": list(image.origin),
            "spacing": list(image.spacing), "direction": list(image.direction), "length_unit": image.length_unit,
            "frame": image.frame}


def _selected_fields(ctx, dataset, requested, *, associations, skip=()):
    """Fields to send as attributes: ``"all"`` (<= 4 components, numeric) or an explicit list."""
    fields = []
    if requested == "all":
        for f in dataset.fields.values():
            if f.name in skip or f.values is None or f.dtype == "string" or f.association not in associations:
                continue
            if f.components > 4:
                ctx.warn(f"Attribute {f.name!r} has {f.components} components (> 4); not sent",
                         code="attribute_skipped", field=f.name)
                continue
            fields.append(f)
        return fields
    for name in requested or ():
        if name not in dataset.fields:
            _fail(f"No field {name!r} in the input; fields: {', '.join(dataset.fields) or 'none'}")
        f = dataset.fields[name]
        if f.dtype == "string" or f.association not in associations:
            _fail(f"Field {name!r} ({f.association}, {f.dtype}) cannot be sent with this layer")
        fields.append(f)
    return fields


def _attribute(field, values):
    from suan.render.layers import Attribute
    return Attribute.from_field(field, values)


# ---------------------------------------------------------------------------
# Geometry helpers


def _fan(cells, np):
    """``(cell index, a, b, c)`` of the fan triangulation of polygons in a CellArray."""
    offsets = np.asarray(cells.offsets, dtype=np.int64)
    connectivity = np.asarray(cells.connectivity, dtype=np.int64)
    sizes = np.diff(offsets)
    counts = np.maximum(sizes - 2, 0)
    cell = np.repeat(np.arange(len(sizes)), counts)
    start = offsets[:-1][cell]
    local = np.arange(len(cell)) - np.repeat(np.cumsum(counts) - counts, counts)
    tris = np.stack([connectivity[start], connectivity[start + local + 1], connectivity[start + local + 2]], axis=1)
    return cell, tris


def _segments(cells, np):
    """``(cell index, (m, 2) point pairs)`` of the polylines in a CellArray."""
    offsets = np.asarray(cells.offsets, dtype=np.int64)
    connectivity = np.asarray(cells.connectivity, dtype=np.int64)
    sizes = np.diff(offsets)
    counts = np.maximum(sizes - 1, 0)
    cell = np.repeat(np.arange(len(sizes)), counts)
    start = offsets[:-1][cell]
    local = np.arange(len(cell)) - np.repeat(np.cumsum(counts) - counts, counts)
    return cell, np.stack([connectivity[start + local], connectivity[start + local + 1]], axis=1)


def _polydata_layer(ctx, poly, requested):
    from suan.render.layers import Layer
    np = _np()
    if poly.points is None:
        _fail("The input polydata has no points", code="kind_mismatch")
    n_verts, n_lines, n_polys = poly.verts.n_cells, poly.lines.n_cells, poly.polys.n_cells
    normals = poly.fields.get("Normals")
    use_normals = normals is not None and normals.association == "point" and normals.components == 3
    props = {**_common_props(poly), "default_color": {"by": "solid", "solid": [0.8, 0.8, 0.8]},
             "pick": _pick(ctx, poly)}
    common = {"id": _layer_id(ctx), "node": _layer_id(ctx), "name": poly.label or poly.id, "props": props}
    if n_polys:
        cell, tris = _fan(poly.polys, np)
        fields = _selected_fields(ctx, poly, requested, associations=("point", "cell"),
                                  skip=("Normals",) if use_normals else ())
        attributes = {}
        for f in fields:
            values = f.values if f.association == "point" else f.values[n_verts + n_lines + cell]
            attributes[f.name] = _attribute(f, values)
        geometry = {"positions": poly.points, "indices": tris,
                    "normals": np.asarray(normals.values, dtype=np.float64) if use_normals else None}
        return Layer("triangles", geometry=geometry, attributes=attributes, **common)
    if n_lines:
        cell, pairs = _segments(poly.lines, np)
        fields = _selected_fields(ctx, poly, requested, associations=("point", "cell"))
        attributes = {f.name: _attribute(f, f.values if f.association == "point" else f.values[n_verts + cell])
                      for f in fields}
        return Layer("lines", geometry={"positions": poly.points, "indices": pairs}, attributes=attributes, **common)
    fields = _selected_fields(ctx, poly, requested, associations=("point",))
    order = np.random.default_rng(SHUFFLE_SEED).permutation(len(poly.points))
    attributes = {f.name: _attribute(f, np.asarray(f.values)[order]) for f in fields}
    props["progressive"] = {"shuffled": True, "seed": SHUFFLE_SEED}
    return Layer("points", geometry={"positions": poly.points[order]}, attributes=attributes, **common)


def _slice_layer(ctx, image, requested):
    from suan.render.layers import Layer
    np = _np()
    dims = image.dimensions
    flat = [axis for axis in range(3) if dims[axis] == 1]
    if len(flat) != 1:
        _fail(f"Image {dims[0]}x{dims[1]}x{dims[2]} is not planar (exactly one dimension of size 1 is needed)",
              code="not_planar", hint="add stk.filter.slice to cut a plane first")
    axis = flat[0]
    u_axis, v_axis = [a for a in range(3) if a != axis]
    origin = np.asarray(image.point(0, 0, 0))
    last = [0, 0, 0]
    last[u_axis] = dims[u_axis] - 1
    u = np.asarray(image.point(*last)) - origin
    last = [0, 0, 0]
    last[v_axis] = dims[v_axis] - 1
    v = np.asarray(image.point(*last)) - origin
    fields = _selected_fields(ctx, image, requested, associations=("point", "cell"))
    attributes = {}
    for f in fields:
        if f.association != "point":
            ctx.warn(f"Cell field {f.name!r} is not sent with a slice image", code="attribute_skipped", field=f.name)
            continue
        values = np.asarray(f.values)                    # (nz, ny, nx, c): u fastest after dropping the flat axis
        values = np.squeeze(values, axis=2 - axis)       # zyx index of the flat axis is 2 - axis
        attributes[f.name] = _attribute(f, values.reshape(dims[u_axis] * dims[v_axis], f.components))
    props = {**_common_props(image), "default_color": {"by": "field"} if attributes else
             {"by": "solid", "solid": [0.8, 0.8, 0.8]}, "pick": _pick(ctx, image)}
    geometry = {"plane": {"origin": origin.tolist(), "u": u.tolist(), "v": v.tolist()},
                "size": [dims[u_axis], dims[v_axis]]}
    return Layer("slice_image", id=_layer_id(ctx), name=image.label or image.id, geometry=geometry,
                 attributes=attributes, props=props, grid=image_grid(image))


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
    from suan.data.model import ImageData, PolyData
    dataset = inputs["in"]
    if isinstance(dataset, ImageData):
        return _slice_layer(ctx, dataset, params["attributes"])
    if isinstance(dataset, PolyData):
        return _polydata_layer(ctx, dataset, params["attributes"])
    _fail(f"stk.render.surface needs polydata or a planar image, got {type(dataset).__name__}", code="kind_mismatch")


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
    from suan.data.model import PolyData
    from suan.render.layers import Layer
    np = _np()
    poly = inputs["in"]
    if not isinstance(poly, PolyData) or poly.points is None:
        _fail("stk.render.glyphs needs a points dataset (e.g. from stk.filter.glyph_source)", code="kind_mismatch")
    ref = params.get("vectors")
    if ref is not None:
        if ref["name"] not in poly.fields:
            _fail(f"No field {ref['name']!r} in the input; fields: {', '.join(poly.fields) or 'none'}")
        vector_field = poly.fields[ref["name"]]
    else:
        vector_field = next((f for f in poly.fields.values() if f.association == "point" and f.components == 3
                             and f.dtype != "string"), None)
        if vector_field is None:
            _fail("The input has no 3-component point field to orient glyphs", hint="set 'vectors'")
    if vector_field.association != "point" or vector_field.components != 3:
        _fail(f"Field {vector_field.name!r} is not a 3-component point field")
    fields = _selected_fields(ctx, poly, params["attributes"], associations=("point",), skip=(vector_field.name,))
    order = np.random.default_rng(SHUFFLE_SEED).permutation(len(poly.points))
    directions = np.asarray(vector_field.values, dtype=np.float64)[order]
    attributes = {f.name: _attribute(f, np.asarray(f.values)[order]) for f in fields}
    props = {**_common_props(poly), "default_color": {"by": "orientation"},
             "progressive": {"shuffled": True, "seed": SHUFFLE_SEED},
             "vectors": vector_field.name, "vector_unit": vector_field.unit, "pick": _pick(ctx, poly)}
    spacing = poly.attrs.get("sample_spacing")
    if spacing is not None:
        props["sample_spacing"] = float(spacing)
    return Layer("instances", id=_layer_id(ctx), name=poly.label or vector_field.name,
                 geometry={"positions": poly.points[order], "directions": directions},
                 attributes=attributes, props=props)


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
                                [[0.0, 0.0], [1.0, 0.8]], stage="client", widget="transfer_function",
                                title="Opacity points [x, alpha], x normalized over range"),
          "sampling": enum(["linear", "nearest"], "linear", stage="client"),
          "shade": boolean(False, stage="client"),
          "name": _nullable_string(stage="client"),
      })
def volume(ctx, inputs, params):
    from suan.data.model import ImageData
    from suan.render.layers import Layer
    np = _np()
    image = inputs["in"]
    if not isinstance(image, ImageData):
        _fail("stk.render.volume needs an image dataset", code="kind_mismatch")
    ref = params.get("field")
    if ref is None:
        field = next((f for f in image.fields.values() if f.association == "point" and f.values is not None
                      and f.dtype != "string"), None)
        if field is None:
            _fail("The image has no point field to render")
        component = None
    else:
        if ref["name"] not in image.fields:
            _fail(f"No field {ref['name']!r} in the image; fields: {', '.join(image.fields) or 'none'}")
        field, component = image.fields[ref["name"]], ref.get("component")
    if field.association != "point":
        _fail(f"Field {field.name!r} is a {field.association} field; volumes use point fields")
    values = np.asarray(field.values)
    if field.components == 1:
        data = values[..., 0]
    elif isinstance(component, int):
        if component >= field.components:
            _fail(f"Component {component} outside the {field.components} components of {field.name!r}")
        data = values[..., component]
    else:
        data = np.linalg.norm(values.astype(np.float64), axis=-1)
    geometry = {"grid": {k: image_grid(image)[k] for k in ("dimensions", "origin", "spacing", "direction")},
                "data": data, "encoding": params["encoding"], "field": field.name, "unit": field.unit,
                "quantity": field.quantity, "categorical": field.is_label,
                "categories": [c.to_json() for c in field.categories or ()], "palette": field.palette}
    return Layer("volume", id=_layer_id(ctx), name=image.label or field.name, geometry=geometry,
                 props={**_common_props(image), "pick": _pick(ctx, image)}, grid=image_grid(image))


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
    from suan.data.model import ImageData, PolyData
    from suan.render.layers import Layer, grid_corners
    np = _np()
    dataset = inputs["in"]
    grid = None
    if isinstance(dataset, ImageData):
        grid = image_grid(dataset)
        corners = grid_corners(grid)
    elif isinstance(dataset, PolyData) and dataset.points is not None and len(dataset.points):
        lo, hi = dataset.points.min(axis=0), dataset.points.max(axis=0)
        corners = np.array([[(lo, hi)[i][0], (lo, hi)[j][1], (lo, hi)[k][2]]
                            for k in (0, 1) for j in (0, 1) for i in (0, 1)], dtype=np.float64)
    else:
        _fail("stk.render.outline needs an image or a non-empty polydata", code="kind_mismatch")
    edges = np.array([(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)])
    props = {**_common_props(dataset), "default_color": {"by": "solid", "solid": [0.0, 0.0, 0.0]}}
    return Layer("lines", id=_layer_id(ctx), name="Outline", geometry={"positions": corners, "indices": edges},
                 props=props, grid=grid)


def _overlay(ctx, kind, **props):
    from suan.render.layers import Layer
    return Layer("overlay", id=_layer_id(ctx), props={"kind": kind, **props})


@node("stk.render.axes", title={"en": "Axes triad", "zh": "坐标轴"},
      description={"en": "Orientation triad overlay (axes_triad)."},
      outputs=[Port("layer", "layer")],
      params={
          "labels": string_list(["x", "y", "z"], min_items=3, max_items=3, stage="client"),
          "anchor": enum(ANCHORS, "bottom_left", stage="client"),
          "size_px": integer(80, minimum=16, maximum=512, stage="client"),
      })
def axes(ctx, inputs, params):
    return _overlay(ctx, "axes_triad", labels=["x", "y", "z"], anchor="bottom_left", size_px=80)


@node("stk.render.scalar_bar", title={"en": "Scalar bar", "zh": "色标"},
      description={"en": "Scalar bar overlay explaining the continuous colouring of the linked layer."},
      inputs=[Port("source", "layer")],
      outputs=[Port("layer", "layer")],
      params={
          "title": _nullable_string(stage="client", title="Title (null = field and unit)"),
          "anchor": enum(ANCHORS, "right", stage="client"),
          "orientation": enum(["vertical", "horizontal"], "vertical", stage="client"),
          "label_count": integer(5, minimum=2, maximum=20, stage="client"),
          "format": string(".3g", min_length=1, max_length=16, stage="client"),
      })
def scalar_bar(ctx, inputs, params):
    source = inputs["source"]
    try:
        info = source.color_info()
    except (KeyError, ValueError) as error:
        _fail(error.args[0] if isinstance(error, KeyError) and error.args else str(error))
    title = info.get("attribute") or source.name
    unit = info.get("unit")
    if info["by"] == "attribute" and info["categorical"]:
        ctx.warn(f"Layer {source.id!r} is coloured by categories; a legend replaces the scalar bar",
                 code="use_legend")
        return _overlay(ctx, "legend", entries=info["entries"], palette=info["palette"],
                        values=[e["value"] for e in info["entries"] if e["value"] != -1], title=title,
                        source_layer=source.id)
    if info["by"] == "direction":
        ctx.warn(f"Layer {source.id!r} is coloured by direction; an orientation legend replaces the scalar bar",
                 code="use_orientation_legend")
        return _overlay(ctx, "orientation_legend", lightness_range=info["lightness_range"], title="Orientation",
                        source_layer=source.id)
    if info["by"] != "attribute":
        _fail(f"Layer {source.id!r} has a solid colour; a scalar bar needs a colormap", code="invalid_input")
    if unit:
        title = f"{title} [{unit}]"
    return _overlay(ctx, "scalar_bar", colormap=info["colormap"], range=info["range"], unit=unit, title=title,
                    source_layer=source.id, anchor="right", offset_px=[24, 24], size_px=[28, 320])


def _present(values, np):
    values = np.asarray(values).reshape(-1)
    if values.dtype.kind == "f":
        values = values[np.isfinite(values)]
    return [int(v) for v in np.unique(values)]


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
    from suan.render.colormaps import palette_entries
    from suan.render.layers import Layer
    np = _np()
    source = inputs["source"]
    name = params.get("field")
    if isinstance(source, Layer):
        attributes = {k: a for k, a in source.attributes.items() if a.categorical}
        if source.type == "volume" and source.geometry.get("categorical"):
            geometry = source.geometry
            entries = palette_entries(geometry.get("categories"), geometry.get("palette"),
                                      values=_present(geometry["data"], np))
            palette, present, title = geometry.get("palette"), _present(geometry["data"], np), geometry.get("field")
        else:
            if name is None:
                spec = source.color_spec()
                name = spec.get("field") if spec.get("by") == "field" and spec.get("field") in attributes else None
                name = name or next(iter(attributes), None)
            if name not in attributes:
                _fail(f"Layer {source.id!r} has no categorical attribute {name!r}; categorical: "
                      f"{', '.join(attributes) or 'none'}")
            attribute = attributes[name]
            entries, palette, present, title = (attribute.entries(), attribute.palette,
                                                _present(attribute.values, np), name)
        source_layer = source.id
    else:
        labels = [f for f in source.fields.values() if f.is_label]
        field = source.fields.get(name) if name is not None else (labels[0] if labels else None)
        if field is None or not field.is_label:
            names = ', '.join(f.name for f in labels) or 'none'
            _fail(f"The dataset has no label field {name!r}; label fields: {names}")
        present = _present(field.values, np) if field.values is not None else []
        entries = palette_entries(field.categories, field.palette, values=present)
        palette, title, source_layer = field.palette, field.name, None
    if params["only_present"]:
        values = [v for v in present if v != -1]
    else:
        values = [e["value"] for e in entries]
    return _overlay(ctx, "legend", entries=entries, palette=palette or "stk:categorical", values=values, title=title,
                    source_layer=source_layer, anchor="right")


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
    return _overlay(ctx, "orientation_legend", anchor="bottom_right", size_px=120, lightness_range=[0.0, 1.0])
