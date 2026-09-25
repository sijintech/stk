"""``stk.plot/1`` specs: validation, embedded tables, row selection and mark data.

A spec (``suan/contracts/schemas/plot-1.schema.json``, docs/specs/stk-graph-v1.md
§8) declares a figure, axes (with an optional second y axis) and marks bound to
columns of named tables. Plot nodes embed the tables they read under
``tables`` so a spec travels with its data; columns are JSON lists (non-finite
numbers as ``null``) or, in memory, NumPy arrays.

Conventions beyond the schema:

* ``data.x`` absent: the row index (0, 1, ...) is the x value.
* ``hist`` with ``data.y``: pre-binned data (``x`` = bin centres, ``y`` =
  counts or densities) drawn with ``bins``/``range`` edges.
* ``bar``: horizontal when the ``y`` column holds strings and ``x`` numbers.
* ``heatmap``: ``data.z`` is a 2D column (rows = y); a table named
  ``"<table>/categories"`` with columns ``value``, ``name``, ``color``
  (``#rrggbb``) makes it categorical when ``categorical`` is absent.

Validation and table handling use the standard library (NumPy lazily), so the
hub can check specs without scientific packages.
"""
import copy
import math
import operator

__all__ = [
    "MARK_TYPES", "SCHEMA", "PlotSpecError",
    "axis_label", "categories_table", "check", "column", "mark_data", "select_rows", "table_payload", "validate",
]

SCHEMA = "stk.plot/1"
MARK_TYPES = ("line", "scatter", "bar", "hist", "heatmap", "quiver", "errorbar", "fill_between")
DATA_ROLES = ("x", "y", "z", "u", "v", "yerr", "y2")
OPS = ("==", "!=", ">", ">=", "<", "<=")
_COMPARE = {"==": operator.eq, "!=": operator.ne, ">": operator.gt, ">=": operator.ge, "<": operator.lt,
            "<=": operator.le}


class PlotSpecError(ValueError):
    """An invalid plot spec (message lists JSON-pointer paths)."""


def _np():
    import numpy
    return numpy


def _resolved_schema():
    from suan.contracts import load_schema
    schema = load_schema("plot-1")
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node and node["$ref"].startswith("#/$defs/"):
                return resolve(copy.deepcopy(defs[node["$ref"][len("#/$defs/"):]]))
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node
    return resolve(schema)


_SCHEMA_CACHE = []


def _schema():
    if not _SCHEMA_CACHE:
        _SCHEMA_CACHE.append(_resolved_schema())
    return _SCHEMA_CACHE[0]


def validate(spec):
    """Problems of a spec as ``["<pointer>: <message>", ...]`` (empty when valid)."""
    from suan.graph.schema import check_value
    if not isinstance(spec, dict):
        return [": a plot spec must be a JSON object"]
    shallow = dict(spec)
    tables = spec.get("tables") or {}
    problems = []
    if isinstance(tables, dict):
        shallow["tables"] = {}
        for name, table in tables.items():
            if not isinstance(table, dict) or not isinstance(table.get("columns"), dict):
                problems.append(f"/tables/{name}: needs a 'columns' object")
                continue
            shallow["tables"][name] = {k: v for k, v in table.items() if k != "columns"}
            shallow["tables"][name]["columns"] = {}
            for key, values in table["columns"].items():
                if not (isinstance(values, list) or hasattr(values, "shape")):
                    problems.append(f"/tables/{name}/columns/{key}: must be a list")
    problems += [f"{path}: {message}" for path, message in check_value(shallow, _schema())]
    if problems:
        return problems
    axes = [a["id"] for a in spec["axes"]]
    if len(set(axes)) != len(axes):
        problems.append("/axes: axes ids must be unique")
    for index, mark in enumerate(spec["marks"]):
        path = f"/marks/{index}"
        if mark["axes"] not in axes:
            problems.append(f"{path}/axes: unknown axes {mark['axes']!r}")
        data = mark["data"]
        if "metric" in data:
            continue
        table = data.get("table")
        if table not in tables:
            problems.append(f"{path}/data/table: unknown table {table!r}")
            continue
        columns = tables[table]["columns"]
        roles = [role for role in DATA_ROLES if role in data]
        for role in roles:
            if data[role] not in columns:
                problems.append(f"{path}/data/{role}: table {table!r} has no column {data[role]!r}")
        for j, condition in enumerate(data.get("filter", ())):
            if condition["column"] not in columns:
                problems.append(f"{path}/data/filter/{j}/column: table {table!r} has no column "
                                f"{condition['column']!r}")
        required = {"line": ("y",), "scatter": ("y",), "bar": ("y",), "hist": ("x",), "heatmap": ("z",),
                    "quiver": ("u", "v"), "errorbar": ("y", "yerr"), "fill_between": ("y", "y2")}[mark["type"]]
        for role in required:
            if role not in data:
                problems.append(f"{path}/data: a {mark['type']} mark needs data.{role}")
    return problems


def check(spec):
    """Return ``spec`` or raise :class:`PlotSpecError` listing every problem."""
    problems = validate(spec)
    if problems:
        raise PlotSpecError("Invalid stk.plot/1 spec: " + "; ".join(problems[:10]))
    return spec


