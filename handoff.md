# STK 开发交接（Codex / Claude / 后续开发者）

更新：2026-10-13；材料数据闭环节点 1 已实施：内置 MuFerro/LAMMPS 桌面入口、数据字典及离线合成演练、厂内调用清单；当前提交 CI 见验收记录。
代码 `4f54d78` 已推送 main，Runtime **8/8**、桌面 **5/5**、文档与密钥扫描均已完成成功。
此前 PET 建模代码 `fbcd9f4` 的 Runtime 8/8、桌面 5/5、密钥扫描与文档均通过，实际测试数与新节点结果见验收记录。
`main` 还包含 E1 数据写出器 `057f96d`、E1c 分析 `6927e27` 与修正 `c17bb4b`、`be9bdd7`（CI 见验收记录）。本文是当前快照：状态、待所有者决定的事项、下一步、
代码入口与验证方法。较早的交付细节（工作台、技能目录、连线编辑、体验包、归档、可用性开发包、S1/S2/S3 各期）已移到
[开发交接记录](docs/development-log.md)与[开发计划](docs/development-plan.md)，测试与 CI 证据在[验收记录](docs/runtime-validation.md)。
接手时以实际 Git 状态和对应提交的 CI 为准，不把此处的快照当作永久状态。

所有者随后提供 PET 基弹性体研发与材料数据能力建设第 6 版方案，要求 STK 后续支持实施；路线文档 `b5fc3b7` 已推送，
Runtime 8/8、密钥扫描与文档站均已结束通过。
已读取正文与表格，新增[材料数据闭环路线](docs/design/pet-materials-data-loop.md)并纳入开发计划：
原始证据与样品状态、数据加工复核、PET 训练评价、受控自主任务、厂内全问题/聊天/派生查询及恢复移交。
路线提交为设计交付；所有者 2026-10-13 要求开始实施，本次节点 1 结果见下。项目格式仍为 13，端点/网络及智能体执行规则未变。
未将方案原稿/客户资料复制到公开仓库。

## 先读什么，先做什么

1. [AGENTS.md](AGENTS.md)：共同约定与**所有代理都必须遵守的规则**（密钥、测试环境变量、不发收费请求、推送前等上一个代码提交的桌面 CI、
   “合作方”称呼）。`CLAUDE.md` 只是 Claude 的入口，内容与 AGENTS.md 相同方向，不另立规则。
2. 本文，再看[开发计划](docs/development-plan.md)开头 **2026-10-08 思劲平台方向**一节（包括其中的“多尺度计算引擎”与“S3”条目）。
3. 产品决定在 `docs/design/`（多尺度见 [multiscale-engines.md](docs/design/multiscale-engines.md)），已发布协议在 `docs/specs/`；
   设计目标不是已实现功能。
4. 接手先检查工作区、当前提交、远端与 CI，保护别人的未提交改动：

```bash
git status --short --branch
git log -5 --oneline
git fetch origin main && git log --oneline HEAD..origin/main
gh run list --branch main --limit 6   # 看最近代码提交的 Runtime 与桌面 CI 是否已结束、是否通过
```

只有主工作树；历史分支 `docs/development-handoff`、`fix/desktop-transfer-resume` 与无关旧 PR 不属于待办，不合并也不删除。

## 现在的状态（2026-10-13）

