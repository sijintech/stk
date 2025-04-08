# -*- mode: python ; coding: utf-8 -*-
import platform
import sys
import os
from pathlib import Path

# 将当前目录添加到路径中，以便导入依赖模块
gui_dir = os.path.dirname(os.path.abspath('__file__'))
if gui_dir not in sys.path:
    sys.path.insert(0, gui_dir)

# 尝试导入依赖提取函数
try:
    from pkg_tools.dependencies import extract_dependencies
    # 提取依赖
    extracted_imports = extract_dependencies()
    print(f"成功提取 {len(extracted_imports)} 个依赖项")
except ImportError:
    print("警告: 无法导入dependencies模块，将使用默认依赖列表")
    extracted_imports = []

# 根据当前系统设置应用程序名称
system = platform.system()
if system == "Windows":
    app_name = "stk_windows"
elif system == "Darwin":
    app_name = "stk_macos"
else:
    app_name = "stk_ubuntu"

# 获取当前脚本路径
script_dir = os.path.dirname(os.path.abspath('__file__'))

# 添加需要包含的文件
added_files = [
    ('confs/*', 'confs/'),
    ('examples/*', 'examples/'),
    ('resources', 'resources'),
    ('icons', 'icons')
]

# 合并所有隐藏导入（依赖完全由dependencies模块提供）
all_hidden_imports = extracted_imports

# 创建钩子目录(如果不存在)
hooks_dir = os.path.join(gui_dir, 'pkg_tools', 'hooks')
if not os.path.exists(hooks_dir):
    os.makedirs(hooks_dir)
    print(f"创建钩子目录: {hooks_dir}")

# 分析规范
a = Analysis(
    ['main.py'],
    pathex=[script_dir],
    binaries=[
        ('Updater', 'Updater'),
        ('Tab', 'Tab'),
        ('version.py', '.'),
        ('custom_logger.py', '.'),
        ('left_sidebar.py', '.'),
        ('right_sidebar.py', '.'),
        ('toolbar.py', '.'),
        ('statusbar.py', '.'),
        ('info_bar.py', '.'),
        ('center_widget.py', '.'),
    ],
    datas=added_files,
    hiddenimports=all_hidden_imports
    hookspath=[hooks_dir],  # 使用绝对路径
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# 压缩
pyz = PYZ(a.pure)

# 生成可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 设置为False隐藏终端窗口，True显示终端窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)