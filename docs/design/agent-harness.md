# 智能体 harness v1（S2 设计）

更新：2026-10-09。状态：**设计，所有者已于 2026-10-09 作答（见“所有者决定”）；均未实现。**
上位方案：[思劲平台方向](sijin-platform-2026-10.md)第 5.2 节与“七、分期与验收”S2 行；模型层前提见[模型网关](model-gateway.md)（S1a–S1d 已交付）。

文中 `文件:行` 指当前 `main` 中已有的代码与文档，用来说明复用点与缺口。凡写“新增”“改为”“将”的内容都还不存在。
新记录类型须所有者确认（[review-drafts-and-conversations.md](review-drafts-and-conversations.md):303-311 的约定）；所有者已对文末的决定作答，见“所有者决定（2026-10-09）”。

## 要做到什么

- 平台方案对 S2 的要求是：多步工具循环、副作用分级、草案审批、步骤记录，以及 MuPRO 与数据表分析技能（sijin-platform-2026-10.md:84-92）。
- 验收原文（sijin-platform-2026-10.md:154）：从一句需求到准备好一个 MuFerro 扫描草案并给出结果分析，全程可审计，未经确认不修改项目、不提交集群作业。
- v1 把验收拆成**同一会话里的两段发言**：
  1. 用户：“以第一个算例为基准，在 300–400 K 之间扫 5 个温度。”
     - 智能体：了解项目 → 捕获参数行 → 发起扫描提议 → 得到草案 → 停下，说明“请审阅并应用草案，然后运行新增的 5 行”。
     - 此时项目修订不变，Runtime 上没有任务。
  2. 人在会话的等待卡片上打开审阅并应用草案（批准留有记录），再用现有的“用工作流运行新增的 N 行”（desktop/engine/lib/stk_app/src/editors/ai_editor.cc:1073-1076）选行并点击运行。
     运行结束后，用户在同一会话说“分析结果”或点“继续”。
     - 智能体：记录观察到的应用回执与运行 → 找到这次运行 → 把结果行捕获为上下文 → 本地计算统计与拟合 → 给出分析。
- **v1 智能体不准备运行，也不开始运行。** 所有者的 P2 决定“执行始终明确。AI 从不准备或开始运行”（ai-batch-loop.md:40）仍然有效。
  平台方案的“提交运行按策略确认”（sijin-platform-2026-10.md:88）与之方向不同，要由所有者明确取舍（决定 3）。
  本文第“S2c”节给出放宽后的设计（智能体准备运行 + 桌面批准并开始），但不作为 v1 内容。

## 现状依据（已实现，只列本设计依赖的）

- **请求记录**：
  - 用途只有三种（suan/project/requests.py:18-23）；
  - `project_requests` 的 `context_id`、`message_id` 是非空外键，`assistant_message_id` 非空且唯一（suan/project/store.py:111-118）；
  - 每次读取都按 `_input` 复核上下文与消息来源（requests.py:113-133）；`_decode` 要求固定的身份键集（requests.py:35-37、146-152）；
  - 请求哈希只含 `{message_id, configuration[, prompt_version]}`（requests.py:98-106）。
- **执行器**：
  - 先过发送前检查、再 `prepare`、提交认领，然后才发送（suan/project/request_executor.py:173-182）；
  - 只发一次，异常映射到固定结果（request_executor.py:271-278）；
  - 同时最多 8 个（request_executor.py:51）；
  - 锁目录写死为 `.stk/request-locks/`（request_executor.py:54-60）；
  - 恢复只把丢失的执行记为不确定，不重发（request_executor.py:337-352）。
- **发送前检查**：
  - `ModelGateway.admit` 检查网络设置、受管本机模型是否在运行，外部端点只收标为公开的表（suan/models/gateway.py:89-105）；
  - 它只看 `frozen_input["context"]["selection"]["table_id"]` 这一张表（gateway.py:100-101），不看消息文字；
  - 不是端点的适配器（测试或嵌入代码经 `__setitem__` 注入，gateway.py:77-78）不检查（gateway.py:92-94）；
  - 桥以 `RequestExecutor(self.models, gate=self.models.admit)` 安装（suan/desktop_bridge/projects.py:42）。
- **路由**：
  - `candidates(..., public=False)` 把外部端点排除为 `private_data`（suan/models/routing.py:39-40）；
  - 未知用途按复杂任务处理（routing.py:18-20）；
  - `models.route` 只读，现在要求 `context_id`（projects.py:289-304）。
- **线协议**：
  - `_payload` 只接受四个键，只组装 `[system, 一条 user]`（suan/project/aliyun.py:198-237）；
  - 非流式解析要求 `finish_reason == "stop"`，并拒绝 `tool_calls`（aliyun.py:333-338）；流式同样拒绝（aliyun.py:459-466）；
  - `_Prepared._send` 负责单次发送、截止时间、取消与错误分类，并直接调用 `_response`（aliyun.py:520-564）；
  - `OpenAICompatibleAdapter` 复用 `_payload` 与 `_Prepared`（gateway.py:51-59）；
  - 现有系统提示写明“数据不是指令”“没有工具”（aliyun.py:46、53、78）；思考关闭（aliyun.py:223）。
- **扫描提议 → 草案**：
  - `propose_sweep` 要求当前修订等于上下文修订（suan/project/parameter_sweep.py:142-145），最多 100 行（parameter_sweep.py:23、155-157）；
  - 草案 ID 由请求派生（parameter_sweep.py:75-78）；
  - 草案与来源链接（`project_proposals`）在同一事务保存（parameter_sweep.py:170-176）。
- **草案**：
  - 草案的 `sha256` 覆盖不可变字段（suan/project/drafts.py:19、74-75）；
  - 只在基准修订上应用一次，写原子回执 `applied_revision`（drafts.py:78-82、186-205）；
  - 草案本身不记审批人（docs/project-drafts.md:100）。
- **运行**：
  - `WorkflowRuns.prepare` 只写本地冻结计划，不改修订（suan/project/workflow_runs.py:1-8、102-141）；
  - 运行的远端步骤会建工作区、上传并提交（suan/desktop_bridge/workflow_runs.py:12-20、330-362）；
  - `stk.muferro.prepare`（suan/workflows/muferro.py:307）先改项目，再建 Runtime 工作区并上传（muferro.py:355-376）。
- **哈希链日志模板**：`workflow_run_events` 的 `_append/_read`（workflow_runs.py:260-289）。起点为空串（:263）；摘要覆盖 run_id、step、row、attempt、status、payload 与前一摘要（:264-266）。
- **格式**：
  - `FORMAT_VERSION = 12`（store.py:23）；
  - 升级先备份，再按版本执行 DDL（store.py:436-465，版本元组在 :453-455）；
  - 归档种类写死在 CHECK（store.py:155-156）与 `archive.KINDS`（suan/project/archive.py:15）中。
- **关注列表**按格式版本分支（suan/project/attention.py:36-104）。
- **脚本目录**：
  - 是 122 个操作的白名单（suan/desktop_bridge/server.py:535-569）；
  - 其中已有 `project.drafts.apply`（:540）与 `project.workflow_runs.start`（:553）；
  - `script_call` 只做白名单与参数校验（server.py:583-606）。
- **契约与校验**：
  - `method_contract` 只返回 params/result，没有副作用字段（suan/desktop_bridge/schema.py:65-69）；
  - 参数校验器 `check_value` 是标准库实现的 JSON Schema 子集（suan/graph/schema.py:265）。
- **L3（结果回到对话）**只在 C++：取成功任务的 `produced.result_record_id`，找到所在表，取数值/整数字段，捕获上下文（desktop/engine/lib/stk_app/src/editors/workflow_editor.cc:1189-1221）。
  只有 MuFerro 收集会写这个字段（desktop_bridge/workflow_runs.py:429）。结果表 ID 为 `RESULT_TABLE_ID`（muferro.py:41）。
- **依赖**：`numpy` 是可选依赖（pyproject.toml:38、67-70），所以统计与拟合用纯 Python。
- **本机模型上下文**：
  - 启动参数含 `--jinja` 与 `--reasoning off`；`-c` 取目录项的 `serve_context`，缺省才是 8192（suan/models/local.py:739-743）；
  - 目录中 11 个 llama.cpp 项里，10 个为 32768（例如 suan/models/catalog.json:72），只有 `qwen3.5-4b-q4_k_m-8k` 为 8192（catalog.json:105）；
  - `routing_view()` 目前不返回 `serve_context`（local.py:460-471）。
