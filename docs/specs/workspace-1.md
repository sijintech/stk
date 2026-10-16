# `stk.workspace/1` 可移植工作空间

状态：第 1 版实现契约；桌面/CI 的实际验收结果见[运行验收记录](../runtime-validation.md)。
规范扩展名为 `.stkworkspace`。表格 CSV、Excel、JSON 交换有自己的接口，本容器保存完整桌面会话及其项目资源。

## 容器

使用普通 ZIP 或 ZIP64 文件成员。只允许未加密的 STORED、DEFLATED 成员；所有成员为普通文件。
容器没有可执行入口，不允许导入触发脚本、模型请求、图求值、Runtime 提交或重试。

```text
manifest.json
state.json
project/project.sqlite3             # 没有项目时整个 project/ 不存在
project/inputs/...
project/results/...
project/.stk/objects/sha256/...
project/.stk/analysis-runs/...
resources/<resource-id>/<basename>  # 文件，或显式目录资源的根
resources/<resource-id>/<basename>/...
```

`manifest.json` 为有限 UTF-8 JSON 对象，精确包含以下键：

```json
{
  "format": "stk.workspace/1",
  "created_at": "2026-10-15T00:00:00+00:00",
  "project": {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "Scientific workspace",
    "revision": 7,
    "format_version": 14,
    "source_root": "/old-machine/project"
  },
  "state": "state.json",
  "files": [
    {"path": "state.json", "size": 2, "sha256": "<64 lowercase hex characters>"},
    {"path": "project/project.sqlite3", "size": 4096, "sha256": "<64 lowercase hex characters>"}
  ],
  "directories": ["project/inputs/empty", "resources/viewer-1/viewer-payload"],
  "resources": [
    {
      "id": "viewer-1",
      "source": "/old-machine/viewer-payload",
      "path": "resources/viewer-1/viewer-payload",
      "kind": "directory"
    }
  ],
  "diagnostics": [],
  "complete": true
}
```

示例摘要为占位符，不是可导入包。`files` 按实际字节记录每个成员的大小和 SHA-256，
精确覆盖除 `manifest.json` 自身外的所有 ZIP 成员；无目录成员。
`directories` 为独立相对路径清单，包含项目和显式目录资源的目录，也保存空目录；
目录没有伪造的字节大小或摘要。导入按清单创建目录，路径校验与普通文件相同，不能与文件或其大小写变体冲突。
必须包含 `state.json`；有项目时必须包含 `project/project.sqlite3`。
`project` 可为 `null`，此时禁止出现 `project/` 成员。项目 UUID、名字、修订和格式与数据库一致。
包不自动升级项目格式，未知或未来数据库版本仍由 `ProjectStore` 拒绝。

`resources` 每项包含四个必需键 `id/source/path/kind`，仅可额外包含 `aliases`。ID 匹配 `[A-Za-z0-9][A-Za-z0-9_-]{0,95}`；
ID 不区分大小写必须唯一，同一规范化来源不能指向不同目标。`source` 为原机器的显式绝对路径。
`kind` 只有 `file`、`directory`。可选 `aliases` 为最多 128 个原机器/中间机器绝对来源；旧四键描述符仍有效。
项目元数据同样可额外携带 `aliases`（最多 128 个旧项目根），保留旧五键项目元数据兼容。`path` 固定为 `resources/<id>/<单个根文件名>`；
文件资源必须存在于清单，目录资源可为空。资源清单覆盖全部 `resources/` 文件。

## 桌面状态

`state.json` 为独立有限 JSON 对象。当前桌面根契约为：

```json
{
  "format": "stk.desktop.workspace-state",
  "version": 1,
  "windows": [],
  "app": {
    "project_selection": {"table_id": "", "record_id": ""},
    "viewer": {}
  }
}
```

每个 `windows` 元素是桌面窗口管理器的布局对象，包含全部编辑区域和所有标签。
编辑器调用 `save_workspace_state/load_workspace_state`；日常 `save_state/load_state` 仍保留其原来的布局语义。
每个桌面区域的状态必须明确 `workspace: true`，精确包含 `tabs/active/toolbar/sidebar/workspace` 五键；
每个标签精确包含 `type/state`。缺失标记、未知设置或非法标签会在替换任何窗口前拒绝，普通布局加载保持原兼容规则。
工作空间中可保存字段、筛选、表格视图、Viewer 相机、节点/工作流参数与未保存稿。
具体编辑器使用独立版本字段校验自己的参数。运行中请求、回调、弱引用、会话句柄与 RPC 缓存不属于状态。
分析与工作流草稿可携带 `baseline_json`：原数据库文档的有界、规范 JSON 字符串，保留历史绝对路径供修订和文档相等性门禁使用。
候选文档仍按普通 JSON 重定位；恢复不会据此改写历史数据库，也不会沿用原机器的打开句柄。旧草稿没有此字段时仍读取 `baseline`。
数据库基线比较忽略对象键顺序，同时保留值的类型差异（如 `1` 与 `1.0`）；UUID、修订与当前打开句柄的门禁仍独立成立。

