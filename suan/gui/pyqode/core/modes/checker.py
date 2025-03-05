# -*- coding: utf-8 -*-
"""
This module contains the checker mode, a base class for code checker modes.
"""
import logging
from pyqode.core import icons
from pyqode.core.api import TextBlockUserData
from pyqode.core.api.decoration import TextDecoration
from pyqode.core.api.mode import Mode
from pyqode.core.backend import NotRunning
from pyqode.core.api.utils import DelayJobRunner
from qtpy import QtCore, QtGui


class CheckerMessages(object):
    """
    Enumerates the possible checker message types.
    """
    #: Status value for an information message.
    INFO = 0
    #: Status value for a warning message.
    WARNING = 1
    #: Status value for an error message.
    ERROR = 2


class CheckerMessage(object):
    """
    Holds data for a message displayed by the
    :class:`pyqode.core.modes.CheckerMode`.
    """

    @classmethod
    def status_to_string(cls, status):
        """
        Converts a message status to a string.

        :param status: Status to convert (p yqode.core.modes.CheckerMessages)
        :return: The status string.
        :rtype: str
        """
        strings = {CheckerMessages.INFO: "Info",
                   CheckerMessages.WARNING: "Warning",
                   CheckerMessages.ERROR: "Error"}
        return strings[status]

    @property
    def status_string(self):
        """
        Returns the message status as a string.

        :return: The status string.
        """
        return self.status_to_string(self.status)

    def __init__(self, description, status, line, text_range=None, icon=None,
                 color=None, path=None, block=None, underline=False,
                 checker_mode=None):
        """
        :param description: The message description (used as a tooltip)
        :param status: The status associated with the message.
        :param line: The message line number
        :param text_range: The start and end range of the text. If specified,
            this overrides the line for the text highlighting.
        :param icon: Unused, we keep it for backward compatiblity.
        :param color: Text decoration color
        :param path: file path. Optional
        """
        assert 0 <= status <= 2
        #: The description of the message, used as a tooltip.
        self.description = description
        #: The status associated with the message. One of:
        #:    * :const:`pyqode.core.modes.CheckerMessages.INFO`
        #:    * :const:`pyqode.core.modes.CheckerMessages.WARNING`
        #:    * :const:`pyqode.core.modes.CheckerMessages.ERROR`
        self.status = status
        #: The line of the message
        self.line = line
        #: The start column (used for the text decoration). If the col is None,
        #: the whole line is highlighted.
        self.text_range = text_range
        self.color = (
            color if color is not None
            else icons.QTA_OPTIONS['color_info']
            if status == CheckerMessages.INFO
            else icons.QTA_OPTIONS['color_warning']
            if status == CheckerMessages.WARNING
            else icons.QTA_OPTIONS['color_error']
        )
        self.decoration = None
        self.path = path
        #: store a reference to the associated QTextBlock, for quick acces
        self.block = block
        self.underline = underline
        self.checker_mode = checker_mode

    def __str__(self):
        return "{0} l{1}".format(self.description, self.line)

    def __eq__(self, other):
        return (
                self.text_range == other.text_range and
                self.block == other.block and
                self.description == other.description and
                self.path == other.path
        )

    def icon(self):
        return self.checker_mode.message_icon(self)

    def tooltip(self):
        return self.checker_mode.message_tooltip(self)

    def widget(self):
        return self.checker_mode.message_widget(self)

    def show_on_panel(self, panel):
        return self.checker_mode.show_on_panel(panel)

    def clicked(self, event):
        self.checker_mode.message_clicked(self, event)


def _logger(klass):
    return logging.getLogger('%s [%s]' % (__name__, klass.__name__))


