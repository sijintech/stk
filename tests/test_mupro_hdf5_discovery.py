"""Metadata-only MuPRO HDF5 discovery (CL-MUPRO-H5-DISCOVERY-03) on real synthetic h5py files.

Every file is written with h5py, copied into an anonymous temporary file as the
caller would hold it, and listed through ``_discover_hdf5_stream``. Nothing
is stubbed except guards that prove no values are read. All data are synthetic
and well under 32 MiB.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

np = pytest.importorskip("numpy")
h5py = pytest.importorskip("h5py")

from suan.connectors.api import ConnectorError  # noqa: E402
from suan.connectors.mupro import discovery, hdf5  # noqa: E402
from suan.connectors.mupro.discovery import _discover_hdf5_stream  # noqa: E402


class Stop(Exception):
    """A caller cancellation (stands in for the graph's Cancelled)."""


def anonymous(path):
    """The caller's anonymous ordinary file holding ``path``'s bytes."""
    stream = tempfile.TemporaryFile(mode="w+b")
    stream.write(path.read_bytes())
    stream.flush()
    stream.seek(0)
    return stream


def discover(path, **kwargs):
    with anonymous(path) as stream:
        return _discover_hdf5_stream(stream, **kwargs)


def fails(path, code, **kwargs):
    with anonymous(path) as stream:
        with pytest.raises(ConnectorError) as excinfo:
            _discover_hdf5_stream(stream, **kwargs)
        assert not stream.closed
    assert excinfo.value.code == code
    assert str(path) not in str(excinfo.value) and str(path.parent) not in str(excinfo.value)
    return excinfo.value


@pytest.fixture
def run_h5(tmp_path):
    path = tmp_path / "run.h5"
    with h5py.File(path, "w") as handle:
        # written out of order on purpose; sizes differ per axis
        handle.create_dataset("t00002000/Polar", data=np.zeros((5, 4, 3, 3)))
        handle.create_dataset("t00000010/b_field", data=np.zeros((2, 3, 4, 1), dtype=">f8"))
        handle.create_dataset("t00000010/Polar", data=np.zeros((5, 4, 3, 3), dtype="float32"))
        handle.create_dataset("t00000010/Label", data=np.zeros((5, 4, 3, 1), dtype="int32"),
                              chunks=(2, 2, 3, 1), compression="gzip")
        handle.create_dataset("t00000010/Count", data=np.zeros((1, 1, 7, 2), dtype=">u2"))
        handle.attrs["solver"] = "synthetic"
    return path


EXPECTED = [
    {"selector": "/t00000010/Count", "step": 10, "name": "Count", "shape": [1, 1, 7, 2], "dtype": "uint16"},
    {"selector": "/t00000010/Label", "step": 10, "name": "Label", "shape": [5, 4, 3, 1], "dtype": "int32"},
    {"selector": "/t00000010/Polar", "step": 10, "name": "Polar", "shape": [5, 4, 3, 3], "dtype": "float32"},
    {"selector": "/t00000010/b_field", "step": 10, "name": "b_field", "shape": [2, 3, 4, 1], "dtype": "float64"},
    {"selector": "/t00002000/Polar", "step": 2000, "name": "Polar", "shape": [5, 4, 3, 3], "dtype": "float64"},
]


# --- listing ----------------------------------------------------------------------------------------


def test_lists_fields_sorted_with_native_dtypes(run_h5):
    entries = discover(run_h5)
    assert entries == EXPECTED
    assert all(isinstance(e["step"], int) and isinstance(e["shape"], list) for e in entries)
    # every selector is accepted by the reader's own selector grammar
    for entry in entries:
        assert hdf5._parse_selector(entry["selector"])[1:] == (entry["step"], entry["name"])


def test_caller_stream_stays_open_and_position_is_restored(run_h5):
    with anonymous(run_h5) as stream:
        stream.seek(17)
        assert _discover_hdf5_stream(stream) == EXPECTED
        assert not stream.closed and stream.tell() == 17
        assert _discover_hdf5_stream(stream) == EXPECTED  # still usable


def test_values_are_never_read(tmp_path, monkeypatch):
    """A field whose only chunk is garbage still lists: its values were never decoded."""
    path = tmp_path / "garbage.h5"
    with h5py.File(path, "w") as handle:
        dataset = handle.create_dataset("t00000001/Polar", data=np.arange(60.0).reshape(5, 4, 3, 1),
                                        chunks=(5, 4, 3, 1), compression="gzip")
        offset = dataset.id.get_chunk_info(0).byte_offset
    with open(path, "r+b") as stream:
        stream.seek(offset)
        stream.write(b"\xff" * 16)
    for name in ("read_direct", "__getitem__", "__array__", "astype"):
        monkeypatch.setattr(h5py.Dataset, name, lambda *a, **k: pytest.fail("dataset values were read"))
    monkeypatch.setattr(hdf5, "_read_hyperslab", lambda *a: pytest.fail("dataset values were read"))
    assert discover(path) == [{"selector": "/t00000001/Polar", "step": 1, "name": "Polar",
                               "shape": [5, 4, 3, 1], "dtype": "float64"}]


def test_unrelated_metadata_is_ignored_without_resolving(tmp_path):
    path = tmp_path / "noise.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("t00000001/Polar", data=np.zeros((2, 2, 2, 3)))
        handle.create_dataset("meta", data=np.zeros(3))
        handle.create_group("params").attrs["x"] = 1
        for name in ("t1", "T00000001", "t00000001x", "t0000000a", "t\u0661\u0660\u0660\u0660\u0660\u0660\u0660\u0660"):
            handle.create_group(name).create_dataset("Polar", data=np.zeros((2, 2, 2, 3)))
        handle["dangling_soft"] = h5py.SoftLink("/nowhere")
        handle["dangling_ext"] = h5py.ExternalLink(str(tmp_path / "absent.h5"), "/x")
        step = handle["t00000001"]
        step.create_dataset("1bad", data=np.zeros(4))
        step.create_dataset("_hidden", data=np.zeros((2, 2, 2, 1)))
        step.create_dataset("with.dot", data=np.zeros((2, 2, 2, 1)))
        step.create_dataset("x" * 65, data=np.zeros((2, 2, 2, 1)))
        step.create_dataset("P\u00f6lar", data=np.zeros((2, 2, 2, 1)))
        step["link_bad.name"] = h5py.SoftLink("/nowhere")
        step.attrs["note"] = "ignored"
    assert [e["selector"] for e in discover(path)] == ["/t00000001/Polar"]


def test_empty_file_lists_nothing(tmp_path):
    path = tmp_path / "empty.h5"
    with h5py.File(path, "w") as handle:
        handle.create_group("t00000005")
    assert discover(path) == []


# --- refusal of recognized but invalid entries -------------------------------------------------------


def test_recognized_step_group_must_be_a_hard_group(tmp_path):
    path = tmp_path / "steps.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("data/Polar", data=np.zeros((2, 2, 2, 3)))
        handle["t00000001"] = h5py.SoftLink("/data")
    assert "soft or external" in str(fails(path, "invalid_data"))
    path2 = tmp_path / "steps2.h5"
    with h5py.File(path2, "w") as handle:
        handle["t00000001"] = h5py.ExternalLink(str(tmp_path / "absent.h5"), "/t00000001")
    fails(path2, "invalid_data")
    path3 = tmp_path / "steps3.h5"
    with h5py.File(path3, "w") as handle:
        handle.create_dataset("t00000001", data=np.zeros((2, 2, 2, 1)))
    assert "wrong object type" in str(fails(path3, "invalid_data"))


def test_recognized_field_links_and_kinds_refused(tmp_path):
    target = tmp_path / "target.h5"
    with h5py.File(target, "w") as handle:
        handle.create_dataset("t00000001/Polar", data=np.zeros((2, 2, 2, 3)))
    cases = {
        "soft": lambda g, f: g.__setitem__("Polar", h5py.SoftLink("/elsewhere/Polar")),
        "external": lambda g, f: g.__setitem__("Polar", h5py.ExternalLink(str(target), "/t00000001/Polar")),
        "group": lambda g, f: g.create_group("Polar"),
    }
    for label, build in cases.items():
        path = tmp_path / f"field-{label}.h5"
        with h5py.File(path, "w") as handle:
            handle.create_dataset("elsewhere/Polar", data=np.zeros((2, 2, 2, 3)))
            build(handle.create_group("t00000001"), handle)
        error = fails(path, "invalid_data")
        assert str(target) not in str(error)


def write_field(path, **kwargs):
    with h5py.File(path, "w") as handle:
        handle.create_group("t00000001").create_dataset("Polar", **kwargs)
    return path


@pytest.mark.parametrize("kwargs", [
    {"data": np.zeros((2, 2, 2))},
    {"data": np.zeros((2, 2, 2, 1, 1))},
    {"data": np.zeros((2, 0, 2, 1))},
    {"data": np.zeros((2, 2, 2, 1), dtype=bool)},
    {"data": np.zeros((2, 2, 2, 1), dtype=np.float16)},
    {"data": np.zeros((2, 2, 2, 1), dtype=np.complex64)},
    {"data": np.zeros((2, 2, 2, 1), dtype="S3")},
    {"data": np.zeros((2, 2, 2, 1), dtype=[("a", "f8")])},
    {"shape": (2, 2, 2, 1), "dtype": "f8"},  # never written: no storage
], ids=["3d", "5d", "zero", "bool", "float16", "complex", "bytes", "compound", "unallocated"])
def test_invalid_shape_type_or_storage_refused(tmp_path, kwargs):
    fails(write_field(tmp_path / "bad.h5", **kwargs), "invalid_data")


def test_partly_written_chunks_refused(tmp_path):
    path = tmp_path / "partial.h5"
    with h5py.File(path, "w") as handle:
        dataset = handle.create_group("t00000001").create_dataset("Polar", shape=(4, 4, 2, 1), dtype="f8",
                                                                   chunks=(2, 2, 2, 1))
        dataset[0:2, 0:2] = 1.0
    assert "partly written" in str(fails(path, "invalid_data"))


def test_vds_and_external_raw_refused(tmp_path):
    source = tmp_path / "source.h5"
    with h5py.File(source, "w") as handle:
        handle.create_dataset("data", data=np.zeros((2, 2, 2, 1)))
    vds = tmp_path / "vds.h5"
    layout = h5py.VirtualLayout(shape=(2, 2, 2, 1), dtype="f8")
    layout[...] = h5py.VirtualSource(str(source), "data", shape=(2, 2, 2, 1))
    with h5py.File(vds, "w") as handle:
        handle.create_group("t00000001").create_virtual_dataset("Polar", layout)
    assert "Virtual" in str(fails(vds, "invalid_data"))
    raw = tmp_path / "raw.bin"
    raw.write_bytes(np.zeros(8).tobytes())
    external = write_field(tmp_path / "external.h5", shape=(2, 2, 2, 1), dtype="f8",
                           external=[(str(raw), 0, h5py.h5f.UNLIMITED)])
    error = fails(external, "invalid_data")
    assert "external raw storage" in str(error) and str(raw) not in str(error)


def test_unknown_filter_refused(tmp_path):
    from h5py import h5d, h5p, h5s, h5t, h5z
    path = tmp_path / "plugin.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("t00000001")
        plist = h5p.create(h5p.DATASET_CREATE)
        plist.set_chunk((2, 2, 2, 1))
        plist.set_filter(32004, h5z.FLAG_OPTIONAL, ())
        dataset = h5py.Dataset(h5d.create(group.id, b"Polar", h5t.IEEE_F64LE, h5s.create_simple((2, 2, 2, 1)),
                                          dcpl=plist))
        dataset[...] = 1.0
    assert "filter" in str(fails(path, "invalid_data"))


def test_one_bad_field_rejects_the_whole_listing(run_h5, tmp_path):
    path = tmp_path / "mixed.h5"
    path.write_bytes(run_h5.read_bytes())
    with h5py.File(path, "r+") as handle:
        handle["t00002000"].create_dataset("Broken", data=np.zeros(3))
    fails(path, "invalid_data")


# --- budget and cancellation ------------------------------------------------------------------------


def budget_file(tmp_path, junk_root=5, fields=2):
    path = tmp_path / "budget.h5"
    with h5py.File(path, "w") as handle:
        step = handle.create_group("t00000001")
        for i in range(fields):
            step.create_dataset(f"F{i}", data=np.zeros((1, 1, 1, 1)))
        for i in range(junk_root):
            handle.create_group(f"junk{i}")
    return path


def test_entry_budget_counts_ignored_names(tmp_path):
    path = budget_file(tmp_path)  # 6 root links (1 step + 5 ignored) + 2 fields = 8 visits
    assert len(discover(path, max_entries=8)) == 2
    error = fails(path, "budget_exceeded", max_entries=7)
    assert "max_entries=7" in str(error)
    fails(path, "budget_exceeded", max_entries=5)  # the root listing alone is over budget


def test_budget_checked_before_iterating_names(tmp_path, monkeypatch):
    path = budget_file(tmp_path, junk_root=300, fields=1)
    visited = []

    def check():
        visited.append(1)

    fails(path, "budget_exceeded", max_entries=50, check=check)
    assert visited == []  # refused from the link count, before any name was iterated


@pytest.mark.parametrize("value", [0, -1, True, False, 1.5, "10", None])
def test_invalid_budget(run_h5, value):
    fails(run_h5, "invalid_param", max_entries=value)


def test_check_is_called_and_cancellation_propagates(run_h5):
    calls = []
    assert discover(run_h5, check=lambda: calls.append(1)) == EXPECTED
    assert len(calls) >= 2 + 5  # at least once per visited link

    seen = []

    def cancel():
        seen.append(1)
        if len(seen) == 3:
            raise Stop("cancelled by caller")

    with anonymous(run_h5) as stream:
        stream.seek(5)
        with pytest.raises(Stop):
            _discover_hdf5_stream(stream, check=cancel)
        assert not stream.closed and stream.tell() == 5


def test_invalid_check_argument(run_h5):
    fails(run_h5, "invalid_param", check="not callable")


# --- stream, corruption and change guards ------------------------------------------------------------


def test_stream_must_be_an_open_ordinary_file(run_h5):
    import io
    with pytest.raises(ConnectorError) as excinfo:
        _discover_hdf5_stream(io.BytesIO(run_h5.read_bytes()))
    assert excinfo.value.code == "invalid_param"
    stream = anonymous(run_h5)
    stream.close()
    with pytest.raises(ConnectorError) as excinfo:
        _discover_hdf5_stream(stream)
    assert excinfo.value.code == "invalid_param"
    if hasattr(os, "pipe"):
        read_end, write_end = os.pipe()
        try:
            with os.fdopen(read_end, "rb", buffering=0) as pipe:
                with pytest.raises(ConnectorError) as excinfo:
                    _discover_hdf5_stream(pipe)
                assert excinfo.value.code in ("invalid_data", "invalid_param")
        finally:
            os.close(write_end)


def test_damaged_files(tmp_path, run_h5):
    junk = tmp_path / "junk.h5"
    junk.write_bytes(b"not hdf5 " * 50)
    assert fails(junk, "invalid_data").args[0] == "The file is not a readable HDF5 file"
    truncated = tmp_path / "truncated.h5"
    truncated.write_bytes(run_h5.read_bytes()[:900])
    fails(truncated, "invalid_data")
    empty = tmp_path / "zero.h5"
    empty.write_bytes(b"")
    fails(empty, "invalid_data")


def test_in_place_rewrite_with_restored_mtime_detected(run_h5):
    with anonymous(run_h5) as stream:
        start = os.fstat(stream.fileno())
        before_change = hdf5._change_time(stream.fileno())
        rewritten = []

        def rewrite():
            """Rewrite one byte in place with its own value, then put mtime back: only the change time moves."""
            if not rewritten:
                rewritten.append(1)
                time.sleep(0.05)  # past coarse timestamp granularity
                position = stream.tell()
                stream.seek(start.st_size - 1)
                last = stream.read(1)
                stream.seek(start.st_size - 1)
                stream.write(last)
                stream.flush()
                stream.seek(position)
                os.utime(stream.fileno() if os.utime in os.supports_fd else stream.name,
                         ns=(start.st_atime_ns, start.st_mtime_ns))

        with pytest.raises(ConnectorError) as excinfo:
            _discover_hdf5_stream(stream, check=rewrite)
        after = os.fstat(stream.fileno())
        assert excinfo.value.code == "invalid_data" and "changed" in str(excinfo.value)
        assert (after.st_size, after.st_mtime_ns) == (start.st_size, start.st_mtime_ns)
        assert hdf5._change_time(stream.fileno()) != before_change  # only the change time moved


def test_append_during_listing_detected(run_h5):
    with anonymous(run_h5) as stream:
        grown = []

        def grow():
            if not grown:
                grown.append(1)
                position = stream.tell()
                stream.seek(0, os.SEEK_END)
                stream.write(b"appended")
                stream.flush()
                stream.seek(position)

        with pytest.raises(ConnectorError) as excinfo:
            _discover_hdf5_stream(stream, check=grow)
        assert excinfo.value.code == "invalid_data"


def test_unverifiable_change_time_fails_closed(run_h5, monkeypatch):
    calls = []
    original = hdf5._change_time

    def flaky(descriptor):
        calls.append(1)
        if len(calls) > 1:
            raise ConnectorError("The HDF5 file's change time cannot be verified", "invalid_data")
        return original(descriptor)

    monkeypatch.setattr(hdf5, "_change_time", flaky)
    fails(run_h5, "invalid_data")
    assert len(calls) == 2


# --- import boundary ---------------------------------------------------------------------------------


def run_python(code):
    env = {k: v for k, v in os.environ.items() if k != "STK_TOKEN_PLAN_MODEL"}
    env["STK_TOKEN_PLAN_API_KEY"] = ""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_passive_import():
    loaded = run_python("import json, sys\n"
                        "import suan.connectors.mupro.discovery\n"
                        "print(json.dumps([n for n in ('h5py', 'numpy', 'ctypes', 'suan.connectors.mupro.hdf5')"
                        " if n in sys.modules]))")
    assert loaded == []


def test_missing_h5py_is_unavailable(run_h5):
    result = run_python("import json, sys, tempfile\n"
                        "sys.modules['h5py'] = None\n"
                        "from suan.connectors.mupro.discovery import _discover_hdf5_stream\n"
                        "from suan.connectors.api import ConnectorError\n"
                        "with tempfile.TemporaryFile() as s:\n"
                        "    try:\n"
                        "        _discover_hdf5_stream(s)\n"
                        "    except ConnectorError as exc:\n"
                        "        print(json.dumps(exc.code))\n")
    assert result == "unavailable"


def test_module_exports_no_public_registration():
    assert discovery.__all__ == ["DEFAULT_MAX_ENTRIES"]
