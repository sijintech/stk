# -*- coding: utf-8 -*-
"""
Matplotlib模块的PyInstaller钩子 (自动生成)
确保所有必要的后端和资源文件被包含
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 自动生成的依赖列表
hiddenimports = ['matplotlib.backends.backend_qt5agg', 'matplotlib.backends.backend_qtagg', 'matplotlib.backends.backend_qt5', 'matplotlib.backends.backend_qt', 'matplotlib.backends.qt_compat', 'matplotlib.backends.qt_editor', 'matplotlib.backends.backend_svg', 'matplotlib.backends.backend_pdf', 'matplotlib.backends.backend_ps', 'matplotlib.backends.backend_agg', 'matplotlib.backends.backend_cairo', 'matplotlib.backends.backend_tkagg', 'matplotlib.backends._backend_tk', 'matplotlib.pyplot', 'matplotlib.figure', 'matplotlib.colors', 'matplotlib.artist', 'matplotlib.text', 'matplotlib.image']

# 收集matplotlib数据文件(包括字体)
datas = collect_data_files('matplotlib')

print(f"Matplotlib钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件")
