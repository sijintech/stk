"""Real receiver filesystem, signed pairing and durable original-operation tests."""
import hashlib
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4
from contextlib import contextmanager

import pytest

pytest.importorskip("cryptography")

from suan.peer.authority import PeerAuthority, PeerDenied, auth_message
from suan.peer.identity import LocalDeviceIdentity
from suan.peer.pairing import PairingStore
from suan.peer.file_store import FileStore, FileStoreError
from suan.peer.file_protocol import CHUNK_BYTES, decode_frame, encode_data, validate_file_result, validate_receipt
from suan.peer.manifests import manifest_sha256


def uid():
    return str(uuid4())


def login(local, remote):
    challenge = local[1].challenge(remote[0].info()["card"]["peer_id"], channel_binding="a" * 64)
    return local[1].authenticate(challenge["challenge_id"], remote[0].signer(local[1].owner_id)(auth_message(challenge)))


@pytest.fixture
def pair(tmp_path):
    sides = []
    for name in ("host", "recipient"):
        identity = LocalDeviceIdentity(tmp_path / (name + "-key"))
        card = identity.initialize(uid(), name)["result"]["card"]
        authority = PeerAuthority(tmp_path / (name + "-authority"), owner_id=card["owner_id"])
        sides.append((identity, authority, PairingStore(authority.directory, identity, authority)))
    host, receiver = sides
    for local, remote in ((host, receiver), (receiver, host)):
        card = remote[0].info()["card"]
        local[2].verify_pin(uid(), card, card["peer_id"])
    hc, rc = login(host, receiver), login(receiver, host)
    store = FileStore(tmp_path / "files", receiver[2])
    return host, receiver, hc, rc, store, tmp_path


def offer(pair, contents=None):
    host, receiver, hc, rc, store, _ = pair
    contents = {"数据/value.bin": b"z" * (CHUNK_BYTES + 17), "empty": b""} if contents is None else contents
    session = host[2].host_session(uid(), receiver[0].info()["card"]["peer_id"], 300, context=hc)["result"]["offer"]
    manifest = {"format": "stk.peer-files-manifest/1", "project_id": uid(), "source_revision": 1,
                "snapshot_id": uid(), "snapshot_sha256": "b" * 64, "files": [
                    {"file_id": uid(), "name": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                     "media_type": "application/octet-stream"} for name, body in contents.items()]}
    params = {"session_id": session["session_id"], "transfer_id": uid(), "manifest_sha256": manifest_sha256(manifest),
              "operation_id": uid(), "manifest": manifest, "session_offer": session}
    result = store.call(rc, "files.offer", params)
    return params, result, contents


def accept_start(pair, params):
    _, _, _, context, store, root = pair
    accepted = store.accept(uid(), context, params["transfer_id"], params["operation_id"], root / "received")["result"]
    control = {key: params[key] for key in ("session_id", "transfer_id", "manifest_sha256")}
    control.update(operation_id=uid(), grant_id=accepted["grant_id"])
    store.call(context, "files.start", control)
    return control


def send(pair, params, contents):
    context, store = pair[3:5]
    for item in params["manifest"]["files"]:
        body = contents[item["name"]]
        for sequence, offset in enumerate(range(0, len(body), CHUNK_BYTES)):
            frame = encode_data(params["transfer_id"], item["file_id"], sequence, offset, body[offset:offset + CHUNK_BYTES])
            receipt = store.accept_data(context, frame)
            validate_receipt(decode_frame(receipt), decode_frame(frame))


def status(pair, params, operation_id=None):
    request = {key: params[key] for key in ("session_id", "transfer_id", "manifest_sha256")}
    request["operation_id"] = operation_id
    return pair[4].call(pair[3], "files.status", request)


