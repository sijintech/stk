# STK - Suan Toolkit

STK 为 MuPRO 等模拟计算提供输入准备、批量任务、数据处理与可视化，独立于 Synorder 发展。
桌面程序 `stk-desktop`、命令行 `suan`、MCP、Blender 工作台 `suan-workbench`（经控制服务与节点代理）和旧 Qt `suan-gui` 连接同一个持久 runtime；
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

文件夹结构：

- suan：提供用户使用的界面，有cli，gui
- toolkits：提供具体功能的一些函数，有数据、可视化等，其中每个子文件夹是一个subpackage。
- suan/runtime：独立任务服务、进程／调度器适配器及统一客户端，不依赖 Qt。
- suan/control：跨设备控制服务 `suan-control` 与执行节点代理 `suan-node`。
- suan/blender_client：Blender 工作台启动器与网络桥接。
- suan/visualization：执行节点上的场数据视图与原始数据探针。
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
- blender：STK Blender 原生工作台源码定制（D1 结束时归档）。
- web：控制服务提供的网页／手机 PWA。
- deploy/systemd：Linux 用户服务模板。
- docs：runtime、MuPRO、可视化、控制服务、桌面程序与站点验收文档。
- docs/specs：数据格式、节点图、渲染数据包、监控事件与畴分类的英文规范，附节点目录与示例。
- plugins/synorder：Synorder 插件（暂缓，可选集成）。
- examples/runtime：确定性参数扫描与 PNG／VTK 结果验收示例。
- tests：任务生命周期、协议、文件传输和科学数据格式的回归测试。


## Blender 原生工作台

此前的桌面主线为 **STK 自有的 Blender 原生工作台**（将由下文的桌面程序取代，D1 结束时归档）：`blender/` 定制版 + `suan/blender_client` + `suan-control` + `suan-node` + STK Runtime，不依赖 Synorder 工作台。

构建、服务启动、配对和计算闭环见 [工作台指南](blender/README.md)，使用 `suan-workbench`（兼容名 `suan-blender`）启动。`plugins/synorder` 与 `suan-synorder-node` 暂缓，作为可选集成保留，见 [插件指南](plugins/synorder/README.md)。Qt 界面保留为旧客户端。早期 `native/` Rust/egui 原型已归档（标签 `archive/native-egui-2026-09`）。

## 桌面程序 `stk-desktop`

STK 自有的 C++ 桌面程序（`desktop/`，GPL-2.0-or-later）复用 Blender 的 GHOST、GPU 与 BLF 模块，经 Python 桥
（`suan.desktop_bridge`，MIT）连接本机 Runtime、`suan connect` 连接与控制服务。桌面里程碑 D1 已完成：任务页
（上传、提交、日志、取消、校验下载）与查看器、属性、探针（节点图预设在数据旁求值、GPU 显示、拾取原始值、
PNG／序列导出）在 Linux（X11、Wayland；OpenGL、Vulkan）上通过真实验收，macOS（Metal）在 CI 中构建并做无界面
测试，Windows 在 CI 中编译并运行 CPU 测试。CI 生成 Linux 可重定位压缩包与 macOS `STK.app`（未签名）；程序包
不含 Python，需在虚拟环境中安装 STK 并用 `STK_PYTHON` 指定。安装、连接、使用、快捷键与故障排查见
[桌面程序指南](docs/desktop.md)，验收见 [验收记录](docs/runtime-validation.md)，开发与打包见
[`desktop/README.md`](desktop/README.md)。

桌面程序将取代 `blender/` 定制版（D1 结束时归档）、PyQt 界面与 SimViz（M-D2 结束时归档），归档计划见
[桌面程序指南](docs/desktop.md#旧界面与归档计划)。

## File format

- C/C++: clang-format
- fortran: fprettify
- python: black
- shell: shfmt
- js: prettier
