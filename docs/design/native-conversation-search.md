# 原生项目会话历史搜索

2026-11-13 起草，基线 STK `f3c666eb`。上位设计见[统一研究工作台](unified-workbench.md)。Web 历史标题筛选是对照目标，提交为 `90bc270e`，后经 `b076c2a3` 调整快捷键。本文是提案，尚未实现，也不修改已发布契约。

本文用两个标记区分事实与提议。「现有」指基线源码、契约或测试中已有的行为，并注明位置。「提议」是本文建议，由 root 决定是否采纳，并负责契约、代码、状态文档和推送。

## Root 实现说明

基线调查与提议保留供后续对照。当前实现采用一个统一的 `project.conversations.search`，在同一页返回问答与智能体会话，游标是 `{kind, id, created_at}`。搜索范围为当前打开项目的活跃问答与已保存智能体会话。归档问答沿现有浏览入口。读取逐条验证标题及其绑定并限制每页输出，单次搜索仍扫描该项目的候选标题。搜索使用历史中的独立入口，输入后按 Enter 或点击「搜索」，再明确打开一个结果。当前线协议以[桌面 Bridge v1](../specs/stk-desktop-bridge-v1.md)为准，实际点击与测试见[验收记录](../runtime-validation.md)。

## 1. 结论

- **现状。** 原生已保存问答的标题只在近期列表中出现，最多 20 条，默认 8 条。完整的分页历史只显示「模型 · 状态 · 编号前 8 位」，因此较早的问答无法按标题找到。智能体会话只载入最近 50 条，左栏显示 5 条。
- **最小的兼容读取。** 新增一个可选的本机只读方法 `project.requests.titles`，在 protocol 1 下通过 `hello.methods` 协商。服务端按标题匹配，并限定每次扫描的行数。返回的单条结果与 `project.requests.recent` 同形，另有游标表示「已扫完」或「可继续」，以及已检查到的时间。
- **智能体会话的对应读取。** `project.agent.titles` 用同样的规则搜索智能体会话标题，单独协商。它可以与问答读取同批发布，也可以后发。
- **只读标题，不读正文。** 问答标题只读请求行和用户消息行，不读上下文、助手回复和进度。智能体会话标题只读会话头和首条事件，不读整条事件链。结果在显式激活前不打开会话、不改选择、不加载交流内容。
- **不复用现有方法。** 不给 `recent` 或 `list` 加参数，也不复用 `project.search`。旧 Bridge 不支持时，界面保持现状，不出现搜索框，不发新方法，也不出现 `invalid_params`。
- **权限范围。** 新方法属于桌面专用读取，不进入脚本目录、智能体工具或 S2c 权限。范围是当前打开句柄所指的项目，默认排除已归档问答。不新增权限、项目格式或数据库表，也不改端点。
- **键盘激活。** 原生单行输入框按 Enter 只提交文字，不会触发 `on_submit`。本提议因此不采用 Web 的「唯一匹配按 Enter 即打开」。用户按 Enter 开始搜索，按 Tab 到结果行，再按 Enter 打开。

## 2. 现有事实

### 2.1 Web 标题筛选（对照目标）

| 项 | 现有行为 | 位置 |
| --- | --- | --- |
| 数据 | Hub 一次返回全部会话，`include_labels=true`，不分页 | `web/src/main.tsx:394`，`suan/control/store.py:382` |
| 标题 | `name`；名称仍为「新会话」时用 `label`。`label` 是首条用户消息的单行摘录，80 字符截断加「…」 | `web/src/conversations.ts:14`，`suan/control/store.py:48` |
| 归一 | 查询与标题均 `normalize('NFKC').toLocaleLowerCase()`，查询再 `trim().split(/\s+/u)` | `web/src/main.tsx:691-695` |
| 多词 | 每个词都须是标题的子串，与顺序无关 | 同上 |
| 范围 | 只筛选已载入的条目，包括本地新对话及「已不存在」「未确认」的条目，不读正文 | `web/src/conversations.ts:188-198` |
| 激活 | 有查询且恰好一条匹配时，Enter 打开并把焦点移到正文。零条或多条时 Enter 无动作 | `web/src/main.tsx:794-797` |
| 空结果 | `role=status` 显示「没有匹配的对话。」 | `web/src/main.tsx:805` |
| 输入 | `maxLength=200`（UTF-16 单元），输入法组字或按住重复时 Enter 被忽略 | `web/src/main.tsx:798-800` |
| 验收 | 宽 1440×900、窄 390×844，32 条历史。零匹配、30 条多匹配、唯一匹配各一次，阅读读取只有 `history B`、`history A`，零 POST，草稿保留，清空后恢复 33 条 | `web/tests/workbench-navigation.spec.ts`（`90bc270e` 新增用例） |

### 2.2 原生的两类会话及其标题

| 类别 | 身份 | 标题来源 | 位置 |
| --- | --- | --- | --- |
| 已保存问答 | `request_id` | 请求的 `message_id` 指向一条 `role=user` 的消息。标题是该消息的单行摘录：C0/C1 和双向控制字符换成空格，空白合并，超过 80 码位截为 79 位加「…」，无剩余文字时为「…」 | `suan/project/requests.py:29-34,308-327` |
| 智能体会话 | `session_id` | 首个 `user_turn` 事件的 `text`，列表截前 200 字符。桌面另做单行化，额外替换 U+061C、U+200E、U+200F，并按显示宽度截到 80 | `suan/project/agent_sessions.py:224-245`，`ai_editor.cc:2298-2315` |

一条用户消息可以对应多条请求，因为 `create()` 不要求 `message_id` 唯一（`requests.py:245-262`）。桌面每次准备问题都新建一条消息（`project_discussion.cc:512-529`），脚本则可以对同一消息另建请求。因此会出现标题相同的问答：可能是文字相同的两条消息，可能是同一消息的多次请求，也可能是 80 码位截断后撞上。

