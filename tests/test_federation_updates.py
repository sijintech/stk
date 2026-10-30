"""Array corruption and actual Flower-admission counterexamples, without Flower."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tracemalloc

import pytest

from suan.federation.updates import (
    ARRAYS_FORMAT, UPDATE_FORMAT, MAX_ARRAYS, MAX_BUNDLE_BYTES, MAX_HEADER_BYTES,
    FederationValidationError, decode_arrays, encode_arrays, validate_layout, validate_round, validate_update,
)


RUN = "11111111-1111-4111-8111-111111111111"
OTHER_RUN = "22222222-2222-4222-8222-222222222222"
GRANT = "33333333-3333-4333-8333-333333333333"
OTHER_GRANT = "44444444-4444-4444-8444-444444444444"
MODEL = "a" * 64
SPEC = "b" * 64
DATASET = "c" * 64
PEERS = [str(i) * 64 for i in range(1, 5)]
BINDING = {"run_id": RUN, "round": 7, "participant_id": PEERS[0],
           "model_sha256": MODEL, "spec_sha256": SPEC,
           "dataset_sha256": DATASET, "grant_id": GRANT}


def array(name="weights", dtype="f64", shape=None, values=(1.25, -0.0, -2.5)):
    return {"name": name, "dtype": dtype, "shape": shape or [len(values)],
            "data": struct.pack("<" + ("f" if dtype == "f32" else "d") * len(values), *values)}


def split(raw):
    length = struct.unpack(">I", raw[8:12])[0]
    return json.loads(raw[12:12+length]), raw[12+length:]


def wire(header, payload, *, encoded_header=None):
    # Independent framing constructor; tests can bypass the product encoder.
    encoded = (json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
               if encoded_header is None else encoded_header)
    return b"STKFAR1\n" + struct.pack(">I", len(encoded)) + encoded + payload


def independent_wire():
    payload = struct.pack("<4f", 1.0, -2.0, 0.0, 0.5)
    header = {"format": "stk.federation-arrays/1", "kind": "delta", "payload_bytes": 16,
              "payload_sha256": hashlib.sha256(payload).hexdigest(), "arrays": [{
                  "name": "layer.weight", "dtype": "f32", "shape": [2, 2],
                  "offset": 0, "nbytes": 16, "sha256": hashlib.sha256(payload).hexdigest()}]}
    return wire(header, payload)


def update(peer=PEERS[0], **changes):
    value = {"format": UPDATE_FORMAT, **BINDING, "participant_id": peer,
             "update_sha256": "d" * 64, "update_bytes": 1234, "num_examples": 8,
             "metrics": {"loss": 0.25, "correct": 7}, "masked": False}
    value.update(changes)
    return value


def participants(count=3):
    return {peer: {"dataset_sha256": DATASET, "grant_id": GRANT} for peer in PEERS[:count]}


def round_admit(values, **changes):
    args = {"participants": participants(), "run_id": RUN, "round": 7,
            "model_sha256": MODEL, "spec_sha256": SPEC}
    args.update(changes)
    return validate_round(values, **args)


def test_independent_wire_decodes_exact_little_endian_values_and_layout():
    raw = independent_wire()
    actual = decode_arrays(raw, expected_kind="delta", expected_layout=[{
        "name": "layer.weight", "dtype": "f32", "shape": [2, 2]}])
    assert actual["format"] == ARRAYS_FORMAT and actual["kind"] == "delta"
    assert struct.unpack("<4f", actual["arrays"][0]["data"]) == (1.0, -2.0, 0.0, 0.5)
    assert actual["sha256"] == hashlib.sha256(raw).hexdigest()
    assert actual["bytes"] == len(raw)


def test_round_trip_preserves_order_negative_zero_extremes_and_detaches_mutable_wire():
    f32 = struct.pack("<II", 0x7f7fffff, 0x00000001)
    items = [array("层.bias"), {"name": "layer.weight", "dtype": "f32", "shape": [1, 2], "data": f32}]
    encoded = encode_arrays(items, kind="model")
    source = bytearray(encoded)
    result = decode_arrays(source)
    source[:] = b"x" * len(source)
    assert result["arrays"] == items
    assert struct.unpack("<3d", result["arrays"][0]["data"])[1] == 0.0
    assert result["arrays"][0]["data"][8:16] == struct.pack("<d", -0.0)
    items[0]["shape"][0] = 99
    assert result["layout"][0]["shape"] == [3]
    result["arrays"][0]["shape"][0] = 88
    assert result["layout"][0]["shape"] == [3]
    assert decode_arrays(memoryview(encoded))["sha256"] == hashlib.sha256(encoded).hexdigest()


def test_encoder_is_deterministic_and_does_not_modify_input():
    items = [array("b"), array("a", "f32", [1, 3])]
    before = deepcopy(items)
    assert encode_arrays(items, kind="delta") == encode_arrays(deepcopy(items), kind="delta")
    assert items == before
    assert [a["name"] for a in decode_arrays(encode_arrays(items, kind="delta"))["arrays"]] == ["b", "a"]


@pytest.mark.parametrize("kind", [None, True, 1, "", "MODEL", "weights", "masked"])
def test_unknown_bundle_kind_is_rejected(kind):
    with pytest.raises(FederationValidationError):
        encode_arrays([array()], kind=kind)


@pytest.mark.parametrize("changes", [
    {"dtype": "float32"}, {"dtype": ">f4"}, {"dtype": "i64"}, {"dtype": True},
    {"shape": []}, {"shape": [1, 1, 1, 1, 1]}, {"shape": [0]}, {"shape": [-1]},
    {"shape": [True, 3]}, {"shape": [3.0]}, {"shape": "3"},
    {"shape": [2**63, 2**63]}, {"shape": [4096, 4096, 4096]},
    {"data": b"too short"}, {"data": bytearray(24)}, {"name": ""}, {"name": " "},
    {"name": "x\x00y"}, {"name": "x" * 129}, {"name": "层" * 43}, {"name": "\ud800"},
    {"unknown": "reject"},
])
def test_encoder_rejects_incompatible_types_shapes_names_and_byte_lengths(changes):
    value = array()
    value.update(changes)
    with pytest.raises(FederationValidationError):
        encode_arrays([value], kind="model")


def test_array_count_and_unique_names_are_bounded_before_encoding():
    maximum = [array(str(i), values=(1.0,)) for i in range(MAX_ARRAYS)]
    assert len(decode_arrays(encode_arrays(maximum, kind="model"))["arrays"]) == 128
    for invalid in ([], [array(), array()], maximum + [array("extra")], iter(maximum)):
        with pytest.raises(FederationValidationError):
            encode_arrays(invalid, kind="model")


@pytest.mark.parametrize("dtype", ["f32", "f64"])
@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")], ids=["nan", "positive-inf", "negative-inf"])
def test_nonfinite_updates_are_rejected_even_with_correct_wire_hashes(dtype, number):
    item = array(dtype=dtype, values=(number,))
    with pytest.raises(FederationValidationError, match="finite"):
        encode_arrays([item], kind="delta")
    header, _ = split(independent_wire())
    data = item["data"]
    header.update(payload_bytes=len(data), payload_sha256=hashlib.sha256(data).hexdigest())
    header["arrays"][0].update(dtype=dtype, shape=[1], nbytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    with pytest.raises(FederationValidationError, match="finite"):
        decode_arrays(wire(header, data))


@pytest.mark.parametrize("mutate", [
    lambda h: h.update(extra=0), lambda h: h.pop("kind"),
    lambda h: h.update(format="stk.federation-arrays/2"), lambda h: h.update(kind="masked"),
    lambda h: h.update(payload_bytes=True), lambda h: h.update(payload_bytes=15),
    lambda h: h.update(payload_sha256="0" * 64), lambda h: h.update(payload_sha256="A" * 64),
    lambda h: h["arrays"][0].update(offset=1), lambda h: h["arrays"][0].update(offset=True),
    lambda h: h["arrays"][0].update(nbytes=15), lambda h: h["arrays"][0].update(nbytes=16.0),
    lambda h: h["arrays"][0].update(shape=[True, 4]),
    lambda h: h["arrays"][0].update(shape=[2**63, 2**63]),
    lambda h: h["arrays"][0].update(dtype="f64"),
    lambda h: h["arrays"][0].update(sha256="0" * 64),
    lambda h: h["arrays"][0].update(extra="reject"), lambda h: h["arrays"][0].pop("name"),
    lambda h: h.update(arrays=[]), lambda h: h.update(arrays={}),
])
def test_independent_header_corruptions_fail_closed(mutate):
    header, payload = split(independent_wire())
    mutate(header)
    with pytest.raises(FederationValidationError):
        decode_arrays(wire(header, payload))


@pytest.mark.parametrize("offset", [0, 15, 17], ids=["overlap", "one-byte-overlap", "one-byte-gap"])
def test_multiple_arrays_must_cover_payload_contiguously(offset):
    encoded = encode_arrays([array("a", "f32", values=(1., 2., 3., 4.)), array("b", "f32", values=(5.,))], kind="model")
    header, payload = split(encoded)
    header["arrays"][1]["offset"] = offset
    with pytest.raises(FederationValidationError, match="offset"):
        decode_arrays(wire(header, payload))


def test_each_digest_and_complete_payload_coverage_are_required():
    raw = independent_wire()
    with pytest.raises(FederationValidationError, match="digest"):
        decode_arrays(raw[:-1] + bytes((raw[-1] ^ 1,)))
    header, payload = split(raw)
    header["payload_sha256"] = hashlib.sha256(payload + b"junk").hexdigest()
    header["payload_bytes"] += 4
    with pytest.raises(FederationValidationError, match="complete payload"):
        decode_arrays(wire(header, payload + b"junk"))
    header, payload = split(encode_arrays([array("a"), array("b")], kind="model"))
    header["arrays"][1]["name"] = "a"
    with pytest.raises(FederationValidationError, match="unique"):
        decode_arrays(wire(header, payload))


@pytest.mark.parametrize("header_bytes", [
    b'{"format":"x","format":"y"}',
    b'{"arrays":[{"name":"a","name":"b"}]}',
    b'{"name":"\xff"}', b'\xef\xbb\xbf{}', b'{}{}', b'{"x":NaN}', b'{"x":Infinity}',
    b'[' * 10 + b'0' + b']' * 10,
])
def test_header_rejects_duplicate_keys_bad_utf8_bom_trailing_json_and_nonfinite_tokens(header_bytes):
    with pytest.raises(FederationValidationError):
        decode_arrays(wire({}, b"data", encoded_header=header_bytes))


def test_framing_rejects_truncation_trailing_bytes_and_large_declarations():
    raw = independent_wire()
    for invalid in (b"", raw[:11], raw[:20], b"WRONG!!!" + raw[8:], raw + b"x",
                    raw[:8] + struct.pack(">I", 0) + raw[12:],
                    raw[:8] + struct.pack(">I", MAX_HEADER_BYTES+1) + raw[12:]):
        with pytest.raises(FederationValidationError):
            decode_arrays(invalid)
    with pytest.raises(FederationValidationError, match="byte budget"):
        decode_arrays(bytearray(MAX_BUNDLE_BYTES + 1))
    with pytest.raises(FederationValidationError):
        decode_arrays(memoryview(raw)[::2])


def test_released_memoryview_is_a_stable_validation_error():
    source = memoryview(independent_wire())
    source.release()
    with pytest.raises(FederationValidationError):
        decode_arrays(source)


def test_double_extremes_and_smallest_subnormal_are_finite_and_keep_their_bits():
    data = struct.pack("<QQ", 0x7fefffffffffffff, 1)
    item = {"name": "extreme", "dtype": "f64", "shape": [1, 1, 1, 2], "data": data}
    raw = encode_arrays((item,), kind="model")
    assert decode_arrays(raw)["arrays"] == [item]


@pytest.mark.parametrize("layout", [
    [{"name": "wrong", "dtype": "f32", "shape": [2, 2]}],
    [{"name": "layer.weight", "dtype": "f64", "shape": [2, 2]}],
    [{"name": "layer.weight", "dtype": "f32", "shape": [4]}],
    [{"name": "layer.weight", "dtype": "f32", "shape": [2, 2], "offset": 0}],
    [],
])
def test_expected_layout_is_exact_and_validated(layout):
    with pytest.raises(FederationValidationError):
        decode_arrays(independent_wire(), expected_layout=layout)


def test_expected_kind_and_order_cannot_silently_reinterpret_delta_or_parameters():
    with pytest.raises(FederationValidationError, match="kind"):
        decode_arrays(independent_wire(), expected_kind="model")
    with pytest.raises(FederationValidationError, match="kind"):
        decode_arrays(independent_wire(), expected_kind=True)
    raw = encode_arrays([array("a"), array("b")], kind="model")
    layout = decode_arrays(raw)["layout"]
    with pytest.raises(FederationValidationError, match="layout"):
        decode_arrays(raw, expected_layout=list(reversed(layout)))


def test_public_layout_validation_detaches_input_order_and_nested_shapes():
    layout = [{"name": "b", "dtype": "f64", "shape": [2, 3]},
              {"name": "a", "dtype": "f32", "shape": (1,)}]
    result = validate_layout(tuple(layout))
    assert result == [{"name": "b", "dtype": "f64", "shape": [2, 3]},
                      {"name": "a", "dtype": "f32", "shape": [1]}]
    layout[0]["shape"][0] = 99
    layout[1]["name"] = "replaced"
    assert [x["name"] for x in result] == ["b", "a"]
    assert result[0]["shape"] == [2, 3]


def test_public_layout_validation_does_not_allocate_large_declared_tensor_buffers():
    layout = [{"name": "large", "dtype": "f32", "shape": [4096, 4095]}]
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        assert validate_layout(layout) == layout
        _, peak = tracemalloc.get_traced_memory()
        assert peak - before < 128 * 1024
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize("bad", [
    [], [{"name": "x", "dtype": "f32", "shape": [True]}],
    [{"name": "x", "dtype": "f64", "shape": []}],
    [{"name": "x", "dtype": "f64", "shape": [0]}],
    [{"name": "x", "dtype": "f32", "shape": [2**63, 2**63]}],
    [{"name": "x", "dtype": "f64", "shape": [1], "data": b"not layout"}],
    [{"name": "x", "dtype": "f32", "shape": [1]}] * 2,
    [{"name": str(i), "dtype": "f32", "shape": [1]} for i in range(129)],
])
def test_public_layout_rejects_the_same_invalid_expected_layouts_as_decode(bad):
    with pytest.raises(FederationValidationError):
        validate_layout(bad)
    with pytest.raises(FederationValidationError):
        decode_arrays(independent_wire(), expected_layout=bad)


def test_public_layout_validates_maximum_array_count_and_matches_decoder_output():
    items = [array(str(i), "f32", values=(float(i),)) for i in range(128)]
    decoded = decode_arrays(encode_arrays(items, kind="delta"))
    admitted = validate_layout(decoded["layout"])
    assert len(admitted) == 128
    assert decode_arrays(encode_arrays(items, kind="delta"), expected_layout=admitted)["layout"] == admitted


def test_update_metadata_is_detached_and_all_expected_bindings_are_required():
    value = update()
    result = validate_update(value, **BINDING)
    assert result == value
    value["metrics"]["loss"] = 100
    assert result["metrics"]["loss"] == 0.25
    assert type(result["metrics"]["correct"]) is int
    assert type(result["metrics"]["loss"]) is float


@pytest.mark.parametrize("field,bad", [
    ("run_id", OTHER_RUN), ("round", 8), ("participant_id", PEERS[1]),
    ("model_sha256", "e" * 64), ("spec_sha256", "f" * 64),
    ("dataset_sha256", "0" * 64), ("grant_id", OTHER_GRANT),
])
def test_other_run_round_sender_model_spec_dataset_or_grant_cannot_be_admitted(field, bad):
    with pytest.raises(FederationValidationError, match="expected"):
        validate_update(update(**{field: bad}), **BINDING)


@pytest.mark.parametrize("changes", [
    {"format": "stk.federation-update/2"}, {"extra": "reject"},
    {"run_id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
    {"run_id": RUN.replace("-", "")}, {"grant_id": "not-a-uuid"},
    {"round": True}, {"round": 0}, {"round": 10001}, {"round": 1.0},
    {"participant_id": "F" * 64}, {"model_sha256": "f" * 63}, {"update_sha256": "F" * 64},
    {"update_bytes": 0}, {"update_bytes": True}, {"update_bytes": MAX_BUNDLE_BYTES+1},
    {"num_examples": 0}, {"num_examples": -1}, {"num_examples": True},
    {"num_examples": 8.0}, {"num_examples": 10**9+1},
    {"masked": True}, {"masked": 0}, {"masked": None},
    {"metrics": {"loss": float("nan")}}, {"metrics": {"loss": float("inf")}},
    {"metrics": {"loss": 10**1000}}, {"metrics": {"loss": True}},
    {"metrics": {"loss": "0.1"}}, {"metrics": {"": 1}}, {"metrics": {" " : 1}},
    {"metrics": {"x" * 65: 1}}, {"metrics": {"\ud800": 1}},
    {"metrics": {str(i): i for i in range(33)}}, {"metrics": []},
])
def test_invalid_update_values_do_not_pass_admission(changes):
    with pytest.raises(FederationValidationError):
        validate_update(update(**changes), **BINDING)


def test_expected_metadata_is_validated_instead_of_using_bool_integer_equality():
    for field, bad in (("round", True), ("run_id", "bad"), ("grant_id", "bad"), ("participant_id", "A" * 64)):
        expected = {**BINDING, field: bad}
        with pytest.raises(FederationValidationError):
            validate_update(update(), **expected)


def test_update_metadata_accepts_exact_upper_bounds_and_empty_or_maximum_metrics():
    value = update(round=10000, update_bytes=MAX_BUNDLE_BYTES, num_examples=10**9,
                   metrics={str(i): float(i) for i in range(32)})
    assert validate_update(value, **{**BINDING, "round": 10000}) == value
    value["metrics"] = {}
    assert validate_update(value, **{**BINDING, "round": 10000})["metrics"] == {}


def test_twenty_distinct_approved_updates_are_admitted_without_a_hidden_smaller_limit():
    peers = [f"{i:064x}" for i in range(1, 21)]
    approved = {peer: {"dataset_sha256": DATASET, "grant_id": GRANT} for peer in peers}
    values = [update(peer) for peer in peers]
    assert round_admit(values, participants=approved) == values


def test_valid_round_preserves_order_and_does_not_alias_metadata_or_authorization():
    values = [update(peer, num_examples=n) for peer, n in zip(PEERS, (8, 12, 20))]
    approved = participants()
    result = round_admit(values, participants=approved)
    assert result == values and [u["num_examples"] for u in result] == [8, 12, 20]
    values[0]["metrics"].clear()
    approved[PEERS[0]]["grant_id"] = OTHER_GRANT
    assert result[0]["metrics"] == {"loss": .25, "correct": 7}
    assert result[0]["grant_id"] == GRANT


def test_three_of_four_approved_participants_meet_the_explicit_minimum_quorum():
    assert len(round_admit([update(peer) for peer in PEERS[:3]], participants=participants(4))) == 3


def test_flower_counterexample_missing_client_cannot_lower_a_three_peer_quorum():
    # Flower 1.42 FedAvg.aggregate_train accepted two valid replies + one error.
    with pytest.raises(FederationValidationError, match="at least three"):
        round_admit([update(peer) for peer in PEERS[:2]])


def test_flower_counterexample_wrong_run_is_rejected_before_aggregation():
    values = [update(peer) for peer in PEERS[:3]]
    values[2]["run_id"] = OTHER_RUN
    with pytest.raises(FederationValidationError, match="expected"):
        round_admit(values)


def test_flower_counterexample_negative_sample_weight_is_rejected_before_aggregation():
    values = [update(peer) for peer in PEERS[:3]]
    values[1]["num_examples"] = -12
    with pytest.raises(FederationValidationError):
        round_admit(values)


def test_round_cannot_count_one_peer_twice_or_admit_an_unapproved_sender():
    for values in ([update(PEERS[0]), update(PEERS[0]), update(PEERS[2])],
                   [update(PEERS[0]), update(PEERS[1]), update(PEERS[3])]):
        with pytest.raises(FederationValidationError, match="unknown or duplicate"):
            round_admit(values)


@pytest.mark.parametrize("approved", [
    {}, participants(2), {str(i).zfill(64): {"dataset_sha256": DATASET, "grant_id": GRANT} for i in range(21)},
    {**participants(), "A" * 64: {"dataset_sha256": DATASET, "grant_id": GRANT}},
    {**participants(), PEERS[0]: {"dataset_sha256": DATASET}},
    {**participants(), PEERS[0]: {"dataset_sha256": DATASET, "grant_id": GRANT, "public": True}},
    {**participants(), PEERS[0]: {"dataset_sha256": "bad", "grant_id": GRANT}},
])
def test_participant_roster_is_strict_bounded_trusted_input(approved):
    with pytest.raises(FederationValidationError):
        round_admit([update(peer) for peer in PEERS[:3]], participants=approved)


def test_production_admission_imports_without_flower_numpy_or_network(tmp_path):
    module = Path(__file__).parents[1] / "suan/federation/updates.py"
    script = r'''
import builtins, importlib.util, socket, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'flwr','numpy'}:
        raise AssertionError('Heavy algorithm dependency imported')
    return original(name,*args,**kwargs)
builtins.__import__=guarded
def audit(event,args):
    if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.sendto'}:
        raise AssertionError('Admission attempted network I/O')
sys.addaudithook(audit)
spec=importlib.util.spec_from_file_location('admission_under_test',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert module.MAX_BUNDLE_BYTES==64*1024*1024
print('standard-library-only admission loaded')
'''
    result = subprocess.run([sys.executable, "-I", "-c", script, str(module)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "standard-library-only admission loaded"
