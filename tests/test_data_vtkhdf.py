"""VTKHDF with the STK profile (h5py) and zero-copy VTK conversion, cross-read by vtkHDFReader."""
import gc
import json
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")
h5py = pytest.importorskip("h5py")

from suan.analysis.orientation import classify_image  # noqa: E402
from suan.data.manifest import validate_dataset  # noqa: E402
from suan.data.model import (CellArray, Dataset, ImageData, PolyData, Provenance, Table, TimeInfo,  # noqa: E402
                             dataset_from_descriptor)
from suan.data.vtkhdf import is_vtkhdf, read_descriptor, read_vtkhdf, write_vtkhdf  # noqa: E402


def image():
    img = ImageData((5, 4, 3), origin=(1.0, -2.0, 1e6), spacing=(0.5, 1.0, 2.0), length_unit="nm", id="Polar",
                    time=TimeInfo(step=1000), provenance=Provenance(agent={"reader": "mupro.dat@1"}))
    x, y, z = np.meshgrid(np.arange(5.0), np.arange(4.0), np.arange(3.0), indexing="ij")
    polar = np.stack([np.sin(x), np.cos(y) - 0.5, z - 1.0], axis=3)
    img.add_field("Polar", polar, layout="xyzc", tensor="vector", component_names=("x", "y", "z"),
                  quantity="polarization", unit="C/m2")
    img.add_field("energy", (x * y).astype(np.float32), layout="xyzc", unit="J/m3", lossy=True)
    img.add_field("cells", np.arange(24, dtype=np.int32).reshape(2, 3, 4), association="cell")
    return classify_image(img, min_magnitude=0.2)


def fields_equal(a, b):
    assert list(a.fields) == list(b.fields)
    for name, field in a.fields.items():
        other = b.field(name)
        assert field.to_json() == other.to_json(), name
        np.testing.assert_array_equal(field.values, other.values)
        assert other.values.flags.c_contiguous


def test_image_round_trip_keeps_values_and_metadata(tmp_path):
    original = image()
    path = write_vtkhdf(tmp_path / "Polar.vtkhdf", original)
    assert is_vtkhdf(path) and not is_vtkhdf(tmp_path / "missing.vtkhdf")
    back = read_vtkhdf(path)
    assert isinstance(back, ImageData) and back.dimensions == (5, 4, 3) and back.origin == original.origin
    assert back.spacing == original.spacing and back.length_unit == "nm" and back.time.step == 1000
    fields_equal(original, back)
    assert back.field("domain").categories == original.field("domain").categories
    assert back.descriptor() == original.descriptor()
    descriptor = read_descriptor(path)
    assert descriptor["schema"] == "stk.dataset/1" and validate_dataset(descriptor) == []
    assert dataset_from_descriptor(descriptor).field("Polar").unit == "C/m2"
    with h5py.File(path, "r") as handle:
        root = handle["VTKHDF"]
        assert root.attrs["Type"] == b"ImageData" and root.attrs["Type"].dtype.kind == "S"
        assert list(root.attrs["Version"]) == [2, 0] and list(root.attrs["WholeExtent"]) == [0, 4, 0, 3, 0, 2]
        polar = root["PointData/Polar"]
        assert polar.shape == (3, 4, 5, 3) and polar.compression == "gzip" and polar.shuffle
        assert root["PointData/energy"].shape == (3, 4, 5) and root["CellData/cells"].shape == (2, 3, 4)
        assert polar.attrs["stk_unit"] == "C/m2" and json.loads(polar.attrs["stk_component_names"]) == ["x", "y", "z"]
        assert bool(root["PointData/energy"].attrs["stk_lossy"])
        assert int(handle["STK"].attrs["profile"]) == 1
    # Fields can be selected; per-array attributes are enough without the /STK descriptor.
    assert list(read_vtkhdf(path, fields=["energy"]).fields) == ["energy"]
    with h5py.File(path, "a") as handle:
        del handle["STK"]
    plain = read_vtkhdf(path)
    assert plain.field("Polar").unit == "C/m2" and plain.field("domain").tensor == "label"
    assert plain.length_unit == "unspecified" and plain.id == "Polar"


