# Repository workflow

- Default to developing, committing and pushing directly on `main`, as requested by the owner.
- Do not create a feature branch or PR for routine changes unless the owner asks for one or a
  repository protection rule requires it.
- The owner has explicitly requested separate worktrees for Codex and Claude. Root keeps `main`;
  Claude uses a task branch in its own worktree, as specified below. This is the authorized
  exception to the default branch workflow, and does not require a PR.
- Existing unrelated open PRs are not implicitly approved for integration by this workflow choice.

# Development direction

- Read `docs/development-plan.md` for the current roadmap and delivery status.
- Product decisions live in `docs/design/project-workbench.md`; the proposed SQLite project model
  and evaluation rules live in `docs/design/project-model.md`.
- Distinguish planned capabilities from implemented features. Published contracts in `docs/specs/`
  remain authoritative until explicitly versioned or extended.
- See `docs/repository-structure.md` for active module boundaries and `archive/manifest.json` for
  archived paths. Do not import archived code or include it in builds, packages or test discovery.
- Reducing navigation clicks is a core UI acceptance metric. For UI deliveries, record the fixed
  starting layout, actual click count and resulting state in `docs/runtime-validation.md`; see
  `docs/desktop-modules.md`. Keep explicit run/save/send actions and protect Viewer state and drafts.

# Handoff

- For known text and file locations, use scoped `rg` and bounded reads. Use Serena for symbol
  definitions and references when semantic navigation helps; keep its responses bounded.
  Setup, measured costs and on-demand jscpd/Knip commands are in `docs/ai-development.md`.
  Do not load full scan reports or create a second whole-repository memory by default.

- Read `handoff.md` before starting: it is the current handoff snapshot (state, pending owner decisions, how to build and
  test, code entry points). Check the real Git state and CI before trusting it, and update it when the state changes.
- Keep `handoff.md`, `docs/development-plan.md`, `docs/development-log.md` and `docs/runtime-validation.md` current at each
  delivery, with the actual commit, test and CI results and the remaining limits. Critically review each delivery, fix
  real problems and protect existing uncommitted changes.

# Rules that every agent must keep

- Never read, print or store secrets. The product's AI key is the environment variable `STK_TOKEN_PLAN_API_KEY`; do not put
  credentials in logs, projects, fixtures or commits. Test placeholders must be low-entropy (e.g. `abcdefghijklmnopqrstu`).
- Run tests with `STK_TOKEN_PLAN_API_KEY=` empty and `STK_TOKEN_PLAN_MODEL` unset. Refresh, reopen and tests must never make a
  charged model request. Do not change the product model endpoint.
- Changing model endpoints, keys or the network policy is desktop-only (never from scripts or the agent). Private project
  data never goes to an external model endpoint.
- In public repository documents, refer to the partner research group as "合作方", not by name.
- Push code only after the desktop CI of the previous code head has finished; record CI results in
  `docs/runtime-validation.md`. Run a secret scan (gitleaks with `.gitleaks.toml`) on staged changes before committing.
- Pending owner decisions are listed in `handoff.md`; do not build on an option the owner has not chosen.

# Agent roles and worktrees (latest owner decision 2026-11-07)

Codex is Root and owns overall delivery. Codex and Claude work in separate worktrees; this replaces
the earlier shared-worktree, design-only arrangement. The working agreement and ready task are in
[docs/planning/agent-collaboration.md](docs/planning/agent-collaboration.md).

- **Root:** `/home/mnemora/xcheng/sijin/stk`, `main`. Owns task ordering, module boundaries,
  shared contracts, review, integration, final regression/builds, pushes and CI follow-up. Root
  maintains the four state docs, repository-wide instructions and the main worktree's AOCI assets.
- **Persistent work:** the owner has asked Root to continue development, assign Claude work and
  periodically merge relevant PRs. Review and validate each PR against the current plan and exact
  head before merging; unrelated PRs remain outside this authorization. Keep undecided options
  pending and continue independent work while the owner is away.
- **Claude:** `/home/mnemora/xcheng/sijin/stk-claude`, `claude/support`. Owns assigned documentation
  and specifically assigned modules, including their relevant tests. A task must name its base
  commit, write scope, dependencies, acceptance and handoff evidence. Being the Web or backend
  directory does not by itself assign ownership to either agent.
- **Isolation:** do not edit or stage another agent's worktree. Use separate build/output directories;
  `/home/mnemora/opt/stk-build/merge-check` remains Root's. Do not copy local credentials or private
  assets to a worktree. AOCI reads/maintenance must bind to the actual worktree root, never silently
  reuse a main-bound MCP service for Claude's tree.
- **Delivery:** Claude commits only the assigned files on its branch and hands Root the exact commit,
  checks, evidence and remaining limits. Root reviews and integrates selected commits into `main`,
  resolves conflicts, validates deliveries, maintains AOCI at milestones, and alone pushes. Do not merge
  whole historical branches or copy another worktree's AOCI baselines as integration.
- **Protect WIP:** inspect the staged diff before every commit. Stage only owned changes, using hunks
  when a file contains pre-existing WIP; avoid `git add .`, destructive cleanup and unintended commits.
- **Decisions:** the owner selected MuPRO/MuFerro as the executor pilot, plugin-defined native
  formats (HDF5 for MuPRO), and development of S2c prepare/run permission extensions. Implementation
  and published-contract changes still need verification; see `docs/design/mupro-executor-pilot.md`.
  Remaining owner decisions and PET new-work deferral stay in force. Claude may investigate and propose; task
  assignment does not authorize changing endpoints, credentials, network policy or execution powers.

<!-- aoci:begin -->
## AOCI 使用约定

- AOCI 按需使用。新会话或上下文压缩后，先读本文件、交接和任务相关的源码及发布契约。遇到不熟悉的模块或跨模块关系时，可以查询相关条目或范围。需要系统全貌时再启动完整 Overview。
- 认知和收据绑定实际 worktree、索引、服务与交付范围。局部查询、交接摘要和失效收据只辅助定位。引用索引时保留工具报告的覆盖与新鲜度，结论以当前源码、契约和实际验证为准。
- 主动启动正式交付时，先读取当前 `aoci_rules`，按实时协议消费已请求范围。原样跟随分块游标到完成，确认交付并按当前 Challenge 提交一次 Attestation。缺块、截断、漂移或 Recovery 停点按工具返回处理。压缩后若选择重新建立完整认知，声明实际 `context_compaction`，仅凭新交付正文验证。
- root 在开发计划中标明的功能阶段集成完成、发布前，或有待维护变化累计一周时，选择稳定状态批量维护。日常提交和交接之间的 Dirty/Stale 可以继续做基于源码的开发和交付，索引使用时须注明状态。只读任务无需维护。
- 维护、初始化和恢复遵循实时 Guide。保留完整机器候选批次、来源摘要和 CAS，模型根据绑定证据写 F/R/A/S。遵守 Recovery、第三方冲突、审批、零写入和凭据边界。Claude 使用自身 worktree 的绑定，由 root 维护 main 的正式索引。
- 日常治理证据留在 AOCI Ledger 与回执。四份状态文档记录开发、测试和 CI，里程碑可简记维护完成。未决写入、恢复或冲突须记录安全续接所需的身份和证据位置。
- 事务保留按受支持的生命周期流程评估，同时核对恢复、审计和未决引用。现有事务保留至有可验证的处理方式。

执行细节见实时工具合同和 [AI 开发工具](docs/ai-development.md)。

<!-- aoci:end -->
