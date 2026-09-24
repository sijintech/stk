"""Clean-room orientation classifier, numbering, palettes and colours (docs/specs/domain-classifiers.md).

Reference values come from the spec (physics and definitions). toolkits/sviz/nt_vtk.py and
mupro_domain.json are used only to cross-check the stk-legacy numbering and palette.
"""
from pathlib import Path
import json
import math
import os
import re
import time

import pytest

np = pytest.importorskip("numpy")

from suan.analysis import palettes  # noqa: E402
from suan.analysis.orientation import (LEGACY_ORDER, OrientationError, classify, classify_image, cubic26,  # noqa: E402
                                       direction_set, orientation_classify, orientation_rgb, rgb8)
from suan.data.model import ImageData  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# domain-classifiers.md §2.3: STK label -> (vector, STK name, legacy label, legacy name, colour).
TABLE = [
    ((1, 0, 0), "T[100]", 21, "T1+(+,0,0)", (1.0000, 0.0000, 0.0000)),
    ((-1, 0, 0), "T[-100]", 22, "T1-(-,0,0)", (0.0000, 1.0000, 1.0000)),
    ((0, 1, 0), "T[010]", 23, "T2+(0,+,0)", (0.5000, 1.0000, 0.0000)),
    ((0, -1, 0), "T[0-10]", 24, "T2-(0,-,0)", (0.5000, 0.0000, 1.0000)),
    ((0, 0, 1), "T[001]", 25, "T3+(0,0,+)", (0.8000, 0.8000, 0.8000)),
    ((0, 0, -1), "T[00-1]", 26, "T3-(0,0,-)", (0.2000, 0.2000, 0.2000)),
    ((1, 1, 0), "O[110]", 9, "O1+(+,+,0)", (1.0000, 0.7500, 0.0000)),
    ((-1, -1, 0), "O[-1-10]", 10, "O1-(-,-,0)", (0.0000, 0.2500, 1.0000)),
    ((1, 0, 1), "O[101]", 13, "O3+(+,0,+)", (1.0000, 0.4243, 0.4243)),
    ((-1, 0, -1), "O[-10-1]", 14, "O3-(-,0,-)", (0.0000, 0.5757, 0.5757)),
    ((1, 0, -1), "O[10-1]", 15, "O4+(+,0,-)", (0.5757, 0.0000, 0.0000)),
    ((-1, 0, 1), "O[-101]", 16, "O4-(-,0,+)", (0.4243, 1.0000, 1.0000)),
    ((1, -1, 0), "O[1-10]", 11, "O2+(+,-,0)", (1.0000, 0.0000, 0.7500)),
    ((-1, 1, 0), "O[-110]", 12, "O2-(-,+,0)", (0.0000, 1.0000, 0.2500)),
    ((0, 1, 1), "O[011]", 17, "O5+(0,+,+)", (0.7121, 1.0000, 0.4243)),
    ((0, -1, -1), "O[0-1-1]", 18, "O5-(0,-,-)", (0.2879, 0.0000, 0.5757)),
    ((0, 1, -1), "O[01-1]", 19, "O6+(0,+,-)", (0.2879, 0.5757, 0.0000)),
    ((0, -1, 1), "O[0-11]", 20, "O6-(0,-,+)", (0.7121, 0.4243, 1.0000)),
    ((1, 1, 1), "R[111]", 1, "R1+(+,+,+)", (1.0000, 0.8366, 0.3464)),
    ((-1, -1, -1), "R[-1-1-1]", 2, "R1-(-,-,-)", (0.0000, 0.1634, 0.6536)),
    ((1, 1, -1), "R[11-1]", 6, "R3-(+,+,-)", (0.6536, 0.4902, 0.0000)),
    ((-1, -1, 1), "R[-1-11]", 5, "R3+(-,-,+)", (0.3464, 0.5098, 1.0000)),
    ((1, -1, 1), "R[1-11]", 7, "R4+(+,-,+)", (1.0000, 0.3464, 0.8366)),
    ((-1, 1, -1), "R[-11-1]", 8, "R4-(-,+,-)", (0.0000, 0.6536, 0.1634)),
    ((1, -1, -1), "R[1-1-1]", 4, "R2-(+,-,-)", (0.6536, 0.0000, 0.4902)),
    ((-1, 1, 1), "R[-111]", 3, "R2+(-,+,+)", (0.3464, 1.0000, 0.5098)),
]


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def rotate(v, degrees):
    """Rotate unit vector v by `degrees` about an axis perpendicular to it."""
    v = unit(v)
    helper = np.array([0.0, 0.0, 1.0]) if abs(v[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    axis = unit(np.cross(v, helper))
    angle = math.radians(degrees)
    return v * math.cos(angle) + np.cross(axis, v) * math.sin(angle)


def test_stk_numbering_is_the_spec_table():
    variants = cubic26("stk")
    assert [v.label for v in variants] == list(range(1, 27))
    for variant, (vector, name, legacy_label, legacy_name, colour) in zip(variants, TABLE):
        assert variant.vector == vector and variant.name == name
        assert variant.family == name[0] and variant.aliases[0] == legacy_name
        assert variant.aliases[1] == legacy_name.split("(")[0]
        np.testing.assert_allclose(variant.direction, unit(vector), atol=1e-15)
        assert tuple(round(c, 4) for c in variant.color) == colour
        assert LEGACY_ORDER[legacy_label - 1] == vector
    assert [v.aliases[2] for v in variants[:6]] == ["a1+", "a1-", "a2+", "a2-", "c+", "c-"]
    # Antiparallel pairs are consecutive: odd label = representative, even label = its negation.
    for odd, even in zip(variants[::2], variants[1::2]):
        assert tuple(-c for c in odd.vector) == even.vector and next(c for c in odd.vector if c) == 1


def test_legacy_numbering_names_and_palette():
    variants = cubic26("stk-legacy")
    by_vector = {v.vector: v for v in variants}
    for vector, name, legacy_label, legacy_name, _ in TABLE:
        variant = by_vector[vector]
        assert variant.label == legacy_label and variant.name == legacy_name and variant.aliases[0] == name
        assert variant.color == palettes.FERRO27[legacy_label]
    assert [v.family for v in variants] == ["R"] * 8 + ["O"] * 12 + ["T"] * 6


@pytest.mark.parametrize("numbering", ["stk", "stk-legacy"])
def test_each_direction_gets_its_own_label(numbering):
    variants = cubic26(numbering)
    vectors = np.array([v.direction for v in variants])
    labels, _ = orientation_classify(np.vstack([vectors, 0.7 * vectors]), numbering=numbering)
    assert labels.dtype == np.int16 and labels.tolist() == list(range(1, 27)) * 2
    # Integer vectors (not normalized) and a 10 degree perturbation keep the label.
    raw = np.array([v.vector for v in variants], dtype=float) * 3.0
    assert classify(raw, variants).tolist() == list(range(1, 27))
    tilted = np.array([rotate(v.direction, 10.0) for v in variants])
    assert classify(tilted, variants, max_angle_deg=11.0).tolist() == list(range(1, 27))
    assert classify(tilted, variants, max_angle_deg=9.0).tolist() == [-1] * 26


def test_subsets_and_custom_sets():
    for set_id, family, first in (("stk:cubic-100", "T", 1), ("stk:cubic-110", "O", 7), ("stk:cubic-111", "R", 19)):
        variants = direction_set(set_id)
        full = cubic26("stk")[first - 1:first - 1 + len(variants)]
        assert [v.label for v in variants] == list(range(1, len(variants) + 1))
        assert all(v.family == family for v in variants)
        assert [(v.name, v.direction, v.color) for v in variants] == [(v.name, v.direction, v.color) for v in full]
        vectors = np.array([v.direction for v in variants])
        assert classify(vectors, variants).tolist() == list(range(1, len(variants) + 1))
    custom = direction_set("custom", directions=[[0, 2, 0], [1, 0, 0]])
    assert [v.name for v in custom] == ["d1", "d2"] and custom[0].direction == (0.0, 1.0, 0.0)
    assert custom[0].family is None and custom[1].color == palettes.categorical_color(2)
    with pytest.raises(OrientationError) as error:
        direction_set("custom", directions=[[0, 0, 0]])
    assert error.value.code == "invalid_direction"
    with pytest.raises(OrientationError) as error:
        direction_set("stk:cubic-100", numbering="stk-legacy")
    assert error.value.code == "numbering_unsupported"
    with pytest.raises(OrientationError):
        direction_set("custom")


def test_thresholds_ties_and_invalid_values():
    variants = cubic26("stk")
    # Magnitude: classified only when |p| > min_magnitude.
    assert classify([[0.1, 0, 0], [0.1000001, 0, 0], [0, 0, 0]], variants).tolist() == [-1, 1, -1]
    assert classify([[0.1, 0, 0]], variants, min_magnitude=0.0).tolist() == [1]
    assert classify([[0, 0, 0]], variants, min_magnitude=0.0).tolist() == [-1]
    # A vector 22 degrees from [001] (its nearest direction) with max_angle 20 is unclassified.
    p = [math.sin(math.radians(22)), 0.0, math.cos(math.radians(22))]
    assert classify([p], variants, max_angle_deg=20).tolist() == [-1]
    assert classify([p], variants, max_angle_deg=25).tolist() == [5]
    # 45 degrees from both [100] and [010] in the T subset: -1 at 20 degrees, a tie (lower label) at 50.
    t_set = direction_set("stk:cubic-100")
    assert classify([[1, 1, 0]], t_set, max_angle_deg=20).tolist() == [-1]
    assert classify([[1, 1, 0]], t_set, max_angle_deg=50).tolist() == [1]
    assert classify([[1, 1, 0]], direction_set("stk:cubic-111")).tolist() == [1]  # R[111] vs R[11-1]
    assert classify([[1, 1, 0]], direction_set("custom", directions=[[0, 1, 0], [1, 0, 0]])).tolist() == [1]
    # Non-finite components are unclassified.
    assert classify([[np.nan, 1, 0], [np.inf, 0, 0], [1, 0, 0]], variants).tolist() == [-1, -1, 1]
    # Huge and tiny vectors keep their direction (|p|^2 used to overflow to inf and classify as T[100]).
    assert classify([[0, 0, -1e160], [0, 0, -1e150], [1e200, 1e200, 0], [1e308, -1e308, 1e308]],
                    variants).tolist() == [6, 6, 7, classify([[1, -1, 1]], variants)[0]]
    assert classify([[0, 1e-200, 0]], variants, min_magnitude=0.0).tolist() == [3]
    assert classify([[0, 1e-200, 0]], variants).tolist() == [-1]
    with pytest.raises(OrientationError):
        classify([[1, 0, 0]], variants, max_angle_deg=0)
    with pytest.raises(OrientationError):
        classify([[1, 0, 0]], variants, min_magnitude=-1)
    # Float32 input and small chunks give the same labels.
    rng = np.random.default_rng(5)
    vectors = rng.standard_normal((1000, 3))
    assert (classify(vectors.astype(np.float32), variants, chunk=7)
            == classify(vectors.astype(np.float32).astype(np.float64), variants)).all()
    vectors[::17] = np.nan
    assert (classify(vectors, variants, chunk=13, threads=4, max_angle_deg=30)
            == classify(vectors, variants, threads=1, max_angle_deg=30)).all()


def _nt_vtk_tables():
    """domainOrth / domainRGB assignments of STK's own MIT nt_vtk.py, applied in file order."""
    source = (ROOT / "toolkits/sviz/nt_vtk.py").read_text(encoding="utf-8")
    tables = {"domainOrth": np.zeros((27, 3)), "domainRGB": np.zeros((27, 3))}
    for name, row, column, expression in re.findall(
            r"(domainOrth|domainRGB)\[(\d+)\]\[(\d+)\]\s*=\s*([-+0-9./()sqrt ]+)", source):
        tables[name][int(row), int(column)] = eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt})
    return tables


