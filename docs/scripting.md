# STK Python 编程

状态：2026-09-28 已实现独立 Python 会话后端、项目操作 API 和本机桌面反向请求契约。
原生控制台与 UI 执行器正在接入；这一版不能仅凭以下布局示例就在现有窗口中执行。
完整方向见[设计记录](design/scripting-and-connections.md)。

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
# p.close() 会关闭共享句柄，包括使用该句柄的原生项目视图。
```

`stk.projects.open/create` 返回数据会话，不自动切换可见的原生项目。
相对路径由 worker 根据当前工作目录解析；桥上的项目路径仍是绝对路径。
`script.open.directory` 指定 worker 的初始目录，默认为桥启动目录；运行文件不会自动切换到文件目录。
可以在自己的脚本中显式调用 `os.chdir()`。状态里的 `directory` 是初始目录，重置 worker 时恢复它。

## 操作覆盖

`stk.operations()` 返回已开放的项目操作参数/结果 schema 和 UI 操作名称；`stk.help()` 打印这份目录。
`stk.call("project.snapshot", handle=...)` 是命名参数形式的底层入口。
操作错误是 `suan.scripting.ScriptError`，可读取 `code`、`data`、`retryable`。

| 范围 | 当前状态 |
|---|---|
| 项目创建、打开、列表、关闭、快照、事务修改、历史 | 已实现，与桌面桥共用命令 |
| 布局读取/应用、编辑器列表、可见项目查询/打开/关闭 | Python facade 与反向请求已实现；需要原生 UI 执行器接入 |
| Jobs、传输、Viewer、图求值、资源与文档 | 现有各自接口仍可用；统一 `stk` facade 待逐步接入 |
| 自动补全、操作记录成脚本、脚本持久历史 | 待开发 |
| 远程机器 Python / UI 控制 | 未开放；本机 stdio 扩展不等于 P2P 或 SSH 服务 |

布局入口在绑定桌面执行器后使用：

```python
saved = stk.ui.layout()
print(stk.ui.editors())
# 修改 saved 的 screen 树后，整体校验再应用；区域 ID 与项目 ID 分开。
stk.ui.apply_layout(saved)
```

布局描述沿用 `stk.desktop.layout/1`，不包含自动执行的 Python 代码。
执行器必须在 UI 主线程校验并应用；非法布局保持原界面，窗口几何不由这一操作强制改变。

## 输出、失败与中断

- Python `print`、异常堆栈进入最多 1 Mi 个 Unicode 字符的输出环；`script.read` 使用**字符偏移**，
  与 Runtime 日志的字节偏移不同。落后于环头会返回 `truncated=true` 和可用起点。
- 原生扩展的文件描述符输出、子进程输出进入 Bridge log；协议使用私有管道，不被这些输出占用。
- worker 中断或崩溃会丢失变量；下一次执行创建新 worker。`script.interrupt` 在空闲时也可用于重置。
  桥重启后整个 Python 会话失效，不重放源码。显式关闭会话也不会关闭项目或取消 Runtime 任务。
- 中断会停止脚本 worker 及其普通子进程。已经交给桥/UI 的操作可能已完成或仍在收尾，
  中断不回滚项目事务，也不撤销已接受的 UI 修改；必要时先检查快照/历史，再决定下一步。
- `stk` 操作须从执行线程调用；后台 Python 线程可以打印，但不能调用项目/UI RPC。
- 单段源码最多 262144 个字符、UTF-8 最多 1 MiB；文件最多 1 MiB。暂不支持交互式 `input()`。

这是运行用户明确选择的代码的环境，具有当前用户权限，不是安全沙箱；打开项目不会自动运行脚本。
完整代码编辑继续使用外部编辑器，STK 只提供操作和查看所需的编程入口。
