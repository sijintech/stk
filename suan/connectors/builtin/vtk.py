"""Built-in connector ``stk.vtk``: VTK XML ``.vti``, legacy ``.vtk`` STRUCTURED_POINTS and VTKHDF files.

``describe`` reads headers only (the XML header of a VTI, the leading lines
of a legacy file, the attributes and ``/STK`` descriptor of a VTKHDF file).
Reading uses VTK's readers for VTI/VTK (all point and cell arrays, the
``STK_units``/``STK_coordinate_units``/``STK_timestep`` annotations of
``suan.visualization.scene``) and h5py for VTKHDF (no VTK needed).
"""
from pathlib import PurePosixPath
import re

from ..api import ConnectorError
from . import SingleFileConnector, dataset_id

__all__ = ["VTKConnector", "read_vtk_image"]

_VTK_TYPES = {"Float64": "float64", "Float32": "float32", "Int64": "int64", "Int32": "int32", "Int16": "int16",
              "Int8": "int8", "UInt64": "uint64", "UInt32": "uint32", "UInt16": "uint16", "UInt8": "uint8",
              "double": "float64", "float": "float32", "long": "int64", "int": "int32", "short": "int16",
              "char": "int8", "unsigned_long": "uint64", "unsigned_int": "uint32", "unsigned_short": "uint16",
              "unsigned_char": "uint8", "vtktypeint64": "int64", "vtkIdType": "int64"}
_HEAD_BYTES = 1 << 16


def read_vtk_image(path, kind, *, fields=None, id="image"):
    """Read a ``.vti`` or legacy ``.vtk`` STRUCTURED_POINTS file with VTK as ImageData."""
    import vtk
    from suan.data.vtkconv import vtk_to_image
    if kind == "vti":
        reader = vtk.vtkXMLImageDataReader()
    elif kind == "vtk":
        reader = vtk.vtkStructuredPointsReader()
    else:
        raise ConnectorError(f"read_vtk_image reads vti or vtk files, not {kind}", "unsupported")
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    if data is None or min(data.GetDimensions()) < 1 or data.GetNumberOfPoints() == 0:
        raise ConnectorError(f"{PurePosixPath(str(path)).name} is not a readable VTK image", "invalid_data")
    return vtk_to_image(data, fields=fields, id=id)


def _attribute(text, name):
    match = re.search(rf'\b{name}\s*=\s*"([^"]*)"', text)
    return match[1].split() if match else None


def _vti_descriptor(head, name):
    piece = re.search(r"<ImageData\b([^>]*)>", head)
    if piece is None:
        raise ConnectorError("Not a VTK XML ImageData file", "invalid_data")
    extent = [int(v) for v in (_attribute(piece[1], "WholeExtent") or [])]
    if len(extent) != 6:
        raise ConnectorError("VTI file without WholeExtent", "invalid_data")
    spacing = [float(v) for v in (_attribute(piece[1], "Spacing") or [1, 1, 1])]
    origin = [float(v) for v in (_attribute(piece[1], "Origin") or [0, 0, 0])]
    direction = [float(v) for v in (_attribute(piece[1], "Direction") or [1, 0, 0, 0, 1, 0, 0, 0, 1])]
    origin = [origin[r] + sum(direction[3 * r + c] * extent[2 * c] * spacing[c] for c in range(3)) for r in range(3)]
    dims = [extent[1] - extent[0] + 1, extent[3] - extent[2] + 1, extent[5] - extent[4] + 1]
    fields = []
    for association, tag in (("point", "PointData"), ("cell", "CellData")):
        block = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", head, re.S)
        for array in re.finditer(r"<DataArray\b([^>]*)>", block[1] if block else ""):
            attrs = array[1]
            array_name = (_attribute(attrs, "Name") or ["array"])[0]
            if array_name.startswith("STK_"):
                continue
            components = int((_attribute(attrs, "NumberOfComponents") or [1])[0])
            dtype = _VTK_TYPES.get((_attribute(attrs, "type") or ["Float64"])[0])
            if dtype is None:
                continue
            fields.append({"name": re.sub(r"[/.]", "_", array_name), "association": association, "dtype": dtype,
                           "components": components, "tensor": "scalar" if components == 1 else "array",
                           "unit": "unspecified"})
    return {"schema": "stk.dataset/1", "id": name, "kind": "image",
            "geometry": {"frame": "grid", "length_unit": "unspecified", "dimensions": dims, "origin": origin,
                         "spacing": spacing, "direction": direction}, "fields": fields}


