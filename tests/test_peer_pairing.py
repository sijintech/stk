"""Actual full-pin approval, signed contexts and explicit two-party session leases."""
from dataclasses import FrozenInstanceError
import json
import sqlite3
import threading
from uuid import uuid4

import pytest

pytest.importorskip("cryptography")

from suan.peer.authority import PeerAuthority, PeerContext, PeerDenied, auth_message
from suan.peer.identity import IdentityError, LocalDeviceIdentity
import suan.peer.pairing as module
from suan.peer.pairing import PairingError, PairingStore


def uid():
    return str(uuid4())


@pytest.fixture
def sides(tmp_path):
    wall, mono = [1000.0], [100.0]
    result = []
    for name in ("host", "recipient", "other"):
        identity = LocalDeviceIdentity(tmp_path / (name + "-identity"))
        identity.initialize(uid(), name)
        authority = PeerAuthority(tmp_path / (name + "-authority"),
                                  owner_id=identity.info()["card"]["owner_id"], clock=lambda: mono[0])
        pairing = PairingStore(authority.directory, identity, authority, clock=lambda: wall[0], monotonic=lambda: mono[0])
        result.append((identity, authority, pairing))
    host, recipient, other = result
    for local, remote in ((host, recipient), (recipient, host), (host, other)):
        card = remote[0].info()["card"]
        local[2].verify_pin(uid(), card, card["peer_id"])
    return host, recipient, other, wall, mono


def login(local, remote):
    _, authority, _ = local
    identity = remote[0]
    card = identity.info()["card"]
    challenge = authority.challenge(card["peer_id"], channel_binding="b" * 64)
    signature = identity.signer(authority.owner_id)(auth_message(challenge))
    return authority.authenticate(challenge["challenge_id"], signature)


def approved(sides, lifetime=300):
    host, recipient, _, _, _ = sides
    hc, rc = login(host, recipient), login(recipient, host)
    approval = host[2].host_session(uid(), recipient[0].info()["card"]["peer_id"], lifetime, context=hc)
    accepted = recipient[2].accept_session(uid(), rc, approval["result"]["offer"])
    return hc, rc, approval, accepted


def test_passive_pairing_reads_never_create_tables_or_enter_write_transaction(tmp_path, monkeypatch):
    identity = LocalDeviceIdentity(tmp_path / "identity")
    card = identity.initialize(uid(), "Device")["result"]["card"]
    authority = PeerAuthority(tmp_path / "authority", owner_id=card["owner_id"])
    pairing = PairingStore(authority.directory, identity, authority)
    before = authority.path.read_bytes()
    monkeypatch.setattr(authority, "_transaction", lambda: pytest.fail("Public reads must be read-only"))
    assert pairing.pins() == []
    assert pairing.sessions() == []
    assert pairing.operation(uid()) is None
    assert authority.path.read_bytes() == before
    with sqlite3.connect(authority.path) as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'pairing_%'").fetchone()[0] == 0
    assert repr(pairing) == "<PairingStore>"


def test_full_pin_owner_cannot_be_substituted_even_with_identical_public_key(sides):
    host, recipient, *_ = sides
    pairing = host[2]
    card = recipient[0].info()["card"]
    substituted = {**card, "owner_id": uid()}
    for action in (lambda: None, lambda: pairing.revoke_pin(uid(), card["peer_id"])):
        action()
        with pytest.raises(PairingError, match="owner or public"):
            pairing.verify_pin(uid(), substituted, card["peer_id"])
        assert pairing.pin(card["peer_id"])["card"]["owner_id"] == card["owner_id"]


def test_verified_pin_replay_is_historical_and_cannot_revive_revoked_authority(sides):
    host, recipient, *_ = sides
    identity, authority, pairing = host
    card = recipient[0].info()["card"]
    operation_id = uid()
    receipt = pairing.verify_pin(operation_id, card, card["peer_id"])
    context = login(host, recipient)
    assert authority.capabilities(context) == frozenset()
    pairing.revoke_pin(uid(), card["peer_id"])
    assert pairing.verify_pin(operation_id, card, card["peer_id"]) == receipt
    assert not pairing.pin(card["peer_id"])["active"]
    with pytest.raises(PeerDenied):
        authority.challenge(card["peer_id"], channel_binding="b" * 64)
    with pytest.raises(PairingError):
        pairing.verify_pin(operation_id, {**card, "display_name": "Other"}, card["peer_id"])
    fresh = pairing.verify_pin(uid(), card, card["peer_id"])
    assert fresh["result"]["epoch"] == receipt["result"]["epoch"] + 2
    with pytest.raises(PeerDenied), authority.peer_access(context):
        pytest.fail("Reapproval cannot restore an old context")
    with pairing.peer_access(login(host, recipient)) as lease:
        assert lease.remote_owner_id == card["owner_id"]
        assert lease.peer_epoch > 1


