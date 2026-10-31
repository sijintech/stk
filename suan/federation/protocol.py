"""Closed, standard-library-only messages for owner-approved federation runs.

These validators do not authenticate identities. The Hub binds public identity
fingerprints to paired devices through an explicit owner-approved run manifest;
each node independently checks its local consent. No path, executable, module,
environment, dataset bytes or training-option override is accepted in messages.
The numeric training spec is a fixed installed adapter, not a cooperative dataset
format. It uses one shared raw-number parameter space without local rescaling.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from uuid import UUID

from .updates import FederationValidationError, MAX_BUNDLE_BYTES, MAX_ROUND, validate_update

SPEC_FORMAT = "stk.federation-training-spec/1"
RUN_FORMAT = "stk.federation-run/1"
MESSAGE_FORMAT = "stk.federation-message/1"
TRAINER = "linear-regression/1"
MAX_MESSAGE_BYTES = 64 * 1024
OPERATIONS = frozenset({"train", "status", "collect", "cancel"})
RESULT_FORMAT = "stk.federation-node-result/1"
STATES = frozenset({"prepared", "queued", "running", "ready", "delivered", "failed",
                    "cancelled", "unknown", "uncertain"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DEVICE = re.compile(r"[0-9a-f]{32}\Z")


def _reject():
    raise FederationValidationError("Invalid frozen federation specification or message") from None


def _fields(value, keys):
    if type(value) is not dict or value.keys() != set(keys):
        _reject()


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _reject()
    return value


def _hex(value, pattern):
    if type(value) is not str or not pattern.fullmatch(value):
        _reject()
    return value


def _uuid(value):
    if type(value) is not str or len(value) != 36:
        _reject()
    try:
        if str(UUID(value)) != value:
            _reject()
    except ValueError:
        _reject()
    return value


def _number(value, low, high, *, positive=False):
    if type(value) not in (int, float):
        _reject()
    try:
        number = float(value)
    except (ValueError, OverflowError):
        _reject()
    if not math.isfinite(number) or not low <= number <= high or (positive and number == 0):
        _reject()
    return 0.0 if number == 0 else number


def _text(value, maximum):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        _reject()
    try:
        raw = value.encode("utf-8")
    except UnicodeError:
        _reject()
    if len(raw) > maximum or any(ord(x) < 32 or ord(x) == 127 for x in value):
        _reject()
    return value


def canonical_json(value):
    """Encode a bounded validated JSON object without credentials or raw data."""
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _reject()
    if len(raw) > MAX_MESSAGE_BYTES:
        _reject()
    return raw


def _columns(value, maximum):
    if type(value) is not list or not 1 <= len(value) <= maximum:
        _reject()
    result, seen = [], set()
    for item in value:
        _fields(item, {"name", "unit"})
        name, unit = _text(item["name"], 128), _text(item["unit"], 64)
        if name in seen:
            _reject()
        seen.add(name)
        result.append({"name": name, "unit": unit})
    return result


def validate_training_spec(value):
    """Return the complete frozen installed linear trainer specification.

    All options are explicit, preserving field order and units. The trainer uses
    raw numeric values; it never fits a separate normalization per participant.
    FedProx adds the proximal penalty against this round's exact base parameters.
    """
    _fields(value, {"format", "trainer", "features", "targets", "dtype", "normalization",
                    "steps", "learning_rate", "strategy", "proximal_mu"})
    if (any(type(value[key]) is not str for key in ("format", "trainer", "dtype", "normalization", "strategy"))
            or value["format"] != SPEC_FORMAT or value["trainer"] != TRAINER
            or value["dtype"] not in ("f32", "f64") or value["normalization"] != "none"
            or value["strategy"] not in ("fedavg", "fedprox")):
        _reject()
    mu = _number(value["proximal_mu"], 0, 100)
    if (value["strategy"] == "fedavg" and mu != 0) or (value["strategy"] == "fedprox" and mu <= 0):
        _reject()
    result = {"format": SPEC_FORMAT, "trainer": TRAINER,
              "features": _columns(value["features"], 64), "targets": _columns(value["targets"], 16),
              "dtype": value["dtype"], "normalization": "none",
              "steps": _integer(value["steps"], 1, 1000),
              "learning_rate": _number(value["learning_rate"], 0, 1, positive=True),
              "strategy": value["strategy"], "proximal_mu": mu}
    canonical_json(result)
    return result


def training_spec_sha256(value):
    return hashlib.sha256(canonical_json(validate_training_spec(value))).hexdigest()


def model_layout(value):
    spec = validate_training_spec(value)
    return [{"name": "weights", "dtype": spec["dtype"],
             "shape": [len(spec["features"]), len(spec["targets"])]},
            {"name": "bias", "dtype": spec["dtype"], "shape": [len(spec["targets"])]}]


def validate_run_manifest(value):
    """Validate an owner-approved identity/device map, without granting consent.

    Only the authenticated owner may register this map at the Hub. The client
    device must already be paired; fingerprints are owner-checked public pins,
    not a claim that bearer authentication proves possession of private keys.
    """
    _fields(value, {"format", "run_id", "coordinator_device_id", "coordinator_id",
                    "spec_sha256", "participants", "max_rounds"})
    if value["format"] != RUN_FORMAT:
        _reject()
    source = value["participants"]
    if type(source) is not list or not 3 <= len(source) <= 20:
        _reject()
    participants, nodes, peers, grants = [], set(), set(), set()
    for item in source:
        _fields(item, {"node_id", "participant_id", "grant_id", "dataset_sha256"})
        node = _hex(item["node_id"], _DEVICE)
        peer = _hex(item["participant_id"], _SHA)
        grant = _uuid(item["grant_id"])
        if node in nodes or peer in peers or grant in grants:
            _reject()
        nodes.add(node); peers.add(peer); grants.add(grant)
        participants.append({"node_id": node, "participant_id": peer, "grant_id": grant,
                             "dataset_sha256": _hex(item["dataset_sha256"], _SHA)})
    result = {"format": RUN_FORMAT, "run_id": _uuid(value["run_id"]),
              "coordinator_device_id": _hex(value["coordinator_device_id"], _DEVICE),
              "coordinator_id": _hex(value["coordinator_id"], _SHA),
              "spec_sha256": _hex(value["spec_sha256"], _SHA), "participants": participants,
              "max_rounds": _integer(value["max_rounds"], 1, MAX_ROUND)}
    if result["coordinator_id"] in peers:
        _reject()
    canonical_json(result)
    return result


def validate_message(value):
    """Validate a closed action payload; each receiver rechecks trusted bindings.

    Status, cancel and collect retain the original model binding too. They never
    accept a task ID, filename, script, interpreter or override training options.
    """
    _fields(value, {"format", "operation", "run_id", "round", "coordinator_id", "participant_id",
                    "grant_id", "spec_sha256", "dataset_sha256", "model"})
    if (type(value["format"]) is not str or value["format"] != MESSAGE_FORMAT
            or type(value["operation"]) is not str or value["operation"] not in OPERATIONS):
        _reject()
    _fields(value["model"], {"sha256", "bytes"})
    result = {"format": MESSAGE_FORMAT, "operation": value["operation"], "run_id": _uuid(value["run_id"]),
              "round": _integer(value["round"], 1, MAX_ROUND),
              "coordinator_id": _hex(value["coordinator_id"], _SHA),
              "participant_id": _hex(value["participant_id"], _SHA),
              "grant_id": _uuid(value["grant_id"]), "spec_sha256": _hex(value["spec_sha256"], _SHA),
              "dataset_sha256": _hex(value["dataset_sha256"], _SHA),
              "model": {"sha256": _hex(value["model"]["sha256"], _SHA),
                        "bytes": _integer(value["model"]["bytes"], 1, MAX_BUNDLE_BYTES)}}
    canonical_json(result)
    return result


def validate_node_result(value, *, message):
    """Bind a closed receipt to the original action without accepting Runtime internals.

    Only a collect receipt can carry update metadata, and only after the node
    recorded delivery. The receiver still verifies actual update bytes separately.
    Status may report an already delivered update without republishing its metadata.
    """
    request = validate_message(message)
    _fields(value, {"format", "run_id", "round", "participant_id", "grant_id", "state",
                    "task_id", "update_id", "update"})
    if (type(value["format"]) is not str or value["format"] != RESULT_FORMAT
            or type(value["state"]) is not str or value["state"] not in STATES):
        _reject()
    result = {"format": RESULT_FORMAT, "run_id": _uuid(value["run_id"]),
              "round": _integer(value["round"], 1, MAX_ROUND),
              "participant_id": _hex(value["participant_id"], _SHA), "grant_id": _uuid(value["grant_id"]),
              "state": value["state"],
              "task_id": None if value["task_id"] is None else _hex(value["task_id"], _DEVICE),
              "update_id": None if value["update_id"] is None else _uuid(value["update_id"]), "update": None}
    if any(result[key] != request[key] for key in ("run_id", "round", "participant_id", "grant_id")):
        _reject()
    if result["state"] in {"ready", "delivered", "uncertain"} and result["update_id"] is None:
        # A submission can also be uncertain before an update exists.
        if result["state"] != "uncertain":
            _reject()
    if value["update"] is not None:
        if request["operation"] != "collect" or result["state"] != "delivered" or result["update_id"] is None:
            _reject()
        result["update"] = validate_update(value["update"],
            run_id=request["run_id"], round=request["round"], participant_id=request["participant_id"],
            model_sha256=request["model"]["sha256"], spec_sha256=request["spec_sha256"],
            dataset_sha256=request["dataset_sha256"], grant_id=request["grant_id"])
    elif request["operation"] == "collect" and result["state"] == "delivered":
        _reject()
    canonical_json(result)
    return result
