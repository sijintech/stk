# STK 0.1.0a1 验收记录

## 2026-11-10 21:35 UTC · 图谱来源、原生复验与 Cocoa 取证

`f497dfae` 集成独立候选 `f50947f9`。Web 图谱以实际接受的渲染层为准，显示绑定任务、运行工作区、预设、输出和时间步。有效载荷步号优先。新场景提交后清除旧探针数值，保留同场景导航和失败时的原画面。新绑定、范围变化或本地数据包使过期画面回执失效。本地数据包显示文件名。独立与 Root Chromium 各 165/165，零跳过及重试。模拟 Hub 额外覆盖有效载荷读取后延迟的真实渲染模块、注入模块失败、迟到计算、错误摘要和仅有输出卡片。

Root 使用当前 Vite 产物、真实本机 Hub、NodeAgent WebSocket、Runtime 和 Chromium。合成 MuFerro SDK 生成任务 B 的公开格式结果，全局队列选中不同项目的任务 A。中文 1440×900 与 390×844，固定起点为已明确计算并显示任务 B 第 2 步。打开「来源」和收起各 1 点击，旧版标出 A，新版两端均显示 B 的完整任务 ID、运行工作区和第 2 步。画布几何保持。宽窗测量段仅捕获到既有定时刷新与一条针对 A 的 `task.get`，窄窗没有请求。零新增动作、图谱求值或模型请求，Runtime 仍只有夹具的两项任务。证据在外部 `root-delivery-20261110-143/graph-live-proof` 与 `graph-source-root`，浏览器使用软件渲染，SDK 为合成夹具。

原生 `8947053d` 主工作树完整构建通过。工作台、保存问答和流式回复 65/65、UI 132/132、窗口 88/88，零跳过。主工作树二进制 SHA256 `ddd9d2486c9905484838ba50d90d0dcc7492ea4855bdc2c8a21f76f7002158cf`，同一中英文 X11 实窗路线再验，往返分别 2 和 4 次点击，零补滚，记录区域零像素差。前一原生集成版 `fd5c69c8` 完整项目套件 966/966，零失败及跳过，975.568 秒。收据在外部 `root-delivery-20261110-142`。

同头 `9ce87c63` 正式 macOS 工件 `13804850740` 校验通过。CPU 1566/1566、Metal 254/254，必测原生 4/6。MP4 与 HTML 首次工具栏暂停都通过，之后分别在隐藏保持和颜色切换前暂停阶段失败。可见重复对照 HTML 通过，同一导航两次查询分别约 47 和 43 ms 返回原始暂停态 2。MP4 在到达重复步骤前就从 0.105125375 s 回到 0.0471945 s，低于原 0.05 s 阈值，ACK 已到而独立核验未回。独立的隐藏对照在同一导航先确认可见暂停，隐藏后 MP4 28 次、HTML 29 次查询均返回原始播放态 1，直到看门狗。该对照与首次工具栏观察分开，原始状态本身不证明解码画面是否前进。Windows CPU 1506/1506，Windows 原生验收仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42895759127) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42895759127/artifacts/13804850740)

`e038d55c` 集成 `e504bdc2` 的可选首次工具栏观察。MP4 和 HTML 视频用同一原片及同一真实工具栏动作，对照零主动等待和 270 ms 延迟。记录点击后早期及约 200、600 ms DOM 读数，并保存派发、隐藏、重显、ACK 与实际返回的原始 WebKit 播放态。早期读数是一次观察，必测路径等待暂停条件。两项新用例接入原可选步骤，六项必测及原延迟注册照旧。独立候选 C++ 四配置、CLI、CMake、AX CPU 1/1 和扫描通过。Root 构建测试程序，核对工作流只有两处可选位置变化，Bash 检查通过。实际取证待下一 macOS CI。 [必测与诊断证据](https://github.com/sijintech/stk/actions/runs/42895759127/job/130108352091)

## 2026-11-10 21:19 UTC · 原生保存问答恢复阅读位置

`8947053d` 集成独立候选 `7cf60aae`。桌面每个 AI 标签在当前项目打开期间按问答保留最近 32 个读取位置，包括是否跟随末尾。读取未完成时的空画面不会覆盖保存位置。新问答继续默认跟随末尾，智能体会话沿独立视图。定向回归旧版从 545 px 回到 0 px，另复现了跟随状态下点击滚动条轨道向上翻页后回弹。候选工作台 25/25、日志控件 2/2，零跳过，覆盖滚轮、轨道、键盘、同一区域不同 AI 实例和重开项目。Root 核对补丁逐字节一致并完成暂存区扫描，主工作树的完整构建与相邻套件正在复验。

Linux X11 英文 1600×1100、中文 680×620，缩放 1。固定起点为隔离项目已打开、长问答 Alpha 可读、草稿未提交。先用实际滚轮向上 10 格，英文由第 67 行到 37，中文由 88 到 58。测量段点短问答 Bravo 和返回 Alpha，英文每次 1 点击，中文经历史每次 2 点击。两端零补滚，旧版均回到第 0 行，候选均回到原行。返回前后记录区域零像素差，草稿文字保留，中文截图的输入框因焦点移到历史而改变底色。测量仅有两次 `project.requests.progress`、两次上下文和四次问答读取，SQLite 与 Runtime 快照一致。实际用窗及对照收据在外部 `root-delivery-20261110-142/native-transcript-comparison.json`，候选二进制 SHA256 `454cd1dac5c01b6eef038969ff2eaa66360a35ac2386af00bfddeefc523331e2`。

Web 图谱来源已在 `aa88dbe4` 的同一 Web 产物上用模拟 Hub 宽窄窗各复现。全局任务为 A 时，图谱绑定另一项目的 B 并实际显示第 1000 步。一次点击「来源」仍显示 A，未列显示步号。已在独立 worktree 修复方向定位到当前显示的载荷和已接受的计算绑定，兼顾本地数据包。基线收据在外部 `root-delivery-20261110-142/graph-source-triage`。

远端 `9ce87c63` 的 Linux Desktop 2201/2201，通过两项 Linux 打包。macOS CPU、Metal 与包内烟雾通过，必测 WKWebView 步骤失败，整轮仍在上传诊断工件及运行 Windows 作业。待终态和正式工件后再发布。本地前一原生集成版 `fd5c69c8` 的完整项目套件已启动，包含 966 项。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42895759127) · [macOS 作业](https://github.com/sijintech/stk/actions/runs/42895759127/job/130108352091)

## 2026-11-10 21:09 UTC · 原生概览精确返回与 Web 阅读位置

`fd5c69c8` 集成独立候选 `6de17daf`。聚焦会话成功打开项目概览后，直接返回时核对原 AI 实例、项目、窗口可见性与分栏活动。主动切换分栏标签会让返回沿普通导航选择。独立旧版定向复现另一份草稿，候选定向 24/24。Root 构建后工作台、问答与布局 61/61，窗口 88/88，零跳过。

Linux X11 英文 1600×900 缩放 2、中文 680×620 缩放 1。固定起点为同一隔离项目、两个 AI 实例各有不同草稿、原会话处于聚焦且 Viewer 公开载荷已转动。新版本准备 11 次点击、两次输入和一次中键拖动。旧中文夹具准备多一次区域菜单点击。测量段各 1 次打开概览、1 次返回工作台、1 次查看结果，零滚轮。旧版显示另一份草稿，新版显示原草稿。返回结果后画布英文 880384 像素、中文 318528 像素均无差异。只观察既有 `modules.list` 读取，SQLite 与 Runtime 快照一致。证据在外部 `root-delivery-20261110-141/exact-return-window`，集成二进制 SHA256 `e1598aa9c667dc3be4eff3c6e43d30294664f535fa39b8071d574f3dfe91187f`。

`c661b195` 集成独立候选 `eddd4ec4`。Web 记录当前连接中每个已访问会话的滚动位置，在切换会话时恢复，普通切页与迟到历史响应沿原行为。独立及 Root 完整 Chromium 各 160/160，构建通过，零跳过和重试。另在同一集成产物用真实浏览器滚轮复验 2/2。模拟 Hub 的中文 1440×900 和 390×844，固定起点为已配对、打开 60 条记录的 A、滚到 560 px 且留有草稿。打开短会话 B 再返回 A，宽窗各 1 次点击，窄窗各 2 次点击，返回无需补滚，零 POST。原版两端回到 0 px。新版也通过独立的 880 px 会话、同会话重选、跨任务页选择、过期读取与断开重连。证据在外部 `root-delivery-20261110-141/web-transcript-root` 和 `web-transcript-return`。

桌面保存问答阅读位置已在旧版 X11 英文 1600×1100 缩放 1 复现。固定起点为长问答从尾部向上滚 10 格后读到第 37 行且有草稿，点短问答与返回长问答各一次，返回显示第 0 行。原草稿区域零像素差，SQLite 与 Runtime 快照一致。截图与方法收据在外部 `root-delivery-20261110-141/window-transcript-red-live`，原生对齐在独立 worktree 开发。

远端 `9ce87c63` 的 Desktop 三个 Linux 作业通过，Windows CPU 和 macOS 原生验收仍运行。macOS CPU 与 Metal 已通过。本地提交等待整批 Desktop 终态。开放 PR 的原头仍为 #53 `c9f13994` 与 #54 `2dd3e4ee`，分别为冲突的旧重试补丁和早期交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42895759127) · [PR #53](https://github.com/sijintech/stk/pull/53) · [PR #54](https://github.com/sijintech/stk/pull/54)

## 2026-11-10 20:56 UTC · MuPRO HDF5 链路与原生全量复验

`39b00f52` 集成独立候选 `11840923`，在测试退出时等待 NodeAgent 停止并关闭事件循环。测试使用真实本机 Hub、NodeAgent WebSocket、Runtime 和已配对 Web 客户端。合成完成任务发布 `case/run.h5`，通过已有图谱节点精确列出两个步号，选择第 2 步的 `Polar` 并按 Web 的 `f32` 编码验收。核对容器和线传载荷的 SHA-256、原生 `float32` 与 24 个体素值。先用错误摘要触发 `invalid_data`，断言动作无结果且 Hub 无新载荷。原 DAT 路线同时覆盖。独立候选定向 2/2、完整 37/37。Root 集成版独立完整 37/37，零跳过，已有 Starlette 弃用警告一项。验证范围为合成产物读取，真实 MuPRO 求解、许可、研究参数和仅凭 HDF5 判定任务完成仍待验。收据及日志在外部 `root-delivery-20261110-140/mupro-hdf5-hub`。

`a7fffbf7` 的最终原生项目全量测试结束，964/964，零失败、零跳过，851.539 秒。日志、XML 和退出码在外部 `root-delivery-20261110-139/compose-project-final.*`。后续 `3055fbf3` 概览入口的实窗与 148 项定向结果见下一节。已定位多会话分栏中从概览返回可能选中另一个 AI 实例，精确返回的回归与修复在独立 worktree 开发。

远端 `main` 仍为 `9ce87c63`。同头 Runtime 13/13 已完成，Desktop 的两项 Linux 打包通过，其余三个作业仍运行。本地提交等待该 Desktop 批次终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42895759127) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42895759007)

## 2026-11-10 20:46 UTC · 聚焦会话的项目概览入口

`3055fbf3` 将聚焦会话页头的次要入口标为「项目概览」及 `Overview`，保留原项目引导、分栏恢复与点击路径。一级「工作台」继续表示聚焦会话，普通分栏与其他编辑器仍使用旧名。旧版定向回归的唯一失败是英文泛称 `Home`。最终工作台及问答 60/60、窗口 88/88，零跳过。英文双倍缩放的控件宽度与六个默认窗口基线均通过。

Linux X11 英文 1600×900 缩放 2、中文 680×620 缩放 1。固定起点为已打开隔离项目、历史读取结束的聚焦工作台，公开载荷此前已在结果页转动。准备 4 次点击和一次中键拖动。两端各 1 次点击输入草稿、1 次打开概览、1 次顶栏工作台返回、1 次查看结果，零滚轮。两种文字完整显示，项目概览内容区与旧版相同，返回同一会话及未提交草稿。相机正对照先改变英文 235513 与中文 111096 像素，往返后相同画布区域英文 880384 与中文 318528 像素均无差异。测量只观察既有 `modules.list` 读取，SQLite 和 Runtime 快照一致。收据在外部 `root-delivery-20261110-140/overview-window`，二进制 SHA256 为 `182f37f75f8dd1cbb50cace3dbaa1d3e58e0a829eb8a29874ebf30137f04f1ff`。

远端仍为 `9ce87c63`。两项 Linux 打包已通过，其他 Desktop 作业与 Runtime 仍运行。最终空会话候选的原生全量套件也在运行。当前两条旧 PR 的头分别仍为 `c9f13994` 和 `2dd3e4ee`。另在独立工作树准备三跳 HDF5 合成验收，核对 Hub、NodeAgent 与 Runtime 转发后的字段、步号、容器摘要及拒绝路径，沿用发布契约。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42895759127) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42895759007)

## 2026-11-10 20:35 UTC · 主线发布与 Web 返回焦点

`9ce87c63` 已快进推送并核对远端 `main`。这批含空会话与归档修复、双端结果保留及 Cocoa 对照。新源码头 Secret scan 与 Pages 通过，Desktop 和 Runtime 已运行。上一批 Desktop、Windows 工件和 macOS 失败阶段见下方终态记录。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42895759127) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42895759007)

`fb458360` 集成 Claude92 已提交的 `1fa5e30f`，补齐缩窗自动打开历史时清除任务返回标记。直接返回任务时核对精确任务范围、入口是否存在、启用和可见，保留两个滚动位置。较早范围、普通导航、忙碌或剪裁入口都使用一级导航焦点。Claude 提交独立验收 157/157，Root 独立复验同提交 157/157。新增缩窗用例在原提交复现焦点错误，整合版构建与 Chromium 158/158，零跳过和重试。

中文模拟 Hub 1440×900 和 390×844。固定起点为已选任务的任务页，200 行队列内滚动 160 px，任务和会话均有草稿，结果画布已调整。两种窗口各覆盖 5 条明确捷径路线。鼠标每条 1 次打开和 1 次返回，键盘路线设置初始焦点后各 1 次激活，并验证长按 Enter 的重复事件。两端返回后队列、TaskSpec 和结果画布截图相同，测量只包含明确捷径已有的结果列表或日志读取。另测 1440→390 自动打开历史，Esc 后恢复 1440，再 1 次点任务，焦点留在导航，滚动和草稿保留。原始路线和截图在外部 `root-delivery-20261110-139/web-task-return-reviewed/playwright-reviewed`。

Claude92 收尾进程因 CLI OAuth 会话过期以 1 退出。它的独立工作树仍保有原提交及两份未提交文件。Root 以已提交候选独立复验并修订。`fb458360` 已在本地 `main`，下一次推送待远端 Desktop 终态。先前原生项目完整套件以 963/964 结束，唯一失败是已更正的归档夹具断言。最终原生候选的 59 项定向已通过，完整项目套件已重新启动。

## 2026-11-10 20:28 UTC · 原生空会话与归档切换

`a7fffbf7` 将原生聚焦空会话的输入放在引导后，省去空记录区和禁用的旧问答操作。现代桥在导航提供最近问答，完整历史、分页和归档筛选由「已保存问答」展开。旧桥保留页内列表。已有问答、模型设置和准备与发送的明确操作沿用原入口。

回归复现了归档筛选切换时，仍在途的旧分页回执令列表错误地回到已加载。修订后接收回执前核对筛选与归档键，过期回执让当前筛选重新读取。定向用例在未归档列表已在途时用鼠标切换筛选，最终读到原归档请求并保留草稿。最终候选工作台、问答及归档 59/59，窗口 88/88、Jobs 55/55，零跳过。另一个较早候选的全项目套件仍在执行，它包含后来更正的归档显示断言。

Linux X11 英文 1600×720 与中文 680×620，比例 1。固定起点为打开无保存问答的隔离项目、列表读取结束后的工作台，准备两次点击。两端各 1 次点击输入，任务、结果、返回工作台各 1 次，零滚轮。输入框和准备按钮在英文上移 200 px，中文上移 188 px，基线也可零滚动输入。返回保留原草稿。另用已有问答的英文宽窗，从聚焦会话 1 次展开完整列表，当前问答的画布区域逐像素一致。三路线无准备、发送、图谱求值、模型调用或写入。归档竞态由窗口事件回归覆盖。收据在外部 `root-delivery-20261110-139/compose-window`，最终二进制 SHA256 为 `ea997e5b6cd2892da7b50fdc1f7cf3f09f6a1713788bdbc737fad1991846d5c2`。

Claude92 的独立候选 `1fa5e30f` 通过 157 项 Chromium 测试。审阅发现宽窗历史获得焦点后缩窄，会自动打开弹层且未清除旧任务返回标记。Claude92 仍在独立 worktree 收尾，Root 按最终候选复验集成。

## 2026-11-10 20:27 UTC · Desktop CI 终态与 Cocoa 对照

远端 `bacdc753` 的 Desktop CI 于 20:17:40 UTC 完成，6 个作业中 5 个通过。Linux 2198/2198、两个 Linux 打包作业、Windows CPU 1505/1505 和 Windows 原生 6/6 通过。Windows 原生零跳过，1313.35 秒。下载工件并校验归档摘要后复核，PDF 20/20 轮、160/160 张截图摘要匹配，最后一轮重新准备第一页，记录的最长捕获启动 81 ms。MP4 和 HTML 视频均 20/20 轮，各 161 张截图摘要匹配。同源码头 Runtime 13/13、Secret scan 和 Pages 通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42883444412) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42883444412/artifacts/13800016347) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42883444505)

macOS 依赖、CPU 1565/1565、Metal 254/254 与包内烟雾均通过。生产原生 4/6，两种视频均通过首次明确可见暂停。MP4 隐藏后暂停保持失败，HTML 视频未能在颜色变化和自然结束前确认隐藏暂停。可见暂停后直接隐藏且不重复发命令的对照通过，隐藏时新发暂停的对照失败。macOS 证据文件数 1786 来自官方上传日志，原生计数和失败阶段来自官方作业日志。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42883444412/job/130065470967) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42883444412/artifacts/13798991845)

`7ab5d972` 集成独立对照 `7bc0f837`。同一可见 Cocoa 视图的首次暂停独立核验后，立即发出第二次暂停，保持导航、可见性、焦点和取证采样不变。保存两次媒体代次、ACK、首个非播放回执和失败时的关闭信息。Linux 与 Apple 条件 C++ 语法检查通过，隔离注册确认 Apple 2 项、Linux 0 项，CI 配置与 shell 检查通过。生产路径、必测项和时限沿用已发布契约。MP4 与 HTML 实际对照待新 macOS CI。收据在外部 `root-delivery-20261110-139/ci` 与 `mac-visible-repeat`。

## 2026-11-10 20:07 UTC · Web 结果切换与项目隔离

`9bc16d66` 集成 Claude90 `d636e94c`、Claude91 最终 `ebb2e951` 和 Root 复审修订。文件与图谱保留各自 Viewer、相机、已显示结果和探针。隐藏期间停止图谱进度读取和尚未发送的拖动，允许明确发出的同范围计算完成。首次图谱真正显示才读预设。项目、节点或任务变化清理旧图谱，迟到回执不能显示到新范围。Root 复现了旧 `.stkp` 选择框残留及窄窗历史上方迟到错误，修订后可在新范围重新选择同一文件，结果通知回到当前结果页才显示。Claude 最终独立 Chromium 133/133，定向 18/18、重复 150/150。Root 整合版构建通过，Chromium 133/133，零跳过及重试。

模拟 Hub 的中文 Chromium 1440×900 与 390×844。固定起点为已选任务、加载 `scalar-0.vti` 并取得探针回执的结果文件页，任务及会话有未提交草稿。导航路线各 6 次点击，首次图谱、文件、图谱、任务、结果、文件各 1 次。首次显示读预设 1 次，明确计算、探针和相机拖动单列。普通切换和随后模拟的 60 秒内无额外图谱读取、求值、模型调用或写入，原有心跳及所选任务的轮询单列。返回时两种 Viewer 实例、画布像素、来源和探针一致，草稿仍在。另验证同节点无所选任务的跨项目、在途轮询晚成功、后台进度、文件重新选择、窄窗历史中的错误及延迟加载。图谱探针迟到回执为源码验证。宽窄路线、截图、请求和测试汇总在外部 `root-delivery-20261110-138/web-result-scopes-reviewed/playwright-integrated-final`。

Claude92 已从 `9bc16d66` 在独立 `claude/web-task-result-return-focus-92` 接 Web 返回任务的焦点对齐。Root 负责复验和集成。远端 `bacdc753` 的 macOS 原生必测步骤失败，包内烟雾与 CPU、Metal 仍为通过。具体用例等原生工件，Windows 原生仍运行。推送待该 Desktop 批次终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42883444412) · [macOS 作业](https://github.com/sijintech/stk/actions/runs/42883444412/job/130065470967) · [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42883444412/job/130088023992)

## 2026-11-10 20:03 UTC · 窄窗历史保留结果页状态

`0dd2f7dd` 让原生菜单弹层与对话框隔离下层输入。窄窗打开历史时，菜单继续处理方向键、Enter、Esc。旧版定向回归复现小键盘改变待应用相机预设，并接受拖入的 `.stkp`、替换原载荷。修订后历史打开时两者均隔离，Esc 关闭后两者正常生效。工作台 45/45、窗口 88/88、Jobs 55/55，零跳过。

Linux X11 中文 680×720，缩放 1。固定起点是打开隔离合成项目和公开 `.stkp` 的聚焦结果页，准备 3 次点击。点历史 1 次，移动到可见画布按小键盘 1 和滚轮，Esc 关闭。Enter 从原入口重开，点保存的 Bravo 会话 1 次，点结果返回 1 次。三段画布像素均一致。另一次不移动的中键点击作为聚焦准备，关闭菜单后同一个小键盘键改变 148371 像素。文件拖放由窗口事件回归覆盖。测量无模型调用、图谱求值或写入，SQLite 与 Runtime 快照一致。原始收据在外部目录 `root-delivery-20261110-138/history-overlay-window/window-zh-final`，二进制 SHA256 为 `d81889d4e95130dce74a55d39095e19479e65ee6929950c5a56c26353b7e277b`。

远端 `bacdc753` 的 Runtime 13/13、Linux Desktop 2198/2198、Windows CPU 1505/1505 与两项 Linux 打包均通过。macOS CPU、Metal 和包内烟雾已通过，macOS 与 Windows 的原生内容验收仍运行。当前原生提交已在本地 `main`，推送待 Desktop 全部到终态。Claude91 的 `34833a93` 候选与 Root 的两个边界修订均独立通过 Web 131/131。Claude 在独立 worktree 补强定向覆盖，Root 依据其最终提交复验集成。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42883444412) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42883444505)

## 2026-11-10 19:46 UTC · 双端一级导航的选中态

`d61ecab3` 让原生聚焦工作台沿用 Web 的视觉层级。当前页以蓝色底、描边、白字和圆点标记，其他页与分栏入口在静止时是平面按钮，键盘焦点单独描边。只在聚焦导航使用该外观。UI 131/131、窗口 88/88、Jobs 55/55、工作台导航与布局 39/39，零跳过。六个默认窗口和两个普通 Jobs 快照沿用原基线。

Linux X11 英文 1600×720 与中文 680×720，缩放 1。固定起点是已冷启动、选定合成 Runtime 任务、保留未提交草稿并滚动 40 px 的聚焦任务页，同一区域挂载任务和结果。到达起点各 3 次点击、一次输入、Return 和一次滚轮。测量段各 1 次点击打开第 7 步、1 次返回。两端的入口文字位置与点击坐标沿用基线，唯一选中项由 `#363636` 灰底变为 `#394A64`，描边 `#6FA9E6`，字形峰值亮度从 142 到 255。分栏获得键盘焦点时当前页仍选中。返回保留 40 px、任务、草稿和结果入口焦点。结果画布对照英文 796928 像素与中文 352656 像素均无差异。未新增切页求值、模型调用或写入。收据和逐像素对照在外部目录 `root-delivery-20261110-137/visual-nav-window`，受测二进制 SHA256 为 `565608fabd01f90d3d1f6900db42d71ffac76cc50a8b6e1f4469f8eb919ff604`。

实际 Claude90 最终提交 `d636e94c`，独立全套 Chromium 115/115。产品变更与先前候选一致，补强了迟到计算回执和时间控制测试。Claude91 已在独立 `claude/web-result-scope-visibility-91` 从该提交开始修正项目和页面可见性边界。Root 等待最终候选后复验集成。

远端仍是 `bacdc753`。同源码头 Runtime 13/13，两项 Linux 打包均通过。macOS 完成依赖、构建和 CPU 测试，已进入 Metal 测试。Linux、Windows 与原生验收门禁仍在运行，待终态后发布本地提交。PR #53 原始重试问题由当前主线定向回归 3/3 覆盖，旧补丁仍冲突。PR #54 是早期交接快照。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42883444505) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42883444412)

## 2026-11-10 19:33 UTC · 原生任务返回与首次结果

`3afb443d` 在原生聚焦工作台为同一区域的任务页与结果页分别保存外层滚动。返回时核对Viewer 当前来源的任务、运行连接、节点、工作区、选中代次和目标编辑器。入口仍可见时把焦点归还给它。切换期间选中别的任务会保留新选择。新增回归在原实现复现返回偏移从 40 px 归零及焦点落在导航，修订后 Jobs 55/55、UI 131/131、窗口 88/88，零跳过。

Linux X11 英文 1600×720 与中文 680×720，缩放 1。固定起点为同一个保存区域的聚焦任务页，已选合成 Runtime 任务，表单展开且有草稿，外层已滚动 40 px。通过公开载荷预热元数据，从启动到起点各 4 次点击、一次输入、Return 和一次外层滚轮。测量段各 1 次打开第 7 步结果、1 次返回。队列区域像素和归一化草稿字形一致。Tab 离开入口、Shift+Tab 回到入口，两端焦点像素变化可复验。只观察到明确打开与已有邻步预取，没有切页引发的新求值、Runtime 写入或模型调用。收据在外部目录 `root-delivery-20261110-136/tasks-return-window/window-*-shared-warm/verified-receipt.json`。受测二进制 SHA256 为 `30a006dddc9a000e6fdbf728248f94aed7014abb2e031362056af21f044a1163`。

`3cdfb7b4` 统一有无预加载元数据时的任务默认预设。冷启动回归在原实现发出 `energy-plot` 并返回空步号。修订后两条路径均按现有任务默认规则打开 `muferro-domains`，精确绑定原任务。Viewer 32/32，零跳过。

冷启动以同一保存布局复验两种窗口。起点前没有打开样例，也没有读取预设、目录或色图。准备为 3 次点击、一次输入、Return 和一次外层滚轮。各 1 次点击打开并显示第 7 步、1 次返回。保留 40 px 偏移、队列与草稿。Tab 和 Shift+Tab 证实焦点恢复。正常邻步预取之外，返回无新求值、模型调用或写入。原始收据在外部目录 `root-delivery-20261110-136/tasks-return-cold-window/window-*-cold/window-receipt.json`，二进制 SHA256 为 `9c4e3b18f2c68bc5269f86a704b9f820d5fc61777adfa26f3b0318d5667328cd`。

远端 `bacdc753` 已发布。该源码头的 Linux 打包与干净环境安装通过，macOS 已通过依赖安装并进入构建。其余 Desktop 与 Runtime 作业未达终态，这两项原生改动仍在本地 `main`。Claude90 的独立候选 `fc42e14b` Web 测试 113/113。审阅发现同节点无所选任务时的项目切换隔离，以及离开结果页和窄窗历史覆盖后的后台读取和待发送拖动问题。Claude91 已排队在独立 worktree 从该候选继续，Root 将完成复验和集成。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42883444412) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42883444505)

## 2026-11-10 19:15 UTC · 上一远端 Desktop CI 终态

远端 `693e7ea4` 的 Desktop CI 于 19:13:06 UTC 结束，6 个作业全部到终态。Linux Desktop 2195/2195、两项 Linux 打包、Windows CPU 1505/1505 与 Windows 原生内容均通过。Windows 原生 6/6、零跳过，PDF 完成 20/20 轮与 160/160 张截图，第 20 轮重新准备第一页的像素证据已上传。PDF 最长捕获启动 112 ms，两个视频均通过。上一轮 PDF 捕获超时本次未复现。唯一失败是 macOS 依赖安装时下载 fmt 补丁返回 HTTP 429，该作业的构建、CPU、Metal 和原生验收均跳过。同一源码头的 Runtime 13/13、Secret scan 与 Pages 均通过。下一批待发布源码含 `a9cefe9e` 的 Windows 捕获诊断与 `37e22f6a` 之前已记录的双端界面交付。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130049729774) · [macOS 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021209994) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42870793242)

## 2026-11-10 19:11 UTC · 双端结果来源详情与弹窗焦点

`222b15e6` 在原生聚焦结果页提供「来源」。详情读取 Viewer 已接受的配置和具体显示步号，展示任务的连接、节点、运行工作区和任务 ID，或本地文件、目录和载荷标签。任务图只展示已知绑定；确切产物路径取决于求值回执。长值可滚动，控制字符按可见转义呈现。Esc 与关闭按钮把焦点归还给来源入口。窗口路由隔离弹窗下方的指针、键盘和文件拖放。Jobs 54/54、UI 131/131、窗口 88/88，零跳过。

Linux X11 英文 1600×1100、中文 680×1000、缩放 1。固定起点为聚焦结果页，真实本地 Runtime 合成任务第 7 步已显示，原任务保有草稿。两端打开来源各 1 次点击。英文 Tab 后 Esc 关闭，中文点关闭 1 次。两端按 Enter 从归还的焦点重开，再按 Esc。弹窗期间注入滚轮，英文另测 Ctrl+Space 和小键盘 1。关闭前后画布区域逐像素一致，英文小键盘 1 在关闭后能改变画布，证明快捷键实际生效。含准备与任务返回全路线 8/9 次点击。保持原任务、日志与草稿。打开和关闭无服务读取、重复计算、模型调用或 Runtime 写入。收据在外部目录 `root-delivery-20261110-135/native-source-window/window-final-*`，二进制 SHA256 为 `8d7ef36927914c9caabc603bd99a8bbed5706daf1b5c9bcd0834d7b88e3cbf72`。

`e3e69af9` 集成实际 Claude89 `9483afc3`。Web「来源」分行展示节点、项目、任务名称与完整 ID，并区分当前显示和待加载文件。图谱在各自面板绑定来源。结果正文里的长摘要限制行数，完整值在可滚动详情中可用。Tab 离开、打开历史或切页会收起详情，Esc 和明确关闭归还焦点；离开字段时清理该字段自动选中的文本。Root 整合版 Chromium 103/103，零跳过。

中文 Chromium 1440×900 与 390×844，模拟 Hub。固定起点为已选合成任务、已载入一个结果文件并改选另一个的结果页。任务打开结果 1 次点击，详情打开和关闭各 1 次。测试完整已显示与待加载路径、不可见字符、超长名称、键盘 Tab 和 Esc、窄屏历史、40 px 滚动偏移、Viewer 像素与任务日志。独立的来源打开/关闭测量期间零 API 请求和剪贴板调用。请求、点击和截图收据在外部目录 `root-delivery-20261110-135/web-source-reviewed/playwright`。

远端 `693e7ea4` Runtime 13/13，Linux Desktop 2195/2195 和两个 Linux 打包作业通过。Windows CPU 1505/1505，逐项确认上一轮的六项默认窗口快照已通过，必测 Python 校验匹配 1197 项。macOS fmt 下载 HTTP 429 在构建前失败。截至本记录，Desktop 仍在运行，Windows 原生内容是唯一进行中的作业。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [Windows CPU 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021210081) · [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130049729774)

## 2026-11-10 18:43 UTC · 窄窗结果取景与 Web 结果来源

`4e4bf6e9` 在聚焦任务明确打开新结果时为窄窗的默认预设首次取景，依据当前视口使用已发布的 View All 计算。作者数值相机、非默认缩放、工作区相机和显式预设沿用原优先级。原生交互分类图例加对比底色，导出图像沿用原图例绘制。Jobs 53/53、相机 10/10，OpenGL 与 Vulkan 各 5 个 Viewer 验收组均通过。定向 GPU 回归确认交互图像出现底色、相同相机的导出像素一致。

Linux X11 固定起点为已选公开合成 Runtime 任务的聚焦任务页，比例 1。英文 1600×1100 与中文 680×1000，各 5 次设置点击、一次输入和 Return。各 1 次点击打开第 7 步结果，1 次返回任务，选中任务、日志和表单草稿保留。窄窗在 632×884 画布内左右留 32、19 像素，四个图例标签可读；旧版初开边距均为 0，需额外点击一次「全部显示」取得相同取景。英文宽窗模型区 1124448 像素与基线一致。另测一次中键旋转后 Tasks→Results，画布逐像素一致。中文另测 680×1000→1600×1100→680×1000 两次调整尺寸，零额外点击，恢复后完整截图逐字节一致。返回与尺寸往返未新增 graph.evaluate，各路线均无模型调用或 Runtime 写入。原始收据在外部目录 `root-delivery-20261110-134/task-result-framing` 与 `task-result-framing-resize`，二进制 SHA256 为 `59b2ac19ab448bad62f024b4adc6328e890b7cf7af5b48b859d35c7510beed48`。

`9d8891c4` 集成实际 Claude88 `625ce3c2`（独立测试 95/95）。Web 结果页显示所选任务的节点、项目与名称，以及 Viewer 当前显示的文件。选中另一文件时保留旧画面及其来源，明确加载成功后才更换。探针、构建回执、错误与复核提示按已显示场景或有效请求绑定；过期的排队轮询停止，认证错误仍断开会话。回执携带来源时核对任务和文件，兼容无来源字段的旧回执。任务日志与文件、图谱探针分别保留。进入另一种结果模式清除原图谱的探针输出。Root 集成版 Chromium 99/99，零跳过。

Web 固定起点为中文模拟 Hub 已选合成任务的任务页，1440×900 与 390×844。每端从任务页打开结果各 1 次点击，编辑文件选择使用程序化下拉。在待加载、历史切页和范围变更路线检查画布位置与原结果，并用迟到成功、HTTP 502、来源不符与旧版无来源回执验证状态。明示的加载和探针通过现有 Hub 操作，切页无模型调用或修改。图谱与文件模式之间的画布重建、超长待选路径的完整窄屏查看仍需后续验收。截图与请求收据位于外部目录 `root-delivery-20261110-134/web-result-final/playwright`。

远端 `693e7ea4` Runtime 13/13，Secret scan、Pages 及两个 Linux 打包作业均通过。Linux Desktop 2195/2195，逐项确认上一轮 6 个默认窗口和 2 个任务页快照修复。macOS 作业 130021209994 因依赖 fmt 补丁下载 HTTP 429 在构建前失败。截至本记录，Desktop 仍在运行，Windows CPU 测试进行中，原生内容作业待该构建包。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [Linux 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021210004) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42870793242)

## 2026-11-10 18:22 UTC · 聚焦任务结果、Web 队列和平台诊断

`e210227d` 从原生聚焦任务页直接打开所选任务的结果，复用该窗口的 Viewer 与一级导航。回调核对窗口、编辑器、连接、节点、工作区和任务身份及代次。激活成功才打开结果，较早排队的打开请求由当前点击取代。传统分栏仍使用原入口。Jobs 53/53，新增回归覆盖创建工作区期间失效的请求及打开结果的顺序。项目导航回归 36/36，零跳过。

Linux X11，英文 1600×1100、中文 680×1000，比例 1。固定起点为聚焦任务页、选中真实本地 Runtime 上已完成的公开合成任务，展开新建表单并保有草稿。5 次设置点击，加一次文本输入和 Return。点击所选结果、返回任务各 1 次。结果显示精确任务与第 7 步，返回保留选中项、日志和草稿。额外英文宽窗将实际结果回执延迟到返回后，完成前后任务页截图逐字节一致。3 条路线均无模型调用或修改请求，Runtime 工作区、任务和产物校验不变。窄屏 Viewer 可见同一结果，但模型两侧裁切、部分图例覆盖网格。原始收据在外部目录 `root-delivery-20261110-133/tasks-results-window-reviewed`，二进制 SHA256 为 `807c20c9c417597936b9cc329eaadf82db77bd5a7778c228537ce3ea88f76f68`。

`2de31dc0` 集成独立 Claude87 末版 `4ad74e25`。Web 任务页先显示队列、已选任务、快捷操作和待复核项，运行环境与新建任务收进详情。运行环境首次展开便于选节点，手动折叠随页面切换保留。Root 加入独立滚动上限，200 条任务仍可看到已选任务状态及运行环境入口。提交与审批沿用现有明确操作，任务、TaskSpec 草稿和 Viewer 在切页时保留。构建与整合版浏览器回归 87/87，零跳过。

Chromium 模拟 Hub，中文 1440×900 与 390×844。已进入选定工作区的任务页直接看到队列，新建任务及手动折叠后的运行环境各 1 次点击展开。完整短队列测量路线中，从已连接的新页面出发 5 次点击另有 2 次程序化下拉选择，已选任务复查 7 次点击，断开与恢复路线 3 次点击。测量包含各自的展开、切页和复查步骤，未调用模型。200 条合成任务的补充路线验证首条单击、尾条可获焦及无写入。JSON 计数和截图在外部目录 `root-delivery-20261110-133/web-queue-integrated/playwright-full`。

`a9cefe9e` 合入隔离 Windows 捕获诊断 `d41795d5`，分别记录 CreateForWindow 的原始调用、HRESULT 转换和退出清理耗时。旧聚合字段、输出上限及验收规则保留。便携计时夹具及证据门 12/12 通过，Windows SDK 构建与实际捕获仍待目标 CI。本轮本地待发提交与远端 `693e7ea4` 分开记录。截至本记录，Desktop 仍在运行，Runtime 仍在运行，13 个作业中 11 个已通过。macOS 作业 130021209994 在 vcpkg 下载 fmt 补丁时多次返回 HTTP 429，配置、构建、CPU、Metal 和原生验收均跳过。Secret scan 与 Pages 通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [macOS 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021209994) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42870793242)

## 2026-11-10 18:00 UTC · 原生智能体会话历史与 Desktop 门禁

`9bc9b771` 将原生工作台历史分成普通问答和智能体会话。工作台、任务与结果共用入口，按对应账本的精确 ID 读取。相同 ID 文本、迟到的读取回执和旧窗口回调由定向回归覆盖。读取失败可点击同一条记录重试，已有发送或待确认回执时禁用历史选择。Root 在独立 worktree 的 Claude86 修订 `dd91cf9f` 上整合界面、同条重试与导航回归。Claude 的控制器定向 20/20 通过，旧基线全量 2159/2167，8 项为已定位的旧布局快照。Root 整合版原生定向 82/82 通过，零跳过。

Linux 实窗固定起点为已打开合成项目、已选任务并保有普通问答与智能体草稿。英文 1600×1100 与中文 680×1000，缩放 1。分别从任务页打开 Agent Alpha、从结果页打开 Agent Bravo，宽屏各 1 点击，窄屏各 2 点击（历史、会话行）。普通问答返回同为 1/2 点击。各次只读对应记录，保留两种草稿。Viewer 回到公开样例第 1000 步，中文画布像素一致，英文差异限于中心体积着色。含设置、切页和复查共 11/15 次点击，每端各输入两次草稿。项目 SQLite 和 Runtime 任务与工作区相同，无模型请求、运行启动、目标修改或项目写入。截图与点击收据位于外部目录 `root-delivery-20261110-132/agent-rail-window`，二进制 SHA256 为 `db0321707bf0d9c945d57303c1da6e44459b6a8fd78a422dd073c7843be2880c`。

上一远端源码头 `79ea12f4` 的 Desktop CI 于 17:54:33 UTC 全部结束，6 个作业中 2 个打包通过、4 个失败。Linux 2174/2182、macOS CPU 1547/1553、Windows CPU 1487/1493，失败分别为 Linux 6 个窗口与 2 个任务快照、macOS 与 Windows 各 6 个相同窗口快照。本地 `15a5830a` 与 `bb812b60` 修正对应快照，定向通过 51/51 与 88/88。macOS 的 Metal 原来随 CPU 失败跳过，导致报告检查缺少 XML。`dc48679b` 在成功构建后独立运行 Metal，保留已有 CPU、Metal 与报告校验失败判据。Runtime 13/13，Secret Scanning 和 Pages 均通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

同一轮 macOS 原生内容 4/6，MP4 隐藏保持与 HTML video 首次明确暂停的时钟超差。可选隐藏探针 0/2，帧时钟探针 1/2。`0c239b42` 调整可选诊断，下一轮实机待验。Windows 原生内容 5/6，PDF 第 20 轮重新准备第一页时捕获启动失败。序列 433 的 `capture.create-for-window` 返回 `0x8007041d`，启动调用总耗时 120059 ms，像素验收随之超时。PDF 19/20 轮完成，两个视频通过。原生内容均零跳过。本地 Linux 回归和实窗完成，macOS 和 Windows 原生结果仍需按新源码头确认。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/129975239887) · [Windows 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/130004878783)

## 2026-11-10 17:25 UTC · Web 会话历史与原生智能体读取保护

`1bc557e6` 集成实际 Claude84 `86671b81`、Claude85 冻结修订 `d5ce6399` 和隔离修正 `5ae21b15`。工作台、任务、结果都能打开只读历史，按会话保留本页草稿。新会话由首次明确发送写入，缺失会话可移出草稿。两种历史与发送回执顺序按消息 ID 合并。结果不明确时，本页先按原 ID 重试，再发送新草稿。Root Web 构建与 74/74 回归通过。Claude85 最后在独立 worktree 以 `51bea8f1` 结束，它独立覆盖了反向回执顺序，整合版的同一行为与缺失、重试保护均有对应回归。跨设备重试仍沿用 Hub 当时的会话上下文，未保存草稿和待重试 ID 存于当前页面。

`8424b230` 集成 `f5f345a9` 的可选 Hub 标题查询。默认名称用首条已保存问题的短标题，显式名称优先。旧版 Hub 沿用原名称。单条查询内读取，保留旧列表字段、权限和排序。整合后 Web 75/75、Hub 53/53，零跳过。

Chromium 153.0.8010.12，中文、比例 1，宽屏 1440×900，窄屏 390×844。两端固定起点为已选合成任务的任务页或结果页。各先用 7 次设置点击载入同一公开合成 Viewer 场景，探针 X=0.25，保留 TaskSpec 草稿。从两页分别选原会话，宽屏各 1 点击，窄屏各 2 点击。新对话打开本地草稿的点击数也为 1 和 2。含返回、复查和额外焦点检查，宽屏 8 次测量点击，窄屏 13 次与 1 次 Escape，各输入一次本地草稿。窄屏 Escape 焦点回到历史按钮。返回后任务选择、表单草稿、滚动位置、Viewer canvas 实例与图像像素一致。两条路线只读取对应的历史，测量期间无写入、无外部请求或模型。证据在外部目录 `root-delivery-20261110-131` 的 `web-window-proof/integrated-module/browser-artifacts`、`web-title-test.log`、`hub-title.xml`。

`c229a3ae` 在原生 AI 会话页确认选中的智能体会话读回后，才启用发送与设置运行目标。控件回调再次核对身份，读取中或缺失时可继续保留草稿。固定起点为已打开合成项目的会话页，严格桥接夹具设置待确认的会话 ID，覆盖读取中及服务返回缺失后的禁用与回调，定向回归 36/36。此处为控件验证，指针点击路线沿用之前实窗。实际 Claude86 已从 `fad1d757` 在独立 worktree 开始修复读取代次，原生侧栏接入智能体会话仍待该修订与集成。

远端 `79ea12f4` 的 Runtime 13/13 通过。Desktop 的 Linux 作业完成，共 2182 项，2174 过、8 失败、零跳过。逐项确认 6 个默认窗口与 2 个普通任务布局快照，分别对应本地 `bb812b60` 与 `15a5830a` 修正。两个 Linux 打包作业通过，整轮 Desktop 仍在运行，本批留在本地等待门禁。PR #53/#54 维持旧冲突补丁与旧交接状态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Linux 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/129975240714) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 17:09 UTC · 聚焦任务队列与回归基准

`fad1d757` 把聚焦任务页的队列放在上方。当前连接、节点和工作区显示在运行环境标题中，展开后使用原配置。新建任务按需展开，提交和重试由表单中的明确按钮触发。任务详情、取消确认和原有分栏入口仍可用。

扩大套件后，发现此前导航变更遗漏了普通任务页和默认窗口的 JSON 快照。`15a5830a` 与 `bb812b60` 集成 `feabc7a0` 和 `902a414c`，更新 8 份经旧基线复现的快照。结构差异是顶部工作台入口与零尺寸导航区域，普通任务页原控件、既有区域尺寸和其余块经结构化比较一致。Root Jobs 51/51、窗口管理 88/88、工作台与工作区 54/54，零跳过。独立 OpenGL、Vulkan、属性表单和 Viewer 图像对照通过，保留原图像基准。

Linux X11/OpenGL，比例 1，英文 1600×1100 与中文 680×1000。固定起点是由相同四区布局进入的任务页，已选合成 Runtime 工作区。首条已完成任务在两端均上移 483 像素，从该起点零点击可见。运行环境和新建任务各 1 点击展开，任务行 1 点击读取原日志。每端 2 次设置点击，11 次测量点击，另输入一次未提交任务名，零滚轮、快捷键或缩放。切到结果再回任务保留草稿，返回分栏恢复普通任务布局。Viewer 仍显示公开样例第 1000 步，两次渲染的中心体积着色存在细微差异。两端无提交、取消、创建工作区、保存或模型调用。进程内调度器在测量前完成合成任务，画面仍显示运行守护进程未运行。未连接的同尺寸窗口另各用 2 次设置和 3 次测量点击，表单的提交禁用。证据见外部目录 `root-delivery-20261110-130` 的 `tasks-jobs-final.xml`、`wm-final.xml`、`tasks-project.xml` 与 `tasks-window-proof`。新界面的 macOS 与 Windows 实窗待验证。

`0c239b42` 集成 `9951a89b`，用现有两个可选 Cocoa CI 槽位观察原片首次真实工具栏暂停。请求前等待 270–290 ms，记录原生派发与分段 DOM 读数。原强制 6 项、20 轮和断言保持。Linux 对象、4 组条件编译及原生 AX CPU 1/1 通过，实际 Cocoa 结论等待对应平台。

远端 `79ea12f4` 的 Desktop 仍运行，两个 Linux 打包作业已过。Runtime 已有 11 个作业成功，整轮仍运行。本批代码已提交到本地，待上一 Desktop 整轮终态再推送。PR #53 仍冲突，#54 仍是旧交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 16:52 UTC · 原生近期问答导航

`159a21a6` 集成 `e88fd9f6` 的原生只读近期问答缓存及导航。支持当前项目和新桥接口时，宽屏左栏显示最近保存的未归档问答，窄窗用历史菜单。从任务、结果或工作台选择即打开原问答。列表变化时旧弹出菜单关闭。同项目打开期间共享一次在途读取，旧项目回执不能替换当前列表。Root 定向原生回归 62/62，零跳过，覆盖归档更新、旧回执与原编辑器复用。

Linux X11/OpenGL，比例 1，英文 1600×1100 和中文 680×1000。固定任务页与结果页均已打开同一合成项目，含一条待处理和一条已完成问答，并预先输入草稿。英文两条路径各用 1 次点击，中文各用 2 次点击，先打开历史再选对应问题。另有 6 次设置、切页与回到结果的点击，每端各输入一次草稿，零键盘快捷键、滚轮或缩放。核对精确问题、保存来源、已完成回复和草稿。两端返回结果后，公开 `example.stkp` 第 1000 步的Viewer 画布逐像素一致。项目数据库字节一致，无任务、工作区、写入、发送或模型启动。较长标题在宽栏截短，悬停可读完整标签。新界面的 macOS 与 Windows 实窗待验证。证据见 `root-delivery-20261110-129/rail-native.xml` 与 `rail-window-proof/window-{en-wide,zh-narrow}/window-receipt.json`。

前一批已推送 `79ea12f4`。推送前核对 `3c4f9bf9` 整轮终态，Desktop 5/6 作业通过。Linux 2177/2177、Windows CPU 1488/1488、Windows 原生 6/6。macOS 原生 4/6，首次可见暂停失败见上一节。`79ea12f4` 的 Secret scan 与文档部署通过，Desktop 仍运行，Runtime 排队。本节的近期问答提交仅在本地，待 `79ea12f4` 的 Desktop 整轮终态后推送。PR #53/#54 的原头分别为旧冲突补丁与旧交接，均未集成。 [新头 Desktop](https://github.com/sijintech/stk/actions/runs/42857730640) · [新头 Runtime](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 16:43 UTC · 上一远端头 Desktop 终态

远端 `3c4f9bf9` 的 Desktop 于 16:43:32 UTC 整轮结束，6 个作业均到终态。Linux 三个作业、Windows CPU 与 Windows 原生通过，macOS 原生必验失败。macOS CPU 1548/1548、Metal 254/254。原生必验 4/6，MP4 与 HTML 均在首次可见暂停低于 0.05 秒下限。两份 270–290 ms 被动延迟对照均在观察窗口内取得稳定暂停。Runtime 13/13 已通过。本次终态满足推送前提，随后推送截至 `4442342e` 的已验证批次及本记录。新头的桌面平台验证以其自身 CI 为准。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42845291750) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42845291916) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42845291750/artifacts/13783327194)

## 2026-11-10 16:38 UTC · 聚焦会话详情与精确问答返回

`a8d80a9a` 将原生聚焦工作台的数据范围与模型设置收在按需展开面板。问答和输入框优先显示。空项目入口使用按文字内容计算的按钮宽度。`6e18a3b1` 集成候选 `1338781b`，从项目首页的问答提醒读取对应请求，保留未发送草稿与新问题的数据范围。“已查看”由独立按钮处理。Root 原生集成回归 53/53，零跳过。

`1fa0baec` 集成 `f2c721cf` 的本地只读 Bridge `project.requests.recent`。接口按保存顺序从新到旧返回未归档问答，默认 8 条，最多 20 条。旧列表仍按原顺序分页。Root Bridge、请求、归档、智能体与脚本回归 179/179，零跳过。原生侧栏接入仍在后续。

Linux X11/OpenGL，比例 1，英文 1600×1100 和中文 680×1000。会话验证先用 2 次点击打开合成项目并进入工作台，固定起点已显示一条原问答。各用 5 次点击展开和收起数据与模型、聚焦输入框、进入结果并返回，另输入一次草稿。返回后同一原问答、草稿与折叠状态仍可见，结果页显示公开样例第 1000 步。中文窄屏展开面板后需要滚动查看输入框下缘。

精确返回固定起点为已打开同一合成项目的首页，含待处理和已完成两条问答。每端 7 次设置点击包含一次显式数据范围捕获，另输入一次草稿。固定起点后两次各 1 点击从对应提醒打开原问答，各 1 点击返回首页，共 4 次点击，零滚轮或快捷键。两端保留草稿，英文宽窗直接显示新问题范围仍为原数据，中文窄窗保留面板折叠。两端项目数据库字节、项目修订、提醒状态和消息摘要保持一致，实际方法观察中模型启动、发送、新建请求和标为已查看均为零。证据见外部目录 `root-delivery-20261110-128` 的 `attention-native.xml`、`recent-root.xml`、`window-proof/window-{en-wide,zh-narrow}/window-receipt.json` 及 `attention-window-proof/window-{en-wide,zh-narrow}/window-receipt.json`。macOS 与 Windows 的新布局实窗待验收。

远端 `3c4f9bf9` 的 Runtime 13/13 通过。Desktop 的 Linux 三个作业与 Windows CPU 通过，macOS CPU 1548/1548、Metal 254/254，强制原生 4/6。两个原片未完成首轮，在初次可见暂停检查中 DOM 时间降至 0.05 秒以下。独立的 270–290 ms 延迟诊断两源均取得原生暂停和观察窗口内稳定的 DOM 时间。Windows 原生作业仍运行，本批提交等待整轮终态。PR #53 与 #54 的原头仍分别为冲突与过期交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42845291750) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42845291916)

## 2026-11-10 16:19 UTC · 聚焦工作台收起技术页头

`7282342a` 将编辑器选择、技术标签和区域菜单移出原生聚焦工作台的页头。工作台保留首页与项目，任务保留提交与刷新，结果保留打开、叠加层、全部显示和导出。通过分栏视图恢复专业工具。原生定向回归 50/50，零跳过。

Linux X11/OpenGL，比例 1。固定起点为文件、Viewer、文献/Python 与项目表格四区，Viewer 已加载公开 `example.stkp`。英文 1600×1100 和中文 680×1000 各依次点工作台、任务、结果、工作台、分栏，合计 5 次点击，零键盘、滚轮或缩放。聚焦页头单行显示且操作按钮宽度正常。回到原区域几何与高级控件，结果仍为第 1000 步。两个流程的任务、工作区和项目修订增量均为零。页头操作通过画面与组件回归核对，本轮实点覆盖导航。外部证据目录 `root-delivery-20261110-127`，具名测试 `header-final-native.xml`，窗口收据 `window-proof/window-{en-wide,zh-narrow}-release/window-receipt.json`。macOS 与 Windows 实窗仍待验收。

上一远端头 `3c4f9bf9` 的 Runtime 13/13 作业成功。Desktop 当前 3 个 Linux 作业已通过，macOS 与 Windows CPU 仍运行，本批本地提交待整轮终态。PR #53 与 #54 仍是已核对的原头，前者冲突，后者为旧交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42845291750) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42845291916)

## 2026-11-10 16:10 UTC · 双端左栏、首次启动与只读会话历史

`67a6fd3f` 增加 Hub 只读会话历史。存在时返回原会话及消息，缺失返回 404，旧会话入口和显式发送兼容。Hub 定向 52/52。`82fc9d43` 集成 Claude82/83 的三页 Web 导航。结果和日志捷径一次显示对应内容，晚回执沿原任务更新，保留当前页和 Viewer。Root 构建与 Chromium/Node 全套 22/22。

`6a562d2e` 原生宽屏用左栏，700 逻辑像素及以下用横栏。保留当前项目名、显式分栏入口及原编辑器。

`1a3ef021` 无保存布局时打开工作台。聚焦布局重开保留当前页，显式 `--open` 在新工作台和已保存的聚焦工作台直接显示结果。旧普通最大化和显式分栏照原状态恢复。原生导航、工作模式、工作区和传输回归 50/50，零跳过。

Linux X11/OpenGL，比例 1，原生固定起点为文件、Viewer、文献与项目表格四区，Viewer 载入公开 `example.stkp`。英文 1600×1100 左栏和中文 680×1000 横栏各走工作台、任务、结果、工作台、分栏五次点击，零滚轮或键盘。英文任务页调整到 800×1000、680×1000、再回原宽度，选中任务页保持。结果步 1000 和原四区回到画面，任务、工作区和项目修订均为 0。窄分栏的 Viewer 图例重叠在起点与回程均可见。

另验六次启动，全部正常退出。英文新配置零点击进入工作台，一次点任务后保存，重开保持任务。对同一保存布局显式传入公开结果，零点击进入 Results 并显示第 1000 步。中文窄屏首次打开结果，无参数重开保留结果页和尺寸，需重新打开载荷。显式旧布局保留普通最大化，原布局文件不变。启动证据见 `startup-release/startup-receipt.json`。完整点击收据和截图在 `root-delivery-20261110-126/window-proof`，具名测试 XML 为 `startup-final.xml`。新界面的 macOS 与 Windows 实窗仍待对应环境验收。

远端 `3c4f9bf9` 的 [Runtime](https://github.com/sijintech/stk/actions/runs/42845291916) 已完成，13/13 作业通过。对应 [Desktop](https://github.com/sijintech/stk/actions/runs/42845291750) 整轮仍在运行。本批代码本地提交待门禁。PR #53 的重试主题已有更新主线实现，且原头冲突。#54 是过期交接候选。两者原头均未集成。

## 2026-11-10 15:42 UTC · 统一工作台首片验证

本地 `058b1555` 复用 AI、Jobs 和 Viewer。点工作台进入聚焦导航，依次显示工作台、任务、结果。分栏视图恢复原区域树。普通最大化和读取已保存布局沿用原入口。工作台导航已在原生顶部验证，左侧项目与会话导航、默认布局和按需详情仍为双端下一片。

原生工作区及模块回归 27/27，零跳过。新增检查实际结果载荷、Viewer 和会话编辑器复用、相机重置代次和原分栏。Linux X11/OpenGL 在 1600×1100 英文和 1000×1200 中文、比例 1 的固定文件/Viewer/文献/项目表格布局下，各点工作台、任务、结果、工作台、分栏视图，共 5 次，零滚轮和键盘。公开 `example.stkp` 回到 Viewer，任务数 0，项目修订 0。前一抓屏驱动继承终端输入并吞掉后续命令，已用隔离 stdin 的驱动重验两组。截图和输入收据在 `root-delivery-20261109-124/window-{en,zh}-focus-final`，具名 XML 在 `root-delivery-20261110-125/unified-native-final.xml`。

`3c4f9bf9` 已推送。对应 [Desktop](https://github.com/sijintech/stk/actions/runs/42845291750) 和 [Runtime](https://github.com/sijintech/stk/actions/runs/42845291916) 已启动。本地导航提交等待该 Desktop 整轮终态。

## 2026-11-10 15:30 UTC · 原生执行预检、CI 夹具与统一工作台方向

`9216d7cb` 在项目的材料仿真中增加默认折叠的执行环境检查。一次明确点击保存请求，再向所选 Runtime 提交单 CPU 诊断。面板可见时读取原任务，重开从本机记录恢复。晚回执按项目、连接、编辑器与父子面板代次核对。指南由实际 Claude80 的 `ae5a82e0` 经 root 审阅集成。 [桌面指南](mupro-desktop-preflight.md)

Linux 最初原生全量 943/944，唯一失败是展开的诊断控件把既有 Runs 入口推到裁剪范围外。改为默认折叠后，仿真、工作台与预检联测 28/28。最终窗口定时唤醒版本的七项预检及既有 MuFerro 提交回归 8/8、零跳过。两级面板折叠、折叠再展开的四个已完成回执用例均通过。

实际 Linux X11/OpenGL 使用 1600×1100 英文和 1000×1200 中文，比例 1。固定四区为文件、已加载公开示例的 Viewer、文献与项目表格，项目路径已填，已保存 Runtime 尚未选择。计时器修正前的两次路径各 6 次点击、5 格滚轮，从打开项目、展开材料仿真、选择运行环境、展开诊断到检查各经过实际输入。两次均创建一个工作区和一个任务，静止窗口留在已接受。最终计时器版本两次完整探索记录分别为 12 和 11 次点击，含导航调试，另各 17 格滚轮。从诊断已打开和目标已选的状态，两次均只点击一次检查，额外输入前已自动读到原任务。每组均一任务、一工作区、1 CPU、七项检查、`checks_incomplete`，项目修订均为 0。核对独立 worker PID、原任务与工作区 ID、实际截图。合成 SDK 与回环 Runtime 用于本次验收。真实 MuPRO、许可、SSH/集群调度和此面板的 macOS/Windows 窗口待验。证据目录 `root-delivery-20261109-124/window-{en,zh}-v8` 和 `root-delivery-20261110-125`。

`e5bfaa7f` 集成实际 Claude81 `ef3dfb05`。补齐跳过构造的测试夹具所需预检状态与锁，保留生产关闭逻辑。旧夹具本机 5 败、4 过。修复后作者三版本各 9/9，Python 3.12 联测 263/263。root 的关闭、journal、严格 RPC 联测 60/60。新头远端结果待验。

`cbe8d866` 的 [Desktop](https://github.com/sijintech/stk/actions/runs/42750023665) 于 04:41:14 UTC 终态，6 个作业全部结束、5 成功。Linux 2170/2170，Windows CPU 1488/1488、原生 6/6 且每项 20 轮，macOS CPU 1548/1548、Metal 254/254，强制原生 4/6。MP4 隐藏暂停失败，HTML 视频未在转换及自然结束前进入隐藏暂停。整轮终态满足本批推送门。 [Runtime](https://github.com/sijintech/stk/actions/runs/42750023868) 终态 8/13，五个矩阵均仅有同五项 transfer shutdown 旧夹具失败。Linux 3.11/3.14 各 6883 过、166 跳过、4 排除，3.12 为 6900 过、149 跳过、4 排除。Windows 两组各 5493 过、295 跳过、983 排除。Secret scan 和 Docs 成功。

## 2026-11-10 03:29 UTC · 诊断请求持久化、严格 Bridge 与前一 CI 终态

`5e377de0` 集成实际 Claude78 `81185683` 的共享预检客户端/未注册适配器，以及独立 `669b523b`、`f046d791` 的诊断 journal，并发布五个 Bridge 方法 describe/list/reserve/retry/refresh。记录在项目外持久化，固定原运行环境、工作区选择、资源和请求键。reserve 纯本机保存 prepared；原生调用方必须先得到持久确认，再在原视图仍有效时发送明确执行请求。丢 reserve 回执不会留下排队执行。重开、列出和刷新均不重提，未知回执只允许沿原 ID/原键明确恢复；已知任务 retry 零 POST。新工作区创建也使用稳定派生键。坏 journal 仅让预检不可用，不删除数据，不阻止其他 Bridge 模块启动。未增 Agent 工具、项目格式或放置权限。 [桌面诊断契约](specs/mupro-preflight-desktop-1.md)

`b7aa88fa` 集成实际 Claude79 `d00d3493` 的严格 stdio Bridge/真实 HTTP Runtime 回归。root 预检、CLI、journal 和 RPC 联测 254/254、零跳过。其中新 RPC 22 项含 SIGKILL 重开、工作区/任务已接受后挂起或丢答复、同键同体恢复、严格 Schema、冻结目标、失败检查产物、零自动回放和坏存储隔离；作者 Python 3.11 同组 22/22。root 另有协议定向 6/6、最终 hello 1/1，以及严格 NDJSON/两种 Schema validator 的 reservation/reopen/坏存储隔离实测。合成 worker PID、原 TaskSpec、产物摘要和环境脚本单次执行均核对；未验证真实 MuPRO、许可、SSH/调度站点或目标 OS 的新界面。

前远端 `37e48356` Desktop `42732315824` 于 2026-11-10 01:58:24 UTC 终态 failure，六个作业全部结束、四成功。Linux 主测 2170/2170、两个打包作业成功；Windows CPU 1488/1488、零跳过，工作区 18/18 和 guarded 7/7 全部具名通过，上一轮四项路径失败已恢复。macOS CPU 1548/1548、Metal 254/254，主原生仍 4/6；独立 Windows 原生实际 5/6，不能沿用前头全过。同头 Runtime `42732316049` 终态 13/13，Secret scan/文档部署成功。整轮结束满足本批已验证后端提交的推送前提；本节随本批交付，新的精确头 CI 结果待验。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42732315824) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42732316049)

本头 Windows 原生仅 PDF 失败：实际完成 7/20，第八轮 reprepared-page1 的捕获构造失败，阶段 capture.create-for-window、HRESULT 0x8007041d；启动及回退/释放混合段约 120,053 ms，尚无 poll 或采样，通用 45 秒结果期限正确拒绝晚结果，却不能抢占同步 COM 构造。其余五项各 20/20。捕获底层代码在前两头相同，当前证据不支持归为本批产品回归或单纯 runner 故障。Mac 原片 MP4 在隐藏暂停阶段失败，HTML 视频更早在初始显式暂停失败。新增 270 ms 可见对照两项有效：MP4 请求/实际派发 273.302/273.341 ms，HTML 275.847/275.898 ms，均在 270–290 ms，期间 DOM/OS 捕获计数未变。两次 DOM 各稳定在 0.470061750/0.344736125 秒，native 验证通过且资源活跃。它是有界对照证据，不能替代原强制门或认定原因已解决。

原生面板仍为未提交候选：root 增加独立 workspace 选择与事件/目标代次，直接调用 Bridge，不复用 Jobs 的选择或 Script 执行。独立真实回归已证明旧候选在折叠及折叠再展开、未绘制下一帧时会误发一次 retry；root 已补事件即时 panel epoch、原 ID 绑定及新建工作区自有选择，等待最终新 ABI 定向与真实窗口验收，不称界面已交付。当前无本地 CI 观察器，后续按同 run 的官方状态复读。实际 Claude80 已从 `b7aa88fa` 在独立 worktree 写一份用户指南，root 保留 UI/契约/集成/推送职责。PR #53/#54 头仍 c9f13994/2dd3e4ee，原冲突未合入。真实软件/研究参数、HDF5-only 完成、H2 和分析提案持久形式等待决保持。

本机证据 `root-delivery-20261109-123/`：`preflight-rpc-integrated.xml`、`bridge-protocol.xml`、`rpc-hello-final.xml`、`rpc-smoke-v2.log`；Claude78/79 实际交付在 `122/claude78/work/` 与 `123/claude79/work/`；journal 两批在 `preflight-journal-evidence/{receipt,reserve-receipt}.json`。首个 RPC smoke 缺 hello.protocol 的夹具失败保留为 `rpc-smoke.log`，修正后的 v2 才是通过。平台终态/具名 CPU/实际媒体观察在 `122/ci37/`，特别是 `windows-native-current-failure.json`、`macos-final-summary.json`、`target-helpers/cocoa-passive-delay-proof.json`。原生旧候选真实红例/新回归在 `preflight-native-tests-evidence/`，冻结归档绑定在 `native-green-archives/receipt.json`，不是已通过的目标 OS 验收。暂存均经过 diff 和 gitleaks，原七份未提交内容与当前原生 UI 工作均保留。

## 2026-11-10 01:32 UTC · 显式执行环境预检与原任务回执

本地 `8d3752ff` 与 `1c8c2dcf` 完成显式 Runtime 执行环境预检。客户端提交固定单 CPU、空输入及空环境覆盖的诊断任务，在 worker/调度环境使用该端自己的配置；不启动 MuPRO/MPI 或签出许可。`preflight-result` 只读原任务，按固定规格、连接、终态/退出码、唯一产物大小/SHA-256和严格内层格式核验。失败检查仍有 failed/1 的有效观察，取消、执行故障、错接规格与未知状态不冒充成功；丢提交答复只允许明确同键同请求重试，零自动重提。本机 `check` 原含义、运行/收集链及 Agent 权限保持。 [任务回执契约](specs/mupro-preflight-task-1.md)

实际 Claude77 `ae980be9` 在独立 worktree 交计算侧规格、观察器及测试。root 捕获 summary 数组/对象产生 TypeError 的解析缺口，两个实际红例后补字符串门。独立 `88fba9e1` 的 CLI 回归另证明旧候选会把别的工作区合法预检当本次提交/读取成功；root 增加提交答复和最终结果的原始规格绑定。三项 CLI 红例均实际失败，最终 31/31；夹具最初错误替换 os.environ 导致三个 worker 配置失败已单独保留，不作为产品反例。

root 最终联测 211 过、2 跳过；两跳过仍为真实 muFerro 样例条件及 Windows 目录联接。Python 3.11/3.14 的计算/本机观察各 111/111、CLI 各 31/31，零跳过。真实回环核对 worker PID、相反客户端配置、环境脚本单次执行、失败产物、冷客户端重读、同键恢复、取消和畸形回执。独立基础依赖 wheel 无 NumPy/h5py，实际安装控制台→HTTP Runtime→worker 的三配置均通过；重开客户端和同键重试保持同一任务/字节，三个任务仅采集三次。四个安装模块与当前主线源码摘要一致。该证据只覆盖本地 Linux 回环和合成前置条件，不是跨机 SSH、PBS/Slurm、真实软件或许可证明。

已推送远端 `37e48356`。截至 2026-11-10T01:31:10+00:00，同头 Runtime `42732316049` 已终态 13/13；Desktop `42732315824` 仍运行，Linux 主测 2170/2170，工作区 18 项及 guarded 7 项均具名通过，两个打包作业成功；macOS 和 Windows CPU 尚未终态。Secret scan、文档部署已成功。上述两个新的远端预检实现提交仅本地，等待 `37e48356` 整个 Desktop 终态后再推送。当前远端 CI 只含上一批本机预检和 UI/路径修正，不把它当新增远端诊断代码的验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42732315824) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42732316049)

实际 Claude78 已从冻结 `1c8c2dcf` 在独立 `claude/mupro-preflight-bridge-78` 接下一模块：共享纯客户端读取/提交逻辑及未注册的桌面 Bridge 适配器。root 负责方法注册/契约、原生仿真面板、目标切换/未知回执状态、最终回归和推送。该适配器与原生按钮尚未交付，不称桌面已可检查。新流程未做产品窗口点击验收；既有文献双布局 8→6 点击回执保持。真实 MuPRO 资产/科学参数、HDF5-only 完成证明、H2和分析提案持久形式仍按原待决；PR #53/#54 原冲突差异未合入，Cocoa 视频问题继续以原强制门禁验收。

本机证据 `root-delivery-20261109-122/`：`final312.xml`、`compute-{311,314}.xml`、`cli{311,314}.xml`、`installed-remote-receipt.json`、`verify-installed.py` 与独立 wheel；作者 `claude77/work/`，独立 CLI `preflight-cli-tests-evidence/receipt.json`。解析器首个 `parser-summary-red.xml` 为选择条件错误（93 排除、退出 5），实际两个红例是 `parser-summary-red-fixed-selection.xml`；不得混用。新头 CI 快照 `preflight-delivery-ci.json` 与 `ci37/`。原观察器 33897/6385 已无句柄且 PID 不存在；GitHub 运行状态由后续同 run 的显式官方复读确认，不将本地观察结束当 CI 结束。代码和文档暂存 diff/gitleaks 均通过，原七份未提交内容保留。

## 2026-11-10 00:57 UTC · MuPRO 本机预检与前一 Desktop 终态

`000bb6ff` 新增显式本机 `suan mupro check --json`，发布 `stk.mupro-preflight/1`：复用既有采集一次，输出固定检查项、保守总结、进程/组件版本与采集时间，排除路径和原始诊断。所有总结均保留软件版本未观察、许可未签出、求解器未运行。原 `python -m suan.mupro check` 诊断和退出码保持。命令会 source 已配置的受信任脚本，不能作为被动 health/graph.meta 读取或所选远端机器的就绪证明。

本机预检及旧链联测 87 过、2 跳过；跳过分别为真实 muFerro 样例条件和 Windows 目录联接，含新增 18 项。Python 3.11、3.14 各 18/18。独立 wheel 仅装基础依赖、无 NumPy/h5py，实际控制台三项观察均符合契约：脚本程序 incomplete/0、原生占位程序 passed/0、缺程序 failed/1。两个安装模块摘要与主线一致，受控夹具零求解器/MPI 调用。占位程序不是 MuPRO，不能据此认定软件身份、许可或科学结果。

实际 Claude74 的 `c124e58b` 经 root 修订为 `bd861dd0`，新增原生文献用户指南及入口链接，明确桥解释器与宿主解析/编码 worker 的环境可以分开配置。实际 Claude76 从冻结 `5fe4e6d7` 在独立 worktree 交 `98663411`，root 以 `e3b80fd8` 集成一份试点文档，核对 50 个本地链接，区分已实现的本机观察与拟议节点传递/读取器投影。 [试点说明](design/mupro-executor-pilot.md)

`5fe4e6d7` 修正 Windows 回归夹具的期望路径，使用词法规范化及 UTF-8 转换，并为新来源等待超时加入状态诊断；不改产品路径行为。旧头 Windows CPU 共 1488 项，1484 过、4 失败、零跳过。三项日志直接证明同一路径的分隔符比较错误；第四项同样使用该谓词并超时，旧回执不能证明其最终来源状态。本地相关 18/18，实际 Windows 修正结果待本批新头 CI。

`ae5090dc` 集成实际 Claude75 `239fc81e` 的可选原片时延对照：保持同一 seek/可见历史，只在 play 返回后普通非阻塞事件泵等待固定 270 ms，期间不作 DOM/媒体采样或 OS 截图。root 增补实际暂停请求和原生派发均落在 270–290 ms 的有效性门，超界保留原始观察但不计有效对照。原强制六项门禁、执行器及看门狗阈值不变。Linux 构建、探针开/关及 Linux/Apple 宏四种语法检查、相邻轮询 CTest 1/1 通过；两个夹具摘要未变。Apple 宏检查不是 Apple SDK 或 Cocoa 运行，目标结果待新 CI。

远端前头 `ba03ac8d` Desktop `42722834184` 于 2026-11-10 00:52:20 UTC 终态 failure，6 个作业全部结束、4 成功。Linux 主测 2169/2169、两个打包作业成功。Windows CPU 结果及修正见上；独立原生 6/6、零跳过，六源各 20/20 轮，PDF 八阶段各 20 次记录且 Viewer/草稿保护通过。macOS CPU 1547/1547、Metal 254/254，主原生仍 4/6。整轮终态满足本批推送前提。同头 Runtime 13/13：Linux 3.11/3.14 各 6634 过、166 跳过，3.12 为 6651 过、149 跳过，均另排除 4；Windows 3.11/3.12 各 5311 过、275 跳过、936 排除。原固定派发来源断言在三个 Linux 版本具名进度均通过。本节随已验证的文献单击打开、Python 面板回归、本机预检及修正提交交付，新的精确头 CI 仍待验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42722834184) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42722834173) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42722834184/artifacts/13724407825)

本头 HTML 原片的隐藏/可见配对均观察到 DOM 时间回到 0.102 秒，可见组原生已验证暂停；MP4 对照在初始显式暂停失败，不能当作完成了新鲜配对。独立帧号夹具两源均 no_clock_reset_observed，8 张 PNG 的摘要及帧号核验通过，但夹具与捕获时延共同变化，仍未解决原产品 4/6。本批 CLI 与诊断未新增产品 UI 交互，文献实际双布局 8→6 点击的既有验收保持。真实 MuPRO 主机/SDK/许可/研究参数、HDF5-only 完成证明、目标 OS 文献交互和分析提案持久形式仍待；H2 未代选。PR #53/#54 已重查，头仍为 c9f13994/2dd3e4ee，原冲突差异未合入。root 继续负责审阅、集成、推送和 CI，Claude 按独立 worktree 的限定任务配合。

本机证据 `root-delivery-20261109-121/`：预检三个版本 XML、`installed-receipt.json`、`windows-source-path-final.xml`、`cocoa-root-review/{syntax-receipt,structure-receipt}.json`、`native-poll.xml`、Claude75/76 固定交付；前头工件与终态在 `120/ci-ba03/{desktop-terminal,runtime-terminal,windows-native-final,windows-cpu-counts,macos-bounded-observations,frame-clock-verdict}.json`。每次暂存均经 diff 检查和 gitleaks 零发现。原七份未提交内容逐字保留。

## 2026-11-10 00:02 UTC · 文献命中单击打开与 Python 面板回归

本地 `26644456` 把文献检索命中明确标为“打开引用页”。一次点击按原引用身份顺序解析、渲染和显示精确高亮，仍可单独明确重试解析或渲染。临时连续读取绑定解析操作、页代次、查询/范围、桥进程与编辑器生命周期，失效或隐藏后不继续旧读取，重显不恢复操作。后端方法与写操作复核沿用已有契约。

原生便携文献测试 33/33。真实本地 PDFium/E5 资产回归最终 6/6、零跳过：两布局正向全链保留再次渲染、撤权同步清纹理及 Viewer/隐藏 Python 稿保护；已成功解析但挂起的 wire 回执在英文改查询、中文改范围、两布局隐藏重显后均零旧页渲染，重新明确搜索/打开仍校验真实 PNG 和高亮。这批测试集成 `4ed31a87`，120 个公开头文件、源码和独立归档摘要绑定经过 root 复核。

实际 Linux X11/OpenGL llvmpipe 窗口从默认英文 1600×1100、中文 1000×1200、scale 1 起步，各使用新预置的自有合成 PDF 资料库/索引和既有本地模型，Viewer 已显示公开网格。到引用页均为 6 次点击、零滚轮，原为 8 次；从已有搜索命中到页图均由 3 次降为 1 次。随后撤权并返回另 5 次，清稿退出另 1 次，总计各 12 次。引用/来源摘要、PNG、30 个高亮、实际像素、撤权清页及 Viewer 像素相等均核验。完整真实资产 CPU 导入至历史链两布局各从 37 降至 35 次点击。英文页底仍受原视口裁切，不宣称完整页展示；目标 macOS/Windows 新交互待验。

`17685b5a` 选择集成实际 Claude73 `e6a01cca` 的 Python 面板回归：真实严格 Bridge、图 worker 与 AppShell 主线程操作验证候选失败保留 A 草稿、错误返回和恢复字节后明确重开 B。root 去掉“首次轮询必须尚未完成”的竞态假设，仍核对每次观察的打开身份与对应来源状态。root 当前定向 4/4；作者原候选在基线 `6333178e` 完整项目测试 939/939。不把作者旧基线全测当本批全部回归；该合成执行链未涉及许可求解器，Windows 科学依赖条件仍排除该用例。

已推送远端 `ba03ac8d`，包含 `6333178e` Viewer 保护与 `83302698` Runtime 旧断言修正。截至 2026-11-10T00:00:46+00:00，新 Desktop `42722834184` 仍运行，两个 Linux 打包作业成功；Runtime `42722834173` 已有 10/13 作业成功，其余矩阵仍运行，暂无失败。Secret scan 和文档部署已成功。上述新文献与面板回归提交仅在本地，等待 `ba03ac8d` 的整个 Desktop 终态后再推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42722834184) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42722834173)

实际 Claude74 已从冻结 `17685b5a` 在独立 `claude/literature-guide-74` 编写文献桌面使用指南，仅新指南文件；待 root 审阅。root 继续负责公共实现、验收、集成和推送。PR #53/#54 仍为 c9f13994/2dd3e4ee，旧冲突差异未合入；原路线和 MuPRO 实际许可/科学参数等剩余条件继续保留。

本机证据 `120/literature-portable.xml`、`literature-real.xml`（原正向）、`literature-tests-build/real-assets-fixed.xml` 与 `final-receipt.json`（最终六项）、`window-{en,zh}-v2/literature-window-proof.json`、`window-events.json`、截图及 `window-source-binding.json`。首轮窗口起点在首帧前而为黑图，已保留原 `window-{en,zh}/` 失败；第二轮等待连续稳定首帧再量测，未改产品或点击数。新增负向夹具首轮缺 encoder.info 的前置失败也单独保留，未宣称产品反例。面板回归 `script-viewer-root.xml`，实际 Claude73 证据 `119/claude73/SUMMARY.md`；当前 CI 证据 `120/ci-ba03/`。源码及交付暂存 gitleaks 零发现，原七份未提交内容保留。

## 2026-11-09 23:44 UTC · 前一 Desktop 终态与 Cocoa 帧号回执

远端 `5cb7cdb9` Desktop `42712877920` 于 23:39:58 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2162/2162，两个打包作业成功；Windows CPU 1481/1481，独立原生 6/6 且每项 20/20 轮、零跳过。macOS CPU 1540/1540、Metal 254/254，主原生 4/6。整轮终态满足本批推送前提。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42712877920/artifacts/13720252143)

本头旧 MP4 首次暂停从 0.356866 到 0.366517 秒，下界通过；约 95 毫秒的 hold 后回到 0.234 秒，仅时间差上界失败，native 查询尚无回答。HTML 隐藏暂停从 0.214776 回到 0.102 秒，下界失败。这些是本头阶段，不能沿用更早头的 MP4 初始暂停失败描述。

新帧号诊断两项均通过，四张必需裁剪图/源共八图经过 ZIP、摘要及独立 PNG 帧号重读核验。MP4 可见播放帧 2→3、暂停 4/4；HTML 播放 1→2、暂停 2/2。最终两次 DOM 分别稳定在 0.4069555、0.353200833 秒，两源均为 `no_clock_reset_observed`。root 已独立查看两源的最后播放和暂停截图。此控制同时采用独立夹具和约 269/268 毫秒的播放捕获延后；DOM 比较使用更早的播放快照，不能排除未捕获间隙，更不能据此称原失败原因已解决。实际产品门禁继续为 4/6。

本批推送包含已本地验证的 `6333178e` Viewer 失败保护与 `83302698` 固定派发来源证明断言修正。同头 Runtime 的 10/13 终态及旧断言失败已记录于上一节；修正后的三版本结果仍待下一远端头验证。实际 Claude73 在独立 worktree 补 Python 面板集成回归。root 同时开发文献命中单击打开，现有真实资产回归中两布局各由 37 降为 35 次点击，命中至页图 3→1；窗口验证和迟到回复回归仍在进行，产品改动尚未提交。

本机证据 `118/ci5cb/desktop-terminal.json`、`frame-clock-verdict.json`、`frame-clock-review-index.json`、`windows-cpu/summary.json`、`windows-summary.jsonl` 与 `windows/receipt.json`。Windows 三项新增/相关 Viewer 状态回归有直接具名 JUnit；GPU 结果仅在适用平台说明，未把 Windows GPU 缺席当通过。

## 2026-11-09 23:23 UTC · 受约束打开保留 Viewer 与草稿

本地 `6333178e` 在已有 Viewer 时先验证带 `source_proof` 的候选来源，成功后才替换。失败、取消或被新操作取代时保留旧来源、画面、相机和未提交参数，自动求值与播放暂停。候选提交直接采用已解码帧，不再发起一次求值。格式错误的新打开在同步校验阶段拒绝，不取消已接受候选。

原生状态与 Python facade 增补可选 `opening` 请求身份和状态。`wait()` 只跟随等待开始时的同一候选，允许成功时切换来源；失败即返回，即使旧来源仍有未提交草稿。取消、替换或其他来源变化会中止等待。无此字段的旧桌面保留既有行为。说明已同步到 Viewer 指南与桌面 Bridge v1 增补。

集成实际 Claude72 `c8286623` 的真实严格 Python Bridge、图 worker 与离屏 GPU 回归，以及 `5be16fc5` 的已完成 Future 延迟回调测试、`3a9217e0` 的等待回归。root 追加同步拒绝不取消候选，并修正未加载翻译目录时错误原因丢失的问题。最终原生工作区 18/18、既有 Viewer 状态及表单 31/31；Vulkan、OpenGL 各 6/6，具名 GTest XML 均包含新用例。Python 3.12 联测 50/50，3.11 与 3.14 定向各 21/21，零跳过。暂存差异和 gitleaks 检查通过。

`83302698` 更新 MuFerro 固定派发测试，核对传入的完整来源证明。相关文件单独 30/30，最终已包含在上述联测。远端 `5cb7cdb9` Runtime `42712878022` 终态为 10/13 成功；三个 Linux 作业均仅在这一旧断言失败。3.11/3.14 各 6618 过、166 跳过，3.12 为 6635 过、149 跳过；均另有 1 失败和 4 排除。两个 Windows 客户端各 5296 过、275 跳过、936 排除。本地修正仍需下一远端头复验。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42712878022)

截至 2026-11-09T23:22:58+00:00，同头 Desktop `42712877920` 仍运行，4/6 作业成功。Linux 主测 2162/2162、两个打包作业与 Windows CPU 已成功；macOS CPU、Metal 及构建已通过，主原生步骤失败后仍继续诊断，新增帧号结果待工件。独立 Windows 原生仍运行。本地新提交尚未推送，继续等待整轮 Desktop 终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920)

实际 Claude73 已从冻结 `6333178e` 在独立 worktree 接 `CL-MUPRO-GUARDED-SCRIPT-73`，仅补 `script_test.cc` 的真实 Python 面板到原生 UI 操作验证；候选待交付与 root 审阅。root 继续负责实现、公共契约、集成、回归、推送和 CI。

本批 GPU 使用 Linux llvmpipe 与合成目录，不是目标 OS 窗口或真实许可 MuPRO 算例。程序入口和状态机验证未测用户窗口点击次数。实际许可、目标平台窗口与后续试点仍按原计划验收。PR #53/#54 头保持 c9f13994/2dd3e4ee，未合入旧 worker 语义或冲突交接路径。

本机证据 `root-delivery-20261109-119/validation-receipt.json`、`workspace-final.xml`、`viewer-cpu-final.xml`、`native-real-cases/`、`python-viewer-{final,311,314}.xml`、`native-real-before-error-fix.log`；Claude72 的原始十次反例与完整控制见 `118/claude72/`。CI 证据 `118/ci5cb/runtime-terminal.json`、`runtime-matrix-totals.json`、`linux-gpu-source-proof.json` 与 `latest.json`。远端 Linux GPU 的成功 CTest 输出被截断，新增用例执行由精确源码清单、无 filter 和零跳过规则推断；本机两个后端另有直接具名 GTest XML，不混作远端具名证据。

## 2026-11-09 22:32 UTC · Cocoa 帧号诊断与前一 Desktop 终态

远端 `5cb7cdb9` 已推送，新 Desktop `42712877920` 与 Runtime `42712878022` 已启动。新查看来源校验、探针代次和帧编号诊断的目标平台结果随这两个精确头回执核对。 [当前 Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920) · [当前 Runtime CI](https://github.com/sijintech/stk/actions/runs/42712878022)

`dbc0ebbb` 集成 Claude71 最终 `0d0de6a1` 的独立合成帧编号视频和可选 Cocoa 诊断。先取得两张递增的播放画面，再取得两张相同帧号的暂停画面，并记录已有 DOM 采样。root 补充了历史 DOM 时间回退判据，以及结论所用四张截图的持久化和摘要核对。缺少必要截图或时间证据时报告不确定。独立 MP4 与 HTML 嵌入视频两项诊断已接入 macOS CI，保存具名 JUnit 和裁剪截图。

最终新视频 44,339 字节，SHA-256 `c2bbcb873b7628c22b512051443adde6ff2e6c8688c6d84f0307d6bab2a34eef`。60 帧、10 fps、六种缩放与关键帧 [0,30] 均验证。精确 C++ 逻辑通过 1080 次解码位置、16 项分类、12 项审计和 5 项记录失败检查。真实 PNG 编解码及最终路径冲突证明无法用较早截图替代丢失的必需截图。Linux 编译、普通及 Apple 宏分支的 GCC 语法检查通过。这些检查尚不能证明 Apple SDK 编译或 Cocoa 截图时延，实际目标执行待新头 CI。

前头 `75b20fc6` Desktop `42702711687` 于 22:24:01 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2159/2159，两个打包作业成功。Windows CPU 1478/1478，独立原生 6/6 且每项 20/20 轮，零跳过。macOS CPU 1537/1537、Metal 254/254、原生主测 4/6。当前 MP4 在首次显式暂停下界失败，HTML 在隐藏暂停下界失败。同头 Runtime `42702712232` 全部 13/13。整轮终态满足本批推送前提。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42702711687/artifacts/13715432852) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232)

本头 MP4 的 fresh-hidden 与 fresh-visible 形成完整配对，已有播放 DOM 时间分别为 0.350154 与 0.367201 秒，两次暂停采样都回到 0.234 秒。隐藏原生报 Playing，持续可见时报 Paused。两组独立会话的视口高度相差 1 CSS 像素。当前 HTML 可见组在初始暂停阶段失败，缺少本头完整配对。该原视频回执仍未证明可见画面帧倒退，新帧号视频用于下一步独立观察。

Claude72 已从冻结基线 2b45ed81 在独立 `claude/guarded-viewer-open-72` 补受约束打开失败时保留原 Viewer 及参数草稿的回归，root 负责审阅和产品实现。现有异步打开在最终字节验证前清理旧来源，该路径继续验证。

本机证据 `root-delivery-20261109-118/` 的 `cocoa-final-review/review.json`、`cocoa-png-io-review/review.json`、`frame-clock-checks.json` 和 `frame-clock-final-verify/`。前头官方终态与 OS 工件证据在 `root-delivery-20261109-109/ci75/` 的 `desktop-terminal.json`、`macos-verdict.json`、`macos/receipt.json` 和 `windows/receipt.json`。

## 2026-11-09 22:12 UTC · 探针代次与原生 MuPRO 查看回归

`3f36d736` 让探针请求编号跨清除选点和关闭来源继续递增。已完成但排在主循环队列中的旧回调，即使无法取消，也无法覆盖新选点或新来源的探针结果。新请求仍按原路径完成。

集成 `8f84451c` 的两个确定性反例。测试先确认旧请求 Future 已成功完成，暂扣其回调，再清除重选或关闭重开，暂扣新回调后只释放旧回调。旧头两个反例各重复 5 次，10/10 在探针状态被覆盖处失败。修复后工作区 11/11、既有 Viewer 状态及表单 31/31，零跳过。

新增 C++ ViewerState 接真实严格 Python Bridge、图 worker 和 llvmpipe 离屏渲染的来源回归。Vulkan、OpenGL 两后端各 5/5，通过已缓存帧改写拒绝、保留上一份已验证画面、工作区恢复后显式求值与探针再次拒绝、恢复原文件后的画面和采样核对。每个后端均实际执行新增用例。该测试使用合成目录，实际目标 OS 窗口交互与许可算例继续验收。

远端 `75b20fc6` Runtime `42702712232` 已终态 13/13。Desktop `42702711687` 仍运行，3 个 Linux 作业与 Windows CPU 已成功，macOS 和独立 Windows 原生仍运行。本地新提交等待整轮终态再推送。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687)

Claude71 已在独立 worktree 提交可选可见帧编号诊断候选 `1525f17b`，仍在完成交付。root 正审阅诊断分类和截图证据落盘，候选尚未集成，实际 Cocoa 执行待下一头。

本机证据 `root-delivery-20261109-118/` 的 `probe-race-build/receipt.json`、`probe-race-build/red-{1..5}.xml`、`probe-workspace-final.xml`、`viewer-cpu-final.xml`、`native-real-graph-final.xml` 和 `native-real-cases/` 两份具名 XML。

## 2026-11-09 21:54 UTC · MuPRO 查看源校验与 Windows 回归

`89ffacbd` 把收集结果中算例文件的路径与 SHA-256 清单带入 Viewer 来源。来源与可编辑预设参数分开保存，打开、步进、预取、探针和工作区恢复后显式求值沿用该清单。图节点缓存命中前仍检查当前内容，读入经过项目目录约束和摘要校验的私有快照。本机缓存显示和探针网格缓存均不能绕过这次读取。

集成 Claude69 `2e3c4940` 与 Claude70 `9bd6d96a` 的回归。真实合成任务在 Viewer 调用处遭同大小、同 mtime 改写时拒绝冷、暖缓存结果，恢复原文件后回到原帧和原畴比例，零新增任务。严格子进程 Bridge 和图 worker 的求值、探针、清单范围及本机来源拒绝转发 Hub 四项通过。普通目录探针仍可携带未使用的失效绑定。

Python 3.12 联测 101/101，独立字节码目录的核心回归 52/52，最终严格 Bridge 4/4。既有 MuFerro 流程与 HDF5 收集兼容 41 过、1 项真实许可条件跳过。Python 3.14 定向 51/51，隔离 wheel 安装态 46/46，8 个安装成员与最终源码一致。Linux 原生 CPU 状态及工作区测试 40/40，包含来源传递、重复显式求值、探针和惰性恢复。这些原生状态测试使用测试桥，实际目标平台界面与真实 MuPRO 许可场景待验。

已推送的 `75b20fc6` Runtime `42702712232` 全部 13/13 作业通过。Windows Python 3.11、3.12 客户端分别 5246 过、275 跳过、934 排除。两组的同 inode 同大小恢复 mtime 文件签名、真实 NTFS 联接的严格 Bridge 拒绝和原生 ChangeTime 三项目标均由官方逐文件进度、精确源码收集顺序及完整跳过记录映射确认通过。该工作流未生成具名 JUnit，映射经独立复核。同头 Desktop `42702711687` 仍运行，本地查看链路修复等待整轮终态再推送。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687)

本机证据 `root-delivery-20261109-117/` 的 `source-clean-bytecode.xml`、`source-chain-final.xml`、`strict-source-final.xml`、`muferro-compatibility.xml`、`source-314.xml`、`wheel-source-final.xml`、`wheel-binding.json`、`native-workspace.xml` 和 `native-viewer.xml`。Windows 映射证据在 `root-delivery-20261109-109/ci75/windows-targeted-summary.json`。

## 2026-11-09 21:27 UTC · 前一 Desktop 终态与 Cocoa 配对对照

远端 `a7fce899` Desktop `42692999966` 于 21:26:05 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2159/2159，两个打包作业成功。Windows CPU 1478/1478，独立原生 6/6 且零跳过。macOS CPU 1537/1537、Metal 254/254，主原生 4/6，视频与 HTML 的隐藏暂停下界失败。同头 Runtime 13/13。前头整轮终态已满足本批推送前提，当前 Viewer 修改继续作为未提交开发。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42692999966/artifacts/13711373511) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

同头 fresh-visible 的 MP4 与 HTML 均暂停成功，DOM current_time 退回上一次 seek 位置。HTML 与 fresh-hidden 配对，两组前置历史和四个 OS 捕获阶段一致。隐藏时原生仍报 Playing、DOM 位置停在 seek，最终触发 watchdog。fresh-hidden MP4 在初始暂停阶段失败，缺少完整同头配对。时钟回退在持续可见时已复现，画面截图尚不能证明百毫秒级的解码帧回退。

本机原生证据 `root-delivery-20261109-109/cia7/` 的 `latest.json`、`macos/receipt.json`、`macos-matched.json`、`macos-summary.jsonl` 和 `windows-native-official-counts.txt`。当前源码与回归交付见 `80804d6f`。

## 2026-11-09 21:19 UTC · Project Runs 精确刷新与 MuPRO 文件身份

`0e5112ed` 通过 Hub 精确查询刷新已接受的 Project Runs 任务。旧节点缺精确读取能力时返回 unsupported 并保留最后观察，恢复现代节点能力后读回同一任务。底层 task.get 的旧节点兼容读取继续可用。真实严格 Bridge、Hub、NodeAgent 与 Runtime 复现了旧版缓存回退和错误的 not_found。持久回归在旧头失败，修复后 Python 3.11 联测 63/63。

`3ae33035` 让受约束的 MuPRO 文件登记、发布及 HDF5 读取复用描述符原生变化时间。Windows 取 ChangeTime，POSIX 取同一描述符的 ctime。覆盖同 inode、同大小且恢复 mtime 后的改写。集成 Claude68 `7241d850` 的严格 Bridge 回归，分别验证登记和发布拒绝链接目录，显式外部文件登记可用，换回真实目录后两条受约束入口可用。

Linux Python 3.11 联测 190 过、1 项 Windows 专属跳过。客户端矩阵定向 38/38，Python 3.14 定向 6 过、1 项 Windows 专属跳过，无 NumPy 回归 3/3。Linux 使用真实目录符号链接。Windows 的 NTFS 联接和原生 ChangeTime 仍待新头目标 CI。文件在末次服务端观察后仍可变更，真实 MuPRO 许可场景待验。

远端 `a7fce899` Desktop `42692999966` 仍在运行，4/6 作业通过。Windows CPU 1478/1478，macOS 原生对照及独立 Windows 原生仍运行。本地提交等待整轮终态。同头 Runtime `42692999627` 已终态 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

本机证据 `root-delivery-20261109-116/` 的 `project-run-exact-refresh/receipt.json`、`project-run-{red,green}.xml`、`native-time-{311,314}.xml`、`junction-root.xml` 和 `mupro-numpy-unavailable.xml`。

## 2026-11-09 21:03 UTC · MuPRO Bridge 发布结果校验

`f69edbe4` 把 MuPRO 结果行的最后复核移到 Bridge 发布请求。沿用结果单元格已有的路径和摘要，额外传原任务文件大小。服务端核对该运行、原生目录清单和内容，扫描目录后再次核对已读文件身份，最后按原句柄和修订提交。

集成 Claude67 `611b5e35` 的真实回环。旧头在发布调用处改写 HDF5 或替换成字节相同的目录链接时仍发布，两个反例按预期失败。修复后拒绝，恢复原文件即可重试同一任务。独立反例证明目录扫描期间的替换也被末次身份复核拦截。Python 3.11 联测 90 过、1 项真实许可条件跳过。Python 3.14 定向 12/12，隔离 wheel 4/4，5 个安装成员与候选字节一致。

真实本地项目发布 10,000 个合成文件，Bridge 请求约 1.66 MB。受控并发编辑与关闭分别得到修订冲突与句柄失效。调用方在校验后改写内存命令时，服务端提交原校验副本。文件在最后一次服务端观察后仍可变更，Windows 重解析点待目标平台实测。

远端 `a7fce899` Desktop `42692999966` 仍在运行，3 个作业通过。本地提交等待整轮终态。同头 Runtime `42692999627` 已终态 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

本机证据 `root-delivery-20261109-115/` 的 `red.xml`、`ordering-red.xml`、`final-311.xml`、`final-314.xml`、`wheel-final.xml`、`publish-cas.json` 与 `full-manifest.json`。

## 2026-11-09 20:45 UTC · MuPRO 收集文件登记一致性

`537b774b` 以原任务大小和 SHA-256 清单校验每批 MuPRO 结果文件。严格 Bridge 只登记规范项目内路径，在写入该批前拒绝链接、重解析点、大小或摘要不符。普通 Files 仍支持元数据登记和显式外部文件。全部批次后、结果行写入前再次复核清单。W5 二次登记保持项目内路径约束，冻结沿用原摘要校验。

集成并扩展 Claude66 `9f58670a` 的真实合成 Runtime 回归。旧头五个故障用例按预期失败。修复后同大小同 mtime 改写、换文件、父目录链接、登记后改写与 W5 重定向均被拒绝。恢复原文件后可显式重试同一任务，零重复提交或取消。Python 3.11 联测 86 过、1 项真实许可条件跳过。Python 3.14 定向与隔离 wheel 各 8/8。

校验期间其他项目操作可继续。受控并发编辑得到修订冲突，关闭得到句柄失效，两例均零索引行。观察之后文件仍可被修改。结果行校验在客户端发布调用前完成，未冻结本地文件。Windows 重解析点路径待目标平台实测。

远端 `a7fce899` Desktop `42692999966` 仍在运行，2 个作业通过，本地提交等待整轮终态。同头 Runtime `42692999627` 当前 10/13 作业通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

本机证据 `root-delivery-20261109-114/` 的 `red.xml`、`green-311.xml`、`green-314.xml`、`wheel-green.xml`、`wheel-binding.json` 和 `session-cas.json`。

## 2026-11-09 20:25 UTC · CLI 续读游标与前一 Desktop 终态

Claude65 的 `92c94ffd` 经 root 复验合入为 `4169e528`。CLI 中断时报告已经输出的字节位置，轮询仍用 Runtime 原游标。直连与 Hub 旧版红例各自报告 7，修复后从 6 续读，中文字符完整，正常 EOF 的残缺字符按替换字符输出并推进到末尾。若恰在输出写入中断，续读可能重放该段。

root 隔离候选的 Python 3.11 联测 120/120，Python 3.14 定向 4/4，均零跳过。此前旧 Runtime 末段重读的两项对照保持通过。

远端 `fa2ff5e2` Desktop `42679509572` 于 20:23:30 UTC 终态，5/6 作业通过，唯一失败是 macOS 主原生 4/6。Linux 主测 2156/2156，两个打包作业成功。macOS CPU 1537/1537、Metal 254/254，同 seek 保持可见对照随本批进入下一头。Windows CPU 1478/1478，Windows 原生 6/6 且每项 20 轮，零跳过。同头 Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42679509572/artifacts/13707666795) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

证据位于本机 `root-delivery-20261109-113/` 的 `cli-{red,green,314}.xml` 和 `desktop-terminal.json`。Windows 原生 PDF 的 20 次重新准备各有独立会话，160 张截图，捕获启动最长 93 ms，重新准备阶段最长 1433 ms。

## 2026-11-09 20:18 UTC · X7 单机链路切断样例

Claude64 的 `47e3cdde` 由 root 审阅修订后集成为 `127b0316`。`disconnect.py --scenario socket-partition` 在真实 NodeAgent 与 Hub 间主动关闭 TCP 隧道。两端保持运行，Runtime 在断线期间完成原任务，恢复后的首个精确答复返回同一任务成功。固定 stdout 和制品经真实 HubBackend 读取、下载并校验，只启动一次且 Hub 动作账本一致。

root 修复 pending connect 导致的排空与清理假成功，阻止切断前的连接跨越重开。失败回执清空 verified。三条回归在作者版按预期失败，在集成候选通过。另以真实断链只注入离线查询回退旧缓存，恰好 P4、P9 拒绝，其余 13 项通过，清理完整。

源码场景 15/15，约 36.49 秒。隔离 wheel 安装态场景 15/15，约 38.37 秒，12 个导入文件与主线摘要匹配。显式启用场景的最终联测 455/455，零跳过。单机主动关闭与静默丢包是不同故障，跨主机与原生桌面界面待验。严格 Bridge 子进程范围另见 19:54 UTC 诊断。

远端 `fa2ff5e2` Desktop `42679509572` 的 Windows 原生 `129402349100` 仍在运行，本地提交等待整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572)

本机证据 `root-delivery-20261109-112/` 的 `source-final/`、`installed/`、`parity-final.xml` 和 `claude64-root-negative/receipt.json`。

## 2026-11-09 20:04 UTC · Runtime 日志末段与 Cocoa 对照

`0458516a` 先读取 Runtime 任务状态再读日志，避免把末段写入前的空读取标成终态。CLI `logs --follow` 在连续两次收到空的终态响应后退出，兼容旧 Runtime。字节偏移与增量 UTF-8 解码保持原义，调度器更晚写入的日志仍可从最后游标续读。

用实际 worker 在 HTTP 读完空块后才放行写出末段并终止。旧服务把该读标成终态。另经真实直连和配对 Hub 注入旧版首次空终态答复，两组旧 CLI 都提前退出。修复后三项回归通过，跨块中文完整输出、游标按字节推进，当前 Hub 读取路径没有新增动作。最终 Python 3.11 Runtime、CLI、事件及桥接联测 118/118，Python 3.14 三项回归 3/3。

远端 `fa2ff5e2` 的 macOS CPU 1537/1537、Metal 254/254，主原生验收 4/6。新鲜隐藏诊断两项采样均完成。MP4 和 HTML 首次原生回复分别约 193、181 ms，均为 Playing。两次 DOM 采样均暂停并分别稳定在末次 seek 的 0.234、0.102 秒，比播放样本回退约 115、121 ms。两组均由一秒看门狗关闭。已在本地提交 `ded55b8a` 的同 seek 保持可见组等待下一轮目标平台对照。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42679509572/artifacts/13706450140)

同一 Desktop 轮次的 Windows CPU 1478/1478，零跳过，3 个 Linux 作业通过。独立 Windows 原生作业 `129402349100` 仍在运行，本地提交等待整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572)

本机日志回归证据见 `root-delivery-20261109-111/` 的 `log-tail-red.xml`、`log-tail-final.xml`、`log-tail-314.xml`。平台工件成员与摘要见 `root-delivery-20261109-107/cifa2/`。

## 2026-11-09 19:54 UTC · Runtime 单实例与 X7 链路切断

`a5239e05` 为 D1 C-11 增加 Linux 真实 API 双进程回归。两个进程均请求临时端口，目录别名启动的第二实例被拒绝，首个 PID 记录与工作区仍可读取。SIGKILL 后在同一锁 inode 上恢复原工作区。部署与 Hub 单实例联测 17/17，外部副本禁用 flock 后第二实例持续运行，回归按预期失败。

在 `62b94d1a` 上用真实严格 Bridge、NodeAgent、Hub 与 Runtime 做了 X7 单机传输诊断。仅切断节点到 Hub 的 TCP 连接，Hub 在 18.82 秒后报告离线。三次精确读取均返回 unavailable，原任务在断线期间完成。恢复同一链路后的首个精确答复为同一任务成功，固定日志与产物摘要核对通过。只有一次程序启动，Hub 动作记录一致，零协议违规，子进程均已回收。跨主机分区与产品观察界面待验。

Claude63 的 `ed59d42a` 由 root 审阅并修订为 `16dcd349`。MuPRO 试点文档补齐已发布的原生 HDF5 列出、显式选择和打开，以及只读查找重试。50 个本地链接检查通过。Linux 合成实窗验收与 Windows 客户端读取 CI 分开记录，真实许可输出、HDF5-only 完成与研究参考仍待验证。 [试点设计](design/mupro-executor-pilot.md)

远端 `fa2ff5e2` Desktop `42679509572` 仍在运行。3 个 Linux 作业通过，macOS CPU 和 Metal 通过，主原生 WKWebView 步骤失败且诊断继续，Windows CPU 测试运行中。同头 Runtime `42679509438` 终态 13/13。本地提交等待 Desktop 整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

证据位于本机 `root-delivery-20261109-110/` 的 `singleton-suite.log`、`singleton-red.log`、`mupro-link-check.json`，以及 `root-delivery-20261109-108/socket-partition-probe/run-01/receipt.json`。纯传输诊断的制品摘要由严格 Bridge 返回的元数据与 Runtime 的实际文件比对。

## 2026-11-09 19:42 UTC · 切换任务后的制品打开复核

`91b9d860` 保留派发时的制品条目。用户切换任务后，迟到回执仍可履行原来的显式打开，并在打开前使用原制品摘要复核本地文件。缺少原摘要时使用同一传输回执，两份摘要冲突时拒绝打开。复核沿用 256 MiB 本地检查上限，读取固定长度的普通文件。

严格 Bridge 与真实 Runtime 回环用两个任务的同名 `result.txt` 核对完成事件先到、切到另一任务、原排队回执最后到。干净文件触发一次打开回调。同长度改写一个字节时，旧版仍发出打开回调，候选显示摘要校验失败且打开回调为零。两个分支均保留原传输终态及当前任务的制品行，零额外 RPC 和零契约违规。

同一任务的两次 PNG 另存为用不同目标。较晚的请求先得到回执，随后较早回执到达时保留最新制品行和预览，两份文件独立校验。另以实际旧任务错误回执验证当前任务的同名制品行和预览保持一致。

Jobs 定向 50/50，零跳过。新增的回执倒序与打开复核用例各连续通过 5 轮。精确文件读取的两个核心测试通过，覆盖拥有字节、链接和 FIFO。

远端 `fa2ff5e2` Desktop `42679509572` 仍在运行，3 个 Linux 作业通过。macOS CPU 和 Metal 通过后继续原生阶段，Windows 在执行 CPU 测试。同头 Runtime `42679509438` 终态 13/13。Linux Python 3.11、3.12、3.14 分别通过 6493、6510、6493 项，两个 Windows 客户端各通过 5250 项。本地提交等待 Desktop 整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

本机证据见 `root-delivery-20261109-109/` 的原生测试 XML 和重复测试日志，以及 `root-delivery-20261109-108/artifact-scope-trust-native/runs/` 与 `overlap-artifact-native/final-relink/runs/candidate-overlap/receipt.json`。打开以生产桌面状态调用的测试回调计数。

## 2026-11-09 19:27 UTC · 初始传输回执与 Cocoa 可见对照

`74ba6ff5` 将同一传输的后续观测用于迟到的上传和下载开始回执。回执仍绑定原用户操作，完成状态保留。上传文件列表刷新按原尝试去重，下载保留一次已授权的打开或制品校验。制品行按详情代次和最新请求标识绑定。

Claude62 在独立 worktree 的真实严格 Bridge 与 Runtime 回环复现了四个迟到场景。旧版把完成行退回排队，上传错误阻塞任务提交，普通文件没有触发打开，PNG 制品仍待校验。root 用同一探针复验候选，新文件和缓存命中的 PNG 均校验并生成一次预览纹理，普通输入触发一次系统打开回调，上传只刷新一次文件列表，显式任务提交发出一次。正常回执顺序的对照通过，严格桥零契约违规。重复终态事件保持同样的计数，完成事件后改写一个 PNG 字节会被制品校验拒绝。另跑了 120 次不延迟回执的真实回环。

Jobs 定向 48/48，零跳过。新增持久用例连续 10 轮通过，覆盖迟到回执下的上传、输入打开、制品校验与提交。

`ded55b8a` 为 MP4 和 HTML 视频增加同一 seek 历史的保持可见对照。可见组通过现有测试钩子调用同一原生暂停执行路径，隐藏组沿用实际切标签。两组先接收原生回复，首个 DOM 样本最早在原生派发 200 ms 后，第二个在首个回调 400 ms 后，回调均受原有一秒上限约束。记录两次采样分别相对暂停前和末次 seek 的差，以及样本之间的差。

Linux 构建及相邻 CTest 44/44，零跳过。独立核对两组的 C++ Apple 条件分支、四个用例的 CTest 注册和 macOS CI 证据归档。Apple SDK、Metal 和 WKWebView 实跑待目标 CI，诊断为非门禁。

远端 `fa2ff5e2` Desktop `42679509572` 正在运行，2 个作业已通过。Runtime `42679509438` 整轮 13/13 通过。本地提交等待当前 Desktop 的整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

本机证据见 `root-delivery-20261109-108/`，含 `start-order-jobs.xml`、`claude62-root-replay/runs/`、`cocoa-control-linux.xml` 和 `cocoa-verification/paired-receipt.json`。传输探针运行编译后的桌面状态与真实回环，使用测试回调计数预览纹理和外部打开。

## 2026-11-09 18:55 UTC · 传输完成状态与迟到回执

`d7fbc3f1` 按原传输 ID 记录桌面已采纳的观测。迟到的继续、取消回执或刷新快照保留请求后已采纳的变化。刷新列表若先观察到已知在途传输完成，复用已有完成处理，随后同一完成事件只更新显示。

Linux X11/Xvfb 1440×1600，软件 OpenGL、英文、缩放 1。固定起点为 Transfers 已打开、选中真实 Runtime 的已取消下载、Viewer 为空。两次点击刷新、继续，零滚动、零键入，只有列表和原 ID 的继续请求。真实桥依次交付运行、完成、原排队回执和原取消列表。旧版从完成 100% 退到排队 76%，再退到已取消 76%。新版在两份迟到快照后仍显示完成 100%。两版均校验同一文件的 2,755,000 字节，Runtime 工作区和 Viewer 保持一致。

另以 Jobs 和 Transfers 可见、已选工作区、另存对话框已打开、Viewer 为空为起点。三次点击、一组快捷键和绝对路径输入，零滚动。真实桥先返回已完成列表，1.531 秒后交付原完成事件。新版收到列表时即显示“已下载并校验”，后续事件保持该状态，两版的 1,570 字节 PNG 均通过摘要校验。两组旧版和最终候选进程均正常退出。

Jobs 原生定向 47/47、零跳过。持久用例覆盖两份旧快照和先完成列表两种顺序，并核对已知上传完成后仅刷新一次工作区文件。隔离 Python 3.11 全量 `7cdaece6` 为 6477 通过、180 跳过、4 排除、零失败。随后加入的晚到 Hub 拒绝修复已由此前 141 项定向联测覆盖。`c5b87b91` 显式取消新增 HDF5 夹具子进程的模型变量，以空模型 API key 重跑仿真与 HDF5 原生定向 20/20、零跳过。

远端 `15dff6ac` Desktop `42669507898` 于 18:59:02 UTC 结束，5/6 个作业通过。Linux 主作业 2142/2142，Windows CPU 1466/1466，Linux 打包和冷环境通过。macOS CPU 和 Metal 步骤通过，主原生验收的 MP4 和 HTML 视频仍失败。新的 Cocoa 诊断 2/2，分别在约 183 和 182 ms 收到 WebKit Playing，各两次 DOM 采样均为暂停，位置分别停在先前 seek 的 0.234 和 0.102 秒。两组都在原一秒窗口内确认了位置回退。下一步用同一 seek 历史做保持可见的暂停对照。Windows 原生 6/6，零跳过，18:59:01 UTC 结束。 [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42669507898/artifacts/13701368078) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898) · [macOS 原生工件](https://github.com/sijintech/stk/actions/runs/42669507898/artifacts/13701990267)

本机证据包括 `root-delivery-20261109-106/final-jobs-v2.xml`、`late-transfer-native/{red-list,final-green-list}/evidence/receipt.json` 和 `root-delivery-20261109-107/owned-transfer-native/{red-owned-final,green-owned}/evidence/receipt.json`。PNG 实窗验收核对的是 Jobs 校验状态。

## 2026-11-09 18:25 UTC · 原传输继续与 HDF5 回执回归

`7cdaece6` 将已取消的传输纳入桌面继续操作。直连下载使用原传输 ID。Hub 上传仅在核对原导入确已拒绝后推进审阅编号，并在派发前持久化下一次尝试。若批准先到，继续跟踪原动作。`abaf0a31` 覆盖原动作在查询与同 ID 重放之间才被拒绝的时序。

严格桥、Hub 和 Runtime 回环覆盖正常拒绝、拒绝已提交但回复丢失、拒绝在重放前到达、批准先到和旧尝试摘要。旧版本定向复现首次重试仍失败。最终联测 141/141 通过。另以实际 CLI 回环核对查询断连或 404 时保留原编号，派发回执丢失后复用冻结的新动作 ID。

Linux X11/Xvfb 1440×1600，软件 OpenGL、英文、缩放 1。固定起点为 Transfers 已打开、真实 Runtime 下载已取消且原行已选中，Viewer 为空。旧版点击继续零请求，仍为已取消。新版一次点击、零滚动、零键入，只发出原 ID 的 `transfer.resume`。原行最终显示 100%，本地文件 2,755,000 字节与 Runtime 登记 SHA-256 一致。已完成行的对照点击零请求。Viewer 像素、日志 ID 集合及远端工作区文件保持一致，两版进程正常退出。

`a6681a6f` 将禁用 NumPy 和 h5py 时的图源注册测试改为核对七个必需的版本化 ID，相关三模块 48/48。隔离 Python 3.11 全量 `49140b04` 为 6473 通过、180 跳过、4 排除、1 失败，唯一失败为原六项断言。包含修复和首版传输变更的隔离 Python 3.11 全量 `7cdaece6` 已启动。

root 从 Claude60 的独立 worktree 选择集成 `f1fc18b6` 为 `fa2ef209`。其 12 项请求与回执测试已由 root 用实际 CMake 目标注册和复验。加上 Transfers、Hub 上传和 MuFerro 按钮共 24/24，零跳过。 Claude61 的任务卡和启动器已备好，等待 Claude60 的独立全量原生测试和进程收尾后启动。

远端 `15dff6ac` Runtime `42669507521` 已结束，8/13 个作业通过。Linux 三个矩阵和 Windows 两个矩阵的唯一失败均为六图源旧断言。两项 Windows 作业各 5249 通过、273 跳过、872 排除、1 失败，后续客户端检查未运行。Linux 3.11 和 3.14 各 6488 通过、165 跳过，3.12 为 6505 通过、148 跳过。三个 Linux 作业各 4 排除、1 失败。Desktop `42669507898` 仍在运行，本地交付等待整轮终态。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42669507521) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898)

本机 `root-delivery-20261109-105/` 保存 `transfer-late-{red,green}.xml`、`cancelled-transfer-native/{red,green}/evidence/receipt.json`、`integrated-native.xml` 和 Runtime 精确作业日志。原生回环覆盖 Linux，新的 Windows 和 macOS 结果待下一轮桌面 CI。

## 2026-11-09 18:07 UTC · MuFerro HDF5 查找重试与旧项目复验

`0b9b1c90` 在已收集的 MuFerro 运行记录查找失败时提供显式重试。点击后重新读取该运行的结果行，列表与打开仍由用户分别触发。仿真指南同步补充操作入口。

Linux X11/Xvfb 1440×1600，软件 OpenGL。固定起点为最大化 Project、已展开仿真运行记录、已选中原成功任务，Viewer 为空。通过严格桥在第一次真实结果行查询后返回可重试错误。旧版在刷新并重新展开后仍只有第一次查询。候选版一次重试仅补一次结果行查询。随后四次点击列出、展开选项、选择 Polar 第 2 步并打开，Viewer 显示 24 个体素，值域为 [0, 69]。两版均正常退出，项目修订 8，项目与 Runtime 记录和文件哈希保持一致。

同一显示环境以 `15dff6ac` 实窗复验。冷启动重开已收集项目，选中原成功运行后，HDF5 项目在空 Viewer 起点四次点击、零滚动打开原任务的 Polar 第 2 步。旧 DAT-only 项目在相同起点一次点击、零滚动打开普通畴 Viewer 的原末帧第 2 步。在同一会话从 HDF5 项目切到 DAT 项目再切回，之前的 HDF5 选择清空。显式重新列出时恢复四个选项，期间 Viewer、未发送草稿、项目修订和原 Runtime 任务保持原状。

原生构建及相邻 CTest 34/34 通过，零跳过。 `49140b04` 的隔离 Python 3.11 全量仍在运行。

远端 `15dff6ac` Desktop `42669507898` 仍在运行，1 个作业已通过。Runtime `42669507521` 已通过 8/13 个作业。本地修复等待前一 Desktop 运行的完整终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42669507521)

本机证据见 `root-delivery-20261109-104/` 的 `h1-retry-{released,green}/receipt.json`、`hdf5-compat/{hdf5,dat,switch}/evidence/receipt.json`、固定起点与结果截图及 `native-adjacent.xml`。MuFerro 本次使用公开合成算例，实际许可环境和合作方样例仍待验收。

## 2026-11-09 17:56 UTC · MuFerro HDF5 原生选择与 Cocoa 隐藏观测

`c3061e78` 为现有严格图入口增加单容器元数据节点，缓存查找前及元数据解析前核对登记 SHA-256。项目根和固定相对路径限定访问范围，列表只返回明确的场和步号。扫描最多 4096 个链接，列表最多 256 项，超出时拒绝整份列表。`49140b04` 在仿真面板接入列表、明确选择和打开。校验并持有载荷后才接纳 Viewer。

Linux X11/Xvfb 1440×1600，软件 OpenGL、缩放 1。固定起点为最大化 Project，Simulations 与 Simulation runs 已展开，选中唯一已成功并收集的运行，正例 Viewer 为空，Python 草稿隐藏。依次点击列表、下拉、`Polar · step 2`、打开，共四次，零滚动、零键入。Viewer 显示第 2 步 `Polar_x` 的 24 个体素，值域 `[0, 69]`。同大小容器改写后拒绝打开并保留原 Viewer。第三组在挂起成功答复时另点一次审阅页，放行后保留审阅页画面及原 Viewer。三组保留原 Runtime 任务、项目修订 8 和隐藏草稿。

本地 Python 联测 165 项通过，1 项性能基准跳过。原生相邻 34/34。离线构建 wheel，并从隔离安装位置确认节点注册和安装版节点参考。 Linux 项目 CPU 广跑 1034 过，12 项 Peer 因初始环境缺少依赖或安装版 helper 失败。补齐后同源码 Peer 20/20 通过。 新头 `49140b04` 的隔离 Python 3.11 全量仍在运行。

`e9d0da9b` 新增两个非门禁 macOS 诊断，复用常规播放、seek 与真实切标签，在原一秒窗口内先读原生回执再尝试两次 DOM 采样。Linux 相关 29/29，Apple 条件语法与目标测试注册通过，实际目标机时序待下一轮。旧 `fd611652` 的新增无重复暂停对照 2/2。两例 WebKit 被动回复 `Playing`，同一隐藏会话两次 DOM 均为暂停，时间增量为零。主验收 4/6，两例在首次原生查询前因隐藏保持时媒体位置回到前一次 seek 而失败。macOS CPU 1524/1524、Metal 254/254。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42658246869/artifacts/13696087547)

远端 `fd611652` Desktop `42658246869` 于 17:52:31 UTC 结束，5/6 个作业通过。Linux 主作业 2141/2141，Linux 打包及冷环境验证通过，Windows CPU 1465/1465。Windows 原生 6/6、零跳过，六项各 20 轮。PDF 160 张 OS 截图，20 次重准备，捕获启动最长 79 ms。PR #53 与 #54 的头未变化。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869) · [Windows 工件](https://github.com/sijintech/stk/actions/runs/42658246869/artifacts/13696884487)

本机证据见 `root-delivery-20261109-103/`，包括 `native-hdf5/{positive,mutation,stale-page}/evidence/receipt.json`、固定起点与结果截图、`python.xml`、`native-adjacent.xml`、`project-cpu.xml`、`peer-corrected.xml`、`installed-catalog.log` 和 `cocoa-linux.xml`。

## 2026-11-09 17:28 UTC · HDF5 载荷接纳与项目根绑定

`9e22e6ed` 提供明确授权的 Viewer 载荷替换。采用前核对项目、调用方、屏幕容量、文本编辑与 Viewer 版本。历史分析仍要求空 Viewer。内容寻址缓存共用有界解码，先检查每个唯一缓冲的长度和总预算，再读取并校验 Viewer 实际持有的独占字节。

实际严格 C++ 桥和 GraphWorker 从合成收集容器打开登记 SHA 对应的第 2 步 `Polar_x`，值域 `[0, 69]`。显式请求在延后阶段替换已有 Viewer。改写同大小 HDF5 时保留原 Viewer 和布局，排队后打开其他来源时返回冲突并保留新来源。另核对缓存改写、独占字节、长度上限、项目修订 8 及严格桥零契约违规。原生项目相关 28/28、载荷单元 6/6，均零跳过。

用合成目录交换复现按算例子目录绑定的边界问题。调用端检查后，若算例目录被换成指向项目外的链接，工作进程会将链接目标当作根。候选改为使用规范化项目根与固定运行相对路径，拒绝这一交换反例。已用真实严格桥核对该打开候选的 C++ 图摘要、24 个体素及 14 项输入或回执拒绝。打开候选已备好供面板接线。Claude59 正在独立 worktree 测试字段与步号适配器。审阅发现通用运行索引会枚举整个绑定，另在隔离 worktree 验证只读取指定容器的元数据节点。原生面板与实际点击仍待验。

隔离 Python 3.11 全量 `2d488712` 已结束，6464 项通过、180 项跳过、4 项按测试标记排除，零失败。 该轮覆盖 HDF5 测试替身修正，采用 3.11 源码和独立依赖环境。

远端 `fd611652` 的 Desktop `42658246869` 三个 Linux 作业成功，主作业 2141/2141。Windows 和 macOS 仍在运行，本地提交等待整轮终态。PR #53 与 #54 的头和审查状态未变化。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869)

本机证据位于 `root-delivery-20261109-102/`，包括 `native-adoption.xml`、`payload-unit.xml`、`native-fixture/candidate/receipt.json`、`hdf5-open/runtime.log` 和 `hdf5-open/binding-swap.json`。Python 全量证据在 `root-delivery-20261109-101/runtime-full311/`。

## 2026-11-09 17:12 UTC · 网页图谱接续、HDF5 选择核查与 Runtime 终态

`84ab61c6` 让网页图谱复用任务面板已接受的节点、工作区及任务观测。快照之外的已核验任务会进入图谱绑定，精确终态结束原任务进度轮询。独立选择其他图谱数据源或显式清空绑定时保留该选择。

生产 Chromium 1440×1100，固定起点已选节点、工作区和图谱页，能量预设已加载，Viewer 为空并有未发送草稿。输入 32 位原任务 ID 后点击一次，零滚轮和页面滚动。输入框为跟随光标有内部水平滚动。真实 Hub、NodeAgent 和 Runtime 保持在线，七次心跳均省略该任务。旧版读到原任务 running 但没有图谱选项或事件读取。新版选择原任务，用一次 `task.events` 显示 40%、第 4/10 步，精确终态后的 11.152 秒无后续事件读取。保留图谱参数、空 Viewer、草稿和重试记录，两轮各一个 Runtime 任务、零 Hub 动作。

网页生产构建和测试 11/11。四项 Chromium 边界覆盖错误工作区、A→B→A 的迟到答复、仅具备事件能力的旧节点及独立或清空绑定。上一轮产物列表对迟到空答复的浏览器回归也通过。

`2d488712` 修正上一批遗漏的 HDF5 快照测试替身，使其模拟允许收集。真实取消门控及摘要拒绝断言照常验证。定向 1/1。HDF5 与工作流组 110 项通过，性能基准和真实 MuFerro 许可环境各跳过一项。隔离 Python 3.11 全量基于 `2d488712` 运行中，已核对依赖及 suan 源码导入位置。

root 以 `e70982f9` 选择集成 Claude58 `045fb476` 的设计和证据。实际收集的合成 HDF5 含两个场各两个步号。严格桥和 GraphWorker 按登记 SHA 读取指定非末帧，原地改写容器与错误选择器被拒绝。root 用作者探针独立复跑 1/1。复核确认原生 `open_path` 会在求值前清空 Viewer，设计改为先验证并解码载荷，再核对项目、选择和 Viewer 版本后接纳。原生界面与点击数仍待实现验证，真实许可与 HDF5-only 完成仍待证。 [设计核查](design/mupro-hdf5-result-selection.md)

远端 `fd611652` Runtime `42658246715` 于 17:07:17 UTC 终态，八个作业通过，三项 Linux Python 与两项 Windows 客户端作业均因同一条 HDF5 测试替身提前抛出 `_Cancelled` 失败，五项各只有这一条失败。Desktop `42658246869` 仍在运行，本批本地提交等待整轮 Desktop 终态后推送。PR #53 和 #54 的头未变化。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42658246715) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869)

本机证据见 `root-delivery-20261109-101/`，包括 `web-graph-live/{red,green}/receipt.json`、固定起点及过程截图、`web-graph-edges/receipt.json`、`web-artifact-control/green-receipt.json`、`hdf5-root.xml`、`claude58-root/receipt.json`和 `runtime-failed-summary.txt`。

## 2026-11-09 16:57 UTC · 网页完成产物刷新与 Hub 动作回执

`ef894f85` 在网页接受同一执行节点、项目和任务的 Runtime 精确终态后，自动只读刷新原任务产物。不同工作区的终态答复不会触发刷新。手动及自动读取共用答复顺序，已采用的新产物列表保留，迟到的旧空列表无法覆盖。

生产 Chromium 1440×1100，固定起点已选节点和项目，Viewer 为空且有未发送草稿。真实 Hub、NodeAgent 和 Runtime 保持连接，测试心跳列表固定显示 running。同一任务解除门控后，旧版两次读到 `succeeded` 仍只有占位项。修复版从起点一次点击、零滚动，自动读取一次产物并列出 `field.vti`。两轮各一项 Runtime 任务、零 Hub 操作记录，Viewer、草稿和重试内容保留。另用受控浏览器响应核对工作区不匹配及迟到的空列表。生产构建和网页 11/11 通过。

`1a6fb12c` 将已读到的 Hub 动作回执与后续 Runtime 任务读取分别保留。真实回环中取消动作先返回排队，Runtime 收到一次请求并在修改前拒绝，随后节点断开。刷新保留原可重试 `unavailable` 错误，冷重开能读到同一 Hub 动作 `failed`，并保留原 Runtime 任务最近的 `running`。旧代码定向复现 1 项失败，隔离相邻回归 68/68，root 主工作区联合回归 80/80，均零跳过。

远端 `fd611652` Desktop `42658246869` 仍在运行，新的本地提交等待该轮终态。Runtime `42658246715` 当前 8/13 个作业通过。开放 PR #53 和 #54 的头未变化，分别仍有冲突和检查问题。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42658246715)

本机证据见 `root-delivery-20261109-100/` 中的 `web-live/{red,green}/receipt.json`、浏览器截图、`web-reply-order/green-receipt.json`、`hub-action/{red-final.xml,green-final.xml,loopback-final.log}` 和 `hub-root.xml`。

## 2026-11-09 16:46 UTC · Runtime 取消确认、Cocoa 对照与桌面终态

`c3f869eb` 先向正在跟踪的各 Runtime 原任务分别发出一次取消，再用原连接只读核对待确认的任务。只有观察到 Runtime `cancelled` 才记录原任务已取消。已先结束的任务保留 Runtime 原终态，未确认的任务保留原 ID 并标为中断。五秒是发出请求后的观察窗口，单次网络读取仍受原连接超时约束。已经持久化的取消可阻止新收集开始。人工再次启动可接回原运行或原成功任务。

旧代码在取消回复丢失时直接写入已取消，并会在成功读取与取消交错时进入收集。新回归核对接收取消后的断连、晚于观察窗口的回执、多行中的畸形回复和已取消后阻止新收集。八个相关 Python 测试文件 137/137，零跳过。

root 集成 Claude57 在独立 worktree 提交的 `d86b2324`。真实回环 Runtime 拒绝第一次取消时，第 2 次尝试停为中断。求解器 PID、创建时点与任务 ID 保持一致，无新增提交、取消重试、收集或分析。第 3 次经人工启动接回同一任务，原批准保留。Claude 基线组 114 过、1 项预期失败。root 在隔离 worktree 使用修复和作者的原始测试，拒绝取消与正常取消对照 2/2。使用门控合成求解器，商业许可宿主仍待验。

上一轮 macOS 的两个失败用例中，DOM 报告暂停但媒体时间倒退。原无 DOM 对照在两例都读到 WK `Playing`。`ad174492` 保留该对照，新增两例非门禁诊断，在同一隐藏视图先保留被动 WK 原生回执，再相隔 400 ms 观察两次 DOM 媒体时间。Linux 相关 CTest 29/29。Apple 条件 C++ 语法和工作流步骤检查通过，实际行为待 macOS CI。

远端 `b4110f8c` Desktop `42646061897` 于 16:41:18 UTC 终态，五项通过，仅 macOS 失败。Linux 主测试 2138/2138，Linux 打包与冷环境验证通过，Windows CPU 1463/1463。Windows 原生 6/6、零跳过，六项各 20 轮。PDF 160 张截图、20 次重准备，重准备启动最长 89 ms，PDF 全程单次捕获启动最长 114 ms。macOS CPU 1521/1521、Metal 254/254、原生 4/6。Runtime `42646061798` 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [Windows 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13692551836) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13690393949) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42646061798)

取消、Claude 复验、Linux 原生测试及 Apple 条件语法证据位于 `root-delivery-20261109-99/`，见 `cancel-final.xml`、`claude57-green.xml`、`native-local.xml` 和 `apple-conditional.log`。Windows 工件的 CRC 校验及循环汇总位于 `root-delivery-20261109-98/cib411-windows/windows/`。

## 2026-11-09 16:25 UTC · 网页精确任务观察、Hub 撤权和人工取消

`683963e9` 为 STK 网页任务面板接入 Hub 精确只读观察。节点快照与 Runtime 最近状态分开，核对节点、工作区和任务 ID。通过任务 ID 也可查询快照外的任务。断线保留最后一次观察，重连继续读。图谱事件轮询使用现有只读入口，选择和自动观察不写 Hub 操作记录。

生产网页 Chromium 1440×1100，起点已选择节点和项目，Viewer 为空。点击任务一次、零滚动，取得同一 Runtime 任务的精确 running。真实 NodeAgent 断连时保留 running 并标明读取不可用，原任务成功后重连更新为 succeeded。模拟心跳遗漏后按 ID 找回，错误工作区拒绝采用结果，撤权后网页退出会话，图谱事件查询为只读。CLI 与严格 Desktop Bridge 的终态记录一致，Runtime 只有一个任务，Hub 操作记录零条。网页构建和 11/11 测试通过。证据 `root-delivery-20261109-98/browser-verified/{receipt.json,fixed-start.png,running.png,unavailable.png,succeeded.png}`。

`75b7e87f` 在转发答复前复核客户端和节点，撤权的迟到回复分别返回 401 和 404。`1774642d` 在发送每条 SSE 后复核授权，同批后续事件被拦截，旧流正常结束。`c98145a3` 要求 MuFerro 完整结果包含能量、进度、完成文件和初始 Polar，已知计划时仍检查计划帧，旧记录的原终态和验证保留。两项首批合跑 172/172，SSE 与联邦等后续 46/46，均零跳过。隔离 MuFerro 联跑 212 过，3 项跳过（Windows junction、两项商业许可）。

root 以 `17cbfcc1` 集成 Claude56 `8962c956`。真实第三个 Bridge 在接管原运行后执行人工取消。求解器仍被夹具门控时，Runtime 对原任务 ID 收到一次取消，求解器停止，项目停止且没有新增提交、收集或分析。重复取消和冷观察保留原批准。作者和 root 分别 114/114 零跳过。该场景使用可达 Runtime 和受控求解器，取消请求未确认的失败分支仍需单独处理。证据 `root-delivery-20261109-98/claude56-root.xml`。

远端 `b4110f8c` Desktop `42646061897` 的三个 Linux 作业通过，Linux 主测试 2138/2138，Windows CPU 1463/1463。macOS 于 16:23:06Z 失败终态，CPU 1521/1521、Metal 254/254、原生 4/6。新增不重复暂停的对照 2/2，视频与 HTML 视频先在可见时读到 Paused，真实隐藏后保留同会话，独立查询均读到 Playing。对照没有隐藏期 DOM 采样，重复暂停组 0/2 且两例各 27 次 Playing 后 watchdog 关闭。Windows 原生仍在运行，本批等整轮 Desktop 终态。Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13690393949)

## 2026-11-09 15:56 UTC · 历史分析归档核验与 MuFerro 运行中接续

`36c5ab8d` 绑定选中历史运行的首次归档回执。相同运行的结果读取和状态读取若返回变化后的回执，保留已验证的结果和检查模型。`af8746ad` 按已验证的归档预算检查所选载荷，用同一普通文件句柄读取精确长度，再对 Viewer 实际持有的独占字节校验 SHA-256。旧代码的回归分别确认会接受替换回执、已解码映射会随源文件原位改写。新代码能拒绝改写和长度错配，已加载载荷仍保持原值。Windows/macOS 的新读取路径待目标 CI。

回执变更 C++ 86/86，精确读取与归档相关 C++ 92/92，独立缓冲与载荷检查 11/11，均零跳过。隔离 core 90/90，另有 3/3 Linux UBSan 读故障注入。Linux X11/Xvfb、1440×1600、软件 OpenGL，起点是已选中成功历史运行且 Viewer 为空。一次点击、零滚动显示冻结 HDF5 第 4 步 `Polar_x`。只请求一次归档，项目修订 13、原 Runtime 任务、冻结文件和隐藏草稿一致。证据 `root-delivery-20261109-97/{archive-owned.xml,archive-unit.xml,native-replay/evidence/receipt.json,archive-exact-io/unit-final.xml}`。补充项目广跑 1473 通过、12 项 Peer 在缺依赖环境失败。重建 Peer 目标并改用含 cryptography 的 Python 3.12 和已安装 helper 后，Peer 20/20 零跳过。

root 以 `6e638721` 集成 Claude55 `b61ecc9e`。旧 Bridge 强制退出时求解器仍被夹具门控。重新观察、非强制人工恢复及显式启动期间，原求解器 PID 与创建时点保持一致。第 2 次尝试在解除门控前记录接管原任务和运行状态，重复启动只读回当前执行。随后记录一次收集，绑定原产物、冻结快照和真实 GraphWorker 能量结果。总提交一次，取消零次，原审批保留。作者和 root 六个源码测试文件各 113/113，均零跳过。商业许可求解器仍待验。证据 `root-delivery-20261109-97/claude55-root.xml` 与 `claude55-root-scratch/`。

`aa9a909d` 把 `transfer.cancel` 的文档与既有返回值对齐，已终态时保留原状态，等待结束时返回当前状态。传输生命周期与关停回归 44/44。复核 #53 `c9f13994`，旧并发问题已由主线修复，剩余立即入队实现会提前从线程表移除旧 worker。#54 `2dd3e4ee` 的大写交接名与现有文件冲突。两项保留待审。 [PR #53](https://github.com/sijintech/stk/pull/53) · [PR #54](https://github.com/sijintech/stk/pull/54)

远端 `b4110f8c` Runtime `42646061798` 于 15:55:20Z 完成，13/13。Desktop `42646061897` 仍在运行，本批等待该轮终态后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42646061798)

## 2026-11-09 15:30 UTC · Cocoa 隐藏采样、MuFerro 人工接续与桌面终态

`f6730c49` 增加 macOS 探针对照。先确认同一导航的可见原生暂停，真实切换标签时只跳过本次再次派发，隐藏保持后独立读一次 WebKit 播放状态。 探针绑定确切窗口、会话和已验证的媒体代次，保留首次真实 ACK 和计数。普通标签切换实际隐藏和释放焦点。1.25 秒保持后，原生轨迹只接一组只读查询及回复，原始枚举作为独立证据。采样要求同一存活、隐藏、失焦的视图，DOM 采样为零。诊断通过表示成功取得原生枚举。

Linux 媒体及证据 34/34，合成守卫 42/42，Apple 条件 C++ 语法及 CTest 注册通过。真实 Apple SDK 构建及 WKWebView 结果待新 CI。 CI 新作业步骤单独归档两例 JUnit 和各自的结果，缺失、失败与跳过均由原检查器报告。证据 `root-delivery-20261109-96/{native-evidence-final.xml,forced-apple-test-syntax-final.log,apple-ctest-registration.json,workflow-validation.json,native-control-proof/receipt.json}`。

root 以 `767903df` 集成 Claude54 `43e52c63`。真实第三个 Bridge 观察原任务时不收集。人工恢复将消失的旧执行尝试标为中断，明确启动后第 2 次尝试接管原成功 Runtime 任务，保留原批准并核对原始输出字节。真实 GraphWorker 生成 Total Energy `[-1.125, -2.25, -3.375]` 并在 Bridge 退出后回收。定向 1/1，六个验收和 Bridge 测试文件共 112/112，均零跳过。使用受控求解器夹具，商业许可宿主仍待验。证据 `root-delivery-20261109-96/claude54-root-final.xml`。

远端 `971c0cbf` Desktop `42633409122` 于 15:30:19Z 终态，五个作业通过，macOS 原生失败。Linux 主测试 2135/2135，Windows CPU 1460/1460，Windows 原生 6/6、零跳过，六项各 20 轮，PDF 160 张截图且重准备 20 次。macOS 原生 4/6，首次可见暂停 2/2，可见二次暂停 1/2，重复隐藏暂停 0/2。两例均先获得可见原生 Paused，真实隐藏后的二次请求收到 ACK，随后 26 和 23 次原生查询均为 Playing。macOS CPU 1518/1518、Metal 254/254，Runtime 13/13。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42633409122/artifacts/13688110049) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42633409122/artifacts/13684539547) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42633409122)

## 2026-11-09 15:10 UTC · 一次点击查看已验证的历史分析

`e345038f` 给成功的历史分析增加“读取并显示结果”。归档校验后只有一个可显示载荷时直接打开，多个时保留手动选择。 沿用原归档校验与 Viewer 延迟交接，绑定原项目会话、运行计划和清单摘要。收到回复时原运行页须可见，Viewer 打开后再关也会使待显示结果失效。普通读档和显式输出选择仍可用。

实窗为 Linux X11/Xvfb 软件 OpenGL、英语、1440×1600，程序记录 UI 缩放 1.04。起点为 Runs 侧栏选中成功的 `40bc4b12`，Viewer 为空，Python 草稿隐藏。左键一次 `(1325,605)` 点 Read and show result、零滚轮，首帧显示 `/t00000004/Polar` 的 x 分量、24 体素。同一固定起点此前四次点击；打开项目后准备此布局另计四次点击。

原收集 HDF5 不在原路径。严格桥只有一次 `project.analysis_runs.result`，计划和清单摘要匹配。项目修订 13、两份数据库、5 个归档文件、52 个任务文件及一个 Runtime 任务一致，隐藏稿字节摘要相同。窗口正常退出。前后截图和回执在 `root-delivery-20261109-95/native/evidence/` 的 `ui-9.png`、`ui-10.png`、`receipt.json`。

分析、Viewer 与工作台定向 70/70，项目 CPU 标签 1044/1044，均无失败或跳过。 root 以 `a8ac9db2` 集成 Claude53 `5a3d8033`。SIGKILL 前核对原批准与已运行的求解器，桥离线时同一任务成功。重开读取历史启动和项目中持久的 running 状态，实际 Runtime 已成功，真实提交共一次。下载三份产物核对摘要，根源码 103/103。证据 `root-delivery-20261109-95/claude53-root-final.xml` 和 `claude53-root-focused/`。 远端 `971c0cbf` 三个 Linux 作业、Windows CPU 1460/1460 与 Runtime 13/13 通过。macOS 原生基线 4/6，新暂停顺序对照 0/2。两个可见暂停先确认成功，隐藏后的新暂停收到 ACK，但 26 次与 23 次原生回复均为 Playing，最终 watchdog 关闭。第二次可见对照 1/2，HTML 用例止于初次暂停的时间下限。Windows 原生仍在运行，本批等待整轮结束。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42633409122/artifacts/13684539547) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42633409122)

## 2026-11-09 14:40 UTC · 冻结 HDF5 归档的原生首帧

`71f878df` 修正 Viewer 在采纳归档后首帧被旧灰色背景盖住的问题。旧代码回归失败，修正后相关 C++ 67/67。 编辑区先构建本帧内容，再取背景，使背景透明度与本帧载荷状态一致。旧测试首命令为全区 `Rect`，新测试从 `ClipPush` 开始。本机证据 `root-delivery-20261109-94/{red-first-frame,green-first-frame}.xml`。

实窗固定为 Linux X11/Xvfb、软件 OpenGL、英语、1440×1600、请求缩放 1，程序记录实际 1.04。从项目已打开的 Home 到成功运行选中，依次打开 Analysis runs、折叠准备、读取列表、选中运行，共四次点击。固定起点为 Runs 侧栏已选 `40bc4b12` 且 Viewer 为空。四次左键分别读取并验证、打开输出下拉、选择 `view`、显示输出，零滚轮。原始 `run.h5` 不在原路径。旧首帧中区 424000 像素全灰，额外重绘才显示；新首帧中区有 1505 种 RGB 值，并显示 `Polar_x` 的 24 个体素、外框、坐标轴与色条。

严格桥在测量区间只收到一次 `project.analysis_runs.result`，运行 ID、冻结计划及归档清单摘要吻合。项目修订 13、两份数据库、5 个归档文件、52 个任务文件及一个 Runtime 任务一致。隐藏 Python 草稿执行的字节摘要与原稿相同。修复版正常退出。固定起点、首帧及回执见 `root-delivery-20261109-94/native-fixed/evidence/` 的 `ui-9.png`、`ui-12.png`、`receipt.json`。

root 以 `641b2807` 集成 Claude52 的 `0cda6bcc` 与 `6464a3c0`，审批跨进程和相邻回归 102/102。 严格桥握手核对真实 PID。首个桥在审批回执写出但未交付后被 SIGKILL，原任务仍在 Runtime 排队。新桥观测同一批准、运行和执行器，测试范围内一次真实提交、零取消或恢复。作者三种故障注入均回收子进程。证据 `root-delivery-20261109-94/claude52-review/evidence/inject/` 与 `claude52-root.xml`。

本机 `395e78fd` 隔离 Python 3.11 全量 6446 过、180 跳过、4 排除、零失败。远端 `971c0cbf` Runtime 13/13 已于 14:39:55Z 结束，Desktop 仍运行。 项目 CPU 首跑的 12 个 Peer 失败涉及缺少 cryptography 和已安装 helper，重建 Peer 目标并补齐后定向 20/20，全组 1041/1041。证据 `root-delivery-20261109-94/{project-cpu,project-peer,project-cpu-final}.xml`。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42633409122) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42633409136)

## 2026-11-09 14:12 UTC · 上一轮 Desktop 终态与冻结 HDF5 分析

远端 `249698d0` 的 Desktop 于 14:12:41Z 结束。三个 Linux 作业通过，Windows CPU 1460/1460、原生 6/6，macOS 原生 4/6。Runtime 13/13。 Linux 主作业 2134/2134，Windows CPU 的 1179 项必测全部运行。Windows 原生 6/6、零跳过、1333.70 秒，PDF 20 轮取得 160 张截图，20 次重准备均记录，未观察到遗留会话。捕获启动最长 96 毫秒，低于 1 秒诊断阈值，此次尚未定位此前的间歇性长停顿。macOS CPU 1518/1518、Metal 254/254，两个原生失败为视频和 HTML 视频。首轮和第二轮可见暂停对照各 2/2，六条隐藏对照在隐藏后取得回执，随后原生状态仍为 Playing。工件核验见本机 `root-delivery-20261109-88/ci249/{windows,macos}/receipt.json`。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42621953590) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42621953348) [Windows 工件](https://github.com/sijintech/stk/actions/runs/42621953590/artifacts/13681666456) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42621953590/artifacts/13680007342)

`9f2bcfd3` 集成 Claude51 的 `047f20b3`。真实本机 Runtime 用合成求解器收集 `run.h5`，工作区记录、冻结清单和分析绑定使用同一 SHA-256。移开原路径后，实际 GraphWorker 解码 `/t00000004/Polar` 的 x 分量，核对 4×3×2 网格、float32、坐标顺序和范围 100–169。错误预期摘要得到 `graph_error`，无输出载荷，文件记录与 Runtime 任务数保持一致。作者联跑 127 过、2 条件跳过，root 最终收集回归 7/7。证据 `root-delivery-20261109-93/claude51-root-final.xml` 和 `root-delivery-20261109-92/claude51/evidence/`。

## 2026-11-09 14:06 UTC · 已收集 HDF5 摘要与 Cocoa 暂停顺序

`395e78fd8f8895aac9b43e7ff849da4865cac624` 让 `stk.source.mupro_hdf5@1` 接受可选的预期容器 SHA-256。规划在缓存查找前核对实际字节，匹配时复用同一内容键。合成测试在相同大小及 mtime 改写后拒绝旧摘要，省略约束的旧调用能读到当前值。独立真实本机 Runtime 收集对照在 View 核验后替换一个体素，旧图读到替换值，加入收集摘要后在冷缓存与已有替换文件缓存两种情况下均拒绝，恢复原字节可读，任务数和项目修订一致。源码 260 过、2 条件跳过，隔离 wheel 25/25。证据 `root-delivery-20261109-92/hdf5-pin-{red,source-final}.xml`、`hdf5-pin-wheel/installed.xml` 与 `root-delivery-20261109-91/hdf5-binding-pinned-independent/`。 [HDF5 契约](specs/mupro-hdf5-1.md)

本地 `2eb64f04` Python 3.11 全量 6442 过、2 败、180 跳过、4 排除，1192.98 秒。失败分别为节点参考页落后于图目录，以及原生分发测试还期望实时预设。`395e78fd` 重新生成参考并更新断言，两项在最终联跑通过。含修正的独立 Python 3.11 全量已启动。旧、新证据分别在 `root-delivery-20261109-90/runtime-full311/` 和 `root-delivery-20261109-92/runtime-full311/`。

`40608ca1` 集成 Claude50 `5f954d84`。合成探针证明快照绑定的 HDF5 场经现有 GraphWorker 生成载荷，选择器是显式字符串。作者定向 73 过、1 性能例跳过，9 个本地链接通过检查。已有 DAT 默认 View 继续按其契约工作。HDF5 专用预设、时间轴和原生分析载荷点击仍需各自验收。Claude51 验证实际收集记录至冻结分析的路径。证据 `root-delivery-20261109-91/claude50/evidence/`。 [试点设计](design/mupro-executor-pilot.md)

`090fe8f2ce52389731d63b23be89a3a2ca8db05f` 新增 Cocoa 诊断。匹配的恢复播放后，同一导航先收到可见原生非 Playing 回执，再切换标签，让生产监听器派发第二次暂停。回执分别记录两个媒体代次、隐藏、原生确认和回复，两个阶段都避免 DOM 取样。实际隐藏和第二次暂停共同发生，诊断只区分该生产顺序的结果。新增 CI 步骤独立记录诊断结果，原验收门保留。Linux 原生测试构建通过，证据检查 12 项及 7 子测通过。独立强制 Apple 分支 C++ 语法、合成观察器、CTest 注册和回执解析通过。实际 Apple SDK 与 WKWebView 待目标 CI。证据 `root-delivery-20261109-92/mac-hide-after-pause/validation.json` 和 `mac-hide-root-evidence.xml`。

远端 `249698d05dc13d9c08a2aebd9e906ebc38873a9d` 的 macOS 作业于 13:51:26Z 失败。CPU 1518/1518、Metal 254/254，零跳过。原生 4/6，失败为视频与 HTML 视频，两个可见对照通过。三个 Linux 与 Windows CPU 作业已通过，14:05Z 时 Windows 原生仍在运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42621953590) [macOS 证据](https://github.com/sijintech/stk/actions/runs/42621953590/artifacts/13680007342)

## 2026-11-09 13:49 UTC · 面板点击、导出共存与原批准观察

`7ac983e8bd69505652b0bc692ee483ad4ce6c09e` 集成 Claude49 的 `2846d935`。只丢弃一次成功 `run_decide` 的已序列化回执，合成 MuFerro 在真实本机 Runtime 完成后普通关闭桥。新严格 Bridge 以新句柄和执行器打开同一项目，通过 `run_observe` 读到原审批和执行器，历史 `started` 与当前 `stopped` 分别匹配。原批准、启动日志、任务 ID 和一次真实提交均可追踪。源码联跑 64 项，隔离 wheel 2 项通过。独立在原候选记录真实 HTTP 服务的一次 submit、零 cancel 和工作流零 recover/cancel。范围为同一进程中重建 Bridge，实际进程中断及执行中重开仍待验。证据 `root-delivery-20261109-91/claude49-source.xml`、`claude49-wheel/installed.xml` 与 `claude49-lost-approval-review/`。

`3f48687021d355093d7f8d08f2e0767752ce286b` 给原生分类传入显式预设。旧版遇到普通 `input.toml` 与合法 `result.json` 同目录时，分类为保存结果，丢掉收集预设。新版显式选 `muferro-collected-domains` 时打开算例，默认打开和直接选 `result.json` 保留保存结果。C++ 红例失败在来源类型及预设，修复后查看器测试 31/31。二进制 SHA-256 `a4acb1b27a9ac9dd6363a53bc02f961d508091e59e548675074d317c21656d43`。证据 `root-delivery-20261109-91/viewer-classification-{red,full}.xml`。 [桌面脚本契约](scripting-viewer.md)

真实 Linux 面板验收在英语 X11/Xvfb 1440×1600、缩放 1、软件 OpenGL，项目编辑器最大化，Simulations 与 Simulation runs 已展开，选中唯一成功的合成 MuFerro 运行，Viewer 为空，项目修订 8。准备布局的 10 次左键和 1 次右键另记。一次 XTest 左键 `(1130,595)` 点击 View collected result，恢复分区布局，显示预设 `muferro-collected-domains`、第 2 步、步选 `[0,2]`、140 个三角面。基线用桌面 `757383af77`，导出共存复跑用修复后构建，两组后端均为 `2eb64f04`。共存用例在算例放入真实导出的第 0 步 `result.json` 和渲染数据。独立三次探查点击确认默认打开为保存结果，图求值新增 0 次。批准、计划和任务写调用均为零。修订、两份数据库、36 个 Runtime 任务文件、29 个本地算例文件的摘要均一致。两次正常退出，子进程回收。证据 `root-delivery-20261109-88/collected-native-review/evidence/panel/panel-receipt.json` 与 `collision/evidence/{panel-collision-receipt.json,fixed-start.png,after-view.png}`。

远端 `249698d05dc13d9c08a2aebd9e906ebc38873a9d` 的 Windows CPU 于 13:49:06Z 通过，1460/1460，1179 项必需，934.83 秒。MSVC 已编译窗口捕获诊断并链接原生验收工具。此前 Linux 三项通过。macOS 原生主验收及三组隐藏对照失败，两组可见暂停对照通过。已核对六条隐藏轨迹，派发时 WebView 实际可见且已无焦点，派发后约 0.14–0.40 毫秒隐藏，约 11.94–24.34 毫秒后在隐藏态收到派发确认。原生查询回执各组为 24/27、28/26、28/26 次 Playing。主验收视频在初始暂停提前失败，HTML 到隐藏后像素条件即失败，两条主验收未提供可比的查询序列。Windows 原生 `129199406869` 在运行。`2eb64f04` 本地 Python 3.11 全量仍在运行。两个开放 PR 的精确头与上次审阅一致。本批等待整轮 Desktop 终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42621953590) [macOS evidence](https://github.com/sijintech/stk/actions/runs/42621953590/artifacts/13680007342)

## 2026-11-09 13:36 UTC · 冷重开、输入字节和收集后的 DAT 末帧

`5e3eba2b5ec1130b95763c644e4bdbe99cc450de` 集成 Claude48 的 `49d3742a`。同一进程中关闭并重建严格 Bridge，重新打开同一项目，句柄更新，卡片、完整计划与摘要保留。显式观察后仍无法批准。重新审阅后原计划批准成功，观察和重放仍绑定原执行器，真实本机 Runtime 仅有一个合成任务。root 的转发计数确认只有一次启动调用，故意在重放时调用一次启动的变异例按预期失败。独立作者候选联跑 14 项，root 源码联跑 63 项通过。证据 `root-delivery-20261109-90/claude48-source.xml` 和 `cold-replay-negative/result.xml`。实际 OS 进程重启和许可软件待验。

`173d0534eba36922d3a93fce73b2ea6ed10ce9f3` 从重新打开的普通文件流校验并复制冻结输入，复制总量沿用 256 MiB 限额。旧版在快照解析后换入同长度、同 mtime 的合成材料文件会创建计划，重试准备目录里的 FIFO 会进入阻塞打开。新版两项均在产生工作区或任务前拒绝。源码 123 过、3 条件跳过，准备、收集和审批隔离 wheel 联跑 12/12。证据 `root-delivery-20261109-90/muferro-prepare-{baseline,source}.xml` 和 `prepare-approval-wheel/installed.xml`。

`2eb64f04079b37b1996b413b2a79d968cc6f7d04` 修复合成 Runtime 收集后查看合法 DAT 的末帧。旧预设对一个只去掉尾部填充的有效第 2 步 Polar 只列第 0 步，即使任务清单和收集行的摘要匹配。独立收集预设仍共用原图，显式关闭实时大小过滤，选第 2 步且保留 `[0,2]`。默认预设保持实时筛选，旧节点缺参数时仍返回原预设。root 源码 100 过、2 条件跳过，隔离 wheel 8/8。独立合成测量中约 9756 个文件时额外普通文件核验中位数约 463 毫秒。此组范围为真实本机 Runtime、合成求解器和无窗图求值。证据 `root-delivery-20261109-90/collected-view-source.xml`、`collected-view-wheel/installed.xml` 和 `muferro-collected-dat-view/`。 [图契约](specs/stk-graph-v1.md)

Linux 原生脚本入口用桌面二进制 `757383af77` 和 Python 后端 `2eb64f04`。固定起点为英语 X11/Xvfb 1440×1000、缩放 1、软件 OpenGL、默认四区布局及空 Viewer。XTest 实际点击三次，依次打开 Python、聚焦代码区、运行缓冲区。其间用键盘选择与粘贴。脚本通过真实桥打开合成项目并调用 `stk.muferro.view`。原生 Viewer 显示 `muferro-collected-domains`、第 2 步、步选 `[0,2]`，图形负载有 140 个三角面。收集的 DAT 摘要和项目修订 8 保持一致。同样三次验收点击的复跑通过。验收后另点一次 Discard edits 清除合成脚本草稿，退出码 0，显示服务和子进程均回收。首轮留有未保存的合成草稿，退出超时后由脚本终止其进程。证据 `root-delivery-20261109-88/collected-native-review/evidence/clean-repeat/{native-receipt.json,ui-2.png,display.log}`。模拟面板 View 按钮仍待单独验收。

远端 `249698d05dc13d9c08a2aebd9e906ebc38873a9d` 的 Runtime 于 13:23:15Z 终态成功，13/13。Desktop 三个 Linux 作业通过。主作业于 13:37:07Z 完成，2134/2134，543.75 秒。macOS 到 Metal 后的必跑检查，Windows CPU 仍运行。`2eb64f04` 的新本地 Python 3.11 全量已启动，证据 `root-delivery-20261109-90/runtime-full311/`。本批仍在本地。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42621953348) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42621953590)

## 2026-11-09 13:17 UTC · S2c 响应字节、传输尝试与 MuFerro 报告

`95c2c4647ff3cf7220b8f3d8a64f8e50e419f2cd` 移除占位请求 ID 的大小估算。严格桥使用实际 NDJSON 响应，经正常校验、完整写出和刷新后才登记审阅。旧版在 128 个可转义字符的合法 ID 下返回 `result_too_large`，却登记了审阅。新例相差一字节的两侧分别拒绝和完整返回，超限后试批返回冲突且原决定未消耗。源码 111 项及隔离 wheel 45 项通过，安装态含子进程 stdout 和 shutdown。证据 `root-delivery-20261109-89/s2c-plan-wire-{red,source-final}.xml` 和 `s2c-wheel/installed-final.xml`。

`3924f39e3900b2761c1a29cbd3536d3e32c83c4f` 让已在等待同一终态 worker 的并发重试共享其后继尝试。旧版 Runtime/Hub 合成用例均会在后继迅速失败时额外启动第三次。新例保持单次后继，另一次明确重试仍可启动。独立候选两项连跑 15 轮均通过，root 源码联跑 150 项。PR #53 原问题已由更早主线处理，新反例使用独立当前主线补丁。证据 `root-pr-review-20261109-resume-generation/checks/` 与 `root-delivery-20261109-89/transfers-root.xml`。

`8da56052798f6d38c9dd9c917fbd9bc444346023` 在 MuFerro 收集和查看用普通文件读取。启动器报告维持 2 MiB 上限，解析复用摘要校验时捕获的字节。旧版的 FIFO 查看会阻塞，报告复开可换入另一条程序摘要。新例保留正常原生查看入口，拒绝 FIFO、链接与缺失产物，收集结果绑定原摘要。验证范围为单个文件，整个目录仍可在核验后变化。root 源码 157 过、3 条件跳过，收集和传输隔离 wheel 联跑 67/67。独立 Python 3.14 子集 99 过、1 条件跳过。目标 macOS、Windows 和真实许可未验证。证据 `root-delivery-20261109-89/muferro-collect-root.xml`、`result-transfer-wheel/installed.xml` 与 `hdf-collection-review/`。

`00831075` 集成 Claude47 的 `fcbcdc08`，六处相对链接可解析。作者 23 项定向通过，合成代理子进程和进程内 Hub 观察显示 `graph.meta` 走持久动作，现有响应不能区分 NumPy 或 h5py 是否可用。旧部署和真实执行节点待验。Claude48 已在独立 worktree 接手同一审批卡的冷重开。证据 `root-delivery-20261109-88/claude47/evidence/`。 [试点设计](design/mupro-executor-pilot.md)

远端 `249698d05dc13d9c08a2aebd9e906ebc38873a9d` Desktop 在 13:16Z 检查时仍运行，Linux 可重定位包与干净机冒烟已通过，Linux 主作业、macOS 和 Windows CPU 仍在构建。Runtime 8 项已过、5 项运行，文档部署和凭据扫描通过。修复监控导入后的 `d49f668535c9e8008bf9bd3f218ed445db100927` 在包含 Peer 依赖的干净 Python 3.11 环境全量 6437 过、180 跳过、4 排除，零失败，1186.45 秒。该轮对应此前监控修复头。证据 `root-delivery-20261109-88/runtime-full311/result.xml`。本批等待整轮 Desktop 终态后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42621953590) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42621953348)

## 2026-11-09 13:01 UTC · 直读、监控、Hub 回环及 Desktop 终态

`8a50e343240edd8fa07780a9286b0620ff323f67` 把 MuFerro DAT 帧和统计绑定到同一份私有快照。旧版本本机同时间戳和长度改写、Runtime 暖缓存改写、统计旧键污染三个反例均复现。新版本来源摘要跟随实际解析字节，自定义远程摘要不符和无效路径继续为 `invalid_data`。源码 256 过 2 条件跳过，隔离 wheel 242 过 1 条件跳过。证据 `root-delivery-20261109-88/dat-source-final.xml` 与 `dat-wheel/installed-final.xml`。

干净 Python 3.11 的 `a656f879` 全量含 Peer 依赖，6430 过、1 败、180 跳过、4 排除，1190.59 秒。失败是 root 早先的 MuFerro 安全打开改动让标准库监控模块加载连接器。`d49f668535c9e8008bf9bd3f218ed445db100927` 只在 MuFerro 调用端注入安全打开，通用 tail 保留非阻塞 FIFO 处理。源码与隔离 wheel 各 114 过 2 跳过，安装态独立导入也核对了 `sys.modules`。同头的新全量已在独立环境启动。证据 `root-delivery-20261109-87/runtime-full311/result.xml`、`root-delivery-20261109-88/monitor-import-green-final.xml`、`monitor-wheel/installed.xml` 和 `runtime-full311/`。

`7132755f` 集成 Claude45 对节点能力、实际执行与授权的区分。`c8618a4f0823addff5d577a403b6bad7f233b2c5` 把 Claude46 的 `b64da145` 证据合入既有本机 Hub、Node、Runtime 用例，目标重复 3/3，Hub 与 Desktop 桥联跑 57/57。真实断线时，列表保留最近心跳与读取能力，精确读取返回 Hub 503。测试仅模拟心跳老化，之后列表离线但保留快照，精确读取返回本地离线错误。真实重连后，同一节点刷新心跳并恢复原任务精确读取。观察期间原任务、动作行和动作事件相同。独立复核在原 Claude 候选移除本地离线门后得到预期失败。证据 `root-delivery-20261109-88/claude46-root-bridges.xml`、`claude46-root-repeat-*.xml` 和 `claude46-independent/`。

`ab86c2eebb1567c2dcacdd9d645d7faf871ca09d` Desktop 于 12:59:20Z 终态失败。三个 Linux 作业通过，主测试 2134/2134。Windows CPU 1460/1460，1179 项必需，932.58 秒。Windows 原生 6/6，1349.93 秒。PDF 20 轮、160 张图像，无捕获失败或遗弃会话，最长捕获启动 101 毫秒。该轮早于下一批的 Windows 分步探针，上一轮间歇卡顿的具体阶段仍待复现。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42611844039) [Windows 原生证据](https://github.com/sijintech/stk/actions/runs/42611844039/artifacts/13677191513)

同头 macOS CPU 1518/1518，Metal 254/254，原生基线 4/6，视频和 HTML 暂停未通过。两组可见对照各 2/2，第二次可见暂停分别在 38.76、45.38 毫秒取得原生暂停状态，并完成可见保持及后续 DOM 观察。三组隐藏对照各 0/2，quiet HTML 在隐藏前的初始显式暂停即失败。两个独立隐藏脚本返回 DOM paused，原生仍分别回复 30/30 与 28/28 次 Playing，触发看门狗。`e1cf1d47cc3b2cfd492afb1b41ead94ad21bd963` 补同会话的媒体代次、焦点、真实可见性和原生回复轨迹，Linux 原生窗口构建通过，证据门 12 项及 7 子测通过，Apple 条件分支语法和合成观察检查通过。Cocoa SDK 编译和原生轨迹待目标 CI。 [macOS 原生证据](https://github.com/sijintech/stk/actions/runs/42611844039/artifacts/13674470811)

## 2026-11-09 12:31 UTC · S2c 实窗审批、产物核验和最小安装

独立 `66b8eb58` 的 S2c 原生联合验收通过三次。固定起点为英语 X11/Xvfb 1280×1600、缩放 1、软件 OpenGL、a2 智能体区域最大化，已选原待批准卡片、Prepare 关闭。XTest 实际点击两次，先在 `(640,693)` 读取完整计划，再在 `(396,1023)` 批准。复核展示 3608 字节，按界面换行显示 128 行，审批前 Runtime 保持零任务。严格 Python stdio 桥与独立 JSON Schema 校验各通过一次 `run_plan` 和一次 `run_decide`。真实回环 Runtime 完成一个合成 MuFerro 任务，绑定原计划摘要与原案例行，在第一次尝试完成工作流，卡片进入原回执 Observe。批准后没有额外规划或直接任务写调用。Viewer、布局和会话选择一致，跟踪进程已回收。早期两次外部适配分别纠正 X11 坐标和产物回执字段，随后三次通过。证据 `root-delivery-20261109-87/s2c-native-receipt/evidence/run-05/receipt.json` 与三张截图。平台范围为 Linux 软件 OpenGL，使用脚本规划器和合成求解器。

`7daf672f9f77796c4dccfac139089b70458321ed` 让核验器和 MuFerro 末次监控读取普通文件，检查最后一级路径的符号链接、reparse 和文件身份。旧版本四类链接产物误判成功，独立核验和监控回放均能在管道处阻塞。六项复现修后通过。源码 135 过 3 跳过，隔离 wheel 112 过 2 跳过。另验默认读取和硬链接仍可用，Linux 普通文件在 `lstat` 后变为 FIFO 时能返回。Windows reparse 实机仍待 CI。证据 `root-delivery-20261109-87/verify-source-final.xml` 与 `verify-wheel/installed-final.xml`。

`a656f8797554259695d24da83dea39d0aabdd695` 集成 Claude44 `e0498ee0`。源码 175 过 1 跳过。根验三种离线安装表明 `[server]` 可列 Polar、energy、progress 元数据，能量行数未知且无总能量。DAT、表格和图运行索引缺 NumPy 时在打开数据前返回 `unavailable`。缺绑定仍为 `unknown_binding`。完整离线结果描述仍执行验证，按原契约读取 30 个 DAT 头和三类结果记录。NumPy-only 与 `[science]` 的值、事件和读取计数与直接父提交一致。证据 `root-delivery-20261109-87/claude44-installed/matrix_receipt.json`。 [D1 兼容门](planning/d1-compatibility-gates.md)

本地 `d02a5938` 的首次 Python 3.11 全量 6249 过、9 败、233 跳过、4 排除，19 分 58 秒。旧导入顺序用例通过，九条失败都是 Peer 身份相关测试。原环境缺 `cryptography`，同一源码在带该依赖的独立环境复跑九项全过。新一轮 `a656f879` 的 3.11 全量已在包含 `peer` extra 的干净环境启动，证据 `root-delivery-20261109-87/runtime-full311/`。

`ab86c2ee` Desktop 的 Linux 主作业 2134/2134，包与干净机也通过。macOS 正跑原生 WKWebView 和 ReportsEditor，Windows CPU 正跑测试，整轮仍未结束。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42611844039)

## 2026-11-09 12:12 UTC · 图文件字节、HDF5 依赖和 Windows 计时

`23ad9f90add2c07facf21a8edc0388a628c78393` 以实际文件字节规划本地缓存，Runtime 使用发布摘要。缓存未命中时校验解析用的私有副本。四个旧反例覆盖原时间和长度不变的本地改写、规划后两种本地改写及 Runtime 暖缓存改写，均在旧实现失败。新回归核对 VTKHDF 外部链接、外部虚拟数据集和外部原始存储被拒绝，同文件虚拟数据集、内部软链接与 VTI/legacy VTK 单位仍可读。无 `/STK` 描述符时，图数据集 ID 取绑定内文件名。源码、独立 wheel 各 206 项通过，两个性能基准按条件跳过。隔离首轮漏复制 `graph_testnodes.py`，补齐后整组重跑。VTI 和 legacy VTK 因原生库需要实际路径，正常退出清理具名副本。图缓存已配置时，强制终止后可能残留的副本纳入缓存暂存目录的裁剪。证据 `root-delivery-20261109-86/file-source-final.xml` 与 `file-wheel/installed-final.xml`。

`0a0b0f2f3946d5249fb689dba7497e323095b6a7` 在打开容器前检查 h5py/NumPy。源码 295 项通过、1 个性能基准跳过。三个独立 wheel 环境分别验证 `[server]`、NumPy-only 和 `[science]`。NumPy-only 的可选发现与索引从 6056/12112 字节降到零，仍可读取 DAT，HDF5 诊断为 `unavailable`。NumPy-only 和 `[server]` 的显式 HDF5 图均在 `node.started` 前拒绝，容器读零字节。`[science]` 读到合成 float32 第 4 步首值 100。没有真实许可输出或跨主机验收。证据 `root-delivery-20261109-86/f5-installed-review/matrix_receipt.json`。

远端 `ab86c2ee` Runtime 于 12:07:33Z 终态失败，8 项通过、5 项失败，五项都只失败在 `test_run_index_preserves_a_replacement_connector_table_reader`。按目录、模拟导入失败、替换读取器的固定顺序复现 2 过 1 败。`d02a59386de1384af6db92fb079401139e78a5cd` 只隔离目标模块并恢复 finder 后再检查，固定顺序 3/3，联跑 198 过 1 跳过，Python 3.11 与 3.14 定向各 163 过 1 跳过。`d02a5938` 的 Python 3.11 本地广跑仍在执行，环境与 hosted 矩阵的可选包有差异。证据 `root-delivery-20261109-86/ci-order-*.xml`。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42611844074)

`cd5ba5ae52961efd0cd3198f89e5303c7fead3db` 集成 Claude43 两个提交。Windows 验收捕获的慢启动有固定步骤、单调时间和独立的日志上限。Linux 独立合成对照把约 1030 毫秒的正常析构记入 `scope-exit`，把模拟异常展开记入 `failed-step-and-unwind`。现有证据门 12 项、7 个子测试通过。Windows 编译、真实 WGC 归因及一直不返回的调用尚无证据。`ab86c2ee` Desktop 已通过 Linux 包和干净机，整轮仍在运行。证据 `root-delivery-20261109-86/wgc43b-root/`。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42611844039)

## 2026-11-09 11:45 UTC · Desktop 推送门和 HDF5 最小安装

`15531049c5c027153c232a2c4ac82c13deb6fe55` 的 Desktop 整轮于 11:45:32Z 终态失败。Linux 三项及 Windows CPU 通过，macOS 原生失败。Windows 原生六项执行五项通过，唯一失败 `reports_native_pdf_opengl` 耗时 134.26 秒，PDF 重新准备后等待第一页像素超时。视频和 HTML 视频通过。JUnit 记录零跳过，后续必需用例检查因 CTest 失败未运行。第一轮重准备阶段启动捕获一次即耗时 120070 毫秒，零轮询、采样和宿主帧。可见及关闭前已有七张有效截图，原重试条件尚未触发。工件已上传，本地新批可以推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42601829902) [Windows 原生](https://github.com/sijintech/stk/actions/runs/42601829902/job/129130779464) [Windows 工件](https://github.com/sijintech/stk/actions/runs/42601829902/artifacts/13669449664)

`d2fcfc72` 收录 Claude42 在 `1980660f` 干净 wheel 的 `[server]` 与 `[science]` 合成读取验证。root 另用单装 NumPy 的隔离 wheel 确认 DAT 和运行索引可用，HDF5 发现和显式图读取报 `unavailable`。`[server]` 缺 NumPy 时，DAT 帧、含能量表的连接器描述及图运行索引失败。证据 `root-delivery-20261109-85/claude42/evidence/` 与 `hdf5-optional-numpy-only/probe.json`。 [D1 兼容门](planning/d1-compatibility-gates.md)

## 2026-11-09 UTC · 真实 Hub 原生任务与 MuFerro case

`1980660fb92c758ffe872fdff5ce7178761bde17` 集成 Claude41 的真实单机 Hub、NodeAgent、Runtime 和 C++ 桥。根构建的 bridge 标签 71/71，零跳过。两个新用例验证窗口外精确读取、对窗口内合成且 Runtime 不存在的任务明确报错、离线可重试和同一节点重连、代理探针零连接及关闭。作者负对照让快照代替实时读取、让离线生成虚构终态以及让夹具异常退出，测试均拒绝。证据 `root-delivery-20261109-85/claude41-root.xml`。

独立 `af106b9c` 加测试适配的 Linux/Xvfb 试验通过两轮，每轮约 34.69 秒。同一适配的两项原有脚本化用例通过。固定起点为英语 1100×980 OpenGL 原生窗口，Jobs 最大化，预选合成 Hub 的原节点及工作区、尚未选择任务。实际 XTest 点击任务行一次、Refresh 两次。运行中选择成立后，真实 NodeAgent 退出且原 Runtime 任务仍运行。离线刷新后详情保留运行中并显示观察不可用，列表为空。原任务在 NodeAgent 停止期间完成，同一配置重连后任务仍在 200 条合成心跳窗口之外，恢复刷新显示成功且已核验。严格桥审计三次同任务精确读取、零提交和取消，清理无遗留进程。独立适配和运行器留在 `root-delivery-20261109-85/jobs-real-f03/`，第二轮 `evidence/real-02/receipt.json` 含源码及工件摘要。范围为本机 Linux，尚缺跨主机及其他系统联合证据。

`ea035adf9603deba62012e7befa36dc1a5bae167` 核对图索引实际消费的 `input.toml` 与 include，拒绝计划后字节变化和 Runtime 暖缓存中不符的已发布内容。未发布或无效 TOML 的原诊断与 DAT 回退可重现，已发布的读取失败按错误返回。对照覆盖相同时间和长度、本地其他扩展名、超过 64 个无关 TOML、缺失依赖补齐，以及已发布依赖不可用、消失和超限。源码与从独立目录加载的 wheel 各 270 项通过、4 项跳过，后者为两个可选性能例、Windows junction 和真实许可 MuFerro。隔离安装首轮少复制公开 DAT 夹具，两个旧测试找不到数据，补齐后全量重跑。证据 `root-delivery-20261109-85/case-root-source.xml` 和 `case-wheel/case-installed-final.xml`。

`15531049` 的 Windows CPU 已完成，1460/1460，1179 项必需，930.24 秒。Linux 三项通过，macOS 原生失败，Windows 原生仍运行。Runtime 同头终态 8 通过、5 失败，五项作业的目录同步错误已在本地 `9c1255a6` 修复。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42601829902) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42601829951)

## 2026-11-09 UTC · 撤权观察与原生窗口

`9f4a9f4d545ba84df1c1c3108cd970a0c06faad6` 在真实回环 Hub 和 Runtime 中复现节点撤权后仍能从桥读取工作区快照。修复后旧快照仍在 Hub 内部记录，桥的工作区列表、任务列表、普通及精确任务读取返回 `unauthorized`，原 watch 最终以相同错误结束，动作记录数保持一致。源码相关 109 项通过，隔离 wheel 定向两项通过。 [桥契约](specs/stk-desktop-bridge-v1.md)

`322d408489bd68f1f7080d622b127639e5cbcc01` 集成 Jobs 选中任务的最近事实和实时观察。含掉出心跳窗口、晚到答复、原节点撤权及重获授权、旧取消确认、桥重启、节点已列出但离线等回归。旧 Hub 明确返回 `Unsupported` 时，原节点仍在线且原任务仍列于当前心跳并可取消，才沿用取消入口。主工作树 Jobs 46 项、报告相关 19 项通过，零跳过。原生点击采用英语 1100×980 Xvfb/OpenGL 窗口，Jobs 最大化，固定预选 `mesh/node1/hub-ws`、无选中任务。三次点击依次为任务行、离线刷新、恢复刷新。原任务从运行中和观察不可用变为成功和核验成功，共三次精确读取、零提交和取消。独立构建生成的两张截图摘要与候选一致。点击用例使用脚本化 Hub，真实 Hub 故障与原生点击的联合验收待执行。

远端 `15531049` macOS 首轮可见暂停两项通过，原生基线 4/6，采样、静默和隔离隐藏对照各 0/2，均零跳过。可见窗口收到非 Playing 回执约 54 和 41 毫秒，约 1.25 秒保持期间无 DOM 采样，之后同一导航已暂停。两项首次 DOM 播放位置回退约 64 和 65 毫秒。隔离隐藏组脚本返回 paused，原生各 27 次 Playing，约一秒后结束会话。 `c634dca502ae5d78efeb51e5056c323b8cd05524` 增加两项第二次可见诊断，沿用静默隐藏组的首次播放、暂停和重播历史，分叉点在第二次暂停，保留原核验截止并单独记录播放位置差。Linux 构建、Apple 条件分支 C++ 语法及 CTest 注册检查通过，实际 WebKit 待目标 CI。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42601829902/job/129107929609) [官方工件](https://github.com/sijintech/stk/actions/runs/42601829902/artifacts/13668346276)

同头 Linux 三项通过，Windows CPU 仍运行。整轮 Desktop 终态后推送本批。Claude41B 的真实 Hub 测试隔离和清理仍在验证。证据见本机 `root-delivery-20261109-84`。 [Desktop](https://github.com/sijintech/stk/actions/runs/42601829902)

## 2026-11-09 UTC · 图目录同步与 DAT 实际字节

远端 `15531049c5c027153c232a2c4ac82c13deb6fe55` Runtime 于 10:54:41Z 终态 8 成功、5 失败。五个作业各只失败 `test_catalog_is_in_sync_with_declarations_and_spec`，JSON 声明比较通过，Markdown 生成器删除了生成区中的手写段落。root 在远端原提交的副本复现，单独移动段落后定向测试通过。 `9c1255a60064615927f111a44a6139c0d618f461` 将内置 MuFerro 说明放到节点语义区。本批完整目录回归通过。 [Runtime](https://github.com/sijintech/stk/actions/runs/42601829951)

`ff5e615f32b7d4fe66513b30ea467235e8a30dcc` 使 MuFerro DAT 场帧按本地实际字节或 Runtime 发布摘要规划，缓存未命中时复制并校验临时文件，再解析同一文件句柄。三条旧反例涵盖等长改写并恢复 mtime、规划后换帧、Runtime 暖下载被改写。Linux 探针在解析前持有 3066 字节已核验快照，强制终止后无具名文件残留。固定宽度与空白回退解析从路径或调用方持有的文件均得到相同数组。源码 175 通过、2 项性能跳过，隔离 wheel 149 通过、1 项性能跳过。Windows 文件回收行为待目标 CI。证据见本机 `root-delivery-20261109-83`。 [图契约](specs/stk-graph-v1.md)

同头 Desktop 仍运行，Linux 包和干净机通过，macOS 原生基线已开始。Jobs 修订候选在独立副本，真实 Hub 的 C++ 路径继续验证。 [Desktop](https://github.com/sijintech/stk/actions/runs/42601829902)

## 2026-11-09 UTC · 完成标记与计划

`fff8d77a6f2216ddf223c184dcd05ecf4e9e1715` 在内置 run-index 核对完成标记的存在性，变化返回 `invalid_data`。两个旧反例在标记出现或消失后恢复原状态，仍从旧键读到错误的 `frames.attrs.complete`。修后恢复原状态会重新求值，下一次可命中正确缓存。实时帧完成属性结合标记存在性与缺帧检查，标记正文由显式核验处理。源码和隔离 wheel 各 97 项通过，性能基准各跳过一项。证据见本机 `root-delivery-20261109-82`。 [图契约](specs/stk-graph-v1.md)

远端 `15531049` 已通过 macOS 构建、Linux 包和干净机，Desktop 整轮仍在运行。Runtime 8/13 项已成功，其余运行中。 [Desktop](https://github.com/sijintech/stk/actions/runs/42601829902) [Runtime](https://github.com/sijintech/stk/actions/runs/42601829951)

## 2026-11-09 UTC · 原生 C++ 实时读取与 MuFerro 表格

`85015dc1d4e88b6cd0a253ec8fb76071adb59069` 集成 Claude40 `c7b9f983e58e12a02fb28afa17563f5113dd3a21`。C++ 桥两参及显式 false 发送省略字段的请求，true 发送布尔值 `require_live`。原生测试校验完整 Target 和 task ID、桥重启后重发以及严格 Python 桥的错误映射。作者 Linux 桥测试 64 项，root 独立 Linux 构建的桥及相关 schema 共 66 项通过、零跳过。真实 Hub 的 Python 证据已在 `49169e0e`，C++ 到真实 Hub 的完整成功路径由 Claude41 复验。 [桥契约](specs/stk-desktop-bridge-v1.md)

`3ff96c0a2ca6cc0282d6562dc7f48b13c91fc255` 让内置 MuFerro 能量和进度表核对计划中的存在性与摘要。能量表与 QOI 共用一次解析，清单记录同一摘要。本地和自定义来源按实际字节规划，Runtime 按发布摘要计划并核对读取字节。八条旧反例涵盖出现、消失、追加、改写及暖缓存，另补自定义来源短读。恢复原内容后可重新求值。源码和隔离 wheel 各 95 项通过，性能基准各跳过一项。替换连接器调用和直读 DAT 回归通过。 [图契约](specs/stk-graph-v1.md)

远端 `15531049c5c027153c232a2c4ac82c13deb6fe55` 已核对推送。新 Desktop 与 Runtime 正在执行，Secret scan 和部署成功。Jobs 的原生 UI 证据待独立候选。证据见本机 `root-delivery-20261109-82`。 [Desktop](https://github.com/sijintech/stk/actions/runs/42601829902) [Runtime](https://github.com/sijintech/stk/actions/runs/42601829951)

## 2026-11-09 UTC · Windows 原生终态和 Cocoa 首轮可见对照

远端 `3d2fcea7fa25ef1c210b453f63a32c37494ad846` Desktop 于 10:32:33Z 终态 failure。Windows 原生作业 10:32:32Z 终态 success，六项必需 CTest 与零跳过检查通过，工件上传通过。Windows CPU 与 Linux 三项成功。macOS CPU 1516/1516、Metal 254/254，原生基线 4/6、三个隐藏对照各 0/2。Runtime 13 项、Docs 和 Secret scan 成功。 [Desktop](https://github.com/sijintech/stk/actions/runs/42593218935) [Windows 作业](https://github.com/sijintech/stk/actions/runs/42593218935/job/129097962786) [Runtime](https://github.com/sijintech/stk/actions/runs/42593219053)

`2308c680216b99e6026e005edec77e52802b55ed` 在原生报告视频和 HTML 视频各加入首轮播放后的可见暂停诊断。调用同一生产暂停入口和原一秒看门狗，等候期间泵送事件，之后再做 DOM 采样。工件记录媒体与导航代次、各阶段可见性、原始 WebKit 状态、关闭前可见性和播放时间差。基线的暂停历史与隐藏对照不同，结果分别解释。Linux 原生报告目标构建、Apple 条件分支的纯 C++ 语法、19 项 CTest 及两项新 CTest 注册检查通过。Cocoa 编译和实际 WebKit 结果待目标 CI。证据见本机 `root-delivery-20261109-82`。

## 2026-11-09 UTC · X7 Hub 进程停止期间完成

`07f2f2a940ac83a4a30181e49f75b8bdd8a2c106` 集成 Claude39 `af9addabb99732a16dde891d6171a81af9dc9f09` 与 `6a10a8ac6f6fa70d8c94c8f5ed19239023616d73`。真实单机先冻结已成功的提交动作，终止并回收 Hub 进程后让同一任务自然完成，再恢复同配置 Hub。停机期间精确读拒绝，恢复后首个精确答复为同一任务成功，固定产物及日志校验通过。核对一个 Runtime 提交入口、匹配成功返回和前后绑定的动作请求。root 增加已知阶段的字段类型检查，旧版接受的缺字段和布尔型调用序号现计入无效记录。

最终源码相关 323 项通过。真实源码与 Python 3.12 隔离 wheel 的 `-I` 运行各取得停机完成 13/13、默认丢回执 11/11，清理通过。证据限单机合成任务。Claude40 已从该头接手 C++ 可选精确读取。远端 `3d2fcea7` 的 Windows 原生仍运行，整轮未终态。证据见本机 `root-delivery-20261109-81`。 [场景](../examples/backend_parity/HUB_RESTART.md) [Desktop](https://github.com/sijintech/stk/actions/runs/42593218935)

## 2026-11-09 UTC · 启动报告身份和 macOS 暂停

`64c55c4d2ef905a637a2e87753edc50bb72f8164` 让内置 MuFerro 图索引从同一份有界报告字节选目录并生成摘要，执行时核对报告存在性和实际字节。四个旧反例在规划后换目录、改状态、加入或删去报告，均错误接受。修后返回 `invalid_data`，恢复后重新求值，再次读取可命中正确缓存。附加验证覆盖名为 `auto` 的实际目录、Runtime 缓存等长改写并恢复 mtime、DAT 在格式异常或报告超限时可用，以及替换插件的旧签名。源码与隔离 wheel 各 84 项通过、各一项性能基准按条件跳过。证据见本机 `root-delivery-20261109-81`。 [图契约](specs/stk-graph-v1.md)

远端 `3d2fcea7fa25ef1c210b453f63a32c37494ad846` 的 macOS CPU 1516/1516、Metal 254/254，原生基线 4/6，采样隐藏、静默隐藏和隔离暂停各 0/2。隔离脚本在同会话及导航确认 paused，原生状态分别连续 27、28 次为 Playing，看门狗在首次隐藏 DOM 采样前关闭。采样组原生分别连续 24、25 次 Playing。静默组在隐藏前的显式暂停时间下限失败。工件摘要与 GitHub 相同，20 条日志观测与工件一致。下一轮将保持视图可见至原生暂停核验完成。Windows CPU、Linux 三项通过，Windows 原生仍运行，整轮未终态。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42593218935/job/129079596628) [官方工件](https://github.com/sijintech/stk/actions/runs/42593218935/artifacts/13664494326)

## 2026-11-09 UTC · 图来源内容和 D2 精确读取

`dd41ba5e0aaeaf7288233e294c6b0929b1701485` 按实际字节建立表格缓存键。普通及自定义来源有界流式散列，Runtime 绑定发布摘要。解析前用读到的字节核对，失配返回 `invalid_data`，无错误缓存。等长改写并恢复 mtime 的两条原始反例分别命中旧表和错误接受新值；自定义 memo 反例也复现。修后重新求值并按实际摘要写入来源。表格实现升为 3，源码联跑 89 项通过，1 项性能基准按条件跳过。 [图契约](specs/stk-graph-v1.md)

`c95a6f26282aaf9ed0578442afe916aaaf38e26e` 核对 HDF5 实际流与 Runtime 已发布摘要。五个旧反例覆盖暖缓存等长改写后的发现、重开、索引与读字段，以及下载前清单改变。修复后返回 `invalid_data`，恢复原内容后可沿用原下载。源码相关 247 项通过、2 项条件跳过，Python 3.11 和 3.14 定向各 39 项。合并构建的隔离 wheel 中图和 HDF5 共 88 项通过。未改写共享 Runtime 缓存对象。 [HDF5 契约](specs/mupro-hdf5-1.md)

`49169e0eb43065dca6b3f35036d47aba0b7c1cc4` 为桌面桥 `task.get` 增加可选 `require_live`。真实单机 Hub 中，桌面、Python 和 CLI 读取到已离开心跳窗口的原任务，断线返回 `unavailable`，旧能力返回 `unsupported`，普通调用保留有界快照。对不存在的原任务，Hub 沿用 `remote_error`，直连是 `not_found`。读取未新增任务、动作或动作事件。源码相关 132 项通过，隔离 wheel 定向六项及重新嵌入 schema 后的七项 C++ 测试通过。JSON 对照确认只增加一个可选布尔参数。 [桌面桥契约](specs/stk-desktop-bridge-v1.md)

Claude39 `af9addab` 的源码相关 463 项通过，源码及隔离 wheel 的 Hub 停机完成各 13/13、默认丢回执各 11/11，清理通过。审阅复现两处验收缺口，失败的第二次提交未计入调用次数，缺失的动作请求可得到相同空摘要。已派发收口，集成待最终证据。远端 `3d2fcea7` Runtime 13 项、Desktop Linux 三项与 macOS CPU 和 Metal 已通过，原生验收未终态。证据见本机 `root-delivery-20261109-80`。 [Desktop](https://github.com/sijintech/stk/actions/runs/42593218935)

## 2026-11-09 UTC · X7 节点离线完成与 HDF5 索引

`3a7928f828ad08d67990be4694441760a4ee7e32` 集成 Claude38 `e31d1f2954e3fef1c8cae4387c21e74013adbf73` 与 `58aebf21caa314db24fd0d09cc78cad011e3313e`。真实单机 Hub、NodeAgent 和 Runtime 验证原任务在节点退出期间完成，原程序和 worker 已退出，完成前后各两次精确读取均明确拒绝，同配置重连的首答复为同一任务成功。读取固定日志和唯一 `out.txt`，保留一次创建和一次提交的动作账本。root 补到期及逾期答复和四种缺失/非布尔状态的反例，旧六例失败，新源码 151 项通过。新隔离 wheel 以 `-I` 验证取消 10/10、离线完成 12/12，实测 26.96 与 28.82 秒，清理通过。证据限单机合成任务。 [D1 矩阵](planning/d1-compatibility-gates.md)

`d2bf693bb0dd450ac0fce364cb1719910ea125a4` 在 MuPRO 图索引执行时拒绝已绑定摘要的容器超限、消失或读取失败，避免将 DAT-only 结果写入原缓存键。旧实现四种反例返回成功。真实稀疏探针将容器由 6,056 字节扩为 1 GiB + 1，修复后拒绝，恢复原字节和 mtime 后重新求值并取到两个 HDF5 字段。规划时已知的可选错误及通过摘要核对的格式错误仍保留 DAT。实现版本升为 3，发布节点仍为 v1。源码相关 210 项通过、2 项条件跳过，root 源码和隔离 wheel 各 73 项通过。Python 3.11、3.14 定向各 34 项。 [HDF5 契约](specs/mupro-hdf5-1.md)

`7366d117` 单独采纳 PR #53 的 `transfer.resume` 表项勘误。当前主线实测取消后同键重放保留原记录，显式同 ID 恢复可发布校验正确的字节。PR 的立即写入排队意图和 worker 循环仍需修订，原竞态已有主线回归。 [PR #53](https://github.com/sijintech/stk/pull/53) [桥接契约](specs/stk-desktop-bridge-v1.md)

远端 `3d2fcea7` Runtime 13 项于 09:42:02Z 全过。Desktop 的 macOS 目标编译和 Linux 包与干净机已通过，原生对照待执行。当前本地批次待整轮终态。证据见本机 `root-delivery-20261109-79`。 [Runtime](https://github.com/sijintech/stk/actions/runs/42593219053) [Desktop](https://github.com/sijintech/stk/actions/runs/42593218935)

## 2026-11-09 UTC · 冻结子任务准备及 WGC 空捕获

`862208e6986845bc3fedf098aaa57e7906609a89` 在每次子任务准备与修订重试中，用传给引擎的同一项目修订核对冻结行。真实 loopback Runtime 和合成 MuFerro 的两条反例分别在早期检查之后、引擎首次准备入口编辑温度。旧版两例均创建任务，修复后均返回 `row_changed`，无新工作区、子计划或任务，下游分析仍待处理。源码工作流和智能体相关 109 项通过，1 项为真实许可条件跳过。root 源码定向 3 项和隔离 wheel 48 项通过。隔离夹具从 wheel 复制纯数据的 volume preset，以支持测试原有的相对路径。已有接管、取消和 LAMMPS 回归通过。

`10ecf59bea890e7baa72b92bc657e8c75a3565cd` 处理 Windows 非媒体报告截图阶段持续空轮询的情况。连续两秒无样本时关闭原采集会话及帧池，再在同一窗口启动新会话。每阶段最多放弃两次空会话，维持 45 秒截止和两次独立采样的像素判据。失败证据记录启动及轮询次数、空轮询、实际宿主帧、阶段和视口状态。Linux 相关 45 项及独立 C++ 边界检查通过，实际 WGC 恢复待目标验证。

完整 `bc25f579` Windows 工件显示 PDF 第五轮重新准备已取得第六个桥会话，并绑定同一冻结 PDF。前四次重准备的首页截图字节相同。失败轮最后保存关闭态，重准备阶段既无通过图也无等待图。适配器源码与此前同类失败的头一致，夹具已有 50 毫秒宿主重绘。已证据化无可保存的截图样本，具体空会话或同步等待机制仍待带新计数的实测。证据见本机 `root-delivery-20261109-76/windows-bc25-review` 和 `root-delivery-20261109-78`。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42584441296/artifacts/13661772980)

远端 `3d2fcea7` Desktop 和 Runtime 仍运行。Linux 包和干净机、Docs 与 Secret scan 已通过。当前本地批次待该 Desktop 整轮终态。 [Desktop](https://github.com/sijintech/stk/actions/runs/42593218935) [Runtime](https://github.com/sijintech/stk/actions/runs/42593219053)

## 2026-11-09 UTC · bc25f579 Desktop 终态

精确 `bc25f579b9c4ddd645145f7c7d29963dbb6ea7f6` 的 Desktop 于 09:22:41Z 终态失败。Windows 原生作业于 09:22:40Z 结束，六项均执行且五项通过，`reports_native_pdf_opengl` 在重新准备后等待 `reprepared-page1` 的 OS 像素超时。Windows CPU 1460/1460，Linux 三项通过。macOS 原生 4/6，定位前采样和静默隐藏各 0/2。Runtime 13 项通过。整轮终态满足下一批推送门，目标平台结果继续逐项验收。 [Desktop](https://github.com/sijintech/stk/actions/runs/42584441296) [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42584441296/job/129068743682) [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42584441296/artifacts/13661772980)

## 2026-11-09 UTC · 快照发布摘要与 Cocoa 暂停动作对照

`7eb7782206f425bdeb99e0cda25b3cfb42be2aa6` 把工作流收集回执的逐文件 SHA-256 传到快照的实际复制路径。合成 HDF5 在项目文件登记后将 Polar 从 1 改为 9，旧执行器接受并发布改写字节。候选在对象入库前拒绝，快照、改写对象和临时文件均无记录，已完成的文件登记保留。恢复原字节后同一路径捕获成功。共享入口也覆盖 LAMMPS。精确源码联合 129 项通过，1 项为真实许可条件跳过。root 另验源码 36 项与隔离 wheel 23 项。 [桥接契约](specs/stk-desktop-bridge-v1.md)

`41ac8fdf50d08ae48ef1f9b060ad6e019d1d50f6` 为独立和 HTML 视频各注册一项 Cocoa 隔离暂停对照。仅对匹配的可见测试会话和导航启用一次固定暂停动作。原生状态查询、一秒截止、无隐藏期 DOM 采样、重显无自动播放和画面验收继续作为门槛。工件区分脚本回执与原生验证。Linux 构建验收程序并联跑 45 项，三组各两项的 CTest 入口、CI 名称与工件目录一致。提取脚本的六种模拟结果通过。实际 WKWebView 编译及行为待目标 CI。 [CI 定义](../.github/workflows/desktop.yml)

完整 `bc25f579` macOS 工件已下载，五份 JUnit 与六份视频结果的摘要已绑定，官方日志的十六个媒体观测与工件逐项一致。Windows CPU 1460/1460，原生在本记录时仍运行。证据在本机 `root-delivery-20261109-76` 和 `root-delivery-20261109-77`。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42584441296/artifacts/13661187057) [Desktop](https://github.com/sijintech/stk/actions/runs/42584441296)

Claude38 `e31d1f29` 作者源码 335 项，隔离安装原取消 10/10、离线完成 12/12。实际原任务在离线期间结束，重连前两次精确读取均不可用，恢复同节点后读取原任务成功和固定产物。审阅复现重连助手跳过已答复的排队状态，且发现候选在校验清单前使用远端描述下载。收口任务已派发，待集成和主线复验。 [D1 矩阵](planning/d1-compatibility-gates.md)

## 2026-11-09 UTC · 日志端点绑定、冷恢复和 Cocoa 静默对照

`0d414c8a90efb2ad13183b3d9c910bfd3f01d20b` 为 `task.logs` 增加可选 `expected_connection_identity`，沿用严格桥在实际后端对象上的检查。MuFerro 桌面与历史入口各验证稳定连接、刷新后切换及 stdout 之后切换。旧代码四个切换用例读取替换端点，修复后返回 `conflict` 且替换后端无日志调用。原 stdout 在第二条读取被拒绝前已输出。桌面共享入口同样应用于 LAMMPS。原有通用日志脚本仍可省略该字段。 [桥接契约](specs/stk-desktop-bridge-v1.md) [MuFerro 工作流](simulation-muferro.md)

`bd5b7e91d6401aaad850e70be9f9069bd1a63f7d` 集成 Claude37 `13874a2898a0af9c8a7c55a62a9c3775b7af1db6`。两个传输管理器实例通过实际持久日志验证冷恢复。替换端点在描述、读取及创建目标目录前被拒绝，恢复原端点后同 ID、原请求及身份完成校验和原子发布，重复启动同键仍只返回该日志。范围为实际传输管理器与内存后端。作者移除守卫的隔离反例在预期断言失败。

Linux 源码原生分派与 MuFerro 53 项通过、1 项真实许可条件跳过。候选精确源码的端点绑定、传输、Runtime 桥和脚本 63 项通过，隔离 wheel 同组 63 项及日志/分派定向 7 项通过。Python 3.11 和 3.14 的六个日志用例均通过。Linux 重新构建 C++ 嵌入 schema，七项通过。发布 schema 对照确认只增加该可选参数。证据见本机 `root-delivery-20261109-75`。

远端 `bc25f579` 的 macOS 作业于 09:04:11Z 终态失败。CPU 1516/1516，Metal 254/254，原生 4/6，定位前采样对照 0/2，静默隐藏对照 0/2。两项静默对照在首次 DOM 观察前由原生暂停校验关闭同一会话。两者在可见时派发并收到 ACK，导航代次均为 1，关闭前分别连续收到 28 和 25 次 Playing。独立视频由超过期限的回复触发关闭，HTML 视频由 watchdog 触发。带采样对照的独立视频通过 0.777 秒的 DOM 观测后仍被 watchdog 关闭。带采样的 HTML 视频更早在显式暂停的时点断言失败。Desktop Linux 三项和 Windows CPU 通过，记录时仅 Windows 原生仍运行。本地批次待整轮终态。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42584441296/job/129050766481) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42584441296/artifacts/13661187057) [Desktop](https://github.com/sijintech/stk/actions/runs/42584441296)

## 2026-11-09 UTC · MuFerro 收集端点前置条件

`5821e025c5f28ff89eb984c8aa0b5a71f9e5bf00` 采用 Claude36 `1150229f0de21df4ce302a980ed5c96f74eeb9ae` 方案，在 `task.artifacts` 与 `download.start` 增加可选 `expected_connection_identity`。MuFerro 使用冻结计划的身份和节点。两项旧代码反例分别在刷新后、产物列表后观察到替换后端调用，修复后均返回 `conflict`，替换后端无产物调用且无新传输日志。默认缓存目录保留私有权限，匹配日志可返回原传输，身份缺失或不符时拒绝带前置条件的重放。冷重启在错配后端上恢复时拒绝传输。

最终 Linux 源码桥、传输与脚本联合 99 项通过，MuFerro 和智能体联合 54 项通过，1 项为真实许可条件跳过。隔离 wheel 桥 51 项和 MuFerro 真实合成 Runtime 定向一项通过。Linux 重编原生嵌入 schema，七项 schema 测试通过。结构对照确认发布 schema 只增加上述两个可选参数及共同格式。证据在本机 `root-delivery-20261109-74`。 [桥接契约](specs/stk-desktop-bridge-v1.md) [试点接线](design/mupro-executor-pilot.md)

远端 `bc25f579` Runtime 13 项和 Desktop Linux 三项已通过。Windows CPU 与 macOS 尚运行，Cocoa 静默隐藏对照仍待本轮执行。本地批次待 Desktop 整轮终态。 [Desktop](https://github.com/sijintech/stk/actions/runs/42584441296)

## 2026-11-09 UTC · 已收集 MuFerro 结果、F9 与 Windows 联接点

`6cae6312daa20df12a2aacd893278a146bc764cd` 在 MuFerro 项目收集及调用 Viewer 前拒绝未登记的原生产物。保留原文件字节，仅新增合成 `Polar.00000099.dat` 时，通用目录读取的最新 Polar 从第 2 步变为第 99 步。旧项目收集与查看分别接受这一反例。修复后两入口拒绝新增帧、HDF5 和能改变自动案例目录的启动器报告，普通备注及移除额外文件后的查看仍通过，拒绝时项目修订保持。Linux 源码 32 项通过，1 项真实许可条件跳过。隔离 wheel 定向通过。范围为稳定本地文件与 Viewer 打开前的工作流检查。 [项目工作流](simulation-muferro.md)

`5ddcdf1709f14e72dce6cb83ac76100f59b6f62f` 集成 Claude35 `eade871d878d35ea05b266ace00479ee22e8244d`。真实 UDP 未找到回执时仍将授权水位推进至 1，之后同 inode 恢复修订 0 触发持久撤权。恢复的数据库字节、历史与回执表保持，后续查询和写入被拒绝。Linux 源码 173 项和隔离 wheel 定向一项通过，零跳过。隔离反例仅跳过失败查询后的水位更新，在预期断言处失败。 [CP-0 矩阵](design/cloud-project-service.md)

另用内存后端确认手动收集的连接切换。刷新后切换时，产物查询走替换连接。产物清单后切换时，下载描述走替换连接。两项探针使用真实严格桥与合成后端对象。方案待审，证据见本机 `root-delivery-20261109-73/frozen-target-repro`。

远端 `bc25f579` Runtime 13 项于 08:33:54Z 全部通过。Windows 客户端 3.11.9 和 3.12.10 各 5141 通过、266 跳过、654 未选。对齐同提交收集顺序与官方模块进度和跳过清单，CLI 与项目导入的真实 `mklink /J` 用例在两个作业均通过。官方日志以模块进度显示，核对记录在本机 `root-delivery-20261109-73/windows-junction`。Desktop 仍运行，本地批次待整轮终态后推送。 [Runtime](https://github.com/sijintech/stk/actions/runs/42584441104) [Windows 3.11](https://github.com/sijintech/stk/actions/runs/42584441104/job/129050765928) [Windows 3.12](https://github.com/sijintech/stk/actions/runs/42584441104/job/129050765950) [Desktop](https://github.com/sijintech/stk/actions/runs/42584441296)

## 2026-11-09 UTC · CLI 成功条件、F8b 与 bc25f579 CI

`8bf086068ae9a0e02873f2236a791c268e2daf2f` 使 `suan mupro result` 在报告校验通过后再读取原任务状态，只有 Runtime 成功才返回 0。实际合成求解器完成并写入通过报告，Runtime 因缺少另一个必需产物判失败。取消态客户端夹具也保留通过报告。两例旧 CLI 都退出 0，修复后退出 3，仍打印并另存报告。Linux 源码 80 项、隔离 wheel 64 项通过，各有 Windows 联接点与真实许可两项条件跳过。Python 3.11、3.12、3.14 的 Linux 结果命令定向各三项通过。 [命令文档](runtime-mupro.md)

`210036e303be1b3a379cd183da2faf4dc58296e3` 集成 Claude34 最终 `a7572ba923583021b7142996b606d27cf216e9ee`。真实已认证 UDP 首次观察到字节相同、inode 不同的数据库替换后，持久撤销绑定、授权及旧连接权限。恢复原 inode 后须显式重新绑定。新连接在新授权下读取原内容，原回执保持在旧 scope。Linux 源码 172 项和隔离 wheel 定向一项通过，零跳过。隔离反例屏蔽 inode 变化后在预期的首次拒绝断言失败。证据在本机 `root-delivery-20261109-72`。 [CP-0 矩阵](design/cloud-project-service.md)

精确远端 `bc25f579b9c4ddd645145f7c7d29963dbb6ea7f6` 已推送。Docs 与 Secret scan 通过，Runtime 和 Desktop 核对时仍运行。本地后续提交待当前 Desktop 整轮终态后推送。 [Runtime](https://github.com/sijintech/stk/actions/runs/42584441104) [Desktop](https://github.com/sijintech/stk/actions/runs/42584441296)

## 2026-11-09 UTC · bb4cea9d 终态和主线新批次

精确 `bb4cea9df632e3a0fd7b107694a7dff56052190e` Desktop 于 08:11:18Z 终态失败。Linux 三项通过，Windows CPU 1460/1460 和原生六项全过，Windows 原生作业于 08:11:17Z 终态。固定 Mesa 26.2.4 的 70,257,286 字节存档通过校验并解包。macOS CPU 1516/1516、Metal 254/254，原生 4/6、定位前隐藏 0/2。Runtime 13 项通过。本地 Cocoa 静默对照、Windows 联接点和同批修复随下一轮验收。 [Desktop](https://github.com/sijintech/stk/actions/runs/42576437438) [Windows 原生证据](https://github.com/sijintech/stk/actions/runs/42576437438/artifacts/13658685452) [macOS 原生证据](https://github.com/sijintech/stk/actions/runs/42576437438/artifacts/13657571015) [Runtime](https://github.com/sijintech/stk/actions/runs/42576437407)

`6dacac4084c775564a673afff75e933ad9cf0f22` 集成 PR #53 的取消锁调整。测试让真实下载完成并等待 worker 退出，再放行已到达管理锁的取消。旧代码把日志从 `completed` 改为 `cancelled`。修复后取消返回原完成态，下载字节、日志字节与事件保持。Linux 源码联合 44 项全过。 [PR #53](https://github.com/sijintech/stk/pull/53)

`bdae4432b7140815822c396ead1827f493dc68e7` 要求 MuFerro 项目收集的报告 v1 与求解器整数退出码、成功状态和原生复验一致，程序摘要须符合 SHA-256 格式。用真实合成 Runtime 在首次计算产物清单前更改报告，旧代码接受非零退出、布尔退出、失败分类和无效程序摘要四种报告，修复后均在登记前拒绝。Linux 源码 23 项通过，1 项真实许可条件跳过。两个修复的隔离 wheel 联合 50 项通过，1 项真实许可条件跳过。证据见本机 `root-delivery-20261109-71`。 [MuFerro 工作流](simulation-muferro.md)

## 2026-11-09 UTC · 项目工作目录边界和 F10 实线

`2bf8d83bb8f746c300772461349aab6550fc409a` 检查仿真工作流已有目录组件的真实元数据。Linux 用实际符号链接模拟 Windows 联接点的目录类型和重解析标志。旧 MuFerro 导入返回成功，在项目外创建 `input.toml` 和 `material.toml`。修复后导入拒绝，项目修订、表和外部哨兵均保持。Windows 夹具直接创建真实目录联接点，待目标矩阵执行。测试覆盖稳定目录和已有组件的检查。Linux 源码联合 108 项通过，2 项真实许可条件跳过。隔离 wheel 的 MuFerro 工作流 13 项通过，1 项真实许可条件跳过。Python 3.11、3.12、3.14 的 Linux 导入定向各 6 项通过。 [项目工作流](simulation-muferro.md)

`fb4dbd39f2f9268b5887e8eb545f4b178a9f9db3` 集成 Claude33 `4e1767477a298fe8c6dd042a59fc13af2b85fc4a`。真实 UDP 编辑获准后在 SQLite 写入口等待，撤权线程到达授权事务。放行编辑后撤权才能完成，观察时原回执已持久化。旧授权的目录、表页、回执查询、精确重放和新写均返回 `forbidden`，回执、修订和历史保持。Linux 源码 171 项和隔离 wheel 定向一项通过，零跳过。隔离副本提前释放授权时在预期的撤权等待断言失败。证据见本机 `root-delivery-20261109-70`。 [CP-0 矩阵](design/cloud-project-service.md)

远端 `bb4cea9d` 的 Runtime 13 项、Windows CPU 和 Linux 三项通过，macOS 失败证据见下节。Windows 原生作业仍运行，本地待整轮终态后推送。 [Windows 原生](https://github.com/sijintech/stk/actions/runs/42576437438/job/129041311528) [Desktop](https://github.com/sijintech/stk/actions/runs/42576437438)

## 2026-11-09 UTC · MuPRO 大步数空结果与 F5c 实线

`1cd5bbbd2a019426f73f25d0dbc884151c238925` 逐行校验实际能量和进度，按需生成缺帧诊断，并在收集展开名单前检查现有文件数上限。999,999 步、间隔 1 的合法合成布局有 14,999,986 个预期 DAT 帧。空结果目录在旧源码和 224 MiB 地址空间上限下，直接核验、连接器和收集探针触发 `MemoryError`，CLI 退出 1 且无结构化输出。修复后直接核验与 CLI 返回四项检查、`invalid_result` 和前五个缺帧，连接器返回前五十个，合成成功任务收集按 10,000 文件上限拒绝。四次独立进程峰值 RSS 约 26 至 29 MiB，只覆盖空结果探针。

Linux 源码联合 119 项通过，3 项按 Windows junction 和真实许可条件跳过。隔离 wheel 启动器 62 项通过，2 项按平台和许可条件跳过。Python 3.11、3.12、3.14 的 Linux 定向各 26 项通过。证据在本机 `root-delivery-20261109-69`。 [MuPRO 运行校验](runtime-mupro.md)

`aa3d1890d6fbe9c6b2fc65b9574dc17579ccf7fc` 集成 Claude32 `19654d4b9402f9422accad545c81542400321c58`。真实 UDP peer 首次读取实际热日志后的项目时恢复原数据库字节，修订、历史、原操作回执和授权水位均符合现行行为。同一连接后续读取成功。Linux 源码 170 项和隔离 wheel 定向一项通过，零跳过。隔离反例绕过恢复后在首次项目读取处失败。 [CP-0 矩阵](design/cloud-project-service.md)

远端 `bb4cea9d` 的 macOS CPU 1516/1516，Metal 254/254，原生主组 4/6，定位前隐藏 0/2。两视频显式暂停首次采样均见可见时派发的代次 1 已 ACK，随后各在隐藏期失败。定位前对照分别收到 24 和 26 次 Playing，均已 ACK、未核验，最终分别由迟到回复和 watchdog 关闭。Linux 三项、Windows CPU 和 Runtime 13 项已过。Windows 原生仍在运行。本地 Cocoa 静默对照等待整轮终态后推送。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42576437438/job/129025111974) [原生证据](https://github.com/sijintech/stk/actions/runs/42576437438/artifacts/13657571015) [Desktop](https://github.com/sijintech/stk/actions/runs/42576437438)

## 2026-11-09 UTC · 原生 JSON 解码、F11b 与 Synthrix 观察

`d9bfc7e1d502ea5e4b8a4ba3d6c21dac93bf4bc1` 修正 MuPRO 完成文件及进度 JSONL 触发解码器嵌套上限时的错误出口。Linux Python 3.11 真实解码反例在旧代码仅有文本错误并退出 1，修复后返回结构化 `invalid_result`、退出 3，QoI 为空且对应校验失败。版本无关的注入回归也在旧代码两项失败、修复后通过。Linux 源码联合 109 项通过，3 项为 Windows junction 和两个真实许可用例。隔离 wheel 启动器 61 项通过，2 项按平台或许可条件跳过。Linux Python 3.11、3.12、3.14 客户端各 39 项通过，各跳过 Windows junction 一项。junction 夹具使用真实目录连接，验证拒绝先于案例内容读取与连接，待 Windows 矩阵执行。

`b27375f2e45cc88c4e6d51cbfeee0a340ca6ac68` 集成 Claude31 `bcfff105d433d6736414a46257ffc081979bd150`。同一操作 UUID 在本机桥和真实 UDP peer 各写一次，固定各自 scope、CAS 和原回执，两次重放不增加写入。Linux 源码 169 项和隔离 wheel 定向一项通过，零跳过。隔离反例把 peer scope 改为 `local` 后，在首次 peer 查询失败。 [CP-0 矩阵](design/cloud-project-service.md)

使用 STK `d9bfc7e1` 源码和 Synthrix `caec2b9` 类型，在 Linux 环回隔离 Runtime 两次复现 worker 丢失但程序仍存活。TypeScript 观察器对原任务只发一次 GET，保留 `unknown` 与原始原因，核对 41 个状态和工作区文件的字节摘要前后一致，排除 SQLite 共享内存文件。之后显式取消同一任务，读到取消终态，程序回收且未发布输出。合成任务成功、失败、取消、真实 404 和服务不可达也通过。证据在本机 `root-delivery-20261109-68/synthrix-live-unknown`。覆盖隔离适配器和一台本地 Runtime，产品路由、UI 和授权接线仍待验证。

远端 `bb4cea9d` 的 Runtime 13 个任务已过，Desktop 的三个 Linux 任务已过，Windows 和 macOS 核对时仍运行。本地提交待上一轮 Desktop 整轮终态后推送。 [Runtime](https://github.com/sijintech/stk/actions/runs/42576437407) [Desktop](https://github.com/sijintech/stk/actions/runs/42576437438)

## 2026-11-09 UTC · MuPRO 严格证据、完整清单和 F13

`207902bb883be2b06a0b286c6e9d1d52b990a003` 要求 MuPRO 原生终态记录中的步数和值使用精确类型，JSON 重复键或非标准数值归为 `invalid_result`，数值类型与预期不符归为 `incomplete_result`。旧源码接受六种反例并产生 QoI。修复后终态与实时监视联合 65 项通过，真实许可用例条件跳过一项。

`b7272392cffb888f553cbcc207fef7e845cc25c4` 在读取根 `input.toml` 内容和连接前核对完整上传清单。拒绝链接、Windows junction、特殊条目、`key/`、`.lic` 以及非法相对路径。旧源码在六个负例失败，正常的 `Polar.in`、嵌套 HDF5 和 `--remote-dir .` 通过。覆盖稳定的本地输入树，Windows junction 待 Windows 复验。两个 MuPRO 修复的最终 Linux 源码 95 项通过、2 项按真实许可条件跳过。隔离 wheel 启动器 59 项通过、1 项同类跳过。Python 3.11、3.12、3.14 的 Linux 客户端各 42 项通过。

`e03a955ab8e89e57a0bfe7d76072e9aa97c3f394` 集成 Claude30 `957dc0a298b6396a56b53a58581b0441dda85a43` 的真实 8 MiB 响应预算回归。两条线路均拒绝包含 8,500,000 字节文本的表页，保持项目修订及历史，同一连接继续读取拆分后的两页。Linux 源码 187 项和隔离 wheel 两项均通过，零跳过。独立副本将上限改为 16 MiB，新例在预期拒绝处失败。原始证据见本机 `root-delivery-20261109-67`。 [CP-0 矩阵](design/cloud-project-service.md)

远端 `bb4cea9d` 的 Runtime 13 个任务全部通过，含 Windows Python 3.11 和 3.12。Docs 和 Secret scan 通过，Desktop 整轮仍在运行。以上本地代码尚待推送和目标平台 CI。 [Runtime](https://github.com/sijintech/stk/actions/runs/42576437407) [Desktop](https://github.com/sijintech/stk/actions/runs/42576437438)

## 2026-11-09 UTC · Cocoa 静默对照与 F15 实线

`207beb8a503932a023873ed1b61cb9c68d09642d` 增加两个 macOS 定位前隐藏对照。相同固定素材经真实 Play 和切页，切页后等原生时限加 250 ms，期间只泵窗口事件、观察资源会话。若关闭则记录同会话原生关闭原因，隐藏阶段 DOM 样本为零。若仍存活，只取一次隐藏 DOM 样本，验证采样派发前同一导航恰有一次新暂停、已 ACK 且已核验。隐藏截图保留 OS 像素检查，随后保留重显、草稿及资源撤销。两项原采样对照继续以原名称运行。

Linux 编译公共报告测试目标，探针与 AX CPU 共 8 项通过、零跳过。临时 CMake 生成四项 macOS 注册，核对了各自的参数、成功标志、精确 CI 名称和分开的 JUnit 与产物目录。静默组实际 Cocoa 行为待 macOS 运行。证据见本机 `root-delivery-20261109-66`。

`718f3cdfe39d635a7adbd0873d0d1bea33e699fb` 集成 Claude 的 `ba7a63a4`。严格桥与已认证 UDP WebRTC 读取同一合成格式 14 项目的非空表，两项回执操作均获 `unsupported`，复读与 SQLite schema 未变。Linux 源码 186 项全过，隔离 `bb4cea9d` wheel 定向通过。 [CP-0 矩阵](design/cloud-project-service.md)

远端 `bb4cea9d` 的 Docs 与 Secret scan 已通过，Desktop 和 Runtime 在本次核对时仍运行。 [Desktop](https://github.com/sijintech/stk/actions/runs/42576437438) [Runtime](https://github.com/sijintech/stk/actions/runs/42576437407)

## 2026-11-09 UTC · a8872719 Desktop 终态

精确 `a88727199d25a5651789d79e2e6650547145e5ee` 的 Desktop 于 06:57:24Z 完成，结论为失败。Linux 三项、Windows CPU 和 Windows 原生成功。Windows 原生通过固定发布地址直连获取 Mesa 26.2.4，大小和 SHA-256 校验通过。WebView2 和生产 ReportsEditor 六项全部执行并通过，精确必跑检查通过。macOS CPU 1516/1516、Metal 254/254，原生 4/6，定位前隐藏对照 0/2。 [Desktop](https://github.com/sijintech/stk/actions/runs/42570072786) [Windows 原生证据](https://github.com/sijintech/stk/actions/runs/42570072786/artifacts/13655576418) [macOS 原生证据](https://github.com/sijintech/stk/actions/runs/42570072786/artifacts/13654776484)

Cocoa 目标环境为 macOS 15.8.2、Xcode 16.4。两项定位前隐藏对照中，单视频 DOM 保持暂停约 0.77 秒，原生分别收到 25 次 Playing 回复后关闭。下一轮用单次派发的新头复验，将原生回执与 DOM 采样的影响分开取证。Runtime 的 Windows 3.11 同头重跑成功。 [Runtime 第 2 次](https://github.com/sijintech/stk/actions/runs/42570072715/attempts/2)

## 2026-11-09 UTC · 报告暂停合并与 Cocoa 回复取证

`ab9707df660e6a1fcac3c351e79ff2a6c29d19dd` 集成 Claude `1736233d` 的宿主改动。Linux Xvfb 从 1280×800 默认工作台的 `a3` 测试标签开始。七个 Pause 点击分属不同生命周期场景，每个由一次按下和松开组成。首个点击在隐藏前只派发一次，重显后可再次派发，关窗撤销资源会话。视图为测试替身。关窗红例在旧夹具中调用谓词两次，修复后一次。联合 114 项全过，14 项宿主无窗口测试和 Xvfb 精确门均通过。缺失、跳过、未运行和失败的必跑门反例均被拒绝。证据见本机 `root-delivery-20261109-64`。

`a8872719` 的 macOS CPU 1516/1516、Metal 254/254，原生 4/6，定位前隐藏对照 0/2。独立视频首次显式暂停为代次 2、派发时已隐藏，DOM 时点从约 0.107 秒退到 0.042 秒。两项隐藏对照在失去挂载前保持判据通过，关闭分别记录为 `pause_watchdog` 与 `pause_reply_after_deadline`。两者均收到暂停 ACK，状态核验未通过，关闭前 25 次查询收到 25 次 Playing 回复。HTML 原组另在第三个保持采样超过时间差上限，当时没有关闭记录。 [macOS 原生证据](https://github.com/sijintech/stk/actions/runs/42570072786/artifacts/13654776484)

Windows 3.11 Runtime 同头重跑于 06:39:14Z 成功，使用旧热日志夹具。Windows Desktop 原生仍在运行，Mesa 准备已完成。 [Runtime 重跑](https://github.com/sijintech/stk/actions/runs/42570072715/attempts/2) [Windows 原生](https://github.com/sijintech/stk/actions/runs/42570072786/job/129016929205)

## 2026-11-09 UTC · MuPRO 布局绑定与 D1 同修订竞争

`9a357f75abe3842c7a75e59f267ce1e088de5845` 的旧码反例让合成求解器把预检三步改为一步，旧启动器退出 0。修复后退出 3，`case_layout` 失败，保留三步预检及空 QoI，独立离线核验仍读当前一步目录。源码联合 126 项通过、2 项仅真实许可资产跳过。隔离 wheel 启动器 47 项通过、1 项仅真实资产跳过。 [节点入口](runtime-mupro.md)

`7017fb938804ccb208a42ef1fe353c3ef6b491be` 在同一 Linux SQLite 项目用严格桥与已认证 UDP WebRTC 各发一项修订 0 编辑，恰一提交和回执，败方及后续陈旧请求无回执。root 源码联跑 185 项、零跳过，隔离 wheel 定向通过。移除 CAS 与改错 peer 冲突映射的两个反例在预期断言处失败。证据见本机 `root-delivery-20261109-63`。 [CP-0 矩阵](design/cloud-project-service.md)

`a8872719` Desktop 的 Windows CPU 及 Linux 三项通过，Windows 原生已通过 Mesa 准备并进入 WebView2 和报告测试，macOS 已进入 WKWebView 和报告测试。整轮仍运行。 [Windows 原生](https://github.com/sijintech/stk/actions/runs/42570072786/job/129016929205) [macOS](https://github.com/sijintech/stk/actions/runs/42570072786/job/129005168960)

## 2026-11-09 UTC · 文献热日志夹具阶段取证

`03bb7fbc8f310e53ff6dbba3b294205aec440688` 在外部数据库热日志夹具中使用 `python -I -S`，显式关闭父连接，保留事务写入、缓存落盘和故意退出。文献与项目编辑联合 170 项通过、零跳过，使用固定 PDFium 5.14.0 和独立无 PDFium 环境。Python 3.11、3.12、3.14 的物理热日志与真实子进程子集各 6 项通过。

外部副本的禁用落盘、替换磁盘标记、事务阶段异常和超时共 4 项均按预期失败。超时保留了写入前的最后阶段。暂存扫描零发现。Windows 同头重跑仍在执行旧夹具，新夹具尚待目标平台验证。证据见本机 `root-delivery-20261109-62`。 [Windows 重跑](https://github.com/sijintech/stk/actions/runs/42570072715/job/129012759353)

## 2026-11-09 UTC · MuPRO 样例预检、重试与 Windows Runtime

`bac536c92ca0a1a998c579bc7195e3529bede05b` 的两个反例先在旧源码失败，分别覆盖 SDK 缺少材料和目标材料路径无法写入。修复后均可在补齐或修正路径后原地重试。联合 133 项通过、2 项仅真实许可资产跳过。隔离安装 wheel 的启动器 46 项通过，1 项仅真实许可资产跳过。源文件与 wheel 安装字节一致。暂存扫描零发现。证据见本机 `root-delivery-20261109-61`。 [计算节点入口](runtime-mupro.md)

`a8872719` Runtime 第一次 12/13 个任务成功。Windows Python 3.11 的外国热日志用例在子进程 join 20 秒后被测试终止，未执行到数据库原字节断言。同头只重跑该 Windows job。Desktop 整轮仍在运行。 [失败 job](https://github.com/sijintech/stk/actions/runs/42570072715/job/129005168400) [Runtime 重跑](https://github.com/sijintech/stk/actions/runs/42570072715/attempts/2) [Desktop](https://github.com/sijintech/stk/actions/runs/42570072786)

## 2026-11-09 UTC · a8872719 密钥扫描重跑与下载验证

`a88727199d25a5651789d79e2e6650547145e5ee` 的 Secret scan 首次在安装步骤收到 HTTP 504，扫描被跳过。第二次同头执行于 06:07:29Z 完成，安装和实际扫描均通过。Docs 已部署，Desktop 和 Runtime 在本次核对时仍运行。 [Secret scan 第 2 次](https://github.com/sijintech/stk/actions/runs/42570072800/attempts/2) [Docs](https://github.com/sijintech/stk/actions/runs/42570072760) [Desktop](https://github.com/sijintech/stk/actions/runs/42570072786) [Runtime](https://github.com/sijintech/stk/actions/runs/42570072715)

`f8d2f79ed59f19de5b0a1dd94a8cd138b358a284` 为固定 gitleaks 8.30.1 Linux x64 加入 GitHub Release API 资产 `378332058` 作为备用。按工作流原脚本本机执行四个场景。公开路径和模拟公开路径 504 后的真实 API 下载均通过同一 SHA-256，解包得到字节相同的 8.30.1。错误内容在校验阶段拒绝，两条下载路径均不可用时退出，两个反例均未解包。暂存扫描零发现。 [上游发行](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)

## 2026-11-09 UTC · 39780e6d Desktop 终态、原生取证和 F23

[Desktop 42564398378](https://github.com/sijintech/stk/actions/runs/42564398378) 对精确 `39780e6d68951047c73c4ff13945b23342b13718` 于 05:46:10Z 终态失败。

| 任务 | 结果 |
|---|---|
| Linux Ubuntu 24.04 发行包 `128987632348` | 通过 |
| Ubuntu 24.04 全新环境包冒烟 `128989634008` | 通过 |
| Linux Ubuntu 26.04 `128987632533` | 通过 |
| Windows CPU `128987632515` | 1,460/1,460 通过 |
| macOS `128987632697` | CPU 1,516/1,516、Metal 254/254；原生原组 4/6、定位前对照 0/2 |
| Windows 原生 `129002156977` | Mesa 下载失败，原生六项未执行 |

Mac HTML 定位前对照的同会话在 0.753939 秒的 27 次采样中保持 0.181362 秒，取得一次隐藏画面匹配。播放样本返回后 1.168254 秒，`pause_watchdog` 关闭导航代次 1、媒体代次 4，记录 ACK 已收到、`verified=false`。原组独立视频与 HTML 分别在首次隐藏暂停读到 0.234 秒和 0.102 秒，低于各自下限，失败点的同会话关闭记录为空。独立视频定位前对照在首次显式暂停从 0.117290 到 0.046819 秒后失败。四份 JSON 经范围读取并核 CRC32，摘要见 `root-delivery-20261109-57/mac/mac-13652111396-evidence.json`。 [Mac 日志](https://github.com/sijintech/stk/actions/runs/42564398378/job/128987632697) [Mac 产物 13652111396](https://github.com/sijintech/stk/actions/runs/42564398378/artifacts/13652111396)

`59183cd0` 记录暂停派发可见性、查询和匹配回复次数、Playing 回复次数、首发及末回时点。现有观测能确认 watchdog，仍需新字段区分未回调与持续报告 Playing。Linux 构建并通过 34 项资源、解析、像素与原生门禁检查，Cocoa 路径待下轮执行。

Windows 同头候选包已下载，第 5 步固定 Mesa 26.2.4 URL 三次 HTTP 504 后退出，产物仅含环境快照。`46bab2cf` 加入 GitHub Release API 资产 `609112860` 作为备用。在本机观察到原路径 504，备用路径下载完整 70,257,286 字节并通过原固定 SHA-256。两条路径共用解包前的大小与摘要门禁。 [Windows 失败步骤](https://github.com/sijintech/stk/actions/runs/42564398378/job/129002156977#step:5:1) [Windows 产物 13652791298](https://github.com/sijintech/stk/actions/runs/42564398378/artifacts/13652791298)

文献 `adc3c591` 用真实本地 CTest JUnit 验证三平台 CPU 门禁。四个文献交互用例在两种固定布局共 8 项通过，分别移除和标为跳过的 16 个反例都被拒。这组核对文献点击、草稿和来源变化的 CPU 回归。

F23 `530df743` 与 Claude27 最终 `304b036e` 的测试文件字节相同。六文件联跑 299 项通过、零跳过，包含显式安装前缀的两项桌面桥验收。root 定向使用 `49837655` wheel 通过，两个隔离副本分别因内容漂移、撤权失效在预期处失败。证据见 `root-delivery-20261109-59/closure.json`。 [CP-0 矩阵](design/cloud-project-service.md)

同头 Runtime `42564398339`、Docs `42564398406`、Secret scan `42564398623` 均通过。

## 2026-11-09 UTC · F14 真实配额线路、F5b/F5c/F23 反例

F14 使用 `49837655` wheel、Python 3.14.4 / SQLite 3.46.1 与已安装 Linux 原生 helper。每个合成项目由严格 NDJSON 桥与已认证 UDP WebRTC 各提交一份原回执，其余成功编辑通过正常 store API 填入。六个相关 Python 模块的安装字节与 wheel 及当前主线一致。

| 检查点 | 已存回执 | 请求与回执合计字节 |
|---|---:|---:|
| 条数满额 | 10,000 | 9,514,154 |
| 新写入将越过字节上限 | 141 | 66,852,607 |
| 字节满额 | 142 | 67,108,864 |

三个检查点两端均返回 `invalid_params`，各失败 ID 为 `not_found`，SQLite 文件及逻辑状态摘要一致。各 scope 的原回执按原 CAS 0 或 1 精确重放，跨 scope 查询返回 `not_found`。这是单 Linux 主机、同库的实额线路证据。配额监控、其他部署与平台单独验收。证据见 `root-delivery-20261109-58/f14-wire/closure.json`。

Claude26 在未改动 `db9a7ed8` 的源码导出上通过 4 项。四份单行为改动在对应断言处触发 5 个预期失败。F5c 补充对照证明普通库仍可读，真实热日志下目录入口被拒、字节保留。root 核验 SHA256、JUnit 和失败点。证据见 `root-delivery-20261109-58/claude26-review.json`。 [CP-0 矩阵](design/cloud-project-service.md)

远端 `39780e6d` 的 Desktop 尚在运行。macOS 的新取证仍待原生媒体组。 [Desktop 42564398378](https://github.com/sijintech/stk/actions/runs/42564398378)

## 2026-11-09 UTC · F12 真实续页与 F14 实额

- **F12**。提交 `b326baef` 使用显式安装的 Linux helper 建立已认证 UDP WebRTC，与本机桥读取同一 SQLite 项目。结构页与记录页各读两页，末页 `next_offset=null`。本地删除一条记录推进修订后，旧的两个续页在两端均返回 `conflict`，peer 随后读取新修订成功。
- **测试结果**。源码 `test_peer_endpoint.py`、`test_peer_projects.py`、`test_project_edit_operations.py`、`test_desktop_bridge_peer.py` 初跑 181 通过、2 跳过。补给 `STK_TEST_PEER_INSTALLATION` 后，这两个相同测试 ID 通过，共 183 个唯一通过项。另一次传输联跑 174 通过、2 跳过，跳过项需要独立的对抗测试程序。隔离 `49837655` wheel 的 F12 定向 1 项通过，桥及 peer 模块来源已核实。两个隔离副本分别把结构页、记录页的原修订替换为当前修订，各在对应的旧续页检查处失败。
- **F14**。隔离 `49837655` wheel，Python 3.14.4 / SQLite 3.46.1。两个合成项目经本机 `ProjectStore.edit_operations` 正常提交，分别达到 10,000 份回执、9,514,466 字节和 140 份回执、67,108,864 字节。在字节项目 66,851,033 字节时，248,340 字节的合法单次请求及其 248,605 字节回执超出总额，事务回滚。两个满额项目拒绝新请求，失败 ID 无回执，项目修订、逻辑状态和已存回执一致。重开后首末原回执均可读及按原 CAS 精确重放。实际配额的桥与 peer 线路另验。
- **CI**。精确 `39780e6d` 的远端 Desktop 仍在运行。macOS 原组与对照会在第 20 步尝试上传四个媒体用例及原生探针数据。 [Desktop 42564398378](https://github.com/sijintech/stk/actions/runs/42564398378) [macOS 任务](https://github.com/sijintech/stk/actions/runs/42564398378/job/128987632697)

测试 JUnit、独立配额清单及摘要保存在 `root-delivery-20261109-57/closure.json`。 [CP-0 证据矩阵](design/cloud-project-service.md)

## 2026-11-09 UTC · CP-0 wheel 复验与 49837655 Desktop 终态

| Python | SQLite | 通过 | 跳过 |
|---|---|---:|---:|
| 3.11.16 | 3.53.1 | 116 | 0 |
| 3.12.14 | 3.53.1 | 116 | 0 |
| 3.14.4 | 3.46.1 | 116 | 0 |

Linux wheel 来自 `49837655`，SHA256 为 `03c2bb32a931d2a5567d26a85511659f0f84510c345312ee8f63b91a589a70dd`。`74ee8b4e` 导出的两份项目编辑测试及一个 F14 原生 helper 用例，在三个解释器有完全相同的测试 ID。主进程与实际热日志子进程均从隔离安装目录导入。真实 WebRTC 限 F14 缩小写后字节预算的同库用例，其他结果按 store、桥和 peer 适配器范围记录。本机合成项目仍待跨主机及目标平台复验。证据目录 `root-delivery-20261109-56` 的 `installed-cp0-matrix.json` 绑定三个 JUnit 和解释器元数据的 SHA256。 [CP-0 矩阵](design/cloud-project-service.md)

[Desktop 42558025291](https://github.com/sijintech/stk/actions/runs/42558025291) 对精确 `4983765575ec708ceb52e195afe87ea3f6211396` 于 04:46:03Z 终态失败。六个任务均已结束。

| 任务 | 结果 |
|---|---|
| Linux Ubuntu 24.04 发行包 `128968016251` | 通过 |
| Ubuntu 24.04 全新环境解包冒烟 `128969883943` | 通过 |
| Linux Ubuntu 26.04 `128968016349` | 通过，2118 CTest |
| Windows CPU `128968016066` | 通过，1460 CTest |
| Windows 原生 `128978712754` | 通过，六项 OpenGL 文档验收 6/6，CTest 1313.55 秒 |
| macOS 原生 `128968016291` | 失败，原组 4/6，定位前对照 0/2 |

Windows 六项为文档预览、Markdown、HTML、PDF、Video 和 HTML video。证据包于 04:45:59Z 上传。macOS 的两类媒体失败及原始证据见下一节。 [Windows 原生任务](https://github.com/sijintech/stk/actions/runs/42558025291/job/128978712754#step:7:1) [Windows 证据 13650009117](https://github.com/sijintech/stk/actions/runs/42558025291/artifacts/13650009117)

同头 Runtime `42558025404` 13 项任务通过，Docs `42558025283` 和 Secret scan `42558025253` 通过。

## 2026-11-09 UTC · 49837655 macOS 失败阶段及原生暂停取证

[macOS 128968016291](https://github.com/sijintech/stk/actions/runs/42558025291/job/128968016291) 于 04:27:26Z 终态失败。第 18 步原组 4/6，第 19 步定位前对照 0/2。定向读取四份原 JSON，共 266,735 字节，逐条校验 ZIP CRC32 与实际 SHA256。[产物 13649638003](https://github.com/sijintech/stk/actions/runs/42558025291/artifacts/13649638003)

| 用例 | 真实停止点 |
|---|---|
| 独立视频原组 | 初始暂停、读数 0、导航代次 1。首次显式暂停时从 0.114528 s 变为 0.046563 s，仅 0.05 s 下限失败，尚未定位或隐藏 |
| 独立视频对照 | 同一阶段从 0.115514 s 变为 0.047413 s，尚未定位或隐藏 |
| HTML 视频原组 | 隐藏保持第 3 个样本由 0.252089 s 变为 0.102000 s |
| HTML 视频对照 | 未定位。隐藏保持 0.764653 s，28 个样本固定 0.181419 s。一次隐藏截图匹配后，会话探针报未附着，未尝试重显 |

独立视频的显式暂停记录当时缺少同次原生 ACK 和核验阶段。HTML 对照的暂停探针在相同导航代次记录 ACK 为真、原生核验为假，截图采样的 DOM 暂停观察为真。现有证据不足以确定会话关闭来源。本地 `b386929b` 在显式暂停取证中带上播放及首次暂停探针的派发和回调快照，并将同会话隐藏关闭对象纳入有界失败日志。Linux 上报告测试程序构建和 25 项 CPU 回归通过，零跳过。Cocoa 待目标 runner。

同头 Windows CPU 1,460 项通过，Windows 原生任务 `128978712754` 仍在运行。Desktop 整轮仍未终态。

## 2026-11-09 UTC · F14 同库的原生 peer 线路与 wheel

本地 `1e7bebf2` 使用显式已安装的 Linux WebRTC helper。两个 PeerEndpoint 实际双向认证并以同机 UDP 交换协议消息。本地严格 Bridge 与远端 peer 入口指向同一合成项目，各先提交一个原操作。将项目回执字节额度缩为当前总量加 1，随后两个入口的新写入都得到 `invalid_params`，项目快照与历史一致。失败 ID 的查询均为 `not_found`，各自原 ID 的读取和精确重放返回同一回执。

四个相关测试文件共 182 项通过，零跳过。以远端 `49837655` 同头 wheel 安装的 Bridge、PeerEndpoint 与编辑回执模块复跑新增用例，1 项通过。隔离导出把 peer 的 `ProjectError` 错映射为 `conflict`，新增用例在远端错误码断言失败。证据在 `root-delivery-20261109-55/closure.json`。范围为单 Linux 主机和缩小后的预算，未写满生产额度，未覆盖跨站或云端部署。

截至 04:26Z，`49837655` 的 [Desktop 42558025291](https://github.com/sijintech/stk/actions/runs/42558025291) 整轮仍在运行。Ubuntu 26.04 GL/Vulkan CTest 2,118 项通过，Ubuntu 24.04 包和新环境安装冒烟成功，Windows CPU 1,460 项通过，macOS 和 Windows 原生在跑。同头 Runtime 13 项通过。

## 2026-11-09 UTC · 已安装中文文献实窗及共享回执配额

桌面二进制取自 `4983765575ec708ceb52e195afe87ea3f6211396` 的 Ubuntu 24.04 CI 包，按 GitHub ZIP 摘要和压缩包自身 SHA256 校验后解到独立前缀。实际宿主为 Ubuntu 26.04.1，Xvfb X11、Mesa llvmpipe OpenGL。Python 桥由同头离线构建的 wheel 安装，观察器校验收到的显式 `state` 和 `cache`，并确认从独立安装目录导入。进程从无源码的工作目录启动，字体和语言文件来自发布包前缀。[CI 包 13647928060](https://github.com/sijintech/stk/actions/runs/42558025291/artifacts/13647928060)

| 固定起点及动作 | 点击 | 滚轮 | 结果 |
|---|---:|---:|---|
| 中文默认工作台 1000×1200、scale 1，合成网格在 Viewer，打开文献 | 1 | 0 | 阅读页打开，明确刷新前未观察到文献桥回复 |
| 从同一起点显示完整引用页 | 8 | 0 | 本地 E5 检索、解析引用、PDFium 5.14.0 PNG 及 30 个逐字高亮，查询由键盘输入并确认 |
| 从已显示引用页撤权并回阅读页 | 5 | 0 | 原版本回执 `active=false`，页图消失 |

安装态回传 PNG 和前次源码构建结果逐字节相同，SHA256 为 `248de01b24a56f013e75b7afd711595bd9100bfdb6c317fab1e2a6f7183f8417`。窗口页图四个采样点及首字高亮吻合，Viewer 区域三帧像素一致。额外一次点击清理合成查询稿，随后退出码 0。证据见 `root-delivery-20261109-54/closure.json`。使用预建合成库和离线模型，目标 Mac/Windows 文献页待验。

F14 `5c4723f4` 对 Bridge 与已认证 peer 适配器共享的回执数量及字节预算复验。缩小测试预算，分别覆盖数量满额、字节已满和新编辑使字节越界后三类拒绝。原两条回执、修订、表和历史保留，原 ID 仍可读取和精确重放。显式实装 helper 的五文件 249 项全过，零跳过。在隔离导出中，按 scope 计数、移除写后字节守卫、把配额检查移到原回执前分别被新增测试捕获。F14 用例仍是同库适配器，未写满生产额度，也未跑云端。

同头 Runtime `42558025404` 于 04:09:13Z 全部 13 项成功。Desktop `42558025291` 的 24.04 包、全新环境安装冒烟和 26.04 GL/Vulkan 均成功，Mac/Windows 仍在运行。

## 2026-11-09 UTC · CP-0 双入口测试与已安装 helper 复验

Claude `d84fe104` 的测试文件原样集成至本地 `b8e42c66`。同修订双入口各用自己的原 UUID 和由入口绑定的 scope，竞争后只提交一次，失败方及两入口首次陈旧写入均无回执。固定文件的 30 次重复通过，Bridge 赢 3 次、peer 赢 27 次。另核两入口分页和序列化预算拒绝、格式 14 仍可读且新回执接口须显式升级。

root 对五个相关测试文件使用显式已安装的 Linux peer helper，246 项通过，零跳过。三项新增覆盖在隔离源码导出中各有绿例，移除 CAS、关闭共享字节上限、改错旧格式的 Bridge 错误映射，各使对应测试失败。移除 CAS 的反例实际返回 `invalid_params`，测试原预期为 `conflict`。竞争和旧格式测试使用同进程 Bridge 与已认证 peer 适配器。实装 helper 的网络用例另计，未运行真实跨部署竞争或云项目。证据见 `root-delivery-20261109-53/closure.json`。

远端 `49837655` 的 24.04 包及新环境安装冒烟已成功，整轮 Desktop `42558025291` 尚未终态。

## 2026-11-09 UTC · Cocoa 隐藏会话关闭诊断候选

本地 `133778cd` 在报告媒体隐藏前观察同一个活的 Cocoa 子视图。实际首次关闭前取原会话的媒体及导航代次、最近暂停 ACK 和核验状态。保持或隐藏截图失败时写 `hidden_media_native_close`，其中的关闭原因区分 `pause_watchdog`、`pause_reply_after_deadline` 和 `other`。观察未附着与附着但无关闭快照分别记录。相对时间从播放返回起算。原 1 秒截止、0.75 秒保持与两次连续真实截图条件继续执行。

本地 Linux 以启用探针的构建生成报告测试程序、媒体探针、报告宿主和辅助功能驱动测试。针对原暂停状态机、DOM 媒体探针、报告宿主和驱动的 CTest 共 25 项通过，零跳过。传输生命周期 pytest 32 项通过，包括主线 `2de183f9` 的旧 worker 清理并重试用例。证据在 `root-delivery-20261109-53/`。Linux 使用 Unsupported 文档后端，Cocoa 新记录须同代码头 macOS runner 核对。

截至 03:52Z，远端 `49837655` 的 Desktop `42558025291` 正在运行。24.04 包成功并启动安装冒烟，26.04 GPU、Mac 和 Windows CPU 在跑。同头 Runtime `42558025404` 已有 8 项成功、5 项运行中。Docs 与 Secret scan 成功。

## 2026-11-09 UTC · fbe4b0cc 整轮 Desktop 终态

[Desktop 42551958437](https://github.com/sijintech/stk/actions/runs/42551958437) 在代码头 `fbe4b0cc64d283fe5298bb76f3f14e16fa244906` 于 03:41:28Z 结束，结论失败。下表是同一轮的全部六个任务。

| 任务 | 结果 | 证据 |
|---|---|---|
| Ubuntu 24.04 可重定位包 | 失败 | Ubuntu 镜像连接超时，APT 退出 100，未编译 |
| Ubuntu 26.04 GPU | 失败 | Ubuntu 镜像连接超时，APT 退出 100，未编译 |
| Ubuntu 24.04 包安装冒烟 | 跳过 | 上游包任务失败 |
| macOS arm64 | 失败 | 原生原组 4/6，定位前隐藏对照 0/2 |
| Windows MSVC CPU | 通过 | 任务 `128949277443`，03:20:49Z |
| Windows 原生文档 | 通过 | 任务 `128961373052`，03:41:27Z。第 7 步六项强制门通过，第 8 步上传成功 |

Windows 原生第 7 步覆盖软件 OpenGL/WARP 上的 20 轮原型和生产报告的 Markdown、HTML、PDF、独立视频、HTML 视频，并逐项要求成功标记。目标 Windows 文献页仍待验。[Windows 原生证据 13647913277](https://github.com/sijintech/stk/actions/runs/42551958437/artifacts/13647913277)

[Runtime 42551958449](https://github.com/sijintech/stk/actions/runs/42551958449) 同头 13 项成功。Docs `42551958518`、Secret scan `42551958603` 成功。上述 CI 结果属于 `fbe4b0cc`。后续 GUI 修复 `2bf4bd50` 的 Linux 本地 37 项及双语文献实窗见下文。

## 2026-11-09 UTC · 中文文献实窗及 macOS 隐藏对照

中文验收使用本地 `2bf4bd50` 二进制、Xvfb X11、Mesa llvmpipe OpenGL，`zh_CN` 1000×1200、scale 1。默认工作台的 Viewer 已装载合成网格。独立真实桥目录预置一份自制 PDF 和固定 E5、PDFium 5.14.0 索引，预置不计入界面点击。

| 固定起点与动作 | 点击 | 滚轮 | 结果 |
|---|---:|---:|---|
| 默认工作台打开文献 | 1 | 0 | 打开阅读页，点击刷新前未观察到文献桥回复 |
| 从默认工作台到已显示引用页 | 8 | 0 | 手动刷新、选库、搜索、选结果、解析、显示，查询由键盘输入并以 Return 确认 |
| 已显示引用页，切到库、选库和版本、撤销并回阅读页 | 5 | 0 | 原版本回执 `active=false`，页图消失 |

E5 语义排名 1，字面分支无排名。实测 `search`、`citations.resolve`、`pages.render`、`versions.revoke` 各一次，均绑定原库及对应引用或版本。完整页在窗口内可见。四个颜色采样与原图一致，首字高亮落在对应四边形内，共 30 个四边形。PNG 为 1599×1244、54,118 字节，SHA256 `248de01b24a56f013e75b7afd711595bd9100bfdb6c317fab1e2a6f7183f8417`，与独立英文实窗结果逐字节相同。网格 Viewer 区域在三张截图中像素一致。清除合成查询稿另计 1 次点击，键盘退出码 0。证据见 `root-delivery-20261109-51/closure.json`，含 `displayed.png` 和 `literature-window-proof.json`。本机证据使用合成 PDF 及离线编码，Mac/Windows 的文献页面待验。

前代码头 `fbe4b0cc` 的 [Desktop 42551958437](https://github.com/sijintech/stk/actions/runs/42551958437) 截至 03:36Z 仍在运行。Ubuntu 24.04 包和 26.04 GPU 在依赖安装阶段因镜像连接超时失败，24.04 安装冒烟跳过。Windows CPU 于 03:20:49Z 成功，Windows 原生文档任务 `128961373052` 仍在第 7 步。此前同头 Runtime 13 项、Secret scan、Docs 均成功。

macOS arm64 任务 `128949277319` 于 03:19:33Z 失败。第 18 步原组 4/6。独立视频隐藏保持的时间从 0.359726 s 退到 0.234 s，HTML 视频在播放读数 0.203298 s 后首次暂停读到 0.102 s，低于允许下限。两项倒退值均与各自此前辅助功能定位的读数相同。第 19 步定位前对照 0/2。独立视频在 0.769151 s 内 31 次采样固定在 0.177161 s，HTML 视频在 0.755982 s 内 25 次采样固定在 0.181094 s。两项分别取得一次匹配的真实隐藏画面，DOM 显示暂停，随后第二次画面采样时会话已脱离。首个暂停探针的 Cocoa 回调记录为已 ACK、原生状态尚未通过核验。四例均未进入重新显示，完整循环均为 0。现有记录尚不能确定会话关闭来源。四份原始 JSON 来自[原生 CI 产物 13647415863](https://github.com/sijintech/stk/actions/runs/42551958437/artifacts/13647415863)，按范围读取并逐条核对 ZIP CRC32 和 SHA256。

## 2026-11-09 UTC · Linux 实窗检索、引用页与撤权

本地 `2bf4bd50` 二进制，Xvfb/X11、Mesa llvmpipe OpenGL，英文 1600×1100、scale 1。默认工作台的 Viewer 已装载合成网格。桥状态目录预置一份自制 PDF、PDFium 5.14.0 的文本索引和固定 E5 的 3 个索引窗口。预置动作与鼠标验收分开。

| 起点与动作 | 点击 | 滚轮 | 结果 |
|---|---:|---:|---|
| 默认工作台打开文献 | 1 | 0 | 阅读页打开 |
| 从同一起点到已显示引用页 | 8 | 0 | 刷新、勾选库、输入查询、搜索、选中首项、解析、显示；文字另由键盘输入和确认 |
| 已显示引用页，切到库、选库和版本、撤销并回阅读页 | 5 | 0 | 原版本回执 `active=false`，页图消失，引用动作禁用 |

首项由 E5 语义分支返回，字面分支无排名。搜索、解析和显示的引用及库身份相同。桥返回的 1599×1244 PNG 共 54,118 字节并核验 SHA256。窗口内红、绿、蓝、白四个采样与 PNG 一致，首字高亮采样落在对应四边形内，回执共 30 个字符四边形。撤权后上述像素消失。Viewer 区域从初始到显示及撤权后均逐像素一致。另一次清理合成查询稿的点击单独计数，键盘退出码为 0。截图、准确点击与验证程序见 `root-delivery-20261109-50/closure.json`。首轮外部观察适配器的参数解析错误已修正并排除，产品验证以复跑为准。

同头 `fbe4b0cc` 的 [Runtime 42551958449](https://github.com/sijintech/stk/actions/runs/42551958449) 于 02:57:25Z 成功，13 项全过。[Desktop 42551958437](https://github.com/sijintech/stk/actions/runs/42551958437) 尚在运行。

## 2026-11-09 UTC · Linux 文献入口实窗与 GUI 桥目录

`2bf4bd50` 将 GUI 的 `--state-dir` 传给桥，使用所给根下的 `state` 和 `cache`。首轮未隔离的试验因 GUI 沿用了默认目录而撤出验收。旧二进制用守卫解释器复测时两个参数均缺失，守卫拒绝启动真实桥，测试外壳超时后清理自己的进程。新二进制每次都精确传入两个参数，真实桥 Ready，四次桌面正常退出。

| 固定起点 | 点击 | 滚轮 | 结果 |
|---|---:|---:|---|
| en 1600×1100，scale 1，默认布局，公开合成网格在 Viewer | 1 | 0 | 顶栏打开文献阅读，Viewer 区域像素逐点相等，Python 标签仍在原区域 |
| zh_CN 1000×1200，同布局和公开合成网格 | 1 | 0 | 同上 |
| 两种原尺寸，改用含体渲染的公开合成包 | 各 1 | 各 0 | 同样进入文献。Viewer 中心 36,260 和 42,680 像素有差异，分别最大通道差 30 和 26 |

Xvfb X11 / Mesa llvmpipe OpenGL，两个语言各自全新的桥状态和缓存。四例均无 SQLite 文件生成。本次实窗范围为默认入口，稿件内容、文献检索和引用页 GPU 交付另验。X11/Wayland 窗口冒烟、OpenGL/Vulkan 无头端到端、33 项文献 CPU 检查共 37 项通过，零跳过。截图、布局、目录参数和 JUnit 见 `root-delivery-20261109-49/closure.json`。

远端 `fbe4b0cc` 的 [Desktop 42551958437](https://github.com/sijintech/stk/actions/runs/42551958437) 成文时仍运行。[Ubuntu 24.04 打包](https://github.com/sijintech/stk/actions/runs/42551958437/job/128949277197#step:4:1)和 [Ubuntu 26.04 GL/Vulkan](https://github.com/sijintech/stk/actions/runs/42551958437/job/128949277278#step:4:1)均在安装依赖时连接镜像超时，APT 退出 100。包 smoke 跳过。Mac 和 Windows 尚在构建，同头 Runtime 9 项成功、4 项运行中。

## 2026-11-09 UTC · Mac 定位前隐藏对照的提交验证

- `0f341a07` 增加 `reports_pre_seek_hide_video_metal` 和 `reports_pre_seek_hide_html-video_metal`。两项从同一默认 a3 Reports/Python 和 Viewer 布局启动，使用冻结 MP4、新资源会话和真实原生 Play。首次隐藏时沿用原有 0.05 秒下限、0.10 秒保持变化上限、0.75 秒保持与重显检查。每项要求一轮、六张图、两次准备及两处撤销。实际点击、时序和终态由目标 Mac 记录。
- 原 Mac 六项验收及 Windows 任务定义保留。新增对照在独立 Mac CI 步骤执行，保存原 `LastTest.log`，对照有独立 JUnit 和证据目录。Linux `stk-reports-native-window` 重建，文档资源、暂停探针、宿主等 42 项通过，零跳过。关闭探针宏语法通过，Linux 的对照测试注册数为 0。目标 Mac 尚待运行。
- 前 [Desktop 42542944337](https://github.com/sijintech/stk/actions/runs/42542944337) 的整轮终态已记录。`757383af` 的路径过滤未触发 Desktop，[Runtime 42548838606](https://github.com/sijintech/stk/actions/runs/42548838606) 于 02:21:06Z 成功，同头文档发布与 Secret scan 也成功。未引入产品界面改动。

## 2026-11-09 UTC · 56 的整轮终态和 CP-0 证据

[Desktop 42542944337](https://github.com/sijintech/stk/actions/runs/42542944337) 绑定 `56b432d0`，attempt 1 于 02:00:59Z 完成，整轮 failure。任务时间为 UTC。

| 任务 | 结果 | 结束 |
|---|---|---|
| Linux 包 128921691191 | success | 01:04:28 |
| Linux 包 smoke 128923650851 | success | 01:05:51 |
| macOS 128921691132 | failure | 01:28:19 |
| Linux GL/Vulkan 128921691262 | success | 01:31:09 |
| Windows CPU 128921690979 | success | 01:39:54 |
| Windows 原生 128933290782 | success | 02:00:58 |

Windows 原生 20 轮步骤于 02:00:45Z 通过。Mac CPU 1516/1516、Metal 254/254、原生 4/6。独立视频首次暂停样本在播放采样后 60.581ms 由 0.336489 秒回到 0.234000 秒，低于播放样本减 0.05 秒的下限。HTML 视频在保持阶段第 4 样本由暂停基线 0.246369 秒回到 0.102000 秒，超过 0.10 秒界限。两者均回到各自最后一次 AX 定位值，采样时已暂停、未结束、未 seek，导航代次为 1。新暂停代次的 ACK 已到，采样时 `verified=false`。首次定位前也观察到约 84 毫秒的回退，下一步做定位前隐藏对照。 [Mac 日志](https://github.com/sijintech/stk/actions/runs/42542944337/job/128921691132#step:18:1) · [Mac 产物](https://github.com/sijintech/stk/actions/runs/42542944337/artifacts/13643187676)

[Runtime 42542944387](https://github.com/sijintech/stk/actions/runs/42542944387) 于 01:16:23Z 完成，13 个任务逐项成功。同头 Docs 和 Secret 也成功。终态已登记，可以推送下一批提交。

- CP-0 `a4a07a41` 以真实 SQLite 热回滚日志验证 owner 绑定读取原字节拒绝和 peer 目录物理恢复，源码和隔离安装核心各 110 项通过。两种反向改动仅在一次性源码副本执行，分别触发 2 和 1 项预期失败。
- CP-0 `bd49fd40` 验证本机桥与已授权 peer 保留同一合成文件索引值，撤销项目授权后 peer 拒绝目录及表读取。源码和隔离安装核心各 111 项通过，零跳过。宽套件 243 项通过，2 项跳过需原生 helper 安装前缀。
- 双仓试验对隔离 Linux Runtime 真实任务执行五次状态 GET 及一次缺失 GET，读前后数据库、WAL、工作区字节一致。另用关闭监听的真实服务验证不可达，用合成 DTO 验证后端 `unknown` 等分支。严格类型检查绑定 Synthrix `a15ab6b`。本次仅为服务器观察映射，真实产品路由和权限另行验证。证据见 `root-delivery-20261109-46/closure.json`。

## 2026-11-09 UTC · CP-0 分页及回执回归

- 本地 `994a3b1a` 使用真实桌面桥 NDJSON 与已授权 `PeerProjects`，核对 peer 方法响应编码。两页目录、三页记录的结果一致，两种陈旧续页均被拒。相同 UUID 在两个 scope 各有一个原回执，分别精确重放。源码四套 143 项，隔离 Python 3.12 wheel 核心两套 107 项，零跳过。用例与证据见 `root-delivery-20261109-45/closure.json`。
- 本次范围是现有项目操作，原生 helper、远端云服务与 R2/R3 待各自验收。两条物理热日志路径目前有外部探针证据，独立回归正在编写。
- 远端 `56b432d0` 的 [Desktop 42542944337](https://github.com/sijintech/stk/actions/runs/42542944337) 与 [Runtime 42542944387](https://github.com/sijintech/stk/actions/runs/42542944387) 尚在运行。Docs 与 Secret 已成功。

## 2026-11-09 UTC：315 的 Desktop 整轮终态

[Desktop 42536615591](https://github.com/sijintech/stk/actions/runs/42536615591) 绑定 `315620f9`，attempt 1 于 00:55:35Z 完成，整轮 failure。六项结果如下，时间为 UTC。

| 任务 | 结果 | 结束 |
|---|---|---|
| Linux 包 128902206042 | success | 11-08 23:53:49 |
| Linux GL/Vulkan 128902206269 | success | 00:07:08 |
| Windows CPU 128902206328 | success | 00:32:12 |
| macOS 128902206365 | failure | 00:27:09 |
| Linux 包 smoke 128904496231 | success | 11-08 23:55:11 |
| Windows 原生 128914767592 | success | 00:55:34 |

[Windows 原生](https://github.com/sijintech/stk/actions/runs/42536615591/job/128914767592) 的 20 轮验收步骤于 00:55:20Z 成功。macOS 两项媒体失败见下节，同头 Runtime 13 项成功。下一代码头含测试诊断 `749076d9`，Cocoa 诊断的编译和执行由新一轮 CI 验证。

## 2026-11-09 UTC：315 的隐藏保持失败和 D1 项目服务基线

- [Desktop 42536615591](https://github.com/sijintech/stk/actions/runs/42536615591)，代码头 `315620f9`。00:39Z 整轮仍运行。Linux 包、包 smoke、Linux GL/Vulkan、Windows CPU 完成且成功，Windows 原生 128914767592 正运行。[Runtime 42536615619](https://github.com/sijintech/stk/actions/runs/42536615619) 00:03:47Z 完成，13 项逐项成功。同头 Docs 和 Secret 成功。
- [macOS 128902206365](https://github.com/sijintech/stk/actions/runs/42536615591/job/128902206365#step:18:1) 00:27:09Z 失败。CPU 1516/1516、Metal 254/254、原生 4/6。Video 和 HTML 视频的首轮隐藏保持分别由 0.386759 回退至 0.234000 秒、由 0.249097 回退至 0.102000 秒。采样仍暂停、未结束、未 seek，导航代次一致，唯一失败条件是时间差绝对值不超过 0.10 秒。这个代码头未包含 `749076d9` 的原生暂停阶段诊断，尚不能判断回退原因。
- D1 受控项目探针在源码和同 Python 源码的隔离 wheel `03c2bb32…` 中通过。比较真实本地桥 NDJSON 路由和有当前授权的 peer 项目适配器，三个目录页和三个记录页相同，陈旧续页被拒。原回执按 scope 分隔，相同 UUID 在另一个 scope 和当前修订下可产生新回执。现有 peer codec 保留授权的文件索引路径值。真实热日志下，所有者绑定读取拒绝且保留文件，peer 目录读取做物理恢复后仍为修订 0，未提交操作无回执。两个现有套件在源码 106/106（3.22 秒）、从无源码夹具目录运行的隔离安装 106/106（2.78 秒），零 skip。无新增 UI 交付，云端、跨机和 R2/R3 验收仍待后续。证据见 `root-delivery-20261109-43/closure.json`。

## 2026-11-09 UTC：Mac 原失败产物关联及测试用暂停阶段快照

- 4d6426fb / Desktop42531177137 / Mac128885487773 / artifact13639166231。经受支持的产物引用有界读取中央目录及两个失败 result.json（96,385/99,201字节），核 ZIP 成员 CRC、尺寸和文件 SHA；未下载或独立核验整个 ZIP 摘要，未读截图或其他夹具文件。八文件冻结清单复核通过，关联报告 SHA238d696efb469726a69c625b6c7a75bb7710866a54d8abdb0873c4c44c2a7de7。
- 两项 cycle1/nav1 的隐藏失败与公开日志对象精确相等，播放样本取自同一 fresh play；最后一次 AX 辅助定位已交付、helper 已回收，其后0.25s hold 稳定在0.234及0.102s。隐藏失败的时间精确回到这两个值。首次 AX 前，显式暂停 hold 已分别0.1240178333→0.039724584及0.126095125→0.042174916s，约84ms回退且仍满足0.10s。前序 AX 不是出现回退的必要条件；隐藏失稳根因仍未隔离，无完整隐藏/重显无自动续播验收。
- [WebKit 上游媒体时间实现](https://chromium.googlesource.com/external/github.com/WebKit/webkit/%2B/c2c1343a292141aa20c260463e8cbb95042c544a/Source/WebKit/WebProcess/GPU/media/MediaPlayerPrivateRemote.cpp)包含远端时间估算及回退更新，这为进一步区分时钟校正提供一个解释。该源码不是 CI 所用 WebKit 二进制的版本或实际分支执行证明。
- 新本地749076d9：TEST_PROBES 下记录隐藏前、首次 paused 与最新观察的原生暂停代次、导航、ACK 和原 verified，分别绑定派发与回调。旧回调不污染新请求；无可用事实用null；verified仅表示现有WK非Playing核验在原期限内通过，不代表DOM时间已稳定或此刻仍暂停。有效view/session/nav而DOM失败时仍保原生回调事实。17字段脚本/解析、原ACK与时序、1秒期限、20轮及全部断言不变。
- Linux最终测试驱动构建和关闭宏语法通过。42个资源/探针/宿主CPU测试全部通过、零skip、0.46s，XML SHA5da5aa95664dda22d8a7a45279fa7407cb255d257ebbbd89a68cfff54aa15e82。独立源码复核确认关闭探针宏后三文件保留字节一致；旧失败对象叠加最大新字段约3460/3391字节，仍低于8192。此批未编译Cocoa、未执行新原生点击/像素，不宣称Mac修复。证据`native-media-pause-phase-20261108-40/validation.json`。
- 315620f9 的 Desktop42536615591 整轮仍运行（Linux包与冒烟两项成功）；Runtime42536615619 12项成功、Windows3.11未终态，Docs42536615604部署及Secret42536615677成功。749本地未推，等前整个Desktop终态并记录后才推。实际后续状态见本批closure；已有文档WIP保留。

## 2026-11-08 UTC：上传第四版完整源码/最小安装验收与前4d整轮终态

源码集成397a464d来自实际Claude分支claude/hub-upload-cli-18、基线a0f77fa3的冻结六路径第四版；patch SHA d83af30da18b22c37116a446ba1674e4b7c4350f33e0b1ae14f1248566f9dfdf。CLI a2010de0…、worker b8891128…与两项测试保持作者冻结字节；root只补设计文档实际验收状态。共同transfers.py为54d47290…、含6c481e59；不把作者531旧依赖当修后版本。

- 作者九模块225/225零skip；root2b已提交归档加六SHA覆盖九模块234/234零skip、95.56s，XML SHA8dcc7ba6ef2a32d4a8d090921a672b37a51f32aa17f991add473fbf51aa81065。差九是root共同后端回归，非重复计数。新侧记发布反例在第三版4失败/2控制通过，第四版通过；独立终审12场景及原读取11组通过、清临时且不调用replace，报告SHA61015342fb0d4c6ffc00ce279c21ea32553f827dfc46033130a58ca8fe394331。
- 离线wheel 48,312,551字节、SHA03c2bb32a931d2a5567d26a85511659f0f84510c345312ee8f63b91a589a70dd；新venv禁系统包，仅server/control/test依赖，无科学/GUI/模型包。无产品目录的独立测试床，从无关cwd以python-I运行，234收集/232通过/2明确排除/零skip，91.63s，XML SHA7ee9c16cb5caa71d6a9aa58641afffac334091fc28948e47d2cb16cbe4eb986f。排除test_deployment.py的test_shipped_parameter_sweep和test_doctor_and_saved_connection_check_running_stopped_and_bad_token，因明确依赖NumPy/Matplotlib，两项已在完整源码矩阵通过。三产品SHA、父进程实际模块均来自venv/site-packages且前后相等，未见自有活后代；不代所有子进程全module图。KEY空、MODEL unset，无收费请求。此CLI交付无新增UI点击流程。
- 前4d6426fb整个Desktop42531177137已23:27:29Z completed/failure，六job全部终态。WinCPU128885487420、LinuxGPU128885487865、Linuxpackage128885487587、smoke128887194734、Win原生128893437017均success；Mac128885487773 failure。MacCPU1516/1516/614.61s、Metal254/254/381.00s、原生4/6/530.16s；Win原生6/6、零失败/skip、1038.93s。Runtime42531177232十三job全success，Docs42531177195实际部署、Secret42531177130成功。终态已满足下一批push等待门，旧CI不包含6c/397。
- Mac两个新快照均完整且probe回调/解析成功、导航一致、paused=true。video隐藏hold的before0.36973825→failed0.234，abs差0.13573825超过原0.10；html-video的playing_before_hide0.2174544167→paused0.102，低于原playing-0.05。两项显式暂停checks全真。这里只确定失败谓词和一次回退观察，不证明持续播放、迟到seek或生产暂停根因；保原容差、期限、原生输入、像素和20轮门。

证据：本机验证根d1-hub-upload-cli-20261108-21/root/author-candidate4-20261108-38/、candidate4-installed-20261108-38/及root-delivery-20261108-39/ci-proposal-agent/。目标OS worker、真实不支持硬链接文件系统、外部站点和科学有效性仍待验；原八项/D1–D5及MuPRO待决不缩减。实际最终提交、push和新CI以本批closure与真实Git核对；旧WIP保留。

## 2026-11-08 UTC：4d Runtime 终态与上传 candidate3 独立源码验收边界

[Runtime42531177232](https://github.com/sijintech/stk/actions/runs/42531177232)已22:57:35Z completed/success；实际查询13job均completed/success，含Linux3.11/3.12/3.14、Windows3.11/3.12、文献三版本、peer-macos、独立联邦、网页及协议组。Docs42531177195实际部署与Secret42531177130成功。整个[Desktop42531177137](https://github.com/sijintech/stk/actions/runs/42531177137)仍运行，Mac/Windows CPU测试、Linux构建，两个Linux包job成功；Windows原生尚未创建。结果绑定4d，不能验证本地6c修复或未集成CLI；等待门仍关闭。

candidate3六文件来自作者冻结manifest（module95ce76b2…），root复制前/复制后/原树再核SHA一致。作者九模块219/219零skip/97.41s；root用13337fde已提交归档加同六文件覆盖、共同backend54d47290…，九模块228/228零skip/95.20s（case合计93.578s），差9恰共同后端新回归。root初次226通过/2失败均因独立副本漏带examples/runtime/run_demo.py，补同提交样例后完整重跑，未改产品代码，初次XML/log与closure保留。当前source-validation.json绑定两份完整XML及所有来源摘要。

独立worker76例、54自有stdlib child全回收，旧b3中断/指数溢出红例转绿，未调用无超时wait；只读R1/R2/R3另11组通过。它们不代真实worker/网络/安装态；真实loopback路径来自上述九模块。root共同依赖54d跳坏日志，而peer仍531旧依赖，不能冒称peer已修。

最终纯文件发布反例仍确认：真实namespace租约持有时，注入EOPNOTSUPP并在exists观察False后让不参与租约的写者放入合法旧侧记，fallback的os.replace覆盖旧字节且采用新身份；正常link已有文件保护及不支持link/无并发者两控制保留。此为无覆盖发布不变量缺口，不证明两个合规worker可并发。candidate3未接受/集成；离线wheel构建成功但未安装，实际Claude按第四版卡在同六路径修复，旧冻结证据保留。证据 `d1-hub-upload-cli-20261108-21/root/author-candidate3-20261108-36/`、`root/sidecar-publication-candidate3-upload_readonly_review/` 及37/closure.json。KEY空/MODEL未设，未发收费请求；无新增UI点击验收，旧WIP保留。


## 2026-11-08 UTC：坏传输日志的启动隔离与真实共同后端回归

本地源码6c481e59、远端4d6426fb；本修复未push，等待前整个[Desktop42531177137](https://github.com/sijintech/stk/actions/runs/42531177137)终态。该新头[Runtime42531177232](https://github.com/sijintech/stk/actions/runs/42531177232)仍运行，Docs42531177195已实际部署成功、Secret42531177130成功，不能把它们当整个Desktop通过。

TransferManager恢复扫描在集合membership前验证state为字符串；坏数组/对象日志原地保留，不再使其他传输启动失败。不改重放、自动恢复授权或GC规则。新增九例在旧源5311155a…上为8个unhashable TypeError失败、1控制通过、零skip；当前source54d47290…/testab4db1f8…下五模块67/67、零skip、35.54s（XML case合计34.62s），覆盖传输生命周期、shutdown锁持有、真实本机Runtime与Hub审阅/续传。测试KEY空/MODEL未设，无收费请求或许可求解。

新增反例涵盖queued/running、旧/新mtime、数组/对象坏状态，核坏字节/mtime/锁保持；合法原request/key/endpoint转interrupted且构造零launch/backend/emit，显式resume只选原合法ID。控制例核unknown/recent保留、只清旧FINAL。独立终审核两源码SHA及旧红XML，无实质发现；其20个外部固定副本探针不替代root五模块实跑。旧红/新绿XML、完整SHA和扫描证据见 `transfer-startup-20261108-36/validation.json`，最终提交及CI见同目录closure。该后端变化无新UI点击验收，不将上一批真实文献CPU界面当本修复的目标OS证据。

实际Claude第三版的固定早期b3另有52个worker场景、30自有stdlib child全部回收，确认中断前kill与1e999非有限JSON两类残留；root已交修订卡，作者在原会话继续，尚未接受最终候选/安装。原四状态文档与正式资产WIP保留。


## 2026-11-08 UTC：前 ae6 完整 Desktop 终态与下一批推送门

[Desktop42523800365](https://github.com/sijintech/stk/actions/runs/42523800365)已于22:21:50Z completed/failure，六个job均终态，满足前整个Desktop结束后再push的等待门。最终job如下，全部绑定ae6e3d7c：

| job | 终态 | UTC结束 |
|---|---|---|
| Linux package128862806342 | success | 21:20:08Z |
| Linux package smoke128865547978 | success | 21:21:11Z |
| Linux GL/Vulkan128862806684 | failure | 21:40:32Z |
| macOS Cocoa/Metal128862806575 | failure | 21:42:37Z |
| Windows CPU128862806559 | failure | 21:58:17Z |
| Windows native128875254641 | success | 22:21:50Z |

Windows原生六项全通过、零skip、1329.01s，required六项精确匹配；冻结终态报告 `root-delivery-20261108-35/ci-review/review.json`（SHA256 `48e1c4169ab37e6d9672fe04cc879a03e19c6067daac50977810f2dbe99b8f65`）。七项artifact仅取得元数据，未下载内容或独立核验整包摘要。

旧头Linux2109/2118、MacCPU1510/1516、WindowsCPU1454/1460，失败为此前记录的八/六布局金样及一个材料测试；Mac原生4/6，两视频分别显式和隐藏暂停条件失败。新源码9b338172（四项提交99a25c36/9779efea/fe2cdb4b/9b338172）不在本轮CI中，不能继承Windows原生成功或宣称Mac已修。Runtime42523800339的13job、Docs实际部署42523800384和Secret42523800368成功。

推送前重新核对21源码和五XML的完整SHA256，全部等于 `root-delivery-20261108-34/root-verification.json`；默认文献33、真实资产UI2、材料22、布局8及AX五组所在1CTest均零skip通过。真实资产两布局各37点击/0滚轮、页图采用/纹理释放和Viewer/隐藏稿保持证据沿用34节；本次无新UI变化或重复模型调用。新头CI、实际push身份及未提交WIP见 `root-delivery-20261108-35/closure.json`，34/closure.json已补齐。Claude第三版仍独立复核，未计入本批产品验收。


## 2026-11-08 UTC：真实文献 CPU UI 全链、当前桌面 CI 与修复

本地源码HEAD9b338172（99a25c36、9779efea、fe2cdb4b、9b338172），远端仍ae6e3d7c。前整个Desktop42523800365尚在运行，Windows原生128875254641仍live，push门未满足；不以任一job终态代整体。最终提交和推送结果见 `root-delivery-20261108-34/closure.json` 与实际Git。

### 固定资产与真实 UI

本机使用预供PDFium5.14.0与固定E5资产，manifest SHA256 `301ef8fcc5b1cf59cb7f55cd7bbc07e5f852f3deca2f89f4f1c548d20b1c2d71`；无下载、许可求解或收费模型。真实服务预检1/1零skip/34.45s；默认文献33/33、零skip；独立真实资产目标2/2、零skip，case耗时合计62.362s。21项相关源码实际运行前后SHA相等，独立源码审阅无阻断发现，未重跑模型作为第二份独立执行证据。

| 固定起点 | 鼠标点击 | 滚轮 | 结果 |
|---|---:|---:|---|
| 默认工作台，en/1600×1100/scale1；Viewer与隐藏未保存Python稿预置 | 37 | 0 | 导入→PDFium索引→E5复核/选择/dense→检索→引用→渲染两次→撤权→历史观察通过 |
| 默认工作台，zh_CN/1000×1200/scale1；同样状态 | 37 | 0 | 同一真实全链通过，Viewer/相机/隐藏稿保持 |

文字输入及End/Enter属于正常键盘事件，不计入鼠标点击。夹具设置2项、隐藏重显/桥换代注入2项单列。打开文献首1点击、0文献RPC且不建库；业务动作均用正常UI事件，结果逐项绑定实际原请求/UUID/SHA。Jobs纹理hooks接实际核验PNG解码RGBA及逐字quads，两次render顺序create/free/create/free；重render先释放旧纹理，revoke输入同步清页，历史import.review结果不能复活批准。hooks按值捕获共享Capture，早失败或晚析构不依赖派生fixture寿命。CPU UI证据不证明OS/GPU呈现、文献段落科研正确性或检索质量。

复现入口：用 `-DSTK_LITERATURE_REAL_ASSETS_APP_ACCEPTANCE=ON` 配置同一桌面构建，构建 `stk-literature-real-assets-app-tests`；显式设置可信 `STK_LITERATURE_TEST_PYTHON`、`STK_LITERATURE_E5_PYTHON`、`STK_LITERATURE_E5_ASSETS`、上述 `STK_LITERATURE_E5_MANIFEST_SHA256`，以KEY空/MODEL未设运行 `ctest --test-dir <build> -R '^RealAssets/LiteratureRealAssets'`。该目标默认OFF，真实CTest仅发现2项；资产缺失的受控单项反例exit1/失败1/零skip。默认可移植33项不增加skip。最初构建因四行同line的GTest宏label重名失败，拆行后目标构建成功；不把该初稿编译当通过。

### 本机桌面修复与受控反例

八份布局金样逐对象核对，仅新增顶栏文献按钮并位移其后Swap/余量标签，其余区域/控件/值逐字一致；正常测试8/8零skip。生成模式的8项skip是更新金样步骤，未计作测试通过。材料整组22/22零skip/10.868s，保1点击及原30s：count(activate)发生在派发前，durable done亦可早于publication lease释放；现在等UI采用真实ACK，准入后仅只读Busy可在原剩余截止内重观测，其他错误或形状不符即失败。

独立外部完整C++目标同参数注入0.65s：activate保存持锁、version-two done提交后仍持锁两个窗口，旧目标都Busy+null304红，新目标各1/1零skip/2.085s和2.053s。31项共享链接输入SHA前后相等，四次自有进程全部退出；6组提取helper受控clock/ASan负例通过。初次注入Store.update遗漏epoch的无效试跑排除，不独断原CI具体初始/最终读取落点。真实目标数据训练器受控，不证明PyTorch训练准确性。

原生媒体最终源64dbbe36…主目标构建、宏关语法通过，CPU AX五组所在1个CTest通过4.24s，最终源码提取95断言通过。新诊断有界记录显式pause真实快照、隐藏pause的上下界/hold细分条件与实际单调时刻；缺回调/无快照为null，晚回调不改已复制失败记录，诊断不盖原错。不增加probe/input/截图，原期限、DOM/唯一slider、像素和20轮门保持；这些不是生产暂停修复或目标OS验收。

### 已推 ae6 的 CI（不覆盖本批新字节）

[Desktop42523800365](https://github.com/sijintech/stk/actions/runs/42523800365)尚未整体结束。Linux2118中2109通过、9失败/498.06s（六默认金样、两Jobs金样、一个Materials激活测试）；MacCPU1516中1510通过、六默认金样失败/519.24s，Mac原生4/6/480.51s，两视频分别在显式暂停与隐藏暂停条件失败；WindowsCPU1460中1454通过、六默认金样失败/939.69s，Windows原生继续。三平台失败日志均绑定ae6；仍缺Mac失败瞬间的细分观测，本批补诊断待后续新头，不能沿用旧AX/Tab根因。

[Runtime42523800339](https://github.com/sijintech/stk/actions/runs/42523800339)13job全部success；Docs42523800384实际部署与Secret42523800368成功。两个Linux包job成功，不代原生OS验收。PR53/54仍为c9f13994/2dd3e4ee旧头、无关未合。实际Claude第三版仍未最终冻结/安装态验收或集成；其开发62绿与旧candidate2的14红/WIP恢复属另一工作树观察，不作本批产品验收。

本批证据 `root-delivery-20261108-34/root-verification.json`、`desktop-ci-42523800365/materials-activation-review/target-red-green-2/review-final.json` 和各XML/冻结源码审阅。暂存扫描用原.gitleaks.toml的 `gitleaks git --pre-commit --staged`，每个源码提交零发现；四状态文档/索引收尾和最终SHA另记closure，既有WIP保留。


## 2026-11-08 UTC：文献原生UI本机回归（源码已本地提交）

当前源码已本地提交5c0b85d3、远端仍c281620d，构建root-build-06/application-build-01成功；17文件完整暂存80031字节，SHA a5be09859f932deaf1c2c98af6287b2ddf193c10965dc4924ee415d01de4ffef，gitleaks退出0且报告[]；源码已commit，四状态文档/认知收尾和push尚未完成。证据根`native-literature-ui-20261108-29/`，本次收尾记录`root-delivery-20261108-31/`。

| 实际范围 | 结果及限制 |
| --- | --- |
| 完整文献CPU | literature-full-03.xml/log：33/33、零skip、33.783s，含8项双布局UI、既有控制器及PNG/几何；不代真实E5全链UI或OS。 |
| UI核心 | image-and-ui-tests-02.xml/log：131/131、零skip、1.317s，含四项高亮变换/裁剪/异常/旧帧回归；KEY为空、MODEL未设置。 |
| App导航与注册 | app-navigation-01.xml/log：19/19、零skip、0.759s，新编辑器追加第21项，既有ID顺序保留。 |
| 默认布局文献入口 | en1600×1100、zh_CN1000×1200，scale1；从默认工作台点击顶栏文献一次、零滚轮，落到文献编辑器，0文献RPC/不建库，Viewer payload/相机/精确隐藏Python稿保持。不声称零其他系统RPC。 |
| 明确复核导入 | 同默认布局13次点击/零滚轮，包含两次复核、一次明确提交；公开自编PDF字节夹具，只验导入不验解析。旧A批准闭包不能批准B。文字键入/Enter未纳入点击计数，隐藏/重连/失效另用注入验证。 |
| 初轮失败保留 | ui-tests-01为8/9；中文测试点击把光标放到词中，错误期待后缀在末尾。增加明确End后全33项通过；不是修改产品来迁就此断言。 |

原生页面复核三项缺陷已修：执行守卫核真实桥进程，批准冻结原review身份，本地文字提交不借桥/库代次授权。最大化其他区域后、下一帧前的旧动作另被直接guard拒绝。隐藏/搬移清授权与页图、保局部文字；新render先释放旧GPU纹理。workspace按发布合同仅保存有限查询/范围稿；真实本地模型、检索引用页图全链UI、GPU实际呈现及目标OS验收尚未完成。

c281整个Runtime42517256886已success、13job全过；Desktop42517256870已20:59:15Z completed/failure，六job均终态，推送等待门满足。Linux全2105零skip、546.14s；WindowsCPU1447零skip、854.61s；MacCPU1503零skip、561.84s和Metal254零skip、430.04s。Mac原生4/6、507.81s，两视频0/20，均已通过公共AX定位/回收及菜单切换前置，首次hidden pause断言失败；两个必要JSON只取261944B/344656372B并核逐项CRC/SHA，未核整archive摘要、未下载PNG，缺失败瞬间状态和单调耗时，不能断言是哪一子条件或生产根因。Windows原生128854043391已success；整轮失败仅Mac，不能把旧头CI当作5c0b85d3文献UI的跨平台验收。Windows原生6/6、零skip、1319.76s；冻结整轮总报告root-delivery-20261108-29/ci/review-final.json，SHA619b1955de07cb60e4e3446880d93215bc0a3c533d2f4867e5828737f6357217。

## 2026-11-08 UTC：原生报告候选与612e整轮终态

- 247cca3b：真实CPU AppFixture固定1024×656、en/scale1，原默认a3宽401，经实际divider拖到286，独立tabs缺失而区域菜单可见启用。普通菜单事件到Python再返回Reports：2鼠标点击、5按键、0滚轮；Viewer/payload/相机及精确未保存Python文字保持。原native-window目标构建0，暂存2977B/SHA8a276058…扫描0。没有新产品UI变更；此CPU探针未覆盖CI完整高度/真实媒体/OS呈现，不能充作原生20轮通过。
- 70a301f4：完整WA唯一候选后再核实际Slider同时处于WA及inner祖先链；独立v3解码拒Above无Slider证明、伪父链/深度、额外Slider/无关行/侧支，保Below旧合法回执。外部-Werror五组4.257s；恢复旧selector谓词红例失败，另三份故意破坏候选为红，不能当三项历史根因。root构建stk-reports-native-ax-tests为0，CTest reports_native_ax_cpu 1/1（内含五组）、零skip、4.25s/总4.32s。冻结差分17066B/SHAa45a6afb…与四源SHA一致，实际暂存gitleaks0。accepted原文一致、1632B/v3/33行和原2s/8s/Provider4、真实WK/会话/导航/布局、DOM/OS像素及20轮门未改；新Apple helper未编译或运行。

612e实际video主回执1632B、463.815ms、helper已回收/exit1：Window0→Group6→Group7→ScrollArea8→WA9→Group10→Group11，4个匹配Group为单链、唯一WA；拒绝发生在查询Slider前，故实际Slider是否属于inner仍未知。HTML-video已成功三次AX seek（557.351/589.065/499.196ms），随后宽286时缺独立tab控件。公开artifact只按range提取并核各条ZIP CRC/SHA，未核整个343MB archive摘要或下载PNG；不作整包完整性或新增截图声明。两失败均0/20，cleanup成功。

前整个[Desktop42509570653](https://github.com/sijintech/stk/actions/runs/42509570653)已于2026-11-08T19:32:03Z completed/failure；run与jobs API核同612e/attempt1、total_count=6且六job均终态。WindowsCPU/job128819473697：1447个唯一测试全Passed、零skip/未跑、914.14s；原同名NativeAgentRuns本轮0.66s过，但612e无13035ccc，不能归功于新夹具。Windows原生/job128831493773：6/6、零skip、1324.32s（spike105.17、MD130.03、HTML126.74、PDF173.81、video381.35、html-video407.18s）。三Linuxjob成功。Mac/job128819473919 CPU1503/1503/559.67s、Metal254/254/337.61s、原生4/6/492.30s，仅原生step18失败：两视频仍未通过。由整轮终态满足push等待门，不用Windows局部绿代新头平台验收。

同612e的[Runtime42509570684](https://github.com/sijintech/stk/actions/runs/42509570684)已18:39:50Z整轮failure，12job成功；3.14旧running观察失败6019通过/153skip/4未选/814.57s，本地fdbefeac未包含于该头。Docs42509570687完整部署及Secret42509570637成功。299e756b/13035ccc/fdbefeac与本批两候选均待新头CI。

证据：desktop-ci-42509570653下review/、root-tab-menu/、ax-selector-proposal/candidate-1/及final-status/review.json（SHA c34409d4…）；root独立复核及扫描在root-delivery-20261108-28/。Claude18六路径仍为独立树WIP，未计安装态/功能验收。提案2aea已在远端但P1/P2未启用；最终提交/push/新头CI和索引收尾见本批closure，原WIP保留。


## 2026-11-08 UTC：三项测试修正的受控验证与612e CI

| 本地提交 | 实际检查 | 覆盖限制 |
|---|---|---|
| 299e756b | 监督失败发布延迟0.3s：旧KeyError/2.60s，新通过/2.84s；模块17通过、零skip、10.23s | 公开假模型服务，无生成请求；原15s不变，目标3.14新头CI未跑 |
| 13035ccc | 实际夹具加受控Windows CRT seek/write语义：长104B/短91B同offset旧红，锁后两完整行；C++20/-Werror编译0；root目标重建及13/13、零skip、6.74s | 仅夹具；原13测试正文不变。未取得原calls.jsonl，非目标Windows运行，不能断定历史唯一根因 |
| fdbefeac | 真实SQLite/executor中旧helper返回running、持久succeeded，新重读succeeded，归档42/一次worker；Python3.14.4模块36通过、零skip、6.27s，真实冷payload0.713s | 受控计算替身与真实冷worker分别核验；原20s不变，产品执行器/worker未改 |

三次实际暂存补丁分别1832B/SHA50bf36e7…、1917B/SHA7102735b…、615B/SHAca1eb59c…，按.gitleaks.toml扫描均0发现。Windows完整坏JSON仍失败，未终止尾行留待下次读取；没有done写入或错flag路径的证据。局部改动不提供新的产品UI点击改善或目标OS验收。

远端612e的[Runtime42509570684](https://github.com/sijintech/stk/actions/runs/42509570684)于18:39:50Z整轮failure，12job成功；Python3.14/job128819473622的test_real_payload_archive_decodes_signed_values_after_worker_cache_is_removed返回running/error=None，6019通过、153skip、4未选、814.57s。真正helper超时走pytest.fail，故该断言不是20s耗尽的证据。[Desktop42509570653](https://github.com/sijintech/stk/actions/runs/42509570653)整轮仍in_progress，终态前不push：MacCPU1503/1503、559.67s，Metal254/254、337.61s，原生4/6、492.30s；video仍唯一slider证明失败，html-video仍Tab不可全见。WindowsCPU仍运行、原生尚待。Docs42509570687完整部署及Secret42509570637成功；本批新测试字节不在612e，不能借其结果验收。

证据：local-model-ci-42504540440/root/、windows-agent-ci-42504540481/review/、runtime-ci-42509570684/analysis-observer/；612e公开失败摘录在root-delivery-20261108-25/runtime-314-failure.log。a0f77fa3为尚未实现的上传CLI方案；设计暂存25059B/SHA30d790d5…扫描0。Claude18尚在独立树实现，未计作功能或安装态验收。最终Git/CI和索引收尾见root-delivery-20261108-25/closure.json，旧WIP保留。


## 2026-11-08 UTC：桥关闭生命周期和AX诊断的有限验证

本地源码7bfae902（Bridge）和0e0a1246（AX诊断），另有提案2aea4a95；均尚未push。Bridge新9例在HEAD旧源码8失败/1通过、0.78s，在新源码连同六既有模块共137通过、零skip、46.43s。真实OS目录锁、真实TransferManager日志及Bridge.shutdown受控重现运行中/准备中重叠；其他服务stub，上传后台用事件控制，不代全Bridge RPC静止或真实远端传输。线程创建失败与已创建后异常均覆盖，释放后原worker已退出。暂存15351B、SHAa868ceb2…，gitleaks0。

AX候选2完整75575B、SHA0aed5213…，暂存扫描0。独立五例证明完整1632B v3仅丢终帧/零进度原误拒、新保留response并标incomplete；两种v2仍拒。accepted逐字不变；坏帧/错代次、2s挂起、取消、stderr/flood、回收门保留。外部-Werror五组4.267s通过；root两目标构建成功，CTest reports_native_ax_cpu 4.24s/总4.32s通过。尚无Apple helper编译、OS像素或20轮证明。无新产品UI交付，固定起点点击未重测，既有Viewer/草稿验收不由CPU诊断代替。

bcec的[Runtime42504540440](https://github.com/sijintech/stk/actions/runs/42504540440)已failure，其余12job成功；3.14为test_servers_that_fail_or_exit_are_reported_and_not_relaunched在派生failed和监督错误详情之间KeyError，6010通过/153skip/4未选、842.13s，仍待修。[Desktop42504540481](https://github.com/sijintech/stk/actions/runs/42504540481)已于18:16:12Z整轮failure终态：Linux三job成功；MacCPU1503/1503、569.88s，Metal254/254、332.04s；原生4/6、434.93s，video为AX证明失败、html-video为Tab不可全见，未证与旧头同根因。WindowsCPU1446/1447、657.33s，唯一NativeAgentRuns.AnUnconfirmedSetReplyCannotRestoreContinueWhenItsSessionIsReselected解析错误，首字符d；Windows原生6/6、1341.53s成功，整个Desktop已终态，推送等待门满足；Docs42504540389部署及Secret42504540501成功。

提案统计/判断检查在aoci-proposal-review-20261108-22/root/；Bridge在bridge-transfer-shutdown-20261108-24/root/，AX在mac-ci-42495020086/root-ax-diagnostics-implementation/candidate-2/。实际Claude17仍设计修订，原八项/D1-D5及真实MuPRO缺口未关闭。认知收尾和本批最终提交/推送见root-delivery-20261108-24/closure.json，旧WIP保留。

## 2026-11-08 UTC：工作区CLI最终验证、联邦等待与691整轮终态

main源码2fcc7251c9a5b70a5918e87792e16b8bfe0046b1，仅三路径集成Claude8ae2088d；其父1a5dc3ad独立提案未合入。作者六模块100通过、0skip、54.752s；root主线test_runtime_hub_cli 42通过、0skip、15.716s。独立新最小Python3.12.14安装态42通过、0skip、17.224s，-I且无源码注入；wheel SHA11bacdc79c0398b2e231517d9888d08b3c01787ad5d3d52195e343bb336eb907，f052归档仅覆盖最终cli.py，已核2fcc产品差异仅该文件。9实际父进程模块来自site-packages且SHA匹配，无NumPy/VTK/PySide6/Torch/h5py；不是逐子进程完整sys.modules采集。

初稿零等待P2有旧红新绿：真实HubBackend加排队传输替身，只POST一次并轮询同ID三次后取得files；失败/超时不当结果，写零等待后原读wait恢复含异常路径。独立23项纯检查通过；作者注入旧全局wait=0的四新例均失败。真实联网用单Linux回环Hub/Node/Runtime与实际worker，review状态是精确请求种入；兼容旧节点为替身，不代旧安装发行或跨机/目标OS。Hub上传在文件检查与网络前拒绝，direct上传spy另证有6种实际文件访问。三路径完整暂存32723字节、SHAf6cce7e59d83d49e06223ca1b6b1924b698ca7cf3655b2003514db5d42efe242，gitleaks0。

root f052f06b406ccc56464ca5ae9942d81b699c38aa仅改联邦测试：准备前等待owner信息采用；生产busy不包含info，prepare会取消在途读取，故晚到info可使Register永不解锁。外部同源红绿均加0.5s响应延迟，仅等待一行不同：旧30.671185913s失败，新2.769111266s通过。固定起点zh_CN/1000×1200/scale1、a4最大化联邦Data、修订1无选择/计划/owner连接、隐藏Python稿及既有Viewer；实际50点击/0滚轮，完成同意、留出准入、显式启用/回退与撤权，Viewer和稿不变，无新增点击。root目标重建及24/24零skip18.464s通过；暂存857字节扫描0。该机制已受控证明，但Mac原日志未给info/future证据，不认定唯一CI根因。证据mac-ci-42495020086/root-federation-race/。

前整个[Desktop42495020086](https://github.com/sijintech/stk/actions/runs/42495020086)绑定691f3f12，于16:29:30Z completed/failure，push等待门已满足。LinuxGPU/包/新机包冒烟三个job成功；WindowsCPU1447通过、0skip/0fail、844.71s；Windows原生6/6、0fail、1030.19s。Mac构建成功，CPU1502/1503、531.86s，唯一ChineseNarrow1x联邦Register30s未解锁；Metal步骤跳过；原生4/6、501.4s，两视频0/20轮失败。691不含c0ff等待补丁，WindowsPDF本轮通过不证明旧根因或该新候选。Runtime42495020053整轮13job成功，Docs42495020085完整部署和Secret42495020054成功；新字节不得继承旧头绿灯。

AX两条诊断仍待实现：数值父链用于区分WebArea祖先/兄弟支；独立有界非阻塞进度通道用于无最终Response时定位API阶段。不能仅给最终Response加phase，更不降低2s/8s、四provider、唯一slider、DOM、OS像素和20轮门。没有新产品UI交付；CLI不记作点击改善。

Claude17仅设计文档，root独占main/共享构建/状态与推送。旧四文档和AOCI WIP保留；最终交付/新CI见d1-hub-workspaces-20261108-20/root/closure.json。MuPRO真实资产、科学扫描值、提案持久形式及原八项/D1-D5继续，HDF5仍需DAT，PET新专项后置。

## 2026-11-08 UTC：Bridge收块丢ACK恢复最终验证与691新CI

Claude15 `4d02ea3a03b8583d13bd8ab1a0a4a7fb8f771a53` 已仅三路径选择集成为 main `2cc40a0ddbe789770a43cb06c1f0f758ae48e524`，尚未push；root原生等待候选c0ff亦未push。远端691整个Desktop42495020086在16:22Z附近仍运行，须整轮终态后推送。Runtime42495020053已13job全绿，Docs/Secret成功；WindowsCPU成功，Windows原生128786216358仍live。Mac CPU1502/1503通过、531.86s，唯一失败为联邦ChineseNarrow1x的federation_register未解锁；Metal跳过。原生4/6，两视频仍失败，不能沿用旧7ef CPU/Metal结果。

真实Hub先收首1MiB、Bridge原journal仍bytes_done=0时SIGKILL/reap，仅重开同profile/state/journal，保持其他四服务原PID/创建时间；原transfer/key/request/upload_session恢复，首新块1048576、下一块2097152，总2621464字节。完成后原workspace.import仍待人工批准，批准前零文件/任务，之后精确大小/SHA一致；无Task提交，不声称程序消费了输入。驱动写后及启动前SHA核验，缺证明和清理失败独立禁通过。

最终script38e42c02…/testc56f8803…；README仅两处说明修正。Claude联合282项零skip通过/74.18s，最终source04/installed05各10断言通过；root主线新模块67项零skip通过/9.814s。root独立最小安装态以同一script运行10/10，场景5.722266164s、含清理6.579574818s，17模块来源探针SHA与root一致、无GUI/科学可选依赖且无残留；探针不等逐服务完整sys.modules采集。独立18纯反例无实质发现，提前SIGTERM和服务session丢失后从0重传真实红例正确失败。暂存75410字节、SHA0a266fba…，gitleaks零发现。证据 `d1-upload-restart-20261108-19/root/`、`claude/`。单Linux主机、一个故障点，不代网络分区/R3/许可求解或科学验证。

691新Mac独立视频在1598.441834ms收到rejected/webarea_outside_viewport_chain：raw4、chain1/length4、唯一WebArea、31nodes/depth10、trusted=true；已证四Group单链，但WebArea不在最内层下，尚无父子序列不能判断祖先或兄弟。HTML视频2003.230ms超2秒后owned SIGKILL/reap、无有效响应，默认trusted=false不证明TCC。两项均0/20轮、各2图且cleanup=true。证据 `mac-ci-42495020086/review/`；未推c0ff不在本轮。无新产品UI或点击交付，旧固定起点点击记录保持。

root继续负责main、公共后端/契约、桌面问题、共享构建、审查集成、四状态文档/AOCI和推送。实际Claude在独立stk-claude/claude/support接CL-D1-HUB-WORKSPACES-16，基线4d02，仅cli.py、test_runtime_hub_cli.py、docs/hub.md：为Hub补工作区create/list/files及原action观察，复用既有后端，先交固定候选供审阅；本片不接Hub上传、不自授desktop、不改协议或R2/R3。当前尚未交付。任务卡 `d1-hub-workspaces-20261108-20/root/claude-task16.txt`。

继续D1剩余合同/故障和云端项目、原生文献实际点击、Synthrix正常装配及D2-D5与原八项；MuPRO/MuFerro、插件自定格式/MuPRO HDF5、有限S2c方向已确认。真实执行主机/SDK/许可/小算例、扫描数值及分析修改提案持久形式仍待输入，HDF5仍需DAT完成验证；PET新专项后置。PR53/54实际头仍c9f13994/2dd3e4ee，不合无关旧差异。原四文档和AOCI WIP保留，正式新交付/CI/治理见本批closure。


## 2026-11-08 UTC：691新头Runtime整轮已通过

691f3f12的Runtime42495020053于15:45:20Z completed/success，13个job全过；Windows3.11/3.12各5098通过、254skip、580未选，分别701.01/900.42s，旧SIGKILL收集错误已获得新头Windows验证。Linux完整矩阵和文献/peer-macos/独立联邦等亦成功；不把Windows排除server组当该组验收。Docs/Secret已成功；整个Desktop42495020086仍live，Mac已目标编译完成并进入CPU测试，WindowsCPU仍构建，原生待出。root c0ff1ac7/7f7a40d3本地未push，仍须等前整个Desktop终态；最新交付见windows-pdf-ci-42487388780/review/closure.json。下方较早“Runtime仍live”为当时快照，保原WIP。


## 2026-11-08 UTC：原生WGC等待候选与固定截止反例

源码c0ff1ac76617769c9d266304f59d856a7485ca56已本地提交、未push；远端691的整个Desktop42495020086仍运行，终态前不再推。当前新Docs42495020085完整部署及Secret42495020054成功；Runtime42495020053 Windows3.11、文献三版本、peer-macos、web/协议/独立联邦等成功，其余仍live（15:43Z附近观察，不是整轮终态）。

旧7ef Windows job128763142651 PDF第13轮reprepared-page1 timeout。artifact13621583516只取result.json及3PNG共400958字节并逐项CRC，另目录/tail262509字节，未下载214MB整包。completed_cycles=12/images=103，最后13/closed，无13/reprepared或waiting完成图；12/reprepared与13/visible PNG完全同SHA、页一正确。缺新帧不能推断像素不匹配。实际vendored GHOST waitForEvent虽Sleep(1)仍循环待消息/计时器；WGC CreateFreeThreaded仅TryGetNextFrame、无UI wake，Ready后Host移除加载timer，支持候选但不证明Windows动态根因。

报告测试采用poll_before原deadline、调用predicate前后及pump后查期，pump(false)；统一process 1ms yield覆盖独立AX循环，无双sleep。原45s、8s seek、唯一slider/新DOM/OS像素/连续帧/20轮及Viewer/隐藏稿要求保留，无新产品UI或点击路径。同步SDK/事件回调不可抢占，只能拒绝其晚结果，不能称硬墙钟截止。

root两target构建成功，相关55/55零skip2.73s。新fake-clock正反例核44s成功、45/46s拒绝、无OS事件仍轮询、慢predicate/pump跨期、expired零派发；独立六contract探针C++20/-Wall/-Wextra/-Werror全过，三源码SHA前后稳定、终审0发现。暂存6098字节gitleaks0。证据windows-pdf-ci-42487388780/review/root-candidate-1/，closure记录最终发布；目标Windows/Mac编译和原生门仍未验新字节。

Claude15的source trial-03为10断言通过/场景5.592835773s、清理干净，提前SIGTERM红例U2拒绝；只属过程结果，尚无最终候选/安装态交付。旧root输入28/installed11及peer18的固定字节结果保留，不替本新模块验收。


## 2026-11-08 UTC：peer实际点击与AX拓扑候选，前整轮终态

源码：peer root a1904447（实际Claude b510da04单路径）；AX root 79ae0adf7bfe7734a49f33fd571ecdd4e7b650bd。前7ef整个Desktop42487388780于15:04:55Z completed/failure，满足等待后push条件，不能称全平台通过。Mac编译成功、CPU1502/1502与Metal254/254，原生4/6；WindowsCPU1446/1446、873.20s，原生5/6，PDF cycle13 reprepared-page1像素timeout/231.05s，两视频384.28/395.15s通过。WindowsCPU本轮尚无14补修，故空JSON具体根因仍未知。旧Runtime42487388719两Windows收集失败，4399本地修复待新CI；Docs42487388755完整部署与Secret42487388666成功。

root重建stk-peer-app-tests并实际18/18、零skip、9045ms。固定起点1440×1200、scale1、en、maximized-a4，真实Bridge、syntheticHostDTO；Viewer及隐藏Python稿保留：

| 起点/动作 | 实际点击/滚轮 | 结果 |
|---|---:|---|
| send-tab，选择两份冻结文件 | 11 / 0 | 两文件Host回执解锁Offer，其他稿与Viewer保留 |
| sender，历史操作 | 20 / 0 | manualSession和grant手改值保留 |
| Files，选中已登记记录 | 1 / 0 | Peers section2及record草稿，无RPC send |

peer暂存13370字节gitleaks0，证据native-peer-fixture-20261108-16/root/candidate-1/。

Mac真实artifact经两result.json独立CRC核验：视频公共AX响应1603.426ms、trusted=true、raw Group4、31nodes/深10，因旧multiple_viewports提前返回；不能据此证明四者为祖先链。HTML-video在2004.280ms deadline后SIGKILL/reap，无解码响应，默认trusted=false不证明TCC拒绝。两项cleanup完整，原4次provider空查询仍保留。

AX新候选纯选择器保raw数，全部同几何Group须一条严格祖先链，外层子树恰一WebArea且在最内层下；helper逐wrapper核原窗，accepted核chain/node/depth证明，私有响应wire同步升级。原2s child、8s seek、4次provider+250ms真实UI泵、真实WK/session/navigation/layout、新DOM、唯一time-matched slider、OS像素和20轮门保持。没有新产品UI点击或Apple编译/原生通过证明，HTML-video deadline仍待定位；WindowsPDF另追。固定差异与实测见mac-ax-ci-42487388780/review/root-candidate-2/及closure.json。

最终两目标构建成功，相关55/55、零skip、2.76s；depth独立编译旧红新绿（14层边界通过、15层伪证明拒绝），暂存24314字节gitleaks0。候选1独立审阅发现depth缺口，候选2由root修复复核，未称独立终审通过。


## 2026-11-08 UTC：D1输入/设备撤权最终字节与新CI边界

源码 main `4399f2fa6dfaba941922d2808ca023eba3766105` 已本地提交，尚未push；远端仍 `7ef5d21e`。前整个Desktop42487388780仍运行，终态前不推送。原四文档WIP和AOCI预存改动保留，最终交付状态见 `d1-input-transfer-20261108-18/root/closure.json` 与实际Git。

新增真实两部署输入/撤权样例：同一1048599字节公开输入，部分会话1MiB后重开同ID/offset，完成SHA校验；B blob必须经原workspace.import人工批准才导入，完整TaskSpec另经批准。两边固定程序读取冻结输入并输出相同SHA，原Runtime清单、各一task/run/marker、program和worker清扫前退出。B仅撤本次desktop设备，热/冷客户端后续11类请求均401，节点仍在线、无新增action，原Runtime任务保持。不是断网、桥日志恢复、项目/用户授权、在途请求中断、已交付字节召回或pending上传字节不变证明。

最终新模块及singleton联合28通过、零skip、14.81s；最小非system-site-packages包以-I installed复验11断言通过，场景6.045540141s、含清理8.1s，实际site-packages来源/模块SHA一致、清理干净。产品Python到7ef无差异，沿用已重建包，不把旧harness试跑当新字节；当前script46f83b43…/helpercf2b13c9…。独立终审关闭A额外queued任务假绿和迟到terminal延长局部截止，反例已入测试。暂存25040字节gitleaks零发现。

7ef的Runtime42487388719于14:14:50Z整轮failure：11job成功、两Windows矩阵因新增Linux专用singleton测试在收集阶段引用不存在的SIGKILL而报错，未执行该矩阵测试。本提交改为函数体解析信号名称，缺SIGKILL的模块红绿反例及Linux原11项通过/5.73s；仍待新Windows CI。Docs42487388755完整部署成功，Secret42487388666成功。Desktop当前Linux三job成功，Mac已越过编译/CPU阶段、WindowsCPU运行，原生最终结果待出；不能继承旧头平台验收。

证据：`d1-input-transfer-20261108-18/root/validation-summary.json`、`candidate-2/`、`joint-final.xml`、`installed-final/`；收集补修红绿及Linux11项在 `native-ci-20261108-17/root/`。首试因原始spec和补默认值比较错误失败，第二试因输入清单另含media_type而失败；均保留，修后只明确比较path/size/SHA，不冒称产品修正。没有新产品UI交付，既有固定起点/点击、Viewer及隐藏稿保护继续有效。

root继续独占main、公共后端/契约、共享构建、审阅集成、四状态文档、认知与推送。实际Claude仍在独立stk-claude/claude/support做CL-NATIVE-PEER-14，只改peer_test.cc，候选尚未集成或目标OS验收；具体Windows空JSON根因仍未知。后续D1其余合同/故障与云端项目、文献实际点击、Synthrix正常装配、D2-D5和原八项保持；PET新专项后置。MuPRO/MuFerro、插件原生格式/MuPRO HDF5及有限S2c按已确认方向推进，真实许可/主机/小算例、扫描数值与提案持久形式仍待输入；HDF5仍需DAT完成验证。

## 2026-11-08 UTC：D1 元数据、Hub 单实例与丢结果重启最终主线验证

本地源码b517554a、2c9729b8、c5d8e503及ddd7d7c2（Claude原755212b2）；本节未push、远端fd394e46。最终提交/推送和新CI见 `d1-hub-restart-20261108-12/root-integration/closure.json`。本批没有产品UI交付或新点击验收，Viewer/隐藏稿及明确run/save/send门保留。

- `d1-contract-fields-20261108-13/root/`：真实旧oracle31红/3绿，固定candidate2原联合155项零skip通过/51.70s；五时间字段按同原task/state的各自Runtime逐值核对，created_at同任务重放稳定，不比较跨部署时钟。固定夹具执行完才要求全五字段；未执行任务缺省/null不变。MIME缺/错先固定错误拒绝，不导出原值；独立run级5文件反例关闭P2，旧候选/试跑保留。script cf2b13c9…，原安装12项结果只证当时产品字节。
- `d1-hub-singleton-20261108-14/root/`：修正过短测试令牌后，旧代码真正7失败/1未选/11.13s，均到达缺锁行为；早期错误夹具日志保留、不作并发证据。最终49通过、零skip、13.48s（singleton/模板平台/控制/联邦），独立candidate2三SHA稳定，14纯mock通过。实际双进程异端口/alias竞争、TERM/KILL同inode重启、pair并行和独立state均验；配置/工厂/serve内部BlockingIOError、正常退出/SystemExit/KeyboardInterrupt均释放且不误标busy。正式serve生命周期锁才是保证，嵌入create_app多worker需外部单实例约束；无DDL或凭据迁移。
- `d1-hub-restart-20261108-12/review/candidate-2/`：初稿错误/缺失driver SHA仍ok的P2已关闭。独立9个proof/run、2个强制全断言pass仍被独立门拒绝、3个真实临时文件篡改/删除零mock spawn及43个保留故障反例通过，未起服务；作者修后157项、source/installed各11项另存，不替最终主线证据。
- `d1-hub-restart-20261108-12/root-integration/joint-main.log/xml`：最终主线8个测试文件271通过、零skip、74.57s；1个既有Starlette testclient/httpx弃用警告。所有测试key空/model unset，无收费模型或真实求解器。三份候选集成SHA相符，旧WIP保留。
- `d1-hub-singleton-20261108-14/root/installed-source.json`、installed-check.json：从已提交c5产品目录归档离线构建wheel，wheel SHA d65b9897…；ddd到c5的suan/toolkits/pyproject零diff。实际最小独立venv非system-site-packages，CLI SHA217e35e3…；未装NumPy、VTK、PySide6、Torch、h5py。首选旧测试解释器无pip，首次打包命令未构建；后改用已缓存uv离线构建/安装成功，原失败日志保留。
- 同批 `root-integration/installed-parity/`、installed-disconnect/、installed-hub-restart/：-I installed实际site-packages来源和全部关键模块SHA匹配新主线。正常12断言，场景11.022404007s/总13.1s；断连10断言，场景23.604974931s/总24.721151801s；Hub重启11断言，场景7.680591277s/总8.607716267s。均预算内、清理完成且无残留。新helper cf2b13c9…，Hub script dd29a3dd…/driver a76fb69b…，driver双次文件SHA匹配；Hub两delivery/一次Runtime.submit/节点缓存恢复同task，一task/run/marker。原program和worker均显式取消后清扫前退出，清理不代取消；不是再次Runtime幂等提交或全部故障通过。
- 暂存检查：元数据/Mac补修各自gitleaks零发现；singleton三路径14071字节、Hub三路径81597字节扫描零发现，Claude自身暂存扫描亦零。最终文档增量另扫，见closure。
- 前远端fd：Runtime42481547894于13:01:05Z整轮success，13job全过；Docs42481547906于12:43:46Z实际构建部署成功；Secret42481547877于12:43:24Z成功。Desktop42481548048于13:51:08Z整轮completed/failure，4job成功/2失败：Linux GPU/包/新24.04冒烟均成功；Mac128734373211于Build失败，AXValueGetValue旧UInt32常量不能转AXValueType，CPU/Metal/原生未跑。2c9729b8仅改kAXValueTypeCGPoint/CGSize两行，未目标Mac编译，不称修复通过。WindowsCPU128734373360为1445/1446通过、1个PeerMouse.ActualClicksSelectTwoFilesHostReceiptEnablesOfferAndPreservesOtherDraftAndViewer空JSON解析失败，902.99s；Windows原生文档job128745117982六项全过/1304.12s（实际required-evidence门成功）。Claude14仅在独立树peer_test.cc定位/修夹具，未交付；前整轮等待门已满足，本批新字节仍须新CI，不继承旧头结果。PR53/54头c9f13994/2dd3e4ee仍未变、未合无关旧差异。

这只补D1时间/MIME、正式serve单实例和接受后丢结果重启边界；输入传输/撤权、其他合同与故障、云端项目、目标OS/跨机、真实MuPRO/HDF5-only完成和科学有效性仍未完成。研究扫描数值及分析修改提案持久形式不代选；原八项、文献实际点击、Synthrix正常装配、D2-D5继续，PET新专项后置。

## 2026-11-08 UTC：主线 AX 候选与节点断连最终字节复验

本地源码 `d2f6262262e713d4bf1e986fb15d03a5fea70b59`（原生12路径）及 `688db5a0889f301f339150f836de8caa3cd1abea`（Claude12三路径）；本节成文时未push，远端b3c3b912。最终交付/新CI见 `native-ax-client-20261108-09/root-integration/closure.json`。无新产品UI或实际点击交付，既有Viewer/隐藏稿保护和原原生验收门保留。

- `native-ax-client-20261108-09/root-integration/build-main.log`、build-main-result.json：root独占merge-check构建stk-reports-native-ax-tests和stk-reports-native-window退出0，12文件前后SHA匹配最终候选0b4b53c0；未Apple编译/链接。ctest-main.log/xml/result为DocumentResources、NativeMediaProbe、ReportDocumentHost和reports_native_ax_cpu，43/43通过、零skip、2.85s；Linux Unsupported用例不是原生呈现通过。
- 同批 `independent-review/review-final.json`：固定c16170c8/0b4b53c0的12blob独立源码审阅无新增实质问题，没有执行Mac。仅四次完整空provider读允许一次公共AX helper；只读本应用公开AX、唯一slider，新DOM与真实WKWebView/资源/session/导航/布局epoch再核后点击。2s原child期限/8s原seek期限不续期，cancel/关闭UI持续泵并drain owned child，丢失回收证明不能通过；同步AppKit查询不可抢占，只能拒绝迟到结果。唯一slider、原生输入、DOM/OS像素和20轮均未放宽，仍待新Mac CI。
- `d1-node-disconnect-20261108-10/review/candidate-2/`：三blob精确匹配Claude最终a215972d，script8d75922fec09e1ea5af91debb1bbcd732ac178172174f624fedb58e0abeaffc3。旧提前退出/worker替换反例从全绿变D2及D5/D7/D8拒绝；五个独立真实sleeper场景通过、八自有进程全reap。Claude最终实际trial-06-source-review14/07-installed-review14各10断言通过、23.6669/23.8132s，仅作为作者证据；未误用旧trial01。
- `d1-node-disconnect-20261108-10/root-integration/pytest-main.log/xml`：root在主线最终三路径运行normal/disconnect联合90项、零skip通过，43.90s；source实际服务场景包含在内。inputs.json/validation-summary.json绑定五输入SHA且前后稳定，产品后端未改。
- 同批 `installed-main/`：非system-site-packages最小server/control/test Python3.12，以-I installed实际启动Runtime/Hub/Node、杀原Node并同profile重连。10/10断言通过、scenario23.544913289s、含清理24.654371985s，预算按原始单调耗时判定。来源均site-packages且12模块SHA相同；helperc1235e8c…/最终script SHA匹配。原program/worker全阶段冻结，显式取消后清扫前按PID/create_time核退出，一任务/run/marker、无遗留；清理不用于补取消证明。包来自58fbd03e，58到当前suan/toolkits/pyproject零diff，不借版本号替字节证据。
- gitleaks-staged-native.json及断连gitleaks-staged.json：各自暂存扫描退出0、零发现，原生patch106792字节；每次commit前执行，diff空白通过。四状态文档只暂存root新增前缀，原WIP/AOCI预存修改保留；工作树认知对齐不等发布索引全量提交。

前远端b3c3b912整个Runtime42479012065于2026-11-08T12:26:56Z completed/success，13job全成功；Docs42479012061于12:13:16Z completed/success，正式站点构建和发布均完成；Secret42479012010于12:10:58Z success且扫描步骤执行。b3六文档路径不命中Desktop触发，未生成其Desktop；最近适用304ba0be的整个Desktop42472416447已于11:15:29Z failure，1job成功/3下载失败/2skip。推送等待门已满足，没有本轮新目标OS原生证明。独立核验 `root-integration/ci-prepush.json`；PR53/54头未变，未集成无关旧差异。

本轮断连只是单Linux主机NodeAgent进程SIGKILL；不含网络分区/长中断/离线自然完成、Hub未完成action重启或全D1。实际Claude已接CL-D1-HUB-RESTART-13，仅三新路径、同a215基线；须Runtime实际接受且原进程运行/Hub尚queued时丢首结果、同库重启和原action重派。保Node原缓存，缓存恢复不称再次Runtime.submit；尚未交付。D1其余合同/传输撤权/云端项目、真实MuPRO/HDF5-only完成、跨站/目标OS和科学有效性仍未完成；S2c/DAT限制与原八项/待决保留。

## 2026-11-08 UTC：文档 CI 下载修正、599 全矩阵及候选反例

本地源码 `9053ea5c394060252e936a121229668d6e185594`，成文时尚未push、远端599937f9；最终提交/推送/CI见 `docs-libvips-20261108-11/root/closure.json`。本批无新产品UI或点击验收，既有Viewer/草稿保护门未改。

- `docs-libvips-20261108-11/root/preflight.json` 与 fetch-step.sh：直接解析当前YAML并执行其下载脚本，bash语法通过；同官方release的libvips8.14.5包6,763,082字节，SHA-512与sharp0.32.6固定上游一致。
- failure-probes.json：curl最终失败退出22、坏摘要退出1；两个实际工作流脚本反例均无正式包和半文件残留。未强制安装、跳过TLS/摘要或改下载来源。
- install.log/build-results.json：独立精确Node22.23.3、pnpm8.15.9，冻结锁安装18.603s；sharp确认Using local及Integrity check passed。首次隔离PATH缺npx，pnpm build虽退出0但Pagefind检查失败，build.log保留。补本地npm/npx后build-with-npx.log构建14.494s，38页、Pagefind37页/两语言，index/en/index/search JS均非空；锁SHA前后37c1ba34…一致，跟踪文档文件逐Git blob核对9053树。修正并非声称远端部署已成。
- staged-scan-summary.json：两路径diff2772字节，gitleaks退出0/零发现；独立CI小审阅见 `d1-node-disconnect-20261108-10/review/candidate-1/docs-ci-review.json`。root仅提交自己新增状态前缀，原WIP和AOCI预存修改保留。

599937f9的整个Runtime42477006366于2026-11-08T12:00:18Z completed/success，13job全成功：Linux3.11为5737通过153skip4未选/843.19s，3.14同计数/905.10s，3.12为5754通过136skip4未选/847.58s。五矩阵日志零失败；三Linux含新41项D1。Windows3.11/3.12各5098通过254skip395未选、820.90/899.00s，server标记组被排除，不作为Windows D1或原生验收。其余八job成功含三文献/协议/peer-macos/Flower/web和该workflow desktop组，详见ci-599-runtime-terminal.json。
Secret42477006328 success。Docs42477006418 attempt1及2均sharp/libvips8.14.5 Request timed out，正式构建未启动；未第三次重试。599改动不命中Desktop路径过滤，未触发其整轮；最近适用304的Desktop42472416447已于11:15:29Z失败终态，前推送门已核。当前没有新的目标Mac/Windows原生证据。

Claude12候选script22c038cd…由独立审阅两个P2纯AST/文件反例证明可假绿：Node已退出0/1仍当主动SIGKILL；worker.json换A为B后B和program已死、原A仍活，十断言仍可全过。root已要求固定杀前有效存活身份、真实SIGKILL和原program/worker的全阶段绑定及取消前退出，不由finally sweep兜底。候选未集成；旧trial-01绑定其他字节，不作当前验收。证据review/candidate-1/review.json、pure-probes.py、probes.json；修后需重新source/installed实测。
Mac公共AX候选独立提交c16170c8及绝对时限后续0b4b53c0，原生辅助有CPU1/1、严格编译与Linux consumer object证据；root最终审阅仍在进行，未Mac编译运行，不称修复或20轮通过。真实MuPRO/跨站/科学有效性均未验，D1其余故障/合同和云端项目仍未完成。

## 2026-11-08 UTC：D1 真实双部署与最终安装验收

本地源码 `6ae9699940633de8fd4de004486bd440107e7bc9`，Claude原提交6cc2d39e选择集成4b33e131；本节成文时尚未push，远端304ba0be。证据根 `d1-parity-20261108-08/root/parity-integration/`，最终提交/推送见closure。无新产品UI或点击验收。

- `final-boundaries-red.xml`：两个无服务反例各失败，分别是受支持Python3.12的config.exists抛PermissionError中断后续清理，以及实际1.04s/预算1s被round成1.0假绿。root改为整步隔离和未舍入耗时后，`final-joint.xml`（41项新样例/边界＋20项既有Hub CLI）61通过、零skip、23.35s。
- `installed-final/`及installed-final-summary.json：root独立最小server/control/test extras、非system-site-packages Python3.12，用-I installed运行最终脚本c1235e8c…，9/9断言通过，scenario10.964686322s、含清理12.1s。A直连Runtime与B真实Hub/WS/Node/另一Runtime来源base与12模块SHA一致；各2任务/run、每个marker严格匹配实际程序PID，程序/worker均退出，目录和进程无残留，五证据文件无个人路径/Bearer等禁止标记。
- `installed-product-binding.json`：已装包由58fbd03e归档构建；git diff58..6ae --suan toolkits pyproject为空。最终harness另绑SHA，不以包版本或旧Git头替代字节证明。最小环境无GUI/科学依赖；未逐服务记录sys.modules，未称完整D1或跨机通过。
- 独立审阅在review/parity/candidate-2、candidate-3及本目录review-final.json/probes；最后两边界均有纯桩红绿验证。Claude最终原版39项/双模式试跑是其交付证据，root最终61项和-I验证绑定已修字节，不混用初稿绿灯。
- code-delivery.json：选择集成暂存81622字节、root修正6266字节，两次gitleaks均退出0/零发现。四状态文档仅提交本批新增前缀，原WIP和AOCI预存资产保留；工作树治理不等发布索引完整提交。

前远端304ba0be的整个Runtime42472416392于2026-11-08T10:57:40Z completed/success，13job全成功。Linux3.11/3.14各5696通过153skip4未选，分别845.02/716.20s；Linux3.12为5713/136/4、937.97s。Windows3.11/3.12各5098通过254skip354未选、934.25/805.86s；旧24项失败均消失。文献三版本、协议、web、peer-macos、Flower和workflow desktop也成功，详见root/ci-304-runtime-terminal.json；不把skip计为能力通过。
整个Desktop42472416447于11:15:29Z completed/failure：Linux GPU job128706090506成功；Linux包job128706090129配置时googletest下载收流curl56，WindowsCPU128706090402下载ninja1.13.2 HTTP503，Mac128706090443下载fmt12.2.0 HTTP2 framing curl92失败，额外必跑检查缺XML因测试未启动。Windows native和Linux smoke跳过，不能借ec32/a506的原生结果作本轮证明。前整轮推送等待门已满足。
Docs42472416432、Secret42472416393各重试一次后仍failure：attempt2 build job128708594837的sharp-libvips请求超时，gitleaks安装job128708601818收流退出56，未执行正式构建/扫描。未改变网络策略或绕下载校验，没有第三次重复触发。

当前只验正常任务切片：state/reason/cancel_requested、三字段产物及下载、UTF8字节游标、重放/冲突、取消和真实启动数。media_type/更多时间字段、输入传输/撤权/其余故障和云端项目语义仍待补。Claude12仅新增disconnect.py、DISCONNECT.md和新测试，正在独立树验证NodeAgent离线/原profile重连；root的另一原生辅助在第四树开发公共AX候选，尚未Mac编译/运行、不算修复。真实MuPRO许可/HDF5-only完成和科学有效性仍未验。

## 2026-11-08 UTC：MuPRO HDF5 预检、完整回归与最小安装核验

源码 `58fbd03ee5976af90a3a083dcb24cf0aeed4994f`；证据根 `/home/mnemora/.local/state/stk-validation/d1-parity-20261108-08/`。本节成文时尚未push、远端ec32a182；最终交付及推送见root/closure.json。无新产品UI或点击验收。

- `root/stale-hdf5-red.xml`：旧代码2失败/1通过，CLI接受旧run.h5、制造MuFerro仍成功运行；修后green为3通过。上传/求解器之前拒绝，不改输入字节或引入HDF5依赖。
- `root/mupro-preflight-joint.xml`：90通过/2跳过、102.80s；CLI/计算wrapper、项目流程、HDF5收集及agent准备。两跳过均缺STK_TEST_MUPRO_PREFIX；制造SDK不证真实许可或科学有效。
- `root/ci-fixtures-red.xml`：24失败/1通过，复现ec32五通用矩阵的两个旧等级断言和22传输桩缺server_key。green五文件联合91通过、13.76s，含材料权限及端点漂移/传输恢复/审批；生产门不变。
- `root/full-python.log/xml`：完整非desktop/perf回归退出0，5698通过/151跳过/4未选、964.35s、零失败。full-inputs-before/after.json的850跟踪输入SHA全同。full-python-summary.json列完整跳过原因：未供PDFium/编码器/Flower/helper/MuPRO和Windows专属，另有15个既有离屏探测SIG11；不借旧专用组证明本次跳过能力。
- `root/minimal-install.log`及minimal-imports.json：先从ec32归档安装server/control/test，独立venv非system-site-packages，四入口/后端无GUI/科学模块，installed Hub CLI20通过/10.51s。随后minimal-install-58.log、minimal-imports-58.json和minimal-hub-cli-58.xml：从58已提交归档重新构建安装，实际site-packages服务/后端无GUI/科学模块，20通过/8.54s。这两次不是新D1harness的最终验收。
- `root/preflight-ci-staged-gitleaks.json`：本批源码暂存27932字节、退出0零发现；独立审查见review/preflight。Claude初稿trial-2和trial-installed各9断言通过，13.3s/20.7s且cleanup_ok；最终需修预期产物、真实启动计数、预算和移除失败反例，未集成，不沿用初稿绿灯。

远端ec32 Runtime42468258331已completed/failure：Linux3.11/3.12/3.14及Windows3.11/3.12各24失败，均定位上述旧测试前提；其他成功包括文献三版本、协议、web、peer-macos、Flower及该workflow desktop组。修正源码仍待新头CI。
整个Desktop42468258292于2026-11-08T10:22:29Z completed/failure，前整轮推送等待门满足。Mac job128692718551的CPU1501/1501（含13个新agent UI）、Metal254/254通过；原生4/6，两个视频唯一time-matched slider失败、退出8，各0/20轮。WindowsCPU拉CMake4.4.4、Linux两job拉googletest1.17.0均下载504，下游Windows native/Linux smoke跳过，不继承旧a506目标平台绿灯。
Docs42468258328、Secret42468258293各attempt2仍下载504，分别sharp-libvips/gitleaks；后者扫描未执行。未绕下载校验或重放生产动作。本批Mac终态独立审计在review/mac-ax/ec32-terminal：8次AX仍2节点/0slider，与旧头同型。外部公共AX helper未Mac编译/运行、未父端接线，不算修复；唯一slider、原生输入、DOM/OS像素与20轮门保留。

云端项目语义、真实MuPRO/HDF5-only完成、目标OS新UI及科学有效性仍未验；四状态文档旧WIP和AOCI预存资产保留。最终Git/推送/扫描及工作树治理状态见本批closure。

## 2026-11-08 UTC：S2c MuPRO 接线、目标绑定与原生卡片验收

源码 main `b6b92d911860b52eda755679f4cc2094a39ba24d`；证据根 `/home/mnemora/.local/state/stk-validation/s2c-wire-20261108-07/`。此前组件99/8只属于旧字节，本批最终结果如下。

- `root/joint-final.xml`：154通过、零跳过、28.27s；`python-final-inputs.json` 的17个Python源码/测试输入前后稳定。严格桥接包含新工具/卡片结构、桌面专用目录排除、完整计划限制、单次消费、资源/修订/busy/容量、失联及转发恢复。
- `root/runtime-final.xml`：22通过、零跳过、148.34s；真实本机Runtime配合制造MuFerro程序、脚本规划回复、旧工作流与Runtime/Hub传输。包括既有案例准备→完整计划→人工首次批准→运行/收集/分析→原观察，重复决定没有第二个Runtime任务。无收费模型或真实MuPRO许可运行。
- `root/native-build-03.log`、`native-build-clicks.log`：共享stk-project-tests目标构建退出0；`native-runs-final.xml` 最终13/13、零跳过、6.401s。独立原生两提交曾12/12，root修正/实际点击另验，不将作者局部链接冒充共享重建。
- `root/native-project.xml`：919/919通过、零跳过、722.343s，进程退出0。完整回归二进制含原12卡片例，后补实际指针例由最终13例单独覆盖；产品实现相同，测试源新增一例。记录24输入时唯一漂移为新增该C++用例，17个Python输入不变。
- `root/code-gitleaks.json`：暂存177180字节扫描退出0、零发现；提交前diff空白检查通过。四文档仅本轮前置增量提交，AOCI预存资产不整包纳入。

固定点击起点：英语、缩放1、1280×1600、a2最大化AI智能体、已选会话的待批准卡片，初始prepare开关关闭。实际鼠标按下/抬起两次：读取完整计划、批准开始；结果各一次run_plan/run_decide，未发planner start，Viewer保存状态及屏幕布局完全相同。长字符串、Unicode、路径和空格经无损换行可完整读取；640px另测每行宽度。此为CPU窗口事件驱动/FakeTextMeasurer，未执行Mac/Windows新功能UI或GPU字体验收；隐藏草稿保护另属原有完整项目回归。

审查证据：`review/backend-wire/` 与 `review/native-6f009292/final-52bb7b4d/`。早期preliminary/wire/binding日志包括陈旧测试断言、fixture参数/回执/Schema不匹配，修正后最终套件通过；不删失败或借前一轮成功覆盖后改。实际修正含完整计划视觉裁剪、目标失败后Continue、stale decline门、historical状态标签、混合步骤回放、decline的ok与端点竞态；传输worker保留ContextVar，新journal还核原端点，重开不改投。

前置远端 `a506cc69a0a86b596eedb55551cc31813648228b` 的整个Desktop42459561098已于08:42:54Z completed/failure，六job均终态、五成功一失败。Windows native128675100405成功，artifact13611270962六份result均20/20轮且保留Viewer/Python草稿；Mac128665708537 CPU1488/1488、Metal254/254成功，两视频失败均为Own-WKWebView唯一时间匹配slider断言，原生4/6、退出8。250ms时序候选未解决问题，不削弱唯一slider/OS像素/20轮门。同头Runtime42459561111、Docs、Secret成功。详见 `ci-audit/desktop-42459561098-final-audit.md`；前整轮等待门满足，新提交CI另记。

真实MuPRO主机/SDK/许可/小算例、新目标OS UI、科学有效性与HDF5-only完成仍未验。HDF5附加结果仍需DAT完成核验，扫描数值与提案持久形式未代选。推送/新CI/AOCI最终身份见本批closure。

## 2026-11-08 UTC：S2c 批准组件与既有 MuPRO 路径回归

源码本地main `afef46c52336ba6dec00594ad1edad560e582b86`（Claude原867eef9b）及 `67670ae30c137fb45903b9f0e90d7421cb4ebdde`（root），尚未push，远端a506cc69。证据根 `/home/mnemora/.local/state/stk-validation/s2c-agent-run-20261108-06/root/`，最终Git/CI与治理见closure。
所有测试KEY为空、MODEL unset；仅制造数据/受控模型适配器与临时本地Runtime，不调用外部或收费模型、真实MuPRO许可软件。未改端点、凭据或网络策略。

| 实际检查 | 结果和范围 |
|---|---|
| Claude first-claim final.xml / related.log | 38项工作流+13项归档/关注回归通过；独立树只交两文件 |
| Claude red-no-started-check / red-no-archive-recheck | 去掉历史started门2失败；去掉事务内归档门1失败；源码恢复后绿 |
| root ledger-first / ledger-second | 各15通过，早期组件检查；不覆盖最终新增观察接线 |
| root joint-01 | 路径预检错误，缺不存在的拆分测试文件，退出4且未跑测试；改用实际test_agent.py后继续 |
| root joint-02 | 97通过，21.29s；尚未覆盖后续_observe修正 |
| root observe-red.log | 2失败，17 deselected：运行卡draft_id错误、运行收据丢原run身份 |
| root joint-03 | 修正后99通过，18.55s；后续decline来源小修正另由joint-04覆盖 |
| root joint-04.xml / .log | **最终8文件99通过、零跳过，19.14s，退出0**；12个记录输入SHA前后相同，不宣称覆盖全部依赖 |
| root muferro-final.xml（最终源码67670ae3） | 既有工作流MuPRO/agent合成Runtime链8通过、114.88s，退出0；非真实许可求解 |
| root claude/ledger staged gitleaks | .gitleaks.toml扫描20.55KB/27.86KB零发现；没有把旧扫描当本批结果 |

另muferro-legacy.xml为观察接线修正前8通过/114.89s，最终另跑muferro-final，不借旧结果覆盖新源码。
四个spawn进程争抢同一决定仅一次dispatch；真实跨进程workflow首次启动竞争、编辑器先启动/停止、归档/修订漂移、丢回执不重派和历史原approval回执均有检查。批准前记录和运行claim是两个事务：会话先消费，运行claim再原子排除手工竞争；中间失败不解锁重派。observe不会启动、恢复或取消。
Claude只读审查R1已由root修复并补两条回归；其外部报告审查时38项不是root最终99项。新账本未授认证身份，不增DDL/对象种类；只支持内部组件，目前没有注册prepare_muferro_run、后台派发转交、桥start/decline或原生卡片。CL-S2C-EXECUTOR-08已另派，仅独立树两路径，尚未集成。
没有新产品UI交付、固定布局或实际点击数，不能以后端测试代UI验收。真实许可软件、目标OS、科学有效性、D1双部署及HDF5-only完成仍未验；原DAT完成验证保留。
同远端a506的[Runtime42459561111](https://github.com/sijintech/stk/actions/runs/42459561111)已success（07:54:07Z），Docs/Secret成功。[Desktop42459561098](https://github.com/sijintech/stk/actions/runs/42459561098)整轮仍in_progress：Linux三项成功、Mac CPU和Metal成功，Windows CPU测试进行中，原生媒体待出；须整轮终态后push本批，不能借成功子job宣称全绿。
PR53/54头仍c9f13994/2dd3e4ee；未把旧重复实现或历史交接隐式合入。四文档仅前置新节，旧WIP保留，AOCI托管改动与代码分开；本轮工作树对齐不代表尚未push的发布索引。

## 2026-11-08 UTC：AX 真实调度间隔与前整轮 Desktop 终态

新源 `598a069b`，前修正源dc5890b1；证据根 `native-ax-20261108-05/root/`。本节不新增产品UI或点击验收，没有真实MuPRO/模型调用；测试构建KEY为空且MODEL移除。
旧已下载Mac两个result.json重新按字段核验：4次完整查询分别只累计34.067041和45.657208ms，均2节点/0slider/0候选/未送输入。
[WebKit311616](https://bugs.webkit.org/show_bug.cgi?id=311616)描述远程对象先于AX初始化的空属性竞态，[当前WebViewImpl源码](https://github.com/WebKit/WebKit/blob/main/Source/WebKit/UIProcess/mac/WebViewImpl.mm)在属性查询时按需启用AX；据此作时序候选，不推断runner已含该修复。
夹具仅在已完整/零候选且尚有重试机会时，泵本窗真实UI直到steady_clock至少250ms后再查；仍4次、原节点/深度/时间匹配及DOM/OS像素/20轮。没有AX setter、DOM seek、全局输入或生产权限修改。
Linux报告目标重建退出0，native-build-01.log；**新增APPLE分支不在本机编译/执行范围**，目标Mac结果待下一CI。暂存836字节gitleaks零发现，原代码前189/5及CPU24结果不覆盖此新分支。
前远端761a9e37的[Desktop42455805095](https://github.com/sijintech/stk/actions/runs/42455805095)已completed/failure、updated07:27:11Z，全部6job终态：4成功，Mac失败（9/1488文献、原生2/6视频），Windows原生失败（1/6 HTML视频divider）。前整轮等待门满足，不代表通过；新源码须新头验证。
Claude145行只读S2c方案已由root审阅，未跑其矩阵。root选择会话payload/无项目格式升级、桌面明确资源和现有批次上限；再将事务内首次启动模块CL-S2C-FIRST-CLAIM-06派发独立树。原计划/请求SHA、修订和归档须与首次started同事务核验，防会话锁之外的编辑器竞争。尚无该模块提交或完整S2c功能验收。
四状态文档仅前置新节，旧WIP保留；认知工作树和发布状态分开，实际push/新CI结果见本证据closure。扫描数值与分析提案形式仍未代选。

## 2026-11-08 UTC：CI 定向修正的本机证据（目标 OS 待验）

源提交 `dc5890b17eeb4c1b7a76aa42e0e8770abeccc924`（5文件），本地main；远端仍761a9e37。本批证据根 `native-ci-20261108-04/root/`，最终Git/认知/CI见该目录closure。
所有测试 `STK_TOKEN_PLAN_API_KEY=` 且移除 `STK_TOKEN_PLAN_MODEL`，无收费模型、真实求解器或端点/网络策略修改。

- **文献租约：** 按[Apple XNU锁实现](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/kern/kern_lockf.c)核对flock/fcntl同inode冲突路径，Darwin改为目录租约候选；Linux保留原DB租约。恢复复制前后身份、授权和关闭顺序不变。独立进程红例lease-red为1失败，修正后lease-green为1通过；Linux可执行两种策略，Darwin测试只启用兼容目录策略。Linux回归不能证明Darwin已修好。
- **真实PDF：** 初轮literature-joint-01为137过/28skip，缺固定PDFium不算解析验收。外部隔离pdfium-python显式安装5.14.0，joint-02为161过/4资产skip；最终joint-03六文件为189过/5skip、26.42s，文献PDF/store恰92唯一、零非通过。4项skip是未配置E5/Qwen真实资产，另一项旧离屏子进程SIG11。
- **测试污染：** CLI测试先于HDF5结果测试时真实复现1失败/27过/1skip；旧缓存注册表仍持早期模块函数。测试使用独立无第三方入口注册表并定位当前模块后28过/1skip；产品插件规则未放宽。红/绿XML与日志均保留。
- **原生CPU/构建：** 当前文献C++24/24、14.392s，literature-cpp-01.xml；stk-literature-app-tests与stk-reports-native-window两个目标build退出0，native-build-01.log。final-inputs-before.json与final-verification.json绑定21个记录输入，最终前后SHA一致；不声称覆盖全部构建依赖。
- **Windows原生候选：** 前失败artifact的windows-html-video-result.json显示直接移动使report宽401→359，泵队列时捕获期真实hover又使宽变511。改夹具在泵队列前完成本地MouseUp，原OS事件仍留正常路由；尺寸、捕获释放、像素和20轮门不降。Linux仅编译此夹具，未做Windows原生通过声明。
- **Mac原生剩余：** 两个旧视频artifact仅看到WKWebView→remote两节点、无slider；四次查找总计仅几十毫秒。未把诊断当修复，没有关闭AX、像素或20轮门。文献创建C++诊断只添状态/error_code。
- **提交检查：** 暂存源码10.44KB由gitleaks8.30.1按.gitleaks.toml扫描零发现；扫描归档SHA256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`已核。四状态文档只前置本次记录，原WIP另证保留；认知托管资产与产品分开审计。

同761a9e37的[Runtime42455805124](https://github.com/sijintech/stk/actions/runs/42455805124)已completed/failure（Linux三版本、Windows两版本失败；文献三版本、peer-macos、Flower等成功）；不能称全绿。
[Desktop42455805095](https://github.com/sijintech/stk/actions/runs/42455805095)最后查询仍in_progress，Windows CPU、Linux包及fresh24.04冒烟成功；须整轮终态才允许下一push。Docs/Secret成功。
PR53/54头仍c9f13994/2dd3e4ee，没有新增修改；旧重复实现/历史交接未因持续目标自动合并。
Claude独立claude/support/c975f58d正整理CL-S2C-PLAN-05，只有外部方案，未当实现或发布契约。本批没有新产品UI交付，无固定布局实际点击数据；真实MuPRO、目标OS及科学有效性仍未验证。

## 2026-11-08 UTC：HDF5 自动发现/收集交付（本地待推送）

源码：main `89e40c89f946556e35ee954eb9a3fbf9c1a0dbfe`，19文件；Claude读取/发现模块后续交付 `c975f58da1290317ecbe9eff510ca53b82ab52b3` 只选择两新文件集成。
证据根：`/home/mnemora/.local/state/stk-validation/mupro-hdf5-discovery-20261108-03/root/`；Claude原始证据在同级 `claude/`。

| 实际检查 | 结果与边界 |
|---|---|
| `joint-final-02.xml` / `.json` | 21文件419通过/5跳过，268.34s；34记录输入SHA前后相同，退出0 |
| `joint-final-01.xml` | 修正前414通过/5跳过，241.95s；不覆盖后续兼容修正 |
| `collection-consistency-red.xml` | 2个先失败反例，确认跨步dtype/分量变化曾被错误收集 |
| `collection-consistency-final.xml` | 修正后18通过，84.85s，记录输入稳定 |
| `dat-compatibility-red.xml` | 3个先失败反例：坏HDF5阻断DAT、容器预算阻断图索引、替换插件误收公共新参数/格式政策 |
| `dat-compatibility-final-01.xml` | 修正后52通过，2.24s；最终21文件联合02再次覆盖 |
| `ci-regressions-01.xml` | 108通过/1 Windows专属跳过，1.75s；目标Windows必须再由CI验证 |
| `cli-02/verification.json` | 真实CLI新进程自动索引及NPY输出，180个float32原值完全相等，selector与源SHA一致；无求解完成声明 |
| `gitleaks-code-01.json` | 暂存按 `.gitleaks.toml` 扫描56.97KB，零发现 |

五个最终skip分别为Windows HANDLE原生查询、未启用性能基准、已有离屏子进程SIG11，以及真实MuPRO项目/批次各一项缺资产。
所有测试清空 `STK_TOKEN_PLAN_API_KEY` 并移除 `STK_TOKEN_PLAN_MODEL`；没有运行真实MuPRO或收费模型、没有新UI交付或点击计数。
当前收集仍要求旧DAT完整核验，并严格检查附加HDF5的容器字节、网格与跨步布局；元数据可读不证明值完成或科学正确。
文件上限仍1GiB、数组/chunk估算另256MiB，临时盘可能tmpfs，命中仍全量哈希；运行中本地容器变化可拒绝，未新增SWMR/活跃Runtime产物读取。

远端代码头 `f152e67a31c6fc742408644e9d9668971cabb060`：
Runtime [42451045163](https://github.com/sijintech/stk/actions/runs/42451045163) completed/failure，13 job中5失败、8成功。
Linux3.11/3.14各1 fail/5542 pass/153 skip/4 deselected，3.12为1 fail/5559 pass/136 skip/4 deselected；失败均旧节点清单。
Windows3.11为2 fail/4951 pass/254 skip/346 deselected；3.12的三失败为节点清单、ctime创建时间前提和msvcrt被动导入前提。精确摘要与原失败在 `f152-ci-failures.json`。
Docs42451045187及Secret42451045182 success；Desktop [42451045164](https://github.com/sijintech/stk/actions/runs/42451045164) 已于06:17:18Z completed/failure。
6个job中Linux包、全新24.04包冒烟、Linux GL/Vulkan和Windows CPU成功；macOS CPU/文献及原生文档、Windows原生文档失败。精确终态保留在 `f152-desktop-terminal.json`。
前整个Desktop等待门已满足，失败仍待修复。本节记录时新源码尚未push/触发CI，随后推送及新CI见本批closure；本地通过不代表远端或目标OS已过。

本轮旧PR53/54头未变，未盲合历史分支；53与主线已有传输重试实现重叠，54为旧大写交接，均未作为当前功能集成。
原四文档正文WIP保留；认知Verify/Check/Guide、记录提交和最终Git/CI实况另记本批 `closure.json`。

## 2026-11-08 UTC：MuPRO HDF5 显式源的回归和真实CLI

- 源码：main `56f51af70d576837426f63c12694941b0ea7cfcd`，16文件；Claude读取器来源`73abd757fcbaa29fbeb72993e6df930ea581aaa3`，仅选择其两项分配文件，root新增来源/图接入。
- 全部测试KEY为空、MODEL未设置，无收费模型或求解器请求。匿名文件修正后联合`root-hdf5-joint-04.xml`：305 pass/3 skip，68.13s；前增量局部68 pass，不用于覆盖后改。
- 三skip：Windows HANDLE专属（Linux未跑）；128³性能例需STK_PERF=1；旧离屏probe子进程signal11。没有用skip或软件渲染故障声称目标平台通过。
- 联合02的2 fail/298 pass/3 skip保留：原agent不支持selector字段、轻量catalog旧5节点断言；已改SourceRef和6节点。图基础前两轮模式样本失败亦保留，03为78 pass。
- 实际CLI：`root-hdf5-cli-01/`，`suan graph run`退出0，读取`/t00001000/Polar`并导出NPY；`verification.json`核180值全部相等、shape[5,4,3,3]、float32及来源摘要。合成数据非MuPRO求解结果。
- 新源回归覆盖裁采/时间/单位、容器内selector隔离与磁盘缓存、规划后同大小恢复mtime改写拒绝、无本地路径的FileSource，以及摘要不符/坏格式/取消/超限的私有副本清理。
- 暂存gitleaks8.30.1按`.gitleaks.toml`扫描约74.83KB、零发现（`gitleaks-root-hdf5-code-01.json`）。旧四文档WIP不连带暂存。
- push门：再次GET Desktop42442318655，6f4de650/completed/failure、04:24:48Z；前整轮已结束。6dd627e4的Runtime42447661806、Docs42447661827和Secret42447661807均success；新代码尚未触发CI。
- 限制：读取文件≤1GiB、选择数组和chunk估算≤256MiB（还受评价内存限额）；非RSS保证。真实程序/许可/算例未就绪，无新产品UI或点击证据；自动run发现/收集、S2c与D1仍待续接。
- 证据根：`/home/mnemora/.local/state/stk-validation/worktree-coordination-20261107-01/`；最终审查、AOCI/推送/新CI结果由该目录本批closure绑定。

补充修正 main `3579aea16ff9249fdb688012575576f1aeea8fb4`：交叉审查确认强杀worker遗留命名副本，已改匿名/关闭即删除的临时文件，共享同一读取核心；真实子进程强杀清理测试通过，CLI无缓存复验180值一致。

## 2026-11-08 UTC：试点计划交付与前置 CI 终态

文档提交 `f6a75f846d2643e993af192cfb867ca19a9d3fb2`（9文件），73个相对链接/锚点、围栏和暂存空白检查通过；gitleaks8.30.1扫描56.67KB零发现。
四状态文档只暂存本轮前缀，原WIP正文精确保留；AOCI配置未由本轮修改，认知资产仍留工作树，不把工作树对齐称为提交索引已发布。
产品源码仍为37d26464；旧MuPRO/工作流/传输回归74pass/1真实MuFerro资产skip，预检退出1，细项和限制见下节。

Claude HDF5候选 `760b7ae1` 尚未集成。root对其源码SHA `7609f159d31598b1fdc5f8a6e0382dd3d7613faa9208381d5fe11f0a22958b18` 独立构造真实h5py文件，
复现尾换行selector被接受、读取期间原位改写同大小数据并恢复mtime后仍交付两项问题；要求fullmatch与同stat API前后ctime检查及反例。
`hdf5-root-review-before.json` 保存结果，不借Claude初稿81项通过覆盖这些未测边界；修正后需重新验收。

前置 [Desktop 42442318655](https://github.com/sijintech/stk/actions/runs/42442318655) 在04:24:48Z completed/failure，绑定远端6f4de650：
Linux三job/Windows CPU成功；Mac CPU1488中9个文献控制器失败、原生6中视频2例失败；Windows原生6中HTML视频1例失败，诊断为真实分隔条拖动未同时改变报告/Viewer并释放捕获。
前整轮等待门现已满足，失败保留；Runtime/Docs/Secret成功。Mac帧artifact两次下载分别TLS/EOF失败，未采用不完整zip作证据；API日志已取得。

本批九项AOCI应用后1197条/remaining0，Verify/Check/Guide均退出0、治理aligned、Check ok、Guide complete/none（`aoci-pilot/`）。
本节终态增量的最终治理与提交/推送状态以 `pilot-doc-delivery.json` 及后续closure为准，不重新传全索引或把旧receipt冒充当前认知。
上述证据均在 `~/.local/state/stk-validation/worktree-coordination-20261107-01/`。未执行收费模型、真实MuPRO、目标OS本地复验或UI点击验收。

## 2026-11-07：独立 worktree 已建立与试点决定（当前）

协作规则提交 `37d26464`（main 本地，7 文件），仅新增本次协作记录，四份状态文档的原有 WIP 未连带提交。
13 个相对链接、暂存空白检查和最终 gitleaks 扫描15.91KB零发现；原四文档正文与本轮前 preimage 精确匹配。
Claude 独立 worktree `/home/mnemora/xcheng/sijin/stk-claude`、分支 `claude/support`，基线同规则提交，后台任务89bf764a已启动。
检测到旧交互 Claude 会话仍指向 root，未终止其进程或覆盖现场；新增任务只在隔离树工作。

AOCI 两批分别16/15项应用成功、最终1195条/remaining0；顺序 Verify/Check/Guide 均退出0，治理aligned、Check ok、Guide complete=true/next_action=none。
保留非阻塞E档提示；证据在 `~/.local/state/stk-validation/worktree-coordination-20261107-01/aoci/`。
本节和新试点决定是该证明之后的新字节，最终治理需覆盖此增量，不能借旧aligned声称当前完整认知可靠。

所有者已选 MuPRO/MuFerro、插件定义格式/MuPRO HDF5、扩展 S2c prepare/run 开发；软件/许可、真实HDF5产物、智能体权限实现和科研结果尚未新验收。
Claude 文档头 `9590d21b` 已按唯一文档路径选择性提取，root 修正未核实的 SDK/HDF5 版本、AOCI 配置推断及回环/外网表述；
D1 两部署、权限及完整迁移验收仍未执行。CL-MUPRO-H5-01 的两个新文件正在独立树开发，尚未作为产品支持采用。

本轮新增实际检查（来源产品代码 `37d26464`，测试期间 main 未改产品代码）：

- `python -m suan.mupro check --json` 退出1：当前 SDK前缀/程序失败，MPI与许可目录未配置，动态库无程序可查。
  未 source 环境脚本、读许可内容或运行求解器；仅查当前配置/PATH及两个已知安装根的名字，不是穷尽搜索。
- `test_mupro.py`、`test_integration_mupro.py`、`test_bridge_workflow_muferro.py`、`test_desktop_transfer_lifecycle.py`：
  74 passed / 1 skipped，82.23s；skip 为未设置 `STK_TEST_MUPRO_PREFIX` 的真实 muFerro 例，不计通过。
  其余使用假求解器及真实本机 Runtime/Hub 链，不证明真实 MuPRO 或科学结论。
- 现有原生 Linux `LiteratureBridge.ActualCorpusKeepsCallerUuidAndPassivelyReopensWithoutReissue` 单例通过（1240ms），
  不能替代 macOS 当前失败。上述命令均清空 KEY、unset MODEL，无收费产品模型请求。

证据：`~/.local/state/stk-validation/worktree-coordination-20261107-01/mupro-preflight-01/report.json`、`mupro-regression-01.xml`。
本轮压缩后按合同新传1195条/45块、约174896估算tokens，交付确认、Challenge10/10、覆盖100%、框架自评87%；
治理仍dirty/stale，最终增量维护另行记录，不借认知验证代当前源码和平台验收。

实时同 `6f4de650` Desktop `42442318655` 整轮仍 in_progress：Linux三job、Windows CPU成功；
macOS CPU1488中9个文献控制器例失败，原生6中两个视频例失败（own-WKWebView时间滑条定位），Windows原生job仍运行。
Runtime/Docs/Secret成功；未提前push下一代码头。PR53旧传输实现与main已有修复重复且有冲突，PR54旧大写HANDOFF与当前交接重复，均未盲合。
本轮没有新的UI点击验收，不记录虚构点击数。

## 2026-11-07：root / Claude worktree 协作设置（当前）

本轮范围是协作规则、隔离 worktree 和交接任务，不是产品 UI/科研功能交付。
起始 `main` 为 `5670f565be32b6be85d187ba2fb2baa22d272341`；原六项未提交 WIP 与空暂存已核对，
六份公开文档 preimage 保存在 `~/.local/state/stk-validation/worktree-coordination-20261107-01/before/`。
仅对四状态文档追加当前记录，历史正文保留；规则详见 [协作约定](planning/agent-collaboration.md)。

| 核验 | 本轮事实与边界 |
|---|---|
| 远端与前置 CI | 已核远端 main 为 6f4de650；该头 Runtime [42442318483](https://github.com/sijintech/stk/actions/runs/42442318483)、Docs [42442318504](https://github.com/sijintech/stk/actions/runs/42442318504)、Secret [42442318534](https://github.com/sijintech/stk/actions/runs/42442318534) completed/success；Desktop [42442318655](https://github.com/sijintech/stk/actions/runs/42442318655) in_progress。未以单 job 或旧 failure 代替整个新 run 终态 |
| 角色与路径 | root 在 stk/main；Claude 在 stk-claude/claude/support，仅接受有基线/路径/验收的文档和模块任务；root 统一集成与推送 |
| 功能与点击 | 未运行新产品、模型、许可软件、GPU、原生窗口或点击验收；CL-D1-01 仅 ready，不标实施完成 |
| AOCI 认知 | 本轮沿用同 Run 的完整 1181 条/44 块、Challenge 10/10、覆盖率 100%、框架掌握度自评 88%；已加载且严格验证通过，治理仍待最终稳定态维护，不声称当前系统全貌可靠 |

协作规则提交及隔离结果以本批外部 closure 和实际 Git 为准；不连带提交原四文档 WIP。
本轮文档检查：13 个相对链接存在，diff 空白检查通过；gitleaks 8.30.1 按 `.gitleaks.toml` 扫描暂存增量零发现。
未运行产品测试，不用旧产品测试计作本轮验证。

所有者另已设持续开发目标为 active：root 合理分配 Claude 工作，并审查、验证及合并当前计划相关 PR；
所有者数日后回复问题，期间继续不依赖待决的工作，不把未回复视为授权选择。

## 2026-11-06 UTC：启动会与多仓规划材料验收（当前，仅文档）

材料提交 `325fe57dc955b4e9a69370e60d03f39ad0a6bb7b`；入口为[总体框架](design/platform-framework.md)、
[开发/周会计划](planning/platform-roadmap.md)、[分仓方案](planning/repository-strategy.md)、
[讲稿](planning/research-kickoff.md)与[HTML 投屏稿](planning/research-kickoff.html)。

| 检查 | 本轮实测与边界 |
|---|---|
| 内容/链接 | 60 个相对目标存在，5 个 Markdown 章节锚点可解析；围栏与暂存 diff 空白检查通过。独立审阅阶段、仓职责、人员假设、旧回执/科学边界无剩余实质问题 |
| 浏览器呈现 | headless Chrome 实际导出 10 页 PDF；DOM 首轮检测 10 页、无整页 scroll overflow；最终只细化仓库候选名，最终仓库页另作实物检查。未声称已测全部交互按钮 |
| PDF | 最终 665750 字节，10 页均有可提取文字及正确页码，仓库页含 stk-platform；实际查看架构/仓库/排期页。来源/摘要见 presentation-final.json，不作为 STK 原生 UI/点击验收 |
| 暂存密钥扫描 | gitleaks 8.30.1 / .gitleaks.toml，材料七文件约 70.13 KB，零发现；交接追记另在其提交前扫描 |
| 产品/科研测试 | 未运行产品回归、许可软件/GPU/节点/科学质量测试，无模型请求。12 周为条件性有限试点，新用例仍未执行 |
| Git/CI | 远端 main 350534d；[Desktop 41639295121](https://github.com/sijintech/stk/actions/runs/41639295121) completed/failure；按本地前代码头 535b0d63 查询 runs 为 0。本轮仅本地文档提交，无 push 或新 CI |
| AOCI/既有改动 | 延续所有者批准的本设计直接证据路径，加载与维护暂缓；config/baseline 字节摘要不变，四文档原文与其既有未提交改动保留 |
| 外部动作 | 未创建/重命名仓库、改访问权限、发送会议消息、预订会议或部署。新仓名称与时间/人员均未当作已确认事实 |

本轮证据根：`/home/mnemora/.local/state/stk-validation/stk-kickoff-plan-20261106/`，包括 preimages、
content-validation.json、presentation-final.json、gitleaks-materials.json 和 STK-Synthrix-kickoff.pdf。
HTML 可直接打开投屏或通过打印保存 PDF，不依赖外部脚本/字体下载。讲稿约 15 分钟，周会 60 分钟均为可调整建议。
以下为此前设计与历史验收，不能用来填本轮新功能的通过状态。

## 2026-11-06 UTC：统一后端设计交付（仅文档，当前）

设计提交 `f541393b31b9f32b1f73bc738998075bc93e6dbd`，main 本地。三项文档为
[架构](design/shared-backend-architecture.md)、[协议](design/distributed-task-data-protocol.md)、
[跨端验收](design/distributed-workbench-acceptance.md)；共同后端采用同一源码/模型/应用服务/状态机，部署适配有明确边界。

| 项目 | 本轮实际结果与限制 |
|---|---|
| 源码核对 | STK 535b0d63；Synthrix 网页 a15ab6b。当前网页无历史 90d7c4a 的可选 STK Hub 接线，不沿旧分支证据宣称当前集成 |
| 文档检查 | 五份设计、87 个相对链接目标均存在，围栏配对；最终暂存 diff 空白检查通过。未验证网页渲染或外部链接持续可用性 |
| 独立审阅 | 同后端实现、D0–D5、离线授权、旧回执缺证据与回滚边界交叉审查，无剩余阻塞问题 |
| 密钥扫描 | gitleaks 8.30.1 / .gitleaks.toml，最终五文件暂存约 63.12 KB、零发现；交接追记另在提交前扫描 |
| 新产品/界面验收 | 未运行测试、构建、模型、服务或 UI；固定起始布局、点击预算及实际值栏已在验收设计分开，实际点击全部未执行 |
| 真实计算 | 新许可软件、GPU、跨平台/网络与科学质量均未验证；stub 不抵扣这些门 |
| Git / CI | 远端 main 350534d；Desktop [41639295121](https://github.com/sijintech/stk/actions/runs/41639295121) completed/failure，Runtime [41639295206](https://github.com/sijintech/stk/actions/runs/41639295206) completed/failure，Docs/Secret success。本地前代码头 535b0d63 尚未推送，按 SHA 查询无 workflow runs；本轮不 push、无新 CI |
| AOCI | 所有者明确批准本轮直接证据设计并暂缓完整加载/维护；此前宿主截断且 chunk_tokens 为合法最小 4000。本轮未改其资产，不声明当前索引对齐 |
| 既有改动 | 六项既有 WIP 已保留；四文档原内容保持，仅追加本轮记录；AOCI config/baseline 摘要与起始快照一致 |

证据目录 `/home/mnemora/.local/state/stk-validation/stk-unified-backend-design-20261106/`：
`before.json`/文档 preimages、`ci-observation.json`、`design-check.json`、`gitleaks-design-final.json`；
本轮交付收口另保存当前文档摘要与既有改动保留验证。D1–D5 所列实测为后续任务，不预填通过。
以下历史记录和旧“当前”标记不覆盖本节。

日期：2026-09-09。状态：工程预发布，尚未完成真实集群和独立桌面安装器验收。
各历史批次的待办及 CI 状态保留当时快照；当前状态以最新首节和 `handoff.md` 为准。

## 2026-11-03：持续目标恢复与整合起点（当前）

所有者恢复开发，并确定 [STK 主体的分布式科研工作台](design/distributed-research-workbench.md) 方向。
本节记录新批次实际结果，下面各历史全量和包证据保留其原来源范围。

| 检查 | 本次真实结果与范围 |
|---|---|
| 恢复前 Git | main/HEAD/实际远端均 `3ef4b2716d42304d708062f9715edae0afb5874f`；91 WIP（33 tracked/58 untracked），暂存空 |
| 既有进程 | 恢复检查未发现目标 pytest/ctest/ninja/旧文献验证进程；不据此声称整台共享主机空闲 |
| 源保护 | 原91路径状态/大小/SHA和旧四状态文档保存于 `/home/mnemora/.local/state/stk-validation/resume-platform-20261103T110725Z` |
| 前头 CI 只读复核 | 同3ef的 Desktop41178119889 completed/failure；Runtime41178119790、Docs41178119912、Secret41178119838 completed/success；不覆盖新WIP |
| 新方向 | 已更新设计与计划，尚不等于跨平台节点、Computer Use、Synthrix集成或完整插件系统已实现 |
| profile当前真实联合 | `OWNER_NEW/encoder-profiles-review-20261103-01/closure.json`：69/69、零fail/error/skip，501.730s，14输入稳定；真实E5/Qwen/PDFium，不代科学质量/其他OS |
| 服务当前三父矩阵 | `OWNER_NEW/literature-service-review-20261103T110738Z/matrix-01/closure.json`：3.11/3.12/3.14各26/26、零fail/error/skip，80.504/79.296/82.287s，20输入稳定；解析/编码子进程均固定3.12 |
| 当前交付状态 | 文献Bridge、S4、wheel及整合02原生/Python均已终态，范围见下表；最终sdist、治理、提交/新头CI仍待完成 |

| 后续真实结果 | 证据和边界 |
|---|---|
| Hub CLI | 9文件187pass/1 warning、58.91s，KEY空/MODEL unset；仅工具session62311控制台与diffcheck，未保存独立XML/前后source proof，不伪造此证明 |
| 文献Bridge | `OWNER_NEW/literature-bridge-contract-20261103-01/final-closure.json`：54/54、零skip、7.749s、27输入稳定。46合同/隔离+6既有+2真实缓存续接；原fresh推理函数明确deselected，初45/46失败保留；实际10 DTO重验/PNG geometry/撤权通过 |
| 独立heldout | `OWNER_NEW/retrieval-quality-independent-01/heldout-release-20261103-01/closure.json`：41输入稳定、各角色一次。Qwen同语120/120、跨语119/120（70/71与49/49）过原门；E5 reference同语120/120、跨语24/120；一般段落非官方QA/科学PDF/RAG，原失败不变 |
| S6最终Schema | `OWNER_NEW/reproduction-s6-final-20261103T112422Z/matrix-final-02/closure.json`：三Python各430/430、零skip、334输入稳定；101.58/102.79/105.69s。保留旧415、加15 I/O反例；绑定后续file_store修复前SHA |
| S4接收撤权竞态 | `OWNER_NEW/peer-accept-revoke-review-20261103-01/closure.json`：两窗口2红→绿；12文件454pass/8skip、28来源稳定，再补6个真实helper案例、19来源稳定，联合唯一460pass/2个Windows-only skip。含240MiB/4098块传输；不代Mac/Windows/WAN或完整双GUI。 |
| S4独立补修矩阵 | `OWNER_NEW/peer-accept-independent-20261103T114715Z/matrix-02/closure.json`：3.11/3.12/3.14各10/10、零非通过、220输入稳定，1.665/1.506/1.739s。窄补修反例，不替12文件套件、helper/平台或第三轮S6全矩阵。 |
| 整合01原生失败保留 | `RESUME_EVIDENCE/integration-01/native/summary.json`：2074pass/1fail，build885.384s、ctest510.207s、670来源稳定。失败为App.EditorKeysExistInEveryCatalog旧计数；Root仅修test_app.cc的19→20并补Peers存在断言。 |
| 整合01 Python失败保留 | `RESUME_EVIDENCE/integration-01/python/summary.json`：5411pass/148skip/2fail，960.894s；973来源中file_store.py及其测试漂移。失败为hello人工buffer过窄与生成节点文档过期；测试buffer8→16KiB且保oversized/EOF断言，重新生成suan/skills/stk-visualize/reference/nodes.md补reproduction，定向2/2通过。 |
| 整合02原生 | `RESUME_EVIDENCE/integration-02/native/summary.json`：2075/2075、零fail/error/skip，build19.251s、ctest490.527s、1291来源稳定，实际已安装Linux helper；目标OS/科学质量另证。 |
| 整合02 Python | `RESUME_EVIDENCE/integration-02/python/summary.json`及stdout.log：5489pass/74skip/4deselected/1warning，5563案例、973来源稳定、changed_sources=[]，KEY空/MODEL unset；pytest1207.90s、wrapper1211.584s、exit0。28个显式encoder资产/解释器依赖、13 Flower、15旧离屏SIG11、9 Windows、3 MuPRO、2可选MCP、2可选adversarial native peer、2 perf跳过；4个按选择排除。69项真实E5/Qwen/PDFium是上方独立证明，不宣称在此全量内执行。 |
| 当前wheel隔离安装 | `OWNER_NEW/package-wheel-20261103-02/closure.json`：Linux Python3.12新隔离环境299/299、零skip、94.198s；四个真实模型/PDF案例明确deselected，715输入稳定、704产品成员逐字节匹配，31次被launcher拦截的子进程cwd/PYTHONPATH均无源码树路径。wheel SHA fbd6625a71e287a5ae83657b80ea583230841a8abc7a078e347e1db7b440c8a2；最终sdist未完成，不代目标OS/干净机/原生UI/真实科学。 |
| 当前Schema原生探针 | Root另编译运行C++64个文献参数/实际DTO正反例，embedded document与当前源Schema相等、exit0；`RESUME_EVIDENCE/integration-01/literature-native-probe-observation.json`保留工具观察和事后哈希，未伪造前后来源快照、未重复运行，不代原生文献UI。 |

以上 `RESUME_EVIDENCE=/home/mnemora/.local/state/stk-validation/resume-platform-20261103T110725Z`；`OWNER_NEW`根见handoff。
本批没有新增原生文献UI/点击验收；原40QA科学PDF全局heldout12/18、cross0/6失败保持，不能以一般XQuAD或软件测试通过替代。

AOCI最新Root完整24/24交付confirmed、Challenge9/10 pass，1144条、estimated165707 tokens。
此前11-03压缩链21/24后在第22块snapshot_unavailable中止、未确认/未Attest，保留失败历史，不再代表最新完整交付状态。
Root逐条审查29条Observed事实并核当前SHA/精确pending set，`OWNER_NEW/observed-review-20261103-01/acknowledge-29.json` status applied、txn40bc59963d92d5d733245239；
这是Observed基线确认，不是Entry语义维护。治理仍Dirty/Stale，不声称全量aligned或当前完整系统认知可靠；最终维护待四文档冻结后执行。

## 2026-11-02 21:38 UTC：当前转交核验（历史）

按所有者要求冻结并写[handoff.md](../handoff.md#当前接手顺序)。main/HEAD/local origin/main/实际远端均3ef；91份WIP（33 tracked/58 untracked），暂存空，无本次commit/push/包/新头CI。交接只改四状态文档，87份其他WIP前后SHA核对及文档/治理检查见 `OWNER_NEW/handoff-20261102T2138Z/closure.json`，根见handoff。本次未新增产品测试/构建，以下为已结束工作的证据及明确限制。

| 证据，相对OWNER_NEW | 真实结果和适用范围 |
|---|---|
| literature-service-01/matrix-01/closure.json | 三父Python各21/21、零skip，19输入稳定；早于corpora.info和双profile适配。 |
| literature-service-01/service-09.xml；worker-regression-01.xml | 22/22与38/38、零skip；当前双profile/bundle/显式timeout版本预计25项，**尚未运行**，未接Bridge/native。 |
| reproduction-workflow-02/matrix-02/closure.json | 三Python各415/415零skip、252输入稳定；早于最后FIFO/I/O修复。 |
| reproduction-workflow-02/io-final-01/closure.json | 三Python各41/41零skip，70.154/72.274/72.833s；source_stable=false，唯一漂移literature.py，不能称最终稳定联合证明。 |
| retrieval-quality-independent-01/e5-tune-01/summary.json | 公开派生检索tune同语119/120、跨语12/120；240段/242窗口，corpus50.055s、peakRSS1,357,760KiB，完整/源稳定。 |
| retrieval-quality-independent-01/qwen-tune-01/summary.json | 同语119/120、跨语115/120；corpus606.868s、peakRSS3,894,632KiB，完整/源稳定，tune family选择三门通过；非heldout/官方QA/PDF/科学验收。 |
| retrieval-quality-independent-01/qwen-dynamic-int8-01/run-01/summary.json | 同语115/120、跨语101/120，corpus608.880s、peakRSS3,899,116KiB；质量非劣/半耗时/RSS门失败，optional_profile_gate=false，不采用。run-closure exit0/未超时/owned child已回收，exit0仅表示执行完整。 |
| 当前源码与首次质量失败 | 新encoder_profiles/worker/Dense/Collection及专用测试已保存未测，旧43项不能覆盖。原40QA全局heldout12/18、cross0/6失败保留；独立heldout未用于推理/评分。 |
| 本次官方只读GET | 同3ef/attempt1 Desktop41178119889 completed/failure，updated2026-10-31T07:34:01Z；Runtime41178119790 completed/success，07:03:28Z。均不覆盖WIP。 |

Root本次AOCI1144条/24块完整交付确认、Challenge10/10；model usable/strict verified为true，治理对齐/当前完整认知可靠为false。最终Maintain/Verify/Check/Guide机器结果见交接closure，Observed/Entry维护未闭合。无新UI点击验收、目标OS/干净机/wheel/真实MuPRO或收费模型结果；八路线、三待决和PET后置保持。

## 2026-11-02：恢复持续目标，推进服务和复现闭环（历史，本次转交前）

所有者已恢复按当前计划完成所有开发，上一轮handoff停止点为历史。main/HEAD/远端仍3ef、暂存空。S6新增四文件，三Python各415/415零skip、252输入稳定（`OWNER_NEW/reproduction-workflow-02/matrix-02/closure.json`）；Root随后复现FIFO读取阻塞并要求增量修复，后改代码不能借旧415结论。LiteratureService真实21项与worker38项已跑，正修独立审查的历史配置/引用rank和身份/数值类型/manifest预算问题并准备三父Python验证，尚未接Bridge/native。

原40QA全局12/18、cross0/6的质量失败保留；独立混合240段实验已冻结文章级tune/heldout，E5开发同语言119/120、cross12/120，候选本地模型正在运行，heldout尚未编码或评分。完整实验和限定在 `OWNER_NEW/retrieval-quality-independent-01/`；无产品模型/endpoint/网络设置或旧QA/语料改动。当前无新commit/push/包/新头CI，AOCI仍Dirty/Stale；稳定交付再维护。完整八项路线、三待决及PET后置保持，接手入口见[handoff](../handoff.md)。

## 2026-11-02：本轮转交核验（历史，本轮恢复前）

按所有者要求停止开发，当前入口 [handoff.md](../handoff.md#当前接手顺序)。main/HEAD/local origin/main/实际远端均3ef；83 WIP文件（33tracked/50untracked），暂存空，无本次commit/push/新包/新头CI。本次仅收集已完成结果并写交接文档，没有新增产品测试或构建。以下证据相对 `OWNER_NEW=/home/mnemora/.local/state/stk-validation/s4-owner-20261102`。

| 证据 | 已核实的终态及边界 |
|---|---|
| `resolve-many-01/closure.json` | PDF/Store三Python各92/92零skip/fail/error、9输入稳定，16.71/16.60/17.57s；CI gate92唯一/68必跑，3实际XML和3Python接受、76负例拒绝。本机验证，不是远端新CI。 |
| `literature-43-01/summary.json` | 43/43真实固定本地E5，零skip/fail/error、410.435s、14输入稳定，覆盖四fence/深引用和两批次集成增量。 |
| `literature-resolution-benchmark-02/closure.json` | 1051完整结果/顺序/几何canonical等价，22输入稳定；single31.489s/1051hash/248018223bytes，batch3.248s/34调用/36hash/8502896bytes。仅解析循环，非端到端或RSS证明。 |
| `retrieval-evaluation-01/run-01/summary.json` | 40QA/2build/80查询、810.474s、执行完整且源稳定；**主质量门false**。全局heldout hit@5=12/18、EN6/6、CN6/6、cross0/6；MRR10=.625，macro citationRecall5=.463889，完整证据包@5=4/18、@10=7/18，不可答nonempty6/6不等于拒答准确率。保留失败，不修改原标签/门槛或按曝光heldout调参。 |
| `reproduction-comparison-01/final-02/closure.json` | 纯核心三Python各57/57零skip、源稳定；通用软件比较，不是科学或输入真实性证明。 |
| `reproduction-graph-01/matrix-02/closure.json` | 三Python各195pass/1skip、25输入稳定；新增97项全部零skip。旧CLI离屏probe：311/314缺VTK，312子进程SIG11；不能冒充全组零skip或平台通过。 |
| `reproduction-workflow-01/preliminary-02.xml` | 外部草稿Python3.12实际15/15零skip，27.101s；真实worker/PNG/Report1/reopen/tamper。无最终source closure/311/314/wheel；eager matplotlib及prepare丢回复恢复两缺口待修，四目标repo文件均未写。制造数据不证明论文/MuPRO/敏感性。 |
| 本轮官方GET | 同3ef/attempt1 Desktop41178119889 completed/failure，updated2026-10-31T07:34:01Z；Runtime41178119790 completed/success，updated07:03:28Z。前Desktop终态不等于P4通过，不覆盖WIP。 |

LiteratureService两草稿及WorkerProcess env patch确认存在但未测，trusted encoder_python、原DB UUID/current approval发布、DTO/预算/生命周期及专用测试/spec待补，未接Bridge或native。旧Peer原生19/19与13/7点击、Bridge123/122/122及全量4716/2056/安装585只保各自旧源/平台范围，后改不能借用；本次没有新UI点击结果。

Root本次完整AOCI24/24、1144条、交付确认、Challenge10/10，但governance_aligned/current_system_cognition_reliable均false。最终四文档、79业务WIP一致性、文档diff扫描与Maintain/Verify/Check/Guide的真实结果位于 `OWNER_NEW/handoff-20261102T2022Z/closure.json`；治理未闭合，接手按实时Guide处理，不能用Observed确认代替Entry维护。

## 2026-11-02：通用开发续接验证（历史，本次转交前）

目标恢复；10-31停止交接为历史。以下证据位于 `/home/mnemora/.local/state/stk-validation/s4-owner-20261102`，各自限定源绑定，尚无新提交/push/包/远端新头CI。

| 证据 | 实际结果和界限 |
|---|---|
| `literature-ci-01/closure.json` | 文献gate72唯一/48必跑，三实际XML和三Python执行通过，56类负例拒绝，YAML/Bash/Python及diffcheck通过；不是新增产品测试或远端CI。 |
| `literature-37-01/summary.json` | Dense/Collection37/37真实固定E5，零skip/fail/error，291.63秒，14输入稳定；早于之后4条Dense守卫回归及修复。 |
| `dense-fences-red-01.xml`、`dense-fences-red-02.xml` | 直接search/hybrid encode后切换模型均未拒绝；另lexical阶段切换模型未拒绝；深20k base在真实保留citation上抛RecursionError。修复为查询/融合原选择fence及canonicalization前封闭base校验；41项最终矩阵正在运行，不能借旧37项证明新源。 |
| `corpora-preparation-01/closure.json` | 4PDF/两新格式库、23页1051段；原version/extraction及完整index回执一致，91条QA引用span/几何/字节/当前权限通过，16输入稳定，9.59秒。无embedding/ranking/质量/科学或统一发表结论；英文不完整/CN字形噪声诊断保留。 |

S6纯数值比较核心及新契约仍在开发，实际验证另记；原报告/1、/2和graph发布目录未变。最终源码稳定后再整合包/平台/暂存扫描与AOCI治理，不维护中间态，当前AOCI仍Dirty/Stale。完整路线和三待决见[handoff](../handoff.md)。

## 2026-10-31 18:30 UTC：本轮转交核验（历史）

所有者要求保存待办交下一Agent，本轮仅文档/状态收尾，未运行新产品测试/构建/embedding/ranking。main/HEAD/实际远端仍3ef，69文件WIP（27tracked/42untracked）、暂存为空，无新提交/push/包/新头CI。最新入口 [handoff.md](../handoff.md#当前接手顺序) 覆盖旧“继续开发”指令。

| 现有证据（相对OWNER_EVIDENCE） | 本轮收集核对的终态与限制 |
|---|---|
| `literature-store-review-01/store2-matrix-02/{311,312,314}/summary.json` | 各72/72，零skip/fail/error，12.19/12.04/12.94秒，10输入稳定；当前Store2f2db946…/test88e1c392…与记录一致。旧store2-closure仅64项，Mac/Win恢复未验。 |
| `s5-dense-01/dense-regressions-04/summary.json` | 28/28真实E5、零skip、166.10秒，当次稳定但绑定旧Store37f88…，不覆盖最新guards。 |
| `s5-dense-01/collection-regressions-01/summary.json` | 9/9真实E5、零skip、120.56秒，source_stable=false；之后Collection分支引用清单/断言又变化，当前版本未测试。没有当前37项闭合或科学语料排名。 |
| `peer-native-ui-02/independent-review.json` | 两实际helper CPU夹具独立只读审查未增可确认缺陷，SHA d4c4accb9dcd2022f64a56d2130013ebf5294675f9b6d6152e1eeca082e2a3d2；不增加测试数或OS/NAT证明。此前19/19、固定起点13/7点击和Viewer/草稿保护见下一历史节。 |
| 本轮官方GET | 同3ef/attempt1 Desktop41178119889 completed/failure、Runtime41178119790 completed/success，updated07:34:01/07:03:28UTC；未证明当前WIP的平台修复。 |

CI文献gate仍为38而实际基础已72，尚未修改/验证；当前源码联合回归、包安装、平台验收和最终治理均待办。接手须保持Store合作写者/POSIX租约与非POSIX恢复失败关闭边界；QA-v2冻结指标不得按heldout结果调整。Root完整AOCI24/24/Challenge9/10通过但治理Dirty/Stale；最终Maintain/Verify/Check/Guide与四文档检查见 `OWNER_EVIDENCE/handoff-20261031T1830Z/`，未对齐不得称完成。

## 2026-10-31 18:10 UTC：通用开发验证（历史）

持续目标恢复，10:30为历史交接；HEAD仍3ef，67路径WIP、暂存为空，尚无新提交/push/CI或新包。以下结果各自源绑定，不能相加成全仓/平台验收。

| 证据（相对OWNER_EVIDENCE） | 实际结果与边界 |
|---|---|
| `store-identity-01/red.xml`、`after.xml` | 未知数据库、替换/删除/原inode重写、真实spawn原导入恢复后回执保持等8项红→绿。随后独立审查发现hot-journal和fd锁问题，正补修，尚无最终闭合。 |
| `store-identity-01/matrix-01/{311,312,314}` | 基础PDF+Store各38/38零skip，10.171/9.857/11.045秒，8输入稳定；早于后续hot-journal/锁/schema修正，不覆盖当前变化。 |
| `peer-bridge-loader-rebind-01/closure.json` | 最新loader差异独立复核，三Python129输入相同且前后稳定；3.12为123pass/1skip17.047s，3.11/3.14各122pass/2skip14.648/14.853s；19专用及两实际安装helper场景全部执行，预期WinDPAPI/可选VTK skip，非目标OS证据。 |
| `peer-native-ui-02/closure.json` | 两目标build exit0；现有17+两真实安装helper UI，19/19零fail/error/skip，9.33s、971输入稳定，六组必跑guard通过。固定1440×1200/en/scale1/maximized-a4：发送已认证连接起点，选两冻结文件→Prepare→Host→Offer→查询批准→Send **13点击/0滚轮**；接收已认证/已Offer起点，复核清单/填本机目标/明确Accept/接收/详情核对 **7/0**。两端实际已安装helper、真实DTO/DATA/接收字节，Viewer workspace/payload/相机及隐藏Python稿保留。对端批准/发送为显式API夹具；不代连接UI、OS/GPU、Mac/Windows/NAT或跨站。原CPU合成反例仍11/20/1，证明范围分开。 |
| `s5-dense-01/dense-validation-03.xml`、`qa-v2-root-sample-review.json` | 纯校验16/16；28项真实模型完整回归待Store冻结。40QA-v1泄漏/不全证据保留；40-v2整篇文档split无交叉，Root6例真实段落语义/字节核对通过，冻结SHA1972ac2e75e4905615c32aa5d67983f72073319a9f78ca292656f59bf2089dee。多库全局检索正在实现，尚无corpus embedding/ranking/质量指标。 |

实际helper原生目标显式开启，缺安装前缀不作skip/回退；不影响默认CPU目标。复验须保持输入稳定，使用新外部结果目录：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  cmake -S desktop -B /home/mnemora/opt/stk-build/merge-check -DSTK_PEER_NATIVE_APP_ACCEPTANCE=ON
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  cmake --build /home/mnemora/opt/stk-build/merge-check --target stk-peer-app-tests stk-peer-native-app-tests --parallel 4
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  STK_TEST_PEER_INSTALLATION=/home/mnemora/.local/state/stk-validation/s4-owner-20261031/helper-package-01/relocated/stk-peer-runtime \
  ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
    -R '^(PeerState|PeerBridge|PeersEditor|PeerMouse|PeerNativeMouse|PeerNativeReceiverMouse)\.' --output-on-failure
```

前一真实sender-only 18/18、13/0证据 `peer-native-ui-01/closure.json` 保留，后续receiver夹具改动由19项新矩阵覆盖。Store物理恢复参考[SQLite锁与hot journal](https://sqlite.org/lockingv3.html)、[URI immutable语义](https://sqlite.org/uri.html)：live immutable跳过锁/变更检测，不能当授权/恢复证明；独立实验确实读到未提交generation2，而正常回滚为1。当前Store完善尚未完成，Windows独立lease/物理恢复和任意不合作的直接SQLite修改均不能借Linux证明。AOCI仍Dirty/Stale；最终源码稳定再按实时Guide完整Observed/维护/检查，不维护每个中间修改。完整路线及三待决见[handoff](../handoff.md)。

## 2026-10-31 10:30 UTC：转交核验（历史）

按所有者要求停止开发；[handoff](../handoff.md#当前接手顺序)为当前入口，下方恢复指令与旧失败状态为历史。main/HEAD/远端3ef，67未提交路径（27tracked/40untracked，含四状态文档），暂存为空；本轮未新增产品测试/构建/UI/包/commit/push/CI，收集已启动终态并核实证据。所有Agent作业终态，native槽释放。

| 证据（相对OWNER_EVIDENCE） | 实际结果及当前限制 |
|---|---|
| `peer-state-review-01/final-17-closure.json` | build08/ctest/四组必跑guard exit0，17/17零fail/error/skip，971输入稳定；保留重复Host/query两红例。固定1440×1200/en/scale1/maximized-a4：发送两冻结文件→Prepare→Host→Offer **11点击/0滚轮**；历史查询+手填session/grant **20/0**；Files已选已登记记录→Peers发送区/记录稿 **1/0**且不自动发送。Viewer workspace/payload/相机和隐藏Python稿保留。真实Bridge/CPU鼠标，**Host/query DTO合成**，不证明实际helper授权、OS或GPU。 |
| `peer-bridge-submit-02/closure.json` | 129输入稳定；3.12 **123pass/1WinDPAPI skip**，3.11/3.14各 **122pass/2skip**（另旧图测试缺可选VTK）；19专用Bridge三版本实际通过，含两安装helper和4提交故障反例。**早于后续loader ctime delta，待当前源码再整合。** |
| `helper-stat-final-01/summary.json` | 三Python各 **38/38零skip**，3输入稳定、实际安装manifest核验；跨API不比较ctime，同API完整戳检查保留。红例before-01.xml保留。没有新route、helper二进制/库或Windows执行。六文件前次独立审查见helper-independent-review-01。 |
| `s5-foundation-01/closure.json`、`matrix-03-*` | 3.11/3.12/3.14各 **30/30零skip**，7输入稳定、9.632/9.230/10.085秒；实际PDFium5.14.0/Unicode几何/全部支持页/FTS/citation等，**不证明随后发现的Store两问题已修**。 |
| `s5-dense-01/dense-01.xml` | 3.12真实固定E5 **8/8零skip，73.376秒**；hybrid_search在运行后新增未测，无最终dense源码闭合/两语料指标/独立QA审查。40QA预先冻结，权重/依赖/原文仅外部。 |
| `s5-dense-01/store-counterexamples.{py,json}` | 无关SQLite被接受并改变字节；真实spawn原import存活时被另一Library恢复，后来原completed receipt generation从1改为2。**两者均未修复**，列首要待办；旧FTS验证库明确重建。 |
| `literature-ci-02/summary.json` | YAML/Bash/Python gate通过，接受三实际30项XML、拒绝12类反例。新Store测试后须改精确数量；无远端新头运行。 |
| 本轮官方GET | 同3ef/attempt1 Desktop41178119889 completed/failure（updated07:34:01UTC），Runtime41178119790 completed/success（07:03:28UTC）；10:24–10:27UTC再核。Mac编译与Windows HTML-video仍待新头实际验证，前头Desktop终态不等于P4通过。 |

各矩阵范围不相加，旧581 peer/4716全量/2056 native/安装585不覆盖后来源码。新包/目标OS/整合回归/实际暂存扫描和AOCI治理仍待办。Root本轮完整AOCI24/24确认、Challenge10/10，但治理Dirty/Stale、完整系统当前可靠性false；不缓存正式认知正文。四文档、Git/hash/CI及最终检查证据 `OWNER_EVIDENCE/handoff-20261031T1030Z/`，不代后续Agent的认知建立或当前批次完整源码审阅。

## 2026-10-31：Bridge基础启动修复与Peer桌面接线（历史）

持续目标恢复；09:00为历史转交点。`OWNER_EVIDENCE/peer-bridge-02/closure.json`：三版本最终source129稳定；3.12为119pass/1WindowsDPAPI skip（17.298s），3.11/3.14各118pass/2skip（15.043/15.142s，另skip旧图测试缺可选VTK），全exit0，全部15个专用Bridge及真实两个已安装helper测试实际运行。四旧stderr证明NumPy急切导入导致基础Bridge/子进程提前退出；修复为MaterialsService懒创建。无NumPy的真实constructor/stdio两版本各2/2先于安装通过，MaterialsAPI3.12为35/35。只离线补声明依赖到隔离环境，opt基础环境不变。

helper独立审查源SHA及限制见 `helper-independent-review-01/review.json`，未新增可确认缺陷，无新helper运行结果。PeersEditor/注册/英中译文/Files导航已写入，i18n初次2771/2771通过（之后增加分页译文须最终重验）；准备来源/桥代次和实际鼠标/工作空间反例、分页/CI依赖尚在修改。**新UI尚未编译或验收，点击次数未测**；旧3CPU基线运行不覆盖新实现。无新增产品提交、push、新包或新头CI，AOCI业务仍变化不维护中间态。

## 2026-10-31：最新交接核验（历史，09:00 UTC）

当前 [handoff](../handoff.md#当前接手顺序) 覆盖旧停止点。main/HEAD/官方远端3ef，48个未提交路径（19 tracked/29 untracked，四状态文档包含在内），暂存为空。本次只整理文档并收集已启动验证终态；没有启动新产品测试/构建/UI/模型调用，也没有新包、commit/push或CI触发。点击次数未测，P4/S4/整份计划未完成。

| 证据（相对OWNER_EVIDENCE） | 本次收集的终态及限制 |
|---|---|
| `helper-package-01/closure.json` | 3.11/3.12/3.14 loader各35/35零skip，12输入稳定；Linux实际重定位UDP/TCP/IPv6，每向1MiB control+64KiB binary，无库路径/源码回退。manifest SHA `49a7fb1705821319e6e328d2bdc258400875c07b57a8a2fbd1e5e0539fbad5be`。34组件/40库/252文件/105对应源码资产；原helper/库不变。当前Linux ABI、签名未核、Mac/Win/干净机及独立审查限制见handoff。 |
| `peer-bridge-01/matrix-312/summary.json` | 117pass/1WindowsDPAPI skip，16.770s、exit0、116输入SHA稳定。含两个实际安装helper/认证/Host+Accept/后台生产文件/重复不重放/被动观察撤权，以及identity recovery/关闭竞态。不是全仓或其他OS证明。 |
| `peer-bridge-01/matrix-{311,314}/summary.json` | 各101pass/2skip/**15fail**/0error，128.480/128.277s、exit1、116输入稳定。13失败明确缺numpy，2旧childBridge无响应超时，未证明后者根因；本次不安装或重跑，保留XML/日志/环境交下一Agent。 |
| 新原生PeerState目标 | 既有build会话87878已exit0，`stk-peer-app-tests`编译/链接完成并释放构建槽；三项新测试**未执行**，没有最终源码SHA闭合、UI或点击验收。 |
| 官方CI再核 | 官方main及两个run同3ef/attempt1：Desktop41178119889 completed/failure（updated07:34:01UTC），Runtime41178119790 completed/success10/10（07:03:28UTC）。上一Desktop终态门满足，Mac/Windows仍有失败，新WIP尚无新头CI。 |

先前581/580 peer矩阵、接收端121矩阵、Mac选择502及Windows诊断72均各自绑定当时源码，晚加被动API/Authority/Bridge/helper/C++不得借旧全量声明通过。旧4716/2056/安装585亦不覆盖本批；旧便携WIP包不含新增sender/helper/Bridge/C++。四状态文档、Git路径/摘要、治理和文档/扫描检查结果见 `OWNER_EVIDENCE/handoff-current-20261031T0900Z/`；本次未暂存，文档扫描不是未来实际暂存扫描，治理未对齐时仍须下一Agent按新Guide处理。

## 2026-10-31：生产文件链源绑定验证（历史，本次转交前）

持续通用目标已恢复，HEAD仍3ef，源码未提交；本批无新产品UI点击、新包安装或新CI触发。所有测试KEY空/MODELunset，无收费请求/端点或网络策略改动。下方交接停止/发送端未接通/两问题未修均为历史。

| 证据（OWNER_EVIDENCE相对路径） | 实际结果及适用边界 |
|---|---|
| `file-store-fixes-01/matrix-01` | receiver26/26；3.11/3.12/3.14各121pass/1WinDPAPI skip、4.07/4.02/4.27s、24输入稳定。原操作最终lease内重查；长resume验证在授权及DB事务外，当前grant/phase/op/物理字节戳/journal CAS再核；7个修复前红例及先前驱动失败保留。 |
| `peer-files-final-01/312/summary.json` | 14个peer测试文件、81输入**全部SHA稳定**，581pass/2skip，282.83s/exit0。含真实两helper UDP/TCP、持久身份/当前批准/生产sender+receiver、丢start/DATA/complete回复、真实断线→新TCP/auth→新Host批准/Accept/grant→明确resume、撤权/rebind/新epoch拒下一块、完整SHA/无覆盖发布。**240MiB/4098块**实际通过，控制RPC计数<10、双端chunk记录4098、Python分配峰值<32MiB断言，不宣称RSS/原生库/浏览器内存或WAN性能。 |
| `peer-files-final-01/{311,314}` | 各580pass/同2skip，62.56/62.71s/exit0，81输入稳定；与312相同14文件，显式不重复native_large。仅跳过Windows真实DPAPI、junction两个精确用例，所有配置的其他native实际执行，无crypto缺失跳过。`matrix-summary.json`保存精确名称/范围；新增helper/Bridge尚不在此矩阵。 |
| 恢复反例 | `peer-files-recovery-before-01.xml`的两失败确认缺显式采用入口；after/最终矩阵证明原files.complete proof采用、撤权不复活、接收端rename后journal故障保持unknown、伪造原SHA拒绝。`peer-files-sender-01.xml`的修订假设失败已改用准备前后实际info比较；后续真实两helper11项通过，原失败不覆盖。 |
| `p4-windows-diagnostic-01/closure.json` | 新有界事件/分阶段宽度诊断，仅reports_native_window.cc改动；Linux六目标构建33.77s、72/72CPU零skip2.31s、566输入稳定。不过滤事件/改帧边界/放宽divider或媒体门。 |
| `runtime-macos-peer-02/summary.json` | Mac job源码新增11文件 `-k not native`，必跑16个sender/recovery和旧九组；本机502pass/2仅Win skip，guard正例/9负例、YAML/Bash及SHA检查通过。并非Mac运行或helper构建/安装证明。 |

3ef官方Desktop41178119889终态failure、Runtime41178119790 success10/10仍是最近已推送头。Windows工件已真实核186947860bytes及SHA：5/6通过（独立视频20轮/161图），HTML-video0轮/0图止于报告401→511、Viewer435→325的反方向divider，capture始终Splitter直到Up，尚无媒体观察；根因未定。`delivery-03/windows-native-3ef-01/analysis.json`及原工件保留，Mac仍from_chars编译失败/本地24Linux补修，均待新头目标OS。不降低像素、导航、暂停或20轮161图门。

本批Python581不是全仓旧4716重跑，不是旧包585或新安装；Linux不代Windows/Darwin/跨站或材料有效性。helper发行/真实桌面入口正在继续，业务仍变化，正式AOCI未维护新WIP，不能沿用1144旧aligned；稳定后再完整Observed/维护/Verify/Check/Guide及真实暂存扫描。四状态当前入口[handoff](../handoff.md)，PET新专项后置。

## 2026-10-31：交接核验（历史，3ef/文件链 WIP）

本次只保存交接并核实Git/已有证据/CI；未运行新产品测试、UI动作、构建、包安装，没有新增点击验收、提交、push或CI重触发。实际HEAD/main/origin/main为 `3ef4b2716d42304d708062f9715edae0afb5874f`，20产品/测试/spec WIP保留、暂存为空，四状态文档另改。交接前SHA/文档原件和最终检查在 `OWNER_EVIDENCE/handoff-20261031T074142Z/`。当前接手顺序见[handoff](../handoff.md#当前接手顺序)，下方旧ahead2/无源码WIP/对齐均为历史。

以下是交接前已有运行，均KEY空/MODELunset；各源绑定范围独立，不相加：

| 证据（相对OWNER_EVIDENCE） | 结果/边界 |
|---|---|
| `peer-file-endpoint-312-02/summary.json` | 最终endpoint定向301/301零skip，3.93s，源/helper SHA稳定；15文件端点含真实两helper UDP/TCP及数据/journal fsync→RECEIPT，测试identity-only adapter，不是生产FileStore/会话/grant接线。 |
| `peer-file-endpoint-01/summary.json` | 联合408/408零skip53.16s，当时源稳定；之后仅endpoint/专用测试改后置capability启动B reader，301覆盖差异，未重跑最终408。 |
| `peer-file-protocol-{311-01,02,314-01}` | 纯codec各286/286零skip；后续endpoint311/314各286pass+15fixture errors（原env缺crypto），失败保留，无跨版本native通过结论。 |
| `identity-pairing-02/`、receiver终端 | 前者3.12为95pass/1WinDPAPI skip，18SHA当时稳定，后置Authority改动未覆盖；receiver最后17/17、0.83s/exit0但无最终SHA/JUnit closure。两源码问题未修：最终写lease内重查op、resume长扫描离开Authority。生产sender/endpoint集成待做。 |
| `delivery-03/peer-file-io-03.xml` | manifest+IO79pass/1Win skip；Windows/Darwin专有分支未在Linux执行。 |
| `p4-macos-number-01/` | parser补修Linux构建32.37s/24项全过5.946s、SHA稳定；无实际Xcode/Cocoa证明。 |

缺crypto环境已另外离线准备于 `peer-python-envs-01/{311,314}`（crypto50.0.2/pytest9.1.1，summary ready=true），尚未补验。`peer-base-regression-01`108pass但源码漂移，harness失败，不作稳定closure。旧完整4716/16skip/2排除、原生2056、安装585和额外worker1均早于本批WIP；无新包，不能沿用旧文档重绑称覆盖。

07:40:57UTC官方GET同3ef/attempt1：Desktop[41178119889](https://github.com/sijintech/stk/actions/runs/41178119889) completed/failure：Mac124469794462编译from_chars deleted（P4原生未跑）、Windowsnative124475289636 step7 OS截图验收失败（07:33:48结束，新日志/工件尚未读、根因未知），其余四jobs成功。Runtime[41178119790](https://github.com/sijintech/stk/actions/runs/41178119790) completed/success10/10；Docs/Secret此前已核成功。证据 `delivery-03/p4-watch-20261031T065124Z/snapshot-20261031T074057253075Z.json`。前头整个Desktop终态push前提满足，P4未通过；原像素/暂停/导航/20轮161图门不变。

AOCI本Run完整传输/确认及严格验证完成，当前业务仍Dirty/Stale中间态；此前1144对齐不覆盖新peer。一次Maintain返回stopped/blocked、aligned=false，8missing/9stale/7observed_new、remaining17，未签发语义候选或写正式Entry/Baseline，无Recovery/第三方冲突。待最终稳定后按实时Guide完整审阅新Observed当前SHA/ACK再维护；本次不替后续Agent确认。最终交接机器检查见closure，不在文档缓存正式认知正文。S4/S5/S6/P5-S7与三待决保留，PET新专项后置。

## 2026-10-31：待办转交核验（历史，3ef 提交前）

本次按所有者要求停止扩展实现，只整理交接和必要AOCI资产，没有新增代码提交、push、产品测试或CI触发。实查本地main2513c088、ahead远端6126两个提交，暂存为空，六份tracked记录改动保留；06:41 UTC前后官方GET：6126 Desktop41163547328 completed/failure、Runtime41163547349 completed/success，均attempt1，当前代码无新头平台CI。前头终态等待满足不等于P4通过。

交接开始时AOCI已Apply25项、1141条，Observed11 ACK已应用，剩余11候选尚未写；本次四文档变化需重新绑定当前完整候选。最终Verify/Check/Guide、实际文档检查和精确Git/CI快照读 `OWNER_EVIDENCE/handoff-final-20261031/closure.json`，不要沿用旧Plan或提前称aligned；不保存正式认知正文。最新文档包重绑读 `OWNER_EVIDENCE/package-final-docs-02/rebind-summary.json`：沿用下节681wheel/995sdist及22测试字节边界，只有本文件进sdist，不扩大范围、不安装或重跑585。新SHA仅存外部结果，避免自身摘要循环。[handoff](../handoff.md#接手先做的待办)列记录提交/push/新CI及剩余通用路线，PET新专项后置。

## 2026-10-31：稳定源码447/2513及窄补验

本批主链 `447a19ac8199c62ba81be5aef5458b4135b04410`、Apple条件rewind补修 `2513c08817bb9036bc63ffd341503f6d85a29aaf` 已在本地main提交；本节是推送前稳定候选记录，真实远端/新头CI先核Git/Actions。源码与测试稳定，不再把下文05:45未验WIP或旧“仍运行”当现状。所有实际测试KEY空、MODEL unset，无收费模型请求。

- Python完整 `OWNER_EVIDENCE/python-full-02/closure.json`：4716通过、16跳过、2排除，0失败/错误、883.547秒，1010输入稳定；8强制真实算法/训练/网络、peer202/federation407零skip，15旧SIG11案例现实际通过。16skip分类、启动器01失败及真实进程退出保留。
- 原生 `NATIVE_EVIDENCE/final-native-01/`：all构建exit0、853.949秒，2056/2056零失败/错误/skip、938.419秒，2816输入当时前后一致。Federation24/24；四固定布局Data各13clicks/0文本，完整同意/两次评估准入/独立启用回退/撤回审计各50clicks/9文本/0滚轮，起点两行/各一训练留出，保Viewer/隐藏稿。生产Bridge/Owner加合成候选的CPU事件，不代实际Flower/UI网络或OS/GPU/物性。
- 全量之后两个差异独立核验：三平台Federation守卫 `NATIVE_EVIDENCE/ci-guard-01/` 已用Linux实际XML及缺组/skip/fail负例验证并进447；Apple补修 `OWNER_EVIDENCE/p4-platform-20261031-02/` 六目标构建exit0/33.628秒、72/72 CPU零skip/2.269秒，529输入前后稳定，JUnit SHA `1b7191c29425fa67d700be957880a87a243436cf2c0d92f74686aa47833bb8a9`。窗口fixture当前SHA `bf5eeda293485d21a3c0abe0bbfb9f6eb7e01ac2aabe1f97c97cdf124671da6d` 与2056时53a525de…差异明确保存；**不是最终2056重跑，Linux不编译Apple条件/Cocoa/Win32**。
- `OWNER_EVIDENCE/package-03/acceptance-summary.json`：独立安装585/585零skip，8真实必跑，681wheel/995sdist源成员核对，基础前后无flwr；`owner-worker-01`额外实际桥/HTTP owner→Runtime ClientApp1/1、1.76秒、独立梯度误差≤1e-14、明确collect一次/撤回。范围重叠，不累加。
- 447和2513实际暂存分别1055276bytes/1389bytes，均按.gitleaks.toml脱敏扫描及空白检查exit0后提交，证据 `OWNER_EVIDENCE/delivery-01/staged-code-summary.json`、`delivery-02/staged-p4-summary.json`。每次后续暂存仍须独立扫描。

包文档收尾：四状态文档只有本文件进入既有sdist；其余三份不因重绑而新增进包。最终重绑使用新目录 `OWNER_EVIDENCE/package-final-docs-01/`，要求wheel整包字节等于已测a6e5…、全部681业务成员和22选定测试不变，sdist995源成员匹配且只允许本文件差异。新SHA及精确差异见外部 `rebind-summary.json`，不回写其自身包含文档形成摘要循环；这是来源/文档重绑，非重跑585/安装或新增平台覆盖。若业务/测试漂移则停止该复用、按影响重新验证。

治理收尾：05:44工具为observed_pending；完整审阅native3/Python4/P4四份并核11路径当前SHA后，Baseline确认已应用（事务f8be6acedab1ccffa0410d6f），证据 `delivery-02/observed-review-sha-check.json`、`aoci-observed-ack.json`。ACK不创建Entry；正式语义维护、最终Verify/Check/Guide与记录暂存扫描以 `delivery-02/` 实际机器结果为准，不以读取/确认代替aligned，不在本文件缓存Whole-Index。

平台：05:43 UTC前后官方GET仍6126，Desktop41163547328 completed/failure、Runtime41163547349 completed/success，旧Windows3/6/Mac4/6，当前补修新头必须另验；终态等待满足不等于通过。S4其余/S5/S6/P5-S7及三待决仍在，PET新专项后置。详细源入口、固定起点/结果及后续范围见[handoff](../handoff.md)。

<a id="2026-10-31最终候选验证与转交范围0545-utc"></a>

## 2026-10-31：最终候选验证与转交范围（历史，05:45 UTC）

当前本地main/HEAD `447a19ac8199c62ba81be5aef5458b4135b04410`，43路径代码提交尚未推送；origin/main/官方远端仍6126，暂存空、7份tracked修改保留。[handoff](../handoff.md)列完整证据、文件/哈希、固定起点点击、未验Apple补修及接手顺序。本次快照整理未重跑产品测试/构建、未新增提交/push/触发CI；测试仍须KEY空/MODEL unset。

- `OWNER_EVIDENCE/python-full-02/closure.json`：4716 passed、16 skipped、2 deselected、0失败/错误，exit0、883.547秒，1010输入稳定。8强制真实算法/训练/网络及peer202/federation407零skip；15项旧SIG11案例现实际通过。16skip分类和失败启动器01均保留。
- `NATIVE_EVIDENCE/final-native-01/`：all构建exit0、853.949秒，完整CTest2056/2056、零失败/错误/skip、938.419秒；2816输入在当时构建/测试窗口一致，JUnit SHA `8bcdaa7aef333125751a2236e020452ae0677e5a792003a78fd91771ac5410c0`。Federation24/24、四布局Data各13clicks/0文本，完整链各50clicks/9文本/0滚轮，起点两行、各一训练留出，保Viewer/隐藏稿；生产Bridge/Owner加合成候选的CPU UI证据，不代Flower/OS/GPU或物性。
- 回归后 `.github/workflows/desktop.yml` 三平台守卫增量已进447，`NATIVE_EVIDENCE/ci-guard-01/`对实际Linux XML及负例核验。之后唯一源码WIP Apple rewind fixture当前SHA `bf5eeda293485d21a3c0abe0bbfb9f6eb7e01ac2aabe1f97c97cdf124671da6d`，全量测试时为 `53a525de8fb958b02313a127b2a9ebfe99ef1e6af31a4aea2262f013c4a836b8`；**尚未构建/测试，不在2056覆盖内**，目标OS仍待新CI。
- `OWNER_EVIDENCE/package-03/acceptance-summary.json`：独立安装585/585零skip，8真实必跑，wheel/sdist681/995源成员匹配，基础前后无flwr；`owner-worker-01`额外实际owner→Runtime ClientApp接线1/1、1.76秒、独立梯度误差≤1e-14、单次collect及撤回。范围重叠，不累加总数；包SHA见handoff。当前交接晚于sdist，最终包文档重绑待做，不能称旧包含本交接。
- 提交447前真实暂存43路径/1055276bytes已过gitleaks/redact及空白检查，证据 `OWNER_EVIDENCE/delivery-01/staged-code-summary.json`；后续暂存须重新扫描。05:43 UTC前后官方GET：6126 Desktop41163547328 completed/failure（04:08:08更新），Runtime41163547349 completed/success（03:29:26更新）；P4 Windows3/6、Mac4/6，新头447未推送/无CI结果。前头终态等待满足不等于平台通过。

正式AOCI治理仍dirty/stale，05:44 Guide blocked/observed_pending、complete=false；native3/Python4完整Observed审阅已有，P4最终审阅及acknowledge/Maintain待接手完成。本次仅转交未完成批次，不提前维护或报告aligned。四文档原版本、Git/7路径SHA/Guide在 `OWNER_EVIDENCE/handoff-20261031T0545Z/`。后续S4/S5/S6/P5-S7及三待决不变，PET新专项后置。

## 2026-10-31：owner 续接验证（历史）

当前代码仍为main上未提交WIP，HEAD6126；以下是实际定向/安装证据，不代表完整计划完成。三Python的桥/owner/契约/agent矩阵各172/172、121输入稳定，属于后续模型CAS预检补修前；补修后三Python后端各112/112、63输入稳定，见 `OWNER_EVIDENCE/bridge-02/matrix-01` 与 `backend-preflight-01/matrix-01`。候选package-03 wheel SHA `a6e5b8bcd8256f511f201787a4d22c1603a8a65c8f5671577837c7f4dc9d9d6b`、sdist SHA `ad9da7b0ffef0cff6269b43987caef91877cb563b815316ab6e092e070d779d6`：681/995源成员匹配；独立安装585/585零失败/错误/跳过，含2聚合、4实际ClientApp、2三节点两轮网络必跑，基础前后无flwr。证据 `OWNER_EVIDENCE/package-03/acceptance-summary.json`；不证明跨站或材料指标。

原生candidate-08构建32.809秒、20/20零跳过，28输入稳定；固定四起点为1440×1200@1英语、1000×1200@1中文、2160×1800@1.5英语、2000×2400@2中文的Federation Data区，项目rev1两行、一特征Temperature[K]/一目标Pressure[Pa]、未选连接/列/角色，保留既有Viewer/相机和隐藏Python稿。各13次实际CPU UI鼠标点击完成读取连接/owner、选表/列/各一训练留出、Freeze及Register；不是OS/GPU截图。candidate-10完整链四布局4/4、4.532秒、31输入稳定，各50点击/0滚轮：授权、两条审计、空阈值明确键入0、两次留出通过及Admit不改active、v1→v2→v1 generation1/2/3、撤回且审计保留，Viewer/隐藏稿均保留。候选来源为合成协调夹具，不是Flower训练；统一2056项回归待结果。candidate-09 GTest同行宏编译失败与修正保留。

P4本地6目标构建32.803秒、72/72CPU零跳过、529输入稳定；之后仅Cocoa零frame回退及Win说明调整，未将这些平台分支记为本机编译，最终hash/差异见 `OWNER_EVIDENCE/p4-platform-20261031-01/closure.json`。同头Windows官方工件实际3/6通过，原始SHA与失败分类在 `p4-windows-read-20261031T0434Z/analysis.json`。所有OS像素、播放/暂停、20轮门保留，新头Mac/Win验收仍待CI。

完整Python首轮 `OWNER_EVIDENCE/python-full-01` 被启动器默认120秒总限终止，未产生JUnit或产品结论；18项原进程身份匹配检查均已结束，没有发送清理信号。失败日志/清理核验保留。新 `python-full-02` 同1010输入、私有Xvfb/llvmpipe及明确1800秒总限，实际 **4716通过/16跳过/2排除、零失败错误、883.547秒**；输入SHA稳定、基础前后无flwr，14算法模块和peer二进制摘要均稳定。8强制聚合/训练/网络、peer202/federation407均零跳过；逐一比对旧SIG11案例名，15/15现已实际通过（render类23项零跳过）。16跳过为Windows专用7、MuFerro opt-in3、PySide6/MCP/未标perf各2；另2已标perf排除，不混算。已核原driver/wrapper/pytest/Xvfb相同进程身份均退出，详见 `closure.json`、`mandatory-cases.json`、`previous-render-skips-now-passed.json`。

额外 `OWNER_EVIDENCE/owner-worker-01` 独立安装接线1/1通过、1.76秒：真实桥/认证HTTP owner登记和固定grant UUID→真实隔离ClientApp Runtime→private delta对独立梯度参考绝对误差≤1e-14→明确collect一次、重复不发送、审计、撤回后拒绝下一轮；普通workspace无原始数据，仅receipt.json公开。该外部用例未改产品或sdist测试，不等于跨站/材料验证。

统一原生all构建exit0、853.949秒、2816输入稳定，完整2056项CTest从05:06:04 UTC开始，尚未终态。全链50次鼠标之外有9次文本提交，各含全选、文本事件和Enter；Data13次点击无文本提交。仅四状态文档在此期间更新，其他Python/Schema/测试及读取指南冻结。最终统一原生、文档/包重绑、AOCI、实际暂存扫描与提交/push仍待完成。

## 2026-10-31：S4 owner 工作树交接实况（历史）

本次仅文档核验，没有新增产品测试/构建/模型请求。04:20:50 UTC官方GET：HEAD/main/origin/main/远端均6126c6a2，暂存为空；40个未提交路径（27 tracked、13 untracked）保留。Desktop41163547328 completed/failure、4成功2失败，04:08:08更新；Runtime41163547349 completed/success。终态等待前提满足，Mac/Windows原生P4未通过；CI只覆盖6126，不覆盖owner WIP。

| 已有运行 | 实际结果与适用范围 |
|---|---|
| `OWNER_EVIDENCE/backend-04/summary.json` | 3.11/3.12/3.14各113/113，Runtime core/input-hashes/events/SSH60/60，零fail/error/skip、46输入SHA稳定；定向源码验证。 |
| `OWNER_EVIDENCE/bridge-01/bridge-before-rejection-tests.xml` | 21/21、零fail/error/skip、3.362秒；已完成JUnit，Root原shell退出状态未闭合。尚无新typed rejection专项和最终源码联合证明。较早312为59/59、311/314各13/13，勿合并充当最终全量。 |
| `NATIVE_EVIDENCE/candidate-06/` | 构建exit0、31.624秒、15输入SHA稳定；13项8pass/5fail、0skip。raw-null包络1项已触发bridge wrapper修正，4项UI journal完成断言已加只读等待；最新源/Schema未重编重跑。 |
| 四固定CPU UI布局 | a4最大化Federation Data、项目rev1两行、无选择、隐藏Python草稿及原Viewer：en1440×1200@1、zh1000×1200@1、en2160×1800@1.5、zh2000×2400@2，各实际13点击到Freeze/Register，Viewer/相机/稿保留且script history空。为CPU UI事件、非OS/GPU证据，完整用例仍失败；consent/evaluation/version全链未验收。 |

原生typed rejection绑定及fresh-info/newUUID、本地prepare确定验证失败恢复、bridge新proof反例、additive桥文档、统一最终源码回归/安装/真实worker和AOCI维护仍待完成。旧4589/402证据属于已推送网络基线。本次文档链接/空白及限定doc diff的脱敏gitleaks结果见 `OWNER_EVIDENCE/handoff-20261031T042050Z/closure.json`；外部根与接续命令见 [handoff](../handoff.md)。

## 2026-10-31：首轮交接核验（历史）

所有者要求写待办并交另一Agent，本轮停止实现。交接前 `git status --short --branch` 干净，HEAD/origin/main及真实remote main均 **`6126c6a22cc19270aedd135fb97c09b949c49f9b`**。本次仅四状态文档与必要AOCI托管资产，未提交/push或重触发CI，未运行新的产品回归、模型请求或UI点击验收；没有活动本地worker/编译/监控。

| 核验 | 实际证据与边界 |
|---|---|
| 已推送交付 | a5510bfa网络、10b784ba Windows有效Content、b02a51cd视频布局、dd318ce2 Mac测试宿主和6126记录/AOCI；`NETWORK_EVIDENCE/delivery-closure-summary.json`确认push及remote。 |
| 最终包重绑已完成 | `package-delivery/acceptance-summary.json`：全部682个wheel成员与402项已测候选字节相同，SHA `93734540988d5801ac0a42b016d1b9d500c51b67c7c3debf7b63091e31c75464`；最终sdist SHA `5ca4e6472d6a79ec78bd0cd5fbbe265758ea78e64b0b2510350aa925201dc8a7`，988成员/987源码，仅Hub测试guard和验收文档差异已核。本次交接文档晚于该包；没有重跑402/4589或声称新sdist已测试。 |
| 已交付AOCI | 24对象按完整11+13批Apply，remaining0；Verify/Check/Guide exit0、aligned、Guide complete/next none，零Observed/未决事务/Recovery。相关compact结果在 `aoci/delivery-*.json`，不重复旧交易；正式治理不替下一Agent自己的完整认知恢复。 |
| 当前CI快照 | **2026-10-31 03:29:04 UTC**，同head6126、attempt1：Desktop41163547328 **in_progress**、2项成功，Runtime41163547349 **in_progress**、9项成功，Docs41163547325与Secret41163547316 **success**。`ci-6126/handoff-20261031T032904Z.json`；无本头Mac/Windows完整原生验收结果，下一次代码push等待整个Desktop终态。 |
| 尚未实现 | owner/evaluation/models及专用Runtime路由、bridge/UI仍是设计草案，后端代理确认零修改；独立线性模型不冒充既有Materials曲线模型。P4/S4和S5/S6/P5-S7未整体完成，三待决及PET后置不变。 |

当前四文档、链接/差异核验和本次AOCI收尾结果统一写入 `NETWORK_EVIDENCE/handoff-transfer-20261031/closure.json`。本机外部证据不随clone携带，移交时只复制明确源码/验证产物，不复制凭据或用户配置。最新任务清单见 [handoff.md](../handoff.md)。

## 2026-10-30：源码提交、Windows有效ContentSize修正与本批闭环（历史交付）

当前网络源码 `a5510bfa838e34e5555f0c6beaa4e0e6b04d190a`、Windows修正 `10b784ba262fae7bbd26c5d1f2d39398019f5ec1` 已本地main提交。实际记录提交、最终包差异绑定、24对象AOCI全批维护/Verify/Check/Guide、暂存扫描、push及新头CI统一记录在 `NETWORK_EVIDENCE/delivery-closure-summary.json`；证据根 `/home/mnemora/.local/state/stk-validation/s4-network-20261030`。恢复开发后的源码提交不等于新平台CI通过，旧停止交接段落均保留为历史。

| 范围 | 本轮新增实证 |
|---|---|
| 网络源码提交 | 25文件3951新增/52删除；实际暂存diff234011bytes、SHA ce53a628c145ca942c0b1023c7a307a1a8147e373106bd2dee939ef70e2b9e98与secrets-source-02同，gitleaks0后提交a5510bfa。4589/31skip/2deselected、安装402/402、最后guard26/26和缺依赖collection证据保持下表原范围，不重写为最终全量。 |
| Windows源码与构建 | 三文件127新增/29删除，commit10b784ba；实际merge-check all-target增量构建exit0、6.265秒，三源SHA前后稳定，Linux实际重编CPU测试并链接；未编译Win32分支。 |
| 相关CPU验证 | `p4-next/candidate-02/focused.xml`，**72/72、零fail/error/skip、1.350秒**；含原69及3个新DocumentEvidence.WindowCaptureContent反例。截取实CI坐标、负origin/物理DPI/缩放/无匹配/非稳定/裁剪/溢出和资源上限均验证；非OS像素/20轮验收。 |
| 裁剪语义及限制 | pool/item/texture1040×736，ContentSize/DWM1026×729，按有效content独立判定origin/crop，避免读取pool padding。DPI/三rect稳定性/格式/嵌套与8192边长/16Mi像素约束保留；尺寸匹配不证明像素原点，等待Windows真实WGC。Mac激活、HTML-video Viewer布局仍未由本修正覆盖。 |
| 本轮暂存扫描 | 三文件实际暂存diff与gitleaks结果在 `p4-next/candidate-02/secrets-staged/summary.json`，exit0/0findings后提交；四状态/AOCI记录最终暂存另扫。 |
| Observed闭环 | 完整复核最后Hub测试头及受影响生产/契约后ack，事务e23ffa808f1598ed4d270db9，baseline06ee56b8406c12447cac83566c7f859611c299ad73f117f6842575017bad53ef；Guide零Observed pending、零pending transaction/Recovery。正式语义仍按本轮完整24批次处理，结果见closure。 |

视频原生验收布局fixture另提交 `b02a51cdea47868e4c599fdbc763ed80ddd1e3b7`：Reports右侧却要求左侧并固定负drag的问题已改为按真实左右顺序，传入/保护原Viewer，真divider事件与完整媒体/同导航暂停时间/终态草稿门不变。实际probes-ON增量构建33.882秒、exit0，相关72/72零skip、1.326秒，源码稳定；证据 `NETWORK_EVIDENCE/p4-next/layout-01/summary.json`，实际单文件暂存gitleaks零发现。Linux只证明编译和相关CPU行为，不证明Mac激活或Windows原生视频/完整20轮。此fixture不进入Python包；最后Observed复核与本批24对象维护结果见closure。

Mac验收宿主追加修正 `dd318ce287bc1d52fd8da324026c321e984dc55c`：普通未打包test executable先显式设置并核验Regular激活策略，再请求自身窗口激活；原active/key/精确窗口合取与5秒UI观察门保留。失败/超时写固定before/after/final整数/布尔快照和计数，轮询不写盘、不识别外部窗口。`p4-next/macos-activation-01/summary.json`：Linux增量全目标构建exit0、32.146秒，原72CPU用例名称集合相同且72/72零skip、1.309秒，三源SHA稳定，暂存gitleaks零发现后提交。**Linux不编译Cocoa分支、不证明真实激活/OS像素/20轮**；38a未记录policy，不能断言原运行态就是prohibited。未打包程序默认策略与setter返回值依据 [Apple activation policy](https://developer.apple.com/documentation/appkit/nsapplication/activationpolicy-swift.enum/prohibited?language=objc) / [setActivationPolicy](https://developer.apple.com/documentation/appkit/nsapplication/setactivationpolicy(_:)?language=objc)，策略成功仍不替代原激活观察。

本轮无新增UI点击验收。前头38a9fd43 Desktop41097301277 completed/failure（4成功2失败）、Runtime41097301247 success10/10已直接核验；前头终态push门满足，P4/S4完整产品、跨站、S5/S6/P5-S7和三待决继续，PET新专项后置。

## 2026-10-30：交接核验（历史，当前见最新首节）

所有者要求保存待办并转交另一Agent；本轮仅四状态文档，未重跑产品测试或修改产品。Git HEAD/origin/main/ls-remote均38a9fd433c1924a5bcc068e4bd1643e3f7c82bbf，25个已暂存网络文件保持原样。证据根 `NETWORK_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-network-20261030`，交接前四文档与本轮核验保存在 `handoff-transfer-20261030T184019Z/`；该目录不是正式AOCI正文缓存。

| 范围 | 已核实结果及限制 |
|---|---|
| 完整Python | `python-full/summary.json`/`results.xml`：**4589 passed、31 skipped、2 deselected，0 failure/error，824.25秒**；4620个JUnit case。1000输入前后同摘要 `7039e8f8b184fe9b8ca1a815f2eaf7e9c226bc5c8f7a99a6761c6387143b38eb`；peer202、federation326均零skip。31skip包含15离屏SIG11；本批未再补离屏，不挪用旧15/15。 |
| 独立安装 | `package-final/acceptance-summary.json`：**402/402，零skip，41.99秒**，8mandatory真实用例实际执行。677wheel/987sdist源成员绑定；base-env-02与algorithm-env隔离、base无flwr、两环境677成员前后稳定。首次离线缓存缺vtk9.7.1失败保留，新base以缓存兼容版本安装并pip-check通过。 |
| 包身份 | 已测wheel SHA `93734540988d5801ac0a42b016d1b9d500c51b67c7c3debf7b63091e31c75464`；sdist SHA `1482643ae7dda2b7fa743261c728815982abb0efc7f20fc818649ac56e51ae03`。全量/安装之后仅改Hub测试可选依赖guard；本次runtime-validation又会改变sdist，交付前新目录重包并核成员差异。不能把这些结果改写为最终源码全量。 |
| 最后可选依赖补验 | `hub/optional-import-followup.xml` **26/26零skip**；`hub/optional-collection-02/summary.json`模拟fastapi/httpx缺失时整模块一skip/0error，exit5=无测试可执行，仅证明收集行为，不是Windows运行通过。 |
| 联合及真实网络 | `network-joint-01.xml` **352/352零skip**。三Linux Runtime/三出站NodeAgent、TCP/WSS、FedAvg/FedProx各两轮、12实际ClientApp任务，与独立梯度参考1e-13一致；同机loopback，不代跨站/NAT/TURN。详情和原失败见下方历史记录。 |
| 暂存密钥扫描 | `secrets-source-02/summary.json`：25文件234011bytes、diff SHA `ce53a628c145ca942c0b1023c7a307a1a8147e373106bd2dee939ef70e2b9e98`，gitleaks exit0/0findings，覆盖可选依赖guard。它不覆盖之后的四文档和未来暂存；提交前实际最终暂存再扫。 |
| 同head最新CI | 本轮GitHub connector直接GET：Desktop41097301277 **completed/failure**、attempt1、updated18:06:52UTC，6jobs中4成功2失败；Runtime41097301247 **completed/success**、10/10。这些只覆盖38a9fd43，不覆盖网络WIP；前头整个Desktop终态的push等待门已满足。 |
| P4目标平台 | `ci-38a/terminal-1806/terminal-summary-v2.json`：Mac CPU1420/Metal254零skip，native4/6，成功601张记录PNG SHA逐一核验；两个媒体用例自身窗口激活门失败、0轮0图。WindowsCPU1364零skip，native0/6、0轮0图，五WGC几何/一Viewer布局失败。媒体状态观察不代最终OS像素。 |
| 外部P4候选 | `p4-next/candidate-01/windows-valid-content.patch` SHA `030f1014195c5d311efe34426eae356ed3753372ceda19b36d01c4e0405d9ec7`，3文件preimage/副本/patch摘要均核实。复制环境C++20/UBSan211检查、完整GTest TU语法及apply-check过；**未应用到仓库、未编译Windows分支或运行WGC**。Content1026×729与DWM相同、pool1040×736与WindowRect相同，不证明候选像素原点。 |

本轮不新增产品UI点击验收。AOCI认知交付和Challenge已核验，但当前Guide因 `tests/test_control_federation.py` 最后指纹变化要求Observed复核，正式语义仍8 missing/13 stale；收尾调用结果保存在transfer目录，不能声称治理已对齐。完整交付、模型准入/桌面授权、P4双平台、S4其他网络产品、S5/S6/P5-S7仍待后续；三待决不擅选，PET专项后置。当前清单见 [handoff.md](../handoff.md)。

## 2026-10-30：S4实际出站网络与Runtime训练（历史进度，当前状态见上）

证据根 `NETWORK_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-network-20261030`。基线38a9fd43，当前新业务仍未提交/push；测试KEY空/MODELunset，无收费请求、无端点/密钥/网络策略修改。

| 范围 | 实际结果 / 限制 |
|---|---|
| 全联邦+Hub联合 | `network-joint-01.xml`，**352/352、零失败/错误/skip，25.99秒**。包含旧230基础、新协议/client/coordinator52、Node/输入/训练42、网络2、Hub26；工作树服务+显式独立安装worker，不冒称最终全包安装。 |
| 真实出站网络 | 三个独立Linux Runtime、三个出站NodeAgent，经真实TCP/WSS及run-scoped blob完成FedAvg/FedProx各两轮（12任务），原身份重开/重复train/collect不重复，逐轮候选与独立逐样本梯度参考1e-13一致。`network-02.xml`为2/2；首次network-01两失败仅测试token长度，保留原证据。全部同机loopback，不是跨站/NAT/TURN或材料有效性。 |
| Hub | `hub/acceptance-summary.json`：3.12所有control76，3.11/3.14新增各26，合计128次零skip；TCP WebSocket断线重派/SSE/配额/跨进程锁/崩溃/撤销竞态；8源码摘要稳定。初始SSE ID/冲突码两失败保留。 |
| Node与worker | `node/candidate-05/summary.json`：实际42/42零skip，三Python便携各33+9另行真实执行；8输入稳定，candidate05 wheel五成员一致但未安装。sourceNode/安装worker来源分开记录，最终全包由package-final补。 |
| 独立审查 | Root协议/client/coordinator52/52；模型替换、collect失败恢复、aggregate_uncertain不重放、私有cache/graph/read及动态reservation反例通过。review保存优化前100job/50对象20,000次读取；优化后精确100次/零逐task HTTP，lostreply过滤保留。两个最终race/perf用例独立2/2、0.14秒。取消先持久意图再Runtime.cancel，防worker合作退出抢成failed；保留旧失败。 |

仅1项Starlette弃用提示。完整Python回归、最终全包安装/真实worker绑定及本批AOCI/暂存扫描/提交/push仍待完成，旧4467回归不覆盖新增源。独立算法CI要求全部联合零skip，精确4个f32/f64×策略训练与2个network；基础环境前后无flwr。当前同38a9fd43 Desktop41097301277最近18:00:31 UTC为queued/conclusion null，仍非终态，push门未完成。

本批后端无新增产品UI点击，桌面同意/撤回/审计与模型准入仍需UI验收；公共work只含净化回执。512MiB为私有原始bundle总预算，元数据单项/数量另限，不声称整个私有目录总量512MiB。P4目标平台与S4其他产品/跨站能力及后续路线仍未完成；已保存handoff快照继续保留作历史。

## 2026-10-30：转交验证边界（历史，38a9fd43）

本次为所有者要求的handoff，已停止实现/轮询，仅核Git/源码/证据/CI，未运行新测试或产品UI动作，无新增点击验收、提交或push。基础源码11844b25、记录/AOCI头38a9fd43均已推送；本地HEAD、origin/main及真实远端一致。当前8个联邦网络业务文件为未验证WIP，未语法检查、新HTTP/WSS、真实Runtime/隔离安装或端到端多轮测试；旧完整Python4467/31/2、独立230/230、本机pipe六轮和Linux69仅绑定上一批范围。

17:42 UTC直接GET同head/attempt1工作流： [Runtime41097301247](https://github.com/sijintech/stk/actions/runs/41097301247) completed/success、10/10jobs；其独立Flower实际230/230零skip，真实f32/f64通过，Windows3.11/3.12成功。 [Desktop41097301277](https://github.com/sijintech/stk/actions/runs/41097301277)仍in_progress/conclusion=null，前代码头整个Desktop尚未终态，后续代码push等待门不满足。Docs41097301182/Secret41097301195/Dependency41097311540已观察success，均不覆盖WIP。17:35 agent快照和Flower XML证据在 `/home/mnemora/.local/state/stk-validation/s4-network-20261030/ci-38a/`；8文件SHA绑定为该network根的 `handoff-source-snapshot.json`。

接手的文件清单、风险、接口和验收顺序见 [handoff.md当前首节](../handoff.md)。训练身份先持久化、status不重训/collect才发送、私有dataset/base/delta不进入通用Runtime文件树、独立FL CAS无普通CAS旁路、取消和撤销不冒充终态，均须实际验证。AOCI当前dirty/stale，新WIP最终稳定后统一维护；旧Observed8/17条已闭合不重复。本次无新Apply/Recovery。P4/S4及S5–S7仍未完成，不改模型端点/密钥/网络策略，无收费模型请求。

## 2026-10-30：联邦基础最终源码验证（历史，11844b25）

源码 `11844b257e3a88f0db1e08611624a295e64b13c2` 已本地提交。证据根沿用下文 FLOWER_EVIDENCE/PEER_EVIDENCE；本批实际记录提交、AOCI/最终包/push及新CI由 `FLOWER_EVIDENCE/delivery-closure-summary.json` 记录，不从旧交接措辞推定。

| 项目 | 实际结果 / 源绑定 |
|---|---|
| 完整Python首次 | 4467通过/31跳过/2排除、0失败/错误，pytest802.62秒、driver805.655秒；873输入pre/post一致。manifest SHA `d71272217415a15f56a69729f2eb28b5b6000c09e89230cc3ed04a9bd8f740de`。`PEER_EVIDENCE/p4-ci-bccb/integration-next/python-full/summary.json`。 |
| 新核心范围 | full中updates150/consent43/flower37共230、peer202、两个watchdog测试实际通过，均无对应skip。另candidate-01隔离联合230/230，真实f32/f64 2/2，六federation成员的候选/安装/工作树SHA一致，worker实际来源独立site-packages；`production-adapter/candidate-01/acceptance-summary.json`。 |
| 三节点多轮 | `production-adapter/multiround-02/summary.json`：三真实ClientApp PID3434122/3434123/3434124，各训练6次；18训练更新先owner审计再显式发送，6次生产隔离FedAvg与独立moment-gradient oracle 1e-13一致，最终[1.951042873829253,-0.9949775733564108]。撤回阻发送/少于3拒绝、不确定发送仅一次且重开审计保留。只用本机anonymous pipes，不是STK认证出站网络验收；原01脚本误用分页键失败保留。 |
| Windows fixture | authority closing三版本各21/21；watchdog三版本各4/4零跳过，旧1.25秒慢暂存复现入队前超时，新测试真实lane acquire失败后才推进同一秒；另测暂存预算仍含在内，误杀active child负控精确失败。生产文件未改；`p4-ci-bccb/analysis-watchdog/summary.json`。 |
| 原生候选 | 最终Linux all退出0，69/69相关CPU零跳过，4文件SHA稳定；`p4-ci-bccb/native-next-final-summary.json`。Cocoa显式激活请求+循环确认，键门禁不变；HTML decoded布局经真实divider且保原nav/暂停时间/!seeking，完整元素门槛不变。WGC仅补数值诊断，尺寸差仍失败。Linux不编Cocoa/Win32、不执行该原生媒体路径，20轮OS证据待新平台CI。 |
| CI与源码扫描 | 独立Flower job YAML/三段bash/内嵌Python语法、230项真实XML门禁通过；精确要求f32/f64、零skip、主环境无flwr。源码163597字节gitleaks8.30.1/.gitleaks.toml脱敏零发现；不覆盖后来记录/AOCI。 |

31skip分类为15离屏探针child SIG11、7 Windows专用、4可选PySide6/MCP、3真实MuFerro环境、2性能opt-in。原15离屏按JUnit精确选取，私有Xvfb/llvmpipe LLVM21.1.8、VTK9.7.0下首次补验15/15、零跳过，25.84秒；873输入与full同SHA，源码/golden及原full证据未变，结果单列于 `p4-ci-bccb/integration-next/render-followup/summary.json`，不修改原full31skip或声称硬件验收。原有Starlette弃用提示1项不影响退出0。新S4无产品UI表单，点击数不适用；native测试会记录实际初始客户区、布局拖动/点击和最终Viewer/草稿状态，本机CPU不能生成目标OS点击验收结论。KEY空、MODELunset，无收费请求，未改产品端点/网络策略。

前头bccb32d7 Desktop41082221172和Runtime41082221295均completed/failure，Docs41082221284/Secret41082221188成功；原失败细节保留下文。仅证明前头push等待门满足，不证明11844b25的Mac/Windows候选已通过。S4真实STK网络/Runtime训练、桌面同意/准入及完整P4仍待完成。

## 2026-10-30：转交时的实际验证与未验证项（历史）

当前本地和远端 main 为 `bccb32d7`；新 federation 模块/测试/指南及 SQLite fixture 修正尚未提交。本次仅核已有 JUnit、源码摘要、构建/安装日志和 CI 快照并保存交接，未重新执行测试或产品 UI 操作；无新增点击验收。

证据根 `FLOWER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-flower-20261030`：`admission/summary.json` 为三 Python 各 150/150，`consent/summary.json` 各 43/43，均零跳过且源稳定；`foundation-layout-bound.xml` 为便携联合 228 通过，两个真实 Flower 用例另行排除，尚未运行。`production-adapter/candidate-01/build-summary.json` 证明离线 wheel/sdist 构建、输入稳定及六个 federation 成员一致，wheel SHA `35f7aad0c73b1fb2bff2c77b9b61d948c295da8985b8c0c4604445e7bb089d68`；install/pip-check 日志证明该 wheel 已装入新隔离环境、59 包兼容，不证明真实聚合或最终安装回归。原 algorithm-probe 的三节点六轮是独立框架研究，不是新 consent/outbox 或真实 STK 出站网络验收。

`PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030`：`p4-ci-bccb/authority-backup-close/summary.json` 为未提交 SQLite fixture 修正三版本各 21/21，零跳过，不冒充 Windows 已验。`p4-ci-bccb/agent-live-ci-summary.json` 保存 bccb32d7 最新 CI 和失败原日志：

| 工作流 | 实际终态与限制 |
|---|---|
| [Desktop 41082221172](https://github.com/sijintech/stk/actions/runs/41082221172) | completed/failure，2026-10-30 16:23:11 UTC 结束；Windows CPU、Linux 主回归/包/smoke 成功，Mac/Windows native 失败；前代码头推送等待门满足。 |
| Mac native | Markdown/HTML/PDF/spike 通过；video 在 `reports_native_input_cocoa.mm:150` 精确 key-window 检查失败，HTML-video 在 `reports_native_window.cc:435` 完整媒体 viewport 检查失败。旧 pause_failed 未再报不代表视频通过。 |
| Windows native | 六项均 0 完整轮/0 验收图；前五项在 `window_evidence_win32.cc:363` frame.ContentSize 与 item.Size 不符，实际差值未知；HTML-video 同 viewport 检查失败。 |
| [Runtime 41082221295](https://github.com/sijintech/stk/actions/runs/41082221295) | completed/failure，7/9 job 成功；Windows 3.11 为 1 failed/3670 passed，3.12 为 2 failed/3669 passed，两者各 168 skipped/327 deselected。两版本有 backup 句柄失败；3.12 另有 queued.wait(2) 失败，MAX_SECONDS=1 的 staging/watchdog 时序待证实和修复，不据日志猜根因。 |
| [Docs 41082221284](https://github.com/sijintech/stk/actions/runs/41082221284)、[Secret 41082221188](https://github.com/sijintech/stk/actions/runs/41082221188) | success；Dependency Graph 41082235142 success。 |

下一 Agent 的明确命令和顺序见 [handoff.md 最新首节](../handoff.md)。当前 WIP 的真实 worker、完整回归/安装来源、平台门槛、AOCI 最终维护、暂存密钥扫描及提交/push 尚未闭合；旧 peer 的对齐和扫描不覆盖新 WIP。没有新产品模型请求，不改端点或网络策略，S4/P4 均不标完成。

2026-10-30续接收尾：先前handoff检查点的未推送/未维护状态是当时快照。记录提交、push、暂存扫描、AOCI完整批次与Verify/Check/Guide及新CI实际状态统一写入下述证据根的 `delivery-closure-summary.json`；未成功步骤不视为通过。最终文档包以 `peer/package-check/final-summary.json` 的成员比对绑定已安装测试候选，不额外声称重跑安装203项。

## 2026-10-30：S4本机端点与平台补修（代码51a795b9）

已推送基线`cfb8c56136ddab92c3a3179d812d99b20eb592f0`；本批代码`51a795b9d09610f0bec31b526612cf849c230793`已提交，状态文档与AOCI随同批收尾。证据根 `PEER_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-peer-20261030/`，以下路径相对该根。测试key空、model unset，无收费模型请求。peer原型不放开本地stdio桥或Linux Runtime监听。

| 验证 | 实际结果和范围 | 证据 |
|---|---|---|
| 最终端点/协议 | 47+94=141/141，35.433秒，0失败/错误/跳过，14文件和helper摘要稳定；真实UDP/TCP/IPv6、7.55MiB分页、授权撤销/CAS、lost-reply后重连原回执 | `endpoint/summary.json` |
| 原生transport | 12/12，0跳过，8.110秒、源码稳定；真实双向16MiB控制包与64KiB/空blob、实际选路、指纹篡改、分片停滞/慢滴绝对截止；不是跨机器穿透 | `transport/summary.json` |
| 三Python语义/安装前置 | 3.11.16/3.12.14/3.14.4各143/143，合计429/429零跳过；真实crypto50.0.2/Ed25519、fresh venv依赖检查和隔离导入，17文件SHA稳定 | `peer/matrix/summary.json` |
| 首次联合失败 | 198项中40失败；helper因缺libnice.so.10在协议前退出127，源码稳定，保留日志；不解释为认证或网络失败 | `p4-ci-cfb8/integration/peer-combined-summary.json` |
| ACK修正前联合 | 补齐已知开发运行库路径后198/198、0失败/错误/跳过，43.191秒，源码稳定；不改失败原结果 | `p4-ci-cfb8/integration/peer-combined-final-summary.json` |
| Linux统一增量构建 | all退出0、10.586秒，1344输入SHA稳定；Mac引用捕获补修后再次all为no work，不代表Cocoa或Win32编译 | `p4-ci-cfb8/integration/native-build-summary.json` |
| 最终相关CPU | DocumentResources/DocumentEvidence/NativeMediaProbe/ReportDocumentHost共65/65，0失败/错误/跳过，0.369秒、源码稳定；含3暂停时序/截止/代次及4几何边界 | `p4-ci-cfb8/integration/native-focused-final-summary.json` |
| Windows几何独立探针 | C++20+UBSan编译/执行退出0；真实[-8,0]完整原点裁client到1024×697、错1像素、DPI/包含/负原点/overflow等；不代Windows实际capture | `p4-ci-cfb8/windows-fix/summary.json` |
| Runtime字段验证隔离 | 最终6/6，4.48秒、0跳过、六文件SHA稳定；正例先通过，field坏值保持mean/min/max仍拒绝；真实science绘图与Runtime两次simulate扫描另实做 | `p4-ci-cfb8/runtime-acceptance/final.json` |
| peer指南 | 三段示例以真实helper/临时签名callback/单向grant完成auth/start/catalog/apply/read/get，revision1/receipt一致；38相对链接核对 | `peer/docs/summary.json` |
| 完整Python首轮 | 4231通过/31跳过/2排除、1失败，801.099秒、786输入SHA稳定；唯一失败为transport说明包含desktop路径触发既有MIT边界检查。仅改说明后原测试1/1通过；最终ACK语义修正另验，不冒称此轮全绿 | `p4-ci-cfb8/integration/python-full-*` |
| 最终业务候选独立安装 | fresh离线wheel[peer,test]，202 peer+1安装源码许可边界=203/203，45.582秒（wall46.470），零失败/错误/跳过；551份py/Schema一致，112模块实际来源均在site，465份安装suan源码非空扫描；源码/二进制SHA稳定 | `peer/package-check/final-1/summary.json` |

开发helper需要`transport/install/lib`和`transport/deps/usr/lib/x86_64-linux-gnu`两段动态库搜索路径；直接no-input启动曾退出127且stderr明确libnice缺失。新指南给出ldd前置和显式环境，Python wheel不携带网络库/helper；三平台依赖/许可闭包和干净机安装未验。

[cfb8 Desktop41001132256](https://github.com/sijintech/stk/actions/runs/41001132256)已终态failure；Linux主回归123885530312、包123885530466、fresh smoke123888346084和WindowsCPU123885530399成功。Mac123885530110编译/CPU/Metal成功、原生静态和spike通过、两个视频失败；video固定诊断live0/ready0/session_matches1/session_active0/nav_matches0/view_matches0/status3/reason=pause_failed，html-video为state_released。此处没有下载本头大图片artifact，不把旧70449的20轮/440图数字移来。Windowsnative123898637995六项失败、均0完整轮/0图。

Windows WGC item1040×736精确等于GetWindowRect[-8,0,1032,736]，而DWM[-1,0,1025,729]为1026×729；client[0,31,1024,728]。修正只接受这两个精确有依据的原点，追加物理per-monitor DPI及捕获期间矩形稳定再核，保留边长、像素、alpha、20轮门禁；没有任意border容差或桌面/GDI回退。鼠标三条local PostMessage只声明enqueue，后续DOM/OS图片仍须消费证明。独立review未发现几何/溢出问题，实际Win32编译与20轮仍待新CI。[GetWindowRect文档](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect)、[PostMessage语义](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postmessagew)。

Mac暂停候选仍只发一次公共pause命令；从原请求开始绝对1秒，每25ms至多一个查询，ACK/查询无回调也关闭，Playing不算成功。回调绑定media/nav代次与WK实例、State/WK弱持有；独立审查发现本批异步Block捕获shared_ptr引用会悬空，已按值传入修正。CPU只验证等待/截止/过期交错，不声称Cocoa已编译或实际失败根因已复现。上游WebPage在corePage暂停调用返回后ACK，并另提供状态请求；允许状态收敛是本批候选判断，不等于证明CI使用的WebKit版本存在同类延迟。[WebKit调用](https://github.com/WebKit/WebKit/blob/main/Source/WebKit/WebProcess/WebPage/WebPage.cpp)、[Clang Blocks引用规则](https://clang.llvm.org/docs/BlockLanguageSpec.html#c-extensions)。

[Runtime41001132201](https://github.com/sijintech/stk/actions/runs/41001132201)7/8成功，仅Windows3.12 job123885529841在test_incorrect_field_is_rejected_even_when_summary_is_correct的simulate子进程communicate超时20秒，未到独立验证断言。历史日志没有子进程栈，不能锁定字体或DLL原因；Linux真实cold-MPL探针1.035秒成功。测试隔离只消除与无关完整绘图启动的耦合，不增加超时、不skip、不改simulate生产代码。Docs41001132275、Secret41001132164已终态成功。

本批暂无新产品UI操作，点击数不适用；沿用既有Viewer/隐藏稿/明确保存运行发送约束。S4仍缺配对/持久身份、部署信令、显式IPv6→UDP（端口预测）→TCP→TURN443、授权文件传输、Flower；最终规范复核还发现accepted挑战对象与规范相反，同实现两端互通会相消；现发送本机已验证挑战、接收核对自己签过的对方挑战，两行修正完成。独立规范对端不复用PeerEndpoint/authcodec，两个role互操作及signed_instead/unrelated错ACK共4项修前全失败、修后全通过，原红绿保留于endpoint/ack-handshake-*；最终141与安装203覆盖修正，不沿用旧137/198冒充最终。Mac/Windows及P4完整验收未完成。九Observed路径已独立审查并核精确SHA，ack事务`74f56c840c267cc396c4732d`已Apply；正式语义维护与Verify/Check/Guide、最终推送/新CI以`PEER_EVIDENCE/delivery-closure-summary.json`和真实Git为准，资产对齐不代替当前模型完整认知可靠。

已测业务候选wheel为48040887字节/668成员，SHA `84f43861d15260b5dd93a87d5642280d43d4dfc278a61e1edb3045fa4de6ad23`；sdist49086107字节/961成员，SHA `8b98e9937ccdbfc925efc7c7baf3030fb2319522cd5ee664346fd1004bed4b3f`，含peer指南。551口径为suan465 py+12 schema、toolkits47 py、stk_data13 py、structure_generator14 py；旧471为suan旧口径，不能直接作功能增量。与ACK修正前候选相比wheel仅endpoint.py、transport.py说明及RECORD变化，665成员相同；sdist新增指南、6项明确源码/规范/测试/声明/验收变化、954成员相同。最终文档版按`peer/package-check/final-summary.json`与该已测候选逐成员对比绑定，不宣称最终版另跑过安装203。源码暂存294782字节，gitleaks8.30.1/.gitleaks.toml脱敏扫描零发现。

## 2026-10-30：格式15原子回执本机验收与平台精确取证

本地HEAD/格式15源码 `59f4cdc3e7bc9ca7c29a3bc75621b0152a3b377e`；Windows发现修正`e0139d9f`和Mac诊断`04aab01c`已本地提交，格式15源码也已本地提交；此为源码提交后的交付快照，新头推送/CI以真实Git及收尾机器证据核对。证据根 `EDIT_EVIDENCE=/home/mnemora/.local/state/stk-validation/s4-foundation-20261029/edit-operations/`；平台根同上级 `p4-ci-70449/`。测试key空、model unset，无收费模型请求。

| 验证 | 实际结果/范围 | 证据 |
|---|---|---|
| 核心最后精准回归 | 3.12 78/78、2.20秒；3.11/3.14恢复各15/15、1.43/1.46秒；零失败/错误/跳过、四文件前后SHA一致 | `final-lstat-py312/311/314.{xml,log,json}` |
| 真实崩溃落盘 | 800命令/138558字节请求，cache_size5/cache_spill ON，hot journal及未提交脏页真实存在；正常fresh/既有Store读取恢复到byte-for-byte baseline、rev/table/history均0、无回执；提交后退出对照rev1/800表/1history/有回执 | `core-spill-probe/run-e23cf2fcce074bb0b58b62e0a9c73ffe/summary.json` |
| 桥/API | 3.12扩大54/54、3.11/3.14各18/18，包含升级Schema修正，零跳过；早于最后恢复修复，后者另由核心及新安装测试覆盖 | `bridge-summary.json` |
| 新恢复候选安装 | 独立Python3.12.14、20缓存依赖、无Torch，78核心+18桥96/96、零跳过，6.95秒；471份安装py/Schema一致，真实桥111模块及worker9模块来源来自安装目录 | `package-check/recovery-business-candidate-summary.json` |
| 新候选构建 | 离线build退出0/10.072秒，764源pre/post/验证结束一致；与旧81候选wheel仅store/RECORD变，sdist另核心测试/规范变 | 同上；旧81候选不覆盖此恢复版本 |
| 平台修正后Linux构建 | 全目标增量退出0、17.066秒、输入稳定；不代表Cocoa/Windows实际编译 | `platform-final-build-summary.json` |
| 最终完整Python | 4034通过/31跳过/2排除、零失败、既有Starlette提示1项，779.39秒；wrapper783.015秒、source_stable=true | `final-python-full.xml/log/summary.json` |
| 首轮完整原生 | 2020/2022、2失败/零错误/零跳过，486.74秒，source_stable=true；两个旧格式升级夹具漏删新表已修，原结果保留；新增真实桥回执/重启用例通过，最终已另跑通过 | `final-native-full.xml/log/summary.json` |
| 最终完整原生/必跑 | 2022/2022、零失败/错误/跳过、483.82秒（wrapper483.895）、source_stable=true；当前工作流全部必跑退出0、1546项匹配、25.256秒 | `verified-native-full.xml/log/summary.json`、`required-current-summary.json` |

新候选wheel 48018135字节/662成员，SHA `2f5bcd74cf1a1c7a98c15ffc11773094f4c5198531b2c1d9ecc4b34b5a788268`；sdist 49026410字节/948成员，SHA `b39ccf0eb8a1b7c310d5140fbef88a011632625d706506dec637a2b1d6d69aac`。产物在 `package-check/recovery-business-candidate/recovery-business-candidate-dist/`，最终文档版由`package-check/final-summary.json`的全成员比对绑定该已测96项候选，不声称额外运行过最终版安装测试。

[70449dc Desktop40973399539](https://github.com/sijintech/stk/actions/runs/40973399539)已终态失败。Windows CPU job123795443006在GoogleTest构建后发现命令失败，可执行文件已链接；双标签拆平为错误属性，连带TIMEOUT/环境设置错配。修正仅将双标签移到发现后的TEST_INCLUDE_FILES，官方3.31.6模块和本机4.2.3独立元数据均证明22/22双标签、120秒、空key/model unset、CPU选择22/22；不替代真实Windows实测。原日志SHA `f6e7e1e52ca17a393576a5a6e60d42d94e9abf5e0f60e565ed801f1fff1d7745`，`windows-build/fix-summary.json`绑定源码及补丁。

Mac job123795443025编译/CPU/Metal成功；原生6项中Markdown、HTML、PDF和独立spike通过，video/html-video失败。artifact12943950957的339193673字节ZIP SHA `cd138c07427e81fd7dc602475fbdb898da3600b8f43d43db71bfb0140d95356f`与GitHub API digest一致。三静态格式各20轮、140/140/160张验收图，全440张记录均核实际PNG SHA，root目视三格式最终图；均保留Viewer/隐藏Python稿。固定1024×653实际client、默认a3 Reports/Python和旁侧Viewer、一次记录的行splitter拖动起点，选择报告/预览共2点击；20轮还有隐藏、移位、滚动、关闭与重新准备动作，其实际事件由result.json记录，不能把2点击当全部轮次操作数。

两个视频result均初始暂停保持一次、原生点击播放一次，实际time推进到约0.10/0.14秒、ready_state4、320×180、duration6；随后Pause附近probe身份guard拒绝，各0完整轮/0验收图。不再误记为首个probe失败；当前证据不足以区分暂停失败、状态报告或其他关闭路径。源码只在原guard失败时加布尔状态、status和固定原因枚举，不输出URL/DOM/项目内容，不重试、移除guard或放宽门禁；仍待新Mac CI。详情 `macos-native/artifact-evidence-summary.json` 及提取的五份result.json。Windowsnative123806568349因上游失败skipped，Linux三job成功。Runtime40973399517八job、Docs40973399507、Secret40973399529成功；前头Desktop推送等待条件已满足，但整个平台交付未完成。

格式15回执规范见[项目编辑操作](specs/project-edit-operations-1.md)，这不是peer端点、授权或网络恰好一次交付。P4视频及第5–8项继续，PET新专项和三项所有者待决不改变。本批源码与记录最终稳定后统一维护AOCI，机器Apply/Verify/Check/Guide和发行收尾绑定见`delivery-closure-summary.json`；资产对齐不代替当前模型完整认知可靠性。

## 2026-10-29：S3交付闭环与Hub上传幂等修复

S3记录/认知交付`70449dc15ed0635014f8bc66924bc7af123f0a8a`已推送。32条语义按13/12/7三批Apply，最终1105条，Verify/Check退出0、Guide complete=true/next_action=none，无未决事务、Recovery或第三方冲突。暂存141405字节gitleaks零发现。完整交付证明在S3证据根`delivery-closure-summary.json`；此前失败的Overview链保留，新链完整1102条/23块、约156129 tokens、Challenge10/10通过，随后索引身份已变，资产对齐与模型完整认知可靠性分开。

后续修复源码`e5cea387f048f937eb643a69bba11d81363d83d3`只把Hub导入预算检查临时变量改为import_request，避免覆盖upload.start原始幂等请求。证据根`/home/mnemora/.local/state/stk-validation/s4-foundation-20261029/hub-idempotency/`，源摘要与结果见`summary.json`。

| 验证 | 实际结果 |
|---|---|
| 修前独立复现 | 16组合中Hub8个均误冲突，Runtime8个正常 |
| 修前扩展回归 | 23项10失败/13通过，0错误/跳过；真实Hub新增key链另1项失败，原XML/log保留 |
| 修后Python3.12 | 四个传输/Hub/Runtime相关文件49/49，0失败/错误/跳过，35.712秒 |
| 修后Python3.11/3.14 | 确定性各23/23，0失败/错误/跳过，0.210/0.214秒 |
| 源与扫描 | 三文件SHA与已测summary一致，diff检查通过，暂存12404字节gitleaks零发现 |

覆盖文件/目录与remote原写法、六状态及重启相同ID不再launch、四并发一次launch、变参冲突、导入预算先拒绝；真实Hub使用2MiB+321字节，分块失败后原offset续传，经审阅、桥重启和批准仅生成一次import，下载SHA一致。旧错误journal已丢原始remote意图，不能由规范化路径猜回；同key保留conflict，已有transfer ID仍可查询/恢复。不修改原协议，不扩展权限。本机Linux执行，不把多Python版本当Mac/Windows实测；S3发行包证明绑定70449dc业务，未声明该包包含后续传输补修。

当前[Desktop40973399539](https://github.com/sijintech/stk/actions/runs/40973399539)的Linux主回归、Linux包、Mac和Windows四job均已进入构建但未结束；[Runtime40973399517](https://github.com/sijintech/stk/actions/runs/40973399517)的control/web/desktop成功，其余五job仍运行。Secret40973399529成功；这是修复本地提交时的查询快照，完整摘要为`desktop-ci-at-local-fix.json`、`runtime-ci-at-local-fix.json`。Desktop终态前不推送后续代码；无新Mac/Win原生通过声明。四份状态记录与AOCI按本批最终稳定源另行收尾，P4及第5–8项继续，PET新专项后置；测试key空/model unset，无收费模型请求。

## 2026-10-29：S3b本机验收完成与平台补修待复验

本轮基线main `9da98ea1aabf129e3f4b8740a1d80698fdde568d`；平台修复`d64023ce`、S3后端`fca7fcf0`、registry预算`99bea12b`、Windows诊断`62984f28`、桌面页`384c16bb`和最终布局补修`c236816a6a67520b816754aa091b06b90f81c051`构成本批源码；状态记录与认知资产同批收尾，新交付头CI待核。S3证据根为 `/home/mnemora/.local/state/stk-validation/s3-training-20261029/`。

| 验证范围 | 实际结果 | 证据 |
|---|---|---|
| 冻结输入与真实CPU训练 | 95+20=115通过，无跳过；Torch2.14.1，权重初始化/normalization、同留出集与最多3个真实test曲线独立核对 | `inputs-training-preview.xml` |
| 后端/API联合 | 198通过、零失败/错误/跳过、29.76秒；含旧接口、Schema、agent工具权限 | `materials-integrated-final.xml` |
| 最后登记读保护 | 服务35、旧接口11、API35，共81通过、26.82秒；登记公开读与发布共用跨进程锁 | `materials-registry-final.xml` |
| 最后registry预算保护 | 服务37、旧接口11、API35，共83通过、28.20秒；拒绝发布超过自身16MiB/10000版本读取预算的registry，原文件不变 | `materials-final-budget.xml` |
| 完整Python | 3911通过、31跳过、2排除、零失败、1项既有Starlette提示，748.98秒；早于最后登记读保护小修，后者由上述81项覆盖 | `python-full.log`、`python-full.xml` |
| 3.11.16/3.14.4材料相关矩阵 | 各199项收集，182通过/17项因未装Torch跳过，8.97/9.23秒；其余冻结与持久任务实际执行 | `materials-py311.xml`、`materials-py314.xml` |
| 同一capsule跨版本 | 3.12真实CPU生成base/baseline并冻结，3.11/3.14对同实体verify/load，摘要、精确ID划分和7文件前后字节全同；两probe均未加载Torch | `capsule-cross-version/` |
| bootstrap隔离wheel | 五材料文件196/196、零跳过，35.96秒；独立Python3.12.14/Torch2.14.1+cpu，全部suan origin位于安装site-packages，470份py/schema逐字节一致 | `package-check/bootstrap-summary.json` |
| 预算补修后业务候选安装 | 五文件198/198（95+20+37+11+35）、零失败/错误/跳过，35.70秒；真实卸旧wheel再装候选，独立-I进程、清PYTHONPATH、所有suan origin在安装路径 | `package-check/business-candidate-summary.json` |
| 新桌面定向 | 30/30，零失败/跳过，25.78秒；22状态/真实事件+8 OpenGL/Vulkan中英宽窄GPU案例，16实际PNG，绘制/图例/裁剪已目视 | `materials-native-focused.xml`、`renderer-proof/` |
| 首次完整原生 | 2016/2021通过、5失败、零跳过，480.74秒；为17→18编辑器数量旧断言及新英文标题撑宽旧布局 | `native-full.xml`、`.log` |
| 布局补修定向 | 39/39，零失败/跳过，18.43秒；保原golden，入口缩为Materials，登记校验扩为18 | `materials-layout-final.xml` |
| 最终完整原生 | 最终统一构建退出0；2021/2021，零失败/错误/跳过，481.20秒 | `native-final-full.xml`、`.log`、`native-final-full-summary.json` |
| 最终Linux必跑 | 从当前desktop.yml真实步骤提取，413次核验/1545匹配、无BAD/缺项/跳过 | `required-current.sh`、`.log` |
| 最后预算跨版本 | Python3.11.16/3.14.4的jobs文件各37通过、无跳过，3.56/3.67秒 | `materials-jobs-budget-py311.xml`、`-py314.xml` |
| 原15个离屏skip补验 | 私有Xvfb+已有软件GL下15通过/0跳过/22排除，27.85秒，golden未改；不改写原full31skip | `render-diagnostics/xvfb-render-15.xml`、`render-environment-summary.json` |

完整Python的31跳过分为：7项仅Windows真实junction/原子generation门禁、15项离屏渲染probe子进程SIG11、2项性能基准、2项缺PySide6、2项可选MCP、3项未指定真实MuFerro前缀。15个离屏用例已在私有Xvfb补验全过，原full跳过计数不改写。隔离包比较绑定757份发行源构建pre/post一致、458份Python/12份Schema及284项声明文件；bootstrap包wheel SHA `396beef6d7380ffbad483e0f5979a627d383724bc769beb12f4cad39f960bc56`、sdist SHA `f20e59aa856f14bf82062c5acebc166542e53d66b045deaae5f40c1e4be4cec4`，不是后续文档最终包。初次外部verifier误要求未声明design指南，原失败保留；只修验证器后同一包通过，未改发行声明。

后续业务候选已实际验证预算补修：761份源（包含冻结五docs）构建前后及安装测试结束一致；470份安装py/schema、196份sdist测试文件与对应产物逐字节一致。候选wheel SHA `4a7fc5c7de8486700f0f73e1cc4bd86ab2be836d6692d976b0bbb641c6fab935`、sdist SHA `07c6b86ef4bbb6a1f7fec5d83c292b4d7793a2d50a2242d1a308df78035278fe`，明确不是最终文档版SHA。最终文档版的产物身份及全成员比较由`package-check/final-summary.json`记录；业务Python/Schema/测试须与这份已测试198项候选完全相同，仅批准的交付文档可变，不重复声明未运行的安装测试。

持久任务/逐epoch曲线、冻结输入删除live后重放、同ID不重训、跨服务取消/互斥、active generation CAS、基准变差拒绝、发布前后崩溃、孤儿版本不复用、已发布缺证据持久uncertain及明确回退后恢复不重激活均有专项反例。只在明确start后加载Torch训练；prepare、读、重开和recover不训练。行级划分不证明材料/批次独立性，旧base可能见过重叠样本，合成曲线不作物性结论。合作格式/MuPRO扫描及原三项所有者待决均未改变。

新头[Runtime40957894618](https://github.com/sijintech/stk/actions/runs/40957894618)已结束，6成功/两Windows失败，各3219通过/100跳过/327排除、仅原子generation测试失败。实际栈为`test_atomic_receipt_replacement_yields_one_complete_generation`打开旧回执后`os.replace`报WinError5；共享DELETE reader本已存在，不能重复以加共享flag解释。候选writer改用`SetFileInformationByHandle(FileRenameInfoEx)`与replace/posix flags，窄unsupported回退仍只准原子replace；不unlink/copy降级。最终相关组三版本各95通过/7项仅Windows真实门禁跳过，原失败反例保留，新增实际Windows三旧handle/UTF16测试；POSIX-backed ABI模拟不作实际Windows证据。证据在P4根`current-ci/windows-atomic-final-local-validation.json`与`runtime-failures-diagnosis.json`；真实Windows候选尚未运行。

新头[Desktop40957894690](https://github.com/sijintech/stk/actions/runs/40957894690)已终态失败：Linux主回归在Phase0旧补丁数上限3失败，vendor1095/1095已过；同步4后本机同一步vendor1095/1095、patches4/4、shims620/800、forbidden0/0通过（`phase0-patch-budget.log`）。Linux包/干净机及Windows主回归成功；Mac Build的NSString引用ownership错误已显式strong，本机仅源码/静态核验。Windows独立native123763562850六项均0轮/0图：原型与MD/HTML/PDF被WGC几何条件拒绝，两个video到首轮paused=true/time0后鼠标SendMessageTimeout失败。本头无RIP0异常栈，不能推断所有线程安全已验证；两处精确geometry/error/线程诊断已提交`62984f28`，未改任何几何/crop/2秒timeout门。前头Desktop推送等待门已满足，本批仍待最终验证与新CI，不把未开始的OS门禁或LinuxUnsupported算通过。

桌面实际事件为英文1440×1100/1×、中文1000×1100/1×、英文2160×1650/1.5×、中文2000×2200/2×。各以a4材料页最大化、侧栏560逻辑单位、数据目录和job ID已填、高级参数折叠，既有Viewer与隐藏Python稿为固定起点：校验→冻结→开始3点击，另1点击切到留出曲线；冻结后删除live目录仍完成，重开只读且旧start/activate/晚到get/list不能跨来源生效。OpenGL/Vulkan的8个GPU案例各导出loss与四角色evaluation图，像素校验排除legend色块、逐角色检查跨度和零越界；root实际查看了英文宽evaluation及中文窄loss。GPU输入是经真实服务冻结与登记的受控训练输出，证明生产draw_gpu呈现，不证明Torch精度或材料性质；真实Torch证据由独立20项训练与服务测试承担。

六个源码提交前分别扫描暂存14229/214740/3012/6156/169628/2238字节，均按`.gitleaks.toml`零发现，`*-staged-gitleaks.log`保留实际记录。状态文档和认知资产的扫描另记；本批AOCI对齐以最终Verify/Check/Guide机器结果为准，对齐不等于当前模型完整认知可靠。测试key为空、model unset，没有收费请求。

上下文恢复时AOCI正式链在11/23块后返回snapshot unavailable，已停止且没有旁路补答或重读；当前按真实源码推进，不声称完整认知可靠。本批在源码和状态记录稳定后统一维护，以收尾Verify/Check/Guide证明资产对齐；资产对齐与完整认知可靠性分开。完整目标仍包含P4平台及第5–8项，PET新专项后置。

## 2026-10-29：冻结 MP4 与平台修正（本机验收完成，平台待复验）

基线main为 `f331dbe7b015220a821b8a5f83bbf852a4d19db5`；平台/LaTeX修复 `852860ae53327ae11fec9cb1a459d64f247bc1cd`、MP4源码 `8627d98184af62548a4b23b0d1e41e4f2856f6f3` 已本地提交，四份记录与AOCI随本批收尾，新交付头CI待核。证据根目录为 `/home/mnemora/.local/state/stk-validation/p4-video-20261029/`。

| 验证范围 | 实际结果 | 证据 |
|---|---|---|
| MP4与报告六文件 | Python3.12/3.11/3.14各348通过，无失败/错误/跳过 | `python-final-focused.xml`；`python-report/matrix-{311,314}/junit.xml` |
| 最新完整Python | 3708通过、24跳过、2排除、1项既有Starlette提示，741.88秒；早于最后目录junction补修 | `python-final-full.xml`、`.log` |
| 最后LaTeX目录与读取专项 | 三版本各86通过、6项仅Windows真实junction跳过；Windows上无法创建junction将失败而非跳过 | `latex-junction-{312,311,314}/junit.xml` |
| 原生统一构建 | 探针开关ON的Linux构建已退出0；平台实际SDK仍须新CI | `native-build-probes.log` |
| 原生完整回归 | 1991/1991，零失败/错误/跳过，471.76秒；早于最后路径断言及Windows-only补修 | `native-full.xml`、`.log` |
| Linux必跑与最后定向 | 现行规则405次调用/1515项匹配；增量all构建退出0，最后编译5/5及必跑通过、2.94秒 | `required.log`、`native-final-build.log`、`native-final-compilation.xml` |
| 隔离wheel十文件 | 456通过、6项仅Windows junction跳过，零失败/错误，62.54秒；所有suan导入realpath来自安装site-packages | `package-check/bootstrap-summary.json`、`package-check/installed-test-work/installed-product-tests.xml` |

前头[Desktop40943343333](https://github.com/sijintech/stk/actions/runs/40943343333)六job已全部结束：Linux主回归、包及干净机冒烟成功；Windows CPU仅两项编译定位失败，Mac与Windows独立native失败。[Runtime40943343293](https://github.com/sijintech/stk/actions/runs/40943343293)六job成功、两个Windows客户端失败；Docs40943343346、Secret40943343327成功。前代码头Desktop等待门已满足，失败并未因此闭环。

Windows Runtime的实际日志显示fd/path两种API的ctime语义不同、读句柄阻止原子replace，以及测试以cp1252读取UTF8回执。修正保留同API前后稳定校验、字节/SHA绑定与竞态反例；仅原子记录使用共享删除且不可继承的句柄。另拒绝编译目录各组件的symlink/reparse point并保留新尝试不可重放。CPU两项还比较了不同斜杠写法，测试改为本机路径的词法规范比较，不放宽源码身份。证据 `previous-ci-runtime/`、`previous-ci-desktop/windows/cpu/`；新Windows实际验证尚未完成。

Mac实际Markdown/HTML各20轮140图及独立原型20轮161图成功，PDF首轮首页marker已两次通过，首次滚动前的窗口关联断言失败。实际PNG已查看；按WebKit公开的windowless-local wheel方式修正，仅直投已核自身WKWebView后代，并前后重核整视口、命中与方向，PDF20轮160图门禁未改。证据 `previous-ci-desktop/macos/analysis/diagnosis.json`。关闭页面JS仍允许宿主只读probe的公开契约及固定版本官方回归见同目录 `webkit-host-probe.json`，不以公开源码标签冒充运行系统二进制版本。

Windows原生前头四项均0轮0图崩溃。实际PE导入与反汇编定位epoxy包装层对unwrapped函数的间接空调用，EXE调用结构与GPUSecondaryContext::activate一致；新线程TLS零槽是符合libepoxy1.5.10源码的机制推断，并非运行内存实测。候选修复在生产GHOST七处WGL切换调用系统入口，再以公开API通知epoxy；真实调用失败也通知并恢复LastError，missing module/export不通知。预检三处同样通知，不关闭后台编译或降低GL能力。vendor1095/1095、补丁fuzz0隔离重放逐字节一致、manifest摘要及独立review通过，仍需新Windows编译和OS20轮；不扩称任意未激活线程的创建/析构均安全。证据 `previous-ci-desktop/windows/diagnosis-final.json`、`patch-format-replay-result.json`。

发行bootstrap在独立环境离线构建并安装：456份suan Python与12份Schema、279项sdist声明内容逐字节核验；源码750项构建pre/post一致。十文件462项中456通过、6项仅Windows跳过，安装后468份Python/Schema再次与wheel一致，192个提取测试与sdist字节一致。首次collection因验证目录缺静态preset而失败，日志独立保留；修验证工具使ROOT/suan指向安装site-packages，未提取sdist产品源码或修改测试，实际导入realpath均审计为安装包。最终文档版重建与bootstrap逐成员对照记录在 `package-check/final-stage-comparison.json`，只允许四份状态文档及报告指南两处状态/附件措辞差异，业务Python/Schema/测试不得漂移；不以bootstrap的包SHA代替final。修复源码暂存扫描37921字节、视频源码318957字节，gitleaks按.gitleaks.toml/redact均零发现；记录与认知资产提交前另扫。测试始终key空/modelunset，无收费模型请求。

视频使用41558字节、6秒、红转蓝的公开合成MP4（H.264/AAC）；来源、生成命令和SHA见 `desktop/spike/document_preview/fixtures/README.md`。独立播放器与HTML内视频使用各自会话下的精确MP4 CSP，资源字节全验后才发布；GET单Range、HEAD、206/416及关闭优先410有CPU反例。隐藏暂停、重显不续播和明确播放须两平台新OS证据。默认关闭的只读探针仅返回17个定型测量字段，不采页面文字或路径。

四个CPU鼠标布局为1440×1000/1×中英、900×1000/1×英文与1800×2000/2×中文，固定a4报告区最大化起点：选报告→预览→原文→预览→关闭，共5点击，保留Viewer与隐藏Python/创建草稿。初轮新UI四项仅资产读取计数断言失败，已纠正为准备时核入口加一次明确资产读取，不减少真实校验。原生OS测试每视频格式要求20轮/161张实际窗口图、21个独立session，包含自然播放红转蓝、seek、隐藏暂停、重显不续播与关闭410；当前未获本批平台通过证据。Linux仍Unsupported；P4完整平台/IME/DPI/浏览器内存、S3–S7与toolkits整合继续，PET新专项后置。

## 2026-10-29：LaTeX 工作流、编译证据与原生判据修复

本批源码 `51a01af143496eeaf58b39b4a6547af45e55176d`，项目来源失效补修 `3d4998d613597d93c6da4b7688775a7e854df57a`；均直接 main，最终交付还包含四份状态记录与AOCI托管资产。
`latex-compile/1` 使用已注册的本机工作流步骤，冻结明确选择的编译器与输入Snapshot；只有启动才探测版本和编译。
静态/动态上游、取消/超时、父进程丢失、旧尝试防重放、回执/日志/诊断篡改、历史上游绑定、源码SHA及晚到响应均有定向反例。
编译成功后的PDF/日志正常登记Files并捕获Snapshot，失败证据也可读；不自动保存报告或预览，不注册Viewer自动求值节点。

持久证据根目录：`/home/mnemora/.local/state/stk-validation/latex-20261029/`。中断前的 `/tmp/stk-latex-*` 已清理；下表为重新生成并绑定源码摘要的证据。

| 阶段 | 实际结果 | 证据 |
|---|---|---|
| 冻结主链完整Python | 3644 passed、24 skipped、2 deselected、零失败，803.73秒；1项既有Starlette弃用提示 | `python-full.log`、`source-sha256.json` |
| 冻结主链完整原生 | 1956/1956，零失败/错误/跳过，474.70秒 | `native-full.xml`、`native-full.log`、`native-full-summary.json` |
| 当时现行Linux必跑核对 | 405次调用，1487项匹配，无未跑/跳过 | `required.sh`、`required.log` |
| 最后回执发布修复 | 3.12新专项79/79，37.91秒；3.11为79/79、32.91秒；3.14为79/79、26.11秒 | `python-final-focused.log`、`python311-final.log`、`python314-final.log` |
| 最后原生判据与来源门禁 | 统一构建退出0；最终29/29、零失败/错误/跳过、3.15秒，含19个像素、5个编译、5个文件/布局用例 | `native-scope-build.log`、`native-final-scope.xml`、`native-final-scope.log` |
| 隔离wheel专项 | 79/79，零失败/错误/跳过，47.50秒；全部suan导入仅来自隔离site-packages | `package-check/bootstrap-summary.json` |

全量结果的源码绑定在最后三项小修之前：唯一临时文件发布、缩放色条识别、项目scope意图失效。
这些修改完成后已定向复验；当前目录虽发现1963项，不把29项定向结果写成最终全量通过。
首轮原生新增测试JSON括号错误已修；隔离发行环境首轮漏装NumPy导致21项报错，离线补齐科学依赖NumPy2.5.3后79项通过，
保留初轮证据，未改变共享Python或产品配置。测试均清空 `STK_TOKEN_PLAN_API_KEY` 并unset `STK_TOKEN_PLAN_MODEL`，没有收费模型请求。

### 实际UI事件与冻结来源

固定1440×2200逻辑像素、1×、a3工作流区最大化、侧栏560、已有失败运行详情起点；中英各6次实际ScreenDriver点击：
选行→查看编译→选诊断→源码定位→读取输出→下一页。通过夹具改变原文件后另1点击拒绝过期源码；无键盘事件，
Viewer完整工作空间不变，未创建报告/准备预览/重放执行。覆盖8192字节处中文跨页、旧读取清理、切运行/工作流后拒绝旧定位，
以及服务器仍持有关闭ACK时拒绝旧源码回调。CPU事件路由与像素重放不替代OS/GPU/IME或跨屏DPI验证。

### 真实TeX与发行包

只在持久验证目录下隔离安装TeX Live2026/pdfTeX1.40.29（约148MiB），不改系统PATH或产品设置。
`source-real-tex-v2/verification-summary.json` 记录strict NDJSON真实桥两个进程均exit0：主源+section先freeze、删除live源后明确启动，
实际生成2页PDF（25675字节）；独立pypdf6.21.4解码两页正文。错误文档实际exit1，定位 `section.tex:2`（column=null），
源码SHA回查通过。明确以workflow_run为来源保存Report、删除四个live产物、关闭重开后，PDF和三日志/ZIP仍逐字节一致。

隔离wheel以同样真实链通过，证据 `installed-real-tex-bootstrap-v2/verification-summary.json`；
该次PDF SHA-256 `5d0551d6999538d032873ccdf0c966dac97f8cb0446dad6bc3b3b017b95ded8c`。
发行首批456份Python、12份Schema与279项sdist声明内容逐字节匹配。
状态文档定稿后的最终发行字节结果保存在 `package-check/final-package-verification.json`，
bootstrap/final全wheel成员与sdist变动对照在 `package-check/final-stage-comparison.json`；
两个纯desktop补修不在Python发行包内，最终对照需证明Python/Schema/测试/规范/新指南均未漂移。

### 前推送头CI与剩余边界

前头3ac89623的[Desktop40472799346](https://github.com/sijintech/stk/actions/runs/40472799346)六job全部结束：
Linux主回归/包/干净机冒烟与Windows主回归成功；Mac与Windows独立native失败。
[Runtime40472799376](https://github.com/sijintech/stk/actions/runs/40472799376)8/8、Docs40472799342和Secret40472799351成功。
前头Desktop等待门已满足；本批新头CI仍待核。

Mac正式Markdown/HTML各20轮140张OS图，独立原型20轮161图及最终guarded内存0块/0字节通过。
PDF首轮截图与result.json已恢复并核SHA：client1024×653，viewport[631,200,385,256]，首页实际显示；
13行的6色实段宽20/18/18/18/17/19、1/1/1/2/2px混色边界使旧连续判据拒绝。
已保留不改字节的公开合成PNG为CPU回放，修正仅接受相邻预期色之间最多2px、通道残差≤2且比例单调的过渡；
6色顺序、8行、几何范围、页身份、视口外拒绝及20轮门禁保留。19个CPU正反例通过不能替代新Mac原生20轮。
Windows四项均完成WGL清理后在其他线程RIP0崩溃；旧栈循环在RIP0漏掉所有帧，现仅修有界栈诊断，未证明驱动或窗口调用根因。
证据ZIP与已核截图在 `native-ci/`，公开夹具说明见 `desktop/spike/document_preview/fixtures/README.md`。

尚无XeLaTeX/MiKTeX、Windows Job实际新CI、完整双平台PDF/输入/跨屏DPI/浏览器内存证明；
编译当前为一次引擎执行，尚无BibTeX/Biber或多遍引用收敛自动链。原生候选默认关闭，Linux Unsupported。
视频仍仅技术调查，P4与第4–8项继续，PET新专项后置，不把本批标作整份计划完成。
暂存扫描沿用 `.gitleaks.toml`，feature244987字节零发现，scope小修另行扫描零发现；最后记录/托管资产提交前仍须扫描。
AOCI最终判据由同证据目录的 `aoci-check.json` 与 `aoci-guide.json` 记录；索引对齐不等于本Run完整认知或平台实测通过。

## 2026-10-27：独立桌面报告生成表单（本机验收完成，平台待复验）

交付头 `035f7bd960d0a5b72bc83db7608342e15951ea68` 已推送main，包含报告源码 `15edede3`、运行器 `5a6f6fd1` 和记录/认知资产；记录暂存gitleaks扫描141729bytes、零发现。新[Runtime CI](https://github.com/sijintech/stk/actions/runs/40274892305)已结束：三个LinuxPython版本、desktop、web、control均成功；Windows3.11/3.12各3057通过、100跳过、327排除、2个setup/teardown错误（537.95/558.16秒）。日志明确为 `test_invalid_or_oversized_generated_body_is_rejected_atomically` 的默认案例名称包含整段超长正文，写入 `PYTEST_CURRENT_TEST` 超过Windows环境变量32767字符限制；没有运行到该案例断言，不能写作报告后端验证失败或通过。
修正保留原始大正文与五类拒绝断言，只显式使用简短案例ID；本机3.11/3.12/3.14报告全文件各46项通过（3.68/3.70/3.68秒），日志 `/tmp/stk-report-generation-testids-python311.log`、`python312.log`、`python314.log`，真实Windows仍待下一头CI。新[Desktop CI](https://github.com/sijintech/stk/actions/runs/40274892272)已结束：Linux主回归、Linux包、干净机冒烟及Windows主回归成功；Mac正式报告3项OS像素超时、独立原型20轮161图及最终零分配通过；Windows独立原生4项均在真实llvmpipe4.6预检后0xC0000005退出、零图。Docs `40274892334`、Secret `40274892259`成功。前头Desktop已终态，下一批仍须自己的CI，不能把本机测试作平台通过。

源码 `64205ba809aacef568d1d85637ee777c9ac8aa50` 已提交main，接入独立桌面AI生成表单、每标签局部控制器及workspace v3，普通v1/v2可读。准备、发送、编辑和保存分别明确操作；复用来源选择器，四类来源分页与完整复核、可选真实快照附件，原UUID回查不重发。三处控制器状态缺陷与跨帧/同帧字段提交票据失效已修，按钮继续核原来源及token。
统一构建退出0；专项 **26/26、零失败/错误/跳过、14.96秒**，`/tmp/stk-report-generation-desktop-tickets.xml`，覆盖14项真实stdio桥、丢回执/取消/换项目/重启，以及中英×1440/560宽度的完整UI、8类恶意workspace状态原子拒绝和恢复零隐式读取/发送、无中间frame的连续Tab与问题重入。首轮14中一例在桥自动重开时重复open，修测试等待；UI首轮18/26后修正用Enter事件输入换行，22/26再暴露真实跨帧票据问题，修正后26/26，不隐藏失败。新增CMake使用NO_PRETTY_VALUES与稳定参数名，三平台必跑规则纳入控制器和UI两类。

固定默认Report模式未最大化、a3报告活动、旁有既有Viewer且隐藏Python/AI草稿；中英各1440×1000和560×1000，实际四场景均 **39鼠标点击、14键盘动作、6文本事件、0滚轮、1指针移动**。14键含一次Ctrl+Space最大化，最大化后的流程仍39点击/13键；四来源、PNG、完整复核、选择上下文与端点/模型、准备/单次发送、编辑和保存均计数。结果是实际读回report/2，四类冻结来源和已删除工作副本的冻结PNG、精确编辑正文；一发一保存，无自动asset/preview读取，Viewer payload/相机与隐藏稿内容保留。证据 `/tmp/stk-report-generation-ui-clicks.xml`、`.log`；WM/CPU事件与UI文本路径不等同真实OS/GPU/IME验收。既有AI页面没有独立has_unsaved_changes覆盖，本轮只证明其内容保留，不声称修复该缺口。

Mac验收harness按实际客户区真实拖动分隔条扩大上排并保留Viewer，关闭popup后移开指针等待Tooltip遮挡解除；PDF改两页独立内嵌960×96 RGB图而保持原强像素判据。555033字节PDF由pypdf6.21.2 strict解析，两页、各276480字节图片、精确六色及第二页反序通过，`/tmp/stk-native-pdf-verify.log`；不代替Mac实际显示。Windows仅补WGL生命周期flush阶段与有限异常地址栈，证据只在显式测试目录、无内存dump；本机无Windows编译，真实崩溃位置与修复仍待下轮CI。
最终复核另发现保存成功后等待项目刷新没有遵守90秒跟踪上限，已补齐截止处理：停止唤醒并保留原UUID和编辑正文，后续明确查询仍能确认同一份报告。新增真实桥回归1/1通过（2.47秒），最终统一构建退出0。完整原生 **1951/1951、零失败/错误/跳过、465.52秒**，日志 `/tmp/stk-report-generation-desktop-native-final.log`、JUnit同名`.xml`；包含 **15项控制器＋12项中英宽窄UI，共27项报告生成用例**，全部实际运行通过。当前Linux必跑脚本405次核对、1481项匹配通过，`/tmp/stk-report-generation-ui-required-final.log`。上一轮1950/1950是在这项边界修正前完成，不混作最终结果。中英2522键、零问题，diffcheck通过；源码暂存gitleaks按 `.gitleaks.toml`、redact扫描258612bytes、零发现，`/tmp/stk-report-generation-ui-staged-gitleaks-final.log`。最终wheel/sdist已离线重建（`/tmp/stk-report-generation-ui-package-final.log`）；wheel中452份Python文件与当前源码逐字节一致，sdist中的运行验收、报告指南、报告测试、生成后端及worker五文件逐字节一致，证据 `/tmp/stk-report-generation-ui-package-verify.log`。本批平台CI仍待新头复验；最终记录与认知资产随本批收尾，具体对齐以托管资产及Verify/Check/Guide事实为准。P4的LaTeX、视频、原生平台验收及第4–8项继续，PET新专项后置。

## 2026-10-26：运行器先发布身份再执行（本机完整回归通过）

源码 `5a6f6fd1f6a1f4b66862a649bb29fdf176bcae02` 已本地提交main，尚未推送；报告源码为 `15edede30c46bc6639eeab910d739bf01fdb762b`。所有测试清空模型key、取消model变量，没有模型请求。

- 旧窗口的确定性复现只修改临时任务副本，在Popen后、program.json发布前以握手暂停：父进程丢失后目标仍活、无持久身份，LocalBackend误报failed，日志 `/tmp/stk-worker-loss-repro.log`，已按PID/创建时间清理。前头Runtime3.11日志没有足够身份证据，不能断言同根。
- 新Linux任务先以隔离解释器启动惰性门禁，fsync并原子发布目标PID/创建时间后才授权。TaskSpec环境在授权后经匿名管道传递，避免PYTHONHOME/PYTHONPATH/加载器变量提前作用于门禁；实际exec沿用原argv/env并恢复原Popen信号语义。第二管道以CLOEXEC确认进入目标，排除临时Python门禁RSS和启动耗时；失败exec保留stderr和127。取消/信号在环境传输及exec等待期间仍有效；历史任务副本、Windows直接启动路径不改。保留既有文件fsync+rename，不增设共享文件系统目录fsync要求或断电保证。
- Runtime全文件：3.12 **36 passed/15.17秒**，`/tmp/stk-runtime-launch-gate-full.log`；3.11 **36 passed/15.23秒**、3.14 **36 passed/18.38秒**，对应 `/tmp/stk-runtime-launch-gate-python311.log`、`python314.log`。覆盖发布前杀父/发布失败零执行、已发布程序丢失worker后取消、exec失败、真实native低内存目标、32MiB门禁暂停、取消和SIGTERM、目标环境延迟生效及SIGPIPE。
- 最终worker后的真实桌面/桥Runtime调用链 **4/4、零失败/错误/跳过、35.65秒**，JUnit `/tmp/stk-runtime-launch-gate-native.xml`，包括日志订阅、Jobs上传/提交/下载与关闭存活、逐行仿真及MuFerro工作流。完整原生1924/1924是在报告源码上、此次Runtime修正前完成；相关调用链在修正后补验，不声称重新跑了全部原生。
- `uv build --offline`最终wheel/sdist成功，`/tmp/stk-report-runtime-final-package.log`；安装到全新隔离目录，`python -I`确认报告与worker模块来自安装目录后运行 **82 passed/18.54秒**，`/tmp/stk-report-runtime-final-installed-tests.log`，不回落源码模块。最终完整Python **3562 passed、24 skipped、2 deselected、零失败、1项既有Starlette提示／705.26秒**，日志 `/tmp/stk-report-generation-runtime-final-full-python.log`，退出0。首轮两处发布清单失败已由下节记录，保留失败历史。
- 本次暂存源码gitleaks用 `.gitleaks.toml`、redact扫描 **24861bytes、零发现**，空白检查通过。推送前已fetch确认origin/main无新提交，前头Desktop `40264284403`全部终态，等待门禁满足；本批新CI待推送后核对。
- 新上下文恢复已完整交付AOCI **22块、1085条、约152153tokens**，Host交付确认和严格Challenge **9/10**通过；读取时治理dirty/stale，模型认知可用不等于当前完整系统认知可靠。最终稳定源码的收尾结果由本提交认知资产与Verify/Check/Guide事实承载，不以此替代源码和平台验收。

当前仍须完成独立桌面AI报告表单、LaTeX、视频及双平台原生显示/输入验收；第4–8项继续，PET新专项后置。

## 2026-10-26：报告模式与生成报告后端（本机验收，平台待复验）

源码 `15edede30c46bc6639eeab910d739bf01fdb762b` 已本地提交main，尚未推送。本轮不修改端点、密钥或网络设置；测试清空 `STK_TOKEN_PLAN_API_KEY` 并取消模型变量，生成回复均由受控适配器/本地测试日志提供，没有收费模型请求。完整桌面生成表单仍未交付。

- 构建 `/tmp/stk-report-generation-native-build.log` 退出0；报告/模式/项目范围 **149/149、零失败/错误/跳过、29.81秒**，JUnit `/tmp/stk-report-generation-native-focused.xml`，相关必跑69匹配通过。新增17项/2读取与valid-wire篡改回归、三模式14项实际执行。
- 完整原生 **1924/1924、零失败/错误/跳过、469.57秒**，JUnit `/tmp/stk-report-generation-native-full.xml`。实际执行当前 `.github/workflows/desktop.yml` 的完整Linux必跑脚本，**405次核对、1454项匹配全部通过**；日志及JSON `/tmp/stk-report-generation-native-required.log`、`-summary.json`。新增generation参数化类加入三平台必跑规则。
- 模式点击固定起点：默认分析布局、无桥、**1000×900逻辑像素**，英文/中文×1×/2×。真实鼠标依次准备→报告→分析，每种菜单+菜单项 **2次**，每场6次；报告位于工作区a3，a1Files/a2Viewer/a4Table保留。布局往返恢复，Viewer无新求值、脚本无会话，隐藏Python/报告草稿及相机保留；`WorkModeLayoutClicks`与`WorkModeLayouts`全部通过。CPU事件证据不扩展为Mac/Windows原生浏览器显示。
- Python普通报告/请求/门面/网关兼容 **192 passed/21.17秒**；新后端 **46 passed/3.41秒**，`/tmp/stk-report-generation-tests.log`；strict bridge与真实ScriptSessions worker **4 passed/2.37秒**，覆盖分步准备/只读/单次明确发送/编辑/保存/预览/ZIP/重开与旧handle拒绝。三种来源绑定反例已真实证明修前3失败、修后拒绝；保留 `/tmp/stk-report-generation-selection-regression.log`。所有来源状态为冻结观察，不将运行状态当科学结果。
- Python3.11/3.14相关各 **196 passed/7.80和8.78秒**，日志 `/tmp/stk-report-generation-python311.log`、`python314.log`。完整Python首轮 **3549 passed、2 failed、24 skipped、2 deselected、725.45秒**，`/tmp/stk-report-generation-full-python.log`；失败为脚本方法集合和支持prompt集合未同步，已补两条报告方法与新purpose，相关 **91 passed/11.05秒**，`/tmp/stk-report-generation-python-inventory-fixed.log`。运行器稳定后的最终3562项完整通过见上，不将首轮写作全绿。
- `uv build --offline`构建wheel/sdist成功，`/tmp/stk-report-generation-package.log`；wheel安装到隔离目录，`python -I`确认两个新模块和Schema来自安装目录，再执行新后端 **46 passed/3.65秒**，无源码包回退。最初venv无build/pip模块，使用已安装uv与离线缓存完成，未修改产品环境依赖。运行器修复后的最终重建及82项读回见上。
- Windows前头job日志 `/tmp/stk-ci-40264284403-windows-job.log:2047/2060` 确认多值discovery标签破坏带空格CMake命令；两处改为单标签，未删测试。Mac日志 `/tmp/stk-ci-40264284403-macos-job.log:7235/7242/7249` 三格式止于 `Create fixture project`。源码存在仅等Client后台Ready而未等主线程ProjectState回调的漏洞，已增加真实项目ready/非busy等待及安全失败诊断；这与日志相容，仍须新MacCI确定效果。原型WKWebView测试成功不等于正式三格式通过。
- 前推送头 `b32fd0c7` Desktop `40264284403` 已全部终态：Linux主回归、Linux包和干净Ubuntu包冒烟成功；Mac编译/CPU/Metal/app smoke成功、正式native步骤失败；Windows编译失败，独立native job skipped。Runtime `40264284376` 的3.11 job `121383139825` 唯一丢失worker用例失败，其余7job成功；Docs `40264284300`、Secret `40264284339`成功。Runtime限定摘录 `/tmp/stk-runtime-b32-python311-failure.log`；本机确定复现子程序已活但program.json未发布、后端误报failed，`/tmp/stk-worker-loss-repro.log`，已清理真实子进程。生产握手修正与完整回归见上，不能由复现宣称远端必然同根。
- Linux自身窗口程序运行退出1，明确 `Native window evidence is unsupported on this platform`，0轮/0图，`/tmp/stk-report-generation-linux-unsupported.log`及同名目录；这是平台边界预检，不证明MacReady修正或实际PDF显示。原生候选继续默认关闭，IME/跨屏DPI/浏览器内存、完整AI表单、LaTeX与视频继续。
- 暂存报告源码密钥扫描 **203977 bytes、零发现**；i18n **2475/2475、零问题**和空白检查通过。运行器最终结果见上；记录与认知收尾后推送，新CI另核。P4和第4–8项保持未完成，PET新专项后置。

## 2026-10-25：正式报告文档视口（本机完整回归通过，平台待验）

- 源码 `023aa66` 已本地提交 main；记录与认知对齐收尾后推送。`stk_document` 生产资源／平台库、正式报告独立视口、同步项目范围与区域移除清理已写入；
  原生候选仍默认关闭，Linux 仍为 Unsupported。统一全部目标构建退出 0，新增与既有报告专项 **167/167、零失败／错误／跳过／35.91 秒**，JUnit `/tmp/stk-formal-report-focused.xml`。包含 Host 9、范围 8、UI视口／遮挡9、区域移除4、真实桥 ReportsEditor30、预览18、无效回执11、资源14、像素3、布局18、内存自检3，以及报告 GPU **40/40**。
- 最终统一构建及 Viewer 元数据基线修正后的重建均退出 0，日志 `/tmp/stk-report-final-full-build.log`、`/tmp/stk-report-final-full-build-metadata-fix.log`。完整原生 **1903/1903、零失败／错误／跳过／454.71 秒**，JUnit `/tmp/stk-report-final-native-full.xml`。实际执行当前 Linux CI 的完整必跑脚本，405 次核对、**1433 项必跑匹配全部通过**，证据 `/tmp/stk-report-final-required.log` 与 `/tmp/stk-report-final-required-summary.json`。其中包含新增 Host、项目范围、UI 遮挡、PDF 回执及失效、正文判据和严格退出码门禁；这些本机结果不证明双平台原生呈现。
- Mac／Windows 的原型与三格式正式窗口测试改用标准库退出码包装器：同时要求真实退出 0、成功标记和无失败／泄漏诊断，取消 CTest 的成功正则覆盖。超时回收直接子进程，日志最多 64 MiB，不承诺清理已脱离后代。Python 3.12／3.11／3.14 各 **12/12** 真实子进程自检通过，分别 **2.207／2.181／2.607 秒**；完整 CTest 中门禁自检也实际执行。Windows 暂存文件以真实 CTest JSON 解析验证四个精确测试、含空格 Python、bundle 路径、600 秒超时及无 PASS 覆盖；修正原先在手写测试文件中会解析为空的目录变量，改用明确 bundle 环境路径。
- `git diff --check` 与 i18n **2474/2474、零问题**通过。CMake 显式开启候选的配置和统一全部目标构建均退出 0，
  日志 `/tmp/stk-formal-report-build.log`。每批全部链接结束后才运行测试。文档八图覆盖 OpenGL／Vulkan×中英×1440或560×1000，固定报告列表起点选报告→预览 **2 点击**；目视英文窄版／中文宽版，工具栏与末行返回控件完整可见。无窗口视口不绘浏览器像素，不作为原生内容显示证据。
- PDF 入口已复用旧 `project.reports.preview`，逐项核对 14 字段、规范 base64 与实际二进制 SHA／大小，最多 4 MiB，不作 UTF-8 解码；Host 只接单 PDF 或 HTML＋栅格图集合。新增 PDF 与既有报告专项 **97/97、零失败／错误／跳过／21.37 秒**及 97 项必跑检查通过，包含 29 个新增 PDF 场景。首轮重复宏标签编译失败已修正并重建成功；JUnit `/tmp/stk-pdf-controller-focused.xml`，构建 `/tmp/stk-pdf-controller-build-final.log`，必跑 `/tmp/stk-pdf-controller-required.log`。
- 无 Blender、默认关闭候选的全新 `/home/mnemora/opt/stk-build/report-resources-cpu` 配置及资源目标构建均退出 0；`DocumentResources` **14/14、零失败／错误／跳过**，必跑匹配 14 项。JUnit `/tmp/stk-report-resources-cpu.xml`，日志 `/tmp/stk-report-resources-cpu-{configure,build,test}.log`。缓存确认 Blender／native candidate／spike 均 OFF，没有拉取 WebView2 SDK。
- 正式按钮链 OS 程序已接入三格式：Markdown／HTML 各要求 20 轮／140 张合格 OS 图，PDF 要求 20 轮／160 张图；均为 21 次明确准备和不同会话。先经真实桥冻结后删除实时入口，文本同时核图片与正文，PDF 核完整二进制回执、原生滚动后第二页出现且第一页消失，隐藏／复显／弹层／关闭／重备均独立留图。Windows 测试 guard 在精确文档容器吞掉并记录未消费的上行滚轮，跨异步投递和捕获保留；调用方采用宿主相同的向内像素取整。Cocoa 只证明定向当前 WK 后代、未全局投递，不声称已证明零 responder-chain 上行。完整回归后仅对这些未注册为 Linux 显示测试的 helper／程序收尾，最终重建退出 0，日志 `/tmp/stk-report-final-harness-build.log`；Linux PDF 冒烟退出 1，失败 JSON 明确 Unsupported、0 轮／0 图，证据 `/tmp/stk-report-final-linux-unsupported/`。实际双平台呈现仍待 CI。
- 正文像素判据 `evidence_text_marker` 已补独立三行／四段文字几何，要求同字宽、极性、对齐及行距；仅六色图片不能通过。classifier 构建退出 0，`DocumentEvidence` **13/13、零失败／错误／跳过**及 13 项必跑检查通过，含 DPI／分数字宽／明暗正例与图片、缺行、乱序、错宽、噪声、工具栏、透明及坏缓冲反例。JUnit `/tmp/stk-report-body-evidence.xml`；构建／测试 `/tmp/stk-report-body-evidence-{build,test}.log`。这是识别器 CPU 验证，正文实际浏览器图像仍待三格式正式窗口验收。
- Windows 独立 job 已配置仅验收 exe 目录的固定 Mesa 26.2.4 双 DLL、显式 llvmpipe 与 WARP；归档 SHA、大小、实际 DLL SHA、GL vendor／renderer／version／模块路径及 WGC adapter 均留证。拒版本覆盖和自动回退，OS 像素／20 轮／关闭及最终 guarded 门禁保持。本机两个官方下载均超时，实际归档布局／DLL 依赖与平台运行尚待 CI，不声明软件路径已通过。
- 导航竞态已新增确定回归：只泵桥回复形成冻结讨论、暂不执行 Screen 队列，再启动项目刷新后执行导航。
  修正前 **1/2 通过**：正例 **0.63 秒**复现仍停留最大化起点，未捕获讨论／其他页面的反例通过；
  JUnit `/tmp/stk-conversation-race-before.xml`。已增加纯只读 `refreshing()` 状态及同项目冻结讨论的窄例外，
  仍保留写／关／打开、句柄、所有者和输入门禁。修正后工作区导航及完整工作流 **14/14、零跳过／36.41 秒**通过，JUnit `/tmp/stk-conversation-race-after.xml`，14 项必跑检查通过。工作流测试也改为先等按钮启用，
  随即核请求被接受，再分开检查捕获与导航，未延长原有超时。
- 前头 `43e5652` Desktop `40247654158` 已 completed/failure：Mac CPU **1220/1220**、Metal **246/246**、native **1/1**，20 轮／161 PNG 的全部 SHA 与阶段覆盖已核，引擎静态析构后 guarded **0 块／0 字节**，父关闭旧 URL 410。短回执 `/tmp/stk-ci-43-macos-evidence-summary.json`；完整图与 JUnit `/tmp/stk-ci-40247654158-macos-frames/`。Windows 编译与 CPU 成功，独立 native **0.25 秒**在预检失败：只提供 OpenGL 1.1、无 WGL_ARB_create_context，未达到 WGC／WebView2 显示；未安装驱动或 Runtime，未跳过，摘录 `/tmp/stk-ci-43-windows-native-failure-excerpt.log`。
  Linux完整 **1811/1812／507.10 秒**，唯一工作流转讨论等待失败已由上述确定性回归修正，须新 CI 复验，摘录 `/tmp/stk-ci-43-linux-failure-excerpt.log`。前头终态等待条件已满足；本批本机回归如上，新 CI 仍待推送后核对。
  Runtime `40247654031`、Docs `40247654048`、Secret `40247654022` 已成功；这些旧头结果不代表本工作树通过。

## 2026-10-25：报告额外来源选择（本机验收完成）

源码 `b23cfc0` 与原型最终内存门禁修正 `9358ca2` 已提交 main，基线 `0268d68`。所有运行均清空产品模型密钥并取消模型变量；没有模型请求。报告来源选择完整回归通过；随后原生验收工具的最终内存门禁已修正，追加验证见下。

- 新增 `project.reports.review_sources`，最多 16 个有序、去重类别／UUID，单一 SQLite 读事务核修订并捕获完整来源；结果限 384 KiB，超限明确失败。有效 12–16 MiB 工作流计划的复核回复小于 4 KiB，但内部仍读取并验证完整计划／事件，不能称作纯 SQL 摘要读取优化。
- 创建可选比较 `expected_sources_sha256`，核对同一捕获数组后才读资产及写入；仿真、分析、工作流观察在修订不变时推进均触发零写入冲突。比较后资产读取期间的观察推进不改已接受捕获，未承诺落库时为最新。旧省略参数行为保留。
- Python 3.12／3.11／3.14 四文件定向各 **131 passed**，分别 **20.55／21.79／21.48 秒**，日志 `/tmp/stk-report-sources-python-focused.log`、`python311-focused.log`、`python314-focused.log`。首轮 129 passed／2 failed：预算异常自抛后被 `ValueError` 捕获，已将预算判断移至捕获之外；新测试 hello 补 `protocol=1`，未放宽校验。
- 桌面与协议定向 **27/27、零跳过／6.61 秒**，JUnit `/tmp/stk-report-sources-native-focused.xml`。覆盖明确读取、恢复与旧回调、修订／项目漂移、来源摘要错误、冲突重审、丢回执精确核对、分页与 16 项上限及 v1 草稿兼容。首轮 25/27 的两个恢复测试未等待阅读器异步就绪，修正等待后通过；此前 ordered/sorted JSON 的 push_back 编译歧义已显式转换。
- 固定起点为 **1440×1000、1×、已最大化 Reports 页、隐藏未保存 Python 稿和已有 Viewer**；7 点击准备原有创建表单，5 点击展开／读来源页／选行／加入／核对，再 1 点击创建，共 **13 次实际鼠标点击**，键入／Enter 和起点建立另计。项目历史只增加一次，完整冻结来源匹配；元数据与复核不读取资产、不执行或刷新运行，也不改变 Viewer／隐藏稿。
- 报告文本／PNG／创建／新来源图形共 **32/32、零跳过／63.11 秒**，JUnit `/tmp/stk-report-sources-gpu.xml`。新增来源八图覆盖 OpenGL／Vulkan×中英×1440 或 560×1000，准备与复核 **12 点击**、停在创建前；宽版 0 滚轮步，窄版英文 6／中文 5 步。四幅语言／宽度组合已目视；完整 UUID、复核提示和完整小来源 JSON 同时可见。Linux 软件 GPU 离屏证据不扩展为硬件或双平台原生浏览器证据。
- wheel 与源码包重新构建成功，`python -I` 从 wheel 经真实无界面服务发现新接口、复核值和摘要、带来源 CAS 创建，再删除实时入口／图片、关闭重开读回冻结来源、净化入口和图片；修订保持 4，源码包指南存在。日志 `/tmp/stk-report-sources-dist-build.log`、`/tmp/stk-report-sources-wheel-smoke.log`。
- 三平台 CPU 必跑追加新 Schema 场景，Linux／Metal GPU 必跑追加来源宽窄场景；i18n **2462/2462、零问题**及空白检查通过。完整 Python **3502 passed、24 skipped、2 deselected、1 既有 Starlette 提示／718.58 秒**，日志 `/tmp/stk-report-sources-python-full.log`。完整原生 **1809/1809、零失败／错误／跳过／451.73 秒**，JUnit `/tmp/stk-report-sources-native-full.xml`；逐条执行现行 Linux CI 必跑脚本，**1339 项实际运行通过**，日志 `/tmp/stk-report-sources-required.log`。随后全部目标构建退出 0，新主程序重链后的安装／验收 **2/2、零跳过／2.73 秒**，JUnit `/tmp/stk-report-sources-final-package.xml`。源码暂存 gitleaks 使用 `.gitleaks.toml` 和 `--redact`，扫描 **132245 bytes、零发现**，日志 `/tmp/stk-report-sources-source-gitleaks.log`。本批新头 CI 待推送后验证。
- 前头 Desktop `40242092854` 的 Windows Build 已失败：`SetProcessDpiAwarenessContext`、`GetThreadDpiAwarenessContext`、`GetAwarenessFromDpiAwarenessContext` 在 `_WIN32_WINNT=0x0603` 下无声明，测试及 Windows native job 未运行。仅在可选证据预检动态解析 User32 三接口，缺任一接口仍明确失败；产品最低系统要求不变。macOS CPU **1207/1207**、Metal **242/242** 零跳过；真实 native 20 轮执行 **101.44 秒**后因最终 guarded 检查失败，整 run 已 completed/failure，Linux 三项成功、Windows Build 失败、Windows native skipped。Runtime `40242092844`、Docs `40242092882`、Secret `40242092819` 均成功，前头推送等待条件已满足。这些结果不代表本批修正的 Windows 或 macOS native 已通过。

- macOS artifact `desktop-macos-frames` 的 161 张最终 OS PNG 已逐一校验 SHA：20 轮×8 阶段加最终父关闭前一帧，均两次连续匹配；20 条关闭记录及父关闭均 detached／hidden、旧 URL 410，运行时为 WKWebView `20621.3.11.11.3`。已目视同窗文档、旁边 Viewer、隐藏后 Python 及最终会话；结果 JSON 仍为 failed、`guarded_stk_leaks=null`。证据 `/tmp/stk-ci-40242092854-macos-desktop`，紧凑核对 `/tmp/stk-ci-40242092854-macos-evidence-check.json`。
- 源码审查发现原型在 Runtime 返回后、Metal 函数局部静态析构前要求零块，与正式应用既有退出检查顺序不符。`9358ca2` 在 Runtime 初始化分配器后、引擎首次初始化前登记最终检查，退出时先析构晚静态，再核零块／零字节，最后保留既有 fail-on-leak 检测器；只有完整图像／生命周期证据和最终零计数才写 passed。提前失败不被最终零计数覆盖，真实泄漏仍退出 1；Runtime 后计数和分配标签仅供诊断。旧日志没有标签，不能认定全部旧块均来自 Metal 静态，也不能据本机通过认作 Mac 修正已通过。
- 追加全部目标构建退出 0；三项纯 CPU 自检分别实际验证晚静态先持有后释放（准确退出 0）、真实 64 字节泄漏（准确退出 1）、早失败但最终零计数（准确退出 1）。包装器核对诊断及析构顺序，崩溃／超时／任意其他退出码不算通过。三项、资源／像素、四窗口及安装相关 **26/26、零跳过／3.16 秒**，JUnit `/tmp/stk-native-final-leak-gate-focused.xml`；三平台 CPU 必跑已追加。没有重新执行整套新增 1812 项原生套件；来源选择完整 1809 项与追加修正专项分别记录。源码暂存 gitleaks 扫描 **31045 bytes、零发现**，日志 `/tmp/stk-native-final-leak-gate-gitleaks.log`。

- 关闭 Blender 的独立构建已重新完成；资源与像素判据 **17/17、零失败／错误／跳过**。同次扩大的 CPU 执行共有 286 项，277 passed、9 skipped；跳过的均为未配置 `STK_BRIDGE_TEST_PYTHON` 的 PythonBridge 用例，不算通过。JUnit `/tmp/stk-native-final-leak-gate-cpu.xml`，构建及执行日志 `/tmp/stk-native-final-leak-gate-cpu-build.log`、`/tmp/stk-native-final-leak-gate-cpu.log`。本项仅补证无 Blender 资源构建，不代替主构建真实桥回归。

本次 AOCI 已完整交付 22 块并确认，Challenge 10/10；源码与记录按最终稳定状态增量维护，实际治理以 Verify／Check／Guide 为准，不用机器对齐替代当前完整认知可靠性或实机验收。P4 富文档／PDF、AI 报告、LaTeX、视频、报告模式与第 4–8 项继续，PET 新专项后置。

## 2026-10-25：报告资源读回与原生显示证据（本机验收完成）

源码 `84d918b` 已提交 main，记录与索引同批交付。基线 `841910f`。前头 `841910f` 的 Desktop `40237659778` 已全部结束并 **5/5 成功**，含 Windows 旧菜单夹具修正后的回归；Runtime `40237659904` **8/8 成功**，Docs `40237659836`、Secret `40237659794` 成功。前头推送等待条件满足，这些结果不代表本批新源码通过 CI。

- 控制器独立准备净化入口和全部栅格图片，源入口／显示入口／图片各自核摘要，按冻结顺序串行读取，64 项与 32 MiB 预算核对后才一次发布；不改原文选择、Viewer、修订或历史，不自动重试或恢复。桥 Client、pid:spawned、句柄、项目、修订、报告、来源 SHA 和本次代次共同隔离晚到回复。
- 新专项 24 项真实桥测试首轮 **22/24**：工作空间测试把正常首次元数据加载误判为 Viewer 被改；另一个对 Ready Client 调用 restart 实为无操作。已先明确完成三份只读 Viewer 元数据，再冻结基线；由夹具持有回复线程自退出触发同一 Client 真实进程代次变化，保留完整 Viewer／零求值断言。测试编译时重复 GTest 宏标签和 string/JSON 比较已修正，没有修改业务门禁来满足测试。
- 修后控制器 24 项、像素判据 3 项及 X11／Wayland × OpenGL／Vulkan 4 项合计 **31/31、零跳过／7.72 秒**，JUnit `/tmp/stk-preview-preparation-focused.xml`；对应必跑检查通过。后四项验证 Linux 的 Unsupported 生命周期，不能证明原生浏览器显示。
- 新建关闭 Blender 的独立构建，资源和像素判据 **17/17、零跳过／0.12 秒**，JUnit `/tmp/stk-preview-evidence-cpu.xml`。Linux 显式 native 验收入口实际返回 1，JSON 为 failed、完成 0 轮、图像 0，原因 Unsupported；没有伪造通过或创建浏览器。证据 `/tmp/stk-preview-unavailable-evidence/result.json`。
- Mac 用当前进程窗口的 ScreenCaptureKit，Windows 用指定自身 HWND 的 WGC，仅采原型父窗口客户区；两页各有宿主 GPU 不生成的六色色条，每阶段两次独立采样匹配。20 轮八阶段加最终父关闭前一帧共 161 张最终 PNG，JSON 记录 SHA、几何、导航代次、会话、关闭和旧 URL。Windows 提前统一 DPI 并预检 GL 4.3，缺显示、Runtime、权限或匹配像素均失败并保留证据；不自动安装 Runtime／驱动或修改权限。OS 合成截图不证明物理 scanout、PDF／IME、跨屏 DPI 或浏览器进程内存稳定。
- Screen 提供可取消的布局完成／立即失效订阅：弱注册表、复制回调、显式 active、重入／代次保护，销毁先失效再断开；隐藏所有者仍被通知，无 UI 回执为 null。标签切换、实际几何／缩放变化、清空及布局采用均先失效，普通重绘不撤焦；跨 Screen 须重新订阅。16 项 CPU 用例覆盖 clear 时 Editor 与 token 析构、取消自身／后续监听、新监听延后、Screen 先死、adopt、隐藏页及 noUI。专项合计 **47/47、零跳过／11.46 秒**，JUnit `/tmp/stk-preview-layout-focused.xml`。
- 随后候选实际使用布局订阅，移除主循环外部全 Host 同步；新增标签／最大化的下一帧前立即隐藏及关闭取消 token 断言，所有 Modal 隐藏、相交浮层暂隐藏。候选仍占整个 main 区域，正式报告需独立预览视口；同批原生输入、快捷键和 IME 尚未证明。
- 最终完整构建退出 0，完整原生 **1791/1791、零失败／错误／跳过／428.09 秒**，JUnit `/tmp/stk-preview-layout-native-full.xml`。逐字核对既有 Linux 必跑脚本未变化后，485 条现行规则匹配 **1321 项全部实际运行**，证据 `/tmp/stk-preview-layout-required.log`。本次没有生产 Python 变更，Python 行为由真实桥原生用例覆盖，不把上一批完整 Python 结果写成本批重新运行。
- 三平台 CI 追加新控制器、布局与像素必跑项。Mac 原生捕获放在既有 STK.app 打包验收／上传之后，Windows 独立作业消费同头候选包；均保留失败 JSON、图像和 JUnit。真实 Mac／Windows 作业尚未执行本批，不能按编译或 Linux Unsupported 认作显示验收。
- i18n **2445/2445、零问题**与差异空白检查通过；源码暂存 gitleaks 使用 `.gitleaks.toml`、`--redact`，扫描 **163187 bytes、零发现**，日志 `/tmp/stk-preview-layout-source-gitleaks.log`。没有新的正式 UI 点击交付，自动调用 API 的循环不换算为用户点击数。

本轮 AOCI 压缩刷新在第 4/22 块被宿主截断，已停止本次链，不自动重试或修改配置；后续为绑定源码开发与最终稳定内容的增量维护。

P4 和整个通用目标仍未完成；保留原文／PNG 阅读器、Viewer 和草稿。额外来源选择、完整浏览器／PDF、AI 报告、LaTeX、视频和报告模式继续，PET 新专项后置。

## 2026-10-25：报告预览资源准备（本机验收完成）

源码 `31c1e06` 已提交 main。前头 `78f51b2` Desktop `40234644345` 已全部结束，4/5 成功：Linux、macOS、打包与干净容器成功；Windows 1107/1108，唯一失败 `WorkModeLayouts.ActiveTextAndDeferredOldMenusCannotHideOrCommitInput`，析构 SEH `0xc0000005`，没有栈。[失败作业](https://github.com/sijintech/stk/actions/runs/40234644345/job/121293477909)。Runtime `40234644378`、Docs `40234644456`、Secret `40234644394` 成功，前头推送等待条件满足；本批新头 CI 待确认。

- 新增可发现只读 `project.reports.preview_resources`，响应只有净化入口、四种栅格图片描述符和实际入口加声明图片大小；32 MiB 总量、入口输入 1 MiB／显示 4 MiB，各资产读取保持原预算，不把整包放进一条桥响应。次级文档不进入相对链接映射，CSP 限具体图片路径；宿主仍须逐项核验原图字节，全部通过后原子建立并按生命周期失效会话。
- 独立审查发现新响应直接复用旧宽类型，Schema 本身可接受 PDF／identity 或 HTML 资源；现仅在新结果用 allOf 收窄，旧 preview 定义不变。Python 与真实 C++ 嵌入 Schema 均检查禁止类型、缺失来源、额外键、63／64 项及 32 MiB 边界；Linux、macOS、Windows 必跑规则追加 `Schema.ReportsPreviewResources`。
- Python 3.12 相关 **232 passed／18.58 秒**；初轮 230 passed／1 failed 是旧脚本目录精确集合漏新方法，已同步。3.11／3.14 最终新接口与脚本专项各 **28 passed／11.95、11.92 秒**。完整 Python 3.12 **3483 passed、24 skipped、2 deselected、1 既有 Starlette 提示／721.04 秒**，日志 `/tmp/stk-report-preview-python-full.log`。
- 完整原生 **1748/1748、零失败／错误／跳过／436.85 秒**，JUnit `/tmp/stk-report-preview-native-full.xml`；当前 Linux CI 的 481 条必跑规则核对 **1278 项全部实际运行**，证据 `/tmp/stk-report-preview-required.log`。新增 C++ Schema 场景实际运行 0.0247 秒。
- 随后核对 Windows 失败：测试显式 `shell.reset()` 使共享 ViewerState 先释放，仍存活 ViewerEditor 析构访问借用指针；普通 fixture 和生产退出顺序没有这处倒置。已先 `screen.clear()`，保留 shell 销毁后复制 action 的原验证；重建实际承载目标 `stk-project-tests` 后，工作模式／旧回调／焦点／导航相关及必跑 **45/45、零跳过／2.05 秒**，JUnit `/tmp/stk-report-preview-fixture-focused.xml`。这是确定夹具缺陷的修正；无 Windows 栈和新头结果，不能宣称复现并解决同一崩溃。
- wheel 与源码包重新构建，使用 `python -I` 从 wheel 隔离导入新模块及 Schema，经真实无界面服务创建报告、删除实时入口和图片、关闭并重开后净化入口、逐项读取图片并验证 SHA，总修订保持 3；源码包指南存在。证据 `/tmp/stk-report-preview-dist-build.log`、`/tmp/stk-report-preview-wheel-smoke.log`。源码暂存 gitleaks 采用 `.gitleaks.toml`、`--redact`，扫描 **56322 bytes、零发现**；差异空白检查通过。

本批为后端与协议交付，没有新增 UI 点击动作。原生浏览器嵌入、完整 PDF、AI 报告、额外来源选择、LaTeX、视频和报告模式仍未完成；macOS／Windows 候选尚无实际嵌入证据，Linux 未选后端。P4 和第 4–8 项继续推进，PET 新专项后置。

## 2026-10-25：桌面创建冻结报告（本机验收完成）

源码 `a10025587fb0b85d386c31f7980f10b2fa2cf01b` 已提交 main，记录与索引按同批交付。前代码头 `93d3a064a31358b4a31ac6355fee333d7e5338c6` 的 Desktop `40230875886` 已全部结束并 **5/5 成功**（Windows、macOS 与三项 Linux）；Runtime `40230875833`、Docs `40230875895`、Secret `40230875843` 成功。前头推送等待条件已满足；这些结果不代表本批新源码的 CI。

- 功能：独立报告页提供显式创建表单，从已有冻结输入快照选择 1–64 项资产、编辑报告内路径并指定唯一入口；创建一次 CAS／撤销，成功后只打开元数据，不自动读资产、运行文档或发送模型请求。当前表单不选择额外上下文／运行来源，Python 接口保留该能力。
- 新增 `project.snapshots.list_summaries`，每页最多 64 条，只返回六个摘要字段；修订、总数和页面同一读事务，选择后才核对完整清单。1025 条快照测试覆盖稳定分页、不向 Python 解码完整清单、并发写一致性及坏页隔离；旧 `list/get`、存储格式和历史行为不变。
- 固定点击起点：**1440×1000、1×、最大化报告页、隐藏未保存 Python 稿和已有 Viewer 数据／相机**。展开创建、读快照页、选快照、标题输入框、选资产、勾选加入、设入口、创建，共 **8 次实际鼠标点击**；键入和 Enter、建立起点另计。修订 3→4、历史增加一次，报告清单核对一致，资产读取／导出计数均为零，隐藏稿与 Viewer 保持。数字不含默认布局导航。
- 报告原生专项最终 **17/17、零跳过／4.44 秒**，JUnit `/tmp/stk-reports-create-budget-native.xml`。覆盖工作空间恢复需明确重审、旧 getter/setter 与按钮失效、不确定回执按原 UUID 查询且 NotFound 不重发，以及创建已落库但回执延迟、更换桥会话后的原身份恢复。
- 独立审查发现工作空间入口会先隐式复制为 ordered JSON，之后才检查草稿预算；现先检查原 JSON 的标量和有界树，阅读状态只复制五个标量。公开入口的超大／深草稿和不匹配 pending 均原子拒绝并保留原状态。首轮专项 **12/14** 的两处失败来自恢复后未等待阅读器异步就绪；补等待后 14/14，新增上述回归后 17/17，未放宽生产忙碌门禁。
- GPU 文本／PNG／创建表单 **24/24、零跳过／21.40 秒**，OpenGL／Vulkan × 中英 × 1440 或 560×1000。新增八张创建图逐张目视无阻断裁切，关键控件完整可见；真实准备表单 **7 点击、0 滚轮步**，停在创建前，未读取／预览正文，项目历史和运行列表不变。此处是软件 GPU 离屏证据，不扩展为硬件或其他平台性能。
- Python 3.12 相关 **63 passed／8.69 秒**；3.11／3.14 快照相关各 **50 passed／2.33、2.30 秒**。最终完整 Python 3.12 **3468 passed、24 skipped、2 deselected、1 既有 Starlette 提示／719.26 秒**，日志 `/tmp/stk-reports-create-python-full.log`。
- 最终完整原生 **1747/1747、零失败／错误／跳过／424.57 秒**，JUnit `/tmp/stk-reports-create-native-full.xml`。按当前 Linux CI 480 条规则核对 **1277 项必跑全部实际运行**，包含新增创建图形；证据 `/tmp/stk-reports-create-required.log`。i18n **2445/2445**、差异空白检查通过。
- wheel 与源码包重新构建，从 wheel 隔离导入，经过真实无界面服务发现新方法、分页、创建、删除实时输入后重开读取冻结字节，修订保持 3；源码包报告指南存在。证据 `/tmp/stk-reports-create-dist-build.log`、`/tmp/stk-reports-create-wheel-smoke.log`。源码暂存 gitleaks 采用 `.gitleaks.toml`、`--redact`，扫描 **129042 bytes、零发现**。

P4 仍未完成：原生富文档／完整 PDF、AI 报告、额外来源选择、LaTeX、视频和报告工作模式继续推进；macOS／Windows 文档候选仍只有编译证据，Linux 原型明确 Unsupported。第 4–8 项与通用目标继续，PET 新专项后置。

## 2026-10-25：冻结报告存储与桌面读取（本机验收完成）

本批源码 `3f4af5e898e8f739591bb6fb05d46e872cce0452` 已提交；前头 `b7a658978c40cd6d7a0cf706bc49182b0e72cdd2` 的 Desktop `40222998247` **completed/failure**：macOS 和三项 Linux 作业成功，Windows **1090/1091**，唯一失败是 `ProjectSkillsPython.LargeWorkflowDependenciesStayBrowsableAndMappingsRemainEditable`；Runtime `40222998233`、Docs `40222998232`、Secret `40222998221` 成功。前头全部结束，推送等待条件满足，本批新头 CI 待确认。两平台文档候选均通过编译，但 CI 没有执行原生嵌入命令，仍不能认作嵌入验收。

- 功能：普通报告表引用同一输入快照中的 1–64 项资产，保存最多 16 个冻结上下文／运行状态；清单、原始资产和显示字节摘要分别验证。`get/list` 只读元数据；读取、预览、导出明确绑定项目句柄／修订／清单摘要，旧来源与坏对象拒绝。导出新 ZIP 包含清单和完整原始资产，不覆盖且不运行来源。
- Python 最终定向：3.12 **217 passed／17.56 秒**；3.11 **204 passed／9.83 秒**，3.14 **204 passed／9.48 秒**。真实桥／worker、坏上下文、路径／摘要／CAS、原文件删除后的读回重开、没有运行或模型请求均覆盖。两段报告指南原例由严格桥直接执行，**0.51 秒**通过。
- 原生报告最终定向 **10/10、零跳过、2.32 秒**，JUnit `/tmp/stk-reports-final-focused.xml`。固定起点是 **1440×1000、1×、已最大化的报告页**，旁有隐藏未保存 Python 稿和已有 Viewer 数据／相机；从此起点依次选报告、读取资产、定位目标输入框、导出，共 **4 次实际鼠标点击**，键入绝对路径及准备起点另计。完成后 ZIP 存在，稿件／Viewer／修订保持，未执行脚本。此数字不包含从默认布局打开报告编辑器。
- GPU 中英宽窄文本／PNG **16/16**，OpenGL／Vulkan 软件渲染，1440 或 560×1000。每张使用真实桥和已删除原文件的冻结资产，实际点击显式读取；校验原文和未渲染提示完整可见、PNG 为真实纹理及图中像素；逐张人工查看无阻断裁切。图片位于构建树 `tests/app/out/reports_*`，日志 `/tmp/stk-reports-visual-focused.log`；该轮报告 CPU 夹具失败后已由上述 10/10 复验，不把整份旧 JUnit 写成全通过。
- 发行检查：安装入口和现有契约／包测试 **23 passed、1 Windows-only skipped**；最终 wheel 与源码包重新构建成功，从 wheel 实际导入三个新模块，并验证 documents extra、指南、原文件删除后的冻结读取／净化预览／导出／重开及修订不变。最终构建证据 `/tmp/stk-reports-final-distribution-build.log`，产物目录由 `/tmp/stk-reports-final-dist-path.txt` 记录；隔离导入冒烟退出 0，代码从 wheel 加载。
- 首次编译因同一行两个 `ASSERT_NO_FATAL_FAILURE` 产生重复标签失败，已分行；CPU 夹具先把 Logs 当作 Python，再遗漏全选及错误假定默认基线为空，现通过真实输入建立稿件并核对原基线不变。原生产编辑器未为测试修改。
- Python 首轮完整 **3430 passed、4 failed、24 skipped、2 deselected／702.24 秒**：六个新方法未列入旧接口集合，另三个缺依赖提示断言是运行开始时收集的旧正则；均已同步。最终完整 **3434 passed、24 skipped、2 deselected、1 既有 Starlette 提示／711.89 秒**，日志 `/tmp/stk-reports-python-final-full.log`，退出 0。
- 完整原生首轮 **1731/1732、零跳过／418.36 秒**，唯一失败 `App.EditorKeysExistInEveryCatalog` 仍断言 16 种编辑器；改为 17 并补报告注册断言，`stk_wm_tests` 重建退出 0。最终完整 **1732/1732、零失败／错误／跳过／414.48 秒**，当前 Linux CI 的主必跑规则及全部中英 GPU／原型循环检查 **1262/1262**；最终证据 `/tmp/stk-reports-native-final-full.log`／`.xml`、`/tmp/stk-reports-native-final-required.log`，首轮日志保留。
- 中英语言目录 **2423/2423、零问题**，差异空白检查通过；源码暂存 gitleaks 使用 `.gitleaks.toml`、`--redact`，扫描 **306737 bytes、零发现**（`/tmp/stk-reports-source-gitleaks.log`）。
- 独立审查复现并修正合法路径之间 1158 字节相对 URL 被错误套用 1024 字节资产键上限（输出 URL 仍受编码前后 8192 字节限制）；对重算 SHA 后的嵌套坏 context 按已发布结构验证，单条 invalid 不再拖垮严格列表回复。
- Windows 旧失败修正仅同步测试准备写入与 800 表分页观察，等待 loaded、准确修订及无忙碌并保留诊断；本机定向已执行通过，仍需下一头 Windows CI 复验。

边界：当前桌面只读原文／PNG，未交付报告创建表单、完整富文档嵌入、PDF 阅读器、AI 生成、LaTeX、视频或独立渲染 HTML 导出。Markdown／HTML 净化输入限 1 MiB，原始资产每项 4 MiB／总 32 MiB；导出是原始来源包。报告不提供认证签名，普通表编辑会重新验证。页面 CSP 和资源门禁不证明浏览器后台无网络，也不代替实机 IME／DPI／PDF／生命周期验收。P4 和第 4–8 项继续推进，PET 新专项后置。

## 2026-10-25：原生文档嵌入候选（本机验证）

源码 `10e6423f5f5bfc18f66047fda686f323ae702fa1` 按 main 交付。前头 `3dc178d17c2eb32a5da48d36b4ce0224e797ecc3` 的 Desktop `40219610785` 已全部结束并 **5/5 成功**（Windows、macOS、Linux、包与干净容器），推送等待条件已满足。Runtime `40219610773`、Docs `40219610766`、Secret `40219610816` 均成功。本批后续 CI 状态以新记录为准。

原型选项 `STK_DESKTOP_BUILD_DOCUMENT_PREVIEW_SPIKE=ON` 只添加开发目标，不安装进产品；默认关闭。Linux 构建日志 `/tmp/stk-document-preview-{configure,build,final-build}.log`，真实窗口使用英文默认工作台 **1440×1000、1×**，右上为文档/Python 标签，Viewer 显式加载公开 payload 夹具。没有桥、用户项目或模型请求。冒烟直接调用标签、最大化、导航及关闭 API，**没有人工点击数验收**，不能由此推断导航点击减少。

- 资源清单 **14/14**：四种身份、UTF-8／空格／`#`／`%` 路径、跨项目／版本拒绝、越界与编码攻击、MIME／预算、HEAD 和关闭失效。
- X11／Wayland × OpenGL／Vulkan 原型 **4/4**：每项两次标签关闭及重开，再创建一份供父窗口关闭检查；实际 GHOST 窗口中的隐藏／恢复、旧会话失效、Viewer 来源保持，脚本历史和 Viewer 求值均未增加。Linux 明确 `Unsupported`／`native=0`，未创建浏览器子视图。
- 同次既有窗口回归 **10/10**；总计 **28/28、零失败／错误／跳过、21.12 秒**，必跑检查匹配 28 项。日志 `/tmp/stk-document-preview-final.log`、JUnit `/tmp/stk-document-preview-final.xml`。
- 独立 `STK_DESKTOP_WITH_BLENDER=OFF` 配置和资源目标构建通过，资源测试 **14/14、0.14 秒**。证据 `/tmp/stk-document-preview-cpu-{configure,build,test}.log`、`.xml`；未生成浏览器或窗口目标。
- 独立审查修复未初始化错误字符串、HEAD 误报零长度和 Windows 旧 Starting/Completed 事件污染新导航状态。Windows 改为等待当前 Starting 绑定，再提交替代 URL；相同冻结 URL 请求幂等。PNG 夹具由 Pillow 解码为 16×16 RGBA；两页 PDF 尚未实际平台显示。

首轮 **16 passed、2 failed**：Wayland 首帧 1440×1000 超过私有 kiosk 显示 1280×800。`WAYLAND_DEBUG` 明确返回 `xdg_wm_base error 4`，不是浏览器失败或 compositor 先崩溃。仅将测试 runner 的固定显示改为 1440×1000，未扩改 GHOST；修后四组合通过。日志 `/tmp/stk-document-preview-focused.log`、`/tmp/stk-document-preview-wayland-debug.log` 保留失败证据，不复制显示授权文件。

macOS／Windows 尚无本批编译或运行结果。CI 将显式编译候选及运行资源测试，原生运行命令单独生成；须在真实平台检查父视图附着、菜单／输入／PDF／跨屏 DPI 与生命周期。`parent_attached`／`visible` 从平台读取，导航 Ready 和帧计数仍不能证明 scanout；本机 Linux 软件 GPU 结果不扩展成跨平台支持。菜单相交及边界拖拽时暂时隐藏子视图，是未解决的体验限制。没有 Markdown 转换、PDF.js、LaTeX、项目关联或文档导出。

浏览器页面资源门禁不证明 Runtime 更新／遥测完全无网络流量；guarded STK 分配零泄漏不证明浏览器进程内存没有增长。20 次真机循环、独立内存采样、离线部署及 OS 截图仍待执行，P0 尚未选型。操作命令见[原型计划](design/document-preview-spike.md)。暂存 gitleaks 使用 `.gitleaks.toml`、`--redact`，扫描 **153963 bytes、零发现**；差异空白检查通过。当前 AOCI 全量读取被宿主截断后已停止链，只进行源码绑定开发；正式索引按最终稳定内容增量维护，机器对齐不证明完整认知可靠。

## 2026-10-25：真实窗口大项目性能（本机验收完成）

前头 `f9a78c2702399064f16abbf5426f3befaad8160f` 的 Desktop `40213263506` 已全部结束并 **5/5 成功**，包括 Windows、macOS、Linux、打包及干净容器冒烟；Runtime `40213263592`、Docs `40213263886`、Secret `40213263583` 也已成功。本机方法库源码 `6fa8994` 与记录／索引 `cf2b40d` 的推送等待条件已满足。

方法库源码及记录头 `cf2b40df0e7562ce09774008c9a3e280af202049` 已成功推送，其 Desktop `40216687457` 已全部结束并 **5/5 成功**；Runtime `40216687448`、Docs `40216687646`、Secret `40216687630` 均成功。本批基准源码 `639614b29ad26e5f7536e3333b82e1806200ceaf` 已本地提交，待记录和索引收尾后推送；前代码头等待条件已满足。下节“尚未推送”是当时的方法库验收记录。

`stk-project-open-window-benchmark` 与原 CPU 目标均构建成功（`/tmp/stk-project-window-benchmark-build.log`）。正式测量使用真实 GHOST 窗口、生产字体和桥，固定英文默认布局 **1440×1200、1×**，两张各 **10000 行、8 列**的公开合成表。每组合按旧快照／分页模式交替顺序各运行三次，共 **24 次**全部退出 0；建库、桥及显示服务启动不计入打开时间。原生基准直接调用明确打开动作，本批没有用户导航点击数变更。

下表是每模式三次中位数，左为旧快照，右为分页；RSS 单位 MiB。

| 显示／后端 | 绘制与交换调用返回（秒） | 原生采样峰值 RSS | 原生及桥进程树 RSS | 关闭前响应量（MiB） |
|---|---:|---:|---:|---:|
| X11／OpenGL | 3.053 → 0.821 | 370.06 → 210.82 | 476.46 → 313.68 | 9.88 → 1.23 |
| X11／Vulkan | 2.905 → 0.711 | 355.81 → 196.98 | 458.59 → 297.45 | 9.14 → 0.50 |
| Wayland／OpenGL | 3.070 → 0.846 | 391.89 → 229.41 | 501.27 → 335.71 | 9.88 → 1.23 |
| Wayland／Vulkan | 2.935 → 0.690 | 355.95 → 195.56 | 459.86 → 291.50 | 9.14 → 0.50 |

全部运行总记录数 20000；旧快照共享缓存 20000 条，分页共享缓存 200 条，独立网格页 500 条。`visible_rows` 是网格可查询页长度，**不是屏幕实际可见的 500 行**。首值为 0，项目修订、脚本运行、Viewer 求值、schema／协议错误和重启次数全部为 0。CPU 与窗口各一对 100 行初始冒烟通过；加入最终能力预检后各一对再次通过，不重复声称整套性能矩阵覆盖该前置检查改动。

正式证据在 `/tmp/stk-window-bench-20261025-{xvfb,weston}-{opengl,vulkan}10000/`，含每次 `result.json`、`stdout.log`、`stderr.log`、响应字节摘要和 `window.png`，以及合并 `report.json`。已查看 X11 OpenGL 冒烟、X11 Vulkan 和 Wayland Vulkan 万行分页图，表格显示首行数据和 500／10000 页状态，Viewer 保持未打开结果。日志只复制明确名单，不复制项目、桥状态、profiles 或显示授权文件。

测量边界：`Window::frames_drawn` 无条件递增，不能证明交换成功或屏幕呈现；兼容字段 `first_visible_seconds` 明确绑定 `timing_boundary=post_data_ready_draw_and_swap_release_return`，包含一次数据就绪后的显式重绘。截图是停止计时／RSS 采样后对当前窗口状态的离屏重绘，不是合成器已呈现帧。驱动为 Mesa 26.0.8、LLVM 21.1.8，OpenGL llvmpipe、Vulkan lvp ICD（设备名仍报告 llvmpipe），全部属于软件渲染。操作系统缓存已热；RSS 每约 5ms 采样，会重复计算共享页，不包括显示服务器或独立显存；响应量统计到桥关闭，包含晚于计时点的 UI 元数据。硬件 GPU、macOS／Windows 原生窗口、真实 scan-out 和冷启动仍未验证。

异常路径：父仍存活时用 pidfd 核对身份、冻结父子树后终止独立进程组／session 后代；根已经退出而重挂的后代无法由该 helper 发现，此处不声称完整崩溃清理。启动被测命令前检查 API、内核能力及权限，缺失时不创建命令。Python 定向 **15 passed、3.23 秒**，包含真实超时子孙、无关进程存活及日志保留；六个预检失败用例注入 API 缺失、ENOSYS、EPERM，不是实际受限内核测量。显示／工作空间 CTest **12/12、零失败／错误／跳过、19.91 秒**，必跑检查匹配全部 12 项，证据 `/tmp/stk-window-benchmark-display-regression.log`／`.xml`。源码暂存 gitleaks 扫描 **43827 bytes、零发现**，差异空白检查通过。

重现入口为 `tools/benchmark_project_open.py` 的 `--gpu-backend opengl|vulkan --artifacts-dir NEW_DIR`，整个 driver 置于 `desktop/tests/wm/run_with_display.py --size 1440x1200 --server xvfb|weston ... --` 内；不能只包 native 子进程，否则 RSS 采样对象改变。沿用本机 sysroot、软件 GPU 环境和空测试密钥，`--rows 10000 --repeat 3`；两个可选目标需要显式构建，不安装进产品、不加入日常性能断言。下一步进入 P4 嵌入验证；本批不等于第 3–8 项完成。

## 2026-10-25：全局用户技能目录（在研）

本批源码 `6fa89943b8011730146c52e8cc339f21aa05c6d4` 已本地提交，尚未推送。基线为已推送记录头 `f9a78c2702399064f16abbf5426f3befaad8160f`（工作流技能源码 `bc964f2`）。该头 Desktop `40213263506` 尚在运行，三项 Linux 与 macOS 作业已成功，Windows 尚未结束；Runtime `40213263592`、Docs `40213263886` 与 Secret `40213263583` 已成功。前批 23 条 AOCI 语义更新已通过 Verify／Check／Guide；记录暂存 gitleaks 扫描 **128977 bytes、零发现**。这些结果不覆盖当前全局目录工作树。

- 新桥测试连同既有目录、脚本和权限回归 **56 passed、27.58 秒**（`/tmp/stk-user-skill-bridge-first.log`）。覆盖分析与完整工作流跨项目固定／创建、原源定义删除后复制、只读目录不加载插件、状态目录隔离、发布不改变项目历史、明确新版本及同请求幂等回执。初次命令误写不存在的 `test_agent_levels.py`，退出 4 且未运行测试；更正为实际 `test_agent.py` 后执行上述套件。
- 接线审查修复库构造器的 keyword-only `root` 调用；版本上限审查修复原版发布不应要求再分配版本，显式新版本耗尽时返回冲突。损坏库内容由内部 `invalid_definition` 映射为公开 `conflict`，保留诊断且不自动重试；固定版本仍拒绝 bool／float。后端初轮 **58 passed、1 failed** 的新夹具误用顶层修订已修，相关 **63 passed**，最终新增库套件 **24 passed、1.53 秒**。
- 桥／目录／项目技能／脚本／权限七文件回归 **128 passed、33.95 秒**（`/tmp/stk-user-skill-focused.log`）；最终 Python 3.11／3.14 同范围各 **128 passed、51.17／51.55 秒**（`/tmp/stk-user-skill-311.log`、`314.log`）。3.12 完整回归 **3221 passed、24 skipped、2 deselected、1 warning、714.29 秒**（`/tmp/stk-user-skill-full-python.log`）。最后的目录名称上限修正由三版本桥端补验覆盖：各 **7 passed**，3.12／3.11／3.14 分别 2.14／3.12／2.12 秒（`/tmp/stk-user-skill-final-bridge.log`、`final-bridge311.log`、`final-bridge314.log`）；不把运行中已导入的旧 schema 当作最后修正的完整复验。
- 独立临时项目实测：4 线程提交 8 个新版本得到唯一连续的 2–9；同发布身份返回原回执。目录当前读取最多 1024 条有界摘要后分页，未读取完整快照；不能宣称 SQLite 只读取当前页。完整内容仅在选定详情／固定版本时核验。
- 原生首轮构建曾因同一行两次 gtest 宏产生重复标签失败，随后修正空图夹具和 keyword-only BridgeError.data 的注入。定向首轮 **32/34**：旧目录替身不接受 `user_library` 参数；另一个实际问题是 ordered_json 把 SQLite 回读后的字段顺序当作回执身份差异。修正替身及逐字段身份比较后，构建退出 0（`/tmp/stk-global-skill-desktop-build6.log`）；定向及必跑 **34/34、零跳过、11.16 秒**（`/tmp/stk-global-skill-desktop2.log`／`.xml`）。损坏回执查询保留原 publication_id；明确未找到才解除不确定状态。官方语言检查中英各 **2396 译文键、零问题**。
- 点击验收：CPU 真实鼠标事件，技能页 `a2` 最大化且项目技能详情已选中；英文 1× 1280×1800、中文 2× 逻辑 560×1800（物理 1120×3600），保存到本机库均 **1 次点击**，不改变源项目修订／历史。目标项目已打开且目录详情已选中时，固定版本 **1 次点击**，创建分析或明确填写映射后创建工作流各 **1 次点击**；分析参数整数 9007199254740993 与空输出保真，工作流只引用明确映射的目标表。冲突后明确新版本再 **1 次点击**。搜索／选择由夹具设置，这些分段不能相加声称跨项目全流程只有 3 点击；Viewer 求值次数均为 0。
- 客户端待确认发布身份保留于共享 AppStore，跨编辑器关闭、源项目关闭及桥重启仍能查询；应用退出后只记录 UUID，尚无自动持久恢复入口。库上限 1024 版本／64 MiB 内容／4096 回执；无删除与远端共享界面。
- 完整原生 **1688/1688、零失败／错误／跳过、407.66 秒**（`/tmp/stk-global-skill-native-full.log`／`.xml`）；Linux 必跑 **858/858**，另 360 个 render 场景全部通过。随后审查发现合法分析方法名称可达 4096 字符而目录响应仅容纳 512，已将 schema 对齐 4096 并补三版 Python 回归；增量构建成功，最终技能定向及必跑 **34/34、零跳过、7.76 秒**（`/tmp/stk-global-skill-final-schema.log`／`.xml`），未重复完整原生。
- 源码暂存 gitleaks 使用 `.gitleaks.toml` 与 `--redact`，扫描 **141654 bytes、零发现**（`/tmp/stk-global-skill-source-gitleaks.log`），差异空白检查通过。新 CI 须等前头 Desktop 全部结束并推送后验证；本机技能库不等于远端共享服务，也不完成第 2 项真实窗口性能或第 3–8 项。当前机器只具 llvmpipe／lavapipe 软件渲染证据，后续真实窗口测试不能冒称硬件 GPU 验收。

## 2026-10-25：工作流技能发布与实例化（在研）

源码 `bc964f26fbc233381371bb55576f166a75995107`，基线 `3a1204f4a9fa0618d0523cdca85b8b5595d1fb5e`；本批跨平台 CI 尚待推送后验证。所有测试清空 `STK_TOKEN_PLAN_API_KEY` 并取消 `STK_TOKEN_PLAN_MODEL`，不发送模型请求。

- 新桥／脚本闭环首轮 **5 failed、8 passed**：新模板 `templates` 位于顶层，schema 错放到 `dependencies`，已修正。第二轮 **1 failed、12 passed**：新增测试使用错误的通用删除命令形状，改为现有 `delete_record {id}`。修正后新增桥套件 **5 passed、0.91 秒**（`/tmp/stk-workflow-skill-bridge.log`）。验证源根／子流程／分析均删除后仍能创建完整闭包、共享子流程仅复制一次、一次撤销／重做，以及缺失或非法映射／旧修订零写入；GraphWorker 没有启动。
- 扩大回归初次路径写错为 `tests/test_workflows.py`，退出 4 且 **未运行测试**；改为真实 `tests/test_project_workflows.py` 后扩大回归 **167 passed、30.74 秒**（`/tmp/stk-workflow-skill-expanded.log`）。补齐损坏元数据／名称长度／命令预算及真实工作器后，3.12 新后端与桥 **25 passed、4.89 秒**（`final-core.log`）；3.11／3.14 相关各 **84 passed、14.04／14.69 秒**（`311.log`／`314.log`）。后者包括真实 GraphWorker：源定义全部删除后，技能实例的合成仿真与分析两任务成功并产生三维 payload，没有跳过。
- 独立审查复现损坏字段类型为对象时技能列表抛 `TypeError`；修复类型前置检查并新增回归。闭包发布预检任何目标都无法容纳的 1000 命令上限；实际目标的集合／快照预算仍在同一事务内核验。
- 完整 Python **3190 passed、1 failed、26 skipped、1 warning、722.54 秒**（`/tmp/stk-workflow-skill-full-python.log`）；唯一失败为 `test_scripts_share_project_commands_conflicts_and_changed_notifications` 的接口清单漏列两个新增 RPC，补齐后脚本套件 **13 passed、7.08 秒**（`scripting.log`）。没有重复完整 Python；不得把首次完整运行写成零失败。
- 原生首轮相关 **107/109**（`/tmp/stk-workflow-skill-native.log`／`.xml`）：中英文新测试将 UI 顶左坐标直接传给窗口底左坐标事件，修正转换并立即断言选中目标。后续 **18/21** 暴露工作流目标匹配仅支持 breadcrumb，以及测试在详情读取中提前切选择。补显式项目句柄、保留原 breadcrumb 兼容和 busy 门禁，修正测试等待；映射输入另补旧 getter／setter 的完整身份和 key 存在检查。最终相关及必跑 **62/62、零失败／错误／跳过、27.38 秒**（`desktop-final.log`／`.xml`、`desktop-required.log`）。
- 最后编译退出 0（`/tmp/stk-workflow-skill-desktop-navigation-build.log`）。最终完整原生 **1681/1681、零失败／错误／跳过、401.51 秒**（`/tmp/stk-workflow-skill-full-native.log`／`.xml`）；按当前 Linux CI 第一组必跑规则核对 **851/851**（`full-required.log`）。语言目录 **2379/2379、零问题**。
- 实际点击：技能页 `a2` 最大化；英文 1280×1800、1×，中文逻辑 560×1800、2×。切到项目技能→展开工作流发布→选父流程→保存，共 **4 点击**；追加版本 **1 点击**、创建实例 **1 点击**、进入根工作流 **1 点击**；Viewer 不变。800 个数据依赖的映射超过 64 KiB 仍可编辑与恢复，来源列表只构造可见项（控件少于 100）；该结构用例不声称 800 表可作为单一运行的 case 表，也不替代真实系统窗口／GPU 性能验收。
- 源码暂存 gitleaks 使用 `.gitleaks.toml` 与 `--redact`：扫描 **147182 bytes、零发现**（`/tmp/stk-workflow-skill-gitleaks.log`）。前头 Desktop `40208002864` 已结束且 **5/5 成功**；Runtime `40208002879`、Docs `40208002935`、Secret `40208003007` 均成功。源码与交付记录分开提交，最终受管对象按 AOCI 流程维护；本批新 CI 尚待确认。全局目录、真实窗口／GPU 大项目验收和计划第 3–8 项仍未完成。

## 2026-10-25：子流程与工作流封装（在研）

基线 `fc14bc6ec945a2b5218323098a14eafa43614f18`；源码 `3a1204f4a9fa0618d0523cdca85b8b5595d1fb5e` 已推送 main；Desktop `40208002864` 已全部结束并 **5/5 成功**；Runtime `40208002879`、Docs `40208002935`、Secret `40208003007` 均已完成成功。
版本 2 接口与递归展开复用现有冻结运行；新内部展开格式与来源、实例路径随计划保存，旧格式／旧运行继续可读。
保存／校验不执行；全部测试清空模型密钥并取消模型变量，没有模型请求。

- 首轮 Python **35 passed、1 failed**（`/tmp/stk-subworkflow-first.log`）：旧“未知格式”夹具使用本次新增的 `/2`，已改为 `/99`。初次新增套件 **48 passed、2 failed**（`core.log`）：修正新桥字段缺失，以及测试误 patch 每次重新创建的服务实例；未放松产品校验。
- 桥接回归 **59 passed、6.69 秒**（`/tmp/stk-subworkflow-bridge.log`），补升级／分支／透传／真实工作器后 **63 passed、8.10 秒**（`bounds.log`）。扩大至工作流、分析、技能、桥契约、工作空间、归档和脚本，Python 3.12 **268 passed、72.26 秒**（`expanded.log`）。
- 后续依赖检查修正并复验：核心四文件 **71 passed、9.49 秒**（`/tmp/stk-subworkflow-final-core.log`），最终新增模板表约束／字节预算后组合模块 **29 passed、3.41 秒**（`extra-bounds.log`）。真实 VTK／GraphWorker 将嵌套合成模拟结果转为三维 payload；没有依赖缺失跳过。
- Python 3.11／3.14 早期核心各 **71 passed**，分别 **13.15／12.81 秒**（`/tmp/stk-subworkflow-311.log`、`314.log`）；后续最终四文件（含新增模板表／预算边界）各 **74 passed**，分别 **14.08／14.36 秒**（`/tmp/stk-subworkflow-final311.log`、`final314.log`）。
- 原生构建与新增真实桥测试编译均退出 0（`/tmp/stk-subworkflow-native-build.log`、`native-rebuild.log`）。原生相关 **90/90、零失败／错误／跳过、36.17 秒**（`/tmp/stk-subworkflow-native.log`／`.xml`）；WorkflowDraft 与 WorkflowEditorPython 必跑 **54/54**（`required.log`），现有三平台通配已包含新增用例。
- 桌面首轮 **90/94**（`/tmp/stk-subworkflow-ui-native.log`／`.xml`）：两项新测试把有序 JSON 的字段顺序当作语义差异，一项折叠面板错误地调用按钮回调；子流程导航暴露 `nlohmann::json` 到 `io::Json` 临时转换的悬空引用。修正断言、实际面板点击和导航对象复制后，四项复验 **3/4**，剩余为子页异步读取期间提前操作重命名。相关扩大回归 **115/116**（`ui-regression.log`）；补齐等待后新增五项复验 **4/5**（`ui-five.log`），父子导航已通过，新增 JSON 参数移除测试需等待候选校验完成后保存，已补等待并继续复验。
- 点击验收：CPU 实际鼠标事件；当前工作流已打开、选中 `cases` 表格步骤、右侧检查器可见。英文 1×、逻辑 1440×1800；中文 2×、逻辑 640×1800，侧栏宽度分别 560／560。点击“设为输出”→“保存”，共 **2 次点击**，得到版本 2 的 `rows ← cases.rows` 输出，项目修订只增加 1，Viewer 不变。不替代真实系统窗口／GPU 验收。
- JSON 默认值补测首轮 **2 passed、1 failed**（`/tmp/stk-subworkflow-literal-first.log`），证明形如 `$field` 的字面量被误当成字段引用。修正来源传播、显式 `$literal`、默认值移除和冻结过期判断后，Python 3.12 核心四文件 **78 passed、8.99 秒**（`literal-stale.log`）；3.11／3.14 各 **78 passed、13.69／13.53 秒**（`ui311.log`、`ui314.log`）。覆盖 `$field`、`$param`、`$literal` 字面量经多层调用后保持原值且没有虚假过期。
- 最终构建退出 0（`/tmp/stk-subworkflow-ui-stable-build.log`）；新增桌面五项及必跑 **5/5、零失败／错误／跳过、1.64 秒**（`ui-final-five.log`／`.xml`）。父子未保存草稿、重入复用、默认值文本迁移／撤销和 JSON 字面量移除后保存均已通过。中英 2364 键、零问题，补充[子流程使用说明](project-workflows.md#可复用子流程版本-2在研)。
- 完整 Python **3166 passed、24 skipped、2 deselected、690.10 秒**（`/tmp/stk-subworkflow-full-python.log`）。该完整运行启动后补充了冻结字段来源元数据及过期修正，因此最终相关代码另由上述三版本各 78 项覆盖；没有把运行中的旧导入状态当作最后修正的完整复验。
- 最终完整原生 **1674/1674、零失败／错误／跳过、398.37 秒**（`/tmp/stk-subworkflow-full-native.log`／`.xml`）；从 Linux CI 当前必跑命令提取表达式核对 **844/844**（`full-required.log`），工作流草稿／桌面必跑 **59/59**（`ui-required.log`）。新用例由三个桌面平台现有通配覆盖；本批跨平台结果尚待提交后的 CI。
- 覆盖重复／多层调用、冻结参数、删除子流程后执行、接口约束、精确大整数、原子升级与撤销、循环、修订漂移、大小边界、独立分支过期、空透传门禁。源码 AOCI 先复核四个 observe 测试路径，再按机器批次提交 12＋9 条完整语义更新；Verify／Check／Guide 均对齐、无恢复事务。暂存 gitleaks 实际扫描 **271348 字节、零发现**（`/tmp/stk-subworkflow-gitleaks.log`）。首次在暂存前启动的零字节扫描不算有效扫描；已在真实暂存完成后重做。新 CI 状态见本节开头；下一次代码推送须等该 Desktop 结束。当前交付记录变动尚未提交，待 CI 稳定后完成文档索引维护与记录提交；工作流技能封装仍待完成。

基线 CI 已核对：Desktop `40199278362` **5/5、全部完成成功**；Runtime `40199278388`、Docs `40199278457`、Secret `40199278445` 均完成成功。下一批推送的前代码头桌面门禁已满足；这些结果不覆盖当前未提交修改。

## 2026-10-25：用户分析技能（进行中）

基线 `e9f5fb6e255572d204a8a44c3204fac647913123`；本节记录当前用户技能交付批次。用户技能 `graph.document` 完整保存分析图、提交参数、输出选择和源项目／分析／修订／摘要。
同一 CAS 事务读取源并创建或追加版本；不替换目录技能、不自动执行，恢复旧版本后版本号仍递增。复用版本能脱离安装目录，随工作空间迁移。
原生入口复用保存分析读取器；输入名按保存参数解析，未绑定实际文件；旧来源按钮、晚响应与项目变化不能改投另一对象。未知节点可保存方法定义，执行仍按现有图服务校验。

- Python 首轮 **36 passed、1 failed**，`/tmp/stk-user-skills-python.log`；失败夹具删除了图参数必须具备的默认值，改为结构合法但引用未声明参数的绑定，继续验证发布拒绝且无写入。一次扩大命令误写不存在的 `tests/test_agent_tools.py`，**未运行任何测试**（`python-recheck.log`）；已改为实际 `test_agent.py`，未计作通过。
- 修正后相关 **77 passed、27.01 秒**（`/tmp/stk-user-skills-python-final.log`）；扩大技能／脚本／智能体／分析回归，Python 3.12 **145 passed、29.29 秒**、3.11 **145 passed、42.46 秒**、3.14 **145 passed、42.96 秒**，分别为 `python-expanded.log`、`python311.log`、`python314.log`。
- 新增真实 GraphWorker 验证：保存公开合成带符号场分析→发布用户技能→复制分析→冻结输入→改变原分析与删除原文件→明确运行，成功输出原参数 `K` 的三维 payload，原准备运行仍未启动。三 Python 版本各 **1 passed**（0.83／1.29／1.30 秒），`/tmp/stk-user-skills-real-run.log`、`real-run311.log`、`real-run314.log`。没有模型请求。
- 原生产品首轮构建退出 0；新增测试编译曾因把返回 void 的 refresh 放入断言失败，修正后构建通过。原生首轮相关 **24/28**，4 项新用例均在不合法的两段节点类型名处被结构校验拒绝；改为规范三段名称，未放宽产品校验。最终构建 `/tmp/stk-user-skills-native-fix-build.log` 退出 0，相关及必跑 **28/28、零跳过、4.81 秒**，`/tmp/stk-user-skills-native-recheck.log`／`.xml`。现有三平台 ProjectSkillsPython 必跑通配覆盖新增用例。
- 点击验收：CPU 事件测试；已打开项目且有一份保存分析，技能库页可见。英文 1×、1280×1200；中文 2×、逻辑 560×1200。点击“项目技能版本”→展开“从保存分析创建技能”→选分析→“保存为新的项目技能”，共 **4 次点击**；随后在同一选中技能／来源下追加版本 **1 次点击**。旧版本字节保留，项目修订各增加 1，Viewer 状态不变；切换来源后保留的旧按钮不写入。这不替代真实系统窗口／GPU 截图验收。
- 中英 **2347 键、零问题**，`git diff --check` 通过；完整原生 **1666/1666、零失败／错误／跳过、393.74 秒**（`/tmp/stk-user-skills-full-native.log`／`.xml`）；按 Linux CI 的完整必跑表达式核对 **836/836**，`/tmp/stk-user-skills-full-required.log`。源码 `fc14bc6ec945a2b5218323098a14eafa43614f18` 已推送；Desktop `40199278362` 5/5、Runtime `40199278388`、Docs `40199278457`、Secret `40199278445` 均已完成成功。

## 2026-10-25：图像附件与卡片缩略图（进行中）

基线 `e30150bb47c7064c945a4c561d99e02fdea5ae69`；源码 `e9f5fb6e255572d204a8a44c3204fac647913123` 已提交并推送 main。
JPEG／WebP／GIF／BMP／TIFF 在本地转成有独立摘要的 PNG；PNG 原样预览与 UTF-8 文本兼容入口保留。
原文件仍限 1 MiB、4096 单边／4194304 像素；新格式和缩略图依赖 visualization extra 的 Pillow（本机 12.3.0）。
按 EXIF 处理方向，多帧只显示第一帧并标明总帧数；原文件与显示像素分别校验，不复制源 EXIF／ICC／文本元数据。
缩略图最大 256 单边，每编辑器最多缓存 32 张；改修订／视图、关闭或重开不复用旧图，重新加载先释放旧图。
不改项目、Viewer 或运行状态；不是文档渲染、动画播放或完整 TIFF 多页浏览。

- Python 3.12 首轮附件／脚本 **59 passed，8.95 秒**，`/tmp/stk-image-previews-python.log`；覆盖格式、缩放、透明度、EXIF、多帧、源／显示双摘要、冻结内容校验、错误扩展名、越限、修订冲突、缺依赖和旧 PNG 路径。
- Python 3.11／3.14 附件／脚本／智能体边界各 **86 passed**（24.36／23.56 秒），`/tmp/stk-image-previews-python311.log`、`python314.log`。3.12 扩大桥／表格／脚本／智能体回归 **177 passed，27.76 秒**，`/tmp/stk-image-previews-python-recheck.log`；未宣称完整 Python 已通过。
- 原生构建退出 0（`/tmp/stk-image-previews-build.log`、`test-build.log`、`final-build.log`）；附件、卡片与读取控制器定向 **22/22、零跳过，4.00 秒**，`/tmp/stk-image-previews-native.log`／`.xml`；同范围必跑 **22/22**，`/tmp/stk-image-previews-required.log`。现有三平台必跑通配覆盖新增测试。
- 实际点击验收：CPU 事件测试、英文 1×、1440×1200，已有文件对象的看板卡片为起点；**1 次点击“加载缩略图”**后显示 256×128 合成图像，未进入详情或改变记录选择、项目修订、Viewer 数据／相机。切回网格释放纹理，再回看板不自动读取；新修订拒绝已排队响应和保留的旧按钮动作。另验证 BMP 转换后原生解码像素一致。CPU 点击与像素验证不替代真机 GPU 截图。
- 中英 **2341 键、零问题**；完整原生 **1662/1662、零失败／错误／跳过，386.38 秒**，`/tmp/stk-image-previews-full-native.log`／`.xml`。按 Linux CI 完整必跑表达式核对 **832/832**，`/tmp/stk-image-previews-full-required.log`（首次误选 Windows 命令得到 791 项，已纠正选择入口，未重跑或跳过测试）。收尾再次读取 XML 与日志确认计数，没有重复运行测试。
- AOCI 21 个受影响条目已分两批维护，3 个观察测试文件已复核确认；Verify／Check／Guide 对齐、complete=true、next_action=none。这是索引与源码的治理对齐，不代表全量模型认知校验通过。前代码头 `e30150b` 的 Desktop 已结束成功，满足本批推送前等待条件。
- 提交前暂存 gitleaks（`.gitleaks.toml`、redact）约 **157 KB、零发现**，差异格式检查通过。源码的 [Runtime 40196571054](https://github.com/sijintech/stk/actions/runs/40196571054)、[Docs 40196570995](https://github.com/sijintech/stk/actions/runs/40196570995)、[Secret 40196571044](https://github.com/sijintech/stk/actions/runs/40196571044) 已成功；[Desktop 40196571079](https://github.com/sijintech/stk/actions/runs/40196571079) **5/5 全部结束且成功**，包含 Windows、macOS、Linux、Linux 打包与干净容器冒烟。后续用户技能批次推送前的等待条件已满足。

## 2026-10-25：大项目分页接入（进行中）

基线 `fe083a3d4f7296182f178fa3e7390e5fb311cc07`；本批源码 `e30150bb47c7064c945a4c561d99e02fdea5ae69` 已提交并推送 main。
结构目录不读取单元格，记录页按同修订分页或稳定 UUID 定位；工作台消费独立记录页，选择最多补充一条共享缓存。
审阅另读完整基线；文件树只读索引与依赖。下方区分前一轮验证与原生首次打开接入后的新结果。

- Python 文件索引／目录树／输入快照／目录与记录页／表格查询共 **87 passed**：3.12 **2.90 秒**、3.11 **3.35 秒**、3.14 **3.03 秒**；日志为 `/tmp/stk-paged-project-python.log`、`python311.log`、`python314.log`。均清空产品模型密钥、取消模型环境变量。
- 最终构建退出 0，`/tmp/stk-paged-table-build.log`；原生表格／详情／审阅／文件树／交换／草稿恢复相关 **109/109、零跳过，22.10 秒**，日志 `/tmp/stk-paged-table-final.log` 与 `.xml`。必跑检查 **109/109**，`/tmp/stk-paged-table-required.log`；中英 **2336 键、零问题**，`git diff --check` 通过。
- 新增用例核对：编辑器页隔离、完整 int64／空值／未设置值、隐藏字段、取消／换表失效、部分共享缓存下的完整审阅基线，以及文件索引依赖求值不读无关单元格。
- 鼠标验收固定起点：CPU 事件测试、英文 1×、1440×1200，排序网格与详情并列可见，共享缓存只有原首行；实际 **1 次点击**当前页未缓存记录后显示正确详情，项目修订与 Viewer 保持。继续切换记录最多只有一条额外缓存，切回原缓存记录后释放额外记录。
- 首次打开接入后两次构建退出 0：`/tmp/stk-project-open-build.log`、`/tmp/stk-project-open-build-incremental.log`。扩大的原生相关回归 **249/257，85.96 秒**，`/tmp/stk-project-open-focused.log`／`.xml`；新增 `ProjectPagingPython` **5/5** 全部通过，包装桥主动禁止 `ProjectStore.snapshot`，验证 902 行仅初读 200、203 张表结构跨页、页外精确 UUID／缺失不回退、取消不改选择、删除后刷新和单条额外缓存。已加入三平台必跑。
- 首轮 8 项失败保留：上下文换到未加载表时空控件崩溃；示例计数误用缓存行数；导入／换表仍按同步读取断言；批次未加载；文件搜索在目录忙时丢失定位；导航被自动读页的 busy 拦住；对象定位仍用同步选择。对应修复在后续扩大回归中通过；该回归整体仍为 **262/268**，`/tmp/stk-project-open-recheck.log`／`.xml`，不能报作全绿。
- 后续仿真定向仍曾 **5/7**，两项精确复验 **1/2**；`/tmp/stk-project-open-result-fix.log`、`/tmp/stk-project-open-diagnosed.log` 保留失败。诊断确认导入会在目录和记录读取间改变修订（预期 3、实际 4），旧处理停止加载；结果入口还错误要求查询响应包含 project_id。前者现最多三次重新读取整组目录与记录，连续修改超限停止，后者按真实查询契约检查表／修订／记录／运行身份。只重试读取，不重放修改。
- 最新构建退出 0：`/tmp/stk-project-open-consistent-build.log`、`/tmp/stk-project-open-consistent-verify-build.log`；定向及必跑 **16/16、零跳过，40.59 秒**，`/tmp/stk-project-open-consistent-focused.log`／`.xml`。包含 8 项 `ProjectPagingPython`，一次并发修改恢复、持续修改有界停止，LAMMPS／MuFerro 原生流程、跨页工作流明确两条记录，以及脚本在 452 行表中选择末行且不改变布局／Viewer。中英 **2339 键、零问题**，差异格式检查通过。
- 较早跨页工作流用例曾遇到桥断连；后续两次精确复验、最新定向和下述完整原生中的该用例通过，但未取得断连的确定根因，不能据此宣称已证明同一缺陷被修复。
- 完整 Python：**3102 passed、1 failed、24 skipped、2 deselected、1 warning，673.76 秒**，`/tmp/stk-project-pages-full-python.log`。唯一失败是脚本操作清单的精确期望漏列新增的 `project.catalog` 与 `project.table.read`；保持精确集合比较并补齐这两项后，脚本及分页协议 **32 passed，7.29 秒**，`/tmp/stk-project-pages-python-recheck.log`。warning 是既有 Starlette/httpx 弃用提示；没有把跳过计为通过，也没有把局部复验改写成另一次完整套件结果。
- 首次完整原生：**1619/1656、零跳过，381 秒**，`/tmp/stk-project-pages-full-native.log`／`.xml`。37 项失败包括 32 项仿真图形夹具、导入及三项对象预览仍按同步记录加载准备状态；旧格式测试替身只拦截旧快照接口，未在目录读取时降级夹具。保留既有字段值、旧格式／备份、Viewer 保护断言，改为等待实际异步记录与绘制稳定，并扩充替身覆盖目录入口。
- 上述修正后构建成功，`/tmp/stk-project-pages-full-fixes-build.log`；37 项复验及必跑 **37/37、零跳过，15.38 秒**，`/tmp/stk-project-pages-full-fixes.log`／`.xml`，包含 32 项 OpenGL／Vulkan、中英、宽窄图形测试。已查看 `tests/app/out/project_batches_lammps_narrow_opengl_zh.png` 和 `project_simulation_lammps_vulkan_en.png`（本机构建目录）；不替代 Mac／Windows 真机验收。最终完整原生 **1656/1656、零失败、零跳过，391.15 秒**，`/tmp/stk-project-pages-final-native.log`／`.xml`；相关必跑 **342/342**，`/tmp/stk-project-pages-final-required.log`。最终中英 **2339 键、零问题**，`git diff --check` 通过。
- 后端首读测量：Python 3.12.14，2 表各 10000 行、8 列，公开合成文字；命令 `env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python tools/benchmark_table_query.py --rows 10000 --mode opening`。原始 `/tmp/stk-project-opening-benchmark.json`。完整快照 **7.473183 秒、107779725 字节 Python 分配峰值、46920072 字节 JSON**；目录＋200 条记录 **0.056649 秒、1766253 字节峰值、472556 字节 JSON**；元信息与首批记录逐项一致。启用 tracemalloc，运行时有并行编译；不含 SQLite 原生内存、RPC 封装或原生窗口，不能解释为桌面 RSS／帧率／端到端耗时。
- 工作空间预读现复用有类型的目录／记录读取器；按打开时的项目身份与修订读取全部目录和所选记录页，全部验证成功才替换桌面。缺失记录和修订冲突不回退到其他记录，不重试采用；新桥禁止全快照，旧桥保留兼容读取。归档仍备份完整数据库，分页缓存不裁剪导出内容。
- 工作空间及分页相关首轮 **23/24**，`/tmp/stk-workspace-pages-focused.log`／`.xml`。大项目用例在新窗口脚本服务尚未就绪时发起导入，被既有忙碌门禁拒绝；补充等待服务就绪，未放宽产品保护。重新构建退出 0，`/tmp/stk-workspace-pages-recheck-build.log`；定向及必跑 **24/24、零跳过，9.01 秒**，`/tmp/stk-workspace-pages-recheck.log`／`.xml` 与 `required.log`。三项新测试加入三平台必跑：204 张表、451 行的页外末行及精确 int64 恢复；修订冲突／缺失记录保留当前桌面并关闭新句柄；读页期间修改 Viewer 后拒绝采用。隐藏 Python 草稿保留，脚本和 Viewer 求值均未启动；首次只读两页目录及一页记录，另读首行证明归档没有丢失未缓存数据。此批直接调用恢复入口，未新增鼠标点击数结论。
- 原生 CPU 首屏测量已完成：可选目标 `stk-project-open-benchmark` 使用真实 Python 桥和默认 1440×1200、英文 1× 布局；同一公开合成数据库两表各 10000 行、8 列，以能力协商切换全快照／分页读取。交替顺序各运行 3 次，每次新建进程；测量时没有并行编译或测试。原始报告 `/tmp/stk-native-project-open-benchmark.json`；20 行冒烟通过。首次万行测量因基准把网格页大小错写为 200 失败，按实际独立网格的 500 修正断言后重跑通过，共享缓存仍只读 200。
- 上述 3 次中位数：从明确打开到第一帧网格有数据 **2.670650→0.448939 秒**；原生进程采样峰值 RSS **190.40→31.17 MiB**；进程树 RSS 和峰值 **257.14→108.29 MiB**；测量标记后至桥关闭的响应 UTF-8 字节数 **9.75→1.10 MiB**。两种模式均显示 500 条网格记录，项目总数 20000，首值和修订一致，脚本运行／Viewer 求值／协议违规／桥重启均为 0。分页共享记录为 200，全快照为 20000。
- 测量边界：CPU UI 使用替代文字度量，不含 GPU、真实系统窗口、IME 或桥启动；打开时尚可有 UI 元数据初始化响应。使用暖 OS 缓存，RSS 约每 5 ms 采样，进程树相加会重复统计共享页，不是 PSS；响应计数到关闭，范围宽于首帧计时。此夹具短文本与上方后端长文本不同，不能直接比较两个基准的绝对传输量。尚不能据此宣称真实窗口、其他平台或全部大项目路径已验收。
- 工作空间接入后的完整原生回归 **1659/1659、零失败、零跳过，386.77 秒**，`/tmp/stk-workspace-pages-full-native.log`／`.xml`；按当前 Desktop CI 的 Linux 必跑表达式检查 **829/829**，`/tmp/stk-workspace-pages-full-required.log`。中英 **2339 键、零问题**，`git diff --check` 通过。跨平台 CI 已成功，源码 AOCI 增量维护已对齐。本机完整 Python 的失败与定向复验已如上保留，未重复本机完整套件；本次未改 Python 产品实现。

- 提交前复核实际 XML：1659 项、零失败／错误／跳过；必跑日志 829 项，Python 定向日志 32 passed。暂存差异 gitleaks（仓库 `.gitleaks.toml`、redact）扫描约 478 KB、零发现，差异格式检查通过。AOCI 46 个条目增量维护与 15 个观察文件复核完成；Verify／Check／Guide 确认对齐，1050 条规模标签零不匹配、无恢复待办，未声称全量模型认知已验证。
- 本源码的 [Desktop 40193509900](https://github.com/sijintech/stk/actions/runs/40193509900) **5/5**（Windows、macOS、Linux、Linux 打包及干净容器冒烟）、[Runtime 40193509895](https://github.com/sijintech/stk/actions/runs/40193509895) **8/8**、[Docs 40193509904](https://github.com/sijintech/stk/actions/runs/40193509904)、[Secret 40193509919](https://github.com/sijintech/stk/actions/runs/40193509919) 均已完成成功。

原生 CPU 测量复现（Linux，产物不安装、不加入日常 CTest）：

```bash
cmake --build /home/mnemora/opt/stk-build/merge-check --target stk-project-open-benchmark --parallel 4
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python tools/benchmark_project_open.py \
  --binary /home/mnemora/opt/stk-build/merge-check/bin/stk-project-open-benchmark --rows 10000 --repeat 3
```

前提交的实际 CI 已结束：Desktop [40177991251](https://github.com/sijintech/stk/actions/runs/40177991251) **5/5 成功**；
Runtime [40177991233](https://github.com/sijintech/stk/actions/runs/40177991233)、Docs [40177991272](https://github.com/sijintech/stk/actions/runs/40177991272)、
Secret [40177991359](https://github.com/sijintech/stk/actions/runs/40177991359) 均成功，包含先前 Windows 换行修正的复验；下一次推送前置等待已满足。

## 2026-10-25：项目技能版本

源码提交 `073c608a271c4dea001a49432879f174f2afab7c`，基线 `c6c39f3856189530db983d3c6f4dba4704c477e4`。
前头 Desktop [40171064126](https://github.com/sijintech/stk/actions/runs/40171064126)、
Docs [40171064146](https://github.com/sijintech/stk/actions/runs/40171064146)、Secret [40171064141](https://github.com/sijintech/stk/actions/runs/40171064141) 均完成成功。
Runtime [40171064147](https://github.com/sijintech/stk/actions/runs/40171064147) **6/8 成功**，两个Windows客户端作业失败：
附件返回原始换行，而测试read_text会规范化CRLF。本批改用原始字节解码作预期，并按字节写出LF／CRLF夹具。
上一代码头桌面等待条件已满足；源码已提交；本批新 CI 待确认，不以本机结果替代Windows复验。

- 最终构建退出0，`/tmp/stk-skills-build.log`；链接完成后才测试。
- Python定向 **74 passed，17.28 秒**，`/tmp/stk-skills-python.log`；3.11／3.14同集合各 **74 passed，31.01／31.04 秒**，对应`/tmp/stk-skills-python311.log`与`python314`日志。
- 完整Python **3083 passed、24 skipped、2 deselected、1 warning，678.04 秒**，`/tmp/stk-skills-full-python.log`。warning为Starlette旧httpx TestClient弃用提示，跳过不算通过。
- 原生技能相关及必跑 **33/33、零跳过，7.62 秒**，`/tmp/stk-project-skills-native.log`、`.xml`和`/tmp/stk-skills-required.log`。8个ProjectSkillsPython用例已加入三平台必跑。
- 完整原生 **1639/1639、零失败、零跳过，375.61 秒**，`/tmp/stk-skills-full-native.log`与`.xml`。
- 16项技能OpenGL／Vulkan宽窄、中英图形测试通过，新增项目技能8项。已查看`project_skills_saved_narrow_vulkan_zh.png`与`project_skills_saved_opengl_en.png`（构建目录`tests/app/out/`）；不代表macOS／Windows真机GPU或输入法验收。
- 中英 **2336键**一致，`git diff --check`通过；源码暂存gitleaks按`.gitleaks.toml` redact扫描 **144.16 KB、零泄漏**。

固定起点为最大化技能区域、空白项目、已查看`stk.muferro.energy_trace@1`；en／zh_CN、1×／2×，逻辑宽560或1280、高1000。
“将此版本保存到项目” **1次点击**进入项目页，增加1个修订；目录选择属于起点准备，不称整个流程仅1次。
项目页已选该技能且更新的目录版本已载入时，“升级并保留旧版” **1次点击**保留两版和原始内容。
随后使目录不可用，“恢复此版本” **1次点击**恢复原摘要，再“创建保存分析” **1次点击**生成带来源草稿，各写入增加1个修订。
这些计数仅对应明确起点的按钮，不把程序准备新目录当作用户升级导航验收。
重新创建编辑器并恢复保存状态仍选择同项目技能；换新项目清选择且不写。Viewer保存状态保持、求值启动0、协议违规0。
“打开分析编辑器”只进入页面，仍须选择新建分析，不自动执行。

后端另验空读不建表、六内置技能、一次编辑撤销／重做、摘要漂移/CAS冲突、冻结深复制、损坏拒绝、
工作空间包往返后目录缺失仍可创建分析，以及技能表不作为工作流参数表。丢回执只读取原UUID，不重放。
上限为128条／4MiB，每条16版本／384KiB；保存方法定义，不包含节点实现、Python环境、说明包正文或科学输入。
读取与恢复不求值或加载插件；全部测试清空产品key、移除model环境，不发收费请求，不改端点、密钥和网络策略。
用户技能、自定义流程封装、子流程及直接技能执行仍待开发；本批不结束通用目标，PET新专项后移。

## 2026-10-25：附件详情预览

源码提交 `bc2896a89f2e357d30ea8bda3a246190604cc411`，基线 `b1673ee12dfe29722d6545463689948a66a8e75e`。
前头 Desktop [40167186317](https://github.com/sijintech/stk/actions/runs/40167186317) 已完成 **5/5 成功**，
Runtime [40167186293](https://github.com/sijintech/stk/actions/runs/40167186293) **8/8**、Docs／Secret 成功，满足本批 push 前等待条件。
新 CI 待推送后确认；不以旧头结果替代。

- 构建最终退出 0：`/tmp/stk-attachment-build-20261025.log`、`/tmp/stk-attachment-build-final-20261025.log`。最初编译缺少 `get_int` 默认参数，已补齐。
- Python 初期新测试暴露重复开启读事务及门面使用错误，分别去掉重复 BEGIN、改为明确打开项目后修正；定向 **75 passed，12.00 秒**，`/tmp/stk-attachment-python-focused-20261025.log`。
- Python 3.11／3.14 附件与表格相关各 **48 passed，3.14／2.76 秒**，`/tmp/stk-attachment-python311-20261025.log` 与 `python314` 对应日志。
- 完整 Python 首轮 **3052 passed、1 failed、24 skipped、2 deselected、1 warning，689.26 秒**，`/tmp/stk-attachment-python-full-20261025.log`。
  唯一失败为脚本操作清单漏列新方法，修正后完整脚本测试及附件测试 **25 passed，7.26 秒**，`/tmp/stk-attachment-python-final-20261025.log`。
- 完整原生首轮 **1622/1623、1 失败、零跳过，398.43 秒**，`/tmp/stk-attachment-native-full-20261025.log` 与 `.xml`。
  唯一失败为新损坏 PNG 用例限定 `PNG header:` 前缀；解码器可能在读取后续块时校验 CRC，改为检查 PNG 解码错误且没有图像。
- 最终原生相关 **59/59、零失败、零跳过，11.27 秒**，`/tmp/stk-attachment-native-final-20261025.log` 与 `.xml`；必跑检查 **59/59**。
  包含全部 4 个新增附件用例，已有 Linux／macOS／Windows 的 `TableWorkbenchEditorPython` 必跑规则覆盖；未放宽跳过条件。
- 最后两处修正仅是测试清单／断言；产品源码未变，未再重复完整回归。保留初轮失败，不把组合证据标为一次完整全绿。
- 中英文 **2318 键**一致、`git diff --check` 通过；源码暂存 gitleaks 8.30.1 按 `.gitleaks.toml` redact 扫描 **47.98 KB、零泄漏**。

固定起点：默认四区域 1440×1200、en／1×，公开合成文件已登记并绑定到当前选中记录的对象格，Viewer 已显示公开合成载荷。
选格与文件登记属于起点准备；鼠标点击“记录详情”再点“预览附件”，共 **2 次点击**。
文字原样显示 `<script>` 等标记；2×2 PNG 的解码像素与输入一致，纹理只创建一次且关闭详情释放。
项目修订、表和记录 UUID、Viewer 载荷及 payload／camera 序列不变，求值启动数为 0；关闭重开详情不自动读附件。
保持旧按钮并切换记录、延迟完成原请求后再回原记录均不会出现旧预览。

后端验证当前文件变化、完整冻结 SHA、同大小损坏、搬迁、UTF-8 边界截断、非普通文件、读取期间变化、
错误项目／缺失对象／不支持格式及冻结目录链接。Python 只检查 PNG 头与资源界限，原生负责完整解码。
图片验收使用真实 Python 桥、libspng 和模拟 GPU hooks；未新增真实 GPU 截图或 macOS／Windows 人工图片显示验收。
单文件最多 1 MiB，文本前 64 KiB，PNG 单边最多 4096、像素总数最多 4194304；当前索引文件读取现有字节而不刷新元数据。
不支持 PDF／视频、Markdown／HTML 渲染或卡片缩略图；本批不表示 P4 完成。
所有测试清空产品 key 并移除 model 环境，不发收费模型请求，不改端点、密钥或网络策略。

## 2026-10-25：看板拖动

源码提交 `752d1ea9016ff6730fa7cb3df4a22e9ecfd5a811`，基线 `35637ea5eb95b1922ff11d36814b0f1696cd898a`。
前头 Desktop [40163712446](https://github.com/sijintech/stk/actions/runs/40163712446) 已完成 **5/5 成功**；
Runtime [40163712511](https://github.com/sijintech/stk/actions/runs/40163712511) **8/8**、Docs／Secret 成功，满足本批 push 前等待条件。
记录／索引头 `b1673ee12dfe29722d6545463689948a66a8e75e` 的 Desktop [40167186317](https://github.com/sijintech/stk/actions/runs/40167186317)
已全部结束并 **5/5 成功**，包含 Windows CPU、macOS Metal、Linux 桌面、可重定位包及新容器冒烟。
Runtime [40167186293](https://github.com/sijintech/stk/actions/runs/40167186293) **8/8**、
Docs [40167186299](https://github.com/sijintech/stk/actions/runs/40167186299)、Secret [40167186297](https://github.com/sijintech/stk/actions/runs/40167186297) 均完成成功。

- 首次构建及最后一次增量链接均退出 0；`/tmp/stk-board-drag-build-20261025.log`、`/tmp/stk-board-drag-build-final-20261025.log`。链接全部完成后才测试。
- 定向 **64/64、零跳过，11.82 秒**，`/tmp/stk-board-drag-focused-20261025.log` 与 `.xml`。
- 完整原生 **1619/1619、零失败、零跳过，360.29 秒**，`/tmp/stk-board-drag-full-20261025.log` 与 `.xml`。
- 必跑检查 **64/64**，`/tmp/stk-board-drag-required-20261025.log`。新增 `ContainerDrag` 四例加入 Linux／macOS／Windows 必跑；三项应用用例由已有 `TableWorkbenchEditorPython` 必跑覆盖。
- 中英文 **2315 键**一致，`git diff --check` 通过。暂存源码 gitleaks 8.30.1 按 `.gitleaks.toml` redact 扫描 **46.40 KB、零泄漏**。

固定起点：默认四区域 1440×1200、en／1×，表格区域已选择保存的状态看板，三条合成记录，Viewer 已显示公开合成载荷。
从首张卡片文字拖入空的另一个状态列，**0 次额外点击＋1 次拖动**；从默认网格进入这个保存看板另需 **1 次点击**，不计入已在看板的起点。
移动中修订不变，左键松开后仅增加 1，准确写入该状态 UUID，另一记录的缺省值和共享选择不变；一次撤销恢复原状态。
Viewer 载荷、payload／camera 序列均保持，求值启动数为 0。原列拖放和 Esc 取消均无写入。

核心事件在 1×／2× 验证文字／背景拖放与空列下部命中，按钮和下拉框不被拖动抢占；
验证按下时回调跨帧保留、非左键不提交、仅一次提交，以及修订／分组漂移、禁用、消失、模态、弹出菜单、失焦、Esc、裁剪和遮挡。
真实桥用例另通过保留回调验证未知目标拒绝、缺省与 null 区分、旧修订／视图拒绝、跨编辑器草稿保护和派生状态只读。
这些类型与旧回调检查不是额外的人工鼠标验收；尚未宣称 macOS／Windows 真机拖放体验通过。

只修改当前页单张记录的单选分组字段，不重排卡片或跨页拖动；缺省／null 列只在已有对应记录时显示，仍可用状态下拉框设置。
无停留边缘定时滚动；富对象预览和首次大表快照仍待后续。本批没有 Python 实现、项目格式或桥协议变更，
测试清空产品 key、移除 model 环境，不发收费模型请求、不改变模型端点或网络策略。

## 2026-10-25：表格填充柄

源码提交 `b2b076d669e6089fd700d4ff02097aaee60adb0b`，基线 `d1493fa337b9768046a15b78d64a32796a1555be`。
前头 Desktop [40160203772](https://github.com/sijintech/stk/actions/runs/40160203772) **5/5 成功且全部结束**，已满足本批 push 等待条件；
Runtime **8/8**、Docs、Secret 亦成功，链接见下节。
记录／索引头 `35637ea5eb95b1922ff11d36814b0f1696cd898a` 的 Desktop [40163712446](https://github.com/sijintech/stk/actions/runs/40163712446)
已全部结束并 **5/5 成功**，包含 Windows CPU、macOS Metal、Linux 桌面、打包和新容器冒烟。
Runtime [40163712511](https://github.com/sijintech/stk/actions/runs/40163712511) **8/8**、
Docs [40163712431](https://github.com/sijintech/stk/actions/runs/40163712431)、Secret [40163712458](https://github.com/sijintech/stk/actions/runs/40163712458) 均成功。

- 首次构建失败来自新测试调用错误的模态接口，修正后完整重建退出 0；日志 `/tmp/stk-table-fill-build-20261025.log` 与 `build-final` 对应日志。
- 定向首轮 **56/57**：有序 JSON 键顺序导致对象断言失败；改为规范内容比较，值与身份未改。再次构建、目录暂存均退出 0，`/tmp/stk-table-fill-build-fix-20261025.log`、`build-catalog` 对应日志。
- 最终定向 **57/57、零跳过，8.34 秒**；`/tmp/stk-table-fill-focused-final-20261025.log` 与 `.xml`。必跑检查 **57/57**，`/tmp/stk-table-fill-required-20261025.log`。
- 完整原生 **1612/1612、零失败、零跳过，365.81 秒**；`/tmp/stk-table-fill-native-20261025.log` 与 `.xml`；新增必跑 **8/8**。`TableGrid` 与 `TableWorkbenchEditorPython` 已在三平台 CI 必跑集合，无需放宽跳过条件。
- 中英文目录 **2314 键**一致，`git diff --check` 通过。暂存源码 gitleaks 8.30.1 使用 `.gitleaks.toml` redact 扫描 **31.03 KB，无泄漏**。

固定起点：默认四区域布局、1440×1200、en、1×，三条合成记录、整数首行 `INT64_MAX`，Viewer 已显示公开合成载荷且未最大化。
单击整数格 **1 次**，再从右下角拖至第三行 **1 次拖动**；拖动中修订不变，松开后仅增加 1，后两行精确保留 int64，
选中记录不变；一次撤销恢复两个缺省格。Viewer 载荷、payload／camera 序列不变，求值启动数为 0。
核心控件另在 1×／2× 验证排序后模型行映射、矩形与向上／左重复、行标签排除；验证取消、版本／选择变化、禁用、模态、消失、非左键及离表松开，超限 1197 格整体拒绝、999 格完整交付。
真实 Python 桥还验证 null 与缺省、选择 UUID、对象链接、公式定义及同源行重绑定、外行引用不变、旧回调拒绝、混合批次不部分写入与草稿保护。

只作用于当前页已有记录，最多 1000 个目标格；类型、单位及选项须一致，不推断数列、不按列偏移公式字段。
静止指针定时滚动、看板拖动、富对象预览及桌面首次全量快照仍待后续。自动事件与既有图形回归不替代 macOS／Windows 真机人工体验验收。
本批没有 Python 实现或项目格式变更；测试清空产品 key、移除 model 环境，不发收费模型请求，不改端点或网络策略。

## 2026-10-25：工作模式布局

源码提交 `85630acbb04f419ac7a13b0d5f99e08990cd91f9`，基线为 `027798ff0d5ca914b947401d14c47e4787430133`。
本节记录提交前本机验证；随后记录／索引提交为 `d1493fa337b9768046a15b78d64a32796a1555be`。
该头 Desktop [40160203772](https://github.com/sijintech/stk/actions/runs/40160203772) 已全部结束且 **5/5 成功**，覆盖 macOS Metal、Windows CPU、Linux 桌面、可重定位包和新容器冒烟。
Runtime [40160203774](https://github.com/sijintech/stk/actions/runs/40160203774) **8/8 成功**；
Docs [40160203773](https://github.com/sijintech/stk/actions/runs/40160203773)、Secret [40160203795](https://github.com/sijintech/stk/actions/runs/40160203795) 均成功。
源码暂存 gitleaks 8.30.1 按 `.gitleaks.toml` redact 扫描约 **64.57 KB，无泄漏**。
推送前已复核前代码头 Desktop [40156836215](https://github.com/sijintech/stk/actions/runs/40156836215) 全部结束，**5/5 成功**。
构建 `/tmp/stk-work-mode-build-20261025.log`、最终增量 `/tmp/stk-work-mode-build-final-20261025.log` 均退出 0。
构建结束后运行定向 **72/72、零失败、零跳过，10.19 秒**；
证据 `/tmp/stk-work-mode-focused-20261025.log` 与 `.xml`，必跑检查 **60/60**。
新增 `WorkModeLayouts` 六例、`WorkModeLayoutClicks` 四例和 `TreeFixture.Arrangement*` 两例接入三平台必跑检查。
完整原生回归 **1604/1604、零失败、零跳过，371.84 秒**，
证据 `/tmp/stk-work-mode-native-20261025.log` 与 `.xml`；最终新增必跑 **12/12**。
中英文目录 **2313 键**一致，`git diff --check` 通过。本批没有 Python 实现变更，已有桥／工作空间整链测试随原生实际运行。

固定起点为默认四区域、1000×900 逻辑像素，en／zh_CN × 1／2 倍缩放，Viewer 已显示且无最大化区域。
通过真实指针事件点击 **视图 → 准备与运行布局**，共 **2 次**；再点击 **视图 → 结果分析布局**，共 **2 次**。
准备时显示 AI 并保留原 Viewer 实例；返回时恢复原分栏、比例和活动标签，求值启动计数为 0、脚本会话未建立。
这属于自动事件验收，不代表 macOS／Windows 真机人工验收；有数据相机、实际时间步与 IME 操作仍应按清单人工核对。

覆盖多次往返、隐藏 Python 草稿、Viewer 共享状态、重复类型与移动标签、添加区域、多窗口独立偏好、
普通布局／工作空间状态往返、旧布局默认值和五类损坏模式的原子拒绝，以及活动输入和关闭后的延迟回调。
区域与标签增删在两模式共享；保存模式的区域集合与当前不符时保留当前分栏，不恢复已关闭区域、不丢新草稿。
普通布局仍不是完整草稿备份，完整内容走 `.stkworkspace`；报告模式尚未实现。
全程清空产品 key、移除 model 环境，不发收费模型请求，不更改端点或网络策略。

## 2026-10-25：表格按需查询与平台修正

编辑器／工具交付提交为 `4f919c752a9f8472e9f736ff91234a935acf4e51`，已推送；
暂存 gitleaks 8.30.1 使用 `.gitleaks.toml` 并 redact 扫描通过。推送前复核 `76715e4` 的 Desktop 已完成 **5/5 成功**。
该新提交 Runtime [40154110795](https://github.com/sijintech/stk/actions/runs/40154110795) **8/8**、
Docs [40154110805](https://github.com/sijintech/stk/actions/runs/40154110805)、
Secret [40154110886](https://github.com/sijintech/stk/actions/runs/40154110886) 均成功。
Desktop [40154110887](https://github.com/sijintech/stk/actions/runs/40154110887) 已全部结束，结论 failure：Windows CPU、Linux 桌面、Linux 打包及新容器冒烟通过；
macOS Build 失败，`analysis_parameter_draft_test.cc` 的 `auto` 混合声明在该平台推导为不同类型。
原日志 `/tmp/stk-editor-macos-ci-20261025.log`；拆开分析与工作流测试各五处相同模式，本机重建退出 0，
`/tmp/stk-query-build-20261025.log`。这项修正未以 Linux 通过冒称 macOS 已通过。

本批后端查询及编译修正已提交并推送 `027798ff0d5ca914b947401d14c47e4787430133`。
推送前已确认前 Desktop `40154110887` 全部结束；暂存 gitleaks 8.30.1 扫描约 69.46 KB，无泄漏。
AOCI 完整批次 Apply 后 Verify／Check 证明治理对齐，Guide `complete=true, next_action=none`；根与 Meta 未改。
新 Docs [40156836343](https://github.com/sijintech/stk/actions/runs/40156836343)、Secret [40156836355](https://github.com/sijintech/stk/actions/runs/40156836355) 成功；
Runtime [40156836276](https://github.com/sijintech/stk/actions/runs/40156836276) **8/8 成功**；Desktop [40156836215](https://github.com/sijintech/stk/actions/runs/40156836215) 全部结束且 **5/5 成功**（macOS Metal、Windows CPU、三项 Linux 作业）。此前 macOS 编译失败已由本次 CI 验证修正。
相关 Python 3.12／3.11／3.14 各 **154 passed**（4.55／12.49／8.71 秒），
日志 `/tmp/stk-query-focused-20261025-2.log`、`/tmp/stk-query-python311-20261025.log`、`python314` 对应日志。
新增查询专门回归 **16 passed**（0.86 秒），包含随后增加的 1100 层离页依赖，
`/tmp/stk-query-regression-20261025-2.log`。覆盖坏缓存、跨表与循环、缺省／null／负零、旧格式、WAL 并发修订一致性、
大值离页与无关表不物化；读后库字节／缓存不变。
完整 Python：**3040 passed、22 skipped、4 deselected、1 warning，683.25 秒**，
`/tmp/stk-query-python-full-20261025.log`；命令为 `python -m pytest -m 'not desktop and not perf' -q`。
本次排除两个桌面标记用例，因此相较前轮跳过数少 2、deselected 多 2；本次收集之后新增的深链用例
已在最终 16 项查询回归以及 Python 3.11／3.14 单项补验中通过。
原生完整：**1592/1592、零失败、零跳过，370.81 秒**，
`/tmp/stk-query-native-20261025.log` 与 `.xml`；JUnit 的 skipped=0，包含修正后的两套历史测试。

性能复现（只创建并删除临时合成项目；不读取用户项目）：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  /home/mnemora/opt/stk-venv/bin/python tools/benchmark_table_query.py --rows 10000
```

Python 3.12.14，2 张表各 10000 行、8 列，其中 7 列为重复公开文字；offset=100、limit=200。
参考路径先 `snapshot()` 整项目再用原筛选／比较器分页，新路径为公开 `table.query`；两者记录和总数完全一致。
下表是**启用 tracemalloc 时**的耗时与 Python 分配峰值，不含 SQLite 原生内存，不等同于进程 RSS 或交互帧率。
原始报告 `/tmp/stk-query-benchmark-20261025.json`。

| 查询 | 全快照参考耗时／峰值 | 按需查询耗时／峰值 |
|---|---|---|
| 普通分页 | 7.3027 s／102.79 MiB | 0.0456 s／1.68 MiB |
| 数值筛选 | 7.6367 s／102.75 MiB | 0.6151 s／1.71 MiB |
| 数值倒序 | 8.1125 s／102.75 MiB | 0.8127 s／7.06 MiB |

筛选仍遍历目标表行；排序保留匹配行的排序字段，公式依赖按需要展开，最坏可达全表或多表。
桌面初始共享快照、粘贴规划和表格导出尚未全部改成增量读取；本批无 UI 交互变更，沿用下节固定起点点击证据，
不宣称百万行桌面验收完成。全程清空产品 key 并移除 model 环境，未调用收费模型或更改网络／端点。

## 2026-10-25：通用编辑器本机验收

基线 `7e0e6b1bc59ef252af72f9aca5f82a9708f7e0de` 加本批工作树；Ninja / RelWithDebInfo，
构建目录 `/home/mnemora/opt/stk-build/merge-check`。最终构建退出 0 后才启动完整 CTest，未并发重链测试程序。
所有测试均清空 `STK_TOKEN_PLAN_API_KEY` 并移除 `STK_TOKEN_PLAN_MODEL`；未更改端点、网络设置或调用收费模型。

| 项目 | 实际结果及本机证据 |
|---|---|
| 最终原生完整回归 | **1592/1592，零失败、零跳过，374 秒**；`/tmp/stk-general-native-full-20261025-2.log` 与同名 `.xml` |
| 编辑器必跑检查 | **164/164** 实际执行；`check_required_tests.py` 检查上述 XML，`/tmp/stk-general-native-required-20261025.log` |
| Python 完整回归 | **3025 passed、24 skipped、2 deselected、1 warning，684.97 秒**；`/tmp/stk-general-python-full-20261024.log` |
| Python 3.11／3.14 | 工作流、契约和项目桥相关分别 **49 passed**，7.87／7.48 秒；`/tmp/stk-general-python311-focused-20261025.log`、`python314` 对应日志 |
| 默认布局 | en／zh × 1／1.5／2 共六项在最终完整回归实际通过；生成阶段的六次 skip 只是更新金样，不算验证 |
| 前产品桌面 CI | `76715e4` 的 `38956471084` 本轮复核 completed/success，**5/5**；本批尚待提交，新 CI 未开始 |

保留失败与修正：初次定向 150/164；第二轮定向 161/164，工作流用例须明确放弃受保护草稿后才能替换标签，
另两例不能仅等项目修订变化，还须等异步详情字段控件就绪。最后三例 3/3 通过。
首轮完整回归 1586/1592，剩余六例均为默认布局金样差异；检查发现新增历史按钮使“三维”入口仅余 6 px（1×）。
将历史按钮从 4 单位缩为 3、定位按钮从 5 缩为 4，并断言五个导航／历史控件至少 3 单位宽。
修复后六个布局的新宽度断言通过，审阅差异只影响 `a3/header` 后更新金样；最终完整回归再验证全部通过。
失败证据为 `/tmp/stk-general-native-focused-20261024.log`、`/tmp/stk-general-native-focused-20261025-2.log`、
`/tmp/stk-general-native-last3-20261025.log`、`/tmp/stk-general-native-full-20261025.log`、`/tmp/stk-general-layout-check-20261025.log`。

点击验收使用测试中的真实指针事件合成，**不是操作系统真机人工验收**：

| 固定起点 | 实际点击与结果 |
|---|---|
| 英文 1×、1440×1200、表格区 `a4` 已显示三条记录的看板，目标 Date 字段隐藏 | **3 次**：打开记录卡→展开字段选择→选隐藏 Date；随后键入并明确 Save。保持原记录 UUID、只改所选字段；非法 URL 留稿，合法 URL 可保存，多选可撤销；Viewer payload／相机序列不变 |
| 同尺寸看板，记录详情已打开 | **2 次**：状态选择器→Wet；仅一次 CAS 修订，记录选择不变，一次撤销恢复，unset／null 分组仍分开；Viewer 不变 |
| 工作流已选步骤，note 参数输入仍活动且文字为 single click | **1 次 Apply** 收取当前文字并应用到本地候选；没有隐式数据库保存或运行，start 调用为 0 |

完整回归覆盖本地历史与文字输入门禁、恢复、归档、陈旧回调和类型保真。macOS／Windows 新代码 CI、
平台文件对话框、IME 与真实输入设备人工验收尚未完成；计划后续工作台、报告、训练、联邦和文献能力未据此宣称交付。

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

本轮是工具与文档交付，无 UI 修改，所以没有新增点击数或真机交互声明。
原始结果位于 `.ai-tools/reports/navigation/summary.json`、`health.log`、`index.log`、
`duplicates/jscpd-report.json`、`knip-web.json`、`knip-docs.json`。这些本机产物不进版本库。
测量是一次运行的 UTF-8 输出字节和墙钟时间；MCP 信封、工具定义和初始说明另计，不能换算为已节省 token 百分比。

## 2026-10-24：AOCI 完整接续与工作树维护

本轮范围是正式 AOCI 读取、当前工作树认知维护和状态交接；历史的完整读取前置阻塞已解除。保留既有产品改动，不提交、不推送。

| 验收项 | 本轮实际证据 |
|---|---|
| Git | fetch 后 main／origin/main 同为 `7e0e6b1bc59ef252af72f9aca5f82a9708f7e0de`；开始有 28 个修改路径，无暂存内容 |
| 完整传输 | AOCI MCP `0.1.0-rc21`；普通 Whole-Index 连续 21/21 块、1031/1031 条，正文 429566 UTF-8 bytes，机器估算 142832 tokens，结束标记已观察、Host 交付确认成功 |
| 严格认知校验 | Challenge **10/10**、覆盖率 100%、系统框架掌握度自评 90%；首次参数校验只纠正字段名一次，答案语义不变。此结果绑定维护前索引 `acb1f12f1d2214add146ffbf5efb7deedfe46a6a5de3bcd02f66f4e23716f08c` |
| 初始治理 | 16 条 code_stale、7 个 observe 测试路径待复核；结构有效，无未决事务／Recovery／第三方冲突。16 项既有技术跳过保持原判定 |
| Observe | 阅读 7 个测试路径及受影响行为后明确 acknowledge；后续 Guide 的 observed_pending_review=0、stage=authoring_required。确认指纹不表示测试已执行 |
| 正式维护与终态 | 使用无参数 Maintain 的完整机器批次及候选／源码 SHA 绑定写入；末批后依次 Verify、Aggregate Check、Guide，实际退出码和完整 JSON 归档为本节证据目录中的 final-verify／final-check／final-guide 文件 |
| 改动保护 | 本轮前后核对 22 个既有产品源码／测试文件 SHA；本轮不修复或重跑产品稿，已知原生编译失败仍待后续产品任务处理 |
| 边界 | 未读取密钥、未发产品模型请求、未改端点／网络／宿主／AOCI 配置；没有本轮 UI 点击、图形、材料或产品回归验收结论 |

CI 已重新查询：当前提交的 [Runtime 39598657750](https://github.com/sijintech/stk/actions/runs/39598657750) **8/8**、[Secret 39598658037](https://github.com/sijintech/stk/actions/runs/39598658037)、[Docs 39598657687](https://github.com/sijintech/stk/actions/runs/39598657687)，以及前产品 `76715e4` 的 [Desktop 38956471084](https://github.com/sijintech/stk/actions/runs/38956471084) **5/5**，均 completed/success。当前未提交工作稿没有新 CI，不据历史绿色替代其验收。

模型审查发现历史索引的“历史 UI 未接入”“参数摘要缺枚举／边界”“完整记录编辑与状态修改未完成”等表述已经落后于工作稿，更新为有源码依据的职责和约束；不将新增测试文本当作通过证据。词典、范围、预算与 Database 未配置状态保持既有治理事实。
证据目录 `/home/mnemora/opt/stk-validation/aoci-20261024/` 保存本轮源码 SHA、认知交付状态摘要、Observe 审查、机器批次及终态验证。维护后索引身份改变，本次 Challenge 不能证明新身份已经重新全量认知校验；后续 Run 按 AGENTS 加载当前索引。下列较早停止记录仅是历史证据。

## 2026-10-23：AI 上下文工具再次接续的停止记录

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

本轮相应结果与覆盖缺口：

| 验收项 | 当前实际结果 |
|---|---|
| AOCI | 当前宿主有 9 个已出现的工具；本轮执行 CLI Check，未建立新的完整模型认知，不把 CLI 结构／治理检查代替 Overview 或 Attestation |
| AOCI 状态 | `ok=false`、`structure_valid=true`、`governance_aligned=false`；pending_transactions=0、recovery_pending=false、third_party_conflict=false、network_accessed=false；observed_pending 只核实为 1 组 finding，未从本轮报告取得组内确切数量 |
| 材料 | 当前树 `tools/ai/dev.py`、`.serena/project.yml`、`docs/ai-development.md`、`.codex/config.toml`、根 `.mcp.json`、`.claude/settings.json`、`.claude/settings.local.json` 无文件；不据此推断全局配置或任意其他路径 |
| ZIP 查找 | 仓库 exit 1／0.158s，xcheng exit 2／22.821s（4 目录权限不足），tmp exit 2／0.233s（8 目录权限不足），均无匹配；这两个 exit 2 是搜索不完整，不算完整成功 |
| 准备和安装 | 交付包尚未取得，未读 README／manifest／patch；未执行 `git apply --check`，未创建独立工作树／应用补丁。Python 3.12、Node >=22.12、固定三工具版本及 Web 锁文件安装未验收 |
| index／health／真实客户端 | 均未执行；当前没有 Serena 工具匹配，不能判定其启动失败，也不能标记 Codex／Claude 客户端加载与符号概览／定义／引用验收通过 |
| 项目边界说明与两项查询 | 未按要求重新取证；TaskSpec 与 cameraSignature 均 0 次，尚无新定义／消费者／契约／状态／测试结论，不用历史摘要替代正式认知 |
| 原生代码 | 未配置或验收 C/C++ 语义解析、构建变体 compile_commands／clangd／宏／生成头，不能宣称完整语义覆盖 |
| 精简审查 | duplicates／Knip 均 0 次，无执行退出码、原始分析报告或实际候选；不自动删改／合并，不建立债务基线 |

计量范围为本次用户重提请求之后的准备工作：AOCI CLI Check **1 次／5.242 秒／stdout 17,245 bytes／stderr 0**，原始退出码 **1**。
文件名定位 **3 次 rg**，并行总耗时 **22.824 秒**；没有匹配不代表权限不足目录已查。上述工具耗时不相加冒充端到端任务时间。
Serena、两项目标查询、duplicates、Knip 各 **0 次**；未测量日常查询成本或上下文 token 收益。本次没有新的 Overview 块交付，不复用 2026-10-21 的传输量作为新结果。
原始 Check 在 `aoci-check.stdout.json`／`aoci-check.stderr.txt`，调用耗时／源码身份／退出状态整理在 `preflight-record.json`，治理 finding 分组在 `governance-counts.json`；精确文件名搜索范围、命令、退出码和权限缺口在 `material-search/material-search.json` 及同目录原始输出。
本轮没有运行分析，所以 `.ai-tools/reports` 没有本轮 duplicates／Knip 输出可交付；停止记录不是原始索引正文或聊天全文。

补充宿主诊断的限度：此前只运行本机 `codex --version`／相关 `--help`，确认被调用 CLI 为 0.163.0；这不证明当前宿主采用该二进制或其配置。未运行 doctor 检查、未读认证／全局配置／聊天日志、未调用 API 或修改配置。
[官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)分别定义 `model_context_window` 与 `model_auto_compact_token_limit`；本会话实际有效值尚未取得，不能由 AOCI 估算 token 数断言精确最小阈值，也不能证明单改阈值即可解除故障。
恢复仍需取得交付材料，并有当前宿主能够完成和保留正式完整认知的证据；不改门禁或用 Serena、旧收据补认知。四份文档的治理收尾同样待恢复前置后完成。

## 2026-10-22：连续受阻复核

2026-10-22 连续受阻复核：原始请求及随后两次续接均停在同一 AOCI 前置条件；本轮没有产品功能进展。
最新 `aoci check --json` 退出 1，`structure_valid=true`、`governance_aligned=false`；AGENTS 与 24 个原有非文档修改文件 SHA 未变化。
未再次全量加载、未修改业务代码或提交推送；现有停止记录的 AOCI 维护仍未完成。生产级表格／节点编辑器目标未缩小、未验收。
恢复需要能够完成并保留完整当前认知的宿主条件，再完成正式流程与维护；不以反复检查替代开发进展。
本轮证据：`/home/mnemora/opt/stk-validation/aoci-stop-recheck-20261022/blocked-audit/`。

上轮 goal 续接分类为无进展；本轮现场检查证据未改变下一步的受阻边界，不算验证等待或功能进展。
独立状态审查确认原始用户回合加两次自动续接达到三回合门槛；不标记完成或暂停。

## 2026-10-21：AI 上下文工具试用前置受阻

本轮结论：**仅完成准备检查与停止记录；AOCI 前置未满足，工具试用未验收，不提交、不推送**。以下是本次停点，不沿用较早成功记录作为当前认知。

- Git：本地 main／origin/main 均为 `7e0e6b1bc59ef252af72f9aca5f82a9708f7e0de`，与给定补丁基线一致；开始时已有 28 个修改路径，不能把当前主工作树当作干净补丁应用目标。未创建分支、独立工作树或 PR。
- 规则：已检查根 AGENTS；先前限定路径搜索仅发现根文件。本轮不改规则、模型端点／网络策略或 MCP 配置，不读取密钥，不发收费模型请求。
- AOCI 与 Serena 分开：AOCI MCP `0.1.0-rc21` 已可实际调用；Serena 尚未安装／调用验收，运行状态未知。预检语义过期 **12**、observe 待复核 **7**（不合并成 19 项语义漂移）；`governance_aligned=false`，`current_system_cognition_reliable=false`。
- 正式重载尝试 `ai-context-trial-20261021-formal-1`：21 块／1031 条，正文 429566 UTF-8 bytes。收到第 4 块后、第 5 块前发生宿主上下文压缩；已收前四块没有工具响应截断，但此前正文不再可靠保留，不能继续完成当前认知证明。未提交 Host 交付确认或 Attestation，也未发生本次 Attestation 判题失败。
- 遵用户明确要求停止：不循环重载，不沿用旧 Attestation／摘要／历史收据，不使用 Serena／源码／局部索引补全正式认知。压缩后只补读一次运行合同，未重新发起 Overview；没有修改 `overview_delivery.chunk_tokens` 或其他认知配置。该故障为宿主压缩，不能宣称减小单块即可解决总容量问题。

材料检查只读取文件存在性，不读配置内容：

| 路径／材料 | 本次实际结果 |
|---|---|
| `tools/ai/dev.py`、`.serena/project.yml`、`docs/ai-development.md` | 当前树无文件 |
| `.codex/config.toml`、根 `.mcp.json`、`.claude/settings.json`、`.claude/settings.local.json` | 所查常见项目路径无文件；不代表客户端其他层级配置状态 |
| `.cursor/mcp.json`、`.vscode/mcp.json` | 文件存在，未读取正文、未修改 |
| `STK_AI_Context_Trial_Review_20261021.zip` | 仓库根、`/home/mnemora/Downloads/`、`/home/mnemora/xcheng/sijin/` 三处未找到；其他位置未查 |
| ZIP 内 `README_ZH.md`／`manifest.json`／补丁及 13 文件 | 未取得、未检查；未执行 `git apply --check`／应用，不根据摘要重建 |

受前置阻塞的实际状态：

| 项目 | 结果／覆盖缺口 |
|---|---|
| Python／Node 前提及 Serena 2.1.0、jscpd 5.4.2、Knip 6.42.1 固定安装 | 未执行；现有版本亦未验收 |
| `index`、`health`、Web 锁文件安装 | 未执行，无退出码可报 |
| 真实 Codex／Claude 配置加载及 Serena 符号概览／定义／引用 | 未调用，客户端验收未通过；尚无可核实的重启续接配置 |
| Python runtime／Web／原生／插件结构说明 | 未重新取证，不以历史摘要补认知 |
| `TaskSpec`、`cameraSignature` 两项查询 | 均未执行；定义、消费者、契约和测试未形成新结论 |
| duplicates、Knip | 均未执行，无原始分析输出或退出码；不能判定候选报告、执行故障或零问题 |
| 最多三个精简候选 | 未审查；不删改、不合并实现，不接受新债务基线 |
| 原生语义覆盖 | 未启用 C/C++，未准备编译数据库／clangd 解析验收，不能宣称完整覆盖 |

准备成本和测量：Overview 预检 **1 次**，完整取块 **4 次**，压缩后 `aoci_rules` **1 次**；Serena／两个目标查询／duplicates／Knip 各 **0 次**。
前四块共 **83,356 bytes／171 条**，占总正文约 19.40%／总 Entry 约 16.59%；仅是已收传输量，不能作为有效认知覆盖率。
四次取块耗时分别约 9600／9992／9589／9730 ms，合计约 **38.9 秒**；首值近似，不包含其他准备或完整任务时间，不计算总任务耗时。
日常查询成本和上下文 token 收益均**未测量**，不从 AOCI 字节／估算 token 推算 Serena 收益。

证据在 `/home/mnemora/opt/stk-validation/ai-context-trial-20261021/`：`blocked-attempt-record.json` 为停止事实整理（不是原始 Overview、正式认知或 Attestation）；`file-inventory.txt` 为本轮存在性检查输出，`reporting-critical-review.txt` 为独立报告审查，`preexisting-document-changes.patch` 保留写停止记录前已有文档改动。
本轮没有运行分析，因此 `.ai-tools/reports` 下没有本轮 duplicates／Knip 原始报告，不能虚构报告路径或退出码。
四份现有文档只记录本次受阻事实；**AOCI 维护、Verify／Check／Guide 收尾未执行，治理未对齐，后续必须在前置恢复后完成**，本次不构成功能交付。
此前产品原生构建进程的实际终态为 exit 1，`analysis_parameters_editor_test.cc:701` 同行两次 GoogleTest 宏产生重复标签；这不是本轮工具试用测试，未重跑，不套用历史 CI 或测试数证明本地稿通过。
续接需要交付包实际位置，以及能完成并保留完整 AOCI 认知的宿主条件；届时按正式流程重新建立当前认知、处理已有漂移，再核对候选与基线，在规则允许的干净独立工作树先检查后应用。本轮不替用户修改前置要求。

## 2026-10-21：AOCI 当前宿主及工作树复核

- 基线 main／origin/main `7e0e6b1bc59ef252af72f9aca5f82a9708f7e0de`；实际发现 9 个 MCP 工具并成功调用，服务 `0.1.0-rc21`，动态加载已生效，无需重启。
- 完整 Overview：1031／1031 条、21／21 块、机器估算 142654 tokens，无截断；Host 交付确认，Challenge **9/10、pass**。读取覆盖与框架自评分开；当时治理有漂移，未宣称当前完整系统认知可靠。
- 当前未提交稿带来 8 项生产源码 stale、3 项 observe 测试变化。最初 Maintain 因 observe 待复核而 stopped，返回候选 0、正式索引未写入，且 pending/recovery/conflict 均为零；闭环证据保存在 `initial-maintain-zero-write-closure.json`。
- 阅读 3 份测试完整改动和 8 份生产文件及关联后明确 acknowledge，随后按新机器完整批次提交 8／8 条；applied、aligned=true、remaining=0、finding_count=0。Root／Meta 和范围策略未改变。
- 源码批次按 **Verify → Check → Guide** 顺序执行，均退出 0；structure_valid／governance_aligned 为 true、Check ok=true、Guide complete=true／stage=aligned／next_action=none。1031 条，missing／stale／orphan／unbaselined 和 observe 待复核均 0，预算违规和未决事务 0。
- Critical review 明确当前稿限制：undo/redo 模型 API 不等于 UI 接入；workflow 参数摘要缺 choices/bounds、文字未贯穿 save/run、恢复文字待修；`analysis_parameter_draft_test.cc:923` 有混合类型 auto 声明编译问题。新增 13 项 draft 单测及 3 项真实桥表格测试**未执行**，不算通过；索引任务没有运行产品构建／回归或 PET MD。
- 保留原 11 个 desktop 文件，开始/结束 SHA 核对 11/11 相同。首次索引 `fd73f48` 已提交推送；本次增量与相应未提交源码留在工作树，待产品节点修复／测试后一并交付，远端不发布脱离源码的索引快照。
- 重新核对已提交 `7e0e6b1`：[Runtime 39598657750](https://github.com/sijintech/stk/actions/runs/39598657750)、[Secret 39598658037](https://github.com/sijintech/stk/actions/runs/39598658037)、[Docs 39598657687](https://github.com/sijintech/stk/actions/runs/39598657687) 均 completed/success；前产品 `76715e4` [Desktop 38956471084](https://github.com/sijintech/stk/actions/runs/38956471084) **5/5 completed/success**。这些不覆盖本地未提交稿。
- [本机面板](http://127.0.0.1:43999/)实际 HTTP 200，已运行的同版本服务直接复用。访问凭据不写仓库；本机回环地址不能作为其他机器的公开链接。
- 本地命令清空 `STK_TOKEN_PLAN_API_KEY` 并取消 `STK_TOKEN_PLAN_MODEL`，无外部模型请求；证据位于 `/home/mnemora/opt/stk-validation/aoci-20261021-refresh/`。四文档更新后仍须按返回完整批次维护并再执行最终三项检查，最终原始结果保存在该目录 `final-*.json`。

## 2026-10-21：AOCI MCP 接入与首次索引

- 前置：main／origin/main 基线 `2bb0aba`；前产品代码 `76715e4` 的 [Desktop 38956471084](https://github.com/sijintech/stk/actions/runs/38956471084) 已 completed/success（5/5）。本轮未创建分支／PR、未合并无关工作。
- 接入：当前宿主动态重载后实际发现 9 个 AOCI MCP 工具，调用成功；无需 Agent 重启。服务版本 `0.1.0-rc21`，布局 Volumes v1 Root／Meta／Code，未配置数据库连接或 Database 卷。
- 覆盖：修正验收快照为 1050 index／2338 observe／171 exclude；排除计数包含实时运行产物，策略身份保持一致。1047 个源对象减 16 个确定性技术跳过，正式条目 **1031／1031**；不把 observe／exclude 算作语义覆盖。
- 作者化与 review：全部草稿由模型依据实际文件及必要关联撰写；327 条原生公开 API 全面核对，修复 25 个路径的名称／可见性错误。213 条 R 分隔符逐条确认，保留原有关系；另修专用 LAMMPS 节点关系和少量字段表达。240 项正式差异经受控完整批次全部写入，最终稿与正式条目逐条一致。
- 首次及修正后顺序执行 `aoci verify --json`、`aoci check --json`、`aoci index agent guide --agent codex --json`，均退出 0；修正后 structure_valid／governance_aligned 为 true，Check ok=true，Guide stage=aligned／complete=true／next_action=none。
- 修正后 missing／stale／orphan／unbaselined 均 0，pending_transactions=0、recovery_pending=false、third_party_conflict=false、network_accessed=false。机器预算 142654 tokens、healthy、违规 0；E scale 1031 条检查、错配 0。16 项跳过原因及完整原始结果保存在 `reviewed-verify.json`／`reviewed-check.json`／`reviewed-guide.json`。
- 宿主完整读取曾在合并输出时截断，已停止该认知链，未声称完整系统认知校验通过；这不等于上述索引完整性或对齐检查失败。
- 接入资产独立审查：原 AGENTS 规则逐字节保留，运行时日志／事务／UI 凭据不进入白名单；公开配置关闭 AI，未发现可证缺陷。生成的 AGENTS 备份移到仓库外，原初始化顺序恢复证据亦保留。
- 本轮只改索引与文档，未把旧产品回归数量当作新测试；本地 AOCI／校验进程清空 `STK_TOKEN_PLAN_API_KEY`、取消 `STK_TOKEN_PLAN_MODEL`，未发外部模型请求或读取产品密钥。
- 最终四文档变更后按完整机器批次维护，Verify／Check／Guide 再次退出 0、1031 条完整对齐；此时范围 1050 index／2338 observe／170 exclude（生成的 AGENTS 备份已移到仓库外，策略身份未变）。暂存 gitleaks 8.30.1 使用 `.gitleaks.toml`、`--redact` 扫描零发现；`git diff --cached --check` 与新增 4 项本地链接检查通过。MCP 搜索及三条精确读取冒烟通过，旧 `append_log` 错误已不在检索结果中。
- 交付：索引 **`fd73f48b8ab529e262b48e2a92ee233777435862` 已推送 main**；精确 [Runtime 39595993694](https://github.com/sijintech/stk/actions/runs/39595993694) **8/8 completed/success**，含 Linux 三版本、Windows 两版本、web、desktop 桥与 control 协议；[Secret 39595993567](https://github.com/sijintech/stk/actions/runs/39595993567)、[Docs 39595993557](https://github.com/sijintech/stk/actions/runs/39595993557) 均 completed/success。本轮未触发独立 Desktop 工作流，前产品代码仍为 `76715e4`。
- 本机证据目录：`/home/mnemora/opt/stk-validation/aoci-20261021/`（含 `critical-review/`）。[面板](http://127.0.0.1:43999/)实际 HTTP 200；仅回环服务，不是远程共享地址，带访问凭据的入口不写入仓库。
- 限制：技术跳过、观察／排除范围和未配置数据库均单列；索引不能替代源码、CI、真实模型／GUI或材料科学验证。后续受管字节变化后需按当前 Guide 再维护，产品待验收事项沿用既有记录。

## 2026-10-15–16：CSV／XLSX／JSON 与 `.stkworkspace`（76715e4跨平台CI全部通过）

- 前置：main/origin/main `4c5f1b3`，此前代码 `d03366e` Desktop 38725595367 **5/5 completed/success**，Runtime 38725595362 **8/8 success**；
  文档头 Runtime 38729204426 **8/8**、Secret 38729204398、Docs 38729204496 均成功。当前节点没有新建分支、PR 或合并无关工作。
- 实现：表格直接工具栏三格式预览／导入／导出，计算值交换、类型／单位／SHA／CAS、一次撤销；`.stkworkspace` 携带全部窗口和隐藏标签、
  参数与草稿、项目一致备份／冻结对象／结果、已打开 Python 和 Viewer 文件及已登记外部文件。独立模块声明资源，不从任意字符串猜测读取路径。
  导入目标须不存在，完整校验后采用，未知路径／缺失资源带诊断；凭据／端点／网络配置、依赖程序及活进程不迁移，恢复不执行工作。
- Critical review 与实际修复：Excel int64／15位精度边界／subnormal／负零文字保真；JSON unset/null、object 原项目来源；
  空目录清单、标准 macOS 系统别名、重复导出旧资源／项目根 aliases、typed opaque baseline、空项目／空表选择；
  旧 UI 回调／bridge session、deferred 同批旧树回调、真实窗口关闭与隐藏稿保护、只读模板默认值不写持久状态。
  恢复来源核对保留全部用户参数／窗口稿，排除三项只读 Viewer 元数据缓存；独立固定 payload 身份和 serial，真实同标签换图反例曾失败，修后通过。
  最后独立审查实修旧表格回调访问已分离 Bridge、待打开结果队列穿过工作空间采用；保留原排队意图并拒绝替换，不清除用户请求。
  分析草稿恢复重复读取会使草稿脱离原修订，已限制为单次来源读取；冻结运行、当前列表选择、结果浏览路径、非默认画布及选中节点分别恢复。
  已删除的分析仍可查看已有冻结运行；读取失败保留诊断与草稿，不重试执行，不恢复轮询或下载。
- Python：首次完整因 operations/catalog 分类不一致中止，修正工作空间为 desktop-only；一次实际完整 **3009 passed/1 failed/24 skipped/2 deselected /643.46s**，
  唯一旧 catalog 夹具漏三项 table.io 方法，补正后完整 **3010 passed/24 skipped/2 deselected/1 warning /639.79s**。
  后续可信根别名审查追加修正，最终完整 **3019 passed/24 skipped/2 deselected/1 warning /639.23s**；相关三版本各 **235/235、零失败／跳过**
  （3.11 7.10s、3.12 7.08s、3.14 7.28s）。24项跳过沿用15个既有offscreen probe、2个PySide6、2个可选MCP、2个STK_PERF与3个真实MuFerro配置项。
  中断／失败的原始日志均保留，未计为完整成功。
- 原生：首轮定向 **69/70 /47.87s**，Fresh 状态门禁实际拒绝；诊断单例记录 AnalysisGraph `new_preset` 只读默认写入，已移除。
  后续定向 **83/84 /22.01s**，Fresh 空 Viewer、非空 packed payload／全部 buffer／独立相机跨新 Bridge 恢复、同标签换图拒绝、
  X11／Wayland 三个真实窗口均通过；唯一 AnalysisParameters 新夹具试图销毁未保存稿，改为明确放弃原稿后恢复包内副本。
  后续 **87/89 /51.74s** 的两项分析参数恢复失败已修重复 get，并纠正科学夹具将绝对路径放入只允许相对路径的 source 参数的问题；生产 source 校验未放宽。
  最终编译 build13 成功；新增／原失败反例 **11/11、零跳过 /2.58s**，含三项分析稿、三项运行／结果、两项旧表格会话及三项恢复来源保护。
  此前结果页新增夹具曾用故意包含未声明参数的文档执行而得到 graph_error，已改为单独的有效文档和新冻结运行；原参数保真夹具保留。
  JSON 转换、缺失头文件、新测试宏标签及字符串／JSON比较的编译错误均已修。
  最终完整 **1539/1539、零失败／跳过 /358.17s**；本节点必跑checker **97次匹配／96个独立测试**，全部实际执行成功。
  初次人工checker用错一个完整用例名称而拒绝“no such test”，改成实际名称后通过，没有改测试或放宽通过判据。
- 实际点击（默认 1440×1200、Viewer 并列、项目已打开；路径键入和 Enter 另计）：CSV 导出 **3 次**；首次切 Excel／JSON 格式的导出各 **5 次**；
  JSON 已选格式的预览／导入 **4 次**。工作空间导出完成 **4 次**、关闭弹窗另 **1 次**；新会话导入 **6 次**，真实事件与计数断言已通过。
  中英文、900/1440宽度、GL/Vulkan **32/32 图形检查通过**；实际目检 Excel 窄窗和中文工作空间导入，修正通用“预览”及跨模式旧成功提示。
- PET 冻结证据：格式13与明确备份升级14各 **479 文件、75.8 MB**，导出→导入→再次移动均完整；离线复核各 **1/1**（2.69s／2.74s），
  最终系统别名修正后再次独立迁移与离线复核各 **1/1**（XML 2.642s／2.702s）。原项目 SHA 未改、11 handoffs／8 density points／25 O₂ COM samples。
  `software_complete=true`，`material_validation=false`，没有重跑 MD。
- 最终 wheel 离线构建和仓库外 `python -I` 安装冒烟通过：**643 成员、47901176 bytes**，七项生产模块／schema与源码逐字节相同，
  不含 archive／desktop；openpyxl 与 defusedxml 为核心依赖。真实三格式交换、int64／精度／null-unset／公式文字与类型回导通过。
  将 socket 连接和 Popen 改为抛错后，原资源删除及连续二次导出／迁移仍保持文件索引、冻结快照、UUID／修订／历史／相机／空目录，模型与 Runtime 请求为零。
  wheel SHA-256 `46be6989efa67e961981bf7e0bbdf4c8befd837d60316e3d9e095149c4f27f68`。
  sdist 离线构建 **896成员、48693234 bytes**，生产模块／schema、两指南／两契约、六测试及pyproject与构建时源码逐字节一致，无archive／desktop；
  SHA-256 `44670f4c07a89d31dbb8079f7292f632e9fb9aae6a4063e1d1fc825a0e573002`。
  源码包是补写本段成功结果之前的文档快照，构建时文档SHA保存在仓库外verification，避免包内记录自身SHA的循环；未冒称文档结果段也已存在于该包中。
- 规模与限制：表格文件8 MiB／64列／10000行，实际导入仍受1000命令（XLSX/JSON另1 MiB）限制；XLSX仅值交换、JSON不携带表达式或外部对象副本。
  工作空间默认8 GiB／20000成员、桌面状态8 MiB；不携带主机凭据／依赖／运行中进程，未知路径需明确接受不完整恢复。
  程序／JSON文本内部路径不作子串重写；字体、DPI、驱动和窗口定位仍受目标操作系统约束。
- 证据：原生原始 `/tmp/stk-portable-20261015/`，耐久副本 `/home/mnemora/opt/stk-validation/table-workspace-20261016-native/`（含32张截图与历史失败）；
  Python／包／PET 耐久副本 `/home/mnemora/opt/stk-validation/table-workspace-20261016-python/`。
  i18n **2289/2289、零问题**，16份Markdown的519个本地链接均存在；差异空白检查通过。
  暂存约590KB经`.gitleaks.toml`／redact扫描无泄漏；推送前再次核对`d03366e`桌面5项均completed/success，门禁满足。
- 代码 **`29e9fe9b9014da93411100e3f4f6951784743e62` 已推送 main**。
  精确头Secret 38838889114、Docs 38838889189已完成成功；[Runtime 38838889023](https://github.com/sijintech/stk/actions/runs/38838889023) **6/8成功，2/8失败，全部completed**。
  Linux3.11／3.14各3030 passed/11 skipped/4 deselected（540.57s／777.91s），3.12 3034/7/4（654.71s），各1warning；三矩阵新专项各166/166、PET各7/7、doctor／wheel／sdist／上传全成功，三个精确头artifact实际存在。
  Python桌面3 passed/6.33s、控制协议24 passed/11.97s、Web构建成功。Windows3.11／3.12各46 failed/2452 passed/94 skipped/317 deselected/34 errors（423.35s／500.07s），client入口因前置pytest失败未执行。
  原因是工作空间自有staging只读fd上fsync返回EBADF，以及DirEntry.stat与Path.lstat的Windows身份值不等；[Python官方说明](https://docs.python.org/3.11/library/os.html#os.DirEntry.stat)明确Windows DirEntry的st_ino／st_dev／st_nlink为0。
  另两项Excel边界测试因32768字符自动参数ID撑爆Windows环境变量长度，业务体尚未运行；改短ID后原边界值与拒绝断言保持。
  最小生产修正仅自有staging使用r+b同步、扫描统一Path.lstat，不跳fsync、不删身份字段、不放宽源变动／链接／无覆盖。
  三项确定性Windows模拟修前2 failed/1 passed、修后3/3；相关三版本各238/238（7.04／6.90／7.11s），原生迁移 **21/21、零跳过 /3.64s**。
  修正完整Python **3022 passed/24 skipped/2 deselected/1 warning /640.05s**，无失败；原3019及Windows失败证据保留。
  [桌面38838889641](https://github.com/sijintech/stk/actions/runs/38838889641) Linux **1539/1539 /405.43s**，新必跑检查和发布包／全新Ubuntu解包启动成功。
  macOS CPU **983/983 /367.11s**、Metal **226/226 /443.54s**均成功且零跳过；required gate因`ViewerWorkspace.*: no such test`失败，后续Mac打包／解包启动未执行。
  原Viewer CPU目标只有app标签，Mac／Windows的unit／wm／ui／bridge／project筛选未选中这8项；正在拆独立纯CPU目标补unit标签，不删除或放宽必跑checker。
  Windows桌面 **918 passed/10 failed/928 /806.61s**；其中两个跨包草稿明确报告项目签名不等，另8项在共享导出等待中超时，尚未进入恢复断言。
  原生表格8+1、WorkspaceTree3、WorkspaceDesktop5与运行恢复3项均通过；Windows必跑gate因前置CTest失败未执行，未冒称通过。
  首轮桌面 **3/5成功、2/5失败，全部completed**，Windows结束于`2026-10-16T02:50:06Z`，后续代码推送门禁满足。
  初次本机标签修正的CPU筛选993/993通过，但checker仍拒绝漏选的ViewerWorkspace；gtest属性中的复合标签被拆分，改为独立目标的单一unit标签，不放宽checker。
  最终统一build15成功，按原Mac／Windows筛选的完整本机CPU **1001/1001、零失败／跳过 /133.79s**；required checker **41/41**，8项ViewerWorkspace全部实际执行通过。
  修复后的新wheel **47901296 bytes／643成员**、离线构建与仓库外三格式／连续迁移冒烟通过，七项生产模块／schema逐字节一致；
  SHA-256 `e9d00a80b40503c69b706600115199f3ed72764763575539e40354d9511c9218`，旧包作为首轮历史快照保留。
  修后PET格式13／明确升级14各479文件、迁移完整，离线各1/1（XML2.716s／2.523s），原DB SHA未变；仍为software_complete=true／material_validation=false，没有重跑MD。
  独立CR确认两处后端修正保留完整源签名／目录／修订复核、链接拒绝、强制fsync及原子无覆盖发布，新增反例可区分原Windows缺陷。
  新sdist离线构建 **48695715 bytes／896成员**，七项生产模块／schema和12项构建时源码／指南／契约／测试逐字节一致，无archive／desktop；
  SHA-256 `348d1d5f28910bd9337d04944579fdd507c75b5c12171b8b9b2032b934f72e84`，文档快照与包外自身SHA记录遵循上文同样规则。
  修正证据 `/home/mnemora/opt/stk-validation/table-workspace-20261016-ci-fix-29e9fe9/`（含native子目录）；本机原始CPU日志另在`/tmp/stk-portable-20261015/`。
  修正i18n2289/2289零问题，6份Markdown的348个本地链接均存在，差异检查通过；暂存约13KB经配置化redact密钥扫描无泄漏。
  推送前重新读取精确旧头Desktop attempt1为completed/failure，updated_at为2026-10-16T02:50:07Z；远端main仍29e9fe9，门禁满足。
  修正 **`2299b2a6f79c67b15ce90a9d9aa226c4b28c4869` 已推送 main**，精确修正CI结果待收口；未在旧代码桌面仍进行时推送。
- 第二次精确[Runtime 38943609861](https://github.com/sijintech/stk/actions/runs/38943609861) **6/8成功、2/8失败，全部completed**。
  Linux3.12 **3037 passed/7 skipped/4 deselected/1 warning /625.35s**，3.14 **3033/11/4/1 /659.68s**，3.11 **3033/11/4/1 /592.39s**。
  Windows3.11 **3 failed/2530 passed/95 skipped/317 deselected /425.51s**，3.12 **5 failed/2528 passed/95 skipped/317 deselected /826.27s**，不再有首轮EBADF／身份误拒／长ID错误。
  三项路径夹具将宿主Windows绝对路径标为external:posix，生产校验正确拒绝；两项3.12专属失败由扫描替身只有上下文接口、无法供stdlib清理器迭代导致。
  只修改两份测试：POSIX与Windows来源明确声明，原数据库／父目录拒绝保留，并补错类型拒绝；扫描替身完整实现迭代／close／上下文协议。
  三版本相关 **103/103、零跳过**（3.11 2.16s、3.12 2.14s、3.14 2.25s），未修改生产路径解析、校验或其他运行文件。
  第二次[Desktop 38943609849](https://github.com/sijintech/stk/actions/runs/38943609849) **4/5成功、1/5失败，全部completed**，Windows于2026-10-16T18:32:05Z结束。
  Mac CPU **991/991 /311.72s**、Metal **226/226 /400.55s**，含8项Viewer恢复、required gate693匹配及Mac应用包／解包启动成功；Linux **1539/1539、零跳过 /371.59s**，两项发布包作业均success。
  Windows原生 **926 passed/2 failed、零跳过 /452.25s**；两项失败均为测试对迁移路径的字符串／map key比较不兼容混合斜杠，导出导入已完成。
  审查同时发现8项ViewerWorkspace目标仍被POSIX fake目标条件挡住，Windows未构建，不能用本机CPU筛选通过宣称其Windows覆盖。
  本轮改用独立可移植同步payload测试桥，保留unit标签与全部必跑检查；路径比较保留数据库baseline／草稿／单次读取／不执行等原断言。
  第二次Secret 38943609965与Docs 38943610085均completed/success；前代码桌面推送门禁现已满足。
- 本轮跨平台夹具收口：统一build16／17成功，定向 **10/10、零跳过 /1.99s**；完整原生 **1539/1539、零失败／跳过 /1300.44s**（本次串行执行，不作性能比较）。
  本节点required checker **74/74**，含32张中英文GL/Vulkan表格／工作空间图形、两种真实窗口及8项Viewer恢复；CPU筛选登记1001项，8项Viewer均为unit。
  Critical review核对路径以文件语义比较，数据库baseline仍逐字节／类型匹配；同步payload测试桥没有网络、Python或作业执行能力，Windows目标不再依赖POSIX fake。
  七项wheel生产模块／schema SHA与2299b2a已验包相同；未改生产解析、运行权限或端点。证据保存在`/home/mnemora/opt/stk-validation/table-workspace-20261016-portable-tests/`。
  新sdist离线重建 **48697258 bytes／896成员**，七项生产模块／schema及12项构建时源码／测试／契约／文档逐字节相同；不含archive／desktop。
  SHA-256 `6e2e4d6941b44baed6fb7b9f20e00c5e0cd03457f066051960712562773c1995`；包为写入本段自身SHA之前的文档快照，构建时文档摘要保存在仓库外verification。
  i18n2289/2289零问题，六份Markdown350个本地链接存在；暂存改动经`.gitleaks.toml`／redact扫描无泄漏。
  推送前再次核对HEAD／origin/main仍为2299b2a，其Desktop5个job全部completed；精确新提交CI继续补记，Windows尚未记为成功。
- 测试修正 **`070f81e76d4109d6df98a266ffc67036621e2918` 已推送 main**；精确[Runtime 38952649174](https://github.com/sijintech/stk/actions/runs/38952649174) **8/8 completed/success**；[Desktop 38952649245](https://github.com/sijintech/stk/actions/runs/38952649245) **5/5 completed/success**，发布包与全新Ubuntu解包两种GPU后端冒烟已通过。
  Secret 38952649187与Docs 38952649179均completed/success；本轮原生与源码包证据在上述portable-tests目录，不覆盖前两轮历史。
  新源码包在仓库外解压，python -I且禁用pytest自动插件，明确断言workspace模块来自解包目录；迁移／路径夹具 **103/103、零跳过 /2.16s**，没有回落工作树。
  精确Runtime的Windows3.11／3.12各 **2533 passed/95 skipped/317 deselected**（541.69s／428.79s），无失败／错误；前两轮夹具问题均修复。
  Linux3.11／3.14各 **3033 passed/11 skipped/4 deselected/1 warning**（606.20s／530.36s），Linux3.12 **3037 passed/7 skipped/4 deselected/1 warning /657.82s**；五矩阵完整日志与计数保存在ci-070f81e。
  Linux原生 **1539/1539 /386.60s**；Mac CPU **991/991 /291.49s**、Metal **226/226 /347.72s**；Windows **936/936 /369.08s**，全部零跳过。
  实际下载Linux／Mac三份JUnit核对零失败／跳过；Windows完整日志逐项核对8个ViewerWorkspace全Passed，required gate **673**匹配成功（Linux **717**、Mac **693**）。
  Linux32张GL/Vulkan、Mac16张Metal新表格／工作空间图形、X11／Wayland真实窗口、Mac应用包解压启动均成功；所有job于2026-10-16T19:34:29Z前结束。
  完整元数据、原始日志、JUnit、截图与python-counts／native-junit-summary保存在portable-tests/ci-070f81e；下载网络超时重试不计作CI失败。
- 视觉复核修正导出提示两处中英文文案：“已安装窗口 / installed window”改为“已打开窗口 / open window”，准确描述用户当前打开的窗口。
  build18完成，i18n **2289/2289、零问题**，导出中英文宽窄GL/Vulkan **8/8、零跳过 /11.67s**；目检中文900宽度完整显示。
  八张新图另存native/copy-frames，不覆盖070f81e的32张图形证据。070f81e桌面于2026-10-16T19:34:29Z全部结束；i18n2289/2289、350个本地链接、暂存配置化redact密钥扫描通过。
  文案修正 **76715e45713554b2fa5619e615e5db62795e33d6** 已随验收文档推送main；不改状态格式或执行逻辑。
  精确[Runtime 38956470955](https://github.com/sijintech/stk/actions/runs/38956470955) **8/8 completed/success**，Secret 38956470972／Docs 38956470956均成功；[Desktop 38956471084](https://github.com/sijintech/stk/actions/runs/38956471084) **5/5 completed/success**，Windows于2026-10-16T20:14:24Z结束，后续推送门禁满足。
  Windows3.11／3.12各2533 passed/95 skipped/317 deselected（500.18s／667.49s），Linux3.11／3.14各3033 passed/11 skipped/4 deselected/1 warning（587.54s／538.91s），3.12 3037/7/4/1（717.35s）；五矩阵日志已保存。
  最终Linux **1539/1539 /417.68s**、Mac CPU **991/991 /363.16s**与Metal **226/226 /372.44s**、Windows **936/936 /447.98s**，全部零失败／跳过。
  Linux／Mac三份JUnit再次逐项核对；Windows从完整workflow日志包提取，8个ViewerWorkspace全Passed、required gate673匹配成功，Linux／Mac gate717／693亦通过。
  32张GL/Vulkan、16张Metal新图形、真实X11／Wayland窗口、Linux／Mac发布包与全新目录解包启动均成功；目检CI中文窄窗已使用新提示且完整显示。
  最终元数据／日志／JUnit／截图／python-counts／native-junit-summary保存在portable-tests/ci-76715e4；Linux图形下载重试存linux-frames-retry1，Windows单job下载超时改取完整日志包，不混淆为CI失败。
  Critical review补核对编辑器装载先保留各自本地视图／稿件、采用阶段统一绑定项目选择；新目标目录浏览使用SaveFile指定未创建名称，保留后端不覆盖约束。
  本轮功能与文案验收完成；前述大小／命令预算、未知路径、凭据／环境／活进程和原始程序文字路径限制保留，PET仍为software_complete=true／material_validation=false，无MD重跑。

## 2026-10-15：本地科研多维表格（`faf3a44` / `d03366e`，修正提交跨平台CI全部通过）

- Git/CI 前置：干净 main/origin/main `73e4fbe`；Runtime 38679106858 **8/8**、Secret 38679106815、Docs 38679106830 全成功。
  上一代码头 `2e331ca` 桌面 38675881571 **5/5 完成成功**，满足本节点推送门禁；未新建分支/PR或合并无关工作。
- 边界：本地科研多维表格，格式 14（旧 13 可读、明确备份升级）；共享项目服务，不改模型端点/密钥/网络/任务授权。
  所有测试清空 `STK_TOKEN_PLAN_API_KEY` 并取消 `STK_TOKEN_PLAN_MODEL`，未发收费请求；功能与限制见[设计](design/multidimensional-tables.md)。
- Python首轮实际 **22 failed、2814 passed、24 skipped、2 deselected / 533.71s**；全是 PetStudy 写死格式13，已修13/14兼容。
  后续因真实审查修复中断的两次全套保留日志，不计完整通过（604pass/1skip；1456pass/7skip/2deselected）。
  最终相关三版本各 **127 passed、19 deselected、零跳过**（3.11 13.21s、3.12 12.47s、3.14 13.41s），含36项新增表契约。
  XML `/tmp/stk-table-final-acceptance-related-{3.11,3.12,3.14}.xml`；完整最终 **2853 passed、24 skipped、2 deselected、零失败 / 642.94s**，XML `/tmp/stk-table-python-final-acceptance.xml`。
  新表契约36/36、PET研究42/42及PET原生接口9/9均实际通过；24skip沿用15个既有offscreen probe、2个PySide6、2个可选MCP、2个未开启STK_PERF及3个未配置真实MuFerro前缀。
- 原生首轮定向 **66/70**，所有13个通用网格/10个控制器及20个新软件GPU截图通过；4项失败为外部网格与定义编辑器可见 UUID 未同步，
  已增加 `set_visible_records` 修复保存/重载/删除，并保留失败与断言，XML `/tmp/stk-table-20261015/targeted1.xml`。
  本机构建编排曾误重入，旧链接看到正被重写的静态库而失败；结束两进程后统一串行重建，不计为源码编译成功或测试通过。
- Critical review 修复与反例：TSV子矩形/多行引号、全表排序而非当前页本地排序、共享稳定选择、异步连续录入、选项 UUID 重排/删除，
  取消/重建弹窗旧按钮和绑定、公式定义保留、布局严格嵌套校验、对象目标表与最终 Viewer 消费门禁、已有kind限制保持，
  options-only撤销的缓存失效、非法空view、URL控制符、同SHA快照来源身份、分组先分页与候选可读标签。
- PET 实际证据副本（原项目只读保留）：格式13 **1 passed/2.72s**，明确备份升级14/rev152 后 **1 passed/2.68s**；
  `/tmp/stk-table-real-pet-offline{13,14}.xml`。验收阻断Runtime执行，没有重复 MD，不把软件成功当物性验证通过。
- 当前 i18n **2254/2254、零问题**，差异空白检查通过。首轮完整原生实际 **1423/1428、无跳过 / 330.19s**（`native-full.xml`）；5项旧夹具仍假定默认详情展开、旧widget路径或降级时未移除新表。
  保留草稿、脚本选择/独立筛选、跨窗和备份原断言，修正异步等待/显式详情/旧DDL；恢复同项目切表时每实例搜索条件。
  第二轮定向实际82/84（`targeted3.xml`），余两项等待未驱动frame/独立查询，继续修正；新增空日期、重名选择、布尔缺测显示与类型筛选控件回归。
  第四轮定向 **86/86、零跳过 / 28.69s**（`targeted4.xml`），原五项失败和新 CSV 界面全流程均通过。
  独立审查再发现单叶过滤视图追加条件会丢原条件，修复后新增真实桥反例 **1/1、零跳过 / 0.66s**，保留嵌套组而非重写为新叶。
  最终统一构建成功，完整 CTest **1432/1432、零失败、零跳过 / 339.17s**（`native-full-final.xml`）；新增必跑检查 **65/65**，含中英宽窄/focus/看板/卡片20张GL/Vulkan截图。
  新增测试已接三平台CI必跑，不靠跳过/取消或放宽原行为断言。代码 **`faf3a44af0303af1e5b597d40ad927e8e02bd98d` 已推送 main**；推送前再次核对旧桌面 38675881571 全5项completed/success，首轮精确代码头 CI 实际结果见下。
- wheel/sdist 离线构建、仓库外安装冒烟成功：三新增服务模块与 bridge schema 在两包和安装目标中均与源码逐字节一致，均无 archive；
  sdist 含最终表格契约与新增测试。实际安装包的十种字段/保存视图重开/对象解析、CSV SHA冲突零写入及类型/单位导入、整批撤销重做/原UUID、筛选导出均通过。
  证据 `/tmp/stk-table-packaging-20261015/{package-verification,installed-wheel-smoke}.json`；未调用模型或Runtime。
  修正提交`d03366e`再从完整git archive副本离线生成两包；sdist有884个成员，修正PET例/README、新服务/schema/格式14契约均与提交逐字节一致，包内无archive。
  从解包源码实际导入运行PET数据演练 **7/7、零跳过 / 1.051s**；wheel与已通过安装冒烟的旧包逐字节相同，没有冒称重复安装。
  最终打包证据 `/tmp/stk-table-packaging-final-20261015/`，可持久副本见本文末证据目录的`package-final/`。
- 首轮精确代码头 CI：文档 38718495515、密钥扫描 38718495517 **completed/success**；[Runtime 38718495465](https://github.com/sijintech/stk/actions/runs/38718495465) **5/8 success、3/8 failure，全部completed**。
  Linux3.11/3.14 pytest各 **2864 passed、11 skipped、4 deselected**（582.28/651.88s），3.12 **2868 passed、7 skipped、4 deselected**（662.16s）；三版本新表36/36。
  Windows3.11/3.12各 **2367 passed、92 skipped、317 deselected**（597.46/492.77s），新表36/36及client入口/服务器拒绝步骤均通过。
  desktop **3 passed/7.37s**、control/Blender **24 passed/9.93s**、web build通过。三个Linux均只在后续独立PET合成例6/7通过、唯一1例失败（14!=13）；doctor/build/upload因此未运行，未算作包CI通过。
  [桌面 38718495503](https://github.com/sijintech/stk/actions/runs/38718495503) **4/5 success、1/5 failure，全部completed**。
  Linux **1431/1432、零跳过/未运行 / 367.44s**；唯一`wm_app_window_weston`在保存/重载布局成功后SIGSEGV，CSD用例通过；原始日志/LastTest/JUnit和Weston日志已保留，未重跑覆盖。
  macOS CPU **918/918 / 361.55s**、Metal **210/210 / 407.53s**，Windows CPU **876/876 / 408.28s**，均零跳过/未运行。
  主必跑checker Linux642、MacCPU620、Windows613全部成功；新表格截图Linux20/Mac10均实际必跑。Linux发布包/全新Ubuntu启动与Mac应用包/解压启动均成功。
- 首轮代码CI实际发现：Linux3.11 pytest **2864 passed、11 skipped、4 deselected / 582.28s**，后续独立PET合成例 **6/7通过、1失败**，唯一失败为旧夹具要求新项目格式13而当前为14。
  仅把该夹具改为当前FORMAT_VERSION并同步示例说明，保留9表/32记录/61引用/20冻结与全部来源/raw字节反例；生产源与原生代码未改。
  三Python版本独立例各 **7/7、零跳过**（3.11 1.203s、3.12 1.022s、3.14 1.216s），日志 `/tmp/stk-pet-data-format14-*.log`；审查和diff检查通过。
  `faf3a44`桌面全部已结束，推送门禁已满足；继续修真实退出缺口后统一推送。
- Weston退出诊断：原始二进制在本机带崩溃栈诊断运行100次均未复现（92.80s），不是修复证明，也没有得到本次CI调用栈。
  两次独立源码复核发现GHOST事件线程detach+cancel不等待结束即释放display/mutex，以及lock_without_input可未持锁返回的确定生命周期缺口。
  已改为独立stop唤醒与join完成后再拆资源、持锁后复查停止、断线错误退出；不在持server_mutex时join，不用取消展开Wayland回调。
  新增12项独立POSIX测试覆盖真实pipe/poll/锁竞争、回调完成sentinel、HUP/EBADF与初始化失败回滚；连同Weston/CSD真实窗口，定向 **14/14、零跳过 / 2.66s**。
  两次独立CR修复wait_readable错误传播和测试stop-before-unlock确定性；最终单一构建和完整原生 **1444/1444、零失败/跳过 / 328.66s**（`/tmp/stk-wayland-exit-20261015/native-full-final.xml`），新增必跑 **77/77**；没有改表格/项目/模型行为。
  仓库外从固定90MiB源包真正重新生成 **1095个文件**，全部SHA和metadata/3个补丁/5个shim一致；vendor.py --check通过。
  [pthread_cancel](https://man7.org/linux/man-pages/man3/pthread_cancel.3.html)仅提交取消请求，[pthread_join](https://man7.org/linux/man-pages/man3/pthread_join.3.html)完成后才保证线程终止；本修正采用协作停止并等待完成。
  修正节点6份Markdown的343个本地文件链接均存在，diff空白检查通过；暂存约42KB经`.gitleaks.toml`/redact扫描无泄漏。
  修正 **`d03366e30caf9421d0ffa61ce74058ec9ebcf550` 已推送 main**；明确等`faf3a44`桌面5个job全部completed后才推送。精确修正CI全部完成成功，实际结果如下。
  在得到更多证据前，不把历史SIGSEGV断言为已证明根因或“环境问题”。
- 修正提交精确 CI：文档 38725595247、密钥扫描 38725595380 **completed/success**；[Runtime 38725595362](https://github.com/sijintech/stk/actions/runs/38725595362) **8/8 已完成成功**。
  Linux3.11/3.14各 **2864 passed、11 skipped、4 deselected**（503.27/643.74s），3.12 **2868 passed、7 skipped、4 deselected**（602.70s）；
  Windows3.11/3.12各 **2367 passed、92 skipped、317 deselected**（421.33/615.75s）；五矩阵新表均实际 **36/36**。
  三Linux版本的独立PET例均 **7/7、零跳过**（0.792/1.016/1.325s），doctor、build、artifact upload逐step全部成功，三个包artifact实际存在且head匹配。
  desktop **3 passed/6.71s**、control/Blender **24 passed/8.78s**、web build **2.84s**，均成功；没有重跑覆盖首轮失败。
  [桌面 38725595367](https://github.com/sijintech/stk/actions/runs/38725595367) **5/5 已完成成功**。
  Linux **1444/1444 / 380.19s**，macOS CPU **930/930 / 286.86s**、Metal **210/210 / 286.37s**，Windows CPU **876/876 / 299.89s**，均零失败/跳过/未运行。
  Linux两个Weston窗口均实际通过（各1.03s）；12项PosixEventThread在Linux和Mac CPU均逐项执行通过，Windows未注册UNIX目标。
  必跑checker Linux654、MacCPU632、Windows613全部通过，Linux328与Mac164个单截图checker通过；新增表格截图Linux20/Mac10均必跑通过。
  Linux发布包和全新Ubuntu解包启动、Mac应用包和全新目录解压启动均成功。完整日志/JUnit/metadata见证据目录`ci-d03366e/`；Windows按真实job日志记录，未虚构未上传的JUnit。
- 点击实测起点：1440×1200 的新默认布局，真实桥加载公开合成表，a4 为活动表格；原 Viewer 已有公开 payload/相机。
  以下由 ScreenDriver 的 mouse down/up 事件驱动，不是直接调用按钮回调的计数，也不是线上用户遥测。

  | 任务 | 实际点击 / 键盘 | 实际结果 |
  |---|---|---|
  | 看见并选择已有表格 | 0 次导航 | 网格直接可见，占表格主体至少55%，详情默认收起 |
  | 更改已存布尔值 | 1 次单元格点击 | 一次修订；布尔缺测仍为空白 |
  | 数值编辑中失焦，再回到草稿并提交 | 3 次（选格→搜索框失焦→原格）+ 输入/F2/Enter | 失焦零写入；恢复原输入后Enter一次写入并移到下一行 |
  | 粘贴矩形并确认 | 2 次（锚点→应用）+Ctrl/Cmd+V | 预览零写入；确认一次修订，整批撤销恢复原值与int64 |
  | 重开项目后切换已存筛选视图 | 1 次视图标签点击 | 全表类型筛选/排序；存储记录数不变 |

  上述用例的 Viewer payload/相机 serial 保持，求值次数为0；字段/对象/CSV表单另有真实桥功能验收，未以直接binding/action冒称鼠标计数。
- 交付文档 critical review 已同步项目/CSV/Python指南；13份Markdown **482个本地文件链接、零缺失**，`git diff --check`通过；暂存约467KB经`.gitleaks.toml`/redact扫描无泄漏。
  最终四份交接/计划/日志/验收记录再次独立复核，澄清历史Weston措辞并补齐修正提交打包与CI；**335个本地文件链接、零缺失**，diff检查及最终暂存密钥扫描通过。
- 证据副本：`/home/mnemora/opt/stk-validation/table-workbench-20261015/`，含整套/定向XML、20张新截图、旧界面对照与包验证摘要。
  本机为自动事件/软件GPU，尚未做macOS/Windows真机人工或读屏验收。当前页搜索/统计最多500行，批量粘贴1000命令；
  附件缩略图、填充柄/看板拖动、通用关联聚合、大表增量引擎与云协作/权限/分享仍未实现。对象来源元数据不替代内容校验或运行授权。


## 2026-10-14：模块化工作区与少点击验收（`2e331ca` 跨平台 CI 全部通过）

- 前置：main / origin/main 为 `c31daa0`；其 Runtime 38602814854、密钥扫描 38602815186、文档 38602815231 均完成成功。
  上一个代码头 `20cc2f7` 的桌面 38535406254 **5/5 完成成功**，之后才允许本节点新代码推送。
- 边界：11 个独立编辑对象库及 16 个注册编辑器，仍链接一个应用；共用 AppStore/项目/Viewer/worker，不新增数据库或调度器。
  独立表格、真实目录树、程序文件编辑与主体分析图入口见[模块说明](desktop-modules.md)。格式 13 / 桥协议 1 不变，接口仅增补；模型、网络与运行授权未变。
- Python 完整最终：**2812 passed、24 skipped、2 deselected，624.00s**；XML `/tmp/stk-ui-modules-python-full-final.xml`。
  首轮真实出现旧 MuFerro 任务 preparing/queued 等待竞态（2810 passed、1 failed），修同快照等待，整文件 **6 passed / 49.58s** 后重跑完整通过。
  3.11/3.14 程序文件/脚本兼容各 **23 passed**；目录/索引/桥/分类各 **80 passed**，3.12 含脚本兼容 **93 passed**。
- 原生统一构建完成（GCC 15，现有 Linux sysroot，GL+Vulkan）。最终定向 **24/24、零跳过**；覆盖 6 个双语缩放默认布局结构检查、
  实例交换/旧布局迁移/工厂失败/菜单失效、草稿拒绝与外部失联、复核导航失败无残留。
  默认界面和新组合截图 **20/20**（两语言 × 两 GPU × 4 组合模式 + 4 默认导出），实际打开目检。
  首版本机完整 CTest **1367/1367、零失败、零跳过**（299.26 秒，`/tmp/stk-ui-modules-native-final.xml`）；新增必跑检查 **70/70**。
  前一次完整实际 **1361/1367**，剩余 6 项是窄栏双行标题、Files 背景及 a3 已为分析图的旧假设；
  保留像素/几何/透明度控件断言，显式选择 Properties 后定向 **6/6**（8.03 秒），再完整重跑通过。代码 **`10adde6a8c0b1bd8fcb02278ad30926e8c7ff631`** 已推送 main。
  文档 38672811827、密钥扫描 38672811832 已完成成功；首轮 Runtime 38672811830 **6/8**，桌面 38672811869 **4/5，已结束**。
  两个 Windows 版本均为 **2326 passed、92 skipped、1 failed、316 deselected**（3.11 379.90 秒、3.12 510.41 秒）。
  唯一失败是新脚本文件测试用 `write_text` 让 Windows 自动写 CRLF，却预期 LF 字节；产品保留真实字节/换行和 SHA 的行为正确。
  仅夹具改为显式 UTF-8 字节写入，保留原 SHA/source/size 和现有 BOM/CRLF 断言；本机 3.11/3.12/3.14 各 **10 passed、零跳过**（1.36/1.35/1.32 秒），未改产品代码。
  当时尚未推送修正，未将本机结果当作 Windows CI 通过；最终修正结果见下。
  首轮 Runtime Linux 3.11/3.14 各 **2823 passed、11 skipped、4 deselected**（561.07/669.49 秒），3.12 **2827 passed、7 skipped、4 deselected**（516.11 秒）；
  各版本新增程序文件 10 项、目录 20 项均实际通过，离线 PET 例各 **7/7**。另 desktop **3 passed**、control/Blender **24 passed**、web type-check/build 成功。
- 首轮桌面 CI（38672811869）Linux **1367/1367**（341.76 秒）、macOS CPU **873/873**（295.49 秒）/Metal **200/200**（299.43 秒）通过，均零跳过。
  Linux 发布包/干净环境启动、macOS 应用包/解压后启动通过；Linux 16 个、Metal 8 个新增组合截图必跑通过。
  Windows 全目标编译通过，CPU **825/831**（455.99 秒），六处文件路径字符串比较失败或等待超时；未跳过测试，后续必跑 checker 因 CPU 失败未运行。
  Python 返回规范反斜杠，C++ 夹具混合分隔符；改用 UTF-8 路径与 `filesystem::equivalent(..., error_code)` 检查实际文件身份，空路径/错误不能通过。
  `.py` 夹具另外固定二进制 LF 写入，保留源码/草稿/执行/Viewer 断言；不改变生产路径、原始换行或 SHA 策略。
  独立 critical review 确认空路径、缺失/不同文件不能通过；增量构建后全部 ScriptPython/FileTree 原生 **34/34、零跳过**（6.39 秒，`/tmp/stk-ui-windows-fixture-native.xml`）。
  仅三份测试源码和交付记录变动；推送遵守等待 `10adde6` 桌面完成的约定，最终 CI 结果见下。
  本次夹具修正与记录的暂存约 **7 KB** 经 `.gitleaks.toml` / redact 扫描无泄漏。
- 跨平台夹具修正 **`2e331cab24b1c5fac2dbff680c0d72c88a6afc4f` 已推送 main**；`10adde6` 桌面 38672811869 明确 completed 后才推送。
  仅三份测试源码与交付记录变动，`desktop/engine`、`desktop/app`、`suan` 对首版的 diff 为空。
  文档 38675881572、密钥扫描 38675881621 已完成成功；[Runtime 38675881568](https://github.com/sijintech/stk/actions/runs/38675881568) **8/8 已完成成功**；[桌面 38675881571](https://github.com/sijintech/stk/actions/runs/38675881571) **5/5 已完成成功**。
  Windows 3.11/3.12 各 **2327 passed、92 skipped、316 deselected**（497.92/794.21 秒），原失败已修；两版本程序文件 10 项、目录 20 项均实际通过。
  Linux 3.11/3.14 各 **2823 passed、11 skipped、4 deselected**（570.35/645.12 秒），3.12 **2827 passed、7 skipped、4 deselected**（539.10 秒）；
  三版本新 30 项均实际通过，离线 PET 例各 **7/7**（0.879/0.636/1.032 秒）。另 desktop **3 passed**、control/Blender **24 passed**、web type-check/build 成功。
- 修正提交最终桌面：Linux **1367/1367、零跳过**（334.63 秒），macOS CPU **873/873**（290.40 秒）/Metal **200/200**（304.31 秒），均零跳过。
  Windows **831/831、零跳过**（367.26 秒），原六个失败用例逐项通过；必跑 checker **568 matched** 实际全部运行通过。
  Linux 必跑 checker **597 matched**、macOS CPU **575 matched**，均成功；Linux 16 个、Metal 8 个新增组合截图必跑全部通过。
  Linux 发布包与全新 Ubuntu 24.04 GL/Vulkan 解包启动、macOS 应用包/解压后启动均成功。
- 点击任务（真实 ScreenDriver 鼠标事件）：新默认 Viewer/节点/表格/文件树 **0 次导航**；进入 Python、切回节点、左右交换各 **1 次**。
  固定旧单 Viewer 起点，传统 File → Python **2 次**，顶部 Python **1 次**，最终布局一致、无执行；这是同版本两条路径比较，不冒充历史用户遥测。
  另外验证中英文 900 UI 像素宽度、1/1.5/2 倍缩放的顶部入口，检查可点击裁剪范围与 Viewer 实例不变。
- wheel/sdist 构建成功，程序文件服务、目录服务与桥 schema 三份文件和源码逐字节一致，均无 archive。
  仓库外安装 wheel 后，两新模块导入及程序创建/读取/SHA 比较后保存通过，没有执行程序。
  中英文 i18n 各 **2156 键、0 问题**，修改文档 **511 个本地文件链接、0 缺失**，`git diff --check` 通过。
  暂存约 **417 KB** 经 `.gitleaks.toml` / redact 扫描无泄漏；独立模块/界面/文档 critical review 无剩余阻断。
- 实际流程：真实桥建合成类型表和已登记/未登记/缺失文件，逐层展开、选择 `.py`、在旁边载入并明确 Run，输出 4 行；
  原 Viewer payload/求值次数、项目修订与表格选择保持。三个程序编辑用例另测保存/另存/外部版本冲突/独立草稿/重连/迟到 Reset，目录读取不运行脚本。
- 本节点代码对已完成的真实 PET 项目隔离副本离线重验 **1 passed**（2.77 秒，`/tmp/stk-ui-modules-pet-offline.xml`）；
  新目录 API 浏览根目录和一层子目录，项目修订不变。禁止 Runtime 请求，未重跑 MD；不覆盖原 PET 证据，也不改变物性未验证的结论。
  本机完整 XML、定向/截图/必跑报告与摘要另保留在 `/home/mnemora/opt/stk-validation/ui-modules-20261014-10adde6/`。
- Critical review 的修复：隐藏草稿删除保护、自动同项目重连、单次 completion、来源/修订/生命周期、工厂/最大化回滚、旧隐藏标签保留原实例迁移，
  附加窗口与布局销毁保护、菜单异步失效、窄页头实际越界与概览空节点，复核导航失败清理内存候选。没有通过跳过或删掉原语义断言消除失败。
- 交付记录收尾：六份 Markdown 的 **358 个本地文件链接、0 缺失**，`git diff --check` 与暂存 gitleaks/redact 扫描通过。
  点击指标已纳入根目录 `AGENTS.md` 共同开发约定；后续 UI 交付持续记录起点、实际次数与任务终态。
- 限制：本机使用自动事件/软件 GPU/X11/Wayland；CI 已覆盖 macOS Metal 与 Windows CPU，跨平台真机人工/读屏验收仍未做。
  组合截图为公开合成场，不等于 PET 轨迹人工操作或物性收敛。
  富对象专用单元格/缩略图、批量粘贴、完整 IDE、二进制插件 ABI、按工作模式保存布局尚未实现。
  现有自定义布局继续恢复；新默认需在“视图 → 恢复默认布局”选择，未保存编辑稿会阻止实例销毁。全过程 key 为空、MODEL unset，无收费模型请求，未读写实际密钥/端点。

## 2026-10-14：界面盘点与产品约定（文档）

- Git 前置：`main`/`origin/main` 为 `6a6218d`，工作区干净，fetch 后无远端新增。
  该提交 Runtime（38588124035）**8/8**、文档（38588124116）与密钥扫描（38588123935）已完成成功；
  最近代码 `20cc2f7` 的桌面（38535406254）**5/5 成功**，满足之后推送前置。
- 四步截图核查：默认工作台 → 分析图 → 项目表格 → Python；1440×1000、中文、原生 headless Vulkan，
  四张 PNG 均已保存、打开目检并纳入[工作台设计](design/project-workbench.md#2026-10-14所有者补充的界面要求)。
  三个编辑器使用隔离布局直接选择，不把截图当作通过菜单实际点击的完整流程；未连接后台、未打开项目。
  这些是本次已有二进制的当前冷启动截图，不是改版效果图；文案可能先于当前源码字典。
- 独立代码盘点核对保存分析编辑、类型表格/引用/公式、文件索引与脚本 worker。
  确认首次文件菜单导航优先取 Viewer 区域，部分项目/图导航默认最大化；对象单元格、实际目录树与安全区域交换尚未实现。
  修正文档的过时节点编辑边界，新增明确的布局、表格、文件树与 Python 编辑要求；不改运行代码、数据库或发布协议。
  未重新运行 MD、完整 Python 或原生回归；截图不是交互、键盘/读屏、macOS/Windows 或高 DPI 的通过证据。
  全部本机命令清空 `STK_TOKEN_PLAN_API_KEY`、取消 `STK_TOKEN_PLAN_MODEL`，未读取密钥、调用模型或改变端点/网络策略。
- 文档 critical review 修正分析图开头及工作流设计表的旧实现状态；七份文档 **369 个本地文件链接**、`git diff --check` 通过，
  四张 PNG 解码和 1440×1000 尺寸检查通过。独立审查确认新要求没有冒称 UI 已交付，也没有解除其他待所有者决定事项。
  暂存文档经 `.gitleaks.toml`、redact 扫描无泄漏；截图为本机空状态，不含项目数据或凭据。

## 2026-10-14：PET 全流程 / E1d（真实软件全流程与最终代码 CI 通过）

- Git/CI 前置：初始 `main`/`origin/main` 为 `8ced4af`，工作区干净；本次期间再次 fetch 仍相同。
  最近代码 `4f54d78` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/38491407351)已完成 **5/5 成功**，允许之后推送新代码。
  文档头 `8ced4af` 的 Runtime **8/8**（38494652101）、文档与密钥扫描均已完成成功。
- 实现与 critical review：持久 PET 专项协调、冻结状态串联、O₂ 与 PET 链 COM 区分、三种分析归档、有界原子/真实键/盒子/轨迹查看。
  修正创建中断、项目/目标/参数竞争、外来冻结子运行与分析、外来 Tg 日志及篡改 CSV、错误化学身份/速度/参数、种子范围与 MPI 加偏移。
  不新增智能体运行权限，不改变项目格式、模型端点/密钥/网络策略，不引入客户原稿或内部数据。
- 首轮完整 Python **2748 passed、24 skipped、3 failed、2 deselected**（610.84 秒，`/tmp/stk-pet-full-python-20261014.xml`）：
  2 项为新增节点后的旧目录/生成参考未同步；1 项为更强来源检查提前拒绝后的旧错误消息断言。修正后完整
  **2764 passed、24 skipped、2 deselected**（612.98 秒，`/tmp/stk-pet-full-python-fixed-20261014.xml`）。
  最后 CVFF/精确六位表示 guard 及打包更改后相关 **101 passed、无跳过**（102.63 秒，`/tmp/stk-pet-final-python-guards-20261014.xml`）；
  不把较早整套计数冒称包含后加 guard。最终相关 3.11 **194 passed**（150.17 秒）、3.14 **194 passed**（149.11 秒），各无跳过。
- 原生首轮新功能定向 **9/11**：2 个 GPU bundle 只在 float32 电荷与 float64 精确相等的测试断言失败，修正精度判据后 **11/11**（10.08 秒）。
  首轮完整 **1314/1318、无跳过**，4 处旧预设数量仍为 11。更新为 12、新增两份表单 golden，并逐项证明旧 11 个预设布局完全不变。
  最终完整 **1318/1318、无跳过**（163.03 秒，`/tmp/stk-pet-native-full-fixed-20261014.xml`）；中英宽窄 PET 界面与 OpenGL/Vulkan 两种分子 GPU 验收均通过。
- O₂ 热态修正后再跑完整 Python **2765 passed、24 skipped、2 deselected**（632.61 秒，`/tmp/stk-pet-full-python-thermal-final-20261014.xml`）；
  再编译后的最终完整原生 **1318/1318、无跳过**（282.53 秒，`/tmp/stk-pet-native-full-thermal-final-20261014.xml`），包含 PET 面板桥接错误反馈。
  3.11/3.14 相关各 **195 passed**（154.91/156.70 秒）；这些整套报告先于最后两项子运行/分析复用 guard，最终定向结果另补。
- 真实 546 PET 全流程首轮：建模与 328000 步压密/释放/采样成功，LAMMPS 退出 0、日志完整，平均密度 **1.0943805532302737 g/cm³**。
  `write_data` 把 OPLS type13 的 4.318996175908222 写作 4.319，type14 也舍入，导致 outer 严格系数检查拒绝，
  首轮验收 **1 failed**（1776.27 秒，`/tmp/stk-pet-study-full-20261014.xml`）。保留失败证据，没有算作全流程通过。
  按固定 LAMMPS 源码只识别精确 `%g` 表示，逐标量记录；下游从首个冻结模型生成 full precision include 和摘要，恢复全部 **54** 类参数。
  原压密输入逐字节不变，重开/恢复/明确接续复用原建模与成功压密子运行。随后完整 11 段与搬迁离线复核通过（2756.89 秒）；11 个冻结状态交接、8 个密度点和 25 个 O₂ COM 样本独立一致，最大 MSD 文本舍入差 0.00047661763221640285 Å²。
  模量拟合成功，Tg 因两段斜率不满足物理判据、扩散因所选窗口斜率非正而拒绝，三份观测/诊断保留。
  科学 critical review 进一步发现 O₂ 前置全体系 FIRE 会清空 PET 速度：源 607.38358 K 变成仅气体热贡献的 3.28989 K；
  NPT 盒体积由约 7217 增至 11165 Å³，扩散段密度 0.71155042 g/cm³，因此这次通过仅是旧实现软件路径证据。
  已删除该 FIRE（保留非重叠插入、气体速度生成与全体系零线动量），协议 48/48 通过；
  独立真实短测正常退出，源 607.383579989503 K → 首个 NPT 606.22709481453 K，热态继承通过；新检查对保存的旧 FIRE 数据明确拒绝（1 个预期失败，`/tmp/stk-pet-study-old-thermal-negative-20261014.xml`），不是悄悄丢弃旧证据。
  新增真实首点温度检查后，从建模开始重新运行全部阶段，旧记录不覆盖；最终通过结果见本节末尾。
- 真实 O₂ 语法/路径短测：546 PET + 4 气体原子，插入、最小化、10 步 COM MSD 和写出完成，550 原子/566 键，正常结束且日志校验通过。
  `/tmp/stk-pet-o2-real-smoke-20261014` 仅用于提前发现求解器语法/分组问题，不作扩散物性判断。
  546 PET 真实轨迹已由原生 headless Vulkan 导出（`/tmp/stk-pet-546-viewer-20261014.png`），实际步 40000、5 图层；像素图已人工查看。
- wheel/sdist 构建通过；安装 wheel 后在仓库外确认 PET 协调/精准系数/O₂/4 新节点与分子预设可用。
  文档与示例按现有包规则仅进 sdist；发现新例缺少显式 include 后已补并重建，最终源码 wheel 与 sdist 示例/契约逐字节匹配，无 archive，仓库外安装冒烟通过；
  中英文 i18n 各 2095 键/0 问题、345 个本地链接检查通过，暂存约 379 KB 的 gitleaks 无泄漏。最终暂存约 **385 KB** 的 gitleaks 无泄漏；代码 **`6aca8f8` 已推送 main**，CI 实际结果见下。
- 最后 backend review 发现预先准备的 owned child 可含额外行，首次分析复用也可能绑定错误记录；
  已在关联/开始前要求唯一 owned row、准确 table/order 和完整冻结 bindings，拒绝后不提交/不改状态。
  唯一子行 guard 后相关 **196 passed、无跳过**（149.85 秒，`/tmp/stk-pet-related-guards-final-20261014.xml`）；
  统一 `get`/首次复用 gate 核项目、定义、完整冻结 graph/recipe 参数、快照、所有 bindings，并拒绝非空参数覆盖。
  最终后端与 native dispatcher 整文件 **46 passed、无跳过**（105.22 秒，`/tmp/stk-pet-study-backend-final.xml`），
  3.11/3.14 最后来源 guard 各 **4 passed**（4.20/4.18 秒），各另 33 deselected；只读复核无剩余阻断。
- O₂ 参数生成器还要求保存态有覆盖全部原子的完整速度段；缺失/部分速度准备前拒绝，完整全零速度不强行重抽。
  最后协议 **51/51**（0.29 秒）通过；最后冻结代码的协议/后端/native dispatcher 组合：3.12 **97 passed**（103.78 秒）、3.11 **97 passed**（105.14 秒）、
  3.14 **97 passed**（106.22 秒），均无跳过；真实 MD 未因这些反例重复提交。
- 最后交互 review 修正同名多研究创建后仍选旧研究：caller 生成新 UUID，表更新期间不回退旧行，同名用行号区分；
  旧选择回调拒绝、桥接错误在 PET 面板可见。2 研究选择/分派与界面定向 5/5（8.49 秒）、native dispatcher 9/9（0.63 秒）通过。
- `6aca8f8` 首轮 CI：文档（38531300843）与密钥扫描（38531300581）成功；Runtime（38531300583）的 Windows 3.11/3.12 各
  **2286 passed、92 skipped、1 failed、316 deselected**。失败均为文件同 tick 改写后复用旧 dump 索引，
  Windows 的 size/mtime/ctime/inode 签名不保证内容不变；不是跳过真实 Runtime 测试或单位误差。
  已修为索引复用核完整 raw SHA，图缓存也复核并失效旧错误指纹，新增元数据固定的跨平台反例；
  该代码头[桌面 CI](https://github.com/sijintech/stk/actions/runs/38531300727)已完成 **5/5 成功**，满足推送修正门槛；Linux 原生 **1318/1318**（260.96 秒）。
  Runtime Linux 3.12 **2787 passed、7 skipped、4 deselected**，3.11/3.14 各 **2783 passed、11 skipped、4 deselected**；
  另 desktop **3 passed**、control/Blender **24 passed**、web type-check/build 成功，整体为 **6/8**（两 Windows 失败）。
  Windows 索引修正 reader/source 三版本各 **76/76**（3.11 2.74 秒、3.12 1.91 秒、3.14 1.88 秒），
  10 个新反例覆盖固定元数据、头/坐标/盒子改变、预算/取消恢复、缓存失效，不用 sleep/skip。
  独立 critical review 通过，最后桌面相关 **11/11**（28.42 秒，`/tmp/stk-pet-native-index-fixed-20261014.xml`），最终完整 Python **2782 passed、24 skipped、2 deselected**（611.58 秒，`/tmp/stk-pet-full-python-index-fixed-20261014.xml`）；不覆盖首轮失败证据。
  修正 wheel/sdist 构建并逐字节复核通过；仓库外安装后实际读取新 546 PET 的 126 帧轨迹、完整 SHA 校验与最新步 20000 通过。
  `6aca8f8` 桌面其余实际计数：macOS CPU **840/840**（304.53 秒）、Metal **192/192**（342.93 秒）、Windows CPU **798/798**（354.12 秒），均无跳过。
  Linux 新 PET 宽窄/中英文/GL/Vulkan 必跑 **8/8**、Metal 新 PET 必跑 **4/4**，各真实执行。
  Linux 三 Python 版本的离线合成例均 **7/7**（3.11 0.866 秒、3.12 0.989 秒、3.14 0.968 秒）。
- 索引补正 **`20cc2f715411baf1c07718934e5e8c2cfb84d44e` 已在 `6aca8f8` 桌面 5/5 结束后推送 main**；暂存约 13.60 KB 的 gitleaks 无泄漏。
  [Runtime](https://github.com/sijintech/stk/actions/runs/38535406260) **8/8 已完成成功**；Windows 3.11/3.12 各
  **2297 passed、92 skipped、316 deselected**（391.80/674.60 秒），reader 56 项及 source/node 20 项均实际执行，原失败及 10 个新反例通过。
  Linux 3.12 **2797 passed、7 skipped、4 deselected**（652.46 秒），3.11/3.14 各 **2793 passed、11 skipped、4 deselected**；
  三 Linux Python 版本的离线合成例各 **7/7**（0.553/1.035/0.911 秒），desktop **3 passed**、control/Blender **24 passed**、web type-check/build 成功。
  [桌面](https://github.com/sijintech/stk/actions/runs/38535406254) **5/5 已完成成功**：Linux 原生 **1318/1318**（236.99 秒），
  macOS CPU **840/840**（272.92 秒）、Metal **192/192**（327.56 秒），Windows CPU **798/798**（300.02 秒），均无原生失败或跳过。
  Linux 新 PET 必跑渲染 **8/8**、Metal **4/4**，三平台两项 `LammpsProjectPython` 必跑均实际执行通过；两 Linux 打包/干净环境启动及 macOS 应用包冒烟通过。
  [文档](https://github.com/sijintech/stk/actions/runs/38535406237)与[密钥扫描](https://github.com/sijintech/stk/actions/runs/38535406248)均完成成功，全部精确匹配 `20cc2f7`。
- **修正热态后的全新真实 PET 软件全流程通过**：study `c4c3b0cd-48aa-41a9-82fd-a19be39fe967`，
  从建模开始完成 546 PET 原子的压密/释放、8 个温度降温、300 K 模量、600 K 两分子 O₂ 扩散，共 **11 个真实 LAMMPS 阶段**；
  全流程验收 **1 passed**（4883.98 秒，`/tmp/stk-pet-study-thermal-fixed-20261014.xml`）。
  每段 **126 帧**，验证实际首步 0 与生产末步；11 个冻结输入/几何/晶胞/速度交接、8 个密度点与 25 个 O₂ COM 样本独立核对通过，
  最大 MSD 文本舍入差 **0.0004942122628222023 Å²**。新首个 NPT **606.22709481453 K**，源为 **607.383579989503 K**；
  20000 步平衡预算结束 **600.154865617982 K、1.04573245290015 g/cm³**，未再出现旧 FIRE 的 PET 近零温重置。
  **模量和扩散数值拟合成功；Tg 未解析**，原因是两段密度斜率不满足物理判据，完整观测与失败诊断归档。
  报告明确 `software_complete=true`、`material_validation=false`；不将科学拒绝改为伪造 Tg。
- 最新 `20cc2f7` 代码对保存项目再次离线验收 **1 passed**（2.62 秒，`/tmp/stk-pet-study-durable-offline-20261014.xml`），
  禁止 Runtime 访问并重算输入/密度/轨迹与 COM；完整测试还验证搬迁重开、重复开始不产生重复任务。
  公开项目独立保留在本机 `/home/mnemora/opt/stk-validation/pet-study-20261014-20cc2f7/project`；
  同级 `evidence.json`、`observations.png/pdf` 和 `oxygen-trajectory-final.png` 保存结构化证据、实际三组观测与末帧。
  只复制项目，不复制 Runtime 状态、连接配置或凭据；74 MiB 真实产物不进 Git。
  当前正确热态的 550 原子轨迹由原生 headless Vulkan 导出，**实际步 200000、5 图层**，图像已目检；数值图亦目检，未为失败 Tg 画拟合。
- 最终独立 scientific critical review：550 原子/8 分子、4 气体原子分组及单位一致；生产 NVT 后半平均 **598.521 K**，密度恒定 **1.0457325 g/cm³** 与最终质量/晶胞独立算值一致。
  10–40 ps 全部 121 点独立 OLS 为 **0.006841529597615499 Å²/fs**，换算有限窗口 D **0.00011402549329359164 cm²/s**，仅复核数值计算。
  NPT 后半密度 **1.093363 ± 0.025371 g/cm³**，其最后单帧晶胞给 NVT 的 1.045732；压力 NPT/NVT 后半分别约 **−38 ± 3131 / −445 ± 3119 atm**（均为样本标准差）。
  短小体系和有限预算未证明平衡，不能以目标 1 atm、恒密度或正斜率宣称物性验收。未发现剩余实现阻断。
- 所有测试清空 `STK_TOKEN_PLAN_API_KEY` 并取消 `STK_TOKEN_PLAN_MODEL`，未发收费模型请求；真实验收只用公开参数和自建 PET。
  余限：6×DP4/单种子/约 2 nm 盒、每 50 K 仅 2 ps 斜坡和 5 ps 采样，600→550 K 密度非单调；
  模量为单方向 **4×10⁹ s⁻¹、2%** 短时窗口，O₂ 为两分子/600 K/50 ps、单原点，未核对长时 MSD 指数、多原点、副本、链长/体积收敛及交叉参数实验一致性。
  全系统零初始动量后残余漂移、文本状态不保存 thermostat/barostat 内部态；后续须做平稳性、分块不确定度与不同预算比较。
  尚不验证收敛物性、溶解度、渗透率、PET 弹性体/酒液/长期变形，GUI 精确拾取及厂内强制边界也未交付。
- 最终交付记录经独立只读 critical review，无阻断；五份文档 **326 个本地文件链接**、`git diff --check` 通过。
  暂存文档经 `.gitleaks.toml` 的 redact 扫描无泄漏；本次仅补记实际结果，不改运行代码，未重复启动真实 MD。

## 2026-10-13：PET 数据闭环节点 1（桌面、字典、调用清单）

- Git/CI 前置：初始 `main` 与 `origin/main` 同为 `af51115`，工作区干净；该文档头的 Runtime 8/8、文档与密钥扫描均已完成成功。
  上一个代码头 `fbcd9f4` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/38285992314)已完成 **5/5 成功**，满足本次代码推送门槛。
- 实现与 critical review：固定内置 MuFerro/LAMMPS 分派、JSON 参数、项目/修订/引擎/冻结运行检查；准备不提交，查看不访问 Runtime。
  修正旧项目/引擎/文件选择/批次成员回调及跨引擎选项复用，离线查看拒绝篡改文件、摘要、输入或伪造 runner。
  第一轮新按钮定向 **31/32**，失败为测试点击折叠面板后视口外的按钮；改为实际折叠/展开面板操作，单项 **1/1** 通过（3.75 秒）。
  第一轮完整桌面 **1308/1309、无跳过**（280 秒）发现产品回归：引擎过滤隐藏无完整 intent 的旧批次。
  修正为保留未知/旧批次的查看、归档与恢复，执行仍需匹配已校验内置模板；旧归档用例 **1/1** 通过（0.46 秒）。
  最终只读 review 另发现归档按钮缺少项目/引擎/批次回调保护，已补校验并加入实际旧按钮回归断言；
  部分批次列表改用不含全局计数的归档开关，避免可见引擎数量误导。
  原始失败报告保留 `/tmp/stk-e1-desktop-{focused,full-native}.xml`，修正定向为 `-fixed.xml`、`-archive-fixed.xml`。
- Python 3.12 完整回归 **2598 passed、24 skipped、2 deselected**（508.03 秒，`/tmp/stk-e1-desktop-full-py.xml`）。
  随后收紧公开离线 view 的 runner 身份，最终相关套件 **28 passed、无跳过**（40.20 秒，`/tmp/stk-e1-desktop-native-final.xml`）；
  该完整计数不冒称包含后加的 guard。较早工作流/批次相关回归 **55 passed、2 skipped**（129.04 秒，真实 MuFerro 选择性跳过）。
- 真实 LAMMPS 原生按钮最终验收 **2/2、无跳过**（6 秒，`/tmp/stk-e1-desktop-real-lammps-final.xml`）：
  导入、两次准备仍零任务、运行记录明确提交、日志/刷新/两次收集、停止 Runtime 后离线查看及结果行定位；
  两成员批次明确运行/重复操作复用任务，旧成员取消和归档回调均不改当前项目/修订。使用已登记 MPICH LAMMPS，
  108 原子氩、300/350 K、20 步只验证软件路径，不代表平衡或 PET 材料结论。
- 离线全合成业务示例：Python 3.11/3.12/3.14 各 **7/7、无跳过**；本机再次 **7/7**（0.758 秒）。
  独立核对 **9 业务表、32 记录、61 引用、20 冻结文件**，内置文件索引另计；
  所有实际 source_kind 均为 synthetic，缺测/失败为空，不作 PET 训练或实验结果。项目保留 `/tmp/stk-pet-data-20261013-final`。
  只读 review 未发现阻断问题；字典是草案，格式 13 普通表尚未强制领域关系或用途规则。
- wheel/sdist 构建成功：核对新 dispatcher、离线 view、桌面指南、字典及完整合成例入包，无归档代码。
  wheel 中两份工作流实现与 `4f54d78` 实际字节一致，sdist 的 **24 项示例/字典文件**也逐字节一致。
  使用本地 wheel、`--no-index --no-deps` 在仓库外安装并导入，固定引擎拒绝与公开 view 可用；不调用模型/求解器。
  本机中英文 i18n 各 **2079 键、0 问题**；已目检 GL 的中文窄屏 LAMMPS 导入与英文宽屏批次截图，未强制 LJ 温度为 K。
- 全部修正后重新编译，最终完整 Linux 原生 **1309/1309、无失败/跳过**（274.06 秒，`/tmp/stk-e1-desktop-full-native-final.xml`）。
  新增 2 项跨平台导入/文件选择、2 项 Linux 全按钮/批次交互与 16 项中英文宽窄 GL/Vulkan 渲染均明确执行成功，
  必跑检查匹配 **20 项**通过。前一完整 **1309/1309**（275.26 秒）先于最后归档回调保护，保留 `-pre-archive-guard.xml`，不替代最终报告。
  三平台 CI 已加入对应必跑规则，macOS Metal 新增 8 张渲染；未执行的其他平台结果不当本机成功。
- 格式/i18n 与 **401 个本地链接**检查通过；暂存约 153 KB 经 gitleaks（`.gitleaks.toml`、redact）无泄漏。
  代码 **`4f54d78`** 已推送 main；[文档](https://github.com/sijintech/stk/actions/runs/38491407349)与
  [密钥扫描](https://github.com/sijintech/stk/actions/runs/38491407329)已完成成功；
  [Runtime](https://github.com/sijintech/stk/actions/runs/38491407387) **8/8 已完成成功**；
  Python 3.12 **2613 passed、7 skipped、4 deselected**（534.47 秒），3.11/3.14 各 **2609 passed、11 skipped、4 deselected**（472.66/530.82 秒）；
  三个 Linux 版本的离线例各 **7/7、无跳过**（0.880/0.984/0.981 秒）。Windows 3.11/3.12 各 **2143 passed、92 skipped、286 deselected**（538.59/350.33 秒），
  客户端入口/服务端拒绝检查成功；Windows 未运行独立离线例或 Linux-only Runtime 夹具。
  另桌面 Python **3 passed**、control/Blender 协议 **24 passed**，web 检查成功。
  [桌面](https://github.com/sijintech/stk/actions/runs/38491407351) **5/5 已完成成功**。
  Linux **1309/1309**（315 秒），macOS CPU **840/840**（257 秒）、Metal **188/188**（263 秒），三份 JUnit 均 **无失败/跳过**；
  Linux 新交互 **4/4**、新渲染 **16/16**，macOS 新交互 **2/2**、Metal 新渲染 **8/8**，必跑检查均成功。
  真实报告保留 `/tmp/stk-e1-ci-4f54-linux/ctest-junit.xml` 与 `/tmp/stk-e1-ci-4f54-macos/ctest-{cpu,metal}.xml`；
  Linux 包构建与新环境包冒烟、macOS 应用包冒烟也通过；Windows CPU **798/798、无失败/跳过**，
  新交互 **2/2**及真实 Python 桥必跑检查均成功；筛选记录保留 `/tmp/stk-e1-ci-4f54-windows-summary.json`。
  CI 结束后补记四份交接文档，复核 **296 个本地链接**与格式、再次做暂存 gitleaks，无泄漏。
- 剩余限制：原生仿真面板只有内置两引擎入口与热力学结果，第三方仍可用既有工作流/脚本；
  面板的第三方入口、原子/键/轨迹显示、远程模块安装、运行中事件未实现。
  两种引擎的资源选项只在当前编辑器会话保留，没有新增跨重启持久设置。
  厂内清单仅代码调用梳理与节点 2 验收设计，未审定第三方出口、未实施强制网络隔离；不接入真实企业资料/聊天。
  真实 PET 物性、气体/水/乙醇/新增弹性体组分参数、PET 数据集契约/独立分组评价与自主训练仍需后续节点。
  全部测试清空 `STK_TOKEN_PLAN_API_KEY`、取消 `STK_TOKEN_PLAN_MODEL`，无收费模型请求；端点、网络、权限与格式未改。

## 2026-10-12：PET 基材料研发项目落地路线（文档）

- 来源：通过授权 Google Drive 读取所有者指定的 DOCX 正文/表格。
  公开仓库只存通用需求映射，不存客户原稿、问题、数据及其访问链接/文件身份；没有修改 Google 文件或分享权限。
- 代码与科学 critical review：核对 S1 公开表准入/自由问题、S2 执行级别、S3a 目标/随机划分/内存任务、项目引用与快照。
  路线明确厂内全问题/派生内容、新版训练工具、样品批次独立评价及恢复移交；纯 PET、拟合模板与合成模型不当材料验收。
- Git/CI 前置核对：`main` 与 `origin/main` 同为 `f1cc462`，初始工作区干净；该文档头的
  [Runtime](https://github.com/sijintech/stk/actions/runs/38291230274)、[密钥扫描](https://github.com/sijintech/stk/actions/runs/38291230436)、
  [文档](https://github.com/sijintech/stk/actions/runs/38291230359)均完成成功；上一个代码头 `fbcd9f4` 的
  [桌面 CI](https://github.com/sijintech/stk/actions/runs/38285992314)已完成 **5/5 成功**，满足后续推送前置门槛。
- 本地检查：六份 Markdown 的新增链接 **17 项**全部存在，换行与文件结尾通过，公开文件不含源稿访问链接/文件身份；
  `git diff --check` 通过。三篇 PET/PET–PEO/传输研究的 DOI 与出版社摘要核对一致；不替客户选择材料阈值。
  本次只修改设计与四份交接文档，没有改运行代码，未重复执行科学/桌面套件；文档站构建由本次 CI 核对。
  本机 Node 为 24、没有 pnpm，未把这一环境当成文档站构建通过。暂存约 26.6 KB 改动经 gitleaks（`.gitleaks.toml`、redact）无泄漏。
  未运行模型请求，未改变端点/网络/权限或发布协议。材料指标、真实数据、工期起算日、部署资源与验收门槛仍待实施任务落实。
- 路线文档 **`b5fc3b7`** 已推送；[文档站](https://github.com/sijintech/stk/actions/runs/38329803248)与
  [密钥扫描](https://github.com/sijintech/stk/actions/runs/38329803250)已完成成功；
  [Runtime](https://github.com/sijintech/stk/actions/runs/38329803247) **8/8 已完成成功**。
  纯文档改动未触发新的原生桌面 CI，上一个代码头桌面 5/5 已完成成功。
  CI 结束后补记四份交接文档，再次核对 **276 个本地链接**、格式与暂存 gitleaks，全部通过。

## 2026-10-12：E1b 文献参数 PET 本机建模

- 授权：所有者要求按文献/公开资料判断并直接执行 PET，解除此前电荷选择等待。采用完整 PET OPLS-AA/MK 2022 适配参数，
  苯环 C −0.115 e 与其他电荷、LJ 配套；醇端 O 的 +0.001 e 舍入修正记录原值/使用值，不沿用历史 0.0。
  默认 COOH/OH 六条四聚体为 546 原子，不改写旧 540 原子 OH/CHO 的独立写出器夹具。
- 独立来源复核：69 个 S1 电荷、15 个类型，12 种键（11 SI+1 canonical）、19 种角（13+6）、23 种 proper（16+7），
  每 proper 35 个角度核对源 cos3/RB/OPLS，源行、单位及两类平面 improper 一致。
  固定论文补充材料与 GROMACS v2025.3 文件 SHA 在资源/来源文档中，公开报告在 `examples/pet_model/validation/2026-10-12-profile-review.json`。
- Critical review 的真实发现与修正：Foyer 保留输入元素质量，现明确换用 S2 并记录原质量；指定 Packmol 的确切程序，
  不接受 `WITHOUT PERFECT PACKING`，使用周期填充并独立审查互链/自镜像重叠。
  **1×DP2、250 kg/m³** 的初始盒子出现约 **1.336 Å** 自镜像重叠而拒绝；降至 80 kg/m³ 后通过。
  成功产物发布前再次核对完整 profile、冻结参数、全部七份实际文件 SHA、XML 摘要、组成与逐链中性；
  拒绝重名 JSON 键/非有限值/超过 2 MiB 的 manifest。取消观察持久项目状态并结束子树，不覆盖已有目录。
- 长链构象回归先真实复现 **DP8/seed42** 的默认 ETKDG 嵌入失败；改为同种子随机坐标 fallback，直接保留坐标转换 mBuild，重复得到相同 SHA。
  **DP8×6、150 kg/m³**（1074 原子）构象/填充/分配分别 2.405/5.651/0.997 秒；
  **DP20×6、100 kg/m³**（2658 原子）分别 22.394/8.124/2.403 秒，类型、每链中性和周期重叠审查通过。
  UFF 200 步状态 **1（未收敛）** 明确记录，只用于有限初始几何松弛，不能当 PET 力场或平衡验收。
  独立 DP100 标准/随机模式在内部 timeout=45 秒下约 192 秒仍未返回，**外部停止，censored**；未当作成功或算法返回失败。
  首版因此明确限制 **DP2–DP20**，产品启动器保留 30 分钟硬预算/取消；大链外部建模后导入仍允许。
  证据在 `2026-10-12-{geometry,extended-chains}.json`，RDKit 内部 timeout 不承诺覆盖所有前处理。
- 真正独立的真实软件验收 **5 passed**（20.56 秒，`/tmp/stk-pet-geometry-delivery.xml`）：
  四原子周期 improper 的解析/OpenMM/LAMMPS 能量与力，以及两份 PET 体系的独立键图与参数核对。
  **1×DP2、80 kg/m³** 为 47/48/77/102/16；**6×DP4、250 kg/m³** 为 546/564/918/1224/192（原子/键/角/proper/improper）。
  原始构型六分项能量最大差 **3.75e-12 kcal/mol**；明确记录的≤0.01 Å 受控扰动后，全力最大差 **2.35e-11 kcal/mol/Å**，
  12 个有限差分分量最大差 **6.25e-8 kcal/mol/Å**。期望系数直接从论文与 canonical 数据独立转录，不读取产品 profile 生成期望。
  原始 DP2 近乎平面 proper 受 [LAMMPS sine 保护](https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/MOLECULE/dihedral_opls.cpp)影响，
  全力最大差 **3.49e-5**，保留原始差异，不称精确一致。非周期参考仅与相同非周期 LAMMPS Hamiltonian 比较；生成 PPPM 案例另行读回成功。
  两份模型与四原子报告在 `examples/pet_model/validation/`，不提交生成的数据文件。
- 真实项目路径 **1 passed**（46.29 秒，`/tmp/stk-pet-real-geometry-workflow.xml`）：
  模块实际检测/登记→两行模型（546/47）→准备后修改表格仍用原冻结种子→八产物 SHA 快照→显式导入→Runtime/LAMMPS 最小化与 60 步运行→收集。
  此短运行仅软件路径，约 0.25 g/cm³ 的松散盒子不是平衡密度。
- Python 3.12/3.11/3.14 的六文件定向各 **105 passed、无跳过**（9.77/10.03/10.07 秒；`/tmp/stk-pet-agent-final{312,311,314}.xml`），
  含独立化学图资源、manifest 反例、冻结/重开/跨进程取消、旧模板兼容；worker/profile/writer/分析定向 **87 passed**（1.74 秒）。
  Linux 原生工作流/仿真/技能目录定向 **40/40、无跳过**（35.42 秒，`/tmp/stk-pet-native-focused.xml`）。
  完整 Python **2569 passed、24 skipped、2 deselected**（464.88 秒，`/tmp/stk-pet-full-final.xml`）；
  其后新增链长上限与构象回归，最终相关套件 **168 passed**（22.99 秒，`/tmp/stk-pet-related-complete.xml`），
  Python 3.11/3.14 的 worker/profile/writer/分析/工作流最终各 **131 passed、无跳过**（6.77/6.74 秒，
  `/tmp/stk-pet-core-complete-{311,314}.xml`）。完整计数不包含后加的一个上限用例。
  wheel/sdist 构建成功并核对 worker、JSON/XML、文档与示例入包；从仓库外安装的包读回 profile、模板注册通过。
- 推送门槛：上一代码头 `be9bdd7` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/38164654996) **5/5 已结束成功**；
  当前初始文档头 `dff03f1` 的 Runtime 8/8、密钥扫描与文档也已完成成功，之后才推进本次代码推送。
  代码 **`fbcd9f4`** 已推送 main；[Runtime](https://github.com/sijintech/stk/actions/runs/38285992490) **8/8 已完成成功**
  （3.12：2585 passed、7 skipped；3.11/3.14 各 2581 passed、11 skipped；均 4 deselected；
  Windows 客户端 3.11/3.12 各 2125 passed、92 skipped、276 deselected，含六个 POSIX shebang 测试的平台跳过）；
  [桌面](https://github.com/sijintech/stk/actions/runs/38285992314) **5/5 已完成成功**：Linux GL/Vulkan/X11/Wayland、
  macOS CPU/Metal/应用包冒烟、Windows CPU、Linux 包构建与新环境包冒烟均通过；
  Linux **1289/1289**、Windows CPU **796 项、0 失败**；macOS CPU **838/838**、Metal **180/180**，
  两份 macOS JUnit 均无失败/跳过，必跑检查也成功。原始 macOS 报告保留 `/tmp/stk-pet-macos-ci/ctest-{cpu,metal}.xml`。
  [密钥扫描](https://github.com/sijintech/stk/actions/runs/38285992279)与[文档](https://github.com/sijintech/stk/actions/runs/38285992192)已完成成功。暂存约 265 KiB 改动经 gitleaks（`.gitleaks.toml`、redact）通过，无泄漏；
  全部测试空 API key、模型变量取消，无收费模型请求。
- 剩余限制：构象/填充与平衡分别判定，资源边界不保证长链成功；仅干燥、中性、COOH/OH 线性 PET，
  未提供气体/水/离子参数，不声称 Tg、模量、气体 D/渗透率收敛。PPPM、参数缺项与平面 improper 都是明确适配，非作者轨迹的精确复现。
  本机建模后显式导入远端案例；参数表与工作流创建分两次普通可撤销编辑，未实现自动串联。macOS/Windows 真机分子模块验收尚未做。

## 2026-10-11：E1c 多温度 Tg 来源与日志列校验

- 审查复现两项失败（`/tmp/stk-e1c-density-before.xml`）：汇总表的八日志摘要没有进入最终 Tg 诊断；
  早期热力学段的重复列名被汇总入口接受。修正后分析 **27 passed**，八个合成温度日志汇总得到 **340 K**，
  输入表不变、全部来源在 summary/fit/provenance 与可序列化 JSON 诊断中一致。
- 各来源 SHA-256 指日志文本 UTF-8 编码，`role: input_text`；不把标签当成已读取/核验的磁盘文件。
  调用者保留原始冻结日志。热力学日志所有段都拒绝重复列名，`stk.source.lammps_log@1` 实现版本 **1→2** 隔离旧缓存。
  发布目录仅此节点实现版本改变，主版本/端口/参数与六技能哈希不变。
- Python 3.11/3.14 的分析/源节点/CLI/契约/技能定向各 **108 passed、1 skipped**（既有离屏 GL probe 不可用）；
  原生 Graph/目录定向 **7/7、无跳过**；真实 LAMMPS 三模板经 Runtime、工作流、分析归档复验 **3 passed**（16.47 秒）。
  JUnit：`/tmp/stk-e1c-density-{after,py311,py314,native,real}.xml`。
  最终完整 Python **2485 passed、24 skipped、2 deselected**（458.73 秒，`/tmp/stk-e1c-density-full.xml`）。
- 推送门槛：上一代码 `c17bb4b` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/38162974612) **5/5 已结束成功**，
  Runtime 8/8、密钥扫描与文档通过后再推送本次代码。PET 电荷仍待所有者决定，没有实施相关建模。
  暂存改动经 gitleaks（`.gitleaks.toml`、redact）无泄漏；测试空 API key、取消模型变量，无模型请求。
  代码 **`be9bdd7`** 已推送；[Runtime](https://github.com/sijintech/stk/actions/runs/38164655024) **8/8 已完成通过**
  （3.12：2500 passed、7 skipped；3.11/3.14 各 2496 passed、11 skipped；均 4 deselected），
  [文档](https://github.com/sijintech/stk/actions/runs/38164655117)、[密钥扫描](https://github.com/sijintech/stk/actions/runs/38164655029)通过；
  [桌面](https://github.com/sijintech/stk/actions/runs/38164654996) **5/5 已完成通过**：Linux **1289/1289**、
  macOS CPU **838/838**、Metal **180/180**（三份 JUnit 均无失败、无跳过）；Windows CPU **796 项、0 失败**，Linux 包构建与新环境包冒烟成功。
  原始成功报告保留在 `/tmp/stk-e1c-linux-be9bdd7/ctest-junit.xml` 与 `/tmp/stk-e1c-macos-be9bdd7/ctest-{cpu,metal}.xml`。
  四份交接文档在代码 CI 全部结束后以文档提交补记最终状态，剩余科学与产品限制未变。

## 2026-10-11：E1c 表头、缓存与桌面回归修正

- 实际误算复现：旧读取器对 `Strain Stress Stress` 保留后一列，合成模量从 **2.5 GPa** 变成 **25 GPa**。
  修正为构造字典前拒绝重复/规范化重名（裁剪、`/`/`.` 替换、128 字符截断），覆盖两种表头格式、JSONL 规范化碰撞与三套性质预设。
- 缓存回归先复现失败：即使新读取器正确，旧实现版本已缓存的 25 GPa 仍可命中；
  `stk.source.table@1` **impl_version 1→2** 后，相同输入/预设明确失败且不输出 summary。
  原始失败 `/tmp/stk-e1c-oldcache-before.xml` 保留。只有这一既有节点的实现版本变化，端口/参数/主版本、其余声明与六技能哈希不变。
- 最终完整 Python：**2483 passed、24 skipped、2 deselected**（472.51 秒），定向 **96 passed、1 skipped**；
  Python 3.11/3.14 各 **78 passed、1 skipped**（既有离屏 GL probe 不可用）。
  JUnit：`/tmp/stk-e1c-headers-and-cache-full.xml`、`/tmp/stk-e1c-headers-py311.xml`、`/tmp/stk-e1c-headers-py314.xml`。
- 最终完整 Linux 原生 CTest **1289/1289、无失败、无跳过**（268.42 秒，`/tmp/stk-e1c-headers-native-full.xml`）。
  三处预设数断言更新为 11，新增三套中英文表单基准；既有八套布局逐项不变，未改产品 UI 代码或放宽判据。
  真实 LAMMPS → Runtime → 按行工作流 → 隔离分析/归档复验 **3 passed**（16.50 秒，`/tmp/stk-e1c-real-headers.xml`）。
- 上一代码 `6927e27` [桌面 CI](https://github.com/sijintech/stk/actions/runs/38160740368) **已完成失败**：
  Linux **1285/1289**（Graph、ViewerFake 与 en/zh PropertiesForms），macOS CPU **837/838**、Windows CPU **795/796**（Graph）；
  失败均为预设数旧断言。macOS 因 CPU 失败未执行 Metal，后续必跑检查缺少 Metal 报告也失败，不能记为 Metal 产品失败或通过。
  Linux 包构建与新环境包冒烟成功。原始 Linux/macOS JUnit 与日志保留在 `/tmp/stk-e1c-{linux,macos}-38160740368/`，
  Windows 失败日志 `/tmp/stk-e1c-windows-38160740368.log`；未重跑覆盖首轮证据。
  [Runtime](https://github.com/sijintech/stk/actions/runs/38160740449) **8/8**、密钥扫描与文档成功。
- 推送前确认上述桌面 CI 已结束；测试全部清空 `STK_TOKEN_PLAN_API_KEY`、取消 `STK_TOKEN_PLAN_MODEL`，无模型请求。
  暂存改动经 gitleaks（`.gitleaks.toml`、redact，24.80 KB）无泄漏。
  修正代码 **`c17bb4b`**：[桌面](https://github.com/sijintech/stk/actions/runs/38162974612) **5/5 已完成通过**，
  Linux **1289/1289**、macOS CPU **838/838**、Metal **180/180**（macOS 均无跳过）；Windows 与包构建/新环境包冒烟通过。
  [Runtime](https://github.com/sijintech/stk/actions/runs/38162974582) **8/8 已完成通过**
  （3.12：2498 passed、7 skipped；3.11/3.14 各 2494 passed、11 skipped；均 4 deselected），
  [密钥扫描](https://github.com/sijintech/stk/actions/runs/38162974606)、[文档](https://github.com/sijintech/stk/actions/runs/38162974584)通过；桌面完成后补记结果。
  性质收敛、PET 电荷与桌面 LAMMPS 入口的限制仍与下条相同。

## 2026-10-11：E1c Tg、模量与扩散分析

- 已知合成曲线：Tg **340 K**（两段斜率 -0.0002/-0.0007 g/cm³/K）、模量 **2.5 GPa**（自由截距 0.125 GPa）、
  扩散 **1e-4 cm²/s**（三维、1000–10000 fs）。三个图预设数值/诊断/绘图与 CLI 示例通过；缺省扩散窗口拒绝执行。
  单位、数据符号、重复温度/重置时间、窗口/分段、来源不变与非有限/溢出输入的失败场景均有回归。
- 首轮完整 pytest **2 failed、2467 passed、24 skipped**：轻依赖源节点数量仍是 4、说明包节点参考未再生成；
  更新到 5 个源节点、重新生成节点参考后完整修正回归 **2469 passed、24 skipped、2 deselected**（458.71 秒）；
  完整回归运行期间另加混合单位拒绝，随后对应定向 **33 passed**。
- Python 3.11 与 3.14 的写出器/脚本/工作流/分析/技能/预设各 **105 passed、1 skipped**（离屏 GL 不可用）；
  来源修正、参考更新与混合单位检查后各 **33 passed**。节点仍可在不导入 NumPy 的环境查询。
- 原生技能/工作流/分析运行/脚本 CTest 初次 **73/74**，唯一失败为技能列表控件仍断言 3 项（现有六项）；
  修正后 **74/74**，必跑检查匹配 74 项且无跳过。i18n en/zh_CN 各 2067 项，检查通过。
- 补充节点目录/参数编辑/中英文宽窄技能截图 **30 项**：首轮 22 通过、8 张截图因渲染夹具仍断言 3 项/索引 2 而失败；
  改为六项/索引 5 后 **30/30**。OpenGL/Vulkan 宽窄截图目视确认六技能可读；两组原生回归共 **104/104**，未改变产品 UI 代码。
  首轮原始 `LastTest.log` 保留在 `/tmp/stk-e1c-native-catalog-initial.log`，未用重跑掩盖失败。
- 发布契约核对：**34 个既有节点声明逐项不变、3 个既有技能哈希不变**；新增四节点/三技能，graph/project 格式不变。
  原 E1a 表的读取/准备不推进修订、不补字段；显式导入后旧运行参数快照仍不变。
- 真实程序（手动，不进默认 CI）：LAMMPS **22 Jul 2025 Update 6 MPICH**，公开 **108 原子氩**，三套脚本经真实 Runtime、
  项目工作流、冻结产物、隔离分析/归档读回 **3 passed**；结果来源摘要与冻结文件一致。
  20 K 行平均温度 **20.7752 K**、密度 **1.74923 g/cm³**；短轨迹模量拟合 **2.43161 GPa**；
  300 K 行的 100–1000 fs MSD 拟合 **1.79843e-4 cm²/s**。
  [报告与运行命令](../examples/lammps_analysis/README.md)保留参数、窗口、输入/日志摘要。
  这些是有限时间路径检查，**不构成氩/PET 的收敛性质验收**；Tg 分支只收集一个密度点，跨温度 Tg 用合成曲线验证。
- 打包：在独立临时 venv 安装 build 1.6.1/poetry-core 2.5.0，wheel 与 sdist 构建成功；
  wheel 包含全部 11 个 E1c 代码/资源文件，从仓库外安装并读取三套模板、分析预设、来源诊断及六个技能通过。
  `graph doctor` 节点目录通过；本机既有离屏 probe 仍以 SIGSEGV 11 失败，未据此声称三维渲染验收。
- 推送门槛：上一代码 `057f96d` [桌面 CI](https://github.com/sijintech/stk/actions/runs/38157976221) **5/5 已完成通过**，
  [Runtime](https://github.com/sijintech/stk/actions/runs/38157976224) 8/8、密钥扫描通过后才推送本次代码。
  测试全部清空 `STK_TOKEN_PLAN_API_KEY`、取消 `STK_TOKEN_PLAN_MODEL`，无模型请求。
  本次暂存改动经 gitleaks（`.gitleaks.toml`、redact）扫描无泄漏。
  代码 `6927e27` 已推送；[Runtime](https://github.com/sijintech/stk/actions/runs/38160740449) **8/8 已完成通过**，
  [桌面](https://github.com/sijintech/stk/actions/runs/38160740368)已结束失败（预设数量断言，具体首轮结果与修正见上条）；
  [密钥扫描](https://github.com/sijintech/stk/actions/runs/38160740601)、[文档](https://github.com/sijintech/stk/actions/runs/38160740493)已通过。
- 剩余限制：无平衡自动判定、跨行自动密度汇总、Tg 置信区间、通用分子质心/多原点 MSD 或全体系漂移自动校正；
  需核对研究协议、采样相关性、温度历史、应变率与扩散区。桌面 LAMMPS 导入/专用仿真视图和 PET 建模未交付，电荷仍待所有者决定。

## 2026-10-11：E1b 独立数据写出器

- 接手 Git：干净 `main`，`101bb27` 与远端一致；上一代码提交 `1859ca7` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/38097721844)
  5/5 已完成通过，当前交接提交 [Runtime](https://github.com/sijintech/stk/actions/runs/38151033592) 与[密钥扫描](https://github.com/sijintech/stk/actions/runs/38151033573)也通过。
- `test_lammps_data.py` **19 passed**：保留非零净电荷、真实系数合并、分子键连通关系、整个角度周期上的独立 RB/OPLS 能量公式对照、
  三斜矢量关系、非法盒子/NaN/Inf/缺参数/外部成员/非标准非键合例外与势项拒绝、improper 显式选项、原子替换且失败不覆盖文件。
- LAMMPS 与工作流/模板/模块定向回归 **97 passed、1 skipped**（既有真实 MuFerro 测试未设置 `STK_TEST_MUPRO_PREFIX`）；
  Python 3.11 与 3.14 的写出器/LAMMPS/工作流各 **56 passed**。测试清空 `STK_TOKEN_PLAN_API_KEY`，取消 `STK_TOKEN_PLAN_MODEL`；未发送模型请求。
- 手动（mBuild 1.4.0、foyer 1.2.0、GMSO 0.17.0、LAMMPS 22 Jul 2025 Update 6）：正交/三斜各 540 原子、558 键、912 角、1212 二面角逐项通过。
  数据容差见示例 README；质量/盒子与坐标保留 STK 的更高精度。类型数 GMSO 15/16/25/30 → STK 10/9/14/13，
  每项实际势系数不变，分子编号按六条键连通链而非默认 residue。
- 真实 LAMMPS 读回 STK 正交/三斜六个晶胞参数与 ParmEd 输入一致（绝对容差 `1e-10`）。
  GMSO 0.17.0 三斜 data 头使用 dump 外包围边界，实际读回体积 **45648.625 Å³**，STK/输入 **29188.420 Å³**；
  这是参考实现错误，验收明确记录差异，未声称原始文件头相等。
- 同几何 `run 0` 的键、角、二面角、LJ、短/长程静电与总势能全部通过（`0.002 kcal/mol` 或相对 `1e-9`）；
  总势能差约 `1.1e-5 kcal/mol`。在直接比较原文件能量时发现松散填充重叠构型放大 GMSO 的坐标舍入误差，
  因此几何精度独立检查，能量检查显式使用同坐标/同晶胞以隔离系数转换。
- STK 写出 **0.044/0.045 秒**，GMSO 写出 **62.15/62.53 秒**，转换 **11.69/11.32 秒**；
  [原始报告](../examples/pet_lammps/validation/2026-10-11-writer.json)保留实际量值与所有差异。
- 代码 `057f96d`：[Runtime](https://github.com/sijintech/stk/actions/runs/38157976224) **8/8**、
  [桌面](https://github.com/sijintech/stk/actions/runs/38157976221) **5/5**、
  [密钥扫描](https://github.com/sijintech/stk/actions/runs/38157976223)、[文档](https://github.com/sijintech/stk/actions/runs/38157976220)均已完成通过；无原生产品代码改动。
  剩余限制：建模步骤与 PET 电荷仍待决定；不支持任意力场或所有 ParmEd 势项，
  不输出速度，RB 只允许源舍入级常数。540 原子历史电荷夹具不构成材料参数/性质验收。

## 2026-10-11：PET 可行性材料移入仓库后的复验

- `examples/pet_lammps/build_pet.py`（分子建模模块的 Python，mBuild 1.4.0、foyer 1.2.0、GMSO 0.17.0）：6 条 4 聚体链 540 原子、558 键、912 角、1212 二面角，
  净电荷 0.0000；填充 0.5 秒、foyer 5.9 秒、GMSO 转换 11.8 秒、写出 61.4 秒；foyer 对 384 个 improper 不给参数（RB 形式按 proper 处理）。
- `examples/pet_lammps/acceptance`（真实 LAMMPS 22 Jul 2025 Update 6 MPICH 版，经项目工作流与本机运行环境）：**2 passed**（26 秒）；
  LJ 两行设定 2.0/3.0，平均 1.03/1.672（`lj` 单位）；PET 两行设定 450/550 K，平均 445.758/551.423 K，与 2026-10-10 一致；算例文件夹未被写入。

## 2026-10-10：E1a LAMMPS 计算引擎

- Python：`test_lammps.py` 26 项——脚本检查（参数的 index 默认值、拒绝的命令、引号中的命令、任意深度的 include 与其中的参数、变量拼出的变量样式、
  不误拒核壳模型与多行三引号）；用真实 LAMMPS（22 Jul 2025）的日志节选读出 2 段热力学输出、单位、平均密度 1.2225 g/cm³，
  截断、ERROR、NaN、`thermo_style multi` 各自判为失败；TaskSpec 不带算例文本；启动器（假 LAMMPS）传 `-var`、记录输出、NaN/ERROR/未正常结束、
  拒绝脚本中的 `shell`、没有 MPI 的程序拒绝多进程、本机 MPI 规则、拒绝已有输出、改写输入判失败、SIGTERM 时仍写报告、`verify` 与 `check`；
  最终状态保留报告且不截断。`test_workflow_lammps.py` 7 项——导入读出参数与默认值、拒绝含输出或脚本不明的文件夹与含 `shell` 的脚本（项目不变）、
  两行经工作流步骤 `lammps/1` 在真实本机运行环境上运行并收集（结果表的平均密度随温度变化）、空着的参数在准备时被拒、复制不要求行已填完。
- 本机实测（手动，不进 CI）：真实 LAMMPS（MPICH 版）经项目工作流运行 LJ 熔体两行（`lj` 单位、默认热力学列）与 PET 模型两行
  （最小化 + 2 ps NVT，设定 450/550 K，平均 445.8/551.4 K）；`suan.lammps check` 报告 MOLECULE、KSPACE 与 MPICH；2 进程区域分解为 `1 by 1 by 2`、
  结果与单进程相同。改用固定版本前，conda-forge 默认的无 MPI 版本在 2 进程下两份各自完整运行、日志互相覆盖却显示成功（已防止）。
- 完整 pytest（`-m "not perf"`）：审查前 2414 passed、3 failed（固定的模板列表，已更新），审查修正后 **2427 passed、24 skipped**；
  Python 3.11 上 LAMMPS、引擎模板与 MuPRO 测试 81 passed。原生代码未改；工作流、仿真、模块与智能体相关 CTest **69/69**。
- CI：`1859ca7` [Runtime](https://github.com/sijintech/stk/actions/runs/38097721893) 8/8（3.12 2442 passed，3.11 与 3.14 各 2438 passed）、
  [桌面](https://github.com/sijintech/stk/actions/runs/38097721844) 5/5，密钥扫描通过。
- 建模性能（手动，不进 CI）：GMSO 写数据文件约 0.13 秒/原子（540/1080/2160 原子 63.5/128.2/246.2 秒，另有转换 11.8/23.0/46.0 秒），见方案。

## 2026-10-10：E0b 模块管理

- Python：`test_modules.py` 9 项（假的 micromamba，不下载）——目录与固定的 micromamba 摘要；PATH 上已有的程序被检测、读出版本、不重装、不移除；
  缺少的模块从 conda-forge 安装（参数、`--override-channels`、独立的根目录、安装程序看不到测试设置的密钥变量）、可移除；
  网络设置不允许外网时拒绝安装、失败与取消不留下环境；Python 工具包按能否导入检测；半装的环境不算安装且可重装；
  重复安装返回同一任务、完整检测不碰正在安装的模块、网络改为离线时取消；损坏或别的版本写的登记表被安全读取。连续 3 次通过。
- 原生：`ModulesPython` 1 项（真实后台服务、隔离的模块文件夹与假程序）——工作台“计算模块”自动检测到 PATH 上的 LAMMPS 并显示版本，
  安装缺少的 Packmol 后显示“STK 已安装”，移除后恢复为可安装。连续 3 次通过；Windows 上跳过（假程序是 shell 脚本）。
- 本机实测（手动，不进 CI）：真实 micromamba 2.9.0（下载并核对 SHA-256）从 conda-forge 安装 Packmol 21.2.1（147 秒，含下载 micromamba）、
  LAMMPS 22 Jul 2025 Update 6（126 秒，1.8 GB）、分子建模工具包 mBuild 1.4.0 + foyer + GMSO + RDKit（169 秒），重新检测均为“STK 已安装”且版本正确。
- 完整 pytest（`-m "not perf"`）**2390 passed、24 skipped**；完整 Linux CTest **1289/1289**（审查修正前后各一次）。
- CI：`2d24b4c` [Runtime](https://github.com/sijintech/stk/actions/runs/38070858627) 8/8（3.12 2405 passed，3.11 与 3.14 各 2401 passed）、
  [桌面](https://github.com/sijintech/stk/actions/runs/38070858576) 5/5（Windows 不跑 `ModulesPython`），密钥扫描通过。
- CI 发现：`6a2a2b4`（只改文档）的 Runtime 在 Python 3.14 上 1 项失败——S2a 的 `test_the_agent_outlines_…` 用“结构里不含 301”判断没有泄露数值，
  而随机 UUID 恰好含“301”；测试改为去掉标识后比对实际的单元格值（测试本身的问题，产品代码不受影响）。

## 2026-10-10：E0a 计算引擎模板接口

- Python：新增 `test_engine_templates.py` 3 项（entry point 注册、内置标识不可替换、缺接口与导入失败被报告且只加载一次、批处理可用、
  `choices()` 的 `remote`/`local`、MuFerro 提供完整接口）；`test_mupro.py` 改为检查新名 `STK_ALLOW_LOCAL_MPI` 并保留旧名有效。
  MuFerro 的工作流、批处理与 Runtime 测试（`test_bridge_workflow_muferro.py`、`test_workflow_muferro.py`、`test_workflow_batches.py`、
  `test_mupro*.py`、`test_integration_mupro.py`）全部通过。完整 pytest 首次 **3 failed**（固定了旧的 `choices()` 形状 2 项、提示文字 1 项），
  更新后完整 pytest **2381 passed、24 skipped**。
- 原生：完整 Linux CTest **1287/1288**，唯一失败为 `wm_app_window_weston`（Wayland 窗口测试，单独重跑连续 3 次通过，与已记录的 Wayland 偶发同类）。

## 2026-10-10：S3a 材料预测模型

- Python：`test_materials.py` 11 项——合成回线（低于 T_c 时 P_r 与解析值 31.6 μC/cm² 相符、矫顽场在单畴本征值的 0.95–1.25 倍、远高于 T_c 只剩很窄的回线、
  频率高时回线变宽）、合成衰减（高温更快、确定性）、读出（已知曲线、缺失点、末点恰好 80%、一开始就低于 80%，从不出现 NaN）、数据集契约
  （合成数据卡与摘要、9 种格式错误只报告不抛错、极端数值不溢出）、训练（衰减模型过门槛并登记、过小的网络被拒、版本与回滚、预测与真值相差 < 0.05；
  回线模型读出误差、只按权重加载、取消；registry.json 丢失后版本号不复用、最后一轮之后取消不登记、损坏的登记表报告为不可用）、
  后台服务与脚本（`materials.*`、相对路径被拒、没有 PyTorch 时 `unsupported`、协议无违例）。连续 3 次通过。
  本机 PyTorch 2.14.1+cpu；Python 3.11 与 3.14 没有 PyTorch，需要它的 4 项跳过、其余通过。
- 完整 pytest（`-m "not perf"`）：审查前 **2375 passed、24 skipped**，审查修正后 **2378 passed、24 skipped**。原生代码未改。
- CI：`8f10cc7` [Runtime](https://github.com/sijintech/stk/actions/runs/38059670305) 8/8（3.12 任务装了 PyTorch CPU，2393 passed；
  3.11 与 3.14 没有它，各 2389 passed，训练的 4 项跳过）、[桌面](https://github.com/sijintech/stk/actions/runs/38059670250) 5/5，密钥扫描通过。

## 2026-10-10：S2b-2 桌面智能体界面

- 原生（真实 Python 后台服务、脚本化模型 `desktop/tests/bridge/agent_bridge.py`，不发出任何模型请求）：`AgentPython` 4 项——
  选“智能体（多步）”、显示本机规划模型、发言后时间线列出“[读] 查看项目结构”“[记录] 取行”与提议草案，卡片“打开修改检查”后经会话应用
  （修订 +1、表格 4 行、会话有批准与回执、卡片改为运行新增的行、核对记录通过）；丢弃记入会话；工作台“需要关注”列出会话（无归档按钮），
  点“打开”回到 AI 助手并选中该会话、来源指向该会话；规划轮被挂起时会话显示运行中、发送不可用、输入框已清空，取消后停于 `cancelled`。
  数据页：格式 13 的三档下拉框（公开、结构公开、私有，标注不推进修订）与格式 12 的复选框各 1 项。新增与改动的测试连续 3 次通过。
- Python：`test_attention.py` 新增 1 项（会话按状态归组、键含消息序号、目标含项目 ID、损坏的记录显示为“记录损坏”而不影响其他项）。
  完整 pytest（`-m "not perf"`）审查前 **2367 passed、24 skipped**，审查修正后同为 **2367 passed、24 skipped**。
- 完整 Linux CTest：审查前 **1286/1286**；审查修正第一次运行 **1279/1288**——修改检查页的门槛把“来源尚未读到”的普通草案也挡住，
  5 个草案应用/丢弃测试失败，`project_drafts_render_*` 4 项因渲染程序在丢弃被拒后对未绘制的界面取空指针而崩溃（测试程序的问题，产品代码不受影响）；
  改为“来源未读到按普通草案”后 **1288/1288**。
- 真实本机模型（手动，不进 CI；后台服务层，未经桌面界面）：用 S1c 安装的 `qwen3.5-4b-q4_k_m`（llama.cpp b11429，48 核 CPU、无 GPU，
  网络设置“离线”），在真实的本机 Runtime 与合成求解器上走“验收演示”第 1–4 步（脚本在会话草稿区 `live/test_live_agent.py`，结果
  `/home/mnemora/opt/stk-live-s1c/agent-report.json`）。规划候选只有这个本机模型（`tiny` 档）。
  第一轮 339 秒：查看结构 → 取行 → `propose_sweep` 三次——这个 4B 模型回答的扫描子请求前两次不可用（“只支持标量字段”“不是严格的 JSON”），
  智能体改写说明后第三次得到 5 行草案 → 查看草案状态 → 以文字说明需要人检查、应用并运行后停下；修订不变、Runtime 没有任务。
  `decide(apply)` 后修订 +1，人运行 5 行（10 个任务成功）。第二轮 119 秒：直接从 `observed` 读到运行 ID → 取结果 → 统计一次参数错误
  （拟合多给了 x 字段）后改正 → 正确说明 5 个温度下能量相同（合成求解器的结果）。`verify` 通过（11 个规划轮），用量为规划 56,407/1,481
  token、代问 3 次 7,376/1,797 token。结论：4B 本机模型能完成整个流程，但子请求的结构化回答不稳定、要靠重试；桌面界面上的同一流程与 9B 模型仍待人工验收。
- 未做：在桌面界面上的人工验收与截图（[工作台清单](workbench-acceptance.md)“AI 智能体（多步）”）。
- CI：`9fbbe10` [桌面](https://github.com/sijintech/stk/actions/runs/38027562437) 5/5（含必跑的 `AgentPython.*`）、
  [Runtime](https://github.com/sijintech/stk/actions/runs/38027562455) 8/8，密钥扫描通过。

## 2026-10-10：S2b-1 智能体的扫描提议、结果分析与签名批准

- Python（规划与子请求都用脚本化的假模型，不发出任何真实模型请求）：
  - `test_agent.py` 27 项（S2b-1 新增 6 项：扫描步骤重放得到同一请求与草案且只问一次；过期上下文不发请求、有运行写入时拒绝、
    不确定的子请求作为错误且重放不重发；`decide` 的等待项、草案与修订检查及脚本不能调用；失败步骤仍登记对象、中文长回答按字节截断、
    取消后什么也不建；重放时丢失执行器留下的“运行中”子请求 5 秒内记为不确定；应用失败后可再批准、卡片上的决定写为 `observed` 并交给规划模型）；
    `test_agent_sessions.py` 2 项（等待项只在回执成功后解决）。
  - `test_agent_muferro_acceptance.py` 2 项（真实的本机 Runtime、假 MuPRO SDK 与合成求解器）：提议 5 个温度的草案（修订不变、Runtime 无任务、
    不存在的工具得到错误结果）→ `decide` 的冲突与 `not_found` 错误码 → 批准应用（修订 +1，批准先于回执）→ 人运行 5 行 → 分析
    （`observed` 记录决定与运行、5 行结果上下文、统计与直接计算一致、子请求回答、`verify` 通过、用量为 11 个规划轮加 2 个子请求、分析不改修订）；
    监视器确认智能体线程从未调用应用草案、改项目、准备或开始运行与标注。私有数据：只有外部端点时没有规划候选；会话读过私有表结构后扫描提议留在本机，
    该表结构公开后同一提议才去外部端点，规划轮始终在本机。
  - 相关 31 项在 Python 3.11 与 3.14 上通过；新增与改动的测试连续 3 次通过。
  - 完整 pytest（`-m "not perf"`）：审查前 **2363 passed、24 skipped**，审查修正后 **2366 passed、24 skipped**。
- 原生：未改；完整 Linux CTest **1283/1283**（审查前后各一次）。
- 未做：桌面界面与真实模型的人工验收（S2b-2）。
- CI：`86dd521` [Runtime](https://github.com/sijintech/stk/actions/runs/38023585936) 8/8、密钥扫描通过；[桌面](https://github.com/sijintech/stk/actions/runs/38023585934) 4/5——
  Linux 任务唯一失败为已知的偶发 `wm_app_window_weston_csd`（Wayland CSD 窗口退出时 SIGSEGV，见 2026-09-30 的记录，根因未定；本提交未改 C++），
  其余 1282 项与 macOS、Windows、两个打包任务通过。

## 2026-10-09：S2a 智能体 harness

- Python（规划模型都是脚本化的假适配器或本机 HTTP 假服务器，不发出任何模型请求）：
  - `test_agent.py` 21 项：完整的“结构→取行→统计→回答”且不改项目、审计重组每一轮输入并重算统计；未知工具、非法参数与连续错误；
    上限前的总结轮；不确定即结束且不重发；取消；规划只用本机或机构内端点（外部端点在认领前被拒）；确定失败换端点；
    线格式只接受单个工具调用；脚本目录全部操作都有级别；经后台服务运行；真实的 OpenAI 兼容适配器（本机 HTTP）。
    审查后新增 11 项：丢失的认领不重发（第一条与后续消息）、丢失的工具调用得到 unknown 结果且编号连续、工具异常与统计溢出仍有结果、
    记不下的回复与上限时的工具调用、重复的模型调用 ID（不同上下文、审计按所属调用重算）、结果记下当时的标注、`create` 重放、
    上一轮正在结束时再发消息（确定性地卡在 `stopped` 之后）、分页、格式错误的 `function`、服务的 `busy` 消息与句柄检查。
    `test_agent_sessions.py` 2 项；`test_labels.py` 6 项（含真实格式 12 标注表的升级：行、ID、自增序号、新约束与完整性检查）。
    新增与改动的测试连续 3 次通过；Python 3.11 与 3.14 上相关 35 项通过。
  - 完整 pytest（`-m "not perf"`，不设 `STK_TOKEN_PLAN_MODEL`）：审查前 **2347 passed、24 skipped**，审查修正后 **2358 passed、24 skipped**。
- 原生：格式常量改为 13；桌面“按行运行”的门槛改为格式 10。完整 Linux CTest **1283/1283**（审查前后各一次）。
- 未做：桌面界面（S2b）、真实模型的人工验收（S2b）。
- CI：`bfacf38` [桌面](https://github.com/sijintech/stk/actions/runs/38018846172) 5/5、[Runtime](https://github.com/sijintech/stk/actions/runs/38018846206) 8/8，密钥扫描通过。

## 2026-10-09：思劲平台 S1d（能力分档与自动切换）

- Python：`test_model_routing.py` 6 项，覆盖以下内容：
  - 提问选最近最小的模型、参数建议选最强的模型；
  - 私有数据、网络设置与缺密钥的排除；
  - 档位来源（目录、声明、按位置）；
  - 经后台服务路由（离线时、Token Plan 未设模型时、脚本 `route_model`）；
  - 端点声明档位与非法档位被拒；
  - 失败过的与目录里已没有的本机模型不作首选。

  `test_model_gateway.py` 增加两项：连不上的端点确定没有收到请求（`DefinitiveFailure`）；连接中取消记为已取消。
  `test_local_models.py` 增加一项检查：无法开始的启动也发出失败进度事件。
  完整 pytest（`-m "not perf"`，不设 `STK_TOKEN_PLAN_MODEL`，与 CI 相同）**2333 passed、24 skipped**。
- 原生（真实 Python 后台服务、假的 llama-server）：
  - 私有数据而只有 Token Plan 时，“自动”说明没有模型可用，“准备”不可用。
  - 加入一个连不上的本机端点和一个已安装未运行的本机模型后，“自动”先选连不上的那个。发送后它记为 `failed/adapter_failed`，自动改问本机模型：先启动、再发送，得到回复并显示改问的说明。
  - 两个本机模型中排在前面的那个启动即退出时，改问下一个并说明“无法启动”。

  两项各连续 3 次通过。另有 11 个原有原生测试改为显式选择 Token Plan，因为默认已是“自动”。完整 Linux CTest **1283/1283**。
- CI：`5c3c7b6` [桌面](https://github.com/sijintech/stk/actions/runs/37950071468) 5/5、[Runtime](https://github.com/sijintech/stk/actions/runs/37950071394) 8/8，密钥扫描通过。

## 2026-10-09：Python 下限升到 3.11

- 本机各版本全量非桌面测试（`-m "not desktop and not perf"`，与 CI 相同的 extras，可编辑安装）：Python 3.11.16 **2325 passed、22 skipped**；
  Python 3.14.4 首次 **2 failed**（`test_listing_prefixes_links_and_loops`、`test_symlinked_case_directory_and_link_loops`：3.13 起符号链接环在打开文件时才以 ELOOP 报错），
  修正后 **2325 passed、22 skipped**，相关文件在 3.11、3.12、3.14 上均通过。Python 3.12.14 完整 pytest（`-m "not perf"`）**2325 passed、24 skipped**。
- 完整 Linux CTest **1281/1281**。
- CI：`e4c0160` [Runtime](https://github.com/sijintech/stk/actions/runs/37912673513) 8/8（Linux 3.11、3.12、3.14，Windows 客户端 3.11、3.12，以及桌面、控制服务、网页），[桌面](https://github.com/sijintech/stk/actions/runs/37912673412) 5/5，密钥扫描通过。

## 2026-10-09：思劲平台 S1c（本机一键部署）

- Python：`test_local_models.py` 17 项（推荐规则、硬件探测、目录必须给出大小与哈希、**随 STK 发布的目录**完整且每项符合桌面协议、
  按机器推荐 Qwen（4 GiB 可用内存→无、5 GiB→4B Q4 的 8K 版、7 GiB→4B Q4、10 GiB→9B Q4、50 GiB 纯 CPU→35B-A3B Q4、100 GiB→其 Q8、
  24 GB GPU→27B Q4 且内存再多也不改选 CPU 上的 MoE、12 GB GPU→9B Q4 在 GPU 上、48 GB 卡与 4×H100→27B Q8、H100 的 81559 MiB 算 80 GB；
  Windows 与 Linux arm64 随附 CPU 版、Linux 没有 Vulkan 时按内存推荐；Apple 统一内存按 Metal 默认份额且不超过可用内存）、
  目录拒绝非法的 `recommend_on` 与数值字段、已下载的部分不再计入所需磁盘、
  下载续传与换源、短读与分块中断后续传、服务器忽略 Range、续传字节损坏时从头再下、解包不越界（zip 路径、tar 符号链接与硬链接）、端点 ID、
  经后台服务安装→启动→提问→停止（服务器有受管密钥且不在命令行、`--no-slots`、`--reasoning off`，其环境不含 Token Plan 与其他端点密钥；
  设置了同名 `STK_MODEL_KEY_*` 时受管密钥仍优先；端点标为 `managed`、不能改密钥或单独移除，`local-` 开头的 ID 不能手动添加，停止后受管密钥清除）、取消后续传、
  两个安装共用一次运行时下载、改为离线时取消下载、离线导入（其间改网络设置不会取消导入；去掉修正后此项失败）、启动失败与运行中退出、启动中停止、随服务停止与下次自动启动、遗留进程回收、无法启动（运行时已删）时不再自动启动（去掉修正后此项失败）、移除）；
  `test_model_gateway.py` 增加本机与机构内端点的长期限与在途取消（本机为已取消、机构内为不确定；去掉关闭连接的修正后两项都失败）。
  完整 pytest（`-m "not perf"`）**2325 passed、24 skipped**（审查修正前后各跑一次，结果相同）。
- 原生：`LocalModelsPython` 经真实 Python 后台服务显示硬件（含可用磁盘）与推荐、安装、启动，AI 助手的端点列表把它列为本机端点（原生测试不提问，
  提问由上面的 Python 测试与下面的真实运行覆盖），其端点标为 `managed`、在端点列表中不能单独移除，停止后显示“已安装，未运行”，移除后端点消失（反复运行均通过）。
  完整 Linux CTest **1281/1281**（审查修正前后各一次）。
- 目录核对：317 个下载地址（13 个不同模型项的 156 个文件 × ModelScope 与 Hugging Face，加 5 个 llama.cpp 构建；8K 版与 4B Q4 共用文件）用 Range 请求核对总长度，
  其中 10 个 GGUF 文件的 20 个地址另核对 GGUF 文件头，全部一致（6 个 Hugging Face 地址首次 TLS 中断，重试通过；ModelScope 的小文件不支持 Range，下载器按“忽略 Range”处理）。
  b11429 的 Linux（CPU、Vulkan）、Windows CPU 与 macOS arm64 构建经 `_extract` 解包，哈希一致；Linux 两个版本的 `llama-server --version` 可运行，
  Vulkan 版在没有 GPU 的机器上列出 0 个设备并用 CPU（`llama-server` 本身不链接 `libvulkan`）。
- 真实运行（手动，不进 CI；48 核 CPU、121 GB 内存、无 GPU）：推荐 `qwen3.6-35b-a3b-q8_0`；安装 `qwen3.5-4b-q4_k_m` 经代理从 ModelScope 下载
  2.7 GB 用 220 秒并核对哈希，llama.cpp b11429 运行时自动下载解包；启动 5.2 秒就绪并登记为本机端点；网络设置为离线时私有数据的问题发往该端点。
  首次提问在 60 秒时成为“不确定”（网关期限过短，已修正）；修正后带思考 188.6 秒完成（生成 2,335 个 token，13 token/秒）；
  `--reasoning off` 后 14.9 秒完成（提示 1,108 个 token 用 11 秒，回答 52 个 token）。不带密钥访问 `/v1/chat/completions` 与 `/slots` 均返回 401。
  审查修正后以提交 `caffb4a` 再跑一次（服务器环境已去掉密钥类变量、不再指定 `-ngl`、受管密钥）：启动 5.2 秒，提问 15.7 秒完成，不带密钥仍返回 401，停止后不再自动启动。
- CI：`caffb4a` [桌面](https://github.com/sijintech/stk/actions/runs/37889597094) 4/5——macOS 的 `LocalModelsPython` 在 30 秒内未见服务器就绪，日志没有原因；Linux、Windows 与两个打包任务通过。[Runtime](https://github.com/sijintech/stk/actions/runs/37889597053) 4/7——Windows 3.10/3.12 的在途取消测试失败（Windows 上从另一线程 shutdown 不会唤醒阻塞的接收，改为随后关闭句柄，在 Linux 上模拟 Windows 分支通过）；Windows 3.12 的 `test_servers_stop_with_the_service_and_start_again_with_the_next` 失败（测试里“被杀掉的服务”仍有监护线程，它把被回收的服务器记为失败并关掉了共享状态中的自动启动，测试改为同时清掉其内存记录）；Linux 3.10 的 MuFerro 排队计时测试失败，与本次改动无关。密钥扫描通过。修正：两个测试 HTTP 服务器不再做反向 DNS 查询（macOS 上可能很慢，未证实为原因），原生测试超时时打印服务端看到的状态、错误与服务器日志、等待改为 60 秒。本机修正后完整 pytest **2325 passed、24 skipped**、完整 Linux CTest **1281/1281**。
- CI：`b88e3a2` [Runtime](https://github.com/sijintech/stk/actions/runs/37892738677) 7/7（Windows 在途取消通过；MuFerro 计时测试这次通过，记为偶发），[桌面](https://github.com/sijintech/stk/actions/runs/37892738710) 4/5：去掉反向 DNS 查询后，macOS 上整个 `LocalModelsPython` 只用 0.64 秒（此前 30 秒内服务器仍未就绪，原因即 macOS 上 `HTTPServer` 的反向 DNS 查询）；剩下的失败是测试在端点出现的同一帧就断言“Running”，而本机模型列表要到下一次读取才更新，`ef79bc5` 改为等待两者都出现。`ef79bc5` [桌面](https://github.com/sijintech/stk/actions/runs/37895399616) 5/5（含 macOS Metal）、[Runtime](https://github.com/sijintech/stk/actions/runs/37895399573) 7/7、密钥扫描通过。

## 2026-10-08：思劲平台 S1a/S1b（模型网关与数据边界）

- Python：`test_labels.py` 4 项（默认私有、标注与列表不改修订与历史、事件、未知对象与错误标签拒绝且不写入、格式 11 升级后可标注、脚本 API）；
  `test_model_gateway.py` 11 项（端点位置与 URL 规则、0600 存放、密钥来源与不外露、网络设置、私有数据不发往外部端点且请求保持待发送、
  离线拒绝外部端点、本机假服务器收到私有数据与流式回复且推理文本被丢弃、密钥作为 Bearer 发送且不出现在 `models.list`、
  端点不提供的模型被拒、脚本只能读取模型设置、HTTP/1.0 与 `Connection: close` 服务器下普通与流式回复都能读完——去掉读取器修复后这两项失败）。
  桥接请求测试改为先把上下文表标为公开。完整 pytest（`-m "not perf"`）**2306 passed、24 skipped**。
- 原生：数据页“公开数据”切换写入并撤回标注且不改修订；AI 助手对未公开数据的外部端点说明原因并禁用发送，标注后可发送，离线时说明网络设置不允许，
  添加本机端点后选择它、问题按其适配器与模型保存，私有数据也可发往本机端点。完整 Linux CTest 首次 **1270/1278**（流式测试 4 项、AI 流式截图 4 项，原因见开发记录），
  修正后 **1280/1280**。
- CI：`622979a`（含 `75b69aa`）[桌面](https://github.com/sijintech/stk/actions/runs/37869624479) 5/5、
  [Runtime](https://github.com/sijintech/stk/actions/runs/37869624480) 7/7、密钥扫描与文档站部署通过。

## 2026-10-08：归档改为“冻结”（所有者澄清）

- Python：`test_archive.py` 改为验证冻结规则——修改已归档对象（保存工作流、重试运行记录、应用/放弃草案、发送问题）被拒且修订不变；
  已归档工作流照常准备并运行一次新运行（完成，且新运行未归档），已归档上下文可添加消息并建请求，恢复后草案可放弃；
  已归档分析不影响工作流校验，含该分析的工作流运行完成两项任务，直接准备分析运行不因归档被拒。删除批次控制台检查的测试（检查已撤去）。
- 原生交互：已归档工作流的“运行”仍可用、编辑不可用，“复制为新工作流”生成可编辑的“Temperature scan (copy)”，原工作流在已归档列表中恢复（修订只因复制增加一次）；
  已归档的已准备分析运行不能开始，恢复后可以；已归档草案可载入查看，“应用/放弃”不可用，经“以当前修订另起草案并检查”复制后应用（修订 1→2，原草案仍待审）；
  已归档问题不能发送，已归档上下文可添加消息与提问；“讨论”页可在已归档上下文中记消息。
- 完整 pytest（`-m "not perf"`）**2291 passed、24 skipped**（少一项为删除的批次控制台测试）；完整 Linux CTest **1278/1278**。
- CI：`a7b91cf` [桌面](https://github.com/sijintech/stk/actions/runs/37811715874) 5/5（Linux、Linux 打包与冒烟、macOS Metal、Windows）、
  [Runtime](https://github.com/sijintech/stk/actions/runs/37811716006) 7/7、密钥扫描通过。

## 2026-10-08：归档 A2（桌面）与 A3

- 原生交互 8 项（真实 Python 后台服务）：工作流归档后离开列表、仍显示且只读（“添加步骤”不可用）、运行区提示先恢复，连带的运行离开运行列表，
  “显示已归档（1）”切换后只列已归档，恢复后可编辑、修订不变（A2a）；分析归档后离开列表、参数表不可用，分析运行单独归档与恢复；
  草案、AI 问答历史、所选上下文已归档时不能提问、仿真运行（已归档不能提交）、仿真批次（界面过滤）、“讨论”页上下文（已归档不能添加消息）；
  引用已归档分析时工作流显示“引用的分析已归档”问题、恢复后通过，Home“需要关注”中失败的运行直接归档后离开列表与状态栏计数（不计为“已看”）。
- Python：`test_archive.py` 增加校验 `archived_reference`（恢复后通过；准备运行仍以“uses an archived analysis”拒绝）。
- 完整 pytest（`-m "not perf"`）**2292 passed、24 skipped**。完整 Linux CTest 首次 **1273/1278**：AI 请求截图 4 项与
  `RunButtonsSubmitRefreshAndCancelOneTaskWithoutChangingTableRevision` 失败（列表在归档状态同步前读取、首帧重读使按钮短暂不可用，见开发记录）；
  修正后这 5 项及全部归档测试重跑通过，完整 CTest **1278/1278**。
- A2a 单独提交前完整 CTest 1269/1271（仅两项 i18n 检查因尚未提交的 A2b 源码缺少文案而失败，A2a 本身无失败），工作流编辑器 16 项通过。
- CI：`54be45d`（A1a）[桌面](https://github.com/sijintech/stk/actions/runs/37751721483) 5/5 通过；[Runtime](https://github.com/sijintech/stk/actions/runs/37751721471)
  client-windows 两项失败于 `test_serve_handles_oversized_lines_and_eof`（Windows 临时路径较长，`hello` 回复超过测试的 4096 行长上限），
  `2fa87b4` 改为 8192 后 [Runtime](https://github.com/sijintech/stk/actions/runs/37756034855) 7/7、[桌面](https://github.com/sijintech/stk/actions/runs/37756034787) 5/5 通过（覆盖 A1b `841d4ba`）。
  `f1e97a7`（A2a）[Runtime](https://github.com/sijintech/stk/actions/runs/37759548427) client-windows (3.10) 一项失败：
  `test_request_executor.py::test_capacity_limit_preserves_pending_and_cancelled_live_workers_keep_their_slot` 在 5 秒内未到达受控边界
  （A2a 未改 Python，3.12 同一测试通过；此前无记录），重跑失败作业后通过，Runtime 7/7；记为 Windows 上的计时偶发失败，未修改测试，再出现时需查看；
  [桌面](https://github.com/sijintech/stk/actions/runs/37759548495) 5/5 通过。
  `9f03540`（A2b、A3）[桌面](https://github.com/sijintech/stk/actions/runs/37762694960) 5/5（Linux、Linux 打包与冒烟、macOS Metal、Windows）、
  [Runtime](https://github.com/sijintech/stk/actions/runs/37762694990) 7/7 通过。

## 2026-10-08：归档 A1b（列表过滤、只读、需要关注与搜索）

- Python 5 项：5 份草案归档第 2、4 份后，未归档列表按页为 [1,3]、[5]（`next_offset` 正确），已归档列表为 [2,4]，不过滤时仍为全部；
  受管表格（分析）的 `total` 随过滤；工作流运行按工作流且未归档为空、已归档列出该运行。已归档的工作流不能保存或准备运行，已归档的运行不能开始，
  已归档的草案不能应用或放弃，已归档的上下文不能添加消息或对其消息建请求，已归档的请求不能发送；修订不变、读取照常，恢复后可再操作；
  引用已归档分析的工作流不能准备运行，已归档分析不能准备分析运行；失败的运行归档后离开“需要关注”；搜索把已归档工作流标注并排在未归档之后；
  批次在控制台检查归档（旧服务视为无归档）。
- 完整 pytest（`-m "not perf"`）**2292 passed、24 skipped**；schema 改动后重新编译，完整 Linux CTest **1270/1270**。

## 2026-10-08：归档 A1a（格式 11）

- Python 4 项：九类中五类一起归档（备注、计数、事件 `project.archive.changed` 列出类别），项目快照与历史不变；重复归档不计也不通知；恢复两类后列表只剩其余；
  运行中的工作流运行、不存在的草案、类别不符的对象使整次调用被拒且不写入；工作流连带两次已停止的运行（运行中的不动）并可一起恢复；
  格式 10 项目读取为空、归档提示升级，升级到 11 后可归档。
- 完整 pytest（`-m "not perf"`）**2287 passed、24 skipped**；完整 Linux CTest 首次 1267/1270，3 项因格式提升失败（固定的格式号 10、伪造旧格式时未删除新表），
  修正后这 3 项及相关的 24 项重跑通过。

## 2026-10-07：P2 L2 运行新增的行、L3 结果回到对话；Metal 释放修复

- 真实后台服务的界面测试（扩展 L1 测试）：应用扫描草案后在 AI 助手点击“用工作流运行新增的 N 行”，工作流编辑器选中使用该表的工作流，
  运行区按钮为“Run the 3 selected rows”，基准行未勾选、3 个新行已勾选，没有开始运行。
- MuFerro 工作流界面测试（扩展 W5b 测试）：运行完成后“Ask about the results of these 3 rows”捕获上下文（标题“Results of MuFerro scan (3 rows)”，
  3 行 × 温度/最终步数/能量 3 个字段）并打开 AI 助手。
- Python：工作流摘要的 `table_id`（精确形状测试更新）。完整 pytest（`-m "not perf"`）**2283 passed、24 skipped**；完整 Linux CTest **1270/1270**。
- CI `8857d0b`（W5b）：Linux、Windows、打包与冒烟通过；**macOS 的 `workflow_run_wide_render_metal_en` 再次报告 1 个 `MTLSafeFreeList`（65624 字节）未释放**。
  原因：Blender Metal 的 `MTLBufferPool::free()` 只删除各安全释放列表的首块，没有删除溢出时串联的块（`update_memory_pools()` 会遍历）；
  绘制较多的截图在退出时释放的缓冲超过一块（8192 个）就会漏掉一块。供应商补丁 `0002-metal-free-safe-list-chains.patch` 修复，`vendor.py` 重新生成并 `--check` 通过；
  Linux 不编译 Metal 代码。CI `20c8570`（含 L1、本修复与 L2/L3）：desktop 全部作业（Linux GL/Vulkan、macOS Metal、Windows、打包与冒烟）、Runtime、
  Secret scan、Cloudflare Pages 通过——macOS 编译补丁成功，`workflow_run_wide_render_metal_en` 通过（此前是间歇失败，需继续观察后续运行）。

## 2026-10-07：P2 L1 AI 扫描提议

- Python 9 项：受控回复的扫描规格转换为草案（5 个新行，行 ID 为请求派生，与同参数的手工 `plan_sweep` 命令完全相同，基准行公式移到各新行），
  重复转换返回同一草案，应用后温度为 300…400 K，之后读取已保存提议不重新编译；越界字段/基准行、轴形状错误、超过 100 行、模式或格式错误均被拒绝且不保存草案；
  捕获后项目已变化时要求重新提问；经后台服务与脚本转换、无 schema 违例。
- 真实后台服务的界面测试 1 项：AI 助手第三种用途准备 `stk.parameter-sweep/1` 请求，回复显示“Based on selected row 1, every combination of the values: · Temperature: 310, 320, 330”，
  保存为草案（3 个新行，应用前表格不变），在修改检查中预览并应用后表格增加 3 行。
- 完整 pytest（`-m "not perf"`）**2282 passed、24 skipped**，另 1 项固定提问用途集合的测试补上新用途后通过（该文件 78 passed）；完整 Linux CTest **1270/1270**。

## 2026-10-07：W5b MuFerro 工作流的桌面运行区

- 真实后台服务、本机回环 Runtime 与合成求解器的界面测试 1 项：含 MuFerro 步骤的工作流在未选 Runtime 时不可运行并说明；选择后按钮为
  “Run the 3 selected rows on run-test”，点击后三行全部提交、跟踪并收集（“All done · 3/3 done”，Runtime 3 个任务、MuFerro 结果表 3 行，
  运行冻结的连接为 runtime:run-test），选中行列出仿真运行与 Runtime 任务；仿真批次的“运行所选行”测试（共用的运行环境组件）通过。
- 截图 8 张（MuFerro 工作流运行区：运行环境、运行方式与资源、案例行 × 宽/窄 × 中/英 × GL/Vulkan）检查后修正截取时机与行标签。
- 完整 pytest（`-m "not perf"`）**2274 passed、24 skipped**；完整 Linux CTest **1269/1269**。

## 2026-10-07：W5a MuFerro 按行工作流运行（服务与脚本）

- 真实本机 Runtime 与 CI 合成 MuFerro 求解器（`tests/mupro_fake.py`）的后台服务测试 6 项：两行在调度器运行前都已提交（Runtime 中 2 个排队任务）；
  完成后各行收集结果（MuFerro 结果表 2 行，温度 300/325 K）、最终状态快照含最后一帧而不含第 0 帧、下游分析收到该快照的文件；
  冻结后修改温度的行以 `row_changed` 失败且不提交，`stale` 给出温度 300→350；停止跟踪后尝试中断（`detached`），再次开始接管同一仿真运行（Runtime 仍只有 1 个任务）；
  失败的求解在重试时提交新任务（共 2 个）；取消运行使 Runtime 任务变为已取消；没有连接或行参数非法时准备被拒绝且不提交。
- 完整 pytest（`-m "not perf"`）**2274 passed、24 skipped**；schema 改动后重新编译，完整 Linux CTest **1260/1260**。
- CI `68d5811`（U2、U3）：desktop、Secret scan、Cloudflare Pages 通过；Runtime 的 `runtime (3.10)` 作业首次在 `apt-get update` 卡住（Ubuntu 镜像）30 分钟被取消、未运行测试，重新运行后全部通过。

## 2026-10-07：体验包 U3 项目内搜索

- Python 3 项：不区分大小写、去除首尾空白；单元格（表/字段/第几行/片段/导航到该行）、草案（标题与状态）与消息按固定类别顺序列出；
  字段名、表名命中；长文字在匹配处前后截取（带省略号，约 80 字）；每类最多 50 项、`limit` 截断并报告；非法查询被拒绝；只读不改项目；
  经后台服务找到工作流、分析（导航目标为对应编辑器）与登记文件（名称与路径），无 schema 违例。
- 真实后台服务的界面测试 1 项：工作台搜索“TEMPERATURE”列出“Workflows (1)”“Saved analyses (1)”，打开第一项进入该工作流；
  搜索“field.vtk”打开文件页并选中该文件行；无结果时明确说明，搜索不改修订；之后的项目修改使方框注明结果可能过时；共发出 3 次搜索。
- 截图 8 张（工作台搜索：工作流与分析结果 × 宽/窄 × 中/英 × GL/Vulkan）检查。
- 完整 pytest（`-m "not perf"`）**2268 passed、24 skipped**；完整 Linux CTest **1260/1260**。
- CI `8bcf3bf`（U4）：desktop（Linux、macOS Metal、Windows、打包与冒烟）、Runtime、Secret scan、Cloudflare Pages 全部通过。U2 `b5805ce` 与本次一并推送，由本次的 CI 覆盖。

## 2026-10-07：体验包 U2 用量可见

- Python 2 项：用量只合计已完成且带回执的请求（3/4 次有回执，输入 200、输出 45），按服务商报告的模型（没有则按请求冻结的模型）分列，
  失败与等待中的请求不计入，读取不改项目；经后台服务与 `stk.project.requests.usage()` 读取一致、无 schema 违例。
- 真实后台服务的界面测试 1 项：发送按钮显示“Send this saved question (fixture-model)”（空密钥时不可用），无完成请求时显示“尚无完成的请求”；
  经脚本以回执完成后显示“This project used 1,840 input · 212 output tokens (1 completed requests, provider receipts)”，悬停按模型分列；项目修订不变。
- AI 截图 32 张（含回执的受控完成）检查：配置区显示“本项目已用”，发送按钮注明模型；读取不使对话忙碌，按钮检查通过。
- 完整 pytest（`-m "not perf"`）**2265 passed、24 skipped**；完整 Linux CTest **1251/1251**。
- CI `63cdc0b` 的 desktop（Linux、macOS Metal、Windows、打包）全部通过：上次 macOS 的 `MTLSafeFreeList` 未释放没有再现。

## 2026-10-07：体验包 U4 工作流记住视图

- 画布单元测试 1 项：缩放、平移后的中心与缩放在另一视口大小与 2 倍界面缩放下恢复（中心图坐标误差 < 1e-9），缩放被限制在上限，非法输入不改变视图。
- 真实后台服务的界面测试 2 项：“温度扫描”选中步骤并放大后切到“Broken”再回来，缩放、中心与所选步骤与离开时一致（未恢复时会重新适应，缩放不同）；
  布局状态记录最后显示的工作流，新编辑器载入后先显示“Broken”（不是列表第一份），再切到“温度扫描”时仍是离开时的视图；格式错误的布局状态被拒绝；
  从工作台打开的失败运行在切到另一工作流再回来后仍显示。
- Python 未改动（沿用 U1 的完整 pytest 2263 passed、24 skipped）；完整 Linux CTest **1250/1250**。
- CI `63cdc0b`（含 `ac82660`）：Runtime（含 client-windows）、Secret scan、Cloudflare Pages、desktop 全部通过。

## 2026-10-07：体验包 U1 需要处理；6fc18a4 CI 修复

- CI `6fc18a4`（覆盖 `47507b8`、`3a3bd22`）：Secret scan、Cloudflare Pages 通过；Runtime 的 Linux 作业通过，**client-windows（3.10/3.12）失败**：
  测试全部通过后 `test_bridge_workflow_runs.py` 收到 KeyboardInterrupt（`os.kill(pid, 0)` 在 Windows 上发送 CTRL_C_EVENT）；
  desktop 的 Linux 与打包作业通过，**Windows** 两项工作流编辑器测试以固定帧数等待后台回复而失败，**macOS** 的
  `workflow_run_wide_render_metal_en` 退出时报告 1 个 `MTLSafeFreeList` 未释放（Blender Metal 后端时序，168 项中仅此一例，未改动，待下一次 CI 观察）。
  修复：`psutil.pid_exists`（新增只看不发信号的存活检查测试）、测试改为 `frames_until`。
- U1 Python 4 项：失败的工作流运行排第一（名称、完成数、导航目标），待审草案其次，运行中与已完成随后；列表只读不改修订；
  标记已看不改项目，状态再变化（再次中断）的运行重新出现；工作流运行产生的分析运行不重复列出；空项目与旧格式无事项；
  仿真运行（失败/排队/成功）与 AI 请求（失败/等待/完成）按状态分组。
- 真实后台服务的界面测试 1 项：第 2 行 -5 K 使合成求解失败，工作台列出“Failed · Workflow run · Temperature scan · 1/2 done”，
  状态栏“Needs you: 1”；点“打开”后工作流编辑器最大化并选中该运行（“Stopped · 1/2 done · 1 failed”），状态栏计数消失，只发出一次 viewed，
  未再准备或开始运行。其他“打开”目标（分析运行 → 分析图“运行”页，草案 → 审阅页，仿真运行、AI 请求 → 对应页面）未做界面测试。截图 8 张（工作台“需要关注”：失败的运行与已完成的运行 × 宽/窄 × 中/英 × GL/Vulkan）检查后把方框标题改为“需要关注”。
- 完整 pytest（`-m "not perf"`）**2263 passed、24 skipped**；完整 Linux CTest **1248/1248**（之后只改了测试等待方式与两处读取健壮性，
  相关的工作流编辑器、工作台导航与截图测试 20 项重跑通过）。

## 2026-10-07：W4 复查补丁（另一服务进程持有的运行）

- 后台服务测试 3 项：同机仍存活的另一服务进程持有的运行，`recover` 以 `busy` 拒绝且任务不变，`force` 后中断；
  另一进程写入的取消请求使执行器在任务之间停止；执行器意外异常记录为运行的 `stop_error`（`executor_failed`）。
- 完整 pytest（`-m "not perf"`）**2258 passed、24 skipped**；重新编译后完整 Linux CTest **1239/1239**。
- CI：W4a-2 `6049fea` 的 desktop、Runtime、Secret scan、Cloudflare Pages 全部通过；W4b `47507b8`、W4c `3a3bd22` 与本补丁同次推送，由最后一次的 desktop 运行覆盖。


- Python 1 项：未改动时无过期；改一行温度只该行过期（`value_changed` 325→330，下游 `upstream_changed`）；改分析使各行分析步骤过期；
  只改步骤名称不算过期，改步骤参数为 `step_changed`；删除行为 `row_removed`；运行本身不变。
- 真实后台服务的界面测试 1 项：两行运行完成后改第 2 行温度，面板显示“1 rows have stale results”、该行标 stale、原因“simulate: T 340 → 345”，
  “重算过期的 1 行”只运行该行（第二次准备）。截图 8 张加入过期展示并检查（加宽行列）。
- 完整 pytest（`-m "not perf"`）**2255 passed、24 skipped**；完整 Linux CTest **1239/1239**。


- 真实后台服务的界面测试 1 项：两行（300/340 K）勾选后运行，面板跟随到“全部完成 · 完成 4/4”，状态表两行均完成；
  选中第 2 行打开温度场的分析运行，分析图切到“运行”页；只发出一次准备和一次开始。
- 截图 8 张（完成的按行运行 × 宽/窄 × 中/英 × GL/Vulkan）检查后修正模板名称与运行记录刷新。
- 完整 Linux CTest **1238/1238**（Python 未改，完整 pytest 沿用 W4a-2 的 2254 passed、24 skipped）。


- 后台服务测试 5 项（`tests/test_bridge_workflow_runs.py`，分析用回显参数的替身工作进程，真实 VTK 用例除外）：3 行按顺序执行、
  每行合成输出写入尝试目录并登记为快照、分析运行带该行的参数覆盖值、每行两次普通编辑并通知；第 2 行仿真失败只停该行、
  再次开始只重做该任务（第 2 次尝试）；分析进行中取消后已完成的保留、保存的分析被修改后任务以 `analysis_changed` 失败；
  幽灵执行器占用时开始被拒、`recover` 中断后可再开始；真实体绘制分析在合成场上成功并有 payload。
- 示例项目验收：`suan demo` 的“温度扫描”经无头 `stk` 按 3 行运行全部成功，各行 `metrics.json` 温度为 300/325/350 K。
- 完整 pytest（`-m "not perf"`）**2254 passed、24 skipped**；重新编译后完整 Linux CTest **1229/1229**。

## 2026-10-07：P3 W4a-1 工作流运行存储（格式 10）

- 新增 `tests/test_workflow_runs.py` 11 项：模板参数按字段校验（类型、单位、未声明）；准备冻结行号与值、执行顺序、按行参数、
  分析内容哈希与输出目录，不改编辑修订，同请求幂等、异请求冲突、过期修订拒绝；`muferro/1`、校验有问题、两个参数表步骤在准备时拒绝；
  行不属于参数表或有公式错误时拒绝；尝试编号、其他执行器被拒、迟到的旧尝试被拒、成功后不再尝试、取消请求与停止后重新认领；
  执行器消失后中断与重新开始；篡改事件后读取失败；格式 9 项目须显式升级（带备份）；分析运行按行参数冻结与请求身份。
- 完整 pytest（`-m "not perf"`）2247 passed、1 failed、24 skipped：失败为 `test_parameter_edits.py` 中写死的格式 9，改用
  `FORMAT_VERSION` 后该文件 78 项通过。重新编译后完整 Linux CTest **1229/1229**。


- 真实后台服务的界面测试 5 项：按对象添加分析步骤→候选立即显示并报告缺输入→下拉连线→校验通过→参数改为参数表字段→保存后读回
  （第 4 步的引用、输入、`$field` 与位置）；画布拖线类型不符被拒、拖到（等待）形成环并列出、拖动位置后保存（位置与拖动距离一致）；
  Delete 删除所选步骤并级联、放弃后恢复；其他项目编辑后保留修改并保存成功、这份工作流在别处改动后修改脱离只能放弃；
  新建工作流、删除后列表减少、项目撤销后恢复。另有 `workflow_provisional_validation` 单元测试 1 项、`rebase` 断言。
- 截图 8 张（编辑中的候选 × 宽/窄 × 中/英 × GL/Vulkan）检查后修正：新增步骤在视图外（改为添加后重新适应）。
- 完整 Linux CTest **1229/1229**（W3c-2 只改 C++ 与界面文字，Python 未变，完整 pytest 沿用 W3c-1 的结果）。
- 复查后补丁：脏草稿暂时不能保存时说明原因（重新读取中/先完成文字输入，测试断言该提示），删去不可达的“（完成）只能连到（等待）”分支；完整 Linux CTest 再次 **1229/1229**。
- CI：`545d8fd` 的 desktop、Runtime、Secret scan、Cloudflare Pages 全部通过；`4583adc` 的 desktop 运行被随后推送按并发规则取消，由 `545d8fd` 覆盖。

## 2026-10-07：P3 W3c-1 工作流编辑模型

- `WorkflowDraft` 单元测试 5 项（改回原样丢弃副本与名称、步骤 ID 不冲突与删除级联、清空键的保留规则与恢复、
  13 种会被存储拒绝的编辑及过期代次/重复 ID/200 步上限、位置与名称不改变检查版本）；真实后台服务 1 项
  （各操作的候选文档经候选检查得到按键绑定的结果——新分析步骤缺输入，保存后读回与候选逐字节一致且名称更新；
  新建空工作流；`choices` 只含参数表）。Python：`choices` 1 项并扩充后台服务测试。
- 完整 pytest（`-m "not perf"`）**2237 passed、24 skipped**；完整 Linux CTest **1215/1215**。
- CI：`d6f54e6`（W3b 复查补丁）的 desktop（27 分 26 秒）、Runtime、Secret scan、Cloudflare Pages 全部通过。
  W3c-1 `387d2a4` 与 ADE 参考文档 `ec28c80` 同次推送，由 `ec28c80` 的 desktop（约 26 分钟）、Runtime、Secret scan、Cloudflare Pages 全部通过覆盖。

## 2026-10-07：P3 W3b 工作流画布与进入分析

- 原生测试 6 项（含复查后补的 1 项）：`WorkflowView` 2 项（步骤标签/类型端口/顺序连线/位置/标记、回复与文档不符时拒绝、顺序环标记）；
  `WorkflowEditorPython` 3 项（真实后台服务：显示 3 个步骤、进入分析在同一区域新增并复用分析图标签、面包屑返回原标签并保留所选步骤；
  另一分析有未保存修改时拒绝进入且草稿保持；缺失引用列为问题、“进入分析”不可用；关闭项目后面包屑消失；全程不求值、不准备运行）。
- 截图 16 张（工作流与进入分析 × 宽/窄 × 中/英 × GL/Vulkan）均检查，据此修正面包屑位置与宽度、等待节点目录。
- CI：W3b `874094b` 的 desktop（约 24 分钟，含 Windows/macOS 必需测试与 16 张截图）、Runtime、Secret scan、Cloudflare Pages 全部通过。
- 完整 Linux CTest：首轮 1201/1208，失败 7 项为预期更新（编辑器类型数 13→14、默认布局 JSON 金样含新增“工作流”按钮），
  更新后只重跑这 7 项通过。默认屏幕 PNG 金样的可见部分不变，未更新。
- 复查后补丁：进入后、读取前关闭项目时丢弃待读请求与面包屑（新增第 6 项测试：之后新建的项目不收到旧请求；去掉修复时该测试失败，
  `analyses.get` 多 1 次）；Windows 也运行的测试夹具改用本机路径分隔符。完整 Linux CTest 重新全量运行 **1209/1209**。

## 2026-10-07：P3 W3a 项目工作流存储与校验

- 新增 `tests/test_project_workflows.py` 20 项：往返保留 `x-` 键与 `ui` 内容、更新/撤销/冲突/重复 UUID/不存在；
  13 种不合规形状被拒绝且不改修订；示例式工作流校验通过并给出名称、端口、内容哈希且不改项目；
  19 种问题代码各自定位到步骤与路径（含环、单位、类型、模板案例表、动态绑定）；受管表格不能作参数表、同一分析只解码一次；
  问题上限；后台服务方法、`script.catalog`、`project.changed`、`not_found`/`conflict` 与协议无违规。
  示例项目测试新增“温度扫描”工作流校验通过。保存分析相关 167 项在抽出 `managed.py` 后不改通过。
- 完整 pytest（`-m "not perf"`）：**2234 passed、1 failed、24 skipped**。失败的是控制台操作清单测试（按设计固定全部
  `project.*` 操作，需加入 5 个新方法），更新后单独通过；之后新增的“受管表格/只解码一次”1 项与相关 168 项一起通过。
  重新编译（桥 schema 变更）后完整 Linux CTest **1187/1187**。
- CI：W3 方案文档 `e574368`、`63d10ab` 的 Runtime、Secret scan、Cloudflare Pages 均通过（只改文档，不触发 desktop）。
  W3a `20ae610`：desktop（27 分 59 秒）、Runtime、Secret scan、Cloudflare Pages 全部通过。

## 2026-10-06：P3 工作流编辑 W1c/W2

- CI：W2 `94cf5ee` 的 desktop（21 分 57 秒）、Runtime and scientific workflow checks、Secret scan、Cloudflare Pages 全部通过；
  `c3a71dc`（W1b）与 `22c83ab`（W1c）的 desktop 运行被随后推送按并发规则取消，其余三项通过，桌面覆盖由 `94cf5ee` 的通过运行代表。
- W1c（`22c83ab`）：等值面节点缺 `field` 时表单下即时提示 `missing_param`，填写后校验通过并只保存该参数；
  新增“编辑图结构”中英文宽/窄 GL/Vulkan 截图 8 张并检查（据此修正改动清单、节点重叠与提示文字）。完整 CTest **1185/1185**。
- W2：真实窗口鼠标事件拖动 `axes` 120 像素后无需校验即可保存，位置与画布换算一致；从 `component.out` 拖到 `box.in`
  后保存需校验，保存结果为该连线。画布单元测试覆盖保留视图、端口命中、拖线预览与节点移动。完整 Linux CTest **1187/1187**。

## 2026-10-06：P3 工作流编辑 W1a/W1b

- 模型（W1a，`5dc88a3`）：候选图测试 5 项（ID 生成与冲突、未改动时与保存图逐字节一致、删除级联、列表输入、
  参数/位置/图输出、节点上限与过期代次），原草稿测试 34 项不改通过；完整 Linux CTest **1172/1172**。
- 编辑器（W1b）：真实后台服务与节点目录下的交互 4 项——新增切片节点后选中、显示候选、未校验不能保存，
  未连接必需输入时校验失败，连接后校验通过并保存，所有节点位置写入定义；删除 `png` 与 `bar` 后图输出 `image`、
  请求输出与 `scene.layers` 中的条目一并删除；`scene.layers` 下移后顺序改变、放弃后回到已保存图；撤回并重新公开
  `png.image` 后保存为 `png_image`。全部用例不求值、不准备运行、不改 Viewer。连线中英文宽/窄截图检查候选画布。
  完整 Linux CTest **1176/1176**。

## 2026-10-06：示例项目、无头 stk 与文档站

- Secret scan：`96c630b` 的推送（含 `42189fa`）被 gitleaks `generic-api-key` 标记——原生 AI 密钥测试中的占位字符串
  （编造的、从未作为凭据使用）。测试改为低熵占位串，并在 `.gitleaks.toml` 中只对该提交的该文件加白名单；
  本机 gitleaks 8.30.1 重新扫描 `7e64ece..HEAD` 无发现。其余文档与归档文件中的既有匹配不在本轮提交范围内。
- CI：`3fd0c17`（可用性开发包的最终累积状态，含 `42189fa`、`96c630b`、`d8f9133`、`406c042`）
  [桌面 5/5 任务成功](https://github.com/sijintech/stk/actions/runs/37510938774)（Linux GL+Vulkan、macOS Metal、Windows CPU、
  Linux 包与全新系统冒烟），Runtime CI、Secret scan 与文档站部署均成功；`7e64ece` 桌面 5/5 成功。
  `96c630b`、`d8f9133`、`406c042` 的桌面运行被后续推送取消，由 `3fd0c17` 覆盖；`d8f9133` 起文档站在 CI（Node 22）构建并部署成功。

- Python：无头会话 2 项（目录与桌面一致、扫描与提交、桌面操作 `unavailable`、同目录 `busy` 提示、关闭后拒绝与重开、
  `python -m` 控制台）；示例项目 3 项（扫描生成的 300/325/350 K、结果引用、指标、README、本机分析运行成功、
  非空目录拒绝、`suan demo` 输出、后台服务 `demo.create` 与无协议违规）。完整 `pytest -m "not perf"` **2216 passed / 24 环境跳过**。
- 原生：工作台“创建示例项目” 1 项（按钮在创建期间禁用、完成后打开项目且两表共 6 行、位置在 `STK_PROJECTS_DIR`、
  打开项目后按钮消失）。完整 Linux CTest **1167/1167**。
- 文档站：在临时副本中 `pnpm install --frozen-lockfile` 与 `pnpm run build` 通过（本机 Node 24 高于 `engines` 声明，仅警告），
  生成 `/quickstart/`、`/en/quickstart/` 与 Pagefind 索引。

## 2026-10-06：收起内部细节与一行说明

- 完整 Linux CTest **1166/1166**（含折叠 JSON 编辑器后更新的 7 处交互测试）；分析运行相关定向 **131/131**。
- 截图检查：修改检查（中文，行号定位与 `#除以零`、折叠的技术详情）、仿真批次（行号与运行环境名称、一行说明）、
  分析运行结果窄窗口（技术详情面板含 UUID 与哈希）。

## 2026-10-06：术语统一与界面内 API 密钥

- Python：`test_token_plan_credentials.py` **3/3**（本次/记住/环境变量优先级、0600 文件、选择不记住即删除旧文件、
  无状态目录不能记住、错误不回显输入、repr 与回复不含密钥、适配器只用注入的来源、桥设置与清除）；
  请求与适配器相关测试按新增字段更新。完整 `pytest -m "not perf"` **2211 passed / 24 环境跳过**（修正 2 项字段断言后）。
- 原生：AI 助手密钥交互 1 项（未设置时面板展开；本次密钥后输入框清空且无文件；记住后文件权限 0600；忘记后文件删除；
  后台服务日志、程序日志与回复中均无密钥）。所有测试密钥均为占位字符串，未发送任何模型请求。
- 布局金样 12 项与默认画面 PNG 因文案更新；完整 Linux CTest **1166/1166**。
- 桌面 CI：`ed5bb29`（扫描、浏览、运行所选行的累积状态）[5/5 任务成功](https://github.com/sijintech/stk/actions/runs/37499461952)。

## 2026-10-06：分析“运行并显示”

- 原生交互 3 项（真实桥与存储，故障注入只在回复投递处）：一次点击恰好各调用一次准备、开始、读取结果，Viewer 显示归档 payload
  且未重新求值；图失败的运行停在“失败”，不读取结果、不改 Viewer；准备回复丢失时停在“结果不明”且不开始，
  核对后再次点击、在状态读取被扣住时“停止”，之后既不读取结果也不取消运行。
- 分析运行相关定向（含 8 张准备/结果截图）**131/131**，中文窄窗口截图检查按钮与说明位置。完整 Linux CTest **1165/1165**。
- 桌面 CI：`1d1c338`（工作台）[5/5 任务成功](https://github.com/sijintech/stk/actions/runs/37492559252)；
  `ca8a8b3`、`b1badce` 的桌面运行被后续推送取消（Runtime CI、文档部署、Secret scan 均成功），由包含它们的 `ed5bb29` 覆盖。

## 2026-10-06：运行环境选择与“运行所选行”

- Python（隔离的 Linux Runtime 与假 SDK）：`stk.batches.run` 修订过期时不写入；一行准备失败时只提交其余两行，
  失败原因留在成员结果；修复后再次运行复用同一批次并只新增该行任务（共 3 个），三个任务均成功。完整 `pytest -m "not perf"` **2208 passed / 24 环境跳过**。
- 原生（真实测试 Runtime）：未选运行环境时按钮禁用；面板下拉框选中后成为当前连接，按钮显示“Run 3 selected rows on run-test”；
  切到 Slurm 需要时限、切回后时限字段消失；线程字段写入选项对象；一次点击提交 3 个任务，再次点击仍为 3 个；
  原有批次逐步按钮回归通过。批次与仿真截图中英文检查。完整 Linux CTest **1162/1162**。

## 2026-10-06：路径框“浏览…”

- 原生交互 1 项（手动作答的对话框替身）：无系统对话框时不显示按钮；项目目录选择文件夹且不打开/新建项目；
  对话框失败时路径不变；CSV 输入只取第一个文件、导出建议 `Cases.csv`；项目文件多选追加；MuFerro 案例目录；
  切换项目后到达的回答被丢弃；Python 文件只填路径不执行。全程项目修订不变。
- CSV 截图中英文两种后端检查按钮布局。完整 Linux CTest **1161/1161**。

## 2026-10-06：参数扫描生成

本机 Linux（未调用模型，未准备或提交运行）：

- Python `test_project_sweep.py` **6/6**：范围/步长/列表与类型检查、全部组合与配对、行数与 1000 条命令上限（333 行可、334 行拒绝）、
  托管表拒绝、基准行复制（行内公式改指新行并求值为 T+10，引用保持原目标）与一次撤销、桥计划只读后经 `project.apply` 提交、
  控制台 `dry_run` 与修订冲突、CLI 按名称。完整 `pytest -m "not perf"` **2207 passed / 24 环境跳过**。
- 原生：输入解析纯函数 1 项；面板交互 1 项（默认字段、范围与列表、整数列表拒绝小数、重复字段与配对长度不等在提交前禁用、
  每次编辑命令上限随复制选项变化、一次提交 6 行并选中首行、复制公式绑定指向各新行、撤销；计划期间他处写入时不写任何行）。
  新增 4 张中英文 GL/Vulkan 截图并逐张检查。完整 Linux CTest **1160/1160**；其后加入重复字段检查，相关定向 **74/74**。

## 2026-10-06：启动即工作台

- 新增交互 2 项：默认布局以工作台开始并标出“1. 项目 · 下一步”，“选择运行环境”复用同组任务标签、“查看器”不最大化；
  打开项目后下一步为参数，加入参数行后变为运行环境（测试环境无 Runtime）。工作台导航回归共 **11/11**。
- 默认布局变化首轮使 33 项失败（预期）；修正测试与金样后完整 Linux CTest **1154** 项中仅属性表单金样 2 项因面板变高失败，
  核对确认只有主区高度改变后更新金样。默认屏幕图像（英文 1x、中文 1.5x）两种后端均与新金样匹配。
- 截图检查：默认启动画面中英文、工作台宽/窄（无项目与已打开项目）。

## 2026-10-06：带符号标量体以 0 为中心与自动值域显示

- Python：`test_scalar_volume.py` **70/70**（新增默认对称、显式端点优先、`data` 模式、全正数据、未设置 `range_mode` 的旧图保持数据范围；
  原精度/编码用例显式使用 `data` 保留原意）；相关套件 137 + 164 项通过；完整 `pytest -m "not perf"` **2201 passed / 24 环境跳过**。
- 原生：表单单元新增“自动端点显示解析值、无结果时不显示数字、显示不写回参数”；标量体交互与 8 张截图更新为 ±66；
  属性表单金样仅变化于自动端点控件与新增“自动值域”一行（已逐项核对）。首轮完整 CTest 1152 项中 3 项因上述预期变化失败，修正后定向 **54/54** 通过。
- 截图检查：中英文宽/窄标量体页显示“最小 -66 / 最大 66”与以 0 为中心的色标。

## 2026-10-06：保存分析的单输入连线编辑

本机 Linux 验证（未调用模型，未运行任何节点）：

- 连线草稿与校验绑定单元测试 **5 项**（与原草稿测试合计 34/34）：只改目标输入且其余字节不变、断开/新接只增删该键、
  多输入/别名/额外字段/重复 ID/非法来源/自连拒绝且不改版本、与参数/输出共同组成候选并随复原/重新固定清空、
  校验票据与键（句柄、UUID、会话、修订、代次、版本）任一不同即不计入。
- 交互回归 **7/7**：校验通过后一次 CAS 保存只改 `box.in` 并可撤销回原文档；`port_mismatch` 与 `cycle` 报告后保存保持禁用；
  通过后再编辑、迟到回复（桥端扣住后再改候选）、外部修订均使旧结果失效；`scene.layers` 只读、`scene.camera` 可断开并保存、
  `volume.in` 无断开项；未知类型只读；无效参数原文 `1e` 保留且暂停连线与校验；保存回复丢失时按 UUID 读回采用，只发送一次更新。
  全部用例结束时确认没有 `graph.evaluate`、运行准备/开始或 Viewer 求值。
- 新增 **8 张** GL/Vulkan 中英文宽/窄连线截图并逐张检查四种组合；夹具同时核对保存后只有一条连线改变、未准备运行。
- 旧的保存分析截图夹具因新增面板标题首轮 8 项失败，修正后与 8 张新图一起通过（见开发日志）。
- 定向回归 **175/175**；完整 Linux CTest **1151/1151**，JUnit 0 失败、0 跳过；中英文目录各 **1446** 项校验通过。
  日志 `/tmp/claude-1000/-home-mnemora-xcheng-sijin-stk/07437944-4ce3-4414-bbc7-e80a0698ca9c/scratchpad/links-{focused,full2}.{log,xml}`。

`3cbaa36` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/37459650536) **5/5 任务成功**：Linux **1151/1151**（必跑 502）、macOS CPU **770** / Metal **146**（必跑 484，含 Metal 连线与保存分析截图）、Windows CPU **729/729**（必跑 478）；[Runtime CI](https://github.com/sijintech/stk/actions/runs/37459650588) **7/7**，文档部署与 Secret scan 成功。macOS/Windows 真机按[工作台验收清单](workbench-acceptance.md#保存分析的单输入连线)复核，未做真机检查。

## 2026-10-05：原生技能目录浏览页

新增原生 `skills` 编辑器与共享只读状态；工作台“技能库”和文件菜单无需项目即可进入。本机 Linux：

- 新增原生回归 **9/9**：行解析与本地化回退、无桥不发请求、列表/选择/详情（整数默认值保持整数，重复绘制不重发）、
  搜索与两次并发请求只采用后者、UTF-8 安全截断、真实桥重启后清空选择并按原查询重读、
  其他桥的当前回复被丢弃后重新读取、旧桥显示不可用、坏定义与缺模块的“部分可用”说明、工作台无项目打开技能库。
  拆除修复的反证：“其他桥回复”用例在 30 秒等待处失败（页面停留在读取中）；恢复后通过。
- 新增 **8 项** GL/Vulkan 中英文宽/窄截图（`project_skills*`）均通过，并逐张检查四种组合的内容、可达控件与中文标点。
- 定向回归（技能、工作台、聚焦导航、Python 控制台、桥）**95/95**，必跑检查 61 项全部实际运行。
- 完整 Linux CTest **1131/1131** 通过，JUnit 中 0 失败、0 跳过；中英文目录各 **1422** 项校验通过。
  日志 `/tmp/claude-1000/-home-mnemora-xcheng-sijin-stk/07437944-4ce3-4414-bbc7-e80a0698ca9c/scratchpad/skills-{focused,full}.{log,xml}`。

契约提交 `5a12d5a` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/37354729828) 成功，
[Runtime CI](https://github.com/sijintech/stk/actions/runs/37354729736) 的两个 Windows 客户端任务因测试假定 VTK 已安装而失败（1 项），
其余任务成功；`526608a` 修正测试期望后 [Runtime CI](https://github.com/sijintech/stk/actions/runs/37357825198) **7/7** 成功
（Linux 3.10/3.12 各 2214 passed，Windows 客户端 3.10/3.12 各 1800 passed）。

浏览页提交 `df4729d` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/37358644895) **7/7** 成功；
[桌面 CI](https://github.com/sijintech/stk/actions/runs/37358644803) Linux **1131/1131**、macOS CPU **758/758** / Metal **142/142**
（含 Metal 中英文技能截图）通过，Windows CPU **716/717**：`ListsSelectsAndShowsTheContractWithoutRunningAnything`
在两帧重建控件后仍通过旧指针设置列表选择，Linux 上偶然可用，属未定义行为。修正为帧后重新查找控件，本机 9 项重复 3 次通过；
修正提交 `08de943` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/37362435293) **7/7** 成功，
[桌面 CI](https://github.com/sijintech/stk/actions/runs/37362435377) Linux **1131/1131**、macOS CPU **758** / Metal **142** 通过；
Windows CPU 任务首次及重跑均在编译阶段因 “The hosted runner lost communication with the server” 中断，与同时段
GitHub Actions 状态页的事件吻合，当时未执行任何测试。事件结束后第三次重跑
[Windows CPU](https://github.com/sijintech/stk/actions/runs/37362435377/job/112242323951) **717/717** 通过（必跑 466 项实际运行），
技能目录首版至此三平台 CI 全部通过。
macOS/Windows 原生页面仅由 CI 覆盖，未做真机检查。

## 2026-10-05：技能目录契约与查询入口

新增实验契约 `stk.skill/1` 与三个内置技能，桥 `skills.list/get`、Python `stk.skills`、`suan skills catalog/show`。
本机 Linux（`/home/mnemora/opt/stk-venv`，Python 3.12）验证：

- `tests/test_skill_catalog.py` **13/13** 通过：内置定义双语且与锁文件一致；哈希覆盖定义与模板、不受格式影响；
  18 类坏定义逐项给出代码与 JSON 指针而不隐藏有效技能；跨来源重复、未知 ID/版本、参数越界；
  缺少 matplotlib/VTK/numpy 或节点类型时的 `limited`/`unavailable`；分页与中英文查询；严格 schema 下的桥方法
  （确认未启动图工作进程、未打开项目）；控制台与 CLI。
- 依赖范围以实际求值核对：子进程屏蔽模块后 `scalar-volume` 的 `view` 无 VTK 可交付、无 numpy 失败；
  `muferro-domains` 的 `fractions/families` 无 VTK 可交付，`view` 失败；两个能量 `energy` 输出无 matplotlib 失败，`table` 可交付。
- 邻近套件（说明包、桥、图预设、控制台图与导航）**81 passed, 1 skipped**（性能基准）。
- 完整 `pytest -m "not perf"`：**2199 passed, 24 skipped, 0 failed**；跳过均为既有环境原因
  （性能基准、PySide6、本机离屏渲染 SIGSEGV、MCP 可选依赖、未配置真实 MuFerro）。
  日志 `/tmp/claude-1000/-home-mnemora-xcheng-sijin-stk/07437944-4ce3-4414-bbc7-e80a0698ca9c/scratchpad/pytest-full-A.log`。

PNG `image` 输出需要离屏 OpenGL；本机离屏子进程 SIGSEGV，目录据此只声明、不探测该能力。原生浏览页的验证见后续记录。

## 2026-10-05：项目工作台与跨页草稿保护

新增原生 `workspace` 编辑器，从文件菜单和项目/AI/分析图页头进入；显示当前项目并定位对话、文件、
保存的分析、分析运行、仿真运行、项目表格和项目管理。复用已有编辑器，默认布局和项目数据库格式不变。
技能目录、全局侧栏、对象附件与完整工作区模式尚未实现，更新后的产品分类和交付顺序见开发计划。

本轮 critical review 重点检查导航的副作用、编辑器寿命及共享选择：

- 回调固定项目打开句柄、来源编辑器和应用壳寿命；关闭/重开、切项目、换标签、销毁编辑器/窗口后拒绝旧动作。
  还覆盖外壳先销毁、无头屏幕后销毁的情况；不能只保护来源编辑器。
- 任一窗口有活动文本输入时暂停项目导航。往返保留未发送问题、已接受的分析参数草稿和无效原文 `1e`；
  再次明确修正、保存才修改定义，导航本身不创建或开始分析运行，不改项目修订或现有 Viewer 载荷、来源和相机。
- 审查发现“文件”入口会隐式选择文件索引表，可能触发单元格编辑器重新载入。新增回归在修复前确认：
  隐藏标签存在未应用单元格编辑时，文件入口仍改变了选择和布局。
  修正为切表前检查所有窗口的全部标签；有当前项目单元格及表/字段名称草稿时保留原状态并提示应用或重新载入。
  回归分别验证隐藏标签、另一窗口仍有草稿、未保存表名，以及明确重新载入后能够继续导航。
  关闭新保护进行反证的日志为 `/tmp/stk-workspace-cell-red.{log,xml}`；保护范围为此工作台入口，不扩大为所有既有手工切表操作的承诺。

首轮新增交互测试有三个夹具问题：错误的侧栏控件名（其中一处未判空而崩溃）及第二窗口鼠标坐标未转换。
单元格夹具最初遗漏 `set_cell.table_id`，创建参数表失败后误用文件表，已补齐前置成功和选择身份断言；该次结果不作为修复证据。
修正控件身份、判空和坐标后新增交互 **9/9** 通过；加强现有 Viewer 保留断言后，首轮完整套件 **1113/1113** 通过，
无失败、错误或跳过。上述单元格保护是随后审查发现的遗漏，最终结果另列，不能沿用首轮结论。
新增八张中英文宽/窄 GL/Vulkan 工作台截图全部检查；另外复查 AI 和分析图窄窗口页头，入口和原控件均可见。
CI 为新交互和 Linux GL/Vulkan、macOS Metal 工作台截图增加必跑检查；本机测试未调用真实模型。

最终完整编译成功，重点回归 **61/61**、完整 Linux CTest **1114/1114** 通过，失败/错误/跳过均为 0。
其中新增 **10 项交互 + 8 项 GL/Vulkan 渲染**全部通过必跑检查；中英文目录各 **1380** 项校验通过，
工作流 YAML 与六份文档的 **214 个本地链接**有效。证据 `/tmp/stk-workspace-build-reviewed.log`、
`/tmp/stk-workspace-test-reviewed-build.log`、`/tmp/stk-workspace-focused-final.{log,xml}`、
`/tmp/stk-workspace-full-final.{log,xml}`、`/tmp/stk-workspace-required-final.log`。
交接时已核对功能提交 `b2e5632` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/37289712961) **5/5 任务成功**：
Linux **1114/1114**、macOS CPU **749/749** / Metal **138/138**、Windows CPU **708/708** 通过，无原生跳过；
新增 10 项交互在三个平台均通过，两个 Weston 应用窗口用例本次通过。Linux/macOS 打包与干净环境检查通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/37289713009) **7/7 任务成功**；文档部署与 Secret scan 也成功。
直接日志保存在 `/tmp/stk-handoff-b2e5632-{linux,macos,windows}.log`；本次交接未另行逐张检查 macOS CI 截图。
真机交互仍按平台验收清单跟进，不能由 Windows CPU CI 替代 GPU/IME 或真实模型按钮验收。

### 旧 Wayland 退出故障的后续证据

上一提交 `17ea194` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36737424773) 成功，
[桌面 CI](https://github.com/sijintech/stk/actions/runs/36737424406) 为 **4/5 任务通过**。
Linux **1095/1096**，唯一失败为 `wm_app_window_weston_csd`，新包装层明确记录子进程以 **SIGSEGV (11)** 退出，
故障发生在窗口检查和布局重载输出之后；macOS、Windows 与两个 Linux 打包任务通过。
本轮修改前，本机同一 CSD 用例连续 **30 次**通过，未复现该退出故障。根因仍未确定，本次项目导航不声称修复它。
证据 `/tmp/stk-project-navigation-baseline-linux.log`、`/tmp/stk-workspace-baseline-weston.log`。
这与上述新测试因错误控件名导致的判空缺失是两份独立失败记录。

## 2026-09-30：Python 文件入口联合验收与输入映射的 Tab 提交修正

新增原生集成测试，从 Python 编辑器选入脚本、明确展开文件面板，再通过可见“运行文件”按钮的真实鼠标点击，
执行离线示例的 `create_demo()`。测试指定独立临时目录，未执行示例 `__main__` 的默认主目录路径。
选入文件及展开面板不执行脚本；明确运行后只准备、启动和读取一次分析结果，保留原项目快照、历史、
Viewer 载荷/来源和布局；示例调用审计未出现 UI、Runtime、独立 `graph.*` 或模型接口。

随后通过明确的项目打开动作进入新项目，按持久项目、分析和运行身份加载归档，再明确读取结果和打开表格。
核对源坐标 0/1 的合成温差 **-9.5 K**，以及末尾 72/9 的 `sample_7` 整数 **576**；
原 Viewer 保持不变，项目修订仍为 3，仅有一次分析运行，没有 Runtime 任务或模型请求。
桌面工作流的 pull request 与 push 路径过滤均加入 `examples/project_analysis/**`，避免示例修改漏跑此验收。

首轮夹具错误地假定拖入文件会展开先前关闭的面板，因找不到运行按钮失败；现先真实点击面板标题、核对所选路径，
再滚动并点击运行按钮，没有改变生产界面行为。最终 `ScriptPython` **26/26 通过**，失败/错误/跳过均为 0，
包含该新增联合测试；证据为 `/tmp/stk-analysis-handoff-script-final.xml` 与同名日志。
该脚本验收及 CI 触发路径本身没有修改生产代码。随后跨模块 critical review 发现输入映射表单的实际缺陷：
“绑定名”和“相对路径”共用提交版本，Tab 在同一帧提交前者并进入后者，后者捕获的旧回调随后拒绝新路径。
真实键盘回归先在原实现复现：输入 `nested/typed-input.dat` 后，提交文字和 Add 后的映射仍为 `input.dat`，
证据 `/tmp/stk-input-binding-tab-red.xml` 与同名日志。

修复分别跟踪两个字段的提交版本；每次文字提交仍使旧 Add/Prepare/Clear/复用动作失效。
清空、采纳复用、快照/文件选择和映射增删等结构变化同时使两个字段的旧回调失效，项目/会话/导航检查保留。
回归覆盖真实 Tab→Enter→首次 Add、同字段旧回调、Add 后旧回调和文件选择往返，
同时核对原快照/文件身份、未修改的冻结运行，以及保留有效参数值与无效原始文字、禁止隐式准备/执行。
本次修复与测试已通过独立审查。最终全量编译成功，相关交互重点 **88/88**、完整 Linux CTest **1095/1095** 通过，
失败/错误/跳过均为 0；完整套件包含上述原生脚本链路、Tab 回归及既有 GL/Vulkan 渲染。
证据为 `/tmp/stk-analysis-handoff-full-build-final.log`、`/tmp/stk-analysis-handoff-focused-green.*`、
`/tmp/stk-analysis-handoff-full-final.*`。十份交接/指南/设计文档的 **233 个本地文件链接**有效。
提交 `c6b6d14` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36731162900) **7/7 任务通过**：
Linux Python 3.10/3.12 各 **2201 passed / 7 skipped / 4 deselected**，Windows 两版本各
**1788 passed / 61 skipped / 260 deselected**；14 项离线示例在四个组合均通过，控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。
[桌面 CI 首次执行](https://github.com/sijintech/stk/actions/runs/36731162962/attempts/1) **4/5 任务通过**：
macOS CPU **739/739**、Metal **134/134**、Windows CPU **698/698**，两项新增用例在三个平台均通过。
Linux **1094/1095**，唯一失败为旧 `wm_app_window_weston`：全部检查包括零 guardedalloc 泄漏已输出，
但最终 `PASS` 行缺失，CTest 报 required regular expression not found；现有包装层未记录子进程退出码。
无原生跳过；Linux/macOS 打包和全新目录启动、载荷及实际预设检查通过，macOS ad-hoc 签名校验通过。
证据 `/tmp/stk-final-handoff-ci/audit-summary.json` 与 `attempt1` 中的原始日志/元数据。
同提交本机 `--repeat until-fail:20` 全部通过；仅重跑远端失败任务一次以检查偶发性，不将重跑当作已修复根因。
[同提交第二次执行](https://github.com/sijintech/stk/actions/runs/36731162962/attempts/2)的 Linux 任务已成功，
直接日志确认 **1095/1095** 通过，原 `wm_app_window_weston` 为 **1.13 秒**，两个新增用例也通过；
其他四个任务沿用首次执行的成功结果，没有全部重跑。证据单独保存在 `/tmp/stk-final-handoff-ci/attempt2`，
首次失败记录仍保留；相同提交的一次成功重跑不能定位或证明修复了原始退出问题。

## 2026-09-30：显示服务器包装层的退出诊断

上述失败的具体信号/退出原因仍未知，不能把正常窗口清理与零内存块当作整个进程正常退出。
独立审查确认 CTest 的 `PASS_REGULAR_EXPRESSION` 会忽略普通退出码，包装脚本将子进程信号转换成普通退出后可能丢失失败判据。
修正包装层：0/77 只报告状态，非零退出、信号（含无枚举名称的实时信号）与超时打印明确 `FAIL:`，保留原子进程状态；
不提前刷新原冒烟测试最终 `PASS`，不增加跳过或放宽通过条件。两个 Viewer GUI-open 用例同步增加 `FAIL` 匹配。
CI 另外归档 `LastTest.log` 与显示服务器日志，方便后续区分正常退出、信号和服务器故障。

新增六个真实子进程回归，覆盖成功且不伪造 `PASS`、跳过 77、已输出 `PASS` 后退出 3、命名/无名信号、超时。
审查移除超时场景对 Python 在 0.5 秒内完成启动的假设；信号用例同时检查包装进程的精确 POSIX 退出码。
此补丁仅改进故障可观察性和测试判据，没有修改桌面产品行为，也不声称已修复原始 Weston 偶发故障。
构建成功后，完整 Linux CTest **1096/1096 通过**，失败/错误/跳过均为 0，其中包装层用例实际执行上述六个子进程场景。
随后补齐 Viewer 的一行失败匹配并重新生成、构建，最终显示包装层、X11/Wayland 窗口和 Viewer GUI-open 定向
**10/10 通过、无跳过**；没有因仅此测试属性变化重复整个套件。
证据 `/tmp/stk-display-exit-build.log`、`/tmp/stk-display-exit-full.{log,xml}`、
`/tmp/stk-display-exit-build-final.log`、`/tmp/stk-display-exit-focused-final.{log,xml}`。
此收尾补丁的远端 CI 结果需另行记录，不沿用 `c6b6d14` 的结论。

## 2026-09-30：源坐标定位与窄侧栏完整滚动

内联结果表格增加“源行 / 源列 → 跳转到单元格”：输入零起始十进制索引并按回车提交，再明确定位。
页面从目标原始坐标开始，保留 64×8 上限并选择首个单元格；没有排序、舍入或跨表推断。
全部坐标检查先于页面修改；格式、溢出和越界错误保留原页面、选择与输入。

关键节点 critical review 检查实际输入链和滚动可达性：

- 数字控件原本支持表达式、舍入和限幅，不适合严格源坐标。这里使用有界文字输入和整数解析，
  不经 double 转换；明确跳转仍核对结果、运行、项目、页面与导航身份，并保护全部窗口的活动输入。
- Tab 可在同一帧提交行字段并进入列字段，若两个字段共用浏览版本，后一个有效提交可能被旧版本误拒绝。
  采用每字段提交版本，页面/结果等身份仍固定；每次提交继续使旧“跳转”动作失效。另一窗口编辑时可保留本地输入，
  但不能执行导航；无效或未保存的分析参数保持原样。
- 截图延伸复查发现侧栏滚动先按全宽文字高度限位，再为滚动条缩窄文本；新增换行未计入最大滚动范围，
  部分底部控件实际不可达。新 CPU 回归先在旧实现上复现：1× / 1.5× / 2× 的末尾按钮分别超出 12 / 18 / 24 像素，
  真正鼠标点击也失败。修正为先按最终可用宽度测量，再限制滚动位置；同时覆盖反复重绘、窗口变宽和内容变短。

初轮重点 **191/191 通过**；随后截图确认英文窄窗口的两个并排坐标标签都被截为 `Sourc…`，
已改为上下两行完整标签，并增加空表禁用入口断言。最终完整 Linux CTest **1093/1093 通过**，
失败/错误/跳过均为 0，包含全部六项新定位交互和一项新滚动回归。
实际键盘测试覆盖行字段→Tab→列字段→Enter 后首次跳转成功、末尾/零坐标、相对翻页、非法格式与溢出，
以及另一窗口输入、旧字段回调、旧结果、销毁和未保存参数保护。

最终 **8 张**定位截图及受影响的 **24 张**已有归档/运行截图复核完整标签、源身份、精确值和底部操作。
EN/ZH 各 **1362 条消息**一致，八份指南 **201 个本地链接**有效；`Region.*` 纳入三平台必跑检查。
本轮无 Python、协议、项目格式和真实模型调用变化。日志与 XML：`/tmp/stk-region-wrap-before.*`、
`/tmp/stk-region-wrap-fixed-ui.*`、`/tmp/stk-table-jump-focused-first.*`、`/tmp/stk-table-jump-full-final.*`。

完整 **1093/1093** 验证完成后，M15 Linux CI 暴露旧“不确定保存”测试的事件时序假设：
畸形保存回复已完成，不代表独立的 `project.changed` 通知及修订刷新已经完成。
本轮仅修改该测试夹具，以文件握手明确暂扣通知，先断言原修订 0，再放行并等待精确修订 1 与空闲状态。
没有主动刷新掩盖事件链，也没有放宽原 UUID、一次创建、一次明确读取和一条历史记录的断言。
畸形回复与丢失回复两项定向复测 **2/2 通过**，证据为 `/tmp/stk-analysis-handoff-focused-final.log`；
同批尚在开发的 M17 脚本入口测试因文件面板尚未展开而找不到按钮，不属于本次 M16 提交，也未计入这两项通过结果。
M16 提交前的最终测试夹具修改后未重复完整套件；其后提交 `86007e3` 的
[桌面 CI](https://github.com/sijintech/stk/actions/runs/36728057610) **5/5 任务通过**：Linux **1093/1093**、
macOS CPU **737/737** 与 Metal **134/134**、Windows CPU **696/696**，失败/错误/跳过均为 0。
全部 **7 项新 CPU** 及畸形/丢失回复修复场景在三平台实际通过；**12 张**更新的 GL/Vulkan/Metal 图逐张复查。
Linux 全新目录 GL/Vulkan 包冒烟、macOS 签名校验及全新应用/载荷/预设 Metal 冒烟通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36728057735) **7/7 任务通过**：两个 Linux Python 版本各
**2201 passed / 7 skipped / 4 deselected**，两个 Windows 版本各 **1788 passed / 61 skipped / 260 deselected**；
14 项离线示例在四个组合均通过，控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。
证据 `/tmp/stk-table-jump-ci-36728057610/audit-summary.json`；M15 的失败历史保留，修复结论来自本次实际执行。

## 2026-09-30：内联科学结果表格

归档输出增加明确的“表格视图”入口：按归档列顺序和源行顺序浏览最多 64 行、8 列的页面，行列分别翻页。
选中行与当前页的一列后，可核对原始行身份、完整列名、单位、实际 JSON 类型和精确值；复合单元格可继续打开属性。
网格复用已核对的不可变结果，不读取额外文件或改变定义、草稿、Viewer 和运行状态。

关键节点 critical review 覆盖列次序、科学数据精度、结构错误、页面身份、计算开销与异步寿命：

- 归档明确提供 `column_names`，JSON 对象次序不代表科学列序。适配器按该数组逐列核对唯一身份、完整列集合、
  数组形状和相同行数；错误结构仍可检查原始属性，不能静默补空值或丢列。
- 表格可能包含向量、对象或混合类型。网格不推断整列 dtype、不展平向量、不把 `"NaN"` 等字符串转换为浮点数，
  缺省单位与明确的单位文本分开保留。当前保持源顺序，避免通用字符串或 double 排序改变科学含义。
- 审查发现有界归档仍可能包含数万空列；逐列查找 `ordered_json` 会形成平方级构造开销。
  改为一次建立借用索引，并仅对可见/选中的单位生成预览。每页只生成最多 512 个单元格摘要，
  不复制完整列数组，也不为每个单元格重复长路径；完整路径只在明确选择时生成。
- 延伸审查发现共享 Python JSON 编码器同样会按键重复查找对象。改为收集键和值的借用指针对并排序，
  保持原有键值对应、源/排序次序、紧凑/带空格格式与规范编码语义；两万列和独立嵌套类型样例验证输出字节。
  此优化同时覆盖归档的精确哈希编码，不改变结果、缓存或图哈希格式。
- 行与列采用绝对源坐标，切换任一页清空单元格选择。页面、结果、导航及浏览版本使旧排序缓存和控件回调失效；
  全部窗口的活动文字输入仍受保护。长列名、单位与标量分别缓存和分页，不在每帧重新序列化。

重点回归 **183/183 通过**：新增适配器 **15 项**、真实桥界面 **12 项**、共享 JSON 编码器 **2 项**、
GL/Vulkan 中英文宽窄表格渲染 **8 项**，以及已有归档、运行、输入复用、冻结图、参数/输出和编码规范回归。
首次编译发现同一源码行的两个 GoogleTest 异常断言产生重名标签，拆成独立行后完整编译通过。
完整 Linux CTest **1086/1086，失败/错误/跳过均为 0**。

截图审查发现“控件存在”不能证明窄窗口中精确值可见；英文窄布局的详情位于初始视口下方。
渲染夹具改为通过真实滚轮滚动侧栏，并断言精确值及“在属性中打开单元格”的矩形完整处于视口，
随后 **8/8 渲染复测通过**。这次只加强测试，没有改变生产滚动行为；完整回归结果对应此前相同的生产代码。
最终新增 **8 张**与受影响的已有归档/结果 **24 张**，共 **32 张**图片逐张复核，未发现阻断问题。
窄区域需纵向滚动到详情，后置表列仍可横向滚动；没有把初始视口当作全部内容。
EN/ZH 各 **1357 条消息**一致，六份指南 **127 个本地链接**有效；新增 CPU 与 GL/Vulkan/Metal 渲染已加入 CI 必跑检查。

新增[离线分析示例](../examples/project_analysis/README.md)以公共 Python API 创建全新目录和 73×10 合成 CSV，
冻结快照、保存定义，记录身份后明确启动一次本机分析。保持已有项目、布局与 Viewer；超时仅结束观察，
不自动取消、重试或切换项目。示例专项 **14/14 通过、无跳过**，包括真实隔离内核→桥→工作进程、
独立归档哈希、全部列值/类型/单位、已存在路径与悬空链接拒绝、能力检测和观察边界。
审查发现目的地提前 resolve 可能绕过悬空链接，已改为先独占创建指定目录，并保留回归。
这是软件验收示例，不是物理模拟，没有真实模型调用，也不改变生产 Python、协议或 SQLite 格式。

日志和 XML：`/tmp/stk-table-grid-focused-final.*`、`/tmp/stk-table-grid-full-final.*`、
`/tmp/stk-table-grid-render-final.*`；示例日志 `/tmp/stk-offline-analysis-example-tests.log`。
大表 blob 解码、数值排序/筛选、编辑、导出和跨输出比较尚待开发；操作见[分析运行指南](project-analysis-runs.md#以科学表格查看内联结果)。

提交 `5aed38d` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36723665636) **4/5 任务通过**：
Linux **1085/1086**，唯一失败是上述旧畸形保存回复夹具过早断言项目修订；macOS CPU **730/730**、
Metal **134/134** 与 Windows CPU **689/689** 全部通过。新增 **29 项 CPU** 在三平台实际执行通过，
**12 张**新增 GL/Vulkan/Metal 中英文宽窄图片逐张复查；Linux/macOS 打包及全新目录启动检查通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36723665667) **7/7 任务通过**：
Linux Python 3.10/3.12 各 **2201 passed / 7 skipped / 4 deselected**，Windows Python 3.10/3.12 各
**1788 passed / 61 skipped / 260 deselected**。新增离线示例 **14 项**在四个 Python/系统组合均执行通过；
控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。证据在 `/tmp/stk-table-grid-ci-36723665636/audit-summary.json`。
该提交的桌面工作流整体仍为失败；后续夹具修复及验证见上方 M16 记录。

## 2026-09-30：归档输出的类型化检查

分析运行的“读取归档结果”增加全部请求输出的只读总览与类型化属性浏览。请求顺序独立于结果对象顺序，
未交付输出明确标出；部分失败仍可检查已经交付的表格、值与原始错误详情。对象键使用带引号的 JSON 表示，
数组下标保留数字身份；每页最多 64 个属性，选中标量可逐页查看精确值，长预览不会冒充完整内容。

关键节点 critical review 覆盖数据精度、归档回执、原子采纳、页面缓存和原生交互：

- 原先读取流程先更新运行记录再检查结果哈希，失败可能混合新旧状态。现在先核对冻结身份、图哈希、
  结果回执和完整候选文档，再共同发布运行、结果、blob 目录与检查模型；失败保留整组已核对状态。
- 普通原生 JSON 解析器可能把超出 64 位范围的 Python 整数解析为浮点数。桌面按保留类型的 Python JSON
  规则编码候选并核对归档 SHA-256；精度已丢失的候选被拒绝，不能当作近似数显示。
  编码保留整数、`1.0`、`-0.0`、`null`、空文本和字符串 `"null"` 的区别，不使用会归一化浮点数的图规范编码。
- 深度和精确 UTF-8 编码大小检查先于递归序列化与复制，覆盖完整结果而非仅输出字段；
  采用归档本身的深度 64、4 MiB 上限，不误用较小的保存分析文档限制。运行/回执的字段集合和标量约束
  也在比较前核对，不依赖可选的桥协议调试校验；嵌套的额外回执字段在进入递归比较前被拒绝。
- 属性、路径和精确值只在明确选择或换页时创建并缓存。单行保存一个类型化路径分量，避免大祖先键重复复制；
  4096 字节标量分页不切断 UTF-8 字符或 JSON 转义。所有页可到达，页码及浏览版本进入表格缓存和回调身份。
- 审查发现只允许打开容器时，相同截断前缀的长标量键无法辨认。现在标量也可明确打开，
  通过完整分页路径确认所选键，返回上级仍保持对象与数组的类型化路径语义。
- 浏览只消费已读取文档。图像、二维图、文件和外置表格/值仍显示元数据，数据集描述不代表数组已加载；
  不额外查询文件、启动运行、求值或导入 Viewer。错误和警告保留完整原始结构，包括非对象条目。

最终重点 **143/143 通过**：新增纯模型 **19 项**、真实桥界面/控制器 **12 项**、GL/Vulkan 中英文宽窄渲染 **16 项**，
以及已有分析运行、输入复用、冻结图、参数/输出编辑和相关渲染回归。12 个界面测试的共同夹具最初漏声明提交参数，
导致执行在归档前被拒绝；补上合法声明和终态诊断后，全部复测通过，没有放宽执行或结果校验。
新测试核对 Python 独立编码哈希、真实超范围整数、同长度分页排序、长标量键、原始/未保存输入保护、另一窗口输入、
项目/桥/编辑器寿命，以及失败刷新保留整组已验证状态且不重发。纯模型另覆盖深度、精确 4 MiB 边界及全部七类交付。

新增 **16 张**与受影响的已有 **24 张**截图共 **40 张**逐张复查；宽窄布局可查看选中精确值、类型、错误内容和原有显式操作。
窄区域的后置列仍通过横向滚动查看。EN/ZH 各 **1340 条消息**一致，四份相关指南 **115 个本地链接**有效；
新增 31 项 CPU 与 GL/Vulkan/Metal 对应渲染纳入三平台必跑门禁。

完整 Linux CTest **1049/1049，失败/错误/跳过均为 0**。日志和 XML：`/tmp/stk-result-inspection-focused-final.*`、`/tmp/stk-result-inspection-full-final.*`。
本轮没有 Python、协议、SQLite 格式或真实模型调用变化；内联科学表格此时以属性层级检查，尚不是行列网格。
blob 内容预览、编辑、导出和跨输出数值比较仍待后续；操作见[分析运行指南](project-analysis-runs.md#检查归档输出与错误)。
提交 `a20e4f7` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36720049116) **5/5 任务通过**：
Linux **1049/1049**、macOS CPU **701/701** 与 Metal **130/130**、Windows CPU **660/660**，均无失败、错误或跳过。
新增 31 项 CPU 在三平台实际执行通过；**24 张**新增 GL/Vulkan/Metal 检查页图片逐张复查。
Linux/macOS 打包与全新目录启动、实际预设渲染通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36720049006) **7/7 任务通过**：Linux 两版本各
**2187 passed / 7 skipped / 4 deselected**，Windows 两版本各 **1774 passed / 61 skipped / 260 deselected**；
控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。证据在 `/tmp/stk-result-inspection-ci-36720049116/audit-summary.json`。

## 2026-09-30：历史输入的明确复用

保存分析运行页增加“复用输入”和“清空输入准备”。按历史运行的精确快照 ID 读取、核对清单与映射，
包括普通选择器前 100 份以外的快照；复制到空准备区后显示来源运行、快照身份及哈希。
只复制输入元数据，保留当前定义和参数/输出草稿。明确准备才创建新 UUID，使用当前保存定义与旧快照；开始执行仍单独操作。

关键节点 critical review 覆盖元数据边界、异步采纳、输入保护、真实桥交互和截图。审查与集成验证修正了：

- 同一次 C++ 调用中读取计划字段并移动计划对象存在参数求值顺序风险。先固定快照 ID，再构造移动捕获，
  跨编译器也不会发送空 ID；回归核对实际请求的精确 ID。
- 只核对项目与运行身份不足以保护新的编辑意图。请求同时固定所载定义版本、导航与准备区版本，
  所有文件/文字/映射修改都提升准备区版本；清空和保留的旧控件回调同样检查版本。
- 完成结果只消费一次。清空、页面往返、重新载入定义、桥/项目更换或另一窗口尚在输入，都会拒绝迟到采纳；
  以后结束输入或再次清空也不会自动填回旧结果。读取期间仍可明确清空准备区。
- 复用快照独立于列表索引和当前选中运行；核对每条映射的哈希、大小与唯一记录身份，按每个别名计入 256 MiB 输入预算，
  未引用的合法大文件仍保留在文件菜单。不复制未消费的图、结果或原始路径树，也不读取文件字节。
- 旧界面测试曾在直接填写路径后立即调用上一帧的添加按钮，现先完成重绘再操作新按钮，保留生产保护。
  新回归用真实键盘输入、Enter 和鼠标添加核对完整流程，并增加对应中英文输入提示。
  渲染夹具错误地假设创建回复包含完整分析对象，已改为使用明确的输入身份及名称。

最终重点 **112/112 通过**：新增纯模型 **16 项**、真实桥界面 **14 项**、GL/Vulkan 中英文宽窄渲染 **8 项**，
连同已有运行、参数、输出、冻结图与运行渲染回归。测试实际删除原文件与快照对象后复用并准备，
确认这两步仅核对元数据；没有开始执行、读取结果或新图求值。新运行采用新参数/输出，旧计划保持原值。
原生文件校验仍在明确开始时执行，不能把复用成功当作输入字节可用证明。

完整 Linux CTest **1002/1002，失败/错误/跳过均为 0**。新增 8 张及受控件变更影响的已有 16 张运行截图
共 **24 张**逐张复查；宽窄窗口的准备、状态与结果控件可见，长标识和哈希仍需横向滚动。
EN/ZH 各 **1312 条消息**一致，相关文档 **115 个本地链接**有效；新增 30 项 CPU 与八项 GL/Vulkan 渲染纳入必跑门禁。

日志和 XML：`/tmp/stk-analysis-input-reuse-focused-final.*`、`/tmp/stk-analysis-input-reuse-full-final.*`。
本轮没有 Python、协议、SQLite 格式或模型调用变化。准备区是编辑器内存状态，不跨重启保存。
提交 `22dd126` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36716494632) **7/7 任务通过**：
Linux 两版本各 **2187 passed / 7 skipped / 4 deselected**，Windows 两版本各
**1774 passed / 61 skipped / 260 deselected**；控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。
[桌面 CI](https://github.com/sijintech/stk/actions/runs/36716494807) **5/5 任务通过**：Linux **1002/1002**、
macOS CPU **670/670** 与 Metal **122/122**、Windows CPU **629/629**，均无失败、错误或跳过。
新增 30 项 CPU 测试在三平台执行通过；**12 张** GL/Vulkan/Metal 输入复用图片逐张复查。
Linux/macOS 打包与全新目录启动通过；证据在 `/tmp/stk-input-reuse-ci-36716494807/audit-summary.json`。
操作见[分析运行指南](project-analysis-runs.md#复用历史运行的输入)，实际设备仍按[验收清单](workbench-acceptance.md)确认。

## 2026-09-30：参数与请求输出的联合草稿

保存分析增加已声明输出的选择、清空、全选、顺序编号与分页。参数和输出共用一个本地草稿；
明确保存使用一次修订检查，一次撤销恢复两者。空数组 `[]` 原样表示不请求输出，启用单项追加到请求顺序末尾；
切换分页、参数修改或读取冻结图不重置选择。画布与明确校验仍使用最后保存的定义，不自动运行草稿。

关键节点 critical review 覆盖精确类型、候选文档界限、组合保存、页间缓存、迟到回调与中英文截图。
审查和集成验证发现并修正：

- 图可声明超过 256 个输出，但单次请求最多选择 256 个；不能以选择上限截断声明列表。
  界面每页显示 64 项，大于 256 项时禁用全选，后续页仍可编辑；纯模型先检查名称、重复项和数量，再复制完整候选。
- 输出端口在契约中是 `node.port` 字符串，不能当作对象读取。专项交互和真实渲染同时核对端点文字。
- 页数和行数相同不代表表格内容相同。分页版本进入排序缓存身份；页面往返、导航与草稿版本使旧控件回调失效。
- 输出独立修改同样阻止载入其他定义、改名及准备运行。保存回复丢失后核对整个类型化文档及输出顺序，
  相同才结束待核对状态，不同或删除均保留本地草稿，不重发写入。旧参数专用接口仍保留已保存输出。
- 上一提交的两处 CI 竞态分别以项目修订/刷新完成条件和假桥明确放行握手修复，保留原有断言；
  另增已经收到全部事件后才注册回调的测试，明确区分该合法顺序，没有修改生产 Future 或重试语义。

最终重点 **86/86 通过**：新增输出纯模型 **11 项**、真实桥界面 **13 项**、GL/Vulkan 宽窄中英文渲染 **8 项**，
以及已有参数/冻结图回归与两项假桥顺序检查。真实键盘与鼠标完成参数应用、清空/全选、按序勾选、一次保存和撤销，
同时核对大整数、浮点数、负零、空文本与 null 保留，Viewer 求值和准备运行次数保持零。
新增及受布局影响的 **16 张** GL/Vulkan 图片逐张检查；关键值、请求状态与联合保存按钮可见，后置列仍可横向滚动。
完整 Linux CTest **964/964，失败/错误/跳过均为 0**。EN/ZH 各 **1304 条消息**一致，
相关文档 **132 个本地链接**有效；新增测试纳入三平台必跑和渲染门禁。

日志和 XML：`/tmp/stk-analysis-outputs-focused-final.*`、`/tmp/stk-analysis-outputs-full-final.*`。
本轮未修改 Python、协议或项目格式，没有真实模型调用。
提交 `31bf2f7` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36713314741) **5/5 任务通过**：
Linux **964/964**、macOS CPU **640/640** 与 Metal **118/118**、Windows CPU **599/599**，均无失败、错误或跳过。
新增 24 项输出 CPU 测试在三平台实际执行；晚注册回调回归在 Linux/macOS 通过，其所属假桥目标原本不在 Windows 构建中。
**12 张** GL/Vulkan/Metal 输出图片逐张复查，
另补查上一轮被阻塞的 **4 张** Metal 冻结图；macOS 打包及全新目录启动通过。
两处旧夹具竞态已在本次平台回归中验证修复。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36713314613) **7/7 任务通过**：Linux 两版本各
**2187 passed / 7 skipped / 4 deselected**，Windows 两版本各 **1774 passed / 61 skipped / 260 deselected**；
控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。证据在 `/tmp/stk-outputs-ci-36713314741/audit-summary.json`。
本地草稿不跨程序重启保存，不包含连线和节点内部参数编辑；操作与边界见[分析文档](project-analyses.md)。

## 2026-09-30：历史运行的独立冻结图检查

运行页增加明确的“检查冻结流程图”，从已读取的记录打开独立只读来源。保留完整图、原始类型化参数、
明确输出选择，以及运行/分析/快照身份、来源修订和哈希；来源与保存定义、参数草稿、Viewer 回执相互独立。
普通修订推进、原定义删除、运行选择或状态变化不会替换已打开的计划；关闭/重开项目或更换桥会话清空历史来源。
检查不查询文件或归档、不启动图。布局只保存检查模式，节点说明和明确校验仍使用当前本机环境。

关键节点 critical review 覆盖消费字段的大小/深度限制、复制边界、来源身份、异步校验、活动输入与真实截图。
自查、交叉审查和集成测试发现并修正：

- 复用文档校验时，深度和字节限制必须从 `document` 自身计算；不能把完整运行包装、生命周期或结果套入较小的文档上限。
  提取共享边界检查，先校验将消费的字段再复制，只保留不可变定义与来源，不遍历或复制结果错误树。
- 每帧的检查按钮只捕获身份和计划哈希，点击后才从当前记录作有界复制，避免重复复制整个运行 JSON。
- 仅核对运行身份不足以保护新的导航意图。检查及返回按钮另固定导航版本，主模式、侧栏往返和布局恢复都会使旧回调失效；
  所有安装窗口的活动输入同样阻止切换。多行输入的测试用 Cmd/Ctrl+Enter 提交，普通 Enter 仍为换行。
- 窄区域使用来源下拉框，冻结输出表把请求状态排在端口之前。完整哈希和后置列通过表格滚动查看；
  图缩小到完整概览后需放大才能看清节点标签，不把微小概览当作可读细节验收。

最终重点 **50/50**：新增共享边界/真实桥状态 **14 项**、原生交互 **10 项**、中英文宽窄 GL/Vulkan 渲染 **8 项**，
以及提取前已有的精确参数模型 **18 项**。真实桥测试覆盖删除原文件后打开冻结图、当前分量从 1 改为 2 后历史仍为 1、
返回后保存定义仍为 2、未保存/无效文字保留、迟到校验和销毁回调拒绝，检查时请求数和 Viewer 求值次数不变。
完整 Linux CTest **931/931，失败/错误/跳过均为 0**；新增 24 项 CPU 纳入三平台必跑检查，
八项 GL/Vulkan 渲染及对应四项 Metal 场景各有不可跳过的门禁。
最终 **8 张**冻结图截图逐张复核，EN/ZH 各 **1295 条消息**一致，相关文档 **71 个本地链接**有效。

日志和 XML：`/tmp/stk-frozen-graph-focused-final.*`、`/tmp/stk-frozen-graph-full-final.*`。
本轮仅修改原生客户端，未重复完整 Python 回归；真实桥由上述原生测试覆盖。
提交 `4bcde42` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36710073707) 为 **3/5 任务通过**：
Windows CPU **575/575**；Linux **931 项执行、930 通过、1 失败**；macOS CPU **615 项执行、614 通过、1 失败**，均无跳过。
新增 24 项 CPU 在三平台全部通过，八项 GL/Vulkan 冻结图渲染通过且图片逐张检查。
Linux 失败为已有假桥事件测试注册回调与快速回复的竞态；macOS 失败为已有丢失回复测试在项目刷新完成前点击核对。
两处夹具修复随下一轮输出编辑交付，保留原有顺序及不重放写入断言。Metal、macOS 打包和新目录启动未执行，不能计为通过。
Linux 打包及新目录 GL/Vulkan 冒烟通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36710073782) **7/7 任务通过**：Linux 两版本各
**2187 passed / 7 skipped / 4 deselected**，Windows 两版本各 **1774 passed / 61 skipped / 260 deselected**；
控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。证据在 `/tmp/stk-frozen-run-ci-36710073707/audit-summary.json`。
没有真实模型调用。检查不冻结插件环境、不证明历史结果可用，也不提供连线编辑或历史计划改写。
操作见[分析图](analysis-graphs.md#历史运行的冻结图)，实际设备仍按[工作台验收](workbench-acceptance.md)单独确认。

## 2026-09-30：保存分析的精确参数草稿

原生“保存的分析 → 分析定义”增加提交参数表、选中值编辑和明确保存。独立草稿保留缺省、`null`、
空字符串、64 位整数、浮点数和未知覆盖项；仅替换文档的 `parameters`，名称、图及输出保持原值。
保存复用已有修订检查与普通撤销，不新增项目格式、协议或 Python 后端操作。编辑、应用本地值及保存不启动节点或准备运行。

关键节点 critical review 覆盖精确 JSON 模型、原生输入、保存回执、会话失效和真实截图。
独立审查与自查发现并修正：

- 普通摘要不显示字符串引号，可能混淆 `null` 与 `"null"`；参数表改用保留类型差异的 JSON 表示，
  窄窗口把参数名和值放在前两列，其他列仍可横向滚动。
- 字符串声明可能保存着 `null` 或数组等不完整值。此时使用严格 JSON 编辑，未经修改的应用不会把它转换为字符串；
  明确输入 `"null"` 才转换为字符串。字符串、缺省值和明确移除覆盖分别处理。
- 合法参数的类型化文字表示可能超过 64 KiB 规范化存储大小。输入上限改为 384 KiB，并继续核对最终文档与参数限制；
  大型负零数组可以原样编辑应用，整数溢出、重复键、无效 UTF-8 和过深 JSON 在改变草稿前拒绝。
- 当前输入、无效但未应用的文字和已经应用的草稿分别受保护。跨项目关闭/重开后保留原始未确认文字，
  旧回调不能写入新项目；删除覆盖后清除失效行选择。参数保存也保留另行输入但尚未保存的名称。
- 保存回复丢失后只读取原 UUID。相同内容可结束待核对状态，不同内容或已删除记录仍保留本地候选；不重发写入。
  原生渲染测试使用真实键盘事件，并分别使用 macOS Command 与其他平台 Ctrl 作为主修饰键。

最终新增重点 **42/42 通过**：精确模型 **18 项**、真实 Python 桥与界面 **16 项**、GL/Vulkan 中英文宽窄渲染 **8 项**。
完整 Linux CTest **899/899，失败/错误/跳过均为 0**。测试实际核对一次 CAS 保存与撤销、迟到操作、
相同/不同/已删除记录读回、无效末次按键、未声明键、空输出、大整数及负零；图求值与准备运行次数保持零。
最终 **8 张**截图逐张复查，窄表的关键值与保存按钮可见，长值及后面的类型/来源列使用横向滚动。
EN/ZH 各 **1282 条消息**一致；必跑检查匹配全部 42 项，新界面已加入三平台 CI 门禁。

日志和 XML：`/tmp/stk-analysis-parameters-focused-final.*`、`/tmp/stk-analysis-parameters-full-final.*`；
这一步仅修改原生客户端，未重复运行完整 Python 套件，真实桥行为由上述原生回归覆盖。
提交 `9d59622` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36707359639) **5/5 任务通过**：
Linux **899/899**、macOS CPU **591/591** 与 Metal **110/110**、Windows CPU **551/551**，均无失败、错误或跳过。
新增 34 项 CPU 在三平台实际执行；八项 GL/Vulkan 与四项 Metal 参数渲染通过，**12 张**图片逐张复查。
打包和全新目录重开检查通过。[Runtime CI](https://github.com/sijintech/stk/actions/runs/36707359661) **7/7 任务通过**：
Linux Python 3.10/3.12 各 **2187 passed / 7 skipped / 4 deselected**，Windows 两版本各
**1774 passed / 61 skipped / 260 deselected**；控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。
CI 证据在 `/tmp/stk-parameters-ci-36707359639/audit-summary.json`。真机输入法与实际设备仍按验收清单另测，没有真实模型调用。
草稿仍只在编辑器内存中；不自动合并旧修订，也不提供节点连线或节点内部参数编辑。
操作见[分析文档](project-analyses.md)，真机步骤见[工作台验收](workbench-acceptance.md)。

## 2026-09-30：冻结输入的分析执行与结果归档

格式 **9** 增加不可变分析计划和生命周期事件，明确绑定一份已有输入快照、完整分析定义及相对文件映射。
准备、开始、取消、遗留执行核对与结果读取分开；准备和状态变化不提升编辑修订、不进入普通撤销。
旧项目需要备份优先的显式升级，普通打开不迁移。原生保存分析的“运行”页与 Python 的七个 `analysis_runs` 接口共用后端。
执行使用独立输入副本、本机图 worker 和跨进程单次领取；先归档并校验结果，再保存终态。中断记录不自动重跑。
原文件、原定义或工作缓存之后变化，不改写已冻结计划和已归档字节；读取时重新检查归档哈希，部分输出失败保留失败状态。

关键节点 critical review 覆盖存储/升级、执行器与文件发布、脚本协议、原生会话和 Viewer 保护、真实数值及截图。
审查和集成验证发现并修正：

- 关闭可能发生在领取执行权等待数据库期间，或归档完成但终态事务尚未取得写锁时。
  现在重新检查关闭状态，并在终态写事务内检查取消；取消意图先落库再通知 worker，租约保持到结算结束。
- 结果解码曾误复用较小的可编辑文档限制，可能无法重开合法的大结果；现独立校验 4 MiB 结果上限。
  同时核对输出选择、图身份、参数元数据、归档总量和全部引用 blob，不以缓存文件存在代替内容校验。
- 绑定名称必须匹配实际图解析器；相对路径同时检查跨平台名称、大小写/Unicode 冲突及逐段长度。
  DAT 字段名取映射后的基本名，测试及指南已按此语义核对，而非把重命名映射误当作原字段名。
- 新开分析页没有 Viewer 时，已知节点可能缺少目录而显示为未知。独立目录读取仅查询 `graph.catalog`，
  不触发 Viewer 的元数据完成回调或待执行工作；构造与 `sync()` 仍不发请求，迟到/销毁/换桥结果均被隔离。
- 界面明确区分左侧载入定义与选中运行的冻结来源；冻结参数/输出改用类型化表格，避免长 JSON 裁切。
  已有或未渲染的 Viewer 来源可明确关闭；导入只接受空 Viewer，并再次检查所有窗口的活动输入、目标容量和迟到回调。
- 完整回归发现旧格式断言和脚本操作目录预期尚未更新；修正后复测通过。三平台必跑检查已增加新目录测试组，防止跳过被误计为通过。

后端完整回归 **2171 passed / 22 skipped / 4 deselected**，另新增的真实 Python 内核集成 **1/1 通过**；
前者未包含随后添加的该内核用例。新增存储专项 **78 项**，执行器/桥专项 **39 项**，协议及 facade **41 项**均通过。
脚本内核实际调用全部七个接口，验证冻结输入、明确执行、结果校验、重开与旧句柄失效，且不新增运行阶段的编辑历史。
指南前两段 Python 示例也通过实际 facade、严格桥及真实 worker 执行；准备后删除原 VTI 文件仍能成功读取归档。
Python 跳过项包括本机 VTK 离屏探测失败、可选 MCP、性能场景和真实 MuFerro 环境，均不计为验收。

原生重点 **47/47** 通过；新增五项独立目录场景另在完整回归中全部执行。
最终完整 Linux CTest **857/857，失败/错误/跳过均为 0**，含 **19 项**真实桥运行/导入回归、**6 项**目录回归和 **16 项**新工作台渲染。
真实有符号数据经快照、执行、归档、原生解码及明确导入，核对范围 **[-9, 14]**，Viewer 求值次数保持为零。
**16 张**中英文宽窄 GL/Vulkan 图逐张复核；窄窗口的参数值和哈希需横向滚动，全图适配时需放大才能看清节点标签。
EN/ZH 字典各 **1268 项**一致，无重复。旧布局基准、打包、窗口和 Viewer 回归全部通过。

日志 `/tmp/stk-analysis-runs-python-final.log`、`/tmp/stk-script-analysis-runs.log`、
`/tmp/stk-analysis-runs-focused.log`、`/tmp/stk-analysis-runs-full-final.log` 及对应 XML 保存验证结果。
提交 `331cdb8` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36703834959) **7/7 任务通过**：
Linux Python 3.10/3.12 各 **2187 passed / 7 skipped / 4 deselected**，Windows 两版本各
**1774 passed / 61 skipped / 260 deselected**。真实脚本内核用例在四个矩阵任务中均实际通过；
Windows 新增的一项跳过为需要特权的符号链接夹具，不计为通过。控制协议 24 项、桌面 MCP 3 项和 Web 检查通过。
同提交的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36703834980) **5/5 任务通过**：Linux **857/857**、
macOS CPU **557/557**、Metal **106/106**、Windows CPU **517/517**，均无失败、错误或跳过。
新增 25 项 CPU 在三平台实际通过，24 项 GL/Vulkan/Metal 分析运行渲染均实际执行，
24 张准备/结果、中英文宽窄截图逐张复查通过。Linux/macOS 打包及全新目录启动检查通过。
Windows 九项 Viewer 配置捕获和此前缺少科学依赖的五项标量测试全部通过，确认前两轮修复已闭环。
CI 证据另存 `/tmp/stk-runs-ci-36703834980/audit-summary.json`、日志、XML 与图片。本轮没有真实模型调用。
本轮不冻结 Python/插件/驱动环境，不承诺位级复现；SQLite 备份不包含输入与结果资产。
原生快照选择器首版显示前 100 份，完整冻结图通过 Python 查询；左侧画布仍展示所载入定义。
详见[分析运行指南](project-analysis-runs.md)及[真机验收清单](workbench-acceptance.md)。

## 2026-09-30：窄视口明确取景与场景文字对比度

原生“全部显示”、Home、方向按钮及小键盘方向快捷键按当前三维主区域的宽高比取景。
透视使用水平和竖直限制中较窄的视角，正交同样考虑横向范围；保留方向及上向量。
这只改变明确的原生取景动作，结果自带的数值相机、复位、手动相机、普通窗口和分栏调整保持既有语义。
旧两参数模型接口和跨 Python/Web 的相机数值基准没有改写。

来源、警告、统计与紧凑状态标签使用可选不透明主题底色及配对文字色；普通标签仍透明。
新样式不改变尺寸、文字位置、裁剪、焦点、悬停提示或鼠标行为。自定义主题仍负责提供合适的配对颜色，
没有宣称任意主题配色均满足固定对比度标准。

关键节点 critical review 检查了当前布局与上一帧尺寸的差异、延后方向操作、退化边界、数值原子性及真实 GPU 像素。
审查发现极小视角或极大正交范围可能产生不可用的裁剪/投影矩阵；现先检查完整候选，再更新相机，失败保留所有原字段。
测试另补投影坐标有限性与正深度检查，避免 NaN 比较错误地通过可见性断言。

新增 **4 项 CPU 相机回归、6 项 CPU 标签回归、2 项 GL/Vulkan 像素回归**。
相机测试覆盖不同宽高比、透视/正交、方向与旋转、点/线/面边界，以及无效输入不修改相机。
标签像素测试在白、黑、饱和彩色背景上检查默认深色与自定义浅色主题，覆盖中英文、禁用文字、1×/2×缩放，
要求底色和字形独立于场景背景，普通标签边缘仍透明。

重点 **26/26** 通过；最终完整 Linux CTest **816/816，失败/错误/跳过均为 0**。
八项标量工作台渲染另通过实际数值控件绑定检查相机、布局更新但尚未 GPU 绘制时的取景、方向/Home 快捷键、
正交边界和普通缩放后的相机保持，未增加图求值次数。旧布局基准全部保持原值。
八张宽窄、中英文 GL/Vulkan 图逐张复核：窄视口左右裁切消失，来源与统计清晰可读。
色条和底部统计仍可能遮住少量体数据；窄英文布局仍有长标签及导出按钮截断，不能把完整取景描述为完全无遮挡。

日志 `/tmp/stk-viewer-fit-focused.log`、`/tmp/stk-viewer-fit-full.log`，对应同名 XML 保存结果。
未修改 Python 后端、项目格式或图契约，没有模型调用；未据此宣称 macOS/Windows 真机操作及 Windows GPU 已验收。
操作边界见[桌面指南](desktop.md)和[标量指南](scalar-volume.md)，真机步骤见[工作台验收](workbench-acceptance.md)。

提交 `921f8e34f86555bae52fe4e09b896d3f452260f1` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36700121488)
为 **4/5 作业通过**：Linux 实际 **816/816**、macOS CPU **532/532**、Metal **98/98**，均无失败、错误或跳过。
Windows 已成功编译并实际执行 **492 项，487 通过、5 失败、0 跳过**；失败全部为五项 `ScalarVolumePython`，
原因均是 Windows 测试虚拟环境只安装基础包，缺少 NumPy。不能把这次 Windows 作业记为通过。
Windows 的全部 **9 项**配置捕获回归已通过，确认前一轮映射文件复用及迟到回调修复；
新增 **4 项**相机、**6 项**标签和 **6 项**浮点上传数值测试也全部通过。
后续将 Windows CI 依赖改为显式科学/可视化 extras，并在编译前运行真实图依赖检查；
该修复已在 `331cdb8` 的 Windows **517/517** 中验证，五项标量测试全部实际通过（见上方分析执行记录）。
全部 **12 张**GL/Vulkan/Metal 宽窄中英文标量图逐张复核；Linux/macOS 安装归档及独立目录启动检查通过。

同一提交的[Runtime CI](https://github.com/sijintech/stk/actions/runs/36700121518) **7/7 作业通过**：
Linux Python 3.10/3.12 各 **2028 passed / 7 skipped / 4 deselected**，Windows 两版本各 **1616 passed / 60 skipped / 260 deselected**；
control **24 项**、desktop/MCP **3 项**与 Web 构建通过。原始日志、JUnit、截图及解析结果在 `/tmp/stk-fit-ci-36700121488/`。

## 2026-09-30：有符号标量体渲染与数值范围检查

新增 `scalar-volume` 预设，明确选择数值字段、零起始分量及可选单位标签，保留正负值；
原 `volume` 的模长语义和默认打开行为不变。单位为空时沿用源数据元信息，明确标签只改标注、不换算数值。
分析定义可以保存并重开这些参数；错误字段或分量不会偷偷改用其他字段，失败时仍保留并标明旧结果。

critical review 分别检查后端科学数值、原生上传与传递函数、表单类型、真实桥和中英文渲染。
发现并修正以下问题：

- 原 GPU 浮点路径把低于固定负阈值的有限值当作缺失值，且极大正负范围可能在 shader 中溢出。
  现在只对独立上传副本用 CPU 双精度归一化，缺失值使用分开的有限哨兵；原始数据、探针和物理单位色条保持原值。
  极小范围、常数场、全负场及正负极值均有独立数值与 GPU 对照。
- 原浮点下采样可能漏掉被跳过样本的溢出。现在在下采样前检查源数组，有限值转 float32 溢出时明确拒绝。
  量化比例溢出或下溢到零同样报错；没有改变现有 NaN/Inf 量化规则，也不将其解释为可靠的缺失值掩码。
- 表单根据初始通用类型转换默认值，可能把 JSON null 误变为文字，或放宽必需字段。
  现在先完成引用类型交集再构造默认值；单位清空恢复 null，严格字段仍不接受 null。
- 实际中文截图出现英文参数名和截断，已补齐字段、分量、单位及色图翻译；原有七个预设的布局基准逐叶比较完全一致。

后端新增 **68 项**数值与真实图求值回归。原生专项 **33/33** 通过，涵盖真实桥、保存重开、表单、
极值归一化及 GL/Vulkan；最终本地完整回归为 Python **2013 passed / 22 skipped / 4 deselected**，
Linux CTest **804/804，失败/错误/跳过均为 0**，其中包含上一轮 Windows 夹具修复与新增迟到回复回归。
Python 跳过项仍为本机离屏 VTK、可选依赖、性能和真实许可求解器场景，
不计为已验证。中英文字典各 **1213 项**一致且无重复；新增预设以外的全部表单布局基准保持原值。

八张 GL/Vulkan 宽窄中英文截图逐张复核，真实桥产生的负值、字段、分量与单位标签可见。
复查另发现原有窄视口取景裁切和浅色背景文字对比度不足，已列入下一轮修复；本轮没有隐式改写用户相机。
线性过滤下缺失边界仍使用近似哨兵插值，量化缺失值仍沿用端点编码，限制见[标量体渲染指南](scalar-volume.md)。

日志 `/tmp/stk-scalar-focused.log`、`/tmp/stk-scalar-renders-final.log`、`/tmp/stk-scalar-full-final.log`、
`/tmp/stk-scalar-python-full.log`；对应同名 XML 保存测试结果。本轮无真实模型调用。
以上是本地 Linux 验证，不代表 macOS/Windows 真机交互、Windows GPU 或异机 SSH 已验收。

提交 `a830dce6b742273acf0944a351cfae9c01b58ac7` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36697082152)
四个作业通过，Windows 作业在测试发现阶段构建失败，**未执行 CTest**。
Linux 实际 **804/804**、macOS CPU **522/522**、Metal **97/97**，均无失败、错误或跳过；
新增 CPU 回归在 Linux 实际执行 **16 项**、macOS **15 项**（另一个 Viewer 表单用例仅纳入 Linux），
两平台均执行了全部 **9 项**配置捕获回归。Linux **8 项**及 Metal **4 项**标量渲染全部执行，
**12 张**宽窄中英文截图逐张复核，确认有符号范围、字段、分量和单位；窄视口裁切及浅底文字问题仍在此提交中可见，
修复属于下一轮。Linux/macOS 打包及独立目录启动检查均通过。
Windows 失败来自 `gtest_discover_tests` 的分号标签在 MSVC 命令中破坏引号，导致带空格的 CMake 模块路径解析错误；
因此上一轮 Windows 捕获夹具修复仍未得到实际测试确认，不能将本次桌面运行记为全通过。
已把该 CPU 目标的发现标签收敛为既有 `project` 标签，保留所有五项测试及原超时；修复仍需下一次 Windows CI 确认。

同一提交的[Runtime CI](https://github.com/sijintech/stk/actions/runs/36697082091) **7/7 作业通过**：
Linux Python 3.10/3.12 各 **2028 passed / 7 skipped / 4 deselected**，
Windows Python 3.10/3.12 各 **1616 passed / 60 skipped / 260 deselected**；control **24 项**、desktop/MCP **3 项**和 Web 构建通过。
跳过的可选依赖、Windows VTK/平台场景及真实求解器不计为验证。原始日志、JUnit、截图及解析结果位于
`/tmp/stk-scalar-ci-36697082152/`。

## 2026-09-30：项目分析文档保存、重开与独立检查

新增 `stk.analysis-document/1`，把完整节点图、提交参数和输出选择保存为普通项目表格中的一条记录。
固定表/字段 UUID、修订检查和普通撤销沿用既有项目接口；要求格式至少为 3，当前格式 8 不变。
原生分析图增加“保存的分析”、明确保存、分页列表、重新载入和改名；Python/桥另支持完整定义替换。
纯 Viewer 配置捕获是单独协商的只读操作，不推进待求值工作、刷新元数据或切换焦点。
保存定义不冻结执行来源绑定、数据内容或节点实现，也不自动运行图；未知节点等语义错误可作为结构合格的草稿保存。

关键节点 critical review 覆盖事务边界、损坏数据、桥契约、原生异步寿命、真实输入与中英文截图。
实现及复查修正了以下问题：

- 保存后的快照可能超过桌面消息容量：在同一写事务内增量检查完整快照的 12 MiB 上限，失败回滚修订、历史及重做栈。
  分页读直接检查有界字面量，不求值公式或加载节点；管理字段被改为引用/公式时明确诊断，不静默覆盖。
- 保存模式曾沿用 Viewer 检查对象：现使用独立定义，不显示或关联 Viewer 回执、解析值；Viewer 单独变化不使保存图校验失效。
- 等待保存/读取时切换标签，迟到响应可能夺回页面：保留最新导航选择，旧响应只更新对应的已保存定义。
- 保存回复丢失时不能盲目重发：派发后保留 UUID，明确读取核对当前内容；关闭编辑器或切换项目/桥时把待核对标识写入本地日志。
  当前观察不是找回原始事务回执，取消本地等待也不保证撤销已提交的编辑。
- 名称与列表的旧回调需核对项目、选择、分页及修订；实际 Unicode 输入后第一次点击保存的完整事件链已验证。

后端存储专项 **67 项**、项目存储/撤销/文件/桥组合 **190 项**通过；桥、脚本和图结构契约专项 **104 项**通过。
首次全量 Python 回归暴露测试关键字白名单落后于实际验证器；核对双方实现后补齐四个已支持关键字，
新增 14 项创建/替换契约回归并与独立 JSON Schema 验证器交叉检查，没有放宽结构契约。
首次原生回归的七项失败来自测试夹具：五项把 JSON 对象键顺序误当内容差异，两项修改了夹具预设未声明的参数。
修正比较及参数选择后，UUID、修订、恰好一次写入、零隐式求值和迟到响应的严格断言均保留。

最终完整 Python 回归 **1945 passed / 22 skipped / 4 deselected**；跳过项包括本机离屏 VTK 不可用、可选依赖、
真实许可求解器及性能场景，不计为已验证。日志 `/tmp/stk-analysis-docs-python-final.log`，
JUnit `/tmp/stk-analysis-docs-python-final.xml`。

最终原生专项 **102/102**，完整 Linux CTest **780/780，失败/错误/跳过均为 0**。
新增 **28 项 CPU 测试**及 **8 项 GL/Vulkan 保存分析渲染**均实际执行；八张保存图逐张复核，
窄图保留选中节点的可读缩放，滚动表格、定义来源和修订提示可见。原有布局基准未修改。
中英文字典各 **1206 项**一致且无重复，改动文档的本地链接全部有效。

日志 `/tmp/stk-analysis-docs-focused-final.log`、`/tmp/stk-analysis-docs-full.log`；
JUnit `/tmp/stk-analysis-docs-focused-final.xml`、`/tmp/stk-analysis-docs-full.xml`。

提交 `c3509706356beba27264611bc9b5389f3cf47114` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36692666924)
四个任务通过、Windows CPU 任务失败：Linux **780/780**、macOS CPU **507/507** 与 Metal **93/93**，
这些平台均无失败、错误或跳过；Windows **465 passed / 2 failed / 0 skipped**。
新增 **28 项 CPU 测试**在三个平台均实际执行，Linux/macOS 全通过，Windows 的两项失败均在配置捕获测试中。
一项错误比较未规范化的 Windows 路径；另一项夹具重复覆盖仍被旧载荷映射的同名缓存文件，
随后旧载荷等待条件掩盖新求值失败，超时回调引用已离开的栈变量并导致堆错误。
已隔离修正夹具路径比较、不可变缓存复用、新载荷确认及回调寿命，并新增受控迟到回复回归；
**本次桌面运行不能记为全通过。** 后续 `331cdb8` 的 Windows **517/517** 已确认修复有效，
九项 Viewer 配置捕获回归均实际通过，见上方分析执行记录。
Linux **8 项**、Metal **4 项**保存分析渲染均实际执行，全部 **12 张**宽窄中英文截图逐张复核；
Linux/macOS 打包和独立目录启动检查通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36692666888) 七个任务全部通过：Linux Python 3.10/3.12
各 **1960 passed / 7 skipped / 4 deselected**，Windows Python 3.10/3.12 各 **1549 passed / 59 skipped / 260 deselected**；
control **24 项**、desktop/MCP **3 项**及 web 构建通过。跳过项为可选依赖、平台限定、性能与真实求解器场景，
不计为已验证；Windows runner 不执行 GPU 渲染。证据存于 `/tmp/stk-analyses-ci-36692666924/audit-summary.json`。

本轮没有真实模型调用；本地 Linux 验证不代表 macOS/Windows 真机交互、Windows GPU 或异机 SSH 验收。
操作与限制见[项目分析文档](project-analyses.md)，人工步骤见[工作台验收](workbench-acceptance.md)。

## 2026-09-30：分析节点图与结果来源检查

新增原生“分析节点图”编辑器，复用当前 Viewer 预设与求值时冻结的配置。
只读画布显示有类型端口、连接顺序及节点参数；侧栏用通用表格检查默认值、明确值、缺失值、
`$param` 引用、提交参数和输出。支持适应图、定位节点、平移、缩放与返回三维。
图定义无位置时按依赖层次排列，循环、重复身份、未知类型与无效端点保留可见诊断。
界面展开有界，超过 200 个节点拒绝展开，不改写原图；画布诊断与显式 `graph.validate` 分开。

关键节点 critical review 分别覆盖纯展示模型、Viewer 来源、异步控制器、UI 生命周期与真实渲染。
发现并修正以下问题：

- 实际求值发送预设 ID，本地冻结的预设不能独自证明后端执行的图。现在结果的两个图哈希须有效、一致且匹配，
  才关联节点执行、解析值及可用输出；导入载荷没有原始图时不猜测。哈希仍不验证源文件变化或节点实现版本。
- `step="latest"` 与求值后具体步数不能混为同一提交；原始值和解析值分列，缓存切步保留原始配置与回执。
- JSON 普通相等会合并整数与浮点数；配置比较改用规范化表示，忽略键顺序但保留数值类型。
- 参数、来源、目录、桥会话或检查模式变化会丢弃旧校验响应；旧按钮再次核对代次，不校验新意图。
- 返回三维的延迟导航检查原编辑器与目标窗口寿命，关闭或移动后的旧回调不能访问销毁的窗口。

专项 **66/66 通过**：纯模型 14、画布 11、来源 13、控制器/原生交互 20，以及 GL/Vulkan 宽窄中英文渲染 8 项。
渲染夹具生成本地科学场，经真实桥取得哈希匹配的结果，再修改颜色参数，检查当前与旧结果区别；
查看、选择和校验都未增加 Viewer 求值次数。八张图片已逐张复核，窄窗口滚动与定位操作可达。
首次完整回归的 10 项旧布局基准不匹配，结构比较确认 175 处差异仅为页头下拉框扩宽后控件横坐标及宽度变化。
独立审查指出默认窄区域菜单被进一步挤压至 16px，因此缩短编辑器名称为“分析图”/“Node Graph”，
保留完整功能名称用于说明；所有旧布局基准恢复原值，没有接纳挤压后的布局。
原生测试夹具首次测到脚本启动的额外两次请求，改为等待 `script.read` 与 `ui.attach` 真正完成再建立基线；
旧回调零请求、明确校验恰好一次请求及零求值的严格断言保留。

中英文字典各 **1179 项**一致且无重复；改动文档的 **142 个本地链接、19 个锚点**有效。
最终资源同步后的完整 Linux CTest **744/744，通过项实际执行，失败/错误/跳过均为 0**，所有旧布局基准保持原值。
日志 `/tmp/stk-graph-full-final.log`，JUnit `/tmp/stk-graph-full-final.xml`。
提交 `20680eb1f6dd92715a447d2c54afe5f979bcd684` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36688052923)
五个任务全部通过：Linux **744/744**、macOS CPU **479/479** 与 Metal **89/89**、Windows CPU **439/439**，
均无失败、错误或跳过。Linux/macOS 逐项核对 JUnit，Windows 逐项核对 CTest 日志；新增模型、画布、
来源、控制器与交互 **58 项 CPU 测试**在三个平台全部执行，Linux **8 项**、Metal **4 项**节点图渲染全部执行。
GL/Vulkan/Metal 宽窄中英文共 **12 张**截图已逐张复核；Linux/macOS 打包及独立目录启动检查通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36688052859) 七个任务全部通过：Linux Python 3.10/3.12
各 **1861 passed / 7 skipped / 4 deselected**，Windows Python 3.10/3.12 各 **1450 passed / 59 skipped / 260 deselected**；
control **24 项**、desktop/MCP **3 项**及 web 构建通过。跳过项为可选依赖、平台限定、性能及真实求解器场景，
不计为已验证；Windows runner 未执行 GPU 渲染。证据存于 `/tmp/stk-graph-ci-36688052923/audit-summary.json`。
本轮没有修改 Python 求值后端，也没有外部模型调用；macOS/Windows 真机输入、触控板和高 DPI 仍待验收。
专项日志 `/tmp/stk-graph-focused-final.log`、JUnit `/tmp/stk-graph-focused-final.xml`。
用法与边界见[分析节点图指南](analysis-graphs.md)，人工步骤见[工作台验收](workbench-acceptance.md)。

## 2026-09-30：准备、分析与分栏聚焦导航

视图菜单增加聚焦准备（AI）、聚焦分析（Viewer）和恢复分栏布局。
导航复用现有编辑器实例，优先当前最大化区域中活动的同类标签、其他活动同类标签、其他已有标签，
最后才检查全部区域的空位并新增。已有分割树、面板、AI 未发送问题和 Python 未执行源码保留。
恢复分栏保留活动标签；默认启动布局与独立工作区存储没有改变。

Python 新增 `stk.ui.activate_editor(editor_id, *, maximize=False)` 和 `restore_split_layout()`，
分别协商可选 `editors.activate` / `layout.unmaximize`。默认 `maximize=False` 显示分栏，返回实际区域、标签及模式；
恢复接口返回此次是否取消了最大化。原生菜单作用于当前窗口，Python 延续首个安装窗口规则。
目标窗口仍在输入文字时拒绝导航，另一窗口的输入不阻止本窗口操作。关闭窗口、会话失效和到期请求在主线程执行前被检查。
沿用现有布局 v1；导航不发送模型请求、不求值或修改数据库，已完成导航不因后续超时而回滚。

critical review 覆盖失败原子性、容量查找、编辑器复用、多窗口、延迟回调及 Python 契约。
同步修正旧内部导航只看首个候选区域而忽略其他空位的问题；最大化时删除重复的旧“恢复区域”菜单项，
保留分栏中的“最大化区域”和原 Ctrl+Space 快捷键。界面核查确认新菜单中英文窄窗口文字完整。
首次构建修正测试使用了错误的 Esc 枚举；审查修正两项输入测试未先选中默认 Python 源码的问题。

Python 聚焦/能力协商/现有脚本及契约组合 **38 项通过**；原生重点 **51/51**，
随后追加并通过 **1 项**从 Python 输入框 Ctrl/Cmd+Enter 提交导航代码的真实操作回归。
完整 Linux CTest **678/678，失败/错误/跳过均为 0**；新导航 CPU 11 项、真实 Python 5 项及菜单渲染 4 项全部实际执行。
四张 GL/Vulkan 中英文菜单图片通过，两个 GL 视图已逐项查看，对应 Vulkan RGB 像素完全一致。
字典各 **1109 项**一致且无重复。
提交 `cb22d552f412bd3267b2583e61abc14442782375` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36681997606)
五个任务全部通过：Linux **678/678**、macOS CPU **421/421** 与 Metal **85/85**、Windows CPU **381/381**，
均无失败或跳过。Linux/macOS 逐项核对 JUnit，Windows 按 CTest 日志逐项计数；新增 `FocusNavigation`
**9 项**、`FocusMenuLayout` **2 项**及真实 Python 导航 **5 项**在三个桌面平台均实际执行。
GL/Vulkan/Metal 中英文菜单共 **6 张**截图已逐张复核，Linux/macOS 打包及独立目录启动检查通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36681997274) 七个任务全部通过：Linux Python 3.10/3.12
各 **1861 passed / 7 skipped / 4 deselected**，Windows Python 3.10/3.12 各 **1450 passed / 59 skipped / 260 deselected**；
新增 Python 导航 **8 项**在四个矩阵任务中均通过，control **24 项**、desktop/MCP **3 项**及 web 构建通过。
跳过项仍为可选依赖、平台限定、性能及真实求解器场景，不计为已验证。证据存于
`/tmp/stk-focus-ci-36681997606/audit-summary.json`；macOS/Windows 真机操作仍待验收。

日志 `/tmp/stk-navigation-python.log`、`/tmp/stk-focus-native-focused.log`、`/tmp/stk-focus-console.log`、
`/tmp/stk-focus-full.log`；JUnit `/tmp/stk-focus-full.xml`。
使用见[桌面指南](desktop.md#ai-助手)、[Python 指南](scripting.md)，人工步骤见[工作台验收](workbench-acceptance.md)。

## 2026-09-30：AI 多行、多字段上下文选择

AI 工作区新增独立的范围选择器，复用已有上下文捕获接口，不扩展 SQLite 或桥格式。
在一张表中按 UUID 勾选行与字段，分页、明确全选/清空、数量和数值预览；保持原表顺序，
不改变共享表格当前行，也不继承其他编辑器的排序/筛选。快速捕获单行入口继续可用。
选择器固定打开时的项目句柄、修订和表格副本；修订变化时保留旧预览，须明确重新载入后从空范围选择。
单轴限制为 100 行、64 字段，乘积超过 1000 时不能捕获，不会截取超限范围。

critical review 分别覆盖纯选择模型、界面异步生命周期、上下文身份和实际截图。发现并修正：

- 选择新范围时准备按钮仍可能使用旧保存上下文；现已禁用，并在回调再次检查，关闭或捕获成功后才恢复。
- 异步捕获刚排队就关闭选择器；现只在确认成功后关闭，失败保留范围与标题，旧修订仍要求明确重新载入。
- 遗留页签 getter 引用已销毁编辑器；改为值捕获，并回归销毁后保留绑定。
- 旧“选择范围”回调可重置正在编辑的选择；加入活动选择器检查。
- 数值先完整序列化才截断；改为直接有界读取单元格，避免深层/超长值的完整展开。
- 截图中的“保存的值”不适用于待捕获预览，改用普通“值”列名。

纯模型 **10 项**、真实桥选择交互 **7 项**、原 AI 工作区 **4 项**、新增 GL/Vulkan 宽窄中英文截图 **8 项**，
重点共 **29/29 通过**。首次回归修正了测试夹具的提供方载入、折叠面板点击与控件路径，未绕过生产检查。
完整 Linux CTest **658/658 通过，失败/错误/跳过均为 0**。
四张新增 GL 视图逐项检查，四张对应 Vulkan 图片 RGB 像素一致；窄窗口捕获按钮可见，后续对话可滚动。
字典各 **1101 项**一致、无重复，改动文档 **138 个本地链接**有效。所有回归无外部模型调用。

日志 `/tmp/stk-scope-focused2.log`、`/tmp/stk-scope-full.log`，JUnit `/tmp/stk-scope-full.xml`。
最后列名修正后八项渲染再次通过，英文宽图已复看，四组 GL/Vulkan RGB 仍一致；
日志 `/tmp/stk-scope-renders-final.log`。
提交 `56367bfd422d3426fe0360169b0e1c0f549dc34f` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36679780190)
五个任务全部通过：Linux **658/658**、macOS CPU **405/405** 与 Metal **83/83**、Windows CPU **365/365**，
均无失败或跳过。Linux/macOS 核对 JUnit，Windows 按 CTest 日志逐项计数；新增 `ProjectContextSelection`
**10 项**及 `ProjectScope` **7 项**在三个桌面平台均实际执行，GL/Vulkan/Metal 的中英文宽窄范围选择截图
共 **12 张**已逐张复核，Linux/macOS 打包与独立目录启动检查通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36679780231) 七个任务全部通过：Linux Python 3.10/3.12
各 **1853 passed / 7 skipped / 4 deselected**，Windows Python 3.10/3.12 各 **1442 passed / 59 skipped / 260 deselected**；
control **24 项**、desktop/MCP **3 项**及 web 构建通过。跳过项仍为可选依赖、平台限定、性能及真实求解器场景，
不计为已验证。证据存于 `/tmp/stk-scope-ci-36679780190/audit-summary.json`；macOS/Windows 真机输入仍待验收。
用法见[桌面指南](desktop.md#ai-助手)、[上下文指南](project-contexts.md)；人工步骤见
[工作台验收](workbench-acceptance.md#ai-多行上下文选择)。

## 2026-09-30：模型参数建议与修改检查

新增 `stk.parameter-edits/1` 请求模式。完整文字回复经明确转换，严格限定为原始捕获范围内的标量
`set_cell`；类型、单位、公式/引用保护、来源修订及大小限制均由本机检查。草案和助手来源在一个事务内保存，
同一请求重试找回原身份及当前状态，应用后撤销不重新打开回执。格式保持 8，旧文字请求摘要不变；
旧读取器可能不支持新的请求模式，不能把格式号相同视作模式兼容。

原生 AI 工作区增加用途选择、可读的建议摘要及数值、原始回复详情，以及显式保存建议和打开修改检查。
检查入口重新读取保存记录，固定请求、项目、编辑器和检查代次，保留草案身份；不自动预览、应用或运行任务。
已占用的检查、活动文字输入、过期修订与无可用标签位置都会拒绝导航。应用/丢弃后已有 AI 页自动重读状态。

关键节点 critical review 分别覆盖存储原子性、桥与兼容性、原生异步生命周期和实际渲染，修正三项问题：

- 标签已满时先检查目标容量，再接纳草案，避免失败导航留下半完成的检查状态。
- 格式化前限制 JSON 嵌套深度，只显示标量；24,000 层异常回复退回原文，不能生成草案。
- 应用或丢弃时通知 AI 控制器重读候选状态，并隔离此前排队的读取，避免继续显示待处理。

后端/桥/真实 Python worker 的组合回归 **455 项通过**，核心参数提案单文件 **78 项通过**。
原生重点回归 **29/29**；完整 Linux CTest **633/633，失败/错误/跳过均为 0**。
新增八张参数建议宽/窄、中英文 GL/Vulkan 图片已复核：四个 GL 视图逐项检查，对应 Vulkan 的 RGB 像素完全一致。
原 AI 窄布局与流式视图也已复看，十组 AI 相关 GL/Vulkan 截图像素一致。字典各 **1087 项**一致且无重复。
完整 Python 回归 **1838 passed / 22 skipped / 4 deselected**；跳过包括本机离屏 VTK 探针不可用的 15 项、
可选 MCP、真实许可求解器和性能场景，不计为已验证。全部模型测试使用受控适配器，没有调用真实账户。

日志 `/tmp/stk-proposal-integration.log`、`/tmp/stk-proposal-core-final.log`、`/tmp/stk-proposal-native-focused.log`、
`/tmp/stk-proposal-full.log`、`/tmp/stk-proposal-python-full.log`；JUnit `/tmp/stk-proposal-full.xml`。
提交 `bf9ccd1142722162750d15b6c47c447ede240cbd` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36677388526)
五个任务全部通过：Linux **633/633**、macOS CPU **388/388** 与 Metal **79/79**、Windows CPU **348/348**，
失败及跳过均为 0；Linux/macOS 逐项核对 JUnit，Windows 按 CTest 日志逐项计数。
新增 `ProjectProposal` **7 项**与 `SavedReviewPython` **8 项**在三个桌面平台均实际执行；
GL/Vulkan/Metal 的中英文宽/窄布局共 **12 张**参数建议截图已逐张复核，安装包及独立目录启动检查通过。
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36677388512) 七个任务全部通过：Linux Python 3.10/3.12
各 **1853 passed / 7 skipped / 4 deselected**，Windows Python 3.10/3.12 各 **1442 passed / 59 skipped / 260 deselected**，
新增参数提案 **78 项**在四个矩阵任务中均通过；control **24 项**、desktop/MCP **3 项**及 web 构建通过。
Runtime 跳过项包括可选依赖、平台限定、性能及真实求解器场景，未计为已验证；证据存于
`/tmp/stk-proposal-ci-36677388526/audit-summary.json`。真实账户参数建议与 macOS/Windows 真机输入仍待验收。
使用步骤见[参数提案指南](project-parameter-edits.md)，人工步骤见[工作台验收](workbench-acceptance.md)。

## 2026-09-30：临时流式回复

阿里适配器新增一次性 SSE 读取，保留非流式调用接口。执行器在内存中收集有界文字，
通过可选 `project.requests.progress` 返回正式请求和临时累计快照；原生 AI 工作区每秒读取、
标明“临时回复（尚未保存）”，旧桥退回正式状态查询。格式仍为 8，无片段表、自动重发或远端查询。
只有 `stop`、`[DONE]`、HTTP 完整结束以及最终文字与片段一致时，才保存完整助手消息。

关键节点 critical review 已覆盖三层：适配器解析、执行器生命周期和原生显示。
独立复审与实现自查发现并修正取消时仍保留旧片段的问题；现在点击取消立即隐藏，
不依赖后续读取成功。额外校验片段计数整数、执行器身份及序列/前缀单调性。
关闭语义明确为：已接受进入原子保存的完整回复可以完成提交，之后到达的回复与片段被隔离；
保留回调在关闭后立即返回，不等待正在保存的执行器锁。对应竞争条件已加入回归。

传输、执行器、桥、Python facade 与能力目录的组合回归 **208 项通过**；
原生重点回归 **14/14 通过**，包括真实桥配受控流式适配器的增量显示、取消后完整迟到回复、
切换项目与同桥重开、旧桥能力回退。所有夹具均无网络调用，桥环境的真实凭据为空。
日志 `/tmp/stk-stream-backend.log`、`/tmp/stk-stream-native-focused.log`。
新增中英文 GL/Vulkan/Metal 的临时回复截图用例，并在各平台 CI 强制检查这些用例实际运行。
Linux 完整 CTest **610/610 通过，失败/错误/跳过均为 0**；JUnit `/tmp/stk-stream-full.xml`，
日志 `/tmp/stk-stream-full.log`。四张新增中英文 GL/Vulkan 截图已逐项检查，临时标记、换行及操作按钮正常。
中英文字典各 **1073 项**一致、无重复。

提交 `6123300` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/36675028481) **5/5 任务通过**：
Linux **610**、macOS CPU **373** / Metal **75**、Windows CPU **333** 项，均无失败或跳过。
Linux/macOS 已下载 JUnit 独立计数；Windows 已逐条核对实际 CTest 结果行。
四项流式/旧桥回退测试在三个平台实际通过，新增六张 Linux/Metal 中英文流式截图均已检查。
安装包及独立启动检查通过，证据 `/tmp/stk-stream-ci-36675028481/audit-summary.json`。

同一提交的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36675028490) **7/7 任务通过**：
Python 3.10/3.12 的 Linux 各 **1747 passed / 7 skipped / 4 deselected**，
Windows 各 **1336 passed / 59 skipped / 260 deselected**；控制 24 项、旧桌面/MCP 3 项及 Web 构建通过。
跳过项为可选依赖、平台能力及独立真实求解器/性能验收，不计为已验证能力。
真实账户流式调用及 macOS/Windows 原生真机验收仍待完成。

## 2026-09-30：原生 AI 准备工作区

新增 AI 工作区编辑器，从项目页头或文件菜单进入，同页完成捕获数据、准备问题（只保存）、核对与明确发送。
保存问答可导航，普通文字回复按宽度换行；运行中/不确定记录仅以约 1 秒间隔读取本地状态，最多 90 秒。
错误或到期暂停，明确刷新可恢复读取；不因刷新、重开或查看历史而发送、重试或核对遗留执行。
沿用格式 8，没有新桥方法、数据表或事件；默认布局未切换，没有流式显示、工具调用或自动模拟。

本机 Linux 重点测试 **41/41 通过**，最终完整 CTest **602/602 通过，失败/错误/跳过均为 0**。
完整 JUnit 已独立核对实际 602 个用例，包含八项 AI 中英文、宽/窄 GL/Vulkan 渲染；对应八张图片已检查。
中英文字典各 **1072 项**一致、无重复。控制器覆盖准备重试、第二步失败保留消息、完成读取、90 秒停止、
明确刷新恢复、取消与旧读取竞争、切换项目及不存在的请求；原生交互覆盖活动输入、一次点击准备、
项目隔离、多区域共享问答和长英文/中文/制表符文本换行，保存文字保持原样。

独立审查与测试发现并修正：活动输入跨项目残留、首次点击只提交输入、长回复裁切、多个区域的历史显示不一致；
控制器缓存插入导致 `ordered_json` 请求引用失效的刷新崩溃，改为持有请求副本；
SQLite 重读配置后的字段顺序导致相同准备被拒绝，改为规范化比较。
准备仍是消息保存、请求创建两步：第二步失败可留下消息，同次会话对当前相同输入重试复用身份，
不承诺跨重启原子事务恢复。未准备的输入仅在编辑器内按项目保存。

首轮完整回归中 10 份原布局基准因新增 AI 编辑器名称扩大下拉框而不匹配；逐项结构比较确认
全部差异只在页头控件横坐标/宽度，区域、分隔条、正文与控件类型不变，更新基准后完整套件通过。
日志 `/tmp/stk-ai-full-final.log`，JUnit `/tmp/stk-ai-full-final.xml`。

代码提交 `852b343` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36667294040) **7/7 任务通过**。
Linux Python 3.10/3.12 各 **1665 passed、7 skipped、4 deselected**；Windows Python 3.10/3.12 各
**1254 passed、59 skipped、260 deselected**。控制/Blender 协议 **24 passed**，旧桌面/MCP **3 passed**，
Web 构建、两版 Linux graph doctor 和 wheel/sdist 构建均成功。跳过项为可选依赖、性能、平台及许可求解器场景，
没有失败记录；日志 `/tmp/stk-ai-runtime-36667294040.log`。

同一代码提交 `852b343` 的 [桌面 CI](https://github.com/sijintech/stk/actions/runs/36667294145) **5/5 任务通过**：
Linux **602/602**、macOS CPU **369/369** 与 Metal **73/73**、Windows MSVC CPU **329/329**，均无失败、错误或跳过。
Linux/macOS 数量由下载的 JUnit 实际用例核对；Windows 日志逐项核对 329 个通过用例，新增 4 项 AIWorkspace
与 6 项 Exchange 测试全部实际运行。八项 Linux、四项 Metal 的 AI 宽/窄中英文渲染全部通过，截图已复核。
Linux/macOS 安装包与启动检查通过。CI artifact 位于 `/tmp/stk-ai-ci-36667294145/`，
Windows 日志 `/tmp/stk-ai-windows-36667294145.log`。

macOS/Windows 原生真实模型、Windows GPU 真机渲染和实际输入设备验收仍待完成；本轮未调用真实模型，
不扩大此前 Linux 合成单元格真实账户验收的范围。用法见[桌面指南](desktop.md#ai-助手)，
人工步骤见[工作台验收](workbench-acceptance.md#ai-助手)。

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

## 2026-09-29 显式上下文与讨论来源

格式 7 的上下文捕获、手工消息、草案来源已接入 SQLite、桥、Python 与原生讨论页。
保存和恢复均不应用参数、不调用模型或执行消息中的代码。用法见[上下文与讨论指南](project-contexts.md)。

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

## 2026-09-29 持久草案与恢复

格式 6 的保存、分页、读取、丢弃和原子应用已接入存储、桥、Python facade 与原生检查页。
项目/桥/工作流 Python **248 通过、2 跳过**，两个真实许可求解器测试按默认配置跳过；
本批只修改项目草案管理，未重新运行许可求解器。草案存储新增 **34** 项测试，包括迁移备份/回滚、
并发保存/应用、规范化 ID、响应恢复、校验损坏和撤销后终态保留。

原生重点和新增截图 **11/11**，完整桌面 **546/546、无跳过**；验证了真实桥的保存/重开/重启、
重新预览后明确应用、过期草案另起副本、输入/异步保护、保留错误提示和冲突刷新。
中英文 GL/Vulkan 草案面板四项通过，中文 Vulkan 和英文 GL 图像已查看；字典各 **947 项**一致。
`f1001cf` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36565773604) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36565773668) 全部通过，包含 Linux GL/Vulkan、
macOS Metal、Windows 编译/CPU、安装包和干净环境启动；草案截图已纳入跨平台必跑检查。

日志 `/tmp/stk-saved-drafts-python-all.log`、`/tmp/stk-saved-drafts-native.log`、`/tmp/stk-saved-drafts-full.log`，
JUnit `/tmp/stk-saved-drafts-full.xml`。操作与兼容边界见[草案指南](project-drafts.md)。

## 2026-09-29 Python 发起原生修改检查

`stk.project.review` 经真实隔离 Python worker 和本地 UI 请求通道启动只读预览，并自动显示原生差异页。
新增 6 项原生集成测试，覆盖明确点击应用后才写入/可撤销、控制台快捷键与新增页签、正在输入的文本保护、
无效参数/Unicode 字节限制、旧修订与草案冲突、请求排队期间切换项目、清除迟到候选及分离桥的请求失效。
相关原生 **13/13**、Python **69/69**、完整桌面 **537/537、无跳过**；能力协商和共享 schema 校验通过。
中英文字典各 **923 项**，中文 Vulkan 检查页截图已查看，文档 80 个本地链接有效。

日志 `/tmp/stk-python-review-python-all.log`、`/tmp/stk-python-review-native.log`、
`/tmp/stk-python-review-full.log`；JUnit `/tmp/stk-python-review-full.xml`。
`fa324d6` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36562716767) 与
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36562716768) 全部成功，包含 Linux GL/Vulkan、macOS Metal、
Windows 编译/CPU 测试、安装包/干净环境启动与双版本 Windows Python。
该提交的入口不包含模型生成、持久草案或新的外部任务执行；草案持久化见后续新增记录。

## 2026-09-29 参数表驱动批次

新增批次协调与原生面板复用项目运行和 MuFerro 模板。相关 Python **29 通过、2 跳过**，
真实 Release MuFerro 批次显式启用后 **1 项通过**：298 K / 310 K 的两个运行，参考能量分别为
`−727.9144455` / `−691.5580935`；重复准备/提交/收集不新增对应任务或结果。
错误/恢复覆盖部分准备失败、进度持久化、关闭重开、过期参数、准备及提交响应丢失、中断、取消后
仅为指定行生成独立尝试，以及伪造标签不能改变模板命令。参数入口校验最终 **1/1** 复验通过。

完整桌面 **531/531、无跳过**；新的 Linux 原生按钮测试通过真实桥/Runtime 和明确的假 SDK
执行三行批次，重复保存/准备/提交、收集以及服务器停止后的关闭重开均通过。
四项中英文 GL/Vulkan 批次渲染通过，已查看中英文截图；中英文字典各 923 项一致。
日志 `/tmp/stk-batch-python-all.log`、`/tmp/stk-batch-full.log`、JUnit `/tmp/stk-batch-full.xml`，
真实运行日志 `/tmp/stk-batch-real.log`，证据 `/tmp/stk-batch-real-HRg9Kh/test_real_muferro_temperature_0/batch-evidence.json`。
`a598c2c` 的 [desktop CI](https://github.com/sijintech/stk/actions/runs/36450940425) 和
[Runtime CI](https://github.com/sijintech/stk/actions/runs/36450940464) 全部成功，包含 Linux GL/Vulkan、
macOS Metal、Windows 编译/CPU 测试、打包/干净环境启动，以及 Windows Python 3.10/3.12；文档部署成功。
原生自动化和离屏渲染仍不等同于 macOS/Windows 真机输入设备交互验收。

## 2026-09-28 MuFerro 项目流程首版

当前工作流通过真实桌面桥调用项目/Runtime API，连接隔离的本机 Linux Runtime，运行已安装的 Release muFerro。
程序 SHA-256 为 `c0c1f3454f5ff5384c76e70455b0441bb8ebeeb40b711b2360f2f0f1d099683a`；
单 rank、单线程、`launcher=none`，不启动 Hydra。许可仅由求解器从原有目录使用，未复制到 STK 项目。

- SDK 原始案例导入后冻结，16×16×16 网格、101 步、输出间隔 100；298 K 最终归一化总能量
  `−727.9144455` 与已有参考一致；修改项目参数至 310 K 后生成独立方案和任务，总能量 `−691.5580935`。
- 两次 `stk-mupro-1` 均通过，下载后重验输入、产物哈希、完成记录、进度、能量和帧头。
  独立 NumPy 文本读取检查每次 30 个 DAT 的所有值有限、点数/分量数、网格范围和索引唯一性；
  同时覆盖原生按分量索引的 DAT 格式，未把测试模拟器的逐点列格式误当作唯一格式。
- 同一方案重复提交不增加任务；重开项目后重复收集仍为原结果行，改变温度后保留旧运行及其过期状态。
- 当前原生 `stk-desktop --headless --preset muferro-domains` 打开两次已收集结果，输出第 100 步铁电畴；
  OpenGL 图像已目视检查。100 是最后输出的 Polar 帧，最终能量对应第 101 步。
  软件 EGL 首次上下文候选报告 `EGL_BAD_MATCH`，随后上下文创建和导出成功，进程退出 0。

测试入口为 `tests/test_workflow_muferro.py::test_real_muferro_project_workflow`，需显式配置
`STK_TEST_MUPRO_PREFIX`、`STK_MUPRO_ENV_SCRIPTS`、`MUPROROOT`；默认 CI 不启动许可求解器。
输入冻结一致性检查加入后，真实求解器再次全程通过；最终日志 `/tmp/stk-muferro-real-final.log`、
`/tmp/stk-muferro-real-render-final.log`，
证据 `/tmp/pytest-of-mnemora/pytest-134/test_real_muferro_project_work0/real-evidence.json`，
图片 `/tmp/stk-muferro-real-render/{first,changed_temperature}.png`；这些临时路径不属于发行物。

工作流/相关 Python 回归 **32 通过、1 跳过**（上述真实测试另行通过）；本机完整桌面 **525/525**。
原生导入按钮验证了真实 Python 调用和项目切换保护，GL/Vulkan 中英文仿真面板截图通过并检查。
桌面日志 `/tmp/stk-muferro-full.log`、JUnit `/tmp/stk-muferro-full.xml`，
Python 日志 `/tmp/stk-muferro-python-final.log`；原生输出显示调整后的相关 **5/5** 通过，
见 `/tmp/stk-muferro-final-native.log`。

新增 `SimulationPython.NativeMuFerroButtonsPrepareSubmitCollectViewAndReopenOffline` 直接驱动原生
项目面板，经过真实 Python worker 和隔离的 Linux Runtime 执行导入、准备、提交、日志与收集。
重复准备时服务器任务数仍为零，重复收集后只有一个任务和一行结果；关闭 Runtime、关闭再打开项目后，
从原生“查看已收集结果”按钮加载非空三维载荷。测试默认使用明确的假 SDK，Linux CI 要求此项执行且通过；
设置上述真实 SDK 环境后，同一个原生测试也已通过，结果表参考能量 `−727.9144455` 一致。
日志 `/tmp/stk-muferro-native-real.log`，JUnit `/tmp/stk-muferro-native-real.xml`。
加入完整原生链路后的本机全量桌面 **526/526、无跳过**，日志 `/tmp/stk-muferro-native-full.log`、
JUnit `/tmp/stk-muferro-native-full.xml`。

功能提交 `7d96151` 首轮 Runtime CI 发现 Windows 3.12 的 `fstat`/`stat` ctime 语义差异；
修正提交 `ef25286` 的 [Runtime CI](https://github.com/sijintech/stk/actions/runs/36442800913)
全部通过，包含 Windows Python 3.10/3.12。最终桌面跨平台 CI 也已通过，见下方最新确认。
本节不能作为 Windows GPU、真机输入法或 macOS/Windows 到实际远端 SSH 的验收证据。

### 完整仿真目标逐项复核

`763eb0b` 上重新核对“在 STK 中完成一个完整的仿真计算”：

| 必要能力 | 已检查的证据 |
|---|---|
| 原生导入、编辑参数、生成并冻结输入 | 原生完整流程驱动导入/准备；`ProjectPython` 验证表格编辑；真实工作流从项目行的 298 K 改到 310 K，保存各自冻结输入 |
| 明确提交、状态、日志与取消 | 原生完整流程准备后服务器任务数为零，再通过提交按钮执行真实求解器并读取日志；原生运行面板测试单独覆盖取消及请求次数 |
| 收集、检查与关联输出 | 两次真实运行各校验 36 个文件哈希；项目保存冻结输入、任务 ID、程序哈希及结果关联；重复收集只有一行结果 |
| 数值及三维结果 | 独立 NumPy 读取两次运行各 30 个 DAT 的全部数值，检查有限值、网格和分量索引；能量分别为 −727.9144455、−691.5580935；原生 Viewer 导出两次结果并检查图片 |
| 重开、断线恢复与独立重算 | 原生流程停止 Runtime 后重开项目并加载结果；两次真实运行在重开后仍存在，旧参数标记 changed、新参数 current；响应丢失测试重新打开项目后只恢复一个任务 |
| 自动回归与交付 | 本机桌面 526/526 无跳过，真实原生按钮用例通过；实现及测试已推送 main，`763eb0b` 的跨平台桌面与 Runtime CI 全部成功 |

前述默认 pytest 临时目录已被后续测试自动清理。为保留可复查的项目与数据，本次重新执行真实测试并
指定独立目录；当前证据为 `/tmp/stk-muferro-audit-763eb0b-I6Zw8m/test_real_muferro_project_work0/real-evidence.json`，
日志 `/tmp/stk-muferro-audit-real.log`（1 项通过）、`/tmp/stk-muferro-audit-numeric.log`、
`/tmp/stk-muferro-audit-render.log`，图片 `/tmp/stk-muferro-audit-render-zrl8l2j8/{first,changed_temperature}.png`。
该目录不会被后续默认 pytest 清理，仍是本机临时验收数据，不属于发行物。
以上证据证明单次完整仿真功能闭环已实现并验收。后续批量、AI、节点编辑与平台真机交互按主计划继续推进。

## 2026-09-28 最新跨平台确认

MuFerro 流程最终提交 `763eb0b` 的 [desktop 36444060112](https://github.com/sijintech/stk/actions/runs/36444060112)
**全部成功**：Linux GL/Vulkan、macOS Metal、Windows 编译/CPU/桥、Linux 安装包和干净环境启动，
以及 macOS 打包与从解压后的应用启动。
[Runtime 36444060140](https://github.com/sijintech/stk/actions/runs/36444060140)、
[文档 36444060188](https://github.com/sijintech/stk/actions/runs/36444060188)和 Secret scan 全部成功。
下载产物的 Linux JUnit **526 项**、macOS JUnit **322 项 CPU / 59 项 Metal** 均无失败、无跳过；
Linux 新增完整仿真按钮测试确实执行。macOS 中英文仿真面板与离线三维截图已目视检查，
产物在 `/tmp/stk-macos-muferro-763eb0b`、`/tmp/stk-linux-muferro-763eb0b`。
Windows 日志确认 **282/282** CPU 测试通过，MuFerro 原生导入及项目身份保护用例实际执行；
本机日志 `/tmp/stk-muferro-desktop-763eb0b-ci.log`。
Runtime 3.12 wheel 中 `suan/workflows` 和脚本入口与当前源码字节一致，确认新增模块实际进入 Python 包。
前一提交 `ef25286` 的桌面运行被后继推送取消，不作为通过证据；本次成功运行覆盖其 Windows 时间戳修正。
Windows CI 仍不包含 GPU 真机渲染，实际异机 SSH 和输入法交互仍需相应平台环境验收。

此前表格修正提交 `c3fa59c` 的[desktop 36416998477](https://github.com/sijintech/stk/actions/runs/36416998477)
**全部成功**，包含 Windows 原生编译/CPU/桥、Linux GL/Vulkan、macOS Metal、两平台打包和干净环境启动。
本机完整 **504/504、无跳过**；下载最终 macOS 产物的 **313 项 CPU、53 项 Metal** 无跳过全部通过，
目视确认横向滚动条不再遮挡第三行数据。
[Runtime 36416998488](https://github.com/sijintech/stk/actions/runs/36416998488)和
[文档 36416998657](https://github.com/sijintech/stk/actions/runs/36416998657)成功。
后续说明文档提交 `d01bf76` 的 Runtime **36417769639**、文档 **36417769613** 成功，未改变上述功能代码。

`a0d7f57` 包含文件 Viewer、表格滚动/精确排序、修改预览及工作台必跑检查：
[desktop 36414890836](https://github.com/sijintech/stk/actions/runs/36414890836)、
[Runtime 36414891171](https://github.com/sijintech/stk/actions/runs/36414891171)、
[文档 36414891070](https://github.com/sijintech/stk/actions/runs/36414891070) **全部成功**。
桌面包括 Linux、macOS、Windows、打包和干净环境启动；Windows 仍是 CPU/桥测试，无 GPU 验收。
已下载 macOS frames artifact：JUnit 的 **312 项 CPU、53 项 Metal** 全通过且无跳过；
归档含 **22 张工作台图片**，已目视检查离线三维/参数表和文件预设入口。
截图进一步发现横向滚动条减少了实际可见行数，其高度修正已由上述 `c3fa59c` 验证。

`dbf3cde` 自身的 desktop run 36414605007 被后续 CI 配置提交取消；上述成功的后继运行覆盖其修改预览代码。
此前文件/表格提交 `f1a0f72` 的 desktop **36413089067**、Runtime **36413089012**、文档 **36413089085** 也全部成功。
本节更新下方各开发包编写时的“待跟踪”状态，不把更晚的尚未完成 CI 自动视为已通过。

## 2026-09-28 项目修改预览

相关 Python **230/230**、完整重编译桌面 **503/503** 通过。源库字节、外部文件和实际历史保持不变；
候选公式结果与使用返回命令进行实际提交后的快照一致。覆盖只读数据库、旧格式拒绝/WAL、
大小预算、身份替换、公式循环错误、过期修订及预览求值期间的并发编辑。真实桥和独立 Python worker
确认预览不发布修改事件，C++ 客户端验证明确提交前后区别；本批远端 CI 待跟踪。

## 2026-09-28 表格滚动与计算值排序

完整重编译桌面 **503/503、无跳过**；此前组件/窗口子集 **149/149**。
覆盖 1x/1.5x/2x 下的横向滚动条、Shift + 滚轮、窗口事件横向数据转换、排序和列宽命中、
选择/键盘、扩大区域/删除列后的偏移校正。公式按计算值排序，64 位整数保持精度，等值记录顺序稳定。
离线工作台四项中英文 GL/Vulkan 截图确认派生温度列可滚入视野。手势是合成事件验收，物理触控板待真机测试。
本批远端 CI 待跟踪。

## 2026-09-28 项目文件 → Viewer

完整重编译后的桌面 **498/498、无跳过**，字典 **851/851** 通过。真实桥按钮验证中文载荷位置、
缺失/不支持文件与预设拒绝、项目修订不变；独立 Python 控制台加载实际 VTK。
验证父目录存在结果清单时仍使用选定场文件、切换预设保留文件名，以及 Viewer 隐藏/不存在时的标签切换。
四项中英文 GL/Vulkan 文件面板截图已检查；本批 macOS/Windows CI 待跟踪。

## 2026-09-28 离线工作台演示

Python 基础/实际 VTK 两种路径 **2/2**，原生 Python → 项目/Viewer/布局交互与中英文 GL/Vulkan
截图 **5/5** 通过。截图目视确认实际三维场，独立统计核对 4913 个点及平均值/最大值。
检查输入副本、重开、修改跨表参数只更新公式而不重跑生成文件，以及原布局恢复。
示例不依赖 Runtime，不创建远程任务。`55373a1` 的 desktop **36410580845**、Runtime **36410580865**、
文档 **36410580930** 全部成功。桌面首轮的干净环境安装遇到 PyPI `python-dateutil` 索引连续超时，
同一提交重跑失败作业后通过；未修改依赖或放宽测试。原生 Windows 基础 CI 不含 VTK；新交互仍需真机测试。

## 2026-09-28 CSV/TSV 参数表

完整桌面 **489/489**、相关 Python **113/113** 通过。覆盖中文、多行引用、精确整数、JSON/布尔、
空值、整批失败、源文件/编辑预算、并发修订、目标竞争不覆盖、一次撤销重做和公式值导出/错误拒绝。
原生按钮通过真实桥验证导入、导出、撤销及重复输出拒绝；4 项 GL/Vulkan 中英文截图已检查，字典各 **846 项**。
当前 CSV 导出要求目标文件系统支持硬链接，未包含 FAT 等目标文件系统验收。
`f4bfbae` 的 desktop **36408907358**、Runtime **36408908042**、文档 **36408907835** 全部成功，
同时覆盖 Python 分析图 API，包含 Linux、macOS、Windows、打包及干净环境。

最近项目 `623fe2b` 的 desktop **36406870490** 全平台成功，文档 **36406870578** 成功。
Runtime **36406870548** 首轮仅 Windows Python 3.12 的旧示例生成子进程超时（20 秒）；已重跑失败作业，
未取得子进程堆栈，不将超时归因于最近项目功能或字体缓存。同一提交重跑失败作业后全部成功，未修改测试或生产代码。

## 2026-09-28 Python 分析图

Python 图/桥/控制台/Hub **65/65**、原生图/Viewer/脚本 **53/53** 通过。
真实独立 Python worker 编辑完整分析图，校验节点错误，计算表格和载荷，核验 blob 哈希及原始场探针数值。
阻塞图 worker 验证控制台中断与进程回收，排队中断不影响其他活动图；真实 loopback Hub + 节点验证
待审核结果保留、显式取消，以及中断等待后远端仍完成、原 eval ID 恢复且不重复创建操作。
本批远端 CI 待跟踪，不代表原生 Node Editor 或完整图版本持久化已交付。

Python Viewer `616bf3f` 的 desktop **36405264363** 全部成功，Runtime **36405264493**、
文档 **36405264372** 成功。最近项目 `623fe2b` 的远端 CI 待跟踪。

## 2026-09-28 最近项目

完整桌面 CTest **484/484**、Python 桥/脚本/最近项目/Viewer **52/52** 通过。
真实桥重启后列表保留而项目不自动打开；通过原生表格按钮重开同一 UUID，移除只清除历史。
检查目录缺失、项目替换、历史损坏和偏好文件写入失败，保留项目文件与会话。4 项中英文 GL/Vulkan
截图已目视检查，中英文字典各 **833 项**。本批远端 CI 待跟踪。

## 2026-09-28 Python Viewer

完整桌面 **478/478**，UI 能力协商调整后的脚本/项目/Viewer 子集 **44/44**，相关 Python **23/23** 通过。
实际独立 worker 控制本机原生 Viewer，检查图层/透明度、混合非法更新不产生部分修改、来源变更保护、
时间序列与播放、显式图求值、错误状态和自动求值开关。Linux 的合成扫描结果通过真实 VTK 图服务加载；
Windows 基础环境测试使用可移植载荷/序列，不能据此声称 Windows 的完整 VTK Python 环境已验收。
扫描 `show.py` 把已下载结果送入共享 Viewer。本批远端 CI 待跟踪。

HTTP 测试端点移除反向 DNS 查询后的 `7ebf746`：desktop **36403445288** 全平台通过，
Runtime **36403445272**、文档 **36403445317** 成功，覆盖前序原生运行面板和温度扫描示例。

## 2026-09-28 手动项目扫描示例

`examples/project_scan` 和运行/Python Runtime 回归 **19/19 通过**。真实独立 Python worker 创建两个
温度案例、冻结并上传程序和输入，准备后远端任务数仍为零；明确提交后由真实 Linux Runtime 执行。
下载 VTK/PNG/JSON，汇总平均值/最大值，重复收集保留两条任务和两条结果记录；修改本地结果后拒绝收集。
独立 VTK reader 验证 `17×17×17` 网格和标量数量。示例明确使用合成场，不是科学模型有效性验收。

格式 5 后端 `613bf6c` 的 desktop **36400084985**、Runtime **36400084994**、文档 **36400084958**
已全部成功。原生运行面板 `f8b7943` 的远端 CI 继续跟踪。

## 2026-09-28 原生运行面板

完整桌面 CTest **474/474 通过**；其中项目/Python 相关 **54 项**，包含分页运行表格、旧参数保护、
关闭重开，以及通过真实 Python 桥和跨平台 HTTP 模拟端点测试提交/刷新/取消按钮，确认只提交一次、
任务状态更新不推进表格修订。四项 GL/Vulkan 中英文运行面板截图已目视检查；中英文字典各 **829 项**。
Python 运行/项目桥 **20/20** 通过。HTTP 模拟不执行求解器，真实 Linux 执行仍由下节集成测试覆盖。
本批原生面板的远端 CI 待推送后跟踪。

## 2026-09-28 项目运行记录基础

格式 5 的 Python/桥/Runtime/Hub 相关回归 **144/144 通过**；最后 Hub 状态读取调整后运行专项
**10/10** 再次通过。覆盖冻结输入上传后执行、源参数变更标记、改名/撤销、公式错误、旧格式备份升级、
响应丢失后新会话恢复同一个 Runtime 任务、连接改指拒绝和 Hub 审核后的只读恢复。
完整桌面 CTest **468/468 通过**，包括升级到格式 5 和共享契约验证；本批尚无原生运行面板。

前序提交 `23773d2` 的 desktop run **36398208056**、Runtime **36398208012** 和文档 **36398208047**
全部成功，确认输入快照的 Windows 时间戳兼容和历史契约修正；格式 5 的远端 CI 待本批推送后跟踪。

## 2026-09-28：Runtime 固定输入哈希

- `input_hashes` 覆盖全部显式选中的输入；校验任务目录中的实际副本后才排队。
  验证哈希不匹配、复制后内容变化时永不启动程序，失败尝试保留原幂等键，旧请求的历史摘要不变。
  工作区后来改变不影响已接受任务的同键恢复；改变预期哈希不能复用旧键。
- 桌面 Python 实际上传/提交/下载通过该检查；直连和 Hub 不支持该能力时在提交前拒绝。
  模型、Runtime、监控事件、脚本、桥、Hub 与 control 相关测试 **80/80** 通过，远端 CI 待跟踪。
- 输入快照兼容修正另通过 Python **49/49** 与原生 **7/7** 专项；保留源变化检测和内容校验。

## 2026-09-28：不可变输入副本

- 格式 4 只追加清单、内容哈希去重及显式备份迁移；打开旧格式不会改变文件。
  覆盖原文件修改/删除、索引撤销、目录搬迁、相同内容复用、空文件、预算、复制中变化、并发修订冲突、
  清单损坏、对象损坏/缺失、符号链接和 FIFO 替换、数据库备份缺少对象，以及 CLI/真实 Python worker。
- Python 相关回归 **133/133**，最终脚本/快照子集 **32/32**，目录发布同步调整后存储专项 **15/15** 通过。
  原生 Project **48/48** 通过，真实桥按钮验证来源删除和索引撤销后仍能校验、关闭重开恢复历史及对象缺失报告。
  中英文 OpenGL/Vulkan 截图已目视检查，字典 **793 项**通过。
- 全量桌面 468 项中 **467 通过**；唯一失败是旧桥生命周期测试仍预期格式 3，改为格式 4 后单项复验通过。
  本批远端 CI 待跟踪。当前冻结选定文件内容，不声称已经冻结完整程序/参数环境或提供原子目录快照。
- `9686180` 的 Runtime **36396871397** 捕获历史 schema 缺少格式 4 枚举，以及 Windows Python 3.12
  的 stat/fstat ctime 语义差异。已补 `upgrade_format` / `capture_files` 历史契约并分开比较同类时间戳，
  保留身份、大小、mtime、源文件变化和 SHA-256 检查；新增跨 API 时间差异与桥历史读取回归，远端修正待验证。

## 2026-09-28：Python Runtime 操作覆盖

- 实际隔离 worker 通过保存连接创建工作区、上传、幂等提交、读取分块中文日志和下载结果；
  同键重复提交返回同一任务，改变请求得到冲突。中断等待后远端任务仍在，新 worker 可显式取消。
- Hub 待审核结果保留完整 action，等待助手遇到审核/中断/失败返回对应状态；超时和网络错误不重试或取消。
  新增 `task.logs` 返回 base64 字节与偏移，Python helper 解码为 bytes；旧 Hub 过长响应按 limit 截取并修正偏移。
- Python 脚本/桥/Runtime/Hub/SSH **69/69** 通过；完整构建后相关原生 schema/项目/Python **23/23** 通过。
  随 `f055275` 的 desktop **36394747178**、Runtime **36394747020**、文档 **36394747069** 全部通过；
  不代表完整批次运行记录、Viewer Python 控制或跨平台远程 Python 已实现。

## 2026-09-28：文件索引与外部编辑入口

- 文件索引复用格式 3 普通表格和撤销，未新增数据库格式。Python 相关回归 **125/125**，
  最终文件/桥/脚本子集 **35/35**：项目移动、内外路径、已缺失和未来输出、符号链接变化、
  跨平台外部位置、结构损坏、修订冲突、UUID 保持、撤销不改文件、CLI 与脚本 facade。
- 全量构建后完整桌面 **463/463 通过，无跳过**。新增原生测试通过真实桥登记/刷新/检查路径，
  以注入的应用启动器验证缺失文件不会触发打开、读操作不增加修订以及拖入/撤销的边界。
  中英文 Vulkan/OpenGL 文件面板截图已目视检查，783 项字典检查通过。
- Windows 的系统打开从占位实现改为 Unicode ShellExecuteEx；VSCode 使用转义后的标准文件 URL。
  本机验证 URL 构造和原生调用边界；`6056591` 的 macOS/Linux CI、Runtime 与文档通过。
  Windows 编译及 255/256 测试通过，文件打开用例因斜杠形式不同的字符串比较失败；
  已改为比较实际文件身份，修正后的 `f055275` desktop **36394747178 全部通过**；真实文件关联/VSCode 启动仍待验证。
  没有把默认程序打开写成应用内 Markdown/PDF 预览，也没有把元数据索引写成完整资源备份。

## 2026-09-28：持久撤销/重做与表格管理

- 格式 3 增加按编辑批次持久保存的行差异；格式 1/2 显式备份后升级，旧格式打开不迁移。
  覆盖完整撤销到空项目、按原顺序重做、关闭重开、单元格定义切换、跨表依赖恢复、删除/重建交换行序、
  并发撤销与编辑只有一个成功、失败保持重做栈、损坏日志拒绝覆盖，以及固定随机混合序列逐步往返。
- 原生表格提供撤销/重做、表格/字段改名和对象删除；测试使用真实桥验证持久重做、共享修订、
  删除后原 ID 恢复、名称和单元格及表/字段名称草稿冲突。Python facade、CLI 与桥使用相同操作。
- 本机全量桌面 **452/452 通过，无跳过**；随后新增的中英文 GL/Vulkan 管理面板 **4/4 通过**，
  截图已目视检查。最终 Project 标签 **36/36**、Python 项目/表达式/撤销/桥/脚本 **108/108** 通过；
  字典 **769 项**检查通过。
- 撤销不还原外部文件或运行中的模拟，升级前编辑没有可撤销的前值。
  `d0fd5f5` 的 desktop **36390818302**、Runtime **36390818350**、文档部署 **36390818365** 全部通过，
  同时验证 procfs 清理修正；前一 `dfd2c27` desktop 被后续推送自动取消。

## 2026-09-28：项目格式 2、引用与公式

- Python 项目/桥/脚本相关回归 **110 项通过**；最后缓存校验调整后项目/脚本子集 **87 项再次通过**。
  覆盖跨表稳定引用、重命名、删除/恢复来源、循环与下游错误、单位/类型/数值范围、非法 Python 语法拒绝、
  1,500 层依赖链/循环、只重算受影响单元格、损坏或旧版本缓存重建。
- 格式 1 保持可读写原有字面量；显式升级先生成并校验数据库备份。覆盖备份恢复、迁移失败回滚、
  并发升级、陈旧修订拒绝以及桥/CLI 同一语义；不会因为打开项目而自动升级。
- Linux 全量桌面构建后 **449/449 CTest 通过，无跳过**。最终绑定表格和错误颜色调整后，
  Project 标签 **29/29 再次通过**；其中真实 Python 桥验证公式编辑、依赖更新、冲突草稿、备份升级。
  中英文 Vulkan/OpenGL 公式编辑截图已生成并目视检查，字典 **759 项**检查通过。
- `d0b6c5c` 的 macOS/Windows、打包、Runtime CI 已通过；Linux 仅旧有超时测试的清理扫描发生
  `/proc` 读取竞态，`dfd2c27` 已修正并连续 12 次通过对应测试，远端修正结果继续跟踪。数据库备份不包含资源文件，
  未交付撤销、完整项目快照或模拟节点自动执行。

## 2026-09-28：原生 Python 与管理 SSH

- `7694ea3` 的 desktop CI [run 36382812292](https://github.com/sijintech/stk/actions/runs/36382812292)
  全部成功：macOS arm64/Metal、Windows/MSVC CPU、Linux GL/Vulkan、Linux 发布包和干净环境启动。
  Runtime/science 检查与文档部署也成功。此记录是 CI 验收，不替代用户实际输入法/完整交互验收。
- SSH 首版在 Linux 上完整重编译后 **442/442 CTest 通过，无跳过**，含 C++ → Python SSH
  配置契约及合成事件驱动的原生 Jobs 配置/断开/重连按钮测试；既有 GPU goldens 全部通过。
- `test_runtime_ssh.py` 与 Runtime/桥相关回归 **74 项通过**；补充失败候选、缺失客户端后，
  最终 SSH 专项 **16 项通过**。临时 sshd 使用测试目录中的独立密钥、配置和 known_hosts，
  只监听本机高端口，不修改用户 SSH 配置、不访问外部服务器。
- 真实 OpenSSH 访问 HTTP 与实际 Runtime：上传输入、提交一次、断开隧道后任务完成、
  重连下载字节一致；未知 host key 拒绝且不发送 token。另测父管道 EOF 进程清理、并发隧道复用、
  进程退出后重连、手动断开阻止隐式重连、端口被其他进程抢占、请求响应丢失不自动重放。
- Linux CI 安装 sshd 并要求真实 SSH 测试不可跳过；Windows 运行模拟转发与生命周期测试，
  macOS/Windows 原生 CI 要求 SSH 配置契约实际执行。desktop run **36386610173** 全部通过；
  Windows 守护进程清理断言改为限时等待 PID 消失后，Runtime run **36387729994** 全部通过。

配置与限制见 [SSH 指南](ssh.md)。真实异机网络、跳板机和 Windows/macOS OpenSSH 仍需站点验收。

## 初始工程版本验收

在 Linux / Python 3.12.13 中构建 wheel 与 sdist。新建独立虚拟环境，先只安装
核心 wheel；确认没有 PySide6 和 NumPy，实际启动独立 API / supervisor，完成
任务提交、执行、日志读取和 SHA-256 校验下载。

随后在该环境安装最终 wheel 的 science、desktop、mcp、test 可选组件，将测试与
科学示例复制到源码目录以外执行。确认导入路径来自新环境的 `site-packages`，
而非可编辑源码安装。

结果：**44 passed**（19.83 秒）；`pip check` 通过，`git diff --check` 通过。
唯一警告来自已有 pyqode 使用已弃用的 `sre_constants`。

桌面采用 Qt offscreen；测试容器缺少的 EGL / OpenGL loader 解压至临时目录使用。
启动任务工作台不会创建 VTK OpenGL 上下文。三维结果的完整交互仍需在具备图形
驱动的真实桌面验证；本次验证了 VTK 文件数据及桌面下载路径。

## 本轮续开发：部署诊断与站点报告

同日补齐 `suan server doctor`、`suan connect check` 和持久站点验收报告。
诊断覆盖本机配置、目录访问、SQLite、worker 环境、调度器命令及 API／supervisor；
失败报告仍为可解析的 JSON，退出码为 1，报告不输出连接令牌。

科学示例现在在提交前保存完整 TaskSpec 和幂等键，在关键步骤保存状态与证据。
等待超时或提交响应丢失时保留可查询／重试的信息。结果校验覆盖 DAT／VTK 的
完整场数据及 PNG 解码，避免只有 summary.json 正确却误报通过。
每次运行保存独立的 `acceptance-<run_id>.json`，包含实际命令、源文件校验值、
客户端和计算环境、输入／结果 manifest、日志片段及误差。

Linux / Python 3.12.13 验证结果：

- 源码环境完整回归：**67 passed**，25.40 秒，包含桌面 offscreen 和 MCP。
- wheel／sdist 构建成功，安装后的 `pip check` 通过。
- 从 sdist 提取测试与示例，在源码目录之外运行；确认新模块导入自独立环境
  `site-packages`。安装包完整回归：**67 passed**，25.92 秒。
- 新增及受影响测试共 25 项；包含未初始化／损坏配置、目录探针清理、网络磁盘识别、
  损坏数据库、Python 超时、缺失调度器命令、认证失败、服务停止、提交响应丢失、
  等待超时保留任务、错误场数据及 NaN 摘要拒绝。

两次完整回归均只有原有 pyqode 的 `sre_constants` 弃用警告。
本轮没有进行真实集群、外部 SSH 或独立桌面安装器验收；新增检查的通过状态
不改变下方站点验收边界。

## 2026-09-24 方向调整

用户确定的方向：

1. STK 独立于 Synorder 发展；桌面主线为 STK 自有的 Blender 原生工作台（`blender/`、
   `suan/blender_client`、`suan-control`、`suan-node` 与 Runtime）。
2. Synorder 集成推迟；`plugins/synorder` 与 `suan-synorder-node` 保留为可选。
3. MuPRO 作业的排队由 STK Runtime 负责。
4. 首个集群为并行云（Paratera），账号尚未开通。
5. 服务器 Runtime 仅支持 Linux；Windows 只作客户端。

据此完成的改动：

- Runtime：MPI 布局 `ranks`／`threads_per_rank`、argv 占位符 `{ranks}`／`{threads_per_rank}`／
  `{nodes}`、OMP／MKL 线程设置及 Slurm／PBS 映射；站点配置 `scheduler` 与不提交作业的 Slurm
  doctor 探针；本机 worker 启动失败不再占住并发名额；`/health` 增加 `resources`、`argv_tokens`，
  HTTP API 仍为 v1，已有任务的幂等键不变。
- 平台：`suan server init/start`、`suan-control init/serve`、`suan-node pair/run` 在非 Linux 上
  拒绝运行；`suan` 在 cp1252 控制台改用 UTF-8 输出；新增 pytest `server` 标记，CI 在 Linux 运行
  全部非桌面测试，在 Windows 只运行客户端测试与入口冒烟。
- MuPRO：`suan mupro submit/result/verify`、计算节点 `python -m suan.mupro run/verify/check`、
  逐次校验 `stk-mupro-1` 与本机多 rank 保护，见 [MuPRO 指南](runtime-mupro.md)。
- 工作台：控制模板 `muferro-example` 与 `--template`／`--template-file`，启动器 `--template`，
  按 MuPRO 帧名确定场名与时间步；`suan-workbench` 改为 STK 工作台启动器，Synorder 宿主改用
  `python -m suan.workbench`。
- 并行云站点清单见 [并行云站点验收清单](runtime-paratera.md)，尚未执行。

Linux / Python 3.12.14，`.[server,science,control,visualization,test]` 环境，
`python -m pytest -p no:cacheprovider -m "not desktop"`：**303 passed，2 skipped**，约 45 秒；
Python 3.10.21 同一命令结果相同。
跳过项为可选 MCP 组件未安装，以及需要 `STK_TEST_MUPRO_PREFIX` 的真实 muFerro 测试。
MuPRO 测试使用模拟的 muFerro、mpiexec 和 srun；Slurm／PBS 为模拟命令；非 Linux 行为通过修改
`sys.platform` 的测试检查，尚未在真实 Windows 或 CI 上运行。本轮没有运行多 rank MPI。

### MuPRO 本机验收

2026-09-24 04:09–04:13（UTC+8），r730xd 测试主机（`mnemora-test`，Linux x86_64，48 个逻辑 CPU），
Python 3.12.14。STK 为 `feature/independent-runtime-mupro` 分支上基于 217bd86 的未提交工作树，
以非可编辑方式安装到临时 venv。按 [MuPRO 指南](runtime-mupro.md) 的“本机验收流程”执行，
结果：**通过**，完成两次真实 muFerro 单 rank 运行。逐步记录见该指南的“结果”。

- 程序：Release 构建 muFerro（muprosdk b2adf41，SHA-256
  `c0c1f3454f5ff5384c76e70455b0441bb8ebeeb40b711b2360f2f0f1d099683a`），Release 许可检查通过，
  没有改用 muFerrod。两次运行都是 1 rank、1 线程、`launcher` 为 `none` 的 MPI singleton，
  没有启动 mpiexec 或 hydra。
- 耗时：CLI 提交 `--wait` 5.24 秒（求解器 3.02 秒）；模板任务从派发到结束 4.57 秒（求解器 2.83 秒）；
  无界面视图检查 0.89 秒；全程 279.6 秒，其中 pip 安装 246 秒。
- 校验：两次均为 `stk-mupro-1` `passed`（完成 101 步，101 行有限能量，101 条进度，30 个 16³ 场帧），
  `qoi.total_energy` 均为 −727.9144455（step 101），与不经 STK 直接运行 muFerro 的 1 rank 参考值相同。任务为
  `b19c4c0fdbbd41708acf4373e6a3f383`（CLI）与 `89213f88715844a7941a3f7601711a0c`（`muferro-example` 模板）。
- 网络：Runtime 只监听 127.0.0.1；运行期间本次运行没有其他监听。
- 幂等：同一 `--key` 返回同一任务 ID，没有新的运行目录。
- 视图：节点代理生成的 slice、等值面和向量箭头可用，slice 通过 `validate_scene`；`view.probe`
  与直接解析 DAT 的值完全相同；`energy_out.dat` 按预期被拒绝。
- 模板链路：C++ 按钮的等价命令按 `client.json` 换成 `muferro-example`，经节点代理在真实 Runtime 上
  运行成功，桥接写出的 `scene.json` 通过 `validate_scene`。
- 清理：Runtime 已停止，没有残留进程或套接字；muprosdk 工作树与许可文件元数据前后一致；
  `$A/shared` 为 31M（每次运行约 16 MB）。
- 发现两个小问题：`muferro-example` 模板没有声明 `ranks`／`threads_per_rank`，模板运行在 Runtime
  `environment.json` 中的 `MKL_NUM_THREADS` 为 null（求解器实际为 1）；以 `--port 0` 初始化时，
  停止后 `status` 的 `url` 显示端口 0。验收后均已修复：模板改为 1 rank、每 rank 1 线程，停止后
  `url` 为 `null`。

本次没有覆盖多 rank MPI、真实集群（含并行云）以及 GPU／Blender C++ 界面构建。

## 2026-09-25 里程碑 1：节点图可视化

内容：数据格式、图、渲染载荷与监控事件规范（`docs/specs/`），无界面图求值器与缓存，muFerro／SimViz
节点集与预设，离屏渲染与二维图，控制服务 blob 存储与图操作，网页“图谱”模式，MCP 工具与技能，见
[可视化工作流](visualization.md) 与 [控制服务指南](hub.md)。

自动测试：Linux，Python 3.12.14 与 3.10.21，`python -m pytest -p no:cacheprovider -m "not desktop"`，
离屏渲染子进程指向 Kitware `vtk-osmesa` 环境（`STK_RENDER_PYTHON`）：**889 passed，12 skipped**；
不设渲染子进程时渲染测试跳过。网页 `npm ci && npm run build` 通过，另有无头 Chromium 渲染与交互检查。
128³ 假 muFerro 帧上 `muferro-domains` 冷启动约 3.7 秒，仅改相机约 0.3 秒（不含 PNG）。

真实验收：2026-09-25 03:45–03:49（UTC+8，全程 204 秒），r730xd 测试主机，分支 `feature/m1-graph-viz`
提交 445e885 以非可编辑方式安装到临时 venv；Runtime、控制服务（含构建后的网页）与节点代理都只监听
127.0.0.1，单 rank。

- 经控制服务模板提交真实 Release muFerro（SDK 示例，16³，101 步），自动执行；校验 `stk-mupro-1`
  通过，总能量 −727.9144455（step 101），与 2026-09-24 的直接运行一致。
- 监控事件：经控制服务 `task.events` 读取 142 条（`metric.declare` 5、`metrics` 101、`progress` 2、
  `frame` 30 等），全部在 Runtime 标记任务结束之前到达。本例求解只有约 2.5 秒，帧事件在求解器退出时发布。
- `graph.evaluate`（`muferro-domains`，profile `web`）自动执行，所有 blob 经 sha256 校验，载荷通过
  `suan.render.payload.decode`；标签与对原始 DAT 的独立分类逐点一致，分数和为 1，能量图数据与
  `energy_out.dat` 101 行相同，离屏 PNG 1600×1200。耗时与缓存：首次 3.42 秒（13 个节点全部计算）；
  仅改视角 1.06 秒（只重算 camera、scene、png）；换步 1.48 秒；相同请求 0.34 秒（全部命中）；
  改阈值 1.38 秒（帧读取命中）。本例为单一 T[100] 畴；提高阈值后为 −1：2885、1：1211。
- 网页（无头 Chromium，127.0.0.1）：“图谱”模式运行 `muferro-domains` 约 1.0 秒显示，含图层、图例、
  分数表与能量图；手机宽度 390 px 无横向溢出；`muferro-polarization-glyphs` 显示箭头与取向图例。
  在畴表面上点击探针，返回值与原始 `Polar.00000100.dat` 的三线性插值完全一致（差 0.0）。
- MCP `graph_render` 返回的 PNG 与控制服务首次求值的 PNG 字节一致。
- 清理：各服务与进程退出，端口关闭；仓库与 muprosdk 工作树、许可文件元数据前后一致。脚本的
  `/dev/shm` 检查报出新条目，经核对属于本机同时运行的 GitHub Actions（muprosdk CI）进程，不属于本次运行。
- 第一次验收（2026-09-25 02:50，提交 626bcd1）发现两个问题并已修复后重验：畴表面平滑后超出网格
  约 0.66 格，点击表面时探针被拒且遮住外框（现已把表面顶点限制在网格内）；控制服务按字母顺序重排
  表格列（现有序列名 `column_names`，且保存结果时保持键顺序）。

未覆盖：Blender 端显示与节点编辑器、真实集群、多 rank、GPU、Windows 客户端实机、控制服务 blob 保留与回收。

## 2026-09-25 桌面里程碑 D1：自有引擎桌面端

内容：自有 C++ 桌面程序（`desktop/`，Blender GHOST + GPU + BLF）的任务、传输、日志编辑器（WP9）与
查看器、属性、探针编辑器（WP10），经 Python 桥（`suan.desktop_bridge`）连接控制服务与 Runtime，见
[桌面程序说明](../desktop/README.md) 与对照清单 `desktop/docs/parity-*.md`。

真实验收：2026-09-25 21:11–21:32（UTC+8），r730xd 测试主机（`mnemora-test`）。分支
`feature/desktop-engine` 提交 dedae97；验收中发现的查看器问题已修复为 19f94ec（见下文问题 1），
任务部分在 dedae97 的构建上运行，查看器部分在含 19f94ec 的构建上运行。STK 以非可编辑方式安装到临时
venv（Python 3.12.14，pip 74 秒），桥使用该安装而不是源码树；桌面程序在 `~/opt/stk-build/d1acc`
以 RelWithDebInfo 构建（约 3.6 分钟，用户 sysroot）。Runtime（并发 1）、控制服务
（`suan-control serve --review-policy not-self --template muferro-example`）与节点代理都只监听
127.0.0.1；桌面程序用 `suan-control pair --role client --profile desktop` 的配对码，经“配对控制服务”
（`connections.pair_hub`）配对，配对码只存于 0600 文件，未打印。

驱动方式：临时驱动程序（草稿目录，不入库）按 `stk-desktop` 的 `run_gui` 装配应用外壳、默认布局、
任务状态钩子与真实 Python 桥，像 `desktop/tests/app/*_live.cc` 一样合成鼠标、键盘与输入法事件
（点击“提交任务”“在查看器中打开”、任务名输入框，在视图中点击拾取）；显示服务器为
`desktop/tests/wm/run_with_display.py` 启动的私有 weston（headless，pixman，自带 `XDG_RUNTIME_DIR`）
与 Xvfb（`-nolisten tcp`），只用 unix 套接字。weston 上用 Vulkan（lavapipe），Xvfb 上用 OpenGL（llvmpipe）。
结果：**通过**（问题 1 修复后）。

- 连接：配对后 `hub.policy` 报告设备类型 `desktop`、审核策略 `not-self`、桌面自动执行上限 256 MiB；
  节点在线，模板列表含 `muferro-example`。
- 任务（weston，Wayland）：点击“提交任务”提交 `muferro-example` 模板，自动执行，0.46 秒登记任务；
  任务表依次显示运行中、成功（2 秒一次的快照共 4 个）；日志视图收到 93 行，第一行比任务结束的快照早
  7.3 秒到达（运行期间）；监控事件 142 条（帧 30、指标 5），校验 `passed`。从登记到完成 4.3 秒
  （Runtime 记录），其中 muFerro 约 3.2 秒。
- 下载：制品 36 个，共 15.9 MB。“另存为” `energy_out.dat`（11220 字节）0.05 秒完成，桥的 sha256 与磁盘
  复核都通过，文件 sha256 与 Runtime 运行目录中的原文件、制品列表中的值三者一致（`1d8c3586…`），101 行，
  末行总能量 −727.9144455。整个运行目录（36 个文件）下载到本地目录用时 1.8 秒，逐个与 Runtime 的
  `work` 目录逐字节一致，供下面的本地求值使用。
- 校验：两次模板运行的 `suan mupro result` 均为 `stk-mupro-1` `passed`，总能量 −727.9144455（step 101），
  与 2026-09-24 与 M1 的记录一致；16³、101 步、30 个场帧，1 rank、1 线程、`launcher` 为 `none`；
  muFerro 程序 SHA-256 仍为 `c0c1f345…`（muprosdk 已更新到 0d6e021，Release 安装未变）。
- 自定义命令与复核：在任务名输入框中用输入法事件输入“铁电畴 验收 D1”（两段拼音预编辑，内联显示后提交，
  再用按键输入“ D1”），提交自定义命令后进入复核（“新命令或模板变更：请检查完整参数后批准执行。”）。
  本机检查请求后自行批准被控制服务拒绝（403），界面按 `review_policy` 显示“控制服务的审核策略（not-self）
  不允许本设备批准该操作，请由控制服务所有者批准。”；所有者令牌批准后，桌面程序以同一幂等键重发，
  0.52 秒得到任务并成功运行。Runtime 任务记录的 `spec.name` 为“铁电畴 验收 D1”。
- 关闭不停止任务：第二次模板运行处于运行中时关闭窗口，桥收到 EOF；该任务在窗口关闭后 0.55 秒完成，
  `succeeded`，`cancel_requested` 为 false，校验通过、能量相同。本例求解只有约 3 秒，所以关闭距完成很近。
  每次退出都没有 guardedalloc 泄漏，外壳已丢弃关闭窗口的屏幕。
- 查看器（weston，冷缓存：清空节点图缓存与桥的 blob、图缓存，关闭相邻步预取）：点击“在查看器中打开”，
  `muferro-domains` 经控制服务**自动执行、无复核**，求值 1.63 秒（10 个节点，数据节点 4 个），打开到画面
  1.78 秒，3068 个三角形、78 KiB。导出 PNG（1600×1200，彩色畴占 40%）0.30 秒。
- 探针：视图中心落在外框上，第二个候选点拾取到畴表面（`surface_layer`，单元 2143），经 `view.probe`
  0.31 秒返回：位置 (14.970, 0.0591, 12.428)，值 (0.6020874395, 0.0020565348, 0.0094302832)，与独立解析原始
  `Polar.00000100.dat` 的三线性插值完全一致（差 0.0）；探针编辑器显示 0.602087。
- 客户端阶段参数：`view` 由 iso 改为 +x，只重算 `camera`、`scene`，**数据节点 0 个**，0.16 秒，视图 65% 的
  像素改变。
- 换步（共 0、100 两步）：未缓存的 100→0 经控制服务求值 589 毫秒（重算 7 个节点，3 个命中）；回到 100
  和再到 0 用查看器缓存，0.4 与 1.7 毫秒（到下一帧约 40 毫秒）。开启预取的另一轮中，三次换步都已预取，
  0.3–0.5 毫秒。
- 本地求值：打开下载到本地的运行目录（本地模式），`muferro-domains` 0.76 秒（10 个节点）；在同一位置
  拾取畴表面，本地探针值与经控制服务的值及原始 DAT 三线性插值都一致（差 0.0）。
- X11（Xvfb，OpenGL）：查看器全流程同样通过（两处探针差 0.0，PNG 1600×1200）；输入法事件输入
  “畴壁 Xvfb 验收”（拼音、按键、拼音混合）的自定义命令经所有者批准后运行，Runtime 记录中名称一致。
- 回归：修复后 `ctest -L "app|jobs"` 72 项全部通过（`STK_BRIDGE_TEST_PYTHON` 指向验收 venv，无跳过）。
- 网络与清理：本次只有 Runtime 127.0.0.1:28686 和控制服务 127.0.0.1:22883 两个服务监听，0.5 秒采样
  （1899 次）中本次进程的监听另有回归测试临时 Runtime 的 127.0.0.1:38425；显示服务器不监听 TCP。结束后
  没有残留进程或监听，两个端口关闭；仓库工作树、muprosdk 工作树与 HEAD、Release 可执行文件和许可文件的
  元数据前后一致。`/dev/shm` 新增 770 个 `__KMP_REGISTERED_LIB_*`，没有一个属于本次运行的进程 PID，是本机
  同时运行的其他 Intel OpenMP 作业（期间还看到其他用户的 muPREDICT／hydra 监听 0.0.0.0:40915）。

发现的问题：

1. **已修复（19f94ec）**：查看器经控制服务求值时没有设置 `budget.max_output_bytes`，控制服务按 desktop
   配置默认的 2 GiB 估计传输量，桌面自动执行不生效：`graph.evaluate` 进入复核（“预计传输超过桌面自动执行
   上限 256 MiB（请设置 budget.max_output_bytes）”），查看器显示“计算超过自动执行额度，正在等待复核；
   批准后请重新计算”。桥规范 §7.1 要求应用按 `hub.policy` 设置；现在 `ViewerState` 对控制服务来源按
   任务编辑器当前连接的策略设置该上限。
2. **未修复**：经控制服务新建工作区后，新工作区不会出现或被选中。`JobsState::create_workspace` 的回调只
   调用一次 `refresh_workspaces()`，而经控制服务的 `workspace.list` 读取节点心跳快照（每 3 秒一次），此时还
   没有新工作区；`apply_workspaces` 在首选工作区不在列表中时改选列表中的第一个。第一次尝试（此前没有
   工作区）60 秒内都没有可选的工作区；正式运行中新建的同名 “d1-accept” 没有被选中，界面改选了上一次
   尝试建立的工作区，之后的任务都提交到了旧工作区，没有提示。需要手动“刷新”。
3. **次要**：任务表“提交时间”直接截取 Runtime 的 UTC 时间字符串（`short_time`），显示 13:19 而本地为
   21:19，也没有时区标记；探针编辑器的插值说明显示为“原始点数据的trilinear插值”（方法名未本地化）。
4. **环境**：weston headless（pixman）上 OpenGL 后端无法启动（`EGL_BAD_MATCH` 后 Wayland 连接断开），
   与 ctest 在 weston 上用 Vulkan 一致；窗口请求 1440×900 而 kiosk 输出为 1280×800 时，程序按请求尺寸
   提交缓冲区而不是按全屏 configure 的尺寸，weston 断开连接，改用 1280×800 后正常。

未覆盖：交互式输入法（weston 不实现 text-input-v3，以上是合成的预编辑／提交事件；GNOME + ibus、
KDE + fcitx5 需人工验收）、macOS 交互（Metal、拼音输入法、Retina）、Windows 客户端实机运行、
真实集群（并行云）、多 rank MPI、真实 GNOME 会话的客户端装饰，以及经 HTTPS 入口访问控制服务。

<a id="desktop-mac-windows-smoke"></a>

## 2026-09-28 补充记录：macOS / Windows 基本启动

来源：所有者在本轮对话反馈“我在 windows 和 mac 上都测试了，能够正常打开界面，看到 3d 渲染”。
据此记录两个平台的真实窗口启动与基本 3D 显示通过；[快速启动脚本](../desktop/QUICKSTART.md)已在主线提供。
具体测试提交、系统版本、硬件、操作步骤和日志未随反馈提供，本条属于用户报告的验收证据。

这补充了 D1 记录中的平台启动覆盖；不代表 macOS / Windows 的输入法、Retina/缩放、全部交互、
大数据、结果导出或安装包已经验收，也不表示此前 CI 失败已修复。后续范围见[开发计划](development-plan.md)。

## 2026-09-28：P0 测试稳定性与 P1 项目存储基础

新增 `suan/project` 和 `suan project create/show/apply/history`，实现独立于 Runtime 的 SQLite 项目存储。
支持稳定 UUID、类型化字面量表格、批次事务、修订冲突与编辑历史；使用范围见[项目存储指南](project.md)。
当前尚未接入桌面项目生命周期，也未实现引用/公式、撤销、资源快照或模拟执行。

本机 Linux 验证：

- 项目、打包、图 worker 与实时图缓存相关测试共 **55 passed，1 skipped**；跳过的是未安装的 MCP 可选组件。
  其中项目测试 28 项，覆盖重开、改名后稳定身份、类型错误整批回滚、并发修订冲突、跨表外键、
  拒绝覆盖已有数据库，以及拒绝未知/损坏/不支持格式的项目。
- 快速启动脚本测试 **13 passed，1 skipped**；Windows PowerShell 集成项在 Linux 跳过。
- 重编译 `stk_app_viewer_gpu_tests`，`app_viewer_python_vulkan` 与 `app_viewer_python_opengl` 均通过。
- 构建 sdist 并从中构建 wheel；在无 NumPy/VTK/Qt/MCP 的全新虚拟环境安装 wheel，
  从源码目录外完成中文/空格路径项目创建、编辑、重开、历史查询与陈旧修订拒绝；未初始化 Runtime。

Windows 退出测试现在处理 `is_running()` 与 `status()` 之间进程退出的情况，保留退出超时断言。
查看器阶段缓存测试先关闭邻帧预取，再分别验证阶段缓存和预取换步：活动预取可能在原生计算中被硬取消，
导致 worker 重启及内存缓存丢失，不能将这一情况等同于客户端参数使数据失效。
本次修改没有放宽阶段缓存断言，也没有改变生产取消策略；原有 worker 取消/重启测试继续通过。
本条是 Linux 本地验证，修改后 macOS Metal 与 Windows 实际结果仍以对应提交 CI/真机记录为准。

## 2026-09-28：本机项目桥接

桌面桥 v1 的新增项目接口和 C++ 客户端使用同一修订式存储服务；协议见 §13。
本机 Linux 验证：

- `test_project.py` 与 `test_desktop_bridge*.py` 共 **72 passed**，包含进程重启后句柄失效、
  关闭与已接受编辑串行、外部修改冲突、未知格式错误码和数据库被替换后的身份检查。
- `stk-bridge-tests` 编译通过。`bridge` 标签首次 60 项中 59 项通过（包括 Vulkan/OpenGL 查看器），
  新增项目测试的断言误将 JSON 对象成员顺序作为差异；改为语义比较后该测试通过。
  另增并通过跨平台 CPU schema/类型测试，覆盖 Windows 绝对路径和 64 位修订。
- 上一存储基础提交 `b73c254` 的桌面 CI 已通过 Linux、macOS、Windows（GitHub run 36359876426）；
  本次新增接口的跨平台结果需等待本次提交的 CI。本条不代表原生项目编辑器已交付。
- 文档站构建的既有失败另行跟踪：run 36374828915 使用 Node 18，Astro 语言服务依赖加载出现
  `ERR_REQUIRE_ESM`；运行时/科学工作流检查通过。不能将仓库全部 CI 记为通过。

## 2026-09-28：原生项目表格首版

新增共享 `ProjectState`、类型化表格模型和“文件 → 项目表格”入口。
界面可创建/打开项目、添加表/字段/记录、编辑字面量、保存后关闭重开。
桥重启按目录和 UUID 恢复；旧修订草稿不会覆盖外部修改。

本机 Linux 验证：

- 构建 `stk-desktop`、`stk-project-tests`、`stk-project-render`、`stk_wm_tests` 通过。
- 最终相关 CTest **31/31 通过**：9 项项目模型/界面/真实 Python 桥测试，
  4 项真实项目桥 → 原生 GPU 截图（中/英文 × Vulkan/OpenGL），18 项应用外壳回归。
  另一次布局回归中的 25 项通用布局通过；最初的 Jobs 布局目标未重新链接，后续 CI 暴露的差异见下条。
- 目视检查中英文截图，确认字段、单位、行选择、单元格编辑区和保存按钮显示正常；
  截图由 `stk-project-render` 生成在构建目录 `tests/app/out/project_*.png`，不是手工画的设计稿。
- 中英文字典各 695 项，`check_i18n.py` 通过；本次尚无 macOS/Windows 真机交互结论。
- 前一桥接提交 `b1e2724` 的全部桌面 CI 已通过（run 36376573973），包含两平台构建及 Linux 包冒烟。

本版共享表格支持基础字面量，不包含引用/表达式、删除、批量粘贴、富内容插件、AI 或 Python 控制台。
完整程序重启后需手动打开项目；编辑器内未保存草稿不写入数据库。测试步骤见[项目指南](project.md)。

## 2026-09-28：英文编辑器标签回归修正

`c537d55` 的 CI 显示，英文 `Project tables` 比原有最长编辑器名更宽，导致所有区域的编辑器下拉框
变宽，使 5 个 Linux 英文布局快照和 3 个 macOS 英文布局快照失败。项目功能测试通过。
英文短标签改为 `Project`，中文仍为“项目表格”；不更新旧快照来掩盖其他区域的布局变化。

修正后本机重新构建全部桌面目标，完整 CTest **427/427 通过、无跳过**，包含此前失败的默认外壳、
Jobs、Properties 英文布局，真实 Python 桥、Vulkan/OpenGL、X11/Wayland 和打包检查。
中英文字典检查通过。macOS/Windows 修正后的结果继续跟踪对应 CI。

## 覆盖范围

2026-09-28 原生 Python 面板：全量重编译后完整桌面 CTest **440/440 通过、无跳过**。
新增 5 项 `ScriptPython` 使用真实独立 worker 验证布局拆分/恢复、非法布局原子拒绝、当前项目修订共享、
中断/重启不重放、过期客户端的排队操作不执行、多行按钮/快捷键和恢复/拖入不自动执行。
4 项 `python_render_*` 通过 Vulkan/OpenGL 生成中英文截图，已目视检查输出、代码缩进和控件位置。
多行输入覆盖 UTF-8 选区、跨行导航、CRLF 粘贴、撤销、IME caret、滚动和提交；最终 Ctrl+Tab 焦点处理
变更后相关 TextArea/TextEdit/TextField **11/11 再次通过**。中英文字典各 719 项，检查通过。
Python 文件语义回归 **8/8 通过**（含 main guard、同目录导入、argv 和 cwd）。

跨平台状态：后端提交 `4d3b762` 的 run 36380377730 在 Linux/macOS/打包通过，Windows **238 项 CPU
测试通过**，但必跑检查使用相对 JUnit 路径而失败。改为 PowerShell `Join-Path $PWD` 的绝对路径；
新原生面板的 macOS/Windows CI 与真机交互结论仍待后续验证，不能用 Linux 截图替代。

2026-09-28 Python 后端：`test_desktop_scripts.py`、`test_desktop_graph_worker.py`、
`test_desktop_bridge_projects.py`、`test_desktop_bridge.py` 共 **52 项通过**；包含真实独立 worker 的
多行/文件执行、变量保留、输出环截断、协议隔离、项目冲突和通知、中断子进程树、崩溃恢复、
反向请求会话匹配/超时/取消。重新构建 `stk-bridge-tests` 后，相关 Schema/Types/Retry CTest
**13/13 通过**，验证 C++ 也拒绝双重源码入口、重复能力和同时携带结果/错误的回复。
这是后端与协议验收；尚不表示原生控制台交互或跨平台真机验收已完成。

2026-09-28 传输恢复补充：Runtime CI run 36378576449 暴露失败通知与 worker 退出之间的窗口。
`resume` 现在在管理锁外等待终态 worker 收尾，然后在锁内重新读取状态；同时到达的恢复请求
不会启动两个 worker，活动/已完成的传输仍保持幂等。收尾超过 5 秒返回可重试 `busy`。
本机 `test_desktop_transfer_lifecycle.py`、`test_hub_desktop_bridge.py` 和
`test_desktop_bridge_runtime.py` 共 **23 项通过**；新增测试用事件门控制时序，不依赖 sleep。

| 验收项 | 证据 |
|---|---|
| API 与 supervisor 分别重启，计算继续 | `test_deployment.py` 实际启动独立进程，检查 worker 身份与日志无重复 |
| 输入隔离、幂等提交、并发上限、取消 | `test_runtime.py` 通过 HTTP 提交实际 Python 进程 |
| 断点上传下载、校验失败、路径边界 | 中断后的字节偏移、SHA-256、符号链接与越界路径检查 |
| 程序失败、缺少结果、超时、内存超限 | 实际失败进程与资源限制触发 |
| worker 丢失与外部终止信号 | 保留活动程序的待核实状态，可取消；外部信号不误报用户取消 |
| PBS / Slurm 状态与不确定提交 | 模拟命令协议；真实运行生成的 job.sh、worker 和程序；不重复派发 |
| 调度器不可用、资源映射、历史查询 | 排队／失败／取消／待核实、跨日期查询与每节点资源参数检查 |
| 确定性参数扫描完整流程 | `examples/runtime` 的两组输入生成、计算、均值与最大值校验、PNG / VTK 下载 |
| 科学格式与无窗口预览 | DAT / NPY / VTK 往返；独立 VTK reader 校验坐标顺序；Agg PNG |
| 桌面远程流程 | Qt 界面通过保存的 HTTP 连接配置上传、提交、读日志、下载 |
| MCP 与 CLI 使用同一任务 | MCP 创建／提交／查询，CLI 读取同一成功记录 |
| 旧桌面和包入口 | 从非项目目录创建工作台；科学模块、GUI 资源、旧 CLI 组在 wheel 中可用 |
| 部署与连接诊断 | `test_diagnostics.py`、`test_deployment.py`：配置、磁盘、数据库、Python、命令、API 认证和 supervisor |
| 验收报告与失败证据 | `test_acceptance.py`、`test_deployment.py`：提交前保存幂等键、超时保留任务、完整场校验与安装包案例 |

## 尚需站点验收

- 真实 PBS / Slurm 集群（首个站点为并行云，账号待开通）、集群上的 MuPRO 可执行程序与许可、
  多 rank MPI / module 环境、共享文件系统、队列和站点资源策略；本次调度器测试为协议模拟，
  不是实际集群性能验证。MuPRO 目前只在本机完成单 rank 验收（见上）。
- 真实 SSH 网络断线／重连；本次已验证客户端重建和服务端任务寿命独立，
  未对外部服务器执行 SSH 测试。
- Windows / macOS 客户端完整交互、输入法与分发验收；基本窗口启动和 3D 显示已有上述用户反馈。
  服务器端仍只支持 Linux；此前 Linux 自动验收不能替代客户端真机完整验收。
- PyInstaller 冻结桌面二进制的多进程启动与 Python 解释器分发；当前验收发布物
  为 Python wheel / sdist，未发布到 PyPI 或创建远程 release。

远程 Python 会话、远程实时三维渲染和团队权限属于后续阶段。

安装、API、SSH 与真实集群验收命令见 [runtime 使用指南](runtime.md)。