def test_pin_requires_explicit_matching_fingerprint_and_nonself_card(sides):
    host, recipient, *_ = sides
    card = recipient[0].info()["card"]
    with pytest.raises(PairingError, match="fingerprint"):
        host[2].verify_pin(uid(), card, "c" * 64)
    own = host[0].info()["card"]
    with pytest.raises(PairingError, match="itself"):
        host[2].verify_pin(uid(), own, own["peer_id"])
    with pytest.raises(IdentityError):
        host[2].verify_pin(uid(), {**card, "address": "loopback"}, card["peer_id"])


def test_peer_lease_authenticates_without_inventing_project_or_file_permission(sides):
    host, recipient, *_ = sides
    context = login(host, recipient)
    with host[1].peer_access(context) as lease:
        assert lease.owner_id == host[1].owner_id
        assert lease.peer_id == recipient[0].info()["card"]["peer_id"]
        assert lease.registry_id and lease.peer_epoch == 1
        with pytest.raises(FrozenInstanceError):
            lease.peer_epoch = 2
    assert host[1].capabilities(context) == frozenset()
    for forged in (PeerContext(), {}, None, recipient[0].info()["card"]["peer_id"]):
        with pytest.raises(PeerDenied), host[1].peer_access(forged):
            pytest.fail("An identity lease must reject fabricated contexts")
    with pytest.raises(PairingError), host[2].session_access(context, uid()):
        pytest.fail("Pairing alone is not a session grant")


def test_two_party_host_approval_and_recipient_accept_yield_bound_primitive_leases(sides):
    host, recipient, *_ = sides
    hc, rc, approval, accepted = approved(sides)
    offer = approval["result"]["offer"]
    assert accepted["result"]["offer"] == offer
    for local, context, role in ((host, hc, "host"), (recipient, rc, "recipient")):
        with local[2].session_access(context, offer["session_id"]) as lease:
            assert lease.role == role and lease.session_epoch == 1
            assert lease.identity_generation == 1
            assert lease.host_owner_id == host[1].owner_id
            assert lease.owner_id == local[1].owner_id
            assert lease.registry_id == local[1]._registry_id
            assert lease.local_peer_id == local[0].info()["card"]["peer_id"]
            assert not any(isinstance(value, (dict, bytes)) for value in vars(lease).values())
        assert local[1].capabilities(context) == frozenset()


def test_host_cannot_approve_different_authenticated_recipient(sides):
    host, recipient, other, *_ = sides
    with pytest.raises(PairingError, match="authenticated peer"):
        host[2].host_session(uid(), recipient[0].info()["card"]["peer_id"], 30, context=login(host, other))
    assert host[2].sessions() == []


@pytest.mark.parametrize("fault", ["host_owner", "recipient_owner", "recipient_key", "expired", "oversized_lifetime", "unknown_key"])
def test_recipient_accepts_only_current_full_host_and_exact_own_card(sides, fault):
    host, recipient, other, wall, _ = sides
    hc, rc = login(host, recipient), login(recipient, host)
    offer = host[2].host_session(uid(), recipient[0].info()["card"]["peer_id"], 30, context=hc)["result"]["offer"]
    if fault == "host_owner":
        offer["host"]["owner_id"] = uid()
    elif fault == "recipient_owner":
        offer["recipient"]["owner_id"] = uid()
    elif fault == "recipient_key":
        offer["recipient"] = other[0].info()["card"]
    elif fault == "expired":
        offer["expires_at"] = wall[0]
    elif fault == "oversized_lifetime":
        offer["expires_at"] = wall[0] + 3601
    else:
        offer["unknown"] = True
    with pytest.raises(PairingError):
        recipient[2].accept_session(uid(), rc, offer)
    assert recipient[2].sessions() == []


def test_old_approval_receipts_do_not_bind_new_context_and_resume_needs_new_host_epoch(sides):
    host, recipient, *_ = sides
    hc, rc = login(host, recipient), login(recipient, host)
    hid, rid = uid(), uid()
    peer = recipient[0].info()["card"]["peer_id"]
    original = host[2].host_session(hid, peer, 300, context=hc)
    offer = original["result"]["offer"]
    accepted = recipient[2].accept_session(rid, rc, offer)
    newhc, newrc = login(host, recipient), login(recipient, host)
    assert host[2].host_session(hid, peer, 300, context=newhc) == original
    assert recipient[2].accept_session(rid, newrc, offer) == accepted
    for local, context in ((host, newhc), (recipient, newrc)):
        with pytest.raises(PairingError, match="explicit approval"), local[2].session_access(context, offer["session_id"]):
            pytest.fail("An old operation cannot bind another connection")
    with pytest.raises(PairingError, match="new Host approval"):
        recipient[2].accept_session(uid(), newrc, offer)
    renewed = host[2].host_session(uid(), peer, 300, context=newhc, session_id=offer["session_id"])["result"]["offer"]
    assert renewed["session_epoch"] == 2
    recipient[2].accept_session(uid(), newrc, renewed)
    # Historical replies stay historical and do not overwrite the newer runtime binding.
    assert recipient[2].accept_session(rid, rc, offer) == accepted
    with recipient[2].session_access(newrc, offer["session_id"]) as lease:
        assert lease.session_epoch == 2
    for local, old_context in ((host, hc), (recipient, rc)):
        with pytest.raises(PairingError), local[2].session_access(old_context, offer["session_id"]):
            pytest.fail("Previous context must not inherit resumed authority")


