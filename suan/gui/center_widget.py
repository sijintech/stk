import matplotlib.pyplot as plt
import vtk
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTabWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from custom_logger import CustomLogger
from Tab.code_tab import CodeTab
from Tab.data_table_tab import DataTableTab
from Tab.preference_tab import PreferenceTab
from Tab.ai import AIChatTab


class CustomFigureCanvas(FigureCanvasQTAgg):
    def __init__(self, figure=None):
        super().__init__(figure)
        self.logger = CustomLogger()
        self._figure = None  # 用于保存 Figure 对象的成员变量

    def setFigure(self, fig):

        self.figure.clf()

        self._figure = fig

        self.__init__(fig)

    def getFigure(self):
        return self._figure


class CenterWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.logger = CustomLogger()
        self.runCodeType = None
        self.runCode = None
        self.parent = parent
        self.parent.registerComponent("Visualization window", self, True)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.tabWidget = QTabWidget()

        self.tabWidget.setTabsClosable(True)
        self.tabWidget.tabCloseRequested.connect(self.close_tab)
        self.tabWidget.setMovable(True)
        self.tabWidget.setTabBarAutoHide(False)
        layout.addWidget(self.tabWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.addMainOperationTabs()


        self.tabWidget.currentChanged.connect(self.onTabChanged)

    def initWorkspace(self):

        try:
            active_tab_index = self.parent.get_workspace_data(
                "center_widget/active_tab_index", 0
            )

            if active_tab_index >= 0 and active_tab_index < self.tabWidget.count():
                self.tabWidget.setCurrentIndex(active_tab_index)
            else:
                self.tabWidget.setCurrentIndex(0)
        except Exception as e:
            self.logger.error(f"初始化工作区标签失败: {e}")
            self.tabWidget.setCurrentIndex(0)

    def close_tab(self, index):
        tabName = self.tabWidget.tabText(index) + " Tab"
        tab = self.parent.components["main"]["children"]["Visualization window"][
            "children"
        ][tabName]
        tab["isVisible"] = not tab["isVisible"]
        self.tabWidget.removeTab(index)

    def closeEvent(self, QCloseEvent):
        super().closeEvent(QCloseEvent)
        self.vtkWidget.Finalize()

    def registerComponent(self, path, component, isVisible):
        truePath = "Visualization window/" + path
        self.parent.registerComponent(truePath, component, isVisible)

    def unregisterComponent(self, path):
        truePath = "Visualization window/" + path
        self.parent.unregisterComponent(truePath)

    def toggleComponentVisibility(self, tabName):
        tab = self.parent.components["main"]["children"]["Visualization window"][
            "children"
        ][tabName]
        tab["isVisible"] = not tab["isVisible"]
        for i in range(self.tabWidget.count()):
            if self.tabWidget.tabText(i) == tabName[: -len(" Tab")]:
                self.tabWidget.removeTab(i)
                self.logger.debug("删除" + tabName)
                return

        component = tab["component"]
        self.tabWidget.addTab(component, tabName[: -len(" Tab")])

    def addMainOperationTabs(self):

        self.codeTab = CodeTab(self)
        self.tabWidget.addTab(self.codeTab, "Code")
        self.registerComponent("Code Tab", self.codeTab, True)

        self.aiChatTab = AIChatTab(self)
        self.tabWidget.addTab(self.aiChatTab, "AI")
        self.registerComponent("AI Tab", self.aiChatTab, True)

        self.aiChatTab.modelConfigChanged.connect(self.onAIModelConfigChanged)

        self.vtkWidget = QVTKRenderWindowInteractor()  # 创建VTK渲染窗口交互器
        self.vtkWidget.Initialize()

        self.vtkVisualizationTab = QWidget()
        vtkLayout = QVBoxLayout()
        vtkLayout.addWidget(self.vtkWidget)
        self.vtkVisualizationTab.setLayout(vtkLayout)
        self.tabWidget.addTab(self.vtkVisualizationTab, "VTK Visualization")
        self.registerComponent("VTK Visualization Tab", self.vtkVisualizationTab, True)

        self.matplotlibWidget = CustomFigureCanvas()  # 创建画布控件
        self.matplotlibDisplayTab = QWidget()
        self.matplotlibLayout = QVBoxLayout()
        self.matplotlibLayout.addWidget(self.matplotlibWidget)
        self.matplotlibDisplayTab.setLayout(self.matplotlibLayout)
        self.tabWidget.addTab(self.matplotlibDisplayTab, "Matplotlib Display")
        self.registerComponent(
            "Matplotlib Display Tab", self.matplotlibDisplayTab, True
        )

        self.dataTableTab = DataTableTab({}, 4)
        self.tabWidget.addTab(self.dataTableTab, "Data Table")
        self.registerComponent("Data Table Tab", self.dataTableTab, True)

    def onAIModelConfigChanged(self):
        """处理AI模型配置变更"""
        self.logger.debug("AI模型配置已更改")

    def addPreferenceTab(self, data):

        self.unregisterComponent("Preference Tab")
        self.preferenceTab = PreferenceTab(data, self.parent)
        self.tabWidget.addTab(self.preferenceTab, "Preference")
        self.registerComponent("Preference Tab", self.preferenceTab, True)
        preferenceTabIndex = self.tabWidget.indexOf(self.preferenceTab)
        self.tabWidget.setCurrentIndex(preferenceTabIndex)

    def runCodeWithAnalysis(self, runCode, runCodeType, need_variable):
        self.runCode = runCode
        self.runCodeType = runCodeType
        script_path = self.parent.curWorkFile
        if self.runCodeType == "vtk":
            local_vars = {}
            global_vars = {"vtk": vtk}
            self.parent.get_component_by_name("Code Tab").execute_code_with_file_path(
                self.runCode, script_path, global_vars, local_vars
            )
            renderer = local_vars.get(need_variable)
            if renderer:
                self.updateVTKVisualization(renderer)
        if self.runCodeType == "matplotlib":
            local_vars = {}
            global_vars = {"plt": plt}
            self.parent.get_component_by_name("Code Tab").execute_code_with_file_path(
                self.runCode, script_path, global_vars, local_vars
            )

            fig = local_vars.get(need_variable)
            if fig:
                self.updateMatplotlibDisplay(fig)

    def clearLayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            layout.removeWidget(widget)
            if widget is not None:
                widget.deleteLater()

    def updateVTKVisualization(self, vtkObject):

        self.vtkObject = vtkObject
        self.vtkWidget.GetRenderWindow().AddRenderer(
            vtkObject
        )  # 将渲染器添加到渲染窗口
        self.vtkWidget.GetRenderWindow().Render()  # 渲染一次

        vtkVisualizationIndex = self.tabWidget.indexOf(self.vtkVisualizationTab)
        self.tabWidget.setCurrentIndex(vtkVisualizationIndex)

    def updateMatplotlibDisplay(self, fig):

        self.matplotlibWidget = CustomFigureCanvas(fig)
        self.clearLayout(self.matplotlibLayout)
        self.matplotlibLayout.addWidget(self.matplotlibWidget)

        matplotlibDisplayIndex = self.tabWidget.indexOf(self.matplotlibDisplayTab)
        self.tabWidget.setCurrentIndex(matplotlibDisplayIndex)

    def updateDataTable(self, data):

        self.dataTableTab.populateTable(data, 4)
        dataTableIndex = self.tabWidget.indexOf(self.dataTableTab)
        self.tabWidget.setCurrentIndex(dataTableIndex)

    def onTabChanged(self, index):
        """选项卡切换事件处理"""
        if index < 0 or index >= self.tabWidget.count():
            return

        code_tab = self.parent.get_component_by_name("Code Tab")
        if code_tab:
            code_tab.save_if_auto()

        tab_name = self.tabWidget.tabText(index)
        self.logger.debug(f"切换到选项卡: {tab_name}")

        if tab_name == "AI" and hasattr(self, "aiChatTab"):

            if not self.aiChatTab.client:
                self.logger.debug("AI对话选项卡需要连接到模型")

                from PySide6.QtCore import QTimer

                QTimer.singleShot(100, self.aiChatTab.connectToModel)

    def switchToAIChat(self):
        """切换到AI对话选项卡"""
        for i in range(self.tabWidget.count()):
            if self.tabWidget.tabText(i) == "AI":
                self.tabWidget.setCurrentIndex(i)
                return True

        if (
            "AI Tab"
            in self.parent.components["main"]["children"]["Visualization window"][
                "children"
            ]
        ):
            self.toggleComponentVisibility("AI Tab")
            return self.switchToAIChat()  # 递归调用一次

        return False

    def activateAIChatTab(self):
        """激活AI对话选项卡并确保它可见"""
        result = self.switchToAIChat()
        if result:
            self.logger.debug("已切换到AI对话选项卡")

            if hasattr(self.aiChatTab, "inputField"):
                self.aiChatTab.inputField.setFocus()
        return result
