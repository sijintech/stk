# -*- coding: utf-8 -*-
"""
This module contains the code completion mode and the related classes.
"""
import logging
import re
import sys
import time
from pyqode.core.api.mode import Mode
from pyqode.core.backend import NotRunning
from qtpy import QtWidgets, QtCore, QtGui
from pyqode.core.api.utils import TextHelper
from pyqode.core import backend

NAVIGATION_KEYS = (
    QtCore.Qt.Key_Backspace,
    QtCore.Qt.Key_Back,
    QtCore.Qt.Key_Delete,
    QtCore.Qt.Key_End,
    QtCore.Qt.Key_Home,
    QtCore.Qt.Key_Left,
    QtCore.Qt.Key_Right,
    QtCore.Qt.Key_Up,
    QtCore.Qt.Key_Down,
    QtCore.Qt.Key_Space
)
MIN_WIDTH = 200
icon_cache = {}


def _logger():
    return logging.getLogger(__name__)


def debug(msg, *args):
    """
    Log internal debugger messages (user should not see them, even in debug
    mode)
    """
    return _logger().log(5, msg, *args)


class SubsequenceSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Performs subsequence matching/sorting (see pyQode/pyQode#1).
    """

    def __init__(self, case, parent=None):
        QtCore.QSortFilterProxyModel.__init__(self, parent)
        self.case = case

    def set_prefix(self, prefix):
        self.filter_patterns = []
        self.filter_patterns_case_sensitive = []
        self.sort_patterns = []
        if self.case == QtCore.Qt.CaseInsensitive:
            flags = re.IGNORECASE
        else:
            flags = 0
        for i in reversed(range(1, len(prefix) + 1)):
            ptrn = '.*%s.*%s' % (prefix[0:i], prefix[i:])
            try:
                self.filter_patterns.append(re.compile(ptrn, flags))
                self.filter_patterns_case_sensitive.append(re.compile(ptrn, 0))
                ptrn = '%s.*%s' % (prefix[0:i], prefix[i:])
                self.sort_patterns.append(re.compile(ptrn, flags))
            except Exception:
                continue
        self.prefix = prefix

    def filterAcceptsRow(self, row, _):
        completion = self.sourceModel().data(self.sourceModel().index(row, 0))
        if completion is None or self.prefix is None:
            return False
        if len(completion) < len(self.prefix):
            return False
        if len(self.prefix) == 1:
            try:
                prefix = self.prefix
                if self.case == QtCore.Qt.CaseInsensitive:
                    completion = completion.lower()
                    prefix = self.prefix.lower()
                rank = completion.index(prefix)
                self.sourceModel().setData(
                    self.sourceModel().index(row, 0), rank, QtCore.Qt.UserRole)
                return prefix in completion
            except ValueError:
                return False
        for i, patterns in enumerate(zip(self.filter_patterns,
                                         self.filter_patterns_case_sensitive,
                                         self.sort_patterns)):
            pattern, pattern_case, sort_pattern = patterns
            match = re.match(pattern, completion)
            if match:
                # compute rank, the lowest rank the closer it is from the
                # completion
                start = sys.maxsize
                for m in sort_pattern.finditer(completion):
                    start, end = m.span()
                rank = start + i * 10
                if re.match(pattern_case, completion):
                    # favorise completions where case is matched
                    rank -= 10
                self.sourceModel().setData(
                    self.sourceModel().index(row, 0), rank, QtCore.Qt.UserRole)
                return True
        return len(self.prefix) == 0


class SubsequenceCompleter(QtWidgets.QCompleter):
    """
    QCompleter specialised for subsequence matching
    """

    def __init__(self, *args):
        super(SubsequenceCompleter, self).__init__(*args)
        self.local_completion_prefix = ""
        self.source_model = None
        self.filterProxyModel = SubsequenceSortFilterProxyModel(
            self.caseSensitivity(), parent=self)
        self.filterProxyModel.setSortRole(QtCore.Qt.UserRole)
        self._force_next_update = True

    def setModel(self, model):
        self.source_model = model
        self.filterProxyModel = SubsequenceSortFilterProxyModel(
            self.caseSensitivity(), parent=self)
        self.filterProxyModel.setSortRole(QtCore.Qt.UserRole)
        self.filterProxyModel.set_prefix(self.local_completion_prefix)
        self.filterProxyModel.setSourceModel(self.source_model)
        super(SubsequenceCompleter, self).setModel(self.filterProxyModel)
        self.filterProxyModel.invalidate()
        self.filterProxyModel.sort(0)
        self._force_next_update = True

    def update_model(self):
        if (self.completionCount() or
                len(self.local_completion_prefix) <= 1 or
                self._force_next_update):
            self.filterProxyModel.set_prefix(self.local_completion_prefix)
            self.filterProxyModel.invalidate()  # force sorting/filtering
        if self.completionCount() > 1:
            self.filterProxyModel.sort(0)
        self._force_next_update = False

    def splitPath(self, path):
        self.local_completion_prefix = path
        self.update_model()
        return ['']


class CodeCompletionMode(Mode, QtCore.QObject):
    """ Provides code completions when typing or when pressing Ctrl+Space.

    This mode provides a code completion system which is extensible.
    It takes care of running the completion request in a background process
    using one or more completion provider and display the results in a
    QCompleter.

    To add code completion for a specific language, you only need to
    implement a new
    :class:`pyqode.core.backend.workers.CodeCompletionWorker.Provider`

    The completion popup is shown when the user press **ctrl+space** or
    automatically while the user is typing some code (this can be configured
    using a series of properties).
    """
    #: Filter completions based on the prefix. FAST
    FILTER_PREFIX = 0
    #: Filter completions based on whether the prefix is contained in the
    #: suggestion. Only available with PyQt5, if set with PyQt4, FILTER_PREFIX
    #: will be used instead. FAST
    FILTER_CONTAINS = 1
    #: Fuzzy filtering, using the subsequence matcher. This is the most
    #: powerful filter mode but also the SLOWEST.
    FILTER_FUZZY = 2

    @property
    def filter_mode(self):
        """
        The completion filter mode
        """
        return self._filter_mode

    @filter_mode.setter
    def filter_mode(self, value):
        self._filter_mode = value
        self._create_completer()

    @property
    def trigger_key(self):
        """
        The key that triggers code completion (Default is **Space**:
        Ctrl + Space).
        """
        return self._trigger_key

    @trigger_key.setter
    def trigger_key(self, value):
        self._trigger_key = value
        if self.editor:
            # propagate changes to every clone
            for clone in self.editor.clones:
                try:
                    clone.modes.get(CodeCompletionMode).trigger_key = value
                except KeyError:
                    # this should never happen since we're working with clones
                    pass

    @property
    def trigger_length(self):
        """
        The trigger length defines the word length required to run code
        completion.
        """
        return self._trigger_len

    @trigger_length.setter
    def trigger_length(self, value):
        self._trigger_len = value
        if self.editor:
            # propagate changes to every clone
            for clone in self.editor.clones:
                try:
                    clone.modes.get(CodeCompletionMode).trigger_length = value
                except KeyError:
                    # this should never happen since we're working with clones
                    pass

    @property
    def trigger_symbols(self):
        """
        Defines the list of symbols that immediately trigger a code completion
        requiest. BY default, this list contains the dot character.

        For C++, we would add the '->' operator to that list.
        """
        return self._trigger_symbols

    @trigger_symbols.setter
    def trigger_symbols(self, value):
        self._trigger_symbols = value
        if self.editor:
            # propagate changes to every clone
            for clone in self.editor.clones:
                try:
                    clone.modes.get(CodeCompletionMode).trigger_symbols = value
                except KeyError:
                    # this should never happen since we're working with clones
                    pass

    @property
    def case_sensitive(self):
        """
        True to performs case sensitive completion matching.
        """
        return self._case_sensitive

    @case_sensitive.setter
    def case_sensitive(self, value):
        self._case_sensitive = value
        if self.editor:
            # propagate changes to every clone
            for clone in self.editor.clones:
                try:
                    clone.modes.get(CodeCompletionMode).case_sensitive = value
                except KeyError:
                    # this should never happen since we're working with clones
                    pass

    @property
    def completion_prefix(self):
        """
        Returns the current completion prefix
        """
        return self._helper.word_under_cursor(
            select_whole_word=False).selectedText().strip()

    @property
    def show_tooltips(self):
        """
        True to show tooltips next to the current completion.
        """
        return self._show_tooltips

    @show_tooltips.setter
    def show_tooltips(self, value):
        self._show_tooltips = value
        if self.editor:
            # propagate changes to every clone
            for clone in self.editor.clones:
                try:
                    clone.modes.get(CodeCompletionMode).show_tooltips = value
                except KeyError:
                    # this should never happen since we're working with clones
                    pass

    def __init__(self):
        Mode.__init__(self)
        QtCore.QObject.__init__(self)
        self._current_completion = ""
        self._trigger_key = QtCore.Qt.Key_Space
        self._trigger_len = 1
        self._trigger_symbols = ['.']
        self._case_sensitive = False
        self._completer = None
        self._filter_mode = self.FILTER_FUZZY
        self._last_cursor_line = -1
        self._last_cursor_column = -1
        self._last_completion_prefix = ''
        self._tooltips = {}
        self._completions = None
        self._completion_anchor = None
        self._completion_rect = None
        self._char_width = None
        self._show_tooltips = False
        self._request_id = self._last_request_id = 0
        self._working = False
        self._stylesheet_initialized = False

    def clone_settings(self, original):
        self.trigger_key = original.trigger_key
        self.trigger_length = original.trigger_length
        self.trigger_symbols = original.trigger_symbols
        self.show_tooltips = original.show_tooltips
        self.case_sensitive = original.case_sensitive

    #
    # Mode interface
    #
    def _create_completer(self):
        if self.filter_mode != self.FILTER_FUZZY:
            self._completer = QtWidgets.QCompleter([''], self.editor)
            if self.filter_mode == self.FILTER_CONTAINS:
                try:
                    self._completer.setFilterMode(QtCore.Qt.MatchContains)
                except AttributeError:
                    # only available with PyQt5
                    pass
        else:
            self._completer = SubsequenceCompleter(self.editor)
        self._completer.setCompletionMode(self._completer.CompletionMode.PopupCompletion)
        if self.case_sensitive:
            self._completer.setCaseSensitivity(QtCore.Qt.CaseSensitive)
        else:
            self._completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._completer.activated.connect(self._insert_completion)
        self._completer.highlighted.connect(
            self._on_selected_completion_changed)
        self._completer.highlighted.connect(self._display_completion_tooltip)

    def on_install(self, editor):
        Mode.on_install(self, editor)
        self._create_completer()
        self._completer.setModel(QtGui.QStandardItemModel())
        self._helper = TextHelper(editor)

    def on_uninstall(self):
        Mode.on_uninstall(self)
        self._completer.popup().hide()
        self._completer = None

    def on_state_changed(self, state):
        if state:
            self.editor.focused_in.connect(self._on_focus_in)
            self.editor.key_pressed.connect(self._on_key_pressed)
            self.editor.post_key_pressed.connect(self._on_key_released)
        else:
            self.editor.focused_in.disconnect(self._on_focus_in)
            self.editor.key_pressed.disconnect(self._on_key_pressed)
            self.editor.post_key_pressed.disconnect(self._on_key_released)

    #
    # Slots
    #
    def _on_key_pressed(self, event):
        def _handle_completer_events():
            nav_key = self._is_navigation_key(event)
            mod = QtCore.Qt.ControlModifier
            ctrl = event.modifiers() == mod
            # complete
            if event.key() in [
                QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return,
                QtCore.Qt.Key_Tab]:
                self._insert_completion(self._current_completion)
                self._hide_popup()
                event.accept()
            # hide
            elif (event.key() in [
                QtCore.Qt.Key_Escape, QtCore.Qt.Key_Backtab] or
                  nav_key and ctrl):
                self._reset_sync_data()
            # move into list
            elif event.key() == QtCore.Qt.Key_Home:
                self._show_popup(index=0)
                event.accept()
            elif event.key() == QtCore.Qt.Key_End:
                self._show_popup(index=self._completer.completionCount() - 1)
                event.accept()

        debug('key pressed: %s' % event.text())
        is_shortcut = self._is_shortcut(event)
        # handle completer popup events ourselves
        if self._completer.popup().isVisible():
            if is_shortcut:
                event.accept()
            else:
                _handle_completer_events()
        elif is_shortcut:
            self._reset_sync_data()
            self.request_completion()
            event.accept()

    def _on_key_released(self, event):
        if self._is_shortcut(event) or event.isAccepted():
            return
        debug('key released:%s' % event.text())
        word = self._helper.word_under_cursor(
            select_whole_word=True).selectedText()
        debug('word: %s' % word)
        if event.text():
            if event.key() == QtCore.Qt.Key_Escape:
                self._hide_popup()
                return
            if self._is_navigation_key(event) and \
                    (not self._is_popup_visible() or word == ''):
                self._reset_sync_data()
                return
            if event.key() == QtCore.Qt.Key_Return:
                return
            if event.text() in self._trigger_symbols:
                # symbol trigger, force request
                self._reset_sync_data()
                self.request_completion(triggered_by_symbol=True)
            elif len(word) >= self._trigger_len and event.text() not in \
                    self.editor.word_separators:
                # Length trigger
                if event.modifiers() in [
                    QtCore.Qt.NoModifier, QtCore.Qt.ShiftModifier]:
                    self.request_completion()
                else:
                    self._hide_popup()
            else:
                self._reset_sync_data()
        else:
            if self._is_navigation_key(event):
                if self._is_popup_visible() and word:
                    self._show_popup()
                    return
                else:
                    self._reset_sync_data()

    def _on_focus_in(self, event):
        """
        Resets completer's widget

        :param event: QFocusEvents
        """
        self._completer.setWidget(self.editor)

    def _on_selected_completion_changed(self, completion):
        self._current_completion = completion

    def _insert_completion(self, completion):
        # If the completions ends with the part of the word that follows the
        # cursor, then the entire word is replaced. This avoid duplicating
        # parts of words through autocompletion.
        trailing_text = self._helper.word_under_cursor(
            select_whole_word=True,
            from_start=False
        ).selectedText()
        cursor = self._helper.word_under_cursor(
            select_whole_word=completion.endswith(trailing_text)
        )
        cursor.insertText(completion)
        self.editor.setTextCursor(cursor)

    def _on_results_available(self, results):
        self._working = False
        debug("completion results (completions=%r), prefix=%s",
              results, self.completion_prefix)
        context = results[0]
        results = results[1:]
        line, column, request_id = context
        debug('request context: %r', context)
        debug('latest context: %r', (self._last_cursor_line,
                                     self._last_cursor_column,
                                     self._request_id))
        self._last_request_id = request_id
        if (line == self._last_cursor_line and
                column == self._last_cursor_column):
            if self.editor:
                all_results = []
                for res in results:
                    all_results += res
                self._show_completions(all_results)
        else:
            debug('outdated request, dropping')

    #
    # Helper methods
    #
    def _is_popup_visible(self):
        return self._completer.popup().isVisible()

    def _reset_sync_data(self):
        debug('reset sync data and hide popup')
        self._last_cursor_line = -1
        self._last_cursor_column = -1
        self._last_completion_prefix = ''
        self._hide_popup()

    def request_completion(self, triggered_by_symbol=False):
        if self._working:
            return
        self._working = True
        line = self._helper.current_line_nbr()
        column = self._helper.current_column_nbr() - \
                 len(self.completion_prefix)
        same_context = (
                line == self._last_cursor_line and
                column == self._last_cursor_column and
                self.completion_prefix == self._last_completion_prefix
        )
        if same_context:
            if self._request_id - 1 == self._last_request_id:
                # context has not changed and the correct results can be
                # directly shown
                debug('request completion ignored, context has not changed')
                self._show_popup()
            return True
        debug('requesting completion')
        data = {
            'code': self.editor.toPlainText(),
            'line': line,
            'column': column,
            'path': self.editor.file.path,
            'encoding': self.editor.file.encoding,
            'prefix': self.completion_prefix,
            'request_id': self._request_id,
            'triggered_by_symbol': triggered_by_symbol
        }
        try:
            self.editor.backend.send_request(
                backend.CodeCompletionWorker, args=data,
                on_receive=self._on_results_available)
        except NotRunning:
            _logger().exception('failed to send the completion request')
            return False
        else:
            debug('request sent: %r', data)
            self._last_cursor_column = column
            self._last_cursor_line = line
            self._last_completion_prefix = self.completion_prefix
            self._request_id += 1
            return True

    def _is_shortcut(self, event):
        """
        Checks if the event's key and modifiers make the completion shortcut
        (Ctrl+Space)

        :param event: QKeyEvent

        :return: bool
        """
        modifier = (QtCore.Qt.MetaModifier if sys.platform == 'darwin' else
                    QtCore.Qt.ControlModifier)
        valid_modifier = event.modifiers() == modifier
        valid_key = event.key() == self._trigger_key
        return valid_key and valid_modifier

    def _hide_popup(self):
        """
        Hides the completer popup
        """
        debug('hide popup')
        if (self._completer.popup() is not None and
                self._completer.popup().isVisible()):
            self._completer.popup().hide()
            self._last_cursor_column = -1
            self._last_cursor_line = -1
            self._last_completion_prefix = ''
            QtWidgets.QToolTip.hideText()

    def _update_popup_rect(self, anchor):
        """
        Updates the rectangle of the completer. If the anchor stays the same,
        only the width of the popup is adjusted. Otherwise, the position is
        also adjusted. There is a minimum with for the completer, because
        occasionally the size hint returns 0, even when there are completion
        entries.
        
        :param anchor: the anchor of the cursor, i.e. the start of the
                       to-be-completed word.
        """
        if anchor != self._completion_anchor:
            self._completion_rect = self.editor.cursorRect()
            if self._char_width is None:
                self._char_width = self.editor.fontMetrics().width('_')
            prefix_len = (len(self.completion_prefix) * self._char_width)
            self._completion_rect.translate(
                self.editor.panels.margin_size() - prefix_len,
                self.editor.panels.margin_size(0) + 5
            )
            self._completion_anchor = anchor
        popup = self._completer.popup()
        width_hint = max(MIN_WIDTH, popup.sizeHintForColumn(0))
        self._completion_rect.setWidth(
            width_hint + popup.verticalScrollBar().sizeHint().width()
        )

    def _show_popup(self, index=0):
        """
        Shows the popup at the specified index.
        :param index: index
        :return:
        """

        # If the cursor is not at the end of the document, then we check
        # whether the next character is a word separator If not, then we don't
        # offer completions, because we don't want to complete in the middle of
        # a word.
        ch = self._helper.get_right_character()  # None means end of document
        if ch is not None and ch not in self.editor.word_separators:
            return
        # Get the word that was typed so far
        text_cursor = self.editor.textCursor()
        text_cursor.movePosition(text_cursor.Left, text_cursor.MoveAnchor, 1)
        text_cursor.select(text_cursor.WordUnderCursor)
        self._update_popup_rect(text_cursor.anchor())
        word_so_far = text_cursor.selectedText()
        self._completer.setCaseSensitivity(
            QtCore.Qt.CaseSensitive
            if self._case_sensitive
            else QtCore.Qt.CaseInsensitive
        )
        self._completer.setCompletionPrefix(self.completion_prefix)
        # Move to the first suggestion that is not the current word, and hide
        # the popup if no such suggestion exists.
        for row in range(self._completer.completionCount()):
            self._completer.setCurrentRow(row)
            if self._completer.currentCompletion() != word_so_far:
                break
        else:
            self._hide_popup()
            return
        if not self.editor.isVisible():
            debug('cannot show popup, editor is not visible')
            return
        if self._completer.widget() != self.editor:
            self._completer.setWidget(self.editor)
        self._completer.complete(self._completion_rect)
        # The QCompleter popup doesn't respect the stylesheet. Here we
        # reconstruct a basic stylesheet and directly apply it. There may be
        # more elegant solutions, but this works.
        if not self._stylesheet_initialized:
            self._completer.popup().setStyleSheet(
                '''
                background: {};
                color: {};
                font-family: {};
                font-size: {};
                '''.format(
                    self.editor.palette().base().color().name(),
                    self.editor.palette().text().color().name(),
                    self.editor.font_name,
                    self.editor.font_size,
                )
            )
            self._stylesheet_initialized = True
        self._completer.popup().setCurrentIndex(
            self._completer.completionModel().index(row, 0)
        )

    def _show_completions(self, completions):
        self._update_model(completions)
        self._show_popup()

    def _icon(self, name):
        if isinstance(name, list):
            name, fallback = name
        else:
            fallback = None
        if name in icon_cache:
            return icon_cache[name]
        if fallback is None:
            icon = QtGui.QIcon(name)
        else:
            icon = QtGui.QIcon.fromTheme(name, self._icon(fallback))
        icon_cache[name] = icon
        return icon

    def _update_model(self, completions):
        """
        Creates a QStandardModel that holds the suggestion from the completion
        models for the QCompleter

        :param completionPrefix:
        """
        if self._completions == completions:
            return  # avoid unnecessary updates to avoid flickering
        self._completions = completions
        self._completion_anchor = None
        # build the completion model
        cc_model = QtGui.QStandardItemModel()
        self._tooltips.clear()
        for completion in completions:
            name = completion['name']
            item = QtGui.QStandardItem()
            item.setData(name, QtCore.Qt.DisplayRole)
            if 'tooltip' in completion and completion['tooltip']:
                self._tooltips[name] = completion['tooltip']
            if 'icon' in completion:
                item.setData(self._icon(completion['icon']),
                             QtCore.Qt.DecorationRole)
            cc_model.appendRow(item)
        try:
            self._completer.setModel(cc_model)
        except RuntimeError:
            self._create_completer()
            self._completer.setModel(cc_model)
        return cc_model

    def _display_completion_tooltip(self, completion):
        if not self._show_tooltips:
            return
        if completion not in self._tooltips:
            QtWidgets.QToolTip.hideText()
            return
        tooltip = self._tooltips[completion].strip()
        pos = self._completer.popup().pos()
        pos.setX(pos.x() + self._completer.popup().size().width())
        pos.setY(pos.y() - 15)
        QtWidgets.QToolTip.showText(pos, tooltip, self.editor)

    @staticmethod
    def _is_navigation_key(event):
        return event.key() in NAVIGATION_KEYS
