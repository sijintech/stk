---
title: 项目文件介绍
description: 主要介绍下pyqt下各文件用途
---

### 项目结构
```
pyqt
├── .venv/
├── src/
│   ├── icons/ #存放图标
│   ├── __init__.py
│   ├── Updater  #程序的自动更新模块
│   ├── center_widget.py #程序窗口中间展示执行用户代码后的效果部分（如VTK渲染窗口,matplotlib的画布）
│   ├── info_bar.py #程序窗口的中下部分显示用户代码，打印终端信息部分
│   ├── left_sidebar.py #程序窗口左边展示用户项目文件结构节点部分
│   ├── main.py #程序运行入口
│   ├── right_sidebar.py #程序窗口右边展示用户代码运行时的一些状态量
│   ├── statusbar.py #程序窗口下方显示用户代码的运行状态
│   ├── toolbar.py #程序窗口上方工具栏
│   ├── version.py #存放程序版本信息，主要方便自动化修改程序版本信息而建立的
│   ├── licence.txt #存放用户安装nsis安装包时显示的许可证信息
│   ├── build_nsis.nsi #用于将可执行文件打包成nsis安装包
├── confs 存放一些配置文件
│   ├── main.spec #用于pyinstaller将py程序打包成可执行文件
│   ├── pyproject.toml #用于上传pypi的设置文件
│   ├── workspace.suan
├── scripts 存放git workflows的脚本
│   ├── deploy.py #上传更新的程序到阿里云的oss服务器
│   ├── fix_toml_version.py #用于git action修改pyproject.toml中的版本信息
│   ├── run_write_version.py #用于git action修改version.py中的程序版本信息
│   ├── update.py #上传更新文件到阿里云的oss服务器
├── LICENSE #用于上传pypi的许可证

```