from PySide6.QtWidgets import (
    QTextEdit,
    QWidget,
    QVBoxLayout,
    QTabWidget,
)

from custom_logger import CustomLogger
from Tab.terminal.terminal import Terminal


class InfoBar(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.logger = CustomLogger()
        self.parent = parent
        self.tabWidget = QTabWidget()
        self.parent.registerComponent("Info", self, True)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)
        self.addInfoTabs()

    def initWorkspace(self):

        pass

    def addInfoTabs(self):

        self.logTab = QTextEdit()
        self.tabWidget.addTab(self.logTab, "Log")
        self.registerComponent("Log Tab", self.logTab)

        self.consoleTab = Terminal()
        self.tabWidget.addTab(self.consoleTab, "Terminal")
        self.registerComponent("Terminal Tab", self.consoleTab)

        self.statusTab = QTextEdit()
        self.tabWidget.addTab(self.statusTab, "Status Information")
        self.registerComponent("Status Information", self.statusTab)

    def registerComponent(self, path, component):
        truePath = "Info/" + path
        self.parent.registerComponent(truePath, component, True)

    def toggleComponentVisibility(self, tabName):
        tab = self.parent.components["main"]["children"]["Info"]["children"][tabName]
        tab["isVisible"] = not tab["isVisible"]
        for i in range(self.tabWidget.count()):
            if self.tabWidget.tabText(i) == tabName[: -len(" Tab")]:
                self.tabWidget.removeTab(i)
                self.logger.debug("删除" + tabName)
                return

        component = tab["component"]
        self.tabWidget.addTab(component, tabName[: -len(" Tab")])

