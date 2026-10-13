# 多尺度计算引擎：ABACUS（第一性原理）与 LAMMPS（分子动力学）（方案，所有者已决定）

2026-10-10。所有者：思劲最近有一个 **PET 基材料设计项目**，需要第一性原理与分子动力学计算；这两类计算资料多、开源软件多，
STK 应优先支持，先融合开源的 **ABACUS** 与 **LAMMPS**，做成相场（MuPRO）之外的另外两个插件或功能模块，体现整个系统是多尺度的。
本文包含方案与交付记录；**仅“进度”中标明已交付的部分已实现**。所有者 2026-10-10 的决定见“所有者决定”。

## PET 材料数据项目的衔接（2026-10-12）

所有者要求参考第 6 版 PET 基材料研发项目方案实施，需求与验收路线见[材料数据闭环](pet-materials-data-loop.md)。
E 系列提供可追溯的计算证据，需连接材料/配方、批次、样品状态、原始实验曲线、专家复核及材料决定；
引擎功能通过不能代替材料成果验收。当前纯 PET 短链初始构型不代表 PET 基弹性体或酒液接触体系。
桌面 LAMMPS 入口仍为最近开发节点；之后 E1d/物性验证、E2、E3 依赖顺序不变。
代表体元/均匀化、流变黏弹、接触介质与工业接口按真实任务登记方法、参数和适用域，不能只把 MD 输出直接连成宏观结论。
该项目要求计算、模型、工具与派生查询遵循厂内边界；远程 Runtime 也须核对是否位于企业控制环境。
本文新增的是后续需求，不声称上述关联、方法或部署约束已经实现。

## 要做到什么

- 在 STK 中，ABACUS 与 LAMMPS 和 MuFerro 一样：参数表的一行就是一个算例；按行的工作流把算例提交到运行环境（本机、SSH 或集群），
  结果回到项目（结果表、文件、快照），可以分析、可视化、问 AI、进入智能体与材料模型的数据集。
- 三个尺度用同一套项目、工作流与运行环境：电子尺度（ABACUS）→ 原子尺度（LAMMPS）→ 介观尺度（MuPRO 相场）。
  以后可以串起来：例如 ABACUS 算出的弹性常数、电荷或相互作用能作为 LAMMPS 力场或相场参数的来源。
- 以 PET 项目为第一个用例：ABACUS 算 PET 单体、链段或晶胞的结构与电子性质；LAMMPS 算无定形 PET 的密度、玻璃化转变温度、力学或扩散性质。

## 两个软件（检索结果）

| | ABACUS | LAMMPS |
|---|---|---|
| 类型 | 第一性原理（DFT），平面波与数值原子轨道（LCAO）基组 | 经典分子动力学 |
| 许可 | LGPL-3.0（`deepmodeling/abacus-develop`） | GPL-2.0 |
| 安装 | conda-forge 预编译（`abacus` + mpich/openmpi），Docker 镜像（官方说明 Docker 只适合评估，生产建议源码编译） | conda-forge 预编译（官方文档推荐），或源码编译；Python 模块需自己编译 |
| 输入 | `INPUT`（参数）、`STRU`（结构、赝势与轨道文件名）、`KPT`（k 点） | `in.*` 脚本、数据文件（原子、键、力场参数）、势函数文件；命令行 `-var 名 值` 可传参数 |
| 额外文件 | 赝势（常用 SG15 ONCV，CC BY-SA 4.0；PseudoDojo）与匹配的数值轨道；ABACUS 官网与轨道库提供 | 力场参数通常在数据文件中；PET 常用 OPLS-AA、PCFF、GAFF，需要建模工具生成 |
| 输出 | `OUT.<后缀>/running_*.log`（总能、费米能、收敛、力与应力）、弛豫后的结构、电荷密度 | `log.lammps`（热力学量随步数）、轨迹 dump、重启文件 |

