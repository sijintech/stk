# hook-pyyaml.py
# PyYAML包在导入时使用的是'yaml'，这个钩子是为了处理'pyyaml'名称的情况

from PyInstaller.utils.hooks import collect_data_files
import sys
import os

# 从yaml钩子导入hiddenimports
from PyInstaller.utils.hooks import collect_submodules
hiddenimports = collect_submodules('yaml')

# 收集数据文件
datas = collect_data_files('yaml')

# 尝试收集PyYAML的元数据
try:
    import importlib.metadata
    dist = importlib.metadata.distribution('PyYAML')
    if hasattr(dist, '_path'):
        metadata_location = os.path.dirname(dist._path)
        if os.path.isdir(metadata_location):
            for item in os.listdir(metadata_location):
                if item.endswith('.dist-info') and ('pyyaml' in item.lower() or 'yaml' in item.lower()):
                    info_dir = os.path.join(metadata_location, item)
                    datas.append((info_dir, item))
                    print(f"pyyaml钩子: 添加元数据目录: {info_dir}")
except Exception as e:
    print(f"警告: pyyaml钩子: 获取元数据时出错: {e}")

print(f"pyyaml钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 