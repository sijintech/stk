# hook-packaging.py
# 确保正确包含packaging库及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集packaging的所有子模块
hiddenimports = collect_submodules('packaging')

# 添加特别容易丢失的模块
additional_modules = [
    'packaging.version',
    'packaging.specifiers',
    'packaging.requirements',
    'packaging.markers',
    'packaging.tags',
    'packaging.utils'
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集数据文件
datas = collect_data_files('packaging')

print(f"packaging钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 