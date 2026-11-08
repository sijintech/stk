# Hub CLI 输入上传与传输恢复

状态：**已由 root 审阅并选择集成 CL-D1-HUB-UPLOAD-CLI-18 第四版实现**。记录日期：2026-11-08 UTC。源码与最小安装态验证见文末；目标平台 CI 仍须按实际提交核对。本文不定义新 schema，也不改变 hub 协议、授权、review 策略、模型或网络策略。

## 源码依据

- **CLI、连接、hub 与上传会话：** `claude/support` 的 `8ae2088d56a7ac1ab5ca25e3e99e42ad3317209e`
  （`suan/runtime/cli.py`、`suan/desktop_bridge/connections.py`、`backends.py`、`suan/control/app.py`、
  `suan/control/uploads.py`）。
- **`TransferManager` 与桥（当前）：** root 的 `612e`。root 告知，Bridge 生命周期已在 `7bfae902` 中修复；当前
  `transfers.py` 的 sha256 为 `5311155aac6cfaed9e142ddb75ba7c258d2b238734c29662dbd8f00ed5a05028`，`server.py` 为
  `684db28f3043c8513f10b5309086fc8f1ceb027271067621fca771c36bcd3d20`。这些由 root 提供，**不是**本人重新读取
  这份源码得到的结论；实施前须按当前源码复核下文所引的位置。
- **历史依据：** 下文的 `transfers.py:N` / `server.py:N` 行号来自 `7bfa` 修复之前（`bcec`）的只读快照（sha256
  `2a0e7179…` / `9b843ee8…`）。其中关于桥在 `stop` 之后立即释放 `bridge.lock` 的描述**只是历史**，不代表当前
  行为。`8ae2088d` 中的这两个文件更旧，缺少 `_record_backend`、`connection_identity` 和 workflow 上下文传递。

## 目标与边界

为已配对、并由所有者签发 `desktop` 配置的 CLI 客户端提供三件事：输入上传、观察原传输、显式恢复。

- 复用 `TransferManager` 及其 hub 上传协议，不复制上传状态机。
- 上传字节与 `workspace.import` 人工复核分开：CLI 只负责上传和观察，没有批准入口。
- hub 既有的 `review_policy`（`any` / `not-self` / `owner`）保持不变；CLI 不要求修改配置，也不每次运行都提示。
- 普通客户端不能自行获得上传额度，CLI 也不会重新配对。
- 不扩展到 R2/R3，不替用户选择科研参数。桥的生命周期由 root 负责，不在本片范围内。
- **首片选择：**
  - 内容门只用 B（严格的 manifest backend 守卫），不做私有冻结副本；
  - 实现放在新的私有模块 `suan/runtime/hub_transfers.py`，`cli.py` 只加惰性的薄入口；
  - `--wait` 默认 600 s，worker 停止宽限为 45 s；
  - 不提供 `--wait-review`。
- 方案形成时的历史状态：`workspaces --hub ... upload` 在检查文件之前即被拒绝（旧 `suan/runtime/cli.py:520`）。第四版实现已接入下述上传入口；直连 / SSH 的上传和 `jobs` 保持不变。

## 已核实的现有行为

