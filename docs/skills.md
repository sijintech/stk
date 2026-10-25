# 技能目录与项目版本（实验性）

更新：2026-10-25。只读内置目录及原生浏览页已交付；项目版本固定、升级、恢复和创建分析草稿已通过本机验收，
保存分析及完整工作流发布为用户技能、追加版本与恢复已完成本机验收，最新批次跨平台 CI 待确认；
本机全局用户库与跨项目固定已完成本机验收，源码 `6fa8994` 已本地提交，尚未推送与跨平台验收。
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

- **身份**：`ref = id@version`，另有 `content_sha256`：定义 JSON 与完整方法模板的规范 JSON 的 SHA-256。
  同一 `ref` 不得保存不同内容；显式新版本不会覆盖旧版。
- **执行入口**：目录支持内置 `graph.preset`、保存分析 `graph.document` 和完整工作流 `workflow.document`。
  用户方法先固定到项目，再明确创建可编辑副本；目录读取不执行、不准备运行、不调用模型。接口摘要来自冻结定义。
- **依赖与可用性**：内置技能按静态节点元数据检查，不加载第三方节点入口；Python 模块用 `importlib.util.find_spec` 查找，**不导入**。
  模块可限定只影响部分输出，例如缺少 matplotlib 时能量曲线不可用，但表格和三维仍可用，状态为 `limited`。
  离屏渲染等运行能力只声明、标记 `checked: false`，不在查询时探测；需要时运行 `suan graph doctor`。
  `tests/test_skill_catalog.py` 在子进程中屏蔽模块实际求值，核对每个声明的影响范围。
  用户方法标记为 `unchecked`：结构完整不表示当前机器具备运行环境，准备运行时再核实。
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

每个项目最多 128 条技能记录、内容总量 8 MiB；每条最多 16 个版本，完整历史合计最多 8 MiB。
最终项目快照仍限 12 MiB，单次编辑最多 1000 条命令；组合后的方法或目标项目超限时整批拒绝。
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
项目内版本可进一步明确保存到本机用户库，供其他项目固定使用；本批实现与验收状态见下。

## 从保存工作流创建用户技能

在技能页选择已保存的工作流，明确创建新技能或向已有工作流技能追加版本。
`workflow.document` 保存根流程、所有递归子流程及引用的分析定义，每个源对象按 UUID 保存一次，
同时记录完整文档摘要和源项目修订。之后修改或删除源定义不会改写这个技能版本。
它保留可编辑的流程层级、接口和参数，不把执行展开结果当作可编辑方法。

“创建保存工作流”复制整套定义并分配新 UUID，重复调用仍共享同一份子流程定义。
表格、字段和文件快照作为外部数据依赖列出；创建前明确确认映射。同项目可沿用原数据，
跨项目需指定目标，不能按名称猜配。字段核对目标表、类型和单位，文件快照核对所需文件名。
参数默认值和 `$literal` 中看起来像字段引用的 JSON 保持字面量，不参与替换。

整套创建是一次修订和一次撤销，失败不留下部分对象。创建后进入工作流编辑器继续检查和编辑，
运行仍须明确准备与启动。读取、恢复和创建不加载计算引擎，也不保证目标机器具备执行环境。
本批桌面与端到端验收结果见[运行验收](runtime-validation.md)。

## 本机用户技能库

在项目技能详情中明确“保存到本机技能库”，将已审阅的活动版本保存到当前桌面桥状态目录的
`skills/catalog.sqlite`。库不依赖源项目继续存在；其他项目可在技能目录选择确切版本，先保存到项目，
再创建分析或工作流。项目技能记录 UUID 与方法 ID 各自独立，目标项目追加版本仍保留原方法身份。

相同 `id@version` 和摘要可重复确认；同版本不同内容会拒绝，需明确选择“发布新版本”。
新版本分配同时考虑库内和来源项目保留的历史，不覆盖旧版，也不改来源项目的活动版本或撤销历史。
全局发布使用独立 `publication_id`；回执丢失时只查询这个身份，关闭源项目后仍可查询，不能自动重放。
桌面在当前应用会话内保留待确认身份，跨页面关闭和桥重启仍可查询；退出应用后尚无自动恢复入口。

当前库限 1024 个版本、快照总量 64 MiB、单版 8 MiB、4096 条发布回执。
列表读取最多 1024 条、每条至多 16 KiB 的摘要后分页，不展开完整方法；选定详情与固定版本才核验完整快照。
源文件字节、执行环境及本机库本身不随项目自动迁移，项目已经固定的版本仍随数据库和工作空间保存。
这是本机方法复用；第三方分发、远端共享和库管理界面仍属后续范围。独立 CLI 默认仍查看内置目录。

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

脚本通过已打开项目的 `p.skills` 访问相同操作；列表和详情是纯读，项目写入及本机发布均要求 `expected_revision`：

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

```python
# 先读取当前项目版本，保存其确切摘要；发布不增加项目修订。
saved = p.skills.get(project_skill_id)
publication_id = str(uuid4())
publication = p.skills.publish_global(project_skill_id, saved["skill"]["active"]["content_sha256"],
    publication_id=publication_id, mode="exact", expected_revision=saved["revision"])
# 丢失回执时保留 publication_id，通过此只读入口核对。
publication = stk.skills.publication(publication_id)
# target 为另一个已打开项目，target_revision 为已检查的目标修订。
method = publication["skill"]
receipt = target.skills.pin(method["id"], method["version"], method["content_sha256"],
    project_skill_id=str(uuid4()), expected_revision=target_revision)
```

## 尚未实现

- 从技能直接准备或运行、对话附件；
- 第三方分发、远端共享、库管理界面和更多入口类型（批次模板、Python 操作等）。
