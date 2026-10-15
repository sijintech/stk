# 项目文件树与文件索引

## 独立文件树

原生“文件树”（编辑器 ID `files`）浏览当前项目的实际目录。每个编辑器实例保存自己的展开和选择，
不改变项目表格的共享选择。没有项目时，可直接进入打开/创建项目页面。

- 选中目录后点击“展开”，只列举这一层；“更多”读取该层下一页，“刷新”重新读取根目录并关闭旧展开。
  不会递归扫描、登记文件、读取文件内容、运行程序或调用模型。读取在 Python 桥执行，UI 线程不列目录。
- 树中标明已登记/未登记；已登记但当前目录内不存在的文件显示“缺失”，不填零大小。
  链接、Windows reparse point 和特殊文件可见但不跟随、不打开；目录路径不能经过链接。
- “已登记资源”另列最多 200 项保存的索引摘要，包括外部和缺失路径。这是**上次保存的观察**，
  不会因为浏览项目目录而自动探测外部位置。项目搜索可以定位未出现在这 200 条摘要中的资源，显示其详情。
- 明确点击“编辑 Python 程序”才交给程序编辑器载入 `.py`，不运行它；未保存程序由该编辑器保护。
  明确点击“在 Viewer 打开”才替换查看的数据，可选择预设；展开、选择或刷新保持已有 Viewer 数据。
  科学场文件、载荷或运行目录沿用 Viewer 支持的格式，预设与实际输入必须匹配；扩展名不能证明科学内容有效。
  文件树不是 LAMMPS 冻结运行的验收入口，原子/轨迹的收集清单与输入/日志校验仍由 LAMMPS 查看入口负责。

单页最多 200 项，每个目录最多检查 4096 个条目（包括被隐藏的条目）；超出时显示截断提示，不声称列出了全部文件。
每实例最多保留 64 个目录、8192 条目录项。隐藏名称、`.stk`、`.git`、`backups`、`__pycache__` 和项目数据库/事务文件不在物理树中展开。
目录分页不是不可变快照，磁盘变化后请刷新；打开前会重新核对当前项目句柄、修订、路径和文件种类，链接更换会被拒绝。
这些观察不锁定文件内容。需要固定文件的运行仍应使用输入快照和独立的来源校验。

Python 使用同一只读接口（要求项目格式至少为 3，不自动升级）：

```python
p = stk.project
revision = p.snapshot()["project"]["revision"]
page = p.files.children("inputs", expected_revision=revision, offset=0, limit=200)
# page: entries, next_offset, truncated，以及根目录返回的 registrations 摘要。
location = p.files.resolve_path("inputs/model.py", expected_revision=revision)
# 只返回当前绝对路径与 file/directory，不读程序、不运行、不登记。
```

桥方法为 `project.files.children` 和 `project.files.resolve_path`，接收相同参数并另带 `handle`。
相对路径采用 POSIX 分隔符；空路径表示项目根目录，拒绝绝对路径、`..`、控制字符和隐藏内部组件。
刷新/关闭项目或桥重启后，旧目录回复与旧打开动作会失效。目录不可访问时显示错误，不自动注册或修复。

## 普通表格文件索引

项目中的输入、输出、代码、Markdown、图片、视频与 PDF 可以登记到“文件表格”。文件内容仍保留为普通文件；
SQLite 保存位置和检查时观察到的信息。它复用现有字段、记录、稳定 ID、修订、引用和撤销机制，
索引本身不需要新的数据库格式；要求至少格式 3。
需要固定文件内容时，使用格式 4 的[输入快照](project-snapshots.md)，与此处的元数据索引分开操作。

## 在桌面使用

1. 打开“项目表格”，展开“项目文件”。每行填一个文件路径，或用“浏览…”多选文件（追加到已有路径后），点击“登记 / 更新文件”。
   相对路径以当前项目目录为起点；也可把一个或多个文件拖入已打开的项目区域登记。
   拖入项目目录或 `project.sqlite3` 仍表示打开项目。
2. 登记后自动选中文件表格和本批第一条记录。已有位置会更新同一条记录，保留其 UUID 和自定义名称。
3. “刷新选中文件”重新读取文件大小、修改时间和是否存在。没有后台监视或自动递归扫描。
4. “用默认程序打开”使用操作系统关联的程序；“在 VSCode 中编辑”使用已安装 VSCode 的 URL 处理程序。
   也可直接打开项目文件夹或在 VSCode 中打开项目。打开前重新核对项目修订、位置和文件是否存在。
