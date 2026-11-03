"""File endpoint seams, actual mutual auth, bounded disk work and durable ACKs.

The test adapter authorizes identity only and performs explicit real fsyncs. It
does not stand in for the production session/grant/FileStore acceptance suite.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
import os
from queue import Empty, Queue
import threading
import time

import pytest

from test_peer_endpoint import sides, links, native_helper
from test_peer_file_protocol import (FILE, TRANSFER, OPERATION, SESSION, PROJECT,
                                     manifest, params as file_params, result as file_result)
from suan.peer.endpoint import (PeerEndpoint, PeerFileCallUncertain,
                                PeerFileDataUncertain, MAX_CONNECTION_REQUESTS)
from suan.peer.authority import PeerDenied
from suan.peer.file_protocol import (DATA, FILE_METHODS, FileProtocolError,
                                     decode_frame, encode_data, encode_frame,
                                     encode_receipt, request_sha256)
from suan.peer.protocol import BASE_METHODS, PeerProtocolError
from suan.peer.transport import TransportError


class MemoryTransport:
    """Two independent queues; transport delivery never asserts file durability."""
    channel_binding = "b" * 64

    def __init__(self):
        self.control, self.blob = Queue(), Queue()
        self.closed = False
        self.blob_hook = None

    def wait_ready(self, **_):
        if self.closed:
            raise TransportError("Closed test transport")
        return {}

    def send_control(self, raw, **_):
        self.wait_ready()
        self.peer.control.put(raw)

    def send_blob_chunk(self, raw, **_):
        self.wait_ready()
        if self.blob_hook is None:
            self.peer.blob.put(raw)
        else:
            self.blob_hook(raw, self.peer.blob)

    def receive(self, queue, timeout):
        self.wait_ready()
        try:
            value = queue.get(timeout=timeout)
        except Empty:
            raise TimeoutError from None
        if value is None:
            raise TransportError("Closed test transport")
        return value

    def recv_control(self, *, timeout):
        return self.receive(self.control, timeout)

    def recv_blob_chunk(self, *, timeout):
        return self.receive(self.blob, timeout)

    def close(self):
        self.closed = True
        self.control.put(None); self.blob.put(None)


class DurableAdapter:
    def __init__(self, authority, directory):
        self.authority, self.directory = authority, directory
        self.directory.mkdir()
        self.trace = []
        self.entered = threading.Event()
        self.release = threading.Event(); self.release.set()
        self.control_reply = None
        self.effects = []
        self.enabled = True

    def capabilities(self, context):
        with self.authority.peer_access(context):
            return {name: 1 for name in FILE_METHODS} if self.enabled else {}

    def call(self, context, method, params):
        with self.authority.peer_access(context):
            self.effects.append((method, deepcopy(params)))
            result = file_result(method, params)
            if self.control_reply is not None:
                result = self.control_reply(method, params, result)
            return result, manifest()

    def receive_frame(self, context, data):
        with self.authority.peer_access(context):
            self.entered.set()
            assert self.release.wait(5), "Test disk gate must be explicitly released"
            path = self.directory / (data.transfer_id + ".partial")
            with path.open("wb") as stream:
                stream.write(data.body); stream.flush(); os.fsync(stream.fileno())
            self.trace.append((data.transfer_id, "data_fsynced"))
            with (self.directory / (data.transfer_id + ".journal")).open("w") as stream:
                json.dump({"file_id": data.file_id, "bytes": data.length,
                           "sha256": data.sha256}, stream)
                stream.flush(); os.fsync(stream.fileno())
            self.trace.append((data.transfer_id, "journal_fsynced"))
        return decode_frame(encode_receipt(data))


@contextmanager
def endpoints(sides, tmp_path, *, native=None, enabled=(True, True), available=(True, True)):
    if native is None:
        transports = [MemoryTransport(), MemoryTransport()]
        transports[0].peer, transports[1].peer = transports[1], transports[0]
    else:
        transports = native
    adapters = [DurableAdapter(side.authority, tmp_path / ("files-" + str(index)))
                if enabled[index] else None for index, side in enumerate(sides)]
    for adapter, value in zip(adapters, available):
        if adapter is not None:
            adapter.enabled = value
    peers = [PeerEndpoint(transport, side.authority, public_key=side.public, sign=side.key.sign,
                          remote_peer_id=remote.peer_id, remote_owner_id=remote.authority.owner_id,
                          file_adapter=adapter)
             for transport, side, remote, adapter in zip(transports, sides, sides[::-1], adapters)]
    try:
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(peer.start, timeout=10) for peer in peers]
            for future in futures:
                future.result(timeout=12)
        yield peers, adapters, transports
    finally:
        for adapter in adapters:
            if adapter is not None:
                adapter.release.set()
        for peer in peers:
            peer.close()


def data(transfer=TRANSFER):
    return decode_frame(encode_data(transfer, FILE, 0, 0, b"abc"))


def test_no_installed_adapter_means_no_optional_advertisement_or_blob_reader(sides, tmp_path):
    with endpoints(sides, tmp_path, enabled=(True, False)) as (peers, _, _):
        assert not FILE_METHODS & peers[0].capabilities.keys()
        assert peers[0]._file_reader is None and peers[1]._file_reader is None
        with pytest.raises(PeerProtocolError) as error:
            peers[0].request("files.offer", file_params("files.offer"))
        assert error.value.code == "unsupported"


def test_authenticated_context_is_exact_opaque_identity_only_while_ready_and_open(sides, tmp_path):
    own, remote = sides
    passive = PeerEndpoint(MemoryTransport(), own.authority, public_key=own.public, sign=own.key.sign,
                           remote_peer_id=remote.peer_id, remote_owner_id=remote.authority.owner_id)
    with pytest.raises(PeerProtocolError):
        _ = passive.authenticated_context
    passive.close()
    with endpoints(sides, tmp_path) as (peers, _, _):
        context = peers[0].authenticated_context
        assert context is peers[0]._context and context is peers[0].authenticated_context
        assert context is not peers[1].authenticated_context
        peers[0].close()
        with pytest.raises(PeerProtocolError):
            _ = peers[0].authenticated_context


def test_explicit_later_negotiation_starts_exactly_one_reader_for_newly_authorized_files(sides, tmp_path):
    with endpoints(sides, tmp_path, available=(False, False)) as (peers, adapters, _):
        assert all(peer._file_reader is None for peer in peers)
        for adapter in adapters:
            adapter.enabled = True
        offered = {"protocols": [1], "capabilities": {name: 1 for name in BASE_METHODS | FILE_METHODS}}
        for peer in peers:
            assert FILE_METHODS <= peer.request("peer.hello", offered)["capabilities"].keys()
        readers = [peer._file_reader for peer in peers]
        for peer in peers:
            peer.request("peer.hello", offered)
        assert readers == [peer._file_reader for peer in peers]
        assert peers[0].send_file_data(data(), timeout=2).length == 3
        assert peers[1].send_file_data(data(PROJECT), timeout=2).length == 3


def test_control_retains_detached_manifest_and_full_original_operation_binding(sides, tmp_path):
    with endpoints(sides, tmp_path) as (peers, adapters, _):
        assert FILE_METHODS <= peers[0].capabilities.keys()
        p = file_params("files.start")
        with pytest.raises(PeerProtocolError):
            peers[0].request("files.start", p)
        reply = peers[0].request("files.start", p, file_manifest=manifest())
        assert reply["operation"]["request_sha256"] == request_sha256("files.start", p)
        p["grant_id"] = SESSION
        assert adapters[1].effects[0][1]["grant_id"] != p["grant_id"]
        # A syntactically valid forged receipt after an accepted effect stays unknown.
        def forge(method, params, result):
            result["operation"]["request_sha256"] = "b" * 64
            return result
        adapters[1].control_reply = forge
        p = file_params("files.start")
        with pytest.raises(PeerFileCallUncertain) as error:
            peers[0].request("files.start", p, file_manifest=manifest())
        assert error.value.operation_id == OPERATION and error.value.transfer_id == TRANSFER
        assert error.value.uncertain and len(adapters[1].effects) == 2


def test_status_receipt_requires_and_checks_the_retained_original_mutation(sides, tmp_path):
    with endpoints(sides, tmp_path) as (peers, adapters, _):
        original = file_params("files.start")
        status = file_params("files.status"); status["operation_id"] = OPERATION
        with pytest.raises(PeerProtocolError):
            peers[0].request("files.status", status, file_manifest=manifest())
        def receipt(method, params, result):
            result["operation"] = file_result("files.start", original)["operation"]
            return result
        adapters[1].control_reply = receipt
        reply = peers[0].request("files.status", status, file_manifest=manifest(),
                                 file_operation=("files.start", original))
        assert reply["operation"]["method"] == "files.start"
        wrong = deepcopy(original); wrong["grant_id"] = SESSION
        with pytest.raises(PeerProtocolError):
            peers[0].request("files.status", status, file_manifest=manifest(),
                             file_operation=("files.start", wrong))
        assert peers[0]._closed.is_set()


def test_generic_remote_failure_after_effect_never_proves_a_file_mutation_was_rejected(sides, tmp_path):
    with endpoints(sides, tmp_path) as (peers, adapters, _):
        def fail_after_effect(*_):
            raise PeerDenied("Fixed synthetic post-accept failure")
        adapters[1].control_reply = fail_after_effect
        p = file_params("files.cancel")
        with pytest.raises(PeerFileCallUncertain) as error:
            peers[0].request("files.cancel", p, file_manifest=manifest())
        assert error.value.operation_id == p["operation_id"]
        assert len(adapters[1].effects) == 1


def test_blocked_disk_does_not_block_control_reply_routing_and_data_budget_is_separate(sides, tmp_path):
    with endpoints(sides, tmp_path) as (peers, adapters, _):
        adapters[0].release.clear()
        before = [peer._request_count for peer in peers]
        with ThreadPoolExecutor(2) as pool:
            sent = pool.submit(peers[1].send_file_data, data(), timeout=4)
            assert adapters[0].entered.wait(2)
            started = time.monotonic()
            hello = peers[0].request("peer.hello", {"protocols": [1], "capabilities":
                                                   {name: 1 for name in BASE_METHODS | FILE_METHODS}}, timeout=1)
            assert hello["protocol"] == 1 and time.monotonic() - started < 1
            assert not sent.done() and adapters[0].trace == []
            adapters[0].release.set()
            assert sent.result(timeout=3).sha256 == data().sha256
        assert adapters[0].trace == [(TRANSFER, "data_fsynced"), (TRANSFER, "journal_fsynced")]
        assert peers[0]._request_count == before[0] + 1
        assert peers[1]._request_count == before[1]


def test_outgoing_data_is_bounded_to_two_transfers_and_one_block_each(sides, tmp_path):
    with endpoints(sides, tmp_path) as (peers, adapters, _):
        adapters[1].release.clear()
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(peers[0].send_file_data, data(), timeout=4)
            assert adapters[1].entered.wait(2)
            second = pool.submit(peers[0].send_file_data, data(PROJECT), timeout=4)
            deadline = time.monotonic() + 2
            while len(peers[0]._file_pending) < 2 and time.monotonic() < deadline:
                time.sleep(.005)
            for transfer in (TRANSFER, SESSION):
                with pytest.raises(PeerProtocolError) as error:
                    peers[0].send_file_data(data(transfer), timeout=.2)
                assert error.value.code == "busy"
            assert not peers[0]._closed.is_set()
            adapters[1].release.set()
            first.result(timeout=3); second.result(timeout=3)


def test_abort_releases_all_pending_block_waiters_without_retry(sides, tmp_path):
    with endpoints(sides, tmp_path) as (peers, adapters, _):
        adapters[1].release.clear()
        with ThreadPoolExecutor(2) as pool:
            sent = [pool.submit(peers[0].send_file_data, data(transfer), timeout=8)
                    for transfer in (TRANSFER, PROJECT)]
            deadline = time.monotonic() + 2
            while len(peers[0]._file_pending) < 2 and time.monotonic() < deadline:
                time.sleep(.005)
            assert len(peers[0]._file_pending) == 2
            peers[0]._abort()
            for future in sent:
                with pytest.raises(PeerFileDataUncertain):
                    future.result(timeout=1)
            adapters[1].release.set()


def test_stream_blocks_do_not_consume_exhausted_control_request_budget(sides, tmp_path):
    with endpoints(sides, tmp_path) as (peers, _, _):
        peers[0]._request_count = MAX_CONNECTION_REQUESTS
        assert peers[0].send_file_data(data(), timeout=2).sha256 == data().sha256
        assert peers[0]._request_count == MAX_CONNECTION_REQUESTS


@pytest.mark.parametrize("mode", ["mismatch", "unsolicited", "duplicate", "drop"])
def test_bad_or_missing_receipts_close_without_retry_or_advancing_unknown_data(sides, tmp_path, mode):
    with endpoints(sides, tmp_path) as (peers, adapters, transports):
        emitted = []
        def alter(raw, queue):
            emitted.append(raw)
            if mode == "drop":
                return
            receipt = decode_frame(raw)
            if mode == "mismatch":
                raw = encode_frame(replace(receipt, offset=1))
            queue.put(raw)
            if mode == "duplicate":
                queue.put(raw)
        transports[1].blob_hook = alter
        if mode == "unsolicited":
            transports[0].blob.put(encode_receipt(data()))
        else:
            if mode == "duplicate":
                try:
                    peers[0].send_file_data(data(), timeout=1)
                except PeerFileDataUncertain:
                    pass
            else:
                with pytest.raises(PeerFileDataUncertain) as error:
                    peers[0].send_file_data(data(), timeout=.3 if mode == "drop" else 1)
                assert error.value.uncertain and error.value.sequence == 0
        deadline = time.monotonic() + 2
        while not peers[0]._closed.is_set() and time.monotonic() < deadline:
            time.sleep(.005)
        assert peers[0]._closed.is_set()
        assert len(emitted) == (0 if mode == "unsolicited" else 1)
        if emitted:
            assert adapters[1].trace[-1] == (TRANSFER, "journal_fsynced")


@pytest.mark.parametrize("route", ["udp", "tcp"])
def test_real_two_helpers_data_receipt_is_after_actual_data_and_journal_fsync(sides, tmp_path, links, route):
    a, b = links(route)
    with endpoints(sides, tmp_path, native=[a, b]) as (peers, adapters, _):
        receipt = peers[0].send_file_data(data(), timeout=8)
        assert receipt.body == b"" and receipt.length == 3
        assert (adapters[1].directory / (TRANSFER + ".partial")).read_bytes() == b"abc"
        journal = json.loads((adapters[1].directory / (TRANSFER + ".journal")).read_text())
        assert journal == {"file_id": FILE, "bytes": 3, "sha256": data().sha256}
        assert adapters[1].trace == [(TRANSFER, "data_fsynced"), (TRANSFER, "journal_fsynced")]
