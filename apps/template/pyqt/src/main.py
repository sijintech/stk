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
)
from PySide6.QtCore import Qt
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

updatejson_url = "https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/update.json"
app_name = "stk"
cur_version = version.version
code_url = "https://github.com/sijintech/stk"


class MainWindow(QMainWindow):
    def __init__(self, create_workspace_if_no):
        super().__init__()
        self.logger = CustomLogger()
        # 用于存储具有层级关系的组件
        self.components = {
            "main": {"name": "main", "component": self, "children": {}}
        }
        # 创建中部区域
        self.center_widget = center_widget.CenterWidget(self)
        # 创建右侧栏
        self.right_sidebar = right_sidebar.RightSidebar(self)
        # 创建底部状态栏
        self.status_bar = statusbar.Statusbar(self)
        # 创建信息栏
        self.info_bar = info_bar.InfoBar(self)
        # 创建左侧栏
        self.left_sidebar = left_sidebar.LeftSidebar(self)
        # 创建顶部工具栏
        self.toolbar = toolbar.Toolbar(50, self)

        self.center_splitter = QSplitter()
        self.main_splitter = QSplitter()
        self.update_status_bar = QStatusBar()
        self.updateWindow = None

        # 如果打开的窗口不是工作区，是否要创建工作区
        self.create_workspace_if_no = create_workspace_if_no
        # 当前工作目录是否是工作区
        self.isWorkspace = False
        # 当前打开的目录
        self.curWorkDir = None
        # 当前打开的文件
        self.curWorkFile = None

        self.workspace_conf_path = None
        self.workspaceData = {}
        self.preferences = None

        self.init_preferences()
        self.init_ui()
        self.check_update()
        # print(self.components)


    def init_ui(self):
        # 设置主窗口标题
        self.setWindowTitle("STK")
        # 使用QSplitter将中心部件和信息栏包裹起来
        self.center_splitter.setOrientation(Qt.Vertical)
        self.center_splitter.addWidget(self.center_widget)
        self.center_splitter.addWidget(self.info_bar)
        self.center_splitter.setHandleWidth(2)  # 设置分割线的宽度
        # 使用另一个QSplitter将左，右侧栏和中心部件包裹起来
        self.main_splitter.addWidget(self.left_sidebar)
        self.main_splitter.addWidget(self.center_splitter)
        self.main_splitter.addWidget(self.right_sidebar)
        self.main_splitter.setHandleWidth(2)  # 设置分割线的宽度
        # 创建主窗口布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_splitter)

        # 创建主窗口中心部件
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        # 将顶部工具栏和底部状态栏添加到主窗口
        self.addToolBar(self.toolbar)
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
                path = (
                        father_component.replace("_", " ")
                        + "/"
                        + component.replace("_", " ")
                )
                self.toggleComponentVisibility(path)

    def showEvent(self, event):
        self.logger.debug("showEvent")
        super().showEvent(event)
        if self.preferences["Open_Last_Workspace"] and self.curworkdir_is_workspace():
            self.init_workspace()
        elif self.create_workspace_if_no:
            self.question_and_create_workspace(self.curWorkDir, True)
        else:
            # 设置主窗口大小和显示
            self.setGeometry(
                50,
                50,
                int(self.preferences["UI_Init"]["window_width"]),
                int(self.preferences["UI_Init"]["window_height"]),
            )

    def closeEvent(self, event):
        self.modify_preferences('Open_Last_Working_Directory', self.curWorkDir)
        self.save_preferences()
        if self.isWorkspace:
            self.check_and_save_curworkspace()
        elif self.left_sidebar.curFile is not None:
            self.check_and_save_curfile()
        event.accept()

    def get_workspace_file(self, directory):
        # 判断目录是否存在
        if not os.path.isdir(directory):
            self.logger.error("目录不存在")
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

    def init_ui_from_workspace(self):
        height = self.get_workspace_data("window/height")
        width = self.get_workspace_data("window/width")
        self.setGeometry(
            50,
            50,
            int(width),
            int(height),
        )
        self.left_sidebar.initWorkspace()
        self.center_widget.initWorkspace()
        self.info_bar.initWorkspace()
        # self.toolbar.initWorkspace()

    def init_workspace(self):
        self.isWorkspace = True
        file_name = self.get_workspace_file(self.curWorkDir)
        self.init_workspace_data(file_name)
        self.init_ui_from_workspace()

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
            shutil.copy(file_to_copy, destination)
            self.logger.debug("已成功复制文件到目录下并改名为:%s", new_file_name)
            return new_file_name

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
            self.create_workspace_file(directory, os.path.join(this_dir, "confs/workspace.suan"))
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
        if not self.info_bar.curFileIsSave():
            reply = QMessageBox.question(
                self,
                "Warning",
                "你还未保存该文件内容，是否保存",
                QMessageBox.Yes,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.toolbar.saveFile()

    def check_and_save_curworkspace(self):
        self.check_and_save_curfile()
        if not self.cur_workspace_is_save():
            # print("curWorkspaceIsSave")
            # self.center_widget.close()
            reply = QMessageBox.question(
                self,
                "Warning",
                "你还未保存工作区设置，是否保存",
                QMessageBox.Yes,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.save_last_workspace_data()
                # event.accept()
            # else:
            # event.accept()

    def save_last_workspace_data(self):
        width = self.width()
        height = self.height()
        self.modify_workspaceData("window/width", width)
        self.modify_workspaceData("window/height", height)
        self.modify_workspaceData(
            "center_widget/active_tab_index",
            self.center_widget.tabWidget.currentIndex(),
        )
        # print(self.center_widget.tabWidget.currentIndex())
        # print(self.workspaceData)
        self.modify_workspaceData("left_sidebar/working_directory", self.curWorkDir)
        self.save_workspace()
        self.toolbar.save_file()

    def load_workspace_data(self):
        try:
            with open(
                    self.workspace_conf_path,
                    "r",
            ) as file:
                workspaceData = toml.load(file)
        except FileNotFoundError:
            workspaceData = {}
        return workspaceData

    def save_workspace(self):
        with open(self.workspace_conf_path, "w") as file:
            toml.dump(self.workspaceData, file)

    def modify_workspaceData(self, path, value):
        parts = path.split("/")
        data = self.workspaceData
        for part in parts[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]
        data[parts[-1]] = value
        # print(self.workspaceData)

    def get_workspace_data(self, path):
        parts = path.split("/")
        data = self.workspaceData
        for part in parts[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]
        return data[parts[-1]]


    def init_preferences(self):
        # 对于已发布版本，首选项文件的位置应位于用户目录中，对于开发版本，应位于当前目录中
        this_dir = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, "frozen", True):
            self.logger.info("执行脚本")
            self.preference_toml_path = os.path.join(this_dir, "./confs/preference.toml")

        else:
            self.preference_toml_path = os.path.join(
                this_dir, "../test/preference.toml"
            )
        self.preferences = self.load_preferences()
        self.curWorkDir = self.preferences["Open_Last_Working_Directory"]
        self.logger.debug("curWorkDir:%s", self.curWorkDir)

    def load_preferences(self):
        try:
            with open(
                    self.preference_toml_path,
                    "r",
            ) as file:
                preferences = toml.load(file)
                # print(preferences)
        except FileNotFoundError:
            preferences = {}
        return preferences

    def modify_preferences(self, path, value):
        parts = path.split("/")
        data = self.preferences
        for part in parts[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]
        data[parts[-1]] = value

    def save_preferences(self):
        with open(self.preference_toml_path, "w") as file:
            toml.dump(self.preferences, file)

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
        self.logger.debug("registerComponent %s " + path)

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
            self.logger.debug("unregisterComponent %s" + path)

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
            self.logger.debug("toggleComponentVisibility %s" + path)
            return
        # 如果修改的是其他的话
        for part in parts[:-1]:
            current_level = current_level[part]["children"]  # 移动到下一个层级的子组件
        component = current_level[component_name]["component"]  # 获取要切换可见性的组件
        component.setVisible(not component.isVisible())  # 切换组件的可见性
        current_level[component_name]["isVisible"] = not current_level[component_name][
            "isVisible"
        ]
        self.logger.debug("toggleComponentVisibility %s" + path)

    def componentIsVisible(self, path):
        """判断组件是否可见."""
        parts = path.split("/")
        current_level = self.components["main"]["children"]  # 从根组件的子组件开始搜索
        component_name = parts[-1]
        for part in parts[:-1]:
            current_level = current_level[part]["children"]  # 移动到下一个层级的子组件
        return current_level[component_name]["isVisible"]

    def getComponent(self, path):
        parts = path.split("/")
        current_level = self.components["main"]["children"]  # 从根组件的子组件开始搜索
        component_name = parts[-1]
        for part in parts[:-1]:
            current_level = current_level[part]["children"]  # 移动到下一个层级的子组件
        return current_level[component_name]["component"]

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


if __name__ == "__main__":
    Updater.init()
    app = QApplication(sys.argv)
    mainWindow = MainWindow(True)
    mainWindow.show()
    sys.exit(app.exec())