**许可的处理**：STK 不打包、不链接这两个软件，只在运行环境上作为独立进程调用（与 MuPRO 相同），用户或机构自行安装；
桌面本身已按 GPL 发布，与二者也相容。赝势与轨道库同样不随 STK 分发，按其许可由用户安装，结果中记录所用文件的摘要与来源。

## 现状与需要先做的通用化（检索代码所得）

STK 在数据一侧已有插件机制（连接器、输入连接器、图节点都可经 Python entry points 加入），但**执行一侧还写死在 MuFerro 上**：

- 模板注册表是固定的字典（`suan/workflows/templates.py`），没有插件发现；
- 按行工作流的远程步骤绕过模板对象，直接调用 `suan.workflows.muferro`（`desktop_bridge/workflow_runs.py` 的提交与收集、
  `project/workflow_runs.py` 的参数冻结与过期判断）；
- 一次运行只有一组运行环境与资源选项，不能“ABACUS 在服务器 A、LAMMPS 在集群 B”；
- `project.workflows.choices()` 不报告模板是否远程，桌面于是写死 `"muferro/1"`；桌面的仿真视图写死 MuFerro 的表与字段 ID；
- 启动器的通用部分（环境脚本、MPI 启动方式、运行记录）在 `suan/mupro/run.py` 中，`STK_MUPRO_ALLOW_LOCAL_MPI` 是 MuPRO 专用名。

因此分四步：

### E0 计算引擎接口（通用化，先做）

- **引擎协议**：每个引擎提供：
  - 运行环境一侧的启动器 `python -m suan.<引擎> run|verify|check`（读算例、检查、启动、验证结果、写运行记录 `stk-<引擎>.json`、环境检查）；
  - 项目一侧的模块（算例表与结果表、导入与复制算例、`describe_case`、准备、收集、`final_state`）。
- **模板注册**：内置的三个引擎 + `stk.engines` entry point，第三方或思劲自研引擎也可以按同一协议加入。
- **按行工作流按模板分派**：去掉对 MuFerro 的直接调用。
- **每个步骤各自的运行环境与资源选项**：协议、计划、桌面都要改。
- **桌面**：模板报告“远程”、显示名、表与关键字段，仿真视图与运行区按引擎显示。
- **共用的启动与核对代码**移到公共模块；`STK_ALLOW_LOCAL_MPI` 取代 MuPRO 专用名（旧名继续认）。
- MuFerro 迁移到新接口后**行为不变**，现有测试全部通过即为验收。

### E1 LAMMPS

- **算例**：一个文件夹，包含 `in.*` 脚本、数据文件与势函数文件。
  - 参数表的字段经 `-var` 传给脚本，例如温度、压力、步数、随机种子；脚本中写 `${temperature}` 一类变量。
  - 导入时检查脚本引用的文件都在文件夹内，不允许 `shell`、`python` 等能执行任意命令的指令。
- **结果**：解析 `log.lammps` 的热力学表，把最后一段（或指定区间）的平均密度、能量、温度、压力等记入结果表；轨迹作为项目文件保存。
  - 可视化：桌面查看器加原子与键的显示（球与棍），读 LAMMPS dump 与数据文件。
- **PET 首个用例**：给定一个已经建好的无定形 PET 数据文件（OPLS-AA 或 PCFF），按行扫描温度，得到密度–温度曲线，
  由拐点求玻璃化转变温度。这正好用上已有的参数扫描、按行运行与结果分析。

### E2 ABACUS

- **算例**：`INPUT`、`STRU`、`KPT`，以及赝势与轨道文件（或运行环境上的库目录，按摘要核对）。
  - 参数表字段写入 `INPUT`：计算类型（scf / relax / cell-relax）、截断能、k 点密度、泛函、自旋。
  - 也可以从 CIF、POSCAR 等常见结构文件生成 `STRU`，用 ASE 读结构。
- **结果**：总能、费米能、带隙、是否收敛、最大受力、应力，以及弛豫后的结构文件；结构可在查看器中显示。
- **PET 首个用例**：PET 单体或晶胞的结构弛豫与能带，或分子间相互作用能，用来对照或校准分子动力学力场。

