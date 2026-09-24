"""Content-keyed source nodes on live muFerro runs (docs/specs/stk-graph-v1.md §5, review finding M6).

A fingerprinted source node is keyed by the content it resolved: the step/policy
selectors and the upstream frame listing are not part of its keys, so aliases of
one frame share a cache entry and a growing live run (energy rows, progress
lines, new frames) does not invalidate what was derived from an unchanged frame.
"""
import copy

import pytest

np = pytest.importorskip("numpy")

from mupro_fake import write_case, write_outputs  # noqa: E402
from suan.graph.cache import GraphCache  # noqa: E402
from suan.graph.catalog import default_registry  # noqa: E402
from suan.graph.evaluator import evaluate  # noqa: E402
from suan.graph.resolve import LocalDirResolver  # noqa: E402

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