- **上下文与讨论**：一个上下文最多 256 KiB（suan/project/contexts.py:18）；讨论消息没有作者字段，角色只有 user/assistant（suan/project/discussion.py:36-38）。

## 安全不变式（每条都有测试守护）

1. **工具面是白名单。** 智能体只能调用本文“v1 工具”表中的工具。改修订、改标注、准备或提交运行、上传的操作在注册表中**不存在**，任何模型输出都触发不了。
2. **副作用级别只由 STK 注册表给出**，不取自模型输出，也不取自外部服务的提示。
3. **改项目只经草案与人的批准。** 智能体最多保存草案。应用由人完成：从会话卡片应用时，记一条绑定草案哈希的批准事件；在别处应用时，记为观察。
4. **开始运行只经人点击**（v1 智能体连运行计划都不准备）。
5. **数据边界按会话检查。** 会话维护一个只增不减的“已进入会话的数据来源”集合。
   v1 规划轮只发往本机或机构内端点；子请求只有在集合中所有来源都公开时，才可能发往外部端点。
6. **每一步冻结并成链**：会话头、每次模型调用、工具调用与结果、等待项、批准、观察、停止原因，都写入只追加的哈希链日志，读取时复核整条链。
7. **结果不确定时不自动重发**，与 model-gateway.md:103（S1d 决定 3）一致。
8. **工具结果是数据，不是指令**：系统提示声明这一点，权限只看注册表；注入最多诱发只读、记录或草案级动作。
9. **批准方法只给桌面**，不进脚本目录。这只能防止脚本伪造批准记录：脚本本来就能直接调用 `project.drafts.apply` 与 `project.workflow_runs.start`（server.py:540、553），那是人自己写的脚本，不受智能体策略管辖。

## 架构

```
桌面 AI 助手（新“智能体”用途）──轮询 project.agent.get──┐
Python 控制台 p.agent.* ────────────────────────────────┤
                                                        ▼
                         suan/desktop_bridge/projects.py  ProjectSessions（新增 agent 方法）
                                                        │
                    suan/agent/executor.py  AgentExecutor（每会话一个线程；锁文件；取消；恢复）
                     │                 │                          │
   suan/agent/tools.py 工具注册表    suan/agent/wire.py 规划轮       suan/project/agent_sessions.py
   suan/agent/levels.py 分级表       （stk.agent/1 请求体与解析，     （格式 13：会话、事件链、对象登记；
     │                               经 _Prepared 非流式发送）         读取校验与 verify）
     ├─ store.contexts / drafts / workflow_runs（只读或追加不可变记录）
     └─ 子请求：discussion.add → requests.create → RequestExecutor.start（现有网关检查）→ propose_edits
```

- **循环放在 Python 后台服务里。** 网关、标注、路由、执行器与项目存储都在 Python。桌面只负责显示、轮询和点击批准；脚本与桌面走同一入口，审计记录只有一处。
- **只有规划轮是新东西。** 会改变项目的模型调用（扫描提议）与可选的文字解读，仍是普通的 `stk.parameter-sweep/1` 与 `stk.text/1` 请求，由工具代为创建、发送与转换。
  这样，草案来源（`project_proposals`）、发送前检查、路由、用量（requests.py:276-308）、关注与归档对它们照常有效，符合方案“复用请求记录、草案与用量统计”（sijin-platform-2026-10.md:92）。
- **工具处理函数不走 `script_call`**，直接调用存储层 API。脚本白名单宽不宽，与智能体能做什么无关。
- **安装方式**：`AgentExecutor` 与 `RequestExecutor` 并列挂在 `ProjectSessions` 上（projects.py:42），共用同一个 `ModelGateway`。
  子请求经同一个 `RequestExecutor`，因此仍受 8 个活动请求的上限约束。
- **并发**：每个项目同时最多 1 个运行中的会话，后台服务合计最多 2 个；会话内同一时间只执行一个模型调用或一个工具。

新模块：

| 文件 | 内容 |
|---|---|
| `suan/project/agent_sessions.py` | `AgentSessions`：create/say/get/list、`_append/_read`、状态推导、对象登记、`verify`；`ProjectStore.agent_sessions` 属性（挂法同 store.py:345-347） |
| `suan/agent/levels.py` | 分级表（数据）：脚本目录全部操作的级别、是否给智能体、不给的理由 |
| `suan/agent/tools.py` | 工具注册表与 8 个工具 |
| `suan/agent/wire.py` | `stk.agent/1` 系统提示与技能说明、对话重组、请求体、回复解析、`ModelTurn` |
| `suan/agent/executor.py` | `AgentExecutor`：循环、认领、结算、锁、取消、恢复、回退 |
| `suan/agent/stats.py` | 纯 Python 统计与最小二乘拟合 |

## 持久化：格式 13（只加表）

### 为什么不复用 `project_requests`

- 规划轮要带多轮历史与工具定义，回复可能只有工具调用、没有文字。
- 若作为新用途放进 `project_requests`：
  - 行没有上下文与用户消息，违反非空外键（store.py:111-118），需要重建这张表；
  - `_input` 与 `_decode` 的来源复核（requests.py:113-152）要分叉；
  - 请求哈希只含消息与配置（requests.py:98-106），同一消息上的第二轮会冲突；
  - 完成时写助手消息，而助手消息要求非空文字（discussion.py:16-20）；
  - `get/list/usage`、关注（attention.py:92-102）与归档检查（archive.py:166）也都会读到这些行。
- 把 `stk.agent/1` 加入 `SUPPORTED_PROMPT_VERSIONS`（requests.py:23），还会让普通的 `requests.create` 与 `_payload`（aliyun.py:202-205）接受它。
- 所以规划轮记在新表里，`stk.agent/1` **不**进入这个集合，也不进入桥的 `projectRequestPromptVersion` 枚举（suan/contracts/schemas/desktop-bridge-1.schema.json:10301-10307）。
- 代价：`requests.usage()` 看不到规划轮用量，由会话自己汇总（见“审计与核对”）。

### 新表（DDL 草案）

```sql
-- _DDL_V13（新增）
CREATE TABLE project_agent_sessions (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
    payload TEXT NOT NULL, request_sha256 TEXT NOT NULL, sha256 TEXT NOT NULL);
CREATE TABLE project_agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES project_agent_sessions(id),
    turn INTEGER NOT NULL CHECK(turn >= 0),
    kind TEXT NOT NULL CHECK(kind IN ('user_turn','model_claimed','model_completed','model_settled',
        'tool_called','tool_result','awaiting_user','approval_decided','approval_receipt',
        'observed','policy','cancel_requested','stopped')),
    payload TEXT NOT NULL, previous_sha256 TEXT NOT NULL, sha256 TEXT NOT NULL);
CREATE INDEX project_agent_events_by_session ON project_agent_events(session_id, id);
-- 会话创建或使用的对象：一个对象最多属于一个会话的一步
CREATE TABLE project_agent_objects (
    kind TEXT NOT NULL CHECK(kind IN ('context','message','request','draft')),
    object_id TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES project_agent_sessions(id),
    event_id INTEGER NOT NULL REFERENCES project_agent_events(id),
    PRIMARY KEY(kind, object_id));
```

- **升级**：
  - `FORMAT_VERSION = 13`，在 store.py:453-455 的元组末尾加 `(12, _DDL_V13)`，沿用“先备份再迁移”；
  - 除新表外，只重建 `project_labels`（store.py:163-170）把标注扩为 `public`、`structure`、`private` 三种（决定 8 的“结构公开”）：
    建新表、逐行复制、删旧表、改名，复制的行不变；`structure` 只用于 `table`。现有 `is_public` 只认 `public`，所以“结构公开”的表的数据仍按私有处理；
    新增 `Labels.structure_public(kind, id)`（`public` 或 `structure`）。数据页的“公开数据”勾选改为“私有 / 结构公开 / 公开”三选一；
  - 其他已有表不动。`project_archive` 的 CHECK 重建放到 S2c（决定 6）；
  - 格式 < 13 时，`project.agent.*` 返回“请先升级”。
- **与请求、草案一样**：不推进可编辑修订，不进撤销（同 workflow_runs.py:8）。
- **对象登记表**：
  - 回答“这条讨论消息、这份草案是哪个会话第几步产生的”。消息没有作者字段（discussion.py:38），没有这张表时，讨论页以外的读者分不出代问的消息；
  - 工具在创建对象的同一事务里写入登记行，主键保证一个对象只属于一步。
