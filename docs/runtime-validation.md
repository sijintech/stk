# STK 0.1.0a1 验收记录

日期：2026-09-09。状态：工程预发布，尚未完成真实集群和独立桌面安装器验收。

## 初始工程版本验收

在 Linux / Python 3.12.13 中构建 wheel 与 sdist。新建独立虚拟环境，先只安装
核心 wheel；确认没有 PySide6 和 NumPy，实际启动独立 API / supervisor，完成
任务提交、执行、日志读取和 SHA-256 校验下载。

随后在该环境安装最终 wheel 的 science、desktop、mcp、test 可选组件，将测试与
科学示例复制到源码目录以外执行。确认导入路径来自新环境的 `site-packages`，
而非可编辑源码安装。

结果：**44 passed**（19.83 秒）；`pip check` 通过，`git diff --check` 通过。
唯一警告来自已有 pyqode 使用已弃用的 `sre_constants`。

桌面采用 Qt offscreen；测试容器缺少的 EGL / OpenGL loader 解压至临时目录使用。
启动任务工作台不会创建 VTK OpenGL 上下文。三维结果的完整交互仍需在具备图形
驱动的真实桌面验证；本次验证了 VTK 文件数据及桌面下载路径。

## 本轮续开发：部署诊断与站点报告

同日补齐 `suan server doctor`、`suan connect check` 和持久站点验收报告。
诊断覆盖本机配置、目录访问、SQLite、worker 环境、调度器命令及 API／supervisor；
失败报告仍为可解析的 JSON，退出码为 1，报告不输出连接令牌。

科学示例现在在提交前保存完整 TaskSpec 和幂等键，在关键步骤保存状态与证据。
等待超时或提交响应丢失时保留可查询／重试的信息。结果校验覆盖 DAT／VTK 的
完整场数据及 PNG 解码，避免只有 summary.json 正确却误报通过。
每次运行保存独立的 `acceptance-<run_id>.json`，包含实际命令、源文件校验值、
客户端和计算环境、输入／结果 manifest、日志片段及误差。

Linux / Python 3.12.13 验证结果：

- 源码环境完整回归：**67 passed**，25.40 秒，包含桌面 offscreen 和 MCP。
- wheel／sdist 构建成功，安装后的 `pip check` 通过。
- 从 sdist 提取测试与示例，在源码目录之外运行；确认新模块导入自独立环境
  `site-packages`。安装包完整回归：**67 passed**，25.92 秒。
- 新增及受影响测试共 25 项；包含未初始化／损坏配置、目录探针清理、网络磁盘识别、
  损坏数据库、Python 超时、缺失调度器命令、认证失败、服务停止、提交响应丢失、
  等待超时保留任务、错误场数据及 NaN 摘要拒绝。

两次完整回归均只有原有 pyqode 的 `sre_constants` 弃用警告。
本轮没有进行真实集群、外部 SSH 或独立桌面安装器验收；新增检查的通过状态
不改变下方站点验收边界。

## 2026-09-24 方向调整

用户确定的方向：

1. STK 独立于 Synorder 发展；桌面主线为 STK 自有的 Blender 原生工作台（`blender/`、
   `suan/blender_client`、`suan-control`、`suan-node` 与 Runtime）。
2. Synorder 集成推迟；`plugins/synorder` 与 `suan-synorder-node` 保留为可选。
3. MuPRO 作业的排队由 STK Runtime 负责。
4. 首个集群为并行云（Paratera），账号尚未开通。
5. 服务器 Runtime 仅支持 Linux；Windows 只作客户端。

据此完成的改动：

- Runtime：MPI 布局 `ranks`／`threads_per_rank`、argv 占位符 `{ranks}`／`{threads_per_rank}`／
  `{nodes}`、OMP／MKL 线程设置及 Slurm／PBS 映射；站点配置 `scheduler` 与不提交作业的 Slurm
  doctor 探针；本机 worker 启动失败不再占住并发名额；`/health` 增加 `resources`、`argv_tokens`，
  HTTP API 仍为 v1，已有任务的幂等键不变。
