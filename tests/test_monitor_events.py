"""Monitoring events v1: the hand-written validator follows event-1.schema.json."""

import json
import math

import pytest

from suan.contracts import load_all_schemas, load_schema
from suan.monitor import events
from suan.monitor.events import (EventError, decode_line, decode_number, encode_line, encode_number, make_event,
                                 sanitize, validate_event)

GOOD = [
    ("run.started", {"app": "muFerro", "version": None, "total_steps": 1000, "ranks": 4, "host": "n1", "pid": 7}),
    ("run.phase", {"name": "solve", "state": "begin", "elapsed_s": "NaN"}),
    ("progress", {}),
    ("progress", {"step": 120, "completed_steps": 120, "total_steps": 1000, "fraction": 0.12, "time": 1.5,
                  "time_end": None, "time_unit": "ps", "phase": "relax", "eta_s": "Inf", "indeterminate": False}),
    ("metric.declare", {"name": "total_energy", "unit": "normalized", "label": "Total Energy", "group": "energy"}),
    ("metrics", {"step": 120, "time": None, "values": {"total_energy": -1.23e-3, "elastic_energy": "NaN",
                                                       "x": "-Inf"}}),
    ("frame", {"dataset": "Polar", "step": 0, "path": "case/Polar.00000000.dat", "reader": "mupro.dat@1",
               "components": 3, "size": 10, "sha256": "a" * 64, "selector": {"component": 0}, "fields": ["P"]}),
    ("checkpoint", {"step": 5, "path": "restart/Polar.in", "restartable": True}),
    ("artifact", {"path": "report.pdf", "role": "report", "media_type": "application/pdf"}),
    ("message", {"level": "warning", "text": "x" * 8192, "code": "nonfinite_energy"}),
    ("usage", {"cpu_s": 1.5, "rss_peak_bytes": 1024, "gpu": None}),
    ("verification", {"verifier": "stk-mupro-1", "status": "failed", "failed_checks": ["energy"]}),
    ("run.completed", {"status": "succeeded", "classification": None, "reason": None}),
    ("x.custom-thing", {"anything": [1, 2]}),
    ("metrics", {"values": {"a": 1}, "unknown_key": "ignored"}),
]

BAD = [
    ("run.started", {}),
    ("run.started", {"app": "a", "ranks": 0}),
    ("run.phase", {"name": "solve", "state": "middle"}),
    ("progress", {"fraction": 1.5}),
    ("progress", {"fraction": "NaN"}),
    ("progress", {"step": -1}),
    ("progress", {"step": True}),
    ("progress", {"indeterminate": 1}),
    ("metric.declare", {"name": "bad name", "unit": "1"}),
    ("metric.declare", {"name": "e"}),
    ("metrics", {"values": {}}),
    ("metrics", {"values": {"a": "nan"}}),
    ("metrics", {"values": {"a": None}}),
    ("metrics", {"values": {"a": True}}),
    ("frame", {"dataset": "Polar", "step": 1, "path": "../Polar.dat"}),
    ("frame", {"dataset": "Polar", "step": 1, "path": "/abs/Polar.dat"}),
    ("frame", {"dataset": "Polar", "step": 1, "path": "C:/Polar.dat"}),
    ("frame", {"dataset": "Polar", "step": 1, "path": "a\\b.dat"}),
    ("frame", {"dataset": "Polar", "step": 1, "path": ""}),
    ("frame", {"dataset": "Polar", "step": 1, "path": "a/../b"}),
    ("frame", {"dataset": "Polar", "step": None, "path": "a"}),
    ("frame", {"dataset": "Polar", "step": 1, "path": "a", "sha256": "ABC"}),
    ("frame", {"dataset": "Polar", "step": 1, "path": "a", "components": 0}),
    ("checkpoint", {"step": 1}),
    ("artifact", {"path": "a"}),
    ("message", {"level": "fatal", "text": "x"}),
    ("message", {"level": "info", "text": "x" * 8193}),
    ("usage", {"rss_peak_bytes": -1}),
    ("verification", {"verifier": "v", "status": "not_run"}),
    ("verification", {"verifier": "v", "status": "passed", "failed_checks": "energy"}),
    ("run.completed", {"status": "done"}),
    ("unknown.type", {}),
    ("x.", {}),
    ("x.custom", []),
]


