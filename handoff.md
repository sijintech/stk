# STK 当前交接

更新：2026-10-30（本机日期；后续收尾使用UTC）。**所有者已重新激活持续开发目标：完成主要通用能力，PET新专项后置。** S4网络训练源码已提交 `a5510bfa838e34e5555f0c6beaa4e0e6b04d190a`，Windows有效内容裁剪修正已提交 `10b784ba262fae7bbd26c5d1f2d39398019f5ec1`。视频验收分隔条方向修正已提交 `b02a51cdea47868e4c599fdbc763ed80ddd1e3b7`，Mac激活宿主修正已提交 `dd318ce287bc1d52fd8da324026c321e984dc55c`；本机验证及剩余平台/产品工作见下；整份路线图尚未完成。实际记录提交、push、新CI和AOCI闭环以 `NETWORK_EVIDENCE/delivery-closure-summary.json` 为准，接手先核真实Git/CI。

先读 [AGENTS.md](AGENTS.md)、本文件和开发计划；产品决定见 [项目工作台](docs/design/project-workbench.md) 与 [项目模型](docs/design/project-model.md)，发布契约在 `docs/specs/`。本文是当前快照；旧交接、首轮失败和历史交付查 [开发日志](docs/development-log.md) 与 [运行验收](docs/runtime-validation.md)，不要再把历史“8 个未验证草稿 / Node 尚未创建 / Desktop 仍 queued”当作现状。

## 当前 Git 与工作树

- 分支 `main`。本批网络源码 `a5510bfa` 与Windows修正 `10b784ba`、视频布局fixture修正 `b02a51cd`、Mac验收宿主修正 `dd318ce2` 已本地提交，未把未完成的桌面授权/准入冒称交付。上一已推送基线为 **`38a9fd433c1924a5bcc068e4bd1643e3f7c82bbf`**，其源码父提交 `11844b257e3a88f0db1e08611624a295e64b13c2`。最终远端/记录提交与新CI在上述closure核实，不从旧WIP快照猜测。
- 网络提交含25路径：`.github/workflows/runtime.yml`；`docs/federation.md`、`docs/repository-structure.md`、`docs/specs/stk-federation-1.md`；`suan/control/{agent,app,cli,federation,policy,store}.py`；`suan/federation/{client,coordinator,inputs,node,protocol,train_worker,training}.py`；`tests/test_control_federation.py` 与 `tests/test_federation_{client,coordinator,inputs,network,node,protocol,training}.py`。原25文件暂存候选已成为源码提交，不再是未验证8文件草稿。
- Windows提交仅 `desktop/spike/document_preview/{window_capture_geometry.hh,window_evidence_win32.cc,evidence_pixels_test.cc}`，127行新增/29行删除；旧媒体/20轮标准保留。本批记录/AOCI资产单独收尾，未提交内容须保护，不reset/clean/覆盖。
- 先前转交时四文档的未提交版本及核验保留在 `NETWORK_EVIDENCE/handoff-transfer-20261030T184019Z/`，当前恢复开发状态以本文件最新内容为准。换机器仅clone不能取得仍未提交文件或本机外部证据；只移交明确的源码/验证产物，不复制凭据、私钥或用户配置。

## 当前 S4 网络训练后端（源码 a5510bfa）

固定线性多目标 MSE、FedAvg/FedProx 的真实 Flower ClientApp 已接入私有输入 capsule、隔离 Runtime worker、持久 Node 服务、owner 绑定 Hub run/设备/public-pin 映射、独立 FL CAS/action ACL、出站 NodeAgent/CLI，以及显式持久 coordinator 和有界 HTTP client。协议和操作说明已扩展到 [联邦契约](docs/specs/stk-federation-1.md) 与 [指南](docs/federation.md)。

