"""The muFerro connector's ``MonitorAdapter`` (``suan.connectors.api``): ``suan.mupro.monitor`` as events.

``python -m suan.mupro run`` already monitors the runs it launches (it writes
``$STK_MONITOR_PATH`` itself). This adapter exposes the same rules -- B4's
:class:`suan.mupro.monitor.MuferroAdapter` and :func:`suan.mupro.monitor.replay`
-- through the connector API, for runs STK did not launch: ``poll`` returns the
new events since the previous call as ``{"type", "data"}`` dicts (the caller's
emitter adds ``v``/``seq``/``ts``/``src``), and ``replay`` returns every event
of a finished run directory, verification and ``run.completed`` included.
"""
from pathlib import Path

from suan.monitor.emit import Emitter
from suan.monitor.events import EventError, make_event, validate_event

__all__ = ["EventBuffer", "MuferroMonitorAdapter"]


class EventBuffer(Emitter):
    """An :class:`~suan.monitor.emit.Emitter` that keeps validated events in memory instead of a file.

    Progress is not coalesced (the adapter reports the latest line of each poll).
    """

    def __init__(self, src="adapter"):
        super().__init__(path=None, src=src, environ={})
        self.events = []

    @property
    def enabled(self):
        return True

    def emit(self, event_type, data=None, *, src=None):
        try:
            event = validate_event(make_event(len(self.events), event_type, data, src or self.src, 0.0))
        except EventError:
            return False
        self.events.append({"type": event_type, "data": event["data"]})
        return True

    def progress(self, step=None, total_steps=None, *, force=False, **data):
        data = {"step": step, "total_steps": total_steps, **data}
        return self.emit("progress", {key: value for key, value in data.items() if value is not None})

    def flush(self):
        return True

    def close(self):
        return None

    def take(self):
        """The events collected so far (and forget them)."""
        events, self.events = self.events, []
        return events


class MuferroMonitorAdapter:
    """Events of one muFerro case directory on this host (``root``: the run directory)."""

    def __init__(self, root, case_dir="."):
        from suan.mupro.monitor import MuferroAdapter
        self.root = Path(root)
        self.case_dir = case_dir or "."
        self._buffer = EventBuffer()
        folder = self.root if self.case_dir in (".", "./", "") else self.root / self.case_dir
        self._adapter = MuferroAdapter(self._buffer, folder, self.case_dir)

    def poll(self, *, final=False, exit_code=None):
        """New events since the last poll; ``final=True`` once the program has exited (``exit_code`` 0 publishes
        every remaining frame, otherwise only frames at or before the last progress step)."""
        self._adapter.poll(final=final, exit_code=exit_code)
        return self._buffer.take()

    def replay(self):
        """Every event of a finished run: the same rules as a live run with all frames published, then
        ``verification`` and ``run.completed`` (``suan.mupro.monitor.replay``). Raises ``MuproError`` when the
        case cannot be read."""
        from suan.mupro.monitor import replay
        buffer = EventBuffer()
        replay(buffer, self.root, self.case_dir)
        return buffer.take()
