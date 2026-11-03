"""Pure optional peer-file DTOs and DATA/RECEIPT frames; no storage or authority.

The adapter supplies current session/file leases and retained original intents.
Encoding a receipt does not perform or prove an fsync or a journal commit.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import struct
from uuid import UUID


FILE_METHODS = frozenset({"files.offer", "files.status", "files.start", "files.cancel",
                          "files.complete", "files.resume"})
FILE_MUTATIONS = FILE_METHODS - {"files.status"}
FILE_STATES = frozenset({"offered", "accepted", "receiving", "interrupted", "complete", "cancelled", "failed"})
CHUNK_BYTES = 60 * 1024
MAX_FRAME_BYTES = 64 * 1024
MAX_FILE_BYTES = 1024 ** 3
MAX_TRANSFER_BYTES = 4 * 1024 ** 3
MAX_FILES = 64
DATA, RECEIPT = 1, 2
HEADER = struct.Struct("!4sBBH16s16sQQI32s")
HEADER_BYTES = HEADER.size
_MAX_U64 = 2 ** 64 - 1
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TARGET = {"session_id", "transfer_id", "manifest_sha256"}


class FileProtocolError(ValueError):
    """Fixed public failure; never includes rejected values or local paths."""
    def __init__(self, code="invalid_params", message="Invalid peer file message"):
        self.code, self.message = code, message
        super().__init__(message)


def _fail(code="invalid_params", message="Invalid peer file message"):
    raise FileProtocolError(code, message) from None


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        _fail()


def _uuid(value):
    if type(value) is not str or len(value) != 36:
        _fail()
    try:
        if str(UUID(value)) != value:
            _fail()
    except ValueError:
        _fail()
    return value


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail()
    return value


def _integer(value, low=0, high=_MAX_U64):
    if type(value) is not int or not low <= value <= high:
        _fail()
    return value


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


def _copy(value):
    return json.loads(_canonical(value))


def _manifest(value):
    # Kept lazy so the binary codec remains independent of the manifest/storage adapter.
    from .manifests import FileManifestError, validate_manifest
    try:
        return validate_manifest(value)
    except FileManifestError:
        _fail()


def _manifest_digest(value):
    from .manifests import manifest_sha256
    return manifest_sha256(value)


def _session_offer(value):
    from .pairing import PairingError, validate_offer
    try:
        return validate_offer(value)
    except PairingError:
        _fail()


def validate_file_params(method, params):
    """Closed syntax only. A UUID, session or advertised method grants no access."""
    if type(method) is not str or method not in FILE_METHODS:
        _fail("unsupported", "Peer file method is not supported")
    names = _TARGET | {"operation_id"}
    if method == "files.offer":
        names |= {"manifest", "session_offer"}
    elif method != "files.status":
        names |= {"grant_id"}
    _fields(params, names)
    _uuid(params["session_id"]), _uuid(params["transfer_id"]), _sha(params["manifest_sha256"])
    if method != "files.status" or params["operation_id"] is not None:
        _uuid(params["operation_id"])
    if "grant_id" in params:
        if method != "files.cancel" or params["grant_id"] is not None:
            _uuid(params["grant_id"])
    if method == "files.offer":
        manifest = _manifest(params["manifest"])
        offer = _session_offer(params["session_offer"])
        if (_manifest_digest(manifest) != params["manifest_sha256"]
                or offer["session_id"] != params["session_id"]):
            _fail()
    return _copy(params)


def request_sha256(method, params):
    """Hash the complete original mutation params, excluding transport UUID/method."""
    if type(method) is not str or method not in FILE_MUTATIONS:
        _fail()
    return hashlib.sha256(_canonical(validate_file_params(method, params))).hexdigest()


def validate_operation_receipt(value, *, method=None, params=None):
    _fields(value, {"operation_id", "method", "request_sha256", "state"})
    _uuid(value["operation_id"]), _sha(value["request_sha256"])
    if (type(value["method"]) is not str or value["method"] not in FILE_MUTATIONS
            or type(value["state"]) is not str or value["state"] not in {"completed", "uncertain"}):
        _fail()
    if method is not None and value["method"] != method:
        _fail()
    if params is not None:
        params = validate_file_params(method, params)
        if (method not in FILE_MUTATIONS or value["method"] != method
                or value["operation_id"] != params.get("operation_id")
                or value["request_sha256"] != request_sha256(method, params)):
            _fail()
    return _copy(value)


def validate_file_result(method, result, *, params=None, manifest=None):
    """Validate shape; with retained params/manifest also validate original binding.

    A completed transfer with retained params requires the retained manifest.
    A status operation receipt is checked against the original mutation separately
    with validate_operation_receipt; the status request itself is not that intent.
    """
    if type(method) is not str or method not in FILE_METHODS:
        _fail("unsupported", "Peer file method is not supported")
    _fields(result, _TARGET | {"state", "grant_id", "files", "operation", "completion"})
    _uuid(result["session_id"]), _uuid(result["transfer_id"]), _sha(result["manifest_sha256"])
    if type(result["state"]) is not str or result["state"] not in FILE_STATES:
        _fail()
    if result["grant_id"] is not None:
        _uuid(result["grant_id"])
    files = result["files"]
    if type(files) is not list or not 1 <= len(files) <= MAX_FILES:
        _fail()
    seen, total = set(), 0
    for item in files:
        _fields(item, {"file_id", "bytes", "committed_bytes", "next_sequence", "verified_sha256"})
        file_id = _uuid(item["file_id"])
        size = _integer(item["bytes"], high=MAX_FILE_BYTES)
        committed = _integer(item["committed_bytes"], high=size)
        _integer(item["next_sequence"])
        total += size
        if (file_id in seen or total > MAX_TRANSFER_BYTES
                or committed != size and committed % CHUNK_BYTES
                or item["next_sequence"] != (committed + CHUNK_BYTES - 1) // CHUNK_BYTES):
            _fail()
        seen.add(file_id)
        verified = item["verified_sha256"]
        if verified is not None:
            _sha(verified)
            if committed != size or result["state"] != "complete":
                _fail()
        if result["state"] in {"offered", "accepted"} and committed:
            _fail()
    operation = result["operation"]
    if operation is not None:
        validate_operation_receipt(operation)
    if method in FILE_MUTATIONS:
        if operation is None or operation["method"] != method or operation["state"] != "completed":
            _fail()
    completion = result["completion"]
    if completion is not None:
        _fields(completion, {"format", "transfer_id", "manifest_sha256", "files"})
        if (completion["format"] != "stk.peer-files-receipt/1"
                or completion["transfer_id"] != result["transfer_id"]
                or completion["manifest_sha256"] != result["manifest_sha256"]
                or type(completion["files"]) is not list or len(completion["files"]) != len(files)
                or result["state"] != "complete"):
            _fail()
        for received, item in zip(completion["files"], files):
            _fields(received, {"file_id", "bytes", "sha256"})
            _uuid(received["file_id"]), _integer(received["bytes"], high=MAX_FILE_BYTES), _sha(received["sha256"])
            if (received["file_id"] != item["file_id"] or received["bytes"] != item["bytes"]
                    or received["sha256"] != item["verified_sha256"]
                    or item["committed_bytes"] != item["bytes"]):
                _fail()
    if (result["state"] == "complete") != (completion is not None):
        _fail()
    if method == "files.complete" and completion is None:
        _fail()
    if params is not None:
        params = validate_file_params(method, params)
        if any(result[key] != params[key] for key in _TARGET):
            _fail()
        if "grant_id" in params and result["grant_id"] != params["grant_id"]:
            _fail()
        if method in FILE_MUTATIONS:
            validate_operation_receipt(operation, method=method, params=params)
        elif params["operation_id"] is None:
            if operation is not None:
                _fail()
        elif operation is not None and operation["operation_id"] != params["operation_id"]:
            _fail()
        if method == "files.offer":
            manifest = params["manifest"]
        if completion is not None and manifest is None:
            _fail()
    if manifest is not None:
        expected = _manifest(manifest)
        if _manifest_digest(expected) != result["manifest_sha256"] or len(expected["files"]) != len(files):
            _fail()
        for original, item in zip(expected["files"], files):
            if (item["file_id"] != original["file_id"] or item["bytes"] != original["bytes"]
                    or item["verified_sha256"] is not None and item["verified_sha256"] != original["sha256"]):
                _fail()
    return _copy(result)


@dataclass(frozen=True)
class FileFrame:
    kind: int
    transfer_id: str
    file_id: str
    sequence: int
    offset: int
    length: int
    sha256: str
    body: bytes = b""


def _check_frame(frame):
    if type(frame) is not FileFrame or type(frame.kind) is not int or frame.kind not in {DATA, RECEIPT}:
        _fail()
    _uuid(frame.transfer_id), _uuid(frame.file_id), _sha(frame.sha256)
    _integer(frame.sequence), _integer(frame.offset), _integer(frame.length, 1, CHUNK_BYTES)
    if type(frame.body) is not bytes or frame.offset > _MAX_U64 - frame.length:
        _fail()
    if frame.kind == DATA:
        if len(frame.body) != frame.length or hashlib.sha256(frame.body).hexdigest() != frame.sha256:
            _fail()
    elif frame.body:
        _fail()


def encode_frame(frame):
    _check_frame(frame)
    return HEADER.pack(b"STKF", 1, frame.kind, 0, UUID(frame.transfer_id).bytes,
                       UUID(frame.file_id).bytes, frame.sequence, frame.offset,
                       frame.length, bytes.fromhex(frame.sha256)) + frame.body


def encode_data(transfer_id, file_id, sequence, offset, body):
    if type(body) is not bytes or not 1 <= len(body) <= CHUNK_BYTES:
        _fail()
    return encode_frame(FileFrame(DATA, transfer_id, file_id, sequence, offset, len(body),
                                  hashlib.sha256(body).hexdigest(), body))


def decode_frame(raw):
    if type(raw) is not bytes or not HEADER_BYTES <= len(raw) <= MAX_FRAME_BYTES:
        _fail()
    magic, version, kind, reserved, transfer, file, sequence, offset, length, digest = HEADER.unpack(raw[:HEADER_BYTES])
    if magic != b"STKF" or version != 1 or reserved != 0 or kind not in {DATA, RECEIPT}:
        _fail()
    frame = FileFrame(kind, str(UUID(bytes=transfer)), str(UUID(bytes=file)), sequence,
                      offset, length, digest.hex(), raw[HEADER_BYTES:])
    _check_frame(frame)
    return frame


def encode_receipt(data):
    _check_frame(data)
    if data.kind != DATA:
        _fail()
    return encode_frame(FileFrame(RECEIPT, data.transfer_id, data.file_id, data.sequence,
                                  data.offset, data.length, data.sha256))


def validate_receipt(receipt, data):
    _check_frame(receipt), _check_frame(data)
    if (receipt.kind != RECEIPT or data.kind != DATA
            or (receipt.transfer_id, receipt.file_id, receipt.sequence, receipt.offset, receipt.length, receipt.sha256)
            != (data.transfer_id, data.file_id, data.sequence, data.offset, data.length, data.sha256)):
        _fail()
    return receipt
