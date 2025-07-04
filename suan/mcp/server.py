#!/usr/bin/env python3
"""
STK MCP Server - 基于Model Context Protocol标准

这个模块实现了MCP服务器，允许AI模型安全地访问STK工具包中的功能。
"""

import asyncio
import logging
import sys
import os
import json
import subprocess
from typing import Any, Dict, List, Optional

# MCP 核心导入
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("请安装MCP Python SDK: pip install \"mcp[cli]\" httpx")
    sys.exit(1)

# 导入配置和CLI集成
from suan.mcp.config import *
from suan.mcp.cli_integration import discover_and_integrate_cli, get_tool_definitions

# 配置日志
import locale

if sys.platform == "win32":
    locale.setlocale(locale.LC_ALL, "Chinese_China.UTF8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [STK-MCP] %(levelname)s: %(message)s",
    stream=sys.stderr,
    encoding="utf-8",
)
logger = logging.getLogger(__name__)

# 创建MCP服务器实例
mcp = FastMCP(SERVER_NAME, description=SERVER_DESCRIPTION)

# ======================= STK工具包集成部分 =======================

# 添加对smesh、sviz和sjob的直接支持
def integrate_stk_core_tools():
    """集成STK核心工具到MCP"""
    logger.info("正在集成STK核心工具...")
    
    # 检查各工具是否可用
    available_tools = []
    
    # 检查smesh
    try:
        import importlib
        if importlib.util.find_spec("smesh"):
            available_tools.append("smesh")
            logger.info("发现smesh工具")
    except ImportError:
        logger.warning("未找到smesh模块")
    
    # 检查sviz
    try:
        if importlib.util.find_spec("sviz"):
            available_tools.append("sviz")
            logger.info("发现sviz工具")
    except ImportError:
        logger.warning("未找到sviz模块")
    
    # 检查sjob
    try:
        if importlib.util.find_spec("sjob") or importlib.util.find_spec("toolkits.sjob.cli"):
            available_tools.append("sjob")
            logger.info("发现sjob工具")
    except ImportError:
        logger.warning("未找到sjob模块")
    
    return available_tools

@mcp.tool()
async def stk_info() -> str:
    """获取STK工具包的基本信息和可用功能列表"""
    info = {
        "name": "STK Scientific Toolkit",
        "version": "1.0.0",
        "description": "科学计算工具集，提供数据处理、可视化和模拟功能",
        "components": [
            {
                "name": "smesh",
                "description": "网格处理工具"
            },
            {
                "name": "sviz",
                "description": "可视化工具"
            },
            {
                "name": "sjob",
                "description": "作业管理工具"
            }
        ],
        "help": "可以通过运行 如`run_sjob` 命令来执行具体的STK工具命令，或者如提供参数`--help`获取帮助信息。",
    }
    
    result = f"""# STK工具包信息
- 名称: {info['name']}
- 版本: {info['version']}
- 描述: {info['description']}
- 用法：{info['help']}

## 可用组件:
"""
    
    for component in info["components"]:
        result += f"- {component['name']}: {component['description']}\n"
    
    return result

