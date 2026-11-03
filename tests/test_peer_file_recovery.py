"""Source recovery adopts only a retained exact completed original operation."""
from uuid import uuid5, NAMESPACE_URL

import pytest

from test_peer_file_store import pair, uid
from test_peer_files import source_project, approve, production_endpoints
from test_peer_endpoint import links, native_helper
from suan.peer.files import FileSender, FileSendUncertain
from suan.peer.file_protocol import FileProtocolError


def complete_id(send_id):
    return str(uuid5(NAMESPACE_URL, "stk.peer.file.send.complete/1/" + send_id))


def test_lost_completion_is_adopted_only_explicitly_without_republish_or_regrant(pair):
    source = source_project(pair);sender = source[3]
    link, offered, accepted = approve(pair, source)
    def lose(method, *_):
        if method == "files.complete":raise ConnectionError("Synthetic lost completion reply")
    link.after_control = lose;send_id = uid()
    with pytest.raises(FileSendUncertain):
        sender.send(send_id, pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert (pair[5] / "received/数据/selected.bin").read_bytes() == source[5]
    assert sender.status(offered["transfer_id"])["state"] == "interrupted"
    original = sender.operation(complete_id(send_id))
    assert original["receipt"] is None
    before = len(link.controls), len(link.blocks)
    sender = FileSender(sender.directory, pair[0][2])
    assert sender.status(offered["transfer_id"])["state"] == "interrupted"
    assert before == (len(link.controls), len(link.blocks))
    sender.revoke(uid(), offered["transfer_id"])
    link.after_control = None;recover_id = uid()
    recovered = sender.recover(recover_id, pair[2], link, send_id)
    assert recovered["recovered"] and recovered["completion"]["state"] == "complete"
    status = sender.status(offered["transfer_id"])
    assert status["state"] == "complete" and not status["active"]
    assert len(link.controls) == before[0] + 1 and link.controls[-1][0] == "files.status"
    assert len(link.blocks) == before[1]
    assert sender.recover(recover_id, pair[2], link, send_id) == recovered
    assert len(link.controls) == before[0] + 1


def test_completed_control_with_lost_local_send_commit_recovers_without_any_network(pair, monkeypatch):
    source = source_project(pair);sender = source[3]
    link, offered, accepted = approve(pair, source)
    put = sender._put
    def fail_final(db, table, identity, value):
        if table == "sends" and value.get("result") is not None:
            raise OSError("Synthetic final source journal fault")
        return put(db, table, identity, value)
    monkeypatch.setattr(sender, "_put", fail_final)
    send_id = uid()
    with pytest.raises(OSError):
        sender.send(send_id, pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert sender.operation(complete_id(send_id))["receipt"]["state"] == "complete"
    monkeypatch.setattr(sender, "_put", put)
    before = len(link.controls), len(link.blocks)
    result = sender.recover(uid(), pair[2], link, send_id)
    assert result["recovered"] and sender.status(offered["transfer_id"])["state"] == "complete"
    assert before == (len(link.controls), len(link.blocks))


def test_unknown_publication_does_not_become_complete_from_visible_files(pair, monkeypatch):
    source = source_project(pair);sender = source[3]
    link, offered, accepted = approve(pair, source)
    finish = pair[4]._finish
    def lose(db, row, method, params):
        if method == "files.complete":raise OSError("Synthetic receiver post-rename journal fault")
        return finish(db, row, method, params)
    monkeypatch.setattr(pair[4], "_finish", lose)
    send_id = uid()
    with pytest.raises(FileSendUncertain):
        sender.send(send_id, pair[2], link, offered["transfer_id"], accepted["grant_id"])
    assert (pair[5] / "received/数据/selected.bin").read_bytes() == source[5]
    before = len(link.controls), len(link.blocks)
    result = sender.recover(uid(), pair[2], link, send_id)
    assert not result["recovered"] and result["completion"] is None
    assert sender.status(offered["transfer_id"])["state"] == "interrupted"
    assert len(link.controls) == before[0] + 1 and len(link.blocks) == before[1]


def test_mismatched_original_completion_proof_cannot_be_adopted(pair):
    source = source_project(pair);sender = source[3]
    link, offered, accepted = approve(pair, source)
    def lose(method, *_):
        if method == "files.complete":raise ConnectionError("Synthetic lost completion")
    link.after_control = lose;send_id = uid()
    with pytest.raises(FileSendUncertain):
        sender.send(send_id, pair[2], link, offered["transfer_id"], accepted["grant_id"])
    def corrupt(method, _params, result):
        if method == "files.status":result["operation"]["request_sha256"] = "a" * 64
    link.after_control = corrupt
    with pytest.raises(FileProtocolError):
        sender.recover(uid(), pair[2], link, send_id)
    assert sender.status(offered["transfer_id"])["state"] == "interrupted"


def test_native_disconnect_reopen_reauthenticate_reapprove_and_explicit_resume(pair, links):
    source = source_project(pair);sender, plan, binding = source[3], source[4], source[2]
    with production_endpoints(pair, links("udp")) as peers:
        hc, rc = [p.authenticated_context for p in peers]
        session = pair[0][2].host_session(uid(), pair[1][0].info()["card"]["peer_id"], 300, context=hc)["result"]["offer"]
        offered = sender.offer(uid(), hc, peers[0], plan["plan_id"], binding["database_generation"], session["session_id"])
        accepted = pair[4].accept(uid(), rc, offered["transfer_id"], offered["operation"]["operation_id"], pair[5] / "received")["result"]
        original_send = peers[0].send_file_data
        def lose(frame, **kwargs):
            original_send(frame, **kwargs)
            peers[0].close()
            raise ConnectionError("Synthetic loss after receiver's durable ACK")
        peers[0].send_file_data = lose
        send_id = uid()
        with pytest.raises(ConnectionError):
            sender.send(send_id, hc, peers[0], offered["transfer_id"], accepted["grant_id"])
    sender = FileSender(sender.directory, pair[0][2])
    assert sender.status(offered["transfer_id"])["progress"][0]["committed_bytes"] == 0
    assert not (pair[5] / "received").exists()
    with production_endpoints(pair, links("tcp")) as peers:
        hc2, rc2 = [p.authenticated_context for p in peers]
        observed = sender.query(hc2, peers[0], offered["transfer_id"], operation_id=send_id)
        assert observed["files"][0]["committed_bytes"] > 0
        # A metadata query never adopts this prefix or rebinds old approval.
        assert sender.status(offered["transfer_id"])["progress"][0]["committed_bytes"] == 0
        pair[0][2].host_session(uid(), pair[1][0].info()["card"]["peer_id"], 300, context=hc2, session_id=session["session_id"])
        newer = sender.offer(uid(), hc2, peers[0], plan["plan_id"], binding["database_generation"],
                             session["session_id"], transfer_id=offered["transfer_id"])
        accepted2 = pair[4].accept(uid(), rc2, newer["transfer_id"], newer["operation"]["operation_id"], pair[5] / "received")["result"]
        assert accepted2["grant_id"] != accepted["grant_id"]
        completed = sender.send(uid(), hc2, peers[0], offered["transfer_id"], accepted2["grant_id"], resume=True)
        assert completed["state"] == "complete"
        assert (pair[5] / "received/数据/selected.bin").read_bytes() == source[5]
