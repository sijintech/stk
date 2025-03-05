"""
Checker panels:

    - CheckerPanel: draw checker messages in front of each line
    - GlobalCheckerPanel: draw all checker markers as colored rectangle to
      offer a global view of all errors
"""
from pyqode.core import icons
from pyqode.core.api import DelayJobRunner, TextHelper
from pyqode.core.api.panel import Panel
from qtpy import QtCore, QtGui, QtWidgets


class CheckerPanel(Panel):
    """ Shows messages collected by one or more checker modes """

    _use_syntax_theme = True
    _adjust_vertical_offset = True

    def __init__(self):
        super(CheckerPanel, self).__init__()
        self._visible_markers = []
        self._tooltip_shown = False
        self._current_widget = None
        self.scrollable = True
        self._job_runner = DelayJobRunner(delay=100)
        self.setMouseTracking(True)

    def marker_for_line(self, line):
        """
        Returns the marker that is displayed at the specified line number if
        any.

        :param line: The marker line.

        :return: Marker of None
        :rtype: pyqode.core.Marker
        """
        block = self.editor.document().findBlockByNumber(line)
        try:
            messages = block.userData().messages
        except AttributeError:
            return []
        return [msg for msg in messages if msg.show_on_panel(self)]

    def sizeHint(self):
        """
        Returns the panel size hint. (fixed with of 16px)
        """
        metrics = QtGui.QFontMetricsF(self.editor.font())
        size_hint = QtCore.QSize(int(metrics.height()), int(metrics.height()))
        if size_hint.width() > 16:
            size_hint.setWidth(16)
        return size_hint

    def on_uninstall(self):
        self._job_runner.cancel_requests()
        super(CheckerPanel, self).on_uninstall()

    def _vertical_offset(self):
        """Allows the icons to be centered on the line, in case they are
        smaller than the line height. Can be overridden to have the icons
        attached to the top of the line.
        """
        size_hint = self.sizeHint()
        return (size_hint.height() - size_hint.width()) // 2

    def _icon_size(self):
        """Gets the intended size of the icons."""
        width = self.sizeHint().width()
        return QtCore.QSize(width, width)

    def _multiple_markers_icon(self):
        """In case there are multiple markers on the same line, show this icon.
        If None is returned, then the first marker icon is shown.
        """
        return icons.icon('list-add', '', 'fa.plus-circle')

    def paintEvent(self, event):
        """Handles the actual drawing of the markers on the panel."""
        super(CheckerPanel, self).paintEvent(event)
        painter = QtGui.QPainter(self)
        message_count = 0
        icon_size = self._icon_size()
        vertical_offset = self._vertical_offset()
        multiple_markers_icon = self._multiple_markers_icon()
        self._visible_markers = []
        for top, block_nbr, block in self.editor.visible_blocks:
            user_data = block.userData()
            if not user_data or not user_data.messages:
                continue
            markers = [
                msg for msg in user_data.messages
                if msg.show_on_panel(self) and msg.icon()
            ]
            if not markers:
                continue
            message_count += len(markers)
            icon = (
                markers[0].icon()
                if len(markers) == 1 or multiple_markers_icon is None
                else multiple_markers_icon
            )
            rect = QtCore.QRect()
            rect.setX(0)
            actual_icon_size = icon.actualSize(icon_size)
            rect.setY(top + vertical_offset)
            rect.setSize(actual_icon_size)
            icon.paint(painter, rect)
            self._visible_markers.append((markers, rect))
        self._message_count(message_count)

    def mouseMoveEvent(self, event):
        if self._tooltip_shown or self._current_widget is not None:
            return
        for markers, rect in self._visible_markers:
            if not rect.contains(event.pos()):
                continue
            tooltips = []
            for marker in markers:
                widget = marker.widget()
                if widget is not None:
                    self._display_widget(widget, rect.top())
                    return
                tooltips.append(marker.tooltip())
            self._job_runner.request_job(
                self._display_tooltip,
                '<pre>{}</pre>'.format('\n'.join(tooltips)), rect.top())
            return
        self._job_runner.cancel_requests()

    def mousePressEvent(self, event):
        for markers, rect in self._visible_markers:
            if not rect.contains(event.pos()):
                continue
            for marker in markers:
                marker.clicked(event)
                break

    def leaveEvent(self, *args):
        """
        Hide tooltip when leaving the panel region.
        """
        if self._tooltip_shown:
            QtWidgets.QToolTip.hideText()
            self._tooltip_shown = False
        if self._current_widget is not None:
            self._current_widget.hide()
            self._current_widget = None

    def _display_tooltip(self, tooltip, top):
        """
        Display tooltip at the specified top position.
        """
        self._tooltip_shown = True
        QtWidgets.QToolTip.showText(self.mapToGlobal(QtCore.QPoint(
            0, top)), tooltip, self)

    def _display_widget(self, widget, top):
        self._current_widget = widget
        widget.show()
        widget.move(self.mapToGlobal(QtCore.QPoint(-widget.width(), top)))

    def _message_count(self, n):
        pass
