# STK 0.1.0a1 验收记录

日期：2026-09-09。状态：工程预发布，尚未完成真实集群和独立桌面安装器验收。

## 2026-09-30：Token Plan 本机配置与首次真实文字请求

用户已在本机 `~/.bashrc` 中导出 `STK_TOKEN_PLAN_API_KEY`，并授权选择默认模型。
本轮添加 `STK_TOKEN_PLAN_MODEL=qwen3.7-plus`；通过新交互式 Bash 启动的桥可读取配置，
检查仅输出配置存在状态和模型名，没有输出密钥。非交互式进程原先未继承该变量，
[请求指南](project-requests.md)已补充启动文件、重开终端和应用环境继承的区别。

在 Linux 使用真实 `ProcessBridge` 子进程和 NDJSON 协议，以隔离项目/状态/缓存目录运行一次明确发送。
仅捕获人工构造的单个 `temperature = 300 K` 单元格，请求模型按“数值 单位”回答，
输出预算 128 token、不启用思考、无工具。`qwen3.7-plus` 返回 **`300 K`**，请求状态为 **completed**，
提供方报告输入 **668 token**、输出 **4 token**；只发送一次，没有重试或使用实际研究项目。

验证助手消息与源上下文关联、文字 SHA-256、单个请求/两条消息、参数快照与修改历史未变，
无额外 `project.changed` 事件或协议校验错误。桥正常退出后重新打开 SQLite，读取到相同完整请求和回复。
密钥未出现在请求、助手消息或桥协议输出中。临时证据目录 `/tmp/stk-token-plan-live-ic7pfdi7`，
结果 `report.json`，请求 ID `e94ae822-c756-4d10-a274-cc2cabf6431e`。

这验证了当前 Linux 桥到提供方再到项目存储的单次文字链路；不代表科研回答质量、多轮对话、
全部模型或 macOS/Windows 原生按钮的真实账户验收，也不代表服务方确认本应用的套餐适用性。
本轮仅修改本机 shell 配置及文档，生产代码沿用 `2ba950b` 的跨平台 CI 基线。

## 2026-09-30：阿里 Token Plan 文字请求接入

按用户指定端点接入 `aliyun-token-plan/1`，固定 HTTPS Chat Completions、非流式文字与不启用思考模式。
本机从 `STK_TOKEN_PLAN_API_KEY` 读取专属凭据，可用 `STK_TOKEN_PLAN_MODEL` 设置默认模型；
不读取 OpenAI/通用百炼密钥，不将凭据、认证头或错误正文写入项目。模型 ID 在原生界面仍可明确填写。

桥和 Python 增加 `project.requests.provider/start/recover`，原生请求页增加准备、明确发送和遗留执行核对。
准备只固定已保存的用户消息和上下文；预检在领取发送权前完成，配置失败保持尚未发送。
发送只发生一次，无重定向、自动重试或工具调用；完整回复才可原子发布，截断/工具回复拒绝，未知传输结果保留不确定。
本轮沿用格式 8，没有新表或新事件。关闭项目的已启动请求继续绑定原库；桥关闭立即隔离迟到回复，
后台尽力写入不确定状态。独立审查发现的 worker 早于关闭线程退出的竞态已修正并加入确定顺序回归。

本机完整桌面 **584/584、无跳过**，请求/讨论与截图重点 **14/14**。Python 主回归 **500/500**，
随后补充真实注册适配器从 HTTP 编解码经桥到 SQLite 的 **4 项**集成，所在文件 **10/10** 通过。
适配器 **74 项**覆盖固定端点/认证隔离、完整/非法/截断回复、状态分类、超时与取消；使用内存 socket，
没有外部网络或套餐调用。字典各 **1039 项**一致，中文 Vulkan 请求页已查看，修改文档 **134 个本地链接**有效。
代码提交 `2ba950b` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36613518011) **7/7 任务通过**：
Windows Python 3.10/3.12 各 **1254 passed、59 skipped、260 deselected**；
Linux Python 3.10/3.12 各 **1665 passed、7 skipped、4 deselected**，打包及 graph doctor 均通过。
四组 Python 环境都完整运行 **74 项适配器、27 项执行器、10 项桥模型请求**测试，相关用例无跳过。
Windows 跳过平台/可选依赖/性能/许可场景；Linux 跳过 2 项性能、2 项可选 MCP 和 3 项许可求解器场景。

对应[桌面 CI](https://github.com/sijintech/stk/actions/runs/36613517994) **5/5 任务通过**：
Linux **584/584**、macOS arm64 CPU **359/359** 与 Metal **69/69**、Windows MSVC CPU **319/319**，均无跳过。
Linux/macOS 可搬移安装包及干净环境启动检查通过；中文 Metal 请求页截图已下载查看，布局和文字显示正常。
Windows GPU、真实账户模型调用和套餐适用性不在本次自动化验收范围内；没有使用真实账户进行模型验收。

使用及双平台环境设置见[请求指南](project-requests.md)，真机步骤见[工作台验收](workbench-acceptance.md)。
阿里官方对 Token Plan 工具用途有限制；技术协议适配不等于服务方已确认 STK 的套餐适用性。
流式回复、远端查询、工具提案与完整 AI 主页继续按[开发计划](development-plan.md)推进。
日志 `/tmp/stk-aliyun-python-all.log`、`/tmp/stk-aliyun-wire-bridge.log`、`/tmp/stk-aliyun-native.log`、
`/tmp/stk-aliyun-full.log`，JUnit `/tmp/stk-aliyun-full.xml`。

## 2026-09-30：请求记录与本地执行生命周期

格式 8 增加 `project_requests`，引用明确保存的上下文和用户消息，固定配置、输入摘要与助手消息身份。
创建、查询、取消和重开不发送请求，不修改参数修订或撤销历史。完成标记与助手消息在同一事务内保存；
旧项目按格式 1–7 → 8 显式备份升级，原数据及历史保留，打开不迁移。

本地 `RequestExecutor` 由可信调用方注入适配器，发送前取得系统锁并持久领取唯一执行权；
重复开始、两个进程、取消竞争、进程退出和关闭后的迟到回复都有回归覆盖。未知网络结果、丢失执行器或
本地保存失败保留不确定状态，不自动重发。当前没有内置提供方、凭据读取、真实模型调用、流式显示或工具提案。

桥和 Python facade 增加 `project.requests.create/get/list/cancel`；原生 **讨论 → 请求** 支持列表、
刷新、取消和查看原消息/已保存回复，刷新详情同步列表状态。旧按钮和迟到回调仍固定原项目句柄及请求 ID。
接口与存储统一拒绝配置标识中的 `//`，不接受认证字段或任意提供方参数；模型/适配器名称不会动态导入模块。

最终本机项目/请求/桥/脚本 Python **416/416**；另运行脚本与 MuFerro/批次工作流 **32 通过、2 跳过**，
两个跳过项需要显式启用真实许可求解器，本轮没有改变求解器或重新进行物理结果验收。
存储/讨论/执行器重点 **100/100**；最终完整桌面 **582/582、无跳过**，包含三项新增原生集成与
四项中英文 GL/Vulkan 请求页渲染。中文 Vulkan 请求页已查看，字典各 **1028 项**一致。
Linux/macOS CI 已将请求页列入十八类工作台截图必跑检查。
`f493224` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36595784259) **5/5 jobs 全通过**，覆盖 macOS Metal、
Linux GL/Vulkan、Windows 编译/CPU/真实桥、Linux 打包与干净环境启动；Windows CI 不包含 GPU 真机渲染。
macOS artifact 确认 **357 项 CPU、69 项 Metal 全通过且无跳过**，
三项请求原生测试及中英文请求截图全部实际执行，中文 Metal 图像已查看。

首轮 Windows Python 测试暴露 pytest 自动生成的超长用例 ID 超过 Windows 环境变量限制。
`bc3edf8` 只为两组参数化用例指定简短名称，保留全部超长输入及断言，聚焦 **18/18** 通过。
其 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36596541216) **7/7 jobs 全通过**；Windows Python 3.10/3.12 各
**1166 通过、59 按环境跳过、260 按标记排除**，两版均实际执行全部 **23 项请求执行器测试**，包含跨进程锁与进程退出恢复。
该测试命名修正不触发桌面工作流，桌面生产代码验证继续对应 `f493224`。

日志 `/tmp/stk-requests-python-final.log`、`/tmp/stk-requests-python-remaining.log`、
`/tmp/stk-request-storage-executor.log`、`/tmp/stk-requests-full.log`，JUnit `/tmp/stk-requests-full.xml`。
使用见[请求指南](project-requests.md)，双平台步骤见[工作台验收](workbench-acceptance.md)。
下一包接单一真实提供方的显式文字请求与结果核对，工具提案随后复用现有草案检查/应用接口。

## 2026-09-29：Python 共享选择与输入保护

新增 `p.selection()` / `p.select(table_id, record_id, expected_revision=...)`，通过两项可协商的本机
反向 UI 操作读取/改变共享表格与记录选择。固定项目句柄、已载入修订和规范 UUID；先校验完整归属再切换，
无效请求不部分改变选择。读取不刷新数据库；后续上下文捕获/编辑仍通过数据库修订检查。
选择不改变布局、焦点、修订、修改历史或已保存草案，任何窗口正在输入文字时拒绝写入选择。
同项目跨表切换保留每个编辑器的独立查询，缓存随目标表重新建立；删除最后一张表后清除残留记录 ID。

