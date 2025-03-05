# -*- coding: utf-8 -*-
"""
Contains a line-sorter mode.
"""
from pyqode.core.api.mode import Mode
from pyqode.core.api.utils import TextHelper
from qtpy.QtWidgets import QAction, QMenu


class LineSorterMode(Mode):
    """ Provides context actions for sorting lines of selected text.

    It does so by adding two new menu entries to the editor's context menu:
      - *Sort lines ascending*
      - *Sort lines descending*
    """

    def __init__(self):
        Mode.__init__(self)
        self._actions_created = False
        self._action_sort_descending = None
        self._action_sort_ascending = None

    def _sort(self, reverse=False):
        th = TextHelper(self.editor)
        th.insert_text(u'\n'.join(
            sorted(
                th.selected_text().replace(u'\u2029', u'\n').split(u'\n'),
                key=str.lstrip,
                reverse=reverse
            )
        ))

    def _sort_descending(self):
        self._sort(reverse=True)

    def _create_actions(self):
        """ Create associated actions """
        self._action_sort_ascending = QAction(
            _('Sort selected lines (ascending)'),
            self.editor
        )
        self._action_sort_ascending.triggered.connect(self._sort)

        self._action_sort_descending = QAction(
            _('Sort selected lines (descending)'),
            self.editor
        )
        self._action_sort_descending.triggered.connect(self._sort_descending)
        self.menu = QMenu(_('Sort'), self.editor)
        self.menu.addAction(self._action_sort_ascending)
        self.menu.addAction(self._action_sort_descending)
        self._actions_created = True

    def on_state_changed(self, state):
        if state:
            if not self._actions_created:
                self._create_actions()
            self.editor.add_action(self.menu.menuAction())
        else:
            self.editor.remove_action(self.menu.menuAction())