def test_region_and_stride_equal_crop_then_sample(tmp_path):
    original = image()
    path = write_vtkhdf(tmp_path / "f.vtkhdf", original)
    part = read_vtkhdf(path, fields=["Polar", "domain"], region=((1, 4), (0, None), (1, 2)), stride=(2, 3, 1))
    assert part.dimensions == (2, 2, 2)
    assert part.origin == original.point(1, 0, 1) and part.spacing == (1.0, 3.0, 2.0)
    np.testing.assert_array_equal(part.array("Polar"), original.array("Polar")[1:3, 0:4:3, 1:5:2])
    np.testing.assert_array_equal(part.array("domain"), original.array("domain")[1:3, 0:4:3, 1:5:2])
    with pytest.raises(ValueError, match="Cell field"):
        read_vtkhdf(path, region=((0, 1), (0, 1), (0, 1)))
    with pytest.raises(ValueError):
        read_vtkhdf(path, fields=["Polar"], region=((4, 1), (0, 1), (0, 1)))


def poly():
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [2, 2, 2]], dtype=float)
    data = PolyData(points, verts=CellArray.uniform([[4]]), lines=CellArray.uniform([[0, 4]]),
                    polys=CellArray.uniform([[0, 1, 2], [0, 1, 3]]), id="surface", length_unit="grid_index")
    data.add_field("iso", np.linspace(0, 1, 5), unit="K")
    data.add_field("label", np.array([7, 1, 3, 4], dtype=np.int32), association="cell")
    return data


def test_polydata_and_table_round_trip(tmp_path):
    original = poly()
    back = read_vtkhdf(write_vtkhdf(tmp_path / "s.vtkhdf", original))
    np.testing.assert_array_equal(back.points, original.points)
    for name in ("verts", "lines", "polys"):
        np.testing.assert_array_equal(getattr(back, name).offsets, getattr(original, name).offsets)
        np.testing.assert_array_equal(getattr(back, name).connectivity, getattr(original, name).connectivity)
    fields_equal(original, back)
    assert back.descriptor() == original.descriptor()
    table = Table.from_columns({"step": np.arange(4), "Total Energy": np.array([1.0, np.nan, 2.5, -1.0]),
                                "name": np.array(["a", "bé", "c", "d"])}, units={"Total Energy": "normalized"},
                               index="step", id="energy")
    table.add_column("pair", np.arange(8.0).reshape(4, 2))
    path = write_vtkhdf(tmp_path / "t.vtkhdf", table)
    back = read_vtkhdf(path)
    assert back.columns == ["step", "Total Energy", "name", "pair"] and back.index == "step"
    assert back.column("name").tolist() == ["a", "bé", "c", "d"] and back.field("Total Energy").unit == "normalized"
    np.testing.assert_array_equal(back.column("Total Energy"), table.column("Total Energy"))
    np.testing.assert_array_equal(back.column("pair"), table.column("pair"))
    with h5py.File(path, "r") as handle:
        assert int(handle["VTKHDF/NumberOfRows"][0]) == 4
    with pytest.raises(ValueError):
        write_vtkhdf(tmp_path / "x.vtkhdf", Dataset(kind="particles"))


def test_vtk_hdf_reader_cross_read(tmp_path):
    vtk = pytest.importorskip("vtk")
    from vtk.util.numpy_support import vtk_to_numpy
    original = image()
    path = write_vtkhdf(tmp_path / "Polar.vtkhdf", original)
    reader = vtk.vtkHDFReader()
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    assert data.GetDimensions() == (5, 4, 3) and data.GetSpacing() == (0.5, 1.0, 2.0)
    assert data.GetOrigin() == (1.0, -2.0, 1e6)
    for name in ("Polar", "energy", "domain"):
        values = vtk_to_numpy(data.GetPointData().GetArray(name))
        expected = original.array(name)
        np.testing.assert_array_equal(values.reshape(expected.shape), expected)
    np.testing.assert_array_equal(vtk_to_numpy(data.GetCellData().GetArray("cells")), np.arange(24))
    polypath = write_vtkhdf(tmp_path / "s.vtkhdf", poly())
    reader = vtk.vtkHDFReader()
    reader.SetFileName(str(polypath))
    reader.Update()
    surface = reader.GetOutput()
    assert surface.GetNumberOfPoints() == 5 and surface.GetNumberOfPolys() == 2 and surface.GetNumberOfLines() == 1
    assert surface.GetNumberOfVerts() == 1
    np.testing.assert_array_equal(vtk_to_numpy(surface.GetCellData().GetArray("label")), [7, 1, 3, 4])