### E3 串联（多尺度）

在一个工作流里串起不同引擎：

- ABACUS 弛豫结构 → LAMMPS 初始构型；
- ABACUS 算出的弹性常数或相互作用能 → LAMMPS 或相场的参数。

这一步需要“上一步的输出作为下一步的输入”的连线规则，在 E0–E2 稳定之后设计。

## 测试

- **CI**：与 MuFerro 的假 SDK 一样，用假的 `abacus` 与 `lmp` 可执行文件写出格式真实的输出（`running_scf.log`、`log.lammps`、dump），
  在本机 Runtime 上走完导入 → 运行 → 收集 → 结果表；解析器另用真实软件的输出样本测试。
- **人工验收**：在本机用 conda-forge 安装真实的 ABACUS 与 LAMMPS，跑一个小算例（例如 Si 的自洽计算、LJ 液体或小的 PET 体系），
  记入验收记录。

## 需要所有者决定

1. **先做哪一个**：(a) 先做 E0 通用化，再做 LAMMPS，再做 ABACUS（建议：PET 的密度、玻璃化转变温度等直接来自分子动力学，
   且参数扫描与按行运行最能体现价值）；(b) 先做 ABACUS；(c) E0 之后两个同时做。
2. **软件怎么安装**：(a) 用户或机构自行安装（推荐 conda-forge），STK 检测并在“检查”中给出安装说明（建议先这样）；
   (b) STK 在运行环境上一键安装 conda-forge 环境（类似本机模型的一键部署，工作量更大）。
3. **PET 项目首先要算的性质**（决定首个用例与结果表的字段）：密度与玻璃化转变温度；力学性质（模量）；
   气体扩散或阻隔性能；还是电子结构与相互作用能？
4. **PET 分子模型怎么来**：(a) 先由用户提供建好的 LAMMPS 数据文件（用 Moltemplate、EMC、LigParGen 等外部工具），
   STK 负责参数扫描、运行与分析（建议）；(b) STK 内置聚合物建模与力场分配（工作量大，放在之后）。

## 进度

- **E1b PET 本机建模（2026-10-12）**：所有者授权依据文献自主选择并直接实施；采用完整 PET OPLS-AA/MK 2022 适配方案，
  不把历史 0.0 当定论。COOH/OH 链默认 6×DP4=546 原子，配套来源 JSON/XML、显式 planar improper、端氧 +0.001 e 舍入修正。
  参数表→本机 `pet-model/1` 生成与冻结八项案例文件；新运行冻结输入，取消停止子树，完整成功才发布。显式导入 `lammps/1` 后运行。
  严格填充审查/周期自重叠拒绝与资源限制见[示例](../../examples/pet_model/README.md)，科学适用范围见[模型](../pet-model.md)。
  初始填充、独立参数/势能核对与软件路径验收不构成 Tg/模量/扩散材料性质收敛；气体、水、离子参数未实现。

- **E1c 分析模板（已交付，2026-10-11）**：导入的 full/real 算例可用三套 LAMMPS 模板，
  增加平衡步数、采样间隔、应变率与溶质类型参数；Tg 取多温度密度表的两段直线交点，
  模量拟合小工程应变窗口的拉伸应力，扩散拟合指定时间窗口的 MSD。
  四个增量图节点、三个预设与技能提供 summary/fit/diagnostics/plot，保留单位、拟合窗口、残差与来源摘要；
  旧节点声明、技能内容哈希与冻结计划保持不变。指南见 [LAMMPS 分析](../lammps-analysis.md)。
  合成曲线独立核对 340 K、2.5 GPa、1e-4 cm²/s；108 原子氩的真实 LAMMPS → Runtime → 工作流 → 隔离分析/归档路径通过。
  **限制**：不是收敛材料性质验收；无平衡自动判定、跨行自动 Tg 汇总、Tg 置信区间、通用分子质心/多原点 MSD。
  扩散生产段固定体积，不清除溶质自身平移；窗口必须明确填写，相关采样的 OLS 标准误差不代表材料性质误差条。

