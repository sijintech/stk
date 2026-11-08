# Codex / Claude worktree 协作约定

## 2026-11-08 当前补充：15已集成，16接Hub工作区CLI

实际Claude15交4d02ea3a，仅三新harness路径，由root选择集成为2cc40a0d。root67项/最小installed10断言及独立审阅通过，既有WIP保留；证据见运行验收。root仍独占main/共享build/状态文档/AOCI/推送，前整个Desktop42495020086终态前不push。

### CL-D1-HUB-WORKSPACES-16：现有Hub工作区的CLI薄适配

- 基线Claude4d02ea3a，独立stk-claude/claude/support，不同步main；已派发，未交付。
- 唯一写入suan/runtime/cli.py、tests/test_runtime_hub_cli.py、docs/hub.md。create/list/files及仅workspace.create原action观察复用现有ConnectionStore/HubBackend；direct/SSH/jobs兼容。
- create先打印原key/action，丢回复保unknown，只观察原身份，不自动批准或重建。list明确有界heartbeat快照；files按既有read及兼容fallback，不冒称旧Hub也零action。Hub upload在遍历/读文件/网络前明确unsupported，直连上传保持；不自授desktop或改R2/R3/协议。
- 真实公开loopback及适配反例验证同键、冲突、review、丢回复、跨node/kind、断线/能力和早拒绝；先交固定diff/SHA/测试，经root审阅才stage/scan/commit，不push或另派peer。任务卡d1-hub-workspaces-20261108-20/root/claude-task16.txt。

下方“15未交付”为历史快照，以上新进度优先。


## 2026-11-08 当前补充：Claude14已集成，15开发中

root单路径集成实际Claude14 b510da04为a1904447，真实peer点击18/18通过；旧7ef WindowsCPU本轮也1446/1446过，具体空JSON根因仍未知。root AX五源码79ae0adf7bfe7734a49f33fd571ecdd4e7b650bd另验，Apple待新CI。前整个Desktop42487388780于15:04:55Z failure终态，等待门满足；WindowsPDF像素和Mac两视频仍未通过。root独占main、共享构建、四状态文档/AOCI和push，旧WIP保留。

### CL-D1-UPLOAD-RESTART-15：真实Bridge上传ACK丢失恢复

- 基线：实际Claude独立stk-claude/claude/support先从b510da04按授权同步b517554a、c5d8e503、4399f2fa三提交，实际59f082db；新任务尚未交付。
- 仅新增examples/backend_parity/upload_restart.py、UPLOAD_RESTART.md及tests/test_backend_parity_upload_restart.py。既有helper、产品、CI、发布契约、全局状态和rootAOCI只读，不push或另派peer。
- Hub真实upload_chunk已收至少1MiB且小于总量、Bridge ACK未入原journal时，仅SIGKILL/reap自有Bridge；Hub/Node/Runtime不重启。重开同profile/state/journal，无重新配对，显式resume原transfer/key/request/upload_session/offset，证明首新块从已收偏移而非0开始。
- 原workspace.import仍人工复核，完成前无workspace字节/任务；驱动写后/启动前SHA绑定，错/缺驱动零spawn反例及独立成功门。复用helper来源、绝对预算和cleanup，source/installed同字节，KEY空/MODEL unset；无真实solver/helper/模型/许可。
- 外部任务卡d1-upload-restart-20261108-19/root/claude-task15.txt；先固定diff和测试、root审阅后才准stage/commit。根四状态文档与认知由root维护，不合并Claude baseline。


## 2026-11-08 当前补充：root输入切片与Claude14

源码 main `4399f2fa6dfaba941922d2808ca023eba3766105` 已本地提交，尚未push；远端仍 `7ef5d21e`。前整个Desktop42487388780仍运行，终态前不推送。原四文档WIP和AOCI预存改动保留，最终交付状态见 `d1-input-transfer-20261108-18/root/closure.json` 与实际Git。