def test_vtk_hdf_reader_reads_numeric_tables(tmp_path):
    pytest.importorskip("vtk")
    table = Table.from_columns({"step": np.arange(3), "e": np.array([0.5, 1.5, 2.5])}, index="step", id="energy")
    path = write_vtkhdf(tmp_path / "t.vtkhdf", table)
    # In a subprocess: an unsupported table layout crashes vtkHDFReader instead of raising.
    code = ("import sys, vtk\nr = vtk.vtkHDFReader(); r.SetFileName(sys.argv[1]); r.Update()\n"
            "t = r.GetOutputDataObject(0)\nprint(t.GetNumberOfRows(), sorted(t.GetColumnName(i) "
            "for i in range(t.GetNumberOfColumns())), t.GetColumnByName('e').GetValue(2))\n")
    result = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.split() == ["3", "['e',", "'step']", "2.5"]


def test_vtkconv_zero_copy_round_trip():
    pytest.importorskip("vtk")
    from suan.data.vtkconv import image_to_vtk, polydata_to_vtk, to_vtk, vtk_to_image, vtk_to_polydata
    from vtk.util.numpy_support import vtk_to_numpy
    original = image()
    data = image_to_vtk(original)
    array = vtk_to_numpy(data.GetPointData().GetArray("Polar"))
    assert np.shares_memory(array, original.array("Polar"))
    assert data.GetPointData().GetScalars().GetName() == "energy"
    assert data.GetPointData().GetVectors().GetName() == "Polar"
    assert data.GetCellData().GetArray("cells").GetNumberOfTuples() == 24
    assert data.GetPoint(data.ComputePointId([1, 2, 1])) == original.point(1, 2, 1)
    back = vtk_to_image(data, meta={"domain": {"categories": original.field("domain").categories}})
    assert back.dimensions == original.dimensions and back.origin == original.origin
    assert np.shares_memory(back.array("Polar"), original.array("Polar"))
    np.testing.assert_array_equal(back.array("domain"), original.array("domain"))
    assert back.field("domain").tensor == "label" and back.field("cells").association == "cell"
    copied = vtk_to_image(data, copy=True, fields=["Polar"])
    assert list(copied.fields) == ["Polar"] and not np.shares_memory(copied.array("Polar"), original.array("Polar"))
    # Views of VTK-owned memory stay valid after the VTK object is gone.
    source = __import__("vtk").vtkRTAnalyticSource()
    source.SetWholeExtent(-2, 2, 0, 3, 1, 2)
    source.Update()
    wavelet = vtk_to_image(source.GetOutput(), id="wavelet")
    expected = vtk_to_numpy(source.GetOutput().GetPointData().GetScalars()).copy()
    assert wavelet.origin == (-2.0, 0.0, 1.0) and wavelet.dimensions == (5, 4, 2)
    del source
    gc.collect()
    np.testing.assert_array_equal(wavelet.array("RTData").reshape(-1), expected)
    surface = poly()
    vtk_poly = to_vtk(surface)
    assert vtk_poly.GetNumberOfPolys() == 2 and vtk_poly.GetNumberOfCells() == 4
    back = vtk_to_polydata(vtk_poly)
    np.testing.assert_array_equal(back.points, surface.points)
    np.testing.assert_array_equal(back.polys.connectivity, surface.polys.connectivity)
    np.testing.assert_array_equal(back.array("label")[:, 0], [7, 1, 3, 4])
    assert back.array("iso").shape == (5, 1) and back.n_cells == 4
    del vtk_poly
    gc.collect()
    np.testing.assert_array_equal(back.points, surface.points)
    assert polydata_to_vtk(PolyData(np.zeros((0, 3)))).GetNumberOfPoints() == 0
    with pytest.raises(ValueError):
        to_vtk(Table.from_columns({"a": np.arange(2)}))
