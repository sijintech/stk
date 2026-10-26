# 桌面编辑模块与交互成本

2026-10-15。编辑器可组合、可单独构建；所有模块仍随一个原生应用发布。
当前交付结果及剩余限制以[验收记录](runtime-validation.md)为准。

## 模块边界

统一入口是 `EditorType` 注册与 `Editor` / `EditorContext` 协议：页头、工具栏、侧栏、主体、GPU 绘制、
导航、布局状态与未保存草稿检查。每个标签持有独立编辑器实例；窗口和标签切换复用实例。
`AppShell` 负责导航、默认布局与跨窗口保护，`EditorArea` 负责标签及分栏。

构建清单是 `desktop/engine/lib/stk_app/editor_modules.cmake`。可分别构建，例如：

```bash
cmake --build build --target stk_editor_table
cmake --build build --target stk_editor_files
cmake --build build --target stk_editor_python
cmake --build build --target stk_editor_analysis
```

| 目标后缀 | 职责 / 主要入口 |
|---|---|
| `viewer` | 三维查看与属性/探针，`src/editors/viewer_*.cc` |
| `analysis` | 分析节点画布、参数、编辑与运行检查，`src/editors/analysis_graph_editor.cc` |
| `workflow` | 项目级工作流，`src/editors/workflow_editor.cc` |
| `table` | `TableWorkbench` 多维表格、独立只读控制器和可复用定义编辑器；传统项目页继续共用 `ProjectTableEditor` |
| `files` | 独立真实目录页和 `ProjectFileTree` 异步控制器 |
| `python` | 程序文档、显式保存与运行，`src/editors/python_editor.cc` |
| `reports` | 冻结报告清单、创建、显式资产读取和导出，`src/editors/reports_editor.cc`；独立文档视口经 `ReportDocumentHost` 承载，原生候选默认关闭 |
| `project` | 项目管理、复核、讨论与仿真 |
| `jobs` | Runtime、任务、日志和传输 |
| `workspace` / `skills` / `ai` | 工作台、技能目录、AI 对话 |

这些是 CMake 对象库，允许逐模块修改和编译；还不是运行时加载的二进制插件 ABI。
模块间的共享服务留在 `stk_app`：项目 UUID/修订/选择/撤销、Viewer 状态、Python worker、运行与来源记录。
`Editor::save_workspace_state/load_workspace_state` 为各模块独立定义可移植参数；`EditorArea` 捕获全部标签，
`AppShell` 校验并恢复整组窗口，`WorkspaceTransfer` 负责显式预览与传输交互。普通布局保存继续使用原有 hooks。
`Editor::workspace_resource_paths` 让各模块声明已明确打开的本地输入文件；Python 页声明已打开的 `.py`，
未打开的路径输入、保存目标和目录浏览根不自动变成递归打包资源。
表格文件解析在 `suan/project/table_io.py`，工作空间容器和路径重定位在 `workspace_bundle.py` / `workspace_paths.py`；
格式和边界见[表格交换](project-table-io.md)与[工作空间](design/portable-workspaces.md)。
Python 服务仍在 `suan/`，目录列举和程序文件读写经同一桌面桥完成。UI 每帧不遍历目录，
各编辑器不另建数据库、调度器或模型客户端。通用单元格点击能力位于 `stk_ui`，区域交换位于 `stk_wm`。

文档的纯 CPU 内存资源协议与可选原生适配位于 `desktop/engine/lib/stk_document/`，
目标分别为 `stk_document_resources` 和 `stk_document_native`；平台实现不在原型和产品间复制。
`stk_ui` 的 `NativeViewport` 只提供最终布局及裁剪，既不绘制浏览器像素，也不接管其输入。
`ReportDocumentHost` 绑定标签所有者、项目范围与父窗口；`Area::on_removed` 经 `EditorArea` 同步通知全部标签，
跨区域移走或移除前撤销资源。项目／桥身份变更另由 `AppStore` 的同步失效订阅通知，不能等下一帧发现。

按工作模式保存布局由 `work_mode_layouts.cc` 管理：准备／分析各自保存几何与标签、面板偏好，
`Screen::rearrange` 只重排完整的活区域集合，不调用编辑器工厂或载入草稿。标签用实例寿命身份跟踪，
跨窗口互不切换；区域集合变化时保留现有树。普通布局和完整工作空间都保存模式偏好，旧文件无需迁移。

上述目标检查各模块编译；运行修改后的应用前再构建 `stk-desktop`，完成最终链接。
原生桌面包仍不内置 Python；本轮新增桥接口需要配套安装同版 Python 包。

## 少点击是核心验收指标

计数从固定的初始布局开始，只计完成指定任务的鼠标点击；打开菜单和选择菜单项分别计一次。
键盘输入、数据加载耗时和明确运行/保存另外说明，不把它们伪装成零成本。
默认空工作区可见不等于已经有数据：需要项目/文件的动作仍由用户明确选择。

| 任务与起点 | 目标 |
|---|---|
| 全新默认布局，看到 Viewer、分析节点、表格与文件树 | 0 次导航点击 |
| 默认布局，进入 Python 程序页并保留 Viewer | 1 次 |
| Python 页切回节点页 | 1 次 |
| 默认布局中交换 Viewer 与节点/代码左右位置 | 1 次 |
| 默认布局，进入准备与运行布局；随后返回结果分析布局 | 每种模式 2 次，保留 Viewer 与隐藏草稿 |
| 传统单 Viewer 布局，从文件菜单进入 Python | 保留菜单兼容，并提供顶部 1 次入口 |

`WorkbenchModules` 测试发送真实鼠标事件，核对任务终态和 Viewer/编辑器实例、来源与状态；
`workbench_modules_*_render_*` 用真实后台服务和合成科研数据捕获中英文宽窄组合工作区。
各次交付必须在[验收记录](runtime-validation.md)写实际次数、起点、未覆盖项与截图，新增功能先检查是否增加额外导航。
这不是线上行为采集，也不是点击次数越少越好：覆盖、运行和发送等明确操作的确认语义继续保留。

## 数据与草稿约束

- 独立表格已有十种字段、UUID 引用、公式、单位和撤销，内联编辑/矩形粘贴/已存视图沿同一项目服务；
  新强类型、选项和命名视图使用显式格式 14，旧 13 不自动升级。
  对象候选和来源查看不执行任务；已有附件缩略图、填充柄和看板拖动，云端协作仍待实现，
  具体能力与限制见[多维表格](design/multidimensional-tables.md)。
- 目录树按需列一层，真实磁盘观察与已登记资源分开；展开、选择、刷新不运行代码或注册文件。
- Python 代码是主区域，输出可展开/收起；载入/保存不执行，运行缓冲区与运行保存文件有明确来源。
  UTF-8 `.py` 上限 256 KiB，SHA 版本冲突保留草稿；乐观并发不能锁住其它编辑器。
- 左右交换移动现存区域，保留相机、时间步和草稿。会销毁实例的关闭/替换/重置若有代码、单元格、分析节点或流程草稿，或有活动文本输入，则拒绝，
  用户需在原编辑器保存或放弃；后台重连可恢复同一项目而不丢草稿。普通导航不会最大化 Viewer。