| 事实 | 位置 | 对本设计的意义 |
|---|---|---|
| hub 只接受 `role=client` 且 `profile=desktop` 的设备上传，否则返回 403 | `suan/control/app.py:177-182` | 额度只能来自所有者签发的 `--profile desktop` 配对码 |
| CLI 配对时如实保存 hub 返回的 `profile` 和 `device_id` | `connections.py:168-180`；`tests/test_runtime_hub_cli.py` 的 `paired` 断言 `profile == ""` | 可在本地读取 `profile` 和 `device_id`，hub 仍会再次检查 |
| `TransferManager.__init__` 会创建目录并执行 `_recover`：把 `queued`/`running` 改写为 `interrupted`，删除 7 天前的终态 journal | 历史 `transfers.py:107-121` | **构造即写入**，必须在命名空间租约之内构造；只读路径不能构造它 |
| 每个传输的 `instance_lock(<id>.lock)` 只在运行期间持有 | 历史 `transfers.py:375` 起；`suan/runtime/common.py:86-101` | 它不保护其他进程的 `_recover` 和 GC |
| 新传输记录 `connection_identity = backend.server_key`（url 与 node 的哈希）；运行和取消都经 `_record_backend` 校验，端点改变即 `conflict` | 历史 `transfers.py:101-105`、`:164`、`:325`、`:334`、`:420` | **端点守卫已经存在** |
| 缺口：`connection_identity` 不包含已配对设备的 `device_id` 和 `profile`；`_existing`（同键返回原传输）不经过 `_record_backend` | 历史 `transfers.py:149-159` | 设备或配置的绑定必须由 CLI 侧记补上 |
| 同键同请求返回原传输，同键不同请求返回 `conflict` | 历史 `transfers.py:144-159`；`tests/test_desktop_transfer_lifecycle.py:17-106` | 原键与原始 request 的身份可直接复用 |
| journal 在 `upload_begin` 后保存会话 ID；**每个分块的确认不保存**；恢复时以 hub 返回的偏移为准 | 历史 `transfers.py:463-480` | 「hub 已收、journal 未记」是正常状态；已由 `upload_restart.py` 实测（真实桥被 SIGKILL 后，从 1 MiB 起在同一会话续传） |
| 源文件的大小或 mtime 改变时，会重新计算哈希，并在**同一个键**下开启新的上传版本；大小和 mtime 不变时不重新计算 | 历史 `transfers.py:457-462` | 现有逻辑不保证内容身份，需要 B 守卫 |
| hub 在 `finish` 时按声明的 sha256 校验已收字节；不符则 `checksum_mismatch` 并中止会话 | 历史 `transfers.py:482` 起 | hub 端的底线 |
| 导入的 action ID 为 `action_id("workspace.import", node, transfer_id, attempt)`；导入在复核中会无限期轮询；被拒绝或失败后 journal 的 `import_attempt+1` | 历史 `transfers.py:507-545` | 被拒绝之后，journal 中的 `attempt` 指向的是**尚未发出**的下一个 action，不能用来推导「原 action」 |
| 取消会撤回复核中的导入并中止上传会话，两者都经端点守卫，**不读取源文件** | 历史 `transfers.py:321-345` | 有效侧记下的取消不依赖源文件 |
| 默认 `review_policy=any`：任何客户端都可以批准，撤回总是允许 | `app.py:352-365` | 维持现状；CLI 不提供批准入口 |
| `jobs download` 每条命令使用临时 journal | `suan/runtime/cli.py:155-173` | 上传不能沿用：每条命令换新 journal 就会从 0 重传、换会话 |

可直接复用：`TransferManager` 的状态机（启动、键语义、端点守卫、续传、导入、取消、恢复），`HubBackend` 的上传与
导入调用，`ConnectionStore`，`instance_lock` 使用的锁原语，以及 `HubCLIClient` 的目标选择和读取用的有界等待。

必须新增：`suan/runtime/hub_transfers.py`（worker、侧记、内容清单、backend 守卫、只读查看）和 `cli.py` 的薄入口。
除 `cli.py` 薄入口外，不修改共用 `TransferManager`、后端或 Hub 协议。

## 命令

挂在 `suan workspaces` 下，无需改动入口：

```text
suan workspaces --hub H --node N upload WORKSPACE_ID SOURCE [--path REMOTE] --key KEY [--wait SECONDS]
suan workspaces --hub-state-dir DIR transfers list
suan workspaces --hub-state-dir DIR transfers show TRANSFER_ID
suan workspaces --hub H --node N transfers show TRANSFER_ID --check
suan workspaces --hub H --node N transfers resume TRANSFER_ID [--wait SECONDS]
suan workspaces --hub H --node N transfers cancel TRANSFER_ID
```

`cli.py` 只解析参数，并在命令执行时才导入 `suan.runtime.hub_transfers`，以保持现有的轻量导入测试。

- **`upload`：** hub 模式必须提供 `--key`，不自动生成。父进程做纯检查（参数、本地连接的 `profile == "desktop"`），
  在 stderr 打印原键、传输 ID 以及导入 action ID 的推导方式，然后启动 worker。父进程**不**计算哈希，也不写入
  任何文件。
- **`transfers list|show`：** 只读本地文件，见「只读路径」。
- **`transfers show --check`：** 在只读结果之外，查询侧记中记录的**最后一次实际派发的导入意图**（见「原导入意图」）。
  - 只查询这一个 action；kind 必须是 `workspace.import`，所选节点必须一致，payload 的请求 sha256 必须与意图记录
    相同；只读取，不派发。
  - 不从 journal 的 `import_attempt` 推导 action ID。
  - `workspaces action` 仍只接受 `workspace.create`。