### 2.3 现有读取及其代价

| 方法 | 返回 | 实际读取 | 能否作标题搜索 |
| --- | --- | --- | --- |
| `project.requests.recent {handle, limit?}` | `{requests:[{request_id,status,created_at,label}]}`，最新在前，排除已归档 | 每行经 `_decode` 完整校验。`_input` 读取上下文与消息（`requests.py:225`），已完成的还要读助手回复（`requests.py:209`） | 只覆盖最新 20 条 |
| `project.requests.list {handle, offset?, limit?, archived?}` | 最旧在前，每页 100 条，只含元数据，无标题 | 同样经 `_decode` 完整校验 | 没有标题 |
| `project.discussion.get` / `list` | 单条消息全文；列表不含 `text`，只有 `text_bytes`（`discussion.py:88-98`） | — | 每条问答要单独读一次全文（N+1） |
| `project.search {handle, query, limit?}` | 按类别分组，每类至多 50 条；消息结果的目标是 `message_id` | 读整个快照（`search.py:39`），以及所有用户和助手消息的正文（`search.py:93-106`） | 读的是正文而不是标题；整串匹配，不分词；归档依据上下文而不是请求；结果没有 `request_id` |
| `project.agent.list {handle, offset?, limit?}` | `{items:[{id,created_at,first_message,state,turn,...}], total}` | 每个会话经 `_read` 读取并校验整条事件链（`agent_sessions.py:202-222,238`） | 读全部记录；桌面固定 `limit:50`，不翻页（`project_agent.cc:370`） |
| `project.agent.get` | 会话视图 | 整条事件链 | 属于打开会话 |

### 2.4 版本协商与严格参数

- **现有：按方法名协商。** 协商依据 `hello.methods`，`protocol` 固定为 1（`server.py:1188-1201`）。客户端以 `has_method` 判断：近期问答见 `project_discussion.cc:88-93`，项目搜索见 `project_search.cc:29-34`。
- **现有：多余参数被拒绝。** 每个方法的参数都是 `additionalProperties:false`，有测试强制（`tests/test_desktop_bridge.py:270-277`）。服务端先校验参数再分派（`server.py:635-640`），因此给 `recent` 加 `offset` 会得到 `invalid_params`，`test_bridge_model_requests.py:118` 断言了这一点。**结论：**旧 Bridge 不能用加参数的方式扩展，只能新增方法名。
- **现有：C++ 客户端的校验。** 客户端在构建时内嵌同一份 schema（`stk_bridge/CMakeLists.txt:14-21`）。发出请求时，只校验自己认识的方法（`client.cc:319-323`）。收到结果后，校验不合格计为 `schema_violations`，并转为 `InternalError`（`client.cc:613-620`）。
- **现有：服务端的错误映射。** `ProjectError` 映射为 `invalid_params`，未知句柄为 `not_found`（`projects.py:96-110`）。近期问答中只要有一行损坏，整次读取失败。

### 2.5 归档与权限范围

- **现有：归档。** 归档从格式 11 起可用。`archive.where(db, "request", archived)`：`true` 只取已归档，`false` 排除已归档，省略则不过滤；格式 11 以下 `true` 返回空（`archive.py:27-43`）。已归档的问答仍可读、可打开，只是不能发送（`projects.py:580-581`）。智能体会话 v1 不能归档（`workspace_editor.cc:365-366`）。
- **现有：分页历史的归档开关。** 开关 `ai_history_show_archived` 按 `show_archived("requests")` 改变 `archived` 参数（`ai_editor.cc:1113`，`project_discussion.cc:396-425`）。
- **现有：权限分级。** `project.requests.recent` 列为 `DESKTOP_ONLY` 的 `read` 级别，理由是「local conversation navigation; not an agent tool」（`levels.py:224`）。它不在脚本目录、`OPERATIONS` 和 `TOOL_USES` 中，由 `test_recent_requests_is_optional_desktop_only_and_strictly_bounded` 断言。`DESKTOP_ONLY` 与脚本目录不相交，由 `tests/test_agent.py:245-247` 断言。
- **现有：本机项目的授权边界。** 授权边界就是 Bridge 会话里打开的项目句柄，没有按用户的可见性。客户端用句柄、`project_scope_epoch`、`bridge_epoch` 和归档版本隔离近期读取（`project_discussion.cc:95-164`）。

### 2.6 原生客户端：入口、激活与键盘

