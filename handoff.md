# STK 当前交接

## 2026-11-07：MuPRO 执行器试点与权限方向更新（当前）

所有者已选择先试点执行器和专业软件，第一项为 MuPRO/MuFerro；数据格式由插件自行定义，MuPRO 使用 HDF5；
同意开发 S2c 智能体 prepare/run 权限扩展。方向已确定，当前工具/发布契约尚未扩展，不能称功能已可用。
实施入口为 [MuPRO 执行器试点](docs/design/mupro-executor-pilot.md) 和 [工作台决定](docs/design/project-workbench.md)。
电场扫描的方向/幅度/单位/步长/推进与采样等由研究任务显式给定；分析修改提案持久形式仍待决定。

root/main 协作规则提交 `37d26464`，Claude 独立 `stk-claude` / `claude/support` 已创建，CL-D1-01 已派发，
后台会话 `89bf764a` 正在工作；新决定已通过该会话排队交付，待 root 核对文档提交，不复用原“ready”状态当当前实况。
Claude 文档头 `9590d21b` 的 D1 清单已由 root 选择性提取并修正事实表述，随本批主线文档集成；D1 两部署验收尚未执行。
CL-MUPRO-H5-01 已另行派发且开始实现，仅两个新文件；独立读取完成后 root 再接 FileSource/connector，不把模块草稿当插件已可用。
root 已运行 MuPRO 配置预检（退出1，当前配置未就绪）及旧链回归（74 pass/1 真实软件资产 skip）。
远端 6f4de650 的 Desktop 整轮仍运行：Linux 三项和 Windows CPU 成功，macOS CPU 文献9项及原生媒体2项失败，Windows原生仍运行。
root 继续 MuPRO 数据/任务集成和 CI 定位；文献 UI 等旧范围保留，详见运行验收。
main 的协作设置 AOCI 31 项两批已应用，Verify/Check/Guide 对当时稳定态均退出0，Guide complete/none；
本节及新试点文档使其再次产生增量，待最终稳定态维护，不借前一 aligned 覆盖新字节。

## 2026-11-07：root / Claude 独立 worktree 协作（当前）

所有者最新决定覆盖此前共用工作树、Claude 只做设计的分工。Codex 为 root，继续在
`/home/mnemora/xcheng/sijin/stk` 的 `main` 负责拆任务、契约、审查、集成、最终验证、AOCI、推送和 CI；
Claude 使用 `/home/mnemora/xcheng/sijin/stk-claude` 的 `claude/support`，配合文档及明确分配的模块和相关测试。
完整规则与首张任务卡见 [协作约定](docs/planning/agent-collaboration.md)。CL-D1-01 为 ready，尚未接单或验收；
首项交付限新文件 `docs/planning/d1-compatibility-gates.md`，不发布 schema、不代选待决。

本轮起始 main 为 `5670f565be32b6be85d187ba2fb2baa22d272341`；实际远端为 `6f4de650`，
旧 11-06 快照中的“远端 350534d / 535b0d63 未推送”已过时。
本轮实时核对同 `6f4de650`：Runtime 42442318483、Docs 42442318504、Secret 42442318534 均 completed/success；
Desktop 42442318655 仍 in_progress，未满足下一代码 push 等待门。协作配置不等于新产品功能验收。
既有六项 WIP 保留；四文档仅前置本次记录，旧正文保留，Claude 工作树只继承提交内容。

root 先跟进当前 Desktop / 记录及认知收口，再做原生文献 UI 与实际点击验收、核实 Synthrix 当前正常启动接线及桌面入口、
推进 D1；Claude 的 D1 前置文档可独立进行。三待决、八项范围与 PET 后置保持。

所有者另已设持续开发目标为 active：root 合理分配 Claude 工作，并审查、验证及合并当前计划相关 PR；
所有者数日后回复问题，期间继续不依赖待决的工作，不把未回复视为授权选择。

## 2026-11-06 UTC：启动会材料、总体框架与多仓协作（当前）

本轮继续同一设计工作，所有者要求为与合作方的固定周会/启动会准备整体框架、开发计划与仓库规划。
已交付 [总体框架](docs/design/platform-framework.md)、[12 周有限试点路线](docs/planning/platform-roadmap.md)、
[多仓库策略](docs/planning/repository-strategy.md)、[约 15 分钟讲稿](docs/planning/research-kickoff.md)和
[10 页投屏稿](docs/planning/research-kickoff.html)。材料本地 main 提交：`325fe57dc955b4e9a69370e60d03f39ad0a6bb7b`，七文件、647 行新增。

