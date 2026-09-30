# 用 Python 控制三维查看器

桌面 Python 面板中的 `stk.viewer` 通过 UI 主线程操作原生 `ViewerState`，与 Viewer/Properties
按钮共用状态。所有窗口共享这一 Viewer 数据源；布局与前台切换针对第一个主窗口。
这是本机控制接口，不是网络端点或远程 Python 服务。

## 打开结果与等待

```python
view = stk.viewer.open(
    "/absolute/path/to/results",
    preset="volume",
    parameters={"path": "field.vtk", "range": [0, 400]},
)
shown = stk.viewer.wait(timeout=120)
print(shown["error"], shown["layers"])
```

支持 `.stkp` / payload 目录、`result.json` / `series.json` 结果目录，以及需要预设求值的计算输出目录。
也可直接打开 `.dat`、`.npy`、`.vti`、`.vtk`、`.vtkhdf` 科学场文件，默认使用体渲染：
`stk.viewer.open("/absolute/field.vtk", preset="slice")`。该方式绑定父目录并固定初始 `path` 为所选文件名，
即使父目录另有 `result.json`，也不会打开另一份结果。切换场预设保留所选文件名；后续仍可明确修改 `path` 参数。
`source.field_file` 记录打开时的文件名，来源 key 区分同目录不同文件；它不是内容哈希。
有符号标量或向量分量可明确选择 `scalar-volume`，并填写 `field`、零起始 `component`；
`unit` 只更换结果标签，不转换数值，见[标量体渲染](scalar-volume.md)。默认 `volume` 仍计算模长。
可用预设及其参数声明见 `stk.viewer.presets()`；
启动期间 `ready=False` 表示元数据仍在加载，等待后再指定预设。载荷/已保存结果不接受图预设参数。
路径由 Python 按当前工作目录转为绝对路径；打开时默认切换到 Viewer 标签，`focus=False` 保持当前标签。

`open` 接受打开请求后即返回；图求值是异步的，不能将收到回复当成已经生成三维画面。
`status` 返回当前来源、参数、图层、求值/待修改状态和错误；`wait` 只等待当前来源。
它在求值失败时返回含 `error` 的状态，由调用者判断；超时抛出 `TimeoutError`，不会取消计算。
等待期间来源切换会报错，防止把另一份数据当成原请求完成。禁用自动求值后仍有待应用参数时，应先明确
`evaluate()` 再等待。状态读取会推动已有的 UI 延迟更新，但不会提交 Runtime 模拟任务。

## 纯读取分析配置

```python
capture = stk.viewer.graph_configuration(displayed=False)
configuration = capture["configuration"]  # 没有原始图定义时为 None
```

这项可选能力读取单次不可变配置，不推进延迟求值、刷新元数据或切换页面。
`displayed=True` 读取本机保存的已显示结果提交配置；`displayed` 必须是布尔值。
返回 Viewer 代次、选择模式、已显示图的哈希核对状态，以及图、提交参数、请求输出和完整来源提示。
没有原始定义的导入结果返回 `configuration=None`；不会根据预设名称或哈希重建图。
核对状态为 `True`、`False` 或 `None`，不验证源文件变化、输入内容或节点实现版本。

捕获响应不包含结果回执和解析值。需要持久保存时，把 `graph`、`parameters`、`requested_outputs`
明确组成[项目分析文档](project-analyses.md)再调用保存接口；来源提示不等于冻结的执行绑定。
旧桌面未协商此能力时返回 `unsupported`，没有桌面连接时为 `unavailable`；不会回退到会推动 UI 更新的 `status()`。

## 参数、图层和时间步

```python
key = stk.viewer.status()["source"]["key"]
stk.viewer.configure(
    auto_evaluate=False,
    parameters={"colormap": "cividis"},
    expected_source=key,
)
stk.viewer.evaluate(expected_source=key)
shown = stk.viewer.wait()

layer = next(item for item in shown["layers"] if item["has_opacity"])
stk.viewer.layer(layer["id"], visible=True, opacity=0.5, expected_source=key)
stk.viewer.reset_camera(expected_source=key)
```

`configure` 先检查整批设置，再应用。未知参数、错误类型、非法枚举或数值范围不会部分改动设置。
参数名与类型来自所选预设；图内部更深的语义/数据错误仍可能在求值时报告。图层使用稳定 ID，
不存在的图层会拒绝，`opacity` 必须在 0–1 且该图层支持整体透明度；体渲染传递函数应通过预设参数设置。

可选设置还包括 `overlays`、`prefetch`、`fps`（0.1–60）、`loop`。关闭自动求值会暂停尚未开始的参数
更新；重新开启会安排待应用参数，已经开始的求值不会因此取消。`evaluate()` 总是明确请求求值。
`preset(id)` 切换预设并重新求值；可用于计算目录/Runtime 任务来源。

```python
state = stk.viewer.status()
print(state["steps"], state["step_index"])
# 有时间序列时，按可用步骤列表的索引选择：
# stk.viewer.step(0)
# stk.viewer.configure(fps=4, loop=True)
# stk.viewer.play(True)
# stk.viewer.play(False)
```

`expected_source` 是可选的来源身份检查：与 `status()["source"]["key"]` 不同则返回冲突。
它检查当前数据来源，不是文件内容哈希，也不是所有参数的事务修订。需要冻结内容时使用项目输入快照。
不提供该参数时，操作作用于执行时的当前 Viewer。

`cancel()` 取消 Viewer 图求值/待更新，`close()` 清空当前查看器；二者都不取消 Runtime 模拟任务。
参数预检失败保留已有状态；打开请求被接受之后，文件解析或图求值仍可能失败，请检查返回状态。
相机任意变换、拾取/探针、图片导出和任意节点图编辑尚未通过此 facade 全部开放。

可运行的[项目温度扫描示例](../examples/project_scan/README.md)包含 `show.py`，将收集的 VTK 结果直接
打开成原生三维视图；示例使用合成数据，不是物理模型验证。
