import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter

from PyQt5.QtCore import Qt 

from left_sidebar import LeftSidebar

from center_widget import CenterWidget

from right_sidebar import RightSidebar

from toolbar import Toolbar

from statusbar import Statusbar

from info_bar import InfoBar


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()


        # 创建中部区域

        self.center_widget = CenterWidget()


        # 创建右侧栏

        self.right_sidebar = RightSidebar(self)


         # 创建底部状态栏

        self.status_bar = Statusbar()


        # 创建信息栏

        self.info_bar = InfoBar(self)


        # 创建左侧栏

        self.left_sidebar = LeftSidebar(self)


        # 创建顶部工具栏

        self.toolbar = Toolbar(50, self)



        self.center_splitter = QSplitter()

        self.main_splitter= QSplitter()

        self.initUI()


    def showEvent(self, event):

        super().showEvent(event)

        # 设置左侧栏和右侧栏的初始宽度

        initial_width_left = 50  # 左侧栏的初始宽度

        initial_width_right = 50  # 右侧栏的初始宽度

        self.main_splitter.setSizes([initial_width_left, self.width() - initial_width_left - initial_width_right, initial_width_right])


    def initUI(self):

        # 设置主窗口标题

        self.setWindowTitle("Main Window")


        # 使用QSplitter将中心部件和信息栏包裹起来

        self.center_splitter.setOrientation(Qt.Vertical)

        self.center_splitter.addWidget(self.center_widget)

        self.center_splitter.addWidget(self.info_bar)

        self.center_splitter.setHandleWidth(5) # 设置分割线的宽度


        # 使用另一个QSplitter将左，右侧栏和中心部件包裹起来

        self.main_splitter.addWidget(self.left_sidebar)

        self.main_splitter.addWidget(self.center_splitter)

        self.main_splitter.addWidget(self.right_sidebar)

        self.main_splitter.setHandleWidth(5)  # 设置分割线的宽度



        # 创建主窗口布局

        main_layout = QVBoxLayout()

        main_layout.addWidget(self.main_splitter)


        # 创建主窗口中心部件

        central_widget = QWidget()

        central_widget.setLayout(main_layout)

        self.setCentralWidget(central_widget)


        # 将顶部工具栏和底部状态栏添加到主窗口

        self.addToolBar(self.toolbar)

        self.setStatusBar(self.status_bar)


        # 设置主窗口大小和显示

        self.setGeometry(100, 100, 1500, 1000)


        self.left_sidebar.openFilePath.connect(self.fixCurFilePath)

    def fixCurFilePath(self, path):

        self.toolbar.current_open_file = path



if __name__ == '__main__':

    app = QApplication(sys.argv)

    mainWindow = MainWindow()

    mainWindow.show()

    sys.exit(app.exec_())

