# STK 当前交接

更新：2026-10-30。先读 [AGENTS.md](AGENTS.md)、本文件与[开发计划](docs/development-plan.md)，核对真实 Git / CI，保护未提交修改。主目标是完成计划中的主要通用能力；PET 新专项后置。以下为当前工作树快照，历史证据见[运行验收](docs/runtime-validation.md)和[开发日志](docs/development-log.md)。

## 最新进度：2026-10-30，联邦基础与平台验证续接

交接检查点保存后，所有者的持续开发目标已恢复。本节覆盖下方转交时快照的 WIP、未执行测试和 CI 时态；不要重复已完成步骤。主要通用路线仍未完成，PET 新专项继续后置。

- **源码已本地提交 `11844b257e3a88f0db1e08611624a295e64b13c2`**（21 文件），包含联邦数组/整轮校验、本机 owner consent/outbox、独立 Flower 聚合、精确依赖与指南，以及平台验收和 Windows 测试补修。本批记录提交、AOCI、最终包、push 和新 CI 的实际状态统一查 `FLOWER_EVIDENCE/delivery-closure-summary.json` 并核真实 Git；该步骤未成功时仍待完成，不凭文档推定已推送。`FLOWER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-flower-20261030`；`PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030`。
- 上一远端 main 是 `bccb32d7`，其 Desktop `41082221172` 已重新核为 completed/failure，前头推送等待门满足；Runtime `41082221295` 7/9，Docs/Secret 成功。具体 Mac/Windows 失败见下方历史快照；**本次修正尚无目标平台新 CI 结果**。

| 本批验证 | 实际结果与证据 |
|---|---|
| 完整 Python 首次运行 | **4467 通过、31 跳过、2 排除**，0 失败/错误，802.62 秒；873 输入摘要前后一致。`PEER_EVIDENCE/p4-ci-bccb/integration-next/python-full/summary.json`。 |
| 联邦实际安装与联合 | **230/230，零跳过**，含 f32/f64 两次真实隔离聚合；六个 federation 安装/候选/工作树成员 SHA 一致，真实 worker 来源为独立 site-packages。`FLOWER_EVIDENCE/production-adapter/candidate-01/acceptance-summary.json`。 |
| 3 节点 6 轮联合 | 三个独立真实 ClientApp 进程，18 份训练更新经过 owner grant/outbox，6 次生产隔离 FedAvg 与独立 moment-gradient 参考一致；撤回阻止发送、不确定发送不重放。`production-adapter/multiround-02/summary.json`。**本机 pipe，不是真实 STK 网络验收**；首轮外部脚本误用分页键的失败保留在 multiround-01，生产源未因该脚本错误改变。 |
| Windows fixture | SQLite backup 两连接显式 closing：三版本 authority 各 21/21。Watchdog 改为真实 lane 排队后才推进模块局部时钟，并另测暂存预算；三版本各 4/4，有旧慢暂存红/新绿和误杀 active worker 的负控。生产预算、原等待时限不变。证据 `p4-ci-bccb/authority-backup-close/`、`analysis-watchdog/`。 |
| 原生 Linux | 最终增量 all 编译成功、相关 **69/69 CPU** 零跳过，4 文件摘要稳定；`p4-ci-bccb/native-next-final-summary.json`。不包含 Cocoa/Win32 实际编译或 20 轮原生图像。 |
| CI 门禁与暂存扫描 | federation-isolated job 独立 venv 装本次 wheel/精确依赖，基础环境前后断言无 flwr，精确要求 f32/f64 且零 skip；YAML、bash/Python 语法和真实 230 项 XML 门禁通过。源码暂存 163597 字节、gitleaks8.30.1/.gitleaks.toml 脱敏零发现；不覆盖后续记录/AOCI。 |

31 个 full skip 已分类：15 离屏探针 SIG11、7 Windows 专用、4 可选 PySide6/MCP、3 真实 MuFerro 环境、2 性能 opt-in。原 15 项离屏已在私有 Xvfb/llvmpipe 精确补验 **15/15、零跳过、25.84秒**，873 输入摘要与 full 相同；证据 `PEER_EVIDENCE/p4-ci-bccb/integration-next/render-followup/`，不改写原 full。其他分项：peer 202/202、联邦 230/230 和两个 watchdog 场景实际通过，无对应 skip。

平台候选现状：Cocoa 验收先显式请求自有窗口激活，再经 UI 循环确认 active app/精确 key window；原键门禁未放宽。HTML-video 解码后若完整元素超出 viewport，通过真实 report/Viewer 分隔条有界调整，记录实际拖动；重验同 navigation、暂停时间差≤0.10 秒且不 seeking/ended，保持原完整元素与 20 轮/像素判据。独立审查已修第三次拖动后漏判成功和布局重载可丢失时间基线的两处边界。Windows WGC **只补数值诊断**（初始池、当前 item/content/texture、差值、crop/rect/DPI、帧/poll/耗时）；没有猜边框补偿或放宽捕获判据。根因与目标 OS 实测仍待新 CI。

