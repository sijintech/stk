# STK 开发交接（Claude / 后续开发者）

更新：2026-10-09。**P3 工作流（W1–W4）已交付；体验包（[ux-package-2026-10.md](docs/design/ux-package-2026-10.md)）进行中：U1“需要处理”已交付
（[suan/project/attention.py](suan/project/attention.py)、`project.attention.*`、[project_attention.hh](desktop/engine/lib/stk_app/include/stk/app/project_attention.hh)、
工作台“需要关注”与状态栏计数）；U4 工作流记住视图已交付（`workflow_editor.cc` 的 `ViewMemory`/`save_state`、`AnalysisGraphCanvas::look_at`）；
U2 用量可见已交付（`Requests.usage`、`project.requests.usage`、AI 助手“本项目已用”与发送按钮模型）；U3 项目内搜索已交付
（[suan/project/search.py](suan/project/search.py)、`project.search`、工作台“搜索项目”）；**体验包四项完成**；所有者决定的后续顺序：归档方案（[project-archive.md](docs/design/project-archive.md)，已确认并实现）→
MuFerro 按行工作流运行（W5a 服务与脚本已交付：[suan/desktop_bridge/workflow_runs.py](suan/desktop_bridge/workflow_runs.py) 的远程步骤、
`muferro.final_state`；W5b 桌面运行区已交付：`simulation_target.hh`、`workflow_editor.cc` 的 `remote_steps()`）→ AI 批量模拟闭环（[方案](docs/design/ai-batch-loop.md)；L1 AI 扫描提议已交付：[suan/project/parameter_sweep.py](suan/project/parameter_sweep.py)、
AI 助手“提议参数扫描”；L2“用工作流运行新增的 N 行”、L3“就这 N 行的结果提问”已交付；P2 闭环完成）；**归档 A1–A3 已交付**（所有者 2026-10-08 确认方案：格式 11 与 [suan/project/archive.py](suan/project/archive.py)、各列表 `archived` 过滤与冻结检查；桌面 [project_archive.hh](desktop/engine/lib/stk_app/include/stk/app/project_archive.hh) 与共用控件 `src/editors/archive_controls.hh`，九类对象在各自列表中归档/恢复，Home“需要关注”可归档；按所有者澄清，归档即冻结：不能修改、可照原样运行和使用，修改须恢复或复制（“复制为新工作流”）；限制见方案“已知限制”）；**思劲平台方向（[方案](docs/design/sijin-platform-2026-10.md)，所有者已答复三轮，按 S1 → S7）：S1 全部交付（S1a–S1d）**（[模型网关](docs/design/model-gateway.md)：格式 12 数据标注、`suan/models/` 端点与网络设置、发送前检查、桌面端点选择与“公开数据”；S1c 本机一键部署：[suan/models/local.py](suan/models/local.py)、[catalog.json](suan/models/catalog.json)、`models.local.*`、桌面“本机模型”，真实下载与运行的手动验证见[验收记录](docs/runtime-validation.md)；S1d 自动选择模型：[suan/models/routing.py](suan/models/routing.py)、`models.route`、AI 助手默认“自动”与按候选回退）；第二轮的四份评估（内网穿透、共享会话、文献借阅、Python 3.11 与 Flower）已由所有者在 2026-10-09 逐项决定（方案“所有者决定（第三轮）”）；Python 下限已升到 3.11（推荐 3.12）；S2 智能体 harness 的[设计](docs/design/agent-harness.md)已由所有者作答（规划只用本机或机构内模型、v1 不准备运行、新增“结构公开”标注等），按 S2a → S2b 实现；**S2a 与 S2b-1 已交付**（格式 13、[suan/agent/](suan/agent/) 循环与 8 个工具、[agent_sessions.py](suan/project/agent_sessions.py) 哈希链日志、`project.agent.*` 13 个方法（`decide` 只给桌面）与脚本 `stk.project.agent`、验收测试 `tests/test_agent_muferro_acceptance.py`；尚无桌面界面，见设计“进度”），下一步 S2b-2（桌面）；此前完成的可用性开发包（[审视记录](docs/design/user-review-2026-10-06.md)，进度见
[开发计划](docs/development-plan.md)开头）：标量体范围（`96152bf`）、启动即工作台（`1d1c338`）、参数扫描生成（`ca8a8b3`）、
路径框“浏览…”（共用 [path_picker.hh](desktop/engine/lib/stk_app/src/editors/path_picker.hh)，`b1badce`）、
运行环境选择与“运行所选行”（`stk.batches.run`、[project_simulation_view.cc](desktop/engine/lib/stk_app/src/editors/project_simulation_view.cc)，`ed5bb29`）、
分析“运行并显示”（`analysis_graph_editor.cc` 的 `RunAndShow` 链条，`7e64ece`）已交付，第 3 项完成；
第 4 项已交付[术语表](docs/design/glossary.md)与 AI 助手内的 API 密钥（`TokenPlanCredentials`，`ai.credentials.*`），
以及收起内部细节（[project_labels.hh](desktop/engine/lib/stk_app/src/editors/project_labels.hh)）与一行说明
（[editor_text.hh](desktop/engine/lib/stk_app/src/editors/editor_text.hh) 的 `hint()`），第 4 项完成；
第 5 项：示例项目（[suan/workflows/demo.py](suan/workflows/demo.py)，工作台按钮与 `suan demo`）、
无头 `stk`（[suan/scripting/headless.py](suan/scripting/headless.py)）、[Linux 快速上手](docs/quickstart-linux.md) 与文档站。
**可用性开发包已全部交付（最终状态 `3fd0c17`，桌面 CI 5/5 通过）。所有者决定 AI 批量模拟闭环交给团队后续完成，
当前进行 P3 工作流编辑（计划见[开发计划](docs/development-plan.md)“P3 工作流编辑”）：W1a 候选图模型已交付**
（`AnalysisParameterDraft` 的 `graph()`/`graph_changes()` 与 `add_node`、`remove_node`、`set_links`、`set_node_param`、`move_nodes`、`set_graph_output`），
W1b 候选视图与“编辑图结构”面板、W1c 节点参数表单已交付（`analysis_graph_editor.cc` 的 `shown_view()`、`graph_edit_panel()`、
`list_input()`、`node_params_editor()`），W2 画布拖动与拖线已交付（`canvas_drag_*`、`AnalysisGraphCanvas::hit_port`）；
W3 方案（[项目工作流与子图导航](docs/design/project-workflows.md)）已由所有者确认；W3a 已交付：[suan/project/workflows.py](suan/project/workflows.py)（存储与 `validate`）、共用受管表格 [suan/project/managed.py](suan/project/managed.py)、`stk.project.workflows`、`project.workflows.*`，用户说明见 [docs/project-workflows.md](docs/project-workflows.md)；W3b 已交付：[workflow_editor.cc](desktop/engine/lib/stk_app/src/editors/workflow_editor.cc)、[workflow_view.hh](desktop/engine/lib/stk_app/include/stk/app/workflow_view.hh)、[project_workflows.hh](desktop/engine/lib/stk_app/include/stk/app/project_workflows.hh)，分析图 `navigate()`/面包屑，`AppShell::open_in_area_later/return_in_area_later`；W3c-1 编辑模型已交付（[workflow_draft.hh](desktop/engine/lib/stk_app/include/stk/app/workflow_draft.hh)、`project.workflows.choices`、`ProjectWorkflows::create/update/check`）；W3c-2 编辑界面已交付（`workflow_editor.cc` 的 `edit_panel`/`step_panel`/`drag_finish`）；W4 方案（[workflow-runs.md](docs/design/workflow-runs.md)）已确认；W4a-1 已交付：[suan/project/workflow_runs.py](suan/project/workflow_runs.py)、格式 10、`suan/workflows/templates.py` 的 `LOCAL_TEMPLATES`/`workflow_templates()`、分析运行 `parameter_overrides`；W4a-2 已交付：[suan/desktop_bridge/workflow_runs.py](suan/desktop_bridge/workflow_runs.py) 执行器、`project.workflow_runs.*`、示例工作流“算例 → 合成求解 → 温度场”；W4b 已交付（`workflow_editor.cc` 的 `run_panel`/`run_detail`，`ProjectWorkflows::run_rows/start_run/...`，分析图 `navigate` 支持 `analysis_run_id`）；W4c 已交付（`WorkflowRuns.stale`、`project.workflow_runs.stale`、运行区过期标记与重算）；体验包见文首；ADE 参考第 1 组已并入 W4、第 3 组（AI 做法）交给负责 AI 批量模拟闭环的同事（[ade-references-2026-10.md](docs/design/ade-references-2026-10.md)）；
之前为保存分析的单输入连线编辑（`3cbaa36`）与技能目录首版（`5a12d5a`、`df4729d`）。均已推送 `main`。
接手时以实际 Git 状态和对应提交的 CI 为准，不把此处的快照当作永久状态；各提交的 CI 结果记在[验收记录](docs/runtime-validation.md)。

