"""Plot nodes ``stk.plot.*@1``: ``stk.plot/1`` specs with their tables embedded (stk-graph-v1.md §8, §14).

The value of a ``plot`` port is a JSON-serializable spec; ``stk.output.image@1``
(or the graph service) renders it with ``suan.plot.mpl`` to PNG/SVG/PDF plus the
plotted data. Axis labels default to the column name and its unit
(``unspecified`` is shown, never guessed). Declarations are copied from
docs/specs/catalog/m1_nodes.py (frozen).
"""
from suan.graph.registry import (
    NodeExecutionError, Port, array, boolean, enum, field_ref, integer, interval, json_param, node, string,
    string_list,
)

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
AXIS_NAMES = ("x", "y", "z")


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


def _plot_common():
    return {
        "title": _nullable_string(stage="client", title="Title"),
        "size_in": json_param(SIZE_IN, [6.0, 4.0], stage="client", title="Figure size (inches)"),
        "dpi": integer(200, minimum=30, maximum=1200, stage="client"),
    }


def _np():
    import numpy
    return numpy


def _fail(message, code="invalid_param", hint=None):
    raise NodeExecutionError(message, code=code, hint=hint)


def _figure(params):
    return {"size_in": [float(v) for v in params["size_in"]], "dpi": int(params["dpi"]), "style": "stk-paper",
            "title": params.get("title")}


def _finish(spec):
    from suan.plot.spec import PlotSpecError, check
    try:
        return check(spec)
    except PlotSpecError as error:
        _fail(str(error), code="node_failed")


def _require_table(value, port):
    from suan.data.model import Table
    if not isinstance(value, Table):
        _fail(f"Input {port!r} must be a table", code="kind_mismatch")
    return value


def _need_columns(table, names, port="table"):
    missing = [name for name in names if name not in table.fields]
    if missing:
        _fail(f"Table {port!r} has no column(s) {', '.join(map(repr, missing))}; columns: "
              f"{', '.join(table.columns) or 'none'}")


def _axis(label, columns, table, scale):
    """Axis config: an explicit label wins; otherwise one column's name plus its unit."""
    axis = {"scale": scale}
    if label is not None:
        axis["label"] = label
    elif len(columns) == 1:
        axis["label"] = columns[0]
        axis["unit"] = table.field(columns[0]).unit
    else:
        units = {table.field(c).unit for c in columns}
        if len(units) == 1:
            axis["unit"] = units.pop()
    return axis


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
    from suan.plot.spec import table_payload
    table = _require_table(inputs["table"], "table")
    table2 = _require_table(inputs["table2"], "table2") if "table2" in inputs else None
    if not table.columns:
        _fail("The table has no columns", code="empty_result")
    x = params.get("x") or table.index or table.columns[0]
    y2_table, y2_name = (table2, "table2") if table2 is not None else (table, "table")
    filters = params["filters"]
    _need_columns(table, [x, *params["y"], *(f["column"] for f in filters)])
    x2 = params.get("x") or (y2_table.index or y2_table.columns[0])
    if params["y2"]:
        _need_columns(y2_table, [x2, *params["y2"]], y2_name)
    styles = params["styles"]
    data_common = {"stride": params["stride"]}
    if params.get("last_n"):
        data_common["last_n"] = params["last_n"]
    marks = []
    for name in params["y"]:
        data = {"table": "table", "x": x, "y": name, **data_common}
        if filters:
            data["filter"] = filters
        marks.append({"type": "line", "axes": "a0", "y_axis": "y", "data": data,
                      "style": {"label": name, **styles.get(name, {})}})
    for name in params["y2"]:
        data = {"table": y2_name, "x": x2, "y": name, **data_common}
        usable = [f for f in filters if f["column"] in y2_table.fields]
        if usable:
            data["filter"] = usable
        marks.append({"type": "line", "axes": "a0", "y_axis": "y2", "data": data,
                      "style": {"label": name, "linestyle": "--", **styles.get(name, {})}})
    axes = {"id": "a0", "grid": [0, 0],
            "x": _axis(params.get("x_label"), [x], table, params["x_scale"]),
            "y": _axis(params.get("y_label"), params["y"], table, params["y_scale"]),
            "legend": {"loc": "best"} if params["legend"] else False,
            "grid_lines": bool(params["grid"]), "stats": bool(params["stats"])}
    if params["y2"]:
        axes["y2"] = _axis(params.get("y2_label"), params["y2"], y2_table, params["y2_scale"])
    columns = [x, *params["y"], *(f["column"] for f in filters)]
    tables = {"table": table_payload(table, columns if y2_name != "table" else columns + [x2, *params["y2"]])}
    if y2_name == "table2":
        tables["table2"] = table_payload(table2, [x2, *params["y2"],
                                                  *(f["column"] for f in filters if f["column"] in table2.fields)])
    return _finish({"schema": "stk.plot/1", "figure": _figure(params), "axes": [axes], "marks": marks,
                    "tables": tables})


