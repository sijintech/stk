# STK - Suan Toolkit

接手开发先读 [handoff.md](handoff.md) 与 [AGENTS.md](AGENTS.md)；Claude 的工作入口见 [CLAUDE.md](CLAUDE.md)。

**第一次使用**：按 [Linux 快速上手](docs/quickstart-linux.md) 安装，在工作台点击“创建示例项目”，用合成数据看一遍
参数扫描 → 结果 → 分析 → 三维显示；不需要服务器。终端/Jupyter 中可用 `suan demo` 与 `python -m suan.scripting.headless`。

STK 为 MuPRO 等模拟计算提供输入准备、批量任务、数据处理与可视化，独立于 Synorder 发展。
桌面程序 `stk-desktop`（直连 Runtime，或经控制服务与节点代理）、命令行 `suan`、MCP、网页和旧 Qt `suan-gui` 连接同一个持久 runtime；
支持本机进程、PBS 和 Slurm，客户端断线后后台任务继续。MuPRO 作业的排队、提交、取消与恢复由 STK Runtime 负责。
服务器端（Runtime、`suan-control`、`suan-node`）仅支持 Linux；Windows / macOS 仅作客户端。

```bash
python -m pip install '.[server,science]'  # Linux 服务器（控制服务另加 control,visualization）
# 客户端：python -m pip install .   旧 Qt 桌面：python -m pip install '.[desktop]'
suan server init
suan server start
suan server status
suan server doctor --science
```

`suan server` 只在 Linux 运行；其他系统上的客户端通过 SSH 隧道和 `suan connect` 使用 Linux runtime。
完整安装、SSH 连接、任务接口、科学示例和验收方法见 [runtime 使用指南](docs/runtime.md)。
当前为 `0.1.0a1` 工程版本；真实集群须执行指南中的站点验收。
首个真实站点为并行云（Paratera），见 [并行云站点验收清单](docs/runtime-paratera.md)，尚未开始。

MuPRO（muFerro）作业由 Runtime 排队；Runtime 服务环境需先配置 SDK、Intel MPI 环境与许可目录，见 [MuPRO 指南](docs/runtime-mupro.md)：

```bash
suan mupro submit --workspace WORKSPACE_ID --input ./case16 --ranks 1 --wait
suan mupro result TASK_ID
```

里程碑 1 的可视化以节点图 `stk.graph/1` 描述：图送到数据旁求值并缓存，返回渲染数据包 `stk.payload/2`、
PNG、二维图与表格，网页“图谱”模式、离屏渲染和 LLM 工具共用同一套契约：

```bash
python -m pip install '.[visualization,science]'
suan graph run muferro-domains --bind run=/path/to/case --out ./domains --param step=all
```

