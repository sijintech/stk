# STK Python 编程

状态：2026-09-28 已实现原生 Python 面板、独立会话、项目/Runtime 操作 API 和本机布局控制首版。
完整方向见[设计记录](design/scripting-and-connections.md)，全部操作覆盖与远程控制仍在后续计划中。

`stk.muferro` 提供案例导入、选行准备、结果收集和三维打开，复用项目/Runtime/Viewer API，
与原生 MuFerro 面板使用同一实现。步骤和参数见[完整仿真指南](simulation-muferro.md)。

## 在界面中运行

更新源码并用[启动脚本](../desktop/QUICKSTART.md)增量编译，选择 **文件 → Python**。
也可以在任一区域的编辑器下拉框中选择 Python；多个区域共用一个执行会话，各自保留输入草稿。

1. 在多行输入框中输入或粘贴代码。Enter 换行并保留行首空格，Tab 插入四个空格，
   上/下箭头按行移动；支持选区、复制/粘贴、撤销和中文预编辑。
2. 点击“运行”，或按 Ctrl+Enter（macOS 为 Cmd+Enter）。最后一个表达式会显示结果。
3. “中断”停止忙碌的 worker；空闲时同一按钮为“重置”，清除变量。“清空输出”只清空可见输出。
4. “上一条/下一条输入”浏览本次程序中的最近 100 条输入，选择不会自动执行；“API 帮助”打印操作目录。
5. 展开“运行 Python 文件”，填写绝对路径或拖入文件，再明确点击“运行文件”。拖入、恢复布局和打开项目均不执行源码。

区域较小时可按 Ctrl+Space 最大化。输出与输入高度随区域大小变化，长文本各自滚动。
草稿和文件路径可随“保存布局”保存；变量、执行历史和输出不跨程序启动保存。
当前没有语法高亮、自动补全、块缩进或 Notebook；Shift+Tab / Ctrl+Tab 移动输入焦点。

`stk.projects.recent()` 返回最近 20 个项目的历史元数据与持久化警告，`stk.projects.forget(directory)`
仅移除列表项；`stk.projects.open(directory, expected_id=...)` 可防止误开已被替换的项目。
它们复用[最近项目列表](project.md)；历史不等同于当前打开的会话列表。

## 会话与项目

桌面桥的 `script.open` 创建一个共享会话，`script.execute` 显式执行多行源码或 UTF-8 文件。
同一个 worker 保留变量和导入；控制台源码最后一个表达式会显示结果并保存到 `_`，文件按普通脚本执行。
`stk` 是注入的 `suan.scripting.API`，不需要在脚本中另开数据库或连接桌面协议流。

```python
# 当前执行开始时选中的项目；切换焦点不会改变已经持有的 p。
p = stk.project
snapshot = p.snapshot()
result = p.apply(
    [{"op": "create_table", "name": "Temperature sweep"}],
    expected_revision=snapshot["project"]["revision"],
)
print(result["revision"])
```

`apply` 必须明确给出读取时的修订号。UI、CLI 或其他脚本修改了项目时，旧修订会得到 `conflict`；
不能只提高修订号后盲目重试。事务命令、类型和稳定 ID 见[项目指南](project.md)。
项目修改会发出与原生表格相同的 `project.changed` 通知，打开该项目的视图可以刷新。

```python
p = stk.projects.create("/absolute/path/to/new-project", "Simulation")
p = stk.projects.open("/absolute/path/to/existing-project")
print(stk.projects.list())
print(p.history())
# 显式备份只包含数据库，不包含外部资源：
print(p.backup())
# 旧项目需要时显式升级；升级前自动生成并校验备份：
# p.upgrade(expected_revision=p.snapshot()["project"]["revision"])
# p.close() 会关闭共享句柄，包括使用该句柄的原生项目视图。
```

`stk.projects.open/create` 返回数据会话，不自动切换可见的原生项目。
相对路径由 worker 根据当前工作目录解析；桥上的项目路径仍是绝对路径。
`script.open.directory` 指定 worker 的初始目录，默认为桥启动目录；运行文件不会自动切换到文件目录。
可以在自己的脚本中显式调用 `os.chdir()`。状态里的 `directory` 是初始目录，重置 worker 时恢复它。
文件执行设置 `__name__ = "__main__"`、`__file__`，并临时设置 `sys.argv = [文件路径]` 及文件目录的导入路径，
因此常见的 main guard 和同目录辅助模块可直接使用；执行后恢复 `sys.argv` / `sys.path`。

## 操作覆盖

