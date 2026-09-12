# STK - Suan Toolkit

STK 为 MuPRO 等模拟计算提供输入准备、批量任务、数据处理与可视化。
桌面 `suan-gui`、命令行 `suan` 和 MCP 可以连接同一个持久 runtime；
支持本机进程、PBS 和 Slurm，客户端断线后后台任务继续。

```bash
python -m pip install '.[server,science]'  # 无 Qt 的服务器
# 或 python -m pip install '.[desktop]'  # 桌面 + 本地 runtime
suan server init
suan server start
suan server status
suan server doctor --science
```

完整安装、SSH 连接、任务接口、科学示例和验收方法见 [runtime 使用指南](docs/runtime.md)。
当前为 `0.1.0a1` 工程版本；真实集群须执行指南中的站点验收。

文件夹结构：

- suan：提供用户使用的界面，有cli，gui
- toolkits：提供具体功能的一些函数，有数据、可视化等，其中每个子文件夹是一个subpackage。
- suan/runtime：独立任务服务、进程／调度器适配器及统一客户端，不依赖 Qt。
- examples/runtime：确定性参数扫描与 PNG／VTK 结果验收示例。
- tests：任务生命周期、协议、文件传输和科学数据格式的回归测试。


## Blender 原生工作台

桌面开发主线为 **Synorder 的 Blender 原生宿主 + STK 科学插件**。通用窗口、控件、三维绘制、网页/PWA、配对和会话归 Synorder；STK 通过 `plugins/synorder` 的能力包、结构化操作和声明式视图定制工作台，Runtime 与科学处理继续独立维护。

安装、节点连接和旧任务收录见 [插件指南](plugins/synorder/README.md)，使用 `suan-workbench` 启动新桌面入口。旧 `blender/`、`suan-blender` 和 Qt 界面保留用于迁移回退与回归；此前 `native/` Rust/egui 原型暂停扩展。

## File format

- C/C++: clang-format
- fortran: fprettify
- python: black
- shell: shfmt
- js: prettier
