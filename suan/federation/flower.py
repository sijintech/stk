"""One explicit, bounded FedAvg aggregation in a separately installed environment.

The selected interpreter must contain this STK package and the pinned optional
algorithm dependencies. No Flower import, installation, listener, training or
model publication happens in the calling STK environment. Expected identities
come from the trusted coordinator; this adapter does not authenticate a sender.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

from .updates import (FederationValidationError, MAX_BUNDLE_BYTES, decode_arrays,
                      validate_round)

FLOWER_VERSION = "1.42.0"
MAX_JOB_BYTES = 256 * 1024 * 1024
MAX_JOB_METADATA_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
JOB_FORMAT = "stk.federation-aggregate-job/1"
RESULT_FORMAT = "stk.federation-aggregate-result/1"


class FlowerAggregationError(RuntimeError):
    """A local algorithm attempt failed; no training or publication is retried."""


def _json(value, maximum):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise FederationValidationError("Invalid aggregation metadata") from None
    if len(raw) > maximum:
        raise FederationValidationError("Aggregation metadata exceeds its byte limit")
    return raw


def _strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate result key")
            value[key] = item
        return value

    def constant(_):
        raise ValueError("Nonfinite result")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("Invalid aggregation JSON") from None


def _same_typed(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(_same_typed(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(_same_typed(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _read(path, maximum):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400):
        raise FlowerAggregationError("Algorithm artifact is not an ordinary file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode) or opened.st_size > maximum):
            raise FlowerAggregationError("Algorithm artifact exceeds its byte limit")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    final = path.lstat()
    if (len(raw) > maximum or len(raw) != opened.st_size
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
               (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            or (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) !=
               (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
        raise FlowerAggregationError("Algorithm artifact exceeds its byte limit")
    return raw


class FlowerAggregator:
    """A passive adapter; only aggregate explicitly launches one local process.

    Each attempt receives validated finite model/delta bundles, uses an absolute
    process timeout, and returns an unregistered candidate. At least three unique
    approved updates are required before the optional framework is invoked.
    """

    def __init__(self, python, *, timeout=30):
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 300):
            raise ValueError("Algorithm timeout must be finite and at most 300 seconds")
        if not isinstance(python, (str, os.PathLike)) or not str(python):
            raise ValueError("An explicit algorithm interpreter is required")
        self.python = str(Path(python).expanduser().absolute())
        self.timeout = timeout

    def aggregate(self, model, updates, *, participants, run_id, round, spec_sha256):
        """Validate every delta and aggregate once; return model bytes and receipt.

        ``updates`` is a list/tuple of (metadata, raw_delta_bundle) pairs. The
        frozen model's actual SHA is the expected base for every participant.
        Consent, current authenticated identity and round scheduling are the
        caller's responsibility; successful math is not model admission.
        """
        if type(model) is not bytes:
            raise FederationValidationError("The frozen model must be immutable bytes")
        base = decode_arrays(model, expected_kind="model")
        if type(participants) is not dict or not 3 <= len(participants) <= 20:
            raise FederationValidationError("The approved participant map is outside its bounds")
        if any(type(item) is not dict or set(item) != {"dataset_sha256", "grant_id"}
               for item in participants.values()):
            raise FederationValidationError("The approved participant bindings are invalid")
        participants = {peer: dict(item) for peer, item in participants.items()}
        if type(updates) not in (list, tuple) or not 3 <= len(updates) <= 20:
            raise FederationValidationError("Aggregation requires three to twenty updates")
        metadata, payloads = [], []
        total = len(model)
        for pair in updates:
            if type(pair) not in (list, tuple) or len(pair) != 2:
                raise FederationValidationError("An update requires metadata and bytes")
            item, payload = pair
            if type(payload) is not bytes:
                raise FederationValidationError("An update must contain immutable bytes")
            total += len(payload)
            if total > MAX_JOB_BYTES:
                raise FederationValidationError("Aggregation inputs exceed their combined byte limit")
            metadata.append(item)
            payloads.append(payload)
        admitted = validate_round(metadata, participants=participants, run_id=run_id,
            round=round, model_sha256=base["sha256"], spec_sha256=spec_sha256)
        for item, payload in zip(admitted, payloads):
            delta = decode_arrays(payload, expected_kind="delta", expected_layout=base["layout"])
            if (item["update_sha256"] != delta["sha256"] or item["update_bytes"] != delta["bytes"]):
                raise FederationValidationError("Update bytes do not match their receipt")
        keys = set(admitted[0]["metrics"])
        if "num-examples" in keys or any(set(item["metrics"]) != keys for item in admitted):
            raise FederationValidationError("Round metric names must agree")
        job = {"format": JOB_FORMAT, "run_id": run_id, "round": round,
               "spec_sha256": spec_sha256, "participants": participants,
               "model_sha256": base["sha256"], "updates": admitted}
        encoded = _json(job, MAX_JOB_METADATA_BYTES)
        # A fresh private directory carries bounded binary artifacts; large model
        # bytes never pass through an unbounded subprocess stdout/JSON pipe.
        with tempfile.TemporaryDirectory(prefix="stk-federation-aggregate-") as name:
            directory = Path(name)
            (directory / "job.json").write_bytes(encoded)
            (directory / "model.bin").write_bytes(model)
            for index, payload in enumerate(payloads):
                (directory / f"update-{index}.bin").write_bytes(payload)
            # Only known noncredential process settings cross the boundary.
            allowed = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
            environment = {key: os.environ[key] for key in allowed if key in os.environ}
            environment.update({"STK_TOKEN_PLAN_API_KEY": "", "FLWR_TELEMETRY_ENABLED": "0",
                "FLWR_TELEMETRY_LOGGING": "0", "FLWR_DISABLE_UPDATE_CHECK": "1",
                "FLWR_HOME": str(directory / "flower-state"), "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
            started = time.monotonic()
            try:
                result = subprocess.run([self.python, "-I", "-m", "suan.federation.flower_worker", str(directory)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=environment, timeout=self.timeout, check=False)
            except subprocess.TimeoutExpired:
                raise FlowerAggregationError("Local aggregation exceeded its deadline") from None
            except OSError:
                raise FlowerAggregationError("The isolated algorithm interpreter is unavailable") from None
            if result.returncode != 0:
                raise FlowerAggregationError("The isolated algorithm attempt failed")
            try:
                receipt = _strict_json(_read(directory / "result.json", MAX_RECEIPT_BYTES))
                candidate = _read(directory / "result.bin", MAX_BUNDLE_BYTES)
                decoded = decode_arrays(candidate, expected_kind="model", expected_layout=base["layout"])
                expected = {"format": RESULT_FORMAT, "run_id": run_id, "round": round,
                    "source_model_sha256": base["sha256"], "spec_sha256": spec_sha256,
                    "participants": [item["participant_id"] for item in admitted],
                    "model_sha256": decoded["sha256"], "model_bytes": decoded["bytes"],
                    "num_examples": sum(item["num_examples"] for item in admitted),
                    "framework": {"name": "flwr", "version": FLOWER_VERSION}}
                if (type(receipt) is not dict or set(receipt) != set(expected) | {"metrics"}
                        or any(not _same_typed(receipt[key], value) for key, value in expected.items())):
                    raise ValueError
                metrics = receipt["metrics"]
                if (type(metrics) is not dict or set(metrics) != keys
                        or any(type(x) not in (int, float) or not math.isfinite(x) for x in metrics.values())):
                    raise ValueError
            except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
                raise FlowerAggregationError("The algorithm result could not be verified") from None
            return {"model": candidate, "receipt": receipt, "seconds": time.monotonic() - started}
