# hook-importlib.py
# 确保正确包含importlib及其子模块，特别是metadata模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import sys

# 收集importlib的所有子模块
hiddenimports = collect_submodules('importlib')

# 添加特别容易丢失的模块
additional_modules = [
    'importlib.metadata',
    'importlib.resources',
    'importlib.abc',
    'importlib.machinery',
    'importlib.util',
    'importlib._bootstrap',
    'importlib._bootstrap_external'
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 如果Python版本>=3.8，添加importlib.metadata._meta
if sys.version_info >= (3, 8):
    meta_module = 'importlib.metadata._meta'
    if meta_module not in hiddenimports:
        hiddenimports.append(meta_module)

# 收集数据文件
datas = collect_data_files('importlib')

print(f"importlib钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 