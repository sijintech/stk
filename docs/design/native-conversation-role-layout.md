# 桌面聚焦会话的角色布局：实现方案（提案）

2026-11-13 起草，基线 STK `dd3c8a02d92c4be1730601b111c1ddff0be2fa14`（Root 任务 119）。首期几何布局已于本地 `main` 的 `385aa7f4` 实现。下文保留基线调查及实现取舍。上位对照见 [Synthrix 主页面视觉对照](synthrix-primary-page-parity.md) 第 3.3 节「角色区分」和第 5 节，交互规则见 [统一研究工作台](unified-workbench.md)。

## Root 审阅结论

首期采用现有日志控件的可选行范围布局。用户块最宽为可用正文文字区的 85%，右缘锚定在预留滚动条后的可见文字区。角色标签和块内文字共用左缘。助手、工具与审批状态继续从左侧显示。实现可复用现有折行和字体测量，按当前语言及实际字体尺寸失效缓存。调色、额外留白与面板常显仍待决。

将角色直接绑定到问答段和智能体事件，统一折行时保留段之间原有的空行与顺序。分栏调用原来的整段 `wrapped_text`，可直接复核旧显示。聚焦路径要测常见终端控制字符和末尾换行。极窄宽度下，单个不可再分的字形可以交给控件裁剪。绘制测试分别核对块内文字共用左缘和块的最宽行抵达右锚点。键盘、滚动和草稿按现有可观察行为验收。以下接口和数据结构供实现参考。

目标：在聚焦工作台中，让桌面的项目问答正文和智能体时间线也有 Web 已有的角色布局，即用户消息靠右，其余内容靠左。已有的比例字体（`15d879b2`）和输入卡片（`dd3c8a02`）不改。分栏视图、原始回复、日志、计划和文件预览也不改。

本文分两类内容：

- **观察**：在基线源码中读到的事实，附 `文件:行`。只读了相关片段，没有构建、运行或测量。
- **提案**：本文的建议，需 Root 审阅后才能采用。

## 1. 观察：Web 的角色规则（已交付 P1，`50e7d5a9`）

| 项 | 位置 | 内容 |
| --- | --- | --- |
| 结构 | `web/src/main.tsx:953-954` | 每条消息是一个 `article`，class 为 `m.role`（`user` 或 `assistant`）。上方 `small` 写「你」或「STK」，下面是 `p` 正文。待发送消息是 `article.user.pending`，标签为「你 · 发送中」 |
| 通用规则 | `web/src/style.css:171-174` | `article` 有下边线，上下内边距 12 px，宽度占满列 |
| 用户规则 | `web/src/style.css:175-183` | 宽度 `fit-content`，最大 `85%`。`margin: 8px 0 8px auto` 把消息块推到右侧，块内文字仍左对齐，标签也在块内。内边距 8/12 px，无边线，圆角 12/12/4/12，底色 `#2a3144` |
| 正文 | `web/src/style.css:184-189` | 标签用强调色 `#7e9cd8`。正文 `pre-wrap`，`overflow-wrap: anywhere` |
| 断言 | `web/tests/workbench-navigation.spec.ts:1854-1859` | 用户消息右缘与记录区右缘相差在 1 px 内，宽度 ≤ 85% + 1 px。助手消息左缘与记录区左缘重合，且比用户消息宽 |

Synthrix 的参照值取自对照文档第 3.3 节，本次没有重读 Synthrix 源码：用户消息右对齐，最宽 85%，浅色底，圆角 12/12/3/12；助手消息左对齐，占满列宽。

可以确定的一点：**Web 的规则是“整块靠右、块内左对齐”，不是每行各自右对齐。** 桌面若要对齐 Web，就得把一个用户块当作整体，按同一个左缩进绘制，并用 85% 列宽来折行。

## 2. 观察：桌面的两条绘制路径

### 2.1 共同的折行函数

`desktop/engine/lib/stk_app/src/editors/ai_editor.cc:168-182` 的 `wrapped_text(text, width, ctx, mono)` 处理步骤如下：

