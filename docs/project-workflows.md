# 项目工作流（实验，W3a）

更新：2026-10-07。状态：**保存、读取与校验（Python 与后台服务，W3a）、桌面“工作流”编辑器与进入分析/面包屑返回（W3b）
和图形编辑（W3c）已实现；按行运行与过期标记属于 W4，尚未实现**。设计与所有者确认的决定见
[项目工作流与子图导航](design/project-workflows.md)。文档格式 `stk.workflow/1` 是实验格式，未写入 `docs/specs/` 的已发布协议。

工作流把项目里已有的对象串成一条过程：参数表 → 输入文件或仿真 → 保存的分析。它只保存引用和连线，
不复制这些对象，也不运行任何东西。示例项目（工作台“创建示例项目”或 `suan demo`）会额外保存一份
“Temperature scan / 温度扫描”：算例表 → 场文件快照 → 温度场分析。

## 在桌面查看与编辑

工作台“其他”→ **工作流** 打开画布：步骤、带类型的连线、校验问题与所选步骤的引用；分析步骤可 **进入分析**，
在同一区域的分析图中打开，并用画布上方的“‹ 工作流名”返回。

编辑先形成未保存的候选（标题注明“未保存”），每次修改后自动检查候选并列出问题；**保存工作流**是一次可撤销的项目编辑，
有问题也能保存（工作流是草稿），**放弃修改**回到已保存版本：

- **编辑工作流**面板：改名；按种类选择项目中已有的参数表、输入快照、仿真模板或保存分析后 **添加步骤**；新建或删除工作流
  （删除可用项目撤销恢复）。
- **所选步骤**面板：步骤名称；每个输入从同类型的输出中选择来源；“先完成”的步骤；分析步骤的每个图参数选择“使用分析中的值”
  “固定值”（JSON）或“参数表字段（按行取值）”；删除步骤。
- 画布：拖动步骤改位置；从输出端口拖到同类型输入端口连线，类型不符时拒绝并说明；拖到（等待）设置先后；Delete 删除所选步骤。

其他项目编辑使修订前进时，未改动这份工作流就保留本地修改并可继续保存；这份工作流在别处被改动时，本地修改不能保存，
放弃后显示当前版本。详见[桌面指南](desktop.md#工作流)。

## 文档

```json
{
  "format": "stk.workflow/1",
  "steps": [
    {"id": "cases", "kind": "table", "ref": {"table": "<表格 UUID>"}},
    {"id": "fields", "kind": "files", "ref": {"snapshot": "<快照 UUID>"}, "after": ["cases"]},
    {"id": "temperature", "kind": "analysis", "ref": {"analysis": "<保存分析 UUID>"},
     "inputs": {"data": {"from": "fields.files"}},
     "parameters": {"colormap": {"$field": "<文本字段 UUID>"}}}
  ],
  "ui": {"positions": {"cases": [0, 0], "fields": [260, 0], "temperature": [520, 0]}}
}
```

| 种类 | `ref` | 输入 | 输出 |
|---|---|---|---|
| `table` 参数表 | `{"table": 表格 UUID}` | — | `rows` |
| `files` 输入文件 | `{"snapshot": 快照 UUID}` | — | `files` |
| `simulation` 仿真 | `{"template": "muferro/1"}` | `rows`（须来自该模板的案例表） | `files` |
| `analysis` 分析 | `{"analysis": 保存分析 UUID}` | 分析图中源节点的每个 `binding` 名（`files`） | 分析图的每个输出（`result`） |

- `inputs` 是数据流：`{"from": "步骤.端口"}`，端口类型须一致。`after` 是执行依赖：须先完成的步骤。
- 分析步骤的 `parameters` 只能设置保存分析图中声明的参数，值为字面量或 `{"$field": 字段 UUID}`。
  字段须属于本工作流中某个参数表步骤，类型须兼容（数字字段对数字参数、文本字段对字符串/枚举参数等），
  参数声明了单位时字段单位须相同；不做单位换算。字面量在准备运行时由图校验检查。
- 步骤可带 `label` 和 `x-` 开头的扩展键，保存后原样保留；`ui` 中除 `positions` 外的内容也原样保留。
- 上限：每个项目 128 份工作流、合计 4 MiB；每份 200 个步骤、256 KiB；每个步骤的参数 64 KiB。

## 保存与校验

保存只检查文档形状，不检查引用是否存在（工作流是草稿）；与保存分析一样存在项目内的固定表格中，
每次保存是一次带预期修订的普通编辑，可撤销/重做。删除沿用项目表格的删除行。

**校验**读取当前项目，逐步解析引用并检查连线，结果中的每个问题带步骤 ID 和路径（例如 `steps/2/inputs/data`）。
它不写入项目、不运行节点、不准备运行、不读取数据文件、不调用模型。问题代码：

| 代码 | 含义 |
|---|---|
| `duplicate_step`、`ambiguous_step` | 步骤 ID 重复；连线指向重复的 ID |
| `unknown_kind`、`invalid_reference` | 不认识的种类；`ref` 的键或 UUID 不合规 |
| `missing_reference`、`unreadable_reference` | 引用的表格、快照或分析不存在或无法读取 |
| `unknown_template`、`template_table` | 仿真模板未注册；仿真的行不来自该模板的案例表 |
| `dynamic_binding` | 分析的源节点用图参数给出绑定名，工作流无法确定输入端口 |
| `unknown_port`、`missing_step`、`missing_port`、`type_mismatch`、`missing_input` | 输入端口、来源步骤或端口不存在；类型不一致；必需输入未连接 |
| `unknown_parameter`、`field_not_in_workflow`、`parameter_type`、`unit_mismatch` | 参数未声明；字段不在本工作流的参数表中；类型或单位不兼容 |
| `cycle` | 数据流与执行依赖形成环 |

校验结果的 `steps` 按文档顺序给出每个步骤引用的对象名称、保存分析的内容哈希（规范 JSON 的 SHA-256）、
快照文件数、带类型的输入/输出端口与分析图参数，供界面显示；引用无法解析时端口为空。

## Python

桌面 Python 控制台、终端或 Jupyter（`suan.scripting.headless`）中：

```python
from uuid import uuid4

p = stk.project
listed = p.workflows.list()                         # 分页摘要：名称、格式、状态
doc = p.workflows.get(listed["workflows"][0]["id"])["workflow"]["document"]
check = p.workflows.validate(doc)                   # {revision, ok, issues, omitted_issues, steps}
for issue in check["issues"]:
    print(issue["code"], issue["step"], issue["path"], issue["message"])

doc["steps"][2]["label"] = "温度场（体绘制）"
revision = p.snapshot()["project"]["revision"]
p.workflows.update(listed["workflows"][0]["id"], "Temperature scan / 温度扫描", doc, expected_revision=revision)
p.workflows.create("Copy", doc, workflow_id=str(uuid4()), expected_revision=revision + 1)
p.workflows.choices()  # 可引用的参数表、输入快照（新的在前）、可读的保存分析与已注册仿真模板
```

后台服务方法为 `project.workflows.create/update/get/list/validate/choices`，见
[桌面桥协议](specs/stk-desktop-bridge-v1.md)的可选扩展说明。
