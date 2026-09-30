# 保存项目分析文档

分析文档把节点图、提交参数和选定输出保存在项目 SQLite 中，可以关闭项目后重新读取，也可以撤销和重做。
当前桌面支持保存、浏览、检查、改名和编辑提交参数；Python 接口另支持替换完整定义。保存或打开定义不会运行节点、
配置 Viewer、读取输入文件或提交任务。

先了解[分析节点图检查](analysis-graphs.md)和[项目表格](project.md)。持久化沿用普通表格及撤销机制，
要求项目格式至少为 3；只保存定义不需要升级到当前格式 9，也不自动升级旧项目。
把定义绑定到输入快照并执行时，使用另行准备的[分析执行记录](project-analysis-runs.md)，这一步需要格式 9。

## 在桌面保存和打开

打开项目，选择 **视图 → 分析图**（英文 **View → Node Graph**），或在区域编辑器下拉框选择“分析图”。
三个标签区分定义来源：

| 标签 | 检查的内容 |
|---|---|
| 当前参数 / Current parameters | 当前 Viewer 的图定义、提交参数和请求输出 |
| 已显示结果 / Displayed result | 本机记录的该结果提交配置；其验证边界见[节点图指南](analysis-graphs.md) |
| 保存的分析 / Saved analysis | 从当前项目明确读取的分析文档，不关联 Viewer 的结果回执 |

1. 在“当前参数”或“已显示结果”中确认要保存的定义，展开右侧 **项目分析文档 / Project analyses**。
   没有可用图定义时不能保存；导入结果没有原始图时不会自动重建。
2. 填写名称，点击 **保存为新分析 / Save as new analysis**。每次明确保存创建新 UUID，
   不覆盖同名文档；也可以从“保存的分析”复制一份新文档。
3. 保存成功后打开“保存的分析”供检查。如果等待期间已经选择了另一个标签，迟到的保存回复保留新的标签选择。
4. 点击 **刷新分析列表 / Refresh analysis list** 获取当前页摘要，再单击列表中的记录，明确读取其完整定义。
   列表每页 50 项，可翻页；刷新列表不等于重新读取已经打开的定义。
5. 在“保存的分析”中，**重新载入定义 / Reload saved definition** 读取当前记录；
   修改名称后点击 **保存名称 / Save name**，以此前读取的项目修订保存同一份完整定义和新名称。
   这个按钮只改名，不把 Viewer 的当前图替换到该文档中。

项目发生任何编辑后，已有列表和已打开定义仍保留之前的内容，并显示修订过期提示。改名前须重新载入；
外部进程也可能修改项目，最终保存由数据库修订检查决定，冲突时不会覆盖新内容。
刷新、选择记录和重新载入只读取项目，不触发图求值。当前画布仍用于检查，尚不提供连线编辑或直接修改节点内部参数；
下方的参数编辑只修改文档的图级 `parameters` 覆盖值。

保存和改名各自是一个普通项目编辑批次，与表格编辑共用撤销栈。撤销创建可移除记录，重做恢复相同 UUID；
撤销改名恢复旧名称及定义。撤销之后刷新列表或重新载入，查看当前保存状态。

## 编辑保存分析的参数

在“保存的分析”的 **定义 / Definition** 页明确打开一份可读取的分析。参数表列出图中声明的参数，
以及已经保存在文档中的未声明覆盖项；来源列区分显式提交值、图默认值和未提供值。
默认值只供检查，打开编辑器不会把默认值补写进文档。未知覆盖项也不会被自动删除。

1. 选择一行，修改选中的值。声明为字符串且当前值也是字符串（或尚未提供值）的参数使用原样文字；
   当前值为 `null` 或其他类型时使用严格 JSON，避免未改文字就发生类型转换。其他参数也使用严格 JSON，
   如 `2`、`1.0`、`true`、`[null, null]` 或 `{"enabled": true}`。
2. 明确应用文字输入到本地草稿，再点击保存参数。无效 JSON 留在输入框中并显示错误；
   不会改存成字符串，也不会以此前的有效值悄悄完成保存。
3. “设为 null”保存显式 JSON `null`；“移除覆盖”删除该键，让图求值时采用它的默认规则。
   两者不同。原样文字模式中的空内容是 `""`，文字 `null` 是字符串 `"null"`；JSON 模式用 `"null"` 明确输入字符串。
4. 保存只替换该文档的提交参数，保留名称、节点图、输出选择与其他覆盖项；一次保存对应一个普通撤销批次。
   原有运行记录仍使用准备时冻结的定义，下一次准备才采用新保存的参数。