接手顺序：

1. 按当前 AOCI 合同建立本 Run 认知，核真实 Git/CI/closure；跟踪已有补验进程，已终态不重启。所有测试 KEY 空、MODEL unset，不改产品端点或网络策略。
2. 完成本批四状态文档、最终发行包成员绑定、Observed 审查/AOCI 完整批次及 Verify/Check/Guide、记录暂存扫描和 main 记录提交/push；以 closure 的实际结果去掉已完成项。旧 peer 的 25 条维护及九路径 ack 不重做。
3. 新 Mac/Windows CI 继续验证焦点/完整媒体布局和 WGC 实际尺寸；Linux 构建或 CPU 不代目标平台通过。保持 Viewer、隐藏草稿、明确运行/保存/发送和固定起点点击记录。
4. S4 仍须桌面持久身份/pin/配对授权 UI、可分发 helper/依赖许可、授权不可变文件 manifest/断点整文件 SHA、部署信令及 IPv6→UDP（含端口预测）→TCP→TURN443；Flower 仍缺 `fl.message`/每 run blob 授权、出站 NodeAgent、Runtime 本机训练、持久协调轮次、桌面 consent/审计与显式模型准入。最终须三个出站 Linux 节点通过真实 STK 通道多轮；Hub 不装 flwr，首批不启 SecAgg+，不另起 Flower 服务。
5. 随后 S5 文献/PDF、两层检索和可核对引用、授权陪读/结构化共享；S6 冻结复现到来源报告；P5/S7 干净机离线/Python、兼容迁移、IME/DPI/对话框/恢复/性能和更新回退。合作方 S3 格式/MuPRO 电场扫描、S2c 权限、分析提案持久形式三待决不擅选，PET 新专项后置。

当前 AOCI 正式维护与收据事实以实时工具/本批 closure 为准；任何旧或子 Agent 收据不证明当前模型完整认知可靠。交接只保留安全续接身份与状态，不保存正式 Whole-Index/Header/Entry/Chunk/Challenge/Attestation 正文。

## 转交时快照：2026-10-30（历史，以上方最新进度为准）

所有者最新要求是写下待办并交给另一 Agent；本次只核对和保存交接，不继续开发、不提交或推送。**本节覆盖后文上一批交付中的“当前”“待新 CI”等旧时态。** 整份开发计划尚未完成。

### 先保护工作树

- 已核实本地 `HEAD`、`origin/main` 及远端 main 都是 **`bccb32d7b1da317121ee147ed54bf06a09b2f7c0`**；其父源码提交是 `51a795b9d09610f0bec31b526612cf849c230793`。上一批 peer 代码、记录和 AOCI 已推送，没有领先的本地提交。
- **本轮联邦基础仍是未提交 WIP**：`suan/federation/` 六个文件，`tests/test_federation_updates.py`、`test_federation_consent.py`、`test_federation_flower.py`，`docs/federation.md`、`docs/specs/stk-federation-1.md`；另有已修改的 `pyproject.toml`、`docs/specs/README.md`、`docs/repository-structure.md`、`tests/test_peer_authority.py`。四份状态文档还有本次交接更新。先运行 `git status --short --branch`，不要 reset/clean 或覆盖这些文件。
- 换机器接手时，**只 clone main 不会取得这些未提交和未跟踪文件**；还须移交当前工作树及下列外部证据目录。不要移交私钥、令牌或用户配置。
- 下文用 `PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030`，`FLOWER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-flower-20261030`。它们不在 Git 内；不在同机则先取得证据或重新验证。

### 当前 WIP 实现了什么

| 文件 | 已实现范围与边界 |
|---|---|
| `suan/federation/updates.py` | 标准库的严格数组/更新/整轮校验；有限 f32/f64、小端原始数据、完整 SHA/长度、精确有序名称/dtype/shape；整包 64MiB、128 数组，3–20 个批准参与者且至少 3 份不同的有效更新。元数据校验不认证身份，接入方仍须验证实际载荷和可信授权。 |
| `suan/federation/consent.py` | 本机所有者 SQLite grant/outbox；grant 必须固定 `model_layout`，prepare/read/send 重验实际布局。先持久化发送意图、再在当前授权租约下调用一次显式 deliver；撤销阻止后续发送，已接受发送可结束。发送或落账不确定保留 sending/uncertain，recover 不重发。不是调度器或网络认证；私有库丢失/回滚不保证全局 exactly-once。 |
| `suan/federation/flower.py`、`flower_worker.py` | 父端先验全轮身份/载荷/布局和预算，以显式隔离 Python `-I -m` 启动有界子进程；子端调用 Flower FedAvg，从 base+delta 重建参与模型并按样本数聚合，父端严格复验结果及回执。只返回未登记候选，不训练、发布或自动重试。依赖固定 `flwr==1.42.0`、`numpy==2.5.4`，不进基础 STK/Hub 依赖。 |
| 联邦规范和指南 | 描述上述基础 API；均为当前未提交候选，不能当作 main 已发布的契约或 S4 完成证明。 |
| `tests/test_peer_authority.py` | 修复 Windows WinError32 的 fixture：SQLite context manager 不会关闭连接，backup 两端已改用 `contextlib.closing`。保留真实替换和旧 context 拒绝断言；生产授权代码未改。 |

