# STK 应用程序

## 特定依赖库版本
    pip install matplotlib==3.6.2
    pip install PySide6==6.4.0
    pip install vtk==9.2.6
    pip install chardet==5.1.0
    pip install toml==0.10.2
    pip install PyInstaller==5.13.0

## 开发环境
- Python 3.9+
- Windows/Linux/MacOS 兼容

## 如何运行
    直接运行./src/main.py文件

## 如何打包
如果想要带终端窗口，先设置main.spec文件里面的console=True，
然后再运行 
```bash
$ pyinstaller .\src\confs\main.spec
```
或者运行 
```bash
$ python -m PyInstaller -F --clean --noconfirm --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py
```

如果不想要带终端窗口，先设置main.spec文件里面的console=False，
然后再运行 
```bash
$ pyinstaller .\src\main.spec
```
或者运行 
```bash
$ python -m PyInstaller -F --clean --noconfirm -w --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py



