from PySide6.QtCore import QFileInfo
import webbrowser
from PySide6.QtWidgets import (
    QToolBar,
    QMenu,
    QFileDialog,
    QTextEdit,
    QToolButton,
    QCheckBox,
    QWidgetAction,
)
from PySide6.QtGui import QAction, QIcon
class Toolbar(QToolBar):

    def __init__(self, height, parent):
        super().__init__()
        self.parent = parent
        # self.current_open_file = None
        self.parent.registerComponent("Tool", self, True)
        self.initUI(height)

    def initUI(self, height):

        self.setFixedHeight(height)  # 设置工具栏高度

        openAction = QAction("Open", self)
        openAction.triggered.connect(self.showOpenMenu)
        self.registerComponent("Open", openAction)
        self.addAction(openAction)


        saveAction = QAction("Save", self)
        saveAction.triggered.connect(self.showSaveMenu)
        self.registerComponent("Save", saveAction)
        self.addAction(saveAction)

        viewAction = QAction("View", self)
        viewAction.triggered.connect(self.showViewMenu)
        self.addAction(viewAction)

        helpAction = QAction("Help", self)
        helpAction.triggered.connect(self.showHelpMenu)
        self.registerComponent("Help", helpAction)
        self.addAction(helpAction)
    # def initWorkspace(self):
    #     file_path=self.parent.get_workspaceData('info_bar/code/file_path')
    #     self.current_open_file=file_path
    def showOpenMenu(self):

        menu = QMenu(self)

        openFileAction = QAction("Open File", self)
        openFileAction.triggered.connect(self.openFile)
        menu.addAction(openFileAction)

        openDirectoryAction = QAction("Open Directory", self)
        openDirectoryAction.triggered.connect(self.openDirectory)
        menu.addAction(openDirectoryAction)
        
        openNewWindowAction = QAction("Open New Window", self)
        openNewWindowAction.triggered.connect(self.parent.open_new_window)
        menu.addAction(openNewWindowAction)

        createNewWorkspaceAction = QAction("Create New Workspace", self)
        createNewWorkspaceAction.triggered.connect(self.createNewWorkspace)
        menu.addAction(createNewWorkspaceAction)

        menu.popup(self.mapToGlobal(self.actionGeometry(self.sender()).bottomLeft()))
    def createNewWorkspace(self):
        self.parent.question_and_create_workspace(self.parent.left_sidebar.curDir)
    def openFile(self):

        # 打开文件对话框
        path, _ = QFileDialog.getOpenFileName(self, "Open File", filter="All Files (*)")
        self.parent.left_sidebar.open_file(path)

        # if path:
        #     try:
        #         # 以二进制模式读取文件，并使用UTF-8解码
        #         with open(path, "rb") as file:
        #             content = file.read().decode("utf-8")
        #             # 设置文件目录树的根路径为文件所在目录
        #             root_path = QFileInfo(path).absolutePath()
        #             self.parent.left_sidebar.treeView.setRootIndex(
        #                 self.parent.left_sidebar.model.index(root_path)
        #             )
        #             # 显示文件内容
        #             self.parent.info_bar.showContent(content)
        #             self.current_open_file = path
        #
        #     except Exception as e:
        #         print("Error reading file:", e)

    def openDirectory(self):

        # 打开目录对话框
        path = QFileDialog.getExistingDirectory(self, "Open Directory")
        if path:
            self.parent.left_sidebar.open_directory(path)
            #
            # # 设置文件目录树的根路径为用户选择的目录路径
            #
            # self.parent.left_sidebar.treeView.setRootIndex(
            #     self.parent.left_sidebar.model.index(path)
            # )

    def showSaveMenu(self):

        menu = QMenu(self)
        saveFileAction = QAction("Save", self)
        saveFileAction.triggered.connect(self.save_file)
        menu.addAction(saveFileAction)
        saveAndRunAction = QAction("Save and Run", self)
        saveAndRunAction.triggered.connect(self.saveAndRun)
        menu.addAction(saveAndRunAction)
        saveWorkspaceAction = QAction("Save Workspace", self)
        saveWorkspaceAction.triggered.connect(self.saveWorkspace)
        menu.addAction(saveWorkspaceAction)

        menu.popup(self.mapToGlobal(self.actionGeometry(self.sender()).bottomLeft()))

    def save_file(self):
        # if not self.current_open_file:
        #     return
        try:
            # 获取Code标签页中的文本内容
            content = self.parent.info_bar.codeTab.toPlainText()
            # 将内容写入文件
            with open(self.parent.curWorkFile, "w", encoding="utf-8") as file:
                file.write(content)
        except Exception as e:
            print("Error saving file:", e)

    def saveAndRun(self):
        self.save_file()
        content = self.parent.info_bar.codeTab.toPlainText()
        self.parent.info_bar.curShowCode=content
        self.parent.info_bar.runCodeWithAnalysis()

    def saveWorkspace(self):
        self.save_file()
        self.parent.save_last_workspace_data()
        
    def registerComponent(self, path, component):
        truePath = "Tool/" + path
        self.parent.registerComponent(truePath, component, True)

    def toggleComponentVisibility(self, path):
        self.parent.toggleComponentVisibility(path)

    def showViewMenu(self):
        menu = QMenu(self)
        self.addComponentsToMenu(self.parent.components["main"]["children"], menu, "")
        menu.exec(self.mapToGlobal(self.actionGeometry(self.sender()).bottomLeft()))

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

    def showHelpMenu(self):

        menu = QMenu(self)

        openWebsiteAction = QAction("Support Website", self)

        openWebsiteAction.triggered.connect(self.openWebsite)

        menu.addAction(openWebsiteAction)

        checkUpdateAction = QAction("Check Update", self)

        checkUpdateAction.triggered.connect(self.checkUpdate)

        menu.addAction(checkUpdateAction)

        preferenceAction = QAction("Preference", self)

        preferenceAction.triggered.connect(self.preference)

        menu.addAction(preferenceAction)

        menu.popup(self.mapToGlobal(self.actionGeometry(self.sender()).bottomLeft()))

    def openWebsite(self):
        url = "https://3dfd8b42.stk.pages.dev"
        webbrowser.open(url)

    def checkUpdate(self):
        self.parent.check_update()

    def preference(self):

        preferences = self.parent.load_preferences()
        Visualization_window = self.parent.getComponent(
            "Visualization window"
        )
        Visualization_window.addPreferenceTab(preferences)
        






