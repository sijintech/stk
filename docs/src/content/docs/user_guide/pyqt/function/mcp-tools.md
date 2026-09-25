---
title: MCP 持久任务
description: 通过 MCP 使用 STK 本地与远程 runtime
---

STK 0.1.0a1 的 MCP 适配器通过 **stdio** 与 AI 客户端通信，再通过 HTTP
访问独立的 runtime。计算由 runtime 管理；关闭 AI 客户端不取消已提交任务。

## 安装和连接

runtime 只在 Linux 运行。以下本机步骤仅适用于 runtime 与 MCP 适配器位于同一台 Linux
主机的情况，在仓库根目录运行：

```bash
python -m pip install '.[server,science,mcp]'
suan server init
suan server start
python -m suan.mcp
```

在 MCP 客户端中配置启动命令为所安装环境的 Python 绝对路径，参数为
`["-m", "suan.mcp"]`；Linux 本机使用时，环境变量 `STK_STATE_DIR` 指向本机 runtime 状态目录。
远程使用时先建立 SSH 隧道，再设置 `STK_RUNTIME_URL` 为本机转发地址，
`STK_RUNTIME_TOKEN` 为服务器令牌。令牌应置于用户私有配置中。

Windows / macOS 只作客户端，必须按上述远程方式连接 Linux 服务器上的 runtime；在这些系统上
`suan server init/start` 会提示只支持 Linux 并退出。SSH 隧道与令牌的设置见仓库
`docs/runtime.md` 的“远程连接”一节。

MCP 不在 8000 端口提供 HTTP 服务。runtime 默认使用回环地址的 8765 端口，
仅通过带令牌的 API 接受请求。

## 任务流程

1. 用 `create_workspace` 创建工作区，`upload_input` 上传所需文件。
2. 用 `submit_task(spec, idempotency_key)` 提交任务，保存返回的任务 ID。
3. 用 `get_task` 查询状态，`get_task_logs` 按字节偏移读取增量日志。
4. 完成后用 `list_artifacts` 和 `download_artifact` 获取、校验结果。
5. 需要停止时调用 `cancel_task`，继续查询直到进入终态。

TaskSpec 示例：

```json
{
  "workspace_id": "替换为工作区ID",
  "argv": ["{python}", "simulate.py"],
  "backend": "local",
  "outputs": ["field.vtk", "preview.png"]
}
```

执行后端可选 `local`、`pbs`、`slurm`。提交成功表示任务已登记；最终成功必须
确认 `state == "succeeded"`。网络错误后重试提交须使用原幂等键，避免重复计算。
同一任务也能在桌面 Tasks 页与 `suan jobs` 中查看。

## 旧工具迁移

旧同步命令与自动发现的 CLI 工具改为统一任务入口。保留的
`run_stk_command(command, workspace_id, idempotency_key, backend)` 支持
`sjob/smesh/sviz` 命令，返回任务记录；不执行 shell 运算符。
`run_sjob/run_smesh/run_sviz` 及动态工具名称不再注册，请更新客户端工具调用。
原本的任意文件／命令访问应迁移为工作区输入上传和 TaskSpec。

完整部署、SSH、状态机、输入输出格式及站点验收说明见仓库 `docs/runtime.md`。
