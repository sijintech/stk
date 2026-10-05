# 技能目录（首版，实验性）

更新：2026-10-05。状态：**只读内置目录已实现**；契约 `stk.skill/1` 仍是实验格式，未冻结。
产品方向见[项目工作台设计](design/project-workbench.md)，存储边界见[项目数据模型](design/project-model.md)。

## 三类内容不要混用

| 内容 | 位置与入口 | 作用 |
|---|---|---|
| SKILL.md 说明包 | `suan/skills/<名称>/SKILL.md`；`suan skills list`、`suan skills export` | 给模型的方法说明和例子，例如 `stk-visualize`、`stk-monitor` |
| 节点目录 | `stk.catalog/1`；`suan graph catalog`、桥 `graph.catalog` | 可执行的节点类型、端口与参数 |
| 版本化技能 | `suan/skills/definitions/<id>.json`；`suan skills catalog/show`、桥 `skills.list/get`、`stk.skills` | 一个可引用单元：稳定 ID、版本、执行入口、输入/参数/输出、依赖、例子，并可指向说明包 |

技能不是节点目录的别名，也不是把全部图预设改名。首版只收录三个已经能离线验证的能力：

| 技能 | 执行入口 | 选择原因 |
|---|---|---|
| `stk.visualize.scalar_volume@1` | 预设 `scalar-volume` | 绑定普通场文件，可在无服务器时检查带符号标量与单位标签 |
| `stk.muferro.domains@1` | 预设 `muferro-domains` | 真实 MuFerro 结果的主要分析：畴变体、占比与能量曲线 |
| `stk.muferro.energy_trace@1` | 预设 `energy-plot` | 只读解析能量表，示范不需绘图库的输出与需要绘图库的输出 |

## 契约要点

- **身份**：`ref = id@version`，另有 `content_sha256`：定义 JSON 与其图模板的规范 JSON 的 SHA-256。
  同一 `ref` 内容不同即为不同定义。目录总是重新读取定义；不缓存旧结果。
- **执行入口**：首版只支持 `graph.preset`，由已有 `graph.evaluate` 执行。目录本身不执行、不准备运行、不调用模型。
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

内置目录当前每个 ID 只发布一个版本。项目以后要采用固定版本时，应把解析后的技能内容随项目保存，
而不是依赖全局目录长期保留旧版本；这一持久引用、迁移和备份规则**尚未实现**。

## 使用

```bash
suan skills catalog                      # 列表与可用性
suan skills catalog --query muferro --json
suan skills show stk.muferro.domains     # 最新版本
suan skills show stk.muferro.domains@1   # 精确版本
```

```python
page = stk.skills.list(limit=20, query="volume")   # 有界分页，最多 200 行
skill = stk.skills.get("stk.visualize.scalar_volume", version=1)
print(skill["ref"], skill["content_sha256"], skill["availability"]["status"])
```

桌面桥方法和字段见[桥协议 §16](specs/stk-desktop-bridge-v1.md#16-versioned-skill-catalog-additive-extension-experimental)。
旧版桥没有这两个方法时，客户端应显示“不提供技能目录”，不能猜测。

## 尚未实现

- 原生“技能”浏览页（下一步，与本节契约共用桥方法）；
- 项目采用技能的持久引用、版本固定、迁移与备份；
- 从技能直接准备或运行、对话附件、工作流封装为技能；
- 用户或第三方技能目录、更多入口类型（批次模板、Python 操作等）。
