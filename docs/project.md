# 本地项目存储（P1 实验版）

当前交付是独立于界面的 SQLite 存储基础：创建/打开项目、表、字段、记录、字面量单元格、
稳定标识、修订冲突检查和事务修改历史。支持 Linux/macOS/Windows 的 Python 客户端，
不需要启动 Runtime 或安装科学/Qt 可选依赖。桌面打开项目、表格编辑器、引用/公式、撤销、
资源快照与执行计划尚未接入；不能把本节理解为整个 P1 已完成。

## 命令行

安装当前源码包后使用：

```sh
suan project create ./example-project --name "温度扫描"
suan project show ./example-project
suan project apply ./example-project --expected-revision 0 --commands edits.json
suan project history ./example-project
```

`edits.json` 是修改命令数组，例如：

```json
[
  {"op": "create_table", "name": "Cases"}
]
```

`apply` 返回新修订及包含已分配 UUID 的命令。`--commands -` 从标准输入读取 JSON；
`--expected-revision` 必填，取自最近一次 `show` 或成功 `apply`。陈旧修订会报告冲突，
应重新读取项目并核对修改；不会自动覆盖。失败批次的任何改动都不保存。

## Python 最小往返示例

下面是另一个项目；在任意工作目录运行，目录名不要与已创建的项目重复：

```python
from uuid import uuid4
from suan.project import ProjectStore

store = ProjectStore.create("scan-project", "温度扫描")
table, field, record = (str(uuid4()) for _ in range(3))
store.apply([
    {"op": "create_table", "id": table, "name": "Cases"},
    {"op": "add_field", "id": field, "table_id": table,
     "name": "Temperature", "type": "number", "unit": "K"},
    {"op": "add_record", "id": record, "table_id": table},
    {"op": "set_cell", "table_id": table, "record_id": record,
     "field_id": field, "value": 300},
], expected_revision=0)

reopened = ProjectStore("scan-project")
assert reopened.snapshot()["tables"][0]["records"][0]["values"][field] == 300
```

接口仅在操作期间持有数据库连接，不需要长期保存连接或调用 `close()`。

| 命令 | 必填参数（除 `op` 外） | 可选参数 |
|---|---|---|
| `create_table` | `name` | `id` |
| `add_field` | `table_id`、`name`、`type` | `id`、`unit` |
| `add_record` | `table_id` | `id` |
| `set_cell` | `table_id`、`record_id`、`field_id`、`value` | 无 |
| `rename_table` | `id`、`name` | 无 |
| `rename_field` | `id`、`name` | 无 |

未提供的新对象 ID 自动生成；需要在同一批次引用新对象时，像示例一样提前生成 UUID。
ID 必须是规范的小写带连字符 UUID 字符串。记录和字段必须属于同一张表；单元格以记录 ID 与字段 ID
定位，表格/字段改名不会影响已有值。当前快照按创建顺序显示，排序/过滤留给后续表格视图。

支持的类型为 `text`、有符号 64 位 `integer`、有限数值 `number`、`boolean`、`json`。
布尔值不作为数值接受，所有层级拒绝 NaN/Infinity。数值字段可登记单位字符串，
本阶段只保存单位元数据，尚不进行单位词表校验或换算。未赋值单元格在 `values` 中缺席，
显式 `null` 则保存为空值；此阶段没有必填约束。

## 实验格式与事务边界

目录中的 `project.sqlite3` 使用 SQLite application ID `STKP` 和 `user_version=1`。
当前物理表是 `project`、`tables`、`fields`、`records`、`cells`、`changes`；每次有效批次在一个
`BEGIN IMMEDIATE` 事务中校验修订、写值、提升一次修订并保存已分配 ID 的命令历史。
并发修改同一修订时仅一个批次能成功；读取快照在单一读事务中完成。
`history` 是编辑记录，尚非撤销栈或模拟运行快照。

显式创建不会覆盖已有数据库；普通打开不会隐式初始化。打开检查 application ID、格式版本、
SQLite 完整性与外键关系。陌生、损坏或不支持版本的文件报告错误，不自动重建或降级。
目前只有首版实验格式，没有旧项目迁移器；后续格式升级需先提供备份/迁移验证。
数据库之外的输入、程序与资源仍可存为普通文件，资源索引和一致性项目备份尚待实现。

该内部格式未冻结为 `docs/specs/` 的公开协议，不改变 `stk.graph/1` 或桌面桥 v1。
业务修改通过 `ProjectStore.apply`，不要让后续编辑器各自写 SQL。
下一步按[开发计划](development-plan.md)接入项目生命周期与共享表格，并实现参数引用和失效传播。