- **单条事件上限 64 KiB**（同 workflow_runs.py:24）。

### 事件链

- 每条事件的摘要为 `digest({session_id, turn, kind, payload, previous_sha256})`。这是本表自己的字段集，与 workflow_runs 的写法（workflow_runs.py:264-266）同理但字段不同。
- **起点取会话头的 `sha256`**，不是空串（workflow_runs.py:263 用空串）。
  - 摘要里已有 `session_id`，日志本来就不能整体挪到另一个会话下；
  - 起点绑定会话头的好处是：改动会话头的冻结内容（系统提示、工具定义、上限），会让整条链校验失败。
- `_read` 每次读取都复核会话头与整条链，断链即报错（同 workflow_runs.py:271-288）。
- **局限，如实说明**：链与数据在同一个 SQLite 文件里，只能发现意外损坏或简单篡改，挡不住有人重写整条链。
  会话结束时，桌面显示链尾摘要，并可导出 `stk.agent-log/1` JSON（会话头、事件、链校验结果）存到别处，作为外部对照。

### 会话头（创建时冻结；上限数值见决定 10）

```json
{"id", "project_id", "created_at", "harness": "stk.agent/1",
 "system": "<系统提示全文>", "system_sha256": "...",
 "skills": [{"id": "muferro-scan", "version": 1, "text": "...", "sha256": "..."},
            {"id": "table-analysis", "version": 1, "text": "...", "sha256": "..."}],
 "tools": [{"name", "version", "level", "annotations", "description", "parameters"}], "tools_sha256": "...",
 "configuration": {"adapter", "model", "max_output_tokens": 4096, "temperature"?},
 "route": {"task": "complex", "candidates": [前 5 个], "excluded": [...]},
 "policy": {"network": "<创建时的网络设置>", "planner_locations": ["local", "internal"]},
 "limits": {"model_turns_per_user_turn": 12, "consecutive_tool_errors": 3, "tokens_per_user_turn": 200000,
            "wall_seconds_per_user_turn": 1800, "transcript_bytes": 524288, "tool_result_bytes": 16384}}
```

- 系统提示、技能说明与工具定义**冻结全文**（合计约十几 KB），不只冻结摘要。这样核对与重组每一轮的输入时，不依赖当时的代码版本。
- 用户的第一句话不放在会话头里，而是第一条 `user_turn` 事件（所有发言同一形式，≤ 8 KiB）。
- `request_sha256` 是创建参数的摘要：同一 ID、同参数返回原记录；同一 ID、不同参数则冲突（与请求、运行一致）。

### 事件种类与载荷

| kind | 载荷要点 | 写入时机 |
|---|---|---|
| `user_turn` | `{turn_id, text}` | `create`/`say`；只保存意图，不发送 |
| `model_claimed` | `{call, configuration, endpoint, location, sources, input_sha256, transcript_events}` | 发送前提交（认领），与请求的认领同义 |
| `model_completed` | `{call, text?, tool_call?{id, name, arguments}, finish_reason, metadata}` | 完整回复解析成功后 |
| `model_settled` | `{call, status: failed/cancelled/uncertain, code}` | 状态与代码沿用 requests.py:28-34 的允许组合 |
| `tool_called` | `{call_id, tool, version, level, arguments, arguments_sha256, decision}` | 执行工具**之前** |
| `tool_result` | `{call_id, status: ok/error/unknown, content（≤16 KiB，模型看到的就是它）, content_sha256, truncated, objects:[{kind,id,sha256}], sources:[{kind,id,label}]}` | 工具结束后 |
| `awaiting_user` | `{text, items:[{item_id, kind:"apply_draft", draft_id, draft_sha256, base_revision}, {item_id, kind:"run_rows", table_id, rows}]}` | 一轮以文字结束，且有需要人处理的事项时 |
| `approval_decided` | `{item_id, decision: apply/discard, draft_id, draft_sha256, base_revision, by:{user, host, authenticated:false}, at}` | 人在会话卡片上作决定时，先于执行 |
| `approval_receipt` | `{item_id, ok, applied_revision?, error?}` | 执行之后 |
| `observed` | `{item_id, facts}`：草案状态与 `applied_revision`；覆盖这些行的运行 ID、状态、连接与资源选项 | 下一次发言或“继续”开始前，读取现有回执后写入 |
| `policy` | 加额度、标注变化导致的停止等策略事实 | 发生时 |
| `cancel_requested` / `stopped` | `{reason: final/cancelled/limit/budget/error/uncertain/interrupted/private_data/network, ...}` | — |

- 会话状态由事件推导（同 `workflow_runs._state` 的做法）：`ready`（有未处理的发言）、`running`、`awaiting`（有未处理的等待项）、`idle`（本轮已结束）、`stopped`。
- **确定性 ID**：工具创建的对象（上下文、讨论消息、子请求）一律用 `uuid5(会话 UUID, f"{turn}:{call_id}:{种类}")`。
  - 现有原语都按 ID 幂等：上下文捕获，讨论消息（discussion.py:68-73），请求创建（requests.py:228-233）；
  - 草案 ID 又由子请求派生（parameter_sweep.py:75-78）；
  - 因此重放同一工具调用，得到的是同一组对象。

## 工具面与副作用级别

### 级别（STK 自己的定义，写在注册表里）

| 级别 | 含义 | 折叠到平台方案的四档（sijin-platform-2026-10.md:87） | v1 |
|---|---|---|---|
| `read` | 只读项目或运行状态；进程内有界计算 | 只读 | 自动 |
| `record` | 追加不可变记录（上下文、讨论消息），不改修订 | 只读（留记录） | 自动 |
| `model` | 经网关创建并发送一次子请求 | 本机或机构内为只读；发往外部端点为访问外部网络 | 自动，受网络设置与会话来源约束 |
| `draft` | 保存草案，不应用 | 生成草案 | 自动；应用只由人 |
| `prepare_run` | 冻结运行计划，不提交 | 提交运行（前一步） | **v1 没有此类工具**（决定 3） |
| `submit_run` | 上传、提交、取消计算 | 提交运行 | 永不给智能体 |
| `project_edit` | 改项目修订、标注、归档、设置 | — | 永不给智能体 |
| `external_network` | 网页检索、文献下载 | 访问外部网络 | v1 没有（S5） |

- 每个工具同时带 MCP ToolAnnotations 的字段名（`readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`），便于以后用同一注册表生成 MCP 工具列表。STK 只信自己的 `level`。
- 界面上按平台方案的四档显示。

### 分级表与一致性测试

- `suan/agent/levels.py` 以数据形式列出脚本目录里的全部 122 个操作（server.py:535-569），每个操作给出级别，以及“作为某个工具给智能体”或 `never` 加理由。
- CI 测试检查以下几点：
  - 目录中的每个名字都已分级，表中也没有目录之外的名字；
  - 标为 `never` 的操作不出现在任何工具的实现路径里；
  - 注册表中工具的级别只在 {read, record, model, draft} 内，工具数 ≤ 12。
- 新加一个桥方法却忘了分级时，CI 失败。
- 契约本身没有副作用字段（schema.py:65-69），所以这张表靠人维护，由测试保证不遗漏。

### v1 工具（8 个）