def test_cross_check_legacy_against_nt_vtk():
    tables = _nt_vtk_tables()
    legacy = cubic26("stk-legacy")
    for variant in legacy:
        np.testing.assert_allclose(tables["domainOrth"][variant.label], variant.direction, atol=1e-12)
    np.testing.assert_array_equal(tables["domainRGB"], np.array(palettes.FERRO27))


def test_cross_check_legacy_palette_against_mupro_domain_json():
    lut = json.loads((ROOT / "toolkits/sviz/mupro_domain.json").read_text(encoding="utf-8"))[0]
    points = np.array(lut["RGBPoints"], dtype=float).reshape(-1, 4)
    constant = {}
    for (x0, *c0), (x1, *c1) in zip(points[:-1], points[1:]):
        if x1 - x0 == 1.0 and c0 == c1 and float(x0 + 0.5).is_integer():
            constant[int(x0 + 0.5)] = tuple(c0)
    assert constant[-1] == palettes.UNCLASSIFIED
    matching = {label for label, colour in constant.items() if label >= 0 and colour == palettes.FERRO27[label]}
    # The ParaView LUT lacks the constant segment of label 9, which shifts labels 10-12; all other labels agree.
    assert matching == set(range(27)) - {9, 10, 11, 12}
    colours = {tuple(c) for c in points[:, 1:]}
    assert colours - {palettes.UNCLASSIFIED} == set(palettes.FERRO27)


