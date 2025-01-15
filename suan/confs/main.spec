# -*- mode: python ; coding: utf-8 -*-
import platform

# 根据当前系统设置应用程序名称
system = platform.system()
if system == "Windows":
    app_name = "stk_windows"
elif system == "Darwin":
    app_name = "stk_macos"
else:
    app_name = "stk_ubuntu"

added_files = [('../confs', 'confs' ),('../examples', 'examples')]

a = Analysis(
    ['../gui/main.py'],
    pathex=['.'],
    binaries=[],
    datas=added_files,
    hiddenimports=['center_widget', 'Updater','info_bar', 'right_sidebar',
    'left_sidebar', 'statusbar', 'toolbar', 'PySide6', 'vtk', 'matplotlib',
    'numpy','requests','toml','vtkmodules'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
