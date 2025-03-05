# -*- coding: utf-8 -*-
"""
Contains the JediCompletionProvider class implementation.
"""

from pyqode.core.modes import CalltipsMode as CoreCalltipsMode
from pyqode.python.backend import workers


class CalltipsMode(CoreCalltipsMode):

    def __init__(self):
        super(CalltipsMode, self).__init__()
        self._working = False

    def _request_calltip(self, source, line, col, fn, encoding):
        if self._working:
            return
        self._working = True
        self.editor.backend.send_request(
            workers.calltips,
            {
                'code': source,
                'line': line,
                'column': col,
                'path': None,
                'encoding': encoding
            },
            on_receive=self._on_results_available
        )

    def _on_results_available(self, results):
        self._working = False
        if not results:
            return
        call = {
            "call.module.name": results[0],
            "call.call_name": results[1],
            "call.params": results[2],
            "call.index": results[3],
            "call.bracket_start": results[4],
            "call.doc": None,
        }
        self.tooltipDisplayRequested.emit(call, results[5])
