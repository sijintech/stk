# 统一首页跨端验收矩阵

2026-11-13 起草，基线 STK `6ed5e920`。上位设计见[统一研究工作台](unified-workbench.md)，结果来源与权限沿用[跨端验收方案](distributed-workbench-acceptance.md)。行为参照 Synthrix `caec2b9` 的主页面与会话融合说明。首页直接显示会话，历史、搜索与新对话共用一处，专业页通过来源返回原会话和原位置。

「现有覆盖」指已有自动化用例或实窗证据。「计划」中的次数是待实测目标。本轮执行结果见[验收记录](../runtime-validation.md)。

## 1. 固定起点

| 端 | 宽窗 | 窄窗 | 必需上下文 |
| --- | --- | --- | --- |
| Web | 中文 Chromium 1440×900，缩放 1 | 中文 Chromium 390×844，缩放 1 | 本标签页已配对，Hub 可达 |
| 原生 | Linux X11 英文 1600×1100，缩放 1 | Linux X11 中文 680×1000，缩放 1 | 已打开本地项目，Bridge 就绪 |

| 起点 | 内容 |
| --- | --- |
| S0 | 缺少必需上下文。Web 为未配对或 Hub 断开，原生为未打开项目 |
| S1 | 具备上下文，零条已保存会话或问答 |
| S2 | 两条已保存会话 A、B，当前会话有未发送草稿。原生另有分栏布局，Viewer 与 Jobs 同区 |
| S3 | S2 加上任务页已选成功任务和未提交表单，结果页已显示文件且相机已移动 |

计数规则如下。一次指针点击或一次激活键（Enter、Space、Esc）计一次。窄窗先打开「历史」计入次数。等待、滚动和窗口尺寸变化不计。

## 2. 零副作用计数

每行结束时以下计数均为零或保持不变。原生「准备问题（不发送）」与「发送这条已保存的问题」只由用户明确触发，本矩阵每行的准备和发送次数均为 0。

| 计数 | Web 测试中的读数 | 原生测试中的读数 |
| --- | --- | --- |
| 任务提交与节点写入 | `posts(page).seen` 只含该行预期的只读动作 | `jobs.submission()` 为假，选中任务不变 |
| 模型发送 | `hub.messages`、`hub.replies` 为空 | `discussion.exchange_id()` 不变，`forbid_question_preparation` 存在时无准备 |
| 会话或项目写入 | `hub.saved.size` 不变 | `project()->revision` 不变 |
| 被动读取 | `hub.calls` 等于预期的 `history <id>` 序列 | `history_reads` 行数等于预期 |
| 画面与草稿 | `work(page)` 前后相等，画布截图一致 | `viewer().camera_serial()` 不变，`ai_question/<handle>` 草稿不变 |

## 3. 矩阵

测试引用缩写如下。W 加行号指 [web/tests/workbench-navigation.spec.ts](../../web/tests/workbench-navigation.spec.ts) 中的用例起始行。原生用例写作 `Suite.Name`，文件为 [workspace_navigation_test.cc](../../desktop/tests/app/workspace_navigation_test.cc)、[jobs_layout_test.cc](../../desktop/tests/app/jobs_layout_test.cc)、[jobs_state_test.cc](../../desktop/tests/app/jobs_state_test.cc) 和 [work_mode_layout_test.cc](../../desktop/tests/app/work_mode_layout_test.cc)。Web 用例使用模拟 Hub，原生用例使用桥接测试替身，均为自动化覆盖。实窗证据另列。

### H1 首页，缺少必需上下文（S0）

