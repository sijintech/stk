# 界面术语表（中英文）

2026-10-06 按[独立使用者审视](user-review-2026-10-06.md)第 5、8 条统一。界面文案（`desktop/app/i18n`）与用户文档使用下表；
代码标识、协议方法名和 Python API（如 `workspace` 编辑器 ID、`suan.desktop_bridge`、`stk.runtime`）保持不变。
新增文案先查本表；需要新术语时在此补充一行再使用。

| 概念 | 中文 | English | 说明 |
|---|---|---|---|
| 启动后的分步引导页 | 工作台 | Home | 编辑器 ID 仍为 `workspace` |
| AI 准备与问答页 | AI 助手 | AI Assistant | 原“AI 工作区 / AI Workspace” |
| 运行环境上的工作目录 | 工作区 | Workspace | 只指 Runtime 中存放输入/输出的工作区 |
| 执行计算的 Linux 服务 | 运行环境 | Runtime | 直连或经 SSH；中文界面不再直接写 Runtime |
| 远端任务及其管理页 | 任务 | Jobs / task | “任务”编辑器；只有 Slurm/PBS 等调度系统的作业称“集群作业” |
| 项目中一次仿真的冻结方案与提交 | 仿真运行（记录） | Simulation runs | 项目页“仿真运行记录” |
| 分析图的一次独立执行 | 分析运行 | Analysis runs | 分析图侧栏“运行”页 |
| 多行仿真的冻结范围 | 仿真批次 | Simulation batches | |
| 桌面与 Python 之间的后台进程 | 后台服务 | Python service | 原“桥接 / bridge”；日志标签为“后台服务日志 / Service log” |
| 三维结果视图 | 查看器 | Viewer | |
| 参数表中的一行 | 行 / 参数行 | row | 记录 ID 属于技术详情 |
