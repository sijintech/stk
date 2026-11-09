# MuPRO / MuFerro 执行器试点

2026-11-08 更新。所有者已选择首期优先执行器与专业软件，首个软件为 MuPRO / MuFerro；
数据格式由插件定义，MuPRO 使用 HDF5；同意扩展 S2c 智能体 prepare/run 权限。
这些是当前开发方向的决定，下面区分实施切片、既有合同和仍未验证的部分。

## 已决定的范围

- 先打通软件发现/能力预检、冻结输入、显式执行、日志与产物核验、按原任务恢复，再扩展跨端入口。
- 插件定义其原生输入输出格式及版本化读写规则；共同层保留稳定资源引用、来源、单位、修订和任务回执。
  不要求所有专业软件采用一种原生格式。MuPRO 的数据适配以 HDF5 为目标，已有 DAT 路径保持兼容。
- S2c 从此前禁止 Agent prepare/run 的边界进入明确的权限扩展开发。仅方向获准，当前注册表和发布协议仍须逐项扩展并验证，
  不能只把两个字符串加入允许列表就当完成。模型建议不能自行构造用户/节点授权。
- 分工由 root 总负责；Claude 在独立 worktree 实现分配的文档及模块。D1 兼容门清单已经 root 审阅修正后合入 main；
  单主机任务/故障子集已验证，D1 完整退出仍未完成。HDF5 读取模块已修正审查问题，由 root 在 main `56f51af7` 接为显式 FileSource/图数据源，
  [读取契约](../specs/mupro-hdf5-1.md)已发布。main `89e40c89` 增加有界元数据发现、限定字段句柄和同一已成功任务的 HDF5 附加产物收集；
  HDF5-only 完成验证与真实执行验收仍待后续增量。有限 S2c 已按[首次批准契约](../specs/agent-muferro-run-1.md)接入：仅桌面明确直连/SSH目标、本地冻结与人工首次批准；不是模型自动执行。

## 当前可复用的实现与缺口

| 入口 | 当前事实 | 试点需要的增量 |
|---|---|---|
| [`suan/mupro/spec.py`](../../suan/mupro/spec.py)、[`run.py`](../../suan/mupro/run.py) | 已有结构化 TaskSpec、Linux/MPI 启动、程序解析与完整输出核验；许可只配置目录 | 定向预检实际引擎/依赖/许可配置及可运行算例，记录真实启动/退出与失败，不读取许可正文 |
| [`suan/workflows/muferro.py`](../../suan/workflows/muferro.py) | 既有执行链已补同任务 `case/run.h5` 的摘要、冻结网格及跨步类型核验和登记 | 收集仍要求旧 DAT 完成验证；继续真实软件与 HDF5-only 输出验收，不另建调度器 |
| [`suan/connectors/mupro/`](../../suan/connectors/mupro/) | 0.2.0 已发现 `run.h5` 并以 `hdf5:<field>` 打开；DAT/表格保持，HDF5 错误有单独诊断 | 合成/CLI 软件验证不代真实 HDF5 输出、完成证据或目标 OS，不能称整个执行器已完成 |
| [数据格式 v1 §10](../specs/stk-data-format-v1.md) | 已写明 MuPRO `run.h5:/tNNNNNNNN/<name>` 数组为 `(nx,ny,nz,nc)`，读入需转成 `(nz,ny,nx,nc)` | 按现有轴序做独立适配；组/字段/步号、类型、几何、单位和限制在插件合同中明示，不猜物理量或六分量张量顺序 |
| [`suan/agent/levels.py`](../../suan/agent/levels.py)、[`tools.py`](../../suan/agent/tools.py) | 已有有限prepare_muferro_run工具与桌面完整计划/单次首次批准；旧会话工具集合不增权，submit_run不进Agent | 真实MuPRO和目标平台验证仍缺；不支持Hub准备，不以本机身份标签充当认证，丢回执仅观察原身份 |

现有 VTKHDF 与 MuPRO HDF5 是不同布局；HDF5 是容器，不自动证明 group、轴序、单位和来源正确。
插件必须能说明实际读出的是什么。真实求解器是否按当前样例生成目标 HDF5，还需实际版本和产物证据。
公开连接器不通过读取合作方私有实现来补猜格式。

