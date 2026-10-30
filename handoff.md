# STK 当前交接

更新：2026-10-30（本地 2026-10-29）。03:03 UTC 已按所有者要求写入交接；随后活动目标续行，完成精确回归、平台修正及以下本机验证。下列Git表是源码59f4cdc3提交后的交付快照，随后记录/认知提交及推送状态以真实Git和收尾证据为准。历史交付与失败证据见
[开发日志](docs/development-log.md)、[运行验收](docs/runtime-validation.md)；路线图见[开发计划](docs/development-plan.md)。
开始前读取 [AGENTS.md](AGENTS.md)，核对真实 Git／CI，保护未提交修改。发布契约优先于设计目标。

## 接手时先读：未完成交付，保护工作树

持续目标仍是完成 `docs/development-plan.md` 的主要通用能力；PET 新专项后置。当前停在 **S4 前置的项目编辑回执与崩溃恢复**，还没有 peer 端点或 Flower 训练实现。

| Git 位置 | 交接时真实状态 |
|---|---|
| 分支 | `main`，本地领先远端 5 提交；另有下述未提交文件 |
| 远端 main | `70449dc15ed0635014f8bc66924bc7af123f0a8a`，S3 记录及认知收尾；已通过 GitHub API 核实 |
| 本地源码提交 | `e5cea387f048f937eb643a69bba11d81363d83d3`，Hub 上传原请求幂等身份修复；未推送 |
| Hub 记录提交 | `9d4e20f737dc81b1789ec3681872d3d92c367637`，上述 Hub 修复的记录和 AOCI；未推送 |
| 平台修正 | Windows 发现修正 `e0139d9f50a6abd5a9e4129c9d00f107bbf6b11f`；Mac 有界诊断 `04aab01c00400110a866cc0c13faba9ba7813477`，均未推送 |
| 当前 HEAD | 格式15源码 `59f4cdc3e7bc9ca7c29a3bc75621b0152a3b377e`，已本地提交，尚未推送 |
| 随后记录 | 四份状态文档与AOCI托管资产同批收尾；不要覆盖其他Agent新产生的修改 |

格式15生产源、测试和记录已达到本批交付状态。最终Python4034通过/31跳过/2排除，最终原生2022/2022、零失败/错误/跳过，当前必跑1546项匹配通过。新业务候选独立安装96/96。所有本批已知编译、pytest、打包/必跑进程均已终态，不接续或重启旧session；原生首轮两夹具失败的原日志保留。实际发行与AOCI收尾绑定见 `EDIT_EVIDENCE/delivery-closure-summary.json`，新平台CI仍须核对。

## 已核实 CI：先处理平台失败

