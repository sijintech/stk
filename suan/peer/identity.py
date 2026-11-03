"""Explicit persistent device identity and a restricted local Ed25519 signer.

The dedicated private SQLite asset stores binary key material, never JSON keys.
POSIX uses owner-only files; Windows protects the seed with user DPAPI (without
machine-wide or interactive flags). This is not a vault or uncloneable identity.
Public reads do not select secret columns, create state, or import cryptography.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from uuid import UUID, uuid4

from .authority import PeerDenied, auth_message, peer_id_for


DEVICE_FORMAT = "stk.peer-device/1"
_APP_ID = 0x53545049
_MAX_OPERATIONS = 4096
_MAX_METADATA = 16384
_PUBLIC_COLUMNS = "owner_id,display_name,peer_id,public_key,generation,active"


class IdentityError(RuntimeError):
    """A fixed local diagnostic which never includes key material or paths."""


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise IdentityError("A canonical operation or owner UUID is required") from None
    return value


def _json(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                             separators=(",", ":"))
        if len(encoded.encode("utf-8")) > _MAX_METADATA:
            raise ValueError
        return encoded
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise IdentityError("Device identity metadata is invalid") from None


def _name(value):
    if (type(value) is not str or not value.strip() or len(value) > 128
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise IdentityError("Device display name is invalid")
    _json(value)
    return value


def validate_card(value):
    """Detached closed public card; an address, display name or Hub is not a pin."""
    if type(value) is not dict or set(value) != {"format", "owner_id", "peer_id", "public_key", "display_name"}:
        raise IdentityError("Device public card is invalid")
    if value["format"] != DEVICE_FORMAT:
        raise IdentityError("Device public card is invalid")
    _uuid(value["owner_id"])
    _name(value["display_name"])
    public = value["public_key"]
    if type(public) is not str or len(public) != 64 or any(c not in "0123456789abcdef" for c in public):
        raise IdentityError("Device public card is invalid")
    if value["peer_id"] != peer_id_for(bytes.fromhex(public)):
        raise IdentityError("Device public fingerprint does not match")
    return json.loads(_json(value))


def _ordinary(path, *, private=False):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise IdentityError("Device identity requires ordinary local files")
    if private and os.name != "nt" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise IdentityError("Device identity file must be owner-only")
    return info.st_dev, info.st_ino


def _directory(path, *, create=False):
    if ".." in path.parts:
        raise IdentityError("Device identity directory is invalid")
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if not create:
                raise
            try:
                part.mkdir(mode=0o700)
            except FileExistsError:
                pass
            info = part.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise IdentityError("Device identity directory must not contain links")
    if os.name != "nt" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise IdentityError("Device identity directory must be owner-only")


def _dpapi(data, *, decrypt=False):
    """User DPAPI, UI forbidden, no LOCAL_MACHINE and no plaintext fallback.

    https://learn.microsoft.com/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
    https://learn.microsoft.com/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata
    """
    if os.name != "nt":
        raise IdentityError("Windows device protection is unavailable")
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    source_buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        call = crypt.CryptUnprotectData
        call.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        call = crypt.CryptProtectData
        call.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    call.restype = wintypes.BOOL
    try:
        if not call(*args) or not 0 < target.size <= 16384:
            raise IdentityError("Windows device protection failed")
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.memset(source_buffer, 0, len(source_buffer))
        if target.data:
            ctypes.memset(target.data, 0, target.size)
            kernel.LocalFree(target.data)


class LocalDeviceIdentity:
    """Explicit local lifecycle; operation replays return history, never reactivate keys."""

    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        self.path = self.directory / "identity.sqlite3"
        self._identity = None

    def __repr__(self):
        return "<LocalDeviceIdentity>"

    @contextmanager
    def _connect(self, *, write=False):
        db = None
        handling_body = False
        try:
            if write and self._identity is not None:
                try:
                    _directory(self.directory)
                    if _ordinary(self.path, private=True) != self._identity:
                        raise IdentityError("Device identity state was replaced")
                except FileNotFoundError:
                    raise IdentityError("Device identity state was lost") from None
            try:
                _directory(self.directory, create=write)
            except FileNotFoundError:
                if self._identity is not None:
                    raise IdentityError("Device identity state was lost") from None
                yield None
                return
            created = False
            if write:
                try:
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(fd)
                    created = True
                except FileExistsError:
                    pass
            try:
                identity = _ordinary(self.path, private=True)
            except FileNotFoundError:
                if write or self._identity is not None:
                    raise IdentityError("Device identity state was lost") from None
                yield None
                return
            if self._identity is not None and self._identity != identity:
                raise IdentityError("Device identity state was replaced")
            db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                 uri=True, isolation_level=None, timeout=10)
            db.row_factory = sqlite3.Row
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("BEGIN")
            if created:
                db.execute("CREATE TABLE device (slot INTEGER PRIMARY KEY CHECK(slot=1), owner_id TEXT NOT NULL, "
                           "display_name TEXT NOT NULL, peer_id TEXT NOT NULL, public_key BLOB NOT NULL, "
                           "generation INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)), "
                           "secret BLOB NOT NULL, provider TEXT NOT NULL)")
                db.execute("CREATE TABLE operations (id TEXT PRIMARY KEY, request TEXT NOT NULL, receipt TEXT NOT NULL)")
                db.execute(f"PRAGMA application_id={_APP_ID}")
                db.execute("PRAGMA user_version=1")
                # Empty schema metadata is not a device identity. Persist it
                # separately so a missing optional dependency cannot strand a
                # zero-byte foreign file or force any implicit key repair.
                db.commit()
                db.execute("BEGIN IMMEDIATE")
            if (db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID
                    or db.execute("PRAGMA user_version").fetchone()[0] != 1
                    or _ordinary(self.path, private=True) != identity):
                raise IdentityError("Device identity state is invalid")
            self._identity = identity
            handling_body = True
            yield db
            handling_body = False
            if _ordinary(self.path, private=True) != identity:
                raise IdentityError("Device identity state changed")
            db.commit()
        except (sqlite3.Error, OSError):
            if handling_body:
                raise
            raise IdentityError("Device identity storage is unavailable") from None
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _info(row):
        if row is None:
            return None
        try:
            card = validate_card({"format": DEVICE_FORMAT, "owner_id": row["owner_id"],
                                  "peer_id": row["peer_id"], "public_key": bytes(row["public_key"]).hex(),
                                  "display_name": row["display_name"]})
            if type(row["generation"]) is not int or row["generation"] < 1 or row["active"] not in (0, 1):
                raise ValueError
            return {"card": card, "generation": row["generation"], "active": bool(row["active"])}
        except (ValueError, TypeError, KeyError):
            raise IdentityError("Device identity public metadata is invalid") from None

    def info(self):
        with self._connect() as db:
            return None if db is None else self._info(db.execute(f"SELECT {_PUBLIC_COLUMNS} FROM device WHERE slot=1").fetchone())

    @contextmanager
    def current_identity(self):
        """Hold a public read lease while one already accepted local action finishes.

        Only the public projection is selected. Rotate/revoke must wait for this
        read transaction before committing their generation change. Callers must
        bound their work and never wait for network input while holding the lease.
        """
        with self._connect() as db:
            current = None if db is None else self._info(db.execute(
                f"SELECT {_PUBLIC_COLUMNS} FROM device WHERE slot=1").fetchone())
            if current is None or not current["active"]:
                raise IdentityError("Current local device identity is unavailable")
            yield current

    @staticmethod
    def _old(db, operation_id, request=None):
        row = db.execute("SELECT request,receipt FROM operations WHERE id=?", (_uuid(operation_id),)).fetchone()
        if row is None:
            return None
        if request is not None and row["request"] != request:
            raise IdentityError("Device operation UUID already belongs to another request")
        if len(row["receipt"].encode("utf-8")) > _MAX_METADATA:
            raise IdentityError("Device operation receipt is invalid")
        try:
            result = json.loads(row["receipt"])
            if (result["operation_id"] != operation_id or result["request_sha256"] !=
                    hashlib.sha256(row["request"].encode("utf-8")).hexdigest()):
                raise ValueError
            return result
        except (ValueError, TypeError, KeyError):
            raise IdentityError("Device operation receipt is invalid") from None

    def operation(self, operation_id):
        _uuid(operation_id)
        with self._connect() as db:
            return None if db is None else self._old(db, operation_id)

    def _change(self, operation_id, kind, *, display_name=None, expected_generation=None):
        _uuid(operation_id)
        request = {"kind": kind}
        if kind == "initialize":
            request["display_name"] = _name(display_name)
        elif type(expected_generation) is not int or expected_generation < 1:
            raise IdentityError("Device generation must be a positive integer")
        else:
            request["expected_generation"] = expected_generation
        encoded = _json(request)
        with self._connect(write=True) as db:
            old = self._old(db, operation_id, encoded)
            if old is not None:
                return old
            if db.execute("SELECT count(*) FROM operations").fetchone()[0] >= _MAX_OPERATIONS:
                raise IdentityError("Device operation capacity is exhausted")
            row = db.execute(f"SELECT {_PUBLIC_COLUMNS} FROM device WHERE slot=1").fetchone()
            current = self._info(row)
            if kind == "initialize":
                if current is not None:
                    raise IdentityError("Device identity is already initialized")
                owner, name, generation = str(uuid4()), display_name, 1
            else:
                if current is None or current["generation"] != expected_generation or not current["active"]:
                    raise IdentityError("Device identity generation is not current")
                # Rotation needs the existing key. Revocation must still work
                # when that key is corrupt: it only invalidates public generation.
                if kind == "rotate":
                    self._key(db, current)
                owner, name, generation = current["card"]["owner_id"], current["card"]["display_name"], expected_generation + 1
            if kind == "revoke":
                db.execute("UPDATE device SET generation=?,active=0 WHERE slot=1", (generation,))
            else:
                try:
                    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                    key = Ed25519PrivateKey.generate()
                    public, seed = key.public_key().public_bytes_raw(), key.private_bytes_raw()
                    secret, provider = (_dpapi(seed), "windows-user-dpapi") if os.name == "nt" else (seed, "posix-private-file")
                except ImportError:
                    raise IdentityError("Device signing requires the optional peer dependency") from None
                db.execute("INSERT OR REPLACE INTO device VALUES (1,?,?,?,?,?,1,?,?)",
                           (owner, name, peer_id_for(public), public, generation, secret, provider))
            result = self._info(db.execute(f"SELECT {_PUBLIC_COLUMNS} FROM device WHERE slot=1").fetchone())
            receipt = {"format": "stk.peer-device-operation/1", "operation_id": operation_id,
                       "kind": kind, "request_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(), "result": result}
            db.execute("INSERT INTO operations VALUES (?,?,?)", (operation_id, encoded, _json(receipt)))
            return receipt

    def initialize(self, operation_id, display_name):
        return self._change(operation_id, "initialize", display_name=display_name)

    def rotate(self, operation_id, expected_generation):
        return self._change(operation_id, "rotate", expected_generation=expected_generation)

    def revoke(self, operation_id, expected_generation):
        return self._change(operation_id, "revoke", expected_generation=expected_generation)

    @staticmethod
    def _key(db, current):
        row = db.execute("SELECT secret,provider FROM device WHERE slot=1").fetchone()
        try:
            provider = "windows-user-dpapi" if os.name == "nt" else "posix-private-file"
            if row is None or row["provider"] != provider or type(row["secret"]) is not bytes:
                raise ValueError
            seed = _dpapi(row["secret"], decrypt=True) if os.name == "nt" else row["secret"]
            if len(seed) != 32:
                raise ValueError
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            key = Ed25519PrivateKey.from_private_bytes(seed)
            if key.public_key().public_bytes_raw().hex() != current["card"]["public_key"]:
                raise ValueError
            return key
        except (ValueError, TypeError, ImportError):
            raise IdentityError("Device signing key is unavailable") from None

    def signer(self, remote_owner_id):
        """No key captured: every signature checks active generation and live storage."""
        remote_owner_id = _uuid(remote_owner_id)
        current = self.info()
        if current is None or not current["active"]:
            raise IdentityError("Device identity is unavailable")
        generation, peer = current["generation"], current["card"]["peer_id"]

        def sign(message):
            try:
                prefix = b"STK-PEER-AUTH/1\0"
                if type(message) is not bytes or len(message) > 4096 or not message.startswith(prefix):
                    raise ValueError
                challenge = json.loads(message[len(prefix):].decode("ascii"))
                if (auth_message(challenge) != message or challenge["peer_id"] != peer
                        or challenge["owner_id"] != remote_owner_id):
                    raise ValueError
            except (ValueError, TypeError, KeyError, UnicodeError, PeerDenied):
                raise IdentityError("Device signer accepts only its pinned peer authentication challenge") from None
            with self._connect() as db:
                now = None if db is None else self._info(db.execute(f"SELECT {_PUBLIC_COLUMNS} FROM device WHERE slot=1").fetchone())
                if now is None or not now["active"] or now["generation"] != generation or now["card"]["peer_id"] != peer:
                    raise IdentityError("Device signer identity is no longer current")
                return self._key(db, now).sign(message)
        return sign


__all__ = ["LocalDeviceIdentity", "IdentityError", "DEVICE_FORMAT", "validate_card"]
