"""Geometry filters on STK datasets (NumPy + VTK) behind the ``stk.filter.*`` nodes.

Semantics are those of docs/specs/stk-graph-v1.md §14 and
docs/specs/domain-classifiers.md §7. Every function takes an in-memory
:class:`~suan.data.model.ImageData` and returns a **new** dataset: inputs are
never modified (the evaluator hands over read-only arrays shared with its
cache), untouched fields are shared zero-copy, and the provenance, time and
coordinate frame of the input travel with the result.

* image -> image: :func:`crop` (inclusive point-index VOI), :func:`sample`
  (stride, spacing x stride), :func:`calculator` (fixed operations, no
  expression language), :func:`slice_axis` (a planar image), :func:`threshold`
  (a uint8 ``0 outside / 1 inside`` label field);
* image -> polydata: :func:`slice_plane` (``vtkCutter``), :func:`contour`
  (``vtkFlyingEdges3D``, several values), :func:`glyph_source` (points),
  :func:`label_surfaces` (one closed smoothed surface per label),
  :func:`streamlines` (``vtkStreamTracer``).

Label (categorical) fields are never interpolated: slices and glyph samples
take the nearest grid sample. VTK runs on local coordinates (origin 0,
identity direction, the grid spacing) so its float32 points keep their
precision far from the origin; results are mapped back to physical float64
coordinates with the image origin and direction. Only filters that exist in
VTK 9.3 are used (no ``vtkImageThreshold``, no surface-nets output styles);
thresholds are NumPy. NumPy and VTK are imported when a function is called.
"""
import math
import os
import re

__all__ = [
    "FilterError",
    "calculator", "contour", "crop", "effective_stride", "glyph_source", "label_surfaces", "sample",
    "scalar_values", "select_field", "slice_axis", "slice_plane", "streamlines", "threshold",
]

AXES = {"x": 0, "y": 1, "z": 2}
SMOOTHING = ("windowed_sinc", "laplacian", "none")
MAX_CONTOUR_VALUES = 32


class FilterError(ValueError):
    """A filter that cannot run with these inputs; ``code`` is a graph error code (``invalid_param`` ...)."""

    def __init__(self, message, code="invalid_param", hint=None):
        super().__init__(message)
        self.code = code
        self.hint = hint


def _np():
    import numpy
    return numpy


def _ignore(message, *, code="node_warning", **details):
    return None


# ---------------------------------------------------------------------------
# Fields and coordinates


def _ref(ref):
    """``(name | None, component)`` of a field reference: a name, ``{"name", "component"}`` or ``None``."""
    if ref is None:
        return None, None
    if isinstance(ref, str):
        return ref, None
    return ref.get("name"), ref.get("component")


def select_field(dataset, ref=None, *, associations=("point", "cell"), labels=True, min_components=1,
                 what="field"):
    """The :class:`~suan.data.model.Field` a reference names (``None`` = the first numeric field that fits)."""
    name, _ = _ref(ref)
    if name is None:
        for field in dataset.fields.values():
            if (field.values is not None and field.dtype != "string" and field.association in associations
                    and field.components >= min_components and (labels or not field.is_label)):
                return field
        kinds = "" if labels else "non-label "
        raise FilterError(f"The input has no {kinds}{'/'.join(associations)} {what} with at least "
                          f"{min_components} component(s); fields: {', '.join(dataset.fields) or 'none'}")
    field = dataset.fields.get(name)
    if field is None:
        raise FilterError(f"No field {name!r} in the input; fields: {', '.join(dataset.fields) or 'none'}")
    if field.values is None or field.dtype == "string":
        raise FilterError(f"Field {name!r} holds no numeric values")
    if field.association not in associations:
        raise FilterError(f"Field {name!r} is a {field.association} field; this filter uses "
                          f"{' or '.join(associations)} fields")
    if field.is_label and not labels:
        raise FilterError(f"Field {name!r} is a label field (categories are not numbers)",
                          hint="use stk.filter.label_surfaces or stk.filter.threshold with 'labels'")
    if field.components < min_components:
        raise FilterError(f"Field {name!r} has {field.components} component(s); {min_components} are needed")
    return field


def scalar_values(field, component=None):
    """float64 scalars (``values.shape[:-1]``): one component, or the magnitude (``"magnitude"``, or
    ``None`` on a multi-component field; ``"magnitude"`` of one component is ``|v|``)."""
    np = _np()
    values = field.values
    if component is None:
        if field.components == 1:
            return np.asarray(values[..., 0], dtype=np.float64)
        component = "magnitude"
    if component == "magnitude":
        if field.components == 1:
            return np.abs(np.asarray(values[..., 0], dtype=np.float64))
        v = np.asarray(values, dtype=np.float64)
        return np.sqrt(np.einsum("...i,...i->...", v, v))
    if isinstance(component, bool) or not isinstance(component, int) or not 0 <= component < field.components:
        raise FilterError(f"Component {component!r} outside the {field.components} component(s) of {field.name!r}")
    return np.asarray(values[..., component], dtype=np.float64)


def _direction(image):
    return _np().asarray(image.direction, dtype=float).reshape(3, 3)


def _to_physical(image, local, offset=(0.0, 0.0, 0.0)):
    """Physical float64 points of local grid-axis coordinates ``(i dx, j dy, k dz) + offset``."""
    np = _np()
    local = np.asarray(local, dtype=np.float64).reshape(-1, 3) + np.asarray(offset, dtype=np.float64)
    if image.is_axis_aligned:
        return local + np.asarray(image.origin)
    return np.asarray(image.origin) + local @ _direction(image).T


def _to_local(image, points):
    np = _np()
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3) - np.asarray(image.origin)
    if image.is_axis_aligned:
        return points
    return np.linalg.solve(_direction(image), points.T).T


def _rotate(image, vectors):
    """Directions (normals, vectors) from grid axes to physical axes."""
    np = _np()
    if image.is_axis_aligned:
        return vectors
    rotated = np.asarray(vectors, dtype=np.float64) @ _direction(image).T
    return rotated.astype(np.asarray(vectors).dtype, copy=False)


def _grid(image, association):
    """``(dims (nx, ny, nz), local origin offset)`` of the samples of a point or cell field."""
    if association == "cell":
        half = tuple(0.5 * s if n > 1 else 0.0 for s, n in zip(image.spacing, image.dimensions))
        return image.cell_dimensions, half
    return image.dimensions, (0.0, 0.0, 0.0)


