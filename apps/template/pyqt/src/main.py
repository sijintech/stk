import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,QStatusBar,QLabel
from PySide6.QtCore import Qt
import left_sidebar
import center_widget
import right_sidebar
import toolbar
import statusbar
import info_bar
import Updater

updatejson_url = "https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/update.json"

app_name = "suan_pyqt"

cur_version = "0.0.0"

index_url = "https://github.com/sijintech/stk"

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
        self.update_status_bar=QStatusBar()

        self.winUpdate = None

        self.initUI()
        self.check_update()

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

    def compare_versions(self,version1, version2):
        v1_parts = list(map(int, version1.split('.')))
        v2_parts = list(map(int, version2.split('.')))

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
    def check_update_callback(self, data):
        # print("数据", 数据)
        new_version = data['版本号']
        release_time = data['发布时间']
        # try:
        #     new_version = f"最新版更新于:{release_time}({new_version})"
        # except:
        #     pass
        #     new_version = "查询失败"
        if self.compare_versions(new_version,cur_version)==1:
            print('SHOW update')
            self.show_update_window()
        print('show end')
    def check_update(self):
        self.check_update_thread = Updater.check_update_thread(updatejson_url, self.check_update_callback)
        print('start')
        self.check_update_thread.start()
    def show_update_window(self):
        if self.winUpdate is None:
            self.winUpdate = Updater.窗口_更新软件(updatejson_url,
                                             app_name,
                                             cur_version,
                                             index_url)
        self.winUpdate.show()


if __name__ == '__main__':
    Updater.初始化()
    app = QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    sys.exit(app.exec_())
