"""suan.graph.evaluator: lazy pull, data/client split, caching, budgets, cancellation and failures."""
from collections import Counter
import json

import pytest

np = pytest.importorskip("numpy")

from graph_testnodes import DATA_NODES, graph, make_registry, write_run  # noqa: E402
from suan.graph.cache import GraphCache  # noqa: E402
from suan.graph.evaluator import EvaluationFailed, evaluate  # noqa: E402
from suan.graph.registry import (Budget, BudgetExceeded, CancelToken, Cancelled, EvaluationResult,  # noqa: E402
                                 Registry)
from suan.graph.resolve import LocalDirResolver  # noqa: E402
from suan.graph.schema import GraphValidationError  # noqa: E402


@pytest.fixture
def run_dir(tmp_path):
    return write_run(tmp_path / "run")


@pytest.fixture
def setup(run_dir):
    registry = make_registry()
    resolver = LocalDirResolver({"run": run_dir})
    cache = GraphCache()

    def run(document=None, **kw):
        registry.runs.clear()
        kw.setdefault("cache", cache)
        return evaluate(document or graph(), registry=registry, resolver=resolver, **kw)
    run.registry, run.resolver, run.cache = registry, resolver, cache
    return run


def runs(setup):
    return {key: value for key, value in setup.registry.runs.items() if value}


def test_full_evaluation_result(setup):
    result = setup()
    assert isinstance(result, EvaluationResult)
    assert set(result.outputs) == {"payload", "image", "stats", "plot", "info", "scene"}
    assert result.output_types == {"payload": "payload", "image": "image", "stats": "table", "plot": "plot",
                                   "info": "value", "scene": "scene"}
    assert result.graph_hash.startswith("sha256:") and len(result.graph_hash) == 71
    assert result.parameters["step"] == {"value": 200, "choices": [0, 100, 200]}
    assert result.parameters["factor"] == {"value": 2.0}
    assert result.parameters["view"] == {"value": "iso"}
    assert result.outputs["info"] == {"dimensions": [4, 3, 2], "fields": ["P"], "step": 200}
    stats = result.outputs["stats"]
    assert stats.column("value")[1] == pytest.approx(71 * 3 * 2)  # max of arange * 3 (third frame) * factor 2
    surface = result.outputs["scene"]["layers"][0]
    assert surface["appearance"] == {"colormap": "viridis", "opacity": 0.8}
    assert result.outputs["scene"]["camera"] == {"preset": "iso"}
    assert result.evaluated == ["frames", "frame", "scale", "surface", "legend", "camera", "scene", "payload",
                                "image", "stats", "plot", "info"]
    assert result.cache == {"hits": 0, "misses": 12}
    assert set(result.keys) == set(result.timings) == set(result.evaluated)
    assert all(len(k["data"]) == 64 and len(k["full"]) == 64 for k in result.keys.values())
    assert [w["code"] for w in result.warnings] == ["test_warning"]
    assert result.warnings[0]["node"] == "stats" and result.warnings[0]["details"] == {"count": 72}
    json.dumps(result.to_json(), allow_nan=False)


def test_lazy_evaluation_pulls_only_ancestors(setup):
    result = setup(outputs=["info"])
    assert result.evaluated == ["frames", "frame", "info"]
    assert set(result.outputs) == {"info"} and set(result.keys) == {"frames", "frame", "info"}
    assert runs(setup) == {"frames": 1, "frame": 1, "info": 1}
    # A cached output does not load its ancestors: only the frame listing (needed for the frame
    # fingerprint) comes from the cache, the frame itself is never loaded.
    result = setup(outputs=["info"])
    assert result.evaluated == [] and result.cache == {"hits": 2, "misses": 0}
    assert set(result.timings) == {"frames", "info"}
    assert runs(setup) == {}


