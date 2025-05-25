# hook-filelock.py
# 确保正确包含filelock库及其元数据

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib
import sys
import os

# 收集filelock的所有子模块
hiddenimports = collect_submodules('filelock')

# 检查filelock是否可用，并打印版本信息
try:
    import filelock
    filelock_version = getattr(filelock, "__version__", "未知")
    print(f"filelock钩子: 找到filelock版本 {filelock_version}")
except ImportError:
    print("警告: filelock钩子: 无法导入filelock库")

# 收集数据文件
datas = collect_data_files('filelock')

# 尝试收集filelock的元数据
try:
    import importlib.metadata
    dist = importlib.metadata.distribution('filelock')
    if hasattr(dist, '_path'):
        metadata_location = os.path.dirname(dist._path)
        if os.path.isdir(metadata_location):
            for item in os.listdir(metadata_location):
                if item.endswith('.dist-info') and 'filelock' in item:
                    info_dir = os.path.join(metadata_location, item)
                    datas.append((info_dir, item))
                    print(f"filelock钩子: 添加元数据目录: {info_dir}")
except Exception as e:
    print(f"警告: filelock钩子: 获取元数据时出错: {e}")

print(f"filelock钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 