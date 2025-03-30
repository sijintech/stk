"""
Provides QtGui classes for compatibility across Qt bindings.
"""
import os
from pyqode.qt import QT_API
from pyqode.qt import PYQT5_API
from pyqode.qt import PYQT4_API
from pyqode.qt import PYSIDE_API

# 确保使用PySide6
os.environ[QT_API] = 'pyside6'

if os.environ[QT_API] in PYQT5_API:
    from PyQt5.QtGui import *
elif os.environ[QT_API] in PYQT4_API:
    from PyQt4.QtGui import *
elif os.environ[QT_API] in PYSIDE_API:
    from PySide6.QtGui import *
