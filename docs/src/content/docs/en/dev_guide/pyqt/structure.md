---
title: Project File Introduction
description: Introduction to the purpose of each file under PyQt
---

### Project Structure
```
pyqt
├── .venv/
├── src/
│   ├── icons/ # Store icons
│   ├── __init__.py
│   ├── Updater  # Program's automatic update module
│   ├── center_widget.py # Middle part of the program window that displays the effect after executing user code (such as VTK rendering window, matplotlib canvas)
│   ├── info_bar.py # Lower middle part of the program window that displays user code and terminal information
│   ├── left_sidebar.py # Left part of the program window that displays the user project file structure nodes
│   ├── main.py # Program entry point
│   ├── right_sidebar.py # Right part of the program window that displays some state variables during user code execution
│   ├── statusbar.py # Bottom part of the program window that displays the running status of user code
│   ├── toolbar.py # Top toolbar of the program window
│   ├── version.py # Stores program version information, mainly established to facilitate automated modification of program version information
│   ├── licence.txt # Stores license information displayed when users install the NSIS installation package
│   ├── build_nsis.nsi # Used to package executable files into NSIS installation packages
├── confs # Store configuration files
│   ├── main.spec # Used by PyInstaller to package Python programs into executable files
│   ├── pyproject.toml # Configuration file for uploading to PyPI
│   ├── workspace.suan
├── scripts # Store Git workflows scripts
│   ├── deploy.py # Upload updated programs to Alibaba Cloud OSS server
│   ├── fix_toml_version.py # Used by Git Action to modify version information in pyproject.toml
│   ├── run_write_version.py # Used by Git Action to modify program version information in version.py
│   ├── update.py # Upload update files to Alibaba Cloud OSS server
├── LICENSE # License for uploading to PyPI
```