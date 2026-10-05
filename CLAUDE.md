# Claude 开发入口

开始工作前读取 [AGENTS.md](AGENTS.md) 和 [handoff.md](handoff.md)。
`AGENTS.md` 是本仓库的共同工作约定；`handoff.md` 是本次交接快照、验证方法和代码入口。

后续开发优先级以 [docs/development-plan.md](docs/development-plan.md) 的最新章节为准；
产品决定在 `docs/design/`，已发布协议在 `docs/specs/`。不要把设计目标当作已实现功能。

按所有者要求直接在 `main` 开发、提交与推送，不自动创建分支/PR或整合无关历史分支。
每个关键交付节点做 critical review，保护已有改动，记录实际测试结果与尚未解决的问题。
持续更新交接文档，避免在此文件复制另一份路线图。
