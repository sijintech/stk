"""Built-in connector ``stk.numpy``: NumPy ``.npy`` fields ``(x, y, z[, c])`` and MuPRO field DATs.

Each file is one ``image`` dataset in ``grid_index`` units with one point
field named after the file stem; ``describe`` reads only the NPY header or
the DAT header line and first row.
"""
from pathlib import PurePosixPath

from ..api import ConnectorError
from . import SingleFileConnector, dataset_id

__all__ = ["NumpyConnector"]

IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]


def _npy_header(stream):
    import numpy as np
    version = np.lib.format.read_magic(stream)
    reader = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
    shape, _, dtype = reader(stream)
    return tuple(shape), np.dtype(dtype)


def _image_descriptor(name, dims, components, dtype):
    tensor = "scalar" if components == 1 else "array"
    return {"schema": "stk.dataset/1", "id": name, "kind": "image",
            "geometry": {"frame": "grid", "length_unit": "grid_index", "dimensions": list(dims),
                         "origin": [0.0, 0.0, 0.0], "spacing": [1.0, 1.0, 1.0], "direction": list(IDENTITY)},
            "fields": [{"name": name, "association": "point", "dtype": dtype, "components": components,
                        "tensor": tensor, "unit": "unspecified"}]}


class NumpyConnector(SingleFileConnector):
    """``.npy`` and ``.dat`` field files as image datasets."""

    id = "stk.numpy"
    formats = ("npy", "dat")

    def describe_file(self, run, item):
        name = dataset_id(item.path)
        suffix = PurePosixPath(item.path).suffix.lower()
        with run.open(item.path) as stream:
            if suffix == ".npy":
                try:
                    shape, dtype = _npy_header(stream)
                except ValueError as exc:
                    raise ConnectorError(f"{item.path}: not an NPY file ({exc})", "invalid_data") from None
                if len(shape) not in (3, 4) or dtype.kind not in "fiu":
                    raise ConnectorError(f"{item.path}: NPY fields must be numeric (x, y, z[, c])", "invalid_data")
                return _image_descriptor(name, shape[:3], shape[3] if len(shape) == 4 else 1, dtype.name)
            from suan.data.dat import DatError, dat_info, frame_name
            try:
                info = dat_info(stream)
            except (DatError, UnicodeDecodeError) as exc:
                raise ConnectorError(f"{item.path}: {exc}", "invalid_data") from None
            stem, _ = frame_name(item.path)
            return _image_descriptor(stem or name, info["dimensions"], info["components"] or 1, "float64")
