"""Monitoring events v1: constants, line encoding and validation (standard library only).

The contract is docs/specs/stk-events-v1.md with its JSON Schema
suan/contracts/schemas/event-1.schema.json; ``validate_event`` is its hand-written check
(jsonschema is not a dependency). One event is one JSON object on one ``\\n``-terminated
UTF-8 line of at most 16 KiB. Non-finite numbers travel as the strings ``"NaN"``,
``"Inf"`` and ``"-Inf"``.
"""

import json
import math
import re

VERSION = 1
MAX_LINE = 16 * 1024  # bytes per line, including the newline
MAX_TEXT = 8192  # characters of message.text
READ_LIMIT = 1024 * 1024  # default and largest read size in bytes
TAIL_WINDOW = 64 * 1024  # bytes read from the end for seq recovery and task summaries
EVENTS_FILE = "events.jsonl"  # <task_dir>/events.jsonl, next to stdout.log and outside work/
ENV_PATH = "STK_MONITOR_PATH"
ENV_TASK_ID = "STK_TASK_ID"
ENV_FAKE_TIME = "STK_MONITOR_FAKE_TIME"  # fixed ts for golden tests
# First set wins; any rank other than 0 does not write.
RANK_ENV = ("PMI_RANK", "PMIX_RANK", "OMPI_COMM_WORLD_RANK", "SLURM_PROCID", "MV2_COMM_WORLD_RANK")
TYPES = ("run.started", "run.phase", "progress", "metric.declare", "metrics", "frame", "checkpoint", "artifact",
         "message", "usage", "verification", "run.completed")
SOURCES = ("program", "adapter", "launcher", "runtime")
LEVELS = ("debug", "info", "warning", "error")
VERIFICATION_STATUSES = ("passed", "failed", "pending", "skipped", "unknown")
COMPLETED_STATUSES = ("succeeded", "failed", "cancelled")
NONFINITE = ("NaN", "Inf", "-Inf")
ENVELOPE = ("v", "seq", "ts", "type", "src", "data")
CUSTOM_TYPE = re.compile(r"x\.[a-z0-9_.-]{1,64}")
# Readers pass on types a newer writer may add; consumers ignore types they do not know.
FUTURE_TYPE = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
SOURCE = re.compile(r"[a-z][a-z0-9_.:-]{0,63}")
METRIC_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
SHA256 = re.compile(r"[0-9a-f]{64}")
# dataset-1.schema.json#/$defs/relative_path: POSIX, relative, no drive, no '..' segment, no backslash or NUL.
RELATIVE_PATH = re.compile(r"(?![/\\])(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))[^\\\x00]+")


class EventError(ValueError):
    """An event or line that does not follow monitoring events v1."""


def encode_number(value):
    """A float as JSON can carry it: non-finite values become "NaN", "Inf" or "-Inf"."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if value != value else "Inf" if value > 0 else "-Inf"
    return value


def decode_number(value):
    """Float from an event number (``"NaN"``/``"Inf"``/``"-Inf"`` included); ``None`` stays ``None``."""
    if value is None:
        return None
    if isinstance(value, str) and value in NONFINITE:
        return {"NaN": math.nan, "Inf": math.inf, "-Inf": -math.inf}[value]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventError(f"Not an event number: {value!r}")
    return float(value)


def sanitize(value):
    """A JSON-ready copy: non-finite floats become strings, tuples lists, integer-like objects ints."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, float):
        return encode_number(float(value))
    if isinstance(value, int):
        return int(value)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EventError(f"Object keys must be strings, not {type(key).__name__}")
            result[key] = sanitize(item)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if getattr(value, "shape", None) == () and hasattr(value, "ndim") and type(value).__name__ == "ndarray":
        return sanitize(value[()])  # a 0-d NumPy array: its scalar
    if hasattr(value, "__index__"):  # e.g. NumPy integers
        try:
            return int(value.__index__())
        except TypeError:  # __index__ exists but refuses (e.g. a float array)
            pass
    if hasattr(value, "__float__") and not hasattr(value, "__len__"):  # e.g. NumPy floating scalars
        return encode_number(float(value))
    raise EventError(f"Cannot encode a {type(value).__name__} in an event")