- **现有：左栏与历史菜单。** 窗宽大于 700 逻辑像素乘缩放时为左栏，否则为顶部条加「历史」菜单（`shell.cc:815,1096`）。两者都有「写问题」「已保存问答」、近期问答 8 条、智能体会话 5 条和「刷新记录」（`shell.cc:1129-1234`）。窄窗菜单按行号派发，不能放输入框。
- **现有：「已保存问答」页（以下称浏览页）。** 浏览页即 `shows_saved_questions`。它只取一页 `project.requests.list`，显示下拉框、刷新、归档开关和上一页/下一页（`ai_editor.cc:289-306,1079-1126`）。浏览页不会自动选中问答，`opened_history_ = true`。现有测试断言进入时只有一次 `project.requests.list`（`workspace_navigation_test.cc:1070-1133`）。
- **现有：激活。** 激活走 `saved_conversation_action`，按屏幕、区域、可见性、句柄、项目 ID、作用域、Bridge、交流代数和导航代数逐项围栏，延迟到下一帧执行。若 `text_input_active()` 为真，则拒绝激活（`shell.cc:309-385`）。
- **现有：单行 Enter。** 单行输入框按 Enter 只提交绑定，`on_submit` 仅对多行框生效（`stk_ui/src/core/context.cc:886-901`）。绑定在提交时才写入（`context.cc:780-785,790-808`），Esc 默认撤销本次输入（`context.cc:903-907`）。字段已有焦点但未在编辑时再按 Enter，会重新进入编辑（`context.cc:1049-1061`）。在聚焦的字段上打字（含输入法预编辑）会直接开始编辑（`context.cc:1454-1467`）。输入法组字期间，按键归输入法处理，Enter 不会提交（`context.cc:855-857`），与 Web 对 `isComposing` 的处理一致。按住 Enter 的重复事件在单行框中会再次提交同一文字。按钮在获得焦点时可用 Enter 或空格激活（`context.cc:1016`）。工作区搜索的注释写着「Enter 开始搜索」，但它的单行框实际上只能点按钮触发（`workspace_editor.cc:195-213`）。现有测试也是点按钮（`workflow_editor_test.cc:898-902`）。
- **现有：大小写转换。** C++ 没有 Unicode 大小写折叠或 NFKC 实现，`stk_core`/`stk_ui` 中没有相应函数。
- **现有：一个副作用陷阱。** 普通会话视图在 `request_page_` 载入后会自动打开最新的一条交流（`ai_editor.cc:1145-1146`），`ProjectDiscussion::call()` 会设置 `busy_`，从而禁用撰写和打开（`project_discussion.cc:190-226`）。搜索若借用这两者，就会产生打开会话或阻塞输入的副作用。

## 3. 方案比较

| 方案 | 覆盖 | 读取 | 匹配 | 问题 |
| --- | --- | --- | --- | --- |
| C1 现有近期缓存（limit 20） | 最新 20 条 | 已有 | 需客户端折叠 | 达不到「全部」；C++ 无 casefold |
| C2 遍历 `requests.list` 页，再逐条 `discussion.get` | 全部 | N+1 次调用，读用户消息全文，每页仍完整校验上下文与回复 | 需客户端折叠 | 调用次数随历史线性增长，每次 `get` 都在 `busy_` 路径上，且无法排除只读一次就够的大正文 |
| C3 复用 `project.search` | 全部消息正文 | 整个快照加所有消息，含助手回复 | 整串，casefold | 搜的是正文而不是标题；结果为 `message_id`，每类至多 50；归档依据上下文；属于脚本目录的 `read` 操作 |
| C4 给 `recent` 加 `query`/`offset` | 全部 | 同 `recent` | 服务端 | 旧 Bridge 返回 `invalid_params`，破坏回退 |
| **S 新方法：服务端按标题匹配并限定扫描量** | 全部可见问答 | 每行只读请求行与用户消息行 | 服务端 NFKC+casefold，多词 | 需要新增契约，由 root 负责 |

推荐 S。理由有三：它是唯一不读正文、能覆盖全部可见问答、又能可靠回退的方案；匹配在 Python 中完成，避免了 C++ 自行实现 Unicode 折叠；新方法名与 `recent` 一样按方法单独协商。

缓存的保留用途：没有新方法时，界面保持现有近期列表与分页历史，不在 C++ 中用 ASCII 小写近似匹配。若只做 ASCII，`Ａ` 与 `a`、`Straße` 与 `strasse` 等会与服务端结果不一致。

## 4. 提议的线协议

### 4.1 `project.requests.titles`

```json
// 请求
{"id": "7", "method": "project.requests.titles",
 "params": {"handle": "0123456789abcdef0123456789abcdef", "query": "相场 讨论",
            "archived": false, "limit": 20}}
// 继续扫描
{"id": "8", "method": "project.requests.titles",
 "params": {"handle": "0123456789abcdef0123456789abcdef", "query": "相场 讨论",
            "archived": false, "limit": 20, "cursor": "11111111-1111-4111-8111-111111111111"}}
// 结果
{"id": "7", "result": {
  "query": "相场 讨论",
  "requests": [
    {"request_id": "22222222-2222-4222-8222-222222222222", "status": "completed",
     "created_at": "2026-11-12T08:00:00+00:00", "label": "相场参数讨论"},
    {"request_id": "33333333-3333-4333-8333-333333333333", "status": "failed",
     "created_at": "2026-11-01T08:00:00+00:00", "label": "相场参数讨论"}],
  "next_cursor": null,
  "checked_until": "2026-10-20T08:00:00+00:00",
  "unreadable": 0}}
```

**参数**

| 字段 | 规则 |
| --- | --- |
| `handle` | `hex32`，必填 |
| `query` | 字符串，必填。schema 为 `minLength 1`、`maxLength 800`，与 `project.search` 一致。服务端去掉首尾空白（Python `str.strip`）后须为 1–200 码位，并至少产生一个词（见第 5 节），否则返回 `invalid_params` |
| `archived` | 布尔，必填。`false` 排除已归档；`true` 只取已归档，格式 11 以下返回空。不提供「省略即全部」，避免与 `list` 的省略语义混淆 |
| `limit` | 1–50，默认 20 |
| `cursor` | `projectUuid`，可选。值为上次结果的 `next_cursor`。该请求行不存在时返回 `invalid_params`，客户端从头重搜 |

**结果**

| 字段 | 规则 |
| --- | --- |
| `query` | 去掉首尾空白后的查询原文，供客户端核对回包 |
| `requests` | 至多 `limit` 条，`maxItems 50`。单条结果与 `project.requests.recent` 同形，`label` 沿用其 schema 约束（1–80 码位、单行、无控制字符），客户端可共用渲染 |
| `next_cursor` | `projectUuid \| null`。`null` 表示从最新到最旧已全部扫完。非空表示达到 `limit` 或扫描上限，结果可能不全 |
| `checked_until` | `string \| null`。本次扫描中最后一条可读行的 `created_at`，不论它是否匹配；本次没有可读行时为 `null`。客户端据此显示「已检查到 {时间}」，不必为此另读请求 |
| `unreadable` | 整数，大于等于 0。本次扫描中无法校验而被跳过的行数 |

