"""stk.analysis.* nodes (suan/graph/nodes/analysis.py): classification, film detection, fractions, statistics."""
from itertools import product
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from suan.data.model import Category, ImageData, PolyData, Provenance, Table  # noqa: E402
from suan.graph.catalog import build_registry, compare_catalog  # noqa: E402
from suan.graph.nodes import analysis  # noqa: E402
from suan.graph.registry import Budget, CancelToken, NodeExecutionError, Registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "docs" / "specs" / "catalog" / "stk-catalog-m1.json").read_text())


class Context:
    def __init__(self, node_type):
        self.node_type = node_type
        self.node_id = "node"
        self.budget = Budget()
        self.cancel = CancelToken()
        self.parameters = {}
        self.cache_dir = None
        self.data_key = "0" * 64
        self.warnings = []
        self.checks = 0

    def resolve(self, binding):
        raise KeyError(binding)

    def check(self):
        self.checks += 1

    def progress(self, fraction=None, message=""):
        pass

    def warn(self, message, *, code="node_warning", **details):
        self.warnings.append(code)

    def report_choices(self, param, choices, *, value=None):
        pass

    def cached(self, name, compute, *, disk=False):
        return compute()


def run(fn, dataset, params=None):
    node_type = fn.stk_node_type
    ctx = Context(node_type)
    return node_type.wrap_outputs(fn(ctx, {"in": dataset}, node_type.normalize_params(params or {}))), ctx


def stk_order():
    reps = [v for v in product((1, 0, -1), repeat=3) if any(v) and next(c for c in v if c) == 1]
    reps.sort(key=lambda v: sum(1 for c in v if c))
    return [w for v in reps for w in (v, tuple(-c for c in v))]


@pytest.fixture
def film():
    """A (4, 3, 8) grid: substrate k = 0-1 (zero), film k = 2-5 with every direction, air k = 6-7 (zero)."""
    vectors = stk_order()
    polar = np.zeros((8, 3, 4, 3))
    for index, (k, j, i) in enumerate(product(range(2, 6), range(3), range(4))):
        polar[k, j, i] = 0.7 * np.asarray(vectors[index % 26], dtype=float) / np.linalg.norm(vectors[index % 26])
    polar[3, 0, 0] = [0.05, 0.0, 0.0]   # below the threshold: unclassified
    polar[4, 1, 1] = [np.nan, 0.0, 0.0]  # no data: unclassified
    image = ImageData((4, 3, 8), id="Polar", provenance=Provenance(agent={"node": "polar"}))
    image.add_field("Polar", polar, tensor="vector", unit="unspecified", component_names=("x", "y", "z"))
    image.fields["Polar"].values.flags.writeable = False
    return image


def test_declarations_equal_the_frozen_catalog():
    live = build_registry(entry_points=False).catalog()
    assert compare_catalog(live, SPEC, families={"analysis"}) == []
    assert {t.id for t in Registry([analysis])} == {n["id"] for n in SPEC["nodes"]
                                                    if n["id"].startswith("stk.analysis.")}


def test_orientation_classify_labels_categories_and_film(film):
    before = film.fields["Polar"].values.copy()
    out, ctx = run(analysis.orientation_classify, film, {"field": "Polar", "film_detection": True,
                                                         "min_magnitude": 0.1})
    labels = out["out"]
    assert np.array_equal(film.fields["Polar"].values, before, equal_nan=True) and list(film.fields) == ["Polar"]
    domain = labels.fields["domain"]
    assert "labels" in labels.kinds() and domain.dtype == "int16" and domain.palette == "stk:cubic-26-orientation"
    assert domain.quantity == "domain_variant" and domain.unit == "1"
    values = domain.values[..., 0]
    assert (values[:2] == 0).all() and (values[6:] == -1).all()  # substrate, air
    assert values[3, 0, 0] == -1 and values[4, 1, 1] == -1        # threshold, NaN
    film_values = values[2:6].reshape(-1)
    expected = [index % 26 + 1 for index in range(48)]
    mask = np.ones(48, dtype=bool)
    mask[[12 + 0, 24 + 4 + 1]] = False  # the two unclassified points
    assert film_values[mask].tolist() == np.asarray(expected)[mask].tolist()
    categories = {c.value: c for c in domain.categories}
    assert categories[-1].name == "unclassified" and categories[0].name == "substrate"
    assert categories[1].name == "T[100]" and categories[1].color == pytest.approx((1.0, 0.0, 0.0))
    assert labels.attrs["film"]["substrate_top"] == 1 and labels.attrs["film"]["film_top"] == 5
    assert labels.provenance.agent == {"node": "polar"} and ctx.checks >= 1
    legacy, _ = run(analysis.orientation_classify, film, {"numbering": "stk-legacy"})
    legacy_values = legacy["out"].fields["domain"].values[2:6].reshape(-1)
    assert legacy_values[0] == 21  # (+1, 0, 0) is T1+ = 21 in the legacy numbering


