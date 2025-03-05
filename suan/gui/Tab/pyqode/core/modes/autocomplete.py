# -*- coding: utf-8 -*-
""" Contains the AutoCompleteMode """
import logging
from qtpy import QtCore, QtGui
from pyqode.core.api import TextHelper
from pyqode.core.api.mode import Mode


class AutoCompleteMode(Mode):
    """ Automatically complete quotes and parentheses

    Generic auto complete mode that automatically completes the following
    symbols:

        - " -> "
        - ' -> '
        - ( -> )
        - [ -> ]
        - { -> }
    """

    def __init__(self):
        super(AutoCompleteMode, self).__init__()
        #: Auto complete mapping, maps input key with completion text.
        self.MAPPING = {'"': '"', "'": "'", "(": ")", "{": "}", "[": "]"}
        self.AVOID_DUPLICATES = ')', ']', '}'
        #: The format to use for each symbol in mapping when there is a selection
        self.SELECTED_QUOTES_FORMATS = {
            key: '%s%s%s'
            for key in self.MAPPING.keys()
        }
        #: The format to use for each symbol in mapping when there is no selection
        self.QUOTES_FORMATS = {key: '%s' for key in self.MAPPING.keys()}
        self.logger = logging.getLogger(__name__)
        self._ignore_post = False

    def on_state_changed(self, state):
        if state:
            self.editor.post_key_pressed.connect(self._on_post_key_pressed)
            self.editor.key_pressed.connect(self._on_key_pressed)
        else:
            self.editor.post_key_pressed.disconnect(self._on_post_key_pressed)
            self.editor.key_pressed.disconnect(self._on_key_pressed)
        self._helper = TextHelper(self.editor)

    def _on_post_key_pressed(self, event):
        if event.isAccepted() or self._ignore_post:
            self._ignore_post = False
            return
        txt = event.text()
        if txt not in self.MAPPING:
            return
        to_insert = self.MAPPING[txt]
        if to_insert == txt:
            # For quotes (characters that map onto themselves), we don't
            # autocomplete if there's already an even number of characters.
            # This avoids over-autocompleting quotes that are already balanced.
            cursor = self.editor.textCursor()
            before_cursor = cursor.block().text()[:cursor.positionInBlock()]
            if not before_cursor.count(to_insert) % 2:
                return
        next_char = self._helper.get_right_character()
        if (not next_char or next_char in self.MAPPING.keys() or
                next_char in self.MAPPING.values() or
                next_char.isspace()):
            self._helper.insert_text(
                self.QUOTES_FORMATS[txt] % to_insert
            )

    def _on_key_pressed(self, event):
        if event.isAccepted():
            return
        txt = event.text()
        cursor = self.editor.textCursor()
        next_char = self._helper.get_right_character()
        if cursor.hasSelection():
            # quoting of selected text
            if txt in self.MAPPING.keys():
                closing_char = self.MAPPING[txt]
                cursor.beginEditBlock()
                cursor.insertText(
                    txt + cursor.selectedText() + closing_char
                )
                # Don't duplocate the closing character
                if self._helper.get_right_character(cursor) == closing_char:
                    cursor.insertText('')
                else:
                    cursor.movePosition(cursor.Left, cursor.MoveAnchor, 1)
                self.editor.setTextCursor(cursor)
                cursor.endEditBlock()
                event.accept()
            self._ignore_post = True
            return
        ignore = False
        if event.key() == QtCore.Qt.Key_Backspace:
            # If we're in between two quotes, a backspace will delete both
            # quotes.
            del_char = self._helper.get_left_character()
            if (
                    del_char in self.MAPPING and
                    self.MAPPING[del_char] == next_char
            ):
                # First select the previous and next character and replace it
                # by an empty string. Then move the cursor one position back.
                cursor.beginEditBlock()
                cursor.movePosition(cursor.Left, cursor.MoveAnchor, 1)
                cursor.movePosition(cursor.Right, cursor.KeepAnchor, 2)
                cursor.deleteChar()
                cursor.endEditBlock()
                self.editor.setTextCursor(cursor)
                event.accept()
                return
        elif (
                # If the next character is already a character that we just
                # autocompleted, then ignore the key press
                txt and next_char == txt and (
                next_char in self.MAPPING or
                txt in self.AVOID_DUPLICATES
        )
        ):
            ignore = True
        if ignore:
            event.accept()
            self._helper.clear_selection()
            self._helper.move_right()
