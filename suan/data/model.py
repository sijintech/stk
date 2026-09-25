"""STK data model v1, in memory (docs/specs/stk-data-format-v1.md).

Datasets are ``ImageData``, ``PolyData`` and ``Table`` (the M1 kinds); the
other kinds of stk.dataset/1 (rectilinear, structured, unstructured,
particles, collection) exist as metadata-only :class:`Dataset` instances.
Time is not a kind: an in-memory dataset is one frame (``time``) and may carry
the frame index of its series (``frames``).

Array layout (the frozen contract):

* ImageData point fields are C-contiguous ``(nz, ny, nx, nc)`` -- VTK order,
  x fastest, zero-copy to VTK and VTKHDF. Cell fields are
  ``(max(nz-1,1), max(ny-1,1), max(nx-1,1), nc)``. ``xyz(name)`` returns an
  ``(x, y, z, c)`` view (no copy) for code written against
  ``suan.visualization.scene.Grid``; ``add_field(..., layout="xyzc")`` accepts
  that order and copies once.
* PolyData point fields are ``(n_points, nc)``, cell fields ``(n_cells, nc)``
  with cells ordered verts, lines, polys (VTK order).
* Table columns are ``(n_rows,)`` for one component, ``(n_rows, nc)`` otherwise;
  ``dtype == "string"`` columns hold ``str`` (NumPy unicode or object arrays).

Units are never guessed: ``"unspecified"`` (the default) is not ``"1"``.
NumPy is imported lazily; descriptors, fields and metadata-only datasets work
without it.
"""
from dataclasses import dataclass, field as _dc_field, replace
import math
import re

__all__ = [
    "ASSOCIATIONS", "DTYPES", "KINDS", "M1_KINDS", "TENSORS", "UNIT_TOKENS",
    "CellArray", "Category", "CoordinateFrame", "Dataset", "Field", "FrameRef", "ImageData", "PolyData",
    "Provenance", "SourceRef", "Table", "TimeInfo",
    "dataset_from_descriptor", "json_safe",
]

KINDS = ("image", "rectilinear", "structured", "unstructured", "polydata", "particles", "table", "collection")
M1_KINDS = ("image", "polydata", "table")
ASSOCIATIONS = ("point", "cell", "field", "row")
DTYPES = ("float64", "float32", "int64", "int32", "int16", "int8", "uint64", "uint32", "uint16", "uint8", "string")
INTEGER_DTYPES = ("int64", "int32", "int16", "int8", "uint64", "uint32", "uint16", "uint8")
TENSORS = ("scalar", "vector", "symmetric_tensor", "tensor", "quaternion", "array", "label")
ROLES = ("index", "time", "value", "label", "coordinate")
UNIT_TOKENS = ("unspecified", "1", "normalized", "grid_index")
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

