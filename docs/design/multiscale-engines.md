# 多尺度计算引擎：ABACUS（第一性原理）与 LAMMPS（分子动力学）（方案，所有者已决定）

2026-10-10。所有者：思劲最近有一个 **PET 基材料设计项目**，需要第一性原理与分子动力学计算；这两类计算资料多、开源软件多，
STK 应优先支持，先融合开源的 **ABACUS** 与 **LAMMPS**，做成相场（MuPRO）之外的另外两个插件或功能模块，体现整个系统是多尺度的。
本文是方案，**均未实现**；所有者 2026-10-10 的决定见“所有者决定”，按决定修订的分期见“分期（按决定修订）”。

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
  - 由 GMSO 写出 LAMMPS 数据文件，作为一个 LAMMPS 算例导入项目；建模参数（链长、链数、密度、小分子种类与数目、随机种子）
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