**排序与扫描**

- **顺序。** 按插入顺序从新到旧，即 `ORDER BY rowid DESC`，与 `recent` 一致。游标为最后一行**已扫描**的请求 ID（不一定是最后一条匹配），下一页条件为 `rowid < (SELECT rowid FROM project_requests WHERE id = :cursor)`。新保存的问答排在游标之前，不会让后续页漂移。
- **扫描上限。** 每次调用至多扫描 `SCAN_LIMIT = 500` 行（提议值，root 可按实测调整）。扫完上限或找满 `limit` 条即返回。服务端多看一行，以确定 `next_cursor` 是否为 `null`，避免末尾多出一次空页。
- **每行读取与校验。** 读请求行。复用 `_decode` 中「身份、状态与行列一致」的那部分校验：身份摘要、状态摘要、`message_id` 和 `status` 列一致。读 `message_id` 对应的消息行，经 `_decode_message` 校验其自身摘要和 `role=user`。**不读**上下文、助手回复、报告输入的冻结来源和进度，也不校验 `input_sha256` 的完整出处，这些留给打开时的 `project.requests.get`。校验失败的行不参与匹配，只计入 `unreadable`，不会让整次搜索失败。
- **无副作用。** 不调用执行器，不改修订、历史或撤销，不发事件，也不写 `project_archive` 或任何表。

### 4.2 `project.agent.titles`

```json
{"id": "9", "method": "project.agent.titles",
 "params": {"handle": "0123456789abcdef0123456789abcdef", "query": "相场 讨论", "limit": 20}}
{"id": "9", "result": {
  "query": "相场 讨论",
  "sessions": [{"session_id": "44444444-4444-4444-8444-444444444444",
                "created_at": "2026-11-10T08:00:00+00:00", "label": "相场参数讨论"}],
  "next_cursor": null, "checked_until": "2026-09-30T08:00:00+00:00", "unreadable": 0}}
```

- **参数。** 与 4.1 相同，但没有 `archived`，因为 v1 的会话不能归档。项目格式低于 13 时返回空结果，与 `list` 一致（`agent_sessions.py:229-230`）。
- **读取。** 读会话头并校验头摘要、ID、项目和 harness（同 `_read` 的 `agent_sessions.py:209-212`）。再按 `project_agent_events_by_session` 索引只取首个事件，用 `previous = header sha256` 校验该事件的摘要，并要求它是 `user_turn`。不读其后的事件。
- **结果。** 不返回 `state`，因为状态要读完整条链才能算出，打开会话后再显示。`label` 用与 4.1 相同的单行算法生成（见 5.1）。`checked_until` 为最后扫描那个会话头的 `created_at`，其余字段与 4.1 相同。
- **顺序与游标。** 与 `project.agent.list` 一致，按首个事件 ID 从新到旧。游标为最后扫描的会话 ID，扫描上限同为 500。

### 4.3 版本协商与旧 Bridge 回退

| 发现的方法 | 浏览页 | 搜索范围提示 |
| --- | --- | --- |
| 两者都有 | 显示搜索框，结果分「问答」「智能体会话」两组 | 无 |
| 只有 `project.requests.titles` | 显示搜索框，只有问答组 | 一行「此版本不能按标题搜索智能体会话」 |
| 只有 `project.agent.titles` | 显示搜索框，只有会话组 | 一行「此版本不能按标题搜索已保存问答」 |
| 两者都没有 | 与基线相同：没有搜索框，也没有提示 | — |

- **前置条件。** 问答搜索还要求格式 8 或以上，并且 `recent_requests_supported()` 为真。会话搜索要求 `agent.supported()`。
- **禁止加参数。** 客户端不得向 `recent`、`list` 或 `agent.list` 加任何参数，也不得在方法缺失时调用后再看是否报错。
- **新桌面配旧 Bridge。** 新方法不在 `hello.methods` 中，客户端不发出调用。界面、RPC 次数与基线逐项相同。
- **旧桌面配新 Bridge。** 旧桌面不认识这两个方法，也不会调用，没有影响。

### 4.4 分类与权限

- **提议：分级。** 两个方法都列入 `DESKTOP_ONLY`，级别为 `read`，理由沿用「local conversation navigation; not an agent tool」。
- **提议：不进入其他目录。** 两个方法不进入 `script_catalog`、`OPERATIONS`、`TOOL_USES` 或 Python 门面的 `p.requests.*`。若以后要给脚本用，另作决定。
- **提议：不新增权限。** 不新增权限、标签检查或网络行为。读取的范围只有当前句柄对应的项目。

### 4.5 root 需改动的位置（实现清单）

1. `suan/project/requests.py`：新增 `titles()`，把标题单行化抽成共用函数，`recent()` 也改为调用它，输出保持不变；新增只做行内校验的解码。
2. `suan/project/agent_sessions.py`：新增 `titles()`。
3. 共用的归一与匹配函数，可放在 `suan/project/` 下的一个小模块。
4. `suan/desktop_bridge/projects.py`：在 `requests` 和 `agent` 两个分派中各加 `"titles"` 分支。
5. `suan/desktop_bridge/server.py`：在方法表中加入两个方法，不加入 `script_catalog`。
6. `suan/agent/levels.py`：`DESKTOP_ONLY` 增加两项。
7. `suan/contracts/schemas/desktop-bridge-1.schema.json`：增加两个方法条目，每个只含 `description`、`params`、`result`，且 `additionalProperties:false`。
8. `docs/specs/stk-desktop-bridge-v1.md`：在 §13 方法表和 `project.requests.recent` 条目旁各补一段。
9. C++ 部分：
   - 新建独立的搜索状态，可仿 `ProjectSearch` 或 `recent_`。不得经过 `ProjectDiscussion::call()`，也不得写入 `request_page_`。
   - 在 `ai_editor.cc` 浏览页加入界面。
   - 在 `desktop/app/i18n/{en,zh_CN}.json` 加入文案。
