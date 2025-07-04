# STK MCP Server - CLI集成版本

## 概述

STK MCP Server CLI集成版本是一个动态发现并集成现有CLI命令的MCP服务器实现。它能够自动将STK工具包中的CLI命令转换为MCP工具，使AI助手能够直接调用这些科学计算功能。

## 主要特性

### ✅ 动态CLI集成
- **自动发现**：自动扫描`toolkits/`目录下的所有CLI工具包
- **即时转换**：将Click命令自动转换为MCP工具定义
- **参数映射**：智能解析CLI参数并生成对应的JSON Schema

### ✅ 完整的MCP协议支持
- **工具列表**：实现`list_tools`接口，动态返回所有可用工具
- **工具调用**：实现`call_tool`接口，执行CLI命令并返回结果
- **错误处理**：完善的错误处理和日志记录机制

### ✅ 混合工具支持
- **静态工具**：提供系统信息和状态查询工具
- **动态工具**：所有CLI命令都自动成为可调用的MCP工具
- **扩展性**：支持添加新的工具包，无需修改服务器代码

## 安装和配置

### 环境要求
- Python 3.10+
- conda 环境管理器
- MCP 相关包

### 安装步骤

1. **创建conda环境**
```bash
conda create -n mcp python=3.10 -y
```

2. **激活环境并安装依赖**
```bash
# Windows
cmd /c "conda activate mcp && pip install mcp click"

# Linux/Mac
conda activate mcp
pip install mcp click
```

3. **验证安装**
```bash
# Windows
cmd /c "conda activate mcp && python test_cli_integration.py"

# Linux/Mac
conda activate mcp
python test_cli_integration.py
```

## 使用方法

### 启动服务器

**方式1：作为模块运行**
```bash
# Windows
cmd /c "conda activate mcp && python -m suan.mcp_server"

# Linux/Mac  
conda activate mcp
python -m suan.mcp_server
```

**方式2：直接运行**
```bash
# Windows
cmd /c "conda activate mcp && python suan/mcp_server/cli_integrated_server.py"

# Linux/Mac
conda activate mcp
python suan/mcp_server/cli_integrated_server.py
```

### AI客户端配置

**Claude Desktop配置**
```json
{
  "mcpServers": {
    "stk-toolkit": {
      "command": "cmd",
      "args": ["/c", "conda activate mcp && python -m suan.mcp_server"],
      "cwd": "D:/work/sijin/stk"
    }
  }
}
```

**对于Linux/Mac系统**
```json
{
  "mcpServers": {
    "stk-toolkit": {
      "command": "bash",
      "args": ["-c", "conda activate mcp && python -m suan.mcp_server"],
      "cwd": "/path/to/stk"
    }
  }
}
```

## 可用工具

### 静态工具

#### `stk_info`
获取STK工具包的基本信息
- **参数**：无
- **返回**：系统信息、可用工具组统计、使用提示

#### `stk_status`  
获取CLI系统的详细状态
- **参数**：无
- **返回**：所有可用工具的详细列表

### 动态CLI工具

#### sjob工具组

##### `sjob_schedule`
生成参数组合的批处理列表
- **参数**：
  - `keyword` (string): 关键词，用于批处理列表
  - `value` (string): 每个关键词的值
  - `condition` (string): 过滤条件，默认"1>0"
  - `separater` (string): 分隔符，默认"+"
  - `format` (string): 格式，默认"%s"
  - `json_file` (path, optional): JSON配置文件

##### `sjob_create`
创建文件夹结构并复制文件
- **参数**：
  - `file_list` (string): 要复制的文件列表
  - `start` (integer, optional): 起始索引
  - `end` (integer, optional): 结束索引
  - `json_file` (path, optional): JSON配置文件

##### `sjob_execute`
在每个文件夹中执行命令
- **参数**：
  - `command` (string): 要执行的命令
  - `start` (integer): 起始索引，默认1
  - `end` (integer, optional): 结束索引
  - `json_file` (path, optional): JSON配置文件

## 使用示例

### 在AI助手中使用

**查看可用工具**
```
请使用stk_info工具查看STK工具包的信息
```

**生成参数组合**
```
请使用sjob_schedule工具生成频率参数组合：
- keyword: "FREQ"  
- value: "1e12 1e13 1e14"
- condition: "1>0"
```

**创建任务文件夹**
```
请使用sjob_create工具创建任务文件夹：
- file_list: "input.txt output.txt"
- start: 1
- end: 3
```

## 扩展新工具包

### 添加新的CLI工具包

1. **在`toolkits/`目录下创建新的工具包目录**
```
toolkits/
├── your_toolkit/
│   ├── __init__.py
│   └── cli.py
```

2. **在`cli.py`中定义Click命令组**
```python
import click

@click.group()
def your_toolkit():
    """Your toolkit description"""
    pass

@your_toolkit.command()
@click.option('--param1', type=str, help='Parameter 1')
@click.option('--param2', type=int, help='Parameter 2')
def your_command(param1, param2):
    """Your command description"""
    # 实现你的命令逻辑
    click.echo(f"Running with {param1} and {param2}")

if __name__ == "__main__":
    your_toolkit()
```

3. **重启MCP服务器**
新工具包会自动被发现和集成，无需修改服务器代码。

## 故障排除

### 常见问题

**Q: 环境激活失败**
```bash
# 确保conda在PATH中
conda --version

# 检查环境是否存在
conda info --envs
```

**Q: 导入错误**
```bash
# 检查包是否安装
cmd /c "conda activate mcp && pip list | findstr mcp"
```

**Q: CLI工具发现失败**
```bash
# 检查toolkits目录结构
ls toolkits/*/cli.py

# 手动测试CLI命令
cmd /c "conda activate mcp && python -c \"from suan.cli.main import cli, load_plugins; load_plugins(); print(list(cli.commands.keys()))\""
```

**Q: 工具调用失败**
- 检查参数是否正确
- 查看服务器日志输出
- 使用测试脚本验证功能

### 调试模式

启动服务器时查看详细日志：
```bash
cmd /c "conda activate mcp && python suan/mcp_server/cli_integrated_server.py"
```

运行测试脚本：
```bash
cmd /c "conda activate mcp && python test_cli_integration.py"
cmd /c "conda activate mcp && python test_sjob_tool.py"
```

## 技术架构

### 核心组件

1. **CLI初始化器**：负责加载和初始化现有的CLI系统
2. **工具发现器**：将Click命令转换为MCP工具定义
3. **工具执行器**：执行CLI命令并处理结果
4. **MCP协议处理器**：处理MCP协议的请求和响应

### 设计优势

- **零重复开发**：100%复用现有CLI基础设施
- **自动发现**：新工具包无需手动配置
- **类型安全**：智能推断参数类型和验证
- **错误处理**：完善的异常处理和用户友好的错误消息

## 贡献和支持

如果您遇到问题或有改进建议，请：

1. 查看本文档的故障排除部分
2. 运行测试脚本进行调试
3. 检查服务器日志输出
4. 提供详细的错误信息和环境信息

---

**STK MCP Server CLI集成版本** - 让AI助手直接调用科学计算工具的最佳方案！