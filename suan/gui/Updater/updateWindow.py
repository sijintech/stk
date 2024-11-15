import os
import webbrowser

from PySide6.QtWidgets import QDialog

from .autoUpdate import download_file_thread, is_windows, is_mac, update_windows_app, check_update_thread, \
    update_mac_app

from . import update_image_rc
from . import ui_winUpdate


class UpdateWindow(QDialog):
    允许关闭 = False

    def __init__(self, updatejson_url="", 应用名称="my_app.app", 当前版本号="1.0",
                 官方网址=""):
        super(UpdateWindow, self).__init__()
        self.ui = ui_winUpdate.Ui_Form()
        self.ui.setupUi(self)
        self.setWindowTitle('软件更新')
        self.resize(620, 380)

        # 绑定按钮事件
        self.ui.pushButton_azgx.clicked.connect(self.install_update)
        self.ui.pushButton_gfwz.clicked.connect(self.open_web)
        self.ui.pushButton_tgbb.clicked.connect(self.close)
        self.ui.pushButton_ok.clicked.connect(self.close)

        # 隐藏更新进度条和状态编辑框
        self.ui.progressBar.hide()
        self.ui.progressBar.setValue(0)
        self.ui.progressBar.setRange(0, 100)
        self.ui.label_zt.hide()
        self.ui.pushButton_ok.hide()
        self.ui.pushButton_azgx.setEnabled(False)
        self.ui.pushButton_tgbb.setEnabled(False)
        # textEdit 禁止编辑
        self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.setText("正在检查更新...")

        self.应用名称 = 应用名称
        self.cur_version = 当前版本号
        self.官方网址 = 官方网址
        最新版本 = "查询中..."
        self.ui.label_2.setText(最新版本)
        self.ui.label_bbh.setText(f'最新版本:{最新版本} 当前版本: {self.cur_version}')
        self.下载文件夹路径 = os.path.expanduser('~/Downloads')
        if is_mac():
            self.压缩包路径 = os.path.abspath(self.下载文件夹路径 + f"/{self.应用名称}.zip")
        if is_windows():
            print('window')
            self.压缩包路径 = os.path.abspath(self.下载文件夹路径 + f"/{self.应用名称}.exe")

        print('查询最新版本')
        self.检查更新线程 = check_update_thread(updatejson_url, self.check_update_and_callback)
        self.检查更新线程.start()

    def closeEvent(self, event):
        # self.检查更新线程.quit()
        self.hide()
        if self.允许关闭 is False:
            event.ignore()
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

    def check_update_and_callback(self, data):
        print("数据", data)
        new_version = data['版本号']
        self.ui.label_bbh.setText(f'最新版本:{new_version} 当前版本: {self.cur_version}')
        self.ui.textEdit.setHtml(data['更新内容'])
        self.mac下载地址 = data['mac下载地址']
        self.win下载地址 = data['win下载地址']

        if self.compare_versions(new_version, self.cur_version) != 1 or new_version == "":
            self.ui.label_2.setText("你使用的是最新版本")
            self.ui.pushButton_azgx.hide()
            self.ui.pushButton_tgbb.hide()
            self.ui.pushButton_ok.show()
            return

        self.ui.pushButton_azgx.setEnabled(True)
        self.ui.pushButton_tgbb.setEnabled(True)
        self.ui.label_2.setText("发现新版本")

    def install_update(self):
        print('安装更新')
        self.ui.progressBar.show()
        self.ui.label_zt.show()
        self.ui.label_zt.setText('更新中...')
        self.ui.pushButton_azgx.setEnabled(False)
        self.ui.pushButton_tgbb.setEnabled(False)
        print('mac下载地址', self.mac下载地址)
        print('win下载地址', self.win下载地址)

        if is_mac():
            if self.mac下载地址 == "":
                self.ui.label_zt.setText("没有找到 ManOS 系统软件下载地址")
                return
            print('安装更新 mac', self.mac下载地址, self.压缩包路径)
            self.下载文件线程 = download_file_thread(
                下载地址=self.mac下载地址,
                保存地址=self.压缩包路径,
                窗口=self,
                编辑框=self.ui.label_zt,
                进度条=self.ui.progressBar,
                应用名称=self.应用名称,
                回调函数=self.finish_download,
            )
            self.下载文件线程.start()

        if is_windows():
            if self.win下载地址 == "":
                self.ui.label_zt.setText("没有找到 windows 系统软件下载地址")
                return
            print('安装更新 win', self.win下载地址, self.压缩包路径)

            self.下载文件线程 = download_file_thread(
                下载地址=self.win下载地址,
                保存地址=self.压缩包路径,
                窗口=self,
                编辑框=self.ui.label_zt,
                进度条=self.ui.progressBar,
                应用名称=self.应用名称,
                回调函数=self.finish_download
            )
            self.下载文件线程.start()

    def finish_download(self, result, save_addr):
        if not result:
            self.ui.label_zt.setText("下载更新失败")
            return
        if is_mac():
            update_mac_app(
                zip_path=save_addr,
                app_name=self.应用名称
            )
        if is_windows():
            exe资源文件路径 = save_addr
            update_windows_app(exe资源文件路径)

    def open_web(self):
        # 浏览器打开网址
        print('官方网址', self.官方网址)
        webbrowser.open(self.官方网址)
