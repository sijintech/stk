"""suan.graph.service: graph.evaluate requests -> stk.graph-result/1 with blobs through an injectable sink."""
import hashlib
import json
import re

import pytest

np = pytest.importorskip("numpy")

from graph_testnodes import encode_scene, graph, make_registry, render_plot, write_run  # noqa: E402
from suan.graph import catalog  # noqa: E402
from suan.graph.cache import GraphCache  # noqa: E402
from suan.graph.evaluator import EvaluationFailed  # noqa: E402
from suan.graph.registry import BudgetExceeded, GraphError  # noqa: E402
from suan.graph.resolve import LocalDirResolver, RuntimeResolver  # noqa: E402
from suan.graph.schema import GraphValidationError  # noqa: E402
from suan.graph.service import (DirectoryBlobSink, MemoryBlobSink, evaluate_request, parse_request,  # noqa: E402
                                shared_cache)

HEX = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture
def run_dir(tmp_path):
    return write_run(tmp_path / "run")


@pytest.fixture
def service(run_dir, tmp_path):
    registry = make_registry()
    resolver = LocalDirResolver({"run": run_dir})
    sink = MemoryBlobSink()

    def call(payload=None, **kw):
        registry.runs.clear()
        options = {"resolver": resolver, "cache_dir": tmp_path / "cache", "blob_sink": sink, "registry": registry,
                   "encode_scene": encode_scene, "render_plot": render_plot}
        options.update(kw)
        return evaluate_request(payload if payload is not None else {"graph": graph()}, **options)
    call.registry, call.sink, call.resolver = registry, sink, resolver
    return call


def blob(sink, digest):
    data = sink.blobs[digest]
    assert hashlib.sha256(data).hexdigest() == digest
    return data


def test_result_document(service):
    result = service({"graph": graph(), "parameters": {"step": 100}, "profile": "phone"})
    json.dumps(result, allow_nan=False)
    assert result["schema"] == "stk.graph-result/1" and result["profile"] == "phone"
    assert HEX.match(result["graph_sha256"]) and result["graph_hash"] == "sha256:" + result["graph_sha256"]
    assert result["parameters"]["step"] == {"value": 100, "choices": [0, 100, 200]}
    assert result["cache"] == {"hits": 0, "misses": 12} and set(result["timings"]) == set(result["evaluated"])
    assert [w["code"] for w in result["warnings"]] == ["test_warning"] and "errors" not in result
    outputs = result["outputs"]
    assert set(outputs) == {"payload", "image", "stats", "plot", "info", "scene"}

    payload = outputs["payload"]
    assert payload["type"] == "payload" and payload["manifest"]["schema"] == "stk.payload/2"
    assert payload["manifest"]["source"]["profile"] == "phone"  # the node sees the request profile
    for entry in payload["manifest"]["buffers"]:
        assert entry["uri"] == "sha256:" + entry["sha256"] and len(blob(service.sink, entry["sha256"])) == entry[
            "byteLength"]
    assert outputs["scene"]["type"] == "payload"  # scenes are delivered as payloads
    assert outputs["scene"]["manifest"]["source"]["profile"] == "phone"

    image = outputs["image"]
    assert image == {"type": "image", "blob": image["blob"], "media_type": "image/png", "size": image["size"],
                     "width": 64, "height": 48}
    assert blob(service.sink, image["blob"]).startswith(b"\x89PNG")

    stats = outputs["stats"]
    assert stats["type"] == "table" and stats["columns"]["stat"] == ["min", "max", "mean"]
    assert stats["units"] == {"stat": "unspecified", "value": "unspecified"}

    plot = outputs["plot"]
    assert plot["type"] == "plot" and plot["media_type"] == "image/svg+xml"
    assert blob(service.sink, plot["blob"]).startswith(b"<svg")
    assert json.loads(blob(service.sink, plot["data_blob"]))["t"]["columns"]["stat"] == ["min", "max", "mean"]

    assert outputs["info"] == {"type": "value", "value": {"dimensions": [4, 3, 2], "fields": ["P"], "step": 100}}


