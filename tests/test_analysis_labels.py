"""Film detection and label fractions (docs/specs/domain-classifiers.md §4, §5)."""
from pathlib import Path
import math

import pytest

np = pytest.importorskip("numpy")

from suan.analysis.labels import (apply_film, film_detect_image, film_info, film_layer_labels,  # noqa: E402
                                  fractions_tables, label_counts, label_fractions)
from suan.analysis.orientation import classify_image, cubic26  # noqa: E402
from suan.data.dat import read_dat_image  # noqa: E402
from suan.data.model import Category, ImageData  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def stack(nz=10):
    """Substrate (k 0-2, zero), film (k 3-7, layer 5 unpolarized inside), air (k 8-9, zero)."""
    polar = np.zeros((nz, 3, 4, 3))
    polar[3:8] = [0.0, 0.0, 0.4]
    polar[5] = 0.0
    polar[6, 1, 1] = [np.nan, 0, 0]  # non-finite samples are ignored
    return polar


def test_film_info_on_a_constructed_stack():
    info = film_info(stack())
    assert info == {"detected": True, "axis": "z", "epsilon": 1e-6, "substrate_top": 2, "film_bottom": 3,
                    "film_top": 7, "substrate_layers": 3, "film_layers": 5, "air_layers": 2}
    assert film_layer_labels(info, 10).tolist() == [0, 0, 0, 1, 1, 1, 1, 1, -1, -1]
    labels = np.full((10, 3, 4), 5, dtype=np.int16)
    apply_film(labels, info)
    assert labels[:, 0, 0].tolist() == [0, 0, 0, 5, 5, 5, 5, 5, -1, -1]
    # A film starting at k = 0 has no substrate (substrate_top = -1); epsilon is a strict bound.
    polar = stack()
    polar[:3] = 1e-3
    assert film_info(polar)["substrate_top"] == -1 and film_info(polar, epsilon=0.01)["film_bottom"] == 3
    nothing = film_info(np.zeros((4, 2, 2, 3)))
    assert nothing == {"detected": False, "axis": "z", "epsilon": 1e-6, "substrate_top": None, "film_bottom": None,
                       "film_top": None, "substrate_layers": 0, "film_layers": 0, "air_layers": 4}
    assert film_layer_labels(nothing, 4).tolist() == [-1] * 4
    untouched = np.ones((4, 2, 2), dtype=np.int16)
    assert (apply_film(untouched, nothing) == 1).all()
    with pytest.raises(ValueError):
        film_info(stack(), epsilon=-1)


def test_film_detect_image():
    image = ImageData((4, 3, 10), id="Polar")
    image.add_field("Polar", stack(), tensor="vector")
    result, info = film_detect_image(image)
    field = result.field("film")
    assert field.dtype == "int8" and field.tensor == "label" and result.attrs["film"] == info
    assert [(c.value, c.name) for c in field.categories] == [(-1, "air"), (0, "substrate"), (1, "film")]
    assert result.array("film")[:, 1, 2, 0].tolist() == [0, 0, 0, 1, 1, 1, 1, 1, -1, -1]
    assert "film" not in image and result.kinds() == {"image", "labels"}


CATEGORIES = [Category(-1, "unclassified", color=(1, 1, 1)), Category(0, "substrate", color=(0.75, 0.75, 0.75))] + \
    [v.category() for v in cubic26("stk")[:8]]


