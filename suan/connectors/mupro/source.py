"""MuPRO HDF5 through a FileSource, with the read bound to the planned content.

The complete source is streamed to a private temporary file (at most 1 GiB),
verified against the planned SHA, then the selected field is read as a
hyperslab. This works with local and remote FileSources and does not trust
metadata-only hash memoization. Temporary bytes are removed on every exit.
Only the reader's selected arrays use the separate allocation budget.
"""
import hashlib
import re
from contextlib import contextmanager
from tempfile import TemporaryFile

from ..api import ConnectorError
from ..files import check_path

FILE_LIMIT = 1024 * 1024 * 1024
_BLOCK = 1024 * 1024


class ContentChanged(ConnectorError):
    """A planned SHA mismatch must not be downgraded to an optional-format diagnostic."""

    def __init__(self):
        super().__init__("The MuPRO HDF5 source changed after its content was planned", "invalid_data")


def _stream(source, path, *, destination=None, check=None):
    """Hash the actual stream, optionally retaining the exact same bytes for parsing."""
    digest, size = hashlib.sha256(), 0
    with source.open(check_path(path)) as stream:
        while True:
            if check is not None:
                check()
            chunk = stream.read(min(_BLOCK, FILE_LIMIT - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > FILE_LIMIT:
                raise ConnectorError("MuPRO HDF5 source exceeds the 1 GiB file limit", "budget_exceeded")
            digest.update(chunk)
            if destination is not None:
                destination.write(chunk)
    return digest.hexdigest(), size


def fingerprint(source, path, selector, *, check=None):
    """Observe actual file bytes and an explicit native selector; never infer a latest frame."""
    from .hdf5 import _parse_selector
    _parse_selector(selector)
    return {**file_fingerprint(source, path, check=check), "selector": selector}


def file_fingerprint(source, path, *, check=None):
    """Whole-container content identity, also used to plan metadata discovery."""
    from .hdf5 import READER
    path = check_path(path)
    sha, size = _stream(source, path, check=check)
    return {"path": path, "sha256": sha, "size": size, "reader": READER}


@contextmanager
def _verified(source, path, expected_sha256, check):
    if expected_sha256 is not None and (not isinstance(expected_sha256, str) or
            re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None):
        raise ConnectorError("A planned content SHA-256 is required", "invalid_param")
    with TemporaryFile(mode="w+b", prefix="stk-mupro-hdf5-") as target:
        sha, size = _stream(source, path, destination=target, check=check)
        if expected_sha256 is not None and sha != expected_sha256:
            raise ContentChanged()
        if check is not None:
            check()
        target.flush()
        target.seek(0)
        yield target, sha, size
        if check is not None:
            check()


def describe(source, path, *, expected_sha256=None, max_entries=4096, check=None):
    """Enumerate native field metadata from one verified copy, without reading values."""
    from .discovery import _discover_hdf5_stream
    from .hdf5 import READER
    if type(max_entries) is not int or max_entries < 1:
        raise ConnectorError("max_entries must be a positive integer", "invalid_param")
    path = check_path(path)
    with _verified(source, path, expected_sha256, check) as (stream, sha, size):
        fields = _discover_hdf5_stream(stream, max_entries=max_entries, check=check)
    return {"path": path, "sha256": sha, "size": size, "reader": READER, "fields": fields}


def read(source, path, selector, *, expected_sha256, region=None, stride=None,
         max_bytes=256 * 1024 * 1024, check=None):
    """Read only bytes matching the fingerprint that planned the caller's execution."""
    from .hdf5 import READER, _parse_selector, _read_hdf5_stream
    from suan.data.model import FrameRef, Provenance, SourceRef
    _parse_selector(selector)
    path = check_path(path)
    if expected_sha256 is None:
        raise ConnectorError("A planned content SHA-256 is required", "invalid_param")
    # POSIX unlinks this file immediately; Windows opens it with delete-on-close.
    # Closing descriptors on worker death also releases the private source copy.
    with _verified(source, path, expected_sha256, check) as (target, sha, size):
        image = _read_hdf5_stream(target, selector, region=region, stride=stride, max_bytes=max_bytes)
    image.provenance = Provenance(activity={"kind": "import", "id": None},
                                  agent={"reader": READER},
                                  used=[{"path": path, "sha256": sha, "role": "input"}])
    image.frames = [FrameRef(step=image.time.step,
                            sources={image.id: SourceRef(path, reader=READER, selector=selector,
                                                         sha256=sha, size=size)})]
    return image
