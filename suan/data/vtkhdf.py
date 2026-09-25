"""VTKHDF files with the STK profile (docs/specs/stk-data-format-v1.md §10), read and written with h5py.

``write_vtkhdf`` stores :class:`~suan.data.model.ImageData`, ``PolyData`` and
``Table`` in the VTKHDF 2 layout that ``vtkHDFReader`` and ParaView read, plus
the STK profile VTK ignores: per-array attributes ``stk_unit``,
``stk_quantity``, ``stk_tensor``, ``stk_component_names``, ``stk_categories``,
``stk_lossy`` and a root group ``/STK`` whose ``descriptor`` attribute is the
stk.dataset/1 JSON (``profile`` = 1). Image arrays keep the in-memory
``(nz, ny, nx[, nc])`` layout (no transform), in 64^3 chunks with shuffle +
gzip 4; array groups keep the field order. Tables also get ``NumberOfRows`` (required by ``vtkHDFReader`` in VTK
9.7, which does not read string columns). One file per frame; files are
written to a temporary name and renamed.

``read_vtkhdf`` restores the dataset with its metadata (from ``/STK`` when
present, else from the array attributes, else ``unspecified`` units) and can
read a region/stride of an image's point fields without loading the rest.
"""
import json
import os
from pathlib import Path
import re
import uuid

__all__ = ["PROFILE", "VERSION", "is_vtkhdf", "read_descriptor", "read_vtkhdf", "write_vtkhdf"]

VERSION = (2, 0)
PROFILE = 1
CHUNK = 64
_TYPES = {"image": "ImageData", "polydata": "PolyData", "table": "Table"}
_CELL_GROUPS = (("verts", "Vertices"), ("lines", "Lines"), ("polys", "Polygons"))
_ARRAY_META = ("unit", "quantity", "tensor", "component_names", "categories", "lossy")


def _np():
    import numpy
    return numpy


def _h5py():
    try:
        import h5py
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on the installation
        raise ModuleNotFoundError("VTKHDF needs h5py: install suan_toolkits[visualization] or [science]") from exc
    return h5py


def is_vtkhdf(path):
    """True if ``path`` is an HDF5 file with a ``/VTKHDF`` group."""
    try:
        with open(path, "rb") as stream:
            if stream.read(8) != b"\x89HDF\r\n\x1a\n":
                return False
        with _h5py().File(path, "r") as handle:
            return "VTKHDF" in handle
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Writing


def _dataset(group, name, values, *, compression, level):
    np = _np()
    h5py = _h5py()
    values = np.asarray(values)
    options = {}
    if values.dtype.kind in "UO":
        values = np.array([str(v) for v in values.reshape(-1)], dtype=object).reshape(values.shape)
        return group.create_dataset(name, data=values, dtype=h5py.string_dtype("utf-8"))
    if compression and values.size and values.ndim:
        if values.ndim >= 3:
            spatial = values.shape[:3]
            options["chunks"] = tuple(min(CHUNK, n) for n in spatial) + tuple(values.shape[3:])
        else:
            options["chunks"] = True
        options.update(compression=compression, shuffle=True)
        if compression == "gzip":
            options["compression_opts"] = level
    return group.create_dataset(name, data=values, **options)


def _array_attrs(target, field):
    target.attrs["stk_unit"] = field.unit
    target.attrs["stk_tensor"] = field.tensor
    if field.quantity is not None:
        target.attrs["stk_quantity"] = field.quantity
    if field.component_names is not None:
        target.attrs["stk_component_names"] = json.dumps(list(field.component_names))
    if field.categories:
        target.attrs["stk_categories"] = json.dumps([c.to_json() for c in field.categories])
    if field.lossy:
        target.attrs["stk_lossy"] = True


def _stored(field):
    """Array as stored: a point/cell field with one component drops its component axis (VTKHDF convention)."""
    values = field.values
    if field.association in ("point", "cell") and field.components == 1 and values.ndim > 1:
        return values.reshape(values.shape[:-1])
    return values


def _write_fields(root, dataset, groups, *, compression, level):
    for field in dataset.fields.values():
        if field.values is None:
            raise ValueError(f"Field {field.name!r} has no values")
        group_name = groups.get(field.association)
        if group_name is None:
            raise ValueError(f"Field {field.name!r}: association {field.association!r} cannot be stored in "
                             f"a {dataset.kind} VTKHDF file")
        group = root[group_name] if group_name in root else root.create_group(group_name, track_order=True)
        written = _dataset(group, field.name, _stored(field), compression=compression, level=level)
        _array_attrs(written, field)


