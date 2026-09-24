"""stk.filter.* nodes (suan/graph/nodes/filters.py): declarations, the node contract and evaluation in graphs."""
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("vtk")

from suan.data.model import Category, ImageData, PolyData, Provenance, TimeInfo  # noqa: E402
from suan.graph.catalog import build_registry, compare_catalog  # noqa: E402
from suan.graph.nodes import filters  # noqa: E402
from suan.graph.registry import Budget, CancelToken, Cancelled, NodeExecutionError, Registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "docs" / "specs" / "catalog" / "stk-catalog-m1.json").read_text())


class Context:
    """The NodeContext subset a filter node uses."""

    def __init__(self, node_type, node_id="node"):
        self.node_type = node_type
        self.node_id = node_id
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
        self.cancel.raise_if_cancelled()

    def progress(self, fraction=None, message=""):
        pass

    def warn(self, message, *, code="node_warning", **details):
        self.warnings.append(code)

    def report_choices(self, param, choices, *, value=None):
        pass

    def cached(self, name, compute, *, disk=False):
        return compute()


def run(fn, image, params=None, *, context=None):
    """``(output, ctx)``: params normalized as the evaluator does; outputs wrapped to ``{port: value}``."""
    node_type = fn.stk_node_type
    ctx = context or Context(node_type)
    result = node_type.wrap_outputs(fn(ctx, {"in": image}, node_type.normalize_params(params or {})))
    return result, ctx


def snapshot(image):
    return {name: (np.array(f.values, copy=True), f.to_json()) for name, f in image.fields.items()}


def unchanged(image, before):
    assert set(image.fields) == set(before)
    for name, (values, descriptor) in before.items():
        assert np.array_equal(image.fields[name].values, values, equal_nan=True)
        assert image.fields[name].to_json() == descriptor


@pytest.fixture
def image():
    nx, ny, nz = 12, 10, 8
    z, y, x = np.meshgrid(np.arange(nz), np.arange(ny), np.arange(nx), indexing="ij")
    image = ImageData((nx, ny, nz), (1.0, 2.0, 3.0), (0.5, 0.5, 0.5), id="Polar", time=TimeInfo(step=4),
                      provenance=Provenance(agent={"node": "polar"}))
    polar = np.stack([np.where(x < 6, 1.0, -1.0), 0.2 * np.sin(y), 0.1 * (z - 3.5)], axis=-1) * 0.6
    image.add_field("Polar", np.ascontiguousarray(polar), tensor="vector", unit="unspecified",
                    component_names=("x", "y", "z"), quantity="polarization")
    labels = np.where(x < 6, 1, 2).astype(np.int16)
    labels[:2] = 0
    labels[-1] = -1
    image.add_field("domain", labels, tensor="label", palette="stk:cubic-26-orientation", unit="1",
                    categories=(Category(-1, "unclassified", color=(1, 1, 1)),
                                Category(0, "substrate", color=(0.75, 0.75, 0.75)),
                                Category(1, "T[100]", color=(1, 0, 0), family="T"),
                                Category(2, "T[-100]", color=(0, 1, 1), family="T")))
    for field in image.fields.values():
        field.values.flags.writeable = False  # as the evaluator hands them over
    return image


def test_declarations_equal_the_frozen_catalog():
    live = build_registry(entry_points=False).catalog()
    assert compare_catalog(live, SPEC, families={"filter"}) == []
    types = {node_type.id for node_type in Registry([filters])}
    assert types == {n["id"] for n in SPEC["nodes"] if n["id"].startswith("stk.filter.")}


def test_every_filter_keeps_its_input_untouched(image):
    before = snapshot(image)
    calls = [
        (filters.crop, {"extent": [1, 5, None, None, 2, None]}),
        (filters.sample, {"stride": [2, 2, 2]}),
        (filters.calculator, {"operation": "magnitude", "field": "Polar"}),
        (filters.slice_filter, {"mode": "axis", "axis": "x", "index": 3}),
        (filters.slice_filter, {"mode": "plane", "origin": [4.0, 4.0, 4.0], "normal": [1, 1, 0]}),
        (filters.threshold, {"field": {"name": "Polar", "component": 0}, "lower": 0}),
        (filters.contour, {"field": {"name": "Polar", "component": None}, "values": [0.55, 0.6]}),
        (filters.glyph_source, {"field": "Polar", "mask_field": "domain", "mask_labels": [2]}),
        (filters.label_surfaces, {}),
        (filters.streamlines, {"field": "Polar", "seed_count": 5}),
    ]
    for fn, params in calls:
        result, _ = run(fn, image, params)
        assert result["out"] is not image
        unchanged(image, before)


