"""Colormaps: built-in LUTs, the spec mapping, stk:orientation-hsl, categorical palettes, transfer functions."""
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from suan.render import colormaps as cm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs" / "specs" / "examples" / "payload-v2" / "manifest.json"


def test_builtin_luts_are_256_rgba8_and_match_matplotlib():
    assert cm.colormap_names() == ("viridis", "cividis", "coolwarm", "turbo", "gray")
    assert cm.canonical_name("grey") == cm.canonical_name("Gray") == "gray"
    with pytest.raises(KeyError, match="built-in"):
        cm.canonical_name("jet")
    for name in cm.colormap_names():
        lut = cm.lut_rgba8(name)
        assert lut.shape == (256, 4) and lut.dtype == np.uint8 and (lut[:, 3] == 255).all()
        assert cm.lut_rgba8_bytes(name) == lut.tobytes()
        assert cm.lut_colors(name)[0] == tuple(lut[0] / 255)
    gray = cm.lut_rgba8("grey")
    assert (gray[:, 0] == np.arange(256)).all() and (gray[:, 0] == gray[:, 2]).all()
    matplotlib = pytest.importorskip("matplotlib")
    for name in ("viridis", "cividis", "coolwarm", "turbo"):
        reference = np.floor(matplotlib.colormaps[name](np.arange(256))[:, :3] * 255 + 0.5).astype(np.uint8)
        assert (cm.lut_rgba8(name)[:, :3] == reference).all(), name


def test_scalar_mapping_follows_the_spec_bins_and_out_of_range_colours():
    lut = cm.lut_rgba8("gray")
    index = cm.lut_index([0.0, 0.5, 1.0, 255 / 256, 254.9 / 256, -0.1, 1.1, float("nan")], (0.0, 1.0))
    assert index.tolist() == [0, 128, 255, 255, 254, -1, 256, -2]
    assert cm.lut_index([3.0, 5.0], (3.0, 3.0)).tolist() == [128, 128]       # hi == lo -> t = 0.5
    rgba = cm.map_scalars([-1.0, 2.0, float("nan"), 0.5], lut, (0.0, 1.0))
    assert rgba[0].tolist() == [0, 0, 0, 1] and rgba[1].tolist() == [1, 1, 1, 1]
    assert rgba[2].tolist() == list(cm.DEFAULT_NAN_COLOR) and rgba[3][0] == pytest.approx(128 / 255)
    rgba = cm.map_scalars([-1.0, 2.0, float("nan")], lut, (0.0, 1.0), below_color=[0, 0, 1],
                          above_color=[1, 0, 0, 0.5], nan_color=[0, 1, 0])
    assert rgba.tolist() == [[0, 0, 1, 1], [1, 0, 0, 0.5], [0, 1, 0, 1]]
    with pytest.raises(ValueError):
        cm.map_scalars([0.0], lut[:10], (0, 1))


# domain-classifiers.md §6.2 reference table (lightness range [0, 1]).
ORIENTATION_TABLE = [
    ((1, 0, 0), 1, (255, 0, 0)), ((0, 1, 0), 1, (128, 255, 0)), ((-1, 0, 0), 1, (0, 255, 255)),
    ((0, -1, 0), 1, (128, 0, 255)), ((0, 0, 1), 1, (255, 255, 255)), ((0, 0, -1), 1, (0, 0, 0)),
    ((0.5, 0, 0), 1, (191, 64, 64)), ((1, 0, 1), math.sqrt(2), (255, 180, 180)),
    ((1, 1, 1), math.sqrt(3), (255, 228, 147)), ((0, 0, 0), 1, (128, 128, 128)),
]


@pytest.mark.parametrize("vector, magnitude, expected", ORIENTATION_TABLE)
def test_orientation_hsl_reference_values(vector, magnitude, expected):
    assert cm.rgba8(cm.orientation_rgb(vector, magnitude))[:3] == expected
    vectorized = cm.orientation_hsl([vector], magnitude)[0]
    assert cm.rgba8(vectorized)[:3] == expected


