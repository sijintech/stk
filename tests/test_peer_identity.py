"""Real isolated persistent signatures and explicit device lifecycle; no user keys."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from suan.peer.authority import auth_message
from suan.peer.identity import IdentityError, LocalDeviceIdentity, validate_card


REMOTE = "22222222-2222-4222-8222-222222222222"


def challenge(card):
    return {"format": "stk.peer-auth/1", "owner_id": REMOTE, "peer_id": card["peer_id"],
            "challenge_id": "33333333-3333-4333-8333-333333333333", "nonce": "b" * 64,
            "channel_binding": "c" * 64, "expires_in": 60}


def test_public_reads_are_passive_and_do_not_select_private_columns(tmp_path, monkeypatch):
    root = tmp_path / "device"
    identity = LocalDeviceIdentity(root)
    assert identity.info() is None
    assert identity.operation(str(uuid4())) is None
    assert not root.exists()
    identity.initialize(str(uuid4()), "测试设备")
    original = sqlite3.connect
    statements = []
    def trace(*args, **kwargs):
        db = original(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db
    monkeypatch.setattr(sqlite3, "connect", trace)
    assert identity.info()["active"]
    assert identity.operation(str(uuid4())) is None
    assert not any("secret" in s.lower() or "provider" in s.lower() or "create " in s.lower()
                   for s in statements)


def test_real_signature_survives_new_interpreter_without_returning_key(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    created = identity.initialize(str(uuid4()), "Device")
    card = created["result"]["card"]
    message = auth_message(challenge(card))
    payload = {"directory": str(identity.directory), "remote": REMOTE, "message": message.hex()}
    code = """import json,sys
