# 下一片验收提案：键盘撰写、明确发送并看到落点

2026-11-13 起草，基线 STK `13d32015`（Root 已于 19:19 UTC 推送到远端 main）。上位设计见[统一研究工作台](unified-workbench.md)和[统一首页跨端验收矩阵](unified-home-acceptance.md)。

Root 采用了主操作快捷键、发送后的 Web 输入焦点和原生会话 Esc 保留草稿。原生项目问答按快捷键完成准备，后续发送仍由用户单独激活，准备完成时保留输入区焦点。Web 与原生智能体会话在明确发送后恢复正文跟随。本文保留 Claude 在基线上的调查和验收建议，实际验证见[验收记录](../runtime-validation.md)。

共用导航、会话详情面板、逐级返回与文件预览已在两端接通。下一处高频阻力是继续追问：在已有会话里写下一句、明确发送、看到自己的消息和回复。本片只处理这一个循环，不改变发送权限和模型选择。

## 1. 比较基线

**Synthrix `caec2b9`。** 只从已发布提交读取已跟踪的源码和文档，未运行应用。`/home` 经 `ChatWorkspaceRoute` 默认挂载 `ConversationWorkspace`。带成本闸门的 `Composer` 只在旧的 `view=research` 路径使用，不作为参照。其主页说明自述“实机验证尚未全部完成”。下表中 Synthrix 一栏均为读源码所得。

**STK 当前回执。** [验收记录](../runtime-validation.md) 19:18 UTC 一节：上一远端 `19998d12` 的 Desktop 六项作业中五项通过，macOS 窄窗会话两项和必测视频失败。Runtime 13/13。`13d32015` 已包含窄窗历史夹具修正 `3ebbb4cd` 和聚焦智能体会话简化 `e2fd284c`，新头的目标平台 CI 待跑。

| 行为 | Synthrix 参照 | STK Web（`13d32015`） | STK 原生（`13d32015`） |
| --- | --- | --- | --- |
| 键盘发送 | 默认 Enter 发送，用户设置可改为 Ctrl/⌘+Enter，Shift+Enter 换行 | 无快捷键。Enter 换行，有用例断言。从输入框按 Tab 到「发送」再按 Enter，共 2 键 | 多行输入区中 Enter 换行，Tab 插入四个空格。需按 Ctrl+Tab 提交编辑并移到按钮，再按 Enter，共 2 键且不易发现。Ctrl+Enter 只结束编辑，因为两个会话输入区都没有设置 `on_submit` |
| 输入法 | 组字（`isComposing` 或 keyCode 229）时不发送 | 不涉及（无快捷键） | 引擎在组字时先由输入法处理按键（`context.cc:855`） |
| 发送后焦点 | 键盘发送时焦点本来就在输入框。点击发送后的焦点未核实 | 草稿清空后「发送」随即禁用，焦点落在禁用按钮上，留下空白焦点 | 未核实 |
| 发送后的正文 | 距末尾 64 px 内时跟随新内容，向上滚动、PageUp 或 Home 停止跟随，并显示「回到最新消息」 | 不跟随。已保存会话首次打开时在顶部，新消息和回复落在可视区外，需手动滚动 | 日志视图跟随末尾，上滚后显示「跟随最新」。智能体时间线没有传入自有位置，上滚后再发送不会恢复跟随 |
| 编辑中按 Esc | 关闭输入区弹层 | 不影响输入框 | 取消本次编辑。未失焦前输入的文字不写回草稿（见第 5 节 N4） |

以上 STK 基线由源码推得，均未在实窗中测量。

## 2. 提案 C1

