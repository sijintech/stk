"""Bounded peer control messages and pure capability negotiation.

This module does not authenticate a channel, grant project access, open a database,
or dispatch the desktop's private stdio bridge. The trusted endpoint does those
steps separately; names advertised by hello are not authorization.
"""
import json
import math
import re
from uuid import UUID


FORMAT = "stk.peer/1"
PROTOCOL_VERSION = 1
SUPPORTED_PROTOCOLS = (PROTOCOL_VERSION,)
MAX_MESSAGE_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_COMMANDS = 1000
MAX_REQUEST_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
METHODS = frozenset(("peer.hello", "project.catalog", "project.table.read",
                     "project.edit_operations.apply_once", "project.edit_operations.get"))
ERROR_CODES = frozenset(("invalid_request", "invalid_params", "unsupported", "unauthorized", "forbidden",
                         "not_found", "conflict", "busy", "unavailable", "limit_exceeded", "internal_error"))
_METHOD = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\Z")
_TARGET = frozenset(("project_id", "grant_id", "database_generation"))


class PeerProtocolError(ValueError):
    """A stable error without the rejected body, local paths or credentials."""

    def __init__(self, code, message):
        if code not in ERROR_CODES:
            raise ValueError("Unknown peer error code")
        self.code, self.message = code, message
        super().__init__(message)

    def to_dict(self):
        return {"code": self.code, "message": self.message}


def _fail(code="invalid_request", message="Message does not match the peer protocol"):
    raise PeerProtocolError(code, message) from None


def _fields(value, required, optional=(), *, code="invalid_request"):
    if type(value) is not dict or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        _fail(code)


def _uuid(value):
    if type(value) is not str or len(value) != 36:
        _fail("invalid_params", "Identity must be a canonical UUID")
    try:
        if str(UUID(value)) != value:
            _fail("invalid_params", "Identity must be a canonical UUID")
    except ValueError:
        _fail("invalid_params", "Identity must be a canonical UUID")


def _positive_integer(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        _fail("invalid_params")


def _tree(value, depth=0):
    kind = type(value)
    if kind in (dict, list):
        depth += 1
        if depth > MAX_JSON_DEPTH:
            _fail("limit_exceeded", "Peer JSON nesting exceeds its limit")
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail()
            _tree(key, depth)
            _tree(item, depth)
    elif kind is list:
        for item in value:
            _tree(item, depth)
    elif kind is str:
        if len(value) > MAX_MESSAGE_BYTES:
            _fail("limit_exceeded", "Peer message exceeds its byte limit")
        try:
            value.encode("utf-8")
        except UnicodeError:
            _fail()
    elif kind is float:
        if not math.isfinite(value):
            _fail()
    elif value is not None and kind not in (bool, int):
        _fail()


def _encode(value, maximum=MAX_MESSAGE_BYTES):
    _tree(value)
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, sort_keys=True,
                                      separators=(",", ":")).iterencode(value):
            block = chunk.encode("utf-8")
            size += len(block)
            if size > maximum:
                _fail("limit_exceeded", "Peer message exceeds its byte limit")
            chunks.append(block)
    except PeerProtocolError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail()
    return b"".join(chunks)


def _depth(raw):
    # Bound nesting before json.loads; braces inside escaped JSON strings do not count.
    depth, quoted, escaped = 0, False, False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                _fail("limit_exceeded", "Peer JSON nesting exceeds its limit")
        elif char in (93, 125):
            depth -= 1


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            _fail()
        value[key] = item
    return value


def _constant(_):
    _fail()


def _decode(raw):
    if not isinstance(raw, (bytes, bytearray)):
        _fail()
    if len(raw) > MAX_MESSAGE_BYTES:
        _fail("limit_exceeded", "Peer message exceeds its byte limit")
    _depth(raw)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError):
        _fail()
    _tree(value)
    return value


def _capabilities(value):
    if type(value) is not dict or len(value) > 64:
        _fail("invalid_params")
    for name, version in value.items():
        if type(name) is not str or len(name) > 128 or not _METHOD.fullmatch(name):
            _fail("invalid_params")
        _positive_integer(version, 65535)