| 方向 | 状态 | 入口 |
|---|---|---|
| 桌面与项目基线 | 原生桌面（GHOST/OpenGL/Vulkan/Metal）、项目格式 **13**（SQLite + 文件）、表格/参数扫描、保存分析、项目工作流（按行运行 MuFerro 与 LAMMPS）、归档、技能目录、工作台 | [开发计划](docs/development-plan.md)“当前基线”；`suan/project/`、`desktop/engine/lib/stk_app/` |
| S1 模型接入 | 全部交付：端点与密钥、数据标注与网络设置、本机一键部署（llama.cpp）、能力分档与自动切换 | [model-gateway.md](docs/design/model-gateway.md)；`suan/models/` |
| S2 智能体 | S2a、S2b 交付（格式 13 会话/事件/对象、8 个工具、签名批准、桌面“智能体（多步）”）；**真实模型的 GUI 人工验收未做** | [agent-harness.md](docs/design/agent-harness.md)；`suan/agent/` |
| S3 材料模型 | S3a 交付（P–E 回线、容量衰减；合成数据；PyTorch CPU 可选） | [materials-models-s3.md](docs/design/materials-models-s3.md)；`suan/materials/` |
| 多尺度引擎 | E0a、E0b、E1a、**E1b 写出器与 PET 本机建模、E1c 分析模板已交付**；PET 参数已按所有者新授权选择 | [方案](docs/design/multiscale-engines.md)、[写出器](docs/lammps-data.md)、[分析](docs/lammps-analysis.md) |
| PET 数据闭环节点 1 | MuFerro/LAMMPS 桌面导入、按冻结引擎处理运行及批次、离线热力学摘要；字典草案和全合成离线数据演练 | [桌面指南](docs/lammps-desktop.md)、[字典](docs/design/pet-data-dictionary.md)、[示例](examples/pet_data/README.md)、[厂内清单](docs/design/inplant-execution-baseline.md) |

## 待所有者决定（决定前不要按某个选项实现）

所有者 2026-10-11 16:46 UTC 要求至少 12 小时后再提请决策；按分钟向后取整，**2026-10-12 04:47 UTC 之前不提请决策**，
继续已有授权且不依赖这些选择的工作。这个时间不构成批准，也不自动选择任何选项。

所有者 2026-10-12 明确授权根据文献与公开资料判断并直接执行 PET，因此 PET 电荷不再待决定。
采用完整 PET OPLS-AA/MK 2022 适配方案：芳环 C −0.115 e，配套全部电荷/LJ；唯一末端醇氧的 +0.001 e 舍入修正明确记录，
不采用历史 0.0 推断。COOH/OH 六条四聚体为 546 原子，来源与限制见[PET 模型](docs/pet-model.md)。其他事项仍待决定。

