# STK 当前交接

更新：**2026-10-31 UTC，按所有者要求转交下一位 Agent**。本次停止扩展产品功能，只整理交接和必要认知资产；没有新增代码提交、push、产品测试或CI重触发。源码和测试现已稳定，整份开发计划仍未完成。本快照按推送前状态记录；接手先核真实Git/同头CI，后续CI不能从旧快照推断。

先读 [AGENTS.md](AGENTS.md)、本文件及[开发计划](docs/development-plan.md)。产品决定见[项目工作台](docs/design/project-workbench.md)、[项目模型](docs/design/project-model.md)，发布契约在 `docs/specs/`。继续按**通用能力优先、PET新专项后置**推进。

## 接手先做的待办

1. **保住本地交付。** main上有447a19ac、2513c088两个未推送提交，另有下文六份未提交记录资产；只clone远端6126会遗漏它们。接手同一工作区，或明确转移这两个提交及六份改动；不reset/clean。
2. **核交接收尾证据。** 本次15项完整批次已Apply、1144条，Verify/Check均对齐、Guide complete=true且next_action=none。最后交接文本同步及最终身份见 `OWNER_EVIDENCE/handoff-final-20261031/closure.json`；接手源码未变时无需重做维护。后续有变更才按新Guide/Plan处理，Observed ACK不代Entry，不沿用旧批次身份。
3. **核包来源后提交记录。** 最新交接文档重绑在 `OWNER_EVIDENCE/package-final-docs-02/rebind-summary.json`；它不增加产品测试覆盖。实际暂存改动重新跑.gitleaks.toml密钥扫描和空白检查，再在main提交；当前暂存为空，本次未commit/push。
4. **推送并跟新头CI。** 推送前重查远端第三方变更和上一代码头整个Desktop终态；当前已知6126的Desktop失败结束、Runtime成功。447/2513未推送，尚无新头Mac/Windows验收。记录真实run ID/head/attempt，保留原像素、导航、暂停和20轮/161图门槛。
5. **继续通用路线。** 先P4/S3平台及S4持久身份、配对、授权不可变文件、helper发行和跨站；再S5文献/检索/共享、S6复现、P5/S7完整交付。下面列源码入口、证据和三项待决定事项；PET新专项后置。

## 当前续接与下一步

- 本地main/HEAD **`2513c08817bb9036bc63ffd341503f6d85a29aaf`**；本批主链 **`447a19ac8199c62ba81be5aef5458b4135b04410`**（43路径）加一文件Apple rewind补修2513。推送前origin/main与官方远端仍 **`6126c6a22cc19270aedd135fb97c09b949c49f9b`**，ahead2；常规工作直接main，不另建PR。
- 2513提交后暂存为空、6份tracked记录修改：`.aoci/baseline.json`、`aoci.code.txt`及四状态文档。没有未提交产品/测试源码；原13个新模块已在447，最后Apple改动已在2513。保护记录工作，不reset/clean。
- 完整Python **4716 passed/16 skipped/2 deselected**，独立安装 **585/585**，额外实际owner→worker **1/1**；原生候选完整 **2056/2056零skip**，其后CI守卫补验及Apple补修 **六目标构建、72/72 CPU零skip** 分别有源绑定证据，不能相加或把窄补验称全量重跑。
- P4四份当前源码已完整复核，最后修正529输入稳定；实际暂存1389bytes密钥扫描/空白检查通过并提交2513。真实Mac/Windows仍待新头CI，不冒称平台/跨站/材料验收。
- 11份Observed当前SHA已逐项匹配完整模型审阅，`aoci scope acknowledge`已policy_bound_auto应用（事务f8be6acedab1ccffa0410d6f）。随后正式剩余11项加本次四文档共15项完整Apply，1144条，Verify/Check对齐、Guide complete=true/none；最终交接文本同步证明在 `OWNER_EVIDENCE/handoff-final-20261031/`。此前Observed ACK本身不创建Entry，也不证明整体对齐。
- 最新交接文档包 `package-final-docs-02` 已13.314秒通过重绑：sdist SHA `df2d4fa3cbb177d861cb32dae66a0cff3be6195787b654d401a96672bbc29f40`，wheel整包仍等于已测a6e5…，995源成员只runtime-validation差异、681wheel成员/22选定测试不变。四状态文档仅runtime-validation进sdist，重绑不等于安装或重跑585；本文件之后的最终文字同步不影响该包成员。`package-final-docs-01`的c213…仅保留为上一文档快照。
- 旧05:45转交备份在 `OWNER_EVIDENCE/handoff-20261031T0545Z/`；本轮继续的代码/扫描/Observed确认在 `delivery-02/`。原生构建已终态、窗口释放，不重启旧运行。后续先核正式交付和新CI，再继续下表完整通用范围。

