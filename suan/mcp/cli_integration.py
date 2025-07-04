#!/usr/bin/env python3
"""
CLI集成模块 - 自动发现并集成CLI命令

此模块负责发现现有的CLI命令并将其集成到MCP服务器中
"""

import importlib
import inspect
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

class CLIIntegration:
    """CLI命令集成类"""
    
    def __init__(self):
        self.commands = {}  # 存储发现的命令
        self.cli_modules = []  # 导入的CLI模块列表
    
    def discover_cli_modules(self) -> List[str]:
        """发现项目中的CLI模块"""
        cli_modules = []
        
        try:
            # 添加项目根目录到路径
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            
            # 尝试导入各种可能的CLI模块
            potential_modules = [
                'suan.cli.main',
                'toolkits.sjob.cli',
                'toolkits.smesh.cli',
                'toolkits.sviz.cli'
            ]
            
            for module_name in potential_modules:
                try:
                    module = importlib.import_module(module_name)
                    cli_modules.append(module_name)
                    self.cli_modules.append(module)
                    logger.info(f"发现CLI模块: {module_name}")
                except ImportError:
                    logger.debug(f"未找到CLI模块: {module_name}")
            
            return cli_modules
        
        except Exception as e:
            logger.error(f"发现CLI模块时出错: {e}")
            return []
    
    def extract_commands(self) -> Dict[str, Dict[str, Any]]:
        """从CLI模块中提取命令"""
        extracted_commands = {}
        
        for module in self.cli_modules:
            module_name = module.__name__.split('.')[-1]
            
            # 查找Click命令组
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                
                # 检查是否为Click命令组
                if hasattr(attr, 'commands') and callable(getattr(attr, 'commands', None)):
                    if module_name not in extracted_commands:
                        extracted_commands[module_name] = {}
                    
                    # 添加命令组中的所有命令
                    for cmd_name, cmd in attr.commands.items():
                        extracted_commands[module_name][cmd_name] = {
                            'command': cmd,
                            'help': cmd.help or f"执行 {cmd_name} 命令",
                            'params': self._extract_params(cmd)
                        }
                    
                    logger.info(f"从 {module_name} 提取了 {len(attr.commands)} 个命令")
        
        # 记录总命令数
        total_commands = sum(len(cmds) for cmds in extracted_commands.values())
        logger.info(f"总共发现 {total_commands} 个命令")
        
        self.commands = extracted_commands
        return extracted_commands
    
    def _extract_params(self, cmd) -> List[Dict[str, Any]]:
        """提取命令参数信息"""
        params = []
        
        if hasattr(cmd, 'params'):
            for param in cmd.params:
                param_info = {
                    'name': param.name,
                    'help': param.help or '',
                    'required': param.required,
                    'default': param.default if param.default is not inspect.Parameter.empty else None,
                    'type': self._get_param_type(param)
                }
                params.append(param_info)
        
        return params
    
    def _get_param_type(self, param) -> str:
        """获取参数类型"""
        if hasattr(param, 'type') and param.type is not None:
            if hasattr(param.type, 'name'):
                return param.type.name
            return str(param.type)
        return 'string'  # 默认类型

    def generate_tool_definitions(self) -> List[Dict[str, Any]]:
        """生成MCP工具定义"""
        tools = []
        
        for group_name, commands in self.commands.items():
            for cmd_name, cmd_info in commands.items():
                tool = {
                    'name': f"{group_name}_{cmd_name}",
                    'description': cmd_info['help'],
                    'parameters': self._generate_parameters_schema(cmd_info['params'])
                }
                tools.append(tool)
        
        return tools
    
    def _generate_parameters_schema(self, params: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成参数JSON Schema"""
        properties = {}
        required = []
        
        for param in params:
            param_schema = {
                'type': self._map_to_json_schema_type(param['type']),
                'description': param['help']
            }
            
            # 添加默认值
            if param['default'] is not None:
                param_schema['default'] = param['default']
            
            properties[param['name']] = param_schema
            
            if param['required']:
                required.append(param['name'])
        
        return {
            'type': 'object',
            'properties': properties,
            'required': required
        }
    
    def _map_to_json_schema_type(self, param_type: str) -> str:
        """将参数类型映射到JSON Schema类型"""
        type_mapping = {
            'string': 'string',
            'text': 'string',
            'int': 'integer',
            'integer': 'integer',
            'float': 'number',
            'bool': 'boolean',
            'boolean': 'boolean',
            'file': 'string',  # 文件路径作为字符串
            'path': 'string'   # 路径作为字符串
        }
        
        return type_mapping.get(param_type.lower(), 'string')

# 创建单例实例
cli_integration = CLIIntegration()

def discover_and_integrate_cli():
    """发现并集成CLI命令"""
    cli_integration.discover_cli_modules()
    return cli_integration.extract_commands()

def get_tool_definitions():
    """获取工具定义"""
    return cli_integration.generate_tool_definitions()
