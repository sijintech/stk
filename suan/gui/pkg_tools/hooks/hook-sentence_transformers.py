# hook-sentence_transformers.py
# 确保正确包含sentence_transformers及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集sentence_transformers的所有子模块
hiddenimports = collect_submodules('sentence_transformers')

# 添加transformers相关依赖
hiddenimports += [
    'transformers',
    'transformers.generation',
    'transformers.generation.utils',
    'transformers.generation.candidate_generator',
    'transformers.models.auto',
    'transformers.models.auto.modeling_auto',
    'transformers.models.auto.auto_factory',
]

# 收集数据文件
datas = collect_data_files('sentence_transformers') 