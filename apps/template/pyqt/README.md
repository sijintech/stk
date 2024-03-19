## 如何运行
    直接运行./src/main.py文件
## 如何打包
    如果想要带终端窗口，先设置main.spec文件里面的console=True，然后再运行 `$ pyinstaller .\src\main.spec`,或者运行 `$ pyinstaller .\src\main.py`
    如果不想要带终端窗口，先设置main.spec文件里面的console=False，然后再运行 `$ pyinstaller .\src\main.spec`,或者运行 `$ pyinstaller -w .\src\main.py`
## 如何打包并发布到github
    window下 运行批处理文件：
       `$ .\nsisbuid_and_release.bat tag_num` 
    pip install matplotlib==3.6.2
    pip install PySide6==6.4.0
    'center_widget.py', 'info_bar.py', 'right_sidebar.py', 'left_sidebar.py', 'statusbar.py', 'toolbar.py','Updater\\'


