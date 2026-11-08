"""MuPRO HDF5 frame reader candidate (CL-MUPRO-H5-01) on real synthetic h5py files.

Every test writes its own HDF5 file with h5py and reads it back through
``read_hdf5_image``; no reader or writer is stubbed. Data are synthetic and say
nothing about real MuPRO output.
"""
import json
import os
import subprocess
import sys
import time

import pytest

np = pytest.importorskip("numpy")
h5py = pytest.importorskip("h5py")

from suan.connectors.api import ConnectorError  # noqa: E402
from suan.connectors.builtin import crop_sample  # noqa: E402
from suan.connectors.mupro import hdf5  # noqa: E402
from suan.connectors.mupro.hdf5 import read_hdf5_image  # noqa: E402

NX, NY, NZ = 5, 4, 3  # deliberately different sizes per axis


def field(nc, dtype="float64", offset=0.0):
    """(nx, ny, nz, nc) array, x slowest; each value encodes its (x, y, z, c) index."""
    x, y, z, c = np.meshgrid(np.arange(NX), np.arange(NY), np.arange(NZ), np.arange(nc), indexing="ij")
    values = 1000 * x + 100 * y + 10 * z + c + offset
    return values.astype(dtype)


def write(path, datasets, **kwargs):
    with h5py.File(path, "w") as handle:
        for name, values in datasets.items():
            handle.create_dataset(name, data=values, **kwargs)
    return path


@pytest.fixture
def run_h5(tmp_path):
    polar = field(3)
    polar[1, 2, 0, 1] = np.nan
    datasets = {
        "/t00001000/Polar": polar,
        "/t00002000/Polar": field(3, offset=0.5),
        "/t00001000/Strain": field(6),
        "/t00001000/Charges": field(1, "float32"),
        "/t00001000/Label": field(1, "int32"),
        "/t00001000/Count": field(2, "uint16"),
        "/t00001000/Wide": field(1, "int64"),
    }
    return write(tmp_path / "run.h5", datasets), datasets


def code(excinfo):
    return excinfo.value.code


def expected_zyxc(values):
    return np.ascontiguousarray(values.transpose(2, 1, 0, 3))


# --- layout, dtype and metadata -------------------------------------------------------------------


def test_axis_order_values_and_metadata(run_h5):
    path, datasets = run_h5
    image = read_hdf5_image(path, "/t00001000/Polar")
    assert image.dimensions == (NX, NY, NZ)
    assert image.origin == (0.0, 0.0, 0.0) and image.spacing == (1.0, 1.0, 1.0)
    assert image.frame == "grid" and image.length_unit == "grid_index"
    assert image.time.step == 1000 and image.time.time is None and image.time.unit == "unspecified"
    polar = image.field("Polar")
    assert polar.values.shape == (NZ, NY, NX, 3) and polar.values.flags.c_contiguous
    assert np.array_equal(polar.values, expected_zyxc(datasets["/t00001000/Polar"]), equal_nan=True)
    # (z, y, x, c) indexing: the value encodes the original (x, y, z, c)
    assert polar.values[2, 3, 4, 1] == 1000 * 4 + 100 * 3 + 10 * 2 + 1
    assert np.isnan(polar.values[0, 2, 1, 1])  # NaN kept, never replaced
    assert polar.tensor == "vector" and polar.component_names == ("x", "y", "z")
    assert polar.quantity == "polarization" and polar.unit == "unspecified" and not polar.lossy
    assert image.provenance.agent == {"reader": "mupro.hdf5@1"}


def test_six_components_stay_array(run_h5):
    path, _ = run_h5
    strain = read_hdf5_image(path, "/t00001000/Strain").field("Strain")
    assert strain.components == 6 and strain.tensor == "array" and strain.component_names is None
    assert strain.unit == "unspecified"


@pytest.mark.parametrize("name, dtype, components", [
    ("Charges", "float32", 1), ("Label", "int32", 1), ("Count", "uint16", 2), ("Wide", "int64", 1)])