def test_kinds_categories_and_lineage(image):
    crop, _ = run(filters.crop, image, {"extent": [0, 3, None, None, None, None]})
    assert "labels" in crop["out"].kinds() and crop["out"].fields["domain"].categories[2].name == "T[100]"
    assert crop["out"].provenance.agent == {"node": "polar"} and crop["out"].time.step == 4
    mask, _ = run(filters.threshold, image, {"field": "domain", "labels": [2], "output": "right"})
    right = mask["out"].fields["right"]
    assert right.is_label and [c.name for c in right.categories] == ["outside", "inside"]
    surfaces, ctx = run(filters.label_surfaces, image, {"smooth_iterations": 10})
    poly = surfaces["out"]
    assert isinstance(poly, PolyData) and poly.kinds() == frozenset({"polydata"})
    label = poly.fields["label"]
    assert label.association == "cell" and label.palette == "stk:cubic-26-orientation"
    assert {c.value: c.color for c in label.categories}[2] == (0.0, 1.0, 1.0)
    assert sorted(np.unique(label.values).tolist()) == [1, 2] and ctx.checks >= 2
    assert poly.provenance.agent == {"node": "polar"}
    points, _ = run(filters.glyph_source, image, {"field": "Polar", "attributes": ["domain"]})
    assert points["out"].kinds() == frozenset({"polydata", "points"})
    assert points["out"].fields["domain"].is_label and points["out"].attrs["sample_spacing"] == 0.5


def test_errors_become_node_errors_with_codes(image):
    cases = [
        (filters.crop, {"extent": [8, 2, None, None, None, None]}, "invalid_param"),
        (filters.calculator, {"operation": "component", "field": "Polar", "component": 5}, "invalid_param"),
        (filters.contour, {"field": "domain"}, "invalid_param"),
        (filters.contour, {"field": "nope"}, "invalid_param"),
        (filters.slice_filter, {"mode": "plane", "normal": [0, 0, 0]}, "invalid_param"),
        (filters.glyph_source, {"field": "domain"}, "invalid_param"),
    ]
    for fn, params, code in cases:
        with pytest.raises(NodeExecutionError) as error:
            run(fn, image, params)
        assert error.value.code == code, (fn.__name__, params)
    plain = ImageData((4, 4, 4))
    plain.add_field("s", np.zeros((4, 4, 4)))
    with pytest.raises(NodeExecutionError) as error:
        run(filters.label_surfaces, plain)
    assert error.value.code == "kind_mismatch"


def test_warnings(image):
    _, ctx = run(filters.sample, image, {"stride": [1, 1, 1], "max_points": 50})
    assert ctx.warnings == ["stride_increased"]
    _, ctx = run(filters.glyph_source, image, {"field": "Polar", "magnitude_range": [10, None]})
    assert ctx.warnings == ["empty_result"]
    _, ctx = run(filters.contour, image, {"field": "Polar", "values": [99.0]})
    assert ctx.warnings == ["empty_result"]
    _, ctx = run(filters.label_surfaces, image, {"labels": [9]})
    assert ctx.warnings == ["empty_result"]


def test_label_surfaces_honours_cancellation(image):
    ctx = Context(filters.label_surfaces.stk_node_type)
    ctx.cancel.cancel("stop")
    with pytest.raises(Cancelled):
        run(filters.label_surfaces, image, context=ctx)


def test_filters_in_a_graph_with_the_disk_cache(tmp_path, image):
    from suan.data.vtkhdf import write_vtkhdf
    from suan.graph.cache import GraphCache
    from suan.graph.evaluator import evaluate
    from suan.graph.resolve import LocalDirResolver
    pytest.importorskip("h5py")
    folder = tmp_path / "data"
    folder.mkdir()
    write_vtkhdf(folder / "field.vtkhdf", image)
    graph = {"schema": "stk.graph/1", "outputs": {"surfaces": "surfaces.out", "iso": "iso.out", "cut": "cut.out"},
             "nodes": [{"id": "src", "type": "stk.source.file@1", "params": {"binding": "data",
                                                                           "path": "field.vtkhdf"}},
                       {"id": "crop", "type": "stk.filter.crop@1", "inputs": {"in": {"from": "src.out"}},
                        "params": {"extent": [None, None, None, None, 1, None]}},
                       {"id": "mask", "type": "stk.filter.threshold@1", "inputs": {"in": {"from": "crop.out"}},
                        "params": {"field": "domain", "labels": [1]}},
                       {"id": "surfaces", "type": "stk.filter.label_surfaces@1", "inputs": {"in": {"from": "mask.out"}},
                        "params": {"field": "domain"}},
                       {"id": "iso", "type": "stk.filter.contour@1", "inputs": {"in": {"from": "crop.out"}},
                        "params": {"field": {"name": "Polar", "component": 0}, "values": [0.0]}},
                       {"id": "cut", "type": "stk.filter.slice@1", "inputs": {"in": {"from": "src.out"}},
                        "params": {"mode": "axis", "axis": "z"}}]}
    registry = build_registry(entry_points=False)
    resolver = LocalDirResolver({"data": folder})
    first = evaluate(graph, registry=registry, resolver=resolver, cache=GraphCache(tmp_path / "cache"))
    iso = first.outputs["iso"]
    assert np.allclose(iso.points[:, 0], 1.0 + 0.5 * 5.5)  # the sign change between x = 5 and 6
    assert first.outputs["cut"].dimensions == (12, 10, 1)
    assert sorted(np.unique(first.outputs["surfaces"].array("label")).tolist()) == [1, 2]
    second = evaluate(graph, registry=registry, resolver=resolver, cache=GraphCache(tmp_path / "cache"))
    assert set(second.evaluated) <= {"crop", "mask", "cut"}  # disk-cached source, surfaces and contour
    assert "surfaces" not in second.evaluated and "iso" not in second.evaluated
    assert np.array_equal(second.outputs["surfaces"].points, first.outputs["surfaces"].points)