分析编辑器另可携带 `analysis_run_id/run_plan_sha256`（结果列表当前选择）与独立的
`frozen_run_id/frozen_plan_sha256`（已固定显示的历史图）。两者可以指向不同的运行，均核对项目 UUID 与计划摘要。
恢复仅单次读取本地运行记录；`result_open=true` 时重新验证已收集的本地结果，不恢复自动跟踪，不准备、启动、恢复任务或替用户显示到 Viewer。
`result_browser_json` 是有界规范 JSON 字符串，只携带结果输出、带类型的 JSON 路径、页码、表格视图和选择/跳转稿，避免把科学对象键误当文件路径重定位。
可变分析定义已删除时保留编辑稿的分离状态并显示诊断，历史固定图可独立恢复；失败不会逐帧重新请求。

后端只负责有限 JSON、安全键和资源路径迁移，不将任意 JSON 当作可执行命令。
状态总大小最多 8 MiB，嵌套深度最多 64，节点值计数最多 150000，键长度最多 4096。
禁止 NaN、Infinity、NUL、重复 JSON 对象键和非 JSON 对象。
具体机器凭据/配置键如 `api_key`、`password`、`credentials`、`private_key`、`model_endpoint`、
`network_policy`、`runtime_config`、`env` 不可携带；普通 `key/token/endpoint` 科学参数不泛化禁止。

## 路径与完整性

状态中与项目根相等或位于项目根下的精确绝对字符串，转换为 `stk-project://<relative>`。
项目根本身为 `stk-project://`。与显式资源相等的字符串转换为 `stk-resource://<id>`；
目录资源内文件为 `stk-resource://<id>/<relative>`。精确匹配和已声明目录的最长前缀匹配优先。
URI 的相对段必须满足成员路径规则，且资源 ID 必须声明。
未知绝对字符串不触发文件读取，保留原样并产生 `unmapped_absolute_path` 诊断。
不会在普通字符串正文内寻找并替换路径子串。

`complete=false` 表示诊断中存在不能完整携带的资源；不得把此标志解释为摘要验证失败。
摘要、路径或容器非法直接报错。导入允许明确恢复不完整包，并返回原诊断；桌面默认阻止并要求用户明确选择恢复现有状态。
常见诊断包括：

| code | 含义 |
|---|---|
| `missing_resource` | 显式资源已不存在 |
| `nonregular_resource` | 资源为非普通文件/目录 |
| `excluded_private_resource` | 显式资源指向被排除的配置或凭据文件名 |
| `unmapped_absolute_path` | 状态含未知绝对字符串，未收集 |
| `missing_project_resource` | 状态中的项目文件引用未找到 |
| `external_not_included` | 项目 File 索引指向未明确列入包的外部文件 |
| `excluded_link` / `excluded_nonregular_file` | 目录内容包含链接、设备或其他不可移植对象 |
| `excluded_private_file` | 项目/显式目录包含被排除的配置或敏感文件名 |
| `excluded_internal_file` / `excluded_hidden_file` | 工作目录内部文件或隐藏缓存未打包 |

最后两个诊断本身不使包不完整。原项目文件索引和运行历史的绝对路径保持原样，
导入返回 `path_map`，并保存资源原始来源；使用这些历史来源的读取器须显式使用重定位解析器。
任何不能通过映射定位的来源仍为缺失，不根据旧路径自动搜索其他磁盘。

## 排除与预算

当前项目读取包括普通可见项目文件、`.stk/objects` 与 `.stk/analysis-runs`。
排除实时数据库的 WAL/SHM/journal 副本、`.stk/tmp` 及其他未允许内部目录、
Git、备份、依赖缓存、用户配置、SSH/云凭据目录、`.env*`、已知凭据文件名及私钥/证书存储后缀。
项目数据库通过 SQLite 在线备份携带；不复制用户主目录配置、Runtime 数据库或模型配置。
排除项给出诊断；输入显式资源不解除这些边界。

