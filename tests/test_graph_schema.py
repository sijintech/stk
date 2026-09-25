"""stk.graph/1 validation, the registry API and the frozen M1 catalog (all NumPy-free)."""
from pathlib import Path
import copy
import json
import os
import runpy
import subprocess
import sys

import pytest

from suan.graph.registry import (CLIENT_TYPES, NodeType, Port, Registry, attach_appearance, binding, boolean,
                                 CancelToken, Cancelled, enum, field_ref, integer, is_subkind, is_subtype, node,
                                 number, ports_compatible, string)
from suan.graph.schema import (GraphError, GraphValidationError, ISSUE_CODES, canonical_json, check_graph,
                               check_value, graph_hash, normalize_value, substitute_params, topological_order,
                               validate_graph)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "specs" / "catalog" / "stk-catalog-m1.json"
EXAMPLE = ROOT / "docs" / "specs" / "examples" / "graph-v1" / "muferro-domains.json"


@pytest.fixture(scope="module")
def registry():
    return Registry.from_catalog(json.loads(CATALOG.read_text(encoding="utf-8")))


@pytest.fixture
def graph():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def by_id(graph, node_id):
    return next(n for n in graph["nodes"] if n["id"] == node_id)


def codes(issues):
    return [issue.code for issue in issues]


def test_example_graph_is_valid(registry, graph):
    assert validate_graph(graph, registry) == []
    check_graph(graph, registry)
    assert validate_graph(graph, registry, parameters={"step": 200, "view": "+z", "min_magnitude": 0.05}) == []
    assert codes(validate_graph(graph, registry, parameters={"nope": 1})) == ["unknown_parameter"]
    assert codes(validate_graph(graph, registry, parameters={"view": "top"})) == ["invalid_parameter"]


def test_catalog_is_in_sync_with_declarations_and_spec():
    module = runpy.run_path(str(ROOT / "docs" / "specs" / "catalog" / "m1_nodes.py"), run_name="stk_m1_catalog")
    assert module["catalog_text"]() == CATALOG.read_text(encoding="utf-8")
    spec = (ROOT / "docs" / "specs" / "stk-graph-v1.md").read_text(encoding="utf-8")
    assert module["update_spec"](spec) == spec
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    ids = [entry["id"] for entry in catalog["nodes"]]
    required = {  # decisions.md M1 list
        "stk.source.muferro_run@1", "stk.source.muferro_frame@1", "stk.source.file@1", "stk.source.table@1",
        "stk.filter.crop@1", "stk.filter.sample@1", "stk.filter.calculator@1", "stk.filter.slice@1",
        "stk.filter.threshold@1", "stk.filter.contour@1", "stk.filter.glyph_source@1",
        "stk.filter.label_surfaces@1", "stk.analysis.orientation_classify@1", "stk.analysis.film_detect@1",
        "stk.analysis.label_fractions@1", "stk.analysis.statistics@1", "stk.render.surface@1",
        "stk.render.glyphs@1", "stk.render.volume@1", "stk.render.outline@1", "stk.render.axes@1",
        "stk.render.scalar_bar@1", "stk.render.categorical_legend@1", "stk.render.orientation_legend@1",
        "stk.view.camera@1", "stk.view.scene@1", "stk.output.payload@1", "stk.output.image@1",
        "stk.output.dataset@1", "stk.plot.line@1", "stk.plot.heatmap@1", "stk.plot.histogram@1", "stk.plot.bar@1"}
    assert required <= set(ids) and ids == sorted(ids)
    assert {e["id"] for e in catalog["nodes"] if e.get("stretch")} == {"stk.filter.streamlines@1"}
    for entry in catalog["nodes"]:
        assert all("x-stk-stage" in p for p in entry["params"]["properties"].values()), entry["id"]
        if entry["stage"] in ("source", "data", "analysis"):
            assert {p["x-stk-stage"] for p in entry["params"]["properties"].values()} <= {"data"}, entry["id"]


def test_catalog_round_trip(registry):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert registry.catalog() == catalog
    assert Registry.from_catalog(registry.catalog()).catalog() == catalog
    assert registry.namespaces == {"stk": 1}