ORIENTATION_REFERENCE = [  # domain-classifiers.md §6.2, [l0, l1] = [0, 1]
    ((1, 0, 0), 1, (1, 0, 0), (255, 0, 0)),
    ((0, 1, 0), 1, (0.5, 1, 0), (128, 255, 0)),
    ((-1, 0, 0), 1, (0, 1, 1), (0, 255, 255)),
    ((0, -1, 0), 1, (0.5, 0, 1), (128, 0, 255)),
    ((0, 0, 1), 1, (1, 1, 1), (255, 255, 255)),
    ((0, 0, -1), 1, (0, 0, 0), (0, 0, 0)),
    ((0.5, 0, 0), 1, (0.75, 0.25, 0.25), (191, 64, 64)),
    ((1, 0, 1), math.sqrt(2), (1, 0.707107, 0.707107), (255, 180, 180)),
    ((1, 1, 1), math.sqrt(3), (1, 0.894338, 0.57735), (255, 228, 147)),
    ((0, 0, 0), 1, (0.5, 0.5, 0.5), (128, 128, 128)),
]


def test_orientation_colours_match_the_reference_table():
    for vector, big, colour, colour8 in ORIENTATION_REFERENCE:
        np.testing.assert_allclose(palettes.orientation_color(vector, big), colour, atol=1e-6)
        assert palettes.to_rgb8(palettes.orientation_color(vector, big)) == colour8
        np.testing.assert_allclose(orientation_rgb([vector], max_magnitude=big)[0], colour, atol=1e-6)
        assert tuple(rgb8(orientation_rgb([vector], max_magnitude=big))[0]) == colour8
    # Default M = the largest magnitude; half magnitude gives saturation 0.5.
    colours = orientation_rgb([[2, 0, 0], [1, 0, 0]])
    np.testing.assert_allclose(colours, [[1, 0, 0], [0.75, 0.25, 0.25]], atol=1e-12)
    assert palettes.to_hex((1, 0.5, 0)) == "#ff8000" and palettes.to_hex(None) == ""