from suan.peer.identity import LocalDeviceIdentity
p=json.loads(sys.stdin.read()); d=LocalDeviceIdentity(p['directory'])
print(json.dumps({'public':d.info(), 'signature':d.signer(p['remote'])(bytes.fromhex(p['message'])).hex()}))
"""
    env = {**os.environ, "STK_TOKEN_PLAN_API_KEY": ""}
    env.pop("STK_TOKEN_PLAN_MODEL", None)
    result = subprocess.run([sys.executable, "-c", code], input=json.dumps(payload), text=True,
                            capture_output=True, env=env, timeout=20, check=True)
    answer = json.loads(result.stdout)
    assert answer["public"] == created["result"]
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(card["public_key"])).verify(bytes.fromhex(answer["signature"]), message)
    assert set(created) == {"format", "operation_id", "kind", "request_sha256", "result"}
    assert "secret" not in json.dumps(created)
    assert repr(identity) == "<LocalDeviceIdentity>"


def test_lifecycle_old_receipt_never_reactivates_key_or_old_signer(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    init_id, rotate_id, revoke_id = (str(uuid4()) for _ in range(3))
    first = identity.initialize(init_id, "Device")
    card = first["result"]["card"]
    sign = identity.signer(REMOTE)
    sign(auth_message(challenge(card)))
    rotated = identity.rotate(rotate_id, 1)
    assert rotated["result"]["generation"] == 2
    assert rotated["result"]["card"]["owner_id"] == card["owner_id"]
    assert rotated["result"]["card"]["peer_id"] != card["peer_id"]
    with pytest.raises(IdentityError, match="no longer current"):
        sign(auth_message(challenge(card)))
    assert identity.initialize(init_id, "Device") == first
    assert identity.info() == rotated["result"]
    sign2 = identity.signer(REMOTE)
    identity.revoke(revoke_id, 2)
    with pytest.raises(IdentityError):
        sign2(auth_message(challenge(rotated["result"]["card"])))
    assert identity.rotate(rotate_id, 1) == rotated
    assert not identity.info()["active"]
    with pytest.raises(IdentityError):
        identity.signer(REMOTE)
    with pytest.raises(IdentityError):
        identity.rotate(str(uuid4()), 3)


@pytest.mark.parametrize("alter", [
    lambda c: {**c, "owner_id": "44444444-4444-4444-8444-444444444444"},
    lambda c: {**c, "peer_id": "d" * 64},
    lambda c: {**c, "expires_in": True},
    lambda c: {**c, "extra": "ignored"},
])
def test_signer_is_not_an_arbitrary_or_other_owner_signing_oracle(tmp_path, alter):
    identity = LocalDeviceIdentity(tmp_path / "device")
    card = identity.initialize(str(uuid4()), "Device")["result"]["card"]
    changed = alter(challenge(card))
    raw = b"STK-PEER-AUTH/1\0" + json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("ascii")
    with pytest.raises(IdentityError):
        identity.signer(REMOTE)(raw)
    for raw in (b"hello", b"STK-PEER-AUTH/1\0{}", "not bytes"):
        with pytest.raises(IdentityError):
            identity.signer(REMOTE)(raw)


def test_original_operation_and_generation_are_strict(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    op = str(uuid4())
    receipt = identity.initialize(op, "Device")
    assert identity.initialize(op, "Device") == receipt
    with pytest.raises(IdentityError, match="another request"):
        identity.initialize(op, "Other")
    for generation in (True, 0, 2, 1.0):
        with pytest.raises(IdentityError):
            identity.rotate(str(uuid4()), generation)
    assert identity.info() == receipt["result"]


@pytest.mark.parametrize("fault", ["key", "provider", "database_replacement", "database_loss"])
def test_key_corruption_loss_or_state_replacement_never_generates_another_key(tmp_path, monkeypatch, fault):
    identity = LocalDeviceIdentity(tmp_path / "device")
    card = identity.initialize(str(uuid4()), "Device")["result"]["card"]
    signer = identity.signer(REMOTE)
    if fault == "database_replacement":
        original = identity.path.with_suffix(".original")
        identity.path.rename(original)
        identity.path.write_bytes(original.read_bytes())
        identity.path.chmod(0o600)
    elif fault == "database_loss":
        identity.path.unlink()
    else:
        with sqlite3.connect(identity.path) as db:
            if fault == "key":
                db.execute("UPDATE device SET secret=?", (b"a" * 32,))
            else:
                db.execute("UPDATE device SET provider='unavailable'")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    monkeypatch.setattr(Ed25519PrivateKey, "generate", lambda: pytest.fail("A read/sign/rotate must not repair keys"))
    with pytest.raises(IdentityError):
        signer(auth_message(challenge(card)))
    with pytest.raises(IdentityError):
        identity.rotate(str(uuid4()), 1)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode enforcement")
def test_private_modes_and_linked_state_are_rejected(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    identity.initialize(str(uuid4()), "Device")
    assert identity.directory.stat().st_mode & 0o777 == 0o700
    assert identity.path.stat().st_mode & 0o777 == 0o600
    identity.path.chmod(0o644)
    with pytest.raises(IdentityError, match="owner-only"):
        identity.info()
    identity.path.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(identity.directory, target_is_directory=True)
    with pytest.raises(IdentityError, match="links"):
        LocalDeviceIdentity(alias).info()


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows user DPAPI provider")
def test_windows_real_dpapi_roundtrip_and_corruption_refusal(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    card = identity.initialize(str(uuid4()), "Device")["result"]["card"]
    reopened = LocalDeviceIdentity(identity.directory)
    message = auth_message(challenge(card))
    signature = reopened.signer(REMOTE)(message)
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(card["public_key"])).verify(signature, message)
    with sqlite3.connect(identity.path) as db:
        provider, size = db.execute("SELECT provider,length(secret) FROM device").fetchone()
        assert provider == "windows-user-dpapi" and size > 32
        db.execute("UPDATE device SET secret=?", (b"a" * 64,))
    with pytest.raises(IdentityError):
        reopened.signer(REMOTE)(message)


def test_public_card_rejects_wrong_fingerprint_and_unknown_metadata(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    card = identity.initialize(str(uuid4()), "Device")["result"]["card"]
    for changed in ({**card, "peer_id": "a" * 64}, {**card, "path": "/private"}, {**card, "public_key": "b" * 63}):
        with pytest.raises(IdentityError):
            validate_card(changed)


def test_corrupt_key_does_not_prevent_explicit_revoke_or_regenerate(tmp_path, monkeypatch):
    identity = LocalDeviceIdentity(tmp_path / "device")
    card = identity.initialize(str(uuid4()), "Device")["result"]["card"]
    old_signer = identity.signer(REMOTE)
    with sqlite3.connect(identity.path) as db:
        db.execute("UPDATE device SET secret=?", (b"a" * 32,))
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    monkeypatch.setattr(Ed25519PrivateKey, "generate", lambda: pytest.fail("Revocation cannot generate keys"))
    revoked = identity.revoke(str(uuid4()), 1)
    assert revoked["result"]["generation"] == 2
    assert not revoked["result"]["active"]
    with pytest.raises(IdentityError):
        old_signer(auth_message(challenge(card)))


def test_lost_previously_opened_state_is_not_created_before_rejection(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    identity.initialize(str(uuid4()), "Device")
    identity.path.unlink()
    with pytest.raises(IdentityError, match="lost"):
        identity.initialize(str(uuid4()), "Other")
    assert not identity.path.exists()


def test_public_identity_lease_preserves_caller_oserror_identity(tmp_path):
    identity = LocalDeviceIdentity(tmp_path / "device")
    identity.initialize(str(uuid4()), "Device")
    failure = OSError("Synthetic caller disk-full failure")
    with pytest.raises(OSError) as observed:
        with identity.current_identity():
            raise failure
    assert observed.value is failure
