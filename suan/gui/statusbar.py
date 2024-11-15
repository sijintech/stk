from PySide6.QtWidgets import QStatusBar, QLabel

class Statusbar(QStatusBar):
    def __init__(self,parent):
        super().__init__()
        self.parent=parent
        self.parent.registerComponent('Statusbar',self,True)
        self.initUI()

    def initUI(self):
        label = QLabel("Status: Ready")
        self.addWidget(label)