共同后端方向保持。建议保留 stk 的后端/原生/CLI/契约与 synthrix 的 React，旧 Node 逐领域迁入；
达到重复交付门槛时新建或复用集成发布仓，候选名 stk-platform。本轮未开仓、改权限、迁移代码或部署。
W0 日期/人员/首演时间未确认，W1–W12 是有限试点候选安排，W2 用实际投入校准；
没有承诺 12 周完整 D1–D5、所有平台或全部科研业务。周会候选 60 分钟，含会前材料、演示、决定/行动模板。

文档交叉审查、60 个相对链接目标/5 个章节锚点及暂存空白检查通过；材料 gitleaks 零发现。
实际 headless Chrome 导出 10 页 PDF，逐页文字/页码可读，并查看架构/仓库/排期页实物；这些不属于 STK 产品 UI 验收。
PDF 与证据在 `/home/mnemora/.local/state/stk-validation/stk-kickoff-plan-20261106/`。

实时 Git/CI：远端仍 350534d；Desktop 41639295121 completed/failure；本地前代码头 535b0d63 无对应 runs。
本轮仅本地文档提交，不连带推送旧源码，不触发 CI；未运行新产品/科研/GPU/许可测试。
沿用所有者已批准的本设计直接证据方式，AOCI 加载/维护继续暂缓；配置/baseline 及六项既有 WIP 原内容保留。
旧八项范围、三待决与 PET 后置继续有效。以下先前三项设计与历史交接保留，当前材料入口以上方为准。

## 2026-11-06 UTC：当前交付为统一后端三项设计

本轮按所有者要求先完成设计，未继续功能实现。STK Core 与云端采用同一后端代码、领域服务和状态机；
Desktop 保留 C++ / Python / GPU，Synthrix Web 保留 React。三项设计已交叉审阅并本地提交 main：
`f541393b31b9f32b1f73bc738998075bc93e6dbd`（设计及两处设计入口，共五文件）。

- [架构边界与迁移](docs/design/shared-backend-architecture.md)：以现有 suan 服务为基础，明确 Synthrix 领域迁移、部署角色与唯一写入归属。
- [任务与数据协议](docs/design/distributed-task-data-protocol.md)：保留当前 Runtime/Hub/Bridge 版本，区分任务/action/运行记录，增加拟议身份、租约、数据副本和恢复边界。
- [跨端验收](docs/design/distributed-workbench-acceptance.md)：同后端双部署、真实跨端链、15 项故障和 4 项迁移场景；所有新运行/点击结果均未执行。

核验基线为本地源码 535b0d63、Synthrix 当前网页 a15ab6b；后者没有旧 90d7c4a 接缝，后续不能沿历史交接推定已有集成。
实际远端 STK main 仍为 350534d；该头 Desktop 41639295121 与 Runtime 41639295206 均 completed/failure，Docs/Secret success。
535b0d63 尚未推送，按该 SHA 查询无 CI；本轮文档仅本地提交，不连带发布旧源码，也不触发或重跑 CI。

验证：五份设计 87 个相对链接目标存在、代码围栏配对、暂存 diff 空白检查通过；最终暂存 gitleaks 零发现。
未运行产品测试、构建、模型请求或实际 UI。下一步为按 D1–D5 实施前逐项落定新 schema/兼容门，不能把 D0 设计完成当功能验收。
旧八项范围、三项待所有者决定和 PET 专项后置继续保留。

AOCI 例外：所有者在本轮明确允许直接证据设计并暂缓完整加载/维护；宿主此前截断且 chunk_tokens 已是最小 4000。
本轮未改 aoci.txt、baseline 或配置，未声称索引已对齐。四份既有状态文档的原内容原样保留，本节为新增当前快照。
证据目录：`/home/mnemora/.local/state/stk-validation/stk-unified-backend-design-20261106/`。

以下 2026-11-03 及更早内容保留为历史，不覆盖本节当前 Git、CI、AOCI 与实施范围。

更新：**2026-11-03 UTC，所有者恢复持续开发目标；完整计划未完成，目标保持 active。**
STK 作为主体，融合 Synthrix 对话与科研管理；本地完整、Web 轻量、分布式节点、跨位置 CLI 与插件底座为当前方向。
详见 [分布式科研工作台](docs/design/distributed-research-workbench.md)。旧冻结转交点为历史；旧八项范围、PET 新专项后置和三待决保持。

## 2026-11-03 当前恢复批次

