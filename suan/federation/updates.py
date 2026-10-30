"""Strict, standard-library-only array and update admission before aggregation.

Array wire: ``b"STKFAR1\\n"`` + a four-byte big-endian JSON-header length +
UTF-8 header + contiguous raw buffers. Dtypes ``f32`` and ``f64`` always mean
little-endian IEEE floating point. There is no compression or executable format.

``decode_arrays`` returns a detached dict containing ``format``, ``kind``,
``arrays`` (ordered name/dtype/shape/data items), ``layout`` (the same ordered
descriptors without data), ``sha256`` (the entire wire digest), and ``bytes``
(the entire wire length). ``expected_layout`` accepts that ordered descriptor
list, or an equivalent tuple; names, dtypes, shapes and order must match exactly.

Metadata validation does not authenticate a sender or verify bytes it was not
given. Trusted transport supplies the expected identities. A caller must also
compare the decoded bundle's sha256/bytes with update_sha256/update_bytes before
using an admitted update. A delta must be explicitly requested as a delta.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from uuid import UUID


ARRAYS_FORMAT = "stk.federation-arrays/1"
UPDATE_FORMAT = "stk.federation-update/1"
MAX_HEADER_BYTES = 64 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_ARRAYS = 128
MAX_PARTICIPANTS = 20
MIN_ROUND_UPDATES = 3
MAX_ROUND = 10000
MAX_EXAMPLES = 10**9
MAX_METRICS = 32
MAGIC = b"STKFAR1\n"
_PREFIX_BYTES = len(MAGIC) + 4
_DTYPES = {"f32": (4, "<f"), "f64": (8, "<d")}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_HEADER_KEYS = frozenset(("format", "kind", "arrays", "payload_bytes", "payload_sha256"))
_ARRAY_KEYS = frozenset(("name", "dtype", "shape", "offset", "nbytes", "sha256"))
_INPUT_KEYS = frozenset(("name", "dtype", "shape", "data"))
_LAYOUT_KEYS = frozenset(("name", "dtype", "shape"))
_UPDATE_KEYS = frozenset(("format", "run_id", "round", "participant_id", "model_sha256",
    "spec_sha256", "dataset_sha256", "grant_id", "update_sha256", "update_bytes",
    "num_examples", "metrics", "masked"))


class FederationValidationError(ValueError):
    """Rejected input; error messages never include the rejected payload."""


def _fail(message):
    raise FederationValidationError(message) from None


def _fields(value, keys):
    if type(value) is not dict or value.keys() != keys:
        _fail("Object fields do not match the federation contract")


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("Integer is outside its federation bound")
    return value


def _digest(value):
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail("Digest or participant identity must be lower-case SHA-256 hex")
    return value


def _uuid(value):
    if type(value) is not str or len(value) != 36:
        _fail("Run and grant identities must be canonical UUIDs")
    try:
        valid = str(UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        _fail("Run and grant identities must be canonical UUIDs")
    return value


def _text(value, maximum, *, byte_bound=False):
    if type(value) is not str or not value or len(value) > maximum:
        _fail("Name or metric key is outside its text bound")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        _fail("Names and metric keys must be valid UTF-8")
    if (byte_bound and len(encoded) > maximum) or not value.strip() or any(
            ord(c) < 32 or ord(c) == 127 for c in value):
        _fail("Name or metric key is outside its text bound")
    return value


def _kind(value):
    if type(value) is not str or value not in ("model", "delta"):
        _fail("Array bundle kind must be model or delta")
    return value


def _descriptor(value):
    name = _text(value["name"], 128, byte_bound=True)
    dtype = value["dtype"]
    if type(dtype) is not str or dtype not in _DTYPES:
        _fail("Array dtype must be little-endian f32 or f64")
    shape = value["shape"]
    if type(shape) not in (list, tuple) or not 1 <= len(shape) <= 4:
        _fail("Array shape must have one through four dimensions")
    width = _DTYPES[dtype][0]
    product = 1
    detached = []
    for dimension in shape:
        _integer(dimension, 1, MAX_BUNDLE_BYTES // width)
        if product > (MAX_BUNDLE_BYTES // width) // dimension:
            _fail("Array shape exceeds the byte budget")
        product *= dimension
        detached.append(dimension)
    return {"name": name, "dtype": dtype, "shape": detached}, product * width


def _layout(value):
    if type(value) not in (list, tuple) or not 1 <= len(value) <= MAX_ARRAYS:
        _fail("Array count is outside its federation bound")
    result, seen = [], set()
    for descriptor in value:
        _fields(descriptor, _LAYOUT_KEYS)
        admitted, _ = _descriptor(descriptor)
        if admitted["name"] in seen:
            _fail("Array names must be unique")
        seen.add(admitted["name"])
        result.append(admitted)
    return result


def validate_layout(value):
    """Return detached ordered name/dtype/shape descriptors without tensor buffers.

    Uses the same descriptor rules as ``decode_arrays(expected_layout=...)``:
    one through 128 unique names, f32/f64 and one through four positive integer
    dimensions with bounded products. This checks layout metadata only; actual
    wire bytes, combined bundle length and values still require ``decode_arrays``.
    """
    return _layout(value)


def _finite_buffer(data, dtype):
    for (value,) in struct.iter_unpack(_DTYPES[dtype][1], data):
        if not math.isfinite(value):
            _fail("Array values must all be finite")


def _encode_header(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        _fail("Array header is not valid JSON")
    if not 1 <= len(raw) <= MAX_HEADER_BYTES:
        _fail("Array header exceeds its byte budget")
    return raw


def encode_arrays(arrays, *, kind):
    """Encode ordered name/dtype/shape/data items; data must be immutable bytes.

    Names are unique, nonblank UTF-8 strings of at most 128 bytes, without control
    characters. Shapes have one through four strictly positive integer dimensions.
    The 64 MiB limit includes framing, header and payload, not just array values.
    """
    kind = _kind(kind)
    if type(arrays) not in (list, tuple) or not 1 <= len(arrays) <= MAX_ARRAYS:
        _fail("Array count is outside its federation bound")
    descriptors, blocks, seen = [], [], set()
    total, payload_digest = 0, hashlib.sha256()
    for item in arrays:
        _fields(item, _INPUT_KEYS)
        descriptor, length = _descriptor(item)
        if descriptor["name"] in seen:
            _fail("Array names must be unique")
        seen.add(descriptor["name"])
        data = item["data"]
        if type(data) is not bytes or len(data) != length:
            _fail("Array byte length does not match its dtype and shape")
        if length > MAX_BUNDLE_BYTES - _PREFIX_BYTES - total:
            _fail("Array bundle exceeds its byte budget")
        _finite_buffer(data, descriptor["dtype"])
        descriptors.append({**descriptor, "offset": total, "nbytes": length,
                            "sha256": hashlib.sha256(data).hexdigest()})
        blocks.append(data)
        payload_digest.update(data)
        total += length
    header = _encode_header({"format": ARRAYS_FORMAT, "kind": kind, "arrays": descriptors,
                            "payload_bytes": total, "payload_sha256": payload_digest.hexdigest()})
    if _PREFIX_BYTES + len(header) + total > MAX_BUNDLE_BYTES:
        _fail("Array bundle exceeds its byte budget")
    return MAGIC + struct.pack(">I", len(header)) + header + b"".join(blocks)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail("Array header contains duplicate JSON keys")
        result[key] = value
    return result


def _constant(_value):
    _fail("Array header contains a non-finite JSON number")


def _decode_header(raw):
    # Reject excessive nesting before the JSON parser allocates its object tree.
    depth, quoted, escaped = 0, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 8:
                _fail("Array header nesting exceeds its bound")
        elif byte in (93, 125):
            depth -= 1
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("Array header must not have a UTF-8 BOM")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except FederationValidationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail("Array header is not strict UTF-8 JSON")


def decode_arrays(raw, *, expected_kind=None, expected_layout=None):
    """Validate all bytes and return a detached bundle as documented above.

    A bytes, bytearray, or contiguous one-dimensional byte memoryview is accepted;
    mutable input is copied only after checking its size. No arrays are returned
    until every descriptor, digest, offset, length and floating value is validated.
    """
    if type(raw) not in (bytes, bytearray, memoryview):
        _fail("Array bundle must be bytes")
    try:
        if type(raw) is memoryview and (raw.ndim != 1 or raw.itemsize != 1 or not raw.c_contiguous):
            _fail("Array bundle must be a contiguous byte view")
        if not _PREFIX_BYTES < len(raw) <= MAX_BUNDLE_BYTES:
            _fail("Array bundle is truncated or exceeds its byte budget")
        raw = bytes(raw)
    except FederationValidationError:
        raise
    except (ValueError, TypeError, BufferError):
        _fail("Array bundle byte view is unavailable")
    if not raw.startswith(MAGIC):
        _fail("Array bundle magic is invalid")
    header_length = struct.unpack_from(">I", raw, len(MAGIC))[0]
    if not 1 <= header_length <= MAX_HEADER_BYTES or header_length > len(raw) - _PREFIX_BYTES:
        _fail("Array header length is invalid")
    header = _decode_header(raw[_PREFIX_BYTES:_PREFIX_BYTES + header_length])
    _fields(header, _HEADER_KEYS)
    if header["format"] != ARRAYS_FORMAT:
        _fail("Array bundle format is unsupported")
    kind = _kind(header["kind"])
    if expected_kind is not None and kind != _kind(expected_kind):
        _fail("Array bundle kind does not match the expected kind")
    declared = _integer(header["payload_bytes"], 1, MAX_BUNDLE_BYTES)
    payload = memoryview(raw)[_PREFIX_BYTES + header_length:]
    if len(payload) != declared:
        _fail("Array bundle payload length or trailing bytes are invalid")
    if hashlib.sha256(payload).hexdigest() != _digest(header["payload_sha256"]):
        _fail("Array bundle payload digest does not match")
    items = header["arrays"]
    if type(items) is not list or not 1 <= len(items) <= MAX_ARRAYS:
        _fail("Array count is outside its federation bound")
    arrays, layout, seen, offset = [], [], set(), 0
    for item in items:
        _fields(item, _ARRAY_KEYS)
        descriptor, length = _descriptor(item)
        if descriptor["name"] in seen:
            _fail("Array names must be unique")
        seen.add(descriptor["name"])
        position = _integer(item["offset"], 0, MAX_BUNDLE_BYTES)
        declared_length = _integer(item["nbytes"], 1, MAX_BUNDLE_BYTES)
        if position != offset or declared_length != length or length > len(payload) - offset:
            _fail("Array offsets or lengths contain a gap, overlap or shape mismatch")
        data = payload[offset:offset + length]
        if hashlib.sha256(data).hexdigest() != _digest(item["sha256"]):
            _fail("Array digest does not match")
        _finite_buffer(data, descriptor["dtype"])
        layout.append(descriptor)
        arrays.append({**descriptor, "shape": descriptor["shape"].copy(), "data": bytes(data)})
        offset += length
    if offset != len(payload):
        _fail("Array descriptors do not cover the complete payload")
    if expected_layout is not None and layout != validate_layout(expected_layout):
        _fail("Array layout does not match the expected layout")
    return {"format": ARRAYS_FORMAT, "kind": kind, "arrays": arrays, "layout": layout,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _metrics(value):
    if type(value) is not dict or len(value) > MAX_METRICS:
        _fail("Update metrics exceed their bound")
    result = {}
    for key, number in value.items():
        _text(key, 64)
        if type(number) not in (int, float):
            _fail("Metrics must be finite numeric values")
        try:
            finite = math.isfinite(number)
        except (OverflowError, ValueError):
            finite = False
        if not finite:
            _fail("Metrics must be finite numeric values")
        result[key] = number
    return result


def validate_update(value, *, run_id, round, participant_id, model_sha256,
                    spec_sha256, dataset_sha256, grant_id):
    """Validate exact update fields and transport-supplied expected bindings.

    Returns a new metadata dict, including a new metrics dict. ``masked`` is
    exactly false: this initial contract does not claim secure aggregation.
    Actual update bytes still require ``decode_arrays`` and digest/size comparison.
    """
    expected = {"run_id": _uuid(run_id), "round": _integer(round, 1, MAX_ROUND),
        "participant_id": _digest(participant_id), "model_sha256": _digest(model_sha256),
        "spec_sha256": _digest(spec_sha256), "dataset_sha256": _digest(dataset_sha256),
        "grant_id": _uuid(grant_id)}
    _fields(value, _UPDATE_KEYS)
    if type(value["format"]) is not str or value["format"] != UPDATE_FORMAT:
        _fail("Update format is unsupported")
    actual = {"run_id": _uuid(value["run_id"]), "round": _integer(value["round"], 1, MAX_ROUND),
        "participant_id": _digest(value["participant_id"]), "model_sha256": _digest(value["model_sha256"]),
        "spec_sha256": _digest(value["spec_sha256"]), "dataset_sha256": _digest(value["dataset_sha256"]),
        "grant_id": _uuid(value["grant_id"])}
    if actual != expected:
        _fail("Update does not match its expected run, round, participant, model, specification or grant")
    _digest(value["update_sha256"])
    _integer(value["update_bytes"], 1, MAX_BUNDLE_BYTES)
    _integer(value["num_examples"], 1, MAX_EXAMPLES)
    if type(value["masked"]) is not bool or value["masked"] is not False:
        _fail("Masked updates are not supported by this contract")
    metrics = _metrics(value["metrics"])
    return {**value, "metrics": metrics}


def validate_round(updates, *, participants, run_id, round, model_sha256, spec_sha256):
    """Admit at least three distinct updates from three through twenty approved peers.

    ``participants`` is a peer-hex -> {dataset_sha256, grant_id} plain dict from
    trusted authorization. Every supplied update must pass; no partial list is
    returned on failure. This function does not grant permission or aggregate.
    """
    _uuid(run_id)
    _integer(round, 1, MAX_ROUND)
    _digest(model_sha256)
    _digest(spec_sha256)
    if type(participants) is not dict or not MIN_ROUND_UPDATES <= len(participants) <= MAX_PARTICIPANTS:
        _fail("Approved participant count must be between three and twenty")
    approved = {}
    for peer, binding in participants.items():
        _digest(peer)
        _fields(binding, frozenset(("dataset_sha256", "grant_id")))
        approved[peer] = {"dataset_sha256": _digest(binding["dataset_sha256"]),
                          "grant_id": _uuid(binding["grant_id"])}
    if type(updates) not in (list, tuple) or not MIN_ROUND_UPDATES <= len(updates) <= len(approved):
        _fail("A round needs at least three approved updates within its participant bound")
    result, seen = [], set()
    for update in updates:
        _fields(update, _UPDATE_KEYS)
        peer = _digest(update["participant_id"])
        if peer not in approved or peer in seen:
            _fail("Round contains an unknown or duplicate participant")
        seen.add(peer)
        result.append(validate_update(update, run_id=run_id, round=round,
            participant_id=peer, model_sha256=model_sha256, spec_sha256=spec_sha256,
            **approved[peer]))
    return result
