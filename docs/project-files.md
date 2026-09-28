# 项目文件索引

项目中的输入、输出、代码、Markdown、图片、视频与 PDF 可以登记到“文件表格”。文件内容仍保留为普通文件；
SQLite 保存位置和检查时观察到的信息。它复用现有字段、记录、稳定 ID、修订、引用和撤销机制，
不需要新的数据库格式；需要先将旧项目显式升级到格式 3。

## 在桌面使用

1. 打开“项目表格”，展开“项目文件”。每行填一个文件路径，点击“登记 / 更新文件”。
   相对路径以当前项目目录为起点；也可把一个或多个文件拖入已打开的项目区域登记。
   拖入项目目录或 `project.sqlite3` 仍表示打开项目。
2. 登记后自动选中文件表格和本批第一条记录。已有位置会更新同一条记录，保留其 UUID 和自定义名称。
3. “刷新选中文件”重新读取文件大小、修改时间和是否存在。没有后台监视或自动递归扫描。
4. “用默认程序打开”使用操作系统关联的程序；“在 VSCode 中编辑”使用已安装 VSCode 的 URL 处理程序。
   也可直接打开项目文件夹或在 VSCode 中打开项目。打开前重新核对项目修订、位置和文件是否存在。
5. 删除文件表格中的记录只删除索引；撤销恢复索引信息，不会还原、删除或改写磁盘文件。

一次登记/刷新最多 100 个明确的文件。目录不会递归展开。尚未生成的输出路径可提前登记为 `missing`，
文件产生后再刷新。表格中的“当前存在”只是上次观察，不是文件锁或不可变快照。

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

这里没有复制文件、计算内容哈希、制作不可变输入快照、递归整理目录或管理远程 Runtime 文件。
大小和修改时间不能证明内容未改变；执行模拟前仍需建立可核验的输入版本。
数据库备份包含文件索引，不包含文件内容。撤销刷新只恢复旧观察，之后打开仍会重新检查实际路径。
Markdown/HTML/PDF 的应用内预览、LaTeX 编译和报告生成仍是后续能力。

外部程序启动使用系统机制：Linux `xdg-open`、macOS `open`、Windows
[ShellExecuteEx](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shellexecuteinfow)。
VSCode 按其[官方文件 URL 入口](https://code.visualstudio.com/docs/configure/command-line#_opening-vs-code-with-urls)
处理 UTF-8 和 URL 转义，不经过命令 shell。当前 VSCode 入口不接受 UNC 路径或包含额外冒号的文件名，
避免与 URL 的行号语法混淆。系统启动器接受请求不保证目标应用已经成功显示文件；未安装/未注册时需检查系统关联。