class CheckerMode(Mode, QtCore.QObject):
    """
    Performs a user defined code analysis job using the backend and
    display the results on the editor instance.

    The user defined code analysis job is a simple **function** with the
    following signature:

    .. code-block:: python

        def analysisProcess(data)

    where data is the request data:

    .. code-block:: python

        request_data = {
                'code': self.editor.toPlainText(),
                'path': self.editor.file.path,
                'encoding': self.editor.file.encoding
            }

    and the return value is a tuple made up of the following elements:

        (description, status, line, [col], [icon], [color], [path])

    The background process is ran when the text changed and the ide is an idle
    state for a few seconds.

    You can also request an analysis manually using
    :meth:`pyqode.core.modes.CheckerMode.request_analysis`

    Messages are displayed as text decorations on the editor. A checker panel
    will take care of display message icons next to each line.
    """

    @property
    def messages(self):
        """
        Returns the entire list of checker messages.
        """
        return self._messages

    def __init__(self, worker,
                 underline=True,
                 delay=500,
                 show_tooltip=True):
        """
        :param worker: The process function or class to call remotely.
        :param underline: Indicates whether lines should be decorated.
        :param delay: The delay used before running the analysis process when
                      trigger is set to
                      :class:pyqode.core.modes.CheckerTriggers`
        :param show_tooltip: Specify if a tooltip must be displayed when the
                             mouse is over a checker message decoration.
        """
        Mode.__init__(self)
        QtCore.QObject.__init__(self)
        # max number of messages to keep good performances
        self.limit = 200
        self.ignore_rules = []
        self._extra_info = {}
        self._job_runner = DelayJobRunner(delay=delay)
        self._messages = []
        self._worker = worker
        self._mutex = QtCore.QMutex()
        self._show_tooltip = show_tooltip
        self._pending_msg = []
        self._finished = True
        self._underline = underline
        self.info_icon = icons.icon(
            'dialog-info', ':pyqode-icons/rc/dialog-info.png',
            'fa.info-circle',
            qta_options={'color': icons.QTA_OPTIONS['color_info']})
        self.warning_icon = icons.icon(
            'dialog-warning', ':pyqode-icons/rc/dialog-warning.png',
            'fa.exclamation-triangle',
            qta_options={'color': icons.QTA_OPTIONS['color_warning']})
        self.error_icon = icons.icon(
            'dialog-error', ':pyqode-icons/rc/dialog-error.png',
            'fa.exclamation-circle',
            qta_options={'color': icons.QTA_OPTIONS['color_error']})
        self._checker_icons = {
            CheckerMessages.INFO: self.info_icon,
            CheckerMessages.WARNING: self.warning_icon,
            CheckerMessages.ERROR: self.error_icon
        }

    def set_ignore_rules(self, rules):
        """
        Sets the ignore rules for the linter.

        Rules are a list of string that the actual linter function will check
        to reject some warnings/errors.
        """
        self.ignore_rules = rules

    def add_extra_info(self, key, value):
        """
        Allows additional info to be passed onto the linter. Things like the
        language for spell checking.
        """
        self._extra_info[key] = value

    def get_extra_info(self, key):
        """Gets additional info for the linter."""
        return self._extra_info[key]

    def add_messages(self, messages):
        """
        Adds a message or a list of message.

        :param messages: A list of messages or a single message
        """
        if len(messages) > self.limit:
            messages = messages[:self.limit]
        _logger(self.__class__).log(5, 'adding %s messages' % len(messages))
        self._finished = False
        self._new_messages = messages
        self._to_check = list(self._messages)
        self._pending_msg = messages
        # start removing messages, new message won't be added until we
        # checked all message that need to be removed
        QtCore.QTimer.singleShot(1, self._remove_batch)

    def _remove_batch(self):
        if self.editor is None:
            return
        for i in range(100):
            if not len(self._to_check):
                # all messages checker, start adding messages now
                QtCore.QTimer.singleShot(1, self._add_batch)
                self.editor.repaint()
                return False
            msg = self._to_check.pop(0)
            if msg.block is None:
                msg.block = self.editor.document().findBlockByNumber(msg.line)
            if msg not in self._new_messages:
                self.remove_message(msg)
        self.editor.repaint()
        QtCore.QTimer.singleShot(1, self._remove_batch)

    def _add_batch(self):

        if self.editor is None:
            return
        for i in range(10):
            if not len(self._pending_msg):
                # all pending message added
                self._finished = True
                _logger(self.__class__).log(5, 'finished')
                self.editor.decorations.set_on_editor()
                self.editor.repaint()
                return False
            message = self._pending_msg.pop(0)
            if message.line < 0:
                continue
            usd = message.block.userData()
            if usd is None:
                usd = TextBlockUserData()
                message.block.setUserData(usd)
            # check if the same message already exists
            if message in usd.messages:
                continue
            self._messages.append(message)
            usd.messages.append(message)
            tooltip = None
            if self._show_tooltip:
                tooltip = message.description
            if not message.underline:
                continue
            start_pos, end_pos = (
                message.text_range
                if message.text_range is not None
                else (None, None)
            )
            message.decoration = TextDecoration(
                self.editor.textCursor(),
                start_line=message.line,
                start_pos=start_pos,
                end_pos=end_pos,
                tooltip=tooltip,
                draw_order=3,
                full_width=start_pos is None
            )
            message.decoration.set_as_error(color=QtGui.QColor(message.color))
            self.editor.decorations.append(
                message.decoration,
                set_on_editor=False
            )
        QtCore.QTimer.singleShot(1, self._add_batch)
        self.editor.decorations.set_on_editor()
        self.editor.repaint()
        return True

    def remove_message(self, message):
        """
        Removes a message.

        :param message: Message to remove
        """
        usd = message.block.userData()
        if usd:
            try:
                usd.messages.remove(message)
            except (AttributeError, ValueError):
                pass
        if message.decoration:
            self.editor.decorations.remove(message.decoration)
        self._messages.remove(message)

    def clear_messages(self):
        """
        Clears all messages.
        """
        while self._messages:
            self.remove_message(self._messages[0])

    def on_state_changed(self, state):
        if state:
            self.editor.textChanged.connect(self.request_analysis)
            self.editor.new_text_set.connect(self.clear_messages)
            self.request_analysis()
        else:
            self.editor.textChanged.disconnect(self.request_analysis)
            self.editor.new_text_set.disconnect(self.clear_messages)
            self._job_runner.cancel_requests()
            self.clear_messages()

    def _on_work_finished(self, results):
        """
        Display results.

        :param status: Response status
        :param results: Response data, messages.
        """

        messages = []
        for msg in results:
            msg = CheckerMessage(*msg)
            msg.underline = self._underline
            msg.checker_mode = self
            if msg.line >= self.editor.blockCount():
                msg.line = self.editor.blockCount() - 1
            block = self.editor.document().findBlockByNumber(msg.line)
            msg.block = block
            messages.append(msg)
        self.add_messages(messages)

    def request_analysis(self):
        """
        Requests an analysis.
        """
        if self._finished:
            _logger(self.__class__).log(5, 'running analysis')
            self._job_runner.request_job(self._request)
        elif self.editor:
            # retry later
            _logger(self.__class__).log(
                5, 'delaying analysis (previous analysis not finished)')
            QtCore.QTimer.singleShot(500, self.request_analysis)

    def _request(self):
        """ Requests a checking of the editor content. """
        try:
            self.editor.toPlainText()
        except (TypeError, RuntimeError):
            return
        try:
            max_line_length = self.editor.modes.get(
                'RightMarginMode').position
        except KeyError:
            max_line_length = 79
        request_data = {
            'code': self.editor.toPlainText(),
            'path': self.editor.file.path,
            'encoding': self.editor.file.encoding,
            'ignore_rules': self.ignore_rules,
            'max_line_length': max_line_length
        }
        request_data.update(self._extra_info)
        try:
            self.editor.backend.send_request(
                self._worker, request_data, on_receive=self._on_work_finished)
            self._finished = False
        except NotRunning:
            # retry later
            QtCore.QTimer.singleShot(100, self._request)

    def message_icon(self, msg):
        return self._checker_icons[msg.status]

    def message_tooltip(self, msg):
        return msg.description

    def message_widget(self, msg):
        return None

    def show_on_panel(self, panel):
        return panel.__class__.__name__ == 'CheckerPanel'

    def message_clicked(self, msg, event):
        pass
