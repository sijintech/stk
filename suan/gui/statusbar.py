from PySide6.QtWidgets import QStatusBar, QLabel
from custom_logger import CustomLogger
class Statusbar(QStatusBar):
    def __init__(self,parent):
        super().__init__()
        self.logger = CustomLogger()
        self.parent = parent
        self.initUI()
        self.parent.registerComponent('Statusbar', self, True)

    def initUI(self):
        label = QLabel("Status: Ready")
        self.addWidget(label)