root新增input_transfer.py/INPUT_TRANSFER.md/测试并修singleton跨平台收集，最终28项与最小安装态11断言已过，独立审阅关闭两假绿。Claude14继续只写peer_test.cc，先交固定候选再由root审阅/构建/集成；尚未通过目标Windows验收。root保留共享构建与状态/认知独占；7ef的Runtime42487388719于14:14:50Z整轮failure：11job成功、两Windows矩阵因新增Linux专用singleton测试在收集阶段引用不存在的SIGKILL而报错，未执行该矩阵测试。本提交改为函数体解析信号名称，缺SIGKILL的模块红绿反例及Linux原11项通过/5.73s；仍待新Windows CI。Docs42487388755完整部署成功，Secret42487388666成功。Desktop当前Linux三job成功，Mac已越过编译/CPU阶段、WindowsCPU运行，原生最终结果待出；不能继承旧头平台验收。

所有者最新决定：Codex 作为 root 总负责，Claude 在独立 worktree 配合文档和特定模块开发。
本约定替代此前共用 main 工作树、Claude 仅做设计的安排；发布协议仍以当前版本为准，剩余待决见交接。

## 工作区和职责

| 角色 | 工作区 / 分支 | 负责的结果 |
|---|---|---|
| Codex / root | `/home/mnemora/xcheng/sijin/stk` / `main` | 任务拆分、模块及契约边界、跨仓协调、代码审查、集成、最终回归与构建、AOCI、提交推送和 CI |
| Claude | `/home/mnemora/xcheng/sijin/stk-claude` / `claude/support` | root 分配的文档和模块实现、相关测试、独立审阅与交接证据；每次只推进明确的任务范围 |

root 统一维护 `AGENTS.md`、`CLAUDE.md`、本协作约定和四份状态文档：`handoff.md`、
`docs/development-plan.md`、`docs/development-log.md`、`docs/runtime-validation.md`。
Claude 的角色不限于网页，也不限于设计；具体后端、原生或前端模块由任务卡指定。
独立审阅任务须报告问题与证据，是否同时授权修复由该任务卡说明。

worktree 隔离工作文件和索引，但共享 Git 对象与 refs。双方仅在自己的分支提交；只有 root 集成或推进 main、推送和处理 CI。
root 不自动整合无关旧分支或 PR。Claude 提交后交付精确 commit，root 审查通过再选择性 cherry-pick；冲突在集成时显式处理。
新契约先协调兼容规则，不能让两个模块分别创造相同业务状态机。

所有者已要求持续推进开发、合理给 Claude 安排任务并定期合并相关 PR。root 在所有者离开期间按已授权范围持续工作，
审查 PR 的实际 diff、依赖、当前 head 和 CI，满足仓库门禁后集成；未相关 PR 不因本授权自动纳入。
默认 main 交付继续适用，Claude 使用独立分支；需要 PR 时由 root 统一推送分支并建立/合并。
待决问题记录候选与影响后继续独立工作，不把未回复当作采用方案。

## 任务交接规则

root 发出的每个任务都填写：

- 任务 ID、目标、基线 commit、明确的写入路径和负责模块。
- 输入/依赖、需要遵守的现有契约、与 root 当前改动的边界。
- 可运行的验收方式、证据目录和未具备的真实平台/资产。
- 交付物、独立检查要求、待所有者决定项和禁止代选的范围。

Claude 开始前核对实际分支和 Git 状态。若所需修改越过任务边界，先向 root 报告具体依赖；在已分配范围继续可独立完成的工作。
未确认的方案保持候选，不因为编写文档或 stub 就宣布已经实施。
每次交付附完整 SHA、改动路径、实际检查结果、失败/未验证项及证据引用。root 按同一基线审阅，不能借旧绿灯覆盖新字节。

Claude 不修改 root 的状态文档；任务结果先在交付说明中记录，由 root 整合。
双方检查 staged diff，仅暂存自己的路径/增量。含既有 WIP 的文件按 hunk 暂存，禁止把旧未提交内容连带提交。
同步分支前确认工作树干净；不通过 reset、clean、强制 checkout 或删除 worktree 丢弃其他人的工作。

## 构建、状态和认知隔离

