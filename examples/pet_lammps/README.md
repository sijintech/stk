# PET → LAMMPS 可行性材料（E1，不是产品代码）

[多尺度引擎方案](../../docs/design/multiscale-engines.md)“E1 可行性”与“E1a”所用的脚本与输入，2026-10-11 从会话临时目录移入仓库，
供后续 E1b（建模步骤）与 E1c（分析模板）参考。**这里的 PET 模型只说明工具链可用，不是可报告的结果**：
与酯基相连的苯环碳电荷（补丁类型 `stk_ester_ipso`，0.0）是 STK 按 OPLS-AA 惯例推出的，等待所有者决定
（方案“需要所有者决定（E1b 之前）”）。

| 文件 | 内容 |
|---|---|
| `pet-oplsaa-patch.xml` | foyer OPLS-AA 的补丁：芳香酯缺的角 CA–C_2–OS 与二面角 CA–C_2–OS–CT、CA–CA–C_2–OS（数值取自 GROMACS 发布的 OPLS-AA，注释中有原行），以及 `stk_ester_ipso` |
| `build_pet.py` | mBuild 建 4 聚体链 → Packmol 松散填充 → foyer（补丁逐节并入 `oplsaa.xml` 后整体加载）→ GMSO 写 `atom_style full`、`real` 单位的数据文件；打印各步耗时 |
| `in.pet` | 完整的平衡流程：最小化 → 500 K NVT → `fix deform` 逐步压缩到约 1.2 g/cm³ → NPT 降温到 300 K（约 4.4 分钟，单进程） |
| `acceptance/` | 手动验收：真实 LAMMPS 经项目工作流与本机运行环境跑 LJ 熔体两行与 PET 两行；不在 `tests/` 下，CI 不收集 |

## 运行

需要 STK 模块“分子建模”（mBuild、foyer、GMSO、RDKit）、Packmol 与 LAMMPS（MPICH 版），可由桌面工作台“计算模块”安装，
或用已有的安装（STK 会检测）。下面的路径以本机开发环境 `/home/mnemora/opt/stk-modules/envs/` 为例，STK 自己安装的在 `~/.stk/modules/envs/`。

```bash
# 1. 建模（6 条链、540 原子约 80 秒，几乎全在 GMSO 写文件；--chains 12/24 可复现方案中的耗时测量）
<modules>/envs/molecular-modeling/bin/python examples/pet_lammps/build_pet.py --out examples/pet_lammps/acceptance/pet-case/pet.data

# 2. 直接用 LAMMPS 跑完整流程（kspace_style 须在 read_data 之后：GMSO 写入倾斜行，盒子按三斜处理）。
#    在另一个文件夹中跑：验收的算例文件夹里不能留下 log.lammps（导入时会被拒绝）
mkdir -p /tmp/pet-run && cp examples/pet_lammps/in.pet examples/pet_lammps/acceptance/pet-case/pet.data /tmp/pet-run/ && \
  (cd /tmp/pet-run && <modules>/envs/lammps/bin/lmp -in in.pet)

# 3. 经 STK 项目工作流的验收（仓库根目录；无 LAMMPS 或无数据文件时失败而不是跳过）
STK_LAMMPS=<modules>/envs/lammps/bin/lmp PYTHONPATH=tests env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  python -m pytest examples/pet_lammps/acceptance -p conftest --rootdir=examples/pet_lammps/acceptance -s -p no:cacheprovider
```

数据文件头含用户名与时间，`*.data` 不提交，按第 1 步重新生成。

## 已知的结果（2026-10-10/11，本机）

- 净电荷：未加补丁时每条链 −0.805；加补丁后为零。foyer 对 384 个反常二面角（improper）不给参数（OPLS-AA 的 RB 形式按 proper 处理）。
- `in.pet`：最后阶段后一半平均密度 1.223 g/cm³（实验无定形 PET 约 1.335；4 聚体、540 原子、约 20 ps，偏低在预期之内）。
- 直接 5000 atm NPT 从 0.25 g/cm³ 压缩会丢原子、PPPM 报错，所以用 `fix deform`。
- 验收：PET 两行设定 450/550 K，平均 445.8/551.4 K；2 进程区域分解 `1 by 1 by 2`，结果与单进程相同。