| 端 | 操作与次数 | 恢复与焦点 | 覆盖 |
| --- | --- | --- | --- |
| Web 断开 | 打开地址 0 次即为「工作台」。「任务」1 次，显示「控制服务未连接」，「新建」禁用 | 页头显示「连接中断 · 显示最近状态」。Hub 恢复后明确「刷新」列出节点，仍未选择节点 | 现有。`start()` 对每个起点断言工作台为当前页。[W875](../../web/tests/workbench-navigation.spec.ts#L875) 宽窄各记录 3 次点击、零写入 |
| Web 未配对 | 目标 0 次即见「一次性配对码」，配对前零会话读取 | 配对后进入「工作台」 | 部分。[W5474](../../web/tests/workbench-navigation.spec.ts#L5474) 只在默认视口覆盖断开后的配对表单。新标签首屏宽窄待实测 |
| 原生首启 | 无保存布局时 0 次进入工作台。未打开项目时从「项目位置」1 次进入项目操作 | 已有布局按保存的分栏或聚焦页恢复 | 已有首次启动的 X11 证据，见[验收记录](../runtime-validation.md)「双端左栏、首次启动与只读会话历史」 |
| 原生分栏 | 工作区页「选择运行环境」1 次进入任务，「查看器」1 次恢复分栏 | 原有标签与分栏编辑器保留 | 现有。`WorkspaceNavigation.EmptyWorkspaceHasOnlyProjectManagementAndSurvivesShellClosure`，`WorkspaceNavigation.GuidedWorkspaceRemainsAvailableAndOpensJobsAndViewerWithoutAProject` |

### H2 首页，具备上下文、无已保存会话（S1）

| 端 | 操作与次数 | 恢复与焦点 | 覆盖 |
| --- | --- | --- | --- |
| Web | 0 次即见「新对话 · 未保存」、「从一个科学问题开始」和输入框 | 输入框可编辑。已有会话从历史打开，输入框移到正文下方 | 宽窄窗覆盖居中的新会话和打开已保存会话，见[会话布局用例](../../web/tests/workbench-navigation.spec.ts#L1800)。零条已保存记录另作为验收起点 |
| 原生 | `open_workbench` 后 0 次即见问题输入框和「准备问题（不发送）」，无正文与历史列表。数据范围与模型面板开、关各 1 次。窄窗「结果」后「工作台」1 次 | 草稿保留，数据范围仍为空 | 现有。`WorkspaceNavigationPython.FocusedConversationKeepsDataAndModelControlsOnDemand` 断言 `context()` 为空、`exchange_id()` 为空、`revision` 为 0 |

### H3 已保存会话（S2）

| 端 | 操作与次数 | 恢复与焦点 | 覆盖 |
| --- | --- | --- | --- |
| Web 打开 | 历史条目宽 1 次，窄 2 次（历史、条目）。「新对话」宽 1 次，窄 2 次 | 当前条目 `aria-current`，各会话分别保留草稿。新对话聚焦输入框 | 现有。[W1920](../../web/tests/workbench-navigation.spec.ts#L1920) `hub.calls` 只含一次 `history A`，`work(page)` 不变 |
| Web 阅读位置 | 在 A、B 间切换各 1 次（窄 2 次） | 每个会话恢复正文滚动位置 | 现有。[W2173](../../web/tests/workbench-navigation.spec.ts#L2173) |
| Web 键盘 | 宽窗历史条目 Enter 1 次。窄窗历史入口 Enter 1 次、条目 Enter 1 次。Esc 1 次关闭 | 键盘打开后焦点进入正文，指针选择焦点留在历史栏。窄窗菜单遮挡下方页面，Esc 后焦点回到历史入口。输入框 Shift+Tab 回到正文 | 现有。[W2908](../../web/tests/workbench-navigation.spec.ts#L2908)，[W2805](../../web/tests/workbench-navigation.spec.ts#L2805)，[W2886](../../web/tests/workbench-navigation.spec.ts#L2886)，[W2250](../../web/tests/workbench-navigation.spec.ts#L2250) |
| Web 刷新 | 刷新同一标签 0 次即恢复已保存会话 | 会话名与正文恢复 | 现有。[W2082](../../web/tests/workbench-navigation.spec.ts#L2082) 的 saved 分支 |
| 原生打开 | 从任务页侧栏近期问答宽 1 次，窄窗「历史」后条目共 2 次 | 回到同一聚焦实例，草稿与数据范围不变，结果页相机序号不变 | 现有。`SavedConversationNavigationPython.RecentQuestionsOpenFromTasksAndResultsAtBothWidths` |
| 原生写问题 | 「写问题」1 次。返回已选问答 1 次 | 复用当前草稿并聚焦输入框，返回后保留阅读位置，焦点回到正文。首次访问不读历史 | 现有。`SavedConversationNavigationPython.WriteQuestionFocusesTheExistingDraftFromTasksAndResults`，`SavedConversationNavigationPython.WriteQuestionDoesNotOpenSavedHistoryOnFirstVisit` |
| 原生历史 | 「已保存问答」1 次打开完整列表，归档筛选 1 次 | 浏览时不选中、不写入。窄窗历史菜单打开时 Viewer 不接收输入 | 现有。`SavedConversationNavigationPython.BrowseSavedQuestionsBeyondTheRecentRailWithoutSelectingOrWriting`，`SavedConversationNavigationPython.RecentQuestionsRestoreTheScrolledTranscript`，`SavedConversationNavigationPython.OpenCompactHistoryIsolatesViewerInputUntilDismissed`，`SavedConversationNavigationPython.AgentHistorySeparatesIdentitiesAndKeepsBothDrafts` |
| 实窗 | 两端四种窗口按上列次数重放 | 同上 | 计划，待实测 |

### H4 从任务或结果打开情境详情再返回（S3）

| 端 | 操作与次数 | 恢复与焦点 | 覆盖 |
| --- | --- | --- | --- |
| Web 结果 | 「在查看器中打开」或「读取日志」1 次，「任务」1 次。键盘为 2 次按键 | 去程焦点在目标控件，返程焦点回到原入口。任务、结果与图谱实例保留 | 现有。[W4392](../../web/tests/workbench-navigation.spec.ts#L4392) 记录指针 2 次或按键 2 次，`posts` 只含一次 `task.artifacts` 或 `task.logs` |
| Web 来源 | 「来源」1 次展开，「收起」或 Esc 1 次 | 焦点回到「来源」，结果布局与 `state(page)` 不变 | 现有。[W1495](../../web/tests/workbench-navigation.spec.ts#L1495) |
| Web 日志流 | 「读取日志」1 次后「标准错误」1 次 | Viewer、草稿与返回焦点保留 | 现有。[W3895](../../web/tests/workbench-navigation.spec.ts#L3895) |
| Web 回首页 | 从结果「工作台」1 次 | 会话草稿保留，焦点留在一级导航。迟到回复不移动任务和结果 | 现有。[W4460](../../web/tests/workbench-navigation.spec.ts#L4460)，[W2284](../../web/tests/workbench-navigation.spec.ts#L2284)，[W2727](../../web/tests/workbench-navigation.spec.ts#L2727) |
| 原生结果 | 「在查看器中打开」1 次，「任务」1 次 | 同一编辑器实例、外层滚动与原入口焦点，选中任务和表单草稿保留，零提交。多个任务标签时回到发起标签。重访保留已显示画面 | 现有。`JobsLayout.FocusedTaskResultReturnKeepsSameAreaScrollAndLauncher`，`JobsLayout.TaskResultReturnsToItsLauncherWhenAnotherJobsEditorIsActive`，`JobsLayout.RevisitingAnAcceptedTaskKeepsTheDisplayedResult`，`JobsLayout.OpeningATaskResultKeepsTheFocusedWorkbench`，`JobsFake.SoleVtiOfTheAcceptedListOpensThatExactFileWithTheSlicePreset` |
| 原生来源 | 「来源」1 次 | 长标签换行可滚动，焦点留在「来源」 | 现有。`JobsLayout.FocusedResultSourceWrapsAndScrollsLongLocalLabels` |
| 原生文件与文献 | 打开「文件」页。聚焦问答「打开文献库」1 次，「工作台」1 次 | 文件索引不编辑、不改选中。返回同一问答，草稿与阅读位置保留 | 现有。`WorkspaceNavigationPython.FilesShowsExistingIndexWithoutEditingOrChangingSelection`，`FocusedLiteraturePython.OneClickEachWayKeepsTheQuestionDraftAndReadingPositionAtBothWidths` |
| 原生分栏 | 「分栏」1 次，「工作台」1 次。「项目概览」1 次 | 恢复原会话实例、草稿和分栏编辑器 | 现有。`WorkspaceNavigation.FocusedSectionsReuseEditorsAndRestoreTheSplitView`，`WorkspaceNavigation.SavedFocusedWorkbenchAndOrdinaryMaximizationRestoreSeparately`，`WorkspaceNavigationPython.FocusedOverviewAndWorkbenchNameDifferentDestinations`，`WorkModeLayoutClicks.TwoClicksSwitchEachModeWithoutRunningOrSending` |
| 实窗 | 去程与返程各 1 次 | 同上 | 部分。Root 已在真实 Hub、NodeAgent、Runtime 与 X11 窗口回放任务结果来回，见 [handoff.md](../../handoff.md) 2026-11-11 各节。由首页 S2 起步的整条路线待实测 |

### H5 会话内的任务与文件详情（条件）

Web 从已保存会话的授权提交回执定位任务。原生从已消费的智能体运行卡片定位本地工作流。普通原生问答的公开契约没有任务或文件引用字段。 [统一研究工作台](unified-workbench.md) [原生会话来源](native-conversation-references.md)

| 端 | 目标操作与次数 | 恢复与焦点 | 零副作用 | 覆盖 |
| --- | --- | --- | --- | --- |
| Web | 已保存会话内 1 次打开关联任务、1 次查看文件，预览或下载另计 1 次 | 关闭后回到原会话、阅读位置和草稿，焦点回到引用入口 | 每一步各一次 GET、零 POST | 1440×900 和 390×844 Chromium、Hub、NodeAgent、Runtime 回放通过 |
| 原生 | 已显示运行卡片时，打开关联任务、查看文件、预览各 1 次。从工作台历史起步，宽窗 4 次、窄窗 5 次到预览 | 每一级返回原控件，关闭回到原卡片，分栏布局、Viewer 相机与草稿保留 | 工作流、清单、预览各一次只读请求，返回和关闭零请求，零智能体动作，`revision` 不变 | 1600×1100 和 680×1000 界面驱动与 Linux X11 实窗通过。下载待接入 |
| 文件读取恢复 | 从已失败的文件预览起步，两端均 1 次重试。Web 25 项清单在原文件行显示重试按钮 | 同一文件成功显示。返回原文件入口，Esc 回会话。Web 实窗核对未发送草稿 | 两次相同身份的文件读取，零模型请求和项目写入 | Chromium 接真实隔离 Hub 和受控节点，1440×900、390×844。Linux X11 1600×1100、680×1000 经真实 Bridge，分别注入一次失败。见[实测](../runtime-validation.md) |
| 原生客户端失效 | 详情打开时切换项目或会话、关闭后重新打开、卡片从当前会话消失 | 丢弃旧详情与迟到回执 | 丢弃零请求 | 桌面 Bridge 和界面回归通过 |
| 服务端拒绝 | 一次明确打开时，服务发现引用失效 | 显示不可用，留在原会话 | 一次只读请求，零写入 | Web 和原生拒绝回归通过 |

### H6 回归

| 情形 | 覆盖 |
| --- | --- |
| 同一已配对标签刷新后恢复运行环境 | 现有。[W5381](../../web/tests/workbench-navigation.spec.ts#L5381) |
| 宽窄切换时历史在左栏与顶部之间移动 | 现有。[W2771](../../web/tests/workbench-navigation.spec.ts#L2771)，[W2805](../../web/tests/workbench-navigation.spec.ts#L2805) |
| 迟到的读取与发送留在各自会话 | 现有。[W1954](../../web/tests/workbench-navigation.spec.ts#L1954)，[W2005](../../web/tests/workbench-navigation.spec.ts#L2005) |
| 旧保存布局与错误模式不替换编辑器 | 现有。`WorkModeLayouts.LayoutAndPortableWorkspaceRoundTripAndLegacyDefaults`，`WorkModeLayouts.BadSavedModeDoesNotReplaceEditorsLanguageOrWorkspace` |
| 返回会话保留未发送问题 | 现有。`WorkspaceNavigationPython.ReturningToConversationKeepsItsUnsentQuestion` |

## 4. 执行方式

- 环境变量 `STK_TOKEN_PLAN_API_KEY` 置空，`STK_TOKEN_PLAN_MODEL` 不设置。不连接线上端点，不运行或发送项目任务，不改变授权。
- Web 在 `web/` 执行 `npm run build`，再执行 `npx playwright test tests/workbench-navigation.spec.ts -g "<用例标题片段>"`。
- 原生在本 worktree 自己的构建目录编译 `stk-project-tests` 与 `stk-jobs-tests`，用 `--gtest_filter` 选择上文用例。
- 实窗只用合成数据。按 [AGENTS.md](../../AGENTS.md) 记录固定起点、实际次数与结果状态，记录写入由 Root 维护的 `docs/runtime-validation.md`。

## 5. 限制

- Web 未配对和零条已保存会话的宽窄窗起点，以及会话内引用，仍待按本矩阵专项验收。