## 先读什么，先做什么

1. 阅读 [AGENTS.md](AGENTS.md)：所有者要求日常直接在 `main` 开发、提交、推送，不自动开分支或 PR。
2. 阅读本文，再看[开发计划](docs/development-plan.md)开头的 **2026-10-05 交付顺序**。
3. 产品决定以[工作台设计](docs/design/project-workbench.md)为准；存储/求值方向见[项目模型](docs/design/project-model.md)。
   已发布的 [specs](docs/specs/README.md) 是现有协议依据，设计提案不是当前数据库 DDL。
4. 接手先检查工作区、当前提交与远端状态，保护别人的未提交改动。完成一个可验收增量后做 critical review，
   修复实际问题、运行相关检查、更新计划/验收记录，再提交推送。

```bash
git status --short --branch
git log -5 --oneline
git fetch origin main
git log --oneline HEAD..origin/main
```

交接前只有主工作树；另有历史分支 `docs/development-handoff`、`fix/desktop-transfer-resume`。
它们不属于本轮待办，不应因为存在就合并或删除；无关旧 PR 也没有获得隐含合并授权。
更长历史在[开发交接记录](docs/development-log.md)，测试证据在[验收记录](docs/runtime-validation.md)。
旧日志中的“下一步”可能已被新计划替代，不要从最早里程碑重新开始。