@mcp.tool()
async def run_stk_command(command: str) -> str:
    """
    运行STK命令行工具
    
    Args:
        command: 要执行的STK命令，例如"sviz plot-scalar --help"
    """
    try:
        # 安全检查 - 限制可以执行的命令
        allowed_prefixes = ["sviz", "smesh", "sjob"]
        cmd_parts = command.split()
        
        if not any(cmd_parts[0] == prefix for prefix in allowed_prefixes):
            return f"错误: 只允许执行 {', '.join(allowed_prefixes)} 开头的命令"
        
        logger.info(f"执行STK命令: {command}")
        
        # 在Windows上处理编码问题
        if sys.platform == "win32":
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=False,  # 不自动解码
                timeout=COMMAND_TIMEOUT
            )
            
            # 尝试不同的编码方式解码输出
            encodings = ['utf-8', 'gbk', 'gb2312', 'cp936']
            stdout = None
            stderr = None
            
            for encoding in encodings:
                try:
                    if not stdout and process.stdout:
                        stdout = process.stdout.decode(encoding, errors='replace')
                    if not stderr and process.stderr:
                        stderr = process.stderr.decode(encoding, errors='replace')
                    if stdout and stderr:
                        break
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，使用'replace'策略的utf-8
            if not stdout and process.stdout:
                stdout = process.stdout.decode('utf-8', errors='replace')
            if not stderr and process.stderr:
                stderr = process.stderr.decode('utf-8', errors='replace')
        else:
            # 非Windows系统使用原来的方法
            process = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                encoding="utf-8",
                timeout=COMMAND_TIMEOUT
            )
            stdout = process.stdout
            stderr = process.stderr
        
        if process.returncode == 0:
            return stdout
        else:
            error_msg = f"命令执行失败 (错误码 {process.returncode}):\n{stderr}"
            logger.error(error_msg)
            return error_msg
    
    except subprocess.TimeoutExpired:
        return f"命令执行超时 (超过 {COMMAND_TIMEOUT} 秒)"
    except Exception as e:
        error_msg = f"执行命令时发生错误: {str(e)}"
        logger.error(error_msg)
        return error_msg

@mcp.tool()
async def get_file_content(file_path: str) -> str:
    """
    获取文件内容
    
    Args:
        file_path: 要读取的文件路径，仅限于工作目录内的文件
    """
    try:
        # 安全检查 - 确保文件在工作目录内并且存在
        abs_path = os.path.abspath(file_path)
        work_dir = os.path.abspath(os.getcwd())
        
        if not abs_path.startswith(work_dir):
            return "错误: 只能访问工作目录内的文件"
        
        if not os.path.exists(abs_path):
            return f"错误: 文件 '{file_path}' 不存在"
        
        if os.path.isdir(abs_path):
            return f"错误: '{file_path}' 是一个目录，不是文件"
        
        # 读取文件内容
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return content
    
    except Exception as e:
        return f"读取文件时发生错误: {str(e)}"

@mcp.tool()
async def list_directory(directory_path: str = ".") -> str:
    """
    列出目录中的文件和子目录
    
    Args:
        directory_path: 要列出内容的目录路径，默认为当前工作目录
    """
    try:
        # 安全检查 - 确保目录在工作目录内并且存在
        abs_path = os.path.abspath(directory_path)
        work_dir = os.path.abspath(os.getcwd())
        
        if not abs_path.startswith(work_dir):
            return "错误: 只能访问工作目录内的目录"
        
        if not os.path.exists(abs_path):
            return f"错误: 目录 '{directory_path}' 不存在"
        
        if not os.path.isdir(abs_path):
            return f"错误: '{directory_path}' 是一个文件，不是目录"
        
        # 列出目录内容
        items = os.listdir(abs_path)
        
        # 区分文件和目录
        dirs = [f"{item}/" for item in items if os.path.isdir(os.path.join(abs_path, item))]
        files = [item for item in items if os.path.isfile(os.path.join(abs_path, item))]
        
        result = f"目录 '{directory_path}' 的内容:\n\n"
        
        if dirs:
            result += "## 子目录:\n"
            for d in sorted(dirs):
                result += f"- {d}\n"
                
        if files:
            result += "\n## 文件:\n"
            for f in sorted(files):
                result += f"- {f}\n"
                
        if not dirs and not files:
            result += "(目录为空)"
            
        return result
    
    except Exception as e:
        return f"列出目录内容时发生错误: {str(e)}"

# ======================= 科学计算工具示例 =======================

