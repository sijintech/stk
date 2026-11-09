"""Actual FileSource bytes, native selectors and content-bound graph execution."""
import hashlib
import io
import os
from pathlib import Path

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")

from suan.connectors.api import ConnectorError  # noqa: E402
from suan.connectors.files import LocalFiles  # noqa: E402
from suan.connectors.mupro import source as adapter  # noqa: E402
from suan.data.manifest import check  # noqa: E402
from suan.graph.cache import GraphCache  # noqa: E402
from suan.graph.catalog import build_registry, default_registry  # noqa: E402
from suan.graph.evaluator import EvaluationFailed, evaluate  # noqa: E402
from suan.graph.registry import Budget, Cancelled  # noqa: E402
from suan.graph.resolve import LocalDirResolver  # noqa: E402


def write_file(path):
    values = np.arange(5 * 4 * 3 * 3, dtype=np.float64).reshape(5, 4, 3, 3)
    with h5py.File(path, "w") as f:
        f.create_dataset("t00000002/Polar", data=values)
        f.create_dataset("t00000004/Polar", data=(values + 1000).astype(np.float32))
    return values


def graph(selector="/t00000002/Polar", **params):
    return {"schema": "stk.graph/1", "catalog": {"stk": 1},
            "nodes": [{"id": "field", "type": "stk.source.mupro_hdf5@1",
                       "params": {"binding": "data", "selector": selector, **params}}],
            "outputs": {"field": "field.out"}}


def run(root, document=None, **kw):
    return evaluate(document or graph(), registry=default_registry(),
                    resolver=LocalDirResolver({"data": root}), **kw)


def fields_graph(path="run.h5", **params):
    return {"schema": "stk.graph/1", "catalog": {"stk": 1},
            "nodes": [{"id": "fields", "type": "stk.source.mupro_hdf5_fields@1",
                       "params": {"binding": "data", "path": path, **params}}],
            "outputs": {"fields": "fields.out"}}


def test_metadata_node_dispatches_only_the_explicit_file(tmp_path, monkeypatch):
    from suan.graph.service import MemoryBlobSink, evaluate_request

    relative = "results/muferro/example/case/run.h5"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    write_file(path)
    with h5py.File(path, "r+") as container:
        container.create_dataset("t00000002/Strain", data=np.zeros((5, 4, 3, 6), dtype=np.int16))
        container["other"] = h5py.SoftLink("/unrelated")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    opens, open_file = [], LocalFiles.open

    def open_one(source, name):
        assert name == relative
        opens.append(name)
        return open_file(source, name)

    monkeypatch.setattr(LocalFiles, "open", open_one)
    monkeypatch.setattr(LocalFiles, "list", lambda *_: pytest.fail("the node scanned its binding"))
    monkeypatch.setattr(h5py.Dataset, "__getitem__", lambda *_: pytest.fail("the node read field values"))
    result = evaluate_request({"graph": fields_graph(relative, expected_sha256=digest), "profile": "desktop"},
                              resolver=LocalDirResolver({"data": tmp_path}), cache_dir=tmp_path / "cache",
                              blob_sink=MemoryBlobSink(), registry=build_registry(entry_points=False))
    assert result["outputs"] == {"fields": {"type": "value", "value": {
        "path": relative, "sha256": digest, "size": path.stat().st_size, "reader": "mupro.hdf5@1", "fields": [
            {"selector": "/t00000002/Polar", "step": 2, "name": "Polar", "shape": [5, 4, 3, 3], "dtype": "float64"},
            {"selector": "/t00000002/Strain", "step": 2, "name": "Strain", "shape": [5, 4, 3, 6], "dtype": "int16"},
            {"selector": "/t00000004/Polar", "step": 4, "name": "Polar", "shape": [5, 4, 3, 3], "dtype": "float32"},
        ]}}}
    assert opens == [relative, relative]


def test_metadata_digest_is_required_before_cache_and_discovery(tmp_path, monkeypatch):
    path = tmp_path / "run.h5"
    write_file(path)
    before = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    pinned = fields_graph(expected_sha256=digest)
    cache_dir = tmp_path / "cache"
    first = run(tmp_path, pinned, cache=GraphCache(cache_dir))
    cached = run(tmp_path, pinned, cache=GraphCache(cache_dir))
    assert cached.evaluated == [] and cached.outputs == first.outputs

    with h5py.File(path, "r+") as container:
        container["t00000002/Polar"][0, 0, 0, 0] = 999
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    monkeypatch.setattr(adapter, "describe", lambda *_, **__: pytest.fail("the node started discovery"))
    for cache in (GraphCache(), GraphCache(cache_dir)):
        events = []
        with pytest.raises(EvaluationFailed) as raised:
            run(tmp_path, pinned, cache=cache, on_event=lambda event: events.append(event["type"]))
        error = raised.value.errors[0]
        assert error["code"] == "invalid_data" and "expected SHA-256" in error["message"]
        assert "node.started" not in events and "node.cached" not in events


