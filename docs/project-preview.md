# 预览项目修改

`ProjectStore.preview`、桌面 Python 的 `stk.project.preview` 和桥方法 `project.preview` 使用同一编辑引擎，
在 SQLite 内存副本上计算一批修改后的表格、引用和公式。它为批量修改和后续 AI 草案提供可检查的结果；
当前还没有 AI 草案页面或持久化的审批记录。

## 先预览，再明确提交

```python
p = stk.project
base = p.snapshot()
proposal = p.preview(
    [{"op": "create_table", "name": "拟议参数表"}],
    expected_revision=base["project"]["revision"],
)
print(proposal["persisted"])          # False
print(proposal["snapshot"]["tables"]) # 假设提交后的表格
print(p.snapshot() == base)           # True：实际项目没有改变
```

返回值包括：

| 字段 | 含义 |
|---|---|
| `persisted` | 始终为 `false` |
| `base_revision` | 被读取的项目修订，也是后续提交的前置修订 |
| `proposed_revision` | 假设提交成功后的修订，等于基础修订加一 |
| `commands` | 校验后的命令，含自动分配的稳定 UUID |
| `snapshot` | 假设提交后的项目快照；其中修订、公式缓存和撤销状态也是假设结果 |

检查内容后，可以在**另一次明确操作**中提交返回的命令：

```python
committed = p.apply(proposal["commands"], expected_revision=proposal["base_revision"])
```

不要重新提交原来缺少 UUID 的命令列表，否则会分配另一组 ID。每次预览都是独立计算，
未提供的 UUID 可能不同；预览不会在后台保留或自动应用草案。

另一个窗口或脚本修改项目后，旧预览仍是旧修订上的结果；提交会得到 `conflict`。
应读取新状态、重新生成并检查预览，不能只把 `expected_revision` 改成最新值后继续提交。
实际提交复用普通原子编辑和撤销机制，不新增数据库格式。

## 错误和副作用边界

命令、类型、对象或修订错误直接拒绝，与 `apply` 一致。公式中的循环、缺失来源、单位不一致等
仍按现有规则显示在候选快照的 `records[].evaluations` 中；预览成功不表示每个公式都有有效结果。
可以在提交前检查这些错误并修改草案。原项目的值和错误状态不会被候选结果覆盖。

预览只接受普通表格编辑命令，不接受文件复制、输入快照捕获、升级、运行方案准备或任务提交。
实际项目修订、修改历史、撤销/重做、文件内容和 Runtime 任务均保持不变；桥不发布 `project.changed`。
文件索引属于普通表格，候选索引信息也只存在于返回的快照中，不代表磁盘文件已经变化。

源库以只读事务建立一致快照，复制完成后释放读事务，再在内存里计算。
这允许外部 CLI/其他连接在候选求值期间写入源库；同一桌面桥的项目操作仍遵守既有串行会话锁，
不能据此承诺同一桥内的编辑与预览并行。
源库逻辑大小限制为 **128 MiB**，每批 **1–1000 条命令**；限制针对数据库副本大小，
不代表计算时的总内存上限。大项目的增量预览、候选差异视图和持久草案留待后续扩展。
旧格式保持原格式：例如格式 1 可以预览字面量修改，但仍不能预览引用/公式，不会自动升级。

## CLI

```bash
suan project preview /absolute/project --commands edits.json --expected-revision 3
```

也可用 `--commands -` 从标准输入读取。输出是上述完整预览对象；需要保存并提交时，
把其中 `commands` 数组写入独立 JSON 文件，再明确调用 `suan project apply` 并使用 `base_revision`。
整个预览对象不能直接当作命令数组传给 `apply`。
