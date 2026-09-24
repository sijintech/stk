"""Fast field DAT reader/writer (suan.data.dat) against the historical read_field parser."""
from pathlib import Path
import os
import time
import tracemalloc

import pytest

np = pytest.importorskip("numpy")

from mupro_fake import _frame, write_outputs  # noqa: E402
from suan.data import dat  # noqa: E402
from suan.data.dat import (DatError, dat_info, frame_name, read_dat, read_dat_image, read_header,  # noqa: E402
                           write_dat)
from toolkits.sviz.field import read_field  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PELOOP = ROOT / "toolkits/sviz/test/PELOOP.00001000.dat"


def legacy_read_dat(path):
    """The DAT branch of toolkits.sviz.field.read_field before it delegated to suan.data.dat."""
    with open(path, encoding="utf-8") as stream:
        first = stream.readline()
        try:
            dimensions = tuple(map(int, first.split("!", 1)[0].split()))
        except ValueError:
            raise ValueError("Not a regular-grid field DAT: the first line must hold 3–5 integer dimensions "
                             "(tables such as energy_out.dat are time series)") from None
        if not 3 <= len(dimensions) <= 5 or any(n < 1 for n in dimensions):
            raise ValueError("DAT header must contain 3–5 positive dimensions")
        rows = np.loadtxt(stream, ndmin=2)
    coordinates = len(dimensions)
    shape = dimensions[:3]
    if rows.shape[0] != int(np.prod(dimensions)) or rows.shape[1] <= coordinates:
        raise ValueError("DAT point count or component count does not match the header")
    coords = rows[:, :coordinates].astype(int) - 1
    if not np.array_equal(coords + 1, rows[:, :coordinates]) or (coords < 0).any() \
            or (coords >= np.array(dimensions)).any():
        raise ValueError("DAT indices must be integral, one-based and inside dimensions")
    if len(np.unique(coords, axis=0)) != len(coords):
        raise ValueError("DAT contains duplicate or missing grid points")
    if coordinates == 3:
        data = np.empty(shape + (rows.shape[1] - 3,))
        data[coords[:, 0], coords[:, 1], coords[:, 2]] = rows[:, 3:]
    else:
        if rows.shape[1] != coordinates + 1:
            raise ValueError("Indexed component DAT requires one value per index tuple")
        tensor = np.empty(dimensions)
        tensor[tuple(coords[:, i] for i in range(coordinates))] = rows[:, -1]
        data = tensor.reshape(shape + (int(np.prod(dimensions[3:])),))
    return data


@pytest.fixture
def fast_only(monkeypatch):
    """Fail if the general (whitespace-token) parser is used."""
    def general(*args):
        raise AssertionError("the fixed-width path was not taken")
    monkeypatch.setattr(dat, "_read_general", general)


def same(fast, legacy):
    return fast.shape == legacy.shape and fast.tobytes() == np.ascontiguousarray(legacy).tobytes()


def test_fast_reader_equals_legacy_on_fake_muferro_frames(tmp_path, fast_only):
    write_outputs(tmp_path, grid=(5, 4, 3), steps=2, interval=1)
    frames = sorted(tmp_path.glob("*.dat"))
    frames = [f for f in frames if f.name != "energy_out.dat"]
    assert {f.name.split(".")[0] for f in frames} >= {"Polar", "Charges", "Strain"}
    for frame in frames:
        legacy = legacy_read_dat(frame)
        assert same(read_dat(frame, layout="xyzc"), legacy), frame.name
        zyxc = read_dat(frame)
        assert zyxc.flags.c_contiguous and same(np.ascontiguousarray(zyxc.transpose(2, 1, 0, 3)), legacy)
        # Chunks of single lines, decoded by several threads, give the same array.
        assert same(read_dat(frame, layout="xyzc", chunk_bytes=1, threads=3), legacy)
    polar = read_dat(tmp_path / "Polar.00000002.dat", layout="xyzc")
    # mupro_fake: value at one-based (i, j, k, c) is i + 10 j + 100 k + 1000 c + step.
    assert polar[4, 3, 2].tolist() == [5 + 40 + 300 + 1000 * c + 2 for c in (1, 2, 3)]


def test_fast_reader_equals_legacy_on_peloop(fast_only):
    legacy = legacy_read_dat(PELOOP)
    fast = read_dat(PELOOP, layout="xyzc")
    assert fast.shape == (64, 1, 150, 6) and same(fast, legacy)
    assert np.abs(fast).max() > 0 and (fast[:, :, 0] == 0).all()  # zero substrate layer, E+000 exponents
    header = read_header(PELOOP)
    assert header.dimensions == (64, 1, 150) and header.grid == (64, 1, 150) and header.comment is None
    assert dat_info(PELOOP) == {"dimensions": [64, 1, 150], "components": 6, "index_columns": 3,
                                "header": [64, 1, 150], "comment": None}