恢复起点为 main/HEAD/origin/main `3ef4b2716d42304d708062f9715edae0afb5874f`，逐文件 91 WIP（33 tracked/58 untracked），暂存空。
已保存原路径/大小/SHA 与旧四文档，证据根 `/home/mnemora/.local/state/stk-validation/resume-platform-20261103T110725Z`。
本批已完成 encoder profiles 真实回归、LiteratureService 来源/恢复审查、公开文献 Bridge 接线、Hub/Runtime CLI 纵切面，
并补修 S4 接收撤权竞态。S6、文献、S4、全量整合和 wheel 的来源/范围分别记录，不能互借结论。
`integration-02/native/summary.json`：2075/2075、零fail/error/skip，build19.251s、ctest490.527s，1291输入稳定。
`integration-02/python/summary.json`：5489pass/74skip/4deselected/1warning，pytest1207.90s、wrapper1211.584s，5563实际案例、973输入稳定。74skip含显式encoder资产、Flower、旧离屏SIG11、Windows、MuPRO和可选依赖；69项真实推理为独立来源证明，不算本全量已执行。integration-01的两失败和两文件来源漂移保留。
Hub CLI相关9文件187pass仅有控制台记录，没有独立XML/前后source proof；不制造补证。
当前 wheel 已离线构建并在新Linux隔离环境299/299、零skip验证，四个真实模型/PDF案例明确deselected；最终sdist未完成。
Root继续负责最终整合、治理、暂存扫描、main提交与新头CI；本批尚无新commit/push/新头CI。
Root收口再次GET同3ef/attempt1的整个前头Desktop41178119889：completed/failure、updated2026-10-31T07:34:01Z；恢复时Runtime41178119790为success。均不覆盖本批WIP，前Desktop终态只满足后续push等待条件。
下方91 WIP是11-03恢复起点，11-02环境/旧证据作历史线索；当前路径计数须按实际Git核对。

## 接手顺序

<a id="当前接手顺序"></a>
<a id="接手先做的待办"></a>
<a id="接手后的实施顺序"></a>
<a id="当前续接与下一步"></a>

1. **接手整个工作区。** `/home/mnemora/xcheng/sijin/stk`，`main`。11-03恢复时HEAD/local origin/main/远端main均为 `3ef4b2716d42304d708062f9715edae0afb5874f`，91 WIP（33 tracked/58 untracked），暂存空；本次收口再次核本地HEAD仍为该3ef，暂存空。后续新增接线/测试使91不再是当前路径计数。wheel见上方及运行验收；尚无本批commit/push/新头CI或包含全部WIP的便携交接包。只clone main会遗漏实现；不要reset/clean/覆盖WIP。
2. 读 AGENTS，按实时规则建立新 Run 的完整 AOCI 认知，再核源码。索引仍 Dirty/Stale；此文件和历史收据不能代替当前认知。
3. encoder profiles 真实联合69/69、14输入稳定；服务三父Python各26/26、20输入稳定。公开Bridge最终54/54、27输入稳定；一次真实E5链发现Schema遗漏已修，实际缓存DTO重验/页渲染/撤权完成，详见下节。原生UI仍待完成。
4. 独立heldout已按冻结release一次完成：Qwen同语120/120、跨语119/120通过原门；E5 reference同语120/120、跨语24/120。仅一般段落检索诊断，原科学PDF质量失败保留；INT8不采用、不按曝光heldout调参。
5. S6最终Schema下三Python各430/430、零skip、334输入稳定，绑定后续file_store.accept修复前SHA。S4最小CAS补修2红→绿；当前联合460pass/2个Windows-only skip、来源稳定，独立三Python各10/10、220输入稳定。Linux原生整合2075/2075、Python整合02为5489pass/74skip/4deselected（973输入稳定）、wheel安装299/299均已终态；各自平台/依赖边界见运行验收，01失败与旧全量不替当前来源。
6. 继续原生精确引用、隐私 RAG/授权共享、P4/S4 平台与网络、真实 MuPRO 论文、发行安装、AOCI/main/新头 CI。八项计划均不能由后端测试或制造夹具替代。

11-02历史交接审计 `HANDOFF_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-owner-20261102/handoff-20261102T2138Z`：`previous-docs/` 保存改写前四文档，`before.json` 保存全部91路径状态/大小/SHA，`closure.json` 保存最终检查。交接只改四状态文档，87份其他WIP保持原字节。外部证据和模型资产为本机路径，异机须另行移交必要非敏感源码/证据和按许可准备资产；不搬身份、凭据、私钥。

以下 `OWNER_NEW=/home/mnemora/.local/state/stk-validation/s4-owner-20261102`，`OWNER_OLD=/home/mnemora/.local/state/stk-validation/s4-owner-20261031`。证明只适用于各自记录的来源/平台。

## S5 当前源码：profile 回归与服务接线

11-03独立审查确认并修复 `DenseIndex.hybrid_search` 把Qwen融合检索误标为E5的问题，现为 `local_fts5_qwen3_rrf`；E5标识保持。
新反例修前23pass/1fail，修后纯守卫24pass/2真实案例deselected。
`OWNER_NEW/encoder-profiles-review-20261103-01/closure.json`：真实E5/Qwen/PDFium联合69/69，零fail/error/skip，501.730秒，14输入稳定。
其中Dense33、Collection10、profiles26，含真实1024维编码/跨库/1024→384显式重建后历史引用及混合profile推理前拒绝。
这不覆盖独立heldout、科学PDF质量、Mac/Windows或RAG答案。

