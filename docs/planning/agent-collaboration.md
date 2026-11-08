# Codex / Claude worktree 协作约定

所有者最新决定：Codex 作为 root 总负责，Claude 在独立 worktree 配合文档和特定模块开发。
本约定替代此前共用 main 工作树、Claude 仅做设计的安排；不改变已发布协议或三项待决。

## 工作区和职责

| 角色 | 工作区 / 分支 | 负责的结果 |
|---|---|---|
| Codex / root | `/home/mnemora/xcheng/sijin/stk` / `main` | 任务拆分、模块及契约边界、跨仓协调、代码审查、集成、最终回归与构建、AOCI、提交推送和 CI |
| Claude | `/home/mnemora/xcheng/sijin/stk-claude` / `claude/support` | root 分配的文档和模块实现、相关测试、独立审阅与交接证据；每次只推进明确的任务范围 |

root 统一维护 `AGENTS.md`、`CLAUDE.md`、本协作约定和四份状态文档：`handoff.md`、
`docs/development-plan.md`、`docs/development-log.md`、`docs/runtime-validation.md`。
Claude 的角色不限于网页，也不限于设计；具体后端、原生或前端模块由任务卡指定。
独立审阅任务须报告问题与证据，是否同时授权修复由该任务卡说明。

worktree 隔离工作文件和索引，但共享 Git 对象与 refs。双方仅在自己的分支提交；只有 root 集成或推进 main、推送和处理 CI。
root 不自动整合无关旧分支或 PR。Claude 提交后交付精确 commit，root 审查通过再选择性 cherry-pick；冲突在集成时显式处理。
新契约先协调兼容规则，不能让两个模块分别创造相同业务状态机。

所有者已要求持续推进开发、合理给 Claude 安排任务并定期合并相关 PR。root 在所有者离开期间按已授权范围持续工作，
审查 PR 的实际 diff、依赖、当前 head 和 CI，满足仓库门禁后集成；未相关 PR 不因本授权自动纳入。
默认 main 交付继续适用，Claude 使用独立分支；需要 PR 时由 root 统一推送分支并建立/合并。
待决问题记录候选与影响后继续独立工作，不把未回复当作采用方案。

## 任务交接规则

root 发出的每个任务都填写：

- 任务 ID、目标、基线 commit、明确的写入路径和负责模块。
- 输入/依赖、需要遵守的现有契约、与 root 当前改动的边界。
- 可运行的验收方式、证据目录和未具备的真实平台/资产。
- 交付物、独立检查要求、待所有者决定项和禁止代选的范围。

Claude 开始前核对实际分支和 Git 状态。若所需修改越过任务边界，先向 root 报告具体依赖；在已分配范围继续可独立完成的工作。
未确认的方案保持候选，不因为编写文档或 stub 就宣布已经实施。
每次交付附完整 SHA、改动路径、实际检查结果、失败/未验证项及证据引用。root 按同一基线审阅，不能借旧绿灯覆盖新字节。

Claude 不修改 root 的状态文档；任务结果先在交付说明中记录，由 root 整合。
双方检查 staged diff，仅暂存自己的路径/增量。含既有 WIP 的文件按 hunk 暂存，禁止把旧未提交内容连带提交。
同步分支前确认工作树干净；不通过 reset、clean、强制 checkout 或删除 worktree 丢弃其他人的工作。

## 构建、状态和认知隔离

root 独占 `/home/mnemora/opt/stk-build/merge-check`。Claude 如任务需要原生构建，使用
`/home/mnemora/opt/stk-build/claude/<task-id>`，结果和测试临时目录也按任务隔离；不共用会写入的编译缓存、安装前缀或测试数据库。
安装依赖使用独立环境，不改 root 的环境，不启动未经任务授权的真实计算或收费模型请求。

Git 仅带入已提交文件，root 现有未提交 WIP 留在 root。不要复制用户凭据、本机私有状态、身份或模型资产。
测试使用 `env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY=`；所有既有隐私、显式执行和目标平台验收要求保持。

AOCI 的认知身份包含仓库根；Claude 不把 root-bound MCP 的回执当作自身 worktree 的认知。
在自己的工作区按当前合同建立认知；若工具仍绑定 main，报告绑定差异，使用对应工作区的受支持入口，不改写 root 的运行资产。
两边各自保持认知约束，正式合入 main 后由 root 在最终稳定状态维护 main 索引；不直接拷贝/合并 Claude 的 `.aoci` baseline。

## 当前任务卡

### CL-D1-01：D1 实施前的最小契约与兼容门清单

- **状态：ready，供 Claude 接单；尚未开始或验收。**
- **基线：** 创建本 worktree 时继承的协作规则提交；接单时在交付说明记录实际完整 SHA。
- **目标：** 将现有三份统一后端设计转为 root 可实施的 D1 清单，逐项区分已发布、拟议新增、当前缺口和依赖决定。
- **唯一写入范围：** 新文件 `docs/planning/d1-compatibility-gates.md`。只读核对相关实现、测试和规格。
- **输入：** [共享架构](../design/shared-backend-architecture.md)、[任务与数据设计](../design/distributed-task-data-protocol.md)、
  [场景验收](../design/distributed-workbench-acceptance.md)、[发布规格](../specs/README.md)、[路线图](platform-roadmap.md)。
- **必须交付：** 最小无 GUI 装配切片；本地/云部署的同语义合同矩阵；旧 CLI/Bridge/Runtime 兼容门；
  原操作回执、当前授权、取消/观察/重开和唯一写入的反例；源码与测试入口、未具备资产及逐项退出证据。
- **边界：** 不发布新 schema，不改产品代码或数据库格式，不替所有者选择 D3 领域、三待决或 PET 新专项；
  不把历史 Synthrix `90d7c4a` 接缝当当前正常启动可达，不推送、不启动主机服务/模型/科研任务。
- **验收：** 文档相对链接/章节锚点和 diff 空白检查；条目均指向精确来源或标明 proposal/unknown，实际未跑检查写未运行；
  提交前暂存 gitleaks 按 `.gitleaks.toml` 零发现，交付完整 commit 与 root 审阅问题清单。

root 当前先核对 `6f4de650` 的整个 Desktop CI 与既有记录/AOCI 债务，再完成原生文献编辑器与实际点击验收、
核实 Synthrix 当前正常启动装配及桌面入口，随后依据 CL-D1-01 进入 D1。顺序可由 root 按真实依赖调整并记录。
后续模块任务在 root 明确路径和验收后交 Claude，不因本任务卡自动获得其他模块写入权。