| 入口 | 职责 / 修改注意 |
|---|---|
| `suan/federation/protocol.py` | 严格冻结训练 spec/run 与 train/status/collect/cancel DTO；拒绝远端 argv/env/路径/训练参数覆盖，四操作都保留完整 model 绑定。 |
| `inputs.py`、`training.py`、`train_worker.py` | 私有 x/y 数据、真实数据 SHA 和有序列名绑定，固定线性训练/原始数值参数空间，隔离解释器单次执行；不采用每节点独立归一化后直接平均。 |
| `node.py` | `(grant_id, round)` 原请求、固定 Runtime spec/key/task 先落盘，再提交；lost reply 只查原身份，重开/status 不重训；只有 collect 显式发送更新。取消先保存意图，再交 Runtime 判断终态。 |
| `client.py`、`coordinator.py` | 已配对原点，无 proxy/redirect/自动重试；持久原 action 后发 HTTP，未知结果只查询，至少三份批准且实字节校验的更新才能聚合；`aggregate_uncertain` 不自动重放，候选不自动准入。 |
| `suan/control/federation.py` | owner 指定 coordinator、私有 FL CAS/run/round ACL、不可变上传引用/额度/进程租约/崩溃清理；撤销 run 不冒充 Runtime 任务已停止。 |
| `suan/control/{agent,app,cli,policy,store}.py` | 出站网络、专用消息和 blob、分角色授权/SSE、普通 snapshot/cache/task/graph/file 出口私有身份隔离。CLI 用 `--federation-python /abs/algo/bin/python` 显式选择算法环境。 |

已修且有反例：RuntimeClient 下私有根重叠检查、同 layout 模型替换绕过原 SHA、首次 collect 失败后卡住、查询未知 task 时新 private reservation 出现的竞态、取消标记次序导致 failed，以及 SSE 泄露私有身份。100 历史 job / 50 普通对象的 snapshot 从 20,000 次状态读取降到精确 100 次，无逐 task HTTP；保留 lost-submit 映射并重核新归属。

## 已完成的验证及适用范围

证据根 `NETWORK_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-network-20261030`。下面是已实际执行的结果，不需要为了交接重复全量测试。

