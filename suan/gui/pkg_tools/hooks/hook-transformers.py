# hook-transformers.py
# 确保正确包含transformers及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import sys
import os

# 收集transformers的所有子模块
hiddenimports = collect_submodules('transformers')

# 添加特别容易丢失的模块
additional_modules = [
    'transformers.generation',
    'transformers.generation.utils',
    'transformers.generation.candidate_generator',
    'transformers.models.auto',
    'transformers.models.auto.modeling_auto',
    'transformers.models.auto.auto_factory',
    # 添加关键依赖模块
    'transformers.utils.versions',  # 依赖检查模块
    'transformers.dependency_versions_check',  # 依赖版本检查模块
    'tqdm',  # 直接加入tqdm依赖
    'tqdm.auto',  # tqdm自动选择模块
    'regex',  # 添加regex依赖
    'packaging.version',  # 版本解析模块
    'packaging.specifiers',  # 版本规格模块
    'importlib.metadata',  # 用于版本检查
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 确保将tqdm库捆绑到打包内容中
try:
    import tqdm
    tqdm_path = os.path.dirname(tqdm.__file__)
    print(f"transformers钩子: tqdm库路径 {tqdm_path}")
    print(f"transformers钩子: 使用的tqdm版本 {tqdm.__version__}")
except ImportError:
    print("WARNING: transformers钩子: 无法导入tqdm，可能导致运行时错误")

# 确保将regex库捆绑到打包内容中
try:
    import regex
    regex_path = os.path.dirname(regex.__file__)
    regex_version = getattr(regex, "__version__", "未知")
    print(f"transformers钩子: regex库路径 {regex_path}")
    print(f"transformers钩子: 使用的regex版本 {regex_version}")
    
    # 检查是否为已知的问题版本
    if regex_version == "2019.12.17":
        print("警告: regex版本为2019.12.17，这可能与transformers不兼容")
except ImportError:
    print("WARNING: transformers钩子: 无法导入regex，可能导致运行时错误")

# 尝试添加importlib.metadata依赖
try:
    import importlib.metadata
    print(f"transformers钩子: importlib.metadata可用")
except ImportError:
    print("WARNING: transformers钩子: 无法导入importlib.metadata")

# 收集数据文件
datas = collect_data_files('transformers')

print(f"transformers钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 