## 所有者已经确定的方向

- UI 主要管理 **项目、文件、技能、工作流、对话**。运行记录保存某次执行的冻结输入、参数、状态和产物，
  有独立身份；重新计算产生新运行，编辑流程不能改写旧结果。
- 准备模拟时以 AI 对话为中心，结果分析时以 3D/数据视图为中心。当前只是逐步建立入口，尚未重做完整默认布局。
- 节点有项目流程与分析子流程两个层级。表格是通用查看/编辑框架，目标支持类型、引用、公式与富内容，
  参考多维表格和 Houdini 参数化；不要为每个 UI 页面另造一份业务状态。
- 项目采用“目录 + SQLite + 普通资源文件”。稳定 ID 用于持久关联，打开句柄只表示当前会话；
  大数据与图像等不必逐单元格写入 SQLite。表达式/依赖由应用服务求值，SQLite 本身不会执行所有计算。
- STK 内使用 Python 控制公开操作和布局；UI、Python、AI 复用共享服务和校验。代码编辑主要跳转 VSCode。
- Markdown/HTML/PDF、AI 报告、LaTeX 编译与嵌入预览仍是后续目标。
- 需要直接连接与 SSH；已有 Linux Runtime 连接/SSH 隧道和本机 stdio 桥，**通用 Mac↔Windows STK 点对点端点尚未实现**。
- `toolkits/` 最终按功能迁入 `suan/`，保留必要兼容；不是整目录改名。当前还有真实调用，不能提前删除。

## 当前已经能做什么

| 范围 | 已交付基线 | 尚未交付或需区分 |
|---|---|---|
| 原生桌面 | C++ / GHOST / OpenGL、Vulkan、Metal；分栏/标签、3D、Python、项目、AI、分析图；默认布局以分步引导工作台开始 | 不是完整的五类内容全局侧栏；各模式独立布局未实现 |
| 项目与表格 | SQLite 格式 **9**；原子修订、撤销、类型化值、引用/公式、文件索引、输入快照、预览/草案；按范围/列表一次生成参数行（[参数扫描](docs/project-sweeps.md)） | 富内容通用插件框架与完整项目打包尚未完成；格式升级必须显式备份 |
| AI | 阿里 Token Plan、OpenAI 兼容端点与本机一键部署的 llama.cpp 模型（数据默认私有，标注公开才可发往外部端点；网络设置离线/机构内/外网）、明确捕获上下文、准备/发送、临时流式回复、持久问答、标量参数建议与修改检查 | 不等于通用自主 Agent、文件/技能附件或完整 AI 批量模拟编排 |
| 分析 | 节点图检查；保存定义；参数、有序输出与单输入连线联合草稿（连线须校验后保存）；冻结输入与独立运行；结果归档、精确内联表格与源坐标定位 | 增删节点、多输入列表、拖线与位置保存未实现；多层图、子图及大表 blob 有界读取仍待开发 |
| Python / Runtime | 持久 Python 会话，项目/图/Viewer/布局等 API；Linux Runtime、MuFerro 流程、SSH 管理 | 不是所有 UI 操作都已覆盖；Runtime 服务端仍限 Linux；通用对等通信待开发 |
| 技能 | `stk-visualize`、`stk-monitor` 说明包及 `suan skills list/export`；实验契约 `stk.skill/1` 的三个内置技能，桥 `skills.list/get`、`stk.skills`、`suan skills catalog/show` 与原生只读“技能”页（[技能目录](docs/skills.md)） | 项目引用/版本固定、从技能直接准备或运行、技能附件、用户技能目录 **未实现**；节点目录不是技能库 |

