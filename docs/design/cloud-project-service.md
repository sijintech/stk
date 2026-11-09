# 云端项目服务：承载方式比较与验收方案（D1，候选设计）

状态：**root 已复审并采纳为 D1 设计比较稿，R2/R3 待决定**（CL-D1-CLOUD-PROJECTS-DESIGN-19）。

- 基线为 `main` 代码提交 `397a464d`，记录日期为 2026-11-09 UTC。本文的源码与测试行号都绑定这个设计基线。
- 本版以 candidate 4 为底稿，按 root 的两项修订意见更正：
  - F1 的线上结果分层：内部 `get` 返回裸回执，线上 `get` 返回 `{receipt}`，`apply_once` 返回 `{receipt, replayed}`；
  - CP-0 的证据层级：反映 root 本地 main 提交 `994a3b1a` 中新增的已提交测试。
- 2026-11-09 证据对齐（CL-D1-CP0-EVIDENCE-MATRIX-25，基线 `5c4723f4`）：只更新 §8.3、§8.4、§9、§10 中的 CP-0 证据。
  - 新增证据以测试名和集成提交绑定，不用行号；原有行号仍绑定 `397a464d`。
  - 设计选项、R2/R3 与已发布契约不变。

**本文不做的事：**
- 不实现任何功能；不新增或修改已发布的方法、schema、认证与授权；不声称已有部署。
- **R2（承载方式）和 R3（项目/用户授权）仍未选择**：本文只列出最小选项、各方职责和约束，以及一份供 root 决定的首片范围。
- 不承诺 PostgreSQL 与 SQLite 语义等价，也不从设计推出任何科学有效性。

R2、R3 与对应缺口见 [D1 兼容门](../planning/d1-compatibility-gates.md)：
- 决定表：第 278–279 行；
- G1-5：第 111 行；
- X5：第 171 行；
- X8：第 174 行；
- 现状缺口：第 194–195 行。

总体方向见[共同后端架构](shared-backend-architecture.md) §5、§7。

## 1. 结论摘要

1. **现有项目语义全部在本地 SQLite `ProjectStore`（format 15）里。** 包括：
   - 稳定 UUID；
   - 普通命令批次的修订 CAS；
   - 永久的 `apply_once` 成功回执，主键为 `(scope, operation_id)`；
   - 撤销/重做 journal；
   - 只追加的输入快照；
   - 校验过的备份与显式升级。

   云端角色目前没有项目应用服务（G1-5）。Hub 只有设备级授权和 action/blob 等协调接口，没有项目权限。
2. **已有一个可借鉴的先例：** `suan/peer/` 的受限项目适配器，用 `PeerAuthority` 加 `PeerProjects` 包住同一个 `ProjectStore`。它的基础子集是 `peer.hello` 加四个项目方法：
   - `project.catalog`
   - `project.table.read`
   - `project.edit_operations.apply_once`
   - `project.edit_operations.get`

   它的做法是：
   - 远端按项目 UUID、grant 和数据库 generation 选择目标；
   - 回执 scope 绑定 owner、调用方和 generation；
   - owner 显式 rebind 时轮换 generation；
   - 丢回复后用原 ID 显式 `get`。

   它的范围（[stk-peer-1](../specs/stk-peer-1.md) 第 1–14、246–248 行）：
   - 它是后端原型，经过本机两进程验收；
   - `PeerEndpoint` 之下是真实的原生 helper 通道：一个可选的 CPU WebRTC helper，带有界私有 IPC 和加密通道（`suan/peer/transport.py:1-10`）；
   - 端点本身不开监听端口，没有云 API 服务或部署；
   - 真实跨站与跨平台都还没有验证。
3. **两种承载方式：**
   - **方案 A：** 同一 SQLite `ProjectStore`，置于本机或团队应用服务之后。
   - **方案 B：** 定义仓储端口，SQLite 是第一个适配，其他数据库是后续适配。

   A 能复用**存储层**已验证的项目语义。授权、封闭响应、单进程与 generation 归属仍要新实现、新验证。

   B 能换存储，但每个适配都要逐项重新证明语义。§6 的 28 个文件是一份盘点，不是交付前必须全部改完的门槛；可以按操作族渐进，但同一项目只能有一个事实归属。
4. **共同约束：** 两种方案都必须遵守 §3 的不变量，都通过应用服务层（§4）对外。**桌面 stdio 桥永不暴露到网络。**
5. **建议首片 CP-0（§8.3），与 R2/R3 无关：**
   - 能在本机桥和 peer 两个入口用同一调用验收的行，按同一矩阵比较；
   - 只在 store、只在 peer、或只能在将来真实服务上验收的行，分开列出，不混签。

   R2/R3 的实现片在 root 决定后再开。

## 2. 现状：源码事实

下表只陈述基线 `397a464d` 中的现有行为。行号对应该提交。