| 范围 | 结果与证据 |
|---|---|
| 完整 Python，一次运行 | **4589 passed / 31 skipped / 2 deselected，0 failed/error，824.25 秒**；`python-full/summary.json`、`results.xml`、`pytest.log`。1000 个输入前后 SHA 全同，清单摘要 `7039e8f8b184fe9b8ca1a815f2eaf7e9c226bc5c8f7a99a6761c6387143b38eb`。federation 326、peer 202 均零 skip。 |
| 跳过与最后测试头修改 | 31 skip 包含 15 项离屏探测 SIG11、平台/可选依赖/真实 MuFerro 与性能 opt-in；本批没有新的离屏补验，不挪用上一批 15/15。完整回归之后仅改 `test_control_federation.py` 的可选依赖 import guard，业务源码未改；另补下方 26 项和缺依赖收集验证，不能称已重跑最终全量。 |
| 全联邦 + Hub 工作树联合 | **352/352，零 skip，25.99 秒**，`network-joint-01.xml`；含真实聚合、四个 dtype×strategy 训练及两个网络用例。Root/Node/Hub 源码与当时已安装 worker 来源分别记录。 |
| 真 TCP/WSS 与 Runtime | 三独立 Linux Runtime + 三出站 NodeAgent，FedAvg/FedProx 各两轮，共 **12 次真实 ClientApp 训练**；逐轮独立逐样本梯度参考误差门槛 1e-13，重复 train/collect/重开不重复执行。**同一 Linux 宿主的 loopback，不能当跨站/NAT/TURN验收。** `network-01.xml` 的初始夹具 token 长度失败和修正后的 `network-02.xml` 2/2 均保留。 |
| 最终独立安装候选 | **402/402，零 skip，41.99 秒**；`package-final/acceptance-summary.json`。15 份原测试从 sdist 提取到无关 cwd，`-I`、PYTHONPATH unset；独立 base/algorithm 环境，8 个 mandatory 真实用例实际执行。677 个 wheel 源成员、987 个 sdist 源成员绑定源码，两环境 677 成员测试前后稳定，base 无 flwr。 |
| 包身份与后续重包边界 | 已测 wheel SHA `93734540988d5801ac0a42b016d1b9d500c51b67c7c3debf7b63091e31c75464`；sdist SHA `1482643ae7dda2b7fa743261c728815982abb0efc7f20fc818649ac56e51ae03`。该安装测试早于最后可选依赖 guard 和本次四状态更新；交付前需新目录重包/逐成员比较。预计 wheel 业务成员不变，sdist 变化是测试头和 `docs/runtime-validation.md`，须实际核对；其他三状态文件不在包内。 |
| Hub 三 Python 版本 / Node | `hub/acceptance-summary.json`：3.12 全 control 76、3.11/3.14 新增各26，合计128次零skip；`node/candidate-05/summary.json` 最终实际42/42。candidate05 wheel 未安装；最终全包安装证据以上行 package-final 为准。 |
| 可选依赖最后补验 | `hub/optional-import-followup.xml` **26/26**；`hub/optional-collection-02/summary.json` 在模拟 fastapi/httpx 缺失时仅跳过整个模块、无 collection error，exit5 表示没有可执行测试。针对 Windows 客户端不装 control 依赖的收集问题，**不是实际 Windows 运行通过**。 |
| workflow / 审查 | `workflow-review/summary.json`：YAML、三个 shell 块、内联 Python 与352项JUnit的精确 gate通过；CI 基础环境无 flwr，算法环境独立。`review/`、`root-admission-03.xml` 保存独立反例和性能证据。 |
| 已暂存源码密钥扫描 | `secrets-source-02/summary.json`：25文件、234011 bytes，暂存 diff SHA `ce53a628c145ca942c0b1023c7a307a1a8147e373106bd2dee939ef70e2b9e98`，gitleaks **0 findings / exit0**。包含最后测试头修正；不覆盖之后的文档或未来暂存改动。提交前对实际最终暂存重新扫描。 |

Windows修正追加验证：`p4-next/candidate-02/summary.json` 实际全目标增量构建exit0，相关72/72零skip，三源稳定；与上述4589/402为不同范围。三文件暂存差异经 `.gitleaks.toml` 扫描零发现后提交10b784ba，扫描证据 `p4-next/candidate-02/secrets-staged/summary.json`。本机Linux不编译Windows分支，不重复跑无关Python全量。

视频布局fixture修正 `b02a51cdea47868e4c599fdbc763ed80ddd1e3b7`：实际默认a2 Viewer在左、a3 Reports在右，旧代码却只收Reports左侧并固定负方向拖动。现在传入原Viewer，核两者确为相邻原实例，按实际child index选择±drag，同时要求Reports缩小、Viewer扩大并释放capture；完整element、同navigation/暂停时间和终态Viewer/草稿断言保留。`p4-next/layout-01/summary.json` 实际增量构建exit0（33.882秒，probes开启并重编/链接该fixture），相关72/72零skip（1.326秒），四源前后稳定。单文件17新增/7删除，经暂存gitleaks零发现后提交；Linux不执行Mac/Windows原生视频，仍须新平台CI。Python包排除desktop，这项不改变已测Python业务成员。

