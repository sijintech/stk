"""stk.render / stk.view / stk.output / stk.plot nodes, called directly with a minimal fake NodeContext.

``run_node`` mimics the evaluator contract (docs/specs/stk-graph-v1.md §4.4):
params are normalized; representation nodes get only data-stage params and
then ``finalize`` attaches the client-stage appearance. Input arrays are made
read-only, as the evaluator hands them over.
"""
import dataclasses
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")

from suan.data.model import Category, CellArray, ImageData, PolyData, Table  # noqa: E402
from suan.graph.nodes import output, plot, render, view  # noqa: E402
from suan.graph.registry import Budget, CancelToken, NodeExecutionError, Registry  # noqa: E402
from suan.render.layers import Layer, Scene  # noqa: E402
from suan.render.payload import Payload, decode  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "specs" / "catalog" / "stk-catalog-m1.json"


class FakeContext:
    def __init__(self, node_type, node_id, *, profile="web", cache_dir=None):
        self.node_type = node_type
        self.node_id = node_id
        self.budget = Budget(profile=profile, max_seconds=120.0)
        self.cancel = CancelToken()
        self.parameters = {}
        self.cache_dir = cache_dir
        self.data_key = "0" * 64
        self.warnings = []

    def resolve(self, binding):
        raise KeyError(binding)

    def check(self):
        self.cancel.raise_if_cancelled()

    def progress(self, fraction=None, message=""):
        pass

    def warn(self, message, *, code="node_warning", **details):
        self.warnings.append((code, message, details))

    def report_choices(self, param, choices, *, value=None):
        pass

    def cached(self, name, compute, *, disk=False):
        return compute()


def run_node(fn, inputs=None, params=None, *, node_id=None, **kw):
    """``(outputs, ctx)`` of one node, following the evaluator's stage rules."""
    node_type = fn.stk_node_type
    ctx = FakeContext(node_type, node_id or node_type.type.rsplit(".", 1)[-1], **kw)
    normalized = node_type.normalize_params(params or {})
    if node_type.stage == "representation":
        data, client = node_type.split_params(normalized)
        result = node_type.wrap_outputs(fn(ctx, dict(inputs or {}), data))
        if node_type.finalize is not None:
            result = node_type.finalize(ctx, result, client)
    else:
        result = node_type.wrap_outputs(fn(ctx, dict(inputs or {}), normalized))
    return result, ctx


def frozen(array):
    array = np.array(array)
    array.flags.writeable = False
    return array


def cubic_categories():
    return (Category(-1, "unclassified", color=(1, 1, 1)), Category(1, "T[100]", direction=(1, 0, 0), family="T"),
            Category(2, "T[-100]", direction=(-1, 0, 0), family="T", color=(0, 1, 1)))


