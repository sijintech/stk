"""stk.graph/1 validation, canonical JSON and graph hashing (standard library only).

The hub validates graphs without NumPy, so this module and ``suan.graph.registry``
never import NumPy (``tests/test_graph_schema.py`` enforces it).

``validate_graph(graph, registry)`` returns a list of :class:`GraphIssue`, each
with a stable ``code``, an RFC 6901 JSON Pointer ``path`` into the graph
document, the ``node`` id when relevant and an actionable ``hint``, so that an
LLM or a UI can fix the graph. The codes are listed in :data:`ISSUE_CODES` and
in ``docs/specs/stk-graph-v1.md``.

``check_value(value, schema)`` implements the JSON Schema subset used by node
parameter declarations (documented in the spec): ``type``, ``enum``, ``const``,
numeric bounds, string length/``pattern``, ``items``/``prefixItems``,
``minItems``/``maxItems``/``uniqueItems``, ``properties``/``patternProperties``/``required``/
``additionalProperties``/``propertyNames``/``min|maxProperties``, ``anyOf``/
``oneOf``/``allOf``/``not`` and ``if``/``then``/``else``. Annotations
(``title``, ``description``, ``default``, ``x-stk-*``) are ignored. Patterns are
searched with Python ``re`` except that ``$`` matches only at the very end of the
string, as in JSON Schema (ECMA-262) and every other client: never before a
trailing newline (:func:`schema_pattern`).
"""
from dataclasses import dataclass
import difflib
import functools
import hashlib
import json
import math
import re

__all__ = [
    "GRAPH_SCHEMA", "ISSUE_CODES", "MAX_GRAPH_BYTES", "MAX_NODES", "MAX_PARAMETERS", "MAX_PARAMS_BYTES",
    "PARAMETER_TYPES", "GraphError", "GraphIssue", "GraphValidationError",
    "canonical_json", "check_graph", "check_value", "find_param_refs", "graph_hash", "normalize_value",
    "parameter_schema", "parameter_values", "parse_port_ref", "parse_type", "pattern_search", "pointer",
    "schema_pattern", "sha256_hex", "substitute_params", "topological_order", "validate_graph",
]

GRAPH_SCHEMA = "stk.graph/1"
MAX_NODES = 200
MAX_GRAPH_BYTES = 256 * 1024
MAX_PARAMS_BYTES = 64 * 1024
MAX_PARAMETERS = 64

# \Z, not $: "$" would also accept a trailing newline ("abc\n").
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}\Z")
TYPE_RE = re.compile(r"^([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)@([1-9][0-9]*)\Z")
PORT_REF_RE = re.compile(r"^([a-z][a-z0-9_]{0,63})\.([a-z][a-z0-9_]{0,63})\Z")

GRAPH_KEYS = frozenset({"schema", "id", "name", "description", "catalog", "parameters", "time", "nodes",
                        "outputs", "ui", "extensions"})
NODE_KEYS = frozenset({"id", "type", "params", "inputs", "label", "description", "ui"})
PARAMETER_KEYS = frozenset({"name", "type", "default", "choices", "minimum", "maximum", "unit", "label",
                            "description", "ui"})
# Keys that never affect evaluation or cache keys.
NON_SEMANTIC_GRAPH_KEYS = frozenset({"id", "name", "description", "ui"})
NON_SEMANTIC_NODE_KEYS = frozenset({"label", "description", "ui"})
NON_SEMANTIC_PARAMETER_KEYS = frozenset({"label", "description", "ui"})

PARAMETER_TYPES = ("number", "integer", "boolean", "string", "step", "vector3", "int3", "range", "enum", "json")

_TIME_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"enum": ["step", "time"]},
        "current": {"type": ["number", "null"]},
        "range": {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}], "minItems": 2,
                  "maxItems": 2},
        "stride": {"anyOf": [{"type": "number", "exclusiveMinimum": 0}, {"type": "null"}]},
        "policy": {"enum": ["latest_at_or_before", "exact"]},
        "fps": {"anyOf": [{"type": "number", "exclusiveMinimum": 0}, {"type": "null"}]},
    },
    "additionalProperties": False,
}

ISSUE_CODES = {
    "invalid_document": "The graph is not a JSON object, or contains values JSON cannot represent (NaN, Inf, non-string keys).",
    "schema_version": "The 'schema' tag is not 'stk.graph/1'.",
    "missing_field": "A required key is missing (graph 'schema'/'nodes'/'outputs', node 'id'/'type').",
    "unknown_key": "A key that stk.graph/1 does not define (extension keys must start with 'x-').",
    "bad_structure": "A value has the wrong JSON shape (e.g. 'nodes' is not a list, 'params' is not an object).",
    "too_large": "A size limit is exceeded (200 nodes, 256 KiB graph, 64 KiB params per node, 64 parameters).",
    "invalid_id": "A node id, port name, parameter or output name does not match ^[a-z][a-z0-9_]{0,63}$.",
    "duplicate_id": "Two nodes share an id.",
    "invalid_type_ref": "A node 'type' is not 'namespace.family.name@major'.",
    "unknown_type": "The node type is not in the catalog (the node is kept but cannot be evaluated).",
    "catalog_version": "The graph requires a newer catalog version for a namespace than is installed.",
    "unknown_param": "A node param is not declared by its node type.",
    "missing_param": "A required node param (one without a default) is absent.",
    "invalid_param": "A node param value does not satisfy the param's schema (type, range, enum, pattern).",
    "invalid_parameter": "A graph-level parameter declaration (or a caller override) is malformed or its value has the wrong type.",
    "unknown_parameter": "A caller override names a parameter the graph does not declare.",
    "bad_param_ref": "A {\"$param\": name} reference is malformed or names an undeclared graph parameter.",
    "param_ref_type": "A graph parameter's value does not satisfy the schema of a node param that references it.",
    "reserved_key": "A '$'-prefixed key other than '$param' appears in a param value ('$anim' is reserved for later versions).",
    "unknown_input": "An input port name is not declared by the node type.",
    "bad_link": "A link is malformed or refers to an unknown node or output port.",
    "multi_link": "A list of links was given to an input port that is not multi.",
    "missing_input": "A required input port has no link.",
    "port_mismatch": "The upstream output's port type or dataset kind is not accepted by the input port.",
    "cycle": "The links form a cycle.",
    "no_outputs": "The graph declares no outputs.",
    "bad_output": "A graph output does not name an existing '<node>.<port>', or its port type cannot be delivered.",
}