真实 Python worker 与原生界面新增 **5 项**集成测试，覆盖空项目、精确选中行的上下文捕获、
错误参数/归属/修订、输入保护、跨表筛选、删除对象，以及排队期间修改修订或切换项目。
相关原生 **13/13**、Python **65/65**，最终完整桌面 **575/575、无跳过**；字典各 **1011 项**一致。
旧六项 UI 能力继续可用；取消/超时后丢弃迟到回复，不重放请求。此包不新增 SQLite 格式。
`00c991c` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36574786525) 全部通过，包含 Windows Python 3.10/3.12。
[desktop CI](https://github.com/sijintech/stk/actions/runs/36574786487) 全部通过，包括 macOS Metal、Linux GL/Vulkan、
Windows 编译/CPU/真实桥、安装包与干净环境启动。Windows CI 不包含 GPU 真机渲染。
macOS artifact 确认 **354 项 CPU、67 项 Metal 全通过且无跳过**，新增五项共享选择测试全部实际执行。

日志 `/tmp/stk-selection-native.log`、`/tmp/stk-selection-python.log`、`/tmp/stk-selection-full.log`，
JUnit `/tmp/stk-selection-full.xml`。用法见[Python 指南](scripting.md#查询和改变原生共享选择)，
双平台手工检查见[工作台验收清单](workbench-acceptance.md)。

## 2026-09-29：表格搜索与捕获单元格预览

普通项目表格增加视图内文字搜索、只显示含错误记录、匹配数量及清除筛选。
各区域分别保存查询，排序/点击/编辑映射回原记录 UUID；隐藏选中记录时保留共享选择，
该区域不能直接修改或删除隐藏行。旧按钮还检查输入框刚提交的查询，避免失焦与重绘之间操作旧目标。
数值排序保持完整整数精度；筛选不改变项目修订、运行/批次范围或 CSV 导出范围。

讨论页增加只读捕获单元格表与原始单元格详情。字面量、空值、未设置、求值错误、缓存不可用、
省略和缺失对象分别显示；数据来源只使用保存的上下文，实时修改或删除字段不改变历史展示。
JSON 摘要按 UTF-8 字节和深度限量生成，不序列化看不到的数组尾部；普通表格按需缓存最多 4096 个摘要。

本机新增纯辅助测试 **9 项**、原生集成 **3 项**；重点与讨论/筛选渲染 **15/15**，
完整桌面 **570/570、无跳过**。覆盖筛选后排序/编辑、等行数查询切换、隐藏选择与迟到按钮、
两个区域独立查询及冻结值在实时编辑/删除后不变；中文 Vulkan 筛选和英文 GL 捕获表截图已查看。
字典各 **1011 项**一致。此包没有 Python、存储格式或桥协议变更。
`8bc4016` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36573460344) 已完成 macOS Metal、
Linux 打包和干净环境启动；Linux/Windows 编译被后继 `00c991c` 推送取消，其代码已由后继提交的完整 CI 覆盖。
已下载 macOS artifact，确认 **349 项 CPU、67 项 Metal 全通过且无跳过**，中文筛选及英文捕获单元格截图已查看。
该提交的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36573460403) 全部通过。

日志 `/tmp/stk-table-views-native.log`、`/tmp/stk-table-views-full.log`，JUnit `/tmp/stk-table-views-full.xml`。
使用见[项目指南](project.md)与[上下文指南](project-contexts.md)。下一步补 Python 的共享选择读写接口。

## 2026-09-29 显式上下文与讨论来源

格式 7 的上下文捕获、手工消息、草案来源已接入 SQLite、桥、Python 与原生讨论页。
保存和恢复均不应用参数、不调用模型或执行消息中的代码。用法见[上下文与讨论指南](project-contexts.md)。

本机项目/桥/脚本/工作流 Python 回归 **300 通过、2 跳过**（两个真实许可求解器测试未显式启用）；
草案/上下文/讨论存储重点 **86/86**，桥及真实脚本 worker **32/32**。
原生专项与新增截图 **9/9**；完整桌面 **554/554、无跳过**。
覆盖原子写入、并发幂等、来源损坏、格式 6 迁移备份、旧上下文不变、消息代码不执行、
项目切换/桥重启、来源关联与撤销、旧回调不能改绑、原生按钮和未保存输入保护。
中英文 GL/Vulkan 讨论页四项通过，中文 Vulkan 和英文 GL 图像已查看；字典各 **988 项**一致。
本轮修改文档的 **174 个本地链接**有效，Linux/macOS CI 已增加讨论页截图必跑检查。
`b796b90` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36570155199) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36570155222) 全部通过，包括 macOS Metal、Linux GL/Vulkan、
Windows 编译/CPU、安装包及干净环境启动；文档部署也已成功。

日志 `/tmp/stk-contexts-python-all.log`、`/tmp/stk-contexts-native.log`、`/tmp/stk-contexts-full.log`，
JUnit `/tmp/stk-contexts-full.xml`。

## 2026-09-29 持久草案与恢复

格式 6 的保存、分页、读取、丢弃和原子应用已接入存储、桥、Python facade 与原生检查页。
项目/桥/工作流 Python **248 通过、2 跳过**，两个真实许可求解器测试按默认配置跳过；
本批只修改项目草案管理，未重新运行许可求解器。草案存储新增 **34** 项测试，包括迁移备份/回滚、
并发保存/应用、规范化 ID、响应恢复、校验损坏和撤销后终态保留。

原生重点和新增截图 **11/11**，完整桌面 **546/546、无跳过**；验证了真实桥的保存/重开/重启、
重新预览后明确应用、过期草案另起副本、输入/异步保护、保留错误提示和冲突刷新。
中英文 GL/Vulkan 草案面板四项通过，中文 Vulkan 和英文 GL 图像已查看；字典各 **947 项**一致。
`f1001cf` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36565773604) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36565773668) 全部通过，包含 Linux GL/Vulkan、
macOS Metal、Windows 编译/CPU、安装包和干净环境启动；草案截图已纳入跨平台必跑检查。

日志 `/tmp/stk-saved-drafts-python-all.log`、`/tmp/stk-saved-drafts-native.log`、`/tmp/stk-saved-drafts-full.log`，
JUnit `/tmp/stk-saved-drafts-full.xml`。操作与兼容边界见[草案指南](project-drafts.md)。

## 2026-09-29 Python 发起原生修改检查

`stk.project.review` 经真实隔离 Python worker 和本地 UI 请求通道启动只读预览，并自动显示原生差异页。
新增 6 项原生集成测试，覆盖明确点击应用后才写入/可撤销、控制台快捷键与新增页签、正在输入的文本保护、
无效参数/Unicode 字节限制、旧修订与草案冲突、请求排队期间切换项目、清除迟到候选及分离桥的请求失效。
相关原生 **13/13**、Python **69/69**、完整桌面 **537/537、无跳过**；能力协商和共享 schema 校验通过。
中英文字典各 **923 项**，中文 Vulkan 检查页截图已查看，文档 80 个本地链接有效。

日志 `/tmp/stk-python-review-python-all.log`、`/tmp/stk-python-review-native.log`、
`/tmp/stk-python-review-full.log`；JUnit `/tmp/stk-python-review-full.xml`。
`fa324d6` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36562716767) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36562716768) 全部成功，包含 Linux GL/Vulkan、macOS Metal、
Windows 编译/CPU 测试、安装包/干净环境启动与双版本 Windows Python。
该提交的入口不包含模型生成、持久草案或新的外部任务执行；草案持久化见后续新增记录。

## 2026-09-29 参数表驱动批次

新增批次协调与原生面板复用项目运行和 MuFerro 模板。相关 Python **29 通过、2 跳过**，
真实 Release MuFerro 批次显式启用后 **1 项通过**：298 K / 310 K 的两个运行，参考能量分别为
`−727.9144455` / `−691.5580935`；重复准备/提交/收集不新增对应任务或结果。
错误/恢复覆盖部分准备失败、进度持久化、关闭重开、过期参数、准备及提交响应丢失、中断、取消后
仅为指定行生成独立尝试，以及伪造标签不能改变模板命令。参数入口校验最终 **1/1** 复验通过。

完整桌面 **531/531、无跳过**；新的 Linux 原生按钮测试通过真实桥/Runtime 和明确的假 SDK
执行三行批次，重复保存/准备/提交、收集以及服务器停止后的关闭重开均通过。
四项中英文 GL/Vulkan 批次渲染通过，已查看中英文截图；中英文字典各 923 项一致。
日志 `/tmp/stk-batch-python-all.log`、`/tmp/stk-batch-full.log`、JUnit `/tmp/stk-batch-full.xml`，
真实运行日志 `/tmp/stk-batch-real.log`，证据 `/tmp/stk-batch-real-HRg9Kh/test_real_muferro_temperature_0/batch-evidence.json`。
`a598c2c` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36450940425) 和
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36450940464) 全部成功，包含 Linux GL/Vulkan、
macOS Metal、Windows 编译/CPU 测试、打包/干净环境启动，以及 Windows Python 3.10/3.12；文档部署成功。
原生自动化和离屏渲染仍不等同于 macOS/Windows 真机输入设备交互验收。

## 2026-09-28 MuFerro 项目流程首版

当前工作流通过真实桌面桥调用项目/Runtime API，连接隔离的本机 Linux Runtime，运行已安装的 Release muFerro。
程序 SHA-256 为 `c0c1f3454f5ff5384c76e70455b0441bb8ebeeb40b711b2360f2f0f1d099683a`；
单 rank、单线程、`launcher=none`，不启动 Hydra。许可仅由求解器从原有目录使用，未复制到 STK 项目。