整数保留有符号或无符号 64 位的精确值，范围 `[-2^63, 2^64-1]`；超出范围的整数字面量会被拒绝。
`1` 与 `1.0`、`0.0` 与 `-0.0` 的表示会保留，不经浮点数表单中转。
单个编辑框最多接受 384 KiB UTF-8 文字，最终仍受下方 64 KiB 规范化参数与完整文档限制；
这一区别允许带小数标记的合法 JSON 原样编辑和应用，不因文字表示更长而被拒绝或在替换输入时截短。
这里只检查可存储的 JSON 与大小限制。保存成功不代表参数适合节点或图可以运行；需要时另行明确校验。

未保存草稿或尚未应用的文字会阻止替换当前定义、重载、改名、保存新副本和准备运行。
先明确保存或放弃这些修改；切换检查模式可以暂时保留草稿。画布与校验仍使用最后读取或保存的定义，
草稿状态会单独提示，不把尚未保存的参数显示成已经验证的定义。

项目修订改变后，草稿保留但不能继续写回旧修订。放弃并重新载入当前定义后再修改，界面不自动合并。
关闭或切换项目、桥会话变化后，旧草稿不会转移到新项目；编辑器仍在时可保留本地文字供检查。
草稿只保存在该编辑器内存中，关闭编辑器或退出程序会丢失，布局文件不保存这些内容。
保存回复不确定时先按下面的方法读取核对；当前保存内容与本地候选不同或记录已删除时，不自动清除本地修改。

## 保存回复不确定时

如果保存已发出，但超时或回复无法确认，在原项目打开会话仍有效时，界面保留此次文档 UUID，并暂停新的保存操作。
点击 **核对保存标识 / Check saved identity** 只按这个 UUID 读取，不重新发送原写入：

- 找到相同内容：说明本次读取时文档存在，不等于找回了原始事务回执。
- 找到不同内容：先检查当前定义，可能已有后续编辑。
- 没有找到：只说明本次读取时不存在，之后可以再次明确保存新文档。

关闭编辑器、切换项目或桥会话后，待核对 UUID 会记入本地应用日志；重新打开原项目后按 UUID 核对。
关闭界面或取消本地等待不保证撤销已提交的 SQLite 编辑。不要因回复丢失就提高修订号并盲目重发。

桌面布局只保留编辑器类型及检查模式，不保存已打开的项目、文档 UUID、完整定义或未提交名称。
恢复布局后仍需明确打开项目、刷新列表并选择记录。

## Python：从 Viewer 明确复制并保存

在[桌面 Python 面板](scripting.md)中，`stk.viewer.graph_configuration(*, displayed=False)`
读取一个脱离 Viewer 内部状态的配置副本，不推进待求值工作、加载新目录或改变焦点。
`displayed=True` 请求本机记录的已显示结果配置；参数必须是布尔值。
此可选能力未协商时返回 `unsupported`，没有桌面时返回 `unavailable`。

```python
from uuid import uuid4

p = stk.project
capture = stk.viewer.graph_configuration(displayed=False)
configuration = capture["configuration"]
if configuration is None:
    raise RuntimeError("当前没有可保存的图定义")

document = {
    "format": "stk.analysis-document/1",
    "graph": configuration["graph"],
    "parameters": configuration["parameters"],
    "outputs": configuration["requested_outputs"],
}
analysis_id = str(uuid4())       # 保留此标识，以便回复丢失时核对
revision = p.analyses.list()["revision"]
receipt = p.analyses.create(
    "体渲染分析", document,
    analysis_id=analysis_id, expected_revision=revision,
)
print(receipt["record_id"], receipt["revision"])
```

捕获响应还包括 `viewer_version`、`displayed` 和 `displayed_graph_verified`。
`viewer_version` 是本次 Viewer 检查代次，不是项目修订；验证标记只描述已显示回执与图哈希的核对情况。
`configuration.source`、`preset_id`、来源路径和验证标记都不属于分析文档，不应一起持久化为执行保证。
捕获与保存是两步明确操作，保存的是捕获副本；随后 Viewer 变化不会改写这份副本。
完整捕获语义见 [Viewer Python 指南](scripting-viewer.md)及[桌面桥协议](specs/stk-desktop-bridge-v1.md)。

接口签名如下，所有修改均要求调用者提供当前项目修订：

```python
p.analyses.create(name, document, *, analysis_id, expected_revision)
p.analyses.update(analysis_id, name, document, *, expected_revision)
p.analyses.get(analysis_id)
p.analyses.list(*, offset=0, limit=50)
```

`create` 要求未占用的 UUID；重复创建返回冲突。`update` 替换同一 UUID 的完整名称及定义，不是局部合并。
修改前读取完整记录并使用该次读取的修订：