- 平台：`suan server init/start`、`suan-control init/serve`、`suan-node pair/run` 在非 Linux 上
  拒绝运行；`suan` 在 cp1252 控制台改用 UTF-8 输出；新增 pytest `server` 标记，CI 在 Linux 运行
  全部非桌面测试，在 Windows 只运行客户端测试与入口冒烟。
- MuPRO：`suan mupro submit/result/verify`、计算节点 `python -m suan.mupro run/verify/check`、
  逐次校验 `stk-mupro-1` 与本机多 rank 保护，见 [MuPRO 指南](runtime-mupro.md)。
- 工作台：控制模板 `muferro-example` 与 `--template`／`--template-file`，启动器 `--template`，
  按 MuPRO 帧名确定场名与时间步；`suan-workbench` 改为 STK 工作台启动器，Synorder 宿主改用
  `python -m suan.workbench`。
- 并行云站点清单见 [并行云站点验收清单](runtime-paratera.md)，尚未执行。

Linux / Python 3.12.14，`.[server,science,control,visualization,test]` 环境，
`python -m pytest -p no:cacheprovider -m "not desktop"`：**303 passed，2 skipped**，约 45 秒；
Python 3.10.21 同一命令结果相同。
跳过项为可选 MCP 组件未安装，以及需要 `STK_TEST_MUPRO_PREFIX` 的真实 muFerro 测试。
MuPRO 测试使用模拟的 muFerro、mpiexec 和 srun；Slurm／PBS 为模拟命令；非 Linux 行为通过修改
`sys.platform` 的测试检查，尚未在真实 Windows 或 CI 上运行。本轮没有运行多 rank MPI。

### MuPRO 本机验收

2026-09-24 04:09–04:13（UTC+8），r730xd 测试主机（`mnemora-test`，Linux x86_64，48 个逻辑 CPU），
Python 3.12.14。STK 为 `feature/independent-runtime-mupro` 分支上基于 217bd86 的未提交工作树，
以非可编辑方式安装到临时 venv。按 [MuPRO 指南](runtime-mupro.md) 的“本机验收流程”执行，
结果：**通过**，完成两次真实 muFerro 单 rank 运行。逐步记录见该指南的“结果”。

- 程序：Release 构建 muFerro（muprosdk b2adf41，SHA-256
  `c0c1f3454f5ff5384c76e70455b0441bb8ebeeb40b711b2360f2f0f1d099683a`），Release 许可检查通过，
  没有改用 muFerrod。两次运行都是 1 rank、1 线程、`launcher` 为 `none` 的 MPI singleton，
  没有启动 mpiexec 或 hydra。
- 耗时：CLI 提交 `--wait` 5.24 秒（求解器 3.02 秒）；模板任务从派发到结束 4.57 秒（求解器 2.83 秒）；
  无界面视图检查 0.89 秒；全程 279.6 秒，其中 pip 安装 246 秒。
- 校验：两次均为 `stk-mupro-1` `passed`（完成 101 步，101 行有限能量，101 条进度，30 个 16³ 场帧），
  `qoi.total_energy` 均为 −727.9144455（step 101），与不经 STK 直接运行 muFerro 的 1 rank 参考值相同。任务为
  `b19c4c0fdbbd41708acf4373e6a3f383`（CLI）与 `89213f88715844a7941a3f7601711a0c`（`muferro-example` 模板）。
- 网络：Runtime 只监听 127.0.0.1；运行期间本次运行没有其他监听。
- 幂等：同一 `--key` 返回同一任务 ID，没有新的运行目录。
- 视图：节点代理生成的 slice、等值面和向量箭头可用，slice 通过 `validate_scene`；`view.probe`
  与直接解析 DAT 的值完全相同；`energy_out.dat` 按预期被拒绝。
