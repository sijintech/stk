"""Owner-created private numeric capsules, not a cooperative dataset format.

This module is passive and standard-library only. Remote messages never select
these paths. Numeric matrices are frozen without executing a model or installing
an adapter; their scientific meaning is reviewed by the owner in the spec.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from uuid import UUID

from suan.materials.jobs import Lease, private_directory
from .updates import MAX_BUNDLE_BYTES, decode_arrays, encode_arrays

FORMAT = "stk.federation-local-dataset/1"
MAX_METADATA_BYTES = 256 * 1024
MAX_ROWS = 100000
MAX_PRIVATE_BYTES = 512 * 1024 * 1024


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("Invalid private federation metadata") from None


def uuid(value):
    try:
        if type(value) is str and str(UUID(value)) == value:
            return value
    except (ValueError, AttributeError):
        pass
    raise ValueError("Expected a canonical dataset or grant UUID")


def read_bytes(path, maximum=MAX_BUNDLE_BYTES):
    """Read one bounded stable ordinary file, rejecting linked components."""
    path = Path(path)
    private_directory(path.parent, create=False)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400
            or before.st_size > maximum):
        raise ValueError("Invalid private federation file")
    def stamp(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if stamp(opened) != stamp(before) or not stat.S_ISREG(opened.st_mode):
            raise ValueError("Private federation file changed")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    final = path.lstat()
    if (len(raw) != opened.st_size or len(raw) > maximum or stamp(after) != stamp(opened)
            or opened.st_ctime_ns != after.st_ctime_ns or stamp(final) != stamp(after)
            or stat.S_ISLNK(final.st_mode)):
        raise ValueError("Private federation file changed")
    return raw


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate private federation metadata key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("Nonfinite private federation metadata")
    try:
        return json.loads(read_bytes(path, MAX_METADATA_BYTES).decode("utf-8"),
                          object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, RecursionError, OverflowError):
        raise ValueError("Invalid private federation metadata") from None


def write_bytes(path, raw, *, replace=False):
    """Fsync before atomic no-overwrite publication (or explicit state CAS)."""
    path = Path(path)
    private_directory(path.parent)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not replace or not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Private federation destination already exists")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".publish-", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        private_directory(path.parent, create=False)
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path, follow_symlinks=False)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path, value, *, replace=False):
    raw = canonical(value)
    if len(raw) > MAX_METADATA_BYTES:
        raise ValueError("Private federation metadata exceeds its bound")
    write_bytes(path, raw, replace=replace)


def check_budget(root, extra=0):
    total = extra
    for folder in (Path(root) / "datasets", Path(root) / "jobs"):
        if folder.exists():
            for path in folder.rglob("*.bin"):
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("Invalid private federation storage")
                total += info.st_size
                if total > MAX_PRIVATE_BYTES:
                    raise ValueError("Private federation storage quota exceeded")
    if total > MAX_PRIVATE_BYTES:
        raise ValueError("Private federation storage quota exceeded")


def _matrix(value, columns, name):
    if type(value) not in (list, tuple) or not 1 <= len(value) <= MAX_ROWS:
        raise ValueError("Numeric capsules need one to 100000 rows")
    width = len(value[0]) if type(value[0]) in (list, tuple) else 0
    if not 1 <= width <= columns:
        raise ValueError("Numeric capsule matrix width is outside its bound")
    packed = bytearray()
    for row in value:
        if type(row) not in (list, tuple) or len(row) != width:
            raise ValueError("Numeric capsule rows must have equal lengths")
        for item in row:
            try:
                valid = type(item) in (int, float) and math.isfinite(item)
                if valid:
                    packed.extend(struct.pack("<d", item))
            except (OverflowError, struct.error):
                valid = False
            if not valid:
                raise ValueError("Numeric capsule values must be finite numbers")
        if len(packed) > MAX_BUNDLE_BYTES:
            raise ValueError("Numeric capsule exceeds its byte budget")
    return {"name": name, "dtype": "f64", "shape": [len(value), width], "data": bytes(packed)}


def _names(value, count, prefix):
    if value is None:
        value = [f"{prefix}{index}" for index in range(count)]
    if (type(value) not in (list, tuple) or len(value) != count
            or any(type(name) is not str or not name.strip() or len(name.encode("utf-8")) > 128
                   or any(ord(char) < 32 for char in name) for name in value)
            or len(set(value)) != count):
        raise ValueError("Numeric capsule column names must be bounded and distinct")
    return list(value)


def capture(target, dataset_id, x, y, *, feature_names=None, target_names=None):
    """Trusted owner API; identical retries return the original immutable capsule."""
    target = Path(target).absolute()
    private_directory(target.parent)
    # The root shared by capsules/jobs is private, and every supported writer
    # holds this same process/file lease while checking and allocating bytes.
    with Lease(target.parent.parent / "node.lock", timeout=10):
        return _capture(target, dataset_id, x, y, feature_names=feature_names, target_names=target_names)


def _capture(target, dataset_id, x, y, *, feature_names=None, target_names=None):
    dataset_id = uuid(dataset_id)
    arrays = [_matrix(x, 64, "x"), _matrix(y, 16, "y")]
    if arrays[0]["shape"][0] != arrays[1]["shape"][0]:
        raise ValueError("Numeric capsule x/y rows must match")
    raw = encode_arrays(arrays, kind="model")
    manifest = {"format": FORMAT, "dataset_id": dataset_id,
                "data_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                "num_examples": len(x),
                "feature_names": _names(feature_names, arrays[0]["shape"][1], "x"),
                "target_names": _names(target_names, arrays[1]["shape"][1], "y")}
    manifest["dataset_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
    target = Path(target)
    if target.exists() or target.is_symlink():
        existing, existing_raw = load(target)
        if existing != manifest or existing_raw != raw:
            raise ValueError("Dataset identity already contains different frozen inputs")
        return manifest
    if sum(1 for path in target.parent.iterdir() if path.is_dir()) >= 1024:
        raise ValueError("Local numeric capsule quota exceeded")
    check_budget(target.parent.parent, len(raw))
    target.mkdir(mode=0o700)
    write_bytes(target / "data.bin", raw)
    write_json(target / "manifest.json", manifest)  # readiness marker is last
    return manifest


def load(target):
    target = private_directory(target, create=False)
    manifest = read_json(target / "manifest.json")
    keys = {"format", "dataset_id", "dataset_sha256", "data_sha256", "bytes", "num_examples", "feature_names", "target_names"}
    if type(manifest) is not dict or set(manifest) != keys or manifest["format"] != FORMAT:
        raise ValueError("Invalid local numeric capsule manifest")
    uuid(manifest["dataset_id"])
    raw = read_bytes(target / "data.bin")
    bundle = decode_arrays(raw, expected_kind="model")
    arrays = bundle["arrays"]
    if (len(arrays) != 2 or [a["name"] for a in arrays] != ["x", "y"]
            or any(a["dtype"] != "f64" or len(a["shape"]) != 2 for a in arrays)
            or not 1 <= arrays[0]["shape"][0] <= MAX_ROWS
            or arrays[0]["shape"][0] != arrays[1]["shape"][0]
            or type(manifest["num_examples"]) is not int or manifest["num_examples"] != arrays[0]["shape"][0]
            or type(manifest["bytes"]) is not int or manifest["bytes"] != len(raw)
            or manifest["data_sha256"] != bundle["sha256"]
            or manifest["dataset_sha256"] != hashlib.sha256(canonical(
                {k: v for k, v in manifest.items() if k != "dataset_sha256"})).hexdigest()
            or not 1 <= arrays[0]["shape"][1] <= 64 or not 1 <= arrays[1]["shape"][1] <= 16):
        raise ValueError("Local numeric capsule bytes differ from their identity")
    _names(manifest["feature_names"], arrays[0]["shape"][1], "x")
    _names(manifest["target_names"], arrays[1]["shape"][1], "y")
    if {path.name for path in target.iterdir()} != {"manifest.json", "data.bin"}:
        raise ValueError("Unexpected local numeric capsule payload")
    return manifest, raw