MUTATIONS = {
    "unknown_type": (lambda g: by_id(g, "surfaces").update(type="stk.filter.label_surface@1"),
                     "surfaces", "/nodes/3/type"),
    "unknown_param": (lambda g: by_id(g, "surfaces")["params"].update(smoothing_iterations=20),
                      "surfaces", "/nodes/3/params/smoothing_iterations"),
    "invalid_param": (lambda g: by_id(g, "domains")["params"].update(max_angle_deg="wide"),
                      "domains", "/nodes/2/params/max_angle_deg"),
    "missing_param": (lambda g: by_id(g, "energy_plot")["params"].pop("y"), "energy_plot", "/nodes/13/params"),
    "missing_input": (lambda g: by_id(g, "surfaces").pop("inputs"), "surfaces", "/nodes/3/inputs"),
    "unknown_input": (lambda g: by_id(g, "box")["inputs"].update(source={"from": "polar.out"}),
                      "box", "/nodes/6/inputs/source"),
    "cycle": (lambda g: by_id(g, "polar")["inputs"].update(frames={"from": "domains.out"}), "polar", "/nodes"),
    "port_mismatch": (lambda g: by_id(g, "surfaces")["inputs"].update({"in": {"from": "polar.out"}}),
                      "surfaces", "/nodes/3/inputs/in/from"),
    "duplicate_id": (lambda g: g["nodes"].append({"id": "box", "type": "stk.render.axes@1"}), "box", "/nodes/14/id"),
    "bad_param_ref": (lambda g: by_id(g, "domains")["params"].update(min_magnitude={"$param": "threshold"}),
                      "domains", "/nodes/2/params/min_magnitude"),
    "param_ref_type": (lambda g: g["parameters"][2].update(choices=["iso", "top"], default="top"),
                       "camera", "/nodes/8/params/preset"),
    "reserved_key": (lambda g: by_id(g, "box").update(params={"color": {"$anim": {"keys": []}}}),
                     "box", "/nodes/6/params/color/$anim"),
    "multi_link": (lambda g: by_id(g, "box")["inputs"].update({"in": [{"from": "polar.out"}]}),
                   "box", "/nodes/6/inputs/in"),
    "bad_link": (lambda g: by_id(g, "box")["inputs"].update({"in": {"from": "nothere.out"}}),
                 "box", "/nodes/6/inputs/in/from"),
    "bad_output": (lambda g: g["outputs"].update(layer="box.layer"), "box", "/outputs/layer"),
    "no_outputs": (lambda g: g.update(outputs={}), None, "/outputs"),
    "catalog_version": (lambda g: g.update(catalog={"stk": 2}), None, "/catalog/stk"),
    "unknown_key": (lambda g: by_id(g, "box").update(parms={}), "box", "/nodes/6/parms"),
    "invalid_id": (lambda g: g["outputs"].update(Bad="fractions.out"), None, "/outputs/Bad"),
    "invalid_type_ref": (lambda g: by_id(g, "box").update(type="stk.render.outline"), "box", "/nodes/6/type"),
    "schema_version": (lambda g: g.update(schema="stk.graph/2"), None, "/schema"),
    "invalid_parameter": (lambda g: g["parameters"][1].update(default="high"), None, "/parameters/1/default"),
}


@pytest.mark.parametrize("code", sorted(MUTATIONS))
def test_error_classes(registry, graph, code):
    mutate, node_id, path = MUTATIONS[code]
    mutate(graph)
    issues = validate_graph(graph, registry)
    assert code in ISSUE_CODES
    matching = [issue for issue in issues if issue.code == code]
    assert matching, [issue.to_dict() for issue in issues]
    issue = matching[0]
    assert issue.node == node_id and issue.path == path and issue.severity == "error" and issue.message
    assert set(issue.to_dict()) == {"code", "message", "path", "node", "hint", "severity"}
    # Each mutation produces only its own error class (a cycle also mismatches ports in this graph).
    assert set(codes(issues)) <= {code, "port_mismatch"}
    with pytest.raises(GraphValidationError) as raised:
        check_graph(graph, registry)
    assert raised.value.issues and raised.value.code in {code, "port_mismatch"}


