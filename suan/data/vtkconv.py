"""Zero-copy conversion between STK datasets and VTK objects (``vtkImageData``, ``vtkPolyData``).

STK image arrays are C-contiguous ``(nz, ny, nx, nc)`` with x fastest, which is
VTK's point order, so ``image_to_vtk`` hands NumPy buffers to VTK without a
copy (the VTK arrays keep the NumPy arrays alive). ``vtk_to_image`` and
``vtk_to_polydata`` return NumPy views of VTK buffers unless ``copy=True``;
the dataset keeps a reference to the VTK arrays. Polydata cells use int64
offsets/connectivity on both sides; they are copied into VTK (a shallow
``vtkIdTypeArray`` in a ``vtkCellArray`` does not keep its NumPy buffer alive
on VTK 9.3) and viewed without a copy on the way back.
Triangle strips are not an STK cell type (triangulate first).

VTK is imported when a function is called.
"""
import re

__all__ = ["image_to_vtk", "polydata_to_vtk", "to_vtk", "vtk_array", "vtk_to_image", "vtk_to_polydata"]

_STK_DTYPES = ("float64", "float32", "int64", "int32", "int16", "int8", "uint64", "uint32", "uint16", "uint8")


def _np():
    import numpy
    return numpy


def _support():
    from vtkmodules.util import numpy_support
    return numpy_support


def vtk_array(values, name):
    """A named VTK data array sharing memory with ``values`` ((n,) or (n, nc), C-contiguous)."""
    np = _np()
    values = np.asarray(values)
    if values.dtype.kind == "b":
        values = values.astype(np.uint8)
    if not values.flags.c_contiguous:
        values = np.ascontiguousarray(values)
    array = _support().numpy_to_vtk(values, deep=False)
    array.SetName(name)
    return array


def _set_attributes(data, fields, association):
    attributes = data.GetPointData() if association == "point" else data.GetCellData()
    scalars = vectors = None
    for field in fields:
        values = field.values.reshape(-1, field.components) if field.components > 1 else field.values.reshape(-1)
        attributes.AddArray(vtk_array(values, field.name))
        if scalars is None and field.components == 1:
            scalars = field.name
        if vectors is None and field.components == 3 and field.tensor == "vector":
            vectors = field.name
    if scalars:
        attributes.SetActiveScalars(scalars)
    if vectors:
        attributes.SetActiveVectors(vectors)


def _selected(dataset, fields, associations):
    wanted = None if fields is None else set(fields)
    chosen = [f for f in dataset.fields.values()
              if (wanted is None or f.name in wanted) and f.association in associations and f.values is not None]
    for field in chosen:
        if field.dtype == "string":
            raise ValueError(f"Field {field.name!r}: string fields cannot be converted to VTK arrays")
    return chosen


def image_to_vtk(image, fields=None):
    """``vtkImageData`` over an :class:`~suan.data.model.ImageData` (point and cell fields, zero copy)."""
    import vtk
    data = vtk.vtkImageData()
    data.SetDimensions(*image.dimensions)
    data.SetOrigin(*image.origin)
    data.SetSpacing(*image.spacing)
    data.SetDirectionMatrix(*image.direction)
    chosen = _selected(image, fields, ("point", "cell"))
    _set_attributes(data, [f for f in chosen if f.association == "point"], "point")
    _set_attributes(data, [f for f in chosen if f.association == "cell"], "cell")
    return data


def _cells(cell_array):
    import vtk
    support = _support()
    np = _np()
    cells = vtk.vtkCellArray()
    offsets = np.ascontiguousarray(cell_array.offsets, dtype=np.int64)
    connectivity = np.ascontiguousarray(cell_array.connectivity, dtype=np.int64)
    # Deep copies: a shallow vtkIdTypeArray handed to vtkCellArray.SetData does not keep the NumPy
    # buffer alive on VTK 9.3 (use-after-free once the STK dataset is freed).
    if vtk.vtkIdTypeArray().GetDataTypeSize() == 8:
        cells.SetData(support.numpy_to_vtkIdTypeArray(offsets, deep=True),
                      support.numpy_to_vtkIdTypeArray(connectivity, deep=True))
    else:  # pragma: no cover - 32-bit vtkIdType builds
        cells.SetData(support.numpy_to_vtk(offsets, deep=True, array_type=vtk.VTK_ID_TYPE),
                      support.numpy_to_vtk(connectivity, deep=True, array_type=vtk.VTK_ID_TYPE))
    return cells


def polydata_to_vtk(poly, fields=None):
    """``vtkPolyData`` over a :class:`~suan.data.model.PolyData` (points, verts, lines, polys and fields)."""
    import vtk
    np = _np()
    data = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    coordinates = poly.points if poly.points is not None else np.zeros((0, 3))
    points.SetData(vtk_array(coordinates, "Points"))
    data.SetPoints(points)
    for name, setter in (("verts", data.SetVerts), ("lines", data.SetLines), ("polys", data.SetPolys)):
        cells = getattr(poly, name)
        if cells is not None and cells.n_cells:
            setter(_cells(cells))
    chosen = _selected(poly, fields, ("point", "cell"))
    _set_attributes(data, [f for f in chosen if f.association == "point"], "point")
    _set_attributes(data, [f for f in chosen if f.association == "cell"], "cell")
    return data


def to_vtk(dataset, fields=None):
    """``image_to_vtk`` or ``polydata_to_vtk`` by dataset kind."""
    if dataset.kind == "image":
        return image_to_vtk(dataset, fields)
    if dataset.kind == "polydata":
        return polydata_to_vtk(dataset, fields)
    raise ValueError(f"Cannot convert a {dataset.kind!r} dataset to a VTK data object")