用户此前在 macOS 和 Windows 真机上确认过能启动并看到 3D；这不是对后续每个交互、IME、GPU 驱动或安装包的全面验收。

## 可用性开发包：参数扫描生成

规划在 [suan/project/sweep.py](suan/project/sweep.py)（只读，输出普通命令；按 `project.apply` 的 1000 条命令上限检查），
桥 `project.sweep.plan`（[projects.py](suan/desktop_bridge/projects.py)）、控制台 `stk.project.sweep`、
CLI `suan project sweep`；原生 `ProjectState::sweep` 先取计划再以同一修订提交，修订变化即丢弃。
面板在 [project_editor.cc](desktop/engine/lib/stk_app/src/editors/project_editor.cc) 的 `sweep_controls`，
输入解析为纯函数 `project_sweep_axis`。测试：`tests/test_project_sweep.py`、`ProjectTable.SweepAxes*`、
`ProjectPython.SweepPanel*`、截图 `project_sweep_render_*`。下一步按计划做浏览按钮与“运行选中行”。

## 最近一次交付：保存分析的单输入连线

在“保存的分析”草稿面板新增 **连线 / Links**：选中节点的已知单输入端口可从全部已声明的上游输出中改接，
可选输入可断开；多输入、未知类型、未声明端口、重复节点 ID、带别名/额外字段的连线保持只读并说明原因。
含连线修改的草稿须点击“校验候选”，用 `graph.validate` 检查完整候选（图、参数、输出），通过后才能保存；
保存用 `ProjectAnalyses::replace_definition` 按读取修订一次写入整个定义。只有参数/输出修改的草稿行为不变。
用法见[保存分析指南](docs/project-analyses.md#编辑连线与图结构)。

继续开发时须保留这些边界：

- 校验结果绑定 `AnalysisCandidateKey`（打开句柄、分析 UUID、读取修订、草稿代次与版本、桥进程会话），
  任何后续编辑、修订或桥变化都使旧通过失效；迟到回复按票据丢弃。目录读取前/失败时输入只读。
- 连线编辑只改原始 JSON 中目标输入，未触碰的连线、别名、标签与参数类型逐字保留；设回原值即撤销该项修改。
- 有未应用或无效的参数文字（如 `1e`）时，连线选择、校验与保存暂停，文字不被重置。
- 画布与“校验”面板仍显示已保存定义；校验、保存、读回不运行节点、不准备运行、不改 Viewer；
  保存回复丢失时按 UUID 核对，不重发。

| 从哪里改 | 入口 |
|---|---|
| 连线草稿与校验绑定 | [analysis_parameter_draft.hh](desktop/engine/lib/stk_app/include/stk/app/analysis_parameter_draft.hh)、[analysis_parameter_draft.cc](desktop/engine/lib/stk_app/src/analysis_parameter_draft.cc) |
| 保存与界面 | [project_analyses.cc](desktop/engine/lib/stk_app/src/project_analyses.cc)、[analysis_graph_editor.cc](desktop/engine/lib/stk_app/src/editors/analysis_graph_editor.cc) 中 `links_panel` |
| 回归 / 截图 | [analysis_parameter_draft_test.cc](desktop/tests/app/analysis_parameter_draft_test.cc)、[analysis_links_editor_test.cc](desktop/tests/app/analysis_links_editor_test.cc)、[analysis_links_render.cc](desktop/tests/app/analysis_links_render.cc) |

## 上一项交付：技能目录首版

实验契约 `stk.skill/1`（[技能目录](docs/skills.md)）区分 SKILL.md 说明包、节点目录与版本化技能。
三个内置技能包装可离线验证的图预设；身份为 `id@version` 加定义与模板的 `content_sha256`，
[锁文件](tests/data/skill-catalog.lock.json)使同版本内容漂移在 CI 中失败（刷新方法与规则见技能目录文档）。
桥 `skills.list/get`（[协议 §16](docs/specs/stk-desktop-bridge-v1.md#16-versioned-skill-catalog-additive-extension-experimental)）、
Python `stk.skills`、`suan skills catalog/show` 与原生 **文件 → 技能** / 工作台“技能库”共用一次解析。

继续开发时须保留这些边界：

- 目录只读：不执行入口、不启动图工作进程、不准备运行、不改项目/Viewer/布局、不调用模型。
- 可用性来自已安装节点与 `find_spec`，不导入模块；离屏渲染等运行能力只声明 `checked: false`。
  依赖范围已用屏蔽模块的实际求值核对（例如畴占比不需要 VTK）；修改定义时同步该回归。
- 坏定义逐文件进入 `problems`，不隐藏其他技能；未知 ID/版本为 `not_found` 并给出已知版本。
- 原生状态按请求代次、桥客户端与进程会话过滤回复；来自其他桥的当前回复会清空目录并重新读取，不会卡在“读取中”。
  搜索按 UTF-8 边界截断到 200 字节；旧桥缺方法时显示“不提供技能目录”。
- 未改数据库格式。项目采用固定版本、从技能直接运行、附件与用户技能目录仍待设计。

| 从哪里改 | 入口 |
|---|---|
| 契约、解析、可用性、锁 | [suan/skills/catalog.py](suan/skills/catalog.py)、[definitions](suan/skills/definitions/)、[skill-catalog.lock.json](tests/data/skill-catalog.lock.json) |
| 桥 / Python / CLI | [server.py](suan/desktop_bridge/server.py)、[桥 schema](suan/contracts/schemas/desktop-bridge-1.schema.json)、[scripting/skills.py](suan/scripting/skills.py)、[skills/cli.py](suan/skills/cli.py) |
| 原生状态与页面 | [skill_catalog.hh](desktop/engine/lib/stk_app/include/stk/app/skill_catalog.hh)、[skill_catalog.cc](desktop/engine/lib/stk_app/src/skill_catalog.cc)、[skills_editor.cc](desktop/engine/lib/stk_app/src/editors/skills_editor.cc) |
| 回归 / 截图 | [test_skill_catalog.py](tests/test_skill_catalog.py)、[skills_catalog_test.cc](desktop/tests/app/skills_catalog_test.cc)、[skills_bridge.py](desktop/tests/bridge/skills_bridge.py)、[project_render.cc](desktop/tests/app/project_render.cc) |

## 更早交付：项目工作台

`b2e5632` 新增 `workspace` 编辑器：从 **文件 → 工作台**，或项目、AI、分析图的页头进入。
工作台显示当前项目，定位对话、文件、保存分析、分析运行、仿真运行、项目表格及创建/打开项目。
导航复用原编辑器并最大化目标区域；**视图 → 恢复分栏布局** 返回已有分栏。
Python 可调用 `stk.ui.activate_editor("workspace", maximize=True)`。

继续开发时须保留这些边界：

- 进入页面不发送模型请求、不启动计算，不改变 Viewer 的载荷、来源、相机或历史运行。
- 未发送的问题、有效参数草稿和无效原文（如 `1e`）在页面往返时保留。
- 项目路由检查全部窗口的活动文本输入。文件入口会选择共享文件索引表；切表前还检查全部窗口及隐藏标签的
  单元格、表名/字段名草稿，有草稿时保持布局与选择并提示先保存或重新载入。
  此保护仅覆盖新工作台入口，不代表所有既有手工切表动作都已统一改造。
- 回调固定项目打开句柄与来源编辑器/外壳寿命；切换、关闭/重开项目、销毁编辑器/窗口后旧动作失效。
- 标签容量满时不替换用户编辑器。导航不创建另一份项目状态；文件页切表也不会自动保存一份“上一张表”的工作区状态。
- 本轮没有数据库迁移；对象深链接、对话附件和完整新主页尚未实现（技能库入口已由技能目录首版补上）。

| 从哪里改 | 入口 |
|---|---|
| 工作台 / 返回按钮 | [workspace_editor.cc](desktop/engine/lib/stk_app/src/editors/workspace_editor.cc)、[project_navigation.hh](desktop/engine/lib/stk_app/src/editors/project_navigation.hh) |
| 路由、标签复用及寿命保护 | [shell.cc](desktop/engine/lib/stk_app/src/shell.cc)、[editor.hh](desktop/engine/lib/stk_app/include/stk/app/editor.hh) |
| 文件/运行/项目子页与草稿保护 | [project_editor.cc](desktop/engine/lib/stk_app/src/editors/project_editor.cc) |
| AI 与分析界面 | [ai_editor.cc](desktop/engine/lib/stk_app/src/editors/ai_editor.cc)、[analysis_graph_editor.cc](desktop/engine/lib/stk_app/src/editors/analysis_graph_editor.cc) |
| 新回归 / 截图 | [workspace_navigation_test.cc](desktop/tests/app/workspace_navigation_test.cc)、[analysis_parameters_editor_test.cc](desktop/tests/app/analysis_parameters_editor_test.cc)、[project_render.cc](desktop/tests/app/project_render.cc) |

## 建议接下来的开发包

### 1. 可审查的工作流提案（下一项功能）

按[开发计划](docs/development-plan.md)第 3 项：在已有“参数建议 → 草案 → 检查 → 明确应用”的模式上，
让 AI 或 Python 提出保存分析的修改（参数、输出、单输入连线），以同一 `AnalysisParameterDraft` 候选承载，
走同一 `graph.validate` 校验与按修订保存；提案、校验、保存、准备和执行保持分离，不自动采纳或重放。
先由所有者确认提案的持久形式：建议复用格式 6 草案与格式 7 来源关联、不升级数据库格式，
理由与边界见[决定建议](docs/design/review-drafts-and-conversations.md#保存分析修改提案的持久形式建议待所有者确认2026-10-06)。确认前不实现。

其他与连线首版相邻、但需单独设计验收的工作：多输入列表编辑、增删节点、拖线与位置保存、子图。

### 2. 技能目录的后续（按需排期，不与其他包混做）

- 项目采用固定技能版本：先定迁移、备份与恢复规则，把解析后的技能内容随项目保存，而非依赖全局目录保留旧版本。
- 从技能明确准备/运行（复用 `graph.evaluate` 或保存分析）、对话附件、更多入口类型（批次模板、Python 操作）及用户技能目录。

### 3. 持续跟进的稳定性与平台工作

- Weston 偶发退出故障仍未定位，见下节。新一次 CI 通过不能替代根因修复。
- macOS/Windows 按[真机验收清单](docs/workbench-acceptance.md)复核交互、IME、实际模型调用；Windows CI 没有 GPU 真机验收。
- 完整 AI 编排、通用 P2P、文档预览与 toolkits 迁移按主计划分批推进，避免混成一个大改动。

## 验证状态与未解决问题

截至 2026-10-06：

| 证据 | 结果 |
|---|---|
| 连线编辑 `3cbaa36` | 本机：草稿/校验单元 5 项、交互 **7/7**、截图 **8**；定向 **175/175**；完整 CTest **1151/1151**，0 失败/跳过。[桌面 CI](https://github.com/sijintech/stk/actions/runs/37459650536) Linux **1151**、macOS **770** / Metal **146**、Windows **729** 全部通过；[Runtime](https://github.com/sijintech/stk/actions/runs/37459650588) **7/7** |
| 技能目录首版本机 | Python 完整 **2199 passed / 24 环境跳过**；技能 Python **13/13**；原生定向 **95/95**；完整 CTest **1131/1131** |
| 技能目录 CI | `df4729d` [桌面](https://github.com/sijintech/stk/actions/runs/37358644803) Linux **1131**、macOS **758** / Metal **142**；`08de943` Windows CPU 重跑 **717/717**；[Runtime](https://github.com/sijintech/stk/actions/runs/37362435293) **7/7** |
| 人工截图检查 | 本机技能页 8 张、连线 8 张及旧保存分析英文窄窗口逐张检查；未逐张检查 macOS CI 截图 |

上一轮工作台交付（`b2e5632`）的证据见[验收记录](docs/runtime-validation.md#2026-10-05项目工作台与跨页草稿保护)。

已知 Weston 问题：旧提交 `17ea194` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36737424406)
有一项 `wm_app_window_weston_csd` 在窗口检查/布局重载之后 **SIGSEGV (11)**；更早非 CSD 用例也曾异常退出。
本机连续 30 次未复现，本次 CI 两个用例都通过。根因未知，不能写成“环境问题”或“已修复”。
`3ed063d` 修的是诊断：包装层必须在子进程非零退出、信号或超时时输出 `FAIL:`，防止 CTest 的成功文字匹配掩盖失败。

调查入口：[run_with_display.py](desktop/tests/wm/run_with_display.py)、[包装层测试](desktop/tests/wm/test_run_with_display.py)、
[窗口用例](desktop/tests/wm/CMakeLists.txt)、[应用窗口冒烟](desktop/tests/wm/app_smoke.cc)。
需要定位时保留原始 `LastTest.log`、Weston 日志和信号/调用栈；不要通过取消测试、放宽判据或反复重跑覆盖原始失败。

本轮本机证据在会话临时目录（不属于 Git，可能已被清理）：
`/tmp/claude-1000/-home-mnemora-xcheng-sijin-stk/07437944-4ce3-4414-bbc7-e80a0698ca9c/scratchpad/` 下的
`pytest-full-A.log`、`skills-{focused,full}.{log,xml}`、`links-{focused,full2}.{log,xml}` 与 `build-*.log`。远端 CI 链接是可共享的证据入口。

## 构建、启动和测试

### 当前 Linux 工作机

以下路径在交接时实际存在，仅适用于当前机器：

| 用途 | 路径 |
|---|---|
| 仓库 | `/home/mnemora/xcheng/sijin/stk` |
| Python | `/home/mnemora/opt/stk-venv/bin/python` |
| CMake 构建目录 | `/home/mnemora/opt/stk-build/merge-check`（Ninja / RelWithDebInfo） |
| 用户 sysroot | `/home/mnemora/opt/stk-sysroot` |
| 原生程序 | `/home/mnemora/opt/stk-build/merge-check/bin/stk-desktop` |
| 离屏图 | `/home/mnemora/opt/stk-build/merge-check/tests/app/out/` |

一次只运行一个原生编译；编译成功退出后再运行测试，不让测试读取仍在重链的二进制。
以下命令在仓库根目录运行；`&&` 保证构建失败时不测试旧程序。

```bash
cmake --build /home/mnemora/opt/stk-build/merge-check --parallel 4 && \
STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  --parallel 4 --timeout 600 --output-on-failure \
  --output-junit /tmp/stk-claude-full.xml
```

工作台/技能/布局/分析草稿定向回归（相关修改时使用；不需要每次文档修改都跑完整套件）：

```bash
STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  -R '^(SkillCatalog\.|SkillsCatalogPython\.|project_skills|WorkspaceNavigation(Python)?\.|AnalysisParametersEditorPython\.|FocusNavigation\.|ScriptPython\.)' \
  --parallel 4 --output-on-failure --output-junit /tmp/stk-claude-focused.xml
python3 desktop/tests/check_required_tests.py /tmp/stk-claude-focused.xml 'SkillCatalog\..*' 'SkillsCatalogPython\..*' \
  'WorkspaceNavigation(Python)?\..*' 'AnalysisParametersEditorPython\..*' 'FocusNavigation\..*' 'ScriptPython\..*'
python3 desktop/app/i18n/check_i18n.py
git diff --check
```

Python 测试按改动选取，例如技能相关可从 `tests/test_skill_catalog.py`、`tests/test_skills.py` 与 `tests/test_graph_schema.py` 开始，
用上述 venv 的 `python -m pytest`；完整平台组合与依赖以 [desktop.yml](.github/workflows/desktop.yml)
和 [runtime.yml](.github/workflows/runtime.yml) 为准。新必跑场景要接入 `check_required_tests.py`，跳过不算验收成功。

其他 Linux 机器按 [desktop/README.md](desktop/README.md#build-linux) 重新配置，不能照搬此机 CMake 缓存。
完整测试需要 Python 的科学/控制/可视化/测试依赖及 Xvfb/Weston；sysroot 下载入口支持 `--with-test-servers`。
配置时将 `STK_BRIDGE_TEST_PYTHON` 和 `STK_APP_TEST_PYTHON` 指向实际 venv，避免缺依赖导致测试跳过。

### macOS / Windows 启动

这两个脚本已存在并供用户测试，不要再建一套。完整工具链要求见[快速启动](desktop/QUICKSTART.md)。

```bash
# macOS，完整 Xcode；仅 CommandLineTools 会导致 xcodebuild 报错
bash desktop/setup-macos.sh --demo
```

```powershell
# Windows x64，VS2022/Build Tools C++ 工作负载、SDK、Git、x64 Python
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --check
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

更新代码后用正常命令重新编译；`--launch-only` 会跳过编译，不能用它验证新功能。
这些脚本只构建主程序，不运行完整测试，也不自动启动 Runtime。进入界面后从 **文件 → 工作台** 检查本次入口。
无服务器演示：[参数扫描/三维](examples/project_scan/OFFLINE.md)、[保存分析/结果表格](examples/project_analysis/README.md)。

## AI 配置与凭据

当前产品适配器是 `aliyun-token-plan/1`，代码在 [suan/project/aliyun.py](suan/project/aliyun.py)，
指定端点为 `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。
所有者说已将 `STK_TOKEN_PLAN_API_KEY` 写入自己的 Bash 启动配置，可按需要选择 `STK_TOKEN_PLAN_MODEL`。
不要把 Claude 作为开发助手与 STK 产品的模型提供方混为一谈，也不要因此改换产品端点。

本次交接没有读取或打印密钥。非交互 shell、其他操作系统和已运行的桥不一定继承 Bash 配置；
查看[模型请求指南](docs/project-requests.md)，只检查配置是否可用，日志/项目/测试夹具不得存入凭据。
`qwen3.7-plus` 是此前一次成功调用的历史记录，不代表本周套餐或模型目录的实时保证。
常规自动化用隔离桥和合成数据，显式清空测试进程的 API key；普通刷新、重开、检查草案不能触发收费请求。

## 代码边界与每次交付的自我审查

原生 UI 放 [desktop/engine/lib/stk_app](desktop/engine/lib/stk_app/) 和共享 UI 库；
持久化规则放 [suan/project](suan/project/)，桥在 [suan/desktop_bridge](suan/desktop_bridge/)，
科学图在 [suan/graph](suan/graph/)，脚本 API 在 [suan/scripting](suan/scripting/)。
详细边界见[仓库结构](docs/repository-structure.md)。`archive/` 不参与导入、构建、打包或测试发现；
旧 Qt 与仍被引用的 `toolkits/` 未达到退役条件。`desktop/` 为 GPL-2.0-or-later，Python 包保持 MIT，注意已有许可证边界。

每个关键节点检查真实问题，而不是只写“已 review”：

1. 操作是否意外写库、发送模型、准备/启动任务，或污染另一个项目/冻结运行？
2. 旧回调在项目/桥/窗口/候选变化后是否失效，未保存与无效原文是否保留，隐藏标签与其他窗口是否被遗漏？
3. 科学数值是否保留精确 JSON 类型、64 位整数、源行列、单位及 `null`/缺省/空值区别？
4. 无效回复、丢失回复、取消/重开是否会自动重发写入或执行？新增协议/格式是否兼容且可恢复？
5. 测试是否实际执行而非跳过，截图中控件是否可达，测试夹具是否先核对准备成功再检查目标行为？

修复后运行适当验证；已通过且无新改动/疑点时不重复扩大测试。
提交前更新[开发计划](docs/development-plan.md)、[交接日志](docs/development-log.md)及[验收记录](docs/runtime-validation.md)，
注明实际提交、CI/本机/真机证据和剩余限制。本文状态发生变化时同步维护，避免下次接手读到陈旧优先级。

## 可直接给 Claude 的起始指令

> 请先读仓库根目录的 CLAUDE.md、AGENTS.md 和 handoff.md，再按 docs/development-plan.md 最新顺序继续。
> 核对 Git/CI 后，从可审查的工作流提案开始（开发计划第 3 项），复用分析草稿候选、graph.validate 与按修订保存。
> 日常直接在 main 工作，不新建分支或合并无关 PR；每个关键节点做 critical review，修复问题、测试并更新文档后提交推送。
> 保留用户草稿、项目身份、冻结运行和明确执行边界，区分已实现能力与设计目标。
