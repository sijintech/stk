"""STK desktop bridge: the MIT Python side of the GPL desktop app (docs/specs/stk-desktop-bridge-v1.md).

``python -m suan.desktop_bridge --stdio`` speaks newline-delimited JSON on stdin/stdout. The bridge
owns every credential (Runtime tokens, hub device tokens) and gives the app opaque connection ids;
large data travels through the content-addressed blob cache ``<cache>/blobs/<aa>/<sha256>``.
Closing the app never stops Runtime jobs.
"""
from .protocol import ERROR_CODES, MAX_LINE_BYTES, PROTOCOL_VERSION, BridgeError

__all__ = ["ERROR_CODES", "MAX_LINE_BYTES", "PROTOCOL_VERSION", "BridgeError"]
