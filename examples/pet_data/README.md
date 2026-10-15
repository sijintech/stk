# PET 身份与证据的合成导入演练

这是[业务字典草案](../../docs/design/pet-data-dictionary.md)的节点 1 软件样例。
九张普通 CSV 表、32 条业务记录、61 个稳定标量引用和 20 项冻结文件演练
材料 → 配方 → 批次 → 样品/分样 → 干燥/接触/脱附状态 → 观测 → 处理 → 复核 → 决定。
本例新建项目使用当前存储格式（现为 14）；核对已有格式 13 项目不会自动升级。
`stk.pet-data-example/0.1` 只是本例清单版本，不是已发布的导入协议。

全部数据都是合成。每条业务记录和原始曲线均有 `source_kind=synthetic`、`synthetic=true`。
观测的 `represented_source_kind` 区分所演练的文献、计算、实测和推断角色，不能当成取得真实证据。
曲线的点序号和无量纲人工响应只用于软件核对，不代表 PET 物性、接触实验或模型训练标签。
计划/实际组成、接触介质与条件尚未指定；不提供酒液配方、科学阈值或合格材料。

## 创建与核对

使用 STK 的 Python ≥3.11 环境，从仓库根目录执行。命令必须给出**尚不存在**的目录；
已有目录、文件、符号链接和不完整的旧演练均拒绝覆盖：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.pet_data.offline --out /absolute/new/pet-data-demo
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.pet_data.offline --verify /absolute/new/pet-data-demo
```

可将 `python` 替换为 STK 虚拟环境解释器的绝对路径。脚本只用 Python 标准库与现有 STK ProjectStore，
无需分子建模模块、求解器、模型服务或互联网。不会启动运行、训练或模型请求，也不切换桌面的当前项目。
成功后在桌面手动打开该目录，进入普通数据表查看 `PET demo ...` 表；这不是新的材料业务界面。

成功输出应为九张业务表、32 条记录、61 个引用、20 项冻结文件，`working_copy_changes=0`、
`verified_reopen=true` 和 `material_validated=false`。文件索引是第十张内置普通表，不计入九张业务表。
`demo.json` 记录项目身份、业务标识到 UUID 的映射、字段身份、文件摘要和快照 ID。
核对重新读取记录与引用、验证冻结对象的真实字节，并报告工作副本与原始夹具的差异，不自动重捕获。

中断会留下新建的部分项目；保留它以检查失败位置，选择另一个新目录重跑。多个表分别是普通原子 CSV 编辑，
整个演练不是单次事务。单表导入已有 1000 条编辑命令/8 MiB 边界，本例总输入额外限定在 1 MiB。

## 文件与需要观察的反例

`fixtures/fixture.json` 声明表名、显式字段类型、最小外键映射及十项原始文件。
执行时全部复制到新项目的 `fixture/`，再通过现有文件索引和内容快照保存。
表中的外键与原始资源路径使用记录/字段 UUID 引用；重命名表头不改变关系。
整体移动项目目录后，引用与冻结对象仍有效。仅导出 CSV 会失去引用定义和冻结内容，不能当作完整备份。

- `syn-batch-A/B` 是两批模拟完成身份；父样品和分样保留同一批次关系。三类状态逐条记录，不覆盖为一个最新状态。
- `syn-batch-failed` 是额外失败制备记录，没有虚构样品或数值；其观测、处理和复核保留失败原因。
- `curve-B-desorbed.csv` 的末点为空；原始观测与处理的数值保持 `None`，不填零，也不替换成上一点。
- 文献/计算/推断说明明确是合成占位，没有真实 DOI、文章、运行或专家验证；复核人也是模拟身份。
- 每条观测关联材料；推断另外引用依据观测。文献说明不伪造样品/测量状态，也不会成为无法回查材料的孤立记录。
- `allowed_uses` 只演练 `software_demo` 或空列表，决定明确要求实际目标和证据；这些字段目前是可编辑普通数据，未实施授权或准入检查。

两批、分样、三种状态不代表独立统计充分性。该字典不实现业务去重、外键/状态自动校验、多证据报告、
材料权限或训练契约；企业实际数据/聊天接入须先完成厂内边界验收。

## 本机验收

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m unittest examples.pet_data.acceptance -v
```

验收覆盖离线执行、重开、展示名称改名、目录移动、缺测/失败保留、拒绝覆盖、工作副本改变与冻结对象损坏。
它只验证本例及已有项目 API，不代表材料性质或新业务协议已经验收。
实际验收调用 ProjectStore；桌面脚本门面、UI 导入/导出及人工查看尚未在本例验证。