用法、预设与限制见 [可视化指南](docs/visualization.md)；控制服务的图谱计算、结果 blob 与反向代理设置见
[控制服务指南](docs/hub.md)；运行中任务的监控事件见 [runtime 使用指南](docs/runtime.md#监控事件)；
英文契约与 JSON Schema 见 [规范索引](docs/specs/README.md)。

文件夹结构（职责与归档依据见[仓库结构说明](docs/repository-structure.md)）：

- suan：共享 Python 服务、科学数据处理与 CLI/MCP/桌面桥入口；原生界面在 desktop。
- toolkits：仍被 CLI、可视化和测试使用的 Python 科学工具；后续按职责整合进 suan，保留过渡兼容。旧 C/C++ 工程已移入 archive。
- suan/runtime：独立任务服务、进程／调度器适配器及统一客户端，不依赖 Qt。
- suan/project：SQLite 项目存储、类型化表格、原子修订命令和输入快照，已接入原生项目表格，见[项目存储指南](docs/project.md)。
- suan/scripting：原生 Python 面板的项目、Runtime 与布局控制 API，见[Python 指南](docs/scripting.md)。
- suan/control：跨设备控制服务 `suan-control` 与执行节点代理 `suan-node`。
- suan/visualization：执行节点上的场数据视图与原始数据探针。
- suan/desktop_bridge：桌面程序的 Python 桥（NDJSON，连接 Runtime 与控制服务）。
- suan/mupro：STK 自有的 MuPRO 提交、计算节点启动与逐次结果校验。
- suan/contracts：JSON Schema 契约与物理量词表，只用标准库加载。
- suan/data：统一数据模型、快速 DAT 读取、VTKHDF（STK 附加信息）、结果清单与 VTK 转换、过滤算法。
- suan/analysis：净室实现的畴取向分类、薄膜检测、标签统计与调色板（仅依赖 NumPy）。
- suan/connectors：连接器接口与注册、本机／Runtime 文件源、内置 VTK/NumPy/表格读取与 muFerro 连接器。
- suan/graph：节点图的校验、节点目录、求值器、缓存、绑定解析、预设与 `suan graph` 命令。
- suan/render：渲染数据包 v2、scene v1 降级、颜色表与子进程离屏渲染。
- suan/plot：二维图规格 `stk.plot/1` 与 matplotlib 渲染。
- suan/monitor：监控事件的写入、读取与原生输出跟踪（标准库）。
- suan/skills：供 LLM 使用的技能说明（`suan skills export`）。
- desktop：STK 桌面程序 `stk-desktop`（C++，GPL），见 [桌面程序指南](docs/desktop.md)。
- web：控制服务提供的网页／手机 PWA。
- deploy/systemd：Linux 用户服务模板。
- docs：runtime、MuPRO、可视化、控制服务、桌面程序与站点验收文档。
- docs/specs：数据格式、节点图、渲染数据包、监控事件与畴分类的英文规范，附节点目录与示例。
- plugins/synorder：Synorder 插件（暂缓，可选集成）。
- examples/runtime：确定性参数扫描与 PNG／VTK 结果验收示例。
- [examples/project_scan](examples/project_scan/README.md)：原生 Python 面板准备参数表/输入快照，运行面板明确提交，下载 VTK/图片并汇总到结果表。
- [examples/project_analysis](examples/project_analysis/README.md)：无需服务器的合成 CSV 验收，明确冻结输入、运行保存分析并检查归档科学表格，保留当前项目与 Viewer。
- tests：任务生命周期、协议、文件传输和科学数据格式的回归测试。
- archive：退出当前构建的历史 C/C++ 工具、实验与旧打包文件，见[归档索引](archive/README.md)。


## 桌面程序 `stk-desktop`

桌面主线是 STK 自有的 C++ 桌面程序（`desktop/`，GPL-2.0-or-later），复用 Blender 的 GHOST、GPU 与 BLF 模块，经 Python 桥
（`suan.desktop_bridge`，MIT）连接本机 Runtime、`suan connect` 连接与控制服务。桌面里程碑 D1 已完成：任务页
（上传、提交、日志、取消、校验下载）与查看器、属性、探针（节点图预设在数据旁求值、GPU 显示、拾取原始值、
PNG／序列导出）在 Linux（X11、Wayland；OpenGL、Vulkan）上通过真实验收，macOS（Metal）在 CI 中构建并做无界面
测试，Windows 在 CI 中编译并运行 CPU 测试。CI 生成 Linux 可重定位压缩包与 macOS `STK.app`（ad-hoc 临时签名，未公证）；程序包
不含 Python，需在虚拟环境中安装 STK 并用 `STK_PYTHON` 指定。安装、连接、使用、快捷键与故障排查见
[桌面程序指南](docs/desktop.md)，验收见 [验收记录](docs/runtime-validation.md)，开发与打包见
[`desktop/README.md`](desktop/README.md)。

后续方向与阶段验收见[开发计划](docs/development-plan.md)：AI 助手、分层节点编辑器和通用多维表格
共用 SQLite 项目模型。产品约定见[项目工作台设计](docs/design/project-workbench.md)，
技术提案见[项目数据模型](docs/design/project-model.md)；已交付基础与后续目标以开发计划中的状态为准。
用户已反馈 macOS / Windows 均能打开窗口并看到 3D 渲染，范围见[补充验收记录](docs/runtime-validation.md#desktop-mac-windows-smoke)。
现在可从“文件 → 项目表格 / Python”使用项目编辑与脚本面板；源码更新后重跑[启动脚本](desktop/QUICKSTART.md)
进行增量编译。Python 面板支持多行运行、中断、文件执行以及项目/Runtime/布局 API；其他功能的统一脚本覆盖仍在推进。
项目文件可登记、跳转 VSCode，并显式保存和校验[不可变输入副本](docs/project-snapshots.md)。
项目编辑器的[讨论页](docs/project-contexts.md)可保存选定数据的上下文、文字消息及修改草案来源；
原生 AI 助手已接入明确准备/发送、流式文字回复，以及捕获范围内的[模型参数建议](docs/project-parameter-edits.md)。
建议须另行保存、预览并明确应用；保存和恢复讨论不会执行代码或提交计算，通用 AI 工具执行仍待开发。
分析图可保存定义、精确编辑参数与请求输出，并通过[本机分析运行](docs/project-analysis-runs.md)冻结输入、明确执行和校验归档。
历史图独立保留，内联科学表格可分页或按源坐标定位，查看类型、单位和精确值；保存分析可明确替换单输入连线并经校验后保存；增删节点、多输入编辑与大表 blob 读取仍待开发。
macOS / Windows 可从 Python 面板运行[离线分析验收](examples/project_analysis/README.md)，创建新的合成数据项目完成这一流程。

远程计算经控制服务：所有者用 `suan-control pair --role client --profile desktop` 签发配对码，在桌面程序
“配对控制服务…”中输入；见 [控制服务指南](docs/hub.md)。

## 已归档与旧界面

- **Blender 原生工作台**（`blender/` SPACE_STK 定制版、`suan/blender_client`、`suan-workbench`／`suan-blender`）
  已在 D1 结束时由桌面程序取代并移出主线，源码保留在标签 `archive/blender-workbench-2026-09`。scene v1 校验
  `validate_scene` 移入 `suan/render/v1.py`，节点代理的 `view.build` 与网页查看器照常使用 scene v1。
- 早期 `native/` Rust/egui 原型已归档（标签 `archive/native-egui-2026-09`）。
- PyQt 界面 `suan-gui` 与 SimViz 保留为旧客户端，M-D2 结束时归档；归档计划见
  [桌面程序指南](docs/desktop.md#旧界面与归档计划)。
- `plugins/synorder` 与 `suan-synorder-node` 暂缓，作为可选集成保留，见 [插件指南](plugins/synorder/README.md)。

## File format

- C/C++: clang-format
- fortran: fprettify
- python: black
- shell: shfmt
- js: prettier
