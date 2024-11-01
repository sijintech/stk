# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['../src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=['center_widget', 'Updater','info_bar', 'right_sidebar', 'left_sidebar', 'statusbar', 'toolbar', 'PySide6', 'vtk', 'matplotlib', 'numpy','requests','toml'],
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
    name='stk',
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