- **`transfers resume`：** 唯一的恢复入口。重开 CLI 不会自动恢复任何传输：worker 不调用 `resume_interrupted`。
- **`transfers cancel`：** 显式取消，只在侧记有效时执行（见「身份与侧记」）。超时、Ctrl-C 和进程中断都不会取消。

### 输出与退出码

每个结果都带 `observed_at`（UTC）和 `observed_from`（`worker_receipt`、`journal` 或 `hub`）。

| `outcome` | 依据 | 退出码 |
|---|---|---|
| `completed` | worker 收据：journal 为 `completed`，且导入 action 为 `succeeded` | 0 |
| `pending_review` | 在 `observed_at` 时，worker 观察到字节已传完、导入 action 处于 `review`。这只是当时的观察：退出前或退出后都可能已被别人批准，CLI 不声称工作区此时仍为空 | 0 |
| `interrupted` | 本地停止（`--wait` 到期、Ctrl-C、worker 有界停止）：没有取消，远端会话保留其偏移 | 1 |
| `unknown` | 传输层不确定：`unavailable`、`timeout`、连接中断、worker 被强制结束或停止超时，hub 可能已收下请求或分块的确认。journal 中本地记的 `failed` 若出于这类原因，**不当作远端终态**。输出原传输 ID 和原导入意图，不换键，也不自动重发 | 1 |
| `failed` / `rejected` / `cancelled` | 依据明确错误或原回执：Hub action/校验结果、明确的本地内容守卫拒绝，或本命令显式取消；本地拒绝不称远端终态 | 1 |
| `busy` | 命名空间租约被另一个 worker 持有；本命令没有改动任何 journal 或侧记的字节 | 3 |
| 拒绝 | 非 desktop、侧记缺失或不一致、内容改变、设备或端点漂移 | 2 |

## 命名空间、租约与写入顺序

### 位置

| 用途 | 路径 |
|---|---|
| 命名空间根目录 | `<hub-state-dir>/cli/` |
| 租约锁文件 | `<hub-state-dir>/cli/namespace.lock` |
| `TransferManager` 的 journal 根目录 | `<hub-state-dir>/cli/transfers/` |
| 侧记 | `<hub-state-dir>/cli/transfers/<id>.cli.json`，0600 |

CLI 命名空间与桥的 `<state_dir>/transfers/` 分开。即使 `--hub-state-dir` 指向桥的目录，CLI 也只读取其中的
`hubs.json`。`*.cli.json` 也匹配 `*.json`：`_recover` 按顶层 `state` 判断，`list` 按顶层 `id` 判断。
侧记统一使用 `transfer_id`，禁止顶层 `id` 和 `state`，才会被两者忽略；须用真实 Manager 验证。

### worker 内的写入顺序

所有持久写入和身份决定都在 worker 取得租约之后进行：

1. 在 `namespace.lock` 上取得非阻塞独占锁；失败就报告 `busy` 并退出，**不读写**任何 journal 或侧记。
2. 在租约内重新核对：
   - 当前 `hubs.json` 的 `profile == "desktop"`；
   - 设备 `device_id` 与端点 `server_key`；
   - 原键对应的传输 ID 与原始 request（逐字节相同的 key 与 request，不做规范化）；
   - 完整内容清单（见「内容门」）。
3. 先只读记录已超过既有保留期的终态 journal，再构造 `TransferManager`，让 `_recover` 和 GC 在租约内完成。
   只清理这些已证明退役且确实被 GC 删除的 journal 对应侧记，不按“没有 journal”删除侧记：它可能是尚未建立
   journal 的准备意图，或崩溃后未确认的原意图。`resume/cancel` 的目标若已退役，明确拒绝，不派发。
4. GC 完成后重新核对身份，再处理侧记；**新侧记只在 GC 之后创建**，避免被本次清理误删。
   - 不存在且确实是新的 `upload`：原子创建（写临时文件后无覆盖发布）；
   - 已存在：必须与第 2 步的原身份和内容完全一致，否则以 2 拒绝；
   - 从不覆写未退役侧记的身份字段；只有最后导入意图节可在同一租约内原子更新。
5. 侧记完整发布后才调用 `start_upload/resume/cancel`。侧记已发布但 journal 尚未建立时崩溃，重开仍核原 key、
   request 和内容；不得把这类侧记当垃圾清除后接受另一份请求。

父进程与 `busy` 的 worker 都不会改变现存 journal 或侧记的字节。

### 租约持有到进程真正退出

- worker 直接打开锁文件并加锁，不用 `with instance_lock(...)` 这样会在退出块时解锁的上下文管理器；任何 `finally`
  都不在仍有传输线程存活时关闭锁文件。