def write_vtkhdf(path, dataset, *, compression="gzip", level=4):
    """Write an in-memory dataset (image, polydata or table) as a VTKHDF file with the STK profile."""
    np = _np()
    h5py = _h5py()
    kind = dataset.kind
    if kind not in _TYPES:
        raise ValueError(f"VTKHDF writing supports {', '.join(_TYPES)} datasets, not {kind!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with h5py.File(temporary, "w") as handle:
            root = handle.create_group("VTKHDF")
            root.attrs["Version"] = np.array(VERSION, dtype=np.int64)
            root.attrs.create("Type", np.bytes_(_TYPES[kind]))
            if kind == "image":
                nx, ny, nz = dataset.dimensions
                root.attrs["WholeExtent"] = np.array([0, nx - 1, 0, ny - 1, 0, nz - 1], dtype=np.int64)
                root.attrs["Origin"] = np.array(dataset.origin, dtype=np.float64)
                root.attrs["Spacing"] = np.array(dataset.spacing, dtype=np.float64)
                root.attrs["Direction"] = np.array(dataset.direction, dtype=np.float64)
                groups = {"point": "PointData", "cell": "CellData", "field": "FieldData"}
            elif kind == "polydata":
                points = dataset.points if dataset.points is not None else np.zeros((0, 3))
                root.create_dataset("NumberOfPoints", data=np.array([len(points)], dtype=np.int64))
                _dataset(root, "Points", points, compression=compression, level=level)
                for attribute, name in _CELL_GROUPS + ((None, "Strips"),):
                    cells = getattr(dataset, attribute) if attribute else None
                    offsets = np.asarray(cells.offsets if cells is not None else [0], dtype=np.int64)
                    connectivity = np.asarray(cells.connectivity if cells is not None else [], dtype=np.int64)
                    group = root.create_group(name)
                    group.create_dataset("NumberOfCells", data=np.array([len(offsets) - 1], dtype=np.int64))
                    group.create_dataset("NumberOfConnectivityIds", data=np.array([len(connectivity)], dtype=np.int64))
                    _dataset(group, "Offsets", offsets, compression=compression, level=level)
                    _dataset(group, "Connectivity", connectivity, compression=compression, level=level)
                groups = {"point": "PointData", "cell": "CellData", "field": "FieldData"}
            else:
                root.create_dataset("NumberOfRows", data=np.array([dataset.n_rows], dtype=np.int64))
                root.create_group("RowData", track_order=True)
                groups = {"row": "RowData"}
            _write_fields(root, dataset, groups, compression=compression, level=level)
            stk = handle.create_group("STK")
            stk.attrs["descriptor"] = json.dumps(dataset.descriptor(), ensure_ascii=False, allow_nan=False)
            stk.attrs["profile"] = np.int64(PROFILE)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


# ---------------------------------------------------------------------------
# Reading


def _text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "tolist"):
        value = value.tolist()
        if isinstance(value, bytes):
            return value.decode("utf-8")
    return str(value)


def read_descriptor(path):
    """The ``/STK`` stk.dataset/1 descriptor, or ``None`` for plain VTKHDF files."""
    with _h5py().File(path, "r") as handle:
        return _descriptor(handle)


def _descriptor(handle):
    if "STK" in handle and "descriptor" in handle["STK"].attrs:
        return json.loads(_text(handle["STK"].attrs["descriptor"]))
    return None


def _field_name(name):
    return name if re.match(r"^[^/.]{1,128}$", name) else re.sub(r"[/.]", "_", name)[:128] or "field"


def _metadata(name, dataset, entries):
    """Descriptor entry of an array, else the per-array STK attributes."""
    entry = dict(entries.get(name) or {})
    attrs = dataset.attrs
    if not entry:
        for key in _ARRAY_META:
            if f"stk_{key}" in attrs:
                value = attrs[f"stk_{key}"]
                if key in ("component_names", "categories"):
                    value = json.loads(_text(value))
                elif key == "lossy":
                    value = bool(value)
                else:
                    value = _text(value)
                entry[key] = value
    return entry