def test_hints_are_actionable(registry, graph):
    by_id(graph, "surfaces")["params"]["smoothing_iterations"] = 20
    by_id(graph, "surfaces")["type"] = "stk.filter.label_surfaces@1"
    issue = validate_graph(graph, registry)[0]
    assert "smooth_iterations" in issue.hint
    graph = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    by_id(graph, "surfaces")["type"] = "stk.filter.label_surface@1"
    assert "stk.filter.label_surfaces@1" in validate_graph(graph, registry)[0].hint


def test_cycle_lists_only_cycle_nodes(registry, graph):
    by_id(graph, "polar")["inputs"]["frames"] = {"from": "domains.out"}
    cycle = next(issue for issue in validate_graph(graph, registry) if issue.code == "cycle")
    assert "polar, domains" in cycle.message and "scene" not in cycle.message
    with pytest.raises(GraphError) as raised:
        topological_order(graph)
    assert raised.value.code == "cycle"


def test_structural_errors(registry):
    assert codes(validate_graph([], registry)) == ["invalid_document"]
    assert codes(validate_graph({"schema": "stk.graph/1", "nodes": [], "outputs": {}}, registry)) == [
        "bad_structure", "no_outputs"]
    nan = {"schema": "stk.graph/1", "nodes": [{"id": "a", "type": "stk.render.axes@1",
                                                "params": {"size_px": float("nan")}}], "outputs": {}}
    assert codes(validate_graph(nan, registry)) == ["invalid_document"]
    big = {"schema": "stk.graph/1", "outputs": {"a": "n0.layer"},
           "nodes": [{"id": f"n{i}", "type": "stk.render.axes@1"} for i in range(201)]}
    assert "too_large" in codes(validate_graph(big, registry))


def test_topological_order_is_lazy(graph):
    assert topological_order(graph, ["fractions"]) == ["run", "polar", "domains", "fractions"]
    order = topological_order(graph)
    assert order.index("camera") < order.index("scene") < order.index("png")
    with pytest.raises(GraphError):
        topological_order(graph, ["missing"])


def test_graph_hash_ignores_presentation(graph):
    reference = graph_hash(graph)
    changed = copy.deepcopy(graph)
    changed["ui"] = {}
    changed["name"] = "renamed"
    by_id(changed, "box")["label"] = "Box"
    changed["nodes"].reverse()
    changed["parameters"].reverse()
    assert graph_hash(changed) == reference
    by_id(changed, "domains")["params"]["max_angle_deg"] = 170
    assert graph_hash(changed) != reference


def test_canonical_json():
    assert canonical_json({"b": 1, "a": [0.1, -0.0]}) == b'{"a":[0.1,0.0],"b":1}'
    assert canonical_json({"a": 1e-1}) == canonical_json({"a": 0.1})
    assert canonical_json({"s": "畴"}) == '{"s":"畴"}'.encode("utf-8")
    with pytest.raises(ValueError):
        canonical_json({"a": float("inf")})
    with pytest.raises(TypeError):
        canonical_json({1: "a"})


def test_check_value_subset():
    schema = {"type": "object", "required": ["by"], "additionalProperties": False,
              "properties": {"by": {"enum": ["solid", "field"]}, "range": {
                  "type": "array", "prefixItems": [{"type": ["number", "null"]}, {"type": ["number", "null"]}],
                  "minItems": 2, "maxItems": 2}}}
    assert check_value({"by": "solid", "range": [None, 2]}, schema) == []
    assert check_value({"by": "solid", "rnage": [0, 1]}, schema)[0][1].startswith("unexpected key 'rnage' (did you mean 'range'")
    assert check_value({"range": [0, 1]}, schema)[0][0] == "/by"
    assert check_value(True, {"type": "integer"})
    assert check_value(2.0, {"type": "integer"}) == []
    assert check_value(float("nan"), {"type": "number"})
    assert check_value(-3, {"anyOf": [{"type": "integer", "minimum": 0}, {"enum": ["latest"]}]})[0][1] == "must be >= 0, got -3"
    assert check_value([1, 1], {"type": "array", "uniqueItems": True})
    assert check_value(5, {"if": {"type": "integer"}, "then": {"maximum": 3}})
    assert check_value("x", {"oneOf": [{"type": "string"}, {"const": "x"}]})[0][1] == "matches more than one allowed form"


