"""
STK MCP Server - 将STK工具包转换为MCP服务器

这个模块提供了一个极简的MCP服务器实现，直接复用现有的CLI基础设施。
"""

__version__ = "1.0.0"
__author__ = "STK Team"
__description__ = "STK Scientific Toolkit MCP Server"

from .cli_integrated_server import main

__all__ = ["main"]
