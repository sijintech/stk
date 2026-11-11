# 工作台中的文献来源入口与回程

2026-11-10，状态：**设计稿，未实现，未实测**。基线 STK `main` `16541e8f`。本文只依据已提交的源码和文档，未运行产品或测试。
上位设计见[统一研究工作台](unified-workbench.md)。文献能力以 [Local desktop literature service — `literature.*`](../specs/stk-desktop-literature-1.md)（下称文献协议）和[在桌面使用本地文献](../literature-desktop.md)（下称文献指南）为准。跨端边界沿用[分布式科研工作台：跨端场景验收方案](distributed-workbench-acceptance.md)的 M03 与「PDF 标注与文献边界」。

## 结论

- 一级导航保持**工作台、任务、结果**三项，文献不成为第四项。
- 首片只做桌面。当前聚焦问答已有已采纳的已保存问答时，页头提供「打开文献库」，打开现有文献编辑器；从分栏顶栏点「工作台」一次回到同一问答。
- 这个入口只是导航。问答目前没有文献引用身份，入口不定位引用，也不暗示回答有引用。
- 进入、回程、重开都是被动导航，不新增 literature RPC。文献页的「刷新」仍是用户明确触发的本机元数据读取，行为不变。
- 切到分栏会让其他已打开的 AI 标签重新绘制，可能推进它已武装但尚未发出的准备、发送或回退。有此风险时保留当前页，不切换。
- 无项目时，顶栏「文献」和工作区「其他 · 文献」沿原路径，不受首片影响。
- Web 不增加文献入口。

## 源码已支持的能力

