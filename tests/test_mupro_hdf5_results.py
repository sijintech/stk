"""MuPRO HDF5 discovery, coexistence with DAT and content-bound result observations."""
import hashlib
import os
from urllib.parse import parse_qs, urlsplit

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")

from mupro_fake import write_case, write_outputs  # noqa: E402
from suan.connectors.api import ConnectorError, DatasetHandle  # noqa: E402
from suan.connectors.files import LocalFiles, MissingFile, RuntimeFiles  # noqa: E402
from suan.connectors.mupro import MuFerroConnector, frame_rows  # noqa: E402
from suan.connectors.mupro import source as adapter  # noqa: E402
from suan.data.manifest import check, validate_result  # noqa: E402
from suan.graph.cache import GraphCache  # noqa: E402
from suan.graph.catalog import build_registry  # noqa: E402
from suan.graph.evaluator import EvaluationFailed, evaluate  # noqa: E402
from suan.graph.resolve import LocalDirResolver, RuntimeResolver  # noqa: E402
from suan.runtime.client import RuntimeClient  # noqa: E402
from test_connectors_muferro import FakeClient  # noqa: E402


def write_hdf5(path, grid=(4, 3, 2)):
    values = np.arange(np.prod(grid) * 3, dtype=np.float32).reshape(*grid, 3)
    with h5py.File(path, "w") as file:
        file.create_dataset("t00000002/Polar", data=values)
        file.create_dataset("t00000004/Polar", data=values + 100)
        file.create_dataset("t00000004/Strain", data=np.ones((*grid, 6), dtype="int16"))
    return values


def result_graph():
    return {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}}],
        "outputs": {"result": "run.result", "frames": "run.frames"}}


def evaluate_result(root, **kwargs):
    # Catalog tests reload built-ins; do not reuse an earlier module's functions.
    return evaluate(result_graph(), registry=build_registry(entry_points=False),
                    resolver=LocalDirResolver({"run": root}), **kwargs)


def test_hdf5_and_dat_are_distinct_and_read_with_native_metadata(tmp_path):
    write_case(tmp_path)
    write_outputs(tmp_path)
    values = write_hdf5(tmp_path / "run.h5")
    source = LocalFiles(tmp_path)
    connector = MuFerroConnector()
    result = connector.describe(source)
    assert validate_result(result) == []
    assert result["complete"] and result["verification"]["status"] == "passed"
    by_id = {dataset["id"]: dataset for dataset in result["datasets"]}
    assert {"Polar", "Strain", "hdf5:Polar", "hdf5:Strain"} <= set(by_id)
    hdf5 = by_id["hdf5:Polar"]
    assert hdf5["geometry"]["dimensions"] == [4, 3, 2]
    assert hdf5["fields"][0]["dtype"] == "float32" and hdf5["fields"][0]["unit"] == "unspecified"
    assert by_id["hdf5:Strain"]["fields"][0]["tensor"] == "array"
    rows = [row for row in frame_rows(result) if row["dataset"] == "hdf5:Polar"]
    assert [row["selector"] for row in rows] == ["/t00000002/Polar", "/t00000004/Polar"]
    digest = hashlib.sha256((tmp_path / "run.h5").read_bytes()).hexdigest()
    assert all(row["sha256"] == digest for row in rows)
    assert next(file for file in result["files"] if file["path"] == "run.h5")["role"] == "output"
    handle = connector.open(source, "hdf5:Polar", result=result)
    assert isinstance(handle, DatasetHandle)
    image = handle.read(frame={"step": 3}, region=((1, 3), (0, 2), (0, 1)), stride=(2, 1, 1))
    assert image.id == "hdf5:Polar" and image.time.step == 2
    assert image.array("Polar").dtype == np.dtype("float32")
    np.testing.assert_array_equal(image.array("Polar"), values[1:4:2].transpose(2, 1, 0, 3))
    check(image.descriptor())
    assert handle.read(frame={"latest": True}).array("Polar")[0, 0, 0, 0] == 100
    assert connector.open(source, "Polar", result=result).read(frame={"first": True}).array("Polar")[0, 0, 0, 0] == 1111
    with pytest.raises(ConnectorError, match="requested field"):
        handle.read(fields=["Other"])
    with pytest.raises(ConnectorError, match="requested field"):
        handle.stats(field="Other")


