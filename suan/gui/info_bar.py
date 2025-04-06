from PySide6.QtWidgets import (
    QTextEdit,
    QWidget,
    QVBoxLayout,
    QTabWidget,
)


from custom_logger import CustomLogger
# 移除 CodeTab 导入
# from Tab.code_tab import CodeTab


class InfoBar(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.logger = CustomLogger()
        self.parent = parent
        self.tabWidget = QTabWidget()
        self.parent.registerComponent("Info", self, True)
        # 移除 codeTab 和 curShowCode 属性
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)
        self.addInfoTabs()

    def initWorkspace(self):
        # 由于移除了codeTab，修改workspace初始化逻辑
        pass

    def addInfoTabs(self):
        # 移除 codeTab 初始化和添加

        self.logTab = QTextEdit()
        self.tabWidget.addTab(self.logTab, "Log")
        self.registerComponent("Log Tab", self.logTab)

        self.consoleTab = QTextEdit()
        self.tabWidget.addTab(self.consoleTab, "Console")
        self.registerComponent("Console Tab", self.consoleTab)

        self.statusTab = QTextEdit()
        self.tabWidget.addTab(self.statusTab, "Status Information")
        self.registerComponent("Status Information", self.statusTab)

    # 移除 runCodeWithAnalysis 方法，因为它与 codeTab 相关
    # def runCodeWithAnalysis(self):
    #    if self.curShowCode:
    #        self.codeTab.executeCode(self.curShowCode)
    #    else:
    #        self.logger.warning("没有代码可执行")

    def registerComponent(self, path, component):
        truePath = "Info/" + path
        self.parent.registerComponent(truePath, component, True)

    def toggleComponentVisibility(self, tabName):
        tab = self.parent.components["main"]["children"]["Info"]["children"][tabName]
        tab["isVisible"] = not tab["isVisible"]
        for i in range(self.tabWidget.count()):
            if self.tabWidget.tabText(i) == tabName[: -len(" Tab")]:
                # 如果选项卡已存在，则删除它
                self.tabWidget.removeTab(i)
                self.logger.debug("删除" + tabName)
                return
        # 如果选项卡不存在，则添加它
        component = tab["component"]
        self.tabWidget.addTab(component, tabName[: -len(" Tab")])