_FIELD_NAME = re.compile(r"^[^/.]{1,128}$")
_DATASET_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")
_QUANTITY = re.compile(r"^([a-z0-9_]+:)?[a-z0-9_]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _np():
    import numpy
    return numpy


def json_safe(value):
    """Plain JSON value: NumPy scalars/arrays to Python, non-finite floats to "NaN"/"Inf"/"-Inf"."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        return json_safe(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Inf" if value > 0 else "-Inf")
    return value


def _floats(values, count, what):
    try:
        result = tuple(float(v) for v in values)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be {count} numbers") from None
    if len(result) != count or not all(math.isfinite(v) for v in result):
        raise ValueError(f"{what} must be {count} finite numbers")
    return result


# ---------------------------------------------------------------------------
# Descriptors


@dataclass(frozen=True)
class Category:
    """One label value of a categorical field. ``color`` is RGB(A) in [0, 1]."""

    value: int
    name: str
    direction: tuple | None = None
    color: tuple | None = None
    family: str | None = None
    aliases: tuple = ()
    description: str | None = None

    def __post_init__(self):
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise ValueError(f"Category value must be an integer, got {self.value!r}")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Category name must be a non-empty string")
        if self.direction is not None:
            object.__setattr__(self, "direction", _floats(self.direction, 3, "Category direction"))
        if self.color is not None:
            color = tuple(float(c) for c in self.color)
            if len(color) not in (3, 4) or not all(0 <= c <= 1 for c in color):
                raise ValueError("Category color must be 3 or 4 numbers in [0, 1]")
            object.__setattr__(self, "color", color)
        object.__setattr__(self, "aliases", tuple(self.aliases))

    def to_json(self):
        result = {"value": self.value, "name": self.name}
        for key in ("direction", "color"):
            if getattr(self, key) is not None:
                result[key] = list(getattr(self, key))
        if self.family is not None:
            result["family"] = self.family
        if self.aliases:
            result["aliases"] = list(self.aliases)
        if self.description is not None:
            result["description"] = self.description
        return result

    @classmethod
    def from_json(cls, data):
        return cls(**{key: (tuple(value) if isinstance(value, list) else value) for key, value in data.items()
                      if not key.startswith("x-")})


@dataclass
class Field:
    """A named array: the field-1 descriptor plus optional ``values`` (NumPy array, dataset layout)."""

    name: str
    association: str = "point"
    dtype: str = "float64"
    components: int = 1
    tensor: str = "scalar"
    unit: str = "unspecified"
    component_names: tuple | None = None
    quantity: str | None = None
    normalization: dict | None = None
    categories: tuple | None = None
    palette: str | None = None
    range: list | None = None
    magnitude_range: list | None = None
    role: str | None = None
    description: str | None = None
    lossy: bool = False
    values: object = _dc_field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self.component_names is not None:
            self.component_names = tuple(self.component_names)
        if self.categories is not None:
            self.categories = tuple(c if isinstance(c, Category) else Category.from_json(c)
                                    for c in self.categories)

    @property
    def is_label(self):
        return self.tensor == "label"

    def category(self, value):
        return next((c for c in self.categories or () if c.value == value), None)

    def validate(self):
        """Raise ``ValueError`` if the descriptor breaks field-1 rules."""
        def fail(message):
            raise ValueError(f"Field {self.name!r}: {message}")
        if not isinstance(self.name, str) or not _FIELD_NAME.match(self.name):
            raise ValueError(f"Field name {self.name!r} must be 1-128 characters without '/' or '.'")
        if self.association not in ASSOCIATIONS:
            fail(f"association must be one of {ASSOCIATIONS}")
        if self.dtype not in DTYPES:
            fail(f"dtype must be one of {DTYPES}")
        if isinstance(self.components, bool) or not isinstance(self.components, int) or self.components < 1:
            fail("components must be a positive integer")
        if self.tensor not in TENSORS:
            fail(f"tensor must be one of {TENSORS}")
        if not isinstance(self.unit, str) or not self.unit:
            fail("unit must be a non-empty string (use 'unspecified' when unknown)")
        if self.component_names is not None and len(self.component_names) != self.components:
            fail(f"{len(self.component_names)} component names for {self.components} components")
        allowed = {"scalar": (1,), "vector": (2, 3), "symmetric_tensor": (6,), "tensor": (4, 9),
                   "quaternion": (4,), "label": (1,)}.get(self.tensor)
        if allowed and self.components not in allowed:
            fail(f"tensor {self.tensor!r} needs {' or '.join(map(str, allowed))} components")
        if self.tensor in ("symmetric_tensor", "tensor", "quaternion") and self.component_names is None:
            fail(f"tensor {self.tensor!r} needs explicit component_names (component order is never assumed)")
        if self.tensor == "label":
            if self.dtype not in INTEGER_DTYPES:
                fail("label fields need an integer dtype")
            if not self.categories:
                fail("label fields need categories")
        if self.dtype == "string" and self.association not in ("row", "field"):
            fail("string fields are only allowed for table rows or field data")
        if self.quantity is not None and not _QUANTITY.match(self.quantity):
            fail("quantity must be 'name' or 'namespace:name' (lower-case)")
        if self.categories:
            values = [c.value for c in self.categories]
            if len(set(values)) != len(values):
                fail("category values must be unique")
        if self.range is not None and len(self.range) != self.components:
            fail("range needs one [min, max] per component")
        if self.role is not None and self.role not in ROLES:
            fail(f"role must be one of {ROLES}")

    def to_json(self):
        """The field-1 descriptor (never includes values)."""
        result = {"name": self.name, "association": self.association, "dtype": self.dtype,
                  "components": self.components, "tensor": self.tensor, "unit": self.unit}
        if self.component_names is not None:
            result["component_names"] = list(self.component_names)
        for key in ("quantity", "normalization", "palette", "role", "description"):
            if getattr(self, key) is not None:
                result[key] = getattr(self, key)
        if self.categories is not None:
            result["categories"] = [c.to_json() for c in self.categories]
        if self.range is not None:
            result["range"] = json_safe([list(pair) for pair in self.range])
        if self.magnitude_range is not None:
            result["magnitude_range"] = json_safe(list(self.magnitude_range))
        if self.lossy:
            result["lossy"] = True
        return result

    @classmethod
    def from_json(cls, data, values=None):
        known = {f for f in cls.__dataclass_fields__ if f != "values"}
        kwargs = {key: value for key, value in data.items() if key in known}
        return cls(**kwargs, values=values)

    def with_values(self, values):
        return replace(self, values=values)

    @staticmethod
    def dtype_name(array):
        """STK dtype name of a NumPy array (``"string"`` for unicode/object arrays)."""
        kind = array.dtype.kind
        if kind in "UO":
            return "string"
        if kind == "b":
            raise ValueError("Boolean arrays are not an STK dtype; convert to uint8")
        name = array.dtype.name
        if name not in DTYPES:
            raise ValueError(f"Unsupported array dtype {name}")
        return name


@dataclass
class TimeInfo:
    """Time of one in-memory frame: integer ``step`` and/or physical ``time`` (with ``unit``)."""

    step: int | None = None
    time: float | None = None
    unit: str = "unspecified"

    def to_json(self):
        return {"index": "step" if self.step is not None else ("time" if self.time is not None else None),
                "step": self.step, "value": self.time,
                "physical": {"unit": self.unit, "known": self.time is not None}}

    @classmethod
    def from_json(cls, data):
        physical = data.get("physical") or {}
        return cls(step=data.get("step"), time=data.get("value"), unit=physical.get("unit", "unspecified"))


@dataclass
class SourceRef:
    """Where one field of one frame lives (relative to the run/binding root)."""

    path: str
    reader: str | None = None
    selector: object = None
    size: int | None = None
    sha256: str | None = None
    media_type: str | None = None

    def to_json(self):
        result = {"path": self.path}
        for key in ("reader", "selector", "size", "sha256", "media_type"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result

    @classmethod
    def from_json(cls, data):
        return cls(**data)


@dataclass
class FrameRef:
    """One entry of a dataset's frame list: step/time and per-field sources ("*" = all fields)."""

    step: int | None = None
    time: float | None = None
    sources: dict = _dc_field(default_factory=dict)
    index: int | None = None

    def to_json(self):
        result = {"step": self.step, "time": self.time,
                  "sources": {name: (s.to_json() if isinstance(s, SourceRef) else s) for name, s in self.sources.items()}}
        if self.index is not None:
            result["index"] = self.index
        return result

    @classmethod
    def from_json(cls, data):
        return cls(step=data.get("step"), time=data.get("time"), index=data.get("index"),
                   sources={name: SourceRef.from_json(s) for name, s in (data.get("sources") or {}).items()})


@dataclass
class CoordinateFrame:
    """A named coordinate frame; ``transform`` is a row-major 4x4 affine to ``parent``."""

    length_unit: str = "unspecified"
    parent: str | None = None
    transform: list | None = None
    description: str | None = None

    def to_json(self):
        result = {"length_unit": self.length_unit}
        for key in ("parent", "transform", "description"):
            if getattr(self, key) is not None:
                result[key] = getattr(self, key)
        return result

    @classmethod
    def from_json(cls, data):
        return cls(**data)


@dataclass
class Provenance:
    """``activity`` {kind: run|graph|import|convert, id}; ``agent`` {connector, reader, node, stk};
    ``used`` [{path, sha256, role}]; ``derived_from`` ["sha256:..." or graph cache keys]."""

    activity: dict | None = None
    agent: dict | None = None
    used: list = _dc_field(default_factory=list)
    derived_from: list = _dc_field(default_factory=list)
    generated_at: str | None = None

    def to_json(self):
        result = {}
        for key in ("activity", "agent", "generated_at"):
            if getattr(self, key) is not None:
                result[key] = getattr(self, key)
        if self.used:
            result["used"] = list(self.used)
        if self.derived_from:
            result["derived_from"] = list(self.derived_from)
        return result

    @classmethod
    def from_json(cls, data):
        return cls(**data)


# ---------------------------------------------------------------------------
# Datasets


class Dataset:
    """Base dataset. M1 code uses the subclasses; this class alone is a metadata-only descriptor."""

    kind = None

    def __init__(self, id="dataset", *, kind=None, fields=(), time=None, frames=(), provenance=None, attrs=None,
                 label=None, geometry=None):
        if not isinstance(id, str) or not _DATASET_ID.match(id):
            raise ValueError(f"Dataset id {id!r} must match {_DATASET_ID.pattern}")
        if kind is not None:
            if type(self).kind is not None and kind != type(self).kind:
                raise ValueError(f"{type(self).__name__} has kind {type(self).kind!r}")
            if kind not in KINDS:
                raise ValueError(f"Unknown dataset kind {kind!r}")
            self.kind = kind
        if self.kind is None:
            raise ValueError("A dataset needs a kind")
        self.id = id
        self.label = label
        self.fields = {}
        self.time = time
        self.frames = list(frames)
        self.provenance = provenance
        self.attrs = dict(attrs or {})
        self._geometry = dict(geometry) if geometry is not None else None
        for item in fields:
            self.add(item)

    # -- fields -------------------------------------------------------------

    def add(self, field):
        """Add (or replace) a :class:`Field`; its values, if any, are checked against the layout."""
        field.validate()
        if field.values is not None:
            self._check_values(field)
        self.fields[field.name] = field
        return field

    def _check_values(self, field):
        raise ValueError(f"{self.kind} datasets carry no field values in M1")

    def field(self, name):
        try:
            return self.fields[name]
        except KeyError:
            raise KeyError(f"No field {name!r} in dataset {self.id!r}; fields: {', '.join(self.fields) or 'none'}") \
                from None

    def __contains__(self, name):
        return name in self.fields

    @property
    def field_names(self):
        return list(self.fields)

    def label_fields(self):
        return [f for f in self.fields.values() if f.is_label]

    def kinds(self):
        """Lattice kinds this dataset satisfies (see suan.graph.registry.DATASET_KINDS)."""
        return frozenset({self.kind})

    @property
    def nbytes(self):
        return sum(getattr(f.values, "nbytes", 0) for f in self.fields.values())

    def copy(self):
        """Shallow copy: new field dict and metadata, shared arrays."""
        other = object.__new__(type(self))
        other.__dict__.update(self.__dict__)
        other.fields = dict(self.fields)
        other.attrs = dict(self.attrs)
        other.frames = list(self.frames)
        return other

    # -- descriptors --------------------------------------------------------

    def geometry(self):
        return dict(self._geometry) if self._geometry is not None else None

    def descriptor(self):
        """The stk.dataset/1 descriptor (no values)."""
        result = {"schema": "stk.dataset/1", "id": self.id, "kind": self.kind}
        if self.label is not None:
            result["label"] = self.label
        geometry = self.geometry()
        if geometry is not None:
            result["geometry"] = geometry
        result["columns" if self.kind == "table" else "fields"] = [f.to_json() for f in self.fields.values()]
        if self.time is not None:
            result["time"] = self.time.to_json()
        if self.frames:
            result["frames"] = [f.to_json() if isinstance(f, FrameRef) else f for f in self.frames]
        if self.provenance is not None:
            result["provenance"] = self.provenance.to_json()
        if self.attrs:
            result["attrs"] = json_safe(self.attrs)
        return result

    @classmethod
    def from_descriptor(cls, data):
        return dataset_from_descriptor(data)

    def __repr__(self):
        return f"{type(self).__name__}(id={self.id!r}, fields={self.field_names})"


def _common(data):
    return {
        "id": data["id"], "label": data.get("label"),
        "time": TimeInfo.from_json(data["time"]) if data.get("time") else None,
        "frames": [FrameRef.from_json(f) for f in data.get("frames", ())],
        "provenance": Provenance.from_json(data["provenance"]) if data.get("provenance") else None,
        "attrs": data.get("attrs"),
    }


def dataset_from_descriptor(data):
    """Metadata-only dataset (fields without values) from an stk.dataset/1 descriptor."""
    kind = data.get("kind")
    common = _common(data)
    fields = [Field.from_json(f) for f in data.get("columns" if kind == "table" else "fields", ())]
    geometry = data.get("geometry") or {}
    if kind == "image":
        dataset = ImageData(geometry["dimensions"], geometry["origin"], geometry["spacing"],
                            geometry.get("direction", IDENTITY), frame=geometry.get("frame", "grid"),
                            length_unit=geometry.get("length_unit", "unspecified"), **common)
    elif kind == "polydata":
        dataset = PolyData(frame=geometry.get("frame", "grid"), length_unit=geometry.get("length_unit", "unspecified"),
                           **common)
        dataset._counts = {key: geometry[key] for key in ("points", "verts", "lines", "polys") if key in geometry}
    elif kind == "table":
        dataset = Table(**common)
        dataset._rows = geometry.get("rows")
    else:
        dataset = Dataset(kind=kind, geometry=data.get("geometry"), **common)
    for f in fields:
        dataset.add(f)
    return dataset


class ImageData(Dataset):
    """Uniform grid. ``dimensions`` are point counts ``(nx, ny, nz)``; arrays are ``(nz, ny, nx, nc)``.

    ``direction`` is a row-major 3x3 matrix whose columns are the unit axis
    directions (VTK convention); physical point = origin + direction @ (i*dx, j*dy, k*dz).
    """

    kind = "image"

    def __init__(self, dimensions, origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), direction=IDENTITY, *,
                 frame="grid", length_unit="unspecified", id="image", **kw):
        dims = tuple(dimensions)
        if len(dims) != 3 or not all(isinstance(n, int) and not isinstance(n, bool) and n >= 1 for n in dims):
            raise ValueError("Image dimensions must be three positive integers (nx, ny, nz)")
        self.dimensions = dims
        self.origin = _floats(origin, 3, "Origin")
        self.spacing = _floats(spacing, 3, "Spacing")
        if min(self.spacing) <= 0:
            raise ValueError("Spacing must be strictly positive")
        self.direction = _floats(direction, 9, "Direction")
        self.frame = frame
        self.length_unit = length_unit
        super().__init__(id, **kw)

    @property
    def shape_zyx(self):
        nx, ny, nz = self.dimensions
        return (nz, ny, nx)

    @property
    def cell_dimensions(self):
        return tuple(max(n - 1, 1) for n in self.dimensions)

    @property
    def n_points(self):
        nx, ny, nz = self.dimensions
        return nx * ny * nz

    @property
    def is_axis_aligned(self):
        return self.direction == IDENTITY

    def geometry(self):
        return {"frame": self.frame, "length_unit": self.length_unit, "dimensions": list(self.dimensions),
                "origin": list(self.origin), "spacing": list(self.spacing), "direction": list(self.direction)}

    def kinds(self):
        return frozenset({"image", "labels"}) if self.label_fields() else frozenset({"image"})

    def _expected_shape(self, association):
        if association == "point":
            return self.shape_zyx
        if association == "cell":
            cx, cy, cz = self.cell_dimensions
            return (cz, cy, cx)
        return None

    def _check_values(self, field):
        values = field.values
        expected = self._expected_shape(field.association)
        if expected is None:
            return
        if tuple(values.shape) != (*expected, field.components):
            raise ValueError(f"Field {field.name!r} has shape {tuple(values.shape)}; expected "
                             f"{(*expected, field.components)} (z, y, x, components)")
        if Field.dtype_name(values) != field.dtype:
            raise ValueError(f"Field {field.name!r} values are {values.dtype}, descriptor says {field.dtype}")
        if not values.flags.c_contiguous:
            raise ValueError(f"Field {field.name!r} values must be C-contiguous (z, y, x, c)")

    def add_field(self, name, values, *, association="point", layout="zyxc", tensor=None, **meta):
        """Add a field from an array in ``layout`` ``"zyxc"`` (stored as is) or ``"xyzc"`` (copied once).

        A missing component axis is added. ``tensor`` defaults to ``"scalar"``
        for one component, ``"label"`` when ``categories`` are given, else
        ``"array"`` (component meaning is never assumed).
        """
        np = _np()
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[..., None]
        if values.ndim != 4:
            raise ValueError(f"Field {name!r}: expected a 3-D or 4-D array, got {values.ndim}-D")
        if layout == "xyzc":
            values = values.transpose(2, 1, 0, 3)
        elif layout != "zyxc":
            raise ValueError("layout must be 'zyxc' or 'xyzc'")
        values = np.ascontiguousarray(values)
        components = values.shape[3]
        if tensor is None:
            tensor = "label" if meta.get("categories") else ("scalar" if components == 1 else "array")
        field = Field(name, association=association, dtype=Field.dtype_name(values), components=components,
                      tensor=tensor, values=values, **meta)
        return self.add(field)

    def array(self, name, layout="zyxc"):
        values = self.field(name).values
        if values is None:
            raise ValueError(f"Field {name!r} has no values (metadata only)")
        if layout == "zyxc":
            return values
        if layout == "xyzc":
            return values.transpose(2, 1, 0, 3)
        raise ValueError("layout must be 'zyxc' or 'xyzc'")

    def xyz(self, name):
        """``(x, y, z, c)`` view of a field (no copy)."""
        return self.array(name, "xyzc")

    def point(self, i, j, k):
        """Physical position (float64 tuple) of point index (i, j, k)."""
        steps = (i * self.spacing[0], j * self.spacing[1], k * self.spacing[2])
        d = self.direction
        return tuple(self.origin[r] + sum(d[3 * r + c] * steps[c] for c in range(3)) for r in range(3))

    def bounds(self):
        """``[[xmin, ymin, zmin], [xmax, ymax, zmax]]`` of the grid points."""
        nx, ny, nz = self.dimensions
        corners = [self.point(i, j, k) for i in (0, nx - 1) for j in (0, ny - 1) for k in (0, nz - 1)]
        return [[min(c[a] for c in corners) for a in range(3)], [max(c[a] for c in corners) for a in range(3)]]

    # -- scene.Grid adapter (suan/visualization/scene.py is unchanged) -------

    def to_grid(self, name=None):
        """A ``suan.visualization.scene.Grid`` over one point field (an ``(x,y,z,c)`` view, no copy).

        Requires an axis-aligned grid. ``length_unit`` ``"grid_index"`` maps to
        scene v1's ``"grid index"``.
        """
        from suan.visualization.scene import Grid
        if not self.is_axis_aligned:
            raise ValueError("scene.Grid supports axis-aligned images only")
        field = self.field(name) if name is not None else next(
            (f for f in self.fields.values() if f.association == "point"), None)
        if field is None or field.association != "point":
            raise ValueError("scene.Grid needs a point field")
        units = "grid index" if self.length_unit == "grid_index" else self.length_unit
        step = self.time.step if self.time is not None else None
        return Grid(self.xyz(field.name), origin=self.origin, spacing=self.spacing, units=field.unit,
                    field=field.name, coordinate_units=units, timestep=step)

    @classmethod
    def from_grid(cls, grid, *, id=None, tensor=None, frame="grid", **meta):
        """ImageData with one point field from a ``scene.Grid`` (values copied to (z,y,x,c))."""
        units = "grid_index" if grid.coordinate_units == "grid index" else grid.coordinate_units
        nx, ny, nz = grid.dimensions
        image = cls((int(nx), int(ny), int(nz)), grid.origin, grid.spacing, frame=frame, length_unit=units,
                    id=id or grid.field, time=TimeInfo(step=grid.timestep) if grid.timestep is not None else None)
        image.add_field(grid.field, grid.values, layout="xyzc", tensor=tensor, unit=grid.units, **meta)
        return image