1. 先用一个 `LogBuffer` 规范化整段文本。制表符在这里展开，ANSI 序列和单独的 `\r` 也在这里处理。
2. 再用 `ui::break_lines` 按所选字体折行。
3. 把每一行追加到新的 `LogBuffer`。

两条路径都把角色标签和正文**拼成一段纯文本**后再折行，所以拼接之后已经没有角色信息。

### 2.2 项目问答（`ai_transcript`）

- 一次只显示**一组**问答，即当前请求的问题和回复，不是多轮会话。见 `ai_editor.cc:1210-1225`，键在 `:1208-1209`。
- 文本的组成是：`ai.you` 加问题，然后一个空行，然后回复。回复的标签按请求类型取 `ai.assistant`、`ai.parameter_reply` 或 `ai.sweep_reply`。没有回复时，显示 `ai.temporary_reply` 加进度文本。
- 字体按聚焦状态选择：聚焦工作台用常规字体，否则用等宽字体（`transcript_mono = !focused`，`:1204`）。
- 折行宽度 `wrap_width = conversation_width − 4·unit`（`:1205-1207`）。聚焦时 `conversation_width = min(区块宽, 880·scale)`。
- 缓存键 `shown_exchange_` 包含：问题、回复、进度、折行宽度、`unit`、字体标记和 `ai.you` 的译文（`:1208-1209`）。
- 绘制调用是 `layout.log_view("ai_transcript", …, transcript_position(transcript_positions_, id)).mono = transcript_mono`（`:1250-1251`）。
- 原始回复 `raw_reply_` 始终用等宽字体折行（`:1224`），显示在「请求详情」里（`:1325`）。

### 2.3 智能体时间线（`ai_agent_timeline`）

- `agent_steps(view, ctx)`（`ai_editor.cc:1598-1653`）按 `view.events[].kind` 逐条生成文本：
  - `user_turn`：先输出一个空行，再输出 `ai.you` 和正文。
  - `model_completed`：输出 `ai.agent.says` 和正文。
  - 其余事件（`tool_called`、`tool_result`、`model_settled`、`approval_decided`、`approval_receipt`、`policy`、`cancel_requested`、`stopped`）：各输出一行状态文字，结果行前面缩进两个空格。
- 折行与绘制在 `:1735-1748`。字体规则与问答相同（`timeline_mono = !focused`）。
- 缓存键 `shown_agent_` 由 `chain_sha256`、折行宽度和字体标记组成（`:1741`），**不含** `unit` 或界面语言。
- 每个会话有自己的阅读位置，表里最多保留 32 条（`:1090-1103`）。
- 位置的跟随状态有两处会改：
  - 离开一个会话时，它的位置改为不跟随（`:1689-1694`）。
  - 明确发送后，当前会话改为跟随，回到最新（`:1837-1839`）。
- 打开另一个项目时，所有会话位置清空（`:1683-1685`）。
- 阅读位置不写入工作区状态。`save_workspace_state` 只保存草稿（`:215` 起）。

### 2.4 `LogView` 控件（`stk_ui`）

| 项 | 位置 | 行为 |
| --- | --- | --- |
| 创建 | `layout.cc:393-403` | 默认 `mono = true`。高度按单位换算。位置对象由调用方提供 |
| 行高 | `context.cc:1206-1210` | 所有行同高：所选字体的 `size_px × 1.4` 取整 |
| 绘制 | `draw.cc:629-707` | 只绘制可见行。每行在 `row.x + text_margin` 处用同一颜色（`th.tooltip.text`）画文字。滚动条宽度 `sbw` 只在内容溢出（`ms > 0`）时计入行宽 |
| 键盘 | `context.cc:1146-1163` | 支持 ↑、↓、PageUp、PageDown、Home、End。滚到底部时恢复跟随 |
| 滚轮与滚动条 | `context.cc:2024-2031`、`:1770-1795` | 滚轮一次滚 3 行。点击滚动条轨道时翻一页 |
| 位置 | `ui.hh:271-274`、`context.cc:179-191` | 位置只有两项：像素偏移 `offset` 和是否跟随 `follow`。跟随时显示最后一行 |
| 选择与复制 | `context.cc:930-941` 只在文本编辑中，`table_grid.cc:286-307` 只在表格中 | **`LogView` 不能选择文字，也不能复制。** 问答的复制入口是「请求详情」里的显式按钮（`ai_editor.cc:1313`），复制的是请求或回复的 ID |
| 缓冲区 | `log_buffer.hh` | 只能追加的终端模型，超过 `max_lines` 时从头部丢行。`wrapped_text` 用 `size_t` 最大值作上限，实际上不会丢行 |

