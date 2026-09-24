"""In-memory data model v1: layouts, descriptors, labels and the scene.Grid adapter."""
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")

from suan.data.model import (Category, CellArray, Dataset, Field, FrameRef, ImageData, PolyData, Provenance,  # noqa: E402
                             SourceRef, Table, TimeInfo, dataset_from_descriptor, json_safe)

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = [Category(-1, "unclassified"), Category(0, "substrate"),
           Category(1, "T[100]", direction=(1, 0, 0), family="T", color=(1, 0, 0), aliases=("T1+(+,0,0)", "a1+"))]


def image():
    img = ImageData((4, 3, 2), origin=(1.0, -2.0, 1e6), spacing=(0.5, 1.0, 2.0), length_unit="nm", id="Polar",
                    time=TimeInfo(step=1000))
    x, y, z = np.meshgrid(np.arange(4), np.arange(3), np.arange(2), indexing="ij")
    img.add_field("Polar", np.stack([x, y, z], axis=3).astype(np.float64), layout="xyzc", tensor="vector",
                  component_names=("x", "y", "z"), quantity="polarization")
    return img


def test_image_layout_and_views():
    img = image()
    values = img.array("Polar")
    assert values.shape == (2, 3, 4, 3) and values.flags.c_contiguous
    assert img.shape_zyx == (2, 3, 4) and img.n_points == 24
    xyz = img.xyz("Polar")
    assert xyz.shape == (4, 3, 2, 3) and np.shares_memory(xyz, values)
    assert xyz[3, 2, 1].tolist() == [3.0, 2.0, 1.0] and values[1, 2, 3].tolist() == [3.0, 2.0, 1.0]
    # (z, y, x, c) arrays are stored as given (zero copy) and x varies fastest in memory.
    raw = np.zeros((2, 3, 4), dtype=np.float32)
    field = img.add_field("scalar", raw, unit="K", quantity="temperature")
    assert field.values.shape == (2, 3, 4, 1) and np.shares_memory(field.values, raw)
    assert field.tensor == "scalar" and field.dtype == "float32" and field.unit == "K"
    assert img.add_field("stress6", np.zeros((2, 3, 4, 6))).tensor == "array"  # never assumed symmetric
    assert img.add_field("cells", np.ones((1, 2, 3)), association="cell").values.shape == (1, 2, 3, 1)
    with pytest.raises(ValueError, match="expected"):
        img.add_field("bad", np.zeros((4, 3, 2)))  # (x, y, z) passed as (z, y, x)
    with pytest.raises(ValueError, match="C-contiguous"):
        img.add(Field("view", components=3, tensor="vector", values=np.asfortranarray(values)))
    assert img.point(1, 1, 1) == (1.5, -1.0, 1e6 + 2) and img.bounds() == [[1.0, -2.0, 1e6], [2.5, 0.0, 1e6 + 2]]
    assert img.kinds() == {"image"}


def test_direction_and_geometry():
    rotated = ImageData((2, 2, 1), direction=(0, -1, 0, 1, 0, 0, 0, 0, 1))
    assert rotated.point(1, 0, 0) == (0.0, 1.0, 0.0) and not rotated.is_axis_aligned
    with pytest.raises(ValueError):
        ImageData((2, 2), spacing=(1, 1, 1))
    with pytest.raises(ValueError):
        ImageData((2, 2, 2), spacing=(1, 0, 1))
    with pytest.raises(ValueError):
        ImageData((2, 2, 2), origin=(0, float("nan"), 0))