def test_offer_capabilities_and_queries_are_passive_to_target_and_stage(pair):
    store, root = pair[4:]
    assert store.capabilities(pair[3])["files.offer"] == 1
    assert not store.directory.exists()
    params, result, _ = offer(pair)
    assert result["state"] == "offered" and result["grant_id"] is None
    assert not (root / "received").exists()
    assert not list(root.glob(".stk-peer-*"))
    assert not pair[1][2].sessions()
    assert status(pair, params)["operation"] is None
    assert store.manifest(params["transfer_id"]) == params["manifest"]


def test_real_chunks_fsync_receipts_full_sha_and_absent_directory_publication(pair):
    params, _, contents = offer(pair)
    control = accept_start(pair, params)
    send(pair, params, contents)
    complete = {**control, "operation_id": uid()}
    result = pair[4].call(pair[3], "files.complete", complete)
    validate_file_result("files.complete", result, params=complete, manifest=params["manifest"])
    assert result["state"] == "complete"
    for name, body in contents.items():
        assert (pair[5] / "received" / name).read_bytes() == body
    assert pair[4].call(pair[3], "files.complete", complete) == result
    assert status(pair, params, complete["operation_id"])["operation"]["state"] == "completed"
    assert pair[1][1].capabilities(pair[3]) == frozenset()


def test_wrong_chunk_offset_short_block_hash_and_file_never_advance(pair):
    params, _, _ = offer(pair)
    accept_start(pair, params)
    item = params["manifest"]["files"][0]
    for frame in (encode_data(params["transfer_id"], item["file_id"], 0, 1, b"a" * CHUNK_BYTES),
                  encode_data(params["transfer_id"], item["file_id"], 0, 0, b"short"),
                  encode_data(params["transfer_id"], uid(), 0, 0, b"a" * CHUNK_BYTES)):
        with pytest.raises(FileStoreError):
            pair[4].accept_data(pair[3], frame)
    assert status(pair, params)["files"][0]["committed_bytes"] == 0


def test_duplicate_durable_block_echoes_receipt_but_conflicting_bytes_rejected(pair):
    params, _, contents = offer(pair)
    accept_start(pair, params)
    item = params["manifest"]["files"][0]
    data = encode_data(params["transfer_id"], item["file_id"], 0, 0, contents[item["name"]][:CHUNK_BYTES])
    first = pair[4].accept_data(pair[3], data)
    assert pair[4].accept_data(pair[3], data) == first
    with pytest.raises(FileStoreError, match="unavailable"):
        pair[4].accept_data(pair[3], encode_data(params["transfer_id"], item["file_id"], 0, 0, b"x" * CHUNK_BYTES))
    assert status(pair, params)["files"][0]["committed_bytes"] == CHUNK_BYTES


def test_original_operation_reuse_conflicts_and_pending_offer_cannot_send(pair):
    params, result, _ = offer(pair)
    assert pair[4].call(pair[3], "files.offer", params) == result
    changed = {**params, "transfer_id": uid()}
    with pytest.raises(FileStoreError) as error:
        pair[4].call(pair[3], "files.offer", changed)
    assert error.value.code == "conflict"
    with pytest.raises((PeerDenied, FileStoreError)):
        pair[4].accept_data(pair[3], encode_data(params["transfer_id"], params["manifest"]["files"][0]["file_id"], 0, 0, b"x"))


def test_existing_destination_is_never_accepted_or_overwritten(pair):
    params, _, _ = offer(pair)
    destination = pair[5] / "received"
    destination.mkdir()
    (destination / "keep").write_text("original")
    with pytest.raises(FileStoreError) as error:
        pair[4].accept(uid(), pair[3], params["transfer_id"], params["operation_id"], destination)
    assert error.value.code == "conflict"
    assert (destination / "keep").read_text() == "original"
    assert not pair[1][2].sessions()