root 独占 `/home/mnemora/opt/stk-build/merge-check`。Claude 如任务需要原生构建，使用
`/home/mnemora/opt/stk-build/claude/<task-id>`，结果和测试临时目录也按任务隔离；不共用会写入的编译缓存、安装前缀或测试数据库。
安装依赖使用独立环境，不改 root 的环境，不启动未经任务授权的真实计算或收费模型请求。

Git 仅带入已提交文件，root 现有未提交 WIP 留在 root。不要复制用户凭据、本机私有状态、身份或模型资产。
测试使用 `env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY=`；所有既有隐私、显式执行和目标平台验收要求保持。

AOCI 的认知身份包含仓库根；Claude 不把 root-bound MCP 的回执当作自身 worktree 的认知。
在自己的工作区按当前合同建立认知；若工具仍绑定 main，报告绑定差异，使用对应工作区的受支持入口，不改写 root 的运行资产。
两边各自保持认知约束，正式合入 main 后由 root 在最终稳定状态维护 main 索引；不直接拷贝/合并 Claude 的 `.aoci` baseline。

## 当前任务卡

### CL-D1-PARITY-11：首个实际双部署任务切片

- **状态：** Claude 已交 `6cc2d39e0f57b15426462897edfb943b2df01505`，root 选择集成为 `4b33e131`，再以 `6ae96999` 修正清理存在检查的异常隔离和未舍入预算判断。当前为本地主线提交，推送/CI 见交接和本批 closure。
- **独占交付：** `examples/backend_parity/offline.py`、`examples/backend_parity/README.md`、`tests/test_backend_parity.py`；仅测试样例，不新增产品 CLI、协议或数据库格式。
- **实际验收：** root 联合 61 通过、零跳过，23.35s；独立最小 extras 环境 `-I --mode installed` 的 A 直连 Runtime 与 B Hub/Node/Runtime 共 9 断言通过、12.1s，来源摘要一致、实际 marker/PID 相符且进程退出、清理完成。原最小包来自 `58fbd03e`，产品目录到 `6ae96999` 零差异，harness SHA 单独绑定。
- **审阅：** 两次独立审阅和 root 红绿反例修正空产物假绿、混合来源、启动计数/PID、预算、异常/清理失效和错误路径导出。root 最后两反例先失败，修后纳入上述 61 项；证据 `d1-parity-20261108-08/root/parity-integration/`。
- **范围：** 单 Linux 主机、固定公开合成程序；不含整个 D1 合同/故障矩阵、云端项目服务、跨站、目标 OS、真实 MuPRO 或科学有效性。

### CL-D1-DISCONNECT-12：节点断线与原任务恢复观察

- **状态：** Claude在同步root两文件修正后交付 `a215972d68ecf2497c3161ac4a083a9323152773`，root选择集成 `688db5a0`；本地主线已提交，推送/新CI见本批closure。
- **当前复核：** 两P2均已关闭：原节点须杀前有效存活、实际SIGKILL并reap；原program/worker冻结身份跨阶段比较，取消后清扫前核原身份退出。旧候选提前退出/worker替换两假绿在最终字节被拒绝；独立五个真实sleeper场景通过，八进程全回收。
- **唯一新增写入：** `examples/backend_parity/disconnect.py`、`examples/backend_parity/DISCONNECT.md`、`tests/test_backend_parity_disconnect.py`。同步后已有 helper/README 只读，root 树、全局状态、AOCI、共享构建、产品契约及 CI 均不改，不推送或另委派 peer。
- **目标：** 私有 loopback Hub/Node/Runtime 中只提交一次固定程序；只停本次 NodeAgent，证明 Runtime 原任务及真实程序身份继续；Hub 离线精确读保持 unavailable/unknown。用同 profile 重启节点后观察同 task，再明确取消并核 PID/worker 退出和一次启动，没有换 authority 或重新提交。
- **退出证据：** 原请求身份、实际阶段观察、逐模块与两份 harness SHA、无新增观察 action、marker/PID 和清理。只读接口若不能证明某项须报告限制；预算、source/installed 和窄环境约束复用已验 helper，异常不导出私有路径或凭据。
- **实际验收：** root最终联合90通过、零skip、43.90s；最小非system-site-packages环境 `-I installed` 的10项断言通过，场景23.544913289s、含清理24.654371985s，module来源/摘要及script/helper SHA一致，原进程退出、一任务/run/marker、清理无残留。Claude最终source/installed分别为trial-06/07，独立审阅核实绑定，旧trial不代新字节。
- **限制：** 仍为单主机进程SIGKILL，不代表网络分区、Hub/Runtime重启、站点故障转移、许可求解或科学通过。证据 `d1-node-disconnect-20261108-10/root-integration/`、`review/candidate-2/`；产品后端未改。

