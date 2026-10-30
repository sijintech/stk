"""The peer control contract without an endpoint, a grant store or a private stdio bridge."""
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from suan.peer.protocol import (FORMAT, MAX_COMMANDS, MAX_JSON_DEPTH, MAX_MESSAGE_BYTES, METHODS,
                                PeerProtocolError, decode_message, encode_message, negotiate_hello,
                                validate_request, validate_response)


IDENTITY = "11111111-1111-4111-8111-111111111111"
PROJECT = "22222222-2222-4222-8222-222222222222"
GRANT = "33333333-3333-4333-8333-333333333333"
GENERATION = "44444444-4444-4444-8444-444444444444"
OPERATION = "55555555-5555-4555-8555-555555555555"
TABLE = "66666666-6666-4666-8666-666666666666"
RECORD = "77777777-7777-4777-8777-777777777777"
FIELD = "88888888-8888-4888-8888-888888888888"
APPLY = "project.edit_operations.apply_once"
GET = "project.edit_operations.get"


def request(method="peer.hello", **params):
    if method == "peer.hello":
        values = {"protocols": [1], "capabilities": {name: 1 for name in METHODS}}
    else:
        values = {"project_id": PROJECT, "grant_id": GRANT, "database_generation": GENERATION}
    values.update(params)
    return {"format": FORMAT, "id": IDENTITY, "method": method, "params": values}


@pytest.mark.parametrize("message", [
    request(),
    request("project.catalog"),
    request("project.catalog", expected_revision=0, offset=200, limit=200),
    request("project.table.read", table_id=TABLE, expected_revision=5, offset=0, limit=500, record_id=RECORD),
    request(APPLY, operation_id=OPERATION, expected_revision=0,
            commands=[{"op": "create_table", "name": "Explicit edit"}]),
    request(GET, operation_id=OPERATION),
], ids=["hello", "catalog", "catalog-page", "table-page", "apply-once", "receipt-get"])
def test_wire_round_trip_preserves_the_exact_request_and_detaches_input(message):
    original = deepcopy(message)
    encoded = encode_message(message)
    received = decode_message(encoded)
    assert received == original and validate_request(received) == original
    message["params"].clear()
    assert received == original


def test_original_values_and_nested_user_json_are_not_identity_or_type_normalized():
    value = {"integer": 1, "float": 1.0, "negative_zero": -0.0, "null": None, "boolean": False,
             "text": '中\\文"{}[]', "scope": "ordinary user JSON", "owner": "ordinary user JSON"}
    message = request(APPLY, operation_id=OPERATION, expected_revision=7, commands=[
        {"op": "set_cell", "table_id": TABLE, "record_id": RECORD, "field_id": FIELD, "value": value}])
    received = decode_message(encode_message(message))
    assert received["params"]["operation_id"] == OPERATION and received["params"]["expected_revision"] == 7
    copied = received["params"]["commands"][0]["value"]
    assert type(copied["integer"]) is int and type(copied["float"]) is float
    assert math.copysign(1, copied["negative_zero"]) == -1
    assert copied == value and copied["null"] is None and copied["boolean"] is False


def test_hello_reports_only_the_authenticated_endpoints_actual_capability_intersection():
    params = {"protocols": [2, 1], "capabilities": {"peer.hello": 1, "project.catalog": 1,
                                                   APPLY: 1, GET: 2, "desktop.control": 1}}
    available = {"peer.hello": 1, "project.catalog": 1, GET: 1}
    original_params, original_available = deepcopy(params), deepcopy(available)
    result = negotiate_hello(params, capabilities=available)
    assert result["protocol"] == 1 and result["capabilities"] == {"peer.hello": 1, "project.catalog": 1}
    assert result["unavailable"] == sorted([APPLY, GET, "desktop.control"])
    assert result["limits"] == {"message_bytes": 16 * 1024 * 1024, "json_depth": 64, "commands": 1000,
                                "request_bytes": 256 * 1024, "receipt_bytes": 512 * 1024}
    response = {"format": FORMAT, "id": IDENTITY, "result": result}
    assert decode_message(encode_message(response, method="peer.hello"), method="peer.hello") == response
    assert params == original_params and available == original_available
    assert negotiate_hello(params)["capabilities"] == {"peer.hello": 1}
    assert negotiate_hello({"protocols": [1], "capabilities": {}}, capabilities=available)["capabilities"] == {}


