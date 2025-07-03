# STK MCP Server

一个极简、可扩展的MCP (Model Context Protocol) 服务器，将STK的CLI工具集成为AI助手可直接调用的工具。

> **最新更新:** 修复了MCP库版本兼容性问题，现在支持MCP 1.0.0及更高版本

## 架构概览

```
mcp_server/
├── cli_integrated_server.py  # 集成CLI与MCP的主服务器实现
├── __main__.py               # 启动入口点
├── __init__.py               # 模块初始化
├── requirements.txt          # 依赖项
├── README.md                 # 详细文档
└── QUICK_START.md            # 快速上手指南
```

核心思想：极简设计，避免冗余代码，直接复用现有CLI命令系统。

## 快速开始

### 1. 安装依赖

确保你已经安装了必要的Python包：

```powershell
# 基本安装方式
pip install -r requirements.txt

# 确认MCP版本（必须>=1.0.0）
pip show mcp
```

**重要:** 如果MCP版本低于1.0.0，会导致`Server.run() missing 1 required positional argument: 'initialization_options'`错误。请升级MCP:

```powershell
pip install --upgrade mcp>=1.0.0
```

### 2. 启动MCP服务器

推荐使用conda环境并设置正确的编码变量：

#### Windows系统:
```powershell
# 激活环境并设置编码
conda activate mcp
set PYTHONIOENCODING=utf-8
set PYTHONLEGACYWINDOWSSTDIO=1

# 启动服务器
python -m suan.mcp_server
```

#### Linux/Mac系统:
```bash
# 激活环境并设置编码
conda activate mcp
export PYTHONIOENCODING=utf-8

# 启动服务器
python -m suan.mcp_server
```

#### 测试服务器是否可正常启动：
```powershell
python d:\work\sijin\stk\suan\mcp_server\test_server.py
```

### 3. 配置AI客户端

启动后，服务器将通过stdin/stdout与AI客户端通信。配置你的AI客户端连接到这个MCP服务器。

#### Claude Desktop配置

在Claude Desktop的配置文件中添加：

**配置文件位置**：
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "stk-toolkit": {
      "command": "cmd",
      "args": ["/c", "conda run -n mcp python -m suan.mcp_server"],
      "cwd": "d:\\work\\sijin\\stk",
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONLEGACYWINDOWSSTDIO": "1"
      }
    }
  }
}
```

#### VS Code配置

在项目根目录创建或修改`.vscode/mcp.json`文件：

```json
{
  "servers": {
    "stk-toolkit": {
      "command": "cmd",
      "args": ["/c", "conda run -n mcp python -m suan.mcp_server"],
      "cwd": "D:/work/sijin/stk",
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONLEGACYWINDOWSSTDIO": "1"
      }
    }
  }
}
```

#### Cursor编辑器配置

与VS Code类似，创建适当的配置文件，确保使用conda环境并设置正确的编码变量。
  ]
}
```

**方式2：通过工作区配置**
在项目根目录创建 `.cursor/mcp_config.json`：

```json
{
  "servers": {
    "stk-toolkit": {
      "command": ["python", "-m", "suan.mcp_server"],
      "cwd": "d:\\work\\sijin\\stk",
      "env": {
        "STK_MCP_LOG_LEVEL": "DEBUG"
      },
      "capabilities": {
        "tools": true,
        "resources": false
      }
    }
  }
}
```

#### VS Code Copilot配置

VS Code Copilot通过扩展支持MCP协议：

**步骤1：安装MCP扩展**
```bash
# 搜索并安装MCP相关扩展
code --install-extension model-context-protocol.mcp-client
```

**步骤2：配置settings.json**
在VS Code的设置文件中添加：

```json
{
  "mcp.servers": {
    "stk-toolkit": {
      "command": "python",
      "args": ["-m", "suan.mcp_server"],
      "cwd": "d:\\work\\sijin\\stk",
      "env": {
        "STK_MCP_DEBUG": "false",
        "STK_MCP_LOG_LEVEL": "INFO"
      },
      "capabilities": {
        "tools": true,
        "prompts": false,
        "resources": false
      }
    }
  },
  "mcp.enableAutoDiscovery": true,
  "mcp.logLevel": "info"
}
```

