"""Built-in file connectors (stk.numpy, stk.vtk), the shared file/table readers and frame selection."""
import pytest

np = pytest.importorskip("numpy")

from suan.connectors.api import ConnectorError, DatasetHandle  # noqa: E402
from suan.connectors.builtin import crop_sample, detect_format, read_file, select_frame  # noqa: E402
from suan.connectors.builtin.numpy import NumpyConnector  # noqa: E402
from suan.connectors.builtin.tables import read_columns, read_csv, read_jsonl  # noqa: E402
from suan.connectors.files import LocalFiles  # noqa: E402
from suan.data.dat import write_dat  # noqa: E402
from suan.data.manifest import validate_result  # noqa: E402
from suan.data.model import ImageData  # noqa: E402
from toolkits.sviz.field import write_field  # noqa: E402


def field(shape=(4, 3, 2), components=3):
    return np.arange(np.prod(shape) * components, dtype=float).reshape(*shape, components) / 4


def test_numpy_connector_npy_and_dat(tmp_path):
    np.save(tmp_path / "field.npy", field())
    write_dat(tmp_path / "Polar.00000100.dat", field())
    (tmp_path / "notes.txt").write_text("ignored")
    source = LocalFiles(tmp_path)
    connector = NumpyConnector()
    assert connector.sniff(source).confidence == 0.3
    result = connector.describe(source)
    assert validate_result(result) == []
    datasets = {d["id"]: d for d in result["datasets"]}
    assert set(datasets) == {"field", "Polar"}
    assert datasets["field"]["geometry"]["dimensions"] == [4, 3, 2]
    assert datasets["field"]["fields"][0]["components"] == 3 and datasets["field"]["fields"][0]["tensor"] == "array"
    assert datasets["Polar"]["frames"][0]["sources"]["*"]["reader"] == "mupro.dat@1"
    handle = connector.open(source, "Polar")
    assert isinstance(handle, DatasetHandle)
    image = handle.read()
    assert image.time.step == 100 and image.length_unit == "grid_index"
    np.testing.assert_array_equal(image.xyz("Polar"), field())
    part = handle.read(region=((1, None), (None, 1), (0, 0)), stride=(2, 1, 1))
    np.testing.assert_array_equal(part.xyz("Polar"), field()[1::2, 0:2, 0:1])
    assert part.origin == (1.0, 0.0, 0.0) and part.spacing == (2.0, 1.0, 1.0)
    assert handle.stats(field="Polar")["components"][2]["max"] == field()[..., 2].max()
    npy = connector.open(source, "field").read()
    np.testing.assert_array_equal(npy.xyz("field"), field())
    with pytest.raises(ConnectorError):
        connector.open(source, "notes")
    assert connector.sniff(LocalFiles(tmp_path / "..")) is not None
    (tmp_path / "empty").mkdir()
    assert connector.sniff(LocalFiles(tmp_path / "empty")) is None


def test_read_file_formats(tmp_path):
    pytest.importorskip("vtk")
    data = field()
    write_field(tmp_path / "f.vtk", data)
    write_field(tmp_path / "f.npy", data)
    write_field(tmp_path / "f.dat", data)
    source = LocalFiles(tmp_path)
    for name in ("f.vtk", "f.npy", "f.dat"):
        image = read_file(source, name)
        (values,) = [f.values for f in image.fields.values()]
        np.testing.assert_array_equal(image.array(next(iter(image.fields))).transpose(2, 1, 0, 3), data)
        assert values.flags.c_contiguous
    assert read_file(source, "f.npy").length_unit == "grid_index"
    assert read_file(source, "f.vtk").length_unit == "unspecified"
    assert detect_format("x.VTKHDF") == "vtkhdf" and detect_format("x.bin", "npy") == "npy"
    with pytest.raises(ConnectorError) as error:
        detect_format("x.bin")
    assert error.value.code == "unsupported"
    with pytest.raises(ConnectorError):
        read_file(source, "f.npy", fields=["nope"])
    with pytest.raises(ConnectorError):
        read_file(source, "f.npy", association="cell")


