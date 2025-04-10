#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
钩子生成工具 - 根据pyproject.toml自动生成PyInstaller钩子文件
"""

import os
import sys
import argparse
from pathlib import Path
import importlib.util

# 确保能够导入dependencies模块
from .dependencies import get_hook_data

# 钩子目录路径
HOOKS_DIR = Path(__file__).parent / "hooks"


# 钩子模板
HOOK_TEMPLATES = {
    "matplotlib": """# -*- coding: utf-8 -*-
\"\"\"
Matplotlib模块的PyInstaller钩子 (自动生成)
确保所有必要的后端和资源文件被包含
\"\"\"

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 自动生成的依赖列表
hiddenimports = {imports}

# 收集matplotlib数据文件(包括字体)
datas = collect_data_files('matplotlib')

print(f"Matplotlib钩子: 收集了 {{len(hiddenimports)}} 个子模块和 {{len(datas)}} 个数据文件")
""",

    "vtk": """# -*- coding: utf-8 -*-
\"\"\"
VTK模块的PyInstaller钩子 (自动生成)
收集VTK的所有子模块和数据文件
\"\"\"

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 自动生成的依赖列表
hiddenimports = {imports}

# 收集额外的子模块
additional_modules = collect_submodules('vtkmodules')
for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集数据文件
datas = collect_data_files('vtkmodules')

print(f"VTK钩子: 收集了 {{len(hiddenimports)}} 个子模块和 {{len(datas)}} 个数据文件")
""",

    "vtkmodules": """# -*- coding: utf-8 -*-
\"\"\"
vtkmodules模块的PyInstaller钩子 (自动生成)
确保所有VTK子模块被包含
\"\"\"

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 确保收集vtkmodules的所有子模块
hiddenimports = collect_submodules('vtkmodules')

# 添加关键模块，确保它们被包含
additional_modules = [
    'vtkmodules',  # 添加vtkmodules本身
    'vtkmodules.all',
    'vtkmodules.qt.QVTKRenderWindowInteractor',
    'vtkmodules.util.numpy_support',
    'vtkmodules.util.colors',
    'vtkmodules.util.vtkAlgorithm',
    'vtkmodules.util.vtkConstants',
    'vtkmodules.util.keys',
    'vtkmodules.util.misc',
    'vtkmodules.util.vtkImageExportToArray',
    'vtkmodules.util.vtkImageImportFromArray',
    'vtkmodules.util.execution_model',
    'vtkmodules.util.data_model',
    'vtkmodules.web',
]

for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集数据文件
datas = collect_data_files('vtkmodules')

print(f"vtkmodules钩子: 收集了 {{len(hiddenimports)}} 个子模块和 {{len(datas)}} 个数据文件")
""",

    "PySide6": """# -*- coding: utf-8 -*-
\"\"\"
PySide6模块的PyInstaller钩子 (自动生成)
收集Qt插件和资源文件
\"\"\"

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs, get_module_file_attribute
import os

# 自动生成的依赖列表
hiddenimports = {imports}

# 收集额外的子模块
additional_modules = collect_submodules('PySide6')
for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

# 收集PySide6数据文件
datas = collect_data_files('PySide6')

# 收集Qt插件
pyside6_dir = os.path.dirname(get_module_file_attribute('PySide6.__init__'))
plugins_dir = os.path.join(pyside6_dir, 'plugins')
designer_dir = os.path.join(pyside6_dir, 'Designer')
qml_dir = os.path.join(pyside6_dir, 'qml')

if os.path.isdir(plugins_dir):
    datas.extend([(plugins_dir, 'PySide6/plugins')])
if os.path.isdir(designer_dir):
    datas.extend([(designer_dir, 'PySide6/Designer')])
if os.path.isdir(qml_dir):
    datas.extend([(qml_dir, 'PySide6/qml')])

# 收集Qt动态库
binaries = collect_dynamic_libs('PySide6')

print(f"PySide6钩子: 收集了 {{len(hiddenimports)}} 个子模块, {{len(datas)}} 个数据文件和 {{len(binaries)}} 个动态库文件")
""",

    "pandas": """# -*- coding: utf-8 -*-
\"\"\"
Pandas模块的PyInstaller钩子 (自动生成)
处理pandas的隐藏依赖
\"\"\"

from PyInstaller.utils.hooks import collect_submodules

# 自动生成的依赖列表
hiddenimports = {imports}

# 收集额外的子模块
additional_modules = collect_submodules('pandas')
for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

