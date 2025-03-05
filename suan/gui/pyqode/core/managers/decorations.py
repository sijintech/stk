"""
Contains the text decorations manager
"""
import logging
from pyqode.core.api.manager import Manager


def _logger():
    return logging.getLogger(__name__)


class TextDecorationsManager(Manager):
    """
    Manages the collection of TextDecoration that have been set on the editor
    widget.
    """

    def __init__(self, editor):
        super(TextDecorationsManager, self).__init__(editor)
        self._decorations = []
        self.editor.textChanged.connect(self._remove_decoration_around_cursor)

    def _remove_decoration_around_cursor(self):
        """Removes the decorations around the cursor. This is necessary when
        the text changes, because otherwise the decorations get dragged along
        with the cursor during typing.
        """
        cursor = self.editor.textCursor()
        to_remove = [
            d for d in self._decorations
            if d.contains_cursor(cursor, margin=1)
        ]
        for decoration in to_remove:
            self.remove(decoration)

    def append(self, decoration, set_on_editor=True):
        """
        Adds a text decoration on a CodeEdit instance

        :param decoration: Text decoration to add
        :type decoration: pyqode.core.api.TextDecoration
        """
        if decoration not in self._decorations:
            self._decorations.append(decoration)
            self._decorations = sorted(
                self._decorations, key=lambda sel: sel.draw_order)
            if set_on_editor:
                self.editor.setExtraSelections(self._decorations)
            return True
        return False

    def set_on_editor(self):
        """Sets the decorations on the editor. We don't do this after each
        decoration (but after each batch) to improve performance.
        """
        self.editor.setExtraSelections(self._decorations)

    def remove(self, decoration):
        """
        Removes a text decoration from the editor.

        :param decoration: Text decoration to remove
        :type decoration: pyqode.core.api.TextDecoration
        """
        try:
            self._decorations.remove(decoration)
            self.editor.setExtraSelections(self._decorations)
            return True
        except ValueError:
            return False

    def clear(self):
        """
        Removes all text decoration from the editor.

        """
        self._decorations[:] = []
        try:
            self.editor.setExtraSelections(self._decorations)
        except RuntimeError:
            pass

    def __iter__(self):
        return iter(self._decorations)

    def __len__(self):
        return len(self._decorations)