`OWNER_NEW/literature-service-review-20261103T110738Z/`保存服务审查反例与修复：先核原UUID/原请求再检查新派发的当前可信解释器，
使配置改变后仍可观察旧admission；换原请求冲突，新UUID不能借旧解释器派发。正文/PNG仍重查当前授权和原DB/来源fence。
最终纯测24/24，2真实案例deselected；真实三父Python各26/26、零skip、20输入稳定，80.504/79.296/82.287秒，见同目录 `matrix-01/closure.json`。
`OWNER_NEW/literature-bridge-contract-20261103-01/final-closure.json`：最终54/54、零skip、27输入稳定，含46新增合同/隔离、6既有及2实际缓存续接。
原fresh E5推理链45pass/1fail发现parser DTO遗漏3字段；Schema精确补齐并保留旧内容，10项实际已完成DTO通过strict Bridge和jsonschema重验，
继续真实PNG/geometry和撤权缓存拒绝。最终轮明确deselected原fresh推理函数，未重复模型推理；保留全部失败，不能描述为一次全新54项真实模型全链。
20个 `literature.*` 已登记且全部desktop-only；默认惰性、只有宿主构造可指定可信解释器，无新stdio/RPC配置入口。

### 11-02历史实现起点（当前结果以上方11-03证据为准）

以下保留实现与资产来源说明；当时的测试/接线待办已由上方69/26/54项证据取代，原生UI及其他未交付边界保持。

新增 `suan/literature/encoder_profiles.py`，同时修改 `dense_worker.py`、`dense.py`、`collection.py`；完整 `tests/test_literature_profiles.py` 在11-02当时已保存未运行；11-03真实回归已完成，见上方当前记录。profile 精确 pin 全部资产文件/大小/SHA/许可和 recipe，拒未知模型/数值类型漂移；manifest 允许有界 legacy license_evidence 注记。`worker_identity_sha256()` 绑定 worker **及 profile helper**，替代旧单文件SHA。

该批新增 `e5-small-cpu-f32`（旧 E5 recipe/384维/mean pooling）与 `qwen3-0.6b-cpu-f32`（Qwen/Qwen3-Embedding-0.6B，revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，Apache-2.0，1024维/last-nonpadding-token）。均 CPU float32、2 threads、完整连续窗口/512 token/L2；Qwen left padding/eager/use_cache=False、指令 query prefix、空 passage prefix。SQLite schema 未升级，显式 rebuild 后应保留可解析的历史 generation。两种 retriever ID 分开，跨库 top20/RRF recipe 保持。

这不是桌面模型设置变更、现有库自动迁移或已验收发布。**INT8 只有外部失败实验，未进支持目录，不应自动 fallback。** 新测试包含实际Qwen、双库检索、1024→384重建后的历史引用、混合profile提前拒绝、损坏向量；缺真实资产导致skip不算通过。11-02提出的守卫及真实回归已按上方69项证明完成，旧43项不替代新增helper/test；不要改旧科学语料库来测试。128MiB DB等预算保留，不偷偷清历史或假设所有最大规模可同时容纳。

```text
E5 assets=OWNER_OLD/s5-dense-01/assets
E5 manifest SHA=301ef8fcc5b1cf59cb7f55cd7bbc07e5f852f3deca2f89f4f1c548d20b1c2d71
Qwen product assets=OWNER_NEW/encoder-profiles-01/qwen-assets
Qwen product manifest SHA=a19c7b0bc8004ab97bf6900a7552a0921f09577d5ec0d2851db51e30639ed69c
shared encoder Python=OWNER_OLD/s5-dense-01/env/bin/python
```

Qwen product view 为11个已核公开资产的普通硬链接和独立 product manifest；原下载证据在独立实验，原 manifest SHA `10c565ccd161395d2509893833e1ca238fc03d9c6ade5254e973d06ba1db3750`，格式不同，不能混用。实际 Linux Python3.12/Torch2.14.1+cpu/Transformers4.57.6；不作Mac/Windows证明。`encoder-profiles-01/{before.json,previous/}` 保留修改前五文件，权重不进仓库。

LiteratureService 文件：`suan/desktop_bridge/{literature.py,literature_worker.py,worker_process.py}`、`tests/test_desktop_bridge_literature.py`、`docs/specs/stk-desktop-literature-1.md`。11-02当时的双profile/bundle/timeout适配预计25项；11-03修复后实际为三父Python各26项、20输入稳定，见上方matrix-01。旧 `OWNER_NEW/literature-service-01/validate-final.py` 不是当前证明入口，不原样重跑覆盖旧目录。下列约束已纳入当前审查/验证，后续仍须保持：