| 能力 | 现有行为 | 证据 |
|---|---|---|
| 项目身份 | `create` 以 `O_EXCL` 创建数据库，写入 `uuid4()` 项目 ID，修订为 0。打开时检查 `quick_check`、外键和"恰好一个项目"；打开后若 ID 变化，报 "database was replaced" | `suan/project/store.py:352-378`、`339-350`、`380-389` |
| 格式 | `FORMAT_VERSION = 15`，`application_id` 为 STKP。只读支持格式 1–15；升级须显式调用，升级前先做校验过的备份，升级后修订加一 | `store.py:23-24`、`615-645` |
| 修订 CAS | `apply`/`undo`/`redo`/`upgrade` 都在 `BEGIN IMMEDIATE` 中比较 `expected_revision`，不一致抛 `RevisionConflict`。归档 `set` 没有 `expected_revision`，也不改可编辑修订 | `store.py:787-791`、`824-827`、`747-752`、`615-621`、`439`；`suan/project/archive.py:1-9`、`94` |
| 预览 | 在内存副本上求值，不持久化。数据库超过 128 MiB 时拒绝 | `store.py:793-818`、`26` |
| 一次性编辑回执 | `apply_once(commands, operation_id, expected_revision, scope)`：<br>- 先按 `(scope, operation_id)` 查回执；<br>- 请求相同，返回原回执（`replayed=true`）；请求不同，抛 `RevisionConflict`；<br>- 没有回执时走 CAS 编辑，回执与编辑在**同一事务**中插入。<br>`get` 只读原回执 | `suan/project/edit_operations.py:148-198`；[project-edit-operations-1](../specs/project-edit-operations-1.md) 第 97–143、161–167 行 |
| 回执预算 | 请求 ≤256 KiB，回执 ≤512 KiB，每项目 ≤10000 条且合计 ≤64 MiB。不做 GC，身份不重用 | `edit_operations.py:15-19`、`178-191`；规范第 145–159 行 |
| 撤销/重做 | 按 journal 恢复差量，修订加一，写入 `changes`。**不删除、不重放回执**；undo/redo 自身没有幂等回执 | `store.py:741-770`；规范第 140–143、184–186 行；`suan/project/journal.py:1-5` |
| 有界读取 | `catalog` 每页 ≤200，`read_table` 每页 ≤500，单次结果 ≤8 MiB。<br>- 续页须带 `expected_revision`，修订一变即冲突；<br>- `read_table` 拒绝同时给 `record_id` 和非零 offset；<br>- 带 `record_id` 时返回包含该记录的那一页 | `suan/project/catalog.py:11-31`、`44-73`、`75-108` |
| 文件索引 | 文件索引是一张固定 UUID 的普通表。项目内位置存相对 POSIX 路径；外部位置存 `external:<platform>` 加原机绝对路径，作为普通记录值保存。登记只看元数据。经授权读这张表，会原样得到这些值 | `suan/project/files.py:1-5`、`60-69`、`76-95` |
| 输入快照 | 清单只追加，清单中的每个文件条目保留原记录的 `path`/`location` 值。对象按内容寻址，存在 `.stk/objects/sha256/`。`resolve` 每次校验字节，并在结果顶层加一个**本机对象路径**。摘要每页 ≤64 | `suan/project/snapshots.py:1-5`、`97-101`、`201-211`、`286-296`、`333-341` |
| 备份 | SQLite 在线备份，校验后以新 UUID 名称原子发布，结果含**本机路径**。不含外部文件和资源 | `store.py:568-613` |
| 归档 | 归档对象被冻结，修改时返回 conflict。归档不改变修订，不进入撤销 | `archive.py:1-9`；`suan/desktop_bridge/projects.py:78-79` |
| 运行记录 | 运行观察不改变可编辑修订。执行者消失后：<br>- 分析运行记为 `unknown`，并注明 "will not be replayed"；<br>- 工作流运行把进行中的尝试记为 `interrupted` 并停止，须显式重新开始 | `suan/project/runs.py:1-5`；`analysis_runs.py:533-544`；`workflow_runs.py:687-700` |
| 热日志恢复（store） | 只有在只读连接上，初次读取遇到精确的 776 时，才允许一次 SQLite 物理回滚。恢复前先核对文件头与 inode；恢复不做业务编辑，不加修订，不重放 | `store.py:391-461`；规范第 116–131 行；`tests/test_project_edit_operations.py:561-656` |
| 桌面桥 | 只通过 `--stdio` 传 NDJSON：<br>- 受信的本机调用方传入绝对目录，桥据此打开项目；<br>- 句柄是一个桥生命周期内的 `uuid4().hex`；<br>- 打开结果含 `directory`；<br>- 桥把 scope 固定为 `local`。<br>项目方法名与 peer 相同：`project.catalog`、`project.table.read`、`project.edit_operations.apply_once/get`；另有 `project.apply` 等本机方法 | `suan/desktop_bridge/__main__.py:1-8`、`72-73`；`suan/desktop_bridge/projects.py:1-4`、`97-123`、`130-138`、`182-188`；`suan/desktop_bridge/server.py:275-279` |
| Peer 适配器（原型） | 基础子集为 `peer.hello` 加四个项目方法，没有第五个项目方法。<br>- 每个业务请求都要带 `project_id`、`grant_id`、`database_generation`；<br>- 拒绝 handle/path/scope 等**协议参数**；<br>- 授权 lease 覆盖整个 store 调用；<br>- 响应的项目、表、字段、记录元数据是封闭 DTO；<br>- 单元格 JSON 是授权内容，不做路径过滤 | `suan/peer/projects.py:1-80`；`suan/peer/protocol.py:23-24`、`190-207`、`282-300`；[stk-peer-1](../specs/stk-peer-1.md) 第 100–176 行（内容与元数据之分见第 121–141 行） |
| Peer 授权 | 授权库与项目分开存放，位于项目之外：<br>- owner 用 `bind_project(directory)` 注册本机项目；<br>- grant 与撤权都在库事务内完成；<br>- 回执 scope 为 `peer/1/` 加 sha256(owner, peer, generation)；<br>- 观察到文件被替换或修订回退时，自动作废；<br>- `rebind_project` 轮换 generation；<br>- 编辑后元数据核对失败时，抛 `PeerOutcomeUncertain` | `suan/peer/authority.py:1-12`、`152-159`、`377-403`、`448-491`、`494-554` |
| Peer 的热日志处理 | 有两条路径，行为不同：<br>- **owner 观察**（`bound_project`，供 peer 文件扩展使用）用 `_BoundProjectStore`，遇热日志即拒绝，要求显式本地恢复；<br>- **peer 项目方法**（`project_access` 经 `_local_project`）用普通 `ProjectStore`，因而继承 store 的 776 物理恢复。<br>基线中没有已提交的专门测试覆盖这两条路径。root 的外部探针已在真实热回滚日志上观察到这两种行为（见 §8.4，不是已提交测试） | `authority.py:54-57`、`405-441`、`377-386`、`518`；`suan/peer/files.py:204` |
| Hub 授权 | 只有 owner token 和设备凭据两种认证。任何已配对的客户端都能读所有非联邦 action。同 ID 同 body 的 action 重放不检查提交者 | `suan/control/app.py:157-167`、`336-350`；`suan/control/store.py:172-187`；D1 兼容门第 135、171 行 |

**现状不是什么：**
- Hub 的简易会话接口不是项目服务（G1-5）。
- 设备配对不是项目授权，也不是用户授权（X5 ③）。
- peer 原型没有云 API 服务、部署或跨站验收；它的本机原生通信是真实的，但只在本机两进程中验收过（stk-peer-1 第 246–259 行）。
- 本机两进程测试不等于云端验收。

## 3. 共同不变量（两种承载都必须满足）