def test_orientation_hsl_vectorized_equals_scalar_and_handles_edge_cases():
    rng = np.random.default_rng(3)
    vectors = rng.normal(size=(200, 3))
    vectors[:5, :2] = 0.0                              # on the z axis: grey by pz
    vectors[5] = [np.nan, 0, 1]                        # non-finite: mid grey
    big = float(np.linalg.norm(vectors[np.isfinite(vectors).all(axis=1)], axis=1).max())
    batch = cm.orientation_hsl(vectors, big, (0.2, 0.8))
    for vector, rgb in zip(vectors, batch):
        assert np.allclose(rgb, cm.orientation_rgb(vector, big, (0.2, 0.8)), atol=1e-12)
    assert np.allclose(batch[5], (0.5, 0.5, 0.5))
    assert np.allclose(cm.orientation_hsl(vectors[:10]), cm.orientation_hsl(vectors[:10], None))
    assert np.allclose(cm.orientation_hsl([[0, 0, 0]], 0.0), [[0.5, 0.5, 0.5]])


def test_hsl_to_rgb_scalar_and_vector_agree():
    hues = np.linspace(0, 720, 97)
    sats = np.linspace(0, 1, 97)
    lights = np.linspace(0, 1, 97)[::-1]
    batch = cm.hsl_to_rgb(hues, sats, lights)
    for h, s, l, rgb in zip(hues, sats, lights, batch):
        assert np.allclose(cm.hsl_to_rgb(float(h), float(s), float(l)), rgb)


def test_stk_categorical_palette_and_category_precedence():
    # domain-classifiers.md §6.5 first values
    for value, expected in ((1, (0.825, 0.175, 0.175)), (2, (0.133, 0.627, 0.2771)), (3, (0.6613, 0.373, 0.867)),
                            (4, (0.825, 0.744, 0.175))):
        assert np.allclose(cm.stk_categorical_color(value), expected, atol=5e-5)
    assert cm.stk_categorical_color(0) == (0.75, 0.75, 0.75) and cm.stk_categorical_color(-1) == (1.0, 1.0, 1.0)
    assert cm.stk_categorical_color(-5) == (0.5, 0.5, 0.5)
    assert cm.category_color({"value": 3, "name": "x", "color": [0.1, 0.2, 0.3]}, "stk:categorical") == (0.1, 0.2, 0.3)
    assert cm.category_color({"value": 1, "name": "T[100]", "direction": [1, 0, 0]},
                             "stk:cubic-26-orientation") == pytest.approx((1.0, 0.0, 0.0))
    assert cm.category_color({"value": 5, "name": "T[001]", "direction": [0, 0, 1]},     # lightness [0.2, 0.8]
                             "stk:cubic-26-orientation") == pytest.approx((0.8, 0.8, 0.8))
    assert cm.category_color({"value": 1, "name": "a"}, None) == cm.stk_categorical_color(1)


def test_cubic26_palette_matches_the_payload_example():
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    palette = next(c for c in example["colormaps"] if c["id"] == "pal0")
    categories = [{k: v for k, v in entry.items() if k != "color"} for entry in palette["entries"]]
    entries = cm.palette_entries(categories, "stk:cubic-26-orientation")
    assert entries == palette["entries"]
    extra = cm.palette_entries(categories[:3], "stk:cubic-26-orientation", values=[1, 99])
    assert extra[-1] == {"value": 99, "name": "unknown(99)",
                         "color": [round(c, 6) for c in cm.stk_categorical_color(99)]}
    assert cm.to_hex(entries[2]["color"]) == "#ff0000"


def test_transfer_function_helpers():
    points = cm.opacity_points([[1.0, 0.8], [0.0, 0.0], [0.5, 0.1]], (10.0, 20.0))
    assert points == [[10.0, 0.0], [15.0, 0.1], [20.0, 0.8]]
    assert cm.opacity_at([0.0, 12.5, 30.0], points).tolist() == pytest.approx([0.0, 0.05, 0.8])
    tf = cm.transfer_function("cm0", (0, 2), [[0, 0], [1, 1]])
    assert tf == {"colormap": "cm0", "range": [0.0, 2.0], "opacity": [[0.0, 0.0], [2.0, 1.0]]}
    alpha = cm.opacity_lut([[0, 0], [1, 1]], (0, 1))
    assert alpha[0] == pytest.approx(0.5 / 256) and alpha[-1] == pytest.approx(255.5 / 256)
    lut = cm.transfer_function_rgba8("viridis", (0.0, 1.0), [[0.0, 0.0], [1.0, 1.0]])
    assert lut[0, 3] == 0 and lut[-1, 3] == 255 and (lut[:, :3] == cm.lut_rgba8("viridis")[:, :3]).all()