@mcp.tool()
async def calculate_statistics(data: List[float]) -> Dict[str, float]:
    """
    计算基本统计量
    
    Args:
        data: 要计算统计量的数值列表
    """
    try:
        import numpy as np
        
        if not data:
            return {"error": "输入数据列表为空"}
        
        # 计算基本统计量
        stats = {
            "count": len(data),
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "mean": float(np.mean(data)),
            "median": float(np.median(data)),
            "std": float(np.std(data)),
            "variance": float(np.var(data))
        }
        
        return stats
    
    except Exception as e:
        return {"error": f"计算统计量时发生错误: {str(e)}"}

@mcp.tool()
async def generate_plot(
    data: List[float], 
    title: str = "数据可视化",
    xlabel: str = "X轴",
    ylabel: str = "Y轴"
) -> str:
    """
    生成简单的数据可视化图表
    
    Args:
        data: 要可视化的数据列表
        title: 图表标题
        xlabel: X轴标签
        ylabel: Y轴标签
    """
    try:
        import matplotlib.pyplot as plt
        import tempfile
        import base64
        
        if not data:
            return "错误: 输入数据列表为空"
        
        # 创建图表
        plt.figure(figsize=(10, 6))
        plt.plot(data, marker='o')
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True)
        
        # 将图表保存为临时文件
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            plt.savefig(tmp.name)
            tmp_path = tmp.name
        
        plt.close()
        
        # 读取并返回图像的base64编码
        with open(tmp_path, 'rb') as img_file:
            img_data = base64.b64encode(img_file.read()).decode('utf-8')
        
        # 删除临时文件
        os.remove(tmp_path)
        
        # 返回可以在Markdown中显示的图像
        return f"![数据可视化](data:image/png;base64,{img_data})"
    
    except Exception as e:
        return f"生成图表时发生错误: {str(e)}"

# ======================= STK核心工具直接集成 =======================

@mcp.tool()
async def run_smesh(command: str) -> str:
    """
    直接运行smesh工具命令
    
    Args:
        command: 要执行的smesh命令参数
    """
    try:
        # 在Windows上，使用python直接调用smesh模块可能更可靠
        if sys.platform == "win32":
            # 构建使用Python执行smesh模块的命令
            smesh_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'toolkits', 'smesh')
            full_command = f"python -m smesh {command}"
        else:
            full_command = f"smesh {command}"
            
        logger.info(f"执行smesh命令: {full_command}")
        
        # 在Windows上处理编码问题
        if sys.platform == "win32":
            process = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=False,  # 不自动解码
                timeout=COMMAND_TIMEOUT
            )
            
            # 尝试不同的编码方式解码输出
            encodings = ['utf-8', 'gbk', 'gb2312', 'cp936']
            stdout = None
            stderr = None
            
            for encoding in encodings:
                try:
                    if not stdout and process.stdout:
                        stdout = process.stdout.decode(encoding, errors='replace')
                    if not stderr and process.stderr:
                        stderr = process.stderr.decode(encoding, errors='replace')
                    if stdout and stderr:
                        break
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，使用'replace'策略的utf-8
            if not stdout and process.stdout:
                stdout = process.stdout.decode('utf-8', errors='replace')
            if not stderr and process.stderr:
                stderr = process.stderr.decode('utf-8', errors='replace')
        else:
            # 非Windows系统使用原来的方法
            process = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=COMMAND_TIMEOUT
            )
            stdout = process.stdout
            stderr = process.stderr
        
        if process.returncode == 0:
            return stdout
        else:
            error_msg = f"smesh命令执行失败 (错误码 {process.returncode}):\n{stderr}"
            logger.error(error_msg)
            return error_msg
    
    except subprocess.TimeoutExpired:
        return f"smesh命令执行超时 (超过 {COMMAND_TIMEOUT} 秒)"
    except Exception as e:
        error_msg = f"执行smesh命令时发生错误: {str(e)}"
        logger.error(error_msg)
        return error_msg