- SDK 原始案例导入后冻结，16×16×16 网格、101 步、输出间隔 100；298 K 最终归一化总能量
  `−727.9144455` 与已有参考一致；修改项目参数至 310 K 后生成独立方案和任务，总能量 `−691.5580935`。
- 两次 `stk-mupro-1` 均通过，下载后重验输入、产物哈希、完成记录、进度、能量和帧头。
  独立 NumPy 文本读取检查每次 30 个 DAT 的所有值有限、点数/分量数、网格范围和索引唯一性；
  同时覆盖原生按分量索引的 DAT 格式，未把测试模拟器的逐点列格式误当作唯一格式。
- 同一方案重复提交不增加任务；重开项目后重复收集仍为原结果行，改变温度后保留旧运行及其过期状态。
- 当前原生 `stk-desktop --headless --preset muferro-domains` 打开两次已收集结果，输出第 100 步铁电畴；
  OpenGL 图像已目视检查。100 是最后输出的 Polar 帧，最终能量对应第 101 步。
  软件 EGL 首次上下文候选报告 `EGL_BAD_MATCH`，随后上下文创建和导出成功，进程退出 0。

测试入口为 `tests/test_workflow_muferro.py::test_real_muferro_project_workflow`，需显式配置
`STK_TEST_MUPRO_PREFIX`、`STK_MUPRO_ENV_SCRIPTS`、`MUPROROOT`；默认 CI 不启动许可求解器。
输入冻结一致性检查加入后，真实求解器再次全程通过；最终日志 `/tmp/stk-muferro-real-final.log`、
`/tmp/stk-muferro-real-render-final.log`，
证据 `/tmp/pytest-of-mnemora/pytest-134/test_real_muferro_project_work0/real-evidence.json`，
图片 `/tmp/stk-muferro-real-render/{first,changed_temperature}.png`；这些临时路径不属于发行物。

工作流/相关 Python 回归 **32 通过、1 跳过**（上述真实测试另行通过）；本机完整桌面 **525/525**。
原生导入按钮验证了真实 Python 调用和项目切换保护，GL/Vulkan 中英文仿真面板截图通过并检查。
桌面日志 `/tmp/stk-muferro-full.log`、JUnit `/tmp/stk-muferro-full.xml`，
Python 日志 `/tmp/stk-muferro-python-final.log`；原生输出显示调整后的相关 **5/5** 通过，
见 `/tmp/stk-muferro-final-native.log`。

新增 `SimulationPython.NativeMuFerroButtonsPrepareSubmitCollectViewAndReopenOffline` 直接驱动原生
项目面板，经过真实 Python worker 和隔离的 Linux Runtime 执行导入、准备、提交、日志与收集。
重复准备时服务器任务数仍为零，重复收集后只有一个任务和一行结果；关闭 Runtime、关闭再打开项目后，
从原生“查看已收集结果”按钮加载非空三维载荷。测试默认使用明确的假 SDK，Linux CI 要求此项执行且通过；
设置上述真实 SDK 环境后，同一个原生测试也已通过，结果表参考能量 `−727.9144455` 一致。
日志 `/tmp/stk-muferro-native-real.log`，JUnit `/tmp/stk-muferro-native-real.xml`。
加入完整原生链路后的本机全量桌面 **526/526、无跳过**，日志 `/tmp/stk-muferro-native-full.log`、
JUnit `/tmp/stk-muferro-native-full.xml`。

功能提交 `7d96151` 首轮 Runtime CI 发现 Windows 3.12 的 `fstat`/`stat` ctime 语义差异；
修正提交 `ef25286` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36442800913)
全部通过，包含 Windows Python 3.10/3.12。最终桌面跨平台 CI 也已通过，见下方最新确认。
本节不能作为 Windows GPU、真机输入法或 macOS/Windows 到实际远端 SSH 的验收证据。

### 完整仿真目标逐项复核

`763eb0b` 上重新核对“在 STK 中完成一个完整的仿真计算”：

| 必要能力 | 已检查的证据 |
|---|---|
| 原生导入、编辑参数、生成并冻结输入 | 原生完整流程驱动导入/准备；`ProjectPython` 验证表格编辑；真实工作流从项目行的 298 K 改到 310 K，保存各自冻结输入 |
| 明确提交、状态、日志与取消 | 原生完整流程准备后服务器任务数为零，再通过提交按钮执行真实求解器并读取日志；原生运行面板测试单独覆盖取消及请求次数 |
| 收集、检查与关联输出 | 两次真实运行各校验 36 个文件哈希；项目保存冻结输入、任务 ID、程序哈希及结果关联；重复收集只有一行结果 |
| 数值及三维结果 | 独立 NumPy 读取两次运行各 30 个 DAT 的全部数值，检查有限值、网格和分量索引；能量分别为 −727.9144455、−691.5580935；原生 Viewer 导出两次结果并检查图片 |
| 重开、断线恢复与独立重算 | 原生流程停止 Runtime 后重开项目并加载结果；两次真实运行在重开后仍存在，旧参数标记 changed、新参数 current；响应丢失测试重新打开项目后只恢复一个任务 |
| 自动回归与交付 | 本机桌面 526/526 无跳过，真实原生按钮用例通过；实现及测试已推送 main，`763eb0b` 的跨平台桌面与 Runtime CI 全部成功 |

前述默认 pytest 临时目录已被后续测试自动清理。为保留可复查的项目与数据，本次重新执行真实测试并
指定独立目录；当前证据为 `/tmp/stk-muferro-audit-763eb0b-I6Zw8m/test_real_muferro_project_work0/real-evidence.json`，
日志 `/tmp/stk-muferro-audit-real.log`（1 项通过）、`/tmp/stk-muferro-audit-numeric.log`、
`/tmp/stk-muferro-audit-render.log`，图片 `/tmp/stk-muferro-audit-render-zrl8l2j8/{first,changed_temperature}.png`。
该目录不会被后续默认 pytest 清理，仍是本机临时验收数据，不属于发行物。
以上证据证明单次完整仿真功能闭环已实现并验收。后续批量、AI、节点编辑与平台真机交互按主计划继续推进。

## 2026-09-28 最新跨平台确认