### CL-D1-HUB-RESTART-13：已接受任务的 Hub 丢结果与重启

- **状态/基线：** 实际Claude独立树从a215972d交付 `755212b2b5636ca07e4fe18974c1c97af0df7a72`，root选择集成为 `ddd7d7c286c306a25eb0d1640fdaa2ebe47404e7`。三路径SHA匹配独立candidate-2，双方暂存扫描零发现；本批未push，最终交付见closure。
- **唯一新增写入：** `examples/backend_parity/hub_restart.py`、`examples/backend_parity/HUB_RESTART.md`、`tests/test_backend_parity_hub_restart.py`。既有offline/disconnect helper、产品、全局docs/AOCI/CI只读，不push或另委派peer。
- **目标：** 原Runtime已接受且原program/worker运行，Hub原action仍queued无结果时，仅SIGKILL/reap自有Hub；原Node/Runtime存活、首次结果在断线时被丢弃后，以同库/端口重启Hub，真实重派原action并恢复同任务。保留节点原缓存，缓存恢复与再次Runtime幂等提交分别记录，不删缓存制造重放。
- **验收：** 只一次客户端提交、冻结action/key/request摘要和原进程身份；实际故障、重派/缓存、一次启动及显式取消前退出证据。source/installed同字节、helper/driver摘要、绝对预算、清理失败拒绝及受控反例；不以只排队未运行的简单重启替代该边界。
- **实际验收：** 作者修后157项联合及source/installed各11断言；root在新CLI生命周期锁和新offline元数据helper上最终联合271项零skip通过/74.57s，独立最小包-I installed的11断言通过，场景7.680591277s、含清理8.607716267s。两次delivery、一次Runtime.submit、节点缓存恢复原任务，一task/run/marker，原program/worker显式取消后清扫前退出，清理完成。
- **审阅：** 初稿驱动SHA错误/缺失仍可ok的P2已关闭：真实文件写后和启动前均核固定SHA，H0及run成功门必需完整匹配。独立9个proof/run用例、2个绕过全部断言仍被独立门拒绝的反例、3个真实临时文件篡改/删除零spawn反例及43个保留故障反例通过。旧候选/旧trial保留，不代新字节；script dd29a3dd…，主线helper cf2b13c9…。
- **证据/限制：** `d1-hub-restart-20261108-12/root-integration/`、`review/candidate-2/`。单实例锁由root另行开发c5d8e503；本切片仍不含网络分区/跨站、云端项目、真实MuPRO或科学验收。Claude保留交付头并接下列14任务；全局状态/认知/共享构建仍由root独占。

### CL-NATIVE-PEER-14：Windows PeerMouse 空 JSON 失败

- **状态/基线：** 同一实际Claude会话已接单，独立 `stk-claude / claude/support` 保持755212b2，不同步其他root改动。唯一可写跟踪路径 `desktop/tests/app/peer_test.cc`，当前与main/fd相同SHA157262a7…；先交固定候选，root审阅后再批准扫描提交。尚未交付或验收。
- **真实失败：** fd的WindowsCPU128734373360在1446项中仅PeerMouse.ActualClicksSelectTwoFilesHostReceiptEnablesOfferAndPreservesOtherDraftAndViewer失败，空JSON解析异常，整组902.99s。日志无法单独证明是哪条读路径或Windows根因；需结合发布/读取时序与确定性反例定位。
- **边界/证据：** 不改产品peer/bridge/UI、CI/预算或共享support，不删点击/两文件/session手改值/业务次数/Viewer和隐藏稿检查，不靠固定sleep或吞永久坏JSON。测试KEY空/MODEL unset、只清自有进程；root统一stk-peer-app-tests构建和目标OS CI。证据 `native-peer-fixture-20261108-16/`，不是传输/撤权或真实helper新验收。