def test_reopen_only_reads_history_and_old_operation_cannot_restore_runtime_binding(sides):
    host, recipient, _, wall, mono = sides
    hc = login(host, recipient)
    op, peer = uid(), recipient[0].info()["card"]["peer_id"]
    original = host[2].host_session(op, peer, 300, context=hc)
    sid = original["result"]["offer"]["session_id"]
    reopened = PairingStore(host[1].directory, host[0], host[1], clock=lambda: wall[0], monotonic=lambda: mono[0])
    assert not reopened.session(sid)["context_bound"]
    assert reopened.host_session(op, peer, 300, context=hc) == original
    with pytest.raises(PairingError), reopened.session_access(hc, sid):
        pytest.fail("Persisted approval history cannot restore a live context")
    renewed = reopened.host_session(uid(), peer, 300, context=hc, session_id=sid)
    with reopened.session_access(hc, sid) as lease:
        assert lease.session_epoch == renewed["result"]["offer"]["session_epoch"] == 2


def test_context_expiry_and_wall_clock_rollback_cannot_extend_session(sides):
    host, recipient, _, wall, mono = sides
    hc, _, approval, _ = approved(sides, lifetime=30)
    sid = approval["result"]["offer"]["session_id"]
    wall[0] -= 100
    mono[0] += 31
    with pytest.raises(PairingError), host[2].session_access(hc, sid):
        pytest.fail("Monotonic lifetime must survive a backwards wall clock")
    wall[0], mono[0] = 1000, 100
    hc, _, approval, _ = approved(sides, lifetime=3600)
    sid = approval["result"]["offer"]["session_id"]
    wall[0] += 601
    mono[0] += 601
    with pytest.raises(PeerDenied), host[2].session_access(hc, sid):
        pytest.fail("A 3600-second logical session must not renew a 600-second PeerContext")
    with pytest.raises(PairingError), host[2].session_access(login(host, recipient), sid):
        pytest.fail("Reauthentication still needs explicit Host reapproval")


def test_session_and_pin_revocation_and_local_rotation_invalidate_current_leases(sides):
    host, recipient, *_ = sides
    hc, rc, approval, _ = approved(sides)
    sid = approval["result"]["offer"]["session_id"]
    host[2].revoke_session(uid(), sid)
    with pytest.raises(PairingError), host[2].session_access(hc, sid):
        pytest.fail("Explicit session revocation must apply immediately")
    with pytest.raises(PairingError):
        host[2].host_session(uid(), recipient[0].info()["card"]["peer_id"], 30, context=hc, session_id=sid)
    hc, rc, approval, _ = approved(sides)
    sid = approval["result"]["offer"]["session_id"]
    host[0].rotate(uid(), 1)
    with pytest.raises(PairingError), host[2].session_access(hc, sid):
        pytest.fail("Local key lifecycle change invalidates old session generation")
    recipient[2].revoke_pin(uid(), approval["result"]["offer"]["host"]["peer_id"])
    with pytest.raises(PeerDenied), recipient[2].session_access(rc, sid):
        pytest.fail("Revoking a full pin invalidates old authenticated contexts too")


def test_session_revoke_waits_for_an_accepted_lease_across_authority_instances(sides):
    host, recipient, _, wall, mono = sides
    hc, _, approval, _ = approved(sides)
    sid = approval["result"]["offer"]["session_id"]
    another = PeerAuthority(host[1].directory, owner_id=host[1].owner_id, clock=lambda: mono[0])
    revoker = PairingStore(another.directory, host[0], another, clock=lambda: wall[0], monotonic=lambda: mono[0])
    entered, release, attempted, finished = (threading.Event() for _ in range(4))
    errors = []
    def accept():
        try:
            with host[2].session_access(hc, sid):
                entered.set()
                assert release.wait(5)
        except Exception as exc:
            errors.append(type(exc).__name__)
    def revoke():
        try:
            attempted.set()
            revoker.revoke_session(uid(), sid)
            finished.set()
        except Exception as exc:
            errors.append(type(exc).__name__)
    accepted = threading.Thread(target=accept)
    accepted.start()
    assert entered.wait(3)
    revoked = threading.Thread(target=revoke)
    revoked.start()
    assert attempted.wait(3)
    assert not finished.wait(.1)
    release.set()
    accepted.join(5)
    revoked.join(5)
    assert not accepted.is_alive() and not revoked.is_alive() and not errors
    assert finished.is_set()
    with pytest.raises(PairingError), host[2].session_access(hc, sid):
        pytest.fail("The next bounded acceptance must observe revocation")


