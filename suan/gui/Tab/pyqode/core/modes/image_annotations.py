# -*- coding: utf-8 -*-
"""
This module contains the image annotations mode. This mode allows annotations
to be sent to the backend, and adds annotations as user data to text blocks.
The annotations are shown in the ImageAnnotationsPanel.
"""
from qtpy import QtGui, QtCore, QtWidgets
from pyqode.core.modes import CheckerMode
from pyqode.core.backend.workers import (
    image_annotations,
    set_image_annotations
)

TOOLTIP = '<img style="background-color:white;" src="{}" />'


class ImageAnnotationWidget(QtWidgets.QWidget):

    def __init__(self, parent, path):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.SubWindow | QtCore.Qt.FramelessWindowHint)
        self.setWindowTitle('Image preview')
        label = QtWidgets.QLabel()
        label.setPixmap(QtGui.QPixmap(path))
        vbox = QtWidgets.QVBoxLayout(self)
        vbox.addWidget(label)
        self.setLayout(vbox)
        self.setPalette(parent.palette())


class ImageAnnotationsMode(CheckerMode):
    annotation_clicked = QtCore.Signal(object, object)

    def __init__(self, annotations={}):
        CheckerMode.__init__(self, image_annotations, underline=False)

    def set_annotations(self, annotations):
        self.editor.backend.send_request(set_image_annotations, annotations)
        self.request_analysis()

    def message_icon(self, msg):
        return QtGui.QIcon(msg.path)

    def message_widget(self, msg):
        return ImageAnnotationWidget(self.editor, msg.path)

    def show_on_panel(self, panel):
        return panel.__class__.__name__ == 'ImageAnnotationsPanel'

    def message_clicked(self, msg, event):
        self.annotation_clicked.emit(msg, event)