### root D1 元数据与 Hub 单实例

- `b517554a` 为正常双部署样例加五时间字段按各自原Runtime保真、created_at重放不变和固定产物MIME门；不比较跨部署时间大小，不收紧未执行任务的缺省/null契约。MIME错误私有文本不进入失败证据；独立反例已关闭。
- `c5d8e503` 只给正式serve按真实状态目录持control.lock至退出，pair仍可并行。真实旧代码7红，修后相关49绿/零skip/13.48s，独立14纯mock覆盖异常归类与释放；直接create_app多worker由部署方管理。最小包重建后正常12/断连10/Hub重启11断言全过，主线联合271项零skip通过。

### root 原生 AX client 测试候选

- **归属：** 另一 Codex 辅助代理，独立 detached `/home/mnemora/xcheng/sijin/stk-native-ax`、基线 `304ba0be`；不是 Claude。旧 `stk-native-runs` worktree 保留。
- **范围：** 报告测试夹具、新公共 AX helper、numeric 协议/所属进程控制和 CPU 反例；root 已扩展 `test_media_probe.hh` 和 `native_view_cocoa.mm` 的 Apple TEST_PROBES 部分，只读核真实 WKWebView/session/导航代次。不改非测试行为、权限或网络。root 统一共享构建、原生验收、认知及发布。
- **当前候选：** 独立提交 `c16170c8` 及绝对时限后续 `0b4b53c0` 已审阅并选择集成 `d2f62622`。12路径SHA与候选一致，root两个主线目标构建通过、43项相关CPU测试零skip通过/2.85s；暂存106792字节gitleaks零发现。独立源码审阅无新增实质问题，未执行Apple分支。
- **新Mac实况：** 已推fd394e46的Mac job128734373211在Build失败：AXValueGetValue收到旧UInt32常量，尚未跑CPU/Metal/原生。root提交 `2c9729b8` 改用类型化kAXValueTypeCGPoint/CGSize两行，暂存扫描零发现，未Apple编译；仍须新MacCI。整个Desktop42481548048于13:51:08Z失败终态，Linux三job和Windows原生文档6/6成功、WindowsCPU另有上述14任务失败；前整轮等待门满足，本批未push。
- **待验：** 已实现父端泵UI、owned child的2s绝对时限/有限kill-reap和关闭前drain、真实窗口/WKWebView/session/导航/布局代次及新DOM再核；8s原seek期限不因重试续期。唯一slider、原生输入、DOM/OS像素和20轮门保留。仍须目标Mac编译/实际原生CI，Linux/审阅不算修复；同步AppKit查询不可抢占，只拒绝晚结果。

### CL-D1-01：D1 实施前的最小契约与兼容门清单

- **状态：Claude 文档头 `9590d21b` 已由 root 审阅修正并集成到 main `f6a75f84`；D1 两部署验收仍待实施。**
- **基线：** 创建本 worktree 时继承的协作规则提交；接单时在交付说明记录实际完整 SHA。
- **目标：** 将现有三份统一后端设计转为 root 可实施的 D1 清单，逐项区分已发布、拟议新增、当前缺口和依赖决定。
- **唯一写入范围：** 新文件 `docs/planning/d1-compatibility-gates.md`。只读核对相关实现、测试和规格。
- **输入：** [共享架构](../design/shared-backend-architecture.md)、[任务与数据设计](../design/distributed-task-data-protocol.md)、
  [场景验收](../design/distributed-workbench-acceptance.md)、[发布规格](../specs/README.md)、[路线图](platform-roadmap.md)。
- **必须交付：** 最小无 GUI 装配切片；本地/云部署的同语义合同矩阵；旧 CLI/Bridge/Runtime 兼容门；
  原操作回执、当前授权、取消/观察/重开和唯一写入的反例；源码与测试入口、未具备资产及逐项退出证据。