def test_pin_public_metadata_authority_and_receipt_roll_back_together(sides, monkeypatch):
    host, _, other, *_ = sides
    # The third device has never approved the first: inject a receipt publication failure.
    card = host[0].info()["card"]
    original = module._json
    def fail_receipt(value):
        if isinstance(value, dict) and value.get("format") == "stk.peer-pairing-operation/1":
            raise IdentityError("Synthetic receipt publication failure")
        return original(value)
    monkeypatch.setattr(module, "_json", fail_receipt)
    with pytest.raises(IdentityError):
        other[2].verify_pin(uid(), card, card["peer_id"])
    assert other[2].pins() == []
    with pytest.raises(PeerDenied):
        other[1].challenge(card["peer_id"], channel_binding="b" * 64)


def test_capacity_never_evicts_original_receipts_or_approved_pins(sides, monkeypatch):
    host, recipient, *_ = sides
    card = recipient[0].info()["card"]
    op = uid()
    receipt = host[2].verify_pin(op, card, card["peer_id"])
    with sqlite3.connect(host[1].path) as db:
        count = db.execute("SELECT count(*) FROM pairing_operations").fetchone()[0]
    monkeypatch.setattr(module, "MAX_OPERATIONS", count)
    with pytest.raises(PairingError, match="capacity"):
        host[2].host_session(uid(), card["peer_id"], 30, context=login(host, recipient))
    assert host[2].verify_pin(op, card, card["peer_id"]) == receipt
    assert host[2].pin(card["peer_id"])["active"]


@pytest.mark.parametrize("lifetime", [True, 0, -1, 3601, 1.0])
def test_session_lifetime_is_explicit_bounded_integer(sides, lifetime):
    host, recipient, *_ = sides
    with pytest.raises(PairingError, match="lifetime"):
        host[2].host_session(uid(), recipient[0].info()["card"]["peer_id"], lifetime, context=login(host, recipient))
    assert host[2].sessions() == []


@pytest.mark.parametrize("kind", ["rotate", "revoke"])
def test_identity_lifecycle_waits_for_bounded_session_lease(sides, kind):
    host, _, *_ = sides
    hc, _, approval, _ = approved(sides)
    sid = approval["result"]["offer"]["session_id"]
    entered, release, attempted, finished = (threading.Event() for _ in range(4))
    errors = []
    def accept():
        try:
            with host[2].session_access(hc, sid):
                entered.set()
                assert release.wait(5)
        except Exception as exc:
            errors.append(type(exc).__name__)
    def lifecycle():
        try:
            attempted.set()
            reopened = LocalDeviceIdentity(host[0].directory)
            getattr(reopened, kind)(uid(), 1)
            finished.set()
        except Exception as exc:
            errors.append(type(exc).__name__)
    reader, writer = threading.Thread(target=accept), threading.Thread(target=lifecycle)
    reader.start()
    assert entered.wait(3)
    writer.start()
    assert attempted.wait(3)
    assert not finished.wait(.1)
    release.set()
    reader.join(5)
    writer.join(5)
    assert not reader.is_alive() and not writer.is_alive() and finished.is_set() and not errors
    with pytest.raises((PairingError, IdentityError)), host[2].session_access(hc, sid):
        pytest.fail("The next bounded block must observe the identity lifecycle change")


def test_corrupt_key_still_allows_explicit_revoke_to_block_active_sessions(sides):
    host, *_ = sides
    hc, _, approval, _ = approved(sides)
    with sqlite3.connect(host[0].path) as db:
        db.execute("UPDATE device SET secret=?", (b"a" * 32,))
    host[0].revoke(uid(), 1)
    with pytest.raises(IdentityError), host[2].session_access(hc, approval["result"]["offer"]["session_id"]):
        pytest.fail("Corrupt-key revocation must still stop existing sharing sessions")


def test_session_lease_preserves_file_adapter_error(sides):
    host, *_ = sides
    hc, _, approval, _ = approved(sides)
    failure = OSError("Synthetic file-adapter failure")
    with pytest.raises(OSError) as observed:
        with host[2].session_access(hc, approval["result"]["offer"]["session_id"]):
            raise failure
    assert observed.value is failure