# ---------------------------------------------------------------------------
# Tables


def _json_values(values):
    np = _np()
    array = np.asarray(values)
    if array.dtype.kind in "UO":
        return [None if v is None else str(v) for v in array.tolist()]
    if array.dtype.kind == "f":
        return [_finite_list(v) for v in array.tolist()]
    return array.tolist()


def _finite_list(value):
    if isinstance(value, list):
        return [_finite_list(v) for v in value]
    return value if isinstance(value, (int, str)) or value is None or math.isfinite(value) else None


def table_payload(table, columns=None, *, rows=None):
    """``{"columns": {name: [...]}, "units": {...}}`` of a ``suan.data.model.Table`` (non-finite -> null)."""
    names = list(table.columns) if columns is None else list(dict.fromkeys(columns))
    result = {"columns": {}, "units": {}}
    for name in names:
        values = table.column(name)
        if rows is not None:
            values = values[rows]
        result["columns"][name] = _json_values(values)
        result["units"][name] = table.field(name).unit
    return result


def column(spec, table, name):
    """NumPy array of a column: float64 for numbers (null -> NaN), else an object array of strings."""
    np = _np()
    values = spec["tables"][table]["columns"][name]
    if hasattr(values, "dtype"):
        return values.astype(np.float64) if values.dtype.kind in "iufb" else values
    if values and any(isinstance(v, str) for v in values):
        return np.array([None if v is None else str(v) for v in values], dtype=object)
    try:
        return np.array([np.nan if v is None else v for v in values], dtype=np.float64)
    except (TypeError, ValueError):
        return np.array([np.array([np.nan if x is None else x for x in row], dtype=np.float64) if isinstance(row, list)
                         else row for row in values], dtype=object)


def categories_table(spec, table):
    """``[(value, name, color)]`` of ``tables["<table>/categories"]``, or ``None``."""
    entry = (spec.get("tables") or {}).get(f"{table}/categories")
    if entry is None:
        return None
    columns = entry["columns"]
    return list(zip(columns["value"], columns["name"], columns["color"]))


def select_rows(spec, table, data):
    """Row indices kept by ``filter`` (all must hold), then ``stride``, then ``last_n``."""
    np = _np()
    columns = spec["tables"][table]["columns"]
    n = len(next(iter(columns.values()))) if columns else 0
    keep = np.ones(n, dtype=bool)
    for condition in data.get("filter", ()):
        keep &= _filter_mask(column(spec, table, condition["column"]), condition)
    index = np.flatnonzero(keep)
    index = index[::int(data.get("stride", 1))]
    if data.get("last_n"):
        index = index[-int(data["last_n"]):]
    return index


def _filter_mask(values, condition):
    """Rows where ``values <op> value`` holds, compared in the column's type (only the requested operator runs).

    A numeric column compares numbers (a numeric string such as ``"3"`` is converted; any other value is
    a :class:`PlotSpecError`); a string column compares strings (``null`` = ``""``).
    """
    np = _np()
    compare = _COMPARE[condition["op"]]
    target = condition["value"]
    if values.dtype.kind in "iufb":
        try:
            target = float(target)
        except (TypeError, ValueError):
            raise PlotSpecError(f"filter on the numeric column {condition['column']!r} needs a number, "
                                f"got {target!r}") from None
        with np.errstate(invalid="ignore"):
            return np.asarray(compare(values.astype(np.float64), target), dtype=bool)
    strings = np.array(["" if v is None else str(v) for v in values], dtype=str)
    return np.asarray(compare(strings, "" if target is None else str(target)), dtype=bool)


def mark_data(spec, mark, metrics=None):
    """Resolved arrays of one mark: ``{"x", "y", ...}`` (row-selected), or ``None`` when data is unavailable.

    ``metrics`` maps live metric names to ``{"x": [...], "y": [...]}`` for ``data.metric`` marks.
    """
    np = _np()
    data = mark["data"]
    if "metric" in data:
        series = (metrics or {}).get(data["metric"]["names"][0])
        if series is None:
            return None
        return {"x": np.asarray(series.get("x", range(len(series["y"]))), dtype=np.float64),
                "y": np.asarray(series["y"], dtype=np.float64)}
    table = data["table"]
    if mark["type"] == "heatmap":
        z = spec["tables"][table]["columns"][data["z"]]
        return {"z": np.array([[np.nan if v is None else v for v in row] for row in z], dtype=np.float64)
                if not hasattr(z, "dtype") else np.asarray(z, dtype=np.float64)}
    index = select_rows(spec, table, data)
    result = {role: column(spec, table, data[role])[index] for role in DATA_ROLES if role in data}
    if "x" not in result and mark["type"] not in ("hist",):
        result["x"] = index.astype(np.float64)
    return result


def axis_label(axis, default=None):
    """Axis text: ``label`` (or ``default``) plus ``[unit]`` when a unit is given."""
    axis = axis or {}
    label = axis.get("label", default)
    unit = axis.get("unit")
    if unit and label and f"[{unit}]" not in label:
        return f"{label} [{unit}]"
    if unit and not label:
        return f"[{unit}]"
    return label