def test_categorical_palette_values():
    expected = {1: (0.825, 0.175, 0.175), 2: (0.133, 0.627, 0.2771), 3: (0.6613, 0.373, 0.867),
                4: (0.825, 0.744, 0.175)}
    for value, colour in expected.items():
        np.testing.assert_allclose(palettes.categorical_color(value), colour, atol=6e-4)
    assert palettes.categorical_color(0) == palettes.SUBSTRATE and palettes.categorical_color(-1) == (1, 1, 1)
    assert palettes.categorical_color(-5) == (0.5, 0.5, 0.5)
    assert palettes.palette_color("stk:cubic-26-orientation", 0) == palettes.SUBSTRATE
    assert palettes.palette_color("stk-legacy:ferro27", 0) == palettes.FERRO27[0]
    with pytest.raises(ValueError):
        palettes.palette_color("stk:cubic-26-orientation", 3)
    with pytest.raises(ValueError):
        palettes.palette_color("nope", 1)


def domain_image(nz=6):
    """Four domains (+x, -x, +y, -z) over two layers of substrate and one of air (z, y, x, c)."""
    image = ImageData((4, 2, nz), id="Polar")
    polar = np.zeros((nz, 2, 4, 3))
    polar[2:nz - 1, :, 0] = [1, 0, 0]
    polar[2:nz - 1, :, 1] = [-1, 0, 0]
    polar[2:nz - 1, :, 2] = [0, 0.5, 0]
    polar[2:nz - 1, :, 3] = [0, 0, -0.3]
    polar[3, 0, 3] = [0.0, 0.0, 0.05]  # below the threshold inside the film
    image.add_field("Polar", polar, tensor="vector", component_names=("x", "y", "z"), quantity="polarization")
    return image


