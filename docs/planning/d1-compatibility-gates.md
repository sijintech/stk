# D1 实施前的最小契约与兼容门清单

## 2026-11-08 后续进度：既有Hub工作区CLI入口

Claude16的三路径8ae2088d由root选择集成为main2fcc7251，新增工作区create/list/files及仅workspace.create原action观察；不接Hub上传或新授权。原key/action先输出，unknown只读原身份；列表标明heartbeat_snapshot且有限，离线/能力错误不猜不存在。旧节点读取兼容仍可创建read action并有界轮询，只有写操作临时wait=0并finally恢复。

作者六模块100/0skip/54.752s、root主线42/0skip/15.716s、新最小安装42/0skip/17.224s通过；wheel11bacdc7…产品差异及9父模块site-packages来源/SHA匹配。review是种入状态，旧节点是传输替身；真实联网仅单Linux回环，不代跨站、旧发行或目标OS。独立发现并关闭旧读零等待P2，23纯检查及四旧行为红例保留。详见运行验收及d1-hub-workspaces-20261108-20/root/。

Claude17已接独立journal/锁/原身份恢复的设计，未实施上传CLI。既有Bridge上传恢复不代此入口，也不证完整D1、R3、云端项目或网络分区。691整个Desktop已失败终态，Windows原生6/6成功；MacCPU1502/1503、Metal跳过、原生4/6。root f052联邦测试等待修正已本地24项通过，仍待新平台CI；独立AOCI提案未集成。

## 2026-11-08 后续进度：真实Bridge收块丢ACK恢复

[上传恢复样例](../../examples/backend_parity/UPLOAD_RESTART.md)由实际Claude4d02ea3a三路径选择集成为main2cc40a0d，本地未push。真实Hub先收首1MiB、Bridge原journal仍bytes_done=0时SIGKILL/reap，仅重开同profile/state/journal，保持其他四服务原PID/创建时间；原transfer/key/request/upload_session恢复，首新块1048576、下一块2097152，总2621464字节。完成后原workspace.import仍待人工批准，批准前零文件/任务，之后精确大小/SHA一致；无Task提交，不声称程序消费了输入。驱动写后及启动前SHA核验，缺证明和清理失败独立禁通过。

最终script38e42c02…/testc56f8803…；README仅两处说明修正。Claude联合282项零skip通过/74.18s，最终source04/installed05各10断言通过；root主线新模块67项零skip通过/9.814s。root独立最小安装态以同一script运行10/10，场景5.722266164s、含清理6.579574818s，17模块来源探针SHA与root一致、无GUI/科学可选依赖且无残留；探针不等逐服务完整sys.modules采集。独立18纯反例无实质发现，提前SIGTERM和服务session丢失后从0重传真实红例正确失败。暂存75410字节、SHA0a266fba…，gitleaks零发现。证据 `d1-upload-restart-20261108-19/root/`、`claude/`。单Linux主机、一个故障点，不代网络分区/R3/许可求解或科学验证。

此片补原输入样例未覆盖的Bridge journal重开/原偏移恢复，仍不补网络分区、R3或云端项目。Claude16转既有Hub工作区CLI入口，root继续公共后端/桌面/集成；不据此裁决R2/R3。最新691 Runtime13job成功；整个Desktop仍待Windows原生终态，Mac CPU1502/1503、Metal跳过、原生4/6，详情见[运行验收](../runtime-validation.md)。


## 2026-11-08 后续进度：输入与现有设备撤权首片

源码 main `4399f2fa6dfaba941922d2808ca023eba3766105` 已本地提交，尚未push；远端仍 `7ef5d21e`。前整个Desktop42487388780仍运行，终态前不推送。原四文档WIP和AOCI预存改动保留，最终交付状态见 `d1-input-transfer-20261108-18/root/closure.json` 与实际Git。

[输入/撤权样例](../../examples/backend_parity/INPUT_TRANSFER.md)已在source和最小installed通过11断言；新增真实两部署输入/撤权样例：同一1048599字节公开输入，部分会话1MiB后重开同ID/offset，完成SHA校验；B blob必须经原workspace.import人工批准才导入，完整TaskSpec另经批准。两边固定程序读取冻结输入并输出相同SHA，原Runtime清单、各一task/run/marker、program和worker清扫前退出。B仅撤本次desktop设备，热/冷客户端后续11类请求均401，节点仍在线、无新增action，原Runtime任务保持。不是断网、桥日志恢复、项目/用户授权、在途请求中断、已交付字节召回或pending上传字节不变证明。

最终新模块及singleton联合28通过、零skip、14.81s；最小非system-site-packages包以-I installed复验11断言通过，场景6.045540141s、含清理8.1s，实际site-packages来源/模块SHA一致、清理干净。产品Python到7ef无差异，沿用已重建包，不把旧harness试跑当新字节；当前script46f83b43…/helpercf2b13c9…。独立终审关闭A额外queued任务假绿和迟到terminal延长局部截止，反例已入测试。暂存25040字节gitleaks零发现。

7ef的Runtime42487388719于14:14:50Z整轮failure：11job成功、两Windows矩阵因新增Linux专用singleton测试在收集阶段引用不存在的SIGKILL而报错，未执行该矩阵测试。本提交改为函数体解析信号名称，缺SIGKILL的模块红绿反例及Linux原11项通过/5.73s；仍待新Windows CI。Docs42487388755完整部署成功，Secret42487388666成功。Desktop当前Linux三job成功，Mac已越过编译/CPU阶段、WindowsCPU运行，原生最终结果待出；不能继承旧头平台验收。

后文旧“传输/撤权尚缺”不覆盖本次有限门；故障、撤权竞态、项目/用户权限、云端项目及跨站仍未完成，R3未代选。