@pytest.mark.parametrize("change", [
    {"protocols": []}, {"protocols": [1, 1]}, {"protocols": [True]}, {"protocols": [0]},
    {"protocols": list(range(1, 18))}, {"protocols": "1"}, {"capabilities": []},
    {"capabilities": {"project.catalog": True}}, {"capabilities": {"Project.Catalog": 1}},
    {"capabilities": {"project.catalog": 0}}, {"capabilities": {"project.catalog": 65536}},
    {"capabilities": {"future.method" + str(i): 1 for i in range(65)}},
    {"capabilities": {"x" * 129: 1}}, {"owner": PROJECT}, {"resume_transfers": True},
])
def test_hello_rejects_malformed_or_privileged_parameters(change):
    message = request()
    message["params"].update(change)
    with pytest.raises(PeerProtocolError):
        validate_request(message)
    with pytest.raises(PeerProtocolError):
        negotiate_hello(message["params"])


def test_unsupported_versions_or_unimplemented_server_capabilities_fail_closed():
    with pytest.raises(PeerProtocolError) as error:
        negotiate_hello({"protocols": [2], "capabilities": {}})
    assert error.value.code == "unsupported"
    for capabilities in ({"desktop.control": 1}, {"project.catalog": 2}, [], True):
        with pytest.raises(PeerProtocolError):
            negotiate_hello(request()["params"], capabilities=capabilities)


@pytest.mark.parametrize("method", ["hello", "project.open", "project.apply", "script.execute", "ui.attach",
                                    "models.local.start", "task.submit", "project.backup", None, ["peer.hello"]])
def test_only_the_five_explicit_peer_methods_can_cross_the_wire(method):
    message = request()
    message["method"] = method
    with pytest.raises(PeerProtocolError) as error:
        validate_request(message)
    assert error.value.code == "unsupported"


@pytest.mark.parametrize("field", ["scope", "owner", "caller", "handle", "directory", "path", "session"])
@pytest.mark.parametrize("method", ["project.catalog", GET])
def test_business_requests_cannot_assert_a_scope_identity_or_local_path(field, method):
    message = request(method, **({"operation_id": OPERATION} if method == GET else {}))
    message["params"][field] = "/private/never-echo-this" if field in {"directory", "path"} else IDENTITY
    with pytest.raises(PeerProtocolError) as error:
        decode_message(json.dumps(message).encode("utf-8"))
    assert error.value.code == "invalid_params" and "never-echo-this" not in str(error.value)


@pytest.mark.parametrize("field", ["project_id", "grant_id", "database_generation"])
def test_each_project_target_identity_is_mandatory_and_canonical(field):
    message = request("project.catalog")
    message["params"].pop(field)
    with pytest.raises(PeerProtocolError):
        validate_request(message)
    message["params"][field] = "ABCDEFAB-ABCD-4ABC-8ABC-ABCDEFABCDEF"
    with pytest.raises(PeerProtocolError):
        validate_request(message)


@pytest.mark.parametrize("change", [
    {"operation_id": "not-a-uuid"}, {"expected_revision": True}, {"expected_revision": -1},
    {"base_revision": 0}, {"commands": []}, {"commands": [{"op": "submit_job"}]},
    {"commands": [{"op": "create_table", "name": "A", "typo": 1}]},
    {"commands": [{"op": "create_table", "name": "A"}] * (MAX_COMMANDS + 1)},
])
def test_edit_request_uses_the_original_explicit_identity_revision_and_shared_command_contract(change):
    message = request(APPLY, operation_id=OPERATION, expected_revision=0,
                      commands=[{"op": "create_table", "name": "A"}])
    message["params"].update(change)
    with pytest.raises(PeerProtocolError):
        validate_request(message)