def test_hdf5_alone_is_discoverable_without_claiming_solver_success(tmp_path):
    write_case(tmp_path)
    write_hdf5(tmp_path / "run.h5")
    result = MuFerroConnector().describe(LocalFiles(tmp_path))
    assert validate_result(result) == []
    assert not result["complete"] and result["state"] == "unknown" and result["verification"] is None
    assert {dataset["id"] for dataset in result["datasets"]} == {"hdf5:Polar", "hdf5:Strain"}


def test_remote_source_metadata_and_read_use_the_same_content(tmp_path):
    write_case(tmp_path)
    write_outputs(tmp_path)
    values = write_hdf5(tmp_path / "run.h5")
    client = FakeClient(tmp_path)
    source = RuntimeFiles(client, "t" * 32, tmp_path / "download-cache")
    connector = MuFerroConnector()
    result = connector.describe(source)
    image = connector.open(source, "hdf5:Polar", result=result).read(frame={"first": True})
    np.testing.assert_array_equal(image.array("Polar"), values.transpose(2, 1, 0, 3))


class _PublishedHDF5Runtime(RuntimeClient):
    """Use RuntimeClient's real checksum and download code with an offline transport."""

    def __init__(self, published, replacement=None):
        self.published, self.replacement = published, replacement
        self.listings = self.file_reads = 0

    def request(self, method, path, data=None, binary=False, max_response_bytes=None):
        assert method == "GET"
        if path.endswith("/artifacts"):
            self.listings += 1
            payload = self.replacement if self.listings > 1 and self.replacement is not None else self.published
            return [{"path": "run.h5", "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}]
        assert binary and "/file?" in path
        self.file_reads += 1
        query = parse_qs(urlsplit(path).query)
        offset, limit = int(query["offset"][0]), int(query["limit"][0])
        payload = self.replacement if self.replacement is not None else self.published
        return payload[offset:offset + limit]


def _original_and_replacement(path):
    write_hdf5(path)
    original = path.read_bytes()
    with h5py.File(path, "r+") as file:
        file["t00000002/Polar"][0, 0, 0, 0] = 99
    replacement = path.read_bytes()
    assert len(original) == len(replacement) and original != replacement
    return original, replacement


@pytest.mark.parametrize("consumer", ["describe", "handle", "run_index", "field_node"])
def test_runtime_hdf5_rejects_same_size_cached_replacement(tmp_path, consumer):
    original, replacement = _original_and_replacement(tmp_path / "run.h5")
    client = _PublishedHDF5Runtime(original)
    resolver = RuntimeResolver(client, tmp_path / "cache", {"run": "a" * 32})
    source = resolver.resolve("run")
    connector = MuFerroConnector()
    handle = connector.open(source, "hdf5:Polar")
    first = {"first": True}
    assert handle.read(frame=first).array("Polar")[0, 0, 0, 0] == 0
    assert client.file_reads == 1
    cached = source.fetch("run.h5")
    metadata = cached.stat()
    cached.write_bytes(replacement)
    os.utime(cached, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    assert cached.stat().st_size == metadata.st_size and cached.stat().st_mtime_ns == metadata.st_mtime_ns
    assert source.sha256("run.h5") == hashlib.sha256(original).hexdigest()
    registry = build_registry(entry_points=False)

    if consumer == "describe":
        with pytest.raises(ConnectorError, match="published artifact") as error:
            connector.describe(source)
        assert error.value.code == "invalid_data"
    elif consumer == "handle":
        # A legitimate description of the replacement bytes still cannot reopen on this Runtime task.
        other = connector.describe(LocalFiles(tmp_path))
        with pytest.raises(ConnectorError, match="published artifact") as error:
            connector.open(source, "hdf5:Polar", result=other).read(frame=first)
        assert error.value.code == "invalid_data"
    else:
        graph = result_graph() if consumer == "run_index" else {
            "schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [{
                "id": "read", "type": "stk.source.mupro_hdf5@1",
                "params": {"binding": "run", "selector": "/t00000002/Polar"}}],
            "outputs": {"field": "read.out"},
        }
        with pytest.raises(EvaluationFailed, match="published artifact") as error:
            evaluate(graph, registry=registry, resolver=resolver)
        assert error.value.errors[0]["code"] == "invalid_data"

    cached.write_bytes(original)
    os.utime(cached, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    assert connector.open(source, "hdf5:Polar").read(frame=first).array("Polar")[0, 0, 0, 0] == 0
    assert client.file_reads == 1  # The additional content check makes no network request on a warm cache.


def test_runtime_hdf5_rejects_download_for_a_changed_listing(tmp_path):
    original, replacement = _original_and_replacement(tmp_path / "run.h5")
    client = _PublishedHDF5Runtime(original, replacement)
    source = RuntimeFiles(client, "a" * 32, tmp_path / "cache")
    with pytest.raises(ConnectorError, match="published artifact") as error:
        MuFerroConnector().describe(source)
    assert error.value.code == "invalid_data"
    assert client.listings == 2 and client.file_reads == 1
    assert source.sha256("run.h5") == hashlib.sha256(original).hexdigest()


def test_old_handle_refuses_rewrite_with_same_size_and_restored_mtime(tmp_path):
    write_case(tmp_path)
    path = tmp_path / "run.h5"
    write_hdf5(path)
    source, connector = LocalFiles(tmp_path), MuFerroConnector()
    handle = connector.open(source, "hdf5:Polar")
    before = path.stat()
    with h5py.File(path, "r+") as file:
        file["t00000002/Polar"][0, 0, 0, 0] = 99
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    with pytest.raises(ConnectorError, match="changed after"):
        handle.read(frame={"first": True})
    assert connector.open(source, "hdf5:Polar").read(frame={"first": True}).array("Polar")[0, 0, 0, 0] == 99


@pytest.mark.parametrize("change", ["dtype", "shape"])
def test_one_dataset_cannot_hide_changing_layout_between_steps(tmp_path, change):
    write_case(tmp_path)
    write_hdf5(tmp_path / "run.h5")
    with h5py.File(tmp_path / "run.h5", "r+") as file:
        del file["t00000004/Polar"]
        file.create_dataset("t00000004/Polar", data=np.ones((4, 3, 2, 3) if change == "dtype" else (5, 3, 2, 3),
                                                          dtype="float64" if change == "dtype" else "float32"))
    connector, source = MuFerroConnector(), LocalFiles(tmp_path)
    result = connector.describe(source)
    assert result["datasets"] == []
    assert "changes shape or dtype" in result["extensions"]["mupro"]["hdf5_error"]["message"]
    with pytest.raises(ConnectorError, match="changes shape or dtype"):
        connector.open(source, "hdf5:Polar", result=result)


def test_graph_result_indexes_hdf5_but_keeps_dat_frame_contract(tmp_path):
    write_case(tmp_path)
    write_outputs(tmp_path)
    path = tmp_path / "run.h5"
    write_hdf5(path)
    cache = GraphCache()
    first = evaluate_result(tmp_path, cache=cache)
    assert any(dataset["id"] == "hdf5:Polar" for dataset in first.outputs["result"]["datasets"])
    assert not any(name.startswith("hdf5:") for name in first.outputs["frames"].column("dataset"))
    assert evaluate_result(tmp_path, cache=cache).evaluated == []
    before = path.stat()
    with h5py.File(path, "r+") as file:
        file["t00000002/Polar"][0, 0, 0, 0] = 42
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    second = evaluate_result(tmp_path, cache=cache)
    assert second.evaluated == ["run"] and second.keys != first.keys


@pytest.mark.parametrize("change", ["rewrite", "remove", "add"])
def test_graph_cannot_cache_a_different_discovery_than_it_planned(tmp_path, change):
    write_case(tmp_path)
    path = tmp_path / "run.h5"
    if change != "add":
        write_hdf5(path)

    def mutate(event):
        if event["type"] != "node.started":
            return
        if change == "remove":
            path.unlink()
        elif change == "add":
            write_hdf5(path)
        else:
            with h5py.File(path, "r+") as file:
                file["t00000002/Polar"][0, 0, 0, 0] = 99

    with pytest.raises(EvaluationFailed) as error:
        evaluate_result(tmp_path, on_event=mutate)
    assert error.value.errors[0]["code"] == "invalid_data"


@pytest.mark.parametrize("change", ["listing_over_limit", "stream_over_limit", "stream_missing", "stream_unavailable"])
def test_graph_rejects_unverified_planned_container_without_poisoning_cache(tmp_path, monkeypatch, change):
    write_case(tmp_path)
    write_outputs(tmp_path)
    path = tmp_path / "run.h5"
    write_hdf5(path)
    original_bytes = path.read_bytes()
    original_stat = path.stat()
    monkeypatch.setattr(adapter, "FILE_LIMIT", original_stat.st_size)
    node_started = False
    open_source = LocalFiles.open

    def grow_container():
        with path.open("ab") as stream:
            stream.write(b"x")

    def open_with_change(source, name):
        if node_started and name == "run.h5":
            if change == "stream_over_limit":
                grow_container()
            elif change == "stream_missing":
                path.unlink()
                raise MissingFile("Synthetic HDF5 source was removed after listing")
            elif change == "stream_unavailable":
                raise ConnectorError("Synthetic HDF5 stream is unavailable", "unavailable")
        return open_source(source, name)

    def mutate(event):
        nonlocal node_started
        if event["type"] == "node.started":
            node_started = True
            if change == "listing_over_limit":
                grow_container()

    monkeypatch.setattr(LocalFiles, "open", open_with_change)
    cache = GraphCache()
    with pytest.raises(EvaluationFailed) as error:
        evaluate_result(tmp_path, cache=cache, on_event=mutate)
    assert error.value.errors[0]["code"] == "invalid_data"

    node_started = False
    path.write_bytes(original_bytes)
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    restored = evaluate_result(tmp_path, cache=cache)
    assert restored.evaluated == ["run"]
    assert {"Polar", "hdf5:Polar", "hdf5:Strain"} <= {d["id"] for d in restored.outputs["result"]["datasets"]}
    assert evaluate_result(tmp_path, cache=cache).evaluated == []


def test_hdf5_unavailable_at_planning_keeps_dat_run_index(tmp_path, monkeypatch):
    write_case(tmp_path)
    write_outputs(tmp_path)
    write_hdf5(tmp_path / "run.h5")
    open_source = LocalFiles.open

    def open_optional_unavailable(source, path):
        if path == "run.h5":
            raise ConnectorError("Synthetic HDF5 stream is unavailable", "unavailable")
        return open_source(source, path)

    monkeypatch.setattr(LocalFiles, "open", open_optional_unavailable)
    result = evaluate_result(tmp_path)
    assert result.outputs["frames"].n_rows > 0
    assert result.outputs["result"]["extensions"]["mupro"]["hdf5_error"]["code"] == "unavailable"


def test_describe_budget_is_checked_before_streaming(tmp_path):
    class NoRead:
        def open(self, path):
            pytest.fail("invalid budget must not open the source")
    with pytest.raises(ConnectorError) as error:
        adapter.describe(NoRead(), "run.h5", max_entries=False)
    assert error.value.code == "invalid_param"


def test_invalid_hdf5_keeps_dat_and_energy_readable_with_a_diagnostic(tmp_path):
    write_case(tmp_path)
    write_outputs(tmp_path)
    (tmp_path / "run.h5").write_bytes(b"not an HDF5 profile")
    source, connector = LocalFiles(tmp_path), MuFerroConnector()
    result = connector.describe(source)
    assert validate_result(result) == [] and result["complete"]
    assert result["extensions"]["mupro"]["hdf5_error"]["code"] == "invalid_data"
    graph_result = evaluate_result(tmp_path).outputs["result"]
    assert graph_result["extensions"]["mupro"]["hdf5_error"]["code"] == "invalid_data"
    assert "Polar" in {d["id"] for d in graph_result["datasets"]}
    assert connector.open(source, "energy").read().n_rows == 3
    assert connector.open(source, "Polar").read(frame={"first": True}).time.step == 0
    with pytest.raises(ConnectorError) as error:
        connector.open(source, "hdf5:Polar")
    assert error.value.code == "invalid_data"


def test_hdf5_over_budget_does_not_block_the_dat_run_index(tmp_path, monkeypatch):
    write_case(tmp_path)
    write_outputs(tmp_path)
    write_hdf5(tmp_path / "run.h5")
    monkeypatch.setattr(adapter, "FILE_LIMIT", 8)
    result = evaluate_result(tmp_path)
    assert result.outputs["frames"].n_rows > 0
    assert result.outputs["result"]["extensions"]["mupro"]["hdf5_error"]["code"] == "budget_exceeded"


def test_replacement_subclass_keeps_its_describe_contract_and_native_format(tmp_path, monkeypatch):
    import importlib
    sources = importlib.import_module("suan.graph.nodes.sources")
    write_case(tmp_path)
    write_outputs(tmp_path)
    document = MuFerroConnector().describe(LocalFiles(tmp_path))
    (tmp_path / "run.h5").write_bytes(b"a replacement plugin owns this native format")

    class Legacy(MuFerroConnector):
        def describe(self, run, *, live=False, case_dir=None):
            return document

    monkeypatch.setattr(sources, "_muferro", lambda: Legacy())
    monkeypatch.setattr(adapter, "file_fingerprint", lambda *a, **k: pytest.fail("public HDF5 policy leaked to plugin"))
    assert evaluate_result(tmp_path).outputs["frames"].n_rows > 0