- **E1b 独立数据写出器（已交付，2026-10-11；2026-10-12 补平面 periodic improper）**：`suan.lammps.write_data` 从已分配参数的 ParmEd 结构直接写 full/real，
  支持 LJ、谐振键/角、RB→OPLS、正交与三斜盒子；保留电荷，按实际系数合并类型，以键连通关系定义分子，不建模、不选择 PET 电荷。
  540 原子 PET 对照 GMSO 0.17.0，逐项验证所有原子和连接的实际参数，用真实 LAMMPS 的同几何 `run 0` 核对分项能量，读回 STK 的六个晶胞参数。
  对照发现 GMSO 三斜 data 头错误地使用 dump 外包围边界；STK 按 LAMMPS data 约定写出，报告保留原始差异和 GMSO 错误读回体积。
  GMSO 按默认 residue 把六条链标为分子 1，STK 标为六个键连通分量。支持边界、RB 舍入常数、显式忽略未参数化 improper 的选项见[写出器指南](../lammps-data.md)。

- **E0a（已交付，2026-10-10）**：引擎模板接口与按模板分派。
  - `suan/workflows/templates.py` 定义远程模板（计算引擎）的接口：`field_ids`、`describe`/`describe_values`、`prepare(…, identity)`、
    `collect`、`results_prefix`、`final_state`、`validate_run`；
  - 外部引擎包经 `stk.engines` entry point 注册（内置标识不可替换，加载问题由 `engine_diagnostics()` 报告）；
  - 按行工作流的冻结、过期判断、提交与收集都按步骤的模板分派，不再直接调用 MuFerro；MuFerro 行为不变（原有测试全部通过）；
  - `project.workflows.choices()` 报告模板的 `remote`/`local`，桌面据此判断运行区是否要选运行环境（旧服务仍按 `muferro/1`）；
  - 通用的 `STK_ALLOW_LOCAL_MPI` 取代 MuPRO 专用名（旧名仍有效，二者都只能由运营者设置）。
- **E0b（已交付，2026-10-10）**：模块管理。
  - `suan/modules/`：随 STK 发布的模块目录（LAMMPS、ABACUS、Packmol、分子建模工具包 mBuild + foyer + GMSO + RDKit），
    micromamba 2.9.0 按平台固定大小与 SHA-256；
  - 检测：STK 自己的环境、指定的文件夹、PATH、常见的 conda 安装与环境；程序按版本参数读版本，Python 工具包按能否导入；
    检测到就登记为“已检测到”并直接使用；
  - 安装：只在没有找到时、由人确认后进行；网络设置须允许外网；下载 micromamba（核对摘要）后在 `~/.stk/modules/envs/<模块>` 从
    conda-forge 创建环境，可看进度、可取消，失败或取消不留下半装的环境；只移除 STK 装的模块；
  - 后台服务 `modules.list/detect`（也给脚本）与 `modules.install/cancel/remove`（只给桌面），进度事件 `modules.progress`；
  - 桌面工作台“计算模块”面板（重新检测、安装、取消、移除）；引擎启动器以 `suan.modules.find_program` 找程序。
  - 交付前审查后的规则：同一模块重复安装返回同一任务、不同模块同时安装时 micromamba 只下载一次；检测不碰正在安装的模块，
    与安装或移除重叠时不丢失或复活登记；正在创建的环境带 `.incomplete` 标记，半装的环境不会被当成已安装；网络设置不再允许外网时取消安装；
    安装有总时长与无输出时长上限，失败或取消先停掉安装程序再删除；安装程序只拿到精简的环境变量（不含密钥）；探测在空文件夹、独立进程组中运行，
    超时整组结束；登记表在文件锁下写入，读入时丢弃格式不对的条目；从未检测过时桌面面板先自动检测一次，检测时仍可取消安装；
    Windows 下按 `Scripts`、`Library\bin` 与环境根目录查找。
  - 本机实测：真实 micromamba 从 conda-forge 装好 LAMMPS（22 Jul 2025 Update 6，126 秒，1.8 GB）、Packmol 21.2.1、
    分子建模工具包（mBuild 1.4.0，169 秒），均被正确检测。