def test_data_after_session_revoke_rejected_without_next_byte(pair):
    params, _, contents = offer(pair)
    accept_start(pair, params)
    pair[1][2].revoke_session(uid(), params["session_id"])
    item = params["manifest"]["files"][0]
    with pytest.raises(PeerDenied):
        pair[4].accept_data(pair[3], encode_data(params["transfer_id"], item["file_id"], 0, 0, contents[item["name"]][:CHUNK_BYTES]))
    assert status(pair, params)["files"][0]["committed_bytes"] == 0


def test_unjournaled_fsynced_tail_needs_explicit_resume_and_is_not_acked(pair, monkeypatch):
    params, _, contents = offer(pair)
    control = accept_start(pair, params)
    store = pair[4]
    original = store._save
    def fail(db, row):
        if row["progress"][0]["committed_bytes"]:
            raise OSError("Synthetic journal failure after payload fsync")
        return original(db, row)
    monkeypatch.setattr(store, "_save", fail)
    item = params["manifest"]["files"][0]
    data = encode_data(params["transfer_id"], item["file_id"], 0, 0, contents[item["name"]][:CHUNK_BYTES])
    with pytest.raises(OSError):
        store.accept_data(pair[3], data)
    monkeypatch.setattr(store, "_save", original)
    assert status(pair, params)["files"][0]["committed_bytes"] == 0
    with pytest.raises(FileStoreError):
        store.accept_data(pair[3], data)
    resume = {**control, "operation_id": uid()}
    assert store.call(pair[3], "files.resume", resume)["state"] == "receiving"
    store.accept_data(pair[3], data)
    assert status(pair, params)["files"][0]["committed_bytes"] == CHUNK_BYTES


def test_corrupt_durable_prefix_blocks_resume(pair):
    params, _, contents = offer(pair)
    control = accept_start(pair, params)
    send(pair, params, contents)
    store = pair[4]
    with store._connect() as db:
        row = store._row(db, params["transfer_id"])
    staged = Path(row["target"]).parent / row["stage_name"] / params["manifest"]["files"][0]["name"]
    with staged.open("r+b") as stream:
        stream.write(b"changed")
    with pytest.raises(FileStoreError, match="prefix changed"):
        store.call(pair[3], "files.resume", {**control, "operation_id": uid()})
    assert not (pair[5] / "received").exists()


def test_published_but_lost_final_journal_is_uncertain_and_never_republished(pair, monkeypatch):
    params, _, contents = offer(pair)
    control = accept_start(pair, params)
    send(pair, params, contents)
    store, original = pair[4], pair[4]._finish
    def fail(db, row, method, request):
        if method == "files.complete":
            raise OSError("Synthetic failure after rename before final journal")
        return original(db, row, method, request)
    monkeypatch.setattr(store, "_finish", fail)
    complete = {**control, "operation_id": uid()}
    with pytest.raises(OSError):
        store.call(pair[3], "files.complete", complete)
    monkeypatch.setattr(store, "_finish", original)
    assert (pair[5] / "received" / "empty").is_file()
    observed = status(pair, params, complete["operation_id"])
    assert observed["state"] == "interrupted" and observed["operation"]["state"] == "uncertain"
    assert observed["completion"] is None
    with pytest.raises(FileStoreError, match="uncertain"):
        store.call(pair[3], "files.complete", complete)
    with pytest.raises(FileStoreError, match="uncertain"):
        store.call(pair[3], "files.resume", {**control, "operation_id": uid()})


def test_reopen_reads_original_status_but_does_not_start_or_publish(pair):
    params, _, _ = offer(pair)
    accept_start(pair, params)
    reopened = FileStore(pair[4].directory, pair[1][2])
    request = {key: params[key] for key in ("session_id", "transfer_id", "manifest_sha256")}
    request["operation_id"] = None
    assert reopened.call(pair[3], "files.status", request)["state"] == "receiving"
    assert not (pair[5] / "received").exists()