`Layout` 支持 `LayoutAlign::Right` 和 `Layout::box()`（`ui.hh:128`、`:363`、`:377`），工作台区域也有自己的外层滚动（`ui.hh:469-471`）。

### 2.5 现有测试

| 层 | 位置 | 已断言的内容 |
| --- | --- | --- |
| UI 核心 | `desktop/tests/ui/test_events.cc:926` `LogView.ClearingMonoDrawsAndScrollsWithTheRegularFontAndKeepsTheDefaultMonospace` | 在缩放 1 和 2 下核对：<br>• 绘制命令的字体和基线；<br>• 行高；<br>• 尾部跟随；<br>• Home、↓、End 三个键；<br>• 追加内容后继续跟随。<br>使用 `FakeTextMeasurer`（`tests/ui/support.hh:19`） |
| 问答（聚焦） | `desktop/tests/app/workspace_navigation_test.cc:1693-1729`（`expect_proportional_transcript`）、`:1730-1755` | 第 0 行是 `ai.you`，第 1 行是问题，第 2 行为空，第 3 行是 `ai.assistant`。核对段落词序与常规字体折行，以及输入卡片与正文同宽、同一左缘 |
| 时间线（聚焦） | `desktop/tests/app/project_agent_runs_test.cc:1402-1460`（`expect_proportional_timeline`），由 `:1682`（宽，英文）和 `:2047`（窄，中文）调用 | 核对标签逐行、两段用户文本的拼接词序、末尾空行、字体、尾部位置和按键 |
| 分栏 | `desktop/tests/app/project_test.cc:1438` | 长双语回复按等宽字体折行，保存的回复不变 |
| 像素 | `widget_gallery` 金标准（见 CL-117 记录） | 默认 `log_view` 的等宽像素 |
| 实窗 | Root 回执 V10（`root-delivery-20261113-192/typography-*-verified`） | Linux X11 两种窗口下的字体、位置和草稿 |

### 2.6 读源码时注意到、尚未验证的问题

- `shown_agent_` 不含界面语言和 `unit`。会话打开时切换语言或缩放，时间线可能要等链变化后才会重新生成。这一点没有运行确认。
- 根据测试中的界限式（`workspace_navigation_test.cc:1699`、`project_agent_runs_test.cc:1412`）推算，`wrap_width ≈ rect.w + 2·panel_margin + scrollbar − 4·unit`。在默认样式（缩放 1）下，这比带滚动条时可见文字区窄约 30 px。这是推算值，不是测量值。

## 3. 观察：已有的语义数据

在拼成纯文本之前，两条路径都已经知道每段文字属于谁，**不需要新增 Bridge 方法或字段**。

| 面 | 用户块 | 其他内容（左侧，占满列宽） | 来源 |
| --- | --- | --- | --- |
| 项目问答 | `question.text`，配标签 `ai.you` | `reply.text`（或参数、扫描回复），或 `progress.text` 及其标签 | `discussion.exchange_*`，`ai_editor.cc:1205-1221` |
| 智能体 | `kind == "user_turn"` 的 `text`，配标签 `ai.you` | `model_completed` 的回复，以及工具、结果、结算、审批、回执、策略、取消、停止各行 | `view.events[]`，`ai_editor.cc:1603-1650` |

