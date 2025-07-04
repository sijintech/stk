#!/usr/bin/env python3
"""
STK MCP Server - CLI集成版本
动态发现并集成现有CLI命令到MCP协议中
"""

import asyncio
import logging
import sys
import os
from typing import List, Dict, Any

# MCP核心导入
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

# CLI执行相关
import click
import io
from contextlib import redirect_stdout, redirect_stderr

# 配置日志
# 解决中文编码问题
import locale

if sys.platform == "win32":
    locale.setlocale(locale.LC_ALL, "Chinese_China.UTF8")

# 使用UTF-8格式输出日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [STK-MCP] %(levelname)s: %(message)s",
    stream=sys.stderr,
    encoding="utf-8",
)
logger = logging.getLogger(__name__)

# 创建MCP服务器实例
server = Server("stk-toolkit")

# 全局状态
_tools_cache: List[Tool] = []
_cli_initialized = False
_cli_commands = {}


def initialize_cli() -> bool:
    """初始化CLI系统"""
    global _cli_initialized, _cli_commands

    if _cli_initialized:
        return True

    try:
        # 添加项目路径
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # 导入CLI系统
        from suan.cli.main import cli, load_plugins

        # 加载插件
        load_plugins()
        _cli_initialized = True

        # 缓存所有可用命令
        for group_name, group in cli.commands.items():
            if isinstance(group, click.Group):
                _cli_commands[group_name] = {}
                for cmd_name, cmd in group.commands.items():
                    _cli_commands[group_name][cmd_name] = cmd

        logger.info(f"CLI system initialized successfully")
        logger.info(f"Available command groups: {list(_cli_commands.keys())}")

        # 统计总命令数
        total_commands = sum(len(commands) for commands in _cli_commands.values())
        logger.info(f"Total commands discovered: {total_commands}")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize CLI system: {e}")
        return False


def cli_command_to_tool(group_name: str, cmd_name: str, cmd: click.Command) -> Tool:
    """将CLI命令转换为MCP工具"""
    tool_name = f"{group_name}_{cmd_name}"

    # 构建描述
    description = cmd.help or f"Execute {group_name} {cmd_name} command"

    # 构建参数schema
    properties = {}
    required = []

    for param in cmd.params:
        if isinstance(param, click.Option):
            param_name = param.name
            param_help = param.help or f"{param_name} parameter"

            # 基本schema
            param_schema = {"description": param_help}

            # 类型推断
            if param.is_flag:
                param_schema["type"] = "boolean"
                param_schema["default"] = False
            elif hasattr(param.type, "choices") and getattr(
                param.type, "choices", None
            ):
                param_schema["type"] = "string"
                param_schema["enum"] = param.type.choices
            elif param.type is click.INT or str(param.type) == "INT":
                param_schema["type"] = "integer"
            elif param.type is click.FLOAT or str(param.type) == "FLOAT":
                param_schema["type"] = "number"
            elif hasattr(param.type, "path_type") or "Path" in str(type(param.type)):
                param_schema["type"] = "string"
                param_schema["format"] = "path"
            else:
                param_schema["type"] = "string"

            # 默认值
            if param.default is not None and not param.is_flag:
                param_schema["default"] = param.default

            properties[param_name] = param_schema

            if param.required:
                required.append(param_name)

    # 添加工具组信息到描述
    full_description = f"[{group_name}] {description}"
    if properties:
        param_list = list(properties.keys())
        full_description += f"\n\n参数: {', '.join(param_list)}"

    return Tool(
        name=tool_name,
        description=full_description,
        inputSchema={"type": "object", "properties": properties, "required": required},
    )


def discover_cli_tools() -> List[Tool]:
    """发现所有CLI工具"""
    if not initialize_cli():
        return []

    tools = []

    for group_name, commands in _cli_commands.items():
        for cmd_name, cmd in commands.items():
            try:
                tool = cli_command_to_tool(group_name, cmd_name, cmd)
                tools.append(tool)
                logger.debug(f"Converted tool: {tool.name}")
            except Exception as e:
                logger.warning(f"Failed to convert {group_name}.{cmd_name}: {e}")

    logger.info(f"Discovered {len(tools)} CLI tools")
    return tools


async def execute_cli_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """执行CLI工具"""
    if not initialize_cli():
        raise RuntimeError("CLI system not available")

    try:
        # 解析工具名称
        parts = tool_name.split("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid tool name format: {tool_name}")

        group_name, cmd_name = parts

        # 获取命令对象
        if group_name not in _cli_commands:
            raise ValueError(f"Unknown command group: {group_name}")

        if cmd_name not in _cli_commands[group_name]:
            raise ValueError(f"Unknown command: {group_name}.{cmd_name}")

        command = _cli_commands[group_name][cmd_name]

        # 构建参数列表
        args = []
        for param_name, param_value in arguments.items():
            if param_value is None:
                continue

            if isinstance(param_value, bool):
                if param_value:
                    args.append(f"--{param_name}")
            elif isinstance(param_value, (list, tuple)):
                for value in param_value:
                    args.extend([f"--{param_name}", str(value)])
            else:
                args.extend([f"--{param_name}", str(param_value)])

        # 执行命令并捕获输出
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        logger.info(f"Executing CLI command: {group_name} {cmd_name} with args: {args}")

        try:
            with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                ctx = command.make_context(command.name, args)
                command.invoke(ctx)
        except SystemExit as e:
            if e.code != 0:
                error = error_buffer.getvalue()
                if error:
                    raise RuntimeError(
                        f"Command failed with exit code {e.code}: {error}"
                    )

        # 获取结果
        output = output_buffer.getvalue()
        error = error_buffer.getvalue()

        if error and not output:
            raise RuntimeError(f"Command error: {error}")

        # 格式化结果
        result = f"=== {group_name}.{cmd_name} 执行结果 ===\n\n"

        if output:
            result += f"输出:\n{output}\n"
        else:
            result += "命令执行成功（无输出）\n"

        if error:
            result += f"\n警告/错误信息:\n{error}"

        result += f"\n执行的参数: {arguments}"

        return result

    except Exception as e:
        logger.error(f"CLI tool execution error: {e}")
        raise