def test_labels_and_field_rules():
    img = image()
    labels = np.full((2, 3, 4), 1, dtype=np.int16)
    labels[0] = 0
    field = img.add_field("domain", labels, categories=DOMAINS, palette="stk:cubic-26-orientation",
                          quantity="domain_variant", unit="1")
    assert field.is_label and field.tensor == "label" and img.kinds() == {"image", "labels"}
    assert field.category(1).direction == (1.0, 0.0, 0.0) and field.category(5) is None
    assert img.label_fields() == [field]
    with pytest.raises(ValueError, match="integer dtype"):
        Field("d", dtype="float32", tensor="label", categories=DOMAINS).validate()
    with pytest.raises(ValueError, match="categories"):
        Field("d", dtype="int16", tensor="label").validate()
    with pytest.raises(ValueError, match="component_names"):
        Field("s", components=6, tensor="symmetric_tensor").validate()
    with pytest.raises(ValueError, match="needs 6"):
        Field("s", components=3, tensor="symmetric_tensor", component_names=("a", "b", "c")).validate()
    with pytest.raises(ValueError):
        Field("a/b").validate()
    with pytest.raises(ValueError, match="unique"):
        Field("d", dtype="int8", tensor="label", categories=[Category(1, "a"), Category(1, "b")]).validate()
    with pytest.raises(ValueError, match="string"):
        Field("s", dtype="string").validate()
    with pytest.raises(ValueError):
        Category(1.5, "x")
    with pytest.raises(ValueError):
        Field.dtype_name(np.zeros(2, dtype=bool))


def test_descriptor_round_trip():
    img = image()
    img.add_field("domain", np.ones((2, 3, 4), dtype=np.int16), categories=DOMAINS, unit="1")
    img.frames = [FrameRef(step=1000, sources={"Polar": SourceRef("Polar.00001000.dat", reader="mupro.dat@1")})]
    img.provenance = Provenance(activity={"kind": "run", "id": "a" * 32}, agent={"connector": "mupro.muferro@0.1.0"},
                                used=[{"path": "Polar.00001000.dat", "sha256": "0" * 64}])
    img.attrs["film"] = {"detected": False, "film_top": None}
    descriptor = img.descriptor()
    assert descriptor["schema"] == "stk.dataset/1" and descriptor["kind"] == "image"
    assert descriptor["geometry"]["dimensions"] == [4, 3, 2] and descriptor["geometry"]["length_unit"] == "nm"
    assert descriptor["fields"][0] == {"name": "Polar", "association": "point", "dtype": "float64", "components": 3,
                                       "tensor": "vector", "unit": "unspecified", "component_names": ["x", "y", "z"],
                                       "quantity": "polarization"}
    assert descriptor["time"]["step"] == 1000
    json.dumps(descriptor, allow_nan=False)
    again = dataset_from_descriptor(json.loads(json.dumps(descriptor)))
    assert isinstance(again, ImageData) and again.descriptor() == descriptor
    assert again.field("Polar").values is None and again.kinds() == {"image", "labels"}
    other = dataset_from_descriptor({"id": "atoms", "kind": "particles", "geometry": {"count": 10},
                                     "fields": [{"name": "type", "association": "point", "dtype": "int32",
                                                 "components": 1, "tensor": "label", "unit": "1",
                                                 "categories": [{"value": 8, "name": "O"}]}]})
    assert type(other) is Dataset and other.kind == "particles" and other.descriptor()["geometry"] == {"count": 10}
    with pytest.raises(KeyError, match="fields"):
        again.field("missing")
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    from suan.contracts import load_all_schemas
    schemas = load_all_schemas()
    registry = referencing.Registry().with_resources(
        [(urn, referencing.Resource.from_contents(s)) for urn, s in schemas.items()])
    validator = jsonschema.Draft202012Validator(schemas["urn:stk:schema:dataset-1"], registry=registry)
    for document in (descriptor, other.descriptor(), PolyData.from_triangles(np.eye(3), [[0, 1, 2]]).descriptor(),
                     Table.from_columns({"step": np.arange(3)}, index="step").descriptor()):
        assert list(validator.iter_errors(document)) == []


def test_grid_adapter_round_trip():
    pytest.importorskip("vtk")  # suan.visualization.scene imports the sviz toolkit
    from suan.visualization.scene import Grid, probe
    img = image()
    img.length_unit = "grid_index"
    grid = img.to_grid("Polar")
    assert isinstance(grid, Grid) and grid.dimensions == (4, 3, 2) and grid.coordinate_units == "grid index"
    assert np.shares_memory(grid.values, img.array("Polar")) and grid.timestep == 1000
    assert probe(grid, (1.5, -1.0, 1e6 + 2))["values"] == [1.0, 1.0, 1.0]
    back = ImageData.from_grid(grid, tensor="vector", component_names=("x", "y", "z"))
    assert back.length_unit == "grid_index" and back.time.step == 1000 and back.id == "Polar"
    np.testing.assert_array_equal(back.array("Polar"), img.array("Polar"))
    assert back.array("Polar").flags.c_contiguous
    with pytest.raises(ValueError):
        ImageData((2, 2, 1), direction=(0, -1, 0, 1, 0, 0, 0, 0, 1), fields=[]).to_grid()