Web 只有两种角色：`user` 和 `assistant`。桌面时间线里的工具、审批和停止等状态行，Web 没有对应规则。**提案：这些行保持靠左、占满列宽，与今天相同，不另设样式。**

## 4. 可选方案

所有方案都按以下几点评估：

- 是否保留 `LogBuffer` 的行文本，以及第 2.5 节测试依赖的标签行、词序和尾部空行。
- 是否保留滚动、跟随、键盘操作和每个会话的像素位置。
- 是否需要新的引擎接口。

| 方案 | 做法 | 行文本 | 滚动、跟随、位置 | 新接口 | 结论 |
| --- | --- | --- | --- | --- | --- |
| A. 前导空格 | 用户块按 85% 宽度折行，每行前补空格，推到右侧 | 改变，每行多出空格 | 不变 | 无 | 不采用。比例字体下空格宽度对不齐，CJK 与拉丁混排时更明显。测试字符串和日后可能的复制内容都会被污染 |
| B. 每条消息一个控件 | 每条消息改为 `Layout::box()` 加段落，用 `LayoutAlign::Right` 排列，依靠区域外层滚动 | 不再有统一缓冲区 | **全部重做**：`LogViewPosition`、尾部跟随、Home/End、只画可见行都要改到区域滚动上实现 | 可能不需要 | 第一片不采用。长会话（测试有 40 条消息）要全量布局。现有的会话位置表、发送后跟随和 V10 回执都建立在 `LogView` 上，回归面太大 |
| C. 行块附表（**推荐**） | 文本照旧放在 `LogBuffer` 中。调用方另给一张很小的“行块”表，记录哪些行属于用户块和块的像素宽度。`LogView` 绘制时只改这些行的 x 坐标 | 不变（只有用户块内因宽度变窄会多折几行） | 不变。行高、`max_scroll`、按键和位置的计算都不变 | 是，在 `Widget` 上加一个可选字段（第 5.1 节），默认为空 | 采用，作为第一片 |
| D. 多个 `LogView` | 每条消息一个 `LogView` | 拆散 | 无法共用一条滚动 | 无 | 不采用 |
| E. 新的会话控件 | 在 `stk_ui` 新增一个控件类型，支持不等高的块、内边距、底色，乃至选择和复制 | 新模型 | 新实现 | 是，接口较大 | 留作后续。以后若需要块内边距、头像或文字选择，再评估 |

## 5. 推荐方案：行块附表（提案）

### 5.1 引擎接口草案（新接口，由 Root 决定是否采用）

本文不预设任何新接口。下面的写法只为说明需要多大的改动：

```cpp
// stk/ui/ui.hh（草案）
struct LogBlock {
  size_t first_line = 0;  // 在 LogBuffer 中的起始行号
  size_t lines = 0;       // 块内行数
  float width = 0.0f;     // 块内最宽一行的像素宽度，用控件当前字体测量
};
// Widget 上新增一个字段，默认为空，行为与今天完全相同
std::shared_ptr<const std::vector<LogBlock>> log_blocks;
```

`draw.cc` 在 `LogView` 分支的改动：

1. 对落在某个块内的可见行，文字起点改为 `anchor − block.width`。
2. 锚点 `anchor = body.x1() − (st.scrollbar + 2·px) − st.text_margin`。**锚点始终预留滚动条宽度，不看内容是否溢出。** 这样内容在实时更新中开始溢出、滚动条出现时，用户块不会横移。
3. 若 `block.width` 超过可用宽度，就退回到 `row.x + text_margin`。
4. 不在块内的行保持 `row.x + text_margin`。
5. 若缓冲区丢过行（`dropped() > 0`），忽略整张表。今天的两条路径都不会丢行。

行高、`max_scroll`、`list_body`、键盘、滚轮、滚动条、`LogViewPosition` 和点击取焦点都不受影响。默认 `log_blocks == nullptr` 时，所有其他 `LogView` 走原路径，包括终端日志、分栏视图、原始回复、运行计划、运行详情和文件预览。