@dataclass
class CellArray:
    """VTK-style cells: ``offsets`` (n_cells + 1, starting at 0) into ``connectivity`` (int64 arrays)."""

    offsets: object
    connectivity: object

    @property
    def n_cells(self):
        return max(len(self.offsets) - 1, 0)

    @classmethod
    def uniform(cls, cells):
        """From an ``(n_cells, k)`` array (e.g. triangles, k = 3)."""
        np = _np()
        cells = np.asarray(cells, dtype=np.int64)
        if cells.ndim != 2:
            raise ValueError("Uniform cells must be an (n_cells, k) array")
        n, k = cells.shape
        return cls(np.arange(0, (n + 1) * k, k, dtype=np.int64), np.ascontiguousarray(cells.reshape(-1)))

    @classmethod
    def empty(cls):
        np = _np()
        return cls(np.zeros(1, dtype=np.int64), np.zeros(0, dtype=np.int64))

    def validate(self, n_points):
        np = _np()
        offsets, connectivity = np.asarray(self.offsets), np.asarray(self.connectivity)
        if offsets.ndim != 1 or len(offsets) < 1 or offsets[0] != 0 or offsets[-1] != len(connectivity):
            raise ValueError("Cell offsets must start at 0 and end at len(connectivity)")
        if np.any(np.diff(offsets) < 0):
            raise ValueError("Cell offsets must be non-decreasing")
        if len(connectivity) and (connectivity.min() < 0 or connectivity.max() >= n_points):
            raise ValueError("Cell connectivity refers to missing points")