独立审查发现并已修：所有者授权未固定实际参数布局、SQLite TEXT 长度低估 UTF-8 审计字节数、子回执 `bool/float == int` 误通过，以及深 JSON/超大整数泄漏普通异常。相关反例已加入；这些修正不代表端到端集成完成。

### 已有验证，别重复宣称更大范围

| 证据（相对上述目录） | 已核实结果 |
|---|---|
| `FLOWER_EVIDENCE/admission/summary.json` | Python 3.11/3.12/3.14 各 150/150，合计 450，零跳过；updates 与测试摘要稳定。 |
| `FLOWER_EVIDENCE/consent/summary.json` | 三版本各 43/43，合计 129，零跳过；含真实子进程崩溃、撤销竞态、持久布局及发送不确定性，摘要稳定。 |
| `FLOWER_EVIDENCE/foundation-layout-bound.xml` | 当前基础三文件便携联合 228 通过、零失败/错误/跳过；**两个真实 Flower 子进程测试另行排除，尚未执行**。`parent-receipt-check.xml` 单列父端 35 项。旧 `foundation-preliminary.xml` 的 201 项是先前候选。 |
| `PEER_EVIDENCE/p4-ci-bccb/authority-backup-close/summary.json` | SQLite fixture 修正三版本 authority 各 21/21，合计 63，真实 cryptography、零跳过；新 Windows CI 尚未验证此未提交修正。 |
| `FLOWER_EVIDENCE/production-adapter/candidate-01/build-summary.json` | wheel/sdist 离线构建成功，输入摘要稳定，六个 federation 成员与源码一致；wheel SHA `35f7aad0c73b1fb2bff2c77b9b61d948c295da8985b8c0c4604445e7bb089d68`。 |
| 同目录 `install.log`、`pip-check.log` | 新隔离环境安装该 wheel 成功，59 包依赖检查兼容；**不是已跑过聚合测试或安装态完整回归**。旧会话句柄 91692 已不存在，不要凭句柄重跑覆盖 candidate-01。 |

当前关键源码 SHA：updates `18cf6c0e29bd29f1bd993dd862cf6d6b9c9970090455f1e982a17c0a1c17de19`；consent `b57d584406995905ffcb60d1801b5472c8750ac14af37cbb7666e1d3939d45d7`；flower `a1fcb75cc3e81bdab6369ef9e42eac103371f72516010e0f71f4f093f9baf75a`；worker `3758033588e73fdee040b050224f7448c29645929c05ff1bdc285bf32621def1`。接手后源码有变则重新绑定相应证据。

原 `FLOWER_EVIDENCE/algorithm-probe/` 是独立框架研究，已有 3 个 Linux 子进程、6 轮和独立加权参考的结果，但没有接上新的 consent/outbox/STK 网络；保留原环境与原始失败。生产候选环境另在 `FLOWER_EVIDENCE/production-adapter/env/bin/python`。本机主 STK venv 未装 flwr；**未核验公网部署 Hub 环境**，不要混称已证明所有 Hub 不装 flwr。

### bccb32d7 的最新 CI：均已终态

快照及失败原日志：`PEER_EVIDENCE/p4-ci-bccb/agent-live-ci-summary.json`，记录于 2026-10-30 16:26 UTC；接手仍须重查真实 CI。