## 已实现的通用 owner 子链

| 范围 | 当前源码入口与行为 |
|---|---|
| 数据/同意 | `suan/federation/owner.py`、`consent.py`、`node.py`：明确登记节点私有数据、固定grant UUID批准/撤回及更新审计。公开标注、Hub配对、peer grant不等于训练同意。 |
| 独立评估/版本 | `suan/federation/evaluation.py`、`models.py`：冻结candidate/base/heldout/当前baseline generation，逐目标绝对RMSE和不差baseline门；Admit只登记，Activate/rollback独立明确操作，防版本/generation/ABA。线性bundle与Materials曲线MLP/model.pt分开。 |
| Runtime | `suan/runtime/{cli,client,common,server,service}.py`：认证 `/v1/federation/owner/{method}`、固定私有root，只用既有direct/SSH；无任意路径/模块/argv，不改产品模型设置。 |
| Bridge | `suan/desktop_bridge/federation.py`、`server.py`、Schema及`agent/levels.py`：冻结项目数值行、有序字段/单位/修订，HTTP前持久保存原操作及SHA；写入Never重试，丢回复查原身份。只供桌面，不加入脚本目录或S2c。 |
| 原生 | `desktop/engine/lib/stk_app/include/stk/app/federation_state.hh`、`src/federation_state.cc`、`src/editors/federation_editor.cc`，AppStore/注册/CMake/i18n接线。稳定ID `federation`；每tab独立View，来源/桥/draft/lifetime epoch隔离，保Viewer/相机/隐藏稿。 |
| 文档/CI | [联邦指南](docs/federation.md)、[联邦契约](docs/specs/stk-federation-1.md)、[桥契约](docs/specs/stk-desktop-bridge-v1.md) additive §17、桌面/模块/结构指南及三平台Federation必跑守卫已进447。机器Schema保留原方法语义，新增20方法。 |

接手修改仍须核源码，重点保护：

- 冻结≤1000总行、64特征、16目标、4MiB；训练/留出UUID非空互斥。单位不推断/换算，未知为unspecified；整数须精确表示为f64。行级互斥不等于样品/材料/站点独立。
- 明确Register会把所选数值capsule经direct/SSH登记到指定私有Runtime owner；raw x/y不进Hub、公共DTO或外部模型。base/delta/private job不进普通Runtime任务输出或普通Hub CAS引用；只公开净化receipt，模型/更新仅在明确动作与授权下经联邦专用通道传送，更新发送须显式collect及同意lease。
- owner信封绑定原UUID、完整原请求SHA和generation。typed rejection七字段proof仅在租约内确认原ID未保留、INSERT/副作用前签发；已有ID冲突、generic400/409、伪造proof、保留后故障或get null均不证明明确拒绝，不能解锁重发。
- **仅Bridge** `federation.owner.operations.get` 返回 `{operation,rejection}`；Runtime HTTP/Client仍raw operation或null。local journal状态completed/uncertain/rejected，不返回原数组。原生消费有效proof后要求明确fresh owner info/新UUID；本地prepare确定输入拒绝可修正后明确新建，通信/不可信回复仍保原身份。哈希保留int/float/负零。
- 已知active CAS拒绝在owner保留前只读preflight，执行时再核；预检后竞态仍uncertain。阈值初始为空，明确由用户填写，不设科学默认值。
- 读/刷新/重开/restore不训练、发送、恢复或激活；重复旧批准不复活撤权；Admit不改active。无SecAgg/DP或材料精度承诺。

## 最终证据与范围

以下实际运行均KEY空、MODEL unset；本次交接未重跑产品测试。

