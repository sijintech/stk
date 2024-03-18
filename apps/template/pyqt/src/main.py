import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter

from PyQt5.QtCore import Qt 

import left_sidebar 

import center_widget 
import right_sidebar 
import toolbar

import statusbar 

import info_bar 


import 自动更新模块 
import version
全局变量_版本号 = version.version
全局_项目名称 = "duolabmeng6/QtEasyDesigner"
全局_应用名称 = "QtEasyDesigner.app"
全局_当前版本 = version.version
全局_官方网址 = "https://github.com/duolabmeng6/QtEasyDesigner"


def 检查更新回到回调函数(self, 数据):
    # print("数据", 数据)
    最新版本号 = 数据['版本号']
    发布时间 = 数据['发布时间']
    发布时间 = 到时间(发布时间).取日期()
    try:
        最新版本 = f"最新版更新于:{发布时间}({最新版本号})"
    except:
        pass
        最新版本 = "查询失败"
    self.状态条标签.setText(f"欢迎使用 Qt视窗设计器(QtEasyDesigner) 当前版本:{全局变量_版本号} {最新版本}")

def 更新版本号(self):
    self.检查更新线程 = 自动更新模块.检查更新线程(全局_项目名称, self.检查更新回到回调函数)
    self.检查更新线程.start()

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()


        # 创建中部区域

        self.center_widget = center_widget.CenterWidget()


        # 创建右侧栏

        self.right_sidebar = right_sidebar.RightSidebar(self)


         # 创建底部状态栏

        self.status_bar = statusbar.Statusbar()


        # 创建信息栏

        self.info_bar = info_bar.InfoBar(self)


        # 创建左侧栏

        self.left_sidebar = left_sidebar.LeftSidebar(self)


        # 创建顶部工具栏

        self.toolbar = toolbar.Toolbar(50, self)



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