## 最小实施与验收顺序

1. **契约/就绪核查**：锁定真实软件/平台及样例可用性；列出缺依赖和访问入口，不读取凭据或许可正文，不把 PATH 未命中当穷尽无安装。
2. **HDF5 独立读取**：用公开合成 HDF5 验证原数组轴序、显式 selector、字段/步号、region/stride、原数值与 dtype。
   缺失/错误形状、损坏、外链/虚拟外部数据、超预算应拒绝；不推断单位，不自动触发求解器。
3. **插件接入**：在既有 FileSource/冻结来源和连接器接口下接入 HDF5；保留 DAT、旧图/CLI 和原身份兼容。
   软件原生格式留插件，公共数据描述与资源完整性不复制成另一套业务事实。
4. **真实执行链**：具备已授权软件与算例后，按原 run/task 显式执行、观察和收集；比对程序/输入/产物摘要、完整退出与验证结果。
   无资产只能完成软件协议子集，真实 MuPRO 运行和科学有效性仍记未验证。
5. **智能体接入**：prepare 与 run 分离，run 核对受信任授权范围、冻结计划及原操作；重复、冷重开、丢回复和撤权不能造成额外启动。
   工具执行来源由服务核定，不能信任模型给出的权限、路径或状态；取消意图与实际停止分开留证。
6. **跨端与交付**：Web/CLI/Desktop 读取同一任务与产物；固定布局和实际点击验收保护 Viewer/草稿。
   目标 OS、真实许可/GPU、故障恢复及科学参考分别验收，来源与结果记入运行验收。

## 收集时核对冻结的 Runtime 端点

Root 审阅 Claude 的 `1150229f` 方案后，选择在桌面桥的产物列表和下载启动增加可选前置条件。
原方案记录了两次内存后端复现。刷新后切换连接会改变产物查询的后端，正确列出产物后切换则会改变下载工作线程的后端。

- 收集传入准备时保存的连接、节点和 `connection_identity`。桥在实际列出产物的实例上核对身份。新下载也先核对实际后端，再保存传输并启动工作线程。
- 传输键与请求签名沿用原定义。已有同键记录若身份相符，直接返回原传输。身份缺失或不符时返回冲突，并保留原记录。
- 从断点或冷重启恢复时，工作线程使用原日志中的身份核对实际后端。恢复原连接后仍可重试同一传输。
- 可选参数只由需要冻结连接的调用传入。普通调用沿用原参数，遇到拒绝该参数的旧桥时保留错误。
- 这项检查绑定配置端点及节点，产物仍以原清单的 SHA-256 复验。Runtime 和 Hub 使用既有协议。

[桌面桥契约](../specs/stk-desktop-bridge-v1.md) [运行验收](../runtime-validation.md)

## 节点能力观察（D1 P-1/F-5，拟议）

Claude 以 `a656f879` 为基线核对执行器和读取器入口。下文比较观察值的传递方案。执行、授权及放置沿用当前发布契约。

### 当前证据

- 节点预检入口是 `python -m suan.mupro check`。CLI 的 `suan mupro` 提供 `submit`、`result` 和 `verify`。预检检查环境脚本、程序、动态库、MPI、许可目录和示例。合成前缀中的两行脚本和空许可目录也能通过当前预检。原始诊断会包含主机路径，节点间传递只应选取固定检查项和状态。[节点预检](../../suan/mupro/run.py) [客户端命令](../../suan/mupro/cli.py)
- Runtime health 的后端和资源是实现清单。Runtime、心跳和 `graph.meta` 的 `features` 都来自组件常量或配置。Hub 的 `public_snapshot` 保留 `features` 字符串并丢弃额外的快照键。`graph.meta` 的 `include` 为闭集。一次新的 Hub `graph.meta` 请求沿用动作路径，带来动作记录。[Runtime health](../../suan/runtime/server.py) [节点能力](../../suan/control/agent.py) [Hub 投影](../../suan/control/federation.py) [动作策略](../../suan/control/policy.py)
- 连接器 `info()` 与图目录可在缺少 NumPy 和 h5py 时读取，声明与装齐依赖的对照一致。DAT、表格和运行索引在读取边界检查 NumPy，HDF5 另查 h5py。已完成结果的连接器描述仍可运行 DAT 核验并生成核验结论。[连接器](../../suan/connectors/mupro/__init__.py) [HDF5 合同](../specs/mupro-hdf5-1.md)
- Hub 列表中的 `online` 依据未撤权设备最近 20 秒内的心跳。节点连接断开时，Hub 保留最后快照和时间。精确读取另检查活动连接，因此最近心跳和当次请求可达性是两个观测值。[心跳存储](../../suan/control/store.py) [Hub 精确读取](../../suan/control/app.py)