def _make_field(name, values, association, entry):
    from .model import Field
    np = _np()
    components = values.shape[-1] if values.ndim else 1
    meta = {key: entry[key] for key in ("unit", "quantity", "component_names", "categories", "palette", "normalization",
                                        "role", "description", "lossy", "range", "magnitude_range") if key in entry}
    tensor = entry.get("tensor")
    if tensor is None or (tensor == "label" and values.dtype.kind not in "iu"):
        tensor = "label" if meta.get("categories") and values.dtype.kind in "iu" else \
            ("scalar" if components == 1 else "array")
    field = Field(name, association=association, dtype=Field.dtype_name(values), components=components,
                  tensor=tensor, values=values, **meta)
    try:
        field.validate()
    except ValueError:  # a foreign or inconsistent descriptor: keep the values, drop the structure claims
        meta.pop("component_names", None)
        field = Field(name, association=association, dtype=Field.dtype_name(values), components=components,
                      tensor="scalar" if components == 1 else "array", values=np.ascontiguousarray(values),
                      **{k: v for k, v in meta.items() if k != "categories"})
    return field


def _read_array(dataset, selection=None):
    np = _np()
    if dataset.dtype.kind == "O" or _h5py().check_string_dtype(dataset.dtype) is not None:
        return np.array(dataset.asstr()[()], dtype=str)
    return np.ascontiguousarray(dataset[selection] if selection is not None else dataset[()])


def _common(descriptor):
    from .model import FrameRef, Provenance, TimeInfo
    if not descriptor:
        return {}
    result = {"label": descriptor.get("label"), "attrs": descriptor.get("attrs")}
    if descriptor.get("time"):
        result["time"] = TimeInfo.from_json(descriptor["time"])
    if descriptor.get("frames"):
        result["frames"] = [FrameRef.from_json(f) for f in descriptor["frames"]]
    if descriptor.get("provenance"):
        result["provenance"] = Provenance.from_json(descriptor["provenance"])
    return result


def _normalize_window(region, stride, dims):
    """Inclusive ``((i0, i1), (j0, j1), (k0, k1))`` clipped to the grid, plus the stride."""
    if region is None:
        region = [(0, n - 1) for n in dims]
    window = []
    for (lo, hi), n in zip(region, dims):
        lo = 0 if lo is None else max(0, int(lo))
        hi = n - 1 if hi is None else min(n - 1, int(hi))
        if lo > hi:
            raise ValueError(f"Empty region {region!r} for dimensions {tuple(dims)}")
        window.append((lo, hi))
    stride = tuple(int(s) for s in (stride or (1, 1, 1)))
    if len(stride) != 3 or min(stride) < 1:
        raise ValueError("stride must be three integers >= 1")
    return window, stride


