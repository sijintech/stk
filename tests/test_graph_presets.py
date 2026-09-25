"""Graph presets (suan/graph/presets/*.json): validation, the muFerro domain view end to end, view.build parity."""
from itertools import product
import json
import math
import os
from pathlib import Path
import time

import pytest

from suan.graph import catalog
from suan.graph.registry import Registry
from suan.graph.schema import validate_graph

ROOT = Path(__file__).resolve().parents[1]
PRESETS = ("energy-plot", "iso", "muferro-domains", "muferro-polarization-glyphs", "slice", "vectors", "volume")


def spec_registry():
    """The frozen spec catalog as a declaration-only registry (what the hub validates with, NumPy-free)."""
    return Registry.from_catalog(json.loads((ROOT / "docs/specs/catalog/stk-catalog-m1.json").read_text(encoding="utf-8")))


def test_every_preset_validates_against_the_spec_and_live_catalogs():
    listed = catalog.list_presets(spec_registry())
    assert [p["id"] for p in listed] == list(PRESETS)
    live = catalog.build_registry(entry_points=False)
    for preset in listed:
        for registry in (spec_registry(), live):
            issues = validate_graph(preset["graph"], registry)
            assert issues == [], (preset["id"], [(i.code, i.path, i.message) for i in issues])
        assert preset["name"] and preset["description"] and preset["parameters"]
        names = [b["name"] for b in preset["bindings"]]
        assert names == (["run"] if preset["id"] in ("energy-plot", "muferro-domains", "muferro-polarization-glyphs")
                         else ["data"])
        assert all(b["description"] for b in preset["bindings"])
        assert catalog.load_preset(preset["id"]) == preset["graph"]
        for name in preset["graph"]["outputs"]:
            assert name in ("view", "image", "fractions", "families", "energy", "table")


def test_presets_hold_no_paths_and_expose_their_thresholds():
    for preset_id in PRESETS:
        graph = catalog.load_preset(preset_id)
        text = json.dumps(graph)
        assert "/home" not in text and "\\\\" not in text
        parameters = {p["name"] for p in graph["parameters"]}
        if preset_id.startswith("muferro-") and preset_id != "muferro-polarization-glyphs":
            assert {"step", "min_magnitude"} <= parameters
        for node in graph["nodes"]:
            if node["type"].startswith("stk.source.") and node["type"] != "stk.source.muferro_frame@1":
                assert node["params"]["binding"] in ("run", "data")


def test_muferro_connector_offers_its_default_presets():
    from suan.connectors.mupro import MuFerroConnector
    graphs = MuFerroConnector().default_graphs({})
    assert [g["id"] for g in graphs] == ["muferro-domains", "energy-plot"]


# ---------------------------------------------------------------------------
# muferro-domains end to end


def stk_directions():
    """The 26 directions in STK numbering, written from the definition (domain-classifiers.md §2.1)."""
    import numpy as np
    reps = [v for v in product((1, 0, -1), repeat=3) if any(v) and next(c for c in v if c) == 1]
    reps.sort(key=lambda v: sum(1 for c in v if c))
    vectors = np.array([w for v in reps for w in (v, tuple(-c for c in v))], dtype=float)
    return vectors / np.linalg.norm(vectors, axis=1)[:, None]


def independent_labels(polar, min_magnitude=0.1, film=True):
    """Labels (x, y, z) of a polarization (x, y, z, 3): argmax cosine, |P| threshold, film layers along z."""
    import numpy as np
    magnitude = np.linalg.norm(polar, axis=-1)
    labels = (np.argmax(polar @ stk_directions().T, axis=-1) + 1).astype(np.int16)
    labels[magnitude <= min_magnitude] = -1
    if film:
        polarized = np.flatnonzero(np.abs(polar).sum(axis=-1).max(axis=(0, 1)) > 1e-6)
        labels[:, :, :polarized[0]] = 0
        labels[:, :, polarized[-1] + 1:] = -1
    return labels


