---
title: Environment Configuration
description: Environment configuration on Windows and Linux, IDE configuration (PyCharm, VSCode non-default settings)
---

## Windows

### Python (3.9) Environment Configuration

You can follow this configuration blog: [Detailed Python Installation and Environment Setup Tutorial](https://blog.csdn.net/weixin_55154866/article/details/134197661)

### Configure Python Virtual Environment (Optional)

Creating a virtual environment can avoid packaging unnecessary third-party packages when building the application, reducing the program size.
Run the following code in the command line:

```sh
python -m venv .venv # Create virtual environment
. .venv\Scripts\activate # Use virtual environment
python.exe -m pip install -U pip
```

### Download Python Third-Party Packages

Run the following code in the command line:

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

### Configure NSIS Packaging Environment (for Windows Program Installation Package)

Run the following code in the command line:

```sh
iwr -useb get.scoop.sh -outfile 'install.ps1' # Download install.ps1 script from get.scoop.sh
.\install.ps1 -RunAsAdmin # Run install.ps1 script with administrator privileges
scoop update
scoop bucket add extras
scoop install nsis
```

### Running

#### Run the Program
    Directly run the ./src/main.py file
    
#### Package as Executable File
If you want a terminal window, first set console=True in the main.spec file, then run `$ pyinstaller .\src\main.spec`, or run `$ python -m PyInstaller -F --clean --noconfirm --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py`  

If you don't want a terminal window, first set console=False in the main.spec file, then run `$ pyinstaller .\src\main.spec`, or run `$ python -m PyInstaller -F --clean --noconfirm -w --name suan_pyqt --hidden-import center_widget --hidden-import info_bar --hidden-import right_sidebar --hidden-import left_sidebar --hidden-import statusbar --hidden-import toolbar --hidden-import PySide6 --hidden-import vtk --hidden-import matplotlib --hidden-import numpy -p .\src\ main.py`

#### Package as NSIS Installation Package
Run the following code in the terminal:

```sh
makensis apps\template\pyqt\src\build_nsis.nsi
```

## Ubuntu

### Python (3.9) Environment Configuration

You can follow this configuration blog: [How to Install Python 3.9 on Ubuntu (Ubuntu 20.04)](https://blog.vlssu.com/views/tech-sharing/linux/python3.9.html#%E7%AE%80%E6%B4%81%E5%AE%89%E8%A3%85)

### Configure Python Virtual Environment (Optional)

Creating a virtual environment can avoid packaging unnecessary third-party packages when building the application, reducing the program size. Run the following commands in the terminal:

```sh
python3 -m venv .venv # Create virtual environment
source .venv/bin/activate # Activate virtual environment
python3 -m pip install -U pip
```

### Download Python Third-Party Packages

Run the following code in the terminal:

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

### Configure NSIS Packaging Environment (for Windows Program Installation Package)

Run the following code in the terminal:

```sh
sudo apt update # Update package index
sudo apt install nsis # Install NSIS
```

## PyCharm Configuration

### Configure Python Environment

You can follow this configuration blog: [How to Configure Python Environment in PyCharm](https://blog.csdn.net/yy17111342926/article/details/128904552)

### Configure Git

You can follow this configuration blog: [Detailed Tutorial on Configuring Git in PyCharm Python IDE](https://blog.csdn.net/yangcangong/article/details/134397131)  
Remote repository address: https://github.com/sijintech/stk.git

## VSCode Configuration

### Configure Python Environment

You can follow this configuration blog: [Setting Up Python Development Environment in VSCode](https://blog.csdn.net/yy17111342926/article/details/128904552)

### Configure Git

You can follow this configuration blog: [VSCode Git Configuration](https://www.cnblogs.com/ostrich-sunshine/p/11329444.html)  
Remote repository address: https://github.com/sijintech/stk.git