def test_other_output_types(service, tmp_path):
    document = graph()
    document["nodes"] += [
        {"id": "export", "type": "test.output.export@1", "inputs": {"in": {"from": "frame.out"}}},
        {"id": "big", "type": "test.analysis.big@1", "inputs": {"in": {"from": "frame.out"}}},
    ]
    document["outputs"].update({"export": "export.file", "big": "big.out", "frame": "frame.out"})
    result = service({"graph": document, "outputs": ["export", "big", "frame"], "plot_format": "png"})
    export = result["outputs"]["export"]
    assert export["type"] == "file" and export["name"] == "export.npy" and "path" not in export
    assert np.load(__import__("io").BytesIO(blob(service.sink, export["blob"]))).shape == (2, 3, 4, 3)
    big = result["outputs"]["big"]
    assert big["type"] == "table" and big["media_type"] == "application/json" and big["rows"] == 40000
    assert big["size"] > 256 * 1024 and len(json.loads(blob(service.sink, big["blob"]))["columns"]["i"]) == 40000
    frame = result["outputs"]["frame"]
    assert frame["type"] == "dataset" and frame["descriptor"]["schema"] == "stk.dataset/1"
    assert frame["descriptor"]["geometry"]["dimensions"] == [4, 3, 2]
    plot = service({"graph": graph(), "outputs": ["plot"], "plot_format": "png"})["outputs"]["plot"]
    assert plot["media_type"] == "image/png"


def test_cache_is_shared_between_requests(service):
    first = service()
    second = service({"graph": graph(surface={"colormap": "gray"}), "parameters": {"view": "-x"}})
    assert set(second["evaluated"]) == {"legend", "camera", "scene", "payload", "image"}
    assert second["keys"]["frame"] == first["keys"]["frame"]
    assert second["cache"]["hits"] > 0
    assert shared_cache(None) is shared_cache(None)


def test_warm_requests_do_not_render_plots_again(service):
    calls = []

    def counting(plot, *, format="svg"):
        calls.append(format)
        return render_plot(plot, format=format)
    first = service({"graph": graph(), "outputs": ["plot"]}, render_plot=counting)
    again = service({"graph": graph(), "outputs": ["plot"]}, render_plot=counting)
    assert calls == ["svg"] and again["outputs"]["plot"] == first["outputs"]["plot"]
    png = service({"graph": graph(), "outputs": ["plot"], "plot_format": "png"}, render_plot=counting)
    assert calls == ["svg", "png"] and png["outputs"]["plot"]["media_type"] == "image/png"
    changed = service({"graph": graph(), "outputs": ["plot"], "parameters": {"factor": 3.0}}, render_plot=counting)
    assert calls == ["svg", "png", "svg"]
    assert changed["outputs"]["plot"]["data_blob"] != first["outputs"]["plot"]["data_blob"]
    assert service({"graph": graph(), "outputs": ["plot"]}, render_plot=counting, cache=GraphCache())
    assert calls[-1] == "svg" and len(calls) == 4  # another cache has not seen the plot


def test_request_validation(service):
    bad = [
        ({"graph": graph(), "extra": 1}, "Unknown request key"),
        ({}, "exactly one of"),
        ({"graph": graph(), "preset": "x"}, "exactly one of"),
        ({"graph": "text"}, "stk.graph/1 object"),
        ({"graph": graph(), "bindings": {"run": {"path": "/data/run"}}}, "task_id"),
        ({"graph": graph(), "bindings": {"run": "/data/run"}}, "task_id"),
        ({"graph": graph(), "bindings": {"Run!": {"task_id": "t"}}}, "binding name"),
        ({"graph": graph(), "outputs": "image"}, "list of graph output names"),
        ({"graph": graph(), "profile": "tv"}, "profile"),
        ({"graph": graph(), "plot_format": "gif"}, "plot_format"),
        ({"graph": graph(), "budget": {"max_seconds": -1}}, "positive"),
        ({"graph": graph(), "budget": {"cpu": 1}}, "budget"),
        ("not an object", "JSON object"),
    ]
    for payload, message in bad:
        with pytest.raises(GraphError, match=message) as info:
            parse_request(payload)
        assert info.value.code == "bad_request"
    with pytest.raises(GraphError, match="task bindings"):  # a local resolver cannot take request bindings
        service({"graph": graph(), "bindings": {"run": {"task_id": "abc"}}})
    with pytest.raises(GraphValidationError):
        service({"graph": graph(), "parameters": {"step": -1}})
    with pytest.raises(GraphError) as info:
        service({"graph": graph(), "outputs": ["nope"]})
    assert info.value.code == "bad_output"


