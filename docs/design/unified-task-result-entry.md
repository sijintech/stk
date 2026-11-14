# 任务到结果的来源标识：两端对照与修正方案

2026-11-13 起草，基线 STK `385aa7f4`。桌面聚焦结果的来源名称已在本地 main `6abd4b71` 实现并通过 Linux 实窗验收。上位规则见[统一研究工作台](unified-workbench.md)，点击计数沿用[统一首页跨端验收矩阵](unified-home-acceptance.md) H4。Synthrix 主页面提供共同参照。用户能在专业页辨认当前来源，并经原入口回到原工作。

## 1. 审计范围

本次只审计一条路线：在「任务」中选中成功任务，打开结果，再回到原任务。文中源码行号以 `385aa7f4` 为准。

| 环节 | Web | 桌面聚焦工作台 |
| --- | --- | --- |
| 任务页入口 | 任务详情行有「读取日志」「在查看器中打开」「取消」，见 `web/src/main.tsx:877` | 任务面板行有「取消」「在查看器中打开」，见 `desktop/engine/lib/stk_app/src/editors/jobs_editor.cc:765-779`。任务列表名称取 `TaskRow::label()`，即任务名，无名时取 ID 前 12 位（`jobs_state.cc:236`） |
| 打开 | `openResults` 先切到「结果」，读取保留自己的范围校验（`main.tsx:639`） | `focused_task_result_action` 打开 Viewer，请求来自 `JobsState::selected_result_request`（`jobs_state.cc:2788`） |
| 结果页标题下的来源行 | `节点名 · 项目名 · 任务名`，接着是 `显示 <文件>` 或「尚未加载结果文件」。悬停提示列出节点、项目、任务和文件的 ID（`main.tsx:782-785`, `905-908`）。「来源」按钮在来源行右侧 | 「来源」按钮在左，其后是 `{kind}：{name}`（`viewer_editor.cc:226-259`, `zh_CN.json:984`）。`name` 取 `ViewerSource::label()`，`field_file` 非空时只给文件名，否则给 `<任务 ID> @ <连接 ID>`（`viewer_state.cc:186`, `1756-1766`） |
| 来源详情 | 节点、项目和任务三行都是先名称后 ID，另有显示的文件和切片（`main.tsx:812-822`） | 连接、节点（仅 Hub）、运行工作区和任务各行只有 ID，另有打开时的输入和已显示步号（`viewer_editor.cc:350-364`） |
| 返回 | 一级导航「任务」。来源仍一致时，焦点回到原入口（`main.tsx:661-672`） | 一级导航「任务」恢复同一编辑器、外层滚动和原入口焦点 |

## 2. 已对齐，不改

- 两端都可以一次点击「在查看器中打开」，一次点击「任务」返回。验证见 Web 用例 `Tasks 在查看器中打开 opens 结果 in one click…`（spec 547 行）和 `… then 任务 returns the focus to ${launcher}…`（4798 行），原生用例见 `JobsLayout.OpeningATaskResultKeepsTheFocusedWorkbench`、`JobsLayout.FocusedTaskResultReturnKeepsSameAreaScrollAndLauncher` 和 `JobsLayout.TaskResultReturnsToItsLauncherWhenAnotherJobsEditorIsActive`。
- 两端都有唯一有效 VTI 的一键切片，以及同一任务重访时保留的画面。验证见 Web 7057 行、`JobsFake.SoleVtiOfTheAcceptedListOpensThatExactFileWithTheSlicePreset` 和 `JobsLayout.RevisitingAnAcceptedTaskKeepsTheDisplayedResult`。2026-11-11 Root 在 X11 两窗实测各一次点击。
- 两端的「来源」都一次点击展开，Esc 收起。焦点回到按钮，画面不变。验证见 Web 1512 行和原生 `FocusedResultSourceWrapsAndScrollsLongLocalLabels`。
- 往返期间草稿、选中任务、Viewer 相机和步号保持不变，零提交、零模型请求。

## 3. 选定差异：结果页来源行不显示任务名

Web 的来源行显示节点、项目、任务名和已显示文件。桌面基线在 Linux X11 的 1600×1100 英文和 680×1000 中文窗口实测。已选合成任务为 `Signed VTI only result`，发布清单已到，Viewer 起初为空，新建任务表单有草稿。进入结果页后，桌面出现以下信息。

- 一键打开唯一 VTI 后，来源行显示 `任务: scalar-0.vti`，来源详情列出完整任务 ID。
- 普通任务请求的来源标签使用 `<任务 ID> @ <连接 ID>`。这一路径由 `test_viewer_state.cc` 的单元测试覆盖。
- 实窗各点击一次打开、返回与重访。先在 Viewer 中旋转画面，回到任务页时原任务行与草稿可见。重访像素与旋转后相同，整个路线只求值一次。 [基线验收](../runtime-validation.md)

**计数（目标对象：当前结果属于哪个已命名任务）。** Web 在结果页 0 次点击即可看到。桌面在结果页上看不到任务名，只能点一次「任务」回去，在列表中找选中行，再点一次「结果」回来，往返共 2 次。这是信息层级差异：Web 先显示名称，ID 放在提示和详情中。c7e04089 已对 Web 会话标题采用同一规则（名称显示在标题，ID 放在提示）。