| 工具 | 级别 | 参数 | 实现（复用） | 数据来源 | 产物 |
|---|---|---|---|---|---|
| `project_outline` | read | 无 | **新增结构读取**：各表 ID、名称、字段（ID、名称、类型、单位）、行数、标注；工作流 ID、名称、参数表、步骤种类；是否有 MuFerro 算例表与结果表。用 SQL 计数，不读单元格；不用 `store.snapshot()`，因为它读取所有表的全部数据（store.py:500-503） | 列出的每张表的结构（“公开”或“结构公开”的表算公开，决定 8） | — |
| `capture_rows` | record | `table_id, record_ids?(≤100), field_ids?(≤64)` | `store.contexts.capture`（contexts.py:157-224），`expected_revision` 取当前修订。上下文可达 256 KiB（contexts.py:18），送回模型时截断到 16 KiB 并标 `truncated`；全文留在上下文里 | 该表 | 上下文 |
| `table_statistics` | read | `context_id, fields, x_field?, fit: none/linear/quadratic` | `suan/agent/stats.py`：n、均值、标准差、最小、最大；最小二乘线性或二次拟合与 R²。只用上下文的冻结数值；纯 Python，结果确定 | 上下文的表 | — |
| `propose_sweep` | model + draft | `context_id, instruction` | `discussion.add`（代问消息）→ 选模型（复杂任务，`public` 按会话来源集合，见“数据边界”）→ `requests.create(stk.parameter-sweep/1)` → `RequestExecutor.start` → 等终态 → `requests.propose_edits`（`expected_revision` 取上下文修订）；同一项目有运行正在写入时，返回“请等运行结束” | 上下文的表 | 消息、子请求、草案 |
| `ask_about_context` | model | `context_id, question` | 同上，用途 `stk.text/1`；回答截断到 8 KiB 交给规划轮，全文留在讨论中 | 上下文的表 | 消息、子请求 |
| `draft_status` | read | `draft_id` | `store.drafts.get`：状态、基准修订、`applied_revision`、新增行 ID（`add_record` 命令） | 草案目标表 | — |
| `find_runs` | read | `draft_id` 或 `table_id + record_ids` | `store.workflow_runs.list/get`：行有交集的运行，以及它们的状态、计数、连接名、资源选项 | 参数表 | — |
| `capture_run_results` | record | `run_id` | **Python 版 L3**：按 workflow_editor.cc:1189-1221 的规则，取成功任务的 `produced.result_record_id`（≤100），找到所在表，取数值与整数字段，再 `contexts.capture`；没有结果时返回错误 | 结果表 | 上下文 |

- 不调用工具的回复：以文字结束本轮。若本轮有待处理的草案或行，执行器写 `awaiting_user`。
- 工具结果统一是有界 JSON 文本（≤16 KiB），超限时截断并标 `truncated`。
- 处理函数抛出的 `ProjectError`、`RevisionConflict`、`PolicyDenied`，作为 `status:error` 的结果交还模型（不含堆栈等内部细节）。连续 3 次错误则停止。
- 参数执行前用 `check_value`（graph/schema.py:265）对照冻结的参数 schema 校验，不合格作为错误结果交还模型。
- **修订陷阱**：扫描转换要求当前修订等于上下文修订（parameter_sweep.py:142-145），而运行登记输出会推进修订（ai-batch-loop.md:61）。
  遇到 `RevisionConflict` 时，工具返回“项目已变化，请重新捕获”，不自动改基准修订。

### 永不提供给智能体的操作（分级表中标 `never`）

- **推进修订或改设置**：
  - `project.apply/undo/redo/upgrade`；
  - `project.workflows.create/update`、`project.analyses.create/update`、`project.csv.import`、`project.files.index/refresh`；
  - `project.snapshots.capture`：推进修订（suan/project/snapshots.py:222-232）；
  - `project.runs.prepare`：推进修订（suan/project/runs.py:137-147）。
- **由人决定**：
  - `project.drafts.apply/discard`：人从会话卡片或审阅页操作；
  - `project.labels.set`：标为公开会让数据可以外发（gateway.py:100-105）；
  - `project.archive.set`。
- **计算与上传**：
  - `project.workflow_runs.prepare/start/cancel`：见 ai-batch-loop.md:40 与决定 3；
  - `project.runs.submit/cancel`、`project.analysis_runs.start`、`graph.evaluate`；
  - `task.*`、`workspace.*`、`upload.start`、`download.start`、`hub.*`；
  - `stk.muferro.prepare/import_case/clone_case`、`stk.batches.*`。
- **设置与执行**：`models.*` 与 `connections.*` 的写操作、执行 Python。

## 审批策略

| 动作 | v1 规则 | 记录 |
|---|---|---|
| read / record | 自动 | `tool_called` + `tool_result` |
| model（规划轮与子请求） | 自动，前提是网络设置允许、数据边界允许。用户发送第一句前，会看到将用的规划模型及其位置 | `model_claimed` 等；子请求另有请求记录 |
| draft（保存） | 自动 | 同上，加对象登记 |
| 应用或丢弃草案 | 只由人：从会话卡片上的“打开审阅”进入现有审阅页，点“应用”或“丢弃”时，改走 `project.agent.decide` | `approval_decided` → 执行 → `approval_receipt` |
| 在会话外应用或丢弃草案（审阅页直接调用 `project.drafts.apply`，desktop/engine/lib/stk_app/src/project_state.cc:885-905；或脚本） | 允许，这本来就是人的操作 | 下一轮开始前写 `observed`，不算签名的批准 |
| 准备运行 | v1 不做（ai-batch-loop.md:40） | — |
| 开始运行（本机或集群） | 只由人在工作流编辑器点运行 | 下一轮开始前写 `observed`（运行 ID、行、连接、资源选项） |
| 改项目、改标注、归档、改设置 | 只由人在原有界面完成；智能体只能说明缺什么、去哪里做 | 若影响会话，记为 `observed` 或 `policy` |

**`project.agent.decide`（新增，只给桌面；决定 12）**

- 参数：`{handle, session_id, item_id, decision: "apply"|"discard", draft_sha256, expected_revision}`。
- 不进脚本目录，先例是模型设置的写操作只给桌面（projects.py:260-262；脚本目录在 server.py:563 只含 `models.list`、`models.local.list`、`models.route` 三个只读项）。
- 执行步骤：
  1. 核对等待项存在且未处理；草案仍为 `pending`，`sha256` 与卡片显示的一致，`base_revision == expected_revision ==` 当前修订。
  2. 写入 `approval_decided` 并提交。批准人记本机用户名与主机名，注明 `authenticated: false`：STK 没有账户体系，工作流执行器也只记 host/pid（desktop_bridge/workflow_runs.py:131-132）。
  3. 调用 `drafts.apply` 或 `drafts.discard`，再写 `approval_receipt`（`applied_revision`，或错误）。执行失败不回滚批准记录：批准是已经发生的事实，执行结果另行记录。
- **无头（脚本）会话**：同样没有任何高于草案级的工具。会话以 `awaiting_user` 结束本轮，列出待处理项后停下，不等待。待处理项留给人在桌面处理。
- **审阅页的来源标记**：审阅页按对象登记表反查，显示“由智能体会话 X 第 n 步提议”。现有的 `project_proposals` 来源（问答消息）照常显示。

## 数据边界与网络设置

- **来源由服务端计算，不由模型声明。**
  - 每个工具给出 `sources:[{kind:"table", id}]`，并在 `tool_result` 中记下当时的标注；
  - 会话的来源集合是所有 `tool_result.sources` 的并集，只增不减（历史对话会整段重发，所以必须用并集）；
  - 未知种类一律视为私有；表的**结构**按该表的标注算：标注为“公开”或“结构公开”时结构算公开，否则算私有（决定 8）。
- **规划轮（v1）只发往本机或机构内端点**（决定 4）：
  - 会话创建时，用 `candidates(..., task="complex", public=False)`（routing.py:23-78）求候选，外部端点自然被排除为 `private_data`；
  - 每次发送前，新增的 `ModelGateway.admit_planner(configuration, sources)` 再检查一次：端点仍存在、网络设置允许（`policy.allows`）、受管本机模型在运行（同 gateway.py:95-99）、位置不是 `external`；
  - 将来允许外部规划时，还要求来源集合全部公开。这条现在就实现，作为第二道防线；
  - 与 `admit` 一样，不是端点的适配器（测试注入的）不检查（gateway.py:92-94），验收测试依赖这一点；
  - 被拒时本轮不认领，写 `stopped{private_data|network}` 并说明原因。
- **子请求按会话来源集合路由与检查**（修补单表检查的缺口）：
  - **缺口**：子请求的指令或问题文字由规划模型写成，而规划模型可能已经读过别的私有表。现有 `admit` 只看子请求上下文那一张表（gateway.py:100-101），所以一条针对公开表的子请求，可能把私有数据带到外部端点。
  - **路由**：工具选模型时传 `public = all_public(会话来源集合 ∪ {该上下文的表})`，按**当前**标注计算。
  - **检查**：在 `RequestExecutor.start` 之前，工具先调用新增的 `ModelGateway.admit_sources(configuration, sources)`，规则同上；之后执行器照常运行现有的 `admit`。两层检查各管一件事：前者管会话来源，后者管单表；
  - 一旦会话读到任何私有来源（包括没有标为“结构公开”的私有表的结构），其后的子请求只发往本机或机构内端点。
