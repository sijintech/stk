# MuPRO / MuFerro 执行器试点

2026-11-08 更新。所有者已选择首期优先执行器与专业软件，首个软件为 MuPRO / MuFerro；
数据格式由插件定义，MuPRO 使用 HDF5；同意扩展 S2c 智能体 prepare/run 权限。
这些是当前开发方向的决定，下面区分实施切片、既有合同和仍未验证的部分。

2026-11-09 按 main `7cf0462b` 校订：已收集结果的原生 HDF5 场与步选择（H1）已发布，见
[已发布的原生 HDF5 场与步选择](#已发布的原生-hdf5-场与步选择h1)。较早的本地探针保留为历史记录，
所有者决定不变。

## 已决定的范围

- 先打通软件发现/能力预检、冻结输入、显式执行、日志与产物核验、按原任务恢复，再扩展跨端入口。
- 插件定义其原生输入输出格式及版本化读写规则；共同层保留稳定资源引用、来源、单位、修订和任务回执。
  不要求所有专业软件采用一种原生格式。MuPRO 的数据适配以 HDF5 为目标，已有 DAT 路径保持兼容。
- S2c 从此前禁止 Agent prepare/run 的边界进入明确的权限扩展开发。仅方向获准，当前注册表和发布协议仍须逐项扩展并验证，
  不能只把两个字符串加入允许列表就当完成。模型建议不能自行构造用户/节点授权。
- 分工由 root 总负责；Claude 在独立 worktree 实现分配的文档及模块。D1 兼容门清单已经 root 审阅修正后合入 main；
  单主机任务/故障子集已验证，D1 完整退出仍未完成。HDF5 读取模块已修正审查问题，由 root 在 main `56f51af7` 接为显式 FileSource/图数据源，
  [读取契约](../specs/mupro-hdf5-1.md)已发布。main `89e40c89` 增加有界元数据发现、限定字段句柄和同一已成功任务的 HDF5 附加产物收集；
  `395e78fd` 让显式字段源按登记摘要约束容器，`c3061e78` 发布单容器元数据节点，`9e22e6ed` 提供已验证载荷的延后接纳，
  `49140b04` 在仿真面板接入列出、明确选择和打开，`0b9b1c90` 增加只读的查找重试，`fa2ef209`、`9ac67dde` 固定其原生请求与回执回归。
  HDF5-only 完成验证与真实执行验收仍待后续增量。有限 S2c 已按[首次批准契约](../specs/agent-muferro-run-1.md)接入：仅桌面明确直连/SSH目标、本地冻结与人工首次批准；不是模型自动执行。

## 当前可复用的实现与缺口

| 入口 | 当前事实 | 试点需要的增量 |
|---|---|---|
| [`suan/mupro/spec.py`](../../suan/mupro/spec.py)、[`run.py`](../../suan/mupro/run.py) | 已有结构化 TaskSpec、Linux/MPI 启动、程序解析与完整输出核验；许可只配置目录。`suan mupro check --json` 输出本机前置检查观察 [`stk.mupro-preflight/1`](../specs/mupro-preflight-1.md) | 定向预检实际引擎版本/依赖/许可签出及可运行算例，记录真实启动/退出与失败，不读取许可正文 |
| [`suan/workflows/muferro.py`](../../suan/workflows/muferro.py) | 既有执行链已补同任务 `case/run.h5` 的摘要、冻结网格及跨步类型核验和登记，结果行记录其 SHA-256 | 收集仍要求旧 DAT 完成验证；继续真实软件与 HDF5-only 输出验收，不另建调度器 |
| [`suan/connectors/mupro/`](../../suan/connectors/mupro/) | 0.2.0 已发现 `run.h5` 并以 `hdf5:<field>` 打开；DAT/表格保持，HDF5 错误有单独诊断 | 合成/CLI 软件验证不代真实 HDF5 输出、完成证据或目标 OS，不能称整个执行器已完成 |
| [`muferro_hdf5_view.cc`](../../desktop/engine/lib/stk_app/src/muferro_hdf5_view.cc)、[图节点](../specs/stk-graph-v1.md) | 已发布 `stk.source.mupro_hdf5_fields@1` 列出场与步号；面板以固定 `results/muferro/<run_id>/case/run.h5` 和登记摘要列出、明确选择并打开一帧。DAT 的查看已收集结果不变 | 仅 Linux 合成验收；真实许可输出、macOS/Windows 面板和 Viewer 内步滑块未验证或未实施 |
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

截至 `7cf0462b`，第 2、3 步的合成读取与收集接入已发布；第 6 步只完成了桌面已收集结果的 Linux 合成点击验收，
见[已发布的原生 HDF5 场与步选择](#已发布的原生-hdf5-场与步选择h1)。第 4 步的真实执行链仍缺授权软件与算例。

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

Claude 以 `a656f879` 为基线核对执行器和读取器入口；其中执行器预检的事实按 `000bb6ff` 校订，Hub、心跳和 `graph.meta` 各条仍为原基线的核查。
本机预检观察已实现，见下一小节。节点之间传递观察值、读取依赖投影、桌面节点预检和放置能力仍是拟议，下文比较传递方案。
执行、授权及放置沿用当前发布契约。

### 已实现的本机预检观察（`000bb6ff`）

`suan mupro check --json` 输出 [`stk.mupro-preflight/1`](../specs/mupro-preflight-1.md)，使用说明见
[MuPRO Runtime 指南](../runtime-mupro.md#本机预检观察)。它只描述调用进程所在机器的已配置前置条件：

- **运行位置。** 在调用进程内执行，`scope` 固定为 `local_process`。命令不构造 Runtime 客户端，不选择节点，也不授权执行。
  在桌面机器上得到的结果不是另一台计算节点的就绪状态。
- **字段。** `producer` 含组件 `suan.mupro` 和已安装 STK 包的 `distribution_version`（不可得时为 null），它不是 MuPRO 版本。
  另有 `process_id`、采集前后的 `started_at`/`observed_at`，七个按序固定的检查项
  `env_scripts`、`sdk_prefix`、`program`、`shared_libraries`、`mpi_launcher`、`license_dir`、`example_case` 及其状态，
  和总结 `summary`。观察对象不含程序/脚本/许可路径、主机名、环境值、原始错误或命令输出。
- **总结规则。** 任一项 `fail` 即 `checks_failed`（退出 1）；否则任一项 `warn` 或 `skip` 为 `checks_incomplete`；其余为 `checks_passed`。
  后两者都退出 0。未配置可选环境脚本记为 `not_configured`，单独出现时不使结果变为未完成。
- **未验证项。** 三种总结都保留 `unverified`：`program_version: unobserved`、`license_checkout: not_checked`、`solver_execution: not_run`。
  `checks_passed` 只说明这些前置检查通过，不能证明已安装 MuPRO、许可有效、算例可运行或结果科学有效，也不代表所选远端执行目标已就绪。
- **副作用。** 检查器本身不启动 MuPRO、MPI 启动器、算例或许可签出，但会用 bash source 已配置的受信任环境脚本，并可能对找到的程序运行本地 `ldd`。
  脚本的作用取决于该受信任配置，检查器不审计其内容。因此这是显式的本机诊断，不是无副作用的被动元数据读取，不能直接放进 `graph.meta` 或心跳。
- **既有命令。** `python -m suan.mupro check` 的 `{ok, checks}` JSON、含本机路径的诊断信息和退出码不变，`ok` 只表示没有 `fail`。
  `submit`、`result`、`verify`、任务身份和逐次运行核验也不变。

Root 证据为合成本机证据，不是真实 MuPRO 或节点证据：`root-delivery-20261109-121/preflight-root.xml` 87 项通过、2 项跳过（1 项需真实 muFerro 样例前缀，1 项为 Windows 目录联接），其中含新增 18 项；
Python 3.11 和 3.14 分别 18/18 通过（`preflight-311.xml`、`preflight-314.xml`）。`installed-receipt.json` 在只装基础依赖、无 NumPy/h5py 的已安装 wheel 中
得到三种控制台结果：脚本程序为 `checks_incomplete`、原生占位可执行文件为 `checks_passed`，两者退出 0；缺程序为 `checks_failed`，退出 1。回执核对了 `run.py` 和 `cli.py` 两个源模块的摘要，受控夹具中未产生求解器或 MPI 调用。
占位可执行文件不是 MuPRO，未验证许可或求解。

### 当前证据

- 预检有两个本机入口：既有的 `python -m suan.mupro check` 返回含主机路径的详细诊断；`suan mupro check --json` 只投影固定检查项和状态（见上一小节）。两者检查环境脚本、程序、动态库、MPI、许可目录和示例。合成前缀中的两行脚本作为程序时，`ldd` 无法检查，结果为 `checks_incomplete`；换成非 MuPRO 的原生占位可执行文件并配空许可目录即可得到 `checks_passed`，所以该总结不说明软件身份或许可有效性。目前没有把这份观察传到 Runtime、Hub 或桌面的入口。[节点预检](../../suan/mupro/run.py) [客户端命令](../../suan/mupro/cli.py)
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
| 执行器预检 | 本机固定检查项和状态已由 `stk.mupro-preflight/1` 提供（`local_process`）。拟议部分是在目标节点上取得并带来源和时效传递。真实软件版本、许可签出和实际算例运行需要各自证据 |
| 当次放置授权 | 由目标、资源和当次请求经现有授权与复核判断。有限 S2c 使用桌面明确选择的直连或 SSH 目标和人工首次批准 |
| 最近一次真实运行 | Runtime 终态与同一任务 `stk-mupro.json` 的 `stk-mupro-1` 核验、程序摘要和时间共同形成回执 |
| DAT 读取 | 在承担读取的进程验证 NumPy 加载 |
| HDF5 读取 | 在承担读取的进程验证 NumPy 和 h5py 加载，数据按原生格式合同另验 |
| 当前可达性 | 列表保留最近心跳，当次精确请求单独反映活动连接 |

每条观察记录来源、组件版本和生成时间。执行器或读取器观察的时效独立于传输心跳。离线时可显示带时间的最近值，实际读取和放置仍经过对应的请求检查。投影使用固定枚举、计数、时间和摘要，预检的路径、环境值和原始错误留在节点本地；本机预检观察已按此形状输出。[首次批准契约](../specs/agent-muferro-run-1.md)

### 传递方案（待选）

| 方案 | 兼容性与使用范围 |
|---|---|
| `features` 字符串 | 现有 Hub 投影保留字符串。适合标记观察操作的支持，可变状态还需要来源和时效 |
| 结构化快照或 health | 可承载独立状态和时间。旧 Hub 会丢弃额外快照键，部署需要版本化投影 |
| `graph.meta` 现有 `features` 对象 | 可按需观察执行图的进程。旧 Hub 的结果转发和客户端兼容性须实测，现有动作记录成本适合低频诊断。本机预检会 source 受信任脚本，不能作为被动读取并入 |
| 现有请求诊断和任务回执 | 继续提供当次读取状态和历史运行证据。节点列表的能力筛选仍待实施 |

先补可重复的节点本地验证，核对合成预检、依赖缺失、旧投影、连接断开和心跳老化。对照应分别记录未报告、过期、断开和明确不可用，检验活动连接上的精确读取。节点本地的固定状态投影已作为本机 CLI 观察实现；在目标节点上触发它并传回的方式尚未选择。发布入口、Hub 列表和放置策略仍需按各自契约审阅。

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

## 收集结果的 HDF5 场显式查看（历史核查，基线 `7ac983e8`）

本节是 H1 之前的本地探针记录，保留原观察以便追溯。其中“缺少原生入口”的结论已由
`c3061e78` 与 `49140b04` 解决，当前行为以[已发布的原生 HDF5 场与步选择](#已发布的原生-hdf5-场与步选择h1)
和已发布契约为准。

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

基线时已有的可用路径是已保存分析。此探针用 `prepared` 夹具登记一份同字节副本，然后经现有 `files.index` 和快照冻结。实际收集记录的摘要交接另由 Runtime 合成回环覆盖。 [分析运行](../../suan/project/analysis_runs.py) [分析执行](../../suan/desktop_bridge/analysis_runs.py)

### 当时的缺口与检查

探针当时的结论是：交互选择步或场需要显式的选择器选项，或新增从已登记容器到 HDF5 选择器的节点。
这一缺口已由 `stk.source.mupro_hdf5_fields@1` 和仿真面板的列出、选择、打开解决，没有改变运行索引的
`frames` 表和 `muferro_frame@1`，二者仍按 DAT 契约工作。Viewer 内拖动 HDF5 步号仍未实施。 [图契约](../specs/stk-graph-v1.md)

外部探针 `probe_collected_hdf5_view.py` 生成 `receipt.json` 和 `probe_stdout.txt`。定向测试包括 `test_mupro_hdf5_source`、`test_mupro_hdf5_results`、`test_mupro_hdf5_collection`、`test_muferro_collected_view`、`test_graph_presets` 及 `test_analysis_run_executor` 的真实载荷用例，结果 73 项通过，1 项跳过（需 `STK_PERF=1` 的性能基准）。
证据位于 `root-delivery-20261109-91/claude50/evidence/`。这些是 H1 之前基线的结果，不是当前面板的验收。
已收集结果的原生点击验收见下节；Hub/Runtime 绑定的分析运行、真实求解器 HDF5 输出和许可证据仍未核验。

## 已发布的原生 HDF5 场与步选择（H1）

本节按 main `7cf0462b` 的已发布契约、用户指南和运行验收整理。设计依据见
[HDF5 场与步选择设计核查](mupro-hdf5-result-selection.md)。

### 已发布的读取节点

- **`stk.source.mupro_hdf5_fields@1`**：参数为 `binding`、相对 `path` 和 64 位小写十六进制的 `expected_sha256`。
  规划在缓存查找前对实际字节流求 SHA-256，不符时报 `invalid_data`。缓存未命中时，先按同一摘要核验私有副本，再打开元数据。
  输出含 `path`、实测 `sha256`、`size`、`reader` 及 `fields`，每项给出确切 `selector`、整数 `step`、场名、原生 `shape` 和 `dtype`，
  先按步号、再按场名排序。发现最多访问 4096 个链接，最多返回 256 项场与步号，超出任一上限都报 `budget_exceeded`，不返回部分列表。
  节点只读元数据，不证明求解完成。 [已验证的字段元数据](../specs/mupro-hdf5-1.md#verified-field-metadata)
- **`stk.source.mupro_hdf5@1`**：调用方明确给出 `/tNNNNNNNN/<field>`，没有最新帧或字段回退。可选 `expected_sha256`
  约束容器，规划在缓存查找前核对。容器上限 1 GiB，所选数组上限 256 MiB，并受求值内存预算限制。
  [FileSource 与图](../specs/mupro-hdf5-1.md#filesource-and-graph) · [原生字段](../specs/mupro-hdf5-1.md#native-field)

### 原生面板流程

在**仿真运行记录**中选中已收集的运行，依次操作。 [仿真指南的 MuPRO HDF5 结果补充](../simulation-muferro.md)

1. **列出 HDF5 帧**：只读。经严格桥 `graph.evaluate` 本地求值内联 `mupro_hdf5_fields@1`，绑定当前项目根，
   路径固定为 `results/muferro/<run_id>/case/run.h5`，`expected_sha256` 取结果行登记的摘要。列表求值输出上限 256 KiB。
   不写项目，不提交，不下载，也不改变 Viewer。
2. **选择**：单个下拉框，条目形如 `Polar · step 2`。初始不选中，明确选中前不能打开。
3. **打开所选 HDF5 帧**：再次核对上下文后，用所选 `selector` 和同一登记摘要求值 `mupro_hdf5@1`，帧载荷上限 256 MiB。
   校验并持有载荷后才接纳到 Viewer。求值失败或答复到达时上下文已变化，则保留原画面。
4. **重试查找 HDF5 结果**：结果行查找失败时出现。点击只重新读取该运行的结果行，不自动列出或打开。

只收集了 DAT 的运行仍通过**查看已收集结果**一次打开最近输出的极化帧，DAT 默认路径、`latest` 默认值和 DAT 步选项不变。
列出的选项绑定项目、修订和所选运行，上下文变化即清空，需要重新列出。 [面板实现](../../desktop/engine/lib/stk_app/src/muferro_hdf5_view.cc)

### Linux 合成验收

以下结果记录在[运行验收](../runtime-validation.md)的 2026-11-09 17:28、17:56 和 18:07 UTC 三节，均使用公开合成算例。

- **固定起点与点击数。** Linux X11/Xvfb 1440×1600，软件 OpenGL，缩放 1。Project 最大化，Simulations 与 Simulation runs 已展开，
  选中唯一已成功并收集的运行，Viewer 为空，Python 草稿隐藏。依次点击列出、下拉、`Polar · step 2`、打开，共四次，零滚动、零键入。
  Viewer 显示第 2 步 `Polar_x` 的 24 个体素，值域 `[0, 69]`。
- **来源已变化。** 同大小改写容器后，打开因摘要不符被拒绝，原 Viewer 保留。实际严格桥另核对了缓存改写，以及排队后改开其他来源时返回冲突并保留新来源。
  访问以规范化项目根和固定相对路径限定，拒绝把算例目录换成指向项目外链接的反例。
- **迟到答复。** 成功答复挂起期间另点一次审阅页，放行后保留审阅页画面和原 Viewer。
- **草稿与项目状态。** 以上三组均保留原 Runtime 任务、项目修订 8 和隐藏的 Python 草稿。
- **查找重试。** 严格桥在第一次真实结果行查询后返回可重试错误。旧版刷新并重新展开后仍只有第一次查询；当前版一次重试只补一次查询，
  随后四次点击打开同一帧。
- **冷重开与 DAT 兼容。** 冷启动重开 HDF5 项目，在空 Viewer 起点四次点击、零滚动打开原任务的 Polar 第 2 步。旧 DAT-only 项目在相同起点一次点击、
  零滚动打开普通畴 Viewer 的原末帧第 2 步。同一会话从 HDF5 项目切到 DAT 项目再切回，原 HDF5 选择被清空，明确重新列出后恢复四个选项。
  项目切换与重新列出期间保留已有 Viewer 画面、未发送草稿、项目修订和原 Runtime 任务。
- **持久回归。** `fa2ef209` 固定列出与打开的请求和解码，见运行验收 18:25 UTC 一节。`9ac67dde` 固定查找重试，在缺少按钮的旧版复现失败，
  集成记录见 [交接](../../handoff.md) 18:55 UTC 一节；运行验收 18:55 UTC 一节记录随后以空模型 API key 重跑的仿真与 HDF5 原生定向 20/20。

### 尚未建立的范围

- **真实许可输出。** 夹具是合成的。真实许可 MuPRO 是否写出 `/tNNNNNNNN/<field>` 布局，以及场名和步号间隔，尚无证据；不读取合作方私有实现来补猜。
- **HDF5-only 完成。** HDF5 元数据可读不代表求解成功。自动收集仍要求既有 DAT 完成核验通过，只有 HDF5 的运行目录不会被登记为成功结果。
- **目标 OS。** 四次点击的原生面板流程已在 Linux 合成实窗验收。Windows Python 3.11 和 3.12 客户端 CI 已运行 HDF5 读取相关测试，
  macOS 和 Windows 的原生面板实窗流程待验。 [Windows 3.11](https://github.com/sijintech/stk/actions/runs/42679509438/job/129369927288) ·
  [Windows 3.12](https://github.com/sijintech/stk/actions/runs/42679509438/job/129369926548)
- **物理含义与科学参考。** 长度单位为 `grid_index`，场单位 `unspecified`，物理时间未知。步号不对应外加电场值，也没有参考数据或科学结论。
- **后续接口。** Viewer 内的 HDF5 步滑块需要按版本新增节点并改契约（H2），HDF5 体素拾取需扩展 `probe`，均未决定。
  Hub 或远端未收集的运行不在范围内，契约也不提供写入中 `run.h5` 的实时访问。

## 电场扫描与剩余决定

电场扫描是将外加电场按任务方案改变，获得 P–E 回线等响应。这些是研究任务的输入，不是文件容器格式。
所有者尚未指定这些数值。任务需逐项明确：

- 场方向，以及所用坐标系或分量；
- 幅度范围和单位；
- 升降与循环顺序、循环次数；
- 场步长或场点数；
- 每个场点的推进步数和采样/输出间隔，由此确定输出步号与场值的对应；
- 初始状态；
- 是否舍弃预循环；
- 用于比较的参考值，以及可用的许可软件、主机和算例。

MuPRO 插件应显式描述和验证这些输入，研究任务给定实际参数。H1 的 `Polar · step N` 只是原生输出步号，
在上述对应给定前不表示某个电场值。现有合成回线网格不自动成为真实 MuPRO 扫描参数，也不能据运行退出 0 认定材料结论。

仍待决定的是分析修改提案的持久形式，以及首个研究任务的实际参数/参考值和可用资产。
原“合作数据格式统一待定”和“S2c 是否扩展”已由上述决定更新，历史文档中的禁止/待决条目不表示新功能已经实现，
实施前继续遵守当前发布契约。原八项范围保留，PET 新专项后置。
