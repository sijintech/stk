"""Scene v1 downgrade of stk.payload/2 and the scene v1 check: every result passes suan.render.v1.validate_scene."""
import copy
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from render_scenes import glyph_scene, grid_mesh, mixed_scene  # noqa: E402
from suan.render.layers import Attribute, Layer, Scene  # noqa: E402
from suan.render.payload import Payload, encode_scene, read_directory  # noqa: E402
from suan.render.v1 import MAX_INDICES, MAX_VERTICES, glyph_mesh, to_scene_v1, validate_scene  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "specs" / "examples" / "payload-v2"


def test_example_downgrades_to_its_first_triangles_layer():
    payload = read_directory(EXAMPLE)
    scene = validate_scene(to_scene_v1(payload))
    m, mesh = scene["manifest"], scene["mesh"]
    assert m["version"] == 1 and m["field"] == "domain" and m["layer"] == "domains"
    assert m["render_origin"] == [100.0, 50.0, 25.0] and m["value_range"] == [1.0, 19.0]
    assert m["timestep"] == 1000 and m["units"] == "1" and m["coordinate_units"] == "grid index"
    assert len(mesh["positions"]) == 72 and len(mesh["indices"]) == 108 and set(mesh["values"]) == {1.0, 7.0, 19.0}
    assert np.allclose(mesh["positions"], payload.array("mesh_pos"))
    assert m["display_reduced"] is False


def test_instances_expand_to_glyph_triangles():
    payload = encode_scene(glyph_scene())
    only = copy.deepcopy(payload.manifest)
    only["layers"] = [layer for layer in only["layers"] if layer["type"] != "lines"]
    scene = validate_scene(to_scene_v1(Payload(only, payload.blobs)))
    points, tris = glyph_mesh("arrow", 12)
    layer = payload.layer("arrows")
    n = payload.accessor(layer["positions"])["count"]
    assert len(scene["mesh"]["positions"]) == n * len(points) and len(scene["mesh"]["indices"]) == n * 3 * len(tris)
    magnitudes = np.linalg.norm(payload.array(layer["directions"]).astype(np.float64), axis=1)
    assert np.allclose(sorted(set(np.round(scene["mesh"]["values"], 6))), sorted(set(np.round(magnitudes, 6))))
    assert scene["manifest"]["field"] == "direction"
    # Centred arrows span x in [-0.5, 0.5] scaled by factor * |d| around each instance position.
    positions = np.asarray(scene["mesh"]["positions"]).reshape(n, len(points), 3)
    centres = payload.array(layer["positions"]).astype(np.float64)
    factor = layer["appearance"]["scale"]["factor"]
    reach = np.linalg.norm(positions - centres[:, None], axis=2).max(axis=1)
    assert np.allclose(reach, np.hypot(0.5, 0.03) * factor * magnitudes, rtol=1e-3)   # shaft base rim


def test_slice_images_become_two_triangles_per_quad():
    layer = Layer("slice_image", id="img", geometry={"plane": {"origin": [1.0, 2.0, 3.0], "u": [4.0, 0, 0],
                                                               "v": [0, 0, 2.0]}, "size": [5, 3]},
                  attributes={"t": Attribute(np.arange(15.0), unit="K")},
                  appearance={"color": {"by": "field", "field": "t"}})
    payload = encode_scene(Scene(layers=[layer], render_origin=(1.0, 2.0, 3.0)))
    scene = validate_scene(to_scene_v1(payload))
    assert len(scene["mesh"]["positions"]) == 15 and len(scene["mesh"]["indices"]) == 2 * 4 * 2 * 3
    assert scene["mesh"]["positions"][6] == [1.0, 0.0, 1.0] and scene["mesh"]["values"][6] == 6.0
    assert scene["manifest"]["units"] == "K"