- **本轮新决定：** 优先执行器与专业软件，首项 MuPRO/MuFerro；插件定义原生格式，MuPRO 使用 HDF5；开发 S2c prepare/run 权限扩展。
  这些方向已获准但尚未实现/发布，纳入本任务的兼容门；电场扫描具体参数和分析提案持久形式仍须区分。
- **边界：** 不发布新 schema，不改产品代码或数据库格式，不替所有者选择剩余未决或 PET 新专项；
  不把历史 Synthrix `90d7c4a` 接缝当当前正常启动可达，不推送、不启动主机服务/模型/科研任务。
- **验收：** 文档相对链接/章节锚点和 diff 空白检查；条目均指向精确来源或标明 proposal/unknown，实际未跑检查写未运行；
  提交前暂存 gitleaks 按 `.gitleaks.toml` 零发现，交付完整 commit 与 root 审阅问题清单。

### CL-MUPRO-H5-01：MuPRO 原生 HDF5 独立读取模块

- **状态：Claude 最终 `73abd757fcbaa29fbeb72993e6df930ea581aaa3` 已由 root 选择性集成 main `56f51af7`。读取器边界修正已验，真实 MuPRO/Windows 尚未验。**
- **基线：** `claude/support` 文档头 `9590d21b`；该头产品源码与 root `37d26464` 相同。
- **唯一写入范围：** 新增 `suan/connectors/mupro/hdf5.py` 和 `tests/test_mupro_hdf5.py`，另作独立提交。
- **目标：** 提供惰性加载的只读 MuPRO HDF5 适配，显式选择 `/tNNNNNNNN/<field>`；
  将源 `(nx,ny,nz,nc)` 映射为 C 连续 `(nz,ny,nx,nc)`，保持原值、dtype 与未知单位。
- **验收：** 真实 h5py 合成非对称网格、多步号/字段、区域与步长等价和读取前预算；
  缺失/错误 shape/dtype、损坏、链接/虚拟数据/外部存储和源变化必须明确拒绝。
  普通导入不读文件或加载 h5py/NumPy，不执行求解器或模型。
- **边界：** 不读合作方私有实现；不改 connector 注册、父模块、依赖、发布协议、智能体或全局状态文档。
  这是独立读取子模块；root 审查后再接既有 FileSource、connector 和图节点，不把合成数据当真实 MuPRO 运行。
- **交接：** 只提交上述两文件，附完整 SHA、接口、实际测试/扫描和限制；不推送，不拷贝 AOCI baseline。

### CL-H5-REVIEW-02：HDF5 接入只读交叉审查

- **状态：Claude 主审查和附加兼容性复核均已回报。** 命名副本在强杀后遗留已由 root 修正为 `3579aea1`；容器上限和全量哈希成本保留，Runtime 终态可见性及本地读取器/FileSource 路径规则已补入读取契约。基线 root `56f51af7`，全程只读 root 的本批 adapter/node/context/测试和 HDF5 契约。
- **目标：** 核对实际字节与规划键、FileSource 边界、取消和私有副本清理、dtype/轴序及兼容性。先交具体反例与证据，root 负责修正。
- **写入范围：** 不改产品源码、文档、认知资产，不提交或推送；可在独立外部临时目录做合成探测。

### CL-MUPRO-H5-DISCOVERY-03：MuPRO HDF5 元数据发现

- **状态：Claude 已交付 `c975f58da1290317ecbe9eff510ca53b82ab52b3`，root 审查并选择集成 main `89e40c89`。** root 接 FileSource、结果描述及原任务收集；最终联合419通过/5跳过，真实许可与目标 OS 未验。
- **基线：** Claude 现有干净 `73abd757fcbaa29fbeb72993e6df930ea581aaa3` / `claude/support`。拟从 main `f152e67a` 新建任务分支被 Claude 后台会话的权限设置拒绝，未改设置或重试绕过；继续使用已授权的既有独立分支，root 只选择集成两个新文件。
- **唯一写入范围：** `suan/connectors/mupro/discovery.py`、`tests/test_mupro_hdf5_discovery.py`。
- **接口：** `_discover_hdf5_stream(stream, *, max_entries=4096, check=None)`；调用方拥有已验内容的普通匿名流，返回 selector/step/name/shape/dtype 元数据，保持流打开。
- **验收：** 复用读取器的链接/存储/dtype 检查，不读值或分配数值数组；两层遍历计入忽略名称并限总条目；顺序确定、取消及同 API 文件变化检查。真实合成 h5py 反例、暂存 gitleaks 后提交完整 SHA。
- **边界：** 不改 root 工作树、父连接器、契约、全局状态或 AOCI；不执行许可软件/模型，不推送，不代选科学参数。root 审查后集成，元数据发现不证明求解成功。