def test_client_stage_changes_rerun_no_data_nodes(setup):
    first = setup()
    changed = graph(surface={"colormap": "coolwarm", "opacity": 0.3})
    second = setup(changed, parameters={"view": "+x"})
    assert not set(second.evaluated) & set(DATA_NODES)
    assert "surface" not in second.evaluated  # geometry reused, only finalize ran
    assert set(second.evaluated) == {"legend", "camera", "scene", "payload", "image"}
    assert runs(setup).get("surface") is None and runs(setup).get("scale") is None
    for node_id in DATA_NODES:
        assert first.keys[node_id] == second.keys[node_id]
    assert first.keys["surface"]["data"] == second.keys["surface"]["data"]
    assert first.keys["surface"]["full"] != second.keys["surface"]["full"]
    layer = second.outputs["scene"]["layers"][0]
    assert layer["appearance"] == {"colormap": "coolwarm", "opacity": 0.3}
    assert second.outputs["scene"]["layers"][1]["colormap"] == "coolwarm"
    assert second.outputs["scene"]["camera"] == {"preset": "+x"}
    # Output-node client params (image size) re-run only that output.
    third = setup(graph(surface={"colormap": "coolwarm", "opacity": 0.3}, image={"width": 128}),
                  parameters={"view": "+x"})
    assert third.evaluated == ["image"]
    assert third.outputs["image"]["width"] == 128


def test_data_change_reruns_only_downstream(setup):
    first = setup()
    second = setup(parameters={"factor": 3.0})
    assert set(second.evaluated) == {"scale", "stats", "surface", "legend", "scene", "payload", "image", "plot"}
    assert "frame" not in second.evaluated and "info" not in second.evaluated
    assert first.keys["frame"] == second.keys["frame"]
    assert first.keys["scale"]["data"] != second.keys["scale"]["data"]
    assert second.outputs["stats"].column("value")[1] == pytest.approx(71 * 3 * 3)


def test_step_change_and_revisit_hits_cache_and_keeps_choices(setup):
    setup()
    earlier = setup(parameters={"step": 100})
    assert "frame" in earlier.evaluated and "info" in earlier.evaluated
    assert earlier.parameters["step"] == {"value": 100, "choices": [0, 100, 200]}
    assert earlier.outputs["info"]["step"] == 100
    revisit = setup(parameters={"step": "latest"})
    assert revisit.evaluated == [] and revisit.cache["misses"] == 0
    assert revisit.parameters["step"] == {"value": 200, "choices": [0, 100, 200]}  # replayed from the cache
    assert [w["code"] for w in revisit.warnings] == ["test_warning"]  # warnings are replayed as well
    between = setup(parameters={"step": 150})  # latest_at_or_before -> the frame of step 100
    assert between.outputs["info"]["step"] == 100
    assert between.parameters["step"] == {"value": 100, "choices": [0, 100, 200]}


def test_new_frames_change_the_source_keys(setup, run_dir):
    first = setup(outputs=["info"])
    (run_dir / "P.00000300.npy").write_bytes((run_dir / "P.00000200.npy").read_bytes())
    second = setup(outputs=["info"])
    assert second.parameters["step"] == {"value": 300, "choices": [0, 100, 200, 300]}
    assert second.keys["frames"]["data"] != first.keys["frames"]["data"]  # the listing is the fingerprint
    assert second.evaluated == ["frames", "frame", "info"]
    (run_dir / "P.00000300.npy").unlink()
    assert setup(outputs=["info"]).evaluated == []  # back to the first listing: everything is cached


def test_disk_cache_is_reused_across_evaluator_instances(run_dir, tmp_path):
    root = tmp_path / "cache"
    first_registry = make_registry()
    first = evaluate(graph(), registry=first_registry, resolver=LocalDirResolver({"run": run_dir}),
                     cache=GraphCache(root))
    registry = make_registry()  # a new process: fresh registry, fresh memory tier
    second = evaluate(graph(), registry=registry, resolver=LocalDirResolver({"run": run_dir}), cache=GraphCache(root))
    ran = {key for key, value in registry.runs.items() if value}
    assert "frame" not in ran and "stats" not in ran and "info" not in ran  # cache="disk" nodes
    assert {"frames", "scale", "surface", "scene", "payload", "image", "plot"} <= ran
    assert second.keys == first.keys
    assert second.outputs["info"] == first.outputs["info"]
    np.testing.assert_array_equal(second.outputs["stats"].column("value"), first.outputs["stats"].column("value"))
    assert second.parameters["step"] == first.parameters["step"]
    assert [w["code"] for w in second.warnings] == ["test_warning"]
    frame = GraphCache(root).get(second.keys["frame"]["data"])
    assert frame.tier == "disk" and not frame.value["out"].array("P").flags.writeable


