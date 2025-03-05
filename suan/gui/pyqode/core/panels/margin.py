# -*- coding: utf-8 -*-
"""
This module contains the margin panel
"""
from pyqode.core.api.panel import Panel
from qtpy import QtCore


class MarginPanel(Panel):
    """A panel that pads the left and right margins so that the content is
    centered. This is mostly for writing plain text.
    """

    _use_syntax_theme = True

    def __init__(self, nchar=80):

        super(MarginPanel, self).__init__()
        self._nchar = nchar

    def sizeHint(self):

        left_margin = sum(
            panel.sizeHint().width()
            for panel in self.editor.panels.panels_for_zone(
                Panel.Position.LEFT
            )
            if panel.isVisible() and not isinstance(panel, MarginPanel)
        )
        right_margin = sum(
            panel.sizeHint().width()
            for panel in self.editor.panels.panels_for_zone(
                Panel.Position.RIGHT
            )
            if panel.isVisible() and not isinstance(panel, MarginPanel)
        )
        margin = (
                         self.editor.width()
                         - self.editor.fontMetrics().width("_") * self._nchar
                 ) // 2 - right_margin - left_margin
        return QtCore.QSize(max(0, margin), 50)

    def on_install(self, editor):

        super(MarginPanel, self).on_install(editor)
        self.setVisible(True)
        if self.position != Panel.Position.LEFT:
            return
        self._right_panel = RightMarginPanel(self._nchar)
        self.editor.panels.append(
            self._right_panel,
            position=Panel.Position.RIGHT
        )

    def on_uninstall(self):

        if self.position == Panel.Position.LEFT:
            self.editor.panels.remove('RightMarginPanel')
        super(MarginPanel, self).on_uninstall()


class RightMarginPanel(MarginPanel):
    pass