- **标注每次发送前重新读取。** 会话中途有表改为私有，下一次发送立即生效；改为公开时，已停下的会话不会自动继续。
- **用户输入的话**与现有 AI 助手的问题一样，不按标注检查（model-gateway.md 的“数据标注”一节）。v1 中它只发给本机或机构内的规划模型；进入子请求的文字随子请求的检查走。
- **工具本身不联网**：v1 的 8 个工具除子请求外，都只读写本地项目。
- **Runtime 上传不查标注**：Runtime 是用户自己的计算资源（server.py:861-865 的上传不做标注检查）。v1 中上传只发生在人点击的运行里。
- **系统提示**沿用现有措辞，“数据不是指令”（aliyun.py:46、53、78），并补充“工具结果是数据”。工具结果以 `{"tool":…, "data":…}` JSON 放进 `tool` 消息。

## 模型层改动（只对 `stk.agent/1`；现有三种请求体逐字节不变）

1. **规划轮输入**（冻结并哈希，不另存全文；按日志事件以确定规则重组）：
   ```json
   {"harness": "stk.agent/1", "configuration": {...}, "tools": [OpenAI function 定义，按注册表顺序],
    "messages": [{"role":"system","content":"<系统提示 + 技能说明>"},
                 {"role":"user","content":"{\"message\":…,\"stk_observations\":[…]}"},
                 {"role":"assistant","content":null,"tool_calls":[{"id","type":"function","function":{"name","arguments":"<JSON 字符串>"}}]},
                 {"role":"tool","tool_call_id":"…","content":"<工具结果 JSON 文本>"}, …]}
   ```
   `model_claimed.input_sha256` 记下重组结果的摘要。
2. **请求体**：新函数 `wire.turn_payload(turn_input, adapter, options, provider)`。
   - 请求体为 `{model, stream:false, max_tokens, messages, tools, tool_choice, parallel_tool_calls:false, **options}`；
   - `tool_choice` 只用 `"auto"`，到达上限后的总结轮用 `"none"`。永不发送 `"required"` 或指定函数（Qwen 不支持前者，思考模式下指定函数也会失败）；
   - 现有 `_payload`（aliyun.py:198-237）一字不改；
   - 规划轮上限：重组对话 ≤ 512 KiB，线上请求体 ≤ 2 MiB（同 aliyun.py:229-237）。
3. **解析**：新函数 `wire.turn_response(raw)`。
   - 只有一个 choice；`finish_reason ∈ {stop, tool_calls}`，`length` 仍算无效；
   - `content` 可为空或 null，但没有工具调用时必须是非空文字；
   - `tool_calls` 至多 1 个，两个及以上算 `response_invalid`；`type == "function"`；`name` 为 1–64 字符；
   - `arguments` **必须是 JSON 字符串**，对象一律拒绝。先用 `_unique_object/_invalid_constant`（aliyun.py:310-321）严格解析，长度 ≤ 16 KiB；
   - 名称不在冻结工具表里，或参数不合 schema：回合照常记为完成，由执行器作为错误结果交还模型，计入连续错误；
   - 缺 `id` 时由执行器派生 `uuid5(会话, call)`；
   - 仍拒绝 `function_call` 与 `audio`；`reasoning_content` 对 OpenAI 兼容端点照旧忽略。
4. **发送**：`_Prepared` 增加可选字段 `parse`（默认 `_response`），`_send` 改为调用 `self.parse`（现为 aliyun.py:564 直接调用 `_response`）。
   - 规划轮**只用非流式 `send`**；
   - 发送、截止时间、取消关闭连接，以及“确定没有发出”与“不确定”的分类全部原样复用（aliyun.py:520-587）；
   - 流式工具调用增量（aliyun.py:459-466 一带）推迟到 S2c。
5. **适配器**：`OpenAICompatibleAdapter.prepare_turn(turn_input)`，覆盖本机 llama.cpp、vLLM 与机构内端点。
   `AliyunTokenPlanAdapter.prepare_turn`（带 `enable_thinking:false`）随外部规划在 S2c 加，并取决于决定 2。
   vLLM 端点由用户自行以工具调用参数启动（例如 `--enable-auto-tool-choice --tool-call-parser …`）；STK 现在不启动 vLLM（model-gateway.md 的 S1c 已知限制）。
6. **返回类型** `ModelTurn(text: str|None, tool_call: dict|None, finish_reason, metadata)`；元数据经 `_validate_metadata`（requests.py:68-82）。
7. **路由与能力**：
   - `routing.TASKS`（routing.py:11）加 `"stk.agent/1": "complex"`。不加也会按复杂任务处理（routing.py:18-20），显式写出便于审计；
   - `LocalModels.routing_view()`（local.py:460-471）多给一个 `serve_context`。规划轮排除 `serve_context < 16384` 的本机项，原因为新增的 `small_context`；按现有目录，只会排除 catalog.json:105 那一项；
   - 用户添加的端点可选声明 `context_tokens` 与 `tool_calling`（决定 9）。未声明的 v1 不排除，回复无效时如实报告。
8. **回退（新行为，决定 7）**：
   - 规划轮只在“确定没有发出”时换冻结候选里下一个**其他端点**，即 `adapter_failed`，或自动选中的本机模型启动失败；
   - 而且只换到**同等或更近**的位置，绝不换到会话开始时没有显示过的端点；
   - 发送时同步被拒（`PolicyDenied`）不回退，显示原因并停下，与 S1d 现状一致（model-gateway.md:141）；
   - “不确定”与 `response_invalid` 不回退。
9. **思考保持关闭**（aliyun.py:223、local.py:743；决定 14）。
10. **黄金样本测试**：现有三种用途的请求体与解析逐字节不变。

## 执行器（`AgentExecutor`）

```
start(store, session_id):                         # 处理未处理的发言；重复调用不重发
  锁 .stk/agent-locks/<id>.lock（_RequestLock 加一个目录名参数，默认 request-locks）
  对上一次 awaiting_user 的每一项：读草案与运行回执 → 写 observed
  loop（≤ 12 个规划轮；墙钟、token、对话字节在每轮前检查）:
     transcript = 重组(日志)
     admit_planner(configuration, sources)；prepared = adapter.prepare_turn(transcript)   # 失败：不认领
     append model_claimed（提交事务）                                                    # 认领在发送之前
     try send → model_completed | model_settled(failed/cancelled/uncertain)
        映射同 request_executor.py:271-278：ConfirmedCancellation→cancelled；DefinitiveFailure→failed/adapter_failed；
        InvalidResponse→failed/response_invalid；其余→uncertain/transport_uncertain
     uncertain → append stopped{uncertain}；退出（从不重发）
     failed(adapter_failed) → 按回退规则换候选另行认领，否则 stopped{error}
     无工具调用 → 有待处理项则 append awaiting_user；append stopped{final}；退出
     有工具调用 → 校验名称与参数 → append tool_called → 执行 → append tool_result
  超限 → 一次 tool_choice:"none" 的总结轮 → stopped{limit}
```

- **子请求等待**：
  - `propose_sweep` 与 `ask_about_context` 调用 `RequestExecutor.start` 之后，轮询 `store.requests.get` 直到终态（间隔 0.2 秒，上限为适配器超时加余量）；
  - 会话取消时，调用 `RequestExecutor.cancel`；
  - 子请求“不确定”时作为工具错误返回，不重发。
- **取消**：
  - `project.agent.cancel` 先写 `cancel_requested`，再置位当前发送的取消事件（`_Prepared` 已支持取消关闭连接），并取消正在等待的子请求；
  - 结果沿用现有语义：确认取消记为 `cancelled`，否则记为 `uncertain/cancel_unconfirmed`（requests.py:344-355）。
- **恢复**：`recover` 由人或脚本显式调用，打开项目时不自动调用（与请求一致，request_executor.py:337-352）。
  - 末尾是 `model_claimed` 而没有结果：写 `model_settled{uncertain, executor_lost}` 与 `stopped{interrupted}`，不重发。
  - 末尾是 `tool_called` 而没有结果：写 `tool_result{status:unknown}`。下次“继续”时，先用同一 call_id 重跑这一工具：
    - 确定性 ID 使上下文、消息、子请求与草案都返回原对象；
    - 子请求若已在运行或已结束，`start` 不会重发（request_executor.py:152-158）。
- **规划轮“不确定”之后**：v1 建议该会话结束，用户另开新会话（决定 5）。

## 桥协议与脚本

新增方法写入 desktop-bridge-1 schema 与 docs/specs/stk-desktop-bridge-v1.md。能力就是方法是否出现在 `hello.methods` 中（stk-desktop-bridge-v1.md:941-942 的现有约定）。