def _scalar(values, component, np):
    values = np.asarray(values)
    if values.ndim == 1 or values.shape[-1] == 1:
        return values.reshape(values.shape[:-1] if values.ndim > 1 and values.shape[-1] == 1 else values.shape)
    if isinstance(component, int):
        if component >= values.shape[-1]:
            _fail(f"Component {component} outside {values.shape[-1]} components")
        return values[..., component]
    return np.linalg.norm(values.astype(np.float64), axis=-1)


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
    from suan.data.model import ImageData
    from suan.render.colormaps import canonical_name, category_color, is_builtin, to_hex
    np = _np()
    image = inputs["in"]
    if not isinstance(image, ImageData):
        _fail("stk.plot.heatmap needs an image dataset", code="kind_mismatch")
    ref = params.get("field")
    field = (image.fields.get(ref["name"]) if ref else
             next((f for f in image.fields.values() if f.association == "point" and f.dtype != "string"), None))
    if field is None or field.values is None:
        _fail(f"No point field {ref['name'] if ref else ''!r} to plot; fields: {', '.join(image.fields) or 'none'}")
    if field.association != "point":
        _fail(f"Field {field.name!r} is a {field.association} field; heatmaps use point fields")
    axis = AXIS_NAMES.index(params["axis"])
    n = image.dimensions[axis]
    index = n // 2 if params.get("index") is None else params["index"]
    if not 0 <= index < n:
        _fail(f"Index {index} outside 0..{n - 1} along {params['axis']}")
    values = np.asarray(field.values)                       # (nz, ny, nx, c)
    plane = np.take(values, index, axis=2 - axis)           # rows = second remaining axis, columns = first
    z = _scalar(plane, (ref or {}).get("component"), np)
    h_axis, v_axis = [a for a in range(3) if a != axis]
    if not image.is_axis_aligned:
        ctx.warn("The grid is rotated; heatmap axes show grid indices", code="grid_index_axes")
        extent = [-0.5, image.dimensions[h_axis] - 0.5, -0.5, image.dimensions[v_axis] - 0.5]
        unit = "grid_index"
    else:
        extent = []
        for a in (h_axis, v_axis):
            start, step = image.origin[a], image.spacing[a]
            extent += [start - step / 2, start + (image.dimensions[a] - 1) * step + step / 2]
        unit = image.length_unit
    title = f"{field.name} ({params['axis']} = {index})"
    tables = {"slice": {"columns": {"z": z.astype(np.float64).tolist()}, "units": {"z": field.unit},
                        "shape": list(z.shape)}}
    mark = {"type": "heatmap", "axes": "a0", "data": {"table": "slice", "z": "z"}, "extent": extent}
    if field.is_label:
        present = [int(v) for v in np.unique(z[np.isfinite(z)])]
        categories = {c.value: c for c in field.categories or ()}
        rows = [(v, categories[v].name if v in categories else f"unknown({v})",
                 to_hex(category_color(categories[v], field.palette) if v in categories
                        else category_color({"value": v}, None))) for v in sorted(set(categories) | set(present))]
        tables["slice/categories"] = {"columns": {"value": [r[0] for r in rows], "name": [r[1] for r in rows],
                                                  "color": [r[2] for r in rows]}}
        mark["categorical"] = True
    else:
        name = params["colormap"]
        mark["style"] = {"cmap": canonical_name(name) if is_builtin(name) else name}
        if any(v is not None for v in params["range"]):
            mark["range"] = list(params["range"])
        if params["colorbar"]:
            mark["colorbar"] = {"label": f"{field.name} [{field.unit}]"}
    names = [AXIS_NAMES[h_axis], AXIS_NAMES[v_axis]]
    axes = {"id": "a0", "grid": [0, 0], "title": title, "x": {"label": names[0], "unit": unit},
            "y": {"label": names[1], "unit": unit}, "legend": False, "aspect": params["aspect"]}
    return _finish({"schema": "stk.plot/1", "figure": _figure(params), "axes": [axes], "marks": [mark],
                    "tables": tables})


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
    np = _np()
    dataset = inputs["in"]
    ref = params.get("field")
    if ref is not None:
        if ref["name"] not in dataset.fields:
            _fail(f"No field {ref['name']!r}; fields: {', '.join(dataset.fields) or 'none'}")
        field = dataset.fields[ref["name"]]
    else:
        field = next((f for f in dataset.fields.values() if f.values is not None and f.dtype != "string"), None)
        if field is None:
            _fail("The input has no numeric field to histogram")
    if field.dtype == "string" or field.values is None:
        _fail(f"Field {field.name!r} is not numeric")
    values = np.asarray(field.values)
    components = field.components
    values = values.reshape(-1, components) if components > 1 else values.reshape(-1)
    scalar = _scalar(values, (ref or {}).get("component"), np).astype(np.float64).reshape(-1)
    finite = scalar[np.isfinite(scalar)]
    lo, hi = params["range"]
    if len(finite):
        lo = float(finite.min()) if lo is None else float(lo)
        hi = float(finite.max()) if hi is None else float(hi)
    else:
        ctx.warn(f"Field {field.name!r} has no finite values", code="empty_result")
        lo, hi = (0.0 if lo is None else float(lo)), (1.0 if hi is None else float(hi))
    if hi < lo:
        _fail(f"Histogram range [{lo}, {hi}] is empty")
    if hi == lo:
        hi = lo + 1.0
    counts, edges = np.histogram(finite, bins=params["bins"], range=(lo, hi), density=params["density"])
    column = "density" if params["density"] else "count"
    centres = (edges[:-1] + edges[1:]) / 2
    tables = {"hist": {"columns": {"bin_center": centres.tolist(), column: counts.tolist()},
                       "units": {"bin_center": field.unit, column: "1"}}}
    mark = {"type": "hist", "axes": "a0", "data": {"table": "hist", "x": "bin_center", "y": column},
            "bins": params["bins"], "range": [lo, hi], "density": bool(params["density"]), "log": bool(params["log"]),
            "style": {"color": params["color"], "label": field.name}}
    label = field.name if not ref or ref.get("component") is None or components == 1 else \
        f"{field.name}[{ref['component']}]"
    axes = {"id": "a0", "grid": [0, 0], "x": {"label": label, "unit": field.unit}, "y": {"label": column},
            "legend": False}
    return _finish({"schema": "stk.plot/1", "figure": _figure(params), "axes": [axes], "marks": [mark],
                    "tables": tables})


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
    from suan.plot.spec import table_payload
    np = _np()
    table = _require_table(inputs["table"], "table")
    x = params["x"]
    color_column = params.get("color_column")
    _need_columns(table, [x, *params["y"], *([color_column] if color_column else [])])
    payload = table_payload(table, [x, *params["y"]])
    payload["columns"][x] = [str(v) for v in np.asarray(table.column(x)).tolist()]
    colors = None
    if color_column:
        colors = [str(c) if c else "#808080" for c in np.asarray(table.column(color_column)).tolist()]
    horizontal = params["orientation"] == "horizontal"
    marks = []
    for name in params["y"]:
        data = {"table": "table", "x": name, "y": x} if horizontal else {"table": "table", "x": x, "y": name}
        style = {"label": name}
        if colors and len(params["y"]) == 1:
            style["colors"] = colors
        marks.append({"type": "bar", "axes": "a0", "data": data, "style": style, "log": bool(params["log"])})
    value_axis = _axis(None, params["y"], table, "log" if params["log"] else "linear")
    value_axis.pop("scale")
    category_axis = {"label": x}
    axes = {"id": "a0", "grid": [0, 0], "x": value_axis if horizontal else category_axis,
            "y": category_axis if horizontal else value_axis,
            "legend": {"loc": "best"} if len(params["y"]) > 1 else False}
    return _finish({"schema": "stk.plot/1", "figure": _figure(params), "axes": [axes], "marks": marks,
                    "tables": {"table": payload}})
