#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Transformers库的PyInstaller运行时钩子
在应用程序启动时运行，确保正确加载transformers相关库
"""

import os
import sys
import logging
import importlib.util

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

# 检查环境变量
if "PYTHONPATH" in os.environ:
    logger.info(f"PYTHONPATH: {os.environ['PYTHONPATH']}")
else:
    logger.info("未设置PYTHONPATH环境变量")
    
# 检查系统路径
logger.info(f"sys.path前5项: {sys.path[:5]}")

# 如果base_dir不在sys.path中，添加它
if base_dir not in sys.path:
    logger.info(f"添加{base_dir}到sys.path")
    sys.path.insert(0, base_dir)

# 确保transformers模型目录存在
transformers_dir = os.path.join(base_dir, 'transformers')
transformers_init = os.path.join(transformers_dir, '__init__.py')
models_dir = os.path.join(transformers_dir, 'models')

# 检查关键文件
if not os.path.exists(transformers_dir):
    logger.warning(f"找不到transformers目录: {transformers_dir}")
else:
    logger.info(f"找到transformers目录: {transformers_dir}")
    
    # 检查__init__.py是否存在
    if os.path.exists(transformers_init):
        logger.info(f"找到transformers/__init__.py文件: {transformers_init}")
    else:
        logger.warning(f"找不到transformers/__init__.py文件: {transformers_init}")
    
    # 检查trainer.py是否存在
    trainer_file = os.path.join(transformers_dir, 'trainer.py')
    if os.path.exists(trainer_file):
        logger.info(f"找到transformers/trainer.py文件: {trainer_file}")
    else:
        logger.warning(f"找不到transformers/trainer.py文件: {trainer_file}")
    
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
            
            # 检查albert模型的关键文件
            albert_init = os.path.join(albert_dir, '__init__.py')
            if os.path.exists(albert_init):
                logger.info(f"找到albert/__init__.py文件: {albert_init}")
            else:
                logger.warning(f"找不到albert/__init__.py文件: {albert_init}")

# 检查sentence_transformers目录
sentence_transformers_dir = os.path.join(base_dir, 'sentence_transformers')
if not os.path.exists(sentence_transformers_dir):
    logger.warning(f"找不到sentence_transformers目录: {sentence_transformers_dir}")
else:
    logger.info(f"找到sentence_transformers目录: {sentence_transformers_dir}")
    
    # 检查__init__.py是否存在
    st_init = os.path.join(sentence_transformers_dir, '__init__.py')
    if os.path.exists(st_init):
        logger.info(f"找到sentence_transformers/__init__.py文件: {st_init}")
    else:
        logger.warning(f"找不到sentence_transformers/__init__.py文件: {st_init}")

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
        'transformers.trainer',  # 尝试预加载trainer模块
        'sentence_transformers',
    ]
    
    for module_name in modules_to_preload:
        try:
            # 首先检查模块是否存在
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                logger.warning(f"模块{module_name}不存在，无法预加载")
                continue
                
            # 导入模块
            module = importlib.import_module(module_name)
            logger.info(f"预加载模块: {module_name}")
            
            # 如果是transformers模块，打印版本信息
            if module_name == 'transformers':
                if hasattr(module, '__version__'):
                    logger.info(f"transformers版本: {module.__version__}")
                
                # 尝试检查模块的关键属性
                if hasattr(module, '__file__'):
                    logger.info(f"transformers文件路径: {module.__file__}")
            
            # 如果是sentence_transformers模块，打印版本信息
            if module_name == 'sentence_transformers':
                if hasattr(module, '__version__'):
                    logger.info(f"sentence_transformers版本: {module.__version__}")
                
                # 尝试检查模块的关键属性
                if hasattr(module, '__file__'):
                    logger.info(f"sentence_transformers文件路径: {module.__file__}")
        except ImportError as e:
            logger.warning(f"无法预加载模块 {module_name}: {str(e)}")
except Exception as e:
    logger.warning(f"预加载模块时出错: {str(e)}")

logger.info("transformers运行时钩子加载完成") 