@pytest.mark.parametrize("message", [
    request("project.catalog", limit=201), request("project.catalog", expected_revision=2 ** 53),
    request("project.table.read", table_id=TABLE, expected_revision=0, limit=501),
    request("project.table.read", table_id=TABLE, expected_revision=0, offset=1, record_id=RECORD),
    request("project.table.read", table_id=TABLE), request(GET, operation_id=OPERATION, expected_revision=0),
])
def test_project_paging_and_receipt_queries_keep_the_shared_public_bounds(message):
    with pytest.raises(PeerProtocolError):
        validate_request(message)


@pytest.mark.parametrize("raw", [
    b'{"format":"stk.peer/1","format":"stk.peer/1"}',
    b'{"result":{"nested":{"key":1,"key":2}}}',
    b'{"result":{"number":NaN}}', b'{"result":{"number":Infinity}}',
    b'{"result":{"number":1e999}}', b'{"result":{"text":"\\ud800"}}',
    b'\xff', b'\xef\xbb\xbf{}', b'{} {}', b'{"text":"unterminated}',
])
def test_raw_json_is_strict_before_any_method_or_authority_is_consulted(raw):
    with pytest.raises(PeerProtocolError) as error:
        decode_message(raw)
    assert error.value.code == "invalid_request"
    assert error.value.to_dict() == {"code": "invalid_request", "message": "Message does not match the peer protocol"}


@pytest.mark.parametrize("old, replacement", [
    (b'"format":"stk.peer/1"', b'"format":"stk.peer/1","format":"stk.peer/1"'),
    (b'"method":"peer.hello"', b'"method":"peer.hello","\\u006dethod":"peer.hello"'),
    (b'"protocols":[1]', b'"protocols":[1],"protocols":[1]'),
])
def test_duplicate_keys_are_rejected_even_when_the_last_value_is_an_otherwise_valid_request(old, replacement):
    raw = json.dumps(request(), separators=(",", ":")).encode("utf-8")
    assert decode_message(raw) == request()
    assert old in raw
    with pytest.raises(PeerProtocolError) as error:
        decode_message(raw.replace(old, replacement, 1))
    assert error.value.code == "invalid_request"


@pytest.mark.parametrize("value", [b"NaN", b"Infinity", b"-Infinity", b"1e999", b'"\\ud800"'])
def test_invalid_scalar_values_fail_inside_an_otherwise_valid_reply(value):
    prefix = json.dumps({"format": FORMAT, "id": IDENTITY}, separators=(",", ":")).encode("utf-8")[:-1]
    raw = prefix + b',"result":{"value":' + value + b"}}"
    with pytest.raises(PeerProtocolError) as error:
        decode_message(raw)
    assert error.value.code == "invalid_request"


def test_byte_limits_count_utf8_and_leave_room_for_existing_eight_megabyte_pages():
    message = {"format": FORMAT, "id": IDENTITY, "result": {"page": "字" * (3 * 1024 * 1024)}}
    encoded = encode_message(message)
    assert 8 * 1024 * 1024 < len(encoded) < MAX_MESSAGE_BYTES
    assert decode_message(encoded) == message
    for oversized in (b" " * (MAX_MESSAGE_BYTES + 1),):
        with pytest.raises(PeerProtocolError) as error:
            decode_message(oversized)
        assert error.value.code == "limit_exceeded"
    message["result"]["page"] = "字" * (6 * 1024 * 1024)
    with pytest.raises(PeerProtocolError) as error:
        encode_message(message)
    assert error.value.code == "limit_exceeded"


def test_a_schema_valid_large_table_page_fits_without_lowering_its_shared_budget():
    result = {"project_id": PROJECT, "revision": 1, "format_version": 15, "total": 500,
              "offset": 0, "next_offset": None,
              "table": {"id": TABLE, "name": "Large page", "fields": [
                  {"id": FIELD, "name": "Notes", "type": "text", "unit": None}],
                  "records": [{"id": f"00000000-0000-4000-8000-{i:012x}",
                               "values": {FIELD: "x" * 16300}} for i in range(1, 501)]}}
    message = {"format": FORMAT, "id": IDENTITY, "result": result}
    encoded = encode_message(message, method="project.table.read")
    assert 7 * 1024 * 1024 < len(encoded) < 8 * 1024 * 1024
    assert decode_message(encoded, method="project.table.read") == message


