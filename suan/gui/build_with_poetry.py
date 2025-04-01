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
import locale
import traceback
from pathlib import Path

# 设置控制台编码
def setup_console_encoding():
    """设置控制台编码，确保中文显示正常"""
    if platform.system() == "Windows":
        try:
            # 尝试设置控制台代码页为UTF-8
            subprocess.run(["chcp", "65001"], shell=True, check=False)
        except Exception:
            pass
        
        # 设置Python标准输出编码
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 调用编码设置函数
setup_console_encoding()

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
        print(f"Error: pyproject.toml not found: {pyproject_path}")
        sys.exit(1)
    
    try:
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            return toml.load(f)
    except Exception as e:
        print(f"Error: Cannot parse pyproject.toml: {e}")
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
        print("Warning: main.spec not found, creating a basic template")
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
        print(f"Warning: main.spec file may be missing dependencies: {', '.join(missing_imports)}")
        print("Consider adding these dependencies to the hiddenimports list")

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

# 确保目录存在
for file_pattern, target_dir in added_files:
    source_dir = file_pattern.split('/*')[0] if '/*' in file_pattern else file_pattern
    if not os.path.exists(source_dir):
        try:
            os.makedirs(source_dir)
            print(f"Created directory {{source_dir}}")
        except Exception as e:
            print(f"Warning: Could not create directory {{source_dir}}: {{e}}")

# 收集VTK模块
vtk_modules = collect_submodules('vtkmodules')

# 收集关键依赖资源
all_datas = []
all_binaries = []

for package in [{dependencies_str}]:
    try:
        pkg_imports, pkg_datas, pkg_binaries = collect_all(package)
        all_datas.extend(pkg_datas)
        
        # 确保二进制文件格式正确
        valid_binaries = []
        for item in pkg_binaries:
            if isinstance(item, tuple):
                if len(item) == 2:
                    valid_binaries.append(item)
                elif len(item) > 2:
                    valid_binaries.append((item[0], item[1]))
                else:
                    print(f"Warning: Invalid binary format: {{item}}")
            else:
                print(f"Warning: Binary item is not a tuple: {{item}}")
        
        all_binaries.extend(valid_binaries)
    except Exception as e:
        print(f"Warning: Error collecting {{package}} resources: {{e}}")

# 检查并创建自定义二进制文件列表
standard_binaries = []
for item in [
    ('Updater', 'Updater'),
    ('Tab', 'Tab'),
    ('version.py', '.'),
    ('custom_logger.py', '.')
]:
    if isinstance(item, tuple) and len(item) == 2:
        standard_binaries.append(item)
    else:
        print(f"Warning: Skipping invalid binary format: {{item}}")

# 分析规范
a = Analysis(
    ['main.py'],
    pathex=[script_dir],
    binaries=standard_binaries + all_binaries,
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
        'vtkmodules.util.data_model',
        # 其他常见的隐藏导入
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'PySide6.QtNetwork',
        'matplotlib.backends.backend_qt5agg',
        'numpy.core._methods',
        'numpy.lib.format'
    ],
    hookspath=['hooks'],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['rapidfuzz.__pyinstaller'],
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
    
    print(f"Created basic spec template file: {spec_path}")

def ensure_hooks_directory():
    """确保hooks目录存在"""
    gui_dir = get_gui_dir()
    hooks_dir = gui_dir / "hooks"
    
    if not hooks_dir.exists():
        os.makedirs(hooks_dir)
        print(f"Created hooks directory: {hooks_dir}")
    
    # 创建基本的钩子文件
    hook_app_path = hooks_dir / "hook-app.py"
    if not hook_app_path.exists():
        with open(hook_app_path, 'w', encoding='utf-8') as f:
            f.write("""\"\"\"
This is a custom PyInstaller hook file to ensure all dependencies for the STK GUI application are correctly packaged.
Place this file in the project's hooks directory and reference it in main.spec.
\"\"\"

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Collect all VTK related modules
hiddenimports = collect_submodules('vtkmodules')

# Ensure these key modules are included
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

# Collect all PySide6 resources
datas, binaries, hiddenimports_pyside = collect_all('PySide6')

# Merge hidden imports
hiddenimports.extend(hiddenimports_pyside)

# These files will be packaged by PyInstaller
datas.extend([])

# These binaries will be packaged by PyInstaller
binaries.extend([])
""")
        print(f"Created hook file: {hook_app_path}")

    # 创建处理rapifuzz的钩子文件
    hook_rapidfuzz_path = hooks_dir / "hook-rapidfuzz.py"
    if not hook_rapidfuzz_path.exists():
        with open(hook_rapidfuzz_path, 'w', encoding='utf-8') as f:
            f.write("""\"\"\"
Hook for rapidfuzz package to avoid errors related to __pyinstaller attribute
\"\"\"

# Define an empty hiddenimports list to prevent PyInstaller from looking for rapidfuzz.__pyinstaller
hiddenimports = []
datas = []
binaries = []
""")
        print(f"Created rapidfuzz hook file: {hook_rapidfuzz_path}")