- 结束时，worker 依次：
  1. 调用 `TransferManager.stop(timeout=45)`；
  2. 在租约内读取并校验原 journal 和侧记，形成**最后的完整绑定快照**；
  3. 把它写入 IPC（stdout）并 flush；
  4. 调用 `os._exit(code)`。

  锁随进程退出由操作系统释放。即使 `stop` 超时仍有线程存活，也不会在进程结束之前解锁。
- 只有这个**私有子进程**会调用 `os._exit`；父进程绝不调用，因此 CLI 嵌在 `CliRunner` 或其他 Python 进程中运行时，
  宿主不受影响。
- 父进程的超期处理：发送 `stop`；超过 45 s 加余量仍未退出，则先 SIGTERM，再 SIGKILL，每一步都等待并回收（reap）。
  被强制结束时没有 worker 收据，`outcome` 为 `unknown`。

### 收据与后续观察

- **原命令的收据**只有两部分：worker 在持租约时发出的最后完整绑定快照，以及父进程回收 worker 的事实（退出码、
  信号、耗时）。
- 父进程在回收之后再读本地文件，只作参考。如果读到的与收据不同（例如下一个 worker 已经取得租约并修改），就标记为
  `subsequent_observation`，不冒充原命令的收据。

### 与桥并存

CLI 与桥的命名空间不同，互不改写对方的 journal。但同一设备在两处以相同的 `digest` 和 `size` 上传，会落到 hub 上同一个
上传会话（`suan/control/uploads.py:236`）。hub 的偏移检查（409）可以防止交错写入，但两边会互相看到对方的进度。文档中
建议两者使用不同的配对设备。

## 身份与侧记

侧记内容：

- `transfer_id`、原键和原始 request；禁止顶层 `id/state`；
- 连接名、`node_id`、`server_key`、`device_id`、`profile`；
- 完整内容清单及其整体 sha256；
- 原导入意图（见下）；
- 首次写入时间。

- **有效侧记：** 存在，形状正确，且与 journal 的传输 ID、request 和 `connection_identity` 一致。
- **侧记缺失或绑定不一致**（包括由旧版本创建的 journal）：只做本地只读诊断。`resume` 和 `cancel` 都拒绝（退出码
  2），**不退回**到只核对端点的取消，也不发起任何新的远端修改。
- **`resume`：** 侧记有效，且当前 `profile`、`device_id`、`server_key` 与侧记一致；内容清单按「内容门」重新核对。
- **`cancel`：** 侧记有效，且当前 `profile`、`device_id`、`server_key` 与侧记一致。**不读取源文件**；源文件可以已被删除。

## 内容门（B：严格的 manifest backend 守卫）

- **清单：** 对文件或文件夹，按 `TransferManager` 的同一套遍历规则（不跟随符号链接，排序，跳过非普通文件），每个
  文件记录 `{remote, size, sha256}`，另记清单整体的 sha256。
- **稳定读取：** 在租约内计算每个文件的哈希，前后各做一次 `stat`（大小、mtime、ino 必须一致），否则拒绝。这只能
  发现读取期间的变化，不能防止读取之后的修改。
- **守卫：** worker 传给 `TransferManager` 的 `backend_for` 返回一个包装：
  - `upload_begin(workspace_id, path, size, digest)` 必须匹配原工作区与清单，否则在调用后端前以 `conflict` 拒绝；
  - `post_import(workspace_id, files, identity)` 必须匹配原工作区、有序完整清单和本次确定 action ID；通过后先保存原导入意图，再发送；
  - 其余调用原样转发。
- **`resume` 时：** 重新计算源文件哈希，与清单比较，不一致即以 2 拒绝。
- **能保证的：** 不会以清单之外的摘要开启会话，也不会导入清单之外的文件。
- **不能保证的：** 源文件在哈希之后被修改时，hub 可能已收下部分不同的字节，到 `finish` 时校验失败
  （`checksum_mismatch`），会话被中止。结果是传输失败、不会导入错误的内容，但**不承诺**在 hub 收到错误字节之前就把它
  挡下。`TransferManager` 在大小和 mtime 不变时不重新计算哈希，这时由 hub 的 `finish` 校验兜底；重新计算出的新摘要则
  会在 `upload_begin` 被守卫拒绝。

## 原导入意图

backend 包装的 `post_import` 在发起网络请求**之前**，把本次意图持久写入侧记（在租约之内，原子替换侧记中的这一节）：