- 可信构造固定 encoder/parser Python，兼容wire值必须匹配；metadata review核资产/profile/runtime而不加载权重，当前配置授权与历史DTO分开；空Qwen passage prefix不能被E5假设拒绝。
- 惰性私有state、最多8库/2 owned worker trees/仅1模型job、有界队列/磁盘/DTO；Library操作日志和service journal分开。原UUID/冻结请求，重开只观察，不自动resume/replay/换ID。
- cached text/PNG交付前核原DB UUID、逐版本当前授权、保留generation和精确citation，不重parse/infer；跨库用两遍UUID/approval/monotonic generation fence。Library全局连接gate禁止同时持两个_db，不声称系统原子快照。
- search的hit/citation/window身份、rank/order/duplicate/RRF精确核对；canonical JSON保数值类型。被动`corpora.info`是当前generation观察，历史receipt不是当前状态；不自动收养/重建库。
- dense.build显式整数timeout1..3600并冻结，外层+10秒清理；完成在owned tree reap后发布。环境白名单、KEY空/MODEL absent，不读取HF凭据值。
- page PNG≤4MiB/2048边长/4M像素，保PDF→pixel affine/quads和parser身份；PDF留本地。不得伪造Report/project身份，或把整PDF塞NDJSON。

旧证据 `literature-service-01/`：`matrix-01/closure.json` 三父Python各21/21零skip、19输入稳定；`service-09.xml` 22/22含被动corpora.info/真实E5与PDF/撤权/DB替换；`worker-regression-01.xml` 38/38。均早于最终profile适配，仅证明11-02当时来源；11-03当前26项矩阵见上方。WorkerProcess未再改，SHA `a7117b008d809c40d411a9f469e6564f3f154c8889457c3ca908828d18d44f0a`；失败历史保留。

11-03已接`server.py`、精确Schema/spec及DESKTOP_ONLY，并验证惰性构造/关闭。Root另完成当前Schema的C++64正反例探针，编译运行exit0；事后观察记录见恢复证据根 `integration-01/literature-native-probe-observation.json`，仅post-observation哈希，未伪造前后来源快照、未重复运行。原生Literature控制器/稳定编辑器ID仍待实现：显式导入/复核/索引/build/search、页段定位高亮、来源失效/草稿/关闭，记录固定起点实际点击数并保护Viewer/隐藏稿。生产stdio尚无parser/encoder解释器选择入口，初版使用宿主默认Python；缺依赖明确unavailable，不给RPC任意exe。再隐私RAG、授权陪读、文字/结构化共享，之后语音/窗口画面。旧Qt截8000字符不替代此路线。

## 检索评估：保留科学PDF失败，独立 heldout 一次评价完成

11-03独立release `OWNER_NEW/retrieval-quality-independent-01/heldout-release-20261103-01/closure.json` 已执行完整、41输入稳定。
锁原protocol/driver/selection和product profile/资产/tune证明，独立审查补齐资产绑定和自有进程SIGTERM回收后，E5仅reference、Qwen仅selected各跑一次；未改原selection或门槛。

| 独立heldout角色 | 同语hit@5 | 跨语hit@5 | 跨语方向 | corpus编码 / peak RSS |
|---|---|---|---|---|
| E5 FP32 reference |120/120|24/120|EN→ZH 23/71，ZH→EN 1/49|45.087s /1,383,944KiB|
| Qwen FP32 selected |120/120|119/120|EN→ZH 70/71，ZH→EN 49/49|627.881s /3,898,360KiB|

Qwen通过原同语≥.85、跨语≥.85、各方向≥.75门。wrapper各次wall57.975/706.920s。
这仍是派生XQuAD一般段落定位、同机单次且可能有预训练污染；不证明官方QA、科研PDF、完整引用/RAG答案或其他平台。
原40QA科学PDF失败与INT8失败保持，已曝光独立heldout不再用于调参。以下保留此前tune与起点说明。

首次scientific PDF评估 `OWNER_NEW/retrieval-evaluation-01/run-01/summary.json`：4PDF/23页1051段、两库、冻结40QA-v2（34可答/6不可答/91引用）；2build+80查询810.474s、执行完整/源稳定，**主质量门失败**。全局heldout hit@5=12/18<.85，EN6/6、CN6/6、cross0/6<.75；完整证据包@5=4/18、@10=7/18，MRR10=.625。不可答非空6/6不是拒答准确率；literal lexical无gold、fused=dense，known-source baseline不替全局主验收。不改原QA/门槛、不用曝光heldout调参。两库现已有dense generation，旧fresh/no-dense driver前提不成立，不能原样重跑或覆盖失败。

