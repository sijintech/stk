# PET 分子模型：文献来源、参数适配与科学验证边界

2026-10-12 确定建模参数，2026-10-14 新增专用分阶段研究与 O₂ 示踪协议。
所有者授权 STK 根据文献与公开资料选择 PET 参数方案并实施，原先等待苯环碳电荷决定的事项已解除。
采用版本化的 **STK PET OPLS-AA/MK 2022 适配模型**（`stk.pet.opls-mk2022/1`），
用于干燥、无定形、未离子化、COOH/OH 端基的线性 PET。它是可追溯的建模基线，**不是已经验证的 PET 材料性质模型，也不是论文的精确复现**。
实现、测试与 CI 的实际交付状态以[开发计划](development-plan.md)和[验收记录](runtime-validation.md)为准。

## 为什么选择整套参数，而不是单独把苯环碳设为 0.0

主要来源是 Sangkhawasi 等的 [All-Atom Molecular Dynamics Simulations on a Single Chain of PET and PEV Polymers](https://doi.org/10.3390/polym14061161)，
Polymers 2022, 14, 1161。该研究以 PET 三聚体的 B3LYP/6-31+G(d) 结构和 Merz–Kollman（MK）电荷为基础，
区分链头、内部和链尾；补充材料 S1 给电荷，S2 给 LJ 与质量，S3 给键和角，S4 给二面角。
其 PET 电荷与 foyer 内置 OPLS-AA 的电荷并不相同。

论文中全部芳香碳，包括与酯羰基相连的 ipso 碳，都是 **−0.115 e**。内部乙二醇亚甲基碳为 +0.190 e，
酯羰基碳为 +0.625 e；它们与氧、氢及芳环的电荷共同使内部重复单元中性。
因此 −0.115 并不是这里的错误，错误是将不同方案中各自不平衡的片段混在一起。
旧可行性模型的 0.0 是 STK 当时的中性化推断，没有这个 PET 文献表的支持，不进入新默认模型。

选择该方案也便于本地复现参数来源：公开补充表足够明确，可随模型保存实际使用的 XML 和摘要，
不需要把项目结构上传到外部参数生成网站。[LigParGen 官方工具](https://jorgensenresearch.com/ligpargen)
提供另一种与 OPLS 配套的 CM1A/CM1A-LBCC 电荷方案；它使用 BOSS 计算，
不等于已安装的 mBuild/foyer 自带本地电荷算法，也不提供替换某一个 PET 原子电荷的理由。

## 链端、组成与电荷修正

模型沿 `HOOC–苯环–COO–CH₂–CH₂–…–OH` 连接，链端是一端羧酸、一端羟基。
每条含 N 个 PET 单元的链具有 `C(10N) H(8N+2) O(4N+1)`，即 **22N+3 个原子**。
三聚体是 69 原子，四聚体是 91 原子；六条四聚体合计 **546 原子**。
旧 [540 原子写出器对照](../examples/pet_lammps/README.md)采用羟基/醛基端基，多尺度工具链的历史验收保留原状，
不能把它解释成相同端基、相同化学体系的新模型电荷对照。

| 局部化学环境 | S1 电荷（e） | STK 使用值 |
|---|---|---|
| 芳环 C / 芳环 H | −0.115 / +0.115 | 原值 |
| 酯羰基 C / 羰基 O / 单键酯 O | +0.625 / −0.430 / −0.330 | 原值 |
| 与酯 O 相连的 CH₂ 碳 / 氢 | +0.190 / +0.030 | 原值 |
| 羧酸端 C / 羰基 O / 羟基 O / 羟基 H | +0.635 / −0.440 / −0.530 / +0.450 | 原值 |
| 末端醇 CH₂ 碳 / 氢 | +0.145 / +0.060 | 原值 |
| 末端醇 O / H | −0.566 / +0.300 | **O 改为 −0.565，H 原值** |

S1 印刷精度下，链头 23 原子合计 +0.250 e、内部 22 原子合计 0、链尾 24 原子合计 −0.251 e，
总计每链 −0.001 e；正文的中性说明与表格舍入存在这一残差。
STK 只给每条链唯一的末端醇氧增加 **0.001 e**，记录原值 −0.566 和使用值 −0.565。
这是明确的 STK 舍入修正，没有重算 MK 电荷；不修改芳环电荷，不通过减去全链平均值掩盖类型错误，
也不使用周期静电的均匀背景来补偿本应中性的 PET 链。

## 参数来源与适配规则

版本资源在 [JSON 参数记录](../suan/lammps/forcefields/pet-opls-mk2022-v1.json)
和[独立 Foyer XML](../suan/lammps/forcefields/pet-opls-mk2022-v1.xml)。
XML 使用完整 PET 电荷与 S2 LJ，不加载或合并 foyer 默认 `oplsaa.xml`。
平面 improper 由建模 worker 按 JSON 中的明确元组另外加入；仅加载 XML 不构成完整模型。
只为 PET 的规定端基和连接关系定义类型，不能用于任意芳香酯、改性 PET、离子或混合物。

1. **S1 与 S2 按完整方案使用。** 电荷按局部化学环境区分酸端、醇端和内部；原子质量及 LJ 的 σ、ε 来自 S2。
   例如 S2 酯羰基 C 的 ε 为 0.066 kcal/mol，单键酯 O 为 σ=2.900 Å、ε=0.140 kcal/mol，
   不能保留 foyer 内置的另一组非键合参数后声称采用这篇论文的模型。
2. **S3/S4 中存在的精确类型项优先。** S3 谐振势写成 `U=½kΔ²`，
   ParmEd 与 LAMMPS harmonic 的系数取该表 k 的一半；长度与能量转换分别按 nm↔Å、1 kcal=4.184 kJ。
   S4 的 cos3 直接转换成 OPLS/RB，不改变奇数项符号约定。
3. **遗漏项明确补全。** 以三聚体实际拓扑逐项枚举，S3 缺 1 种键、6 种角，S4 缺 7 种 proper 二面角；
   补全来自固定 [GROMACS v2025.3 OPLS-AA ffbonded.itp](https://raw.githubusercontent.com/gromacs/gromacs/v2025.3/share/top/oplsaa.ff/ffbonded.itp)。
   仅在查找这些键合项时声明 `CO→C`、`OES→OS`、`HAE→HC`；不把这些别名用于电荷或 LJ。
   GROMACS 中 `CO` 是缩醛碳，不能按 PET 表里的 `CO` 名称直接查找。
   每项记录源行与数值；芳环氢二面角来源的 `X–CA–CA–X` 在模型中展开为明确的 `HA–CA–CA–HA`，
   不在运行时用通配项掩盖缺参数。
4. **不猜补充表的未说明项。** S4 印刷的 `OS–CT–CT–OES` 不是该 PET 类型图中的实际组合；
   `HC–CT–CT–OH` 同样不对应 S1 的实际 PET 链端类型。
   STK 不把它们静默重命名为 PET 项，实际缺失组合使用上述明确的 GROMACS 补全。
5. **平面 improper 是额外适配。** 补充表未列 improper；GROMACS OPLS 给出保持羰基与芳环平面的周期项。
   STK 使用相位 180°、周期数 2 的显式平面 improper，并记录它们的 GROMACS 来源，
   经[写出器](lammps-data.md)写成 CVFF improper。不能由表格未列 improper 推断 OPLS 不需要它们，
   也不能声称这就是作者 DL_POLY 中未公开的具体设置。

OPLS 非键合组合采用几何混合，1–2/1–3 非键合排除，1–4 LJ 与 Coulomb 均缩放为 0.5。
RB 使用 `ψ=φ−π` 的约定；GROMACS 原始五位小数系数可能产生约 2.39×10⁻⁶ kcal/mol 的单项常数舍入残差，
STK 保留原始 RB 系数和写出器记录，不将其误认为力场缺项。
函数形式与单位约定见 [GROMACS 2025.3 键合相互作用手册](https://manual.gromacs.org/2025.3/reference-manual/functions/bonded-interactions.html)。

## 构建与发布检查

PET 全链 SMILES 在本机以固定种子的 ETKDGv3 默认模式构象化；失败后用同种子随机坐标模式，随后做有限步 UFF 初始松弛，
直接保留坐标转换为 mBuild 粒子与键，不经会再次嵌入的 `from_rdkit`。UFF 只准备初始几何，不替代 PET 的生产力场。
首版链长 2–20；DP100 的距离矩阵前处理在内部 timeout=45 秒下仍持续超过 3 分钟，已由外部停止，未当作成功或算法返回失败。
因此 RDKit 的内部 timeout 不能视为整个构建的硬墙时限；产品启动器的 30 分钟外部预算与取消负责停止整个进程组。
Packmol 使用已登记的具体程序，按初始质量密度填充周期盒子。
Foyer 返回的 ParmEd 结构可能保留输入元素库质量，worker 因此明确换用 S2 质量，并在报告保存原始输入质量。
源软件、Packmol 程序摘要、完整 XML/参数定义与七份输出摘要随模型保存；JSON 自身的摘要由项目快照保存。
初始密度按实际写出晶胞计算，不能把请求密度当作材料预测。

程序拒绝 Packmol 的不完善填充回退，并独立检查周期互链/自镜像重叠；整个构建有时间与日志上限。
成功输出先暂存，经核心环境再次核对完整 profile、参数、组成、电荷与所有文件摘要后原子发布，不覆盖旧模型。
重开、刷新或创建表格不启动构建。准备时冻结行参数，开始后使用已安装的软件；软件版本不是二进制快照，实际使用版本保存在产物中。
参数方案按版本维护，未来改物理参数须新增版本，不覆写已发布 profile 1。

## PET 专用分阶段研究与 O₂ 示踪

新增协议 `stk.pet-study-recipe/1` 与本机协调步骤 `pet-study/1`，在项目格式 13 中串联现有建模、LAMMPS 运行、快照和保存分析。
它是 PET 专用流程；未改变原 PET profile 1 或旧 E1c 模板，也不替代通用工作流协议。
`stk.lammps.create_pet_study` 冻结配方与 Runtime 意图，显式 `start_pet_study` 才开始计算；
查看、重开和恢复记录不会自行提交。使用方法见[全流程示例](../examples/pet_study/README.md)，实际运行结果与 CI 另记[验收记录](runtime-validation.md)。

初始最小化与高温预热后，NPT 压力逐步升至设定压密压力，再释放至设定压力；默认末端压力为 1 atm。
冷却温度按冻结序列逐段下降：下一段读取前段的几何、晶胞与原子速度，以前一设定温度到本段温度作 NPT 温度斜坡，
随后在本段温度采样。模量和扩散分别读取所选温度的保存状态，不互相使用已经拉伸或已经加入气体的状态。
交接采用文本 `state.data`，并不保存温控器/压控器的内部状态，也不声称等同于连续二进制 restart 的动力学。
各段保持输入 `input-state.data` 与输出 `state.data` 分离，并保存来源快照、实际文件摘要和含原子/分子 ID、类型、电荷及非折回坐标的轨迹。

LAMMPS 的这些势函数在 `write_data` 中以默认 `%g` 写浮点系数，即六位有效数字；
OPLS 的内部半系数写出前会乘回 2，harmonic 角的内部弧度会换回度，CVFF 的符号和周期数仍按整数写出。
这会使状态文件中的某些 OPLS 系数与初始精确值略有差异。
下游每段在 `read_data` 后立即读取由**首次冻结 `pet.data`**生成的 `forcefield-exact.in`，
用 17 位有效数字恢复原有 pair/bond/angle/dihedral/improper 系数，不从前段舍入表反复推导参数；O₂ 新类型系数另行设置。
配套 JSON 保存原始数据摘要、逐类型精确数值和命令摘要；输入/输出的校验只识别已确认的文本表示舍入并逐项记录，任意改参仍拒绝。
初始松弛使用原始精确数据，不因增加下游恢复文件改变已冻结的松弛输入。
这些规则针对当前明确支持的势函数；源码依据是固定的
[LAMMPS 22Jul2025 OPLS 写出函数](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/MOLECULE/dihedral_opls.cpp)，
以及下列[各势函数写出实现](#可复核的公开来源与许可)。

默认 `pet_chain_com` 为纯 PET 整链质心的单原点 MSD；`{"diffusion":{"group":"o2_com"}}` 选择独立版本
`stk.oxygen.iff2021-12-6/1` 的中性 O₂ 示踪模型。它采用 Wang、Hou、Heinz 的
[2021 年 IFF 气体模型](https://doi.org/10.1021/acs.jctc.0c01132)，
[作者公开稿](https://par.nsf.gov/servlets/purl/10297174)表 2 中的 12–6 参数，完整保留该双原子模型的键与 LJ 项：

| 参数 | 文献定义 | STK / LAMMPS real 定义 |
|---|---|---|
| O–O 平衡距离 | 1.2074 Å | 1.2074 Å |
| 谐振键系数 | `U = ½ Kr Δr²`，Kr = 1640.4 kcal mol⁻¹ Å⁻² | `U = K Δr²`，K = 820.2 kcal mol⁻¹ Å⁻² |
| LJ 距离 | 势能最小位置 rmin = 3.297 Å | 零交点 σ = rmin / 2¹ᐟ⁶ = 2.9372930737086986 Å |
| LJ 势阱深度 | ε = 0.1047 kcal mol⁻¹ | 原值 |
| 每个氧原子的质量、电荷 | 作者补充 FRC / O₂ 结构文件 | 15.9994 g mol⁻¹、0 e |

作者示例输入将 σ 舍入为 2.937 Å；STK 明确使用表中 rmin 的解析转换，不声称逐位复现作者轨迹。
交叉 σ、ε 沿现有 PET OPLS 的几何混合规则生成；O₂ 的 1–2 非键合排除，不增加角、二面角、虚拟电荷点、极化或化学反应。
原论文关于气体/水与力场兼容性的结果不能转述为本 PET/O₂ 混合体系的扩散准确性证明。

O₂ 只在扩散分支中随机插入，默认两个分子；重叠距离、尝试预算、分子数和随机种子随配方冻结。
建模、初速度和分子插入的种子分别受其随机数算法范围限制，插入种子还须与冻结的 MPI 进程数相容。
未满足非重叠条件或未生成全部指定分子时停止，不能用缺少的示踪分子继续拟合。
新增类型、质量、电荷、分子 ID、气体键与总原子数须核对；PET 原有身份、拓扑和系数保持不变。
随机非重叠插入不是 GCMC 或平衡吸附方法，其实际构型、数量与执行选项需保留，不能把气体数解释为预测溶解度。

气体插入后保留已有 PET 坐标和速度，只为新 O₂ 创建速度，再清除全体系线动量；这个步骤不对全体系作 FIRE 最小化。
固定 [LAMMPS 22Jul2025 的 FIRE 初始化](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/min_fire.cpp)
会清零全部原子速度，并把速度用于最小化的虚拟动力学，不能当作保留高温保存态的准备步骤。
这与初始 PET 建模后先最小化、再为全体系明确创建热速度的顺序不同。
插入分支依赖明确的非重叠约束与后续有限 NPT 准备，仍须检查温度、压力、密度和体积随时间的稳定性；
保留热态或完成准备预算本身不证明含气体系已平衡。

扩散先作有限 NPT 准备，生产段采用固定体积 NVT；质心按原子质量与非折回坐标计算，并只选择指定 PET 或 O₂ 分子组。
不会去掉气体组自身的整体质心位移；插入后只清除全体系初始线动量。当前为单时间原点、有限浓度与有限时间采样，
还需检验整体漂移、独立构型、多原点、长时扩散区和稀释极限。
`pilot` 与 `research` 是不同的起始预算，不是平衡或收敛判据；完整软件结果始终保留 `material_validation = false`，
被拒绝的 Tg、模量或扩散拟合保存失败诊断，不补造物性值。

## 科学适用范围与仍需完成的验证

参数与拓扑核对、独立势能公式对照、真实 LAMMPS 运行以及项目生成/归档路径是分别验收的环节。
即使这些检查全部通过，也只证明对应实现环节，不能证明密度、Tg、模量或扩散系数已经接近真实 PET，
不能把初始 Packmol 填充密度当作平衡密度，也不能把数 ps 的运行当作聚合物平衡。
具体已执行内容及结果须查验收记录，未运行的验证不能写成通过。

原论文使用 DL_POLY、Berendsen 控温控压和截断静电处理；STK 的 LAMMPS 模板采用不同的动力学和长程静电实现，
加上缺项补全、平面 improper 和末端氧的舍入修正，已经构成方法适配。
文章所报告的数值只能作为后续比较对象，不能作为当前模型的已验证结果。

需要在真实、足够长的轨迹上检查以下问题，并保存输入、力场摘要、平衡判据、随机种子与拟合窗口：

- **密度与 Tg**：检查链长、体系大小、多份独立初始结构、热历史、冷却速度和每个温度的平衡时间；
  Tg 的密度曲线需覆盖玻璃态与高温态，评估拟合窗口和不确定度。小四聚体是功能验收体系，不代表高分子量 PET。
- **模量**：先取得受力与结构稳定的玻璃态构型，检查温度、方向、应变窗口、应变率与独立构型之间的变化；
  MD 高应变率结果不能直接当作实验加载速率下的材料模量。
- **扩散与阻隔**：首个 O₂ 示踪参数与专项分子质心采样已实现，但 PET/O₂ 交叉作用和材料扩散尚未验证；CO₂、水和乙醇参数尚未提供。
  仍须取得已平衡含气体系，检查分子质心、多时间原点、整体漂移、浓度效应与真正扩散区。
  旧 E1c 单原点所选原子组模板保持原状；新专项质心 MSD 也不等于收敛气体扩散验收。
  扩散系数不足以单独给出渗透率，尚需吸附/溶解信息。
- **不同材料形态与化学**：本模型不描述晶体/半结晶形态、取向、交联、改性共聚物、去质子化端基或水解反应；
  这些体系需要重新选择端基、参数或模型。固定电荷经典模型也不提供电子性质或化学反应路径。

纯 PET 不能代替 PET 基弹性体，干燥 PET/O₂ 也不能代替酒液接触后的材料。
多相或多个热转变不由两段直线 Tg 拟合自动识别；小应变斜率不能代替回弹、黏弹性或长期永久变形。
组成、结晶、热史、接触状态与实验时间尺度必须另行记录、标定和验证。

## 可复核的公开来源与许可

- 主文献：[DOI 10.3390/polym14061161](https://doi.org/10.3390/polym14061161)，
  [PMC 公开全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC8951138/)。
  [NIH 官方补充文件 ZIP](https://pmc-oa-opendata.s3.amazonaws.com/PMC8951138.1/polymers-14-01161-s001.zip)
  大小 221623 字节，SHA-256 `aeb126cea1ecf997545619389bdf94e17e57470384648ad14d53564eabd03457`；
  其中 `polymers-1582649-supplementary.pdf` 的 SHA-256 为
  `65f9363f878c9c35bdbb98d51c8b0921729a072dfa3c381d1175e3aff85134ea`。
  文献为 CC BY 4.0，数字表转录须保留作者、出处与修改说明。
- 后续 PET/PEV 共混研究复用该参数：[DOI 10.3390/polym14142858](https://doi.org/10.3390/polym14142858)。
  这是已有使用证据，不替代本实现的独立物性验证。
- 键合补全与平面 improper：[固定 GROMACS v2025.3 文件](https://raw.githubusercontent.com/gromacs/gromacs/v2025.3/share/top/oplsaa.ff/ffbonded.itp)，
  SHA-256 `145e6924f52fae7e93108fa3d674f31a53aea10c80b13dd89abf0b011adfd4fa`；
  其[仓库许可](https://raw.githubusercontent.com/gromacs/gromacs/v2025.3/COPYING)为 LGPL v2.1。
  参数来源固定到版本与文件摘要，运行时不从外网补参数；这些公开数据的使用不表示原作者或 NIH 为 STK 模型背书。
- O₂ 参数：Wang、Hou、Heinz，JCTC 2021, 17, 5198–5213，[DOI 10.1021/acs.jctc.0c01132](https://doi.org/10.1021/acs.jctc.0c01132)。
  [作者补充代码与结构 ZIP](https://acs.figshare.com/articles/journal_contribution/14977419)的 SHA-256 为
  `542c793b9bdadfab894eb45c913435bce1f47ad30fe031987d6da0f821ed52fc`，公开元数据标注 CC BY-NC 4.0。
  质量与零电荷分别核对 `Supporting_Files/FORCE_FIELD/cvff_interface_Gas.frc` 的 `o2g` 类型及 `Supporting_Files/MODEL/O2.car`、`O2.mdf`。
  仓库记录必需的数值事实、来源与换算，没有分发整份作者力场、结构文件或补充 ZIP；许可字段记录来源许可，不宣称其适用于所有下游用途。
- 气体传输的研究参考：[Lightfoot 等，PET/PEF 氧扩散对照研究](https://doi.org/10.1021/acs.macromol.1c01316)。
  其[作者研究记录](https://researchportal.bath.ac.uk/en/publications/a-comparative-study-of-oxygen-diffusion-in-pet-and-pef-using-mole/)
  与[公开补充材料](https://acs.figshare.com/articles/journal_contribution/17105809)保留长时间 MSD 和多条轨迹分析。
  该研究使用的聚合物/氧模型与 STK 不同，只用于制定长时采样、扩散区与独立轨迹的后续验证方法，不作为本实现已经通过的数值基准。
- 文本系数表示：固定 LAMMPS `stable_22Jul2025` 的
  [LJ/Coulomb long](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/KSPACE/pair_lj_cut_coul_long.cpp)、
  [harmonic bond](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/MOLECULE/bond_harmonic.cpp)、
  [harmonic angle](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/MOLECULE/angle_harmonic.cpp)、
  [OPLS dihedral](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/MOLECULE/dihedral_opls.cpp) 与
  [CVFF improper](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/MOLECULE/improper_cvff.cpp) 的 `write_data` 实现。
  这是文件表示精度的来源，不是更改物理参数或放宽任意系数差异的依据。