print(f"Pandas钩子: 收集了 {{len(hiddenimports)}} 个子模块")
"""
}


def ensure_hooks_dir():
    """确保钩子目录存在"""
    if not HOOKS_DIR.exists():
        os.makedirs(HOOKS_DIR)
        print(f"创建钩子目录: {HOOKS_DIR}")
    
    # 确保有__init__.py文件
    init_file = HOOKS_DIR / "__init__.py"
    if not init_file.exists():
        with open(init_file, "w", encoding="utf-8") as f:
            f.write("# PyInstaller钩子目录\n")
    
    return HOOKS_DIR


def get_transformers_deps():
    """获取transformers库的依赖"""
    try:
        from transformers.dependency_versions_check import deps_table
        return deps_table
    except (ImportError, AttributeError):
        print("警告: 无法获取transformers依赖表")
        return {}


def generate_dependency_hooks():
    """为transformers和sentence_transformers的依赖自动生成钩子文件"""
    # 获取transformers的依赖表
    deps_table = get_transformers_deps()
    
    # 基本的依赖列表
    basic_deps = ["tqdm", "regex", "packaging", "importlib.metadata", "tokenizers"]
    
    # 合并依赖
    all_deps = list(set(list(deps_table.keys()) + basic_deps))
    
    # 确保钩子目录存在
    hooks_dir = ensure_hooks_dir()
    
    # 为每个依赖生成一个简单的钩子文件
    for pkg_name in all_deps:
        # 跳过不应该生成钩子的特殊包
        if pkg_name in ["python"]:
            continue
            
        # 构造钩子文件名
        hook_file = hooks_dir / f"hook-{pkg_name.lower()}.py"
        
        # 如果钩子文件已存在，跳过
        if hook_file.exists():
            continue
        
        # 获取版本约束
        version_constraint = deps_table.get(pkg_name, "")
        
        # 生成钩子内容
        content = f"""# hook-{pkg_name}.py
# 自动生成的钩子文件，用于处理{pkg_name}依赖

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import sys
import os

# 版本约束: {version_constraint}

# 收集{pkg_name}的所有子模块
hiddenimports = collect_submodules('{pkg_name}')

# 收集数据文件
datas = collect_data_files('{pkg_name}')

# 尝试导入并记录版本信息
try:
    import {pkg_name}
    if hasattr({pkg_name}, "__version__"):
        print(f"{pkg_name}钩子: 找到版本 {{{pkg_name}.__version__}}")
except ImportError:
    print(f"警告: {pkg_name}钩子: 无法导入模块")
except Exception as e:
    print(f"警告: {pkg_name}钩子: 导入时出错 {{e}}")

print(f"{pkg_name}钩子: 收集了 {{len(hiddenimports)}} 个子模块和 {{len(datas)}} 个数据文件")
"""
        
        # 写入钩子文件
        try:
            with open(hook_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"成功生成钩子文件: {hook_file}")
        except Exception as e:
            print(f"警告: 无法写入钩子文件 {hook_file}: {e}")
    
    print(f"共为 {len(all_deps)} 个依赖生成钩子文件")


def generate_hook(hook_name):
    """生成指定名称的钩子文件"""
    # 确保钩子目录存在
    hooks_dir = ensure_hooks_dir()
    
    # 获取钩子模板
    if hook_name not in HOOK_TEMPLATES:
        print(f"错误: 未找到 {hook_name} 的钩子模板")
        return False
    
    template = HOOK_TEMPLATES[hook_name]
    
    # 获取依赖数据
    try:
        if hook_name == "vtkmodules":
            # vtkmodules钩子使用模板中的collect_submodules
            imports = []
        else:
            imports = get_hook_data(hook_name)
            # 确保正确的格式
            if hook_name == "PySide6":
                imports = [f"PySide6.{imp}" if not imp.startswith("PySide6.") else imp 
                          for imp in imports]
            elif hook_name == "matplotlib":
                imports = [f"matplotlib.{imp}" if not imp.startswith("matplotlib.") and not "." in imp else imp 
                          for imp in imports]
            elif hook_name == "pandas":
                imports = [f"pandas.{imp}" if not imp.startswith("pandas.") else imp 
                          for imp in imports]
    except Exception as e:
        print(f"错误: 获取 {hook_name} 的依赖数据失败: {str(e)}")
        return False
    
    # 格式化钩子内容
    try:
        hook_content = template.format(imports=imports)
    except Exception as e:
        print(f"错误: 格式化 {hook_name} 钩子模板失败: {str(e)}")
        return False
    
    # 写入钩子文件
    hook_file = hooks_dir / f"hook-{hook_name.lower()}.py"
    try:
        with open(hook_file, "w", encoding="utf-8") as f:
            f.write(hook_content)
        print(f"成功生成钩子文件: {hook_file}")
        return True
    except Exception as e:
        print(f"错误: 写入钩子文件 {hook_file} 失败: {str(e)}")
        return False


def generate_all_hooks():
    """生成所有已定义模板的钩子文件"""
    success_count = 0
    for hook_name in HOOK_TEMPLATES:
        if generate_hook(hook_name):
            success_count += 1
    
    # 生成依赖钩子
    try:
        generate_dependency_hooks()
    except Exception as e:
        print(f"生成依赖钩子文件时出错: {e}")
    
    print(f"共生成 {success_count}/{len(HOOK_TEMPLATES)} 个钩子文件")
    return success_count == len(HOOK_TEMPLATES)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="PyInstaller钩子生成工具")
    parser.add_argument("--hook", help="指定要生成的钩子名称")
    parser.add_argument("--all", action="store_true", help="生成所有钩子文件")
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    if args.hook:
        if generate_hook(args.hook):
            return 0
        else:
            return 1
    elif args.all:
        if generate_all_hooks():
            return 0
        else:
            return 1
    else:
        print("错误: 必须指定--hook或--all参数")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 