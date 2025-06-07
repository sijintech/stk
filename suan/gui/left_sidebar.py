from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileSystemModel, QTreeView, QMessageBox, QFileIconProvider
from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
import os
import vtkmodules.all as vtk
from custom_logger import CustomLogger
import chardet

class FileIconProvider(QFileIconProvider):
    def icon(self, file_info):
        if file_info.isDir():
            return QIcon("./icons/dir.png")
        else:
            return QIcon("./icons/file.png")



class LeftSidebar(QWidget):
    openFilePath = Signal(str)  # 

    def __init__(self, parent):
        super().__init__()
        self.logger = CustomLogger()
        self.parent = parent

        self.parent.registerComponent('File structure', self, True)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.treeView = QTreeView()

        layout.addWidget(self.treeView)
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setupFileSystemModel()

    def setupFileSystemModel(self):

        self.model = QFileSystemModel(self)
        root_path = os.getcwd()  # 
        self.logger.debug(f": {root_path}")
        self.model.setRootPath(root_path)


        root_index = self.model.index(root_path)
        self.logger.debug(f": {root_index.isValid()}")

        self.treeView.setModel(self.model)
        if root_index.isValid():
            self.treeView.setRootIndex(root_index)
        else:
            self.logger.error("")

        self.model.setIconProvider(FileIconProvider())

        self.treeView.header().hide()

        self.treeView.setColumnHidden(1, True)
        self.treeView.setColumnHidden(2, True)
        self.treeView.setColumnHidden(3, True)

        self.treeView.doubleClicked.connect(self.onDoubleClick)
    def initWorkspace(self):
        working_directory = self.parent.get_workspace_data('left_sidebar/working_directory')
        self.logger.debug(f": {working_directory}")

        if not hasattr(self, 'model') or self.model is None:
            self.logger.error(" setupFileSystemModel")
            return

        index = self.model.index(working_directory)
        self.logger.debug(f": {index.isValid()}")

        if index.isValid():
            self.treeView.setRootIndex(index)
        else:
            self.logger.error(f": {working_directory}")

    def onDoubleClick(self, index: QModelIndex):

        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.open_dir(path)
        else:
            self.open_file(path)

    def open_dir(self, directory):

        index = self.model.index(directory)
        if os.path.exists(directory):
            index = self.model.index(directory)
            if index.isValid():
                self.treeView.expand(index)  # 
        else:
            QMessageBox.warning(self, "", f": {directory}")

    def open_directory(self, directory, workspace_data=None, init_workspace=True):

        self.logger.debug(f": {self.parent.curWorkDir}")

        if self.parent.curWorkDir is not None and not self.parent.curWorkDir == directory:
            if self.parent.isWorkspace:
                self.parent.check_and_save_curworkspace()
            else:
                self.parent.check_and_save_curfile()

        self.logger.debug(f": {directory}")
        self.parent.curWorkDir = directory

        if not hasattr(self, 'model') or self.model is None:
            self.logger.error(" setupFileSystemModel")
            return

        index = self.model.index(directory)
        self.logger.debug(f": {index.isValid()}")

        if index.isValid():
            self.treeView.setRootIndex(index)
        else:
            self.logger.error(f": {directory}")


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

        index = self.treeView.currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "", "")
            return
        path = self.model.filePath(index)
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        new_file_path = os.path.join(path, ".txt")
        try:
            with open(new_file_path, "w", encoding="utf-8") as file:
                file.write("")
            self.logger.info(f": {new_file_path}")
            self.model.refresh()
        except Exception as e:
            QMessageBox.critical(self, "", f": {e}")

    def create_new_dir(self):

        index = self.treeView.currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "", "")
            return
        path = self.model.filePath(index)
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        new_dir_path = os.path.join(path, "")
        try:
            os.makedirs(new_dir_path, exist_ok=True)
            self.logger.info(f": {new_dir_path}")
            self.model.refresh()
        except Exception as e:
            QMessageBox.critical(self, "", f": {e}")

    def detect_file_encoding(self, file_path):
        with open(file_path, 'rb') as file:
            raw_data = file.read(100)  # 100
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            return encoding

    def open_file(self, path, working_directory="", is_init=False):

        if working_directory == "":
            working_directory = os.path.dirname(os.path.abspath(path))

        if self.parent.curWorkFile is not None and not is_init:
            self.parent.check_and_save_curfile()
        if os.path.isdir(path):
            self.logger.debug("")
            return

        self.parent.curWorkFile = path

        if self.parent.isWorkspace:
            self.parent.modify_workspaceData('info_bar/code/file_path', path)

        if QFileInfo(path).isFile():
            extension = QFileInfo(path).suffix().lower()
            if extension == 'vtk':
                reader = vtk.vtkStructuredPointsReader()
                reader.SetFileName(path)
                reader.Update()

                structured_points = reader.GetOutput()

                dimensions = structured_points.GetDimensions()
                origin = structured_points.GetOrigin()
                spacing = structured_points.GetSpacing()

                vertex_data = {}

                num_x = dimensions[0]
                num_y = dimensions[1]
                num_z = dimensions[2]

                for i in range(num_x):
                    for j in range(num_y):
                        for k in range(num_z):
                            x = origin[0] + i * spacing[0]
                            y = origin[1] + j * spacing[1]
                            z = origin[2] + k * spacing[2]

                            scalar_value = structured_points.GetScalarComponentAsFloat(i, j, k, 0)

                            vertex_data[(x, y, z)] = scalar_value
                self.parent.center_widget.updateDataTable(vertex_data)
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        content = file.read()

                        self.parent.get_component_by_name('Code Tab').showContent(content)
                except Exception as e:
                    self.logger.error(f"Error reading file:{e}")
            else:
                try:
                    file_encoding = self.detect_file_encoding(path)
                    with open(path, 'r', encoding=file_encoding, errors='ignore') as file:
                        content = file.read()

                        self.parent.get_component_by_name('Code Tab').encoding = file_encoding
                        self.parent.get_component_by_name('Code Tab').showContent(content)
                except Exception as e:
                    self.logger.error(f"Error reading file:{e}")

    def tree_double_clicked(self, item, column):

        self.check_auto_save()
        
        if item.childCount() == 0:  # 判断是否是叶子节点
            file_path = self.get_file_path(item)
            self.logger.debug(f"双击了文件: {file_path}")

            self.openFilePath.emit(file_path)
            code_tab = self.parent.get_component_by_name("Code Tab")
            if code_tab:
                code_tab.open_file(file_path)
                
    def check_auto_save(self):
        """检查并自动保存当前文件（如果启用了自动保存）"""
        code_tab = self.parent.get_component_by_name("Code Tab")
        if code_tab:
            code_tab.save_if_auto()