独立公开开发实验 `OWNER_NEW/retrieval-quality-independent-01/`：XQuAD官方commit `7d30520c717524000f0d9d2f9c10a069acd9d285`，48文章/240段，每段只留一种语言（121ZH/119EN），全库候选；按整篇文章24tune/24heldout，480配对问答。以下是tune的120同语+120跨语查询；不作官方XQuAD QA、PDF、科学或RAG验收，预训练污染未知、同文相关、单机单次资源有局限。

| 候选与summary目录 | 同语hit@5 | 跨语hit@5 | corpus编码/peak RSS | 实际结论 |
|---|---|---|---|---|
| E5 FP32，e5-tune-01 |119/120|12/120|50.055s /1,357,760KiB|执行完整、源稳定|
| Qwen FP32，qwen-tune-01 |119/120|115/120|606.868s /3,894,632KiB|tune family选择三门通过；非heldout|
| Qwen INT8，qwen-dynamic-int8-01/run-01 |115/120|101/120|608.880s /3,899,116KiB|optional_profile_gate=false|

INT8固定Torch原生dynamic qint8/x86：196/196 Linear转换，转换4.629s、total689.557s；质量非劣、半耗时、RSS门失败，仅两跨语方向≥.75门通过。`run-closure.json` exit0/未超时/owned_child_reaped=true、elapsed690.602s，只表示执行完整。未重跑、改门槛或采用。

冻结身份：protocol SHA `74118c11987b26de75b693d7d456fc4135067fbfff8a12a3c55db2864ae42faf`；原evaluate.py SHA `65e2f18b5bfdff0c82b3db95fce0c7bba9c2306e979e2564c1507b3c4fda271f`；tune后冻结的selection.json SHA `454195930d14f06364b2b59c5915af9841d88ff373f88c7a8f32e56c1c15876d`，选择Qwen family，**不可覆盖**。量化protocol SHA `05529c7a0a5d1fb3cd0b38298151e30ca2fb86e77f133f6d973b6b51910fde55`；独立审查/root-release保留。

11-02待办现已按本节上方release完成：原driver的heldout guard未充分约束selected_model/allowed set、selection未入before/after，故使用已审查/哈希绑定wrapper而不改原driver。固定门后一次评价，曝光后不再调参到通过。top20 windows cap与生产一致，tune候选最少18/19个不同段，均无低于10，未观察hit5/10截断。FP32 corpus超过旧600s build限，当前服务只新增显式timeout，不声称交互或通用CPU性能。

## S6 当前软件闭环与真实复现缺口

核心`suan/reproduction/{__init__.py,comparison.py}`、节点`suan/graph/nodes/reproduction.py`及spec/catalog/tests已入仓。compare/verify和`stk.analysis.reproduction_compare@1`输出完整JSON/typed ErrorTable：显式单位/容差/domain、exact或明确linear，禁外推，missing/failed/单位不兼容保持indeterminate；不猜换算，不认证原观测。57核心+40节点新案例在三Python均执行通过。

四工作流文件已保存：`examples/reproduction_comparison/{README.md,offline.py}`、`tests/test_reproduction_workflow.py`、`docs/reproduction-comparison.md`。真实headless API→Files/Snapshots→保存AnalysisRun→显式start→Agg PNG/精确数据→Report/1 review SHA/CAS→分离显式export/reopen/tamper；五种自写解析场景。动作前保原UUID/请求，丢prepare回复只读原run核完整定义/binding，丢report回复不重造ID。18资产精确成员/原archive bytes/实际plot x/y有独立验证；notes非backend receipt。归档inline ErrorTable省Field dtype/lossy，原精确数值/描述在comparison JSON，不扩大保真声明。无Viewer/current project/layout/模型请求变化。

Root复现FIFO阻塞后已修ordinary/nofollow/nonblock打开、前后身份/稳定性/完整字节数；Windows有CreateFileW/reparse守卫，跨stat API不比ctime/fullmode；_new exclusive/0600。独立复审补短EOF守卫。实际Windows仍未验。

| OWNER_NEW下证据 | 结果与边界 |
|---|---|
| reproduction-comparison-01/final-02/closure.json |三Python各57/57零skip、源稳定；比较软件非科学结果|
| reproduction-graph-01/matrix-02/closure.json |各195pass/1旧CLI离屏skip、25输入稳定，新增97全过；311/314缺VTK、312旧probe SIG11|
| reproduction-workflow-02/matrix-02/closure.json |各415/415零skip、252输入稳定，95.875/94.644/94.878s；早于最后FIFO修复|
| reproduction-workflow-02/io-final-01/closure.json |各41/41零skip，70.154/72.274/72.833s；source_stable=false，唯一漂移literature.py，需冻结后补验|