```python
read = p.analyses.get(analysis_id)
analysis = read["analysis"]
if analysis["state"] != "readable":
    raise RuntimeError(analysis["error"])

replacement = analysis["document"]
replacement["outputs"] = []    # 明确不选择输出，不自动替换成“全部输出”
receipt = p.analyses.update(
    analysis_id, "暂不选择输出", replacement,
    expected_revision=read["revision"],
)
page = p.analyses.list(offset=0, limit=50)
print(page["revision"], page["total"], page["analyses"])
```

列表只返回摘要，支持 `offset >= 0`、`limit` 为 1–100；一次 `get` 返回完整记录及观察到的修订。
列表摘要为 `{id, name, format, state, error}`，完整记录再加 `document`。
外层同时返回 `table_id`、`compatible`、`error`；不存在分析表时列表为空，不会因读取而创建表。
写入返回 `{revision, commands, table_id, record_id}`。项目句柄固定于获取 `p` 时的项目打开会话，
关闭并重新打开项目后须使用新的句柄，不会自动改写到另一个项目。

## 普通 Python 直接访问

无桌面时可通过 `ProjectStore` 使用同样的存储接口；Viewer 捕获仍需要已连接的原生桌面。

```python
from suan.project import ProjectStore

store = ProjectStore("/absolute/path/to/project")
page = store.analyses.list(offset=0, limit=50)
read = store.analyses.get(analysis_id)
if read["analysis"]["state"] == "readable":
    store.analyses.update(
        analysis_id, "新名称", read["analysis"]["document"],
        expected_revision=read["revision"],
    )
```

`store.analyses.create(...)` 的参数也与桌面接口一致；直接 API 同样执行修订检查、事务回滚和普通撤销记录。
当前没有专用的 `suan project analyses` CLI 子命令。

## 表格结构、草稿与限制

每份文档占普通表格的一条记录，五个固定字段保存 `name`、`format`、`graph`、`parameters`、`outputs`；
后三者是 JSON 单元格。固定表与字段 UUID 定义在 [analyses.py](../suan/project/analyses.py)，
改表名或字段名不改变身份，自定义字段可以保留。
节点 ID 与 `$param` 引用仍属于图文档内部，尚未拆成“每个节点一条记录”，也没有项目流程层或子图层级。

`stk.analysis-document/1` 只接受上述四个文档键；图遵循 [graph v1 结构契约](specs/stk-graph-v1.md)。
未知节点类型、重复节点 ID、循环或悬空连接可以保存为草稿。`readable` 只代表结构可读取，
不能据此断定可运行；需要时明确点击“校验节点图”或调用 [Python 图校验](scripting-graphs.md)。
提交参数可保留尚未声明的覆盖项，语义检查留给显式校验；选定输出必须是图中声明的不同名称。

当前有以下有界接口限制：

| 内容 | 限制 |
|---|---|
| 名称 | 非空白，最多 256 字符、1024 UTF-8 字节，不含 NUL |
| 图 | 最多 256 KiB、200 节点、64 项图参数声明；每节点参数最多 64 KiB |
| 提交参数 | 最多 64 个覆盖项、64 KiB |
| 输出选择 | 最多 256 个不同的已声明输出；允许空列表 |
| 完整文档 | 最多 384 KiB，JSON 深度最多 64；仅普通 JSON、有限数字和可表示的 64 位整数 |
| 管理的集合 | 最多 128 条记录、4 MiB 已存储管理单元格 JSON |
| 写入后的完整项目快照 | 最多 12 MiB；超过时整次写入连同修订、历史和重做栈变化回滚 |

这些写入限制只保证分析文档 API 接受的修改。普通表格编辑或撤销仍可能使集合超限，此时分页读取仍可诊断；
后续 API 写入要求最终状态回到全部限制内，不因“比之前小”而放行。
最终快照检查沿用项目纯标量表达式求值，但不加载节点插件或执行图；分析文档读取直接检查字面量，不求值表达式。

手工编辑造成的无效记录返回 `invalid` 和简短原因；未来文档版本返回 `unsupported`，两者 `document` 都为 `null`。
无法安全显示的名称或格式为 `null`。缺失或不兼容的固定字段使 `compatible=false`，需撤销或明确修复结构，
不会自动补表覆盖信息。已知格式中的坏字面量可用完整 `update` 明确替换；管理字段若改为公式或引用，
须先通过普通表格操作恢复字面量，分析 API 不会静默覆盖。未来格式不能通过 `update` 降级。

保存不复制数据、不冻结执行来源绑定或远端文件、不保存结果回执，也不冻结节点实现及节点目录默认值。
保存的显式图参数默认值仍在图 JSON 中；检查器显示的节点类型和节点默认值来自当前加载的目录。
这些文档本身不是可直接重放的执行快照；[分析执行记录](project-analysis-runs.md)另行冻结文件映射与内容哈希。
实际运行和跨平台渲染仍须按[运行验收记录](runtime-validation.md)单独验证。