@mcp.tool()
async def run_sviz(command: str) -> str:
    """
    直接运行sviz可视化工具命令
    
    Args:
        command: 要执行的sviz命令参数
    """
    try:
        # 在Windows上，使用python直接调用sviz模块可能更可靠
        if sys.platform == "win32":
            # 构建使用Python执行sviz模块的命令
            sviz_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'toolkits', 'sviz')
            full_command = f"python -m sviz {command}"
        else:
            full_command = f"sviz {command}"
            
        logger.info(f"执行sviz命令: {full_command}")
        
        # 在Windows上处理编码问题
        if sys.platform == "win32":
            process = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=False,  # 不自动解码
                timeout=COMMAND_TIMEOUT
            )
            
            # 尝试不同的编码方式解码输出
            encodings = ['utf-8', 'gbk', 'gb2312', 'cp936']
            stdout = None
            stderr = None
            
            for encoding in encodings:
                try:
                    if not stdout and process.stdout:
                        stdout = process.stdout.decode(encoding, errors='replace')
                    if not stderr and process.stderr:
                        stderr = process.stderr.decode(encoding, errors='replace')
                    if stdout and stderr:
                        break
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，使用'replace'策略的utf-8
            if not stdout and process.stdout:
                stdout = process.stdout.decode('utf-8', errors='replace')
            if not stderr and process.stderr:
                stderr = process.stderr.decode('utf-8', errors='replace')
        else:
            # 非Windows系统使用原来的方法
            process = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=COMMAND_TIMEOUT
            )
            stdout = process.stdout
            stderr = process.stderr
        
        if process.returncode == 0:
            return stdout
        else:
            error_msg = f"sviz命令执行失败 (错误码 {process.returncode}):\n{stderr}"
            logger.error(error_msg)
            return error_msg
    
    except subprocess.TimeoutExpired:
        return f"sviz命令执行超时 (超过 {COMMAND_TIMEOUT} 秒)"
    except Exception as e:
        error_msg = f"执行sviz命令时发生错误: {str(e)}"
        logger.error(error_msg)
        return error_msg