def test_normalize_and_substitute():
    assert normalize_value([4.0, 4, 4], {"type": "array", "items": {"type": "integer"}}) == [4, 4, 4]
    assert type(normalize_value(1, {"type": "number"})) is float
    assert normalize_value(-0.0, {"type": "number"}) == 0.0
    assert substitute_params({"a": [{"$param": "x"}, {"b": {"$param": "y"}}]}, {"x": 1, "y": "z"}) == {"a": [1, {"b": "z"}]}


def _toy_registry():
    registry = Registry()

    @registry.node("toy.source.numbers", title="Numbers", outputs=[Port("out", "table")],
                   params={"binding": binding()}, fingerprint=lambda ctx, inputs, params: None)
    def numbers(ctx, inputs, params):
        return {"out": params}

    @registry.node("toy.filter.scale", title={"en": "Scale", "zh": "缩放"},
                   inputs=[Port("in", "dataset", accepts=["image"])], outputs=[Port("out", "dataset", kind_from="in")],
                   params={"factor": number(1.0, exclusive_minimum=0), "field": field_ref(None, nullable=True),
                           "stride": integer(1, minimum=1)})
    def scale(ctx, inputs, params):
        return inputs["in"]

    @registry.node("toy.render.dots", inputs=[Port("in", "dataset", accepts=["polydata"])],
                   outputs=[Port("layer", "layer")],
                   params={"size": number(2.0), "color": enum(["red", "blue"], "red", stage="client")})
    def dots(ctx, inputs, params):
        return {"kind": "points"}

    @registry.node("toy.render.legend", inputs=[Port("source", "layer")], outputs=[Port("layer", "layer")],
                   params={"title": string("", stage="client")})
    def legend(ctx, inputs, params):
        return {"kind": "legend"}

    return registry


def test_registry_declarations_and_contract():
    registry = _toy_registry()
    assert registry.types() == ["toy.filter.scale@1", "toy.render.dots@1", "toy.render.legend@1",
                                "toy.source.numbers@1"]
    scale = registry["toy.filter.scale@1"]
    assert scale.stage == "data" and scale.title == {"en": "Scale", "zh": "缩放"} and scale.keyed_by_data
    assert scale.impl_ref.endswith("scale") and scale.impl.stk_node_type is scale
    assert scale.normalize_params({"factor": 2, "field": "Polar", "stride": 3.0}) == {
        "factor": 2.0, "field": {"name": "Polar", "component": None}, "stride": 3}
    assert scale.normalize_params({}) == {"factor": 1.0, "field": None, "stride": 1}
    with pytest.raises(GraphError):
        scale.normalize_params({"bogus": 1})
    dots = registry["toy.render.dots@1"]
    assert dots.stage == "representation" and dots.finalize is attach_appearance and dots.keyed_by_data
    assert dots.split_params(dots.normalize_params({})) == ({"size": 2.0}, {"color": "red"})
    assert not registry["toy.render.legend@1"].keyed_by_data and "layer" in CLIENT_TYPES
    assert dots.wrap_outputs({"layer": 1}) == {"layer": 1} and dots.wrap_outputs(5) == {"layer": 5}

    class Ctx:
        node_type = dots
    assert attach_appearance(Ctx(), {"layer": {"kind": "points"}}, {"color": "blue"}) == {
        "layer": {"kind": "points", "appearance": {"color": "blue"}}}
    # Declaration-only registries export the same catalog.
    assert Registry.from_catalog(registry.catalog()).catalog() == registry.catalog()
    with pytest.raises(ValueError):
        registry.register(scale)
    assert registry.register(scale, replace=True) == [scale]


