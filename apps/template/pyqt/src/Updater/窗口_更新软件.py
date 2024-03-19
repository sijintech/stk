import os
import webbrowser

from PySide6.QtWidgets import QDialog

from .自动更新功能 import download_file_thread, 系统_是否为window系统, 系统_是否为mac系统, 更新自己Window应用, check_update_thread, 更新自己MacOS应用

from . import update_image_rc
from . import ui_winUpdate


class 窗口_更新软件(QDialog):
    允许关闭 = False

    def __init__(self, updatejson_url="duolabmeng6/qtAutoUpdateApp", 应用名称="my_app.app", 当前版本号="1.0",
                 官方网址="https://github.com/duolabmeng6/qtAutoUpdateApp"):
        super(窗口_更新软件, self).__init__()
        self.ui = ui_winUpdate.Ui_Form()
        self.ui.setupUi(self)
        self.setWindowTitle('软件更新')
        self.resize(620, 380)

        # 绑定按钮事件
        self.ui.pushButton_azgx.clicked.connect(self.安装更新)
        self.ui.pushButton_gfwz.clicked.connect(self.打开官方网址)
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
        if 系统_是否为mac系统():
            self.压缩包路径 = os.path.abspath(self.下载文件夹路径 + f"/{self.应用名称}.zip")
        if 系统_是否为window系统():
            print('window')
            self.压缩包路径 = os.path.abspath(self.下载文件夹路径 + f"/{self.应用名称}.exe")

        print('查询最新版本')
        self.检查更新线程 = check_update_thread(updatejson_url, self.检查更新回到回调函数)
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
    def 检查更新回到回调函数(self, data):
        print("数据", data)
        new_version = data['版本号']
        self.ui.label_bbh.setText(f'最新版本:{new_version} 当前版本: {self.cur_version}')
        self.ui.textEdit.setHtml(data['更新内容'])
        self.mac下载地址 = data['mac下载地址']
        self.win下载地址 = data['win下载地址']

        if self.compare_versions(new_version,self.cur_version)!=1 or new_version == "":
            self.ui.label_2.setText("你使用的是最新版本")
            self.ui.pushButton_azgx.hide()
            self.ui.pushButton_tgbb.hide()
            self.ui.pushButton_ok.show()
            return

        self.ui.pushButton_azgx.setEnabled(True)
        self.ui.pushButton_tgbb.setEnabled(True)
        self.ui.label_2.setText("发现新版本")

    def 安装更新(self):
        print('安装更新')
        self.ui.progressBar.show()
        self.ui.label_zt.show()
        self.ui.label_zt.setText('更新中...')
        self.ui.pushButton_azgx.setEnabled(False)
        self.ui.pushButton_tgbb.setEnabled(False)
        print('mac下载地址', self.mac下载地址)
        print('win下载地址', self.win下载地址)

        if 系统_是否为mac系统():
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
                回调函数=self.下载完成,
            )
            self.下载文件线程.start()

        if 系统_是否为window系统():
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
                回调函数=self.下载完成
            )
            self.下载文件线程.start()

    def 下载完成(self, 下载结果, 保存地址):
        if not 下载结果:
            self.ui.label_zt.setText("下载更新失败")
            return
        if 系统_是否为mac系统():
            更新自己MacOS应用(
                资源压缩包=保存地址,
                应用名称=self.应用名称
            )
        if 系统_是否为window系统():
            exe资源文件路径 = 保存地址
            更新自己Window应用(exe资源文件路径)

    def 打开官方网址(self):
        # 浏览器打开网址
        print('官方网址', self.官方网址)
        webbrowser.open(self.官方网址)