def test_vtk_connector_describes_vti_vtk_and_vtkhdf(tmp_path):
    vtk = pytest.importorskip("vtk")
    pytest.importorskip("h5py")
    from suan.connectors.builtin.vtk import VTKConnector
    from suan.data.vtkconv import image_to_vtk
    from suan.data.vtkhdf import write_vtkhdf
    image = ImageData((4, 3, 2), origin=(1, 2, 3), spacing=(0.5, 0.5, 2), id="sample")
    image.add_field("P", field().transpose(2, 1, 0, 3).copy(), tensor="vector")
    image.add_field("c", np.arange(6, dtype=np.int32).reshape(1, 2, 3), association="cell")
    writer = vtk.vtkXMLImageDataWriter()
    writer.SetFileName(str(tmp_path / "sample.vti"))
    writer.SetInputData(image_to_vtk(image))
    writer.Write()
    write_field(tmp_path / "legacy.vtk", field())
    write_vtkhdf(tmp_path / "sample.vtkhdf", image)
    (tmp_path / "plain.h5").write_bytes(b"\x89HDF\r\n\x1a\nnot really")
    source = LocalFiles(tmp_path)
    connector = VTKConnector()
    result = connector.describe(source)
    assert validate_result(result) == []
    datasets = {d["frames"][0]["sources"]["*"]["path"]: d for d in result["datasets"]}
    assert set(datasets) == {"sample.vti", "legacy.vtk", "sample.vtkhdf"}
    vti = datasets["sample.vti"]
    assert vti["geometry"]["dimensions"] == [4, 3, 2] and vti["geometry"]["origin"] == [1.0, 2.0, 3.0]
    assert [(f["name"], f["association"], f["components"]) for f in vti["fields"]] == [("P", "point", 3),
                                                                                        ("c", "cell", 1)]
    assert datasets["legacy.vtk"]["fields"][0]["components"] == 3
    assert datasets["sample.vtkhdf"]["fields"][0]["tensor"] == "vector"
    for dataset_id in (d["id"] for d in result["datasets"]):
        handle = connector.open(source, dataset_id)
        loaded = handle.read()
        assert loaded.dimensions == (4, 3, 2)
    back = connector.open(source, datasets["sample.vti"]["id"]).read(fields=["P"])
    np.testing.assert_array_equal(back.array("P"), image.array("P"))
    region = connector.open(source, datasets["sample.vtkhdf"]["id"]).read(fields=["P"], region=((1, 2), (0, 2), (0, 1)))
    np.testing.assert_array_equal(region.array("P"), image.array("P")[:, :, 1:3])


def test_crop_sample_and_frame_selection():
    image = ImageData((5, 4, 3), origin=(10, 20, 30), spacing=(1, 2, 3))
    values = np.arange(60, dtype=float).reshape(3, 4, 5)
    image.add_field("s", values)
    assert crop_sample(image) is image
    part = crop_sample(image, ((1, 4), (1, 3), (0, 2)), (3, 2, 2))
    assert part.dimensions == (2, 2, 2) and part.origin == (11.0, 22.0, 30.0) and part.spacing == (3.0, 4.0, 6.0)
    np.testing.assert_array_equal(part.array("s")[..., 0], values[0:3:2, 1:4:2, 1:5:3])
    with pytest.raises(ConnectorError):
        crop_sample(image, ((3, 1), (0, 1), (0, 1)))
    frames = [{"step": 0}, {"step": 100}, {"step": 200}]
    assert select_frame(frames, None)["step"] == 200 and select_frame(frames, {"first": True})["step"] == 0
    assert select_frame(frames, {"step": 150})["step"] == 100 and select_frame(frames, {"index": -1})["step"] == 200
    for selector in ({"step": 150, "policy": "exact"}, {"index": 3}, {"step": -1}):
        with pytest.raises(ConnectorError) as error:
            select_frame(frames, selector)
        assert error.value.code == "frame_not_found"
    with pytest.raises(ConnectorError):
        select_frame([], None)


def test_generic_table_readers():
    table = read_columns("# comment\n! fortran comment\nstep  energy  label\n1  0.5  3\n2  1.5D0  4  # trailing\n",
                         units={"energy": "eV"})
    assert table.columns == ["step", "energy", "label"] and table.column("energy").tolist() == [0.5, 1.5]
    assert table.column("step").dtype == np.int64 and table.field("energy").unit == "eV"
    assert table.field("label").unit == "unspecified"
    assert read_columns("1 2\n3 4\n").columns == ["column_1", "column_2"]
    with pytest.raises(ConnectorError):
        read_columns("1 2\n3\n")
    csv = read_csv("name,value,count\na,1.5,1\nb,,2\n", keep=["count", "name"])
    assert csv.columns == ["count", "name"] and csv.column("name").tolist() == ["a", "b"]
    assert np.isnan(read_csv("name,value\na,1.5\nb,\n").column("value")[1])
    with pytest.raises(ConnectorError):
        read_csv("a,b\n1\n")
    with pytest.raises(ConnectorError):
        read_csv("a,b\n1,2\n", keep=["c"])
    jsonl = read_jsonl('{"step": 1, "loss": 0.5}\n{"step": 2, "note": "x", "loss": 0.25}\n{"step": 3')
    assert jsonl.columns == ["step", "loss", "note"] and jsonl.n_rows == 2
    assert jsonl.column("note").tolist() == ["", "x"] and jsonl.column("step").dtype == np.int64
    with pytest.raises(ConnectorError):
        read_jsonl("[1, 2]\n")
