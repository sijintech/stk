# Codex / Claude worktree 协作约定

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

- **状态：已派发，尚未集成。** Claude独立树从`867eef9b`继续，仅写`suan/desktop_bridge/workflow_runs.py`及新`tests/test_workflow_run_executor_approval.py`；root不并发修改这两路径。
- **接口与验收：** `WorkflowRunExecutor.start(store, run_id, *, approval=None)`；省略时原行为不变，非空须经store原子首次启动门，不能因已有活job就返回批准成功。保留容量/关闭检查、线程失败stop及原手工重启；真实SQLite/受控线程覆盖错绑定、并发、线程失败和已启动拒绝。
- **边界：** 不新增工具、桥路由或权限，不改并发上限/CMake/全局状态/AOCI，不运行Runtime、许可软件或模型；暂存扫描后只提交两文件，由root审查、集成和推送。不得另向peer委派。

root 已核对 `6f4de650` 整个 Desktop 失败终态；继续按最新决定优先 MuPRO/MuFerro 执行器与 HDF5 试点，
原生文献 UI、Synthrix 正常装配/桌面入口及 D1-D5 保留在队列，按真实依赖推进。
其他模块仍须 root 明确路径和验收后再派发。
