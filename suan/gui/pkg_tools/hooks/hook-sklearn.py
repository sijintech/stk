# hook-sklearn.py
# 确保正确包含sklearn及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集sklearn的所有子模块
hiddenimports = collect_submodules('sklearn')

# 添加特别容易丢失的模块
hiddenimports += [
    'sklearn.metrics',
    'sklearn.metrics.roc_curve',
    'sklearn.utils',
    'sklearn.utils.validation',
    'sklearn.utils._array_api',
    'sklearn.utils._param_validation',
    'sklearn.base',
]

# 收集数据文件
datas = collect_data_files('sklearn') 