**步骤3：工作区特定配置**
在项目的 `.vscode/settings.json` 中：

```json
{
  "mcp.servers": {
    "stk-toolkit": {
      "command": "python",
      "args": ["-m", "suan.mcp_server"],
      "cwd": "${workspaceFolder}",
      "displayName": "STK Scientific Toolkit",
      "description": "Tools for scientific computation and analysis"
    }
  }
}
```

#### 通用配置说明

**环境变量配置**（适用于所有客户端）：
```json
{
  "env": {
    "STK_MCP_DEBUG": "false",
    "STK_MCP_LOG_LEVEL": "INFO",
    "PYTHONPATH": "d:\\work\\sijin\\stk",
    "PATH": "${env:PATH}"
  }
}
```

**命令行参数说明**：
- `python`: Python解释器路径（确保与项目环境一致）
- `-m suan.mcp_server`: 运行MCP服务器模块
- `cwd`: 项目工作目录
- `env`: 环境变量设置

## 配置选项

### 环境变量

- `STK_MCP_DEBUG`: 设置为`true`启用调试模式
- `STK_MCP_LOG_LEVEL`: 设置日志级别（DEBUG, INFO, WARNING, ERROR）
- `STK_MCP_CLI_MODULE`: 指定CLI模块路径（默认：`suan.cli.main`）

### 配置文件

创建`mcp_config.json`文件：

```json
{
  "debug": false,
  "log_level": "INFO",
  "cli_module": "suan.cli.main",
  "excluded_commands": ["internal-cmd"],
  "custom_executors": {
    "special-tool": "my_module.SpecialExecutor"
  }
}
```


## 调试和故障排除

### 启用调试模式

```powershell
# Windows PowerShell
$env:STK_MCP_DEBUG="true"
python -m suan.mcp_server

# Windows CMD
set STK_MCP_DEBUG=true
python -m suan.mcp_server

# Linux/macOS
export STK_MCP_DEBUG=true
python -m suan.mcp_server
```

### 常见问题

1. **Server.run() missing 1 required positional argument: 'initialization_options'**
   - 这是MCP库版本不兼容导致的，请确保：
   ```bash
   # 检查MCP版本，必须>=1.0.0
   pip show mcp
   
   # 升级MCP库
   pip install --upgrade mcp>=1.0.0
   ```
   - 确保使用最新版的`cli_integrated_server.py`文件，其中已正确传递`initialization_options`参数

2. **工具未被发现**
   ```bash
   # 检查CLI模块是否正确导入
   python -m suan.cli.main --help
   
   # 检查工具包结构
   ls toolkits/*/cli.py
   
   # 启用详细日志
   STK_MCP_LOG_LEVEL=DEBUG python -m suan.mcp_server
   ```

2. **参数转换错误**
   - 检查Click参数定义与MCP调用参数是否匹配
   - 确认参数类型（string, integer, boolean等）
   - 查看MCP工具定义：
   ```bash
   # 在调试模式下会输出工具定义
   STK_MCP_DEBUG=true python -m suan.mcp_server
   ```

3. **执行失败**
   - 检查Python环境和依赖：
   ```bash
   python -c "import click, mcp; print('Dependencies OK')"
   ```
   - 确认文件路径和权限
   - 检查工作目录设置

4. **客户端连接问题**
   - **Claude Desktop**: 检查配置文件语法和路径
   - **Cursor**: 确认MCP扩展已正确安装
   - **VS Code**: 验证MCP扩展版本兼容性

### 各编辑器特定问题

#### Claude Desktop故障排除

1. **配置文件不生效**：
   - 确认文件路径正确
   - 检查JSON语法是否有效
   - 重启Claude Desktop

2. **权限问题**：
   ```json
   {
     "mcpServers": {
       "stk-tools": {
         "command": "python",
         "args": ["-m", "suan.mcp_server"],
         "cwd": "d:\\work\\sijin\\stk",
         "env": {
           "PYTHONPATH": "d:\\work\\sijin\\stk"
         }
       }
     }
   }
   ```