为什么锚定在可见文字区右缘，而不是 `wrap_width` 右缘：Web 用户块的右缘就是记录区右缘减去内边距（第 1 节的断言）。而按第 2.6 节的推算，`wrap_width` 右缘还要再往里约 30 px。若 Root 更想让用户块与助手正文的折行右缘一致，可以把锚点改成 `text_left + wrap_width`，接口不用变。这一项列为 R2。

### 5.2 两个面共用一个实现

两条路径在同一个文件里，都走 `wrapped_text`。提案在 `ai_editor.cc` 中加一个内部辅助函数，**不新增公开接口**：

```cpp
struct Turn { bool user; std::string text; };   // text 已包含角色标签行，结尾为 '\n'
struct WrappedTurns { ui::LogBuffer log; std::vector<ui::LogBlock> blocks; };
WrappedTurns wrapped_turns(const std::vector<Turn> &turns, float width, EditorContext &ctx, bool mono, bool roles);
```

- `roles == false` 时，结果必须与今天的 `wrapped_text(拼接文本, …)` **逐字节相同**。分栏视图走这条路径。
- `roles == true` 时，非用户段按 `width` 折行。用户段按 `floor(0.85 · width)` 折行，记录行号范围，并取块内最宽一行的宽度。角色标签也算在块内，所以 `width ≥ 标签宽度`。
- 问答把问题、回复或进度组成两到三段。智能体把 `agent_steps` 改为逐段产出，`user_turn` 前面的空行仍然单独成段、留在块外。
- 两处调用都把 `focused` 作为 `roles` 的条件，与现有的 `!transcript_mono` 和 `!timeline_mono` 相同。

缓存键需要补的项：

- `shown_exchange_` 和 `shown_agent_` 都要加入角色布局的标记，做法与 CL-117 加入字体标记相同。
- `shown_agent_` 建议同时补上 `unit`，因为块宽是像素值。是否同时补上语言标记见 R4。

需要逐字节核对的边界：今天的 `wrapped_text` 是对整段文本规范化，按段拆开后改为逐段规范化。一段的末尾若有单独的 `\r`、未闭合的 ANSI 序列或不完整的 UTF-8，跨段时的处理结果可能不同。智能体的每一行都以 `\n` 结尾，问答的问题段也以 `\n\n` 结尾，所以只有回复段会落在最后。验收用例要覆盖这类输入（第 7.1 节）。

### 5.3 第一片的范围

做：

1. `stk_ui`：`LogBlock` 和 `Widget::log_blocks`，以及 `draw.cc` 的 x 偏移（第 5.1 节）。
2. `ai_editor.cc`：`wrapped_turns`，接入两条聚焦路径，更新缓存键。
3. 测试：第 7.1、7.2 节列出的单元测试和应用测试。

不做：

- **底色、圆角和块内边距**。底色属于配色选择，见第 6 节 Q1。上下内边距需要不等行高或额外的空行，属于方案 E 的范围。
- 头像、标签颜色和字号层级。
- 文字选择与复制：基线不支持，本片也不增加。
- Web 的任何改动。
- 分栏视图、原始回复、运行计划、运行详情、文件预览和终端日志：行为与像素都不变。
- Bridge、项目数据、模型请求、发送权限、草稿、Viewer 和面板常显。面板常显见对照文档 Q2，本文不涉及。

做完第一片后，宽窗中用户问题会靠右，最宽为列宽的 85%，字体和颜色不变。这是只改几何的最小一步。

## 6. 必须保持的行为

