# 本地项目存储（P1 实验版）

当前交付包括 SQLite 存储、本机桌面桥和原生项目表格编辑器：创建/打开项目、表、字段、记录、
字面量、稳定引用、轻量公式、错误定位、数据库备份/升级、修订冲突检查和持久撤销/重做。
Python 接口支持 Linux/macOS/Windows，不需要启动 Runtime 或安装科学/Qt 可选依赖。
文件登记、元数据检查与外部编辑入口见[项目文件索引](project-files.md)，同样使用普通类型化表格和撤销。
富内容插件、资源快照与执行计划
仍待开发；不能把本节理解为整个 P1 已完成。

## 在桌面中测试

使用[快速启动脚本](../desktop/QUICKSTART.md)重新编译后：

1. 选择 **文件 → 项目表格**，在已有区域打开新标签；也可从区域左上角的编辑器下拉菜单选择。
   表格较宽时可按 `Ctrl+Space` 最大化该区域。
2. 展开“打开或新建项目”，填绝对目录和项目名称，点击“新建”。已有项目只填目录后点击“打开”。
   也可把项目目录或 `project.sqlite3` 拖入项目表格区域。
3. 输入表名、添加表格，再展开“添加字段”设置字段名、类型及可选数值单位。
4. 添加记录，选中行与字段，在下方选择“字面量 / 单元格引用 / 公式”。字面量中的文本直接输入；
   数值、布尔和 JSON 使用 JSON 语法。引用可选择来源表格/记录/字段；公式可在“添加变量绑定”中
   选择来源并命名，然后使用变量名计算。绑定表显示来源与当前值，也可在高级面板直接修改绑定 JSON。
   点击“保存值”提交定义。
   “设为空值”保存显式 `null`，“清除定义”恢复未赋值，“重新载入已保存值”放弃当前草稿。
5. 点击“关闭项目”，再打开同一目录，确认数据与类型保留。每次成功修改即时保存；`Ctrl+S`
   仍是保存页面布局，不是提交单元格草稿。
6. 展开“管理表格、字段与记录”可改名或删除对象。标题栏的“撤销 / 重做”按整个修改批次恢复，
   删除后撤销会恢复原 ID 与顺序。未保存的单元格/名称草稿仍需明确重新载入。

各项目表格区域共享当前项目、表格和记录选择；排序使用显示顺序，编辑仍以 UUID 定位。
桥接进程重启会按目录和项目 UUID 重开，不会重放修改。若其他入口修改了项目，修订校验会拒绝旧草稿；
界面保留输入并要求重新载入核对。外部 CLI 的修改需点击“刷新”才能主动显示。
关闭整个程序后再次启动不会自动打开项目；布局只保存目录输入，点击“打开”恢复数据。

本阶段通过路径字段操作，尚无项目专用的系统文件对话框；表格是可排序列表加选中单元格编辑区，
还不是完整多维表格。字段/记录/表删除已提供修改命令，尚无对应桌面按钮；批量粘贴、富内容等继续补齐。

## 命令行

安装当前源码包后使用：