| 安装 | DAT 和表格 | HDF5 |
|---|---|---|
| `[server]` | 元数据可列出，能量表行数未知。请求读取时返回 `unavailable`，打开数据零次 | 可选发现记录 `hdf5_error`，显式图在规划阶段返回 `unavailable` |
| NumPy-only | 可读取 DAT 和表格 | 缺 h5py，返回 `unavailable` |
| `[science]` | 可读取 DAT 和表格 | 合成对照读到 float32 第 4 步首值 100 |

合成安装证据见 `root-delivery-20261109-86/f5-installed-review/matrix_receipt.json` 和 `root-delivery-20261109-87/claude44-installed/matrix_receipt.json`。完整结果描述的本地核验仍会读取原生记录及 DAT 头。能力方案的合成预检和投影探针见 `root-delivery-20261109-87/claude45/evidence/`。

### 拟分别记录的观察值

| 观察值 | 来源与含义 |
|---|---|
| 执行器安装 | 节点找到可执行程序时记录组件身份和观察时间。程序路径只供节点本地诊断 |
| 执行器预检 | 记录固定检查项和状态。真实软件版本、许可签出和实际算例运行需要各自证据 |
| 当次放置授权 | 由目标、资源和当次请求经现有授权与复核判断。有限 S2c 使用桌面明确选择的直连或 SSH 目标和人工首次批准 |
| 最近一次真实运行 | Runtime 终态与同一任务 `stk-mupro.json` 的 `stk-mupro-1` 核验、程序摘要和时间共同形成回执 |
| DAT 读取 | 在承担读取的进程验证 NumPy 加载 |
| HDF5 读取 | 在承担读取的进程验证 NumPy 和 h5py 加载，数据按原生格式合同另验 |
| 当前可达性 | 列表保留最近心跳，当次精确请求单独反映活动连接 |

每条观察记录来源、组件版本和生成时间。执行器或读取器观察的时效独立于传输心跳。离线时可显示带时间的最近值，实际读取和放置仍经过对应的请求检查。投影使用固定枚举、计数、时间和摘要，预检的路径、环境值和原始错误留在节点本地。[首次批准契约](../specs/agent-muferro-run-1.md)

### 传递方案（待选）

| 方案 | 兼容性与使用范围 |
|---|---|
| `features` 字符串 | 现有 Hub 投影保留字符串。适合标记观察操作的支持，可变状态还需要来源和时效 |
| 结构化快照或 health | 可承载独立状态和时间。旧 Hub 会丢弃额外快照键，部署需要版本化投影 |
| `graph.meta` 现有 `features` 对象 | 可按需观察执行图的进程。旧 Hub 的结果转发和客户端兼容性须实测，现有动作记录成本适合低频诊断 |
| 现有请求诊断和任务回执 | 继续提供当次读取状态和历史运行证据。节点列表的能力筛选仍待实施 |

先补可重复的节点本地验证，核对合成预检、依赖缺失、旧投影、连接断开和心跳老化。对照应分别记录未报告、过期、断开和明确不可用，检验活动连接上的精确读取。随后可以验证节点本地的固定状态投影。发布入口、Hub 列表和放置策略仍需按各自契约审阅。

#### 现有 `graph.meta` 路径核对（基线 `c8618a4f`）

| 路径 | 回答的进程与来源 |
|---|---|
| 直连、SSH | 桌面桥的 `graph.catalog` 和 `graph.presets` 来自桥接进程。`graph.evaluate` 使用桥以同一解释器启动的子进程，探针取样在桥接进程内。SSH 转发 Runtime 请求，这条路径的图读取仍在桌面侧。桌面桥方法表没有 `graph.meta` |
| 配对 Hub | `graph.meta`、`graph.evaluate` 和 `view.*` 由活动连接对应的 NodeAgent 执行。动作记录含 `node_id`、`created` 和 `updated`，结果缺少 agent 版本、进程身份和观测时间 |