| 行为 | 基线 | 第一片如何保持 |
| --- | --- | --- |
| 折行后的阅读位置 | 每个请求或会话各存一份像素偏移。同一宽度下重新打开会恢复位置 | 行高与偏移的含义都不变。同一宽度下内容不变，位置精确恢复。宽度改变时会重新折行，偏移按像素保存，可能落在不同的文字行，与 CL-117 的已知限制相同 |
| 尾部跟随 | `follow` 为真时始终显示最后一行。离开会话时取消跟随，明确发送后恢复 | 不改 `LogViewPosition`，也不改 `ai_editor.cc:1689-1694` 和 `:1837-1839` 的逻辑 |
| 复制与选择 | `LogView` 不支持。ID 复制靠显式按钮 | 保持不支持，按钮不变 |
| 键盘滚动 | ↑、↓、PageUp、PageDown、Home、End，滚到底部恢复跟随 | 行高不变，按键步长不变 |
| 角色文字 | 标签各占一行：`ai.you`、`ai.assistant`、`ai.agent.says` 等 | 标签文本和所在行不变。用户标签移到用户块内，随块一起靠右 |
| 项目、Viewer 与草稿 | 输入卡片和草稿键不变，Viewer 相机不受影响 | 本片只改绘制坐标，不新增读取、写入或焦点移动 |
| 分栏与原始回复 | 等宽字体，不分角色 | `roles = false`，`log_blocks` 为空，逐字节相同 |

## 7. 验收方案（提案）

固定起点沿用对照文档第 4 节：

- **NS1**：Linux X11，英文 1600×1100、中文 680×1000。聚焦「工作台」，已打开合成项目，智能体会话甲有运行卡片。
- **V10 起点**：会话甲已上滚，且有未发送草稿。

本片**不新增任何点击**：阅读正文 0 次。切到会话乙再回到甲，宽窗 2 次、窄窗 4 次，与 V10 相同。V1–V10 的点击、按键和焦点结果都必须不变。

每一轮都要核对：

- 零发送、零模型调用（`STK_TOKEN_PLAN_API_KEY` 为空，`STK_TOKEN_PLAN_MODEL` 未设置）；
- 项目修订、会话链和数据库摘要不变；
- 草稿和 Viewer 相机不变。

### 7.1 UI 核心（`tests/ui/test_events.cc`，`FakeTextMeasurer`，缩放 1 和 2）

- `log_blocks` 为空时，每条文字绘制命令的位置与今天相同。现有 `LogView` 用例和 `widget_gallery` 金标准不动并且通过。
- 给出一块后：
  - 块内行的 x 等于 `anchor − width`，块外行的 x 等于 `row.x + text_margin`；
  - 从不溢出追加到溢出、滚动条出现前后，块内行的 x 不变；
  - 行高、尾部偏移，以及 ↑、↓、Home、End、滚轮的结果与无块时相同；
  - 跟随状态下追加一行后仍在尾部。
- 块宽超过可用宽度时退回左对齐。缓冲区丢行时忽略整张表。

### 7.2 应用（扩展现有辅助函数，不另写一套）

在 `expect_proportional_transcript` 和 `expect_proportional_timeline` 中增加以下断言：

- **标签与词序不变**：第 2.5 节列出的行号、标签和拼接词序断言保持原样。用户段因为按 85% 折行会多出几行，但拼接后的词序相同。
- **几何**：
  - 用户块每行的测量宽度不超过 `floor(0.85 · wrap_width)`；
  - 块内文字命令的 x 一致，最宽一行的右缘在锚点 ±1 px 以内；
  - 助手回复、智能体回复和工具状态行的 x 等于 `row.x + text_margin`；
  - 输入卡片与正文仍然同宽、左缘相同（`workspace_navigation_test.cc:1730-1755`）。
- **宽窗与窄窗**：宽窗英文（`project_agent_runs_test.cc:1682`），窄窗中文（`:2047`，经「历史」进入）。窄窗中 85% 的列宽仍要能完整放下标签「你」。
- **双语**：用户块中混排 CJK、拉丁文字和 emoji。`FakeTextMeasurer` 中 ASCII 按 0.5 em、CJK 按 1 em 计宽。中文窗口下块宽不小于「你」的宽度，英文窗口下不小于「You」的宽度。若 R4 决定补语言键：打开会话后切换语言，下一帧标签与块宽随之更新。
- **长消息**：
  - 用户消息远超 85% 时按 85% 折行，块宽接近 `0.85 · wrap_width`。
  - 有 200 行的用户消息时，滚轮上滚 10 格、切到会话乙再返回，偏移与离开时相同（同一宽度）。
  - 改变窗口宽度后重新折行，偏移按像素截取，不出现越界。
