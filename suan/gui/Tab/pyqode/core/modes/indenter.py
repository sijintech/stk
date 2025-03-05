# -*- coding: utf-8 -*-
"""
Contains the default indenter.
"""
from pyqode.core.api.mode import Mode


class IndenterMode(Mode):
    """ Implements classic indentation/tabulation (Tab/Shift+Tab)

    It inserts/removes tabulations (a series of spaces defined by the
    tabLength settings) at the cursor position if there is no selection,
    otherwise it fully indents/un-indents selected lines. If the
    tab_always_indents property is set to True, then tab always indents, even
    if there is no selection.

    To trigger an indentation/un-indentation programatically, you must emit
    :attr:`pyqode.core.api.CodeEdit.indent_requested` or
    :attr:`pyqode.core.api.CodeEdit.unindent_requested`.
    """

    def __init__(self):
        self.tab_always_indents = False
        super(IndenterMode, self).__init__()

    @property
    def _indent_char(self):
        if self.editor.use_spaces_instead_of_tabs:
            return ' '
        return '\t'

    @property
    def _single_indent(self):
        if self.editor.use_spaces_instead_of_tabs:
            return self.editor.tab_length * ' '
        return '\t'

    @property
    def _indent_width(self):
        if self.editor.use_spaces_instead_of_tabs:
            return self.editor.tab_length
        return 1

    def on_state_changed(self, state):
        if state:
            self.editor.indent_requested.connect(self.indent)
            self.editor.unindent_requested.connect(self.unindent)
        else:
            self.editor.indent_requested.disconnect(self.indent)
            self.editor.unindent_requested.disconnect(self.unindent)

    def _select_full_block(self, cursor, anchor, pos):
        """Selects full blocks of text from the first character of the first
        block until the last character of the last block, while keeping the
        order of the position and anchor constant. Returns the new anchor,
        new position, and a list of selected lines.
        """
        cursor.setPosition(anchor)
        if pos > anchor:
            cursor.movePosition(cursor.StartOfBlock)
            cursor.setPosition(pos, cursor.KeepAnchor)
            cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
        else:
            cursor.movePosition(cursor.EndOfBlock)
            cursor.setPosition(pos, cursor.KeepAnchor)
            cursor.movePosition(cursor.StartOfBlock, cursor.KeepAnchor)
        return (
            cursor.anchor(),
            cursor.position(),
            cursor.selectedText().split(u'\u2029')
        )

    def _max_common_indent(self, lines):
        """Gets the maximum indentation level that is common to all non-empty
        lines.
        """
        max_common_indent = None
        for line in lines:
            if not line.strip():  # Ignore empty lines
                continue
            stripped_line = line.lstrip(self._indent_char)
            indent = len(line) - len(stripped_line)
            max_common_indent = (
                indent if max_common_indent is None
                else min(indent, max_common_indent)
            )
        return max_common_indent if max_common_indent is not None else 0

    def _restore_selection(self, cursor, selection, orig_anchor, orig_pos):
        """Restores a selection based taking into account the order of the
        original anchor and position, and the length of the new selection.
        """
        if orig_anchor > orig_pos:
            cursor.setPosition(orig_pos + len(selection))
            cursor.movePosition(
                cursor.Left,
                cursor.KeepAnchor,
                n=len(selection)
            )
        else:
            cursor.setPosition(orig_anchor)
            cursor.movePosition(
                cursor.Right,
                cursor.KeepAnchor,
                n=len(selection)
            )

    def indent(self):
        cursor = self.editor.textCursor()
        orig_anchor = cursor.anchor()
        orig_pos = cursor.position()
        indent_width = self._indent_width
        indent_char = self._indent_char
        # If there is no selection, and there is non-whitespace before the
        # cursor on the current block, then we simply insert the tab at the
        # cursor position.
        if not self.tab_always_indents and not cursor.hasSelection():
            cursor.movePosition(cursor.StartOfBlock, cursor.KeepAnchor)
            if cursor.selectedText().strip(indent_char):
                cursor.setPosition(orig_pos)
                cursor.insertText(self._single_indent)
                self.editor.setTextCursor(cursor)
                return
        cursor.beginEditBlock()
        # Select from the start of the first block until the end of the last
        # block.
        sel_anchor, sel_pos, lines = self._select_full_block(
            cursor,
            orig_anchor,
            orig_pos
        )
        # Indent to the next tab stop and replace the selection
        max_common_indent = self._max_common_indent(lines)
        indent_width = indent_width - (max_common_indent % indent_width)
        lines = [indent_char * indent_width + line for line in lines]
        new_selection = '\n'.join(lines)
        cursor.insertText(new_selection)
        if orig_anchor == orig_pos:
            cursor.setPosition(orig_pos + indent_width)
        else:
            self._restore_selection(
                cursor,
                new_selection,
                sel_anchor,
                sel_pos
            )
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def unindent(self):
        cursor = self.editor.textCursor()
        orig_anchor = cursor.anchor()
        orig_pos = cursor.position()
        orig_pos_in_block = cursor.positionInBlock()
        indent_width = self._indent_width
        indent_char = self._indent_char
        cursor.beginEditBlock()
        # Select from the start of the first block until the end of the last
        # block.
        sel_anchor, sel_pos, lines = self._select_full_block(
            cursor,
            orig_anchor,
            orig_pos
        )
        # De-indent to the previous tab stop and replace the selection
        max_common_indent = self._max_common_indent(lines)
        deindent_width = max_common_indent % indent_width
        if not deindent_width and max_common_indent >= indent_width:
            deindent_width = indent_width
        lines = [line[deindent_width:] for line in lines]
        new_selection = '\n'.join(lines)
        cursor.insertText(new_selection)
        # If there was no selection, restore the cursor position. Move the
        # cursor to the left to compensate for the deindentation, but don't
        # wrap to the previous line.
        if orig_anchor == orig_pos:
            cursor.setPosition(
                orig_pos - min(orig_pos_in_block, deindent_width)
            )
        else:
            self._restore_selection(
                cursor,
                new_selection,
                sel_anchor,
                sel_pos
            )
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