def test_label_counts_and_fractions():
    values = np.array([-1] * 3 + [0] * 2 + [1] * 5 + [7] * 3 + [8] * 2 + [30], dtype=np.int16)
    assert label_counts(values) == {-1: 3, 0: 2, 1: 5, 7: 3, 8: 2, 30: 1}
    assert label_counts(np.array([10 ** 9, -10 ** 9, 5])) == {-10 ** 9: 1, 5: 1, 10 ** 9: 1}
    rows, families, attrs, warnings = label_fractions(values, CATEGORIES, field="domain")
    by_value = {r["value"]: r for r in rows}
    assert [r["value"] for r in rows] == [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 30]
    assert attrs == {"field": "domain", "denominator": 11, "total": 16, "excluded": {"-1": 3, "0": 2}}
    assert math.isnan(by_value[-1]["fraction"]) and math.isnan(by_value[0]["fraction"])
    assert by_value[1]["fraction"] == 5 / 11 and by_value[2]["count"] == 0 and by_value[2]["fraction"] == 0
    assert by_value[30]["name"] == "unknown(30)" and by_value[30]["family"] == "" and by_value[30]["color"] == ""
    assert by_value[1]["color"] == "#ff0000" and by_value[7]["family"] == "O"
    assert sum(r["fraction"] for r in rows if r["value"] not in (-1, 0)) == pytest.approx(1.0)
    assert families == [{"family": "T", "count": 5, "fraction": 5 / 11},
                        {"family": "O", "count": 5, "fraction": 5 / 11}]
    assert [w["code"] for w in warnings] == ["unknown_label"]
    rows, _, _, _ = label_fractions(values, CATEGORIES, include_empty=False)
    assert [r["value"] for r in rows] == [-1, 0, 1, 7, 8, 30]
    rows, families, attrs, warnings = label_fractions(np.array([-1, -1, 0]), CATEGORIES)
    assert attrs["denominator"] == 0 and all(math.isnan(r["fraction"]) for r in rows)
    assert [w["code"] for w in warnings] == ["empty_denominator"] and math.isnan(families[0]["fraction"])
    rows, _, attrs, _ = label_fractions(values, CATEGORIES, exclude=[])
    assert attrs["denominator"] == 16 and {r["value"]: r for r in rows}[-1]["fraction"] == 3 / 16


def test_fractions_tables_columns():
    image = ImageData((4, 1, 1))
    image.add_field("domain", np.array([1, 1, -1, 7], dtype=np.int16).reshape(1, 1, 4), categories=CATEGORIES,
                    palette="stk:cubic-26-orientation")
    out, families, warnings = fractions_tables(image)
    assert out.columns == ["value", "name", "family", "count", "fraction", "color"] and warnings == []
    assert [out.field(c).dtype for c in out.columns] == ["int64", "string", "string", "int64", "float64", "string"]
    assert out.field("fraction").unit == "1" and out.field("value").role == "label"
    assert out.column("count").tolist() == [1, 0, 2, 0, 0, 0, 0, 0, 1, 0]
    assert out.attrs["denominator"] == 3 and families.columns == ["family", "count", "fraction"]
    assert families.column("family").tolist() == ["T", "O"] and families.column("count").tolist() == [2, 1]
    assert out.to_json()["columns"]["fraction"][0] == "NaN"
    assert out.id == "domain_fractions" and families.id == "domain_families"
    with pytest.raises(ValueError):
        fractions_tables(ImageData((1, 1, 1)))
    # Field names may hold blanks, CJK text or a leading '-'; the table ids stay valid dataset ids.
    for name, expected in (("domain labels", "domain_labels_fractions"), ("畴", "__fractions"),
                           ("-x", "_-x_fractions"), ("L" * 128, "L" * 118 + "_fractions")):
        other = ImageData((4, 1, 1))
        other.add_field(name, np.array([1, 1, -1, 7], dtype=np.int16).reshape(1, 1, 4), categories=CATEGORIES)
        out, families, _ = fractions_tables(other)
        assert out.id == expected and len(families.id) <= 128 and out.attrs["field"] == name


def test_peloop_film_and_fractions():
    """A real legacy film frame: 64 x 1 x 150, second triplet (component_offset 3), zero substrate and air."""
    image = read_dat_image(ROOT / "toolkits/sviz/test/PELOOP.00001000.dat")
    result = classify_image(image, component_offset=3, film_detection=True, min_magnitude=0.1)
    info = result.attrs["film"]
    labels = result.array("domain")[..., 0]
    assert info["detected"] and info["substrate_top"] + 1 == info["film_bottom"]
    assert (labels[:info["substrate_top"] + 1] == 0).all() and (labels[info["film_top"] + 1:] == -1).all()
    assert (labels[info["film_bottom"]:info["film_top"] + 1] != 0).all()
    polar = image.array("PELOOP")[..., 3:6]
    assert np.abs(polar[:info["film_bottom"]]).max() <= 1e-6 and np.abs(polar[info["film_top"] + 1:]).max() <= 1e-6
    out, families, _ = fractions_tables(result)
    fractions = out.column("fraction")
    assert np.nansum(fractions) == pytest.approx(1.0)
    assert out.attrs["total"] == 64 * 150 and families.column("fraction").sum() == pytest.approx(1.0)
