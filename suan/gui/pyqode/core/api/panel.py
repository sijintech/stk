"""
This module contains the panel API.
"""
import logging
from pyqode.core.api.mode import Mode
from qtpy import QtWidgets, QtGui


def _logger():
    """ Returns module's logger """
    return logging.getLogger(__name__)


class Panel(QtWidgets.QWidget, Mode):
    """
    Base class for editor panels.

    A panel is a mode and a QWidget.

    .. note:: Use enabled to disable panel actions and setVisible to change the
        visibility of the panel.
    """

    _use_syntax_theme = False

    class Position(object):
        """
        Enumerates the possible panel positions
        """
        #: Top margin
        TOP = 0
        #: Left margin
        LEFT = 1
        #: Right margin
        RIGHT = 2
        #: Bottom margin
        BOTTOM = 3

        @classmethod
        def iterable(cls):
            """ Returns possible positions as an iterable (list) """
            return [cls.TOP, cls.LEFT, cls.RIGHT, cls.BOTTOM]

    @property
    def scrollable(self):
        """
        A scrollable panel will follow the editor's scroll-bars. Left and right
        panels follow the vertical scrollbar. Top and bottom panels follow the
        horizontal scrollbar.

        :type: bool
        """
        return self._scrollable

    @scrollable.setter
    def scrollable(self, value):
        self._scrollable = value

    def __init__(self, dynamic=False):
        Mode.__init__(self)
        QtWidgets.QWidget.__init__(self)
        #: Specifies whether the panel is dynamic. A dynamic panel is a panel
        #: that will be shown/hidden depending on the context.
        #: Dynamic panel should not appear in any GUI menu (e.g. no display
        #: in the panels menu of the notepad example).
        self.dynamic = dynamic
        #: Panel order into the zone it is installed to. This value is
        #: automatically set when installing the panel but it can be changed
        #: later (negative values can also be used).
        self.order_in_zone = -1
        self._scrollable = False
        #: Position in the editor (top, left, right, bottom)
        self.position = -1
        self._cached_background_brush = None
        self._cached_foreground_pen = None

    def on_install(self, editor):
        """
        Extends :meth:`pyqode.core.api.Mode.on_install` method to set the
        editor instance as the parent widget.

        .. warning:: Don't forget to call **super** if you override this
            method!

        :param editor: editor instance
        :type editor: pyqode.core.api.CodeEdit
        """
        Mode.on_install(self, editor)
        self.setParent(editor)
        self.setPalette(QtWidgets.QApplication.instance().palette())
        self.setFont(QtWidgets.QApplication.instance().font())
        self.editor.panels.refresh()

    @property
    def _background_brush(self):

        """
        Gives the brush that is used to draw the background. The panel can
        adopt the syntax theme, so that it blends in with the editor, which
        looks best for example for line numbers, or it can adopt the
        application theme, which looks best for example for the search panel.
        The brush is cached for performance.
        """

        if self._cached_background_brush is not None:
            return self._cached_background_brush
        if not self._use_syntax_theme:
            self._cached_background_brush = QtGui.QBrush(
                QtGui.QColor(self.palette().window().color())
            )
        else:
            try:
                self._color_scheme = \
                    self.editor.syntax_highlighter.color_scheme
            except AttributeError:
                # There is no syntax highlighter to adopt the theme from
                self._use_syntax_theme = False
                return self._background_brush
            self._cached_background_brush = \
                self._color_scheme.formats['background'].background()
        return self._cached_background_brush

    @property
    def _foreground_pen(self):

        """
        Gives the pen that is used to draw the foreground. The panel can
        adopt the syntax theme, so that it blends in with the editor, which
        looks best for example for line numbers, or it can adopt the
        application theme, which looks best for example for the search panel.
        The pen is cached for performance.
        """

        if self._cached_foreground_pen is not None:
            return self._cached_foreground_pen
        if not self._use_syntax_theme:
            self._cached_foreground_pen = QtGui.QPen(
                QtGui.QColor(self.palette().windowText().color())
            )
        else:
            try:
                self._color_scheme = \
                    self.editor.syntax_highlighter.color_scheme
            except AttributeError:
                # There is no syntax highlighter to adopt the theme from
                self._use_syntax_theme = False
                return self._foreground_pen
        self._cached_foreground_pen = \
            self._color_scheme.formats['normal'].foreground()
        return self._cached_foreground_pen

    def paintEvent(self, event):

        if not self.isVisible():
            return
        QtGui.QPainter(self).fillRect(event.rect(), self._background_brush)

    def setVisible(self, visible):
        """
        Shows/Hides the panel

        Automatically call CodeEdit.refresh_panels.

        :param visible: Visible state
        """
        _logger().log(5, '%s visibility changed', self.name)
        super(Panel, self).setVisible(visible)
        if self.editor:
            self.editor.panels.refresh()
