import os
import sys

if sys.platform == "win32":
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(2)
    except (ImportError, AttributeError, OSError):
        pass

import re
import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QStatusBar,
    QLabel,
    QMessageBox,
    QFileDialog,
    QDialog,
    QPushButton,
    QLineEdit,
    QFormLayout,
    QDialogButtonBox,
    QListWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
import left_sidebar
import center_widget
import right_sidebar
import toolbar
import statusbar
import info_bar
import Updater
import version
import os
import toml
import shutil
from custom_logger import CustomLogger
from Tab.cli import CLIIntegrator

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "./Tab")))
updatejson_url = "https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/update.json"
app_name = "stk"
cur_version = version.version
code_url = "https://github.com/sijintech/stk"
os.environ["QT_API"] = "pyside"


class MainWindow(QMainWindow):
    def __init__(self, create_workspace_if_no):
        super().__init__()
        self.logger = CustomLogger()
        

        self.curWorkDir = None
        self.curWorkFile = None
        self.workspace_conf_path = None
        self.workspaceData = {}
        self.preferences = None
        self.isWorkspace = False
        self.is_first_launch = False
        self.create_workspace_if_no = create_workspace_if_no
        self.window_initialized = False

        self.init_preferences()
        

        self.components = {"main": {"name": "main", "component": self, "children": {}}}
        self.center_widget = center_widget.CenterWidget(self)
        self.right_sidebar = right_sidebar.RightSidebar(self)
        self.status_bar = statusbar.Statusbar(self)
        self.info_bar = info_bar.InfoBar(self)
        self.left_sidebar = left_sidebar.LeftSidebar(self)
        self.toolbar = toolbar.ToolBar(self)
        self.center_splitter = QSplitter()
        self.main_splitter = QSplitter()
        self.update_status_bar = QStatusBar()
        self.updateWindow = None
        self.cli_integrator = None

        self.init_ui()
        self.check_update()

    def init_ui(self):

        self.setWindowTitle("STK")

        self.center_splitter.setOrientation(Qt.Vertical)
        self.center_splitter.addWidget(self.center_widget)
        self.center_splitter.addWidget(self.info_bar)

        self.main_splitter.addWidget(self.left_sidebar)
        self.main_splitter.addWidget(self.center_splitter)
        self.main_splitter.addWidget(self.right_sidebar)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.main_splitter)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.setStatusBar(self.status_bar)

        self.left_sidebar.openFilePath.connect(self.fixCurFilePath)

        self.main_splitter.setSizes(
            [
                int(self.preferences["UI_Init"]["left_sidebar_width"]),
                self.main_splitter.width()
                - int(self.preferences["UI_Init"]["right_sidebar_width"])
                - int(self.preferences["UI_Init"]["left_sidebar_width"]),
                int(self.preferences["UI_Init"]["right_sidebar_width"]),
            ]
        )

        self.center_splitter.setSizes(
            [
                int(self.preferences["UI_Init"]["center_widget_height"]),
                self.center_splitter.height()
                - int(self.preferences["UI_Init"]["center_widget_height"]),
            ]
        )

        for father_component in ["Info", "Visualization_window", "Tool", "Other"]:
            UI_Components_not_Visibile = [
                key
                for key, value in self.preferences["UI_Component_Visibility_Init"][
                    father_component
                ].items()
                if value is False
            ]
            for component in UI_Components_not_Visibile:
                if father_component != "Other":
                    path = (
                            father_component.replace("_", " ")
                            + "/"
                            + component.replace("_", " ")
                    )
                    self.toggleComponentVisibility(path)
                else:
                    path = component.replace("_", " ")
                    self.toggleComponentVisibility(path)

        self.cli_integrator = CLIIntegrator(self)

    def showEvent(self, event):
        self.logger.debug("showEvent")
        super().showEvent(event)
        if self.window_initialized:
            return

        if self.is_first_launch:
            self.show_welcome_dialog()
            return

        if self.preferences.get("Open_Last_Workspace", True) and self.preferences.get("Recent_Workspaces", []):

            recent_workspaces = self.preferences.get("Recent_Workspaces", [])
            if recent_workspaces and os.path.exists(recent_workspaces[0]):
                self.curWorkDir = recent_workspaces[0]
                if self.curworkdir_is_workspace():
                    self.init_workspace()
                    return

            for workspace_path in recent_workspaces[1:]:
                if os.path.exists(workspace_path):
                    self.curWorkDir = workspace_path
                    if self.curworkdir_is_workspace():
                        self.init_workspace()
                        return

        if self.curWorkDir and os.path.exists(self.curWorkDir):
            if self.create_workspace_if_no:
                self.question_and_create_workspace(self.curWorkDir, True)
            else:

                self.setGeometry(
                    50,
                    50,
                    int(self.preferences["UI_Init"]["window_width"]),
                    int(self.preferences["UI_Init"]["window_height"]),
                )
        else:

            self.show_welcome_dialog()
            
    def show_welcome_dialog(self):
        """显示欢迎对话框，让用户选择打开文件夹或创建新项目"""
        dialog = QDialog(self)
        dialog.setWindowTitle("欢迎使用STK")
        dialog.setMinimumWidth(650)
        dialog.setMinimumHeight(400)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        top_section = QVBoxLayout()

        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        
        title_label = QLabel("欢迎使用STK")
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignCenter)
        top_section.addWidget(title_label)

        desc_label = QLabel("选择一个选项开始您的工作")
        desc_label.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        desc_label.setAlignment(Qt.AlignCenter)
        top_section.addWidget(desc_label)
        
        main_layout.addLayout(top_section)

        middle_section = QHBoxLayout()
        middle_section.setSpacing(15)

        button_style = """
        QPushButton {
            background-color: #f5f5f5;
            border: 1px solid #dcdcdc;
            border-radius: 5px;
            padding: 15px;
            text-align: center;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
            border: 1px solid #c0c0c0;
        }
        QPushButton:pressed {
            background-color: #d0d0d0;
        }
        """

        open_folder_card = QVBoxLayout()
        open_folder_btn = QPushButton("打开文件夹")
        open_folder_btn.setMinimumHeight(100)
        open_folder_btn.setStyleSheet(button_style)
        open_folder_btn.clicked.connect(lambda: self.open_folder_from_dialog(dialog))
        open_folder_card.addWidget(open_folder_btn)
        open_folder_desc = QLabel("浏览并打开一个已有的文件夹作为工作目录")
        open_folder_desc.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        open_folder_desc.setAlignment(Qt.AlignCenter)
        open_folder_card.addWidget(open_folder_desc)
        middle_section.addLayout(open_folder_card)

        create_project_card = QVBoxLayout()
        create_new_btn = QPushButton("创建新项目")
        create_new_btn.setMinimumHeight(100)
        create_new_btn.setStyleSheet(button_style)
        create_new_btn.clicked.connect(lambda: self.create_new_project_dialog(dialog))
        create_project_card.addWidget(create_new_btn)
        create_project_desc = QLabel("创建一个新的项目目录和工作区")
        create_project_desc.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        create_project_desc.setAlignment(Qt.AlignCenter)
        create_project_card.addWidget(create_project_desc)
        middle_section.addLayout(create_project_card)

        if self.preferences.get("Recent_Workspaces", []):
            recent_project_card = QVBoxLayout()
            open_recent_btn = QPushButton("打开最近项目")
            open_recent_btn.setMinimumHeight(100)
            open_recent_btn.setStyleSheet(button_style)
            open_recent_btn.clicked.connect(lambda: self.open_recent_workspace_dialog(dialog))
            recent_project_card.addWidget(open_recent_btn)
            recent_project_desc = QLabel("从最近的项目列表中选择")
            recent_project_desc.setStyleSheet("color: #7f8c8d; font-size: 12px;")
            recent_project_desc.setAlignment(Qt.AlignCenter)
            recent_project_card.addWidget(recent_project_desc)
            middle_section.addLayout(recent_project_card)
        
        main_layout.addLayout(middle_section)

        bottom_section = QHBoxLayout()

        bottom_right = QHBoxLayout()
        bottom_right.addStretch()
        skip_btn = QPushButton("跳过，直接进入")
        skip_btn.setStyleSheet("color: #7f8c8d;")
        skip_btn.clicked.connect(dialog.accept)
        bottom_right.addWidget(skip_btn)
        bottom_section.addLayout(bottom_right)
        
        main_layout.addLayout(bottom_section)
        
        dialog.setLayout(main_layout)
        dialog.exec()

        if not self.isWorkspace:
            self.setGeometry(
                50,
                50,
                int(self.preferences["UI_Init"]["window_width"]),
                int(self.preferences["UI_Init"]["window_height"]),
            )
    
    def open_folder_from_dialog(self, parent_dialog=None):
        """从对话框中选择并打开文件夹"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "选择工作目录", os.path.expanduser("~")
        )
        
        if folder_path:
            self.curWorkDir = folder_path

            self.add_to_recent_workspaces(folder_path)
            
            if self.curworkdir_is_workspace():
                self.init_workspace()
            else:
                self.question_and_create_workspace(folder_path, True)

            if parent_dialog:
                parent_dialog.accept()
    
    def create_new_project_dialog(self, parent_dialog=None):
        """创建新项目对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("创建新项目")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()

        project_name_edit = QLineEdit()
        form_layout.addRow("项目名称:", project_name_edit)

        location_layout = QHBoxLayout()
        location_edit = QLineEdit(os.path.expanduser("~"))
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(lambda: self.browse_project_location(location_edit))
        location_layout.addWidget(location_edit)
        location_layout.addWidget(browse_btn)
        form_layout.addRow("项目位置:", location_layout)
        
        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(lambda: self.create_new_project(project_name_edit.text(), location_edit.text(), dialog, parent_dialog))
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    def browse_project_location(self, line_edit):
        """浏览项目位置"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "选择项目位置", line_edit.text()
        )
        if folder_path:
            line_edit.setText(folder_path)
    
    def create_new_project(self, project_name, location, dialog, parent_dialog=None):
        """创建新项目"""
        if not project_name or not location:
            QMessageBox.warning(self, "错误", "项目名称和位置不能为空")
            return

        project_path = os.path.join(location, project_name)
        if os.path.exists(project_path):
            QMessageBox.warning(self, "错误", f"项目目录已存在: {project_path}")
            return
            
        try:
            os.makedirs(project_path, exist_ok=True)
            self.logger.info(f"已创建项目目录: {project_path}")

            self.curWorkDir = project_path

            self.add_to_recent_workspaces(project_path)

            this_dir = os.path.dirname(os.path.abspath(__file__))
            workspace_template = os.path.join(this_dir, get_resource_path("confs/workspace.suan"))
            self.create_workspace_file(project_path, workspace_template)

            self.init_workspace()

            dialog.accept()
            if parent_dialog:
                parent_dialog.accept()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建项目失败: {e}")
            self.logger.error(f"创建项目失败: {e}")
    
    def open_recent_workspace_dialog(self, parent_dialog=None):
        """打开最近工作区对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("最近的项目")
        dialog.setMinimumWidth(550)
        dialog.setMinimumHeight(350)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title_label = QLabel("选择要打开的项目:")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(title_label)

        recent_list = QListWidget()
        recent_list.setStyleSheet("""
        QListWidget {
            border: 1px solid #dcdcdc;
            border-radius: 5px;
            padding: 5px;
            background-color: #f8f9fa;
        }
        QListWidget::item {
            padding: 8px;
            border-bottom: 1px solid #efefef;
        }
        QListWidget::item:selected {
            background-color: #e3f2fd;
            color: #1976d2;
        }
        QListWidget::item:hover {
            background-color: #f1f8fe;
        }
        """)
        
        valid_workspaces = []
        for workspace in self.preferences.get("Recent_Workspaces", []):
            if os.path.exists(workspace):
                valid_workspaces.append(workspace)
                recent_list.addItem(workspace)

        if not valid_workspaces:
            no_workspaces_label = QLabel("没有找到最近的工作区")
            no_workspaces_label.setAlignment(Qt.AlignCenter)
            no_workspaces_label.setStyleSheet("color: #7f8c8d; padding: 20px;")
            layout.addWidget(no_workspaces_label)
        else:
            layout.addWidget(recent_list)

            recent_list.itemDoubleClicked.connect(
                lambda: self.open_selected_workspace(recent_list, dialog, parent_dialog)
            )

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        open_btn = QPushButton("打开")
        open_btn.setMinimumWidth(100)
        open_btn.setStyleSheet("""
        QPushButton {
            background-color: #1976d2;
            color: white;
            border-radius: 4px;
            padding: 8px 15px;
        }
        QPushButton:hover {
            background-color: #1565c0;
        }
        QPushButton:disabled {
            background-color: #bbdefb;
            color: #e3f2fd;
        }
        """)
        open_btn.setEnabled(len(valid_workspaces) > 0)
        open_btn.clicked.connect(lambda: self.open_selected_workspace(recent_list, dialog, parent_dialog))
        button_layout.addWidget(open_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setStyleSheet("""
        QPushButton {
            background-color: #f5f5f5;
            border: 1px solid #dcdcdc;
            border-radius: 4px;
            padding: 8px 15px;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    def open_selected_workspace(self, list_widget, dialog, parent_dialog=None):
        """打开选中的工作区"""
        if not list_widget.currentItem():
            QMessageBox.warning(self, "警告", "请选择一个项目")
            return
            
        workspace_path = list_widget.currentItem().text()
        if not os.path.exists(workspace_path):
            QMessageBox.warning(self, "警告", f"项目路径不存在: {workspace_path}")
            return
            
        self.curWorkDir = workspace_path

        self.add_to_recent_workspaces(workspace_path)
        
        if self.curworkdir_is_workspace():
            self.init_workspace()
            dialog.accept()
            if parent_dialog:
                parent_dialog.accept()
        else:
            QMessageBox.warning(self, "警告", f"选择的目录不是有效的工作区: {workspace_path}")
    
    def add_to_recent_workspaces(self, workspace_path):
        """添加路径到最近工作区列表"""
        recent_workspaces = self.preferences.get("Recent_Workspaces", [])

        if workspace_path in recent_workspaces:
            recent_workspaces.remove(workspace_path)

        recent_workspaces.insert(0, workspace_path)

        recent_workspaces = recent_workspaces[:10]

        self.preferences["Recent_Workspaces"] = recent_workspaces
        self.save_preferences()

    def closeEvent(self, event):

        self.modify_preferences("Open_Last_Working_Directory", self.curWorkDir)

        if self.isWorkspace and self.curWorkDir:
            self.add_to_recent_workspaces(self.curWorkDir)

        self.save_preferences()

        auto_save = self.preferences.get("Auto_Save", True)

        if auto_save:

            if self.isWorkspace:
                self.save_window_position()
                self.save_last_workspace_data(skip_confirm=True)
            
            if self.curWorkFile is not None:

                if not self.get_component_by_name("Code Tab").curFileIsSave():
                    self.toolbar.save_file()
        else:

            if self.isWorkspace:
                self.check_and_save_curworkspace()
            elif self.curWorkFile is not None:
                self.check_and_save_curfile()
        
        event.accept()
        
    def save_window_position(self):
        """保存窗口位置和大小到工作区配置"""
        if not self.isWorkspace or not self.workspace_conf_path:
            return

        geo = self.geometry()
        self.modify_workspaceData("window/x", geo.x())
        self.modify_workspaceData("window/y", geo.y())
        self.modify_workspaceData("window/width", geo.width())
        self.modify_workspaceData("window/height", geo.height())

    def get_workspace_file(self, directory):

        if not os.path.isdir(directory):
            self.logger.error(f"目录不存在 {directory}")
            return None

        for file_name in os.listdir(directory):
            if file_name.endswith(".suan"):
                return file_name
        return None

    def curworkdir_is_workspace(self):
        if self.get_workspace_file(self.curWorkDir) == None:
            return False
        else:
            return True

    def init_workspace_data(self, file_name):
        self.workspace_conf_path = os.path.join(self.curWorkDir, file_name)
        self.workspaceData = self.load_workspace_data()

        try:
            user_config_dir = os.path.join(os.path.expanduser("~"), ".stk", "workspaces")
            os.makedirs(user_config_dir, exist_ok=True)

            workspace_id = self.curWorkDir.replace(":", "_").replace("\\", "_").replace("/", "_")
            backup_path = os.path.join(user_config_dir, f"{workspace_id}.suan.bak")

            with open(backup_path, "w") as backup_file:
                toml.dump(self.workspaceData, backup_file)
            self.logger.debug(f"已创建工作区配置备份: {backup_path}")
        except Exception as e:
            self.logger.error(f"创建工作区备份失败: {e}")

    def init_ui_from_workspace(self):

        width = self.get_workspace_data("window/width", 800)
        height = self.get_workspace_data("window/height", 500)
        x = self.get_workspace_data("window/x", 10)
        y = self.get_workspace_data("window/y", 10)

        if width < 400:
            width = 800
        if height < 300:
            height = 500

        screen = QApplication.primaryScreen().geometry()
        if x < 0 or x > screen.width() - 200:
            x = 10
        if y < 0 or y > screen.height() - 200:
            y = 10
        
        self.setGeometry(
            int(x),
            int(y),
            int(width),
            int(height),
        )

        try:
            if hasattr(self, 'left_sidebar'):
                self.left_sidebar.initWorkspace()
        except Exception as e:
            self.logger.error(f"初始化左侧栏失败: {e}")
        
        try:
            if hasattr(self, 'center_widget'):
                self.center_widget.initWorkspace()
        except Exception as e:
            self.logger.error(f"初始化中央窗口失败: {e}")

        try:
            if hasattr(self, 'info_bar'):
                self.info_bar.initWorkspace()
        except Exception as e:
            self.logger.error(f"初始化信息栏失败: {e}")

        self.setWindowTitle(f"STK - {os.path.basename(self.curWorkDir)}")

    def init_workspace(self):
        self.isWorkspace = True
        file_name = self.get_workspace_file(self.curWorkDir)
        self.init_workspace_data(file_name)
        self.init_ui_from_workspace()

        if self.cli_integrator is None:
            self.cli_integrator = CLIIntegrator(self)

        self.add_to_recent_workspaces(self.curWorkDir)

    def create_workspace_file(self, directory, file_to_copy):
        file_name = self.get_workspace_file(directory)

        dir_name = os.path.basename(directory)
        if self.isWorkspace:
            self.logger.info("目录下已存在.suan后缀的文件")
            return file_name
        else:

            new_file_name = dir_name + ".suan"
            destination = os.path.join(directory, new_file_name)
            
            try:

                if not os.path.exists(file_to_copy):

                    self.create_basic_workspace_file(destination, dir_name)
                else:

                    shutil.copy(file_to_copy, destination)
            
                self.logger.debug("已成功创建工作区文件: %s", new_file_name)

                self.backup_workspace_file(directory, destination)
            
                return new_file_name
            except Exception as e:
                self.logger.error(f"工作区文件操作失败: {e}")

                try:
                    self.create_basic_workspace_file(destination, dir_name)
                    return new_file_name
                except Exception as e2:
                    self.logger.error(f"创建基本工作区文件失败: {e2}")
                    return None

    def create_basic_workspace_file(self, file_path, dir_name):
        """创建一个基本的工作区文件"""
        basic_workspace = {
            "window": {
                "width": 800,
                "height": 600
            },
            "left_sidebar": {
                "working_directory": os.path.dirname(file_path)
            },
            "center_widget": {
                "active_tab_index": 0
            },
            "info_bar": {
                "code": {
                    "file_path": ""
                }
            }
        }
        
        with open(file_path, "w") as file:
            toml.dump(basic_workspace, file)
        self.logger.info(f"已创建基本工作区文件: {file_path}")

    def backup_workspace_file(self, directory, workspace_file):
        """备份工作区文件到用户配置目录"""
        try:
            user_config_dir = os.path.join(os.path.expanduser("~"), ".stk", "workspaces")
            os.makedirs(user_config_dir, exist_ok=True)

            workspace_id = directory.replace(":", "_").replace("\\", "_").replace("/", "_")
            backup_path = os.path.join(user_config_dir, f"{workspace_id}.suan.bak")

            if os.path.exists(workspace_file):
                shutil.copy(workspace_file, backup_path)
                self.logger.debug(f"已创建工作区配置备份: {backup_path}")
        except Exception as e:
            self.logger.error(f"备份工作区文件失败: {e}")

    def question_and_create_workspace(self, directory, is_init):
        reply = QMessageBox.question(
            self,
            "Warning",
            directory + " 目录下还未创建工作区，是否创建",
            QMessageBox.Yes,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            this_dir = os.path.dirname(os.path.abspath(__file__))
            self.create_workspace_file(
                directory,
                os.path.join(this_dir, get_resource_path("confs/workspace.suan")),
            )
            if is_init:
                self.init_workspace()

    def open_new_window(self):
        newWindow = MainWindow(False)
        newWindow.show()

    def cur_workspace_is_save(self):
        if self.load_workspace_data() != self.workspaceData:
            return False
        else:
            return True

    def check_and_save_curfile(self):

        auto_save = self.preferences.get("Auto_Save", True)

        if not self.get_component_by_name("Code Tab").curFileIsSave():
            if auto_save:

                self.logger.debug(f"自动保存文件: {self.curWorkFile}")
                self.toolbar.save_file()
                return True
            else:

                reply = QMessageBox.question(
                    self,
                    "Warning",
                    f"你还未保存文件:{self.curWorkFile}，是否保存",
                    QMessageBox.Yes,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self.toolbar.save_file()
        return False

    def check_and_save_curworkspace(self):

        self.check_and_save_curfile()

        auto_save = self.preferences.get("Auto_Save", True)
        
        if not self.cur_workspace_is_save():
            if auto_save:

                self.logger.debug(f"自动保存工作区: {self.curWorkDir}")
                self.save_last_workspace_data(skip_confirm=True)
                return True
            else:

                reply = QMessageBox.question(
                    self,
                    "Warning",
                    f"你还未保存工作区:{self.curWorkDir}，是否保存",
                    QMessageBox.Yes,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self.save_last_workspace_data()
                    return True
        return False

    def save_last_workspace_data(self, skip_confirm=False):
        if not self.isWorkspace or not self.workspace_conf_path:
            return
        
        try:

            geo = self.geometry()
            self.modify_workspaceData("window/x", geo.x())
            self.modify_workspaceData("window/y", geo.y())
            self.modify_workspaceData("window/width", geo.width())
            self.modify_workspaceData("window/height", geo.height())

            if hasattr(self, 'center_widget') and hasattr(self.center_widget, 'tabWidget'):
                self.modify_workspaceData(
                    "center_widget/active_tab_index",
                    self.center_widget.tabWidget.currentIndex(),
                )
            
            self.modify_workspaceData("left_sidebar/working_directory", self.curWorkDir)
            self.save_workspace()

            if hasattr(self, 'toolbar') and self.toolbar and self.curWorkFile:
                code_tab = self.get_component_by_name("Code Tab")
                if code_tab and not code_tab.curFileIsSave():
                    self.toolbar.save_file()
        except Exception as e:
            self.logger.error(f"保存工作区数据失败: {e}")

    def load_workspace_data(self):
        try:

            if not os.path.exists(self.workspace_conf_path):
                self.logger.error(f"工作区配置文件不存在: {self.workspace_conf_path}")
                return {}
            
            if not os.access(self.workspace_conf_path, os.R_OK):
                self.logger.error(f"工作区配置文件不可读: {self.workspace_conf_path}")

                return self.recover_workspace_from_backup()
            
            with open(self.workspace_conf_path, "r") as file:
                workspace_data = toml.load(file)

            workspace_data = self.validate_workspace_data(workspace_data)
            return workspace_data
        except (FileNotFoundError, toml.TomlDecodeError) as e:
            self.logger.error(f"加载工作区配置失败: {e}")

            return self.recover_workspace_from_backup()
        except Exception as e:
            self.logger.error(f"未预期的工作区配置加载错误: {e}")
            return {}

    def validate_workspace_data(self, workspace_data):
        """验证并填充缺失的工作区配置项"""

        if "window" not in workspace_data:
            workspace_data["window"] = {"width": 800, "height": 600}
        elif "width" not in workspace_data["window"] or "height" not in workspace_data["window"]:
            workspace_data["window"]["width"] = workspace_data["window"].get("width", 800)
            workspace_data["window"]["height"] = workspace_data["window"].get("height", 600)
        
        if "center_widget" not in workspace_data:
            workspace_data["center_widget"] = {"active_tab_index": 0}
        elif "active_tab_index" not in workspace_data["center_widget"]:
            workspace_data["center_widget"]["active_tab_index"] = 0
        
        if "left_sidebar" not in workspace_data:
            workspace_data["left_sidebar"] = {"working_directory": self.curWorkDir}
        elif "working_directory" not in workspace_data["left_sidebar"]:
            workspace_data["left_sidebar"]["working_directory"] = self.curWorkDir
        
        return workspace_data

    def recover_workspace_from_backup(self):
        """从备份恢复工作区配置"""
        try:

            user_config_dir = os.path.join(os.path.expanduser("~"), ".stk", "workspaces")
            workspace_id = self.curWorkDir.replace(":", "_").replace("\\", "_").replace("/", "_")
            backup_path = os.path.join(user_config_dir, f"{workspace_id}.suan.bak")
            
            if os.path.exists(backup_path) and os.access(backup_path, os.R_OK):
                self.logger.info(f"正在从备份恢复工作区配置: {backup_path}")
                with open(backup_path, "r") as file:
                    workspace_data = toml.load(file)
                return self.validate_workspace_data(workspace_data)
            else:
                self.logger.warning(f"工作区备份不存在或不可读: {backup_path}")

                return self.create_basic_workspace_data()
        except Exception as e:
            self.logger.error(f"从备份恢复工作区配置失败: {e}")
            return self.create_basic_workspace_data()

    def create_basic_workspace_data(self):
        """创建基本的工作区数据"""
        return {
            "window": {
                "width": 800,
                "height": 600
            },
            "left_sidebar": {
                "working_directory": self.curWorkDir
            },
            "center_widget": {
                "active_tab_index": 0
            },
            "info_bar": {
                "code": {
                    "file_path": ""
                }
            }
        }

    def save_workspace(self):
        if not self.workspace_conf_path:
            self.logger.error("未设置工作区配置路径")
            return
        
        try:

            temp_path = self.workspace_conf_path + ".tmp"
            with open(temp_path, "w") as file:
                toml.dump(self.workspaceData, file)

            import os
            if os.path.exists(self.workspace_conf_path):
                os.replace(temp_path, self.workspace_conf_path)
            else:
                os.rename(temp_path, self.workspace_conf_path)

            try:
                user_config_dir = os.path.join(os.path.expanduser("~"), ".stk", "workspaces")
                os.makedirs(user_config_dir, exist_ok=True)
                
                workspace_id = self.curWorkDir.replace(":", "_").replace("\\", "_").replace("/", "_")
                backup_path = os.path.join(user_config_dir, f"{workspace_id}.suan.bak")
                
                with open(backup_path, "w") as backup_file:
                    toml.dump(self.workspaceData, backup_file)
            except Exception as e:
                self.logger.error(f"更新工作区备份失败: {e}")
        except Exception as e:
            self.logger.error(f"保存工作区失败: {e}")

    def modify_workspaceData(self, path, value):
        parts = path.split("/")
        data = self.workspaceData
        for part in parts[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]
        data[parts[-1]] = value
        self.logger.debug(self.workspaceData)

    def get_workspace_data(self, path, default_value=None):
        parts = path.split("/")
        data = self.workspaceData
        
        for part in parts[:-1]:
            if part not in data:
                if default_value is not None:
                    return default_value
                data[part] = {}
            data = data[part]
        
        if parts[-1] not in data and default_value is not None:
            return default_value
        
        return data.get(parts[-1], default_value)

    def init_preferences(self):

        user_config_dir = os.path.join(os.path.expanduser("~"), ".stk")
        os.makedirs(user_config_dir, exist_ok=True)

        this_dir = os.path.dirname(os.path.abspath(__file__))
        default_preference_path = os.path.join(
            this_dir, get_resource_path("confs/preference.toml")
        )

        self.preference_toml_path = os.path.join(user_config_dir, "preference.toml")

        first_launch = not os.path.exists(self.preference_toml_path)

        if first_launch:
            try:

                if os.path.exists(default_preference_path):
                    shutil.copy(default_preference_path, self.preference_toml_path)
                    self.logger.info(f"已从默认配置创建用户配置文件: {self.preference_toml_path}")
                else:

                    self.create_default_preferences()
                    self.logger.info(f"已创建基本用户配置文件: {self.preference_toml_path}")
            except Exception as e:
                self.logger.error(f"创建用户配置文件失败: {e}")

                self.preferences = self.get_default_preferences()
                self.is_first_launch = True
                return

        self.preferences = self.load_preferences()

        self.is_first_launch = self.preferences.get("First_Launch", first_launch)
        if self.is_first_launch:
            self.preferences["First_Launch"] = False
            self.save_preferences()

        self.update_path_for_current_os()
        
        self.curWorkDir = self.preferences.get("Open_Last_Working_Directory", os.path.expanduser("~"))
        self.logger.debug("curWorkDir:%s", self.curWorkDir)

    def update_path_for_current_os(self):
        """更新配置中的路径，适应当前操作系统"""

        if "Open_Last_Working_Directory" in self.preferences:
            path = self.preferences["Open_Last_Working_Directory"]

            if path and (not os.path.exists(path) or not os.access(path, os.R_OK)):
                self.preferences["Open_Last_Working_Directory"] = os.path.expanduser("~")
                self.logger.warning(f"工作目录路径 {path} 不可访问，已重置为用户主目录")

    def create_default_preferences(self):
        """创建默认配置文件"""
        default_prefs = self.get_default_preferences()
        
        try:
            with open(self.preference_toml_path, "w") as file:
                toml.dump(default_prefs, file)
        except Exception as e:
            self.logger.error(f"写入默认配置文件失败: {e}")

    def get_default_preferences(self):
        """获取默认配置"""

        home_dir = os.path.expanduser("~")

        default_prefs = {
            "Default_Location": "Home",
            "Open_Last_Workspace": True,
            "Open_Last_Working_Directory": home_dir,
            "Recent_Workspaces": [],  # 新增：记录最近使用的工作区
            "First_Launch": True,     # 新增：标记是否首次启动
            "Auto_Save": True,        # 新增：自动保存选项
            "UI_Init": {
                "window_width": "800",
                "window_height": "500",
                "left_sidebar_width": "100",
                "right_sidebar_width": "100",
                "center_widget_height": "300"
            },
            "UI_Component_Visibility_Init": {
                "Info": {
                    "Log_Tab": True,
                    "Console_Tab": True,
                    "Status_Information": True
                },
                "Visualization_window": {
                    "VTK_Visualization_Tab": True,
                    "Matplotlib_Display_Tab": True,
                    "Data_Table_Tab": True,
                    "Code_Tab": True,
                    "AI_Tab": True
                },
                "Tool": {
                    "Open": True,
                    "Save": True,
                    "View": True,
                    "Help": True
                },
                "Other": {
                    "File_structure": True,
                    "Status": True,
                    "Statusbar": True
                }
            }
        }
        
        return default_prefs

    def load_preferences(self):
        try:
            with open(
                self.preference_toml_path,
                "r",
            ) as file:
                preferences = toml.load(file)

            preferences = self.validate_preferences(preferences)
        except (FileNotFoundError, toml.TomlDecodeError) as e:
            self.logger.error(f"加载配置文件错误: {e}")

            preferences = self.get_default_preferences()
        except Exception as e:
            self.logger.error(f"未预期的配置加载错误: {e}")
            preferences = self.get_default_preferences()
        
        return preferences

    def validate_preferences(self, preferences):
        """验证并修复配置中缺失的必要设置"""
        default_prefs = self.get_default_preferences()

        for key in default_prefs:
            if key not in preferences:
                preferences[key] = default_prefs[key]

        if "UI_Init" not in preferences:
            preferences["UI_Init"] = default_prefs["UI_Init"]
        else:
            for key in default_prefs["UI_Init"]:
                if key not in preferences["UI_Init"]:
                    preferences["UI_Init"][key] = default_prefs["UI_Init"][key]

        if "UI_Component_Visibility_Init" not in preferences:
            preferences["UI_Component_Visibility_Init"] = default_prefs["UI_Component_Visibility_Init"]
        else:
            for category in default_prefs["UI_Component_Visibility_Init"]:
                if category not in preferences["UI_Component_Visibility_Init"]:
                    preferences["UI_Component_Visibility_Init"][category] = default_prefs["UI_Component_Visibility_Init"][category]
                else:
                    for component in default_prefs["UI_Component_Visibility_Init"][category]:
                        if component not in preferences["UI_Component_Visibility_Init"][category]:
                            preferences["UI_Component_Visibility_Init"][category][component] = default_prefs["UI_Component_Visibility_Init"][category][component]
        
        return preferences

    def modify_preferences(self, path, value):
        if not path or not isinstance(path, str):
            self.logger.error(f"Invalid path: {path}")
            return
        
        parts = path.split("/")
        data = self.preferences
        
        for part in parts[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]
        
        data[parts[-1]] = value

    def save_preferences(self):
        try:

            temp_path = self.preference_toml_path + ".tmp"
            with open(temp_path, "w") as file:
                toml.dump(self.preferences, file)

            import os
            if os.path.exists(self.preference_toml_path):
                os.replace(temp_path, self.preference_toml_path)
            else:
                os.rename(temp_path, self.preference_toml_path)
        except Exception as e:
            self.logger.error(f"保存配置失败: {e}")

    def fixCurFilePath(self, path):
        self.toolbar.current_open_file = path

    def compare_versions(self, version1, version2):
        if version1 == "":
            return -1
        if version2 == "":
            return 1
        v1_parts = list(map(int, version1.split(".")))
        v2_parts = list(map(int, version2.split(".")))

        while len(v1_parts) < len(v2_parts):
            v1_parts.append(0)
        while len(v2_parts) < len(v1_parts):
            v2_parts.append(0)

        for part1, part2 in zip(v1_parts, v2_parts):
            if part1 < part2:
                return -1
            elif part1 > part2:
                return 1

        return 0

    def registerComponent(self, path, component, isVisible):
        """按路径注册组件,根组件为main"""
        parts = path.split("/")
        current_level = self.components["main"]["children"]  # 从根组件的子组件开始搜索

        for part in parts[:-1]:
            current_level = current_level.setdefault(part, {}).setdefault(
                "children", {}
            )  # 确保每个组件都有一个 'children' 字典

        current_level[parts[-1]] = {
            "component": component,
            "children": {},
            "isVisible": isVisible,
        }  # 在路径的最后一个部分中添加组件
        self.logger.debug("registerComponent %s ", path)

    def unregisterComponent(self, path):
        """按路径取消注册组件,根组件为main"""
        parts = path.split("/")
        father_level = self.components["main"]["children"]  # 从根组件的子组件开始搜索
        component_name = parts[-1]
        for part in parts[:-2]:
            father_level = father_level.setdefault(part, {}).setdefault("children", {})
        current_level = father_level.setdefault(parts[-1], {}).setdefault(
            "children", {}
        )
        if component_name in current_level:

            if "Tab" in component_name:
                father_level["component"].toggleComponentVisibility(component_name)
            current_level.pop(parts[-1])
            self.logger.debug("unregisterComponent %s", path)

    def toggleComponentVisibility(self, path):
        self.logger.debug(path)
        """切换组件的可见性."""
        parts = path.split("/")
        current_level = self.components["main"]["children"]  # 从根组件的子组件开始搜索
        component_name = parts[-1]

        if "Tab" in component_name:
            for part in parts[:-1]:
                current_level = current_level[part]  # 移动到下一个层级的子组件

            current_level["component"].toggleComponentVisibility(component_name)

            self.logger.debug("toggleComponentVisibility %s", path)
            return

        for part in parts[:-1]:
            current_level = current_level[part]["children"]  # 移动到下一个层级的子组件
        component = current_level[component_name]["component"]  # 获取要切换可见性的组件
        component.setVisible(not component.isVisible())  # 切换组件的可见性
        current_level[component_name]["isVisible"] = not current_level[component_name][
            "isVisible"
        ]
        self.logger.debug(
            "toggleComponentVisibility %s:%s", path, component.isVisible()
        )

    def componentIsVisible(self, path):
        """判断组件是否可见."""
        parts = path.split("/")
        current_level = self.components["main"]["children"]  # 从根组件的子组件开始搜索
        component_name = parts[-1]
        for part in parts[:-1]:
            current_level = current_level[part]["children"]  # 移动到下一个层级的子组件
        return current_level[component_name]["isVisible"]

    def get_component_by_path(self, path):
        parts = path.split("/")
        current_level = self.components["main"]["children"]  # 从根组件的子组件开始搜索
        component_name = parts[-1]
        for part in parts[:-1]:
            current_level = current_level[part]["children"]  # 移动到下一个层级的子组件
        return current_level[component_name]["component"]

    def get_component_by_name(self, name):

        def search_component(current_level):
            for key, value in current_level.items():

                if key == name:
                    return value["component"]

                if "children" in value:
                    result = search_component(value["children"])
                    if result:  # 如果子组件中找到了匹配项，返回该组件
                        return result
            return None

        return search_component(self.components["main"]["children"])

    def check_update_callback(self, data):
        new_version = data["版本号"]
        release_time = data["发布时间"]
        if self.compare_versions(new_version, cur_version) == 1:
            self.logger.debug("SHOW update")
            self.show_update_window()

    def check_update(self):
        self.check_update_thread = Updater.check_update_thread(
            updatejson_url, self.check_update_callback
        )
        self.check_update_thread.start()

    def show_update_window(self):
        if self.updateWindow is None:
            self.updateWindow = Updater.UpdateWindow(
                updatejson_url, app_name, cur_version, code_url
            )
        self.updateWindow.show()


def load_qss(qss_file_path):
    """
    加载 QSS 文件内容
    """
    with open(qss_file_path, "r", encoding="gbk", errors="ignore") as file:
        return file.read()


def scale_qss_font_size(qss, scale_factor):
    """
    根据缩放因子动态调整 QSS 字体大小
    :param qss: 原始 QSS 字符串
    :param scale_factor: 缩放因子
    :return: 调整后的 QSS
    """

    def adjust_font_size(match):
        size = int(match.group(1))  # 提取 font-size 的数值部分
        scaled_size = int(size * scale_factor)  # 乘以缩放因子
        return f"font-size: {scaled_size}px;"

    scaled_qss = re.sub(r"font-size:\s*(\d+)px;", adjust_font_size, qss)
    return scaled_qss


def apply_qss(app, qss):
    """
    应用 QSS 样式
    """
    app.setStyleSheet(qss)


def get_resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def check_resource():
    current_path = os.path.dirname(os.path.abspath(__file__))

    subdirs = ["confs", "examples", "resources", "icons"]

    for subdir in subdirs:
        dir_path = os.path.join(current_path, get_resource_path(subdir))
        print(f"\n目录: {dir_path}")

        if os.path.exists(dir_path) and os.path.isdir(dir_path):

            items = os.listdir(dir_path)
            if items:
                print("包含以下内容:")
                for item in items:
                    print(f"  - {item}")
            else:
                print("目录为空。")
        else:
            print("目录不存在。")


def ensure_config_directories():
    """确保所有配置目录都存在且可访问"""
    user_home = os.path.expanduser("~")

    config_dirs = [
        os.path.join(user_home, ".stk"),
        os.path.join(user_home, ".stk", "workspaces"),
        os.path.join(user_home, ".stk", "logs"),
        os.path.join(user_home, ".stk", "cache"),
        os.path.join(user_home, ".stk", "temp"),
    ]
    
    success = True
    for directory in config_dirs:
        try:

            os.makedirs(directory, exist_ok=True)

            if not os.access(directory, os.W_OK):
                print(f"警告: 配置目录不可写 {directory}")
                if sys.platform == "win32":

                    try:
                        import stat
                        os.chmod(directory, stat.S_IWRITE)
                        print(f"已尝试修改目录权限: {directory}")
                    except Exception as e:
                        print(f"修改目录权限失败: {e}")
                        success = False
                else:

                    print(f"请使用 'chmod u+w {directory}' 命令修改权限")
                    success = False
                    
        except Exception as e:
            print(f"无法创建配置目录 {directory}: {e}")
            success = False

    check_system_compatibility()
    
    return success

def check_system_compatibility():
    """检查系统兼容性并进行必要的调整"""
    system = sys.platform
    
    if system == "win32":

        try:

            temp_dir = os.environ.get("TEMP")
            if temp_dir and not os.access(temp_dir, os.W_OK):
                print(f"警告: Windows临时目录不可写: {temp_dir}")

                user_temp = os.path.join(os.path.expanduser("~"), ".stk", "temp")
                os.environ["TEMP"] = user_temp
                print(f"已将临时目录重定向到: {user_temp}")
        except Exception as e:
            print(f"Windows系统兼容性检查失败: {e}")
    
    elif system == "linux":

        try:

            if "XDG_CONFIG_HOME" not in os.environ:
                xdg_config = os.path.join(os.path.expanduser("~"), ".config")
                os.environ["XDG_CONFIG_HOME"] = xdg_config
                print(f"已设置XDG_CONFIG_HOME为: {xdg_config}")
        except Exception as e:
            print(f"Linux系统兼容性检查失败: {e}")
    
    elif system == "darwin":

        try:

            app_support = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "STK")
            os.makedirs(app_support, exist_ok=True)
        except Exception as e:
            print(f"MacOS系统兼容性检查失败: {e}")

    try:

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".tmp", prefix="stk_", delete=True) as tmp:
            pass  # 测试临时文件创建
    except Exception as e:
        print(f"临时文件创建测试失败: {e}")

        user_temp = os.path.join(os.path.expanduser("~"), ".stk", "temp")
        tempfile.tempdir = user_temp
        print(f"已将Python临时文件目录重定向到: {user_temp}")

if __name__ == "__main__":

    if not ensure_config_directories():
        print("警告: 配置目录设置不完整，应用程序可能无法正常工作")

    app = QApplication(sys.argv)
    check_resource()

    screen = app.primaryScreen()
    dpi = screen.logicalDotsPerInch()
    scale_factor = dpi / 96.0  # 96 为标准 DPI

    qss_file_path = get_resource_path("resources/styles.qss")
    qss = load_qss(qss_file_path)

    scaled_qss = scale_qss_font_size(qss, scale_factor)

    apply_qss(app, scaled_qss)
    mainWindow = MainWindow(True)
    mainWindow.show()

    sys.exit(app.exec())