def ensure_required_directories():
    """确保所有必需的目录存在"""
    gui_dir = get_gui_dir()
    
    # 检查并创建必要的目录
    required_dirs = [
        'dist',
        'hooks',
        'Updater',
        'Tab',
        'confs',
        'examples',
        'resources',
        'icons'
    ]
    
    for dir_name in required_dirs:
        dir_path = gui_dir / dir_name
        if not dir_path.exists():
            try:
                os.makedirs(dir_path)
                print(f"Created required directory: {dir_path}")
            except Exception as e:
                print(f"Warning: Could not create directory {dir_path}: {e}")

def run_build():
    """运行构建过程"""
    gui_dir = get_gui_dir()
    
    # 确保当前目录是GUI目录
    os.chdir(gui_dir)
    
    # 在运行PyInstaller之前确保所有必需的文件和目录都存在
    ensure_required_files()
    
    # 构建命令行参数
    pyinstaller_args = [
        "--clean",  # 清理旧的构建文件
        "--noconfirm",  # 不确认覆盖
        "--log-level=INFO",  # 设置日志级别
    ]
    
    if platform.system() == "Windows":
        pyinstaller_cmd = ["pyinstaller"] + pyinstaller_args + ["main.spec"]
    elif platform.system() == "Darwin":
        pyinstaller_cmd = ["python", "-m", "PyInstaller"] + pyinstaller_args + ["main.spec"]
    else:
        pyinstaller_cmd = ["python3", "-m", "PyInstaller"] + pyinstaller_args + ["main.spec"]
    
    print(f"Starting build: {' '.join(pyinstaller_cmd)}")
    try:
        # 运行构建命令并捕获输出
        process = subprocess.run(
            pyinstaller_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False  # 不要立即引发异常，让我们自己处理错误
        )
        
        # 打印输出
        if process.stdout:
            print("=== Build Output ===")
            print(process.stdout)
        
        # 打印错误
        if process.stderr:
            print("=== Build Errors ===")
            print(process.stderr)
        
        # 检查是否构建成功
        if process.returncode != 0:
            print(f"Build failed with exit code {process.returncode}")
            
            # 检查错误中是否包含已知问题
            if "too many values to unpack" in process.stderr:
                print("\nERROR DETECTED: 'too many values to unpack'")
                print("This is usually caused by an invalid binary format in the spec file.")
                print("Please check the format of the 'binaries' list in main.spec")
            
            # 创建错误日志文件
            with open(gui_dir / "build_error.log", 'w', encoding='utf-8') as f:
                f.write("=== BUILD ERROR LOG ===\n\n")
                f.write(f"Command: {' '.join(pyinstaller_cmd)}\n")
                f.write(f"Exit Code: {process.returncode}\n\n")
                f.write("=== STDOUT ===\n")
                f.write(process.stdout)
                f.write("\n\n=== STDERR ===\n")
                f.write(process.stderr)
            
            print(f"Error details have been saved to {gui_dir / 'build_error.log'}")
            sys.exit(1)
        else:
            print("Build successful!")
    except Exception as e:
        print(f"Exception during build: {e}")
        traceback.print_exc()
        sys.exit(1)