def _hello_params(params):
    _fields(params, ("protocols", "capabilities"), code="invalid_params")
    protocols = params["protocols"]
    if type(protocols) is not list or not 1 <= len(protocols) <= 16:
        _fail("invalid_params")
    for version in protocols:
        _positive_integer(version, 65535)
    if len(set(protocols)) != len(protocols):
        _fail("invalid_params")
    _capabilities(params["capabilities"])


def _project_params(method, params):
    extra = {
        "project.catalog": ((), ("expected_revision", "offset", "limit")),
        "project.table.read": (("table_id", "expected_revision"), ("offset", "limit", "record_id")),
        "project.edit_operations.apply_once": (("operation_id", "expected_revision", "commands"), ()),
        "project.edit_operations.get": (("operation_id",), ()),
    }[method]
    _fields(params, _TARGET | set(extra[0]), extra[1], code="invalid_params")
    for key in _TARGET:
        _uuid(params[key])
    for key in ("table_id", "record_id", "operation_id"):
        if key in params:
            _uuid(params[key])
    if method == "project.edit_operations.apply_once":
        commands = params["commands"]
        if type(commands) is not list or not 1 <= len(commands) <= MAX_COMMANDS:
            _fail("invalid_params")
        # A necessary input bound; the core also includes its trusted scope/identity overhead.
        _encode(commands, MAX_REQUEST_BYTES)
    if method == "project.table.read" and "record_id" in params and params.get("offset", 0) != 0:
        _fail("invalid_params")
    # Reuse only the published command/read type contracts. Never instantiate or call Bridge.
    from suan.desktop_bridge.schema import validate_params
    local = {key: item for key, item in params.items() if key not in _TARGET}
    local["handle"] = "0" * 32
    if validate_params(method, local):
        _fail("invalid_params", "Parameters do not match the peer method contract")


def _request(message):
    _fields(message, ("format", "id", "method", "params"))
    if message["format"] != FORMAT:
        _fail("unsupported", "Unsupported peer protocol format")
    _uuid(message["id"])
    method = message["method"]
    if type(method) is not str or method not in METHODS:
        _fail("unsupported", "Peer method is not supported")
    if method == "peer.hello":
        _hello_params(message["params"])
    else:
        _project_params(method, message["params"])


def _hello_result(result):
    _fields(result, ("protocol", "capabilities", "unavailable", "limits"))
    if type(result["protocol"]) is not int or result["protocol"] not in SUPPORTED_PROTOCOLS:
        _fail()
    _capabilities(result["capabilities"])
    if not result["capabilities"].keys() <= METHODS or any(v != 1 for v in result["capabilities"].values()):
        _fail()
    unavailable = result["unavailable"]
    if type(unavailable) is not list or len(unavailable) > 64 or any(type(item) is not str for item in unavailable):
        _fail()
    if unavailable != sorted(set(unavailable)) or set(unavailable) & result["capabilities"].keys():
        _fail()
    _capabilities({name: 1 for name in unavailable})
    limits = {"message_bytes": MAX_MESSAGE_BYTES, "json_depth": MAX_JSON_DEPTH, "commands": MAX_COMMANDS,
              "request_bytes": MAX_REQUEST_BYTES, "receipt_bytes": MAX_RECEIPT_BYTES}
    if type(result["limits"]) is not dict or result["limits"] != limits:
        _fail()