| 证据位置 | 已核结果及限制 |
|---|---|
| `OWNER_EVIDENCE/python-full-02/closure.json` | **4716通过/16跳过/2排除**，零失败错误，exit0，883.547秒，1010输入SHA稳定。8项真实聚合/训练/网络必跑、peer202/federation407零skip；15项旧SIG11渲染跳过逐名核对现全部实际通过。16跳过：Windows专用7、MuFerro opt-in3、PySide6/MCP/未标perf各2；另2标记perf排除。私有Xvfb/llvmpipe不代目标OS。 |
| `NATIVE_EVIDENCE/final-native-01/` | 全目标构建exit0、853.949秒；完整CTest **2056/2056、零失败/错误/跳过**、938.419秒，2816输入在该构建/测试窗口前后一致。见`source-closure.json`、`build-summary.json`、`test-summary.json`、`native.xml`。**之后CI和Apple fixture两个差异另记，不能说当前全部字节跑过2056。** |
| 同目录`federation-acceptance.json` | Federation **24/24**（State2/Editor1/Bridge13/Mouse8），8条UI记录。四布局Data各13点击、0文本；完整同意/两次评估准入/独立启用回退/撤回审计各50点击、9文本提交、0滚轮。详情见下文。 |
| `NATIVE_EVIDENCE/ci-guard-01/` | 完整回归后workflow三平台加入四组Federation regex，已进447。三平台守卫命令在Linux2056 XML验证24项计数，缺组/skip/fail反例均拒绝，YAML/diff通过；仅证守卫逻辑，不是Mac/Win执行。 |
| `OWNER_EVIDENCE/package-03/acceptance-summary.json` | wheel/sdist的681/995源成员逐字节核对，独立基础/算法环境 **585/585、零skip**，含8真实必跑，基础前后无flwr。wheel SHA `a6e5b8bcd8256f511f201787a4d22c1603a8a65c8f5671577837c7f4dc9d9d6b`，原sdist SHA `ad9da7b0ffef0cff6269b43987caef91877cb563b815316ab6e092e070d779d6`。当前文档来源以`package-final-docs-02`重绑为准，585仍是历史已测业务字节的证据。 |
| `OWNER_EVIDENCE/owner-worker-01/` | 额外独立安装 **1/1、1.76秒**：实际桥/认证HTTP登记授权→真实隔离ClientApp/Runtime→独立梯度误差≤1e-14→明确collect一次/审计→撤回拒下一轮，普通workspace无raw、仅receipt。外部用例未改源码/sdist测试，不是跨站/物性。 |
| `OWNER_EVIDENCE/backend-preflight-01/matrix-01/summary.json` | CAS预检修复后三Python3.11/3.12/3.14各112/112、零skip，63输入稳定；较早bridge各172/172发生在此补修之前，不当最终联合矩阵。 |
| `OWNER_EVIDENCE/delivery-01/staged-code-summary.json` | 447提交前真实暂存43路径、补丁1055276bytes，SHA `42f662cd8eb08699ee2781ef8796de6d493701ec88caa80a4274cd9b5e5598d9`；`.gitleaks.toml`+redact扫描exit0、暂存空白检查通过。后续任何暂存须重新扫描。 |

UI固定起点：英语1440×1200@1、中文1000×1200@1、英语2160×1800@1.5、中文2000×2400@2；最大化a4 Federation Data，项目rev1两行、Temperature[K]一特征/Pressure[Pa]一目标，未选连接/字段/角色，训练/留出各一行。Data13点击完成读取/选择、Freeze/Register；完整50点击进一步覆盖批准、两条审计、明确填阈值0、两次评估及Admit不改active、v1→v2→v1 generation1/2/3、撤回且审计保留。9次文本聚焦点击已计入50；Viewer/结果/相机/隐藏Python稿保留，script history为空。**CPU真实UI事件、生产Bridge/Owner加合成协调候选夹具**，不声称该UI测试运行Flower或OS/GPU/跨站训练。i18n2705/2705、零问题。

保留失败：`python-full-01`被启动器默认120秒总限终止，无JUnit/产品结论；原18进程身份退出已核、未发清理信号；02使用明确1800秒总限，未改单测门槛。`package-01`缺build模块、`package-02`在CAS补修前；原生candidate-09为GTest同行宏标签编译失败。不要覆盖或合并这些证据。

## 已提交补修：Apple rewind-after-show

