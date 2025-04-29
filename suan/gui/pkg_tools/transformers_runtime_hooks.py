#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Transformers库的PyInstaller运行时钩子
在应用程序启动时运行，确保正确加载transformers相关库
"""

import os
import sys
import logging

# 设置日志记录
logger = logging.getLogger("TransformersRuntimeHook")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

logger.info("正在加载transformers运行时钩子...")

# 获取应用程序的根目录
base_dir = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(os.path.dirname(sys.argv[0]))
logger.info(f"应用根目录: {base_dir}")

# 确保transformers模型目录存在
transformers_dir = os.path.join(base_dir, 'transformers')
models_dir = os.path.join(transformers_dir, 'models')

if not os.path.exists(transformers_dir):
    logger.warning(f"找不到transformers目录: {transformers_dir}")
else:
    logger.info(f"找到transformers目录: {transformers_dir}")
    
    # 检查models目录
    if not os.path.exists(models_dir):
        logger.warning(f"找不到transformers模型目录: {models_dir}")
    else:
        # 列出可用的模型目录
        available_models = [d for d in os.listdir(models_dir) if os.path.isdir(os.path.join(models_dir, d))]
        logger.info(f"找到 {len(available_models)} 个transformers模型: {', '.join(available_models)}")
        
        # 特别检查albert模型
        albert_dir = os.path.join(models_dir, 'albert')
        if not os.path.exists(albert_dir):
            logger.warning(f"找不到albert模型目录: {albert_dir}")
        else:
            logger.info(f"找到albert模型目录: {albert_dir}")

# 提前导入关键模块
try:
    import importlib
    
    # 预加载核心模块
    modules_to_preload = [
        'transformers',
        'transformers.utils',
        'transformers.utils.versions',
        'transformers.dependency_versions_check',
        'transformers.models.auto',
        'transformers.models.auto.modeling_auto',
        'sentence_transformers',
    ]
    
    for module_name in modules_to_preload:
        try:
            importlib.import_module(module_name)
            logger.info(f"预加载模块: {module_name}")
        except ImportError as e:
            logger.warning(f"无法预加载模块 {module_name}: {str(e)}")
except Exception as e:
    logger.warning(f"预加载模块时出错: {str(e)}")

logger.info("transformers运行时钩子加载完成") 