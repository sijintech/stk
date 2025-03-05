# -*- coding: utf-8 -*-
"""
This module contains the image annotations panel, which shows the image
annotations in the marging of the editor. The annotations are managed by the
ImageAnnotationsMode.
"""

from pyqode.core.panels import CheckerPanel
from qtpy import QtCore


class ImageAnnotationsPanel(CheckerPanel):
    _adjust_vertical_offset = False

    def __init__(self):
        self._shown_size_hint = QtCore.QSize(256, 256)
        self._hidden_size_hint = QtCore.QSize(1, 1)
        self._size_hint = self._hidden_size_hint
        self._update_size_timer = QtCore.QTimer()
        self._update_size_timer.timeout.connect(self._update_size)
        self._update_size_timer.setSingleShot(True)
        self._update_size_timer.setInterval(1000)
        CheckerPanel.__init__(self)

    def sizeHint(self):
        return self._size_hint

    def _icon_size(self):
        return self.sizeHint()

    def _multiple_markers_icon(self):
        return

    def _vertical_offset(self):
        return 0

    def _message_count(self, n):
        # When there are annotations, the size hint of the panel is changed so
        # that it becomes visible. Otherwise, the size hint is reduced to 1 so
        # that it's practically invisible but still functional.
        new_hint = self._shown_size_hint if n else self._hidden_size_hint
        if new_hint == self._size_hint:
            return
        self._size_hint = new_hint
        if new_hint == self._hidden_size_hint:
            if self._update_size_timer.isActive():
                self._update_size_timer.stop()
            self._update_size_timer.start()
        else:
            self._update_size()

    def _update_size(self):
        self.editor.panels.refresh()
