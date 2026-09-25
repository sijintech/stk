"""STK monitoring events v1 (docs/specs/stk-events-v1.md), standard library only.

``events`` holds the constants, line encoding and hand-written validation of
``suan/contracts/schemas/event-1.schema.json``; ``emit`` is the writer used by programs
and adapters (a no-op without ``$STK_MONITOR_PATH``); ``reader`` reads whole lines by byte
offset for the Runtime; ``tail`` is a small framework for legacy adapters that follow a
program's native output files. Nothing here imports STK modules outside this package, so
the package runs on compute nodes and inside simulation wrappers unchanged.
"""

from .emit import Emitter
from .reader import read_events

__all__ = ["Emitter", "read_events"]
