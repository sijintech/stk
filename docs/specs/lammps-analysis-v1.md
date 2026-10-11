# LAMMPS 分析节点 v1（E1c，增量扩展）

2026-10-11。在 `stk.graph/1`、`stk.catalog/1` 中新增四个 `@1` 节点；既有节点声明和项目格式不变。
声明来源仍为 `catalog/m1_nodes.py`，生成 JSON 与 [图协议目录](stk-graph-v1.md)同步。
实现与使用见 [LAMMPS 分析指南](../lammps-analysis.md)。

| 节点 | 输入 | 输出 | 行为 |
|---|---|---|---|
| `stk.source.lammps_log@1` | 文件绑定、相对 `path`、`block`（默认 -1） | `out: table` | 读取一个正常结束的 real 单位热力学段，不拼接 reset 后的时间或平衡/生产段 |
| `stk.analysis.lammps_tg@1` | `in: table` | `summary: table`、`fit: table`、`diagnostics: value<json>` | 两段密度–温度直线交点 |
| `stk.analysis.lammps_modulus@1` | 同上 | 同上 | 指定工程应变窗口内的应力斜率 |
| `stk.analysis.lammps_diffusion@1` | 同上 | 同上 | 指定时间窗口内的 MSD 斜率除以 `2d` |

源节点要求正常结束、所有热力学段完整且数值有限，没有 ERROR；只支持已有的 one/custom 单行布局。
日志必须明确含 `units real`，出现其他单位声明则拒绝，不能把 clear 后的末次单位套到前段。选择段按 Python 索引（负数从末尾算）；不存在的段报 `invalid_result`。
日志读取上限 256 MiB。标准列映射：`Step → 1`，`Temp → K`，`Density → g/cm3`，`Press → atm`，
`Volume → Ao3`，`Time → fs`，`PotEng/KinEng/TotEng → kcal/mol`；自定义列保持 `unspecified`。
源文件路径与所读原始字节的 SHA-256 保留在表格 provenance 与 attrs.source。重复列名拒绝。

三个拟合节点要求带明确单位的数值标量列，不能从字符串、`unspecified` 或其他单位猜测转换。
所有输入行须有限；不静默丢弃 NaN/Inf 或缺失点。一般输入上限 100000 行，Tg 上限 500 个温度。
CSV/列文件经通用表格源读取，重复表头或规范化后重名的列在拟合前拒绝；不按最后一列覆盖原观测。
OLS 为等权、有自由截距的最小二乘，至少三点；保留拟合范围、样本数、残差平方和、R²、斜率标准误差。
零纵向方差的 R² 为 null，不能产生 NaN/Inf。窗口端点包含在拟合中。

- **Tg**：列默认 `Temperature: K`、`Density: g/cm3`，排序后拟合，不改输入。
  温度必须正、各不相同，密度正；重复温度需要调用者先显式合并与保存来源。
  `min_points` 默认 3，每侧至少该数量；`split_temperature` 默认 null，自动遍历满足数量的相邻温度间隙，选两段 RSS 合计最小的一项。
  显式边界将 `T ≤ split_temperature` 分到低温段。两条线均须递减，高温段更陡，斜率差须大于 `max(1e-14, |低温斜率|*1e-6)`。
  交点须位于所选间隙内，否则拒绝，不从不合规数据中勉强产生 Tg。无 Tg 置信区间。
- **模量**：列默认 `Strain: 1`、`Stress: GPa`，应变须严格递增；默认窗口 `[0, 0.02]`，可显式改变。
  横坐标是工程应变，应力拉伸为正；正斜率即模量 GPa，预载/残余应力由自由截距表示，负或零模量拒绝。
- **扩散**：列默认 `Time: fs`、`MSD: Ao2`（UCUM Å²），时间严格递增且非负，MSD 非负；
  `time_min/time_max` 默认 null，运行时必须填写非负且递增的数值窗口，不能自动把弹道/暂态段当扩散段。
  `dimensions` 默认 3，只允许 1/2/3，调用者须保证所选 MSD 分量与维数一致。
  `D = slope/(2d)*0.1`，输出 cm²/s；负或零斜率拒绝。

`summary` 为一行数量/单位明确的结果，`fit` 包含所选数据与 `Fitted` 列；Tg 使用全部输入，另外两项只包含窗口内的行。
结果 attrs 与 `diagnostics` 保存方法与限制；输入有 provenance 时，诊断的 `source` 也携带该来源，
即使通用表格输出被转成 blob，独立诊断输出仍保留来源。三个节点发 `md_fit_limits` 警告：
MD 数据相关，OLS 标准误差不能作为独立重复或材料性质不确定度；须检查平衡、拟合窗口、温度历史、应变率、组选择与长时扩散条件。
拟合失败报 `invalid_result`，读取或求值不会运行 LAMMPS、修改项目或请求模型。