10. 测试见第 8 节。

## 5. 匹配规则

### 5.1 被匹配的标题

问答与智能体会话都用同一单行算法，即现有 `recent` 的算法：替换控制字符、合并空白、80 码位截断。匹配的对象是截断后、**添加「…」之前**的文字。截断时追加的「…」，以及没有文字时的占位「…」，都不参与匹配。效果与 Web 一致，Web 也只匹配 80 字符的 `label`；标题第 80 码位之后的词搜不到。

### 5.2 归一、大小写、空白与多词

```text
fold(s)  = casefold(NFKC(s))
terms    = fold(strip(query)).split()      # Python 的 Unicode 空白
title_f  = fold(title_core)
match    = terms 非空 且 每个 term 都是 title_f 的子串
```

- **不分词。** 子串匹配不考虑词边界，例如「场参」可以匹配「相场参数」。词序无关，重复的词等同于一个。
- **中文。** 中文没有大小写，也不分词，按字面子串匹配。
- **全空白。** 查询全为空白时客户端不发请求，直接显示完整的浏览页。服务端对这类查询返回 `invalid_params`。
- **不支持语法。** 不支持引号短语、通配、正则或排除词。

### 5.3 与 Web 的已知差异（实测向量）

以下各行均已实测：Python 用 3.12.14 加 `unicodedata`；Web 侧用 Node v24.20.0 运行 Web 的同一表达式，区域为 en-US。

| 标题 | 查询 | 原生（提议） | Web（现有） | 说明 |
| --- | --- | --- | --- | --- |
| `ＡＢＣ 报告` | `abc` | 匹配 | 匹配 | NFKC 全角 |
| `Ⅻ 号样品` | `xii` | 匹配 | 匹配 | NFKC 兼容字符 |
| `ﬁle 列表` | `file` | 匹配 | 匹配 | 连字 |
| `cafe` + U+0301 | `café` | 匹配 | 匹配 | 组合字符合成 |
| `相场参数讨论` | `讨论 相场` | 匹配 | 匹配 | 多词、乱序 |
| `ΟΔΟΣ` | `οδος` | 匹配 | 匹配 | — |
| `ΟΔΟΣ` | `οδοσ` | 匹配 | **不匹配** | casefold 统一 σ/ς；JS 按词尾规则转小写 |
| `Straße` | `STRASSE` | 匹配 | **不匹配** | casefold 把 ß 展开为 ss |
| `İstanbul` | `i̇stanbul` | 匹配 | 匹配（en-US） | JS 的结果随区域变化，tr 区域不同 |

两端不追求逐字一致。原生采用不随区域变化的 casefold，以上差异只会让原生多匹配，不会漏匹配。Web 是否改用同一规则，由 root 另行决定。

### 5.4 长度

- **查询长度。** 输入框 `max_length = 200`，与工作区搜索一致（`workspace_editor.cc:211-212`）。服务端按码位复核。
- **Web 的计数单位。** Web 的 200 按 UTF-16 单元计，所以含 emoji 时 Web 允许的码位更少。这一差异无害。

## 6. 列表与分页规则

### 6.1 单类列表与双类列表

「单类/双类列表」沿用 `build_history` 中 `show_agents` 的分支（`shell.cc:1136-1142`）：只列问答、只列智能体会话，或两类都列。仓库中没有更具体的定义，本文按这个理解，请 root 确认。

- **问答组出现的条件。** `recent_requests_supported()` 为真，且 `hello.methods` 含 `project.requests.titles`。
- **会话组出现的条件。** 现有 `show_agents` 为真，且 `hello.methods` 含 `project.agent.titles`。按 `show_agents` 的现有规则，问答可用、会话列表已载入且为空时，左栏不列会话。这时搜索也不列会话组，也不发 `project.agent.titles`。
- **方法缺失时。** 某一类在左栏列出、但缺少对应的标题方法时，按 4.3 显示一行范围提示，不发请求。

- **单类。** 不显示组标题，结果直接列出，计数写作「N 条问答」。
- **双类。** 问答组在前，智能体会话组在后，各有自己的计数、游标和「继续搜索」按钮。两组不合并排序，因为两类的游标不可比。某一组扫完且为空时显示「没有匹配的问答」或「没有匹配的智能体会话」，另一组照常显示。

### 6.2 分页与「继续搜索」

- **首次结果。** 提交查询后，每组发一次首页请求。
- **继续搜索。** `next_cursor` 非空时，该组末尾显示「继续搜索更早的记录」，需用户点击或用键盘激活，不自动连续翻页。
- **追加。** 后续页的结果追加到已显示的结果后面，按 ID 去重。同一 ID 若在后页再次出现，以后页为准。
- **空结果的判定。** 只有 `next_cursor` 为 `null` 且该组结果为零时，才显示「没有匹配」。未扫完时显示「已检查到 {时间}，尚未找到」，并显示继续按钮。{时间} 取最近一页的 `checked_until`，按本地时间显示；它为 `null` 时只显示「尚未找到」。不得在未扫完时显示「没有匹配」。
- **无法读取的行。** `unreadable` 大于 0 时，在该组末尾加一行「另有 N 条记录无法读取」。实际原因要从分页历史打开该条才能看到，界面不猜测。

### 6.3 标题相同的结果

