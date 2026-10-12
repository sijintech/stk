# PET 建模与项目工作流

本例使用版本化的 `stk.pet.opls-mk2022/1` 参数，建立干燥、未离子化、COOH/OH 端基的线性 PET 初始盒子。
采用论文的完整电荷方案及明确记录的键合参数补全，不沿用旧可行性脚本中单独把酯基苯环碳设为 0.0 的推断。
来源、末端氧的 0.001 e 舍入修正、单位约定与适用限制见[PET 模型说明](../../docs/pet-model.md)。

默认六条四聚体共 **546 原子**；旧 [540 原子可行性体系](../pet_lammps/README.md)采用不同端基，保留为历史写出器对照。
建模成功说明初始结构、参数与文件路径通过检查；它不代表密度、Tg、模量或气体阻隔性质已经收敛。

## 准备模块

在桌面工作台“计算模块”中检测或安装 **分子建模**与 **Packmol**；运行模拟还需要 LAMMPS。
这些模块位于本机，PET 构建不上传结构、不调用模型服务，也不在刷新或打开项目时自动执行。
分子建模环境自带 Packmol 包，但独立的 Packmol 模块仍须检测并登记实际程序位置。
模块的检测、安装与运行环境范围见[多尺度方案](../../docs/design/multiscale-engines.md)。

开发验收或终端运行时，先按仓库约定隔离产品模型配置：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  python -m suan.scripting.headless --state-dir /tmp/stk-pet-example-state
```

桌面 Python 控制台已经提供 `stk`。终端控制台中可以创建并选择一个新项目；目录必须适合创建项目：

```python
p = stk.use(stk.projects.create("~/STK Projects/pet-example", "PET example"))
```

## 创建参数表，明确开始建模

```python
from uuid import uuid4

p = stk.project
made = stk.lammps.create_pet_workflow(
    expected_revision=p.snapshot()["project"]["revision"],
    rows=[
        {"chain_length": 4, "chain_count": 6, "packing_density": 250, "seed": 4928459},
        {"chain_length": 4, "chain_count": 6, "packing_density": 250, "seed": 42},
    ],
)

run = p.workflow_runs.prepare(
    made["workflow_id"], made["record_ids"], run_id=str(uuid4()),
    expected_revision=made["revision"],
)
p.workflow_runs.start(run["id"])
```

创建助手只保存普通参数表与 `cases → model` 工作流，不执行建模。`prepare` 冻结选定行，`start` 才运行本机模板 `pet-model/1`。
模板在独立的分子建模 Python 中使用 RDKit、mBuild、Packmol、Foyer 与 STK 数据写出器；无需 Runtime 连接。

| 参数 | 含义与限制 |
|---|---|
| `chain_length` | 每链的 PET 单元数，2–20；全链 RDKit 构象生成有独立资源边界，长链不保证成功 |
| `chain_count` | 链数，1–1000；整个盒子不超过 50000 原子 |
| `packing_density` | **初始填充**密度，1–2000 kg/m³；250 kg/m³ 等于 0.25 g/cm³，不是平衡密度或材料预测 |
| `seed` | 1–2147483647 的整数，同时控制构象与填充；改变种子生成独立初始模型 |

参数表可以继续编辑和扫描。已经准备的运行使用其冻结值；编辑参数后，应重新准备一个运行。
Packmol 只移动已有链构象；链构象无法装进指定盒子、填充失败或参数不匹配时，任务明确失败，不发布部分模型。
单次建模有 30 分钟时间预算和文件大小限制；取消会停止本机 Python 及其 Packmol 子进程。

查看状态或取消：

```python
state = p.workflow_runs.get(run["id"])
for task in state["tasks"]:
    print(task["row"], task["status"], task.get("error"))

# 需要停止本次建模时：
# p.workflow_runs.cancel(run["id"])
```

某一行失败不阻止其他行。再次 `start` 只重试未成功的任务，并使用新的 `attempt-N` 目录。
关闭后重新打开项目，用 `workflow_runs.list/get` 找到保存的运行；服务重启造成无人执行的尝试时，先 `recover` 再明确开始。
已成功模型与输入快照保留，不因刷新、重开或重试其他行而重建。

## 查看产物并显式导入 LAMMPS 案例

成功任务的 `produced` 包含项目内相对目录、输入快照 ID 与全部文件记录。
目录为 `results/workflow-runs/<运行 UUID>/row-N/model/attempt-N`，完整输出如下：

| 文件 | 内容 |
|---|---|
| `pet.data` | 初始填充状态，LAMMPS `atom_style full` / `real`，含电荷与全部写出的参数 |
| `model.in` | 力场样式、几何混合、1–4 缩放、长程静电与 `read_data pet.data` |
| `forcefield.xml` | 本次使用的实际 Foyer XML；显式平面 improper 的补全规则另见 JSON |
| `pet-model.json` | 完整参数来源、版本、摘要、组成、电荷、软件与构建审查；保存其对应文件哈希 |
| `in.pet` | 初始最小化、NVT/NPT 松弛示例；输出 `equilibrated.data` 的名字不构成平衡验收 |
| `in.tg`、`in.modulus`、`in.diffusion` | E1c 分析对应的运行模板，需先准备适当的已平衡模型 |

所有八个文件都由项目工作流登记并冻结。`pet-model.json` 记录其余产物摘要；JSON 自身的摘要由项目快照记录，避免自引用哈希。
发布前重新核对冻结参数、整套版本化力场、XML 与实际产物摘要、组成及逐链中性电荷；不一致的报告不会成为成功模型。
生成目录先暂存，完整成功后才原子发布；已有目录不会被覆盖。请保留原始生成产物与快照。

将已确认成功的一行导入为普通 LAMMPS 案例，显式指定脚本：

```python
from pathlib import Path

