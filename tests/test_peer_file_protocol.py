"""Independent wire vectors and closed optional file-control contracts."""
from copy import deepcopy
from dataclasses import replace
import hashlib

import pytest

from suan.peer.file_protocol import (CHUNK_BYTES, DATA, FILE_METHODS, FILE_MUTATIONS,
    HEADER_BYTES, RECEIPT, FileFrame, FileProtocolError, decode_frame, encode_data,
    encode_frame, encode_receipt, request_sha256, validate_file_params,
    validate_file_result, validate_operation_receipt, validate_receipt)
from suan.peer.protocol import (BASE_METHODS, FORMAT, METHODS, PeerProtocolError,
    decode_message, encode_message, negotiate_hello)
from suan.peer.authority import peer_id_for


TRANSFER = "11111111-1111-4111-8111-111111111111"
FILE = "22222222-2222-4222-8222-222222222222"
SESSION = "33333333-3333-4333-8333-333333333333"
OPERATION = "44444444-4444-4444-8444-444444444444"
GRANT = "55555555-5555-4555-8555-555555555555"
PROJECT = "66666666-6666-4666-8666-666666666666"
SNAPSHOT = "77777777-7777-4777-8777-777777777777"
EMPTY_FILE = "88888888-8888-4888-8888-888888888888"
ABC_SHA = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
# Independent literal: network endian, RFC UUID bytes (not bytes_le), no padding.
ABC_WIRE = bytes.fromhex(
    "53544b46" "01" "01" "0000"
    "11111111111141118111111111111111" "22222222222242228222222222222222"
    "0000000000000000" "0000000000000000" "00000003"
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" "616263")


def test_binary_pinned_vector_and_network_endian_integer_fields():
    assert HEADER_BYTES == 92 and len(ABC_WIRE) == 95
    assert encode_data(TRANSFER, FILE, 0, 0, b"abc") == ABC_WIRE
    assert decode_frame(ABC_WIRE) == FileFrame(DATA, TRANSFER, FILE, 0, 0, 3, ABC_SHA, b"abc")
    raw = encode_data(TRANSFER, FILE, 0x0102030405060708, 0x1112131415161718, b"abc")
    assert raw[40:48] == bytes.fromhex("0102030405060708")
    assert raw[48:56] == bytes.fromhex("1112131415161718")


@pytest.mark.parametrize("length", range(92))
def test_binary_every_truncated_header_is_rejected(length):
    with pytest.raises(FileProtocolError):
        decode_frame(ABC_WIRE[:length])


@pytest.mark.parametrize("position,value", [(0, 0), (4, 0), (4, 2), (5, 0), (5, 3), (6, 1), (7, 1), (60, 0), (94, 0)])
def test_binary_changed_header_or_data_cannot_bypass_fixed_framing_and_digest(position, value):
    raw = bytearray(ABC_WIRE)
    raw[position] = value
    with pytest.raises(FileProtocolError):
        decode_frame(bytes(raw))


@pytest.mark.parametrize("declared", [0, 1, 2, 4, CHUNK_BYTES + 1, 2**32 - 1])
def test_binary_declared_data_length_is_not_trusted(declared):
    raw = ABC_WIRE[:56] + declared.to_bytes(4, "big") + ABC_WIRE[60:]
    with pytest.raises(FileProtocolError):
        decode_frame(raw)


def test_binary_chunk_limit_and_unsigned_overflow_without_journal_alignment_claim():
    data = b"a" * CHUNK_BYTES
    frame = decode_frame(encode_data(TRANSFER, FILE, 2**64 - 1, 2**64 - 1 - len(data), data))
    assert frame.body == data and len(encode_frame(frame)) == 92 + 60 * 1024 < 64 * 1024
    for body in (b"", data + b"a", bytearray(b"abc"), "abc"):
        with pytest.raises(FileProtocolError):
            encode_data(TRANSFER, FILE, 0, 0, body)
    for number in (-1, True, 1.0, 2**64):
        with pytest.raises(FileProtocolError):
            encode_data(TRANSFER, FILE, number, 0, b"abc")
        with pytest.raises(FileProtocolError):
            encode_data(TRANSFER, FILE, 0, number, b"abc")
    with pytest.raises(FileProtocolError):
        encode_data(TRANSFER, FILE, 0, 2**64 - 3, b"abc")
    with pytest.raises(FileProtocolError):
        decode_frame(b"a" * (64 * 1024 + 1))
    # Alignment/file-size/permission checks belong to the current leased journal.
    assert decode_frame(encode_data(TRANSFER, FILE, 9, 7, b"abc")).offset == 7


def test_binary_application_receipt_has_empty_body_and_echoes_logical_data_length():
    data = decode_frame(ABC_WIRE)
    raw = encode_receipt(data)
    assert len(raw) == 92 and raw[:5] == ABC_WIRE[:5] and raw[5] == RECEIPT
    assert raw[56:60] == b"\x00\x00\x00\x03"
    receipt = decode_frame(raw)
    assert receipt.body == b"" and validate_receipt(receipt, data) == receipt
    with pytest.raises(FileProtocolError):
        decode_frame(raw + b"a")
    with pytest.raises(FileProtocolError):
        encode_receipt(receipt)
    for changed in (replace(receipt, transfer_id=SESSION), replace(receipt, file_id=EMPTY_FILE),
                    replace(receipt, sequence=1), replace(receipt, offset=1),
                    replace(receipt, length=2), replace(receipt, sha256=EMPTY_SHA)):
        assert decode_frame(encode_frame(changed)) == changed
        with pytest.raises(FileProtocolError):
            validate_receipt(changed, data)


def manifest():
    return {"format": "stk.peer-files-manifest/1", "project_id": PROJECT, "source_revision": 0,
            "snapshot_id": SNAPSHOT, "snapshot_sha256": "a" * 64,
            "files": [{"file_id": FILE, "name": "example.bin", "bytes": 3, "sha256": ABC_SHA,
                       "media_type": "application/octet-stream"},
                      {"file_id": EMPTY_FILE, "name": "empty.bin", "bytes": 0, "sha256": EMPTY_SHA,
                       "media_type": "application/octet-stream"}]}


def session_offer():
    def card(public, owner, name):
        return {"format": "stk.peer-device/1", "owner_id": owner,
                "peer_id": peer_id_for(public), "public_key": public.hex(), "display_name": name}
    return {"format": "stk.peer-sharing-session/1", "session_id": SESSION,
            "session_epoch": 1, "host": card(b"a" * 32, PROJECT, "Host"),
            "recipient": card(b"b" * 32, SNAPSHOT, "Recipient"), "expires_at": 2000.0}


def params(method):
    from suan.peer.manifests import manifest_sha256
    result = {"session_id": SESSION, "transfer_id": TRANSFER, "manifest_sha256": manifest_sha256(manifest()),
              "operation_id": None if method == "files.status" else OPERATION}
    if method == "files.offer":
        result["manifest"] = manifest()
        result["session_offer"] = session_offer()
    elif method != "files.status":
        result["grant_id"] = GRANT
    return result


def result(method, request, *, complete=False):
    complete = complete or method == "files.complete"
    progress = [{"file_id": f["file_id"], "bytes": f["bytes"],
                 "committed_bytes": f["bytes"] if complete else 0,
                 "next_sequence": (f["bytes"] + CHUNK_BYTES - 1) // CHUNK_BYTES if complete else 0,
                 "verified_sha256": f["sha256"] if complete else None} for f in manifest()["files"]]
    operation = None if method == "files.status" else {
        "operation_id": request["operation_id"], "method": method,
        "request_sha256": request_sha256(method, request), "state": "completed"}
    completion = None if not complete else {"format": "stk.peer-files-receipt/1", "transfer_id": TRANSFER,
        "manifest_sha256": request["manifest_sha256"], "files": [
            {key: f[key] for key in ("file_id", "bytes", "sha256")} for f in manifest()["files"]]}
    return {"session_id": SESSION, "transfer_id": TRANSFER, "manifest_sha256": request["manifest_sha256"],
            "state": "complete" if complete else "offered" if method == "files.offer" else
                     "cancelled" if method == "files.cancel" else "receiving",
            "grant_id": None if method == "files.offer" else GRANT,
            "files": progress, "operation": operation, "completion": completion}


@pytest.mark.parametrize("method", sorted(FILE_METHODS))
def test_optional_closed_control_round_trip_and_bound_results(method):
    p = params(method)
    envelope = {"format": FORMAT, "id": OPERATION, "method": method, "params": p}
    assert decode_message(encode_message(envelope)) == envelope
    response = {"format": FORMAT, "id": OPERATION, "result": result(method, p)}
    arguments = {"method": method, "request_params": p, "file_manifest": manifest()}
    assert decode_message(encode_message(response, **arguments), **arguments) == response
    detached = validate_file_params(method, p)
    p.clear()
    assert detached


def test_known_codec_does_not_add_optional_methods_to_default_endpoint_requests_or_grant_them():
    assert METHODS == BASE_METHODS and len(BASE_METHODS) == 5
    offered = {"protocols": [1], "capabilities": {name: 1 for name in BASE_METHODS | FILE_METHODS}}
    assert negotiate_hello(offered)["capabilities"] == {"peer.hello": 1}
    assert not (negotiate_hello(offered, capabilities={name: 1 for name in BASE_METHODS})["capabilities"].keys()
                & FILE_METHODS)
    selected = negotiate_hello(offered, capabilities={"peer.hello": 1, "files.offer": 1})
    assert selected["capabilities"] == {"peer.hello": 1, "files.offer": 1}


@pytest.mark.parametrize("method", sorted(FILE_METHODS))
@pytest.mark.parametrize("field", ["root", "directory", "path", "owner", "private_key", "accept"])
def test_control_rejects_extra_privilege_or_destination_fields_without_echo(method, field):
    p = params(method)
    p[field] = "private-never-echo"
    with pytest.raises(FileProtocolError) as error:
        validate_file_params(method, p)
    assert "private-never-echo" not in str(error.value)


@pytest.mark.parametrize("method", sorted(FILE_MUTATIONS))
@pytest.mark.parametrize("field", ["operation_id", "method", "request_sha256", "state"])
def test_successful_mutation_must_bind_its_own_completed_original_operation(method, field):
    p = params(method)
    reply = result(method, p)
    reply["operation"][field] = {"operation_id": SESSION, "method": "files.cancel" if method != "files.cancel" else
        "files.start", "request_sha256": "b" * 64, "state": "uncertain"}[field]
    with pytest.raises(FileProtocolError):
        validate_file_result(method, reply, params=p, manifest=manifest())


def test_cancel_before_accept_and_unknown_status_are_not_implicit_start_or_no_effect_proofs():
    p = params("files.cancel"); p["grant_id"] = None
    assert validate_file_params("files.cancel", p) == p
    for method in ("files.start", "files.resume", "files.complete"):
        p = params(method); p["grant_id"] = None
        with pytest.raises(FileProtocolError):
            validate_file_params(method, p)
    p = params("files.status"); p["operation_id"] = OPERATION
    reply = result("files.status", p)
    assert validate_file_result("files.status", reply, params=p)["operation"] is None
    original = params("files.start")
    reply["operation"] = {"operation_id": OPERATION, "method": "files.start",
                          "request_sha256": request_sha256("files.start", original), "state": "uncertain"}
    assert validate_operation_receipt(reply["operation"], method="files.start", params=original)


def test_complete_requires_retained_manifest_and_exact_frozen_order_size_and_whole_hashes():
    p = params("files.complete"); original = result("files.complete", p)
    with pytest.raises(FileProtocolError):
        validate_file_result("files.complete", original, params=p)
    assert validate_file_result("files.complete", original, params=p, manifest=manifest()) == original
    variants = []
    wrong = deepcopy(original); wrong["files"].reverse(); wrong["completion"]["files"].reverse(); variants.append(wrong)
    wrong = deepcopy(original); wrong["files"][0]["bytes"] = 4; variants.append(wrong)
    wrong = deepcopy(original); wrong["files"][0]["verified_sha256"] = "b" * 64
    wrong["completion"]["files"][0]["sha256"] = "b" * 64; variants.append(wrong)
    wrong = deepcopy(original); wrong["completion"]["files"].pop(); variants.append(wrong)
    wrong = deepcopy(original); wrong["completion"]["files"][1]["sha256"] = ABC_SHA; variants.append(wrong)
    for wrong in variants:
        with pytest.raises(FileProtocolError):
            validate_file_result("files.complete", wrong, params=p, manifest=manifest())
    # An empty file has no DATA frame and is not verified during offer/start.
    p = params("files.start"); wrong = result("files.start", p)
    wrong["files"][1]["verified_sha256"] = EMPTY_SHA
    with pytest.raises(FileProtocolError):
        validate_file_result("files.start", wrong, params=p)


@pytest.mark.parametrize("value", [True, -1, 1.0, 2**64])
def test_progress_counters_are_exact_bounded_integers(value):
    p = params("files.status"); reply = result("files.status", p)
    reply["files"][0]["committed_bytes"] = value
    with pytest.raises(FileProtocolError):
        validate_file_result("files.status", reply, params=p)


def test_control_peer_errors_remain_fixed_and_unsupported_local_actions_stay_outside_wire():
    p = params("files.offer"); p["manifest_sha256"] = "b" * 64
    with pytest.raises(FileProtocolError):
        validate_file_params("files.offer", p)
    for method in ("files.accept", "files.remove", "files.read", "peer.files"):
        with pytest.raises(PeerProtocolError) as error:
            encode_message({"format": FORMAT, "id": OPERATION, "method": method, "params": {}})
        assert error.value.code == "unsupported"


@pytest.mark.parametrize("change", ["missing", "session", "epoch", "card", "expiry", "extra"])
def test_offer_requires_closed_full_public_session_offer_bound_to_same_session(change):
    p = params("files.offer")
    if change == "missing":
        del p["session_offer"]
    elif change == "session":
        p["session_offer"]["session_id"] = PROJECT
    elif change == "epoch":
        p["session_offer"]["session_epoch"] = True
    elif change == "card":
        p["session_offer"]["host"]["public_key"] = "a" * 64
    elif change == "expiry":
        p["session_offer"]["expires_at"] = float("inf")
    else:
        p["session_offer"]["accept"] = True
    with pytest.raises(FileProtocolError):
        validate_file_params("files.offer", p)


def test_reapproval_changes_original_offer_request_hash_without_changing_content_identity():
    first = params("files.offer")
    second = deepcopy(first)
    second["operation_id"] = PROJECT
    second["session_offer"]["session_epoch"] = 2
    second["session_offer"]["expires_at"] = 3000.0
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert request_sha256("files.offer", first) != request_sha256("files.offer", second)
    # No state or permission is created by either pure validation.
    assert validate_file_params("files.offer", second) == second


def test_operation_receipt_checks_an_explicit_retained_method_even_without_params():
    p = params("files.start")
    receipt = result("files.start", p)["operation"]
    with pytest.raises(FileProtocolError):
        validate_operation_receipt(receipt, method="files.resume")


@pytest.mark.parametrize("method", ["files.start", "files.resume", "files.complete", "files.cancel"])
def test_bound_result_cannot_substitute_an_unrelated_grant(method):
    p = params(method)
    reply = result(method, p)
    reply["grant_id"] = PROJECT
    with pytest.raises(FileProtocolError):
        validate_file_result(method, reply, params=p, manifest=manifest())
