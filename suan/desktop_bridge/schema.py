"""Validation of bridge messages against ``desktop-bridge-1.schema.json`` (standard library only).

The schema uses the JSON Schema subset of :func:`suan.graph.schema.check_value` plus local
``$ref`` (``#/$defs/...``), which is inlined here before checking. The C++ client validates the
same schema with its own subset validator (stk_io).
"""
from functools import lru_cache

from suan.contracts import load_schema
from suan.graph.schema import check_value

__all__ = ["event_names", "method_names", "validate_incoming", "validate_outgoing", "validate_params"]

SCHEMA_ID = "desktop-bridge-1"


@lru_cache(maxsize=1)
def _schema():
    return load_schema(SCHEMA_ID)


def _pointer(document, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"Only local $ref is supported, got {ref!r}")
    node = document
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _inline(node, document, depth=0):
    if depth > 64:
        raise ValueError("The schema's $ref chain is too deep (recursive?)")
    if isinstance(node, dict):
        if "$ref" in node:
            target = _inline(_pointer(document, node["$ref"]), document, depth + 1)
            rest = {k: _inline(v, document, depth + 1) for k, v in node.items() if k != "$ref"}
            if not rest:
                return target
            return {"allOf": [target, rest]}
        return {k: _inline(v, document, depth + 1) for k, v in node.items() if k not in ("$defs", "$schema", "$id")}
    if isinstance(node, list):
        return [_inline(item, document, depth + 1) for item in node]
    return node


@lru_cache(maxsize=None)
def _resolved(ref):
    document = _schema()
    return _inline({"$ref": ref}, document)


def method_names():
    return tuple(sorted(_schema()["$defs"]["methods"]))


def event_names():
    return tuple(sorted(_schema()["$defs"]["events"]))


def _method_ref(method, part):
    return f"#/$defs/methods/{method.replace('~', '~0').replace('/', '~1')}/{part}"


def validate_params(method, params):
    """``[(json_pointer, message)]`` of a request's params (empty when valid)."""
    if method not in _schema()["$defs"]["methods"]:
        return [("", f"unknown method {method!r}")]
    return check_value(params, _resolved(_method_ref(method, "params")), "/params")


def validate_incoming(message):
    """Check a request from the app: the envelope, then its method's params."""
    errors = check_value(message, _resolved("#/$defs/request"))
    if errors or not isinstance(message, dict):
        return errors
    return validate_params(message["method"], message.get("params", {}))


def validate_outgoing(message, method=None):
    """Check a message the bridge sends: envelope, then the result (needs ``method``) or event data."""
    if isinstance(message, dict) and "event" in message:
        errors = check_value(message, _resolved("#/$defs/event"))
        if errors:
            return errors
        if message["event"] not in _schema()["$defs"]["events"]:
            return [("/event", f"unknown event {message['event']!r}")]
        return check_value(message["data"], _resolved(f"#/$defs/events/{message['event']}"), "/data")
    errors = check_value(message, _resolved("#/$defs/response"))
    if errors:
        return errors
    if "result" in message and method is not None:
        if method not in _schema()["$defs"]["methods"]:
            return [("", f"unknown method {method!r}")]
        return check_value(message["result"], _resolved(_method_ref(method, "result")), "/result")
    return []
