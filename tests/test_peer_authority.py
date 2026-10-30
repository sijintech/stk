"""Real signatures and persistent authority invariants; no model or network service."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import suan.peer.authority as module
from suan.peer.authority import PeerAuthority, PeerContext, PeerDenied, auth_message, peer_id_for
from suan.project import ProjectStore


@pytest.fixture
def setup(tmp_path):
    now = [100.0]
    authority = PeerAuthority(tmp_path / "authority", owner_id=str(uuid4()), clock=lambda: now[0])
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    peer = peer_id_for(public)
    authority.approve_peer(peer, public)
    store = ProjectStore.create(tmp_path / "project", "Public test project")
    binding = authority.bind_project(store.directory)
    grant = authority.grant(peer, binding["project_id"], ["project.read", "project.edit"])
    return authority, key, peer, store, binding, grant, now


def login(authority, key, peer, binding="b" * 64):
    challenge = authority.challenge(peer, channel_binding=binding)
    return authority.authenticate(challenge["challenge_id"], key.sign(auth_message(challenge)))


def access(setup, context, authority=None):
    original, _, _, _, binding, grant, _ = setup
    return (authority or original).project_access(context, binding["project_id"],
        grant_id=grant["grant_id"], database_generation=grant["database_generation"], capability="project.read")


def test_valid_proof_is_single_use_and_context_is_not_a_wire_credential(setup):
    authority, key, peer, _, _, _, _ = setup
    challenge = authority.challenge(peer, channel_binding="b" * 64)
    signature = key.sign(auth_message(challenge))
    context = authority.authenticate(challenge["challenge_id"], signature)
    with access(setup, context) as lease:
        assert lease.operation_scope.startswith("peer/1/")
    with pytest.raises(PeerDenied):
        authority.authenticate(challenge["challenge_id"], signature)
    for forged in (PeerContext(), {"peer_id": peer}, peer, None):
        with pytest.raises(PeerDenied), access(setup, forged):
            pytest.fail("A fabricated context must not enter the project")
    assert repr(context) == "<PeerContext>"


@pytest.mark.parametrize("field,value", [
    ("channel_binding", "c" * 64), ("owner_id", "11111111-1111-4111-8111-111111111111"),
    ("peer_id", "d" * 64), ("nonce", "e" * 64),
])
def test_signature_cannot_be_retargeted_to_another_channel_or_identity(setup, field, value):
    authority, key, peer, *_ = setup
    challenge = authority.challenge(peer, channel_binding="b" * 64)
    altered = {**challenge, field: value}
    with pytest.raises(PeerDenied, match="authentication failed"):
        authority.authenticate(challenge["challenge_id"], key.sign(auth_message(altered)))
    # Failure consumed the nonce too; a fresh valid handshake remains possible.
    with pytest.raises(PeerDenied):
        authority.authenticate(challenge["challenge_id"], key.sign(auth_message(challenge)))
    with access(setup, login(authority, key, peer)):
        pass


def test_unpaired_or_wrong_key_cannot_authenticate(setup):
    authority, _, peer, *_ = setup
    wrong = Ed25519PrivateKey.generate()
    with pytest.raises(PeerDenied):
        authority.challenge(peer_id_for(wrong.public_key().public_bytes_raw()), channel_binding="b" * 64)
    challenge = authority.challenge(peer, channel_binding="b" * 64)
    with pytest.raises(PeerDenied):
        authority.authenticate(challenge["challenge_id"], wrong.sign(auth_message(challenge)))


def test_expired_challenge_and_session_and_explicit_disconnect_are_rejected(setup):
    authority, key, peer, _, _, _, now = setup
    challenge = authority.challenge(peer, channel_binding="b" * 64)
    now[0] += module.CHALLENGE_SECONDS
    with pytest.raises(PeerDenied):
        authority.authenticate(challenge["challenge_id"], key.sign(auth_message(challenge)))
    context = login(authority, key, peer)
    now[0] += module.SESSION_SECONDS
    with pytest.raises(PeerDenied), access(setup, context):
        pass
    context = login(authority, key, peer)
    authority.disconnect(context)
    with pytest.raises(PeerDenied), access(setup, context):
        pass


def test_revoke_then_reapprove_never_revives_old_sessions_or_challenges(setup):
    authority, key, peer, _, _, _, _ = setup
    old = login(authority, key, peer)
    challenge = authority.challenge(peer, channel_binding="b" * 64)
    authority.revoke_peer(peer)
    authority.approve_peer(peer, key.public_key().public_bytes_raw())
    with pytest.raises(PeerDenied):
        authority.authenticate(challenge["challenge_id"], key.sign(auth_message(challenge)))
    with pytest.raises(PeerDenied), access(setup, old):
        pass
    assert authority.capabilities(login(authority, key, peer)) == frozenset()


def test_registry_restart_requires_new_proof_but_preserves_operation_namespace(setup):
    authority, key, peer, *_ = setup
    old = login(authority, key, peer)
    with access(setup, old) as lease:
        original_scope = lease.operation_scope
    reopened = PeerAuthority(authority.directory, owner_id=authority.owner_id)
    with pytest.raises(PeerDenied), access(setup, old, reopened):
        pass
    with access(setup, login(reopened, key, peer), reopened) as lease:
        assert lease.operation_scope == original_scope
    with pytest.raises(PeerDenied):
        PeerAuthority(authority.directory, owner_id=str(uuid4()))


def test_grant_exhaustion_keeps_previously_authorized_access(setup, monkeypatch):
    authority, key, peer, _, binding, _, _ = setup
    monkeypatch.setattr(module, "MAX_GRANTS", 1)
    with pytest.raises(PeerDenied, match="capacity"):
        authority.grant(peer, binding["project_id"], ["project.edit"])
    assert authority.capabilities(login(authority, key, peer)) == {"project.read", "project.edit"}


def test_session_capacity_does_not_evict_an_accepted_session(setup, monkeypatch):
    authority, key, peer, *_ = setup
    monkeypatch.setattr(module, "MAX_SESSIONS", 1)
    original = login(authority, key, peer)
    with pytest.raises(PeerDenied, match="capacity"):
        login(authority, key, peer)
    with access(setup, original):
        pass


def test_challenge_capacity_does_not_replace_an_outstanding_nonce(setup, monkeypatch):
    authority, key, peer, *_ = setup
    monkeypatch.setattr(module, "MAX_CHALLENGES", 1)
    original = authority.challenge(peer, channel_binding="b" * 64)
    with pytest.raises(PeerDenied, match="capacity"):
        authority.challenge(peer, channel_binding="b" * 64)
    context = authority.authenticate(original["challenge_id"], key.sign(auth_message(original)))
    with access(setup, context):
        pass


@pytest.mark.parametrize("corrupt", ["{", "{}", '["project.read", "project.read"]', '["models.configure"]'])
def test_invalid_stored_grant_cannot_turn_into_a_permission(setup, corrupt):
    authority, key, peer, _, _, grant, _ = setup
    context = login(authority, key, peer)
    with sqlite3.connect(authority.path) as db:
        db.execute("UPDATE grants SET capabilities=? WHERE grant_id=?", (corrupt, grant["grant_id"]))
    with pytest.raises(PeerDenied):
        authority.capabilities(context)
    with pytest.raises(PeerDenied), access(setup, context):
        pass


def test_changed_public_key_is_not_authenticated_under_the_old_fingerprint(setup):
    authority, key, peer, *_ = setup
    original = login(authority, key, peer)
    replacement = Ed25519PrivateKey.generate()
    challenge = authority.challenge(peer, channel_binding="b" * 64)
    with sqlite3.connect(authority.path) as db:
        db.execute("UPDATE peers SET public_key=? WHERE peer_id=?",
                   (replacement.public_key().public_bytes_raw(), peer))
    with pytest.raises(PeerDenied):
        authority.authenticate(challenge["challenge_id"], replacement.sign(auth_message(challenge)))
    with pytest.raises(PeerDenied), access(setup, original):
        pass


def test_authority_registry_replacement_invalidates_live_contexts(setup, tmp_path):
    authority, key, peer, *_ = setup
    original = login(authority, key, peer)
    copy = tmp_path / "replacement.sqlite3"
    with closing(sqlite3.connect(authority.path)) as source, closing(sqlite3.connect(copy)) as target:
        source.backup(target)
    os.replace(copy, authority.path)
    before = authority.path.read_bytes()
    with pytest.raises(PeerDenied), access(setup, original):
        pass
    assert authority.path.read_bytes() == before


def test_foreign_registry_is_not_opened_or_modified(tmp_path):
    directory = tmp_path / "authority"
    directory.mkdir()
    database = directory / "peer-authority.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")
        db.execute("INSERT INTO unrelated VALUES ('public sentinel')")
    before = database.read_bytes()
    with pytest.raises(PeerDenied):
        PeerAuthority(directory, owner_id=str(uuid4()))
    assert database.read_bytes() == before


def test_revocation_serializes_with_an_operation_across_registry_instances(setup):
    authority, key, peer, _, _, grant, _ = setup
    other = PeerAuthority(authority.directory, owner_id=authority.owner_id)
    context = login(authority, key, peer)
    started, finished = threading.Event(), threading.Event()
    failure = []

    def revoke():
        started.set()
        try:
            other.revoke_grant(grant["grant_id"])
        except Exception as exc:
            failure.append(exc)
        finally:
            finished.set()

    with access(setup, context):
        thread = threading.Thread(target=revoke)
        thread.start()
        assert started.wait(5)
        assert not finished.wait(0.15), "Another registry must not revoke across an accepted store call"
    assert finished.wait(5)
    thread.join()
    assert not failure
    with pytest.raises(PeerDenied), access(setup, context):
        pass


def test_authority_cannot_be_exported_as_part_of_its_shared_project(tmp_path):
    project = ProjectStore.create(tmp_path / "project", "Public fixture")
    authority = PeerAuthority(project.directory / "private-authority", owner_id=str(uuid4()))
    with pytest.raises(PeerDenied, match="outside shared projects"):
        authority.bind_project(project.directory)