- **每行一个身份。** 每行以 `request_id` 或 `session_id` 为身份，控件键为 `ai_history_search/question/<id>` 和 `ai_history_search/agent/<id>`。标题相同的结果不合并、不去重。
- **行文字。** 行文字为「标题 · 本地创建时间 · 状态」。标题、时间都相同时，再加编号前 8 位。会话组的行没有状态。
- **不自动打开。** 结果再多，也不因唯一匹配而自动打开，见 7.4。

## 7. 界面行为

### 7.1 位置

- **放在浏览页内。** 搜索框放在浏览页顶部、标题行之下。窄窗的「历史」菜单只能放按钮，所以宽窗和窄窗共用浏览页。
- **左栏与历史菜单不变。** 近期问答 8 条、会话 5 条和刷新照旧。
- **非聚焦的 AI 编辑器。** 分页历史仍内嵌在会话中（`!history_on_rail`）。本期不在那里加搜索框，以免与正在进行的交流争夺 Enter 和焦点。
- **进入浏览页。** 打开浏览页时，用 `restore_focus_next_frame` 把焦点放在搜索框上，但不进入编辑。用户可以直接打字（`context.cc:1454-1467`），也可以按 Tab 越过搜索框，用原下拉框。
- **焦点顺序。** 依次为：搜索框、问答结果行、问答组的继续按钮、会话结果行、会话组的继续按钮，然后是原有的下拉框、刷新、归档开关和翻页。

### 7.2 状态

| 状态 | 显示 |
| --- | --- |
| 未输入或已清空 | 搜索框为空，浏览页与基线完全相同，不发出新方法 |
| 请求中 | 搜索框下显示「正在搜索…」，保留上一次结果；新提交替换旧请求 |
| 已载入 | 计数与结果行（见第 6 节） |
| 已扫完且为空 | `没有匹配的问答。`，与 Web 的 `role=status` 措辞对应 |
| 未扫完 | 「已检查到 {时间}，尚未找到」加继续按钮，{时间} 来自 `checked_until` |
| 失败 | 显示错误的 `describe()`，保留查询；不自动重试，按「刷新记录」或再按一次 Enter 才重搜 |
| 方法不可用 | 见 4.3 |

### 7.3 结果过时与作用域

- **记录变化没有通知。** 问答和会话记录不推进修订，也不发 `project.changed`（`stk-desktop-bridge-v1.md` §13）。所以工作区搜索那种「修订不同即提示过时」的检查在这里不适用。
- **围栏。** 搜索状态以句柄、`project_scope_epoch`、`bridge_epoch`、归档版本、归档开关和查询原文为围栏。任一变化即作废已显示的结果和迟到的回包，与 `recent_` 的处理相同（`project_discussion.cc:95-164`）。
- **本桌面写入后。** 本桌面保存、取消或重试问答后，会置 `recent_.dirty`（`project_discussion.cc:466-467` 等）。此时把搜索标记为过时：浏览页可见时自动重跑首页，不可见时等回到浏览页再重跑。重跑只是读取。
- **外部写入。** 脚本、另一进程或另一台机器写同一个 SQLite，客户端无法察觉。用户按「刷新记录」才会重跑当前查询的首页。这是已知限制。
- **作用域隔离。** 项目 A 的结果不会出现在 B。切换、关闭或重开项目，以及 Bridge 重启，都会清空查询和结果，迟到的回包按代数丢弃。

### 7.4 显式激活

- **激活方式。** 结果行是按钮，鼠标单击或键盘 Enter/空格激活。问答行调用 `saved_conversation_action(origin, request_id)`，会话行调用 `saved_conversation_action(origin, session_id, AgentSession)`，与左栏条目相同，所以继承第 2.6 节列出的全部围栏和 `text_input_active()` 检查。
- **激活前零读取。** 激活前不得发出 `project.requests.get`、`progress`、`discussion.get`、`contexts.get` 或 `agent.get`。浏览页的 `opened_history_ = true` 语义保持不变。
- **Enter 只搜索，不打开。** 在搜索框中按 Enter，只提交文字并启动搜索。提议不采用「唯一匹配即打开」，原因有二：
  - 原生搜索是异步的，Enter 按下时结果还没到，直接打开会对上一次结果竞态；
  - 单行框的 `on_submit` 不会在 Enter 时触发，要做到这一点必须改界面引擎。
- **键盘路径。** 输入，按 Enter（搜索），按 Tab（到第一条结果），再按 Enter（打开），共 3 个非字符键。
- **改 Enter 的选项。** 若 root 希望单行 Enter 触发 `on_submit`，应作为 `stk_ui` 的独立改动处理。这一改动会同时影响工作区搜索，需单独验收。
- **会话行的可用性。** `history_selection_available()` 为假时（有尚未完成的发送或启动），会话行禁用，提示与左栏一致。

### 7.5 近期列表与归档

- **近期列表照旧。** 近期列表仍用 `recent`，不受搜索影响，也不显示搜索结果。
- **归档开关决定范围。** 浏览页的归档开关同时决定搜索范围。开关关闭时 `archived:false`，结果与近期列表一样排除已归档。开关打开时 `archived:true`，只搜已归档，与 `list` 一致。切换开关即作废当前结果，并用同一查询重搜首页。
- **打开已归档的问答。** 已归档的问答可以打开阅读，但不能发送，沿用现有冻结规则。

### 7.6 草稿与 Viewer

- **草稿不变。** 搜索与激活不读写撰写草稿 `project_draft`，也不改变其选区或焦点记录。
- **查询的生命周期。** 查询原文只保存在当前打开项目的编辑器内存中，不写入布局 JSON。离开浏览页再回来，查询仍在，与 Web 用例中 `toHaveValue('相场 讨论')` 一致。切换项目即清空。Esc 按引擎默认撤销本次输入，恢复上次已提交的查询。
- **Viewer 不变。** 搜索不触及 Viewer 的载荷、相机和时间步。激活与左栏条目的路径相同，因此保留 Viewer 和分栏，验收中核对相机序号。

