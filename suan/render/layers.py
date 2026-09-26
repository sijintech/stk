"""Render layers and scenes: the in-memory values of the graph port types ``layer`` and ``scene``.

A :class:`Layer` holds geometry in **physical float64 coordinates** plus raw
attributes (the representation nodes' data-stage half) and the node-level
appearance (client-stage params, attached by ``finalize`` through
:meth:`Layer.with_appearance`). :func:`suan.render.payload.encode_scene` turns
a :class:`Scene` into ``stk.payload/2``: it subtracts the render origin,
resolves colour specs to payload colour specs and colormaps, and enforces the
profile budget. Layer types follow docs/specs/stk-render-payload-v2.md §6.

Geometry keys per type (NumPy arrays):

* ``triangles``: ``positions`` (n, 3), ``indices`` (m, 3), optional ``normals`` (n, 3)
* ``slice_image``: ``plane`` {origin, u, v} (absolute), ``size`` (w, h)
* ``lines``: ``positions`` (n, 3), ``indices`` (m, 2) segments
* ``points``: ``positions`` (n, 3), optional ``radii`` (n,)
* ``instances``: ``positions`` (n, 3), ``directions`` (n, 3), optional ``scales`` (n,)
* ``volume``: ``grid`` {dimensions, origin (absolute), spacing, direction}, ``data`` (nz, ny, nx)
* ``overlay``: none (``props`` carries the overlay keys)
"""
from dataclasses import dataclass, field, replace
import math

from .colormaps import ORIENTATION_HSL, canonical_name, palette_entries

__all__ = [
    "ANCHORS", "LAYER_TYPES", "ORIENTATION_HSL", "OVERLAY_KINDS", "PRESETS",
    "Attribute", "Layer", "Scene", "camera_pose", "default_view_up", "fit_camera", "grid_corners", "resolve_range",
    "union_bounds", "view_preset",
]

LAYER_TYPES = ("triangles", "slice_image", "lines", "points", "instances", "volume", "overlay")
OVERLAY_KINDS = ("scalar_bar", "legend", "orientation_legend", "text", "axes_triad")
ANCHORS = ("top_left", "top", "top_right", "left", "center", "right", "bottom_left", "bottom", "bottom_right")
_S3 = 1 / math.sqrt(3)
# preset -> (unit direction from the focal point to the camera, view up); "+x" means "looking from +x".
PRESETS = {
    "+x": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), "-x": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "+y": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), "-y": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "+z": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)), "-z": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    "iso": ((_S3, -_S3, _S3), (0.0, 0.0, 1.0)),
}
DEFAULT_COLOR = {"by": "solid", "solid": [0.8, 0.8, 0.8]}


def _np():
    import numpy
    return numpy


@dataclass
class Attribute:
    """A per-point (or per-cell) array of a layer. ``values`` is ``(n,)`` or ``(n, c)``."""

    values: object
    association: str = "point"
    categorical: bool = False
    categories: tuple = ()
    palette: str | None = None
    unit: str | None = None
    quantity: str | None = None
    component_names: tuple | None = None

    @property
    def components(self):
        return 1 if self.values.ndim == 1 else int(self.values.shape[1])

    def __len__(self):
        return int(self.values.shape[0])

    def scalar(self, component=None):
        """float64 ``(n,)``: one component, or the magnitude (``None``/``"magnitude"`` on vectors)."""
        np = _np()
        values = np.asarray(self.values)
        if values.ndim == 1 or values.shape[1] == 1:
            return values.reshape(-1).astype(np.float64)
        if component in (None, "magnitude"):
            return np.linalg.norm(values.astype(np.float64), axis=1)
        if not 0 <= int(component) < values.shape[1]:
            raise ValueError(f"Component {component} outside {values.shape[1]} components")
        return values[:, int(component)].astype(np.float64)

    def finite_range(self, component=None):
        np = _np()
        values = self.scalar(component)
        values = values[np.isfinite(values)]
        return [float(values.min()), float(values.max())] if len(values) else None

    def entries(self):
        """Payload palette entries of a categorical attribute (values present but unnamed included)."""
        np = _np()
        present = np.unique(np.asarray(self.values).reshape(-1)) if len(self) else []
        return palette_entries(self.categories, self.palette, values=[int(v) for v in present])

    def take(self, index):
        return replace(self, values=self.values[index])

    @classmethod
    def from_field(cls, field, values):
        """From a ``suan.data.model.Field`` and values flattened to ``(n,)``/``(n, c)``."""
        np = _np()
        values = np.asarray(values)
        if values.ndim == 2 and values.shape[1] == 1:
            values = values[:, 0]
        return cls(values=values, association="cell" if field.association == "cell" else "point",
                   categorical=bool(field.is_label), categories=tuple(field.categories or ()),
                   palette=field.palette, unit=field.unit, quantity=field.quantity,
                   component_names=tuple(field.component_names) if field.component_names else None)


