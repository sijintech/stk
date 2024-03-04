from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTabWidget
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg 
import matplotlib.pyplot as plt
class CustomFigureCanvas(FigureCanvasQTAgg):
    def __init__(self, figure=None):
        super().__init__(figure)
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
    def __init__(self):
        super().__init__()
        self.runCodeType=None
        self.runCode=None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.tabWidget = QTabWidget()
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)

        self.addMainOperationTabs()

    def addMainOperationTabs(self):
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

        #  matplotlibDisplayTab
        self.matplotlibWidget = CustomFigureCanvas()  # 创建画布控件
        self.matplotlibDisplayTab = QWidget()
        self.matplotlibLayout = QVBoxLayout()
        self.matplotlibLayout.addWidget(self.matplotlibWidget)
        self.matplotlibDisplayTab.setLayout(self.matplotlibLayout)
        self.tabWidget.addTab(self.matplotlibDisplayTab, "Matplotlib Display")

        # dataTableTab
        dataTableTab = QWidget()
        dataTableLabel = QLabel("Data Table Tab")
        dataLayout = QVBoxLayout()
        dataLayout.addWidget(dataTableLabel)
        dataTableTab.setLayout(dataLayout)
        self.tabWidget.addTab(dataTableTab, "Data Table")
    
    def runCodeWithAnalysis(self,runCode,runCodeType,need_variable):
        self.runCode=runCode
        self.runCodeType=runCodeType
        if self.runCodeType=='vtk':
            local_vars = {}
            global_vars = {'vtk': vtk}
            exec(self.runCode, global_vars, local_vars)
            renderer = local_vars.get(need_variable)
            if renderer:
                self.updateVTKVisualization(renderer)
        if self.runCodeType=='matplotlib':
            local_vars = {}
            global_vars = {'plt': plt}
            exec(self.runCode, global_vars, local_vars)
            fig = local_vars.get(need_variable)
            if fig:
                self.updateMatplotlibDisplay(fig) 
    # 清空 QVBoxLayout 中所有子控件
    def clearLayout(self,layout):
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
        self.vtkWidget.GetRenderWindow().AddRenderer(vtkObject)  # 将渲染器添加到渲染窗口
        self.vtkWidget.GetRenderWindow().Render()  # 渲染一次
        # 将当前选中的 tab 设置为 "Vtk Visualization"
        vtkVisualizationIndex = self.tabWidget.indexOf(self.vtkVisualizationTab)
        self.tabWidget.setCurrentIndex(vtkVisualization)
    def updateMatplotlibDisplay(self,fig):
        # 更新Matplotlib显示
        self.matplotlibWidget=CustomFigureCanvas(fig)
        self.clearLayout(self.matplotlibLayout)
        self.matplotlibLayout.addWidget(self.matplotlibWidget)
        # 将当前选中的 tab 设置为 "Matplotlib Display"
        matplotlibDisplayIndex = self.tabWidget.indexOf(self.matplotlibDisplayTab)
        self.tabWidget.setCurrentIndex(matplotlibDisplayIndex)
       

