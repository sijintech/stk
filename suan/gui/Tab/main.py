import logging
import os

os.environ['FORCE_QT_API'] = 'PySide6'

os.environ['QT_API'] = 'pyside6'
logging.basicConfig(level=logging.DEBUG)
import sys

# os.chdir("./")  # 设置项目路径
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from pyqode1.core import api
from pyqode1.core import modes
from pyqode1.core import panels
# from pyqode.qt import QtCore, QtGui, QtWidgets

# print(QtCore.QEvent)
# print(QtGui.QPainter)
# print(QtWidgets)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QStatusBar,
    QLabel,
    QMessageBox,
)


def main():
    app = QApplication(sys.argv)

    # create editor and window
    window = QMainWindow()
    editor = api.CodeEdit()
    window.setCentralWidget(editor)

    def handle_error(error):
        print(f"进程发生错误：{error}")

    # start the backend as soon as possible
    script_path= os.path.abspath(os.path.join(os.path.dirname(__file__), 'code_server.py'))
    print(script_path)
    editor.backend.start(script=script_path, error_callback=handle_error)

    # append some modes and panels
    editor.modes.append(modes.CodeCompletionMode())
    editor.modes.append(modes.CaretLineHighlighterMode())
    editor.modes.append(modes.PygmentsSyntaxHighlighter(editor.document()))
    editor.panels.append(panels.SearchAndReplacePanel(),
                         api.Panel.Position.BOTTOM)

    # open a file
    editor.file.open(__file__, encoding='utf-8', use_cached_encoding=False)

    # run
    window.show()
    app.exec_()
    editor.file.close()


if __name__ == "__main__":
    main()

