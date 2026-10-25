# 技能目录与项目版本（实验性）

更新：2026-10-25。只读内置目录及原生浏览页已交付；项目版本固定、升级、恢复和创建分析草稿已通过本机验收，
从保存分析创建用户技能、追加版本及保留提交参数／输出选择正在验收；
提交与实际结果见[当前交接](../handoff.md)。`stk.skill/1` 与 `stk.project-skill/1` 仍是实验格式，未冻结。
产品方向见[项目工作台设计](design/project-workbench.md)，存储边界见[项目数据模型](design/project-model.md)。

## 三类内容不要混用

| 内容 | 位置与入口 | 作用 |
|---|---|---|
| SKILL.md 说明包 | `suan/skills/<名称>/SKILL.md`；`suan skills list`、`suan skills export` | 给模型的方法说明和例子，例如 `stk-visualize`、`stk-monitor` |
| 节点目录 | `stk.catalog/1`；`suan graph catalog`、桥 `graph.catalog` | 可执行的节点类型、端口与参数 |
| 版本化技能 | `suan/skills/definitions/<id>.json`；`suan skills catalog/show`、桥 `skills.list/get`、`stk.skills` | 一个可引用单元：稳定 ID、版本、执行入口、输入/参数/输出、依赖、例子，并可指向说明包 |

技能不是节点目录的别名，也不是把全部图预设改名。当前收录六个已经能离线验证的能力：

| 技能 | 执行入口 | 选择原因 |
|---|---|---|
| `stk.visualize.scalar_volume@2` | 预设 `scalar-volume` | 绑定普通场文件，可在无服务器时检查带符号标量与单位标签 |
| `stk.muferro.domains@1` | 预设 `muferro-domains` | 真实 MuFerro 结果的主要分析：畴变体、占比与能量曲线 |
| `stk.muferro.energy_trace@1` | 预设 `energy-plot` | 只读解析能量表，示范不需绘图库的输出与需要绘图库的输出 |
| `stk.lammps.tg@1` | 预设 `lammps-tg` | 密度–温度两段拟合；交点与分段规则明确 |
| `stk.lammps.modulus@1` | 预设 `lammps-modulus` | 工程应变窗口内拉伸应力斜率，保留自由截距 |
| `stk.lammps.diffusion@1` | 预设 `lammps-diffusion` | 显式时间窗口中的 MSD 爱因斯坦关系，不自动选择扩散段 |

后三项的单位、脚本与物理限制见[LAMMPS 分析](lammps-analysis.md)。数值输出只需 NumPy，绘图另需 matplotlib；查询目录不运行 LAMMPS。

## 契约要点

- **身份**：`ref = id@version`，另有 `content_sha256`：定义 JSON 与其图模板的规范 JSON 的 SHA-256。
  同一 `ref` 内容不同即为不同定义。目录总是重新读取定义；不缓存旧结果。
- **执行入口**：内置目录支持 `graph.preset`；项目用户技能支持完整保存的 `graph.document`。均通过保存分析和已有图求值服务使用，本身不执行、不准备运行、不调用模型。
  输入（绑定）、参数和输出直接取自图模板，不另存一份可能偏离的说明。
- **依赖与可用性**：节点类型按已安装节点目录检查；Python 模块用 `importlib.util.find_spec` 查找，**不导入**。
  模块可限定只影响部分输出，例如缺少 matplotlib 时能量曲线不可用，但表格和三维仍可用，状态为 `limited`。
  离屏渲染等运行能力只声明、标记 `checked: false`，不在查询时探测；需要时运行 `suan graph doctor`。
  `tests/test_skill_catalog.py` 在子进程中屏蔽模块实际求值，核对每个声明的影响范围。
- **坏定义可解释**：无法读取、JSON 错误、字段不合格、文件名与 ID 不一致、重复、未知入口类型、未知预设/说明包、
  例子或依赖引用不存在的参数/输出时，该文件列入 `problems`，其他技能照常显示。
- **未知 ID 或版本**：`skills.get` 返回 `not_found`，`data.known_versions` 给出已知版本；
  只有坏定义时 `data.problems` 说明原因。

## 版本规则

已发布的 `id@version` 内容不应改变。修改定义或其包装的图预设时：

1. 默认新增版本（新的 `version`），旧运行记录仍以冻结的完整图为准，不受目录更新影响；
2. 确属更正时，运行 `python -m suan.skills.catalog --lock --output tests/data/skill-catalog.lock.json`
   刷新锁文件，并在[开发交接记录](development-log.md)写明原因。CI 在锁文件不一致时失败。

内置目录当前每个 ID 只发布一个版本。项目版本保存完整定义与图模板及对应摘要，采用独立的稳定 UUID。
读取、恢复已保存版本和创建分析草稿都不重新查询安装目录；本机目录更新不会改变项目的活动版本。
明确升级时追加比全部历史版本都新的版本；恢复仅选择已有版本，不删除历史。

## 项目版本