| 方法 | 级别 | 说明 | 脚本目录 |
|---|---|---|---|
| `project.agent.tools` | read | 注册表（名称、级别、注解、参数 schema），以及 `never` 清单与理由 | 进 |
| `project.agent.route` | read | `{handle}`：规划轮候选与排除原因（v1 只含本机与机构内） | 进 |
| `project.agent.create` | record | `{handle, session_id, text, configuration?}`：冻结会话与第一条发言；不发送；可幂等重放 | 进 |
| `project.agent.say` | record | `{handle, session_id, turn_id, text}`：追加发言；幂等；会话运行中时拒绝 | 进 |
| `project.agent.start` | model | 处理未处理的发言；重复调用不重发 | 进 |
| `project.agent.cancel` / `recover` | record | 见上 | 进 |
| `project.agent.get` | read | `{handle, session_id, offset?, limit?}`：会话、校验后的事件、推导状态、等待项、用量（规划轮与子请求分开） | 进 |
| `project.agent.list` | read | 分页摘要 | 进 |
| `project.agent.objects` | read | `{handle, kind, object_id}` → 所属会话与步骤（审阅页、讨论页的来源标记） | 进 |
| `project.agent.verify` | read | 见“审计与核对”；不调用模型 | 进 |
| `project.agent.export` | read | `stk.agent-log/1` JSON | 进 |
| `project.agent.decide` | 应用或丢弃草案 | 只给桌面 | **不进**，并有测试 |

- 全部方法除 `decide` 外都不推进修订，也不发 `project.changed`。
- 桥 v1 不新增推送事件，客户端轮询（与请求一致）。
- Python 侧提供 `p.agent.create/say/start/get/list/tools/verify/export`，另有便捷的 `p.agent.ask(text, wait=True)`。
- 这些方法都不高于“问模型”，与已在白名单中的 `project.requests.start`（server.py:545）同级（决定 11）。

## 桌面（AI 助手内，最小改动）

- AI 助手的“用途”现有三项（ai_editor.cc:244），加第四项“智能体（多步）”。只有 `hello.methods` 含 `project.agent.start`、且项目为格式 13 时才出现。不新建工作区布局（沿用 ai-batch-loop.md 决定 4 的做法）。
- 发送前显示规划模型及其位置，复用 S1d 的说明方式（ai_editor.cc:474 的 `automatic_choice`）。没有可用模型时说明原因，例如“只配置了外部端点；v1 智能体只用本机或机构内模型”，并引导安装 32K 档本机模型。
- **步骤时间线**：新状态类 `project_agent.cc/.hh`，按 `project_discussion.cc` 的轮询方式。每步一行：
  - 级别徽标（读、记录、问模型、草案）、工具名（本地化）、一行摘要、所用模型与位置、数据来源及其标注；
  - 产物可以点开：上下文跳到讨论，子请求跳到对话，草案跳到审阅页，运行跳到工作流编辑器。
- **等待卡片**：“等待你：审阅并应用草案『…』”。
  - “打开审阅”进入现有审阅页，此时应用与丢弃改走 `project.agent.decide`；
  - 应用后显示回执，以及现有的“用工作流运行新增的 N 行”（ai_editor.cc:1073-1076）和“继续”按钮。
- **记录页**：完整事件列表、“核对记录”（调用 `verify`）、导出 JSON、链尾摘要。
- **其他**：取消、恢复；用量分规划 token 与子请求 token 两部分显示。
- **关注列表**：格式 ≥ 13 时，在 attention.py 中新增分支。
  - 等待你处理的会话列为 needs_you/review；
  - `stopped` 于 uncertain、error、limit、interrupted、private_data 的会话列为 needs_you/failure；
  - 运行中的会话列为 progress，`stopped{final}` 的列为 done；
  - v1 会话不能归档，出错的会话靠现有的“已看过”（`project.attention.viewed`）收起，直到 S2c 支持归档。
- **审阅页与讨论页**：经 `project.agent.objects` 标注“由智能体会话 X 第 n 步提议”或“由智能体代问”。

## 审计与核对

- **每次读取**：`project.agent.get` 都复核会话头与整条事件链。
- **`verify`**（新增 `AgentSessions.verify(session_id)`）在此之外还检查：
  - 按日志重组每一轮的输入，与 `model_claimed.input_sha256` 比对；比对冻结的系统提示、技能与工具定义全文和各自的摘要；
  - 核对每个 `objects` 引用的对象都存在，摘要一致，并且已登记在对象表中；子请求到草案的来源链接也要有效（discussion.py:131-161）；
  - **重算确定性工具**：
    - `capture_rows` 与 `capture_run_results`：上下文的摘要；
    - `table_statistics`：用冻结的上下文重新计算，与 `content_sha256` 比对；
    - `propose_sweep`：用现有的草案核对，即 `edit_proposal` 以回复摘要、标题与基准修订核对，不重新编译（ai-batch-loop.md 的 L1 说明）；
  - `observed` 与 `approval_receipt` 中的回执，仍与草案、运行记录一致。
- **修订对账**（测试与 `verify` 的报告项）：会话时间窗内，`changes` 表中的每次修订，要么是草案应用（`project_drafts.applied_revision`），要么来自运行登记输出，要么来自用户直接编辑；没有一次能对应到智能体的工具调用。
- **用量**：
  - 规划轮的 token 取自 `model_completed.metadata`，子请求的 token 由 `objects` 中的请求读出；
  - 会话显示两者之和；
  - 项目用量页在 S2b 增加“智能体规划”一行。
- **不做**：重放时重新调用模型（结果不可复现，还会产生费用）。

## 增量与测试

### S2a 记录、规划轮与只读工具（不接桌面）

- **内容**：
  - 格式 13 与升级、`AgentSessions`（三张表、链、对象登记、`verify` 的链与输入部分）；
  - `levels.py` 与一致性测试；
  - `wire.py`（请求体、解析、`ModelTurn`）、`_Prepared.parse`、`OpenAICompatibleAdapter.prepare_turn`、`admit_planner`、`routing_view` 的 `serve_context`；
  - `AgentExecutor`（循环、认领、结算、锁、取消、恢复、回退）；
  - 工具 `project_outline`、`capture_rows`、`table_statistics`；
  - 桥方法与脚本接口。
- **测试**（都不用真实密钥）：
  - **升级**：12 → 13 先备份，旧表与数据逐行不变；格式 12 的项目调用返回“请先升级”。
  - **链**：篡改任一载荷、顺序或会话头，读取与 `verify` 都报错；同 ID 同参数创建幂等，不同参数冲突。
  - **分级表**：覆盖脚本目录的全部操作；`never` 操作不可达。
  - **解析器**：
    - 合法的单个工具调用通过；
    - 两个调用、参数为对象、`finish_reason:length`、无工具调用且无文字，都判为 `response_invalid` 并停止；
    - 未知工具名、参数不合 schema，作为错误结果交还模型，计入连续 3 次上限；
    - 现有三种用途的请求体与解析，与固定样本逐字节一致。
  - **线上格式**：用标准库的本地 HTTP 假服务器跑真实的 `OpenAICompatibleAdapter`，覆盖 `tools`、`parallel_tool_calls:false` 与 `tool` 消息回传。
  - **网关**：
    - 规划轮用外部端点时报 `PolicyDenied`，没有 `model_claimed`；
    - 网络设置为离线时，本机仍可用；
    - `serve_context < 16384` 的本机项被排除为 `small_context`。
  - **崩溃点**：在认领前、认领后发送前、发送中、完成后保存前分别注入异常，恢复后的结果分别为未认领、`uncertain/executor_lost` 等，绝不重发（计数适配器的调用次数）。
  - **上限**：12 轮、连续 3 次错误、token 预算、对话字节、墙钟时间。
  - **取消**：发送前取消记为 `cancelled`；发送中取消，本机端点确认取消，机构内端点记为 `uncertain`。
  - **统计**：与手算值对比，覆盖常数列、单点与缺失值。
- **测试夹具**：脚本化的规划适配器，经 `ModelGateway.__setitem__` 注入，按顺序返回预设的 `ModelTurn`。这是新代码。
  现有 `controlled/1` 只是一个配置标签：tests/test_parameter_sweep.py:12-19 用 `claim` 加 `requests._complete` 绕过执行器，不是可以照搬的适配器。

### S2b 草案与结果技能、草案批准、桌面、验收

