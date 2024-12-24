import os
from PyInstaller.utils.hooks import collect_data_files

# 获取当前工作目录，并根据该目录确定 toolkits 的路径
toolkits_dir = os.path.join(os.getcwd(), '../../toolkits')  # toolkits 作为一个包

# 自动收集所有插件目录下的 cli.py 和相关文件
plugin_data = []
block_cipher = None

# 遍历 toolkits 目录，查找包含 cli.py 的子目录
for plugin_name in os.listdir(toolkits_dir):
    plugin_path = os.path.join(toolkits_dir, plugin_name)
    # 确保是目录，并且该目录下有 cli.py 文件
    if os.path.isdir(plugin_path) and os.path.exists(os.path.join(plugin_path, 'cli.py')):
        print(f"Adding plugin: {plugin_path}")
        # 将整个插件目录添加到打包列表
        plugin_data.append((plugin_path, os.path.join('toolkits', plugin_name)))

        # 如果插件目录下还有其他需要包含的文件，使用 collect_data_files 自动收集
        plugin_data.extend(collect_data_files(plugin_name))
print("Collected plugin data:", plugin_data)

# 以下是 PyInstaller spec 文件的其他部分
a = Analysis(
    ['main.py'],  # 主脚本
    pathex=['.','../../toolkits'],  # 包含路径
    binaries=[],
    datas=plugin_data,  # 添加 plugin_data，其中包含 toolkits 中的插件目录
    hiddenimports=['importlib','click'],  # 如果有隐式导入的模块，可以添加到这里
    hookspath=[],  # 如果有特定的 hooks，您可以添加到这里
    runtime_hooks=[],  # 如果有需要的 runtime hooks
    excludes=[],  # 如果有需要排除的模块，可以在这里列出
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

# 创建压缩包
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 创建可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='suan',  # 可执行文件名称
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 在控制台运行
)

# 收集所有数据文件
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='suan',
)