| # | 不变量 | 现有依据 |
|---|---|---|
| I1 | **协议元数据中的对象身份**只用项目、表、字段、记录 UUID 和 `database_generation`，**不用**本机路径、桥句柄、PID、地址或显示名。本机路径与句柄只由受信的本机适配器解析（桥、owner 的 `bind_project`）。peer 调用方是已认证身份；将来网络调用方的身份由 R3 另定 | `projects.py:1`、`97-107`；`authority.py:388-403`；peer 规范第 108–126 行 |
| I2 | 首片的**普通命令批次**（`apply`/`apply_once`）每次都带 `expected_revision`，由同一 CAS 裁决；同一修订上两个不同操作只能成功一个。以下操作另有规则：<br>- undo/redo 也走 CAS，但没有回执（I7）；<br>- 归档不走 CAS（`archive.py:94`）；<br>- 格式 1–14 的项目可读、可普通编辑，回执 API 须先显式升级（I3） | `store.py:824-827`；`tests/test_project_edit_operations.py:196`、`427` |
| I3 | `apply_once` 写入要求调用方显式给出 `operation_id`：<br>- 身份是 `(scope, operation_id)`：同一 UUID 在另一个 scope 中是**另一个新操作**；<br>- 原始请求在生成对象 ID 之前哈希；<br>- 回执与业务行在同一事务内提交，永久保留；<br>- 修订错误时不改变任何状态，也不插入回执 | 规范第 20–31、97–114、145–167 行；`tests/test_peer_projects.py:139-151`、`173-190` |
| I4 | 回执 scope 由受信适配器根据稳定的 owner、调用方与 generation 推导，从不取自请求体，跨重连与重启保持不变。桥固定为 `local` | `authority.py:527-528`；`edit_operations.py:158-164`；`projects.py:182-188` |
| I5 | 回复丢失时，结果是"不确定"。只能用原 ID 显式 `get`，或显式重复完全相同的请求。超时和重连都不自动重放，不改 ID 或修订，不 rebase | 规范第 133–138 行；peer 规范第 160–167、250–264 行 |
| I6 | 读取历史回执前，也要先核当前授权。回执证明的是"历史上成功过"，不证明当前状态 | 规范第 25–31、140–143 行；`peer/projects.py:77-80` |
| I7 | undo/redo 照常走 journal，不撤销回执。它们没有幂等回执；结果不确定时，只能通过 `history` 或修订去观察 | `store.py:741-776`；规范第 184–186 行 |
| I8 | 快照清单只追加。`resolve` 结果顶层的本机对象路径是**本机结果元数据**，网络 DTO 不应带它。清单中保留的 `path`/`location` 是项目内容（I15） | `snapshots.py:1-5`、`286-296`、`333-341` |
| I9 | 恢复或替换数据库要在**服务归属**下显式进行：新 generation 生效，旧 grant 与旧 scope 一律作废。以下两种情况无法从 SQLite 快照本身证明安全，不得宣称全局恰好一次：<br>- 同 inode、未被观察到的带外回滚；<br>- 授权注册表丢失 | `authority.py:8-11`、`466-491`；规范第 177–182 行；peer 规范第 169–176 行 |
| I10 | 文件和资源归数据库所在主机所有。`external:*` 值不是远端可解析的 ID。备份不含外部文件 | `files.py:60-69`；`store.py:610-611` |
| I11 | 非活跃恢复：打开、读取、热日志物理恢复都**不**派发任务、不重复写入、不恢复授权、不运行任何东西。中断的运行只记为 `unknown`/`interrupted` | `store.py:391-425`；`analysis_runs.py:533-544`；`workflow_runs.py:687-700` |
| I12 | 读取有界：页大小沿用 ≤200 / ≤500 / ≤64，单次结果 ≤8 MiB。续页固定在首页返回的修订上，没有"读全部" | `catalog.py:11-53`、`84-88`；`snapshots.py:210-211` |
| I13 | 错误返回固定、有界的代码与描述，不带 SQL、路径或原始异常 | peer 规范第 266–272 行 |
| I14 | 每个项目只有一个事实归属服务接受写入。其他实例只转发，或提供带观察时间的投影；不自动合并副本 | 共同后端 §5（第 111–118 行）；peer 规范第 149–150 行 |
| I15 | **内容与元数据分开处理：**<br>- 协议元数据是封闭 DTO，不带路径、句柄、PID；<br>- 授权单元格 JSON 是用户内容，可以合法地含有 `path` 等键和路径样的值，读取时原样返回；<br>- 不得为了隐藏路径而静默改写已存的回执、摘要或历史；<br>- 不得宣称做了通用的递归脱敏 | peer 规范第 121–141 行；`protocol.py:282-300`；规范第 86–95 行 |

## 4. 应用服务层（两方案共用；内部草案，未发布）

### 4.1 位置

```text
Desktop(C++) ─stdio─▶ 桌面桥（本机兼容层；本机目录→句柄；scope=local）─┐
CLI / 脚本 ─────────────────────────────────────────────────────────────┤
peer 端点（已认证身份；本机原生传输，两进程验收）───────────────────────┼─▶ 项目应用服务 ─▶ 承载（A：ProjectStore / B：仓储端口）
未来网络适配器（R2/R3 决定后；调用方身份由 R3 定）───────────────────────┘        ▲
                                                                       授权 lease（R3）
```

- 应用服务只处理领域对象和授权 lease，不接受目录、句柄或 scope 参数。
- 本机路径只由受信的本机适配器解析：
  - 桥：本机调用方给出绝对目录；
  - peer：owner 用 `bind_project` 注册目录。
- 桥、peer 和未来的网络适配器把各自的传输身份翻译成"已认证调用方 + 目标"，再调用应用服务。
- 桥仍是 stdio 本机层（共同后端第 91 行；peer 规范第 12–14 行）。网络适配器**不得**转发桥的方法表。

**术语："网络边界"与"网络适配器"。** 本文的这两个词只指将来面向远端调用方的云端或团队服务 API；它的形状待 R2/R3 决定后再定，本文不定义发布契约。
- 这个词**不**覆盖 peer 现有的原生 helper 通道，也不替代它。该通道位于 `PeerEndpoint` 之下（`transport.py:1-10`），是真实存在的加密原生通道，保持原样。
- 加密通道本身不是机器身份：它的 channel binding 必须进入双方签名的授权挑战，之后才路由业务消息（`transport.py:5-7`；peer 规范第 178–221 行）。
- "不开网络端口"指不新增监听或服务，不是说 peer 没有网络通信。

### 4.2 最小操作集（对齐已发布的 peer 子集）

这里列的是语义要求，不是新的方法名或 schema。网络形状由 root 以后按已发布契约单独设计。现有 peer 只有下面四个项目方法，外加 `peer.hello`。

| 操作 | 输入（授权上下文之外） | 语义 |
|---|---|---|
| 结构页（`project.catalog`） | `expected_revision?`、`offset`、`limit ≤ 200` | 等同 `catalog`。续页必须带首页返回的修订。<br>项目信息取这一页中 `project` 的封闭元数据（`id`/`name`/`revision`），**不另设方法**。<br>若将来要单独的"项目信息"操作，须作为候选另行设计。桥 `_info` 中的 `directory` 是本机结果元数据，不进入网络 DTO（`projects.py:110-111`；`tests/test_peer_projects.py:95-104`） |
| 表页（`project.table.read`） | `table_id`、`expected_revision`、`offset`、`limit ≤ 500`、`record_id?` | 等同 `read_table`。<br>store 拒绝同时给 `record_id` 和非零 offset（`catalog.py:85-88`），peer 协议也拒绝（`protocol.py:207`）。<br>带 `record_id` 时返回含该记录的那一页（`catalog.py:97-102`） |
| 一次性编辑（`project.edit_operations.apply_once`） | `operation_id`、`expected_revision`、`commands` | 等同 `apply_once`，scope 由 lease 推导 |
| 原 ID 查询（`project.edit_operations.get`） | `operation_id` | 内部的 `EditOperations.get` 与 `PeerProjects.get` 返回裸回执（`edit_operations.py:148-156`；`peer/projects.py:77-80`）。线上结果在桥和 `PeerEndpoint` 中都包成 `{"receipt": <原回执>}`（`desktop_bridge/projects.py:185-186`；`suan/peer/endpoint.py:516-517`）。<br>只查本调用方 scope 下的回执；`not_found` 不等于没执行。调用方要保留原请求，可显式重复 |

**内容中的路径（I15）：** 现有 peer 合同把文件索引表的 `path`/`location` 值当作授权内容原样返回。快照清单和回执中的 `commands` 也可能含这类值。这是已发布的现行行为，不是安全漏洞。

云端候选可以从两种处理中选：
- 默认不开放文件索引表，也不开放写入或含有它的命令与原回执；
- 为它们单独设计。

无论选哪种，都**不**改写已存的回执或摘要。

### 4.3 首片之外的操作

以下操作要分别论证：
- 撤销/重做：没有回执，见 I7；
- 归档：不走 CAS，见 I2；
- 快照的捕获与读取：涉及文件归属与内容，见 I8、I10、I15；
- 备份与恢复：需要 owner 权限，并轮换 generation；
- 运行与任务：有各自的身份，归 D2。

### 4.4 不确定结果的客户端规则

1. 写之前，先持久保存 `(project_id, database_generation, operation_id, expected_revision, commands)`。
2. 回复超时、断线，或拿到 `unavailable`/`internal_error`，或出现 `PeerOutcomeUncertain` 之类的标记时，记为 `unknown`，不自动重试。
3. 用原 ID 查询：
   - 得到回执：这就是原来的那次成功；
   - `not_found`：可以由人或调用方显式重复同一请求（同 ID、同修订、同命令）。返回冲突时不 rebase。
