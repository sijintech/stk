# LAMMPS 数据文件写出器

STK 可以直接将 foyer 返回的 ParmEd 结构写成 `atom_style full`、`units real` 的数据文件，不经过 GMSO。
写出器只序列化已经分配好的力场，不建链、不分配参数、不改电荷，不包含 PET 电荷的默认选择。

```python
from suan.lammps import write_data

# structure 是 foyer.Forcefield.apply(...) 的返回值。
write_data(structure, "system.data")
```

支持 Lennard-Jones、谐振键/角、可转换为 OPLS 的 Ryckaert–Bellemans 二面角。
ParmEd 数值的约定：长度 Å，能量 kcal/mol，角度 °，质量 amu，电荷 e；不推断或转换其他单位。
盒子是 `[a, b, c, alpha, beta, gamma]`，坐标须在 ParmEd 的标准盒子坐标系中。
支持正交与三斜盒子，原点为零，保留未包裹坐标；输出不含速度，脚本须显式初始化速度。

输入脚本需要设置相应势的样式：

```text
units real
atom_style full
boundary p p p
pair_style lj/cut/coul/long 9.0
pair_modify mix geometric
bond_style harmonic
angle_style harmonic
dihedral_style opls
special_bonds lj/coul 0.0 0.0 0.5
read_data system.data
kspace_style pppm 1e-4
```

`kspace_style` 放在 `read_data` 之后，输出包含三斜倾斜行（正交盒子也写零倾斜）。
截止半径、长程精度、尾项修正等由输入脚本负责，不属于数据文件。
物理势的约定见 [LAMMPS OPLS](https://docs.lammps.org/dihedral_opls.html)、
[三斜盒子](https://docs.lammps.org/Howto_triclinic.html)和 [read_data](https://docs.lammps.org/read_data.html)。

类型按完整的实际数值参数合并；电荷逐原子保留，即使同一 LJ 类型的电荷不同也不混淆。
分子编号取键图的连通分量，避免把多个链或一个多残基分子错误地解释为 ParmEd 的 residue。
这是与 GMSO 在 PET 可行性示例上的有意差异：GMSO 把默认同名 residue 中的六条链都标为分子 1，STK 标为六个分子。
写出先验证完整结构，再原子替换目标文件；验证失败不改现有文件，不修改输入对象。

周期二面角、已分配参数的 improper、Urey–Bradley、CMAP、NBFIX、自定义排除或不等价于 OPLS 的非键合例外均拒绝。
foyer 的标准 1–2/1–3 排除与半强度 1–4 例外会逐项核对。
未分配参数的 improper 默认也拒绝；只有使用者显式传入 `allow_untyped_impropers=True` 才能忽略，数量记在文件注释中。
foyer 的 RB 系数可能带舍入常数：每个二面角允许不超过 `5e-6 kcal/mol`，累计省略的常数记在文件注释中；
更大的常数或非零五次项不支持，不能宣称保留了任意 RB 势的绝对能量。

手动对照脚本与说明在 [PET 可行性示例](../examples/pet_lammps/README.md)。
它逐原子核对质量、LJ、电荷、坐标，逐键/角/二面角核对成员与系数，核对盒子、类型合并与分子连通关系。
GMSO 降低了输出精度，容差按其实际输出精度设置；真实 LAMMPS 的 `run 0` 能量比较先统一两文件的坐标与盒子，
以区分势系数误差与初始重叠构型对坐标舍入的放大。该对照不是 PET 参数或材料性质的验收，电荷仍待所有者决定。

三斜盒子的对照还发现 **GMSO 0.17.0 的错误**：它将 dump 格式的外包围边界写进 data 文件头，
LAMMPS 实际读出的体积为 45648.625 Å³，输入晶胞应为 29188.420 Å³（540 原子夹具，角度 80°/85°/75°）。
STK 按 data 文件约定写晶胞边界，真实 LAMMPS 读回六个晶胞参数与 ParmEd 输入一致；不复制 GMSO 的这个错误。
对照报告保留原始 GMSO 文件头与真实读回值，逐项比较其意图表达的晶胞时显式撤销外包围边界扩展。