1. **主修饰键加 Enter 触发可见的主操作。** 在 Linux 和 Windows 上为 Ctrl+Enter，macOS 上为 ⌘+Enter（原生 `primary_mod()`）。启用条件与对应按钮完全一致：
   - Web：「发送」。
   - 原生智能体会话：「开始」或「发送」（`ai_agent_send`）。
   - 原生项目问答：只触发「准备问题（不发送）」。「发送这条已保存的问题」仍需单独激活，可以点击，也可以在聚焦后按 Enter 或 Space。

   Enter 和 Shift+Enter 继续换行。组字期间或按键重复时，快捷键不触发。按钮禁用时为零动作，原因文字不变。本提案不采用 Synthrix 的 Enter 发送，因为两端都有断言 Enter 换行的用例。

   STK 中 Ctrl/⌘+Enter 现有两种含义：[Python 运行](../scripting.md)用它执行，[报告要求](../project-reports.md)只用它完成编辑。两个 AI 输入区目前和报告要求一样，只结束编辑。C1 会把它们改为触发动作。快捷键的选择和这项语义变化需由 Root 或所有者确认。
2. **焦点留在输入区。** 发送后，Web 把焦点放回输入框。原生结束编辑后，焦点预期仍在输入区，继续打字会重新开始编辑。这一点依据 UI 核心已有的“在已聚焦字段上打字即开始编辑”行为，尚未在 AI 输入区核实。项目问答准备成功且「发送这条已保存的问题」可用时，可把焦点移到该按钮。这一点由 Root 决定，见第 5 节 N3。
3. **明确发送后正文跟随。** 用户自己的明确发送让当前会话恢复跟随：先显示刚发出的消息，回复到达后显示其末尾。阅读者向上滚动、按 PageUp 或 Home 后停止跟随。点击「跟随最新」一次，或聚焦后按 Enter，回到末尾并恢复跟随。切换会话时仍恢复各自保存的阅读位置。后台读取历史、其他会话的迟到回复都不移动当前正文。
   - Web 首次打开仍从顶部开始。「跟随最新」只在这一会话中本页明确发送过、且阅读者随后离开末尾时出现，首次打开和普通阅读不出现。所以「the composer can return keyboard focus to the saved transcript」中从输入框按 Shift+Tab 到正文的规则保持不变。只有该控件可见时，Shift+Tab 先到达它，这是对现有规则的有意修改。
   - 该控件叠放在正文区域内，不改变输入框和「发送」的位置。「conversation column keeps its composer visible while the transcript scrolls」断言了这两个位置。
   - 原生沿用 `ui.log.follow` 的名称和行为：日志视图从末尾开始，离开末尾即显示该控件。两端起始位置不同，这一差异保留。
4. **原生会话输入区的 Esc 保留文字。** 编辑中按 Esc 结束编辑，已输入的文字写回草稿。下一次 Esc 按现有行为关闭面板或历史菜单。表格和其他字段仍保持“取消”的语义。

本片不包括下列能力：↑ 找回上一条输入、Tab 采用推荐问题、回复计时与「查看回复」、发送快捷键偏好、Web 停止回复。原因见第 4 节。

## 3. 实现入口（`13d32015`）

**Web**

