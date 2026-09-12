# STK 0.1.0a1 验收记录

日期：2026-09-09。状态：工程预发布，尚未完成真实集群和独立桌面安装器验收。

## 初始工程版本验收

在 Linux / Python 3.12.13 中构建 wheel 与 sdist。新建独立虚拟环境，先只安装
核心 wheel；确认没有 PySide6 和 NumPy，实际启动独立 API / supervisor，完成
任务提交、执行、日志读取和 SHA-256 校验下载。

随后在该环境安装最终 wheel 的 science、desktop、mcp、test 可选组件，将测试与
科学示例复制到源码目录以外执行。确认导入路径来自新环境的 `site-packages`，
而非可编辑源码安装。

结果：**44 passed**（19.83 秒）；`pip check` 通过，`git diff --check` 通过。
唯一警告来自已有 pyqode 使用已弃用的 `sre_constants`。

桌面采用 Qt offscreen；测试容器缺少的 EGL / OpenGL loader 解压至临时目录使用。
启动任务工作台不会创建 VTK OpenGL 上下文。三维结果的完整交互仍需在具备图形
驱动的真实桌面验证；本次验证了 VTK 文件数据及桌面下载路径。

## 本轮续开发：部署诊断与站点报告

同日补齐 `suan server doctor`、`suan connect check` 和持久站点验收报告。
诊断覆盖本机配置、目录访问、SQLite、worker 环境、调度器命令及 API／supervisor；
失败报告仍为可解析的 JSON，退出码为 1，报告不输出连接令牌。

科学示例现在在提交前保存完整 TaskSpec 和幂等键，在关键步骤保存状态与证据。
等待超时或提交响应丢失时保留可查询／重试的信息。结果校验覆盖 DAT／VTK 的
完整场数据及 PNG 解码，避免只有 summary.json 正确却误报通过。
每次运行保存独立的 `acceptance-<run_id>.json`，包含实际命令、源文件校验值、
客户端和计算环境、输入／结果 manifest、日志片段及误差。

Linux / Python 3.12.13 验证结果：

- 源码环境完整回归：**67 passed**，25.40 秒，包含桌面 offscreen 和 MCP。
- wheel／sdist 构建成功，安装后的 `pip check` 通过。
- 从 sdist 提取测试与示例，在源码目录之外运行；确认新模块导入自独立环境
  `site-packages`。安装包完整回归：**67 passed**，25.92 秒。
- 新增及受影响测试共 25 项；包含未初始化／损坏配置、目录探针清理、网络磁盘识别、
  损坏数据库、Python 超时、缺失调度器命令、认证失败、服务停止、提交响应丢失、
  等待超时保留任务、错误场数据及 NaN 摘要拒绝。

两次完整回归均只有原有 pyqode 的 `sre_constants` 弃用警告。
本轮没有进行真实集群、外部 SSH 或独立桌面安装器验收；新增检查的通过状态
不改变下方站点验收边界。

## 覆盖范围

| 验收项 | 证据 |
|---|---|
| API 与 supervisor 分别重启，计算继续 | `test_deployment.py` 实际启动独立进程，检查 worker 身份与日志无重复 |
| 输入隔离、幂等提交、并发上限、取消 | `test_runtime.py` 通过 HTTP 提交实际 Python 进程 |
| 断点上传下载、校验失败、路径边界 | 中断后的字节偏移、SHA-256、符号链接与越界路径检查 |
| 程序失败、缺少结果、超时、内存超限 | 实际失败进程与资源限制触发 |
| worker 丢失与外部终止信号 | 保留活动程序的待核实状态，可取消；外部信号不误报用户取消 |
| PBS / Slurm 状态与不确定提交 | 模拟命令协议；真实运行生成的 job.sh、worker 和程序；不重复派发 |
| 调度器不可用、资源映射、历史查询 | 排队／失败／取消／待核实、跨日期查询与每节点资源参数检查 |
| 确定性参数扫描完整流程 | `examples/runtime` 的两组输入生成、计算、均值与最大值校验、PNG / VTK 下载 |
| 科学格式与无窗口预览 | DAT / NPY / VTK 往返；独立 VTK reader 校验坐标顺序；Agg PNG |
| 桌面远程流程 | Qt 界面通过保存的 HTTP 连接配置上传、提交、读日志、下载 |
| MCP 与 CLI 使用同一任务 | MCP 创建／提交／查询，CLI 读取同一成功记录 |
| 旧桌面和包入口 | 从非项目目录创建工作台；科学模块、GUI 资源、旧 CLI 组在 wheel 中可用 |
| 部署与连接诊断 | `test_diagnostics.py`、`test_deployment.py`：配置、磁盘、数据库、Python、命令、API 认证和 supervisor |
| 验收报告与失败证据 | `test_acceptance.py`、`test_deployment.py`：提交前保存幂等键、超时保留任务、完整场校验与安装包案例 |

## 尚需站点验收

- 真实 PBS / Slurm 集群、MuPRO 可执行程序、MPI / module 环境、共享文件系统、
  队列和站点资源策略；本次调度器测试为协议模拟，不是实际集群性能验证。
- 真实 SSH 网络断线／重连；本次已验证客户端重建和服务端任务寿命独立，
  未对外部服务器执行 SSH 测试。
- Windows / macOS 运行；已添加 Linux / Windows CI 矩阵，但本次仅在 Linux 执行。
- PyInstaller 冻结桌面二进制的多进程启动与 Python 解释器分发；当前验收发布物
  为 Python wheel / sdist，未发布到 PyPI 或创建远程 release。

交互式 Python 内核、远程实时三维渲染、Web / 手机界面和团队权限属于后续阶段。

安装、API、SSH 与真实集群验收命令见 [runtime 使用指南](runtime.md)。