def test_metadata_change_after_planning_is_refused_before_hdf5_discovery(tmp_path, monkeypatch):
    from suan.connectors.mupro import discovery

    path = tmp_path / "run.h5"
    write_file(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    def mutate(event):
        if event["type"] == "node.started":
            with h5py.File(path, "r+") as container:
                container["t00000002/Polar"][0, 0, 0, 0] = 999

    monkeypatch.setattr(discovery, "_discover_hdf5_stream", lambda *_, **__: pytest.fail("the changed file was parsed"))
    with pytest.raises(EvaluationFailed) as raised:
        run(tmp_path, fields_graph(expected_sha256=digest), on_event=mutate)
    assert raised.value.errors[0]["code"] == "invalid_data"
    assert "changed after" in raised.value.errors[0]["message"]


@pytest.mark.parametrize("params", [{}, {"expected_sha256": None}, {"expected_sha256": "A" * 64},
                                    {"expected_sha256": "a" * 63}, {"expected_sha256": "a" * 64 + "\n"}])
def test_metadata_node_rejects_missing_or_nonliteral_sha256(tmp_path, params):
    from suan.graph.schema import GraphValidationError

    with pytest.raises(GraphValidationError):
        run(tmp_path, fields_graph(**params))


def test_metadata_choice_limit_is_separate_from_visited_links(tmp_path):
    path = tmp_path / "run.h5"
    with h5py.File(path, "w") as container:
        group = container.create_group("t00000002")
        for i in range(256):
            group.create_dataset(f"Field{i:03}", data=np.zeros((1, 1, 1, 1), dtype=np.int16))
        container["other"] = h5py.SoftLink("/unrelated")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = run(tmp_path, fields_graph(expected_sha256=digest))
    assert len(result.outputs["fields"]["fields"]) == 256

    with h5py.File(path, "r+") as container:
        container["t00000002"].create_dataset("Extra", data=np.zeros((1, 1, 1, 1), dtype=np.int16))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(EvaluationFailed) as raised:
        run(tmp_path, fields_graph(expected_sha256=digest))
    error = raised.value.errors[0]
    assert error["code"] == "budget_exceeded" and "256 field choices" in error["message"]
    assert raised.value.partial.outputs == {}


def test_metadata_visited_link_limit_refuses_even_ignored_names(tmp_path):
    path = tmp_path / "run.h5"
    with h5py.File(path, "w") as container:
        for i in range(4097):
            container[f"ignored_{i:04}"] = h5py.SoftLink("/unrelated")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(EvaluationFailed) as raised:
        run(tmp_path, fields_graph(expected_sha256=digest))
    error = raised.value.errors[0]
    assert error["code"] == "budget_exceeded" and "max_entries=4096" in error["message"]
    assert raised.value.partial.outputs == {}


def test_local_source_preserves_values_metadata_and_crop(tmp_path):
    values = write_file(tmp_path / "run.h5")
    result = run(tmp_path, graph(extent=[1, 4, 0, 3, 1, 2], stride=[2, 3, 1]))
    image = result.outputs["field"]
    np.testing.assert_array_equal(image.array("Polar"), values[1:5:2, 0:4:3, 1:3].transpose(2, 1, 0, 3))
    assert image.origin == (1., 0., 1.) and image.spacing == (2., 3., 1.)
    assert image.time.step == 2 and image.time.time is None
    assert image.time.to_json()["physical"] == {"unit": "unspecified", "known": False}
    assert image.length_unit == "grid_index" and image.fields["Polar"].unit == "unspecified"
    assert image.frames[0].sources["Polar"].selector == "/t00000002/Polar"
    assert image.provenance.used == [{"path": "run.h5", "role": "input",
                                      "sha256": hashlib.sha256((tmp_path / "run.h5").read_bytes()).hexdigest()}]
    check(image.descriptor())


def test_selectors_separate_cached_frames_and_reopen_disk_cache(tmp_path):
    write_file(tmp_path / "run.h5")
    cache_dir = tmp_path / "cache"
    first = run(tmp_path, cache=GraphCache(cache_dir))
    second = run(tmp_path, graph("/t00000004/Polar"), cache=GraphCache(cache_dir))
    assert first.keys != second.keys and second.outputs["field"].time.step == 4
    assert second.outputs["field"].array("Polar").dtype == np.dtype("float32")
    again = run(tmp_path, cache=GraphCache(cache_dir))
    assert again.evaluated == [] and again.keys == first.keys
    np.testing.assert_array_equal(again.outputs["field"].array("Polar"), first.outputs["field"].array("Polar"))


def test_expected_sha256_guards_local_reads_before_using_the_cache(tmp_path):
    path = tmp_path / "run.h5"
    values = write_file(path)
    before = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    pinned = graph(expected_sha256=digest)
    cache = GraphCache(tmp_path / "cache")

    ordinary = run(tmp_path, cache=cache)
    exact = run(tmp_path, pinned, cache=cache)
    assert exact.keys == ordinary.keys and exact.evaluated == []
    assert exact.outputs["field"].provenance.used[0]["sha256"] == digest

    with h5py.File(path, "r+") as container:
        container["t00000002/Polar"][0, 0, 0, 0] = values[0, 0, 0, 0] + 999
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    events = []
    with pytest.raises(EvaluationFailed) as raised:
        run(tmp_path, pinned, cache=cache, on_event=lambda event: events.append(event["type"]))
    assert raised.value.errors[0]["code"] == "invalid_data"
    assert "expected SHA-256" in raised.value.errors[0]["message"] and "node.started" not in events

    current = run(tmp_path, cache=cache)
    assert current.keys != ordinary.keys and current.evaluated == ["field"]
    assert current.outputs["field"].array("Polar")[0, 0, 0, 0] == 999


def test_missing_reader_fails_before_graph_execution_or_source_reads(tmp_path, monkeypatch):
    from suan.connectors.mupro import hdf5

    path = tmp_path / "run.h5"
    write_file(path)
    source = LocalFiles(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    opened, events = [], []
    open_source = LocalFiles.open

    def unavailable():
        raise ConnectorError("Reading MuPRO HDF5 needs h5py and NumPy", "unavailable")

    def record_open(source, path):
        opened.append(path)
        return open_source(source, path)

    monkeypatch.setattr(hdf5, "_modules", unavailable)
    monkeypatch.setattr(LocalFiles, "open", record_open)
    with pytest.raises(EvaluationFailed) as raised:
        run(tmp_path, on_event=lambda event: events.append(event["type"]))
    assert raised.value.errors[0]["code"] == "unavailable"
    for operation in (lambda: adapter.describe(source, "run.h5", expected_sha256=digest),
                      lambda: adapter.read(source, "run.h5", "/t00000002/Polar", expected_sha256=digest)):
        with pytest.raises(ConnectorError) as error:
            operation()
        assert error.value.code == "unavailable"
    assert opened == [] and "node.started" not in events


def test_rewrite_after_planning_cannot_poison_cache(tmp_path):
    path = tmp_path / "run.h5"
    write_file(path)
    cache = GraphCache()
    before = path.stat()

    def mutate(event):
        if event["type"] == "node.started":
            with h5py.File(path, "r+") as f:
                f["t00000002/Polar"][0, 0, 0, 0] = 999
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    with pytest.raises(EvaluationFailed) as raised:
        run(tmp_path, cache=cache, on_event=mutate)
    assert raised.value.errors[0]["code"] == "invalid_data"
    assert "changed after" in raised.value.errors[0]["message"]
    assert path.stat().st_size == before.st_size
    after = run(tmp_path, cache=cache)
    assert after.outputs["field"].array("Polar")[0, 0, 0, 0] == 999
    assert after.evaluated == ["field"]


def test_file_source_without_local_path_or_trusted_hash(tmp_path, monkeypatch):
    write_file(tmp_path / "run.h5")
    data = (tmp_path / "run.h5").read_bytes()

    class Remote:
        def open(self, path):
            assert path == "run.h5"
            return io.BytesIO(data)

        def sha256(self, path):
            raise AssertionError("metadata hash memo must not be trusted")

        def local_path(self, path):
            raise AssertionError("must work with remote streams")

    planned = adapter.fingerprint(Remote(), "run.h5", "/t00000004/Polar")
    seen = []
    from suan.connectors.mupro import hdf5
    original = hdf5._read_hdf5_stream

    def observed(stream, *args, **kwargs):
        seen.append(stream)
        return original(stream, *args, **kwargs)

    monkeypatch.setattr(hdf5, "_read_hdf5_stream", observed)
    image = adapter.read(Remote(), "run.h5", planned["selector"], expected_sha256=planned["sha256"])
    assert image.time.step == 4 and seen and seen[0].closed


def test_source_limit_and_cancellation_precede_hdf5_parse(tmp_path, monkeypatch):
    write_file(tmp_path / "run.h5")
    source = LocalFiles(tmp_path)
    monkeypatch.setattr(adapter, "FILE_LIMIT", 8)
    with pytest.raises(ConnectorError) as raised:
        adapter.fingerprint(source, "run.h5", "/t00000002/Polar")
    assert raised.value.code == "budget_exceeded"

    def cancel():
        raise Cancelled("test cancellation")

    with pytest.raises(Cancelled):
        adapter.read(source, "run.h5", "/t00000002/Polar", expected_sha256="0" * 64, check=cancel)


@pytest.mark.parametrize("failure", ["hash", "parse", "cancel", "limit"])
def test_private_copy_removed_on_failed_read(tmp_path, monkeypatch, failure):
    path = tmp_path / "run.h5"
    write_file(path)
    if failure == "parse":
        path.write_bytes(b"invalid HDF5 bytes")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    if failure == "hash":
        expected = "0" * 64
    created, temporary = [], adapter.TemporaryFile

    def private_file(*args, **kwargs):
        stream = temporary(*args, dir=tmp_path, **kwargs)
        created.append(stream)
        return stream

    def cancel():
        if failure == "cancel":
            raise Cancelled("test cancellation")

    monkeypatch.setattr(adapter, "TemporaryFile", private_file)
    if failure == "limit":
        monkeypatch.setattr(adapter, "FILE_LIMIT", 8)
    with pytest.raises((Cancelled, ConnectorError)):
        adapter.read(LocalFiles(tmp_path), "run.h5", "/t00000002/Polar", expected_sha256=expected, check=cancel)
    assert created and all(stream.closed for stream in created)


def test_private_copy_does_not_survive_worker_kill(tmp_path):
    import subprocess
    import sys
    import time
    write_file(tmp_path / "run.h5")
    temporary = tmp_path / "private-temp"
    temporary.mkdir()
    ready = tmp_path / "ready"
    script = r'''
import sys, threading
from pathlib import Path
from suan.connectors.files import LocalFiles
from suan.connectors.mupro import source, hdf5
src = LocalFiles(sys.argv[1])
planned = source.fingerprint(src, "run.h5", "/t00000002/Polar")
def blocked(stream, *args, **kwargs):
    assert stream.read(8) == b"\x89HDF\r\n\x1a\n"
    Path(sys.argv[2]).write_text("ready")
    threading.Event().wait(120)
hdf5._read_hdf5_stream = blocked
source.read(src, "run.h5", "/t00000002/Polar", expected_sha256=planned["sha256"])
'''
    env = {"STK_TOKEN_PLAN_API_KEY": "", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
           "TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary)}
    for name in ("PATH", "SYSTEMROOT"):
        if name in os.environ:
            env[name] = os.environ[name]
    child = subprocess.Popen([sys.executable, "-c", script, str(tmp_path), str(ready)],
                             env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 30
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "worker must reach reading the verified private copy"
        child.kill()
        child.wait(timeout=10)
        assert list(temporary.iterdir()) == []
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)


def test_selected_array_allocation_respects_evaluation_budget(tmp_path, monkeypatch):
    import importlib
    from suan.connectors.mupro import hdf5
    # Isolate the deterministic pre-allocation limit from the independent, process-wide RSS limit.
    monkeypatch.setattr(importlib.import_module("suan.graph.evaluator"), "_rss", lambda: 0)
    monkeypatch.setattr(hdf5, "_read_hyperslab", lambda *a: pytest.fail("over-budget values were read"))
    # The selected 256*256*3*8 bytes require twice that during transpose (>1 MiB).
    with h5py.File(tmp_path / "run.h5", "w") as f:
        f.create_dataset("t00000002/Polar", data=np.zeros((256, 256, 1, 3)))
    with pytest.raises(EvaluationFailed) as raised:
        run(tmp_path, budget=Budget(max_memory_mb=1))
    assert raised.value.errors[0]["code"] == "budget_exceeded"


@pytest.mark.parametrize("selector", ["/t00000002/Polar\n", "/t00000002/Polar\r", "/t٢0000002/Polar"])
def test_node_rejects_nonliteral_selector(tmp_path, selector):
    from suan.graph.schema import GraphValidationError
    with pytest.raises(GraphValidationError):
        run(tmp_path, graph(selector))


def test_planned_fingerprint_is_copied_and_unavailable_during_fingerprinting():
    from suan.graph.registry import GraphError, Port, Registry
    registry = Registry(namespaces={"stk": 1})

    def fingerprint(ctx, inputs, params):
        with pytest.raises(GraphError, match="not available"):
            _ = ctx.source_fingerprint
        return {"nested": ["planned"]}

    @registry.node("stk.source.context", outputs=[Port("out", "value", value_type="json")],
                   fingerprint=fingerprint)
    def impl(ctx, inputs, params):
        observed = ctx.source_fingerprint
        observed["nested"][0] = "mutated"
        return ctx.source_fingerprint

    document = {"schema": "stk.graph/1", "catalog": {"stk": 1},
                "nodes": [{"id": "a", "type": "stk.source.context@1"}], "outputs": {"out": "a.out"}}
    result = evaluate(document, registry=registry, resolver={})
    assert result.outputs["out"] == {"nested": ["planned"]}