[桥接方法](../../suan/desktop_bridge/server.py) [桥接图求值](../../suan/desktop_bridge/graphs.py) [节点代理](../../suan/control/agent.py) [Hub 路由](../../suan/control/app.py) [动作策略](../../suan/control/policy.py)

- **观察内容。** `features` 返回静态 `agent` 列表、`graph_workers` 配置和最近的 Hub health 能力。首次 health 失败时 Hub 能力为空，后续失败会保留上次结果。可选的 `render` 使用子进程探测离屏渲染，解释器可由 `STK_RENDER_PYTHON` 指定。现有 `reason` 可含解释器路径。
- **传递形状。** 当前 Hub 在动作结果中原样保留额外键，超过 64 KiB 的结果转入 blob。心跳投影会丢弃合成的同类额外键。`f8785319` 引入 `graph.meta` 动作。进程内对照验证了未知 kind 的拒绝与模拟旧 agent 拒绝时的失败回执。
- **权限与时效。** 拥有者和已配对客户端可提交该动作，各复核策略均直接放行。专用读取入口拒绝 `graph.meta`。四次合成提交中一次复用了相同 ID，最终得到 3 条动作记录、5 条变更事件。离线提交进入 `queued`，节点随后接手。重复 ID 只取原回执。动作时间缺少采样和进程绑定，无法区分排队期间的断开和执行缓慢。
- **读取依赖。** 装齐依赖、阻断 h5py、同时阻断 NumPy 和 h5py 的三个子进程得到相同 `features`、目录和预设摘要。`load_errors` 均为空，三者调用后都未导入两库。设置为不可达的 Runtime 没有收到调用。现有字段只能表示读取能力未报告。

合成结果来自节点代理子进程和进程内 TestClient。定向 23 项通过，证据为 `root-delivery-20261109-88/claude47/evidence/graph_meta_receipt.json` 和 `pytest_targeted.txt`。实际旧部署、支持 VTK 的渲染节点、真实 MuPRO 节点以及新客户端兼容仍待核验。 [图测试](../../tests/test_control_graph.py)

## 收集结果的 HDF5 场显式查看（核查，基线 `7ac983e8`）

本节核对已收集运行的 `case/run.h5` 经 `mupro_hdf5@1` 显式查看的入口。完成核验和默认 View 沿用 DAT 契约。下文的选择器用于合成验证，真实求解器输出、许可和研究步号需要独立依据。

### 观察事实

- **入口。** 内置和派生预设都不含 `mupro_hdf5@1`。`iso`、`scalar-volume`、`slice`、`vectors`、`volume` 是 `data`+`path` 场预设，使用 `stk.source.file@1`，其格式枚举不含 MuPRO HDF5。`run.h5` 自动判为 `vtkhdf`，`scalar-volume` 在 `src` 报 `unsupported`（无 `/VTKHDF` 组）。
  桌面 Viewer 直接打开文件只接受 `.dat/.npy/.vti/.vtk/.vtkhdf`。打开目录时，预设的第一个绑定指向该目录。脚本 `viewer.open` 只接收路径、预设 ID 和参数，不接收内联图。
- **SHA。** 收集以任务发布 SHA 调用 `describe`，`view()` 打开前复核登记文件和清单。基线图源把执行绑定到本次规划读到的字节。独立合成对照在收集核验与图读取之间改写一个体素，未指定摘要的请求读到了改写后的内容。图源现支持 `expected_sha256`，调用方可提供收集行的摘要，规划会在缓存查找前拒绝不符的字节。Runtime 绑定也核对任务发布 SHA。 [HDF5 契约](../specs/mupro-hdf5-1.md)
- **选择器与步。** 节点无输入端口，`selector` 是带模式的字符串。`string` 图参数经 `$param` 传入可通过校验，结果参数只回显该值，没有 choices。`step` 类型参数校验报 `param_ref_type`。
  运行索引（`live: false`）在 `result.datasets` 给出 `hdf5:Polar` 两帧和 `hdf5:Strain` 一帧的原选择器、容器 SHA 和大小。`frames` 表只含 DAT。不存在的步报 `frame_not_found`，不回退。
