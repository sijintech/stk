# 原生会话内的任务与文件引用

2026-11-13 起草，基线 STK `2390a099`。上位设计见统一研究工作台与跨端验收矩阵 H5。桌面首片已实现智能体运行卡片的只读详情。 [统一研究工作台](unified-workbench.md) [统一首页跨端验收矩阵](unified-home-acceptance.md#h5-会话内的任务与文件详情条件)

第二节的「现有」指基线源码已有的字段、方法或界面。

## 1. 结论

- 第一片放在智能体会话的 MuPRO / MuFerro 运行卡片上。卡片已有决定或回执时，点一次「关联任务」打开详情并只读一次 `project.workflow_runs.get`。详情显示运行状态、任务状态、冻结快照和产物名称。关闭后返回原卡片入口。
- 已保存的项目问答没有公开的任务或文件引用字段，不作为首片入口。正文里出现的编号不算引用。
- 不新增权限、数据库表、项目格式、Bridge 方法或已发布契约字段，也不连接 Hub 或 Runtime。

## 2. 本地持久来源

下表按存储位置列出每类来源能否作为会话内引用。所在模块均为 `suan/project/`，原生读取均经本机 Bridge 的项目句柄。

| 来源 | 持久位置 | 引用字段 | 冻结或实时 | 可作会话引用 |
| --- | --- | --- | --- | --- |
| 问答上下文 | `project_contexts`（contexts.py） | `selection` 的表、记录与字段 ID，`source_revision`，内容 `sha256` | 冻结。读取时校验摘要 | 现有。已在问答「来源」中显示，只含表格单元格，不含任务或文件 |
| 问答消息 | `project_messages`（discussion.py） | 固定六个字段 `id, project_id, context_id, role, text, created_at`，多一个字段即判为损坏 | 冻结 | 否。没有任务或文件字段 |
| 问答请求 | `project_requests`（requests.py） | 公开字段只有上下文、消息、助手消息、配置、提示版本和状态 | 身份冻结，状态追加 | 否。见下一行 |
| 报告请求的选择 | 同上，`stk.report-draft/1` 的 `report_selection` 与 `report_input` | 来源种类 `context`、`simulation_run`、`analysis_run`、`workflow_run`，`snapshot_id`，资产 `record_id` | 冻结 | 不可用。这两个字段属私有，`Requests._public` 不返回，`project.requests.get` 读不到。公开它们须改契约 |
| 问答提议 | `project_proposals`（discussion.py） | 消息到草稿的链接 | 冻结 | 现有。已用于打开审阅，不含任务或文件 |
| 智能体事件 | `project_agent_events`（agent_sessions.py），哈希链 | `tool_result.objects` 只登记 context、message、request、draft，`tool_result.sources` 为 `{kind, id, label}`，种类有 `table`、`table_structure`、`workflow_run` | 追加，链式校验 | 部分。`workflow_run` 来源只出现在准备运行的工具结果中 |
| 智能体工具结果正文 | 同上，`tool_result.content` | 模型可见的 JSON 文本，可能截断 | 冻结 | 否。`find_runs` 等结果中的运行 ID 只是文本，不作授权依据 |
| 运行批准卡片 | `agentSessionView.run_approvals`，由事件链计算（agent/run_approvals.py） | `item_id, run_id, plan_sha256, request_sha256, expected_revision, source_event_id, source_turn, source_call_id`，回执含 `outcome` 与 `run_status` | 条目冻结，回执追加 | 是。服务按原工具调用、计划和请求摘要校验每张卡片 |
| 工作流运行 | `workflow_run_plans` 与 `workflow_run_events`（workflow_runs.py） | 计划含行号、步骤顺序与冻结参数。任务为 `{step, row, attempt, status, produced, error, updated_at, progress}` | 计划冻结，任务状态由追加日志实时计算 | 是，经卡片的 `run_id` |
| 任务进度 | 运行事件的 `progress` | `stage`、`simulation_run_id`、`task_id`、`state`、`adopted_from` | 记录下来的远端观察 | 是。`task_id` 为 Runtime 任务 ID |
| 任务产物 | 运行事件的 `produced` | 收集的仿真为 `{directory, snapshot_id, files}`，文件步骤为 `{snapshot_id, files}`，分析步骤为 `{analysis_run_id, snapshot_id}`。`files` 把输出名映射到文件索引记录 ID | 写入时冻结 | 是 |
| 单次仿真运行 | `run_plans` 与 `run_observations`（runs.py） | 冻结计划含连接、节点、端点指纹、`input_snapshot_id`，最新观察含 `task.id` 与 `task.state` | 计划冻结，观察追加 | 首片不读。`project.runs.get` 返回端点指纹等配置 |
| 文件索引 | 项目文件表（files.py，`urn:stk:project:files:1`） | 名称、相对路径、位置、种类、大小、修改时间、状态、检查时间 | 实时元数据 | 首片只显示输出名。`resolve` 需要 `expected_revision` 并返回绝对路径，`refresh` 是带修订的写入 |
| 输入或结果快照 | `project_snapshots` 与内容寻址副本（snapshots.py） | 清单记录 ID、`sha256`、大小 | 冻结 | 首片只显示快照 ID 前缀与文件数。`verify` 读取全部字节，`resolve` 校验字节并返回绝对路径 |
| 任务页 | Runtime 或 Hub 的实时任务列表（JobsState） | 运行环境中的任务 | 实时，不在项目里持久保存 | 否。会话详情显示的是项目记录的最后观察，不是任务页 |

## 3. 冻结与实时的区分

- 问答上下文、问答消息、运行计划、运行批准条目和快照清单在写入后不变，读取时校验摘要。界面可标为「冻结」。
- 运行与任务状态、任务进度和文件索引元数据会变化。详情显示读取那一刻的状态，标为「读取时状态」，不自动刷新，也不当作 Runtime 实时状态。
- 产物中的 `snapshot_id` 指冻结副本，`files` 中的记录 ID 指可能已改动或删除的项目文件。详情分两行显示，前者写「冻结快照」，后者写「项目文件」。
- 智能体事件是追加的哈希链。打开或收起详情不追加事件，`chain_sha256` 保持不变。

## 4. 第一片实现

### 4.1 正常入口（现有）

| 端与窗口 | 到达会话的操作 | 次数 |
| --- | --- | --- |
| 宽窗聚焦工作台 | 左栏「智能体会话」中的条目 `workbench_agent_session/<session_id>` | 1 |
| 窄窗聚焦工作台 | 「历史」菜单 `workbench_history`，再选会话条目 | 2 |
| 首页待办 | 带 `session_id` 的待办项，经 AI 编辑器的 `navigate` | 1 |
| 已打开的 AI 编辑器 | 会话下拉 `ai_agent_session` | 1 |

左栏最多列 5 个会话（`shell.cc` 的 `max_recent_sessions`）。会话视图中的运行卡片由 `ProjectAgent::run_cards()` 组装，服务最多返回 20 张，待决定的在前，随后是最近已消费的。更早的卡片要等后续分页设计，首片不处理。

### 4.2 关联任务入口

位置在 `desktop/engine/lib/stk_app/src/editors/ai_editor.cc` 的 `agent_run_cards`，紧接「查看原决定的回执」按钮。

- 控件键 `ai_agent_run_detail/<item_id>`。控件文字为「关联任务」。打开后按 Tab 可聚焦关闭按钮。
- 只在卡片已消费时出现，即 `decision` 或 `receipt` 为对象。待决定卡片不显示，避免与「读取完整计划」混淆。批准仍只由完整计划解锁。
- 显示条件还包括 `ProjectAgent::runs_supported()` 为真，以及 Bridge 握手中有 `project.workflow_runs.get`。项目格式 13 已满足该方法所需的格式 10。
- 新增中英文文案键放在 `desktop/app/i18n/en.json` 与 `zh_CN.json` 的 `ai.agent.run.detail*` 下。

### 4.3 读取

在 `ProjectAgent` 增加以下接口。

```cpp
uint64_t read_run_detail(const io::Json &item);
const io::Json *run_detail(uint64_t ticket, const io::Json &item) const;
void close_run_detail(uint64_t ticket);
```

- 只发 `project.workflow_runs.get {handle, run_id}`，`run_id` 取自卡片条目。重试策略为 `Retry::Never`，超时 15 秒。
- 回复时核对 `alive_`、`epoch_`、项目句柄、项目作用域、会话选择和当前卡片。失败只写入该次详情的条目。项目切换发出后即丢弃旧详情，切换期间入口禁用。
- 每次打开分配独立票据。结果只保留在 `run_details_` 的内存中，关闭时清除对应票据。`reset()` 与 `select()` 时和 `run_plans_` 一起清除。
- 回复须满足 `run.id` 等于条目的 `run_id`，`tasks` 为数组。`run.plan_sha256` 与条目的 `plan_sha256` 不同时，只保留不一致标记，不显示任务。
- 只保留有限投影，不保留完整计划。投影包括运行 `status`、`counts`、`complete`、是否有 `stop_error`，以及前 200 个任务的 `step`、行号（由计划 `rows` 的 `number` 换算）、`attempt`、`status`、`progress` 的 `stage`、`state`、`task_id` 前缀，还有 `produced` 的 `snapshot_id` 前缀、`files` 的输出名、相对 `directory` 和 `analysis_run_id` 前缀。超过 200 个时显示剩余数量。
- 不使用工作流编辑器自己的 `ProjectWorkflows` 实例，也不调用其 `load_run`，以免改动工作流页已选的运行和编译证据。
- 不调用 `project.agent.run_plan`，它会登记计划检查并解锁批准。不调用 `project.agent.run_observe`，它可能追加回执事件。也不调用 `project.runs.refresh`、`project.files.resolve`、`project.files.refresh`、`project.snapshots.verify` 或 `project.snapshots.resolve`。

### 4.4 显示

详情通过统一的「关联任务」入口打开。宽窗用右侧面板，宽度为 700 逻辑像素及以下时用底部覆盖层。面板绑定发起卡片和窗口，关闭时焦点回到该卡片入口。

- 第一行为运行状态，沿用现有 `workflow.run.status.<status>` 文案，后接各状态任务数与「读取时状态」。
- 每个任务一行，写行号、步骤、第几次尝试、状态和 Runtime 任务 ID 前 8 位。没有进度时不写任务 ID。
- 有产物的任务另起一行。「冻结快照」后写快照 ID 前 8 位与文件数，「项目文件」后列输出名，有 `directory` 时写项目内相对目录。
- 不显示绝对路径、连接端点指纹、资源选项、执行者 ID 或运行所有者的主机与进程号。
- 进入任务页、查看器或文件页需要另外的明确操作，首片不提供这些跳转。

### 4.5 失效与错误

| 情形 | 发现方 | 结果 | 请求数 |
| --- | --- | --- | --- |
| 项目重新打开或切换，句柄或作用域变化 | 客户端 | 丢弃详情，按钮按新卡片重画 | 0 |
| 会话重新选择，`selection_epoch()` 变化 | 客户端 | 丢弃详情与迟到回复 | 0 |
| Bridge 替换 | 客户端 | 同上 | 0 |
| 卡片已不在 `run_cards()` 中 | 客户端 | 不显示按钮与详情 | 0 |
| 旧 Bridge 缺少运行方法 | 客户端 | 不显示卡片与按钮 | 0 |
| 运行不存在或计划摘要损坏 | 服务 | 卡片内显示「无法读取这次运行」，留在原会话 | 1 |
| 计划摘要与批准条目不一致 | 客户端核对服务回复 | 显示不一致，不列任务 | 1 |

不会改为打开其他运行、最新运行或运行列表。`project.workflow_runs.get` 不拒绝已归档的运行，首片无法显示归档状态，见第 6 节。

### 4.6 隐私

- 工作流运行的来源元数据属本地或机构内私有数据（[MuPRO 首次启动扩展](../specs/agent-muferro-run-1.md)）。详情只在本机界面显示。
- 详情不写入模型输入、智能体消息、问答上下文、草稿、提示、日志、布局 JSON 或 `save_workspace_state()`，也不发往 Hub 或 Web。
- 所需读取已在 Bridge v1 发布，使用原有项目句柄，不扩展 S2c 权限，不改变模型端点、凭据或网络策略。

### 4.7 兼容

- 不改数据库、项目格式或 Bridge 契约。旧的冻结会话按原方式计算卡片，没有卡片的会话不受影响。
- `NativeAgentRunsLegacy` 覆盖的旧 Bridge 继续隐藏运行控件。
- 原有「读取完整计划」「批准」「拒绝」「查看原决定的回执」的行为与次数不变。
- Root 的 Hub 会话关联与本片互不依赖。原生端不读取 Hub 会话，按双端统一工作台的布局验收。

## 5. 验收

### 5.1 固定起点

自动化使用桌面界面驱动、Bridge 替身和合成项目。宽窗英文 1600×1100，窄窗中文 680×1000，缩放均为 1。从已打开本地项目且 Bridge 就绪的聚焦工作台起步。界面驱动检查问答与智能体草稿、原会话焦点和 Viewer 状态。真实 Linux X11 窗口留待验证。

### 5.2 操作与次数

| 行 | 操作 | 次数 | 结果与焦点 |
| --- | --- | --- | --- |
| 宽窗打开 | 左栏会话 A，再点「关联任务」 | 2 | 显示所选卡片的详情，首个 Tab 聚焦关闭按钮 |
| 宽窗收起 | 「关闭」或 Esc | 1 | 焦点返回原卡片入口，会话阅读位置不变 |
| 窄窗打开 | 「历史」，会话 A，「关联任务」 | 3 | 同宽窗，历史菜单关闭后查看器不接收输入 |
| 窄窗收起 | 「关闭」或 Esc | 1 | 同宽窗 |
| 键盘 | 焦点在该控件时 Enter 打开，Esc 关闭 | 各 1 | Esc 后焦点返回原入口 |
| 待决定卡片 | 无操作 | 0 | 没有「关联任务」，「批准」的启用状态与基线一致 |
| 失效 | 先打开详情，再切到会话 B 并回到 A | 2 | 详情已丢弃，回到 A 不自动重读 |
| 读取失败 | 运行不存在时点「关联任务」 | 1 | 卡片内显示不可用，留在会话 A |

### 5.3 零副作用读数

每行结束时以下读数为零或不变。

| 读数 | 期望 |
| --- | --- |
| 运行详情读取 | 每次打开 `workflow_runs.get` 恰好 1 次，收起 0 次 |
| 智能体动作 | `run_plan`、`run_decide`、`run_observe`、`run_target`、`create`、`say`、`start` 均为 0 |
| 会话记录 | `agent().view()` 的 `chain_sha256` 与 `total` 不变，`selected()` 不变 |
| 项目写入 | `project()->revision` 不变 |
| 问答 | `discussion().exchange_id()` 不变，问答草稿不变 |
| 工作流页 | 不新建工作流编辑器。已打开时其 `ProjectWorkflows` 实例的 `run()` 不变 |
| 画面 | `f.screen.arrangement()`、查看器 `save_workspace_state()` 与 `camera_serial()` 不变 |
| 持久化 | AI 编辑器 `save_workspace_state()` 中没有 `run_id`、`tasks` 或 `snapshot_id` |
| 智能体草稿 | `ai_agent_text/<handle>` 的文字不变 |

### 5.4 测试位置

- 放在 `desktop/tests/app/project_agent_runs_test.cc`，扩展现有 `kRunWire` 替身。替身登记 `project.workflow_runs.get` 并写入 `calls.jsonl`，参数校验绕过范围与 `project.agent.*` 相同。
- 新增标记文件 `consumed`、`run_missing` 和 `run_mismatch`。`consumed` 让第一张卡片带决定与回执并另加一张待决定卡片，`run_missing` 返回 `not_found`，`run_mismatch` 返回不同的 `plan_sha256`。回复的任务中含 `progress.task_id`、`produced.snapshot_id`、`produced.files` 和超长 Unicode 输出名。
- 入口用 `f.shell->open_workbench(f.screen)` 和左栏条目 `workbench_agent_session/session-a`，不用 `open_ui()` 中的 `set_maximized` 和意图下拉。替身的 `list` 只返回已读过的会话，须预先建立 `session-a` 与 `session-b`。窄窗 680×1000 另建中文夹具，语言参数沿用壳层选项的 `zh_CN`。
- 构建 `stk-project-tests`，用 CTest `-R NativeAgentRun` 运行。在本工作树自己的构建目录编译，`STK_TOKEN_PLAN_API_KEY` 置空，`STK_TOKEN_PLAN_MODEL` 不设置。
- 实窗只用合成项目，次数与结果由 Root 记入 `docs/runtime-validation.md`。

## 6. 限制与交给 Root 的事项

- 首片只覆盖运行卡片上的工作流运行。会话左栏的 5 个、卡片的 20 张和事件视图的 1000 条上限之外的引用暂不可达。
- `project.workflow_runs.get` 返回完整冻结计划，大小可达 16 MiB。首片在客户端只保留投影，传输量未减少。若要轻量读取，须由 Root 决定是否扩展契约。
- `project.workflow_runs.get` 不报告归档状态，也不拒绝已归档运行，详情无法显示「已归档」。
- 报告请求的 `report_selection` 已持久保存运行、快照和文件引用，但属私有字段，不经 Bridge 返回。若要在问答中显示，须先确定公开范围与契约。
- 矩阵 H5 的失效行写「零请求」。服务端才能发现的情形（运行缺失或计划损坏）需要 1 次只读请求，建议 Root 把该行拆成客户端失效与服务端拒绝两类。
- 下一片可按同一规则补文件详情。从产物的文件记录 ID 经现有文件页或查看器打开，打开前须明确点击，并保持文件页选择不变。之后再补任务页跳转，用 `task_id` 匹配任务页实时列表，并处理找不到该任务的情形。
