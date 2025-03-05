# -*- coding: utf-8 -*-
"""
This module contains the spell checker mode
"""
from qtpy import QtWidgets
from pyqode.core.modes import CheckerMode

WARNING = 1
WORD_PATTERN = r'(?P<word>\w\w\w+)'


def run_spellcheck(request_data):
    import re
    import string

    global sc
    try:
        sc
    except NameError:
        print('initializing spellchecker')
        import spellchecker
        sc = spellchecker.SpellChecker(request_data.get('language', 'en'))
    ignore = request_data.get('ignore', [])
    messages = []
    code = request_data['code']
    for group in re.finditer(WORD_PATTERN, code):
        # Strip off starting and trailing underscores. This could probably
        # be included in the regular expression, but this is easier.
        word = group.group('word')
        end = group.end()
        if word.startswith('__'):
            word = word[2:]
        if word.endswith('__'):
            word = word[:-2]
            end -= 2
        # Ignore words that start with a digit, that are in the ignore list, or
        # that are part of the dictionary
        if (
                word[0] in string.digits or
                word in ignore or
                not sc.unknown([word])
        ):
            continue
        # Convert the position to a line number and a start and end position
        # in the line.
        line_nr = code[:end].count('\n')
        line_pos = code[:end].rfind('\n') + 1
        messages.append((
            '[spellcheck] {}'.format(word),
            WARNING,
            line_nr,
            (end - len(word) - line_pos, end - line_pos)
        ))
    return messages


class SpellCheckerMode(CheckerMode):

    def __init__(self):
        super(SpellCheckerMode, self).__init__(
            run_spellcheck,
            delay=1000,
            show_tooltip=False
        )