- **E1 可行性（本机实测，2026-10-10，尚未写入 STK）**：用真实模块走通 PET 建模 → LAMMPS。
  - 脚本、OPLS-AA 补丁与手动验收在 [examples/pet_lammps/](../../examples/pet_lammps/README.md)（2026-10-11 移入，可行性材料，不是产品代码）；
  - mBuild 由重复单元 SMILES `OCCOC(=O)c1ccc(cc1)C=O` 建 4 聚体链（90 原子），Packmol 以 250 kg/m³ 松散填充 6 条链（540 原子）；
  - foyer 自带的 OPLS-AA 对芳香酯缺三项参数（酯羰基碳的类别是 `C_2`，而相应条目写的是 `C`）：角 CA–C–OS、二面角 CA–C–OS–CT 与
    CA–CA–C–OS；补丁按同一文件中类别 `C` 的条目补上，数值与 GROMACS 发布的 OPLS-AA（`ffbonded.itp`）一致；
  - foyer 给与酯基相连的苯环碳 −0.115（苯的 C–H 值）而没有氢平衡，每条链净电荷 −0.805；按 OPLS-AA 对带取代基芳碳的惯例
    （取代基与环合起来呈中性，如苯腈 +0.035、硝基苯 +0.09、萘的稠合碳 0.0），酯基本身中性，故该碳取 0.0，补丁新增类型 `stk_ester_ipso`；
    补丁并入 foyer 的 `oplsaa.xml` 后整体加载（foyer 逐个文件校验，补丁不能单独引用原文件的类型）；之后每条链电荷为零、全部二面角有参数；
  - GMSO 写出 `atom_style full`、`real` 单位的数据文件；GMSO 写入倾斜行，LAMMPS 把盒子当作三斜，`kspace_style` 须放在 `read_data` 之后；
  - LAMMPS（22 Jul 2025 Update 6，单进程）：能量最小化 → 500 K NVT → 用 `fix deform` 逐步压缩到约 1.2 g/cm³（直接 5000 atm NPT
    在 4 ps 内从 0.25 压到 1.17 g/cm³，原子飞出、PPPM 报错）→ 500 K、1 atm NPT → 降温到 300 K → 300 K、1 atm NPT，共约 4.4 分钟；
    最后阶段后一半的平均密度 1.223 g/cm³（实验无定形 PET 约 1.335 g/cm³；4 聚体、羟基/醛基端基、540 原子、约 20 ps，偏低在预期之内，
    只说明工具链可用，不是可报告的结果）。
