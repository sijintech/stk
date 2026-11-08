# Claude 开发入口

开始工作前读取 [AGENTS.md](AGENTS.md) 和 [handoff.md](handoff.md)。
`AGENTS.md` 是本仓库的共同工作约定；`handoff.md` 是本次交接快照、验证方法和代码入口。

后续开发优先级以 [docs/development-plan.md](docs/development-plan.md) 的最新章节为准；
产品决定在 `docs/design/`，已发布协议在 `docs/specs/`。不要把设计目标当作已实现功能。

按所有者最新决定，Codex 为 root 总负责；Claude 在独立 worktree
`/home/mnemora/xcheng/sijin/stk-claude` 的 `claude/support` 分支承担文档和明确分配的模块开发。
任务边界与交付方式见 [协作约定](docs/planning/agent-collaboration.md)。
Claude 只提交本任务文件，由 root 审查、集成到 `main` 并统一推送；不直接改 root 工作树或接管其他模块。
每个关键交付节点做 critical review，保护已有改动，记录实际测试结果与尚未解决的问题。
向 root 交付精确提交、验证证据与剩余问题；四份全局状态文档由 root 统一维护。