- `attempt`、导入 action ID；
- 完整请求（kind、node、workspace、files、action ID）的 sha256，以及有序文件清单的 sha256；
- 写入时间。

`show --check` 只查询侧记中**最后一次实际派发**的这个意图。导入被拒绝后，journal 的 `import_attempt` 已经加 1，指向的
是尚未发出的下一个 action；CLI 不会据此查询。

## 复核、确认丢失与原 action

- **复核：** 字节传完后，`_import` 发起导入。worker 一旦在 journal 中看到 `action.state == "review"`，就形成收据并按
  上述方式结束；父进程输出 `pending_review` 和 `observed_at`。批准由所有者或另一台设备完成；在 `any` 策略下，也可以由
  本设备通过其他客户端完成。CLI 本身不批准。
- **批准之后：** 用户执行 `transfers resume`，以同一个导入 action ID 重新查询（hub 幂等），直到 `succeeded`。若被拒绝，
  只有显式恢复才会以新的 `attempt` 派发；派发前会先记录新的意图，CLI 也会打印新的 action ID。
- **分块确认丢失：** 以 hub 的偏移为准（task 15 已实测）。
- **导入请求确认丢失：** 包括 `unavailable`、`timeout` 和连接中断，hub 可能已经收下。输出 `unknown` 与侧记中的原导入
  意图；用 `show --check` 读取，或显式 `resume` 以同一个 ID 重新请求。
- **本地停止不是远端取消：** 只有 `transfers cancel` 会撤回或中止远端的东西。

## 只读路径

`transfers list` 和 `show`（不带 `--check`）：

- 不构造 `TransferManager`，不取租约，不创建锁文件，不派发，不恢复，不连接 hub。
- 只读取 `<hub-state-dir>/cli/transfers/` 下文件名严格匹配 `^[0-9a-f]{32}\.json$` 的 journal 和
  `^[0-9a-f]{32}\.cli\.json$` 的侧记。
- 每个路径都先 `lstat`：符号链接和非普通文件都拒绝读取，只计数；打开时使用 `O_NOFOLLOW`（如平台支持）。
- 读取预算：每个文件最多 8 MiB，超出即视为不合格、不解析；本次调用总共最多 64 MiB，用完即停止并标记
  `truncated: true`。文件数最多 10 000。
- 分别校验两种形状：journal 的 `id` 与文件名相同、`kind == "upload"`、`state` 属于已知集合；侧记的
  `transfer_id` 匹配文件名及原绑定，且无顶层 `id/state`。不合格的只计数，不输出内容。
- 允许读到原子替换前后的任一完整快照；读失败计为 `unreadable`。
- 输出 `observation: "last_journaled"`：journal 中的 `running` 可能来自一个已结束的 worker，不代表正在运行。
- 保留原始 key 与 request 的身份，不做规范化。

保留期：worker 在租约内运行 `_recover` 时，会删除 7 天前的终态 journal 和对应侧记。超过保留期后，同一个键会开启一个
新传输（现有语义），文档中写明这一点。

## 验证计划（真实本机 loopback，公开合成数据）

沿用 `upload_restart.py` 和 `tests/test_hub_desktop_bridge.py:172` 的 fixture 风格：真实 Runtime、hub、外连节点，
CLI 以子进程运行。环境中 KEY 为空，MODEL 和显示相关变量全部 unset，不调用模型、求解器或 helper。实施前按 root 当前
源码复核所引的位置。

1. **首次上传：** 所有者签发 `--profile desktop` 配对码。用 2.5 MiB 的公开输入执行 `upload --key K`：
   - stderr 先出现键和传输 ID；
   - 结果为 `pending_review`，带 `observed_at`，退出码为 0；
   - **fixture 一直扣住批准**，直到断言「工作区文件数为 0、任务数为 0」完成之后才批准；
   - 收据来自 worker；worker 已被回收，租约已释放，侧记中有原导入意图。
2. **跨进程续传（hub 已收、journal 未记）：** 在第一个分块被 hub 接受后，SIGKILL worker（task 15 的驱动方式）。
   - 父进程报告 `unknown`，没有 worker 收据；
   - 第二次 `transfers resume`：传输 ID 相同，会话相同，偏移为 1 MiB，中途没有从 0 开始的分块，只有一次 finish。
3. **完成：** 所有者批准后执行 `transfers resume`，得到 `completed`；`show --check` 读到的就是记录中的原 action，状态为
   `succeeded`。
   - 工作区的路径、大小、sha256 与实际字节都一致；
   - 同一个键再执行 `upload` 返回原传输；换一个 `--path` 返回 `conflict`，且侧记的字节不变。