class Layer:
    """One render layer (see the module docstring for ``geometry`` keys)."""

    def __init__(self, type, *, id="layer", name=None, node=None, geometry=None, attributes=None, props=None,
                 appearance=None, grid=None, stats=None, visible=True, source=None):
        if type not in LAYER_TYPES:
            raise ValueError(f"Unknown layer type {type!r}; expected one of {', '.join(LAYER_TYPES)}")
        self.type = type
        self.id = id
        self.name = name
        self.node = node if node is not None else id
        self.geometry = dict(geometry or {})
        self.attributes = dict(attributes or {})
        self.props = dict(props or {})
        self.appearance = dict(appearance or {})
        self.grid = grid            # {"bounds", "dimensions", "origin", "spacing", "length_unit"} of the source image
        self.stats = dict(stats or {})
        self.visible = visible
        self.source = source        # the upstream Layer an overlay explains (scalar bar / legend)

    def __repr__(self):
        return f"Layer(type={self.type!r}, id={self.id!r}, attributes={list(self.attributes)})"

    def copy(self, **changes):
        other = object.__new__(type(self))
        other.__dict__.update(self.__dict__)
        for key in ("geometry", "attributes", "props", "appearance", "stats"):
            setattr(other, key, dict(getattr(self, key)))
        other.__dict__.update(changes)
        return other

    def with_appearance(self, appearance):
        """Copy with client-stage params merged into ``appearance`` (``finalize`` of render nodes)."""
        merged = {**self.appearance, **{k: v for k, v in dict(appearance).items()}}
        other = self.copy(appearance=merged)
        if merged.get("name") is not None:
            other.name = merged["name"]
        return other

    # -- geometry -----------------------------------------------------------

    @property
    def nbytes(self):
        """Bytes held by the geometry and attribute arrays (for cache accounting)."""
        total = sum(getattr(value, "nbytes", 0) for value in self.geometry.values())
        return total + sum(getattr(a.values, "nbytes", 0) for a in self.attributes.values())

    @property
    def is_3d(self):
        return self.type != "overlay"

    def count(self):
        """Primitive count used for budgets (triangles, texels, segments, points, instances, voxels)."""
        g = self.geometry
        if self.type in ("triangles", "lines"):
            return int(len(g["indices"]))
        if self.type in ("points", "instances"):
            return int(len(g["positions"]))
        if self.type == "slice_image":
            return int(g["size"][0]) * int(g["size"][1])
        if self.type == "volume":
            return int(math.prod(g["grid"]["dimensions"]))
        return 0

    def corners(self):
        """Points spanning the layer's extent (physical), or ``None`` for overlays/empty layers."""
        np = _np()
        g = self.geometry
        if self.type in ("triangles", "lines", "points", "instances"):
            positions = np.asarray(g["positions"], dtype=np.float64).reshape(-1, 3)
            return positions if len(positions) else None
        if self.type == "slice_image":
            o, u, v = (np.asarray(g["plane"][k], dtype=np.float64) for k in ("origin", "u", "v"))
            return np.array([o, o + u, o + v, o + u + v])
        if self.type == "volume":
            return grid_corners(g["grid"])
        return None

    def bounds(self):
        """``[[xmin, ymin, zmin], [xmax, ymax, zmax]]`` (physical) or ``None``."""
        if "bounds" not in self.stats:
            points = self.corners()
            self.stats["bounds"] = None if points is None else [points.min(axis=0).tolist(),
                                                                points.max(axis=0).tolist()]
        return self.stats["bounds"]

    # -- colour -------------------------------------------------------------

    def color_spec(self):
        """The node-level colour spec (``appearance.color`` or the layer default)."""
        spec = self.appearance.get("color")
        if spec is None:
            spec = self.props.get("default_color", DEFAULT_COLOR)
        if isinstance(spec, (list, tuple)):         # a plain RGB colour (e.g. stk.render.outline@1)
            return {"by": "solid", "solid": [float(c) for c in spec]}
        return dict(spec)

    def vectors(self, name=None):
        """``(n, 3)`` vectors used by ``by: "orientation"``: a named 3-component attribute or the directions."""
        if name is not None:
            attribute = self.attributes.get(name)
            if attribute is None or attribute.components != 3:
                raise ValueError(f"Layer {self.id!r} has no 3-component attribute {name!r}")
            return name, attribute.values
        if self.type == "instances":
            return None, self.geometry["directions"]
        for key, attribute in self.attributes.items():
            if attribute.components == 3 and not attribute.categorical:
                return key, attribute.values
        raise ValueError(f"Layer {self.id!r} has no vectors to colour by orientation")

    def color_info(self):
        """Resolve the colour spec against the data.

        Returns ``{"by": "solid", "solid"}``, ``{"by": "attribute", "attribute",
        "component", "categorical": True, "entries", "palette"}``, ``{"by":
        "attribute", "attribute", "component", "categorical": False, "colormap",
        "range", "unit", "quantity"}`` or ``{"by": "direction", "attribute",
        "max_magnitude", "lightness_range"}``. Volumes resolve their transfer
        function instead (``by: "attribute"`` on the volume data).
        """
        np = _np()
        if self.type == "volume":
            return self._volume_color()
        spec = self.color_spec()
        by = spec.get("by", "solid")
        if by == "solid":
            return {"by": "solid", "solid": [float(c) for c in spec.get("solid") or DEFAULT_COLOR["solid"]]}
        if by == "orientation":
            name, vectors = self.vectors(spec.get("field"))
            magnitude = np.linalg.norm(np.asarray(vectors, dtype=np.float64).reshape(-1, 3), axis=1)
            magnitude = magnitude[np.isfinite(magnitude)]
            big = float(magnitude.max()) if len(magnitude) else 0.0
            return {"by": "direction", "attribute": name, "max_magnitude": big if big > 0 else 1.0,
                    "lightness_range": [float(v) for v in spec.get("lightness_range") or (0.0, 1.0)]}
        if by != "field":
            raise ValueError(f"Unknown colour mode {by!r}")
        name = spec.get("field")
        if name is None:
            if not self.attributes:
                raise ValueError(f"Layer {self.id!r} has no attributes to colour by")
            name = next(iter(self.attributes))
        if name not in self.attributes:
            raise ValueError(f"Layer {self.id!r} has no attribute {name!r}; attributes: "
                             f"{', '.join(self.attributes) or 'none'}")
        attribute = self.attributes[name]
        component = spec.get("component")
        if attribute.categorical:
            palette = spec.get("palette") or attribute.palette or "stk:categorical"
            present = [int(v) for v in np.unique(np.asarray(attribute.values).reshape(-1))] if len(attribute) else []
            return {"by": "attribute", "attribute": name, "component": None, "categorical": True,
                    "entries": palette_entries(attribute.categories, palette, values=present), "palette": palette,
                    "unit": attribute.unit}
        value_range = resolve_range(attribute.scalar(component), spec.get("range"), spec.get("range_mode"))
        return {"by": "attribute", "attribute": name, "component": component, "categorical": False,
                "colormap": canonical_name(spec.get("colormap") or "viridis"), "range": value_range,
                "unit": attribute.unit, "quantity": attribute.quantity}

    def _volume_color(self):
        g = self.geometry
        a = self.appearance
        if g.get("categorical"):
            entries = palette_entries(g.get("categories"), g.get("palette"),
                                      values=[int(v) for v in _np().unique(g["data"])])
            return {"by": "attribute", "attribute": g.get("field"), "component": None, "categorical": True,
                    "entries": entries, "palette": g.get("palette") or "stk:categorical", "unit": g.get("unit")}
        value_range = resolve_range(g["data"], a.get("range"), "fixed")
        return {"by": "attribute", "attribute": g.get("field"), "component": None, "categorical": False,
                "colormap": canonical_name(a.get("colormap") or "viridis"), "range": value_range,
                "unit": g.get("unit"), "quantity": g.get("quantity")}