`desktop/tests/app/reports_native_window.cc`约1055行：隐藏/重显后暂停时间若仍>0.90，Apple改用既有 `native_media_seek(...,0.07)`；其他平台保留LeftArrow。增加捕获navigation_generation相同校验；原paused/!ended/!seeking/time≤0.90、5秒、20轮/161图门均保留。

这是源码复核发现的剩余路径缺口，未宣称在新Mac复现。**已提交2513；Linux六目标构建exit0、33.628秒，72/72 CPU零skip、2.269秒，529输入稳定**，证据 `OWNER_EVIDENCE/p4-platform-20261031-02/closure.json`。当前SHA `bf5eeda293485d21a3c0abe0bbfb9f6eb7e01ac2aabe1f97c97cdf124671da6d`，2056测试时SHA `53a525de8fb958b02313a127b2a9ebfe99ef1e6af31a4aea2262f013c4a836b8`。复核前证据 `OWNER_EVIDENCE/delivery-01/observed-p4-before-rewind.json`。

全部seek/rewind调用点和四份文件已完整复核，`delivery-01/observed-p4-review.json`明确绑定Root审阅及当前SHA；post-full-regression-delta和72CPU范围独立记录。真实暂存扫描及2513提交证据 `delivery-02/staged-p4-summary.json`，补丁SHA `c5834ddcbe02bb169ff9d6be6171f8d79e5bd04c7a6aea03b94f013615828d29`。Linux不编译Apple条件分支，真实Mac/Windows须新CI。

447已含先前四份P4 fixture/input候选：首拖前Mac宿主激活、只读WKWebView AX滑条几何后普通鼠标seek、无效AX frame的Position/Size回退、Win同步消息重入修正、HTML字体fixture及有界输入诊断。原六目标/72CPU见 `OWNER_EVIDENCE/p4-platform-20261031-01/closure.json`，另记之后Cocoa回退差异；不把它算作新WIP已验。

## 官方CI快照

本次06:41 UTC前后官方只读GET再次确认远端main仍6126，以下同head/attempt1；精确快照保存在 `OWNER_EVIDENCE/handoff-final-20261031/ci.json`：

