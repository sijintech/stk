---
title: 环境配置
description: Windows，Linux上的环境配置，ide配置（pycharm，vscode非默认的设置）
---

## Windows

### python（3.9）环境配置

可以按照这篇配置博客进行：[超详细的 Python 安装和环境搭建教程](https://blog.csdn.net/weixin_55154866/article/details/134197661)

### 配置 py 虚拟环境(可选)

创建虚拟环境，可以避免之后打包程序时，打包不必要的第三方包，减小程序大小
在命令行中运行下面代码：

```sh
python -m venv .venv # 创建虚拟环境
. .venv\Scripts\activate # 使用虚拟环境
python.exe -m pip install -U pip
```

### 下载 py 第三方包

在命令行中运行下面代码：

```sh
pip install pyinstaller
pip install matplotlib==3.6.2
pip install PySide6==6.4.0
pip install vtk
pip install pandas
pip install numpy
pip install requests
pip install oss2
```

### 配置 NSIS 打包环境

在命令行中运行下面代码：

```sh
iwr -useb get.scoop.sh -outfile 'install.ps1' # 从 get.scoop.sh 下载 install.ps1 脚本
.\install.ps1 -RunAsAdmin # 以管理员权限运行 install.ps1 脚本
scoop update
scoop bucket add extras
scoop install nsis
```

### 运行
#### 运行程序
    直接运行./src/main.py文件
#### 打包成可执行文件
如果想要带终端窗口，先设置main.spec文件里面的console=True，然后再运行 `$ pyinstaller .\src\main.spec`,或者运行 `$ python -m PyInstaller -F --clean --noconfirm --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py`  

如果不想要带终端窗口，先设置main.spec文件里面的console=False，然后再运行 `$ pyinstaller .\src\main.spec`,或者运行 `$ python -m PyInstaller -F --clean --noconfirm -w --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py`

#### 打包成Nsis安装包
在终端中运行下面代码：

```sh
makensis apps\template\pyqt\src\build_nsis.nsi
```

## Ubuntu

### python（3.9）环境配置

可以按照这篇配置博客进行：[在 Ubuntu 如何安装 Python3.9（Ubuntu 20.04）](https://blog.vlssu.com/views/tech-sharing/linux/python3.9.html#%E7%AE%80%E6%B4%81%E5%AE%89%E8%A3%85)

### 配置 Python 虚拟环境 (可选)

创建虚拟环境，以避免在打包程序时包含不必要的第三方库，从而减小程序的大小。在终端中运行以下命令：

```sh
python3 -m venv .venv # 创建虚拟环境
source .venv/bin/activate # 激活虚拟环境
python3 -m pip install -U pip
```

### 下载 py 第三方包

在终端中运行下面代码：

```sh
pip install pyinstaller
pip install matplotlib==3.6.2
pip install PySide6==6.4.0
pip install vtk
pip install pandas
pip install numpy
pip install requests
pip install oss2
```

### 配置 NSIS 打包环境

在终端中运行下面代码：

```sh
sudo apt update # 更新软件包索引
sudo apt install nsis # 安装 NSIS
```

## Pycharm 配置

### 配置 python 环境

可以按照这篇配置博客进行：[pycharm 如何配置 python 环境](https://blog.csdn.net/yy17111342926/article/details/128904552)

### 配置 git

可以按照这篇配置博客进行：[Python 集成开发环境 pycharm 配置 git 详细教程](https://blog.csdn.net/yangcangong/article/details/134397131)  
远程仓库地址为：https://github.com/sijintech/stk.git

## Vscode 配置

### 配置 python 环境

可以按照这篇配置博客进行：[在 VSCode 中搭建 Python 开发环境](https://blog.csdn.net/yy17111342926/article/details/128904552)

### 配置 git

可以按照这篇配置博客进行：[VSCode 配置 git](https://www.cnblogs.com/ostrich-sunshine/p/11329444.html)  
远程仓库地址为：https://github.com/sijintech/stk.git