def test_read_field_delegates_and_keeps_values(tmp_path):
    assert same(read_field(PELOOP), legacy_read_dat(PELOOP))
    write_outputs(tmp_path, grid=(3, 2, 2), steps=1, interval=1)
    frame = tmp_path / "Polar.00000001.dat"
    data = read_field(frame)
    assert data.flags.c_contiguous and data.dtype == np.float64 and same(data, legacy_read_dat(frame))


ERROR_CASES = [
    ("      step    Elastic Energy\nkt: 1 energy: 1.0 2.0\n", "Not a regular-grid field DAT"),
    ("kt:      1 energy:   0.1000000000E+01\n", "Not a regular-grid field DAT"),
    ("2 2\n1 1 1\n", "DAT header must contain 3–5 positive dimensions"),
    ("2 0 1\n1 1 1 1\n", "DAT header must contain 3–5 positive dimensions"),
    ("2 1 1\n1 1 1 3\n", "DAT point count or component count does not match the header"),
    ("2 1 1\n1 1 1\n2 1 1\n", "DAT point count or component count does not match the header"),
    ("2 1 1\n1 1 1 3\n3 1 1 4\n", "DAT indices must be integral, one-based and inside dimensions"),
    ("2 1 1\n1 1 1 3\n1.5 1 1 4\n", "DAT indices must be integral, one-based and inside dimensions"),
    ("2 1 1\n1 1 1 3\n1 1 1 4\n", "DAT contains duplicate or missing grid points"),
    ("1 1 1 2\n1 1 1 1 3 4\n1 1 1 2 5 6\n", "Indexed component DAT requires one value per index tuple"),
    # Fixed-width variants of the same errors (the fast path must report them identically).
    ("     2     1     1\n     1     1     1  3.0000000E+000\n     1     1     1  4.0000000E+000\n",
     "DAT contains duplicate or missing grid points"),
    ("     2     1     1\n     1     1     1  3.0000000E+000\n     3     1     1  4.0000000E+000\n",
     "DAT indices must be integral, one-based and inside dimensions"),
    ("     2     1     1     1\n     1     1     1     1  3.0000000E+000\n     1     1     1     1  4.0000000E+000\n",
     "DAT contains duplicate or missing grid points"),
]


@pytest.mark.parametrize("text,message", ERROR_CASES)
def test_errors_match_read_field(tmp_path, text, message):
    path = tmp_path / "bad.dat"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        legacy_read_dat(path)
    with pytest.raises(DatError, match=message):
        read_dat(path)
    with pytest.raises(ValueError, match=message):
        read_field(path)


def test_value_parse_errors_propagate_like_loadtxt(tmp_path):
    path = tmp_path / "bad.dat"
    path.write_text("     2     1     1\n     1     1     1  3.0000000E+000\n     2     1     1  4.00x0000E+000\n")
    with pytest.raises(ValueError) as legacy:
        legacy_read_dat(path)
    with pytest.raises(ValueError) as fast:
        read_dat(path)
    assert type(fast.value) is type(legacy.value) and str(fast.value) == str(legacy.value)


def test_header_variants_and_exponent_styles(tmp_path, fast_only):
    rng = np.random.default_rng(7)
    data = rng.standard_normal((4, 3, 5, 3)) * 10.0 ** rng.integers(-12, 12, size=(4, 3, 5, 3))
    data[0, 0, 0] = [0.0, -0.0, 1e-30]
    for kwargs in [{}, {"exponent_char": "D"}, {"exponent_digits": 2}, {"comment": "comment: nx ny nz"},
                   {"component_shape": ()}, {"digits": 12}, {"trailing_space": False},
                   {"newline": "\r\n"}, {"pad_header": False}]:
        path = write_dat(tmp_path / "field.dat", data, **kwargs)
        text = path.read_text()
        legacy = legacy_read_dat(path) if kwargs.get("exponent_char") != "D" else \
            legacy_read_dat(_d_to_e(path, tmp_path / "e.dat"))
        assert same(read_dat(path, layout="xyzc"), legacy), kwargs
        if "comment" in kwargs:
            assert read_header(path).comment == "comment: nx ny nz" and "!" in text.splitlines()[0]
        if kwargs.get("exponent_char") == "D":
            assert "D+" in text or "D-" in text
    # Five index columns: 'nx ny nz 2 3' with 'i j k a b v' rows; component = a * 3 + b.
    tensor = np.arange(4 * 3 * 2 * 6, dtype=float).reshape(4, 3, 2, 6) / 8
    path = write_dat(tmp_path / "tensor.dat", tensor, component_shape=(2, 3))
    assert read_header(path).dimensions == (4, 3, 2, 2, 3)
    assert dat_info(path)["components"] == 6
    assert same(read_dat(path, layout="xyzc"), legacy_read_dat(path)) and same(read_dat(path, layout="xyzc"), tensor)