`stk.operations()` 返回已开放的项目、连接、Runtime 操作参数/结果 schema 和 UI 操作名称；`stk.help()` 打印这份目录。
`stk.call("project.snapshot", handle=...)` 是命名参数形式的底层入口。
操作错误是 `suan.scripting.ScriptError`，可读取 `code`、`data`、`retryable`。

| 范围 | 当前状态 |
|---|---|
| 项目创建、打开、列表、关闭、快照、事务修改、历史、撤销/重做、数据库备份/升级 | 已实现，与桌面桥共用命令；包括引用与轻量公式 |
| 项目修改预览 | `stk.project.preview` 在内存副本计算候选结果；不保存修改，见[预览指南](project-preview.md) |
| CSV/TSV 表格导入与当前值导出 | `stk.project.csv` 共用类型校验、修订和撤销，见[CSV 交换](project-csv.md) |
| 文件索引登记、刷新、列表、路径检查 | `stk.project.files` 已实现；不复制、删除、打开或执行文件，见[文件指南](project-files.md) |
| 不可变输入副本、历史清单和 SHA-256 校验 | `stk.project.snapshots` 已实现，格式 4；显式复制选中文件，表格撤销不删除历史，见[输入快照](project-snapshots.md) |
| 参数行、输入版本、执行规格和远端任务关联 | `stk.project.runs` 已实现，格式 5；显式准备/提交/刷新/取消，见[运行记录](project-runs.md) |
| 布局读取/应用、编辑器列表、可见项目查询/打开/关闭 | 已接入原生 UI 主线程执行器，目标为第一个安装的主窗口 |
| 已保存连接查询/检查、管理 SSH 状态/连接/断开 | `stk.connections`；配置与凭据继续在 Jobs 或 CLI 管理 |
| Runtime/Hub 工作区、上传/下载、任务提交/查询/取消、产物、日志 | `stk.runtime(connection, node=...)` 与 `stk.transfers`；复用已有幂等和审核规则 |
| Viewer 打开/关闭、状态、预设参数、图层、求值、时间步/播放和相机重置 | `stk.viewer` 已接入共享原生状态，见[Viewer Python 指南](scripting-viewer.md) |
| 分析图目录、连接校验、求值/取消、blob 与原场探针 | `stk.graph` 已接入现有图服务，保留 Hub 审核和结果，见[分析图 Python 指南](scripting-graphs.md) |
| 相机完整变换、原生图编辑、完整项目打包与文档 | 统一操作与界面仍待逐步接入 |
| 自动补全、操作记录成脚本、脚本持久历史 | 待开发 |
| 远程机器 Python / UI 控制 | 未开放；本机 stdio 扩展不等于 P2P 或 SSH 服务 |

布局入口已随原生桌面绑定，可读取、修改并恢复：

```python
saved = stk.ui.layout()
print(stk.ui.editors())
# 先保存 saved，再把主窗口切成两个区域。
import copy
layout = copy.deepcopy(saved)
layout["screen"] = {
    "maximized": None,
    "root": {"factor": 1, "split": "horizontal", "children": [
        {"factor": 0.65, "area": {"id": "view", "type": "viewer"}},
        {"factor": 0.35, "area": {"id": "code", "type": "python"}},
    ]},
}
stk.ui.apply_layout(layout)
# 在新的 Python 区域中继续输入，变量 saved 仍在同一个会话中。
stk.ui.apply_layout(saved)
```

布局描述沿用 `stk.desktop.layout/1`，不包含自动执行的 Python 代码。
执行器必须在 UI 主线程校验并应用；非法布局保持原界面，窗口几何不由这一操作强制改变。

## 运行模拟与取得结果

先在 Jobs 或 CLI 保存 Runtime 连接。Python 使用连接 ID，不把 token 放进脚本或项目：

```python
print(stk.connections.list())
r = stk.runtime("runtime:lab")  # 换成自己的连接 ID；本机 Runtime 使用 "local"
print(stk.connections.check(r.connection))
# 对已经配置 ssh.host 的连接：
# stk.connections.ssh(r.connection, "connect")  # 或 "status" / "disconnect"
```

下面以输入文件 `input.json` 和远端已安装的程序为例。`source` / `dest` 相对当前 Python 工作目录；
远端路径使用工作区内 POSIX 相对路径。每个独立操作使用自己的幂等键，并在重试时复用该键及原请求：