def test_keys_are_stable_under_reordering_and_float_formatting(setup):
    base = setup(parameters={"factor": 2.0})
    text = json.dumps(graph())
    reordered = json.loads(text)
    reordered["nodes"].reverse()
    for node in reordered["nodes"]:
        if "params" in node:
            node["params"] = dict(reversed(list(node["params"].items())))
        node["label"] = "cosmetic"
    reordered["parameters"].reverse()
    reordered["ui"] = {"positions": {}}
    reordered["name"] = "renamed"
    surface = next(n for n in reordered["nodes"] if n["id"] == "surface")
    surface["params"]["opacity"] = json.loads("8e-1")
    for factor in (2, 2.0, json.loads("20e-1"), json.loads("2.000")):
        other = setup(reordered, parameters={"factor": factor})
        assert other.keys == base.keys
        assert other.graph_hash == base.graph_hash
    assert setup(parameters={"factor": 2.5}).keys["scale"] != base.keys["scale"]


def test_ctx_cached_subkeys_intermediates(setup):
    document = graph(scale={"mode": "cached"})
    setup(document)
    assert setup.registry.runs["scale.norm"] == 1
    setup(graph(scale={"mode": "cached"}, surface={"colormap": "gray"}))
    assert setup.registry.runs["scale.norm"] == 0 and setup.registry.runs["scale"] == 0


def test_cancellation(setup):
    token = CancelToken()
    token.cancel("stop now")
    with pytest.raises(Cancelled, match="stop now") as info:
        setup(cancel=token)
    assert info.value.code == "cancelled" and info.value.partial.outputs == {}
    assert runs(setup) == {}

    document = graph()
    document["nodes"].append({"id": "slow", "type": "test.filter.slow@1", "inputs": {"in": {"from": "frame.out"}},
                              "params": {"steps": 50}})
    document["outputs"]["slow"] = "slow.out"
    token = CancelToken()
    events = []

    def listen(event):
        events.append(event)
        if event["type"] == "progress" and event["fraction"] and event["fraction"] > 0.1:
            token.cancel("user cancelled")
    with pytest.raises(Cancelled) as info:
        setup(document, outputs=["info", "slow"], cancel=token, on_event=listen)
    assert info.value.node == "slow"
    assert info.value.partial.outputs["info"]["step"] == 200  # computed before the cancellation
    assert setup.registry.runs["slow"] == 1
    assert any(e["type"] == "node.failed" and e["code"] == "cancelled" for e in events)


def test_time_memory_and_output_budgets(setup):
    document = graph()
    document["nodes"].append({"id": "slow", "type": "test.filter.slow@1", "inputs": {"in": {"from": "frame.out"}},
                              "params": {"steps": 200, "delay": 0.01}})
    document["outputs"]["slow"] = "slow.out"
    with pytest.raises(BudgetExceeded) as info:
        setup(document, outputs=["slow"], budget=Budget(max_seconds=0.5))
    assert info.value.code == "budget_exceeded" and info.value.node == "slow"
    with pytest.raises(BudgetExceeded, match="outputs hold"):
        setup(outputs=["stats"], budget=Budget(max_output_bytes=100))
    assert setup(outputs=["info"], budget=Budget(max_memory_mb=4096)).outputs["info"]["step"] == 200


def test_node_failure_keeps_independent_outputs(setup):
    events = []
    with pytest.raises(EvaluationFailed) as info:
        setup(graph(scale={"mode": "fail"}), on_event=events.append)
    error = info.value
    assert error.code == "node_failed" and error.node == "scale"
    assert error.errors == [{"code": "node_failed", "message": "ValueError: synthetic failure", "path": "",
                             "node": "scale", "hint": None, "severity": "error"}]
    assert set(error.partial.outputs) == {"info"}
    assert {"stats", "surface", "scene", "payload", "image", "plot"} <= set(error.skipped)
    assert any(e["type"] == "node.failed" and e["node"] == "scale" for e in events)