- **E1a（已交付，2026-10-10）**：LAMMPS 计算引擎（导入的算例按行在运行环境上运行），先从 Python 控制台与按行工作流使用。
  - 计算端 `python -m suan.lammps run|verify|check`：读准备时写入的 `stk-lammps-input.json`（脚本名与参数，命令行上不带算例文本），
    再次检查脚本，找程序（`--program` → 本机 STK 模块登记 → PATH 上的 `lmp`/`lmp_mpi`/`lmp_serial`），在算例文件夹中运行
    `lmp -in <脚本> -log log.lammps -nocite -var 名 值 …`，检查 `log.lammps` 后写 `stk-lammps.json`；LAMMPS 退出码为 0 不等于成功：
    日志须正常结束（`Total wall time`）、没有 `ERROR`、每段热力学输出完整且全部有限（NaN 记为 `numerical_failure`）；
  - 结果取最后一段热力学输出后一半的平均（密度、温度、压力、势能，以及全部列的平均与末值），单位制取自脚本的 `units`；
  - 参数：温度、压力、步数、时间步长、随机种子按 `-var` 传入；脚本可用 `variable temperature index 300` 给默认值（导入时读入行中），
    用了而没有默认值的须在行中填写，脚本没用到的须留空（脚本用到哪些参数随原始输入一起冻结，准备工作流运行时即检查每一行）；
    以其他样式定义这些变量会被拒绝（LAMMPS 会报错），默认值须是单个数（多个值的 index 循环在 `-var` 下只跑一次）；
  - 脚本检查：覆盖主脚本、`include`/`jump` 引用的全部文件（任意深度）以及 `if … then "…"`、`run … every N "…"` 中引号里的命令；
    拒绝 `shell`、`python`、`plugin`、`fix python/*`、`pair_style python`、`log`、`getenv` 与 `python` 变量、由变量拼出的命令名或变量样式，
    以及字面上的绝对路径、`~` 与 `..`；由变量拼出的路径不追踪。这是防误用与防止把脚本当作纯输入，不是沙箱（运行环境的客户端本来就能运行任何命令）；
  - 只读 `thermo_style one/custom` 的热力学输出；`multi`、`yaml` 明确报“不支持的输出格式”；运行改写了自己的输入文件时判为失败
    （否则收集时无法与冻结的计划核对）；被取消或超时（SIGTERM）时仍写出 `stk-lammps.json`；
  - 多进程：同 MuPRO 的本机 MPI 规则（共用 `suan/runtime/launch.py`）；LAMMPS 没有 MPI（`lmp -h` 显示 MPI STUBS）时拒绝多于 1 个进程，
    否则每个进程各自完整跑一遍、日志互相覆盖却显示成功——本机正是这样发现的：conda-forge 默认选到无 MPI 的版本，
    模块目录因此固定为与 MPICH 链接的 CPU 版本 `lammps=*=cpu*_mpi_mpich_*`（四个平台都有）；
  - 项目：`stk.lammps.import_case/clone_case/prepare/collect`，工作流模板 `lammps/1`（内置的第二个远程引擎，经 E0a 的按模板分派运行）；
    结果表“LAMMPS results / 分子动力学结果”；传给下游分析的最终状态是报告与算例文件夹中除轨迹（`*.dump`、`*.lammpstrj` 等或名字含 dump）
    以外的全部文件，超过 100 个时该步骤明确失败而不截断；收集时报告列出的输出必须都在运行环境中且内容一致；
  - 与 MuFerro 共用的项目辅助函数移入 `suan/workflows/common.py`。
  - 本机实测（手动，不进 CI）：真实 LAMMPS（22 Jul 2025 Update 6，MPICH 版）经项目工作流与本机运行环境跑 LJ 熔体两行（`lj` 单位）
    与 PET 模型两行（最小化 + 2 ps NVT，设定 450/550 K，平均 445.8/551.4 K）；2 进程运行时区域分解为 `1 by 1 by 2`、结果与单进程相同。
  - 尚未做（E1 后续）：桌面的导入按钮与按引擎的仿真视图（目前只有 MuFerro）、原子与键的显示（E1d）、
    运行中的监控事件、远程运行环境上的模块安装；单次下载上限 1 GiB（同 MuFerro），轨迹很大的运行暂时无法经工作流收集。
  - 交付前审查（独立代理，用真实 LAMMPS 复现）后的修正：引号中的命令（`if`、`run every`）与多层 `include` 原先不检查，`shell` 可经此执行；
    写在被包含文件中的参数原先读不到，行中无法设置；变量样式可由变量拼成 `getenv`；`thermo_style multi` 的正常运行被误判为输出被截断；
    最终状态按名字排序后截断到 100 个，会丢掉报告；工作流准备时不检查参数，空着的参数要到运行时才失败；运行改写输入后无法收集；
    `region shell`、`./` 路径与多行三引号被误拒；多值 index 默认值被接受。
- E0 其余部分（每个步骤各自的运行环境、桌面仿真视图按引擎显示、共用辅助代码移出 `muferro.py`、在远程运行环境上安装模块）：未实现，
  随 E1 按需要做。

## PET 参数决定（2026-10-12，所有者授权文献判断并直接执行）