# Port types a graph output may deliver (layer/camera/colormap/... only exist inside a graph).
DELIVERABLE_TYPES = frozenset({"dataset", "table", "value", "scene", "plot", "image", "payload", "file"})


class GraphError(Exception):
    """Base error with a stable code, e.g. raised by evaluators and resolvers."""

    def __init__(self, code, message, *, node=None, path="", hint=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.node = node
        self.path = path
        self.hint = hint

    def to_issue(self):
        return GraphIssue(self.code, self.message, self.path, self.node, self.hint)


class GraphValidationError(GraphError):
    """Raised by :func:`check_graph`; ``issues`` holds every error found."""

    def __init__(self, issues):
        issues = list(issues)
        first = issues[0] if issues else GraphIssue("invalid_document", "Invalid graph")
        super().__init__(first.code, f"{len(issues)} graph validation error(s); first: {first.message}",
                         node=first.node, path=first.path, hint=first.hint)
        self.issues = issues


@dataclass(frozen=True)
class GraphIssue:
    code: str
    message: str
    path: str = ""
    node: str | None = None
    hint: str | None = None
    severity: str = "error"

    def to_dict(self):
        return {"code": self.code, "message": self.message, "path": self.path, "node": self.node,
                "hint": self.hint, "severity": self.severity}


def pointer(*parts):
    """RFC 6901 JSON Pointer from path segments."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


# ---------------------------------------------------------------------------
# JSON Schema subset


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value)))


def _is_type(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return _is_number(value) and (isinstance(value, int) or float(value).is_integer())
    if name == "number":
        return _is_number(value)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, (list, tuple))
    if name == "object":
        return isinstance(value, dict)
    raise ValueError(f"Unsupported JSON Schema type {name!r}")


def _json_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_number(a) and _is_number(b):
        return a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _describe(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number" if _is_number(value) else "non-finite number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _short(value, limit=60):
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=True)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def schema_pattern(pattern):
    """A JSON-Schema ``pattern`` as a Python regex: every ``$`` outside a character class becomes ``\\Z``.

    Python's ``$`` also matches before a final newline, so ``^[a-z]+$`` would accept ``"abc\\n"``; in JSON
    Schema (ECMA-262 regular expressions, the web and desktop clients) ``$`` matches only at the end.
    Escapes (``\\$``) and ``$`` inside ``[...]`` are literal and kept as they are.
    """
    out, i, n, in_class = [], 0, len(pattern), False
    while i < n:
        c = pattern[i]
        if c == "\\":
            out.append(pattern[i:i + 2])
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
        elif c == "[":
            in_class = True
            out.append(c)
            i += 1
            if i < n and pattern[i] == "^":     # "[^]...]" and "[]...]" start with a literal "]"
                out.append("^")
                i += 1
            if i < n and pattern[i] == "]":
                out.append("]")
                i += 1
            continue
        elif c == "$":
            out.append("\\Z")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


@functools.lru_cache(maxsize=256)
def _compiled_pattern(pattern):
    return re.compile(schema_pattern(pattern))


def pattern_search(pattern, text):
    """JSON-Schema ``pattern`` semantics: :func:`re.search` with ``$`` anchored at the very end."""
    return _compiled_pattern(pattern).search(text) is not None


def check_value(value, schema, path=""):
    """Validate ``value`` against a JSON Schema subset; return ``[(pointer, message), ...]``."""
    errors = []
    _check(value, schema, path, errors)
    return errors


def _check(value, schema, path, errors):
    if schema is True or schema == {}:
        return
    if schema is False:
        errors.append((path, "no value is allowed here"))
        return
    if "type" in schema:
        types = [schema["type"]] if isinstance(schema["type"], str) else list(schema["type"])
        if not any(_is_type(value, name) for name in types):
            errors.append((path, f"expected {' or '.join(types)}, got {_describe(value)}"))
            return
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append((path, f"must be {_short(schema['const'])}"))
    if "enum" in schema and not any(_json_equal(value, option) for option in schema["enum"]):
        errors.append((path, f"must be one of {_short(schema['enum'], 200)}, got {_short(value)}"))
    if _is_number(value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append((path, f"must be >= {schema['minimum']}, got {value}"))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append((path, f"must be <= {schema['maximum']}, got {value}"))
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append((path, f"must be > {schema['exclusiveMinimum']}, got {value}"))
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append((path, f"must be < {schema['exclusiveMaximum']}, got {value}"))
    elif isinstance(value, float) and not math.isfinite(value) and "type" not in schema:
        errors.append((path, "non-finite numbers are not allowed"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append((path, f"must have at least {schema['minLength']} characters"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append((path, f"must have at most {schema['maxLength']} characters"))
        if "pattern" in schema and not pattern_search(schema["pattern"], value):
            errors.append((path, f"does not match pattern {schema['pattern']}"))
    if isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append((path, f"must have at least {schema['minItems']} items, got {len(value)}"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append((path, f"must have at most {schema['maxItems']} items, got {len(value)}"))
        prefix = schema.get("prefixItems", ())
        for index, item in enumerate(value):
            if index < len(prefix):
                _check(item, prefix[index], pointer_join(path, index), errors)
            elif "items" in schema:
                _check(item, schema["items"], pointer_join(path, index), errors)
        if schema.get("uniqueItems"):
            for index, item in enumerate(value):
                if any(_json_equal(item, other) for other in value[:index]):
                    errors.append((pointer_join(path, index), "items must be unique"))
                    break
    if isinstance(value, dict):
        for key in schema.get("required", ()):
            if key not in value:
                errors.append((pointer_join(path, key), f"required key '{key}' is missing"))
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            errors.append((path, f"must have at least {schema['minProperties']} entries"))
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            errors.append((path, f"must have at most {schema['maxProperties']} entries"))
        properties = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        for key, item in value.items():
            if not isinstance(key, str):
                errors.append((path, f"object keys must be strings, got {_short(key)}"))
                continue
            if "propertyNames" in schema:
                for sub_path, message in check_value(key, schema["propertyNames"]):
                    errors.append((pointer_join(path, key), f"invalid key: {message}"))
            matched = False
            if key in properties:
                matched = True
                _check(item, properties[key], pointer_join(path, key), errors)
            for pattern, sub in patterns.items():
                if pattern_search(pattern, key):
                    matched = True
                    _check(item, sub, pointer_join(path, key), errors)
            if not matched and "additionalProperties" in schema:
                extra = schema["additionalProperties"]
                if extra is False:
                    known = sorted(properties)
                    close = difflib.get_close_matches(key, known, n=1)
                    hint = f" (did you mean '{close[0]}'?)" if close else (f"; allowed: {', '.join(known)}" if known else "")
                    errors.append((pointer_join(path, key), f"unexpected key '{key}'{hint}"))
                else:
                    _check(item, extra, pointer_join(path, key), errors)
    for sub in schema.get("allOf", ()):
        _check(value, sub, path, errors)
    if "anyOf" in schema:
        branches = [check_value(value, sub, path) for sub in schema["anyOf"]]
        if all(branches):
            errors.append(_best_branch_error(value, schema["anyOf"], branches, path))
    if "oneOf" in schema:
        branches = [check_value(value, sub, path) for sub in schema["oneOf"]]
        passing = sum(1 for branch in branches if not branch)
        if passing == 0:
            errors.append(_best_branch_error(value, schema["oneOf"], branches, path))
        elif passing > 1:
            errors.append((path, "matches more than one allowed form"))
    if "not" in schema and not check_value(value, schema["not"], path):
        errors.append((path, "matches a form that is not allowed"))
    if "if" in schema:
        if not check_value(value, schema["if"], path):
            if "then" in schema:
                _check(value, schema["then"], path, errors)
        elif "else" in schema:
            _check(value, schema["else"], path, errors)


def _best_branch_error(value, branches, results, path):
    # Prefer the branch whose declared type matches: its message is the useful one.
    for sub, result in zip(branches, results):
        declared = sub.get("type") if isinstance(sub, dict) else None
        if declared is not None and result and any(
                _is_type(value, t) for t in ([declared] if isinstance(declared, str) else declared)):
            return result[0]
    forms = []
    for sub in branches:
        if isinstance(sub, dict) and "const" in sub:
            forms.append(_short(sub["const"]))
        elif isinstance(sub, dict) and "enum" in sub:
            forms.extend(_short(item) for item in sub["enum"])
        elif isinstance(sub, dict) and "type" in sub:
            forms.append(sub["type"] if isinstance(sub["type"], str) else "/".join(sub["type"]))
        else:
            forms.append("object")
    return (path, f"got {_short(value)}; expected one of: {', '.join(forms)}")


def pointer_join(path, *keys):
    return path + pointer(*keys)


def normalize_value(value, schema):
    """Coerce a *valid* value to its canonical JSON form for ``schema``.

    Integral floats become ``int`` where the schema says ``integer``; numbers
    become ``float`` where it says ``number`` (so 1 and 1.0 hash the same);
    ``-0.0`` becomes ``0.0``; tuples become lists. ``anyOf``/``oneOf`` use the
    first matching branch.
    """
    if not isinstance(schema, dict):
        return _plain(value)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            for sub in schema[key]:
                if not check_value(value, sub):
                    value = normalize_value(value, sub)
                    break
    types = schema.get("type")
    types = [types] if isinstance(types, str) else (types or [])
    if _is_number(value):
        if "integer" in types and float(value).is_integer() and "number" not in types:
            return int(value)
        if "number" in types:
            value = float(value)
            return 0.0 if value == 0 else value
        return value
    if isinstance(value, (list, tuple)):
        prefix = schema.get("prefixItems", ())
        items = schema.get("items", True)
        return [normalize_value(item, prefix[i] if i < len(prefix) else items) for i, item in enumerate(value)]
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        return {key: normalize_value(item, properties.get(key, extra if isinstance(extra, dict) else True))
                for key, item in value.items()}
    return value


def _plain(value):
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, float) and value == 0:
        return 0.0
    return value


# ---------------------------------------------------------------------------
# Canonical JSON and hashing


def _canon(value):
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical JSON cannot represent NaN or infinity")
        return 0.0 if value == 0 else value
    if isinstance(value, (list, tuple)):
        return [_canon(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Canonical JSON object keys must be strings")
        return {key: _canon(item) for key, item in value.items()}
    raise TypeError(f"Canonical JSON cannot represent {type(value).__name__}")


def canonical_json(value):
    """UTF-8 bytes: sorted keys, no whitespace, shortest round-trip floats, -0.0 -> 0.0, no NaN.

    ``1`` and ``1.0`` stay distinct here; node params are normalized by their
    schema first (:func:`normalize_value`) so equal values hash equally.
    """
    return json.dumps(_canon(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _semantic_graph(graph):
    result = {key: value for key, value in graph.items()
              if key not in NON_SEMANTIC_GRAPH_KEYS and not key.startswith("x-")}
    if isinstance(graph.get("nodes"), list):
        nodes = [{key: value for key, value in node.items()
                  if key not in NON_SEMANTIC_NODE_KEYS and not key.startswith("x-")}
                 if isinstance(node, dict) else node for node in graph["nodes"]]
        result["nodes"] = sorted(nodes, key=lambda n: str(n.get("id")) if isinstance(n, dict) else "")
    if isinstance(graph.get("parameters"), list):
        result["parameters"] = sorted(
            ({key: value for key, value in item.items() if key not in NON_SEMANTIC_PARAMETER_KEYS}
             if isinstance(item, dict) else item for item in graph["parameters"]),
            key=lambda p: str(p.get("name")) if isinstance(p, dict) else "")
    return result


def graph_hash(graph):
    """``"sha256:<hex>"`` of the evaluation-relevant graph content.

    Ignores ``id``, ``name``, ``description``, ``ui`` and ``x-*`` keys at the top
    level, node ``label``/``description``/``ui``/``x-*`` keys, parameter
    ``label``/``description``/``ui``, and the order of ``nodes`` and
    ``parameters`` (the order of multi-input links is significant).
    """
    return "sha256:" + sha256_hex(canonical_json(_semantic_graph(graph)))


# ---------------------------------------------------------------------------
# Graph helpers


def parse_type(type_ref):
    """``"stk.filter.contour@1"`` -> ``("stk", "filter", "contour", 1)``; ``ValueError`` if malformed."""
    match = TYPE_RE.match(type_ref) if isinstance(type_ref, str) else None
    if not match:
        raise ValueError(f"Node type must be 'namespace.family.name@major', got {type_ref!r}")
    return match.group(1), match.group(2), match.group(3), int(match.group(4))


def parse_port_ref(ref):
    """``"src.out"`` -> ``("src", "out")``; ``ValueError`` if malformed."""
    match = PORT_REF_RE.match(ref) if isinstance(ref, str) else None
    if not match:
        raise ValueError(f"Port reference must be '<node>.<port>', got {ref!r}")
    return match.group(1), match.group(2)


def _links(value):
    """Normalize an input entry to a list of link dicts (or None if malformed)."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    return None


def parameter_schema(declaration):
    """JSON Schema fragment for a graph-level parameter declaration."""
    kind = declaration.get("type")
    schema = {
        "number": {"type": "number"},
        "integer": {"type": "integer"},
        "boolean": {"type": "boolean"},
        "string": {"type": "string"},
        "step": {"anyOf": [{"type": "integer", "minimum": 0}, {"enum": ["latest", "first"]}]},
        "vector3": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "int3": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
        "range": {"type": "array", "prefixItems": [{"type": ["number", "null"]}, {"type": ["number", "null"]}],
                  "minItems": 2, "maxItems": 2},
        "enum": {"enum": declaration.get("choices", [])},
        "json": {},
    }.get(kind)
    if schema is None:
        raise ValueError(f"Unknown parameter type {kind!r}")
    schema = dict(schema)
    if kind in ("number", "integer"):
        for key in ("minimum", "maximum"):
            if _is_number(declaration.get(key)):
                schema[key] = declaration[key]
    if "choices" in declaration and kind != "enum" and isinstance(declaration["choices"], list):
        schema = {"allOf": [schema, {"enum": declaration["choices"]}]}
    return schema


def parameter_values(graph, overrides=None):
    """Effective graph parameter values: declared defaults updated by ``overrides``."""
    values = {}
    for item in graph.get("parameters") or ():
        if isinstance(item, dict) and isinstance(item.get("name"), str) and "default" in item:
            values[item["name"]] = item["default"]
    for name, value in (overrides or {}).items():
        values[name] = value
    return values


def find_param_refs(value, path=""):
    """Return ``[(pointer, name_or_None, problem_or_None), ...]`` for '$'-keys inside a param value."""
    found = []
    if isinstance(value, dict):
        dollar = [key for key in value if isinstance(key, str) and key.startswith("$")]
        if "$param" in value:
            name = value["$param"]
            if len(value) != 1:
                found.append((path, None, "a $param reference must be an object with the single key '$param'"))
            elif not isinstance(name, str) or not ID_RE.match(name):
                found.append((path, None, "the '$param' value must be a parameter name"))
            else:
                found.append((path, name, None))
            return found
        for key in dollar:
            found.append((pointer_join(path, key), None, f"reserved key '{key}'"))
        for key, item in value.items():
            if not (isinstance(key, str) and key.startswith("$")):
                found.extend(find_param_refs(item, pointer_join(path, key)))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(find_param_refs(item, pointer_join(path, index)))
    return found


def substitute_params(value, values):
    """Replace every ``{"$param": name}`` inside ``value`` with ``values[name]`` (``KeyError`` if unknown)."""
    if isinstance(value, dict):
        if set(value) == {"$param"}:
            return values[value["$param"]]
        return {key: substitute_params(item, values) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [substitute_params(item, values) for item in value]
    return value


def topological_order(graph, outputs=None):
    """Node ids needed for ``outputs`` (graph output names; default all) in dependency order.

    Ties keep document order. Raises :class:`GraphError` (code ``cycle``,
    ``bad_output`` or ``bad_link``) on graphs that fail those checks.
    """
    nodes = [node for node in graph.get("nodes") or () if isinstance(node, dict)]
    ids = [node.get("id") for node in nodes]
    upstream = {node_id: [] for node_id in ids}
    for node in nodes:
        for port, entry in (node.get("inputs") or {}).items():
            for link in _links(entry) or ():
                try:
                    source, _ = parse_port_ref(link.get("from"))
                except ValueError as exc:
                    raise GraphError("bad_link", str(exc), node=node.get("id")) from None
                if source not in upstream:
                    raise GraphError("bad_link", f"Link from unknown node '{source}'", node=node.get("id"))
                upstream[node["id"]].append(source)
    targets = []
    requested = graph.get("outputs") or {}
    for name in (outputs if outputs is not None else list(requested)):
        if name not in requested:
            raise GraphError("bad_output", f"Unknown graph output '{name}'", hint=f"Known: {', '.join(requested)}")
        try:
            targets.append(parse_port_ref(requested[name])[0])
        except ValueError as exc:
            raise GraphError("bad_output", str(exc)) from None
    needed, stack = set(), [t for t in targets if t in upstream]
    while stack:
        current = stack.pop()
        if current not in needed:
            needed.add(current)
            stack.extend(upstream[current])
    order, done = [], set()
    remaining = [node_id for node_id in ids if node_id in needed]
    while remaining:
        progressed = False
        for node_id in list(remaining):
            if all(dep in done for dep in upstream[node_id]):
                order.append(node_id)
                done.add(node_id)
                remaining.remove(node_id)
                progressed = True
        if not progressed:
            raise GraphError("cycle", f"Cycle among nodes: {', '.join(remaining)}", node=remaining[0])
    return order


# ---------------------------------------------------------------------------
# Validation


def check_graph(graph, registry, *, parameters=None):
    """Raise :class:`GraphValidationError` if :func:`validate_graph` finds errors."""
    errors = [issue for issue in validate_graph(graph, registry, parameters=parameters)
              if issue.severity == "error"]
    if errors:
        raise GraphValidationError(errors)


def validate_graph(graph, registry, *, parameters=None):
    """Validate an stk.graph/1 document against a node registry; return a list of :class:`GraphIssue`.

    ``registry`` is a :class:`suan.graph.registry.Registry` (a registry built
    from an exported catalog with ``Registry.from_catalog`` works the same).
    ``parameters`` are caller overrides of graph parameters; they are checked
    like the declared defaults. Never imports NumPy and never runs node code.
    """
    from .registry import ports_compatible  # local import: registry imports this module

    issues = []

    def add(code, message, path="", node=None, hint=None, severity="error"):
        issues.append(GraphIssue(code, message, path, node, hint, severity))

    if not isinstance(graph, dict):
        add("invalid_document", f"A graph must be a JSON object, got {_describe(graph)}")
        return issues
    try:
        size = len(canonical_json(graph))
    except (TypeError, ValueError) as exc:
        add("invalid_document", f"The graph is not plain JSON: {exc}")
        return issues
    if size > MAX_GRAPH_BYTES:
        add("too_large", f"The graph is {size} bytes; the limit is {MAX_GRAPH_BYTES}",
            hint="Move large inline data into a dataset referenced through a binding")
    if "schema" not in graph:
        add("missing_field", "The graph has no 'schema' key", "/schema", hint="Add \"schema\": \"stk.graph/1\"")
    elif graph["schema"] != GRAPH_SCHEMA:
        add("schema_version", f"Unsupported graph schema {_short(graph['schema'])}", "/schema",
            hint="This evaluator reads \"stk.graph/1\"")
    for key in graph:
        if key not in GRAPH_KEYS and not key.startswith("x-"):
            add("unknown_key", f"Unknown graph key '{key}'", pointer(key),
                hint=f"Allowed: {', '.join(sorted(GRAPH_KEYS))}; extensions must start with 'x-'")

    # Graph-level catalog requirements.
    catalog = graph.get("catalog")
    if catalog is not None:
        if not isinstance(catalog, dict):
            add("bad_structure", "'catalog' must be an object like {\"stk\": 1}", "/catalog")
        else:
            installed = getattr(registry, "namespaces", {}) or {}
            for namespace, required in catalog.items():
                if required is None:
                    continue
                if not _is_type(required, "integer") or required < 1:
                    add("bad_structure", f"Catalog version for '{namespace}' must be a positive integer or null",
                        pointer("catalog", namespace))
                elif installed.get(namespace, 0) < required:
                    add("catalog_version", f"The graph needs catalog '{namespace}' version >= {required}; installed: "
                        f"{installed.get(namespace, 'none')}", pointer("catalog", namespace),
                        hint="Install the node package that provides this namespace, or relax the requirement")

    if "time" in graph:
        for sub_path, message in check_value(graph["time"], _TIME_SCHEMA, "/time"):
            add("bad_structure", f"Invalid time block: {message}", sub_path)

    # Graph parameters.
    declared = {}
    named = set()  # every parameter name that appears, valid or not
    items = graph.get("parameters", [])
    if not isinstance(items, list):
        add("bad_structure", "'parameters' must be a list of {name, type, default}", "/parameters")
        items = []
    if len(items) > MAX_PARAMETERS:
        add("too_large", f"{len(items)} graph parameters; the limit is {MAX_PARAMETERS}", "/parameters")
    for index, item in enumerate(items):
        path = pointer("parameters", index)
        if not isinstance(item, dict):
            add("invalid_parameter", "A parameter must be an object {name, type, default}", path)
            continue
        for key in item:
            if key not in PARAMETER_KEYS:
                add("invalid_parameter", f"Unknown parameter key '{key}'", pointer_join(path, key),
                    hint=f"Allowed: {', '.join(sorted(PARAMETER_KEYS))}")
        name = item.get("name")
        if not isinstance(name, str) or not ID_RE.match(name):
            add("invalid_id", f"Parameter name {_short(name)} must match ^[a-z][a-z0-9_]{{0,63}}$",
                pointer_join(path, "name"))
            continue
        if name in named:
            add("invalid_parameter", f"Duplicate parameter '{name}'", pointer_join(path, "name"))
            continue
        named.add(name)
        if item.get("type") not in PARAMETER_TYPES:
            add("invalid_parameter", f"Parameter '{name}' has unknown type {_short(item.get('type'))}",
                pointer_join(path, "type"), hint=f"Types: {', '.join(PARAMETER_TYPES)}")
            continue
        if item["type"] == "enum" and not (isinstance(item.get("choices"), list) and item["choices"]):
            add("invalid_parameter", f"Enum parameter '{name}' needs a non-empty 'choices' list",
                pointer_join(path, "choices"))
            continue
        if "default" not in item:
            add("invalid_parameter", f"Parameter '{name}' has no default", path,
                hint="Every graph parameter needs a default so the graph evaluates without overrides")
            continue
        schema = parameter_schema(item)
        problems = check_value(item["default"], schema, pointer_join(path, "default"))
        for sub_path, message in problems:
            add("invalid_parameter", f"Default of parameter '{name}': {message}", sub_path)
        if not problems:
            declared[name] = (item, schema)
    values = {name: item["default"] for name, (item, _) in declared.items()}
    if parameters is not None:
        if not isinstance(parameters, dict):
            add("invalid_parameter", "Parameter overrides must be an object {name: value}")
        else:
            for name, value in parameters.items():
                if name not in declared:
                    add("unknown_parameter", f"Override for undeclared parameter '{name}'",
                        hint=f"Declared: {', '.join(sorted(declared)) or 'none'}")
                    continue
                problems = check_value(value, declared[name][1])
                for _, message in problems:
                    add("invalid_parameter", f"Override of parameter '{name}': {message}")
                if not problems:
                    values[name] = value

    # Nodes.
    nodes = graph.get("nodes")
    if "nodes" not in graph:
        add("missing_field", "The graph has no 'nodes' list", "/nodes")
        nodes = []
    elif not isinstance(nodes, list):
        add("bad_structure", "'nodes' must be a list", "/nodes")
        nodes = []
    elif not nodes:
        add("bad_structure", "'nodes' must not be empty", "/nodes")
    if len(nodes) > MAX_NODES:
        # Stop here: the per-node checks below are linear, but a longer chain is not worth validating.
        add("too_large", f"{len(nodes)} nodes; the limit is {MAX_NODES}", "/nodes",
            hint="Split the work into several graphs")
        return issues
    by_id = {}  # id -> (index, node dict, NodeType or None)
    for index, node in enumerate(nodes):
        path = pointer("nodes", index)
        if not isinstance(node, dict):
            add("bad_structure", "A node must be an object {id, type, params, inputs}", path)
            continue
        node_id = node.get("id")
        if "id" not in node:
            add("missing_field", "Node has no 'id'", path)
            continue
        if not isinstance(node_id, str) or not ID_RE.match(node_id):
            add("invalid_id", f"Node id {_short(node_id)} must match ^[a-z][a-z0-9_]{{0,63}}$",
                pointer_join(path, "id"))
            continue
        if node_id in by_id:
            add("duplicate_id", f"Duplicate node id '{node_id}' (first at /nodes/{by_id[node_id][0]})",
                pointer_join(path, "id"), node_id, hint="Give every node a unique id")
            continue
        for key in node:
            if key not in NODE_KEYS and not key.startswith("x-"):
                close = difflib.get_close_matches(key, sorted(NODE_KEYS), n=1)
                add("unknown_key", f"Unknown node key '{key}'", pointer_join(path, key), node_id,
                    hint=f"Did you mean '{close[0]}'?" if close else f"Allowed: {', '.join(sorted(NODE_KEYS))}")
        node_type = None
        type_ref = node.get("type")
        if "type" not in node:
            add("missing_field", f"Node '{node_id}' has no 'type'", path, node_id)
        elif not isinstance(type_ref, str) or not TYPE_RE.match(type_ref):
            add("invalid_type_ref", f"Node type {_short(type_ref)} is not 'namespace.family.name@major'",
                pointer_join(path, "type"), node_id, hint="Example: \"stk.filter.contour@1\"")
        else:
            node_type = registry.get(type_ref)
            if node_type is None:
                known = [t for t in registry.types() if t.rsplit("@", 1)[0] == type_ref.rsplit("@", 1)[0]]
                close = known or difflib.get_close_matches(type_ref, registry.types(), n=3)
                add("unknown_type", f"Node type '{type_ref}' is not in the catalog", pointer_join(path, "type"),
                    node_id, hint=f"Did you mean: {', '.join(close)}?" if close else
                    "Run `suan graph catalog` to list node types")
        for key, kind in (("params", "object"), ("inputs", "object")):
            if key in node and not isinstance(node[key], dict):
                add("bad_structure", f"Node '{node_id}' {key} must be an {kind}", pointer_join(path, key), node_id)
        by_id[node_id] = (index, node, node_type)

    # Params and inputs of known node types.
    edges = {node_id: [] for node_id in by_id}
    for node_id, (index, node, node_type) in by_id.items():
        path = pointer("nodes", index)
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if isinstance(node.get("params"), dict):
            try:
                if len(canonical_json(params)) > MAX_PARAMS_BYTES:
                    add("too_large", f"Params of node '{node_id}' exceed {MAX_PARAMS_BYTES} bytes",
                        pointer_join(path, "params"), node_id,
                        hint="Reference large data through a dataset instead of inlining it")
            except (TypeError, ValueError):
                pass
        # $param references are checked even when the node type is unknown.
        refs, skip = {}, set()
        for name, value in params.items():
            for ref_path, ref_name, problem in find_param_refs(value, pointer_join(path, "params", name)):
                if problem or ref_name not in declared:
                    skip.add(name)
                if problem and problem.startswith("reserved key"):
                    add("reserved_key", f"Node '{node_id}' param '{name}': {problem}", ref_path, node_id,
                        hint="Only {\"$param\": name} is supported in stk.graph/1; '$anim' is reserved")
                elif problem:
                    add("bad_param_ref", f"Node '{node_id}' param '{name}': {problem}", ref_path, node_id,
                        hint="Write {\"$param\": \"<name>\"} with a declared graph parameter")
                elif ref_name not in named:
                    add("bad_param_ref", f"Node '{node_id}' param '{name}' references undeclared parameter "
                        f"'{ref_name}'", ref_path, node_id,
                        hint=f"Declare it under graph 'parameters'; declared: {', '.join(sorted(declared)) or 'none'}")
                else:
                    refs.setdefault(name, []).append(ref_name)
        if node_type is None:
            for port, entry in inputs.items():
                for link in _links(entry) or ():
                    try:
                        source, _ = parse_port_ref(link.get("from"))
                        if source in by_id:
                            edges[node_id].append(source)
                    except ValueError:
                        pass
            continue
        declared_params = node_type.params
        for name, value in params.items():
            param_path = pointer_join(path, "params", name)
            if name not in declared_params:
                close = difflib.get_close_matches(name, list(declared_params), n=1)
                add("unknown_param", f"'{node_type.id}' has no param '{name}'", param_path, node_id,
                    hint=(f"Did you mean '{close[0]}'? " if close else "") +
                    f"Params: {', '.join(declared_params) or 'none'}")
                continue
            schema = declared_params[name].schema
            if name in skip:
                continue
            try:
                effective = substitute_params(value, values)
            except KeyError:
                continue  # already reported as bad_param_ref
            for sub_path, message in check_value(effective, schema, param_path):
                if name in refs:
                    add("param_ref_type", f"Node '{node_id}' param '{name}' (via parameter "
                        f"{', '.join(repr(r) for r in refs[name])}): {message}", sub_path, node_id,
                        hint=f"Parameter values must satisfy '{node_type.id}' param '{name}'")
                else:
                    add("invalid_param", f"Node '{node_id}' param '{name}': {message}", sub_path, node_id,
                        hint=_param_hint(schema))
        for name, param in declared_params.items():
            if param.required and name not in params:
                add("missing_param", f"Node '{node_id}' ('{node_type.id}') needs param '{name}'",
                    pointer_join(path, "params"), node_id, hint=_param_hint(param.schema))
        input_ports = {port.name: port for port in node_type.inputs}
        for port_name, entry in inputs.items():
            port_path = pointer_join(path, "inputs", port_name)
            if port_name not in input_ports:
                close = difflib.get_close_matches(port_name, list(input_ports), n=1)
                add("unknown_input", f"'{node_type.id}' has no input '{port_name}'", port_path, node_id,
                    hint=(f"Did you mean '{close[0]}'? " if close else "") +
                    f"Inputs: {', '.join(input_ports) or 'none'}")
                continue
            port = input_ports[port_name]
            links = _links(entry)
            if links is None:
                add("bad_link", f"Input '{port_name}' of node '{node_id}' must be {{\"from\": \"node.port\"}} "
                    "or a list of them", port_path, node_id)
                continue
            if isinstance(entry, list) and not port.multi:
                add("multi_link", f"Input '{port_name}' of node '{node_id}' takes one link, got a list",
                    port_path, node_id, hint="Link a single {\"from\": \"node.port\"}")
                continue
            for link_index, link in enumerate(links):
                link_path = pointer_join(port_path, link_index) if isinstance(entry, list) else port_path
                extra = [key for key in link if key not in ("from", "as")]
                if extra or "from" not in link:
                    add("bad_link", f"A link is {{\"from\": \"node.port\"}} with optional \"as\"; got keys "
                        f"{', '.join(link) or 'none'}", link_path, node_id)
                    continue
                if "as" in link and (not isinstance(link["as"], str) or not ID_RE.match(link["as"])):
                    add("bad_link", f"Link alias {_short(link['as'])} must match ^[a-z][a-z0-9_]{{0,63}}$",
                        pointer_join(link_path, "as"), node_id)
                try:
                    source, source_port = parse_port_ref(link["from"])
                except ValueError as exc:
                    add("bad_link", str(exc), pointer_join(link_path, "from"), node_id)
                    continue
                if source not in by_id:
                    close = difflib.get_close_matches(source, list(by_id), n=1)
                    add("bad_link", f"Input '{port_name}' of node '{node_id}' links from unknown node '{source}'",
                        pointer_join(link_path, "from"), node_id,
                        hint=f"Did you mean '{close[0]}'?" if close else None)
                    continue
                edges[node_id].append(source)
                source_type = by_id[source][2]
                if source_type is None:
                    continue
                outputs_of = {p.name: p for p in source_type.outputs}
                if source_port not in outputs_of:
                    add("bad_link", f"Node '{source}' ('{source_type.id}') has no output '{source_port}'",
                        pointer_join(link_path, "from"), node_id,
                        hint=f"Outputs: {', '.join(outputs_of)}")
                    continue
                kinds = _output_kinds(source, source_port, by_id, set())
                if not ports_compatible(outputs_of[source_port], port, kinds):
                    add("port_mismatch", f"'{source}.{source_port}' ({_port_label(outputs_of[source_port], kinds)}) "
                        f"cannot feed input '{port_name}' of node '{node_id}' ({_port_label(port)})",
                        pointer_join(link_path, "from"), node_id,
                        hint="Insert a node that converts the data, or link a compatible output")
        for port in node_type.inputs:
            entry = inputs.get(port.name)
            if port.required and (entry is None or entry == []):
                add("missing_input", f"Node '{node_id}' ('{node_type.id}') needs input '{port.name}' "
                    f"({_port_label(port)})", pointer_join(path, "inputs"), node_id,
                    hint=f"Add \"inputs\": {{\"{port.name}\": {{\"from\": \"<node>.<port>\"}}}}")

    # Cycles (Kahn).
    indegree = {node_id: 0 for node_id in edges}
    downstream = {node_id: [] for node_id in edges}
    for node_id, sources in edges.items():
        for source in sources:
            indegree[node_id] += 1
            downstream[source].append(node_id)
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    while ready:
        current = ready.pop()
        for target in downstream[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    cyclic = {node_id for node_id, degree in indegree.items() if degree > 0}
    pruned = True
    while pruned:  # drop nodes downstream of a cycle that are not on one
        pruned = False
        for node_id in list(cyclic):
            if not any(target in cyclic for target in downstream[node_id]):
                cyclic.discard(node_id)
                pruned = True
    cyclic = [node_id for node_id in edges if node_id in cyclic]
    if cyclic:
        add("cycle", f"The links form a cycle through nodes: {', '.join(cyclic)}", "/nodes", cyclic[0],
            hint="A graph must be acyclic; remove one of the links between these nodes")

    # Outputs.
    outputs = graph.get("outputs")
    if "outputs" not in graph:
        add("missing_field", "The graph has no 'outputs'", "/outputs",
            hint="Add \"outputs\": {\"<name>\": \"<node>.<port>\"}")
    elif not isinstance(outputs, dict):
        add("bad_structure", "'outputs' must be an object {name: \"node.port\"}", "/outputs")
    elif not outputs:
        add("no_outputs", "The graph declares no outputs", "/outputs",
            hint="Add \"outputs\": {\"<name>\": \"<node>.<port>\"}")
    else:
        for name, ref in outputs.items():
            path = pointer("outputs", name)
            if not isinstance(name, str) or not ID_RE.match(name):
                add("invalid_id", f"Output name {_short(name)} must match ^[a-z][a-z0-9_]{{0,63}}$", path)
            try:
                source, port_name = parse_port_ref(ref)
            except ValueError as exc:
                add("bad_output", str(exc), path)
                continue
            if source not in by_id:
                add("bad_output", f"Output '{name}' names unknown node '{source}'", path)
                continue
            source_type = by_id[source][2]
            if source_type is None:
                continue
            ports = {p.name: p for p in source_type.outputs}
            if port_name not in ports:
                add("bad_output", f"Output '{name}': node '{source}' has no output port '{port_name}'", path, source,
                    hint=f"Outputs of '{source_type.id}': {', '.join(ports)}")
            elif ports[port_name].type not in DELIVERABLE_TYPES:
                add("bad_output", f"Output '{name}': port type '{ports[port_name].type}' cannot be delivered",
                    path, source, hint="Deliver a scene, payload, image, plot, table, value, file or dataset instead")
    return issues


def _output_kinds(node_id, port_name, by_id, seen):
    """Possible dataset kinds of an output port (``None`` = unknown / any).

    Follows ``kind_from`` links upstream iteratively (a long chain never exhausts the stack).
    """
    while True:
        key = (node_id, port_name)
        if key in seen:
            return None
        seen.add(key)
        node_type = by_id[node_id][2]
        port = next((p for p in node_type.outputs if p.name == port_name), None) if node_type else None
        if port is None:
            return None
        if not port.kind_from:
            return port.kinds
        entry = (by_id[node_id][1].get("inputs") or {}).get(port.kind_from)
        links = _links(entry) if entry is not None else None
        if links:
            try:
                source, source_port = parse_port_ref(links[0].get("from"))
            except ValueError:
                return None
            if source in by_id and by_id[source][2] is not None:
                node_id, port_name = source, source_port
                continue
        source_input = next((p for p in node_type.inputs if p.name == port.kind_from), None)
        return tuple(source_input.accepts) if source_input and source_input.accepts else None


def _port_label(port, kinds=None):
    types = port.type if isinstance(port.type, str) else " | ".join(port.type)
    kinds = kinds if kinds is not None else (getattr(port, "accepts", None) or port.kinds)
    return f"{types}<{', '.join(kinds)}>" if kinds else types


def _param_hint(schema):
    if "enum" in schema:
        return f"Allowed values: {_short(schema['enum'], 200)}"
    if "default" in schema:
        return f"Default: {_short(schema['default'])}"
    parts = []
    for key in ("type", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems"):
        if key in schema:
            parts.append(f"{key}={_short(schema[key])}")
    return ", ".join(parts) or None