def test_reoffer_requires_explicit_accept_new_grant_and_resume_preserving_prefix(pair):
    host, receiver, hc, rc, store, root = pair
    params, _, contents = offer(pair)
    original = accept_start(pair, params)
    item = params["manifest"]["files"][0]
    first = encode_data(params["transfer_id"], item["file_id"], 0, 0, contents[item["name"]][:CHUNK_BYTES])
    store.accept_data(rc, first)
    renewed = host[2].host_session(uid(), receiver[0].info()["card"]["peer_id"], 300,
                                   context=hc, session_id=params["session_id"])["result"]["offer"]
    reoffer = {**params, "operation_id": uid(), "session_offer": renewed}
    result = store.call(rc, "files.offer", reoffer)
    assert result["state"] == "interrupted" and result["files"][0]["committed_bytes"] == CHUNK_BYTES
    with pytest.raises(FileStoreError):
        store.call(rc, "files.resume", {**original, "operation_id": uid()})
    accepted = store.accept(uid(), rc, params["transfer_id"], reoffer["operation_id"], root / "received")["result"]
    assert accepted["state"] == "interrupted" and accepted["grant_id"] != original["grant_id"]
    resume = {**original, "operation_id": uid(), "grant_id": accepted["grant_id"]}
    assert store.call(rc, "files.resume", resume)["files"][0]["committed_bytes"] == CHUNK_BYTES
    # Duplicate exact first block is harmless; the existing prefix is never reset.
    send(pair, params, contents)
    store.call(rc, "files.complete", {**resume, "operation_id": uid()})
    assert (root / "received" / item["name"]).read_bytes() == contents[item["name"]]


def test_reoffer_cannot_change_manifest_or_pins_and_local_target_is_frozen(pair):
    host, receiver, hc, rc, store, root = pair
    params, _, _ = offer(pair)
    accept_start(pair, params)
    renewed = host[2].host_session(uid(), receiver[0].info()["card"]["peer_id"], 300,
                                   context=hc, session_id=params["session_id"])["result"]["offer"]
    changed_manifest = {**params["manifest"], "source_revision": 2}
    bad = {**params, "operation_id": uid(), "session_offer": renewed,
           "manifest": changed_manifest, "manifest_sha256": manifest_sha256(changed_manifest)}
    with pytest.raises(FileStoreError):
        store.call(rc, "files.offer", bad)
    renewed_params = {**params, "operation_id": uid(), "session_offer": renewed}
    store.call(rc, "files.offer", renewed_params)
    with pytest.raises(FileStoreError, match="destination"):
        store.accept(uid(), rc, params["transfer_id"], renewed_params["operation_id"], root / "elsewhere")


@pytest.mark.parametrize("withdraw_at", ["before_session", "after_session"])
def test_local_revoke_during_accept_never_restores_the_original_grant(pair, monkeypatch, withdraw_at):
    params, _, _ = offer(pair, {"sample.bin": b"abc"})
    store, context, root = pair[4], pair[3], pair[5]
    operation = uid()
    original = store.pairing.accept_session
    calls = []

    def withdraw(*args, **kwargs):
        calls.append(True)
        if withdraw_at == "before_session":
            assert store.revoke(uid(), params["transfer_id"])["result"]["state"] == "cancelled"
        result = original(*args, **kwargs)
        if withdraw_at == "after_session":
            assert store.revoke(uid(), params["transfer_id"])["result"]["state"] == "cancelled"
        return result

    monkeypatch.setattr(store.pairing, "accept_session", withdraw)
    with pytest.raises(FileStoreError):
        store.accept(operation, context, params["transfer_id"], params["operation_id"], root / "received")
    assert store.get(params["transfer_id"])["state"] == "cancelled"
    assert store.get(params["transfer_id"])["grant_id"] is None
    # The persisted original intent stays uncertain; reopening/retrying it does
    # not perform a second approval or make a new grant.
    reopened = FileStore(store.directory, store.pairing)
    with pytest.raises(FileStoreError) as retry:
        reopened.accept(operation, context, params["transfer_id"], params["operation_id"], root / "received")
    assert retry.value.code == "unavailable" and calls == [True]
    control = {key: params[key] for key in ("session_id", "transfer_id", "manifest_sha256")}
    control.update(operation_id=uid(), grant_id=uid())
    with pytest.raises(FileStoreError):
        store.call(context, "files.start", control)
    item = params["manifest"]["files"][0]
    with pytest.raises(FileStoreError):
        store.accept_data(context, encode_data(params["transfer_id"], item["file_id"], 0, 0, b"abc"))
    assert store.get(params["transfer_id"])["files"][0]["committed_bytes"] == 0
    assert not (root / "received").exists() and not list(root.glob(".stk-peer-*"))