当前offline SHA `86a9d411b847be5024c9b8dabc4eacf2e9e85117c28f06d0645cbfce0be86dd5`、test SHA `b04b643dbaea7105de2dab0a2e76eeabfc91b2e5c864f799f9805b5be89f2f34`。不要在writers活动时机械重跑252输入矩阵。

**真实S6尚需**：合法可用MuPRO、论文/数据许可、参数/单位/边界/初始条件/domain/time、冻结输入/solver身份、明确执行、独立参考曲线、不确定度/敏感性及含失败缺参的来源报告。`mupro-reproduction-readiness-01/{local-readiness.json,bounded-location-probe.json}`仅有界检查显式设置/候选位置/PATH未就绪，不是穷尽无安装；论文候选未核准，无已连通远端solver证明。未读license内容/私有SDK，不猜待决电场扫描；PET/制造夹具不作替代。

## 已有基础、平台和完整八项待办

PDF/Store `OWNER_NEW/resolve-many-01/closure.json`：三Python各92/92零skip、9输入稳定；runtime.yml门禁92唯一/68必跑、3真实XML/3Python接受、76负例拒绝。Dense/Collection `literature-43-01/summary.json`旧E5真实43/43零skip、410.435s/14输入稳定，早于当前profile。引用benchmark-02完整1051结果/顺序/几何等价、22输入稳定，31.489→3.248s仅解析循环约9.7倍，非端到端/RSS。Store schema/UUID/当前授权/hot-journal/合作SQLite gate继续保持；未知库不收养/迁移，非合作任意SQLite写入不在保证内。

旧peer证据相对OWNER_OLD：`peer-bridge-loader-rebind-01/closure.json`129输入稳定，312为123pass/1Win-DPAPI skip，311/314为122pass/2skip（另可选VTK）；`peer-native-ui-02/closure.json`19/19零skip、971输入稳定，1440×1200/en/scale1/maximized-a4，已认证发送起点13点击/0滚轮、已认证+Offer接收7/0，真实两helper/字节，Viewer/隐藏稿保护。对端是显式API夹具，不代完整连接UI/双GUI/OSGPU/NAT/跨站。

Linux helper `OWNER_OLD/helper-package-01/relocated/stk-peer-runtime`有UDP/TCP/IPv6重定位，34组件/40ELF/252文件/105源资产；不代任意Linux ABI/Mac/Windows/干净机。别重跑会改名prefix/覆盖证明的旧relocate_and_run.py。旧4716 Python/2056 native/安装585、peer581/580和240MiB测试仅保原来源；tracemalloc不是RSS。

