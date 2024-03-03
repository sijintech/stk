from PyQt5.QtCore import QFileInfo

from PyQt5.QtWidgets import QToolBar, QAction, QMenu, QFileDialog, QTextEdit


class Toolbar(QToolBar):

    def __init__(self, height,parent):

        super().__init__()

        self.parent=parent
        # self.left_sidebar = left_sidebar

        # self.info_bar = info_bar

        self.current_open_file = None

        self.initUI(height)


    def initUI(self, height):

        self.setFixedHeight(height)  # 设置工具栏高度

        openAction = QAction("Open", self)

        openAction.triggered.connect(self.showOpenMenu)

        self.addAction(openAction)


        saveAction = QAction("Save", self)

        saveAction.triggered.connect(self.saveFile)

        self.addAction(saveAction)


    def showOpenMenu(self):

        menu = QMenu(self)

        openFileAction = QAction("Open File", self)

        openFileAction.triggered.connect(self.openFile)

        menu.addAction(openFileAction)


        openDirectoryAction = QAction("Open Directory", self)

        openDirectoryAction.triggered.connect(self.openDirectory)

        menu.addAction(openDirectoryAction)


        menu.popup(self.mapToGlobal(self.actionGeometry(self.sender()).bottomLeft()))


    def openFile(self):

        # 打开文件对话框

        path, _ = QFileDialog.getOpenFileName(self, "Open File", filter="All Files (*)")

        if path:

            try:

                # 以二进制模式读取文件，并使用UTF-8解码

                with open(path, 'rb') as file:

                    content = file.read().decode('utf-8')

                    # 设置文件目录树的根路径为文件所在目录

                    root_path = QFileInfo(path).absolutePath()

                    self.parent.left_sidebar.treeView.setRootIndex(self.parent.left_sidebar.model.index(root_path))

                    # 显示文件内容

                    self.parent.info_bar.showContent(content)

                    self.current_open_file = path

            except Exception as e:

                print("Error reading file:", e)


    def openDirectory(self):

        # 打开目录对话框

        path = QFileDialog.getExistingDirectory(self, "Open Directory")

        if path:

            # 设置文件目录树的根路径为用户选择的目录路径

            self.parent.left_sidebar.treeView.setRootIndex(self.parent.left_sidebar.model.index(path))


    def saveFile(self):

        if not self.current_open_file:           

            return

        try:

            # 获取Code标签页中的文本内容

            content = self.parent.info_bar.codeTab.toPlainText()

            # 将内容写入文件

            with open(self.current_open_file, 'w', encoding='utf-8') as file:

                file.write(content)

        except Exception as e:

            print("Error saving file:", e)

