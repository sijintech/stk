# -*- coding: utf-8 -*-
import os
from pyqode.core import api, icons
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QAction


class CommentsMode(api.Mode):
    """Comments/uncomments a set of lines using Ctrl+/."""

    def __init__(self, prefix='# '):

        super(CommentsMode, self).__init__()
        self.prefix = prefix
        self.action = QAction(_("Comment/Uncomment"), self.editor)
        self.action.setShortcut("Ctrl+/")
        icon = icons.icon(qta_name='fa.comment')
        if icon:
            self.action.setIcon(icon)

    def on_state_changed(self, state):

        if state:
            self.action.triggered.connect(self.comment)
            self.editor.add_action(self.action, sub_menu='Advanced')
            if 'pyqt5' in os.environ['QT_API'].lower():
                self.editor.key_pressed.connect(self.on_key_pressed)
        else:
            self.editor.remove_action(self.action, sub_menu='Advanced')
            self.action.triggered.disconnect(self.comment)
            if 'pyqt5' in os.environ['QT_API'].lower():
                self.editor.key_pressed.disconnect(self.on_key_pressed)

    def on_key_pressed(self, key_event):

        ctrl = (
                key_event.modifiers() & Qt.ControlModifier == Qt.ControlModifier
        )
        if key_event.key() == Qt.Key_Slash and ctrl:
            self.comment()
            key_event.accept()

    def comment(self):

        stripped_prefix = self.prefix.rstrip()
        cursor = self.editor.textCursor()
        selection_start = cursor.selectionStart()
        selection_end = cursor.selectionEnd()
        orig_pos = cursor.position()
        orig_pos_block_nr = cursor.blockNumber()
        orig_anchor = cursor.anchor()
        cursor.setPosition(orig_anchor)
        orig_anchor_block_nr = cursor.blockNumber()
        cursor.beginEditBlock()
        # Fully select all selected lines. If there was no selection, this
        # simply selects the current line.
        cursor.setPosition(selection_start)
        cursor.movePosition(cursor.StartOfBlock)
        cursor.setPosition(selection_end, cursor.KeepAnchor)
        cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
        # First get the maximum common indentation level, and check if all
        # lines are commented. If not then we uncomment, otherwise we comment.
        indent_char = ' ' if self.editor.use_spaces_instead_of_tabs else '\t'
        max_common_indent = None
        comment_action = False
        selected_lines = cursor.selectedText().split(u'\u2029')
        for line in selected_lines:
            if not line.strip():  # Ignore empty lines
                continue
            stripped_line = line.lstrip(indent_char)
            indent = len(line) - len(stripped_line)
            max_common_indent = (
                indent if max_common_indent is None
                else min(indent, max_common_indent)
            )
            if not stripped_line.startswith(stripped_prefix):
                comment_action = True
        # Go through all lines and comment or uncomment them
        processed_lines = []
        for i, line in enumerate(selected_lines):
            if line.strip():  # Only change lines with content
                # Comment the line
                if comment_action:
                    line = line[:max_common_indent] + self.prefix + \
                           line[max_common_indent:]
                    # On the first line, both the anchor and the position
                    # need to be adjusted. On the next lines, either the
                    # anchor or the position need to be adjusted, depending
                    # on which one comes last.
                    if not i:
                        orig_pos += 2
                        orig_anchor += 2
                    elif orig_pos > orig_anchor:
                        orig_pos += 2
                    else:
                        orig_anchor += 2
                # Uncomment the line
                else:
                    # The prefix often ends with whitespace ('# '). But if a
                    # line is commented without whitespace ('#') then we still
                    # want to treat this as being commented.
                    to_strip = (
                        len(self.prefix)
                        if line[max_common_indent:].startswith(self.prefix)
                        else len(stripped_prefix)
                    )
                    line = line[:max_common_indent] + \
                           line[max_common_indent + to_strip:]
                    if not i:
                        orig_pos -= 2
                        orig_anchor -= 2
                    elif orig_pos > orig_anchor:
                        orig_pos -= 2
                    else:
                        orig_anchor -= 2
            processed_lines.append(line)
        cursor.insertText('\n'.join(processed_lines))
        # Make sure that poisitions fall within the text boundaries
        char_count = self.editor.document().characterCount()
        orig_anchor = min(max(orig_anchor, 0), char_count - 1)
        orig_pos = min(max(orig_pos, 0), char_count - 1)
        # Restore the anchor but make sure that it doesn't cross to another
        # block.
        cursor.setPosition(orig_anchor)
        if cursor.blockNumber() < orig_anchor_block_nr:
            cursor.movePosition(cursor.NextBlock)
        elif cursor.blockNumber() > orig_anchor_block_nr:
            cursor.movePosition(cursor.PreviousBlock)
            cursor.movePosition(cursor.EndOfBlock)
        # And the same for the position
        cursor.setPosition(orig_pos, cursor.KeepAnchor)
        if cursor.blockNumber() < orig_pos_block_nr:
            cursor.movePosition(cursor.NextBlock, cursor.KeepAnchor)
        elif cursor.blockNumber() > orig_pos_block_nr:
            cursor.movePosition(cursor.PreviousBlock, cursor.KeepAnchor)
            cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