4. generation 已经变了，或授权已失效：停止，如实报告，不换 ID 重试。

## 5. 方案 A：同一 SQLite ProjectStore 置于本机或团队应用服务之后

**做法：**
- 每个项目数据库归一个服务进程所有。进程运行在作者本机（本机 Core）或团队服务器上，数据库放在该机本地盘。
- 应用服务调用现有 `ProjectStore` 及其子模块。
- 授权 lease 包住整个调用，沿用 `PeerAuthority.project_access` 的模式（`authority.py:494-554`）。

**可以复用的部分（只限存储层项目语义）：** I2–I8、I11、I12 的存储行为已有实现和测试：
- `tests/test_project_edit_operations.py`：
  - 丢回复、重开、撤销后的重放（第 78 行）；
  - 多连接与多进程（第 181、213 行）；
  - 提交前后进程退出（第 267 行）；
  - 热日志（第 561–656 行）。
- `tests/test_peer_projects.py`：scope、撤权、generation 与恢复（第 121–390 行）。

**必须新实现、新验证的部分：** 以下不能算作"复用"：
- 云端调用方认证与授权（R3）；
- 网络封闭响应与内容策略（I15）；
- 单一服务进程归属与重复打开检测（I14）；
- 在服务归属下的 generation 注册与轮换（I9）；
- 错误映射（I13）。

**职责：**
- 服务：持有授权 lease，负责项目注册与 generation，输出封闭的元数据 DTO。
- `ProjectStore`：负责 CAS、回执、journal 与有界读取。
- 运维：负责主机磁盘、备份文件与恢复流程。

**约束：**
- 一个数据库文件只由一个服务主机打开，不放网络盘。SQLite 官方提示，网络文件系统上的锁不可靠（<https://www.sqlite.org/useovernet.html>）；peer 规范第 149–150 行也有同样规定。
- 写入按项目串行（`BEGIN IMMEDIATE`），吞吐受单库限制。预览 128 MiB、回执 64 MiB 等上限保持不变。
- 高可用、多副本与跨区容灾不在此方案能力内，只能冷备份加 generation 轮换。
- 以下限制仍然存在：同 inode、未被观察到的带外回滚，以及授权注册表丢失（I9）。
- 文件资源与快照对象留在服务主机上。`external:*` 记录在团队服务器上无法解析，只能报不可用。

**改动面（估计）：** 新增应用服务门面、注册与授权（R3）、网络适配器；不改 `ProjectStore` 的格式与语义。

## 6. 方案 B：仓储端口与适配器

**做法：** 在应用服务与存储之间定义仓储端口。SQLite 是第一个适配；PostgreSQL 等团队数据库是后续适配。共同后端第 115–118 行已经提出这个方向。

**现状盘点（源码事实）：**
- 项目子模块不经过端口，直接通过 `store._connect()` 拿 SQLite 连接并写 SQL，例如 `edit_operations.py:151`、`171`，以及 `catalog.py`。
  - `suan/project/` 下共有 48 个 Python 模块，合计 14 307 行。
  - 其中 28 个文件含 `_connect(`：定义它的 `store.py`，加 27 个子模块。
  - 这只是直接调用的盘点，不是交付前必须全部改完的门槛。
- journal 依赖 SQLite rowid 保持原显示顺序（`journal.py:3-4`）。
- 热日志恢复、`application_id`、`user_version` 和在线备份都是 SQLite 机制（`store.py:294-461`、`568-608`）。

**渐进方式：**
- 可以按**操作族**逐步把实现移到端口之后。首个操作族可以是结构页、表页、`apply_once` 和 `get`，它们只触及 project、tables、fields、records、cells、changes、edit_journal 和回执表。
- 同一项目的所有操作族仍由**同一事实归属服务、同一存储事务边界**承载。
- 不允许把同一项目的不同操作族拆到不同存储，否则跨族事务与 CAS 无法成立。
- 未迁移的操作族在新存储上明确返回"不支持"。

**职责：**
- 端口：定义以下语义：
  - 事务边界与 CAS；
  - 回执插入与查询的原子性；
  - 有序 journal；
  - 有界分页；
  - 数值、单位、JSON 的精确保存。
- 每个适配器：逐条证明这些语义，不支持的操作明确拒绝（共同后端第 117 行）。
- 迁移：冻结旧写入入口，备份后离线对账，再显式切换事实归属（共同后端第 152–156 行）。

**约束：**
- 不能假定现有 SQL 换个驱动就能跑。
- 回执永久保留、generation 与恢复语义都要在新存储中重新设计。恢复旧库可能退回到旧的回执集合（规范第 177–182 行）。
- 本文**不**承诺 PostgreSQL 与 SQLite 等价。等价只能靠逐条一致性测试证明。

**改动面（估计）：** 抽出端口，按操作族迁移子模块，同时保证格式 1–15 可读。整体是大规模重构，需要分领域推进。

## 7. 比较

| 维度 | 方案 A：SQLite + 应用服务 | 方案 B：仓储端口 |
|---|---|---|
| 存储层项目语义 | 直接复用已验证的实现 | 端口之上的规则可以复用；存储语义要每个适配重新证明 |
| 授权、封闭响应、内容策略 | 需新实现、新验证 | 同左 |
| 单进程与 generation 归属 | 需新实现；注册表丢失、同 inode 回滚的限制仍在 | 需新实现；新存储的恢复语义另行设计 |
| UUID/修订/CAS | 现有实现 | 端口必须定义，并在每个适配上测试 |
| 永久 `apply_once` 回执、原请求身份 | 现有实现（同一事务） | 回执表要与业务行同一事务提交，每个适配都要测 |
| 撤销与不可变快照 | 现有 journal 与只追加清单 | 依赖 rowid 顺序，须重新设计；快照对象另需对象存储端口 |
| 备份与回滚 | SQLite 在线备份，加 generation 轮换 | 各存储的备份机制不同，回执集合的回退另行设计 |
| 文件/资产归属 | 留在服务主机 | 同样要求，另需对象存储与归属模型 |
| 非活跃恢复 | store 规则已有（只读 776 物理恢复）；服务是否允许这种恢复须决定并验证（F5b） | 每个适配都要证明打开、恢复时不执行任何工作 |
| 扩展与可用性 | 每项目单写；容灾靠冷备 | 可以借助团队数据库复制，但须重新验证 |
| 首次交付风险 | 低到中（新增授权与网络层） | 高（重构加逐个适配验证；可按操作族降低单次风险） |
| 与 Synthrix 存储的关系 | 不直接利用 | 有可能对接（Synthrix 有 memory/PostgreSQL 适配，共同后端第 100 行） |

## 8. 给 root 决定的选项与建议范围

### 8.1 R2 最小选项（不选择）

- **R2-a：** 采用方案 A；团队部署即单一归属的服务主机。
- **R2-b：** 采用方案 B；先抽端口，按操作族迁移，SQLite 适配保持现有语义；PostgreSQL 适配作为单独的后续片。
- **R2-c：** 先做 A，同时把 §4 的应用服务门面定为将来的端口边界，以后再决定是否走 B。门面不暴露 SQLite 细节。

### 8.2 R3 最小选项（不选择）

