#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
基于 Poetry 的 PyInstaller 打包辅助脚本
此脚本从 pyproject.toml 读取依赖信息，自动配置 PyInstaller
"""

import os
import sys
import platform
import subprocess
import shutil
import toml
from pathlib import Path

def get_project_root():
    """获取项目根目录"""
    # 假设当前脚本在项目的gui目录下
    return Path(__file__).parent.parent.parent

def get_gui_dir():
    """获取GUI目录"""
    return Path(__file__).parent

def load_pyproject():
    """加载 pyproject.toml 文件"""
    project_root = get_project_root()
    pyproject_path = project_root / "pyproject.toml"
    
    if not pyproject_path.exists():
        print(f"错误: 找不到 pyproject.toml 文件: {pyproject_path}")
        sys.exit(1)
    
    try:
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            return toml.load(f)
    except Exception as e:
        print(f"错误: 无法解析 pyproject.toml 文件: {e}")
        sys.exit(1)

def extract_dependencies(pyproject):
    """从 pyproject.toml 中提取依赖"""
    dependencies = []
    
    if 'tool' in pyproject and 'poetry' in pyproject['tool'] and 'dependencies' in pyproject['tool']['poetry']:
        for pkg, version in pyproject['tool']['poetry']['dependencies'].items():
            if pkg != 'python':  # 排除Python自身
                dependencies.append(pkg)
    
    # 添加必要的系统包（这些包可能未在 pyproject.toml 中指定）
    essential_packages = ['PySide6', 'vtk', 'matplotlib', 'numpy', 'pandas', 'requests', 'toml', 'pyinstaller']
    for pkg in essential_packages:
        if pkg not in dependencies:
            dependencies.append(pkg)
    
    return dependencies

def ensure_pyinstaller_spec(dependencies):
    """确保 PyInstaller spec 文件存在并包含所需依赖"""
    gui_dir = get_gui_dir()
    spec_path = gui_dir / "main.spec"
    
    # 如果不存在spec文件，创建一个基本模板
    if not spec_path.exists():
        print("警告: 未找到 main.spec 文件，将创建一个基本模板")
        create_basic_spec_template(spec_path, dependencies)
        return
    
    # 读取现有spec文件内容
    with open(spec_path, 'r', encoding='utf-8') as f:
        spec_content = f.read()
    
    # 检查spec文件是否包含关键包的hiddenimports
    missing_imports = []
    for dep in dependencies:
        if dep.lower() not in spec_content.lower():
            missing_imports.append(dep)
    
    if missing_imports:
        print(f"警告: main.spec 文件中可能缺少以下依赖: {', '.join(missing_imports)}")
        print("请考虑在 hiddenimports 列表中添加这些依赖")

def create_basic_spec_template(spec_path, dependencies):
    """创建基本的 PyInstaller spec 模板"""
    system = platform.system()
    if system == "Windows":
        app_name = "stk_windows"
    elif system == "Darwin":
        app_name = "stk_macos"
    else:
        app_name = "stk_ubuntu"
    
    # 格式化依赖列表
    dependencies_str = ',\n        '.join([f"'{dep}'" for dep in dependencies])
    
    # 基本模板
    template = f"""# -*- mode: python ; coding: utf-8 -*-

import platform
import sys
import os
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

# 收集VTK模块
vtk_modules = collect_submodules('vtkmodules')

# 收集关键依赖资源
all_datas = []
all_binaries = []

for package in [{dependencies_str}]:
    try:
        pkg_imports, pkg_datas, pkg_binaries = collect_all(package)
        all_datas.extend(pkg_datas)
        all_binaries.extend(pkg_binaries)
    except Exception as e:
        print(f"警告: 收集 {{package}} 资源时出错: {{e}}")