#### Cursor编辑器故障排除

1. **MCP服务器无响应**：
   - 检查Cursor的MCP扩展是否最新版本
   - 查看扩展日志：`Ctrl+Shift+P` -> "Developer: Toggle Developer Tools"

2. **工具调用失败**：
   ```bash
   # 在终端中测试MCP服务器
   echo '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}' | python -m suan.mcp_server
   ```

#### VS Code Copilot故障排除

1. **MCP扩展冲突**：
   - 禁用其他MCP相关扩展
   - 重新加载窗口：`Ctrl+Shift+P` -> "Developer: Reload Window"

2. **工具不可见**：
   - 检查settings.json配置
   - 确认工作区配置优先级

### 日志分析

#### 正常启动日志
```
[INFO] STK MCP Server starting...
[INFO] Loading CLI plugins...
[INFO] Loaded 3 command groups: sjob, smesh, sviz
[DEBUG] Discovered 8 tools total
[DEBUG] Tool 'sjob_schedule' registered with parameters: keyword, value, output
[INFO] MCP Server ready for connections
```

#### 错误日志示例
```
[ERROR] Failed to import CLI modules: No module named 'suan.cli.main'
[ERROR] Tool sjob_schedule execution failed: Required parameter 'keyword' not provided
[WARNING] Command group 'broken_tool' has no valid commands
```

### 性能优化

#### 启动优化
- **工具缓存**：首次发现的工具会被缓存
- **延迟加载**：只在需要时加载具体工具
- **预热模式**：
  ```bash
  STK_MCP_PRELOAD=true python -m suan.mcp_server
  ```

#### 运行时优化
- **异步执行**：所有工具调用都是异步的
- **并发控制**：可以配置最大并发数
  ```json
  {
    "env": {
      "STK_MCP_MAX_CONCURRENT": "5"
    }
  }
  ```

### 测试工具

#### 命令行测试
```bash
# 测试工具发现
python -c "
from suan.mcp_server.tool_discovery import ToolDiscovery
import asyncio
discovery = ToolDiscovery()
tools = asyncio.run(discovery.discover_tools())
print(f'Found {len(tools)} tools')
for tool in tools:
    print(f'- {tool.name}: {tool.description}')
"

# 测试工具执行
python -c "
from suan.mcp_server.tool_executor import ToolExecutor
import asyncio
executor = ToolExecutor()
result = asyncio.run(executor.execute('sjob_schedule', {'keyword': 'TEST', 'value': '123'}))
print(result)
"
```

#### 集成测试脚本
```python
# test_mcp_integration.py
import asyncio
import json
from suan.mcp_server.server import STKMCPServer

async def test_mcp_server():
    server = STKMCPServer()
    
    # 测试工具发现
    tools = await server.tool_discovery.discover_tools()
    print(f"✅ Discovered {len(tools)} tools")
    
    # 测试工具执行
    if tools:
        tool_name = tools[0].name
        result = await server.tool_executor.execute(tool_name, {})
        print(f"✅ Tool {tool_name} executed")
    
    print("🎉 All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_mcp_server())
```

### 监控和维护

#### 日志文件配置
```python
# 在启动脚本中添加文件日志
import logging
from logging.handlers import RotatingFileHandler

# 配置轮转日志
handler = RotatingFileHandler(
    'stk_mcp_server.log', 
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
logging.getLogger().addHandler(handler)
```

#### 健康检查
创建健康检查端点：
```python
# health_check.py
import asyncio
from suan.mcp_server.tool_discovery import ToolDiscovery

async def health_check():
    try:
        discovery = ToolDiscovery()
        tools = await discovery.discover_tools()
        return {"status": "healthy", "tools_count": len(tools)}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

print(asyncio.run(health_check()))
```

## 使用示例

### 在Claude Desktop中使用

配置完成后，在Claude Desktop中可以直接使用STK工具：

