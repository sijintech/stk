# coding=utf-8

"""This panel allows the user to change the file extension of empty, unsaved
buffers. This panel requires that the editor is part of a
SplittableCodeEditTabWidget.
"""

import os
from pyqode.core.api.panel import Panel
from pyqode.core import icons
from qtpy.QtCore import QTimer, Signal, QRegularExpression
from qtpy.QtGui import QRegularExpressionValidator
from qtpy.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy
)


class ChangeExtensionPanel(Panel):
    extension_changed = Signal(str)

    def __init__(self):
        super(ChangeExtensionPanel, self).__init__()
        self.hide()
        self._splitter = None
        self._layout = None

    def on_install(self, editor):
        super(ChangeExtensionPanel, self).on_install(editor)
        self.editor.textChanged.connect(self._check)
        self._check()

    @property
    def splitter(self):
        """The splitter is somewhere in the parental hierarchy of the editor,
        but not always at the same level.
        """
        if self._splitter is not None:
            return self._splitter
        from pyqode.core.widgets import SplittableCodeEditTabWidget
        self._splitter = self.editor.parent()
        while not isinstance(self._splitter, SplittableCodeEditTabWidget):
            self._splitter = self._splitter.parent()
            if self._splitter is None:
                raise ValueError('Cannot find SplittableCodeEditTabWidget')
        return self._splitter

    def _change_extension(self):
        """Creates a new document with the requested extension and closes the
        current one.
        """
        splitter = self.splitter
        tab_widget = splitter.main_tab_widget
        ext = self._ext_edit.text()
        self.extension_changed.emit(ext)
        splitter.create_new_document(extension=ext)
        tab_widget.remove_tab(tab_widget.indexOf(self.editor))

    def _hide(self):
        try:
            self.editor.textChanged.disconnect(self._check)
        except TypeError:  # In case it was already disconnected
            pass
        self.hide()

    def _check(self):
        """Hides the panel as soon as the buffer is no longer empty or has
        been saved. Shows the panel as soon as it is unsaved and empty.
        """
        if self.editor.toPlainText() or self.editor.file.path:
            self._hide()
            return
        if self.isVisible() or self._layout is not None:
            return
        self._layout = QHBoxLayout(self)
        self._label = QLabel(_('Change extension to'))
        self._ext_edit = QLineEdit(self.splitter.default_extension(), self)
        self._ext_edit.setValidator(QRegularExpressionValidator(
            QRegularExpression(r'\.\w+'), self))
        self._ext_edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._apply_button = QPushButton(_('Apply'), self)
        self._apply_button.setIcon(icons.icon(qta_name='fa.check'))
        self._apply_button.clicked.connect(self._change_extension)
        self._dismiss_button = QPushButton(_('Dismiss'), self)
        self._dismiss_button.setIcon(icons.icon(qta_name='fa.remove'))
        self._dismiss_button.clicked.connect(self._hide)
        self._layout.addWidget(self._label)
        self._layout.addWidget(self._ext_edit)
        self._layout.addWidget(self._apply_button)
        self._layout.addWidget(self._dismiss_button)
        self._layout.addStretch()
        self.setLayout(self._layout)
        self.show()