def test_task_bindings_through_the_runtime_resolver(service, run_dir, tmp_path):
    class Client:
        def artifacts(self, task_id):
            assert task_id == "task7"
            return [{"path": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted(run_dir.iterdir())]

        def download(self, task_id, remote_path, destination):
            destination.write_bytes((run_dir / remote_path).read_bytes())
            return destination
    resolver = RuntimeResolver(Client(), tmp_path / "downloads")
    result = service({"graph": graph(), "bindings": {"run": {"task_id": "task7"}}, "outputs": ["info"]},
                     resolver=resolver, cache_dir=tmp_path / "remote-cache")
    assert result["outputs"]["info"]["value"]["step"] == 200


def test_partial_and_total_failures(service):
    result = service({"graph": graph(scale={"mode": "fail"})})
    assert set(result["outputs"]) == {"info"}
    error = result["errors"][0]
    assert error["code"] == "node_failed" and error["node"] == "scale" and "stats" in error["skipped"]
    with pytest.raises(EvaluationFailed):
        service({"graph": graph(scale={"mode": "fail"}), "outputs": ["stats"]})


def test_budgets(service):
    with pytest.raises(BudgetExceeded):
        service({"graph": graph(), "outputs": ["image"], "budget": {"max_output_bytes": 200}})
    with pytest.raises(BudgetExceeded):
        service({"graph": graph(), "outputs": ["info"], "budget": {"max_output_bytes": 10}})
    assert service({"graph": graph(), "outputs": ["info"], "budget": {"max_seconds": None}})["outputs"]["info"]


def test_scene_and_plot_need_the_render_packages(service):
    try:
        import suan.render.payload  # noqa: F401
    except ImportError:
        with pytest.raises(GraphError) as info:
            service({"graph": graph(), "outputs": ["scene"]}, encode_scene=None)
        assert info.value.code == "unsupported" and info.value.path == "/outputs/scene"
    try:
        import suan.plot.mpl  # noqa: F401
    except ImportError:
        with pytest.raises(GraphError) as info:
            service({"graph": graph(), "outputs": ["plot"]}, render_plot=None)
        assert info.value.code == "unsupported"

    def broken(scene, *, profile, budget=None):
        return {"manifest": {"schema": "stk.payload/2", "buffers": [{"sha256": "0" * 64, "byteLength": 1}]},
                "buffers": {}}
    with pytest.raises(GraphError) as info:
        service({"graph": graph(), "outputs": ["scene"]}, encode_scene=broken)
    assert info.value.code == "bad_outputs"


def test_blob_sinks(tmp_path):
    sink = DirectoryBlobSink(tmp_path / "blobs")
    digest = sink(b"hello")
    assert digest == hashlib.sha256(b"hello").hexdigest() and sink.path(digest).read_bytes() == b"hello"
    assert sink(b"hello") == digest
    source = tmp_path / "file.bin"
    source.write_bytes(b"x" * 3_000_000)
    assert sink(source) == hashlib.sha256(source.read_bytes()).hexdigest()
    assert sorted(p.name for p in (tmp_path / "blobs").rglob("*") if p.is_file()) == sorted(
        [digest, hashlib.sha256(source.read_bytes()).hexdigest()])
    memory = MemoryBlobSink()
    assert memory(source) == sink(source) and memory.blobs[memory(b"a")] == b"a"


def test_presets(service, tmp_path, monkeypatch):
    presets = tmp_path / "presets"
    presets.mkdir()
    (presets / "demo.json").write_text(json.dumps({"name": "Demo", "description": "A demo", "graph": graph(),
                                                   "bindings": [{"name": "run", "description": "A run"}]}))
    (presets / "bare.json").write_text(json.dumps(graph()))
    (presets / "Not A Preset.json").write_text("{}")
    monkeypatch.setattr(catalog, "_presets_root", lambda: presets)
    listing = catalog.list_presets(service.registry)
    assert [p["id"] for p in listing] == ["bare", "demo"]
    demo = listing[1]
    assert demo["name"] == "Demo" and demo["bindings"] == [{"name": "run", "description": "A run"}]
    assert demo["parameters"][0]["name"] == "step" and listing[0]["name"] == "test pipeline"
    assert catalog.load_preset("bare") == graph()
    result = service({"preset": "demo", "outputs": ["info"]})
    assert result["outputs"]["info"]["value"]["step"] == 200
    for bad in ("missing", "../etc", "Not A Preset"):
        with pytest.raises(GraphError) as info:
            service({"preset": bad})
        assert info.value.code == "unknown_preset"


def test_default_registry_and_cache_dir(service, tmp_path):
    # The default registry holds the installed built-ins only; test types are unknown there.
    with pytest.raises(GraphValidationError):
        evaluate_request({"graph": graph()}, resolver=service.resolver, cache_dir=None, blob_sink=MemoryBlobSink())
    cache = shared_cache(tmp_path / "shared")
    assert isinstance(cache, GraphCache) and cache is shared_cache(tmp_path / "shared" / ".")


def test_output_byte_limit_applies_to_delivery_not_to_in_memory_values(service):
    # A 64^3 vector field (6.3 MB in memory) delivered as a dataset descriptor (a few KB): the evaluator runs
    # without an output-byte limit and only the delivered bytes count against the request budget.
    from suan.data.model import ImageData
    from suan.graph.registry import Port

    @service.registry.node("test.analysis.huge", inputs=[Port("in", "dataset", accepts=["image"])],
                           outputs=[Port("out", "dataset", kind="image")])
    def huge(ctx, inputs, params):
        image = ImageData((64, 64, 64), id="huge")
        image.add_field("v", np.ones((64, 64, 64, 3)), tensor="vector")
        return image
    document = graph()
    document["nodes"].append({"id": "huge", "type": "test.analysis.huge@1", "inputs": {"in": {"from": "frame.out"}}})
    document["outputs"]["huge"] = "huge.out"
    result = service({"graph": document, "outputs": ["huge"], "budget": {"max_output_bytes": 1024 * 1024}})
    assert result["outputs"]["huge"]["type"] == "dataset"
    with pytest.raises(BudgetExceeded):  # the delivered document itself is still limited
        service({"graph": document, "outputs": ["huge"], "budget": {"max_output_bytes": 256}})


def test_default_delivery_limits_follow_the_request_profile():
    from suan.graph.service import PROFILE_OUTPUT_BYTES, _budget
    assert PROFILE_OUTPUT_BYTES == {"phone": 32 * 2**20, "web": 128 * 2**20, "desktop": 2 * 2**30}
    for profile, limit in PROFILE_OUTPUT_BYTES.items():
        budget = _budget(parse_request({"graph": graph(), "profile": profile}))
        assert budget.max_output_bytes == limit and budget.profile == profile
    explicit = _budget(parse_request({"graph": graph(), "profile": "desktop", "budget": {"max_output_bytes": 5}}))
    assert explicit.max_output_bytes == 5
    assert _budget(parse_request({"graph": graph(), "budget": {"max_output_bytes": None}})).max_output_bytes is None


def test_pruned_exports_are_written_again(tmp_path):
    # Exports live in the cache's scratch space; if pruning removed the file of a value still held in the
    # memory tier, the request re-runs the export node instead of failing.
    data = tmp_path / "data"
    data.mkdir()
    np.save(data / "field.npy", np.arange(24, dtype=np.float64).reshape(2, 3, 4))
    document = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "src", "type": "stk.source.file@1", "params": {"binding": "data", "path": "field.npy"}},
        {"id": "exp", "type": "stk.output.dataset@1", "inputs": {"in": {"from": "src.out"}},
         "params": {"format": "npy"}}], "outputs": {"export": "exp.file"}}
    cache, sink = GraphCache(tmp_path / "cache"), MemoryBlobSink()

    def request():
        return evaluate_request({"graph": document}, resolver=LocalDirResolver({"data": data}), cache_dir=None,
                                blob_sink=sink, cache=cache)
    first = request()
    export = first["outputs"]["export"]
    assert export["type"] == "file" and export["name"] == "exp.npy"
    assert np.array_equal(np.load(__import__("io").BytesIO(blob(sink, export["blob"]))),
                          np.arange(24, dtype=np.float64).reshape(2, 3, 4))
    assert cache.stats()["scratch"]["entries"] == 1
    assert request()["evaluated"] == []
    cache.prune(0)  # removes the scratch export (and the disk entries)
    again = request()
    assert "exp" in again["evaluated"] and again["outputs"]["export"]["blob"] == export["blob"]


