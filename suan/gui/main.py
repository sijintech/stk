import os
import sys

# 在导入其他模块前设置 DPI 感知
# 解决 "qt.qpa.window: SetProcessDpiAwarenessContext..." 警告
if sys.platform == "win32":
    try:
        from ctypes import windll

        # 使用 SetProcessDpiAwareness 替代 SetProcessDpiAwarenessContext
        # 0 = 不感知, 1 = 系统感知, 2 = 每显示器感知
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
        
        # 初始化关键数据和状态
        self.curWorkDir = None
        self.curWorkFile = None
        self.workspace_conf_path = None
        self.workspaceData = {}
        self.preferences = None
        self.isWorkspace = False
        self.is_first_launch = False
        self.create_workspace_if_no = create_workspace_if_no
        self.window_initialized = False
        # 先初始化首选项
        self.init_preferences()
        
        # 用于存储具有层级关系的组件
        self.components = {"main": {"name": "main", "component": self, "children": {}}}
        
        # 初始化UI组件
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

        # 初始化UI和其他系统
        self.init_ui()
        self.check_update()

    def init_ui(self):
        # 设置主窗口标题
        self.setWindowTitle("STK")
        # 使用QSplitter将中心部件和信息栏包裹起来
        self.center_splitter.setOrientation(Qt.Vertical)
        self.center_splitter.addWidget(self.center_widget)
        self.center_splitter.addWidget(self.info_bar)
        # self.center_splitter.setHandleWidth(2)  # 设置分割线的宽度
        # 使用另一个QSplitter将左，右侧栏和中心部件包裹起来
        self.main_splitter.addWidget(self.left_sidebar)
        self.main_splitter.addWidget(self.center_splitter)
        self.main_splitter.addWidget(self.right_sidebar)
        # 创建主窗口布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.main_splitter)

        # 创建主窗口中心部件
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        # 将顶部工具栏和底部状态栏添加到主窗口
        # self.addToolBar(self.toolbar)
        self.setStatusBar(self.status_bar)

        self.left_sidebar.openFilePath.connect(self.fixCurFilePath)

        #  根据preference_toml设置组件UI setSizes
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

    def showEvent(self, event):
        self.logger.debug("showEvent")
        super().showEvent(event)
        if self.window_initialized:
            return
        # 检查是否是首次启动
        if self.is_first_launch:
            self.show_welcome_dialog()
            return
            
        # 非首次启动逻辑
        # 1. 尝试打开上次的工作区
        if self.preferences.get("Open_Last_Workspace", True) and self.preferences.get("Recent_Workspaces", []):
            # 首先尝试打开最近的工作区
            recent_workspaces = self.preferences.get("Recent_Workspaces", [])
            if recent_workspaces and os.path.exists(recent_workspaces[0]):
                self.curWorkDir = recent_workspaces[0]
                if self.curworkdir_is_workspace():
                    self.init_workspace()
                    return
            
            # 如果最近的工作区不可用，尝试其他工作区
            for workspace_path in recent_workspaces[1:]:
                if os.path.exists(workspace_path):
                    self.curWorkDir = workspace_path
                    if self.curworkdir_is_workspace():
                        self.init_workspace()
                        return
            
        # 2. 如果没有可用的工作区，但有上次的工作目录
        if self.curWorkDir and os.path.exists(self.curWorkDir):
            if self.create_workspace_if_no:
                self.question_and_create_workspace(self.curWorkDir, True)
            else:
                # 设置主窗口大小和显示
                self.setGeometry(
                    50,
                    50,
                    int(self.preferences["UI_Init"]["window_width"]),
                    int(self.preferences["UI_Init"]["window_height"]),
                )
        else:
            # 3. 如果没有有效的工作目录，显示欢迎界面
            self.show_welcome_dialog()
            
    def show_welcome_dialog(self):
        """显示欢迎对话框，让用户选择打开文件夹或创建新项目"""
        dialog = QDialog(self)
        dialog.setWindowTitle("欢迎使用STK")
        dialog.setMinimumWidth(650)
        dialog.setMinimumHeight(400)
        
        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # 顶部区域 - 标题和说明
        top_section = QVBoxLayout()
        
        # 添加标题
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        
        title_label = QLabel("欢迎使用STK")
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignCenter)
        top_section.addWidget(title_label)
        
        # 添加说明文本
        desc_label = QLabel("选择一个选项开始您的工作")
        desc_label.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        desc_label.setAlignment(Qt.AlignCenter)
        top_section.addWidget(desc_label)
        
        main_layout.addLayout(top_section)
        
        # 中部区域 - 操作按钮
        middle_section = QHBoxLayout()
        middle_section.setSpacing(15)
        
        # 设置按钮样式
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
        
        # 打开文件夹卡片
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
        
        # 创建新项目卡片
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
        
        # 仅当有最近项目时才显示
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
        
        # 底部区域 - 额外选项
        bottom_section = QHBoxLayout()
        
        # 跳过按钮 - 在右边
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
        
        # 对话框关闭后，设置默认窗口大小
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
            # 更新最近工作区列表
            self.add_to_recent_workspaces(folder_path)
            
            if self.curworkdir_is_workspace():
                self.init_workspace()
            else:
                self.question_and_create_workspace(folder_path, True)
                
            # 关闭父对话框(如果有)
            if parent_dialog:
                parent_dialog.accept()
    
    def create_new_project_dialog(self, parent_dialog=None):
        """创建新项目对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("创建新项目")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # 项目名称
        project_name_edit = QLineEdit()
        form_layout.addRow("项目名称:", project_name_edit)
        
        # 项目位置
        location_layout = QHBoxLayout()
        location_edit = QLineEdit(os.path.expanduser("~"))
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(lambda: self.browse_project_location(location_edit))
        location_layout.addWidget(location_edit)
        location_layout.addWidget(browse_btn)
        form_layout.addRow("项目位置:", location_layout)
        
        layout.addLayout(form_layout)
        
        # 按钮区域
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
            
        # 创建项目目录
        project_path = os.path.join(location, project_name)
        if os.path.exists(project_path):
            QMessageBox.warning(self, "错误", f"项目目录已存在: {project_path}")
            return
            
        try:
            os.makedirs(project_path, exist_ok=True)
            self.logger.info(f"已创建项目目录: {project_path}")
            
            # 设置当前工作目录
            self.curWorkDir = project_path
            # 更新最近工作区列表
            self.add_to_recent_workspaces(project_path)
            
            # 创建工作区文件
            this_dir = os.path.dirname(os.path.abspath(__file__))
            workspace_template = os.path.join(this_dir, get_resource_path("confs/workspace.suan"))
            self.create_workspace_file(project_path, workspace_template)
            
            # 初始化工作区
            self.init_workspace()
            
            # 关闭对话框
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
        
        # 添加说明
        title_label = QLabel("选择要打开的项目:")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(title_label)
        
        # 最近工作区列表
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
        
        # 如果没有有效的工作区，显示提示
        if not valid_workspaces:
            no_workspaces_label = QLabel("没有找到最近的工作区")
            no_workspaces_label.setAlignment(Qt.AlignCenter)
            no_workspaces_label.setStyleSheet("color: #7f8c8d; padding: 20px;")
            layout.addWidget(no_workspaces_label)
        else:
            layout.addWidget(recent_list)
            # 双击打开
            recent_list.itemDoubleClicked.connect(
                lambda: self.open_selected_workspace(recent_list, dialog, parent_dialog)
            )
        
        # 按钮区域
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
        # 更新最近工作区列表（将此工作区移到列表首位）
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
        
        # 如果已存在，移除旧的条目
        if workspace_path in recent_workspaces:
            recent_workspaces.remove(workspace_path)
            
        # 添加到列表开头
        recent_workspaces.insert(0, workspace_path)
        
        # 保持列表不超过10个条目
        recent_workspaces = recent_workspaces[:10]
        
        # 更新配置
        self.preferences["Recent_Workspaces"] = recent_workspaces
        self.save_preferences()

    def closeEvent(self, event):
        # 保存当前的工作目录到偏好设置
        self.modify_preferences("Open_Last_Working_Directory", self.curWorkDir)
        
        # 如果当前目录是工作区，将其添加到最近工作区列表
        if self.isWorkspace and self.curWorkDir:
            self.add_to_recent_workspaces(self.curWorkDir)
        
        # 保存偏好设置
        self.save_preferences()
        
        # 检查自动保存选项
        auto_save = self.preferences.get("Auto_Save", True)
        
        # 处理未保存的工作区和文件
        if auto_save:
            # 自动保存模式：直接保存所有内容
            if self.isWorkspace:
                # 保存窗口位置和其他信息到工作区文件
                self.save_window_position()
                self.save_last_workspace_data(skip_confirm=True)
            
            if self.curWorkFile is not None:
                # 检查文件是否被修改，如果被修改则保存
                if not self.get_component_by_name("Code Tab").curFileIsSave():
                    self.toolbar.save_file()
        else:
            # 手动保存模式：询问用户是否保存
            if self.isWorkspace:
                self.check_and_save_curworkspace()
            elif self.curWorkFile is not None:
                self.check_and_save_curfile()
        
        event.accept()
        
    def save_window_position(self):
        """保存窗口位置和大小到工作区配置"""
        if not self.isWorkspace or not self.workspace_conf_path:
            return
            
        # 保存窗口位置
        geo = self.geometry()
        self.modify_workspaceData("window/x", geo.x())
        self.modify_workspaceData("window/y", geo.y())
        self.modify_workspaceData("window/width", geo.width())
        self.modify_workspaceData("window/height", geo.height())

    def get_workspace_file(self, directory):
        # 判断目录是否存在
        if not os.path.isdir(directory):
            self.logger.error(f"目录不存在 {directory}")
            return None

        # 检查目录下是否有.suan后缀的文件
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
        
        # 创建工作区配置的备份到用户目录
        try:
            user_config_dir = os.path.join(os.path.expanduser("~"), ".stk", "workspaces")
            os.makedirs(user_config_dir, exist_ok=True)
            
            # 使用工作区目录路径作为标识，创建唯一的备份文件名
            workspace_id = self.curWorkDir.replace(":", "_").replace("\\", "_").replace("/", "_")
            backup_path = os.path.join(user_config_dir, f"{workspace_id}.suan.bak")
            
            # 保存工作区配置的备份
            with open(backup_path, "w") as backup_file:
                toml.dump(self.workspaceData, backup_file)
            self.logger.debug(f"已创建工作区配置备份: {backup_path}")
        except Exception as e:
            self.logger.error(f"创建工作区备份失败: {e}")

    def init_ui_from_workspace(self):
        # 尝试从工作区配置中获取窗口大小和位置，如果不存在则使用默认值
        width = self.get_workspace_data("window/width", 800)
        height = self.get_workspace_data("window/height", 500)
        x = self.get_workspace_data("window/x", 10)
        y = self.get_workspace_data("window/y", 10)
        
        # 确保窗口大小合理
        if width < 400:
            width = 800
        if height < 300:
            height = 500
        
        # 确保窗口位置在屏幕内
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
        
        # 初始化各个组件
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
        
        # 记录工作区路径到窗口标题
        self.setWindowTitle(f"STK - {os.path.basename(self.curWorkDir)}")

    def init_workspace(self):
        self.isWorkspace = True
        file_name = self.get_workspace_file(self.curWorkDir)
        self.init_workspace_data(file_name)
        self.init_ui_from_workspace()
        
        # 将当前工作区添加到最近工作区列表
        self.add_to_recent_workspaces(self.curWorkDir)

    def create_workspace_file(self, directory, file_to_copy):
        file_name = self.get_workspace_file(directory)
        # 获取目录名
        dir_name = os.path.basename(directory)
        if self.isWorkspace:
            self.logger.info("目录下已存在.suan后缀的文件")
            return file_name
        else:
            # 复制文件到目录下，并重命名为目录名+".suan"
            new_file_name = dir_name + ".suan"
            destination = os.path.join(directory, new_file_name)
            
            try:
                # 检查源文件是否存在
                if not os.path.exists(file_to_copy):
                    # 源模板文件不存在，创建一个基本的工作区文件
                    self.create_basic_workspace_file(destination, dir_name)
                else:
                    # 复制模板文件
                    shutil.copy(file_to_copy, destination)
            
                self.logger.debug("已成功创建工作区文件: %s", new_file_name)
            
                # 同时在用户配置目录创建备份
                self.backup_workspace_file(directory, destination)
            
                return new_file_name
            except Exception as e:
                self.logger.error(f"工作区文件操作失败: {e}")
                # 尝试直接创建一个基本的工作区文件
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
            
            # 创建唯一的标识
            workspace_id = directory.replace(":", "_").replace("\\", "_").replace("/", "_")
            backup_path = os.path.join(user_config_dir, f"{workspace_id}.suan.bak")
            
            # 如果源文件存在则复制
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
        # 检查是否开启了自动保存
        auto_save = self.preferences.get("Auto_Save", True)
        
        # 检查文件是否被修改
        if not self.get_component_by_name("Code Tab").curFileIsSave():
            if auto_save:
                # 自动保存模式：直接保存文件
                self.logger.debug(f"自动保存文件: {self.curWorkFile}")
                self.toolbar.save_file()
                return True
            else:
                # 手动保存模式：询问用户是否保存
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
        # 先检查并保存当前文件
        self.check_and_save_curfile()
        
        # 检查是否开启了自动保存
        auto_save = self.preferences.get("Auto_Save", True)
        
        if not self.cur_workspace_is_save():
            if auto_save:
                # 自动保存模式：直接保存工作区
                self.logger.debug(f"自动保存工作区: {self.curWorkDir}")
                self.save_last_workspace_data(skip_confirm=True)
                return True
            else:
                # 手动保存模式：询问用户是否保存
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
            # 保存窗口位置和大小
            geo = self.geometry()
            self.modify_workspaceData("window/x", geo.x())
            self.modify_workspaceData("window/y", geo.y())
            self.modify_workspaceData("window/width", geo.width())
            self.modify_workspaceData("window/height", geo.height())
            
            # 只有当center_widget组件存在且有tabWidget属性时才保存
            if hasattr(self, 'center_widget') and hasattr(self.center_widget, 'tabWidget'):
                self.modify_workspaceData(
                    "center_widget/active_tab_index",
                    self.center_widget.tabWidget.currentIndex(),
                )
            
            self.modify_workspaceData("left_sidebar/working_directory", self.curWorkDir)
            self.save_workspace()
            
            # 只有工具栏存在且文件被修改时才保存文件
            if hasattr(self, 'toolbar') and self.toolbar and self.curWorkFile:
                code_tab = self.get_component_by_name("Code Tab")
                if code_tab and not code_tab.curFileIsSave():
                    self.toolbar.save_file()
        except Exception as e:
            self.logger.error(f"保存工作区数据失败: {e}")

    def load_workspace_data(self):
        try:
            # 检查文件是否存在且可读
            if not os.path.exists(self.workspace_conf_path):
                self.logger.error(f"工作区配置文件不存在: {self.workspace_conf_path}")
                return {}
            
            if not os.access(self.workspace_conf_path, os.R_OK):
                self.logger.error(f"工作区配置文件不可读: {self.workspace_conf_path}")
                # 尝试从备份恢复
                return self.recover_workspace_from_backup()
            
            with open(self.workspace_conf_path, "r") as file:
                workspace_data = toml.load(file)
            
            # 验证加载的数据
            workspace_data = self.validate_workspace_data(workspace_data)
            return workspace_data
        except (FileNotFoundError, toml.TomlDecodeError) as e:
            self.logger.error(f"加载工作区配置失败: {e}")
            # 尝试从备份恢复
            return self.recover_workspace_from_backup()
        except Exception as e:
            self.logger.error(f"未预期的工作区配置加载错误: {e}")
            return {}

    def validate_workspace_data(self, workspace_data):
        """验证并填充缺失的工作区配置项"""
        # 确保必要的节点存在
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
            # 尝试从备份目录恢复
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
                # 返回基本配置
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
            # 创建临时文件，成功后再重命名，避免写入失败导致配置丢失
            temp_path = self.workspace_conf_path + ".tmp"
            with open(temp_path, "w") as file:
                toml.dump(self.workspaceData, file)
            
            # 替换原文件
            import os
            if os.path.exists(self.workspace_conf_path):
                os.replace(temp_path, self.workspace_conf_path)
            else:
                os.rename(temp_path, self.workspace_conf_path)
            
            # 同时更新工作区配置的备份
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
        # 确保用户配置目录存在
        user_config_dir = os.path.join(os.path.expanduser("~"), ".stk")
        os.makedirs(user_config_dir, exist_ok=True)
        
        # 获取程序目录中的默认配置文件路径
        this_dir = os.path.dirname(os.path.abspath(__file__))
        default_preference_path = os.path.join(
            this_dir, get_resource_path("confs/preference.toml")
        )
        
        # 用户配置文件路径设置在用户主目录下
        self.preference_toml_path = os.path.join(user_config_dir, "preference.toml")
        
        # 检查是否首次启动
        first_launch = not os.path.exists(self.preference_toml_path)
        
        # 如果用户配置文件不存在，则生成一个新的配置文件
        if first_launch:
            try:
                # 尝试从默认配置复制
                if os.path.exists(default_preference_path):
                    shutil.copy(default_preference_path, self.preference_toml_path)
                    self.logger.info(f"已从默认配置创建用户配置文件: {self.preference_toml_path}")
                else:
                    # 如果默认配置不存在，则创建一个基本配置
                    self.create_default_preferences()
                    self.logger.info(f"已创建基本用户配置文件: {self.preference_toml_path}")
            except Exception as e:
                self.logger.error(f"创建用户配置文件失败: {e}")
                # 创建失败时，使用内存中的默认配置
                self.preferences = self.get_default_preferences()
                self.is_first_launch = True
                return
        
        # 使用缓存机制加载配置文件
        self.preferences = self.load_preferences()
        
        # 设置首次启动标志
        self.is_first_launch = self.preferences.get("First_Launch", first_launch)
        if self.is_first_launch:
            # 更新首次启动标志，下次启动时不再视为首次启动
            self.preferences["First_Launch"] = False
            self.save_preferences()
        
        # 适应不同操作系统的路径表示方式
        self.update_path_for_current_os()
        
        self.curWorkDir = self.preferences.get("Open_Last_Working_Directory", os.path.expanduser("~"))
        self.logger.debug("curWorkDir:%s", self.curWorkDir)

    def update_path_for_current_os(self):
        """更新配置中的路径，适应当前操作系统"""
        # 确保工作目录路径格式适应当前系统
        if "Open_Last_Working_Directory" in self.preferences:
            path = self.preferences["Open_Last_Working_Directory"]
            # 如果路径存在但不可访问，则使用用户主目录
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
        # 根据当前操作系统设置合适的默认路径
        home_dir = os.path.expanduser("~")
        
        # 创建基本的默认配置
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
            
            # 验证加载的配置文件，确保包含必要的设置
            preferences = self.validate_preferences(preferences)
        except (FileNotFoundError, toml.TomlDecodeError) as e:
            self.logger.error(f"加载配置文件错误: {e}")
            # 提供默认配置
            preferences = self.get_default_preferences()
        except Exception as e:
            self.logger.error(f"未预期的配置加载错误: {e}")
            preferences = self.get_default_preferences()
        
        return preferences

    def validate_preferences(self, preferences):
        """验证并修复配置中缺失的必要设置"""
        default_prefs = self.get_default_preferences()
        
        # 确保一级配置项存在
        for key in default_prefs:
            if key not in preferences:
                preferences[key] = default_prefs[key]
        
        # 确保UI_Init配置存在且完整
        if "UI_Init" not in preferences:
            preferences["UI_Init"] = default_prefs["UI_Init"]
        else:
            for key in default_prefs["UI_Init"]:
                if key not in preferences["UI_Init"]:
                    preferences["UI_Init"][key] = default_prefs["UI_Init"][key]
        
        # 确保UI组件可见性配置存在且完整
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
            # 创建临时文件，成功后再重命名，避免写入失败导致配置丢失
            temp_path = self.preference_toml_path + ".tmp"
            with open(temp_path, "w") as file:
                toml.dump(self.preferences, file)
            
            # 替换原文件
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

        # 补齐版本号，使其长度一致
        while len(v1_parts) < len(v2_parts):
            v1_parts.append(0)
        while len(v2_parts) < len(v1_parts):
            v2_parts.append(0)

        # 逐部分比较版本号
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
            # component = current_level[parts[-1]]["component"]
            # component.setVisible(not component.isVisible())
            # print(current_level)
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

        # 如果修改的是标签页的话
        if "Tab" in component_name:
            for part in parts[:-1]:
                current_level = current_level[part]  # 移动到下一个层级的子组件
            # print(current_level)
            # component = current_level["children"][component_name]["component"]
            # oldVisible=component.isVisible()
            current_level["component"].toggleComponentVisibility(component_name)
            # component.setVisible(not oldVisible)  # 切换组件的可见性
            self.logger.debug("toggleComponentVisibility %s", path)
            return
        # 如果修改的是其他的话
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
        # 从根组件的子组件开始搜索
        def search_component(current_level):
            for key, value in current_level.items():
                # 如果当前组件的名称匹配，则返回该组件
                if key == name:
                    return value["component"]
                # 如果有子组件，递归搜索
                if "children" in value:
                    result = search_component(value["children"])
                    if result:  # 如果子组件中找到了匹配项，返回该组件
                        return result
            return None

        # 从根组件的子组件开始搜索
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

    # 用正则表达式匹配 font-size 并替换
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

    # 获取当前文件路径
    current_path = os.path.dirname(os.path.abspath(__file__))

    # 需要检查的子目录列表
    subdirs = ["confs", "examples", "resources", "icons"]

    for subdir in subdirs:
        dir_path = os.path.join(current_path, get_resource_path(subdir))
        print(f"\n目录: {dir_path}")

        # 判断目录是否存在
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            # 列出目录中的所有文件和子目录
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
    # 主配置目录及子目录
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
            # 创建目录
            os.makedirs(directory, exist_ok=True)
            
            # 确保目录可写
            if not os.access(directory, os.W_OK):
                print(f"警告: 配置目录不可写 {directory}")
                if sys.platform == "win32":
                    # Windows下尝试修改权限
                    try:
                        import stat
                        os.chmod(directory, stat.S_IWRITE)
                        print(f"已尝试修改目录权限: {directory}")
                    except Exception as e:
                        print(f"修改目录权限失败: {e}")
                        success = False
                else:
                    # Linux/MacOS下提示用户修改权限
                    print(f"请使用 'chmod u+w {directory}' 命令修改权限")
                    success = False
                    
        except Exception as e:
            print(f"无法创建配置目录 {directory}: {e}")
            success = False
    
    # 检查系统特定的配置
    check_system_compatibility()
    
    return success

def check_system_compatibility():
    """检查系统兼容性并进行必要的调整"""
    system = sys.platform
    
    if system == "win32":
        # Windows特定的检查
        try:
            # 检查临时目录权限
            temp_dir = os.environ.get("TEMP")
            if temp_dir and not os.access(temp_dir, os.W_OK):
                print(f"警告: Windows临时目录不可写: {temp_dir}")
                # 尝试使用用户目录中的临时目录
                user_temp = os.path.join(os.path.expanduser("~"), ".stk", "temp")
                os.environ["TEMP"] = user_temp
                print(f"已将临时目录重定向到: {user_temp}")
        except Exception as e:
            print(f"Windows系统兼容性检查失败: {e}")
    
    elif system == "linux":
        # Linux特定的检查
        try:
            # 确保XDG_CONFIG_HOME存在
            if "XDG_CONFIG_HOME" not in os.environ:
                xdg_config = os.path.join(os.path.expanduser("~"), ".config")
                os.environ["XDG_CONFIG_HOME"] = xdg_config
                print(f"已设置XDG_CONFIG_HOME为: {xdg_config}")
        except Exception as e:
            print(f"Linux系统兼容性检查失败: {e}")
    
    elif system == "darwin":
        # MacOS特定的检查
        try:
            # 检查Application Support目录
            app_support = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "STK")
            os.makedirs(app_support, exist_ok=True)
        except Exception as e:
            print(f"MacOS系统兼容性检查失败: {e}")
            
    # 通用系统检查
    try:
        # 确保Python临时文件可以正确创建
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".tmp", prefix="stk_", delete=True) as tmp:
            pass  # 测试临时文件创建
    except Exception as e:
        print(f"临时文件创建测试失败: {e}")
        # 尝试重定向临时文件目录
        user_temp = os.path.join(os.path.expanduser("~"), ".stk", "temp")
        tempfile.tempdir = user_temp
        print(f"已将Python临时文件目录重定向到: {user_temp}")

if __name__ == "__main__":
    # 确保所有配置目录存在并进行系统兼容性检查
    if not ensure_config_directories():
        print("警告: 配置目录设置不完整，应用程序可能无法正常工作")
    
    # 初始化应用程序
    app = QApplication(sys.argv)
    check_resource()
    # 获取屏幕的逻辑 DPI 和缩放因子
    screen = app.primaryScreen()
    dpi = screen.logicalDotsPerInch()
    scale_factor = dpi / 96.0  # 96 为标准 DPI

    # 加载原始 QSS 文件
    qss_file_path = get_resource_path("resources/styles.qss")
    qss = load_qss(qss_file_path)

    # 动态调整字体大小
    scaled_qss = scale_qss_font_size(qss, scale_factor)

    # 应用调整后的 QSS 样式
    apply_qss(app, scaled_qss)
    mainWindow = MainWindow(True)
    mainWindow.show()

    sys.exit(app.exec())