class PolyData(Dataset):
    """Points ``(n, 3)`` float64 plus ``verts``/``lines``/``polys`` :class:`CellArray` (VTK order)."""

    kind = "polydata"

    def __init__(self, points=None, *, verts=None, lines=None, polys=None, frame="grid", length_unit="unspecified",
                 id="polydata", **kw):
        self.frame = frame
        self.length_unit = length_unit
        self._counts = {}
        if points is not None:
            np = _np()
            points = np.ascontiguousarray(points, dtype=np.float64)
            if points.ndim != 2 or points.shape[1] != 3:
                raise ValueError("Points must be an (n, 3) array")
            self.points = points
            self.verts = verts if verts is not None else CellArray.empty()
            self.lines = lines if lines is not None else CellArray.empty()
            self.polys = polys if polys is not None else CellArray.empty()
            for cells in (self.verts, self.lines, self.polys):
                cells.validate(len(points))
        else:
            self.points = None
            self.verts = verts
            self.lines = lines
            self.polys = polys
        super().__init__(id, **kw)

    @classmethod
    def from_triangles(cls, points, triangles, **kw):
        return cls(points, polys=CellArray.uniform(triangles), **kw)

    @property
    def n_points(self):
        return len(self.points) if self.points is not None else self._counts.get("points")

    def _n(self, name):
        cells = getattr(self, name)
        return cells.n_cells if cells is not None else self._counts.get(name, 0)

    @property
    def n_cells(self):
        return self._n("verts") + self._n("lines") + self._n("polys")

    def kinds(self):
        if self._n("lines") == 0 and self._n("polys") == 0:
            return frozenset({"polydata", "points"})
        return frozenset({"polydata"})

    def geometry(self):
        result = {"frame": self.frame, "length_unit": self.length_unit}
        if self.n_points is not None:
            result.update(points=self.n_points, verts=self._n("verts"), lines=self._n("lines"),
                          polys=self._n("polys"))
            if self.points is not None and len(self.points):
                result["bounds"] = self.bounds()
        return result

    def bounds(self):
        return [self.points.min(axis=0).tolist(), self.points.max(axis=0).tolist()]

    def _check_values(self, field):
        values = field.values
        expected = {"point": self.n_points, "cell": self.n_cells}.get(field.association)
        if expected is None:
            return
        if values.ndim != 2 or values.shape != (expected, field.components):
            raise ValueError(f"Field {field.name!r} has shape {tuple(values.shape)}; expected "
                             f"({expected}, {field.components})")
        if Field.dtype_name(values) != field.dtype:
            raise ValueError(f"Field {field.name!r} values are {values.dtype}, descriptor says {field.dtype}")

    def add_field(self, name, values, *, association="point", tensor=None, **meta):
        np = _np()
        values = np.asarray(values)
        if values.ndim == 1:
            values = values[:, None]
        values = np.ascontiguousarray(values)
        components = values.shape[1]
        if tensor is None:
            tensor = "label" if meta.get("categories") else ("scalar" if components == 1 else "array")
        return self.add(Field(name, association=association, dtype=Field.dtype_name(values), components=components,
                              tensor=tensor, values=values, **meta))

    def array(self, name):
        return self.field(name).values