def test_local_revoke_retains_bytes_and_old_grant_cannot_restart(pair):
    params, _, contents = offer(pair)
    control = accept_start(pair, params)
    send(pair, params, contents)
    store, context = pair[4], pair[3]
    op = uid()
    revoked = store.revoke(op, params["transfer_id"])
    assert revoked["result"]["state"] == "cancelled"
    assert store.revoke(op, params["transfer_id"]) == revoked
    with pytest.raises(FileStoreError):
        store.call(context, "files.resume", {**control, "operation_id": uid()})
    with store._connect() as db:
        row = store._row(db, params["transfer_id"])
    assert (Path(row["target"]).parent / row["stage_name"] / "empty").is_file()


def test_new_destination_appearing_after_accept_is_preserved_as_uncertain_publish(pair):
    params, _, contents = offer(pair)
    control = accept_start(pair, params)
    send(pair, params, contents)
    destination = pair[5] / "received"
    destination.mkdir()
    (destination / "keep").write_text("other content")
    complete = {**control, "operation_id": uid()}
    with pytest.raises(FileExistsError):
        pair[4].call(pair[3], "files.complete", complete)
    assert (destination / "keep").read_text() == "other content"
    assert status(pair, params, complete["operation_id"])["operation"]["state"] == "uncertain"


def test_transfer_quota_rejection_does_not_poison_initial_schema(pair, monkeypatch):
    import suan.peer.file_store as module
    monkeypatch.setattr(module, "MAX_TRANSFERS", 0)
    with pytest.raises(FileStoreError) as error:
        offer(pair)
    assert error.value.code == "limit_exceeded"
    monkeypatch.setattr(module, "MAX_TRANSFERS", 128)
    params, result, _ = offer(pair)
    assert result["state"] == "offered" and status(pair, params)["state"] == "offered"


def test_file_only_authenticated_peer_uses_owner_bound_project_without_project_grant(pair):
    from suan.project import ProjectStore
    host, receiver, hc, _, _, root = pair
    project = ProjectStore.create(root / "source-project", "File-only source")
    binding = host[1].bind_project(project.directory)
    assert host[1].capabilities(hc) == frozenset()
    with host[2].peer_access(hc):
        observed = host[1].bound_project(binding["project_id"], binding["database_generation"])
        assert isinstance(observed, ProjectStore) and observed.info()["id"] == project.info()["id"]
    rebound = host[1].rebind_project(binding["project_id"], project.directory)
    # No project grant existed, so rebind need not invalidate the generic peer context.
    with host[2].peer_access(hc):
        with pytest.raises(PeerDenied):
            host[1].bound_project(binding["project_id"], binding["database_generation"])
        assert host[1].bound_project(binding["project_id"], rebound["database_generation"]).info()["id"] == binding["project_id"]
    assert host[1].capabilities(hc) == frozenset()


