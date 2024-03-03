from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTabWidget
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
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


        vtkVisualizationTab = QWidget()
        # vtkVisualizationLabel = QLabel("VTK Visualization Tab")
        vtkLayout = QVBoxLayout()
        # vtkLayout.addWidget(vtkVisualizationLabel)
        vtkLayout.addWidget(self.vtkWidget)
        vtkVisualizationTab.setLayout(vtkLayout)
        self.tabWidget.addTab(vtkVisualizationTab, "VTK Visualization")

        #  matplotlibDisplayTab
        matplotlibDisplayTab = QWidget()
        matplotlibLabel = QLabel("Matplotlib Display Tab")
        matplotlibLayout = QVBoxLayout()
        matplotlibLayout.addWidget(matplotlibLabel)
        matplotlibDisplayTab.setLayout(matplotlibLayout)
        self.tabWidget.addTab(matplotlibDisplayTab, "Matplotlib Display")

        # dataTableTab
        dataTableTab = QWidget()
        dataTableLabel = QLabel("Data Table Tab")
        dataLayout = QVBoxLayout()
        dataLayout.addWidget(dataTableLabel)
        dataTableTab.setLayout(dataLayout)
        self.tabWidget.addTab(dataTableTab, "Data Table")
    
    def runCodeWithAnalysis(self,runCode,runCodeType,need_variable):
        print("更新运行代码")
        self.runCode=runCode
        self.runCodeType=runCodeType
        if self.runCodeType=='vtk':
            local_vars = {}
            global_vars = {'vtk': vtk}
            exec(self.runCode, global_vars, local_vars)
            renderer = local_vars.get(need_variable)
            if renderer:
                self.updateVTKVisualization(renderer)
        
    def updateVTKVisualization(self, vtkObject):
        # 更新VTK可视化图
        print("更新运行代码")
        # renderer = self.vtkWidget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        # renderer.RemoveAllViewProps()  # 移除当前渲染器中的所有对象
        self.vtkWidget.GetRenderWindow().AddRenderer(vtkObject)  # 将渲染器添加到渲染窗口
        self.vtkWidget.GetRenderWindow().Render()  # 渲染一次

       

