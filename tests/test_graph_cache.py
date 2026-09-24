"""suan.graph.cache: Merkle keys, the memory LRU, the disk store, codecs, pruning and concurrency."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

np = pytest.importorskip("numpy")

from suan.data.model import (Category, CellArray, FrameRef, ImageData, PolyData, Provenance, SourceRef,  # noqa: E402
                             Table, TimeInfo)
from suan.graph.cache import (ENTRY_SCHEMA, GraphCache, canonical, data_key, estimate_nbytes, freeze,  # noqa: E402
                              full_key, plain_json, sub_key)
from suan.graph.registry import NodeType, Port, number, integer, string  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEY = "ab" + "0" * 62


def key(n):
    return f"{n:064x}"


def test_keys_are_canonical_merkle_hashes():
    inputs = {"in": ["a" * 64 + ":out"]}
    one = data_key("stk.filter.x@1", 1, {"b": 0.1, "a": [1, 2]}, inputs, {"path": "f", "sha256": "0" * 64})
    two = data_key("stk.filter.x@1", 1, {"a": [1, 2], "b": json.loads("1e-1")}, inputs,
                   {"sha256": "0" * 64, "path": "f"})
    assert one == two and len(one) == 64
    assert data_key("stk.filter.x@1", 2, {"b": 0.1, "a": [1, 2]}, inputs, {"path": "f", "sha256": "0" * 64}) != one
    assert data_key("stk.filter.x@1", 1, {"b": 0.1, "a": [1, 2]}, inputs, None) != one
    assert data_key("stk.filter.x@1", 1, {"b": -0.0}, {}, None) == data_key("stk.filter.x@1", 1, {"b": 0.0}, {}, None)
    assert full_key(one, {"opacity": 1.0}, {}) != full_key(one, {"opacity": 0.5}, {})
    assert full_key(one, {}, {"in": ["x:out"]}) != full_key(one, {}, {"in": ["y:out"]})
    assert sub_key(one, "norm") != sub_key(one, "other") != one
    # NumPy values in fingerprints hash like the Python values.
    assert canonical({"n": np.int64(3), "x": np.float32(0.5), "a": np.arange(3), "t": (1, 2)}) == \
        canonical({"n": 3, "x": 0.5, "a": [0, 1, 2], "t": [1, 2]})
    assert plain_json(Path("a") / "b") == "a/b"
    with pytest.raises(TypeError):
        plain_json({"x": object()})
    with pytest.raises(ValueError):
        canonical({"x": math.nan})


def test_param_normalization_makes_int_and_float_equal():
    node_type = NodeType("stk.filter.x", outputs=[Port("out", "dataset")],
                         params={"factor": number(1.0), "count": integer(1), "name": string("a")})
    a = node_type.normalize_params({"factor": 2, "count": 3.0})
    b = node_type.normalize_params({"count": 3, "factor": 2.0, "name": "a"})
    assert data_key(node_type.id, 1, a, {}, None) == data_key(node_type.id, 1, b, {}, None)


def image(values=None, **kw):
    values = np.arange(24, dtype=np.float64).reshape(2, 3, 4, 1) if values is None else values
    result = ImageData((4, 3, 2), origin=(1, 2, 3), spacing=(0.5, 0.5, 2), length_unit="nm", id="img",
                       time=TimeInfo(step=100, time=1.5, unit="ns"),
                       frames=[FrameRef(step=100, sources={"*": SourceRef("P.00000100.dat", reader="mupro.dat@1")}),
                               {"step": 200, "time": None, "sources": {}}],
                       provenance=Provenance(activity={"kind": "graph", "id": "g"},
                                             used=[{"path": "p", "sha256": "0" * 64}]),
                       attrs={"sample_spacing": 0.5, "nan": math.nan, "arr": np.arange(2)}, **kw)
    result.add_field("P", values, unit="C/m2", quantity="polarization", range=[[0.0, 23.0]])
    labels = (np.arange(24) % 3 - 1).astype(np.int16).reshape(2, 3, 4)
    result.add_field("domain", labels, categories=[Category(-1, "none"), Category(0, "substrate", color=(0, 0, 0)),
                                                   Category(1, "T1", direction=(1, 0, 0), color=(1, 0, 0), family="T")],
                     palette="stk:cubic-26-orientation")
    return result


def test_memory_lru_respects_the_byte_budget():
    cache = GraphCache(memory_bytes=12_000)
    for n in range(4):
        cache.put(key(n), {"a": np.zeros(400)})  # ~3.3 kB each
    assert cache.contains(key(0)) is None and cache.contains(key(3)) == "memory"
    assert cache.get(key(1)).tier == "memory"
    cache.put(key(4), {"a": np.zeros(400)})
    assert cache.contains(key(1)) == "memory" and cache.contains(key(2)) is None  # 1 was used recently
    cache.put(key(5), {"a": np.zeros(10_000)})  # larger than the whole budget: not kept
    assert cache.contains(key(5)) is None
    stats = cache.stats()["memory"]
    assert stats["bytes"] <= 12_000 and stats["entries"] == 3
    assert cache.put(key(6), {"a": 1}, disk=True) is False  # no root: memory only
    assert cache.scratch_dir(key(6)) is None
    with pytest.raises(TypeError):
        cache.put(key(7), 1)


def test_estimate_and_freeze():
    table = Table.from_columns({"x": np.arange(1000, dtype=np.float64)})
    assert estimate_nbytes(table) >= 8000
    assert estimate_nbytes({"a": np.zeros(100), "b": [b"12345"]}) >= 805
    poly = PolyData.from_triangles(np.zeros((3, 3)), np.array([[0, 1, 2]]))
    frozen = freeze({"poly": poly, "layers": [{"values": np.ones(3)}], "img": image()})
    assert not frozen["poly"].points.flags.writeable and not frozen["poly"].polys.connectivity.flags.writeable
    assert not frozen["layers"][0]["values"].flags.writeable
    assert not frozen["img"].array("domain").flags.writeable
    freeze(np.float64(1.0))  # scalars are fine

    @dataclass
    class Layer:  # e.g. a render layer object
        values: object

    layer = freeze(Layer(np.zeros(1000)))
    assert not layer.values.flags.writeable and estimate_nbytes(layer) >= 8000


def test_disk_round_trip_of_datasets_and_values(tmp_path):
    cache = GraphCache(tmp_path / "cache")
    original = image()
    poly = PolyData(np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0.0]]),
                    polys=CellArray.uniform([[0, 1, 2], [1, 3, 2]]), lines=CellArray.uniform([[0, 3]]),
                    length_unit="nm", id="mesh")
    poly.add_field("label", np.array([1, 2, 2], dtype=np.int32), association="cell",
                   categories=[{"value": 1, "name": "a"}, {"value": 2, "name": "b"}])
    poly.add_field("Normals", np.ones((4, 3), dtype=np.float32), tensor="vector")
    table = Table.from_columns({"step": np.array([0, 100]), "name": np.array(["a", "bé"], dtype=object),
                                "e": np.array([1.5, math.nan])}, units={"e": "normalized"}, index="step", id="energy")
    value = {"step": 200, "values": [1, 2.5, None], "nested": {"ok": True, "nan": math.nan}}
    blob = b"\x00\x01binary"
    array = np.arange(12, dtype=np.int16).reshape(3, 4)
    stored = {"image": original, "poly": poly, "table": table, "value": value, "blob": blob, "array": array}
    assert cache.put(KEY, stored, notes={"choices": {"step": {"value": 1, "choices": [1]}}, "warnings": []},
                     disk=True, label="test")
    entry = tmp_path / "cache" / "objects" / "ab" / KEY
    manifest = json.loads((entry / "entry.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == ENTRY_SCHEMA and manifest["key"] == KEY and manifest["label"] == "test"
    assert {p["codec"] for p in manifest["ports"].values()} == {"dataset-npz", "json", "bytes", "npy"}
    assert not list((tmp_path / "cache" / "tmp").iterdir())

    hit = GraphCache(tmp_path / "cache").get(KEY)  # a new instance reads the disk tier
    assert hit.tier == "disk" and hit.notes["choices"]["step"]["choices"] == [1]
    got = hit.value
    img = got["image"]
    assert type(img) is ImageData and img.descriptor() == original.descriptor()
    np.testing.assert_array_equal(img.array("P"), original.array("P"))
    assert img.array("domain").dtype == np.int16 and not img.array("P").flags.writeable
    assert img.fields["domain"].categories == original.fields["domain"].categories
    assert img.time.step == 100 and img.time.time == 1.5 and isinstance(img.frames[0], FrameRef)
    assert img.frames[1] == {"step": 200, "time": None, "sources": {}}
    assert math.isnan(img.attrs["nan"]) and img.attrs["arr"] == [0, 1] and img.kinds() == {"image", "labels"}
    mesh = got["poly"]
    assert type(mesh) is PolyData and mesh.descriptor() == poly.descriptor() and mesh.kinds() == {"polydata"}
    np.testing.assert_array_equal(mesh.polys.connectivity, [0, 1, 2, 1, 3, 2])
    np.testing.assert_array_equal(mesh.array("Normals"), poly.array("Normals"))
    tab = got["table"]
    assert tab.index == "step" and tab.column("name").tolist() == ["a", "bé"] and tab.column("name").dtype == object
    assert tab.fields["e"].unit == "normalized" and math.isnan(tab.column("e")[1])
    assert got["value"]["values"] == [1, 2.5, None] and math.isnan(got["value"]["nested"]["nan"])
    assert got["blob"] == blob
    np.testing.assert_array_equal(got["array"], array)
    assert GraphCache(tmp_path / "cache").contains(KEY) == "disk"
    assert GraphCache(tmp_path / "cache").notes(KEY) == hit.notes


def test_values_without_a_codec_stay_in_memory(tmp_path):
    cache = GraphCache(tmp_path / "cache")
    assert cache.put(KEY, {"layer": {"values": np.ones(3)}, "odd": object()}, disk=True) is False
    assert cache.contains(KEY) == "memory" and GraphCache(tmp_path / "cache").contains(KEY) is None
    assert cache.put(key(1), {"objects": np.array([object()])}, disk=True) is False


def test_corrupt_and_foreign_entries_are_misses(tmp_path):
    root = tmp_path / "cache"
    GraphCache(root).put(KEY, {"a": np.arange(3)}, disk=True)
    GraphCache(root).put(key(1), {"a": np.arange(3)}, disk=True)
    entry = root / "objects" / "ab" / KEY
    (entry / "00.npy").write_bytes(b"garbage")
    assert GraphCache(root).get(KEY) is None and not entry.exists()  # removed
    other = root / "objects" / key(1)[:2] / key(1)
    data = json.loads((other / "entry.json").read_text(encoding="utf-8"))
    data["ports"]["a"]["codec"] = "vtkhdf-from-the-future"
    (other / "entry.json").write_text(json.dumps(data))
    assert GraphCache(root).get(key(1)) is None and other.exists()  # kept for the codec that wrote it
    (other / "entry.json").write_text("{not json")
    assert GraphCache(root).get(key(1)) is None and not other.exists()
    assert GraphCache(root).get("not-a-key") is None


def test_pruning_is_least_recently_used(tmp_path):
    root = tmp_path / "cache"
    cache = GraphCache(root, disk_bytes=10**9)
    for n in range(5):
        cache.put(key(n), {"a": np.zeros(1000)}, disk=True)  # ~8.3 kB each
        os.utime(root / "objects" / key(n)[:2] / key(n) / "entry.json")
    cache._touch(key(0), force=True)  # key 0 used most recently
    result = cache.prune(max_bytes=3 * 8500)
    assert result["removed"] == 2 and result["freed"] > 16_000
    remaining = {n for n in range(5) if GraphCache(root).contains(key(n))}
    assert remaining == {0, 3, 4}
    assert cache.stats()["disk"]["entries"] == 3
    small = GraphCache(root, disk_bytes=20_000)  # writes prune down to 90 % of the budget automatically
    small.put(key(9), {"a": np.zeros(1000)}, disk=True)
    assert small.stats()["disk"]["bytes"] <= 20_000 and GraphCache(root).contains(key(9)) == "disk"
    # A lost index is rebuilt from the entry directories.
    (root / "index.sqlite").unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(root / "index.sqlite") + suffix).unlink(missing_ok=True)
    rebuilt = GraphCache(root)
    assert rebuilt.stats()["disk"]["entries"] == len(list((root / "objects").glob("*/*")))


def test_scratch_directories_are_counted_and_pruned(tmp_path):
    root = tmp_path / "cache"
    cache = GraphCache(root, disk_bytes=10**9)
    assert GraphCache().scratch_dir(key(1)) is None and cache.scratch_dir("../x") is None
    for n in range(3):
        directory = cache.scratch_dir(key(n))
        (directory / "exports").mkdir()
        (directory / "exports" / "a.bin").write_bytes(b"x" * 10_000)
        os.utime(directory, (1000 + n, 1000 + n))  # key 0 least recently requested
    cache.put(key(9), {"a": np.zeros(1000)}, disk=True)  # a newer disk entry (~8.3 kB)
    stats = cache.stats()
    assert stats["scratch"] == {"entries": 3, "bytes": 30_000} and stats["disk"]["entries"] == 1
    result = cache.prune(max_bytes=30_000)  # LRU across entries and scratch: key 0's scratch goes first
    assert result["removed"] == 1 and result["freed"] == 10_000
    assert not (root / "scratch" / key(0)[:2] / key(0)).exists() and GraphCache(root).contains(key(9)) == "disk"
    assert cache.stats()["scratch"]["entries"] == 2
    cache.prune(0)
    assert cache.stats()["scratch"] == {"entries": 0, "bytes": 0} and cache.stats()["disk"]["entries"] == 0
    assert list((root / "trash").iterdir()) == []
    # Scratch space counts towards the budget: a directory requested when the cache is over budget
    # triggers pruning of the older ones, and the one handed out survives.
    small = GraphCache(root, disk_bytes=15_000)
    old = small.scratch_dir(key(1))
    (old / "big.bin").write_bytes(b"y" * 20_000)
    os.utime(old, (1000, 1000))
    small._scratch_scan = (-math.inf, 0)
    fresh = small.scratch_dir(key(2))
    assert fresh.is_dir() and not old.exists()


def test_concurrent_writers_and_readers(tmp_path):
    root = tmp_path / "cache"
    value = {"a": np.arange(200_000, dtype=np.float64)}
    seen, errors = [], []

    def write():
        try:
            assert GraphCache(root).put(KEY, value, disk=True)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    def read():
        try:
            for _ in range(50):
                hit = GraphCache(root).get(KEY)
                if hit is not None:
                    seen.append(int(hit.value["a"].sum()))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(4)] + [threading.Thread(target=read) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert set(seen) <= {int(value["a"].sum())}  # never a partial entry
    assert len(list((root / "objects" / "ab").iterdir())) == 1 and not list((root / "tmp").iterdir())


def test_other_processes_see_entries(tmp_path):
    root = tmp_path / "cache"
    program = ("import sys, numpy as np; from suan.graph.cache import GraphCache; "
               "assert GraphCache(sys.argv[1]).put(sys.argv[2], {'a': np.arange(5)}, disk=True)")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-c", program, str(root), KEY], check=True, env=env)
    np.testing.assert_array_equal(GraphCache(root).get(KEY).value["a"], np.arange(5))


def test_scratch_dirs_are_private(tmp_path):
    cache = GraphCache(tmp_path / "cache")
    path = cache.scratch_dir(KEY)
    assert path == tmp_path / "cache" / "scratch" / "ab" / KEY and path.is_dir()
    assert cache.scratch_dir("../escape") is None
    if os.name == "posix":
        assert (tmp_path / "cache").stat().st_mode & 0o077 == 0