- 模板链路：C++ 按钮的等价命令按 `client.json` 换成 `muferro-example`，经节点代理在真实 Runtime 上
  运行成功，桥接写出的 `scene.json` 通过 `validate_scene`。
- 清理：Runtime 已停止，没有残留进程或套接字；muprosdk 工作树与许可文件元数据前后一致；
  `$A/shared` 为 31M（每次运行约 16 MB）。
- 发现两个小问题：`muferro-example` 模板没有声明 `ranks`／`threads_per_rank`，模板运行在 Runtime
  `environment.json` 中的 `MKL_NUM_THREADS` 为 null（求解器实际为 1）；以 `--port 0` 初始化时，
  停止后 `status` 的 `url` 显示端口 0。验收后均已修复：模板改为 1 rank、每 rank 1 线程，停止后
  `url` 为 `null`。

本次没有覆盖多 rank MPI、真实集群（含并行云）以及 GPU／Blender C++ 界面构建。

## 2026-09-25 里程碑 1：节点图可视化

内容：数据格式、图、渲染载荷与监控事件规范（`docs/specs/`），无界面图求值器与缓存，muFerro／SimViz
节点集与预设，离屏渲染与二维图，控制服务 blob 存储与图操作，网页“图谱”模式，MCP 工具与技能，见
[可视化工作流](visualization.md) 与 [控制服务指南](hub.md)。

自动测试：Linux，Python 3.12.14 与 3.10.21，`python -m pytest -p no:cacheprovider -m "not desktop"`，
离屏渲染子进程指向 Kitware `vtk-osmesa` 环境（`STK_RENDER_PYTHON`）：**889 passed，12 skipped**；
不设渲染子进程时渲染测试跳过。网页 `npm ci && npm run build` 通过，另有无头 Chromium 渲染与交互检查。
128³ 假 muFerro 帧上 `muferro-domains` 冷启动约 3.7 秒，仅改相机约 0.3 秒（不含 PNG）。

真实验收：2026-09-25 03:45–03:49（UTC+8，全程 204 秒），r730xd 测试主机，分支 `feature/m1-graph-viz`
提交 445e885 以非可编辑方式安装到临时 venv；Runtime、控制服务（含构建后的网页）与节点代理都只监听
127.0.0.1，单 rank。

- 经控制服务模板提交真实 Release muFerro（SDK 示例，16³，101 步），自动执行；校验 `stk-mupro-1`
  通过，总能量 −727.9144455（step 101），与 2026-09-24 的直接运行一致。
- 监控事件：经控制服务 `task.events` 读取 142 条（`metric.declare` 5、`metrics` 101、`progress` 2、
  `frame` 30 等），全部在 Runtime 标记任务结束之前到达。本例求解只有约 2.5 秒，帧事件在求解器退出时发布。
- `graph.evaluate`（`muferro-domains`，profile `web`）自动执行，所有 blob 经 sha256 校验，载荷通过
  `suan.render.payload.decode`；标签与对原始 DAT 的独立分类逐点一致，分数和为 1，能量图数据与
  `energy_out.dat` 101 行相同，离屏 PNG 1600×1200。耗时与缓存：首次 3.42 秒（13 个节点全部计算）；
  仅改视角 1.06 秒（只重算 camera、scene、png）；换步 1.48 秒；相同请求 0.34 秒（全部命中）；
  改阈值 1.38 秒（帧读取命中）。本例为单一 T[100] 畴；提高阈值后为 −1：2885、1：1211。
- 网页（无头 Chromium，127.0.0.1）：“图谱”模式运行 `muferro-domains` 约 1.0 秒显示，含图层、图例、
  分数表与能量图；手机宽度 390 px 无横向溢出；`muferro-polarization-glyphs` 显示箭头与取向图例。
  在畴表面上点击探针，返回值与原始 `Polar.00000100.dat` 的三线性插值完全一致（差 0.0）。