def test_project_response_metadata_is_closed_without_restricting_authorized_user_json():
    result = {"format_version": 15, "project": {"id": PROJECT, "name": "Project", "revision": 0},
              "tables": [], "total": 0, "offset": 0, "next_offset": None}
    message = {"format": FORMAT, "id": IDENTITY, "result": result}
    assert decode_message(encode_message(message, method="project.catalog"), method="project.catalog") == message
    for key in ("directory", "handle", "pid"):
        malformed = deepcopy(message)
        malformed["result"]["project"][key] = "private-local-metadata"
        with pytest.raises(PeerProtocolError):
            validate_response(malformed, method="project.catalog")


def test_container_depth_is_bounded_before_parse_and_escaped_braces_are_ordinary_text():
    value = "end"
    for _ in range(MAX_JSON_DEPTH - 2):
        value = [value]
    message = {"format": FORMAT, "id": IDENTITY, "result": {"value": value}}
    assert decode_message(encode_message(message)) == message
    message["result"]["value"] = [value]
    with pytest.raises(PeerProtocolError) as error:
        encode_message(message)
    assert error.value.code == "limit_exceeded"
    with pytest.raises(PeerProtocolError) as error:
        decode_message(b"[" * (MAX_JSON_DEPTH + 1) + b"0" + b"]" * (MAX_JSON_DEPTH + 1))
    assert error.value.code == "limit_exceeded"
    text = '{[\\"' * 1000
    flat = {"format": FORMAT, "id": IDENTITY, "result": {"text": text}}
    assert decode_message(encode_message(flat)) == flat


@pytest.mark.parametrize("change", [{"directory": "/private/local"}, {"pid": 123}, {"handle": "0" * 32},
                                    {"authenticated": True}, {"owner": PROJECT}])
def test_hello_result_does_not_return_local_paths_handles_or_authentication_claims(change):
    result = negotiate_hello(request()["params"])
    result.update(change)
    with pytest.raises(PeerProtocolError):
        validate_response({"format": FORMAT, "id": IDENTITY, "result": result}, method="peer.hello")


def test_error_envelopes_are_bounded_and_cannot_be_confused_with_success():
    response = {"format": FORMAT, "id": None, "error": {"code": "unauthorized", "message": "Peer authorization required"}}
    assert decode_message(encode_message(response)) == response
    for change in ({"result": {}}, {"error": {"code": "raw_exception", "message": "bad"}},
                   {"error": {"code": "unauthorized", "message": "x" * 257}}):
        malformed = {**response, **change}
        with pytest.raises(PeerProtocolError):
            validate_response(malformed)
    with pytest.raises(PeerProtocolError):
        validate_response({"format": FORMAT, "id": None, "result": {}})


def test_pure_hello_cannot_spawn_resume_open_or_connect_in_a_fresh_interpreter(tmp_path):
    program = '''
import builtins, socket, sqlite3, subprocess, sys, threading
from suan.peer.protocol import negotiate_hello
def forbidden(*args, **kwargs):
    raise AssertionError('hello performed an external action')
builtins.open = socket.socket = sqlite3.connect = subprocess.Popen = threading.Thread.start = forbidden
result = negotiate_hello({'protocols':[1], 'capabilities':{'peer.hello':1, 'project.catalog':1}})
assert result['capabilities'] == {'peer.hello':1}
assert 'suan.desktop_bridge.server' not in sys.modules
assert 'suan.desktop_bridge.projects' not in sys.modules
assert 'suan.models.local' not in sys.modules
print('pure hello passed')
'''
    completed = subprocess.run([sys.executable, "-c", program], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "pure hello passed\n"
