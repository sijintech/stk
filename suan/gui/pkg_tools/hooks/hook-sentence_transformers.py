# hook-sentence_transformers.py
# 确保正确包含sentence_transformers及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集sentence_transformers的所有子模块
hiddenimports = collect_submodules('sentence_transformers')

# 添加transformers相关依赖
additional_modules = [
    'transformers',
    'transformers.generation',
    'transformers.generation.utils',
    'transformers.generation.candidate_generator',
    'transformers.models.auto',
    'transformers.models.auto.modeling_auto',
    'transformers.models.auto.auto_factory',
    # 添加tqdm相关依赖
    'tqdm',
    'tqdm.auto',
    'tqdm.std', 
    'tqdm.utils',
    'transformers.utils.versions',        # 依赖tqdm的版本检查模块
    'transformers.dependency_versions_check',  # 依赖检查模块
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 检查tqdm是否可用，并打印版本信息
try:
    import tqdm
    print(f"sentence_transformers钩子: 找到tqdm版本 {tqdm.__version__}")
except ImportError:
    print("WARNING: sentence_transformers钩子: 无法导入tqdm，这可能导致运行时错误")

# 收集数据文件
datas = collect_data_files('sentence_transformers')

print(f"sentence_transformers钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 