def _response(message, method=None):
    if type(message) is not dict or ("result" in message) == ("error" in message):
        _fail()
    _fields(message, ("format", "id", "result" if "result" in message else "error"))
    if message["format"] != FORMAT:
        _fail("unsupported", "Unsupported peer protocol format")
    if "result" in message or message["id"] is not None:
        _uuid(message["id"])
    if "error" in message:
        error = message["error"]
        _fields(error, ("code", "message"))
        if (type(error["code"]) is not str or error["code"] not in ERROR_CODES or
                type(error["message"]) is not str or not 1 <= len(error["message"]) <= 256):
            _fail()
    elif type(message["result"]) is not dict:
        _fail()
    elif method == "peer.hello":
        _hello_result(message["result"])
    elif method is not None:
        if type(method) is not str or method not in METHODS:
            _fail("unsupported", "Peer method is not supported")
        from suan.desktop_bridge.schema import validate_outgoing
        if validate_outgoing({"id": 1, "result": message["result"]}, method):
            _fail("invalid_params", "Result does not match the peer method contract")
        # Local snapshot schemas permit future metadata keys. The network DTO is
        # deliberately closed; do not accidentally send a local session object.
        result = message["result"]
        if method == "project.catalog":
            _fields(result["project"], ("id", "name", "revision"))
            tables = result["tables"]
        elif method == "project.table.read":
            table = result["table"]
            _fields(table, ("id", "name", "fields", "records"))
            for record in table["records"]:
                _fields(record, ("id", "values"), ("definitions", "evaluations"))
            tables = [table]
        else:
            tables = []
        for table in tables:
            for field in table["fields"]:
                _fields(field, ("id", "name", "type", "unit"), ("options",))


def validate_request(message):
    """Return a detached validated request; the result still requires authentication and a grant."""
    detached = _decode(_encode(message))
    _request(detached)
    return detached


def validate_response(message, *, method=None):
    """Validate an envelope; pass the original method to also validate its result contract."""
    detached = _decode(_encode(message))
    _response(detached, method)
    return detached


def decode_message(raw, *, method=None):
    """Decode one length-bounded JSON document, independent of transport framing.

    For replies, ``method`` is the retained original request's method. It is not
    accepted from the received result body. Transport code supplies that context.
    """
    message = _decode(raw)
    if type(message) is dict and "method" in message:
        _request(message)
    else:
        _response(message, method)
    return message


def encode_message(message, *, method=None):
    """Encode a validated control message without adding stream delimiters."""
    detached = _decode(_encode(message))
    if type(detached) is dict and "method" in detached:
        _request(detached)
    else:
        _response(detached, method)
    return _encode(detached)


def negotiate_hello(params, *, capabilities=None):
    """Pure protocol/capability intersection for an already authenticated channel.

    ``capabilities`` comes from the endpoint's actual, currently authorized method
    registry; default is hello only. It is never copied from an asserted owner or
    caller in a request. Negotiation neither grants access nor resumes work.
    """
    params = _decode(_encode(params))
    _hello_params(params)
    if PROTOCOL_VERSION not in params["protocols"]:
        _fail("unsupported", "No common peer protocol version")
    available = {"peer.hello": 1} if capabilities is None else _decode(_encode(capabilities))
    _capabilities(available)
    if not available.keys() <= METHODS or any(version != 1 for version in available.values()):
        _fail("unsupported", "Endpoint capability is not implemented by this peer protocol")
    selected = {name: version for name, version in sorted(params["capabilities"].items())
                if available.get(name) == version}
    result = {"protocol": PROTOCOL_VERSION, "capabilities": selected,
              "unavailable": sorted(set(params["capabilities"]) - selected.keys()),
              "limits": {"message_bytes": MAX_MESSAGE_BYTES, "json_depth": MAX_JSON_DEPTH,
                         "commands": MAX_COMMANDS, "request_bytes": MAX_REQUEST_BYTES,
                         "receipt_bytes": MAX_RECEIPT_BYTES}}
    _hello_result(result)
    return result


__all__ = ["FORMAT", "PROTOCOL_VERSION", "SUPPORTED_PROTOCOLS", "MAX_MESSAGE_BYTES", "MAX_JSON_DEPTH",
           "MAX_COMMANDS", "MAX_REQUEST_BYTES", "MAX_RECEIPT_BYTES", "METHODS", "ERROR_CODES",
           "PeerProtocolError", "decode_message", "encode_message", "validate_request", "validate_response",
           "negotiate_hello"]