1. **S3 下一步**：`stk.dataset/1` 两个数据格式要先交给合作方讨论；MuPRO 能否做电场扫描以产生相场回线待确认。
2. **S2c**（外部规划模型、智能体准备运行）视所有者决定。
3. **保存分析修改提案的持久形式**（较早的 P3 项，[建议](docs/design/review-drafts-and-conversations.md#保存分析修改提案的持久形式建议待所有者确认2026-10-06)）：仍待确认，目前未排期。

## 下一步（建议顺序，不依赖待决定事项的先做）

1. **E1b 写出器与 PET 建模已交付**：写出器保留传入电荷，支持 full/real、谐振键/角、RB→OPLS、三斜盒子，
   新增明确相位 180°/周期 2 的平面 periodic improper→CVFF，保留原子顺序，其他 improper 仍拒绝。
   `stk.lammps.create_pet_workflow` 建参数表与本机 `pet-model/1` 工作流；明确 start 后用已登记分子建模/Packmol 模块生成并冻结八项产物。
   文献参数、来源、文件摘要与每链中性校验随模型保存；取消停止 Python/Packmol，完整成功才发布，不覆盖已有目录。
   旧 540 原子 GMSO 对照保留为写出器夹具；新 COOH/OH 默认 546 原子不是同一个化学体系。
   操作见 [examples/pet_model](examples/pet_model/README.md)。生成后**显式导入** LAMMPS 算例，不声称自动串联本机模型与远程仿真。
   初始填充不是平衡样品；未分配气体参数，未验证 PET 材料性质。长链 DP≤20 只是构象生成资源上限，不保证成功或物性收敛。
2. **E1c 已交付**（只用导入算例）：三套脚本、四个图节点、三个预设与技能；Tg 密度两段拟合、模量小应变斜率、显式扩散窗口。
   合成曲线与真实氩的运行/分析归档通过；限制与使用见[指南](docs/lammps-analysis.md)。短轨迹拟合不代表材料性质验收。
   多温度 `density_series` 的来源随最终 Tg 诊断保存；日志任一段的重复列名拒绝，日志源实现版本 2 隔离旧缓存。
3. **桌面的 LAMMPS 入口（节点 1）**：内置引擎选择、指定主脚本、准备/日志/收集/离线查看与结果行导航；批次按引擎区分，资源选项在编辑器会话内各自保留。
   旧项目/引擎/成员回调失效，打开和重开不执行；目前仅热力学结果查看，球棍/轨迹仍是 E1d。
4. 之后：E1d 球棍显示、运行中的监控事件、远程运行环境上的模块安装 → E2 ABACUS（先查 conda-forge 的 MPI 变体，LAMMPS 默认无 MPI 的教训）→ E3 串联。
5. 与 E 系列并行、需要人参与的：S2 真实本机模型的 GUI 人工验收（[工作台清单](docs/workbench-acceptance.md)“AI 智能体（多步）”）；
   macOS/Windows 真机复核。
6. **PET 研发数据闭环**：按[新增路线](docs/design/pet-materials-data-loop.md)八节点推进，业务字典、导入样例与厂内部署设计可同 E1 并行。
   节点 1 已加入字典草案、普通表合成导入与厂内调用清单；下一步节点 2 厂内执行基线，见[清单](docs/design/inplant-execution-baseline.md)。
   可先做只读版本化部署清单与模型请求统一准入，覆盖自由问题、planner/子请求、发送前目标/策略复核与外部回退；
   用纯合成内容测试，不启用或改写实际端点/网络。Runtime/SSH、子进程/插件/下载及日志/备份仍须继续接入并做真实部署出口观测。
   企业内部数据/聊天接入前先验收厂内边界；公开表标注不能覆盖自由问题/派生查询的隔离要求。
   PET 数据集需新契约与批次分组评价；现有 S3a 随机样本划分和内存训练任务不满足该项目。
   自主训练需后续企业授权策略与新版工具；当前智能体仍不准备/开始运行，S2c 外部规划等其他待决定事项不解除。

## 多尺度引擎：LAMMPS 代码入口

导入的 LAMMPS 算例（输入脚本 + 它读的文件）成为“LAMMPS cases”表的一行，温度、压力、步数、时间步长、随机种子从脚本的 `index` 默认值读入；
行作为工作流步骤 `lammps/1` 在运行环境上运行；STK 检查 `log.lammps` 后把后一半的平均密度、温度、压力、能量写入“LAMMPS results”表。

| 从哪里改 | 入口 |
|---|---|
| 脚本检查（拒绝 shell/python/getenv/字面路径，任意深度 include 与引号中的命令） | [suan/lammps/script.py](suan/lammps/script.py) |
| 日志读取与判定（`Total wall time`、`ERROR`、NaN、`thermo_style multi/yaml` 不支持） | [suan/lammps/log.py](suan/lammps/log.py) |
| 计算端启动器 `python -m suan.lammps run|verify|check`、找程序、MPI 检查 | [suan/lammps/run.py](suan/lammps/run.py)、[spec.py](suan/lammps/spec.py)、共用 MPI 规则 [suan/runtime/launch.py](suan/runtime/launch.py) |
| 项目：导入/复制/准备/收集、最终状态 | [suan/workflows/lammps.py](suan/workflows/lammps.py)、与 MuFerro 共用的 [common.py](suan/workflows/common.py) |
| 原生仿真动作/引擎与离线查看 | [dispatcher](suan/workflows/native.py)、[桌面视图](desktop/engine/lib/stk_app/src/editors/project_simulation_view.cc)、[Python 验证](tests/test_workflow_native.py) |
| 模板注册 | [suan/workflows/templates.py](suan/workflows/templates.py) 的 `LammpsTemplate`（E0a 接口，外部引擎经 `stk.engines` entry point） |
| PET 本机建模、参数记录与工作流 | [suan/lammps/pet.py](suan/lammps/pet.py)、[pet_worker.py](suan/lammps/pet_worker.py)、[suan/workflows/pet.py](suan/workflows/pet.py)、[指南](examples/pet_model/README.md) |
| 数据写出（不分配电荷或力场） | [suan/lammps/data.py](suan/lammps/data.py)、[tests/test_lammps_data.py](tests/test_lammps_data.py)、手动对照 `examples/pet_lammps/compare_writer.py` |
| E1c 脚本/拟合/图预设 | [suan/lammps/analysis.py](suan/lammps/analysis.py)、[templates.py](suan/lammps/templates.py)、`suan/lammps/templates/*.in`、`suan/graph/presets/lammps-*.json`、[已知曲线测试](tests/test_lammps_analysis.py) |
| 模块目录（LAMMPS 固定 MPICH 版 `lammps=*=cpu*_mpi_mpich_*`） | [suan/modules/catalog.json](suan/modules/catalog.json)、[suan/modules/](suan/modules/) |
| 测试 | [tests/test_lammps.py](tests/test_lammps.py)、[tests/test_workflow_lammps.py](tests/test_workflow_lammps.py)、假 LAMMPS [tests/lammps_fake.py](tests/lammps_fake.py)、真实日志节选 `tests/data/lammps/pet-npt.log` |
| 手动验收（真实 LAMMPS，不进 CI）与 PET 可行性脚本 | [examples/pet_lammps/](examples/pet_lammps/README.md) |
| E1c 合成数据与真实路径（108 原子氩，非性质验收） | [examples/lammps_analysis/](examples/lammps_analysis/README.md) |

继续开发时须保留这些边界：

- LAMMPS 退出码 0 不等于成功：日志须正常结束、无 `ERROR`、每段热力学输出完整且全部有限；收集时重新校验日志并与冻结的输入与报告核对。
- 参数经 `-var` 传入；LAMMPS 中 `-var` 定义的 index 变量会让脚本里同名的 `variable X index V` 失效，以别的样式重定义会报错，
  所以参数变量只能是单值 `index`。脚本用到哪些参数随原始输入冻结。
- 脚本检查是防误用，不是沙箱；由变量拼出的路径不追踪。
- LAMMPS 没有 MPI（`lmp -h` 显示 MPI STUBS）时拒绝多于 1 个进程——conda-forge 默认的无 MPI 版本在 2 进程下会各自完整运行、日志互相覆盖却显示成功。
- 最终状态是报告与算例文件夹中除轨迹以外的文件，超过 100 个时明确失败、不截断；单次下载上限 1 GiB。

本机开发用的模块（仅此机器）：`/home/mnemora/opt/stk-modules/envs/{lammps,packmol,molecular-modeling}`（LAMMPS 22 Jul 2025 Update 6 MPICH 版；
mBuild 1.4.0、foyer 1.2.0、GMSO 0.17.0），`MAMBA_ROOT_PREFIX=/home/mnemora/opt/stk-modules/mamba`。STK 自己安装的模块在 `~/.stk/modules/envs/`。

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


## 验证状态与未解决问题

| 证据 | 结果 |
|---|---|
| 数据闭环节点 1 本机（2026-10-13） | Python 完整 **2598 passed、24 skipped**，最终 guard 定向 **28 passed**；Linux 原生 **1309/1309、无跳过**，含 4 新交互/16 截图；真实 LAMMPS 原生 **2/2**；离线字典例三 Python 版本各 **7/7**。打包/i18n/链接/暂存密钥扫描通过，当前提交 CI 见[验收](docs/runtime-validation.md) |
| E1b PET 本机建模（2026-10-12） | 完整 pytest 2569 passed、24 skipped（后加上限另定向）；最终定向 168 passed；独立真实模型/构象 5 passed、项目→LAMMPS 1 passed；原生定向 40/40。`fbcd9f4` 的 Runtime 8/8、桌面 5/5、密钥扫描与文档均通过，详见[验收记录](docs/runtime-validation.md) |
| E1a `1859ca7` 本机 | 完整 pytest（`-m "not perf"`）**2427 passed、24 skipped**；Python 3.11 相关 81 passed；工作流/仿真/模块/智能体 CTest **69/69** |
| E1a CI | [Runtime](https://github.com/sijintech/stk/actions/runs/38097721893) 8/8（3.12 2442 passed，3.11 与 3.14 各 2438）、[桌面](https://github.com/sijintech/stk/actions/runs/38097721844) 5/5、密钥扫描通过 |
| E1a 手动（真实 LAMMPS） | LJ 熔体两行与 PET 两行经项目工作流（设定 450/550 K，平均 445.8/551.4 K）；2 进程 `1 by 1 by 2` 与单进程一致；2026-10-11 用 `examples/pet_lammps` 重新运行，结果见[验收记录](docs/runtime-validation.md) |
| E1b `057f96d` | 写出器 19 项通过，正交/三斜 540 原子对照和真实能量/晶胞读回通过；[Runtime](https://github.com/sijintech/stk/actions/runs/38157976224) 8/8、[桌面](https://github.com/sijintech/stk/actions/runs/38157976221) 5/5、密钥扫描/文档 CI 通过 |
| E1c 初版 `6927e27` 本机 | 合成曲线与真实氩路径 3 passed；完整 pytest 2469 passed、24 skipped，最后新增单位检查定向 33 passed；原生定向 104/104（含技能 GL/Vulkan 截图）；首轮 CI 与修正见后续记录 |
| E1c 修正 `c17bb4b` | 重名表头拒绝、旧缓存隔离；本机完整 pytest **2483 passed、24 skipped**、Linux CTest **1289/1289、无跳过**；[桌面 CI](https://github.com/sijintech/stk/actions/runs/38162974612) **5/5**（macOS CPU 838/838、Metal 180/180）、[Runtime](https://github.com/sijintech/stk/actions/runs/38162974582) **8/8**，密钥扫描/文档通过 |
| E1c 多温度来源 `be9bdd7` | 完整 pytest **2485 passed、24 skipped**，3.11/3.14 各 108 passed、1 skipped，原生目录 7/7、真实氩三路径通过；[桌面 CI](https://github.com/sijintech/stk/actions/runs/38164654996) **5/5**（Linux 1289/1289、macOS CPU 838/838、Metal 180/180，无跳过）、[Runtime](https://github.com/sijintech/stk/actions/runs/38164655024) **8/8**，密钥扫描/文档通过 |
| E1c `6927e27` 首轮 CI | Runtime 8/8、密钥扫描与文档通过；桌面已结束，Linux 1285/1289、macOS CPU 837/838、Windows CPU 795/796，失败均为预设数量旧断言；已在 `c17bb4b` 修正并通过桌面 5/5，原始证据见验收记录 |
| 更早各期 | 见[验收记录](docs/runtime-validation.md)，每项含提交与 CI 链接 |

未解决：

- **E1 的限制**：桌面入口仅内置 MuFerro/LAMMPS；原子/轨迹查看未实现。PET 建模仅本机、需显式导入远程算例；运行中没有监控事件；远程运行环境上不能安装模块；轨迹很大时超出 1 GiB 下载上限。
  E1c 不自动判定平衡或扩散区，没有跨温度行自动汇总、Tg 置信区间、通用分子质心/多原点 MSD；OLS 误差不能当材料性质不确定度。
  历史 540 原子可行性模型密度 1.223 g/cm³（所引用实验约 1.335）、4 聚体、约 20 ps，只说明工具链可用；
  它不是本次 COOH/OH 默认 546 原子模型的物性验收，初始填充密度也不能当作平衡密度。
- **S2**：真实本机模型的 GUI 人工验收未做。

已知 Weston 问题：旧提交 `17ea194` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36737424406)
有一项 `wm_app_window_weston_csd` 在窗口检查/布局重载之后 **SIGSEGV (11)**；更早非 CSD 用例也曾异常退出。
本机连续 30 次未复现，本次 CI 两个用例都通过。根因未知，不能写成“环境问题”或“已修复”。
`3ed063d` 修的是诊断：包装层必须在子进程非零退出、信号或超时时输出 `FAIL:`，防止 CTest 的成功文字匹配掩盖失败。

调查入口：[run_with_display.py](desktop/tests/wm/run_with_display.py)、[包装层测试](desktop/tests/wm/test_run_with_display.py)、
[窗口用例](desktop/tests/wm/CMakeLists.txt)、[应用窗口冒烟](desktop/tests/wm/app_smoke.cc)。
需要定位时保留原始 `LastTest.log`、Weston 日志和信号/调用栈；不要通过取消测试、放宽判据或反复重跑覆盖原始失败。


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
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  --parallel 4 --timeout 600 --output-on-failure \
  --output-junit /tmp/stk-claude-full.xml
```

工作台/技能/布局/分析草稿定向回归（相关修改时使用；不需要每次文档修改都跑完整套件）：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
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

### Python 测试与密钥扫描

完整 Python 套件约 7.5 分钟（没有安装 xdist，不要加 `-n`）；LAMMPS 相关可先跑定向：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python -m pytest -q -m "not perf" -p no:cacheprovider
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_lammps.py tests/test_workflow_lammps.py tests/test_project_workflows.py tests/test_workflow_batches.py tests/test_modules.py
```

Python 3.11 与 3.14 的环境在 `/home/mnemora/opt/stk-venv311`、`/home/mnemora/opt/stk-venv314`（CI 测 3.11、3.12、3.14）。
新增内置模板时，`test_project_workflows.py` 与 `test_workflow_batches.py` 中固定的模板列表要一起更新。
提交前对暂存的改动做密钥扫描（gitleaks，规则在 `.gitleaks.toml`；本机没有全局安装时自行下载固定版本），CI 也会扫描：

```bash
git diff --cached | gitleaks stdin --config .gitleaks.toml --redact --no-banner
```

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
不要把开发助手（Claude、Codex）与 STK 产品的模型提供方混为一谈，也不要因此改换产品端点。

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


## 可直接给接手代理（Codex / Claude）的起始指令

> 请先读仓库根目录的 AGENTS.md 和 handoff.md，再看 docs/development-plan.md 开头“2026-10-08 思劲平台方向”一节与
> docs/design/multiscale-engines.md。核对 Git 与最近代码提交的 CI 后，继续多尺度引擎 E1：
> E1b 写出器、PET 本机建模与 E1c 三套分析已交付，下一步见本文；不要重新实现已完成内容。
> 所有者已授权按文献自主选择 PET 参数并执行，采用完整 OPLS-AA/MK 2022 适配方案；历史 0.0 不是新默认电荷。
> 读 docs/pet-model.md 和 examples/pet_model/README.md，区分初始填充、软件验证与尚未完成的物性收敛。
> S3、S2c 等其他事项仍待所有者决定，决定前不按未选项实施。
> 日常直接在 main 工作，不新建分支或合并无关 PR；测试时清空 STK_TOKEN_PLAN_API_KEY、取消 STK_TOKEN_PLAN_MODEL，不发收费的模型请求，
> 不读取或打印密钥；上一个代码提交的桌面 CI 结束后再推送新的代码。每个交付节点做 critical review，修复问题、测试，
> 更新 handoff.md、开发计划、开发日志与验收记录（写实际结果与剩余限制）后提交推送。
