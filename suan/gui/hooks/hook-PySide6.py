"""
专门用于PySide6库的PyInstaller钩子文件
这个钩子解决了PySide6模块导入和资源文件包含的问题
"""

import os
import sys
import glob
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, get_module_file_attribute, collect_entry_point

# 解决与PySide6有关的依赖导入问题
hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'PySide6.QtPrintSupport',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtUiTools',
    'PySide6.QtXml',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
]

datas = []
binaries = []

# 获取PySide6安装路径
try:
    pyside6_path = Path(get_module_file_attribute('PySide6')).parent
    
    # 收集插件
    plugins = [
        'platforms',
        'platformthemes',
        'styles',
        'iconengines',
        'imageformats',
        'sqldrivers'
    ]
    
    # 添加插件目录
    for plugin in plugins:
        plugin_dir = os.path.join(pyside6_path, 'plugins', plugin)
        if os.path.exists(plugin_dir):
            datas.append((plugin_dir, os.path.join('PySide6', 'plugins', plugin)))
    
    # 添加translations目录
    translations_dir = os.path.join(pyside6_path, 'translations')
    if os.path.exists(translations_dir):
        datas.append((translations_dir, os.path.join('PySide6', 'translations')))
    
    # 添加qml目录
    qml_dir = os.path.join(pyside6_path, 'qml')
    if os.path.exists(qml_dir):
        datas.append((qml_dir, os.path.join('PySide6', 'qml')))
    
    # 添加libexec目录中的QtWebEngineProcess
    if sys.platform == 'win32':
        webengine_proc = os.path.join(pyside6_path, 'QtWebEngineProcess.exe')
        if os.path.exists(webengine_proc):
            binaries.append((webengine_proc, '.'))
    elif sys.platform == 'darwin':
        webengine_proc = os.path.join(pyside6_path, 'libexec', 'QtWebEngineProcess')
        if os.path.exists(webengine_proc):
            binaries.append((webengine_proc, 'libexec'))
    else:
        webengine_proc = os.path.join(pyside6_path, 'libexec', 'QtWebEngineProcess')
        if os.path.exists(webengine_proc):
            binaries.append((webengine_proc, 'libexec'))
    
    # 添加resources目录
    resources_dir = os.path.join(pyside6_path, 'resources')
    if os.path.exists(resources_dir):
        datas.append((resources_dir, os.path.join('PySide6', 'resources')))
    
    # 收集所有DLL文件(Windows)或.so文件(Linux)或.dylib文件(macOS)
    if sys.platform == 'win32':
        for dll in glob.glob(os.path.join(pyside6_path, '*.dll')):
            binaries.append((dll, '.'))
    elif sys.platform == 'linux':
        for so in glob.glob(os.path.join(pyside6_path, '*.so')):
            binaries.append((so, '.'))
    elif sys.platform == 'darwin':
        for dylib in glob.glob(os.path.join(pyside6_path, '*.dylib')):
            binaries.append((dylib, '.'))
    
except (ImportError, AttributeError) as e:
    print(f"WARNING: 无法收集PySide6资源: {e}") 