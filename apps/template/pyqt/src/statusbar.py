from PySide6.QtWidgets import QStatusBar, QLabel

class Statusbar(QStatusBar):
    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):
        label = QLabel("Status: Ready")
        self.addWidget(label)