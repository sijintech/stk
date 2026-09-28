# STK Python 编程

状态：2026-09-28 已实现原生 Python 面板、独立会话、项目操作 API 和本机布局控制首版。
完整方向见[设计记录](design/scripting-and-connections.md)，全部操作覆盖与远程控制仍在后续计划中。

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
文件执行设置 `__name__ = "__main__"`、`__file__`，并临时设置 `sys.argv = [文件路径]` 及文件目录的导入路径，
因此常见的 main guard 和同目录辅助模块可直接使用；执行后恢复 `sys.argv` / `sys.path`。

## 操作覆盖

`stk.operations()` 返回已开放的项目操作参数/结果 schema 和 UI 操作名称；`stk.help()` 打印这份目录。
`stk.call("project.snapshot", handle=...)` 是命名参数形式的底层入口。
操作错误是 `suan.scripting.ScriptError`，可读取 `code`、`data`、`retryable`。

| 范围 | 当前状态 |
|---|---|
| 项目创建、打开、列表、关闭、快照、事务修改、历史 | 已实现，与桌面桥共用命令 |
| 布局读取/应用、编辑器列表、可见项目查询/打开/关闭 | 已接入原生 UI 主线程执行器，目标为第一个安装的主窗口 |
| Jobs、传输、Viewer、图求值、资源与文档 | 现有各自接口仍可用；统一 `stk` facade 待逐步接入 |
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
