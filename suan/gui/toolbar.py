from PySide6.QtCore import Qt
import webbrowser
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QToolBar,
    QMenu,
    QFileDialog,
    QToolButton,
    QCheckBox,
    QComboBox,
    QWidgetAction
)
import zipfile
from PySide6.QtGui import QAction, QIcon
from custom_logger import CustomLogger
import os
import shutil


class ToolBar(QWidget):
    """自定义工具栏，继承自 QWidget，并作为窗口的一个部件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = CustomLogger()
        self.parent = parent
        self.initUI()

    def initUI(self):
        self.logger.info("初始化工具栏部件...")

        # 第一行工具栏
        self.toolbar1 = QToolBar("第一行工具栏", self)
        self.createFirstRowButtons()
        self.parent.addToolBar(self.toolbar1)
        self.parent.addToolBarBreak()
        # 第二行工具栏
        self.toolbar2 = QToolBar("第二行工具栏", self)
        self.createSecondRowButtons()
        self.parent.addToolBar(self.toolbar2)

        self.logger.info("工具栏初始化完成")

    def createFirstRowButtons(self):
        self.logger.info("创建第一行工具栏按钮...")

        # 文件菜单
        file_menu = QMenu("文件", self)
        open_file_action = QAction(QIcon("./icons/file_icon.ico"), "打开文件", self)
        open_file_action.triggered.connect(self.openFile)
        file_menu.addAction(open_file_action)

        open_directory_action = QAction(QIcon("./icons/folder_icon.ico"), "打开项目", self)
        open_directory_action.triggered.connect(self.openDirectory)
        file_menu.addAction(open_directory_action)

        open_new_action = QAction(QIcon("./icons/new.ico"), "新建", self)
        open_new_action.triggered.connect(self.showNewMenu)
        file_menu.addAction(open_new_action)

        file_action = QAction("文件", self)
        file_action.triggered.connect(
            lambda: file_menu.exec(self.toolbar1.mapToGlobal(self.toolbar1.actionGeometry(file_action).bottomLeft())))
        self.toolbar1.addAction(file_action)

        # 视图菜单
        viewAction = QAction("视图", self)
        view_menu = QMenu("视图", self)
        self.addComponentsToMenu(self.parent.components["main"]["children"], view_menu, "")
        viewAction.triggered.connect(
            lambda: view_menu.exec(self.toolbar1.mapToGlobal(self.toolbar1.actionGeometry(viewAction).bottomLeft())))
        self.toolbar1.addAction(viewAction)

        # 窗口菜单
        window_menu = QMenu("窗口", self)
        preference_action = QAction("设置布局", self)
        preference_action.triggered.connect(self.preference)
        window_menu.addAction(preference_action)

        window_action = QAction("窗口", self)
        window_action.triggered.connect(lambda: window_menu.exec(
            self.toolbar1.mapToGlobal(self.toolbar1.actionGeometry(window_action).bottomLeft())))
        self.toolbar1.addAction(window_action)

        # 帮助菜单
        help_menu = QMenu("帮助", self)
        support_action = QAction("支持网站", self)
        support_action.triggered.connect(self.openWebsite)
        help_menu.addAction(support_action)

        help_action = QAction("帮助", self)
        help_action.triggered.connect(
            lambda: help_menu.exec(self.toolbar1.mapToGlobal(self.toolbar1.actionGeometry(help_action).bottomLeft())))
        self.toolbar1.addAction(help_action)

    def showNewMenu(self):
        new_menu = QMenu(self)
        new_menu.addAction(QAction("新文件", self))

        new_menu.addAction(QAction("新目录", self))

        new_window_action = QAction("新窗口", self)
        new_window_action.triggered.connect(self.parent.open_new_window)
        new_menu.addAction(new_window_action)

        create_workspace_action = QAction("创建工作区", self)
        create_workspace_action.triggered.connect(self.createNewWorkspace)
        new_menu.addAction(create_workspace_action)
        new_menu.popup(self.toolbar1.mapToGlobal(self.toolbar1.actionGeometry(self.toolbar1.sender()).bottomLeft()))

    def createSecondRowButtons(self):
        self.logger.info("创建第二行工具栏按钮...")

        # 新建按钮
        new_button = QToolButton(self)
        new_button.setIcon(QIcon("./icons/new.ico"))
        new_button.setPopupMode(QToolButton.InstantPopup)
        new_menu = QMenu(self)

        new_file_action = QAction("新文件", self)
        new_file_action.triggered.connect(self.create_new_file)
        new_menu.addAction(new_file_action)

        new_dir_action = QAction("新目录", self)
        new_dir_action.triggered.connect(self.create_new_dir)
        new_menu.addAction(new_dir_action)

        new_window_action = QAction("新窗口", self)
        new_window_action.triggered.connect(self.parent.open_new_window)
        new_menu.addAction(new_window_action)

        create_workspace_action = QAction("创建工作区", self)
        create_workspace_action.triggered.connect(self.createNewWorkspace)
        new_menu.addAction(create_workspace_action)

        new_button.setMenu(new_menu)
        self.toolbar2.addWidget(new_button)

        # 保存工作区按钮
        save_workspace_action = QAction(QIcon("./icons/save.ico"), "保存工作区", self)
        save_workspace_action.triggered.connect(self.saveWorkspace)
        self.toolbar2.addAction(save_workspace_action)

        # 打开文件按钮
        open_file_action = QAction(QIcon("./icons/file_action.ico"), "打开文件", self)
        open_file_action.triggered.connect(self.openFile)
        self.toolbar2.addAction(open_file_action)

        # 打开目录按钮
        open_directory_action = QAction(QIcon("./icons/folder_icon.ico"), "打开项目", self)
        open_directory_action.triggered.connect(self.openDirectory)
        self.toolbar2.addAction(open_directory_action)
        # 分隔符
        self.toolbar2.addSeparator()

        # 保存并运行按钮
        save_and_run_action = QAction(QIcon("./icons/run.png"), "保存并运行", self)
        save_and_run_action.triggered.connect(self.saveAndRun)
        self.toolbar2.addAction(save_and_run_action)

        # 停止按钮
        stop_action = QAction(QIcon("./icons/stop.png"), "停止", self)
        stop_action.triggered.connect(self.stop_execution)
        self.toolbar2.addAction(stop_action)

        # 分隔符
        self.toolbar2.addSeparator()

        # 项目下拉菜单
        self.project_dropdown = QComboBox(self)
        self.project_dropdown.addItem("选择项目")  # 默认提示选项
        self.loadProjects("../examples")
        self.project_dropdown.currentIndexChanged.connect(self.handleProjectSelection)
        self.toolbar2.addWidget(self.project_dropdown)
        # 分隔符
        self.toolbar2.addSeparator()
        # 检查更新按钮
        check_update_action = QAction(QIcon("./icons/update.png"), "检查更新", self)
        check_update_action.triggered.connect(self.checkUpdate)
        self.toolbar2.addAction(check_update_action)

    # 工具栏按钮的功能实现

    def loadProjects(self, examples_dir):
        """
        读取 ../examples 下的 .zip 文件，并加载到下拉菜单中。
        """
        if not os.path.exists(examples_dir):
            self.logger.error(f"目录 {examples_dir} 不存在")
            return

        self.projects = []
        for file_name in os.listdir(examples_dir):
            if file_name.endswith(".zip"):
                self.projects.append(os.path.join(examples_dir, file_name))
                # 去掉后缀名添加到下拉菜单
                self.project_dropdown.addItem(os.path.splitext(file_name)[0])

    def handleProjectSelection(self, index):
        """
        处理用户选择的项目。
        """
        if index == 0:  # 默认提示项
            return

        selected_project = self.projects[index - 1]  # 下拉菜单索引与项目列表对齐
        self.logger.info(f"用户选择了项目：{selected_project}")

        # 打开文件对话框，选择目标路径
        target_dir = QFileDialog.getExistingDirectory(
            self, "选择目标路径"
        )
        if not target_dir:
            self.logger.info("用户取消了路径选择")
            return

        # 提示用户重命名项目
        new_dir, _ = QFileDialog.getSaveFileName(
            self, "重命名项目", os.path.join(target_dir)
        )
        os.makedirs(new_dir, exist_ok=True)

        # 解压缩项目到新目录
        try:
            with zipfile.ZipFile(selected_project, 'r') as zip_ref:
                zip_ref.extractall(new_dir)
            self.logger.info(f"项目成功解压到：{new_dir}")
        except Exception as e:
            self.logger.error(f"解压项目失败：{e}")
            return

        # 打开解压后的项目
        try:
            workspace_updates = {
                'left_sidebar/working_directory': new_dir,
                'info_bar/code/file_path': '',
            }
            # 打开复制后的项目
            self.parent.left_sidebar.open_directory(new_dir, workspace_updates)
        except Exception as e:
            self.logger.error(f"打开项目失败：{e}")

    def openFile(self):
        # 打开文件对话框
        path, _ = QFileDialog.getOpenFileName(self, "Open File", filter="All Files (*)")
        self.parent.left_sidebar.open_file(path)

    def openDirectory(self):
        # 打开目录对话框
        path = QFileDialog.getExistingDirectory(self, "Open Directory")
        if path:
            self.parent.left_sidebar.open_directory(path)

    def createNewWorkspace(self):
        self.logger.info("创建新工作区...")
        self.parent.question_and_create_workspace(self.parent.curDir)

    def saveWorkspace(self):
        self.logger.info("保存工作区...")
        self.save_file()
        self.parent.save_last_workspace_data()

    def openWebsite(self):
        self.logger.info("打开支持网站...")
        webbrowser.open("https://3dfd8b42.stk.pages.dev")

    def preference(self):
        self.logger.info("打开布局设置...")
        preferences = self.parent.load_preferences()
        Visualization_window = self.parent.get_component_by_path(
            "Visualization window"
        )
        Visualization_window.addPreferenceTab(preferences)

    def save_file(self):
        try:
            # 获取Code标签页中的文本内容
            content = self.parent.info_bar.codeTab.toPlainText()
            # 将内容写入文件
            with open(self.parent.curWorkFile, "w", encoding="utf-8") as file:
                file.write(content)
        except Exception as e:
            self.logger.debug("Error saving file:", e)

    def saveAndRun(self):
        self.save_file()
        content = self.parent.info_bar.codeTab.toPlainText()
        self.parent.info_bar.curShowCode = content
        self.parent.info_bar.runCodeWithAnalysis()

    def checkUpdate(self):
        self.parent.check_update()

    def stop_execution(self):
        # todo
        pass

    def create_new_file(self):
        # todo
        pass

    def create_new_dir(self):
        # todo
        pass

    def registerComponent(self, path, component):
        truePath = "Tool/" + path
        self.parent.registerComponent(truePath, component, True)

    def toggleComponentVisibility(self, path):
        self.parent.toggleComponentVisibility(path)

    def showViewMenu(self):
        menu = QMenu(self)
        self.addComponentsToMenu(self.parent.components["main"]["children"], menu, "")
        menu.exec(self.toolbar1.mapToGlobal(self.toolbar1.actionGeometry(self.toolbar1.sender()).bottomLeft()))

    def addComponentsToMenu(self, components, menu, path):
        for name, info in components.items():
            current_path = path + name  # 使用局部变量存储当前节点的路径
            if len(info["children"]) != 0:  # 该节点有子组件
                sub_menu = menu.addMenu(name)
                self.addComponentsToMenu(
                    info["children"], sub_menu, current_path + "/"
                )  # 传递更新后的当前路径
            else:  # 该节点为叶子节点

                checkbox = QCheckBox(self)
                checkbox.setText(name)
                self.logger.debug(info)
                checkbox.setChecked(info["isVisible"])
                action = QWidgetAction(self)
                action.setDefaultWidget(checkbox)
                menu.addAction(action)
                # checkbox.clicked.connect(self.toggleComponentVisibility(current_path))
                checkbox.clicked.connect(
                    lambda c=info[
                        "component"
                    ], p=current_path: self.toggleComponentVisibility(p)
                )
