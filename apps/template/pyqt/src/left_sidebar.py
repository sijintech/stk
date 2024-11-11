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
        # self.curFile=None
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
        # TODO:设置一个上级目录，以供返回

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
        working_directory = self.parent.get_workspace_data('left_sidebar/working_directory')
        self.treeView.setRootIndex(self.model.index(working_directory))

        
    def onDoubleClick(self, index: QModelIndex):
        # 获取所选项的路径
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.open_directory(path)
        else:
            self.open_file(path)

    def open_directory(self, directory, init_workspace=True):
        # 原来目录处理
        if self.parent.curWorkDir is not None and not os.path.samefile(self.parent.curWorkDir, directory):
            if self.parent.isWorkspace:
                self.parent.check_and_save_curworkspace()
            else:
                self.parent.check_and_save_curfile()

        # 新的目录处理
        print("打开：", directory)
        self.parent.curWorkDir = directory
        # self.parent.checkWorkspaceFile(directory)
        self.treeView.setRootIndex(self.model.index(directory))

        if not init_workspace:
            return
        elif self.parent.curworkdir_is_workspace():
            self.parent.init_workspace()
        else:
            self.parent.question_and_create_workspace(directory, False)

    def open_file(self, path, working_directory="", is_init=False):
        # TODO:打开一个数据大文件时，需要等待，应设置等待页面
        # 原来文件处理
        if working_directory == "":
            working_directory = os.path.dirname(os.path.abspath(path))

        if self.parent.curWorkFile is not None and not is_init:
            # self.parent.checkAndSaveCurFile()
            if self.parent.isWorkspace and not os.path.samefile(self.parent.curWorkDir, working_directory):
                self.parent.check_and_save_curworkspace()
            else:
                self.parent.check_and_save_curfile()
        # 新的文件处理
        self.parent.curWorkFile = path
        if not os.path.samefile(self.parent.curWorkDir, working_directory):
            self.open_directory(working_directory, not is_init)
        if self.parent.isWorkspace:
            self.parent.modify_workspaceData('info_bar/code/file_path', path)

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
