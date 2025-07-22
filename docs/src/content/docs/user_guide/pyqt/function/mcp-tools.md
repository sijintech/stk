---
title: MCP模块
description: MCP模块
---
STK 提供了基于 Model Context Protocol (MCP) 的工具集，允许 AI 助手安全地访问和使用 STK 工具包中的功能。本指南将介绍如何设置和使用这些 MCP 工具。

## 功能概述

STK MCP Server 是一个基于 Model Context Protocol 标准的服务器实现，提供以下特性：

- 允许 AI 助手安全地访问 STK 工具包中的功能
- 提供丰富的科学计算工具集，包括数据处理、可视化和模拟功能
- 支持多种 MCP 兼容客户端（如 Cursor、VSCode 等）
- 可扩展的工具集成架构
- 自动集成 CLI 命令为 MCP 工具

## 先决条件

使用 STK MCP 工具前，您需要准备：

- 已下载 STK 代码库
- MCP 兼容客户端（例如 Cursor、Claude Desktop、带有 MCP 插件的 VSCode）
- Python 环境（推荐 Python 3.8 或更高版本）

## 环境准备

在使用 MCP 工具前，请确保您已完成以下准备工作：

1. 安装 Python 环境（要求 Python 3.10 或更高版本）
2. 克隆或下载 STK 代码库到本地
3. 安装 STK 依赖项：
   ```bash
   pip install -e .
   ```
   或使用 Poetry：
   ```bash
   poetry install
   ```
4. 确保 STK 工具包可以正常运行

## 使用步骤

### 1. 启动服务器

在完成环境准备后，您可以通过以下方式启动 MCP 服务器：

#### 方法一：直接启动

在终端（命令提示符或 PowerShell）中，导航到 STK 项目根目录，然后运行：

```bash
python -m suan.mcp
```

服务器启动后，您将看到类似以下的输出：

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

#### 方法二：通过 MCP 客户端启动

如果您已经在 Cursor 或 VSCode 中配置了 MCP 服务器，客户端会在需要时自动启动服务器。

### 2. 连接到服务器

服务器启动后，您的 MCP 客户端（Cursor、VSCode 等）将自动连接到运行中的服务器（通常在 http://localhost:8000）。

如果连接成功，您将能够在客户端中使用 STK 提供的 MCP 工具。

### 3. 在 Cursor 中配置

要在 Cursor 中使用 STK MCP 工具，请按照以下步骤操作：

1. 在项目根目录下创建 `.cursor/mcp.json` 文件。
2. 添加以下内容：

   ```json
   {
       "mcpServers": {
           "stk-toolkit": {
               "command": "cmd.exe",
               "args": ["/c", "python -m suan.mcp"],
               "cwd": "您的STK项目路径",
               "env": {
                   "PYTHONIOENCODING": "utf-8",
                   "PYTHONLEGACYWINDOWSSTDIO": "1"
               }
           }
       }
   }
   ```

3. 替换 "您的STK项目路径" 为实际的 STK 项目绝对路径（例如 "D:/stk/work/stk"）。
4. 在 Cursor 中使用 AI 助手时，它将自动连接到配置的 MCP 服务器。
5. 如果您使用的是 Windows 系统，请确保使用 `cmd.exe` 作为命令执行器；如果是 Linux 或 macOS，请相应地修改命令和参数。

### 4. 在 VSCode 中配置

要在 VSCode 中使用 STK MCP 工具，请按照以下步骤操作：

1. 安装 VSCode MCP 插件（如果可用）。
2. 在项目根目录下创建 `.vscode/mcp.json` 文件。
3. 添加以下内容：

   ```json
   {
     "servers": {
       "stk-toolkit": {
         "command": "cmd.exe",
         "args": ["/c", "python -m suan.mcp"],
         "cwd": "您的STK项目路径",
         "env": {
           "PYTHONIOENCODING": "utf-8",
           "PYTHONLEGACYWINDOWSSTDIO": "1"
         }
       }
     }
   }
   ```

4. 替换 "您的STK项目路径" 为实际的 STK 项目绝对路径（例如 "D:/stk/work/stk"）。
5. 在 VSCode 中使用 MCP 插件连接到服务器。
6. 如果您使用的是 Windows 系统，请确保使用 `cmd.exe` 作为命令执行器；如果是 Linux 或 macOS，请相应地修改命令和参数。

## 可用工具

STK MCP 服务器提供多种工具，可分为以下几类：

### 核心工具

