# -*- mode: python ; coding: utf-8 -*-
import platform
import sys
import os
import pkgutil
import importlib
import site
from PyInstaller.utils.hooks import collect_all, collect_submodules

# 根据当前系统设置应用程序名称
system = platform.system()
if system == "Windows":
    app_name = "stk_windows"
elif system == "Darwin":
    app_name = "stk_macos"
else:
    app_name = "stk_ubuntu"

# 获取当前脚本路径
script_dir = os.path.dirname(os.path.abspath('__file__'))

# 添加需要包含的文件
added_files = [
    ('confs/*', 'confs/'),
    ('examples/*', 'examples/'),
    ('resources', 'resources'),
    ('icons', 'icons')
]

# 自动收集常用模块的依赖
def collect_dependencies(module_names):
    all_imports = []
    all_datas = []
    all_binaries = []
    
    for module_name in module_names:
        try:
            imports, datas, binaries = collect_all(module_name)
            all_imports.extend(imports)
            all_datas.extend(datas)
            all_binaries.extend(binaries)
        except Exception as e:
            print(f"警告: 收集模块 {module_name} 依赖时出错: {e}")
    
    return all_imports, all_datas, all_binaries

# 关键第三方库列表 - 可以根据项目需要扩展
key_packages = ['PySide6', 'vtk', 'matplotlib', 'numpy', 'pandas', 'requests', 'toml', 'chardet']

# 自动检测项目中导入的模块 (检查当前目录下的所有Python文件)
def scan_project_imports():
    imports = set()
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.py') and not file == 'main.spec':
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 简单解析import语句
                    for line in content.split('\n'):
                        line = line.strip()
                        if line.startswith('import ') or line.startswith('from '):
                            parts = line.replace('import ', ' ').replace('from ', ' ').split()
                            if parts and parts[0] not in ['os', 'sys', 'time', 're', '.']:
                                base_module = parts[0].split('.')[0]
                                if not base_module.startswith('.'):
                                    imports.add(base_module)
                except Exception as e:
                    print(f"无法解析文件 {os.path.join(root, file)}: {e}")
    
    return list(imports)

# 扫描项目导入
project_imports = scan_project_imports()
print(f"检测到项目中使用的模块: {project_imports}")

# 合并导入列表
all_packages = list(set(key_packages + project_imports))

# 收集所有依赖
pkg_imports, pkg_datas, pkg_binaries = collect_dependencies(all_packages)

# 确保VTK相关模块被正确包含
vtk_modules = collect_submodules('vtkmodules')

# 项目自定义模块
custom_modules = [
    'version', 'custom_logger', 'center_widget', 'Updater', 'info_bar', 'right_sidebar',
    'left_sidebar', 'statusbar', 'toolbar', 'Tab'
]

# 分析规范
a = Analysis(
    ['main.py'],
    pathex=[script_dir],
    binaries=[
        ('Updater', 'Updater'),
        ('Tab', 'Tab'),
        ('version.py', '.'),
        ('custom_logger.py', '.')
    ] + pkg_binaries,
    datas=added_files + pkg_datas,
    hiddenimports=[
        *custom_modules, 
        *vtk_modules,
        *pkg_imports,
        'vtkmodules.util.execution_model', 
        'vtkmodules.util.data_model'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# 压缩
pyz = PYZ(a.pure)

# 生成可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 开发时设为True以查看错误，发布时可改为False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/app_icon.ico',
)