def test_orientation_classify_errors_and_warnings(film):
    with pytest.raises(NodeExecutionError) as error:
        run(analysis.orientation_classify, film, {"direction_set": "stk:cubic-100", "numbering": "stk-legacy"})
    assert error.value.code == "numbering_unsupported"
    with pytest.raises(NodeExecutionError) as error:
        run(analysis.orientation_classify, film, {"direction_set": "custom", "directions": [[0, 0, 0]]})
    assert error.value.code == "invalid_direction"
    with pytest.raises(NodeExecutionError):
        run(analysis.orientation_classify, film, {"field": "missing"})
    _, ctx = run(analysis.orientation_classify, film, {"directions": [[1, 0, 0]]})
    assert ctx.warnings == ["ignored_param"]
    empty = ImageData((2, 2, 2))
    empty.add_field("P", np.zeros((2, 2, 2, 3)), tensor="vector")
    _, ctx = run(analysis.orientation_classify, empty, {"film_detection": True})
    assert ctx.warnings == ["no_film"]


def test_film_detect(film):
    out, _ = run(analysis.film_detect, film, {"output": "layers"})
    info = out["info"]
    assert info["detected"] and (info["substrate_top"], info["film_bottom"], info["film_top"]) == (1, 2, 5)
    layers = out["out"].fields["layers"]
    assert layers.dtype == "int8" and [c.name for c in layers.categories] == ["air", "substrate", "film"]
    assert layers.values[:, 0, 0, 0].tolist() == [0, 0, 1, 1, 1, 1, -1, -1]


def test_label_fractions_tables_and_warnings(film):
    labels = run(analysis.orientation_classify, film, {"film_detection": True})[0]["out"]
    out, ctx = run(analysis.label_fractions, labels)
    table, families = out["out"], out["families"]
    assert isinstance(table, Table) and table.columns == ["value", "name", "family", "count", "fraction", "color"]
    counts = dict(zip(table.column("value").tolist(), table.column("count").tolist()))
    values = labels.fields["domain"].values
    assert all(counts[v] == int((values == v).sum()) for v in range(-1, 27))
    fractions = dict(zip(table.column("value").tolist(), table.column("fraction").tolist()))
    assert math.isnan(fractions[-1]) and math.isnan(fractions[0])
    assert math.isclose(sum(f for v, f in fractions.items() if v > 0), 1.0)
    assert table.attrs["denominator"] == 46 and table.attrs["excluded"] == {"-1": counts[-1], "0": 24}
    assert families.column("family").tolist() == ["T", "O", "R"] and families.column("count").sum() == 46
    assert ctx.warnings == []
    unknown = ImageData((2, 1, 1))
    unknown.add_field("lab", np.array([[[1, 5]]], dtype=np.int16).reshape(1, 1, 2), tensor="label",
                      categories=(Category(1, "one"),))
    _, ctx = run(analysis.label_fractions, unknown)
    assert ctx.warnings == ["unknown_label"]
    with pytest.raises(NodeExecutionError) as error:
        run(analysis.label_fractions, unknown, {"field": "other"})
    assert error.value.code == "invalid_param"
    plain = ImageData((2, 1, 1))
    plain.add_field("s", np.zeros((1, 1, 2)))
    with pytest.raises(NodeExecutionError) as error:
        run(analysis.label_fractions, plain)
    assert error.value.code == "kind_mismatch"


def test_statistics_of_images_polydata_and_tables():
    image = ImageData((3, 2, 1))
    v = np.arange(18, dtype=float).reshape(1, 2, 3, 3)
    v[0, 0, 0, 0] = np.nan
    image.add_field("P", v, tensor="vector", unit="C/m2", component_names=("x", "y", "z"))
    image.add_field("s", np.arange(6, dtype=np.int32).reshape(1, 2, 3))
    out, _ = run(analysis.statistics, image)
    table = out["out"]
    rows = {(f, c): i for i, (f, c) in enumerate(zip(table.column("field"), table.column("component")))}
    assert set(rows) == {("P", "x"), ("P", "y"), ("P", "z"), ("P", "magnitude"), ("s", "0")}
    x = rows[("P", "x")]
    assert table.column("count")[x] == 5 and table.column("nan_count")[x] == 1
    assert table.column("min")[x] == 3 and table.column("max")[x] == 15 and table.column("unit")[x] == "C/m2"
    finite = v.reshape(-1, 3)[1:]
    m = rows[("P", "magnitude")]
    assert table.column("mean")[m] == pytest.approx(np.linalg.norm(finite, axis=1).mean())
    assert table.column("std")[rows[("s", "0")]] == pytest.approx(np.arange(6).std())
    only_magnitude, _ = run(analysis.statistics, image, {"fields": ["P"], "components": "magnitude"})
    assert only_magnitude["out"].column("component").tolist() == ["magnitude"]
    poly = PolyData(np.zeros((2, 3)))
    poly.add_field("w", np.array([1.0, 3.0]))
    assert run(analysis.statistics, poly)[0]["out"].column("mean").tolist() == [2.0]
    energies = Table.from_columns({"step": np.array([1, 2]), "name": np.array(["a", "b"])})
    stats, _ = run(analysis.statistics, energies)
    assert stats["out"].column("field").tolist() == ["step"]  # string columns are skipped
    with pytest.raises(NodeExecutionError):
        run(analysis.statistics, image, {"fields": ["nope"]})
    _, ctx = run(analysis.statistics, Table.from_columns({"name": np.array(["a"])}))
    assert ctx.warnings == ["empty_result"]
