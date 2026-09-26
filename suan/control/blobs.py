"""Content-addressed blob store of the control hub (standard library only).

Blobs are immutable byte strings named by their sha256 (64 lower-case hex
digits): payload buffers, rendered images and plots uploaded by node agents,
and action results too large to keep in the action row. Files live at
``<root>/<sha[:2]>/<sha>``; uploads stream into ``<root>/.incoming`` and are
renamed into place only after the content hashed to the requested name, so a
reader never sees a partial or mismatched blob and repeated uploads are
harmless.
"""
import hashlib
import os
from pathlib import Path
import re
import uuid

__all__ = ["DEFAULT_MAX_BYTES", "SHA256_RE", "BlobError", "BlobMismatch", "BlobStore", "BlobTooLarge"]

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_MAX_BYTES = 512 * 1024 * 1024


class BlobError(ValueError):
    """An invalid blob name or upload."""


class BlobMismatch(BlobError):
    """The uploaded bytes do not hash to the requested sha256."""


class BlobTooLarge(BlobError):
    """The upload exceeds the store's size cap."""


class BlobStore:
    def __init__(self, root, max_bytes=DEFAULT_MAX_BYTES):
        self.root = Path(root)
        self.max_bytes = int(max_bytes)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.incoming = self.root / ".incoming"
        self.incoming.mkdir(exist_ok=True, mode=0o700)

    @staticmethod
    def check(digest):
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise BlobError("A blob is named by its sha256: 64 lower-case hexadecimal characters")
        return digest

    def path(self, digest):
        digest = self.check(digest)
        return self.root / digest[:2] / digest

    def size(self, digest):
        """Size in bytes, or ``None`` when the blob is absent."""
        try:
            return self.path(digest).stat().st_size
        except FileNotFoundError:
            return None

    def exists(self, digest):
        return self.size(digest) is not None

    def read(self, digest):
        return self.path(digest).read_bytes()

    def put(self, data):
        """Store bytes held by the hub itself (idempotent; the upload cap does not apply); returns their sha256."""
        data = bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        if not self.exists(digest):
            upload = Upload(self, digest, None)
            try:
                upload.write(data)
                upload.commit()
            finally:
                upload.abort()
        return digest

    def adopt(self, source, digest):
        """Move a finished file (on the store's file system) into place after it hashed to ``digest``.

        Returns ``True`` when this call created the blob; raises :class:`BlobMismatch` (the file is
        left where it is) when the bytes do not match.
        """
        self.check(digest)
        result = hashlib.sha256()
        with open(source, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                result.update(block)
        if result.hexdigest() != digest:
            raise BlobMismatch("Uploaded bytes do not match the blob's sha256")
        target = self.path(digest)
        created = not target.exists()
        target.parent.mkdir(exist_ok=True, mode=0o700)
        os.replace(source, target)
        return created

    def begin(self, digest, expected_size=None):
        """An :class:`Upload` (capped at ``max_bytes``) that streams into a private temporary file."""
        self.check(digest)
        if expected_size is not None and expected_size > self.max_bytes:
            raise BlobTooLarge(f"Blob of {expected_size} bytes exceeds the {self.max_bytes}-byte limit")
        return Upload(self, digest, self.max_bytes)


class Upload:
    """One streamed upload: ``write`` chunks, then ``commit`` (verify and rename) or ``abort``."""

    def __init__(self, store, digest, max_bytes):
        self.store, self.digest, self.max_bytes = store, digest, max_bytes
        self.size = 0
        self._hash = hashlib.sha256()
        self._tmp = store.incoming / f"{digest}.{uuid.uuid4().hex}.part"
        descriptor = os.open(self._tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._stream = os.fdopen(descriptor, "wb")

    def write(self, chunk):
        self.size += len(chunk)
        if self.max_bytes is not None and self.size > self.max_bytes:
            raise BlobTooLarge(f"Blob exceeds the {self.max_bytes}-byte limit")
        self._hash.update(chunk)
        self._stream.write(chunk)

    def commit(self):
        """Verify the sha256 and move the file into place; returns ``True`` when this call created it."""
        if self._hash.hexdigest() != self.digest:
            raise BlobMismatch("Uploaded bytes do not match the blob's sha256")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        target = self.store.path(self.digest)
        created = not target.exists()
        target.parent.mkdir(exist_ok=True, mode=0o700)
        os.replace(self._tmp, target)  # same content either way; atomic for concurrent uploads
        return created

    def abort(self):
        """Discard the temporary file (safe after ``commit``)."""
        if not self._stream.closed:
            self._stream.close()
        self._tmp.unlink(missing_ok=True)
