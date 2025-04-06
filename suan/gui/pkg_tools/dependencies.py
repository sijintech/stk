#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PyInstaller依赖管理模块 - 从pyproject.toml提取依赖信息，生成PyInstaller所需的hiddenimports列表
实现"单一真实来源"策略，所有依赖配置只在pyproject.toml一处定义
"""

import os
import sys
import argparse
import toml
from pathlib import Path
import json


def find_pyproject_toml():
    """查找pyproject.toml文件"""
    # 从当前目录开始向上查找
    current_dir = Path(os.getcwd())
    
    while current_dir != current_dir.parent:
        pyproject_path = current_dir / "pyproject.toml"
        if pyproject_path.exists():
            return str(pyproject_path)
        current_dir = current_dir.parent
    
    # 如果没有找到，尝试相对于脚本路径查找
    script_dir = Path(__file__).parent.parent.parent
    project_root = script_dir.parent
    pyproject_path = project_root / "pyproject.toml"
    
    if pyproject_path.exists():
        return str(pyproject_path)
    
    return None


def load_pyproject_config():
    """加载pyproject.toml文件配置"""
    pyproject_path = find_pyproject_toml()
    if not pyproject_path:
        print("错误: 无法找到pyproject.toml文件")
        return None
    
    try:
        return toml.load(pyproject_path)
    except Exception as e:
        print(f"错误: 加载pyproject.toml失败 - {str(e)}")
        return None


def get_poetry_dependencies(config):
    """从Poetry配置中提取依赖"""
    if not config or "tool" not in config or "poetry" not in config["tool"]:
        return []
    
    dependencies = []
    if "dependencies" in config["tool"]["poetry"]:
        dependencies = list(config["tool"]["poetry"]["dependencies"].keys())
        # 移除Python依赖项
        if "python" in dependencies:
            dependencies.remove("python")
    
    return dependencies


def get_pyinstaller_config(config):
    """获取PyInstaller配置"""
    if not config or "tool" not in config or "pyinstaller" not in config["tool"]:
        return {}
    
    return config["tool"]["pyinstaller"]


def extract_hidden_imports(config):
    """提取所有hidden_imports"""
    pyinstaller_config = get_pyinstaller_config(config)
    
    # 获取基本hidden_imports
    hidden_imports = pyinstaller_config.get("hidden_imports", [])
    
    # 从分类配置中获取额外的hidden_imports
    for key, value in pyinstaller_config.items():
        if isinstance(value, dict) and "modules" in value:
            # 确保模块名前缀正确
            prefix = f"{key}." if not key.endswith("modules") else ""
            for module in value["modules"]:
                full_module = f"{prefix}{module}" if not module.startswith(prefix) else module
                if full_module not in hidden_imports:
                    hidden_imports.append(full_module)
    
    return hidden_imports


def extract_dependencies():
    """主函数：提取所有依赖"""
    config = load_pyproject_config()
    if not config:
        return []
    
    # 获取Poetry依赖
    poetry_deps = get_poetry_dependencies(config)
    
    # 获取PyInstaller隐藏导入
    hidden_imports = extract_hidden_imports(config)
    
    # 合并所有依赖（去重）
    all_imports = list(set(poetry_deps + hidden_imports))
    
    return all_imports


def get_hook_data(hook_name):
    """获取特定钩子所需的数据"""
    config = load_pyproject_config()
    if not config:
        return []
    
    pyinstaller_config = get_pyinstaller_config(config)
    hook_config = pyinstaller_config.get(hook_name, {})
    
    # 为不同类型的钩子返回适当的数据
    if hook_name == "matplotlib":
        backends = hook_config.get("modules", [])
        return [f"matplotlib.{b}" if not b.startswith("matplotlib.") else b for b in backends]
    elif hook_name == "vtk" or hook_name == "PySide6" or hook_name == "pandas":
        modules = hook_config.get("modules", [])
        return modules
    else:
        return []


def format_imports_for_spec():
    """以spec文件格式返回导入列表"""
    imports = extract_dependencies()
    formatted = "[\n"
    for imp in imports:
        formatted += f"    '{imp}',\n"
    formatted += "]"
    return formatted


def output_imports(format_type="list", hook_name=None):
    """根据指定格式输出导入列表"""
    if hook_name:
        imports = get_hook_data(hook_name)
    else:
        imports = extract_dependencies()
    
    if format_type == "json":
        return json.dumps(imports, indent=2)
    elif format_type == "spec":
        return format_imports_for_spec()
    elif format_type == "python":
        return f"hiddenimports = {imports}"
    else:  # 默认为list
        return "\n".join(imports)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="PyInstaller依赖提取工具")
    parser.add_argument("--format", choices=["list", "json", "spec", "python"], 
                      default="list", help="输出格式")
    parser.add_argument("--hook", help="指定要获取数据的钩子名称")
    parser.add_argument("--output", help="输出文件路径，默认为标准输出")
    
    return parser.parse_args()


def main():
    """命令行入口点"""
    args = parse_args()
    
    output = output_imports(args.format, args.hook)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 