# hook-sentence_transformers.py
# 确保正确包含sentence_transformers及其子模块

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import os
import glob
import importlib

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
    # 显式添加albert模型相关模块
    'transformers.models.albert',
    'transformers.models.albert.modeling_albert', 
    'transformers.models.albert.tokenization_albert',
    'transformers.models.albert.configuration_albert',
    # 添加其他常用模型
    'transformers.models.bert',
    'transformers.models.roberta',
    'transformers.models.distilbert',
    'transformers.models.electra',
    'transformers.models.mpnet',
    'transformers.models.deberta',
    'transformers.models.deberta_v2',
    'transformers.models.xlm_roberta',
    # 添加tqdm相关依赖
    'tqdm',
    'tqdm.auto',
    'tqdm.std', 
    'tqdm.utils',
    # 添加regex相关依赖
    'regex',
    # 添加requests相关依赖
    'requests',
    'urllib3',
    'certifi',
    'idna',
    'charset_normalizer',
    # 添加filelock依赖
    'filelock',
    # 添加huggingface_hub依赖
    'huggingface_hub',
    'huggingface_hub.utils',
    'huggingface_hub.file_download',
    'huggingface_hub.hf_api',
    'huggingface_hub.hub_mixin',
    # 添加safetensors依赖
    'safetensors',
    'safetensors.torch',
    'safetensors.numpy',
    # 添加yaml依赖
    'yaml',
    'yaml.loader',
    'yaml.dumper',
    'transformers.utils.versions',        # 依赖tqdm和regex的版本检查模块
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

# 检查regex是否可用，并打印版本信息
try:
    import regex
    regex_version = getattr(regex, "__version__", "未知")
    print(f"sentence_transformers钩子: 找到regex版本 {regex_version}")
    
    # 检查是否为已知的问题版本
    if regex_version == "2019.12.17":
        print("警告: regex版本为2019.12.17，这可能与transformers不兼容")
except ImportError:
    print("WARNING: sentence_transformers钩子: 无法导入regex，这可能导致运行时错误")

# 检查requests是否可用，并打印版本信息
try:
    import requests
    requests_version = getattr(requests, "__version__", "未知")
    print(f"sentence_transformers钩子: 找到requests版本 {requests_version}")
except ImportError:
    print("WARNING: sentence_transformers钩子: 无法导入requests，这可能导致运行时错误")

# 检查filelock是否可用，并打印版本信息
try:
    import filelock
    filelock_version = getattr(filelock, "__version__", "未知")
    print(f"sentence_transformers钩子: 找到filelock版本 {filelock_version}")
except ImportError:
    print("WARNING: sentence_transformers钩子: 无法导入filelock，这可能导致运行时错误")

# 检查huggingface_hub是否可用，并打印版本信息
try:
    import huggingface_hub
    hub_version = getattr(huggingface_hub, "__version__", "未知")
    print(f"sentence_transformers钩子: 找到huggingface_hub版本 {hub_version}")
    
    # 检查版本是否满足要求
    from packaging import version
    if version.parse(hub_version) < version.parse("0.26.0"):
        print(f"警告: huggingface_hub版本 {hub_version} 低于transformers要求的最低版本0.26.0")
except ImportError:
    print("WARNING: sentence_transformers钩子: 无法导入huggingface_hub，这可能导致运行时错误")

# 检查safetensors是否可用，并打印版本信息
try:
    import safetensors
    safetensors_version = getattr(safetensors, "__version__", "未知")
    print(f"sentence_transformers钩子: 找到safetensors版本 {safetensors_version}")
    
    # 检查版本是否满足要求
    from packaging import version
    if version.parse(safetensors_version) < version.parse("0.4.3"):
        print(f"警告: safetensors版本 {safetensors_version} 低于transformers要求的最低版本0.4.3")
except ImportError:
    print("WARNING: sentence_transformers钩子: 无法导入safetensors，这可能导致运行时错误")

# 检查yaml是否可用，并打印版本信息
try:
    import yaml
    yaml_version = getattr(yaml, "__version__", "未知")
    print(f"sentence_transformers钩子: 找到yaml版本 {yaml_version}")
    
    # 检查版本是否满足要求
    from packaging import version
    if version.parse(yaml_version) < version.parse("5.1"):
        print(f"警告: yaml版本 {yaml_version} 低于transformers要求的最低版本5.1")
except ImportError:
    print("WARNING: sentence_transformers钩子: 无法导入yaml，这可能导致运行时错误")

# 收集数据文件
datas = collect_data_files('sentence_transformers')

# 添加：手动收集sentence_transformers使用的transformers模型目录
try:
    import transformers
    transformers_path = os.path.dirname(transformers.__file__)
    models_path = os.path.join(transformers_path, 'models')
    
    # 查找所有模型目录
    model_dirs = glob.glob(os.path.join(models_path, '*'))
    for model_dir in model_dirs:
        if os.path.isdir(model_dir):
            model_name = os.path.basename(model_dir)
            rel_path = os.path.join('transformers', 'models', model_name)
            # 添加整个模型目录到datas
            print(f"添加模型目录: {model_name}")
            datas.append((model_dir, rel_path))
    
    # 特别确保添加albert模型
    albert_dir = os.path.join(models_path, 'albert')
    if os.path.isdir(albert_dir):
        print(f"添加albert模型目录: {albert_dir}")
        datas.append((albert_dir, os.path.join('transformers', 'models', 'albert')))
    else:
        print(f"警告: 找不到albert模型目录: {albert_dir}")
    
    # 添加sentence_transformers可能使用的其他模型
    common_models = ['bert', 'roberta', 'distilbert', 'mpnet', 'deberta', 'deberta_v2', 'xlm_roberta']
    for model_name in common_models:
        model_dir = os.path.join(models_path, model_name)
        if os.path.isdir(model_dir):
            print(f"添加常用模型目录: {model_name}")
            datas.append((model_dir, os.path.join('transformers', 'models', model_name)))
except ImportError:
    print("WARNING: 无法导入transformers，无法收集模型目录")
except Exception as e:
    print(f"WARNING: 收集transformers模型目录时出错: {str(e)}")

print(f"sentence_transformers钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 