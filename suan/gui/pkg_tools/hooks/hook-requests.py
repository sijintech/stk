 # hook-requests.py
# 确保正确包含requests库及其元数据

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib
import sys
import os

# 收集requests的所有子模块
hiddenimports = collect_submodules('requests')

# 添加特别容易丢失的模块
additional_modules = [
    'requests.api',
    'requests.adapters',
    'requests.auth',
    'requests.cookies',
    'requests.exceptions',
    'requests.hooks',
    'requests.models',
    'requests.sessions',
    'requests.status_codes',
    'requests.structures',
    'requests.utils',
    # 添加子依赖
    'urllib3',
    'urllib3.contrib',
    'urllib3.contrib.pyopenssl',
    'urllib3.contrib.socks',
    'urllib3.util',
    'urllib3.util.retry',
    'urllib3.util.timeout',
    'urllib3.util.url',
    'certifi',
    'idna',
    'charset_normalizer',
    'chardet'  # 兼容性支持
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 检查requests是否可用，并打印版本信息
try:
    import requests
    requests_version = getattr(requests, "__version__", "未知")
    print(f"requests钩子: 找到requests版本 {requests_version}")
except ImportError:
    print("警告: requests钩子: 无法导入requests库")

# 收集数据文件
datas = collect_data_files('requests')

# 尝试收集requests的元数据
try:
    import importlib.metadata
    dist = importlib.metadata.distribution('requests')
    if hasattr(dist, '_path'):
        metadata_location = os.path.dirname(dist._path)
        if os.path.isdir(metadata_location):
            for item in os.listdir(metadata_location):
                if item.endswith('.dist-info') and 'requests' in item:
                    info_dir = os.path.join(metadata_location, item)
                    datas.append((info_dir, item))
                    print(f"requests钩子: 添加元数据目录: {info_dir}")
    
    # 收集子依赖的元数据
    for dependency in ['urllib3', 'certifi', 'idna', 'charset_normalizer', 'chardet']:
        try:
            dep_dist = importlib.metadata.distribution(dependency)
            if hasattr(dep_dist, '_path'):
                dep_location = os.path.dirname(dep_dist._path)
                if os.path.isdir(dep_location):
                    for item in os.listdir(dep_location):
                        if item.endswith('.dist-info') and dependency in item:
                            info_dir = os.path.join(dep_location, item)
                            datas.append((info_dir, item))
                            print(f"requests钩子: 添加{dependency}元数据目录: {info_dir}")
        except Exception as e:
            print(f"requests钩子: 无法获取{dependency}的元数据: {e}")
            
except Exception as e:
    print(f"警告: requests钩子: 获取元数据时出错: {e}")

print(f"requests钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件")