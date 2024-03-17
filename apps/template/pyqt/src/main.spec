# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['center_widget.py', 'info_bar.py', 'right_sidebar.py', 'left_sidebar.py', 'statusbar.py', 'toolbar.py'],
    binaries=[],
    datas=[],
    hiddenimports=['center_widget', 'info_bar', 'right_sidebar', 'left_sidebar', 'statusbar', 'toolbar', 'PyQt5', 'vtk', 'matplotlib', 'numpy'],
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
    name='main',
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