def test_dtypes_preserved(run_h5, name, dtype, components):
    path, datasets = run_h5
    result = read_hdf5_image(path, f"/t00001000/{name}").field(name)
    assert result.dtype == dtype and result.values.dtype == np.dtype(dtype)
    assert result.components == components and not result.lossy
    assert result.tensor == ("scalar" if components == 1 else "array")
    assert np.array_equal(result.values, expected_zyxc(datasets[f"/t00001000/{name}"]))


def test_unknown_stem_and_mismatched_count_are_generic(tmp_path):
    path = write(tmp_path / "f.h5", {"/t00000001/Polar": field(1), "/t00000001/Custom7": field(3)})
    polar = read_hdf5_image(path, "/t00000001/Polar").field("Polar")
    assert polar.tensor == "scalar" and polar.quantity is None
    custom = read_hdf5_image(path, "/t00000001/Custom7").field("Custom7")
    assert custom.tensor == "array" and custom.component_names is None and custom.quantity is None


def test_big_endian_values_kept(tmp_path):
    values = field(1, ">f8")
    values[0, 0, 0, 0] = -0.0
    path = write(tmp_path / "be.h5", {"/t00000005/Elec_Phi": values})
    result = read_hdf5_image(path, "/t00000005/Elec_Phi").field("Elec_Phi")
    assert result.dtype == "float64" and result.values.dtype.isnative
    assert np.array_equal(result.values, expected_zyxc(values.astype("<f8")))
    assert np.signbit(result.values[0, 0, 0, 0])


def test_two_step_selectors(run_h5):
    path, datasets = run_h5
    first = read_hdf5_image(path, "/t00001000/Polar")
    second = read_hdf5_image(path, "/t00002000/Polar")
    assert second.time.step == 2000
    assert np.array_equal(second.field("Polar").values, expected_zyxc(datasets["/t00002000/Polar"]))
    assert not np.array_equal(first.field("Polar").values, second.field("Polar").values, equal_nan=True)


def test_chunked_compressed_source(tmp_path):
    values = field(3)
    path = write(tmp_path / "c.h5", {"/t00000003/Polar": values}, chunks=(2, 2, 2, 3), compression="gzip",
                 shuffle=True)
    result = read_hdf5_image(path, "/t00000003/Polar", region=((1, 3), (0, 2), (1, 2)), stride=(2, 1, 1))
    full = read_hdf5_image(path, "/t00000003/Polar")
    assert np.array_equal(result.field("Polar").values,
                          crop_sample(full, ((1, 3), (0, 2), (1, 2)), (2, 1, 1)).field("Polar").values)


# --- region / stride ------------------------------------------------------------------------------


REGIONS = [
    (None, None),
    (((1, 3), (0, 2), (1, 2)), None),
    (None, (2, 3, 2)),
    (((1, 4), (1, 3), (0, 2)), (2, 2, 2)),
    (((None, 2), (2, None), (None, None)), (1, 2, 1)),
    (((-5, 99), (-1, 1), (2, 7)), (3, 1, 1)),  # clamped like crop_sample
    (((4, 4), (3, 3), (2, 2)), (9, 9, 9)),  # single point, stride larger than the grid
]


@pytest.mark.parametrize("region, stride", REGIONS)
def test_region_stride_equals_crop_sample(run_h5, region, stride):
    path, _ = run_h5
    full = read_hdf5_image(path, "/t00001000/Polar")
    expected = crop_sample(full, region, stride)
    result = read_hdf5_image(path, "/t00001000/Polar", region=region, stride=stride)
    assert result.dimensions == expected.dimensions
    assert result.origin == expected.origin and result.spacing == expected.spacing
    assert result.direction == expected.direction and result.length_unit == expected.length_unit
    values = result.field("Polar").values
    assert values.flags.c_contiguous
    assert np.array_equal(values, expected.field("Polar").values, equal_nan=True)