@pytest.mark.parametrize("kwargs, message", [
    ({"type": "toy.filter.bad", "params": {"c": boolean(True, stage="client")}}, "client-stage"),
    ({"type": "toy.filter.bad", "outputs": [Port("out", "unknown")]}, "unknown port type"),
    ({"type": "toy.filter.bad", "outputs": [Port("out", "value", kind="image")]}, "kinds only apply"),
    ({"type": "toy.filter.bad", "params": {"n": integer(0, minimum=1)}}, "default of 'n' is invalid"),
    ({"type": "toy.render.bad", "outputs": [Port("layer", "layer")], "cache": "disk"}, "disk cache"),
    ({"type": "toy.source.bad", "outputs": [Port("out", "table")]}, "fingerprint"),
    ({"type": "toy.misc.bad"}, "family"),
    ({"type": "toy.filter.bad", "outputs": [Port("out", "dataset", kind_from="in")]}, "kind_from"),
])
def test_registration_checks(kwargs, message):
    kwargs = {"outputs": [Port("out", "dataset")], **kwargs}
    with pytest.raises(ValueError, match=message):
        node(kwargs.pop("type"), **kwargs)(lambda ctx, inputs, params: None)


def test_port_lattice():
    assert is_subtype("table", "dataset") and is_subtype("layer", "any") and not is_subtype("dataset", "table")
    assert is_subkind("labels", "image") and is_subkind("frames", "table") and not is_subkind("image", "labels")
    labels_out = Port("out", "dataset", kind="labels")
    image_in = Port("in", "dataset", accepts=["image"])
    assert ports_compatible(labels_out, image_in)
    assert not ports_compatible(Port("out", "dataset", kind="image"), Port("in", "dataset", accepts=["labels"]))
    assert ports_compatible(Port("out", "dataset", kind=["image", "polydata"]), Port("in", "dataset", accepts=["polydata"]))
    assert ports_compatible(Port("out", "table"), Port("in", "dataset", accepts=["image", "table"]))
    assert not ports_compatible(Port("out", "dataset", kind="image"), Port("in", "table"))
    assert ports_compatible(Port("out", "plot"), Port("in", ["scene", "plot"]))
    assert ports_compatible(Port("o", "value", value_type="integer"), Port("i", "value", value_type="number"))
    assert not ports_compatible(Port("o", "value", value_type="string"), Port("i", "value", value_type="number"))


def test_kind_from_propagates_through_validation():
    registry = _toy_registry()

    @registry.node("toy.source.grid", outputs=[Port("out", "dataset", kind="image")], params={"labels": boolean(True)},
                   fingerprint=lambda *a: None)
    def grid(ctx, inputs, params):
        return None

    @registry.node("toy.analysis.count", inputs=[Port("in", "dataset", accepts=["labels"])], outputs=[Port("out", "table")])
    def count(ctx, inputs, params):
        return None

    graph = {"schema": "stk.graph/1", "outputs": {"t": "count.out"}, "nodes": [
        {"id": "src", "type": "toy.source.grid@1"},
        {"id": "scale", "type": "toy.filter.scale@1", "inputs": {"in": {"from": "src.out"}}},
        {"id": "count", "type": "toy.analysis.count@1", "inputs": {"in": {"from": "scale.out"}}}]}
    # scale.out has the kind of src.out (image), which is not a labels dataset.
    issues = validate_graph(graph, registry)
    assert codes(issues) == ["port_mismatch"] and issues[0].node == "count"
    registry.register(NodeType("toy.source.grid", outputs=[Port("out", "dataset", kind="labels")]), replace=True)
    assert validate_graph(graph, registry) == []


def test_cancel_token():
    token = CancelToken()
    token.raise_if_cancelled()
    token.cancel("user")
    assert token.cancelled
    with pytest.raises(Cancelled) as raised:
        token.raise_if_cancelled()
    assert raised.value.code == "cancelled"


NUMPY_FREE = r"""
import json, sys
sys.modules["numpy"] = None
from suan.graph.registry import Registry, Port, number
from suan.graph.schema import validate_graph, graph_hash
import suan.contracts, suan.connectors.api, suan.data.model
registry = Registry.from_catalog(json.load(open(sys.argv[1], encoding="utf-8")))
graph = json.load(open(sys.argv[2], encoding="utf-8"))
assert validate_graph(graph, registry) == [], validate_graph(graph, registry)
graph["nodes"][2]["params"]["max_angle_deg"] = 300
assert [i.code for i in validate_graph(graph, registry)] == ["invalid_param"]
@registry.node("toy.filter.x", inputs=[Port("in", "dataset")], outputs=[Port("out", "dataset")], params={"a": number(1)})
def x(ctx, inputs, params):
    import numpy
assert "toy.filter.x@1" in registry and graph_hash(graph).startswith("sha256:")
assert sys.modules["numpy"] is None
print("ok")
"""