在技能库中查看确切版本后，点击“将此版本保存到项目”，进入“项目技能版本”。每次写入都核对项目修订；保存与升级还核对刚查看的内容摘要。
项目页显示活动版本、摘要和已保存版本。要升级，先在技能库查看同一技能的新版本，再回项目页明确升级；
“恢复此版本”和“创建保存分析”各是独立操作。草稿带来源技能 UUID、版本与摘要，后续编辑不会改写已保存技能或历史运行。
“打开分析编辑器”进入分析页面，仍须从列表选择刚创建的分析；创建不绑定输入或启动求值。

这些操作复用普通项目编辑事务和撤销／重做。工作空间包中的数据库备份保留完整版本内容，恢复编辑器仅还原同一项目的选择。
**保存的是方法定义，不是可执行环境**：不打包节点实现、Python 依赖、说明包正文或科学输入；实际运行仍需对应依赖、输入绑定和明确启动。
失去写入回执时先按原对象 UUID 检查当前状态，不自动重放。损坏或不支持的记录保留错误说明，不能创建分析或恢复。

每个项目最多 128 条技能记录、内容总量 4 MiB；每条最多 16 个版本、384 KiB。
这些是有界方法快照，不用于保存大型结果。

## 从保存分析创建用户技能

先在分析编辑器保存图、提交参数和所选输出，再到技能页的“项目技能版本”，展开“从保存分析创建技能”。
选择分析后，“保存为新的项目技能”创建版本 1；选中已有用户技能时，“向所选技能追加版本”保存比全部历史版本更高的新版本。
标题沿用分析名称（最多 120 字符），说明沿用图的 description，缺省时使用分析名称；修改这些内容后先保存分析。
此入口不替换内置目录技能，也不把未保存草稿偷偷带入版本；其他页面有草稿时写入入口保持禁用。

用户技能使用 `graph.document`，冻结完整图、参数覆盖值及输出选择（显式空列表仍为空），并记录源项目、分析 UUID、修订与文档摘要。
绑定名按保存的参数值解析；这些输入名没有绑定实际文件。未知节点可作为结构合法的分析定义保存，发布不证明节点可用或图可执行；
运行时仍须按共享服务验证节点、参数、依赖和输入。读取或发布不加载节点插件，也不执行图。
“保存的方法接口”可查看输入、参数名和所选输出；修改参数化绑定名时，运行所需的输入名也可能改变。

创建分析时完整恢复该版本的图、提交参数和输出，并附上技能版本来源；之后编辑分析不会修改技能。
恢复旧版本不删除新版本，随后追加仍从历史最大版本继续。普通项目撤销、数据库备份和工作空间迁移保留所有版本。
当前是项目内用户技能；跨项目独立发布、用户／第三方全局目录和项目工作流整体封装仍待接入。

## 使用

```bash
suan skills catalog                      # 列表与可用性
suan skills catalog --query muferro --json
suan skills show stk.muferro.domains     # 最新版本
suan skills show stk.muferro.domains@1   # 精确版本
```

```python
page = stk.skills.list(limit=20, query="volume")   # 有界分页，最多 200 行
skill = stk.skills.get("stk.visualize.scalar_volume", version=2)
print(skill["ref"], skill["content_sha256"], skill["availability"]["status"])
```

桌面桥方法和字段见[桥协议 §16](specs/stk-desktop-bridge-v1.md#16-versioned-skill-catalog-additive-extension-experimental)。
旧版桥没有这两个方法时，客户端应显示“不提供技能目录”，不能猜测。

原生桌面从 **文件 → 技能** 或工作台“技能库”打开同一目录，用法见[桌面指南](desktop.md#技能目录)。

脚本通过已打开项目的 `p.skills` 访问相同操作；列表和详情是纯读，四种写入均要求 `expected_revision`：

```python
from uuid import uuid4

skill = stk.skills.get("stk.muferro.energy_trace", version=1)
project_skill_id = str(uuid4())
# p 为已打开的项目；revision 为刚检查过的该项目修订。
receipt = p.skills.pin(skill["id"], skill["version"], skill["content_sha256"],
                       project_skill_id=project_skill_id, expected_revision=revision)
saved = p.skills.get(project_skill_id)["skill"]
receipt = p.skills.create_analysis(project_skill_id, saved["active"]["content_sha256"],
                                  analysis_id=str(uuid4()), name="能量分析", expected_revision=receipt["revision"])
```

这里只保存分析，不准备输入或执行图。`p.skills.upgrade(id, version, content_sha256, expected_revision=...)`
与 `p.skills.restore(id, content_sha256, expected_revision=...)` 分别追加新版本和切换已保存版本。

```python
identity = str(uuid4())
receipt = p.skills.publish_analysis(analysis_id, project_skill_id=identity, create=True,
    name="我的分析方法", description="输入数据及适用范围的说明", expected_revision=revision)
# 后续先保存修改后的分析，再明确向同一用户技能追加版本：
receipt = p.skills.publish_analysis(analysis_id, project_skill_id=identity, create=False,
    name="我的分析方法", description="新版本说明", expected_revision=current_revision)
```

## 尚未实现

- 从技能直接准备或运行、对话附件、工作流封装为技能；
- 用户或第三方全局技能目录、更多入口类型（批次模板、Python 操作等）；项目内分析方法版本见上。
