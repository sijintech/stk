# MuPRO HDF5 收集结果的场与步选择（设计核查）

本文记录基线 `fd6116524fcf278f0b43448fb5ea98262cb1d618` 的设计核查。Claude 提供探针与初稿，root 复核后修订了 Viewer 接纳路径。
所述桌面选择界面尚未实现，下文的点击数是**计划目标**，不是观察结果。

研究者在桌面上选择已收集 MuFerro `case/run.h5` 中的一个场和确切步号，然后在 Viewer 打开。整个过程
不手写 `/tNNNNNNNN/<field>` 选择器，不自动回退到最新步，也不改变现有 DAT 默认 View。本文核对现有
入口能否完成这件事，并给出最小后续方案。

不在范围：真实许可求解器的 HDF5 布局、物理单位与时间、研究参数或步号的选择，以及 HDF5-only 完成判定。
收集仍要求既有 DAT 完成核验，见 [HDF5 契约](../specs/mupro-hdf5-1.md)。

## 结论

1. **选项可以从现有入口取得，但不能复用当前的 View 答复。** 面板 View 打开 DAT 预设，Viewer 答复的
   `parameters.step.choices` 是 DAT 步 `[0, 2, 4]`，不含任何 HDF5 内容。收集答复和结果行只带 `run.h5`
   的路径和 SHA-256，没有场或步。另做一次现有的严格桥 `graph.evaluate`（本地模式，内联 `muferro_run@1`，
   `live: false`，输出 `run.result`）就能拿到每个场的 `(step, selector, sha256, size)` 选项、dtype 和分量数。
   每帧的 SHA 都等于登记值。
2. **选定的非最新帧可以经现有图路径按确切 SHA 打开，但原生 Viewer 没有入口。** 显式
   `mupro_hdf5@1` 加 `expected_sha256` 能读到第 2 步而不是第 4 步。严格桥生成的桌面载荷和历史分析的
   冻结快照运行，读到的值域都是 `[0, 69]`。不过没有预设读取 `mupro_hdf5@1`，`viewer.open` 也不接受内联图。
   面板可复用内联图求值，把验证后的载荷交给原生 Viewer。现有 `viewer.open` 会先更换来源，再异步验证图结果，
   因此失败时保留原 Viewer 需要延后接纳。
3. **选取和打开应分开。** 选取只读、不碰 Viewer。打开是一次明确操作，会替换 Viewer 的当前来源。
4. **真正需要后续接口的只有 Viewer 内的 HDF5 步滑块。** 现有 HDF5 节点不上报步选项，而 Viewer 只从
   `step` 类型参数的上报取得步选项。要实现这一点，需要按版本新增节点或扩展图契约，不属于最小后续。

## 现有路径（源码事实）