def _nearest(image, association, local, values):
    """Nearest samples of a point/cell field ``values`` (z, y, x, c) at local coordinates."""
    np = _np()
    dims, offset = _grid(image, association)
    index = []
    for axis in range(3):
        position = (local[:, axis] - offset[axis]) / image.spacing[axis]
        index.append(np.clip(np.rint(position), 0, dims[axis] - 1).astype(np.int64))
    return values[index[2], index[1], index[0]]


def _vtk_image(dims, spacing, arrays, *, origin=(0.0, 0.0, 0.0), scalars=None, vectors=None):
    """A local ``vtkImageData`` (identity direction) over NumPy point arrays ``{name: (n,) | (n, c)}`` (zero copy)."""
    import vtk
    from .vtkconv import vtk_array
    data = vtk.vtkImageData()
    data.SetDimensions(*[int(n) for n in dims])
    data.SetSpacing(*[float(s) for s in spacing])
    data.SetOrigin(*[float(o) for o in origin])
    for name, values in arrays.items():
        data.GetPointData().AddArray(vtk_array(values, name))
    if scalars is not None:
        data.GetPointData().SetActiveScalars(scalars)
    if vectors is not None:
        data.GetPointData().SetActiveVectors(vectors)
    return data


def _flat(values):
    """(n,) or (n, c) view of a (z, y, x, c) array."""
    components = values.shape[-1]
    return values.reshape(-1) if components == 1 else values.reshape(-1, components)


def _vtk_points(poly):
    np = _np()
    from vtkmodules.util import numpy_support
    points = poly.GetPoints()
    if points is None or poly.GetNumberOfPoints() == 0:
        return np.zeros((0, 3), dtype=np.float64)
    return np.asarray(numpy_support.vtk_to_numpy(points.GetData()), dtype=np.float64).reshape(-1, 3)


def _vtk_cells(cells):
    np = _np()
    from vtkmodules.util import numpy_support
    from .model import CellArray
    if cells is None or cells.GetNumberOfCells() == 0:
        return CellArray.empty()
    offsets = np.array(numpy_support.vtk_to_numpy(cells.GetOffsetsArray()), dtype=np.int64)
    connectivity = np.array(numpy_support.vtk_to_numpy(cells.GetConnectivityArray()), dtype=np.int64)
    return CellArray(offsets, connectivity)


def _vtk_point_array(poly, name):
    from vtkmodules.util import numpy_support
    array = poly.GetPointData().GetArray(name)
    return None if array is None else numpy_support.vtk_to_numpy(array)


def _triangles_only(poly):
    import vtk
    if poly.GetNumberOfStrips() or poly.GetNumberOfPolys() != poly.GetNumberOfCells():
        triangles = vtk.vtkTriangleFilter()
        triangles.SetInputData(poly)
        triangles.PassVertsOff()
        triangles.PassLinesOff()
        triangles.Update()
        return triangles.GetOutput()
    return poly


def _new_image(image, dims, origin, spacing, **changes):
    from .model import ImageData
    kw = dict(frame=image.frame, length_unit=image.length_unit, id=image.id, time=image.time,
              frames=image.frames, provenance=image.provenance, attrs=image.attrs, label=image.label)
    kw.update(changes)
    return ImageData(tuple(int(n) for n in dims), origin, spacing, image.direction, **kw)


def _new_poly(image, points, *, id=None, attrs=None, **cells):
    from .model import PolyData
    return PolyData(points, frame=image.frame, length_unit=image.length_unit, id=id or image.id, time=image.time,
                    provenance=image.provenance, attrs=attrs if attrs is not None else {}, label=image.label, **cells)


def _copy_meta(field, **changes):
    """Field metadata (never values) of ``field`` with changes, for ``add_field`` keyword arguments."""
    meta = {"unit": field.unit, "quantity": field.quantity, "component_names": field.component_names,
            "categories": field.categories, "palette": field.palette, "lossy": field.lossy,
            "description": field.description}
    meta.update(changes)
    return {key: value for key, value in meta.items() if value is not None and value != ()}


def _add(dataset, field, values, *, association=None, tensor=None, **changes):
    """Add ``values`` to ``dataset`` as a field named and described like ``field`` (metadata copied)."""
    return dataset.add_field(field.name, values, association=association or field.association,
                             tensor=tensor or field.tensor, **_copy_meta(field, **changes))


def _chosen_fields(dataset, names, associations=("point", "cell")):
    """Fields to carry: all (``None``) or the named ones (unknown names are an error)."""
    if names is None:
        return [f for f in dataset.fields.values() if f.values is not None and f.association in associations]
    missing = [n for n in names if n not in dataset.fields]
    if missing:
        raise FilterError(f"No field(s) {', '.join(missing)} in the input; fields: "
                          f"{', '.join(dataset.fields) or 'none'}")
    chosen = [dataset.fields[n] for n in dict.fromkeys(names)]
    wrong = [f.name for f in chosen if f.association not in associations or f.values is None or f.dtype == "string"]
    if wrong:
        raise FilterError(f"Field(s) {', '.join(wrong)} cannot be used here (needs numeric "
                          f"{' or '.join(associations)} fields)")
    return chosen


# ---------------------------------------------------------------------------
# image -> image


def crop(image, extent=None):
    """``stk.filter.crop@1``: inclusive point ranges ``[i0, i1, j0, j1, k0, k1]`` (``None`` = start/end).

    Ranges are clipped to the grid; an empty range after clipping is an error.
    The origin moves to point (i0, j0, k0); spacing, direction, fields (C-contiguous
    copies) and categories are kept. Cell fields keep the cells between the kept
    points (one layer when an axis keeps a single point).
    """
    np = _np()
    extent = list(extent) if extent is not None else [None] * 6
    if len(extent) != 6:
        raise FilterError("extent must be [i0, i1, j0, j1, k0, k1]")
    window = []
    for axis, n in enumerate(image.dimensions):
        lo, hi = extent[2 * axis], extent[2 * axis + 1]
        lo = 0 if lo is None else max(0, int(lo))
        hi = n - 1 if hi is None else min(n - 1, int(hi))
        if lo > hi:
            raise FilterError(f"Empty {'xyz'[axis]} range [{extent[2 * axis]}, {extent[2 * axis + 1]}] for "
                              f"{n} point(s)")
        window.append((lo, hi))
    dims = [hi - lo + 1 for lo, hi in window]
    result = _new_image(image, dims, image.point(window[0][0], window[1][0], window[2][0]), image.spacing)
    cells = []
    for (lo, hi), n in zip(window, image.dimensions):
        ncell = max(n - 1, 1)
        start = min(lo, ncell - 1)
        cells.append((start, max(start + 1, min(hi, ncell))))
    for field in image.fields.values():
        if field.values is None:
            result.add(field)
            continue
        ranges = window if field.association == "point" else [(a, b - 1) for a, b in cells]
        if field.association not in ("point", "cell"):
            result.add(field)
            continue
        selection = tuple(slice(lo, hi + 1) for lo, hi in reversed(ranges))
        result.add(field.with_values(np.ascontiguousarray(field.values[selection])))
    return result