def test_validation_without_numpy():
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])}
    result = subprocess.run([sys.executable, "-c", NUMPY_FREE, str(CATALOG), str(EXAMPLE)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


# -- JSON-Schema `pattern` / `patternProperties`: `$` matches only at the very end (spec §4.2) ----------------


def _catalog_patterns():
    patterns = set()

    def walk(schema):
        if isinstance(schema, dict):
            if isinstance(schema.get("pattern"), str):
                patterns.add(schema["pattern"])
            patterns.update(key for key in schema.get("patternProperties") or {})
            for value in schema.values():
                walk(value)
        elif isinstance(schema, list):
            for value in schema:
                walk(value)

    walk(json.loads(CATALOG.read_text(encoding="utf-8")))
    return sorted(patterns)


def test_dollar_does_not_match_before_a_trailing_newline():
    from suan.graph.schema import pattern_search, schema_pattern
    schema = {"type": "string", "pattern": "^[a-z]+$"}
    assert check_value("abc", schema) == []
    assert check_value("abc\n", schema) == [("", "does not match pattern ^[a-z]+$")]
    keyed = {"type": "object", "patternProperties": {"^[a-z]+$": {"type": "integer"}}, "additionalProperties": False}
    assert check_value({"ab": 1}, keyed) == []
    assert [path for path, _ in check_value({"ab\n": 1}, keyed)] == ["/ab\n"]
    # "$" escaped or inside a class stays a literal; alternatives and groups are anchored too
    assert schema_pattern(r"^[$]\$x$") == r"^[$]\$x\Z" and schema_pattern(r"[]$]|[^]$]$") == r"[]$]|[^]$]\Z"
    assert pattern_search(r"^a$|^b$", "b") and not pattern_search(r"^a$|^b$", "b\n")
    assert pattern_search(r"(/|$)", "x") and pattern_search(r"[$]", "$") and pattern_search(r"\$", "a$")
    with pytest.raises(Exception):
        pattern_search("(ab", "ab")


def test_catalog_patterns_keep_their_meaning():
    import re
    from suan.graph.schema import pattern_search
    patterns = _catalog_patterns()
    assert len(patterns) >= 7
    texts = ["", "a", "abc", "Polar", "a/b", "a.b", "../x", "x/../y", "x/..", "..", "/abs", "\\x", "C:x", "run:1",
             "stk:cubic", "a_b-c", "A9", "12", ".3g", "+.1e", "08,.2f", "d", "{}", "999999", "中文", "x" * 128,
             "x" * 129, "ab cd", "tab\there", "Polar.00000000.dat", "sub/dir/file.h5"]
    for pattern in patterns:
        accepted = [t for t in texts if pattern_search(pattern, t)]
        assert accepted, pattern
        for text in texts:      # without a trailing newline nothing changes
            assert pattern_search(pattern, text) == (re.search(pattern, text) is not None), (pattern, text)
        if "[^" not in pattern:  # identifiers, formats: a trailing newline is never accepted any more
            for text in accepted:
                assert not pattern_search(pattern, text + "\n"), (pattern, text)
                assert re.search(pattern, text + "\n"), (pattern, text)    # Python's own "$" accepted it
    # Classes such as [^/.] admit "\n" (in JavaScript too): the newline is then an ordinary character.
    field = next(p for p in patterns if p.startswith("^[^/.]"))
    assert pattern_search(field, "a\n") and not pattern_search(field, "a.b\n")
    path = next(p for p in patterns if "(?!" in p)
    assert pattern_search(path, "a/b\n") and not pattern_search(path, "/abs\n")
    assert not pattern_search(path, "x/../y") and not pattern_search(path, "a/..") and not pattern_search(path, "C:x")


def test_preset_and_task_ids_reject_a_trailing_newline():
    from suan.graph.catalog import PRESET_ID_RE
    from suan.graph.resolve import TASK_ID_RE
    assert PRESET_ID_RE.match("muferro-domains") and not PRESET_ID_RE.match("muferro-domains\n")
    assert TASK_ID_RE.match("task-1.a") and not TASK_ID_RE.match("task-1.a\n")