# 静态示例工具（保留作为后备）
STATIC_TOOLS = [
    Tool(
        name="stk_info",
        description="获取STK工具包信息",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="stk_status",
        description="获取CLI系统状态",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]


async def execute_static_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """执行静态工具"""
    if tool_name == "stk_info":
        if not initialize_cli():
            cli_status = "❌ 未初始化"
            total_tools = 0
        else:
            cli_status = "✅ 已初始化"
            total_tools = sum(len(commands) for commands in _cli_commands.values())

        return f"""
STK (Scientific Toolkit) MCP服务器信息:

📋 基本信息:
- 版本: 1.0.0 (CLI集成版)
- 描述: 科学计算工具包MCP服务器
- 服务器状态: 运行中

🔧 CLI系统状态:
- CLI系统: {cli_status}
- 可用工具组: {len(_cli_commands) if _cli_commands else 0}
- 总工具数: {total_tools}

🛠️ 可用工具组:
{chr(10).join(f"  - {group}: {len(commands)}个命令" for group, commands in _cli_commands.items()) if _cli_commands else "  - 无"}

💡 使用提示:
使用工具名格式: <工具组>_<命令名>
例如: sjob_schedule, sjob_create, sjob_execute
        """.strip()

    elif tool_name == "stk_status":
        if not initialize_cli():
            return "❌ CLI系统未初始化，请检查配置"

        status_info = "✅ STK MCP服务器运行状态正常\n\n"
        status_info += "📊 详细统计:\n"

        for group_name, commands in _cli_commands.items():
            status_info += f"  🔹 {group_name}: {len(commands)}个命令\n"
            for cmd_name in commands.keys():
                status_info += f"    - {group_name}_{cmd_name}\n"

        return status_info

    else:
        raise ValueError(f"未知静态工具: {tool_name}")


# MCP协议处理器
@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """处理工具列表请求"""
    global _tools_cache

    try:
        if not _tools_cache:
            # 获取CLI工具
            cli_tools = discover_cli_tools()
            # 合并静态工具和CLI工具
            _tools_cache = STATIC_TOOLS + cli_tools

        logger.info(
            f"返回 {len(_tools_cache)} 个工具 (静态: {len(STATIC_TOOLS)}, CLI: {len(_tools_cache) - len(STATIC_TOOLS)})"
        )
        return _tools_cache

    except Exception as e:
        logger.error(f"列出工具时出错: {e}")
        return STATIC_TOOLS  # 至少返回静态工具


@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """处理工具调用请求"""
    logger.info(f"工具调用: {name}, 参数: {arguments}")

    try:
        # 判断是静态工具还是CLI工具
        if name in ["stk_info", "stk_status"]:
            result = await execute_static_tool(name, arguments)
        else:
            result = await execute_cli_tool(name, arguments)

        logger.info(f"工具 {name} 执行成功")

        return CallToolResult(content=[TextContent(type="text", text=result)])

    except Exception as e:
        error_msg = f"工具执行失败: {str(e)}"
        logger.error(error_msg)

        return CallToolResult(
            content=[TextContent(type="text", text=f"错误: {error_msg}")], isError=True
        )


async def main():
    """主入口函数"""
    try:
        logger.info("启动 STK MCP 服务器（CLI集成版）...")

        # 预初始化CLI系统
        if initialize_cli():
            logger.info("✅ CLI系统初始化成功")

            # 预加载工具列表以便早期发现问题
            try:
                tools = discover_cli_tools()
                logger.info(f"✅ 预加载了 {len(tools)} 个CLI工具")

                # 显示可用工具组
                if _cli_commands:
                    groups_info = []
                    for group, commands in _cli_commands.items():
                        groups_info.append(f"{group}({len(commands)})")
                    logger.info(f"可用工具组: {', '.join(groups_info)}")
            except Exception as e:
                logger.error(f"工具发现错误: {e}")
                logger.warning("⚠️ 部分工具可能不可用")
        else:
            logger.warning("⚠️ CLI系统初始化失败，仅提供静态工具")

        # 启动stdio服务器
        try:
            async with stdio_server() as (read_stream, write_stream):
                # 运行服务器，传递空的初始化选项
                initialization_options = {}
                await server.run(read_stream, write_stream, initialization_options)
        except asyncio.CancelledError:
            logger.info("服务器任务被取消")
        except Exception as e:
            logger.error(f"MCP服务器运行错误: {e}")
            if hasattr(e, "__context__") and e.__context__:
                logger.error(f"上下文错误: {e.__context__}")

    except KeyboardInterrupt:
        logger.info("服务器被用户停止")
    except Exception as e:
        logger.error(f"服务器错误: {e}")
    finally:
        logger.info("STK MCP 服务器已关闭")


if __name__ == "__main__":
    asyncio.run(main())