- [main.tsx:883-889](../../web/src/main.tsx#L883) 中的 `textarea#chat-input`：增加 `onKeyDown`。条件为 Enter 加 `ctrlKey` 或 `metaKey`，同时不按 Shift 和 Alt，不是按键重复（`!repeat`），不在组字中（`!nativeEvent.isComposing` 且 `keyCode!==229`）。满足条件时阻止默认行为，并且只在 `conv.canSend` 为真时调用 `conv.send()`。不要直接调用 `form.requestSubmit()`：它不检查按钮的 `disabled`。重复提交仍由 [conversations.ts](../../web/src/conversations.ts) 中 `post()` 的 `inflight` 拦截。
- 发送后焦点：在同一表单的 `onSubmit` 中执行 `composer.current?.focus({preventScroll:true})`。
- 跟随：[main.tsx:187-193](../../web/src/main.tsx#L187) 已有 `messageList` 与按会话保存的 `transcriptOffsets`。正文容器在 [main.tsx:869](../../web/src/main.tsx#L869)。
  - 按会话 ID 记录“跟随”状态，只在本页明确发送时置位。
  - 在 `thread.messages.length` 或 `pending` 变化后，若当前会话处于跟随状态，就滚到末尾。
  - 滚动和按键监听负责清除跟随状态。
  - 「跟随最新」叠放在正文区域底部，不参与正文与输入框之间的布局。Tab 顺序在正文之后、输入框之前。样式使用 [style.css](../../web/src/style.css) 中 `.messages` 现有的变量。
  - 第 191 行切换会话时恢复位置的效果保持优先。

**原生**（[ai_editor.cc](../../desktop/engine/lib/stk_app/src/editors/ai_editor.cc)）

- 项目问答：在第 1318 行的 `text_area("ai_question/"+handle, …)` 上设置 `.on_submit`，与第 1334 行的 `ai_prepare` 共用同一个动作。`on_submit` 绕过按钮的 `.disable(...)`，所以第 1362-1365 行的全部条件要提成一个函数，由按钮和快捷键共同判断。
- 智能体会话：第 1765 行的 `text_area("ai_agent_text/"+handle, …)` 同样设置 `.on_submit`，与第 1772-1783 行的 `ai_agent_send` 共用动作和条件。动作内要保留项目句柄、会话、`selected_agent_loaded` 和运行目标 `matches(...)` 的复核。
- 跟随：给第 1690 行的 `log_view("ai_agent_timeline", …)` 传入按项目句柄和会话保存的 `LogViewPosition`。明确发送成功后把 `follow` 置为真。项目问答第 1223 行已使用 `transcript_position(id)`，新请求是否从跟随状态开始，需由用例确认。
- Esc：在 [ui.hh:255-263](../../desktop/engine/lib/stk_ui/include/stk/ui/ui.hh#L255) 的 `TextFieldOptions` 中加一个只对会话输入区开启的选项。[context.cc:903-905](../../desktop/engine/lib/stk_ui/src/core/context.cc#L903) 的 `Key::Escape` 在该选项开启时改为调用 `commit_edit()`。
- 不需要新增文案键。若给按钮增加快捷键提示，需在 `en.json` 和 `zh_CN.json` 中同时添加，两份目录按键数校验。

## 4. 身份差异与需要契约的跨端一致性

| 对象 | 身份与权限 | 草稿 | 发送 |
| --- | --- | --- | --- |
| Web 会话 | 当前已配对 Hub 的会话 ID，权限随客户端配对 | 同一页面内按会话 ID 保留 | `POST /api/v1/sessions/{id}/messages` 同步返回回复（见 [Hub](../hub.md#路由)） |
| 原生项目问答 | 本地项目句柄加请求 ID、上下文 ID 与 `source_revision` | `ai_question/<handle>` | 每次一问。先 `project.requests.create` 准备，再明确发送 |
| 原生智能体会话 | 项目内的会话 ID 与事件链摘要 | `ai_agent_text/<handle>` | `project.agent.say`（[Bridge v1](../specs/stk-desktop-bridge-v1.md)） |

C1 只改变客户端呈现，不合并三类身份，也不新增或改变 Bridge 或 Hub 的调用。下列一致性需要先定契约：

- **Web 回复进行中与停止。** Hub 发送为同步请求，没有进度事件或取消路由。原生有临时回复流和取消。
- **原生项目问答多轮追问。** `project.requests.create` 只有一个 `message_id`，没有线程或上一轮字段。界面文案也说明不附带其他问答。
- **↑ 找回上一条输入。** 需要先定作用域：Synthrix 按账户加会话。在 STK 中，要决定 Hub 配对和本地项目各自如何划分，以及是否保存历史输入。
- **发送快捷键偏好。** 两端没有共享的用户偏好契约，C1 固定为 Ctrl/⌘+Enter。
- **跨端统一会话列表。** Synthrix 由服务端合并研究和协作记录。STK 的 Hub 会话与本地项目请求之间没有共同列表。

## 5. 固定起点与检查

计数沿用[统一首页矩阵](unified-home-acceptance.md)第 1 节，另加一条：**键盘检查计入从输入区聚焦且已有草稿起、到动作被接受为止的全部按键**，包括 Tab、Ctrl+Tab 和 Shift+Tab。录入草稿本身不计。

**起点**

- **Web**：中文 Chromium，1440×900 与 390×844，缩放 1，已配对模拟 Hub。已保存会话 A 有 36 条消息，正文高于视口，首次打开时位于顶部。输入框已聚焦，草稿为「核对第 37 个网格」。会话 B 另有草稿和阅读位置。
- **原生**：Linux X11，英文 1600×1100 与中文 680×1000，缩放 1，已打开合成项目的聚焦工作台，Bridge 就绪。
  - K1：智能体会话 A 已读取、可发送，`allow_prepare` 关闭，时间线已上滚离开末尾，输入区正在编辑草稿。
  - K2：项目问答已捕获数据范围、选定夹具模型，输入区正在编辑问题。

两端每项都验证零任务提交、零项目修订变化（智能体会话本身保存的事件除外）、Viewer 相机与选中任务不变。测试中 `STK_TOKEN_PLAN_API_KEY` 置空，`STK_TOKEN_PLAN_MODEL` 不设置。

每一行都在宽窗和窄窗两个起点执行。目前没有任何用例按过这个快捷键，而 `on_submit` 不受按钮 `.disable(...)` 约束，所以每一行都需要新用例。「相邻回归」列出同一条件下按钮路径的现有用例，新用例应沿用其夹具和判据。

| ID | 端 | 检查 | 基线（源码推得，未实测） | 目标 | 相邻回归 |
| --- | --- | --- | --- | --- | --- |
| W0 | Web | 指针发送 | 点击「发送」1 次。焦点落在禁用按钮上，正文停在顶部 | 点击 1 次。焦点在已清空的输入框，落点同 W3 | 「only 发送 writes; a failed send keeps the draft…」 |
| W1 | Web | 键盘发送 | Tab、Enter 共 2 键，发送后焦点失落 | Ctrl+Enter 1 键。`hub.messages` 恰好 +1，焦点在已清空的输入框 | — |
| W2 | Web | Enter、Shift+Enter、组字中按 Ctrl+Enter、按住重复 | Enter 换行，零 POST | 均为零 POST，文字保留 | Enter 换行由「conversation column keeps its composer visible while the transcript scrolls」断言（`sent.seen` 为空）。组字需用 `dispatchEvent` 构造 `isComposing` |
| W3 | Web | 从顶部发送后的落点 | `scrollTop` 停在顶部，至少需 1 次滚动 | 零滚动。发送中的消息位于正文框内，回复后与末尾相差 ≤1 px。输入框和「发送」位置不变 | 末尾判据见「the composer can return keyboard focus to the saved transcript」，位置判据见上一行所引用例 |
| W4 | Web | 回复挂起时上滚 520 px | 无跟随控件 | 释放后位置不变，出现「跟随最新」。点击 1 次，或 Shift+Tab、Enter 共 2 键，回到末尾 | 用 `hub.holdNext('send')` 挂起 |
| W5 | Web | A 发送挂起时切到 B（宽 1 次，窄 2 次），再释放 | — | B 位置不变，回到 A 时恢复离开时的位置 | 「delayed reads and a late send stay with their own conversation」「history restores each conversation reading position」 |
| W6 | Web | 空草稿、超长、失败待重试、发送中时按 Ctrl+Enter | — | 零 POST，提示不变 | 「only 发送 writes…」「one draft is sent once even when it is submitted twice at once」「an oversized draft remains editable before any send」 |
| N0 | 原生 K1/K2 | 指针发送或准备 | 点击「发送」或「准备问题（不发送）」1 次。焦点未核实，时间线已上滚时停在原处 | 点击 1 次。焦点在输入区，时间线落点同 N2 | `AgentPython.ARunningSessionCanBeCancelledAndItsDraftsWait`、`ProjectPython.AIWorkspaceFirstTypedQuestionPreparesOnceWithoutSending` |
| N1 | 原生 K1 | 键盘发送 | Ctrl+Tab、Enter 共 2 键 | Ctrl+Enter 1 键。恰好一次 `project.agent.say`，回执后输入框清空 | 同 N0 智能体用例 |
| N2 | 原生 K1 | 发送后的时间线 | 已上滚时不恢复跟随 | 发送后在末尾。挂起期间上滚后出现「跟随最新」，点击 1 次回到末尾 | `LogView.FollowsTailUntilScrolledUp`、`LogView.OwnedPositionFollowsNewLinesUntilScrolled` |
| N3 | 原生 K2 | 键盘准备 | Ctrl+Tab、Enter 共 2 键 | Ctrl+Enter 1 键准备，恰好一个 pending 请求，`executor_id` 为空，零发送。若采纳焦点移动，再按 Enter 1 键明确发送，否则仍点击 1 次 | 同 N0 项目问答用例 |
| N4 | 原生 K1/K2 | 编辑中按 Esc | 推断会丢失本次编辑的文字 | 退出编辑后草稿保留，零请求，再按一次 Esc 才关闭面板 | 先补一个失败用例确认基线。证据为 `TextArea` 的 Esc 断言（`test_events.cc:204`）和 `AIWorkspaceFirstTypedQuestionPreparesOnceWithoutSending` 中失焦前绑定为空的断言 |
| N5 | 原生 | 组字中、无数据范围、模型不可用、会话运行中或未读取 | — | 快捷键零动作，原因文字保留 | 组字只有源码依据（`context.cc:855`），现有 `TextArea` 用例在提交组字后才按 Ctrl+Enter。其余条件见 `SavedConversationNavigationPython.UnreadAgentSessionCannotSendOrSetATarget`、`WorkspaceNavigationPython.FocusedConversationKeepsDataAndModelControlsOnDemand` |
| N6 | 原生 | 切换项目后旧快捷键回调、多区域、两类草稿 | — | 零动作，草稿各自保留 | `ProjectPython.AIWorkspaceActiveDraftAndStaleButtonsStayWithTheirProject`、`ProjectPython.AIWorkspaceMultipleAreasShareTheDisplayedRequestIdentity`、`SavedConversationNavigationPython.AgentHistorySeparatesIdentitiesAndKeepsBothDrafts` |

Web 用例在 [workbench-navigation.spec.ts](../../web/tests/workbench-navigation.spec.ts) 中按标题引用。统一首页矩阵中的 W 行号已随文件增长而失效。原生用例分布在 `desktop/tests/app/{project_test,workspace_navigation_test,project_agent_runs_test}.cc` 与 `desktop/tests/ui/test_events.cc`。实窗按上述起点回放 W1、W3、N1、N3，由 Root 记入[验收记录](../runtime-validation.md)。

## 6. 尚未验证

- 本文只读源码和文档，未构建、未运行任何测试或窗口。所有基线次数都是在 `13d32015` 上由源码推得，未实测。N4 尚未在 AI 输入区复现。
- Synthrix 行为只读源码，未在运行中的应用里核对。
- 以下相邻回归只按标题引用，未逐条阅读断言：Web 的「delayed reads…」「history restores…」「an oversized draft…」，以及 N5、N6 所列原生用例。已读断言的有：Web 的「conversation column…」「the composer can return…」「only 发送 writes…」「one draft is sent once…」，原生的 `AgentPython.ARunningSessionCanBeCancelledAndItsDraftsWait`、`AIWorkspaceFirstTypedQuestionPreparesOnceWithoutSending` 和两个 `LogView` 用例。
- 尚未核对：原生快捷键在按键重复时的表现、`on_submit` 之后的焦点、macOS ⌘ 映射与 Windows 行为、Web 真实输入法组字。
- 新头的 macOS 窄窗会话用例和 Windows 结果仍待 Desktop CI。