def test_classify_image_labels_categories_and_film():
    image = domain_image()
    result = classify_image(image)
    labels = result.array("domain")[..., 0]
    assert result.field("domain").dtype == "int16" and result.field("domain").palette == "stk:cubic-26-orientation"
    assert np.shares_memory(result.array("Polar"), image.array("Polar")) and "domain" not in image
    assert labels[2, 0].tolist() == [1, 2, 3, 6] and (labels[:2] == -1).all() and labels[3, 0, 3] == -1
    field = result.field("domain")
    assert [c.value for c in field.categories] == [-1] + list(range(1, 27))
    assert field.quantity == "domain_variant" and field.unit == "1" and field.category(1).name == "T[100]"
    assert result.kinds() == {"image", "labels"}
    assert result.attrs["orientation"]["min_magnitude"] == 0.1 and result.attrs["orientation"]["unit"] == "unspecified"
    filmed = classify_image(image, film_detection=True, numbering="stk-legacy", output="variant")
    labels = filmed.array("variant")[..., 0]
    assert filmed.attrs["film"]["substrate_top"] == 1 and filmed.attrs["film"]["film_top"] == 4
    assert (labels[:2] == 0).all() and (labels[5] == -1).all() and labels[2, 0].tolist() == [21, 22, 23, 26]
    assert [c.value for c in filmed.field("variant").categories][:2] == [-1, 0]
    assert filmed.field("variant").category(0).color == palettes.FERRO27[0]
    with pytest.raises(OrientationError):
        classify_image(image, component_offset=1)
    with pytest.raises(OrientationError):
        classify_image(image, field="nope")


def test_classify_second_triplet_of_six_columns():
    image = ImageData((2, 1, 1))
    values = np.zeros((1, 1, 2, 6))
    values[0, 0, 0] = [0, 0, 1, 1, 0, 0]
    values[0, 0, 1] = [1, 0, 0, 0, 0, -1]
    image.add_field("PE", values)
    assert classify_image(image, component_offset=3).array("domain")[0, 0, :, 0].tolist() == [1, 6]
    assert classify_image(image).array("domain")[0, 0, :, 0].tolist() == [5, 1]


@pytest.mark.skipif(os.environ.get("STK_PERF") != "1", reason="performance benchmark: set STK_PERF=1")
def test_perf_classify_128_cubed():
    """Milestone-1 target: stk:cubic-26 classification of 128^3 points in <= 1 s (x STK_PERF_FACTOR)."""
    vectors = np.random.default_rng(2).standard_normal((128, 128, 128, 3))
    started = time.perf_counter()
    labels, _ = orientation_classify(vectors)
    elapsed = time.perf_counter() - started
    assert labels.shape == (128, 128, 128)
    assert elapsed <= 1.0 * float(os.environ.get("STK_PERF_FACTOR", "1")), elapsed
