# hook-transformers.py
# 确保正确包含transformers及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集transformers的所有子模块
hiddenimports = collect_submodules('transformers')

# 添加特别容易丢失的模块
hiddenimports += [
    'transformers.generation',
    'transformers.generation.utils',
    'transformers.generation.candidate_generator',
    'transformers.models.auto',
    'transformers.models.auto.modeling_auto',
    'transformers.models.auto.auto_factory',
]

# 收集数据文件
datas = collect_data_files('transformers') 