def _integer(value, minimum=None):
    """JSON Schema integer: an int or an integral float, never a bool."""
    if isinstance(value, bool) or not (isinstance(value, int) or (isinstance(value, float) and value.is_integer())):
        return False
    return minimum is None or value >= minimum


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _num(value):
    return _number(value) or (isinstance(value, str) and value in NONFINITE)


def _nullable(check):
    return lambda value: value is None or check(value)


def _count(minimum):
    return lambda value: _integer(value, minimum)


def _one_of(choices):
    return lambda value: isinstance(value, str) and value in choices


def _string(value):
    return isinstance(value, str)


def _strings(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _boolean(value):
    return isinstance(value, bool)


def relative_path_ok(value):
    return isinstance(value, str) and 1 <= len(value) <= 1024 and RELATIVE_PATH.fullmatch(value) is not None


def _values(value):
    return isinstance(value, dict) and len(value) >= 1 and all(_num(item) for item in value.values())


_opt_num = _nullable(_num)
_opt_string = _nullable(_string)
_opt_step = _nullable(_count(0))
# type -> (required keys, {key: check}); keys not listed are ignored, as consumers must.
DATA = {
    "run.started": (("app",), {"app": _string, "version": _opt_string, "total_steps": _opt_step,
                               "ranks": _nullable(_count(1)), "host": _opt_string, "pid": _nullable(_integer)}),
    "run.phase": (("name", "state"), {"name": _string, "state": _one_of(("begin", "end")), "elapsed_s": _opt_num}),
    "progress": ((), {"step": _opt_step, "completed_steps": _opt_step, "total_steps": _opt_step,
                      "fraction": _nullable(lambda v: _number(v) and 0 <= v <= 1), "time": _opt_num,
                      "time_end": _opt_num, "time_unit": _opt_string, "phase": _opt_string, "eta_s": _opt_num,
                      "indeterminate": _boolean}),
    "metric.declare": (("name", "unit"), {"name": lambda v: isinstance(v, str) and METRIC_NAME.fullmatch(v) is not None,
                                          "unit": _string, "quantity": _opt_string, "label": _opt_string,
                                          "group": _opt_string}),
    "metrics": (("values",), {"step": _opt_step, "time": _opt_num, "values": _values}),
    "frame": (("dataset", "step", "path"), {
        "dataset": _string, "step": _count(0), "time": _opt_num, "path": relative_path_ok,
        "selector": lambda v: v is None or isinstance(v, (str, dict)), "fields": _strings, "reader": _opt_string,
        "components": _nullable(_count(1)), "size": _opt_step,
        "sha256": _nullable(lambda v: isinstance(v, str) and SHA256.fullmatch(v) is not None)}),
    "checkpoint": (("step", "path"), {"step": _count(0), "path": relative_path_ok, "restartable": _boolean}),
    "artifact": (("path", "role"), {"path": relative_path_ok, "role": _string, "media_type": _opt_string}),
    "message": (("level", "text"), {"level": _one_of(LEVELS),
                                    "text": lambda v: isinstance(v, str) and len(v) <= MAX_TEXT, "code": _opt_string}),
    "usage": ((), {"cpu_s": _opt_num, "rss_peak_bytes": _opt_step, "gpu": _nullable(lambda v: isinstance(v, dict))}),
    "verification": (("verifier", "status"), {"verifier": _string, "status": _one_of(VERIFICATION_STATUSES),
                                              "failed_checks": _strings}),
    "run.completed": (("status",), {"status": _one_of(COMPLETED_STATUSES), "classification": _opt_string,
                                    "reason": _opt_string}),
}


def validate_data(event_type, data):
    """Check ``data`` of a known type; unknown keys are allowed. Returns ``data``."""
    if not isinstance(data, dict):
        raise EventError("data must be an object")
    required, checks = DATA[event_type]
    for key in required:
        if key not in data:
            raise EventError(f"{event_type}: data.{key} is required")
    for key, check in checks.items():
        if key in data and not check(data[key]):
            raise EventError(f"{event_type}: invalid data.{key}: {data[key]!r}"[:300])
    return data


def validate_event(event, strict=True):
    """Check one decoded event against event-1.schema.json and return it.

    ``strict`` (writers) accepts only the v1 types and ``x.*``. Readers pass
    ``strict=False`` to hand on well-formed types from newer writers, whose data is
    not checked; consumers ignore types they do not know.
    """
    if not isinstance(event, dict):
        raise EventError("An event must be a JSON object")
    unknown = [key for key in event if key not in ENVELOPE]
    if unknown:
        raise EventError("Unknown envelope key: " + ", ".join(sorted(map(str, unknown)))[:200])
    missing = [key for key in ENVELOPE if key not in event]
    if missing:
        raise EventError("Missing envelope key: " + ", ".join(missing))
    if not _integer(event["v"]) or event["v"] != VERSION:
        raise EventError(f"Unsupported event version {event['v']!r}"[:200])
    if not _integer(event["seq"], 0):
        raise EventError("seq must be an integer >= 0")
    if not _number(event["ts"]) or event["ts"] < 0:
        raise EventError("ts must be Unix seconds >= 0")
    if not isinstance(event["src"], str) or not SOURCE.fullmatch(event["src"]):
        raise EventError(f"Invalid src {event['src']!r}"[:200])
    kind = event["type"]
    if not isinstance(kind, str):
        raise EventError("type must be a string")
    if kind in DATA:
        validate_data(kind, event["data"])
    elif CUSTOM_TYPE.fullmatch(kind) or (not strict and FUTURE_TYPE.fullmatch(kind)):
        if not isinstance(event["data"], dict):
            raise EventError("data must be an object")
    else:
        raise EventError(f"Unknown event type {kind!r}"[:200])
    return event


def make_event(seq, event_type, data, src="program", ts=0.0):
    """An envelope in the spec's key order; ``data`` is sanitized (non-finite numbers become strings)."""
    return {"v": VERSION, "seq": seq, "ts": ts, "type": event_type, "src": src,
            "data": sanitize({} if data is None else data)}


def encode_line(event):
    """UTF-8 bytes of one event line ending in ``\\n``; raises EventError when longer than MAX_LINE."""
    try:
        text = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        line = (text + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:  # UnicodeEncodeError (lone surrogates) is a ValueError
        raise EventError(f"Cannot encode event: {exc}") from exc
    if len(line) > MAX_LINE:
        raise EventError(f"Event line is {len(line)} bytes; the limit is {MAX_LINE}")
    return line


def _reject_constant(name):
    token = {"Infinity": "Inf", "-Infinity": "-Inf"}.get(name, name)
    raise ValueError(f"non-standard JSON constant {name}; write the string \"{token}\"")


def _float(text):
    # A number too large for a double is valid JSON; carry it as the matching token.
    return encode_number(float(text))


def decode_line(line, strict=False):
    """Parse and validate one line (bytes, with or without its newline) into an event dict."""
    if len(line) > MAX_LINE:
        raise EventError(f"Line exceeds {MAX_LINE} bytes")
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EventError("Line is not UTF-8") from exc
    if not text.strip():
        raise EventError("Empty line")
    try:
        event = json.loads(text, parse_constant=_reject_constant, parse_float=_float)
    except (ValueError, RecursionError) as exc:
        raise EventError(f"Invalid JSON: {exc}"[:300]) from exc
    return validate_event(event, strict=strict)