# 分析规范
a = Analysis(
    ['main.py'],
    pathex=[script_dir],
    binaries=[
        ('Updater', 'Updater'),
        ('Tab', 'Tab'),
        ('version.py', '.'),
        ('custom_logger.py', '.')
    ] + all_binaries,
    datas=added_files + all_datas,
    hiddenimports=[
        # 项目自定义模块
        'version', 'custom_logger', 'center_widget', 'Updater', 'info_bar', 'right_sidebar',
        'left_sidebar', 'statusbar', 'toolbar', 'Tab',
        # 第三方依赖
        {dependencies_str},
        # VTK相关模块
        *vtk_modules,
        'vtkmodules.util.execution_model', 
        'vtkmodules.util.data_model'
    ],
    hookspath=['hooks'],
    hooksconfig={{}},
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
"""
    
    # 写入模板文件
    with open(spec_path, 'w', encoding='utf-8') as f:
        f.write(template)
    
    print(f"已创建基本 spec 模板文件: {spec_path}")

def ensure_hooks_directory():
    """确保hooks目录存在"""
    gui_dir = get_gui_dir()
    hooks_dir = gui_dir / "hooks"
    
    if not hooks_dir.exists():
        os.makedirs(hooks_dir)
        print(f"已创建hooks目录: {hooks_dir}")
    
    # 创建基本的钩子文件
    hook_app_path = hooks_dir / "hook-app.py"
    if not hook_app_path.exists():
        with open(hook_app_path, 'w', encoding='utf-8') as f:
            f.write("""\"\"\"
这是一个自定义的PyInstaller钩子文件，用于确保STK GUI应用程序的所有依赖项都被正确打包。
将此文件放在项目的hooks目录中，并在main.spec中引用它。
\"\"\"

from PyInstaller.utils.hooks import collect_all, collect_submodules

# 收集所有VTK相关模块
hiddenimports = collect_submodules('vtkmodules')

# 确保这些关键模块被包含
hiddenimports.extend([
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
    'PySide6.QtNetwork',
    'matplotlib.backends.backend_qt5agg',
    'numpy.core._methods',
    'numpy.lib.format',
    'pandas._libs.tslibs.timedeltas',
    'pandas._libs.tslibs.nattype',
    'pandas._libs.tslibs.np_datetime',
    'vtk.vtkIOXMLPython',
    'vtk.vtkRenderingCorePython',
    'vtk.vtkCommonCorePython',
    'vtk.vtkFiltersCoreModule',
])

# 收集所有PySide6资源
datas, binaries, hiddenimports_pyside = collect_all('PySide6')

# 合并隐藏导入
hiddenimports.extend(hiddenimports_pyside)

# 这些文件会被PyInstaller打包
datas.extend([])

# 这些二进制文件会被PyInstaller打包
binaries.extend([])
""")
        print(f"已创建钩子文件: {hook_app_path}")

def run_build():
    """运行构建过程"""
    gui_dir = get_gui_dir()
    
    # 确保当前目录是GUI目录
    os.chdir(gui_dir)
    
    # 运行PyInstaller
    system = platform.system()
    if system == "Windows":
        build_command = "pyinstaller main.spec"
    elif system == "Darwin":
        build_command = "python -m PyInstaller main.spec"
    else:
        build_command = "python3 -m PyInstaller main.spec"
    
    print(f"开始构建: {build_command}")
    try:
        subprocess.run(build_command, shell=True, check=True)
        print("构建成功!")
    except subprocess.CalledProcessError as e:
        print(f"构建失败: {e}")
        sys.exit(1)

def create_debug_log(dependencies):
    """创建调试日志，记录环境和依赖情况"""
    gui_dir = get_gui_dir()
    log_path = gui_dir / "build_debug.log"
    
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("=== STK构建调试日志 ===\n\n")
        
        f.write(f"Python版本: {sys.version}\n")
        f.write(f"操作系统: {platform.system()} {platform.release()}\n")
        f.write(f"平台: {platform.platform()}\n\n")
        
        f.write("=== 提取的依赖列表 ===\n")
        for dep in dependencies:
            f.write(f"- {dep}\n")
        
        f.write("\n=== 已安装的包版本 ===\n")
        try:
            process = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True, text=True, check=True
            )
            f.write(process.stdout)
        except Exception as e:
            f.write(f"无法获取已安装的包信息: {e}\n")
    
    print(f"已创建调试日志: {log_path}")

def main():
    """主函数"""
    print("==== 基于Poetry的STK项目打包工具 ====")
    print(f"当前Python版本: {sys.version}")
    print(f"当前操作系统: {platform.system()} {platform.release()}")
    
    # 加载 pyproject.toml
    pyproject = load_pyproject()
    print("已加载 pyproject.toml")
    
    # 提取依赖
    dependencies = extract_dependencies(pyproject)
    print(f"已从pyproject.toml提取{len(dependencies)}个依赖")
    
    # 确保hooks目录存在
    ensure_hooks_directory()
    
    # 确保 PyInstaller spec 文件存在并包含所需依赖
    ensure_pyinstaller_spec(dependencies)
    
    # 创建调试日志
    create_debug_log(dependencies)
    
    # 询问是否继续构建
    response = input("是否立即进行构建? (y/n): ")
    if response.lower() in ['y', 'yes']:
        run_build()
    else:
        print("已取消构建，您可以稍后手动运行 'pyinstaller main.spec'")

if __name__ == "__main__":
    main() 