## 8. 测试建议

### 8.1 Python（不收费、无密钥）

- **`test_titles_is_optional_desktop_only_and_strictly_bounded`**
  - 仿照 `test_bridge_model_requests.py:105-127`。
  - 断言：两个方法都在 `hello.methods` 中，在 `DESKTOP_ONLY` 中，不在 `OPERATIONS`、`TOOL_USES` 或 `script.catalog` 中。
  - `limit` 取 0、51、`True`、`"8"`、`1.5`，以及缺少 `archived`、多出 `offset`，都返回 `invalid_params`。
  - 全空白查询和 201 码位的查询返回 `invalid_params`。
  - 结果用 `validate_outgoing` 检查，并对 `label` 的非法样例做反证。
- **匹配**：参数化第 5.3 节全部向量，再加以下各项：
  - 「…」不匹配被截断的标题；
  - 第 80 码位之后的词不匹配；
  - 只出现在助手回复或上下文单元格里的词，返回空且 `next_cursor` 为 `null`。
- **只读不读正文**
  - 用 monkeypatch 让 `Contexts._get` 抛错，并让助手消息的读取抛错，`titles` 照常返回。
  - 前后比较 `store.snapshot()`、`store.history()`、`requests.list()` 和数据库字节，必须相同。
  - 执行器的 `start` 和 `progress` 被禁用（同 `test_bridge_model_requests.py:78-83`），`project.changed` 不出现。
- **分页**
  - 保存 130 条问答；
  - 把扫描上限 monkeypatch 为 50，断言前两页的 `next_cursor` 非空，结果为部分；
  - 第三页 `next_cursor` 为 `null`；
  - 扫描上限内零匹配时，`requests` 为空、`next_cursor` 非空，`checked_until` 等于第 50 行的 `created_at`；
  - 页间新插入的问答不进入后续页；
  - `cursor` 指向不存在的 ID 时返回 `invalid_params`。
- **归档与格式**
  - 已归档的问答在 `false` 时缺席、在 `true` 时只出现它；
  - 格式 10 项目用 `true` 返回空；
  - 格式 7 返回 `unsupported`，与 `recent` 同源。
- **损坏行**：篡改一行请求的 `state`，断言 `unreadable == 1`，其余结果照常返回。
- **智能体会话**
  - 篡改第二个事件，`titles` 仍返回该会话，而 `list` 把它标为 damaged，证明没有读整条链；
  - 篡改首事件或会话头，计入 `unreadable`。
- **标题相同**：两条文字相同的消息，加上同一消息的两次 `create`，共 3 行，标题相同、ID 不同、全部返回。

### 8.2 C++（`desktop/tests/app`）

沿用 `RecentRequestsPython` 的 hold/release 与失败标记（`project_test.cc:420-466`），以及 `SavedConversationNavigationPython` 的读取追踪（`workspace_navigation_test.cc:758-765`）。

- **迟到回包**：搜索回包挂起时切换项目、切换归档开关、更改查询或重启 Bridge，迟到的回包被丢弃，且 `schema_violations == 0`。
- **零副作用**
  - 打开浏览页并完成搜索后，追踪文件只多一条 `project.requests.list`，加上每组一次 `titles`；
  - `exchange_id()` 仍为空；
  - `discussion.busy()` 在请求中保持为假，撰写区可用。
- **激活**
  - 点击，或者 Tab 加 Enter 打开第 105 条（见第 9 节）；
  - 原草稿字节不变，`viewer.camera_serial()` 不变，`f.screen.maximized()` 为 AI 区域。
- **会话行激活**：从搜索结果激活会话行，读取与从左栏打开同一会话完全相同（现有回执为 route/get），选中该会话，且不开始新一轮；有尚未完成的发送时，该行禁用。
- **旧 Bridge**
  - 用 `del self.methods[...]` 去掉一个或两个新方法（同 `workspace_navigation_test.cc:2371`）；
  - 断言搜索框和提示按 4.3 的表格出现；
  - 追踪中没有新方法，日志中没有 `invalid_params`。
- **焦点与输入**
  - 进入浏览页即可打字；
  - Enter 不打开结果；
  - Esc 恢复上次查询；
  - 宽窗与窄窗（`kWorkbenchRailBreakpoint` 两侧）的焦点顺序与 7.1 一致。

## 9. 固定桌面验收

两个窗口都使用 Linux X11、真实桌面、严格 Python Bridge 和合成项目，缩放 1，沿用最近交付的窗口约定。

### 9.1 固定起点

- **窗口。** 英文 1600×1100（左栏），中文 680×1000（「历史」菜单）。
- **项目 A。**
  - 共有 130 条已保存问答，按插入顺序编号 #1 为最旧、#130 为最新。
  - #105 为「Zircon 相场参数讨论」，已完成，带两行回复。它不在近期列表（最新 8 条，`limit` 上限 20 时为 #111–#130）中，也不在分页历史首页（最旧 100 条，#1–#100）中。在基线中，它的下拉标题只有「模型 · 状态 · 编号」，无法按标题找到。
  - #3 的文字与 #105 完全相同，用于检验标题相同的情况。
  - 另有一条已归档问答「Zircon 讨论 archived note」。它含查询的两个词，只因归档而被排除。
  - 有一个智能体会话，首条消息为「Zircon 讨论 agent session」。项目格式为当前版本（不低于 13），所以 `show_agents` 为真。
  - 只在 #50 的助手回复和上下文单元格中出现过「hafnium」。
- **项目 B。** 有一条问答「Zircon 讨论 other project」，也含查询的两个词。本次测量前已关闭，它的句柄已失效。
- **界面起点。** 当前为任务页，项目 A 已打开并显示 #130。撰写区有两行未发送草稿。Viewer 已打开公开的 `muferro_domains.stkp`，记下相机序号。归档开关关闭。

