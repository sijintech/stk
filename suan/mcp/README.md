# STK MCP Server

STK MCP Server是基于Model Context Protocol (MCP)标准的服务器实现，可以将STK科学计算工具包提供给AI助手使用。

## 简介

MCP（Model Context Protocol，模型上下文协议）是由Anthropic推出的开放标准，旨在统一大型语言模型与外部数据源和工具之间的通信。STK MCP Server实现了这一协议，使AI模型能够安全地访问科学计算功能。

## 核心功能

- **CLI命令集成**：自动发现并集成STK工具包中的CLI命令
- **文件访问**：安全地读取和操作工作目录内的文件
- **数据可视化**：提供科学数据的可视化功能
- **统计计算**：执行基本的统计计算和数据处理

## 支持的客户端

STK MCP Server支持以下MCP客户端：

- Claude Desktop
- Cursor
- Cline
- VSCode (带MCP插件)
- 任何其他支持MCP协议的客户端

## 快速开始

### 安装依赖

```bash
pip install "mcp[cli]" httpx matplotlib numpy
```

### 运行服务器

```bash
python -m suan.mcp
```

### 使用MCP Inspector进行测试

```bash
mcp dev suan/mcp/server.py
```

然后访问 http://localhost:5173/ 进行功能测试

## CLI命令集成

STK MCP Server能够自动发现并集成现有的CLI命令，使AI助手能够直接调用这些科学计算功能。详情请参阅 [CLI集成说明](CLI_INTEGRATION_README.md)。