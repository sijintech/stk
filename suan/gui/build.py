#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STK应用打包入口脚本 - 简化打包命令调用
"""

import sys
import os
from pathlib import Path

# 将当前目录添加到路径中
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 如果未指定--debug参数，默认添加它
if len(sys.argv) > 1 and "--debug" not in sys.argv:
    sys.argv.append("--debug")

try:
    # 尝试从pkg_tools模块导入builder
    from pkg_tools.builder import main as build_main
    print("正在启动STK应用打包工具...")
    sys.exit(build_main())
except ImportError as e:
    print(f"错误: 无法导入打包模块: {e}")
    print("请确保pkg_tools目录存在并且包含必要的模块")
    sys.exit(1)
except Exception as e:
    print(f"打包过程中出现错误: {e}")
    sys.exit(1) 