### CL-H5-INTEGRATION-REVIEW-04：发现与收集接入复核

- **范围：** 只读 root 的 FileSource/结果句柄、父连接器、图索引、收集和相关测试/契约；外部小型合成探测，不改源码/文档/认知，不提交推送。
- **已回报：** HDF5 诊断曾阻断 DAT/能量入口，root 已复现并修复；保留严格原生字段规则及硬链接 selector，不把别名当独立科学观察。root 另复现并修正跨步布局收集漏检和替换插件调用兼容。
- **收口：** Claude 已针对 main `89e40c89` 完成只读复核，合成探测确认 DAT/能量兼容问题关闭；`integration-review.md` 与 `integration-probe-recheck.json` 保留在本轮外部证据的 `claude/`。未传 `result=` 的 open 仍重做完整容器复制，运行中改写仍可使索引失败，无 live HDF5 支持。419/5为root实际回归；Claude未重跑该套件、目标 OS 或真实 MuPRO。独立树保持 `c975f58d`，root继续负责全局交付。

### CL-S2C-PLAN-05：MuPRO 智能体执行授权的实施清单

- **状态：Claude已交外部 `s2c-plan-05.md`（145行），root已按实际源码审阅。** 基线 `89e40c89`，尚未运行方案中的测试或扩展发布权限。root选择会话payload可重算run身份、不升项目格式；由桌面明确选择连接/资源，保留本机未认证身份标记和现有1–100行限制。分析提案持久形式与科学参数仍待所有者。最终准备入口也须支持既有MuPRO工作流/案例行，不把目标缩成仅支持AI新建扫描行；开始仍须完整计划复核。
- **目标：** 核对 agent 工具/事件、项目运行和桌面桥，提出最小契约及反例矩阵：冻结计划、受信任桌面人工单次批准、prepare/submit 分离、原请求/幂等键恢复、撤权/CAS和取消/观察区分。
- **范围：** 有界只读当前源码、相关发布契约及测试；只在外部证据目录 `claude/s2c-plan-05.md` 交付源码依据、建议路径和测试清单，不改两棵树的产品、文档或认知资产，不提交推送。
- **边界：** S2c方向获准不代表无限自动执行；不代选扫描数值或分析提案持久形式，不调用真实求解器或收费模型，不改凭据/端点/网络策略。root 审查后再安排具体实现模块。

### CL-S2C-FIRST-CLAIM-06：工作流首次批准启动的原子门

- **状态：Claude已交 `867eef9b7565a46f69dfba7c02a1b2e835de721c`，root选择集成 main `afef46c5`。** 两文件限定提交，38项工作流及13项归档/关注回归通过；去掉历史started门时2失败，去掉事务内归档门时1失败。root联合及MuPRO旧链另见运行验收，不将本模块当完整S2c。
- **唯一写入：** `suan/project/workflow_runs.py`、新增 `tests/test_workflow_run_approval.py`。不改两树其他源码、全局文档、契约或认知资产；不推送、不运行共享CMake/真实Runtime/许可软件/模型。
- **接口：** `WorkflowRuns.start(..., approval=None)`；省略时保留原人工启动/重启行为。非空为封闭四键 `{approval_id, plan_sha256, request_sha256, expected_revision}`，严格核UUID、小写SHA和非bool整数。
- **原子约束：** 与追加started同一BEGIN IMMEDIATE内核原计划/请求摘要、当前项目修订、当前workflow_run归档状态，并拒绝任何历史started；started保存验证后独立复制的approval。此对象是前置条件和审计绑定，不是身份认证或可复用授权。
- **验收：** 错形/漂移无新事件，批准后停止不可再批，普通启动后停止不可转首次批准，原人工重启兼容；不同store并发及真实跨进程SQLite竞争不能双认领，归档/输入变更不绕过。测试KEY空/MODEL缺席、暂存gitleaks后仅提交两文件并交精确SHA。
- **root职责：** 会话批准记录的单次消费、原身份恢复、工具/桥/桌面接线及版本契约仍由root负责。单独会话锁不能排除编辑器并发启动，所以本门必须落在工作流事务内；本模块交付也不等于完整S2c可用。

