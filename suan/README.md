# STK 应用程序

## 特定依赖库版本
依赖及版本范围以仓库根目录 `pyproject.toml` 为准（旧 Qt 桌面使用 `desktop` 可选组件，打包使用 `build`）。

## 开发环境
- Python 3.10–3.14
- Qt 桌面为旧客户端，兼容 Windows/Linux/MacOS；服务器 Runtime 仅支持 Linux；桌面主线为 [Blender 原生工作台](../blender/README.md)

## 如何运行
    在仓库根目录执行 python -m pip install '.[desktop]'，然后运行 suan-gui

## 如何打包
如果想要带终端窗口，先设置main.spec文件里面的console=True，
然后再运行 
```bash
$ cd suan/gui
$ pyinstaller main.spec
```
或者运行 
```bash
$ python -m PyInstaller -F --clean --noconfirm --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py
```

如果不想要带终端窗口，先设置main.spec文件里面的console=False，
然后再运行 
```bash
$ cd suan/gui
$ pyinstaller main.spec
```
或者运行 
```bash
$ python -m PyInstaller -F --clean --noconfirm -w --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py



