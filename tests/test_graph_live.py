"""Content-keyed source nodes on live muFerro runs (docs/specs/stk-graph-v1.md §5, review finding M6).

A fingerprinted source node is keyed by the content it resolved: the step/policy
selectors and the upstream frame listing are not part of its keys, so aliases of
one frame share a cache entry and a growing live run (energy rows, progress
lines, new frames) does not invalidate what was derived from an unchanged frame.
"""
import copy
import hashlib
import io
import os

import pytest

np = pytest.importorskip("numpy")

from mupro_fake import _e18, _frame, write_case, write_outputs  # noqa: E402
from suan.connectors.files import LocalFiles, RuntimeFiles  # noqa: E402
from suan.connectors.mupro import MuFerroConnector  # noqa: E402
from suan.data.dat import read_dat_image  # noqa: E402
from suan.graph.cache import GraphCache  # noqa: E402
from suan.graph.catalog import default_registry  # noqa: E402
from suan.graph.evaluator import EvaluationFailed, evaluate  # noqa: E402
from suan.graph.resolve import HashMemo, LocalDirResolver  # noqa: E402
from suan.graph.service import MemoryBlobSink, evaluate_request  # noqa: E402

GRAPH = {
    "schema": "stk.graph/1", "id": "live", "catalog": {"stk": 1},
    "parameters": [{"name": "step", "type": "step", "default": "latest"},
                   {"name": "view", "type": "enum", "choices": ["iso", "+x", "+z"], "default": "iso"}],
    "nodes": [
        {"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
        {"id": "polar", "type": "stk.source.muferro_frame@1", "inputs": {"frames": {"from": "run.frames"}},
         "params": {"dataset": "Polar", "step": {"$param": "step"}}},
        {"id": "box", "type": "stk.render.outline@1", "inputs": {"in": {"from": "polar.out"}}},
        {"id": "camera", "type": "stk.view.camera@1", "params": {"preset": {"$param": "view"}}},
        {"id": "scene", "type": "stk.view.scene@1",
         "inputs": {"layers": [{"from": "box.layer"}], "camera": {"from": "camera.camera"}}},
        {"id": "payload", "type": "stk.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}}},
        {"id": "energy", "type": "stk.plot.line@1", "inputs": {"table": {"from": "run.energy"}},
         "params": {"x": "step", "y": ["Total Energy"]}},
    ],
    "outputs": {"payload": "payload.payload", "polar": "polar.out", "energy": "energy.plot"},
}
FRAME_DERIVED = {"polar", "box", "camera", "scene", "payload"}


@pytest.fixture
def live(tmp_path):
    run = tmp_path / "run"
    write_case(run, grid=(4, 3, 2), steps=4, interval=2)
    write_outputs(run, grid=(4, 3, 2), steps=4, interval=2)  # Polar frames 0, 2, 4
    registry, resolver, cache = default_registry(), LocalDirResolver({"run": run}), GraphCache()

    def evaluate_graph(graph=GRAPH, **kw):
        kw.setdefault("cache", cache)
        return evaluate(graph, registry=registry, resolver=resolver, **kw)
    evaluate_graph.run = run
    return evaluate_graph


def _append_energy(run, step):
    with open(run / "energy_out.dat", "a") as stream:
        stream.write(f"kt: {step:6d} energy:   0.1000000000E+01  0.2000000000E+01  0.3000000000E+01"
                     "  0.4000000000E+01 -0.1000000000+102\n")
    with open(run / "mupro_progress.jsonl", "a") as stream:
        stream.write(f'{{"step":{step},"completed_steps":{step},"total_steps":10}}\n')


ENERGY_FILE = "energy_out.dat"
PROGRESS_FILE = "mupro_progress.jsonl"


def _run_index(folder, *, cache=None, on_event=None, source=None):
    graph = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [GRAPH["nodes"][0]],
             "outputs": {port: f"run.{port}" for port in ("frames", "energy", "progress", "result")}}
    resolver = LocalDirResolver({"run": folder}) if source is None else {"run": source}
    return evaluate(graph, registry=default_registry(), resolver=resolver, cache=cache, on_event=on_event)


def _one_row_run(folder):
    write_case(folder, steps=5)
    write_outputs(folder, steps=5, mode="fail")


def _changed_energy(raw):
    changed = raw.replace(_e18(-1.125).encode(), _e18(-9.125).encode())
    assert changed != raw and len(changed) == len(raw)
    return changed


def _assert_one_energy(outputs, total):
    assert outputs["energy"].column("Total Energy").tolist() == [total]
    assert next(q for q in outputs["result"]["qoi"] if q["name"] == "total_energy")["value"] == total


@pytest.mark.parametrize("change", ["energy", "append", "appears", "disappears"])
def test_run_index_refuses_table_drift_after_planning_and_restores_cleanly(tmp_path, change):
    _one_row_run(tmp_path)
    path = tmp_path / (ENERGY_FILE if change == "energy" else PROGRESS_FILE)
    if change == "appears":
        path.unlink()
    original = path.read_bytes() if path.exists() else None
    stamp = path.stat() if original is not None else None
    cache = GraphCache()

    def mutate(event):
        if event["type"] != "node.started":
            return
        if change == "energy":
            path.write_bytes(_changed_energy(original))
        elif change == "disappears":
            path.unlink()
        else:
            with path.open("ab") as stream:
                stream.write(b'{"step":2,"completed_steps":2,"total_steps":5}\n')

    with pytest.raises(EvaluationFailed) as error:
        _run_index(tmp_path, cache=cache, on_event=mutate)
    assert error.value.errors[0]["code"] == "invalid_data"

    if original is None:
        path.unlink()
    else:
        path.write_bytes(original)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    restored = _run_index(tmp_path, cache=cache)
    assert restored.evaluated == ["run"]
    _assert_one_energy(restored.outputs, -1.125)
    assert restored.outputs["progress"].column("completed_steps").tolist() == ([] if change == "appears" else [1])
    assert _run_index(tmp_path, cache=cache).evaluated == []


def test_run_index_energy_qoi_and_port_share_one_verified_observation(tmp_path):
    _one_row_run(tmp_path)
    original = (tmp_path / ENERGY_FILE).read_bytes()
    changed = _changed_energy(original)

    class ChangedOnce(LocalFiles):
        armed = False
        execution_reads = 0

        def open(self, path):
            if self.armed and path == ENERGY_FILE:
                self.execution_reads += 1
                if self.execution_reads == 1:
                    return io.BytesIO(changed)
            return super().open(path)

    source, cache = ChangedOnce(tmp_path), GraphCache()

    def mutate(event):
        if event["type"] == "node.started":
            source.armed = True

    with pytest.raises(EvaluationFailed) as error:
        _run_index(tmp_path, cache=cache, source=source, on_event=mutate)
    assert error.value.errors[0]["code"] == "invalid_data" and source.execution_reads == 1
    source.armed = False
    restored = _run_index(tmp_path, cache=cache, source=source, on_event=mutate)
    assert restored.evaluated == ["run"] and source.execution_reads == 2
    _assert_one_energy(restored.outputs, -1.125)
    file = next(entry for entry in restored.outputs["result"]["files"] if entry["path"] == ENERGY_FILE)
    assert file["sha256"] == hashlib.sha256(original).hexdigest() and file["size"] == len(original)


def test_run_index_accepts_short_reads_from_a_file_source(tmp_path):
    _one_row_run(tmp_path)

    class ShortStream(io.BytesIO):
        def read(self, size=-1):
            return super().read(min(size, 7) if size >= 0 else 7)

    class ShortSource(LocalFiles):
        def open(self, path):
            if path in (ENERGY_FILE, PROGRESS_FILE):
                with super().open(path) as stream:
                    return ShortStream(stream.read())
            return super().open(path)

    outputs = _run_index(tmp_path, source=ShortSource(tmp_path)).outputs
    _assert_one_energy(outputs, -1.125)
    assert outputs["progress"].column("completed_steps").tolist() == [1]


@pytest.mark.parametrize("initially_present", [False, True])
def test_run_index_refuses_completion_marker_presence_drift(tmp_path, initially_present):
    write_case(tmp_path, steps=4, interval=2)
    write_outputs(tmp_path, steps=4, interval=2)
    marker = tmp_path / "mupro_completion.json"
    original, stamp = marker.read_bytes(), marker.stat()
    if not initially_present:
        marker.unlink()
    cache = GraphCache()

    def change_presence(event):
        if event["type"] == "node.started":
            if initially_present:
                marker.unlink()
            else:
                marker.write_bytes(original)

    with pytest.raises(EvaluationFailed) as error:
        _run_index(tmp_path, cache=cache, on_event=change_presence)
    assert error.value.errors[0]["code"] == "invalid_data"

    if initially_present:
        marker.write_bytes(original)
        os.utime(marker, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    else:
        marker.unlink()
    restored = _run_index(tmp_path, cache=cache)
    assert restored.evaluated == ["run"]
    assert restored.outputs["frames"].attrs["complete"] is initially_present
    assert (marker.name in {item["path"] for item in restored.outputs["result"]["files"]}) is initially_present
    assert restored.outputs["result"]["complete"] is False
    assert _run_index(tmp_path, cache=cache).evaluated == []


def test_run_index_hashes_same_size_and_mtime_local_energy_rewrite(tmp_path):
    _one_row_run(tmp_path)
    cache = GraphCache()
    first = _run_index(tmp_path, cache=cache)
    path = tmp_path / ENERGY_FILE
    stamp = path.stat()
    path.write_bytes(_changed_energy(path.read_bytes()))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    new = _run_index(tmp_path, cache=cache)
    assert new.evaluated == ["run"] and new.keys != first.keys
    _assert_one_energy(new.outputs, -9.125)


@pytest.mark.parametrize("filename", [ENERGY_FILE, PROGRESS_FILE])
def test_run_index_refuses_runtime_table_cache_rewrite(tmp_path, filename):
    from test_connectors_files import FakeClient
    _one_row_run(tmp_path)
    files = {name: (tmp_path / name).read_bytes() for name in (ENERGY_FILE, PROGRESS_FILE)}
    client = FakeClient(files)
    source = RuntimeFiles(client, "test-task", tmp_path / "runtime-cache")
    correct_cache = GraphCache()
    first = _run_index(tmp_path, source=source, cache=correct_cache)
    _assert_one_energy(first.outputs, -1.125)
    path = source.fetch(filename)
    stamp = path.stat()
    altered = _changed_energy(files[filename]) if filename == ENERGY_FILE else files[filename].replace(
        b'"completed_steps":1', b'"completed_steps":2')
    assert altered != files[filename] and len(altered) == len(files[filename])
    path.write_bytes(altered)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    cached = _run_index(tmp_path, source=source, cache=correct_cache)
    assert cached.evaluated == []
    _assert_one_energy(cached.outputs, -1.125)
    assert cached.outputs["progress"].column("completed_steps").tolist() == [1]
    empty_cache = GraphCache()
    with pytest.raises(EvaluationFailed) as error:
        _run_index(tmp_path, source=source, cache=empty_cache)
    assert error.value.errors[0]["code"] == "invalid_data"
    path.write_bytes(files[filename])
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    restored = _run_index(tmp_path, source=source, cache=empty_cache)
    assert restored.evaluated == ["run"]
    _assert_one_energy(restored.outputs, -1.125)
    assert restored.outputs["progress"].column("completed_steps").tolist() == [1]
    assert client.downloads == 2


def test_run_index_preserves_direct_malformed_energy_diagnostic(tmp_path):
    _one_row_run(tmp_path)
    (tmp_path / ENERGY_FILE).write_text("malformed energy row\n")
    result = MuFerroConnector().describe(LocalFiles(tmp_path), live=True)
    energy = next(dataset for dataset in result["datasets"] if dataset["id"] == "energy")
    assert energy["geometry"]["rows"] is None and not result["qoi"]
    with pytest.raises(EvaluationFailed) as error:
        _run_index(tmp_path)
    assert error.value.errors[0]["code"] == "invalid_data"


def test_run_index_preserves_a_replacement_connector_table_reader(tmp_path, monkeypatch):
    from suan.graph.nodes import sources
    _one_row_run(tmp_path)
    opened = []

    class CustomOpen(MuFerroConnector):
        def open(self, run, dataset_id, **options):
            opened.append(dataset_id)
            return super().open(run, dataset_id, **options)

    monkeypatch.setattr(sources, "_muferro", lambda: CustomOpen())
    _assert_one_energy(_run_index(tmp_path).outputs, -1.125)
    assert opened == ["energy", "progress"]


def test_step_aliases_share_one_frame_entry(live):
    first = live(parameters={"step": 2}, outputs=["polar"])
    assert first.evaluated == ["run", "polar"]
    for alias in ({"step": 3}, {"step": 2}):  # step 3 resolves to frame 2 (latest_at_or_before)
        again = live(parameters=alias, outputs=["polar"])
        assert again.evaluated == [] and again.keys["polar"] == first.keys["polar"]
        assert again.parameters["step"] == {"value": 2, "choices": [0, 2, 4]}
    exact = copy.deepcopy(GRAPH)
    exact["nodes"][1]["params"]["policy"] = "exact"  # the policy is a selector too
    assert live(exact, parameters={"step": 2}, outputs=["polar"]).keys["polar"] == first.keys["polar"]
    latest = live(outputs=["polar"])
    assert latest.evaluated == ["polar"] and latest.parameters["step"]["value"] == 4
    four = live(parameters={"step": 4}, outputs=["polar"])
    assert four.evaluated == [] and four.keys["polar"] == latest.keys["polar"] != first.keys["polar"]
    assert four.outputs["polar"].time.step == 4


def test_live_energy_appends_do_not_invalidate_frame_derived_nodes(live):
    first = live(parameters={"step": 2})
    assert FRAME_DERIVED <= set(first.evaluated) and "energy" in first.evaluated
    _append_energy(live.run, 5)
    second = live(parameters={"step": 2})
    # Only the run index and what reads the energy trace re-run; the frame and everything built on it is cached.
    assert set(second.evaluated) == {"run", "energy"}
    assert second.keys["run"] != first.keys["run"]
    for node_id in FRAME_DERIVED:
        assert second.keys[node_id] == first.keys[node_id], node_id
    assert second.outputs["payload"].manifest == first.outputs["payload"].manifest
    assert second.parameters["step"] == {"value": 2, "choices": [0, 2, 4]}


def test_camera_only_change_on_a_live_run_reruns_only_view_and_output_nodes(live):
    first = live(parameters={"step": "latest"})
    _append_energy(live.run, 5)
    second = live(parameters={"step": "latest", "view": "+x"})
    assert set(second.evaluated) == {"run", "energy", "camera", "scene", "payload"}
    assert second.keys["polar"] == first.keys["polar"] and second.keys["box"]["data"] == first.keys["box"]["data"]
    assert second.keys["payload"]["full"] != first.keys["payload"]["full"]
    # The same camera change without new energy rows re-runs only the view and output nodes.
    third = live(parameters={"step": "latest", "view": "+z"})
    assert set(third.evaluated) == {"camera", "scene", "payload"}


def test_fresh_choices_override_replayed_cache_notes(live):
    live(parameters={"step": 2}, outputs=["polar"])
    polar = live.run / "Polar.00000004.dat"
    (live.run / "Polar.00000006.dat").write_bytes(polar.read_bytes())  # the live run publishes frame 6
    again = live(parameters={"step": 2}, outputs=["polar"])
    assert again.evaluated == ["run"]  # frame 2 is unchanged and cached
    assert again.parameters["step"] == {"value": 2, "choices": [0, 2, 4, 6]}  # not the cached [0, 2, 4]


def test_content_keys_with_a_disk_cache_across_evaluations(live, tmp_path):
    root = tmp_path / "cache"
    first = live(parameters={"step": 3}, outputs=["polar"], cache=GraphCache(root))
    assert first.evaluated == ["run", "polar"]
    _append_energy(live.run, 5)
    second = live(parameters={"step": 2}, outputs=["polar"], cache=GraphCache(root))
    assert second.evaluated == ["run"] and second.keys["polar"] == first.keys["polar"]
    assert second.outputs["polar"].time.step == 2


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_frame_rewritten_in_place_is_read_again(live):
    # The frames table (and its sha256 column) may come from the cache; the frame's key uses the file now.
    live(parameters={"step": 2}, outputs=["polar"])
    _append_energy(live.run, 5)
    assert live(parameters={"step": 2}, outputs=["polar"]).evaluated == ["run"]
    frame = live.run / "Polar.00000002.dat"
    size, mtime = frame.stat().st_size, frame.stat().st_mtime_ns
    _frame(frame, (4, 3, 2), 3, 7)  # other values, same size
    os.utime(frame, ns=(mtime + 10**9, mtime + 10**9))  # a later write (coarse clocks may repeat a tick)
    assert frame.stat().st_size == size
    third = live(parameters={"step": 2}, outputs=["polar"])
    assert "polar" in third.evaluated
    expected = read_dat_image(frame, name="Polar").array("Polar")
    assert np.array_equal(third.outputs["polar"].array("Polar"), expected)
    assert third.outputs["polar"].provenance.used[0]["sha256"] == _sha(frame)
    # A cache miss for another reason stores the new content under the new content's key.
    changed = copy.deepcopy(GRAPH)
    changed["nodes"][1]["params"]["precision"] = "float32"
    fourth = live(changed, parameters={"step": 2}, outputs=["polar"])
    assert fourth.outputs["polar"].provenance.used[0]["sha256"] == _sha(frame)


def test_run_directories_with_identical_listings_are_told_apart(tmp_path):
    runs = {}
    for name, offset in (("a", 0), ("b", 50)):
        run = runs[name] = tmp_path / name
        write_case(run, grid=(4, 3, 2), steps=4, interval=2)
        write_outputs(run, grid=(4, 3, 2), steps=4, interval=2)
        for extra in ("energy_out.dat", "mupro_progress.jsonl", "mupro_completion.json"):
            (run / extra).unlink()
        for step in (0, 2, 4):
            _frame(run / f"Polar.{step:08d}.dat", (4, 3, 2), 3, step + offset)
    memo, registry, cache = HashMemo(tmp_path / "hashes.sqlite"), default_registry(), GraphCache()
    graph = copy.deepcopy(GRAPH)
    graph["nodes"][1]["params"]["step"] = 2

    def run_of(name):
        return evaluate(graph, registry=registry, resolver=LocalDirResolver({"run": runs[name]}, hash_memo=memo),
                        cache=cache, outputs=["polar"])
    first = run_of("a")
    cache.discard(first.keys["run"]["data"], disk=False)  # e.g. an LRU eviction: the run is described again
    run_of("a")
    for name in ("a", "b"):
        expected = read_dat_image(runs[name] / "Polar.00000002.dat", name="Polar").array("Polar")
        assert np.array_equal(run_of(name).outputs["polar"].array("Polar"), expected), name


def test_a_frame_being_written_is_not_the_latest(live):
    full = (live.run / "Polar.00000004.dat").read_bytes()
    (live.run / "Polar.00000006.dat").write_bytes(full[: len(full) // 2])  # muFerro is writing frame 6
    result = live(outputs=["polar"])
    assert result.parameters["step"] == {"value": 4, "choices": [0, 2, 4]}
    assert result.outputs["polar"].time.step == 4
    (live.run / "Polar.00000006.dat").write_bytes(full)  # written: now the latest
    assert live(outputs=["polar"]).parameters["step"] == {"value": 6, "choices": [0, 2, 4, 6]}
    # Unreadable rows (numpy's ValueError in the general parser) are invalid data, not a node crash.
    (live.run / "Polar.00000006.dat").write_bytes(full.replace(b"E+", b"x+", 1))
    with pytest.raises(EvaluationFailed) as error:
        live(parameters={"step": 6}, outputs=["polar"], cache=GraphCache())
    assert error.value.errors[0]["code"] == "invalid_data"


def test_layers_and_picks_name_nodes_of_the_graph_being_evaluated(live):
    # Keys are content-only, so a graph naming its nodes differently shares the source's cache entry; the
    # values that embed node ids (layers, scenes, payloads) never come from the other graph.
    graph = {"schema": "stk.graph/1", "catalog": {"stk": 1},
             "nodes": [{"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
                       {"id": "polar", "type": "stk.source.muferro_frame@1",
                        "inputs": {"frames": {"from": "run.frames"}}},
                       {"id": "vol", "type": "stk.render.volume@1", "inputs": {"in": {"from": "polar.out"}}},
                       {"id": "scene", "type": "stk.view.scene@1", "inputs": {"layers": [{"from": "vol.layer"}]}},
                       {"id": "payload", "type": "stk.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}}}],
             "outputs": {"payload": "payload.payload"}}
    renamed = copy.deepcopy(graph)
    renamed["nodes"][1]["id"], renamed["nodes"][2]["id"] = "frame", "layer1"
    renamed["nodes"][2]["inputs"]["in"]["from"] = "frame.out"
    renamed["nodes"][3]["inputs"]["layers"][0]["from"] = "layer1.layer"
    cache, registry = GraphCache(), default_registry()
    resolver = LocalDirResolver({"run": live.run})
    layers = {}
    for name, document in (("a", graph), ("b", renamed)):
        result = evaluate_request({"graph": document}, resolver=resolver, cache_dir=None, blob_sink=MemoryBlobSink(),
                                  registry=registry, cache=cache)
        layers[name] = result["outputs"]["payload"]["manifest"]["layers"][0]
        ids = {node["id"] for node in document["nodes"]}
        assert layers[name]["node"] in ids and layers[name]["pick"]["probe"]["node"] in ids, layers[name]
        if name == "b":
            assert "frame" not in result["evaluated"]  # the frame read by graph a is reused
    assert layers["a"]["id"] == "vol" and layers["a"]["pick"]["probe"] == {"node": "polar", "dataset": "Polar"}
    assert layers["b"]["id"] == "layer1" and layers["b"]["pick"]["probe"]["node"] in ("frame", "layer1")
