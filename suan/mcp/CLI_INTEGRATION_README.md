# MCP Server CLI集成说明

STK MCP Server能够自动发现并集成现有的CLI命令，使AI助手能够直接调用这些科学计算功能。

## 工作原理

1. MCP服务器启动时会自动扫描并发现项目中的CLI命令
2. 每个CLI命令会被转换为一个MCP工具
3. AI助手可以通过MCP协议调用这些工具
4. 命令执行结果会被返回给AI助手

## 支持的CLI模块

MCP服务器会自动查找以下模块中的CLI命令：

- `suan.cli.main` - 主CLI模块
- `toolkits.sjob.cli` - 作业管理CLI
- `toolkits.smesh.cli` - 网格处理CLI
- `toolkits.sviz.cli` - 可视化CLI

## 工具命名规则

每个CLI命令会被转换为一个命名为 `{模块名}_{命令名}` 的MCP工具。例如：

- `sviz plot-scalar` 命令会被转换为 `sviz_plot-scalar` 工具
- `smesh generate` 命令会被转换为 `smesh_generate` 工具

## 配置

可以在 `suan/mcp/config.py` 文件中配置以下选项：

- `ENABLE_COMMAND_EXECUTION` - 是否启用CLI命令执行功能
- `COMMAND_TIMEOUT` - 命令执行最大超时时间
- `ALLOWED_COMMANDS` - 允许执行的命令前缀列表

## 安全性

MCP服务器实现了以下安全措施：

1. 只允许执行白名单中的命令前缀
2. 命令执行有超时限制
3. 文件访问限制在工作目录内
4. 输入参数经过验证和净化
