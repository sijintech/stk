"""Generate scalar and area-weighted normal references without VTK.

    PYTHONPATH=. python desktop/tests/unit/fixtures/make_viewer_helpers.py

Scalars use suan.render.layers.Attribute.scalar; payload encoding uses the real
Python builder. Normals use independent vectorized NumPy cross/scatter/sums.
These area-weighted normals deliberately do not model vtkPolyDataNormals' equal
face weighting or ConsistencyOn winding changes in the Python offscreen renderer.
"""
from pathlib import Path
import base64
import json
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))

from suan.render.layers import Attribute  # noqa: E402
from suan.render.payload import PayloadBuilder  # noqa: E402


def numbers(values):
    return [float(v) if np.isfinite(v) else "nan" if np.isnan(v) else "inf" if v > 0 else "-inf"
            for v in np.asarray(values).ravel()]


def scalar_case(name, raw, *, component=None, normalized=False, categorical=False,
                palette=False, hints=False, spec_range=None, attr_range=None):
    builder = PayloadBuilder()
    builder.add_accessor("positions", np.zeros((len(raw), 3), dtype=np.float32))
    builder.add_accessor("values", raw, normalized=normalized, hints=hints)
    attribute = {"accessor": "values", "association": "point", "categorical": categorical}
    spec = {"by": "attribute", "attribute": "value", "component": component}
    if palette:
        attribute["palette"] = builder.add_colormap({"id": "labels", "categorical": True,
                                                    "entries": [{"value": 1, "name": "one", "color": [1, 0, 0]}]})
    if spec_range is not None:
        spec["range"] = spec_range
    if attr_range is not None:
        attribute["range"] = attr_range
    builder.layers.append({"id": "points", "type": "points", "positions": "positions",
                           "attributes": {"value": attribute}, "appearance": {"color": spec}})
    payload = builder.build()
    is_label = categorical or palette
    values = raw
    if normalized and not is_label:
        info = np.iinfo(raw.dtype)
        values = np.maximum(-1, raw.astype(np.float64) / info.max).astype(np.float32)
    if is_label:
        selected = component if isinstance(component, int) else 0
        scalars = values if values.ndim == 1 else values[:, selected]
    else:
        scalars = Attribute(values).scalar(component)
    value_range = None
    if not is_label:
        value_range = spec_range if spec_range is not None else attr_range
        if value_range is None and hints and (raw.ndim == 1 or isinstance(component, int)):
            a = payload.manifest["accessors"][1]
            c = component or 0
            value_range = [a["min"][c], a["max"][c]]
        if value_range is None:
            finite = scalars[np.isfinite(scalars)]
            value_range = [float(finite.min()), float(finite.max())] if len(finite) else [0, 1]
    return {"name": name, "stkp": base64.b64encode(payload.to_stkp()).decode("ascii"),
            "values": numbers(scalars), "range": value_range, "categorical": is_label,
            "colormap": "labels" if palette else None}


def normal_case(name, positions, indices):
    positions = np.asarray(positions, dtype=np.float32).reshape(-1, 3)
    triangles = np.asarray(indices, dtype=np.uint32).reshape(-1, 3)
    vertices = positions.astype(np.float64)[triangles]
    face = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
    summed = np.zeros_like(positions, dtype=np.float64)
    np.add.at(summed, triangles.reshape(-1), np.repeat(face, 3, axis=0))
    lengths = np.linalg.norm(summed, axis=1)
    normals = summed / np.where(lengths > 0, lengths, 1)[:, None]
    return {"name": name, "positions": numbers(positions), "indices": triangles.ravel().tolist(),
            "normals": numbers(normals.astype(np.float32))}


def main():
    vectors = np.array([[3, -4, 0], [-6, 0, 8], [0, 0, 0]], dtype=np.float64)
    scalar_cases = [
        scalar_case("scalar preserves f64", np.array([1 + 2**-40, -2, 9], dtype=np.float64)),
        scalar_case("default vector magnitude ignores hints", vectors, hints=True),
        scalar_case("explicit vector magnitude", vectors, component="magnitude"),
        scalar_case("selected component hints", vectors, component=1, hints=True),
        scalar_case("attribute range wins over hints", vectors, component=0, hints=True, attr_range=[-8, 8]),
        scalar_case("spec range wins over attribute", vectors, component=0, hints=True,
                    attr_range=[-8, 8], spec_range=[-12, 12]),
        scalar_case("nonfinite scalar values", np.array([np.nan, np.inf, -np.inf, 2, -3], dtype=np.float32)),
        scalar_case("all nonfinite scalar values", np.array([np.nan, np.inf, -np.inf], dtype=np.float32)),
        scalar_case("empty scalars", np.array([], dtype=np.float64)),
        scalar_case("normalized signed bytes", np.array([-128, -127, 0, 127], dtype=np.int8), normalized=True),
        scalar_case("normalized unsigned shorts", np.array([1, 32768, 65535], dtype=np.uint16), normalized=True),
        scalar_case("normalized accessor hints retain stored domain", np.array([1, 128, 255], dtype=np.uint8),
                    normalized=True, hints=True),
        scalar_case("labels stay raw when normalized", np.array([1, 128, 255], dtype=np.uint8),
                    normalized=True, categorical=True),
        scalar_case("categorical vector default is first component", vectors, categorical=True),
        scalar_case("categorical selected component", vectors, categorical=True, component=1),
        scalar_case("palette implies categorical", np.array([1, 2], dtype=np.uint8), palette=True),
    ]
    rng = np.random.default_rng(726)
    normal_cases = [
        normal_case("unequal face areas and isolated point", [[0, 0, 0], [2, 0, 0], [0, 2, 0],
                                                             [0, 0, 1], [9, 9, 9]], [[0, 1, 2], [0, 3, 1]]),
        normal_case("opposite winding cancels", [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2], [0, 2, 1]]),
        normal_case("degenerate triangle", [[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 1, 2]]),
        normal_case("random shared vertices", rng.normal(size=(25, 3)), rng.integers(0, 25, size=(50, 3))),
    ]
    out = HERE / "viewer_helpers.json"
    out.write_text(json.dumps({"scalars": scalar_cases, "normals": normal_cases}, separators=(",", ":")) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {out.name}: {len(scalar_cases)} scalar and {len(normal_cases)} normal cases")


if __name__ == "__main__":
    main()