def test_hyperslab_reads_only_the_selection(run_h5, monkeypatch):
    path, _ = run_h5
    seen = []
    original = hdf5._read_hyperslab

    def spy(dataset, destination, selection):
        seen.append((destination.shape, selection))
        original(dataset, destination, selection)

    monkeypatch.setattr(hdf5, "_read_hyperslab", spy)
    read_hdf5_image(path, "/t00001000/Polar", region=((1, 3), (0, 2), (1, 2)), stride=(2, 1, 1))
    assert seen == [((2, 3, 2, 3), (slice(1, 4, 2), slice(0, 3, 1), slice(1, 3, 1), slice(None)))]


@pytest.mark.parametrize("region, stride", [
    (((3, 1), (0, 1), (0, 1)), None),
    (((0, 1), (0, 1)), None),
    (((0, 1, 2), (0, 1), (0, 1)), None),
    (((0.5, 1), (0, 1), (0, 1)), None),
    (((True, 1), (0, 1), (0, 1)), None),
    ("abc", None),
    (5, None),
    (None, (0, 1, 1)),
    (None, (1, 1)),
    (None, (1, True, 1)),
    (None, (1.0, 1, 1)),
    (None, 3),
])
def test_bad_region_or_stride(run_h5, region, stride):
    path, _ = run_h5
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Polar", region=region, stride=stride)
    assert code(excinfo) == "invalid_param"


def test_region_outside_grid_is_empty(run_h5):
    path, _ = run_h5
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Polar", region=((7, 9), (0, 1), (0, 1)))
    assert code(excinfo) == "invalid_param"


# --- selector, missing objects, shapes and types --------------------------------------------------


@pytest.mark.parametrize("selector", [
    "t00001000/Polar", "/t1000/Polar", "/t000010000/Polar", "/t00001000/", "/t00001000/Po.lar",
    "/t00001000/Po/lar", "/t00001000/1Polar", "/x00001000/Polar", "/t00001000/Polar/", None, 1000, b"/t00001000/P",
    "/t00000000/Polar\n", "/t00001000/Polar\n", "/t00001000/Polar\r", "/t00001000/Polar\r\n", "\n/t00001000/Polar",
    "/t00001000/Polar ", "/t٠٠٠٠١٠٠٠/Polar", "/t00001000/Polаr"])
def test_bad_selector(run_h5, selector):
    path, _ = run_h5
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, selector)
    assert code(excinfo) == "invalid_param"


def test_missing_group_and_field(run_h5):
    path, _ = run_h5
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00003000/Polar")
    assert code(excinfo) == "frame_not_found"
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Stress")
    assert code(excinfo) == "not_found"
    assert str(path) not in str(excinfo.value)


def test_wrong_object_types(tmp_path):
    path = tmp_path / "types.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("t00000001", data=np.zeros((1, 1, 1, 1)))
        handle.create_group("t00000002/Polar")
    for selector in ("/t00000001/Polar", "/t00000002/Polar"):
        with pytest.raises(ConnectorError) as excinfo:
            read_hdf5_image(path, selector)
        assert code(excinfo) == "invalid_data"


@pytest.mark.parametrize("values", [
    np.zeros((NX, NY, NZ)), np.zeros((NX, NY, NZ, 1, 1)), np.zeros((NX, 0, NZ, 1)), np.zeros(())],
    ids=["3d", "5d", "zero-size", "scalar"])
def test_bad_shapes(tmp_path, values):
    path = write(tmp_path / "shape.h5", {"/t00000001/Polar": values})
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data"


@pytest.mark.parametrize("values", [
    np.zeros((2, 2, 2, 1), dtype=bool), np.zeros((2, 2, 2, 1), dtype=np.float16),
    np.zeros((2, 2, 2, 1), dtype=np.complex128), np.zeros((2, 2, 2, 1), dtype="S4"),
    np.zeros((2, 2, 2, 1), dtype=[("a", "f8"), ("b", "i4")]), np.zeros((2, 2, 2, 1), dtype=("f8", (2,)))],
    ids=["bool", "float16", "complex", "bytes", "compound", "subarray"])