def _legacy_descriptor(head, name):
    text = head.decode("latin-1")
    if "STRUCTURED_POINTS" not in text:
        raise ConnectorError("Legacy VTK files must be DATASET STRUCTURED_POINTS", "unsupported")
    tokens = text.split()

    def triple(key, default):
        if key not in tokens:
            return default
        i = tokens.index(key)
        return tokens[i + 1:i + 4]
    dims = [int(v) for v in triple("DIMENSIONS", [])]
    if len(dims) != 3:
        raise ConnectorError("Legacy VTK file without DIMENSIONS", "invalid_data")
    spacing = [float(v) for v in triple("SPACING", triple("ASPECT_RATIO", [1, 1, 1]))]
    origin = [float(v) for v in triple("ORIGIN", [0, 0, 0])]
    fields = []
    for match in re.finditer(r"^(SCALARS|VECTORS)\s+(\S+)\s+(\S+)(?:\s+(\d+))?", text, re.M):
        kind, array_name, vtk_type, count = match.groups()
        components = 3 if kind == "VECTORS" else int(count or 1)
        dtype = _VTK_TYPES.get(vtk_type)
        if dtype:
            fields.append({"name": re.sub(r"[/.]", "_", array_name), "association": "point", "dtype": dtype,
                           "components": components, "tensor": "scalar" if components == 1 else "array",
                           "unit": "unspecified"})
    return {"schema": "stk.dataset/1", "id": name, "kind": "image",
            "geometry": {"frame": "grid", "length_unit": "unspecified", "dimensions": dims, "origin": origin,
                         "spacing": spacing, "direction": [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0]}, "fields": fields}


def _vtkhdf_descriptor(source, path, name):
    from suan.data.vtkhdf import read_descriptor, read_vtkhdf
    from ..files import materialize
    local = materialize(source, path)
    descriptor = read_descriptor(local)
    if descriptor is None:
        dataset = read_vtkhdf(local)
        descriptor = dataset.descriptor()
    descriptor = dict(descriptor)
    descriptor["id"] = name
    descriptor.pop("frames", None)
    return descriptor


class VTKConnector(SingleFileConnector):
    """``.vti``, ``.vtk`` and ``.vtkhdf`` (``.hdf``/``.h5`` with a ``/VTKHDF`` group) files."""

    id = "stk.vtk"
    formats = ("vti", "vtk", "vtkhdf")
    reads = ("image", "polydata", "table")

    def describe_file(self, run, item):
        name = dataset_id(item.path)
        suffix = PurePosixPath(item.path).suffix.lower()
        if suffix in (".vtkhdf", ".hdf", ".h5", ".hdf5"):
            return _vtkhdf_descriptor(run, item.path, name)
        with run.open(item.path) as stream:
            head = stream.read(_HEAD_BYTES)
        if suffix == ".vti":
            return _vti_descriptor(head.decode("utf-8", "replace"), name)
        return _legacy_descriptor(head, name)

    def _files(self, run):
        from suan.data.vtkhdf import is_vtkhdf
        found = []
        for item in super()._files(run):
            if PurePosixPath(item.path).suffix.lower() in (".hdf", ".h5", ".hdf5"):
                # Generic HDF5 names are probed only when the file is already on this host: probing a remote
                # file would download it (e.g. a multi-GB MuPRO run.h5). Remote VTKHDF uses '.vtkhdf'.
                local = None if hasattr(run, "fetch") else run.local_path(item.path)
                if local is None or not is_vtkhdf(local):
                    continue  # plain HDF5 (e.g. MuPRO run.h5) is not a VTKHDF dataset
            found.append(item)
        return found