- **R3-a：维持现状。** 没有项目授权；云端不开放项目方法（即当前的 D1 声明）。
- **R3-b：按项目 grant 授给设备或调用方。** 沿用 `PeerAuthority` 模型：
  - grant 分 `project.read` 与 `project.edit`；
  - grant 绑定 generation；
  - 撤权与写入串行；
  - 回执 scope 绑定调用方。

  这需要为云端调用方身份新建注册表；**不能**把 Hub 的设备配对当作项目授权。
- **R3-c：用户账号加项目成员关系。** 设备从属于用户。需要账号映射、撤权传播，并与 Synthrix `authz` 迁移对账（共同后端第 97、127 行）。

**无论选哪项，职责划分都是：**
- 授权实现：认证、撤权，以及读历史回执前的授权核查（X5 ②③）；
- 应用服务：lease 覆盖整个调用；
- 运维：恢复时在服务归属下轮换 generation。

### 8.3 建议首片 CP-0（与 R2/R3 无关，由 root 决定是否派发）

**目标：** 把 §3 的不变量做成可重复执行的验收，按入口分组。只有能用同一调用、在两个入口上验收的行，才按同一矩阵比较。

**范围：**
- 只新增测试与说明；
- 复用现有方法与 schema，不新增已发布方法；
- 不改格式；不新增监听端口、服务或部署；不启动 peer 原生 helper，也不建立 `PeerEndpoint` 会话。

#### (a) 本机桥与 peer 共同验收

两个入口用同名方法、同一 store 和同一操作序列。

**比较字段：**
- `project.id`、`project.revision`；
- `total`、`offset`、`next_offset`；
- 表 ID、记录 ID 的顺序；
- 回执的 `operation_id`、`base_revision`、`applied_revision`、`request_sha256`、`commands`；
- `replayed`。

**错误的比较方式：** 各入口按自己已发布的错误映射比较。例如桥把 `RevisionConflict` 映射为 `conflict`、把 `ProjectError` 映射为 `invalid_params`（`projects.py:75-95`）。不要求两端异常类型相同。

**每条负对照的通用断言：** 调用前后 store 状态完全相同（参照 `tests/test_peer_projects.py` 的 `unchanged(store)`）。

| 行 | 内容 |
|---|---|
| F1 | **线上层：**<br>- 首次 `apply_once` 返回 `{receipt, replayed: false}`；<br>- 之后原 ID 的 `get` 在两个入口都返回 `{"receipt": <原回执>}`，没有 `replayed` 字段；<br>- 完全相同的请求再发一次，返回 `{receipt: <原回执>, replayed: true}`。<br>**比较对象：** 每个入口在自己的 scope 中核对首次写入、原 ID 查询与精确重放的 `receipt` 内容。`replayed` 仅出现在 apply 的结果中 |
| F2 | 同 ID 不同命令：冲突，原回执不变 |
| F3 | 同一修订上两个不同 ID：一个成功，另一个冲突 |
| F11b | 跨入口同一 UUID，两个独立的 scope：桥为 `local`，peer 为 `peer/1/…`。<br>- 第一个 scope 在修订 r 写入；<br>- 第二个 scope 用**当时的当前修订** r+1 写入，得到一个**不同**的新回执，`replayed=false`；<br>- 各自的 `get` 返回各自的回执 |
| F11c | 同一 scope、同一 UUID，修改原 CAS（另一个 `expected_revision`）后重放：冲突，状态与原回执不变 |
| F11d | 用一个从未用过的新 UUID、陈旧修订做首次写入：冲突，不插入回执，此后 `get` 为 `not_found` |
| F12 | 首页取得修订 r；外部写入使修订变为 r+1；用 r 读续页时，两个入口都冲突，不拼接。正对照：带 r 的续页在无写入时成功，`next_offset` 链在最后一页为 `null` |
| F13 | `limit=201`（结构页）、`limit=501`（表页）、带 offset 但没有 `expected_revision`、8 MiB 预算（用 monkeypatch 降低上限）：两个入口都拒绝，状态不变 |
| F14 | 项目级回执数量与字节预算（用 monkeypatch 缩小）由两个入口共用：新 UUID 在两个入口都被拒，状态与已存回执不变，原回执仍可读、可精确重放。原先列在 (b)，现在已有两入口的同一调用 |
| F15 | 格式 14 项目：两个入口都能读；`apply_once`/`get` 要求显式升级，读取时不隐式升级 |
| F23 | **路径内容现状对照：** 已授权读文件索引表时，两个入口都原样返回 `external:*` 的绝对路径值。这一行把现状记录下来，不当作漏洞修复，也不过滤 |

#### (b) 只在 store 或本机桥验收（没有两端的同一调用）

| 行 | 内容 |
|---|---|
| F4 | 提交前后进程退出 |
| F5a | 初次只读遇到精确的 776 时做物理恢复，不做业务编辑 |
| F6 | 撤销后重放：撤销只在桥/store 上进行，重放可在两个入口上观察 |
| F7 | undo/redo 回复丢失 |
| F8a | store 检测到数据库被替换 |
| F16 | 快照对象校验 |
| F17 | 解析 `external:*` |
| F18 | 便携工作区导入 |
| F19 | 中断的运行不重放 |
| F20 | 编辑已归档对象 |

#### (c) 只在 peer 验收

| 行 | 内容 |
|---|---|
| F5b | 已绑定的 owner 观察（`bound_project`）遇热日志时拒绝恢复，须单独构造热日志来测 |
| F5c | peer 项目方法在热日志下的现行行为：继承 store 恢复。先记录现状，是否保留由 root 决定 |
| F8b | 观察到替换后授权作废，要求 rebind |
| F9 | rebind 轮换 generation；观察到修订回退时拒绝 |
| F10 | 撤权与写入并发 |
| F11a | 另一个 scope 的调用方用同一 UUID 做 `get`，找不到第一个回执（`not_found`），也就无从重放它 |
| F21 | 重新认证后回执仍在 |

只读 grant 不能重放写入（`tests/test_peer_projects.py:193`），也归这一组。

#### (d) 只能在将来真实服务上验收

| 行 | 内容 |
|---|---|
| F3' | 跨部署并发 |
| F21' | 网络分区、换设备 |
| F22 | 两个服务实例 |
| — | 网络授权（R3）、迁移、不同存储（方案 B） |

**验收：**
- (a)(b)(c) 组在 source 与安装态各通过一次，零 skip；
- 每条关键边界有一个旧代码 RED 或负对照；
- 结果固定在提交 SHA 上；
- (d) 组不由 CP-0 签收。

**交付以后：** CP-0 只锁住已列语义的回归。R2/R3 的实现片拿 (a)(b)(c) 当回归基线，网络、授权、迁移、不同存储和跨部署并发由实现片自己验收。

### 8.4 已有证据的三个层级

**1. 已提交测试（仓库内）。** §9 中引用的 `tests/…` 行就是这一层，行号绑定设计基线 `397a464d`。root 在 source 和中性隔离安装态各运行了一次 `tests/test_peer_projects.py` 与 `tests/test_project_edit_operations.py`：
- source：106 passed，0 skipped，3.22 s；
- 隔离安装：106 passed，0 skipped，2.78 s，Python 3.12.14。

