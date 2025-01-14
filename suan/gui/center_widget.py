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

    def initWorkspace(self):
        active_tab_index = self.parent.get_workspace_data('center_widget/active_tab_index')
        self.tabWidget.setCurrentIndex(active_tab_index)
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
        self.dataTableTab = DataTableTab({},4)
        self.tabWidget.addTab(self.dataTableTab, "Data Table")
        self.registerComponent("Data Table Tab", self.dataTableTab, True)

        # preferenceTab
        # self.preferenceTab = PreferenceTab()
        # # self.tabWidget.addTab(self.preferenceTab, "Preference")
        # self.registerComponent("Preference Tab", self.preferenceTab,False)

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
            self.parent.get_component_by_name('Code Tab').execute_code_with_file_path(
                self.runCode, script_path, global_vars, local_vars
            )
            renderer = local_vars.get(need_variable)
            if renderer:
                self.updateVTKVisualization(renderer)
        if self.runCodeType == "matplotlib":
            local_vars = {}
            global_vars = {"plt": plt}
            self.parent.get_component_by_name('Code Tab').execute_code_with_file_path(
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
        self.vtkObject=vtkObject
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

    # def update_code(self):
    #     codeIndex = self.tabWidget.indexOf(self.codeTab)
    #     self.tabWidget.setCurrentIndex(codeIndex)
