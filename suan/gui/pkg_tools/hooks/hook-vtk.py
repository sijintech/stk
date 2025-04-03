# -*- coding: utf-8 -*-
"""
VTK模块的PyInstaller钩子 (自动生成)
收集VTK的所有子模块和数据文件
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 自动生成的依赖列表
hiddenimports = ['vtk', 'vtk.vtkCommonCore', 'vtk.vtkCommonCorePython', 'vtk.vtkRenderingCorePython', 'vtk.vtkFiltersCoreModule', 'vtk.vtkIOXMLPython', 'vtk.vtkInteractionStyle', 'vtk.vtkRenderingOpenGL2', 'vtkmodules', 'vtkmodules.all', 'vtkmodules.qt.QVTKRenderWindowInteractor', 'vtkmodules.util.numpy_support', 'vtkmodules.util.execution_model', 'vtkmodules.util.data_model', 'vtkmodules.util.colors', 'vtkmodules.util.vtkAlgorithm', 'vtkmodules.util.vtkConstants', 'vtkmodules.util.misc', 'vtkmodules.vtkCommonCore', 'vtkmodules.vtkRenderingCore', 'vtkmodules.vtkIOXML', 'vtkmodules.vtkFiltersCore', 'vtkmodules.vtkImagingCore', 'vtkmodules.vtkRenderingOpenGL2', 'vtkmodules.web']

# 收集额外的子模块
additional_modules = collect_submodules('vtkmodules')
for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集数据文件
datas = collect_data_files('vtkmodules')

print(f"VTK钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件")