def test_runtime_error_codes(setup, run_dir):
    with pytest.raises(EvaluationFailed) as info:
        setup(graph(scale={"mode": "missing"}), outputs=["stats"])
    assert info.value.errors[0]["code"] == "unknown_binding" and info.value.node == "scale"
    with pytest.raises(EvaluationFailed) as info:
        setup(graph(frames={"binding": "other"}), outputs=["info"])
    assert info.value.code == "unknown_binding" and info.value.node == "frames"
    with pytest.raises(EvaluationFailed) as info:
        setup(graph(frame={"dataset": "Q"}), outputs=["info"])
    assert info.value.code == "frame_not_found"
    with pytest.raises(EvaluationFailed) as info:  # inputs are read-only: cached values stay intact
        setup(graph(scale={"mode": "inplace"}), outputs=["stats"])
    assert info.value.code == "node_failed" and "read-only" in info.value.message
    assert setup(outputs=["info"]).outputs["info"]["step"] == 200
    frame = setup.cache.get(setup(outputs=["info"]).keys["frame"]["data"]).value["out"]
    assert frame.array("P").max() == 71 * 3


def test_kind_checks_at_run_time(setup):
    document = graph()
    document["nodes"] += [
        {"id": "maybe", "type": "test.filter.maybe_labels@1", "inputs": {"in": {"from": "frame.out"}}},
        {"id": "count", "type": "test.analysis.count_labels@1", "inputs": {"in": {"from": "maybe.out"}}},
    ]
    document["outputs"]["count"] = "count.out"
    with pytest.raises(EvaluationFailed) as info:
        setup(document, outputs=["count"])
    assert info.value.code == "kind_mismatch" and info.value.node == "count"
    next(n for n in document["nodes"] if n["id"] == "maybe")["params"] = {"wrong": "yes"}
    with pytest.raises(EvaluationFailed) as info:
        setup(document, outputs=["count"])
    assert info.value.code == "bad_outputs" and info.value.node == "maybe"


def test_validation_and_unimplemented_types(setup, run_dir):
    document = graph()
    document["nodes"][2]["params"]["factor"] = "big"
    with pytest.raises(GraphValidationError) as info:
        setup(document)
    assert [issue.code for issue in info.value.issues] == ["invalid_param"]
    assert runs(setup) == {}
    with pytest.raises(GraphValidationError):
        setup(parameters={"nope": 1})
    declared = Registry.from_catalog(setup.registry.catalog())  # declarations without implementations
    with pytest.raises(EvaluationFailed) as info:
        evaluate(graph(), registry=declared, resolver=setup.resolver, outputs=["info"])
    assert info.value.code == "unsupported" and info.value.node == "frames"


def test_events_and_default_cache(setup):
    events = []
    result = evaluate(graph(), registry=setup.registry, resolver={"run": setup.resolver.resolve("run")},
                      outputs=["stats"], on_event=events.append)
    kinds = [(e["type"], e.get("node")) for e in events]
    assert kinds[:2] == [("node.started", "frames"), ("node.finished", "frames")]
    assert ("warning", "stats") in kinds
    finished = [e for e in events if e["type"] == "node.finished"]
    assert [e["node"] for e in finished] == result.evaluated
    assert all(e["total"] == 4 and 1 <= e["index"] <= 4 for e in finished)

    def broken(event):
        raise RuntimeError("listener bug")
    result = setup(outputs=["info"], on_event=broken)
    assert "event_callback_failed" in [w["code"] for w in result.warnings]


def test_values_are_shallow_copies_and_read_only(setup):
    result = setup(outputs=["info", "stats"])
    frame = setup.cache.get(result.keys["frame"]["data"]).value["out"]
    assert frame.field_names == ["P"]  # the scale node added a field to its own copy only
    assert not frame.array("P").flags.writeable
    counter = Counter()
    registry = make_registry(counter)
    assert registry.runs is counter