@mcp.tool()
async def run_sjob(command: str) -> str:
    """
    直接运行sjob作业管理工具命令
    
    Args:
        command: 要执行的sjob命令参数
    """
    # 显示详细的命令帮助
    sjob_help = """
sjob - 批处理作业管理工具

主要功能:
  创建和管理高通量计算的批处理作业，自动化生成多个参数组合的计算作业

主要命令:
  schedule    创建作业调度脚本，基于批处理配置生成调度文件 
  create      创建作业文件结构，构建作业目录和替换配置文件中的变量
  execute     执行作业，运行指定命令处理批处理作业
使用方法:
    一定要先查看子命令具体帮助再使用，不能想当然的输入参数，要根据具体帮助来输入参数。

如果要查看子命令具体帮助，请输入参数:
  schedule --help
  create --help
  execute --help
    """
    
    try:
        # 如果只是获取总体帮助信息，直接返回预定义的帮助
        if command == "--help" or command == "-h":
            return sjob_help
            
        logger.info(f"获取sjob子命令: {command}")
                  
        # 获取suan/cli/main.py脚本路径
        main_py_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cli', 'main.py')
        
        if sys.platform == "win32":
            # 通过main.py执行sjob命令
            full_command = f"python \"{main_py_path}\" sjob {command}"
            logger.info(f"执行sjob命令: {full_command}")
            
            # 使用subprocess.run，但设置较短的超时时间
            try:
                process = subprocess.run(
                    full_command,
                    shell=True,
                    capture_output=True,
                    text=False,  # 不自动解码
                    timeout=100  # 超时时间
                )
                
                # 尝试解码输出
                try:
                    stdout = process.stdout.decode('utf-8', errors='replace') if process.stdout else ""
                    stderr = process.stderr.decode('utf-8', errors='replace') if process.stderr else ""
                    logger.info(f"执行sjob命令输出: {stdout}")
                    logger.info(f"执行sjob命令问题输出: {stderr}")
                except Exception:
                    stdout = str(process.stdout)
                    stderr = str(process.stderr)
                
                if process.returncode == 0:
                    return stdout or "命令执行成功，无输出"
                else:
                    # 如果是因为命令行参数错误，提供针对性的帮助信息
                    if "Error: No such command" in stderr or "Missing command" in stderr:
                        return f"{stderr}\n\n请使用以下命令之一:\n- sjob schedule --json-file batch.json\n- sjob create --json-file batch.json\n- sjob execute --json-file batch.json\n或者使用 --help 获取更多帮助:\n- sjob --help\n- sjob schedule --help"
                    elif "Error: Missing option" in stderr or "required parameter" in stderr:
                        if "schedule" in command:
                            return f"{stderr}\n\n请提供必要的参数\n完整的参数列表请使用:\n schedule --help"
                        elif "create" in command:
                            return f"{stderr}\n\n请提供必要的参数\n完整的参数列表请使用:\n create --help"
                        elif "execute" in command:
                            return f"{stderr}\n\n请提供必要的参数\n完整的参数列表请使用:\n execute --help"
                        else:
                            return f"{stderr}\n\n请检查命令参数，或者使用 --help 获取帮助。"
                    else:
                        error_msg = f"sjob命令执行失败 (错误码 {process.returncode}):\n{stderr}"
                        logger.error(error_msg)
                        return error_msg
            
            except subprocess.TimeoutExpired:
                # 命令超时，可能是卡住了，提供一些简单的反馈
                if "create" in command:
                    return "创建批处理作业结构...\n请检查当前目录，确认作业目录是否已创建。"
                elif "schedule" in command:
                    return "调度批处理作业...\n请检查当前目录，确认作业调度是否已完成。"
                elif "execute" in command:
                    return "执行批处理作业...\n请检查当前目录，确认作业是否正在执行。"
                else:
                    return f"sjob命令执行超时，请尝试在终端中直接运行: {full_command}"
        
        else:
            # 非Windows系统使用main.py运行sjob命令
            main_py_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cli', 'main.py')
            full_command = f"python \"{main_py_path}\" sjob {command}"
            logger.info(f"执行sjob命令: {full_command}")
            
            try:
                process = subprocess.run(
                    full_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=10  # 使用较短的超时时间
                )
                
                if process.returncode == 0:
                    return process.stdout or "命令执行成功，无输出"
                else:
                    # 如果是因为命令行参数错误，提供针对性的帮助信息
                    if "Error: No such command" in process.stderr or "Missing command" in process.stderr:
                        return f"{process.stderr}\n\n请使用以下命令之一:\n- sjob schedule --file batch.json\n- sjob create --file batch.json\n- sjob execute --cmd \"命令\"\n\n或者使用 --help 获取更多帮助:\n- sjob --help\n- sjob schedule --help"
                    elif "Error: Missing option" in process.stderr or "required parameter" in process.stderr:
                        if "schedule" in command:
                            return f"{process.stderr}\n\n请提供必要的参数，例如:\n- sjob schedule --file batch.json\n\n完整的参数列表请使用:\n- sjob schedule --help"
                        elif "create" in command:
                            return f"{process.stderr}\n\n请提供必要的参数，例如:\n- sjob create --file batch.json\n\n完整的参数列表请使用:\n- sjob create --help"
                        elif "execute" in command:
                            return f"{process.stderr}\n\n请提供必要的参数，例如:\n- sjob execute --cmd \"echo '执行命令'\"\n\n完整的参数列表请使用:\n- sjob execute --help"
                        else:
                            return f"{process.stderr}\n\n请检查命令参数，或者使用 --help 获取帮助。"
                    else:
                        error_msg = f"sjob命令执行失败 (错误码 {process.returncode}):\n{process.stderr}"
                        logger.error(error_msg)
                        return error_msg
            
            except subprocess.TimeoutExpired:
                # 命令超时，可能是卡住了，提供一些简单的反馈
                if "create" in command:
                    return "创建批处理作业结构...\n请检查当前目录，确认作业目录是否已创建。"
                elif "schedule" in command:
                    return "调度批处理作业...\n请检查当前目录，确认作业调度是否已完成。"
                elif "execute" in command:
                    return "执行批处理作业...\n请检查当前目录，确认作业是否正在执行。"
                else:
                    return f"sjob命令执行超时，请尝试在终端中直接运行: {full_command}"
    
    except Exception as e:
        error_msg = f"执行sjob命令时发生错误: {str(e)}"
        logger.error(error_msg)
        return error_msg

