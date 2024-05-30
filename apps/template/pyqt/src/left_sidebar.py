from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileSystemModel, QTreeView
from PySide6.QtCore import QModelIndex, Qt,Signal
from PySide6.QtCore import QFileInfo
import os
import vtk
class LeftSidebar(QWidget):
    openFilePath = Signal(str)  # 定义一个信号，用于发送打开文件请求
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.parent.registerComponent('File structure',self,True)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.treeView = QTreeView()

        layout.addWidget(self.treeView)
        self.setLayout(layout)
        layout.setContentsMargins(0,0,0,0)
        self.setupFileSystemModel()

    def setupFileSystemModel(self):
        # 创建文件系统模型
        self.model = QFileSystemModel(self) 
        self.model.setRootPath("")
        self.treeView.setModel(self.model)
        self.treeView.setRootIndex(self.model.index(""))  # 设置根索引为当前路径
        # 只想显示name这一列，不想显示size,type,modified的信息
        self.treeView.setColumnHidden(1, True)
        self.treeView.setColumnHidden(2, True)
        self.treeView.setColumnHidden(3, True)
        # 连接双击信号到槽函数
        self.treeView.doubleClicked.connect(self.onDoubleClick)

    def initWorkspace(self):
        working_directory=self.parent.get_workspaceData('left_sidebar/working_directory')
        self.treeView.setRootIndex(self.model.index(working_directory))

        
    def onDoubleClick(self, index: QModelIndex):
        # 获取所选项的路径
        path = self.model.filePath(index)
        self.openFlie(path)
        
    def openFlie(self,path):  
        working_directory = os.path.dirname(os.path.abspath(path))
        self.parent.modify_workspaceData('left_sidebar/working_directory', working_directory)
        self.parent.modify_workspaceData('info_bar/code/file_path',path)
        # 如果是文件，则读取文件内容
        if QFileInfo(path).isFile():
            extension = QFileInfo(path).suffix().lower()
            if extension == 'vtk':
                reader = vtk.vtkStructuredPointsReader()
                reader.SetFileName(path)
                reader.Update()
                # 获取结构化点数据对象
                structured_points = reader.GetOutput()
                # 获取结构化点数据的属性信息
                dimensions = structured_points.GetDimensions()
                origin = structured_points.GetOrigin()
                spacing = structured_points.GetSpacing()

                # 创建一个字典来存储顶点坐标和数据值
                vertex_data = {}

                # 计算每个维度上的顶点数量
                num_x = dimensions[0]
                num_y = dimensions[1]
                num_z = dimensions[2]

                # 将顶点的坐标和数据值存储到字典中
                for i in range(num_x):
                    for j in range(num_y):
                        for k in range(num_z):
                            x = origin[0] + i * spacing[0]
                            y = origin[1] + j * spacing[1]
                            z = origin[2] + k * spacing[2]

                            scalar_value = structured_points.GetScalarComponentAsFloat(i, j, k, 0)
                            
                            # 使用(x, y, z)作为键，数据值作为值存储到字典中
                            vertex_data[(x, y, z)] = scalar_value
                self.parent.center_widget.updateMatplotlibDisplay(vertex_data)
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        content = file.read()
                        # self.openFilePath.emit(path)
                        # 发送文件内容给InfoBar
                        self.parent.info_bar.showContent(content, path)
                except Exception as e:
                    print("Error reading file:", e)
            else:
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        content = file.read()
                        # self.openFilePath.emit(path)
                        # 发送文件内容给InfoBar
                        self.parent.info_bar.showContent(content,path)
                except Exception as e:
                    print("Error reading file:", e)