**1b. 提交 `994a3b1a5c330db953ef4bc610c60a0f9e58e44f`。** 此提交在本设计基线之后，新增了测试 `tests/test_peer_projects.py::test_bridge_and_peer_project_pages_and_scoped_receipts`，用两个入口验收：
- 严格的真实本机桥；
- 已认证的 `PeerProjects`，加按方法校验的 peer codec。

覆盖内容：
- 2 页结构页、3 页记录页；
- 陈旧的结构页续页和表页续页都被拒绝；
- 同一 UUID 在两个独立 scope 中各有一个原回执；
- 每个 scope 内的精确重放。

root 记录的结果，均为 0 skipped：
- source 相关套件 143 passed；
- 隔离安装的核心套件 107 passed。

因此，F1/F11b 的跨入口情形和 F12 的两入口一致性，已有已提交测试（在 `994a3b1a`，不在本设计基线中）。

**1c. 之后的已提交测试（均在 [`tests/test_peer_projects.py`](../../tests/test_peer_projects.py)，按本分支历史中的集成提交列出）。** 入口都是同进程的严格本机桥（`InProcessBridge`，经 `Bridge.handle_line` 分发）和/或已认证的 `PeerProjects` 适配器；只有 F23 另外经过按方法校验的 peer codec。都不建立活的 `PeerEndpoint` 会话，也不经过原生 helper 通道。

| 行 | 测试 | 提交 | 验收内容 |
|---|---|---|---|
| F5b | `test_current_bound_owner_observation_refuses_a_physical_hot_journal_without_any_write`（`first_owner_observation`、`cached_owner_store` 两例） | `a4a07a41` | 用 [`tests/test_project_edit_operations.py`](../../tests/test_project_edit_operations.py) 的 `_spill` 子进程造出真实热回滚日志（不模拟错误码）。`bound_project` 拒绝，且异常链指向 "explicit local recovery"。数据库、热日志与授权库的字节都不变，grant 仍有效 |
| F5c | `test_current_peer_catalog_physically_recovers_the_preimage_without_a_receipt` | `a4a07a41` | 同样的热日志下，已认证的 `PeerProjects.catalog` 恢复到前像，返回修订 0、无表。被杀操作在任何 scope 都没有回执 |
| F23 | `test_current_authorized_file_index_content_is_identical_on_bridge_and_peer_until_revoked` | `bd49fd40` | 用现有文件索引 API 登记项目外的合成文件。桥、`PeerProjects` 和 peer codec 原样返回同一行的路径与平台位置值，元数据保持封闭。撤销 grant 后 peer 读取被拒 |
| F3、F11d | `test_bridge_and_peer_race_two_identities_at_one_revision_with_one_winner_and_no_loser_receipt` | `b8e42c66` | 两个入口各用新 UUID，在修订 0 竞争：恰一成功，修订只加一，败方为 `conflict` 且无回执。同一项目上，两入口用陈旧修订做首次写入都冲突（F11d） |
| F13 | `test_shared_paging_and_serialized_response_budgets_are_not_relaxed`（扩展到桥） | `b8e42c66` | 桥对同样的越界读取返回 `invalid_params`。`limit` 越界由桥的已发布 schema 在分发前拒绝；续页缺修订和 8 MiB 预算在共享 store 中拒绝 |
| F15 | `test_legacy_project_reads_remain_supported_without_implicit_format_upgrade`（扩展到桥） | `b8e42c66` | 格式 14 项目桥可读；回执接口在桥上返回 `unsupported`，不隐式升级 |
| F14 | `test_bridge_and_peer_share_the_project_receipt_quota_without_evicting_original_receipts`（`count`、`bytes_exhausted_before_write`、`bytes_exceeded_by_new_edit` 三例） | `5c4723f4` | 测试内用 monkeypatch 缩小预算。数量已满和字节已耗尽均在编辑前拒绝，新事务越过字节上限时回滚已执行的编辑。两入口各自的错误映射都成立，状态与已存回执字节不变，原回执可读、可精确重放 |

**F3 竞争的边界：** 不持锁时，采样中总是桥抢先。因此测试先持有 SQLite 写锁，直到观察到两个调用都到达 `ProjectStore._connect(write=True)` 才释放。这一观察只证明两个调用到了写入口，不证明它们已在 SQLite 中等待。赢家由 SQLite 决定，断言不依赖赢家是谁。

**root 记录的运行（仓库外证据）：**
- `root-delivery-20261109-53/closure.json`：
  - 集成 `b8e42c66` 时，root 在 source 模式下对五个相关测试文件（含整份 `tests/test_peer_projects.py`）联跑，显式使用已安装的 Linux peer helper，246 passed，0 skipped；
  - 竞争测试固定文件重复 30 次全过，peer 赢 27、桥赢 3（采样，不是保证的分布）；
  - 隔离导出中三项改动各使对应测试失败（`claude-red.json`）：
    - 去掉 CAS（F3 竞争测试）；
    - 关闭读取结果的字节预算（F13）；
    - 改错旧格式的桥错误映射（F15）。
- `root-delivery-20261109-54/closure.json`：
  - 集成 `5c4723f4` 时，同样的已安装 helper 联跑 249 passed，0 skipped；
  - 三项故障注入（scope、写后预算、重放顺序）各使对应用例失败（`claude-red.json`）。

已安装 helper 只服务于该联跑中 `tests/test_desktop_bridge_peer.py` 的 helper 验收用例。它不把上表各行变成活 peer 或线上证据。

**1d. F14 真实通道及 Linux 隔离安装复验。** `1e7bebf2` 新增 [`tests/test_peer_endpoint.py`](../../tests/test_peer_endpoint.py) 的 `test_real_peer_and_bridge_share_receipt_byte_limit_on_the_same_project`。本机桥和经已安装 helper 建立的 WebRTC `PeerEndpoint` 操作同一 SQLite 库，分别在缩小的写后回执字节预算下得到 `invalid_params`。失败 ID 查回执均为 `not_found`，已有 scope 的回执仍能精确读取及重放。root 的源码联跑 182 项全过，隔离 wheel 单跑通过。把 peer 的该处错误映射改成 `conflict` 后，定向测试在原预期处失败。证据见 `root-delivery-20261109-55/closure.json`。

root 隔离安装复验使用 `49837655` 构建的 wheel，以及 `74ee8b4e` 导出的 `test_peer_projects.py`、`test_project_edit_operations.py` 和上述一个 F14 用例。主进程及热日志子进程均验证从 wheel 安装目录导入。Python 3.11.16 / SQLite 3.53.1、Python 3.12.14 / SQLite 3.53.1、Python 3.14.4 / SQLite 3.46.1 各通过同一组 116 项，零跳过。1b、1c 在这里仍按各自入口验收，真实通道覆盖限于 F14 写后溢出。证据见 `root-delivery-20261109-56/installed-cp0-matrix.json`。

**2. root 外部探针（仓库外，未提交）。** 证据记录在 `root-delivery-20261109-43/closure.json` 的 `cp0` 节：
- 两个脚本：`cp0-parity-probe.py`（sha256 `23de877c…`）和 `cp0-hot-journal-probe.py`（sha256 `1d951c7c…`）；
- 用合成项目，在 source 和同一份 Python 源码的中性隔离安装中运行；
- 入口是真实的本机桥 NDJSON，以及已认证的 `PeerProjects` 加按方法校验的 peer codec。

