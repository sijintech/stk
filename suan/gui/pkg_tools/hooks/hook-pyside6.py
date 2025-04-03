# -*- coding: utf-8 -*-
"""
PySide6模块的PyInstaller钩子 (自动生成)
收集Qt插件和资源文件
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs, get_module_file_attribute
import os

# 自动生成的依赖列表
hiddenimports = ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg', 'PySide6.QtXml', 'PySide6.QtNetwork', 'PySide6.QtPrintSupport']

# 收集额外的子模块
additional_modules = collect_submodules('PySide6')
for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集PySide6数据文件
datas = collect_data_files('PySide6')

# 收集Qt插件
pyside6_dir = os.path.dirname(get_module_file_attribute('PySide6.__init__'))
plugins_dir = os.path.join(pyside6_dir, 'plugins')
designer_dir = os.path.join(pyside6_dir, 'Designer')
qml_dir = os.path.join(pyside6_dir, 'qml')

if os.path.isdir(plugins_dir):
    datas.extend([(plugins_dir, 'PySide6/plugins')])
if os.path.isdir(designer_dir):
    datas.extend([(designer_dir, 'PySide6/Designer')])
if os.path.isdir(qml_dir):
    datas.extend([(qml_dir, 'PySide6/qml')])

# 收集Qt动态库
binaries = collect_dynamic_libs('PySide6')

print(f"PySide6钩子: 收集了 {len(hiddenimports)} 个子模块, {len(datas)} 个数据文件和 {len(binaries)} 个动态库文件")