state = p.workflow_runs.get(run["id"])
task = next(t for t in state["tasks"] if t["status"] == "succeeded")
info = next(info for info in stk.projects.list() if info["handle"] == p.handle)
case = Path(info["directory"]) / task["produced"]["directory"]
imported = stk.lammps.import_case(
    case, script="in.pet", expected_revision=p.snapshot()["project"]["revision"],
)
```

生成目录含多份输入脚本，省略 `script` 会因入口不明确而被拒绝。
导入会复制并冻结案例文件，然后可通过已有 `lammps/1` 工作流或 `stk.lammps.prepare`、项目运行操作提交到 Runtime。
本次本机构建工作流不会自动把文件串联到远端 LAMMPS；导入、选择运行环境、准备与开始仍需明确执行。
详细路径见 [Python 运行接口](../../docs/scripting.md#运行模拟与取得结果)与[项目工作流](../../docs/project-workflows.md)。

## 性质分析前还需完成什么

初始松散盒子需要适当的退火、逐渐致密化与足够长的平衡过程；检查密度、能量和结构的稳定性，比较链长、体系大小与独立种子。
之后复制案例，在新的 `model.in` 中读取经检查的最终构型，保留本次力场、来源与原始快照；不要改写旧运行。
原论文与当前 LAMMPS 模板的温控、压控和静电处理存在差别，不能声称精确复现论文。

纯 PET 模型没有 O₂、CO₂、水等渗透小分子。直接运行 `in.diffusion` 的 PET 原子组 MSD 不会给出气体扩散或阻隔性质。
含气体系需要另选可兼容、来源明确的小分子与交叉参数，并检查分子质心、多时间原点与扩散窗口。
现有 Tg、模量、扩散拟合入口及其限制见[分析指南](../../docs/lammps-analysis.md)。

## 验证

标准库参数资源与工作流检查：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  python -m pytest tests/test_pet_profile.py tests/test_pet_worker.py tests/test_workflow_pet.py -q -p no:cacheprovider
```

`acceptance/test_improper_energy.py` 使用真实 LAMMPS、ParmEd 与 OpenMM，独立核对四原子的平面 improper 势能及全部力分量；
它不进入普通测试发现，也不验证 PET 物性。手动运行时提供真实程序，使用含这些依赖的 Python：

```bash
PYTHONPATH=. STK_LAMMPS=/path/to/lmp STK_PACKMOL=/path/to/packmol \
  env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  /path/to/molecular-modeling/bin/python -m pytest \
  examples/pet_model/acceptance/test_improper_energy.py \
  examples/pet_model/acceptance/test_model_energy.py \
  examples/pet_model/acceptance/test_geometry.py -q -p no:cacheprovider
```

实际交付结果、完整 PET 路径验收和剩余限制以[验收记录](../../docs/runtime-validation.md)为准。

实际模块与项目冻结/导入/Runtime 路径另用核心环境运行：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= PYTHONPATH=.:tests \
  STK_MOLECULAR_PYTHON=/path/to/molecular-modeling/bin/python \
  STK_PACKMOL=/path/to/packmol STK_LAMMPS=/path/to/lmp \
  python -m pytest -p conftest -p no:cacheprovider \
  examples/pet_model/acceptance/test_workflow_real.py -q
```

手动验收缺少真实程序/依赖时失败，不以跳过作为通过。分子环境若没有 pytest，需使用已有的测试依赖；
开发机可把核心环境的同版本 site-packages 加到 PYTHONPATH，并设 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1。
非周期 OpenMM 参考与相同非周期 LAMMPS 比较；生成的 PPPM 案例另行读回，两个 Hamiltonian 不混比。
原始近乎平面的二聚体受 LAMMPS OPLS 正弦分母保护影响；能量仍一致，全力精确比较使用明确记录的微小扰动，原始差异保留。
公开报告见 [validation](validation/)，不是收敛材料性质结果。

参数方案按版本发布；未来改变物理参数须新增版本，不能覆写已发布 profile 1。准备时冻结的是行参数与工作流，
安装的分子软件不是二进制快照；实际版本、Packmol 程序摘要、完整参数与模型文件在成功产物中记录。
