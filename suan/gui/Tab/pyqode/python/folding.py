"""
This module contains the python code fold detector.
"""
import re
from pyqode.core.api import IndentFoldDetector, TextBlockHelper


class PythonFoldDetector(IndentFoldDetector):
    """
    Python specific fold detector.

    Python is an indent based language so we use indentation for detecting
    the outline but we discard regions with higher indentation if they do not
    follow a trailing ':'. That way, only the real logical blocks are
    displayed.

    We also add some trickery to make import regions and docstring appear with
    an higher fold level than they should be (in order to make them foldable).
    """
    #: regex which identifies a single line docstring
    _single_line_docstring = re.compile(r'""".*"""')

    def _strip_comments(self, prev_block):
        txt = prev_block.text().strip() if prev_block else ''
        if txt.find('#') != -1:
            txt = txt[:txt.find('#')].strip()
        return txt

    def _handle_docstrings(self, block, lvl, prev_block):
        # Increase the block level for all except the first block of a
        # docstring.
        if (
                block.docstring and
                prev_block in self.editor.syntax_highlighter.docstrings
        ):
            return lvl + 1
        return lvl

    def _handle_imports(self, block, lvl, prev_block):
        txt = block.text()
        indent = len(txt) - len(txt.lstrip())
        if (hasattr(block, 'import_stmt') and prev_block and
                'import ' in prev_block.text() and indent == 0):
            return 1
        return lvl

    def detect_fold_level(self, prev_block, block):
        """
        Perfoms fold level detection for current block (take previous block
        into account).

        :param prev_block: previous block, None if `block` is the first block.
        :param block: block to analyse.
        :return: block fold level
        """
        # Python is an indent based language so use indentation for folding
        # makes sense but we restrict new regions to indentation after a ':',
        # that way only the real logical blocks are displayed.
        lvl = super(PythonFoldDetector, self).detect_fold_level(
            prev_block, block)
        # cancel false indentation, indentation can only happen if there is
        # ':' on the previous line
        prev_lvl = TextBlockHelper.get_fold_lvl(prev_block)
        if prev_block and lvl > prev_lvl and not (
                self._strip_comments(prev_block).endswith(':')):
            lvl = prev_lvl
        lvl = self._handle_docstrings(block, lvl, prev_block)
        lvl = self._handle_imports(block, lvl, prev_block)
        return lvl

    def _three_quotes(self, block):

        return "'''" in block or '"""' in block

    def require_rehighlight(self, from_block, to_block):

        if from_block is None or to_block is None:
            return
        # A highlight is required when a block is changed such that it now has
        # three quotes, or now no longer has three quotes. Because this changes
        # the docstring status of the block, which can affect the folding
        # structure of the entire document.
        nr1, txt1 = from_block
        nr2, txt2 = to_block
        return (
                nr1 == nr2 and
                self._three_quotes(txt1) != self._three_quotes(txt2)
        )
