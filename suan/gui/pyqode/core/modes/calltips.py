# -*- coding: utf-8 -*-
"""
Contains a base class for a calltips mode.
"""
import logging
from pyqode.core.api import Mode, TextHelper
from pyqode.core.api.panel import Panel
from qtpy import QtCore, QtWidgets

MAX_CALLTIP_WIDTH = 80


def _logger():
    return logging.getLogger(__name__)


class CalltipsMode(Mode, QtCore.QObject):
    """A base class for calltips modes."""
    tooltipDisplayRequested = QtCore.Signal(object, int)
    tooltipHideRequested = QtCore.Signal()

    def __init__(self):
        Mode.__init__(self)
        QtCore.QObject.__init__(self)
        self.tooltipDisplayRequested.connect(self._display_tooltip)
        self.tooltipHideRequested.connect(QtWidgets.QToolTip.hideText)
        self.__requestCnt = 0
        self._cached_style = None

    def on_state_changed(self, state):
        if state:
            self.editor.key_released.connect(self._on_key_released)
        else:
            self.editor.key_released.disconnect(self._on_key_released)

    def _on_key_released(self, event):
        if (event.key() == QtCore.Qt.Key_ParenLeft or
                event.key() == QtCore.Qt.Key_Comma):
            tc = self.editor.textCursor()
            line = tc.blockNumber()
            col = tc.columnNumber()
            fn = self.editor.file.path
            encoding = self.editor.file.encoding
            source = self.editor.toPlainText()
            # jedi has a bug if the statement has a closing parenthesis
            # remove it!
            lines = source.splitlines()
            try:
                l = lines[line].rstrip()
            except IndexError:
                # at the beginning of the last line (empty)
                return
            if l.endswith(")"):
                lines[line] = l[:-1]
            source = "\n".join(lines)
            self._request_calltip(source, line, col, fn, encoding)
        elif (event.key() in [
            QtCore.Qt.Key_ParenRight,
            QtCore.Qt.Key_Return,
            QtCore.Qt.Key_Left,
            QtCore.Qt.Key_Right,
            QtCore.Qt.Key_Up,
            QtCore.Qt.Key_Down,
            QtCore.Qt.Key_End,
            QtCore.Qt.Key_Home,
            QtCore.Qt.Key_PageDown,
            QtCore.Qt.Key_PageUp,
            QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete]):
            QtWidgets.QToolTip.hideText()

    def _request_calltip(self, source, line, col, fn, encoding):
        pass

    def _on_results_available(self, results):
        pass

    def _is_last_chard_end_of_word(self):
        try:
            tc = TextHelper(self.editor).word_under_cursor()
            tc.setPosition(tc.position())
            tc.movePosition(tc.StartOfLine, tc.KeepAnchor)
            l = tc.selectedText()
            last_char = l[len(l) - 1]
            seps = self.editor.word_separators
            symbols = [",", " ", "("]
            return last_char in seps and last_char not in symbols
        except IndexError:
            return False

    def _tooltip_style(self):
        if self._cached_style is not None:
            return self._cached_style
        pal = self.editor.palette()
        qss = '''
            white-space: pre;
            background: {background_color};
            color: {text_color};
            font-family: {font_family};
            font-size: {font_size};
        '''.format(
            background_color=pal.base().color().name(),
            text_color=pal.text().color().name(),
            font_family=self.editor.font_name,
            font_size=self.editor.font_size,
        )
        try:
            highlight = self.editor.syntax_highlighter.formats[
                'keyword'].foreground().color().name()
        except (AttributeError, KeyError):
            highlight = self.editor.palette().highlightedText().color().name()
        self._cached_style = qss, highlight
        return self._cached_style

    def _format_tooltip(self, name, params, current_param=None, doc=None):
        lines = []
        qss, highlight = self._tooltip_style()
        html = '<div style="{}">{}('.format(qss, name)
        line = '{}('.format(name)
        for i, param in enumerate(params):
            if len(line) + len(param) > MAX_CALLTIP_WIDTH:
                lines.append(html)
                html = line = ' ' * (len(name) + 1)
            if i < len(params) - 1 and not param.endswith(','):
                param += ", "
            if param.endswith(','):
                param += ' '  # pep8 calltip
            if i == current_param:
                html += "<span style='color:{};'>".format(highlight)
            line += param
            html += param
            if i == current_param:
                html += "</span>"
        lines.append(html + ')</div>')
        return '\n'.join(lines)

    def _display_tooltip(self, call, col):
        if not call or self._is_last_chard_end_of_word():
            return
        calltip = self._format_tooltip(
            call['call.call_name'],
            call['call.params'],
            call['call.index'],
            call['call.doc'],
        )
        rect = self.editor.cursorRect()
        position = QtCore.QPoint(
            (
                    rect.left() +
                    self.editor.panels.margin_size(Panel.Position.LEFT) -
                    (col - call['call.bracket_start'][1]) *
                    self.editor.fontMetrics().width('_')
            ),
            (
                    rect.bottom() +
                    self.editor.panels.margin_size(Panel.Position.TOP)
            )
        )
        position = self.editor.mapToGlobal(position)
        QtWidgets.QToolTip.showText(position, calltip, self.editor)
