#!/usr/bin/env python3
"""
STK MCP服务器安装脚本
安装运行MCP服务器所需的依赖
"""

import subprocess
import sys
import os

def check_pip():
    """检查pip是否可用"""
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', '--version'])
        return True
    except subprocess.CalledProcessError:
        return False

def install_dependencies():
    """安装依赖"""
    if not check_pip():
        print("错误: pip未安装或无法使用")
        return False
    
    print("安装MCP服务器依赖...")
    
    # 安装核心依赖
    requirements = [
        "mcp[cli]",
        "httpx",
        "matplotlib",
        "numpy"
    ]
    
    try:
        subprocess.check_call([
            sys.executable,
            '-m',
            'pip',
            'install',
            *requirements
        ])
        
        print("依赖安装成功！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"安装依赖时出错: {e}")
        return False

def main():
    """主函数"""
    print("STK MCP服务器安装脚本")
    print("======================")
    
    if install_dependencies():
        print("\n安装完成！您现在可以运行MCP服务器了:")
        print("python -m suan.mcp")
        return 0
    else:
        print("\n安装失败。请检查错误信息并重试。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