本次重新GET同3ef/attempt1：[Desktop41178119889](https://github.com/sijintech/stk/actions/runs/41178119889) completed/failure，updated2026-10-31T07:34:01Z；[Runtime41178119790](https://github.com/sijintech/stk/actions/runs/41178119790) completed/success，07:03:28Z。前整个Desktop终态满足push等待前提，不代表P4/WIP通过。Mac floating-from_chars补丁仅Linux证明；Win原生5/6的HTML-video divider失败及有界诊断保留，根因/新OS复验未闭合，不能放宽像素/暂停/20轮161图门槛。

| 路线 | 尚需开发或验收 |
|---|---|
|1 表格/节点|类型编辑/详情/undo/redo/草稿回归，明确保存/运行/发送|
|2 工作台复用|富对象/大表/填充/看板/布局/子流程/技能的规模、真GPU和平台验证|
|3 P4 文档报告|新头Mac/Windows MD/HTML/PDF/LaTeX/图片/视频/混合文档、原生捕获20轮、导出重开、IME/跨屏DPI/GPU|
|4 S3训练|冻结/迁移/比较/准入回退的目标平台和真实材料/样品独立评价；线性联邦非曲线MLP|
|5 S4协作|helper目标OS/干净机、完整配对连接UI/Mac↔Windows；站点授权会合信令、IPv6→UDP端口预测→TCP→TURN/TLS443策略和跨机构、独立Flower网络训练|
|6 S5文献共享|profile/服务/Bridge软件验证已完成本批范围；继续科学PDF质量、原生引用UI、隐私RAG/授权陪读/结构化共享，再语音/窗口画面；一般XQuAD heldout不替科学验收|
|7 S6真实复现|真实MuPRO论文、完整参数/参考/不确定度/敏感性和来源报告|
|8 P5/S7发行|干净机离线安装/Python/文件对话框/IME/DPI/快捷键/恢复/性能/模型更新回退、toolkits兼容/wheel/sdist；ABACUS按依赖|

<a id="三项待所有者决定"></a>

**不能擅选**：（1）合作方S3格式和MuPRO电场扫描；（2）S2c智能体prepare/run权限；（3）保存分析修改提案的持久形式。内部capsule/比较节点/desktop-only服务不构成这些决定。PET新字典/厂内专项/专用训练/长链气体收敛后置，保护已有功能。

## 环境、验证和交付规则

```text
base Python3.12=/home/mnemora/opt/stk-venv/bin/python
new parent Python=OWNER_NEW/reproduction-workflow-02/envs/{311,312,314}/bin/python
PDF/Store Python=OWNER_OLD/s5-foundation-01/{env-311,env,env-314}/bin/python
empty Python=OWNER_OLD/s5-foundation-01/empty-env/bin/python
encoder Python=OWNER_OLD/s5-dense-01/env/bin/python
native build=/home/mnemora/opt/stk-build/merge-check
sysroot=/home/mnemora/opt/stk-sysroot
helper prefix=OWNER_OLD/helper-package-01/relocated/stk-peer-runtime
uv=/home/mnemora/.local/bin/uv
gitleaks=/home/mnemora/.local/state/stk-validation/s4-flower-20261030/tools/gitleaks-8.30.1/gitleaks
offline builder=/home/mnemora/.local/state/stk-validation/p4-video-20261029/package-check/build-env/bin/python
```

测试一律`env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY=`，不读/打印/保存secrets，不收费模型请求。新profile需STK_LITERATURE_QWEN_ASSETS/STK_LITERATURE_QWEN_MANIFEST_SHA256/STK_LITERATURE_QWEN_PYTHON和现有E5/parser fixture；命令先读当前源码/validator，输出用新目录，禁覆盖旧proof/旧fresh-corpus driver。主环境/parser/encoder/Flower分开，不随意改依赖。

native cache开启STK_PEER_NATIVE_APP_ACCEPTANCE=ON，完整ctest须STK_TEST_PEER_INSTALLATION=<helper prefix>，缺prefix失败；单native build写者。
11-02 交接时全部协作代理冻结、INT8 session62558已终态并回收自有child，这是历史记录；11-03 当前协作任务见首节和实时工具状态。
共享机器可能有其他会话/CI，不宣称全机空闲、不杀未知进程，观察超时不等于进程终态。

提交前独立审查最终diff、适当联合回归、wheel/sdist/隔离安装，四状态文档同步、最终稳定AOCI维护；暂存变更须gitleaks `.gitleaks.toml`过再commit。默认main，不routine分支/PR，不合无关PR；push前再核前整个Desktop终态，跟新头CI如实记失败。本批已运行上述软件测试/构建与wheel隔离安装；本次四文档收口不改业务源码、不stage/commit/push。最终sdist、治理、提交与新头CI仍待Root完成。

## AOCI 当前状态和安全续接

MCP0.1.0-rc21，CLI `/home/mnemora/.local/bin/aoci`。11-03最新Root完整Overview已24/24交付confirmed、Challenge9/10 pass，覆盖1144条、estimated165707 tokens；完整交付与严格校验通过，治理仍Dirty/Stale，不能称全量aligned或当前完整系统认知可靠。此前同日context_compaction链在21/24块后于第22块返回 `cognition_snapshot_unavailable`，该失败链未确认/未Attest，保留为历史，不再作为最新状态。下一Agent不能继承Root当前Run认知资格，仍按AGENTS建立自己的可靠认知。

此前失败链仅供排错的安全身份：index/scope `289be6ffd55ee88d742bbee3164d450f0e4ec90f41c9b417397f3dcea834e3a6`，Composite `86d326dc722396408b1f9df4812b22f6d9ae0f96f288749f862a300e36ff94a0`。不保存正式Whole-Index/Header/Entry/Chunk/Challenge/Attestation正文。新Run rules→普通完整overview；已知压缩声明context_compaction和新event ID，跟原cursor到completed，确认交付，仅按新正文提交一次attestation，不用check_only/probe/源码补答。

旧`OWNER_NEW/handoff-20261102T2022Z/`维护为31missing/31stale/31unbaselined/21Observed、候选0/remaining62、无pending tx/Recovery/conflict；之后profile等又变，旧计数不作当前事实。11-02的Maintain/Verify/Check/Guide见历史HANDOFF_EVIDENCE/closure.json，不作为当前债务计数。11-03 Root已逐条审查29条Observed事实并核当前SHA/精确pending set，acknowledge status applied、txn `40bc59963d92d5d733245239`，证据 `OWNER_NEW/observed-review-20261103-01/acknowledge-29.json`。这仅确认Observed基线，不是Entry语义维护或全量aligned；最终维护待四文档冻结后由Root按实时Guide完成，不套模板/缩scope/复用旧ACK。

Guide入口`aoci index agent guide --agent codex --json`；Volumes status --deep unsupported不等于损坏。按需scoped rg/有界读/Serena符号导航，不预热全仓/载全扫描/建第二全仓记忆。公开文档称合作方，archive不进导入/构建/包/测试；产品端点/密钥/网络策略只经桌面明确动作，私有项目不送外部模型。
