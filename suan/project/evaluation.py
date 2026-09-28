"""Stable-cell dependency evaluation, with iterative graph traversal and selective caches."""
from collections import defaultdict, deque
import json

from .expressions import ENGINE_VERSION, EvaluationError, Expression, Value, check_target


def address(reference):
    return reference["record_id"], reference["field_id"]


def dependencies(definition):
    if definition["kind"] == "reference":
        return {address(definition["source"])}
    return {address(source) for source in definition["bindings"].values()}


def _cycles(edges):
    """Iterative Kosaraju: long reference chains never consume the Python call stack."""
    visited, order = set(), []
    for root in edges:
        if root in visited:
            continue
        visited.add(root)
        stack = [(root, iter(edges[root]))]
        while stack:
            node, iterator = stack[-1]
            child = next(iterator, None)
            if child is None:
                order.append(node)
                stack.pop()
            elif child not in visited:
                visited.add(child)
                stack.append((child, iter(edges[child])))
    reverse = defaultdict(set)
    for node, children in edges.items():
        for child in children:
            reverse[child].add(node)
    visited, cyclic = set(), set()
    for root in reversed(order):
        if root in visited:
            continue
        group, stack = set(), [root]
        visited.add(root)
        while stack:
            node = stack.pop()
            group.add(node)
            for child in reverse[node]:
                if child not in visited:
                    visited.add(child)
                    stack.append(child)
        if len(group) > 1 or root in edges[root]:
            cyclic.update(group)
    return cyclic


def evaluate(fields, records, literals, definitions, cached, changed, revision):
    """Return cache + affected definitions; all mappings use UUID identity, never display order.

    A cache entry's evaluated_revision changes only when one of its dependencies/definition
    changes, or when the cache/engine version is missing. Name-only edits leave it untouched.
    """
    def valid_cache(key, entry):
        if not isinstance(entry, dict) or type(entry.get("engine_version")) is not int or entry["engine_version"] != ENGINE_VERSION:
            return False
        stamp = entry.get("evaluated_revision")
        if type(stamp) is not int or not 0 <= stamp <= revision:
            return False
        if entry.get("state") == "ok":
            if "value" not in entry or "unit" not in entry or (entry["unit"] is not None and not isinstance(entry["unit"], str)):
                return False
            try:
                json.dumps(entry["value"], allow_nan=False)
                field = fields[key[1]]
                check_target(Value(entry["value"], entry["unit"]), field["type"], field["unit"])
                return True
            except (EvaluationError, ValueError, TypeError, RecursionError):
                return False
        error = entry.get("error")
        if entry.get("state") != "error" or not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
            return False
        source = error.get("source")
        return "source" not in error or (isinstance(source, dict) and set(source) == {"record_id", "field_id"}
                                          and all(isinstance(value, str) for value in source.values()))

    cached = {key: value for key, value in cached.items() if key in definitions and valid_cache(key, value)}
    deps = {key: dependencies(value) for key, value in definitions.items()}
    reverse = defaultdict(set)
    for key, sources in deps.items():
        for source in sources:
            reverse[source].add(key)
    dirty = set(changed)
    dirty.update(key for key in definitions if key not in cached or cached[key].get("engine_version") != ENGINE_VERSION)
    queue = deque(dirty)
    while queue:
        source = queue.popleft()
        for key in reverse[source]:
            if key not in dirty:
                dirty.add(key)
                queue.append(key)
    affected = dirty & definitions.keys()
    cache = {key: value for key, value in cached.items() if key in definitions}
    if not affected:
        return cache, affected
    edges = {key: sources & definitions.keys() for key, sources in deps.items()}
    cyclic = _cycles(edges)

    def fail(key, error):
        cache[key] = {"state": "error", "error": error.document(),
                      "evaluated_revision": revision, "engine_version": ENGINE_VERSION}

    for key in cyclic & affected:
        fail(key, EvaluationError("cycle", "Cell belongs to a reference/expression cycle", key))

    def resolve(key):
        record, field = records.get(key[0]), fields.get(key[1])
        if record is None or field is None or record["table_id"] != field["table_id"]:
            raise EvaluationError("missing_reference", "Referenced record/field is missing or belongs to a different table", key)
        if key in definitions:
            entry = cache[key]
            if entry["state"] != "ok":
                raise EvaluationError("dependency_error", "Referenced cell has an evaluation error", key)
            return Value(entry["value"], entry.get("unit"))
        if key not in literals:
            raise EvaluationError("missing_value", "Referenced cell is unset", key)
        return Value(literals[key], field["unit"])

    pending = affected - cyclic
    counts = {key: len(edges[key] & pending) for key in pending}
    queue = deque(sorted(key for key, count in counts.items() if count == 0))
    completed = set()
    while queue:
        key = queue.popleft()
        definition, field = definitions[key], fields[key[1]]
        try:
            if definition["kind"] == "reference":
                result = resolve(address(definition["source"]))
            else:
                expression = Expression(definition["expression"], definition["bindings"].keys())
                result = expression.evaluate(lambda name: resolve(address(definition["bindings"][name])))
            check_target(result, field["type"], field["unit"])
            cache[key] = {"state": "ok", "value": result.value, "unit": result.unit,
                          "evaluated_revision": revision, "engine_version": ENGINE_VERSION}
        except EvaluationError as exc:
            fail(key, exc)
        completed.add(key)
        for target in reverse[key] & pending:
            counts[target] -= 1
            if counts[target] == 0:
                queue.append(target)
    assert completed == pending, "dependency ordering left a non-cyclic node unevaluated"
    return cache, affected
