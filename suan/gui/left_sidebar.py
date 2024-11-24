from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileSystemModel, QTreeView, QMessageBox, QFileIconProvider
from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
import os
import vtk
from custom_logger import CustomLogger


class FileIconProvider(QFileIconProvider):
    def icon(self, file_info):
        if file_info.isDir():
            return QIcon("./icons/dir.png")
        else:
            return QIcon("./icons/file.png")
        # return super().icon(file_info)


class LeftSidebar(QWidget):
    openFilePath = Signal(str)  # 定义一个信号，用于发送打开文件请求

    def __init__(self, parent):
        super().__init__()
        self.logger = CustomLogger()
        self.parent = parent
        # self.curFile=None
        self.parent.registerComponent('File structure', self, True)
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
        root_path = os.getcwd()  # 获取当前工作目录
        self.model.setRootPath(root_path)
        self.treeView.setRootIndex(self.model.index(root_path))  # 设置根索引为当前路径
        self.treeView.setModel(self.model)
        # 自定义文件和目录图标
        self.model.setIconProvider(FileIconProvider())

        # 隐藏标题栏
        self.treeView.header().hide()

        # 隐藏其他列
        self.treeView.setColumnHidden(1, True)
        self.treeView.setColumnHidden(2, True)
        self.treeView.setColumnHidden(3, True)

        # 连接双击信号到槽函数
        self.treeView.doubleClicked.connect(self.onDoubleClick)
    def initWorkspace(self):
        working_directory = self.parent.get_workspace_data('left_sidebar/working_directory')
        self.logger.debug(working_directory)
        self.treeView.setRootIndex(self.model.index(working_directory))

    def onDoubleClick(self, index: QModelIndex):
        # 获取所选项的路径
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.open_dir(path)
        else:
            self.open_file(path)

    def open_dir(self, directory):
        # 展开指定目录的内容
        index = self.model.index(directory)
        if os.path.exists(directory):
            index = self.model.index(directory)
            if index.isValid():
                self.treeView.expand(index)  # 展开目录
        else:
            QMessageBox.warning(self, "警告", f"目录不存在: {directory}")

    def open_directory(self, directory, workspace_data=None, init_workspace=True):
        # 原来目录处理
        self.logger.debug(self.parent.curWorkDir)

        if self.parent.curWorkDir is not None and not self.parent.curWorkDir == directory:
            if self.parent.isWorkspace:
                self.parent.check_and_save_curworkspace()
            else:
                self.parent.check_and_save_curfile()

        # 新的目录处理
        self.logger.debug("打开：%s", directory)
        self.parent.curWorkDir = directory
        # self.parent.checkWorkspaceFile(directory)
        self.treeView.setRootIndex(self.model.index(directory))

        if not init_workspace:
            return
        elif self.parent.curworkdir_is_workspace():
            self.parent.init_workspace()
            if workspace_data and isinstance(workspace_data, dict):
                for path, value in workspace_data.items():
                    self.parent.modify_workspaceData(path, value)
                self.parent.init_ui_from_workspace()
        else:
            self.parent.question_and_create_workspace(directory, False)

    def create_new_file(self):
        # 在文件系统视图选中的位置创建一个新文件
        index = self.treeView.currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "警告", "请先选择一个位置")
            return
        path = self.model.filePath(index)
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        new_file_path = os.path.join(path, "新建文件.txt")
        try:
            with open(new_file_path, "w", encoding="utf-8") as file:
                file.write("")
            self.logger.info(f"新建文件: {new_file_path}")
            self.model.refresh()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建新文件: {e}")

    def create_new_dir(self):
        # 在文件系统视图选中的位置创建一个新目录
        index = self.treeView.currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "警告", "请先选择一个位置")
            return
        path = self.model.filePath(index)
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        new_dir_path = os.path.join(path, "新建文件夹")
        try:
            os.makedirs(new_dir_path, exist_ok=True)
            self.logger.info(f"新建文件夹: {new_dir_path}")
            self.model.refresh()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建新文件夹: {e}")

    def open_file(self, path, working_directory="", is_init=False):
        # TODO:打开一个数据大文件时，需要等待，应设置等待页面
        # 原来文件处理
        if working_directory == "":
            working_directory = os.path.dirname(os.path.abspath(path))

        if self.parent.curWorkFile is not None and not is_init:
            # self.parent.checkAndSaveCurFile()
            # if self.parent.isWorkspace and not os.path.samefile(self.parent.curWorkDir, working_directory):
            #     self.parent.check_and_save_curworkspace()
            # else:
            self.parent.check_and_save_curfile()
        # 新的文件处理
        self.parent.curWorkFile = path
        # if not os.path.samefile(self.parent.curWorkDir, working_directory):
        #     self.open_directory(working_directory, not is_init)
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
                    print("Error reading file:%s", e)
            else:
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        content = file.read()
                        # self.openFilePath.emit(path)
                        # 发送文件内容给InfoBar
                        self.parent.info_bar.showContent(content,path)
                except Exception as e:
                    print("Error reading file:%s", e)
