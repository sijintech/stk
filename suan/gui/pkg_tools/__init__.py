#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STK应用打包工具包
提供用于构建应用程序的模块和功能
"""

from . import builder
from . import dependencies
from . import hooks_generator

__all__ = ['builder', 'dependencies', 'hooks_generator']

from pathlib import Path

# 包路径
PACKAGE_DIR = Path(__file__).parent
GUI_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = GUI_DIR.parent.parent

# 版本信息
__version__ = "1.0.0" 