```sh
suan project create ./example-project --name "温度扫描"
suan project show ./example-project
suan project apply ./example-project --expected-revision 0 --commands edits.json
suan project history ./example-project
suan project backup ./example-project
# 仅旧格式需要显式升级，修订号以 show 的结果为准：
suan project upgrade ./old-project --expected-revision 3
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
| `set_reference` | `table_id`、`record_id`、`field_id`、`source: {record_id, field_id}` | 无 |
| `set_expression` | `table_id`、`record_id`、`field_id`、`expression`、`bindings` | 无 |
| `unset_cell` | `table_id`、`record_id`、`field_id` | 无 |
| `delete_record` / `delete_field` / `delete_table` | `id` | 无 |

未提供的新对象 ID 自动生成；需要在同一批次引用新对象时，像示例一样提前生成 UUID。
ID 必须是规范的小写带连字符 UUID 字符串。记录和字段必须属于同一张表；单元格以记录 ID 与字段 ID
定位，表格/字段改名不会影响已有值。当前快照按创建顺序显示，排序/过滤留给后续表格视图。

支持的类型为 `text`、有符号 64 位 `integer`、有限数值 `number`、`boolean`、`json`。
布尔值不作为数值接受，所有层级拒绝 NaN/Infinity。数值字段可登记单位字符串，
字面量不进行单位词表校验或换算；派生值按下述保守规则校验单位。未赋值单元格在 `values` 中缺席，
显式 `null` 则保存为空值；此阶段没有必填约束。

## 稳定引用与轻量公式

引用的身份是 `record_id + field_id`，不保存行号、列号或字段名称。记录与字段在来源端必须属于
同一张表，可以跨表引用。改名和排序不改变引用；删除来源后保留定义并报告 `missing_reference`，
不会悄悄指向下一行。重新写入字面量或清除单元格会移除原引用/公式。

接着上面的 Python 示例，可加入派生温度：

```python
derived = str(uuid4())
store.apply([
    {"op": "add_field", "id": derived, "table_id": table,
     "name": "Derived temperature", "type": "number", "unit": "K"},
    {"op": "set_expression", "table_id": table, "record_id": record, "field_id": derived,
     "expression": 'base + quantity(10, "K")',
     "bindings": {"base": {"record_id": record, "field_id": field}}},
], expected_revision=1)
assert store.snapshot()["tables"][0]["records"][0]["values"][derived] == 310
```

桌面 Python 面板中的 `stk.project.apply(...)` 使用同样的命令。变量绑定名称是本公式内的标识符，
不是项目对象 ID。编辑表达式时绑定 UUID 不变；变量可由桌面选择器插入，也可编辑 JSON。

首版语法支持数字、变量、括号、`+ - * / **`、`abs/min/max/round/sqrt/quantity`；不支持属性、
索引、导入、文件/网络、任意函数、Python `eval` 或 SQL。它只解释受限 AST，不执行 Python 源码。
最多 4096 字符、64 个变量、256 个 AST 节点及 32 层；指数是 -16…16 的无量纲整数，
`round` 小数位是 -12…12 的整数。结果必须有限，赋给 `integer` 字段还必须是有符号 64 位整数。

单位规则：

- 数字常量的单位是 `1`；无量纲来源字段应明确填写 `1`。未声明的来源单位不会被猜测。
- 加减和 `min/max` 要求相同、已知的单位字符串；`m` 和 `cm` 不自动换算。
- 乘法允许无量纲因子；除以无量纲值保留单位，同单位相除得到 `1`。
- `quantity(10, "K")` 为无量纲数字显式标注单位，不是单位转换函数。
- `sqrt` 仅支持无量纲值；暂不提供一般单位乘积/幂的代数或完整 UCUM 换算。
- 目标字段声明了单位时结果必须匹配；目标未声明时保存结果携带的单位供检查，不修改字段定义。

格式正确的引用/公式即使存在语法、循环、类型、单位或除零错误，也会保留定义和定位信息；
表格显示 `#错误代码`，编辑区显示原因。错误计算不沿用旧值；依赖错误的下游报告 `dependency_error`。
未赋值来源报告 `missing_value`；显式 `null` 可直接引用，但不能参与数值运算。
非法命令结构、非规范 UUID 或字面量类型错误仍拒绝整个事务。

快照中的每条记录继续提供 `values`；含派生单元格时还提供以字段 UUID 为键的 `definitions` 和
`evaluations`。成功项包含值、单位、`evaluated_revision`；失败项包含结构化 `error`。
修改只重算受影响的依赖项，改名不更新计算修订。依赖图使用迭代算法，长链不消耗 Python 递归栈。
计算缓存可由定义重建；缺失缓存的只读快照可临时求值，不增加编辑修订。
当前只实现标量值之间的传播，昂贵节点/运行结果的过期标记仍待后续接入，编辑不会启动模拟。

## 数据库备份与显式升级

新建项目使用格式 3；格式 1 仍可执行原有字面量命令，格式 2 仍可使用引用/公式，不会因为打开而迁移。
引用、公式、清除和删除命令需要至少格式 2，持久撤销/重做需要格式 3；桌面删除入口要求格式 3。
桌面提供“备份并升级项目”；CLI 使用 `project upgrade`，
Python 使用 `store.upgrade(expected_revision=...)` 或 `stk.project.upgrade(expected_revision=...)`。

升级先以 SQLite 在线备份 API 保存并检查旧修订，再在一个写事务中创建新表、更新格式和修订。
失败时原库回滚；已生成的备份保留。陈旧修订拒绝升级，也不会生成多余备份。重复升级当前格式是无修改操作。
备份存于项目的 `backups/format-版本-revision-修订-随机ID.sqlite3`，原项目 UUID 和数据保留。