- **实时增量**：
  - 问答：在跟随状态下，进度文本分三次追加，每次都停在尾部。在上滚状态下追加，偏移不变，可见行的文本和 x 也不变。
  - 智能体：在会话甲上滚时，追加 `tool_called`、`tool_result` 和 `model_completed`，偏移不变。明确发送后出现新的 `user_turn`，回到跟随，新的用户块靠右。
- **分栏与原始回复**：`project_test.cc:1438` 原样通过。分栏视图中 `log_blocks` 为空、字体为等宽，行文本与基线逐字节相同。
- **逐字节一致**：对含制表符、`\r`、ANSI 序列、CJK 和 emoji 的回复，`wrapped_turns(…, roles=false)` 与基线 `wrapped_text` 的输出逐行相同。

### 7.3 实窗（Root 执行）

- 起点、操作和点击次数同上。真实 BLF 字体，Linux X11 两种窗口。
- 截图中用户字形掩膜的右缘应落在锚点 ±2 px 以内，左缘一致，助手字形的左缘与基线相同。
- 回到会话甲后，正文区域与出发时像素一致，草稿字样及其位置一致。
- 记录每一轮的项目读取次数。基线为每轮两次 `project.agent.get`，本片不应增加。
- macOS 和 Windows 由 CI 的原生作业覆盖，本文不要求另做手工验收。

## 8. 需要 Root 或所有者决定

| 编号 | 问题 | 归属 | 本文立场 |
| --- | --- | --- | --- |
| Q1 | 用户块的底色、圆角和标签颜色 | 所有者（配色，对照文档 Q1） | 第一片不加底色。若要沿用现有主题而不引入新颜色，可选的现成槽位有 `th.box.inner`、`th.list_item.inner_sel`、`th.panel_sub_back`。选用哪个也属于配色决定，本文不选 |
| Q2 | 字体与字号层级 | 所有者（对照文档 Q1） | 不改，沿用现有常规字体 |
| Q3 | 任务与文件面板常显或持久化 | 所有者（对照文档 Q2） | 不涉及 |
| R1 | 是否接受 `Widget::log_blocks` 这一新的引擎字段 | Root | 推荐接受。不接受时，第一片没有可行的低风险替代方案（第 4 节） |
| R2 | 锚点取可见文字区右缘，还是 `wrap_width` 右缘 | Root | 推荐可见文字区右缘，并始终预留滚动条宽度 |
| R3 | 智能体的非对话行（工具、审批、停止等）是否需要单独样式 | Root，必要时问所有者 | 第一片保持靠左、占满列宽 |
| R4 | 是否在本片给 `shown_agent_` 补上语言与 `unit` 键（第 2.6 节） | Root | 至少补 `unit`。语言键先用测试确认问题是否存在，再决定 |
| R5 | 用户块上下内边距与块间距 | Root，必要时问所有者 | 需要不等行高，留给方案 E |

## 9. 限制

- 只读了第 1–2 节列出的源码片段，没有构建，也没有运行任何测试、应用或截图。第 2.6 节的 30 px 是根据测试中的界限式推算的，不是测量值。
- Synthrix 的数值转引自对照文档，本次没有重读 Synthrix 源码。
- 没有进行 AOCI 查询或写入。本任务是按需的只读调研，结论以基线源码为准。
- 基线的 `docs/planning/agent-collaboration.md` 中没有 119 号任务卡。本文的范围以 Root 的任务说明为准。
- 第 5 节的接口和函数名都是草案，最终的名称、所在位置和测试细节由实现者与 Root 确定。
