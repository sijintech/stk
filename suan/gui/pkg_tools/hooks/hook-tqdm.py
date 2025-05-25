from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib
import sys
import os

# 收集tqdm的所有子模块
hiddenimports = collect_submodules('tqdm')

# 添加特别容易丢失的模块
additional_modules = [
    'tqdm.auto',
    'tqdm.std',
    'tqdm.utils',
    'tqdm._tqdm',
    'tqdm._tqdm_pandas',
    'tqdm._tqdm_notebook',
    'tqdm._tqdm_gui',
    'tqdm._tqdm_tk',
    'tqdm._tqdm_qt',
    'tqdm._tqdm_gtk',
    'tqdm._tqdm_widgets',
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 确保tqdm与transformers的依赖关系被正确处理
try:
    # 尝试导入tqdm并检查其版本
    import tqdm
    print(f"Found tqdm version: {tqdm.__version__}")
    
    # 确保版本大于等于4.27
    from packaging import version
    if version.parse(tqdm.__version__) < version.parse("4.27"):
        print("WARNING: tqdm版本低于4.27，可能不满足transformers的依赖要求")
except ImportError as e:
    print(f"WARNING: 无法导入tqdm或检查版本: {e}")

# 添加依赖于tqdm的库模块，以确保它们正确工作
dependencies = [
    'transformers.utils.versions',  # transformers版本检查模块，依赖tqdm
    'transformers.dependency_versions_check',  # transformers依赖检查
    'sentence_transformers.util',   # sentence_transformers工具模块，间接依赖tqdm
]

for module in dependencies:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集tqdm数据文件
datas = collect_data_files('tqdm')

print(f"tqdm钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 