- MCP `graph_render` 返回的 PNG 与控制服务首次求值的 PNG 字节一致。
- 清理：各服务与进程退出，端口关闭；仓库与 muprosdk 工作树、许可文件元数据前后一致。脚本的
  `/dev/shm` 检查报出新条目，经核对属于本机同时运行的 GitHub Actions（muprosdk CI）进程，不属于本次运行。
- 第一次验收（2026-09-25 02:50，提交 626bcd1）发现两个问题并已修复后重验：畴表面平滑后超出网格
  约 0.66 格，点击表面时探针被拒且遮住外框（现已把表面顶点限制在网格内）；控制服务按字母顺序重排
  表格列（现有序列名 `column_names`，且保存结果时保持键顺序）。

未覆盖：Blender 端显示与节点编辑器、真实集群、多 rank、GPU、Windows 客户端实机、控制服务 blob 保留与回收。

## 覆盖范围

| 验收项 | 证据 |
|---|---|
| API 与 supervisor 分别重启，计算继续 | `test_deployment.py` 实际启动独立进程，检查 worker 身份与日志无重复 |
| 输入隔离、幂等提交、并发上限、取消 | `test_runtime.py` 通过 HTTP 提交实际 Python 进程 |
| 断点上传下载、校验失败、路径边界 | 中断后的字节偏移、SHA-256、符号链接与越界路径检查 |
| 程序失败、缺少结果、超时、内存超限 | 实际失败进程与资源限制触发 |
| worker 丢失与外部终止信号 | 保留活动程序的待核实状态，可取消；外部信号不误报用户取消 |
| PBS / Slurm 状态与不确定提交 | 模拟命令协议；真实运行生成的 job.sh、worker 和程序；不重复派发 |
| 调度器不可用、资源映射、历史查询 | 排队／失败／取消／待核实、跨日期查询与每节点资源参数检查 |
| 确定性参数扫描完整流程 | `examples/runtime` 的两组输入生成、计算、均值与最大值校验、PNG / VTK 下载 |
| 科学格式与无窗口预览 | DAT / NPY / VTK 往返；独立 VTK reader 校验坐标顺序；Agg PNG |
| 桌面远程流程 | Qt 界面通过保存的 HTTP 连接配置上传、提交、读日志、下载 |
| MCP 与 CLI 使用同一任务 | MCP 创建／提交／查询，CLI 读取同一成功记录 |
| 旧桌面和包入口 | 从非项目目录创建工作台；科学模块、GUI 资源、旧 CLI 组在 wheel 中可用 |
| 部署与连接诊断 | `test_diagnostics.py`、`test_deployment.py`：配置、磁盘、数据库、Python、命令、API 认证和 supervisor |
| 验收报告与失败证据 | `test_acceptance.py`、`test_deployment.py`：提交前保存幂等键、超时保留任务、完整场校验与安装包案例 |

## 尚需站点验收

- 真实 PBS / Slurm 集群（首个站点为并行云，账号待开通）、集群上的 MuPRO 可执行程序与许可、
  多 rank MPI / module 环境、共享文件系统、队列和站点资源策略；本次调度器测试为协议模拟，
  不是实际集群性能验证。MuPRO 目前只在本机完成单 rank 验收（见上）。
- 真实 SSH 网络断线／重连；本次已验证客户端重建和服务端任务寿命独立，
  未对外部服务器执行 SSH 测试。
- Windows / macOS 客户端运行；服务器端只支持 Linux。CI 在 Linux 运行服务器测试，
  在 Windows 运行客户端路径，本次仅在 Linux 执行。
- PyInstaller 冻结桌面二进制的多进程启动与 Python 解释器分发；当前验收发布物
  为 Python wheel / sdist，未发布到 PyPI 或创建远程 release。

交互式 Python 内核、远程实时三维渲染和团队权限属于后续阶段。

安装、API、SSH 与真实集群验收命令见 [runtime 使用指南](runtime.md)。