def resolve_range(values, requested=None, mode=None):
    """``[lo, hi]``: ``requested`` with ``null`` ends filled from the finite data (``symmetric``: ±max|v|)."""
    np = _np()
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = values[np.isfinite(values)]
    lo, hi = (float(finite.min()), float(finite.max())) if len(finite) else (0.0, 1.0)
    if mode == "symmetric":
        bound = max(abs(lo), abs(hi))
        lo, hi = -bound, bound
    requested = list(requested) if requested is not None else [None, None]
    lo = float(requested[0]) if requested[0] is not None else lo
    hi = float(requested[1]) if requested[1] is not None else hi
    return [lo, hi]


def grid_corners(grid):
    """The 8 physical corners of an image grid ``{dimensions, origin, spacing, direction}``."""
    np = _np()
    dims = [int(n) for n in grid["dimensions"]]
    spacing = np.asarray(grid["spacing"], dtype=np.float64)
    direction = np.asarray(grid.get("direction") or (1, 0, 0, 0, 1, 0, 0, 0, 1), dtype=np.float64).reshape(3, 3)
    index = np.array([(i, j, k) for k in (0, dims[2] - 1) for j in (0, dims[1] - 1) for i in (0, dims[0] - 1)],
                     dtype=np.float64)
    return np.asarray(grid["origin"], dtype=np.float64) + (index * spacing) @ direction.T