def _name(raw, used):
    name = raw if raw and re.match(r"^[^/.]{1,128}$", raw) else re.sub(r"[/.]", "_", raw or "array")[:128] or "array"
    base, n = name, 2
    while name in used:
        name = f"{base[:120]}_{n}"
        n += 1
    used.add(name)
    return name


def _arrays(attributes, fields, copy, keep):
    """(name, values (n, nc)) of the numeric arrays of a vtkPointData/vtkCellData."""
    np = _np()
    support = _support()
    wanted = None if fields is None else set(fields)
    used = set()
    for index in range(attributes.GetNumberOfArrays()):
        array = attributes.GetArray(index)
        if array is None:  # string or other abstract arrays
            continue
        raw = array.GetName()
        if wanted is not None and raw not in wanted:
            continue
        values = support.vtk_to_numpy(array)
        if values.dtype.kind == "b":
            values = values.astype(np.uint8)
        if values.dtype.name not in _STK_DTYPES:
            values = values.astype(np.int64 if values.dtype.kind in "iu" else np.float64)
        values = values.reshape(len(values), -1) if values.ndim == 1 else values
        if copy:
            values = np.array(values, order="C")
        else:
            keep.append(array)
        yield _name(raw, used), np.ascontiguousarray(values)


def _annotation(field_data, name):
    array = field_data.GetAbstractArray(name)
    if array is None or array.GetNumberOfValues() != 1:
        return None
    return array.GetVariantValue(0).ToString()


def vtk_to_image(data, *, fields=None, copy=False, id="image", unit=None, length_unit=None, time=None, meta=None):
    """:class:`~suan.data.model.ImageData` from a ``vtkImageData`` (arrays are views unless ``copy``).

    A nonzero VTK extent moves the origin to the first stored point. The
    ``STK_units``, ``STK_coordinate_units`` and ``STK_timestep`` field-data
    annotations written by STK are honoured (``unit``/``length_unit``/``time``
    arguments win). ``meta`` maps field names to extra field metadata.
    """
    from .model import ImageData, TimeInfo
    dims = data.GetDimensions()
    extent = data.GetExtent()
    spacing = data.GetSpacing()
    matrix = data.GetDirectionMatrix()
    direction = [matrix.GetElement(r, c) for r in range(3) for c in range(3)]
    base = data.GetOrigin()
    offset = [extent[2 * a] * spacing[a] for a in range(3)]
    origin = [base[r] + sum(direction[3 * r + c] * offset[c] for c in range(3)) for r in range(3)]
    field_data = data.GetFieldData()
    unit = unit or _annotation(field_data, "STK_units") or "unspecified"
    coordinates = length_unit or _annotation(field_data, "STK_coordinate_units") or "unspecified"
    if coordinates == "grid index":
        coordinates = "grid_index"
    if time is None:
        step = field_data.GetArray("STK_timestep")
        if step is not None and step.GetNumberOfTuples() == 1:
            value = float(step.GetTuple1(0))
            if value >= 0 and value.is_integer():
                time = TimeInfo(step=int(value))
    image = ImageData(tuple(int(n) for n in dims), origin, spacing, direction, length_unit=coordinates, id=id,
                      time=time)
    keep = []
    nx, ny, nz = dims
    cx, cy, cz = image.cell_dimensions
    for attributes, association, shape in ((data.GetPointData(), "point", (nz, ny, nx)),
                                           (data.GetCellData(), "cell", (cz, cy, cx))):
        for name, values in _arrays(attributes, fields, copy, keep):
            extra = dict((meta or {}).get(name, {}))
            extra.setdefault("unit", unit)
            image.add_field(name, values.reshape(*shape, values.shape[1]), association=association, **extra)
    image._vtk_arrays = keep
    return image


def _cell_array(cells):
    from .model import CellArray
    np = _np()
    support = _support()
    offsets = support.vtk_to_numpy(cells.GetOffsetsArray())
    connectivity = support.vtk_to_numpy(cells.GetConnectivityArray())
    return CellArray(np.asarray(offsets, dtype=np.int64), np.asarray(connectivity, dtype=np.int64))


def vtk_to_polydata(data, *, fields=None, copy=False, id="polydata", length_unit="unspecified", meta=None):
    """:class:`~suan.data.model.PolyData` from a ``vtkPolyData`` (points become float64)."""
    from .model import PolyData
    np = _np()
    support = _support()
    if data.GetNumberOfStrips():
        raise ValueError("Triangle strips are not supported; run vtkTriangleFilter first")
    points = data.GetPoints()
    coordinates = support.vtk_to_numpy(points.GetData()) if points is not None else np.zeros((0, 3))
    cells = {name: getter() for name, getter in (("verts", data.GetVerts), ("lines", data.GetLines),
                                                  ("polys", data.GetPolys))}
    arrays = {name: _cell_array(cell) for name, cell in cells.items()}
    if copy:
        coordinates = np.array(coordinates, dtype=np.float64)
        arrays = {name: type(a)(a.offsets.copy(), a.connectivity.copy()) for name, a in arrays.items()}
    poly = PolyData(coordinates, length_unit=length_unit, id=id, **arrays)
    keep = [] if copy else [points.GetData() if points is not None else None, *cells.values()]
    for attributes, association in ((data.GetPointData(), "point"), (data.GetCellData(), "cell")):
        for name, values in _arrays(attributes, fields, copy, keep):
            poly.add_field(name, values, association=association, **dict((meta or {}).get(name, {})))
    poly._vtk_arrays = keep
    return poly