4. **拒绝后的意图：** 所有者拒绝导入，journal 的 `import_attempt` 加 1。`show --check` 仍查询侧记中已派发的原 action
   （`rejected`），不查询尚未发出的下一个 ID；显式 `resume` 时先写入新意图，再派发新 action。
5. **授权：** 非 desktop 配对的设备在启动 worker 和联系 hub 之前以 2 退出；hub 一侧的 403 另测。
6. **内容与身份：** 以下情况都在 worker 取得租约之后、构造 `TransferManager` 之前以 2 拒绝（用只记录调用的探针
   证明）：
   - 源文件内容改变但大小和 mtime 不变（恢复 mtime 后修改）；
   - 源文件大小改变；
   - `server_key` 改变（同名连接重新配对到另一个 hub）；
   - `device_id` 改变；
   - 配置不再是 desktop。
7. **B 守卫：**
   - 清单哈希之后、Manager 重新哈希之前修改源文件：新摘要在 begin 守卫被拒绝，没有新会话；
   - Manager 哈希已完成后再修改：守卫可能接受原声明，允许传输失败；须由 finish 拒绝不匹配字节，且没有 import；
   - 会话进行中修改：hub 返回 `checksum_mismatch`，没有导入，工作区为空；
   - `post_import` 的文件列表与清单不同（用桩构造）：被拒绝，也没有写入意图。
8. **侧记：**
   - 实际 Manager 的 `_recover/list` 都忽略合法侧记；顶层 `id/state` 侧记形状被 CLI 拒绝；
   - GC 不删除本次新侧记或未确认的无 journal 意图；侧记发布后、journal 创建前崩溃，异内容同键仍拒绝；
   - 侧记缺失或绑定不一致时，`resume` 和 `cancel` 都以 2 拒绝，且没有远端请求；
   - 侧记有效时删除源文件，`cancel` 仍能撤回复核中的导入、中止会话，工作区没有文件。
9. **并发与租约：**
   - 第一个 worker 持有租约时，第二次命令返回 `busy`（退出码 3），现存 journal 和侧记的字节完全不变；
   - 用一个阻塞分块的桩让 `stop` 超时：worker 在发出收据并调用 `os._exit` 之前，租约一直不释放；父进程超期后强制
     结束并回收；
   - 在 `CliRunner` 中运行时，宿主进程不退出；
   - 回收之后，下一个 worker 修改了 journal：原命令的输出仍是收据，之后读到的变化标为 `subsequent_observation`。
10. **只读查看：**
    - `transfers list|show` 前后，命名空间目录（包括锁文件）的文件列表、mtime 和字节都不变，也不产生 hub 请求；
    - 符号链接、非普通文件、大于 8 MiB 的文件都不被读取；总读取量不超过 64 MiB；
    - 损坏或形状不符的文件只计数，不输出内容。
11. **超时与中断：**
    - `--wait` 到期或 Ctrl-C 都得到 `interrupted`，hub 会话保留其偏移，没有调用 cancel 或 reject；
    - 让导入请求的回复丢失（hub 已收下）：得到 `unknown` 和侧记中的原意图；`show --check` 读到 hub 上的原 action。
12. **回归：** 现有的 direct / SSH `workspaces upload`、`jobs` 全套、task 16 的 Hub workspace 测试，以及轻量导入测试
    （`suan.runtime.cli` 不导入 `suan.runtime.hub_transfers` 或 `server`）都不退化。
13. **证据：** 只写到外部目录。不记录 token、配对码、upload ID 或本地路径。

## 不在本片范围

hub 或节点的协议、授权、review 策略与 schema 变更；桥的生命周期；私有冻结副本；`--wait-review`；R2/R3；模型、密钥
与网络策略；科研参数；真实 MuPRO、跨站点使用和科学有效性。

## 实现状态（CL-D1-HUB-UPLOAD-CLI-18 第四版，root 集成）

实现位于 `suan/runtime/hub_transfers.py`（worker、侧记、内容清单、守卫、只读查看与父进程监督）以及 `suan/runtime/cli.py`
的惰性入口（`workspaces upload` 的 hub 分支与 `workspaces transfers`），测试在 `tests/test_runtime_hub_transfers.py`。