def test_large_meshes_are_decimated_to_the_v1_budget():
    points, triangles = grid_mesh(320, origin=(5e5, 0.0, 0.0))
    layer = Layer("triangles", id="big", geometry={"positions": points, "indices": triangles},
                  attributes={"z": Attribute(points[:, 2].copy())})
    payload = encode_scene(Scene(layers=[layer], render_origin=(5e5, 0.0, 0.0)), profile="desktop")
    scene = validate_scene(to_scene_v1(payload))
    mesh = scene["mesh"]
    assert len(mesh["positions"]) <= MAX_VERTICES and len(mesh["indices"]) <= MAX_INDICES
    assert scene["manifest"]["display_reduced"] is True and scene["manifest"]["render_origin"] == [5e5, 0.0, 0.0]
    values = np.asarray(mesh["values"])
    assert values.min() >= -1.0 - 1e-6 and values.max() <= 1.0 + 1e-6


def test_mixed_scene_empty_scene_and_non_finite_values():
    assert validate_scene(to_scene_v1(encode_scene(mixed_scene())))["manifest"]["layer"] == "tri"
    empty = validate_scene(to_scene_v1(encode_scene(Scene(layers=[]))))
    assert empty["mesh"] == {"positions": [], "indices": [], "values": []}
    assert empty["manifest"]["value_range"] == [0.0, 0.0]
    points = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]])
    layer = Layer("triangles", id="nan", geometry={"positions": points, "indices": np.array([[0, 1, 2]])},
                  attributes={"v": Attribute(np.array([np.nan, 2.0, 3.0]))}, appearance={"color": {"by": "field"}})
    scene = validate_scene(to_scene_v1(encode_scene(Scene(layers=[layer]))))
    assert scene["mesh"]["values"] == [2.0, 2.0, 3.0]


@pytest.mark.parametrize("shape", ["arrow", "cone", "sphere", "line", "cube"])
def test_canonical_glyph_meshes(shape):
    points, tris = glyph_mesh(shape, 8)
    assert tris.min() >= 0 and tris.max() < len(points)
    lo, hi = points.min(axis=0), points.max(axis=0)
    if shape in ("arrow", "cone", "line"):
        assert lo[0] == pytest.approx(0.0) and hi[0] == pytest.approx(1.0)
    else:
        assert lo == pytest.approx([-0.5] * 3) and hi == pytest.approx([0.5] * 3)
    with pytest.raises(ValueError):
        glyph_mesh("torus")


def small_scene():
    """A 2 x 2 point scene v1 with two triangles."""
    return {"manifest": {"version": 1, "association": "point", "dataset_id": "check", "field": "t",
                         "dimensions": [2, 2, 1], "origin": [0, 0, 0], "render_origin": [0, 0, 0],
                         "spacing": [1, 1, 1], "value_range": [0.0, 3.0], "units": "1", "coordinate_units": "m",
                         "timestep": 0, "resources": [{"kind": "triangle_mesh", "key": "mesh"}]},
            "mesh": {"positions": [[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0], [1.0, 1, 0]],
                     "values": [0.0, 1.0, 2.0, 3.0], "indices": [0, 1, 2, 1, 3, 2]}}


@pytest.mark.parametrize("mutation", [
    lambda s: s["mesh"]["indices"].append(999999),
    lambda s: s["mesh"]["indices"].extend([0, 1, 999999]),
    lambda s: s["mesh"]["indices"].__setitem__(0, True),
    lambda s: s["mesh"]["positions"][0].__setitem__(0, float("nan")),
    lambda s: s["mesh"]["values"].__setitem__(0, float("inf")),
    lambda s: s["mesh"]["values"].pop(),
    lambda s: s["manifest"].__setitem__("spacing", [0, 1, 1]),
    lambda s: s["manifest"].__setitem__("dimensions", [2, 2.5, 1]),
    lambda s: s["manifest"].__setitem__("value_range", [5, -5]),
    lambda s: s["manifest"].__setitem__("version", 2),
    lambda s: s["manifest"].__setitem__("association", "cell"),
])
def test_validate_scene_rejects_invalid_scene(mutation):
    scene = small_scene()
    assert validate_scene(scene) is scene
    mutation(scene)
    with pytest.raises(ValueError):
        validate_scene(scene)