def test_payload_profile_auto_follows_the_request_profile(tmp_path):
    pytest.importorskip("suan.render.payload")
    from mupro_fake import write_case, write_outputs
    run = tmp_path / "run"
    write_case(run, grid=(4, 3, 2), steps=2, interval=2)
    write_outputs(run, grid=(4, 3, 2), steps=2, interval=2)
    document = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
        {"id": "polar", "type": "stk.source.muferro_frame@1", "inputs": {"frames": {"from": "run.frames"}}},
        {"id": "box", "type": "stk.render.outline@1", "inputs": {"in": {"from": "polar.out"}}},
        {"id": "scene", "type": "stk.view.scene@1", "inputs": {"layers": [{"from": "box.layer"}]}},
        {"id": "auto", "type": "stk.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}}},
        {"id": "web", "type": "stk.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}},
         "params": {"profile": "web"}}],
        "outputs": {"auto": "auto.payload", "web": "web.payload"}}
    cache, sink = GraphCache(), MemoryBlobSink()
    seen = {}
    for profile in ("phone", "desktop", "phone"):
        result = evaluate_request({"graph": document, "profile": profile}, resolver=LocalDirResolver({"run": run}),
                                  cache_dir=None, blob_sink=sink, cache=cache)
        auto, web = (result["outputs"][name]["manifest"] for name in ("auto", "web"))
        assert auto["source"]["profile"] == auto["budget"]["profile"] == profile  # unset -> the request profile
        assert web["source"]["profile"] == "web"  # an explicit profile wins
        seen.setdefault(profile, result["keys"]["auto"]["full"])
        assert result["keys"]["auto"]["full"] == seen[profile]  # the key names the effective profile
    assert seen["phone"] != seen["desktop"]
    assert result["evaluated"] == []  # the second phone request is served from the cache