def polar_image(n=(6, 5, 4), origin=(10.0, 20.0, 30.0), spacing=(0.5, 0.5, 1.0)):
    nx, ny, nz = n
    k, j, i = np.meshgrid(np.arange(nz), np.arange(ny), np.arange(nx), indexing="ij")
    polar = np.stack([np.where(i < nx // 2, 1.0, -1.0), 0.1 * j, 0.05 * k], axis=-1)
    image = ImageData(n, origin, spacing, length_unit="nm", id="polar")
    image.add_field("Polar", frozen(polar), tensor="vector", component_names=("x", "y", "z"), unit="C/m2")
    labels = np.where(i < nx // 2, 1, 2).astype(np.int16)[..., None]
    image.add_field("domain", frozen(labels), categories=cubic_categories(), palette="stk:cubic-26-orientation",
                    unit="1")
    return image


def two_squares():
    """Two quads (as polygons) with a categorical cell field and point normals."""
    points = frozen([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [3, 0, 0], [3, 1, 0], [2, 1, 0]])
    polys = CellArray(frozen([0, 4, 8]), frozen([0, 1, 2, 3, 4, 5, 6, 7]))
    poly = PolyData(points, polys=polys, length_unit="nm", id="squares")
    poly.add_field("label", frozen(np.array([1, 2], dtype=np.int32)), association="cell",
                   categories=cubic_categories(), palette="stk:cubic-26-orientation")
    poly.add_field("Normals", frozen(np.tile([0.0, 0.0, 1.0], (8, 1)).astype(np.float32)))
    poly.add_field("height", frozen(np.arange(8.0)), unit="nm")
    poly.add_field("wide", frozen(np.zeros((8, 6))))
    return poly


# -- catalog ----------------------------------------------------------------------------------


def test_declarations_equal_the_frozen_catalog():
    registry = Registry(namespaces={"stk": 1})
    for module in (render, view, output, plot):
        registry.register(module)
    frozen_catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    expected = {n["id"]: n for n in frozen_catalog["nodes"] if n["category"] in ("render", "view", "output", "plot")}
    assert {n["id"]: n for n in registry.catalog()["nodes"]} == expected
    assert all(registry.get(i).impl is not None for i in expected)


def test_node_modules_import_without_numpy():
    code = ("import sys; sys.modules['numpy'] = None; "
            "import suan.graph.nodes.render, suan.graph.nodes.view, suan.graph.nodes.output, suan.graph.nodes.plot; "
            "print('ok')")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr


# -- render -----------------------------------------------------------------------------------


def test_surface_triangulates_polygons_and_keeps_categories():
    out, ctx = run_node(render.surface, {"in": two_squares()},
                        {"color": {"by": "field", "field": "label"}, "opacity": 0.5, "name": "Domains"},
                        node_id="surf")
    layer = out["layer"]
    assert isinstance(layer, Layer) and layer.type == "triangles" and layer.id == "surf" and layer.name == "Domains"
    assert layer.geometry["indices"].tolist() == [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    assert layer.geometry["normals"] is not None and "Normals" not in layer.attributes
    assert layer.attributes["label"].values.tolist() == [1, 1, 2, 2] and layer.attributes["label"].categorical
    assert "wide" not in layer.attributes and ctx.warnings[0][0] == "attribute_skipped"
    assert layer.appearance["opacity"] == 0.5
    info = layer.color_info()
    assert info["categorical"] and {e["value"] for e in info["entries"]} >= {1, 2}
    colors = {e["value"]: e["color"] for e in info["entries"]}
    assert colors[1] == [1.0, 0.0, 0.0] and colors[2] == [0.0, 1.0, 1.0]         # direction colour / own colour
    payload = run_node(output.payload_output, {"scene": run_node(view.scene, {"layers": [layer]})[0]["scene"]})[0]
    manifest = payload["payload"]["manifest"]
    tri = manifest["layers"][0]
    assert tri["appearance"]["color"]["interpolate"] == "nearest" and tri["appearance"]["opacity"] == 0.5
    assert tri["attributes"]["label"]["association"] == "cell"


def test_surface_lines_points_and_attribute_selection():
    points = frozen([[0, 0, 0], [1, 0, 0], [2, 1, 0], [3, 1, 1]])
    lines = PolyData(points, lines=CellArray(frozen([0, 4]), frozen([0, 1, 2, 3])), id="line")
    lines.add_field("id", frozen(np.array([7], dtype=np.int32)), association="cell")
    layer = run_node(render.surface, {"in": lines})[0]["layer"]
    assert layer.type == "lines" and layer.geometry["indices"].tolist() == [[0, 1], [1, 2], [2, 3]]
    assert layer.attributes["id"].values.reshape(-1).tolist() == [7, 7, 7]
    cloud = PolyData(points, id="cloud")
    cloud.add_field("t", frozen(np.arange(4.0)))
    layer = run_node(render.surface, {"in": cloud}, {"attributes": ["t"]})[0]["layer"]
    assert layer.type == "points" and sorted(layer.attributes["t"].values.tolist()) == [0, 1, 2, 3]
    order = layer.attributes["t"].values.astype(int)
    assert np.allclose(layer.geometry["positions"], points[order])
    with pytest.raises(NodeExecutionError, match="No field 'nope'"):
        run_node(render.surface, {"in": cloud}, {"attributes": ["nope"]})


def test_surface_turns_planar_images_into_slice_images():
    image = polar_image(n=(6, 1, 4))
    out, _ = run_node(render.surface, {"in": image}, {"color": {"by": "field", "field": "domain"}})
    layer = out["layer"]
    assert layer.type == "slice_image" and layer.geometry["size"] == [6, 4]
    assert layer.geometry["plane"] == {"origin": [10.0, 20.0, 30.0], "u": [2.5, 0.0, 0.0], "v": [0.0, 0.0, 3.0]}
    domain = layer.attributes["domain"].values
    assert domain.shape == (24,) and domain[:6].tolist() == [1, 1, 1, 2, 2, 2]
    polar = layer.attributes["Polar"].values
    assert polar.shape == (24, 3) and polar[6 * 3 + 5].tolist() == pytest.approx([-1.0, 0.0, 0.15])
    assert layer.grid["dimensions"] == [6, 1, 4]
    with pytest.raises(NodeExecutionError) as error:
        run_node(render.surface, {"in": polar_image()})
    assert error.value.code == "not_planar"


def test_glyphs_are_instances_with_auto_scale_and_orientation_colour():
    rng = np.random.default_rng(0)
    points = frozen(rng.normal(size=(40, 3)))
    vectors = rng.normal(size=(40, 3))
    poly = PolyData(points, id="samples", attrs={"sample_spacing": 0.5})
    poly.add_field("Polar", frozen(vectors), tensor="vector")
    poly.add_field("magnitude", frozen(np.linalg.norm(vectors, axis=1)))
    layer = run_node(render.glyphs, {"in": poly}, {"shape": "cone"}, node_id="gly")[0]["layer"]
    assert layer.type == "instances" and len(layer.geometry["positions"]) == 40
    assert "Polar" not in layer.attributes and "magnitude" in layer.attributes
    assert layer.props["progressive"] == {"shuffled": True, "seed": 0}
    order = np.argsort(layer.attributes["magnitude"].values)
    assert np.allclose(np.sort(np.linalg.norm(layer.geometry["directions"], axis=1)),
                       layer.attributes["magnitude"].values[order])
    scene = run_node(view.scene, {"layers": [layer]})[0]["scene"]
    manifest = run_node(output.payload_output, {"scene": scene})[0]["payload"].manifest
    entry = manifest["layers"][0]
    assert entry["glyph"] == {"shape": "cone", "resolution": 8, "center": True}
    big = float(np.linalg.norm(vectors, axis=1).max())
    assert entry["appearance"]["scale"] == {"by": "magnitude", "factor": pytest.approx(0.8 * 0.5 / big)}
    assert entry["appearance"]["color"]["by"] == "direction"
    assert entry["appearance"]["color"]["max_magnitude"] == pytest.approx(big)
    with pytest.raises(NodeExecutionError):
        run_node(render.glyphs, {"in": poly}, {"vectors": "magnitude"})


def test_volume_layers_encode_per_profile_and_labels_are_categorical():
    image = polar_image()
    layer = run_node(render.volume, {"in": image}, {"field": {"name": "Polar", "component": 0}, "colormap": "grey",
                                                    "opacity": [[0, 0], [1, 1]]})[0]["layer"]
    assert layer.type == "volume" and layer.geometry["data"].shape == (4, 5, 6)
    scene = run_node(view.scene, {"layers": [layer]})[0]["scene"]
    for profile, kind in (("phone", "u8"), ("web", "u16"), ("desktop", "f32")):
        payload = run_node(output.payload_output, {"scene": scene}, {"profile": profile})[0]["payload"]
        entry = payload.layer("volume")
        assert payload.accessor(entry["data"])["type"] == kind
        assert entry["transfer_function"]["range"] == [-1.0, 1.0]
        assert entry["transfer_function"]["opacity"] == [[-1.0, 0.0], [1.0, 1.0]]
        assert payload.colormap(entry["transfer_function"]["colormap"])["name"] == "gray"
    labels = run_node(render.volume, {"in": image}, {"field": "domain"})[0]["layer"]
    entry = run_node(output.payload_output, {"scene": run_node(view.scene, {"layers": [labels]})[0]["scene"]}
                     )[0]["payload"].layer("volume")
    assert entry["sampling"] == "nearest" and entry["value_range"] == [1.0, 2.0]
    magnitude = run_node(render.volume, {"in": image}, {"field": "Polar"})[0]["layer"]
    assert np.allclose(magnitude.geometry["data"], np.linalg.norm(image.array("Polar"), axis=-1))


def test_outline_axes_and_orientation_legend():
    image = polar_image()
    layer = run_node(render.outline, {"in": image}, {"color": [1.0, 0.0, 0.0], "width_px": 2.0})[0]["layer"]
    assert layer.type == "lines" and len(layer.geometry["indices"]) == 12
    assert layer.bounds() == [[10.0, 20.0, 30.0], [12.5, 22.0, 33.0]]
    assert layer.color_info() == {"by": "solid", "solid": [1.0, 0.0, 0.0]}
    axes = run_node(render.axes, {}, {"labels": ["a", "b", "c"], "anchor": "top_left"})[0]["layer"]
    legend = run_node(render.orientation_legend, {}, {"size_px": 90, "title": "P"})[0]["layer"]
    scene = run_node(view.scene, {"layers": [layer, axes, legend]})[0]["scene"]
    manifest = run_node(output.payload_output, {"scene": scene})[0]["payload"].manifest
    entries = {entry["id"]: entry for entry in manifest["layers"]}
    assert entries["outline"]["appearance"]["width_px"] == 2.0
    assert entries["axes"] == {"id": "axes", "type": "overlay", "node": "axes", "kind": "axes_triad",
                               "anchor": "top_left", "size_px": [80.0, 80.0], "labels": ["a", "b", "c"]}
    assert entries["orientation_legend"]["size_px"] == [90.0, 90.0] and entries["orientation_legend"]["title"] == "P"
    assert entries["orientation_legend"]["colormap"] == "stk:orientation-hsl"


def test_scalar_bar_explains_continuous_colouring_and_redirects_categories():
    source = run_node(render.surface, {"in": two_squares()}, {"color": {"by": "field", "field": "height",
                                                                        "colormap": "turbo", "range": [0, None]}},
                      node_id="surf")[0]["layer"]
    bar, ctx = run_node(render.scalar_bar, {"source": source}, {"label_count": 3, "format": ".1f"}, node_id="bar")
    bar = bar["layer"]
    assert bar.props["kind"] == "scalar_bar" and bar.props["colormap"] == "turbo"
    assert bar.props["range"] == [0.0, 7.0] and bar.props["title"] == "height [nm]" and not ctx.warnings
    scene = run_node(view.scene, {"layers": [source, bar]})[0]["scene"]
    payload = run_node(output.payload_output, {"scene": scene})[0]["payload"]
    entry = payload.layer("bar")
    assert entry["colormap"] == payload.layer("surf")["appearance"]["color"]["colormap"]
    assert entry["label_count"] == 3 and entry["format"] == ".1f" and entry["source_layer"] == "surf"
    labelled = run_node(render.surface, {"in": two_squares()}, {"color": {"by": "field", "field": "label"}})[0]
    legend, ctx = run_node(render.scalar_bar, {"source": labelled["layer"]})
    assert legend["layer"].props["kind"] == "legend" and ctx.warnings[0][0] == "use_legend"
    solid = run_node(render.surface, {"in": two_squares()})[0]["layer"]
    with pytest.raises(NodeExecutionError):
        run_node(render.scalar_bar, {"source": solid})


def test_categorical_legend_from_layers_and_datasets():
    layer = run_node(render.surface, {"in": two_squares()}, {"color": {"by": "field", "field": "label"}})[0]["layer"]
    legend = run_node(render.categorical_legend, {"source": layer}, {"title": "Variant", "columns": 2})[0]["layer"]
    assert legend.props["values"] == [1, 2] and legend.props["palette"] == "stk:cubic-26-orientation"
    image = polar_image()
    everything = run_node(render.categorical_legend, {"source": image}, {"only_present": False})[0]["layer"]
    assert everything.props["values"] == [-1, 1, 2] and everything.props["title"] == "domain"
    scene = run_node(view.scene, {"layers": [layer, legend]})[0]["scene"]
    payload = run_node(output.payload_output, {"scene": scene})[0]["payload"]
    entry = payload.layer("categorical_legend")
    assert entry["title"] == "Variant" and entry["columns"] == 2
    assert entry["colormap"] == payload.layer("surface")["attributes"]["label"]["palette"]
    with pytest.raises(NodeExecutionError):
        run_node(render.categorical_legend, {"source": layer}, {"field": "height"})


def test_unknown_colormaps_fail_with_a_stable_code():
    layer = run_node(render.surface, {"in": two_squares()},
                     {"color": {"by": "field", "field": "height", "colormap": "jet"}})[0]["layer"]
    scene = run_node(view.scene, {"layers": [layer]})[0]["scene"]
    with pytest.raises(NodeExecutionError) as error:
        run_node(output.payload_output, {"scene": scene})
    assert error.value.code == "invalid_param" and "jet" in str(error.value)
    with pytest.raises(NodeExecutionError, match="jet"):
        run_node(render.scalar_bar, {"source": layer})


# -- view -------------------------------------------------------------------------------------


def test_camera_presets_numeric_cameras_and_render_origin():
    image = polar_image()
    box = run_node(render.outline, {"in": image})[0]["layer"]
    camera = run_node(view.camera, {}, {"preset": "+x", "zoom": 2.0})[0]["camera"]
    scene = run_node(view.scene, {"layers": [box], "camera": camera}, {"width": 800, "height": 600,
                                                                        "title": "Frame 3"})[0]["scene"]
    assert isinstance(scene, Scene) and scene.render_origin == (11.25, 21.0, 31.5)
    cam = scene.view["camera"]
    radius = np.linalg.norm([2.5, 2.0, 3.0]) / 2
    assert cam["focal_point"] == [11.25, 21.0, 31.5] and cam["view_up"] == [0.0, 0.0, 1.0]
    assert cam["position"][0] - 11.25 == pytest.approx(radius / np.sin(np.radians(15)) / 2)
    assert cam["preset"] == "+x" and cam["frame"] == "grid" and scene.length_unit == "nm"
    assert scene.view["viewport"] == {"width": 800, "height": 600, "magnification": 1, "lock_aspect": True}
    assert scene.layers[-1].props == {"kind": "text", "text": "Frame 3", "anchor": "top", "offset_px": [0, 12],
                                      "font_size_px": 18}
    numeric = run_node(view.camera, {}, {"position": [0, 0, 10], "focal_point": [0, 0, 0]})[0]["camera"]
    cam = run_node(view.scene, {"layers": [box], "camera": numeric}, {"render_origin": [1, 2, 3]})[0]["scene"]
    assert cam.view["camera"]["view_up"] == [0.0, 1.0, 0.0] and cam.render_origin == (1.0, 2.0, 3.0)
    with pytest.raises(NodeExecutionError):
        run_node(view.camera, {}, {"focal_point": [0, 0, 0]})
    twice = run_node(view.scene, {"layers": [box, box]})[0]["scene"]
    assert [layer.id for layer in twice.layers] == ["outline", "outline_1"]


# -- output -----------------------------------------------------------------------------------


def test_payload_output_budget_warning_and_v1_fallback():
    from suan.blender_client.scene import validate_scene
    j, i = np.meshgrid(np.arange(20), np.arange(20), indexing="ij")
    points = np.stack([i.reshape(-1), j.reshape(-1), np.zeros(400)], axis=1).astype(float)
    a = (j[:-1, :-1] * 20 + i[:-1, :-1]).reshape(-1)
    grid = PolyData.from_triangles(frozen(points), np.concatenate([np.stack([a, a + 1, a + 21], axis=1),
                                                                   np.stack([a, a + 21, a + 20], axis=1)]))
    grid.add_field("height", frozen(points[:, 0] * 0.5))
    layer = run_node(render.surface, {"in": grid}, {"color": {"by": "field", "field": "height"}})[0]["layer"]
    scene = run_node(view.scene, {"layers": [layer]})[0]["scene"]
    payload, ctx = run_node(output.payload_output, {"scene": scene},
                            {"profile": "phone", "budget": {"triangles": 100}, "v1_fallback": True})
    payload = payload["payload"]
    assert isinstance(payload, Payload) and set(payload) >= {"manifest", "buffers", "scene_v1"}
    assert all(isinstance(data, bytes) for data in payload["buffers"].values())
    assert payload["manifest"]["source"]["reduced"] and ctx.warnings[0][0] == "payload_reduced"
    assert decode(payload["manifest"], payload["buffers"])
    validate_scene(payload.scene_v1)
    with pytest.raises(NodeExecutionError) as error:
        run_node(output.payload_output, {"scene": scene}, {"budget": {"bytes": 1}})
    assert error.value.code == "budget_exceeded"


def test_image_output_renders_plots_and_reports_missing_gl(monkeypatch, tmp_path):
    table = Table.from_columns({"step": np.arange(5), "E": np.arange(5.0) ** 2}, units={"E": "normalized"})
    spec = run_node(plot.line, {"table": table}, {"y": ["E"], "dpi": 50, "size_in": [4, 3]})[0]["plot"]
    for fmt, magic in (("png", b"\x89PNG"), ("svg", b"<?xml"), ("pdf", b"%PDF")):
        image = run_node(output.image_output, {"source": spec}, {"format": fmt, "width": 300, "height": 200})[0]
        image = image["image"]
        assert image["bytes"].startswith(magic) and image["format"] == fmt
        assert (image["width"], image["height"]) == (300, 200)
    doubled = run_node(output.image_output, {"source": spec}, {"magnification": 2})[0]["image"]
    assert (doubled["width"], doubled["height"]) == (400, 300)
    scene = run_node(view.scene, {"layers": [run_node(render.outline, {"in": polar_image()})[0]["layer"]]})[0]
    with pytest.raises(NodeExecutionError) as error:
        run_node(output.image_output, {"source": scene["scene"]}, {"format": "svg"})
    assert error.value.code == "unsupported"
    monkeypatch.setenv("STK_RENDER_PYTHON", str(tmp_path / "missing-python"))
    with pytest.raises(NodeExecutionError) as error:
        run_node(output.image_output, {"source": scene["scene"]})
    assert error.value.code == "render_unavailable" and "vtk-osmesa" in (error.value.hint or "")


def test_dataset_output_formats(tmp_path):
    image = polar_image()
    npy = run_node(output.dataset_output, {"in": image}, {"format": "npy", "name": "polar"},
                   cache_dir=tmp_path)[0]["file"]
    assert npy["name"] == "polar.npy" and npy["media_type"] == "application/x-npy"
    assert np.load(npy["path"]).shape == (6, 5, 4, 3) and npy["size"] == Path(npy["path"]).stat().st_size
    table = Table.from_columns({"step": np.arange(3), "v": np.array([[1.0, 2.0]] * 3)}, id="t")
    csv = run_node(output.dataset_output, {"in": table}, {"format": "csv"}, cache_dir=tmp_path)[0]["file"]
    assert Path(csv["path"]).read_text(encoding="utf-8").splitlines()[:2] == ["step,v_0,v_1", "0,1.0,2.0"]
    data = run_node(output.dataset_output, {"in": table}, {"format": "json", "precision": "float32"},
                    cache_dir=tmp_path)[0]["file"]
    assert json.loads(Path(data["path"]).read_text(encoding="utf-8"))["columns"]["v"] == [[1.0, 2.0]] * 3
    with pytest.raises(NodeExecutionError) as error:
        run_node(output.dataset_output, {"in": image}, {"format": "csv"}, cache_dir=tmp_path)
    assert error.value.code == "unsupported"
    pytest.importorskip("vtk")
    vti = run_node(output.dataset_output, {"in": image}, {"format": "vti", "fields": ["Polar"]},
                   cache_dir=tmp_path)[0]["file"]
    from suan.visualization.scene import load_grid
    grid = load_grid(vti["path"])
    assert grid.dimensions == (6, 5, 4) and grid.origin == (10.0, 20.0, 30.0)
    assert np.allclose(grid.values, image.xyz("Polar"))
    pytest.importorskip("h5py")
    hdf = run_node(output.dataset_output, {"in": image}, {"format": "vtkhdf", "name": "polar"},
                   cache_dir=tmp_path)[0]["file"]
    from suan.data.vtkhdf import read_vtkhdf
    back = read_vtkhdf(hdf["path"])
    assert hdf["name"] == "polar.vtkhdf" and back.dimensions == image.dimensions
    assert np.array_equal(back.xyz("Polar"), image.xyz("Polar"))


def test_scalar_bar_label_format_is_validated_with_the_graph():
    from suan.graph.schema import check_value
    schema = render.scalar_bar.stk_node_type.params["format"].schema
    for good in (".3g", ".2f", "+.1e", ".0%", "d"):
        assert check_value(good, schema) == [], good
    for bad in ("999999", "{}", ".3d", "abc"):  # "999999" made every label a 999999-character string
        assert check_value(bad, schema), bad


def test_dataset_exports_are_atomic_content_addressed_and_hash_what_they_wrote(tmp_path):
    import hashlib
    import threading
    image = polar_image()
    doubled = image.copy()
    doubled.fields = {"Polar": dataclasses.replace(image.field("Polar"), values=image.array("Polar") * 2)}
    values, errors = [], []

    def export(dataset):
        try:
            values.append(run_node(output.dataset_output, {"in": dataset}, {"format": "npy", "name": "polar"},
                                   cache_dir=tmp_path)[0]["file"])
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
    threads = [threading.Thread(target=export, args=(image if n % 2 else doubled,)) for n in range(16)]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    assert not errors and len(values) == 16
    for value in values:  # every value names a file whose bytes it hashed, however the writers interleaved
        data = Path(value["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == value["sha256"] and len(data) == value["size"]
        assert Path(value["path"]) == tmp_path / "exports" / value["sha256"] / "polar.npy"
    assert len({v["sha256"] for v in values}) == 2  # same name, different content: different files
    assert sorted(p.name for p in (tmp_path / "exports").iterdir()) == sorted({v["sha256"] for v in values})


def test_dataset_exports_without_a_cache_directory_leave_nothing_behind(tmp_path, monkeypatch):
    import hashlib
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    value = run_node(output.dataset_output, {"in": polar_image()}, {"format": "npy"})[0]["file"]
    assert "path" not in value and value["size"] == len(value["bytes"])
    assert hashlib.sha256(value["bytes"]).hexdigest() == value["sha256"]
    assert np.load(io.BytesIO(value["bytes"])).shape == (6, 5, 4, 3)
    assert list(tmp_path.iterdir()) == []  # no stk-export-* directory is leaked


# -- plot -------------------------------------------------------------------------------------


def test_line_plot_spec_with_second_table_and_default_labels():
    from suan.plot.mpl import plot_data
    energy = Table.from_columns({"step": np.arange(1, 7), "Total Energy": -np.arange(1.0, 7.0)},
                                units={"Total Energy": "normalized"}, index="step")
    progress = Table.from_columns({"step": np.arange(1, 7), "completed": np.arange(1, 7) / 6.0})
    spec = run_node(plot.line, {"table": energy, "table2": progress},
                    {"y": ["Total Energy"], "y2": ["completed"], "filters": [{"column": "step", "op": ">", "value": 1}],
                     "last_n": 3, "styles": {"Total Energy": {"color": "C2"}}, "stats": True})[0]["plot"]
    axes = spec["axes"][0]
    assert axes["y"] == {"scale": "linear", "label": "Total Energy", "unit": "normalized"}
    assert axes["x"]["label"] == "step" and axes["y2"]["label"] == "completed"
    assert spec["marks"][0]["style"] == {"label": "Total Energy", "color": "C2"}
    data = plot_data(spec)["marks"]
    assert data[0]["data"]["x"] == [4, 5, 6] and data[0]["data"]["y"] == [-4.0, -5.0, -6.0]
    assert data[1]["data"]["x"] == [4, 5, 6] and data[1]["y_axis"] == "y2"
    with pytest.raises(NodeExecutionError, match="no column"):
        run_node(plot.line, {"table": energy}, {"y": ["missing"]})


def test_heatmap_histogram_and_bar_specs():
    from suan.plot.mpl import plot_data, render
    image = polar_image()
    spec = run_node(plot.heatmap, {"in": image}, {"field": "domain", "axis": "y", "index": 1})[0]["plot"]
    assert spec["marks"][0]["categorical"] is True
    categories = spec["tables"]["slice/categories"]["columns"]
    assert categories["value"] == [-1, 1, 2] and categories["color"] == ["#ffffff", "#ff0000", "#00ffff"]
    z = np.asarray(spec["tables"]["slice"]["columns"]["z"])
    assert z.shape == (4, 6) and z[:, 0].tolist() == [1] * 4 and spec["marks"][0]["extent"] == [9.75, 12.75, 29.5, 33.5]
    assert render(spec, format="png")[:4] == b"\x89PNG"
    continuous = run_node(plot.heatmap, {"in": image}, {"field": {"name": "Polar", "component": 1},
                                                        "range": [0, None]})[0]["plot"]
    mark = continuous["marks"][0]
    assert mark["colorbar"] == {"label": "Polar [C/m2]"} and mark["range"] == [0, None]
    assert np.allclose(continuous["tables"]["slice"]["columns"]["z"], image.array("Polar")[2, :, :, 1])
    hist = run_node(plot.histogram, {"in": image}, {"field": {"name": "Polar", "component": 0}, "bins": 4})[0]["plot"]
    counts, edges = np.histogram(image.array("Polar")[..., 0], bins=4)
    assert hist["tables"]["hist"]["columns"]["count"] == counts.tolist() and hist["marks"][0]["range"] == [-1.0, 1.0]
    assert plot_data(hist)["marks"][0]["data"]["y"] == counts.tolist()
    fractions = Table.from_columns({"value": np.array([1, 2]), "name": np.array(["T[100]", "T[-100]"]),
                                    "fraction": np.array([0.25, 0.75]), "color": np.array(["#ff0000", ""])})
    bars = run_node(plot.bar, {"table": fractions}, {"x": "name", "y": ["fraction"], "color_column": "color",
                                                     "orientation": "horizontal"})[0]["plot"]
    assert bars["marks"][0]["data"] == {"table": "table", "x": "fraction", "y": "name"}
    assert bars["marks"][0]["style"]["colors"] == ["#ff0000", "#808080"]
    assert render(bars, format="svg").lstrip().startswith(b"<?xml")


def test_full_chain_image_to_payload_round_trip():
    image = polar_image(n=(8, 6, 1))
    surface = run_node(render.surface, {"in": image}, {"color": {"by": "field", "field": "Polar",
                                                                 "component": "magnitude"}})[0]["layer"]
    box = run_node(render.outline, {"in": image})[0]["layer"]
    bar = run_node(render.scalar_bar, {"source": surface})[0]["layer"]
    legend = run_node(render.categorical_legend, {"source": image})[0]["layer"]
    scene = run_node(view.scene, {"layers": [surface, box, bar, legend]})[0]["scene"]
    payload = run_node(output.payload_output, {"scene": scene}, {"profile": "phone"})[0]["payload"]
    manifest = json.loads(json.dumps(payload["manifest"]))
    decoded = decode(manifest, payload["buffers"])
    assert [layer["type"] for layer in manifest["layers"]] == ["slice_image", "lines", "overlay", "overlay"]
    assert decoded.layer("surface")["appearance"]["color"]["component"] == "magnitude"
    assert manifest["render_origin"] == [11.75, 21.25, 30.0]