def union_bounds(bounds_list):
    """Union of ``[[min], [max]]`` bounds (``None`` entries skipped); ``None`` if empty."""
    boxes = [b for b in bounds_list if b is not None]
    if not boxes:
        return None
    return [[min(b[0][a] for b in boxes) for a in range(3)], [max(b[1][a] for b in boxes) for a in range(3)]]


def fit_camera(bounds, preset="iso", *, view_angle_deg=30.0, zoom=1.0, projection="perspective"):
    """Camera fitting ``bounds`` (docs/specs/stk-graph-v1.md §7): the focal point is the centre c,
    the position ``c + u * r / sin(theta / 2) / zoom`` and the parallel scale ``r / zoom``."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown camera preset {preset!r}; expected one of {', '.join(PRESETS)}")
    lo, hi = bounds if bounds is not None else ([-1.0] * 3, [1.0] * 3)
    centre = [(float(a) + float(b)) / 2 for a, b in zip(lo, hi)]
    radius = math.sqrt(sum((float(b) - float(a)) ** 2 for a, b in zip(lo, hi))) / 2 or 1.0
    direction, up = PRESETS[preset]
    distance = radius / math.sin(math.radians(view_angle_deg) / 2) / zoom
    return {"projection": projection, "preset": preset,
            "position": [c + u * distance for c, u in zip(centre, direction)],
            "focal_point": centre, "view_up": list(up), "view_angle_deg": float(view_angle_deg),
            "parallel_scale": radius / zoom}


def _unit(a):
    length = math.hypot(*a) or 1.0
    return [v / length for v in a]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _is_vec3(value):
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value))


def _positive(value, fallback):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
    return float(value) if ok else fallback


def _up_for(up, direction):
    """``up``, unless it is within 1e-6 of the view direction: then +z, or +y when looking along z."""
    if math.hypot(*_cross(_unit(up), direction)) < 1e-6:
        return [0.0, 1.0, 0.0] if abs(direction[2]) > 0.99 else [0.0, 0.0, 1.0]
    return [float(v) for v in up]


def default_view_up(position, focal_point):
    """``+z``, or ``+y`` when the view direction is within 1e-6 of the z axis (render payload spec §2.1)."""
    return _up_for([0.0, 0.0, 1.0], _unit([f - p for p, f in zip(position, focal_point)]))


def view_preset(view):
    """Camera preset of an ``stk.view/1`` view: ``camera.preset``, else ``preset``; ``None`` for a numeric
    camera (``position`` and ``focal_point``) without one; ``"iso"`` otherwise (render payload spec §2.1)."""
    view = view if isinstance(view, dict) else {}
    camera = view.get("camera") if isinstance(view.get("camera"), dict) else {}
    preset = camera.get("preset")
    if preset is None:
        preset = view.get("preset")
    if isinstance(preset, str) and preset:
        return preset
    return None if _is_vec3(camera.get("position")) and _is_vec3(camera.get("focal_point")) else "iso"


def camera_pose(view, render_origin, bounds):
    """The camera of an ``stk.view/1`` view as every client shows it (render payload spec §2.1).

    ``bounds`` ``[[min], [max]]`` are relative to ``render_origin`` (``None``: the unit cube); so is the
    returned pose ``{position, focal_point, view_up, view_angle_deg, parallel, parallel_scale}``. A numeric
    camera (``position`` != ``focal_point``) wins over a preset; its ``zoom`` narrows the view angle unless a
    preset is also named (a fitted preset has its zoom built in). Presets fit the bounds. An explicit
    ``view_up`` is kept unless it is within 1e-6 of the view direction; a view angle of 180 degrees or more
    is replaced by 30. Mirrors ``web/src/camera.ts`` ``cameraPose``.
    """
    view = view if isinstance(view, dict) else {}
    camera = view.get("camera") if isinstance(view.get("camera"), dict) else {}
    lo, hi = bounds if bounds is not None else ([-1.0] * 3, [1.0] * 3)
    centre = [(float(a) + float(b)) / 2 for a, b in zip(lo, hi)]
    radius = 0.5 * math.hypot(*(float(b) - float(a) for a, b in zip(lo, hi)))
    if not radius or radius != radius:
        radius = 1.0
    requested = _positive(camera.get("view_angle_deg"), 30.0)
    angle = requested if requested < 180 else 30.0
    zoom = _positive(camera.get("zoom"), 1.0)
    parallel = camera.get("projection") == "parallel"
    preset = view_preset(view)
    parallel_scale = _positive(camera.get("parallel_scale"), radius / zoom)
    position, focal = camera.get("position"), camera.get("focal_point")
    up = camera.get("view_up")
    if _is_vec3(position) and _is_vec3(focal) and any(p != f for p, f in zip(position, focal)):
        position = [float(p) - float(o) for p, o in zip(position, render_origin)]
        focal = [float(f) - float(o) for f, o in zip(focal, render_origin)]
        direction = _unit([f - p for p, f in zip(position, focal)])
        return {"position": position, "focal_point": focal,
                "view_up": _up_for(up if _is_vec3(up) else [0.0, 0.0, 1.0], direction),
                "view_angle_deg": angle / zoom if not parallel and preset is None else angle,
                "parallel": parallel, "parallel_scale": parallel_scale}
    u, preset_up = PRESETS.get(preset or "iso", PRESETS["iso"])
    distance = radius / math.sin((angle * math.pi) / 360) / zoom
    view_up = [float(v) for v in preset_up]
    if _is_vec3(up) and math.hypot(*_cross(_unit(up), u)) > 1e-6:
        view_up = [float(v) for v in up]
    return {"position": [c + d * distance for c, d in zip(centre, u)], "focal_point": centre, "view_up": view_up,
            "view_angle_deg": angle, "parallel": parallel, "parallel_scale": parallel_scale}


@dataclass
class Scene:
    """Ordered layers plus an ``stk.view/1`` view (camera in physical coordinates)."""

    layers: list = field(default_factory=list)
    view: dict = field(default_factory=lambda: {"schema": "stk.view/1"})
    render_origin: tuple = (0.0, 0.0, 0.0)
    length_unit: str = "unspecified"
    time: dict | None = None
    grid: dict | None = None
    title: str | None = None

    def bounds(self):
        return union_bounds([layer.bounds() for layer in self.layers if layer.is_3d])

    @property
    def nbytes(self):
        return sum(layer.nbytes for layer in self.layers)

    def layer(self, layer_id):
        return next(layer for layer in self.layers if layer.id == layer_id)

    def with_view(self, **changes):
        view = {**self.view, **changes}
        return replace(self, view=view)

