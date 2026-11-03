"""Production sender/receiver journals with real identities and frozen files.

ApplicationLink omits transport intentionally; separate native cases below use
actual helper pipes, mutual channel authentication and the same production APIs.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import tracemalloc

import pytest

from test_peer_file_store import pair, uid
from test_peer_endpoint import links, native_helper
from suan.project import ProjectStore
from suan.peer.authority import PeerDenied
from suan.peer.endpoint import PeerEndpoint
from suan.peer.file_store import FileStore, FileStoreError
from suan.peer.files import FileSender, ReceiverAdapter, FileSendError, FileSendUncertain
from suan.peer.file_protocol import CHUNK_BYTES, FileProtocolError, decode_frame


class ApplicationLink:
    def __init__(self, context, remote_context, receiver):
        self.authenticated_context, self.remote_context = context, remote_context
        self.adapter, self.controls, self.blocks = ReceiverAdapter(receiver), [], []
        self.after_control = self.after_data = None

    def request(self, method, params, **_):
        self.controls.append((method, params))
        result, _manifest = self.adapter.call(self.remote_context, method, params)
        if self.after_control:
            self.after_control(method, params, result)
        return result

    def send_file_data(self, frame, **_):
        self.blocks.append(frame)
        receipt = decode_frame(self.adapter.receive_frame(self.remote_context, frame))
        return self.after_data(frame, receipt) if self.after_data else receipt


def source_project(pair, *, size=2 * CHUNK_BYTES + 17):
    root = pair[5]
    project = ProjectStore.create(root / "project", "Explicit source")
    data = project.directory / "selected.bin"
    # Deterministic independent bytes, including every byte value.
    body = (bytes(range(256)) * ((size + 255) // 256))[:size]
    data.write_bytes(body)
    empty = project.directory / "empty.txt"; empty.write_bytes(b"")
    ids = project.files.index([str(data), str(empty)], expected_revision=0)["record_ids"]
    snapshot = project.snapshots.capture(ids, expected_revision=1)["snapshot"]
    binding = pair[0][1].bind_project(project.directory)
    sender = FileSender(root / "sender", pair[0][2])
    before_prepare = project.info()
    plan = sender.prepare(uid(), project, snapshot["id"], ids, names={ids[0]: "数据/selected.bin"})
    return project, snapshot, binding, sender, plan, body, before_prepare


def approve(pair, source, link=None):
    project, snapshot, binding, sender, plan, body = source[:6]
    host, receiver, hc, rc, store, root = pair
    link = ApplicationLink(hc, rc, store) if link is None else link
    session = host[2].host_session(uid(), receiver[0].info()["card"]["peer_id"], 300, context=hc)["result"]["offer"]
    offered = sender.offer(uid(), hc, link, plan["plan_id"], binding["database_generation"], session["session_id"])
    accepted = store.accept(uid(), rc, offered["transfer_id"], offered["operation"]["operation_id"], root / "received")["result"]
    return link, offered, accepted


def test_preparation_and_reopen_are_passive_and_public_receipts_have_no_source_paths(pair):
    sender = FileSender(pair[5] / "passive", pair[0][2])
    assert not sender.directory.exists()
    assert sender.list() == [] and pair[4].list() == []
    assert not sender.directory.exists() and not pair[4].directory.exists()
    with pytest.raises(FileSendError):
        sender.status(uid())
    assert not sender.directory.exists()
    source = source_project(pair)
    project, snapshot, binding, sender, plan, _ = source[:6]
    assert sender.manifest(plan["plan_id"]) == plan["manifest"]
    assert str(project.directory) not in str(plan)
    assert not (pair[5] / "received").exists()
    assert not pair[0][2].sessions()
    reopened = FileSender(sender.directory, pair[0][2])
    assert reopened.manifest(plan["plan_id"]) == plan["manifest"]
    assert project.info() == source[6]


def test_local_transfer_pages_detach_safe_history_and_never_create_targets_or_approve(pair):
    source = source_project(pair);sender = source[3]
    link, offered, accepted = approve(pair, source)
    before = len(link.controls), len(link.blocks)
    sent, received = sender.list(limit=1), pair[4].list(limit=1)
    assert len(sent) == len(received) == 1
    assert sent[0] == sender.status(offered["transfer_id"])
    assert received[0] == pair[4].get(offered["transfer_id"])
    review = pair[4].reviewed_offer(offered["transfer_id"])
    assert review["offer_operation_id"] == offered["operation"]["operation_id"]
    assert review["manifest"] == sender.transfer_manifest(offered["transfer_id"]) == source[4]["manifest"]
    assert review["session_offer"]["session_id"] == offered["session_id"]
    assert str(pair[5]) not in str(review)
    assert sender.list(offset=1) == pair[4].list(offset=1) == []
    assert str(pair[5]) not in str((sent, received))
    assert all(key not in str((sent, received)) for key in ('source_directory', 'stage_name', 'nonce', 'parent_identity'))
    sent[0]["state"] = received[0]["state"] = "corrupted caller copy"
    assert sender.list()[0]["state"] == "offered" and pair[4].list()[0]["state"] == "accepted"
    assert before == (len(link.controls), len(link.blocks))
    assert not (pair[5] / "received").exists()
    for params in ({"offset": True}, {"limit": 0}, {"limit": 51}, {"offset": -1}):
        with pytest.raises(FileProtocolError):sender.list(**params)
        with pytest.raises(FileProtocolError):pair[4].list(**params)


def test_real_production_multifile_full_hash_publication_and_old_send_never_replays(pair):
    source = source_project(pair); sender, body = source[3], source[5]
    link, offered, accepted = approve(pair, source)
    # Editing the working file does not replace the selected frozen content.
    (source[0].directory / "selected.bin").write_bytes(b"new working copy")
    op = uid()
    result = sender.send(op, pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert result["state"] == "complete" and len(link.blocks) == 3
    assert (pair[5] / "received/数据/selected.bin").read_bytes() == body
    assert (pair[5] / "received/empty.txt").read_bytes() == b""
    assert result["files"][0]["verified_sha256"] == hashlib.sha256(body).hexdigest()
    counts = len(link.controls), len(link.blocks)
    assert sender.send(op, pair[2], link, offered["transfer_id"], accepted["grant_id"]) == result
    assert counts == (len(link.controls), len(link.blocks))
    assert sender.status(offered["transfer_id"])["state"] == "complete"
    assert not pair[0][1].capabilities(pair[2])


def test_lost_offer_preserves_original_id_and_queries_cannot_send_or_accept(pair):
    source = source_project(pair); sender, plan, binding = source[3], source[4], source[2]
    link = ApplicationLink(pair[2], pair[3], pair[4])
    session = pair[0][2].host_session(uid(), pair[1][0].info()["card"]["peer_id"], 300, context=pair[2])["result"]["offer"]
    def lost(*_): raise ConnectionError("Synthetic lost reply")
    link.after_control = lost; op = uid()
    with pytest.raises(FileSendUncertain) as caught:
        sender.offer(op, pair[2], link, plan["plan_id"], binding["database_generation"], session["session_id"])
    transfer = caught.value.transfer_id
    assert sender.operation(op)["receipt"] is None
    link.after_control = None
    with pytest.raises(FileSendUncertain):
        sender.offer(op, pair[2], link, plan["plan_id"], binding["database_generation"], session["session_id"])
    assert len(link.controls) == 1
    observed = sender.query(pair[2], link, transfer, operation_id=op)
    assert observed["operation"]["state"] == "completed" and observed["state"] == "offered"
    assert sender.operation(op)["receipt"] is None
    assert not link.blocks and not pair[1][2].sessions()
    assert not (pair[5] / "received").exists()


@pytest.mark.parametrize("loss", ["start", "data"])
def test_uncertain_send_reopens_read_only_then_explicit_resume_reconciles_prefix(pair, loss):
    source = source_project(pair); sender = source[3]
    link, offered, accepted = approve(pair, source)
    if loss == "start":
        def lose(method, *_):
            if method == "files.start": raise ConnectionError("Synthetic lost start receipt")
        link.after_control = lose
    else:
        def lose(*_): raise ConnectionError("Synthetic lost DATA receipt")
        link.after_data = lose
    original = uid()
    with pytest.raises((FileSendUncertain, ConnectionError)):
        sender.send(original, pair[2], link, offered["transfer_id"], accepted["grant_id"])
    before = len(link.controls), len(link.blocks)
    sender = FileSender(sender.directory, pair[0][2])
    assert sender.status(offered["transfer_id"])["state"] == "interrupted"
    with pytest.raises(FileSendUncertain):
        sender.send(original, pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert before == (len(link.controls), len(link.blocks))
    link.after_control = link.after_data = None
    result = sender.send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"], resume=True)
    assert result["state"] == "complete"
    assert [f.offset for f in link.blocks] == [0, CHUNK_BYTES, 2 * CHUNK_BYTES]
    assert (pair[5] / "received/数据/selected.bin").read_bytes() == source[5]


def test_revoke_during_receipt_wait_allows_current_block_but_denies_next(pair):
    source = source_project(pair); sender = source[3]
    link, offered, accepted = approve(pair, source)
    def withdraw(_frame, receipt):
        sender.revoke(uid(), offered["transfer_id"])
        return receipt
    link.after_data = withdraw
    with pytest.raises(FileSendError) as error:
        sender.send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert error.value.code == "forbidden" and len(link.blocks) == 1
    assert sender.status(offered["transfer_id"])["state"] == "cancelled"
    assert not (pair[5] / "received").exists()


def test_source_replacement_after_first_receipt_never_sends_replaced_private_bytes(pair):
    source = source_project(pair); sender = source[3]
    link, offered, accepted = approve(pair, source)
    path = Path(source[0].snapshots.resolve(source[1]["id"], source[4]["manifest"]["files"][0]["file_id"])["path"])
    def change(_frame, receipt):
        with path.open("r+b") as stream:
            stream.seek(CHUNK_BYTES);stream.write(b"do not send this replacement")
        return receipt
    link.after_data = change
    with pytest.raises(FileSendError, match="Frozen source"):
        sender.send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert len(link.blocks) == 1 and not (pair[5] / "received").exists()


def test_wrong_receipt_stays_pending_and_no_false_progress(pair):
    source = source_project(pair); sender = source[3]
    link, offered, accepted = approve(pair, source)
    link.after_data = lambda _f, receipt: replace(receipt, sha256="a" * 64)
    with pytest.raises(FileProtocolError):
        sender.send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert sender.status(offered["transfer_id"])["progress"][0]["committed_bytes"] == 0
    assert not (pair[5] / "received").exists()


def test_approved_context_cannot_drive_another_connection_even_to_same_peer(pair):
    source = source_project(pair);link, offered, accepted = approve(pair, source)
    link.authenticated_context = object()
    with pytest.raises(FileSendError) as error:
        source[3].send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert error.value.code == "forbidden" and not link.blocks


def test_project_rebind_during_wait_denies_next_block_without_project_read_grant(pair):
    source = source_project(pair);sender = source[3]
    link, offered, accepted = approve(pair, source)
    def rebind(_frame, receipt):
        pair[0][1].rebind_project(source[0].info()["id"], source[0].directory)
        return receipt
    link.after_data = rebind
    with pytest.raises(PeerDenied):
        sender.send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert len(link.blocks) == 1
    assert not pair[0][1].capabilities(pair[2])


def test_explicit_remote_cancel_withdraws_locally_and_never_resends_old_operation(pair):
    source = source_project(pair);sender = source[3]
    link, offered, accepted = approve(pair, source)
    op = uid()
    result = sender.cancel(op, pair[2], link, offered["transfer_id"], grant_id=accepted["grant_id"])
    assert result["state"] == "cancelled" and not sender.status(offered["transfer_id"])["active"]
    before = len(link.controls)
    assert sender.cancel(op, pair[2], link, offered["transfer_id"], grant_id=accepted["grant_id"]) == result
    assert len(link.controls) == before and not link.blocks
    with pytest.raises(FileSendError):
        sender.send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"])


def test_new_host_approval_cannot_implicitly_renew_an_already_running_send(pair):
    source = source_project(pair); sender, binding, plan = source[3], source[2], source[4]
    link, offered, accepted = approve(pair, source);fresh = []
    def reapprove(_frame, receipt):
        link.after_data = None
        pair[0][2].host_session(uid(), pair[1][0].info()["card"]["peer_id"], 300,
                              context=pair[2], session_id=offered["session_id"])
        newer = sender.offer(uid(), pair[2], link, plan["plan_id"], binding["database_generation"],
                             offered["session_id"], transfer_id=offered["transfer_id"])
        fresh.append(pair[4].accept(uid(), pair[3], newer["transfer_id"], newer["operation"]["operation_id"],
                                   pair[5] / "received")["result"])
        return receipt
    link.after_data = reapprove
    with pytest.raises(FileSendError) as error:
        sender.send(uid(), pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert error.value.code == "forbidden" and len(link.blocks) == 1
    assert fresh[0]["grant_id"] != accepted["grant_id"]
    result = sender.send(uid(), pair[2], link, offered["transfer_id"], fresh[0]["grant_id"], resume=True)
    assert result["state"] == "complete"
    assert [f.offset for f in link.blocks] == [0, CHUNK_BYTES, 2 * CHUNK_BYTES]


@contextmanager
def production_endpoints(pair, transports):
    adapters = [ReceiverAdapter(FileStore(pair[5] / "host-receives", pair[0][2])), ReceiverAdapter(pair[4])]
    peers = []
    for i in range(2):
        own, remote = pair[i], pair[1-i]
        peers.append(PeerEndpoint(transports[i], own[1], public_key=bytes.fromhex(own[0].info()["card"]["public_key"]),
            sign=own[0].signer(remote[1].owner_id), remote_peer_id=remote[0].info()["card"]["peer_id"],
            remote_owner_id=remote[1].owner_id, file_adapter=adapters[i]))
    try:
        with ThreadPoolExecutor(2) as pool:
            pending = [pool.submit(peer.start, timeout=10) for peer in peers]
            for future in pending:future.result(timeout=12)
        yield peers
    finally:
        for peer in peers:peer.close()


@pytest.mark.parametrize("route", ["udp", "tcp"])
def test_native_production_files_with_persistent_identities_sessions_and_receipts(pair, links, route):
    source = source_project(pair, size=CHUNK_BYTES + 29)
    with production_endpoints(pair, links(route)) as peers:
        host_context, recipient_context = [p.authenticated_context for p in peers]
        host, receiver = pair[:2];sender, plan, binding = source[3], source[4], source[2]
        session = host[2].host_session(uid(), receiver[0].info()["card"]["peer_id"], 300, context=host_context)["result"]["offer"]
        offered = sender.offer(uid(), host_context, peers[0], plan["plan_id"], binding["database_generation"], session["session_id"])
        accepted = pair[4].accept(uid(), recipient_context, offered["transfer_id"], offered["operation"]["operation_id"], pair[5] / "received")["result"]
        result = sender.send(uid(), host_context, peers[0], offered["transfer_id"], accepted["grant_id"])
        assert result["state"] == "complete"
        assert (pair[5] / "received/数据/selected.bin").read_bytes() == source[5]
        assert not host[1].capabilities(host_context) and not receiver[1].capabilities(recipient_context)


def test_native_large_file_exceeds_control_identity_budget_with_bounded_memory(pair, links):
    project = ProjectStore.create(pair[5] / "large-project", "Large immutable source")
    path = project.directory / "large.bin"
    block = bytes(range(256)) * (CHUNK_BYTES // 256)
    expected = hashlib.sha256()
    with path.open("wb") as stream:
        for _ in range(4097):
            stream.write(block); expected.update(block)
        stream.write(b"last explicit block"); expected.update(b"last explicit block")
    ids = project.files.index([str(path)], expected_revision=0)["record_ids"]
    snapshot = project.snapshots.capture(ids, expected_revision=1)["snapshot"]
    binding = pair[0][1].bind_project(project.directory)
    sender = FileSender(pair[5] / "sender", pair[0][2])
    plan = sender.prepare(uid(), project, snapshot["id"], ids)
    with production_endpoints(pair, links("udp")) as peers:
        hc, rc = [p.authenticated_context for p in peers]
        session = pair[0][2].host_session(uid(), pair[1][0].info()["card"]["peer_id"], 300, context=hc)["result"]["offer"]
        offered = sender.offer(uid(), hc, peers[0], plan["plan_id"], binding["database_generation"], session["session_id"])
        accepted = pair[4].accept(uid(), rc, offered["transfer_id"], offered["operation"]["operation_id"], pair[5] / "received")["result"]
        tracemalloc.start()
        try:
            result = sender.send(uid(), hc, peers[0], offered["transfer_id"], accepted["grant_id"])
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert result["state"] == "complete"
        assert result["files"][0]["next_sequence"] == 4098
        assert peers[0]._request_count < 10 and peers[1]._request_count < 10
        assert peak < 32 * 1024**2, "Python allocations must not scale with the 240MiB file"
    actual = hashlib.sha256()
    with (pair[5] / "received/large.bin").open("rb") as stream:
        while data := stream.read(1024**2):actual.update(data)
    assert actual.hexdigest() == expected.hexdigest() == result["files"][0]["verified_sha256"]
    with sqlite3.connect(sender.path) as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 4098
    with sqlite3.connect(pair[4].path) as db:
        assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == 4098