def effective_stride(dimensions, stride=(1, 1, 1), max_points=None):
    """The stride after growth: ``stride * f`` with the smallest integer f >= 1 such that
    ``prod(ceil(n_i / (s_i f))) <= max_points`` (``None`` = no limit)."""
    stride = [int(s) for s in stride]
    if len(stride) != 3 or min(stride) < 1:
        raise FilterError("stride must be three integers >= 1")
    if max_points is None:
        return tuple(stride)
    if max_points < 1:
        raise FilterError("max_points must be >= 1")
    factor = 1
    while math.prod(-(-n // (s * factor)) for n, s in zip(dimensions, stride)) > max_points:
        factor += 1
    return tuple(s * factor for s in stride)


def sample(image, stride=(1, 1, 1), max_points=None):
    """``stk.filter.sample@1``: points 0, s, 2s, ... per axis (the last point is not forced), spacing x s.

    Cell fields keep every s-th cell (the cell starting at each kept point).
    Returns ``(image, effective stride)``.
    """
    np = _np()
    steps = effective_stride(image.dimensions, stride, max_points)
    dims = [len(range(0, n, s)) for n, s in zip(image.dimensions, steps)]
    result = _new_image(image, dims, image.origin, [d * s for d, s in zip(image.spacing, steps)])
    cell_dims = result.cell_dimensions
    for field in image.fields.values():
        if field.values is None or field.association not in ("point", "cell"):
            result.add(field)
            continue
        if field.association == "point":
            selection = tuple(slice(None, None, s) for s in reversed(steps))
            values = field.values[selection]
        else:
            selection = tuple(slice(0, None, s) for s in reversed(steps))
            values = field.values[selection][:cell_dims[2], :cell_dims[1], :cell_dims[0]]
        result.add(field.with_values(np.ascontiguousarray(values)))
    return result, steps


def calculator(image, operation, *, field=None, fields=None, component=0, factor=1.0, compose_as="array",
               result=None, unit=None, keep_input=True):
    """``stk.filter.calculator@1``: add one field computed with a fixed operation.

    ``magnitude`` -> |v| (float64, unit kept, ``<field>_magnitude``); ``component``
    -> ``v[..., component]`` (``<field>_<component name or index>``); ``scale`` ->
    v x factor (unit = ``unit``, else the input unit when factor = 1, else
    ``unspecified``; ``<field>_scaled``); ``normalize`` -> v / |v| (0 where |v| = 0,
    unit ``1``; ``<field>_normalized``); ``compose`` -> the scalar ``fields``
    stacked in order (``vector`` needs 2-3 fields and names the components x, y,
    z; ``array`` names them after the fields; unit = the common unit or
    ``unspecified``; ``composed``). ``result`` overrides the name;
    ``keep_input=False`` keeps only the result.
    """
    np = _np()
    if operation == "compose":
        names = list(fields or ())
        if len(names) < 2:
            raise FilterError("compose needs at least two scalar 'fields'")
        sources = []
        for name in names:
            source = select_field(image, name, labels=False)
            if source.components != 1:
                raise FilterError(f"compose stacks scalar fields; {name!r} has {source.components} components")
            sources.append(source)
        if len({s.association for s in sources}) != 1:
            raise FilterError("compose needs fields of one association (all point or all cell)")
        if compose_as == "vector" and len(names) not in (2, 3):
            raise FilterError("A vector is composed of 2 or 3 fields")
        values = np.concatenate([np.asarray(s.values, dtype=np.float64) for s in sources], axis=-1)
        units = {s.unit for s in sources}
        name = result or "composed"
        meta = {"unit": unit or (units.pop() if len(units) == 1 else "unspecified"),
                "tensor": "vector" if compose_as == "vector" else "array",
                "component_names": ("x", "y", "z")[:len(names)] if compose_as == "vector" else tuple(names)}
        association = sources[0].association
    else:
        source = select_field(image, field, labels=False)
        values = np.asarray(source.values, dtype=np.float64)
        association = source.association
        meta = {"quantity": source.quantity}
        if operation == "magnitude":
            values = np.sqrt(np.einsum("...i,...i->...", values, values))[..., None]
            name = result or f"{source.name}_magnitude"
            meta.update(unit=unit or source.unit, tensor="scalar")
        elif operation == "component":
            if isinstance(component, bool) or not isinstance(component, int) or \
                    not 0 <= component < source.components:
                raise FilterError(f"Component {component!r} outside the {source.components} component(s) of "
                                  f"{source.name!r}")
            label = source.component_names[component] if source.component_names else str(component)
            values = np.ascontiguousarray(source.values[..., component:component + 1])
            name = result or f"{source.name}_{label}"
            meta.update(unit=unit or source.unit, tensor="scalar")
        elif operation == "scale":
            values = values * float(factor)
            name = result or f"{source.name}_scaled"
            meta.update(unit=unit or (source.unit if float(factor) == 1.0 else "unspecified"),
                        tensor=source.tensor, component_names=source.component_names)
        elif operation == "normalize":
            norm = np.sqrt(np.einsum("...i,...i->...", values, values))[..., None]
            with np.errstate(invalid="ignore", divide="ignore"):
                values = np.where(norm > 0, values / np.where(norm > 0, norm, 1.0), 0.0)
            name = result or f"{source.name}_normalized"
            meta.update(unit=unit or "1", tensor=source.tensor, component_names=source.component_names,
                        quantity=None)
        else:
            raise FilterError(f"Unknown operation {operation!r}")
    if not re.match(r"^[^/.]{1,128}$", name):
        name = re.sub(r"[/.]", "_", name)[:128]
    output = image.copy()
    if not keep_input:
        output.fields = {}
    meta = {key: value for key, value in meta.items() if value is not None}
    output.add_field(name, np.ascontiguousarray(values), association=association, **meta)
    return output


def slice_axis(image, axis="z", index=None, fields=None):
    """``stk.filter.slice@1`` axis mode: the grid plane at ``index`` (``None`` = n // 2) as an image
    with that axis of size 1 (exact samples; label fields kept; cell fields keep the cell layer)."""
    np = _np()
    a = AXES[axis] if isinstance(axis, str) else int(axis)
    n = image.dimensions[a]
    index = n // 2 if index is None else int(index)
    if not 0 <= index < n:
        raise FilterError(f"Slice index {index} outside 0..{n - 1} along {'xyz'[a]}")
    dims = list(image.dimensions)
    dims[a] = 1
    ijk = [0, 0, 0]
    ijk[a] = index
    result = _new_image(image, dims, image.point(*ijk), image.spacing)
    for field in _chosen_fields(image, fields):
        if field.association == "point":
            layer = index
        elif field.association == "cell":
            layer = min(index, max(n - 1, 1) - 1)
        else:
            continue
        selection = [slice(None)] * 3
        selection[2 - a] = slice(layer, layer + 1)
        result.add(field.with_values(np.ascontiguousarray(field.values[tuple(selection)])))
    return result


def slice_plane(image, origin=None, normal=(0.0, 0.0, 1.0), fields=None, warn=_ignore):
    """``stk.filter.slice@1`` plane mode: an arbitrary plane cut as triangulated polydata.

    ``origin`` ``None`` = the centre of the bounds; ``normal`` is normalized (zero is
    an error). Numeric point fields are interpolated linearly by ``vtkCutter`` (exact
    for fields linear in space); label fields and cell fields take the nearest sample
    (the cell containing each triangle's centroid). Integer point fields that are not
    labels are interpolated as float64.
    """
    import vtk
    np = _np()
    normal = np.asarray(normal, dtype=np.float64)
    length = float(np.linalg.norm(normal))
    if normal.shape != (3,) or not np.isfinite(normal).all() or length == 0:
        raise FilterError("The plane normal must be a nonzero 3-vector")
    normal = normal / length
    if origin is None:
        lo, hi = image.bounds()
        origin = [(a + b) / 2 for a, b in zip(lo, hi)]
    local_origin = _to_local(image, [origin])[0]
    local_normal = _direction(image).T @ normal if not image.is_axis_aligned else normal
    chosen = _chosen_fields(image, fields)
    interpolated = [f for f in chosen if f.association == "point" and not f.is_label]
    arrays = {}
    for i, f in enumerate(interpolated):
        values = f.values if f.values.dtype.kind == "f" else f.values.astype(np.float64)
        arrays[f"a{i}"] = _flat(values)
    if not arrays:  # vtkCutter needs a point array to interpolate; a zero-cost placeholder
        arrays["_"] = np.zeros(image.n_points, dtype=np.float32)
    data = _vtk_image(image.dimensions, image.spacing, arrays)
    plane = vtk.vtkPlane()
    plane.SetOrigin(*local_origin.tolist())
    plane.SetNormal(*local_normal.tolist())
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane)
    cutter.SetInputData(data)
    cutter.GenerateTrianglesOn()
    cutter.SetOutputPointsPrecision(vtk.vtkAlgorithm.DOUBLE_PRECISION)
    cutter.Update()
    cut = _triangles_only(cutter.GetOutput())
    local = _vtk_points(cut)
    polys = _vtk_cells(cut.GetPolys())
    points = _to_physical(image, local)
    # VTK's image plane cutter emits float32 points; put them back on the plane exactly (float64).
    points -= ((points - np.asarray(origin, dtype=np.float64)) @ normal)[:, None] * normal
    poly = _new_poly(image, points, polys=polys,
                     attrs={"plane": {"origin": [float(v) for v in origin], "normal": normal.tolist()}})
    if not len(local):
        warn("The plane does not cut the grid", code="empty_result")
    for i, f in enumerate(interpolated):
        values = _vtk_point_array(cut, f"a{i}")
        values = np.zeros((0, f.components)) if values is None else np.asarray(values)
        values = values.reshape(len(local), f.components)
        dtype = f.values.dtype if f.values.dtype.kind == "f" else np.float64
        _add(poly, f, np.ascontiguousarray(values, dtype=dtype), association="point")
    centroids = None
    for f in chosen:
        if f.association == "point" and f.is_label:
            _add(poly, f, np.ascontiguousarray(_nearest(image, "point", local, f.values)), association="point")
        elif f.association == "cell":
            if centroids is None:
                tris = polys.connectivity.reshape(-1, 3)
                centroids = local[tris].mean(axis=1) if len(tris) else np.zeros((0, 3))
            _add(poly, f, np.ascontiguousarray(_nearest(image, "cell", centroids, f.values)), association="cell")
    return poly


def threshold(image, field, *, lower=None, upper=None, labels=None, invert=False, output="mask"):
    """``stk.filter.threshold@1``: add a uint8 label field ``output`` (1 inside, 0 outside).

    Inside means ``lower <= s <= upper`` (``None`` = unbounded) for the selected
    component, or the magnitude when ``component`` is ``None`` on a multi-component
    field; with ``labels`` (label or integer fields) inside means ``value in labels``.
    ``invert`` flips; non-finite samples are always outside.
    """
    from suan.analysis import palettes
    from .model import Category
    np = _np()
    name, component = _ref(field)
    source = select_field(image, field)
    if labels is not None:
        if not (source.is_label or source.values.dtype.kind in "iu"):
            raise FilterError(f"'labels' selects values of a label or integer field; {source.name!r} is "
                              f"{source.dtype}")
        values = source.values[..., 0] if component is None or source.components == 1 else \
            scalar_values(source, component)
        inside = np.isin(values, np.asarray(list(labels)))
        finite = np.ones(inside.shape, dtype=bool)
    else:
        if source.is_label:
            raise FilterError(f"{source.name!r} is a label field; select categories with 'labels'")
        values = scalar_values(source, component)
        finite = np.isfinite(values)
        inside = finite.copy()
        if lower is not None:
            inside &= values >= float(lower)
        if upper is not None:
            inside &= values <= float(upper)
    if invert:
        inside = ~inside & finite
    result = image.copy()
    categories = (Category(0, "outside", color=palettes.categorical_color(0)),
                  Category(1, "inside", color=palettes.categorical_color(1)))
    result.add_field(output, inside.astype(np.uint8)[..., None], association=source.association, tensor="label",
                     categories=categories, palette=palettes.CATEGORICAL, unit="1")
    result.attrs = {**image.attrs, "threshold": {"field": name or source.name, "component": component,
                                                 "lower": lower, "upper": upper,
                                                 "labels": list(labels) if labels is not None else None,
                                                 "invert": bool(invert)}}
    return result


# ---------------------------------------------------------------------------
# image -> polydata


def contour(image, field, values=None, *, compute_normals=True, probe_fields=None, warn=_ignore):
    """``stk.filter.contour@1``: isosurfaces at one or more values (``vtkFlyingEdges3D``).

    The scalar is selected as in :func:`threshold`; ``values`` ``None`` = one value at
    the middle of the finite data range. Point field ``iso_value`` (float64) holds the
    value each vertex belongs to; ``Normals`` (float32 x 3) when ``compute_normals``;
    ``probe_fields`` are interpolated linearly (label fields: nearest sample).
    Non-finite samples are replaced by a value below every isovalue (warning
    ``nonfinite_samples``). A grid with a dimension of 1 gives isolines (lines).
    """
    import vtk
    np = _np()
    name, component = _ref(field)
    source = select_field(image, field, associations=("point",), labels=False)
    scalars = scalar_values(source, component)
    finite = np.isfinite(scalars)
    if not finite.any():
        warn(f"Field {source.name!r} has no finite samples", code="empty_result")
        return _empty_contour(image, source, compute_normals)
    lo, hi = float(scalars[finite].min()), float(scalars[finite].max())
    levels = [(lo + hi) / 2] if values is None else [float(v) for v in values]
    if not levels or len(levels) > MAX_CONTOUR_VALUES or not all(math.isfinite(v) for v in levels):
        raise FilterError(f"Give 1-{MAX_CONTOUR_VALUES} finite isovalues")
    if not finite.all():  # a placeholder value, then no geometry in the cells that touch those samples
        scalars = np.where(finite, scalars, min(min(levels), lo) - 1.0 - (hi - lo))
        warn(f"{int((~finite).sum())} non-finite samples of {source.name!r}: the cells around them are left out",
             code="nonfinite_samples")
    probes = _chosen_fields(image, probe_fields or [], associations=("point",)) if probe_fields else []
    arrays = {"_s": np.ascontiguousarray(scalars, dtype=np.float64).reshape(-1)}
    numeric = [f for f in probes if not f.is_label]
    for i, f in enumerate(numeric):
        arrays[f"p{i}"] = _flat(f.values if f.values.dtype.kind == "f" else f.values.astype(np.float64))
    data = _vtk_image(image.dimensions, image.spacing, arrays, scalars="_s")
    if min(image.dimensions) >= 2:
        algorithm = vtk.vtkFlyingEdges3D()
        algorithm.ComputeNormalsOn() if compute_normals else algorithm.ComputeNormalsOff()
        algorithm.ComputeGradientsOff()
        algorithm.ComputeScalarsOn()
        algorithm.InterpolateAttributesOn()
    else:
        algorithm = vtk.vtkContourFilter()
        algorithm.ComputeNormalsOff()
        algorithm.ComputeScalarsOn()
    algorithm.SetInputData(data)
    algorithm.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, "_s")
    for i, level in enumerate(levels):
        algorithm.SetValue(i, level)
    algorithm.Update()
    out = algorithm.GetOutput()
    if out.GetNumberOfStrips():
        out = _triangles_only(out)
    local = _vtk_points(out)
    cells = {"polys": _vtk_cells(out.GetPolys()), "lines": _vtk_cells(out.GetLines())}
    kept = slice(None)
    if not finite.all() and len(local):
        cells, kept = _drop_cells(image, local, cells, _bad_cells(finite))
        local = local[kept]
    poly = _new_poly(image, _to_physical(image, local), attrs={"contour": {"field": source.name,
                                                                           "component": component,
                                                                           "values": levels}}, **cells)
    if not len(local):
        warn(f"No isosurface of {source.name!r} at {levels}", code="empty_result")

    def point_array(name, components, dtype):
        values = _vtk_point_array(out, name)
        if values is None:
            return np.zeros((len(local), components), dtype=dtype)
        return np.ascontiguousarray(np.asarray(values, dtype=dtype).reshape(-1, components)[kept])

    poly.add_field("iso_value", point_array("_s", 1, np.float64), unit=source.unit,
                   **({"quantity": source.quantity} if source.quantity else {}))
    if compute_normals and min(image.dimensions) >= 2:
        poly.add_field("Normals", np.ascontiguousarray(_rotate(image, point_array("Normals", 3, np.float32))),
                       tensor="vector", unit="1", component_names=("x", "y", "z"))
    for i, f in enumerate(numeric):
        dtype = f.values.dtype if f.values.dtype.kind == "f" else np.float64
        _add(poly, f, point_array(f"p{i}", f.components, dtype), association="point")
    for f in probes:
        if f.is_label:
            _add(poly, f, np.ascontiguousarray(_nearest(image, "point", local, f.values)), association="point")
    return poly


