"""
这是一个自定义的PyInstaller钩子文件，用于确保STK GUI应用程序的所有依赖项都被正确打包。
将此文件放在项目的hooks目录中，并在main.spec中引用它。
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

# 收集所有VTK相关模块
hiddenimports = collect_submodules('vtkmodules')

# 确保这些关键模块被包含
hiddenimports.extend([
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
    'PySide6.QtNetwork',
    'matplotlib.backends.backend_qt5agg',
    'numpy.core._methods',
    'numpy.lib.format',
    'pandas._libs.tslibs.timedeltas',
    'pandas._libs.tslibs.nattype',
    'pandas._libs.tslibs.np_datetime',
    'vtk.vtkIOXMLPython',
    'vtk.vtkRenderingCorePython',
    'vtk.vtkCommonCorePython',
    'vtk.vtkFiltersCoreModule',
])

# 收集所有PySide6资源
datas, binaries, hiddenimports_pyside = collect_all('PySide6')

# 合并隐藏导入
hiddenimports.extend(hiddenimports_pyside)

# 这些文件会被PyInstaller打包
datas.extend([])

# 这些二进制文件会被PyInstaller打包
binaries.extend([]) 