观察到：
- 两个入口的三页结构页、三页表页完全一致；陈旧续页被拒绝（F12）。
- 原 ID 的查找与重放按 scope 进行。桥的 `local` scope 和 peer scope 用同一 UUID、在各自应在的修订上，各产生自己的回执（F1、F11b）。
- 一个合成的、已授权的 `external:posix` 文件索引单元格，原样出现在两个入口的响应中，也通过了 peer codec（F23）。
- 构造真实的热回滚日志后：
  - `bound_project` 拒绝恢复，数据库与日志字节都不变（F5b）；
  - `PeerProjects.catalog` 恢复到前像，返回修订 0，没有未提交的回执（F5c）。

这些探针**没有**覆盖：
- 活的 `PeerEndpoint`、原生 helper 通道、远端监听；
- 云服务；
- 任何 R2/R3 验证。

这些探针仍是有效的历史观察。F23 与 F5b/F5c 现在另有 1c 中的已提交测试，探针不再是这几行的唯一证据。

**3. 仍待验证。**
- **活 peer：** 1d 的 F14 写后溢出之外，CP-0 各行经 `PeerEndpoint` 与原生 helper 的线上行为，包括适用的错误码映射。
- **平台：** Windows、macOS 上这些行的复验。
- **F5b/F5c/F23 的旧代码反例：** 已找到的 RED 证据只覆盖 F3、F13、F15、F14。
- **F14 的真实上限：** 按真实的 10000 条与 64 MiB 实际写满。现有测试只缩小预算。
- **F5c：** 保留现行恢复行为还是改为拒绝，仍由 root 决定。
- **第 (d) 组：** 跨部署并发（F3′）、网络分区与换设备（F21′）、两个服务实例（F22）；以及云服务、R2/R3。

## 9. 故障验收矩阵

- "本地"指现有 `ProjectStore` 加本机桥或 peer 原型的行为；"云端"指将来服务必须满足的要求。云端一律**未实现**。
- "组"对应 §8.3：a 为两入口共同验收，b 为只在 store/桥，c 为只在 peer，d 为只能在将来服务上。