```python
created = r.workspaces.create("Temperature scan", idempotency_key="scan-001:workspace")
w = created["workspace"]["id"]
upload = r.upload(w, "input.json", idempotency_key="scan-001:input")
uploaded = stk.transfers.wait(upload["id"], timeout=60)
assert uploaded["state"] == "completed", uploaded

submitted = r.tasks.submit({
    "workspace_id": w,
    "argv": ["/absolute/remote/path/to/solver", "input.json"],
    "outputs": ["result.csv"],
}, idempotency_key="scan-001:submit")
task_id = submitted["task"]["id"]
task = r.tasks.wait(task_id, timeout=300)
print(task["state"], r.tasks.artifacts(task_id))
if task["state"] == "succeeded":
    download = r.download("result.csv", task_id=task_id, dest="result.csv",
                          idempotency_key="scan-001:result")
    print(stk.transfers.wait(download["id"], timeout=60))
```

这是直接 Runtime 示例。Hub 使用 `stk.runtime("hub:lab", node="32位节点ID")`；
工作区创建、提交和取消返回完整 `{workspace/task?, action?}` 结果。如果只有 `action.state == "review"`，
应保留操作 ID，在 Jobs 中检查和审核；批准后用**相同键和请求**获取结果，不能直接读取不存在的 `task`。
`stk.call("hub.action", connection="hub:lab", action_id=...)` 可查询操作，字段以 `stk.help()` 为准。
目录还开放 `hub.devices/templates/actions`，未开放从 Python 自动批准审核。

常用读操作还有 `r.workspaces.list()/files(w)`、`r.tasks.list(workspace_id=w)/get(task_id)`。
`r.tasks.cancel(task_id, idempotency_key=...)` 显式请求取消；`stk.transfers.get/list/resume/cancel` 管理传输。
下载必须指定 `task_id` 或 `workspace_id` 中的一个；省略 `dest` 使用桥的下载缓存目录。

等待助手只轮询，遇到网络错误直接抛出，不发起额外的重连、恢复传输或取消请求。
底层读取仍遵守保存连接的 SSH 策略；显式断开的隧道不会被轮询重新打开。任务返回 `succeeded/failed/cancelled/unknown`；
传输在完成、失败、取消、中断或等待 Hub 审核时返回。调用者必须检查状态。超时抛出 `TimeoutError`，
已接受的任务/传输仍可继续；单次网络调用有其自身超时，等待总时间可能超过传入的轮询期限。
这些对象只绑定连接/节点 ID，不持有远端对象；重开桌面后可用保存的任务/传输 ID 再查询。
直接调用 `r.tasks.submit` 不自动写回项目；要持久关联冻结输入、参数和任务，使用 `stk.project.runs`，见[运行记录](project-runs.md)。

日志使用**字节偏移**，`data` 在 Python helper 中为 `bytes`。逐块拼接后解码，或使用增量解码器：

```python
chunk = r.tasks.logs(task_id, stream="stdout", offset=0, limit=65536)
print(chunk["data"].decode("utf-8", errors="replace"))  # 单块预览；完整读取应跨块解码
next_offset = chunk["next_offset"]
```

`limit` 为 1–1 MiB，默认 64 KiB；支持 stdout、stderr、scheduler.out、scheduler.err、wrapper。
`terminal` 表示任务已结束，仍可能有未读取的日志；继续读到空块才到达当次日志末尾。

## 输出、失败与中断

- Python `print`、异常堆栈进入最多 1 Mi 个 Unicode 字符的输出环；`script.read` 使用**字符偏移**，
  与 Runtime 日志的字节偏移不同。落后于环头会返回 `truncated=true` 和可用起点。
- 原生扩展的文件描述符输出、子进程输出进入 Bridge log；协议使用私有管道，不被这些输出占用。
- worker 中断或崩溃会丢失变量；下一次执行创建新 worker。`script.interrupt` 在空闲时也可用于重置。
  桥重启后整个 Python 会话失效，不重放源码。显式关闭会话也不会关闭项目或取消 Runtime 任务。
- 中断会停止脚本 worker 及其普通子进程。已经交给桥/UI 的操作可能已完成或仍在收尾，
  中断不回滚项目事务、不撤销已接受的 UI 修改，也不取消已提交任务/传输；必要时先查询状态，再决定下一步。
- `stk.graph.evaluate` 的本机求值随当前脚本中断取消；Hub 求值只停止等待，不发送远端取消。
  `stk.viewer.wait` 仍只停止轮询，详见[分析图中断边界](scripting-graphs.md)。
- `stk` 操作须从执行线程调用；后台 Python 线程可以打印，但不能调用项目/UI RPC。
- 单段源码最多 262144 个字符、UTF-8 最多 1 MiB；文件最多 1 MiB。暂不支持交互式 `input()`。

这是运行用户明确选择的代码的环境，具有当前用户权限，不是安全沙箱；打开项目不会自动运行脚本。
完整代码编辑继续使用外部编辑器，STK 只提供操作和查看所需的编程入口。