MuFerro 流程最终提交 `763eb0b` 的 [desktop 36444060112](https://github.com/sijintech/stk/actions/runs/36444060112)
**全部成功**：Linux GL/Vulkan、macOS Metal、Windows 编译/CPU/桥、Linux 安装包和干净环境启动，
以及 macOS 打包与从解压后的应用启动。
[Runtime 36444060140](https://github.com/sijintech/stk/actions/runs/36444060140)、
[文档 36444060188](https://github.com/sijintech/stk/actions/runs/36444060188)和 Secret scan 全部成功。
下载产物的 Linux JUnit **526 项**、macOS JUnit **322 项 CPU / 59 项 Metal** 均无失败、无跳过；
Linux 新增完整仿真按钮测试确实执行。macOS 中英文仿真面板与离线三维截图已目视检查，
产物在 `/tmp/stk-macos-muferro-763eb0b`、`/tmp/stk-linux-muferro-763eb0b`。
Windows 日志确认 **282/282** CPU 测试通过，MuFerro 原生导入及项目身份保护用例实际执行；
本机日志 `/tmp/stk-muferro-desktop-763eb0b-ci.log`。
Runtime 3.12 wheel 中 `suan/workflows` 和脚本入口与当前源码字节一致，确认新增模块实际进入 Python 包。
前一提交 `ef25286` 的桌面运行被后继推送取消，不作为通过证据；本次成功运行覆盖其 Windows 时间戳修正。
Windows CI 仍不包含 GPU 真机渲染，实际异机 SSH 和输入法交互仍需相应平台环境验收。

此前表格修正提交 `c3fa59c` 的[desktop 36416998477](https://github.com/sijintech/stk/actions/runs/36416998477)
**全部成功**，包含 Windows 原生编译/CPU/桥、Linux GL/Vulkan、macOS Metal、两平台打包和干净环境启动。
本机完整 **504/504、无跳过**；下载最终 macOS 产物的 **313 项 CPU、53 项 Metal** 无跳过全部通过，
目视确认横向滚动条不再遮挡第三行数据。
[Runtime 36416998488](https://github.com/sijintech/stk/actions/runs/36416998488)和
[文档 36416998657](https://github.com/sijintech/stk/actions/runs/36416998657)成功。
后续说明文档提交 `d01bf76` 的 Runtime **36417769639**、文档 **36417769613** 成功，未改变上述功能代码。

`a0d7f57` 包含文件 Viewer、表格滚动/精确排序、修改预览及工作台必跑检查：
[desktop 36414890836](https://github.com/sijintech/stk/actions/runs/36414890836)、
[Runtime 36414891171](https://github.com/sijintech/stk/actions/runs/36414891171)、
[文档 36414891070](https://github.com/sijintech/stk/actions/runs/36414891070) **全部成功**。
桌面包括 Linux、macOS、Windows、打包和干净环境启动；Windows 仍是 CPU/桥测试，无 GPU 验收。
已下载 macOS frames artifact：JUnit 的 **312 项 CPU、53 项 Metal** 全通过且无跳过；
归档含 **22 张工作台图片**，已目视检查离线三维/参数表和文件预设入口。
截图进一步发现横向滚动条减少了实际可见行数，其高度修正已由上述 `c3fa59c` 验证。

`dbf3cde` 自身的 desktop run 36414605007 被后续 CI 配置提交取消；上述成功的后继运行覆盖其修改预览代码。
此前文件/表格提交 `f1a0f72` 的 desktop **36413089067**、Runtime **36413089012**、文档 **36413089085** 也全部成功。
本节更新下方各开发包编写时的“待跟踪”状态，不把更晚的尚未完成 CI 自动视为已通过。

## 2026-09-28 项目修改预览

相关 Python **230/230**、完整重编译桌面 **503/503** 通过。源库字节、外部文件和实际历史保持不变；
候选公式结果与使用返回命令进行实际提交后的快照一致。覆盖只读数据库、旧格式拒绝/WAL、
大小预算、身份替换、公式循环错误、过期修订及预览求值期间的并发编辑。真实桥和独立 Python worker
确认预览不发布修改事件，C++ 客户端验证明确提交前后区别；本批远端 CI 待跟踪。

## 2026-09-28 表格滚动与计算值排序

完整重编译桌面 **503/503、无跳过**；此前组件/窗口子集 **149/149**。
覆盖 1x/1.5x/2x 下的横向滚动条、Shift + 滚轮、窗口事件横向数据转换、排序和列宽命中、
选择/键盘、扩大区域/删除列后的偏移校正。公式按计算值排序，64 位整数保持精度，等值记录顺序稳定。
离线工作台四项中英文 GL/Vulkan 截图确认派生温度列可滚入视野。手势是合成事件验收，物理触控板待真机测试。
本批远端 CI 待跟踪。

## 2026-09-28 项目文件 → Viewer

完整重编译后的桌面 **498/498、无跳过**，字典 **851/851** 通过。真实桥按钮验证中文载荷位置、
缺失/不支持文件与预设拒绝、项目修订不变；独立 Python 控制台加载实际 VTK。
验证父目录存在结果清单时仍使用选定场文件、切换预设保留文件名，以及 Viewer 隐藏/不存在时的标签切换。
四项中英文 GL/Vulkan 文件面板截图已检查；本批 macOS/Windows CI 待跟踪。

## 2026-09-28 离线工作台演示

Python 基础/实际 VTK 两种路径 **2/2**，原生 Python → 项目/Viewer/布局交互与中英文 GL/Vulkan
截图 **5/5** 通过。截图目视确认实际三维场，独立统计核对 4913 个点及平均值/最大值。
检查输入副本、重开、修改跨表参数只更新公式而不重跑生成文件，以及原布局恢复。
示例不依赖 Runtime，不创建远程任务。`55373a1` 的 desktop **36410580845**、Runtime **36410580865**、
文档 **36410580930** 全部成功。桌面首轮的干净环境安装遇到 PyPI `python-dateutil` 索引连续超时，
同一提交重跑失败作业后通过；未修改依赖或放宽测试。原生 Windows 基础 CI 不含 VTK；新交互仍需真机测试。

## 2026-09-28 CSV/TSV 参数表

完整桌面 **489/489**、相关 Python **113/113** 通过。覆盖中文、多行引用、精确整数、JSON/布尔、
空值、整批失败、源文件/编辑预算、并发修订、目标竞争不覆盖、一次撤销重做和公式值导出/错误拒绝。
原生按钮通过真实桥验证导入、导出、撤销及重复输出拒绝；4 项 GL/Vulkan 中英文截图已检查，字典各 **846 项**。
当前 CSV 导出要求目标文件系统支持硬链接，未包含 FAT 等目标文件系统验收。
`f4bfbae` 的 desktop **36408907358**、Runtime **36408908042**、文档 **36408907835** 全部成功，
同时覆盖 Python 分析图 API，包含 Linux、macOS、Windows、打包及干净环境。

最近项目 `623fe2b` 的 desktop **36406870490** 全平台成功，文档 **36406870578** 成功。
Runtime **36406870548** 首轮仅 Windows Python 3.12 的旧示例生成子进程超时（20 秒）；已重跑失败作业，
未取得子进程堆栈，不将超时归因于最近项目功能或字体缓存。同一提交重跑失败作业后全部成功，未修改测试或生产代码。

## 2026-09-28 Python 分析图

Python 图/桥/控制台/Hub **65/65**、原生图/Viewer/脚本 **53/53** 通过。
真实独立 Python worker 编辑完整分析图，校验节点错误，计算表格和载荷，核验 blob 哈希及原始场探针数值。
阻塞图 worker 验证控制台中断与进程回收，排队中断不影响其他活动图；真实 loopback Hub + 节点验证
待审核结果保留、显式取消，以及中断等待后远端仍完成、原 eval ID 恢复且不重复创建操作。
本批远端 CI 待跟踪，不代表原生 Node Editor 或完整图版本持久化已交付。

Python Viewer `616bf3f` 的 desktop **36405264363** 全部成功，Runtime **36405264493**、
文档 **36405264372** 成功。最近项目 `623fe2b` 的远端 CI 待跟踪。

## 2026-09-28 最近项目

完整桌面 CTest **484/484**、Python 桥/脚本/最近项目/Viewer **52/52** 通过。
真实桥重启后列表保留而项目不自动打开；通过原生表格按钮重开同一 UUID，移除只清除历史。
检查目录缺失、项目替换、历史损坏和偏好文件写入失败，保留项目文件与会话。4 项中英文 GL/Vulkan
截图已目视检查，中英文字典各 **833 项**。本批远端 CI 待跟踪。

## 2026-09-28 Python Viewer

完整桌面 **478/478**，UI 能力协商调整后的脚本/项目/Viewer 子集 **44/44**，相关 Python **23/23** 通过。
实际独立 worker 控制本机原生 Viewer，检查图层/透明度、混合非法更新不产生部分修改、来源变更保护、
时间序列与播放、显式图求值、错误状态和自动求值开关。Linux 的合成扫描结果通过真实 VTK 图服务加载；
Windows 基础环境测试使用可移植载荷/序列，不能据此声称 Windows 的完整 VTK Python 环境已验收。
扫描 `show.py` 把已下载结果送入共享 Viewer。本批远端 CI 待跟踪。

HTTP 测试端点移除反向 DNS 查询后的 `7ebf746`：desktop **36403445288** 全平台通过，
Runtime **36403445272**、文档 **36403445317** 成功，覆盖前序原生运行面板和温度扫描示例。

## 2026-09-28 手动项目扫描示例

`examples/project_scan` 和运行/Python Runtime 回归 **19/19 通过**。真实独立 Python worker 创建两个
温度案例、冻结并上传程序和输入，准备后远端任务数仍为零；明确提交后由真实 Linux Runtime 执行。
下载 VTK/PNG/JSON，汇总平均值/最大值，重复收集保留两条任务和两条结果记录；修改本地结果后拒绝收集。
独立 VTK reader 验证 `17×17×17` 网格和标量数量。示例明确使用合成场，不是科学模型有效性验收。

格式 5 后端 `613bf6c` 的 desktop **36400084985**、Runtime **36400084994**、文档 **36400084958**
已全部成功。原生运行面板 `f8b7943` 的远端 CI 继续跟踪。

## 2026-09-28 原生运行面板

完整桌面 CTest **474/474 通过**；其中项目/Python 相关 **54 项**，包含分页运行表格、旧参数保护、
关闭重开，以及通过真实 Python 桥和跨平台 HTTP 模拟端点测试提交/刷新/取消按钮，确认只提交一次、
任务状态更新不推进表格修订。四项 GL/Vulkan 中英文运行面板截图已目视检查；中英文字典各 **829 项**。
Python 运行/项目桥 **20/20** 通过。HTTP 模拟不执行求解器，真实 Linux 执行仍由下节集成测试覆盖。
本批原生面板的远端 CI 待推送后跟踪。

## 2026-09-28 项目运行记录基础

格式 5 的 Python/桥/Runtime/Hub 相关回归 **144/144 通过**；最后 Hub 状态读取调整后运行专项
**10/10** 再次通过。覆盖冻结输入上传后执行、源参数变更标记、改名/撤销、公式错误、旧格式备份升级、
响应丢失后新会话恢复同一个 Runtime 任务、连接改指拒绝和 Hub 审核后的只读恢复。
完整桌面 CTest **468/468 通过**，包括升级到格式 5 和共享契约验证；本批尚无原生运行面板。

前序提交 `23773d2` 的 desktop run **36398208056**、Runtime **36398208012** 和文档 **36398208047**
全部成功，确认输入快照的 Windows 时间戳兼容和历史契约修正；格式 5 的远端 CI 待本批推送后跟踪。

## 2026-09-28：Runtime 固定输入哈希

- `input_hashes` 覆盖全部显式选中的输入；校验任务目录中的实际副本后才排队。
  验证哈希不匹配、复制后内容变化时永不启动程序，失败尝试保留原幂等键，旧请求的历史摘要不变。
  工作区后来改变不影响已接受任务的同键恢复；改变预期哈希不能复用旧键。
- 桌面 Python 实际上传/提交/下载通过该检查；直连和 Hub 不支持该能力时在提交前拒绝。
  模型、Runtime、监控事件、脚本、桥、Hub 与 control 相关测试 **80/80** 通过，远端 CI 待跟踪。
- 输入快照兼容修正另通过 Python **49/49** 与原生 **7/7** 专项；保留源变化检测和内容校验。

## 2026-09-28：不可变输入副本

- 格式 4 只追加清单、内容哈希去重及显式备份迁移；打开旧格式不会改变文件。
  覆盖原文件修改/删除、索引撤销、目录搬迁、相同内容复用、空文件、预算、复制中变化、并发修订冲突、
  清单损坏、对象损坏/缺失、符号链接和 FIFO 替换、数据库备份缺少对象，以及 CLI/真实 Python worker。
- Python 相关回归 **133/133**，最终脚本/快照子集 **32/32**，目录发布同步调整后存储专项 **15/15** 通过。
  原生 Project **48/48** 通过，真实桥按钮验证来源删除和索引撤销后仍能校验、关闭重开恢复历史及对象缺失报告。
  中英文 OpenGL/Vulkan 截图已目视检查，字典 **793 项**通过。
- 全量桌面 468 项中 **467 通过**；唯一失败是旧桥生命周期测试仍预期格式 3，改为格式 4 后单项复验通过。
  本批远端 CI 待跟踪。当前冻结选定文件内容，不声称已经冻结完整程序/参数环境或提供原子目录快照。
- `9686180` 的 Runtime **36396871397** 捕获历史 schema 缺少格式 4 枚举，以及 Windows Python 3.12
  的 stat/fstat ctime 语义差异。已补 `upgrade_format` / `capture_files` 历史契约并分开比较同类时间戳，
  保留身份、大小、mtime、源文件变化和 SHA-256 检查；新增跨 API 时间差异与桥历史读取回归，远端修正待验证。

## 2026-09-28：Python Runtime 操作覆盖

- 实际隔离 worker 通过保存连接创建工作区、上传、幂等提交、读取分块中文日志和下载结果；
  同键重复提交返回同一任务，改变请求得到冲突。中断等待后远端任务仍在，新 worker 可显式取消。
- Hub 待审核结果保留完整 action，等待助手遇到审核/中断/失败返回对应状态；超时和网络错误不重试或取消。
  新增 `task.logs` 返回 base64 字节与偏移，Python helper 解码为 bytes；旧 Hub 过长响应按 limit 截取并修正偏移。
- Python 脚本/桥/Runtime/Hub/SSH **69/69** 通过；完整构建后相关原生 schema/项目/Python **23/23** 通过。
  随 `f055275` 的 desktop **36394747178**、Runtime **36394747020**、文档 **36394747069** 全部通过；
  不代表完整批次运行记录、Viewer Python 控制或跨平台远程 Python 已实现。

## 2026-09-28：文件索引与外部编辑入口

- 文件索引复用格式 3 普通表格和撤销，未新增数据库格式。Python 相关回归 **125/125**，
  最终文件/桥/脚本子集 **35/35**：项目移动、内外路径、已缺失和未来输出、符号链接变化、
  跨平台外部位置、结构损坏、修订冲突、UUID 保持、撤销不改文件、CLI 与脚本 facade。
- 全量构建后完整桌面 **463/463 通过，无跳过**。新增原生测试通过真实桥登记/刷新/检查路径，
  以注入的应用启动器验证缺失文件不会触发打开、读操作不增加修订以及拖入/撤销的边界。
  中英文 Vulkan/OpenGL 文件面板截图已目视检查，783 项字典检查通过。
- Windows 的系统打开从占位实现改为 Unicode ShellExecuteEx；VSCode 使用转义后的标准文件 URL。
  本机验证 URL 构造和原生调用边界；`6056591` 的 macOS/Linux CI、Runtime 与文档通过。
  Windows 编译及 255/256 测试通过，文件打开用例因斜杠形式不同的字符串比较失败；
  已改为比较实际文件身份，修正后的 `f055275` desktop **36394747178 全部通过**；真实文件关联/VSCode 启动仍待验证。
  没有把默认程序打开写成应用内 Markdown/PDF 预览，也没有把元数据索引写成完整资源备份。

## 2026-09-28：持久撤销/重做与表格管理

- 格式 3 增加按编辑批次持久保存的行差异；格式 1/2 显式备份后升级，旧格式打开不迁移。
  覆盖完整撤销到空项目、按原顺序重做、关闭重开、单元格定义切换、跨表依赖恢复、删除/重建交换行序、
  并发撤销与编辑只有一个成功、失败保持重做栈、损坏日志拒绝覆盖，以及固定随机混合序列逐步往返。
- 原生表格提供撤销/重做、表格/字段改名和对象删除；测试使用真实桥验证持久重做、共享修订、
  删除后原 ID 恢复、名称和单元格草稿冲突。Python facade、CLI 与桥使用相同操作。
- 本机全量桌面 **452/452 通过，无跳过**；随后新增的中英文 GL/Vulkan 管理面板 **4/4 通过**，
  截图已目视检查。最终 Project 标签 **36/36**、Python 项目/表达式/撤销/桥/脚本 **108/108** 通过；
  字典 **769 项**检查通过。
- 撤销不还原外部文件或运行中的模拟，升级前编辑没有可撤销的前值。
  `d0fd5f5` 的 desktop **36390818302**、Runtime **36390818350**、文档部署 **36390818365** 全部通过，
  同时验证 procfs 清理修正；前一 `dfd2c27` desktop 被后续推送自动取消。

## 2026-09-28：项目格式 2、引用与公式

- Python 项目/桥/脚本相关回归 **110 项通过**；最后缓存校验调整后项目/脚本子集 **87 项再次通过**。
  覆盖跨表稳定引用、重命名、删除/恢复来源、循环与下游错误、单位/类型/数值范围、非法 Python 语法拒绝、
  1,500 层依赖链/循环、只重算受影响单元格、损坏或旧版本缓存重建。
- 格式 1 保持可读写原有字面量；显式升级先生成并校验数据库备份。覆盖备份恢复、迁移失败回滚、
  并发升级、陈旧修订拒绝以及桥/CLI 同一语义；不会因为打开项目而自动升级。
- Linux 全量桌面构建后 **449/449 CTest 通过，无跳过**。最终绑定表格和错误颜色调整后，
  Project 标签 **29/29 再次通过**；其中真实 Python 桥验证公式编辑、依赖更新、冲突草稿、备份升级。
  中英文 Vulkan/OpenGL 公式编辑截图已生成并目视检查，字典 **759 项**检查通过。
- `d0b6c5c` 的 macOS/Windows、打包、Runtime CI 已通过；Linux 仅旧有超时测试的清理扫描发生
  `/proc` 读取竞态，`dfd2c27` 已修正并连续 12 次通过对应测试，远端修正结果继续跟踪。数据库备份不包含资源文件，
  未交付撤销、完整项目快照或模拟节点自动执行。

## 2026-09-28：原生 Python 与管理 SSH

- `7694ea3` 的 desktop CI [run 36382812292](https://github.com/sijintech/stk/actions/runs/36382812292)
  全部成功：macOS arm64/Metal、Windows/MSVC CPU、Linux GL/Vulkan、Linux 发布包和干净环境启动。
  Runtime/science 检查与文档部署也成功。此记录是 CI 验收，不替代用户实际输入法/完整交互验收。
- SSH 首版在 Linux 上完整重编译后 **442/442 CTest 通过，无跳过**，含 C++ → Python SSH
  配置契约及合成事件驱动的原生 Jobs 配置/断开/重连按钮测试；既有 GPU goldens 全部通过。
- `test_runtime_ssh.py` 与 Runtime/桥相关回归 **74 项通过**；补充失败候选、缺失客户端后，
  最终 SSH 专项 **16 项通过**。临时 sshd 使用测试目录中的独立密钥、配置和 known_hosts，
  只监听本机高端口，不修改用户 SSH 配置、不访问外部服务器。
- 真实 OpenSSH 访问 HTTP 与实际 Runtime：上传输入、提交一次、断开隧道后任务完成、
  重连下载字节一致；未知 host key 拒绝且不发送 token。另测父管道 EOF 进程清理、并发隧道复用、
  进程退出后重连、手动断开阻止隐式重连、端口被其他进程抢占、请求响应丢失不自动重放。
- Linux CI 安装 sshd 并要求真实 SSH 测试不可跳过；Windows 运行模拟转发与生命周期测试，
  macOS/Windows 原生 CI 要求 SSH 配置契约实际执行。desktop run **36386610173** 全部通过；
  Windows 守护进程清理断言改为限时等待 PID 消失后，Runtime run **36387729994** 全部通过。

配置与限制见 [SSH 指南](ssh.md)。真实异机网络、跳板机和 Windows/macOS OpenSSH 仍需站点验收。

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

## 2026-09-24 方向调整

用户确定的方向：

1. STK 独立于 Synorder 发展；桌面主线为 STK 自有的 Blender 原生工作台（`blender/`、
   `suan/blender_client`、`suan-control`、`suan-node` 与 Runtime）。
2. Synorder 集成推迟；`plugins/synorder` 与 `suan-synorder-node` 保留为可选。
3. MuPRO 作业的排队由 STK Runtime 负责。
4. 首个集群为并行云（Paratera），账号尚未开通。
5. 服务器 Runtime 仅支持 Linux；Windows 只作客户端。

据此完成的改动：

- Runtime：MPI 布局 `ranks`／`threads_per_rank`、argv 占位符 `{ranks}`／`{threads_per_rank}`／
  `{nodes}`、OMP／MKL 线程设置及 Slurm／PBS 映射；站点配置 `scheduler` 与不提交作业的 Slurm
  doctor 探针；本机 worker 启动失败不再占住并发名额；`/health` 增加 `resources`、`argv_tokens`，
  HTTP API 仍为 v1，已有任务的幂等键不变。
- 平台：`suan server init/start`、`suan-control init/serve`、`suan-node pair/run` 在非 Linux 上
  拒绝运行；`suan` 在 cp1252 控制台改用 UTF-8 输出；新增 pytest `server` 标记，CI 在 Linux 运行
  全部非桌面测试，在 Windows 只运行客户端测试与入口冒烟。
- MuPRO：`suan mupro submit/result/verify`、计算节点 `python -m suan.mupro run/verify/check`、
  逐次校验 `stk-mupro-1` 与本机多 rank 保护，见 [MuPRO 指南](runtime-mupro.md)。
- 工作台：控制模板 `muferro-example` 与 `--template`／`--template-file`，启动器 `--template`，
  按 MuPRO 帧名确定场名与时间步；`suan-workbench` 改为 STK 工作台启动器，Synorder 宿主改用
  `python -m suan.workbench`。
- 并行云站点清单见 [并行云站点验收清单](runtime-paratera.md)，尚未执行。

Linux / Python 3.12.14，`.[server,science,control,visualization,test]` 环境，
`python -m pytest -p no:cacheprovider -m "not desktop"`：**303 passed，2 skipped**，约 45 秒；
Python 3.10.21 同一命令结果相同。
跳过项为可选 MCP 组件未安装，以及需要 `STK_TEST_MUPRO_PREFIX` 的真实 muFerro 测试。
MuPRO 测试使用模拟的 muFerro、mpiexec 和 srun；Slurm／PBS 为模拟命令；非 Linux 行为通过修改
`sys.platform` 的测试检查，尚未在真实 Windows 或 CI 上运行。本轮没有运行多 rank MPI。

### MuPRO 本机验收

2026-09-24 04:09–04:13（UTC+8），r730xd 测试主机（`mnemora-test`，Linux x86_64，48 个逻辑 CPU），
Python 3.12.14。STK 为 `feature/independent-runtime-mupro` 分支上基于 217bd86 的未提交工作树，
以非可编辑方式安装到临时 venv。按 [MuPRO 指南](runtime-mupro.md) 的“本机验收流程”执行，
结果：**通过**，完成两次真实 muFerro 单 rank 运行。逐步记录见该指南的“结果”。

- 程序：Release 构建 muFerro（muprosdk b2adf41，SHA-256
  `c0c1f3454f5ff5384c76e70455b0441bb8ebeeb40b711b2360f2f0f1d099683a`），Release 许可检查通过，
  没有改用 muFerrod。两次运行都是 1 rank、1 线程、`launcher` 为 `none` 的 MPI singleton，
  没有启动 mpiexec 或 hydra。
- 耗时：CLI 提交 `--wait` 5.24 秒（求解器 3.02 秒）；模板任务从派发到结束 4.57 秒（求解器 2.83 秒）；
  无界面视图检查 0.89 秒；全程 279.6 秒，其中 pip 安装 246 秒。
- 校验：两次均为 `stk-mupro-1` `passed`（完成 101 步，101 行有限能量，101 条进度，30 个 16³ 场帧），
  `qoi.total_energy` 均为 −727.9144455（step 101），与不经 STK 直接运行 muFerro 的 1 rank 参考值相同。任务为
  `b19c4c0fdbbd41708acf4373e6a3f383`（CLI）与 `89213f88715844a7941a3f7601711a0c`（`muferro-example` 模板）。
- 网络：Runtime 只监听 127.0.0.1；运行期间本次运行没有其他监听。
- 幂等：同一 `--key` 返回同一任务 ID，没有新的运行目录。
- 视图：节点代理生成的 slice、等值面和向量箭头可用，slice 通过 `validate_scene`；`view.probe`
  与直接解析 DAT 的值完全相同；`energy_out.dat` 按预期被拒绝。
- 模板链路：C++ 按钮的等价命令按 `client.json` 换成 `muferro-example`，经节点代理在真实 Runtime 上
  运行成功，桥接写出的 `scene.json` 通过 `validate_scene`。
- 清理：Runtime 已停止，没有残留进程或套接字；muprosdk 工作树与许可文件元数据前后一致；
  `$A/shared` 为 31M（每次运行约 16 MB）。
- 发现两个小问题：`muferro-example` 模板没有声明 `ranks`／`threads_per_rank`，模板运行在 Runtime
  `environment.json` 中的 `MKL_NUM_THREADS` 为 null（求解器实际为 1）；以 `--port 0` 初始化时，
  停止后 `status` 的 `url` 显示端口 0。验收后均已修复：模板改为 1 rank、每 rank 1 线程，停止后
  `url` 为 `null`。

本次没有覆盖多 rank MPI、真实集群（含并行云）以及 GPU／Blender C++ 界面构建。

## 2026-09-25 里程碑 1：节点图可视化

内容：数据格式、图、渲染载荷与监控事件规范（`docs/specs/`），无界面图求值器与缓存，muFerro／SimViz
节点集与预设，离屏渲染与二维图，控制服务 blob 存储与图操作，网页“图谱”模式，MCP 工具与技能，见
[可视化工作流](visualization.md) 与 [控制服务指南](hub.md)。

自动测试：Linux，Python 3.12.14 与 3.10.21，`python -m pytest -p no:cacheprovider -m "not desktop"`，
离屏渲染子进程指向 Kitware `vtk-osmesa` 环境（`STK_RENDER_PYTHON`）：**889 passed，12 skipped**；
不设渲染子进程时渲染测试跳过。网页 `npm ci && npm run build` 通过，另有无头 Chromium 渲染与交互检查。
128³ 假 muFerro 帧上 `muferro-domains` 冷启动约 3.7 秒，仅改相机约 0.3 秒（不含 PNG）。

真实验收：2026-09-25 03:45–03:49（UTC+8，全程 204 秒），r730xd 测试主机，分支 `feature/m1-graph-viz`
提交 445e885 以非可编辑方式安装到临时 venv；Runtime、控制服务（含构建后的网页）与节点代理都只监听
127.0.0.1，单 rank。

- 经控制服务模板提交真实 Release muFerro（SDK 示例，16³，101 步），自动执行；校验 `stk-mupro-1`
  通过，总能量 −727.9144455（step 101），与 2026-09-24 的直接运行一致。
- 监控事件：经控制服务 `task.events` 读取 142 条（`metric.declare` 5、`metrics` 101、`progress` 2、
  `frame` 30 等），全部在 Runtime 标记任务结束之前到达。本例求解只有约 2.5 秒，帧事件在求解器退出时发布。
- `graph.evaluate`（`muferro-domains`，profile `web`）自动执行，所有 blob 经 sha256 校验，载荷通过
  `suan.render.payload.decode`；标签与对原始 DAT 的独立分类逐点一致，分数和为 1，能量图数据与
  `energy_out.dat` 101 行相同，离屏 PNG 1600×1200。耗时与缓存：首次 3.42 秒（13 个节点全部计算）；
  仅改视角 1.06 秒（只重算 camera、scene、png）；换步 1.48 秒；相同请求 0.34 秒（全部命中）；
  改阈值 1.38 秒（帧读取命中）。本例为单一 T[100] 畴；提高阈值后为 −1：2885、1：1211。
- 网页（无头 Chromium，127.0.0.1）：“图谱”模式运行 `muferro-domains` 约 1.0 秒显示，含图层、图例、
  分数表与能量图；手机宽度 390 px 无横向溢出；`muferro-polarization-glyphs` 显示箭头与取向图例。
  在畴表面上点击探针，返回值与原始 `Polar.00000100.dat` 的三线性插值完全一致（差 0.0）。
- MCP `graph_render` 返回的 PNG 与控制服务首次求值的 PNG 字节一致。
- 清理：各服务与进程退出，端口关闭；仓库与 muprosdk 工作树、许可文件元数据前后一致。脚本的
  `/dev/shm` 检查报出新条目，经核对属于本机同时运行的 GitHub Actions（muprosdk CI）进程，不属于本次运行。
- 第一次验收（2026-09-25 02:50，提交 626bcd1）发现两个问题并已修复后重验：畴表面平滑后超出网格
  约 0.66 格，点击表面时探针被拒且遮住外框（现已把表面顶点限制在网格内）；控制服务按字母顺序重排
  表格列（现有序列名 `column_names`，且保存结果时保持键顺序）。

未覆盖：Blender 端显示与节点编辑器、真实集群、多 rank、GPU、Windows 客户端实机、控制服务 blob 保留与回收。

## 2026-09-25 桌面里程碑 D1：自有引擎桌面端

内容：自有 C++ 桌面程序（`desktop/`，Blender GHOST + GPU + BLF）的任务、传输、日志编辑器（WP9）与
查看器、属性、探针编辑器（WP10），经 Python 桥（`suan.desktop_bridge`）连接控制服务与 Runtime，见
[桌面程序说明](../desktop/README.md) 与对照清单 `desktop/docs/parity-*.md`。

真实验收：2026-09-25 21:11–21:32（UTC+8），r730xd 测试主机（`mnemora-test`）。分支
`feature/desktop-engine` 提交 dedae97；验收中发现的查看器问题已修复为 19f94ec（见下文问题 1），
任务部分在 dedae97 的构建上运行，查看器部分在含 19f94ec 的构建上运行。STK 以非可编辑方式安装到临时
venv（Python 3.12.14，pip 74 秒），桥使用该安装而不是源码树；桌面程序在 `~/opt/stk-build/d1acc`
以 RelWithDebInfo 构建（约 3.6 分钟，用户 sysroot）。Runtime（并发 1）、控制服务
（`suan-control serve --review-policy not-self --template muferro-example`）与节点代理都只监听
127.0.0.1；桌面程序用 `suan-control pair --role client --profile desktop` 的配对码，经“配对控制服务”
（`connections.pair_hub`）配对，配对码只存于 0600 文件，未打印。

驱动方式：临时驱动程序（草稿目录，不入库）按 `stk-desktop` 的 `run_gui` 装配应用外壳、默认布局、
任务状态钩子与真实 Python 桥，像 `desktop/tests/app/*_live.cc` 一样合成鼠标、键盘与输入法事件
（点击“提交任务”“在查看器中打开”、任务名输入框，在视图中点击拾取）；显示服务器为
`desktop/tests/wm/run_with_display.py` 启动的私有 weston（headless，pixman，自带 `XDG_RUNTIME_DIR`）
与 Xvfb（`-nolisten tcp`），只用 unix 套接字。weston 上用 Vulkan（lavapipe），Xvfb 上用 OpenGL（llvmpipe）。
结果：**通过**（问题 1 修复后）。

- 连接：配对后 `hub.policy` 报告设备类型 `desktop`、审核策略 `not-self`、桌面自动执行上限 256 MiB；
  节点在线，模板列表含 `muferro-example`。
- 任务（weston，Wayland）：点击“提交任务”提交 `muferro-example` 模板，自动执行，0.46 秒登记任务；
  任务表依次显示运行中、成功（2 秒一次的快照共 4 个）；日志视图收到 93 行，第一行比任务结束的快照早
  7.3 秒到达（运行期间）；监控事件 142 条（帧 30、指标 5），校验 `passed`。从登记到完成 4.3 秒
  （Runtime 记录），其中 muFerro 约 3.2 秒。
- 下载：制品 36 个，共 15.9 MB。“另存为” `energy_out.dat`（11220 字节）0.05 秒完成，桥的 sha256 与磁盘
  复核都通过，文件 sha256 与 Runtime 运行目录中的原文件、制品列表中的值三者一致（`1d8c3586…`），101 行，
  末行总能量 −727.9144455。整个运行目录（36 个文件）下载到本地目录用时 1.8 秒，逐个与 Runtime 的
  `work` 目录逐字节一致，供下面的本地求值使用。
- 校验：两次模板运行的 `suan mupro result` 均为 `stk-mupro-1` `passed`，总能量 −727.9144455（step 101），
  与 2026-09-24 与 M1 的记录一致；16³、101 步、30 个场帧，1 rank、1 线程、`launcher` 为 `none`；
  muFerro 程序 SHA-256 仍为 `c0c1f345…`（muprosdk 已更新到 0d6e021，Release 安装未变）。
- 自定义命令与复核：在任务名输入框中用输入法事件输入“铁电畴 验收 D1”（两段拼音预编辑，内联显示后提交，
  再用按键输入“ D1”），提交自定义命令后进入复核（“新命令或模板变更：请检查完整参数后批准执行。”）。
  本机检查请求后自行批准被控制服务拒绝（403），界面按 `review_policy` 显示“控制服务的审核策略（not-self）
  不允许本设备批准该操作，请由控制服务所有者批准。”；所有者令牌批准后，桌面程序以同一幂等键重发，
  0.52 秒得到任务并成功运行。Runtime 任务记录的 `spec.name` 为“铁电畴 验收 D1”。
- 关闭不停止任务：第二次模板运行处于运行中时关闭窗口，桥收到 EOF；该任务在窗口关闭后 0.55 秒完成，
  `succeeded`，`cancel_requested` 为 false，校验通过、能量相同。本例求解只有约 3 秒，所以关闭距完成很近。
  每次退出都没有 guardedalloc 泄漏，外壳已丢弃关闭窗口的屏幕。
- 查看器（weston，冷缓存：清空节点图缓存与桥的 blob、图缓存，关闭相邻步预取）：点击“在查看器中打开”，
  `muferro-domains` 经控制服务**自动执行、无复核**，求值 1.63 秒（10 个节点，数据节点 4 个），打开到画面
  1.78 秒，3068 个三角形、78 KiB。导出 PNG（1600×1200，彩色畴占 40%）0.30 秒。
- 探针：视图中心落在外框上，第二个候选点拾取到畴表面（`surface_layer`，单元 2143），经 `view.probe`
  0.31 秒返回：位置 (14.970, 0.0591, 12.428)，值 (0.6020874395, 0.0020565348, 0.0094302832)，与独立解析原始
  `Polar.00000100.dat` 的三线性插值完全一致（差 0.0）；探针编辑器显示 0.602087。
- 客户端阶段参数：`view` 由 iso 改为 +x，只重算 `camera`、`scene`，**数据节点 0 个**，0.16 秒，视图 65% 的
  像素改变。
- 换步（共 0、100 两步）：未缓存的 100→0 经控制服务求值 589 毫秒（重算 7 个节点，3 个命中）；回到 100
  和再到 0 用查看器缓存，0.4 与 1.7 毫秒（到下一帧约 40 毫秒）。开启预取的另一轮中，三次换步都已预取，
  0.3–0.5 毫秒。
- 本地求值：打开下载到本地的运行目录（本地模式），`muferro-domains` 0.76 秒（10 个节点）；在同一位置
  拾取畴表面，本地探针值与经控制服务的值及原始 DAT 三线性插值都一致（差 0.0）。
- X11（Xvfb，OpenGL）：查看器全流程同样通过（两处探针差 0.0，PNG 1600×1200）；输入法事件输入
  “畴壁 Xvfb 验收”（拼音、按键、拼音混合）的自定义命令经所有者批准后运行，Runtime 记录中名称一致。
- 回归：修复后 `ctest -L "app|jobs"` 72 项全部通过（`STK_BRIDGE_TEST_PYTHON` 指向验收 venv，无跳过）。
- 网络与清理：本次只有 Runtime 127.0.0.1:28686 和控制服务 127.0.0.1:22883 两个服务监听，0.5 秒采样
  （1899 次）中本次进程的监听另有回归测试临时 Runtime 的 127.0.0.1:38425；显示服务器不监听 TCP。结束后
  没有残留进程或监听，两个端口关闭；仓库工作树、muprosdk 工作树与 HEAD、Release 可执行文件和许可文件的
  元数据前后一致。`/dev/shm` 新增 770 个 `__KMP_REGISTERED_LIB_*`，没有一个属于本次运行的进程 PID，是本机
  同时运行的其他 Intel OpenMP 作业（期间还看到其他用户的 muPREDICT／hydra 监听 0.0.0.0:40915）。

发现的问题：

1. **已修复（19f94ec）**：查看器经控制服务求值时没有设置 `budget.max_output_bytes`，控制服务按 desktop
   配置默认的 2 GiB 估计传输量，桌面自动执行不生效：`graph.evaluate` 进入复核（“预计传输超过桌面自动执行
   上限 256 MiB（请设置 budget.max_output_bytes）”），查看器显示“计算超过自动执行额度，正在等待复核；
   批准后请重新计算”。桥规范 §7.1 要求应用按 `hub.policy` 设置；现在 `ViewerState` 对控制服务来源按
   任务编辑器当前连接的策略设置该上限。
2. **未修复**：经控制服务新建工作区后，新工作区不会出现或被选中。`JobsState::create_workspace` 的回调只
   调用一次 `refresh_workspaces()`，而经控制服务的 `workspace.list` 读取节点心跳快照（每 3 秒一次），此时还
   没有新工作区；`apply_workspaces` 在首选工作区不在列表中时改选列表中的第一个。第一次尝试（此前没有
   工作区）60 秒内都没有可选的工作区；正式运行中新建的同名 “d1-accept” 没有被选中，界面改选了上一次
   尝试建立的工作区，之后的任务都提交到了旧工作区，没有提示。需要手动“刷新”。
3. **次要**：任务表“提交时间”直接截取 Runtime 的 UTC 时间字符串（`short_time`），显示 13:19 而本地为
   21:19，也没有时区标记；探针编辑器的插值说明显示为“原始点数据的trilinear插值”（方法名未本地化）。
4. **环境**：weston headless（pixman）上 OpenGL 后端无法启动（`EGL_BAD_MATCH` 后 Wayland 连接断开），
   与 ctest 在 weston 上用 Vulkan 一致；窗口请求 1440×900 而 kiosk 输出为 1280×800 时，程序按请求尺寸
   提交缓冲区而不是按全屏 configure 的尺寸，weston 断开连接，改用 1280×800 后正常。

未覆盖：交互式输入法（weston 不实现 text-input-v3，以上是合成的预编辑／提交事件；GNOME + ibus、
KDE + fcitx5 需人工验收）、macOS 交互（Metal、拼音输入法、Retina）、Windows 客户端实机运行、
真实集群（并行云）、多 rank MPI、真实 GNOME 会话的客户端装饰，以及经 HTTPS 入口访问控制服务。

<a id="desktop-mac-windows-smoke"></a>

## 2026-09-28 补充记录：macOS / Windows 基本启动

来源：所有者在本轮对话反馈“我在 windows 和 mac 上都测试了，能够正常打开界面，看到 3d 渲染”。
据此记录两个平台的真实窗口启动与基本 3D 显示通过；[快速启动脚本](../desktop/QUICKSTART.md)已在主线提供。
具体测试提交、系统版本、硬件、操作步骤和日志未随反馈提供，本条属于用户报告的验收证据。

这补充了 D1 记录中的平台启动覆盖；不代表 macOS / Windows 的输入法、Retina/缩放、全部交互、
大数据、结果导出或安装包已经验收，也不表示此前 CI 失败已修复。后续范围见[开发计划](development-plan.md)。

## 2026-09-28：P0 测试稳定性与 P1 项目存储基础

新增 `suan/project` 和 `suan project create/show/apply/history`，实现独立于 Runtime 的 SQLite 项目存储。
支持稳定 UUID、类型化字面量表格、批次事务、修订冲突与编辑历史；使用范围见[项目存储指南](project.md)。
当前尚未接入桌面项目生命周期，也未实现引用/公式、撤销、资源快照或模拟执行。

本机 Linux 验证：

- 项目、打包、图 worker 与实时图缓存相关测试共 **55 passed，1 skipped**；跳过的是未安装的 MCP 可选组件。
  其中项目测试 28 项，覆盖重开、改名后稳定身份、类型错误整批回滚、并发修订冲突、跨表外键、
  拒绝覆盖已有数据库，以及拒绝未知/损坏/不支持格式的项目。
- 快速启动脚本测试 **13 passed，1 skipped**；Windows PowerShell 集成项在 Linux 跳过。
- 重编译 `stk_app_viewer_gpu_tests`，`app_viewer_python_vulkan` 与 `app_viewer_python_opengl` 均通过。
- 构建 sdist 并从中构建 wheel；在无 NumPy/VTK/Qt/MCP 的全新虚拟环境安装 wheel，
  从源码目录外完成中文/空格路径项目创建、编辑、重开、历史查询与陈旧修订拒绝；未初始化 Runtime。

Windows 退出测试现在处理 `is_running()` 与 `status()` 之间进程退出的情况，保留退出超时断言。
查看器阶段缓存测试先关闭邻帧预取，再分别验证阶段缓存和预取换步：活动预取可能在原生计算中被硬取消，
导致 worker 重启及内存缓存丢失，不能将这一情况等同于客户端参数使数据失效。
本次修改没有放宽阶段缓存断言，也没有改变生产取消策略；原有 worker 取消/重启测试继续通过。
本条是 Linux 本地验证，修改后 macOS Metal 与 Windows 实际结果仍以对应提交 CI/真机记录为准。

## 2026-09-28：本机项目桥接

桌面桥 v1 的新增项目接口和 C++ 客户端使用同一修订式存储服务；协议见 §13。
本机 Linux 验证：

- `test_project.py` 与 `test_desktop_bridge*.py` 共 **72 passed**，包含进程重启后句柄失效、
  关闭与已接受编辑串行、外部修改冲突、未知格式错误码和数据库被替换后的身份检查。
- `stk-bridge-tests` 编译通过。`bridge` 标签首次 60 项中 59 项通过（包括 Vulkan/OpenGL 查看器），
  新增项目测试的断言误将 JSON 对象成员顺序作为差异；改为语义比较后该测试通过。
  另增并通过跨平台 CPU schema/类型测试，覆盖 Windows 绝对路径和 64 位修订。
- 上一存储基础提交 `b73c254` 的桌面 CI 已通过 Linux、macOS、Windows（GitHub run 36359876426）；
  本次新增接口的跨平台结果需等待本次提交的 CI。本条不代表原生项目编辑器已交付。
- 文档站构建的既有失败另行跟踪：run 36374828915 使用 Node 18，Astro 语言服务依赖加载出现
  `ERR_REQUIRE_ESM`；运行时/科学工作流检查通过。不能将仓库全部 CI 记为通过。

## 2026-09-28：原生项目表格首版

新增共享 `ProjectState`、类型化表格模型和“文件 → 项目表格”入口。
界面可创建/打开项目、添加表/字段/记录、编辑字面量、保存后关闭重开。
桥重启按目录和 UUID 恢复；旧修订草稿不会覆盖外部修改。

本机 Linux 验证：

- 构建 `stk-desktop`、`stk-project-tests`、`stk-project-render`、`stk_wm_tests` 通过。
- 最终相关 CTest **31/31 通过**：9 项项目模型/界面/真实 Python 桥测试，
  4 项真实项目桥 → 原生 GPU 截图（中/英文 × Vulkan/OpenGL），18 项应用外壳回归。
  另一次布局回归中的 25 项通用布局通过；最初的 Jobs 布局目标未重新链接，后续 CI 暴露的差异见下条。
- 目视检查中英文截图，确认字段、单位、行选择、单元格编辑区和保存按钮显示正常；
  截图由 `stk-project-render` 生成在构建目录 `tests/app/out/project_*.png`，不是手工画的设计稿。
- 中英文字典各 695 项，`check_i18n.py` 通过；本次尚无 macOS/Windows 真机交互结论。
- 前一桥接提交 `b1e2724` 的全部桌面 CI 已通过（run 36376573973），包含两平台构建及 Linux 包冒烟。

本版共享表格支持基础字面量，不包含引用/表达式、删除、批量粘贴、富内容插件、AI 或 Python 控制台。
完整程序重启后需手动打开项目；编辑器内未保存草稿不写入数据库。测试步骤见[项目指南](project.md)。

## 2026-09-28：英文编辑器标签回归修正

`c537d55` 的 CI 显示，英文 `Project tables` 比原有最长编辑器名更宽，导致所有区域的编辑器下拉框
变宽，使 5 个 Linux 英文布局快照和 3 个 macOS 英文布局快照失败。项目功能测试通过。
英文短标签改为 `Project`，中文仍为“项目表格”；不更新旧快照来掩盖其他区域的布局变化。

修正后本机重新构建全部桌面目标，完整 CTest **427/427 通过、无跳过**，包含此前失败的默认外壳、
Jobs、Properties 英文布局，真实 Python 桥、Vulkan/OpenGL、X11/Wayland 和打包检查。
中英文字典检查通过。macOS/Windows 修正后的结果继续跟踪对应 CI。

## 覆盖范围

2026-09-28 原生 Python 面板：全量重编译后完整桌面 CTest **440/440 通过、无跳过**。
新增 5 项 `ScriptPython` 使用真实独立 worker 验证布局拆分/恢复、非法布局原子拒绝、当前项目修订共享、
中断/重启不重放、过期客户端的排队操作不执行、多行按钮/快捷键和恢复/拖入不自动执行。
4 项 `python_render_*` 通过 Vulkan/OpenGL 生成中英文截图，已目视检查输出、代码缩进和控件位置。
多行输入覆盖 UTF-8 选区、跨行导航、CRLF 粘贴、撤销、IME caret、滚动和提交；最终 Ctrl+Tab 焦点处理
变更后相关 TextArea/TextEdit/TextField **11/11 再次通过**。中英文字典各 719 项，检查通过。
Python 文件语义回归 **8/8 通过**（含 main guard、同目录导入、argv 和 cwd）。

跨平台状态：后端提交 `4d3b762` 的 run 36380377730 在 Linux/macOS/打包通过，Windows **238 项 CPU
测试通过**，但必跑检查使用相对 JUnit 路径而失败。改为 PowerShell `Join-Path $PWD` 的绝对路径；
新原生面板的 macOS/Windows CI 与真机交互结论仍待后续验证，不能用 Linux 截图替代。

2026-09-28 Python 后端：`test_desktop_scripts.py`、`test_desktop_graph_worker.py`、
`test_desktop_bridge_projects.py`、`test_desktop_bridge.py` 共 **52 项通过**；包含真实独立 worker 的
多行/文件执行、变量保留、输出环截断、协议隔离、项目冲突和通知、中断子进程树、崩溃恢复、
反向请求会话匹配/超时/取消。重新构建 `stk-bridge-tests` 后，相关 Schema/Types/Retry CTest
**13/13 通过**，验证 C++ 也拒绝双重源码入口、重复能力和同时携带结果/错误的回复。
这是后端与协议验收；尚不表示原生控制台交互或跨平台真机验收已完成。

2026-09-28 传输恢复补充：Runtime CI run 36378576449 暴露失败通知与 worker 退出之间的窗口。
`resume` 现在在管理锁外等待终态 worker 收尾，然后在锁内重新读取状态；同时到达的恢复请求
不会启动两个 worker，活动/已完成的传输仍保持幂等。收尾超过 5 秒返回可重试 `busy`。
本机 `test_desktop_transfer_lifecycle.py`、`test_hub_desktop_bridge.py` 和
`test_desktop_bridge_runtime.py` 共 **23 项通过**；新增测试用事件门控制时序，不依赖 sleep。

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

- 真实 PBS / Slurm 集群（首个站点为并行云，账号待开通）、集群上的 MuPRO 可执行程序与许可、
  多 rank MPI / module 环境、共享文件系统、队列和站点资源策略；本次调度器测试为协议模拟，
  不是实际集群性能验证。MuPRO 目前只在本机完成单 rank 验收（见上）。
- 真实 SSH 网络断线／重连；本次已验证客户端重建和服务端任务寿命独立，
  未对外部服务器执行 SSH 测试。
- Windows / macOS 客户端完整交互、输入法与分发验收；基本窗口启动和 3D 显示已有上述用户反馈。
  服务器端仍只支持 Linux；此前 Linux 自动验收不能替代客户端真机完整验收。
- PyInstaller 冻结桌面二进制的多进程启动与 Python 解释器分发；当前验收发布物
  为 Python wheel / sdist，未发布到 PyPI 或创建远程 release。

远程 Python 会话、远程实时三维渲染和团队权限属于后续阶段。

安装、API、SSH 与真实集群验收命令见 [runtime 使用指南](runtime.md)。
