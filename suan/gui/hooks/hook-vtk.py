"""
专门用于VTK库的PyInstaller钩子文件
这个钩子解决了VTK模块导入和资源文件包含的问题
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

# 收集所有VTK子模块
hiddenimports = collect_submodules('vtk')
hiddenimports.extend(collect_submodules('vtkmodules'))

# 确保这些关键模块被包含
hiddenimports.extend([
    'vtkmodules.all',
    'vtkmodules.qt.QVTKRenderWindowInteractor',
    'vtkmodules.util',
    'vtkmodules.numpy_interface.dataset_adapter',
    'vtkmodules.util.numpy_support',
    'vtkmodules.util.colors',
    'vtkmodules.util.vtkImageExportToArray',
    'vtkmodules.util.vtkImageImportFromArray',
    'vtkmodules.util.execution_model',
    'vtkmodules.util.data_model',
])

# 收集VTK数据文件
datas = collect_data_files('vtk')
datas.extend(collect_data_files('vtkmodules'))

# 收集VTK动态库
binaries = collect_dynamic_libs('vtk')
binaries.extend(collect_dynamic_libs('vtkmodules')) 