| 能力 | 已支持的内容 | 证据 |
|---|---|---|
| 三项一级导航 | 聚焦工作区只有工作台、任务、结果三项，另有「分栏」和「历史」。宽度大于 700 逻辑像素时用左栏，否则用顶部横栏 | [shell.cc:812-823](../../desktop/engine/lib/stk_app/src/shell.cc#L812-L823)，[shell.cc:950-996](../../desktop/engine/lib/stk_app/src/shell.cc#L950-L996) |
| 无项目的文献入口 | 非聚焦时顶栏有「文献」等工具按钮，聚焦时隐藏；工作区「其他」也有「文献」。两者都不需要打开项目 | [shell.cc:1162-1181](../../desktop/engine/lib/stk_app/src/shell.cc#L1162-L1181)，[workspace_editor.cc:126-127](../../desktop/engine/lib/stk_app/src/editors/workspace_editor.cc#L126-L127)，[文献指南「进入文献页」](../literature-desktop.md#进入文献页) |
| 被动打开与明确刷新 | 打开、绘制或恢复文献页不发送 literature RPC；「刷新」发 `info`、`encoder.info`，并对当前文献库和每个选中范围各发一次 `corpora.info`（去重） | [文献协议 Native UI and validation](../specs/stk-desktop-literature-1.md#native-ui-and-validation)，[literature_editor.cc:236-243](../../desktop/engine/lib/stk_app/src/editors/literature_editor.cc#L236-L243) |
| 文献页隐藏后的状态 | 文献页被移出或被最大化区域遮住时挂起：保留表单文字，清除授权勾选、复核结果和页图，代次递增使迟到回执失效；后台操作不取消，也不自动接续。工作空间只保存 `section`、`query`、`corpus`、`scopes` | [literature_editor.cc:172-208](../../desktop/engine/lib/stk_app/src/editors/literature_editor.cc#L172-L208)，[文献指南「表单草稿与工作空间」](../literature-desktop.md#表单草稿与工作空间) |
| 切换前的发送安全检查 | 打开已保存问答前，对将被显露的每个 AI 编辑器调用 `saved_conversation_dispatch_safe`，任一不安全就不切换。AI 编辑器每次绘制都会调用 `advance_auto`，推进已武装的准备、发送和回退 | [shell.cc:359-371](../../desktop/engine/lib/stk_app/src/shell.cc#L359-L371)，[ai_editor.cc:656-707](../../desktop/engine/lib/stk_app/src/editors/ai_editor.cc#L656-L707)，[ai_editor.cc:1060](../../desktop/engine/lib/stk_app/src/editors/ai_editor.cc#L1060) |
| 概览回程先例 | `OverviewReturn` 记录原区域、AI 编辑器生命周期、项目打开句柄、可见代次和分栏活动。点「工作台」时这些都未变才回到原实例，否则按当前布局打开 | [shell.hh:287-294](../../desktop/engine/lib/stk_app/include/stk/app/shell.hh#L287-L294)，[shell.cc:465-487](../../desktop/engine/lib/stk_app/src/shell.cc#L465-L487)，[shell.cc:854-869](../../desktop/engine/lib/stk_app/src/shell.cc#L854-L869)，[shell.cc:912-926](../../desktop/engine/lib/stk_app/src/shell.cc#L912-L926) |
| 问答身份校验先例 | 问答页「保存建议供检查」等动作绑定项目打开句柄、`exchange_generation()` 和所选请求编号，任一变化即不执行 | [ai_editor.cc:1294-1299](../../desktop/engine/lib/stk_app/src/editors/ai_editor.cc#L1294-L1299)，[project_discussion.hh:100-108](../../desktop/engine/lib/stk_app/include/stk/app/project_discussion.hh#L100-L108) |
| 草稿与阅读位置 | 「写问题」复用当前项目草稿；项目打开期间每个 AI 标签保留最近 32 条已保存问答的阅读位置；主动切换分栏标签后按当前布局打开工作台 | [统一研究工作台「两端的目标结构」](unified-workbench.md#两端的目标结构) |
| 文献只在桌面 | 20 个 `literature.*` 方法都是 desktop-only（包括被动元数据），不进入脚本目录和 Agent 工具 | [文献协议](../specs/stk-desktop-literature-1.md)，[levels.py:268-277](../../suan/agent/levels.py#L268-L277) |
| 问答没有文献引用 | `citation` 只在文献编辑器、`literature_state`、`literature_page` 中出现；项目问答没有引用字段。Web 消息只有 `id`、`role`、`content`、`created` | [project_discussion.hh](../../desktop/engine/lib/stk_app/include/stk/app/project_discussion.hh)，[main.tsx:491](../../web/src/main.tsx#L491)，[conversations.ts](../../web/src/conversations.ts) |

## 现有路径与点击估计

只从代码推断，均未实测。起点：聚焦工作台的问答页，项目已打开，已选中一条已保存问答，输入框有草稿，缩放 1。

| 宽度 | 现有路径 | 进入 | 回程 | 回程结果 |
|---|---|---:|---:|---|
| 宽窗（如 1600×1000，左栏） | 「分栏」→ 顶栏「文献」；回程点顶栏「工作台」 | 2 | 1 | 点「文献」是主动切换分栏标签，按当前布局打开工作台，不保证回到原问答 |
| 宽窗，保存的分栏已含文献区 | 「分栏」 | 1 | 1 | 取决于保存的布局。[STK 0.1.0a1 验收记录](../runtime-validation.md)「聚焦工作台收起技术页头」的起点含文献/Python 区，只测了导航，未测文献回程 |
| 窄窗（如 680×900，横栏） | 「分栏」→ 顶栏「文献」 | 2 | 1 | 同宽窗；680 宽时顶栏按钮是否被裁切未验证 |
| 任一宽度，经项目概览 | 「项目概览」→ 工作区「其他 · 文献」 | 2（可能需滚动） | 1 | 同样切换了分栏标签，不保证回到原问答 |

首片目标：宽窄两种布局均为进入 1、回程 1，且回到同一问答。

## 引用身份的缺口

桌面文献的现有身份来自文献协议：`corpus_id`（`local_` 加 32 位十六进制）、`database_id`、`version_id`、文献库 `generation`，以及检索结果中的 `citation`。它们只在文献编辑器内流转。本文**不定义**新字段或协议。

**引用绑定与读取协议缺口。** 问答消息和已保存问答没有引用字段；没有从其他编辑器打开文献页并预设引用的接口，工作空间也不保存 `citation`；Hub 会话接口和 Web 没有文献方法。补齐时，实际跨越边界的接口须先版本化。Web 文献授权须遵守 M03：授权检查和引用可追溯，desktop-only 能力不经版本化不能暴露给 Web。

**RAG 待决事项。** 文献是否进入问答上下文由所有者决定；文献协议把 Privacy RAG 列为单独待办。这一决定不替代上面的协议工作。

在两者都完成前，标题、DOI、摘要、文件名或 SHA 相同都不能授予读取、匹配来源或迁移身份，也不能从正文推断来源。

**未来引用须保留的内容。** 若日后让问答携带引用，须原样保存冻结的 collection citation（`stk.literature-collection-citation/1`）和当时选中的 scopes；读取时由服务校验原始源字节、保留代次成员、版本及其当前授权，任一不符即拒绝（[collection.py:184-216](../../suan/literature/collection.py#L184-L216)，[文献协议 141–150 行](../specs/stk-desktop-literature-1.md)）。本文不指定须改哪些发布协议，只要求实际跨越边界的接口先版本化。

## 拟实现：最小切片（仅桌面）

**入口。** 聚焦问答页头「项目概览」旁增加「打开文献库」。只在当前聚焦问答有已采纳的已保存问答时出现：`exchange_id()` 非空且 `exchange_request()` 的 `id` 与之相同。准备中的新问题、空会话和无项目时不出现。不进一级导航、横栏或任务、结果页。

**动作。** 仿照 `focused_project_overview_action`，点击时校验原区域、AI 编辑器生命周期、可见代次和活动代次，然后在分栏中激活现有文献编辑器标签（没有就新建）。激活后记录回程，分栏活动取激活之后的值，使这次打开不算用户切换标签。

**发送安全。** 进入和回程都复用 `saved_conversation_dispatch_safe` 的策略（同 [shell.cc:359-371](../../desktop/engine/lib/stk_app/src/shell.cc#L359-L371)）：切换前检查将被显露的每个 AI 编辑器，任一有已武装但未发出的准备、发送或回退，就保留当前页并提示，不切换。已发出的请求照常完成，不取消。

**回程记录。** 在 `OverviewReturn` 原有字段之外，绑定：

- 当前项目打开句柄；
- 该次已采纳的选中问答请求编号；
- 其捕获上下文编号（`exchange_context()`）；
- 当时的 `exchange_generation()`。

点「工作台」时，原区域、编辑器生命周期、可见代次、分栏活动和上述四项都未变，才回到原 AI 实例和标签，草稿和阅读位置不变。任一项变化，包括另一窗口改选问答，或项目关闭后重开换了打开句柄，都按现有工作台导航处理：按当前布局打开，不选择旧问答，不新建问答，不写入项目。

**不做的事。** 不传引用，不预填检索，不自动刷新、检索、准备、发送或保存。Web 不改。

## 同一回程验收

宽窗（1600×1000 左栏）和窄窗（680×900 横栏）用同一起点、同一步骤。起点固定：语言、窗口大小、缩放 1、项目、选中问答编号、草稿文字、文献页分页与检索内容、Viewer 相机和时间步。

| 步骤 | 点击上限 | 结束状态 |
|---|---:|---|
| 问答 → 「打开文献库」 | 1 | 文献编辑器可见，表单文字与上次一致 |
| 文献 → 「工作台」 | 1 | 同一 AI 实例、同一问答、同一草稿和阅读位置；窄窗横栏仍只有三项导航加「分栏」和「历史」 |

计数口径：

- 进入和回程**新增**的 literature RPC、模型请求、准备、发送、任务提交和项目写入均为 0。
- 起点之前已在途的读取或后台回执（文献后台操作、问答跟随读取）不计为新增，但不被取消、不重复发起，也不渲染到已失效的视图。
- 若验收中点「刷新」，只计它原有的元数据读取：每次点击 `info`、`encoder.info` 各一次，加上当前文献库与选中范围去重后每库一次 `corpora.info`。
- Viewer 状态和隐藏草稿不变。

结果按 AGENTS 要求记入[STK 0.1.0a1 验收记录](../runtime-validation.md)。

## 反例（每条都应有回归测试）

| 类别 | 反例 | 期望结果 |
|---|---|---|
| 入口 | 无项目、空会话，或只有准备中尚未保存的问题 | 不显示「打开文献库」；无项目时顶栏和工作区「文献」照旧可用 |
| 来源身份 | 回答正文出现论文标题、DOI、文件名或页码 | 不生成引用按钮，入口文字不变 |
| 来源身份 | 另一文献库有标题、DOI、摘要或 SHA 相同的文献 | 不视为同一来源，不授予读取、不迁移身份（M03） |
| 权限 | 在文献页撤销某版本授权后回到问答，再进入 | 已清除的页图不重现；已撤权版本的页图不能再返回。新检索可以命中另一已授权版本，需重新「打开引用页」 |
| 权限 | 选中历史中的文献操作 | 不恢复授权或复核结果 |
| 权限 | Web 用户有 Hub 会话权限 | 不能因此读取文献元数据；Web 没有文献入口 |
| 过期回程 | 打开文献后关闭原 AI 标签、改动分栏，或可见代次改变 | 「工作台」按当前布局打开，不新建问答，草稿不丢 |
| 过期回程 | 打开文献后在另一窗口改选问答，使选中请求、捕获上下文或交换代次改变 | 按现有工作台导航处理，不选择旧问答，不写入 |
| 过期回程 | 打开文献后关闭项目再重开（打开句柄改变） | 同上；旧回程记录不生效 |
| 过期回程 | 隐藏文献页前，某个打开引用页的操作仍在进行 | 回到问答及再次进入时都不渲染迟到的页图 |
| 在途请求 | 问答回复仍在跟随时点「打开文献库」 | 只切换显示，不取消、不重复在途读取 |
| 发送安全 | 分栏中另有一个 AI 标签，其自动路由已武装准备、发送或回退但未发出；点「打开文献库」或「工作台」 | 保留当前页并提示，不切换，该标签不因重绘而准备、发送或回退；已发出的请求照常完成 |
| 发送安全 | 两分栏均有 AI 标签，均无已武装动作 | 正常进入和回程，新增准备、发送均为 0 |
| 被动导航 | 进入、回程、重开文献页 | 无新增网络请求、literature RPC 或模型请求；`STK_TOKEN_PLAN_*` 为空时相同 |
| 明确刷新 | 在文献页点「刷新」 | 只发出 `info`、`encoder.info` 和每个相关库的 `corpora.info`，不检索、不运行模型、不写项目 |
| 工具目录 | Agent 或脚本请求文献 | 仍按 `DESKTOP_ONLY` 拒绝，入口不改变工具目录 |

## 仍待验证或决定

- 尚未运行任何产品或测试。上述现有路径、点击估计、草稿与阅读位置保持都需要实窗证据，包括 680 宽时顶栏是否裁切，以及两分栏/另一 AI 标签的发送安全反例。
- macOS 和 Windows 上的文献页仍未验证（见[文献指南「当前范围与限制」](../literature-desktop.md#当前范围与限制)）。
- 引用绑定与读取协议、Web 文献授权版本、RAG 是否接入问答，以及任务、结果与文献的关联，都待所有者决定后另做版本化设计。