| # | 组 | 故障/场景 | 本地现有行为（证据） | 云端要求 | 缺失资产 |
|---|---|---|---|---|---|
| F1 | a | 提交后回复丢失 | 不同层返回不同形状：<br>- 原 ID 显式 `get`：内部 `EditOperations.get` 与 `PeerProjects.get` 返回裸回执；线上的桥与 `PeerEndpoint` 返回 `{"receipt": <原回执>}`（`edit_operations.py:148-156`；`desktop_bridge/projects.py:185-186`；`endpoint.py:516-517`）；<br>- 完全相同的请求再发一次：返回 `{receipt, replayed: true}`，不再执行（`edit_operations.py:173-177`）。<br>测试：`test_project_edit_operations.py:78`、`213`；`test_peer_projects.py:121`。两入口在各自 scope 中的精确重放，见 §8.4 | 同左。不确定结果记为 `unknown`，不自动重试（§4.4） | 网络适配器；客户端的持久请求记录 |
| F2 | a | 同 ID、不同命令 | `RevisionConflict`，不 rebase，状态不变（`edit_operations.py:175-176`；`test_project_edit_operations.py:103`；`test_peer_projects.py:143-145` 中的不同命令一例）。修改原 CAS 的情况见 F11c | 固定的 `conflict` 码，原回执不变 | 错误映射测试 |
| F3 | a | 同一修订上两个不同操作 | 一个成功，一个冲突（`test_project_edit_operations.py:196`）。两入口竞争见 `test_bridge_and_peer_race_two_identities_at_one_revision_with_one_winner_and_no_loser_receipt`（`b8e42c66`，同进程；测试持写锁至两调用到达写入口，见 §8.4 1c） | 跨部署同样只能成功一个（X8，见 F3'） | 两实例共同归属规则（I14） |
| F3' | d | 跨部署并发写同一项目 | 本地没有对应场景 | 只有事实归属服务接受写入 | 归属与转发实现 |
| F4 | b | 进程在提交前后退出 | 不留下部分成功；提交后的回执仍可读（`test_project_edit_operations.py:267`、`573`） | 服务崩溃后重启，结果同左 | 服务级崩溃测试 |
| F5a | b | 初次只读遇到精确 776 | 一次物理回滚，不做业务编辑（`store.py:391-461`；`test_project_edit_operations.py:561-656`） | 是否允许服务做这种恢复，须决定 | 服务恢复策略 |
| F5b | c | owner 观察已绑定项目时遇热日志 | `_BoundProjectStore` 拒绝，要求显式本地恢复（`authority.py:54-57`、`405-441`）。root 外部探针在真实热回滚日志上观察到拒绝，数据库与日志字节都不变（§8.4 2）。已提交测试 `test_current_bound_owner_observation_refuses_a_physical_hot_journal_without_any_write`（`a4a07a41`，首次观察与缓存 store 两例）：数据库、日志与授权库字节不变，grant 仍有效（§8.4 1c） | 同左 | 服务级恢复流程；安装态与非 Linux 复验 |
| F5c | c | peer 项目方法遇热日志 | 经 `_local_project` 用普通 `ProjectStore`，继承 776 恢复（`authority.py:377-386`、`518`）。root 外部探针观察到：`PeerProjects.catalog` 恢复到前像，返回修订 0，没有未提交的回执（§8.4 2）。已提交测试 `test_current_peer_catalog_physically_recovers_the_preimage_without_a_receipt`（`a4a07a41`）固定这一现行行为，被杀操作在任何 scope 都没有回执（§8.4 1c） | 由 root 决定保留，或改为拒绝 | 决定 |
| F6 | b | 撤销后重放旧回执 | 返回原回执，不再执行，也不恢复效果（`test_project_edit_operations.py:78`） | 同左；回执注明是历史观察 | DTO 说明 |
| F7 | b | undo/redo 回复丢失 | 没有回执。用同一 `expected_revision` 重试时，如果第一次已提交，会因修订冲突失败（`store.py:747-752`） | 首片不开放；如要开放，先设计回执或观察规则 | 设计决定 |
| F8a | b | 数据库文件被替换（store） | 打开后 ID 变化即报错（`store.py:386-389`）；旧 store 的操作访问不被继承（`test_project_edit_operations.py:485`） | 同左 | 服务注册表实现 |
| F8b | c | 数据库文件被替换（peer） | 授权作废，要求 rebind（`authority.py:515-526`） | 同左 | 服务注册表实现 |
| F9 | c | 恢复旧备份 | 显式 rebind 轮换 generation（`test_peer_projects.py:260`）；观察到修订回退即拒绝（`authority.py:519-526`）；同 inode、未观察到的带外恢复和注册表丢失都无法证明安全（`authority.py:8-11`） | 恢复在服务归属下进行，并轮换 generation；不宣称全局恰好一次 | 恢复运维手册与测试 |
| F10 | c | 撤权与写入并发 | 撤权确认要等已接受的调用完成（`test_peer_projects.py:294`）；撤权后会话被拒（第 209 行） | 同左 | R3 实现 |
| F11a | c | 另一个 scope 的 `get` 查第一个回执 | 第二个调用方用同一 UUID 做 `get`，得到 `OperationNotFound`，找不到第一个回执（`test_peer_projects.py:185-186`） | 同左。Hub action 的同类缺口（X5 ②）不能照搬 | R3 实现 |
| F11b | a | 两个独立 scope 用同一 UUID 先后写入 | 第一个 scope 在修订 r 写入；第二个 scope 用当时的当前修订 r+1 写入，得到 `replayed=false` 的另一个新回执。两个回执的 scope 不同，各自 `get` 返回各自的回执（`test_peer_projects.py:187-190`）。主键是 `(scope, operation_id)`。桥 `local` 与 peer scope 的跨入口情形，由 `994a3b1a` 的已提交测试覆盖（§8.4 1b） | 同左；scope 由服务推导 | 云端服务上的同一验收 |
| F11c | a | 同一 scope、同一 UUID，重放时修改了原 CAS | 冲突，状态与原回执都不变（`test_peer_projects.py:143-145` 中 `(None, 1)` 一例，第 151 行断言） | 同左 | 无 |
| F11d | a | 新 UUID、陈旧修订的首次写入 | 冲突，不插入回执，之后 `get` 为 `not_found`（`test_peer_projects.py:146-151`）。同一项目上的两入口情形（桥 `conflict`、peer `RevisionConflict`）见 `b8e42c66` 的竞争测试（§8.4 1c） | 同左 | 无 |
| F12 | a | 翻页途中项目被修改 | 续页因修订冲突而失败（`catalog.py:20-25`、`52-53`；`test_peer_projects.py:114-118`）。两入口一致性，以及结构页、表页的陈旧续页被拒，由 `994a3b1a` 的已提交测试覆盖（2 页结构页、3 页记录页，§8.4 1b）；root 的外部探针另有观察（§8.4 2） | 同左，不拼接不同修订的页 | 云端服务上的同一验收 |
| F13 | a | 页过大，或参数越界 | 超过页数上限、缺少续页修订、超过 8 MiB 都拒绝，状态不变（`catalog.py:14-31`；`test_peer_projects.py:355-372`）。`b8e42c66` 将 `test_shared_paging_and_serialized_response_budgets_are_not_relaxed` 扩展到桥：均为 `invalid_params`，其中 `limit` 越界由桥的已发布 schema 在分发前拒绝（§8.4 1c） | 同左；网络层不放宽 | 网络帧上限 |
| F14 | a | 回执容量耗尽 | 两入口共用项目级配额。数量已满或字节已耗尽时在写前拒绝，新增回执越过字节上限时回滚。适配器用例固定桥 `invalid_params` 和 peer `ProjectError`（§8.4 1c）。写后溢出另有同库真实线路用例，两端均返回 `invalid_params`，并可读取及精确重放各自的旧回执（§8.4 1d） | 同左，并报警；不做 GC | 监控；真实上限下的验证；其余配额情形的真实线路验证 |
| F15 | a | 旧格式项目 | 1–14 可读；新 API 要求显式升级（`test_project_edit_operations.py:427`；`test_peer_projects.py:390`）。`b8e42c66` 将该测试扩展到桥：格式 14 可读，回执接口返回 `unsupported`，不隐式升级（§8.4 1c） | 服务不隐式升级 | 升级审批流程 |
| F16 | b | 快照对象缺失或损坏 | `resolve` 时校验失败，拒绝（`snapshots.py:103-123`、`333-341`） | 结果元数据中不带本机对象路径。清单中的路径值属于内容（I15），默认不开放快照，或单独设计 | 对象存储归属 |
| F17 | b | `external:*` 文件不在服务主机 | 只有原机能解析（`files.py:82-95`） | 报不可用，不改写成别的路径 | 文件归属模型 |
| F18 | b | 便携工作区导入另一台机器 | 保留项目身份与回执，但不授予访问（规范第 177–182 行） | 新主机须在服务归属下重新注册，产生新 generation | 注册流程 |
| F19 | b | 服务重启时有运行中的分析或工作流 | 记为 `unknown`/`interrupted`，不重放（`analysis_runs.py:533-544`；`workflow_runs.py:687-700`） | 同左；打开、恢复都不派发（I11） | 服务装配测试 |
| F20 | b | 编辑已归档对象 | 返回 `conflict`（`projects.py:78-79`） | 同左 | 无 |
| F21 | c | 断开后重新认证 | 回执仍在（`test_peer_projects.py:249`）；`PeerCallUncertain` 保留原 ID 和修订（peer 规范第 250–259 行） | 满足 §4.4，调用方身份稳定（I4） | — |
| F21' | d | 网络分区，或客户端换设备重连 | 本地没有对应场景 | 同 F21，加真实网络验证 | 网络适配器、R3、真实网络测试 |
| F22 | d | 两个服务实例打开同一个库 | 本地没有对应场景。每个状态目录只有一个桥（`bridge.lock`，stk-desktop-bridge-v1 第 52–53 行），但外部 CLI 写入者仍可同时写，靠 SQLite 修订仲裁（`projects.py:1-4`） | 禁止；必须有单一归属，并检测重复打开（I14） | 归属锁设计 |
| F23 | a | 授权读取含路径的用户内容 | peer 与桥都原样返回文件索引的 `path`/`location` 值。peer codec 只封闭元数据，不过滤单元格内容（`protocol.py:282-300`；peer 规范第 121–141 行）；桥直接返回 store 的结果（`projects.py:173-175`）。root 外部探针：合成的 `external:posix` 单元格原样出现在两个入口的响应中，也通过了 peer codec（§8.4 2）。已提交测试 `test_current_authorized_file_index_content_is_identical_on_bridge_and_peer_until_revoked`（`bd49fd40`）在桥、`PeerProjects` 与 peer codec 上固定这一现状，撤销 grant 后 peer 读取被拒（§8.4 1c） | 默认不开放文件索引表、写入它的命令及其原回执，或单独设计。负对照：网络适配器默认不返回这些值，也不改写任何已存的回执或摘要 | 内容策略设计与测试 |

## 10. 缺失资产清单

1. 云端项目应用服务与网络适配器：没有（G1-5）。
2. 调用方注册表、账号映射、按项目或用户的授权：没有（X5、R3）。
3. 方案 B 的仓储端口与 PostgreSQL 适配：没有。
4. 服务级的项目归属锁、重复打开检测、恢复运维流程：没有。
5. 网络候选的内容策略（文件索引、含路径的命令与回执、快照清单）及其负对照：没有（F23）。
6. CP-0 已提交的同进程测试涵盖 F1/F11b、F12、F5b/F5c、F23、F3/F11d、F13、F15、F14（§8.4 1b、1c）。Linux 隔离 wheel 已复验这些测试，以及 F14 的真实通道写后溢出（§8.4 1d）。仍待验证：
   - F14 写后溢出之外，经活 `PeerEndpoint` 与原生 helper 的线上行为；
   - Windows、macOS 复验；
   - F5b/F5c/F23 的旧代码反例；
   - F14 在真实上限下的验证（§8.4 3）。
7. 快照对象与项目文件的远端归属与传输模型：没有。peer 文件扩展是另一份契约，不授予项目权限（stk-peer-files-1 第 1–13 行）。
8. 网络 DTO 与已发布 schema：没有，本文也不定义。
9. 真实部署、跨主机、网络分区、目标 OS 的验收证据：没有。

## 11. 不在范围

- 选择 R2 或 R3。
- 任何实现，以及对方法、schema、认证、授权、网络策略的改动。
- 启动服务、部署、安装，以及计费请求或模型请求。
- Synthrix 对话与科研领域迁移（D3）。
- 运行与任务的跨端链（D2）。
- PostgreSQL 等价性，以及科学有效性。
- 把本机两进程测试当作云端验收。
