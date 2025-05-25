from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib
import sys
import os

# 收集huggingface_hub的所有子模块
hiddenimports = collect_submodules('huggingface_hub')

# 添加特别容易丢失的模块
additional_modules = [
    'huggingface_hub.utils',
    'huggingface_hub.file_download',
    'huggingface_hub.hf_api',
    'huggingface_hub.hub_mixin',
    'huggingface_hub.repository',
    'huggingface_hub.constants',
    'huggingface_hub.inference_api',
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 检查huggingface_hub是否可用，并打印版本信息
try:
    import huggingface_hub
    hub_version = getattr(huggingface_hub, "__version__", "未知")
    print(f"huggingface_hub钩子: 找到huggingface_hub版本 {hub_version}")
    
    # 检查版本是否满足要求
    from packaging import version
    if version.parse(hub_version) < version.parse("0.26.0"):
        print(f"警告: huggingface_hub版本 {hub_version} 低于transformers要求的最低版本0.26.0")
except ImportError:
    print("警告: huggingface_hub钩子: 无法导入huggingface_hub库")

# 收集数据文件
datas = collect_data_files('huggingface_hub')

# 尝试收集huggingface_hub的元数据
try:
    import importlib.metadata
    # 注意：在importlib.metadata中使用的是带连字符的名称
    dist = importlib.metadata.distribution('huggingface-hub')
    if hasattr(dist, '_path'):
        metadata_location = os.path.dirname(dist._path)
        if os.path.isdir(metadata_location):
            for item in os.listdir(metadata_location):
                if item.endswith('.dist-info') and 'huggingface' in item and 'hub' in item:
                    info_dir = os.path.join(metadata_location, item)
                    datas.append((info_dir, item))
                    print(f"huggingface_hub钩子: 添加元数据目录: {info_dir}")
except Exception as e:
    print(f"警告: huggingface_hub钩子: 获取元数据时出错: {e}")

print(f"huggingface_hub钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 