# 从模型参数建议到修改检查

AI 助手可以针对已捕获的单元格提出参数建议。**回复完成、保存建议、打开检查和应用修改是分别触发的操作。**
模型回复和保存建议都不会改变参数，也不会执行 Python、生成仿真输入或提交任务。
本机完整回归与界面复核已通过；平台验收结果另见[验收记录](runtime-validation.md)。

项目继续使用 SQLite 格式 8，不需要新增数据库迁移。模型与本机凭据配置沿用
[模型请求指南](project-requests.md)，上下文选择沿用[上下文指南](project-contexts.md)。

## 界面操作

1. 在项目表格中选定参数记录，进入 **AI 助手**，点击 **捕获选中记录**，保存该记录全部字段。
   多行或部分字段可在同页点击 **选择多行与字段…**，勾选并核对预览后明确捕获；Python 和讨论页也支持明确范围。
   核对捕获值、来源修订、字段类型、单位以及缺失或省略内容；后续改变表格选择不会更新这份上下文。
2. 在 **准备问题** 中将 **用途** 设为 **建议参数修改**，填写问题和模型，点击 **准备问题（不发送）**。
   这一步只保存用户消息、固定上下文和请求配置。普通讨论仍使用 **讨论数据**；改变用途不会修改已有请求。
3. 核对上方已保存的问题及数据范围，点击 **发送这条已保存的问题**。
   流式片段仅用于显示，须等完整回复持久保存后才可处理参数建议。
4. 查看建议摘要、目标字段和数值；在 **请求详情 → 保存的原始回复** 中可查看完整文字。
   点击 **保存建议供检查**，系统严格校验结构、选择范围、类型和原始修订，并运行只读预览，
   随后把草案及其来源一起保存。此步骤仍不应用修改；回复能显示出来也不代表它一定能通过保存校验。
5. 点击 **打开修改检查**。系统再次读取保存的草案，将其载入检查页；这一步不自动预览或应用。
   若已有检查草案、其他窗口仍在输入文字、项目已变化或窗口没有可用标签位置，会保留当前界面并提示原因。
6. 在检查页明确点击 **计算预览**，检查差异、类型、单位及受影响公式的结果，再点击 **应用已检查的修改**。
   应用走[持久草案](project-drafts.md)的原子回执与普通撤销流程。

正在检查的旧草案需要先自行查看并清空；清空检查页不会删除数据库中保存的草案。
应用或丢弃后，AI 建议保留相应状态及应用修订；打开历史问答或刷新回复时也会读取保存的状态。
关闭重开只恢复记录，不会自动发送、保存新建议、应用参数或启动仿真。

## 当前允许的建议

首版将建议编译为普通 `set_cell` 命令，并额外约束在该请求的原始捕获范围内。
这与手工草案的[来源关联](project-contexts.md)不同：手工关联说明依据，不自行限制命令的选中范围。

| 项目 | 当前规则 |
|---|---|
| 来源 | 只能使用 `stk.parameter-edits/1` 请求保存的完整回复；普通讨论或手工导入的 `assistant` 消息不能代替 |
| 范围 | 一张明确捕获的表，1–100 行、1–64 字段、最多 1000 个单元格；建议含 1–1000 个不重复目标 |
| 类型 | 仅 `text`、`integer`、`number`、`boolean`；整数限有符号 64 位，数字须有限，布尔不能当作数字 |
| 空值 | 允许设置显式 `null`，也允许给捕获时为空的单元格赋值；空白与未捕获、缺失或省略不同 |
| 数值与单位 | 使用字段原有类型和单位，不把字符串转成数字，也不自动换算单位 |
| 源值 | 目标行和字段必须存在于捕获内容中；目标原值被省略或整个上下文被省略时拒绝转换 |
| 定义 | 不替换公式或引用，不修改 JSON 字段、表结构，不创建或删除行、字段和表 |
| 大小 | 新值的 UTF-8 JSON 编码最多 16 KiB；回复摘要最多 4096 字符；完整回复最多 64 KiB UTF-8 |

其他已选单元格的省略不会自动扩大范围，也不允许推测被省略目标的内容。最终数值是否符合科研问题仍需用户检查；
结构和类型校验不能证明物理假设正确。运行准备、任务提交和代码执行继续使用各自的明确入口。

## 请求模式与回复格式

创建请求时的 `prompt_version` 默认为 `stk.text/1`，用于普通讨论。
参数建议明确使用 `stk.parameter-edits/1`，要求模型返回下面这样的单一 JSON 文档。
它仍是一条保存的助手文字，没有模型工具调用，也不能从 Markdown 代码块或自然语言中提取命令。

```json
{
  "format": "stk.parameter-edits/1",
  "context_id": "11111111-1111-4111-8111-111111111111",
  "base_revision": 42,
  "summary": "将已选记录的温度建议为 310 K。",
  "edits": [
    {
      "record_id": "22222222-2222-4222-8222-222222222222",
      "field_id": "33333333-3333-4333-8333-333333333333",
      "value": 310
    }
  ]
}
```

这里的 UUID 和修订仅用于展示格式；真实值必须匹配保存的请求上下文。顶层与每条编辑的字段必须恰好如上，
不接受附加的项目 ID、表 ID、操作名、候选快照或审批标记。项目与表由本机保存的来源确定。
重复 JSON 键、重复目标、额外文字、代码围栏、非有限数值、未知字段或错误类型均被拒绝。
摘要必须非空，空编辑数组不形成草案。

