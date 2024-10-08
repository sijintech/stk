from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileSystemModel, QTreeView, QMessageBox
from PySide6.QtCore import QModelIndex, Qt,Signal
from PySide6.QtCore import QFileInfo
import os
import vtk
class LeftSidebar(QWidget):
    openFilePath = Signal(str)  # 定义一个信号，用于发送打开文件请求
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.curDir=None
        self.curFile=None
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
        if os.path.isdir(path):
            self.openDirectory(path)
        else:
            self.openFile(path)

    def openDirectory(self, directory):
        # 原来目录处理
        if self.curDir!=None and self.curDir!=directory:
            if self.parent.openWorkspace:
                self.parent.checkAndSaveCurWorkspace()

        # 新的目录处理
        self.curDir=directory
        self.parent.modify_preferences('Open_Last_Working_Directory', directory)
        # self.parent.checkWorkspaceFile(directory)
        self.treeView.setRootIndex(self.model.index(directory))
        file_name=self.parent.checkWorkspaceFile(directory)
        if self.parent.openWorkspace:
            self.parent.workspace_suan_path = os.path.join(directory, file_name)
            self.parent.workspaceData=self.parent.load_workspaceData_from_file()
            self.parent.modify_workspaceData('left_sidebar/working_directory', directory)

        else:
            self.parent.questionAndCreateWorkspace(directory)

    def openFile(self, path, working_directory=""):
        # if working_directory=="":
        #     working_directory = os.path.dirname(os.path.abspath(path))
        # self.parent.modify_preferences('Open_Last_Working_Directory', working_directory)
        # self.parent.checkWorkspaceFile(working_directory)
        # self.treeView.setRootIndex(self.model.index(working_directory))
        # if self.parent.openWorkspace==True:
        #     # self.parent.modify_workspaceData('left_sidebar/working_directory', working_directory)
        #     self.parent.modify_workspaceData('info_bar/code/file_path',path)
        # else :
        #     reply = QMessageBox.question(
        #         self,
        #         "Warning",
        #         "是否为该目录创建工作区",
        #         QMessageBox.Yes,
        #         QMessageBox.No,
        #     )
        #     if reply == QMessageBox.Yes:
        #         this_dir = os.path.dirname(os.path.abspath(__file__))
        #         self.parent.createWorkspaceFile(working_directory, os.path.join(this_dir, "../workspace.suan"))
        # 原来文件处理
        if working_directory == "":
            working_directory = os.path.dirname(os.path.abspath(path))
        if self.curFile != None:
            # self.parent.checkAndSaveCurFile()
            if self.parent.openWorkspace and self.curDir!=working_directory:
                self.parent.checkAndSaveCurWorkspace()
            else:
                self.parent.checkAndSaveCurFile()
        # 新的文件处理
        self.curFile=path
        self.openDirectory(working_directory)
        if self.parent.openWorkspace:
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
                self.parent.center_widget.updateDataTable(vertex_data)
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