**当前源码定位（本分支基线 `a0f77fa3` 中的 `suan/desktop_bridge/transfers.py`）：** 上文的历史行号已按当前文件复核。
- `_recover` 在 128-142：只按顶层 `state` 处理，只按 `*.json` 枚举。
- `list` 在 151-161：只收有顶层 `id` 的记录。
- 键与身份：`keyed_id` 在 165-168，`_existing` 在 170-180，`_new` 在 182-192（`connection_identity` 在 185）。
- 启动：`_start_upload` 在 206-256。
- 恢复与取消：`resume` 在 297-322，`cancel` 在 333-344，`_finish_cancel` 在 346-370。
- 停止：`stop` 在 372-380。
- `_upload` 在 530-590：重新哈希在 542-547，`upload_begin` 后保存在 548-550，分块在 554-565，`finish` 校验在 567-581。
- `_import` 在 592-633：`attempt` 在 599，`post_import` 在 605，拒绝后 `+1` 在 625。
- 当前文件新增了 `_writer` 准入（69-81）和 `release_after_stop`（387-417）。worker 不调用后者：它的租约随 `os._exit`
  结束，不需要后台回收线程。

**实现中的细节：**
- **复核要实时确认：** journal 中的 `review` 可能是上一次运行留下的（`_import` 只在 action 视图变化时才保存）。
  worker 先实时读取 hub 上同一个导入 action，确认仍为 `review`，才输出 `pending_review`；否则继续观察。
- **重复派发不改写意图：** 复核通过后恢复时，会以相同的 attempt、action ID 和请求再次派发；这不会改写侧记中的原
  意图（侧记字节不变）。
- **侧记写法：** 以排序后的键写入磁盘，按键集合校验形状；通过临时文件加 `os.link` 无覆盖发布。临时文件不匹配
  `*.json`，所以 Manager 和只读读取都看不到半写的侧记。
- **worker 的导入来源：** worker 用 `sys.executable -P -m suan.runtime.hub_transfers --worker` 启动（`-P` 需要
  Python 3.11+，使工作目录不进入 `sys.path`），不用 `-I`：
  开发环境中 `-I` 会改从可编辑安装的另一棵源码树导入。父进程把自己的 `suan` 来源目录放在子进程 `PYTHONPATH`
  的最前面；worker 在取得租约之前核对来源一致，不一致即以 `origin_mismatch` 拒绝。安装态下这个目录就是
  site-packages 本身。
- **父进程不碰源文件：** `SOURCE` 以普通字符串接收，因为 click 的 `Path` 类型即使不要求存在也会 `stat` 它。直连
  模式改为显式调用 `click.Path(exists=True)` 转换，保持原有的检查和提示。
- **租约对象：** 保存在模块级引用中。如果只在构造后丢弃，CPython 会立即关闭文件并解锁；红例已证明。
- **GC 后复核：** 在 Manager 的恢复与 GC 之后，worker 重读目标 journal 和侧记；除 journal 的 `state` 外，任何身份
  字段或侧记字节变化都以 `changed_during_recovery` 拒绝。
- **没有收据时：** 原传输和原导入意图只能在回收之后读取，因此标为 `subsequent_observation` 输出，不冒充收据。
- **只读读取（候选 2）：**
  - 以非阻塞、不跟随链接的方式打开，并对描述符本身做 `fstat`；`lstat` 之后被换成 FIFO 的路径直接拒绝，不会阻塞。
  - 每次读取以剩余预算和单文件上限为界，按实际读到的字节计入总预算；打开后变大的文件按 `budget` 或 `too_large`
    拒绝，并标记截断。
  - 目录扫描最多检查 `4 × 10 000` 个条目。
  - journal 中视图会用到的嵌套字段要先校验类型，不合格的只计为跳过。
- **父进程监督（候选 2）：**
  - 作业行超过 IPC 行上限时，在启动 worker 之前拒绝。
  - 作业和停止请求由单独的写线程发送，worker 不读取输入也不会拖过同一个绝对截止时间。
  - 第一次 Ctrl-C 请求在宽限内停止；第二次直接终止。终止、强杀与回收放在 `finally` 中，重复中断也不能跳过。
- **收据的接受条件（候选 2）：** 以下任一不满足，结果都是 `unknown`：
  - 每条记录都以换行结束，在字节与条数上限之内，并且是已知类型的对象；
  - 恰好一条、并且是最后一条收据；
  - 其 `outcome` 已知，并与真实退出码一致；
  - 带有本次作业的随机 `nonce`；
  - 指向预期的传输 ID。