def _bad_cells(finite):
    """Cells (z, y, x) with a non-finite corner sample."""
    bad = ~finite
    for axis in range(3):
        n = bad.shape[axis]
        if n > 1:
            lo, hi = [slice(None)] * 3, [slice(None)] * 3
            lo[axis], hi[axis] = slice(0, n - 1), slice(1, n)
            bad = bad[tuple(lo)] | bad[tuple(hi)]
    return bad


def _drop_cells(image, local, cells, bad):
    """Remove the cells whose centroid lies in a ``bad`` grid cell; returns ``(cells, kept point indices)``."""
    np = _np()
    from .model import CellArray
    used = np.zeros(len(local), dtype=bool)
    kept = {}
    for name, cell_array in cells.items():
        offsets = np.asarray(cell_array.offsets, dtype=np.int64)
        connectivity = np.asarray(cell_array.connectivity, dtype=np.int64)
        sizes = np.diff(offsets)
        if not len(sizes):
            kept[name] = (sizes, connectivity)
            continue
        owner = np.repeat(np.arange(len(sizes)), sizes)
        index = []
        for axis in range(3):
            centroid = np.bincount(owner, weights=local[connectivity, axis], minlength=len(sizes)) / sizes
            cells_along = bad.shape[2 - axis]
            index.append(np.clip(np.floor(centroid / image.spacing[axis]), 0, cells_along - 1).astype(np.int64))
        ok = ~bad[index[2], index[1], index[0]]
        connectivity = connectivity[ok[owner]]
        used[connectivity] = True
        kept[name] = (sizes[ok], connectivity)
    remap = np.cumsum(used) - 1
    result = {name: CellArray(np.concatenate([[0], np.cumsum(sizes)]).astype(np.int64), remap[connectivity])
              for name, (sizes, connectivity) in kept.items()}
    return result, np.flatnonzero(used)