2026-10-30 03:02:43 UTC，[Desktop 40973399539](https://github.com/sijintech/stk/actions/runs/40973399539) 已结束，**failure**，对应远端 `70449dc`，不包含本地 Hub 和格式 15 改动。

| Job | 结果 | 已核实边界 |
|---|---|---|
| Windows CPU `123795443006` | failure | 第 9 步 `Build (every target)`，可执行文件已链接，GoogleTest 多值 LABELS 破坏发现命令及后续属性；本机已修，实际 Windows 待新 CI |
| macOS `123795443025` | failure | 编译、CPU、Metal 已过；Markdown/HTML/PDF 各 20 轮、140/140/160 张 OS 图通过；两个视频在播放后 Pause 附近失败，各 0 完整轮/0 验收图，根因仍待精确诊断 |
| Windows native `123806568349` | skipped | 上游构建失败，未执行，不能算原生验收 |
| Linux 主回归 `123795443078` | success | 远端头范围 |
| Linux 包 `123795442762` | success | 远端头范围 |
| Linux 干净机 smoke `123798196412` | success | 远端头范围 |

[Runtime 40973399517](https://github.com/sijintech/stk/actions/runs/40973399517) **8/8 success**，Docs `40973399507`、Secret `40973399529` success。以前“仍在跑”的记录已经过期。前代码头 Desktop 的等待门已满足，但平台失败仍须修复并在新头验证；不降低原生截图/必跑门禁，不因观察超时取消或重复 CI。P4 文档与视频候选继续默认关闭。

最新 Desktop 快照：`/home/mnemora/.local/state/stk-validation/s4-foundation-20261029/p4-ci-70449/status-20261030T030243Z.json`，SHA-256 `aec5a004eec32f2fd720fa9e26a3f599f8eb3b94bfaa5efd1c60f3e7249bc348`。后续先看精确失败步骤和对应 artifact，不用旧零轮/零图记录猜本次根因。

后续取证在同根 `windows-build/`、`macos-native/`：Windows `materials.cmake` 已将双标签移到发现后的 `TEST_INCLUDE_FILES`，CMake 3.31.6/4.2.3 元数据均核对 22 项双标签、120 秒、空 key/model unset，CPU 标签选择覆盖 22/22。Mac artifact `12943950957` 的 339193673 字节 ZIP SHA `cd138c07427e81fd7dc602475fbdb898da3600b8f43d43db71bfb0140d95356f` 与 GitHub API digest 一致；440 张已记录图片均核 SHA，三格式最终图已目视，Viewer/草稿保留。`artifact-evidence-summary.json` 记录范围。视频实际完成初始暂停保持和一次显式播放，不能再描述为首个 probe 就失败。Cocoa 源码只增加固定原因/布尔状态诊断，原身份门禁未动，未声称暂停缺陷已修复。

## 本地源码已提交：已写到哪里

### 格式 15 与原子项目编辑回执

- 核心入口：`suan/project/edit_operations.py`（新）、`suan/project/store.py`；规范 `docs/specs/project-edit-operations-1.md`（新）；核心测试 `tests/test_project_edit_operations.py`（新）。
- 新表 `project_edit_operations` 与业务修改、revision、history、undo delta 在同一 `BEGIN IMMEDIATE` 中提交。显式 `operation_id`（规范 UUID）与原始请求绑定；同项目/scope/ID 的相同原请求先返回历史成功回执，再考虑当前 CAS，异请求冲突。失败全回滚，undo/redo 不释放已用 ID。
- `store.edit_operations.apply_once(commands, operation_id=..., expected_revision=..., scope="local")` 返回 `{receipt, replayed}`；`get` 只读回执。原请求在生成对象 ID/规范化命令之前哈希。请求 256 KiB/1000 命令、回执 512 KiB、项目总计 10000 回执/64 MiB，达到限额不清除旧身份。
- 新建项目格式 15，1–14 可读；两个新 API 必须显式升级到 15。升级先验证原库备份、一次事务增加修订，不隐式升级。14 的既有发布契约不被改写。
- 桥：`suan/desktop_bridge/projects.py`、`server.py`，新增 `project.edit_operations.apply_once/get`；只接受本地 handle，scope 固定 `local`，首个成功才发一次 `project.changed`。脚本入口 `p.edit_operations`；级别表已同步，未扩大智能体工具权限。
- Schema：`suan/contracts/schemas/desktop-bridge-1.schema.json`，严格回执及方法；已修真实升级历史枚举范围（from 1–14/to 2–15）。桥测试 `tests/test_desktop_bridge_edit_operations.py`（新）。`docs/project.md`、`docs/scripting.md`、桥规范和规范目录已更新。
- 原生兼容：`desktop/engine/lib/stk_app/include/stk/app/project_state.hh`、`desktop/tests/app/table_workbench_state_test.cc`、`desktop/tests/bridge/test_client_python.cc`。新增真实桥重启测试 `PythonBridge.ProjectEditOperationReceiptSurvivesRetryAndBridgeRestart`，已编译，并在首轮完整原生中实际通过。
- 旧格式测试夹具仅在模拟降级前移除新表；`suan/workflows/pet_study.py` 仅增加格式 15 兼容、测试改为拒绝未来 16，没有新增 PET 业务。

### 最后修复的真实 SQLite 热日志问题

此前小事务崩溃测试未触发实际脏页落盘。独立探针使用 800 条合法命令、138558 字节请求、`cache_size=5/cache_spill=ON`，在提交前 `os._exit`，真实产生 hot journal；原 `mode=ro` 重开失败，SQLite 扩展错误码为 776。

现有修复只在读取连接首次身份检查、尚未 yield 给调用方、精确 776 时尝试一次：核验普通文件及 100 字节 SQLite/STKP header、检查文件身份，使用已有文件 `mode=rw + query_only=ON` 交给 SQLite 做物理恢复，关闭后重新 `mode=ro` 读取。没有业务重放、逻辑编辑、修订增加、回执插入、升级、改权限或手工删除 journal；需要可写访问及恢复锁。普通 READONLY/CORRUPT/CANTOPEN、调用方/提交阶段异常不触发重试。

独立审查指出的“恢复连接关闭后最后 lstat 的 OSError 未归一化”已经修入当前源码，随后已补精准故障注入 `test_final_lstat_failure_after_recovery_close_is_normalized_without_retrying`：真实恢复连接关闭后令该次 lstat 抛 PermissionError，明确转为 ProjectError，不重试读或业务编辑，恢复 baseline/零修订/无回执。最终核心 3.12 **78/78**，3.11/3.14 恢复相关各 **15/15**；`final-lstat-py{312,311,314}.{xml,log,json}`，四拥有文件前后 SHA 一致。

当前稳定摘要（接手时重新核对）：

| 文件 | SHA-256 |
|---|---|
| `suan/project/store.py` | `f66bb91845f3556603b5639b0d9cca84bca26ac32759a57cf787cb25a3af9688` |
| `suan/project/edit_operations.py` | `e13f55f26d1db18a6dc5c2be96c99a325a20fdd43d71ce7d622f76d56c224e6c` |
| `tests/test_project_edit_operations.py` | `83c0a64fa6a92168591048d063c88548cbd2ea8cb8d93713f7c29715822ad154` |
| `docs/specs/project-edit-operations-1.md` | `1ab335b0134352c27c940bd04ff9ec2838c2886d26d2a2bff148a914ed8b4f0b` |
| 桥 Schema | `dafc6b3600d170283e0a63ed11423ce8cc74d3db2bf8607a22f84f2f3665a1ad` |

## 测试与安装证据：哪些仍需补跑

本机证据根，下文简称 `EDIT_EVIDENCE`：
`/home/mnemora/.local/state/stk-validation/s4-foundation-20261029/edit-operations/`。

| 证据 | 实际结果与范围 |
|---|---|
| `final-lstat-py312/311/314.xml` | 最新 3.12 核心 **78/78**、3.11/3.14 恢复各 **15/15**，零跳过，包含最后 lstat 精准故障注入 |
| `recovery-final.xml/log/summary.json` | **77/77**、零失败/错误/跳过；pytest 约 2.26 秒，四拥有文件前后 SHA 一致，包含最终热日志修复 |
| `core-spill-probe/run-e23cf2fcce074bb0b58b62e0a9c73ffe/summary.json` | 最终源码真实 spill 后正常重开：数据库字节回到 baseline、revision/table/history 均 0、无回执；提交后退出对照为 revision 1/800 表/1 history/回执可读 |
| `bridge-summary.json` | Python 3.12 扩大 **54/54**；3.11/3.14 各 **18/18**，零跳过；包含 Schema 补修，发生在最终热日志修复前 |
| `native-final-build-summary.json` | 最终 Schema 后增量全目标编译退出 0、49.256 秒、编译输入稳定；这是首轮原生执行前的构建证据，不代表本批最终测试结果。此前 515.404 秒构建期间 Schema 有变化，不冒称那次冻结验收 |
| `python-full.xml/log/summary.json` | **4019 passed/31 skipped/2 deselected**，约 760 秒；`source_stable=false`，期间落入恢复修复，**不能算最终冻结全量**；现已另跑最终4034通过且源码稳定，保留此旧证据 |
| `compat-pet-final-summary.json` | 格式兼容定向 5/5、源码稳定；首次兼容回归的旧未来版本断言失败已保留 |
| `package-check/business-candidate-summary.json` | **旧候选**离线构建、独立环境安装，核心 63+桥 18＝81/81；471 份安装 py/Schema 一致，真实桥与 worker 从安装目录导入。**不包含后来热日志修复，不能作为最终包证据** |
| `package-check/recovery-business-candidate-summary.json` | **新业务候选**独立安装，78 核心+18 桥＝**96/96**，零跳过；471 份安装 py/Schema、真实桥 111 模块及 worker 9 模块来源核对通过；764 源文件构建/验证期间稳定，尚非最终状态文档包 |
| `platform-final-build-summary.json` | Windows CMake 修正后唯一增量全目标构建退出 0、17.066 秒、输入稳定；Linux 不编译 Cocoa，不冒称 macOS 诊断已编译 |
| `final-python-full-*` | **4034通过/31跳过/2排除**、779.39秒、零失败、1项既有Starlette提示；source_stable=true，覆盖最终Python源 |
| `final-native-full-*` | 首轮 **2020/2022**、486.74秒、2失败/零跳过、源码稳定；两个旧格式升级夹具已修，原失败证据保留 |
| `verified-native-full-*`、`required-current-summary.json` | 最终 **2022/2022**、零失败/错误/跳过、483.82秒（wrapper483.895）、源码稳定；当前全部必跑规则退出0，**1546项匹配**，25.256秒；含新增真实桥回执/重启用例 |

旧候选 wheel SHA `851f6606e74ec45cb5f7a380b4cbd9d57bb37ff4893d192f5ccddc2165edba3a`；sdist SHA `23a12d33d3a2bdf597458211c11b09d161047ac18724ff5e279c3786fb79edfc`。原文件保留于 `EDIT_EVIDENCE/package-check/business-candidate-dist/`，不要覆盖后声称原结果验证了新包。

新 96 项候选在 `EDIT_EVIDENCE/package-check/recovery-business-candidate/recovery-business-candidate-dist/`：wheel SHA `2f5bcd74cf1a1c7a98c15ffc11773094f4c5198531b2c1d9ecc4b34b5a788268`，sdist SHA `b39ccf0eb8a1b7c310d5140fbef88a011632625d706506dec637a2b1d6d69aac`。此后只补了项目物理恢复说明和状态文档；最终文档版由`package-check/final-summary.json`的全成员比对绑定此96项候选，不把比对描述为额外安装测试。

Hub 已提交修复证据另在 `/home/mnemora/.local/state/stk-validation/s4-foundation-20261029/hub-idempotency/`：3.12 相关 **49/49**、3.11/3.14 各 **23/23**，真实 Hub 分块失败、重启、继续、批准仅导入一次；预算临时变量改为 `import_request`，原请求身份保留。旧错误 journal 没有原请求，仍按 transfer ID 查询/恢复，不猜写。此处没有待实现的 Hub 修补。

S3 已推送批次的证据根 `/home/mnemora/.local/state/stk-validation/s3-training-20261029/`：最终原生 **2021/2021**、零跳过、481.20 秒；Linux 必跑 413 次/1545 匹配；完整 Python 3911 通过后补修另 83 项、离屏补验 15 项；隔离安装业务候选 198/198。它们属于上一批，不能作格式 15 的测试结果。

## 下一 Agent 的执行顺序

1. 读本文件、AGENTS、开发计划开头和真实 Git/CI；按实时 AOCI 合同建立本 Run 认知。保留全部未提交业务文件，先审查 diff 与上面的最终摘要。
2. Windows 构建发现命令已修且本机元数据正确，待新 CI 实测。Mac 视频有界诊断待新头，保持截图、循环次数、几何与 required-test 门禁；不把原生 skipped 当成功。
3. 格式 15 核心/桥及热日志边界已完成本机定向和安装候选；最后 lstat 精准回归及 `docs/project.md` 物理恢复说明均已补，不重复这些已完成工作。
4. 本批Python4034、最终原生2022、当前必跑1546匹配及安装96项均已完成。不要把它们继续列为待跑；只有新改动、失败或未解决关注点才追加相应验证。所有本批旧句柄均已终态。
5. 发行证据核对`package-check/final-summary.json`和`delivery-closure-summary.json`，最终包业务字节须等于已测96项候选，只允许明确交付文档差异。保留旧81项和新96项原始产物与日志；记录缺失时不宣称最终包通过。
6. 本批四份状态文档及AOCI收尾的机器证据见`delivery-closure-summary.json`；后续每批仍须最终稳定后维护全部候选、处理完remaining，并Verify/Check/Guide。提交前用`.gitleaks.toml`扫暂存，本机已有gitleaks 8.30.1：`/home/mnemora/.local/state/stk-validation/latex-20261029/tools/gitleaks`。默认直接 main 提交/推送，记录实际新 CI。前头等待条件目前已满足，推送前仍复查。
7. 完成这批基础后继续开发计划第 5–8 项和 P4 平台缺口；不得据回执功能就标记 S4 完成。

### 后续通用开发范围与实现边界

- **第 5 项 / S4**：独立 STK peer 端点、配对、加密和能力协商、每 peer/项目授权与撤销、单主 SQLite 写入及修订冲突、分块校验/断点传输、网络自检；随后隔离 Flower 环境做多 Linux 模拟节点多轮训练，公网 hub 不安装 flwr。Mac↔Windows 真机连接与 Flower 模拟验收分别记录。
- 不把现有 loopback/stdio 桥暴露上网：`Bridge.hello` 会恢复传输/启动本机模型并返回路径/PID，不能直接作为 peer hello；`ProjectSessions.open` 接受本机绝对路径，远端必须以授权 project ID 映射，不能接收目录或本地 handle。回执 scope 必须绑定稳定认证身份与数据库 generation，备份恢复会回退回执集，不能承诺丢失权威状态后的全局 exactly-once。
- WebRTC 仅完成上游调研，**没有安装或网络测试通过**。候选是可选 CPU helper/SDK 的 `libdatachannel + libnice`，须显式构建 `USE_NICE=ON`；默认 libjuice 与上游默认 CI 不证明 ICE-TCP。`aiortc`/`aioice` 的 UDP 候选及 TURN TCP 不等于直连 ICE-TCP，不得据此满足全部 TCP/443/NAT 需求。实现前核当前上游版本及许可/包依赖，实际记录 IPv6、UDP、TCP、relay 选路；未验证的穿透能力不承诺。
- **第 6 项 / S5**：本地 PDF 解析、两层检索、可核对引用和授权共享会话；先公开/自有资料，结构化内容共享须显式批准，不自动公开项目数据。
- **第 7 项 / S6**：文献参数→冻结流程→明确运行→数值/曲线比较→带来源报告，缺参、失败与不确定度保留。
- **第 8 项 / P5/S7**：干净机离线包/Python、文件对话框、IME/DPI/快捷键/恢复/性能、模型更新回退、`toolkits/` 按职责迁入 `suan/` 并保护兼容导入和发行包；通用引擎整理、执行目标及 ABACUS 按依赖推进。
- PET 新专项、合作数据格式、电场扫描、S2c 权限及分析修改提案均保持后文既有优先级/待决定边界。

### AOCI 续接

Hub提交前上一稳定索引已对齐；本批最终维护结果、Verify/Check/Guide及Recovery事实以收尾机器证据和接手时实际状态为准，不从旧收据推定当前治理状态。本交接不保存正式 Whole-Index、Header、Entry 或 Challenge/Attestation 正文。

本 Run 压缩后的新完整 Overview 只接收了 1/23 块（工具报告约 156800 tokens），未完成交付与 Attestation；没有据此声称当前完整系统认知可靠。新 Agent 不复用这条链或历史认知答案；先 `aoci_rules`，再按当前 Guide/合同重新获取完整 Overview。不要把此文件当正式索引，也不要加载全量扫描报告。后续维护仍须等待对应批次源码、测试和文档达到交付稳定状态。

核对命令：

```bash
git status --short --branch
git log -5 --oneline
git fetch origin main && git log --oneline HEAD..origin/main
gh run list --branch main --limit 6
```

默认直接在 main 交付；不自动合并或删除无关旧 PR／分支。

## 已交付产品基线

| 方向 | 状态 | 入口 |
|---|---|---|
| 桌面与项目基线 | 原生桌面（GHOST/OpenGL/Vulkan/Metal）、项目格式 **14**（旧 13 可读、升级先备份；SQLite + 文件）、表格/参数扫描、保存分析、项目工作流（按行运行 MuFerro 与 LAMMPS）、归档、技能目录、工作台 | [开发计划](docs/development-plan.md)“当前基线”；`suan/project/`、`desktop/engine/lib/stk_app/` |
| S1 模型接入 | 全部交付：端点与密钥、数据标注与网络设置、本机一键部署（llama.cpp）、能力分档与自动切换 | [model-gateway.md](docs/design/model-gateway.md)；`suan/models/` |
| S2 智能体 | S2a、S2b 交付（格式 13 会话/事件/对象、8 个工具、签名批准、桌面“智能体（多步）”）；**真实模型的 GUI 人工验收未做** | [agent-harness.md](docs/design/agent-harness.md)；`suan/agent/` |
| S3 材料模型 | S3a与S3b通用本机主链交付：冻结输入、迁移/同留出集比较、持久任务、桌面曲线与回退；跨平台新CI待验，合成/PyTorch CPU边界保留 | [materials-models-s3.md](docs/design/materials-models-s3.md)；`suan/materials/` |
| 多尺度引擎 | E0a、E0b、E1a、**E1b 写出器与 PET 本机建模、E1c 分析模板已交付**；PET 参数已按所有者新授权选择 | [方案](docs/design/multiscale-engines.md)、[写出器](docs/lammps-data.md)、[分析](docs/lammps-analysis.md) |
| PET 数据闭环节点 1 | MuFerro/LAMMPS 桌面导入、按冻结引擎处理运行及批次、离线热力学摘要；字典草案和全合成离线数据演练 | [桌面指南](docs/lammps-desktop.md)、[字典](docs/design/pet-data-dictionary.md)、[示例](examples/pet_data/README.md)、[厂内清单](docs/design/inplant-execution-baseline.md) |
| PET 专项研究 / E1d（已交付） | 冻结建模→压密→逐温降温→模量/O₂ 或 PET 链 COM MSD→保存分析；明确启动、取消、恢复、成功阶段复用；full/real 原子/真实键/盒子与实际轨迹帧。11 段真实软件验收通过，物性未验证收敛 | [全流程例](examples/pet_study/README.md)、[结构契约](docs/specs/lammps-structure-1.md)、[参数/限制](docs/pet-model.md) |

## 待所有者决定（决定前不要按某个选项实现）

历史等待期限已结束，但时间经过不构成批准。

所有者 2026-10-12 明确授权根据文献与公开资料判断并直接执行 PET，因此 PET 电荷不再待决定。
采用完整 PET OPLS-AA/MK 2022 适配方案：芳环 C −0.115 e，配套全部电荷/LJ；唯一末端醇氧的 +0.001 e 舍入修正明确记录，
不采用历史 0.0 推断。COOH/OH 六条四聚体为 546 原子，来源与限制见[PET 模型](docs/pet-model.md)。其他事项仍待决定。

1. **S3 下一步**：`stk.dataset/1` 两个数据格式要先交给合作方讨论；MuPRO 能否做电场扫描以产生相场回线待确认。
2. **S2c**（外部规划模型、智能体准备运行）视所有者决定。
3. **保存分析修改提案的持久形式**（较早的 P3 项，[建议](docs/design/review-drafts-and-conversations.md#保存分析修改提案的持久形式建议待所有者确认2026-10-06)）：仍待确认，目前未排期。

## 所有者已经确定的方向

- UI 主要管理 **项目、文件、技能、工作流、对话**。运行记录保存某次执行的冻结输入、参数、状态和产物，
  有独立身份；重新计算产生新运行，编辑流程不能改写旧结果。
- 准备模拟时以 AI 对话为中心，结果分析时以 3D/数据视图为中心。已有 Viewer/节点/表格/文件树组合默认布局；准备／分析独立布局已完成本机回归，源码提交与 CI 状态见上。文档与报告布局已实现并完成本机回归；完整 AI 报告表单已提交并完成本机回归，平台交付仍待复验。
- 节点有项目流程与分析子流程两个层级。表格是通用查看/编辑框架，目标支持类型、引用、公式与富内容，
  参考多维表格和 Houdini 参数化；不要为每个 UI 页面另造一份业务状态。
- 项目采用“目录 + SQLite + 普通资源文件”。稳定 ID 用于持久关联，打开句柄只表示当前会话；
  大数据与图像等不必逐单元格写入 SQLite。表达式/依赖由应用服务求值，SQLite 本身不会执行所有计算。
- STK 内使用 Python 控制公开操作和布局；UI、Python、AI 复用共享服务和校验。2026-10-14 明确应用内基础代码编辑与运行，VSCode 保留为可选外部 IDE。
- Markdown/HTML/PDF 原生候选默认关闭、双平台待验；AI 报告后端和三模式布局已本机实现，LaTeX主链与MP4已实现，完整平台和编译兼容验证继续推进。
- 需要直接连接与 SSH；已有 Linux Runtime 连接/SSH 隧道和本机 stdio 桥，**通用 Mac↔Windows STK 点对点端点尚未实现**。
- `toolkits/` 最终按功能迁入 `suan/`，保留必要兼容；不是整目录改名。当前还有真实调用，不能提前删除。


## 代码导航

- 当前模块边界：[仓库结构](docs/repository-structure.md)、[桌面模块](docs/desktop-modules.md)。`archive/` 不进入导入、构建或测试发现。
- 表格：`suan/project/table_workbench.py`、`field_types.py`、`table_io.py`；原生 `desktop/engine/lib/stk_app/src/table_workbench.cc`、`project_table_editor.cc`。
- 分析／工作流：`suan/project/workflows.py`、`analysis_runs.py`；原生 `src/editors/analysis_graph_editor.cc`、`workflow_editor.cc`，共享候选历史在 `analysis_parameter_draft.cc`、`workflow_draft.cc`。
- 科学链路：[LAMMPS 桌面指南](docs/lammps-desktop.md)、[PET 模型](docs/pet-model.md)、[PET 全流程](examples/pet_study/README.md)。软件验收不证明材料性质收敛。
- 新增工具按任务读取[工具指南](docs/ai-development.md)，不要每轮加载完整历史日志或全仓库扫描报告。

## 构建、启动和测试

### 当前 Linux 工作机

以下路径在交接时实际存在，仅适用于当前机器：

| 用途 | 路径 |
|---|---|
| 仓库 | `/home/mnemora/xcheng/sijin/stk` |
| Python | `/home/mnemora/opt/stk-venv/bin/python` |
| CMake 构建目录 | `/home/mnemora/opt/stk-build/merge-check`（Ninja / RelWithDebInfo） |
| 用户 sysroot | `/home/mnemora/opt/stk-sysroot` |
| 原生程序 | `/home/mnemora/opt/stk-build/merge-check/bin/stk-desktop` |
| 离屏图 | `/home/mnemora/opt/stk-build/merge-check/tests/app/out/` |

一次只运行一个原生编译；编译成功退出后再运行测试，不让测试读取仍在重链的二进制。
以下命令在仓库根目录运行；`&&` 保证构建失败时不测试旧程序。

```bash
cmake --build /home/mnemora/opt/stk-build/merge-check --parallel 4 && \
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  --parallel 4 --timeout 600 --output-on-failure \
  --output-junit /tmp/stk-claude-full.xml
```

工作台/技能/布局/分析草稿定向回归（相关修改时使用；不需要每次文档修改都跑完整套件）：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  -R '^(SkillCatalog\.|SkillsCatalogPython\.|ProjectSkillsPython\.|project_skills|WorkspaceNavigation(Python)?\.|AnalysisParametersEditorPython\.|FocusNavigation\.|ScriptPython\.)' \
  --parallel 4 --output-on-failure --output-junit /tmp/stk-claude-focused.xml
python3 desktop/tests/check_required_tests.py /tmp/stk-claude-focused.xml 'SkillCatalog\..*' 'SkillsCatalogPython\..*' 'ProjectSkillsPython\..*' \
  'WorkspaceNavigation(Python)?\..*' 'AnalysisParametersEditorPython\..*' 'FocusNavigation\..*' 'ScriptPython\..*'
python3 desktop/app/i18n/check_i18n.py
git diff --check
```

Python 测试按改动选取，例如技能相关可从 `tests/test_skill_catalog.py`、`tests/test_skills.py` 与 `tests/test_graph_schema.py` 开始，
用上述 venv 的 `python -m pytest`；完整平台组合与依赖以 [desktop.yml](.github/workflows/desktop.yml)
和 [runtime.yml](.github/workflows/runtime.yml) 为准。新必跑场景要接入 `check_required_tests.py`，跳过不算验收成功。

其他 Linux 机器按 [desktop/README.md](desktop/README.md#build-linux) 重新配置，不能照搬此机 CMake 缓存。
完整测试需要 Python 的科学/控制/可视化/测试依赖及 Xvfb/Weston；sysroot 下载入口支持 `--with-test-servers`。
配置时将 `STK_BRIDGE_TEST_PYTHON` 和 `STK_APP_TEST_PYTHON` 指向实际 venv，避免缺依赖导致测试跳过。

### Python 测试与密钥扫描

最新完整 Python 套件约 13 分钟（没有安装 xdist，不要加 `-n`，耗时随环境变化）；LAMMPS 相关可先跑定向：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python -m pytest -q -m "not perf" -p no:cacheprovider
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_lammps.py tests/test_workflow_lammps.py tests/test_project_workflows.py tests/test_workflow_batches.py tests/test_modules.py
```

Python 3.11 与 3.14 的环境在 `/home/mnemora/opt/stk-venv311`、`/home/mnemora/opt/stk-venv314`（CI 测 3.11、3.12、3.14）。
新增内置模板时，`test_project_workflows.py` 与 `test_workflow_batches.py` 中固定的模板列表要一起更新。
提交前对暂存的改动做密钥扫描（gitleaks，规则在 `.gitleaks.toml`；本机没有全局安装时自行下载固定版本），CI 也会扫描：

```bash
git diff --cached | gitleaks stdin --config .gitleaks.toml --redact --no-banner
```

### macOS / Windows 启动

这两个脚本已存在并供用户测试，不要再建一套。完整工具链要求见[快速启动](desktop/QUICKSTART.md)。

```bash
# macOS，完整 Xcode；仅 CommandLineTools 会导致 xcodebuild 报错
bash desktop/setup-macos.sh --demo
```

```powershell
# Windows x64，VS2022/Build Tools C++ 工作负载、SDK、Git、x64 Python
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --check
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

更新代码后用正常命令重新编译；`--launch-only` 会跳过编译，不能用它验证新功能。
这些脚本只构建主程序，不运行完整测试，也不自动启动 Runtime。进入界面后从 **文件 → 工作台** 检查本次入口。
无服务器演示：[参数扫描/三维](examples/project_scan/OFFLINE.md)、[保存分析/结果表格](examples/project_analysis/README.md)。

## 每次交付约束

不读取、打印或保存密钥。测试清空 `STK_TOKEN_PLAN_API_KEY`、取消 `STK_TOKEN_PLAN_MODEL`；刷新、重开和测试不发收费模型请求。
端点、密钥和产品网络策略只能由桌面显式配置；私有项目数据不发外部模型。公开文档统一称“合作方”。
保持明确运行／保存／发送动作，保护 Viewer、隐藏页草稿和文字输入。UI 交付记录固定起点、实际点击数及结果；本批格式 15 无新增 UI 动作，旧头 Mac 三格式原生 2 点击/20 轮证据已另记。
交付同步四份状态文档，按最终稳定内容维护 AOCI；提交前扫描暂存密钥，推送前等待前代码头 Desktop CI 完成。