“数据库备份”按钮、`project backup`、`store.backup()` 和 `stk.project.backup()` 也可独立使用，
不改变项目修订。要查看旧备份，先关闭项目，将备份复制到另一个目录并命名为 `project.sqlite3` 后打开。
**这是数据库备份，不包含外部程序、输入、图片或其他资源文件**；完整项目资源快照仍待开发。

## 实验格式与事务边界

目录中的 `project.sqlite3` 使用 SQLite application ID `STKP`，当前 `user_version=3`。
原物理表为 `project`、`tables`、`fields`、`records`、`cells`、`changes`；格式 2 新增
`definitions` 和可重建的 `evaluations`，格式 3 增加 `edit_journal`。字面量与定义分开。每次有效批次在一个
`BEGIN IMMEDIATE` 事务中校验修订、写值/定义、更新受影响缓存、提升一次修订并保存命令历史。
并发修改同一修订时仅一个批次能成功；读取快照在单一读事务中完成。
`history` 保留已发生的编辑、升级及撤销/重做事件，不是模拟运行快照。

显式创建不会覆盖已有数据库；普通打开不会隐式初始化。打开检查 application ID、格式版本、
SQLite 完整性与外键关系。陌生、损坏或不支持版本的文件报告错误，不自动重建或降级。
当前提供格式 1/2 → 3 的显式、备份优先迁移；更新的未知格式仍拒绝打开，不自动降级。
数据库之外的输入、程序与资源仍可存为普通文件，资源索引和一致性项目备份尚待实现。

该内部数据库格式未冻结为 `docs/specs/` 的公开协议，不改变 `stk.graph/1`。
业务修改通过 `ProjectStore.apply/undo/redo`，不要让后续编辑器各自写 SQL。
打开的 store 会记住项目 UUID；同一路径被另一项目替换后，旧 store 拒绝读写，需要明确重新打开。

## 本机桌面桥接口

[桌面桥 v1 §13](specs/stk-desktop-bridge-v1.md#13-local-project-sessions-additive-p1-extension)
增加 `project.create/open/list/close/snapshot/apply/history/backup/upgrade/undo/redo`，并提供 C++ `Client::project_*` 封装。
项目修改复用上述命令和修订校验，不绕过存储服务。桥中的句柄只在当前进程内有效，
桥重启后应按绝对目录重新打开；项目 UUID 和已提交内容保持不变。

每次编辑立即保存；关闭项目只释放句柄。编辑响应丢失后先重开并检查快照/历史，不能自动提高修订后重试。
`project.changed` 通知用于刷新；外部 CLI 修改需主动刷新，写入时仍有修订冲突保护。
快照/历史暂不分页，受桥的 16 MiB 消息限制。此接口仍是本机 stdio 通道，不是两台 STK 的直接连接。

原生桌面入口复用此接口；下一步按[开发计划](development-plan.md)继续资源版本、通用字段与运行快照。

## 持久撤销与重做

`store.undo(expected_revision=...)` / `redo(...)`、`stk.project.undo(...)` / `redo(...)` 与
`suan project undo/redo DIRECTORY --expected-revision N` 使用同一项目级栈。
每次 `apply` 的完整批次是一项，来自 UI、Python 或 CLI 的编辑共用历史；不是每个面板各有一个栈。

- 撤销/重做各自增加一次修订，保留原编辑历史，并记录 `target_revision`；不会把项目修订倒退。
- 栈保存到数据库，关闭重开或桥重启后仍在。新编辑清空重做分支；失败和冲突不改变栈。
- 恢复名称、类型、字面量、引用/公式、UUID 和显示顺序，只记录被编辑行的前后状态；公式缓存重新计算。
- 升级前的历史没有前值，不能事后撤销；升级自身也不能撤销。需要回到旧格式时使用升级前备份。
- 撤销不取消 Runtime 作业、不还原外部文件、不执行 Python，也不恢复未保存的输入框草稿。
- 快照的 `edit_history = {undo_revision, redo_revision}` 给出下一项原编辑修订，无对应项时为 `null`。
  空栈操作报错且不改变项目；响应丢失后检查新修订和历史，不自动重试。

目前没有撤销历史压缩或保留期限，大批删除会记录对应数据；完整资源和执行状态快照仍属后续开发。