def test_scene_outputs_report_payload_reductions_as_warnings(tmp_path):
    # A scene output is encoded at delivery; its budget reductions are warned like stk.output.payload@1's.
    pytest.importorskip("suan.render.payload")
    data = tmp_path / "data"
    data.mkdir()
    np.save(data / "field.npy", np.random.default_rng(0).random((6, 5, 4)))
    document = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "src", "type": "stk.source.file@1", "params": {"binding": "data", "path": "field.npy"}},
        {"id": "vol", "type": "stk.render.volume@1", "inputs": {"in": {"from": "src.out"}}},
        {"id": "scene", "type": "stk.view.scene@1", "inputs": {"layers": [{"from": "vol.layer"}]}},
        {"id": "payload", "type": "stk.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}}}],
        "outputs": {"view": "scene.scene", "payload": "payload.payload"}}
    result = evaluate_request({"graph": document, "profile": "phone"}, resolver=LocalDirResolver({"data": data}),
                              cache_dir=None, blob_sink=MemoryBlobSink(), cache=GraphCache())
    reductions = result["outputs"]["view"]["manifest"]["budget"]["reductions"]
    assert reductions and "quantized" in reductions[0]["reason"]
    reduced = [w for w in result["warnings"] if w["code"] == "payload_reduced"]
    by_scene = [w for w in reduced if w["node"] == "scene"]
    assert len(by_scene) == len(reductions) and by_scene[0]["path"] == "/outputs/view"
    assert by_scene[0]["severity"] == "warning" and "'vol'" in by_scene[0]["message"]
    assert [w for w in reduced if w["node"] == "payload"]  # the payload node's own warning, as before


def test_table_outputs_list_their_column_names_in_order(tmp_path):
    from suan.data.model import Table
    from suan.graph.service import _Delivery
    table = Table(id="t")
    for name in ("value", "name", "count", "10"):  # an integer-like name moves first in a JS object
        table.add_column(name, np.arange(3) if name != "name" else np.array(["a", "b", "c"]))
    delivery = _Delivery(MemoryBlobSink(), profile="web", plot_format="svg", max_bytes=None, encode_scene=None,
                         render_plot=None)
    inline = delivery.deliver("t", "table", table)
    assert inline["column_names"] == ["value", "name", "count", "10"] == list(inline["columns"])
    big = Table(id="big")
    big.add_column("z", np.arange(40_000, dtype=np.float64))
    big.add_column("a", np.arange(40_000, dtype=np.float64))
    offloaded = delivery.deliver("big", "table", big)
    assert "blob" in offloaded and offloaded["column_names"] == ["z", "a"]