- `stk_info()`: 获取 STK 工具包的基本信息和可用功能列表
- `run_stk_command(command: str)`: 运行 STK 命令行工具
- `get_file_content(file_path: str)`: 获取文件内容
- `list_directory(directory_path: str)`: 列出目录中的文件和子目录

### 科学计算工具

- `calculate_statistics(data: List[float])`: 计算基本统计量
- `generate_plot(data: List[float], title: str, xlabel: str, ylabel: str)`: 生成简单的数据可视化图表

### STK 核心工具

- `run_smesh(command: str)`: 直接运行 smesh 网格处理工具命令
- `run_sviz(command: str)`: 直接运行 sviz 可视化工具命令
- `run_sjob(command: str)`: 直接运行 sjob 作业管理工具命令

### CLI 集成工具

MCP 服务器会自动发现并集成现有的 CLI 命令，每个 CLI 命令会被转换为一个命名为 `{模块名}_{命令名}` 的 MCP 工具。例如：

- `sviz plot-scalar` 命令会被转换为 `sviz_plot-scalar` 工具
- `smesh generate` 命令会被转换为 `smesh_generate` 工具

## 使用示例

以下是一些常见的 MCP 工具使用示例，您可以在支持 MCP 的 AI 助手中直接使用这些工具。

### 基本工具使用

```python
# 获取 STK 工具包信息
stk_info()

# 运行 STK 命令
run_stk_command("sviz plot-scalar --help")

# 读取文件内容
get_file_content("example.txt")

# 列出目录内容
list_directory("/path/to/your/directory")
```

### 使用 smesh 工具

```python
# 生成网格
run_smesh("generate --input input.json --output output.mesh")

# 或使用 CLI 集成工具
smesh_generate(input="input.json", output="output.mesh")
```

### 使用 sviz 可视化工具

```python
# 绘制标量场
run_sviz("plot-scalar --input data.vtk --output plot.png")

# 或使用 CLI 集成工具
sviz_plot_scalar(input="data.vtk", output="plot.png")
```

### 使用 sjob 作业管理工具

```python
# 创建作业
run_sjob("create --name my_job --script job.py")

# 执行作业
run_sjob("execute --name my_job")

# 或使用 CLI 集成工具
sjob_create(name="my_job", script="job.py")
sjob_execute(name="my_job")
```

### 数据处理示例

```python
# 计算统计数据
data = [1.2, 3.4, 5.6, 7.8, 9.0]
result = calculate_statistics(data)
print(f"平均值: {result['mean']}, 标准差: {result['std']}")

# 生成图表
generate_plot(data, title="数据分析", xlabel="索引", ylabel="值")
```

> **注意**：在使用文件路径时，建议使用绝对路径以避免路径解析问题。

## 最佳实践

使用 STK MCP 工具时，请遵循以下最佳实践：

1. **使用正确的工具类型**：优先使用专门的工具（如 `run_smesh`）而不是通用工具（如 `run_stk_command`）。

2. **提供完整路径**：在处理文件时，尽量使用绝对路径以避免路径解析问题。

3. **错误处理**：始终检查工具返回的错误信息，并根据需要进行调整。

4. **资源管理**：对于长时间运行的作业，使用 `sjob` 工具进行管理，而不是直接在 MCP 会话中运行。

5. **使用 CLI 集成工具**：当可用时，优先使用 CLI 集成工具（如 `smesh_generate`），因为它们提供更好的参数验证和帮助信息。

## 故障排除

### 安全注意事项

使用 STK MCP 工具时，请注意以下安全事项：

1. **文件访问限制**：MCP 服务器可能限制对某些目录的访问，请确保您的文件位于允许访问的目录中。

2. **命令执行限制**：只有白名单中的命令才能被执行，默认包括 `sviz`、`smesh` 和 `sjob`。

3. **超时限制**：长时间运行的命令可能会被自动终止，请使用 `sjob` 管理长时间运行的任务。

4. **参数验证**：所有工具参数都会经过验证，确保它们符合预期格式和范围。

5. **不要共享敏感信息**：避免在 MCP 会话中共享敏感信息，如密码或访问令牌。

### 配置问题

如果遇到配置问题：

1. 检查 `mcp.json` 文件中的路径是否正确
2. 确认 Python 环境和依赖项已正确安装
3. 验证 MCP 服务器是否正在运行
4. 查看服务器日志以获取更详细的错误信息

可以在 `suan/mcp/config.py` 文件中配置安全选项和其他服务器参数。

有关添加工具的开发者指南，请参阅[开发者指南](/dev_guide/pyqt/add-mcp-tool)。