5. “在查看器中打开”显示 `.stkp`、载荷清单或 STK 结果；科学场文件 `.dat`、`.npy`、`.vti`、`.vtk`、
   `.vtkhdf` 使用选定的体渲染、切片、等值面或矢量预设。打开前检查文件及修订，保留确切文件名；
   Viewer 隐藏时切换到对应标签，布局里没有 Viewer 时添加标签，不替换项目。
   实际数据读取/求值失败会在 Viewer 显示错误，扩展名不保证内容和数据形状适合该预设。
6. 删除文件表格中的记录只删除索引；撤销恢复索引信息，不会还原、删除或改写磁盘文件。

一次登记/刷新最多 100 个明确的文件。目录不会递归展开。尚未生成的输出路径可提前登记为 `missing`，
文件产生后再刷新。表格中的“当前存在”只是上次观察，不是文件锁或不可变快照。

当前默认 `volume` 预设会先计算字段模长 `|v|`，再进行体渲染；标量负值也会变成绝对值。
它不是自动识别物理含义的通用标量查看器。离线示例采用非负合成场，因此模长与原值一致；
需要保留正负号时，应使用明确选定标量字段的分析图直接连接 `stk.render.volume@1`。
保留符号的专用标量预设、明确字段/分量选择和相应界面标签仍需后续补充。

## 路径与元数据

| 字段 | 含义 |
|---|---|
| Name | 可编辑的显示名称，首次登记时取文件名 |
| Path | 项目内的相对路径，或外部文件的绝对路径 |
| Location | `project`、`external:posix` 或 `external:windows` |
| Kind | 根据扩展名分类为 code/document/image/video/data/file；不读取内容识别格式 |
| Size | 上次观察的字节数；缺失或无法检查时为空 |
| Modified (UTC) | 上次观察的文件修改时间 |
| State | present/missing/not_file/invalid_location/unavailable |
| Checked (UTC) | 元数据检查时间 |

项目内位置使用 POSIX 相对路径，移动整个项目目录后仍可解析。外部路径标记其操作系统路径语法；
把项目从 Windows 移到 macOS 后，Windows 外部文件不会被误当作项目内相对文件，应明确登记新的本机位置。
相对路径不能包含 `..` 或通过后来替换的符号链接跳出项目。首次登记符号链接时，明确记录它解析后的目标。
运行中的项目数据库及 SQLite 事务文件不能作为自己的资源登记。

表格/字段改名不影响索引身份。可以用普通单元格引用读取文件信息，也可编辑名称或文件位置。
删除固定字段或改成不兼容结构后，文件操作会提示撤销结构修改/恢复备份，不静默创建第二张表覆盖原信息。
其他自定义字段可继续添加。固定视图与字段 UUID 定义在 `suan/project/files.py`，不是依赖表格名称识别。

## Python 和 CLI

在桌面 Python 面板中：

```python
p = stk.project
revision = p.snapshot()["project"]["revision"]
added = p.files.index(["inputs/case.json", "notes.md", "results/future.vti"], expected_revision=revision)
print(p.files.list())
updated = p.files.refresh(added["record_ids"], expected_revision=added["revision"])
print(p.files.resolve(added["record_ids"][0], expected_revision=updated["revision"]))
```

普通 Python 使用 `ProjectStore(directory).files`，接口相同。`resolve` 只返回通过检查的绝对路径，
脚本调用不会自动启动外部程序。文件登记和刷新通过普通 `apply` 批次提交，来自不同入口的编辑共用撤销栈。
响应丢失时先查询修订/历史，不自动提高修订后重试。

```bash
suan project files index /absolute/project inputs/case.json notes.md --expected-revision 3
suan project files list /absolute/project
suan project files refresh /absolute/project RECORD_UUID --expected-revision 4
suan project files resolve /absolute/project RECORD_UUID --expected-revision 5
```

## 当前边界

文件索引操作本身不复制文件、计算内容哈希、递归整理目录或管理远程 Runtime 文件。
大小和修改时间不能证明内容未改变；执行模拟前可显式创建[输入快照](project-snapshots.md)来固定和校验内容。
数据库备份包含文件索引，不包含文件内容。撤销刷新只恢复旧观察，之后打开仍会重新检查实际路径。
Markdown/HTML/PDF 的应用内预览、LaTeX 编译和报告生成仍是后续能力。

外部程序启动使用系统机制：Linux `xdg-open`、macOS `open`、Windows
[ShellExecuteEx](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shellexecuteinfow)。
VSCode 按其[官方文件 URL 入口](https://code.visualstudio.com/docs/configure/command-line#_opening-vs-code-with-urls)
处理 UTF-8 和 URL 转义，不经过命令 shell。当前 VSCode 入口不接受 UNC 路径或包含额外冒号的文件名，
避免与 URL 的行号语法混淆。系统启动器接受请求不保证目标应用已经成功显示文件；未安装/未注册时需检查系统关联。