任务卡：CL-D1-01、CL-D1-PARITY-11、CL-D1-DISCONNECT-12、CL-D1-HUB-RESTART-13（见[协作约定](agent-collaboration.md#当前任务卡)）。状态：**正常任务、节点断连、Hub 丢结果重启及正式 serve 单实例已本地验收，D1 完整退出门尚未完成；下列新进度优先于历史基线。**
本文不发布新 schema，不改产品代码或数据库格式，也不替所有者选择 D3 领域、剩余未决事项或 PET 新专项。
2026-11-07 所有者对原三项待决作了新回答，root 已把它们写入任务卡并要求纳入本清单，见 §6。

**历史基线：** 初稿来自 `claude/support` 的 `37d26464591f9191986459f4d70b7320e68f5555`；三份设计当时以 `535b0d63d15521ea7d4294ddfce2ac68a3555667` 为证据，两头当时的产品代码相同。下文未更新的 `路径:行` 仅定位该历史版本，不能据此声称当前源码仍相同。

**2026-11-08 最新进度：** 本地 `b517554a` 补五个时间字段按各自原 Runtime 保真及固定产物 MIME 核验；`c5d8e503` 对正式 `suan-control serve` 加同一真实状态目录的全生命周期锁；Claude `755212b2` 三路径选择集成为 `ddd7d7c2`，验证原任务已接受、Hub 尚 queued 时丢结果和同库重启。主线联合271项通过、零skip、74.57s；新最小安装包的正常/断连/Hub重启分别12/10/11断言通过，来源与模块SHA匹配。Hub恢复为两次delivery、一次Runtime.submit、一个任务/run/marker，原进程显式取消后清扫前退出。驱动摘要缺失/不匹配假绿已修并独立关闭，证据 `d1-hub-restart-20261108-12/root-integration/`、`d1-hub-singleton-20261108-14/`。单机进程故障不代表网络分区、云端项目或许可/科学验收。

已推 `fd394e46` 的整个 Runtime 13 job、文档部署和 Secret 均成功；Desktop于13:51:08Z整轮failure终态，Linux三job及Windows原生文档6/6成功；Mac构建的AXValue枚举类型错误已本地补 `2c9729b8`，尚未目标Mac复验。WindowsCPU1445/1446通过、1个PeerMouse空JSON失败，Claude14限定测试夹具定位。本批未push；前整轮等待门已满足，最终交付和新CI以[运行验收](../runtime-validation.md)及本批closure为准，不能借旧头CI覆盖新字节。Windows 排除 server 组，不能算该组的 Windows 验收。HDF5 和有限 S2c 契约分别见 [MuPRO HDF5/1](../specs/mupro-hdf5-1.md) 和 [agent MuFerro run/1](../specs/agent-muferro-run-1.md)。S2c 仍只允许桌面明确选择的直连/SSH Runtime，不支持 Hub 准备。

root 选择 R1(a)，已将 Claude `6cc2d39e` 的[双部署样例](../../examples/backend_parity/README.md)选择集成，并修正清理异常和未舍入预算判断；源码 `6ae96999` 已随文档 `599937f9` 推送。联合测试 61 通过、零跳过；root 在独立、非 system-site-packages 的最小 `server/control/test` 环境，以 `-I --mode installed` 验证真实 Runtime A 和 Hub/Node/Runtime B，9 项断言通过、总耗时 12.1s，两个部署的实际模块来源/摘要一致，任务程序和 worker 均退出，临时目录已删除。包来自 `58fbd03e`，到 `6ae96999` 的 `suan/`、`toolkits/`、`pyproject.toml` 无差异；样例自身另绑 SHA。证据为 `d1-parity-20261108-08/root/parity-integration/`，最终提交/推送以其 closure 和[运行验收](../runtime-validation.md)为准。

CL-D1-DISCONNECT-12 已由 Claude `a215972d` 交付，root 选择集成 `688db5a0`；[断连样例](../../examples/backend_parity/DISCONNECT.md)联合90项零skip通过、43.90s。root 最小安装环境 `-I --mode installed` 的10项断言通过，场景23.544913289s、含清理24.654371985s，实际site-packages来源和模块SHA一致。仅杀本次原NodeAgent且核实际SIGKILL/reap；Hub离线精确读不返回任务状态；同profile重连后观察原任务，显式取消后原program和worker均在清扫前退出，一任务/run/marker、无残留。

初稿两P2已关闭：提前退出不能冒充故障注入，worker元数据替换不能漏掉仍活的原进程。旧假绿及修后拒绝反例均保留，原交付绑定script `8d75922f…`、helper `c1235e8c…`；见 `d1-node-disconnect-20261108-10/root-integration/` 和独立 `review/candidate-2/`。本批已在新helper `cf2b13c9…` 和新CLI上复验；仍缺网络分区/长中断和离线期间自然完成。新增[Hub重启样例](../../examples/backend_parity/HUB_RESTART.md)仅覆盖接受后丢结果的精确边界，保节点原缓存，实际恢复不能算再次Runtime幂等提交。

全部合同矩阵、传输/撤权、云端项目语义、跨主机/目标OS、真实MuPRO和科学有效性均未完成。文档CI修正及原生AX候选不能作为这些验收证据。

**输入：**
- [共享架构](../design/shared-backend-architecture.md)
- [任务与数据协议](../design/distributed-task-data-protocol.md)
- [跨端验收](../design/distributed-workbench-acceptance.md)
- [发布规格](../specs/README.md)
- [路线图](platform-roadmap.md)

## 0. 分类与读法

| 标签 | 含义 |
|---|---|
| 已发布 | `docs/specs/` 中的契约，或 [Runtime HTTP API v1](../runtime.md#http-api-v1-与代码入口) 和 [Hub](../hub.md) 中已写明的 v1 行为。改变它们须按版本处理 |
| 现行实现 | 代码的实际行为，但没有写成发布契约。D1 不得静默改变，要改须由 root 明确决定并补测试 |
| 拟议 | 三份设计中的新增对象或规则，或本文的建议。都还没有 schema、代码或测试 |
| 缺口 | D1 退出时需要、但现有代码和设计都没给出可执行做法的部分 |
| 依赖决定 | 需要所有者或 root 决定。本文只列候选方案及其影响 |
| unknown | 本轮未核实 |

Claude 编写清单时没有运行产品测试；root 集成时实际运行的子集见[运行验收](../runtime-validation.md)。
未被上述实际进度覆盖的“退出证据”仍为建议产物。
证据文件名沿用[跨端验收 §7](../design/distributed-workbench-acceptance.md#7-证据格式与结果判定)的约定，例如 `run-manifest.json`、`requests.jsonl`、`backend-parity.json`、`resources.json` 和 `assertions.json`。

## 1. 最小无 GUI 装配切片

**目标：** 在一台 Linux 机器上，用同一源码修订启动两种部署角色，不依赖 Desktop、GUI 或 GPU。对同一条合成命令走完四步，再逐项比较两边的结果：
1. 提交；
2. 精确读取；
3. 取消或等待完成；
4. 读取日志和产物。

这是 D1 的第一片。项目服务、Web 和 D2 跨端链都不在本片内。

### 1.1 两种部署的进程计划

各入口均为现行实现；CL-D1-PARITY-11 已按 R1(a) 在单 Linux 主机组合以下两种独立部署，没有新增产品入口。

| 项 | 部署 A：本地 Core | 部署 B：云端/团队协调 |
|---|---|---|
| 执行 | Runtime：`suan server --state-dir A/runtime init`，然后 `start`（`suan/runtime/cli.py:201-223`） | 另起一套 Runtime：`suan server --state-dir B/runtime init`，然后 `start` |
| 协调 | 无，客户端直连 Runtime | Hub：`suan-control init`、`serve`（`suan/control/cli.py:49-117`）。节点代理：`suan-node pair`、`run`（`suan/control/cli.py:145-188`） |
| 客户端 | `suan jobs --state-dir A/runtime …`（`LazyClient`，`suan/runtime/cli.py:521-536`）。Bridge 侧对应 `RuntimeBackend`（`suan/desktop_bridge/backends.py:86`） | 先 `suan connect hub-pair`（`suan/runtime/cli.py:338-343`），再 `suan jobs --hub NAME --node NODE_ID …`（`HubCLIClient`，`suan/runtime/cli.py:37`） |
| 监听 | Runtime 只绑 `127.0.0.1`，不可配置（`suan/runtime/server.py:19-22`） | Hub 默认 `127.0.0.1:8790`（`suan/control/cli.py:60-61`）。节点主动连出，不开放 Runtime 端口（`suan/control/agent.py:664`） |
| 凭据 | Runtime `config.json` 中的 token（`suan/runtime/common.py:173`） | `control.json` 中的 owner token，0600 独占创建（`suan/control/cli.py:19-26,49-55`）；还有 `node.json` 和客户端配对文件 |
| 单实例 | `api.lock` 和 `config.lock`（`suan/runtime/server.py:170`；`suan/runtime/common.py:86,148`） | Runtime B 同左。正式 `suan-control serve` 解析真实状态目录并全生命周期持 `control.lock`；同目录换端口/符号链接仍拒绝第二实例。pair可并行，退出/崩溃释放且不换inode。直接嵌入create_app需调用方保证单实例，不支持多worker共享目录（见 C-11） |
| 平台 | 仅 Linux（`suan/runtime/common.py:109`） | 仅 Linux（`suan/control/cli.py:29-42`） |
| 关闭 | `suan server stop [--supervisor]` 只停 API 和调度，已启动的 worker 继续运行（`suan/runtime/cli.py:319-330`） | 同左，并停止本轮自己启动的 `serve` 和 `node run` 进程 |

**实施方式由 root 决定。** 两个候选：
- **(a) 不改产品代码。** 用测试 harness 编排上表的现有入口，先得到两部署的比较基线。
- **(b) 新增统一装配入口。** 例如一条按角色组合 Runtime、Hub 和节点代理的命令。它的名称、参数和打包都未定，不能写成已发布 CLI。

本文建议先做 (a)，再做 (b)。这样 (a) 的比较结果就是 (b) 必须保持的语义。

### 1.2 切片门

| ID | 门 | 类别与现状 | 退出证据 |
|---|---|---|---|
| G1-1 | 两部署用同一源码修订的同一安装。不共享状态目录、数据库、端口或个人凭据 | 当前样例已验：逐模块 base/SHA 相同；新建两套私有状态和进程，源码头仅作参考，实际 SHA 绑定执行字节 | `run-manifest.json`、`resources.json` 及 root 的 `installed-product-binding.json` |
| G1-2 | 无 GUI 启动：环境中不设 `DISPLAY` 和 `WAYLAND_DISPLAY`；独立 venv 只装 `.[server,control,test]` | 最小安装和 unset 显示环境已验；Runtime CI 的较多 extras 不替代该证据。尚未逐服务采集完整 `sys.modules` | `minimal-imports-58.json`、`installed-final/`；各服务内部模块清单仍待专门核验 |
| G1-3 | 合成命令在两条路径上字面相同 | 当前样例已用同一固定公开程序及 `{python}` argv；B 注册精确运维模板，不使用仅由节点展开的 `@python`。未运行 `muferro-example` | `run-manifest.json` 的模板 argv SHA 和冻结样例源码；`requests.jsonl` 只列实际记录的创建/提交/首次取消，不保存原环境 |
| G1-4 | 每个部署只写自己的 state dir。收尾时只清理本轮拥有的进程和目录 | 正常路径及信号竞态、配置检查失败、扫描/移除失败等反例已验；有清理错误不能 ok，API/监督器停止不等于取消任务 | `resources.json`、`final-joint.xml` 及 `final-boundaries-red.xml` 中的两红例 |
| G1-5 | 本片不比较项目语义 | **缺口。** 云端角色目前没有项目应用服务。Hub 提供的是配对、设备、action、blob/上传、图谱目录、节点连接，以及一个简易会话消息接口；该接口用消息 ID 幂等，同 ID 不同内容时返回 409（`suan/control/app.py:282-639`，会话部分在 `:580-600`）。这个会话接口不是 Synthrix 的对话或科研领域服务。ProjectStore 只有本地 SQLite（`suan/project/store.py`） | 本片只比较任务生命周期命令。项目语义的双部署比较列为 D1 后续片，承载方式见 §7.2 的 R2 |

## 2. 同语义合同矩阵

本节比较现状：A 是直连 Runtime，B 是 Hub → 节点代理 → Runtime。差异分三类：
- **业务差异**：D1 必须消除，或明确拒绝相应操作；
- **部署/策略差异**：必须由能力或策略声明解释；
- **投影差异**：允许存在，但要写明。

正常样例现有12断言：除状态、同路径重放/冲突、下载字节、UTF-8日志、取消和启动数外，核五个时间字段在各部署与自身原Runtime精确一致，以及原任务created_at重放不变、固定text/plain产物MIME。不同部署不比较墙钟大小或假设时间单调；五字段必有值只针对两个确已执行的终态夹具，未执行任务仍按原契约允许缺省/null。更多状态、输入传输、撤权和其他故障仍缺，不能据此宣称整个矩阵通过。

| 命令 | A：直连 Runtime | B：Hub → 节点 → Runtime | 类别 | D1 比较规则 |
|---|---|---|---|---|
| 健康/能力 | `GET /v1/health`：`api_version:1`；`features` 为 `events`、`input_checksums`，可能另有 `federation_owner`（`suan/runtime/server.py:92-98`） | Hub `FEATURES`（`suan/control/app.py:24,282-284`）；节点 `FEATURES` 经心跳上报（`suan/control/agent.py:42`）；`GET /api/v1/policy` 给出 `read_kinds` 和 `review_policy`（`suan/control/app.py:320-329`） | 已发布，两边各自是 v1；能力名称不同 | 差异只能用能力声明解释。缺能力时明确拒绝，不静默降级 |
| `workspace.create` | 可选 key。工作区 ID 取 `sha256("workspace:"+key)` 的前 32 位；同 key 不同名时报错（`suan/runtime/service.py:46-60`） | ID 为 `action_id("workspace.create", node_id, key)`，无 key 时为 uuid4（`suan/desktop_bridge/backends.py:309-311`）；节点把 action ID 作为 Runtime key（`suan/control/agent.py:340-341`） | 现行实现。同一用户 key 在两边得到不同工作区 ID | 同一路径重放的结果一致；不要求跨路径 ID 相同 |
| 输入登记 | 直接上传到 Runtime 工作区（`suan/runtime/server.py:129-141`；`suan/runtime/service.py:80-155`） | 先进 Hub 的内容寻址 blob，再用 `workspace.import` action 复制到节点（`suan/desktop_bridge/backends.py:385-398`）。只有 desktop profile 客户端能上传（`suan/control/app.py:326`）；有配额并在 24 小时后回收（`suan/control/cli.py:76-81`） | 现行实现，两步路径与配额属部署差异 | 本片用无输入或固定小输入。输入登记单列比较：比最终工作区的 `{path,size,sha256}`，不比中间路径 |
| `task.submit` | `POST /v1/tasks {spec, idempotency_key}` 返回 202。`request_key` 只在该 Runtime 库内唯一；同 key 同 spec 返回原记录，同 key 不同 spec 返回 HTTP 400（`suan/runtime/store.py:51-61`；`suan/runtime/service.py:157-198`；`suan/runtime/server.py:101-105`） | action ID 为 `action_id("task.submit", node_id, key)`（`suan/desktop_bridge/backends.py:75-77,328`）。Hub 上同 ID 不同 body 返回 400（`suan/control/store.py:170-186`；`suan/control/app.py:253-265`）；节点缓存同 ID 不同请求时拒绝（`suan/control/agent.py:297-316`）；节点把 action ID 作为 Runtime key（`suan/control/agent.py:346`） | 已发布加现行实现。**同一用户 key 在两边映射为不同的 Runtime key** | 恢复必须沿原路径和原 authority。比较的是"同路径重放"语义；用同一个 key 改走另一条路径会产生第二个任务（反例 X3） |
| 冲突的错误形状 | 400，`{"error": "Idempotency key was already used for a different task"}`（`suan/runtime/store.py:56-57`） | 400，FastAPI 默认 `detail` 字段：`"Action ID already used for a different request"`（`suan/control/store.py:179-180`） | 现行实现。Bridge 靠**英文消息子串**把两者都归为 `conflict`（`suan/desktop_bridge/backends.py:60-62`；`suan/desktop_bridge/hub.py:210-211`） | 按冲突类别归一，同时保留原文。在没有版本化的稳定冲突码之前，改动这两段错误文本会破坏客户端分类，属兼容门 C-5 |
| 人工复核 | 无 | 新命令、模板变更和高资源请求进入 `review`（`suan/control/policy.py:186-207`）；复核策略为 any、not-self 或 owner（`suan/control/cli.py:85-88`；`suan/control/app.py:352-366`） | 部署/策略差异，已在 [Hub](../hub.md) 文档写明 | 由 `/api/v1/policy` 解释。不在 A 侧模拟复核，也不为对齐而关闭 B 侧复核 |
| `task.get` | `GET /v1/tasks/{id}`，返回含 `spec` 的完整记录和 `monitor` 摘要（`suan/runtime/service.py:242-252`） | 精确读取：节点 features 含 `read` 和 `task.get`、且 Hub `read_kinds` 含 `task.get` 时，走 `POST /api/v1/nodes/{id}/read`；节点离线时返回 `unavailable`。投影去掉 `spec`（`suan/control/agent.py:257-260,347-352`；`suan/desktop_bridge/backends.py:248-272`）。CLI 固定 `require_live=True`（`suan/runtime/cli.py:101-102`） | 已发布加现行实现。`spec` 的差异属投影差异 | 比较 `state`、`reason`、`cancel_requested`、`attempted_at` 和时间字段。B 侧做最终核实时必须 `require_live`，旧快照中查不到任务不等于不存在 |
| 列表 | 数据库中的全部任务（`suan/runtime/store.py:70-73`） | 心跳快照，最多 200 条，标注 `heartbeat_snapshot`（`suan/runtime/cli.py:94-99`） | 现行实现差异 | 列表不用于判断任务是否存在；不比较列表全集 |
| `task.cancel` | 无 key。已到终态时返回原记录；否则置 `cancel_requested`，尚未派发时记为 `cancelled`（`suan/runtime/service.py:200-211`） | `task.cancel` action：有 key 时 ID 为 `action_id("task.cancel", node_id, key)`，否则为 uuid4（`suan/desktop_bridge/backends.py:330-332`）。CLI 自动生成并打印 key（`suan/runtime/cli.py:589-601`） | 现行实现差异 | 比较最终的 Runtime 事实。B 侧不带 key 的取消每次都是新 action，本片必须带 key |
| 日志/事件 | 按字节偏移，返回 `offset`、`next_offset`、`terminal`（`suan/runtime/service.py:213-240`） | 走只读路径或只读 action，偏移语义相同（`suan/desktop_bridge/backends.py:334-357,361-369`） | 已发布（[events v1](../specs/stk-events-v1.md)） | 偏移逐字节一致；不改成事件序号 |
| 产物/文件 | 只有终态任务能读产物清单；文件按块读取（`suan/runtime/service.py:254-284`） | `task.artifacts`；`file.read` 每次 1 MiB，base64 编码（`suan/control/agent.py:356-366`） | 已发布。传输编码不同属投影差异 | 比较 `{path,size,sha256,media_type}` 清单和下载字节的 SHA |
| 认证/授权 | 单一 bearer token，相当于 owner 权限（`suan/runtime/server.py:47-50`） | 设备凭据可撤销，撤销后返回 401（`suan/control/app.py:157-165,306-315`）。CLI 撤权后被拒绝由 `tests/test_runtime_hub_cli.py:153` 覆盖；`tests/test_control.py:30` 只断言凭据失效，不断言 HTTP 状态码。任何已配对客户端都能列出和读取所有非联邦 action（`suan/control/app.py:336-350`） | 现行实现。**两边都没有按项目或用户的授权**（缺口） | 本片只证明 B 侧撤权后拒绝。A 侧没有设备概念，作为部署差异声明。按项目授权见 §4 的 X5 |
| authority 身份 | 没有独立于配置的持久实例身份 | `server_key = sha256(url + "\0" + node_id)[:16]`，只能防配置误指向（`suan/desktop_bridge/backends.py:207-209`） | 缺口。TaskRef/authorityId 属拟议 | 本片记录"同地址换实例"无法识别，是 D2 前的已知限制 |

## 3. 旧 CLI、Bridge 与 Runtime 的兼容门

D1 的任何改动都要先过下面这些门。"测试入口"均为基线中已有的测试，本轮没有运行。

| ID | 必须保持的行为 | 类别与依据 | 测试入口 |
|---|---|---|---|
| C-1 | Runtime `/v1` 的路由、状态码和 `features`；`TERMINAL` 集合为 succeeded、failed、cancelled，其中不含 `unknown` | 已发布：[Runtime HTTP API v1](../runtime.md#http-api-v1-与代码入口)；`suan/runtime/server.py:92-145`；`suan/runtime/models.py:8` | `tests/test_runtime.py`（`server` 标记）；`tests/test_runtime_events.py`；`tests/test_runtime_input_hashes.py` |
| C-2 | 旧 TaskSpec 省略 `input_hashes` 时，序列化和幂等摘要保持原样；Runtime 不支持 `input_checksums` 时拒绝冻结输入 | 已发布；`suan/runtime/service.py:160-164`；`suan/desktop_bridge/backends.py:127-128,325-326` | `tests/test_runtime_input_hashes.py` |
| C-3 | Bridge `protocol:1` 握手：版本不符时拒绝，并返回 `supported` 列表；params 是闭集；错误码是闭集 | 已发布：[desktop bridge v1](../specs/stk-desktop-bridge-v1.md)；`suan/desktop_bridge/protocol.py:18,26`；`suan/desktop_bridge/server.py:1078-1087`；`suan/contracts/schemas/desktop-bridge-1.schema.json` | `tests/test_desktop_bridge.py`；控制台操作的固定集合在 `tests/test_desktop_scripts.py` |
| C-4 | 精确读取的能力门：Hub 和节点都支持 `task.get` 才精确读；否则在 `require_live` 时明确 `unsupported`；任务超出 200 条心跳窗口后仍可读 | 现行实现；`suan/desktop_bridge/backends.py:248-272`。Bridge v1 §7 的旧描述仍允许心跳读取，文档差异待正式实现时校准 | `tests/test_runtime_hub_cli.py:174`（超过 200 条）、`:225`（旧 Hub/节点）、`:281`（投影） |
| C-5 | 冲突分类：Runtime 和 Hub 的冲突文本保持现状，否则需要 Bridge 两处映射与一个版本化的稳定冲突码同时落地 | 现行实现；`suan/desktop_bridge/backends.py:60-62`；`suan/desktop_bridge/hub.py:210-211` | 缺少直接测试"消息文本 → `conflict`"的用例（缺口）；相关行为由 `tests/test_desktop_bridge_runtime.py:164` 间接覆盖 |
| C-6 | Hub action 的 ID 派生和缓存重放：同 ID 同 body 返回原记录，同 ID 不同 body 返回 400；节点缓存按 action ID 保存 | 现行实现；`suan/desktop_bridge/backends.py:75-77`；`suan/control/store.py:170-186`；`suan/control/agent.py:309-316` | `tests/test_control.py:46` |
| C-7 | CLI 丢失回复后用原 key 和原 action 恢复，不重新提交；`jobs action` 解析未决提交 | 现行实现；`suan/runtime/cli.py:57-85,604-614` | `tests/test_runtime_hub_cli.py:90` |
| C-8 | 关闭 API 或 Bridge 不取消 Runtime 任务；Bridge 重启后原 key 幂等 | 已发布：[desktop bridge v1](../specs/stk-desktop-bridge-v1.md)；`suan/runtime/cli.py:319-330` | `tests/test_desktop_bridge_runtime.py:49,164,276` |
| C-9 | 项目运行记录用冻结方案中的固定 `idempotency_key` 提交，用 `key + ":cancel"` 取消；已接受的 task ID 不可替换 | 现行实现；`suan/desktop_bridge/project_runs.py:49-51`；[项目运行记录](../project-runs.md) | `tests/test_project_runs.py`；`tests/test_bridge_analysis_runs.py` |
| C-10 | 服务端只在 Linux 运行；在 Windows 和 macOS 上 `suan server init` 与控制服务拒绝初始化，且不创建任何文件 | 现行实现；`suan/runtime/common.py:109`；`suan/control/cli.py:29-42` | CI `.github/workflows/runtime.yml:174-189`（客户端任务） |
| C-11 | 同一Runtime state只有一个API；同一Bridge状态目录第二实例回答busy后退出；正式Hub serve同真实状态目录第二实例报错并退出1 | `suan/runtime/common.py::instance_lock`、`suan/desktop_bridge/server.py::StateDirLock`；新增 `suan/control/cli.py::serve` 全生命周期持control.lock，pair不共用该服务锁，直接factory部署须调用方管理 | Hub：`tests/test_control_singleton.py` 11例含不同端口/alias、TERM/KILL后同inode重启、pair并行、独立目录和异常释放；相关49项及主线271项通过。Bridge原测试保留；Runtime API锁仍无专门双进程新测试 |

**CI 入口：**
- Linux 服务端测试由 `.github/workflows/runtime.yml:31` 运行：`pytest -m "not desktop and not perf"`，三个 Python 版本。
- Windows 和 macOS 客户端测试由 `.github/workflows/runtime.yml:174` 运行：`-m "not server and not desktop"`。
- Desktop 工作流的 push 触发带路径过滤（`.github/workflows/desktop.yml:38-48`）。只改 `docs/` 不会触发它，所以只改文档的提交不能证明原生回归。

## 4. 反例清单

ID 前缀 X 是本文编号；括号里给出对应的[跨端验收](../design/distributed-workbench-acceptance.md#5-失败注入与通过条件)用例。

| ID | 注入或动作 | 期望 | 现状与类别 | 测试入口 / 退出证据 |
|---|---|---|---|---|
| X1（F01） | 提交已持久化后丢失回复；冷重开后用原 key 恢复 | 返回原记录；执行启动次数不增加 | 两条路径都已实现：Runtime 用 `request_key`，Hub 用确定性 action ID | `tests/test_runtime.py:25`；`tests/test_desktop_bridge_runtime.py:164`；`tests/test_runtime_hub_cli.py:90`。D1 需要两部署各跑一次并计启动次数（`execution.json`） |
| X2（F01/F02） | 同 key 换 spec；同 action ID 换 body | 明确冲突，原记录不变 | 已实现，两边都返回 400；分类依赖文本（C-5） | `tests/test_control.py:46`；Runtime 侧见 `suan/runtime/store.py:56-57` |
| X3 | 同一用户 key 先走 A 提交，再改走 B（或反过来）"恢复" | 不应被当成同一操作恢复；应被识别为不同 authority 或拒绝 | **缺口。** 两边的 Runtime key 不同，会产生第二个任务，且没有任何提示 | 无现有测试。拟议：记录原 authority 和原路径，恢复时比对（依赖 TaskRef，属拟议） |
| X4（F05） | 排队中取消、运行中取消、取消回复丢失 | 取消意图幂等；只有核实退出后才是 `cancelled` | Runtime 侧已实现；B 侧只在带 key 时幂等 | `tests/test_runtime.py:115,511,556`；`tests/test_runtime_hub_cli.py:153` |
| X5（F10） | 撤销设备后热缓存读取、冷重开、原 key 重放 | 当前授权先于返回数据 | 设备级撤权已实现（401）。**缺口：** ① 任何已配对客户端都能读所有非联邦 action；② 另一设备用相同 ID 和 body 重放时，`create_action` 直接返回原记录，不检查提交者（`suan/control/store.py:177-186`）；③ 没有按项目或用户的作用域 | `tests/test_control.py:30`；`tests/test_runtime_hub_cli.py:153`。②③没有测试，需要先有授权模型（依赖决定，见 R3） |
| X6（F13） | 旧 Hub 或旧节点缺 `task.get`；任务超出心跳窗口 | 明确不支持；已知任务不因列表中没有就变成"不存在" | 已实现 | `tests/test_runtime_hub_cli.py:174,225` |
| X7（F03） | 节点代理或 Hub 重启，期间 worker 完成 | 最后的任务事实和观察可用性分开展示；失联期间保留最近一次任务状态 | 单机真实线路已验 NodeAgent 离线及 Hub 进程停止期间原任务自然完成。离线时精确读取明确拒绝。恢复后首个精确答复为同一任务成功，固定日志与产物校验通过。Hub 停机场景核对同一动作请求、一次 Runtime 提交入口及对应成功返回。网络分区与产品观察界面继续验收 | `examples/backend_parity/disconnect.py`、`hub_restart.py` 及对应测试。NodeAgent 离线完成 12/12，旧取消 10/10。Hub 停机完成 13/13，默认丢回执 11/11，均有隔离安装证据 |
| X8 | 两个实例写同一项目：同修订上的两个不同操作 | 只有一个成功，另一个冲突 | 本地已实现：`expected_revision` CAS（`suan/project/store.py:229,289`）和 format-15 编辑回执（[project-edit-operations-1](../specs/project-edit-operations-1.md)）。**跨部署没有对应承载**（G1-5） | `tests/test_project_edit_operations.py:78,103,196` |
| X9 | 同一地址换成另一个 Runtime 实例 | 拒绝把新实例当原服务 | **缺口：** 只有配置级 `server_key`，无法认证实例 | 无测试；依赖拟议的 authority 身份 |
| X10 | 刷新、重开、订阅、等待超时 | 不重新提交，不取消，不调用模型 | 现行实现中提交和取消都是显式命令 | `tests/test_desktop_bridge_runtime.py:405`。D1 要在两部署上各记一次（`requests.jsonl` 中零新增提交） |

## 5. 入口、缺少的资产与逐项退出证据

### 5.1 D1 要拿出的证据

| 退出项 | 证据 | 依赖 |
|---|---|---|
| E1 两部署启动 | `run-manifest.json` 和 `resources.json`；按 G1-1 至 G1-4 | 只需 Linux 和独立 venv，不需要 GPU、许可或外部网络；本机回环通信仍须可用 |
| E2 合同矩阵比较 | `backend-parity.json`：§2 每一行的两边原始请求与回复、归一化规则、允许差异的理由 | G1-3 的命令统一 |
| E3 兼容门回归 | §3 每项测试的实际运行记录（命令、Python 版本、通过/失败/跳过数、XML 报告） | 在 root 的整合构建上运行；本文未运行 |
| E4 反例 | `assertions.json`：X1、X2、X4、X6、X10 在两部署上的结果；X3、X5②③、X9 以 `blocked` 或 `fail` 如实记录，不改写为通过 | X3、X9 依赖 authority 身份；X5 依赖授权模型 |
| E5 无 GUI | G1-2 的进程模块检查 | — |

### 5.2 本片不具备、不能用桩代替的资产

| 资产或能力 | 状态 |
|---|---|
| 云端项目应用服务、Synthrix 级别的对话/科研领域服务，以及 PostgreSQL 项目仓储 | 不存在（缺口，见 G1-5 与 R2）。Hub 现有的简易会话接口不能顶替 |
| 账号映射和按项目、用户的授权 | 不存在（X5） |
| 多租户执行隔离 | 不存在。现有 Runtime 是个人可信环境，不能对外开放执行 |
| 持久 authority 身份、Attempt、Lease | 只有拟议，见[任务与数据协议 §2–3](../design/distributed-task-data-protocol.md#2-归属一项任务只有一个调度权威) |
| Synthrix 正常启动时的装配 | 本地 `synthrix` 的 HEAD 观察为 `a15ab6b006ae348ef862b03773d6380b2e4abb3d`，与设计基线相同。未查看其内容；是否已接入正常启动由 root 核实。历史 `90d7c4a` 接缝不能当作当前能力 |
| 真实许可软件和 GPU | 不属于 D1 |
| Windows 或 macOS 服务端 | 不支持（C-10） |

## 6. 本轮新决定纳入的兼容门

**来源：** 2026-11-07 所有者对原三项待决的回答，以及首个专业软件的选择。root 把它们写进了 CL-D1-01 任务卡的"本轮新决定"。
方向已获准；HDF5 读取/发现/附加收集和有限 S2c 已有实现及发布扩展，真实软件与 D1 两部署联合验收仍有缺口。下面按当前事实逐项分类，不能用初稿的“均未实现”覆盖已交付能力。

| 原待决或新问题 | 所有者的回答 | 本文如何处理 |
|---|---|---|
| 合作方数据格式 | 格式由插件自己定义；MuPRO 用 HDF5 | 仿真输出格式见 §6.2 的 F-1～F-7。原待决指的是 S3 合作方训练数据格式，那条路径不同，单列为 F-9 |
| MuPRO 电场扫描口径 | 所有者问了它的含义；root 解释为施加方向、最大正负场强、单位、增减顺序、步长、每点步数，以及是否先跑一圈再取数 | 具体数值仍未决定：由插件显式声明参数，数值由研究任务给定（F-8） |
| S2c 智能体权限 | 扩展智能体权限 | 纳入 §6.3 |
| 保存分析修改提案的持久形式 | 未回答 | 仍待决，本文不涉及 |
| 首个专业软件 | MuPRO / MuFerro | 纳入 §6.1 |

### 6.1 执行器与专业软件链（首项 MuPRO/MuFerro）

root 描述的链条是：软件发现 → 能力预检 → 冻结输入 → 显式执行 → 日志与产物核验 → 原任务恢复。下表按这条链列门。

| ID | 门 | 现状与类别 | 测试入口 / 退出证据 |
|---|---|---|---|
| P-1 | 软件发现和预检必须在执行节点上运行，不能在客户端上推断 | **现行实现：** `python -m suan.mupro check` 依次检查环境脚本、SDK 前缀、程序、`ldd` 动态库、`mpiexec` 和 `MUPROROOT`，不读许可内容（`suan/mupro/run.py:466-530,565`）。**缺口：** 预检结果没有进入 Runtime 的 `features`（`suan/runtime/server.py:92-98`），也没有进入节点心跳 `FEATURES`（`suan/control/agent.py:42`）。因此 Hub 和 Web 无法按"真实可用的执行器"放置任务，这与[任务与数据协议 §7](../design/distributed-task-data-protocol.md#7-身份放置与本地能力)的放置条件不符 | 拟议：节点按执行器分别声明能力和版本，并区分"已安装""预检通过""最近一次真实运行成功"。`check` 通过不等于许可 checkout 成功，后者只能由真实运行证明 |
| P-2 | 许可只留在执行节点；许可内容不进 TaskSpec、日志、项目字段或证据包 | **现行实现：** 许可目录通过 `--license-dir` 设为 `MUPROROOT`，内容从不读取（`suan/mupro/run.py:346-347,407`）。但这个路径和 SDK 前缀、环境脚本路径一起写进了 argv（`suan/mupro/spec.py:35-40`），见 R7 | 证据包只记录"许可目录已配置 / 预检状态"，不记录路径原文 |
| P-3 | 冻结输入：提交时固定输入的 SHA，执行时不再读取可编辑参数 | 已发布：C-2 的 `input_hashes`。现行实现：MuFerro 输入上限 256 MiB（`suan/workflows/muferro.py:51`）；逐行运行时，参数与冻结值不符就拒绝，并要求作为新运行重跑（`suan/desktop_bridge/workflow_runs.py:345-351`） | `tests/test_runtime_input_hashes.py`；`tests/test_bridge_workflow_muferro.py` |
| P-4 | 显式执行：两部署的执行入口都是明确命令；Hub 侧非模板命令照常进入复核 | 现行实现：内置模板 `muferro-example`（`suan/control/templates.py:14-17`）；非模板命令和高资源请求进入复核（`suan/control/policy.py:186-207`）；在 Slurm/PBS 分配之外，本机 `mpiexec` 会被拒绝，除非运维在 Runtime 环境中设置 `STK_ALLOW_LOCAL_MPI=1`（`suan/runtime/launch.py:26-31`）；任务不能自己设置这个变量（`suan/runtime/models.py:16-17`；`suan/runtime/worker.py:136-142`） | 同一 MuFerro 算例在 A、B 各执行一次，记录 argv、复核动作和实际启动次数 |
| P-5 | 输出核验：按 MuPRO 输出合同核验后才算完成 | 现行实现：`verify_run`，合同 `stk-mupro-1`（`suan/mupro/run.py:205`）；connector 的 `verify` 包装同一函数（[data format v1 §14](../specs/stk-data-format-v1.md#14-reference-mapping-muferro-public-connector-mupromuferro)） | 现有 MuPRO 测试；真实运行的 `artifacts.json` |
| P-6 | 原任务恢复：重启或断线后接管原来的远端任务，不重新提交 | 现行实现：逐行身份为 `workflow-run:{run}:{step}:{row}:{attempt}`（`suan/desktop_bridge/workflow_runs.py:366`）；上一次尝试的远端任务只要没有失败或取消就接管（`:355-365`） | `tests/test_bridge_workflow_muferro.py`；`tests/test_bridge_workflow_runs.py`。D1 中经 Hub 接管时，同样受 X3 的路径约束 |
| P-7 | 真实资产 | **未就绪：** 本会话的 shell 中 PATH 上没有 `muFerro`，也没有设置 `MUPRO_SDK_PREFIX`；root 实际 `check --json` 退出 1。此结论仅限当前配置和有界安装候选检查，不是穷尽安装搜索，不读取合作方私有实现补猜格式 | root 的预检结果见运行验收；现有假求解器回归不计真实 MuPRO 运行通过 |

### 6.2 插件定义原生格式；MuPRO 用 HDF5

| ID | 门 | 现状与类别 | 测试入口 / 退出证据 |
|---|---|---|---|
| F-1 | 新格式通过现有插件机制接入：connector 和 inputs 两类 entry point，在 `info().capabilities` 中声明带版本的读取器；不改 `API_VERSION` | 已发布：[connector 接口 §13](../specs/stk-data-format-v1.md#13-connector-interface-suanconnectorsapipy-api_version--1)；`suan/connectors/api.py:31-32`。现行实现：优先级、白名单 `connectors.allow`，坏插件不拖垮注册表（`suan/connectors/registry.py:27-32,80-135`） | 现有 connector 测试；新增读取器后，旧注册表诊断结果不变 |
| F-2 | MuPRO 的 HDF5 由插件读取，与 VTKHDF + STK profile 分开，不强制转换 | 已发布 `mupro.hdf5@1` / `stk.source.mupro_hdf5@1`；连接器 0.2.0 从选定案例的 `run.h5` 发现 `hdf5:<field>`，保留 selector、原 dtype 和容器 SHA。见 [MuPRO HDF5/1](../specs/mupro-hdf5-1.md) | 合成读取/发现/CLI 原值回归已记录；真实 MuPRO 输出仍待资产。单位、六分量意义和求解成功不推断 |
| F-3 | 旧的 `.dat` 运行和已有项目保持可读 | 现行实现：帧文件规则 `FRAME`（`suan/mupro/run.py:48`）和 `mupro.dat@1` 读取器 | 旧结果表、旧运行目录的回归读取 |
| F-4 | 陈旧输出预检与最终状态输入覆盖 HDF5 | root 已复现 CLI 和计算侧均会接受遗留 `run.h5`，本轮把该已发布输出名加入可选产物预检；不把它加入 DAT 必需完成文件。最终状态保留完整 HDF5 容器；工作流收集/下游快照按 100 文件/256 MiB 拒绝超限，不自动裁剪 | 两条旧输出反例及其他 HDF5 输入名仍可用的对照；最终联合结果见运行验收。HDF5-only 完成仍未实现 |
| F-5 | 读取 HDF5 的节点必须真的装了 h5py；缺依赖时声明读取器不可用，而不是运行到一半才失败 | **缺口：** h5py 是可选依赖（`pyproject.toml:61`），只在 `science`、`desktop`、`visualization` extras 中；`server` extra 为空（`pyproject.toml:86-94`） | 在只装 `.[server]` 的节点上检查能力声明 |
| F-6 | HDF5 库版本兼容 | unknown：实际求解器使用的 HDF5 版本和输出特性尚未核实，不能从目录名推断 ABI 或可读性 | 记录求解器及读取端版本，用固定版本的 h5py 读取一份真实 MuPRO 输出 |
| F-7 | 核验合同 | 已发布 HDF5/1 读取与附加收集，仍要求 `stk-mupro-1` 的 DAT 完成核验；读取 HDF5 不代表求解成功。新增 `run.h5` 陈旧产物预检不改变必需完成文件 | HDF5-only 求解完成须取得真实输出和版本化核验合同后另验，不能据读取通过宣称实现 |
| F-8 | 电场扫描参数 | **依赖决定：** 由插件显式声明扫描参数，STK 不提供默认值；具体数值由研究任务给定，尚未确定 | 声明缺参数时拒绝准备运行；参数随冻结计划保存 |
| F-9 | S3 合作方训练数据：插件定义的格式先映射到现有 `stk.dataset/1` 目录，或经版本化扩展后再接入；训练冻结 capsule `stk.materials-training-input/1` 不变；来源、许可、敏感级别和合成标记必须保留 | 现行实现：`stk.dataset/1` 契约与校验器（`suan/materials/datasets.py:21`）；训练 capsule（`suan/materials/inputs.py:20`）；[materials-training-1](../specs/materials-training-1.md)。**缺口：** 还没有从插件格式导入 `stk.dataset/1` 的接口；connector API 面向仿真输出读取，不能直接充当训练数据导入 | 一份插件格式样本导入后通过现有 `stk.dataset/1` 校验器，数据卡保留上述字段。MuFerro 生成的 P–E 回线数据集同时受 F-8 约束 |

### 6.3 S2c：智能体准备运行，人批准后开始

设计见[智能体设计的 S2c 节](../design/agent-harness.md#s2c视所有者决定)。所有者 2026-10-09 的决定 3 已写明"智能体准备运行计划、人在卡片上批准后开始"；2026-11-07 的"扩展智能体权限"批准进入开发。

| ID | 门 | 现状与类别 | 测试入口 / 退出证据 |
|---|---|---|---|
| A-1 | 只给明确工具 `prepare_run`，不放开智能体提交或修改 | 现行实现：`AGENT_LEVELS` 增加 `prepare_run`，唯一注册工具为 `prepare_muferro_run@1`；参数恰工作流、1–100 个既有案例行及原修订。旧会话冻结头不增权，`submit_run` 不进智能体 | `tests/test_agent.py` 的精确集合、`tests/test_agent_muferro_prepare.py` 的领域/参数/回放反例；不是放行该级别的任意工具 |
| A-2 | 准备只冻结本地计划和待批准项 | 现行实现：`prepare_muferro_run` 仅取桌面明确冻结的目标，调用本地 `WorkflowRuns.prepare`；不调用 `MuFerro.prepare`、上传、Runtime 或执行器，也不为模型补主机/资源 | `tests/test_agent_muferro_prepare.py`；真实 Runtime 的准备后零任务检查见 `tests/test_agent_muferro_acceptance.py` |
| A-3 | 完整计划复核后人工单次批准首次开始 | 已发布 `project.agent.run_plan/run_decide/run_observe`，仅桌面。目标、会话停止及本进程容量先准入，再持久消费决定；后台 `WorkflowRuns.start(approval=...)` 在追加 started 同一 IMMEDIATE 事务核计划/请求 SHA、修订、归档及任何历史 started。消费和 claim 是两事务，未知不得重派；省略 approval 的普通人工重启独立 | `tests/test_agent_run_bridge.py`、`tests/test_agent_run_approvals.py`、`tests/test_workflow_run_approval.py` 和 `tests/test_workflow_target_binding.py`；包含停止后重放、手工抢先启动、多进程竞争及真实后端端点绑定 |
| A-4 | 桌面批准不能替代 Hub 复核或资源准入 | Hub 复核仍按现有策略实施；当前 MuPRO 准备明确拒绝 Hub，只支持直连/SSH。不能把一般任务的 Hub 双部署 harness 算成 S2c 经 Hub 已验 | 将来扩展 Hub 准备须独立处理审核暂停及原身份恢复，保留非模板/高资源复核 |
| A-5 | 数据与模型边界不变：规划只用本机或机构内模型；子请求只有在读过的数据全部公开时才可外发；不改端点或密钥 | 已决定（2026-10-09 的决定 2、4） | 现有智能体测试；扩展后重跑 `tests/test_agent.py`、`tests/test_agent_sessions.py`、`tests/test_agent_muferro_acceptance.py` |
| A-6 | 本地或集群的 MuPRO 首次执行都须人工批准 | 当前扩展只允许本地准备，未授权智能体自动开始轻量计算。桌面显式资源和完整计划门保留 | R9；资源选择不等于开始授权，刷新/重开/恢复不自动派发 |

### 6.4 与 D1 两部署的交点

- 智能体开始的 MuPRO 运行同样受 X3 约束：必须记录原路径和原 authority，不能用同一个 key 换路径"恢复"。
- G1-3 的合成命令可以沿用 `muferro-example` 的 `{python}` 写法，但真实 MuPRO 运行要等 P-7 的资产到位；D1 的语义比较仍建议先用不需要许可的合成命令。
- P-2 的 argv 路径在部署 A 的 `task.get` 中可见、在部署 B 的投影中不可见，`backend-parity.json` 要把这一点标为投影差异。

## 7. 交付核对与 root 审阅问题

### 7.1 Claude 编写清单时实际执行的检查

- 读取了上述设计、规格、源码和测试文件；行号按基线 `37d26464` 核对。
- 在提交前运行了相对链接/锚点检查、`git diff --check` 和暂存 gitleaks；结果写在交付提交说明中。
- **未运行**任何产品测试、构建、服务、模型请求或 UI。

**AOCI：** 本文的源码定位与清单不能替代任何会话的完整认知收据；没有项目 `.mcp.json` 也不能据此推断 MCP 不可用。
各 worktree 须按实时合同独立绑定认知，合入 main 后由 root 在最终稳定状态维护 main 的索引；不复制 Claude 的 baseline。

### 7.2 请 root 决定或核对的问题

| ID | 问题 | 本文建议 | 影响 |
|---|---|---|---|
| R1 | D1 第一片先编排现有入口，还是同时新增统一装配入口 | root 已选择 (a)：Claude 的 CL-D1-PARITY-11 只新增双部署 harness、说明与测试，先比较真实现有 CLI。统一入口 (b) 留到语义比较后设计 | 未新增或发布角色装配 CLI；两个 Runtime 不共享状态、authority 或恢复 key |
| R2 | 云端角色的项目语义由什么承载：同一 SQLite ProjectStore 加 HTTP 应用服务，还是 PostgreSQL 仓储适配 | 不在本文选择；先把项目语义的双部署比较列为 D1 后续片 | 决定 G1-5 何时关闭，也决定 X8 能否跨部署验证 |
| R3 | 授权模型：Hub 现在是设备级授权，D1 是否引入按项目或用户的作用域 | D1 先声明现状差异，不扩大开放范围；按项目授权进 D2 前置 | 关闭 X5 的②③；与 Synthrix 的 `authz` 迁移相关 |
| R4 | `@python` 与 `{python}` 不对称（G1-3）是只在 harness 中规避，还是把 `demo-field` 模板改用 `{python}` | 只在 harness 中规避；改模板会改变已发布模板，须单独审 | 影响 Hub 模板的精确匹配和既有测试 |
| R5 | 冲突分类依赖英文消息子串（C-5）。是否在 D1 引入版本化的稳定冲突码 | 不在 D1 改；先补一条"文本 → `conflict`"的回归测试锁住现状 | 防止改错误文本时无声地破坏客户端 |
| R6 | (1)正式Hub serve单实例；(2)Hub有未完成action时进程重启 | root已选择正式serve生命周期锁并提交c5d8e503，相关49项通过；Claude13三路径集成ddd7d7c2，最终主线271项及新最小安装11断言通过。保原缓存，驱动绑定须真实文件核验且参与成功门 | 这两个有限缺口已本地关闭；直接create_app多worker、分布式租约及X7其余故障仍未验，未push不继承旧CI |
| R7 | MuFerro 的 `--license-dir`、`--sdk-prefix`、`--env-script` 路径都写进 argv（`suan/mupro/spec.py:35-40`），因而随 TaskSpec 存进 Runtime 库和项目运行计划；直连 `task.get` 能看到，Hub 投影会去掉 | 这些是节点本地路径，不是秘密（许可内容从不读取）。建议先列为已知现状；是否改为节点本地配置由 root 决定 | 影响 P-2，以及任何把 TaskSpec 原文导出或送入模型的路径 |
| R8 | HDF5 陈旧输出及最终状态输入边界 | 本轮已用 CLI 和制造求解器复现 `run.h5` 遗留混入，补可选输出预检及反例；不把所有 `.h5` 都当输出，也不把可选文件变成 DAT 必需文件。最终状态的文件/字节上限继续保留 | 不证明 HDF5-only 完成或真实许可运行；最终测试与提交见运行验收 |
| R9 | 同一批准不能重复启动；扩权不等于自动执行 | 已实现：消费一次后只观察原证据，任何历史 started 都使批准首次 claim 失败；消费前已有手工 started 会拒绝消费并保持待决；决定已消费后的手工竞争启动才观察为 other_start，不能冒充原批准。未授权本地轻量自动开始 | 决定先落盘、claim 同事务复核；两事务间崩溃保留 uncertain，不用新 ID 或换路径补发 |

原三项待决的现状见 §6 开头。仍未决的是：电场扫描的具体参数，以及保存分析修改提案的持久形式。这两项和 PET 新专项，本文都不代为选择。