@pytest.mark.parametrize("method", ["files.start", "files.resume", "files.complete", "files.cancel"])
def test_identical_controls_recheck_original_operation_after_final_lease_race(pair, monkeypatch, method):
    params, _, contents = offer(pair)
    store, context = pair[4], pair[3]
    if method == "files.start":
        accepted = store.accept(uid(), context, params["transfer_id"], params["operation_id"], pair[5] / "received")["result"]
        request = {key: params[key] for key in ("session_id", "transfer_id", "manifest_sha256")}
        request.update(operation_id=uid(), grant_id=accepted["grant_id"])
    else:
        request = {**accept_start(pair, params), "operation_id": uid()}
        if method == "files.complete":
            send(pair, params, contents)
    private = "_start" if method in {"files.start", "files.resume"} else "_complete" if method == "files.complete" else "session_access"
    owner = store.pairing if method == "files.cancel" else store
    # Both real callers pass the initial lookup before either final acceptance.
    original = getattr(owner, private)
    barrier, first_done = threading.Barrier(2), threading.Event()
    results, errors = {}, {}
    def dispatch(*args, **kwargs):
        barrier.wait(5)
        if threading.current_thread().name == "second":
            assert first_done.wait(5)
            return original(*args, **kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(owner, private, dispatch)
    def run():
        name = threading.current_thread().name
        try:
            results[name] = store.call(context, method, request)
        except Exception as error:
            errors[name] = type(error).__name__
        finally:
            if name == "first":
                first_done.set()
    workers = [threading.Thread(target=run, name=name) for name in ("first", "second")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(8)
    assert not any(worker.is_alive() for worker in workers)
    assert not errors
    assert results["first"] == results["second"]
    assert results["second"]["operation"]["operation_id"] == request["operation_id"]


def test_resume_scan_releases_authority_and_file_journal_before_revoke(pair, monkeypatch):
    params, _, contents = offer(pair)
    request = {**accept_start(pair, params), "operation_id": uid()}
    store, context = pair[4], pair[3]
    item = params["manifest"]["files"][0]
    store.accept_data(context, encode_data(params["transfer_id"], item["file_id"], 0, 0,
                                          contents[item["name"]][:CHUNK_BYTES]))
    original = store._verify_prefix
    entered, release, revoked = threading.Event(), threading.Event(), threading.Event()
    failures = {}
    def scan(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "_verify_prefix", scan)
    def resume():
        try:
            store.call(context, "files.resume", request)
        except Exception as error:
            failures["resume"] = error
    def revoke():
        try:
            store.revoke(uid(), params["transfer_id"])
            revoked.set()
        except Exception as error:
            failures["revoke"] = error
    scanner = threading.Thread(target=resume)
    scanner.start()
    assert entered.wait(3)
    revoker = threading.Thread(target=revoke)
    revoker.start()
    try:
        assert revoked.wait(1), "A long prefix scan must not hold Authority or the journal transaction"
    finally:
        release.set()
        scanner.join(6)
        revoker.join(6)
    assert not scanner.is_alive() and not revoker.is_alive()
    assert "revoke" not in failures and isinstance(failures.get("resume"), FileStoreError)
    observed = status(pair, params, request["operation_id"])
    assert observed["state"] == "cancelled" and observed["operation"]["state"] == "uncertain"


@pytest.mark.parametrize("change", ["bytes", "journal"])
def test_resume_final_checkpoint_rejects_scan_to_commit_change_before_truncation(pair, monkeypatch, change):
    params, _, contents = offer(pair)
    request = {**accept_start(pair, params), "operation_id": uid()}
    store, context = pair[4], pair[3]
    item = params["manifest"]["files"][0]
    store.accept_data(context, encode_data(params["transfer_id"], item["file_id"], 0, 0,
                                          contents[item["name"]][:CHUNK_BYTES]))
    with store._connect() as db:
        row = store._row(db, params["transfer_id"])
    path = Path(row["target"]).parent / row["stage_name"] / item["name"]
    with path.open("ab") as stream:
        stream.write(b"uncommitted tail")
    original = store._verify_prefix
    def scan(*args, **kwargs):
        checkpoint = original(*args, **kwargs)
        if change == "bytes":
            with path.open("r+b") as stream:
                stream.write(b"modified")
        else:
            with sqlite3.connect(store.path) as db:
                db.execute("UPDATE chunks SET sha256=? WHERE transfer_id=? AND file_id=?",
                           ("e" * 64, params["transfer_id"], item["file_id"]))
        return checkpoint
    monkeypatch.setattr(store, "_verify_prefix", scan)
    with pytest.raises(FileStoreError):
        store.call(context, "files.resume", request)
    assert path.stat().st_size == CHUNK_BYTES + len(b"uncommitted tail")
    observed = status(pair, params, request["operation_id"])
    assert observed["state"] == "interrupted" and observed["operation"]["state"] == "uncertain"


def test_resume_actual_prefix_read_holds_neither_authority_nor_files_transaction(pair, monkeypatch):
    params, _, contents = offer(pair)
    request = {**accept_start(pair, params), "operation_id": uid()}
    store, context = pair[4], pair[3]
    item = params["manifest"]["files"][0]
    store.accept_data(context, encode_data(params["transfer_id"], item["file_id"], 0, 0,
                                          contents[item["name"]][:CHUNK_BYTES]))
    entered, release, revoked = threading.Event(), threading.Event(), threading.Event()
    original = store._file
    failures = {}
    class BlockRead:
        def __init__(self, stream):
            self.stream = stream
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def read(self, length):
            entered.set()
            assert release.wait(5)
            return self.stream.read(length)
    @contextmanager
    def file_stream(stage, name, **kwargs):
        with original(stage, name, **kwargs) as stream:
            yield BlockRead(stream) if kwargs.get("write") is False and name == item["name"] else stream
    monkeypatch.setattr(store, "_file", file_stream)
    def resume():
        try:
            store.call(context, "files.resume", request)
        except Exception as error:
            failures["resume"] = error
    def revoke():
        try:
            store.revoke(uid(), params["transfer_id"])
            revoked.set()
        except Exception as error:
            failures["revoke"] = error
    reader = threading.Thread(target=resume)
    reader.start()
    assert entered.wait(3)
    writer = threading.Thread(target=revoke)
    writer.start()
    try:
        assert revoked.wait(1), "Durable revoke must commit while prefix bytes are being read"
    finally:
        release.set()
        reader.join(6)
        writer.join(6)
    assert not reader.is_alive() and not writer.is_alive()
    assert "revoke" not in failures and isinstance(failures.get("resume"), FileStoreError)


def test_superseding_resume_prevents_late_original_scan_from_overwriting_receipt(pair, monkeypatch):
    params, _, contents = offer(pair)
    control = accept_start(pair, params)
    store, context = pair[4], pair[3]
    first, second = {**control, "operation_id": uid()}, {**control, "operation_id": uid()}
    item = params["manifest"]["files"][0]
    store.accept_data(context, encode_data(params["transfer_id"], item["file_id"], 0, 0,
                                          contents[item["name"]][:CHUNK_BYTES]))
    original = store._verify_prefix
    entered, release = threading.Event(), threading.Event()
    failures = []
    def scan(*args, **kwargs):
        if threading.current_thread().name == "older-resume":
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "_verify_prefix", scan)
    def older():
        try:
            store.call(context, "files.resume", first)
        except Exception as error:
            failures.append(error)
    worker = threading.Thread(target=older, name="older-resume")
    worker.start()
    assert entered.wait(3)
    try:
        completed = store.call(context, "files.resume", second)
    finally:
        release.set()
        worker.join(6)
    assert not worker.is_alive() and len(failures) == 1 and isinstance(failures[0], FileStoreError)
    assert completed["operation"]["operation_id"] == second["operation_id"]
    assert completed["files"][0]["committed_bytes"] == CHUNK_BYTES
    assert status(pair, params, first["operation_id"])["operation"]["state"] == "uncertain"
    assert status(pair, params, second["operation_id"])["operation"]["state"] == "completed"