def _empty_contour(image, source, compute_normals):
    np = _np()
    poly = _new_poly(image, np.zeros((0, 3)))
    poly.add_field("iso_value", np.zeros(0), unit=source.unit)
    if compute_normals:
        poly.add_field("Normals", np.zeros((0, 3), np.float32), tensor="vector", unit="1")
    return poly


def glyph_source(image, field=None, *, sampling="stride", stride=(1, 1, 1), max_points=5000, seed=0,
                 magnitude_range=(None, None), mask_field=None, mask_labels=None, attributes=None):
    """``stk.filter.glyph_source@1``: sample points of a vector field for glyphs.

    Candidates are the points of the stride lattice (``stride``: the lattice grows
    like :func:`sample` until it has at most ``max_points`` points; ``random``: the
    given lattice), kept when |v| is inside ``magnitude_range`` (inclusive, ``None``
    = open) and the mask holds (``mask_field`` value in ``mask_labels``, or nonzero).
    ``random`` draws ``min(max_points, candidates)`` without replacement with
    ``numpy.random.default_rng(seed)`` (output in draw order); ``stride`` keeps grid
    order (x fastest). Point fields: the vector field, ``magnitude`` (float64) and
    ``attributes``; ``attrs["sample_spacing"]`` = min(spacing x effective stride).
    Returns ``(points polydata, effective stride)``.
    """
    np = _np()
    from .model import CellArray
    source = select_field(image, field, associations=("point",), labels=False, min_components=3,
                          what="vector field")
    if source.components != 3:
        raise FilterError(f"Glyphs need a 3-component vector field; {source.name!r} has {source.components}")
    if sampling not in ("stride", "random"):
        raise FilterError(f"Unknown sampling {sampling!r}")
    steps = effective_stride(image.dimensions, stride, max_points if sampling == "stride" else None)
    nx, ny, nz = image.dimensions
    kz, ky, kx = (np.arange(0, n, s) for n, s in zip((nz, ny, nx), reversed(steps)))
    flat_index = ((kz[:, None, None] * ny + ky[None, :, None]) * nx + kx[None, None, :]).reshape(-1)
    vectors = source.values.reshape(-1, 3)[flat_index]
    magnitude = np.sqrt(np.einsum("ij,ij->i", vectors.astype(np.float64), vectors.astype(np.float64)))
    keep = np.isfinite(magnitude)
    lo, hi = (list(magnitude_range) + [None, None])[:2] if magnitude_range is not None else (None, None)
    if lo is not None:
        keep &= magnitude >= float(lo)
    if hi is not None:
        keep &= magnitude <= float(hi)
    if mask_field is not None:
        mask = select_field(image, mask_field, associations=("point",))
        if mask.components != 1:
            raise FilterError(f"Mask field {mask.name!r} must have one component")
        mask_values = mask.values.reshape(-1)[flat_index]
        keep &= np.isin(mask_values, np.asarray(list(mask_labels))) if mask_labels is not None else mask_values != 0
    elif mask_labels is not None:
        raise FilterError("'mask_labels' needs 'mask_field'")
    picked = np.flatnonzero(keep)  # positions in the lattice
    if sampling == "random":
        order = np.random.default_rng(int(seed)).choice(len(picked), size=min(int(max_points), len(picked)),
                                                        replace=False)
        picked = picked[order]
    chosen = flat_index[picked]    # flat grid indices
    i = chosen % nx
    j = (chosen // nx) % ny
    k = chosen // (nx * ny)
    local = np.stack([i * image.spacing[0], j * image.spacing[1], k * image.spacing[2]], axis=1).astype(np.float64)
    n = len(chosen)
    verts = CellArray(np.arange(n + 1, dtype=np.int64), np.arange(n, dtype=np.int64))
    spacing = min(d * s for d, s in zip(image.spacing, steps))
    poly = _new_poly(image, _to_physical(image, local), verts=verts,
                     attrs={"sample_spacing": float(spacing), "stride": list(steps), "sampling": sampling,
                            "vectors": source.name})
    _add(poly, source, np.ascontiguousarray(source.values.reshape(-1, 3)[chosen]), association="point",
         tensor="vector" if source.tensor in ("vector", "array") else source.tensor)
    poly.add_field("magnitude", np.ascontiguousarray(magnitude[picked]), unit=source.unit,
                   **({"quantity": source.quantity} if source.quantity else {}))
    for name in attributes or ():
        extra = select_field(image, name, associations=("point",))
        if extra.name in (source.name, "magnitude"):
            continue
        _add(poly, extra, np.ascontiguousarray(extra.values.reshape(-1, extra.components)[chosen]),
             association="point")
    return poly, steps


def _smooth(poly, smoothing, iterations, factor):
    import vtk
    if smoothing == "none" or iterations == 0 or poly.GetNumberOfPoints() == 0:
        return poly
    if smoothing == "windowed_sinc":
        smoother = vtk.vtkWindowedSincPolyDataFilter()
        smoother.SetPassBand(float(factor))
        smoother.NormalizeCoordinatesOn()
    elif smoothing == "laplacian":
        smoother = vtk.vtkSmoothPolyDataFilter()
        smoother.SetRelaxationFactor(float(factor))
    else:
        raise FilterError(f"Unknown smoothing {smoothing!r}; known: {', '.join(SMOOTHING)}")
    smoother.SetNumberOfIterations(int(iterations))
    smoother.BoundarySmoothingOff()
    smoother.FeatureEdgeSmoothingOff()
    smoother.SetInputData(poly)
    smoother.Update()
    return smoother.GetOutput()


def _clamp_points(poly, bounds):
    """``poly`` with its points clamped into ``bounds`` (``[(lo, hi)]`` per x, y, z; ``None`` = unclamped)."""
    import vtk
    np = _np()
    from vtkmodules.util import numpy_support
    points = _vtk_points(poly)
    lo = np.array([b[0] if b is not None else -np.inf for b in bounds])
    hi = np.array([b[1] if b is not None else np.inf for b in bounds])
    clamped = np.clip(points, lo, hi)
    if np.array_equal(clamped, points):
        return poly
    result = vtk.vtkPolyData()
    result.ShallowCopy(poly)
    vtk_points = vtk.vtkPoints()
    vtk_points.SetData(numpy_support.numpy_to_vtk(np.ascontiguousarray(clamped), deep=True))
    result.SetPoints(vtk_points)
    return result


def _label_surface(values, value, spacing, close, smoothing, iterations, factor, normals, bounds=None):
    """``(local points, triangles, normals | None)`` of one label (points relative to the field grid origin).

    ``bounds`` (``[(lo, hi) | None]`` per x, y, z in the same local coordinates) clamps the smoothed
    surface into the grid: the closing faces that the padding puts half a cell outside (and smoothing may
    push further) are projected onto the bounding box, so the surface stays closed and never overhangs.
    """
    import vtk
    np = _np()
    from vtkmodules.util import numpy_support
    mask = values == value
    ranges = []
    for axis in range(3):  # (z, y, x) axes of the array
        others = tuple(a for a in range(3) if a != axis)
        present = np.flatnonzero(mask.any(axis=others))
        if not len(present):
            return None
        ranges.append((int(present[0]), int(present[-1])))
    if close:
        sub = np.pad(mask[tuple(slice(lo, hi + 1) for lo, hi in ranges)], 1).astype(np.float32)
        start = [lo - 1 for lo, _ in ranges]
    else:
        ranges = [(max(lo - 1, 0), min(hi + 1, n - 1)) for (lo, hi), n in zip(ranges, mask.shape)]
        sub = mask[tuple(slice(lo, hi + 1) for lo, hi in ranges)].astype(np.float32)
        start = [lo for lo, _ in ranges]
    if min(sub.shape) < 2:
        return None
    nz, ny, nx = sub.shape
    origin = [start[2] * spacing[0], start[1] * spacing[1], start[0] * spacing[2]]
    data = _vtk_image((nx, ny, nz), spacing, {"_i": sub.reshape(-1)}, origin=origin, scalars="_i")
    surface = vtk.vtkFlyingEdges3D()
    surface.SetInputData(data)
    surface.SetValue(0, 0.5)
    surface.ComputeNormalsOff()
    surface.ComputeGradientsOff()
    surface.ComputeScalarsOff()
    surface.Update()
    poly = _smooth(surface.GetOutput(), smoothing, iterations, factor)
    if poly.GetNumberOfPoints() == 0:
        return None
    if bounds is not None:
        poly = _clamp_points(poly, bounds)  # before the normals, which follow the clamped faces
    normal_values = None
    if normals:
        filter_ = vtk.vtkPolyDataNormals()
        filter_.SetInputData(poly)
        filter_.ConsistencyOn()
        filter_.SplittingOff()
        filter_.AutoOrientNormalsOff()
        filter_.ComputePointNormalsOn()
        filter_.ComputeCellNormalsOff()
        filter_.Update()
        poly = filter_.GetOutput()
        normal_values = np.array(numpy_support.vtk_to_numpy(poly.GetPointData().GetNormals()), dtype=np.float32)
    points = _vtk_points(poly)
    triangles = np.array(numpy_support.vtk_to_numpy(poly.GetPolys().GetConnectivityArray()),
                         dtype=np.int64).reshape(-1, 3)
    return points, triangles, normal_values


def label_surfaces(image, field=None, labels="present", exclude=(-1, 0), *, smoothing="windowed_sinc",
                   smooth_iterations=30, smooth_factor=0.1, compute_normals=True, close_boundaries=True,
                   check=None, threads=None, warn=_ignore):
    """``stk.filter.label_surfaces@1`` (domain-classifiers.md §7): one surface per label.

    For each label v (``"present"`` = values in the field minus ``exclude``, or an
    explicit list): indicator (label == v) -> padded with 0 on every side when
    ``close_boundaries`` (closed surfaces) -> contour at 0.5 (``vtkFlyingEdges3D``)
    -> smoothing (windowed sinc: ``smooth_iterations``, pass band ``smooth_factor``,
    boundary/feature-edge smoothing off, normalized coordinates; or Laplacian with
    relaxation ``smooth_factor``; or none) -> point normals (consistent, no
    splitting). Vertices are clamped into the dataset's bounds before the normals are
    computed, so the closing faces lie on the grid's bounding box instead of half a
    cell (or, after smoothing, more) outside it; surfaces stay closed. Each label is
    processed inside its bounding box (the result is the same as on the whole grid),
    up to ``threads`` labels at a time (VTK releases the GIL). The surfaces are
    appended in label order; cell field ``label`` (int32) carries the input field's
    categories and palette. Label fields may be point or
    cell fields (cell fields are sampled at the cell centres).
    """
    np = _np()
    from .model import CellArray
    if field is None:
        found = [f for f in image.fields.values() if f.is_label and f.values is not None]
        if not found:
            raise FilterError("The input has no label field", code="kind_mismatch",
                              hint="classify first (stk.analysis.orientation_classify) or threshold")
        source = found[0]
    else:
        source = select_field(image, field)
        if not source.is_label:
            raise FilterError(f"Field {source.name!r} is not a label field", code="kind_mismatch")
    if smoothing not in SMOOTHING:
        raise FilterError(f"Unknown smoothing {smoothing!r}; known: {', '.join(SMOOTHING)}")
    values = source.values[..., 0]
    if labels == "present":
        from suan.analysis.labels import label_counts
        wanted = [v for v in sorted(label_counts(values)) if v not in set(int(e) for e in exclude)]
    else:
        wanted = sorted({int(v) for v in labels})
    dims, offset = _grid(image, source.association)
    spacing = image.spacing
    # The dataset's bounds in the local coordinates of the label samples (cell centres are offset by half a
    # cell): surfaces never leave the grid. Axes of one sample keep their half-cell slab (no flat surfaces).
    bounds = [(-offset[axis], (image.dimensions[axis] - 1) * spacing[axis] - offset[axis])
              if image.dimensions[axis] > 1 else None for axis in range(3)]
    pieces = {}
    workers = max(1, min(int(threads) if threads is not None else min(16, os.cpu_count() or 1), len(wanted) or 1))
    args = (spacing, bool(close_boundaries), smoothing, int(smooth_iterations), float(smooth_factor),
            bool(compute_normals), bounds)
    if workers == 1:
        for value in wanted:
            if check is not None:
                check()
            pieces[value] = _label_surface(values, value, *args)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(workers, thread_name_prefix="stk-label-surfaces") as pool:
            pending = {}
            try:
                for value in wanted:
                    if check is not None:
                        check()
                    pending[value] = pool.submit(_label_surface, values, value, *args)
                for value, future in pending.items():
                    if check is not None:
                        check()
                    pieces[value] = future.result()
            except BaseException:
                for future in pending.values():
                    future.cancel()
                raise
    points, triangles, normals, cell_labels, done = [], [], [], [], []
    count = 0
    for value in wanted:
        piece = pieces.get(value)
        if piece is None:
            continue
        p, t, n = piece
        points.append(p)
        triangles.append(t + count)
        if n is not None:
            normals.append(n)
        cell_labels.append(np.full(len(t), value, dtype=np.int32))
        count += len(p)
        done.append(value)
    if not done:
        warn("No label surfaces (no labels left after 'exclude')" if not wanted else
             "The requested labels are not present", code="empty_result")
    local = np.concatenate(points) if points else np.zeros((0, 3))
    tris = np.concatenate(triangles) if triangles else np.zeros((0, 3), dtype=np.int64)
    poly = _new_poly(image, _to_physical(image, local, offset), polys=CellArray.uniform(tris) if len(tris) else
                     CellArray.empty(),
                     attrs={"label_surfaces": {"field": source.name, "labels": done, "smoothing": smoothing,
                                               "smooth_iterations": int(smooth_iterations),
                                               "smooth_factor": float(smooth_factor),
                                               "close_boundaries": bool(close_boundaries)}})
    if compute_normals:
        normal_values = np.concatenate(normals) if normals else np.zeros((0, 3), dtype=np.float32)
        poly.add_field("Normals", np.ascontiguousarray(_rotate(image, normal_values)), tensor="vector", unit="1",
                       component_names=("x", "y", "z"))
    label_values = np.concatenate(cell_labels) if cell_labels else np.zeros(0, dtype=np.int32)
    poly.add_field("label", label_values, association="cell", tensor="label", categories=source.categories,
                   palette=source.palette, unit=source.unit if source.unit != "unspecified" else "1",
                   **({"quantity": source.quantity} if source.quantity else {}))
    return poly


def streamlines(image, field=None, *, seed_center=None, seed_radius=None, seed_count=100, direction="forward",
                max_length=None, seed=0, warn=_ignore):
    """``stk.filter.streamlines@1`` (stretch): ``vtkStreamTracer`` (Runge-Kutta 4) from seeds drawn
    uniformly in a sphere with ``numpy.random.default_rng(seed)`` (SimViz's point-source seeds).

    ``seed_center`` ``None`` = the bounds centre; ``seed_radius`` ``None`` = 10 % of the
    bounds diagonal; ``max_length`` ``None`` = twice the diagonal. Output polylines
    with point fields: the vector field (interpolated), ``magnitude`` and
    ``integration_time``.
    """
    import vtk
    np = _np()
    source = select_field(image, field, associations=("point",), labels=False, min_components=3,
                          what="vector field")
    if source.components != 3:
        raise FilterError(f"Streamlines need a 3-component vector field; {source.name!r} has {source.components}")
    if direction not in ("forward", "backward", "both"):
        raise FilterError(f"Unknown direction {direction!r}")
    lo, hi = image.bounds()
    diagonal = math.dist(lo, hi) or 1.0
    center = [(a + b) / 2 for a, b in zip(lo, hi)] if seed_center is None else [float(v) for v in seed_center]
    radius = 0.1 * diagonal if seed_radius is None else float(seed_radius)
    rng = np.random.default_rng(int(seed))
    directions = rng.normal(size=(int(seed_count), 3))
    directions /= np.maximum(np.linalg.norm(directions, axis=1), 1e-300)[:, None]
    seeds = np.asarray(center) + directions * (radius * rng.random(int(seed_count)) ** (1 / 3))[:, None]
    local_seeds = _to_local(image, seeds)
    vectors = source.values.reshape(-1, 3)
    if vectors.dtype.kind != "f":
        vectors = vectors.astype(np.float64)
    if not image.is_axis_aligned:  # vector components are physical; VTK integrates along the grid axes
        vectors = np.ascontiguousarray(np.linalg.solve(_direction(image), vectors.T.astype(np.float64)).T)
    data = _vtk_image(image.dimensions, image.spacing, {"_v": vectors}, vectors="_v")
    from .vtkconv import vtk_array
    seed_points = vtk.vtkPoints()
    seed_points.SetData(vtk_array(np.ascontiguousarray(local_seeds), "points"))
    seed_poly = vtk.vtkPolyData()
    seed_poly.SetPoints(seed_points)
    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(data)
    tracer.SetSourceData(seed_poly)
    tracer.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, "_v")
    tracer.SetIntegratorTypeToRungeKutta4()
    {"forward": tracer.SetIntegrationDirectionToForward, "backward": tracer.SetIntegrationDirectionToBackward,
     "both": tracer.SetIntegrationDirectionToBoth}[direction]()
    tracer.SetMaximumPropagation(float(max_length) if max_length is not None else 2 * diagonal)
    tracer.SetIntegrationStepUnit(vtk.vtkStreamTracer.CELL_LENGTH_UNIT)
    tracer.SetInitialIntegrationStep(0.2)
    tracer.SetMaximumNumberOfSteps(100000)
    tracer.SetTerminalSpeed(1e-12)
    tracer.SetComputeVorticity(False)
    tracer.Update()
    out = tracer.GetOutput()
    local = _vtk_points(out)
    poly = _new_poly(image, _to_physical(image, local), lines=_vtk_cells(out.GetLines()),
                     attrs={"streamlines": {"field": source.name, "seed_center": center, "seed_radius": radius,
                                            "seed_count": int(seed_count), "direction": direction}})
    if not len(local):
        warn("No streamlines (the seeds are outside the grid or the field is zero)", code="empty_result")
    traced = _vtk_point_array(out, "_v")
    traced = np.zeros((len(local), 3)) if traced is None else np.asarray(traced, dtype=np.float64).reshape(-1, 3)
    traced = _rotate(image, traced)
    _add(poly, source, np.ascontiguousarray(traced), association="point",
         tensor="vector" if source.tensor in ("vector", "array") else source.tensor)
    poly.add_field("magnitude", np.linalg.norm(traced, axis=1) if len(traced) else np.zeros(0), unit=source.unit)
    times = _vtk_point_array(out, "IntegrationTime")
    if times is not None:
        poly.add_field("integration_time", np.asarray(times, dtype=np.float64).reshape(-1), unit="unspecified")
    return poly
