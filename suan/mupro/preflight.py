"""Compute-side MuPRO preflight task: write one stk.mupro-preflight/1 observation artifact.

``python -m suan.mupro.preflight`` runs as an explicitly submitted Runtime task (see
``suan.mupro.spec.preflight_spec``) in the selected compute or scheduler environment. It
observes the worker's own configured environment (``MUPRO_SDK_PREFIX``,
``STK_MUPRO_ENV_SCRIPTS``, ``MUPROROOT``) through the existing local collector, exactly
once, and writes the published observation (docs/specs/mupro-preflight-1.md) to
``stk-mupro-preflight.json`` in the task work directory. It accepts no configuration
options: the client cannot supply SDK, program, script or licence paths.

Configured trusted environment scripts are sourced by the collector and may have
effects; this is not a passive probe. MuPRO, MPI launchers and licence checkouts are not
started and licence directory contents are not read.

Exit status: 0 for ``checks_passed`` or ``checks_incomplete`` and 1 for
``checks_failed``; each of these leaves a valid observation. 2 means the output name
was already occupied (nothing collected, prior file untouched) or the arguments were
invalid. 3 means collection or writing failed; no valid observation is left.

``parse_observation`` validates downloaded observation bytes; it is standard library
only and safe to import on any client OS.
"""

import argparse
from datetime import datetime, timedelta
import json
import os
import sys

OBSERVATION_NAME = "stk-mupro-preflight.json"
MAX_OBSERVATION_BYTES = 65536

_FIELDS = frozenset({"schema", "scope", "producer", "process_id", "started_at", "observed_at",
                     "summary", "checks", "unverified"})
# Ordered check IDs and the statuses the published /1 table allows for each.
_CHECKS = (("env_scripts", frozenset({"pass", "fail", "not_configured"})),
           ("sdk_prefix", frozenset({"pass", "fail"})),
           ("program", frozenset({"pass", "fail"})),
           ("shared_libraries", frozenset({"pass", "fail", "skip"})),
           ("mpi_launcher", frozenset({"pass", "warn"})),
           ("license_dir", frozenset({"pass", "fail", "warn"})),
           ("example_case", frozenset({"pass", "warn"})))
_UNVERIFIED = {"program_version": "unobserved", "license_checkout": "not_checked", "solver_execution": "not_run"}
_SUMMARIES = frozenset({"checks_failed", "checks_incomplete", "checks_passed"})


def _invalid(message):
    # Messages are static: never echo payload content, which came from another machine.
    return ValueError(f"Invalid MuPRO preflight observation: {message}")


class _Rejected(ValueError):
    """A static rejection raised from inside the JSON decoder hooks."""