- **原字段。** `(4,3,2,3)` float32 读出 `(2,3,4,3)` float32，step 2，`grid_index`，场单位 `unspecified`，物理时间未知。六分量 int16 `Strain` 保留 dtype 和分量数，单位 `unspecified`。量名按已发布的 MuFerro 字段含义记为 `polarization` 和 `strain`。
- **DAT 共存与缺 h5py。** 同一 case 中 DAT 数据集与 `hdf5:*` 并列，DAT `Polar` 的步 0、2 保持。新解释器阻断 h5py 后，运行索引仍列出 DAT 并记 `hdf5_error: unavailable`。显式节点在规划阶段报 `unavailable`，未启动，也未加载 h5py。

[图源节点](../../suan/graph/nodes/sources.py) [Viewer 源分类与绑定](../../desktop/engine/lib/stk_app/src/viewer_state.cc) [脚本 Viewer](../../desktop/engine/lib/stk_app/src/scripting_viewer.cc) [收集与查看](../../suan/workflows/muferro.py) [图契约](../specs/stk-graph-v1.md)

### 两条路径

| 路径 | 合成核查 | 兼容性与限制 |
|---|---|---|
| 已保存分析的数据绑定 | 把 `scalar-volume` 的 `src` 换成 `mupro_hdf5@1`，并把 `selector` 声明为字符串参数，校验通过。快照冻结的 `run.h5` SHA 等于登记值。真实 GraphWorker 生成了与第 0 分量转置一致的载荷 | 可经现有分析编辑器打开载荷。选择器写在分析参数里，换步需要新的分析运行。分析输入上限 256 MiB，低于 HDF5 源的 1 GiB |
| 专用显式预设 | 可用新增预设或从现有图派生。打开目录和 `ui.viewer.open(path, preset, parameters)` 沿用现有协议 | 由调用方从收集观测传入选择器和摘要。当前节点的字符串参数只回显选择，步滑块需要独立的步号选择逻辑 |

已有的可用路径是已保存分析。此探针用 `prepared` 夹具登记一份同字节副本，然后经现有 `files.index` 和快照冻结。实际收集记录的摘要交接另由 Runtime 合成回环覆盖。 [分析运行](../../suan/project/analysis_runs.py) [分析执行](../../suan/desktop_bridge/analysis_runs.py)

### 缺口与检查

交互选择步或场需要显式的选择器选项，或新增从运行索引到 HDF5 选择器的节点。现有节点仅报告字符串值，运行索引的 `frames` 表和 `muferro_frame@1` 仍按 DAT 契约工作。 [图契约](../specs/stk-graph-v1.md)

外部探针 `probe_collected_hdf5_view.py` 生成 `receipt.json` 和 `probe_stdout.txt`。定向测试包括 `test_mupro_hdf5_source`、`test_mupro_hdf5_results`、`test_mupro_hdf5_collection`、`test_muferro_collected_view`、`test_graph_presets` 及 `test_analysis_run_executor` 的真实载荷用例，结果 73 项通过，1 项跳过（需 `STK_PERF=1` 的性能基准）。
证据位于 `root-delivery-20261109-91/claude50/evidence/`。原生桌面中分析载荷的点击验收、Hub/Runtime 绑定的分析运行、真实求解器 HDF5 输出和许可证据仍未核验。

## 电场扫描与剩余决定

电场扫描是将外加电场按任务方案改变，获得 P–E 回线等响应。任务需明确场方向、幅度和单位、
升降/循环顺序、步长、每点推进/采样、初始状态以及是否舍弃预循环；这些不是文件容器格式。
所有者尚未指定这些数值，MuPRO 插件应显式描述和验证，研究任务给定实际参数。
现有合成回线网格不自动成为真实 MuPRO 扫描参数，也不能据运行退出 0 认定材料结论。

仍待决定的是分析修改提案的持久形式，以及首个研究任务的实际参数/参考值和可用资产。
原“合作数据格式统一待定”和“S2c 是否扩展”已由上述决定更新，历史文档中的禁止/待决条目不表示新功能已经实现，
实施前继续遵守当前发布契约。原八项范围保留，PET 新专项后置。