成员路径为相对 POSIX 路径，最多 4096 字符、64 段。拒绝绝对路径、反斜线、空段、`.`、`..`、冒号、
控制字符、尾部空格/点和 Windows 保留名。成员、路径前缀经 NFC 规范化和大小写折叠后必须唯一；
同一路径不能既是文件又是其他文件的父目录。拒绝软链接、reparse point、加密成员、重复成员和额外未列出的成员。
唯一源路径例外是 macOS 固定系统别名 `/var`、`/tmp`、`/etc`，且真实目标必须分别为 `/private/var`、`/private/tmp`、`/private/etc`。
这只规范化系统根前缀，项目和资源内部的链接仍拒绝；不会先解析任意用户链接再绕过敏感路径检查。
项目/资源包含关系与导出、导入、重开目标按同一可信物理前缀比较，避免根别名隐藏包位于自身项目/资源内的情况。
状态映射保留原根拼写；显式资源携带原来源与物理来源别名，同一物理资源的别名描述符合并为一个清单目标。

默认累计展开字节预算 **8 GiB**，可由调用者明确调高至 **1 TiB**；这不是自动申请磁盘配额。
清单最多 **16 MiB**，文件与目录合计最多 **20000**，显式资源最多 **1024**。
在 ZIP 解析前先限制中央目录规模，再按已声明文件大小、累计大小和实际解压数据验证，避免无界展开。

## Python 接口

```python
from suan.project.workspace_bundle import (
    export_workspace, preview_workspace, import_workspace, open_workspace,
)

exported = export_workspace(
    project_directory_or_none,
    "/exports/research.stkworkspace",
    state=captured_desktop_state,
    expected_revision=7,  # 无项目可省略
    resources=[{"id": "viewer-1", "path": "/explicit/viewer-payload"}],
)
preview = preview_workspace(exported["path"])
restored = import_workspace(
    exported["path"], "/new-machine/fresh-workspace",
    expected_sha256=preview["sha256"],
)
reopened = open_workspace("/new-machine/fresh-workspace")
```

三个归档接口都支持 `max_bytes`。导出/导入目标的父目录必须已存在，目标本身必须不存在。
导出目标不能位于被打包的项目或资源目录内。

公共结果包含 `format/project/diagnostics/complete`。
导出返回 `path/sha256/archive_bytes/file_count/total_bytes`；
预览返回 `path/sha256/state/resources/file_count/total_bytes`，其中状态仍使用可移植 URI；
导入返回 `directory/project_directory/workspace_path/sha256/state/path_map/file_count/total_bytes`，
其中 `project_directory` 可为空，状态中的已声明路径已转为新机器绝对位置。
`open_workspace` 返回导入结果中的状态与映射字段，不返回原包文件数和总字节数。

导入目录结构中 `workspace.json` 包含 `format/archive_sha256/project/state/resources/diagnostics/complete`，
保存 URI 状态与原始来源。导入后可改项目，重开只核对项目 UUID，不将后续合法修订回滚到导出时修订。
再次移动该目录后，`open_workspace` 按新的目录位置重新计算本地状态和 `path_map`。
再次导出已导入的项目时，后端读取已验证的本地描述符，按本次实际资源路径反向继承先前的 `source` 和 `aliases`；
同时继承旧项目根，避免二次/三次迁移丢失数据库中未改写的初始来源。
一个文件在新机器被再次登记时，新旧 FileIndex 路径可映射同一个包内对象，不改原记录 UUID 或历史。
同一来源别名映射两个不同目标直接拒绝；不会根据旧机器路径读取内容。
独立 Python `export_workspace` 的资源参数也允许可选 `aliases`；当前桌面 RPC 输入仍仅接受 `id/path`，别名自动内部继承。

## 发布与验证

导出在私有临时目录建立 SQLite 备份并生成包；核对项目修订和资源身份后无覆盖发布。
导入到私有临时目录，验证全部成员摘要、状态、数据库完整性和项目身份后，以平台原子无覆盖目录发布完成。
已有目标即使为空也不替换；失败不修改当前项目和原包。
预览/导入不更新主机端点、网络策略、凭据或计算模块，也不自动恢复运行中的任务。
桌面 bridge 单条结果上限为 16 MiB；后端状态与清单组合超过此传输上限时返回 `result_too_large`，不采用候选窗口状态。

本机后端、bridge 和重定位共 **112 项**，已包含在 Python 3.11、3.12、3.14 各 **238/238 通过**的相关验证中；原生和跨平台结果独立记录于
[验收记录](../runtime-validation.md)，不从 Python 后端测试推断桌面迁移验收完成。
