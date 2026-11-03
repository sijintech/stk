"""Portable, immutable selections from verified project file snapshots.

Content identity is independent of recipients, sessions and transfer attempts.
Preparing a manifest reads only the explicitly selected snapshot objects; it does
not grant access, start a helper, publish files or change public-data labels.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from uuid import UUID


FORMAT = "stk.peer-files-manifest/1"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_FILES = 64
MAX_FILE_BYTES = 1024 ** 3
MAX_TRANSFER_BYTES = 4 * 1024 ** 3
MAX_NAME_BYTES = 1024
MAX_PATH_COMPONENTS = 16
_FIELDS = frozenset({"format", "project_id", "source_revision", "snapshot_id", "snapshot_sha256", "files"})
_FILE_FIELDS = frozenset({"file_id", "name", "bytes", "sha256", "media_type"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MEDIA = re.compile(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+\Z")
_ENCODED_SEPARATOR = re.compile(r"%(?:2f|5c|00)", re.IGNORECASE)
_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])\Z", re.IGNORECASE)
_FORBIDDEN = frozenset('<>:"\\|?*')


class FileManifestError(ValueError):
    """A bounded public failure without source paths or rejected content."""

    def __init__(self, message="Invalid peer file manifest", *, code="invalid_params"):
        self.code, self.message = code, message
        super().__init__(message)


def _fail(message="Invalid peer file manifest", *, code="invalid_params"):
    raise FileManifestError(message, code=code) from None


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


def portable_name(value):
    """Validate without renaming; reject ambiguous Windows/POSIX path spellings."""
    if type(value) is not str or not 1 <= len(value) <= MAX_NAME_BYTES:
        _fail("File name exceeds its portable bounds")
    try:
        if len(value.encode("utf-8")) > MAX_NAME_BYTES:
            _fail("File name exceeds its portable bounds")
    except UnicodeError:
        _fail("File name is not portable Unicode")
    if (unicodedata.normalize("NFC", value) != value or not value.isprintable()
            or _ENCODED_SEPARATOR.search(value)):
        _fail("File name has an ambiguous portable spelling")
    parts = value.split("/")
    if len(parts) > MAX_PATH_COMPONENTS:
        _fail("File name exceeds its portable bounds")
    for part in parts:
        if (part in {"", ".", ".."} or part[-1:] in {" ", "."}
                or any(c in _FORBIDDEN for c in part)
                or len(part.encode("utf-8")) > 255
                or len(part.encode("utf-16-le")) > 510
                or _DEVICE.fullmatch(part.split(".", 1)[0].rstrip(" ."))):
            _fail("File name is not a portable relative path")
    # This name is reserved for the durable, no-overwrite publication receipt.
    if parts[0].casefold() == ".stk-peer-receipt.json":
        _fail("File name conflicts with transfer metadata")
    return value


def _names(files):
    prefixes, leaves = {}, set()
    for item in files:
        parts = item["name"].split("/")
        for end in range(1, len(parts) + 1):
            actual = "/".join(parts[:end])
            key = unicodedata.normalize("NFC", actual.casefold())
            old = prefixes.setdefault(key, actual)
            if old != actual:
                _fail("File names collide across supported platforms")
            if end != len(parts) and key in leaves:
                _fail("A file name is also a parent directory")
        key = unicodedata.normalize("NFC", item["name"].casefold())
        if key in leaves or any(p.startswith(key + "/") for p in prefixes):
            _fail("File names collide or have a file/directory conflict")
        leaves.add(key)


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def validate_manifest(value):
    """Return a detached closed manifest; no I/O, authority or implicit defaults."""
    if type(value) is not dict or len(value) != len(_FIELDS) or value.keys() != _FIELDS:
        _fail()
    if value["format"] != FORMAT:
        _fail()
    if type(value["source_revision"]) is not int or not 0 <= value["source_revision"] < 2 ** 63:
        _fail()
    source = value["files"]
    if type(source) is not list or not 1 <= len(source) <= MAX_FILES:
        _fail("Select between one and 64 explicit files", code="limit_exceeded")
    files, identities, total = [], set(), 0
    for item in source:
        if type(item) is not dict or len(item) != len(_FILE_FIELDS) or item.keys() != _FILE_FIELDS:
            _fail()
        identity = _uuid(item["file_id"])
        if identity in identities:
            _fail("A file identity appears more than once")
        identities.add(identity)
        size = item["bytes"]
        if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
            _fail("File exceeds the explicit transfer size limit", code="limit_exceeded")
        total += size
        if total > MAX_TRANSFER_BYTES:
            _fail("Selected files exceed the transfer size limit", code="limit_exceeded")
        media = item["media_type"]
        if type(media) is not str or not 1 <= len(media) <= 127 or not _MEDIA.fullmatch(media):
            _fail()
        files.append({"file_id": identity, "name": portable_name(item["name"]), "bytes": size,
                      "sha256": _sha(item["sha256"]), "media_type": media})
    _names(files)
    result = {"format": FORMAT, "project_id": _uuid(value["project_id"]),
              "source_revision": value["source_revision"], "snapshot_id": _uuid(value["snapshot_id"]),
              "snapshot_sha256": _sha(value["snapshot_sha256"]), "files": files}
    if len(_encoded(result)) > MAX_MANIFEST_BYTES:
        _fail("File manifest exceeds its byte limit", code="limit_exceeded")
    return result


def encode_manifest(value):
    return _encoded(validate_manifest(value))


def manifest_sha256(value):
    return hashlib.sha256(encode_manifest(value)).hexdigest()


def prepare_manifest(store, snapshot_id, record_ids, *, names=None, media_types=None):
    """Freeze a chosen order of verified snapshot files, keeping all paths local.

    Optional names are explicit portable destination names; absent names use only
    the source basename, never its private absolute path. Duplicates require the
    owner to choose unambiguous names rather than a silent rename.
    """
    _uuid(snapshot_id)
    if type(record_ids) is not list or not 1 <= len(record_ids) <= MAX_FILES:
        _fail("Select between one and 64 explicit files", code="limit_exceeded")
    ids = [_uuid(value) for value in record_ids]
    if len(set(ids)) != len(ids):
        _fail("A file identity appears more than once")
    names = {} if names is None else names
    media_types = {} if media_types is None else media_types
    for mapping in (names, media_types):
        if type(mapping) is not dict or len(mapping) > MAX_FILES or not mapping.keys() <= set(ids):
            _fail()
    snapshot = store.snapshots.get(snapshot_id)
    sources = {item["record_id"]: item for item in snapshot["manifest"]["files"]}
    if any(identity not in sources for identity in ids):
        _fail("A selected file is not in the frozen snapshot")
    manifest = validate_manifest({"format": FORMAT, "project_id": snapshot["manifest"]["project_id"],
        "source_revision": snapshot["manifest"]["source_revision"], "snapshot_id": snapshot_id,
        "snapshot_sha256": snapshot["sha256"], "files": [
            {"file_id": identity, "name": names.get(identity, sources[identity]["name"]),
             "bytes": sources[identity]["size"], "sha256": sources[identity]["sha256"],
             "media_type": media_types.get(identity, "application/octet-stream")} for identity in ids]})
    # Verify only selected objects; a valid manifest is not proof of stored bytes.
    for identity in ids:
        store.snapshots.resolve(snapshot_id, identity)
    return manifest


__all__ = ["FORMAT", "MAX_MANIFEST_BYTES", "MAX_FILES", "MAX_FILE_BYTES", "MAX_TRANSFER_BYTES",
           "FileManifestError", "portable_name", "validate_manifest", "encode_manifest",
           "manifest_sha256", "prepare_manifest"]
