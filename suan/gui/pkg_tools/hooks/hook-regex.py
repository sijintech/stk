# hook-regex.py
# 确保正确包含regex库及其元数据

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib
import sys
import os

# 收集regex的所有子模块
hiddenimports = collect_submodules('regex')

# 检查regex是否可用，并打印版本信息
try:
    import regex
    if hasattr(regex, "__version__"):
        print(f"regex钩子: 找到regex版本 {regex.__version__}")
        # 检查是否为已知的问题版本
        if regex.__version__ == "2019.12.17":
            print("警告: 检测到regex版本为2019.12.17，这可能与transformers不兼容")
    else:
        print("regex钩子: 无法确定regex版本")
except ImportError:
    print("警告: regex钩子: 无法导入regex库")

# 收集数据文件
datas = collect_data_files('regex')

# 尝试收集regex的元数据
try:
    import importlib.metadata
    dist = importlib.metadata.distribution('regex')
    if hasattr(dist, '_path'):
        metadata_location = os.path.dirname(dist._path)
        if os.path.isdir(metadata_location):
            for item in os.listdir(metadata_location):
                if item.endswith('.dist-info') and 'regex' in item:
                    info_dir = os.path.join(metadata_location, item)
                    datas.append((info_dir, item))
                    print(f"regex钩子: 添加元数据目录: {info_dir}")
except Exception as e:
    print(f"警告: regex钩子: 获取元数据时出错: {e}")

print(f"regex钩子: 收集了 {len(hiddenimports)} 个子模块和 {len(datas)} 个数据文件") 