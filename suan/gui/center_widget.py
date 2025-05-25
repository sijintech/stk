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
        # 清除当前画布上的所有内容
        self.figure.clf()
        # 关联新的 Figure 对象
        self._figure = fig
        # 重新构造 FigureCanvasQTAgg 对象并关联新的 Figure 对象
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

        # 设置自定义 TabBar
        # self.tabWidget.setTabBar(CustomTabBar())

        self.tabWidget.setTabsClosable(True)
        self.tabWidget.tabCloseRequested.connect(self.close_tab)
        self.tabWidget.setMovable(True)
        self.tabWidget.setTabBarAutoHide(False)
        layout.addWidget(self.tabWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.addMainOperationTabs()

        # 设置信号连接
        self.tabWidget.currentChanged.connect(self.onTabChanged)

    def initWorkspace(self):
        # 获取工作区中的活动标签索引，如果不存在则默认为0
        try:
            active_tab_index = self.parent.get_workspace_data(
                "center_widget/active_tab_index", 0
            )
            # 确保索引有效
            if active_tab_index >= 0 and active_tab_index < self.tabWidget.count():
                self.tabWidget.setCurrentIndex(active_tab_index)
            else:
                self.tabWidget.setCurrentIndex(0)
        except Exception as e:
            self.logger.error(f"初始化工作区标签失败: {e}")
            self.tabWidget.setCurrentIndex(0)
        # self.vtkObject=self.parent.get_workspaceData('center_widget/vtk/view_port')
        # self.vtkWidget.GetRenderWindow().AddRenderer(
        #     self.vtkObject
        # )

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
                # 如果选项卡已存在，则删除它
                self.tabWidget.removeTab(i)
                self.logger.debug("删除" + tabName)
                return
        # 如果选项卡不存在，则添加它
        component = tab["component"]
        self.tabWidget.addTab(component, tabName[: -len(" Tab")])

    def addMainOperationTabs(self):
        # codeTab
        self.codeTab = CodeTab(self)
        self.tabWidget.addTab(self.codeTab, "Code")
        self.registerComponent("Code Tab", self.codeTab, True)

        # AI Chat Tab
        self.aiChatTab = AIChatTab(self)
        self.tabWidget.addTab(self.aiChatTab, "AI")
        self.registerComponent("AI Tab", self.aiChatTab, True)
        # 连接AI模型配置变更信号
        self.aiChatTab.modelConfigChanged.connect(self.onAIModelConfigChanged)

        # vtkVisualizationTab
        self.vtkWidget = QVTKRenderWindowInteractor()  # 创建VTK渲染窗口交互器
        self.vtkWidget.Initialize()
        # self.vtkWidget.GetRenderWindow().AddRenderer(renderer)  # 将渲染器添加到渲染窗口
        # self.vtkWidget.GetRenderWindow().Render()  # 渲染一次
        self.vtkVisualizationTab = QWidget()
        vtkLayout = QVBoxLayout()
        vtkLayout.addWidget(self.vtkWidget)
        self.vtkVisualizationTab.setLayout(vtkLayout)
        self.tabWidget.addTab(self.vtkVisualizationTab, "VTK Visualization")
        self.registerComponent("VTK Visualization Tab", self.vtkVisualizationTab, True)

        #  matplotlibDisplayTab
        self.matplotlibWidget = CustomFigureCanvas()  # 创建画布控件
        self.matplotlibDisplayTab = QWidget()
        self.matplotlibLayout = QVBoxLayout()
        self.matplotlibLayout.addWidget(self.matplotlibWidget)
        self.matplotlibDisplayTab.setLayout(self.matplotlibLayout)
        self.tabWidget.addTab(self.matplotlibDisplayTab, "Matplotlib Display")
        self.registerComponent(
            "Matplotlib Display Tab", self.matplotlibDisplayTab, True
        )

        # dataTableTab
        self.dataTableTab = DataTableTab({}, 4)
        self.tabWidget.addTab(self.dataTableTab, "Data Table")
        self.registerComponent("Data Table Tab", self.dataTableTab, True)

        # preferenceTab
        # self.preferenceTab = PreferenceTab()
        # # self.tabWidget.addTab(self.preferenceTab, "Preference")
        # self.registerComponent("Preference Tab", self.preferenceTab,False)

    def onAIModelConfigChanged(self):
        """处理AI模型配置变更"""
        self.logger.debug("AI模型配置已更改")
        # 可以在这里更新其他组件或设置

    def addPreferenceTab(self, data):
        # print("addPreferenceTab")
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
            # exec(self.runCode, global_vars, local_vars)
            fig = local_vars.get(need_variable)
            if fig:
                self.updateMatplotlibDisplay(fig)

    # 清空 QVBoxLayout 中所有子控件
    def clearLayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            layout.removeWidget(widget)
            if widget is not None:
                widget.deleteLater()

    def updateVTKVisualization(self, vtkObject):
        # 更新VTK可视化图
        # renderer = self.vtkWidget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        # renderer.RemoveAllViewProps()  # 移除当前渲染器中的所有对象
        self.vtkObject = vtkObject
        self.vtkWidget.GetRenderWindow().AddRenderer(
            vtkObject
        )  # 将渲染器添加到渲染窗口
        self.vtkWidget.GetRenderWindow().Render()  # 渲染一次
        # 将当前选中的 tab 设置为 "Vtk Visualization"
        vtkVisualizationIndex = self.tabWidget.indexOf(self.vtkVisualizationTab)
        self.tabWidget.setCurrentIndex(vtkVisualizationIndex)

    def updateMatplotlibDisplay(self, fig):
        # 更新Matplotlib显示
        self.matplotlibWidget = CustomFigureCanvas(fig)
        self.clearLayout(self.matplotlibLayout)
        self.matplotlibLayout.addWidget(self.matplotlibWidget)
        # 将当前选中的 tab 设置为 "Matplotlib Display"
        matplotlibDisplayIndex = self.tabWidget.indexOf(self.matplotlibDisplayTab)
        self.tabWidget.setCurrentIndex(matplotlibDisplayIndex)

    def updateDataTable(self, data):
        # print(data)
        # self.unregisterComponent("Data Table Tab")
        # self.dataTableTab = DataTableTab(data,4)
        # self.tabWidget.addTab(self.dataTableTab, "Data Table")
        # self.registerComponent("Data Table Tab", self.dataTableTab, True)
        self.dataTableTab.populateTable(data, 4)
        dataTableIndex = self.tabWidget.indexOf(self.dataTableTab)
        self.tabWidget.setCurrentIndex(dataTableIndex)

    def onTabChanged(self, index):
        """选项卡切换事件处理"""
        if index < 0 or index >= self.tabWidget.count():
            return

        # 先自动保存当前文件（如果已修改且开启了自动保存）
        code_tab = self.parent.get_component_by_name("Code Tab")
        if code_tab:
            code_tab.save_if_auto()

        tab_name = self.tabWidget.tabText(index)
        self.logger.debug(f"切换到选项卡: {tab_name}")

        # 特殊处理AI对话选项卡
        if tab_name == "AI" and hasattr(self, "aiChatTab"):
            # 如果AI对话选项卡未连接，尝试连接
            if not self.aiChatTab.client:
                self.logger.debug("AI对话选项卡需要连接到模型")
                # 异步连接，避免阻塞UI
                from PySide6.QtCore import QTimer

                QTimer.singleShot(100, self.aiChatTab.connectToModel)

    def switchToAIChat(self):
        """切换到AI对话选项卡"""
        for i in range(self.tabWidget.count()):
            if self.tabWidget.tabText(i) == "AI":
                self.tabWidget.setCurrentIndex(i)
                return True

        # 如果没有找到AI对话选项卡，尝试添加它
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
            # 确保聊天输入框获得焦点
            if hasattr(self.aiChatTab, "inputField"):
                self.aiChatTab.inputField.setFocus()
        return result