def _no_duplicates(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise _Rejected("duplicate object key")
    return dict(pairs)


def _no_constant(_):
    raise _Rejected("non-finite number")


def _timestamp(value, field):
    if not isinstance(value, str):
        raise _invalid(f"{field} must be a string")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise _invalid(f"{field} is not an ISO 8601 timestamp") from None
    if moment.utcoffset() != timedelta(0):
        raise _invalid(f"{field} must be a UTC timestamp")


def parse_observation(data):
    """Return the observation decoded from ``data`` bytes, or raise ``ValueError``.

    Enforces the closed stk.mupro-preflight/1 shape: exact fields, the seven ordered
    checks with their published statuses, a summary consistent with those statuses and
    the fixed ``unverified`` object. It does not establish where or when it was produced.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise _invalid("expected bytes")
    if len(data) > MAX_OBSERVATION_BYTES:
        raise _invalid(f"larger than {MAX_OBSERVATION_BYTES} bytes")
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        raise _invalid("not UTF-8") from None
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except RecursionError:
        raise _invalid("nested too deeply") from None
    except _Rejected as exc:
        raise _invalid(str(exc)) from None
    except ValueError:
        # JSONDecodeError keeps the whole document; raise a fresh static error instead.
        raise _invalid("not JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise _invalid("fields differ from stk.mupro-preflight/1")
    if value["schema"] != "stk.mupro-preflight/1":
        raise _invalid("schema is not stk.mupro-preflight/1")
    if value["scope"] != "local_process":
        raise _invalid("scope is not local_process")
    producer = value["producer"]
    if not isinstance(producer, dict) or set(producer) != {"component", "distribution_version"}:
        raise _invalid("producer fields differ")
    if producer["component"] != "suan.mupro":
        raise _invalid("producer component is not suan.mupro")
    if producer["distribution_version"] is not None and not isinstance(producer["distribution_version"], str):
        raise _invalid("producer distribution_version must be a string or null")
    process_id = value["process_id"]
    if type(process_id) is not int or process_id < 1:
        raise _invalid("process_id must be a positive integer")
    _timestamp(value["started_at"], "started_at")
    _timestamp(value["observed_at"], "observed_at")
    checks = value["checks"]
    if not isinstance(checks, list) or len(checks) != len(_CHECKS):
        raise _invalid("checks must list the seven published checks")
    for item, (check_id, statuses) in zip(checks, _CHECKS):
        if not isinstance(item, dict) or set(item) != {"id", "status"}:
            raise _invalid("check fields differ")
        if item["id"] != check_id:
            raise _invalid("check IDs differ from the published order")
        if not isinstance(item["status"], str) or item["status"] not in statuses:
            raise _invalid(f"{check_id} status is not permitted")
    found = {item["status"] for item in checks}
    expected = ("checks_failed" if "fail" in found else
                "checks_incomplete" if found & {"warn", "skip"} else "checks_passed")
    if (not isinstance(value["summary"], str) or value["summary"] not in _SUMMARIES or
            value["summary"] != expected):
        raise _invalid("summary is inconsistent with the checks")
    unverified = value["unverified"]
    if (not isinstance(unverified, dict) or set(unverified) != set(_UNVERIFIED)
            or any(not isinstance(unverified[key], str) or unverified[key] != text_value
                   for key, text_value in _UNVERIFIED.items())):
        raise _invalid("unverified differs from the published values")
    return value


def _reserve(name):
    """Create ``name`` exclusively; an existing file or (dangling) symlink is never reused."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    return os.open(name, flags, 0o600)


def _discard(name, descriptor):
    """Close and remove a reserved output only while it is still the file this process created."""
    try:
        created = os.fstat(descriptor)
    except OSError:
        created = None
    os.close(descriptor)
    try:
        current = os.lstat(name)
        if created is not None and (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
            os.unlink(name)
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m suan.mupro.preflight",
        description="Write this worker's MuPRO preflight observation to " + OBSERVATION_NAME
                    + "; accepts no configuration options.")
    parser.parse_args(argv)
    try:
        descriptor = _reserve(OBSERVATION_NAME)
    except FileExistsError:
        print(f"MuPRO preflight: {OBSERVATION_NAME} already exists; refusing to reuse or overwrite it",
              file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"MuPRO preflight: cannot create {OBSERVATION_NAME} ({type(exc).__name__})", file=sys.stderr)
        return 3
    try:
        from types import SimpleNamespace
        from . import run

        observation = run.preflight_observation(SimpleNamespace(
            sdk_prefix=None, program="muFerro", env_scripts=[], license_dir=None))
        data = (json.dumps(observation, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        summary = parse_observation(data)["summary"]
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view):]
        os.fsync(descriptor)
        os.close(descriptor)
    except Exception as exc:  # noqa: BLE001 - raw diagnostics may hold local paths; report the type only
        _discard(OBSERVATION_NAME, descriptor)
        print(f"MuPRO preflight: collection failed ({type(exc).__name__}); no observation was written",
              file=sys.stderr)
        return 3
    print(f"MuPRO preflight: {summary}; wrote {OBSERVATION_NAME}")
    return 1 if summary == "checks_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