def test_polydata():
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    poly = PolyData.from_triangles(points, [[0, 1, 2], [0, 1, 3]], length_unit="nm")
    assert poly.n_points == 4 and poly.n_cells == 2 and poly.kinds() == {"polydata"}
    poly.add_field("label", np.array([1, 2], dtype=np.int32), association="cell", categories=DOMAINS[2:] + [
        Category(2, "T[-100]")])
    poly.add_field("Normals", np.zeros((4, 3), dtype=np.float32), tensor="vector")
    with pytest.raises(ValueError, match="expected"):
        poly.add_field("wrong", np.zeros(3))
    assert poly.geometry() == {"frame": "grid", "length_unit": "nm", "points": 4, "verts": 0, "lines": 0,
                               "polys": 2, "bounds": [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]}
    cloud = PolyData(points)
    assert cloud.kinds() == {"polydata", "points"}
    with pytest.raises(ValueError):
        PolyData(points, polys=CellArray.uniform([[0, 1, 9]]))
    cells = CellArray.uniform([[0, 1, 2], [2, 3, 0]])
    assert cells.n_cells == 2 and cells.offsets.tolist() == [0, 3, 6]


def test_table():
    table = Table.from_columns({"step": np.array([0, 10, 20]), "Total Energy": np.array([1.5, np.nan, -np.inf])},
                               units={"Total Energy": "normalized"}, quantities={"Total Energy": "energy"},
                               index="step", id="energy")
    assert table.n_rows == 3 and table.columns == ["step", "Total Energy"]
    assert table.field("step").role == "index" and table.field("Total Energy").unit == "normalized"
    assert table.to_json() == {"columns": {"step": [0, 10, 20], "Total Energy": [1.5, "NaN", "-Inf"]},
                               "units": {"step": "unspecified", "Total Energy": "normalized"}}
    table.add_column("name", np.array(["a", "b", "c"]))
    assert table.field("name").dtype == "string" and table.kinds() == {"table"}
    with pytest.raises(ValueError, match="rows"):
        table.add_column("short", np.zeros(2))
    frames = Table.from_columns({"dataset": np.array(["Polar"]), "step": np.array([0]), "path": np.array(["P.dat"])})
    assert frames.kinds() == {"table", "frames"}
    descriptor = table.descriptor()
    assert "columns" in descriptor and descriptor["geometry"] == {"rows": 3}
    assert dataset_from_descriptor(descriptor).descriptor() == descriptor
    assert json_safe({"a": np.float32(np.inf), "b": np.arange(2)}) == {"a": "Inf", "b": [0, 1]}


METADATA_ONLY = r"""
import sys
sys.modules["numpy"] = None
from suan.data.model import Category, Field, ImageData, Table, TimeInfo, dataset_from_descriptor
img = ImageData((8, 8, 4), length_unit="grid_index", id="Polar", time=TimeInfo(step=5))
img.add(Field("Polar", components=3, tensor="vector", quantity="polarization"))
img.add(Field("domain", dtype="int16", tensor="label", unit="1", categories=[Category(1, "T[100]")]))
d = img.descriptor()
assert dataset_from_descriptor(d).descriptor() == d and img.kinds() == {"image", "labels"}
t = Table(id="energy")
t.add(Field("step", association="row", dtype="int64", role="index"))
assert dataset_from_descriptor(t.descriptor()).descriptor() == t.descriptor()
try:
    img.add_field("x", [[[1.0]]])
except ImportError:
    print("ok")
"""


def test_metadata_without_numpy():
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])}
    result = subprocess.run([sys.executable, "-c", METADATA_ONLY], cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