| 工作流 | 终态 |
|---|---|
| [Desktop41163547328](https://github.com/sijintech/stk/actions/runs/41163547328) | **completed/failure**，04:08:08 UTC更新，6jobs中4成功2失败。前代码头Desktop结束这个push前提满足，**P4未验收**。 |
| [Runtime41163547349](https://github.com/sijintech/stk/actions/runs/41163547349) | **completed/success**，03:29:26 UTC更新，不覆盖本地447/2513。 |
| Docs41163547325/Secret41163547316 | 先前已核成功，本次未重触发，不覆盖447。 |

6126实际原生路径Windows **3/6**（Spike/Markdown/PDF20轮过；HTML ink77.8%<80、视频同步消息超时、HTML视频拖动失败），Mac **4/6**（激活门过，seek/视频捕获未过）。证据 `OWNER_EVIDENCE/p4-windows-read-20261031T0434Z/analysis.json`、`NETWORK_EVIDENCE/ci-6126/owner-progress-20261031T040117Z/`。447/2513在本快照写入时尚未推送，**新头平台CI不能由旧头结果推断**；不降低像素/暂停/导航/20轮/161图门。

## 接手后的实施顺序

1. **核实正式交付。** 新Run按AGENTS建立自己的AOCI认知，再查真实Git/同头CI和closure。本批447/2513源码、完整回归、窄补修及完整Observed审阅均已完成，不重复旧WIP待办；若尚未推送，移交必须含本地提交/记录改动，单clone远端会遗漏。
2. **核收尾门。** Observed11的Baseline确认及正式Entry维护已完成，本次15项后Verify/Check对齐、Guide complete=true/none；最后交接文本同步和最终身份读 `OWNER_EVIDENCE/handoff-final-20261031/closure.json`。Root/Meta受Guard保护；后续完整候选按新机器批次提交，remaining非零继续，不能缩scope或猜FRAS。记录仍未暂存，提交前必须扫描真实暂存改动。
3. **核包来源。** 最新交接文档重绑读 `package-final-docs-02/rebind-summary.json`；wheel应逐字节等于已585项验过的a6e5包，sdist只允许包含的状态文档改变。业务/测试变化必须另验，不能称重绑是重跑585，也不覆盖旧环境。
4. **按main交付/跟CI。** 实际暂存gitleaks及空白检查后记录提交；push前重新核前代码头整个Desktop终态及远端第三方变化。新run记录真实ID/head/attempt和结果，未出结果明确pending；不借6126成功、不把失败终态当通过。后续正常交付更新四状态文档，保护已有未提交记录。
5. **继续完整通用路线。** 先处理新头P4/S3平台结果及S4其余身份/配对/文件/helper/跨站；再推进S5/S6/P5-S7，见下表。三待决不擅选，PET新专项后置。下一S4方案依据在 `OWNER_EVIDENCE/next-s4/implementation.md`，仅调查，不当已实现契约。

## AOCI与Observed接续

服务 `0.1.0-rc21`，CLI `/home/mnemora/.local/bin/aoci`。维护前1137条、05:44 Guide blocked/observed_pending均为历史。11份Observed审阅/ACK、原两批25项及本次15项均已完成，正式条目1144；本次15项后的Verify/Check对齐、Guide complete=true/none，missing/stale/unbaselined/Observed待审均0，无Recovery/第三方冲突。最后交接文本同步及最终scope/index身份读当前资产与 `OWNER_EVIDENCE/handoff-final-20261031/closure.json`，不把历史receipt当当前完整认知。

本次交接开始时，已有两批共25项原子Apply，索引1141条、scope `3e05a4170924b997f0df2fb7831bc00871ed0f3b1eba369c7c664386b33bb2c6`；剩余11项尚未Apply。交接文档随后也变化，旧Plan不能当新源码的写入授权；最终批次/对齐情况另存 `handoff-final-20261031/closure.json`。没有未决Recovery或第三方冲突的旧状态不能代替重新核验。

Observed11：native新 `desktop/tests/app/{federation.cmake,federation_test.cc}` 与 `desktop/tests/wm/test_app.cc`；Python新 `tests/test_desktop_bridge_federation.py`、`tests/test_federation_{evaluation,models,owner}.py`；P4改动 `desktop/tests/app/reports_native_input.hh`、`reports_native_input_cocoa.mm`、`reports_native_input_win32.cc`、`reports_native_window.cc`。完整审阅在 `OWNER_EVIDENCE/delivery-01/{observed-native-review.json,observed-python-review.json,observed-p4-review.json}`；本轮实际匹配和ACK在 `delivery-02/observed-review-sha-check.json`、`aoci-observed-ack.json`。精确后续集合以新Guide/Plan为准。

新Agent/压缩后按实时rules与普通完整overview跟随全部cursor、一次确认/Attestation；此文不保存或摘要正式Whole-Index/Header/Entry/Chunk/Challenge/Attestation正文，旧receipt不替代当前认知。限定rg/有界读，符号定义引用按需Serena；不预热全仓/读整份扫描报告，见[AI开发指南](docs/ai-development.md)。

## 后续通用开发仍缺什么

| 范围 | 未完成内容 |
|---|---|
| P4平台 | 新头Mac/Windows原生文档/视频/混合文档20轮及实际捕获；IME/跨屏DPI/真GPU另验。Linux Unsupported/CPU不代目标OS。 |
| S3训练 | 本机冻结/迁移/准入/回退/桌面已实现，持续目标平台和真实材料独立评价；合成/行级留出指标不证明科学有效，合作格式待决定。 |
| S4其余连接 | 持久设备身份/public-pin核对/配对UI，Mac↔Windows真端点，helper/运行库/许可发行，授权不可变文件manifest/续传/整文件SHA，部署信令及IPv6/UDP/TCP/TURN443实际站点策略/许可。loopback不证跨站。 |
| S5文献/共享 | 版本化授权PDF导入、完整支持页解析/来源、真实本地稀疏+稠密两层检索、可核引用/页段点击、授权陪读/文本及结构化共享，后续语音与窗口画面仍待实现。旧Qt前8000字符截取不是RAG，Hub聊天不是协作；未实现。 |
| S6复现 | 文献参数来源→冻结工作流→明确运行→数值/曲线对齐、单位/容差/独立参考/敏感性→来源报告，保留缺参数/失败/假设。真实授权MuPRO论文端到端证据缺，PET不作替代。 |
| P5/S7 | 干净机离线安装/Python环境、平台对话框/IME/缩放/快捷键/恢复/性能、模型更新回退、toolkits按职责迁移及兼容导入/wheel/sdist；ABACUS按依赖安排。 |

S5/S6研究笔记在 `OWNER_EVIDENCE/next-s5-s6/{requirements.md,engineering.md}`，后者25项一手来源，**仅调研，未安装/下载模型或实现接口**。候选隔离PDFium、本地FTS5+固定权重/分词器摘要真实dense encoder、精确引用映射，先验许可/解析偏移/平台包装；不以假向量/两tab称完成。共享边界按[平台设计](docs/design/sijin-platform-2026-10.md)后轮决定，不擅开收费、远程控制或私有外发。

## 三项待所有者决定

1. 合作方S3两数据格式及MuPRO电场扫描。
2. S2c外部规划/智能体准备运行权限。
3. 保存分析修改提案的持久形式。

未选前不按任一方案实现；内部capsule/owner UI不构成决定或agent授权。PET新字典、厂内专项、专用训练、长链/气体收敛和材料指标验证后置，保护既有功能/证据。

## 本机工具与复验入口

```text
OWNER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-owner-20261031
NATIVE_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-owner-desktop-20261031
NETWORK_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-network-20261030
FLOWER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-flower-20261030
PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030
Python3.12=/home/mnemora/opt/stk-venv/bin/python
Python3.11=/home/mnemora/opt/stk-venv311/bin/python
Python3.14=/home/mnemora/opt/stk-venv314/bin/python
native build=/home/mnemora/opt/stk-build/merge-check
sysroot=/home/mnemora/opt/stk-sysroot
gitleaks=FLOWER_EVIDENCE/tools/gitleaks-8.30.1/gitleaks
offline builder=/home/mnemora/.local/state/stk-validation/p4-video-20261029/package-check/build-env/bin/python
```

既有native缓存Ninja/RelWithDebInfo、文档候选/原型/探针ON；一次一个构建。离线builder有poetry-core、无build模块；已审阅的 `OWNER_EVIDENCE/final-doc-rebind-plan/rebind.py` 默认inspect，显式rebind要求新的绝对证据目录，直接使用 `poetry.core.masonry.api.build_wheel/build_sdist`、`SOURCE_DATE_EPOCH=1793413645`。不要用package-03的prepare_env.py替代，它会安装环境。Flower只在独立Linux算法环境flwr1.42.0/numpy2.5.4，基础/Hub不装。

以下仅为出现新改动或未决失败时的条件复验参考，**当前2513对应的六目标/72项已完成，不因交接重跑**。需要时由下一Agent审查后在新证据目录使用，保存JUnit/日志/manifest、不覆盖旧结果；本次交接整理未再次运行：

```bash
stk_handoff_evidence="$(mktemp -d /home/mnemora/.local/state/stk-validation/s4-owner-20261031/p4-rewind-XXXXXX)"

env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  cmake --build /home/mnemora/opt/stk-build/merge-check --target \
  stk-reports-native-window stk-document-evidence-tests stk-document-resources-tests \
  stk-document-media-probe-tests stk-report-document-tests stk-document-preview-spike --parallel 4

env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  -R '^(DocumentEvidence\.|DocumentResources\.|NativeMediaProbe\.|ReportDocumentHost\.|document_preview_memory_|native_evidence_gate$)' \
  --parallel 4 --output-on-failure --output-junit "$stk_handoff_evidence/cpu.xml"
```

Federation定向目标 `stk-federation-tests`，CTest筛选 `Federation(State|Editor|Bridge|Mouse)`、设置 `STK_BRIDGE_TEST_PYTHON=/home/mnemora/opt/stk-venv/bin/python`；既有24已通过，不因交接机械重跑。Mac/Windows按[QUICKSTART](desktop/QUICKSTART.md)准备自己的工具链，不复制CMake缓存；`--launch-only`不验证新源码。

不读/打印/存密钥、私钥或真实用户配置；测试KEY空/MODEL unset、不发收费请求，端点/密钥/网络策略只经桌面明确修改，私有项目数据不去外部模型。公开文档称“合作方”；archive不入导入/构建/打包/测试。外部证据不随clone迁移，仅移交明确源码和验证产物，不复制私有运行凭据。
