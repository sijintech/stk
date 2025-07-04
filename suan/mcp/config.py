"""
STK MCP Server 配置
"""

# 服务器基础配置
SERVER_NAME = "stk-toolkit"
SERVER_VERSION = "1.0.0"
SERVER_DESCRIPTION = "科学计算工具集的MCP服务器实现"

# 日志配置
LOG_LEVEL = "INFO"  # 可选: DEBUG, INFO, WARNING, ERROR, CRITICAL

# 安全配置
ALLOWED_COMMANDS = ["sviz", "smesh", "sjob"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 最大允许读取的文件大小（字节）

# 超时配置
COMMAND_TIMEOUT = 60  # 命令执行最大超时时间（秒）

# 功能开关
ENABLE_FILE_ACCESS = True
ENABLE_COMMAND_EXECUTION = True
ENABLE_VISUALIZATION = True