def event(kind, data, **changes):
    return {"v": 1, "seq": 0, "ts": 1790000000.125, "type": kind, "src": "program", "data": data, **changes}


@pytest.mark.parametrize("kind,data", GOOD)
def test_valid_events(kind, data):
    assert validate_event(event(kind, data)) == event(kind, data)
    assert decode_line(encode_line(event(kind, data)), strict=True) == event(kind, data)


@pytest.mark.parametrize("kind,data", BAD)
def test_invalid_events(kind, data):
    with pytest.raises(EventError):
        validate_event(event(kind, data))


@pytest.mark.parametrize("changes", [
    {"v": 2}, {"v": True}, {"seq": -1}, {"seq": 1.5}, {"seq": "1"}, {"ts": -1}, {"ts": "NaN"}, {"ts": True},
    {"src": "Program"}, {"src": ""}, {"src": 3}, {"type": 3}, {"data": []}, {"extra": 1},
])
def test_invalid_envelopes(changes):
    with pytest.raises(EventError):
        validate_event({**event("progress", {}), **changes})
    missing = event("progress", {})
    missing.pop("data")
    with pytest.raises(EventError, match="Missing"):
        validate_event(missing)


def test_readers_pass_on_future_types_but_writers_do_not():
    future = event("run.heartbeat", {"anything": 1})
    assert validate_event(future, strict=False) == future
    with pytest.raises(EventError, match="Unknown event type"):
        validate_event(future)
    with pytest.raises(EventError):
        validate_event(event("Not A Type", {}), strict=False)
    # Known types keep their data checks in both modes.
    with pytest.raises(EventError):
        validate_event(event("progress", {"fraction": 2}), strict=False)


def test_constants_match_the_frozen_schema():
    schema = load_schema("event-1")
    assert list(events.TYPES) == schema["properties"]["type"]["anyOf"][0]["enum"]
    assert set(events.ENVELOPE) == set(schema["required"]) == set(schema["properties"])
    assert schema["$defs"]["num"]["oneOf"][1]["enum"] == list(events.NONFINITE)
    assert schema["$defs"]["message"]["properties"]["level"]["enum"] == list(events.LEVELS)
    assert schema["$defs"]["message"]["properties"]["text"]["maxLength"] == events.MAX_TEXT
    assert schema["$defs"]["verification"]["properties"]["status"]["enum"] == list(events.VERIFICATION_STATUSES)
    assert schema["$defs"]["run_completed"]["properties"]["status"]["enum"] == list(events.COMPLETED_STATUSES)
    assert schema["$defs"]["metric_declare"]["properties"]["name"]["pattern"] == "^" + events.METRIC_NAME.pattern + "$"
    assert schema["properties"]["src"]["pattern"] == "^" + events.SOURCE.pattern + "$"
    assert schema["properties"]["type"]["anyOf"][1]["pattern"] == "^" + events.CUSTOM_TYPE.pattern + "$"
    for kind in events.TYPES:
        required, checks = events.DATA[kind]
        definition = schema["$defs"][kind.replace(".", "_")]
        assert list(required) == definition.get("required", []), kind
        assert set(checks) == set(definition["properties"]), kind
    assert "16 KiB" in schema["description"] and events.MAX_LINE == 16384


def test_relative_path_matches_the_dataset_schema_pattern():
    import re
    pattern = load_schema("dataset-1")["$defs"]["relative_path"]["pattern"]
    # ECMA-262 and Python agree on this pattern once \u0000 is spelled \x00.
    ecma = re.compile(pattern.replace("\\u0000", "\\x00"))
    for path in ["a", "a/b.dat", "case16/Polar.00000100.dat", "a..b", "..a/b", "a/b..", ".hidden", "a b/ü.dat",
                 "..", "../a", "a/..", "a/../b", "/a", "\\a", "a\\b", "C:/a", "c:a", "a\x00b", "a/./b"]:
        assert events.relative_path_ok(path) == bool(ecma.search(path)), path