**为何可做。** 名称来自 Jobs 已经读取的 `TaskRow::name`、`WorkspaceRow::name`、`ConnectionInfo::name` 和 Hub 的 `NodeRow::name`。修正只改显示，不增加请求、能力、持久化字段或发布契约，也不依赖[待决事项](../../handoff.md#三项待所有者决定)。

## 4. 实现

1. **修改位置**为 `viewer_editor.cc` 的 `draw_main` 来源行（226-259 行）。`ViewerSource::label()` 和 `m.label` 不改。原因有三：`label` 会作为 `source_label` 写入受键检查的工作区状态（`viewer_state.cc:2879`, `2904`），恢复用例也依赖它，`test_viewer_state.cc:550` 保持原断言。
2. **名称绑定。** 仅当以下条件同时成立时显示名称：
   - `source().kind == Task`；
   - Viewer 记录的 `task_scope_current` 仍返回真（即 `still_same_scope` 的连接代次、URL 和桥代次）；
   - Jobs 当前目标的连接、节点和工作区与 `source()` 相同，并且 `tasks()` 中有 `source().task_id`。

   条件不成立时沿用原来源标签。发起动作携带当时的名称与来源验证条件，`ViewerState::task_source_names` 在绘制前复核。队列内改选另一任务后，画面仍引用原任务，名称取原任务的行。恢复的布局、冻结画面及连接范围变更时显示原标签。
3. **文字与顺序。** 新增 i18n 键：
   - `viewer.source.task_named`：中文为 `{location} · {workspace} · {task}`，英文与之对应。
   - `viewer.source.task_shown`：中文为 `显示 {file}`，仅在 `field_file` 非空时追加。

   `location` 在 Hub 中取节点名，其他情况取连接显示名。任一名称为空时，该段回退为 ID，任务名回退沿用 `TaskRow::label()` 的规则。步号后缀照旧。悬停提示改为逐行列出连接、节点、工作区和任务的 ID 及文件路径，与 Web 的 `sourceIds` 对应。非任务来源的 `{kind}：{name}` 不变。
4. **来源详情。** 满足同一绑定条件时，连接、节点、运行工作区和任务各行按 Web 的方式显示「名称 + ID」，ID 仍可完整查看。不满足时只显示 ID。
5. **窄窗。** 一行能容纳时显示位置、工作区、任务和文件。文件放不下时保留前三项。如果位置和工作区也挤占任务名，来源行只显示任务，详情给出完整工作区、文件及各项 ID。任务名过长时使用现有标签的省略规则。
6. 「来源」仍在桌面左侧和 Web 右侧，沿用现有焦点顺序。命名来源行用于聚焦工作台，分栏沿用原来源标签。

## 5. 验收

**固定起点（S3 子集）。** Linux X11，缩放 1，1600×1100 英文和 680×1000 中文。打开合成项目后进入聚焦工作台。连接 `runtime:lab`，在名为「项目一」的工作区中选中成功任务「Result task」。冻结清单只有唯一的 `scalar-0.vti` 和一份日志，新建任务表单中有未提交草稿，当前问答有未发送问题。

| 步骤 | 宽窗 | 窄窗 | 预期 |
| --- | --- | --- | --- |
| 「在查看器中打开」 | 1 | 1 | 打开切片。来源行为 `<连接名> · 项目一 · Result task · 显示 scalar-0.vti`，不再出现 `任务：scalar-0.vti` |
| 读取任务名 | 0 | 0 | 现状为往返「任务」「结果」各 1 次，共 2 次 |
| 「来源」，然后按 Esc | 1 + Esc | 1 + Esc | 三行均显示名称和 ID，焦点回到「来源」 |
| 「任务」 | 1 | 1 | 回到原任务行、原滚动位置和原入口焦点 |
| 在 Jobs 中改选另一任务后回「结果」 | 2 | 2 | 原画面保留。在原范围仍能复核原任务行时显示原任务名，否则沿用原来源标签 |

**恢复。** 全程以下状态不变：`camera_serial`、`payload_serial`、`evaluations_started`、选中任务、表单草稿、`ai_question/<handle>` 草稿和 `project()->revision`。不增加 `task.get` 或清单请求，`jobs.submission()` 保持为假，模型发送为零。

**回归入口。**

- 改动范围以 `viewer_editor.cc` 的来源行和来源详情为主，另有 `viewer_state.{hh,cc}` 新增的只读判断，以及 `desktop/app/i18n/{en,zh_CN}.json` 新增的两个键。新键须通过 `check_i18n.py`。
- 在 `JobsLayout.OpeningATaskResultKeepsTheFocusedWorkbench` 中断言来源行包含 `Result task` 且不含 32 位 ID，详情包含名称和 ID。
- 新增用例覆盖改选任务后保留原来源、名称证据失效、冷恢复、Hub 节点名和长名称。冷恢复沿用原来源标签。
- 以下用例保持通过：`JobsLayout.FocusedTaskResultReturnKeepsSameAreaScrollAndLauncher`、`…RevisitingAnAcceptedTaskKeepsTheDisplayedResult`、`…FocusedResultSourceWrapsAndScrollsLongLocalLabels`、`JobsFake.SoleVtiOfTheAcceptedListOpensThatExactFileWithTheSlicePreset`、`test_viewer_state.cc:550`，以及工作区状态往返用例。
- 定向测试用 `stk-jobs-tests` 和 `stk_app_viewer_tests` 的 `--gtest_filter`，再跑 UI 标签。实窗回执由 Root 记入 `docs/runtime-validation.md`。

## 6. 限制

- Linux 实窗覆盖直连 Runtime。Hub 节点名、跨范围失效与冷恢复由桌面控件测试覆盖。 [验收记录](../runtime-validation.md)
- 一个连接描述下替换为外部凭据时，若桌面没有观测到，名称与 ID 一样无法区分。这一点沿用 `still_same_scope` 的现有边界。
