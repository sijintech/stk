# 桌面编辑模块与交互成本

2026-10-14。编辑器可组合、可单独构建；所有模块仍随一个原生应用发布。
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
| `table` | 独立表格页和可复用 `ProjectTableEditor`；传统项目页共用组件 |
| `files` | 独立真实目录页和 `ProjectFileTree` 异步控制器 |
| `python` | 程序文档、显式保存与运行，`src/editors/python_editor.cc` |
| `project` | 项目管理、复核、讨论与仿真 |
| `jobs` | Runtime、任务、日志和传输 |
| `workspace` / `skills` / `ai` | 工作台、技能目录、AI 对话 |

这些是 CMake 对象库，允许逐模块修改和编译；还不是运行时加载的二进制插件 ABI。
模块间的共享服务留在 `stk_app`：项目 UUID/修订/选择/撤销、Viewer 状态、Python worker、运行与来源记录。
Python 服务仍在 `suan/`，目录列举和程序文件读写经同一桌面桥完成。UI 每帧不遍历目录，
各编辑器不另建数据库、调度器或模型客户端。通用单元格点击能力位于 `stk_ui`，区域交换位于 `stk_wm`。

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
| 传统单 Viewer 布局，从文件菜单进入 Python | 保留菜单兼容，并提供顶部 1 次入口 |

`WorkbenchModules` 测试发送真实鼠标事件，核对任务终态和 Viewer/编辑器实例、来源与状态；
`workbench_modules_*_render_*` 用真实后台服务和合成科研数据捕获中英文宽窄组合工作区。
各次交付必须在[验收记录](runtime-validation.md)写实际次数、起点、未覆盖项与截图，新增功能先检查是否增加额外导航。
这不是线上行为采集，也不是点击次数越少越好：覆盖、运行和发送等明确操作的确认语义继续保留。

## 数据与草稿约束

- 独立表格复用五种字段、UUID 引用、公式、单位和撤销；点击单元格可选择字段并查看 JSON 详情。
  富对象缩略图、结构/结果专用单元格、批量粘贴和完整单元格内编辑仍需后续版本化类型契约。
- 目录树按需列一层，真实磁盘观察与已登记资源分开；展开、选择、刷新不运行代码或注册文件。
- Python 代码是主区域，输出可展开/收起；载入/保存不执行，运行缓冲区与运行保存文件有明确来源。
  UTF-8 `.py` 上限 256 KiB，SHA 版本冲突保留草稿；乐观并发不能锁住其它编辑器。
- 左右交换移动现存区域，保留相机、时间步和草稿。会销毁实例的关闭/替换/重置若有代码、单元格、分析节点或流程草稿，或有活动文本输入，则拒绝，
  用户需在原编辑器保存或放弃；后台重连可恢复同一项目而不丢草稿。普通导航不会最大化 Viewer。
