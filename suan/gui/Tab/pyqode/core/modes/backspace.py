"""
This module contains the smart backspace mode
"""
from qtpy.QtCore import Qt
from pyqode.core.api import Mode


class SmartBackSpaceMode(Mode):
    """Improves backspace and delete behaviour. The exact behavior is intended
    to be as intuitive as possible, but is quite complex and described in more
    detail in the functions below.
    """

    def on_state_changed(self, state):
        if state:
            self.editor.key_pressed.connect(self._on_key_pressed)
        else:
            self.editor.key_pressed.disconnect(self._on_key_pressed)

    def _on_key_pressed(self, event):
        if (event.modifiers() != Qt.NoModifier or event.isAccepted()):
            return
        key = event.key()
        if key == Qt.Key_Backspace:
            do_backspace = True
            do_delete = False
        elif key == Qt.Key_Delete:
            do_delete = True
            do_backspace = False
        else:
            return
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            cursor.removeSelectedText()
        elif do_backspace:
            if cursor.atBlockStart():
                self._do_backspace_at_block_start(cursor)
            else:
                self._do_regular_backspace(cursor)
        else:
            if cursor.atBlockEnd():
                self._do_delete_at_block_end(cursor)
            else:
                self._do_regular_delete(cursor)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        event.accept()

    def _do_delete_at_block_end(self, cursor):
        """When deleting while the cursor is at the end of a block, the next
        newline and all subsequent whitespace is deleted.
        """
        cursor.deleteChar()
        while not cursor.atBlockEnd():
            cursor.movePosition(cursor.Right, cursor.KeepAnchor)
            if not cursor.selectedText().isspace():
                cursor.movePosition(cursor.Left)
                break
            cursor.removeSelectedText()

    def _do_regular_delete(self, cursor):

        """A delete does different things depending on the context.
        
        1. If the cursor is in the trailing whitespace of a block, then all
        trailing whitespace is removed.
        
            `x = 1|    ` -> `x = 1|`
            
        2. If the cursor is followed by whitespace, then what follows is
        de-indented by one tab stop, or until the cursor position is reached.
        
            `|    x = 1`     -> `|x = 1`
            ` |   x = 1`     -> ` |x = 1`
            ` |       x = 1` -> ` |  x = 1`
            ` |     x = 1` ->   ` |  x = 1`
            ` |  x = 1`      -> ` |x = 1`
            
        3. Else, the next character is deleted:
        
            `|x = 1` -> ` = 1`
        """

        orig_pos = cursor.position()
        selected_text, selected_whitespace, selected_entire_block = \
            self._select_until_block_end(cursor)
        if selected_whitespace:
            cursor.removeSelectedText()
            return
        cursor.setPosition(orig_pos)
        # For tab-based indentation, no specific de-indenting logic is
        # necessary.
        if not self.editor.use_spaces_instead_of_tabs:
            cursor.deleteChar()
            return
        new_pos = self._move_right_until_non_whitespace(cursor)
        # If there was no whitespace after, simply delete the next character
        if orig_pos == new_pos:
            cursor.setPosition(orig_pos)
            cursor.deleteChar()
        # Determine the maximum number of characters to delete
        n_del = cursor.positionInBlock() % self.editor.tab_length
        if not n_del:
            n_del = self.editor.tab_length
        n_del = min(new_pos - orig_pos, n_del)  # don't delete beyond cursor
        cursor.movePosition(cursor.Left, cursor.KeepAnchor, n=n_del)
        cursor.removeSelectedText()
        cursor.setPosition(orig_pos)

    def _do_backspace_at_block_start(self, cursor):
        """When backspacing at the start of a block, first delete the previous
        character, which is the newline that takes the cursor to the previous
        block. If the cursor was initially at a line of only whitespace, we
        delete the whitespace so that it's not carried over to the previous
        block.
        """
        if cursor.block().text().isspace():
            cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
            cursor.removeSelectedText()
        cursor.deletePreviousChar()

    def _do_regular_backspace(self, cursor):
        """A backspace does different things depending on the context.
        
        If the cursor is in the trailing white space of a block that is not
        only whitespace, then all trailing whitespace is deleted.
        
            `x = 1   |   ` -> `x = 1|`
        
        Otherwise, we deindent to the previous tab stop, or until the first non
        whitespace character, while deleting at least one character even if it
        is non whitespace.
        
            `x = 1|` -> `x = |`
            `y = 1;     |x = 1` -> `y = 1;  x = 1`
            
        If the block is only whitespace, then the trailing whitespace is also
        deleted:
        
            `    |    ` -> `|`
        """
        orig_pos = cursor.position()
        self._move_left_until_non_whitespace(cursor)
        selected_text, selected_whitespace, selected_entire_block = \
            self._select_until_block_end(cursor)
        # If we've selected some whitespace, delete this selection. But not
        # if the entire line is whitespace, because then we want
        # to de-indent.
        if selected_whitespace and not selected_entire_block:
            cursor.removeSelectedText()
        # Otherwise, return the cursor to its original position and
        # fall back to a de-indent-like behavior, such that as many
        # whitespaces are removed as are necessary to de-indent by one
        # level.
        else:
            cursor.setPosition(orig_pos)
            # If there's only whitespace on the line, we also remove the
            # trailing whitespace.
            if selected_whitespace:
                cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
                cursor.removeSelectedText()
            if self.editor.use_spaces_instead_of_tabs:
                cursor_pos = cursor.positionInBlock()
                n_del = cursor_pos % self.editor.tab_length
                ch_del = ' '
                if not n_del:
                    n_del = self.editor.tab_length
                if n_del > cursor_pos:  # Don't delete beyond the line
                    n_del = cursor_pos
            else:
                n_del = 1
                ch_del = '\t'
            for i in range(n_del):
                cursor.movePosition(
                    cursor.PreviousCharacter,
                    cursor.KeepAnchor
                )
                if cursor.selectedText() == ch_del:
                    cursor.removeSelectedText()
                # The first time, we also delete non-whitespace characters.
                # However, this means that we are not de-indenting, and
                # therefore we break out of the loop. In other words, this
                # is a regular backspace.
                else:
                    if not i:
                        cursor.removeSelectedText()
                    else:
                        cursor.clearSelection()
                        cursor.movePosition(cursor.Right)
                    break

    def _move_left_until_non_whitespace(self, cursor):
        """Moves the cursor left until the first non-whitespace character
        or until the start of the block.
        """
        while not cursor.atBlockStart():
            cursor.movePosition(
                cursor.Left,
                cursor.KeepAnchor
            )
            if not cursor.selectedText().isspace():
                cursor.setPosition(cursor.position() + 1)
                break
        cursor.setPosition(cursor.position())
        return cursor.position()

    def _move_right_until_non_whitespace(self, cursor):
        """Moves the cursor right until the first non-whitespace character
        or until the end of the block.
        """
        while not cursor.atBlockEnd():
            cursor.movePosition(
                cursor.Right,
                cursor.KeepAnchor
            )
            if not cursor.selectedText().isspace():
                cursor.setPosition(cursor.position() - 1)
                break
        cursor.setPosition(cursor.position())
        return cursor.position()

    def _select_until_block_end(self, cursor):
        """Select all the characters until the end of the block. Returns the
        selected text, whether this text contains only whitespace (and is not)
        empty, and whether this text corresponds to the entire block
        """
        cursor.movePosition(cursor.EndOfBlock, cursor.KeepAnchor)
        selected_text = cursor.selectedText()
        return (
            selected_text,
            selected_text.isspace() and selected_text,
            cursor.block().text() == selected_text
        )
