"""Unregistered bridge adapter for an explicit MuPRO execution-environment preflight task.

The caller (the bridge server, once root registers methods) resolves the saved connection to a
backend and passes it here. Only a direct or SSH :class:`RuntimeBackend` is accepted; a hub
node is ``unsupported`` before any task or action I/O. Each request is bound to a frozen target:
its ``connection`` id and the backend's credential-free ``server_key`` must both match.

- :func:`describe` is passive metadata only (no health check, task, subprocess or collection).
- :func:`submit` builds the fixed ``preflight_spec`` task and submits it exactly once through
  :func:`suan.mupro.client.submit_preflight`. No waiting, health check, workspace creation or
  project write. A lost or mismatched reply is never retried or replaced; the caller repeats
  the request with the same ``idempotency_key`` to observe the original task.
- :func:`result` verifies one finished task through :func:`suan.mupro.client.read_preflight`
  without submitting, waiting, refreshing a collection or writing files.

The submitted task sources the worker's configured trusted scripts, so it is an explicit
operation with possible effects rather than a passive probe. Responses never include the raw
Runtime URL, SSH host, credentials or worker paths.
"""

import re

from suan.mupro.client import PreflightError, read_preflight, submit_preflight
from suan.mupro.spec import preflight_spec

from .backends import RuntimeBackend
from .protocol import BridgeError

__all__ = ["describe", "result", "submit"]

SUBMIT_PARAMS = frozenset({"connection", "expected_connection_identity", "workspace_id", "idempotency_key", "options"})
RESULT_PARAMS = frozenset({"connection", "expected_connection_identity", "task_id"})
OPTIONS = frozenset({"backend", "walltime_seconds", "memory_mb", "queue", "account", "name"})
_TASK_ID = re.compile(r"[a-f0-9]{32}")


def _runtime(backend):
    # A hub node would need a reviewed action; this adapter never creates one or falls back.
    if not isinstance(backend, RuntimeBackend):
        raise BridgeError("unsupported", "MuPRO preflight tasks need a saved direct or SSH Runtime connection")
    return backend


def _params(params, names):
    if type(params) is not dict or set(params) != names:
        raise BridgeError("invalid_params", "Expected exactly the parameters " + ", ".join(sorted(names)))
    for name in ("connection", "expected_connection_identity"):
        if not isinstance(params[name], str) or not params[name]:
            raise BridgeError("invalid_params", f"'{name}' must be a nonempty string")
    return params


def _bind(backend, params):
    if params["connection"] != backend.connection_id:
        raise BridgeError("conflict", "The preflight request names a different connection")
    if params["expected_connection_identity"] != backend.server_key:
        raise BridgeError("conflict", "The Runtime endpoint differs from the expected connection")


def _remote_error(exc, action):
    # Only the shared module's static messages are forwarded; other errors may hold reply content.
    message = str(exc) if type(exc) is PreflightError else f"The Runtime returned an invalid preflight {action}"
    return BridgeError("remote_error", message)


def describe(backend):
    """``{connection, connection_identity}`` of the backend; performs no I/O."""
    backend = _runtime(backend)
    return {"connection": backend.connection_id, "connection_identity": backend.server_key}


def submit(backend, params):
    """Submit the fixed preflight task once; ``{"task": record}`` with the original Runtime record."""
    backend = _runtime(backend)
    params = _params(params, SUBMIT_PARAMS)
    key, options = params["idempotency_key"], params["options"]
    if not isinstance(key, str) or not 1 <= len(key) <= 200:
        raise BridgeError("invalid_params", "'idempotency_key' must be a string of 1–200 characters")
    if type(options) is not dict or set(options) - OPTIONS:
        raise BridgeError("invalid_params", "'options' accepts only " + ", ".join(sorted(OPTIONS)))
    if not isinstance(params["workspace_id"], str):
        raise BridgeError("invalid_params", "'workspace_id' must be a Runtime workspace ID")
    try:
        spec = preflight_spec(params["workspace_id"], **options)
    except (TypeError, ValueError) as exc:
        raise BridgeError("invalid_params", f"Invalid preflight options: {exc}") from None
    _bind(backend, params)
    try:
        record = backend.call(submit_preflight, backend.client, spec, key)
    except BridgeError:
        raise
    except ValueError as exc:  # after I/O: the request itself was validated above
        raise _remote_error(exc, "submission reply") from None
    return {"task": record}


def result(backend, params):
    """Verify one finished preflight task: ``{result, connection, connection_identity}``."""
    backend = _runtime(backend)
    params = _params(params, RESULT_PARAMS)
    task_id = params["task_id"]
    if not isinstance(task_id, str) or _TASK_ID.fullmatch(task_id) is None:
        raise BridgeError("invalid_params", "'task_id' must be a Runtime task ID")
    _bind(backend, params)
    try:
        envelope = backend.call(read_preflight, backend.client, task_id, None)
    except BridgeError:
        raise
    except ValueError as exc:
        _bind(backend, params)  # An endpoint change is a conflict, not a malformed result.
        raise _remote_error(exc, "result") from None
    _bind(backend, params)
    if envelope["target"]["connection_sha256"][:16] != backend.server_key:
        raise BridgeError("conflict", "The preflight result was read from a different Runtime endpoint")
    return {"result": envelope, "connection": backend.connection_id, "connection_identity": backend.server_key}