- **内容**：
  - 工具 `propose_sweep`、`ask_about_context`、`draft_status`、`find_runs`、`capture_run_results`；
  - `admit_sources` 与子请求按会话来源路由；
  - `awaiting_user`、`observed`、`project.agent.decide`；
  - 技能说明 `muferro-scan@1` 与 `table-analysis@1`：写进系统提示附录，冻结在会话头。技能目录现在只有 `graph.preset` 一种条目（suan/skills/catalog.py:41），新条目种类留到 S2 之后；
  - 桌面的“智能体”用途、时间线、等待卡片、记录页、关注列表、用量、来源标记；
  - 验收测试，以及真实模型的人工验收。
- **测试**：
  - `propose_sweep`：
    - 同一调用重放，得到同一消息、子请求与草案；
    - 修订变化时返回错误结果，不自动重定位；
    - 运行写入期间返回“请等运行结束”。
  - **子请求边界**：会话读过私有表之后，即使针对公开表的子请求，也只路由到本机或机构内端点；把配置固定为外部端点时，被 `admit_sources` 拒绝，请求保持 `pending`。
  - **`capture_run_results`** 与 C++ 的 L3 行为一致：只取成功任务、≤100 行、只取数值和整数字段，没有结果时报错。
  - **`decide`**：
    - 哈希不符、草案已不是 `pending`、修订已变化时，拒绝批准；
    - `approval_decided` 写在应用之前，并带 `authenticated:false`；
    - 脚本调用 `decide` 得到 `unsupported`。
  - **结构性保证**：用监视器包住 `store.drafts.apply`、`store.apply`、`workflow_runs.prepare/start`、`runs.prepare/submit`、`labels.set`，只要智能体执行路径（不含 `decide`）调用了其中任何一个，测试即失败。
  - **C++**：按现有编辑器测试的方式，覆盖时间线模型与等待卡片的各种状态。
  - **验收测试** `tests/test_agent_muferro_acceptance.py`，见下一节。

### S2c（视所有者决定）

- **外部规划**：
  - 需要决定 2 与决定 4 放开；
  - 加 `AliyunTokenPlanAdapter.prepare_turn`；
  - 规划轮也按来源集合检查。`project_outline` 遇到外部规划时，只列公开表，并注明“另有 N 张私有表”。
- **智能体准备运行与批准开始**（需要决定 3 放宽 ai-batch-loop.md:40）：
  - 工具 `prepare_sweep_run`，级别 `prepare_run`：调用 `workflow_runs.prepare` 加 `_simulation_identity`（server.py:382-389）。
    - 后者经 `connections.backend → runtime_client → tunnels.client`（suan/desktop_bridge/connections.py:203-225、236-244）取指纹；
    - 对 SSH 配置，只构造 `Tunnel` 对象而不启动进程（suan/runtime/ssh.py:59-75、226-243），指纹由地址计算（suan/desktop_bridge/backends.py:94-97）；
    - 但用本机 Runtime 时，它必须已在运行（connections.py:203-211）；
    - 实现时用测试固定“准备不发起网络连接”这一点；
  - 等待项 `{kind:"start_run", run_id, plan_sha256}`；
  - `decide(start)` 的步骤：
    1. 重读计划，要求 `sha256` 相同、状态仍为 `prepared`，行没有变化（同 desktop_bridge/workflow_runs.py:336-340 的检查）；
    2. 写 `approval_decided`；
    3. 调用工作流执行器的 `start`；
  - 卡片写明“批准将上传输入、提交 N 个任务，并在完成后写入结果表”，集群后端醒目标出 walltime 与节点数；
  - “本地轻量计算自动”要先能判定本地还是集群，见决定 3。现在只能从冻结的 `simulation.options` 推断后端（suan/mupro/spec.py:9-24）；而 Runtime 可能部署在集群登录节点上，此时本机后端会在登录节点上直接运行（docs/runtime-mupro.md:84-86 要求那里改用 slurm）。
- **流式**：规划轮的流式显示，在流式解析中加入工具调用增量。
- **归档**：会话归档，需要重建 `project_archive` 以扩充 kind 的 CHECK（store.py:155-156、archive.py:15、140-169），格式升到 14 或并入当时的格式变化。

### S2 之后

- 表格绘图；
- 技能进入技能目录（新条目种类，锁文件随之更新）；
- 用同一注册表生成 MCP 工具；
- 对话压缩；
- 运行结束后自动继续。

## 验收演示（不需要真实集群）

- **夹具**：
  - tests/test_bridge_workflow_muferro.py:39-69 的 `scan`：假 MuPRO SDK（tests/mupro_fake.py）、进程内 Runtime 与 Supervisor，两行 MuFerro 算例（300 K、325 K），工作流“算例 → muferro/1 → 能量分析”，`poll_seconds=0.02`。
  - `suan demo` 不能用：它没有 MuFerro 表，合成步骤也不产生 `result_record_id`（ai-batch-loop.md:59）。
- **模型**：
  - 脚本化规划适配器（S2a 新增）；
  - 受控子请求适配器，注入 `RequestExecutor`：扫描提议返回预设的 `stk.parameter-sweep/1` JSON，解读返回文字。

**步骤与断言**：

1. `project.agent.create`“以第一个算例为基准，在 300–400 K 之间扫 5 个温度”，然后 `start`。
   - 规划序列：`project_outline` → `capture_rows(MuFerro 表, [第一行], [温度…])` → `propose_sweep` → 文字结束。
   - 断言：
     - 草案为 `pending`，含 5 个新行；
     - **项目修订与开始前相同**；
     - Runtime 上 `client.tasks() == []`；
     - 有 `awaiting_user`，事件链校验通过；
     - 监视器没有记录任何应用、准备运行或提交的调用。
2. 规划模型若调用名为 `drafts_apply` 的工具，得到“不存在的工具”错误结果，记入链，项目不变。
3. 测试代表人调用 `project.agent.decide(apply)`：草案被应用，修订加 1，`approval_decided` 与 `approval_receipt` 记入链。
   再以人的身份 `workflow_runs.prepare + start` 运行新增的 5 行（`options={"launcher":"none"}`），等待完成。
4. `project.agent.say`“分析结果”，然后 `start`。
   - 规划序列：`draft_status` → `find_runs` → `capture_run_results` → `table_statistics(能量对温度, linear)` → `ask_about_context` → 文字结束。
   - 断言：
     - `observed` 记录了运行 ID 与资源选项，结果上下文含 5 行；
     - 统计值与直接计算一致；
     - 最终文字与子请求的回答都存在；
     - `verify` 通过（含重算统计与输入摘要）；
     - 会话用量等于规划轮之和加两个子请求之和；
     - 修订对账中，每次变化都来自第 3 步的人工动作或运行登记。
5. **变体**：只配置外部端点（全部表默认私有）。`project.agent.route` 没有候选，原因为 `private_data`，会话无法开始，没有发出任何请求。
   再加一个本机端点，然后把某张公开表的子请求固定到外部端点：在 `project_outline` 读过私有表之后，被 `admit_sources` 拒绝。

**真实环境人工验收**（不进 CI，记入 docs/runtime-validation.md）：
- 在 Linux 上用本机 32K 档模型（例如 catalog.json:72 一类条目）在桌面里走同一场景，记录模型、token、工具调用是否一次成功，并截图；
- Token Plan 的工具调用冒烟测试等决定 2；
- 有集群时，人在工作流编辑器里用 slurm 后端运行一次，智能体只观察。

## 明确推迟（v1 不做）

- 智能体准备或开始运行、运行批准卡片、“本地轻量计算自动”（决定 3）。
- 外部规划端点与 Token Plan 工具调用（决定 2、4）。
- 规划轮流式显示、对话压缩与摘要、运行结束自动继续、会话归档。
- 技能目录的新条目种类、MCP 暴露、表格绘图、文献与网页工具。
- 创建工作流、导入 MuFerro 算例、添加 Runtime 配置：仍由人完成。项目里须已有“算例 → muferro/1”工作流；智能体发现缺少时说明缺什么、去哪里做。
- 现有 `suan/mcp/server.py` 的 `submit_task`（:56）与 `run_stk_command`（:104）会直接提交、没有闸门：它们是“人工配置的 Runtime 工具”，不受智能体策略管辖。v1 在文档中写明这一点（决定 13）。

## 风险

1. **私有数据经子请求外发**：由服务端计算的来源并集与两层检查兜底；未知种类与私有表结构都按私有处理；有专门测试。
2. **v1 只用本机或机构内规划**：只配置了 Token Plan 的用户用不了智能体，界面要说明，并引导安装本机模型。
3. **小型本机模型的工具调用可靠性**（4B 级可能格式错误）：
   - 用 `small_context` 排除 8K 档；
   - 严格解析，设错误上限，失败时如实报告；
   - 每个目录项做一次人工的工具调用冒烟测试。