### 9.2 步骤与预期

| 步骤 | 英文 1600×1100 | 中文 680×1000 |
| --- | --- | --- |
| 进入浏览页 | 左栏「Saved questions」1 次点击 | 「历史」、「已保存问答」2 次点击 |
| 输入 | 直接键入 `zircon 讨论`，按 Enter | 同左。驱动以文本输入事件发送，不经输入法；组字中的 Enter 由 C++ 测试覆盖 |
| 预期结果（查询 `zircon 讨论`，归档关闭） | 问答组 2 行：#105 在前、#3 在后，标题相同，时间不同。会话组 1 行「Zircon 讨论 agent session」。没有已归档条目，没有 B 的条目。两组的 `next_cursor` 均为 `null` | 同左 |
| 打开 | 按 Tab（到 #105 行），Enter | 同左 |
| 结果 | AI 区域显示 #105 及其回复；草稿、Viewer 相机与分栏不变 | 同左 |
| 反证 1：权限与归档（查询 `zircon 讨论`） | 回到浏览页，查询仍为 `zircon 讨论`，结果与上面相同，仍然没有已归档条目和 B 的条目。打开归档开关后，问答组只剩「Zircon 讨论 archived note」1 行，可打开阅读，不能发送。会话组不变。关闭归档开关 | 同左 |
| 反证 2：只看标题（查询 `hafnium`） | 改为 `hafnium` 并按 Enter：两组都显示「没有匹配」，`next_cursor` 均为 `null` | 同左 |
| 合计（打开 #105 为止） | 鼠标 1 次点击；非字符键 Enter、Tab、Enter | 鼠标 2 次点击；非字符键同左 |

鼠标路径：输入并按 Enter 后单击 #105 行，宽窗共 2 次点击，窄窗共 3 次。

### 9.3 记录与核对

- **RPC 次数。** 进入浏览页到打开之前，只有 1 次 `project.requests.list`（现有）、1 次 `project.requests.titles` 和 1 次 `project.agent.titles`。会话行在本次测量中不激活，激活由 C++ 测试覆盖。`get`、`progress`、`discussion.get`、`contexts.get`、`agent.get` 均为零。打开后的读取与现有「从历史打开问答」的回执相同。
- **零写入。** 测量全程零 `create`、`start`、`discussion.add` 和模型请求。项目 A 的 SQLite 摘要和修订号前后一致。
- **状态保留。** 撰写草稿字节一致，Viewer 相机序号一致，布局 JSON 一致。
- **权限反证。** 项目 B 的「Zircon 讨论 other project」从未出现。归档开关关闭时，「Zircon 讨论 archived note」不出现。两者都含全部查询词，所以它们的缺席只能来自作用域和归档过滤。`script.catalog` 中没有新方法。
- **旧 Bridge 对照。** 同一起点改用去掉两个方法的 Bridge：浏览页与基线像素一致，追踪中没有新方法。
- **回执。** 写入 `receipt.json`，至少包含窗口、语言、缩放、起点描述、点击和按键序列、RPC 追踪、两份 SQLite 摘要、草稿摘要和相机序号。截图保存为 `search.png` 和 `opened.png`。点击数照 AGENTS 的要求记入 `docs/runtime-validation.md`，由 root 填写。

## 10. 本次核对

- **Python 定向测试**
  - 在本 worktree 使用 `/home/mnemora/opt/stk-venv/bin/python`（3.12.14），`env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY=`，输出在 `/tmp/stk-claude-115/`。
  - `tests/test_bridge_model_requests.py`、`tests/test_search.py`、`tests/test_archive.py`、`tests/test_project_requests.py` 共 92 项通过（9.42 秒）。
  - `tests/test_agent_sessions.py` 2 项通过。
  - 这些测试固定了第 2 节引用的现有行为：`recent` 的边界、排序与截断，`list` 的分页，严格参数，`DESKTOP_ONLY` 分类，以及搜索与归档的语义。
- **只看源码与断言，未运行**
  - C++ 原生测试与 Web Playwright 用例本次没有构建或运行。
  - 第 2.1 节的 Web 行为和第 2.6 节的原生行为，依据所引源码和测试断言（`workbench-navigation.spec.ts` 中 `90bc270e` 新增的用例、`workspace_navigation_test.cc:1070-1133`、`project_test.cc:420-560`）。
- **Unicode 向量**：第 5.3 节的每一行都按所列 Python 和 Node 版本实际计算过。
- **未改动的部分**：本文没有修改契约、代码、端点或权限。

## 11. 未决事项

- **扫描上限与 `limit`。** 500 行和 20 条（上限 50）是提议值，需要在合作方规模的问答库上实测时延后再定。
- **是否只做问答。** 问答和会话两个方法可以同批发布。若 root 只先做 `project.requests.titles`，按 4.3 的「只有问答」一行处理。
- **会话标题的控制字符。** 会话标题由服务端单行化后，不再替换桌面额外处理的 U+061C、U+200E、U+200F。需要决定是把这三个字符也加入共用控制字符集（这会改变 `recent` 的输出和 schema 模式），还是保留现状。
- **单行 Enter。** 是否让单行 Enter 触发 `on_submit`，属于 `stk_ui` 的独立决定。它同时会修正工作区搜索注释与实际行为的不一致。
- **「单类/双类列表」的含义。** 本文按 `show_agents` 分支理解（6.1）。若 root 另有所指，例如单条匹配与多条匹配，需要改写 6.1 和 7.4。
- **Web 是否改用同一归一规则。** Web 是否改为 NFKC 加 casefold，以消除第 5.3 节的差异，由 root 另定。