def test_bad_dtypes(tmp_path, values):
    path = write(tmp_path / "dtype.h5", {"/t00000001/Polar": values})
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data"


def test_enum_dtype_refused(tmp_path):
    path = tmp_path / "enum.h5"
    kind = h5py.enum_dtype({"A": 0, "B": 1}, basetype="i1")
    with h5py.File(path, "w") as handle:
        handle.create_dataset("t00000001/Polar", data=np.zeros((2, 2, 2, 1), dtype="i1"), dtype=kind)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data"


# --- budget ---------------------------------------------------------------------------------------


def test_byte_budget_checked_before_reading(run_h5, monkeypatch):
    path, _ = run_h5
    needed = 2 * NX * NY * NZ * 3 * 8  # buffer plus transposed copy
    assert read_hdf5_image(path, "/t00001000/Polar", max_bytes=needed).field("Polar").values.nbytes == needed // 2

    def fail(*args):
        raise AssertionError("read attempted over budget")

    monkeypatch.setattr(hdf5, "_read_hyperslab", fail)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Polar", max_bytes=needed - 1)
    assert code(excinfo) == "budget_exceeded"
    # a smaller region fits the same budget
    small = 2 * 2 * 2 * 2 * 3 * 8
    monkeypatch.undo()
    assert read_hdf5_image(path, "/t00001000/Polar", region=((0, 1), (0, 1), (0, 1)), max_bytes=small).dimensions \
        == (2, 2, 2)


@pytest.mark.parametrize("max_bytes", [0, -1, 1.5, True, "1", None])
def test_bad_max_bytes(run_h5, max_bytes):
    path, _ = run_h5
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Polar", max_bytes=max_bytes)
    assert code(excinfo) == "invalid_param"


def test_chunk_decoding_counts_against_budget(tmp_path):
    """A one-point read of a big compressed chunk must still decode the whole chunk; the budget sees that."""
    path = tmp_path / "bigchunk.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("t00000001/Polar", data=field(3), chunks=(NX, NY, NZ, 3), compression="gzip")
    one = ((0, 0), (0, 0), (0, 0))
    chunk = NX * NY * NZ * 3 * 8
    needed = 2 * 3 * 8 + 2 * chunk  # buffer + transposed copy + stored and decoded chunk
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar", region=one, max_bytes=needed - 1)
    assert code(excinfo) == "budget_exceeded"
    assert read_hdf5_image(path, "/t00000001/Polar", region=one, max_bytes=needed).dimensions == (1, 1, 1)
    plain = tmp_path / "plainchunk.h5"
    with h5py.File(plain, "w") as handle:  # chunked without filters: one decoded chunk only
        handle.create_dataset("t00000001/Polar", data=field(3), chunks=(NX, NY, NZ, 3))
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(plain, "/t00000001/Polar", region=one, max_bytes=2 * 3 * 8 + chunk - 1)
    assert code(excinfo) == "budget_exceeded"
    assert read_hdf5_image(plain, "/t00000001/Polar", region=one, max_bytes=2 * 3 * 8 + chunk).dimensions \
        == (1, 1, 1)


# --- unwritten data and filters -------------------------------------------------------------------


def test_unwritten_dataset_refused(tmp_path, monkeypatch):
    path = tmp_path / "unwritten.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("t00000001/Polar", shape=(NX, NY, NZ, 3), dtype="f8")  # never written
        handle.create_dataset("t00000002/Polar", shape=(NX, NY, NZ, 3), dtype="f8", chunks=(2, 2, 2, 3))
    monkeypatch.setattr(hdf5, "_read_hyperslab", lambda *a: pytest.fail("fill values were read"))
    for selector in ("/t00000001/Polar", "/t00000002/Polar"):
        with pytest.raises(ConnectorError) as excinfo:
            read_hdf5_image(path, selector)
        assert code(excinfo) == "invalid_data" and "written" in str(excinfo.value)