完成状态只表示完整文字已保存。模型返回不合格的 JSON 时，原回复仍可查看，但转换不会留下半份草案。
界面无法安全格式化的结构会退回原始文字；显示层不会执行或修复模型内容。

## Python 示例

以下示例在 STK 的 Python 面板中使用当前项目，假设已选记录所在表有唯一名为 `Temperature`、单位为 `K` 的数值字段。
可先在表格中核对或按自己的字段调整这项明确选择。`p` 固定当时打开的项目句柄；切换项目不会自动改投新的项目。

```python
from uuid import uuid4

p = stk.project
scope = p.selection()
assert scope['table_id'] and scope['record_id'], '先在项目表格中选择一条记录'
table = next(t for t in p.snapshot()['tables'] if t['id'] == scope['table_id'])
fields = [f for f in table['fields'] if f['name'] == 'Temperature']
assert len(fields) == 1 and fields[0]['type'] in ('integer', 'number')
assert fields[0]['unit'] == 'K'

context = p.contexts.capture(
    scope['table_id'], [scope['record_id']], [fields[0]['id']],
    expected_revision=scope['revision'], title='温度参数建议', context_id=str(uuid4()),
)
message = p.discussion.add(
    '建议把这条记录的 Temperature 改为 310 K，仅提出参数修改。',
    message_id=str(uuid4()), context_id=context['id'],
)
provider = p.requests.provider()
assert provider['model'], '先配置模型，或明确填写要使用的模型 ID'
request = p.requests.create(
    message['id'], request_id=str(uuid4()),
    configuration={'adapter': provider['adapter'], 'model': provider['model'],
                   'max_output_tokens': 4096},
    prompt_version='stk.parameter-edits/1',
)
print(request['id'], request['status'])  # pending；准备未发送。
```

核对已保存的问题和上下文后，另行明确运行发送；此调用不等待模型完成：

```python
p.requests.start(request['id'])
```

随后按需读取完整结果，查看原回复。保留原请求 ID，不因等待或响应丢失而创建另一条请求：

```python
current = p.requests.get(request['id'])
print(current['status'])
if current['status'] == 'completed':
    print(p.discussion.get(current['result']['message_id'])['text'])
```

确认需要把该回复保存供检查后，再运行转换。必须使用原始来源修订：

```python
saved = p.requests.propose_edits(
    request['id'], expected_revision=request['source_revision'],
)
print(saved['draft']['id'], saved['draft']['status'], saved['replayed'])
print(saved['proposal'])  # 关联助手消息、上下文和草案的来源记录。
```

在原生 AI 助手打开同一条已保存问答，然后使用 **打开修改检查**、预览和应用，可以保留该草案的身份及回执。
Python 中也可独立查看只读预览；只有另行明确调用 `drafts.apply` 才会改变参数：

```python
pair = p.requests.edit_proposal(request['id'])
draft = pair['draft']
assert draft is not None and draft['status'] == 'pending'
preview = p.preview(draft['commands'], expected_revision=draft['base_revision'])
print(preview)

# 核对预览后，另行明确执行：
# receipt = p.drafts.apply(draft['id'], expected_revision=draft['base_revision'])
# 不采用时，另行明确执行：p.drafts.discard(draft['id'])
```

## 保存、重试和过期建议

`propose_edits` 返回 `{request_id, draft, proposal, replayed}`。草案和来源 UUID 由原请求、项目与转换版本确定，
调用者不再分配第二组身份。只读预览之后会重新检查原始修订，再在一个事务内保存两条记录；
任一步失败均不留下单边记录。保存不增加项目修订，也不进入参数撤销历史。

`edit_proposal(request_id)` 只读返回 `{request_id, draft, proposal}`；尚未转换时后两项同时为 `null`，
包括尚未完成或普通讨论请求。它不创建草案，不预览，不发送模型请求。
保存响应丢失时先查询这个接口，再决定是否明确重试同一 `propose_edits` 调用。
`replayed: true` 表示找回原来保存的两条记录，不表示再次执行参数修改。

已有草案的状态可以是 `pending`、`applied` 或 `discarded`。原调用重试会返回同一身份和当前终态，
即使项目已继续编辑或已撤销应用，也不会重新生成待应用草案。应用本身的重试由 `drafts.apply` 返回原始应用回执；
撤销不会重置这个回执。丢弃后的同一建议也不能通过重试复活。

首次转换和后续应用都要求项目仍处于原始基础修订。期间表格发生修改，即使只是重命名，也会拒绝旧建议；
不能把 `expected_revision` 改为当前修订来绕过检查。需要新建议时，应明确捕获当前数据、准备并发送新请求，
旧消息与旧草案继续保留原来源。

## 兼容性与当前边界

本功能沿用格式 8，但扩展了请求的输入版本和桥方法。旧版读取器可能拒绝 `stk.parameter-edits/1` 记录；
数据库格式相同不代表旧版支持新的请求模式。旧 `stk.text/1` 的保存记录与幂等摘要保持不变，默认 Python 调用仍使用旧参数形状。
桥需同时声明 `project.requests.propose_edits` 和 `project.requests.edit_proposal`；原生界面在能力缺失时禁用参数建议用途。
详细字段以[桌面桥契约](specs/stk-desktop-bridge-v1.md)为准。

本轮验证使用受控回复，仍在进行本机回归与界面复核，不据此宣称真实模型一定会返回合格建议或各平台已验收。
更多编辑种类、扫描行生成、自动执行和独立运行提案不包含在这个参数修改入口中。
