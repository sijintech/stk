"""NDJSON framing, message envelopes and stable error codes (docs/specs/stk-desktop-bridge-v1.md).

Standard library only. One message is one line: UTF-8 JSON (strict: no NaN/Infinity, no duplicate
keys) terminated by ``\\n``. Envelopes::

    request   {"id": <int|string>, "method": "<name>", "params": {...}}
    response  {"id": <same>, "result": {...}}  |  {"id": <same or null>, "error": {"code", "message", ...}}
    event     {"event": "<name>", "data": {...}}   (bridge -> app only)
"""
import json
import re

__all__ = [
    "ERROR_CODES", "MAX_LINE_BYTES", "PROTOCOL_VERSION", "BridgeError", "LineReader", "check_envelope",
    "decode_line", "encode_message", "error_object", "leading_id",
]

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 16 * 1024 * 1024
MAX_ID_LENGTH = 128
METHOD_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
# A request line that starts with its id member: {"id": 7, ...} or {"id": "a-1", ...}.
LEADING_ID_RE = re.compile(rb'^[ \t]*\{[ \t]*"id"[ \t]*:[ \t]*(0|[1-9][0-9]{0,15}|"[^"\\\x00-\x1f]{1,512}")[ \t]*[,}]')

# Stable error codes (spec §4). "retryable" is the default for each code.
ERROR_CODES = {
    "parse_error": False,          # the line is not UTF-8 JSON
    "line_too_long": False,        # the line exceeds MAX_LINE_BYTES
    "invalid_request": False,      # the envelope is malformed
    "unknown_method": False,
    "invalid_params": False,       # params fail the schema or a semantic check
    "unsupported": False,          # the connection or protocol version cannot do this
    "not_found": False,            # unknown connection, workspace, task, transfer, subscription, blob
    "unauthorized": False,         # the Runtime or hub rejected the stored credential
    "unavailable": True,           # the Runtime or hub cannot be reached; retry the same request
    "conflict": False,             # an idempotency key or id reused with different content, offsets
    "review_not_inspected": False,  # approving a hub action whose full request was not read first
    "remote_error": False,         # the Runtime, hub or node refused the operation
    "checksum_mismatch": True,     # a transfer's bytes do not hash to the declared sha256
    "graph_error": False,          # graph validation or evaluation failed (data.graph_code)
    "cancelled": False,
    "timeout": True,
    "busy": True,                  # too many requests in flight
    "result_too_large": False,
    "shutting_down": False,
    "internal_error": False,
}


class BridgeError(Exception):
    """An error with a stable ``code`` that becomes a response's ``error`` object."""

    def __init__(self, code, message, *, data=None, retryable=None):
        if code not in ERROR_CODES:
            raise ValueError(f"Unknown bridge error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = str(message)[:4000]
        self.data = data
        self.retryable = ERROR_CODES[code] if retryable is None else bool(retryable)

    def to_json(self):
        return error_object(self.code, self.message, data=self.data, retryable=self.retryable)


def error_object(code, message, *, data=None, retryable=None):
    error = {"code": code, "message": str(message)[:4000],
             "retryable": ERROR_CODES.get(code, False) if retryable is None else bool(retryable)}
    if data is not None:
        error["data"] = data
    return error


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _no_constants(name):
    raise ValueError(f"{name} is not JSON")


def decode_line(raw):
    """Parse one line (bytes, without or with the trailing newline) into a JSON value.

    Raises :class:`BridgeError` ``parse_error`` for invalid UTF-8, invalid or non-strict JSON.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BridgeError("parse_error", f"The line is not valid UTF-8 (byte {exc.start})") from None
    text = text.rstrip("\r\n")
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    except (ValueError, RecursionError) as exc:
        raise BridgeError("parse_error", f"The line is not strict JSON: {exc}"[:500]) from None


def leading_id(raw):
    """The request id of a line that cannot be decoded, when the line starts with its ``"id"`` member.

    Lets the error response of an undecodable line (``parse_error``, ``line_too_long``) name the
    request (spec §3): clients that write ``id`` first get every error attributed. ``None`` when the
    line does not start that way or the id is not a valid request id.
    """
    match = LEADING_ID_RE.match(bytes(raw[:1024]))
    if not match:
        return None
    token = match.group(1)
    if token.startswith(b'"'):
        try:
            identity = token[1:-1].decode("utf-8")
        except UnicodeDecodeError:
            return None
        return identity if 1 <= len(identity) <= MAX_ID_LENGTH else None
    identity = int(token)
    return identity if identity <= 2**53 - 1 else None


def encode_message(message):
    """One NDJSON line (bytes, ending in ``\\n``); ``allow_nan=False`` keeps it strict JSON."""
    text = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return text.encode("utf-8") + b"\n"


class LineReader:
    """Bounded line reader over a binary stream.

    ``next()`` returns ``(line_bytes, None)`` for a complete line, ``(None, BridgeError)`` for a
    line longer than ``max_bytes`` (the rest of that line is discarded; the error's ``request_id``
    is the line's :func:`leading_id`), and ``(None, None)`` at EOF. A final line without a newline
    is still delivered.
    """

    def __init__(self, stream, max_bytes=MAX_LINE_BYTES):
        self.stream = stream
        self.max_bytes = max_bytes

    def next(self):
        line = self.stream.readline(self.max_bytes + 1)
        if not line:
            return None, None
        if len(line) > self.max_bytes and not line.endswith(b"\n"):
            # Discard the remainder of the oversized line in bounded reads.
            while True:
                rest = self.stream.readline(self.max_bytes)
                if not rest or rest.endswith(b"\n"):
                    break
            error = BridgeError("line_too_long", f"A message line must be at most {self.max_bytes} bytes")
            error.request_id = leading_id(line)
            return None, error
        return line, None


def check_envelope(message):
    """Validate a request envelope; returns ``(id, method, params)`` or raises ``invalid_request``.

    The id is recovered whenever possible so the error response can name it.
    """
    if not isinstance(message, dict):
        raise BridgeError("invalid_request", "A request must be a JSON object")
    identity = message.get("id")
    valid_id = ((isinstance(identity, int) and not isinstance(identity, bool) and 0 <= identity <= 2**53 - 1)
                or (isinstance(identity, str) and 1 <= len(identity) <= MAX_ID_LENGTH))
    if not valid_id:
        raise BridgeError("invalid_request", "A request needs an 'id': an integer 0..2^53-1 or a string of "
                          f"1..{MAX_ID_LENGTH} characters")
    extra = set(message) - {"id", "method", "params"}
    if extra:
        raise _with_id(identity, "invalid_request", f"Unknown request key(s): {', '.join(sorted(extra))}")
    method = message.get("method")
    if not isinstance(method, str) or not METHOD_RE.match(method) or len(method) > 64:
        raise _with_id(identity, "invalid_request", "A request needs a 'method' name")
    params = message.get("params", {})
    if not isinstance(params, dict):
        raise _with_id(identity, "invalid_request", "'params' must be a JSON object")
    return identity, method, params


def _with_id(identity, code, message):
    error = BridgeError(code, message)
    error.request_id = identity
    return error