def test_partly_written_chunks_refused(tmp_path, monkeypatch):
    path = tmp_path / "partial.h5"
    with h5py.File(path, "w") as handle:
        dataset = handle.create_dataset("t00000001/Polar", shape=(4, 4, 2, 1), dtype="f8", chunks=(2, 2, 2, 1))
        dataset[0:2, 0:2] = 1.0  # one of four chunks
        assert dataset.id.get_num_chunks() == 1
    monkeypatch.setattr(hdf5, "_read_hyperslab", lambda *a: pytest.fail("fill values were read"))
    for region in (None, ((0, 1), (0, 1), (0, 1))):  # even a selection inside the written chunk
        with pytest.raises(ConnectorError) as excinfo:
            read_hdf5_image(path, "/t00000001/Polar", region=region)
        assert code(excinfo) == "invalid_data" and "partly written" in str(excinfo.value)


def test_plugin_filter_refused_before_reading(tmp_path, monkeypatch):
    from h5py import h5d, h5p, h5s, h5t, h5z
    path = tmp_path / "plugin.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("t00000001")
        plist = h5p.create(h5p.DATASET_CREATE)
        plist.set_chunk((NX, NY, NZ, 1))
        plist.set_filter(32004, h5z.FLAG_OPTIONAL, ())  # a registered plugin id (LZ4), not built in
        dataset = h5py.Dataset(h5d.create(group.id, b"Polar", h5t.IEEE_F64LE, h5s.create_simple((NX, NY, NZ, 1)),
                                          dcpl=plist))
        dataset[...] = field(1)
    monkeypatch.setattr(hdf5, "_read_hyperslab", lambda *a: pytest.fail("a plugin filter would be loaded"))
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data" and "filter" in str(excinfo.value)


def test_builtin_filters_accepted(tmp_path):
    values = field(3, "float32")
    path = write(tmp_path / "filters.h5", {"/t00000001/Polar": values}, chunks=(2, 2, 3, 3), compression="lzf",
                 shuffle=True, fletcher32=True)
    result = read_hdf5_image(path, "/t00000001/Polar").field("Polar")
    assert np.array_equal(result.values, expected_zyxc(values))


# --- damaged files, links and external storage ----------------------------------------------------


