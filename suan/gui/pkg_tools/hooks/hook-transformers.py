# hook-transformers.py
# 确保正确包含transformers及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata
import sys
import os
import glob
import importlib
import shutil

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
    # 显式添加albert模型相关模块
    'transformers.models.albert',
    'transformers.models.albert.modeling_albert',
    'transformers.models.albert.tokenization_albert',
    'transformers.models.albert.configuration_albert',
    # 显式添加trainer和processing_utils模块
    'transformers.trainer',
    'transformers.processing_utils',
    'transformers.trainer_pt_utils',
    'transformers.trainer_utils',
    'transformers.training_args',
    # 添加关键依赖模块
    'transformers.utils.versions',  # 依赖检查模块
    'transformers.dependency_versions_check',  # 依赖版本检查模块
    'tqdm',  # 直接加入tqdm依赖
    'tqdm.auto',  # tqdm自动选择模块
    'regex',  # 添加regex依赖
    'requests',  # 添加requests依赖
    'urllib3',  # requests的依赖
    'certifi',  # requests的依赖
    'filelock',  # 添加filelock依赖
    'huggingface_hub',  # 添加huggingface_hub依赖
    'huggingface_hub.utils',  # hub的关键模块
    'huggingface_hub.file_download',  # hub的文件下载模块
    'safetensors',  # 添加safetensors依赖
    'safetensors.torch',  # safetensors的torch相关功能
    'yaml',  # 添加yaml依赖
    'yaml.loader',  # yaml的加载器
    'yaml.dumper',  # yaml的导出器
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

# 确保将requests库捆绑到打包内容中
try:
    import requests
    requests_path = os.path.dirname(requests.__file__)
    requests_version = getattr(requests, "__version__", "未知")
    print(f"transformers钩子: requests库路径 {requests_path}")
    print(f"transformers钩子: 使用的requests版本 {requests_version}")
except ImportError:
    print("WARNING: transformers钩子: 无法导入requests，可能导致运行时错误")

# 确保将filelock库捆绑到打包内容中
try:
    import filelock
    filelock_path = os.path.dirname(filelock.__file__)
    filelock_version = getattr(filelock, "__version__", "未知")
    print(f"transformers钩子: filelock库路径 {filelock_path}")
    print(f"transformers钩子: 使用的filelock版本 {filelock_version}")
except ImportError:
    print("WARNING: transformers钩子: 无法导入filelock，可能导致运行时错误")

# 确保将huggingface_hub库捆绑到打包内容中
try:
    import huggingface_hub
    hub_path = os.path.dirname(huggingface_hub.__file__)
    hub_version = getattr(huggingface_hub, "__version__", "未知")
    print(f"transformers钩子: huggingface_hub库路径 {hub_path}")
    print(f"transformers钩子: 使用的huggingface_hub版本 {hub_version}")
    
    # 检查是否满足最低版本要求
    from packaging import version
    if version.parse(hub_version) < version.parse("0.26.0"):
        print(f"警告: huggingface_hub版本 {hub_version} 低于transformers要求的最低版本0.26.0")
except ImportError:
    print("WARNING: transformers钩子: 无法导入huggingface_hub，可能导致运行时错误")

# 确保将safetensors库捆绑到打包内容中
try:
    import safetensors
    safetensors_path = os.path.dirname(safetensors.__file__)
    safetensors_version = getattr(safetensors, "__version__", "未知")
    print(f"transformers钩子: safetensors库路径 {safetensors_path}")
    print(f"transformers钩子: 使用的safetensors版本 {safetensors_version}")
    
    # 检查是否满足最低版本要求
    from packaging import version
    if version.parse(safetensors_version) < version.parse("0.4.3"):
        print(f"警告: safetensors版本 {safetensors_version} 低于transformers要求的最低版本0.4.3")
except ImportError:
    print("WARNING: transformers钩子: 无法导入safetensors，可能导致运行时错误")

# 确保将yaml库捆绑到打包内容中
try:
    import yaml
    yaml_path = os.path.dirname(yaml.__file__)
    yaml_version = getattr(yaml, "__version__", "未知")
    print(f"transformers钩子: yaml库路径 {yaml_path}")
    print(f"transformers钩子: 使用的yaml版本 {yaml_version}")
    
    # 检查是否满足最低版本要求
    from packaging import version
    if version.parse(yaml_version) < version.parse("5.1"):
        print(f"警告: yaml版本 {yaml_version} 低于transformers要求的最低版本5.1")
except ImportError:
    print("WARNING: transformers钩子: 无法导入yaml，可能导致运行时错误")

# 尝试添加importlib.metadata依赖
try:
    import importlib.metadata
    print(f"transformers钩子: importlib.metadata可用")
except ImportError:
    print("WARNING: transformers钩子: 无法导入importlib.metadata")

# 收集transformers的元数据
try:
    metadata = copy_metadata('transformers')
    print(f"transformers钩子: 收集到 {len(metadata)} 个元数据文件")
except Exception as e:
    print(f"WARNING: 收集transformers元数据时出错: {str(e)}")

# 收集数据文件 - 确保包含所有transformers的Python文件
datas = collect_data_files('transformers')

# 添加：手动收集transformers库的所有Python文件
try:
    import transformers
    transformers_path = os.path.dirname(transformers.__file__)
    print(f"transformers钩子: transformers库路径: {transformers_path}")
    
    # 添加整个transformers目录（确保包含__init__.py文件）
    py_files = []
    
    # 收集所有.py文件 - 包括__init__.py
    for root, dirs, files in os.walk(transformers_path):
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, os.path.dirname(transformers_path))
                rel_dir = os.path.dirname(rel_path)
                py_files.append((full_path, rel_dir))
    
    # 确保所有收集到的Python文件都被添加到datas中
    for py_file, rel_dir in py_files:
        # 避免重复添加
        if not any(src == py_file for src, _ in datas):
            datas.append((py_file, rel_dir))
    
    print(f"transformers钩子: 手动收集了 {len(py_files)} 个Python文件")
    
    # 特别处理__init__.py文件
    init_file = os.path.join(transformers_path, '__init__.py')
    if os.path.exists(init_file):
        print(f"transformers钩子: 确认__init__.py存在: {init_file}")
        # 确保已添加到datas
        if not any(src == init_file for src, _ in datas):
            datas.append((init_file, 'transformers'))
    else:
        print(f"警告: transformers钩子: 找不到__init__.py文件: {init_file}")
    
    # 查找所有模型目录
    model_dirs = glob.glob(os.path.join(transformers_path, 'models', '*'))
    for model_dir in model_dirs:
        if os.path.isdir(model_dir):
            model_name = os.path.basename(model_dir)
            rel_path = os.path.join('transformers', 'models', model_name)
            # 添加整个模型目录到datas
            print(f"添加模型目录: {model_name}")
            datas.append((model_dir, rel_path))
    
    # 特别确保添加albert模型
    albert_dir = os.path.join(transformers_path, 'models', 'albert')
    if os.path.isdir(albert_dir):
        print(f"添加albert模型目录: {albert_dir}")
        datas.append((albert_dir, os.path.join('transformers', 'models', 'albert')))
    else:
        print(f"警告: 找不到albert模型目录: {albert_dir}")
except ImportError:
    print("WARNING: 无法导入transformers，无法收集模型目录")
except Exception as e:
    print(f"WARNING: 收集transformers模型目录时出错: {str(e)}")

print(f"transformers钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 