Mac验收宿主追加修正 `dd318ce287bc1d52fd8da324026c321e984dc55c`：普通未打包test executable先显式设置并核验Regular激活策略，再请求自身窗口激活；原active/key/精确窗口合取与5秒UI观察门保留。失败/超时写固定before/after/final整数/布尔快照和计数，轮询不写盘、不识别外部窗口。`p4-next/macos-activation-01/summary.json`：Linux增量全目标构建exit0、32.146秒，原72CPU用例名称集合相同且72/72零skip、1.309秒，三源SHA稳定，暂存gitleaks零发现后提交。**Linux不编译Cocoa分支、不证明真实激活/OS像素/20轮**；38a未记录policy，不能断言原运行态就是prohibited。未打包程序默认策略与setter返回值依据 [Apple activation policy](https://developer.apple.com/documentation/appkit/nsapplication/activationpolicy-swift.enum/prohibited?language=objc) / [setActivationPolicy](https://developer.apple.com/documentation/appkit/nsapplication/setactivationpolicy(_:)?language=objc)，策略成功仍不替代原激活观察。

## 当前 GitHub CI：上一头已结束，平台仍失败

本次直接重查同一 head `38a9fd43` 的 run，attempt1；未重新触发。结果只覆盖已提交基线，**不覆盖当前网络 WIP**。

| 工作流 | 当前结果 |
|---|---|
| [Runtime 41097301247](https://github.com/sijintech/stk/actions/runs/41097301247) | **completed/success，10/10 jobs**；独立 Flower 基础230/230零skip，主矩阵仍有环境跳过项。 |
| [Desktop 41097301277](https://github.com/sijintech/stk/actions/runs/41097301277) | **completed/failure**，2026-10-30 18:06:52 UTC 更新；6 jobs中4成功2失败。前代码头整个Desktop结束的 push 等待条件已满足；P4验收没有通过。 |
| [Docs 41097301182](https://github.com/sijintech/stk/actions/runs/41097301182)、[Secret 41097301195](https://github.com/sijintech/stk/actions/runs/41097301195) | 已保存 success；Dependency Graph41097311540亦success。 |

完整平台证据在 `ci-38a/terminal-1806/terminal-summary-v2.json`、`windows-geometry-analysis-v2.json`，保留日志/工件及官方摘要核验：

- macOS CPU **1420/1420**、Metal **254/254** 零skip；原生4/6通过。Markdown/HTML各20轮140图，PDF20轮160图，spike20轮161图，合计 **601 张记录 PNG**，SHA已逐张核验。视频与HTML视频均在自身窗口激活确认门超时，**0完整轮/0图**；现有错误不能区分 active 与 key predicate，不猜改。
- Windows CPU **1364/1364** 零skip；独立native **0/6、0完整轮/0图**。五项WGC几何失败，一项 Viewer 并排布局门失败。已观察媒体解码状态不能代替最终视频像素/20轮证据。
- Windows精确观测：WindowRect/item/pool/texture均1040×736，DWM/frame.ContentSize均1026×729；client1024×697，DPI96/awareness2。旧FullWindow原点crop右边超有效Content6px；DWM候选crop完全在界内。**尺寸匹配不证明像素原点正确**，目标平台仍须实测。

## 后续实施顺序

1. **先核本批交付闭环。** 源码a5510bfa/10b784ba，实际记录提交、包重绑、AOCI全批Apply/Verify/Check/Guide、暂存gitleaks和push/新CI在 `NETWORK_EVIDENCE/delivery-closure-summary.json`；逐项核结果与剩余限制。不重做已完成的4589/402等验证；只有新源码/失败才扩大回归，旧全量不冒称覆盖后续源码。
2. **P4 Windows目标平台复验。** 原外部候选 `p4-next/candidate-01/windows-valid-content.patch`（SHA `030f1014195c5d311efe34426eae356ed3753372ceda19b36d01c4e0405d9ec7`）已应用并提交10b784ba；实际merge-check全目标增量构建成功6.265秒，相关 **72/72、零fail/error/skip、1.350秒**，3个新ContentSize反例均执行且三源前后稳定。证据 `p4-next/candidate-02/{summary.json,build-summary.json,test-summary.json,focused.xml}`。当前按有效ContentSize独立计算crop、分别记录pool/content origin，DPI/嵌套矩形/格式/8192边长/16Mi像素约束不变。**仍未本机编译Windows分支或执行WGC**；尺寸匹配不证明内容像素原点，须新头Windows编译/完整20轮。
3. **P4其余平台继续取证修复。** Mac测试宿主已显式设置Regular并记录有界active/key状态，待新CI核实际策略和失败谓词；激活/暂停/完整媒体/20轮标准保留；Windows布局fixture的左右方向假设已在b02a51cd修正，目标平台仍须完整复验。平台修复后核真实Mac/Windows完整native结果，Linux CPU不编译Cocoa/Win32，也不证明OS呈现。S3b跨平台及真实GUI/IME/DPI仍按相应完成条件验收。
4. **S4下一产品链**：桌面本机数据集consent/撤回/逐轮审计、明确发送与显式模型准入；保留候选与活动模型分离，重开/刷新不训练、发送或激活。新UI记录固定起点/点击数/结果，保留Viewer与隐藏草稿。
5. **S4其余连接能力**：持久设备身份/public-pin核对/配对UI；Mac↔Windows真实端点；可分发helper与运行库/许可；授权不可变文件manifest、断点与整文件SHA；部署信令、网络自检及IPv6→UDP（含端口预测）→TCP→TURN443实际策略/站点验收。现有peer后端与本机loopback训练都不代表这些已完成。
6. **S5**：本地PDF解析、两层检索和可核对引用，按既定授权陪读/结构化共享；旧Qt仅截PDF文字，不可当RAG。优先公开或自有资料，沿用既定文献许可与加密中继边界。
7. **S6**：文献设置→冻结工作流→明确运行→数值/曲线对比→带来源报告；保留缺参、失败、来源与不确定度，不伪造复现成功。
8. **P5/S7**：干净机离线安装/Python环境，文件对话框、IME/DPI/快捷键/恢复/性能，模型更新/回退；toolkits按职责迁入suan并保留兼容导入/wheel/sdist。通用引擎、执行目标及ABACUS按依赖推进。PET新字典、厂内专项、专用训练、长链/气体收敛及材料指标后置，保护已有11段真实软件路径，不声称物性收敛。

## AOCI 与工具续接

- 新Run先按 [AGENTS.md](AGENTS.md) 与实时 `aoci_rules`/`aoci_overview` 建立认知；压缩恢复声明 `context_compaction`、用新event ID，跟随全部cursor并做一次当前Attestation。**本文件不保存正式Whole-Index、Header、Entry、Chunk、Challenge或Attestation正文；旧收据不替代新Run认知。**
- 本次服务 `0.1.0-rc21`，CLI `/home/mnemora/.local/bin/aoci`。维护前已完整交付并校验的scope/index为 `10c54ba7e7e8e9ffed303703eee44366b16b79177fe7cf62288dd81ba379b0a3`、1129对象；这是续接身份，不能替代维护后的当前身份或新Run认知。新index、baseline与Apply/Verify/Check/Guide实际结果见delivery-closure与实时Guide。
- 最后Hub测试可选依赖guard的Observed指纹已完整复核并ack：事务 `e23ffa808f1598ed4d270db9`、baseline `06ee56b8406c12447cac83566c7f859611c299ad73f117f6842575017bad53ef`，证据 `aoci/observed-optional-guard-{review,ack}.json`。随后Guide已核observed_pending0、pending_transactions0、recovery_pendingfalse。b02a51cd的验收fixture已另做精确Observed复核，结果在 `aoci/observed-layout-{review,ack}.json`；Mac三验收文件的最终复核见 `aoci/observed-macos-{review,ack}.json`。此前8个新测试review/ack事务 `03bffe5d064714648856ae35` 及基础17条交易已经闭合，不重复。
- 本轮正式维护入口为 **8 missing + 16 stale，共24对象**（网络21加Windows3，忽略重复unbaselined/技术skip）。文件最终稳定后按机器签发完整批次创作/Apply，原样回绑候选/摘要/批次；所有remaining清零再Verify/Check/Guide。收尾实际结果在delivery-closure；有Recovery或第三方冲突时按实时Guide处理，不猜写或缩减受管范围，已aligned后不重复维护。
- Guide：`/home/mnemora/.local/bin/aoci index agent guide --agent codex --json`；Scope：`... scope status --json`。输出先提取必要字段，避免把完整报告灌入上下文。Volumes v1不支持`status --deep`不是版本不匹配。
- 导航优先限定`rg`和有界读；符号定义/引用需要语义时用Serena并限返回量，配置与实测见 [AI开发指南](docs/ai-development.md)。jscpd/Knip按需，不默认全仓预热或创建第二份仓库记忆。

## 安全、产品边界和未决事项

- 不读/打印/保存任何密钥。测试必须 `STK_TOKEN_PLAN_API_KEY=` 且 unset `STK_TOKEN_PLAN_MODEL`；刷新/重开/测试不发收费模型请求。端点、密钥与产品网络策略只经桌面明确操作；私有项目数据不发外部模型。测试token用低熵占位，遵守既有长度门槛。
- dataset/base/未放行delta/私有job/result不进入普通Runtime inputs/work；公共work仅净化receipt。`outputs`不是访问白名单，普通file/graph/snapshot/cache出口必须继续过滤私有身份。Runtime不是同OS用户安全沙箱。
- FL CAS/run权限独立于普通Hub blob，授权先于存在性检查；run撤销不自动停止任务或收回已发送字节。设备32hex与公钥指纹64hex分开；owner显式核对映射，管理owner不自动成为coordinator，不宣称此映射已证明私钥持有。
- Flower只在独立Linux算法环境，精确`flwr==1.42.0`、`numpy==2.5.4`；基础/Hub不装flwr，不启动SuperLink/SuperNode/gRPC，首批无SecAgg/DP承诺。512MiB限制为原始bundle预算，元数据另限，不是整个私有目录总上限。
- 三项仍待所有者决定：①合作方S3两数据格式及MuPRO电场扫描；②S2c外部规划/智能体准备运行权限；③保存分析修改提案的持久形式。时间经过不构成批准，现有内部capsule不替合作方选择数据格式。公开仓库统一称“合作方”。

## 本机路径、复验和构建

```text
NETWORK_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-network-20261030
FLOWER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-flower-20261030
PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030
主Python=/home/mnemora/opt/stk-venv/bin/python
另两版=/home/mnemora/opt/stk-venv311/bin/python、/home/mnemora/opt/stk-venv314/bin/python
已测最终算法Python=NETWORK_EVIDENCE/package-final/algorithm-env/bin/python
已测最终基础Python=NETWORK_EVIDENCE/package-final/base-env-02/bin/python
已核验gitleaks=FLOWER_EVIDENCE/tools/gitleaks-8.30.1/gitleaks
Linux构建目录=/home/mnemora/opt/stk-build/merge-check
用户sysroot=/home/mnemora/opt/stk-sysroot
```

路径仅适用于当前机器。不要覆盖旧证据/候选；旧FLOWER production-adapter环境只含上一批基础，不能当新worker环境。需要复验网络候选时：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  STK_FEDERATION_TEST_PYTHON=/home/mnemora/.local/state/stk-validation/s4-network-20261030/package-final/algorithm-env/bin/python \
  /home/mnemora/opt/stk-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_federation_*.py tests/test_control_federation.py
```

原生一次只运行一个编译，成功退出后再测试，避免读取旧二进制；按改动选用目标/测试。基本命令：

```bash
cmake --build /home/mnemora/opt/stk-build/merge-check --parallel 4
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  --parallel 4 --timeout 600 --output-on-failure --output-junit /tmp/stk-handoff-ctest.xml
```

Windows/macOS沿用 [desktop/QUICKSTART.md](desktop/QUICKSTART.md) 的 `setup-windows.ps1` / `setup-macos.sh`，不要另造启动链；`--launch-only`不验证新源码，脚本仅构建主程序。新机器按 [desktop/README.md](desktop/README.md) 重配，不照搬CMake缓存。归档目录不进导入/构建/测试。每次实际交付同步四状态文件、按最终源码维护AOCI、扫描最终暂存，再在main提交；push前核前代码头整个Desktop终态，并记录新头实际CI及剩余限制。