def ensure_required_files():
    """确保所有必需的文件存在"""
    gui_dir = get_gui_dir()
    
    # 检查必需的文件
    required_files = [
        ('version.py', '# Generated version\nversion = "0.0.0"\n'),
        ('custom_logger.py', '# Placeholder for custom logger\ndef setup_logger():\n    pass\n')
    ]
    
    for file_name, default_content in required_files:
        file_path = gui_dir / file_name
        if not file_path.exists():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(default_content)
                print(f"Created placeholder file: {file_path}")
            except Exception as e:
                print(f"Warning: Could not create file {file_path}: {e}")

def create_debug_log(dependencies):
    """创建调试日志，记录环境和依赖情况"""
    gui_dir = get_gui_dir()
    log_path = gui_dir / "build_debug.log"
    
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("=== STK Build Debug Log ===\n\n")
        
        f.write(f"Python version: {sys.version}\n")
        f.write(f"Operating system: {platform.system()} {platform.release()}\n")
        f.write(f"Platform: {platform.platform()}\n\n")
        
        f.write("=== Directory Structure ===\n")
        f.write(f"Current working directory: {os.getcwd()}\n")
        f.write(f"GUI directory: {gui_dir}\n")
        f.write(f"Project root: {get_project_root()}\n\n")
        
        # 记录目录内容
        f.write("=== Directory Contents ===\n")
        for path, dirs, files in os.walk(gui_dir):
            rel_path = os.path.relpath(path, gui_dir)
            if rel_path == ".":
                f.write(f"Root directory: {len(files)} files, {len(dirs)} subdirectories\n")
            else:
                f.write(f"Directory {rel_path}: {len(files)} files, {len(dirs)} subdirectories\n")
        
        f.write("\n=== Extracted Dependencies ===\n")
        for dep in dependencies:
            f.write(f"- {dep}\n")
        
        f.write("\n=== Installed Package Versions ===\n")
        try:
            process = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True, text=True, check=True
            )
            f.write(process.stdout)
        except Exception as e:
            f.write(f"Could not get installed package information: {e}\n")
        
        # 添加系统环境变量信息
        f.write("\n=== Environment Variables ===\n")
        for key, value in os.environ.items():
            # 过滤敏感信息
            if not any(sensitive in key.lower() for sensitive in ['token', 'key', 'secret', 'password', 'auth']):
                f.write(f"{key}={value}\n")
    
    print(f"Created debug log: {log_path}")

def is_ci_environment():
    """检测是否在CI/CD环境中运行"""
    # 检查常见的CI环境变量
    ci_env_vars = [
        'CI',
        'GITHUB_ACTIONS',
        'GITLAB_CI',
        'TRAVIS',
        'CIRCLECI',
        'JENKINS_URL',
        'TEAMCITY_VERSION'
    ]
    
    return any(os.environ.get(var) for var in ci_env_vars)

def prepare_build_environment():
    """准备构建环境"""
    # 确保所有必需的目录存在
    ensure_required_directories()
    
    # 确保所有必需的文件存在
    ensure_required_files()

def main():
    """主函数"""
    print("==== Poetry-based STK Project Packaging Tool ====")
    print(f"Current Python version: {sys.version}")
    print(f"Current operating system: {platform.system()} {platform.release()}")
    
    # 准备构建环境
    prepare_build_environment()
    
    # 加载 pyproject.toml
    pyproject = load_pyproject()
    print("Loaded pyproject.toml")
    
    # 提取依赖
    dependencies = extract_dependencies(pyproject)
    print(f"Extracted {len(dependencies)} dependencies from pyproject.toml")
    
    # 确保hooks目录存在
    ensure_hooks_directory()
    
    # 确保 PyInstaller spec 文件存在并包含所需依赖
    ensure_pyinstaller_spec(dependencies)
    
    # 创建调试日志
    create_debug_log(dependencies)
    
    # 检查是否在CI环境中运行
    in_ci = is_ci_environment()
    
    # 在CI环境中自动构建，在本地环境中询问用户
    if in_ci:
        print("CI environment detected, automatically starting build process...")
        run_build()
    else:
        try:
            response = input("Start build now? (y/n): ")
            if response.lower() in ['y', 'yes']:
                run_build()
            else:
                print("Build canceled, you can run 'pyinstaller main.spec' manually later")
        except EOFError:
            # 即使在非交互式环境中也自动构建
            print("Non-interactive environment detected, automatically starting build process...")
            run_build()

if __name__ == "__main__":
    main() 