class Table(Dataset):
    """Named columns (fields with association ``"row"``). ``index`` names the index column, if any."""

    kind = "table"

    def __init__(self, id="table", *, index=None, **kw):
        self.index = index
        self._rows = None
        super().__init__(id, **kw)

    @property
    def n_rows(self):
        for f in self.fields.values():
            if f.values is not None:
                return len(f.values)
        return self._rows if self._rows is not None else 0

    @property
    def columns(self):
        return list(self.fields)

    def geometry(self):
        return {"rows": self.n_rows if any(f.values is not None for f in self.fields.values()) else self._rows}

    def kinds(self):
        if {"dataset", "step", "path"} <= set(self.fields):
            return frozenset({"table", "frames"})
        return frozenset({"table"})

    def _check_values(self, field):
        values = field.values
        if field.association != "row":
            raise ValueError(f"Table column {field.name!r} must have association 'row'")
        expected_ndim = 1 if field.components == 1 else 2
        if values.ndim != expected_ndim or (expected_ndim == 2 and values.shape[1] != field.components):
            raise ValueError(f"Column {field.name!r} has shape {tuple(values.shape)} for {field.components} "
                             "component(s)")
        rows = next((len(f.values) for f in self.fields.values()
                     if f.values is not None and f.name != field.name), None)
        if rows is not None and len(values) != rows:
            raise ValueError(f"Column {field.name!r} has {len(values)} rows; the table has {rows}")
        if Field.dtype_name(values) != field.dtype:
            raise ValueError(f"Column {field.name!r} values are {values.dtype}, descriptor says {field.dtype}")

    def add_column(self, name, values, *, unit="unspecified", tensor=None, **meta):
        np = _np()
        values = np.asarray(values)
        if values.dtype.kind == "b":
            values = values.astype(np.uint8)
        if values.ndim == 0 or values.ndim > 2:
            raise ValueError(f"Column {name!r} must be 1-D or 2-D")
        components = 1 if values.ndim == 1 else values.shape[1]
        if tensor is None:
            tensor = "label" if meta.get("categories") else ("scalar" if components == 1 else "array")
        return self.add(Field(name, association="row", dtype=Field.dtype_name(values), components=components,
                              tensor=tensor, unit=unit, values=values, **meta))

    def column(self, name):
        return self.field(name).values

    @classmethod
    def from_columns(cls, columns, *, units=None, quantities=None, id="table", index=None, **kw):
        table = cls(id, index=index, **kw)
        for name, values in columns.items():
            role = "index" if name == index else None
            table.add_column(name, values, unit=(units or {}).get(name, "unspecified"),
                             quantity=(quantities or {}).get(name), role=role)
        return table

    def to_json(self, max_rows=None):
        """``{"columns": {name: [...]}, "units": {name: unit}}``; non-finite numbers as "NaN"/"Inf"/"-Inf"."""
        columns = {}
        for name, f in self.fields.items():
            values = f.values if max_rows is None else f.values[:max_rows]
            columns[name] = json_safe(values)
        return {"columns": columns, "units": {name: f.unit for name, f in self.fields.items()}}