def test_not_hdf5_and_truncated(tmp_path, run_h5):
    junk = tmp_path / "junk.h5"
    junk.write_bytes(b"not an hdf5 file" * 100)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(junk, "/t00001000/Polar")
    assert code(excinfo) == "invalid_data"
    path, _ = run_h5
    truncated = tmp_path / "truncated.h5"
    data = path.read_bytes()
    truncated.write_bytes(data[: len(data) // 3])
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(truncated, "/t00001000/Polar")
    assert code(excinfo) == "invalid_data"
    empty = tmp_path / "empty.h5"
    empty.write_bytes(b"")
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(empty, "/t00001000/Polar")
    assert code(excinfo) == "invalid_data"


def test_corrupt_chunk(tmp_path):
    path = tmp_path / "chunk.h5"
    values = np.arange(NX * NY * NZ * 3, dtype="f8").reshape(NX, NY, NZ, 3)
    with h5py.File(path, "w") as handle:
        dataset = handle.create_dataset("t00000001/Polar", data=values, chunks=(NX, NY, NZ, 3),
                                        compression="gzip")
        offset = dataset.id.get_chunk_info(0).byte_offset
    with open(path, "r+b") as stream:
        stream.seek(offset)
        stream.write(b"\xff" * 16)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data"


def test_soft_links_refused(tmp_path):
    path = tmp_path / "soft.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("data/Polar", data=field(3))
        handle["t00000001"] = h5py.SoftLink("/data")
        handle.create_group("t00000002")
        handle["t00000002/Polar"] = h5py.SoftLink("/data/Polar")
    for selector in ("/t00000001/Polar", "/t00000002/Polar"):
        with pytest.raises(ConnectorError) as excinfo:
            read_hdf5_image(path, selector)
        assert code(excinfo) == "invalid_data"


def test_external_links_refused_without_opening_target(tmp_path, monkeypatch):
    target = write(tmp_path / "target.h5", {"/t00000001/Polar": field(3)})
    path = tmp_path / "ext.h5"
    with h5py.File(path, "w") as handle:
        handle["t00000001"] = h5py.ExternalLink(str(target), "/t00000001")
        handle.create_group("t00000002")
        handle["t00000002/Polar"] = h5py.ExternalLink(str(target), "/t00000001/Polar")
    os.chmod(target, 0)  # opening the target would fail differently; it must not be attempted
    try:
        for selector in ("/t00000001/Polar", "/t00000002/Polar"):
            with pytest.raises(ConnectorError) as excinfo:
                read_hdf5_image(path, selector)
            assert code(excinfo) == "invalid_data" and "external" in str(excinfo.value)
            assert str(target) not in str(excinfo.value)
    finally:
        os.chmod(target, 0o600)


def test_virtual_dataset_refused(tmp_path):
    source = write(tmp_path / "source.h5", {"/data": field(3)})
    path = tmp_path / "vds.h5"
    layout = h5py.VirtualLayout(shape=(NX, NY, NZ, 3), dtype="f8")
    layout[...] = h5py.VirtualSource(str(source), "data", shape=(NX, NY, NZ, 3))
    with h5py.File(path, "w") as handle:
        handle.create_group("t00000001").create_virtual_dataset("Polar", layout)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data" and "Virtual" in str(excinfo.value)


def test_external_storage_refused(tmp_path):
    raw = tmp_path / "raw.bin"
    raw.write_bytes(field(1).tobytes())
    path = tmp_path / "external.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("t00000001/Polar", shape=(NX, NY, NZ, 1), dtype="f8",
                              external=[(str(raw), 0, h5py.h5f.UNLIMITED)])
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data" and "external raw storage" in str(excinfo.value)


# --- file system guards ---------------------------------------------------------------------------


def test_missing_file(tmp_path):
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(tmp_path / "absent.h5", "/t00000001/Polar")
    assert code(excinfo) == "missing_file" and "absent" not in str(excinfo.value)


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32", reason="POSIX symlinks")
def test_symlink_not_followed(run_h5, tmp_path):
    path, _ = run_h5
    link = tmp_path / "link.h5"
    link.symlink_to(path)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(link, "/t00001000/Polar")
    assert code(excinfo) == "invalid_path"
    dangling = tmp_path / "dangling.h5"
    dangling.symlink_to(tmp_path / "nowhere.h5")
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(dangling, "/t00001000/Polar")
    assert code(excinfo) == "invalid_path"


def test_directory_and_fifo_refused(tmp_path):
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(tmp_path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data"
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "fifo.h5"
        os.mkfifo(fifo)
        with pytest.raises(ConnectorError) as excinfo:
            read_hdf5_image(fifo, "/t00000001/Polar")
        assert code(excinfo) == "invalid_data"


@pytest.mark.parametrize("path", ["", "a\x00b", 5, None])
def test_bad_path_argument(path):
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_param"


def test_replaced_during_read_is_detected(run_h5, tmp_path, monkeypatch):
    path, _ = run_h5
    other = write(tmp_path / "other.h5", {"/t00001000/Polar": field(3, offset=7.0)})
    original = hdf5._read_hyperslab

    blocked = []

    def replace_then_read(dataset, destination, selection):
        try:
            os.replace(other, path)  # a real rename over the open file
        except PermissionError:
            if os.name != "nt":
                raise
            blocked.append(True)  # Windows refuses to replace a file that is open without FILE_SHARE_DELETE
        original(dataset, destination, selection)

    monkeypatch.setattr(hdf5, "_read_hyperslab", replace_then_read)
    if os.name == "nt":
        image = read_hdf5_image(path, "/t00001000/Polar")
        assert blocked and image.field("Polar").values[0, 0, 0, 0] == 0.0  # original bytes, not the other file
        return
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Polar")
    assert code(excinfo) == "invalid_data" and "changed" in str(excinfo.value)


def native_change_time(path):
    """The reader's own native change-time helper on a separately opened descriptor."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        return hdf5._change_time(descriptor)
    finally:
        os.close(descriptor)


def rewrite_restoring_mtime(path, offset, data):
    """Overwrite bytes in place (same size), then put atime/mtime back with os.utime."""
    start = os.stat(path)
    time.sleep(0.05)  # past coarse file system timestamp granularity
    with open(path, "r+b") as stream:
        stream.seek(offset)
        stream.write(data)
    os.utime(path, ns=(start.st_atime_ns, start.st_mtime_ns))


def test_change_time_helper_is_native_and_advances(tmp_path):
    path = tmp_path / "helper.bin"
    path.write_bytes(b"0123456789abcdef")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        first = hdf5._change_time(descriptor)
        assert isinstance(first, int)
        if os.name != "nt":
            assert first == os.fstat(descriptor).st_ctime_ns
        start = os.stat(path)
        rewrite_restoring_mtime(path, 4, b"WXYZ")
        end = os.stat(path)
        assert (start.st_size, start.st_mtime_ns) == (end.st_size, end.st_mtime_ns)
        assert hdf5._change_time(descriptor) != first  # observed through the same pinned descriptor
    finally:
        os.close(descriptor)


def test_change_time_helper_fails_closed(tmp_path):
    path = tmp_path / "closed.bin"
    path.write_bytes(b"x")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    os.close(descriptor)
    with pytest.raises(ConnectorError) as excinfo:
        hdf5._change_time(descriptor)
    assert code(excinfo) == "invalid_data"


@pytest.mark.skipif(os.name != "nt", reason="Windows HANDLE query")
def test_windows_change_time_is_not_creation_time(tmp_path):
    import ctypes
    import msvcrt
    from ctypes import wintypes
    path = tmp_path / "win.bin"
    path.write_bytes(b"0123456789abcdef")
    descriptor = os.open(path, os.O_RDONLY | os.O_BINARY)
    query = ctypes.WinDLL("kernel32", use_last_error=True).GetFileTime
    query.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                      ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME))
    query.restype = wintypes.BOOL

    def creation_time():
        value = wintypes.FILETIME()
        assert query(msvcrt.get_osfhandle(descriptor), ctypes.byref(value), None, None)
        return value.dwHighDateTime << 32 | value.dwLowDateTime

    try:
        # Python's path/fd stat APIs and versions need not expose the same ctime.
        # Query creation time independently of the reader's ChangeTime API.
        created = creation_time()
        changed = hdf5._windows_change_time(descriptor)
        rewrite_restoring_mtime(path, 0, b"ABCD")
        assert creation_time() == created
        assert hdf5._windows_change_time(descriptor) != changed  # FILE_BASIC_INFO.ChangeTime does
        assert hdf5._change_time(descriptor) == hdf5._windows_change_time(descriptor)
    finally:
        os.close(descriptor)
    with pytest.raises(ConnectorError):
        hdf5._change_time(descriptor)


def test_unverifiable_change_time_fails_closed_during_read(run_h5, monkeypatch):
    path, _ = run_h5
    calls = []
    original = hdf5._change_time

    def flaky(descriptor):
        calls.append(descriptor)
        if len(calls) > 1:
            raise ConnectorError("The HDF5 file's change time cannot be verified", "invalid_data")
        return original(descriptor)

    monkeypatch.setattr(hdf5, "_change_time", flaky)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Polar")
    assert code(excinfo) == "invalid_data" and len(calls) == 2


def test_in_place_rewrite_with_restored_mtime_is_detected(tmp_path, monkeypatch):
    """Same inode, same size, mtime put back with os.utime: only ctime shows the change, and it is refused."""
    path = tmp_path / "inplace.h5"
    with h5py.File(path, "w") as handle:
        dataset = handle.create_dataset("t00000001/Polar", data=field(3))  # contiguous: raw bytes at one offset
        offset = dataset.id.get_offset()
    original = hdf5._read_hyperslab
    observed = {}

    def rewrite_then_read(dataset, destination, selection):
        observed["start"], observed["start_change"] = os.stat(path), native_change_time(path)
        rewrite_restoring_mtime(path, offset, np.full(4, 99.0).tobytes())
        observed["end"], observed["end_change"] = os.stat(path), native_change_time(path)
        original(dataset, destination, selection)

    monkeypatch.setattr(hdf5, "_read_hyperslab", rewrite_then_read)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00000001/Polar")
    assert code(excinfo) == "invalid_data" and "changed" in str(excinfo.value)
    start, end = observed["start"], observed["end"]
    # the mutation really kept inode, size and mtime; only the native change time moved (no platform skip)
    assert (start.st_ino, start.st_size, start.st_mtime_ns) == (end.st_ino, end.st_size, end.st_mtime_ns)
    assert observed["start_change"] != observed["end_change"]
    monkeypatch.undo()
    assert read_hdf5_image(path, "/t00000001/Polar").field("Polar").values[0, 0, 0, 0] == 99.0  # a fresh read is fine


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32", reason="POSIX symlinks")
def test_swapped_for_link_during_read_is_detected(run_h5, tmp_path, monkeypatch):
    path, _ = run_h5
    copy = tmp_path / "copy.h5"
    copy.write_bytes(path.read_bytes())
    original = hdf5._read_hyperslab

    def swap(dataset, destination, selection):
        moved = tmp_path / "moved.h5"
        os.replace(path, moved)
        path.symlink_to(moved)  # same bytes and inode behind a link
        original(dataset, destination, selection)

    monkeypatch.setattr(hdf5, "_read_hyperslab", swap)
    with pytest.raises(ConnectorError) as excinfo:
        read_hdf5_image(path, "/t00001000/Polar")
    assert code(excinfo) == "invalid_data"


def test_file_reads_through_pinned_descriptor(run_h5, tmp_path, monkeypatch):
    """The HDF5 library gets the descriptor opened once, never the path."""
    path, _ = run_h5
    opened = []
    real = h5py.File

    def record(name, *args, **kwargs):
        opened.append(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(h5py, "File", record)
    read_hdf5_image(path, "/t00001000/Polar")
    assert len(opened) == 1 and not isinstance(opened[0], (str, bytes, os.PathLike))


# --- import boundary ------------------------------------------------------------------------------


def run_python(code_text):
    env = {k: v for k, v in os.environ.items() if k != "STK_TOKEN_PLAN_MODEL"}
    env["STK_TOKEN_PLAN_API_KEY"] = ""
    result = subprocess.run([sys.executable, "-c", code_text], capture_output=True, text=True, env=env,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_passive_import():
    loaded = run_python("import json, sys\n"
                        "import suan.connectors.mupro.hdf5 as m\n"
                        # msvcrt may already be loaded by subprocess in the parent package on Windows.
                        "print(json.dumps([n for n in ('h5py', 'numpy', 'suan.data.model', 'ctypes')\n"
                        "                  if n in sys.modules]))")
    assert loaded == []


def test_missing_h5py_is_unavailable(run_h5):
    path, _ = run_h5
    result = run_python("import json, sys\n"
                        "sys.modules['h5py'] = None\n"
                        "from suan.connectors.mupro.hdf5 import read_hdf5_image\n"
                        "from suan.connectors.api import ConnectorError\n"
                        "try:\n"
                        f"    read_hdf5_image({str(path)!r}, '/t00001000/Polar')\n"
                        "except ConnectorError as exc:\n"
                        "    print(json.dumps(exc.code))\n")
    assert result == "unavailable"