**面板 View 是 DAT 默认路径。** 成功且已收集的运行才启用
[`simulation_view`](../../desktop/engine/lib/stk_app/src/editors/project_simulation_view.cc#L209)。
它经[固定动作表](../../suan/workflows/native.py#L19)只传 `run_id`，执行
[`MuFerroWorkflow.view`](../../suan/workflows/muferro.py#L437)：复核登记文件与清单后调用
`viewer.open(case_dir, preset="muferro-collected-domains")`（[L462](../../suan/workflows/muferro.py#L462)）。
该预设由 `muferro-domains` [派生](../../suan/graph/catalog.py#L149)，仅把 `live` 设为 false。它的
`step` 参数默认 `latest`（[预设](../../suan/graph/presets/muferro-domains.json#L13)），由 `muferro_frame@1`
读取 DAT。原生动作以脚本执行，返回 `None`（[执行助手](../../desktop/engine/lib/stk_app/src/editors/project_simulation_view.cc#L43)），
所以面板拿不到动作的返回数据，下拉选项不能来自现有 `muferro/1` 动作。

**Viewer 的步选项。** Viewer 把图中第一个 `step` 类型参数当作步参数
（[viewer_state.cc L637](../../desktop/engine/lib/stk_app/src/viewer_state.cc#L637)），从答复的
`parameters[step].choices` 更新步选项（[L893](../../desktop/engine/lib/stk_app/src/viewer_state.cc#L893)）。
请求只按预设 ID 发送，只要求载荷输出（[L721](../../desktop/engine/lib/stk_app/src/viewer_state.cc#L721)、
[L1032](../../desktop/engine/lib/stk_app/src/viewer_state.cc#L1032)）。DAT 帧节点用
`report_choices("step", …)` 上报（[sources.py L273](../../suan/graph/nodes/sources.py#L273)）。
`frames` 表排除 `hdf5:*`（[L153](../../suan/graph/nodes/sources.py#L153)）。`mupro_hdf5@1` 没有输入端口，
`selector` 是带模式的字符串，不上报选项（[L489](../../suan/graph/nodes/sources.py#L489)）。

**表单。** 预设参数声明了静态 `choices` 时，表单显示为下拉
（[form_json.cc L413](../../desktop/engine/lib/stk_ui/src/core/form_json.cc#L413)）。静态选项在预设载入时
就已确定，无法按运行变化。历史分析编辑器的节点参数表单把 `selector` 显示为文本框
（[analysis_graph_editor.cc L1034](../../desktop/engine/lib/stk_app/src/editors/analysis_graph_editor.cc#L1034)），
所以现在换步要手写选择器，再新建一次分析运行。

**图契约。** 每个图参数都必须有默认值，图要在没有覆盖值时也能求值
（[schema.py L774](../../suan/graph/schema.py#L774)）。Viewer 的
[`probe`](../specs/stk-desktop-bridge-v1.md#L486) 只解析到 `file@1` 或 `muferro_frame@1`，HDF5 体素拾取不在现有能力内。
严格桥 `graph.evaluate` 接受内联 `graph` 和本地目录绑定
（[桥契约](../specs/stk-desktop-bridge-v1.md#L442)）。`viewer.open` 只接受 `{path, preset?, parameters?, focus?}`。

## 实测（公开合成夹具）

环境：Linux，`/home/mnemora/opt/stk-venv311`（Python 3.11、h5py 3.16.0、NumPy 2.4.6、VTK 9.7.1），
`STK_TOKEN_PLAN_API_KEY` 为空，`STK_TOKEN_PLAN_MODEL` 未设置。探针为仓库外的 pytest 模块，以
`-p conftest` 复用现有夹具，已确认导入本 worktree 的 `suan`。

夹具：现有 `make_fake_sdk(steps=4)` 合成求解器生成 DAT 第 0、2、4 步，并复制一份合成 `run.h5`：
`Polar` 为 float32 三分量，`Strain` 为 int16 六分量，各有第 2 步和第 4 步，第 4 步值另加偏移。
真实回环 Runtime 只执行一次任务，再由真实 `stk.muferro.collect` 收集。登记 SHA 为
`db577d9b…219d`（6328 字节），与 Runtime 发布 SHA 及本地文件一致。严格桥是真实子进程
（`ProcessBridge --strict`），它的 GraphWorker 负责求值。

| 检查 | 观察结果 |
|---|---|
| 收集答复 | 键为 `directory, files, qoi, record_id, run_id, table_id`。`case/run.h5` 条目与结果行一致，不含 `hdf5:` 或选择器 |
| 面板 View 动作 | `viewer.open(case_dir, "muferro-collected-domains")`；读取 `mupro_hdf5@1` 的预设为空集 |
| 类 Viewer 答复（DAT 预设、`view`、desktop） | `step = {value: 4, choices: [0, 2, 4]}`，答复中无 HDF5 内容。第 0 步只存在于 DAT |
| 运行索引（严格桥内联图） | `hdf5:Polar` 和 `hdf5:Strain` 各列出第 2、4 步，带原选择器，所有帧 SHA 等于登记值。dtype 分别为 float32/3 分量和 int16/6 分量，单位 `unspecified`，时间 `null`，无 `hdf5_error`。值内联返回，整份答复 22882 字节，抽出的选项 573 字节 |
| 非最新帧（严格桥，固定 SHA） | `/t00000002/Polar` 描述符 4×3×2，float32。进程内读值等于第 2 步，`/t00000004/Strain` 为 int16 原值，溯源 SHA 等于登记值 |
| 桌面载荷（严格桥，`scalar-volume` 换源） | `Polar_x`，`polarization`/`unspecified`，值域 `[0, 69]`（第 4 步为 `[100, 169]`） |
| 历史分析（冻结快照，GraphWorker） | 成功，绑定 `{record_id, sha256 = 登记值, size 6328}`，值域 `[0, 69]` |
| 错误选择器 | `/t00000006/Polar` 与只有 DAT 的 `/t00000000/Polar` 报 `frame_not_found`。`/t00000002/Nope` 报 `not_found`。`/t2/Polar`、尾换行和 `latest` 报 `invalid_param`。都没有回退 |
| 原位改写一个体素（大小不变） | 运行索引给出新 SHA，选择器不变，与登记值不符。固定 SHA 的请求报 `invalid_data`。不固定 SHA 的请求读到改写后的值 `-7.0`。面板 View 拒绝（"Collected result changed locally"）。改写后新快照的历史分析失败（"expected SHA-256"），原快照仍以 `[0, 69]` 成功 |
| 替换容器并加第 6 步 | 运行索引列出 `[2, 4, 6]`，SHA 不等于登记值，固定 SHA 读第 2 步报 `invalid_data` |
| 预设形状（单独脚本） | 无默认值时校验失败。空串默认值静态校验失败，但显式参数可以求值。`step` 类型引用报 `param_ref_type`。SHA 默认为 64 个 `0` 的哨兵值时校验通过：不覆盖则规划阶段报 `invalid_data`，不读任何场；显式选择第 2 步则成功 |
| 提交与修订 | 全程只有一个 Runtime 任务，无新提交 |

现有定向回归：`test_mupro_hdf5_collection`、`_source`、`_results`、`_discovery`、`test_muferro_collected_view`、
`test_graph_presets` 共 111 过、1 败、1 跳过（`STK_PERF` 性能例）。失败的
`test_workflow_snapshot_refuses_changed_hdf5_after_collection` 在干净基线可确定复现，与本核查无关。
基线 `c3f869eb` 改为在 `_progress` 返回 `None` 时取消收集，该测试把 `_progress` 替换成返回 `None` 的桩，
所以在第一个断言前就以 `_Cancelled` 退出。HDF5 收集主用例 `[valid]` 通过。

证据位于 `~/.local/state/stk-validation/root-delivery-20261109-100/claude58/`：`probe/`（探针）、`receipt.json`、
`probe_stdout.txt`、`probe.xml`、`probe2/`（预设形状）、`targeted.{txt,xml}`。

## 哪些可复用，哪些需要后续接口

| 操作 | 现有答复或入口 | 判断 |
|---|---|---|
| 身份：`run.h5` 路径与 SHA | 收集答复和结果行 `files` | 可复用，无需新接口 |
| 场与步选项 | 当前 View 的 Viewer 答复 | 不可复用：只有 DAT 步，且 DAT 步集合可能与 HDF5 不同（实测含 HDF5 没有的第 0 步） |
| 场与步选项 | 严格桥 `graph.evaluate` 内联运行索引 | 可用，是已发布方法的一次新调用。只需面板代码，不需要新的已发布接口 |
| 打开选定帧到 Viewer | 严格桥 `graph.evaluate` 和原生 `ViewerState::open_payload` | 需要面板接线，先验证载荷，再接纳进 Viewer。现有 `viewer.open(path, preset, parameters)` 的来源切换时机会提前清空画面 |
| 打开选定帧到历史分析 | 已保存分析和分析运行 | 现已可用，但每换一步要写项目并新建运行，适合固定归档，不适合浏览 |
| Viewer 内拖动 HDF5 步 | 无 | 需要后续接口：按版本新增能上报步选项的节点，或给 `mupro_hdf5` 增加选项上报 |
| HDF5 体素拾取 | 无 | 需要扩展 `probe` 的解析目标 |

## 最小后续建议（H1）

**范围。** 只做 MuFerro 仿真面板及原生载荷接纳接线。复用严格桥、已发布的图节点与 DAT View。

**求值。** 以实测的 `scalar-volume` 图为模板。原生 [`bridge::Client::graph_evaluate`](../../desktop/engine/lib/stk_bridge/src/client.cc#L1597)
发起本地求值，绑定当前项目根。内联 `mupro_hdf5@1` 使用按运行 ID 推导的项目相对路径，以及本次选择的 `selector` 和行内 `expected_sha256`。
项目根作为绑定边界，可拒绝调用端检查后被替换为项目外链接的算例目录。登记 SHA-256 约束实际解析的字节。
使用 `desktop` profile，只请求 `view` 载荷。面板在 Viewer 接纳前处理缺选择、摘要不符和输出错误。

**接纳。** [`ViewerState::open_path`](../../desktop/engine/lib/stk_app/src/viewer_state.cc#L1657) 会在求值前调用 `close()`。
H1 先验证输出类型、载荷结构和每个唯一缓冲的长度、摘要及总预算，再解码并持有同一份缓冲字节。借鉴历史分析
[`decode_payload`](../../desktop/engine/lib/stk_app/src/project_analysis_runs.cc#L425) 的普通文件句柄读取和独占缓冲做法。
H1 的结果没有历史归档回执，使用此次明确请求、选中行、求值 ID 和专用输出预算核对。
在主线程采纳前复核项目、选中行、求值 generation、屏幕和发起时 Viewer 版本。复用
[`AppShell::open_viewer_payload`](../../desktop/engine/lib/stk_app/src/shell.cc#L648) 的延后导航与版本校验方式。
已有历史分析入口只接纳到空 Viewer。H1 由明确打开动作授权替换当前画面，接纳使用
[`ViewerState::open_payload`](../../desktop/engine/lib/stk_app/src/viewer_state.cc#L1760)，在求值与验证全部通过后调用。
失败、迟到结果或用户已改变 Viewer 时保留原画面。H1 显示静态载荷及场、步号和容器摘要来源。

**面板控件。** 在 View 旁增加 HDF5 区，只在选中运行已有结果行、行中有 `case/run.h5` 且桌面就绪时启用：

1. **列出 HDF5 帧**（明确点击，只读）：用行中的 SHA，经严格桥 `graph.evaluate` 本地模式求值内联运行索引，
   绑定当前项目的绝对根，使用项目相对的 case 目录。只在每帧 SHA 都等于行内 SHA 时显示选项，
   否则显示"收集结果已在本地改变"，不给选项。若答复带 `hdf5_error`，显示该诊断，DAT 不受影响。
2. **选取**：单个下拉框，条目为"场 · 第 N 步"，按场名再按步号排序。初始不选中任何项，打开按钮在明确
   选中之前保持禁用。
3. **打开所选帧**（明确点击）。再次核对项目、句柄、修订、`run_id`、结果行 ID 和行内 SHA，再用
   `{selector, expected_sha256: 行内 SHA, field, component: 0}` 求值。规划和实际读取分别核对字节。
   只在验证载荷且打开目标仍有效后接纳。

**点击目标。** 固定起点沿用[面板 View 验收](../runtime-validation.md)：英语 Linux X11/Xvfb 1440×1600，
缩放 1，软件 OpenGL；项目编辑器最大化，Simulations 和 Simulation runs 展开；选中唯一成功并已收集的
合成 MuFerro 运行；Viewer 为空，Python 草稿隐藏。目标是 4 次点击、0 次滚动、0 次键入：列出、展开下拉、
选中第 2 步 `Polar`、打开。首帧应显示 `Polar_x`，值域 `[0, 69]`。在同一面板换步需要 3 次点击。
DAT View 仍为 1 次点击。

**身份链。** `run_id → uuid5 结果行 → files[case/run.h5].{path, sha256} → 运行索引每帧 SHA 相等 →
expected_sha256`。要求唯一结果行，文件路径必须等于按运行 ID 推导的 `results/muferro/<run_id>/case/run.h5`，实际路径须在当前项目目录内。
选项与 `(句柄, 修订, generation, run_id, 结果行, SHA)` 绑定，任一变化即清空选项和选中项。
迟到的答复按现有 `context_current` 和修订比对丢弃。

**上限。** 容器上限 1 GiB，发现只走两层、最多 4096 项，所选数组 256 MiB 并受求值内存预算限制。
下拉框最多 256 项，超出时明确报告。运行索引的值超过 256 KiB 时以 `{type, blob, media_type, size}` 返回，
只从实际求值回执的 `blob_dir` 按声明长度和摘要核验后解析（合成夹具为内联 22.9 KB）。
H1 拟用现有 `budget.max_output_bytes` 将列表求值限制为 8 MiB，视图求值限制为 256 MiB。C++ 接收端在分配、读取前执行同一上限。
历史分析快照沿用 100 个文件和 256 MiB 的输入预算。

**兼容与保护。**
- View、`muferro-collected-domains`、`muferro_frame@1` 的 DAT 读取、`latest` 默认值和 DAT 步选项都不变。
- 收集、日志、准备仍是各自的明确操作。列出不写项目，不提交，不下载。
- 列出与选取不改变 Viewer 的来源、相机、图层，也不改 Python 或分析草稿。只有"打开"会替换 Viewer 来源，
  与 View 的行为一致。
- 旧结果行没有 `run.h5` 时禁用 HDF5 区。缺 h5py 时显示读取诊断。切换节点、项目或运行后丢弃旧选项。
- Hub 或远端未收集的运行不在本增量内，契约也不提供写入中的 `run.h5` 实时访问。
- H1 的 Viewer 展示一个已验证静态载荷。通过仿真面板重新选择后打开下一帧。

**Linux 验证。**
- Python 和严格桥以本文内联图探针为基础，检查第 2 步的载荷值域，以及错误选择器和改写容器的拒绝。
  比较列出与打开前后项目修订、原 Runtime 任务和严格桥调用记录。
- C++ 单元：上下文变化时清空选项；默认不选中；SHA 不符时不显示选项；迟到答复被丢弃；打开前重新核对。
- 原生 Linux X11/Xvfb：在上述固定起点用 XTest 计数点击。截图首帧，回执记录预设、参数、值域、修订、
  任务数和隐藏草稿字节。负例从已显示其他结果的 Viewer 开始，在列出后、求值前改写 `run.h5`。
  核对旧画面、来源和相机均保留。另核对求值期间用户主动改开其他来源时，迟到答复不覆盖新画面。

**后续 H2（需要契约变更，另行决定）。** 新增按版本的 HDF5 帧节点，以 `field` 加整数 `step`（`exact`，
拒绝 `latest`/`first`）为参数，从同一 SHA 的列表上报步选项。这样 Viewer 步滑块可直接浏览 HDF5 步，
同时需要更新图目录与 [HDF5 契约](../specs/mupro-hdf5-1.md)。HDF5 拾取另需扩展 `probe`。

## 尚未证明的内容

- 原生桌面中尚无 HDF5 选择界面，上文的 4 次点击、首帧和草稿保护都是计划目标。
- H1 的原生面板载荷接纳尚待实测。已观察的是严格桥载荷解码，以及历史分析原生
  首帧（第 4 步，见 `root-delivery-20261109-94/97`）。
- Viewer 在用新预设打开时，是否把 `viewer.open` 传入的 `selector` 和 `expected_sha256` 用于首次求值，
  也没有观察过。已观察的打开路径只有 DAT 预设。
- 夹具是合成的。真实许可的 MuPRO 输出是否使用 `/tNNNNNNNN/<field>` 布局、场名和步号间隔尚无证据。
- 不建立 HDF5-only 完成判定。收集仍依赖 DAT 核验。
- 只在 Linux 上实测，macOS 和 Windows 的面板与读取路径未验证。
