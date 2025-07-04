import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ServerConfig:
    """服务器基础配置"""

    name: str = "stk-toolkit"
    version: str = "1.0.0"
    description: str = "STK Scientific Toolkit MCP Server"
    log_level: str = "INFO"
    debug: bool = False

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """从环境变量创建配置"""
        debug = os.getenv("STK_MCP_DEBUG", "false").lower() in ("true", "1", "yes")
        return cls(
            name=os.getenv("STK_MCP_NAME", cls.name),
            version=os.getenv("STK_MCP_VERSION", cls.version),
            description=os.getenv("STK_MCP_DESCRIPTION", cls.description),
            log_level=os.getenv("STK_MCP_LOG_LEVEL", cls.log_level),
            debug=debug,
        )

    @classmethod
    def from_file(cls, config_path: str) -> "ServerConfig":
        """从文件加载配置"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return cls(
                name=data.get("name", cls.name),
                version=data.get("version", cls.version),
                description=data.get("description", cls.description),
                log_level=data.get("log_level", cls.log_level),
                debug=data.get("debug", cls.debug),
            )
        except Exception as e:
            logging.warning(f"Failed to load config from {config_path}: {e}")
            return cls()  # 返回默认配置


# 简化的配置加载函数
def load_config(config_path: Optional[str] = None) -> ServerConfig:
    """加载配置

    优先级：文件配置 > 环境变量 > 默认值
    """
    if config_path and os.path.exists(config_path):
        config = ServerConfig.from_file(config_path)
    else:
        config = ServerConfig.from_env()

    return config


# 扩展点：自定义工具执行器注册
CUSTOM_EXECUTORS = []


def register_custom_executor(executor_class):
    """注册自定义工具执行器"""
    CUSTOM_EXECUTORS.append(executor_class)


def get_custom_executors():
    """获取已注册的自定义执行器"""
    return CUSTOM_EXECUTORS
