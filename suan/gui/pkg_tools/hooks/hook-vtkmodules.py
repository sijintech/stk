# -*- coding: utf-8 -*-
"""
vtkmodules模块的PyInstaller钩子 (自动生成)
确保所有VTK子模块被包含
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 确保收集vtkmodules的所有子模块
hiddenimports = collect_submodules('vtkmodules')

# 添加关键模块，确保它们被包含
additional_modules = [
    'vtkmodules',  # 添加vtkmodules本身
    'vtkmodules.all',
    'vtkmodules.qt.QVTKRenderWindowInteractor',
    'vtkmodules.util.numpy_support',
    'vtkmodules.util.colors',
    'vtkmodules.util.vtkAlgorithm',
    'vtkmodules.util.vtkConstants',
    'vtkmodules.util.keys',
    'vtkmodules.util.misc',
    'vtkmodules.util.vtkImageExportToArray',
    'vtkmodules.util.vtkImageImportFromArray',
    'vtkmodules.util.execution_model',
    'vtkmodules.util.data_model',
    'vtkmodules.web',
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集数据文件
datas = collect_data_files('vtkmodules')

print(f"vtkmodules钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件")
