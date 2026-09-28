# Python 分析图操作

桌面 Python 面板的 `stk.graph` 复用已有 `suan.graph` 节点、契约、缓存和独立求值进程。
可以编辑图的 JSON、校验端口连接、计算数据并读取表格/载荷/图片/导出文件。
这不是原生 Node Editor；图形节点编辑器、项目子图导航与持久分析版本仍在计划中。

## 从节点连接开始

```python
catalog = stk.graph.catalog()
print([node["id"] for node in catalog["nodes"]])
print([preset["id"] for preset in stk.graph.presets()])
```

下面连接文件读取节点与统计节点，分析已收集的扫描结果。先将 `directory` 改为实际包含
`field.vtk` 的结果目录；示例字段 `response` 是合成标量，并非物理求解器有效性证据。

```python
from uuid import uuid4

graph = {
    "schema": "stk.graph/1", "id": "scan-statistics", "catalog": {"stk": 1},
    "nodes": [
        {"id": "source", "type": "stk.source.file@1",
         "params": {"binding": "data", "path": "field.vtk"}},
        {"id": "stats", "type": "stk.analysis.statistics@1",
         "inputs": {"in": {"from": "source.out"}},
         "params": {"fields": ["response"], "components": "each"}},
    ],
    "outputs": {"statistics": "stats.out"},
}
checked = stk.graph.validate(graph)
if not checked["ok"]:
    raise ValueError(checked["issues"])

response = stk.graph.evaluate(
    {"graph": graph, "outputs": ["statistics"]},
    eval_id=uuid4().hex,
    local_bindings={"data": directory},
)
print(response["result"]["outputs"]["statistics"])
```

校验返回 `{ok, issues}`，错误包含稳定代码和 JSON 指针；未知节点和不兼容端口不会被静默接受。
求值可用 `{preset: "volume", parameters: {...}}` 代替完整 `graph`。
节点所需可选依赖仍须安装在桌面桥的 Python 环境中。

## 求值与返回值

`evaluate(request, *, eval_id, local_bindings=None, connection=None, node=None, mode="local", wait=None)`
同步等待当前调用，返回完整 `{result, blob_dir, action?}`。它不改变 Viewer 选择，也不自动修改项目表格。
图文档、参数、输出选择和预算使用[图协议](specs/stk-graph-v1.md)；编辑时可设置受约束的
`request.budget`。`result.errors` 可能表示部分输出失败，必须检查需要的输出，不能只看调用是否返回。

- `local_bindings` 把图中绑定名映射到本机目录，helper 解析为绝对路径。本机图在独立进程内执行。
- 读取 Runtime 任务文件可用 `connection="runtime:lab"` 和
  `request.bindings={"data": {"task_id": task_id}}`。保存的 SSH 连接也使用同一个本机转发端点；
  文件取回后在本机求值，不是在 SSH 远端执行 Python。
- `mode="hub"` 必须提供 `hub:...` 连接及节点 ID，不能带本机目录绑定。`wait` 控制 Hub 等待秒数。
  待审核时保留 `action.state == "review"`、`result == None`，不自动批准。

`eval_id` 必须由调用者明确保存。本机 ID 只标识当前活动求值：活动 ID 冲突会拒绝，完成后再调用会重新求值，
不能当作持久运行记录。Hub 同一节点、ID 和请求恢复同一操作；变更请求需使用新 ID。
网络错误、超时和 worker 故障不会触发 helper 自动重试。

## 表格、数据文件与探针

小表格的结果包含 `column_names`、按列数组 `columns`、`units` 和 `attrs`；大型表格/值改为 JSON blob。
载荷引用二进制 buffers，图片、绘图和导出文件也使用 SHA-256 blob；格式详见图协议 §9。

```python
blobs = stk.graph.ensure_blobs([digest])  # 本机缓存
# Hub 缺失的 blob 可通过 connection="hub:lab" 显式下载。
if blobs["missing"]:
    raise FileNotFoundError(blobs["missing"])
print(blobs["blobs"][digest]["path"])
```

缓存路径不是项目持久文件；需要长期保存时明确复制到项目并登记到文件索引。
`ensure_blobs` 查找现有文件或下载缺失内容，已存在的本机缓存不会在每次查询时重新哈希。
归档时应校验实际字节的摘要，不能只信文件名。

`probe(pick, *, graph=None, preset=None, context=None, position=None, local_bindings=None,
connection=None, node=None)` 使用载荷中的 `layer.pick.probe` 描述定位原始场。
不传 `position` 只返回来源 `target`；传入三维世界坐标后还返回 `sample`（位置、值、单位等）。
`context` 可提供 `values`、`result`、Runtime `bindings`；本机输入使用 `local_bindings`。
它与原生 Viewer 的探针共用求值规则，但不会设置界面的拾取高亮。
`colormaps()` 返回已有色图表、别名和颜色定义。

## 中断边界

中断或关闭控制台会取消**该次脚本正在等待的本机图求值**。排队中的调用被移除，不会取消其他视图
正在运行的图；活动 native 运算不响应时，独立图 worker 会被终止，下一次求值重新启动。

对于 Hub，中断只停止本机等待；远端分析和 Runtime 模拟继续。保留原 `eval_id`，以后明确查询/恢复。
`stk.graph.cancel(eval_id, connection=..., node=...)` 才显式请求取消对应 Hub 图；
本机图只需 `cancel(eval_id)`。图取消不等同于取消 Runtime 模拟任务。

`stk.viewer.wait()` 是另一类操作：它只轮询界面状态，中断等待不会取消 Viewer 的独立图求值。