- **候选 3 补充：**
  - **等待时间：** `--wait`、`run_command` 和 `supervise` 都只接受有限的正数秒（不接受布尔值）。CLI 对 `nan`、`inf`
    以退出码 2 拒绝，不启动 worker。
  - **严格 JSON（IPC）：** 在每一层嵌套都拒绝以下内容：
    - 重复键；
    - `NaN`/`Infinity` 字面量；
    - 溢出为无穷的数，如 `1e999`、`-1e999`（`parse_float` 校验，因为这类数不会触发 `parse_constant`）。

    写出端用 `allow_nan=False`。
  - **收据字段类型：** 先查字段类型，再做成员查找；`journal` 必须是对象，带字符串 `id` 和已知 `state`。
    `run_command` 还要求 `journal.id` 等于预期的传输 ID。
  - **回收（`_reap`）：** 只有信号调用真正返回后，这一步才算完成。在 `terminate` 或 `kill` 执行之前到达的中断会
    重试该调用，不会跳过。进入强杀之后，每一轮都重发 `kill`，再做有界等待，没有无超时的 `wait`。只有观察到
    worker 真正退出才返回，所以命名空间租约始终由操作系统随进程退出释放。
  - **只读读取的计费：** 已读到的字节在 `finally` 中计入预算，后续读取失败也照样计入。字段先做类型判断，
    不可哈希的值计为跳过，不会抛出。
  - **身份可读回：** 发布侧记前，先估算两样东西的大小：
    - 侧记加上预留的导入意图（`INTENT_RESERVE`）；
    - Manager journal（预留 `JOURNAL_RESERVE` = 64 KiB）。

    任一超过 `READ_FILE_BYTES`，就以 `identity_too_large` 拒绝。拒绝发生在构造 Manager、GC 和发布之前，以保证
    只读查看能读回自己写下的身份。
- **候选 4 补充（侧记发布）：**
  - `SidecarHolder.publish` 只使用原子的不覆盖原语 `os.link`：
    - `FileExistsError` 拒绝为 `sidecar_exists`；
    - 其他硬链接错误（如 `EOPNOTSUPP`、`EPERM`）拒绝为 `sidecar_publication_unsupported`。

    候选 3 在这里有 `exists()` 后 `os.replace` 的回退，已删除。命名空间租约只排除遵守约定的 worker，
    排除不了其他写入者，所以这个回退在检查与替换之间可能覆盖别人新出现的侧记。
  - 已存在的最终侧记从不被替换、删除或修改。只有链接成功后，`holder.sidecar` 才采用新身份。
  - 只删除本次发布的临时文件：写临时文件和链接都在同一个 `finally` 中。

**已验证：** `tests/test_runtime_hub_transfers.py` 与 `tests/test_runtime_hub_cli.py` 在真实 loopback hub、外连节点与
Runtime 上运行。红例分别证实：
- worker 存活期间第二个命令得到 `busy`；
- 内容守卫在 Manager 重新哈希之前拒绝。

**root 集成验证：** 作者基线 `a0f77fa3` 九模块 225 项通过、零跳过；root 基线 `2b92622d` 加六文件冻结覆盖后，九模块 234 项通过、零跳过，差九项是 `6c481e59` 的共同后端坏状态启动回归。root 使用的 `transfers.py` 摘要为 `54d472903c71f6c5b924d262bb9a2f808804e0e1718077842a08e1aaab1b8b36`；上文 `5311155a…` 仅为作者旧基线，不能当作已包含该修复。

root 离线构建新 wheel，在不继承系统包、无科学/GUI/模型依赖的新环境中，从无产品源码的测试副本以 `python -I` 运行：收集 234 项，明确排除两个需 NumPy/Matplotlib 的部署用例，实际 232 项通过、零跳过；这两项仍由完整源码矩阵覆盖。运行前后三项产品源码摘要和父进程实际导入来源一致，测试结束未观察到自有活后代。此来源证明只覆盖父进程已加载模块；不能声称核对了每个服务进程的完整模块图。

独立纯文件检查还覆盖 12 个发布场景及 11 组读取边界，硬链接失败不覆盖并发出现的侧记，也不提前采用新身份。证据：`d1-hub-upload-cli-20261108-21/root/author-candidate4-20261108-38/`、`candidate4-installed-20261108-38/` 及 `readonly-review-author-candidate4-upload_readonly_review/`（均位于本机验证根）。

**尚未验证：** Windows 与 macOS 上的 worker 生命周期、真实不支持硬链接的文件系统、外部站点网络与科研有效性。本机 loopback 和注入反例不替代这些验收。