def test_jsonschema_agrees_when_available():
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    registry = referencing.Registry().with_resources(
        (uri, referencing.Resource.from_contents(schema)) for uri, schema in load_all_schemas().items())
    validator = jsonschema.Draft202012Validator(load_schema("event-1"), registry=registry)
    for kind, data in GOOD:
        assert validator.is_valid(event(kind, data)), (kind, data)
    for kind, data in BAD:
        assert not validator.is_valid(event(kind, data)), (kind, data)


def test_nonfinite_numbers_travel_as_strings():
    assert [encode_number(v) for v in (math.nan, math.inf, -math.inf, 1.5, 2, None)] == \
        ["NaN", "Inf", "-Inf", 1.5, 2, None]
    assert math.isnan(decode_number("NaN")) and decode_number("-Inf") == -math.inf
    assert decode_number(3) == 3.0 and decode_number(None) is None
    with pytest.raises(EventError):
        decode_number("nan")
    data = sanitize({"values": {"a": math.nan, "b": (1, math.inf)}, "flag": True})
    assert data == {"values": {"a": "NaN", "b": [1, "Inf"]}, "flag": True}
    line = encode_line(make_event(3, "metrics", {"values": {"e": -math.inf}}, "adapter", 1.0))
    assert line == b'{"v":1,"seq":3,"ts":1.0,"type":"metrics","src":"adapter","data":{"values":{"e":"-Inf"}}}\n'
    with pytest.raises(EventError):
        sanitize({1: "not a string key"})
    with pytest.raises(EventError):
        sanitize({"a": object()})


def test_numpy_scalars_are_encoded_when_numpy_is_present():
    np = pytest.importorskip("numpy")
    assert sanitize({"a": np.float32(np.nan), "b": np.int64(4), "c": np.float64(0.5)}) == {"a": "NaN", "b": 4, "c": 0.5}
    # 0-d arrays (e.g. array.sum() on an np.matrix, or np.array(x)) are their scalar; they used to raise TypeError.
    assert sanitize({"a": np.array(1.5), "b": np.array(3), "c": np.array(np.inf), "d": [np.array(2.0)]}) == {
        "a": 1.5, "b": 3, "c": "Inf", "d": [2.0]}
    with pytest.raises(EventError):
        sanitize({"a": np.array([1.0, 2.0])})  # arrays with elements are not numbers


def test_line_encoding_and_decoding_rules():
    big = make_event(0, "x.big", {"blob": "y" * events.MAX_LINE}, "program", 0.0)
    with pytest.raises(EventError, match="limit is 16384"):
        encode_line(big)
    line = encode_line(make_event(0, "message", {"level": "info", "text": "第一行\n第二行"}, "program", 0.5))
    assert line.count(b"\n") == 1 and line.endswith(b"\n") and "第一行".encode() in line
    assert decode_line(line)["data"]["text"] == "第一行\n第二行"
    for raw, message in [(b"\xff\n", "not UTF-8"), (b"\n", "Empty"), (b"{not json}\n", "Invalid JSON"),
                         (b"[1]\n", "JSON object"), (b"x" * (events.MAX_LINE + 1), "exceeds")]:
        with pytest.raises(EventError, match=message):
            decode_line(raw)
    tokens = json.dumps(event("metrics", {"values": {"a": float("nan")}})).encode()
    with pytest.raises(EventError, match="non-standard JSON constant NaN"):
        decode_line(tokens)
    # Numbers too large for a double are valid JSON; they become the matching token.
    overflow = b'{"v":1,"seq":0,"ts":1,"type":"metrics","src":"program","data":{"values":{"a":1e999,"b":-1e999}}}'
    assert decode_line(overflow)["data"]["values"] == {"a": "Inf", "b": "-Inf"}
    with pytest.raises(EventError):
        encode_line(make_event(0, "message", {"level": "info", "text": "\ud800"}, "program", 0.0))