@pytest.fixture
def domain_run(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    from mupro_fake import write_domain_run
    frames = write_domain_run(tmp_path / "run", grid=(16, 12, 10), steps=2, interval=1)
    return tmp_path / "run", {step: np.asarray(values) for step, values in frames.items()}


def evaluate_preset(run, cache_dir, sink, outputs, parameters=None):
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import evaluate_request
    request = {"preset": "muferro-domains", "outputs": outputs, "parameters": parameters or {}}
    return evaluate_request(request, resolver=LocalDirResolver({"run": run}), cache_dir=cache_dir, blob_sink=sink,
                            registry=catalog.build_registry(entry_points=False))


def test_muferro_domains_end_to_end(domain_run, tmp_path, offscreen_probe):
    import numpy as np
    from suan.graph.evaluator import evaluate
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink
    from suan.render.payload import decode
    run, frames = domain_run
    expected = independent_labels(frames[2])  # the latest step
    present = sorted(set(np.unique(expected).tolist()) - {-1, 0})
    assert len(present) == 4 and {-1, 0} <= set(np.unique(expected).tolist())
    sink = MemoryBlobSink()
    outputs = ["view", "fractions", "families", "energy"] + (["image"] if offscreen_probe["ok"] else [])
    result = evaluate_preset(run, tmp_path / "cache", sink, outputs)
    assert result["schema"] == "stk.graph-result/1" and set(result["outputs"]) == set(outputs)
    assert result["parameters"]["step"] == {"value": 2, "choices": [0, 1, 2]}

    # The payload: one closed surface per variant present, coloured by the classification's categories.
    view = result["outputs"]["view"]
    assert view["type"] == "payload"
    payload = decode(view["manifest"], sink.blobs)
    layers = {layer["id"]: layer for layer in payload.manifest["layers"]}
    surface = layers["surface_layer"]
    assert surface["type"] == "triangles" and surface["pick"] == {"probe": {"node": "polar", "dataset": "Polar"}}
    label = surface["attributes"]["label"]
    assert label["categorical"] and label["association"] == "cell"
    triangle_labels = payload.array(label["accessor"])
    assert sorted(np.unique(triangle_labels).tolist()) == present
    palette = next(c for c in payload.manifest["colormaps"] if c["id"] == label["palette"])
    entries = {e["value"]: e for e in palette["entries"]}
    assert entries[1]["name"] == "T[100]" and entries[2]["name"] == "T[-100]"
    assert all(entries[v]["color"] != [1.0, 1.0, 1.0] for v in present)
    assert surface["appearance"]["color"]["by"] == "attribute"
    legend = layers["legend"]
    assert legend["type"] == "overlay" and sorted(legend["values"]) == present
    assert "box" in layers and "axes" in layers
    assert payload.manifest["view"]["camera"]["preset"] == "iso"

    # Fractions: counts equal the independent classification; the denominator excludes -1 and 0.
    fractions = result["outputs"]["fractions"]
    columns = fractions["columns"]
    counts = dict(zip(columns["value"], columns["count"]))
    for value in set(np.unique(expected).tolist()):
        assert counts[value] == int((expected == value).sum())
    denominator = int(np.isin(expected, present).sum())
    assert fractions["attrs"]["denominator"] == denominator
    shares = {v: f for v, f in zip(columns["value"], columns["fraction"]) if v in present}
    assert math.isclose(sum(shares.values()), 1.0) and columns["fraction"][columns["value"].index(-1)] == "NaN"
    families = dict(zip(result["outputs"]["families"]["columns"]["family"],
                        result["outputs"]["families"]["columns"]["count"]))
    assert families == {"T": counts[2] + counts[6], "O": counts[13], "R": counts[19]}

    # The energy trace plot and its plotted data.
    energy = result["outputs"]["energy"]
    assert energy["type"] == "plot" and energy["media_type"] == "image/svg+xml"
    assert sink.blobs[energy["blob"]].lstrip().startswith(b"<?xml")
    plotted = json.loads(sink.blobs[energy["data_blob"]])
    assert [-1.125, -2.25] in [series.get("y") for series in _series(plotted)]
    if offscreen_probe["ok"]:
        image = result["outputs"]["image"]
        assert image["media_type"] == "image/png" and (image["width"], image["height"]) == (1600, 1200)
        assert sink.blobs[image["blob"]].startswith(b"\x89PNG")

    # The labels themselves, through the evaluator (the domains node as an extra output).
    graph = catalog.load_preset("muferro-domains")
    graph["outputs"] = {"labels": "domains.out", "surfaces": "surfaces.out"}
    direct = evaluate(graph, registry=catalog.build_registry(entry_points=False),
                      resolver=LocalDirResolver({"run": run}))
    labels = direct.outputs["labels"]
    assert np.array_equal(labels.xyz("domain")[..., 0], expected)
    assert labels.attrs["film"]["substrate_top"] == 1 and labels.attrs["film"]["film_top"] == 7
    assert direct.outputs["surfaces"].attrs["label_surfaces"]["labels"] == present

    # A camera-only change re-runs only the view nodes; every data node is a cache hit.
    again = evaluate_preset(run, tmp_path / "cache", sink, outputs, {"view": "+x"})
    assert set(again["evaluated"]) <= {"camera", "scene", "png"} and "scene" in again["evaluated"]
    assert again["cache"]["hits"] > 0
    camera = decode(again["outputs"]["view"]["manifest"], sink.blobs).manifest["view"]["camera"]
    assert camera["preset"] == "+x"
    assert again["outputs"]["fractions"] == result["outputs"]["fractions"]

    # An earlier step re-runs from the frame reader onward.
    earlier = evaluate_preset(run, tmp_path / "cache", sink, ["fractions"], {"step": 0})
    assert {"polar", "domains", "fractions"} <= set(earlier["evaluated"])
    old = independent_labels(frames[0])
    counts0 = dict(zip(earlier["outputs"]["fractions"]["columns"]["value"],
                       earlier["outputs"]["fractions"]["columns"]["count"]))
    assert all(counts0[v] == int((old == v).sum()) for v in set(np.unique(old).tolist()))


def _series(plotted):
    """Every ``{"x", "y", ...}`` data mapping inside the plotted-data JSON."""
    found = []
    if isinstance(plotted, dict):
        if "y" in plotted and isinstance(plotted["y"], list):
            found.append(plotted)
        for value in plotted.values():
            found.extend(_series(value))
    elif isinstance(plotted, list):
        for value in plotted:
            found.extend(_series(value))
    return found


def test_polarization_glyphs_and_energy_presets(domain_run, tmp_path):
    import numpy as np
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink, evaluate_request
    from suan.render.payload import decode
    run, frames = domain_run
    sink = MemoryBlobSink()
    registry = catalog.build_registry(entry_points=False)
    result = evaluate_request({"preset": "muferro-polarization-glyphs", "outputs": ["view"],
                               "parameters": {"stride": [2, 2, 1], "min_magnitude": 0.1}},
                              resolver=LocalDirResolver({"run": run}), cache_dir=tmp_path / "cache", blob_sink=sink,
                              registry=registry)
    payload = decode(result["outputs"]["view"]["manifest"], sink.blobs)
    layers = {layer["id"]: layer for layer in payload.manifest["layers"]}
    arrows = layers["arrows"]
    lattice = frames[2][::2, ::2, :]
    assert arrows["type"] == "instances" and payload.array(arrows["positions"]).shape[0] == int(
        (np.linalg.norm(lattice, axis=-1) >= 0.1).sum())
    assert arrows["appearance"]["color"]["by"] == "direction"
    assert layers["legend"]["kind"] == "orientation_legend"
    energy = evaluate_request({"preset": "energy-plot"}, resolver=LocalDirResolver({"run": run}),
                              cache_dir=tmp_path / "cache", blob_sink=sink, registry=registry)
    assert energy["outputs"]["energy"]["type"] == "plot"
    assert energy["outputs"]["table"]["columns"]["Total Energy"] == [-1.125, -2.25]


# ---------------------------------------------------------------------------
# view.build parity: the slice / iso / vectors presets reproduce suan.visualization.scene.build_scene


@pytest.fixture
def field_file(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    nx, ny, nz = 14, 12, 10
    x, y, z = np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij")
    field = np.stack([(x - 6.5) + 0.1 * y, (y - 5.5) - 0.05 * z, (z - 4.5) + 0.02 * x * y], axis=-1)
    folder = tmp_path / "data"
    folder.mkdir()
    np.save(folder / "field.npy", field)
    return folder, field


def preset_scene(folder, preset, parameters):
    from suan.graph.evaluator import evaluate
    from suan.graph.resolve import LocalDirResolver
    result = evaluate(catalog.load_preset(preset), registry=catalog.build_registry(entry_points=False),
                      resolver=LocalDirResolver({"data": folder}), outputs=["view"],
                      parameters={"path": "field.npy", **parameters})
    scene = result.outputs["view"]
    return {layer.id: layer for layer in scene.layers}


def sorted_rows(array, decimals=6):
    import numpy as np
    array = np.round(np.asarray(array, dtype=np.float64), decimals)
    return array[np.lexsort(array.T[::-1])]


def test_slice_preset_matches_view_build(field_file):
    import numpy as np
    from suan.visualization.scene import build_scene, load_grid
    folder, field = field_file
    grid = load_grid(folder / "field.npy")
    for axis, index in (("z", None), ("x", 3)):
        built = build_scene(grid, dataset_id="f", mode="slice", component=0, axis="xyz".index(axis), index=index)
        mesh = built["mesh"]
        positions = np.asarray(mesh["positions"]).reshape(-1, 3) + built["manifest"]["render_origin"]
        layer = preset_scene(folder, "slice", {"axis": axis, "index": index})["plane"]
        plane, (w, h) = layer.geometry["plane"], layer.geometry["size"]
        iu, iv = np.meshgrid(np.arange(w), np.arange(h), indexing="xy")
        samples = (np.asarray(plane["origin"]) + np.outer(iu.reshape(-1) / (w - 1), plane["u"])
                   + np.outer(iv.reshape(-1) / (h - 1), plane["v"]))
        values = layer.attributes["field"].scalar(0)
        mine = sorted_rows(np.column_stack([samples, values]))
        theirs = sorted_rows(np.column_stack([positions, mesh["values"]]))
        assert mine.shape == theirs.shape and np.allclose(mine, theirs, atol=1e-6)


def test_iso_preset_matches_view_build(field_file):
    import numpy as np
    from suan.visualization.scene import build_scene, load_grid
    folder, field = field_file
    level = 4.0
    built = build_scene(load_grid(folder / "field.npy"), dataset_id="f", mode="iso", component="magnitude",
                        level=level, max_vertices=40000)
    assert not built["manifest"]["display_reduced"]
    theirs = np.asarray(built["mesh"]["positions"]).reshape(-1, 3) + built["manifest"]["render_origin"]
    their_tris = np.asarray(built["mesh"]["indices"]).reshape(-1, 3)
    layer = preset_scene(folder, "iso", {"levels": [level]})["surface"]
    mine = layer.geometry["positions"]
    tris = layer.geometry["indices"]
    assert np.allclose(layer.attributes["iso_value"].values, level)
    # The same vertices (on grid edges, linear interpolation) and the same surface area.
    assert np.allclose(sorted_rows(np.unique(np.round(mine, 5), axis=0)),
                       sorted_rows(np.unique(np.round(theirs, 5), axis=0)), atol=1e-4)

    def area(points, triangles):
        a, b, c = (points[triangles[:, i]] for i in range(3))
        return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum()
    assert area(mine, tris) == pytest.approx(area(theirs, their_tris), rel=1e-3)


def test_vectors_preset_matches_view_build(field_file):
    import numpy as np
    from suan.render.payload import glyph_scale
    from suan.visualization.scene import build_scene, load_grid
    folder, field = field_file
    max_vertices = 40000
    grid = load_grid(folder / "field.npy")
    built = build_scene(grid, dataset_id="f", mode="vectors", max_vertices=max_vertices)
    stride = max(1, int(np.ceil((np.prod(grid.dimensions) / max(1, max_vertices // 60)) ** (1 / 3))))
    layers = preset_scene(folder, "vectors", {"stride": [stride] * 3, "max_points": 10**6})
    arrows = layers["arrows"]
    positions, directions = arrows.geometry["positions"], arrows.geometry["directions"]
    coords = np.array(list(np.ndindex(tuple((n - 1) // stride + 1 for n in grid.dimensions)))) * stride
    expected = coords * np.array(grid.spacing) + np.array(grid.origin)
    assert sorted_rows(positions).shape == expected.shape
    assert np.allclose(sorted_rows(positions), sorted_rows(expected))
    order = np.lexsort(positions.T[::-1])
    assert np.allclose(np.column_stack([positions, directions])[order],
                       sorted_rows(np.column_stack([expected, field[tuple(coords.T)]]), decimals=12), atol=1e-9)
    # view.build scales arrows by |v| with factor min(spacing) * stride * 0.8 / max|v|: the preset's auto scale.
    factor = min(grid.spacing) * stride * 0.8 / np.linalg.norm(field[tuple(coords.T)], axis=1).max()
    scale = glyph_scale(arrows)
    assert scale["by"] == "magnitude" and scale["factor"] == pytest.approx(factor)
    assert arrows.appearance["center"] is False  # arrows start at the samples, like view.build
    # Arrow extents: view.build's glyph mesh spans the samples plus the scaled vectors.
    mesh = np.asarray(built["mesh"]["positions"]).reshape(-1, 3) + built["manifest"]["render_origin"]
    tips = positions + directions * factor
    lo, hi = np.minimum(positions, tips).min(axis=0), np.maximum(positions, tips).max(axis=0)
    pad = 0.1 * factor * np.linalg.norm(directions, axis=1).max()  # the arrow head's radius
    assert np.all(mesh.min(axis=0) >= lo - pad - 1e-6) and np.all(mesh.max(axis=0) <= hi + pad + 1e-6)
    assert np.allclose(mesh.min(axis=0), lo, atol=pad + 1e-6) and np.allclose(mesh.max(axis=0), hi, atol=pad + 1e-6)


def test_volume_and_iso_presets_on_a_vector_file(field_file):
    import numpy as np
    folder, field = field_file
    volume = preset_scene(folder, "volume", {})
    data = volume["volume"].geometry["data"]
    assert np.allclose(data, np.linalg.norm(field, axis=-1).transpose(2, 1, 0))
    assert volume["bar"].props["kind"] == "scalar_bar"
    iso = preset_scene(folder, "iso", {"levels": [2.0, 4.0, 6.0]})
    assert sorted(np.unique(np.round(iso["surface"].attributes["iso_value"].values, 9)).tolist()) == [2.0, 4.0, 6.0]
    assert iso["bar"].props["kind"] == "scalar_bar" and iso["surface"].props["pick"]["probe"]["node"] == "src"


# ---------------------------------------------------------------------------
# Performance (approved plan: full domains graph at 128^3 cold <= 10 s, a render-only change <= 1.5 s)


@pytest.mark.perf
@pytest.mark.skipif(os.environ.get("STK_PERF") != "1", reason="performance benchmark: set STK_PERF=1")
def test_perf_muferro_domains_128_cubed(tmp_path, offscreen_probe):
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    from mupro_fake import write_domain_run
    from suan.graph.service import MemoryBlobSink
    factor = float(os.environ.get("STK_PERF_FACTOR", "1"))
    write_domain_run(tmp_path / "run", grid=(128, 128, 128), steps=1, interval=1, complete=False)
    web = ["view", "fractions", "families", "energy"]
    outputs = web + (["image"] if offscreen_probe["ok"] else [])  # cold: payload + PNG (1600 x 1200)
    sink = MemoryBlobSink()

    def timed(requested, parameters=None):
        started = time.perf_counter()
        result = evaluate_preset(tmp_path / "run", tmp_path / "cache", sink, requested, parameters)
        return result, time.perf_counter() - started
    cold, cold_seconds = timed(outputs)
    warm, render_seconds = timed(web, {"view": "+z"})  # the interactive path: a new payload for the viewer
    report = (f"\nmuferro-domains 128^3: cold {cold_seconds:.2f} s (PNG {'yes' if 'image' in outputs else 'no'}), "
              f"render-only payload {render_seconds:.2f} s")
    if offscreen_probe["ok"]:
        png, png_seconds = timed(outputs, {"view": "-z"})
        report += f", render-only payload + PNG {png_seconds:.2f} s (png node {png['timings'].get('png', 0):.2f} s)"
    timings = {node: round(seconds, 3) for node, seconds in sorted(cold["timings"].items(), key=lambda kv: -kv[1])}
    print(report + f"; cold node timings {timings}")
    assert set(warm["evaluated"]) <= {"camera", "scene"}
    assert cold_seconds <= 10.0 * factor, cold_seconds
    assert render_seconds <= 1.5 * factor, render_seconds
    assert np.isfinite(cold["outputs"]["fractions"]["attrs"]["denominator"])


def test_muferro_domains_with_nothing_classified_still_draws(domain_run, tmp_path, offscreen_probe):
    # Spec §14: a node that produces nothing returns an empty result and warns; the view, its legend and the
    # image are still delivered (a zero initial frame, or a threshold above every |P|).
    from suan.graph.service import MemoryBlobSink
    from suan.render.payload import decode
    run, _ = domain_run
    sink = MemoryBlobSink()
    outputs = ["view", "fractions"] + (["image"] if offscreen_probe["ok"] else [])
    result = evaluate_preset(run, tmp_path / "cache", sink, outputs, {"min_magnitude": 50.0})
    assert sorted(result["outputs"]) == sorted(outputs) and not result.get("errors")
    codes = {(w["node"], w["code"]) for w in result["warnings"]}
    assert {("surfaces", "empty_result"), ("legend", "empty_result")} <= codes
    payload = decode(result["outputs"]["view"]["manifest"], sink.blobs)
    layers = {layer["id"]: layer for layer in payload.manifest["layers"]}
    domains = layers["surface_layer"]
    assert domains["type"] == "triangles" and payload.array(domains["positions"]).shape[0] == 0
    assert domains["attributes"]["label"]["association"] == "cell"  # the colouring field is kept
    assert layers["legend"]["kind"] == "legend" and layers["legend"]["values"] == []


def test_energy_outputs_before_the_first_energy_row(domain_run, tmp_path):
    # A live run without energy_out.dat (or with only its header) names muFerro's columns all the same.
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink, evaluate_request
    run, _ = domain_run
    registry = catalog.build_registry(entry_points=False)
    header = "      step     " + "".join(f"{h:>18}" for h in ("Elastic Energy", "Electric Energy", "Landau Energy",
                                                            "Gradient P Energy", "Total Energy")) + "\n"
    for label, content in (("missing", None), ("header only", header)):
        energy = run / "energy_out.dat"
        if content is None:
            energy.unlink(missing_ok=True)
        else:
            energy.write_text(content)
        for preset, outputs in (("energy-plot", ["energy", "table"]), ("muferro-domains", ["energy"])):
            result = evaluate_request({"preset": preset, "outputs": outputs}, resolver=LocalDirResolver({"run": run}),
                                      cache_dir=tmp_path / label, blob_sink=MemoryBlobSink(), registry=registry)
            assert sorted(result["outputs"]) == sorted(outputs) and not result.get("errors"), (label, preset)
            assert result["outputs"]["energy"]["type"] == "plot"


def test_presets_find_a_case_submitted_with_input_dir(tmp_path):
    # `suan mupro submit --input DIR` keeps the case in DIR/ of the task and records case_dir in stk-mupro.json.
    pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    from mupro_fake import write_domain_run
    from suan.graph.evaluator import EvaluationFailed, evaluate
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink, evaluate_request
    task = tmp_path / "task"
    write_domain_run(task / "mycase", grid=(8, 6, 4), steps=2, interval=1)
    (task / "stk-mupro.json").write_text(json.dumps({"schema_version": 1, "case_dir": "mycase",
                                                      "state": "succeeded"}))
    registry = catalog.build_registry(entry_points=False)
    resolver = LocalDirResolver({"run": task})
    result = evaluate_request({"preset": "muferro-domains", "outputs": ["fractions", "energy"]}, resolver=resolver,
                              cache_dir=tmp_path / "cache", blob_sink=MemoryBlobSink(), registry=registry)
    assert not result.get("errors") and result["parameters"]["step"] == {"value": 2, "choices": [0, 1, 2]}
    graph = catalog.load_preset("muferro-domains")
    run_node = next(node for node in graph["nodes"] if node["id"] == "run")
    assert "case_dir" not in run_node["params"]  # the catalog default, "auto"
    run_node["params"]["case_dir"] = "."  # the binding root holds no frames
    with pytest.raises(EvaluationFailed) as error:
        evaluate(graph, registry=registry, resolver=resolver, outputs=["fractions"])
    assert error.value.errors[0]["code"] == "frame_not_found"
    run_node["params"]["case_dir"] = "mycase"
    assert evaluate(graph, registry=registry, resolver=resolver, outputs=["fractions"]).outputs["fractions"].n_rows
    # An unsafe recorded path falls back to the binding root.
    (task / "stk-mupro.json").write_text(json.dumps({"case_dir": "../elsewhere"}))
    run_node["params"].pop("case_dir")
    with pytest.raises(EvaluationFailed) as error:
        evaluate(graph, registry=registry, resolver=resolver, outputs=["fractions"])
    assert error.value.errors[0]["code"] == "frame_not_found"


def test_table_outputs_carry_their_column_order(domain_run, tmp_path):
    from suan.graph.service import MemoryBlobSink
    run, _ = domain_run
    result = evaluate_preset(run, tmp_path / "cache", MemoryBlobSink(), ["fractions", "families"])
    for name in ("fractions", "families"):
        table = result["outputs"][name]
        assert table["column_names"] == list(table["columns"]), name
    assert result["outputs"]["fractions"]["column_names"][:2] == ["value", "name"]
    # The hub stores results in their own key order (requests stay canonical for idempotency).
    from suan.control.store import ControlStore
    store = ControlStore(tmp_path / "hub")
    request = {"id": "a" * 32, "node_id": "b" * 32, "kind": "graph.evaluate", "payload": {"preset": "muferro-domains"}}
    store.create_action(request)
    store.complete(request["id"], request["node_id"], result)
    stored = store.action(request["id"])["result"]["outputs"]["fractions"]
    assert list(stored["columns"]) == result["outputs"]["fractions"]["column_names"]
    assert list(stored) == list(result["outputs"]["fractions"])