```
用户: 请帮我使用sjob工具生成FREQ参数的调度，值为"1e12 1e13"

Claude: 我来帮您使用sjob工具生成参数调度。

[调用工具: sjob_schedule]
参数: {
  "keyword": "FREQ", 
  "value": "1e12 1e13"
}

[工具执行结果]
Parameter scheduling completed:
  FREQ: 1e12, 1e13
  Generated 2 parameter combinations
  Ready for job creation

调度已完成！生成了2个参数组合，包含FREQ参数的两个值：1e12和1e13。
```

### 在Cursor中使用

配置完成后，在Cursor编辑器中：

1. **通过Chat界面使用**：
   - 打开Cursor的AI Chat面板
   - 输入请求：`使用STK的sjob工具创建作业文件`
   - AI会自动调用对应的MCP工具

2. **在代码中使用**：
   - 选中代码片段
   - 按 `Ctrl+K` 或 `Cmd+K`
   - 输入：`用STK工具分析这个数据文件`
   - AI会根据上下文调用合适的工具

3. **工具发现**：
   ```
   用户: 显示所有可用的STK工具
   
   Cursor AI: 我来查看可用的STK工具。
   
   [自动调用工具发现]
   
   可用工具：
   - sjob_schedule: 参数调度工具
   - sjob_create: 作业创建工具
   - sjob_execute: 作业执行工具
   - smesh_generate: 网格生成工具
   - sviz_plot: 数据可视化工具
   ```

### 在VS Code中使用

配置MCP扩展后，在VS Code中使用STK工具：

1. **通过命令面板**：
   - 按 `Ctrl+Shift+P` 打开命令面板
   - 搜索 "MCP: List Tools"
   - 选择STK工具进行调用

2. **通过Copilot Chat**：
   ```
   @workspace 请使用STK的网格生成工具处理当前项目中的几何文件
   ```

3. **内联使用**：
   - 在代码注释中：`// 使用STK工具生成这个参数的作业文件`
   - Copilot会建议调用相应的MCP工具

4. **快捷键配置**：
   在 `keybindings.json` 中添加：
   ```json
   {
     "key": "ctrl+alt+s",
     "command": "mcp.callTool",
     "args": {
       "server": "stk-toolkit",
       "tool": "sjob_schedule"
     }
   }
   ```

### 工具命名规则

MCP服务器会自动将CLI命令转换为MCP工具：

| CLI命令 | MCP工具名 | 描述 |
|---------|----------|------|
| `suan sjob schedule` | `sjob_schedule` | 参数调度 |
| `suan sjob create` | `sjob_create` | 作业创建 |
| `suan smesh generate` | `smesh_generate` | 网格生成 |
| `suan sviz plot` | `sviz_plot` | 数据绘图 |

### 参数传递示例

**原CLI命令**：
```bash
python -m suan.cli.main sjob schedule --keyword FREQ --value "1e12 1e13" --output jobs.json
```

**MCP工具调用**：
```json
{
  "tool": "sjob_schedule",
  "arguments": {
    "keyword": "FREQ",
    "value": "1e12 1e13",
    "output": "jobs.json"
  }
}
```

## 扩展开发

### 添加新工具包

1. 在 `toolkits/` 目录下创建新的工具包目录
2. 按照现有规范创建 `cli.py` 文件：

```python
import click

@click.group()
def my_new_tool():
    """新工具包的描述"""
    pass

@my_new_tool.command()
@click.option('--input', help='输入文件路径')
@click.option('--output', help='输出文件路径')
def process(input, output):
    """处理数据的命令"""
    # 实现逻辑
    click.echo(f"Processing {input} -> {output}")
```
3. 重启MCP服务器，新工具会自动被发现和注册

### 自定义工具执行器

为特殊工具创建自定义执行逻辑：

```python
# custom_executor.py
from suan.mcp_server.tool_executor import BaseToolExecutor

class MyCustomExecutor(BaseToolExecutor):
    async def can_handle(self, tool_name: str) -> bool:
        return tool_name.startswith('my_special_')
    
    async def execute(self, tool_name: str, arguments: dict) -> str:
        # 自定义执行逻辑
        result = await self.my_special_logic(arguments)
        return f"## Custom Result\n\n{result}"

# 注册自定义执行器
from suan.mcp_server.config import register_custom_executor
register_custom_executor(MyCustomExecutor)
```







