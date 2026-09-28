# 本地项目存储（P1 实验版）

当前交付包括 SQLite 存储、本机桌面桥和原生项目表格编辑器：创建/打开项目、表、字段、记录、
字面量单元格、稳定标识、修订冲突检查和事务修改历史。Python 接口支持 Linux/macOS/Windows，
不需要启动 Runtime 或安装科学/Qt 可选依赖。引用/公式、撤销、富内容插件、资源快照与执行计划
仍待开发；不能把本节理解为整个 P1 已完成。

## 在桌面中测试

使用[快速启动脚本](../desktop/QUICKSTART.md)重新编译后：

1. 选择 **文件 → 项目表格**，在已有区域打开新标签；也可从区域左上角的编辑器下拉菜单选择。
   表格较宽时可按 `Ctrl+Space` 最大化该区域。
2. 展开“打开或新建项目”，填绝对目录和项目名称，点击“新建”。已有项目只填目录后点击“打开”。
   也可把项目目录或 `project.sqlite3` 拖入项目表格区域。
3. 输入表名、添加表格，再展开“添加字段”设置字段名、类型及可选数值单位。
4. 添加记录，选中行与字段，在下方编辑值并点击“保存值”。文本直接输入；数值、布尔和 JSON
   使用 JSON 语法。“设为空值”保存显式 `null`。“重新载入已保存值”放弃当前单元格草稿。
5. 点击“关闭项目”，再打开同一目录，确认数据与类型保留。每次成功修改即时保存；`Ctrl+S`
   仍是保存页面布局，不是提交单元格草稿。

各项目表格区域共享当前项目、表格和记录选择；排序使用显示顺序，编辑仍以 UUID 定位。
桥接进程重启会按目录和项目 UUID 重开，不会重放修改。若其他入口修改了项目，修订校验会拒绝旧草稿；
界面保留输入并要求重新载入核对。外部 CLI 的修改需点击“刷新”才能主动显示。
关闭整个程序后再次启动不会自动打开项目；布局只保存目录输入，点击“打开”恢复数据。

本阶段通过路径字段操作，尚无项目专用的系统文件对话框；表格是可排序列表加选中单元格编辑区，
还不是完整多维表格。字段/记录删除、批量粘贴、富内容与跨表引用将继续补齐。

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

该内部数据库格式未冻结为 `docs/specs/` 的公开协议，不改变 `stk.graph/1`。
业务修改通过 `ProjectStore.apply`，不要让后续编辑器各自写 SQL。
打开的 store 会记住项目 UUID；同一路径被另一项目替换后，旧 store 拒绝读写，需要明确重新打开。

## 本机桌面桥接口

[桌面桥 v1 §13](specs/stk-desktop-bridge-v1.md#13-local-project-sessions-additive-p1-extension)
增加 `project.create/open/list/close/snapshot/apply/history`，并提供 C++ `Client::project_*` 封装。
项目修改复用上述命令和修订校验，不绕过存储服务。桥中的句柄只在当前进程内有效，
桥重启后应按绝对目录重新打开；项目 UUID 和已提交内容保持不变。

每次编辑立即保存；关闭项目只释放句柄。编辑响应丢失后先重开并检查快照/历史，不能自动提高修订后重试。
`project.changed` 通知用于刷新；外部 CLI 修改需主动刷新，写入时仍有修订冲突保护。
快照/历史暂不分页，受桥的 16 MiB 消息限制。此接口仍是本机 stdio 通道，不是两台 STK 的直接连接。

原生桌面入口复用此接口；下一步按[开发计划](development-plan.md)继续字段能力、参数引用和失效传播。
