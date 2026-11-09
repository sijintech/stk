# 开发交接记录

## 2026-11-09 17:56 UTC · MuFerro HDF5 原生选择与 Cocoa 隐藏观测

`c3061e78` 为现有严格图入口增加单容器元数据节点，缓存查找前及元数据解析前核对登记 SHA-256。项目根和固定相对路径限定访问范围，列表只返回明确的场和步号。扫描最多 4096 个链接，列表最多 256 项，超出时拒绝整份列表。`49140b04` 在仿真面板接入列表、明确选择和打开。校验并持有载荷后才接纳 Viewer。

Linux X11/Xvfb 1440×1600，软件 OpenGL、缩放 1。固定起点为最大化 Project，Simulations 与 Simulation runs 已展开，选中唯一已成功并收集的运行，正例 Viewer 为空，Python 草稿隐藏。依次点击列表、下拉、`Polar · step 2`、打开，共四次，零滚动、零键入。Viewer 显示第 2 步 `Polar_x` 的 24 个体素，值域 `[0, 69]`。同大小容器改写后拒绝打开并保留原 Viewer。第三组在挂起成功答复时另点一次审阅页，放行后保留审阅页画面及原 Viewer。三组保留原 Runtime 任务、项目修订 8 和隐藏草稿。

本地 Python 联测 165 项通过，1 项性能基准跳过。原生相邻 34/34。离线构建 wheel，并从隔离安装位置确认节点注册和安装版节点参考。 Linux 项目 CPU 广跑 1034 过，12 项 Peer 因初始环境缺少依赖或安装版 helper 失败。补齐后同源码 Peer 20/20 通过。 新头 `49140b04` 的隔离 Python 3.11 全量仍在运行。

Claude59 在独立 worktree 交付 `239bcd8d` 的通用运行索引适配器作为对照。H1 采用只访问单个容器的专用路径。Claude60 已从 H1 产品头接手原生请求与回执的持久回归，root 负责审阅、集成与发布。

`e9d0da9b` 新增两个非门禁 macOS 诊断，复用常规播放、seek 与真实切标签，在原一秒窗口内先读原生回执再尝试两次 DOM 采样。Linux 相关 29/29，Apple 条件语法与目标测试注册通过，实际目标机时序待下一轮。旧 `fd611652` 的新增无重复暂停对照 2/2。两例 WebKit 被动回复 `Playing`，同一隐藏会话两次 DOM 均为暂停，时间增量为零。主验收 4/6，两例在首次原生查询前因隐藏保持时媒体位置回到前一次 seek 而失败。macOS CPU 1524/1524、Metal 254/254。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42658246869/artifacts/13696087547)

远端 `fd611652` Desktop `42658246869` 于 17:52:31 UTC 结束，5/6 个作业通过。Linux 主作业 2141/2141，Linux 打包及冷环境验证通过，Windows CPU 1465/1465。Windows 原生 6/6、零跳过，六项各 20 轮。PDF 160 张 OS 截图，20 次重准备，捕获启动最长 79 ms。PR #53 与 #54 的头未变化。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869) · [Windows 工件](https://github.com/sijintech/stk/actions/runs/42658246869/artifacts/13696884487)

## 2026-11-09 17:28 UTC · HDF5 载荷接纳与项目根绑定

`9e22e6ed` 提供明确授权的 Viewer 载荷替换。采用前核对项目、调用方、屏幕容量、文本编辑与 Viewer 版本。历史分析仍要求空 Viewer。内容寻址缓存共用有界解码，先检查每个唯一缓冲的长度和总预算，再读取并校验 Viewer 实际持有的独占字节。

实际严格 C++ 桥和 GraphWorker 从合成收集容器打开登记 SHA 对应的第 2 步 `Polar_x`，值域 `[0, 69]`。显式请求在延后阶段替换已有 Viewer。改写同大小 HDF5 时保留原 Viewer 和布局，排队后打开其他来源时返回冲突并保留新来源。另核对缓存改写、独占字节、长度上限、项目修订 8 及严格桥零契约违规。原生项目相关 28/28、载荷单元 6/6，均零跳过。

用合成目录交换复现按算例子目录绑定的边界问题。调用端检查后，若算例目录被换成指向项目外的链接，工作进程会将链接目标当作根。候选改为使用规范化项目根与固定运行相对路径，拒绝这一交换反例。已用真实严格桥核对该打开候选的 C++ 图摘要、24 个体素及 14 项输入或回执拒绝。打开候选已备好供面板接线。Claude59 正在独立 worktree 测试字段与步号适配器。审阅发现通用运行索引会枚举整个绑定，另在隔离 worktree 验证只读取指定容器的元数据节点。原生面板与实际点击仍待验。

隔离 Python 3.11 全量 `2d488712` 已结束，6464 项通过、180 项跳过、4 项按测试标记排除，零失败。 该轮覆盖 HDF5 测试替身修正，采用 3.11 源码和独立依赖环境。

远端 `fd611652` 的 Desktop `42658246869` 三个 Linux 作业成功，主作业 2141/2141。Windows 和 macOS 仍在运行，本地提交等待整轮终态。PR #53 与 #54 的头和审查状态未变化。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869)

## 2026-11-09 17:12 UTC · 网页图谱接续、HDF5 选择核查与 Runtime 终态

`84ab61c6` 让网页图谱复用任务面板已接受的节点、工作区及任务观测。快照之外的已核验任务会进入图谱绑定，精确终态结束原任务进度轮询。独立选择其他图谱数据源或显式清空绑定时保留该选择。

生产 Chromium 1440×1100，固定起点已选节点、工作区和图谱页，能量预设已加载，Viewer 为空并有未发送草稿。输入 32 位原任务 ID 后点击一次，零滚轮和页面滚动。输入框为跟随光标有内部水平滚动。真实 Hub、NodeAgent 和 Runtime 保持在线，七次心跳均省略该任务。旧版读到原任务 running 但没有图谱选项或事件读取。新版选择原任务，用一次 `task.events` 显示 40%、第 4/10 步，精确终态后的 11.152 秒无后续事件读取。保留图谱参数、空 Viewer、草稿和重试记录，两轮各一个 Runtime 任务、零 Hub 动作。

网页生产构建和测试 11/11。四项 Chromium 边界覆盖错误工作区、A→B→A 的迟到答复、仅具备事件能力的旧节点及独立或清空绑定。上一轮产物列表对迟到空答复的浏览器回归也通过。

`2d488712` 修正上一批遗漏的 HDF5 快照测试替身，使其模拟允许收集。真实取消门控及摘要拒绝断言照常验证。定向 1/1。HDF5 与工作流组 110 项通过，性能基准和真实 MuFerro 许可环境各跳过一项。隔离 Python 3.11 全量基于 `2d488712` 运行中，已核对依赖及 suan 源码导入位置。

root 以 `e70982f9` 选择集成 Claude58 `045fb476` 的设计和证据。实际收集的合成 HDF5 含两个场各两个步号。严格桥和 GraphWorker 按登记 SHA 读取指定非末帧，原地改写容器与错误选择器被拒绝。root 用作者探针独立复跑 1/1。复核确认原生 `open_path` 会在求值前清空 Viewer，设计改为先验证并解码载荷，再核对项目、选择和 Viewer 版本后接纳。原生界面与点击数仍待实现验证，真实许可与 HDF5-only 完成仍待证。 [设计核查](design/mupro-hdf5-result-selection.md)

Claude59 已在独立 `stk-claude` worktree 从本批设计头开始实现原生 HDF5 字段与步号的有界元数据适配器。root 负责面板、Viewer 接纳、审阅和集成。

远端 `fd611652` Runtime `42658246715` 于 17:07:17 UTC 终态，八个作业通过，三项 Linux Python 与两项 Windows 客户端作业均因同一条 HDF5 测试替身提前抛出 `_Cancelled` 失败，五项各只有这一条失败。Desktop `42658246869` 仍在运行，本批本地提交等待整轮 Desktop 终态后推送。PR #53 和 #54 的头未变化。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42658246715) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869)

## 2026-11-09 16:57 UTC · 网页完成产物刷新与 Hub 动作回执

`ef894f85` 在网页接受同一执行节点、项目和任务的 Runtime 精确终态后，自动只读刷新原任务产物。不同工作区的终态答复不会触发刷新。手动及自动读取共用答复顺序，已采用的新产物列表保留，迟到的旧空列表无法覆盖。

生产 Chromium 1440×1100，固定起点已选节点和项目，Viewer 为空且有未发送草稿。真实 Hub、NodeAgent 和 Runtime 保持连接，测试心跳列表固定显示 running。同一任务解除门控后，旧版两次读到 `succeeded` 仍只有占位项。修复版从起点一次点击、零滚动，自动读取一次产物并列出 `field.vti`。两轮各一项 Runtime 任务、零 Hub 操作记录，Viewer、草稿和重试内容保留。另用受控浏览器响应核对工作区不匹配及迟到的空列表。生产构建和网页 11/11 通过。

`1a6fb12c` 将已读到的 Hub 动作回执与后续 Runtime 任务读取分别保留。真实回环中取消动作先返回排队，Runtime 收到一次请求并在修改前拒绝，随后节点断开。刷新保留原可重试 `unavailable` 错误，冷重开能读到同一 Hub 动作 `failed`，并保留原 Runtime 任务最近的 `running`。旧代码定向复现 1 项失败，隔离相邻回归 68/68，root 主工作区联合回归 80/80，均零跳过。

Claude58 以 `fd611652` 在独立 `stk-claude` worktree 开始 HDF5 字段和精确步号选择设计。任务限一份设计说明及仓库外合成探针，核对已有发现和图入口能否复用收集摘要。真实许可与 HDF5-only 完成仍待验证。

远端 `fd611652` Desktop `42658246869` 仍在运行，新的本地提交等待该轮终态。Runtime `42658246715` 当前 8/13 个作业通过。开放 PR #53 和 #54 的头未变化，分别仍有冲突和检查问题。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42658246715)

## 2026-11-09 16:46 UTC · Runtime 取消确认、Cocoa 对照与桌面终态

`c3f869eb` 先向正在跟踪的各 Runtime 原任务分别发出一次取消，再用原连接只读核对待确认的任务。只有观察到 Runtime `cancelled` 才记录原任务已取消。已先结束的任务保留 Runtime 原终态，未确认的任务保留原 ID 并标为中断。五秒是发出请求后的观察窗口，单次网络读取仍受原连接超时约束。已经持久化的取消可阻止新收集开始。人工再次启动可接回原运行或原成功任务。

旧代码在取消回复丢失时直接写入已取消，并会在成功读取与取消交错时进入收集。新回归核对接收取消后的断连、晚于观察窗口的回执、多行中的畸形回复和已取消后阻止新收集。八个相关 Python 测试文件 137/137，零跳过。

root 集成 Claude57 在独立 worktree 提交的 `d86b2324`。真实回环 Runtime 拒绝第一次取消时，第 2 次尝试停为中断。求解器 PID、创建时点与任务 ID 保持一致，无新增提交、取消重试、收集或分析。第 3 次经人工启动接回同一任务，原批准保留。Claude 基线组 114 过、1 项预期失败。root 在隔离 worktree 使用修复和作者的原始测试，拒绝取消与正常取消对照 2/2。使用门控合成求解器，商业许可宿主仍待验。

上一轮 macOS 的两个失败用例中，DOM 报告暂停但媒体时间倒退。原无 DOM 对照在两例都读到 WK `Playing`。`ad174492` 保留该对照，新增两例非门禁诊断，在同一隐藏视图先保留被动 WK 原生回执，再相隔 400 ms 观察两次 DOM 媒体时间。Linux 相关 CTest 29/29。Apple 条件 C++ 语法和工作流步骤检查通过，实际行为待 macOS CI。

远端 `b4110f8c` Desktop `42646061897` 于 16:41:18 UTC 终态，五项通过，仅 macOS 失败。Linux 主测试 2138/2138，Linux 打包与冷环境验证通过，Windows CPU 1463/1463。Windows 原生 6/6、零跳过，六项各 20 轮。PDF 160 张截图、20 次重准备，重准备启动最长 89 ms，PDF 全程单次捕获启动最长 114 ms。macOS CPU 1521/1521、Metal 254/254、原生 4/6。Runtime `42646061798` 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [Windows 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13692551836) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13690393949) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42646061798)

## 2026-11-09 16:25 UTC · 网页精确任务观察、Hub 撤权和人工取消

`683963e9` 为 STK 网页任务面板接入 Hub 精确只读观察。节点快照与 Runtime 最近状态分开，核对节点、工作区和任务 ID。通过任务 ID 也可查询快照外的任务。断线保留最后一次观察，重连继续读。图谱事件轮询使用现有只读入口，选择和自动观察不写 Hub 操作记录。

生产网页 Chromium 1440×1100，起点已选择节点和项目，Viewer 为空。点击任务一次、零滚动，取得同一 Runtime 任务的精确 running。真实 NodeAgent 断连时保留 running 并标明读取不可用，原任务成功后重连更新为 succeeded。模拟心跳遗漏后按 ID 找回，错误工作区拒绝采用结果，撤权后网页退出会话，图谱事件查询为只读。CLI 与严格 Desktop Bridge 的终态记录一致，Runtime 只有一个任务，Hub 操作记录零条。网页构建和 11/11 测试通过。证据 `root-delivery-20261109-98/browser-verified/{receipt.json,fixed-start.png,running.png,unavailable.png,succeeded.png}`。

`75b7e87f` 在转发答复前复核客户端和节点，撤权的迟到回复分别返回 401 和 404。`1774642d` 在发送每条 SSE 后复核授权，同批后续事件被拦截，旧流正常结束。`c98145a3` 要求 MuFerro 完整结果包含能量、进度、完成文件和初始 Polar，已知计划时仍检查计划帧，旧记录的原终态和验证保留。两项首批合跑 172/172，SSE 与联邦等后续 46/46，均零跳过。隔离 MuFerro 联跑 212 过，3 项跳过（Windows junction、两项商业许可）。

root 以 `17cbfcc1` 集成 Claude56 `8962c956`。真实第三个 Bridge 在接管原运行后执行人工取消。求解器仍被夹具门控时，Runtime 对原任务 ID 收到一次取消，求解器停止，项目停止且没有新增提交、收集或分析。重复取消和冷观察保留原批准。作者和 root 分别 114/114 零跳过。该场景使用可达 Runtime 和受控求解器，取消请求未确认的失败分支仍需单独处理。证据 `root-delivery-20261109-98/claude56-root.xml`。

远端 `b4110f8c` Desktop `42646061897` 的三个 Linux 作业通过，Linux 主测试 2138/2138，Windows CPU 1463/1463。macOS 于 16:23:06Z 失败终态，CPU 1521/1521、Metal 254/254、原生 4/6。新增不重复暂停的对照 2/2，视频与 HTML 视频先在可见时读到 Paused，真实隐藏后保留同会话，独立查询均读到 Playing。对照没有隐藏期 DOM 采样，重复暂停组 0/2 且两例各 27 次 Playing 后 watchdog 关闭。Windows 原生仍在运行，本批等整轮 Desktop 终态。Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13690393949)

## 2026-11-09 15:56 UTC · 历史分析归档核验与 MuFerro 运行中接续

`36c5ab8d` 绑定选中历史运行的首次归档回执。相同运行的结果读取和状态读取若返回变化后的回执，保留已验证的结果和检查模型。`af8746ad` 按已验证的归档预算检查所选载荷，用同一普通文件句柄读取精确长度，再对 Viewer 实际持有的独占字节校验 SHA-256。旧代码的回归分别确认会接受替换回执、已解码映射会随源文件原位改写。新代码能拒绝改写和长度错配，已加载载荷仍保持原值。Windows/macOS 的新读取路径待目标 CI。

回执变更 C++ 86/86，精确读取与归档相关 C++ 92/92，独立缓冲与载荷检查 11/11，均零跳过。隔离 core 90/90，另有 3/3 Linux UBSan 读故障注入。Linux X11/Xvfb、1440×1600、软件 OpenGL，起点是已选中成功历史运行且 Viewer 为空。一次点击、零滚动显示冻结 HDF5 第 4 步 `Polar_x`。只请求一次归档，项目修订 13、原 Runtime 任务、冻结文件和隐藏草稿一致。证据 `root-delivery-20261109-97/{archive-owned.xml,archive-unit.xml,native-replay/evidence/receipt.json,archive-exact-io/unit-final.xml}`。补充项目广跑 1473 通过、12 项 Peer 在缺依赖环境失败。重建 Peer 目标并改用含 cryptography 的 Python 3.12 和已安装 helper 后，Peer 20/20 零跳过。 [验收记录](runtime-validation.md)

root 以 `6e638721` 集成 Claude55 `b61ecc9e`。旧 Bridge 强制退出时求解器仍被夹具门控。重新观察、非强制人工恢复及显式启动期间，原求解器 PID 与创建时点保持一致。第 2 次尝试在解除门控前记录接管原任务和运行状态，重复启动只读回当前执行。随后记录一次收集，绑定原产物、冻结快照和真实 GraphWorker 能量结果。总提交一次，取消零次，原审批保留。作者和 root 六个源码测试文件各 113/113，均零跳过。商业许可求解器仍待验。证据 `root-delivery-20261109-97/claude55-root.xml` 与 `claude55-root-scratch/`。

`aa9a909d` 把 `transfer.cancel` 的文档与既有返回值对齐，已终态时保留原状态，等待结束时返回当前状态。传输生命周期与关停回归 44/44。复核 #53 `c9f13994`，旧并发问题已由主线修复，剩余立即入队实现会提前从线程表移除旧 worker。#54 `2dd3e4ee` 的大写交接名与现有文件冲突。两项保留待审。 [PR #53](https://github.com/sijintech/stk/pull/53) · [PR #54](https://github.com/sijintech/stk/pull/54)

远端 `b4110f8c` Runtime `42646061798` 于 15:55:20Z 完成，13/13。Desktop `42646061897` 仍在运行，本批等待该轮终态后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42646061798)

## 2026-11-09 15:30 UTC · Cocoa 隐藏采样、MuFerro 人工接续与桌面终态

`f6730c49` 增加 macOS 探针对照。先确认同一导航的可见原生暂停，真实切换标签时只跳过本次再次派发，隐藏保持后独立读一次 WebKit 播放状态。 Linux 媒体及证据 34/34，合成守卫 42/42，Apple 条件 C++ 语法及 CTest 注册通过。真实 Apple SDK 构建及 WKWebView 结果待新 CI。 [验收记录](runtime-validation.md)

root 以 `767903df` 集成 Claude54 `43e52c63`。真实第三个 Bridge 观察原任务时不收集。人工恢复将消失的旧执行尝试标为中断，明确启动后第 2 次尝试接管原成功 Runtime 任务，保留原批准并核对原始输出字节。真实 GraphWorker 生成 Total Energy `[-1.125, -2.25, -3.375]` 并在 Bridge 退出后回收。定向 1/1，六个验收和 Bridge 测试文件共 112/112，均零跳过。使用受控求解器夹具，商业许可宿主仍待验。证据 `root-delivery-20261109-96/claude54-root-final.xml`。

远端 `971c0cbf` Desktop `42633409122` 于 15:30:19Z 终态，五个作业通过，macOS 原生失败。Linux 主测试 2135/2135，Windows CPU 1460/1460，Windows 原生 6/6、零跳过，六项各 20 轮，PDF 160 张截图且重准备 20 次。macOS 原生 4/6，首次可见暂停 2/2，可见二次暂停 1/2，重复隐藏暂停 0/2。两例均先获得可见原生 Paused，真实隐藏后的二次请求收到 ACK，随后 26 和 23 次原生查询均为 Playing。macOS CPU 1518/1518、Metal 254/254，Runtime 13/13。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42633409122/artifacts/13688110049) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42633409122/artifacts/13684539547) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42633409122)

## 2026-11-09 15:10 UTC · 一次点击查看已验证的历史分析

`e345038f` 给成功的历史分析增加“读取并显示结果”。归档校验后只有一个可显示载荷时直接打开，多个时保留手动选择。 root 实测固定起点一次点击，与此前四次点击相对照。 分析、Viewer 与工作台定向 70/70，项目 CPU 标签 1044/1044，均无失败或跳过。 [验收记录](runtime-validation.md)

root 以 `a8ac9db2` 集成 Claude53 `5a3d8033`。SIGKILL 前核对原批准与已运行的求解器，桥离线时同一任务成功。重开读取历史启动和项目中持久的 running 状态，实际 Runtime 已成功，真实提交共一次。下载三份产物核对摘要，根源码 103/103。证据 `root-delivery-20261109-95/claude53-root-final.xml` 和 `claude53-root-focused/`。 远端 `971c0cbf` 三个 Linux 作业、Windows CPU 1460/1460 与 Runtime 13/13 通过。macOS 原生基线 4/6，新暂停顺序对照 0/2。两个可见暂停先确认成功，隐藏后的新暂停收到 ACK，但 26 次与 23 次原生回复均为 Playing，最终 watchdog 关闭。第二次可见对照 1/2，HTML 用例止于初次暂停的时间下限。Windows 原生仍在运行，本批等待整轮结束。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42633409122/artifacts/13684539547) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42633409122)

## 2026-11-09 14:40 UTC · 冻结 HDF5 归档的原生首帧

`71f878df` 修正 Viewer 在采纳归档后首帧被旧灰色背景盖住的问题。旧代码回归失败，修正后相关 C++ 67/67。 根工作树按相同布局做了旧、新二进制像素对照，第四次点击后无需额外输入即可显示体数据。 root 以 `641b2807` 集成 Claude52 的 `0cda6bcc` 与 `6464a3c0`，审批跨进程和相邻回归 102/102。 [验收记录](runtime-validation.md)

本机 `395e78fd` 隔离 Python 3.11 全量 6446 过、180 跳过、4 排除、零失败。远端 `971c0cbf` Runtime 13/13 已于 14:39:55Z 结束，Desktop 仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42633409122)

## 2026-11-09 14:12 UTC · 上一轮 Desktop 终态与冻结 HDF5 分析

root 以 `9f2bcfd3` 集成 Claude51 的 `047f20b3`，将合成求解器步数与 HDF5 夹具对齐，并在两次分析期间移开原收集文件来验证冻结读取。根工作树收集回归 7/7。 [验收记录](runtime-validation.md)

远端 `249698d0` 的 Desktop 于 14:12:41Z 结束。三个 Linux 作业通过，Windows CPU 1460/1460、原生 6/6，macOS 原生 4/6。Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42621953590)

## 2026-11-09 14:06 UTC · HDF5 实际摘要、图目录复验与隐藏对照

root 提交 `395e78fd`，复验 HDF5 摘要和 Python 全量发现的两处目录遗漏。`40608ca1` 集成 Claude50 的 `5f954d84`。Claude51 接手实际收集记录的冻结分析回归。`090fe8f2` 集成独立 Cocoa 诊断，Windows 原生仍是前一轮 Desktop 唯一未完成作业。 [验收记录](runtime-validation.md)

## 2026-11-09 13:49 UTC · 丢失批准回复和收集目录消歧

root 以 `7ac983e8` 集成 Claude49 的 `2846d935`，加入提交调用计数。`3f486870` 统一原生入口与 Viewer 的收集预设消歧，Linux C++ 红绿和实际面板点击已验。Claude50 接手已收集 HDF5 显式查看核对。前一轮 Windows CPU 通过，原生正在运行，macOS 可见与隐藏对照已有回执。 [验收记录](runtime-validation.md)

## 2026-11-09 13:36 UTC · 审批冷重开和 MuFerro 本地验收

root 以 `5e3eba2b` 集成 Claude48 的 `49d3742a`，加入实际启动调用计数。`173d0534` 修复输入快照路径重新打开与旧准备目录 FIFO，`2eb64f04` 集成独立末帧复现、补旧节点预设回退，并取得 Linux 原生脚本入口证据。Claude49 接手丢失批准响应后的冷重开。远端前批 Runtime 13/13，本批在整个 Desktop 终态后推送。 [验收记录](runtime-validation.md)

## 2026-11-09 13:17 UTC · 主线修复与开放 PR 核对

root 提交 `95c2c464`、`3924f39e`、`8da56052`，分别处理审批响应、同一传输尝试的重试、MuFerro 收集与查看。`00831075` 集成 Claude47 的 `fcbcdc08`，Claude48 接手 S2c 冷重开验证。PR #53 旧分支与主线冲突，其原重试丢失已修，另复现的尝试竞态由本地独立补丁处理。PR #54 的历史交接与现有文件名大小写冲突。两个 PR 维持待审状态。`d49f6685` 的干净 Python 3.11 全量已结束，6437 项通过。 [PR #53](https://github.com/sijintech/stk/pull/53) [PR #54](https://github.com/sijintech/stk/pull/54) [验收记录](runtime-validation.md)

## 2026-11-09 13:01 UTC · DAT、Cocoa、监控导入及 Hub 回环

root 提交 `8a50e343`、`e1cf1d47`、`d49f6685`。三个提交分别绑定直读实际字节、补 Cocoa 隐藏暂停探针、恢复独立监控导入。root 以 `7132755f` 集成 Claude45 的 `2563468d`，以 `c8618a4f` 将 Claude46 的 `b64da145` 改为扩充现有回环测试。Claude47 接手现有 `graph.meta` 观察证据。前一轮 Desktop 已终态且结果入档，本批满足推送等待条件。 [验收记录](runtime-validation.md)

## 2026-11-09 12:31 UTC · MuFerro 输出和原生审批证据

root 以 `7daf672f` 修复链接产物误判和管道阻塞，并以 `a656f879` 集成 Claude44 的 `e0498ee0`，保留图绑定错误和轻量结果描述。S2c 的隔离 Linux 实窗联合验收三次通过。Claude45 接节点能力设计。完整 Desktop 仍运行，后续本地批次待推。 [验收记录](runtime-validation.md)

## 2026-11-09 12:12 UTC · 文件缓存、读取器预检和 CI 隔离

root 以 `23ad9f90` 绑定通用文件解析与原始内容，以 `0a0b0f2f` 前移 HDF5 读取器检查，另以 `d02a5938` 修复 Runtime 矩阵暴露的测试顺序问题。`cd5ba5ae` 集成 Claude43 的 `cfa84a5d` 和 `0ed23ea0`。Claude44 接手 NumPy 缺失诊断。前 Desktop 未结束，新批保留在本地。 [验收记录](runtime-validation.md)

## 2026-11-09 11:45 UTC · Desktop 终态和 F-5 安装对照

`15531049` Desktop 整轮结束。Windows 原生 5/6，CPU 和 Linux 三项通过，macOS 原生失败。root 以 `d2fcfc72` 集成 Claude42 的 `59dee90e`，补单装 NumPy 的隔离对照，记录 HDF5 及 DAT 各入口行为。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 桥接真实回环和图索引输入

root 将 Claude41 的 `4eaf211c` 和 `5fa320ca` 集成为 `1980660f`，独立桥标签 71 项通过。真实原生 Jobs 的独立适配试验两轮通过，回执和截图留在本地证据目录。`ea035adf` 绑定 MuFerro 实际 case 字节，源码和隔离安装各 270 项通过、4 项条件跳过。Claude42 接最小安装 HDF5 证据。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 设备撤权、Jobs 和 Cocoa

root 以 `9f4a9f4d` 修复桥的旧快照读取，以 `322d4084` 集成 Jobs 任务观察和取消作用域，另以 `c634dca5` 加入第二次可见暂停对照。独立 Jobs 46 项、报告 19 项和 Hub/Python 109 项通过。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 目录同步回归与场帧快照

root 用远端精确源复现生成区断言，以 `9c1255a6` 移动说明。 `ff5e615f` 修复 DAT 场帧旧缓存、执行期间更换和 Runtime 缓存改写。已通过源码和隔离安装，Linux 强制结束探针核对临时文件回收。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 图索引完成标记

root 以 `fff8d77a` 修复规划后标记增删造成的缓存错配。两条旧反例复现，修后源码和隔离 wheel 各 97 项通过。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · C++ 入口与图表格核验

root 推送 `15531049`，本地集成 Claude40 为 `85015dc1` 并以 `3ff96c0a` 修复 MuFerro 表格和结果摘要的绑定。已安排 Claude41 完成原生到真实 Hub 的单机验证。Jobs 状态候选保持独立。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · Windows 原生与 Cocoa 首轮诊断

root 核对 `3d2fcea7` Desktop 整轮终态，Windows 原生六项通过。 `2308c680` 加入独立的 Cocoa 首轮可见暂停基线，补关闭前的原生代次和可见性。Linux 相关 19 项通过，目标结果待新头。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · Claude39 集成与 Claude40 分工

root 以 `07f2f2a9` 集成 Hub 停机自然完成两份候选，补阶段形状的旧假绿。Claude40 在独立 worktree 承接 C++ 桥的可选实时任务读取，root 负责平台对照、集成与推送。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuFerro 启动报告与 Cocoa

root 提交 `64c55c4d`，内置图索引从同一份报告字节解析目录并生成摘要，执行时核对报告身份。已复验实际目录名为 `auto`、Runtime 暖缓存改写和 DAT 回退。macOS 隔离暂停已取得脚本回执与原生状态分歧的证据，已安排保持可见的独立对照。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 精确读取和图内容键

root 提交 `dd41ba5e`、`c95a6f26`，分别校验表格解析字节和 HDF5 Runtime 发布身份。 `49169e0e` 将现有 Hub 精确查询开放为桌面桥的可选契约。Claude39 首候选已复验，待入口计数与动作摘要收口。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · X7、HDF5 和传输契约

root 以 `3a7928f8` 集成 Claude38 两个候选，补超时首答复与明确布尔离线状态的反例，派发 Claude39。 `d2bf693b` 拒绝图索引缓存的四种执行期不可验证情况。 `7366d117` 从 PR #53 采纳取消后显式恢复的表项勘误，沿用主线已有重试实现。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 精确修订和空 WGC 会话

root 提交 `862208e6`，覆盖早期检查之后的参数编辑及原生准备重试。root 以 `10ecf59b` 在 Windows 验收捕获器中有限替换空会话，保留原始截止和画面证据门。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 核对整轮终态

root 核对 `bc25f579` 的 Windows PDF 重新准备和 macOS 隐藏验收失败，确认上轮所有作业已终态，进入含 Cocoa 新对照的下一批。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · Cocoa 动作对照和快照摘要

root 在 `41ac8fdf` 以 macOS 测试专用的一次性动作隔离暂停派发变量。 `7eb77822` 将 MuFerro 与 LAMMPS 的最终状态快照绑定各自收集摘要，HDF5 替换反例验证无错误对象、临时文件或快照。Claude38 `e31d1f29` 已审阅，后续候选补首答复和下载前的验收。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 日志端点绑定和冷恢复

root 提交 `0d414c8a`，让桌面引擎分派及 MuFerro 历史入口的每条日志请求沿用冻结身份与节点。四项反例在旧代码读取替换端点，新代码在替换端点 I/O 前拒绝。root 以 `bd5b7e91` 集成 Claude37 `13874a28` 的同传输冷恢复测试。Claude38 已在独立 worktree 开始 D1 X7 自然完成验收。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 收集时校验实际后端

root 以 `5821e025` 采用 Claude36 `1150229f` 的可选端点检查，在桌面桥的产物查询和下载启动实施。传输保留原幂等键和请求签名，已存在的日志按已记录身份判断。Claude37 在独立分支补冷恢复成功验收。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 已登记的 Viewer 输入与观察水位

root 提交 `6cae6312`，用两个旧代码反例证明加入未登记 Polar 帧后旧收集与查看均接受。修复后拒绝新增原生产物。root 以 `5ddcdf17` 集成 Claude35 `eade871d` 的真实 UDP 水位回退测试。另以纯内存后端验证刷新、产物清单和下载间的连接切换，Claude36 接手实施方案。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · Runtime 结果出口与物理替换

root 提交 `8bf08606`，真实 Runtime 在合成求解器通过后因另一必需产物缺失而判失败，CLI 现在退出 3 并保留原报告。root 以 `210036e3` 集成 Claude34 `a7572ba9`。Claude35 已在独立分支接手 F9。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 前轮 Desktop 终态、传输与报告核对

root 核实 `bb4cea9d` 全轮终态，Windows 原生 6/6 和 CPU 1460/1460，macOS 仍有隐藏期失败。 `6dacac40` 从 PR #53 单独接入取消读取锁，经真实下载发布和精确事件测试。 `bdae4432` 拒绝四种合成矛盾成功报告。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 共享工作目录和真实撤权

root 提交 `2bf8d83b`，按实际目录元数据拒绝重定向的工作目录。旧 MuFerro 导入反例创建了项目外的输入文件和项目记录，修复后在复制和索引前拒绝。root 以 `fb4dbd39` 集成 Claude33 `4e176747` 的真实 UDP 撤权并发测试。Claude34 已在独立分支接手 F8b。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 稀疏结果核验与真实热日志

root 提交 `1cd5bbbd`，用 999,999 步案例复现空结果目录核验、连接器和收集预判的高内存失败，恢复结构化错误和已有诊断及文件上限。root 以 `aa3d1890` 集成 Claude32 `19654d4b` 的真实线路热日志回归。Claude33 已在独立 worktree 接手 F10。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO 失败报告和 D1 观察

root 提交 `d9bfc7e1`，复现两个原生终态文件的解码器嵌套失败并恢复结构化错误，同时加入 Windows 原生 junction 回归。root 以 `b27375f2` 集成 Claude31 `bcfff105`。另用隔离 Synthrix 类型与 STK 源码跑两次真实 worker 丢失和只读观察。Claude32 已在独立分支开始 F5c。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO 输入边界和 D1 真实上限

root 提交 `207902bb` 和 `b7272392`。终态证据拒绝布尔值、等值浮点数和重复键。直接上传先核对完整本地清单和合成远端相对路径，再读取输入 TOML 和连接。分别用六个失败反例确认旧缺陷。Claude30 的 `957dc0a2` 经 root 复验，以 `e03a955a` 集成。Claude31 已在独立 worktree 接手 F11b。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 静默隐藏对照和格式 14 真实线路

root 以 `207beb8a` 接入独立 Cocoa 对照，分别对独立视频和 HTML 视频保存同会话的静默窗口、暂停代次、ACK、验证结果和关闭。原有采样和生产报告验收仍各自执行。root 以 `718f3cdf` 集成 Claude29 `ba7a63a4`，两个真实入口均读取格式 14 并按发布契约拒绝回执操作。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · a8872719 Desktop 终态

Windows WebView2 原生六项和证据门全过，Linux 三项与 Windows CPU 成功。macOS 的媒体两项及定位前隐藏对照失败，整轮于 06:57:24Z 终态。Claude28B 的宿主去重已在本地主线验证，Claude29 从 `8e3b5f8e` 在独立 worktree 接手 F15 的真实 WebRTC 验收。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 报告单次点击的暂停派发

root 以 `ab9707df` 集成 Claude28B `1736233d` 的宿主实现，补关窗安全和 Linux 精确必跑门。旧夹具关窗后会再调用一次谓词，红例实测两次；修复后只调用一次，资源会话被撤销。Linux 联合 114 项通过。上一轮 macOS 两项隐藏对照在关闭前持续收到 Playing 回复。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO 启动布局和 D1 实线

本地 `9a357f75` 修复求解器修改布局后仍可让启动器判为成功的问题。重读布局与预检不符时返回 `invalid_result`，保留原布局和空 QoI。同一合成输出可在当前目录独立核验。D1 `7017fb93` 增加严格桥和已认证 UDP WebRTC 的同修订竞争、败方查询、重放及新陈旧写入断言。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 隔离文献热日志夹具

本地 `03bb7fbc` 关闭父进程建库连接，由标准库子进程实际写入未提交页后退出。失败时保留启动、连接、事务和写入阶段。夹具核对热日志头、数据库磁盘标记以及拒绝操作后的原文件字节和模式。对旧头 Windows 失败的阶段仍待重跑确认。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO SDK 样例预检

本地 `bac536c9` 修复样例缺少 `material.toml` 时预检仍通过的问题。启动检查两份文件，材料发布失败后清理由该尝试创建的输入。两个反例在旧代码失败，修复后在源码与 wheel 安装态均通过。Claude28 的只读候选证明鼠标按下和松开分别派发暂停，首轮补丁留在仓库外。后续任务已在同一独立分支启动 Xvfb 验收，生产候选待审。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 密钥扫描下载恢复与协作任务

主线 `a8872719` 首次 Secret scan 在安装器下载收到 HTTP 504，重跑同一提交通过。root 以 `f8d2f79e` 固定备用下载的 release asset ID 和 SHA-256，四个本机安装场景符合预期。Claude28 在独立分支 `claude/report-pause-28` 从 `d7ece658` 接手报告宿主的重复暂停，写入范围限宿主和相应测试。

复核开放的 #53 `c9f13994` 与 #54 `2dd3e4ee`。#53 和主线已验的 worker 退场修复冲突，并扩展恢复契约。#54 新增与 `handoff.md` 大小写冲突的文件，所列五个历史标签已在远端核对。本轮未合入。 [PR #53](https://github.com/sijintech/stk/pull/53) [PR #54](https://github.com/sijintech/stk/pull/54)

## 2026-11-09 UTC · Mac watchdog、Windows Mesa 与 F23

核验远端 `39780e6d` 四份原生媒体 JSON。HTML 定位前对照已证明同一原生会话由暂停 watchdog 关闭，关闭时 ACK 已到且状态核验未通过。`59183cd0` 加入匹配请求的查询、回复、Playing 回复计数和时点。本地 Linux 34 项通过。Windows 原生因固定 Mesa URL 三次 504 退出。`46bab2cf` 新增同一资产的 API 备用路径，实际下载并核对完整字节数和原摘要。

`adc3c591` 让三平台 CPU 验收逐项要求四个文献用例的两种布局，8 项通过、16 个缺项或跳过的反例被拒。Claude27 的 `0375e577` 和 `304b036e` 经审阅合为 `530df743`，F23 同库真实线路通过，路径转义、撤权与原行保留均验证。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · F14 实额线路、Claude26 反例

两个独立 Linux 安装项目分别达 10,000 份与 64 MiB。真实 UDP WebRTC 和严格桥分别写入并保留各自的原回执，随后两端均拒绝超额新写入，原回执可按原 CAS 精确重放。

审阅 Claude26 的基线、四份单块隔离补丁和 JUnit。F5b 两个用例、F5c 一个用例、F23 两个用例在对应行为被改动后按预期失败。F5c 补充对照核对普通库可读和热日志拒绝。下一项 Claude27 补真实线路 F23。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · CP-0 真实续页与回执配额

root 增加 `b326baef`。真实 peer 和本机桥读同库，两种分页到末页后推进修订，原续页均被拒。四文件 181 项与显式安装前缀的另 2 项通过，wheel 定向 1 项通过。结构和记录路径的两份隔离反例分别检出错误续页。

本机安装 store 的独立项目写满 10,000 条和 67,108,864 字节，分别核对容量门、字节越限回滚及重开后的原回执。Claude26 的隔离反例待交付，当前远端 Desktop 尚在运行。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 集成 Claude25 与复验 CP-0 安装态

审阅 `claude/cp0-evidence-matrix-25` 的 `08773ca5`，逐项核对测试名、基线和入口后，以原文件集成到 `db9a7ed8`。root 在设计矩阵补上 F14 的真实 WebRTC 写后溢出，以及三个 Python 版本各 116 项零跳过的 Linux wheel 复验。数量满和字节已耗尽均属写前拒绝，新回执超限属于写后回滚。Claude26 接手 F5b/F5c/F23 的隔离反例。 [设计矩阵](design/cloud-project-service.md)

`49837655` 的前序 Desktop 整轮于 04:46:03Z 终态失败。Windows 原生 6/6 和其余四项平台任务通过，macOS 原组 4/6、定位前对照 0/2。 [Desktop 42558025291](https://github.com/sijintech/stk/actions/runs/42558025291)

## 2026-11-09 UTC · 核验 49837655 的 macOS 失败条目

root 按范围核对四份结果。独立视频原组与对照都在任何定位前出现显式暂停读数回退。HTML 原组在隐藏保持回退，HTML 对照保持通过后只取得一次匹配截图。现有失败记录尚未给出视图关闭来源。新增 `b386929b` 在显式暂停前后分别记录探针的原生暂停快照，并把隐藏关闭对象带到失败日志。Linux 25 项通过。

## 2026-11-09 UTC · 核对 F14 在线路上的拒绝与回执

`1e7bebf2` 用已安装的两个 WebRTC helper、实际互认证的 PeerEndpoint 和严格本地 Bridge，对同一项目施加缩小的字节额度。验证真实协议中的 `invalid_params`、失败 ID 查无回执、原 ID 读取与重放。源码联跑 182 项，另在同头 wheel 安装态通过。隔离导出中，改错 peer 拒绝映射使新用例失败。Claude25 在独立 worktree 对齐既有矩阵。

## 2026-11-09 UTC · 复验已安装文献入口与集成 Claude24

root 核验同头 CI 压缩包并解到独立前缀，以同头 wheel 启动真实 Bridge。中文默认布局从检索到页图、逐字高亮、撤权和恢复阅读均实测，页图与之前源码构建的合成结果字节相同。

Claude `651295d8` 的配额三例以同字节集成到 `5c4723f4`。实装 helper 五文件 249 项通过，隔离导出中的三个故障注入分别触发测试失败。Claude25 已接 CP-0 证据矩阵文档任务。

复核 PR #54。它新增根目录大写 `HANDOFF.md`，当前主线已有小写 `handoff.md`。两者同入会在大小写不敏感的工作树产生路径冲突。当前交接继续使用小写路径，PR 保留审阅状态。[PR #54](https://github.com/sijintech/stk/pull/54)

## 2026-11-09 UTC · 集成 Claude23 的同修订竞争与兼容回归

Claude 的 `d84fe104` 只改 `tests/test_peer_projects.py`，root 校验同字节后集成到 `b8e42c66`。固定候选 30 次竞争均通过，Bridge 3 次、peer 27 次。root 使用已安装 helper 跑五文件 246 项全过，另在隔离源码导出中验证三项人为回归分别被拒。Claude24 已在独立分支接 F14 回执共享配额任务。

## 2026-11-09 UTC · 绑定实际 Cocoa 关闭来源

`133778cd` 在隐藏前从已匹配的原生视图注册观察，首次关闭写入只读测试快照。观察寿命独立于视图，失败证据由同一测试周期保存。Linux 25 项 CPU 回归通过，Cocoa 实机待验。

复核 PR #53 的丢重试竞态。主线 `2de183f9` 已等待原 worker 清理后重新检查并继续同一传输，32 项传输生命周期检查通过。PR 另提议立即持久排队并提前返回，涉及不同的回复及恢复语义，保留为独立审阅项。[PR #53](https://github.com/sijintech/stk/pull/53)

## 2026-11-09 UTC · 记录 fbe4b0cc 的 Desktop 终态

Desktop `42551958437` 全部六个任务均结束。Windows CPU 与原生报告通过，Linux 两项在安装依赖时失败，包安装冒烟跳过，macOS 媒体组失败。同头 Runtime 13 项成功。root 将 `2bf4bd50` GUI 修复与其后原生文献验收记录作为下一次 main 推送。

## 2026-11-09 UTC · 中文原生文献引用页和 macOS 对照结果

root 从 1000×1200 的简体中文默认工作台和合成网格 Viewer 出发，以实际 X11 窗口输入显示完整 PDFium 页图，核对逐字高亮后撤销合成授权。两次独立索引返回相同的 PNG，中文窗口的网格 Viewer 在初始、显示和撤权后逐像素一致。点击数、截图和原操作证据见验收记录。

从同头 macOS 产物定向核对四份失败证据。原组两项在定位后出现时间倒退，两项定位前对照则在首段隐藏暂停保持通过后失去会话。各取得一次匹配隐藏截图，均未尝试重显。Claude 在独立 worktree 复测 CP-0 的 Bridge/peer 同修订竞争，两入口均实际成为过胜方，提交待交付。

## 2026-11-09 UTC · 原生窗口显示真实引用页并撤权

root 在独立桥目录预建合成库，使用固定本地 E5 和 PDFium，通过实际 X11 窗口鼠标操作完成检索、解析引用、显示页图和撤权。页图返回摘要、采样像素和逐字高亮坐标已核验。两次验证的是默认入口与引用页链路，固定布局与分段点击见验收记录。Claude23 的双入口回归仍在独立验证。

## 2026-11-09 UTC · 文献实窗发现 GUI 忽略桥目录

Linux 双实窗首轮发现 GUI 解析 `--state-dir` 后没有传给桥，其中英文窗口遇到默认目录占用。root 在 `2bf4bd50` 接好两条目录参数，守卫解释器复测时仅按准确的隔离目录启动真实桥。四次入口观察均 1 点击、0 滚轮。OpenGL/Vulkan 无头端到端、X11/Wayland 窗口冒烟及 33 项文献 CPU 检查共 37 项通过。固定起点、图像差异和 CI 见验收记录。

Claude 接独立任务 23，范围为已有桥与已授权 peer 的 D1 共同回归。root 负责集成和当前 Desktop 证据。

## 2026-11-09 UTC · 提交 Mac 定位前隐藏对照

root 在 `0f341a07` 集成三处测试与 CI 配置。两种媒体各要求一轮、六张 OS 证据、两次显式准备和两处撤销。原验收继续要求 20 轮。Claude 独立复核源码、证据计数和平台门槛。第二次 CTest 前复制原验收日志，两组 JUnit 和证据目录分别上传。

Linux 本机通过驱动构建、42 项 CPU、关闭探针宏的语法及不注册 Mac 对照的检查。结果与所推精确头见 `root-delivery-20261109-47/closure.json`。

## 2026-11-09 UTC · 集成 Claude 的 CP-0 回归并核对双仓观察

Claude 在独立 worktree 完成热日志任务 20 和授权内容任务 21。root 复核冻结内容、扫描暂存区，分别集成 `a4a07a41`、`bd49fd40`。热日志两套各 110 项通过，一次性副本反转对应路径后分别出现 2 和 1 项预期失败，恢复前像后 3 项通过。授权内容集成前两套各 111 项通过。宽套件两个跳过均需要原生 helper 安装前缀。

Synthrix 双仓观察夹具由独立复核者运行两次，root 另行复现一次。每轮五个真实状态返回 200，一次真实查无返回 404，读取前后数据库、WAL、工作区字节一致。原时间字符串逐字段保留。Mac 原生新证据和前整轮终态见验收记录。

## 2026-11-09 UTC · CP-0 复用回归和云项目设计复审

本地 `994a3b1a` 复用真实桌面桥测试工具和已授权 peer 项目夹具。源码相关四套 143 项，隔离 wheel 两个核心套件 107 项，均零跳过。Claude 在独立 worktree 提交已扫描的 `2f2e6ef7`。root 在 `07c91e85` 集成设计稿，明确线上 get 返回 `{receipt}`、内部返回原回执，以及各 scope 内核对原操作。

下一项已交 Claude，范围为两个现有入口的物理恢复回归。远端 Desktop 42542944337 整轮仍运行，本地提交等待终态。

## 2026-11-09 UTC：核对 315 的完整 Desktop 终态

[Desktop 42536615591](https://github.com/sijintech/stk/actions/runs/42536615591) 于 00:55:35Z 为 failure。Windows 原生最后成功完成，唯一失败任务为 macOS。终态逐项记录于验收文档。CP-0 源码、隔离安装和 Claude 候选 3 的证据已收拢到 `root-delivery-20261109-43/closure.json`。

## 2026-11-09 UTC：复核云端项目边界和原生媒体现象

- root 恢复 AOCI 完整交付并校验 1,220 条，Challenge 10/10。核对 Claude19 两版冻结候选及源码后，将元数据与授权内容、scope、已发布操作集、CP-0 覆盖和云端独立验收五点发回原会话。已观察到 Claude 接续修订。
- 两个受控探针在源码和隔离 wheel 重现相同分页、回执和恢复事实。旧稿中对 peer 禁止热日志恢复的表述须按入口区分。项目回执/peer 基线源码、安装态各 106 项通过。
- `315620f9` 的 Runtime 13 项成功，Desktop macOS 原生 4/6，Windows CPU 已通过，Windows 原生运行。两视频隐藏保持失败的最新差量留在运行验收。诊断 `749076d9` 继续等待前轮整轮终态。

## 2026-11-09 UTC：关联 Mac 失败产物并记录暂停阶段

- root 核验 4d Desktop 的 Mac 两份失败 JSON：有界 ZIP 成员读取，CRC、尺寸、各自 SHA 和关联报告八文件清单吻合。两份失败均 cycle1/nav1，原日志、fresh play 和失败快照同一会话；AX 前显式暂停已各回退约84ms并过容差，隐藏时刻精确回到最后 AX 位置，不足以判根因。
- 749076d9 在三个文件增加测试宏内的原生暂停快照，不增加 WebKit 调用、不改 DOM 脚本、原 ACK、1秒核验或任何判据。捕获隐藏前、首次 paused 及最新探针两端的代次；有效原生来源但 DOM 求值失败仍保回调阶段。独立复核宏关保留源码逐字节一致；历史失败样本加入最大新字段后约3460/3391字节，低于8192上限，非新原生实测。
- Linux 最终原生驱动目标重编及宏关语法检查通过；既有资源、探针、宿主三组42项零失败/skip、0.46s。Cocoa 编译和实际播放未在本机执行。315前整轮Desktop仍live，本地749待推；Runtime12成功+Win3.11运行，Docs/Secret成功，不将旧头CI冒充749验证。
- 实际Claude18独立留档5a256190；同一会话在claude/cloud-projects-design-19推进单文档源码比较，R2/R3未选。原计划与待决保留；证据和最终Git状态见root-delivery-20261108-40/closure.json，旧WIP保留。

## 2026-11-08 UTC：集成 Claude 上传第四版与独立安装验收

- root选择集成六路径第四版为397a464d。侧记发布仅用原子无覆盖link；硬链接不支持拒绝且清自己的临时文件，不采用或覆写竞态出现的身份。保留第三版及其发布红例，最终作者红例4失败/2控制通过、修后全绿；原导入意图更新仍在自己的租约内。
- 作者基线a0九模块225通过；root已提交2b归档加六SHA冻结覆盖及共同6c修复，234通过、零skip、95.56s。离线wheel SHA03c2bb32…，新非系统包环境无科学/GUI/模型依赖，从无产品源码测试床以-I运行232通过、2明确排除、零skip、91.63s；三产品SHA及父导入来源前后相等，自有活后代观察0。源验证和安装验证分别留证，未声称所有子服务完整module图。
- 独立侧记发布12场景、读取11组通过，模块除publish外与第三版逐字节相同。作者依赖531旧版、root54d含6c，不能混用结果。根证据为d1-hub-upload-cli-20261108-21/root/author-candidate4-20261108-38/及candidate4-installed-20261108-38/。
- 4d整个Desktop23:27:29Z failure且六job终态；MacCPU1516/1516、Metal254/254，原生4/6。视频的新有界快照已抓到隐藏后回退时间，两个显式暂停均过，仍不认定根因或调门；Win原生6/6、1038.93s，其余平台job与Runtime13/Docs/Secret成功。终态记入验收后才推下一批；这些旧头CI不验证6c/397。
- 原八项及D1–D5、MuPRO待决、HDF5需DAT、PET新专项后置和P1/P2未生效保持。root独占集成推送，Claude保独立worktree，既有WIP未整份暂存。最终提交/push/新CI见root-delivery-20261108-39/closure.json。

## 2026-11-08 UTC：Runtime 全绿，上传候选通过联合回归后补无覆盖发布

4d的Runtime42531177232已22:57:35Z success且13job全成功，Docs部署/Secret成功；完整Desktop仍live，root本地6c481e59/13337fde暂不push。候选3作者219项零skip/97.41s，root133提交归档加六SHA覆盖的独立源码228项零skip/95.20s，差9为共同后端新回归。root初次遗漏随附examples/runtime造成2例部署失败，226通过；补同133的样例后完整重跑通过，无产品源变化，初稿保留。

76个worker反例及11组读取边界通过后，最终发布检查发现SidecarHolder在link不支持时先exists再replace可覆盖新出现侧记；前提为不参与租约的写入者，未证明两个合规worker并发。已交实际Claude第四版修订卡并观察开始修改，保留candidate3六SHA/diff/旧红绿与离线wheel。尚未接受、集成或安装此候选。完整证据和CI见 `root-delivery-20261108-37/closure.json`；原路线/待决及旧WIP保留。


## 2026-11-08 UTC：共同传输恢复跳过坏状态，上传第三版继续修订

root以6c481e59本地提交TransferManager._recover的一行字符串类型守卫及九例启动/恢复/GC回归。实际坏数组/对象状态在旧源码造成8个TypeError，控制例通过；新源码五模块67通过、零skip、35.54s，独立固定副本及当前两SHA终审无实质发现。坏日志字节、mtime与锁保留，正常任务仍以原key/request/endpoint标interrupted，构造不派发或联系后端；原显式resume与旧FINAL清理控制保留。不扩大恢复执行或身份权限。暂存扫描零发现，尚未push，等待4d整个Desktop42531177137终态。

上一批4d6426fb已推远端，Docs部署/Secret成功，Runtime与Desktop运行中。实际Claude早期b3经root独立52个worker场景发现两项残留，已在原会话按修订卡继续六路径修改；共享坏日志路径由root修复，早期快照非最终候选或安装验收。完整证据和当前状态见 `transfer-startup-20261108-36/closure.json`；原路线、MuPRO待决、PET后置和旧WIP保留。


## 2026-11-08 UTC：完整 Desktop 终态与本机修复推送收尾

ae6的整个Desktop42523800365已22:21:50Z completed/failure，六job全部终态；Windows原生128875254641成功，先前Mac/Linux/WindowsCPU失败仍照实保留。root重新核对9b338172四项源码提交及d0f749bf文档提交，21源码和五测试XML均与冻结证据一致，未为推送重复跑真实模型。前整轮等待门满足，补齐34/closure.json并记录终态后推送，新头平台结果另验。

真实文献CPU界面2/2、默认33/33、材料22/22、布局8/8均零skip；不能代目标OS/GPU或科学有效性。实际Claude同会话独立六路径继续第三版，早期v3只读快照分派worker与读取预算复核，不作作者最终交付或安装验收。原八项/D1–D5、MuPRO待决、HDF5仍需DAT和PET后置保持；最终交付见35/closure.json，原WIP保留。


## 2026-11-08 UTC：真实 PDFium/E5 文献 UI 与桌面回归

本地提交99a25c36（八份布局金样仅顶栏变化）、9779efea（显式/隐藏暂停实际诊断）、fe2cdb4b（默认关闭的真实文献UI验收）和9b338172（材料测试等待发布/激活ACK）。暂存扫描均使用原.gitleaks.toml、零发现；本批未push，前ae6整个Desktop42523800365仍live。Runtime13job、Docs实际部署及Secret成功；各平台旧头失败与当前本机修复分别记录于运行验收。

真实自有PDF与固定PDFium5.14.0/E5通过真实Bridge，从正常鼠标键盘完成导入、索引、检索模型选择、dense/search、引用与两次页图渲染/纹理释放、撤权和只读历史。英文1600×1100与中文1000×1200/scale1各37点击/零滚轮，2/2零skip/62.362s（case耗时合计），21项相关源码前后摘要一致；Viewer、相机和精确隐藏稿保持。默认33/33、材料22/22和布局8/8通过；缺资产受控反例失败不skip。CPU采用实际PNG/高亮仍非目标OS/GPU呈现或科研检索质量。

材料22项正常通过；实际锁内0.65s注入的两个旧目标各Busy+null304失败，新目标各1/1零skip，31项共享链接输入不变、无残留。初次外部注入遗漏epoch参数的试跑无效且排除；原CI具体初始/最终读取落点未证明。媒体最终源码主目标和宏关语法通过，95提取断言及独立源码审阅通过，未放宽期限/唯一slider/像素/20轮门；Mac两视频仍需新头真实证据。

实际Claude继续同会话独立第三版上传CLI：开发模块62通过，旧candidate2的14条边界红例后恢复WIP；根取得早期不可变六文件快照供独立审阅，未接受、集成或安装态验收。原八项/D1–D5与MuPRO未决不变，PET新专项后置，PR53/54旧头无关。最终交付见 `root-delivery-20261108-34/closure.json`；现行索引收尾，保留旧WIP。


## 2026-11-08 UTC：原生文献入口和三项生命周期修正已本地验证

root新增文献编辑器、导航/翻译和图像覆盖API；前四成员聚合兼容，高亮用同一fit/pan/zoom矩形并裁剪、不改PNG。独立审阅抓到旧批准闭包改投新review、同Client换进程未泵监听时旧动作可派发、库/桥失效丢TextEdit输入，已分别冻结批准参数、核PID/spawn、分离本地文字guard；隐藏布局订阅停观察并清瞬态。重复render先释放旧纹理，历史只读摘要分页并同步清理。

最新构建成功；完整文献33/33零skip、33.783s，UI核心131/131、App/AppStore19/19通过。初轮新UI8/9，唯一失败是中文点击定位光标后测试误按末尾插入，改为明确End后全过；不把它说成产品丢稿。固定默认en1600×1100、zh_CN1000×1200/scale1一次点击进入、文献RPC为0并保Viewer及隐藏稿；重复复核导入13点击/零滚轮。生命周期注入另计。真实E5/页图全链UI、目标OS与最终推送未完成。

c281 Runtime整轮成功；新Mac原生两视频已越过AX/Tab但隐藏暂停失败，失败瞬间状态未保存，根因待证；整个Desktop已20:59:15Z failure终态，六job均结束且Windows原生job成功，推送等待门满足。Claude18独立修订、RED结束待先恢复candidate2，未接受或集成新候选。源码已本地提交5c0b85d3、远端仍c281620d，原WIP保留，证据native-literature-ui-20261108-29/与root-delivery-20261108-31/。

## 2026-11-08 UTC：窄区域tab与AX同链证明候选

247cca3b只改原生报告验收的tab导航。612e HTML-video实际将a3从401缩到286，而生产header在300 UI像素以下不建独立tabs、把tab放在区域菜单尾部；旧前置检查因此误拒。现在独立tabs存在时仍要求可见/启用，仅不存在时经既有菜单和End/Up/Enter正常事件选择。外部真实CPU AppFixture固定1024×656、en/scale1复现宽度切换，往返2点击/5按键/0滚轮，Viewer/payload/相机及精确未保存Python稿保留；native-window重建成功。CPU未还原全部原生媒体高度/OS呈现。

70a301f4只改四个AX测试/协议/helper文件。实际Mac数值链为Window0→Group6→Group7→ScrollArea8→WebArea9→Group10→Group11，旧规则在Slider查询前拒绝WA位于inner祖先。新候选只接受可比较祖先关系；完整WA中所有时间/几何/启用/同窗匹配Slider仍须恰一，再证明真实选中Slider位于WA与inner之下，父链进入原1632B/v3数值回执。Above成功缺Slider证明、侧支或多个候选仍拒，Below旧合法形状兼容；accepted原函数、2s/8s/Provider4、真实WK/会话代次、DOM、OS像素和20轮门均保持。原关系谓词恢复后受控红例失败，三份故意破坏的新候选分别拒绝；不是三项历史缺陷声明。root构建和一个CPU CTest内五组通过/4.25s，实际暂存17066B扫描0；新helper尚未Apple编译，真实Slider是否在inner下仍未知。

612e整个Desktop42509570653已19:32:03Z failure终态，WindowsCPU1447/1447、原生6/6成功，Mac原生4/6失败；旧Windows同名智能体测试本轮过不归功于尚未包含的13035ccc。Runtime12job成功/3.14失败，Docs部署和Secret成功。已记终态后推进本批push，最终见root-delivery-20261108-28/closure.json。Claude18独立六路径仍在实现，未计交付；原路线与MuPRO缺口不变，P1/P2未启用，旧WIP保留。


## 2026-11-08 UTC：测试观察修正与上传实施分工

299e756b让local-model测试等同一次观察的failed、exited详情和autostart=false，原15s预算不变；公开假服务使用确定性测试凭据。0.3s监督发布延迟下旧KeyError、新通过，模块17项零skip/10.23s；无产品模型配置变化。

13035ccc把智能体Python夹具日志的open/write/close串行化并仅解析完整JSONL行；原13个测试正文不变。受控Windows CRT seek/write语义重现长短行覆盖后首字符d，另证未终止尾行；完整坏JSON仍拒绝。root构建成功，13/13零skip/6.74s；未取得原CI日志文件或新Windows运行，不认定唯一历史根因，旧done误读猜想无源码依据。

fdbefeac让settled在确认job移除后重读SQLite。真实executor/SQLite、受控计算旧返回running而持久状态succeeded，新返回succeeded，归档42、一次worker；Python3.14.4模块36通过/零skip/6.27s，真实payload0.713s，原20s不变。生产执行器/worker文件无改动，未找到Bridge.shutdown参与此测试路径。

实际Claude17提交443c9fa7；root经sidecar/API/源变更与GC校正以a0f77fa3纳入实施设计，尚非产品能力。干净peer安全新建claude/hub-upload-cli-18后开始六路径实现，旧support引用保留；root独占集成、构建和push。612e Runtime已失败、Desktop整轮仍live，Mac两视频未修复；终态前不push本批。提案2aea已在远端但P1/P2未启用。原路线及待决保持，证据和最终状态见root-delivery-20261108-25/closure.json，保WIP。


## 2026-11-08 UTC：审阅提案并修复Bridge传输关闭生命周期

root以2aea4a95将实际Claude1a5提案修订合入本地main，纠正字符比例/成本、主线提交计法和worktree边界，保留交付与恢复约束；P1/P2未启用、AGENTS未改。7bfae902修复已复现的关桥早释目录锁：关闭传输准入，计数已接收调用与worker，stop仍有界，真实线程退出后才释放。旧源码新9例8失败/1通过，新七模块137通过、零skip、46.43s；完整暂存15351B扫描0。

0e0a1246加入AX数值拓扑及FD3非阻塞进度；root审阅发现合法末帧丢失误拒，外部旧红新绿后修正，accepted函数逐字未变。root两目标构建及CPU4.24s通过，完整暂存75575B扫描0；尚未Apple编译/真实AX和20轮，不宣布视频修好。未交付产品UI变更或新增点击改善。

bcec Runtime42504540440整轮failure：其余12job成功，3.14为local-model测试KeyError/error（6010通过/153skip/842.13s）。Desktop42504540481已于18:16:12Z整轮failure终态：MacCPU1503/1503、Metal254/254，原生4/6；WindowsCPU1446/1447，NativeAgentRuns解析done前缀失败，原生6/6成功、1341.53s。Docs/Secret成功，推送等待门已满足。实际Claude17继续独立设计修订，不实施或提交。原路线及真实MuPRO缺口保留；外部root-delivery-20261108-24/closure.json保存本批状态和收尾，原WIP不覆盖。

## 2026-11-08 UTC：集成Claude16并补联邦测试等待

实际Claude16交8ae2088d（父1a5dc3ad），root只集成cli.py、test_runtime_hub_cli.py、hub.md为2fcc7251。父提交的独立AOCI使用提案保留在Claude分支，未入main或生效。新增Hub工作区入口沿用原动作身份和权限；审阅抓到全局wait=0使旧节点读取无法完成的P2，改为仅写操作临时零等待并finally恢复。真实HubBackend排队读取反例一POST、同ID三次poll取得结果，失败/超时不返回文件；独立23项纯检查通过，作者恢复旧行为的四例全部失败。

作者100/0skip/54.752s；root集成42/0skip/15.716s；独立最小安装42/0skip/17.224s，wheel11bacdc7…及9实际父模块来源/摘要匹配。原三文件暂存32723字节SHAf6cce7e5…扫描0发现。root f052f06b只补测试owner信息采用等待，24项18.464s全过；同0.5s延迟旧30.671s失败、新2.769s通过，不宣布Mac动态根因已证实。

691 Desktop42495020086已16:29:30Z整轮failure终态：Linux三成功，WindowsCPU1447/1447及原生6/6成功；Mac1502/1503、Metal跳过、原生4/6。Runtime13job、Docs部署、Secret成功。新代码仍待新头CI；691不含c0ff，PDF通过不证旧根因。root继续main/构建/公共后端/原生/集成/交付，实际Claude接17独立journal/上传恢复设计，唯一文档候选不实施产品。原八项/D1-D5和真实MuPRO缺口保留，旧WIP受保护；本批closure记录最终推送。

## 2026-11-08 UTC：集成真实Bridge上传恢复并派发Claude16

Claude15 `4d02ea3a03b8583d13bd8ab1a0a4a7fb8f771a53` 已仅三路径选择集成为 main `2cc40a0ddbe789770a43cb06c1f0f758ae48e524`，尚未push；root原生等待候选c0ff亦未push。远端691整个Desktop42495020086在16:22Z附近仍运行，须整轮终态后推送。Runtime42495020053已13job全绿，Docs/Secret成功；WindowsCPU成功，Windows原生128786216358仍live。Mac CPU1502/1503通过、531.86s，唯一失败为联邦ChineseNarrow1x的federation_register未解锁；Metal跳过。原生4/6，两视频仍失败，不能沿用旧7ef CPU/Metal结果。

真实Hub先收首1MiB、Bridge原journal仍bytes_done=0时SIGKILL/reap，仅重开同profile/state/journal，保持其他四服务原PID/创建时间；原transfer/key/request/upload_session恢复，首新块1048576、下一块2097152，总2621464字节。完成后原workspace.import仍待人工批准，批准前零文件/任务，之后精确大小/SHA一致；无Task提交，不声称程序消费了输入。驱动写后及启动前SHA核验，缺证明和清理失败独立禁通过。

最终script38e42c02…/testc56f8803…；README仅两处说明修正。Claude联合282项零skip通过/74.18s，最终source04/installed05各10断言通过；root主线新模块67项零skip通过/9.814s。root独立最小安装态以同一script运行10/10，场景5.722266164s、含清理6.579574818s，17模块来源探针SHA与root一致、无GUI/科学可选依赖且无残留；探针不等逐服务完整sys.modules采集。独立18纯反例无实质发现，提前SIGTERM和服务session丢失后从0重传真实红例正确失败。暂存75410字节、SHA0a266fba…，gitleaks零发现。证据 `d1-upload-restart-20261108-19/root/`、`claude/`。单Linux主机、一个故障点，不代网络分区/R3/许可求解或科学验证。

root继续负责main、公共后端/契约、桌面问题、共享构建、审查集成、四状态文档/AOCI和推送。实际Claude在独立stk-claude/claude/support接CL-D1-HUB-WORKSPACES-16，基线4d02，仅cli.py、test_runtime_hub_cli.py、docs/hub.md：为Hub补工作区create/list/files及原action观察，复用既有后端，先交固定候选供审阅；本片不接Hub上传、不自授desktop、不改协议或R2/R3。当前尚未交付。任务卡 `d1-hub-workspaces-20261108-20/root/claude-task16.txt`。

继续D1剩余合同/故障和云端项目、原生文献实际点击、Synthrix正常装配及D2-D5与原八项；MuPRO/MuFerro、插件自定格式/MuPRO HDF5、有限S2c方向已确认。真实执行主机/SDK/许可/小算例、扫描数值及分析修改提案持久形式仍待输入，HDF5仍需DAT完成验证；PET新专项后置。PR53/54实际头仍c9f13994/2dd3e4ee，不合无关旧差异。原四文档和AOCI WIP保留，正式新交付/CI/治理见本批closure。


## 2026-11-08 UTC：691新头Runtime整轮已通过

691f3f12的Runtime42495020053于15:45:20Z completed/success，13个job全过；Windows3.11/3.12各5098通过、254skip、580未选，分别701.01/900.42s，旧SIGKILL收集错误已获得新头Windows验证。Linux完整矩阵和文献/peer-macos/独立联邦等亦成功；不把Windows排除server组当该组验收。Docs/Secret已成功；整个Desktop42495020086仍live，Mac已目标编译完成并进入CPU测试，WindowsCPU仍构建，原生待出。root c0ff1ac7/7f7a40d3本地未push，仍须等前整个Desktop终态；最新交付见windows-pdf-ci-42487388780/review/closure.json。下方较早“Runtime仍live”为当时快照，保原WIP。


## 2026-11-08 UTC：报告原生等待不依赖额外OS事件

root提交c0ff1ac76617769c9d266304f59d856a7485ca56，仅reports_native_window.cc、新wait helper及原AX CPU测试。旧7ef Windows PDF result/3PNG经精确Range与CRC核验：12完整轮/103图，第13轮closed后无完成捕获，不能当页一像素不匹配。WGC后台frame pool无UI wake，真正GHOST等待循环支持改为非阻塞pump候选；未声称已在Windows复现。

原绝对deadline前后核predicate、pump后核时，统一1ms yield含独立AX轮询；原45s/8s、OS像素与20轮门保留，慢同步调用不抢占。两个target构建成功，55/55零skip2.73s；独立C++20/-Wall/-Wextra/-Werror六探针、固定三路径终审0发现，SHA稳定，暂存6098字节gitleaks0。前691整轮Desktop仍live，未push，不借旧CI证明新候选。

实际Claude15 source trial-03的10断言通过/5.592835773s、清理无残留，提前非SIGKILL退出红例被拒；固定最终字节、installed与交付尚未完成。root保main/构建/认知独占；旧WIP与原路线保持。


## 2026-11-08 UTC：peer发布读取诊断与AX拓扑证明候选

- 实际Claude14 b510da04由root精确选择集成a1904447，仅peer_test.cc；JSON关闭临时文件后原子发布，读取区分missing/unreadable/empty/invalid/complete，永久坏JSON立即失败，原30s预算泵UI。root18/18绿、零skip、9045ms，暂存13370字节gitleaks0；不推定Windows根因。
- AX源码79ae0adf7bfe7734a49f33fd571ecdd4e7b650bd保raw匹配数，纯数值完整树选择器证明单祖先链、外层范围唯一WebArea/内层支配；helper逐wrapper核同窗，父端核链、节点数和depth，旧wire拒绝。独立审阅补不可能深度反例，未改产品权限/截止或媒体门；Apple仍待新CI。
- 前Desktop42487388780于15:04:55Z整轮failure，等待门满足：Mac编译/CPU/Metal过、原生4/6；WindowsCPU1446/1446过、原生5/6，PDF cycle13 reprepared-page1像素timeout，两视频过。Docs/Secret成功，Runtime旧两Windows收集错误已本地补修，待新头验。
- Claude独立树三基线同步至59f082db后接CL-D1-UPLOAD-RESTART-15，限定三个新样例/测试路径，尚未交付；root维护全局状态、AOCI和推送。固定字节/测试与最终发布见mac-ax-ci-42487388780/review/closure.json。

最终两目标构建成功，相关55/55、零skip、2.76s；depth独立编译旧红新绿（14层边界通过、15层伪证明拒绝），暂存24314字节gitleaks0。候选1独立审阅发现depth缺口，候选2由root修复复核，未称独立终审通过。


## 2026-11-08 UTC：D1输入/撤权样例及singleton跨平台收集修正

源码 main `4399f2fa6dfaba941922d2808ca023eba3766105` 已本地提交，尚未push；远端仍 `7ef5d21e`。前整个Desktop42487388780仍运行，终态前不推送。原四文档WIP和AOCI预存改动保留，最终交付状态见 `d1-input-transfer-20261108-18/root/closure.json` 与实际Git。

新增真实两部署输入/撤权样例：同一1048599字节公开输入，部分会话1MiB后重开同ID/offset，完成SHA校验；B blob必须经原workspace.import人工批准才导入，完整TaskSpec另经批准。两边固定程序读取冻结输入并输出相同SHA，原Runtime清单、各一task/run/marker、program和worker清扫前退出。B仅撤本次desktop设备，热/冷客户端后续11类请求均401，节点仍在线、无新增action，原Runtime任务保持。不是断网、桥日志恢复、项目/用户授权、在途请求中断、已交付字节召回或pending上传字节不变证明。

最终新模块及singleton联合28通过、零skip、14.81s；最小非system-site-packages包以-I installed复验11断言通过，场景6.045540141s、含清理8.1s，实际site-packages来源/模块SHA一致、清理干净。产品Python到7ef无差异，沿用已重建包，不把旧harness试跑当新字节；当前script46f83b43…/helpercf2b13c9…。独立终审关闭A额外queued任务假绿和迟到terminal延长局部截止，反例已入测试。暂存25040字节gitleaks零发现。

7ef的Runtime42487388719于14:14:50Z整轮failure：11job成功、两Windows矩阵因新增Linux专用singleton测试在收集阶段引用不存在的SIGKILL而报错，未执行该矩阵测试。本提交改为函数体解析信号名称，缺SIGKILL的模块红绿反例及Linux原11项通过/5.73s；仍待新Windows CI。Docs42487388755完整部署成功，Secret42487388666成功。Desktop当前Linux三job成功，Mac已越过编译/CPU阶段、WindowsCPU运行，原生最终结果待出；不能继承旧头平台验收。

root继续独占main、公共后端/契约、共享构建、审阅集成、四状态文档、认知与推送。实际Claude仍在独立stk-claude/claude/support做CL-NATIVE-PEER-14，只改peer_test.cc，候选尚未集成或目标OS验收；具体Windows空JSON根因仍未知。后续D1其余合同/故障与云端项目、文献实际点击、Synthrix正常装配、D2-D5和原八项保持；PET新专项后置。MuPRO/MuFerro、插件原生格式/MuPRO HDF5及有限S2c按已确认方向推进，真实许可/主机/小算例、扫描数值与提案持久形式仍待输入；HDF5仍需DAT完成验证。

## 2026-11-08 UTC：时间/MIME 证据、Hub 单实例和原 action 重启恢复

root提交b517554a、2c9729b8、c5d8e503，并将实际Claude13的755212b2三路径选择集成ddd7d7c2。本节未push、远端fd394e46，最终交付见 `d1-hub-restart-20261108-12/root-integration/closure.json`；四文档旧WIP及AOCI预存资产不连带提交。

正常双部署补五个时间字段按自身Runtime精确保真、created_at同任务重放不变和固定text/plain产物；不比较两部署墙钟或收紧未执行任务缺省/null。独立审阅抓到错误MIME原文导出，修后固定错误并用run级五文件反例关闭。原155项绿及12项安装绿另存；最终八文件271通过、零skip、74.57s，实际新CLI和helper稳定。

Hub正式serve加真实状态目录control.lock生命周期，pair不共锁。旧代码真实7红；修后相关49绿/13.48s，独立14纯mock无阻断。覆盖alias/异端口、TERM/KILL后同inode重启、独立目录、pair并行、配置/构造/内部BlockingIOError与退出释放。早期过短低熵令牌夹具被既有校验挡住，单独保留，不作并发证据；直接factory多worker和分布式锁不在保证内。

Claude13初稿驱动摘要错误/缺失仍ok的P2经真实run级反例复现；修后真实文件写后/启动前核SHA，H0和独立run门均必需，篡改/删除零spawn。独立9+2+3+43项纯探针关闭；作者157项联合和source/installed11断言，root最终271项及新最小包11断言通过。两delivery、一次Runtime.submit、一task/run/marker，恢复为节点缓存，原program/worker显式取消后清扫前退出；不冒称第二次Runtime重放、网络分区或科学通过。

root离线重建c5产品归档包，新CLI217e35e3…，ddd到c5产品目录零diff；最小-I安装正常12/断连10/Hub重启11全过，场景11.022404007/23.604974931/7.680591277s，Hub含清理8.607716267s，无残留。未装GUI/科学包。证据与来源见运行验收。

fd整个Runtime13job、Docs实际部署及Secret成功；Desktop已于13:51:08Z失败终态，Linux三项成功。Mac Build的AXValue旧常量类型错误两行已补2c9729b8，未Apple编译；WindowsCPU1445/1446通过、1个PeerMouse空JSON失败/902.99s，Windows原生文档6/6通过/1304.12s；前整轮等待门满足，新本地字节仍待新CI。PR53/54无新头。实际Claude13已交并接CL-NATIVE-PEER-14，仅修peer_test.cc夹具、待固定候选审阅；原八项/D1-D5、文献点击/Synthrix及真实MuPRO/待决不缩减，PET新专项后置。

## 2026-11-08 UTC：固定原进程断连验收与公共 AX client 集成

root提交原生 `d2f6262262e713d4bf1e986fb15d03a5fea70b59`，来自独立候选c16170c8/0b4b53c0的12文件，随后选择集成Claude12最终a215972d为 `688db5a0889f301f339150f836de8caa3cd1abea` 三文件。当前未push，远端b3，后续交付见本批closure；旧WIP及AOCI资产未连带提交。
原生测试仅四次完整空provider后一次公共AX只读helper，严格numeric协议、真实父窗/WKWebView/资源/导航/布局代次及新DOM绑定。子进程2s和seek8s均为原绝对截止，失效/关闭取消并在UI泵中drain/reap；唯一slider、原生输入和原DOM/OS像素20轮门不改。两次固定源码审阅无新增实质问题，root主线两目标构建成功、43项CPU零skip通过/2.85s，12输入SHA稳定；106792字节暂存扫描零发现。没有Apple SDK或真实AX运行，不能称Mac问题修复；旧同步AppKit调用仅能拒晚结果。
断连初稿两P2经Claude修复、独立五个真实sleeper场景和旧反例验证关闭，八owned进程全回收。root最终source联合90项通过/43.90s、最小installed-I 10断言通过（23.544913289s，含清理24.654371985s），原program/worker跨阶段一致且显式取消后清扫前退出，一任务/run/marker，清理无残留。最终harness8d75922f…与helperc1235e8c…，已装包58到当前产品目录零diff；暂存三路径扫描零发现。单Linux节点SIGKILL不代网络分区、长故障或Hub重启。
b3整个Runtime13job于12:26:56Z success、Docs完整部署12:13:16Z success、Secret12:10:58Z success；无Desktop触发。最近适用整轮Desktop304于11:15:29Z失败终态，推送等待门满足。PR53/54无新头，不合无关旧差异。
Claude已接13，仅新增Hub丢首次结果/同状态重启样例、说明和测试，尚未交付；保真实Node缓存，恢复原action与再次Runtime提交须分别陈述。root统一共享构建/状态/认知及发布，原八项/D1-D5/文献点击/Synthrix入口及待决不缩减；真实MuPRO和科学有效性仍缺资产。证据见运行验收。

## 2026-11-08 UTC：固定文档依赖的有界下载与独立故障复核

root源码 `9053ea5c394060252e936a121229668d6e185594` 本地提交，尚未push。文档CI新增同官方release的固定libvips8.14.5准备：每次120秒、至多两次重试、先核上游SHA-512再移动正式包，半文件退出清理；sharp继续自身完整性核验，冻结锁/搜索产物门保留。真实步骤下载6,763,082字节通过，两失败反例均不发布或残留；暂存2772字节扫描零发现。
隔离精确Node22.23.3/pnpm8.15.9：安装18.603s；首次本地PATH无npx使搜索门失败，原日志保留。补齐本地npm/npx后构建14.494s，38页、37搜索页/两语言，锁SHA不变，跟踪文档输入绑定9053树；并未发布站点。证据 `docs-libvips-20261108-11/root/`。
599整个Runtime42477006366于12:00:18Z成功，13job全过，三Linux含41项新D1测试；Windows5098通过254skip/395未选，未验该Linux服务组。Secret成功，Docs两attempt仍libvips超时、构建未跑，未第三次重试。599不命中Desktop过滤，最近整轮304失败终态不等当前目标OS证明。
Claude12初稿独立审阅出现两P2：已退出Node也可十断言全绿、worker.json替换后原worker仍活亦可全绿；均无服务复现，root停止接收并要求同三路径修正及冻结字节复验。原生辅助交AX候选和绝对时限补丁，仍独立审核、未目标Mac验收。PR53/54未变，保旧WIP/原八项和待决；真实MuPRO与科学有效性不借合成证明。最终交付见本批closure。

## 2026-11-08 UTC：D1 双部署样例与严格验收边界

Claude独立提交 `6cc2d39e0f57b15426462897edfb943b2df01505`，root选择集成main `4b33e131`；三路径为offline.py、README和test_backend_parity.py，没有新增产品CLI或业务契约。修正空产物假绿、来源混用、marker/PID、清理和错误导出；root最后复现config.exists异常跳过清理、实际1.04s/预算1s被舍入为通过，两红例先失败，`6ae96999` 修后联合61通过/零skip、23.35s。
root独立最小extras环境-I installed跑最终真实Runtime A及Hub/Node/Runtime B，9断言通过，总12.1s。harness c1235e8c…单独绑定；已装包来自58，产品suan/toolkits/pyproject到6ae无差异；来源base/模块SHA一致，实际进程/marker、下载字节和清理已核。不称整个D1矩阵、云端项目、目标OS或真实求解器通过。
304的整个Runtime42472416392 success：三Linux/两Windows通用矩阵零失败，旧24项前提问题关闭；13job全成功。整个Desktop42472416447于11:15:29Z failure：Linux GPU成功，其余三个直接失败为googletest收流56、ninja503及fmt HTTP2下载92；两下游skip，没有新的目标原生证明。Docs/Secret各重试一次仍失败，不绕下载校验。
Claude已接12任务，只开发节点断线/原任务恢复观察；另一Codex在stk-native-ax开发Mac公共AX测试候选，非Claude且未目标机验收。root收口共享构建、认知与推送；四文档旧WIP保留。当前源码尚未push，最终交付见 `d1-parity-20261108-08/root/parity-integration/closure.json`，原八项/待决仍保留。

## 2026-11-08 UTC：陈旧 HDF5 红绿例与完整回归收尾

源码 `58fbd03ee5976af90a3a083dcb24cf0aeed4994f` 已本地提交；本节成文时未push。旧run.h5被CLI上传及制造求解器成功运行的两反例已修：可选输出仅加入陈旧预检，RUN_OUTPUTS/DAT验证不变，其他HDF5名不被该规则保留。定向2红1绿变3绿，MuPRO联合90通过/2真实资产跳过。D1文档纠正超限拒绝和批准消费前后手工启动观察。
ec32 Runtime五通用矩阵同24失败，本地24红/1绿复现；只更新两个旧AGENT_LEVELS断言和22个传输桩的端点身份，联合91通过、13.76s。完整非desktop/perf回归退出0：5698通过、151跳过、4未选、964.35s，850跟踪输入SHA未变；15个既有离屏SIG11及未供可选/真实资产和目标OS跳过单列，不冒称能力验收。
root在非system-site-packages纯净Python3.12先装ec32，再独立构建安装58归档；安装态后端/服务无GUI/科学模块，58 Hub CLI20通过、8.54s。Claude的独立双部署初稿source/installed各9断言通过，最终模块仍补预期产物、启动计数、预算/清理失败反例，未集成。
ec32整个Desktop于10:22:29Z终态failure：Mac CPU1501/Metal254通过、原生4/6，两视频仍同AX slider失败；三job依赖504、两下游skip。Docs/Secret各重试仍504；不削弱验收或把下载错当产品错。Mac公共AX外部原型未编译/接线，未称修复。PR53/54未变，旧WIP保留。实际交付/推送/治理见 `d1-parity-20261108-08/root/closure.json`。

## 2026-11-08 UTC：S2c MuPRO 工具、桌面批准与 Runtime 目标绑定

本地源码提交 `b6b92d911860b52eda755679f4cc2094a39ba24d`，29文件。集成Claude09内部准备模块与独立原生卡片，root接资源选择/工具级别/完整桥接、单次消费与派发、端点/传输恢复绑定及发布扩展；不升项目格式，不重写旧会话头。
审阅发现并修复长行视觉裁剪、目标配置失败后切换会话放行继续、混合 frozen step 回放、decline缺ok、历史状态误标当前及批准后profile改投窗口。反例/早期失败日志均保留，最终联合154项、Runtime/Hub22项及原生卡片13项通过；额外完整项目回归919/919通过、零跳过、722.343s。
固定1280×1600、AI智能体a2最大化、原待批准卡片：两次真实指针事件读完整计划并批准；仅一次run_plan/run_decide，无planner start，Viewer与布局不变。CPU/FakeTextMeasurer不是GPU字体或目标OS证明。
前远端a506 Desktop42459561098已于08:42:54Z失败终态：五job成功；Windows原生6/6各20轮过，Mac CPU/Metal过、两视频AX失败。新代码CI尚待推送，不借旧绿灯；PR53/54实际head未变，不整合无关旧差异。
四状态文档旧WIP保留；root统一AOCI与交付，Claude10只交外部复核。真实许可/HDF5-only完成与科学有效性仍未验，原八项/D1和待决保留。完整证据见 s2c-wire-20261108-07/root/closure.json。

## 2026-11-08 UTC：首次批准启动与单次消费组件

Claude独立claude/support交 `867eef9b`，root审查后选择集成 `afef46c5`；仅两个分配文件。WorkflowRuns.start可选approval在追加started同一事务核原计划/请求、当前修订与归档并拒绝历史started，普通人工重启保留。Claude38+13项回归通过，禁用started/归档门分别出现2/1个预期失败。
root随后提交 `67670ae3`：RunApprovals利用现有会话哈希链，绑定原工具调用、确定UUID和冻结请求；start/decline先原子消费，重复决定无dispatch。observe只认原approval的started证据，不运行/恢复/取消；未认证用户标记、历史收据与当前状态明确保留。
CL-S2C-LEDGER-REVIEW-07发现旧_observe对start_run读取draft_id；root两个红例先失败，再补运行卡/收据观察和decline来源，最终joint-04为99通过/零跳过、19.14s、12输入稳定。MuPRO/agent既有合成Runtime兼容链8通过、114.88s，无真实许可或模型调用。
尚无prepare工具/派发/桥路由/原生卡片，现有AGENT_LEVELS未扩；不是完整S2c或真实执行验收。Claude接CL-S2C-EXECUTOR-08仅改后台执行器和新测试，root保全局集成/契约/四文档。C2仅AI新增行范围不采用，最终也支持既有MuPRO案例行。
a506cc69的Runtime42459561111/Docs/Secret成功，Desktop42459561098整轮仍在跑；本批源码未push、无新CI。PR53/54头c9f13994/2dd3e4ee未变，未合入旧重复实现或历史交接。证据见s2c-agent-run-20261108-06/root/closure.json。

## 2026-11-08 UTC：AX 异步调度候选与 S2c 方案审阅

源码 `598a069b` 仅改报告原生夹具：每次完整空AX查找后泵UI至少250ms，再进入原四次上限的下一次；成功输入、唯一时间匹配slider、DOM/OS像素和20轮门均保留。
独立重读旧artifact确认两视频的第4次累计时间为34.067041/45.657208ms；WebKit311616及WebViewImpl的按需AX初始化为时序假说的直接来源，未声称本候选已修好Mac。
Linux stk-reports-native-window目标重建退出0；本机不编译或运行新增APPLE分支。暂存836字节gitleaks8.30.1零发现，未新增产品UI或点击测试。
前761a Desktop42455805095于07:27:11Z completed/failure，4job成功；Mac9文献/2视频，Windows原生1/6旧divider失败。前整轮门满足，下一push将含dc5890b1和598a069b，新CI另核。
Claude交付145行s2c-plan-05.md，root核对CHECK约束、原prepare副作用和start可重启，选择无格式升级的会话payload方案；新增跨路径竞态要求：仅会话锁无法约束编辑器start，须在同一工作流写事务内防重复。
已派发CL-S2C-FIRST-CLAIM-06，仅独立树workflow_runs.py与新测试；root负责其余接线和发布。方案测试未执行，完整S2c、真实MuPRO、D1/文献UI等继续，原WIP与待决保留。

## 2026-11-08 UTC：文献锁、原生夹具及插件测试顺序修正

源码已本地提交 `dc5890b17eeb4c1b7a76aa42e0e8770abeccc924`，5文件；未push，前远端为761a9e37。
Darwin租约改钉住corpus目录inode，并在加锁前后核身份、持有至SQLite关闭；Linux保留DB inode租约及原恢复校验。
已有独立进程恢复测试扩展两种Linux可行策略，Darwin只跑目录策略；复核时修正强制启用旧Darwin策略的测试前提，未增加或跳过必跑案例。
Windows失败OS证据显示MouseMove曾正确改变尺寸，随后捕获期排队hover移回；本地MouseMove/Up连续派发后才泵队列，原事件仍正常路由，验收门不降。
文献C++夹具补corpora.create的状态/错误码；不记录请求、正文或私有路径。
HDF5测试在CLI模块重载后误用旧注册表函数，真实有序红例1失败/27通过/1跳过；独立build_registry及当前模块修正后28通过/1跳过。
最终联合03为189通过/5跳过、26.42s；文献92唯一零skip，21个记录输入稳定；原生文献24/24、14.392s，两个目标构建退出0。
初轮137通过/28跳过因缺PDFium，不作真实解析验收；外部隔离环境安装仓库固定PDFium 5.14.0后161通过/4资产跳过，最终联合含该真实解析环境。
本批暂存10.44KB gitleaks8.30.1零发现；扫描器归档SHA已验证。未跑真实MuPRO/模型/新UI或目标OS原生，不将候选修正写成已验收。
761a Runtime已失败终态，Desktop仍运行，等待整轮后再push；四文档旧WIP保留。Claude独立树继续CL-S2C-PLAN-05只读方案，尚未交付验收。

## 2026-11-08 UTC：MuPRO HDF5 发现、收集与兼容修正

源码提交 `89e40c89f946556e35ee954eb9a3fbf9c1a0dbfe`，19文件；Claude两新文件来自 `c975f58d`，root完成跨模块接入。本地已提交；前Desktop现已终态，推送及新CI以本批closure为准。

- 元数据仅遍历两层、总4096项，复用原读取器的链接/存储/类型检查；不读值。字段按原名/步号、dtype和selector描述。
- `hdf5:<field>` 与DAT独立；句柄读入须匹配发现时容器SHA。图索引规划SHA与执行绑定，替换插件保持原describe契约。
- 同任务 `case/run.h5` 经产物摘要、冻结网格及跨步shape/dtype核验后登记；不新增调度器或提交路径，坏HDF5不登记为成功结果。
- 审查复现并修正跨步布局漏检（2个先失败反例）及DAT浏览、容器预算、替换插件兼容（3个先失败反例）。HDF5问题进入独立诊断，规划内容变化仍拒绝。
- 修复f152 CI遗漏的节点目录断言；Windows创建时间测试改独立GetFileTime，不假设fstat ctime语义，被动导入不再误禁标准库msvcrt。产品HANDLE ChangeTime检查保留。

最终21文件419通过/5跳过，268.34s，34记录输入前后稳定；修正前414/5、各红例及18/52项定向复验保留，不能用旧结果覆盖新字节。
CLI02在实际新进程自动发现HDF5并导出NPY，180个float32值/selector/源SHA独立相等。合成SDK只证明软件和原任务身份，不是许可求解或科学验证。
暂存56.97KB gitleaks零发现。远端f152 Runtime终态失败、Docs/Secret成功，Desktop于06:17:18Z失败终态（4个job成功，macOS及Windows原生文档失败）；本节记录时未推新源码或重跑CI。
root保持四文档原WIP，认知最终收口和记录提交身份见本批closure。后续S2c、D1、原生文献、真实MuPRO与旧CI范围继续。

## 2026-11-08 UTC：MuPRO HDF5 读取、来源与图接入

读取器由 Claude 独立树 `73abd757` 交付，root 审查并接入 FileSource 和 `stk.source.mupro_hdf5@1`；源码已提交 main `56f51af70d576837426f63c12694941b0ea7cfcd`。
root复现的selector尾换行、原地改写后恢复mtime已修；Windows采用HANDLE ChangeTime，POSIX同API ctime，无法核验时报错。
独立复核还补了压缩chunk分配估算、未写入数据/缺chunk及过滤器边界；没有用此读取器替代MuFerro完成验证。
root新增实际FileSource流SHA与私有副本校验，NodeContext返回规划指纹副本；新增显式节点及同步目录/规格/技能参考。
首轮图模式样本失败已修；联合回归曾2失败（selector放错agent字段、旧节点数量），改为SourceRef及6节点后最终匿名文件修正后305通过/3跳过。
真实CLI合成HDF5读取及NPY导出成功，180个float32值与原数组全部一致。实际MuPRO与UI/目标OS未验，旧离屏SIG11保留。
暂存74.83KB gitleaks零发现；四状态文档旧WIP保留，正式认知收口及最终CI状态见本批closure，不借旧aligned证明后改字节。

补充修正 main `3579aea16ff9249fdb688012575576f1aeea8fb4`：交叉审查确认强杀worker遗留命名副本，已改匿名/关闭即删除的临时文件，共享同一读取核心；真实子进程强杀清理测试通过，CLI无缓存复验180值一致。

## 2026-11-08 UTC：试点文档集成与读取器审查

main `f6a75f84` 集成9份试点/分工/D1文档；检查73个链接/锚点、暂存gitleaks56.67KB零发现，仅提交四状态文档新增前缀，保留原WIP。
Claude在独立树提交HDF5初稿 `760b7ae1`；root独立实测确认尾换行selector及同大小改写后恢复mtime均被错误接受，交回修正，未采用初稿。
原远端Desktop整轮completed/failure，Mac文献9例/媒体2例、Windows HTML视频布局拖动1例未过；Linux三job/Windows CPU成功，未改门槛或借局部绿灯覆盖。
main九项AOCI增量维护并顺序Verify/Check/Guide通过；本节终态记录是后续新增字节，按最终稳定状态收口。

## 2026-11-07：MuPRO/HDF5 试点与 S2c 方向获准

所有者选择 MuPRO/MuFerro 为首个执行器/专业软件试点，原生格式由各插件定义、MuPRO 使用 HDF5，并同意开发 S2c prepare/run 权限扩展。
新增试点设计并更新工作台决定和协作入口；研究任务的电场扫描数值与分析修改提案持久形式仍未指定。
协作规则已本地提交 `37d26464`，Claude worktree/分支独立建立，CL-D1-01 后台会话89bf764a已启动并收到排队的新决定。
31 项 AOCI 两批应用后 Verify/Check/Guide 均退出0、Guide complete/none；新决定文档的增量随后再维护。
root 审查并选择性提取 Claude 文档头 `9590d21b`，纠正外部网络与回环的区分、未核实的 SDK/HDF5 版本推断和 AOCI 配置推断，清单仍不是 D1 实施验收。
另派发 CL-MUPRO-H5-01 独立读取模块和测试；Claude 已在自己的树开始写代码，root 暂不采用未交付源码。
MuPRO 当前配置预检退出1（无 SDK/程序/许可配置），四组旧链回归74 pass/1真实程序资产skip，Linux文献现有单例复核通过。
Desktop同头整轮尚未结束，macOS文献9项和原生视频2项失败均保留，未盲合PR53/54；详情及证据在运行验收。
本节是决定、前置检查与协作交付，不表示新 HDF5/Agent 功能或真实 MuPRO 科研验收。

## 2026-11-07：所有者指定 root 总负责与独立 worktree

Codex 负责拆任务、审查、集成和交付；Claude 在独立 `stk-claude` / `claude/support` 承担文档及指定模块，
替换刚提交的 5670f565 共用树/设计专属分工。更新 AGENTS/CLAUDE 入口并增加协作约定和 CL-D1-01 ready 任务卡。
原有未提交状态文档内容保留，四文档新增本节；未改产品代码或发布契约，未宣称 Claude 已开始任务。
实时 CI：远端 6f4de650 的 Runtime/Docs/Secret 成功，Desktop 42442318655 仍运行；本轮验证/证据见运行验收。
旧八项范围、三待决、PET 后置保持。证据目录为 `~/.local/state/stk-validation/worktree-coordination-20261107-01/`。

所有者另已设持续开发目标为 active：root 合理分配 Claude 工作，并审查、验证及合并当前计划相关 PR；
所有者数日后回复问题，期间继续不依赖待决的工作，不把未回复视为授权选择。

## 2026-11-06 UTC：准备启动会、整体框架和多仓库协作材料

交付 [平台总体框架](design/platform-framework.md)、[滚动路线/周会模板](planning/platform-roadmap.md)、
[仓库规划](planning/repository-strategy.md)、[讲稿](planning/research-kickoff.md)及
[10 页 HTML 演示](planning/research-kickoff.html)，更新共同后端设计与仓库结构入口。
材料 main 本地提交 `325fe57dc955b4e9a69370e60d03f39ad0a6bb7b`（七文件，647 行新增）。

明确 stk 共用后端/原生/CLI/协议，synthrix 保留 React 并逐领域退出旧 Node；候选 stk-platform 仅集成发布，达到门槛再建或复用。
W0+12 周是有限试点条件计划，W2 以实际投入重排，不承诺全平台/全部领域；真实许可/GPU/科学结论各自验收。
审阅收窄了网络波动下“绝不重复”的口径为原键恢复、未知不另起执行，避免承诺任意外部副作用 exactly-once。

验证：60 相对链接目标、5 章节锚点、围栏和暂存空白检查通过，材料暂存 gitleaks 扫描约 70.13 KB、零发现。
headless Chrome 导出最终 PDF 10 页，PDFium 逐页文字/页码核对，实际查看架构/仓库/排期页；无新产品运行测试。
证据/PDF：`/home/mnemora/.local/state/stk-validation/stk-kickoff-plan-20261106/`。
远端仍 350534d，Desktop 41639295121 失败终态；本地前代码头 535b0d63 查询无 CI。本轮不 push、不触发 CI、不创建仓库或改权限。
设计直接证据例外继续，AOCI 不维护或改资产；六项原 WIP 保留，本节仅追加当前记录。

以下保留此前交付原文。

## 2026-11-06 UTC：交付统一后端架构、协议和验收设计

按所有者补充，明确 STK Core 与云端共用后端实现，Desktop 保留 C++ / Python / GPU，Web 保留 React。
新增[架构](design/shared-backend-architecture.md)、[协议](design/distributed-task-data-protocol.md)、
[验收](design/distributed-workbench-acceptance.md)，并更新两处已有设计入口。
设计提交：`f541393b31b9f32b1f73bc738998075bc93e6dbd`（main 本地，五文件、497+/2-）。

直接证据核对 STK 535b0d63 与 Synthrix 网页 a15ab6b；纠正不能将历史 90d7c4a 的可选 Hub 接缝当作当前网页能力。
交叉审查明确同后端代码/状态机、数据归属、迁移回滚、旧回执缺证据不猜补、不在失联时重算，
以及本地独立任务离线可用与远端授权失联限制的区别。验收包含 15 项故障、4 项迁移，真实 license/GPU 与 stub 分开。

文档验证：87 个相对链接目标均存在，代码围栏配对、暂存 diff 空白检查通过；最终暂存 gitleaks 扫描约 63.12 KB，零发现。
未运行产品测试/构建/UI/模型，未修改发布契约或业务源码。旧六项 WIP 原样保留；本次只向四份状态文档追加当前记录。
远端仍 350534d；该头 Desktop/Runtime 失败终态、Docs/Secret 成功；本地前代码头 535b0d63 未推送、无对应 CI。
本轮仅本地文档提交，无 push 或新 CI。所有者授权本轮直接证据设计并暂缓 AOCI 加载/维护，未改配置/索引/baseline、未声称对齐。
证据：`/home/mnemora/.local/state/stk-validation/stk-unified-backend-design-20261106/`。

以下为历史记录，旧“当前”标记不覆盖本节。

各历史批次的待办及 CI 状态保留当时快照；当前状态以最新首节和 `handoff.md` 为准。

## 2026-11-03：恢复持续目标并落实 STK 主体方向（当前）

所有者恢复完整计划的持续开发。新增[分布式科研工作台](design/distributed-research-workbench.md)，
将 STK 主体、Synthrix 对话/科研管理、本地完整/Web 轻量、授权节点、跨位置 CLI、Computer Use 与插件分发记录为产品方向，
同步工作台设计和主计划；旧八项完成条件与三待决保持，不以新方向缩减原范围。
恢复前已核 Git、前头 CI 和当前进程；保存 91 WIP 逐文件 SHA 与旧四文档至
`/home/mnemora/.local/state/stk-validation/resume-platform-20261103T110725Z`，无 reset/clean 或覆盖现有源码。
文献 profile、文献服务和 Hub CLI 分工推进，联合回归和真实资产测试按来源冻结点运行；结果以本节后续补记和运行验收为准。

本批修正Qwen融合检索身份及历史encoder review恢复两个真实反例；E5/Qwen/PDFium联合69/69、零skip、14输入稳定，文献服务三父Python各26/26、20输入稳定。
公开文献Bridge最终54/54、27输入稳定；一次fresh E5链发现Schema缺parser三字段后精确补齐，10项实际缓存DTO重验、PNG/geometry和撤权续接通过，最终原fresh函数明确deselected。Root随后编译运行当前嵌入Schema的C++64正反例exit0；恢复证据根下integration-01/literature-native-probe-observation.json记录实际工具观察及事后哈希，未伪造前后来源快照、未重复运行。
Hub CLI相关9文件187pass只保控制台证据，没有独立XML/前后source proof。独立冻结heldout各角色一次、41输入稳定；Qwen同语120/120、跨语119/120过原门，E5 reference为120/120与24/120；仅派生XQuAD一般段落诊断，不替原科学PDF12/18/cross0/6失败、官方QA或RAG验收。
S6最终Schema三Python各430/430、334输入稳定，绑定后续file_store修复前SHA。S4独立审查复现旧Accept越过本地撤权，原intent/整行checkpoint CAS补修2红→绿；联合460pass/2个Windows-only skip，独立三Python各10/10、220输入稳定。

整合01保留真实失败：原生2074pass/1fail为过期editor数量断言；Root仅将19→20并补Peers存在断言。
Python01为5411pass/148skip/2fail，960.894s，973来源中file_store及其测试发生漂移；修hello测试人工上限8→16KiB并保oversized/EOF断言，重新生成技能nodes.md补reproduction节点，定向2/2通过。
整合02原生2075/2075、零fail/error/skip，build19.251s/ctest490.527s、1291输入稳定；Python02为5489pass/74skip/4deselected/1warning，pytest1207.90s、wrapper1211.584s，5563案例、973输入稳定。跳过含显式encoder资产、Flower、离屏SIG11、Windows、MuPRO和可选依赖，不将独立69项真实推理重复算作全量已执行。
当前wheel SHA `fbd6625a71e287a5ae83657b80ea583230841a8abc7a078e347e1db7b440c8a2`；新Linux隔离环境299/299、零skip，四个真实模型/PDF案例明确deselected，715输入稳定、704产品成员逐字节一致。完整证据见运行验收；最终sdist未完成。

11-03此前AOCI压缩链21/24后因snapshot_unavailable中止，未确认/未Attest，该失败保留。
最新Root完整24/24交付confirmed、Challenge9/10 pass，1144条/estimated165707 tokens；29条Observed逐当前SHA核对后acknowledge applied、txn40bc59963d92d5d733245239。这不是Entry语义维护或全量aligned，Dirty/Stale仍待最终稳定后维护。
本地HEAD仍 `3ef4b2716d42304d708062f9715edae0afb5874f`，本批无新commit/push/新头CI；通用完整计划、八路线、三待决和PET后置保持，原生文献UI/目标平台/真实科学复现仍待完成。

## 2026-11-02 21:38 UTC：按所有者要求保存待办并转交（历史）

重写[handoff.md](../handoff.md)并冻结开发，保留最新代码/失败/未验证边界、外部证据和接手顺序。逐文件91 WIP（33 tracked/58 untracked），暂存空；HEAD/local origin/main/实际远端均3ef，无新commit/push/包/新头CI。本次仅四状态文档/审计，87份其他WIP保持原字节，旧四文档备份和最终检查见 `OWNER_NEW/handoff-20261102T2138Z/`（根见handoff）。

续开发阶段已保存encoder_profiles、E5/Qwen双维worker/Dense/Collection及测试，但未运行；LiteratureService最新双profile/bundle/timeout适配预计25项也未运行，旧21/22/38项不能覆盖。S6四文件已入仓，415项稳定证明早于FIFO修复；最新各41项零skip，但源稳定性因literature.py漂移失败，保留真实限制。原40QA检索质量失败不变；独立tune真实Qwen FP32跨语115/120、E5为12/120，INT8为101/120并失败质量/耗时/RSS门，未采用；独立heldout未评分。

所有协作代理已冻结，既有INT8 session62558完成、未超时、自有child回收，没有新实验。Root本次AOCI24/24交付确认、Challenge10/10，治理仍Dirty/Stale；最终Maintain/Verify/Check/Guide见交接closure，未完成语义维护。再次实际GET同3ef/attempt1 Desktop failure/Runtime success；八路线/三待决/PET后置和当前WIP限制保持。

## 2026-11-02：恢复持续目标，推进服务和复现闭环（历史，本次转交前）

所有者已恢复按当前计划完成所有开发，上一轮handoff停止点为历史。main/HEAD/远端仍3ef、暂存空。S6新增四文件，三Python各415/415零skip、252输入稳定（`OWNER_NEW/reproduction-workflow-02/matrix-02/closure.json`）；Root随后复现FIFO读取阻塞并要求增量修复，后改代码不能借旧415结论。LiteratureService真实21项与worker38项已跑，正修独立审查的历史配置/引用rank和身份/数值类型/manifest预算问题并准备三父Python验证，尚未接Bridge/native。

原40QA全局12/18、cross0/6的质量失败保留；独立混合240段实验已冻结文章级tune/heldout，E5开发同语言119/120、cross12/120，候选本地模型正在运行，heldout尚未编码或评分。完整实验和限定在 `OWNER_NEW/retrieval-quality-independent-01/`；无产品模型/endpoint/网络设置或旧QA/语料改动。当前无新commit/push/包/新头CI，AOCI仍Dirty/Stale；稳定交付再维护。完整八项路线、三待决及PET后置保持，接手入口见[handoff](../handoff.md)。

## 2026-11-02：停止开发，保存待办转交（历史，本轮恢复前）

按所有者最新请求重写 [handoff.md](../handoff.md)，停止开发并收集协作Agent终态；本轮仅文档/审计，没有新产品测试/构建/提交/push。83 WIP（33tracked/50untracked）、暂存空，main/HEAD/实际远端仍3ef。保存旧四文档和79个非状态文档WIP before/after SHA，外部证据 `OWNER_NEW/handoff-20261102T2022Z/`（根见handoff）。

此前本轮实际结果已核：PDF/Store三Python各92/92零skip，CI92唯一/68必跑/76负例；Dense/Collection43/43真实E5零skip、410.435秒、14输入稳定；1051完整引用批次结果等价，解析31.489→3.248秒。首次冻结两库40QA/80查询完整、源稳定，但全局heldout hit@5为12/18、cross0/6，主门失败；保留首次失败和旧QA，禁止以exit0称达标。S6比较核心57项+图节点40项三Python全执行，相关195pass/1旧离屏skip；外部工作流草稿3.12初验15/15尚未源绑定/入仓。

LiteratureService两草稿和WorkerProcess env patch已确认保存但未测试；wire选encoder解释器尚未纠正，spec/tests缺失，Bridge/Schema/native未接。S6外部稿还需私有Matplotlib导入、prepare丢回复恢复及三Python/wheel证明。Root本次新完整AOCI24/24、1144条、Challenge10/10；治理仍Dirty/Stale，最终Maintain/Verify/Check/Guide见外部closure，不保存正式认知正文。官方同头Desktop failure/Runtime success再次GET；八项通用路线、PET后置和三待决不变。

## 2026-11-02：恢复完整通用目标并修检索收尾（历史，本次转交前）

最新目标恢复，原交接65份业务源码字节全部保留。文献CI门禁改72唯一案例、48必跑；三份实际报告/三Python执行及56负例通过，`OWNER_20261102/literature-ci-01/`。Dense/Collection37/37真实E5、零skip、291.63秒，14输入稳定；独立审查后实际复现两个查询入口中途换模型仍返回、融合lexical阶段换模型仍返回，以及深层base原始RecursionError，四反例和修复已保存，当前41项回归进行中。

四公开PDF新格式两库显式导入索引，23页1051段、原身份和完整回执一致，91引用几何/span/字节/授权核对通过，16输入稳定；未启动科学语料embedding/ranking。S6独立比较核心/新契约开发中，不改现有报告或图目录，不声称真实论文复现。旧转交停止点为历史；无新提交/push/包/新头CI，业务仍变化，最终稳定再做AOCI维护，PET后置/三待决不变。

## 2026-10-31 18:30 UTC：冻结工作并转交（历史）

按所有者最新请求重写 [handoff.md](../handoff.md)，清除过期实施顺序，保存当前69文件WIP、优先待办、源码摘要、复验环境、外部证据、平台边界及三待决；本轮不继续开发。main/HEAD/远端仍3ef，暂存为空，无新产品测试/构建/包/提交/push/CI触发，协作Agent及既有测试进程均终态。

收集现有最终Store三Python各72/72零skip、10输入稳定；保留64项历史，不把旧aggregate称72项。Dense28/28在旧Store稳定，Collection9/9运行中Store漂移且后加分支清单未测，当前37项及科学语料排名未完成。当前CI仍固定38，明确列为首要配置待办。最新helper Bridge123/122/122pass与实际helper原生19/19、发送13/接收7点击保留各自源绑定与CPU起点范围。官方同3ef/attempt1 Desktop failure、Runtime success再次GET确认。

Root本轮AOCI24/24交付确认及Challenge9/10 pass，治理仍Dirty/Stale，不持久化正式认知正文。四文档备份、Git/源码一致性、CI和最终文档/治理检查见 `OWNER_EVIDENCE/handoff-20261031T1830Z/`。完整通用目标未完成，PET新专项后置，接手后按实时合同重建认知。

## 2026-10-31 18:10 UTC：恢复通用目标并继续真实链路验证

目标恢复后Root新增Store八条实际反例，8红→绿，基础三Python各38/38；P4独立复核又证实未知库hot-journal被恢复及DB原始fd关闭导致SQLite锁失效，继续完善专属Store2，不把前一矩阵称最终闭合。S5补dense参数/诊断/损坏重用和融合校验，纯16/16，28项真实完整回归等Store稳定；QA v1问题保留，v2按整篇文档隔离、Root6例逐span核对后冻结，开始实现无金标corpus过滤的本地多库检索，尚无语料排名结果。

P4最新loader审查+Bridge三版本123/122/122pass，129输入稳定，两真实helper和19专用场景通过。Root新增可选真实安装helper原生CPU验收目标：实际发送页13点击/接收页7点击，各0滚轮、字节匹配、Viewer/隐藏稿保留；两场景与旧17项联合19/19、971输入稳定、六组守卫通过。连接与对端动作为明确夹具，不冒称连接UI/OS/GPU/跨平台/跨站。各证据见runtime-validation及handoff当前节。native槽已释放；无新提交/push/包/CI，旧暂停指令为历史。

## 2026-10-31 10:30 UTC：冻结当前工作并转交（历史）

按所有者最新要求重写 [handoff.md](../handoff.md)，停止继续实现，列当前67路径WIP、首要Store两缺陷、验证适用范围、剩余通用路线和三待决。main/HEAD/官方远端3ef，暂存为空；无新增产品测试/构建/包/提交/push/CI。所有参与Agent已安全停止，native槽释放；旧handoff外部备份及本轮Git/证据/文档/治理检查见 `OWNER_EVIDENCE/handoff-20261031T1030Z/`。

收集本次转交前终态：PeerState/UI build08及17/17、971输入稳定，固定起点11/20/1点击，合成Host/query DTO边界明确。Bridge submit故障保护最终123/122/122pass（对应1/2/2skip），129输入稳定，早于最新loader修改；loader ctime补修三Python各38/38。PDF/FTS基础三Python各30/30；真实E5测试3.12为8/8，随后hybrid_search新增未测。语料/40QA已冻结，无独立QA审核/检索指标。实际spawn反例确认未知库DDL和completed回执改写，Root修复尚未开始，交下一Agent优先处理。没有把旧全量或跨平台结果转作本批验收。

Root本轮AOCI24/24传输/确认、严格Challenge10/10，治理仍Dirty/Stale；此前owner_review22/24 snapshot失败原因未定，未重试/绕过。最终维护及检查以外部机器结果为准，不复制正式认知正文。官方同3ef/attempt1 Desktop failure、Runtime success；P4/S4/S5/整份计划均未完成，PET新专项后置。

## 2026-10-31：持续目标恢复，修基础Bridge启动并编写Peer页面（历史）

继续通用目标，PET新专项后置。查明旧3.11/3.14的15失败均起于Bridge构造时急切导入可选NumPy，含两个stdio子进程先退出的超时；四份stderr证明保留。MaterialsService改为显式访问才构造、缺依赖明确unsupported，shutdown不隐式创建。先在无NumPy的两环境各2/2真实证明，再仅离线补隔离环境NumPy；MaterialsAPI35/35，最终三版本Bridge119/118/118通过（WinDPAPI及缺可选VTK两类skip分别记录），129源输入稳定，`peer-bridge-02/closure.json`。

Root独立审查helper六文件并保存源SHA，未增可确认缺陷。编写PeersEditor、注册/i18n/Files导航；独立审查修正Host嵌套回执、文件名/字节数、手填新grant/session被旧缓存覆盖、多选后快照消失等问题，正在补分页和当前prepare/bridge epoch反例。新UI尚未编译/验收，P4唯一build槽待源码冻结；不以代码存在替代实际点击/Viewer草稿保护。暂无新增commit/push或新头CI，四状态记录随后按真实验证更新。

## 2026-10-31：保存当前待办并转交（历史，09:00 UTC）

按所有者要求停止扩展实现，重写 [handoff.md](../handoff.md) 清除相互冲突的旧停止点，列明48个WIP路径、续接顺序、具体入口、证据边界、平台失败、三待决和完整通用路线。HEAD/远端main仍3ef，暂存为空；未提交、推送、触发CI或启动新产品测试/构建，只收集已启动验证终态。

helper发行候选已终态：三Python loader各35/35、12输入稳定，Linux重定位UDP/TCP/IPv6通过；Root独立审查和跨平台/干净机仍待办。Bridge新增精确identity.recover、关闭竞态保护及29个desktop-only方法；最终3.12为117pass/1Win skip、116输入稳定，3.11/3.14各101pass/2skip/15fail（13缺numpy、2旧child超时），失败保留并交下一Agent处理。新PeerState目标构建exit0，三个新测试尚未执行，没有PeersEditor/UI或点击验证。四状态文档与外部交接检查同步，AOCI正式治理仍不一致，不沿用旧aligned或旧包/全量结论；PET新专项后置。

## 2026-10-31：恢复通用目标并接通生产文件链（历史，本次转交前）

持续目标恢复，PET新专项保持后置。接收端最终写租约内重查原op，resume大前缀扫描移出Authority/identity/pairing/DB事务并在效果前核当前授权及物理/journal checkpoint；receiver26/26，三Python各121pass/1Win skip、24输入稳定，保留红例和补修历史。

新增 `suan/peer/files.py`、sender/recovery两测试文件，实际生产身份/会话/FileStore/Endpoint两helper UDP/TCP链通过；每块先持久意图，网络等候无授权锁，原epoch及rebind阻下一块，新批准不自动续旧send。补齐独立审查发现的最终完成回执丢失收尾：显式recover仅采用原请求/完成proof，无重发/发布/复活撤权，unknown publish仍unknown。初始测试捕获snapshot修订假设错误已修；恢复缺口两红例、最终本地journal故障和伪造/未知proof均保留验证。

`OWNER_EVIDENCE/peer-files-final-01/`：14文件/81输入，3.12完整peer581pass/2仅Win skip，282.83s，含240MiB/4098block及Python峰值<32MiB断言、实际断线/新TCP/再批准/newgrant/显式resume；3.11/3.14各580pass/同2skip，62.56/62.71s（不重复大文件），所有输入稳定。独立源码审查未发现新增可确认缺陷，非全仓或安装/目标OS证明。

Windows3ef真实5/6，独立视频20/161通过，HTML-video0轮止于反方向divider且capture保留，根因未定；仅增有界真实事件/几何诊断，原门保留。Linux六目标33.77s、72/72CPU2.31s、566输入稳定。Mac CI追加11文件非native选择502pass/2Win skip、9守卫负例/YAML/Bash过；真实Mac未跑。helper安装/发现/对应源码许可与实际桌面生命周期/Bridge继续开发。HEAD仍3ef，无新增commit/push/CI触发，新包/AOCI最终收尾尚待稳定，当前入口[handoff](../handoff.md)。

## 2026-10-31：交接（历史，3ef 已推送，文件共享尚未接通）

按所有者要求停止实现/测试/构建，将当前待办写入[handoff](../handoff.md#当前接手顺序)。447/2513及记录3ef已推送；实际HEAD/main/origin/main为 `3ef4b2716d42304d708062f9715edae0afb5874f`。20个peer/平台源码、测试和spec WIP保留，暂存为空，本次只改四状态文档；没有新增产品测试、提交、push或CI重触发。交接前20路径SHA和旧文档存于 `OWNER_EVIDENCE/handoff-20261031T074142Z/`，最终结果见closure。

续接开发已有持久身份/配对、manifest/安全IO、接收FileStore和可选Endpoint文件帧；生产发送协调器/包装接线未完成。独立审查定位receiver重复请求竞态和resume长Authority租约，两项未修；下一Agent先修再验。endpoint最终3.12定向301/301零skip、早期联合408/408、纯codec三Python各286；identity95pass/1Win skip及receiver17pass范围分别保留，旧4716/2056/585不覆盖新WIP。

07:40:57UTC官方同3ef/attempt1：Desktop41178119889终态failure（Mac编译及Windowsnative失败）、Runtime41178119790终态success10/10；Windows新失败根因未知，Macfrom_chars本地补修只过Linux24。业务中间态AOCI仍Dirty/Stale，无新包安装或整体S4验收；本次不强行完成产品。PET新专项后置，通用路线与三待决保留。

## 2026-10-31：按所有者要求保存待办并转交（历史，3ef 提交前）

停止扩展功能，仅整理四状态文档及必要AOCI资产；没有新增代码提交、push、产品测试或CI重触发。实际本地main仍2513c088，ahead远端6126两个提交；六份记录资产未提交、暂存为空。06:41 UTC前后官方GET确认6126 Desktop41163547328失败终态、Runtime41163547349成功，未覆盖447/2513。当前交接列明确待办顺序、源码入口、已测范围/限制、S4/S5/S6/P5-S7和三待决，PET新专项后置。机器收尾、文档检查及最新包来源见 `OWNER_EVIDENCE/handoff-final-20261031/closure.json`、`package-final-docs-02/rebind-summary.json`；未完成前不得把Observed确认或旧批次写入当整体aligned。[handoff](../handoff.md)是接手入口，下节候选收尾为历史。

## 2026-10-31：完成Apple窄补修与交付候选收尾

在05:45交接保存后，持续目标明确恢复。主链447a19ac保留原43路径验证，独立补修提交 `2513c08817bb9036bc63ffd341503f6d85a29aaf`：Apple视频隐藏/重显后的条件rewind改用已有只读AX定位加普通鼠标路径，其他平台保留LeftArrow，追加同导航核对，暂停/时间/像素/20轮门不变。Root完整审阅四份2116行源码，未发现其他已验证缺陷。

`OWNER_EVIDENCE/p4-platform-20261031-02/closure.json`：六目标构建exit0、33.628秒；72/72 CPU、零失败错误跳过、2.269秒，529输入稳定。与完整2056回归的fixture差异明确另记，Linux不证明Apple分支或目标OS运行。Root实际暂存1389bytes补丁SHA `c5834ddcbe02bb169ff9d6be6171f8d79e5bd04c7a6aea03b94f013615828d29`，gitleaks/redact和空白检查exit0后提交2513，证据 `delivery-02/staged-p4-summary.json`。

native3、Python4、P4四份完整Observed审阅与当前11路径SHA匹配后，机器Baseline确认已policy_bound_auto应用，事务f8be6acedab1ccffa0410d6f；不创建Entry，也不单独证明aligned。正式语义批次及最终Verify/Check/Guide结果读 `delivery-02/` 实际机器证据；最终文档包重绑读 `package-final-docs-01/rebind-summary.json`，保持已测wheel不变，历史585与重绑分记。

本节为推送前候选记录，源码447/2513本地已提交；旧6126 Desktop41163547328失败终态、Runtime41163547349成功仅覆盖旧头。新头实际推送/CI以Git和Actions为准；P4/S4不标完成。完整4716/16skip/2排除、2056、585及真实worker1证据与限制见[handoff](../handoff.md)和[验收](runtime-validation.md)。继续完整通用路线，三待决不擅选，PET新专项后置；下文转交/进行中均为历史。

最终文档包 `package-final-docs-01` 已13.326秒完成：已测wheel整包仍a6e5…，新sdist SHA `c213092f48b1b719f7f46170a4f19330f105ffd35ea9425e12c230b0ebd466e1`；995源成员只runtime-validation变化，681wheel源成员/22选定测试及310非状态已测输入不变。未安装/重跑585。新SHA不回写包内runtime-validation，避免自包含摘要循环；外部rebind-summary保留完整实际命令/字节核对。

## 2026-10-31：最终验证后转交（历史，05:45 UTC）

按所有者要求停止实现/构建，native构建窗口释放。实际本地HEAD为未推送 `447a19ac8199c62ba81be5aef5458b4135b04410`，43路径已提交；origin/main及官方远端仍6126，暂存为空、7个tracked修改保留。此次将[handoff](../handoff.md)改写为当前接手入口，前四文档及7路径SHA备份在 `OWNER_EVIDENCE/handoff-20261031T0545Z/`。快照整理未新建提交、push、产品测试或CI重触发。

已闭合Python4716/16skip/2排除（1010输入稳定）、独立安装585/585、额外实际worker1/1、原生候选完整2056/2056零skip（2816输入稳定）；详见[验收最新节](runtime-validation.md#2026-10-31最终候选验证与转交范围0545-utc)。三平台Federation CI守卫后置增量已检查并进447。最后Apple rewind-after-show fixture尚未构建/测试，保留为唯一源码WIP；不借2056为它背书。6126 Desktop失败终态、Runtime成功均只覆盖旧头，新头OS验收待推送。

交付未闭合：窄补修验证/代码提交、四状态最终记录、包文档重绑、P4最终Observed审阅、AOCI acknowledge与Maintain/Verify/Check/Guide、实际暂存扫描与记录提交/push。当前Guide blocked/observed_pending，不伪报aligned；S4其余/S5/S6/P5-S7、三待决及PET后置见handoff。下文旧HEAD/仍运行/未实现描述均保留为历史。

## 2026-10-31：通用 owner 流程续接与最终验证（历史）

持续目标恢复后继续通用路线，PET专项后置。新增桥拒绝证明反例通过；三Python172/172属于活动模型CAS补修前。独立审查修复了已知模型CAS拒绝发生在intent登记后的卡住问题：现在只读预检先于owner保留、实际执行再次校验，后续竞态仍不确定；补修后三Python各112/112、63输入稳定。

candidate-08原生20/20零跳过，四固定布局Data流程各13点击；candidate-10完整授权、两次评估/准入、独立启用/回退和撤回审计四布局4/4、各50点击，均保Viewer/隐藏稿，起点两行/各一训练留出，CPU事件不代OS/GPU。2056项原生统一回归仍待结果。新package-03的681个wheel源成员与995个sdist源成员逐字节匹配，独立安装585/585零跳过、8真实必跑通过，基础前后无Flower；完整Python首轮被启动器120秒限终止，进程清理已核，原失败保留，新python-full-02同1010输入/1800秒总限继续且不改单测门槛。P4修正/诊断及72CPU通过只证本机范围，Windows同头3/6、目标OS候选尚待CI。未stage/commit/push，最终记录与AOCI待源码稳定后闭合；[交接](../handoff.md#当前续接与下一步)优先于下方历史停止状态。

完整Python后续结果已闭合于 `OWNER_EVIDENCE/python-full-02/closure.json`：4716通过、16跳过、2排除、883.55秒、1010输入稳定；15项旧SIG11跳过实际全部通过，peer202/federation407及8强制算法/网络均零跳过。额外独立安装 `owner-worker-01` 真实桥/HTTP owner登记授权→ClientApp Runtime→独立梯度→单次collect/审计/撤回1/1通过。统一原生all构建853.95秒、2816输入稳定，2056项CTest仍运行。前段“完整Python仍运行”为当时快照，不覆盖本段实际终态；剩余交付工作不变。

## 2026-10-31：保存已实现但未闭合的 S4 owner 工作树（历史）

按所有者最新要求停止实现并更新交接，保护40个未提交路径（27 tracked、13 untracked）、空暂存区及原六份交接/AOCI资产。基线 HEAD/main/origin/main/官方远端均6126c6a2；没有新增提交、push、CI触发或产品测试。本次前四文档及精确Git/源码SHA、官方CI与文档核验保存在 `OWNER_EVIDENCE/handoff-20261031T042050Z/`，主入口 [handoff.md](../handoff.md)。本节覆盖此前“后端零修改、尚未实现”的交接描述，下面同日首轮转交保留为历史。

owner/evaluation/models、Runtime认证路由、bridge本地冻结与原操作journal、20个发布Schema方法、独立Federation编辑器已经写入工作树。后端最终三版本各113/113及Runtime60/60零skip；bridge最后21项JUnit全过但typed rejection新专项未写，原生candidate-06为8/13通过、5失败且修正后未重跑。新proof仅在租约内原ID尚未保留且副作用前证明确定拒绝；原生消费proof与local prepare验证错误恢复尚待补全。文档、全量/独立安装、真实worker/network和最终AOCI维护均未闭合，不借用旧4589/402背书。

04:20:50 UTC官方CI核实6126 Desktop41163547328已failure（4/6 jobs成功），Mac/Windows原生仍失败；Runtime41163547349成功。Mac激活门已通过，seek/捕获修正仅候选方向、P4三源未改。终态等待前提满足不等于平台通过；通用路线、三待决和PET后置见handoff。

## 2026-10-31：首轮保存待办并转交（历史）

停止产品实现并确认后端代理零文件修改、零测试/构建/安装/委派，没有活动进程、shell session或CI监控。交接前直接核HEAD、origin/main及真实remote main均 **`6126c6a22cc19270aedd135fb97c09b949c49f9b`**，工作树干净。此前a5510bfa/10b784ba/b02a51cd/dd318ce2和记录/AOCI6126均已推送；最后包逐成员重绑与24对象11+13批维护、Verify/Check/Guide已经闭合。旧历史停止与未提交描述不再代表现状。

只读重查同head/attempt1的CI，03:29:04 UTC：Desktop41163547328仍运行（2项成功，其余编译），Runtime41163547349仍运行（9项成功，3.12打包），Docs41163547325/Secret41163547316成功；未观察到失败或新头完整原生验收结果。保存 `s4-network-20261030/ci-6126/handoff-20261031T032904Z.json`；下一代码push仍等整个Desktop终态。

更新四状态文件，明确owner/evaluation/models只是设计草案，列出固定身份/CAS恢复、数据登记与授权、独立线性评估/准入、bridge/UI及其验收顺序；保留S4其余、S5/S6/P5-S7、三待决和PET后置。没有产品改动或新增产品测试/点击验收，本次文档留工作树，不提交/push或重触发CI；文档核验及本次AOCI维护结果见 `NETWORK_EVIDENCE/handoff-transfer-20261031/closure.json`，接手入口 [handoff.md](../handoff.md)。

## 2026-10-30：恢复持续开发，提交网络主链与Windows有效内容裁剪（历史交付）

所有者重新激活通用目标。源码 `a5510bfa838e34e5555f0c6beaa4e0e6b04d190a` 正式提交已验证的25文件网络主链；仅在核实际暂存SHA与secrets-source-02完全一致、gitleaks零发现后提交，未夹带四状态/AOCI资产。Windows三文件外部候选核preimage后应用，实际merge-check全目标增量构建exit0、6.265秒；相关72/72零fail/error/skip、1.350秒，新三用例实际执行，三源前后稳定。暂存扫描零发现后提交 `10b784ba262fae7bbd26c5d1f2d39398019f5ec1`；证据 `s4-network-20261030/p4-next/candidate-02/`。

视频原生验收布局fixture另提交 `b02a51cdea47868e4c599fdbc763ed80ddd1e3b7`：Reports右侧却要求左侧并固定负drag的问题已改为按真实左右顺序，传入/保护原Viewer，真divider事件与完整媒体/同导航暂停时间/终态草稿门不变。实际probes-ON增量构建33.882秒、exit0，相关72/72零skip、1.326秒，源码稳定；证据 `NETWORK_EVIDENCE/p4-next/layout-01/summary.json`，实际单文件暂存gitleaks零发现。Linux只证明编译和相关CPU行为，不证明Mac激活或Windows原生视频/完整20轮。此fixture不进入Python包；最后Observed复核与本批24对象维护结果见closure。

Mac验收宿主追加修正 `dd318ce287bc1d52fd8da324026c321e984dc55c`：普通未打包test executable先显式设置并核验Regular激活策略，再请求自身窗口激活；原active/key/精确窗口合取与5秒UI观察门保留。失败/超时写固定before/after/final整数/布尔快照和计数，轮询不写盘、不识别外部窗口。`p4-next/macos-activation-01/summary.json`：Linux增量全目标构建exit0、32.146秒，原72CPU用例名称集合相同且72/72零skip、1.309秒，三源SHA稳定，暂存gitleaks零发现后提交。**Linux不编译Cocoa分支、不证明真实激活/OS像素/20轮**；38a未记录policy，不能断言原运行态就是prohibited。未打包程序默认策略与setter返回值依据 [Apple activation policy](https://developer.apple.com/documentation/appkit/nsapplication/activationpolicy-swift.enum/prohibited?language=objc) / [setActivationPolicy](https://developer.apple.com/documentation/appkit/nsapplication/setactivationpolicy(_:)?language=objc)，策略成功仍不替代原激活观察。

改为对WGC有效ContentSize与分配pool分别精确判定crop和origin，保留DPI/嵌套矩形/尺寸/格式/像素/20轮标准；Linux未编译Windows代码，目标平台仍待新CI。网络4589/402及最后guard26项证据范围保持原样。本批无产品UI点击变化；桌面授权/审计/模型准入继续。最后Observed测试头已完整review/ack，事务e23ffa808f1598ed4d270db9，Guide确认零pending/Recovery；正式24对象维护及记录/push/新CI见 `NETWORK_EVIDENCE/delivery-closure-summary.json`，不重复旧Observed8或基础17条交易。

## 2026-10-30：整理待办并转交（历史）

按所有者要求停止扩展实现，重写当前handoff为单一快照，保留旧四状态的未提交版本到 `s4-network-20261030/handoff-transfer-20261030T184019Z/before/`；历史事实仍保留在本日志和运行验收。Git直接核实HEAD/origin/main/真实远端均38a9fd43，25个已暂存网络候选保持原样；本轮仅改四状态文件，没有产品修改、测试重跑、提交/push或CI重触发。

完整Python已实际4589通过/31跳过/2排除，1000输入前后稳定；安装候选402/402零skip。全量和安装后仅补可选依赖guard，26/26和缺fastapi/httpx的collection验证分记，不冒称最终全量/实际Windows通过。已暂存25文件234011bytes的gitleaks零发现；文档和未来暂存须另扫。Desktop41097301277直接重查已completed/failure、4成功2失败，Runtime41097301247成功10/10；Mac成功601图、两媒体0轮0图，Windows原生0/6。外部Windows三文件patch仅复制环境211检查与语法/apply-check通过，未应用/编译Windows/运行WGC。

最新handoff写明源码入口、包/测试/CI的独立适用范围、外部证据、精确接手顺序、AOCI一个Observed指纹和8 missing/13 stale债务、三所有者待决及后续通用路线。正式索引仍dirty/stale；收尾工具结果见上述transfer目录。S4/P4、S5/S6/P5-S7未整体完成，PET新专项后置。

## 2026-10-30：恢复S4实际网络/Runtime链（历史进度，当前状态见上）

交接快照保存后，按持续目标恢复。实现owner绑定Hub run/独立FL CAS/action、冻结训练DTO、私有capsule/固定ClientApp worker、持久Node和显式coordinator/client、NodeAgent/CLI接入。真实TCP/WSS+三独立Runtime完成FedAvg/FedProx各两轮，12实际任务、独立逐样本梯度对照；全联邦+Hub352/352、零skip，25.99秒。安装态worker与工作树Node/协调器分记，最终全包安装和完整Python未提前宣称。

独立审查/红绿修复保留了RuntimeClient私有根重叠、模型同layout替换、早collect失败卡住、动态reservation授权竞态、取消次序和snapshot历史规模反例；100job/50普通对象从20,000状态读取降至100，仍重核未知任务当前归属。Hub三版本128次、Node实际42次均零skip；首轮网络夹具token长度、重复collect回执和取消race失败原证据均保留。workflow加入完整联合和精确真实训练/网络门禁。证据位于 `s4-network-20261030/`，详见handoff与runtime-validation。

当前业务未提交或push，基线38a9fd43；Desktop同run未终态、AOCI dirty/stale，最终包/全量/四状态/维护/暂存扫描/main交付继续。本轮无产品UI新增点击；S4/P4与后续主要路线未完成，PET专项后置。

## 2026-10-30：保存网络训练待办并转交（历史）

按所有者最新要求停止实现agent/CI轮询，保护8个未提交联邦网络草稿文件。本次仅核Git、源码差异、已有证据和CI并更新四状态文档，无新实现、测试、提交或push；草稿尚未语法检查，不能使用上一批230/4467等通过数字背书。Node服务/出站NodeAgent/CLI、持久协调轮次、新HTTP/WSS和训练测试及真实网络多轮仍待实现验证，具体接口和风险写入 [handoff.md当前首节](../handoff.md)。

已核HEAD/origin/main/真实远端均38a9fd433c1924a5bcc068e4bd1643e3f7c82bbf，基础源码11844b25及上一批AOCI/记录已推送；Observed8和17条语义收尾不重做。17:42 UTC直接重查Runtime41097301247成功、Desktop41097301277运行中，后续push门尚未满足。新WIP最终稳定后再维护AOCI/暂存扫描/交付；本次没有新Apply/Recovery。S4/P4及后续通用路线未完成，PET新专项后置，三待决未擅选。

## 2026-10-30：恢复通用目标，联邦基础与平台补修（历史，11844b25）

交接保存后继续开发；源码 `11844b257e3a88f0db1e08611624a295e64b13c2` 已本地提交21文件。隔离候选真实 f32/f64 聚合2/2、联合230/230零跳过，六成员与安装/工作树一致；三独立 ClientApp 六轮18份训练更新经过 consent/outbox，生产 FedAvg 与独立 moment-gradient 参考一致，撤回及不确定发送不重放通过。外部首轮脚本在最终审计读取误用分页键，失败保留，修脚本后新目录重验；未归因产品。

Windows backup fixture 三版本各21；watchdog 通过真实lane排队与模块局部可控时钟隔离暂存耗时，三版本各4，另有慢暂存红绿、误杀无关active负控，未改生产预算/等待时限。Mac 测试显式请求并观察自有key窗口，HTML视频解码后经真实divider调整完整媒体布局并保护原导航/时间；独立复核修正第三次拖动漏判和新几何基线丢失播放身份两处问题。WGC仍拒绝相同尺寸差异，仅补自身窗数值诊断。最终Linux编译及69 CPU通过，不冒充目标平台。

完整Python首次4467通过/31跳过/2排除、802.62秒、873输入SHA稳定；包含联邦230/peer202/两个watchdog实际通过。15个离屏SIG11 skip另补验且保留原full。源码暂存163597字节扫描零发现；本批记录、最终包、AOCI、push和新CI实际状态查 `FLOWER_EVIDENCE/delivery-closure-summary.json`，不能沿用旧handoff的WIP/未跑说法。前头bccb32d7 Desktop/Runtime已终态失败，Docs/Secret成功，推送等待门满足；S4/P4与后续路线尚未全部验收。

完整回归原15个离屏SIG11 skip已按JUnit精确选取，在私有Xvfb/llvmpipe软件GL下15/15、25.84秒、零跳过补验；873输入与full同SHA，原full证据未改、无源码/golden变更，不代替硬件或目标OS验收。

## 2026-10-30：按所有者要求转交待办（历史）

已核本地/远端 main 为 `bccb32d7b1da317121ee147ed54bf06a09b2f7c0`，上一 peer 源码 `51a795b9`、25 条 AOCI 维护及记录已推送。新增联邦基础及 SQLite fixture 修正保留为未提交工作树；本次只写交接和同步状态文档，没有继续实现、运行新测试、提交或推送。

已有联邦 admission 三版本各 150、consent 各 43，便携联合 228 通过；两个真实隔离 Flower 测试仍待执行。candidate-01 wheel/sdist 构建和隔离安装已完成，59 包依赖兼容；这不是聚合或完整安装回归。authority fixture 使用 closing 关闭 backup 两连接，三版本各 21 项通过，实际 Windows 修复效果待新 CI。证据入口、源码 SHA、测试命令及后续 S4/S5/S6/S7 任务均写入 [handoff.md](../handoff.md)。

bccb32d7 的 Desktop/Runtime 已终态失败；Docs/Secret 成功。Mac video 精确 key-window、HTML-video viewport，Windows WGC frame/item 几何及 viewport 仍失败；Windows 3.12 另有 watchdog 排队事件未到，尚未修。未将 CPU/便携结果替代目标平台验收。WIP 尚未到源码最终稳定状态，AOCI 收尾、实际暂存密钥扫描和交付列为接手任务；旧交易不重复，PET 新专项及三个待决边界不变。

2026-10-30续接：待办handoff检查点已保存，随后继续本批收尾；实际记录HEAD、push、AOCI批次/对齐、暂存密钥扫描与新CI由本批 `PEER_EVIDENCE/delivery-closure-summary.json` 记录。包最终比对绑定已测203项候选，不重复宣称安装验证；整份路线图尚未完成。

## 2026-10-30：S4真实连接后端与平台补修（代码51a795b9）

已推送基线`cfb8c561`，本批代码`51a795b9d09610f0bec31b526612cf849c230793`加入独立`stk.peer/1`、可选libdatachannel/libnice原生helper、双方Ed25519实际通道绑定认证、owner持久授权/撤销与单主项目服务。远端仅选project/grant/generation UUID，复用分页、CAS与格式15回执；不开放stdio桥、Runtime监听、脚本或模型设置。提交后元数据/响应失败保留原UUID的不确定结果；真实重连get原回执已验。

ACK修正前联合198/198、零跳过、43.191秒，最终端点/协议141/141、零跳过、35.433秒；三Python版本各143/143、真实crypto50.0.2，源码摘要稳定。首次联合因缺libnice.so.10退出127产生40失败，原日志保留；补齐开发运行库路径才通过，不冒称helper可直接发行。独立审查与真实反例修正了hello阻塞唯一reader、并发能力快照乱序和ready前业务派发。完整Python首轮4231通过/31跳过/2排除、1许可路径检查失败；仅改transport说明后原门禁1/1通过。最终ACK对象方向已两行修正，独立规范对端四项红→绿；fresh wheel安装202 peer+1边界203/203、零跳过、45.582秒，551份安装py/Schema一致、112模块来源正确，未含原生helper/libs。

cfb8 Desktop已终态：WindowsCPU发现修正获验证，Mac静态/spike通过但两个视频失败，Windowsnative六项零轮/零图；Runtime7/8、Docs/Secret成功。当前Windows精确完整WindowRect/DWM原点与物理DPI、局部三条queued鼠标消息保持原验收门禁。Mac改为单次pause后绝对1秒内有界查询，超时关闭；独立审查修正本批Block引用捕获，State/WK仍weak。Linux增量all与最终65项相关CPU通过，不替代目标平台。acceptance字段篡改单测去掉无关绘图子进程20秒耦合，6项定向含真实绘图/两任务扫描通过；历史Windows内部耗时点仍不确定。

本批无新增产品UI点击链；桌面配对、跨OS原生端点、授权文件传输、实际分阶段NAT/TURN443与端口预测、Flower及S5–S7继续。新的用户指南与正式规范入口已补；实际证据、Git和剩余任务见handoff及runtime-validation。

源码暂存294782字节，gitleaks8.30.1配合仓库规则/脱敏扫描零发现。九Observed路径独立审查及精确SHA绑定完成，ack事务74f56c840c267cc396c4732d已Apply；正式语义维护/最终包比对/推送和新CI事实以本批closure与真实Git为准。

## 2026-10-30：原子项目编辑回执与热日志恢复收尾中

格式15源码`59f4cdc3`已本地提交，本地 HEAD `59f4cdc3`，Hub 修复 `e5cea387`、Windows发现修正`e0139d9f`及Mac诊断`04aab01c`尚未推送。格式 15 工作树增加调用者保留 UUID 的原子编辑回执与本地桥/脚本接口，原请求摘要在生成对象 ID 前绑定；业务/修订/历史/回执同事务，查询及重复成功不编辑，旧库显式备份升级，未扩大智能体权限。真实800命令强制spill暴露只读打开无法回滚hot journal的问题，已限定精确776、初始读取身份检查、普通STKP header/文件身份验证及一次query_only原生物理恢复，恢复后重新只读打开，无业务重放或升级。

最后lstat异常精准注入已补，3.12核心78/78，3.11/3.14恢复各15/15；新wheel独立安装78核心+18桥96/96，471份安装py/Schema及真实bridge/worker来源核对。旧63/81及source_stable=false的4019项完整回归保留，不冒充最终。最终完整Python4034通过/31跳过/2排除、779.39秒，源码稳定；首轮完整原生2020/2022、零跳过，两个旧格式夹具漏删新表使升级回滚，已各补严格DROP且原断言不变，增量编译112.077秒及定向2/2已过，最终完整原生2022/2022、零失败/错误/跳过、483.82秒，源码稳定；当前全部必跑1546项匹配通过。格式15源码已本地提交`59f4cdc3`。

70449dc Desktop已结束：Windows材料测试可执行文件已链接，GoogleTest双标签破坏发现命令及后续属性，现用发现后TEST_INCLUDE_FILES保留双标签、120秒和空key/model unset；两个CMake版本的22项元数据及CPU标签覆盖均通过，Linux增量all构建退出0。Mac Markdown/HTML/PDF各20轮、140/140/160张真实OS图片摘要核对并目视，Viewer/草稿保留；两个视频已实际初始暂停及显式播放，随后Pause附近失败、0完整轮/0验收图，只增加有界状态/固定原因诊断，根因未证实。Runtime8/8、Docs/Secret成功，Windowsnative因上游构建失败skip。P4及S4–S7仍未完成，PET新专项后置。

## 2026-10-29：S3推送与Hub上传原请求幂等修复

S3交付头`70449dc15ed0635014f8bc66924bc7af123f0a8a`已推送main；32条语义分三批更新，1105条资产Verify/Check/Guide对齐，无Recovery或第三方冲突，记录暂存141405字节gitleaks零发现。新完整Overview1102条/23块交付确认及Challenge10/10通过，发生在最终索引更新前；不以旧收据断言新索引完整认知可靠。

S4连接基础调查复现现有Hub上传重复key误冲突：预算检查把原request覆盖成workspace.import伪请求。源码`e5cea387f048f937eb643a69bba11d81363d83d3`仅分开局部变量，保留路径规范化、预算和原始请求严格匹配。修前扩展23项10失败/13通过，真实Hub链也实测失败；修后3.12四文件49/49、3.11/3.14各23/23零失败/错误/跳过，真实分块失败续传、人工批准、桥重启和单次import/下载SHA链通过。旧错误journal不猜测修复，按transfer ID查询/恢复；暂存12404字节扫描零发现。详见[验收](runtime-validation.md)。

70449dc的Desktop40973399539与Runtime40973399517当前仍运行，Secret成功；后续修复尚未推送，等待Desktop终态。通用项目原子编辑回执及独立peer端点继续，S4–S7和P4平台未完成，PET新专项后置。

## 2026-10-29：通用训练S3b本机验收与平台补修

基线main `9da98ea1`。新增独立冻结训练capsule、精确ID划分、base权重/标准化初始化与同测试集baseline比较；任务和每轮损失持久保存，准备/启动分开，取消跨进程持久生效。绝对门槛、基准不退步及活动版本generation共同保护登记；崩溃只核已经发布的精确回执，不重训、不重新激活。新模型校验权重摘要，旧模型明确legacy未验证。增量桥/API与脚本已接，保留旧job/model读取及现有智能体权限。

后端/API联合198项通过；最后登记读锁/registry预算补修后服务/API83项通过。完整Python3911通过/31跳过/2排除、748.98秒，后续83项覆盖最后源差异；原15个离屏skip在私有Xvfb/软件GL下15/15通过，原full结果不改写。3.11/3.14材料矩阵各182通过/17因无Torch跳过，最后预算37项各无跳过通过，同一capsule跨版本SHA/IDs不变。预算补修后业务候选隔离安装五文件198/198、0跳过，470份py/schema与wheel逐字节一致；最终文档版用全成员比对绑定该已测候选，旧bootstrap196项及其SHA不冒充final。主线六代码提交见handoff；每次暂存扫描零发现。

桌面新30项（22状态/实际事件、8真实GPU）通过；首轮完整2016/2021、5失败分别是编辑器旧数量断言与英文标题撑宽旧布局，未更新golden，标题缩为Materials并校验18编辑器后39项通过。最终统一构建后完整原生2021/2021、零失败/错误/跳过、481.20秒，Linux现行必跑413次/1545匹配。四个中英宽窄/缩放布局固定预填起点校验→冻结→开始3点击、评估另1点击，保护Viewer/隐藏稿。16实际PNG验证生产draw_gpu曲线与零越界，受控图数据不作Torch或材料精度结论；真实Torch另由训练/服务专项核对。源码`c236816a`，状态/认知资产同批收尾，新交付头跨平台CI待核；[训练契约](specs/materials-training-1.md)。

9da CI实际发现Linux Phase0第4补丁越过旧上限、Mac测试NSString引用ARC不匹配和Windows持旧generation句柄时原子replace失败。已分别同步补丁上限4、显式strong引用与FileRenameInfoEx发布；最后Windows专项本机三版本各95通过/7项Windows实际测试跳过，保留原反例并新增真实多reader/Unicode门禁。Desktop已终态，Windows主回归成功，独立native六项0轮/0图；新几何/输入诊断保持原门禁，仍不能声称平台通过；实际证据见[运行验收](runtime-validation.md)。

## 2026-10-29：冻结视频与平台回归修复（本机验收完成，平台待复验）

基于main `f331dbe7b015220a821b8a5f83bbf852a4d19db5`，平台修复提交 `852860ae53327ae11fec9cb1a459d64f247bc1cd`、MP4提交 `8627d98184af62548a4b23b0d1e41e4f2856f6f3`。MP4改动覆盖文件报告入口及生成报告附件、独立HTML播放器、精确来源路径与显示摘要、单Range响应和局部原生暂停。原始MP4仍按冻结清单完整核验；模型请求只含资产元数据，读取、重开和恢复不播放或发送。旧14字段预览回执兼容，媒体预览使用renderer/2与显式source_path。

Python六报告文件三版本各348通过；最新全量3708通过、24跳过、2排除，之后目录junction补修三版本各86通过、6项仅Windows真实junction跳过。原生完整1991/1991、零失败/错误/跳过、471.76秒，Linux必跑405次/1515项匹配；最后路径断言修正后统一构建及编译5/5通过。隔离wheel十文件456通过/6项Windows专用跳过，导入来源仅安装包；最终文档版包做逐成员字节对照。新增四种中英宽窄/缩放场景以5次真实CPU鼠标点击预览和返回，实际OS播放仍须新头CI。平台探针默认关闭，视频两个格式各要求20轮、161张OS证据和21个独立会话，不以Linux Unsupported代替。

前头f331的Desktop40943343333与Runtime40943343293均已结束：Linux三项桌面成功，Windows CPU编译定位、Mac PDF事件及Windows native失败；Runtime六项成功、两Windows客户端失败。已据日志修正LaTeX的Windows跨API时间戳比较、原子回执共享删除句柄、UTF8测试读取，以及测试路径分隔符比较；Windows实际分支仍待新CI。Mac修正公开局部滚轮事件构造；Windows PE定位到epoxy wrapper间接空调用，生产七处WGL切换及独立预检改为系统入口后通知epoxy，保留失败结果/LastError。vendor1095/1095、补丁fuzz0精确重放及独立review通过；TLS零槽仍为机制推断，不冒称实际新平台已通过。修复源码暂存扫描37921字节、MP4源码318957字节，均零发现。详见最新[运行验收](runtime-validation.md)。

## 2026-10-29：冻结 LaTeX 工作流与桌面编译证据

源码 `51a01af143496eeaf58b39b4a6547af45e55176d` 增加 `latex-compile/1` 的明确准备/启动、冻结文件与编译器、取消/超时、持久日志与只读诊断；
补修 `3d4998d613597d93c6da4b7688775a7e854df57a` 使项目关闭/打开/刷新意图在旧句柄仍存在时也拒绝晚到源码跳转。两者均直接在 main，
记录与托管认知资产随本批收尾；新头 CI 待核。普通 Viewer 图与报告读取不会启动编译，也不自动创建报告或预览。

本轮先完成源码主链的完整 Python **3644 passed、24 skipped、2 deselected、零失败、803.73秒**，
完整原生 **1956/1956、零失败/错误/跳过、474.70秒**；Linux 现行必跑规则405次调用、1487项匹配通过。
最后再修中断遗留 `.new` 阻塞回执、Mac PDF 缩放色条判据及关闭项目前ACK的定位窗口：
三 Python 版本的新专项各 **79/79**，末次统一构建后原生定向 **29/29**（19像素、5编译、5文件/布局）通过。
全量结果属于最后这些小修之前的已冻结主链，不能冒称最终1963项已跑全量。

中英固定1440×2200、1×、a3最大化/侧栏560的失败运行详情起点，各6次实际鼠标点击完成日志与源码检查，
另1次点击拒绝已修改源的旧定位；Viewer状态完全不变，未发送模型请求或自动保存/预览。
真实 TeX Live 2026 验证两页 PDF、`section.tex:2` 失败日志、明确保存报告、删除工作文件后重开及ZIP逐字节一致。
隔离 wheel 的79项与相同真实TeX链也通过，456份Python/12份Schema及279项sdist内容逐字节核对；
最终状态文档版由发行机器比对记录，详见[运行验收](runtime-validation.md)与[LaTeX指南](latex-workflows.md)。

前头3ac89623 Desktop已全部结束：Linux三项和Windows主回归成功；Mac正式Markdown/HTML及独立原型通过，
PDF首页已显示但被1–2px混色边界判据拒绝，已保存原图并补严格CPU重放/正反例；新平台20轮仍待验。
Windows四项在WGL清理后其他线程RIP0崩溃，现有栈记录循环漏掉RIP0，已仅修诊断，未断言驱动根因。
Runtime8/8、Docs、Secret成功。前头Desktop推送等待门已满足。本批尚不代表P4或整份计划完成，视频和第4–8项继续，PET新专项后置。

## 2026-10-27：独立桌面报告生成表单（本机验收完成，平台待复验）

交付头 `035f7bd960d0a5b72bc83db7608342e15951ea68` 已推送main，包含报告源码 `15edede3`、运行器 `5a6f6fd1` 和记录/认知资产；记录暂存gitleaks扫描141729bytes、零发现。新[Runtime CI](https://github.com/sijintech/stk/actions/runs/40274892305)已结束：三个LinuxPython版本、desktop、web、control均成功；Windows3.11/3.12各3057通过、100跳过、327排除、2个setup/teardown错误（537.95/558.16秒）。日志明确为 `test_invalid_or_oversized_generated_body_is_rejected_atomically` 的默认案例名称包含整段超长正文，写入 `PYTEST_CURRENT_TEST` 超过Windows环境变量32767字符限制；没有运行到该案例断言，不能写作报告后端验证失败或通过。
修正保留原始大正文与五类拒绝断言，只显式使用简短案例ID；本机3.11/3.12/3.14报告全文件各46项通过（3.68/3.70/3.68秒），日志 `/tmp/stk-report-generation-testids-python311.log`、`python312.log`、`python314.log`，真实Windows仍待下一头CI。新[Desktop CI](https://github.com/sijintech/stk/actions/runs/40274892272)已结束：Linux主回归、Linux包、干净机冒烟及Windows主回归成功；Mac正式报告3项OS像素超时、独立原型20轮161图及最终零分配通过；Windows独立原生4项均在真实llvmpipe4.6预检后0xC0000005退出、零图。Docs `40274892334`、Secret `40274892259`成功。前头Desktop已终态，下一批仍须自己的CI，不能把本机测试作平台通过。

源码 `64205ba809aacef568d1d85637ee777c9ac8aa50` 已提交main，接入独立桌面AI生成表单、每标签局部控制器及workspace v3，普通v1/v2可读。准备、发送、编辑和保存分别明确操作；复用来源选择器，四类来源分页与完整复核、可选真实快照附件，原UUID回查不重发。三处控制器状态缺陷与跨帧/同帧字段提交票据失效已修，按钮继续核原来源及token。
统一构建退出0；专项 **26/26、零失败/错误/跳过、14.96秒**，`/tmp/stk-report-generation-desktop-tickets.xml`，覆盖14项真实stdio桥、丢回执/取消/换项目/重启，以及中英×1440/560宽度的完整UI、8类恶意workspace状态原子拒绝和恢复零隐式读取/发送、无中间frame的连续Tab与问题重入。首轮14中一例在桥自动重开时重复open，修测试等待；UI首轮18/26后修正用Enter事件输入换行，22/26再暴露真实跨帧票据问题，修正后26/26，不隐藏失败。新增CMake使用NO_PRETTY_VALUES与稳定参数名，三平台必跑规则纳入控制器和UI两类。

固定默认Report模式未最大化、a3报告活动、旁有既有Viewer且隐藏Python/AI草稿；中英各1440×1000和560×1000，实际四场景均 **39鼠标点击、14键盘动作、6文本事件、0滚轮、1指针移动**。14键含一次Ctrl+Space最大化，最大化后的流程仍39点击/13键；四来源、PNG、完整复核、选择上下文与端点/模型、准备/单次发送、编辑和保存均计数。结果是实际读回report/2，四类冻结来源和已删除工作副本的冻结PNG、精确编辑正文；一发一保存，无自动asset/preview读取，Viewer payload/相机与隐藏稿内容保留。证据 `/tmp/stk-report-generation-ui-clicks.xml`、`.log`；WM/CPU事件与UI文本路径不等同真实OS/GPU/IME验收。既有AI页面没有独立has_unsaved_changes覆盖，本轮只证明其内容保留，不声称修复该缺口。

Mac验收harness按实际客户区真实拖动分隔条扩大上排并保留Viewer，关闭popup后移开指针等待Tooltip遮挡解除；PDF改两页独立内嵌960×96 RGB图而保持原强像素判据。555033字节PDF由pypdf6.21.2 strict解析，两页、各276480字节图片、精确六色及第二页反序通过，`/tmp/stk-native-pdf-verify.log`；不代替Mac实际显示。Windows仅补WGL生命周期flush阶段与有限异常地址栈，证据只在显式测试目录、无内存dump；本机无Windows编译，真实崩溃位置与修复仍待下轮CI。
最终复核另发现保存成功后等待项目刷新没有遵守90秒跟踪上限，已补齐截止处理：停止唤醒并保留原UUID和编辑正文，后续明确查询仍能确认同一份报告。新增真实桥回归1/1通过（2.47秒），最终统一构建退出0。完整原生 **1951/1951、零失败/错误/跳过、465.52秒**，日志 `/tmp/stk-report-generation-desktop-native-final.log`、JUnit同名`.xml`；包含 **15项控制器＋12项中英宽窄UI，共27项报告生成用例**，全部实际运行通过。当前Linux必跑脚本405次核对、1481项匹配通过，`/tmp/stk-report-generation-ui-required-final.log`。上一轮1950/1950是在这项边界修正前完成，不混作最终结果。中英2522键、零问题，diffcheck通过；源码暂存gitleaks按 `.gitleaks.toml`、redact扫描258612bytes、零发现，`/tmp/stk-report-generation-ui-staged-gitleaks-final.log`。最终wheel/sdist已离线重建（`/tmp/stk-report-generation-ui-package-final.log`）；wheel中452份Python文件与当前源码逐字节一致，sdist中的运行验收、报告指南、报告测试、生成后端及worker五文件逐字节一致，证据 `/tmp/stk-report-generation-ui-package-verify.log`。本批平台CI仍待新头复验；最终记录与认知资产随本批收尾，具体对齐以托管资产及Verify/Check/Guide事实为准。P4的LaTeX、视频、原生平台验收及第4–8项继续，PET新专项后置。

## 2026-10-26：运行器身份发布与执行门禁（本机完整回归通过）

源码 `5a6f6fd1f6a1f4b66862a649bb29fdf176bcae02` 已本地提交main，尚未推送。确定性复现证明旧worker可以在program.json发布前运行用户程序；新Linux任务先fsync及原子发布PID/创建时间，再经匿名管道授权同一PID执行。门禁使用隔离启动环境，任务环境仅在授权后传入，恢复原生信号默认行为；exec确认后才开始时间/内存监测，取消和信号可中断等待。既有任务继续各自冻结副本。
Python3.12/3.11/3.14的Runtime各36项通过；对应完整桌面调用链4/4、零跳过/35.65秒。最终wheel/sdist离线重建，python -I确认模块来自隔离安装目录后，报告与Runtime82项通过。最终完整Python3562通过、24跳过、2排除、零失败/705.26秒；本次暂存密钥扫描24861bytes、零发现。新Mac/Windows与Runtime CI仍待推送后复验，前头CI失败与本机复现不作确定因果等同。
本轮新AOCI完整交付22块、1085条，交付确认与严格Challenge9/10通过；读取时治理尚未对齐。最终源码认知收尾以本提交托管资产及Verify/Check/Guide事实为准。P4完整桌面AI表单、LaTeX、视频与第4–8项继续，PET新专项后置。

## 2026-10-26：报告模式与来源绑定的生成后端（本机验收，平台修复待复验）

源码 `15edede30c46bc6639eeab910d739bf01fdb762b` 已本地提交main，尚未推送。报告布局复用原区域和编辑器，三模式独立几何/活动标签/面板偏好；旧两模式文件可读，Viewer和隐藏稿保留。中英1×/2×固定默认1000×900起点每模式2点击，切换不执行或发送。
新增 `stk.report-draft/1`、冻结报告输入与 `/2` 内联编辑正文；真实主上下文计入16来源，复核SHA静态绑定选择，发送时重查全部公开标签，运行来源限本机/机构内。输入合并192KiB、正文64KiB，准备阶段预留最坏JSON转义和资产预算；侧车路径提前拒绝。保存仅完成请求、固定输入/回复SHA和一次CAS；ZIP包含原输入/回复证据。普通报告/1保持。
原生reader支持/2并验证本地正文/元数据，精确UUIDv5和原请求日志绑定仍由后端；独立桌面生成表单继续开发。
统一构建、完整原生1924/1924、零跳过/469.57秒，当前Linux全部必跑1454匹配通过。新后端46、strict桥/真实worker4、普通兼容192、3.11/3.14专项各196与wheel隔离46通过。完整Python首轮3549通过/2失败，两处精确发布集合遗漏已修、相关91通过，未冒称首轮全绿。
已核前头b32fd0c7全部终态：Desktop Linux成功，Mac仅正式报告前置创建失败，Windows多标签discovery命令拆分失败；本批分别修Ready等待和两处单标签，真实平台仍待新CI。Runtime3.11另有丢失worker失败，本机可证程序先执行/身份后发布的窗口，后续修正与结果见上；其余Runtime7job、Docs/Secret成功。详细日志和最终结果见运行验收，本任务继续P4与通用路线。

## 2026-10-25：正式报告文档视口（本机完整回归通过，平台待验）

源码 `023aa66` 已本地提交 main，本批新 CI 待核对。资源会话与 WKWebView／WebView2 适配迁入 `stk_document`，原型与产品复用单一实现，原生候选仍默认关闭。
ReportsEditor 显式准备 Markdown／HTML 后移动完整校验集合到独立文档宿主；原文、PNG、创建稿与 Viewer 独立保留。
同步项目范围通知、区域移除及 UI 遮挡失效在下一帧前撤销或隐藏原生资源；Tab 方向返回分别绑定前后控件，
鼠标进入文档的焦点意图只由当前会话的下一次安全布局消费。统一全部目标构建通过，报告专项 167/167、零跳过／35.91 秒，含 40 个 GPU 场景。两点击的中英宽窄视口布局已核，无窗口图像不证明浏览器显示。另补只读刷新与冻结讨论延迟导航的确定性回归，修正后的导航与完整工作流 14/14、零跳过通过。
PDF 已复用旧 preview 合同接入单入口完整二进制准备、独立 MIME 能力发现与相同宿主；新增 PDF 与既有报告专项 **97/97、零跳过／21.37 秒**通过，含 29 个新增 PDF 场景；首轮重复 GoogleTest 宏标签编译问题已修正后重建成功。
无 Blender、默认关闭原生候选的干净构建完成，生产资源回归 **14/14、零跳过**及必跑检查通过，没有拉取 WebView2 SDK。
真实 ReportsEditor 按钮链已完成正文与 PDF 两页 OS 验收程序：MD／HTML 各 140 图、PDF 160 图，20 轮／21 次准备；Windows 滚轮持久 guard 拦截上行，采用与宿主一致的向内像素取整。最终程序重建成功，Linux PDF 冒烟明确失败 Unsupported、0 轮／0 图；双平台呈现仍待 CI，Cocoa 不声称已证明零 responder-chain 上行。
正文独有像素判据及负例已构建，`DocumentEvidence` **13/13、零跳过**和必跑检查通过；不把合成 classifier 图当原生正文显示。
最终完整原生 **1903/1903、零失败／错误／跳过／454.71 秒**，当前 Linux CI 完整必跑脚本的 **1433 项匹配全部通过**。原型与正式三格式验收均接严格退出码包装器，三 Python 版本各 **12/12** 真实子进程自检通过；Windows 暂存命令通过真实 CTest 解析，修正手写测试目录变量为空的问题。独立审查还发现验收程序在 Viewer 元数据异步回复前记录全状态，已先完成正常只读加载再取保留基线，重新构建成功。
Windows 测试 job 使用固定摘要的进程局部 Mesa 双 DLL 和显式 llvmpipe／WARP，记录实际 GL 模块与 renderer、捕获 adapter，缺能力仍失败；本机未取得发行归档，实际布局／依赖与 Windows 执行待 CI。
输入法、跨屏 DPI 与浏览器内存仍未验收。
前头 `43e5652` Desktop `40247654158` 已终态失败。Mac job 成功，20 轮／161 PNG 摘要及最终 guarded 0 块／0 字节已核；Windows 编译与 CPU 成功，独立 native 在 OpenGL 1.1／缺 WGL_ARB_create_context 的运行器预检失败，未达到 WebView2 显示。Linux 1811/1812，
唯一 `WorkflowSimulationPython.MuFerroWorkflowRunsEveryRowOnThePickedRuntime` 在转讨论等待时失败，已按下述确定性场景修正，须新 CI 复验。
新增可控调度回归已在 0.63 秒复现“冻结讨论捕获完成、延迟导航遇只读刷新而丢失”；反例仍拒未捕获讨论和其他页面。
窄范围修正后的导航及完整工作流 **14/14、零跳过／36.41 秒**通过；工作流测试等待启用且验证捕获被接受，未放宽原超时。

## 2026-10-25：报告额外来源选择（本机验收完成）

源码 `b23cfc0` 已提交 main，在 `0268d68` 上增加只读完整来源复核、可选来源摘要 CAS 和桌面四类来源选择。普通草稿只保存类别／UUID，恢复须明确重审；待确认创建保留完整清单与原 UUID，不重放。来源复核与创建捕获比较在资产读取和写入前完成，之后观察推进不会改写已捕获来源。
三 Python 版本定向各 131 项、桌面 27/27、报告图形 32/32 和 wheel 隔离读回通过；完整 Python 3502 项通过、24 跳过、2 排除；完整原生 1809/1809、零跳过，1339 项必跑通过。修复了预算错误被 ValueError 捕获、测试 hello 缺协议版本、JSON 容器混用编译问题及恢复后异步测试等待。固定报告起点创建 13 点击；GPU 准备复核 12 点击，未创建，Viewer／隐藏稿保持。
前头 Desktop `40242092854` 已确认 Windows 编译失败：共享 Windows 8.1 宏下新 DPI API 声明不可见。仅为候选动态解析 User32 接口，缺任一接口仍失败；未提高产品最低系统，也未跳过原生门禁。macOS 实际完成 20 轮／161 张 OS 图及关闭检查，但最终 guarded 门禁失败，修正 `9358ca2` 已将零块／零字节检查移至引擎静态析构后，晚静态／真泄漏／早失败三项严格退出码及相关 26/26 通过，不减基线或放宽门槛。修正仍须新 Mac／Windows CI；旧日志没有分配标签，不能确认全部块身份。前头整 run 已终态失败，Runtime／Docs／Secret 成功。P4 与整个通用目标继续，PET 新专项后置。

## 2026-10-25：报告资源读回与原生显示证据（本机验收完成）

源码 `84d918b` 在 `841910f` 上增加独立预览准备：验证净化入口，再串行核对图片回执、清单、字节和 SHA，全部成功才发布完整集合；来源代次变化废弃旧回执，原文／Viewer 保持独立，恢复不自动准备。候选实际消费 Screen 布局完成／失效订阅，切换标签和最大化在下一帧前隐藏，关闭先退订；没有把布局同步写成已解决原生输入路由。
Mac／Windows 加入自身窗口 OS 捕获及两页空间像素标记、20 轮／161 图和失败证据；Windows 先核 DPI／GL，Mac 验证放在既有打包上传之后，缺 Runtime、权限或显示能力均失败，不自动安装或修改权限。
最终完整原生 **1791/1791、零跳过／428.09 秒**，485 条必跑规则核对 **1321** 项；专项 47/47，无 Blender 独立构建 17/17。首轮测试编译问题、Viewer 元数据基线和 Ready Client restart 无操作均已修正，未放宽生产门禁。源码暂存扫描 **163187 bytes、零发现**，i18n 与空白检查通过。前头 Desktop **5/5**、Runtime **8/8**、Docs／Secret 成功，本批新 CI 待确认；具体证据见[验收](runtime-validation.md#2026-10-25报告资源读回与原生显示证据本机验收完成)。
正式报告页仍为原文／PNG；双平台 OS 显示、完整浏览器／PDF、AI 报告、额外来源选择、LaTeX、视频与报告模式继续，第 4–8 项未完成，PET 新专项后置。

## 2026-10-25：报告预览资源准备（本机验收完成）

源码 `31c1e06` 追加 `project.reports.preview_resources`：先净化 Markdown／HTML 入口，再按同一修订与清单摘要逐张读取图片；图片描述符不等于字节校验。排除次级 HTML／Markdown／CSS／PDF，CSP 只授予具体图片路径，保留 32 MiB 总预算和旧预览兼容。独立审查修复新响应 Schema 沿用宽类型的问题，Python 与 C++ 均补负例，三平台 CI 强制新协议测试实际运行。
完整 Python **3483 passed、24 skipped、2 deselected**，完整原生 **1748/1748、零跳过**、必跑 **1278**；随后夹具清理修正的相关 **45/45**，三版本专项、wheel 与源码包隔离读回及暂存密钥扫描通过。前头 `78f51b2` Desktop `40234644345` 已全部结束、4/5 成功，Windows 唯一工作模式测试析构 SEH 无栈；源码确认测试把 shell 早于借用状态的编辑器销毁，已按正常生命周期先清编辑器并保留旧回调验证。不能据 Linux 通过认作同一 Windows 崩溃已经解决，新头 CI 待确认。具体证据见[验收](runtime-validation.md#2026-10-25报告预览资源准备本机验收完成)。
本批没有新增桌面预览动作或点击验收；原生富文档、PDF、AI 报告、LaTeX、视频与报告模式仍未完成，第 4–8 项继续，PET 新专项后置。

## 2026-10-25：桌面创建冻结报告（本机验收完成）

源码 `a10025587fb0b85d386c31f7980f10b2fa2cf01b` 在报告标签加入显式创建表单，按有界快照摘要选取完整冻结清单、资产路径与唯一入口，一次编辑保存；恢复仅还原稿件，修订变化后须明确重审。不确定创建保留原 UUID，不自动重发，换桥会话后仍可只读确认。新增分页摘要 API 不改变旧快照接口或项目格式。
独立审查修复工作空间预算检查前的 JSON 隐式整树复制；新增超大／深状态、同帧字段和旧回调、已落库延迟回执换会话回归。原生专项 17/17、图形 24/24，固定报告起点创建 8 次真实点击；完整原生 1747/1747、零跳过，Linux 必跑 1277 项；完整 Python 3468 passed、24 skipped、2 deselected。三 Python 版本、发行包隔离读回、i18n 与源码暂存密钥扫描通过，失败修正和点击范围见[本批验收](runtime-validation.md#2026-10-25桌面创建冻结报告本机验收完成)。
源码按 main 交付：前头 `93d3a06` Desktop `40230875886` 已全部结束并 5/5 成功；Runtime／Docs／Secret 成功，前头推送等待条件满足，本批新头 CI 待确认。P4 富文档、PDF、AI 报告、LaTeX、视频与后续通用目标继续，PET 新专项后置。

## 2026-10-25：冻结报告存储与桌面读取（本机验收完成）

本批源码 `3f4af5e898e8f739591bb6fb05d46e872cce0452` 新增 `stk.report/1` 普通报告表、冻结快照资产与上下文／运行观察来源，接入桥、脚本和独立报告标签。选择元数据不读资产；显式读取校验完整字节，导出完整来源 ZIP 不覆盖、不改修订；Markdown／HTML 另经可选 Markdown／nh3 净化，原始、清单和显示摘要分别核对。
独立审查修复了合法深目录的相对 URL 长度误拒，以及嵌套坏上下文仍被标为 readable、触发严格桥 internal_error 的问题。原生测试准备修复重复 GTest 宏、默认标签身份与 Python 默认基线的错误假设；生产草稿保护未放宽。首轮完整 Python 的接口清单漏项和旧提示断言已修正，最终完整 3434 项通过、24 跳过、2 排除，相关 217 项；3.11／3.14 新专项各 204 项、报告原生 10/10、GPU 16/16 通过。完整原生首轮仅旧注册计数漏计报告页，修正为 17 并断言报告注册后最终完整 **1732/1732、零跳过／414.48 秒**，当前 Linux CI 必跑 **1262/1262**。最终发行包读回与暂存密钥扫描通过。
前头 `b7a6589` 的 Desktop 4/5，Windows 技能大依赖测试是唯一失败；已改为逐次等待准确修订和加载成功，保留有界冲突恢复。前头已全部结束，推送等待条件满足；本批新头 CI 待确认。macOS／Windows 文档候选编译已有 CI 证据，但未作原生实际嵌入验收。报告创建表单、浏览器/PDF、AI 报告、LaTeX 和视频仍未交付，整个通用目标与 PET 后置顺序不变。实际证据见[本批验收](runtime-validation.md#2026-10-25冻结报告存储与桌面读取本机验收完成)。

## 2026-10-25：原生文档嵌入候选本机验证

源码 `10e6423f5f5bfc18f66047fda686f323ae702fa1` 按 main 交付。新增默认关闭的 P0 原型：窗口层借用平台句柄，独立 WKWebView／WebView2 适配器、内存资源清单、HTML／PNG／PDF 夹具和与 Viewer 同窗的标签／最大化／关闭冒烟。清单只提供绑定项目、资源、来源版本及预览会话的资产，关闭使旧 URL 失效；没有项目目录授权或页面主机桥。
修复独立审查发现的 Host 初始化顺序、HEAD 长度和 Windows 迟到导航事件问题。首轮资源与 X11 通过，Wayland 因 1440×1000 首帧超过 1280×800 测试显示触发协议错误；固定私有显示尺寸后最终 **28/28、零跳过、21.12 秒**。无 Blender 的独立资源构建与 **14/14、0.14 秒** 通过，源码暂存扫描 **153963 bytes、零发现**。三平台 CI 已加入显式编译，不能把 Linux Unsupported 路径或仅编译当作双平台嵌入通过。
前头 `3dc178d` 的 Desktop `40219610785` 已全部结束并 **5/5 成功**，Runtime、Docs、Secret 成功，推送等待条件已满足；本批新 CI 另行核对。菜单相交时临时隐藏、IME／PDF／DPI／截图和浏览器内存仍待实机验收，P0 未选型、P4 未完成。复现和实际限制见[运行验收](runtime-validation.md#2026-10-25原生文档嵌入候选本机验证)。

## 2026-10-25：真实窗口大项目性能本机验收完成

基准源码 `639614b29ad26e5f7536e3333b82e1806200ceaf` 已本地提交，待记录及索引收尾后推送。前头 `cf2b40d` 的 Desktop `40216687457` 已全部结束并 **5/5 成功**，Runtime `40216687448`、Docs `40216687646`、Secret `40216687630` 成功，推送等待条件已满足。
新增可选 GHOST 基准、固定显示尺寸、真实字体和截图后置握手，保留 CPU 工具；两个目标构建成功。两表各万行的 X11／Wayland × OpenGL／Vulkan 四组合、每模式三次共 **24 次**全部完成，分页绘制及交换调用返回中位 **2.90–3.07→0.69–0.85 秒**，原生采样峰值 RSS **356–392→196–229 MiB**。全部零脚本执行、零 Viewer 求值、零协议错误且项目修订保持 0；本机 llvmpipe／lavapipe 软件渲染不能代替硬件或其他平台性能证据。
独立审查修正帧计数的过强呈现声明，截图分配移到开屏计时和 RSS 采样之后；超时清理按 PID 身份冻结并终止仍可追溯的后代，启动前检查 pidfd 能力。已经退出父进程的重挂后代仍不在保证范围内。Python 定向 **15 passed、3.23 秒**；既有显示／工作空间回归及必跑检查 **12/12、零跳过、19.91 秒**；最终 CPU 和窗口各一对 100 行冒烟通过。源码暂存 gitleaks 扫描 **43827 bytes、零发现**。
当前读取周期的 AOCI 全量输出曾被宿主截断，已终止该链，不声称完整认知可靠；仅依据绑定源码进行本批验收和后续增量维护。数值、重现方式和未完成项见[运行验收](runtime-validation.md#2026-10-25真实窗口大项目性能本机验收完成)。下一步是 P4 原生文档嵌入验证，第 3–8 项继续，PET 新专项后置。

## 2026-10-25：全局用户技能目录（在研）

前批工作流技能源码 `bc964f2` 与记录头 `f9a78c2` 已推送；23 条 AOCI 增量更新全部应用，Verify／Check／Guide 对齐，记录暂存扫描 128977 bytes、零发现。Runtime／Docs／Secret CI 成功，Desktop `40213263506` 待结束。
源码 `6fa89943b8011730146c52e8cc339f21aa05c6d4` 已本地提交、尚未推送，继续第 2 项：本机 SQLite 方法库保存不可覆盖的 `id@version`，项目记录 UUID 与方法身份分离。全局发布绑定已审阅源修订／摘要，明确选择原版或新版本；发布回执有独立身份，源项目修改或关闭后仍可只读核对，不改变项目修订或撤销历史。目录默认不再加载第三方节点入口；用户方法执行环境保持未检查，固定后再明确实例化和运行。
三 Python 版本相关各 **128 passed**；新增库最终 **24 passed**。原生定向及必跑 **34/34、零跳过**，中英固定详情起点保存到库各 1 点击。审查与验收修复最高版本原样发布、导入后追加方法身份、损坏回执的错误码及 pending 身份保留，以及 JSON 字段顺序误判；完整 Python **3221 passed、24 skipped、2 deselected**，完整原生 **1688/1688、零跳过**，Linux 必跑 **858/858**。最后目录名称上限对齐 4096，由三版 Python 桥端各 7 项及重建后的桌面34/34补验；源码暂存扫描141654 bytes、零发现。前头Windows CI尚未结束，推送门禁继续保留。失败历史、点击范围与本机库限制见[验收](runtime-validation.md#2026-10-25全局用户技能目录在研)。

## 2026-10-25：工作流技能发布与实例化（在研）

在 `3a1204f` 子流程源码基础上继续第 2 项，源码提交 `bc964f26fbc233381371bb55576f166a75995107`。新增 `workflow.document`，在同一源修订冻结根流程、递归子流程和引用分析，保留共享对象与每份定义摘要。表、字段和快照单独声明依赖，创建时明确映射；默认值及 `$literal` 不参与字段替换。整套创建一次 CAS／撤销，不加载引擎或启动运行。
桥、Python、权限分类及桌面发布／创建入口已接入；项目技能完整历史和集合预算提升到 8 MiB，普通分析预算保持原值，项目快照 12 MiB／事务 1000 命令边界继续生效。
新增桥端 5 项通过；首轮模板字段层级的 schema 不一致及测试删除命令形状已修正。独立审查发现损坏字段类型会使整个技能列表读取失败，已改为单记录 invalid 并补测。最终完整原生 **1681/1681、零失败／错误／跳过**，Linux 必跑 **851/851**，相关桌面 **62/62**；Python 3.11／3.14 相关各 **84 passed**，3.12 新专项 **25 passed**。完整 Python **3190 passed、1 failed、26 skipped**，接口清单漏项已修且相关 **13 passed**。中英发布 4 点击，追加／实例化／打开各 1 点击。源码暂存扫描 **147182 bytes、零发现**，前头 Desktop 已 **5/5 成功**；本批 CI 待确认。具体范围与失败历史见[运行验收](runtime-validation.md#2026-10-25工作流技能发布与实例化在研)。

## 2026-10-25：子流程与工作流封装（在研）

基线 `fc14bc6ec945a2b5218323098a14eafa43614f18`，源码 `3a1204f4a9fa0618d0523cdca85b8b5595d1fb5e` 已推送 main。新增版本 2 工作流接口，显式声明输入、输出和参数，按稳定实例路径展开重复调用并冻结所引用文档。
准备运行拒绝引用环、依赖环、接口类型／单位不匹配与实际行值越界；执行使用既有任务日志与执行器，删除子流程定义不影响旧冻结运行。
过期检查按来源分支比较，位置、标签与名称不使结果过期；空的透传子流程仍保留依赖门禁。
旧格式保持可读，显式保存升级在一次 CAS／撤销事务中补接口列。桌面已加入公开输入／输出／参数、类型化默认值编辑和父子独立标签页导航；保存与运行继续明确分开。修正导航目标临时 JSON 的生命周期，返回与重入保留两边未保存草稿。
接口默认值始终作为字面量；显式 `$literal` 保留形似引用的 JSON，编译和冻结记录保存真正的字段绑定来源，避免误读行值或误报结果过期。三 Python 版本核心各 78 项通过；新增桌面及必跑 5/5、零跳过，中英公开输出＋保存为 2 次点击。完整 Python 3166 项通过、24 跳过、2 排除，最终字段来源修正由相关套件补验；最终完整原生 **1674/1674、零失败／错误／跳过、398.37 秒**，Linux 必跑 **844/844**，工作流技能发布尚未实现。
Python 扩大回归 268 项通过；原生构建完成，相关 90/90、零失败／跳过，必跑 54/54。具体用例、初始失败与分版本结果见[验收](runtime-validation.md#2026-10-25子流程与工作流封装在研)。
上一用户技能源码 `fc14bc6` 的 Desktop `40199278362` **5/5**、Runtime `40199278388`、Docs `40199278457`、Secret `40199278445` 已全部完成成功；新源码 Desktop `40208002864` 已全部结束并 **5/5 成功**；Runtime `40208002879`、Docs `40208002935`、Secret `40208003007` 均已完成成功。
源码 AOCI 共 21 条语义更新已 Apply，Verify／Check／Guide 对齐；暂存 gitleaks 扫描 271348 字节、零发现。后续交付记录按同样流程维护；本批不等于完整工作台交付。

## 2026-10-25：用户分析技能（进行中）

基线 `e9f5fb6e255572d204a8a44c3204fac647913123`；本批增加 `project.skills.publish_analysis` 和原生“从保存分析创建技能”。
项目内用户版本冻结图、提交参数、所选输出与来源摘要，新增 `graph.document`；创建和追加明确区分，不覆盖内置目录技能。
恢复旧版本后继续从历史最大版本追加；复制分析保留空输出和大整数，不加载目录或执行节点。
用户版本沿用项目 CAS、撤销、备份及工作空间迁移；来源切换、项目重开、旧按钮及隐藏草稿均沿既有边界处理。
三 Python 版本相关各 145 项、另补真实图执行各 1 项通过；原生相关及必跑 28/28，零跳过。
固定技能库起点创建 4 次点击，既有选中用户技能与来源起点追加 1 次点击；英文 1× 和中文 2× 通过。
首轮夹具、命令和编译失败保留在[验收](runtime-validation.md#2026-10-25用户分析技能进行中)；完整原生 **1666/1666、零失败／跳过、393.74 秒**，Linux 必跑 **836/836**。源码 `fc14bc6ec945a2b5218323098a14eafa43614f18` 已推送；Desktop `40199278362` 5/5、Runtime、Docs／Secret 均已完成成功。

## 2026-10-25：图像附件与卡片缩略图（进行中）

接续分页源码 `e30150b`，源码 `e9f5fb6e255572d204a8a44c3204fac647913123` 已推送 main，增加 JPEG／WebP／GIF／BMP／TIFF 预览和显式卡片缩略图。
复用受保护的本地文件读取与冻结摘要，转换像素另给大小、摘要及方向／第一帧信息；原 PNG 和文本读取保持兼容。
卡片／看板直接加载，缓存有数量上限且与来源、修订、视图绑定，失效即释放纹理；不改 Viewer 或启动执行。
Python 3.12 附件／脚本 59 项、3.11／3.14 含智能体边界各 86 项通过；原生定向与必跑 22/22，通过实际一点击加载、晚回调拒绝和纹理释放。
3.12 扩大桥与表格回归 177 项通过；完整原生 1662/1662、零跳过，Linux 必跑 832/832；21 个 AOCI 条目与 3 个观察文件已维护核对，Verify／Check／Guide 对齐，跨平台 CI 已完成成功。范围和日志见[本批验收](runtime-validation.md#2026-10-25图像附件与卡片缩略图进行中)。
暂存 gitleaks 约 157 KB、零发现；Runtime `40196571054`、Docs `40196570995`、Secret `40196571044` 成功，Desktop `40196571079` **5/5 全部结束且成功**。

## 2026-10-25：大项目分页接入（进行中）

基线为 `fe083a3d4f7296182f178fa3e7390e5fb311cc07`，本批源码 `e30150bb47c7064c945a4c561d99e02fdea5ae69` 已推送 main。
新增同修订的结构目录和记录分页接口，支持按稳定记录 UUID 定位页，保留类型与跨页依赖求值。
表格工作台直接绘制查询返回的记录，多个编辑器各自持页；共享详情仅补充当前选中记录，切换时释放前一条额外缓存。
修改审阅显式读取完整基线并检查修订，避免把未缓存行误算为新增。文件树读取只覆盖文件索引及所需依赖。
三 Python 版本相关各 **87 passed**；最终原生相关及必跑 **109/109、零跳过，22.10 秒**。英文 1×、1440×1200 的排序网格与详情起点，未缓存记录 **1 次鼠标点击**后正确显示详情，修订与 Viewer 保持。
已补桥契约和脚本示例。后续原生首次打开接入结构目录与最多 200 条记录，按 UUID 异步选择、取消和同修订校验；
新增 5 项测试通过。扩大回归 **249/257**，8 项失败揭示上下文切表、文件定位、模拟批次与旧同步测试假设；
现补独立上下文分页及最多 100 条选中记录缓存、共享导航等待、批次分页和结果按运行 ID 查询。
后续扩大回归 **262/268**，仿真定向仍曾 **5/7**；日志明确记录目录预期修订 3、实际 4，不能当作同步测试等待不足。
现对目录／记录分步读取的 Conflict 最多重启整组读取三次，不混合发布不同修订、不重放修改；连续修改超限时保留错误供明确刷新。
LAMMPS 结果查询按其真实响应契约校验表、修订、记录与运行身份，不再要求该接口不存在的 project_id。
最新构建成功、定向及必跑 **16/16、零跳过，40.59 秒**；新增一次并发修改恢复、连续修改有界停止和脚本第 452 行精确选择用例。
完整 Python **3102 passed、1 failed、24 skipped、2 deselected**，唯一失败为脚本清单漏列两个新只读方法；保持精确清单校验并补齐后相关 **32 passed**。
完整原生 **1619/1656、零跳过**，37 项失败来自异步读取准备状态及旧格式测试替身；修正后对应复验及必跑 **37/37、零跳过**，包含 32 项中英文、宽窄、OpenGL／Vulkan 图形场景。最终完整原生 **1656/1656、零跳过，391.15 秒**，相关必跑 **342/342**；中英 **2339 键、零问题**。
较早工作流测试的桥断连未取得确定根因，不能把后续通过解释为已证明同一缺陷被修复；原始失败和精确复验路径见验收记录。
新增 `benchmark_table_query.py --mode opening`：两表各万行，后端全快照／分页首读为 **7.473／0.0566 秒**，
Python 分配峰值 **102.79／1.68 MiB**，响应 JSON **44.75／0.45 MiB**，首批记录与元信息一致；不含原生 UI／RSS。
工作空间打开现复用目录／记录读取器，在打开修订下验证所选记录后原子采用；冲突或记录缺失保留当前桌面并关闭新句柄，归档仍保存完整数据库。
新增三项分页恢复测试及三平台必跑；定向首轮 **23/24**，补齐新窗口服务就绪等待后 **24/24、零跳过，9.01 秒**，未放宽产品忙碌门禁。
两表各万行的真实桥／原生 CPU 首屏基准各三次中位 **2.670650→0.448939 秒**，原生采样峰值 RSS **190.40→31.17 MiB**，响应 **9.75→1.10 MiB**。
使用短合成文本、暖 OS 缓存和 CPU 替代文字度量，不含真实窗口／GPU；RSS 与响应计数范围、首次测量断言修正及复现命令见[验收](runtime-validation.md#2026-10-25大项目分页接入进行中)。
工作空间接入后的完整原生 **1659/1659、零失败、零跳过，386.77 秒**，当前 Linux CI 必跑检查 **829/829**；跨平台 CI 已完成成功，真实窗口性能仍待验收，不能以该批分页功能标记第 2 项完成。
AOCI 共 46 个受影响条目已完成增量维护，并复核 15 个观察文件；修正一项文件规模标签。Verify／Check／Guide 均确认 aligned、complete=true、next_action=none，全部规模标签匹配；这不代表全量认知校验通过。暂存 gitleaks 扫描约 478 KB、零发现，提交前差异检查通过。Desktop `40193509900` **5/5**、Runtime `40193509895` **8/8**、Docs `40193509904`、Secret `40193509919` 均已完成成功。

同时实查前头 CI：Desktop `40177991251` **5/5**，Runtime `40177991233`、Docs `40177991272`、Secret `40177991359` 全部成功。
下方项目技能版本记录中的待确认状态已由这些结果解除。

## 2026-10-25：项目技能版本

源码提交 `073c608a271c4dea001a49432879f174f2afab7c`，基线 `c6c39f3856189530db983d3c6f4dba4704c477e4`。
项目以普通托管表保存完整技能定义和图模板，按确切版本与摘要固定；升级追加更新版本，恢复保留历史。
读取、恢复和创建分析不依赖安装目录；创建复制图与来源身份，不绑定输入或执行。
六个新增桥方法与 Python 门面共用修订 CAS／撤销，丢失回执只按原 UUID 读取检查。
原生控件核对会话、修订和编辑器寿命，保护活动输入及隐藏草稿；工作空间恢复仅同项目选择，技能表不作为工作流参数表候选。

最终构建通过；技能定向及必跑 **33/33、零跳过**，含8个真实桥项目版本用例和16个图形用例。
完整原生 **1639/1639、零跳过，375.61 秒**；完整 Python **3083 passed、24 skipped、2 deselected，678.04 秒**。
三 Python 版本相关各 **74 passed**，中英 **2336 键**一致，源码暂存 gitleaks **144.16 KB、零泄漏**。
中英文宽窄／1×与2×按钮事件、Linux软件OpenGL／Vulkan通过；不替代 macOS／Windows 真机验收。
前头 Desktop `40171064126`、Docs `40171064146`、Secret `40171064141` 均完成成功，Runtime `40171064147` 两项 Windows 作业失败。
附件测试错误地用规范化 CRLF 的文本读取作预期；本批改原始UTF-8字节并增加LF／CRLF夹具，产品预览行为未改。
源码已提交；本批新 CI 待确认。点击起点、证据与限制见[验收](runtime-validation.md#2026-10-25项目技能版本)。
技能版本仍是实验格式，不冻结节点实现、依赖和说明包正文；用户目录、自定义流程封装和直接技能执行未完成。
通用目标继续，PET 新专项后移。

## 2026-10-25：附件详情预览

源码提交 `bc2896a89f2e357d30ea8bda3a246190604cc411`，基于 `b1673ee`。
新增独立只读桥方法及 Python 门面，从当前项目的文件或冻结附件读取有界 PNG／UTF-8 文本；
元数据解析仍不读取正文。读取核对文件及目录身份、完整大小与摘要，冻结内容不符则拒绝；
原生再次校验完整字节摘要并解码 PNG，文本不解释标记。单文件 1 MiB，文本显示 64 KiB，PNG 单边 4096／4194304 像素。
记录详情明确点预览；换来源、关闭详情或过期回调不采用旧内容，独立纹理随预览释放，不改变 Viewer 或项目修订。

最终构建成功，原生相关及必跑 **59/59、零跳过，11.27 秒**；新增 4 项通过已有三平台必跑集合覆盖。
完整原生首轮 **1622/1623、零跳过**，唯一失败是损坏 PNG 测试要求错误必须在 header 阶段报告，
改为检查 PNG 解码错误及无图像后复验通过。完整 Python 首轮 **3052 passed、1 failed、24 skipped、2 deselected**，
唯一失败为脚本目录预期集合未加入新读方法；修正后脚本／附件相关 **25 passed**。
此前 Python 定向 **75 passed**，3.11／3.14 相关各 **48 passed**。两处最后修正仅涉及测试，未再次重复完整回归；不将复验混写为首次全绿。
中英文 **2318 键**一致，暂存源码 gitleaks 按 `.gitleaks.toml` redact 扫描 **47.98 KB、零泄漏**。
前头 `b1673ee` Desktop **5/5**、Runtime **8/8**、Docs／Secret 均已完成成功；新 CI 待推送后确认。
固定已选对象格起点 **2 次点击**，项目修订／选择和 Viewer 不变。图片像素与纹理生命周期用真实桥及模拟 GPU hooks 验证，
未新增跨平台真机图片显示验收。更多格式、缩略图和 P4 文档渲染仍待开发，PET 新专项后移。
完整证据及限制见[验收](runtime-validation.md#2026-10-25附件详情预览)。

## 2026-10-25：看板拖动

源码提交 `752d1ea9016ff6730fa7cb3df4a22e9ecfd5a811`，基于 `35637ea`。
通用 UI 增加容器拖放区域，卡片文字和空白可拖，子按钮与下拉框保留自身行为；空列目标覆盖整行高度。
按下时冻结分组、版本和回调，目标遵守裁剪、遮挡和模态；只在有效左键松开时一次交付，取消／失焦／身份漂移不提交。
表格单选状态复用原来的类型化修改路径，保留选项 UUID、缺省与 null，一次 CAS 和撤销；公式／引用状态只读，
源修订或视图变化、任何相关编辑器草稿均阻止过期写入。同列拖动不产生修订，不改变共享选择或 Viewer。

两次构建均退出 0；定向及必跑 **64/64**，完整原生 **1619/1619、零失败、零跳过，360.29 秒**。
新增 4 个容器事件用例及 3 个实际 Python 桥用例，三平台必跑已覆盖；中英文 **2315 键**一致。
当前看板起点 **0 次额外点击＋1 次拖动** 改状态，一次撤销恢复；控件另验 1×／2×，实际项目手势为 en／1×。
暂存源码 gitleaks 8.30.1 扫描 **46.40 KB、零泄漏**。前头 `35637ea` Desktop **5/5**、Runtime **8/8**、Docs／Secret 均成功且已结束。
记录头 `b1673ee` 的 Desktop `40167186317` **5/5**、Runtime `40167186293` **8/8**、Docs `40167186299`、Secret `40167186297` 均已完成成功。
只改单卡当前页状态，不重排卡片、跨页移动或定时边缘滚动。详细证据见[验收](runtime-validation.md#2026-10-25看板拖动)。
通用目标继续：富预览、首次大表读取、子流程与技能版本等仍待交付，PET 新专项后移。

## 2026-10-25：表格填充柄

源码提交 `b2b076d669e6089fd700d4ff02097aaee60adb0b`，基于 `d1493fa`。
通用网格增加选区右下角填充柄与目标预览，按可见顺序沿单轴重复；捕获按下时的选择、排列、版本和回调，
只在左键松开时交付完整映射，Esc／失焦／模态／版本或选择漂移取消。最多 1000 个目标格，超限拒绝且提示。
工作台检查字段类型、单位和选项一致，直接复制原始类型值、缺省／null、对象及引用／表达式定义；
同来源行的公式绑定迁到目标行，外行引用保持稳定身份。整批复用一次 `project.apply` 和撤销；草稿阻止写入，不运行模型或任务。

首次构建因新测试使用错误的模态接口失败，修正后成功。定向首轮 **56/57**，唯一失败为有序 JSON 的键顺序比较；
改成规范对象内容比较后 **57/57**，必跑 **57/57**。完整原生 **1612/1612、零失败、零跳过，365.81 秒**，新增必跑 **8/8**。
中英目录 **2314 键**一致。默认 1440×1200 布局下 **1 次选格＋1 次拖动**，不改变 Viewer 数据、相机序列或启动求值。
暂存源码 gitleaks 8.30.1 按 `.gitleaks.toml` 扫描 **31.03 KB、零泄漏**；前头 `d1493fa` Desktop **5/5**、Runtime **8/8**、Docs／Secret 均成功。
记录／索引头 `35637ea` 的 Desktop `40163712446` **5/5**、Runtime `40163712511` **8/8**、Docs `40163712431`、Secret `40163712458` 均已完成成功；本机自动事件不替代真机人工验收。当前页范围、同类型限制、数列推断和静止指针滚动边界见[表格指南](design/multidimensional-tables.md)，详细证据见[验收](runtime-validation.md#2026-10-25表格填充柄)。
通用目标仍继续，PET 新专项后移。

## 2026-10-25：工作模式布局

源码提交 `85630acbb04f419ac7a13b0d5f99e08990cd91f9`，基于 `027798f` 增加当前窗口准备／分析两种布局，分别记忆分栏位置和比例、最大化区域、活动标签及面板偏好。
窗口管理器先验证完整区域集合，再移动现有区域对象；不从布局重建编辑器。模式标签以实例寿命身份跟踪，
重复类型、跨区移动和隐藏草稿保留；新增／关闭区域在两模式共享，旧集合不匹配时沿用当前分栏。
普通布局和完整工作空间保存可选模式偏好；先在临时树验证全部内容再采用，旧文件无需迁移，坏模式不替换原桌面。
菜单旧回调核对 Shell、屏幕及原模式，活动文本和拖动期间拒绝切换；不调用保存、运行或发送。

本机构建通过；定向 **72/72**，必跑 **60/60**；中英文及 1×／2× 默认 1000×900 逻辑像素布局每次切换 **2 次点击**。
完整原生 **1604/1604、零跳过，371.84 秒**；源码暂存区 gitleaks 扫描约 **64.57 KB、零泄漏**。
前代码头 Desktop `40156836215` **5/5 成功**，本批推送等待条件已满足；随后记录／索引头 `d1493fa` 的 Desktop `40160203772` 已全部结束且 **5/5 成功**。更新使用指南和真机验收清单，真实平台交互仍待验收。
详见[验收](runtime-validation.md#2026-10-25工作模式布局)。通用目标继续，PET 新专项后移。
`d1493fa` 的 Runtime `40160203774` **8/8**、Docs `40160203773`、Secret `40160203795` 也均成功。

## 2026-10-25：表格按需查询与平台修正

本批已提交并推送 `027798ff0d5ca914b947401d14c47e4787430133`；暂存 gitleaks 扫描约 69.46 KB，无泄漏。
新 Runtime `40156836276` **8/8**、Docs `40156836343`、Secret `40156836355` 成功；Desktop `40156836215` **5/5 成功**。macOS 编译修正已由该次 CI 验证。

通用编辑器和 AI 开发工具以 `4f919c7` 推送；暂存 gitleaks 无泄漏，推送前已确认前产品 Desktop 完成。
新 Runtime `40154110795` **8/8**、Docs `40154110805`、Secret `40154110886` 成功。
Desktop `40154110887` 已全部结束，Windows 与三项 Linux 作业成功；macOS 编译失败：同条 `auto` 声明混合 `uint64_t` 和 `size_t`，Linux 类型别名相同未暴露。
拆开分析和工作流历史测试中各五处声明；本机重建成功，跨平台尚待新提交验证，保留原失败日志。

开始第 2 项工作台完善：`table.query` 去掉全项目快照，普通视图先按稳定行序分页；筛选／分组／排序仅取相关字段，
最后返回整页完整类型值和定义。跨表、离页和循环依赖用迭代闭包读取，复用同一求值器，损坏祖先缓存仍触发重建，
整个读取保持一个 SQLite 修订且不写缓存。新增可复现合成性能脚本和查询回归；不改数据库格式或桥契约。
三 Python 版本相关各 154 项通过，随后增加的 1100 层离页链也分别通过；完整 Python
**3040 passed、22 skipped、4 deselected**（本轮排除 desktop/perf，随后补充的深链不在该次收集内），
原生 **1592/1592、零跳过**。新查询专门回归最终 **16 passed**。
两张各 10000 行／8 列表、200 行页面在 tracemalloc 下的普通查询为 0.0456 秒／1.68 MiB，
全快照参考为 7.3027 秒／102.79 MiB；筛选、排序与原参考结果一致，具体口径见[验收](runtime-validation.md#2026-10-25表格按需查询与平台修正)。
桌面初始共享快照、粘贴规划和表交换仍有全量读取；不把后端单项改善写成大表产品验收完成。PET 新专项后移。

## 2026-10-25：通用编辑器本机验收

接续既有产品工作稿，完成分析／工作流局部撤销重做、类型化参数与独立文字稿、表格记录详情和看板状态修改的构建及回归。
共享参数 JSON 拒绝重复键、溢出、非有限值、BOM 与尾随内容，保留数值类型与负零；历史限 100 步／8 MiB，恢复不携带历史。
表格按稳定字段／记录 UUID 编辑隐藏字段，保留公式定义与精确类型；管理和扫描动作读取点击时输入并拒绝过期来源。

审查并修复：同行 GoogleTest 宏重复标签、恢复上限常量和测试辅助引用导致的编译失败；
隐藏工作流尚未绘制时仍须保护恢复的步骤名称草稿；两个表格用例等待异步字段控件真正就绪，避免空指针访问。
首轮完整原生发现 6 个默认布局金样差异，同时确认新历史按钮把“三维”导航压至窄条。
缩紧历史与定位按钮，加入最小可用宽度断言，再仅更新六份默认布局金样的节点工具栏块。

最终本机原生 **1592/1592、零跳过**（374 秒），相关必跑 **164/164**；Python 完整 **3025 passed、24 skipped、2 deselected**，
3.11／3.14 的工作流、契约及项目桥相关各 **49 passed**。点击、失败轮次与原始日志见[验收记录](runtime-validation.md#2026-10-25通用编辑器本机验收)。
本机测试清空产品 key 并移除 model 环境变量，未发收费模型请求。
基线 main／origin/main 为 `7e0e6b1`；前产品 Desktop `38956471084` 已完成 5/5 成功。本批尚待提交和新 CI，不能用旧 CI 代替。
开发目标仍覆盖计划第 2–8 项；PET 新专项后移，原有能力保留；三项待所有者决定的边界没有扩展。

## 2026-10-24：AI 开发工具配置与上下文测量

依据所有者“按照建议执行”完成官方固定版本的本地接入，不依赖先前未取得的 ZIP。
安装 Serena 2.1.0（Python 3.13 隔离环境）、jscpd 5.4.2、Knip 6.42.1；检查器有独立 package-lock。
项目 Serena 只读、六工具、三语言，使用 ide 单项目 context／tools interface；本机 Codex 配置已生成，
Cursor／VS Code 的 Serena 路径已改为可移植命令。其他服务未冒称全部配置完成。

实际 MCP 验证三例定义正文与源码一致，Python／C++／TypeScript 引用均非空并抽查调用点。
初次 C++ 查询用了错误的符号路径；从 .cc 定义查引用又得到空集，改从 .hh 声明后找到编辑器与测试。
health exit 0；全量预热在 684/1039、约 4 分钟时主动中断，默认按需使用，不宣称完整索引完成。
clangd 首次下载失败已用官方包与安装代码中的 SHA-256 修复；未改产品网络／端点／密钥设置。

jscpd exit 0：531 源文件、27 组重复、484 重复行；增加 cpp-header 避免漏掉头文件。
Knip web exit 1 为问题报告：23 项 export、11 项 type export；显式登记动态 Service Worker 后消除未用文件误报。
三个候选 accessorInfo／viewCamera／FRAME 在模块内仍被调用，未删除实现或建立债务基线。
docs 扫描也产生报告，但依赖未完整安装，缺工具与动态组件发现仍需按文档站环境复核。

小函数已知位置查询没有显示 Serena 比精确 rg 更省返回文本；语义引用提供了更丰富的上下文。
handoff 48045→12788 字节（−73.4%），计划 85489→78018；两份共减少 42728 字节。
AOCI 单轮约 430 KB、21 块，工具估算 143015 tokens，并经历上下文压缩重复加载；这些不是模型账单测量。
详细命令、各例字节／时间、初次失败和平台限制见[工具指南](ai-development.md)。

main／origin/main 为 `7e0e6b1`；原有 22 产品文件 SHA-256 全部保持，未构建产品、未提交推送、无新 CI。
前产品 Desktop 38956471084 本轮复核 5/5 completed/success；当前工作稿已知编译失败仍待产品任务解决。
Python 脚本与 JSON 语法、编译数据库绑定幂等检查通过。缓存、日志、下载及本机配置均忽略提交。
当前聊天未热加载 Serena；独立 MCP 成功不代替 Codex／Cursor／VS Code GUI 验收。
受管文档／工具文件的 AOCI 收尾按实时 Guide 执行，机器结果留本地审计记录；未更改完整覆盖或认知合同。

## 2026-10-24：AOCI 完整接续与工作树维护

按所有者要求执行 AOCI。服务 `0.1.0-rc21` 连续交付正式索引 1031 条／21 块，约 142832 个机器估算 tokens；Host 交付确认成功，Challenge **10/10**，覆盖率 100%，系统框架掌握度自评 90%。第一次提交仅因答案字段名不合 JSON Schema 被拒；只读取得实际 MCP tools/list Schema 后，将字段名改为 object_identity／core_f，语义答案未变，未作语义重试。
初始 Guide 报告 16 条过期及 7 个 observe 测试路径。模型阅读改动与行为证据后，通过 scope acknowledge 受治理确认全部 7 项，随后 Guide 已无 observe 待复核；正式 Entry 按机器签发的完整批次维护，不缩小范围、不改 Root／Meta 或配置。
源码复核区分了当前实现与历史索引：共享参数 JSON 解析已移到 analysis_document；分析／工作流有局部历史入口和原子结构编辑；工作流回复已有可选枚举／边界／说明元数据；参数文字采用明确应用及独立迁移；表格记录字段选择与状态修改已有工作稿。索引同步不证明其生产闭环，保留既有原生编译失败及未运行测试的事实。
fetch 后 main／origin/main 仍是 `7e0e6b1bc59ef252af72f9aca5f82a9708f7e0de`。重新查询该头的 Runtime 39598657750 **8/8**、Secret 39598658037、Docs 39598657687，以及前产品 Desktop 38956471084 **5/5**，均 completed/success；它们不覆盖当前未提交产品稿。
22 个既有产品源码／测试文件与本轮开始 SHA 一致；本轮只维护 AOCI 托管资产和四份状态文档，不运行产品／材料测试，不发模型请求，不提交推送。机器批次、终态 Verify／Check／Guide、源码 SHA 及审查记录在 `/home/mnemora/opt/stk-validation/aoci-20261024/`；实际结果见[验收记录](runtime-validation.md#2026-10-24aoci-完整接续与工作树维护)。以下旧停止记录保留为历史。

2026-10-23 AI 上下文工具方案再次接续：**仍停在前置边界，工具试用未验收；本轮不提交、不推送**。
依赖范围澄清：交付 ZIP 仅是 AI 上下文工具试用的材料前提；表格／节点编辑器开发本身无需等待该 ZIP，其当前停点是 AOCI 完整认知前置。宿主条件恢复后可继续产品开发，不将工具试用包设为额外开发门禁。
同日宿主只读诊断：本机 CLI 0.163.0，运行中的本机 app-server 0.160.1；已用 0.160.1 二进制生成仓库外静态协议 schema。所查接口未明确提供按字段读取三项当前上下文设置的方式；未执行 config/read 或 thread/read，未启动／重启服务、读取认证／配置／聊天正文或发起模型请求。该版本差异不证明当前会话绑定关系或压缩原因，不能视为 AOCI 前置已解除。诊断证据在同日目录 resumed-host-diagnostic/。
进一步核对 0.160.1 静态协议：ConfigReadParams 仅有 cwd／includeLayers，Config 响应允许 additionalProperties=true；未证明存在排除凭据的逐字段读取，故未实际调用 config/read。这不是发现了真实泄漏或断言配置含密钥，只记录无法满足本轮安全读取要求的边界；未取得当前上下文有效值。
同日 17:08，本次 16:54 恢复后的三轮现场检查均未解除同一 AOCI 前置阻塞，旧 blocked 审计不计入；最新 Check 仍 exit 1、结构有效／治理未对齐，24 个原有非文档修改文件 SHA 未变。已达到重新标记 blocked 的门槛，停止继续扩展宿主诊断，完整产品目标保持未完成。恢复条件仍为宿主能够完成并保留按现有规则进行的正式 AOCI 流程；所询问配置值只是诊断证据，不另增审批或永久门禁。证据为 resumed-host-diagnostic/third-turn-audit/。
同日 08:50 UTC，本次恢复后的第三次现场复核仍为 Check exit 1、结构有效／治理未对齐；24 个原有非文档修改文件 SHA 保留。独立状态审查确认达到本次恢复后的连续受阻门槛，旧 2026-10-22 审计不计入；等待宿主条件的非敏感有效值与交付材料路径，不扩大产品完成声明。
重新确认 main／origin/main 本地引用均为 `7e0e6b1bc59ef252af72f9aca5f82a9708f7e0de`；28 个修改路径、24 个既有非文档修改文件 SHA 均保留，当前主树并不干净。
本轮文档更新前的 `aoci check --json` 退出 1：结构有效、治理未对齐，16 项 code_stale（含四文档变化）、1 组 observed_pending；另有 16 项既有技术跳过，不能计作新增故障。未完成当前完整认知或 Attestation，不重复上次受宿主压缩打断的完整加载。
候选脚本／Serena 项目配置／工具指南及所查常见 Codex／Claude 项目配置仍不存在；Cursor／VS Code 配置存在，正文未读、未改。当前宿主列出 9 个 AOCI 工具，无 Serena 工具匹配；Serena 安装及运行状态未验收。
交付 ZIP 在仓库、`/home/mnemora/xcheng`、`/tmp` 的可读取范围未找到；后两处搜索均退出 2，有权限缺口，不能断言全盘不存在。Downloads 与 `/mnt/data` 当前不存在；已询问所有者包的本地路径，尚未取得答复。
未检查交付包 README／manifest／补丁、未核对 13 文件、未建独立工作树或应用补丁；不根据摘要重建。安装、index／health、真实客户端验收、两项代码查询、duplicates／Knip 均未执行。
本轮只记录停止事实；AOCI 正式维护及收尾仍未完成，生产功能与上下文工具均不宣称验收通过。证据目录：`/home/mnemora/opt/stk-validation/ai-context-trial-20261023/`。

2026-10-22 连续受阻复核：原始请求及随后两次续接均停在同一 AOCI 前置条件；本轮没有产品功能进展。
最新 `aoci check --json` 退出 1，`structure_valid=true`、`governance_aligned=false`；AGENTS 与 24 个原有非文档修改文件 SHA 未变化。
未再次全量加载、未修改业务代码或提交推送；现有停止记录的 AOCI 维护仍未完成。生产级表格／节点编辑器目标未缩小、未验收。
恢复需要能够完成并保留完整当前认知的宿主条件，再完成正式流程与维护；不以反复检查替代开发进展。
本轮证据：`/home/mnemora/opt/stk-validation/aoci-stop-recheck-20261022/blocked-audit/`。

## 2026-10-21：AI 上下文工具试用前置受阻

按所有者新范围停止产品源码写入，仅准备工具试用；不提交、不推送。实际 main／origin/main 同为 `7e0e6b1bc59ef252af72f9aca5f82a9708f7e0de`，原有 28 个修改路径保留。
先检查规则及 Git，调用 AOCI 预检：服务 `0.1.0-rc21` 可用，12 项语义过期、7 项 observe 待复核，治理未对齐，当前完整系统认知不可靠。
随后只尝试一次正式完整重载：总 21 块／1031 条，收到前 4 块／171 条后发生宿主上下文压缩；前四块未出现工具截断，但丢失此前正式正文，未提交 Host 交付确认或 Attestation。
按用户明确停止要求终止认知链，压缩后仅重读运行合同以确认边界；未继续游标或再发完整重载，不用历史收据、摘要或局部检索补认知。
文件级准备检查发现三个候选文件及常见项目级 Codex／Claude 配置路径均无文件；Cursor／VS Code MCP 文件存在且未修改，未读取配置正文。
交付包在仓库根、Downloads、项目父目录未找到；检查范围有限，不能断言全盘不存在。未检查交付包内容、应用补丁或创建工作树，未自行重建配置。
安装、索引、health、真实客户端验收、两项源码查询、duplicates 与 Knip 均未执行；没有精简候选报告或上下文 token 收益测量。
独立 critical review 仅复核停止报告的状态与算术，明确传输比例不是认知验证、未执行不是通过；最小记录仍待 AOCI 正式维护，不宣称闭环完成。
停止事实记录、文件清单、预存文档改动及审查意见保存在 `/home/mnemora/opt/stk-validation/ai-context-trial-20261021/`；不保存正式索引正文、聊天全文或凭据。
原生产品构建上一进程已退出 1：`analysis_parameters_editor_test.cc:701` 同一行两个 `ASSERT_NO_FATAL_FAILURE` 生成重复标签；本轮没有修复、重跑或把此前 CI 当作当前稿结果。

## 2026-10-21：AOCI 宿主复核与本地草稿索引同步

按所有者的索引请求暂停后台产品写入，确认当前宿主的 9 个 MCP 工具已加载且实际调用成功，服务 `0.1.0-rc21`，无需重启。
普通 Overview 完整读取 1031 条、21 块、约 142654 个机器估算 tokens，交付确认及 Challenge 9/10 通过；当时治理因本地源码变化未对齐，未宣称当前完整系统认知可靠。
3 项 observe 测试变化经阅读后明确确认；最初 Maintain 的 observe 阻断发生在正式索引零写入之前，按返回动作解决后取得新的完整 8 项批次。
逐项读源码及关联证据、复核 API／分类／约束，用受控 CAS 一次写入 8 条，未缩小范围；源码 Verify／Check／Guide 均退出 0、完整对齐。
Critical review 保留实际限制：历史仅在会话内且尚未接 UI，参数 metadata／文字保存运行门禁／迁移恢复未闭环；新增测试未运行并有一处确定编译问题。
11 个 desktop 开发文件 SHA 与开始时一致，未在索引任务夹带修复、运行或提交。首次索引 `fd73f48` 已推送；本次依赖未提交源码的增量留工作树，待产品验证后一起交付。
核对 `7e0e6b1` Runtime 39598657750、Secret 39598658037、Docs 39598657687 均完成成功，前产品 Desktop 38956471084 仍为 5/5 成功；未替本地稿宣称新 CI。
本机面板 HTTP 200、仅监听回环；入口访问凭据不进入仓库，未调用外部模型或读取产品密钥。原始校验与源 SHA 保留在仓库外 refresh 证据目录。

## 2026-10-21：AOCI MCP 接入与首次仓库索引

按所有者要求确认宿主接入后建索引：动态重载已提供 9 个实际可调用工具，无需重启 Agent。
服务 `0.1.0-rc21`，按新项目 Guide 建立 Volumes v1 Root／Meta／Code；初始化顺序问题只恢复本轮新建且尚无条目的资产，原备份保存在仓库外，未绕过既有审批或覆盖用户资产。
范围按当前模块、第三方、归档及生成资源职责裁定，固定策略后完整建立 1031 条语义条目，16 项空文件／二进制／超大对象按机器结果技术跳过。
路径与符号扫描只作定位和验收，Tag／F／R／A／S 由模型读取实际文件与关联后撰写。

Critical review 全面核对 327 条原生桌面公开 API，修正 25 个路径的名字或可见性错误；
213 条关系分号经原作者逐条确认后规范为逗号，另修正 LAMMPS 结构规范的专用节点关系及少量字段表达。
全部 240 项正式差异经 Cognition Optimization 完整批次写入；逐条比对最终稿零差异。
修正后 Verify、Check、Guide 均退出 0，1031 条、完整对齐、预算健康，无缺失／过期／孤儿／未绑定条目或未决恢复事务。
一次宿主全量读取曾被输出截断，未计为完整认知读取通过；索引建立及机器验收的结果独立记录。

基线 `2bb0aba`、main 直接交付；前代码 `76715e4` 的 Desktop 38956471084 已 5/5 成功。
索引提交 `fd73f48` 已推送，精确 Runtime 39595993694 **8/8**、Secret 39595993567、Docs 39595993557 均 completed/success；本轮索引／文档路径未触发 Desktop 工作流。
最终四文档稳定变更后按机器批次维护；Verify／Check／Guide 均通过，暂存 gitleaks 8.30.1 使用仓库配置和 redact 扫描零发现，新增本地链接 4 项零缺失、暂存空白检查通过。
只修改索引和文档，未重跑产品回归／PET MD，未发外部模型请求、未读取产品密钥、未更改模型端点或网络策略。
检查原始结果与审查证据保存在本机 `/home/mnemora/opt/stk-validation/aoci-20261021/`；[验收记录](runtime-validation.md)注明范围和限制。
[面板](http://127.0.0.1:43999/)仅监听本机，访问凭据及运行时文件不进入 Git。后续稳定变更仍需维护索引。

## 2026-10-15–16：表格三格式交换与工作空间文件（76715e4跨平台验收完成）

新增 `TableIO` 共享服务与直接工具栏，CSV/XLSX/JSON 均先预览再明确导入，SHA／修订门禁、一次撤销与计算值导出沿用项目事务。
XLSX 拒绝公式、宏和外链，保留高精度数值；JSON 保留十种字段配置、int64、unset 与 null，身份和表达式仍由工作空间承载。
新增 `.stkworkspace` 清单、目录与 SHA 校验、一致 SQLite 备份、显式资源及跨平台路径映射；再次导出保留旧来源 aliases，数据库历史不改写。
原生各模块提供独立状态／资源 hooks，整组窗口先校验再采用；冻结 Viewer 数据、相机、参数与隐藏稿，恢复不执行任务。
Critical review 修复只读元数据误判、同标签换图身份、延迟回调旧树、空项目／空表、未保存稿关闭保护、typed baseline 与多次迁移来源。
新增真实 X11／Wayland 多窗口创建、绘制与清理验证；实际失败、最终整套结果和剩余限制见[验收记录](runtime-validation.md)。
最终独立审查再修旧表格Bridge回调、排队打开结果覆盖、分析稿重复get及冻结图的画布／节点恢复；原失败反例 **11/11**。
Python完整 **3019 passed/24 skipped/2 deselected**，相关三版本各 **235/235**；原生完整 **1539/1539、零跳过 /358.17s**，本节点96项独立必跑均通过。
中英文宽窄GL/Vulkan32张与真实双窗口系统通过；wheel／sdist、三格式安装包和删除原资源后的连续工作空间迁移通过，无模型／Runtime请求。
导出／新会话导入工作空间为4／6次实际点击；参数与草稿可携带，运行环境／凭据／活进程及原代码文字中的路径仍有明确边界。
代码 **`29e9fe9b9014da93411100e3f4f6951784743e62` 已推送 main**；首轮Runtime 6/8成功，两个Windows矩阵各46 failed/2452 passed/94 skipped/34 errors。
Windows只读fd的fsync与DirEntry缺省dev/inode是两处实际生产缺陷，改为同步自有可写staging和使用Path.lstat完整身份；另将Excel超长pytest参数ID改短，保留原边界值。
三项Windows差异模拟修前2 fail/1 pass、修后3/3，真实源变动仍拒绝；相关三版本各238/238、完整Python3022 passed/24 skipped/2 deselected/640.05s、原生迁移21/21通过。
首轮桌面Linux1539/1539通过，macOS CPU983/983与Metal226/226均通过，但新Viewer测试仅app标签而未进入CPU筛选，使必跑gate正确拒绝；Windows918/928，10项在导出阶段失败。
首轮桌面全部结束后收口修正；Viewer恢复拆为独立unit测试目标，旧Viewer目标与必跑要求保留。
同Mac／Windows的最终CPU筛选 **1001/1001、零跳过 /133.79s**，必跑检查41项均实际通过，包括此前漏选的8项Viewer恢复；新wheel仓库外迁移与两版本PET离线复核通过。
新sdist离线构建及构建时源码／契约／指南／测试逐字节校验通过，未将旧包视为修后产物；完整历史证据与剩余迁移边界保留在验收记录。
在`29e9fe9`桌面5个job全部结束后，修正 **`2299b2a6f79c67b15ce90a9d9aa226c4b28c4869` 已推送 main**；精确修正CI验收中。
该修正的Linux科学矩阵及Linux／Mac桌面通过；Windows科学3.11余3项、3.12余5项失败，分别为宿主Windows路径被测试标作POSIX、扫描替身未实现迭代接口，生产解析与迁移规则未变。
两份Python夹具加入明确POSIX／Windows来源和错误类型拒绝检查，扫描替身保留标准迭代／上下文协议；三版本相关各103/103。
2299b2a桌面全部结束，4/5成功；Windows926/928，余两项路径夹具只比较斜杠字符串，实际导入已成功，改为本机文件路径比较。
Critical review还发现Viewer独立unit目标仍嵌套在POSIX fake目标条件内，使Windows漏构建8项必跑测试；本轮拆出可移植同步payload桥，无需Python／进程组，保留全部8项恢复与显式执行断言。
本轮统一build16／17成功，定向10/10（1.99s）；完整原生1539/1539、零失败／跳过（串行1300.44s），74项本节点必跑检查实际通过。
原Mac／Windows CPU筛选登记1001项，8项Viewer均为unit；生产实现不再变动。
本轮sdist离线重建48697258字节／896成员，七项生产模块／schema、12项构建时测试／契约／文档与源码逐字节一致；旧wheel内容核对未变。
源码包在仓库外解压后用python -I运行迁移夹具103/103（2.16s），模块来源明确为解包目录，未回落工作树。
暂存改动经配置化redact密钥扫描无泄漏；测试修正 **`070f81e76d4109d6df98a266ffc67036621e2918` 已推送 main**。
推送前2299b2a桌面5个job全部completed，远端main核对无新增提交；Runtime 38952649174 **8/8**、Desktop 38952649245 **5/5**、Secret／Docs均completed/success；Linux原生1539/1539、Mac CPU991/991／Metal226/226、Windows936/936，均零跳过。
Windows8项Viewer恢复全部实际执行，必跑gate673匹配通过；Linux／Mac gate717／693通过，32张GL/Vulkan与16张Metal新图形及两平台发布包／解包冒烟均成功。
视觉复核另修正导出提示“已安装窗口”为“已打开窗口”（中英），避免把内部宿主注册术语展示给用户；i18n2289/2289与8张宽窄GL/Vulkan导出检查通过（11.67s），前代码桌面于2026-10-16T19:34:29Z全部结束后，文案修正 **76715e4** 已随验收文档推送main；Runtime 38956470955 **8/8**、Desktop 38956471084 **5/5**、Secret／Docs全部完成成功。
最终Linux1539/1539（417.68s）、Mac CPU991/991（363.16s）与Metal226/226（372.44s）、Windows936/936（447.98s），均零跳过；8项Windows Viewer恢复与673匹配gate再次通过。
最终32张GL/Vulkan与16张Metal图形、两平台发布包／解包冒烟均通过；四份交付文档按最终代码和实际CI收口，所有模型测试环境保持key空、model取消。

## 2026-10-15：本地多维表格、类型契约与可撤销批量编辑

所有者确认先完成本地科研多维表格。TableWorkbench 复用既有项目和定义组件，通用 TableGrid 为可选协议，旧表格保持行选择行为。
新增强类型/字段选项、命名视图、分页前全表分组排序/筛选、对象候选和只读来源、CSV 预览/映射/SHA 以及视图导出。
格式 14 增加独立关系，不改变旧 fields 日志镜像；升级先备份。PET 格式门禁原写死 13，完整回归实际发现 22 项失败后修兼容13/14，
真实 PET 证据副本各离线通过，无 MD 重跑。首轮原生定向 66/70；旧定义组件未收到外部网格可见 UUID，使保存/重载/删除被拒，已修同步。

Critical review 实修：子矩形按唯一 TSV parser裁剪目标、全表排序委托、跨实例选择、连续录入延后导航、选项稳定ID、对象目标表、
字段/视图/对象/粘贴的取消与旧绑定、公式不隐式改常量、布局嵌套校验、选项-only撤销的求值缓存、非法空view、URL控制符、
同SHA快照文件的来源身份、已有object字段kind限制及最终Viewer队列来源门禁；保留根叶过滤条件再追加，空日期/重名选项/布尔缺测语义，对应反例均纳入测试。
完整 Python 最终 **2853 passed/24 skipped/2 deselected**，相关三版本各 **127 passed**；首轮原生完整1423/1428的5项旧夹具已修，
最终完整 **1432/1432、零跳过 / 339.17s**，新增必跑 **65/65**。wheel/sdist 与仓库外安装包全流程冒烟通过；布尔编辑/已存视图1次、矩形粘贴2次+快捷键，
代码 **`faf3a44` 已推送 main**；首轮CI完整pytest通过，独立PET合成例的旧格式13期望已修，三Python版本各7/7。
首轮桌面4/5成功，Linux唯一Weston退出SIGSEGV；源码发现线程取消不join/未持锁返回，已实现唤醒+join后释放，12项确定性线程测试与两种Weston窗口14/14通过；vendor全部1095文件重生成一致。
修正后完整原生1444/1444、零跳过（328.66s），新增必跑77/77；明确等首轮桌面全部结束后推送 **`d03366e`**。
修正提交Runtime **8/8**、桌面 **5/5**、文档部署与密钥扫描均完成成功；五Python矩阵新表各36/36，三个Linux独立PET例各7/7及诊断/打包/上传通过。
从精确修正提交离线重建sdist并解包演练7/7，新wheel与此前仓库外安装冒烟产物逐字节一致。历史崩溃没有调用栈，不冒称已证明其根因。
最终测试/点击/提交/CI及首轮失败以[验收](runtime-validation.md)为准。本轮不调用模型、不更换端点，不改变任务授权。
功能与剩余范围见[多维表格](design/multidimensional-tables.md)。


## 2026-10-14：编辑模块拆分、直接可用工作区与点击指标

所有者要求继续实施模块化，并把减少点击作为核心指标。拆出 11 个编辑对象库，统一 Editor/EditorContext/注册/导航/草稿协议，
项目、修订、选择、撤销、Viewer 和执行服务仍共用。独立 Table 复用传统项目页组件；Files 新增有界逐层目录观察，不冒充登记表；
Python 以程序文档为主体，载入/保存/另存、SHA 冲突保护与显式运行共用已有 worker。桥协议 1 增补文件/目录接口，项目格式仍为 13。
默认文件树、Viewer、分析图、表格直接可见，顶部常用入口与保留实例的左右交换各一次；普通导航分栏，旧 Viewer 后隐藏的草稿移动原实例。
窄栏两行页头，概览节点保留可读 ID；表格点击选择字段并查看 JSON 详情。完整富对象类型/缩略图、批量粘贴、完整 IDE、插件 ABI 尚未实现。

Critical review 修复跨表删除丢隐藏草稿、同项目后台重连被草稿 guard 阻断、同步拒绝重复 completion、旧目录/代码来源回调、
工厂失败的布局回滚、旧布局遮挡 Viewer、附加窗口关闭保护、迟到 Reset、菜单/页头 callback lifetime，以及复核导航失败遗留不可见候选。
旧几何/持久化/预设表单测试显式使用历史布局；当前默认布局与新指标另用真实事件/结构 goldens 检查，不改全局夹具掩盖新行为。
旧 MuFerro 测试先等任务数而碰到合法 preparing 状态，修为等待同一快照两个任务均 queued 后才启动执行，未放宽队列判据。

本机 Python 3.12 完整 **2812 passed、24 skipped、2 deselected**；3.11/3.14 程序文件相关各 **23 passed**，目录/旧索引/桥/分类相关各 **80 passed**。
最终定向 **24/24**、中英文宽窄 GL/Vulkan 组合工作区与默认界面 **20/20** 通过；完整原生 **1367/1367、零跳过**（299.26 秒），新增必跑检查 **70/70**。
代码 `10adde6` 与夹具修正 `2e331ca` 已推送 main；后者 Runtime **8/8**、桌面 **5/5**、文档与密钥扫描全部成功，实际结果见[验收记录](runtime-validation.md)。
真实鼠标任务：新默认主要区域 0 次导航，Python/切回节点/交换各 1 次；同一旧单 Viewer 起点菜单 2 次对照顶部 1 次，
另测中英文 900 UI 像素 × 1/1.5/2 倍缩放的顶部一次入口。未做线上埋点或移除显式运行/保存。
截图使用合成数据与真实后台，未重新运行 MD 或收费模型，不代替 PET 物性/跨平台真机/读屏验收。
首轮跨平台 CI 暴露 Windows 换行与路径字符串夹具差异；仅修三份测试文件，以原始 LF 字节和真实文件身份核对，保留全部行为断言。
独立复核及本机三 Python 版本各 10/10、原生脚本/目录 **34/34**（6.39 秒）通过；在前代码桌面已结束后推送修正 `2e331ca`，Runtime 38675881568 **8/8 已成功**，桌面 38675881571 **5/5 已成功**，文档与密钥扫描也已成功。
最终桌面 Linux 1367/1367、macOS CPU 873/873 + Metal 200/200、Windows CPU 831/831 均无跳过，原六个 Windows 用例逐项通过。
少导航点击已写入根目录 `AGENTS.md` 共同开发约定，后续 UI 交付须记录固定起点、实际次数与任务终态。

## 2026-10-14：界面盘点与工作方式更新

所有者要求 Viewer 持续可见，与节点数据处理或 Python 程序编辑并排，增加独立表格/文件树窗口与对象单元格。
按实际代码核对：保存分析已有节点编辑，基础表格已有类型/引用/公式；文件只有登记表，Python 是输出优先的脚本页。
导航首次可能占用 Viewer 区域，若干入口会最大化；这些问题不能仅靠重新命名编辑器解决。
本机重新捕获并目检默认布局、分析图、项目表格和 Python 四张离线冷启动截图；未连接后台或打开项目，不冒充完整操作验收。
更新[工作台约定](design/project-workbench.md#2026-10-14所有者补充的界面要求)、计划与交接，明确应用内基础程序编辑优先，VSCode 作为可选完整 IDE。
修正文档仍称不能增删节点/拖线的过时说明。本次仅设计与文档交付，独立文件树、富对象表格及布局改版尚未实现。

## 2026-10-14：PET 全流程研究与 E1d（真实软件全流程验收通过）

新增 `pet-study/1` 本机协调模板，格式 13 普通参数行保持不变，关联行只记录子运行与交接，生命周期继续由既有运行器持久化。
冻结建模、压密/释放、逐温降温和对应温度的模量/质心 MSD，三份保存分析包括被拒绝拟合的原始观测和诊断。
准备/查看/重开/恢复不提交；明确开始接续、取消和成功阶段复用。新增 IFF2021 O₂ 中性双位点示踪，保留 PET 完整 profile 与旧 E1c 哈希。

Critical review 修正旧目标/资源回调、未完成创建、冻结参数竞争、外来子运行/汇总/分析来源、篡改 CSV、未知系数和错误原子/化学身份。
真实压密计算揭示 LAMMPS `write_data` `%g` 六位有效数字使 OPLS 系数表示发生变化：首轮被严格拒绝，未当成物理错误或跳过检查。
修正为识别精确的六位表示并记录差异；后续每段由首个冻结模型生成精准系数 include，CVFF 整数分量保持严格，原压密输入逐字节未变并复用成功子运行。

E1d 使用有界 full/real data/dump reader，保留真实 ID、原子属性、拓扑键、盒子和严格递增实际帧；球、线段、类别颜色与相机沿用 payload/2。
GUI 精确原子拾取未实施，体场探针不会采样分子点；原始 reader 为 float64，GPU 属性显示可能为 float32。
兼容回归同步 12 个预设数量、生成节点参考与新增中英文表单 goldens；旧 11 份预设布局逐项一致。

本机完整 Python **2782 passed、24 skipped**，最终协议/后端/dispatcher 三 Python 版本各 **97 passed**，3.11/3.14 相关各 **195 passed**、最后来源 guard 各 **4 passed**；
原生 **1318/1318、无跳过**，546 PET 真实压密/轨迹 GPU 导出通过，O₂ 插入与 COM 求解器短测通过。
首轮 11 段软件路径通过后，科学复核发现并修复 O₂ 前置 FIRE 清空 PET 速度的问题。全新建模重验的 **11 段真实 MD 全部通过**（4883.98 秒），每段 126 帧；源 607.38358 K → 首个 NPT 606.22709 K，温度继承通过。
模量/O₂ 扩散数值拟合成功，Tg 因物理判据不足被拒绝；观测与诊断保存，`software_complete=true`、`material_validation=false`。
搬迁重开后再次断开 Runtime 独立验收 **1 passed**（2.62 秒），11 个交接、8 个密度点和 25 个 O₂ COM 样本核对一致，最终 550 原子轨迹由 Vulkan 导出并目检。
公开项目与数值图保留在本机 `/home/mnemora/opt/stk-validation/pet-study-20261014-20cc2f7/`；不含 Runtime 配置或凭据，不作为材料实验/训练数据。

轨迹索引补正：首个代码头 Runtime 的 Windows 文件同 tick 改写反例失败，现以完整 raw SHA 复核索引和缓存，清除旧错误指纹。
三 Python 版本各 76 项、完整 Python 2782 项与桌面相关 11/11 通过；前代码头桌面 5/5 结束后推送 `20cc2f7`，未用延时或跳过规避。
最终 `20cc2f7` 的 Runtime **8/8**、桌面 **5/5**、文档与密钥扫描全部成功；Linux 原生 1318、macOS CPU 840 / Metal 192、Windows CPU 798 均通过。
独立代码/科学 critical review 无剩余阻断；短链、单构型/单原点、有限温压采样与交叉参数实验一致性仍未完成，实际测试和历史失败见[验收记录](runtime-validation.md)。

## 2026-10-13：PET 数据闭环节点 1 实施

原生“材料仿真”与“仿真批次”增加内置 MuFerro/LAMMPS 选择、指定主输入脚本、导入/准备/日志/收集，
历史运行按冻结引擎处理，两种资源选项在编辑器会话内独立保留。LAMMPS 结果在本机复核文件、冻结输入、报告、日志与表中摘要，
显示热力学结果并导航到对应结果行；离线查看不访问 Runtime。固定 Python dispatcher 校验项目、修订、引擎和运行身份，
不接受以参数指定任意 Python 模块或未知引擎执行、不增加智能体工具；准备不提交，批次运行/提交仍需明确操作。操作见[桌面指南](lammps-desktop.md)。

[字典草案](design/pet-data-dictionary.md)与[离线示例](../examples/pet_data/README.md)用项目格式 13 的普通表、稳定引用与快照，
形成材料→配方→批次→样品/状态→观测→加工复核→决定的全合成链：9 业务表、32 记录、61 引用、20 冻结文件。
保留失败/缺测与计划/实际差别，不填造材料阈值、测量或训练数据；普通表还没有业务级强制校验和用途准入。
[厂内调用清单](design/inplant-execution-baseline.md)逐项列出问题/子请求、模型、Runtime、模块、脚本、日志与备份路径，
明确自由问题与公开表准入的差距、配置指纹不证明主机身份、第三方出口尚未审定；强制厂内边界属于节点 2。

Critical review 修正旧文件选择/项目/引擎/成员回调、选项覆盖与伪造运行、离线文件和摘要篡改的处理。
完整桌面回归发现旧的无完整 intent 批次被引擎过滤隐藏，现保留查看、归档和恢复，未知方案只读；
有效已归档批次按原设置运行仍符合既有所有者确认。新按钮测试首轮点击超出视口，修正实际面板操作后通过，未绕过提交按钮。
最终审查补上归档按钮的旧项目/引擎/批次回调保护；部分批次列表不再显示全局归档数量。
新增 28 个 Python 用例、4 个原生交互用例、16 个中英文/宽窄/GL/Vulkan 截图，并纳入三平台必跑检查。
真实 LAMMPS 原生单任务与两成员批次均通过；108 原子氩的 20 步只验证软件路径，不作为 PET 性质验收。
完整 Python、最终桌面回归、打包、密钥扫描与 CI 的实际结果见[验收记录](runtime-validation.md)。
本机完整 Python **2598 passed、24 skipped**、最终 guard 定向 **28 passed**；最终原生 **1309/1309、无跳过**（274.06 秒），
含必跑检查的 4 新交互和 16 截图；离线例三 Python 版本各 **7/7**。暂存密钥扫描无泄漏；
代码 `4f54d78` 已推送 main，Runtime **8/8**、桌面 **5/5**、文档与密钥扫描均已完成成功。
本次不改变项目格式、端点、密钥、网络或 S2 执行权限；E1d 轨迹显示、PET 物性收敛及节点 2–8 尚未交付。

## 2026-10-12：PET 基材料研发项目方案的 STK 落地路线

读取所有者指定的 DOCX 正文与表格，原稿、客户资料及其访问链接/文件身份未写入公开仓库。
新增[材料数据闭环路线](design/pet-materials-data-loop.md)，将七项数据工作映射到现有项目、引擎、材料模型与智能体基础，
给出最小材料/批次/样品状态/证据/评价/决定关系、用途准入、八个交付节点和一条真实任务验收场景。
同步主开发计划、多尺度设计和 handoff；本次只交付设计，不改数据库格式、执行权限、模型端点或网络设置。

Critical review 核对代码与方案的实质差距：现有公开表准入仍会发送自由问题；S2 不准备/开始运行、无训练工具；
S3a 只有铁电/容量合成曲线、随机样本划分，训练任务仅在内存，不能当作 PET 独立批次评价或完整移交。
新增厂内全内容要求、版本化自主训练设计和样品分组独立评价，区分规划与当前契约。
科学审查明确纯 PET 与 PET 基弹性体/接触介质、多相 Tg、扩散与渗透、跨尺度传递及材料实测验收的边界。
一年阶段与 2027 年底只记录为方案目标；材料阈值、起算日、资源与预算不虚构。
路线文档 `b5fc3b7` 已推送 main；本地六份 Markdown/17 个新增链接与格式检查通过，暂存 gitleaks 无泄漏。
该提交 Runtime **8/8**、密钥扫描与文档站均已完成成功，见[验收记录](runtime-validation.md)；
纯文档改动未触发原生桌面 CI，最近代码 `fbcd9f4` 桌面 5/5 已结束通过。

## 2026-10-12：E1b 文献参数 PET 本机建模

所有者明确授权根据文献与公开资料选择并直接执行，PET 电荷选择不再待决定；其他待决定事项不解除。
选择 PET 专用完整 OPLS-AA/MK 2022 适配方案（DOI 10.3390/polym14061161），按完整 S1/S2 电荷、LJ、质量配套，
S3/S4 精确项优先并用固定 GROMACS v2025.3 明确补全缺项，添加显式平面 periodic improper。
芳环 C 保留文献 −0.115 e，唯一醇端 O −0.566→−0.565 e 的舍入修正明确记录。
COOH/OH 每链 22N+3 原子，默认 6×DP4=546；旧 540 原子 OH/CHO 可行性夹具保留作历史写出器对照。

`pet-model/1` 本机模板和 `stk.lammps.create_pet_workflow` 建普通参数表/流程；明确开始后用已登记分子模块与 Packmol 构建。
八项产物经来源、参数、组成、电荷与实际 SHA 复核后原子发布，再由工作流登记/冻结；生成目录不覆盖。
取消停止 Python/Packmol，其他进程写入的取消请求也能在长步骤内被观察；重开不执行，旧模板双参数接口不变。
生成后显式导入 LAMMPS 案例；现有远程仿真模板尚不直接消费本机建模步骤产物。

Critical review 逐项复核 69 个印刷电荷、15 个局部类型、12/19/23 种键合系数与单位，修正 Foyer 保留输入元素质量的问题，
严格拒绝 Packmol 的 imperfect fallback，增加周期互链/自镜像重叠检查；小单链高密度盒子确实被拒绝。
Packmol 使用确切登记程序，日志/时间有上限；whole-chain 构象资源、数据文件与 manifest 也有上限。
DP8 默认构象失败后使用同种子 ETKDG 随机坐标 fallback，保留真实坐标与失败/有限步 UFF 状态；DP8/DP20 初始建模通过。
DP100 试验内部 timeout 未返回，外部停止并保留 censored 证据，首版链长因此明确限 2–20，不保证更大分子构象。
补上发布前七份产物、完整 profile 与 XML 的实际摘要核对，拒绝重名 JSON 键、NaN 与过量数据，固定 XML 实际字节避免跨平台换行摘要差异。
周期 improper→CVFF 只接受单项相位 180°/周期 2，成员顺序不重排；其他不支持势项仍拒绝。

独立 OpenMM 参考从文献数值和化学键图重建，未从产品 profile 读期望；非周期相同 Hamiltonian 的能量、力与有限差分对照，
生成 PPPM 案例另行真实读回；保留 LAMMPS 原始近乎平面 proper 力的保护截断差异，未声称原始 DP2 全力精确一致。
真实模型两行已走参数冻结、建模、八产物快照、显式导入和 Runtime/LAMMPS 路径。
代码 `fbcd9f4` 已推送 main；Runtime 8/8、桌面 5/5、密钥扫描与文档均已完成成功。
本机测试与最终 CI 的实际证据见[验收记录](runtime-validation.md)。来源/操作见[模型](pet-model.md)与[示例](../examples/pet_model/README.md)。
初始填充和软件核对不代表已平衡无定形 PET；未实现气体参数、分子质心/多原点气体 MSD 或 Tg/模量/扩散材料性质收敛。

## 2026-10-11：E1c 多温度 Tg 来源与日志列校验

Critical review 沿 `density_series` → Tg 检查多温度来源，复现最终诊断丢掉原日志摘要；
同一辅助入口也未拒绝早期热力学段的重复列名，汇总字典可能覆盖观测。
现在全部段统一检查列名，汇总表建立多来源 provenance，最终 summary/fit/diagnostics 保留各标签与日志文本 UTF-8 SHA-256。
这些是 `input_text` 摘要，函数不读取文件，不声称核对原始磁盘字节；冻结日志仍由调用者保存。
`stk.source.lammps_log@1` 实现版本升为 2，使旧缓存不能绕过新校验；节点主版本/端口/参数与六技能哈希不变。
八个合成温度点从完整日志汇总、拟合回读 340 K，八份来源与 JSON 诊断一致；真实氩三路径仍通过。
代码 `be9bdd7` 已推送 main，桌面 CI 5/5、Runtime 8/8、密钥扫描与文档均已结束通过；
Linux 1289/1289、macOS CPU 838/838 与 Metal 180/180，无失败、无跳过。本机与 CI 证据见[验收记录](runtime-validation.md)。
最终状态以文档提交补记，不涉及 PET 建模或电荷决定。

## 2026-10-11：E1c 表头、缓存与桌面回归修正

Critical review 复现：通用 CSV/列文件读取器先构造字典，重复的 Stress 列会覆盖前列，使同一输入从 2.5 GPa 误算成 25 GPa。
现在在构造字典之前检查原始及规范化后的列名唯一性，三套性质预设均在拟合前拒绝歧义输入。
已有缓存仍能绕过新增校验，先用旧实现版本的真实文件指纹与预设缓存复现，再把 `stk.source.table@1` 的 `impl_version` 升为 2；
类型、主版本、端口及参数不变，其他节点声明与六个技能哈希不变，旧归档不改写。

`6927e27` 桌面 CI 已结束：Linux 四项、macOS CPU 与 Windows CPU 各一项失败，均为预设数量仍断言 8（现在 11）。
原始报告保留，修正三处断言并为新增三预设补中英文表单基准，既有八套基准逐项不变。
修正后本机完整 pytest 2483 passed、24 skipped，完整桌面 CTest 1289/1289 无跳过；Python 3.11/3.14 各 78 passed、1 skipped。
真实氩三套运行/分析路径复验通过。推送前上一代码头桌面 CI 已结束，所有测试保持空 API key、模型变量未设置。
修正代码 `c17bb4b` 已推送 main，桌面 CI 5/5、Runtime 8/8、密钥扫描与文档通过；详细报告见[验收记录](runtime-validation.md)。PET 电荷仍未决定，相关建模没有实施。

## 2026-10-11：E1c Tg、模量与扩散模板

导入的 full/real 算例使用三套随包安装的 LAMMPS 脚本；参数表增加平衡步数、采样间隔、应变率、溶质类型。
`suan/lammps/analysis.py` 实现明确单位与范围的两段密度 Tg、小应变拉伸斜率、MSD 爱因斯坦关系；
四个增量 `@1` 图节点、三个图预设与技能交付 summary/fit/diagnostics/plot。
34 个既有节点声明与 3 个既有技能哈希逐项不变，项目/图格式不变；补齐发布目录、说明包节点参考与独立契约。
旧 E1a 参数表读取/准备不升级，显式导入或复制才加字段，既有冻结计划保持原形。

Critical review 修正：扩散生产阶段改为固定盒子 NVT，不扣溶质组自身平移（单溶质会因此丢失位移）；
扩散窗口默认 null、未明确填写时拒绝；采用自由截距以保留预载/残余应力；分段/窗口不足、错误单位/符号、重复/重置坐标与非有限值拒绝。
通用表格输出不导出内存 provenance，因此将来源同时保存在独立诊断，真实归档读回核对 SHA-256；
日志若在 clear 后换单位，不能把末次单位用于前段，E1c 明确拒绝混合单位。
相关 MD 采样的 OLS 标准误差仅作拟合描述，不能作为独立重复的材料性质不确定度。

合成曲线分别回读 340 K、2.5 GPa、1e-4 cm²/s；真实 LAMMPS 22 Jul 2025 Update 6 的 108 原子氩，
走 Runtime → 按行仿真 → 冻结产物 → 隔离分析 → 归档数值/绘图，三项通过并保存公开报告。
软件短轨迹路径不代表材料性质收敛；无跨行自动 Tg 汇总、自动平衡/扩散区判断、Tg 置信区间或通用分子质心/多原点 MSD。
不实现依赖未决 PET 电荷的建模，不把 0.0 作为定论；所需决策仍延后至少 2026-10-12 04:47 UTC。

代码 `6927e27` 已推送 main；本机回归、首轮失败及修正、打包与 CI 的实际结果见[验收记录](runtime-validation.md)。
推送前确认写出器 `057f96d` 的桌面 CI 已完成 5/5；所有测试清空 API key、取消模型变量，无模型请求。

## 2026-10-11：E1b 独立 LAMMPS 数据写出器

`suan.lammps.write_data` 从 foyer 的 ParmEd 结构直接写 full/real；按物理系数合并类型，保留电荷与未包裹坐标，
分子按键连通分量编号，支持正交/三斜盒子、LJ、谐振键/角与 RB→OPLS。写出前完整验证，再原子替换目标文件。
不实现链长/链数/密度建模步骤，不把历史 PET 0.0 补丁作为产品电荷选择。所有者要求至少 12 小时后再提请决策，
交接中按分钟向后取整记录最早 2026-10-12 04:47 UTC；时间经过不代表批准。

Critical review 发现并处理：foyer 有显式 1–4 调整，逐项核对标准 OPLS 缩放，不能直接丢掉；RB 源系数含约 2.4e-6 kcal/mol
舍入常数，设明确的每项 5e-6 上限并记录累计省略量，不能静默丢任意常数或五次项；未参数化 improper 需要显式选项，
已参数化 improper 和其他未支持势项拒绝；非有限输入/转换溢出拒绝，失败保留已有文件。

540 原子 PET 正交/三斜逐项对照 GMSO 0.17.0：类型 15/16/25/30 合并为 10/9/14/13，每个原子与连接的实际参数都相符。
GMSO 以默认 residue 将六条链记为一个分子，STK 按键图记为六个。真实 LAMMPS 证实 GMSO 三斜 data 头误用 dump 外包围边界，
读回体积 45648.625 Å³，应为 29188.420 Å³；STK 的晶胞参数与输入一致，不复制参考实现的错误。
同几何各项能量最大差约 1.1e-5 kcal/mol；STK 写出 0.044/0.045 秒，GMSO 62.15/62.53 秒，另需转换 11.69/11.32 秒。
完整对照报告在 `examples/pet_lammps/validation/2026-10-11-writer.json`。这是写出器验证，非 PET 材料结果。
代码 `057f96d` 的 Runtime 8/8、桌面 5/5、密钥扫描与文档 CI 已完成通过，详细结果见验收记录。

## 2026-10-11：交接给 Codex 等其他代理

所有者要求准备给 Codex 的交接文档与起始提示词。Codex 自动读 `AGENTS.md`、不读 `CLAUDE.md`，而密钥、测试环境变量、不发收费请求、
推送前等桌面 CI、“合作方”称呼等规则此前只在 Claude 的会话指令中，所以写入 `AGENTS.md`，并让它指向 `handoff.md`。
`handoff.md` 重写为当前快照：各方向状态、待所有者决定的事项（PET 酯基苯环碳电荷等）、不依赖决定的下一步（STK 自有 LAMMPS 数据写出器、
E1c 分析模板、桌面 LAMMPS 入口）、E1a 代码入口与边界、Python 测试与密钥扫描命令；较早交付的细节留在本记录与开发计划中。
PET 可行性脚本、OPLS-AA 补丁与真实 LAMMPS 的手动验收原先只在会话临时目录，移入 `examples/pet_lammps/`（不在 `tests/` 下，CI 不收集；
GROMACS 的 `ffbonded.itp` 不提交，补丁注释中保留所引的原行；生成的数据文件不提交）。建模脚本把合并后的力场写到临时目录，
避免留在作为算例导入的文件夹中。移入后重新运行：建模 540 原子、净电荷 0，各步 0.5/5.9/11.8/61.4 秒；验收 2 passed，PET 两行平均 445.758/551.423 K。

## 2026-10-10：E1a LAMMPS 计算引擎

先在本机用真实模块走通 PET 建模：mBuild 由重复单元建链、Packmol 填充、foyer 分配 OPLS-AA、GMSO 写数据文件、LAMMPS 压缩与 NPT。
foyer 的 OPLS-AA 对芳香酯缺一个角与两个二面角（类别写成 `C`，酯羰基碳却是 `C_2`），按同一文件的 `C` 条目补上（与 GROMACS 发布的 OPLS-AA 一致）；
与酯基相连的苯环碳拿到 −0.115 而没有氢平衡，每条链带 −0.805 净电荷，按 OPLS-AA 惯例取 0.0（STK 推出的值，列入“需要所有者决定”）。
最后阶段密度 1.223 g/cm³（实验约 1.335；4 聚体、540 原子、约 20 ps，只说明工具链可用）。

然后实现 E1a（见[方案](design/multiscale-engines.md)“进度”）：`suan/lammps/`（脚本检查、日志读取与核对、TaskSpec、计算端启动器）、
`suan/workflows/lammps.py` 与模板 `lammps/1`、`stk.lammps`；与 MuFerro 共用的辅助函数移到 `suan/workflows/common.py`，
MPI 启动规则移到 `suan/runtime/launch.py`（MuPRO 的提示文字不变）。本机发现 conda-forge 默认装的 LAMMPS 没有 MPI，
2 个进程各自完整运行、日志互相覆盖却显示成功；模块目录改为固定 MPICH 版本，启动器对没有 MPI 的程序拒绝多于 1 个进程。

交付前审查（独立代理，用真实 LAMMPS 复现，9 项属实另 5 项次要，均已处理）：`if … then "shell …"` 与多层 include 绕过脚本检查；
被包含文件中的参数读不到；变量样式可由变量拼出 `getenv`；`thermo_style multi` 被误判为截断；最终状态截断会丢掉报告；
工作流准备时不检查参数；运行改写输入后无法收集；收集时报告列出的输出未与运行环境核对；被取消时不写报告；以及几处误拒（核壳模型的 `region shell`、
`./` 路径、多行三引号）与多值 index 默认值。只追踪字面路径（由变量拼出的路径不追踪）已写入说明。

## 2026-10-10：E0b 模块管理（检测已有软件，没有才安装）

按所有者决定：可选模块由人选择；先检测这台电脑上已有的 LAMMPS、ABACUS、Packmol 与分子建模工具包（PATH、常见 conda 环境、STK 自己的文件夹），
检测到就直接使用；没有才在确认后用 micromamba（固定版本与 SHA-256）从 conda-forge 装到 `~/.stk/modules/envs/<模块>`。
后台服务 `modules.*`（安装、取消、移除只给桌面）、工作台“计算模块”面板、引擎用 `suan.modules.find_program` 找程序。
本机实测：真实 LAMMPS（22 Jul 2025 Update 6）、Packmol 21.2.1 与分子建模工具包（mBuild 1.4.0）装好并被检测。

交付前审查（独立代理，11 项属实，另有 9 项疑似，均已处理）：原生测试的假程序在 Windows 上无法运行而被列为必跑；两个模块同时安装时
micromamba 下载互相破坏；同一模块的重复安装会启动两个安装程序且返回内部字段而协议报错；检测与安装或移除重叠时会丢失或复活登记；
服务退出时半装的环境会被当成已安装；网络设置改为离线后安装仍在下载；安装的超时不起作用且失败时未先停掉安装程序；格式不对的登记表让列表失败；
面板在从未检测时就说“未找到”、检测期间不能取消；另外按建议在 Windows 上查找 `Library\bin`、探测在空文件夹与独立进程组中运行、
登记表加文件锁、安装程序只拿到精简的环境变量、目录校验更严格、`modules.detect` 的级别改为“记录”。

## 2026-10-10：E0a 计算引擎模板接口

为加入 LAMMPS 与 ABACUS 先把执行一侧从 MuFerro 中解开：远程模板（计算引擎）有统一的接口（冻结哪些字段、冻结值、准备、收集、结果目录、
传给下游的文件），按行工作流的冻结、过期判断、提交与收集都按步骤的模板分派；外部引擎包经 `stk.engines` entry point 注册
（内置标识不可替换、加载问题可查）；`project.workflows.choices()` 报告模板是否远程，桌面运行区据此决定是否选运行环境；
`STK_ALLOW_LOCAL_MPI` 取代 MuPRO 专用名（旧名仍有效）。MuFerro 的原有测试全部通过；改动的 3 个测试只是固定了旧的输出形状或提示文字。

## 2026-10-10：多尺度计算引擎方案与所有者决定

所有者：思劲最近的 PET 基材料设计项目需要第一性原理与分子动力学，STK 应优先融合开源的 ABACUS 与 LAMMPS，作为相场之外的两个模块，体现多尺度。
检索（许可：ABACUS LGPL-3.0、LAMMPS GPL-2.0，均可从 conda-forge 安装）与梳理代码后写成[方案](design/multiscale-engines.md)：
数据一侧已有插件机制，执行一侧写死在 MuFerro 上，需先做计算引擎接口。所有者决定：通用化 → LAMMPS → ABACUS；STK 集成常用软件的安装，
作为可选模块，先检测已有的、没有才自动安装；PET 的四项性质都要（密度与玻璃化转变温度、模量、气体扩散、电子结构与相互作用能）；
集成开源分子建模工具作为可加载模块，同时允许导入外部建好的模型。

## 2026-10-10：S3a 材料预测模型的首版链路

按所有者决定实现：`suan/materials/`（两种曲线目标与读出、合成生成器、`stk.dataset/1` 契约与数据卡、PyTorch CPU 训练、后台任务、
评估门槛与模型登记、预测）、后台服务 `materials.*` 与脚本 `stk.materials`；Runtime CI 的 3.12 任务安装 PyTorch CPU。
合成数据上回线模型读出的剩余极化误差约 0.5 μC/cm²、矫顽场约 2 kV/cm，衰减模型每点误差约 3%（见方案“进度”）。

交付前审查（独立代理，全部复现后修正）：P–E 回线缺一个点时读出为 NaN，模型照样登记并把 NaN 写进 registry.json，之后列表、预测与查询任务
全部失败（读出改为数值或空、指标只取有限值、写 JSON 拒绝 NaN）；registry.json 丢失后再训练会把新模型移进旧版本文件夹、预测却读旧权重
（版本号取登记与文件夹的最大值、不覆盖已有文件夹）；最后一轮之后取消仍会登记（训练结束后与登记时都检查取消）；校验器遇到非对象的 target、
重复的输入名、超大整数、跨度极大的数值、非 UTF-8、过长的问题文字会抛错或产生不合协议的数据卡（全部改为报告问题，并拒绝重复的样本 ID、
非正的 E_max 与越界的 SOH）；registry.json 损坏时报告为参数错误（改为 `unavailable`）；训练在锁内读取数据集会阻塞其他请求；
合成数据集上限改为 5000（约 18 秒）；生成合成数据的级别改为 `project_edit`；训练至少 20 个样本；方案中关于单位与范围检查、日志、生成器、
公式与电场波形的描述与代码不符（已改正）。

## 2026-10-10：S3 方案与所有者决定

所有者答复：先做最简单的测试；铁电预测 P–E 电滞回线；锂电池选一个最常见的参数；暂无数据，待与学校合作者合作后才有。
检索后建议锂电池预测容量衰减曲线（机器学习文献中最集中的目标是 SOH 与剩余寿命/循环寿命），写成[方案](design/materials-models-s3.md)；
所有者四项都按建议：容量衰减曲线、合成数据先跑通、PyTorch CPU 可选依赖、本机后台任务。STK 现有的 MuFerro 链路没有外加电场扫描，
相场回线要等确认 MuPRO 是否支持后再接。

## 2026-10-10：S2b-2 桌面智能体界面

`ProjectAgent`（`project_agent.hh/.cc`）读取规划候选、会话列表、所选会话（运行时每秒一次）与对象来源；AI 助手加第四种用途“智能体（多步）”，
显示规划模型及其位置、步骤时间线、等待卡片（“打开修改检查”→ 修改检查页的“应用”“丢弃”经 `project.agent.decide` 记入会话；应用后“用工作流运行新增的 N 行”）、
继续与取消、记录（链尾摘要、核对、恢复）与用量。工作台“需要关注”列出会话（服务端 `attention.py` 格式 13 分支），打开回到会话；
修改检查页注明草案来自哪个会话；数据页格式 13 起用“私有 / 结构公开 / 公开”下拉框。新增原生夹具 `AgentPython`（脚本化模型的真实后台服务）。

交付前审查（4 个方向、25 项：20 项核实属实、1 项驳回、4 项未核实后自查属实或已覆盖；去重后约 14 项，全部修正）：首条消息回复丢失后重试会建第二个会话；
读取较慢时 1 毫秒重绘；读取失败每帧重发；与上一条相同的新消息被清空无法发送；项目忙时保存的消息不会开始；修改检查页只看最近 50 个会话的列表，
列表未读或过期时绕过 `decide`，会话运行中“应用”被拒且已消耗预览；从列表丢弃别的草案会清掉正在显示的预览；导航可能选中另一个项目的会话；
丢弃的回执显示“修订 -1”；一个记录损坏的会话让整个会话列表与“需要关注”失败；格式 12 的复选框失去测试；“需要关注”的测试绕过了工作台；
验收清单把标注说成会话的。

真实模型验收（后台服务层）：用本机 `qwen3.5-4b-q4_k_m` 离线走完 MuFerro 提议→批准→运行→分析，见[验收记录](runtime-validation.md)；
4B 模型能完成，但两次扫描子请求的 JSON 不可用、一次统计参数错误，均由智能体自行改正。

## 2026-10-10：S2b-1 智能体的扫描提议、结果分析与签名批准（服务端）

工具 `propose_sweep`、`ask_about_context` 经现有请求执行器各发一次子请求（消息、请求、草案 ID 由会话、轮次与调用 ID 决定，重放得到同一组对象、
不重发），按 S1d 排序选已在运行的模型；会话读过的来源（按当前标注）与该上下文的表都公开时才可去外部端点，`admit_sources` 在建请求与开始前各查一次。
`draft_status`、`find_runs`、`capture_run_results` 读草案与运行，后者与桌面 L3 规则相同。一轮留下草案时写 `awaiting_user`，下一条消息前写 `observed`；
`project.agent.decide` 只给桌面：先记批准（本机用户与主机、未验证身份）再应用并记回执，应用后列出“运行新增的行”。丢失的执行器留下的工具调用由下一次
`start` 以同一 ID 重跑。验收测试按设计的“验收演示”在真实的本机 Runtime 上走完提议→批准→运行 5 行→分析。

写验收测试时发现 S2a 的 `project_outline` 在有工作流的项目上抛 `KeyError`（工作流记录在 `workflow` 键下），S2a 的测试项目没有工作流，未能发现；已修正并由验收测试覆盖。

交付前审查（4 个方向、18 项；去重后 13 项，全部属实并修正）：重放时丢失的执行器留下的“运行中”子请求要等满 30 分钟；已建消息与请求后失败的步骤不登记对象；
回答按字符截断使中文回答撑破 16 KiB 结果；取消、墙钟上限与过期上下文在建请求之后才检查（过期上下文的扫描请求注定失败仍会发出）；
应用失败的草案其等待项已被批准记录“解决”，再也不能批准；卡片上的决定不告诉规划模型；同一条消息重跑时重复观察、插入空的用户消息；
不在等待中的项返回 `invalid_params`（改为 `conflict`）；等待项没有上限而协议限 100；验收测试 5 行运行用掉 60 秒等待中的 54 秒；
私有数据验收用的是“简单”提问（本来就选最近的模型），去掉来源检查也能通过，改为扫描提议并加全部公开时去外部端点的对照；计划与交接文档未更新。

## 2026-10-09：S2a 智能体 harness（记录、规划轮、只读工具）

按设计与所有者决定实现 S2a。格式 13：`project_agent_sessions`（冻结的会话头）、`project_agent_events`（哈希链，起点为会话头摘要，
每次读取复核）、`project_agent_objects`（每一步做出的上下文等对象），并重建 `project_labels` 加入“结构公开”（只用于表）。
`suan/agent/`：`levels.py` 给脚本目录全部 122 个操作与 12 个 `project.agent.*` 定级并说明不给智能体的理由（测试保证全覆盖）；
`wire.py` 系统提示、技能、由事件重组对话与严格的单个工具调用解析；`tools.py` 三个工具；`executor.py` 循环（认领后发送、
不确定即结束、只在 `adapter_failed` 时换会话展示过的同等或更近端点、连续 3 次工具错误即停、上限前做一次不带工具的总结轮）；
`audit.py` 按日志重组每一轮输入比对摘要并重算统计。网关新增 `admit_planner`（规划轮只用本机或机构内端点）与 `admit_sources`（S2b 用），
本机模型路由可按上下文长度排除（`small_context`）。后台服务 12 个 `project.agent.*`，均进脚本目录；桌面专用的 `decide` 在 S2b。

交付前审查（5 个方向、25 项：23 项核实属实、1 项驳回、1 项未核实；属实的去重后 18 项，全部修正并补测试）：丢失的执行器留下的已认领轮在下一次 `start` 时会重发、
`recover` 只按调用序号匹配而漏掉后续消息里的认领（违反“不确定不重发”）；非 `ProjectError` 的工具异常（如统计溢出）留下没有结果的调用，
之后每一轮都发出不合法的对话；记不下的长回复使认领没有结果；上限时总结轮仍调用工具留下悬空调用；`function` 字段格式错误被当成“不确定”而结束会话；
依赖模型给的调用 ID（重复时两次记录撞到同一上下文、审计配错调用）；`create` 重放受路由变化影响；上一轮刚结束时 `start` 什么也不做；
`tool_result` 未记当时的标注；会话视图超过协议的 1000 个事件上限；导出与其核对分开读取；`tools` 不检查句柄；智能体的 `busy` 消息说成请求执行器；
脚本 `labels()` 看不到结构公开；桌面把“按行运行”的门槛绑在当前格式上，格式 12 的项目被挡住并提示“需要格式 10”；12→13 升级测试没有用到真实的旧表。
未核实的一项（桌面数据页还不能显示结构公开）记为已知限制，三档控件在 S2b。

## 2026-10-09：S2 智能体 harness 设计与所有者决定

设计（`docs/design/agent-harness.md`）由一个工作流完成：四路梳理现有代码（请求与草案、脚本目录与副作用、MuFerro 链路、工具调用的模型层），
三个方案（安全优先、验收优先、平台优先）独立设计，三位评审对照代码打分，以“验收优先”为底、嫁接另两者的数据边界与审计设计。
所有者作答：规划只用本机或机构内模型（Token Plan 只用于子请求）；v1 不准备运行、S2c 加批准开始；不确定后会话结束；
新增“结构公开”标注；上限按建议；v1 提供签名的草案批准；其余技术项按建议。

## 2026-10-09：思劲平台 S1d（能力分档与自动切换）

所有者决定（四项都按建议）：AI 助手默认“自动”、可固定；按任务分档（提问用最近最快、参数建议用最强）；只在确定没有发出时自动回退；
需要时自动启动本机模型。实现：`suan/models/routing.py` 给出候选与排除原因（数据私有时排除外部端点、网络设置、缺密钥、无模型），
`models.route`（脚本 `stk.project.route_model()`），端点可声明 `tier`；请求在创建时冻结端点与模型，所以“自动”在准备问题时解析为具体端点，
回退时另建请求，失败的那条留在记录里。为使“确定没有发出”成立，连接阶段的失败（拒绝连接、DNS、TLS 握手）改记为 `failed/adapter_failed`，
连接中被取消记为已取消。桌面：端点下拉框首项“自动（推荐）”，显示将用的模型与理由或为何没有模型；发送时先启动本机模型（看本次启动的进度事件），
`adapter_failed` 或启动失败时改问另一个端点上的下一个候选并说明。默认改为“自动”后，私有数据而只有 Token Plan 时没有候选，
11 个原生测试改为显式选择 Token Plan（与之前的行为一致）。

交付前审查（4 个方向、32 项，核实 31 项属实，全部修正）：目录里已没有的受管端点被当作可用、失败过的本机模型仍排第一、目录读不了时整个路由失败、
目录档位未校验；桌面读缓存里上一次的“失败”而立即误回退、启动被拒时一直等待、取消后仍会回退、服务端拒绝后“发送”失效、准备时项目忙导致放弃、
路由缓存不随 Token Plan 密钥变化且多个 AI 编辑器互相驱逐、路由出错时一直显示“正在选择”、按状态与模型匹配可能挂到别的请求上；
连接中取消被记为失败而触发回退；回退提示对 4xx 说“无法连接”；协议规范缺 `models.local.*`、`models.route` 与 `tier`，脚本可用方法的说明过时；
请求说明与设计文档里“连接失败为不确定”等表述。

## 2026-10-09：Python 下限升到 3.11

按所有者决定（最低 3.11、默认 3.12；Flower 单独环境，因此不放宽 Web 栈）：`pyproject.toml` 改为 `>=3.11,<3.15` 并去掉 tomli；
Runtime CI 的 Linux 矩阵改为 3.11、3.12、3.14，Windows 客户端为 3.11、3.12；Runtime 自检、`suan graph doctor` 与 `desktop/setup.py` 的版本门槛改为 3.11；
四处 `tomli` 回退改为直接 `import tomllib`；用户文档改为“3.11–3.14（推荐 3.12）”。历史验收记录中的 3.10 不改。
首次在 3.14 上跑全量测试，发现 2 项失败：Python 3.13 起 `Path.resolve()` 遇到符号链接环不再抛 `RuntimeError`，
环一直到打开文件时才以 ELOOP 报错，`LocalFiles.open` 没有接住；改为把 ELOOP 当作文件不存在（与 3.12 的结果一致）。

## 2026-10-09：所有者第三轮决定

所有者答复第二轮评估：Flower 单独环境；内网穿透用思劲服务器辅助打通、之后直连（即 WebRTC/ICE；查看了 GL.iNet KVM 的开源固件，
它同样是 WebRTC + STUN + TURN）；端口全部被封时任何方式都不通，只放行 443 时只能经 TURN 中转。随后逐项选择 9 项决定，
与建议不同的两项：不做前置的三校实测、边用边测；文献直连失败时用端到端加密的中继兜底（修改第二轮第 7 条）。下一步 Python 3.11 升级，再做 S1d。

## 2026-10-09：思劲平台 S1c（本机一键部署）

所有者第二轮决定（2026-10-08）：联邦学习选 Flower 作算法库；STK 与 Web 框架升到 Python ≥ 3.11；训练节点先只支持 Linux；
首批三个课题组（合作方在北京、珠海、聊城）；学校不能开端口，先做内网穿透，可参考 RustDesk、ZeroTier；文献存课题组 Linux 服务器、直连不经思劲中转（以后做）；
中心服务与中继放在思劲服务器；不跨机构分享，只允许“借阅”（远程看、不能下载）；新增需求：共享对话、作图与页面，带语音和文字交流。
这几项的评估见 `docs/design/` 的四份第二轮评估，待所有者决定。

S1c 交付：`suan/models/local.py` 与随 STK 发布的 `suan/models/catalog.json`（14 项、5 个平台的 llama.cpp b11429 构建，
大小与 SHA-256 来自发布者仓库的固定修订，2026-10-08 核对；317 个下载地址逐一用 Range 请求核对了长度，GGUF 文件另核对文件头）；
后台服务 `models.local.*` 与事件 `models.local.progress`；桌面“本机模型”面板。实现中经过一轮 50 项的对抗式审查（45 项属实并已修正，
包括：短读删除了已下载字节、未核对的文件被使用、解包 tar 的链接、两次安装同时下载运行时、遗留的 llama-server 进程、死掉的服务器仍显示运行、
改为离线时下载不停、推荐重复请求、桌面读取空 JSON 崩溃、`ai_editor.cc` 中对临时对象的悬空引用）。

真实运行（不进 CI，手动）：从 ModelScope 经代理下载 Qwen3.5-4B Q4_K_M（2.7 GB，220 秒）并核对哈希，解包官方 llama.cpp b11429，
llama-server 5 秒就绪，经网关提问。由此发现并修正三处问题：
- llama-server 默认不设密钥、允许所有 CORS 来源，浏览器里的任何网页都能调用本机模型并从 `/slots` 读到之前的提示（含私有数据）。
  现在每次启动生成随机密钥（经环境变量传入，不在命令行），登记为端点的会话密钥，并加 `--no-slots`；不带密钥的请求实测返回 401。
  这类端点标为 `managed`，不能在设置中清除或替换密钥、不能单独移除；服务器进程的环境也去掉了 Token Plan 等密钥。
- 网关对所有 OpenAI 兼容端点只给 60 秒，本机 CPU 上的模型先思考再回答，第一次提问 60 秒后成了“不确定”。现在本机与机构内端点的期限为 30 分钟，
  且取消时立即关闭连接（本机为“已取消”，机构内为“不确定”）；外部端点 5 分钟；内置 Token Plan 不变。
- Qwen3.5 默认先思考：一个两句话的回答生成了 2,335 个 token，用时 188.6 秒（13 token/秒）。与 Token Plan 一致（`enable_thinking` 为 false），
  本机服务器以 `--reasoning off` 启动，同一问题 14.9 秒完成。
推荐规则改为：档位高者优先，同档中能整个放进 GPU 的优先，再比大小，8 位版只在余量达到所需量四成以上时推荐（原先的排序使 8 位版永远不会被推荐）；
目录项可用 `recommend_on` 限定推荐的设备——Gemma 只作备选（其参数量含逐层嵌入，按大小会压过 Qwen），稠密 27B 只在 GPU、35B-A3B 只在 CPU 上推荐。

交付前的审查（4 个方向、27 项，独立核实 26 项属实，全部修正）：Windows 与 Linux arm64 随附的是 CPU 版 llama.cpp 却按显存推荐
（现按 `llama_gpu` 判断，Linux 还要有 Vulkan 加载器）；内存充足的 GPU 机器会推荐 CPU 上的 MoE 8 位版（改为上述排序）；Apple 统一内存按 Metal 默认份额并受可用内存限制；
nvidia-smi 的显存按整 GB 计（H100 的 81559 MiB 算 80 GB）；8 GB 笔记本没有可装的项（加 4B 的 8K 上下文版）；续传时部分文件计入磁盘需求；
`-ngl 999` 改为由 llama.cpp 按空闲显存决定；目录校验 `recommend_on` 与数值字段；`remove`、`stop` 与监护线程登记端点之间的竞争；
受管密钥优先于 `STK_MODEL_KEY_*`；服务器环境再去掉代理与口令类变量；`local-` 开头的端点 ID 不能手动添加；导入时改网络设置不再取消导入；
无法启动的模型不再每次自动启动；建立连接仍限 60 秒（取消只在连接建立后生效）；HTTPS 连接取消时用普通套接字关闭，不先拆掉 TLS；
桌面硬件一栏加可用磁盘并注明未使用的显卡；文档中 vLLM 只评估（桌面不提供下载）、原生测试不提问、核对数字等更正。

## 2026-10-08：思劲平台 S1a/S1b（模型网关、数据边界）与两份评估

所有者答复平台方案：SDK 即 STK；默认 API 沿用 Token Plan 并支持 OpenAI 兼容端点；本地运行时按推荐（llama.cpp / vLLM）；按 S1 → S7；
联邦学习框架与节点通信先评估；付费全文只留本地、类 BitTorrent 按需共享；数据默认不外发、人工标注公开才外发。随后补充：思劲尚无材料预测模型，
计划训练铁电与锂电池两个（方案据此把 S3 改为先从零训练，联邦学习首个场景建议铁电）。

S1a：格式 12 `project_labels`（只追加，标注不推进修订）；`suan/models/` 的端点登记（回环地址为本机，其余默认外部、可声明机构内，外部须 HTTPS）、
端点密钥（环境变量优先、0600 文件）、网络设置（离线/机构内/允许外网）、`OpenAICompatibleAdapter`（共用阿里云适配器的载荷检查与回复解析，丢弃推理文本）、
`ModelGateway.admit` 发送前检查；端点、密钥与网络设置不进脚本目录（智能体脚本不能自行打开外发通道）。
发现并修复阿里云读取器的潜在问题：服务器回复后关闭连接时，读完正文再对已关闭的套接字设超时，结果被判为“不确定”；本机服务器（llama.cpp、vLLM）
会这样回复，测试用 HTTP/1.0 与 `Connection: close` 两种服务器覆盖，去掉修复后这两项失败。
S1b：桌面 `ModelSettings`、`ProjectDataLabels`、数据页“公开数据”、AI 助手端点与模型选择、端点密钥、“模型与网络”设置，不能发送时说明原因
（共用 `model_gate.hh`，“讨论”页的发送按钮也按端点判断）。

数据边界的连带变化：发往内置 Token Plan（外部）的问题现在要求其参数表标注为公开；相关 Python 与原生测试、截图场景在发送前标注，
流式测试包装改为替换模型网关中的适配器。完整 CTest 首次 1270/1278：流式测试 4 项因未标注被拒，AI 流式截图 4 项因包装仍替换旧位置的适配器
而用了真实适配器、等待超时后崩溃；修正后通过。

评估（子代理调研，写入 `docs/design/`，待所有者决定）：联邦学习——没有现成框架满足全部需要，建议 Flower 只作算法库（SecAgg+、差分隐私），
经 STK 出站通道实现其 `Grid` 接口；flwr 要求 Python ≥ 3.11 且锁定的 fastapi 与 STK 冲突，需独立虚拟环境；Windows 站点要先决定 WSL2 或另配 Linux 节点。
组网——基础层用现有 hub 的出站 HTTPS/WSS，但节点代理目前禁用 HTTP 代理（`agent.py` 的 `proxy=None`，已核对），须先支持显式代理；
文献共享在 hub 上加不落盘的直通中继与分块校验；可选直连用 iroh 1.x（按站点经校方同意开启）；不推荐 WireGuard/Nebula（只走 UDP）、
ZeroTier（控制器商用需许可）、自建 Headscale/NetBird 控制面与 Shadowsocks；协调服务与中继建议部署在境内并办理备案，部分法律问题待法务确认。

## 2026-10-08：归档改为“冻结”（所有者澄清）

所有者澄清“只读”：归档意味着不能修改，但仍可用同样的设置运行；要修改就取消归档，或复制出新版本再改。确认三点：
运行记录（含未发送的问题、已准备未提交的仿真运行）不在原记录上重试/发送/提交，要再运行就新建；草案不直接应用或放弃，复制后再改或应用；
批次运行写回结果属于运行记录，允许。

服务端：撤去对“使用”的拒绝——工作流运行准备不再检查工作流或其分析步骤是否归档，`workflows.validate` 撤回 `archived_reference`，
分析运行准备不检查分析，批次准备/提交不检查（删除控制台的 `_archived`），上下文可添加消息与建请求，已归档问题的回复可以转换为草案。
保留对“修改”的拒绝：工作流/分析保存、运行记录开始与重试、仿真运行提交、问题发送、草案应用与放弃。
桌面：按类别说明（`archive.notice.*`）；工作流运行区不再因归档阻止运行，新增“复制为新工作流”（以 `{name}（副本）` 新建并选中）；
分析的准备与“运行并显示”不再阻止，已归档的已准备分析运行不能开始；AI 助手与“讨论”页可就已归档上下文提问与记消息，已归档问题的回复可生成草案；
已归档草案可载入查看，“应用”与“放弃”不可用，经“以当前修订另起草案并检查”复制后应用；批次不再阻止准备与提交；工作流编辑器不再因归档变化重读检查。

## 2026-10-08：归档 A2（桌面）与 A3

A2a（`f1e97a7`）：`ProjectArchive`（`project.archive.list`，`project.archive.changed` 或自己的修改后重读，过时的项目打开与后台服务的回复忽略；
`version()` 只在已归档集合变化时增加）与共用控件 `archive_controls.hh`（`archive_filter`、`archive_switch`、`archive_button`、`archived_notice`）。
工作流编辑器：列表与运行列表带 `archived` 过滤，记下读取时的“过滤:版本”，变化时从第一页重读（归档不推进修订）；已归档工作流 `editable()` 为假、
运行区提示先恢复；归档工作流连带运行（`include_runs`，恢复同样）；运行单独归档（运行中不可）、已归档运行不重试。
顺带修复：运行列表原按修订读取一次，同一修订内切到另一个工作流时不读它的运行，改为按“工作流@修订”。
A2b：`ProjectAnalyses`/`ProjectAnalysisRuns` 的过滤与分析编辑器（已归档分析的参数、画布与重命名不可用，不能准备或“运行并显示”）；
`ProjectDiscussion` 的上下文与问答列表过滤由 AI 助手与“讨论”页共用（`show_archived`/`sync_archive`），AI 助手历史开关、已归档问题不能发送或生成草案、
所选上下文已归档时不能提问，“讨论”页上下文不能再添加消息；`ProjectState` 的草案与仿真运行列表过滤（仿真运行改用通用 `project.runs.list` 调用以带过滤）；
仿真批次在界面按归档 ID 过滤，已归档批次不能准备或提交。
A3：Home“需要关注”已看项的“归档”（`ProjectAttention` 在归档版本变化时重读）；`workflows.validate` 对引用已归档分析的步骤给出问题 `archived_reference`
（仍可保存；准备运行时仍以 `Archived` 拒绝并给出步骤），工作流编辑器在归档版本变化时重读并检查所显示的工作流。

critical review（顾问）：A2a 单独提交前跑完整 CTest，并在提交说明中点名运行列表的行为修复；方案中“每个列表都有显示已归档（N）”改为有已归档对象时才出现、
运行开关不显示数量（按项目统计）、恢复工作流会恢复其单独归档过的运行——均写入方案“已知限制”。引用提示按“恢复前只读”细化为工作流问题，
与方案“提示而非错误”的差别（只影响运行，不影响保存）已在方案中注明。
完整 CTest 首次 1273/1278：AI 请求截图（4 个后端/语言）与“运行按钮”交互测试失败——列表在归档状态同步前读取（记为未过滤），
首帧发现过滤不同而重读，界面短暂忙碌、按钮不可用。修正：计算过滤前先同步归档状态；打开项目后第一次读到的归档集合不算变化
（列表本就由服务端过滤），之后集合变化、或收到变化通知/自己写入后的读取才算；草案与仿真运行的“显示已归档”选择移入 `ProjectState`，
使程序直接读取的列表也用同一过滤。

## 2026-10-08：归档 A1b（列表过滤、只读、需要关注与搜索）

`archive.where/clause` 加入八个列表（工作流、分析、工作流运行、分析运行、仿真运行、请求、草案、上下文）的 SQL，受管表格的 `total` 同样过滤；
后台服务与 `stk` 的列表接受 `archived`（脚本只在过滤时发送）。只读检查（`Archived` → `conflict`）：工作流/分析保存、工作流运行准备（含引用已归档分析的步骤）、
工作流运行开始、分析运行准备与开始、仿真运行提交、批次准备与提交（控制台经 `p.archived("batch")`）、草案应用与放弃、上下文添加消息与其消息建请求、
请求发送与转换。“需要关注”各来源只列未归档；搜索带 `archived` 标记、同类中排在后面（已归档上下文的消息视为已归档）。
已知范围：只读不拦截直接对受管表格的 `project.apply`（删除仍是普通表格编辑），写入方案与协议说明。

## 2026-10-08：归档 A1a（格式 11 与归档记录）

所有者确认归档方案：B（独立记录，格式 11）、恢复前只读、搜索包含已归档并标注、首版九类（含草案与上下文，按“我认为需要包含”理解）。
A1a：`_DDL_V11` 的 `project_archive`（类别 CHECK、按对象索引），新建与 10→11 升级；`suan/project/archive.py` 的 `Archive.set/list/ids/is_archived/require_active`
与供列表使用的 `clause/where`（以每个对象最后一行为当前状态）；归档前检查对象存在、进行中则拒绝（整次调用不写入），已在目标状态的对象不计；
`include_runs` 连带工作流的非运行中运行。后台服务 `project.archive.set/list`（`set` 有变化时发 `project.archive.changed`）、schema、
`stk.project.archive/unarchive/archived`。格式提升连带：伪造旧格式的测试补删 `project_archive`，固定为 10 的断言改为 11，桌面 `kProjectFormatVersion = 11`。

## 2026-10-07：P2 L2 运行新增的行、L3 结果回到对话

L2：工作流摘要（列表与读取）增加单一参数表步骤的 `table_id`；工作流编辑器 `navigate` 接受 `{table_id, rows}`（无 `workflow_id`）：
保留正在显示且使用该表的工作流，否则在列表中选第一份可读且使用该表的工作流，表格读到这些行后只勾选它们；没有适用工作流时在列表下说明。
AI 助手对已应用的 `stk.parameter-sweep/1` 草案显示“用工作流运行新增的 N 行”（从草案的 `add_record` 命令得到行与表），经 `AppShell::open_target_later` 导航。
L3：运行区对有 MuFerro 结果行（`produced.result_record_id`）的成功任务显示“就这 N 行的结果提问”，以 `ProjectDiscussion::capture` 捕获结果表中这些行的数值字段，
成功后打开 AI 助手（该上下文即为下一问题使用的数据）。

critical review：上下文只含一张表，结果上下文不能作为下一轮扫描的基准（扫描基准行须在所捕获的选择中），写入方案与桌面说明。

## 2026-10-07：P2 L1 AI 扫描提议

方案 [ai-batch-loop.md](design/ai-batch-loop.md)（按推荐执行）。`suan/project/parameter_sweep.py`：严格解析 `stk.parameter-sweep/1` 回复
（基准行与扫描字段必须在上下文所选范围内、标量字段、1–8 轴、`product`/`zip`），在等于上下文修订的当前快照上用 `plan_sweep` 展开
（`new_id` 派生 `uuid5(请求, 项目:sweep:i)`，最多 100 行），经预览保存为草案并链接到助手消息；已保存的草案以回复文本摘要、标题与基准修订核对，
不重新编译（扫描读取基准行的当前其他单元格，之后的编辑会让重新编译得到不同结果）。`Requests.propose_edits/edit_proposal` 按用途分派；
提示 `_PARAMETER_SWEEP_SYSTEM`；schema 的提问用途枚举。桌面：`structured_proposal()` 统一参数修改与扫描两种用途的保存/打开检查，
AI 助手“用途”第三项与扫描回复的文字呈现。

critical review：顾问指出若沿用参数修改的“重新编译后比较”核对已保存草案，任何后续编辑（包括运行登记输出）都会让已保存的扫描草案无法读取，
改为摘要核对；草案的预览经测试确认能处理同批新增行的赋值与公式复制。

## 2026-10-07：W5b MuFerro 工作流的桌面运行区

仿真批次面板的运行环境选择与执行选项提取为共用的 `SimulationTarget`（`src/editors/simulation_target.*`，批次行为不变）。工作流编辑器的运行区在工作流含
`muferro/1` 步骤时显示它们，“运行所选 N 行”改为“在 … 上运行所选 N 行”，未选可用 Runtime 时不可运行；`ProjectWorkflows::run_rows` 带上
`simulation`；重算过期行沿用原运行冻结的连接与选项。任务格在尝试运行中显示远程阶段（已提交/排队中/Runtime 运行中/收集结果/接管中），
选中行列出各步骤的仿真运行与 Runtime 任务；MuFerro 行在勾选框中显示案例名与带单位的字段。服务读取间隔可用 `STK_WORKFLOW_POLL_SECONDS` 调整（0.02–3600 秒）。

critical review（截图）：首张截图截在切换工作流的中间状态（画布仍是上一份），截图脚本改为等候新工作流检查完成；行勾选框只显示“行 1”，补上案例名与温度；
成功后的行详情仍写“收集结果”，改为只在运行中显示阶段。

## 2026-10-07：W5a MuFerro 按行工作流运行（服务与脚本）

所有者决定：归档方案（已写）→ MuFerro 按行工作流运行 → AI 批量模拟闭环。W5a：`WorkflowRuns.prepare(..., simulation=)` 冻结连接、
端点指纹（`server_key`）、`muferro_spec` 选项与每行全部案例字段（准备时逐行 `describe_case` 校验，不提交任何东西）；MuFerro 模板标记 `remote`。
执行器经服务内的 `stk` 接口（`Bridge.script_call`，与控制台相同的操作）调用 `stk.muferro.prepare/collect` 与 `p.runs.submit/refresh/cancel`：
主循环改为多轮——远程步骤提交后即返回，后续每轮（`poll_seconds`，默认 15 秒）读取任务，成功则收集、按 `muferro.final_state` 选出最终状态
登记并捕获为该行快照，再运行下游分析。`describe_case/prepare` 新增可选 `identity`（工作流运行/步骤/行/尝试），批次标签不变。
进度保存为同一尝试的又一条 `running` 事件（格式 10 的表有状态 CHECK 约束，不能加新状态），任务的 `progress` 跨尝试保留；
停止跟踪时尝试记为中断（`detached`），下次开始接管未失败的仿真运行；用户取消时以不可中断的接口取消 Runtime 任务。

critical review：首版把进度写成新状态 `progress`，被表的 CHECK 约束拒绝（测试发现），改为 `running` 事件；一次补丁脚本漏写文件导致执行器改动缺失，
重做并核对；控制台调用在取消后全部报 `cancelled`，取消 Runtime 任务改用单独、永不取消的接口；MuFerro 准备读取当前行，执行前比较冻结值。

## 2026-10-07：体验包 U3 项目内搜索

`suan/project/search.py` 的 `search(store, query, limit)`：从项目快照查找参数表（不含受管的分析、工作流与文件表）的表名、字段名与文本单元格，
从受管表取工作流与分析名称、文件名与路径，分页读取草案标题，直接读取消息记录的文字（读不出的记录不算命中）；结果按类别固定顺序、每类最多 50 项，
单元格与消息给出匹配处前后约 80 字的单行片段。后台服务 `project.search`、schema（`projectSearchItem`）、协议说明与 `stk.project.search()`。
桌面 `ProjectSearch`（明确开始，项目或服务变化时丢弃结果）；工作台“搜索项目”方框；`AppShell::open_project_page_later` 新增 `record_id`，
打开数据页或文件页时选中该行（换行同样受未保存修改的检查）。

critical review：结果不会自行更新，项目在搜索后变化时可能指向已删除的行（打开时选择被清除），方框中注明“项目在搜索后有变化”并提示再次搜索；
测试中打开文件页会占用工作台所在区域，测试改为切回工作台标签。

已知限制：搜索要读完所有消息，并在后台服务的项目会话锁内进行，期间其他项目操作等待（当前规模下很快）；打开同一表格的另一行也会检查
其他标签的未保存修改，可能以“选择被占用”提示拒绝。U2 的用量读取失败后不自动重试，直到下一次有回复完成或重新打开项目。

## 2026-10-07：体验包 U2 用量可见

`Requests.usage()` 直接读取请求记录（不逐条校验哈希链，记录读不出时只是不计入），合计状态为“已完成”且结果带服务商回执
（`input_tokens`/`output_tokens`）的请求，按服务商报告的模型（没有则用请求冻结的模型）分列；后台服务 `project.requests.usage`、schema、
协议说明与 `stk.project.requests.usage()`。桌面 `ProjectDiscussion::load_usage`：读取有自己的在途标记，不设置对话的 `busy`
（否则读取期间“发送”“取消”等按钮会被禁用）；展示过的已完成回复变化时重读。AI 助手配置区一行“本项目已用 … token（N 次完成的请求，服务商回执）”，
无回执的完成数另注，悬停按模型分列；发送按钮写明“（模型）”。

critical review（截图）：首版读取经由对话的通用调用，读取期间界面按钮被禁用，AI 截图脚本的按钮检查失败，改为独立读取；
截图脚本在绘制后才发出读取，需在最后一帧前等待回复（窄布局折叠配置区，不发出读取，不等待）。

## 2026-10-07：体验包 U4 工作流记住视图

`AnalysisGraphCanvas::look_at(center, zoom, width, height, ui_scale)` 与 `center()`：以画布中心的图坐标和缩放表示视图，
在任意视口大小与界面缩放下恢复（平移以物理像素保存，不能直接复用）。工作流编辑器的 `ViewMemory` 按（项目, 工作流）记录中心、缩放、
所选步骤与显示的运行：每帧在编辑器空闲时（无读取、无拖动、没有另一份在路上）更新，切换前再记一次；再次显示时先恢复视图（代替适应），
选中记住的步骤并读取记住的运行。最近 50 份与上次显示的工作流随布局保存，新编辑器在项目的工作流列表中找到它就先显示它。

critical review：记录起初放在 GPU 绘制中，切换时会把正在离开的工作流记成“未选步骤、无运行”（点击后先清空所选、读取期间旧画面仍在），
改为空闲时才记录并在切换前显式保存；步骤与运行的记忆不再依赖画布已绘制（未绘制时沿用记住的视图）；项目切换时按视图所属项目记录。
测试中一处 `for (… : save_state().at("views"))` 遍历了已销毁的临时对象（C++23 之前的范围 for 规则），改为先保存结果。

## 2026-10-07：体验包 U1 需要处理；6fc18a4 CI 修复

U1：`suan/project/attention.py` 的 `collect(store)` 只读汇总各来源（每类最近 50 条），每项带结构化字段、导航目标与随状态变化的 `key`；
`suan/desktop_bridge/attention.py` 把“已查看”写入服务状态目录的 `attention-viewed.json`（每项目最多 2000 个）；
后台服务 `project.attention.list/viewed`、schema、协议说明与 `stk.project.attention()/mark_viewed()`。桌面 `ProjectAttention`
（项目修订变化、仿真运行变化事件或标记已看后重读；有运行中事项时每 3 秒重读，状态栏负责定时唤醒）；工作台“需要关注”方框与状态栏“需要处理 N”；
`AppShell::open_target_later` 打开编辑器并导航到目标，工作流编辑器 `navigate` 支持 `run_id`，项目页面新增 `review`。
工作台参数表计数不再包含工作流托管表。

critical review：仿真运行的状态判定原先用了不存在的状态名（`lost`/`completed`），改为 Runtime 实际状态（失败/待核实 → 需要处理，成功/已取消 → 已完成，
提交中/已提交/排队/运行 → 运行中）；标记已看时进行中的读取可能把旧状态写回，改为丢弃该读取并在标记保存后重读；方框标题与分组同名，改为“需要关注”。

6fc18a4 的 CI 失败（三处）：Windows 上 `_owner_alive` 用 `os.kill(pid, 0)` 检查进程，而 Windows 的信号 0 是 `CTRL_C_EVENT`，
会向控制台进程组发送 Ctrl+C（测试进程收到 KeyboardInterrupt；桌面中可能中断服务本身），改用基础依赖 `psutil.pid_exists`；
Windows 上两个工作流编辑器测试用固定帧数等待后台回复，慢机器上不够，改为 `frames_until`（最多 30 秒）；
macOS 上 `workflow_run_wide_render_metal_en` 退出时报告一个 `MTLSafeFreeList` 未释放（Blender Metal 后端的命令缓冲完成回调与缓冲池释放的时序），
168 个 Metal 测试中仅此一例，与本次改动无关，暂记为间歇问题，观察下一次 CI。

## 2026-10-07：W4 复查补丁

复查发现：`recover` 只看本进程的执行器，另一个桌面或无头会话的服务仍在执行时也会把其尝试标为中断，原执行器随后结束尝试被当作过期拒绝；
另一进程写入的取消没人响应；执行器意外异常被吞掉，运行停止却无原因。修复：认领时记录服务进程（主机与 pid），`recover` 在该进程仍存在时
以 `busy` 拒绝（`force` 可强制）；执行器每个任务前读取存储的取消请求；意外异常写入日志并作为停止事件的 `stop_error`，运行区显示“运行意外停止”。
设计文档的步骤种类表补上本机模板 `demo-synthetic/1`。

## 2026-10-07：P3 W4c 过期与按行重算

`WorkflowRuns.stale(run_id)`（只读）按冻结计划逐行逐步骤与当前定义比较：工作流缺失/不可读、步骤定义改变（忽略 `label`）、
分析内容哈希改变或分析缺失、模板不再注册、该步骤按字段取用的值改变（带字段名与前后值）或出现公式错误、行被删除；
上游步骤过期时下游标 `upstream_changed`。后台服务 `project.workflow_runs.stale`、schema、协议说明与 `stk.project.workflow_runs.stale`。
运行区在运行停止后读取过期信息（每次项目修订变化后重读），行号与任务格标“过期”（琥珀色），选中行列出原因，
“重算过期的 N 行”用当前定义开始新运行，原运行不变。

critical review（截图）：行列宽度放不下“2 · 过期”，加宽。

## 2026-10-07：P3 W4b 工作流运行区

工作流编辑器新增“运行”面板（项目格式 10 且后台服务提供 `project.workflow_runs.*` 时）：说明冻结语义（ADE 做法 14）；
参数表行的复选框（显示工作流按字段取用的值，例如“温度 325 K”；记住的是取消勾选的行，新增行默认选中）；“运行所选 N 行”
在保存且校验通过的工作流上以读取时的修订准备并开始运行（ADE 做法 3：立即返回）；运行记录（最近 20 次）与行 × 步骤状态表
（按状态着色，尝试序号 #n）；选中一行显示失败原因与“打开该行的分析运行”（分析图 `navigate` 新增 `analysis_run_id`，打开“运行”页并选中）；
重试未成功的任务、取消、恢复。运行中每 0.5 秒读取一次，停止后重读运行记录。仿真模板在界面中用目录名称（`workflow.template.*`）。

critical review（截图）：模板名称在中文界面显示英文（改为目录名称）；运行结束后列表刷新在服务忙时被丢弃（改为成功发出才记下）；
初次显示表格时“全选”早于新增行导致 0 行可运行（改为记住取消勾选的行）。测试：画布手势测试需等待编辑器空闲（读取运行记录时手势暂不可用）。

## 2026-10-07：P3 W4a-2 工作流运行执行器

`WorkflowRunExecutor`（后台服务，每次运行一个线程，最多 4 个）：认领后逐行、按冻结的步骤顺序执行未成功的任务；上游未成功的任务保持等待，
不影响其他行。本机模板写入每次尝试独立的目录，登记输出并捕获为该行快照（普通编辑，修订冲突时有限重试，并以 `project.changed`
通知已打开的句柄——新增 `ProjectSessions.handles_of` 与服务的 `_announce`）；分析步骤用该快照与行的参数覆盖值准备分析运行，
`expected_document_sha256` 保证保存的分析未变（否则 `AnalysisChanged`，任务码 `analysis_changed`，不重试），交给本机分析执行器并等待结束。
取消在当前任务后停止并取消进行中的分析；`recover` 在没有存活执行器时把运行中的尝试标为中断。后台服务方法 `project.workflow_runs.*`、
schema、协议说明与 `stk.project.workflow_runs`。示例工作流改为“算例 → 合成求解 → 温度场”（旧的“场文件”快照三个文件同名，不能按行运行）。

critical review：分析已改的拒绝起初是修订冲突，被当作并发编辑重试 8 次后报“项目持续变化”，改为独立的不可重试错误。

## 2026-10-07：P3 W4a-1 工作流运行存储（格式 10）

所有者按推荐确认 W4 方案四问。实现：项目格式 10（`workflow_run_plans`、`workflow_run_events`，可从 1–9 备份后显式升级）；
`WorkflowRuns.prepare` 在一次检查中读取工作流（须校验通过）、项目模型与各对象，冻结所选行（行号与所用字段值，公式错误拒绝）、
执行顺序（数据流与先完成的拓扑序，参数表步骤不执行）、每个（步骤、行）的参数、被引用分析的完整文档与内容哈希、
快照文件名（重名时拒绝供分析使用）与输出目录 `results/workflow-runs/<运行 ID>`；`muferro/1` 步骤、多个参数表步骤、
来自多个来源的分析输入均在准备时拒绝（校验不报，只查看的工作流不受影响）。事件按（步骤、行）编号尝试，
`finish_attempt` 只接受最新且仍在运行的尝试，执行器认领/取消/停止/中断（服务重启后）均为带哈希链的事件，不提升编辑修订。
本机模板 `demo-synthetic/1` 不进入批次模板列表，声明参数 `temperature`（K）供字段绑定；工作流校验把模板参数当作步骤参数检查。
分析运行准备新增可选 `parameter_overrides`：冻结在计划中、计入请求身份，文档保持保存的分析原样，执行时叠加在提交参数上。

critical review：准备时工作流记录变量被循环中的行变量覆盖（改名修复）；`muferro/1` 拒绝改到行检查之前（与所选行无关）；
多处模拟旧格式的测试原来只删格式 9 的表，升级到 10 时报表已存在，统一加删格式 10 的两张表。

## 2026-10-07：W4 方案草案与 ADE 分组确认

所有者确认 ADE 参考的三组安排（第 1 组并入 W4、第 2 组体验包在 W4 后、第 3 组交 AI 闭环同事）。新增
[工作流按行运行、过期与重算](design/workflow-runs.md) 方案草案：格式 10 的运行计划与事件、步骤×行的任务与编号尝试、
首版只执行本机 `demo-synthetic/1` 与分析、明确运行中自动登记模板声明的输出、分析运行的按行参数覆盖、过期原因与按行重算；
四个问题待所有者确认，未写代码。

## 2026-10-07：P3 W3c-2 工作流编辑界面

工作流编辑器接入 `WorkflowDraft`：选中可读工作流时固定草稿；有修改时画布显示候选（标题“未保存”，修改的步骤描边），
候选检查到达前用 `workflow_provisional_validation` 依次取上次已检查的候选与已保存工作流的步骤摘要，新步骤在下一次修改时不再丢失端口和参数控件。
每次修改后自动发送候选检查（只保留最新）；保存不要求检查通过，但须等本次候选的检查结果（或错误）到达。
“编辑工作流”面板：改名、种类+对象（来自 `choices`）添加到所选步骤右侧并重新适应视图、改动清单、保存/放弃、新建、删除（项目表格的
`delete_record`，可撤销）。“所选步骤”面板：名称、各输入按类型可选的来源、先完成列表、分析参数三种取值方式、删除。
画布：拖动移动、拖线（本地按端口类型拒绝不符，拖到（等待）追加先后）、Delete。另一项目编辑使修订前进时照常重读，
未改动的工作流由 `WorkflowDraft::rebase` 保留修改，被改动的工作流使修改脱离（只能放弃）。

critical review：保存后列表页被清空且不再重读（改为缺页时每个修订重读一次）；新步骤每次修改后暂时失去端口与参数控件
（改为优先使用上次检查的候选摘要）；新增步骤在视图外（改为添加后重新适应）；测试中在读取期间点击被丢弃的列表（测试改为等待控件可用，
界面本身在读取时禁用列表）。

## 2026-10-07：P3 W3c-1 工作流编辑模型

按复查建议把 W3c 拆为模型（本次）与界面。`project.workflows.choices` 列出步骤可引用的对象：参数表（不含分析、工作流、文件索引三张托管表，
最多 500）、输入快照（新的在前，最多 200）、可读的保存分析与已注册仿真模板。C++ `WorkflowDraft` 是保存工作流的候选副本，
`check_workflow_document` 与 Python `_step`/`_document` 的形状规则逐条一致（标识符、`x-` 键、引用/标签/参数/先完成的上限、位置、256 KiB），
因此界面做出的文档不会在保存时被拒；编辑清掉的 `inputs`/`parameters`/`after` 在已保存步骤原本没有时一并去掉，改回原样即丢弃副本。
`check_version()` 不随位置与名称变化，候选检查在拖动后仍有效。`ProjectWorkflows` 新增 `create/update`（回执确认后直接采用写入的文档，
项目刷新完成后由 `validate_selected()` 补做检查；回复丢失时标记不确定，重读前不再保存）、`load_choices` 与独立的候选检查槽
（复用 `AnalysisCandidateKey`/`AnalysisCandidateValidation`，不占用读取通道）。`canonical_uuid`/`visible_text` 移到 `analysis_document`
供两种草稿共用。

critical review：保存成功后链式读取会因项目正在刷新而被拒，改为采用回执确认的文档并稍后补做检查（与保存分析一致）。

## 2026-10-07：P3 W3b 工作流画布与进入分析

新增原生“工作流”编辑器（`kEditorWorkflow`，工作台“其他”入口）：`ProjectWorkflows` 读取列表、读取所选工作流后立即校验同一份文档
（回复按项目打开、桥进程与代次隔离，修订变化后自动重读一次）；`workflow_graph_view` 把步骤和校验摘要转成 `AnalysisGraphView`
（为每个步骤合成节点类型与端口，`after` 依赖用（完成）/（等待）伪端口，标签含不可能出现在端口名中的括号），画布复用分析图画布，
新增 `AnalysisGraphNode::flagged` 标出有校验问题的步骤。`Editor::navigate(target, from, reason)` 与
`AppShell::open_in_area_later/return_in_area_later`：分析步骤在同一区域的分析图标签中打开（复用已有标签，拒绝时关闭新加的标签并提示），
分析图在下一次同步时读取该分析，画布上方显示“‹ 工作流 › 步骤”返回原标签；另一分析有未保存修改时拒绝，草稿不变。
工作台原“保存的分析”页面 ID 由 `workflows` 改为 `analyses`，新 `workflows` 指向工作流编辑器；仿真面板“工作流操作”改称“仿真操作”。

critical review（截图检查）：进入分析的截图在节点目录载入前拍下，节点全显示为未知，渲染工具改为等待目录；
面包屑起初放在页头，窄区域把“定位节点”“三维”挤出可见范围，改放到画布上方的说明行；宽区域步骤名被截断，按宽窄调整宽度。
已知限制：窄区域适应窗口时缩放低于标签显示阈值，节点只显示方框（与分析图画布相同），需放大查看。
复查后补丁：进入请求在读取前遇到项目关闭或本地开始编辑时与面包屑一起丢弃，避免在之后打开的项目中读取旧 ID。

## 2026-10-07：P3 W3a 项目工作流存储与校验

所有者确认 W3 方案的四项推荐（新文档 `stk.workflow/1` 存为受管表格、编辑跟随当前修订并在执行时冻结、两层范围、
示例求解器在 W4 注册为本机模板）。实现：

- 受管表格抽到 [suan/project/managed.py](../suan/project/managed.py)（`ManagedTable` 与 JSON 拷贝/严格解码/快照上限），
  保存分析改用它，错误文字与限额不变（限额在写入时读取模块常量，原测试的 monkeypatch 仍然生效）。
- [suan/project/workflows.py](../suan/project/workflows.py)：形状检查（ID/端口/参数名为小写标识符，`x-` 键保留，位置有限且 ≤1e6，
  256 KiB/200 步/每步 64 KiB 参数）、list/get/create/update 与只读 `validate`。校验在一次读事务中解析表格、快照、保存分析与已注册模板，
  分析步骤的端口取自源节点的字面量 `binding`、图 `parameters` 与 `outputs`；`$field` 须属于本工作流的参数表步骤，
  类型兼容表见模块常量 `FIELD_PARAMETER_TYPES`，单位须相同；数据流与 `after` 合并做 Tarjan 环检测；问题上限 256 条。
- 后台服务 `project.workflows.*`（写入后发 `project.changed`）、桥 schema 与协议文档、`stk.project.workflows`、示例项目的“温度扫描”。

critical review：保存的 JSON 按规范顺序存储，对象键顺序不保留，因此分析步骤的输出端口顺序跟随存储后的图（字母序），
测试据此断言；`dynamic_binding` 消息最多列 5 个节点，避免超出协议的消息长度上限。

## 2026-10-06：P3 W3 项目工作流方案（待所有者确认）

新增[项目工作流与子图导航](design/project-workflows.md)方案草案，不含代码。要点：工作流是新的实验文档 `stk.workflow/1`，
与保存分析一样存为固定 UUID 的受管普通表格（不升级项目格式）；首版步骤只引用已有对象（参数表、`muferro/1` 仿真模板、
输入快照、保存分析）；分析步骤的输入/可暴露参数/输出直接取自保存分析的文件绑定、图 `parameters` 与图 `outputs`；
编辑时按 UUID 跟随当前修订，执行时冻结工作流快照与各运行记录，以哈希比较得出影响范围（W4）；两层导航与面包屑。
文档沿用 graph 的书写习惯，以复用 W1–W2 的候选编辑与画布代码。四个待确认问题写在方案末尾。
同时更新工作台设计中已过时的“只有单输入连线”描述，术语表加入“工作流 / Workflow”“步骤 / Step”（界面实现后启用）。

## 2026-10-06：P3 工作流编辑 W2——画布拖动与拖线

分析图画布支持编辑手势（仅在编辑与草稿一致的保存分析、无待处理输入时）：按住节点拖动只移动画面，松开时一次
`move_nodes`；从输出端口拖到输入端口按单输入或多输入列表连线；Delete 删除所选节点；被拒绝时以提示说明。
画布新增端口命中、拖线预览与“同一图的新版本保留缩放/平移”（此前每次候选更新都会重置视图）。草稿新增
`evaluation_version()`：只改位置不递增，候选校验结果绑定它，因此移动节点不会让已通过的校验失效。
新增画布单元测试 1 项与真实窗口事件的交互测试 1 项（拖动 `axes` 后无需校验即可保存且位置相符；从 `component.out`
拖到 `box.in` 后需校验，保存后连线正确）。

## 2026-10-06：P3 工作流编辑 W1c——节点参数

“编辑图结构”中所选节点的参数改用节点目录参数定义生成的表单（`node_params_schema` + `build_form`，与属性面板同一套控件），
每次控件修改成为候选图中的一次节点参数编辑；表单模型在草稿每次变化后从候选图重建（先填值再挂回调，避免重建时触发写入）。
引用图参数的取值只读显示；显式取值可恢复默认；客户端 `validate_node_params` 即时列出缺失/不合规参数。
新增“编辑图结构”中英文宽/窄截图（GL/Vulkan），检查中发现并修正：首次增删节点固定布局后改动清单逐个列出“已移动”，
改为一行汇总；新节点与已有节点重叠，改为向下避让；顶部提示仍写“连线修改”，改为“图改动”。
新增 1 项交互测试（等值面缺 `field` 时即时提示、表单填写后校验通过并只保存该参数）；完整 Linux CTest **1185/1185**。

## 2026-10-06：P3 工作流编辑 W1b——候选视图与图结构编辑

分析图编辑器在草稿有图改动时，画布、“节点”和“连线”面板改为显示候选图（标题注明未保存，改动节点琥珀色描边），
在已保存视图与候选之间切换时按节点 ID 保留选择、不重新适配视图。新增“编辑图结构”面板：从节点目录（按阶段和名称排序，
界面语言的名称）添加节点到所选节点右侧并选中、删除所选节点（级联）、公开/撤回所选节点的图输出、列出全部待保存改动；
首次增删节点时把其余未定位节点的当前位置写入 `ui.positions`，避免自动布局重排。多输入端口改为有序列表编辑（上移、下移、
移除、追加）。候选校验抽成共用函数，“连线”与“编辑图结构”中各有按钮。

critical review：原测试把“多输入只读”当作规则，按新行为改为检查列表编辑器；连线面板原说明“画布显示已保存定义”
已不成立，改为说明候选与描边。新节点只能取参数默认值，带必需参数的类型（如等值面 `field`）需等 W1c。
新增 4 项交互测试（新增节点需校验后保存且位置固定、删除节点级联、列表重排与放弃、公开/撤回输出），
连线编辑测试 11/11；完整 Linux CTest **1176/1176**。

## 2026-10-06：P3 工作流编辑 W1a——候选图模型

`AnalysisParameterDraft` 的单输入连线改动表换成一份候选图：首次图改动时复制已保存图，每次改动只动相关键，
与已保存图相同时丢弃副本（为此清除保存图中原本没有的空 `inputs`/`params`/`ui.positions`/`ui`）。新增操作：
多输入有序列表 `set_links`、`add_node`（类型名生成 ID，与任何现有 ID 不冲突，可带位置）、`remove_node`（级联删除指向它的
单连线与列表项、引用它的图输出与请求输出、位置；保留图参数和其他节点的 `$param`）、`set_node_param`、`move_nodes`、
`set_graph_output`（撤回时同时移出请求输出，至少保留一个输出）。`graph_changes()` 逐项列出改动；原 `link_edits()` 由差异推导，
原有 34 项草稿测试不改即通过。请求输出的可选名单改为来自候选图。编辑器的保存门槛改为“有影响求值的图改动才须校验”，
只改位置可直接保存。新增 5 项模型测试；完整 Linux CTest **1172/1172**。

## 2026-10-06：可用性开发包 5——无需服务器的试用路径

- **示例项目**（`suan.workflows.demo.create_demo`）：用控制台同一套操作，在新目录中依次完成参数扫描生成三行算例、
  本机合成求解器写出场文件与指标（不是物理模拟）、结果表（首列引用算例行）、文件登记与输入快照、保存“温度场”分析
  并启动、观察一次本机运行。入口：工作台“创建示例项目”（仅未打开项目时；后台服务 `demo.create`，完成后打开该项目）、
  `suan demo [目录]`、控制台 `create_demo(stk)`。默认位置 `$STK_PROJECTS_DIR`，否则 `~/STK Projects`。
- **无头 `stk`**（`suan.scripting.headless`）：在当前进程内启动私有后台服务，直接调用桌面控制台的 `script_call`，
  因此操作范围与参数校验完全相同；窗口、查看器等桌面操作明确返回 `unavailable`。默认状态目录 `~/.stk/headless`，
  可与桌面同时运行；同一目录第二个会话给出改用 `state_dir` 的提示。`python -m suan.scripting.headless [项目]` 为交互控制台。
- **Linux 快速上手**（`docs/quickstart-linux.md`）一页覆盖安装、示例项目、终端/Jupyter 与接入真实运行；
  文档站改名 STK，首页与侧栏指向快速上手（直接引用同一文件）与 GitHub 完整文档，旧 PyQt 页面归入“旧版（已停止维护）”。

critical review：示例项目默认写入用户目录，原生测试改用 `STK_PROJECTS_DIR` 指向临时目录；站点首次构建因 MDX 中
`Content` 与页面自身导出同名而失败，改名后本地 `pnpm run build` 通过（含 Pagefind 索引）。
已知限制：示例分析运行需要本机科学/VTK 依赖，缺少时运行记为失败但项目其余部分可用；`demo.create` 不在脚本目录中。

收尾复查修正：工作台示例测试原用字符串比较项目目录，macOS（`/private/var`）与 Windows（反斜杠）会失败，改为比较路径；
`hint()` 原在第一个 ". " 处截断，会把 “e.g. launcher” 截成半句，改为只在其后为大写字母时视为英文句末。
已知小问题：项目表格缓存的单元格摘要不随界面语言切换刷新，公式错误名称要等表格重新查询后才换语言。

## 2026-10-06：可用性开发包 4b——默认收起内部细节，说明压缩为一行

- 项目表格第一列由记录 UUID 前缀改为行号（按表内顺序排序），UUID 移到单元格编辑标题的悬停提示；公式错误显示为本地化名称
  （`#除以零`，14 个错误代码均有中英文名称），模型文本、搜索与测试仍用稳定代码。
- 修改检查：位置为“表 / 字段 / 第 N 行”；JSON 命令编辑器与“填入示例”移入默认收起的“高级：以 JSON 编辑命令”；
  完整值与实际应用的命令改名为“技术详情”并默认收起。
- 分析运行：运行 UUID、来源修订、快照与计划哈希移入“技术详情”面板；页首与准备面板显示分析名称（UUID 在悬停提示）。
- 仿真批次：成员与已选行以“第 N 行 · 名称 · 温度”标识，批次标题显示“MuFerro · 运行环境：名称”而非 `muferro/1 · runtime:lab`；
  AI 助手的捕获范围同样用行号。
- 新增 `hint()`：面板说明只显示第一句并以“…”结尾，完整说明（上限、不会发生的操作）在悬停提示中；首批用于 30 处主流程说明。

critical review：JSON 编辑器折叠后，7 处测试原先直接点击该输入框，改为先展开面板；草案截图原本靠点击收起“完整值”面板，
现已默认收起，夹具不再点击。完整 Linux CTest **1166/1166**。

## 2026-10-06：可用性开发包 4a——统一术语与界面内设置 API 密钥

新增[术语表](design/glossary.md)并据此修改界面文案：启动页英文 Workspace → Home，AI 工作区 → AI 助手 / AI Assistant
（“工作区”只指运行环境上的工作目录），桥接 / bridge → 后台服务 / Python service（日志标签“后台服务日志 / Service log”），
中文界面中的 Runtime、Viewer 改为运行环境、查看器，“作业”统一为“任务”（只有调度系统的作业称“集群作业”），
项目页“运行记录 / Runs”改为“仿真运行记录 / Simulation runs”。编辑器 ID、协议与 Python API 不变；用户文档同步改名。

AI 助手新增“API 密钥”：密码框输入后交给本机 Python 后台服务（`ai.credentials.set/clear`），默认只用于本次运行，
可选“在此电脑上记住”写入后台服务私有状态目录的 `token-plan-key.json`（0600，原子写入）。环境变量始终优先。
回复只含 `key_source`（environment/session/saved）与 `can_remember`，错误信息不回显输入；设置不联系服务商。
密钥来源对象 `TokenPlanCredentials` 由各后台服务实例持有并注入适配器，不使用模块级全局状态，测试之间不会串用。

critical review：首轮全量 CTest 有 25 项失败——测试运行期间正在修改后台服务的回复与协议，而 C++ 客户端在编译时内嵌协议；
重新编译后其余通过，剩下的流式测试桥替身构造函数不接受新参数，已修正。默认画面、任务与属性表单的布局金样仅因文案宽度变化而更新，
默认画面 PNG 已目视检查后替换。

## 2026-10-06：可用性开发包 3d——分析“运行并显示”

分析图“运行”页新增 **运行并显示**（位于“准备运行”之上）：一次点击依次准备、开始、等待完成、读取校验结果，
再把第一个 payload 输出打开到 Viewer。链条放在编辑器中，按每帧状态推进，每一步都是单独按钮的同一调用，
`ProjectAnalysisRuns` 的“同步/重开不执行”约定不变。链条绑定点击时的桥会话、项目句柄、分析 UUID、
准备返回的运行 UUID 与计划哈希及运行选择代次；定义被他处修改、改选其他运行、出错或结果不明时停止且不改 Viewer。
等待超过 90 秒的只读跟踪时在运行预算内（330 秒）重新读取；**停止**只结束自动步骤，不取消运行。
“在查看器中显示”按钮与链条共用 `show_output`。

critical review：显示后 Viewer 接管最大化区域，分析页控件不再可见，测试改为核对调用次数与 Viewer 来源；
失败运行（无归档结果）不读取结果；准备回复丢失时停在“结果不明”，不调用开始。
已知限制（既有）：准备要求至少一个文件映射，没有文件输入的分析目前无法从界面准备，“运行并显示”同样受限。

## 2026-10-06：可用性开发包 3c——选择运行环境并运行所选行

MuFerro 仿真与仿真批次面板不再要求先到“任务”页选连接、再手写执行选项 JSON：面板内的**运行环境**下拉框列出
已保存的直连/SSH Runtime 及其状态（选择即成为任务页的当前连接，**管理…**跳到任务页添加），
**运行方式 / MPI 进程数 / 每进程线程数**和集群作业的**时限（分钟）**直接编辑同一个选项对象，原 JSON 折叠为高级选项。
批次面板新增 **在 … 上运行所选 N 行**：Python `stk.batches.run` 在点击时的修订保存批次，在保存后的修订准备全部行，
只提交准备成功的行；提交时每行仍按冻结的批次意图核对参数。相同行与选项再次点击复用批次、方案与任务，不重复提交。
离线的运行环境、无效 JSON 与缺时限的集群作业在点击前禁用并说明原因；原先的英文硬编码错误改为中英文文案。

critical review：选择运行环境会改变任务页的当前连接（共享状态，已写入文档）；准备失败的行不再交给提交步骤，
避免在成员表留下“请先准备”的二次错误；多余的旧文案（JSON 选项、无连接）已移除。
刷新、收集、结果查看仍是明确的独立步骤；任务被接受后不在此等待完成。

## 2026-10-06：可用性开发包 3b——路径框旁的“浏览…”

项目目录、CSV 输入/输出、项目文件（多选追加）、MuFerro 案例目录与 Python 文件的路径框旁新增 **浏览…**，
复用任务页已有的系统文件对话框（Linux zenity/kdialog）。选择只填入路径，导入、登记、导出或运行仍需另行点击；
没有系统对话框时不显示按钮，对话框无法运行时在路径框下说明原因。共用的 `PathPicker` 以自身生命周期令牌丢弃
已关闭编辑器的回答，项目相关路径框还会丢弃打开对话框后已切换到其他项目的回答（否则旧路径会写进新项目的输入框）。
CSV 截图夹具接入一个不作答的对话框，以便目视检查按钮布局。

## 2026-10-06：可用性开发包 3a——参数扫描生成

新增 `suan.project.sweep.plan_sweep`：按字段的取值列表、`start/stop/count` 等间距范围或 `start/stop/step`
生成新行，全部组合（第一个参数变化最慢）或按顺序配对。取值按字段类型严格检查（整数不接受小数与布尔，
数值须有限），计算出的小数舍入到 12 位有效数字。可选基准行：未扫描字段的字面量、引用与公式复制到新行，
指向基准行自身的绑定改为新行（`T + 10 K` 仍指本行）。计划只读，不写入、不求值、不准备运行；
应用时作为一次普通 `apply`，一次修订、一次撤销。项目托管表（已保存分析、文件索引）拒绝扫描。

入口：桥 `project.sweep.plan`（只读，返回计划与所依据的修订）、Python 控制台 `stk.project.sweep(...)`
（修订不一致即冲突，`dry_run` 只返回计划）、CLI `suan project sweep`（字段与表可用名称）、
桌面项目表格页的折叠面板 **生成参数扫描**（最多 4 个参数，按钮显示将添加的行数，成功后选中第一个新行）。
桌面先在显示的修订上取得计划，再以同一修订提交；期间项目若被修改则丢弃计划并提示，不改到新修订重试。

critical review 中发现并处理：

- `project.apply` 一次最多 1000 条命令，而首稿只限制 1000 行，复制基准行或多参数时大扫描会在提交时才失败。
  规划器改为按命令数检查并说明每次最多可加多少行；桌面面板按相同规则（每行 1 条加每个扫描与复制的单元格）提前禁用按钮。
- 托管表虽能被普通命令写入，但扫描它们没有意义且会破坏约定结构，规划器直接拒绝，面板不显示。
- 结果只显示在页面顶部时，滚动到下方面板的用户看不到；按钮下方同时显示本次结果。
- 截图夹具首版在第一次绘制前读取区域矩形（全为 0），改为每次绘制后读取。

首版限制：文本取值不能含逗号（Python/CLI 不受限）；JSON 字段只能在 Python/CLI 用列表；不去重、不检查物理合理性。

## 2026-10-06：可用性开发包 2——启动即工作台

新的默认布局以分步引导的工作台开始：左栏为“工作台”与“任务”两个标签（工作台在前），中间查看器、右侧属性，
底部日志条由 28% 缩到 20%，使五个步骤在 1280×800 下可直接看到。已保存布局的用户不受影响，“恢复默认布局”可切换。
工作台按“项目 → 参数 → 运行环境 → 运行 → 结果”显示已知状态（已打开项目、参数表与行数、当前连接与健康、
查看器是否有结果），并标出第一个未完成步骤；后台服务未就绪时用一句话说明。按钮只导航，“选择运行环境”切到任务标签，
“查看器”不最大化以保留属性面板。工作台改用与任务/属性一致的面板底色。
默认布局变化影响了 33 项测试：按真实行为更新（需要任务编辑器的测试先切到任务标签，标签序号随新增的工作台后移），
布局导出、默认屏幕图像与任务金样均重新生成并逐项核对，只含布局与标签变化。

## 2026-10-06：可用性开发包 1——带符号标量体的显示

按独立使用者审视（[记录](design/user-review-2026-10-06.md)）启动可用性开发包，所有者确认先于工作流提案。
第 1 项修正误导性显示：`stk.render.volume@1` 新增客户端参数 `range_mode`（`data` 默认、`symmetric`），
只填充 `range` 的 `null` 端点，显式端点优先，载荷仍携带解析后的两端；规范目录与 `stk-graph-v1.md` 由生成脚本同步。
“带符号标量体”预设默认改为发散色图 `coolwarm` 并以 0 为中心（±max|v|），可选回“数据最小–最大”；
预设内容变化按锁文件规则把技能升级为 `stk.visualize.scalar_volume@2`。保存过的分析与已冻结运行保留原图，不受影响。
桌面通用表单的“自动”端点不再显示存储的占位 0，而显示屏幕上结果实际使用的值（仅当结果与当前参数一致），
否则显示“由数据决定”；新参数与取值有中英文名称。

## 2026-10-06：保存分析的单输入连线编辑首版

按开发计划交付保存分析的受限连线编辑。`AnalysisParameterDraft` 增加单输入连线修改，直接改原始 JSON 的目标输入，
未触碰的连线、别名、标签和参数类型逐字保留；多输入列表、带 `as`/额外字段的连线、重复节点 ID 结构上只读，
目录侧再限制未知类型与未声明端口。新增纯状态 `AnalysisCandidateValidation`：`graph.validate` 的回复绑定打开句柄、
分析 UUID、读取修订、草稿代次/版本与桥进程会话，只有当前候选的通过结果才放行含连线修改的保存；
保存经 `ProjectAnalyses::replace_definition` 按读取修订一次写入。只有参数/输出修改的草稿行为不变。

critical review 与测试中发现并处理：

- 节点目录尚未读取完时所有节点都显示“类型不在目录中”，提示具有误导性；改为显示“正在读取节点目录/没有目录时只读”。
- “连线”面板默认展开使侧栏变长，旧的保存分析截图夹具按坐标点击的面板标题在英文窄窗口被挤出画面（8 项失败）。
  面板改为默认收起、标题显示修改数，保存受阻原因移到草稿面板顶部；夹具点击前改为经真实滚轮把标题滚入可视区，判据不变。
- 测试自身问题：误用 `volume` 预设的节点名、文档带未声明参数导致校验失败、丢失回复用例解引用空控件指针（已改为断言）。

技能目录首版的 Windows CI 在 GitHub Actions 事件结束后重跑 717/717 通过，三平台至此全部通过。
可审查的工作流提案、多输入/增删节点与拖线仍未实现。

## 2026-10-05：技能目录首版——原生只读浏览页

在契约提交 `5a12d5a` 之后接入原生 **技能** 编辑器：**文件 → 技能**、工作台“技能库”（无需项目）或编辑器类型菜单打开。
共享 `SkillCatalogState` 读取一页（50 项）、明确搜索/重新读取/翻页，选择后读取契约详情；展示可用性、执行入口、
SKILL.md 说明包、输入/参数/输出、依赖、未检测运行能力、例子及未载入定义。旧桥缺少方法时显示不可用。
`skills.list/get` 加入客户端可在桥重启后重发的只读方法。用法见[桌面指南](desktop.md#技能目录)。

critical review 发现并修正的问题：

- 回复过滤后若同一客户端重新接回（例如暂时解除桥），旧代码丢弃当前回复却保留请求句柄，页面会永久“读取中”。
  改为丢弃其他桥的当前回复时清空目录，下一帧重新读取；还原旧代码后新回归在 30 秒超时失败，修复后通过。
- 搜索原按字节截断到 200，会切开多字节 UTF-8 字符，序列化时出错；改为按字符边界截断并加中文回归。
- 列表行文字回调原捕获单帧 `EditorContext`，改为只捕获应用存储拥有的目录与数据；中文可用性冒号与“数据绑定”已本地化。
- 首轮测试自身的两个问题：帧重建后复用旧控件指针；`Client::restart()` 只重启失败的桥，未真正重启，改用 `shutdown_bridge()`。

契约提交的 Runtime CI 在 Windows 客户端失败：测试假定三个内置技能都“可用”，但该环境没有 VTK，
目录正确报告畴结构技能为“部分可用”（`view`/`image` 不可交付）。`526608a` 改为按实际安装模块推导期望值，
并在本机模拟缺少 VTK 验证。产品行为未改。浏览页提交的 Windows CI 又暴露一处测试在帧后复用旧控件指针（Linux 偶然通过），
已改为帧后重新查找。项目引用/版本固定、从技能直接运行与附件仍未实现。

## 2026-10-05：技能目录首版——契约与查询入口

按 handoff 顺序开始“内置技能目录首版”。先分清三类内容：给模型的 SKILL.md 说明包（`suan skills list/export`，保持不变）、
可执行节点目录（`stk.catalog/1`）以及新的版本化技能（实验契约 `stk.skill/1`，见[技能目录](skills.md)）。
首批只收录三个可离线验证的图预设：`stk.visualize.scalar_volume@1`、`stk.muferro.domains@1`、`stk.muferro.energy_trace@1`，
没有把全部预设改名为技能。输入、参数和输出直接取自图模板；`content_sha256` 覆盖定义及模板，
`tests/data/skill-catalog.lock.json` 使同一版本的内容漂移在 CI 中失败。

查询入口为桥 `skills.list/get`（[协议 §16](specs/stk-desktop-bridge-v1.md#16-versioned-skill-catalog-additive-extension-experimental)）、
Python `stk.skills` 与 `suan skills catalog/show`，共用一次解析；有界分页，不执行入口、不启动图工作进程、不触及项目或模型。
坏定义逐文件列入 `problems` 而不影响其他技能；未知 ID/版本返回 `not_found` 与已知版本。

critical review 时以实际求值核对依赖声明：在子进程中屏蔽模块后，畴结构的占比统计不需要 VTK，
因此 VTK 只限定影响 `view`/`image`，而非整个技能；能量曲线需要 matplotlib，表格不需要。该核对已写成回归。
本机 PNG 输出因离屏渲染子进程 SIGSEGV 不可用，目录只声明“离屏渲染未检测”，不把它报告为可用。
项目引用、版本固定、迁移与备份尚未实现，未改数据库格式；原生浏览页为下一提交。

## 2026-10-05：围绕五类内容建立项目工作台入口

按照项目、文件、技能、工作流、对话的分类调整路线图，本轮先交付原生项目导航。
从 **文件 → 工作台** 或项目/AI/分析图页头进入，复用已有编辑器，分别定位文件、保存分析、两类运行、
对话、数据和项目管理。默认启动页、技能库、对象附件与稳定 ID 深链接仍未实现；下一步是整理内置技能契约与目录。
使用方法见[桌面指南](desktop.md#项目工作台)，目标与存储边界已同步到两个设计文档。

critical review 补齐来源编辑器、外壳及项目打开会话保护；导航保持未发送问题、有效/无效分析参数和 Viewer。
另外以失败回归证实文件入口会在存在单元格及表/字段名称草稿时切换共享选择，增加全部窗口及隐藏标签的切表保护。
用户明确应用或重新载入后才继续；不隐式应用参数、执行计算或发送模型请求。
构建、测试、失败记录及截图证据统一见[验收记录](runtime-validation.md#2026-10-05项目工作台与跨页草稿保护)。
本轮最终重点回归 **61/61**、完整 Linux CTest **1114/1114** 通过，无失败、错误或跳过；新增八张工作台截图已检查。
交接时确认 `b2e5632` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/37289712961) **5/5**、
[Runtime CI](https://github.com/sijintech/stk/actions/runs/37289713009) **7/7** 任务全部成功。
Linux 1114、macOS CPU 749 / Metal 138、Windows CPU 708 项通过，无原生跳过；真机验收范围仍单独记录。
后续开发入口统一在根目录 [handoff.md](../handoff.md)，Claude 入口为 [CLAUDE.md](../CLAUDE.md)。
旧 Linux Wayland CSD 退出故障的 CI 已记录 SIGSEGV；本机 30 次未复现，根因仍待定位，不能作为本轮已修复项。

## 2026-09-30：持续开发交接——AI 建议到可追溯的分析结果

本轮直接在 `main` 连续推进 AI 与分析工作台，未创建功能分支。M1–M17 的代码提交止于 `c6b6d14`；
本次继续补齐原生 Python 文件入口联合验收，并修复审查发现的输入映射 Tab 提交丢失问题。
当前开发方向仍以[开发计划](development-plan.md)为准，逐项测试、CI 与截图证据集中在[验收记录](runtime-validation.md)。
本轮没有新增真实模型调用，自动化测试使用隔离桥、工作进程与合成数据，不代表科研结论或双平台真机验收。

- **AI 与工作区（M1–M4）**：临时流式文字、捕获范围内的结构化标量建议、明确保存草案及检查入口；
  多行/字段上下文选择固定来源修订，保存成功才采纳；准备/分析聚焦导航保留原编辑器与草稿。
  准备、发送、保存建议、预览和应用保持独立，过期建议不自动重定基准。见[参数建议](project-parameter-edits.md)与[桌面指南](desktop.md)。
- **图与科学显示（M5–M8）**：只读节点画布与端口/参数检查，区分当前配置、已显示配置和独立保存定义；
  只有核对图哈希后才关联显示回执。新增保留正负值的标量体预设、稳定的浮点 GPU 上传映射、按视口明确取景与文字底色。
  单位标签不进行换算，导入结果不伪造原始图。见[分析图](analysis-graphs.md)与[标量体渲染](scalar-volume.md)。
- **保存分析到运行（M9–M13）**：格式 9 增加持久分析执行记录，准备冻结定义及快照映射，明确开始才执行；
  运行一次领取、取消意图、失败/不确定状态和校验归档可重开读取，不自动重跑。旧格式只经明确备份升级。
  参数与有序请求输出共用精确类型草稿，联合保存只产生一次修订/撤销；历史运行可打开独立冻结图，
  输入映射可明确复用到空准备区，再单独准备新运行。见[保存分析](project-analyses.md)与[分析运行](project-analysis-runs.md)。
- **结果检查（M14–M16）**：已校验的归档可检查全部输出、缺失交付及原始问题；类型化属性和精确标量分页保留整数、
  浮点、`null` 与字符串的区别。内联科学表格按原列序、原行身份分页，每页最多 64 行、8 列，可检查精确单元值、列名和单位。
  已补充按源坐标明确跳转与窄侧栏完整滚动，避免长表逐页翻找和底部控件不可达；M16 本机验证见下方。
  大表 blob 内容仍不加载。新增[离线分析验收示例](../examples/project_analysis/README.md)，以全新 73×10 合成 CSV 项目走通冻结、
  保存、一次明确执行和归档检查；保留已有项目/Viewer，观察超时不等于取消，重新运行会另建项目。

关键审查修正覆盖科学精度、可恢复性和界面寿命：有限双精度到浮点显示溢出明确拒绝，极端有符号范围不再与缺失值混淆；
严格 JSON 编辑拒绝重复键和整数溢出，归档按保留类型的编码核对 SHA-256，拒绝原生解析已损失精度的结果。
不确定保存只读回原身份，不重放写入；运行归档与终态之间的取消竞争在事务内再核对。
迟到回调固定项目、会话、导航和选择代次，保留活动输入与未保存草稿；分页缓存不复用同长度的旧页面身份。
另外修正 Windows 已映射文件的重复写入夹具、Future 迟到挂接的测试竞态，以及宽对象逐键扫描导致的平方级开销。
最后的联动审查通过真实键盘回归复现“绑定名 → Tab → 相对路径”丢失自定义路径；分别跟踪字段提交版本后，
旧 Add/Prepare/复用动作与结构变化后的旧字段回调仍失效，原快照、冻结运行和无效参数草稿保留。
详细原因与回归分布见验收记录，各项修正没有放宽数值、结果或来源校验。

M15 本机原生重点 **183/183**（135 项 CPU、48 项渲染）、完整 Linux CTest **1086/1086** 通过，失败/错误/跳过均为 0。
其后仅加强截图夹具，使窄窗口精确值实际滚入视口，**8/8 渲染复测通过**；没有改变生产行为。
离线示例的真实隔离内核→桥→工作进程及边界回归 **14/14 通过、无跳过**。
后续坐标定位与侧栏滚动修正（M16）最终完整 Linux CTest **1093/1093 通过、无跳过**；
新增六项交互、一项三种缩放的滚动回归，并复核 32 张图，细节见验收记录。
M15 提交 `5aed38d` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36723665636) **4/5 任务通过**：
Linux **1085/1086**，唯一失败为旧不确定保存夹具在独立 `project.changed` 到达前断言修订；
macOS CPU **730/730**、Metal **134/134**、Windows CPU **689/689** 通过，新增 **29 项 CPU** 在三平台均通过，
**12 张**新增图片逐张复查，Linux/macOS 打包及全新目录启动通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36723665667) **7/7 任务通过**：Linux Python 3.10/3.12 各
**2201 passed / 7 skipped / 4 deselected**，Windows 两版本各 **1788 passed / 61 skipped / 260 deselected**；
新增离线示例 **14 项**在四个组合均通过。证据在 `/tmp/stk-table-grid-ci-36723665636/audit-summary.json`。

上述 M16 全量验证后，仅修正旧保存测试夹具：明确暂扣变更通知，验证原修订后放行，再等待修订 1 与空闲状态；
保留一次创建、原 UUID 的一次明确读回和一条历史记录断言。畸形/丢失回复定向复测 **2/2 通过**，
日志 `/tmp/stk-analysis-handoff-focused-final.log`；同批 M17 脚本测试因面板未展开找不到按钮，属于当时尚未提交的 M17 工作，未计为通过。
该测试夹具修改后在 M16 提交前未重复完整套件；其后 `86007e3` 的
[桌面 CI](https://github.com/sijintech/stk/actions/runs/36728057610) **5/5**、
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36728057735) **7/7** 任务全部通过。
原生 Linux **1093**、macOS CPU **737** / Metal **134**、Windows CPU **696** 项均无失败、错误或跳过；
新增 7 项 CPU 和两个保存回复修复场景均在三平台通过，12 张更新图已逐张复查。
Runtime 四个 Python 组合及 14 项示例各自通过，数量与 M15 相同；M15 失败历史仍单独保留。

本次 M17 已完成全量重新编译，重点交互 **88/88**、完整 Linux CTest **1095/1095** 通过，失败/错误/跳过均为 0。
新增原生验收实际点击“运行文件”，在独立目录调用离线示例，再明确打开新项目和归档，核对 **-9.5 K** 与源坐标
**72/9 → 整数 576**；原项目、Viewer 和布局保持不变。另一个新增回归验证上述 Tab 修正与旧回调失效。
本机结果和修复前失败均见[验收记录](runtime-validation.md)；`c6b6d14` 的
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36731162900) **7/7** 任务通过，四个 Python 组合的数量与 M16 相同，
14 项离线示例均实际通过；[桌面 CI 首次执行](https://github.com/sijintech/stk/actions/runs/36731162962/attempts/1) **4/5** 任务通过。
macOS CPU **739/739** / Metal **134/134**、Windows CPU **698/698** 通过，两项新增用例在三个平台均通过，
Linux/macOS 打包、签名检查及全新目录启动/载荷/预设检查通过（macOS 为 ad-hoc 临时签名，未公证）。
Linux **1094/1095**：唯一失败的旧 `wm_app_window_weston` 打印全部检查与零内存泄漏后，缺少要求的最终 `PASS`。
日志没有记录子进程退出码，根因仍未确定；不能据此断言仅为 CI 环境问题。本机同提交定向连续 **20 次**未复现。
原始失败保留于 `/tmp/stk-final-handoff-ci/attempt1`。同提交仅重跑该 Linux 任务的
[第二次执行](https://github.com/sijintech/stk/actions/runs/36731162962/attempts/2)已通过：直接日志确认 **1095/1095**，
包含原 Weston 用例和两个新增用例，其余四个任务沿用首次成功结果。证据单独保存在 `attempt2`，
这次未复现不能作为已修复根因的依据。

收尾 critical review 发现测试包装层的独立缺口：CTest 匹配到成功文字时会忽略普通退出码，包装层又将子进程信号转为普通退出。
已补充非零退出、命名/无名信号、超时的明确 `FAIL:`，保留 0/77 状态且不自行输出 `PASS`；
Viewer GUI-open 的失败匹配同步覆盖此诊断，CI 保留 CTest 和 Weston 日志。六个真实子进程回归覆盖成功、跳过、
成功文字之后的异常退出/信号以及超时。审查另修正了超时测试对 Python 启动速度的依赖。
这项诊断改进不是上述 Weston 根因修复；本机完整 **1096/1096** 通过，最后补齐 Viewer 测试失败匹配后，
重新生成/构建并完成 **10/10** 定向复测，均无失败、错误或跳过。远端结果需单独记录，见[验收记录](runtime-validation.md)。

macOS / Windows [快速启动入口](../desktop/QUICKSTART.md)仍指向仓库内的 `setup.py`，正常运行会更新专用 Python 环境并增量编译。
测试新增功能时应重跑正常启动命令，不用跳过编译的 `--launch-only`；随后按离线分析指南从“文件 → Python”明确运行脚本。
完整 Xcode 与 Windows C++ 工具链要求不变；Windows GPU、两平台输入法/交互和真实模型按钮仍需单独真机验收。

后续优先收齐最新提交的跨平台 CI、定位上述 Weston 退出问题并收集双平台离线验收反馈；下一项功能是保存分析中已有节点单输入端口的受限连线编辑，
范围和验收已写入[开发计划](development-plan.md)，继续沿用联合草稿、明确校验、原子保存和新运行身份。
科学表格的精确排序/筛选及大表有界读取分别定义契约并单独验收。
通用 AI 工具/自主模拟、完整分层流程、跨输出比较、跨平台 STK 点对点通信以及 Markdown/HTML/PDF 嵌入仍属后续计划，
本轮没有把现有本机桥、只读图或科学表格当作这些功能已经完成。

## 2026-09-30：AI 准备工作区首版（本机及跨平台 CI 通过）

新增原生 **AI 工作区** 编辑器，可从项目页头或文件菜单打开，并返回项目表格选择数据。
单页串联明确捕获选中记录全部字段、输入问题、**准备问题（不发送）**、核对保存内容与明确发送。
复用格式 8 的上下文、消息与请求，无新表或桥方法。准备先保存消息、再创建请求；第二步失败可能留下保存的消息，
但不会发布半份问答。同次会话对当前相同输入重试复用身份，不承诺跨重启事务或身份恢复。
已保存问答可导航及刷新列表；回复按窗口宽度换行显示普通文字，不附带其他对话或未保存输入。

运行中/不确定请求只读取本地已保存状态，约 1 秒一次、最多 90 秒；终态、读错误或到期停止，
明确刷新可继续观察。读请求与取消独立，旧响应按项目句柄/选择代次隔离；没有自动发送、重试或遗留执行核对。
每个编辑器按项目保留内存中的未保存问题及模型选择，退出/关闭编辑器不保证保留，布局 JSON 不存这些文字。
宽窗口并排显示数据与对话，窄窗口使用可折叠的数据设置；默认首页/布局未切换。

独立审查发现并已修正：活动输入在项目切换后残留、普通长回复被裁切、从空输入准备需再次点击，
以及多个 AI 区域的历史选择与共享问答不一致。另固定捕获按钮的修订/字段范围，补充手动刷新记录入口。
测试另发现两项控制器缺陷：向 `ordered_json` 问答对象插入缓存字段使请求引用失效，刷新时可能崩溃，
已改为持有请求副本；SQLite 重读后的配置字段顺序不同导致相同准备重试被拒绝，已改为规范化语义比较。
修正后，控制器、原生 AI 交互、宽/窄截图与 App 重点测试 **41/41 通过、无跳过**。
最终 Linux 完整 CTest **602/602 通过，失败/错误/跳过均为 0**；八张 AI 中英文宽/窄 GL/Vulkan 截图已检查，
中英文字典各 **1072 项**一致、无重复。新增编辑器名称使下拉框变宽，首轮 10 份旧布局基准不匹配；
独立结构比较确认更新只涉及页头控件横坐标/宽度，区域、分隔条和正文未变，再运行完整套件通过。
代码提交 `852b343` 的 [桌面 CI](https://github.com/sijintech/stk/actions/runs/36667294145) **5/5 任务通过**：
Linux **602/602**、macOS CPU **369/369** 与 Metal **73/73**、Windows MSVC CPU **329/329**，均无失败、错误或跳过。
Linux/macOS 安装包及启动检查通过；八项 Linux 和四项 Metal AI 宽/窄中英文渲染实际执行，截图已复核。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36667294040) **7/7 任务通过**：Linux Python 3.10/3.12 各
1665 通过、7 跳过；Windows Python 3.10/3.12 各 1254 通过、59 跳过，范围与排除项见[验收记录](runtime-validation.md)。
此轮未调用真实模型；此前 Linux 单次账号验证与双平台真实账户待验收范围保持不变。
日志 `/tmp/stk-ai-full-final.log`，JUnit `/tmp/stk-ai-full-final.xml`；范围见[验收记录](runtime-validation.md)。
CI 证据在 `/tmp/stk-ai-ci-36667294145/`，Windows 日志 `/tmp/stk-ai-windows-36667294145.log`。

后续依次补齐真机使用反馈、流式显示和通过检查/应用流程的结构化修改提案；工具执行、自动模拟流程与
完整 AI 主页仍属后续计划。用法见[桌面指南](desktop.md#ai-助手)，验收见[工作台清单](workbench-acceptance.md#ai-助手)。

## 2026-09-30：Token Plan 本机配置与首次真实文字请求

用户已在本机 `~/.bashrc` 中导出 `STK_TOKEN_PLAN_API_KEY`，并授权选择默认模型。
本轮添加 `STK_TOKEN_PLAN_MODEL=qwen3.7-plus`；通过新交互式 Bash 启动的桥可读取配置，
检查仅输出配置存在状态和模型名，没有输出密钥。非交互式进程原先未继承该变量，
[请求指南](project-requests.md)已补充启动文件、重开终端和应用环境继承的区别。

在 Linux 使用真实 `ProcessBridge` 子进程和 NDJSON 协议，以隔离项目/状态/缓存目录运行一次明确发送。
仅捕获人工构造的单个 `temperature = 300 K` 单元格，请求模型按“数值 单位”回答，
输出预算 128 token、不启用思考、无工具。`qwen3.7-plus` 返回 **`300 K`**，请求状态为 **completed**，
提供方报告输入 **668 token**、输出 **4 token**；只发送一次，没有重试或使用实际研究项目。

验证助手消息与源上下文关联、文字 SHA-256、单个请求/两条消息、参数快照与修改历史未变，
无额外 `project.changed` 事件或协议校验错误。桥正常退出后重新打开 SQLite，读取到相同完整请求和回复。
密钥未出现在请求、助手消息或桥协议输出中。临时证据目录 `/tmp/stk-token-plan-live-ic7pfdi7`，
结果 `report.json`，请求 ID `e94ae822-c756-4d10-a274-cc2cabf6431e`。

这验证了当前 Linux 桥到提供方再到项目存储的单次文字链路；不代表科研回答质量、多轮对话、
全部模型或 macOS/Windows 原生按钮的真实账户验收，也不代表服务方确认本应用的套餐适用性。
本轮仅修改本机 shell 配置及文档，生产代码沿用 `2ba950b` 的跨平台 CI 基线。

## 2026-09-30：阿里 Token Plan 文字请求接入

按用户指定端点接入 `aliyun-token-plan/1`，固定 HTTPS Chat Completions、非流式文字与不启用思考模式。
本机从 `STK_TOKEN_PLAN_API_KEY` 读取专属凭据，可用 `STK_TOKEN_PLAN_MODEL` 设置默认模型；
不读取 OpenAI/通用百炼密钥，不将凭据、认证头或错误正文写入项目。模型 ID 在原生界面仍可明确填写。

桥和 Python 增加 `project.requests.provider/start/recover`，原生请求页增加准备、明确发送和遗留执行核对。
准备只固定已保存的用户消息和上下文；预检在领取发送权前完成，配置失败保持尚未发送。
发送只发生一次，无重定向、自动重试或工具调用；完整回复才可原子发布，截断/工具回复拒绝，未知传输结果保留不确定。
本轮沿用格式 8，没有新表或新事件。关闭项目的已启动请求继续绑定原库；桥关闭立即隔离迟到回复，
后台尽力写入不确定状态。独立审查发现的 worker 早于关闭线程退出的竞态已修正并加入确定顺序回归。

本机完整桌面 **584/584、无跳过**，请求/讨论与截图重点 **14/14**。Python 主回归 **500/500**，
随后补充真实注册适配器从 HTTP 编解码经桥到 SQLite 的 **4 项**集成，所在文件 **10/10** 通过。
适配器 **74 项**覆盖固定端点/认证隔离、完整/非法/截断回复、状态分类、超时与取消；使用内存 socket，
没有外部网络或套餐调用。字典各 **1039 项**一致，中文 Vulkan 请求页已查看，修改文档 **134 个本地链接**有效。
代码提交 `2ba950b` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36613518011) **7/7 任务通过**：
Windows Python 3.10/3.12 各 **1254 passed、59 skipped、260 deselected**；
Linux Python 3.10/3.12 各 **1665 passed、7 skipped、4 deselected**，打包及 graph doctor 均通过。
四组 Python 环境都完整运行 **74 项适配器、27 项执行器、10 项桥模型请求**测试，相关用例无跳过。
Windows 跳过平台/可选依赖/性能/许可场景；Linux 跳过 2 项性能、2 项可选 MCP 和 3 项许可求解器场景。

对应[桌面 CI](https://github.com/sijintech/stk/actions/runs/36613517994) **5/5 任务通过**：
Linux **584/584**、macOS arm64 CPU **359/359** 与 Metal **69/69**、Windows MSVC CPU **319/319**，均无跳过。
Linux/macOS 可搬移安装包及干净环境启动检查通过；中文 Metal 请求页截图已下载查看，布局和文字显示正常。
Windows GPU、真实账户模型调用和套餐适用性不在本次自动化验收范围内；没有使用真实账户进行模型验收。

使用及双平台环境设置见[请求指南](project-requests.md)，真机步骤见[工作台验收](workbench-acceptance.md)。
阿里官方对 Token Plan 工具用途有限制；技术协议适配不等于服务方已确认 STK 的套餐适用性。
流式回复、远端查询、工具提案与完整 AI 主页继续按[开发计划](development-plan.md)推进。
日志 `/tmp/stk-aliyun-python-all.log`、`/tmp/stk-aliyun-wire-bridge.log`、`/tmp/stk-aliyun-native.log`、
`/tmp/stk-aliyun-full.log`，JUnit `/tmp/stk-aliyun-full.xml`。

## 2026-09-30：请求记录与本地执行生命周期

格式 8 增加 `project_requests`，引用明确保存的上下文和用户消息，固定配置、输入摘要与助手消息身份。
创建、查询、取消和重开不发送请求，不修改参数修订或撤销历史。完成标记与助手消息在同一事务内保存；
旧项目按格式 1–7 → 8 显式备份升级，原数据及历史保留，打开不迁移。

本地 `RequestExecutor` 由可信调用方注入适配器，发送前取得系统锁并持久领取唯一执行权；
重复开始、两个进程、取消竞争、进程退出和关闭后的迟到回复都有回归覆盖。未知网络结果、丢失执行器或
本地保存失败保留不确定状态，不自动重发。当前没有内置提供方、凭据读取、真实模型调用、流式显示或工具提案。

桥和 Python facade 增加 `project.requests.create/get/list/cancel`；原生 **讨论 → 请求** 支持列表、
刷新、取消和查看原消息/已保存回复，刷新详情同步列表状态。旧按钮和迟到回调仍固定原项目句柄及请求 ID。
接口与存储统一拒绝配置标识中的 `//`，不接受认证字段或任意提供方参数；模型/适配器名称不会动态导入模块。

最终本机项目/请求/桥/脚本 Python **416/416**；另运行脚本与 MuFerro/批次工作流 **32 通过、2 跳过**，
两个跳过项需要显式启用真实许可求解器，本轮没有改变求解器或重新进行物理结果验收。
存储/讨论/执行器重点 **100/100**；最终完整桌面 **582/582、无跳过**，包含三项新增原生集成与
四项中英文 GL/Vulkan 请求页渲染。中文 Vulkan 请求页已查看，字典各 **1028 项**一致。
Linux/macOS CI 已将请求页列入十八类工作台截图必跑检查。
`f493224` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36595784259) **5/5 jobs 全通过**，覆盖 macOS Metal、
Linux GL/Vulkan、Windows 编译/CPU/真实桥、Linux 打包与干净环境启动；Windows CI 不包含 GPU 真机渲染。
macOS artifact 确认 **357 项 CPU、69 项 Metal 全通过且无跳过**，
三项请求原生测试及中英文请求截图全部实际执行，中文 Metal 图像已查看。

首轮 Windows Python 测试暴露 pytest 自动生成的超长用例 ID 超过 Windows 环境变量限制。
`bc3edf8` 只为两组参数化用例指定简短名称，保留全部超长输入及断言，聚焦 **18/18** 通过。
其 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36596541216) **7/7 jobs 全通过**；Windows Python 3.10/3.12 各
**1166 通过、59 按环境跳过、260 按标记排除**，两版均实际执行全部 **23 项请求执行器测试**，包含跨进程锁与进程退出恢复。
该测试命名修正不触发桌面工作流，桌面生产代码验证继续对应 `f493224`。

日志 `/tmp/stk-requests-python-final.log`、`/tmp/stk-requests-python-remaining.log`、
`/tmp/stk-request-storage-executor.log`、`/tmp/stk-requests-full.log`，JUnit `/tmp/stk-requests-full.xml`。
使用见[请求指南](project-requests.md)，双平台步骤见[工作台验收](workbench-acceptance.md)。
下一包接单一真实提供方的显式文字请求与结果核对，工具提案随后复用现有草案检查/应用接口。

## 2026-09-29：Python 共享选择与输入保护

新增 `p.selection()` / `p.select(table_id, record_id, expected_revision=...)`，通过两项可协商的本机
反向 UI 操作读取/改变共享表格与记录选择。固定项目句柄、已载入修订和规范 UUID；先校验完整归属再切换，
无效请求不部分改变选择。读取不刷新数据库；后续上下文捕获/编辑仍通过数据库修订检查。
选择不改变布局、焦点、修订、修改历史或已保存草案，任何窗口正在输入文字时拒绝写入选择。
同项目跨表切换保留每个编辑器的独立查询，缓存随目标表重新建立；删除最后一张表后清除残留记录 ID。

真实 Python worker 与原生界面新增 **5 项**集成测试，覆盖空项目、精确选中行的上下文捕获、
错误参数/归属/修订、输入保护、跨表筛选、删除对象，以及排队期间修改修订或切换项目。
相关原生 **13/13**、Python **65/65**，最终完整桌面 **575/575、无跳过**；字典各 **1011 项**一致。
旧六项 UI 能力继续可用；取消/超时后丢弃迟到回复，不重放请求。此包不新增 SQLite 格式。
`00c991c` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36574786525) 全部通过，包含 Windows Python 3.10/3.12。
[desktop CI](https://github.com/sijintech/stk/actions/runs/36574786487) 全部通过，包括 macOS Metal、Linux GL/Vulkan、
Windows 编译/CPU/真实桥、安装包与干净环境启动。Windows CI 不包含 GPU 真机渲染。
macOS artifact 确认 **354 项 CPU、67 项 Metal 全通过且无跳过**，新增五项共享选择测试全部实际执行。

日志 `/tmp/stk-selection-native.log`、`/tmp/stk-selection-python.log`、`/tmp/stk-selection-full.log`，
JUnit `/tmp/stk-selection-full.xml`。用法见[Python 指南](scripting.md#查询和改变原生共享选择)，
双平台手工检查见[工作台验收清单](workbench-acceptance.md)。

下一阶段的[模型请求设计](design/review-drafts-and-conversations.md#后续模型集成)已细化为本地生命周期、
单提供方文字响应、普通编辑提案三包，明确未发送与结果不确定、取消竞争和重启核对。
这些仍是设计，未新增模型调用或请求数据库格式。

## 2026-09-29：表格搜索与捕获单元格预览

普通项目表格增加视图内文字搜索、只显示含错误记录、匹配数量及清除筛选。
各区域分别保存查询，排序/点击/编辑映射回原记录 UUID；隐藏选中记录时保留共享选择，
该区域不能直接修改或删除隐藏行。旧按钮还检查输入框刚提交的查询，避免失焦与重绘之间操作旧目标。
数值排序保持完整整数精度；筛选不改变项目修订、运行/批次范围或 CSV 导出范围。

讨论页增加只读捕获单元格表与原始单元格详情。字面量、空值、未设置、求值错误、缓存不可用、
省略和缺失对象分别显示；数据来源只使用保存的上下文，实时修改或删除字段不改变历史展示。
JSON 摘要按 UTF-8 字节和深度限量生成，不序列化看不到的数组尾部；普通表格按需缓存最多 4096 个摘要。

本机新增纯辅助测试 **9 项**、原生集成 **3 项**；重点与讨论/筛选渲染 **15/15**，
完整桌面 **570/570、无跳过**。覆盖筛选后排序/编辑、等行数查询切换、隐藏选择与迟到按钮、
两个区域独立查询及冻结值在实时编辑/删除后不变；中文 Vulkan 筛选和英文 GL 捕获表截图已查看。
字典各 **1011 项**一致。此包没有 Python、存储格式或桥协议变更。
`8bc4016` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36573460344) 已完成 macOS Metal、
Linux 打包和干净环境启动；Linux/Windows 编译被后继 `00c991c` 推送取消，其代码已由后继提交的完整 CI 覆盖。
已下载 macOS artifact，确认 **349 项 CPU、67 项 Metal 全通过且无跳过**，中文筛选及英文捕获单元格截图已查看。
该提交的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36573460403) 全部通过。

日志 `/tmp/stk-table-views-native.log`、`/tmp/stk-table-views-full.log`，JUnit `/tmp/stk-table-views-full.xml`。
使用见[项目指南](project.md)与[上下文指南](project-contexts.md)。下一步补 Python 的共享选择读写接口。

## 2026-09-29：显式上下文、手工讨论与草案来源

项目格式 7 增加独立上下文、消息和提案来源表。捕获固定项目 UUID、来源修订及明确选择的表/行/字段，
保留类型、单位、字面量、公式和已有求值结果；缺失、超限和不可用缓存均有明确诊断。
只读取选定内容，不读取外部文件或重新求值其他表；每项 16 KiB、完整上下文 256 KiB，
超限保存大小/校验和及省略原因。相同调用者 UUID 的重试返回原记录；格式升级前备份校验。

手工或导入消息保存文字，提案关联已保存草案及同修订上下文；不执行代码或应用修改。
来源链读取验证消息、上下文和草案一致性，保留合法终态变化与撤销后的历史。
原生“讨论”页增加捕获范围、分页查询、详情、消息填写、关联草案及回到检查页；
检查页显示来源并支持刷新。异步回调固定项目句柄，旧按钮核对所显示对象，不覆盖新输入；
重开和桥重启只恢复查询能力，不重发请求或恢复执行。
Python `p.contexts`、`p.discussion` 与八个可发现桥方法共享同一存储。

本机项目/桥/脚本/工作流 Python 回归 **300 通过、2 跳过**（两个真实许可求解器测试未显式启用）；
草案/上下文/讨论存储重点 **86/86**，桥及真实脚本 worker **32/32**。
原生专项与新增截图 **9/9**；完整桌面 **554/554、无跳过**。
覆盖原子写入、并发幂等、来源损坏、格式 6 迁移备份、旧上下文不变、消息代码不执行、
项目切换/桥重启、来源关联与撤销、旧回调不能改绑、原生按钮和未保存输入保护。
中英文 GL/Vulkan 讨论页四项通过，中文 Vulkan 和英文 GL 图像已查看；字典各 **988 项**一致。
本轮修改文档的 **174 个本地链接**有效，Linux/macOS CI 已增加讨论页截图必跑检查。
`b796b90` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36570155199) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36570155222) 全部通过，包括 macOS Metal、Linux GL/Vulkan、
Windows 编译/CPU、安装包及干净环境启动；文档部署也已成功。

日志 `/tmp/stk-contexts-python-all.log`、`/tmp/stk-contexts-native.log`、`/tmp/stk-contexts-full.log`，
JUnit `/tmp/stk-contexts-full.xml`。

使用与边界见[上下文与讨论指南](project-contexts.md)。当前没有模型生成、Markdown 渲染或文件附件；
下一包完善上下文的表格化检查、普通项目表格的搜索/错误筛选，再设计模型请求和工具调用生命周期。

## 2026-09-29：持久草案、重开恢复与原子应用回执

项目格式 6 增加独立 `project_drafts`：显式保存已校验的稳定命令、原始修订、名称和终态回执。
保存/丢弃不改变参数修订或撤销栈；应用命令与已应用状态在一个 SQLite 事务中提交。
同一草案 ID 的保存可恢复相同原始请求，重复应用返回原回执；撤销参数不会使旧草案再次执行。
旧格式须明确升级，迁移前备份并校验；打开项目不自动升级。

原生“修改检查”增加“已保存草案”面板，支持保存、分页、载入、丢弃与应用状态查询。
载入只恢复命令，需重新计算并检查；过期草案须明确另起新草案，保留原记录。
新输入、清除、项目切换和桥重启使旧回调失效；失败消息保留到用户后续操作，外部修订冲突会刷新项目。
Python `p.drafts` 和五个可发现桥方法共用这一存储，不准备或提交任务。

本机项目/桥/工作流 Python 回归 **248 通过、2 跳过**（两个许可求解器测试未显式启用）；
含新增 **34** 项存储草案测试。原生重点与新增截图 **11/11**；完整桌面 **546/546、无跳过**。
覆盖迁移备份、原子回滚、并发/不确定响应恢复、关闭重开、重启、稳定 UUID、过期草案、撤销后不重放、
迟到回调和原生按钮。中英文 GL/Vulkan 草案面板通过，中文 Vulkan/英文 GL 截图已查看；字典各 **947 项**一致。
`f1001cf` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36565773604) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36565773668) 全部通过，包含 Linux GL/Vulkan、
macOS Metal、Windows 编译/CPU、安装包和干净环境启动；草案截图已纳入跨平台必跑检查。

日志 `/tmp/stk-saved-drafts-python-all.log`、`/tmp/stk-saved-drafts-native.log`、`/tmp/stk-saved-drafts-full.log`，
JUnit `/tmp/stk-saved-drafts-full.xml`。用法见[草案指南](project-drafts.md)。
下一包按[对话上下文设计](design/review-drafts-and-conversations.md)接显式上下文捕获、消息与提案关联；
当前没有模型接入、聊天页面或持久对话，不把这些设计提案描述为已实现能力。

## 2026-09-29：Python 发起原生修改检查

新增 `stk.project.review(commands, expected_revision=...)` 和可协商的本地 `project.review` UI 操作。
脚本绑定项目句柄及基础修订，原生主线程重新计算候选并打开“修改检查”；返回接受状态，
计算结果或语义错误随后在界面显示。用户点击应用后才保存，复用稳定命令、普通事务与撤销。
已有草案、错误、候选和未结束的文本输入均受保护，不会被脚本覆盖；排队后的项目切换、过期修订、
清除草案和桥断开保留现有失效规则。没有自动应用、任务准备/提交或持久草案。

本机相关 Python **69/69**；原生重点测试 **13/13**；完整桌面 **537/537、无跳过**。
新增 6 项真实 worker → UI 集成测试，覆盖差异/应用/撤销、快捷键发起并添加页签、未提交输入保护、
范围/类型/UTF-8 大小限制、旧修订与已有草案拒绝、排队期间切换项目、丢弃迟到预览及桥分离。
共享能力 schema 上限同步为 19；旧能力缺失与未附加桌面返回明确错误。中英文字典各 **923 项**一致，
检查了本轮生成的中文 Vulkan 检查页截图，80 个文档本地链接有效。

日志 `/tmp/stk-python-review-python-all.log`、`/tmp/stk-python-review-native.log`、
`/tmp/stk-python-review-full.log`；JUnit `/tmp/stk-python-review-full.xml`。
`fa324d6` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36562716767) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36562716768) 全部成功，包含 Linux GL/Vulkan、macOS Metal、
Windows 编译/CPU 测试、安装包/干净环境启动与双版本 Windows Python。
用法见[预览指南](project-preview.md)。下一步设计对话上下文、持久草案和重开恢复记录，再接模型生成。

## 2026-09-29：参数表驱动的仿真批次

新增版本化模板注册和 `stk.batches`；首个模板为 `muferro/1`。普通项目表格保存内容确定的批次 ID、
明确的案例范围、冻结参数/选项和逐行操作结果，复用已有不可变运行记录、传输和 Runtime 调度。
原生“仿真批次”支持复制参数值、增减选择、全部/单行准备、提交、刷新、取消、收集及进入运行详情。
准备与提交分开；部分失败继续处理其他成员，中断停止后续成员，重试恢复原方案/任务。
重算失败或取消任务时显式增加 Attempt、只为指定行创建新批次，保留旧记录。

相关 Python **29 通过、2 跳过**（两项真实求解器测试需显式启用）；实际 Release MuFerro 批次另行
**1 项通过**，298 K / 310 K 能量分别为 **−727.9144455 / −691.5580935**，重复提交仍为两个任务。
测试覆盖部分准备失败、重开、重复操作、取消后单行重算、准备/提交/进度写入响应丢失、中断恢复、
过期修订、批次范围篡改与伪造运行标签不能改变执行命令。最终参数校验补充 **1/1** 通过。
最终本机桌面 **531/531、无跳过**，含原生三行完整批次和四张中英文 GL/Vulkan 批次截图；截图已检查。
字典各 **923 项**一致。`a598c2c` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36450940425)
和 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36450940464) 均全部通过，
包含 Linux GL/Vulkan、macOS Metal、Windows 编译/CPU 测试、安装包/干净环境启动及双版本 Windows Python；文档部署也通过。

日志 `/tmp/stk-batch-python-all.log`、`/tmp/stk-batch-full.log`、JUnit `/tmp/stk-batch-full.xml`；
真实批次 `/tmp/stk-batch-real.log`，证据 `/tmp/stk-batch-real-HRg9Kh/test_real_muferro_temperature_0/batch-evidence.json`。
使用、恢复步骤和边界见[批次指南](simulation-batches.md)。模板目前只注册 MuFerro；批量参数生成器、
更多求解器/模板、可视化模板编辑和工具包迁移仍待后续。下一包按主计划接 Python 发起原生修改检查。

## 2026-09-28：完整真实仿真验收收尾

`763eb0b` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36444060112) 全部成功，
包括 Linux GL/Vulkan、macOS Metal、Windows 编译/CPU 测试、安装包和干净环境启动；
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36444060140)、文档部署和 Secret scan 全部通过。
下载产物核对 Linux **526/526**、macOS **322 项 CPU / 59 项 Metal**，均无跳过；
Linux 完整仿真按钮测试确实执行，中英文 macOS 仿真面板及离线三维截图已检查。
Python wheel 内的工作流与脚本入口和当前源码逐字节一致。

最终复核重新运行真实 Release MuFerro 两个温度案例，并把数据保存到独立临时目录，避免被后续默认 pytest 清理。
各次 36 个文件哈希、30 个场文件的全部数值、冻结输入与持久运行状态通过检查，三维输出再次渲染并查看。
完整目标的逐项证据见[验收记录](runtime-validation.md#完整仿真目标逐项复核)，
使用步骤见[MuFerro 工作流指南](simulation-muferro.md)。单次完整仿真闭环已验收；下一包为参数表驱动的批量计算。
Windows GPU、真机输入法和实际 macOS/Windows 到远端的 SSH 链路仍保留为独立平台验收项。

## 2026-09-28：真实 MuFerro 项目流程首版

功能提交 `7d96151` 已推送。其 Runtime CI 的 Windows 3.12 导入测试失败：新增文件复制逻辑
再次遇到句柄 `fstat` 与路径 `stat` 的 ctime 语义差异；现按 `project.snapshots` 既有规则修正，
ctime 仅在同一 API 内比较，跨 API 仍检查文件身份、大小与 mtime。新增模拟两种时间语义的回归，
同时确认真实句柄变化仍被拒绝。本机工作流 **12 通过、1 跳过**；修正提交 `ef25286` 的
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36442800913) 全部通过，包含 Windows Python 3.10/3.12。

新增 `suan/workflows/muferro.py` 与桌面 Python 的 `stk.muferro`；原生项目面板增加 MuFerro 入口，
复用同一流程执行案例导入、选行准备、日志、收集校验和三维打开。参数行引用不可变源输入；
准备期间检查项目修订和生成输入哈希，相同参数/资源/尝试次数重用方案，提交仍由已有运行面板明确发起。
结果以稳定运行 ID 写入普通项目表格，重复收集保留一行；过期方案和历史结果不覆盖。

当前已验证：真实桥/Runtime 的工作流与相关回归 **32 项通过**，1 项真实求解器测试默认跳过、另行显式运行；
真实 Release MuFerro 完成 16³、101 步、单 rank/单线程案例，298 K 总能量 **−727.9144455** 与参考一致，
310 K 为 **−691.5580935**。独立读取各次 30 个场的全部数值，检查有限值、网格与分量索引；
关闭重开、重复收集、变更参数后的独立运行通过。两次输出已由当前原生 Viewer 渲染并检查图片。
本机完整桌面 **525/525** 通过，新增原生导入/项目身份保护及 4 项中英文 GL/Vulkan 截图已检查。
日志与限制见[验收记录](runtime-validation.md)，操作步骤见[MuFerro 工作流指南](simulation-muferro.md)。

原生完整链路补充：`SimulationPython.NativeMuFerroButtonsPrepareSubmitCollectViewAndReopenOffline`
驱动实际项目面板完成导入、重复准备、提交、日志、重复收集；断开测试 Runtime 后关闭重开项目，
通过原生按钮加载已收集的三维载荷。默认假 SDK 测试通过，同一个测试显式使用实际 Release MuFerro 也通过，
结果表参考能量一致。Linux CI 增加该项必跑检查；运行器只启动、取消和清理自己创建的测试 Runtime/任务。
日志 `/tmp/stk-muferro-native-real.log`、JUnit `/tmp/stk-muferro-native-real.xml`。

最终本机完整桌面 **526/526、无跳过**，日志 `/tmp/stk-muferro-native-full.log`、
JUnit `/tmp/stk-muferro-native-full.xml`。最终跨平台 CI 状态见上方收尾记录；
原生自动化测试不等同于全部真机输入设备交互验收。

## 2026-09-28：优先贯通完整真实仿真

当前目标为“在 STK 中完成一个完整的仿真计算”，据此调整[主计划](development-plan.md)：
先完成单次 MuFerro 的项目工作流，再做通用批次和 AI 工作区，后续推进共享富内容表格、分层节点与报告。
验收覆盖输入导入/生成、冻结参数、明确提交、日志、校验并收集结果、三维检查、关闭重开和独立重算记录。

现有温度扫描使用合成场；真实 MuFerro 已有单次运行及后处理证据，但不能据此宣称新的完整项目流程已经交付。
本批只更新计划与设计状态，没有新增运行时能力。Python API、双平台客户端回归贯穿开发；
跨平台点对点通信与文档预览继续独立验收。以下历史记录中的“下一包”以本次主计划为准。

## 2026-09-28：原生修改检查

按后续计划继续直接在 `main` 开发。原生项目编辑器已增加“表格 / 修改检查”视图，
可以由单元格编辑器发起值、引用或公式预览，也可输入普通 JSON 编辑命令。
候选差异按稳定 ID 对比表格、字段、记录和单元格，包含依赖计算值、级联删除和完整定义；
错误页列出所有候选公式错误，包括原有错误，不把重新计算的修订戳当作值变化。
明确应用复用普通修订检查和撤销；输入改变、项目切换/关闭及桥重启会废弃旧候选。
外部无事件写入由最终数据库修订检查拒绝，应用尝试不自动重试。

本机完整桌面 **520/520** 通过，无跳过；新增 8 项模型/真实桥/原生交互回归和 8 项 GL/Vulkan 中英文截图。
测试覆盖稳定 ID 应用/撤销、依赖值、旧错误、级联删除、未设置/null/int64、过期及待返回候选、
关闭/重启、外部并发、旧按钮不能应用后来的新候选，以及文本尚未失焦时直接点击应用。
已检查差异/错误页和原有离线工作台截图。
中英文字典各 **878 项** 一致。最终日志：`/tmp/stk-review-binding-build.log`、
`/tmp/stk-review-binding-full.log`、`/tmp/stk-review-binding-full.xml`。
功能提交 `1905df7` 已推送 `main`；[desktop CI](https://github.com/sijintech/stk/actions/runs/36431384632)
的 Linux GL/Vulkan、macOS Metal、Windows 编译/CPU 测试及两项 Linux 打包/干净环境检查全部通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36431384638)和文档部署成功。
下载本次 macOS artifact 确认 **321 项 CPU、57 项 Metal** 无跳过通过，已查看修改检查、公式错误和离线工作台截图；
保存在 `/tmp/stk-macos-review-1905df7`。Windows CI 只覆盖 CPU/桥，不包含 Windows GPU 真机验收。

使用步骤见[预览指南](project-preview.md#原生修改检查)和[真机验收清单](workbench-acceptance.md)。
草案仅在当前项目会话共享，尚未接 AI 模型、持久化或 Python → 原生检查页入口。
下一包补脚本发起检查，再推进持久草案/对话和通用批次模板，见[开发计划](development-plan.md)。

## 前一轮连续开发收尾

本轮连续开发收尾：功能代码已直接提交并推送 `main`。最后功能提交 `c3fa59c` 的
[desktop CI](https://github.com/sijintech/stk/actions/runs/36416998477)全平台成功，Runtime 与文档部署成功；
本机完整桌面 **504/504**。最终 macOS 的 **313 项 CPU、53 项 Metal** 无跳过通过，已检查三行完整显示的截图。
后续文档 `d01bf76` 的 Runtime 和文档部署也成功。仅保留原有主工作树，未创建新分支或合并无关 PR。
从[工作台验收清单](workbench-acceptance.md)开始测试；下一包以[开发计划](development-plan.md)中的
草案检查/AI 工作区为先，图形节点、文档预览及通用跨平台对等通信仍未交付。

## 2026-09-28：连续开发

按所有者要求直接在 `main` 分批开发、验证、提交和推送。功能状态以
[开发计划](development-plan.md)、[项目指南](project.md)和[验收记录](runtime-validation.md)为准。

### 已完成开发包

- CSV/TSV 表格交换：CLI、Python、桥和原生面板按明确列类型创建新表，复用原子修订与撤销；
  导出一致修订的计算值、拒绝公式错误，以 UTF-8 BOM 写入新文件并拒绝覆盖已有目标。
  完整桌面 **489/489**、相关 Python **113/113** 通过；包含类型/编码/批次上限、并发冲突、
  输出目标竞争、公式错误、原生导入导出及一次撤销。4 项 GL/Vulkan 中英文截图已检查，字典各 **846 项**。
  CSV 是值交换，不含公式/ID/单位，首版导入仍受 1000 条原子命令上限，见 CSV 指南。

- Python 分析图操作：`stk.graph` 查询节点/预设、校验 JSON 图、显式求值/取消、定位结果 blob、
  读取色图和原始场探针；保留 Hub 审核和完整结果，不自动重试。中断取消本次本机图，
  排队中断不影响其他求值；Hub 中断只停止等待，同一 ID 可恢复原操作。
  Python 图服务/控制台/真实 Hub 节点回归 **65/65**、原生图/Viewer/脚本子集 **53/53** 通过。
  真实 worker 验证自定义图、表格、blob 哈希和原场数值；图形 Node Editor 仍待开发。

- 最近项目首版：桥状态目录原子保存最近 20 个位置，原生共享表格和 Python 提供重开/移除入口；
  列表只读取历史元数据，打开校验 UUID，移除不删除文件或关闭会话，历史损坏/不可写不阻止创建项目。
  完整桌面 **484/484**、相关 Python **52/52** 通过；包含桥进程重启、原生按钮、身份替换保护，
  4 项中英文 GL/Vulkan 截图已检查，字典各 **833 项**。本批远端 CI 待跟踪。

- Python Viewer 操作首版（`616bf3f`）：`stk.viewer` 控制本机共享三维视图的打开、预设/参数、图层、时间步、播放、
  求值/取消和相机重置；通过原生主线程执行，校验整组参数并支持来源保护，轮询等待不自动取消。
  UI 能力按桥目录协商；关闭自动求值现在也暂停已排队的参数编辑。扫描示例新增 `show.py`。
  完整桌面 **478/478** 通过，能力协商调整后相关 **44/44**；Python 相关 **23/23**。
  包含真实 Python → 原生 Viewer 的载荷/时间序列操作和合成 VTK 图求值；本批远端 CI 待跟踪。

- 手动温度扫描示例：桌面 Python 文件创建参数表、冻结并上传程序/输入、保存运行方案；运行面板显式提交，
  收集脚本下载 VTK/PNG/JSON 并更新稳定 ID 的结果表。仅依赖服务端标准库，使用明确标注的合成场。
  两次收集不新增任务/结果行，本地结果被修改时拒绝纳入汇总；真实 Runtime 与独立 VTK reader 已验证。
  示例/运行记录/Python Runtime 相关 **19/19** 通过。

- 原生运行面板：同一表格组件显示分页摘要，查看冻结参数/输入；明确提交/恢复、刷新和取消，
  过期方案必须显式选择旧参数；关闭/切换清空缓存，状态事件仅在观察记录改变时发布。
  完整桌面 **474/474** 通过，含真实桥的原生按钮 + 跨平台 HTTP 协议模拟、关闭重开和参数变更保护；
  四项 GL/Vulkan 中英文运行面板截图已检查，字典 **829/829**；相关 Python **20/20**。
  这是客户端交互验收；真实程序执行由 Linux Runtime 集成覆盖，真机 macOS/Windows 交互仍需后续验证。

- 格式 5 运行记录后端：冻结参数行、输入清单、完整 TaskSpec、连接目标指纹和固定幂等键；
  显式准备/提交/刷新/取消，任务状态不修改表格修订；响应丢失可恢复同一次提交，保留 Hub 审核。
  Python 控制台可调用 `stk.project.runs`；运行列表分页，原生运行面板由紧接着的开发包提供。
  相关 Python **144/144**，最后 Hub 刷新调整后运行专项 **10/10**；完整桌面 **468/468** 通过。

- `b1e2724`：本机项目桥接与 C++ 客户端；项目会话、快照、事务修改、历史、修订通知，
  以及关闭/重启/文件替换边界。72 项 Python 测试通过，跨平台桌面 CI 通过。
- `c537d55`：原生项目表格首版：文件菜单入口、项目创建/打开/关闭、共享选择、类型化字段和单元格编辑，
  保留旧修订草稿，桥重启后重新读取。31 项最终相关 CTest 通过，包含中英文 Vulkan/OpenGL 实际截图。
- 文档站构建修复：使用 Node 22.23.3、pnpm 8.15.9 和现有锁文件，去掉无效的空包自引用，
  排除生成目录的类型检查、标明非内容辅助文件。隔离目录重复构建通过，0 项类型错误/警告，
  36 个静态页面，Pagefind 索引 35 页/两种语言；CI 增加搜索文件检查。
  `3daa422` 已成功部署（run 36378576452）。
- CI 回归修正：项目编辑器英文短标签改为 `Project`，避免撑宽其他区域的编辑器选择框。
  本机全量重编译后的完整桌面 CTest 427/427 通过，无跳过；修正后的跨平台 CI 待验证。
- 传输恢复竞态：终态事件发出后、旧 worker 释放锁之前的立即恢复，现在等待旧 worker 收尾，
  再重新检查日志并启动一次新尝试；超时返回可重试 `busy`，不再静默返回失败状态。
  确定性时序测试及 hub/Runtime 桥回归共 23 项通过。
- Python 后端首版：独立持久 worker、项目 facade、显式执行/中断、输出环与可发现的反向桌面请求。
  共用图 worker 的进程管道/清理实现；52 项 Python 回归与 13 项相关 C++ 契约测试通过。
  原生 Python 编辑器和 UI 主线程执行器为紧接着的开发包，尚未在此批提供按钮入口。
- 原生 Python 面板：文件菜单入口、多行/粘贴/IME 输入、运行/中断/重置、会话历史与脚本文件；
  同一个 worker 可控制项目及主窗口布局，非法布局保留原状，桥重启不重放源码。
  完整桌面 CTest 440/440 通过，包含 5 项真实 Python → UI 集成及 4 项中英文 Vulkan/OpenGL 截图。
  文件 main guard、同目录导入和标准脚本上下文的 Python 回归 8/8 通过。
  替换布局前丢弃引用旧编辑器的输入绑定，避免异步布局操作碰到已销毁的编辑器。
- Windows CI 路径修正：run 36380377730 的 Windows CPU 238 项均通过，后续必跑检查找不到相对路径
  JUnit 文件而失败；改为绝对路径。该 run 的 Linux/macOS/打包均通过；此修正与新 Python 面板的 CI 待跟踪。
- `7694ea3` 跨平台确认：desktop run 36382812292 全部成功（macOS Metal、Windows CPU、Linux
  GL/Vulkan、打包与干净环境启动）；Runtime run 36382812264、文档部署 36382812227 成功。
- STK 内 SSH 管理：原生 Jobs/CLI 共用 OpenSSH Host 配置；保存远端 URL、按需分配本机端口，
  提供连接状态和显式断开/重连。认证/转发就绪前不使用端口，不重放 HTTP 请求；桥退出的父管道 EOF
  会触发独立守护进程清理 SSH 子进程，远端 Runtime 作业继续。
  真实临时 sshd 完成上传、提交、断开后运行、重连下载及 host key 拒绝验证。
  完整桌面 CTest **442/442** 通过；相关 Python 回归 **74/74**，最终 SSH 专项 **16/16**，
  包括失败候选保留旧配置、缺失 OpenSSH、端口抢占、并发与 CLI；本批跨平台 CI 待跟踪。

- 项目格式 2：稳定引用、受约束标量公式、保守单位校验、循环/缺失来源错误及选择性缓存重算；
  原生项目编辑器新增定义模式、来源选择与变量绑定表，Python/CLI/桥共用相同修改命令。
  数据库备份与格式 1 → 2 显式升级保留旧数据；失败回滚，打开不迁移。
  相关 Python **110 项通过**，最终子集 **87 项通过**；完整桌面 **449/449**，最终 Project **29/29**。
  中英文 GL/Vulkan 截图及 759 项字典检查通过；此批跨平台 CI 待跟踪。
- 项目格式 3：持久撤销/重做与表格管理。按批次保存涉及行的前后状态，恢复 UUID、顺序与定义，
  重新计算依赖；项目修订始终递增。新编辑清空重做，失败/冲突保留栈，打开旧库不自动迁移。
  原生标题栏加入撤销/重做，管理面板提供改名与对象删除；名称草稿也保留修订。
  全量桌面 **452/452**，新增管理面板中英文 GL/Vulkan **4/4**；769 项字典检查通过。
  最终 Project 标签 **36/36**，Python 项目/表达式/撤销/桥/脚本回归 **108/108**，均通过。
- 文件索引：以格式 3 的普通类型化表格保存元数据、项目相对位置和外部位置；UI/Python/CLI 共用
  登记、刷新和路径检查。拖入文件可登记，索引编辑支持撤销；实际文件不会被复制、删除或恢复。
  原生入口支持系统打开、VSCode 编辑与项目文件夹；补齐 Windows 系统打开实现，URL 参数按数据转义。
  Python 相关回归 **125/125**，最终文件/桥/脚本 **35/35**；完整桌面 **463/463、无跳过**，
  含中英文 GL/Vulkan 文件面板截图，783 项字典检查通过。此批跨平台 CI 和真实应用关联验收待跟踪。

### CI 跟踪

Runtime 输入哈希检查：TaskSpec 可显式携带 `input_hashes`，要求与 `inputs` 精确对应；
Runtime 在复制到任务私有目录后检查哈希，通过才排队，不匹配保留失败记录与实际输入清单。
旧 spec 不增加空字段，既有幂等摘要保持；同键重试返回原任务，不重新核对已改变的工作区。
直连/Hub 完整 spec 提交检查 `input_checksums` 能力。模型/Runtime/事件/脚本/桥/Hub/control
相关回归 **80/80** 通过；未修改 C++ 任务 UI，本批远端 CI 待跟踪。

快照兼容修正的本机验证：Python 快照/项目桥/协议 **49/49**，原生 schema/项目生命周期/输入快照 **7/7**。

输入快照 `9686180` 的 Runtime run **36396871397** 发现两处问题：历史 schema 的升级目标枚举
遗漏格式 4；Windows Python 3.12 的路径 stat 与 fd fstat 使用不同含义的 ctime，已修改过的文件
被误判为复制中变化。已补格式 4 / `capture_files` 历史契约；ctime 只在同一 API 内比较，跨 API
继续比较文件身份、大小、mtime，最终源检查使用路径 stat 基线。增加模拟该差异及桥历史读取回归。
Python 3.10 Windows 快照用例已通过；3.12 修正仍需新 CI 验证。实现依据见
[CPython 3.12 路径 stat](https://github.com/python/cpython/blob/3.12/Modules/posixmodule.c) 与
[fd 元数据转换](https://github.com/python/cpython/blob/3.12/Python/fileutils.c)。

输入快照首版：格式 4 增加只追加的历史清单，选中文件流式复制到按 SHA-256 去重的内部对象库，
校验源文件变化、总字节预算、对象损坏和最终项目修订。表格撤销保留历史副本；数据库备份仍不含对象。
CLI/Python/桥及原生输入快照面板已接入。Python 相关 **133/133**、最终脚本子集 **32/32**、
最终存储专项 **15/15** 通过；原生 Project **48/48**，包含中英文 GL/Vulkan 截图，793 项字典通过。
全量桌面 468 项中 467 通过，一处新建项目格式仍预期 3 的旧断言已更新为 4，针对性复验通过。
此批跨平台 CI 待跟踪；完整项目打包、程序/参数快照与任务关联仍待后续实现。

`f055275` 的 desktop **36394747178 全部成功**，包括 Windows 路径身份修正、macOS、Linux、发布包
与干净环境启动；Runtime **36394747020**、文档 **36394747069** 成功。同时覆盖 Python Runtime API 提交 `6834188`。

Python Runtime 操作覆盖：`stk.connections`、`stk.runtime()`、`stk.transfers` 复用已有工作区、
任务和传输操作，显式幂等键、保留 Hub 待审核结果；新增有界 `task.logs` 字节读取。
真实 worker + loopback Runtime 完成上传/提交/日志/下载及冲突重试，中断不取消已接受任务。
Python 脚本/桥/Runtime/Hub/SSH **69/69**，原生 schema/项目/Python **23/23** 通过；本批远端 CI 待跟踪。

文件索引提交 `6056591` 的 Runtime **36393074017**、文档部署 **36393073998** 成功；
desktop **36393073976** 的 Linux、macOS 与打包成功；Windows 编译成功、255/256 测试通过，
文件打开测试仅因原生规范化反斜杠路径与混合斜杠预期的字符串比较而失败。改为用 UTF-8 路径解析后
比较实际文件身份，保留打开目标、缺失文件拒绝及调用次数断言；生产路径未改。修正后的远端 CI 待跟踪。
真实应用关联/VSCode 启动仍需真机验收。

`d0fd5f5` 的 desktop run **36390818302 全部成功**（Linux/macOS/Windows/打包/干净环境），
同时包含前一批 `dfd2c27` 的 procfs 清理修正。Runtime **36390818350**、文档部署 **36390818365** 成功。
`dfd2c27` 自身的 desktop run 36390225570 被后续推送自动取消，不作为失败或已通过的证据。

`d0b6c5c` 的 Runtime run **36388797350**、文档部署、macOS、Windows 和打包验收已通过。
desktop run **36388797238** 的 Linux 449 项中，仅旧有 `HelloTimeoutRestartsTheBridge` 在清理扫描
`/proc/*/cmdline` 时失败：进程退出引发流缓冲迭代器直接抛出 ESRCH。改用带流状态检查的分块读取，
忽略已不可读的进程，保留存活进程匹配和清理断言；不改变生产重启逻辑。
重新构建后的超时重启用例连续 **12 次通过**，修复提交 `dfd2c27` 的远端 CI 继续跟踪。

SSH CI 补充：`33c88d6` 的 Runtime run 36384809632 全部成功，包括 Linux 真实 sshd 和 Windows
模拟传输；文档部署成功。desktop run 36384809472 的 Linux/macOS/打包成功，Windows 现有 CPU
测试通过，但必跑检查发现 SSH 用例未被旧 CMake Windows 过滤器注册。已将该可移植用例加入过滤器；
不删除必跑检查；修正后的 desktop run **36386610173 全部通过**。

`8007029` 的 Runtime 重跑还捕获 Windows 清理断言竞态：守护进程退出后立即检查后代 PID，
可能碰到已终止进程的 PID 尚未消失。改为限时等待整个已记录进程树终止，并继续断言没有存活后代；
不放宽为跳过或忽略清理失败。生产清理逻辑未变；`05293e3` 的 Runtime run
**36387729994 全部通过**，文档部署也成功。

### 紧接着处理

- `f8b7943` Runtime **36401996982**、文档 **36401997053** 成功；desktop **36401996989** 的
  Linux/打包通过，macOS 296/297 通过，新 HTTP 端点测试在准备阶段超时。发现测试 `HTTPServer`
  默认调用反向 DNS，改为直接绑定 loopback，不依赖主机名；增加超时状态日志。
  禁止 DNS 的 HTTP 提交/取消检查通过，原生按钮测试连续 **5 次通过**。
  修正提交 `7ebf746` 的 desktop **36403445288 全部成功**（macOS、Windows、Linux、打包及干净环境），
  Runtime **36403445272**、文档 **36403445317** 成功；原超时未取得进程堆栈，不把 DNS 归因为已证实。

- `616bf3f` 的 Runtime **36405264493**、文档 **36405264372** 成功；desktop **36405264363**
  **全部成功**，包含 Linux、macOS、Windows、打包和干净环境。
- 最近项目 `623fe2b` 的 desktop **36406870490** 全部成功，文档 **36406870578** 成功。
  Runtime **36406870548** 首次的 Windows Python 3.12 在旧 `test_acceptance` 生成完整示例时超过 20 秒；
  其余测试与平台通过。同一提交显式重跑失败作业后全部成功，未修改测试或生产代码；超时原因未证实。
- 格式 5 后端 `613bf6c` 的 desktop **36400084985** 全平台成功，Runtime **36400084994**、文档 **36400084958** 成功。
- `23773d2` 的 desktop **36398208056**、Runtime **36398208012**、文档 **36398208047** 全部成功，
  验证了输入快照、Windows 时间戳兼容、历史契约和 Runtime 输入哈希检查。
  `9686180` 的 desktop 36396871406 被后续提交取消，不能作为全平台通过证据。
- 继续 Python 操作覆盖和通用对等端点；当前 SSH 访问 Linux Runtime，不提供远程 Python/UI 操作。
- 继续原生运行交互、结果打开入口和通用字段；按可独立验证的开发包交付。

### 当前限制

项目表格仍是基础编辑闭环；完整多维表格、插件单元格、AI 页面、分层节点和文档预览待开发。
用户此前已验证 macOS/Windows 主窗口与 3D 渲染；新增项目编辑交互仍需后续平台验证。
不合并无关既有 PR，不发布私有历史交接内容，不改变外部求解器或授权服务。

### 离线工作台演示

`examples/project_scan/offline.py` 可在桌面 Python 面板显式运行：准备三组参数、跨表公式、
本机合成场与独立图统计、结果表、文件索引和输入副本，并配置项目/Viewer/Python 三个区域。
每次创建新项目，保存此前布局以便恢复；无远程连接、无 Runtime 任务，不把合成场称为物理求解。
Python 基础/VTK 两种路径 **2/2**、真实桥原生交互及四种中英文 GL/Vulkan 渲染 **5/5** 通过；
截图确认 Viewer 实际显示三维场。完整验收步骤见 `examples/project_scan/OFFLINE.md`，跨平台 CI 待跟踪。

CSV/图 API 提交 `f4bfbae` 的 desktop **36408907358** 全部成功，Runtime **36408908042**、
文档 **36408907835** 成功；包含 Linux、macOS、Windows、打包及干净环境。

### 项目文件进入三维视图

文件索引新增场数据预设和“在查看器中打开”；解析位置与修订后才发起本机查看，不改变项目修订。
Viewer 直接接受 DAT/NPY/VTI/VTK/VTKHDF，保留文件名并区分同目录来源；即使父目录包含结果清单，
也读取明确选中的场文件。已保存载荷/结果直接打开，未知文本、缺失文件和不兼容预设拒绝。
结果请求由应用壳在帧后消费，隐藏 Viewer 会被激活；没有 Viewer 时添加标签，保留已有项目。
完整重编译后桌面 **498/498** 通过，无跳过；含真实桥/中文路径/独立 Python 实际 VTK、
无 Viewer 和隐藏标签回归、中英文 GL/Vulkan 截图。字典 **851/851** 通过；本批远端 CI 待跟踪。

离线演示 `55373a1` 的 Runtime **36410580865**、文档 **36410580930** 成功。desktop
**36410580845** 的干净环境安装在 PyPI `python-dateutil` 索引连续读取超时后解析失败，
首次未执行包启动检查；同一提交重跑失败作业后全部成功，macOS、Windows、Linux、打包与干净环境均通过。
未修改依赖约束掩盖网络失败。

### 通用表格横向滚动与数值排序

表格超宽时显示可拖动/翻页的横向滚动条，支持 Shift + 滚轮及横向触控板事件；
表头、数据、排序命中和列宽拖动使用同一偏移。窗口变宽/删除列会校正偏移，删除被排序列不会保留越界索引。
项目数字列改用实际单元格值比较，公式前缀不参与排序，整数不转成 double；相等项保留模型顺序。
组件/窗口子集 **149/149**，最终完整重编译后的桌面 **503/503、无跳过**。覆盖 1x/1.5x/2x，
横向手势、滑块/轨道、排序/选择/键盘/列宽、空表/删列和 64 位整数；离线中英文 GL/Vulkan 截图
确认窄项目区域可滚动看到派生温度。物理触控板和新增交互仍需 macOS/Windows 真机验收。

### 项目修改预览

`ProjectStore.preview` / `stk.project.preview` / CLI / 桌面桥及 C++ 客户端复用相同编辑和公式引擎，
在 128 MiB 以内源库的内存副本中返回候选快照与已分配 UUID 的命令；原项目、撤销/重做、文件和任务不变。
候选状态明确 `persisted=false`；显式 `apply` 仍检查基础修订，不自动确认、保存草案或提交任务。
验证只读源库、旧格式、WAL、源身份替换、内存副本预算、失败整批不写入、公式错误保留、
并发编辑不受预览求值锁住、候选结果与实际提交一致，以及真实 Python worker/C++ 桥无修改事件。
相关 Python **230/230**，完整重编译桌面 **503/503** 通过；协议操作目录旧断言补入新增方法，未放宽校验。
使用和限制见 `docs/project-preview.md`；AI 草案页面、持久草案及候选差异 UI 仍待开发。

### 工作台 CI 证据补齐

`f1a0f72` 的 desktop **36413089067 全部成功**，Runtime **36413089012**、文档 **36413089085** 成功，
覆盖前一批文件打开与表格改进。下载 macOS 产物后发现上传路径遗漏了 `tests/app/out` 中的
项目/Python/离线工作台截图；测试已执行，但旧产物无法检查这些画面。
补入 macOS 工作台截图、Linux Viewer 截图及两平台 JUnit。Linux GL/Vulkan 和 macOS Metal
各自按中英文逐项检查十类工作台测试，缺失、跳过、失败均拒绝，不仅依赖已有宽泛模式。
工作流 YAML/命令语法检查通过，本地已完成的 JUnit 中全部 **40 项** Linux 渲染记录通过必跑检查；
macOS 产物与新门槛待本次 CI 验证。未声称 Windows CI 执行了 GPU 渲染。

### 交付检查与下一批依赖

离线工作台测试通过真实 Python worker 先预览公共参数修改、检查三条跨表派生值且源库不变，
再在独立操作中应用原命令/修订；基础和实际 VTK 两条路径 **2/2** 通过，冻结输入与已有结果保留。
演示指南补充用户可直接执行的两步检查，桌面 CI 触发路径补入其实际加载的 `examples/project_scan/**`。

开发计划重排为草案检查/AI 工作区基础、通用批次、共享字段、文档嵌入原型和分析过期传播，
已完成的存储开发包不再重复列为下一步。新增文档预览技术验证记录，核对 GHOST 句柄层、
WKWebView/WebView2/Qt 接口与分发条件，引用官方资料并明确原型尚未实施、技术尚未选定。

新增[工作台真机验收清单](workbench-acceptance.md)，覆盖双平台更新启动、离线参数/公式、
撤销、候选预览、文件 Viewer/VSCode、输入校验、Python 布局及重开；远程 Linux Runtime 检查单独列出。
明确 Windows CI 未执行 GPU 真机渲染，以及通用对等通信仍待开发。

`a0d7f57` 的 desktop **36414890836**、Runtime **36414891171**、文档 **36414891070** 全部成功，
覆盖修改预览和新的必跑/产物检查。下载 macOS artifact 后确认 **312 项 CPU、53 项 Metal** 无跳过全部通过，
已检查离线三维和文件预设截图；共归档 22 张工作台图片。`dbf3cde` 自身桌面 CI 被后继推送取消，
以本次完整成功为跨平台证据。

Linux 单机额外检查：100/1000 行、每行 5 个无量纲表达式共同依赖一个输入，以不超过 1000 条命令分批创建。
预览一次修改公共输入分别约 **0.034/0.358 秒**，候选 JSON 约 **0.20/1.98 MB**，源库 SHA-256 不变且所有值核对通过。
这是一次直接 `ProjectStore` 调用的规模观察，不包含桥序列化/桌面响应时间，不作为性能门槛或双平台承诺。

### 横向滚动条保留完整数据行

检查实际 macOS 截图时发现离线表格的第三行被滚动条部分遮住。共享布局现在根据最终列宽
额外分配滚动条高度，保留要求显示的行数；变宽时移除额外高度，多次布局不累计高度。
1x/1.5x/2x 回归验证完整第三行可点击、父区域滚动引发的二次布局和窗口宽度往返。
首轮完整测试只有六个默认布局 golden 预期变化：逐项比较确认每份仅 Jobs 表格高度和其后标签 Y
增加相同的滚动条高度，其他属性完全不变；据此更新六份 golden，未放宽比较。
更新后的 Linux 三维演示截图确认三行温度完整显示；最终完整回归 **504/504、无跳过**，跨平台 CI 待跟踪。

`c3fa59c` 的 Runtime **36416998488**、文档 **36416998657** 成功；桌面 **36416998477** 继续跟踪。
复核截图对应的预设后，文件指南补充实际数学语义：现有 `volume` 先计算模长，负标量会失去符号。
离线示例的非负场不受影响；专用有符号标量预设及字段/单位选择列入后续分析开发包，未改变既有预设契约。

最终 desktop **36416998477 全部成功**；Windows 作业完成后确认本轮最后功能提交跨平台通过。
macOS 最终 JUnit **313 项 CPU、53 项 Metal** 全通过且无跳过，截图确认第三行完整显示。
文档说明提交 `d01bf76` 的 Runtime **36417769639**、文档 **36417769613** 成功。