| 工作流 | 结果 / 必须继续处理 |
|---|---|
| [Desktop 41082221172](https://github.com/sijintech/stk/actions/runs/41082221172) | completed/failure，16:23:11 UTC 已结束；Windows CPU 和三个 Linux job 成功；Mac、Windows native 失败。**前代码头 Desktop 等待门已满足**，不等于平台验收通过。 |
| [Runtime 41082221295](https://github.com/sijintech/stk/actions/runs/41082221295) | completed/failure，7/9 job 成功，Windows 3.11/3.12 失败。3.11 为 1 failed/3670 passed；3.12 为 2 failed/3669 passed；两者各 168 skipped/327 deselected。 |
| [Docs 41082221284](https://github.com/sijintech/stk/actions/runs/41082221284)、[Secret 41082221188](https://github.com/sijintech/stk/actions/runs/41082221188) | success；Dependency Graph 41082235142 也成功。 |

- Windows 两版本的 authority registry replacement 失败由上述未提交 fixture 修正处理，不能把 Linux 三版本通过写成 Windows 已通过。
- Windows 3.12 另失败于 `tests/test_analysis_run_executor.py::test_queued_attempt_watchdog_does_not_kill_an_unrelated_active_graph`，`queued.wait(2)` 未置位。测试先将 `MAX_SECONDS=1`，生产先启动 watchdog 再 staging、检查取消、进入 worker；可能入队前已超时，日志尚未证明根因。先将测试的入队因果与 staging 时间隔离，**不要只增加 wait 或放宽生产预算**。该项尚未修。
- Windows native 六项均 **0 完整轮 / 0 验收图**：前五项命中 `desktop/spike/document_preview/window_evidence_win32.cc:363` 的 `frame.ContentSize != item_.Size()`，实际差值尚未输出，不能猜边框/缩放补偿；HTML-video 先命中 `desktop/tests/app/reports_native_window.cc:435` 的完整媒体超出 viewport。
- Mac 六项中 Markdown/HTML/PDF 和独立 spike 通过；video 卡在 `desktop/tests/app/reports_native_input_cocoa.mm:150` 精确 STK key-window 门禁，尚未发送该键；HTML-video 同样未完整容纳媒体。旧 pause_failed 本轮未再出现，**不证明视频已验收**。不降低 20 轮、像素、DPI、焦点和隐藏暂停门槛。

### 接手后的具体执行顺序

1. 按 AGENTS 完成新 Run 的 AOCI 认知建立；核 Git/CI 和上列源码 SHA，阅读新增规范、指南及对应实现。所有测试清空 `STK_TOKEN_PLAN_API_KEY` 并 unset `STK_TOKEN_PLAN_MODEL`；不改变产品端点、密钥或网络策略，不调用收费模型。
2. **先执行两个尚未跑的真实 Flower 聚合用例**，验证候选安装来源、f32/f64 加权值、回执/布局/SHA 与依赖隔离。可在当前机器仓库根运行：

   ```bash
   FLOWER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-flower-20261030
   env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
     STK_FEDERATION_TEST_PYTHON="$FLOWER_EVIDENCE/production-adapter/env/bin/python" \
     /home/mnemora/opt/stk-venv/bin/python -m pytest -q -p no:cacheprovider \
       tests/test_federation_flower.py -k real_isolated_flower
   ```

   应实际执行两项，不接受缺解释器导致的 skip。失败须保留原结果，必要时在外部私有目录追踪固定阶段/异常类型，不能输出私有数组/数据或凭据；改源码后构建全新 candidate-02，别覆盖 candidate-01 或只补丁安装目录。
3. 修 Windows watchdog 测试的真实时序问题；按原门槛继续 Mac 焦点/viewport、Windows WGC 几何及 viewport 修正。Linux 不编译目标分支，最终须目标平台新 CI/原生证据。
4. 联邦基础继续做 3 节点多轮、独立本机 grant/outbox、发送审计/撤销/不确定性与独立数值参考的联合验证；本地 pipe 仿真仍不能标成真实 STK 出站网络验收。按最后源码跑有意义的联合、完整 Python 和安装态检查，核包成员与来源，保留失败和 skip 口径。现有 228 项不等于最新完整仓库回归。
5. 稳定交付时更新四状态文档；按实时 Guide 处理新增/变更测试等 Observed 路径并维护全部 AOCI 候选、核 Verify/Check/Guide。对**实际暂存内容**用 `.gitleaks.toml` 扫描后在 main 提交；push 前确认前一代码头 Desktop 已终态。当前 WIP 尚未扫描暂存、提交、push 或完成 AOCI 收尾；旧 peer 扫描和对齐不覆盖它。
6. 再补 S4 产品集成：桌面持久身份/pin/配对与授权 UI、可分发原生 helper/运行库/许可、认证下的不可变授权文件 manifest 和断点校验、部署信令及 IPv6→UDP（含端口预测）→TCP→TURN443 阶段策略。Flower 还缺 STK `fl.message`/每运行 blob 授权、出站 NodeAgent、Runtime 本地训练、持久协调轮次、桌面 consent/审计和显式模型准入；Hub 不装 flwr，不另启 SuperLink/SuperNode/gRPC。至少 3 方，最终须 3 个出站 Linux 节点经真实 STK 通道完成多轮；首批不启 SecAgg+。
7. 后续通用路线仍为 S5 文献/PDF、两层检索、可核对引用和授权陪读/结构化共享；S6 文献参数→冻结工作流→明确运行→数值对比→来源报告；P5/S7 干净机离线包/Python、模块兼容迁移、IME/DPI/对话框/恢复/性能及模型更新回退。PET 新专项后置，保护既有 11 段真实软件路径，不能宣称物性收敛。

### AOCI 与所有者待决边界

上一 peer 批次 **25 条语义已 Apply，remaining=0，Verify/Check/Guide 对齐，已随 bccb32d7 推送**；旧九 Observed ack 也已完成，不重复交易。本次 WIP 还在待验证阶段，维护延后到源码和测试稳定；没有为本次交接签发或留下新的未决 Apply/Recovery。正式 scope identity 为 `55cd6386a7b2ace6089323d022d532ad469d87d68225dc3fb8850b83fb850ff2`、1121 对象，服务 `0.1.0-rc21`。这些身份只供核对；新 Agent 仍须按实时合同加载，不能用本文代替正式认知。本文不保存正式 Whole-Index/Header/Entry/Chunk/Challenge/Attestation 正文。

三项所有者待决保持不变：合作方 S3 数据格式及 MuPRO 电场扫描、S2c 权限、保存分析修改提案的持久形式；没有新批准，不替所有者选项。UI 交付继续记录固定起点、实际点击数与结果，保留 Viewer、隐藏草稿和明确运行/保存/发送动作。本次只写交接，无产品 UI 点击验收。

## 上一已交付批次与历史验证（51a795b9 / bccb32d7）

以下保留原交付证据及通用构建入口；其中旧 CI 和“待新 CI”的说法由上方最新快照更新。

## 接手续接与完成边界

此前应所有者要求保存了待办检查点 `PEER_EVIDENCE/handoff-checkpoint-summary.json`，其中“本地领先1提交、语义尚未Apply”是当时快照。之后按持续开发目标继续本批收尾；**整份开发计划仍未完成**。

1. 先核真实Git/CI并保护任何未提交文件。本批源码为 `51a795b9`；记录提交、push、AOCI事务及新CI的实际状态统一记录于 `PEER_EVIDENCE/delivery-closure-summary.json`。该文件不存在或其中步骤未成功时，相应交付仍待完成，不从文档措辞推定成功。
2. 九Observed路径的ack事务 `74f56c840c267cc396c4732d` 已Apply，不重复ack。语义维护必须消费机器签发的完整批次及remaining，再核Verify/Check/Guide；旧候选SHA或旧认知收据不证明当前对齐。维护工具输出截断不等于Overview传输失败或正式语义写入成功。
3. 推送仍须前代码头Desktop已终态，提交仍须扫描实际暂存内容。源码294782字节的零发现不覆盖后来文档/AOCI；实际记录扫描结果见closure。
4. 优先核新Mac两个视频、Windows六项原生报告/视频及Windows3.12 Runtime；不降低20轮/像素/DPI/暂停门槛。本地验证已终态：141端点/协议、三Python各143、安装203、相关CPU65。完整Python首轮的一处失败与精准复验另列，不冒称最终全量全绿。
5. 再继续S4桌面身份/配对、可分发helper、授权文件传输、网络策略和独立Flower多节点；P4平台验收并行。S5知识库、S6复现闭环、P5/S7离线交付/模块整合仍未完成。PET新专项后置，三项待决仍未批准。

外部证据目录只在当前工作机；另一台机器接手须移交该目录或重新取得对应证据，不能只复制通过数字。

## 当前 Git 与交付位置

- 分支 `main`；本批代码提交 `51a795b9d09610f0bec31b526612cf849c230793`，上一交付头为 `cfb8c561`。实际记录HEAD、push和新CI见真实Git及上述closure，不沿用旧检查点的未推送状态。
- 格式15源码 `59f4cdc3` 及记录头 `cfb8c561` 已推送。Hub 原请求幂等修复 `e5cea387`、Windows GoogleTest 发现修正 `e0139d9f`、Mac 有界诊断 `04aab01c` 均已随此前批次推送。
- **本批 peer 后端、依赖/CI、规范/指南、平台候选与 acceptance 测试隔离已提交上述代码头。** 四份状态文档和AOCI随同批收尾；接手保护任何后来产生的未提交修改。
- 已知源修改：`suan/peer/`、五份 `tests/test_peer_*.py`、`desktop/engine/lib/stk_peer/`、`docs/specs/stk-peer-1.md`、`pyproject.toml`、`.github/workflows/runtime.yml`；平台文件见下。治理状态依当前机器证据与closure，不能由旧收据推定新状态。

## 已核实的上一头 CI

对应 `cfb8c561` 的工作流均已终态：

| 工作流 / Job | 结果与剩余问题 |
|---|---|
| [Desktop 41001132256](https://github.com/sijintech/stk/actions/runs/41001132256) | failure；Linux 主回归、包和干净机 smoke 均成功 |
| Windows CPU `123885530399` | success；上一批 GoogleTest 双标签发现修正已获真实 Windows 验证 |
| Mac `123885530110` | 编译/CPU/Metal通过；Markdown/HTML/PDF与独立spike通过；两个视频失败。video诊断为 `pause_failed`，另一个为 `state_released`；不能据此断言 WebKit 根因 |
| Windows native `123898637995` | 六项失败，均0完整轮/0验收图；WGC尺寸匹配完整WindowRect而非DWM可见边界，视频鼠标DOWN同步发送也曾超时 |
| [Runtime 41001132201](https://github.com/sijintech/stk/actions/runs/41001132201) | 7/8成功；只有Windows3.12独立字段篡改测试在simulate子进程20秒超时，未到验证器断言 |
| [Docs 41001132275](https://github.com/sijintech/stk/actions/runs/41001132275)、[Secret 41001132164](https://github.com/sijintech/stk/actions/runs/41001132164) | success |

前代码头 Desktop 等待门已满足；推送前仍需重新核对远端与终态。上一头失败不等于当前修正已通过。此前 `70449dc` 的 Mac 三静态格式20轮/440图是历史已验数据，不能移作 `cfb8c561` 的新图数。

## 本批已经实现的 S4 后端（代码 `51a795b9`）

证据根 `PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030/`。

- `suan/peer/authority.py`：持久保存**公钥和授权元数据**；Ed25519一次nonce挑战绑定实际DTLS通道，签名后发opaque进程内context。每次项目调用重新核peer、grant、capability和数据库generation；整个共享store操作持registry事务租约，撤销与rebind串行。scope绑定稳定owner/peer公钥指纹/数据库generation，不绑定短期session或grant UUID。
- 本机owner控制入口 `approve_peer` / `bind_project` / `grant` / `revoke_*` / `rebind_project` 不暴露给远端。发现换inode、项目ID变化或已经观察过的revision回退时撤销绑定；可信备份恢复必须显式rebind。**无法保证检测未观察的原地恢复，丢失权威状态后不承诺全局exactly-once。**
- `protocol.py`：独立严格 `stk.peer/1`；仅 `peer.hello`、catalog、table.read、edit_operations.apply_once/get。远端参数是project/grant/generation UUID，不接受路径、本地handle、scope或owner/caller身份。16MiB总包，256KiB编辑请求与512KiB回执；能力双向独立协商。
- `projects.py`：直接复用现有分页、CAS与格式15原子回执；完整操作处于当前授权lease内，没有第二套项目写路径。
- `transport.py` 与可选 `desktop/engine/lib/stk_peer/`：固定libdatachannel 0.24.6 / USE_NICE=ON真实原生helper，DTLS实际验证过的远端指纹与双方随机数形成绑定；有界control/blob、摘要ACK、背压及绝对分片期限。**原生helper不是Python wheel内置组件**，其依赖闭包/三平台发行尚未完成。
- `endpoint.py`：双方签名验证→hello→本机ready后项目派发；单reader与有界worker并发。已修真实held-lease下hello阻塞reader、并发hello乱序、协商未完成仍派发业务三项交错；提交后authority元数据或结果DTO编码失败保持 `PeerCallUncertain`，保留原operation UUID/CAS，重连后只读get确认，不自动重放。最后规范复核发现accepted挑战对象反向、同实现两端相消，已作两行修正；独立规范对端两种角色互操作及两类错ACK共4项红→绿，不能仅靠同实现互通证明规范正确。
- optional extra为 `peer`（cryptography>=50.0.2,<51）。Runtime矩阵安装peer依赖，新增Mac纯授权/协议/项目测试；这些不是跨OS原生WebRTC验收。

### 最终验证与保留的首轮失败

| 证据 | 结果与边界 |
|---|---|
| `endpoint/summary.json` | 47端点+94协议=141/141，0失败/错误/跳过，35.433秒；14文件与真实helper前后SHA稳定 |
| `transport/summary.json` | 12/12真实helper测试，包括本机UDP、ICE-TCP、IPv6、双向16MiB control、64KiB/空blob及指纹篡改、分片停滞/慢滴绝对期限 |
| `peer/matrix/summary.json` | Python3.11.16/3.12.14/3.14.4各143/143（授权+项目+协议），合计429/429零跳过；真实cryptography50.0.2/Ed25519、隔离安装导入和依赖检查，17文件SHA稳定 |
| `p4-ci-cfb8/integration/peer-combined-final-summary.json` | ACK修正前五文件联合198/198，0失败/错误/跳过，43.191秒；最终ACK源另由141项及安装203覆盖 |
| `p4-ci-cfb8/integration/peer-combined-summary.json` | 首次联合158/198；40失败来自缺libnice.so.10的loader退出127，原日志保留；补齐已知隔离运行库路径后另跑198通过，不改原结果 |
| `p4-ci-cfb8/integration/python-full-*` | 本批完整Python已终态：4231通过/31跳过/2排除、1失败，801.099秒、786输入摘要稳定。唯一失败是transport说明含desktop源码路径触发既有许可隔离检查；仅改说明并保持门禁，精准复验1/1。最终ACK修正由141项与安装203覆盖，不把旧全量写成新源全通过 |
| `peer/package-check/final-1/summary.json` | fresh离线安装202 peer+1许可边界=203/203，45.582秒、零跳过、源稳定；551份安装py/Schema一致，112实际模块来源均为site-packages，465份安装suan源码实际接受边界扫描 |

已测业务wheel SHA `84f43861d15260b5dd93a87d5642280d43d4dfc278a61e1edb3045fa4de6ad23`，48040887字节/668成员；业务sdist SHA `8b98e9937ccdbfc925efc7c7baf3030fb2319522cd5ee664346fd1004bed4b3f`，49086107字节/961成员，含peer指南。最后状态文档包重建已完成：wheel全部668成员与已测候选相同；sdist SHA `7c1426a8684402b1eb436c61f5011ad67cb6ef427755f6606fc9099617952402`，49086339字节/961成员，仅 `docs/runtime-validation.md` 与已测候选不同。证据为 `peer/package-check/final-summary.json`，不宣称又跑了一次安装套件。之后若再修改打包输入，需重建或重新核对绑定。

原生helper开发运行必须提供已安装/隔离的运行库。此机示例：

```bash
PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  LD_LIBRARY_PATH="$PEER_EVIDENCE/transport/install/lib:$PEER_EVIDENCE/transport/deps/usr/lib/x86_64-linux-gnu" \
  STK_PEER_TEST_HELPER="$PEER_EVIDENCE/transport/helper-build/stk-peer-transport" \
  STK_PEER_TEST_ATTACKER="$PEER_EVIDENCE/transport/helper-build/stk-peer-partial-test" \
  /home/mnemora/opt/stk-venv/bin/python -m pytest -q tests/test_peer_*.py
```

`ldd` 中缺库必须先解决；不能把显式helper测试skip当通过。不要记录SDP、ICE凭据或私钥。各证据文件的source摘要绑定具体版本，后续源码变化后不能照搬旧通过数。

### 尚未完成的 S4 产品能力

1. 持久设备身份/公钥pin的桌面管理与配对、项目授权/撤销UI，实际Mac↔Windows端点、可分发helper及运行库/许可闭包。
2. 实际部署的信令/STUN/TURN和网络自检；现有 `route=all` 是ICE候选并行选择，**没有实现所有者指定IPv6→UDP（含端口预测）→TCP→TURN443的完整阶段策略**。没有跨机器NAT、对称NAT端口预测或TURN443成功证据；不默用公共STUN。
3. 有授权的文件传输与断点：现有blob channel只证明块通信。文件索引的Path可编辑、可指向external，`project.read`不等于批准发送任意文件字节。下一批应从本机显式冻结/批准不可变文件manifest开始，以当前认证和project/generation租约读取有界块；不要把索引路径直接作为远端能力。完成须整文件SHA、fsync与无覆盖发布，ACK不代表落盘或项目commit。
4. 独立Flower环境、多Linux模拟节点多轮训练；公网hub不安装flwr；不因连接原型标记S4完成。

## 平台修正与验收待办

- Windows四文件：`window_evidence_win32.cc`、新 `window_capture_geometry.hh`、`reports_native_input_win32.cc`、`evidence_pixels_test.cc`。WGC只接受精确DWM或完整WindowRect尺寸并取对应原点；物理per-monitor DPI及采集中几何稳定再核；保留8192边长/16Mi像素、alpha与20轮门禁。输入为固定三条local PostMessage，日志明确queued而非已消费，后续DOM和OS图片仍必须证明效果。独立只读审查未发现实质几何/溢出错误；Windows真实编译/六项20轮仍待新CI。
- Mac：`native_view_cocoa.mm`、新 `media_pause_verification.hh`、`resources_test.cc`。单次公共pause命令；同一generation/navigation/WK实例下每25ms至多一个状态查询，原始绝对1秒截止覆盖ACK/查询缺失，未验证则关闭撤销。State和WK仅weak持有；异步Block按值持shared请求，不能捕获shared_ptr引用。此为候选修正，**本机不能编译/验收Cocoa，不声称WebKit根因已证或Mac视频已通过**。
- 唯一增量all构建10.586秒退出0、1344输入摘要稳定；最终相关DocumentResources/DocumentEvidence/NativeMediaProbe/ReportDocumentHost共65/65、零跳过。Linux不编Cocoa/Win32分支；最终源摘要和追加核验见 `p4-ci-cfb8/integration/`。
- `tests/test_acceptance.py`隔离字段篡改验证，直接构造有效夹具，先核正例，再确认mean/min/max不变仍拒绝坏field；`simulate.py`未改，未延长20秒或skip。定向6/6含真实绘图和Runtime两任务扫描，4.48秒/源码稳定。历史Windows子进程内部耗时点无栈，原因仍不确定；此改动消除无关冷启动耦合，不称Windows实测通过。
- 本批没有新产品UI操作；不伪造点击数。保留旧固定布局/Viewer/草稿和明确保存/运行/发送；双平台新20轮、IME、跨屏DPI与浏览器内存继续真实验收。

## 格式15上一批已经完成的验证

`EDIT_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-foundation-20261029/edit-operations/`。
最后核心78/78、3.11/3.14恢复各15/15，完整Python4034通过/31跳过/2排除；最终完整原生2022/2022、零跳过，Linux必跑1546匹配；恢复候选独立安装96/96。精确776 hot-journal物理恢复和最后lstat注入均已完成，不重复列为待跑。
最终wheel SHA `2f5bcd74cf1a1c7a98c15ffc11773094f4c5198531b2c1d9ecc4b34b5a788268`；最终sdist SHA `236b03b17685ecbd2c295c0849f06f312fe09fd7c8c42420075d0184d420b697`。包、真实bridge/worker来源、观察ack/19项语义维护/Verify/Check/Guide与已推送六提交见 `delivery-closure-summary.json`。旧81项包与首轮失败不可冒充新96项/最终2022证据。

## 接手执行顺序与剩余通用路线

1. 核实Git/CI、最新源码、握手ACK规范反例和发行候选的当前终态，保护所有未提交文件；已终态进程不重启，活进程继续观察。
2. 本批Mac异步生命周期/九Observed路径审查、最终源绑定、peer指南和独立安装已完成；新平台CI仍须实际核对。本批完整Python首轮结果及其唯一边界失败/精准复验已记录；最终ACK独立规范反例、141项与安装203已通过；不要重复旧全量或旧198候选来冒充新证据。
3. 四状态文档保存本批源码commit/测试/上一头CI快照。依closure核对本批AOCI语义批次及remaining、Verify/Check/Guide、暂存扫描、main记录提交和push；已完成步骤不重复，继续核新平台CI。
4. 第5项继续上述S4产品缺口，不以当前198项替代配对/文件/网络/Flower完成；第3项P4继续平台缺口。
5. 第6项S5：本地PDF解析、两层检索、可核对引用和授权陪读/结构化共享；先公开或自有资料，旧Qt截文不代表RAG。
6. 第7项S6：文献参数→冻结工作流→明确运行→数值/曲线比较→带来源报告；保留缺参、失败与不确定度。
7. 第8项P5/S7：干净机离线包/Python、平台文件对话框、IME/DPI/快捷键/恢复/性能、模型更新回退；toolkits按职责迁入suan且保留兼容导入和发行包。通用引擎/执行目标/ABACUS按依赖推进。
8. PET新字典、厂内专项、专用训练、长链/气体收敛和材料指标后置，已有功能及证据继续保护。后文三项待决不因持续开发而视为批准。

### AOCI续接

本批九Observed路径已逐项审查并核SHA，ack事务`74f56c840c267cc396c4732d`已Apply；正式语义维护、最终对齐及Recovery事实见 `PEER_EVIDENCE/delivery-closure-summary.json`。此前正式索引1107对象属于cfb8批次，不能代替本批结果；旧Maintain批次在文档再次变化后不能直接Apply。
本Run压缩后按合同完成新完整传输与交付/严格核验，但Dirty治理不允许声称当前完整系统认知可靠。本交接不保存正式Whole-Index、Header、Entry、Chunk、Challenge或Attestation正文。
新Agent或压缩恢复必须先 `aoci_rules`，再按当前合同普通完整 `aoci_overview`；实际压缩声明 `context_compaction` 与新event ID，原样跟随cursor到completed并只提交一次核验，不能拿本文件/Memory代替正式认知。源码、测试与状态文档稳定后统一维护；不得重复已对齐事务。

## 已交付产品基线

| 方向 | 状态 | 入口 |
|---|---|---|
| 桌面与项目基线 | 原生桌面（GHOST/OpenGL/Vulkan/Metal）、项目格式 **15**（旧 1–14 可读、升级先备份；SQLite + 文件；永久编辑回执）、表格/参数扫描、保存分析、项目工作流（按行运行 MuFerro 与 LAMMPS）、归档、技能目录、工作台 | [开发计划](docs/development-plan.md)“当前基线”；`suan/project/`、`desktop/engine/lib/stk_app/` |
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
- 需要直接连接与 SSH；已有 Linux Runtime 连接/SSH 隧道和本机 stdio 桥，已实现本机两端 peer 后端原型，**Mac↔Windows 真机端点与桌面配对尚未验收**。
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
