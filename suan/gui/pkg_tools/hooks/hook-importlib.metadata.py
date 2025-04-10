# hook-importlib.metadata.py
# 确保正确包含包元数据，解决"无法找到包"问题

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import sys
import os
import importlib.metadata

# 收集importlib.metadata的所有子模块
hiddenimports = collect_submodules('importlib.metadata')

# 添加packaging模块以支持版本处理
hiddenimports += [
    'packaging',
    'packaging.version',
    'packaging.specifiers',
    'packaging.requirements'
]

# 关注的包列表
packages_of_interest = [
    'tqdm',
    'transformers',
    'sentence_transformers',
    'torch',
    'numpy'
]

# 收集关键包的元数据
datas = []
metadata_added = []

for package in packages_of_interest:
    try:
        # 尝试获取包的版本信息
        version = importlib.metadata.version(package)
        print(f"包 {package} 的版本: {version}")
        
        # 尝试获取包的元数据文件位置
        try:
            dist = importlib.metadata.distribution(package)
            metadata_location = os.path.dirname(dist._path)
            
            if metadata_location and metadata_location not in metadata_added:
                # 直接包含整个site-packages目录中的.dist-info或.egg-info目录
                if os.path.isdir(metadata_location):
                    for item in os.listdir(metadata_location):
                        if item.endswith('.dist-info') and package in item:
                            info_dir = os.path.join(metadata_location, item)
                            datas.append((info_dir, item))
                            metadata_added.append(info_dir)
                            print(f"添加元数据目录: {info_dir}")
                        elif item.endswith('.egg-info') and package in item:
                            info_dir = os.path.join(metadata_location, item)
                            datas.append((info_dir, item))
                            metadata_added.append(info_dir)
                            print(f"添加元数据目录: {info_dir}")
        except Exception as e:
            print(f"警告: 获取包 {package} 的元数据位置时出错: {e}")
    
    except importlib.metadata.PackageNotFoundError:
        print(f"警告: 未找到包 {package} 的元数据")
    except Exception as e:
        print(f"警告: 处理包 {package} 时出错: {e}")

print(f"importlib.metadata钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个元数据目录") 