- 已选择 PET 专用完整 OPLS-AA/MK 2022 参数，芳环碳 −0.115 e 与其他原子电荷共同中性；
  不沿用历史片段拼接后 −0.805 e/链，也不采用单独设 0.0 的推断。
  S1/S2 完整使用，S3/S4 精确项优先、缺项按固定 GROMACS v2025.3 补全；源未公开的设置、PPPM与improper属于明确的 STK 适配。
  COOH/OH 端基每链 22N+3 原子；末端氧 +0.001 e 修正、完整来源和适用范围见[参数说明](../pet-model.md)。
- 此授权只解决 PET 建模的参数选择，其他 S3/S2c 等待决定事项不自动解除。

- **建模的性能（已测，2026-10-10）**：6/12/24 条 4 聚体链（540/1080/2160 原子）——填充 0.7/3.0/3.9 秒，foyer 分配力场 5.4/10.7/21.5 秒，
  GMSO 转换 11.8/23.0/46.0 秒、写出 63.5/128.2/246.2 秒，随原子数线性增长，约 0.13 秒/原子几乎全在 GMSO；
  按此估计，接近文献规模的 PET 体系（约 9000 原子）仅写文件就要约 20 分钟。mBuild 1.4 已没有自带的 LAMMPS 写出器（移到了 GMSO）。
  建议 E1b 由 STK 直接从 foyer 给出的 ParmEd 结构写 LAMMPS 数据文件（原子、键、角、RB→OPLS 二面角、对势系数），
  以 GMSO 在 540 原子体系上的输出逐项对照验证；这不是所有者决定，记在此处供 E1b 设计。

## 所有者决定（2026-10-10）

1. **顺序**：先做计算引擎接口的通用化，再做 LAMMPS，再做 ABACUS。
2. **安装**：STK 集成常用软件的安装，作为可选模块由人选择是否安装；安装时先自动检测是否已有相应软件，
   已经装了就直接用、不再安装，没有才自动安装。
3. **PET 首先要算的性质**：四项都要——密度与玻璃化转变温度、力学性质（模量）、气体扩散/阻隔、电子结构与相互作用能。
4. **分子模型**：STK 集成开源的分子建模工具，用它们完成建模，这些工具本身也作为 STK 可加载的模块；
   同时也允许用户在其他软件中建好模型后直接导入。

## 分期（按决定修订）

### E0 计算引擎接口与模块管理

- **引擎接口**：同上文 E0（引擎协议与插件注册、按行工作流按模板分派、每个步骤各自的运行环境、桌面按引擎显示、MuFerro 迁移后行为不变）。
- **模块管理（新增）**：一个模块目录，列出可选模块及其许可、用途与所需磁盘：
  - 模块：LAMMPS、ABACUS（含赝势与轨道库）、分子建模（mBuild + foyer + GMSO，OPLS-AA；Packmol；RDKit；Moltemplate）；
  - 先检测：在 PATH、常见的 conda 环境、用户指定的目录中找可执行文件或 Python 包，记录版本、路径与是否支持 MPI；
  - 检测到就登记使用、不再安装；没有才由人确认后安装：STK 自带或下载 micromamba（单个静态程序，不需要管理员权限），
    在 STK 管理的目录中从 conda-forge 创建独立环境，可看进度、可取消；安装前显示软件的许可；
  - 模块装在**算的地方**：本机的模块由后台服务安装；运行环境（服务器或集群）上的模块以一个运行环境任务安装和检测；
  - 安装结果写入模块登记（版本、来源、环境路径、摘要），引擎的 `check` 与工作流都从登记中找可执行文件；
  - 以后：离线安装包（把 conda 包复制到没有外网的机器）。

### E1 LAMMPS 与分子建模（PET 的原子尺度）

- **建模模块**（可选模块，Python 侧运行）：
  - 用 mBuild 由重复单元建 PET 链；用 foyer 分配 OPLS-AA；用 Packmol 按目标密度填充无定形盒子，可加入 O₂、CO₂、H₂O 等小分子；
  - 已交付由 STK 写出器从 ParmEd 写 LAMMPS 文件，GMSO 仅作历史独立对照；生成后显式导入项目；建模参数（链长、链数、密度、小分子种类与数目、随机种子）
    是参数表中的一行，建模本身也是工作流中的一步；
