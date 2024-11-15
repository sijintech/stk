# -*- coding: utf-8 -*-
import json
import os
import platform
import shutil
import sys

from PySide6 import QtCore
from PySide6.QtCore import QThread

from .handleZip import unpack
from .downloadFile import download_file
from .updateVersion import get_version_and_download_addr


def is_windows():
    return platform.system().lower() == 'windows'


def is_linux():
    return platform.system().lower() == 'linux'


def is_mac():
    return platform.system().lower() == 'darwin'


def get_windows_path():
    # 如果不处于编译状态反馈空
    try:
        path = sys._MEIPASS
        return sys.argv[0]
    except Exception:
        return ""


def get_mac_path():
    # 如果不处于编译状态反馈空
    try:
        编译后路径 = sys._MEIPASS
    except Exception:
        编译后路径 = os.path.abspath(".")
        # 调试的
        # 编译后路径 = "/Users/chensuilong/Desktop/pythonproject/autotest/dist/my_app.app/Contents/MacOS"
    app目录 = 编译后路径[:编译后路径.rfind('/')]
    app目录 = app目录[:app目录.rfind('/')]
    父目录名称 = 编译后路径[编译后路径.rfind('/') + 1:]
    if 父目录名称 == "MacOS":
        return app目录
    else:
        return ""


def update_mac_app(zip_path, app_name="my_app.app"):
    # 资源压缩包 = "/Users/chensuilong/Desktop/pythonproject/autotest/dist/my_app.2.0.zip"
    # 应用名称 例如 my_app.app 这你的压缩包里面压缩的应用文件夹名称
    MacOs应用路径 = get_mac_path()
    if MacOs应用路径 != "":
        app目录父目录 = MacOs应用路径[:MacOs应用路径.rfind('/')]
        print(f"资源压缩包 {zip_path} app目录父目录{app目录父目录} MacOs应用路径{MacOs应用路径}")
        if MacOs应用路径 != "":
            unpack(zip_path, app目录父目录, [app_name + '/Contents/'])
            # 解压完成就压缩包
            os.remove(zip_path)
            MacOs应用路径 = os.path.join(app目录父目录, app_name)
            # QApplication.quit()
            app_name = app_name[:app_name.rfind('.')]
            运行命令 = f"killall {app_name} && open -n -a {MacOs应用路径}"
            os.system(运行命令)
            return True, MacOs应用路径
    else:
        print("非MacOS编译环境")
        return False, ""


def _get_run_path():
    """ PyInstaller 单文件的运行目录  """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.realpath(sys.argv[0]))
    else:
        return sys.path[0]


def init():
    # 构建时测试运行是否正常的
    传入参数 = sys.argv
    if len(传入参数) == 2:
        参数1 = 传入参数[1]
        if 参数1 == "test":
            print("app run success")
            # 写出文件
            with open(_get_run_path() + "/test.txt", "w") as f:
                f.write("app run success")
            sys.exit(0)

    # 如果在window系统中存在旧的文件则自动删除
    自身路径Window = get_windows_path()
    if 自身路径Window == "":
        # print("非Window编译环境")
        return False, ""
    # 检查文件是否存在
    旧的文件名 = 自身路径Window + ".old.bak"
    if os.path.exists(旧的文件名):
        # 删除文件
        os.remove(旧的文件名)


def update_windows_app(exe资源文件路径):
    # window更新方法
    # exe资源文件路径 = r"C:\Users\csuil\.virtualenvs\QtEsayDesigner\Scripts\dist\my_app1.0.exe"
    自身路径Window = get_windows_path()
    if 自身路径Window == "":
        print("非Window编译环境")
        return False, ""
    文件名 = os.path.basename(自身路径Window)

    # 检查文件是否存在
    旧的文件名 = 自身路径Window + ".old.bak"
    if os.path.exists(旧的文件名):
        # 删除文件
        os.remove(旧的文件名)

    os.rename(自身路径Window, 旧的文件名)
    shutil.move(exe资源文件路径, 自身路径Window)
    # 删除文件 这步放到启动时检查删除就好
    # os.remove(自身路径Window + ".old.bak") 这个运行中是无法删除的

    # 结束自身运行 然后重启自己
    os.execv(自身路径Window, sys.argv)
    os.system(f"taskkill /f /im {文件名}")
    return True, ""


class download_file_thread(QThread):
    刷新进度条 = QtCore.Signal(int, str)  # 进度 提示文本

    def __init__(self, *args, **kwargs):
        super(download_file_thread, self).__init__()
        self.窗口 = kwargs.get('窗口')
        self.下载地址 = kwargs.get('下载地址')
        self.保存地址 = kwargs.get('保存地址')
        self.编辑框 = kwargs.get('编辑框')
        self.进度条 = kwargs.get('进度条')
        self.应用名称 = kwargs.get('应用名称')
        self.回调函数 = kwargs.get('回调函数')

        self.刷新进度条.connect(self.ui_refresh)

        # 绑定线程开始事件
        self.started.connect(self.ui_start)
        # 绑定线程结束事件
        self.finished.connect(self.ui_end)

    def run(self):
        if self.下载地址 == None:
            print("请传入下载地址")
            return

        def 进度(进度百分比, 已下载大小, 文件大小, 下载速率, 剩余时间):
            信息 = f"文件大小 {文件大小}MB 速度 {下载速率}MB 剩余时间 {剩余时间}秒"
            self.刷新进度条.emit(进度百分比, 信息)

        try:
            下载结果 = download_file(self.下载地址, self.保存地址, 进度)
            self.下载结果 = True
        except:
            self.下载结果 = False

    def ui_start(self):
        self.编辑框.setText(f'开始下载')

    def ui_end(self):
        print("下载结果", self.下载结果)
        print("保存地址", self.保存地址)
        self.回调函数(self.下载结果, self.保存地址)
        self.编辑框.setText(f"下载完成 {self.保存地址}")

    def ui_refresh(self, progress, meg):
        if self.编辑框:
            self.编辑框.setText(str(meg))
        if self.进度条:
            self.进度条.setValue(int(progress))


class check_update_thread(QThread):
    def __init__(self, updatejson_url, callback=None):
        super(check_update_thread, self).__init__()
        # 绑定线程开始事件
        self.started.connect(self.ui_start)
        # 绑定线程结束事件
        self.finished.connect(self.ui_end)
        self.updatejson_url = updatejson_url
        self.callback = callback

    def run(self):
        print('检查更新中')
        data = get_version_and_download_addr(self.updatejson_url)
        self.data = data
        # self.callback(self.data)
        # print("检查更新结果", data)


    def ui_start(self):
        # pass
        print("开始检查更新")
        # self.run()

    def ui_end(self):
        # data = json.dumps(self.数据, indent=4, ensure_ascii=False)
        print("检查更新结果", self.data)
        self.callback(self.data)