def _d_to_e(source, target):
    target.write_text(source.read_text().replace("D", "E"))
    return target


def test_last_line_without_break_and_trailing_blank_lines(tmp_path, fast_only):
    data = np.arange(24, dtype=float).reshape(2, 3, 4, 1) * 1.25
    path = write_dat(tmp_path / "f.dat", data)
    text = path.read_text()
    for variant in (text.rstrip("\n"), text.rstrip(" \n"), text + "\n\n  \n"):
        path.write_text(variant)
        assert same(read_dat(path, layout="xyzc"), data)


def test_unordered_rows_and_general_fallback(tmp_path):
    data = np.arange(5 * 4 * 3 * 3, dtype=float).reshape(5, 4, 3, 3) - 17.5
    path = write_dat(tmp_path / "f.dat", data)
    header, *rows = path.read_text().splitlines()
    rng = np.random.default_rng(3)
    order = rng.permutation(len(rows))
    shuffled = tmp_path / "shuffled.dat"
    shuffled.write_text("\n".join([header] + [rows[i] for i in order]) + "\n")
    for kwargs in ({}, {"chunk_bytes": 1, "threads": 1}, {"chunk_bytes": 200, "threads": 4}):
        assert same(read_dat(shuffled, layout="xyzc", **kwargs), data)
    # Only a few chunks out of order: in-order chunks are placed directly, the others scattered.
    swapped = list(range(len(rows)))
    swapped[40], swapped[100] = swapped[100], swapped[40]
    partly = tmp_path / "partly.dat"
    partly.write_text("\n".join([header] + [rows[i] for i in swapped]) + "\n")
    assert same(read_dat(partly, layout="xyzc", chunk_bytes=1), data)
    duplicate = list(swapped)
    duplicate[100] = duplicate[5]
    partly.write_text("\n".join([header] + [rows[i] for i in duplicate]) + "\n")
    with pytest.raises(DatError, match="duplicate or missing"):
        read_dat(partly, chunk_bytes=1, threads=2)
    # Free format (variable widths, comments, blank lines): the general parser.
    free = tmp_path / "free.dat"
    free.write_text("5 4 3 3 ! comment\n# a comment\n\n" + "".join(
        f"{i + 1} {j + 1} {k + 1} {c + 1} {float(data[i, j, k, c])!r}\n"
        for i, j, k, c in np.ndindex(5, 4, 3, 3)))
    assert same(read_dat(free, layout="xyzc"), data) and same(read_field(free), legacy_read_dat(free))


def test_non_finite_values(tmp_path):
    data = np.ones((2, 2, 2, 1))
    data[1, 1, 1, 0] = np.nan
    data[0, 1, 0, 0] = -np.inf
    path = write_dat(tmp_path / "nan.dat", data)
    values = read_dat(path, layout="xyzc")
    assert np.isnan(values[1, 1, 1, 0]) and values[0, 1, 0, 0] == -np.inf and values[0, 0, 0, 0] == 1
    with pytest.raises(ValueError, match="Expected a finite numeric"):
        read_field(path)


def test_writer_matches_muferro_bytes(tmp_path):
    grid = (4, 3, 2)
    _frame(tmp_path / "Polar.00000004.dat", grid, 3, 4)
    _frame(tmp_path / "Charges.00000004.dat", grid, 1, 4, scalar=True)
    i, j, k = np.meshgrid(*[np.arange(1, n + 1) for n in grid], indexing="ij")
    base = (i + 10 * j + 100 * k + 4).astype(float)
    polar = np.stack([base + 1000 * c for c in (1, 2, 3)], axis=3)
    write_dat(tmp_path / "polar.dat", polar)
    write_dat(tmp_path / "charges.dat", base + 1000)
    assert (tmp_path / "polar.dat").read_bytes() == (tmp_path / "Polar.00000004.dat").read_bytes()
    assert (tmp_path / "charges.dat").read_bytes() == (tmp_path / "Charges.00000004.dat").read_bytes()
    # zyxc input is written in the same (x slowest) order.
    write_dat(tmp_path / "zyxc.dat", np.ascontiguousarray(polar.transpose(2, 1, 0, 3)), layout="zyxc")
    assert (tmp_path / "zyxc.dat").read_bytes() == (tmp_path / "polar.dat").read_bytes()
    with pytest.raises(ValueError):
        write_dat(tmp_path / "x.dat", polar, component_shape=(2,))


