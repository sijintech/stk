# -*- mode: python ; coding: utf-8 -*-


# 创建一个分析对象，用于分析 Python 脚本的依赖关系和打包选项
a = Analysis(
    # 指定要分析的 Python 脚本文件列表
    ['main.py','left_sidebar.py','center_widget.py','right_sidebar.py','toolbar.py','statusbar.py','info_bar.py'],
    # 额外的路径列表，用于查找依赖项
    pathex=[],
    # 二进制文件列表
    binaries=[],
    # 数据文件列表
    datas=[],
    # 隐藏导入的模块列表，这些模块将不被打包到输出文件中
    hiddenimports=['PyQt5','vtk','matplotlib','pandas', 'numpy','sys','left_sidebar','center_widget','right_sidebar','toolbar','statusbar','info_bar'],
    # 钩子文件路径列表
    hookspath=[],
    # 钩子配置字典
    hooksconfig={},
    # 运行时钩子列表
    runtime_hooks=[],
    # 排除的模块列表，这些模块将不被分析
    excludes=[],
    # 是否创建归档文件
    noarchive=False,
)

# 创建 PYZ 对象，用于将纯 Python 代码打包成一个 Python 二进制资源
pyz = PYZ(a.pure)

# 创建 EXE 对象，用于打包可执行文件
exe = EXE(
    # 纯 Python 代码的 PYZ 对象
    pyz,
    # 脚本文件列表
    a.scripts,
    # 二进制文件列表
    a.binaries,
    # 数据文件列表
    a.datas,
    # 其他资源文件列表
    [],
    # 输出可执行文件的名称
    name='suan_pyqt',
    # 是否启用调试模式
    debug=False,
    # 是否忽略引导程序的信号
    bootloader_ignore_signals=False,
    # 是否剥离调试信息
    strip=False,
    # 是否使用 UPX 压缩
    upx=True,
    # 不压缩的模块列表
    upx_exclude=[],
    # 运行时临时目录
    runtime_tmpdir=None,
    # 是否为控制台应用程序
    console=False,
    # 是否禁用窗口化的回溯
    disable_windowed_traceback=False,
    # 是否模拟命令行参数
    argv_emulation=False,
    # 目标架构
    target_arch=None,
    # 代码签名标识
    codesign_identity=None,
    # 权限文件路径
    entitlements_file=None,
)

