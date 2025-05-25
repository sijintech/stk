from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib
import sys
import os

# 收集yaml的所有子模块
hiddenimports = collect_submodules('yaml')

# 添加特别容易丢失的模块
additional_modules = [
    'yaml.loader',
    'yaml.dumper',
    'yaml.constructor',
    'yaml.representer',
    'yaml.resolver',
    'yaml.emitter',
    'yaml.parser',
    'yaml.scanner',
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 检查yaml是否可用，并打印版本信息
try:
    import yaml
    yaml_version = getattr(yaml, "__version__", "未知")
    print(f"yaml钩子: 找到PyYAML版本 {yaml_version}")
    
    # 检查版本是否满足要求
    from packaging import version
    if version.parse(yaml_version) < version.parse("5.1"):
        print(f"警告: PyYAML版本 {yaml_version} 低于transformers要求的最低版本5.1")
except ImportError:
    print("警告: yaml钩子: 无法导入PyYAML库")

# 收集数据文件
datas = collect_data_files('yaml')

# 尝试收集PyYAML的元数据
try:
    import importlib.metadata
    # 注意：在importlib.metadata中使用的是"PyYAML"而不是"yaml"
    dist = importlib.metadata.distribution('PyYAML')
    if hasattr(dist, '_path'):
        metadata_location = os.path.dirname(dist._path)
        if os.path.isdir(metadata_location):
            for item in os.listdir(metadata_location):
                if item.endswith('.dist-info') and ('pyyaml' in item.lower() or 'yaml' in item.lower()):
                    info_dir = os.path.join(metadata_location, item)
                    datas.append((info_dir, item))
                    print(f"yaml钩子: 添加元数据目录: {info_dir}")
except Exception as e:
    print(f"警告: yaml钩子: 获取元数据时出错: {e}")

print(f"yaml钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 