- **导入**：用户在其他软件中建好的 LAMMPS 数据文件与脚本直接导入，规则同上文 E1。
- **四项性质中的分子动力学部分**各有一个分析：
  - 密度与玻璃化转变温度：按温度扫描的密度（或比体积）–温度曲线，两段直线拟合求拐点；
  - 模量：单轴拉伸的应力–应变曲线，取小应变段的斜率；
  - 气体扩散：小分子均方位移的爱因斯坦关系求扩散系数，并估算渗透性所需的量；
  - 每项都配一套 LAMMPS 脚本模板（平衡、降温扫描、拉伸、扩散），参数由参数表给出，结果写入结果表。
- **可视化**：查看器加原子与键（球棍）显示，读 LAMMPS 数据文件与轨迹。

### E2 ABACUS（PET 的电子尺度）

- 同上文 E2；结构来自建模模块（单体、二聚体、链段）、晶体结构文件或 LAMMPS 的构型。
- 电子结构：结构弛豫、能带与态密度、带隙。
- 相互作用能：二聚体与两个单体分别计算，E_int = E(AB) − E(A) − E(B)，作为一个三步的工作流（必要时加基组重叠修正）。
- 赝势与轨道库作为 ABACUS 模块的一部分安装和登记（SG15 ONCV 与配套轨道），按许可记录出处。

### E3 串联（多尺度）

同上文：ABACUS 的结构或相互作用能 → LAMMPS 力场的检查与校准；LAMMPS 的弹性与扩散 → 相场参数；在 E0–E2 稳定之后设计。

## 依据

- ABACUS：[源码与许可（LGPL-3.0）](https://github.com/deepmodeling/abacus-develop)、
  [安装（conda-forge、Docker）](https://abacus-develop.readthedocs.io/en/latest/quick_start/easy_install.html)、
  [接口（ASE、PyABACUS）](https://abacus-develop.readthedocs.io/en/latest/advanced/interface/index.html)、
  [赝势与轨道](https://abacus-develop.readthedocs.io/en/latest/advanced/pp_orb.html)。
- LAMMPS：[源码（GPL-2.0）](https://www.github.com/lammps/lammps)、[conda 安装](https://doc.lammps.org/Install_conda.html)、
  [Python 模块](https://docs.lammps.org/Python_install.html)。
- 建模工具：[mBuild、foyer 与 GMSO（MoSDeF）](https://github.com/mosdef-hub/mbuild/blob/c7f5868965d9191bbd3a4327dced9767a24e61bc/docs/index.rst)、
  [GMSO 写 LAMMPS 数据文件](https://github.com/CalCraven/gmso)、[mBuild 的 fill_box（Packmol）](https://mbuild.readthedocs.io/en/0.13.1/getting_started/quick_start/fill_box_example.html)、
  [NIST 聚合物构建扩展](https://pages.nist.gov/mbuild_polybuild/en/main/index.html)、[Packmol（MIT）](https://m3g.iqm.unicamp.br/packmol/download.shtml)、
  [Moltemplate](https://github.com/LL8848/moltemplate)、[RDKit（BSD）](https://en.wikipedia.org/wiki/RDKit)、
  [micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)；MoSDeF 各包的许可在 conda 上标为 MIT，安装前按仓库的 LICENSE 文件核对。
- PET 力场：[OPLS-AA 用于 PET 与玻璃化转变温度](https://pmc.ncbi.nlm.nih.gov/articles/PMC8951138)、
  [PET 的 Drude 可极化力场](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11741139/)、
  [常用力场对聚乙烯的准确度比较](https://ramprasad.mse.gatech.edu/wp-content/uploads/2023/12/accuracy_of_classical_force_fields_for_PE_structures_away_from_equilibrium.pdf)。