def read_vtkhdf(path, *, fields=None, region=None, stride=None):
    """Read a VTKHDF file (image, polydata or table) as an in-memory STK dataset.

    ``fields`` limits the arrays read. For images, ``region`` (inclusive point
    index ranges ``((i0, i1), (j0, j1), (k0, k1))``, clipped) and ``stride``
    ``(sx, sy, sz)`` read only that part of the point fields; the result equals
    cropping then sampling the full image (origin at the first kept point,
    spacing times the stride). Cell fields cannot be read with a region.
    """
    from .model import CellArray, ImageData, PolyData, Table
    np = _np()
    with _h5py().File(path, "r") as handle:
        if "VTKHDF" not in handle:
            raise ValueError(f"{Path(path).name} is not a VTKHDF file (no /VTKHDF group)")
        root = handle["VTKHDF"]
        kind = _text(root.attrs["Type"])
        descriptor = _descriptor(handle) or {}
        entries = {f["name"]: f for f in descriptor.get("columns" if kind == "Table" else "fields", ())}
        geometry = descriptor.get("geometry") or {}
        common = _common(descriptor)
        wanted = None if fields is None else set(fields)
        base_id = descriptor.get("id") or re.sub(r"[^A-Za-z0-9_]", "_", Path(path).name.split(".")[0]) or "dataset"
        if kind == "ImageData":
            extent = [int(v) for v in root.attrs["WholeExtent"]]
            dims = [extent[1] - extent[0] + 1, extent[3] - extent[2] + 1, extent[5] - extent[4] + 1]
            spacing = [float(v) for v in root.attrs["Spacing"]]
            direction = [float(v) for v in root.attrs["Direction"]] if "Direction" in root.attrs \
                else [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0]
            origin = [float(v) for v in root.attrs["Origin"]]
            window, steps = _normalize_window(region, stride, dims)
            start = [extent[0] + window[0][0], extent[2] + window[1][0], extent[4] + window[2][0]]
            offset = [start[a] * spacing[a] for a in range(3)]
            origin = [origin[r] + sum(direction[3 * r + c] * offset[c] for c in range(3)) for r in range(3)]
            sub_dims = [len(range(lo, hi + 1, s)) for (lo, hi), s in zip(window, steps)]
            image = ImageData(tuple(sub_dims), origin, [spacing[a] * steps[a] for a in range(3)], direction,
                              frame=geometry.get("frame", "grid"), length_unit=geometry.get("length_unit",
                                                                                            "unspecified"),
                              id=base_id, **common)
            partial = region is not None or stride is not None
            selection = tuple(slice(lo, hi + 1, s) for (lo, hi), s in reversed(list(zip(window, steps))))
            for group_name, association in (("PointData", "point"), ("CellData", "cell"), ("FieldData", "field")):
                if group_name not in root:
                    continue
                for name, data in root[group_name].items():
                    if wanted is not None and name not in wanted:
                        continue
                    if association == "cell" and partial:
                        raise ValueError(f"Cell field {name!r} cannot be read with a region or stride")
                    values = _read_array(data, selection if association == "point" else None)
                    if values.ndim == 3 or (association == "field" and values.ndim == 1):
                        values = values[..., None]
                    image.add(_make_field(_field_name(name), np.ascontiguousarray(values), association,
                                          _metadata(name, data, entries)))
            return _in_order(image, entries)
        if kind == "PolyData":
            points = np.asarray(root["Points"][()], dtype=np.float64)
            cells = {}
            for attribute, name in _CELL_GROUPS:
                group = root[name]
                cells[attribute] = CellArray(np.asarray(group["Offsets"][()], dtype=np.int64),
                                             np.asarray(group["Connectivity"][()], dtype=np.int64))
            if "Strips" in root and int(root["Strips"]["NumberOfCells"][()][0]):
                raise ValueError("Triangle strips are not supported; triangulate them first")
            poly = PolyData(points, frame=geometry.get("frame", "grid"),
                            length_unit=geometry.get("length_unit", "unspecified"), id=base_id, **cells, **common)
            for group_name, association in (("PointData", "point"), ("CellData", "cell")):
                for name, data in (root[group_name].items() if group_name in root else ()):
                    if wanted is None or name in wanted:
                        values = _read_array(data)
                        values = values[:, None] if values.ndim == 1 else values
                        poly.add(_make_field(_field_name(name), values, association, _metadata(name, data, entries)))
            return _in_order(poly, entries)
        if kind == "Table":
            table = Table(id=base_id, index=next((e["name"] for e in entries.values() if e.get("role") == "index"),
                                                 None), **common)
            for name, data in (root["RowData"].items() if "RowData" in root else ()):
                if wanted is None or name in wanted:
                    values = _read_array(data)
                    table.add(_make_field(_field_name(name), values, "row", _metadata(name, data, entries))
                              if values.ndim == 2 else _column(name, values, _metadata(name, data, entries)))
            return _in_order(table, entries)
        raise ValueError(f"VTKHDF type {kind!r} is not supported by STK in Milestone 1")


def _in_order(dataset, entries):
    """Fields in the descriptor's order (arrays sit in separate point/cell groups in the file)."""
    rank = {name: i for i, name in enumerate(entries)}
    dataset.fields = dict(sorted(dataset.fields.items(), key=lambda item: rank.get(item[0], len(rank))))
    return dataset


def _column(name, values, entry):
    from .model import Field
    meta = {key: entry[key] for key in ("unit", "quantity", "categories", "palette", "role", "description", "lossy",
                                        "normalization") if key in entry}
    tensor = "label" if meta.get("categories") and values.dtype.kind in "iu" else "scalar"
    return Field(_field_name(name), association="row", dtype=Field.dtype_name(values), components=1, tensor=tensor,
                 values=values, **meta)