4. **llama.cpp 构建或 GGUF 模板变化导致工具调用格式漂移**：固定构建版本，配合上面的冒烟测试。
5. **修订陷阱**：后台运行登记输出会推进修订，使扫描转换失败。工具报错并允许重新捕获，不自动变基。
6. **提示注入**（经表格文字或文件）：工具最高只到草案级，应用要人批准；最坏结果是一份没用的草案或多花 token。
7. **代问消息**以 `role:user` 存入讨论：对象登记表能标出来源，但旧桌面与只读讨论表的读者分不出来。
8. **记录体积**：单条事件 ≤ 64 KiB，工具结果 ≤ 16 KiB；完整数据留在原对象里，日志只存模型看到的有界内容与摘要。
9. **链的防篡改能力有限**（同一 SQLite 文件）：靠导出与显示链尾摘要作外部对照。

## 所有者决定（2026-10-09）

1. **记录形态**：按建议 (a)，格式 13 加三张新表，规划轮不进 `project_requests`（技术项，按建议执行）。
2. **Token Plan**：所有者先选“现在就开”，又在澄清时确认**规划只用本机或机构内模型**；因此 Token Plan 不用于规划轮，
   只用于智能体代问的子请求（按会话来源集合检查，与现有 AI 助手相同），不必等工单确认。
3. **运行**：v1 保持“AI 从不准备或开始运行”；S2c 加“智能体准备运行计划、人在卡片上批准后开始”。
4. **模型位置**：规划只用本机或机构内模型；子请求只有在会话读过的所有数据都公开时才可发往外部。
5. **规划轮“不确定”之后**：会话结束，用户另开新会话。
6. **格式 13 范围**：按建议只加表（技术项），另按决定 8 重建 `project_labels`。
7. **规划轮回退**：按建议 (a)（技术项）。
8. **表结构**：**新增“结构公开”标注**（三种：公开 / 结构公开 / 私有）；结构按标注判定，详见“数据边界”与“持久化”。
9. **能力标签**：按建议 (a)（技术项）。
10. **上限**：按建议值（12 轮、连续 3 次错误、30 分钟、20 万 token、每项目 1 个会话、全局 2 个；超限先总结再停，可人工加额度）。
11. **脚本目录**：按建议 (a)，除 `decide` 外全部进入（技术项）。
12. **签名的草案批准**：v1（S2b）提供。
13. **MCP**：按建议 (a)，S2 之后（技术项）。
14. **思考**：按建议保持关闭。

## 需要所有者决定（原文，已作答）

1. **智能体记录的形态。**
   - (a) 格式 13 只加三张新表（会话、哈希链事件、对象登记），规划轮不进 `project_requests`；
   - (b) 把 `stk.agent/1` 放进 `project_requests`。这要重建该表，把外键改为可空，并分叉 `_input/_decode`、请求哈希、完成路径、用量、关注与归档。
   - 建议 (a)。现有三种请求逐字节不变；代价是规划轮用量由会话自己汇总。
2. **Token Plan 能否用于应用内智能体**（外部规划）。官方没有说明，仓库已记有用途限制的提示（docs/runtime-validation.md:1347）。
   - (a) v1 规划轮不用 Token Plan，所有者向阿里云提工单确认后再在 S2c 打开；
   - (b) 现在就打开，风险是密钥被封。
   - 建议 (a)。子请求照旧可以按数据边界使用 Token Plan，与现有 AI 助手相同。
3. **是否放宽“AI 从不准备或开始运行”**（ai-batch-loop.md:40）。
   - (a) v1 保持：智能体只到草案，运行由人经现有的 L2 导航与运行按钮完成，日志记录观察到的回执；
   - (b) S2c 允许智能体准备运行（只写本地冻结计划），由桌面的 `decide` 绑定计划哈希后开始；
   - (c) 再进一步，本地轻量计算按策略自动开始，集群作业必须确认。
   - 建议 v1 用 (a)，S2c 做 (b)。(c) 要先设计“本地还是集群”的可靠判定，再定。
4. **v1 的模型位置。**
   - (a) 规划轮只用本机或机构内模型；子请求只有在会话来源全部公开时才可去外部；
   - (b) 子请求也一律只用本机或机构内模型；
   - (c) 现在就允许外部规划，并按来源逐步检查。
   - 建议 (a)。
5. **规划轮“不确定”之后。**
   - (a) 该会话结束，用户另开新会话；
   - (b) 允许人点“重新发送”，以同一对话向同一端点再发一轮，界面写明可能重复计费、数据会再发一次，并记为 `policy` 事件。
   - 建议 (a)，与“不确定不重发”（model-gateway.md:103）最一致；若所有者认为 (b) 属于该条中的“由用户决定”，可改用 (b)。
6. **格式 13 的范围。**
   - (a) 只加表，会话在 v1 不能归档，`project_archive` 的 CHECK 重建留到 S2c；
   - (b) 格式 13 同时重建 `project_archive`。
   - 建议 (a)：迁移只做加法，风险最小。
7. **规划轮的回退。** S1d 在同步 `PolicyDenied` 时不回退（model-gateway.md:141），所以下面每一种都是规划轮的新规则。
   - (a) 只在 `adapter_failed` 或本机模型启动失败时换候选，且只换到同等或更近的位置、会话开始时已显示过的端点；`PolicyDenied` 时停下并说明原因；
   - (b) `PolicyDenied` 时也回退。
   - 建议 (a)。
8. **私有表的结构**（表名、字段名、行数）算不算私有。
   - (a) 算，按该表的标注；
   - (b) 结构总可以外发，只有单元格值受标注约束；
   - (c) 新增“结构公开”标注。
   - 建议 (a)，符合“新数据默认私有”。
9. **模型能力标签。**
   - (a) 本机项按实际 `serve_context` 排除 < 16384 的项（原因 `small_context`）；用户端点可选声明 `context_tokens` 与 `tool_calling`，声明不足的被排除，未声明的照常参与；
   - (b) 不加标签，出错再说。
   - 建议 (a)，并为每个目录项补一次人工的工具调用冒烟测试。
10. **上限默认值。** 建议：
    - 每次发言最多 12 个规划轮，每轮最多 1 个工具调用；
    - 连续 3 次工具错误即停，每次发言墙钟 30 分钟（不含等待人的时间）；
    - 每次发言 token 预算 200k（规划轮与子请求合计）；
    - 工具结果每条 16 KiB，重组对话 512 KiB，每轮回复 4096 token；
    - 每个项目同时 1 个会话，后台服务合计 2 个；
    - 超限时先做一次总结轮，然后停下；人可以加额度继续，加额度记为 `policy` 事件。
    请确认这些数值，或者给出其他值。
11. **`project.agent.*` 是否进入 Python 脚本目录。**
    - (a) 除 `decide` 外全部进入：它们都不高于“问模型”，与已在目录中的 `project.requests.start` 同级；
    - (b) 只给只读方法，发送只能在桌面。
    - 建议 (a)。`decide` 永不进入，但要说明：这只防止伪造批准记录，脚本本来就能直接应用草案、开始运行。
12. **v1 是否提供签名的草案批准**（桌面专用 `decide` 包装 `drafts.apply/discard`，与 ai-batch-loop.md:40 不冲突）。
    - (a) v1（S2b）提供：批准绑定草案哈希与基准修订，批准人记本机用户名与主机名，注明未经身份认证；
    - (b) v1 只记观察，批准记录留到 S2c。
    - 建议 (a)：改动小，能直接回应“草案审批”。
13. **MCP 的时间与现有 MCP 工具。**
    - (a) S2 之后，由同一注册表生成 MCP 工具与注解，外部宿主只能用 read、record、draft 级工具；同时在文档中写明现有 `submit_task`、`run_stk_command` 不受智能体策略管辖；
    - (b) 现在就做；
    - (c) 给现有两个工具补确认。
    - 建议 (a)。`mcp` 是可选依赖（pyproject.toml:70），harness 不依赖它。
14. **智能体回合是否打开思考。**
    - (a) 保持关闭（aliyun.py:223、local.py:743 的现状）；
    - (b) 对复杂规划打开：阿里云思考模式下指定函数会失败，计费也更高。
    - 建议 (a)。
