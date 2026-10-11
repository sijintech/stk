# LAMMPS：Tg、模量与扩散分析（E1c）

2026-10-11。三套脚本与分析用于**已经建好、已分配力场的外部算例**，不选择 PET 电荷或生成 PET 模型。
数值结果是给定模拟协议与拟合窗口下的估计；软件路径通过不等于材料性质通过。
节点的单位、参数、拒绝条件见[版本化契约](specs/lammps-analysis-v1.md)，
可复现的合成曲线与真实 LAMMPS 路径验收见[示例](../examples/lammps_analysis/README.md)。

## 运行脚本

`suan.lammps.templates.template_text("tg" | "modulus" | "diffusion")` 返回随包安装的脚本。
把脚本写入一个新算例目录，并提供 `model.in` 与其读取的模型文件：

```python
from pathlib import Path
from suan.lammps.templates import template_text

case = Path("/absolute/new/case")
case.mkdir()  # 已有目录报错，避免覆盖算例
(case / "in.modulus").write_text(template_text("modulus"), encoding="utf-8")
# 在此目录提供 model.in、system.data 等外部模型文件，再明确导入。
```

`model.in` 设置 pair/bond/angle/dihedral/improper/kspace 等实际需要的样式、非键合规则与 `read_data`。
它必须与模型匹配。模板已设置 `units real`、`atom_style full`、三维周期边界；不适用于其他单位或边界条件。
模板的阻尼时间为 100/1000 fs，默认步数与时间步仅为起点，不能替代体系稳定性、平衡和收敛检查。
导入文件须遵守 E1a 的脚本与相对路径规则；脚本检查不是沙箱。

在桌面 Python 控制台中明确执行：

```python
row = stk.lammps.import_case(case, script="in.modulus",
                           expected_revision=stk.project.info()["revision"])
```

导入后在参数表中检查、调整参数；用工作流的 `lammps/1` 步骤按行准备与运行。
共用参数是温度 K、压力 atm、生产步数 `steps`、时间步 fs、随机种子。
新增 `equilibration_steps`、`sample_interval`，模量另有 `strain_rate`（1/fs），扩散另有 `solute_type`（原子类型整数）。
正整数/正数和至少三个采样间隔在准备时检查；旧 E1a 表在读取/准备时不升级，显式导入或复制才补齐新字段。
既有冻结运行计划保留原来字段与参数形状。

## 三个分析

| 性质 | 模板产物与输入单位 | 拟合与输出 |
|---|---|---|
| Tg | 多个温度行的 `log.lammps`；汇总为 `Temperature: K, Density: g/cm3` | 两段递减直线交点，输出 K；高温段须更陡，交点须在分段间隙内 |
| 拉伸模量 | `stress-strain.dat`，`Strain: 1, Stress: GPa` | 小工程应变窗口内的自由截距 OLS 斜率，输出 GPa |
| 扩散 | `msd.dat`，`Time: fs, MSD: Ao2` | 显式时间窗口内的斜率除以 `2d`，乘 0.1 得 cm²/s |

Tg 模板在每个独立温度行 NPT 平衡后重置步数，再运行 NPT 生产段。E1a 的结果表已经返回末段后一半的平均温度和密度；
也可用 `density_series({"来源标签": 日志文本, ...})` 创建带来源与采样数的 STK Table。
这是固定的后一半平均规则，**没有自动判定平衡**。保存原始冻结日志，检查时间历史、平衡长度、独立重复与温度路径。
当前模板不是连续降温模拟；需按研究协议准备状态和温度序列。至少每段三温度，重复温度需先显式汇总。

模量模板先 NPT 平衡，再控制 y/z 压力、沿 x 按恒定工程应变率拉伸；拉伸应力为 `-pxx * 0.000101325` GPa。
应力以当前体积计，包含全体系的动能与 virial 项（[LAMMPS 压力张量](https://docs.lammps.org/compute_pressure.html)）。
自由截距保留预载/残余应力；默认拟合 `[0, 0.02]`，必须检查线性区与应变率效应。
模板输出的是有限温度与有限应变率的拉伸响应，不直接声称静态杨氏模量。

扩散模板先 NPT 平衡，生产阶段用固定盒子的 NVT；`compute msd ... com no average no` 使用展开坐标与一个时间原点。
不扣除溶质组自身平移，以免单个溶质的位移被清除。需检查全体系漂移，且所选类型须存在。
选择每个小分子的一个代表原子类型，或明确报告原子平均 MSD；**尚无通用分子质心 MSD、多时间原点平均或漂移自动校正**。
模板输出三个方向的 MSD 总和，使用 `dimensions=3`；手动换成单方向/平面 MSD 后，分析维数也须相应改变。
`time_min/time_max` 必须填写，默认 null 在执行时拒绝；检查弹道/暂态结束及长时近似线性，不能只凭正斜率确认扩散。

## 图预设、技能与工作流

`lammps-tg`、`lammps-modulus`、`lammps-diffusion` 都使用文件绑定 `data`，
输出 `summary`（一行数值）、`fit`（数据与拟合线）、`diagnostics`（范围/残差/方法）与 `plot`。
只请求前三项需要 NumPy；绘图另需 matplotlib。无需 LAMMPS、分子建模模块、模型服务或网络即可分析已保存数据。
它们在只读技能库中对应 `stk.lammps.tg@1`、`stk.lammps.modulus@1`、`stk.lammps.diffusion@1`。

```sh
suan graph run lammps-modulus --bind data=/absolute/results \
  --param strain_min=0 --param strain_max=0.02 --out /absolute/new/modulus-output
suan graph run lammps-diffusion --bind data=/absolute/results \
  --param time_min=1000 --param time_max=10000 --out /absolute/new/diffusion-output
```

保存分析可使用 `load_preset("lammps-modulus")` 得到图，沿用 `stk.analysis-document/1` 与已有保存/准备接口。
在项目工作流中，把分析的 `data` 输入接到仿真步骤的 `files` 输出，设置 `path="case/stress-strain.dat"` 或 `"case/msd.dat"`。
按行冻结脚本、参数与文件后运行下游分析；修改当前窗口或参数不会改写旧结果。
Tg 需要跨温度行的汇总表，当前按行工作流不自动把多个行的产物合并；明确汇总后再运行 Tg 预设。
`stk.source.lammps_log@1` 可直接读取一个正常结束的 real 单位 thermo 段（默认最后一段），不拼接重置后的步数。

结果保留来源文件与 SHA-256，显示 `md_fit_limits`：MD 采样相关，OLS 标准误差只是拟合描述，
不是独立重复的误差条或材料性质置信区间；Tg 也没有置信区间。
非法单位、缺点、NaN/Inf、零/负斜率、不合格分段或窗口直接失败，不静默删除数据。
CSV/列文件的表头必须唯一，规范化后重名也拒绝；不会用重复的后一列覆盖前一列。
上限为一般拟合 100000 行、Tg 500 温度、日志 256 MiB。

这些入口不实现桌面的 LAMMPS 导入按钮、自动 PET 建模、球棍显示或轨迹分析。
PET 酯基苯环碳电荷仍待所有者决定；历史可行性夹具中的 0.0 不是定论。
