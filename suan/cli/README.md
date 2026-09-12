# STK CLI

持久任务与安装说明统一维护在 [runtime 使用指南](../../docs/runtime.md)。

`suan sjob/smesh/sviz` 保留科学工具入口。`suan server` 管理本机服务，
`suan connect` 保存连接，`suan workspaces` 管理输入，`suan jobs` 管理持久任务。
每个命令组均支持 `--help`；工作区与任务命令可通过 `--profile` 连接 SSH 转发端口。

部署排查使用 `suan server doctor --backend local --science`；服务器上可将后端改为
`pbs`／`slurm`。客户端使用 `suan connect check NAME` 检查已保存连接。
两个诊断命令都支持 `--json` 和 `--timeout`，有失败项时退出码为 1。
