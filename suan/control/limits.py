"""Size and time limits shared by the control hub and the node agent (each defined once, here).

The hub and the agent exchange JSON messages over one WebSocket. Neither side accepts a message of
:data:`FRAME_LIMIT` bytes or more (the hub's ``ws_max_size``, the agent's ``max_size``), so the hub
bounds every request it stores or forwards well below it, and refuses to send anything that would
not fit (a request that did not fit would disconnect the node on every reconnect).
"""
import json

__all__ = ["ACTION_BODY_BYTES", "ACTION_REQUEST_BYTES", "FRAME_LIMIT", "IMPORT_MAX_FILES", "IMPORT_REQUEST_BYTES",
           "READ_QUEUE", "READ_REQUEST_BYTES", "READ_TIMEOUT", "encoded_size", "frame"]

MIB = 1024 * 1024
FRAME_LIMIT = 16 * MIB             # largest WebSocket message the hub or the agent accepts
ACTION_REQUEST_BYTES = 1 * MIB     # an action request (id, node_id, kind, payload), encoded
IMPORT_REQUEST_BYTES = 4 * MIB     # a workspace.import request, encoded
IMPORT_MAX_FILES = 4096            # files of one workspace.import
ACTION_BODY_BYTES = IMPORT_REQUEST_BYTES + 64 * 1024  # HTTP body of POST /api/v1/actions
READ_REQUEST_BYTES = 64 * 1024     # HTTP body of POST /api/v1/nodes/<id>/read
READ_TIMEOUT = 30                  # seconds the hub waits for a read; the node drops reads older than this
READ_QUEUE = 16                    # reads a node holds (waiting or running) before it answers "busy"


def encoded_size(value):
    """Bytes of ``json.dumps(value, ensure_ascii=False)`` in UTF-8 (the measure of every request cap).

    Non-finite numbers raise ``ValueError``: a node could not decode them as strict JSON.
    """
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def frame(message):
    """The exact text the hub sends for ``message`` (compact JSON, not ASCII-escaped)."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