def test_float32_and_image(tmp_path):
    write_outputs(tmp_path, grid=(4, 3, 2), steps=2, interval=2)
    path = tmp_path / "Polar.00000002.dat"
    assert frame_name(path) == ("Polar", 2) and frame_name("energy_out.dat") == (None, None)
    image = read_dat_image(path, tensor="vector", component_names=("x", "y", "z"), quantity="polarization")
    assert image.id == "Polar" and image.dimensions == (4, 3, 2) and image.time.step == 2
    assert image.length_unit == "grid_index" and image.spacing == (1.0, 1.0, 1.0)
    field = image.field("Polar")
    assert field.unit == "unspecified" and field.tensor == "vector" and field.components == 3
    assert same(np.ascontiguousarray(image.xyz("Polar")), legacy_read_dat(path))
    single = read_dat_image(path, dtype="float32", name="P", spacing=(0.5, 0.5, 1), step=7)
    assert single.field("P").lossy and single.field("P").dtype == "float32" and single.time.step == 7
    np.testing.assert_array_equal(single.array("P"), image.array("Polar").astype(np.float32))
    with pytest.raises(ValueError):
        read_dat(path, layout="xzyc")


def test_chunked_parse_bounds_memory(tmp_path):
    data = np.random.default_rng(0).standard_normal((32, 32, 32, 3))
    path = write_dat(tmp_path / "big.dat", data)  # 98304 rows, about 4 MB of text
    output_bytes = data.nbytes
    tracemalloc.start()
    try:
        values = read_dat(path, chunk_bytes=64 * 1024, threads=1)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert values.shape == (32, 32, 32, 3)
    assert peak < output_bytes + 2 * 1024 * 1024, peak  # the text is never held whole
    assert path.stat().st_size > 3 * 1024 * 1024


def test_header_promising_huge_grids_fails_before_allocating(tmp_path):
    # 124 bytes whose header promises 30 000 000 z points: the size check comes before any index table.
    bomb = tmp_path / "bomb.dat"
    bomb.write_text("1 1 1 30000000 1\n" + "".join(str(1).rjust(18) for _ in range(5)) + "  1.0000000E+000\n")
    tracemalloc.start()
    try:
        with pytest.raises(DatError, match="does not match the header"):
            read_dat(bomb)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 16 * 1024 * 1024, peak


def test_general_parser_streams_lines_with_fortran_exponents_and_old_line_breaks(tmp_path):
    data = np.arange(3 * 2 * 2 * 3, dtype=float).reshape(3, 2, 2, 3) * 1.5e-3 - 0.25
    text = "3 2 2 3\n# free format\n" + "".join(
        f"{i + 1} {j + 1} {k + 1} {c + 1}   {float(data[i, j, k, c]):.16E}\n".replace("E", "D" if c else "d")
        for i, j, k, c in np.ndindex(3, 2, 2, 3))
    for newline in ("\n", "\r\n", "\r"):
        path = tmp_path / "free.dat"
        path.write_bytes(text.replace("\n", newline).encode())
        assert same(read_dat(path, layout="xyzc"), data), repr(newline)
    rows = 200_000
    big = tmp_path / "big-free.dat"
    with open(big, "w") as stream:
        stream.write(f"{rows} 1 1\n# free\n")
        stream.writelines(f"{n + 1} 1 1 {n * 0.5:.6f}\n" for n in range(rows))
    tracemalloc.start()  # the fallback streams the text into loadtxt: no whole-file string copies
    try:
        values = read_dat(big, layout="xyzc")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert values.shape == (rows, 1, 1, 1) and values[-1, 0, 0, 0] == (rows - 1) * 0.5
    assert peak < 5 * big.stat().st_size, (peak, big.stat().st_size)  # a whole-file StringIO needed > 37 MB


@pytest.mark.skipif(os.environ.get("STK_PERF") != "1", reason="performance benchmark: set STK_PERF=1")
def test_perf_128_cubed_parse(tmp_path):
    """Milestone-1 target: a 128^3 x 3 muFerro Polar frame parses in <= 2 s (x STK_PERF_FACTOR)."""
    data = np.random.default_rng(1).standard_normal((128, 128, 128, 3)) * 0.3
    path = write_dat(tmp_path / "Polar.00000100.dat", data)
    started = time.perf_counter()
    values = read_dat(path)
    elapsed = time.perf_counter() - started
    assert values.shape == (128, 128, 128, 3)
    assert elapsed <= 2.0 * float(os.environ.get("STK_PERF_FACTOR", "1")), elapsed
