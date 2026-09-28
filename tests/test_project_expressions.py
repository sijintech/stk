"""Pure expression bounds, units and dependency topology independent of SQLite/UI."""
from uuid import uuid4

import pytest

from suan.project.evaluation import evaluate
from suan.project.expressions import EvaluationError, Expression, Value


def run(source, **values):
    return Expression(source, values.keys()).evaluate(values.__getitem__)


@pytest.mark.parametrize("source,expected", [
    ("2 + 3 * 4", 14), ("(2 + 3) * 4", 20), ("-2 ** 2", -4),
    ("sqrt(16) + abs(-3)", 7), ("round(2.75, 1)", 2.8),
    ("min(1, 5, 2) + max(1, 5, 2)", 6), ("2 ** -3", 0.125),
    ("-9223372036854775808", -(2**63)),
])
def test_bounded_scalar_language(source, expected):
    assert run(source) == Value(expected, "1")


@pytest.mark.parametrize("source", [
    "__import__('os').system('echo unsafe')", "x.__class__", "x[0]", "[x for x in [1]]",
    "(lambda: 1)()", "open('file')", "sum([1, 2])", "True + 1", "'text'", "abs(x=1)",
    "2 ** 10000000", "1e309", "1 +", "(1, 2)", "2 // 1", "[0] * 1000000",
])
def test_rejects_general_python_and_unbounded_operators(source):
    with pytest.raises(EvaluationError):
        run(source)


def test_units_are_explicit_and_never_converted():
    assert run('temperature + quantity(10, "K")', temperature=Value(300, "K")) == Value(310, "K")
    assert run("temperature * 2", temperature=Value(300, "K")) == Value(600, "K")
    assert run("left / right", left=Value(6, "m"), right=Value(3, "m")) == Value(2, "1")
    for source, values, code in [
        ("temperature + 10", {"temperature": Value(300, "K")}, "unit"),
        ("left + right", {"left": Value(1, "m"), "right": Value(100, "cm")}, "unit"),
        ("left + right", {"left": Value(1), "right": Value(2)}, "unit_unknown"),
        ("left * right", {"left": Value(2, "m"), "right": Value(3, "m")}, "unit_operation"),
        ('quantity(left, "cm")', {"left": Value(1, "m")}, "unit"),
        ("1 / 0", {}, "division_by_zero"),
        ("unused + 1", {}, "binding"),
        ("1 + 1", {"unused": Value(1, "1")}, "binding"),
    ]:
        with pytest.raises(EvaluationError) as caught:
            run(source, **values)
        assert caught.value.code == code


def test_long_dependency_chain_cycles_and_selective_recomputation():
    table, field, row = (str(uuid4()) for _ in range(3))
    fields = {field: {"table_id": table, "type": "number", "unit": "1"}}
    records = {row: {"table_id": table}}
    literals = {(row, field): 7}
    definitions = {}
    previous = (row, field)
    for _ in range(1500):
        record = str(uuid4())
        records[record] = {"table_id": table}
        key = (record, field)
        definitions[key] = {"kind": "reference", "source": {"record_id": previous[0], "field_id": previous[1]}}
        previous = key
    cache, affected = evaluate(fields, records, literals, definitions, {}, set(), 1)
    assert len(affected) == 1500
    assert cache[previous]["value"] == 7
    unchanged, affected = evaluate(fields, records, literals, definitions, cache, set(), 2)
    assert not affected and unchanged == cache
    # An unrelated cell must not invalidate this entire chain.
    unchanged, affected = evaluate(fields, records, literals, definitions, cache, {(str(uuid4()), field)}, 3)
    assert not affected and unchanged == cache
    # Close a cycle, then repair it: no recursive Python calls even for a deep graph.
    first = next(iter(definitions))
    definitions[first]["source"] = {"record_id": previous[0], "field_id": field}
    errors, affected = evaluate(fields, records, literals, definitions, cache, {first}, 4)
    assert len(affected) == 1500
    assert all(value["error"]["code"] == "cycle" for value in errors.values())
    definitions[first]["source"] = {"record_id": row, "field_id": field}
    restored, affected = evaluate(fields, records, literals, definitions, errors, {first}, 5)
    assert len(affected) == 1500 and restored[previous]["value"] == 7
    assert restored[previous]["evaluated_revision"] == 5


def test_cycle_dependents_are_distinguished_from_cycle_members():
    fields = {"f": {"table_id": "t", "type": "number", "unit": "1"}}
    records = {r: {"table_id": "t"} for r in ("a", "b", "c", "d")}
    definitions = {(r, "f"): {"kind": "reference", "source": {"record_id": source, "field_id": "f"}}
                   for r, source in (("a", "b"), ("b", "a"), ("c", "a"), ("d", "absent"))}
    cache, _ = evaluate(fields, records, {}, definitions, {}, set(), 1)
    assert cache[("a", "f")]["error"]["code"] == "cycle"
    assert cache[("b", "f")]["error"]["code"] == "cycle"
    assert cache[("c", "f")]["error"]["code"] == "dependency_error"
    assert cache[("d", "f")]["error"]["code"] == "missing_reference"