### CL-S2C-LEDGER-REVIEW-07：单次批准持久层复核

- **状态：只读报告已回报；R1已由root修复并提交 `67670ae3`。** 旧`_observe`把运行卡当草稿导致KeyError；root两个红例先失败、修正后最终联合99通过。Claude独立探针确认修复，审查时小组38项通过不等于root最终99项；报告在外部证据目录，不改两树产品文件。
- **已核：** SQLite原子消费、重放不再派发、原tool call/计划/请求/修订绑定、归档、原started回执及普通手工重启；未知回执只观察。身份明确未认证，工具/派发/桥/桌面尚未接入。
- **root裁决：** 既有MuPRO案例/工作流行也在最终范围内，C2“仅AI新增行”不作为强制条件；会话busy与桌面资源选择须在接线时实现。先消费后失败仍不能再次派发。

### CL-S2C-EXECUTOR-08：将批准传入后台执行器

- **当前状态：** Claude `8577335ad0fe693321215e55397df4b38a6aeb65` 已选择集成 main `c39f31e4`；root 独立联合32项通过。后续目标绑定、工具与原生接线由 root 统一交付，原任务记录保留如下。

- **原任务范围：** Claude独立树从`867eef9b`继续，仅写`suan/desktop_bridge/workflow_runs.py`及新`tests/test_workflow_run_executor_approval.py`；当时两路径由其独占，集成后由root接线。
- **接口与验收：** `WorkflowRunExecutor.start(store, run_id, *, approval=None)`；省略时原行为不变，非空须经store原子首次启动门，不能因已有活job就返回批准成功。保留容量/关闭检查、线程失败stop及原手工重启；真实SQLite/受控线程覆盖错绑定、并发、线程失败和已启动拒绝。
- **边界：** 不新增工具、桥路由或权限，不改并发上限/CMake/全局状态/AOCI，不运行Runtime、许可软件或模型；暂存扫描后只提交两文件，由root审查、集成和推送。不得另向peer委派。

root 已核对 `6f4de650` 整个 Desktop 失败终态；继续按最新决定优先 MuPRO/MuFerro 执行器与 HDF5 试点，
原生文献 UI、Synthrix 正常装配/桌面入口及 D1-D5 保留在队列，按真实依赖推进。
其他模块仍须 root 明确路径和验收后再派发。

- **后续 CL-S2C-PREPARE-09：** Claude 在自己的 worktree 交付 `6d9d0e08deebe194bb03c1f42e165e02051403b0`，仅新增 `suan/agent/muferro_runs.py` 与 `tests/test_agent_muferro_prepare.py`。模块支持既有 MuFerro 案例行，使用桌面冻结目标，只冻结本地计划并生成首次批准项；自身不注册工具、不联系 Runtime。Claude 最终联合61项通过，领域门/回放门红例分别4项和2项失败，恢复后扫描通过。root 集成时另补混合 frozen step 的回放边界及测试。
- **后续 CL-S2C-WIRE-REVIEW-10：** Claude 只读复核 root 集成后的 helper 边界与新增契约，外部交审阅证据，不改业务或认知文件、不提交推送。
- **root 原生辅助任务：** 另一 Codex 代理在独立 detached worktree `/home/mnemora/xcheng/sijin/stk-native-runs` 交付卡片控制器/UI/双语及 CPU 用例 `6f009292`、`52bb7b4d`。root 审查并修正陈旧计划拒绝入口、历史状态标签及真实指针点击用例，负责共享 CMake/最终构建。此辅助代理不是 Claude，Claude 的模块归属和独立 worktree 不变。
