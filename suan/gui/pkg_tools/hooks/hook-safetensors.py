from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib
import sys
import os

# 收集safetensors的所有子模块
hiddenimports = collect_submodules('safetensors')

# 添加特别容易丢失的模块
additional_modules = [
    'safetensors.torch',
    'safetensors.flax',
    'safetensors.tensorflow',
    'safetensors.numpy',
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 检查safetensors是否可用，并打印版本信息
try:
    import safetensors
    safetensors_version = getattr(safetensors, "__version__", "未知")
    print(f"safetensors钩子: 找到safetensors版本 {safetensors_version}")
    
    # 检查版本是否满足要求
    from packaging import version
    if version.parse(safetensors_version) < version.parse("0.4.3"):
        print(f"警告: safetensors版本 {safetensors_version} 低于transformers要求的最低版本0.4.3")
except ImportError:
    print("警告: safetensors钩子: 无法导入safetensors库")

# 收集数据文件
datas = collect_data_files('safetensors')

# 尝试收集safetensors的元数据
try:
    import importlib.metadata
    dist = importlib.metadata.distribution('safetensors')
    if hasattr(dist, '_path'):
        metadata_location = os.path.dirname(dist._path)
        if os.path.isdir(metadata_location):
            for item in os.listdir(metadata_location):
                if item.endswith('.dist-info') and 'safetensors' in item:
                    info_dir = os.path.join(metadata_location, item)
                    datas.append((info_dir, item))
                    print(f"safetensors钩子: 添加元数据目录: {info_dir}")
except Exception as e:
    print(f"警告: safetensors钩子: 获取元数据时出错: {e}")

print(f"safetensors钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 