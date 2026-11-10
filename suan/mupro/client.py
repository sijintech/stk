"""Submit and read explicit MuPRO preflight tasks through an existing Runtime client.

Shared by ``suan mupro preflight`` / ``preflight-result`` and the desktop bridge adapter
(``suan.desktop_bridge.mupro_preflight``). Pure transport logic: no Click, CLI output, file
writes, waiting, transport retry, replacement submission or local fallback check. The client
is a ``RuntimeClient`` (or a direct/SSH subclass); its transport errors propagate unchanged.

Errors raised after validation are :class:`PreflightError` with static messages that never echo
Runtime-provided content (docs/specs/mupro-preflight-task-1.md).
"""

import hashlib
import re
from urllib.parse import urlencode

from suan.runtime.models import TaskSpec

from .preflight import MAX_OBSERVATION_BYTES, OBSERVATION_NAME, parse_observation
from .spec import preflight_spec

__all__ = ["RESULT_SCHEMA", "PreflightError", "read_preflight", "submit_preflight"]

RESULT_SCHEMA = "stk.mupro-preflight-result/1"
_TASK_ID = re.compile(r"[a-f0-9]{32}")
_DIGEST = re.compile(r"[a-f0-9]{64}")
_RESOURCES = ("walltime_seconds", "memory_mb", "queue", "account")


class PreflightError(ValueError):
    """A preflight request, acknowledgement or result failed a check; the message is static."""


def _is_task_id(value):
    return isinstance(value, str) and _TASK_ID.fullmatch(value) is not None


def _canonical_spec(spec):
    """``spec`` normalized by the Runtime, or raise when it is not an unmodified preflight task."""
    try:
        actual = TaskSpec(**spec).to_dict()
        resources = actual["resources"]
        expected = preflight_spec(actual["workspace_id"], backend=actual["backend"], name=actual["name"],
            **{k: resources[k] for k in _RESOURCES if k in resources})
        matches = actual == TaskSpec(**expected).to_dict()
    except (TypeError, ValueError, KeyError) as exc:
        raise PreflightError("Invalid preflight task specification") from exc
    if not matches:
        raise PreflightError("Task is not an unmodified MuPRO preflight task")
    return actual


def _checked_task(record, task_id):
    if not isinstance(record, dict) or record.get("id") != task_id:
        raise PreflightError("Preflight task identity does not match the requested task")
    spec = record.get("spec")
    if not isinstance(spec, dict):
        raise PreflightError("Preflight task specification is missing")
    actual = _canonical_spec(spec)
    if record.get("state") not in ("succeeded", "failed"):
        raise PreflightError("Preflight task must finish successfully or with failed checks before reading its observation")
    return actual


def submit_preflight(client, spec, key):
    """Submit one fixed preflight task exactly once; return the Runtime's validated task record.

    ``spec`` must be an unmodified ``preflight_spec`` result and ``key`` a nonempty string;
    both are checked before any I/O (the Runtime enforces the key's length). The reply must name a Runtime task ID
    and the requested specification. A lost or mismatched reply is never retried here: the
    caller observes it by explicitly submitting the same spec with the same key again.
    """
    requested = _canonical_spec(spec)
    if not isinstance(key, str) or not key:
        # RuntimeClient.submit would replace a falsy key with a random one and break replay;
        # the Runtime itself enforces the length limit.
        raise PreflightError("A nonempty idempotency key is required")
    record = client.submit(spec, key)
    task_id = record.get("id") if isinstance(record, dict) else None
    if not _is_task_id(task_id):
        raise PreflightError("Submission returned an invalid Runtime task ID; observe the original idempotency key")
    try:
        matches = TaskSpec(**record["spec"]).to_dict() == requested
    except (TypeError, ValueError, KeyError) as exc:
        raise PreflightError("Submission returned an invalid preflight specification; observe the original idempotency key") from exc
    if not matches:
        raise PreflightError("Submission does not match the requested preflight specification; observe the original idempotency key")
    return record


def read_preflight(client, task_id, profile=None, *, expected_spec=None):
    """Return the verified stk.mupro-preflight-result/1 envelope of one finished task.

    Reads the task, its artifact listing, one bounded ranged download of the listed
    observation and the task again; it never submits, waits or runs a local check.
    ``profile`` is only recorded in ``target``. ``expected_spec`` additionally binds the
    task to the specification a caller submitted.
    """
    if not _is_task_id(task_id):
        raise PreflightError("Expected a Runtime task ID")
    identity = client.connection_identity
    if not isinstance(identity, str) or not identity:
        raise PreflightError("Preflight result needs a stable Runtime connection identity")
    record = client.task(task_id)
    spec = _checked_task(record, task_id)
    if expected_spec is not None and spec != TaskSpec(**expected_spec).to_dict():
        raise PreflightError("Preflight task no longer matches the submitted specification")
    items = client.artifacts(task_id)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise PreflightError("Invalid preflight artifact listing")
    matches = [item for item in items if item.get("path") == OBSERVATION_NAME]
    if len(matches) != 1:
        raise PreflightError("Preflight observation artifact is missing or ambiguous; the compute package may need upgrading")
    item = matches[0]
    size, digest = item.get("size"), item.get("sha256")
    if (type(size) is not int or not 1 <= size <= MAX_OBSERVATION_BYTES or
            not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None):
        raise PreflightError("Invalid preflight observation artifact size or digest")
    # One bounded ranged read avoids a second artifact listing changing the download budget.
    query = urlencode({"path": OBSERVATION_NAME, "offset": 0, "limit": size})
    data = client.request("GET", f"tasks/{task_id}/file?{query}", binary=True, max_response_bytes=size)
    if (not isinstance(data, bytes) or len(data) != size or hashlib.sha256(data).hexdigest() != digest):
        raise PreflightError("Preflight observation does not match the listed artifact")
    try:
        observation = parse_observation(data)
    except ValueError as exc:
        raise PreflightError(str(exc)) from None  # parse_observation messages are static
    exit_code = record.get("exit_code")
    failed = observation["summary"] == "checks_failed"
    if (type(exit_code) is not int or exit_code != int(failed) or
            record["state"] != ("failed" if failed else "succeeded")):
        raise PreflightError("Task completion does not match its preflight observation")
    # A refresh reads this same task; it never submits a replacement or runs a local check.
    latest = client.task(task_id)
    if (client.connection_identity != identity or _checked_task(latest, task_id) != spec or
            latest.get("state") != record["state"] or type(latest.get("exit_code")) is not int or
            latest["exit_code"] != exit_code):
        raise PreflightError("Preflight task or Runtime connection changed while reading the observation")
    return {"schema": RESULT_SCHEMA, "scope": "runtime_task",
        "target": {"profile": profile, "connection_sha256": hashlib.sha256(identity.encode()).hexdigest()},
        "task": {"id": task_id, "workspace_id": spec["workspace_id"], "backend": spec["backend"],
                 "state": record["state"], "exit_code": exit_code},
        "artifact": {"path": OBSERVATION_NAME, "size": size, "sha256": digest},
        "observation": observation}
