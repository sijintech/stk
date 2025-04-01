#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
依赖管理和自动更新辅助脚本
用于生成、维护、更新项目依赖管理
"""

import os
import sys
import re
import subprocess
import platform
import toml
from pathlib import Path

def get_project_root():
    """获取项目根目录"""
    # 假设当前脚本在项目的gui目录下
    return Path(__file__).parent

def scan_imports(directory=None):
    """扫描项目中所有Python文件中导入的模块"""
    if directory is None:
        directory = get_project_root()
    
    standard_libs = set()
    try:
        # 获取Python标准库列表
        process = subprocess.run(
            [sys.executable, "-c", "import sys; print(' '.join(sys.stdlib_module_names))"],
            capture_output=True, text=True, check=True
        )
        standard_libs = set(process.stdout.strip().split())
    except (subprocess.SubprocessError, AttributeError):
        # 在较旧版本的Python中，可能没有stdlib_module_names
        standard_libs = {'os', 'sys', 'time', 're', 'io', 'json', 'math', 'random',
                        'datetime', 'collections', 'typing', 'pathlib', 'shutil'}
    
    # 添加常见内置模块
    internal_modules = {'__future__', '__main__', 'builtins'}
    standard_libs.update(internal_modules)
    
    imports = set()
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py') and file != os.path.basename(__file__):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 使用正则表达式查找导入语句
                    import_lines = re.findall(r'^(?:from|import)\s+([\w\.]+)', content, re.MULTILINE)
                    
                    for imp in import_lines:
                        # 获取顶级模块
                        base_module = imp.split('.')[0]
                        if base_module and base_module not in standard_libs and not base_module.startswith('.'):
                            imports.add(base_module)
                except Exception as e:
                    print(f"警告: 无法解析文件 {os.path.join(root, file)}: {e}")
    
    # 排除项目自身的模块
    # 这里假设项目模块都在项目目录下，可能需要根据具体项目调整
    project_dirs = set(next(os.walk(directory))[1])
    imports = {imp for imp in imports if imp not in project_dirs}
    
    return sorted(list(imports))

def generate_requirements():
    """生成requirements.txt文件"""
    imports = scan_imports()
    
    # 添加已知的关键依赖（确保这些包总是被包含）
    key_packages = ['PySide6', 'vtk', 'matplotlib', 'numpy', 'pandas', 'requests', 'toml', 'pyinstaller']
    
    for pkg in key_packages:
        if pkg not in imports:
            imports.append(pkg)
    
    # 获取已安装包的版本信息
    installed_versions = {}
    try:
        process = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True, text=True, check=True
        )
        
        for line in process.stdout.splitlines():
            if '==' in line:
                pkg_name, version = line.split('==', 1)
                installed_versions[pkg_name.lower()] = version
    except subprocess.SubprocessError as e:
        print(f"警告: 无法获取已安装的包版本信息: {e}")
    
    # 生成requirements.txt内容
    requirements = []
    for pkg in imports:
        pkg_lower = pkg.lower()
        if pkg_lower in installed_versions:
            requirements.append(f"{pkg}=={installed_versions[pkg_lower]}")
        else:
            requirements.append(pkg)
    
    # 写入requirements.txt
    req_path = get_project_root() / "requirements.txt"
    with open(req_path, 'w', encoding='utf-8') as f:
        f.write("# 自动生成的依赖列表 - 由 update_dependencies.py 更新\n")
        f.write("# 重新生成命令: python update_dependencies.py\n\n")
        f.write("\n".join(requirements))
    
    print(f"已生成 requirements.txt，包含 {len(requirements)} 个包")
    return req_path

def update_poetry_file():
    """更新 pyproject.toml 文件（如果使用 Poetry）"""
    project_root = get_project_root()
    pyproject_path = project_root / "pyproject.toml"
    
    if not pyproject_path.exists():
        print("未找到 pyproject.toml 文件，跳过 Poetry 更新")
        return
    
    try:
        # 读取现有的 pyproject.toml
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            pyproject = toml.load(f)
        
        # 获取导入的包
        imports = scan_imports()
        key_packages = ['PySide6', 'vtk', 'matplotlib', 'numpy', 'pandas', 'requests', 'toml', 'pyinstaller']
        for pkg in key_packages:
            if pkg not in imports:
                imports.append(pkg)
        
        # 确保 tool.poetry.dependencies 存在
        if 'tool' not in pyproject:
            pyproject['tool'] = {}
        if 'poetry' not in pyproject['tool']:
            pyproject['tool']['poetry'] = {}
        if 'dependencies' not in pyproject['tool']['poetry']:
            pyproject['tool']['poetry']['dependencies'] = {}
        
        dependencies = pyproject['tool']['poetry']['dependencies']
        
        # 获取已安装包的版本信息
        installed_versions = {}
        try:
            process = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True, text=True, check=True
            )
            
            for line in process.stdout.splitlines():
                if '==' in line:
                    pkg_name, version = line.split('==', 1)
                    installed_versions[pkg_name.lower()] = version
        except subprocess.SubprocessError as e:
            print(f"警告: 无法获取已安装的包版本信息: {e}")
        
        # 确保 Python 依赖存在且正确
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        dependencies['python'] = f"^{python_version}"
        
        # 更新依赖
        for pkg in imports:
            pkg_lower = pkg.lower()
            if pkg_lower in installed_versions and pkg_lower not in dependencies:
                dependencies[pkg] = f"^{installed_versions[pkg_lower]}"
            elif pkg_lower not in dependencies:
                dependencies[pkg] = "*"  # 使用任意版本
        
        # 写回文件
        with open(pyproject_path, 'w', encoding='utf-8') as f:
            toml.dump(pyproject, f)
        
        print(f"已更新 pyproject.toml")
    except Exception as e:
        print(f"更新 pyproject.toml 时出错: {e}")

def create_platform_specific_spec():
    """创建特定平台的spec文件"""
    system = platform.system()
    template_spec_path = get_project_root() / "main.spec"
    
    if not template_spec_path.exists():
        print("无法找到模板spec文件")
        return
    
    with open(template_spec_path, 'r', encoding='utf-8') as f:
        spec_content = f.read()
    
    # 根据平台创建特定的spec文件
    if system == "Windows":
        platform_spec_path = get_project_root() / "windows.spec"
        # 可以在这里修改Windows特定的配置
    elif system == "Darwin":
        platform_spec_path = get_project_root() / "macos.spec"
        # macOS特定配置
    else:
        platform_spec_path = get_project_root() / "linux.spec"
        # Linux特定配置
    
    with open(platform_spec_path, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print(f"已创建平台特定的spec文件: {platform_spec_path}")

def main():
    """主函数"""
    print("==== STK项目依赖管理和自动更新工具 ====")
    print(f"当前Python版本: {sys.version}")
    print(f"当前操作系统: {platform.system()} {platform.release()}")
    
    # 生成requirements.txt
    req_path = generate_requirements()
    print(f"依赖文件已保存到: {req_path}")
    
    # 更新Poetry文件（如果存在）
    update_poetry_file()
    
    # 创建平台特定的spec文件
    create_platform_specific_spec()
    
    print("\n提示: 生成可执行文件命令:")
    print("  pyinstaller main.spec")
    print("完成！")

if __name__ == "__main__":
    main() 