# ======================= 动态集成CLI命令 =======================

def integrate_cli_commands():
    """动态集成CLI命令到MCP工具"""
    logger.info("开始集成CLI命令...")
    
    try:
        # 发现并提取CLI命令
        cli_commands = discover_and_integrate_cli()
        
        if not cli_commands:
            logger.warning("未找到CLI命令")
            return
        
        # 为每个CLI命令创建MCP工具
        for group_name, commands in cli_commands.items():
            for cmd_name, cmd_info in commands.items():
                tool_name = f"{group_name}_{cmd_name}"
                
                # 动态创建工具函数
                async def cli_tool_function(**kwargs):
                    return await execute_cli_command(group_name, cmd_name, kwargs)
                
                # 更新函数属性
                cli_tool_function.__name__ = tool_name
                cli_tool_function.__doc__ = cmd_info['help']
                
                # 注册为MCP工具
                mcp.tool()(cli_tool_function)
                
                logger.info(f"集成CLI命令为MCP工具: {tool_name}")
        
        logger.info(f"CLI命令集成完成")
    
    except Exception as e:
        logger.error(f"集成CLI命令时出错: {e}")

async def execute_cli_command(group_name: str, cmd_name: str, params: Dict[str, Any]) -> str:
    """执行CLI命令并返回结果"""
    try:
        # 构建命令行
        cmd_parts = [group_name, cmd_name]
        
        # 添加参数
        for name, value in params.items():
            if isinstance(value, bool):
                # 布尔参数
                if value:
                    cmd_parts.append(f"--{name}")
            else:
                # 其他参数
                cmd_parts.append(f"--{name}")
                cmd_parts.append(str(value))
        
        # 执行命令
        cmd_line = " ".join(cmd_parts)
        logger.info(f"执行CLI命令: {cmd_line}")
        
        process = subprocess.run(
            cmd_line,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=COMMAND_TIMEOUT
        )
        
        if process.returncode == 0:
            return process.stdout
        else:
            error_msg = f"命令执行失败 (错误码 {process.returncode}):\n{process.stderr}"
            logger.error(error_msg)
            return error_msg
    
    except subprocess.TimeoutExpired:
        return f"命令执行超时 (超过 {COMMAND_TIMEOUT} 秒)"
    except Exception as e:
        error_msg = f"执行命令时发生错误: {str(e)}"
        logger.error(error_msg)
        return error_msg

# ======================= 运行服务器 =======================

def run_server():
    """运行MCP服务器"""
    logger.info(f"启动 {SERVER_NAME} MCP服务器 (v{SERVER_VERSION})")
    
    try:
        # 设置日志级别
        logging.getLogger().setLevel(getattr(logging, LOG_LEVEL))
        
        # 集成STK核心工具
        available_tools = integrate_stk_core_tools()
        logger.info(f"成功集成STK核心工具: {', '.join(available_tools) if available_tools else '无'}")
        
        # 集成CLI命令
        if ENABLE_COMMAND_EXECUTION:
            integrate_cli_commands()
        
        # 启动服务器
        mcp.run(transport='stdio')
    except KeyboardInterrupt:
        logger.info("服务器被用户中断")
    except Exception as e:
        logger.error(f"服务器运行错误: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(run_server())
