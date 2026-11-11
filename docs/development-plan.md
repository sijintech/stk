# STK 开发计划

## 2026-11-11 03:21 UTC · 双语首个任务指南与远端 Runtime 终态

`a1f12980` 集成 Claude 独立工作树的两份用户指南，并对照桌面控件、Web 表单和最终任务目标检查修订措辞。中英文覆盖创建工作区、默认展开、明确提交、草稿及目标不一致提示。Root 以 Node 22.23.3 运行 Astro 检查和生产构建，7 个文件零诊断，生成 38 页。两个生成页面的实际文本和本地快速上手、旧版指南路径已核对。暂存扫描零发现。证据在外部 `root-delivery-20261111-156/user-guide/render-receipt.json`。

远端 `abdc57f7` 的 Runtime `42948501059` 于 03:15:40 UTC 结束，12/13。唯一失败为 Linux Python 3.12 的既有 PET 测试，6914 通过、149 跳过、4 deselected。测试已经通过协调器一秒预算断言，随后在 `tests/test_pet_study.py:618` 读子工作流时，桥接 `project.workflow_runs.get` 请求 203 在 60 秒内无回执。上个发布头对应 Linux 3.12 通过，相关 Python 源码无差异。Root Python 3.12.14 将原用例独立运行八次，8/8，保留原预算与超时，额外取证继续。Linux 3.11、3.14 和两项 Windows Python 作业通过。外部收据为 `root-delivery-20261111-156/pet-timeout` 和 `root-delivery-20261111-155/published-platform-ci`。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42948501059)

同发布头 Desktop 的 Linux 打包和新环境冒烟已通过，Linux 主回归、Windows CPU 和 macOS 后续验收仍在运行。本地工作台、任务目标修正与双语指南等待整轮结束后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42948501049)

## 2026-11-11 03:14 UTC · 新工作区直接进入首个任务表单

`8296e5e1` 以逐字节相同补丁集成独立原生候选 `65baa1df`，`49d8c858` 集成 Claude 独立 Web 工作树候选，Root 要求成功回执与规范 ID，并补无效 ID 回归。两端只在发起创建的当前工作台采纳确切工作区后默认展开「新建任务」。普通改选保留开合与草稿，手动开合优先。原生隔离回归验证延迟回执、回执与列表之间的改选、暂缺新工作区的 Hub 列表、第二窗口、对话框替换。Web 回归覆盖同名工作区的确切 ID、晚到快照、重连、仅待复核和保留草稿。提交仍为明确操作。

固定起点为任务页已确认并选中新建工作区、运行环境收起、没有任务。真实 Linux X11 和本机 Runtime 在英文 1600×1100、中文 680×1000、缩放 1 各测一次。旧版均点击一次「新建任务」，最终版零次。Root 应用 `2b320dc052ea05766301cf060e0adc7753cbcfbb34153cf5528ce0b0e26b276d` 与隔离候选两张对应结果图整窗像素一致。真实 Chromium、Hub、外连节点及本机 Runtime 在 1440×900 和 390×844 以相同起点复验，任务页滚动位置均为零，点击从 1 次降到 0 次。各轮实际仅创建一个工作区，零任务提交和模型调用。正式收据位于外部 `root-delivery-20261111-156/{first-task-window,first-task-browser}/comparison.json`。

`0c526425` 修正 Web 自定义任务目标。旧组合在表单显示 B 时，将含 A ID 的原草稿发往 A，回归抓到了实际请求 ID。最终版在该冲突下保留草稿与 B，提示核对且零任务请求；改为相同 ID 后一次明确点击向 B 发送复核。未指定 ID 沿用当前工作区。Root 原生 Jobs 60/60，隔离原生 60/60，四项定向各连跑十轮通过。Claude Web 全量 209/209，Root 最终生产构建和完整 Web 210/210，零失败或跳过。最终 Web 入口摘要 `bd6ed9e93dd69a344a8eaed9c48dbdf341a32993c40db99c3c5b8232e6ac34b3`。测试和失败对照在外部 `root-delivery-20261111-156/web-first-task`。各次暂存扫描零发现。

远端 `abdc57f7` 的 Windows Python 3.11 和 3.12 Runtime 两项各通过 5503 个用例，包含原热日志失败所在测试文件，3.11 于 03:03:05 UTC 完成。Desktop 的 Linux 包与新环境冒烟通过，Desktop 整轮仍在运行。Secret scan 和 Pages 通过。本地提交等待当前远端 Desktop 整轮结束再推送。开放 PR #53、#54 的头保持上次审阅结果。Claude 已转入独立 `stk-claude-workbench-first-task-guide-97` 补中英文用户指南。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42948501059) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42948501049)

## 2026-11-11 02:49 UTC · 工作台更新已发布到 main

远端 `main` 从 `9ce14a5ba5701b38c6f34e98f320582f5c4bdc83` 快进至 `abdc57f7a8cdc648920b34fe53e54c219719d720`，已独立核验完整 SHA。13 个提交范围扫描零发现。包含桌面文献一步入口与旧版 Agent 专项回归、Windows SQLite 夹具修正、桌面运行环境默认展开、Web 历史键盘焦点，以及 Cocoa 重显失败取证。原工作区 AOCI 资产与四份状态文档的既有修改已保留。

同头 Desktop `42948501049`、Runtime `42948501059`、Secret scan `42948501027`、Pages `42948501043` 已启动。Runtime 验证 Windows Python 3.11 夹具，Desktop 保留 macOS 媒体必测并采集静默对照失败时的重显回执。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42948501049) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42948501059) [Secret scan](https://github.com/sijintech/stk/actions/runs/42948501027) [Pages](https://github.com/sijintech/stk/actions/runs/42948501043)

下一片从刚确认的新工作区直接呈现新建任务表单。Claude 在独立工作树负责 Web 候选，Root 负责桌面候选、审阅和跨端验收。两个候选均以 `878e65f6` 为代码基线，尚无实现交付。

## 2026-11-11 02:48 UTC · 上一轮 Desktop 终态与 Cocoa 重显取证

远端 `9ce14a5ba5701b38c6f34e98f320582f5c4bdc83` 的 Desktop `42941178087` 于 02:44:55 UTC 整轮结束，5/6 作业通过。Linux 主回归 2225/2225、打包和新环境冒烟通过。Windows CPU 1529/1529，原生 6/6，零跳过，1152.48 秒。PDF、MP4、HTML 视频各完成 20/20 轮，分别保留 160、161、161 张验收图。已核对官方工件所取成员的 CRC 与关键图摘要。PDF 的 431 次捕获请求使用一个 WGC 目标，复用 430 次并回收，已接受帧启动最长 55 ms。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42941178087) [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42941178087/artifacts/13824060424)

macOS Cocoa 编译、CPU 1589/1589 与 Metal 254/254 通过。必测原生 4/6。MP4 在隐藏保持中从 0.346070 秒回到最后一次 seek 的 0.234 秒，HTML 视频在首次隐藏暂停从 0.209411 秒回到 0.102 秒。两个失败的导航代次相同，已记录暂停与挂起回执。可选挂起与释放 1/1，验证回到暂停状态，仍观察到时间回退。官方工件逐成员 CRC 核对，摘要在外部 `root-delivery-20261111-153/published-platform-ci/platform-terminal-summary.json`。同一发布头 Runtime 12/13，Windows Python 3.11 夹具修正在待发布提交 `cb68a9cf`。Secret scan 与 Pages 通过。 [macOS 原生工件](https://github.com/sijintech/stk/actions/runs/42941178087/artifacts/13822179975) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42941178016)

`ffcdddf6` 集成独立候选 `a617461f` 的单文件测试取证。当两个静默隐藏 HTML 对照未能重显，记录有界的原生暂停/释放轨迹、关闭原因、资源绑定和可见性、视口几何与界面阻挡。取证只在原等待失败后运行，原操作、时限及断言沿用。独立三种 C++ 条件编译与 Root 组合原生窗口目标通过，Root 文档宿主 14/14，暂存扫描零发现。目标平台新回执仍待本次推送后的 macOS 作业。

## 2026-11-11 02:44 UTC · 文献回程的旧版 Agent 执行边界

`f49833f8` 集成 Claude 在独立 worktree 的专项回归。真实旧版 ProjectAgent 保存一条合成消息，因项目读取在途保留待派发 Start。项目空闲后，文献入口和回程均阻止显示会触发 Start 的 Agent 页，保持原页与会话。显式切到该 Agent 页时观察到一次 Start，严格桥在执行器或模型之前拦截。Root 将测试等待条件绑定到读取已实际挂起和 Start 已延后两个事实。Root CMake 重建通过，新增用例连续 20/20，包含原生导航与 Agent 路由的定向组 43/43，零跳过。暂存扫描无发现。证据在外部 `root-delivery-20261111-155/claude-agent-95-{repeat,related}.log`。

已在独立 worktree `stk-claude-workbench-first-task-96` 分派下一片的 Web 候选。基线在浏览器宽窄窗使用合成项目，刚创建并选中的工作区需要一次点击展开「新建任务」。验收绑定当前节点与创建结果，按用户开合偏好直接呈现表单，显式提交前零任务请求。Root 负责原生对齐与两端验收。

## 2026-11-11 02:38 UTC · 统一工作台的运行环境与历史键盘入口

`ff2c8238` 将桌面聚焦任务页的「运行环境」对齐 Web。无有效工作区时默认展开，队列在前。首次选定工作区后收起，若焦点在即将隐藏的控件内则交还标题。失去工作区后展开，之后选定仍保持展开。手动开合优先。隔离候选 `92e1a91e` 的原回归在工作区控件隐藏处失败，修复后任务布局、界面工具包和焦点导航合计 159/159，零跳过。Root 组合构建及 Jobs 57/57 通过。固定起点为聚焦任务页、未连接运行环境且无工作区。Linux X11 英文 1600×1100 和中文 680×1000，缩放 1，均从一次点击降为零次，运行位置与工作区控件已显示。启动的分栏布局进入任务页各需两次点击，测量从任务页开始。Root 应用 `b2dc36738fcf91ddd178066eb25f27c6944b9d52aad36eb2e34f9277b2f09352` 的两张结果图各与独立候选整窗像素一致。测试期间工作区和任务均为空，零提交、写入和模型调用。外部证据为 `root-delivery-20261111-155/native-environment-window/exact-bundle-receipt.json` 和 `native-task-environment/root-jobs.xml`。

`c7418325` 让 Web 宽窗从键盘打开历史会话后直接进入正文，并沿用窄窗与宽窗鼠标的各自焦点行为。真实本机 Hub 和 Chromium 固定起点为任务页、32 条历史、原会话已有未发送草稿与阅读位置。1440×900 宽窗从按 Enter 打开到正文取得焦点，额外 Tab 由 32 次降为 0 次，PageDown 推进正文且历史栏保持位置。390×844 窄窗原有行为同样验证。两种窗口均保留草稿和阅读位置，一次历史 GET，零 POST 与模型调用，Hub 历史摘要一致。Root 生产包与独立候选 `4c32154f` 的入口摘要同为 `6126d484661096c89718814bc6742570eb0a50dbbe716a1674b35333ed82ee86`，两次全量各 201/201，零失败或跳过。`4687a95b` 同步统一工作台设计。外部证据为 `root-delivery-20261111-155/web-history-keyboard/focus-comparison.json` 和 `root-full.xml`。

上一文献入口的补充 Agent 回归 27/27，覆盖原生旧版、新版与 Python 本地模型路由。实际 Claude 在独立 `stk-claude-literature-agent-95` 继续专项延后 Start 回归。复审开放 PR #53 的重试修复已由现行终态清理与重试合并覆盖，#54 的旧交接文件与当前小写文件冲突，快速启动修订已随 #55 合入。 [PR #53](https://github.com/sijintech/stk/pull/53) [PR #54](https://github.com/sijintech/stk/pull/54)

远端 `9ce14a5b` 的 Linux 主回归 2225/2225，打包与新环境冒烟通过。Windows CPU 1529/1529，包括 HDF5 原生路径修正用例。macOS Cocoa 构建、CPU 与 Metal 通过，必测 WKWebView/Reports 原生像素验收失败，具体阶段待该作业发布证据。Windows 原生验收仍在运行。新代码等待上一 Desktop 整轮结束后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42941178087)

## 2026-11-11 02:14 UTC · 聚焦问答的文献入口与热日志夹具修正

`7c8e3c7d` 集成实际 Claude 的 `CL-WORKBENCH-LITERATURE-94` 六路径实现与 Root 审阅修正。已加载且显示已保存问答时，页头「打开文献库」沿用现有分栏文献页。切回「工作台」按原项目打开句柄、问答、捕获上下文、交换代次和布局选择恢复原实例。完整历史与 Agent 页隐藏入口，过期回调作废。进入和回程检查将显示的问答或 Agent，阻止尚待派发的动作因切页启动。`d95368b9` 更新设计的实现与验收状态。暂存扫描零发现。

固定起点为公开合成项目中九条问答的最早一条、已滚动正文、未发送草稿、隐藏文献页中已有检索文字及稳定的 Viewer。英文 1600×1000、中文 680×900，缩放 1。旧版经分栏与顶栏文献两次进入，新版均一次。返回均一次。最终二进制 `2f2ef012e0b730863c31cba6cbf892dce76120d1b3d4074302ee10f5bd5b9fb4` 与配套资源已按摘要核对。两种窗口的新旧正文、草稿、检索文字与 Viewer 比较像素差为零。新版往返桥接调用零，SQLite 字节一致。固定夹具、截图与点击收据在外部 `root-delivery-20261111-153/literature-window/candidate-final-aggregate.json`。

Root 组合构建与 36/36 定向通过，零跳过，覆盖两种宽度、多窗口改选、关闭重开、历史和 Agent 页、原项目概览、明确刷新，以及隐藏标签中的自动问答在进入和回程均不启动。证据在外部 `root-delivery-20261111-154/literature-integration/verified-targeted.xml`。Claude 原独立环境的非桥接定向 24/24，Python 桥缺依赖，组合测试使用已有项目虚拟环境。已向 Claude 分派 `CL-WORKBENCH-LITERATURE-AGENT-95`，在独立 `stk-claude-literature-agent-95` 仅验证旧版 Agent 延后 Start 的专项运行边界，使用现有可用桥接解释器，避免重复全量构建测试。

远端 `9ce14a5b` 的 Runtime `42941178016` 于 02:09:46 UTC 整轮结束，12/13。唯一失败在 Windows Python 3.11 的外来 SQLite 热日志测试，子进程进入 UPDATE 后在 20 秒内未返回。相同源码的上轮 Windows 3.11 和本轮 Windows 3.12 通过。`cb68a9cf` 选择集成独立候选 `b71bb953`，将同样使用 FULL 同步和两页缓存的测试夹具从 512 行缩至 16 行，保留真实热日志、崩溃写入与原文件字节断言。Linux 跟踪中子进程同步写盘从 1023 次降至 31 次，注入相同的 25 ms 延迟时，旧版复现超时，候选 1.51 秒通过。三种 Python 版本各 11/11，SQLite 真实副本回滚证明一致。Root 组合相关测试 5+6/11，零失败和跳过。新头 Windows 仍待验证。证据位于外部 `root-delivery-20261111-154/windows-hot-journal`。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42941178016)

当前远端 Desktop `42941178087` 的 macOS Cocoa 构建、Linux 打包与新环境冒烟通过，macOS 原生视频与 Windows 平台验收继续运行。本地文献与夹具提交待整轮终态后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42941178087)

## 2026-11-11 01:45 UTC · 工作台与平台修正已发布至 main

远端 `main` 从 `16541e8f1c41c0ed8387048e6770cd5f190c6120` 快进到 `9ce14a5ba5701b38c6f34e98f320582f5c4bdc83`，推送后独立核对完整 SHA。14 个提交范围扫描零发现。包含聚焦问答适用操作、撰写一步返回已选问答、同一任务已验证结果复用、Claude 文献入口设计、Windows HDF5 本地路径断言和 Cocoa 隐藏媒体候选。原四状态文档和 AOCI 的工作区改动已按原字节保护。

同头 Desktop `42941178087`、Runtime `42941178016`、Secret scan `42941178080` 和 Pages `42941177965` 均已启动。重点验证新的 Windows CPU 路径断言与 Cocoa 编译、MP4/HTML 视频必测原生验收。上一头完整终态与本地真实窗口、977/977 全量、55/55 导航、15/15 HDF5 及 38/38 媒体宿主结果见前节，各自绑定所测代码。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42941178087) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42941178016) [Secret scan](https://github.com/sijintech/stk/actions/runs/42941178080) [Pages](https://github.com/sijintech/stk/actions/runs/42941177965)

实际 Claude 的 `CL-WORKBENCH-LITERATURE-94` 六路径实现仍在独立工作树运行，Root 已准备英文宽窗与中文窄窗的正常路径基线。入口尚未作为实现发布，返回待派发动作保护仍需审阅。该基线使用公开合成问答、未发送草稿、文献检索文字与稳定 Viewer，在两种窗口均记录进入两次、回程一次，草稿、阅读位置和画面保持。外部证据为 `root-delivery-20261111-153/literature-window/baseline-aggregate.json`。

## 2026-11-11 01:44 UTC · 隐藏媒体候选与上一轮 Desktop 终态

`dbedeac2` 按逐字节相同的六路径补丁集成独立候选 `cc8b26599f4802fde78197ac57669e5eca168514`。文档宿主的隐藏路径使用专用暂停入口，Cocoa 对精确 WKWebView 顺序提交挂起与原有暂停，隐藏期持有一对挂起/释放。重显后核验原视图、导航、媒体与可见代次，在确认 Paused/None 后恢复原生输入。串行回执处理覆盖快速隐藏/重显、迟到释放、实际 AppKit 可见性中断与同视图新导航，验证期限为一秒。普通显式暂停沿用现有入口。原必测与可选原生验收未改。

两名独立 Agent 和 Root 审阅生命周期。Linux 独立应用与相关测试构建通过，38/38、2.61 秒。Root 正常 CMake 重建应用、项目和文档资源目标后，38/38、1.44 秒，零跳过，含真实 Xvfb 宿主路由与暂停合并。macOS Objective-C++ 编译与 MP4、HTML 视频各 20 轮的目标平台验收仍待新头 CI。暂存扫描无发现。外部构建和测试在 `root-delivery-20261111-153/cocoa-hide-suspension`。

远端上一代码头 `16541e8f1c41c0ed8387048e6770cd5f190c6120` 的 Desktop `42931986988` 已于 01:38:15 UTC 整轮结束，4/6 作业通过。Linux 主回归 2221/2221，Linux 打包和新环境冒烟通过。Windows CPU 1525/1526 的唯一失败由 `5c48faa5` 修正。macOS CPU 1586/1586、Metal 254/254，必测原生 4/6；其两个视频失败与可选挂起/释放 1/1 的正式细节见前节。当前已满足上一整轮终态的推送门。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42931986988)

Windows 原生作业独立结束并通过 6/6、1032.61 秒。官方工件的所取成员通过 CRC 和摘要核对。PDF、MP4、HTML 视频各完成 20/20 轮，验收图分别 160、161、161 张。PDF 的 450 次捕获请求记录 WGC 创建 1 次、复用 449 次并结束回收，已接受帧的最长捕获启动 49 ms。第 5 和第 20 轮重新准备的关键 PNG 与报告 SHA 相同。外部正式汇总为 `root-delivery-20261111-150/published-platform-ci/platform-terminal-summary.json`。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42931986988/artifacts/13820246740)

Claude 的独立文献入口实现仍在进行，Root 已记录返回路径需同样防止待派发准备/发送的审阅点。它的未审定代码保持在 `stk-claude-literature-94`。两条开放旧 PR 的头与范围已重核，本批没有适用的待合入改动。

## 2026-11-11 01:32 UTC · Windows HDF5 路径断言修正

`5c48faa5` 选择集成独立候选 `7b34a24a0b55829183502799dbad5c3766aeaaaf`，唯一修改为 `muferro_hdf5_view_test.cc` 的本地运行目录断言。UTF-8 本地绑定先解析为文件系统路径，再比较规范化后的精确运行目录。图谱、选择器、分量、范围、发布源摘要与拒绝场景继续由原断言检查。两次暂存扫描无发现。

正式 Windows CPU `16541e8f` 的 1526 项中仅这条字符串断言失败，实际和预期的两种分隔符解析到相同 Windows 路径。独立候选相关套件 15/15；Root 正常 CMake 重建后同套件 15/15，零跳过，0.30 秒。目标 Windows 的新头执行待推送后确认。外部证据在 `root-delivery-20261111-153/windows-cpu-triage`，包含正式 JUnit、日志摘要、微软路径语义、独立与组合构建记录。当前旧头 Windows 原生作业继续运行，Desktop 整轮尚未终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42931986988)

## 2026-11-11 01:26 UTC · 文献设计交付与当前平台回归

`6dbf7cb3` 选择集成实际 Claude 文献设计提交 `072f13139d04393810d9391c910879cc41475f8d`，唯一文件为 `docs/design/workbench-literature-entry.md`。Root 与独立源码审阅确认原问答身份、跨分栏待派发动作保护、冻结引用与选中 scopes、当前授权和明确刷新计数。点击数仍是设计目标。Claude 在干净独立 `stk-claude-literature-94/claude/workbench-literature-94` 从 `6dbf7cb3` 实现已分配的六条原生导航、UI 和测试路径；Root 维护公共契约、状态、整合及发布。原 `stk-claude` 的 Web 改动在原工作树内。此次暂存扫描无发现。

上一组合 `17b3b3ae` 的完整原生项目回归已结束，977/977，951.010 秒，零失败和跳过，测后核对测试二进制摘要一致。随后才重建含 `64e4fff4` 一步返回问答的组合测试，55/55，10.21 秒，含导航、草稿、来源、明确准备及 OpenGL UI，零失败和跳过。完整日志在外部 `root-delivery-20261111-151/native-result-revisit`，本片组合定向在 `root-delivery-20261111-153/native-integration`。

远端 `16541e8f` 的 Runtime 整轮 13/13。Desktop Linux 主作业 2221/2221、619.19 秒，打包和新环境冒烟也通过。Windows CPU 1525/1526，唯一失败是 HDF5 体素回归将同一实际目录的两种路径分隔符按字符串比较，独立工作树正在修正断言。Windows 原生作业已由成功暂存的候选独立启动，继续执行。当前 Desktop 整轮尚未结束，本地后续提交待其终态后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42931986988) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42931986868)

macOS CPU 1586/1586、Metal 254/254，必测原生 4/6，MP4 与 HTML 视频仍在隐藏暂停时回到先前时间。正式工件的所取成员通过 ZIP CRC 并分别记录 SHA。新可选挂起/释放对照 1/1、9.03169 秒，同一视图和导航依次为 Playing、Suspended、释放后 Paused、明确操作后 Playing。首次和保持 0.75 秒后的重显位置都为 0.074674875 秒，随后明确播放到 0.1802841253 秒。初始挂起前为 0.113265125 秒，因此这条对照只证明所测释放流程。生产候选在独立 worktree 实现，保留原必测标准，目标 macOS 验收待新头。外部正式收据为 `root-delivery-20261111-150/published-platform-ci/macos-summary.json`。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42931986988/artifacts/13818583337)

## 2026-11-11 01:04 UTC · 撰写后一步返回已选问答

`64e4fff4` 按逐字节相同的补丁集成独立桌面候选 `c6030606`。聚焦工作台的撰写区有已验证的选中问答时，可直接回到该问答。回程沿用当前项目、问答、输入草稿和正文位置，把键盘焦点交给正文。旧入口回调在撰写代次、项目或选中问答变化时作废。已有问答的回程无需读取隐藏的分页历史，显式打开历史继续加载。`2fb24ba5` 更新共用设计。两次 Root 暂存扫描零发现。

独立源码构建和 41/41 定向通过，26.59 秒，零跳过。用例覆盖主动编辑中的草稿、过期回程按钮、隐藏的旧历史页及返回后键盘翻页。Root 组合应用构建成功。真实 Linux X11 固定起点为最近列表之外的一条问答，即九条夹具问答中最早的一条，回复已滚离末尾，撰写区已有草稿。英文 1600×1000 和中文 680×900，缩放 1。旧版分别需要两次和三次点击打开并关闭完整历史，新版均一次点击。Root 和独立候选的返回正文、Page Down 后正文及草稿区域像素相同。两种窗口测量中无桥 RPC，SQLite 摘要不变。证据在外部 `root-delivery-20261111-152/native-return-to-question/root-aggregate.json`。Root 上一组合二进制的全量项目回归仍在运行，结束并核对其摘要后再重建本片测试二进制。

Claude 独立文献设计已交初稿并通过第一轮修订，Root 审阅后要求补齐跨分栏自动派发保护、明确刷新读取与撤权后的来源校验。该文档仍是设计，实际入口、跨端文献能力和真实点击验收尚待后续。上一远端头 `16541e8f` 的 Desktop 整轮仍在运行，等待整轮终态后推送本地批次。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42931986988)

## 2026-11-11 00:57 UTC · 聚焦问答操作与同一任务的结果复用

`d60ba43e` 按逐字节相同的补丁集成独立桌面候选 `0af30c23`。聚焦项目问答在正文旁显示状态、模型和捕获来源，按状态呈现操作。已完成的问答显示刷新和归档，待发送或运行中的问答显示适用的发送、取消或恢复。请求和上下文的完整 ID 各可在「请求详情」复制。独立构建和 45/45 定向通过。Linux X11 固定起点为已打开第 8 条已保存问答且已有未发送草稿，缩放 1。英文 1600×1000 和中文 680×900 均一次点击展开详情，每个 ID 各一次点击复制且与夹具 UUID 一致。切换待发送问答分别一次和两次点击，保留草稿，零滚轮、模型和写入 RPC，SQLite 摘要相同。独立收据在外部 `root-delivery-20261111-151/native-discussion-actions/x11-evidence.json`。

`17b3b3ae` 对齐 Web 与原生聚焦工作台的同一任务结果捷径。仅复用与当前运行连接、工作区和任务绑定的已验证画面，保留视角、实际步号和探针。另一任务、重选运行连接、已观测到的连接检查失败、恢复的冻结画面和其他未验证画面沿用正常打开。当前连接描述无法识别未被桌面观测到且描述相同的外部凭据替换。旧代码回归在同一结果步号、相机、载荷与探针复位处失败。组合构建和 Jobs 56/56、问答与导航 55/55 通过，零跳过。`bca22db3` 更新统一工作台设计。各次暂存扫描零发现。

Root 组合二进制及配套资源在 Linux X11 的英文 1600×720 与中文 680×720 上复验，缩放 1，使用真实本机 Runtime 与合成 MuFerro 两步任务。固定起点为已选成功任务、任务表单有草稿、结果第 7 步已旋转并返回任务页。再次打开同一结果、展开来源和返回任务各一次点击，Esc 关闭来源，测量中零滚轮。两种窗口的图谱请求均从旧版 2 次降为 0 次，视角、关闭来源后的画面、任务队列和草稿对应像素差均为 0，工作区、任务和产物摘要一致。原始收据和构建测试位于外部 `root-delivery-20261111-151/native-result-revisit-window/exact-bundle-receipt.json` 与 `native-result-revisit`。

上一发布头 `16541e8f` 对应的桌面源码 `d70c2a2e` 全量项目回归结束，976/976，952.132 秒，测试二进制摘要测后核对一致。当前组合全量项目回归已启动。远端 Runtime 13/13 于 00:54:55 UTC 通过，Desktop 的 Linux 打包和新环境冒烟通过，整轮仍在运行。本地新代码等待上一 Desktop 整轮结束后推送。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42931986868) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42931986988)

Claude CLI 登录已恢复。文献来源入口和返回设计 `CL-WORKBENCH-LITERATURE-93` 已派发至独立 `stk-claude-literature-93/claude/workbench-literature-93`，基线为已公开的 `16541e8f`，仅可写 `docs/design/workbench-literature-entry.md`，由 Root 审阅与集成。旧 `stk-claude` 的 Web 工作树仍有原改动。下一小片是从「写问题」一次点击回到最近列表外已选问答，在独立 Codex worktree 验证。

## 2026-11-11 00:32 UTC · 共用工作台发布到主线

远端 `main` 从 `ee0515122d2e7a565705e63c98694ad0bece0c2b` 快进至 `16541e8f1c41c0ed8387048e6770cd5f190c6120`，推送后独立查验完整 SHA。21 个提交范围扫描零发现。包含双端导航、会话列、Web 键盘阅读、桌面快速撰写、MuPRO HDF5 原始体素与双语指南。保留既有 AOCI 和状态文档工作区改动。

同头 Pages 和 Secret scan 已通过。公共中英文指南实际返回 HTTP 200，均确认新撰写和体素入口。响应摘要在外部 `root-delivery-20261111-150/published-pages`。新头 Desktop 和 Runtime 继续运行，macOS 新挂起对照待正式目标结果。 [中文指南](https://stk.pages.dev/user_guide/) [英文指南](https://stk.pages.dev/en/user_guide/) [Pages](https://github.com/sijintech/stk/actions/runs/42931986851) [Secret scan](https://github.com/sijintech/stk/actions/runs/42931986854) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42931986988) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42931986868)

`d70c2a2e` 原生组合二进制的 976 项完整项目回归已启动，未以该次未终态运行替代上节 37 项定向和前头 976/976。下一批继续简化当前问答的状态与专业操作，按相同真实窗口与显式准备/发送边界验收。

## 2026-11-11 00:29 UTC · 共用会话列与键盘阅读

`d70c2a2e` 和 `9bddb062` 分别按逐字节相同的补丁集成独立原生 `c1325d46`、Web `5fb8d9e5`。聚焦项目问答和 Web 会话使用居中单列，宽窗上限 880 逻辑像素，窄窗使用可用宽度。常规会话正文独立滚动，输入在下方，主要按钮按所需宽度靠右。桌面「写问题」仍将原草稿放到页首并聚焦，准备与发送为显式操作。普通分栏、完整已保存问答浏览和结构化 Agent 沿各自现有布局。`b1ae4598` 更新统一工作台设计。

`39738985` 使已显示正文可从 Web 输入框按 Shift+Tab 返回。旧组合产物的宽窄用例均因正文未获得焦点失败。Root 新产物从输入框按 Shift+Tab 进入正文，再用 PageDown 和 End 滚动。Tab 回到输入框，往返任务页共两次点击，草稿和阅读位置相同。独立 Web 全量 198/198，Root 生产构建和完整 Web 200/200，零失败、跳过和重试。Root 用真实本机 Hub 的 60 段公开合成历史复验中文 1440×900 与 390×844，分别一次和两次点击打开历史。宽列 880 px，窄区 390 px，发送按钮均宽 66 px。测量范围内一个历史 GET，零 POST 和模型调用，历史摘要一致。证据在外部 `root-delivery-20261111-150/web-keyboard-transcript`。

独立与 Root 原生构建通过，定向各 37/37，零失败及跳过。固定起点为任务页、项目已选第 8 条已保存问答且有草稿。真实 X11 英文 1600×1000 从左栏一次点击，中文 680×900 通过「历史」两次点击。均可直接输入并在返回后查看原问答，零滚轮，数据库摘要不变，只有返回原问答时一次进度读取。整合与独立二进制的输入区域像素一致。宽窗正文与输入占 880 px，窄窗占可用 664 px，原生另验证 UI 缩放 1.25。证据在外部 `root-delivery-20261111-150/native-centered-root` 和 `root-delivery-20261110-150/native-conversation-layout`。

上节 Windows WGC `creates=1 reuses=430 retired=true` 仅属 PDF 用例，覆盖该用例的 431 次捕获调用。已核对所取的 JUnit、日志、报告与两张关键 PNG，旧版失败的第 5 轮本次 12 ms 取得匹配帧。完整收据在外部 `root-delivery-20261110-149/windows-lease-ci/windows-native-receipt.json`。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42920785230/artifacts/13815826674)

Claude CLI 当前未登录，独立 `stk-claude/claude/web-task-result-return-focus-92` 的原改动保留。为登录恢复后准备了文献来源入口设计卡 `root-delivery-20261111-150/claude-workbench-literature-task.txt`，写入范围限一份设计文档。本批两端会话模块由独立 Codex worktree 交付，Root 审阅、集成和发布。两次集成、键盘修复与文档的暂存扫描均无发现。

## 2026-11-11 00:26 UTC · 上一轮 Desktop 终态与 Windows 捕获复用

远端 `ee0515122d2e7a565705e63c98694ad0bece0c2b` 的 Desktop `42920785230` 于 00:20:43 UTC 结束，5/6 作业成功。Linux 主回归 2211/2211，Linux 打包、新环境冒烟、Windows CPU 1516/1516 与 Windows 原生 6/6 通过。Windows 原生共 1315.37 秒，PDF、MP4、HTML 视频各完成 20/20 轮，分别有 160、161、161 张验收图。官方工件的逐成员 CRC 已核对，原生日志记录一个 WGC 捕获目标创建、430 次复用和结束回收。PDF 已接受图像的最长捕获启动为 72 ms。完整 Windows ZIP 下载出现 EOF，当前结论来自已核对的正式报告与日志成员。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42920785230) [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42920785230/artifacts/13815826674)

macOS CPU 1576/1576、Metal 254/254，必测原生 4/6。ZIP 完整 SHA-256 已与 GitHub 核对。MP4 首次隐藏后从 0.352418 s 回到 0.234 s，HTML 视频在隐藏保持中从 0.246686 s 回到 0.102 s。两者仍暂停且导航未换，派发均在隐藏前，ACK 均在隐藏后。先确认可见暂停、再隐藏但不重复派发的四条对照，隐藏后的被动原生枚举仍全报 Playing，其中两条带 DOM 尾部观察各相隔 0.4 s 且位置变化为 0。保持重复派发的两条对照则分别收到 29 和 27 次 Playing，随后会话由看门狗关闭。可选的挂起再重显对照将随本批代码运行。 [macOS 原生工件](https://github.com/sijintech/stk/actions/runs/42920785230/artifacts/13813874701)

前轮本地 `631808cc` 原生项目完整回归 976/976，923.797 秒，零失败和跳过。测后重建前核对测试二进制摘要。证据位于外部 `root-delivery-20261110-149/native-combined`。同远端 Runtime 13/13、Pages 与 Secret scan 通过。两条开放 PR 已重核头和范围。#53 是已用不同回执语义处理的旧传输改动，#54 只改旧版大写交接文件。当前未合入这两条 PR。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42920785047)

## 2026-11-11 00:10 UTC · 双端 MuPRO 原始体素与中英文工作台指南

`631808cc` 集成独立原生候选 `1ab5182a`，十三条路径的补丁内容一致。已显示且有本地收集证明的 HDF5 帧在普通分栏 Viewer 和聚焦结果页的「来源」内可查询原始体素。查询固定到实际场、步号、分量、收集文件摘要和从零开始的网格索引。更改坐标、关闭来源、切页或替换画面作废在途回执。单体素数据验证字节、摘要、来源和原始 dtype。恢复或导入的 Viewer 载荷在缺少现行证明时仅供查看。

独立原生构建通过，定向 16/16。真实严格 Python 桥从合成收集 HDF5 读得 `9223372036854775931 · uint64`，同大小和 mtime 的改写也被拒绝，覆盖同一窗口返回、分栏隐藏、请求换坐标、项目关闭和重开。Root 合并源码构建成功，组合定向 70/70，零失败、跳过，含导航、HDF5、Viewer、真实 Vulkan/OpenGL 桥和 X11/Wayland 窗口。Root 全量项目回归已用组合二进制启动。证据在外部 `root-delivery-20261110-149/native-hdf5-voxel` 和 `native-combined`。

Root 对独立和整合二进制重跑同一 X11 流程。固定为英文 1440×1600、缩放 1，普通分栏 Viewer 已显示 `Polar` 第 2 步分量 0。单击「来源」与「读取体素」两次得到 `[0,0,0]` 的 `0 · float32`。两次点击输入框和键入 `[2,1,0]` 没有发请求，再一次点击得到 `42 · float32`。每次显式读取只有一个图谱请求，零滚轮。数据与 h5py 直接读取一致，独立和整合二进制的两个读数面板像素相同。项目和 Runtime 数据库、原任务和已收集文件摘要保持一致。实际窗口证据在外部 `root-delivery-20261110-149/native-hdf5-window/layout-clean`。早期手动定位脚本在等待最后一批坐标命令时超时，使用同一组确认坐标完整重放后两版正常退出。

`7b24bc3d` 更新中英文指南和统一工作台设计。Node 22.23.3 上 Astro 检查零诊断，生成 38 页和中英搜索索引，两个实际 HTML 都含撰写和体素入口。Root 暂存扫描均无发现。Web 的 196/196 组合回归及实机浏览器结论见前节。

远端 `ee051512` 的 macOS 正式 CPU 1576/1576、Metal 254/254，必测原生 4/6，MP4 与 HTML 视频仍在隐藏暂停阶段失败。Windows CPU 1516/1516，原生 Windows 作业继续运行。按整轮 Desktop 终态发布已验证的本地提交。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42920785230) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42920785230/artifacts/13813874701)

## 2026-11-10 23:58 UTC · 从桌面历史入口直接撰写问题

`2cc1f7e0` 按逐字节相同的补丁集成独立候选 `6a03a2d9`。原生工作台在宽窗左栏和窄窗「历史」首项提供「写问题」。继续使用当前 AI 编辑器实例、项目草稿、选中的已保存问答与其阅读位置。撰写时输入区移到页首并接收键盘。选择已保存问答返回阅读布局。准备与发送仍是各自的显式操作。`743d6f14` 记录 Web「新对话」与桌面「写问题」各自使用的草稿身份。

真实 Linux X11 桌面固定起点为任务页，当前项目选中已保存的第 8 条问答，并有一份未发送草稿。缩放为 1。英文 1600×1000 左栏一次点击，中文 680×900 经「历史」两次点击。两端均能立即键入，已有草稿与原回复同时保留，零滚轮。返回原问答分别一次与两次点击，仅返回时有一次进度读取。测量中无模型、准备、发送或数据库写入，SQLite 摘要相同。实窗使用合成项目与真实严格 Python 桥，证据在外部 `root-delivery-20261110-149/native-compose-window`。

独立候选的实际发布路径源码与 Root 整合 `desktop/` 无差异。旧版定向用例因缺少入口失败。候选桌面构建通过，导航 28/28、UI 核心 132/132，零跳过。导航回归还验证窄窗 Esc 恢复历史入口焦点，再用键盘撰写可保持原问答、阅读位置、草稿及 Viewer。Root 暂存扫描无发现。验证在外部 `root-delivery-20261110-149/native-direct-compose`。

远端 `ee051512` 的 Desktop 还在运行，macOS CPU 与 Metal 步骤成功，必测原生 WKWebView 步骤已报失败，失败用例和剩余作业以正式终态为准。Windows CPU 仍在运行。Root 本地批次等待整轮结束后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42920785230)

## 2026-11-10 23:46 UTC · Web 与桌面共享工作台导航布局

`bef72321` 将 Web 宽屏的导航与历史从两栏合到一条 144 逻辑像素左栏。两端以 700 逻辑像素为共同阈值。超过阈值时左栏依次显示工作台、任务、结果与可用历史，较窄时主导航在顶部。会话、任务和结果继续复用当前实例。根导航布局已实测，两端会话正文和输入区的视觉层级仍在对齐。共同布局见 `docs/design/unified-workbench.md`。

固定中文 Chromium 701×844，节点和项目已选，任务页显示一条完成任务，存在两条已保存对话和一份未发送草稿。新版从任务页一次实际点击打开历史对话，出现完整问题与回复，仅发一次历史 GET。旧产物此时还需要打开历史，再选择对话。调整到 700×844 后顶部显示历史入口，打开后 Esc 返回该入口，再两次点击选回原草稿。过程没有任务提交或消息发送。1440×900 和 390×844 定向覆盖历史开关、焦点、阅读位置与结果画面。原 Web 构建分别在双栏坐标和 701 像素入口两个新断言上失败。Root 用真实 X11 窗口验证中文桌面 701×844 和 700×844、缩放 1、未打开项目。前者绘制边界在 x=144，后者为顶部导航。截图和浏览器测试在外部 `root-delivery-20261110-149/unified-rail`。

`711164a5` 集成 Web 候选 `5802f4ae`，七条路径的补丁内容一致。Web 结果页显示 MuPRO HDF5 当前画面的场、步号和分量，用户显式输入从零开始的网格索引并读取原始体素。图谱和 blob 同时绑定已发布源摘要，坐标、帧或任务切换时丢弃旧回复。两端在独立工作树开发，桌面入口尚未集成。

独立 Web 全量 195/195。Root 组合生产构建与 Web 回归 196/196，零失败、零跳过及零重试。用该组合产物和真实本机 Hub、NodeAgent、Runtime 在中文 Chromium 1440×900 和 390×844 验证 HDF5 与 DAT。固定起点为已显示第 2 步、分量 1，结果滚动位置为 0。修改未打开的第 4 步/分量 0 和坐标不发动作。两端分别一次点击或一次 Enter 读取 `9223372036854775931 · uint64`，一个图谱请求、一个 blob，保持同一画布且零滚轮。随后精确读取 `1.0000000000000002 · float64` 并验证原 DAT 入口。合成夹具不含真实 MuPRO 执行。两次 Root 暂存扫描零发现。完整 JUnit 与实机浏览器收据在外部 `root-delivery-20261110-149/web-combined`。

本地提交待远端 `ee051512` 的整轮 Desktop 结束后推送。该头 Runtime 13/13 通过，Linux Desktop 三个作业通过，Windows 和 macOS 仍运行。桌面侧栏直接写新问题与 HDF5 体素分别在独立 Codex worktree 验证。Claude worktree 保留原有未提交改动。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42920785230) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42920785047)

## 2026-11-10 23:40 UTC · Viewer 恢复、Cocoa 诊断与 HDF5 取值

`ea3f5eb1` 用已求值图谱的语义摘要验证恢复时的来源。固定起点为已显示 MuFerro 帧、同一项目与来源、已调整的 Viewer 相机。预设显示名称和节点排列更改后，旧版一次查询发送零个请求，新版一次查询仍读取已显示帧的原始值。计算定义更改时拒绝使用旧证明。刷新并接纳语义等价图谱时保留物理选点。Root 定向构建与 25/25 测试通过，零跳过，覆盖真实 Python 桥、OpenGL、Vulkan、X11 和 Wayland。先前 `6ee7ae36` 项目套件完整 971/971，零跳过及失败，859.07 秒。暂存扫描通过。证据在外部 `root-delivery-20261110-148/native-probe-preset-root` 和 `root-delivery-20261110-149/restored-probe-metadata`。

`8a066663` 按逐字节相同补丁集成 `3c8d6be0`。Cocoa MP4 的可选诊断依次验证同一原生视图显式挂起、普通切页隐藏、重显后释放和人工点击恢复播放。诊断独立于必测视频门。Root Linux 编译与 Report/DocumentEvidence 31/31，零跳过，暂存扫描通过。Cocoa Objective-C++ SDK 编译和实际播放仍等该提交发布后的 macOS 作业。证据在外部 `root-delivery-20261110-149/cocoa-suspend-root`。

同一发布摘要绑定下，Root 使用真实本机 Hub、NodeAgent 与 Runtime，对合成 MuPRO HDF5 用现有图谱协议读取单体素。三份 136 字节 NPY 工件经下载与摘要复核，分别精确读取 `uint64` 的 `9223372036854775942`、`float64` 的 `1.0000000000000002` 与 `inf`。源摘要不符与越界均由 Runtime 拒绝。取值与两端 UI 继续分别在独立工作树验证。证据在外部 `root-delivery-20261110-149/hdf5-live-voxel`。

远端 `ee051512` Runtime 13/13 全通过。Desktop 的 Linux 主回归、打包和新环境冒烟通过，macOS、Windows 尚未完成。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42920785047) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42920785230)

## 2026-11-10 23:16 UTC · 原生探针使用已显示图谱

`6ee7ae36` 集成 `695025ea`，保留 `7f2ea3fc` 的跨帧 Pending 回执防护。探针固定到已接纳画面的图谱、原参数、绑定和本地证明。预设更改等待或失败时，旧画面的探针继续读取原来源。新图谱或来源真正接替时，旧选点与迟到回执失效。同一图谱的时间步切换继续按原物理坐标查询。恢复工作区需要可验证的已显示图谱和相符的原预设定义，已保存的探针结果仍可查看。仅标签或节点排列变化也可能使恢复后的重新取值不可用。独立审阅核对本机、已收集目录、直连 Runtime、Hub 和旧预设五种协议形状，真实原生数据验证覆盖本机与已收集目录。

独立候选 CPU 55/55、Python 探针 7/7、Linux RelWithDebInfo 软件 OpenGL 原生 3/3，零跳过。最初独立 Debug 的 llvmpipe 着色器断言发生在探针验证前，按发行构建重跑通过。Root 保留现有防护后重新构建，组合套件 61/61，零失败及跳过，含真实 Python 桥的 Vulkan 与 OpenGL 各 6 项，以及 X11、Wayland 实际 Viewer 窗口。暂存扫描零发现。证据在外部 `root-delivery-20261110-147/native-probe-preset` 与 `root-delivery-20261110-148/native-probe-preset-root`。

上一个包含桌面历史入口与跨帧探针防护的原生项目套件终态 968/968，零跳过及失败，944.4 秒。新本地源码的 971 项项目套件已启动。远端 `ee051512` 的 Desktop 仍在运行，Windows 处于全目标构建，Runtime 8/13 作业已成功。公共指南已上线。下一批可选 Cocoa 诊断在独立工作树检验同一视图隐藏前挂起、真实隐藏暂停及重显释放后的行为。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42920785230) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42920785047)

## 2026-11-10 23:10 UTC · 主线发布与公共指南上线

远端 `main` 从 `a64941b4` 快进至 `ee0515122d2e7a565705e63c98694ad0bece0c2b`，推送后实查完整 SHA 一致。17 个提交范围扫描零发现，所有者的 AOCI 与状态文档工作区改动已保留。发布包含桌面已保存问答、双端 MuPRO 结果读取、Web 状态标签与 Viewer 迟到点击修复。上一轮 Desktop 终态和 482 张 Windows 图像摘要见下一节。

新头 Secret scan 与 Pages 均通过。对公共中英文指南实际 HTTP 200，核对已保存问答和 MuPRO HDF5 章节，响应摘要在外部 `root-delivery-20261110-148/pages-live`。新头 Desktop 与 Runtime 正在运行。Windows 捕获目标复用首次进入正式目标平台，macOS 两个视频隐藏阶段仍待修。 [中文工作台指南](https://stk.pages.dev/user_guide/) [英文工作台指南](https://stk.pages.dev/en/user_guide/) [Pages](https://github.com/sijintech/stk/actions/runs/42920785458) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42920785230) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42920785047)

## 2026-11-10 23:07 UTC · Desktop 上一轮终态、Web 任务状态与 Viewer 点击

远端 `a64941b4` 的 Desktop `42908396134` 于 23:00:45 UTC 结束，5/6 作业成功。Linux 主回归 2205/2205、打包及新环境冒烟均过，Windows CPU 1510/1510。Windows 原生 6/6，零跳过，1344.66 秒。正式 Windows 工件 `13811017650` 有 1888 个文件，完整 ZIP SHA-256 和 PDF/视频的 482 张验收图像摘要已核对。PDF 20/20、160 张图像，第 20 轮 `reprepared-page1` 两次匹配，已接受图像最长捕获启动 93 ms。MP4、HTML 视频各 20/20、各 161 张。该轮使用原捕获实现，待发布的复用目标另在新 Windows CI 取证。macOS CPU 1570/1570、Metal 254/254，必测原生 4/6，两个视频的隐藏阶段失败，详细时间及对照见前一节。相同代码头 Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42908396134) [Windows 工件](https://github.com/sijintech/stk/actions/runs/42908396134/artifacts/13811017650) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42908396134/artifacts/13809562358) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42908396193)

`ff015622` 按逐字节相同的补丁集成 `d9456044`。Web 队列、精确状态和图谱任务选项使用桌面的八种中文状态。已请求取消的未终态任务显示「正在取消」，终态显示实际结果。快照、不可达、待核实与精确 Runtime 的原规则保持。未知的新状态在队列保留原值。模拟 Hub 宽窄屏基线确证八种旧枚举，候选定向 5/5。独立与 Root Chromium 各 189/189，零跳过及重试，生产构建通过。

Root 使用实际 Web 产物、真实本机 Hub、NodeAgent 和 Runtime。中文 Chromium 1440×900、390×844，固定起点为节点、工作区已选且队列含一个完成与一个等待任务。两端选择各任务均 1 点击，队列及 Runtime 精确详情分别显示「成功」「排队中」，保留原状态样式。两端都只有已有 `task.get` 和 `task.artifacts` 读取，零动作或模型请求，Runtime 任务终态未被 UI 改写。收据在外部 `root-delivery-20261110-148/web-task-status-root/real-browser`。

`28690dcf` 在真正取 GPU 像素前校对已绘制载荷代次和 Viewer 当前载荷。固定起点为真实 MuFerro 图谱已绘制并回到默认取景，1 次点击进入队列，已排在前面的回调接纳替换载荷。X11 原实现把迟到点击应用到新结果并把探针置为不可用。新版 X11 与 Wayland 在新结果保持空探针。再打开原运行并点击一次，均从真实 Python 桥读回数值，Probe 编辑器显示原始值。Root 构建通过，两端实际 Viewer 窗口及启动共 4/4，零跳过。暂存扫描通过。收据在外部 `root-delivery-20261110-148/gpu-pick`。切换预设期间探针绑定已接纳图谱的独立候选继续验证。

本节确认上一 Desktop 整轮终态。发布前本地原生 968 项项目套件已开始，终态另记。两条现存旧 PR 仍为原提交，#53 的传输行为已在主线通过不同回执语义处理，#54 会引入旧版大写交接文件。两者本轮均未合入。

## 2026-11-10 22:53 UTC · 桌面历史直达、跨帧探针与 Cocoa 对照

`e4f74494` 按逐字节相同的补丁集成 `08ec9dca`。从聚焦界面的宽窗左栏和窄窗「历史」直接打开已保存问答的完整分页与归档筛选。第一次需要时只读一页，打开已缓存列表可复用。选择条目才读取问答。原 AI 编辑器实例、草稿和 Viewer 状态保留，项目重开重置浏览界面。公共指南和统一工作台设计已补入口。

独立与 Root 实窗固定起点均为已显示公开 STKP、当前项目有 9 条问答且留有未发送草稿。英文 1600×1000 缩放 1，旧入口 2 点击，新入口 1 点击。中文 680×900 缩放 1，旧入口 2 点击，新入口为「历史」加「已保存问答」2 点击。再单击下拉框，按 Home 和 Return 可打开最旧问答。返回结果 1 点击，零滚轮。两端测量段各 1 次请求进度读取、1 次上下文读取和 2 次消息读取，零模型调用及写入，SQLite 摘要一致。Root 整合二进制的回复与草稿取样区域与已验独立候选零像素差。两版的三维像素区域均会波动，Viewer 载荷与相机序号由定向测试核对。Root 初次实窗脚本在窗口完成首次绘制前点击，后来改为等画面和项目读取就绪后再采样。证据在外部 `root-delivery-20261110-146/native-history-browse` 与 `root-delivery-20261110-147/native-history-root`。

`7f2ea3fc` 修复第 2 步探针回执迟到并覆盖已显示第 1 步的竞态。接受新帧时，未完成的旧探针也按同一物理坐标重新绑定，迟到回执失效。原版真实 C++ 桥接测试只发一次探针且把第 2 步结果显示到第 1 步，新版两个请求分别绑定 2 与 1，旧回执对当前探针无影响。Root 联合构建桌面及测试目标成功，项目导航 26 项、Viewer 19 项合计 45/45，零失败及跳过。暂存扫描通过。用户更换预设而旧画面仍显示时，原生探针还可能引用新预设。独立 worktree 正在将请求完整绑定已接纳的图谱与输入。

同头 `a64941b4` macOS 正式工件 `13809562358` 的 ZIP SHA-256 已核对。CPU 1570/1570、Metal 254/254、必测原生 4/6。MP4 首次工具栏通过，隐藏暂停从 0.340429 s 回到 0.234 s，越过 50 ms 允许回退。HTML 首次工具栏通过，隐藏保持从 0.248717 s 回到 0.102 s，越过 100 ms 容差。两次状态均为暂停且未更换导航、未结束。

首次工具栏零等待与 270 ms 对照按同一格式与夹具分别成对，4/4 取得观察。MP4 零等待三个 DOM 点约为 0.138438、0.055272、0.055272 s，有延迟的三个点均为 0.314729 s。HTML 零等待均为 0.049428 s，有延迟均为 0.312140 s。四个独立原生回复均为原始暂停态 2，且各自导航和媒体代次保持一致。正式失败发生在后续隐藏路径。Windows CPU 1510/1510，Windows 原生像素作业仍在运行，待整轮终态后推送。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42908396134/artifacts/13809562358) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42908396134)

## 2026-11-10 22:44 UTC · 公共工作台指南与原生探针来源

`71d7e7ef` 更新 Pages 首页、侧栏和现有用户指南，中英文都按工作台、任务和结果介绍桌面与 Web。Web 步骤写明配对、执行环境、来源和显式 MuPRO HDF5 读取。旧版 PyQt 指南仍从原链接进入。Linux 快速上手改走原生 **项目概览 → 创建示例项目**。固定为中文 X11 1280×900、首次启动且未开项目，实际两次点击生成三个合成结果。使用独立候选桌面二进制和真实本机 Python，无许可求解。Node 22.23.3、pnpm 8.15.9 冻结依赖、Astro 检查与构建通过，共 38 页，Pagefind 产物存在。固定从本站首页进入，两种语言各一次点击到指南、一次到对应快速上手。实际 Chromium 中文 1440×900、英文 390×844。原英文快速上手仍嵌入仓库共用的中文安装正文。Pages 发布随主线推送，当前公共站点仍服务旧内容。证据在外部 `root-delivery-20261110-147/current-workbench-docs`。

`767847f9` 集成 `fd80b2cf` 并修正评审发现的两处问题。已求值 MuFerro DAT 按所选图层实际步号定位，普通与已收集本地目录使用受约束的读取器和独立快照，以求值时的数据键核对文件名及摘要。真实本机图谱进程确认从 `case/Polar.00000002.dat` 返回 `[0.34765625, 0.40625, 0.34765625]`，内联步号 3 仍读实际第 2 步。已改变的算例记录或同大小同时间戳的数据会被拒绝。Runtime 和 Hub 从对应任务的终态发布清单获取路径，自动目录有同名歧义时零取值请求。Root 将严格模式绑定真实图谱结果，恢复旧调用传空结果对象的行为。校验场名并固定快照文件名，避免未经校验的路径进入临时文件写入。两项新增回归在独立候选上均失败，修订后均通过。

独立候选原验证 91 通过、1 项性能测试按条件跳过。Root 最终桥、Runtime、Hub、图谱预设和脚本回归 74 通过、零失败、同一可选基准跳过，暂存扫描零发现。真实回归和测试收据在外部 `root-delivery-20261110-147/native-probe-root`。已显示新帧后收到旧探针回执的 C++ 回归另在原版复现，修复和桌面历史入口的联合构建正在进行。

远端 `a64941b4` Windows CPU 作业成功，Windows 原生像素作业仍在运行。macOS CPU、Metal 和打包冒烟通过，必测 WKWebView 步骤失败，诊断与工件仍待。Linux Desktop 与 Runtime 已成功。本地提交等待该 Desktop 整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42908396134) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42908396193)

## 2026-11-10 22:25 UTC · Web 图谱按所选图层读取原始值

`b105894f` 集成独立候选 `13d9586e`。MuFerro DAT 探针从已显示图层的读取节点取实际解析步号，绑定该图层的原计算任务。用户点「查询原始值」才读取该任务的发布清单。明确算例目录只接受完整匹配路径，自动目录要求同名帧在该任务中唯一。无法确认来源时提示原因，保留当前画面。切换图层、坐标、工作区或页面会丢弃旧请求的迟到回执。已发出的取值动作可在 Hub 完成。普通文件图谱和显式 MuPRO HDF5 路径沿用各自读取器。

固定起点为实际 Web 产物已显示另一工作区的任务第 2 步，队列仍选任务 A。真实本机 Hub、NodeAgent、Runtime、Chromium 软件渲染，中文 1440×900 和 390×844。两种尺寸都实际点选图层 1 次，输入坐标 3 次，再点「查询原始值」1 次。旧版对两个同名发布文件取根目录值 `[0.125, 0.125, 0.125]`。新版只发一条绑定任务的清单读取并提示歧义，零取值请求。唯一发布文件时发同一绑定的清单读取与取值动作各一条，读取 `case/Polar.00000002.dat` 并返回 `[0.34765625, 0.40625, 0.34765625]`。点选阶段零新增清单与取值请求，两端均保留一个画布。Runtime 只有夹具的三项任务。收据和截图在外部 `root-delivery-20261110-146/graph-probe-browser/{baseline-exact,integrated}`。

独立最终产物及 Root 生产构建通过，完整 Web 均 186/186，零跳过。独立 Runtime 及 NodeAgent 对照另覆盖内联步号 3 实际解析成 2、自动目录歧义与已明确目录。模拟 Hub 验证旧读取路径、延迟回执隔离及相同宽窄屏操作。Root 核对补丁逐字节一致，暂存扫描零发现。原生桥的同名串读和字面步号问题已用真实本机图谱 worker 复现，修复在独立 worktree。原生侧栏直接打开完整保存问答也在另一独立 worktree 验证。

远端 `a64941b4` Linux Desktop 2205/2205，Linux 安装包和冒烟通过，Runtime 13/13。macOS 和 Windows Desktop 作业仍在运行，本地提交待其终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42908396134) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42908396193)

## 2026-11-10 22:13 UTC · Windows PDF 捕获生命周期与图谱探针取证

`2a8afa4a` 集成独立候选 `78bb2f8a`。Windows 报告 PDF 原生验收为同一窗口保留一个 WGC 捕获目标。窗口销毁、目标关闭或宿主身份变化会使旧目标失效，窗口重开后重新绑定。每次取样仍创建新的图形设备、帧池和会话。新增目标创建与复用计数，原 20 轮、160 张图片和每阶段连续有效取样门槛照旧。此前远端 `9ce87c63` 在第 5 轮 PDF 重开的 `CreateForWindow` 同步调用耗时 120038 ms，返回 `0x8007041d`，零采样。新实现首次绑定仍使用该系统调用，实际 Windows SDK 构建、计数和像素结论待目标 CI。 [Microsoft 捕获会话](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture) [原失败工件](https://github.com/sijintech/stk/actions/runs/42895759127/artifacts/13806041518)

Root 核对集成补丁逐字节一致，Linux 构建四个相关目标，像素、证据门和 AX CPU 共 31/31，零跳过。按集成源码抽取 Windows 捕获目标逻辑，以模拟 Win32/WinRT 接口独立编译并通过 7 项，覆盖相同窗口复用、换窗、跨线程关闭、数值句柄复用和初始化失败。暂存密钥扫描零发现。收据在外部 `root-delivery-20261110-146/windows-capture-root`。

Web 图谱在真实本机 Runtime 和 NodeAgent 复现了同名文件串读。已显示图谱来自任务子目录的 `case/Polar.00000002.dat`，探针却返回根目录同名发布文件的 `[0.125, 0.125, 0.125]`，图谱实际源文件的对应值为 `[0.34765625, 0.40625, 0.34765625]`。更换发布清单顺序会改变现行猜测。另确认内联字面步号 3 可实际解析到第 2 步。基线复现 1/1，修复在独立 worktree 进行，优先绑定当前画面的读取节点、实际步号和唯一发布路径。

远端 `a64941b4` Runtime 13/13 全部成功。Desktop 的 Linux 包与安装冒烟成功，整轮仍在运行。本地提交等待上一轮 Desktop 终态。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42908396193) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42908396134)

## 2026-11-10 22:03 UTC · Web 明确读取 MuPRO HDF5

`db432922` 集成独立候选 `1dd5d2e8`，并保留本地任务页运行环境折叠。Web 的成功 Runtime 任务有唯一 `case/run.h5`、发布摘要和有效大小时，图谱顶部提供「MuPRO HDF5」。明确列出后，用户选择读取器返回的场与确切步号，多分量场再选从 0 开始的分量。列表与帧请求都绑定原任务和整个容器的摘要。原生 shape 和 dtype、网格坐标及未知物理单位在面板中显示。Viewer 接纳实际图层后才更新来源，摘要不符、无效列表、错误步号、失败图层或迟到回执保留当前画面。两次明确读取可在 Hub 操作记录追踪，选项编辑不会发起求值。

独立候选构建、字段请求与数值对照 3/3、最终完整 Web 174/174。首轮一个既有日志用例在模拟时钟准备阶段遇到向过去快进，原用例双宽度 2/2 及完整重跑通过。Root 整合生产构建及 Web 180/180，零跳过及重试。旧版底部入口在固定起点未完全进入视口的反例已复现，上移后五个交互检查点的外层和窗口滚动均为 0。确切补丁、构建与回归收据在外部 `root-delivery-20261110-144/web-mupro-hdf5` 与 `root-delivery-20261110-145/web-hdf5-root`。

Root 以整合产物连接真实本机 Hub、NodeAgent WebSocket 和 Runtime，使用合成 HDF5 生产任务及另一个普通 DAT 任务。中文 Chromium 1440×900 和 390×844，固定起点为成功任务已选、结果图谱已打开、外层滚动 0。打开矢量帧两端均为 4 次点击、1 次字段选择和1 次分量输入，零滚轮，所有目标操作前都完全在视口内。选择 `/t00000002/Polar` 的分量 1，容器另有第 4 步。来源显示正确任务、运行工作区、SHA、selector、分量及第 2 步。随后打开同一第 2 步 Scalar，验证单分量路径，再切换到普通 DAT 预设。每端只有列出、矢量打开、标量打开、DAT 计算四项明确图谱动作。来源展开及收起没有新增动作。API 数值对照核验两组各 24 个原始 `float32` 体素。该验收使用合成产物和软件渲染，真实许可求解仍待验证。实测收据在外部 `root-delivery-20261110-144/hdf5-live-proof/integrated-browser`。 [使用指南](https://github.com/sijintech/stk/blob/main/docs/simulation-muferro.md#mupro-hdf5-结果补充)

原生 `8947053d` 的最终完整项目套件 967/967，零跳过与失败，887.629 秒，证据在外部 `root-delivery-20261110-144/native-current-full.*`。远端 `main` 仍为 `a64941b4`。该头两项 Linux 打包、Secret scan 和 Pages 已通过，Desktop 其余作业及 Runtime 仍运行。本节 HDF5 入口在本地 `main`，下一次推送等待该头的整轮 Desktop 终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42908396134) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42908396193)

## 2026-11-10 21:49 UTC · 主线发布与任务页运行环境

远端 `main` 已由 `9ce87c63` 快进至 `a64941b4`，推送后核对全 SHA 一致。上一批 Desktop 整轮终态见下一节。推送范围 15 个提交的 gitleaks 通过。新头 Secret scan 通过，Desktop 与 Runtime 已开始。原生阅读位置、Web 图谱真实来源、MuPRO HDF5 三跳验收及可选 Cocoa 对照均包含在本次推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42908396134) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42908396193)

`629f964b` 集成 `528d6715`。首次有效工作区选定后收起 Web「运行环境」，标题保留节点与工作区。焦点原在收起的控件中时回到标题，外部焦点和滚动保留。手动开合沿用用户选择，自动收起后失去范围会展开恢复，重新选择后由用户决定开合。队列顺序和既有任务入口保留。独立定向 18/18，独立及 Root 完整 Chromium 各 171/171，零跳过及重试，生产构建与扫描通过。

模拟 Hub 的中文 1440×900、390×844，固定起点为首次选定节点、工作区及队列任务，队列外层滚动 0。宽窗的 1 行、200 行和窄窗的 1 行队列都以 1 次点击打开「新建任务」，零滚轮。窄窗 200 行实际滚动 53 px，再 1 次点击打开。旧版部分路线须先收起高约 274 px 的运行环境，收起后约 42 px。四条路线测量无新增请求或动作，所选任务、草稿及返回位置保留。焦点、手动展开、项目切换、节点撤销和重选另有定向回归。收据在外部 `root-delivery-20261110-144/tasks-environment` 与 `tasks-environment-root`。该提交已在本地 `main`，发布待 `a64941b4` 的整轮 Desktop 终态。

Web MuPRO HDF5 明确入口在另一独立 worktree 开发。Root 的真实本机 Hub、NodeAgent 和 Runtime 合成夹具验证 `case/run.h5` 第 2 步的单分量场和显式选择的 Polar 分量 1，各 24 个 `float32` 体素。元数据只从发布摘要对应容器读取，另含第 4 步用于排除默认末帧。保留普通 DAT 任务作为浏览器兼容对照。API 收据在外部 `root-delivery-20261110-144/hdf5-live-proof/api-baseline`。真实许可求解与研究参数仍待验。最新原生项目全量测试继续运行。

## 2026-11-10 21:46 UTC · 上一 Desktop 批次终态

远端 `9ce87c63` 的 Desktop `42895759127` 整批终态失败，4/6 作业通过。Linux 主作业 2201/2201、两个 Linux 打包、Windows CPU 1506/1506 均通过。macOS CPU 1566/1566、Metal 254/254，原生必测 4/6，媒体和可选对照的阶段见下一节。同头 Runtime 13/13，Pages 和 Secret scan 通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42895759127) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42895759007)

Windows 原生 5/6，零跳过。PDF 完成 4/20 轮并有 39 张验收图片。第 5 轮 `reprepared-page1` 的 WGC `capture.create-for-window` 返回 `0x8007041d`，同步调用 120038 ms，捕获启动总计 120060 ms。失败时 1 次捕获请求，零轮询、零采样和零宿主帧。视口已就绪，第 5 轮前七张图片摘要已核对，最后为关闭预览图。重开阶段没有新像素可判定。此阶段和错误码与既有 WGC 阻塞记录一致，两次发布间 Windows 报告承载、PDF 夹具和捕获实现源码无变化。两项视频均完成 20/20 轮，各 161 张图片。两个 OS 工件均核对完整归档 SHA-256。 [Windows 作业](https://github.com/sijintech/stk/actions/runs/42895759127/job/130137120764) · [Windows 工件](https://github.com/sijintech/stk/actions/runs/42895759127/artifacts/13806041518) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42895759127/artifacts/13804850740)

终态和工件已记入验收，主线推送门禁满足。待发布版本包含统一工作台返回、阅读位置、图谱来源、合成 HDF5 三跳验收及可选 Cocoa 取证。发布前工作树中的所有者未提交内容保留，上一远端至待发版本的提交范围扫描通过。

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

`e3e69af9` 集成实际 Claude89 `9483afc3`。Web「来源」分行展示节点、项目、任务名称与完整 ID，并区分当前显示和待加载文件。图谱在各自面板绑定来源。结果正文里的长摘要限制行数，完整值在可滚动详情中可用。Tab 离开、打开历史或切页会收起详情，Esc 和明确关闭归还焦点；离开字段时清理该字段自动选中的文本。Root 整合版 Chromium 103/103，零跳过。

远端 `693e7ea4` Runtime 13/13，Linux Desktop 2195/2195 和两个 Linux 打包作业通过。Windows CPU 1505/1505，逐项确认上一轮的六项默认窗口快照已通过，必测 Python 校验匹配 1197 项。macOS fmt 下载 HTTP 429 在构建前失败。截至本记录，Desktop 仍在运行，Windows 原生内容是唯一进行中的作业。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [Windows CPU 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021210081) · [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130049729774)

Claude90 已排队，从 Root `e3e69af9` 接手 Web 文件与图谱互切时的 Viewer 保留，等待 Claude89 在独立 worktree 完成交接。Root 负责双端集成和 CI 门禁。

## 2026-11-10 18:43 UTC · 窄窗结果取景与 Web 结果来源

`4e4bf6e9` 在聚焦任务明确打开新结果时为窄窗的默认预设首次取景，依据当前视口使用已发布的 View All 计算。作者数值相机、非默认缩放、工作区相机和显式预设沿用原优先级。原生交互分类图例加对比底色，导出图像沿用原图例绘制。Jobs 53/53、相机 10/10，OpenGL 与 Vulkan 各 5 个 Viewer 验收组均通过。定向 GPU 回归确认交互图像出现底色、相同相机的导出像素一致。

`9d8891c4` 集成实际 Claude88 `625ce3c2`（独立测试 95/95）。Web 结果页显示所选任务的节点、项目与名称，以及 Viewer 当前显示的文件。选中另一文件时保留旧画面及其来源，明确加载成功后才更换。探针、构建回执、错误与复核提示按已显示场景或有效请求绑定；过期的排队轮询停止，认证错误仍断开会话。回执携带来源时核对任务和文件，兼容无来源字段的旧回执。任务日志与文件、图谱探针分别保留。进入另一种结果模式清除原图谱的探针输出。Root 集成版 Chromium 99/99，零跳过。

远端 `693e7ea4` Runtime 13/13，Secret scan、Pages 及两个 Linux 打包作业均通过。Linux Desktop 2195/2195，逐项确认上一轮 6 个默认窗口和 2 个任务页快照修复。macOS 作业 130021209994 因依赖 fmt 补丁下载 HTTP 429 在构建前失败。截至本记录，Desktop 仍在运行，Windows CPU 测试进行中，原生内容作业待该构建包。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [Linux 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021210004) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42870793242)

Claude89 已在独立 worktree 启动，基线为 `9d8891c4`，负责 Web 结果来源的按需详情与键盘、触屏可用性。Root 负责统一原生入口、集成和平台验收。

## 2026-11-10 18:22 UTC · 聚焦任务结果、Web 队列和平台诊断

`e210227d` 从原生聚焦任务页直接打开所选任务的结果，复用该窗口的 Viewer 与一级导航。回调核对窗口、编辑器、连接、节点、工作区和任务身份及代次。激活成功才打开结果，较早排队的打开请求由当前点击取代。传统分栏仍使用原入口。Jobs 53/53，新增回归覆盖创建工作区期间失效的请求及打开结果的顺序。项目导航回归 36/36，零跳过。

`2de31dc0` 集成独立 Claude87 末版 `4ad74e25`。Web 任务页先显示队列、已选任务、快捷操作和待复核项，运行环境与新建任务收进详情。运行环境首次展开便于选节点，手动折叠随页面切换保留。Root 加入独立滚动上限，200 条任务仍可看到已选任务状态及运行环境入口。提交与审批沿用现有明确操作，任务、TaskSpec 草稿和 Viewer 在切页时保留。构建与整合版浏览器回归 87/87，零跳过。

`a9cefe9e` 合入隔离 Windows 捕获诊断 `d41795d5`，分别记录 CreateForWindow 的原始调用、HRESULT 转换和退出清理耗时。旧聚合字段、输出上限及验收规则保留。便携计时夹具及证据门 12/12 通过，Windows SDK 构建与实际捕获仍待目标 CI。本轮本地待发提交与远端 `693e7ea4` 分开记录。截至本记录，Desktop 仍在运行，Runtime 仍在运行，13 个作业中 11 个已通过。macOS 作业 130021209994 在 vcpkg 下载 fmt 补丁时多次返回 HTTP 429，配置、构建、CPU、Metal 和原生验收均跳过。Secret scan 与 Pages 通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [macOS 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021209994) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42870793242)

Claude88 已在独立 worktree 从 `4ad74e25` 接手 Web 结果的来源展示和探针绑定。Root 负责集成、双端验收和 CI 门禁。PR #53 的对应主线续传回归定向 3/3，旧补丁仍冲突。PR #54 仍是九月的旧交接快照。

## 2026-11-10 18:00 UTC · 原生智能体会话历史与 Desktop 门禁

`9bc9b771` 将原生工作台历史分成普通问答和智能体会话。工作台、任务与结果共用入口，按对应账本的精确 ID 读取。相同 ID 文本、迟到的读取回执和旧窗口回调由定向回归覆盖。读取失败可点击同一条记录重试，已有发送或待确认回执时禁用历史选择。Root 在独立 worktree 的 Claude86 修订 `dd91cf9f` 上整合界面、同条重试与导航回归。Claude 的控制器定向 20/20 通过，旧基线全量 2159/2167，8 项为已定位的旧布局快照。Root 整合版原生定向 82/82 通过，零跳过。

上一远端源码头 `79ea12f4` 的 Desktop CI 于 17:54:33 UTC 全部结束，6 个作业中 2 个打包通过、4 个失败。Linux 2174/2182、macOS CPU 1547/1553、Windows CPU 1487/1493，失败分别为 Linux 6 个窗口与 2 个任务快照、macOS 与 Windows 各 6 个相同窗口快照。本地 `15a5830a` 与 `bb812b60` 修正对应快照，定向通过 51/51 与 88/88。macOS 的 Metal 原来随 CPU 失败跳过，导致报告检查缺少 XML。`dc48679b` 在成功构建后独立运行 Metal，保留已有 CPU、Metal 与报告校验失败判据。Runtime 13/13，Secret Scanning 和 Pages 均通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

同一轮 macOS 原生内容 4/6，MP4 隐藏保持与 HTML video 首次明确暂停的时钟超差。可选隐藏探针 0/2，帧时钟探针 1/2。`0c239b42` 调整可选诊断，下一轮实机待验。Windows 原生内容 5/6，PDF 第 20 轮重新准备第一页时捕获启动失败。序列 433 的 `capture.create-for-window` 返回 `0x8007041d`，启动调用总耗时 120059 ms，像素验收随之超时。PDF 19/20 轮完成，两个视频通过。原生内容均零跳过。本地 Linux 回归和实窗完成，macOS 和 Windows 原生结果仍需按新源码头确认。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/129975239887) · [Windows 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/130004878783)

Claude87 已在独立 worktree 接手 Web 任务页队列优先，将运行环境和新任务放入按需展开区。Root 负责统一入口、点击数、状态保留和双端集成验收。PR #53 与 #54 仍分别是冲突的旧补丁和旧交接。

## 2026-11-10 17:25 UTC · Web 会话历史与原生智能体读取保护

`1bc557e6` 集成实际 Claude84 `86671b81`、Claude85 冻结修订 `d5ce6399` 和隔离修正 `5ae21b15`。工作台、任务、结果都能打开只读历史，按会话保留本页草稿。新会话由首次明确发送写入，缺失会话可移出草稿。两种历史与发送回执顺序按消息 ID 合并。结果不明确时，本页先按原 ID 重试，再发送新草稿。Root Web 构建与 74/74 回归通过。Claude85 最后在独立 worktree 以 `51bea8f1` 结束，它独立覆盖了反向回执顺序，整合版的同一行为与缺失、重试保护均有对应回归。跨设备重试仍沿用 Hub 当时的会话上下文，未保存草稿和待重试 ID 存于当前页面。

`8424b230` 集成 `f5f345a9` 的可选 Hub 标题查询。默认名称用首条已保存问题的短标题，显式名称优先。旧版 Hub 沿用原名称。单条查询内读取，保留旧列表字段、权限和排序。整合后 Web 75/75、Hub 53/53，零跳过。

`c229a3ae` 在原生 AI 会话页确认选中的智能体会话读回后，才启用发送与设置运行目标。控件回调再次核对身份，读取中或缺失时可继续保留草稿。固定起点为已打开合成项目的会话页，严格桥接夹具设置待确认的会话 ID，覆盖读取中及服务返回缺失后的禁用与回调，定向回归 36/36。此处为控件验证，指针点击路线沿用之前实窗。实际 Claude86 已从 `fad1d757` 在独立 worktree 开始修复读取代次，原生侧栏接入智能体会话仍待该修订与集成。

远端 `79ea12f4` 的 Runtime 13/13 通过。Desktop 的 Linux 作业完成，共 2182 项，2174 过、8 失败、零跳过。逐项确认 6 个默认窗口与 2 个普通任务布局快照，分别对应本地 `bb812b60` 与 `15a5830a` 修正。两个 Linux 打包作业通过，整轮 Desktop 仍在运行，本批留在本地等待门禁。PR #53/#54 维持旧冲突补丁与旧交接状态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Linux 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/129975240714) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 17:09 UTC · 聚焦任务队列与回归基准

`fad1d757` 把聚焦任务页的队列放在上方。当前连接、节点和工作区显示在运行环境标题中，展开后使用原配置。新建任务按需展开，提交和重试由表单中的明确按钮触发。任务详情、取消确认和原有分栏入口仍可用。

扩大套件后，发现此前导航变更遗漏了普通任务页和默认窗口的 JSON 快照。`15a5830a` 与 `bb812b60` 集成 `feabc7a0` 和 `902a414c`，更新 8 份经旧基线复现的快照。结构差异是顶部工作台入口与零尺寸导航区域，普通任务页原控件、既有区域尺寸和其余块经结构化比较一致。Root Jobs 51/51、窗口管理 88/88、工作台与工作区 54/54，零跳过。独立 OpenGL、Vulkan、属性表单和 Viewer 图像对照通过，保留原图像基准。

`0c239b42` 集成 `9951a89b`，用现有两个可选 Cocoa CI 槽位观察原片首次真实工具栏暂停。请求前等待 270–290 ms，记录原生派发与分段 DOM 读数。原强制 6 项、20 轮和断言保持。Linux 对象、4 组条件编译及原生 AX CPU 1/1 通过，实际 Cocoa 结论等待对应平台。

实际 Claude85 在独立 worktree 提交 `d5ce6399`，正在完成测试复核。独立审阅发现旧 POST 回执先到时可能压掉含较新消息的历史读取，已确认会话缺失时仍有旧创建授权，以及先发下一条会覆盖待重试消息。从该冻结候选另建隔离修订，完成前暂缓集成。Claude86 任务已排队，待前一 CLI 终态和精确 worktree 检查后处理原生智能体会话读取代次。

远端 `79ea12f4` 的 Desktop 仍运行，两个 Linux 打包作业已过。Runtime 已有 11 个作业成功，整轮仍运行。本批代码已提交到本地，待上一 Desktop 整轮终态再推送。PR #53 仍冲突，#54 仍是旧交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 16:52 UTC · 原生近期问答导航

`159a21a6` 集成 `e88fd9f6` 的原生只读近期问答缓存及导航。支持当前项目和新桥接口时，宽屏左栏显示最近保存的未归档问答，窄窗用历史菜单。从任务、结果或工作台选择即打开原问答。列表变化时旧弹出菜单关闭。同项目打开期间共享一次在途读取，旧项目回执不能替换当前列表。Root 定向原生回归 62/62，零跳过，覆盖归档更新、旧回执与原编辑器复用。

Claude85 正在独立 worktree 从 `86671b81` 修订 Web 历史回执和重试。后续仍需接入智能体会话并验证不同会话身份，桌面任务页的运行设置和表单也待整理。已安排独立原生诊断候选复用现有 macOS 可选 CI 槽位，比对首次可见暂停的工具栏触发时序。强制原生门禁沿用原测试。

前一批已推送 `79ea12f4`。推送前核对 `3c4f9bf9` 整轮终态，Desktop 5/6 作业通过。Linux 2177/2177、Windows CPU 1488/1488、Windows 原生 6/6。macOS 原生 4/6，首次可见暂停失败见上一节。`79ea12f4` 的 Secret scan 与文档部署通过，Desktop 仍运行，Runtime 排队。本节的近期问答提交仅在本地，待 `79ea12f4` 的 Desktop 整轮终态后推送。PR #53/#54 的原头分别为旧冲突补丁与旧交接，均未集成。 [新头 Desktop](https://github.com/sijintech/stk/actions/runs/42857730640) · [新头 Runtime](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 16:43 UTC · 上一远端头 Desktop 终态

远端 `3c4f9bf9` 的 Desktop 于 16:43:32 UTC 整轮结束，6 个作业均到终态。Linux 三个作业、Windows CPU 与 Windows 原生通过，macOS 原生必验失败。macOS CPU 1548/1548、Metal 254/254。原生必验 4/6，MP4 与 HTML 均在首次可见暂停低于 0.05 秒下限。两份 270–290 ms 被动延迟对照均在观察窗口内取得稳定暂停。Runtime 13/13 已通过。本次终态满足推送前提，随后推送截至 `4442342e` 的已验证批次及本记录。新头的桌面平台验证以其自身 CI 为准。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42845291750) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42845291916) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42845291750/artifacts/13783327194)

## 2026-11-10 16:38 UTC · 聚焦会话详情与精确问答返回

`a8d80a9a` 将原生聚焦工作台的数据范围与模型设置收在按需展开面板。问答和输入框优先显示。空项目入口使用按文字内容计算的按钮宽度。`6e18a3b1` 集成候选 `1338781b`，从项目首页的问答提醒读取对应请求，保留未发送草稿与新问题的数据范围。“已查看”由独立按钮处理。Root 原生集成回归 53/53，零跳过。

`1fa0baec` 集成 `f2c721cf` 的本地只读 Bridge `project.requests.recent`。接口按保存顺序从新到旧返回未归档问答，默认 8 条，最多 20 条。旧列表仍按原顺序分页。Root Bridge、请求、归档、智能体与脚本回归 179/179，零跳过。原生侧栏接入仍在后续。

实际 Claude84 以 `86671b81` 正常结束，Web 构建和 46 项回归通过，补齐初次读取确认之前的发送限制。Root 审阅发现真实 Hub 会先保存问题再交付回执，现有 mock 缺少此时序。暂缓集成。实际 Claude85 从 `86671b81` 在独立 worktree 接同 ID 重试、旧回执合并、历史去重、缺失会话草稿和窄屏遮罩焦点。Root 下一步接入原生近期问答侧栏，继续使用已有的精确返回护栏。

## 2026-11-10 16:19 UTC · 聚焦工作台收起技术页头

`7282342a` 将编辑器选择、技术标签和区域菜单移出原生聚焦工作台的页头。工作台保留首页与项目，任务保留提交与刷新，结果保留打开、叠加层、全部显示和导出。通过分栏视图恢复专业工具。原生定向回归 50/50，零跳过。

Claude84 在独立 worktree 继续 Web 会话历史及每会话草稿。Root 审阅时发现原生项目首页的问答提醒已带 `request_id`，入口仍只传页面名。已安排独立候选修复精确返回，原生历史侧栏和跨端来源返回仍待集成。

## 2026-11-10 16:10 UTC · 双端左栏、首次启动与只读会话历史

`67a6fd3f` 增加 Hub 只读会话历史。存在时返回原会话及消息，缺失返回 404，旧会话入口和显式发送兼容。Hub 定向 52/52。`82fc9d43` 集成 Claude82/83 的三页 Web 导航。结果和日志捷径一次显示对应内容，晚回执沿原任务更新，保留当前页和 Viewer。Root 构建与 Chromium/Node 全套 22/22。

`6a562d2e` 原生宽屏用左栏，700 逻辑像素及以下用横栏。保留当前项目名、显式分栏入口及原编辑器。

`1a3ef021` 无保存布局时打开工作台。聚焦布局重开保留当前页，显式 `--open` 在新工作台和已保存的聚焦工作台直接显示结果。旧普通最大化和显式分栏照原状态恢复。原生导航、工作模式、工作区和传输回归 50/50，零跳过。

长日志修订 `8a80dc8c` 集成实际 Claude83 后续 `45fc1059`。点击时给日志预留有界空间，迟到日志原位更新。宽窄屏各验证离开再回到结果页与用户滚动后的稳定性。Root 最终 Web 28/28，含 17 项 Chromium 合成回归和 11 项 Node 测试。

实际 Claude84 从 `8a80dc8c` 在独立 `claude/unified-workbench-web-history-84` 接会话历史侧栏、每会话草稿及异步回执保护。Web 当前会话读取仍沿用旧入口，新历史界面接入只读路径待集成。原生项目会话历史、精确来源返回及收起技术标签仍是后续。

## 2026-11-10 15:42 UTC · 统一工作台首片验证

本地 `058b1555` 复用 AI、Jobs 和 Viewer。点工作台进入聚焦导航，依次显示工作台、任务、结果。分栏视图恢复原区域树。普通最大化和读取已保存布局沿用原入口。工作台导航已在原生顶部验证，左侧项目与会话导航、默认布局和按需详情仍为双端下一片。

实际 Claude82 `0e17ecea` 的 Web 候选使用同序三入口、宽屏左栏、窄屏横栏。两种 Chromium 合成窗口检查通过，验证隐藏面板持续挂载、草稿及 Scene v1 回到原任务。Root 审阅发现明确的结果和日志动作要直接展示内容，延迟视图回执应保留当前页面。实际 Claude83 在独立 worktree 修订，待审阅集成。

## 2026-11-10 15:30 UTC · 原生执行预检、CI 夹具与统一工作台方向

`9216d7cb` 在项目的材料仿真中增加默认折叠的执行环境检查。一次明确点击保存请求，再向所选 Runtime 提交单 CPU 诊断。面板可见时读取原任务，重开从本机记录恢复。晚回执按项目、连接、编辑器与父子面板代次核对。指南由实际 Claude80 的 `ae5a82e0` 经 root 审阅集成。 [桌面指南](mupro-desktop-preflight.md)

所有者要求简化 STK 并统一 Web 与本地客户端。以 Synthrix `caec2b9` 的统一主页面和 Codex 的会话工作方式为参照。首片共用工作台、任务、结果的顺序，保留现有会话、任务与 Viewer 实例。Root 负责原生聚焦及分栏恢复。实际 Claude82 已在独立 `claude/unified-workbench-web-82` 接 Web 导航，候选待跨端审阅。项目与会话侧栏、默认布局和详情的统一继续实施。 [统一工作台](design/unified-workbench.md)

既有试点任务及科学验收继续按依赖推进。实际点击和目标系统 CI 见[运行验收](runtime-validation.md)。

## 2026-11-10 03:29 UTC · 诊断请求持久化、严格 Bridge 与前一 CI 终态

`5e377de0` 集成实际 Claude78 `81185683` 的共享预检客户端/未注册适配器，以及独立 `669b523b`、`f046d791` 的诊断 journal，并发布五个 Bridge 方法 describe/list/reserve/retry/refresh。记录在项目外持久化，固定原运行环境、工作区选择、资源和请求键。reserve 纯本机保存 prepared；原生调用方必须先得到持久确认，再在原视图仍有效时发送明确执行请求。丢 reserve 回执不会留下排队执行。重开、列出和刷新均不重提，未知回执只允许沿原 ID/原键明确恢复；已知任务 retry 零 POST。新工作区创建也使用稳定派生键。坏 journal 仅让预检不可用，不删除数据，不阻止其他 Bridge 模块启动。未增 Agent 工具、项目格式或放置权限。 [桌面诊断契约](specs/mupro-preflight-desktop-1.md)

前远端 `37e48356` Desktop `42732315824` 于 2026-11-10 01:58:24 UTC 终态 failure，六个作业全部结束、四成功。Linux 主测 2170/2170、两个打包作业成功；Windows CPU 1488/1488、零跳过，工作区 18/18 和 guarded 7/7 全部具名通过，上一轮四项路径失败已恢复。macOS CPU 1548/1548、Metal 254/254，主原生仍 4/6；独立 Windows 原生实际 5/6，不能沿用前头全过。同头 Runtime `42732316049` 终态 13/13，Secret scan/文档部署成功。整轮结束满足本批已验证后端提交的推送前提；本节随本批交付，新的精确头 CI 结果待验。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42732315824) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42732316049)

原生面板仍为未提交候选：root 增加独立 workspace 选择与事件/目标代次，直接调用 Bridge，不复用 Jobs 的选择或 Script 执行。独立真实回归已证明旧候选在折叠及折叠再展开、未绘制下一帧时会误发一次 retry；root 已补事件即时 panel epoch、原 ID 绑定及新建工作区自有选择，等待最终新 ABI 定向与真实窗口验收，不称界面已交付。当前无本地 CI 观察器，后续按同 run 的官方状态复读。实际 Claude80 已从 `b7aa88fa` 在独立 worktree 写一份用户指南，root 保留 UI/契约/集成/推送职责。PR #53/#54 头仍 c9f13994/2dd3e4ee，原冲突未合入。真实软件/研究参数、HDF5-only 完成、H2 和分析提案持久形式等待决保持。

## 2026-11-10 01:32 UTC · 显式执行环境预检与原任务回执

本地 `8d3752ff` 与 `1c8c2dcf` 完成显式 Runtime 执行环境预检。客户端提交固定单 CPU、空输入及空环境覆盖的诊断任务，在 worker/调度环境使用该端自己的配置；不启动 MuPRO/MPI 或签出许可。`preflight-result` 只读原任务，按固定规格、连接、终态/退出码、唯一产物大小/SHA-256和严格内层格式核验。失败检查仍有 failed/1 的有效观察，取消、执行故障、错接规格与未知状态不冒充成功；丢提交答复只允许明确同键同请求重试，零自动重提。本机 `check` 原含义、运行/收集链及 Agent 权限保持。 [任务回执契约](specs/mupro-preflight-task-1.md)

已推送远端 `37e48356`。截至 2026-11-10T01:31:10+00:00，同头 Runtime `42732316049` 已终态 13/13；Desktop `42732315824` 仍运行，Linux 主测 2170/2170，工作区 18 项及 guarded 7 项均具名通过，两个打包作业成功；macOS 和 Windows CPU 尚未终态。Secret scan、文档部署已成功。上述两个新的远端预检实现提交仅本地，等待 `37e48356` 整个 Desktop 终态后再推送。当前远端 CI 只含上一批本机预检和 UI/路径修正，不把它当新增远端诊断代码的验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42732315824) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42732316049)

实际 Claude78 已从冻结 `1c8c2dcf` 在独立 `claude/mupro-preflight-bridge-78` 接下一模块：共享纯客户端读取/提交逻辑及未注册的桌面 Bridge 适配器。root 负责方法注册/契约、原生仿真面板、目标切换/未知回执状态、最终回归和推送。该适配器与原生按钮尚未交付，不称桌面已可检查。新流程未做产品窗口点击验收；既有文献双布局 8→6 点击回执保持。真实 MuPRO 资产/科学参数、HDF5-only 完成证明、H2和分析提案持久形式仍按原待决；PR #53/#54 原冲突差异未合入，Cocoa 视频问题继续以原强制门禁验收。

## 2026-11-10 00:57 UTC · MuPRO 本机预检与前一 Desktop 终态

`000bb6ff` 新增显式本机 `suan mupro check --json`，发布 `stk.mupro-preflight/1`：复用既有采集一次，输出固定检查项、保守总结、进程/组件版本与采集时间，排除路径和原始诊断。所有总结均保留软件版本未观察、许可未签出、求解器未运行。原 `python -m suan.mupro check` 诊断和退出码保持。命令会 source 已配置的受信任脚本，不能作为被动 health/graph.meta 读取或所选远端机器的就绪证明。

`5fe4e6d7` 修正 Windows 回归夹具的期望路径，使用词法规范化及 UTF-8 转换，并为新来源等待超时加入状态诊断；不改产品路径行为。旧头 Windows CPU 共 1488 项，1484 过、4 失败、零跳过。三项日志直接证明同一路径的分隔符比较错误；第四项同样使用该谓词并超时，旧回执不能证明其最终来源状态。本地相关 18/18，实际 Windows 修正结果待本批新头 CI。

`ae5090dc` 集成实际 Claude75 `239fc81e` 的可选原片时延对照：保持同一 seek/可见历史，只在 play 返回后普通非阻塞事件泵等待固定 270 ms，期间不作 DOM/媒体采样或 OS 截图。root 增补实际暂停请求和原生派发均落在 270–290 ms 的有效性门，超界保留原始观察但不计有效对照。原强制六项门禁、执行器及看门狗阈值不变。Linux 构建、探针开/关及 Linux/Apple 宏四种语法检查、相邻轮询 CTest 1/1 通过；两个夹具摘要未变。Apple 宏检查不是 Apple SDK 或 Cocoa 运行，目标结果待新 CI。

远端前头 `ba03ac8d` Desktop `42722834184` 于 2026-11-10 00:52:20 UTC 终态 failure，6 个作业全部结束、4 成功。Linux 主测 2169/2169、两个打包作业成功。Windows CPU 结果及修正见上；独立原生 6/6、零跳过，六源各 20/20 轮，PDF 八阶段各 20 次记录且 Viewer/草稿保护通过。macOS CPU 1547/1547、Metal 254/254，主原生仍 4/6。整轮终态满足本批推送前提。同头 Runtime 13/13：Linux 3.11/3.14 各 6634 过、166 跳过，3.12 为 6651 过、149 跳过，均另排除 4；Windows 3.11/3.12 各 5311 过、275 跳过、936 排除。原固定派发来源断言在三个 Linux 版本具名进度均通过。本节随已验证的文献单击打开、Python 面板回归、本机预检及修正提交交付，新的精确头 CI 仍待验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42722834184) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42722834173) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42722834184/artifacts/13724407825)

本头 HTML 原片的隐藏/可见配对均观察到 DOM 时间回到 0.102 秒，可见组原生已验证暂停；MP4 对照在初始显式暂停失败，不能当作完成了新鲜配对。独立帧号夹具两源均 no_clock_reset_observed，8 张 PNG 的摘要及帧号核验通过，但夹具与捕获时延共同变化，仍未解决原产品 4/6。本批 CLI 与诊断未新增产品 UI 交互，文献实际双布局 8→6 点击的既有验收保持。真实 MuPRO 主机/SDK/许可/研究参数、HDF5-only 完成证明、目标 OS 文献交互和分析提案持久形式仍待；H2 未代选。PR #53/#54 已重查，头仍为 c9f13994/2dd3e4ee，原冲突差异未合入。root 继续负责审阅、集成、推送和 CI，Claude 按独立 worktree 的限定任务配合。

## 2026-11-10 00:02 UTC · 文献命中单击打开与 Python 面板回归

`26644456` 将文献命中至引用页缩为一次明确点击；真实 X11 双布局均验证默认入口 8→6，命中至页图 3→1。`17685b5a` 补原生 Python 面板的受约束打开回归。 [运行验收](runtime-validation.md)

已推送远端 `ba03ac8d`，包含 `6333178e` Viewer 保护与 `83302698` Runtime 旧断言修正。截至 2026-11-10T00:00:46+00:00，新 Desktop `42722834184` 仍运行，两个 Linux 打包作业成功；Runtime `42722834173` 已有 10/13 作业成功，其余矩阵仍运行，暂无失败。Secret scan 和文档部署已成功。上述新文献与面板回归提交仅在本地，等待 `ba03ac8d` 的整个 Desktop 终态后再推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42722834184) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42722834173)

实际 Claude74 已从冻结 `17685b5a` 在独立 `claude/literature-guide-74` 编写文献桌面使用指南，仅新指南文件；待 root 审阅。root 继续负责公共实现、验收、集成和推送。PR #53/#54 仍为 c9f13994/2dd3e4ee，旧冲突差异未合入；原路线和 MuPRO 实际许可/科学参数等剩余条件继续保留。

## 2026-11-09 23:44 UTC · 前一 Desktop 终态与 Cocoa 帧号回执

远端 `5cb7cdb9` Desktop `42712877920` 于 23:39:58 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2162/2162，两个打包作业成功；Windows CPU 1481/1481，独立原生 6/6 且每项 20/20 轮、零跳过。macOS CPU 1540/1540、Metal 254/254，主原生 4/6。整轮终态满足本批推送前提。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42712877920/artifacts/13720252143)

新帧号控制已取得可核验 OS 截图；它未复现回退，仍不解决旧夹具失败。 [运行验收](runtime-validation.md)

本批推送包含已本地验证的 `6333178e` Viewer 失败保护与 `83302698` 固定派发来源证明断言修正。同头 Runtime 的 10/13 终态及旧断言失败已记录于上一节；修正后的三版本结果仍待下一远端头验证。实际 Claude73 在独立 worktree 补 Python 面板集成回归。root 同时开发文献命中单击打开，现有真实资产回归中两布局各由 37 降为 35 次点击，命中至页图 3→1；窗口验证和迟到回复回归仍在进行，产品改动尚未提交。

## 2026-11-09 23:23 UTC · 受约束打开保留 Viewer 与草稿

`6333178e` 完成带来源证明的候选验证与失败时 Viewer/草稿保护；等待接口支持唯一打开请求。 [运行验收](runtime-validation.md)

`83302698` 更新 MuFerro 固定派发测试，核对传入的完整来源证明。相关文件单独 30/30，最终已包含在上述联测。远端 `5cb7cdb9` Runtime `42712878022` 终态为 10/13 成功；三个 Linux 作业均仅在这一旧断言失败。3.11/3.14 各 6618 过、166 跳过，3.12 为 6635 过、149 跳过；均另有 1 失败和 4 排除。两个 Windows 客户端各 5296 过、275 跳过、936 排除。本地修正仍需下一远端头复验。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42712878022)

截至 2026-11-09T23:22:58+00:00，同头 Desktop `42712877920` 仍运行，4/6 作业成功。Linux 主测 2162/2162、两个打包作业与 Windows CPU 已成功；macOS CPU、Metal 及构建已通过，主原生步骤失败后仍继续诊断，新增帧号结果待工件。独立 Windows 原生仍运行。本地新提交尚未推送，继续等待整轮 Desktop 终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920)

实际 Claude73 已从冻结 `6333178e` 在独立 worktree 接 `CL-MUPRO-GUARDED-SCRIPT-73`，仅补 `script_test.cc` 的真实 Python 面板到原生 UI 操作验证；候选待交付与 root 审阅。root 继续负责实现、公共契约、集成、回归、推送和 CI。

## 2026-11-09 22:32 UTC · Cocoa 帧号诊断与前一 Desktop 终态

远端 `5cb7cdb9` 已推送，新 Desktop `42712877920` 与 Runtime `42712878022` 已启动。新查看来源校验、探针代次和帧编号诊断的目标平台结果随这两个精确头回执核对。 [当前 Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920) · [当前 Runtime CI](https://github.com/sijintech/stk/actions/runs/42712878022)

`dbc0ebbb` 已接入两项独立 Cocoa 帧编号诊断，目标平台验证随下一头运行。 [运行验收](runtime-validation.md)

前头 `75b20fc6` Desktop `42702711687` 于 22:24:01 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2159/2159，两个打包作业成功。Windows CPU 1478/1478，独立原生 6/6 且每项 20/20 轮，零跳过。macOS CPU 1537/1537、Metal 254/254、原生主测 4/6。当前 MP4 在首次显式暂停下界失败，HTML 在隐藏暂停下界失败。同头 Runtime `42702712232` 全部 13/13。整轮终态满足本批推送前提。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42702711687/artifacts/13715432852) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232)

Claude72 已从冻结基线 2b45ed81 在独立 `claude/guarded-viewer-open-72` 补受约束打开失败时保留原 Viewer 及参数草稿的回归，root 负责审阅和产品实现。现有异步打开在最终字节验证前清理旧来源，该路径继续验证。

## 2026-11-09 22:12 UTC · 探针代次与原生 MuPRO 查看回归

`3f36d736` 修复已完成探针回调跨选点/来源覆盖。MuPRO 查看链路增加真实原生 Bridge 与双后端离屏渲染验证。 [运行验收](runtime-validation.md)

远端 `75b20fc6` Runtime `42702712232` 已终态 13/13。Desktop `42702711687` 仍运行，3 个 Linux 作业与 Windows CPU 已成功，macOS 和独立 Windows 原生仍运行。本地新提交等待整轮终态再推送。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687)

Claude71 已在独立 worktree 提交可选可见帧编号诊断候选 `1525f17b`，仍在完成交付。root 正审阅诊断分类和截图证据落盘，候选尚未集成，实际 Cocoa 执行待下一头。

## 2026-11-09 21:54 UTC · MuPRO 查看源校验与 Windows 回归

`89ffacbd` 完成 MuPRO 收集来源到 Viewer、图缓存、探针与工作区恢复的文件摘要绑定。真实许可和目标平台界面继续验收。 [运行验收](runtime-validation.md)

已推送的 `75b20fc6` Runtime `42702712232` 全部 13/13 作业通过。Windows Python 3.11、3.12 客户端分别 5246 过、275 跳过、934 排除。两组的同 inode 同大小恢复 mtime 文件签名、真实 NTFS 联接的严格 Bridge 拒绝和原生 ChangeTime 三项目标均由官方逐文件进度、精确源码收集顺序及完整跳过记录映射确认通过。该工作流未生成具名 JUnit，映射经独立复核。同头 Desktop `42702711687` 仍运行，本地查看链路修复等待整轮终态再推送。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687)

实际 Claude71 在独立 `claude/cocoa-frame-clock-71` 从冻结基线 77c83814 开发可选可见帧编号诊断。独立合成视频和 OS 截图用于区分播放时钟回退与可见画面回退。旧固定视频和既有验收下界继续作为原验收依据，新的诊断仍待 root 审阅及目标 macOS 执行。

## 2026-11-09 21:27 UTC · 前一 Desktop 终态与 Cocoa 配对对照

远端 `a7fce899` Desktop `42692999966` 于 21:26:05 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2159/2159，两个打包作业成功。Windows CPU 1478/1478，独立原生 6/6 且零跳过。macOS CPU 1537/1537、Metal 254/254，主原生 4/6，视频与 HTML 的隐藏暂停下界失败。同头 Runtime 13/13。前头整轮终态已满足本批推送前提，当前 Viewer 修改继续作为未提交开发。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42692999966/artifacts/13711373511) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

## 2026-11-09 21:19 UTC · Project Runs 精确刷新与 MuPRO 文件身份

D1 `0e5112ed` 修复 Project Runs 精确刷新。MuPRO `3ae33035` 补齐文件变化时间和目录重解析点回归。Windows 目标平台与真实许可待验。 [运行验收](runtime-validation.md)

Claude69 已从 0e5112ed 在独立 worktree 开始 DAT Viewer 持久反例。已在合成运行中复现 Viewer 调用后用同大小、同 mtime 的改写改变图求值。待核对源证明在打开、后续步进和工作区恢复中的传递。

远端 `a7fce899` Desktop `42692999966` 仍在运行，4/6 作业通过。Windows CPU 1478/1478，macOS 原生对照及独立 Windows 原生仍运行。本地提交等待整轮终态。同头 Runtime `42692999627` 已终态 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

## 2026-11-09 21:03 UTC · MuPRO Bridge 发布结果校验

`f69edbe4` 把 MuPRO 文件校验移入 Bridge 结果发布，封住已复现的客户端提交边界。真实许可与 Windows 重解析点仍待验证。 [运行验收](runtime-validation.md)

远端 `a7fce899` Desktop `42692999966` 仍在运行，3 个作业通过。本地提交等待整轮终态。同头 Runtime `42692999627` 已终态 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

## 2026-11-09 20:45 UTC · MuPRO 收集文件登记一致性

`537b774b` 拒绝 MuPRO 收集验证后登记阶段的内容替换和路径重定向，保留同一任务恢复。真实许可与目标平台回归继续验收。 [运行验收](runtime-validation.md)

远端 `a7fce899` Desktop `42692999966` 仍在运行，2 个作业通过，本地提交等待整轮终态。同头 Runtime `42692999627` 当前 10/13 作业通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

## 2026-11-09 20:25 UTC · CLI 续读游标与前一 Desktop 终态

`4169e528` 修正 CLI 中断时的 UTF-8 字节续读，最终联测 120/120。MuPRO 结果收集一致性已复现并进入后续修复。 [运行验收](runtime-validation.md)

远端 `fa2ff5e2` Desktop `42679509572` 于 20:23:30 UTC 终态，5/6 作业通过，唯一失败是 macOS 主原生 4/6。Linux 主测 2156/2156，两个打包作业成功。macOS CPU 1537/1537、Metal 254/254，同 seek 保持可见对照随本批进入下一头。Windows CPU 1478/1478，Windows 原生 6/6 且每项 20 轮，零跳过。同头 Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42679509572/artifacts/13707666795) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

## 2026-11-09 20:18 UTC · X7 单机链路切断样例

D1 X7 已交付 `127b0316` 单机主动断链样例，源码和 wheel 各 15/15，联测 455/455。跨主机、静默丢包和原生桌面界面继续验收。 [D1 矩阵](planning/d1-compatibility-gates.md)

Claude65 已从 `ed08a0c9` 在独立 `claude/cli-log-resume-65` 修复另一处 CLI 中断续读问题。真实 Click 入口在读取 UTF-8 首字节后被中断，未输出字符却把游标从 7 报到 8。

远端 `fa2ff5e2` Desktop `42679509572` 的 Windows 原生 `129402349100` 仍在运行，本地提交等待整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572)

## 2026-11-09 20:04 UTC · Runtime 日志末段与 Cocoa 对照

D1 日志末段读取竞态已在 `0458516a` 修复，直连与 Hub 旧 Runtime 兼容纳入回归。P4 macOS 原生媒体保持 4/6，当前证据等待同 seek 保持可见对照。 [运行验收](runtime-validation.md)

同一 Desktop 轮次的 Windows CPU 1478/1478，零跳过，3 个 Linux 作业通过。独立 Windows 原生作业 `129402349100` 仍在运行，本地提交等待整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572)

Claude64 仍在独立 worktree 开发单机链路切断场景。root 已独立审阅本轮日志改动。

## 2026-11-09 19:54 UTC · Runtime 单实例与 X7 链路切断

D1 C-11 的 Runtime 单实例、目录别名和崩溃重启已有持久回归 `a5239e05`，部署联测 17/17。X7 已获得单机纯链路切断的严格 Bridge 证据。跨主机分区、产品观察界面与完整 D1 退出继续。 [D1 矩阵](planning/d1-compatibility-gates.md) [运行验收](runtime-validation.md)

`16dcd349` 同步 MuPRO HDF5 已发布流程与实际验收边界。Claude64 正在固化 X7 链路切断样例。 [试点设计](design/mupro-executor-pilot.md)

远端 `fa2ff5e2` Desktop `42679509572` 仍在运行。3 个 Linux 作业通过，macOS CPU 和 Metal 通过，主原生 WKWebView 步骤失败且诊断继续，Windows CPU 测试运行中。同头 Runtime `42679509438` 终态 13/13。本地提交等待 Desktop 整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

## 2026-11-09 19:42 UTC · 切换任务后的制品打开复核

`91b9d860` 保留派发时的制品条目。用户切换任务后，迟到回执仍可履行原来的显式打开，并在打开前使用原制品摘要复核本地文件。缺少原摘要时使用同一传输回执，两份摘要冲突时拒绝打开。复核沿用 256 MiB 本地检查上限，读取固定长度的普通文件。 [验收记录](runtime-validation.md)

Jobs 定向 50/50，零跳过。新增的回执倒序与打开复核用例各连续通过 5 轮。精确文件读取的两个核心测试通过，覆盖拥有字节、链接和 FIFO。

Claude62 已在独立 worktree 完成初始派发回执探针及审阅报告。Claude63 已启动，负责在独立 `claude/mupro-pilot-doc-63` 更新一份 MuPRO 试点说明，对齐已发布的 HDF5 原生流程和真实许可验收边界。

远端 `fa2ff5e2` Desktop `42679509572` 仍在运行，3 个 Linux 作业通过。macOS CPU 和 Metal 通过后继续原生阶段，Windows 在执行 CPU 测试。同头 Runtime `42679509438` 终态 13/13。Linux Python 3.11、3.12、3.14 分别通过 6493、6510、6493 项，两个 Windows 客户端各通过 5250 项。本地提交等待 Desktop 整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

## 2026-11-09 19:27 UTC · 初始传输回执与 Cocoa 可见对照

`74ba6ff5` 将同一传输的后续观测用于迟到的上传和下载开始回执。回执仍绑定原用户操作，完成状态保留。上传文件列表刷新按原尝试去重，下载保留一次已授权的打开或制品校验。制品行按详情代次和最新请求标识绑定。 [验收记录](runtime-validation.md)

Jobs 定向 48/48，零跳过。新增持久用例连续 10 轮通过，覆盖迟到回执下的上传、输入打开、制品校验与提交。

`ded55b8a` 为 MP4 和 HTML 视频增加同一 seek 历史的保持可见对照。可见组通过现有测试钩子调用同一原生暂停执行路径，隐藏组沿用实际切标签。两组先接收原生回复，首个 DOM 样本最早在原生派发 200 ms 后，第二个在首个回调 400 ms 后，回调均受原有一秒上限约束。记录两次采样分别相对暂停前和末次 seek 的差，以及样本之间的差。

Linux 构建及相邻 CTest 44/44，零跳过。独立核对两组的 C++ Apple 条件分支、四个用例的 CTest 注册和 macOS CI 证据归档。Apple SDK、Metal 和 WKWebView 实跑待目标 CI，诊断为非门禁。

远端 `fa2ff5e2` Desktop `42679509572` 正在运行，2 个作业已通过。Runtime `42679509438` 整轮 13/13 通过。本地提交等待当前 Desktop 的整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

## 2026-11-09 18:55 UTC · 传输完成状态与迟到回执

`d7fbc3f1` 按原传输 ID 记录桌面已采纳的观测。迟到的继续、取消回执或刷新快照保留请求后已采纳的变化。刷新列表若先观察到已知在途传输完成，复用已有完成处理，随后同一完成事件只更新显示。 [验收记录](runtime-validation.md)

Jobs 原生定向 47/47、零跳过。持久用例覆盖两份旧快照和先完成列表两种顺序，并核对已知上传完成后仅刷新一次工作区文件。隔离 Python 3.11 全量 `7cdaece6` 为 6477 通过、180 跳过、4 排除、零失败。随后加入的晚到 Hub 拒绝修复已由此前 141 项定向联测覆盖。`c5b87b91` 显式取消新增 HDF5 夹具子进程的模型变量，以空模型 API key 重跑仿真与 HDF5 原生定向 20/20、零跳过。

Claude60 的独立 Linux 全量项目测试 937/937 通过。root 集成 Claude61 的 `c0a4c75c` 为 `9ac67dde`。查找重试持久用例在缺少按钮的旧版复现失败，当前一次重试只重读同一行。合并后的仿真与 HDF5 原生定向 20/20、零跳过。Claude62 已从传输修复头在独立 worktree 开始核查初始派发回执乱序。

远端 `15dff6ac` Desktop `42669507898` 于 18:59:02 UTC 结束，5/6 个作业通过。Linux 主作业 2142/2142，Windows CPU 1466/1466，Linux 打包和冷环境通过。macOS CPU 和 Metal 步骤通过，主原生验收的 MP4 和 HTML 视频仍失败。新的 Cocoa 诊断 2/2，分别在约 183 和 182 ms 收到 WebKit Playing，各两次 DOM 采样均为暂停，位置分别停在先前 seek 的 0.234 和 0.102 秒。两组都在原一秒窗口内确认了位置回退。下一步用同一 seek 历史做保持可见的暂停对照。Windows 原生 6/6，零跳过，18:59:01 UTC 结束。 [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42669507898/artifacts/13701368078) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898) · [macOS 原生工件](https://github.com/sijintech/stk/actions/runs/42669507898/artifacts/13701990267)

## 2026-11-09 18:25 UTC · 原传输继续与 HDF5 回执回归

`7cdaece6` 将已取消的传输纳入桌面继续操作。直连下载使用原传输 ID。Hub 上传仅在核对原导入确已拒绝后推进审阅编号，并在派发前持久化下一次尝试。若批准先到，继续跟踪原动作。`abaf0a31` 覆盖原动作在查询与同 ID 重放之间才被拒绝的时序。 [验收记录](runtime-validation.md)

`a6681a6f` 将禁用 NumPy 和 h5py 时的图源注册测试改为核对七个必需的版本化 ID，相关三模块 48/48。隔离 Python 3.11 全量 `49140b04` 为 6473 通过、180 跳过、4 排除、1 失败，唯一失败为原六项断言。包含修复和首版传输变更的隔离 Python 3.11 全量 `7cdaece6` 已启动。

root 从 Claude60 的独立 worktree 选择集成 `f1fc18b6` 为 `fa2ef209`。其 12 项请求与回执测试已由 root 用实际 CMake 目标注册和复验。加上 Transfers、Hub 上传和 MuFerro 按钮共 24/24，零跳过。 Claude61 的任务卡和启动器已备好，等待 Claude60 的独立全量原生测试和进程收尾后启动。

远端 `15dff6ac` Runtime `42669507521` 已结束，8/13 个作业通过。Linux 三个矩阵和 Windows 两个矩阵的唯一失败均为六图源旧断言。两项 Windows 作业各 5249 通过、273 跳过、872 排除、1 失败，后续客户端检查未运行。Linux 3.11 和 3.14 各 6488 通过、165 跳过，3.12 为 6505 通过、148 跳过。三个 Linux 作业各 4 排除、1 失败。Desktop `42669507898` 仍在运行，本地交付等待整轮终态。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42669507521) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898)

## 2026-11-09 18:07 UTC · MuFerro HDF5 查找重试与旧项目复验

`0b9b1c90` 在已收集的 MuFerro 运行记录查找失败时提供显式重试。点击后重新读取该运行的结果行，列表与打开仍由用户分别触发。仿真指南同步补充操作入口。 [验收记录](runtime-validation.md)

原生构建及相邻 CTest 34/34 通过，零跳过。 `49140b04` 的隔离 Python 3.11 全量仍在运行。

Claude60 在独立 worktree 编写原生 HDF5 请求与回执回归。root 已验证本次用户流程并负责后续审阅与发布。

远端 `15dff6ac` Desktop `42669507898` 仍在运行，1 个作业已通过。Runtime `42669507521` 已通过 8/13 个作业。本地修复等待前一 Desktop 运行的完整终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42669507521)

复查 PR #53 和 #54。#53 旧实现与当前 worker 退场、重试归并机制冲突。独立回环发现已取消的 Runtime 下载可立即按原 ID 重试。审阅中取消的 Hub 上传第一次重试仍会复用已拒绝的导入动作，第二次才发起新审阅。桌面开放全部已取消传输的重试前，需先修复该动作轮换。#54 的归档标签和快速启动入口已核对，其新增文件与现有交接文件在大小写不敏感文件系统上冲突。 [PR #53](https://github.com/sijintech/stk/pull/53) · [PR #54](https://github.com/sijintech/stk/pull/54)

## 2026-11-09 17:56 UTC · MuFerro HDF5 原生选择与 Cocoa 隐藏观测

`c3061e78` 为现有严格图入口增加单容器元数据节点，缓存查找前及元数据解析前核对登记 SHA-256。项目根和固定相对路径限定访问范围，列表只返回明确的场和步号。扫描最多 4096 个链接，列表最多 256 项，超出时拒绝整份列表。`49140b04` 在仿真面板接入列表、明确选择和打开。校验并持有载荷后才接纳 Viewer。 [验收记录](runtime-validation.md)

本地 Python 联测 165 项通过，1 项性能基准跳过。原生相邻 34/34。离线构建 wheel，并从隔离安装位置确认节点注册和安装版节点参考。 Linux 项目 CPU 广跑 1034 过，12 项 Peer 因初始环境缺少依赖或安装版 helper 失败。补齐后同源码 Peer 20/20 通过。 新头 `49140b04` 的隔离 Python 3.11 全量仍在运行。

Claude59 在独立 worktree 交付 `239bcd8d` 的通用运行索引适配器作为对照。H1 采用只访问单个容器的专用路径。Claude60 已从 H1 产品头接手原生请求与回执的持久回归，root 负责审阅、集成与发布。

`e9d0da9b` 新增两个非门禁 macOS 诊断，复用常规播放、seek 与真实切标签，在原一秒窗口内先读原生回执再尝试两次 DOM 采样。Linux 相关 29/29，Apple 条件语法与目标测试注册通过，实际目标机时序待下一轮。旧 `fd611652` 的新增无重复暂停对照 2/2。两例 WebKit 被动回复 `Playing`，同一隐藏会话两次 DOM 均为暂停，时间增量为零。主验收 4/6，两例在首次原生查询前因隐藏保持时媒体位置回到前一次 seek 而失败。macOS CPU 1524/1524、Metal 254/254。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42658246869/artifacts/13696087547)

远端 `fd611652` Desktop `42658246869` 于 17:52:31 UTC 结束，5/6 个作业通过。Linux 主作业 2141/2141，Linux 打包及冷环境验证通过，Windows CPU 1465/1465。Windows 原生 6/6、零跳过，六项各 20 轮。PDF 160 张 OS 截图，20 次重准备，捕获启动最长 79 ms。PR #53 与 #54 的头未变化。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869) · [Windows 工件](https://github.com/sijintech/stk/actions/runs/42658246869/artifacts/13696884487)

## 2026-11-09 17:28 UTC · HDF5 载荷接纳与项目根绑定

`9e22e6ed` 提供明确授权的 Viewer 载荷替换。采用前核对项目、调用方、屏幕容量、文本编辑与 Viewer 版本。历史分析仍要求空 Viewer。内容寻址缓存共用有界解码，先检查每个唯一缓冲的长度和总预算，再读取并校验 Viewer 实际持有的独占字节。 [验收记录](runtime-validation.md)

用合成目录交换复现按算例子目录绑定的边界问题。调用端检查后，若算例目录被换成指向项目外的链接，工作进程会将链接目标当作根。候选改为使用规范化项目根与固定运行相对路径，拒绝这一交换反例。已用真实严格桥核对该打开候选的 C++ 图摘要、24 个体素及 14 项输入或回执拒绝。打开候选已备好供面板接线。Claude59 正在独立 worktree 测试字段与步号适配器。审阅发现通用运行索引会枚举整个绑定，另在隔离 worktree 验证只读取指定容器的元数据节点。原生面板与实际点击仍待验。

隔离 Python 3.11 全量 `2d488712` 已结束，6464 项通过、180 项跳过、4 项按测试标记排除，零失败。 该轮覆盖 HDF5 测试替身修正，采用 3.11 源码和独立依赖环境。

远端 `fd611652` 的 Desktop `42658246869` 三个 Linux 作业成功，主作业 2141/2141。Windows 和 macOS 仍在运行，本地提交等待整轮终态。PR #53 与 #54 的头和审查状态未变化。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869)

## 2026-11-09 17:12 UTC · 网页图谱接续、HDF5 选择核查与 Runtime 终态

`84ab61c6` 让网页图谱复用任务面板已接受的节点、工作区及任务观测。快照之外的已核验任务会进入图谱绑定，精确终态结束原任务进度轮询。独立选择其他图谱数据源或显式清空绑定时保留该选择。 [验收记录](runtime-validation.md)

`2d488712` 修正上一批遗漏的 HDF5 快照测试替身，使其模拟允许收集。真实取消门控及摘要拒绝断言照常验证。定向 1/1。HDF5 与工作流组 110 项通过，性能基准和真实 MuFerro 许可环境各跳过一项。隔离 Python 3.11 全量基于 `2d488712` 运行中，已核对依赖及 suan 源码导入位置。

root 以 `e70982f9` 选择集成 Claude58 `045fb476` 的设计和证据。实际收集的合成 HDF5 含两个场各两个步号。严格桥和 GraphWorker 按登记 SHA 读取指定非末帧，原地改写容器与错误选择器被拒绝。root 用作者探针独立复跑 1/1。复核确认原生 `open_path` 会在求值前清空 Viewer，设计改为先验证并解码载荷，再核对项目、选择和 Viewer 版本后接纳。原生界面与点击数仍待实现验证，真实许可与 HDF5-only 完成仍待证。 [设计核查](design/mupro-hdf5-result-selection.md)

Claude59 已在独立 `stk-claude` worktree 从本批设计头开始实现原生 HDF5 字段与步号的有界元数据适配器。root 负责面板、Viewer 接纳、审阅和集成。

远端 `fd611652` Runtime `42658246715` 于 17:07:17 UTC 终态，八个作业通过，三项 Linux Python 与两项 Windows 客户端作业均因同一条 HDF5 测试替身提前抛出 `_Cancelled` 失败，五项各只有这一条失败。Desktop `42658246869` 仍在运行，本批本地提交等待整轮 Desktop 终态后推送。PR #53 和 #54 的头未变化。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42658246715) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869)

## 2026-11-09 16:57 UTC · 网页完成产物刷新与 Hub 动作回执

`ef894f85` 在网页接受同一执行节点、项目和任务的 Runtime 精确终态后，自动只读刷新原任务产物。不同工作区的终态答复不会触发刷新。手动及自动读取共用答复顺序，已采用的新产物列表保留，迟到的旧空列表无法覆盖。 [验收记录](runtime-validation.md)

`1a6fb12c` 将已读到的 Hub 动作回执与后续 Runtime 任务读取分别保留。真实回环中取消动作先返回排队，Runtime 收到一次请求并在修改前拒绝，随后节点断开。刷新保留原可重试 `unavailable` 错误，冷重开能读到同一 Hub 动作 `failed`，并保留原 Runtime 任务最近的 `running`。旧代码定向复现 1 项失败，隔离相邻回归 68/68，root 主工作区联合回归 80/80，均零跳过。

Claude58 以 `fd611652` 在独立 `stk-claude` worktree 开始 HDF5 字段和精确步号选择设计。任务限一份设计说明及仓库外合成探针，核对已有发现和图入口能否复用收集摘要。真实许可与 HDF5-only 完成仍待验证。

远端 `fd611652` Desktop `42658246869` 仍在运行，新的本地提交等待该轮终态。Runtime `42658246715` 当前 8/13 个作业通过。开放 PR #53 和 #54 的头未变化，分别仍有冲突和检查问题。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42658246869) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42658246715)

## 2026-11-09 16:46 UTC · Runtime 取消确认、Cocoa 对照与桌面终态

`c3f869eb` 先向正在跟踪的各 Runtime 原任务分别发出一次取消，再用原连接只读核对待确认的任务。只有观察到 Runtime `cancelled` 才记录原任务已取消。已先结束的任务保留 Runtime 原终态，未确认的任务保留原 ID 并标为中断。五秒是发出请求后的观察窗口，单次网络读取仍受原连接超时约束。已经持久化的取消可阻止新收集开始。人工再次启动可接回原运行或原成功任务。 [验收记录](runtime-validation.md)

root 集成 Claude57 在独立 worktree 提交的 `d86b2324`。真实回环 Runtime 拒绝第一次取消时，第 2 次尝试停为中断。求解器 PID、创建时点与任务 ID 保持一致，无新增提交、取消重试、收集或分析。第 3 次经人工启动接回同一任务，原批准保留。Claude 基线组 114 过、1 项预期失败。root 在隔离 worktree 使用修复和作者的原始测试，拒绝取消与正常取消对照 2/2。使用门控合成求解器，商业许可宿主仍待验。

上一轮 macOS 的两个失败用例中，DOM 报告暂停但媒体时间倒退。原无 DOM 对照在两例都读到 WK `Playing`。`ad174492` 保留该对照，新增两例非门禁诊断，在同一隐藏视图先保留被动 WK 原生回执，再相隔 400 ms 观察两次 DOM 媒体时间。Linux 相关 CTest 29/29。Apple 条件 C++ 语法和工作流步骤检查通过，实际行为待 macOS CI。

远端 `b4110f8c` Desktop `42646061897` 于 16:41:18 UTC 终态，五项通过，仅 macOS 失败。Linux 主测试 2138/2138，Linux 打包与冷环境验证通过，Windows CPU 1463/1463。Windows 原生 6/6、零跳过，六项各 20 轮。PDF 160 张截图、20 次重准备，重准备启动最长 89 ms，PDF 全程单次捕获启动最长 114 ms。macOS CPU 1521/1521、Metal 254/254、原生 4/6。Runtime `42646061798` 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [Windows 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13692551836) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13690393949) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42646061798)

## 2026-11-09 16:25 UTC · 网页精确任务观察、Hub 撤权和人工取消

`683963e9` 为 STK 网页任务面板接入 Hub 精确只读观察。节点快照与 Runtime 最近状态分开，核对节点、工作区和任务 ID。通过任务 ID 也可查询快照外的任务。断线保留最后一次观察，重连继续读。图谱事件轮询使用现有只读入口，选择和自动观察不写 Hub 操作记录。 [验收记录](runtime-validation.md)

`75b7e87f` 在转发答复前复核客户端和节点，撤权的迟到回复分别返回 401 和 404。`1774642d` 在发送每条 SSE 后复核授权，同批后续事件被拦截，旧流正常结束。`c98145a3` 要求 MuFerro 完整结果包含能量、进度、完成文件和初始 Polar，已知计划时仍检查计划帧，旧记录的原终态和验证保留。两项首批合跑 172/172，SSE 与联邦等后续 46/46，均零跳过。隔离 MuFerro 联跑 212 过，3 项跳过（Windows junction、两项商业许可）。

root 以 `17cbfcc1` 集成 Claude56 `8962c956`。真实第三个 Bridge 在接管原运行后执行人工取消。求解器仍被夹具门控时，Runtime 对原任务 ID 收到一次取消，求解器停止，项目停止且没有新增提交、收集或分析。重复取消和冷观察保留原批准。作者和 root 分别 114/114 零跳过。该场景使用可达 Runtime 和受控求解器，取消请求未确认的失败分支仍需单独处理。证据 `root-delivery-20261109-98/claude56-root.xml`。

远端 `b4110f8c` Desktop `42646061897` 的三个 Linux 作业通过，Linux 主测试 2138/2138，Windows CPU 1463/1463。macOS 于 16:23:06Z 失败终态，CPU 1521/1521、Metal 254/254、原生 4/6。新增不重复暂停的对照 2/2，视频与 HTML 视频先在可见时读到 Paused，真实隐藏后保留同会话，独立查询均读到 Playing。对照没有隐藏期 DOM 采样，重复暂停组 0/2 且两例各 27 次 Playing 后 watchdog 关闭。Windows 原生仍在运行，本批等整轮 Desktop 终态。Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [macOS 工件](https://github.com/sijintech/stk/actions/runs/42646061897/artifacts/13690393949)

## 2026-11-09 15:56 UTC · 历史分析归档核验与 MuFerro 运行中接续

`36c5ab8d` 绑定选中历史运行的首次归档回执。相同运行的结果读取和状态读取若返回变化后的回执，保留已验证的结果和检查模型。`af8746ad` 按已验证的归档预算检查所选载荷，用同一普通文件句柄读取精确长度，再对 Viewer 实际持有的独占字节校验 SHA-256。旧代码的回归分别确认会接受替换回执、已解码映射会随源文件原位改写。新代码能拒绝改写和长度错配，已加载载荷仍保持原值。Windows/macOS 的新读取路径待目标 CI。 [验收记录](runtime-validation.md)

root 以 `6e638721` 集成 Claude55 `b61ecc9e`。旧 Bridge 强制退出时求解器仍被夹具门控。重新观察、非强制人工恢复及显式启动期间，原求解器 PID 与创建时点保持一致。第 2 次尝试在解除门控前记录接管原任务和运行状态，重复启动只读回当前执行。随后记录一次收集，绑定原产物、冻结快照和真实 GraphWorker 能量结果。总提交一次，取消零次，原审批保留。作者和 root 六个源码测试文件各 113/113，均零跳过。商业许可求解器仍待验。证据 `root-delivery-20261109-97/claude55-root.xml` 与 `claude55-root-scratch/`。

远端 `b4110f8c` Runtime `42646061798` 于 15:55:20Z 完成，13/13。Desktop `42646061897` 仍在运行，本批等待该轮终态后推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42646061897) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42646061798)

## 2026-11-09 15:30 UTC · Cocoa 隐藏采样、MuFerro 人工接续与桌面终态

macOS 在已有重复暂停对照之外，新增只改变二次派发的测试。目标系统回执用于区分隐藏后的播放状态和再次请求的影响。 [验收记录](runtime-validation.md)

root 以 `767903df` 集成 Claude54 `43e52c63`。真实第三个 Bridge 观察原任务时不收集。人工恢复将消失的旧执行尝试标为中断，明确启动后第 2 次尝试接管原成功 Runtime 任务，保留原批准并核对原始输出字节。真实 GraphWorker 生成 Total Energy `[-1.125, -2.25, -3.375]` 并在 Bridge 退出后回收。定向 1/1，六个验收和 Bridge 测试文件共 112/112，均零跳过。使用受控求解器夹具，商业许可宿主仍待验。证据 `root-delivery-20261109-96/claude54-root-final.xml`。

## 2026-11-09 15:10 UTC · 一次点击查看已验证的历史分析

MuFerro 合成试点的历史分析已有一次点击查看路径。只采用已核验的唯一三维输出，多个输出仍明确选择。真实许可主机、HDF5-only 完成、科学参数及 macOS/Windows 交付仍待验。 [验收记录](runtime-validation.md)

root 以 `a8ac9db2` 集成 Claude53 `5a3d8033`。SIGKILL 前核对原批准与已运行的求解器，桥离线时同一任务成功。重开读取历史启动和项目中持久的 running 状态，实际 Runtime 已成功，真实提交共一次。下载三份产物核对摘要，根源码 103/103。证据 `root-delivery-20261109-95/claude53-root-final.xml` 和 `claude53-root-focused/`。

## 2026-11-09 14:40 UTC · 冻结 HDF5 归档的原生首帧

合成 MuFerro 的收集记录、冻结分析和原生归档查看已连通。原始收集文件移开后，桌面仍显示经过验证的指定 HDF5 步骤和分量。其他目标平台、真实许可求解器、HDF5-only 完成和科学口径分别待验。 [验收记录](runtime-validation.md)

root 以 `641b2807` 集成 Claude52 的 `0cda6bcc` 与 `6464a3c0`，审批跨进程和相邻回归 102/102。

## 2026-11-09 14:12 UTC · 上一轮 Desktop 终态与冻结 HDF5 分析

MuFerro 收集记录已在合成 Runtime 实际生成后进入冻结分析。GraphWorker 从快照读取所选步骤和分量，错误容器摘要被拒绝。下一项是验证原生加载该分析载荷。真实许可主机、科学参数和 HDF5-only 完成仍待验证。

上一轮 Desktop 的 Windows 原生通过 20 轮 PDF 重准备，macOS 视频与 HTML 视频仍失败。新头继续在目标平台核对新增暂停顺序。 [验收记录](runtime-validation.md)

## 2026-11-09 14:06 UTC · 显式 HDF5 读取和 macOS 诊断

收集记录的 SHA-256 现在可绑定显式 HDF5 图源。冻结分析已有合成载荷证据，下一项是用实际收集记录验证图求值。HDF5 的图参数仍为显式选择器，Viewer 时间轴、真实许可和 HDF5-only 完成待分别验证。macOS 下一轮新增可见原生确认后走正常隐藏的对照，保留主验收和既有对照。 [验收记录](runtime-validation.md)

## 2026-11-09 13:49 UTC · 仿真面板末帧与失回执观察

MuFerro 原生仿真面板已在 Linux 软件 OpenGL 从固定选中运行状态一次点击显示收集的末帧。算例目录并存导出结果时，显式预设和默认打开各自得到对应数据。S2c 成功批准回复丢失后，新严格 Bridge 可以观察原回执，真实本机 Runtime 只收到一次提交。Claude50 核对已有 HDF5 读取器在收集后显式查看的可用路径。目标 macOS/Windows、许可求解器和 HDF5-only 完成仍待各自验证。 [验收记录](runtime-validation.md)

## 2026-11-09 13:36 UTC · 原审批卡重审与 MuFerro 结果查看

冷重开后的新严格 Bridge 保留原审批卡、计划和摘要，观察之后仍需重新读完整计划。批准只调用一次工作流启动。下一项是批准回复丢失后的同一回执恢复。MuFerro 准备只使用与冻结摘要相符的普通文件。已收集结果使用明确的末帧预设，旧图和旧节点沿用原有实时行为。Linux 原生脚本入口已显示第 2 步。真实许可、HDF5-only 完成、模拟面板 View 按钮和其他原生平台仍待各自验收。 [验收记录](runtime-validation.md)

## 2026-11-09 13:17 UTC · S2c 完整响应与收集文件核验

S2c 审阅前置条件现在绑定实际完整响应，超限回执不能开启审批。下一项验证是同一项目冷重开后，原审批项保留且须重新读取完整计划。MuFerro 收集从摘要对应的启动报告字节解析，查看拒绝非普通文件。继续沿用现有 DAT 完成验证，真实许可和 HDF5-only 完成仍待核对。D1 `graph.meta` 已厘清节点代理动作、权限与依赖诊断缺口，能力投影仍待选择。 [验收记录](runtime-validation.md)

## 2026-11-09 13:01 UTC · DAT 一致性、节点观察与原生验收

DAT 直接读取和统计共用校验后的实际内容摘要。监控通用 tail 保持标准库独立和非阻塞 FIFO 处理，MuFerro 读取拒绝最后一级链接及非普通产物。D1 P-1/F-5 已通过本机真实 Hub、Node、Runtime 回环验证心跳列表与活动连接的差异，能力投影仍处于比较阶段。Claude47 核查现有 `graph.meta` 观察可承载的内容。真实 MuPRO 许可、样例和跨主机仍待验证。

Windows 原生前一轮完成 20 轮 PDF 重准备，后续仍用启动计时排查间歇长停顿。macOS 可见暂停对照通过，隐藏对照仍失败。下一轮用 Cocoa 探针记录实际可见性、焦点交还和原生回复。 [验收记录](runtime-validation.md)

## 2026-11-09 12:31 UTC · S2c 联合验收与 MuFerro 文件边界

S2c 已补 Linux 原生批准卡片、严格桥和真实本机 Runtime 的联合证据。使用脚本规划器和合成求解器，真实许可、跨主机与目标平台仍待验证。MuFerro 核验及监控拒绝链接或非普通产物，最小安装缺 NumPy 时可列元数据，读取和图规划返回稳定错误。Claude45 比较现有契约下的节点能力声明，执行预检与授权状态分别记录。 [验收记录](runtime-validation.md)

## 2026-11-09 12:12 UTC · 通用文件、HDF5 预检和原生定位

通用图文件源已核对实际解析的内容。单文件 VTKHDF 保持内部链接，外部存储明确拒绝。MuPRO HDF5 缺依赖时在读取容器前报告，按执行节点声明能力和真实许可算例仍待验证。Claude44 在独立 worktree 核对 MuFerro DAT 与运行索引缺 NumPy 时的诊断。Windows PDF 的捕获启动已加入分步计时，下一轮要区分 WinRT/DWM、设备、会话、启动和 COM 释放。macOS 当前头第二次可见暂停仍待结果。 [验收记录](runtime-validation.md)

## 2026-11-09 11:45 UTC · 原生验收终态与 MuPRO 读取依赖

Windows 原生余下 PDF 重准备后的像素超时，macOS 下一轮验证第二次可见暂停对照。MuPRO HDF5 已区分可选依赖诊断与只装 `server` 时的 NumPy 缺失。按执行节点声明能力、提前报告缺失依赖和真实许可输出验证仍待处理。 [验收记录](runtime-validation.md) [D1 兼容门](planning/d1-compatibility-gates.md)

## 2026-11-09 UTC · D2 真实 Jobs 回环与 case 依赖

D2 已取得 Linux 本机原生点击加真实 Hub 的联合证据。固定作用域保留原任务，断线期间只更新观察，重连后由精确读取更新原任务终态。跨主机网络及其他目标系统仍待验证。MuFerro 图索引按实际 case 依赖的字节绑定布局和清单。Claude42 核验缺少 HDF5 依赖时各入口的实际行为。通用图文件源的内容绑定反例已在隔离数据上复现，留作下一批处理。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 断线观察及第二次可见暂停

Jobs 已保留同作用域的任务事实，分开显示实时观察。下一步在真实 Hub 故障下结合原生点击验收。节点撤权的旧快照读取已有真实回环回归。macOS 新对照沿用隐藏组的播放历史，在第二次暂停前分叉，目标 CI 待执行。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 图目录与场帧实际内容

生成区由目录脚本维护，MuFerro 行为说明已在节点语义区。DAT 场帧缓存命中使用核对过的内容身份，未命中从已核验临时副本解析。Jobs 继续验证断线观察和取消确认的作用域，C++ 的真实 Hub 场景由 Claude41 独立验收。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 实时帧完成状态

MuFerro 图索引已核对计划中的完成标记存在性。恢复原状态后重新求值。下一步验收 Jobs 精确读取和独立可见暂停基线。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · D2 C++ 读取及图表格身份

原生 C++ 桥已具备可选实时任务读取。真实 Hub 链路由 Claude41 在独立 worktree 验证。Jobs 下一步保持选中任务的最近一次事实，独立显示当前观察状态。MuFerro 图索引内置能量与进度已加入实际字节核验，随后核对完成标记与 live 结果的绑定。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 平台验收与可见暂停基线

Windows 原生 6/6 已取得远端终态。macOS 新增首轮播放后的可见暂停基线，用原截止区分可见请求的原生回执与后续 DOM 观测。首轮可见诊断和已有隐藏对照各自留证。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · Hub 停机完成和 C++ 实时读取

D1 X7 已补 Hub 进程停止期间原任务自然完成的单机证据。跨机网络分区及界面观察继续验收。Claude40 接手 D2 的 C++ 桥可选实时读取入口，使用已有桥协议及 Python 路径。 [验收记录](runtime-validation.md) [D1 矩阵](planning/d1-compatibility-gates.md)

## 2026-11-09 UTC · 启动报告身份和原生暂停

MuFerro 内置图索引已核对报告实际字节及 Runtime 发布摘要，避免把变化后的目录或状态写入原键。macOS 下一步保持同一播放视图可见直至暂停回执与原生状态核验，单独检验隐藏时点。Claude39 已补进入 Runtime 提交的次数与原动作请求绑定，待 root 集成验证。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 内容绑定及 D2 实时任务读取

图表格和 MuPRO HDF5 进一步按实际解析字节核对来源。D2 桌面桥加可选实时任务读取，在真实 Hub 上与 CLI 共用精确查询。Claude39 的 Hub 停机完成候选已获单机证据，待补入口次数及动作请求绑定。macOS CPU 和 Metal 已过，下一步核原生隔离暂停结果。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 节点离线完成和 HDF5 图索引

D1 X7 已补 NodeAgent 离线期间原任务自然完成的单机真实线路证据。Claude39 继续 Hub 停机的独立场景。MuPRO 图索引拒绝已计划摘要的容器执行时无法核对，恢复原内容后重新求值。macOS 隔离暂停对照已通过目标编译，运行证据待远端。 [验收记录](runtime-validation.md) [D1 矩阵](planning/d1-compatibility-gates.md)

## 2026-11-09 UTC · 冻结准备与 Windows 捕获

工作流首次及重试准备按实际项目修订复核冻结参数。Windows 原生 PDF 对已准备新会话但没有截图样本的阶段启用有界 WGC 会话替换，继续验证两张独立的 OS 像素。macOS 隔离暂停对照随远端 `3d2fcea7` 执行。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 目标平台接续

下一轮 macOS 对比固定隔离暂停动作与现有静默隐藏。Windows 保留 PDF 重准备的画面判据，`bc25f579` 本轮超时后核对会话与画面阶段。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 结果冻结和原生暂停对照

工作流结果快照绑定验证过的收集摘要，异常替换在对象入库前拒绝。macOS 下一轮用固定隔离暂停动作与既有静默隐藏路径比较，沿用相同的核验、截止、保留草稿及重显判据。D1 X7 已有作者单机证据，待 Claude38 收口首个实时答复和下载清单后由 root 验收。 [验收记录](runtime-validation.md) [D1 矩阵](planning/d1-compatibility-gates.md)

## 2026-11-09 UTC · 日志绑定、冷恢复和节点离线完成

MuFerro 桌面日志逐次检查冻结端点，已验两处切换和原连接双流。已补冷重启恢复原连接后按同一 ID 完成传输的验收。Claude38 接手 D1 X7 的节点离线期间任务自然完成，既有断连后显式取消作为回归。macOS 静默对照确认关闭发生在隐藏期 DOM 采样前，后续核对宿主暂停及原生关闭路径。 [验收记录](runtime-validation.md) [D1 故障矩阵](planning/d1-compatibility-gates.md)

## 2026-11-09 UTC · 冻结连接和传输恢复

MuFerro 已接入冻结端点检查，覆盖产物列表、下载启动及按日志恢复的后端。Claude37 补冷重启后恢复原连接的完整成功路径。Cocoa 静默对照仍在当前 Desktop 队列，Windows 联接点已通过独立客户端矩阵。 [执行器试点](design/mupro-executor-pilot.md) [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 已收集产物和冻结连接

MuFerro 项目收集及 Viewer 打开前校验已收集清单，保留普通备注。两处桌面连接切换已用内存后端复现，Claude36 设计按已冻结身份检查实际产物后端和传输重试。D1 F9 已补真实线路。两种 Windows Python 的真实目录联接点已通过，Cocoa 静默对照仍待 `bc25f579` Desktop。 [验收记录](runtime-validation.md) [CP-0 矩阵](design/cloud-project-service.md)

## 2026-11-09 UTC · CLI 终态与 F8b

本地 MuPRO CLI 校验报告后核对原 Runtime 任务状态。D1 F8b 已在真实 UDP 验证物理替换与重新绑定，Claude35 接手 F9 的同 inode 旧修订恢复。Cocoa 静默对照及 Windows 原生联接点等待远端 `bc25f579` 复验。 [CP-0 矩阵](design/cloud-project-service.md) [验收记录](runtime-validation.md)

## 2026-11-09 UTC · Desktop 新轮和结果登记

上一轮已完成 Windows 原生和全轮验收，进入含 Cocoa 静默对照的下一轮。传输取消保护已完成发布的日志，MuFerro 收集补启动器成功报告和程序摘要格式核对。真实许可、目标 Windows junction 和 Cocoa 隐藏行为分别验收。Claude34 继续真实线路数据库替换。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 项目目录边界和 F10

项目仿真共享目录已在 Linux 用合成 Windows 元数据和真实导入路径验证，真 junction 由 Windows 矩阵复验。D1 F10 已有 Linux 真实线路和安装态证据。Claude34 继续 F8b，核对同内容数据库被物理替换后的授权失效。Cocoa 静默对照仍随待推批次。 [CP-0 矩阵](design/cloud-project-service.md) [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO 核验资源与 D1 物理恢复

MuPRO 大步数案例可在缺产物时返回有限诊断，收集先用现有文件数量门槛。F5c 已记录 Linux 真实 peer 的当前物理恢复行为，Claude33 继续 F10 撤权并发。Cocoa 在上一轮已观察到显式暂停成功，隐藏期仍失败。下一轮用本地已提交的无 DOM 采样对照区分隐藏期状态和探针影响。 [CP-0 矩阵](design/cloud-project-service.md) [验收记录](runtime-validation.md)

## 2026-11-09 UTC · D1 scope 隔离和真实未知状态

D1 F11a/F11b 已有 Linux 真实线路和安装态回归。Claude32 接手 F5c，记录现行 peer 项目读取的物理恢复行为。Synthrix 只读观察对同一 Runtime 的真实 `unknown` 与取消终态已实测，前端和产品授权接线仍待实施。MuPRO 解码失败报告已本地通过，下一轮 Windows CI 增加真实 junction 拒绝证据。 [CP-0 矩阵](design/cloud-project-service.md) [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO 证据边界与 D1 F13

MuPRO 启动链已在 Linux 验证终态精确步数和连接前完整清单检查。Windows junction 和真实许可小算例仍待对应环境。D1 F13 的真实 8 MiB 预算已有单机 Linux 源码与安装态证据。Claude 接手 F11b，验收同一操作 UUID 在本机桥和已认证 peer 上各自持久和重放。 [验收记录](runtime-validation.md) [CP-0 矩阵](design/cloud-project-service.md)

## 2026-11-09 UTC · Cocoa 对照与 D1 F15

新增 Cocoa 静默隐藏对照。每种素材复用既有 Play 和隐藏，直到原生核验时限结束才读取 DOM。比较在首次 DOM 采样前的原生状态和现有采样组，继续保留原失败关闭。D1 F15 已通过同一 Linux 项目上的真实 WebRTC 和本机桥验收，其他目标平台另验。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 桌面交付与 Cocoa 对照

Windows 原生在 `a8872719` 完整通过。新头在 Cocoa 核对宿主去重后的显式暂停与隐藏期状态。若隐藏期仍报告 Playing，比较同一固定素材的独立会话，一组在隐藏后仅采原生回执，一组继续采样 DOM。上游公开探针入口带有用户手势标志，该对照用于验证探针是否影响结果。保留现有截止和关闭判据。 [上游入口](https://github.com/WebKit/WebKit/blob/main/Source/WebKit/UIProcess/API/Cocoa/WKWebView.mm#L1192-L1205)

Claude29 已在独立分支补 D1 F15 的真实线路回归。目标是格式 14 可读，回执操作明确拒绝，旧 schema 和项目状态完整保留。 [CP-0 矩阵](design/cloud-project-service.md)

## 2026-11-09 UTC · 原生报告暂停与回执复验

Claude28B 的重复暂停修复经 root 整合和 Linux 真窗口复验。新头在 macOS 分别核对首次显式暂停的代次、媒体时点和隐藏期的原生状态。上一轮隐藏对照已确认收到回复，持续返回 Playing。Windows 保持现有验收门。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO 布局核验与 D1 实线竞争

MuPRO 启动后的结果按预检布局验收，保留离线核验入口。D1 的 F3/F11d 已用本机桥和真实 WebRTC 验证单库同修订竞争，目标平台和跨部署另验。Windows Mesa 准备通过，原生报告运行中。Claude28B 已交候选，root 继续核对窗口提前关闭时的测试夹具及 Linux 必跑门。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · Windows 文献热日志复验

外部数据库热日志夹具已从 Python multiprocessing spawn 改为独立标准库子进程。Windows 先看 `a8872719` 同头重跑，再用新头验证阶段日志、实写热日志和原字节保护。Linux 三个 Python 版本的物理夹具通过。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · MuPRO 样例预检与报告窗口回归

MuPRO 计算端预检和启动已统一 SDK 样例的两份文件清单，缺件修复后可在原目录重试。真实许可、研究参数和 HDF5-only 完成仍按各自证据验收。Claude28 已定位两次暂停派发，下一候选使用 Linux Xvfb 真窗口和假原生视图验证宿主生命周期，之后由 root 核对 Cocoa 结果。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · 报告暂停候选与验收顺序

Claude28 在独立 worktree 核对同一报告视图的隐藏暂停和紧接的显式暂停，只在能用便携回归证明会话和失效边界时提交候选。root 对照新一轮 Cocoa 请求与回执，分别验收首次显式暂停和隐藏期间的关闭。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · macOS 关闭已归因与三平台回归门

Mac 原生报告 HTML 对照已确认由同会话暂停 watchdog 关闭。继续查已确认 ACK 后的实际查询及状态回调，并用暂停派发可见性核对单次按钮点击的两条路径。显式暂停时间回退与隐藏关闭分别验收。Windows 原生以固定 Mesa 资产的下载备用路径重新进入下一轮，同头 CPU 已通过。 [验收记录](runtime-validation.md)

文献两种布局的八项 CPU 交互进入三平台必跑校验。目标原生文献实窗仍需 Windows/macOS 的可信 PDFium 与 E5 运行时及资产。D1 F23 已补真实 WebRTC 路径与撤权用例，云端内容策略和跨部署仍各按原设计门。 [CP-0 矩阵](design/cloud-project-service.md)

## 2026-11-09 UTC · CP-0 实际配额和隔离反例

F14 本机桥与真实 WebRTC 的实际配额已验，后续按配额监控、目标 OS、跨部署和 R2/R3 分开推进。Claude26 补齐 F5b/F5c/F23 的隔离反例及 F5c 无热日志对照。Claude27 接续 F23 真实线路验收，覆盖授权内容与撤权。 [CP-0 矩阵](design/cloud-project-service.md)

`39780e6d` 的 macOS 已完成构建、CPU 和 Metal 测试，原生媒体组仍待结果。 [Desktop 42564398378](https://github.com/sijintech/stk/actions/runs/42564398378)

## 2026-11-09 UTC · F12 真实续页与 F14 本机实额

F12 结构页、记录页的陈旧续页在本机桥与真实 WebRTC 上均获 `conflict`。F14 的两个实际配额已用本机安装 store 填满，分别核对拒绝、回滚、原回执读取和重放。后续区分实际配额线路验证、目标平台和跨部署。 [CP-0 证据矩阵](design/cloud-project-service.md)

Mac 媒体的新探针已随 `39780e6d` 进入 Desktop CI，等待 macOS 运行结果。原生报告验收继续按原门。 [Desktop 42564398378](https://github.com/sijintech/stk/actions/runs/42564398378)

## 2026-11-09 UTC · CP-0 安装复验与下一轮原生证据

D1 的 CP-0 已补齐回执、读页、热日志、授权内容及预算的证据矩阵。隔离 Linux wheel 在三个 Python 版本各通过 116 项。其中 F14 写后字节溢出经真实 WebRTC 和本机桥对同一 SQLite 库验证，其余入口范围按矩阵逐行记录。下一步由 Claude 在独立 worktree 用现有 F5b/F5c/F23 测试做隔离反例。Windows/macOS 复验、其余真实通道、真实配额上限、跨部署及 R2/R3 继续按独立条件推进。 [CP-0 矩阵](design/cloud-project-service.md)

原生 Desktop 前序 `49837655` 已终态。Windows 原生六项通过，macOS 媒体仍待新头的暂停与关闭阶段证据。 [验收记录](runtime-validation.md)

## 2026-11-09 UTC · macOS 首次显式暂停与隐藏分开定位

同头 macOS 独立视频的两例在首次显式暂停即低于 0.05 s，HTML 对照仍在隐藏保持及一次截图匹配后失去会话。补采显式暂停的原生阶段、已有隐藏关闭来源和两者的代次，按同一会话读回。现有暂停、两次截图、重显和撤权验收条件继续执行。

## 2026-11-09 UTC · F14 真实 peer 协议验证

本地 `1e7bebf2` 补齐共享回执字节越限在原生 WebRTC 协议上的错误及历史回执观察。已安装 Linux helper 和同头 wheel 运行通过，F14 仍属单机同库的现有契约。跨部署归属与云端写入按原门推进。

Linux Desktop 和 Windows CPU 已通过，Mac 及 Windows 原生验收仍在运行。

## 2026-11-09 UTC · 可重定位包和 CP-0 共享配额

Ubuntu 24.04 CI 包在 26.04 上用独立目录实测中文文献引用页、撤权和 Viewer 保留。固定布局各段点击为 8 和 5，证据补齐发布包入口。Mac/Windows 文献实窗仍待验证。

CP-0 的 F14 项目级回执配额回归已进入本地 `5c4723f4`，涵盖写前拒绝、事务越限回滚及旧回执恢复。Claude25 复核 CP-0 矩阵与现有测试证据。后续云端项目归属、授权和跨部署写入仍按原设计门推进。

## 2026-11-09 UTC · CP-0 两入口回归

`b8e42c66` 已在本地覆盖 Bridge／peer 同修订竞争、陈旧写入、分页和响应预算、格式 14。五文件 246 项通过，配套安装 helper 用例均执行。Claude 下一任务验证 F14 项目级回执配额、满额后原回执读取与精确重放。跨部署写入、云端归属和授权仍按既定设计门推进。

## 2026-11-09 UTC · macOS 原生媒体关闭取证

本地 `133778cd` 给隐藏测试增加同会话关闭原因记录，区分暂停 watchdog 到期、暂停状态回调逾期和其他关闭。25 项 Linux CPU 回归通过。先在 macOS 核真实关闭路径，再按证据选择产品修复，继续执行原暂停门槛与双截图判据。

`49837655` 的 Ubuntu 24.04 包已通过，Ubuntu 26.04 任务已越过上次的镜像下载失败点。整轮 Desktop 终态后推送本地候选。

## 2026-11-09 UTC · 前一代码头的桌面平台结果

Windows CPU 和原生报告通过，macOS 暂停会话关闭来源仍需验证，Linux 两项受 Ubuntu 镜像超时阻断。前头整轮已终态，GUI 桥目录修复和双语 Linux 文献实窗记录可进入下一头。Windows 软件原生报告完成不代替目标平台文献实窗。

## 2026-11-09 UTC · 双语文献实窗与 macOS 媒体验收

Linux X11 软件 OpenGL 已完成英文和简体中文默认布局的合成文献检索、引用页和撤权实窗。各为 8 次点击显示页图、另 5 次撤权，零滚轮。中文布局可完整显示页图，两个独立库返回逐字节相同的 PDFium PNG，网格 Viewer 状态有像素证据。目标 Mac/Windows 文献实窗仍待验。

macOS 定位前两项对照通过首段暂停保持，在第二次隐藏画面核验前失去原生会话，原组和对照的完整循环仍缺。下一项验证应区分原生暂停核验截止撤销和其他关闭路径，并保留两次连续截图与原暂停门槛。Windows CPU 已成功，Windows 原生文档仍在跑，前整个 Desktop 终态后推送。

## 2026-11-09 UTC · 文献引用页 Linux 实窗验证

英文默认布局从已索引的合成文献库进入，8 次点击显示真实 PDFium 页图及逐字高亮，另 5 次点击撤销后确认页图消失。Linux X11 软件 OpenGL 的网格 Viewer 截图像素一致。中文实窗全链、Mac/Windows 及实测素材留待后续验收。

GUI 桥目录修复已本地提交。前头 Runtime 13 项通过，Desktop 整轮终态登记后推送。

## 2026-11-09 UTC · 文献原生窗口入口与桥目录隔离

`2bf4bd50` 让 GUI 使用显式的桥状态和缓存目录。Linux X11 的中英文默认布局均完成文献入口实窗验收，各 1 点击、0 滚轮。继续验证真实引用页 GPU 呈现及 Mac/Windows。Mac 媒体定位前对照仍由 `fbe4b0cc` 的 Desktop 执行。

Claude 在独立 worktree 补 D1 已发布入口的并发与兼容性回归。根本地修复等待前整轮 Desktop 终态及登记。

## 2026-11-09 UTC · 区分 Mac 隐藏暂停与定位历史

`0f341a07` 加入独立的 Mac 无定位隐藏对照，覆盖独立 MP4 和 HTML 媒体。每种用新会话执行实际播放、隐藏、保持、重显及撤销，与原先包含 AX 定位的 20 轮并列出证据。先核采样时间与暂停阶段，再决定生产层处理。Linux 构建和 42 项 CPU 验证通过，目标 Mac 待 CI。

## 2026-11-09 UTC · 扩充 CP-0 回归和双仓观察证据

D1 现有项目语义加入热日志双入口回归和授权文件索引回归。Synthrix 观察原型通过真实本机 Runtime 的精确读取、只读副作用对照与 `JobObservation` 类型检查。已知任务 ID 由夹具预先绑定，真实产品路由、跨站、R2/R3 和授权仍待设计。

Mac 新诊断在两个失败点都采到 ACK 已到、核验未完成。继续用首次 AX 定位之前的隐藏对照区分定位和暂停时间回退，保留原有期限、时间判据和 20 轮验收。

## 2026-11-09 UTC · 固化 D1 现有项目语义

CP-0 已有一项跨入口回归，覆盖同修订目录和记录分页、陈旧续页与各 scope 原回执。已集成[云项目承载比较稿](design/cloud-project-service.md)，R2/R3 待决定。Claude 独立补物理热日志的两条入口测试。

Synthrix 当前计算 API 读取本地 LAMMPS 任务，前端缺少 `unknown`。双仓下一步可先用已知合成 STK 任务验证只读观察映射，分别处理不可达、查无、未知和终态；真实产品路由和授权仍待设计。

## 2026-11-09 UTC：原生暂停诊断可进入目标平台验证

315 的整轮 Desktop 已终态。Windows 原生 20 轮通过，macOS 两项媒体隐藏保持失败。下一轮验证 `749076d9` 的暂停阶段诊断，以区分暂停请求、原生确认与后续时间读数。D1 项目服务候选 3 已冻结，R2/R3 待决定。

## 2026-11-09 UTC：先验证 D1 项目语义，再比较云端承载

1. Claude 在独立 worktree 修订云端项目服务比较稿，区分有界目录和记录、原回执及授权项目内容。CP-0 先比较已发布的本地桥和 peer 项目操作，并把存储专属、peer 专属和未来云端场景分开。root 已在源码和隔离安装中实测同修订页、同 ID 跨 scope、路径单元格及物理恢复差异。R2/R3 保持待决。
2. `315620f9` 的 Desktop 仍待 Windows 原生终态，Mac 两视频均在隐藏保持阶段回退。待本轮终态登记后，推送本地 `749076d9` 采集原生暂停阶段。继续 D1 云端项目与 Synthrix 接线、文献目标 OS 验收、MuPRO 试点及其余路线。

## 2026-11-09 UTC：定位隐藏暂停观察边界，继续 D1 项目服务设计

1. root 已本地提交 749076d9：只在测试探针记录 Cocoa 暂停原代次的 ACK/核验，绑定隐藏前、首个暂停及最新回执；现有暂停行为、阈值、期限、像素、20 轮不变。Linux 最终目标构建及 42 项 CPU 零 skip；目标 Cocoa 编译与原生观察尚待新头。
2. 4d 实际证据已确认 AX 前也有小幅时间回退，两个隐藏失败又精确落在各自最后一次 seek 的位置。保留定位、时间校正与隐藏因素的区分，不能从当前证据认定生产根因或放宽验收。
3. 315 的前整轮 Desktop 仍运行；Runtime 已核12成功、Windows3.11未终态，Docs/Secret成功。不能把315的结果当749的验收，完整Desktop终态登记后才推。
4. 实际Claude在独立19分支开展云端项目单文档设计，18六路径冻结提交5a256190保留。R2/R3仅比较；云端项目/Synthrix接线、原八项/D1–D5保持。MuPRO真实资产、扫描值与分析提案形式不代选，HDF5仍需DAT、PET后置。核本批closure和真实Git，保旧WIP。

## 2026-11-08 UTC：交付可恢复 Hub 上传 CLI，继续原路线

1. root已把实际Claude六路径第四版选择集成为397a464d：私有worker命名空间租约、完整内容侧记及原导入意图，Hub输入上传、只读查看与显式恢复/取消。人工导入和既有权限保持；不支持硬链接拒绝而不覆盖。原D1故障、云端项目、Synthrix共同后端接线与D2–D5仍继续，不能把CLI切片当整个D1完成。
2. 完整源码九模块234/234、最小安装232/232均零skip；安装明确排除两个科学依赖用例，完整源码已覆盖。发布12反例/控制和读取11组独立通过；作者225与root234的差九项为共同后端6c回归。目标OS worker、外部网络和科学有效性未验。
3. 前4d整个Desktop42531177137已23:27:29Z failure终态、六job全结束，push等待门满足。MacCPU1516和Metal254全过，原生4/6；两视频显式暂停过，隐藏后媒体时间回退检查失败，新快照已留证，根因未知。其他五job及Runtime13、Docs、Secret成功；不套用到新6c/397字节。
4. root继续main/共享构建/公共契约与最终验收，Claude独立worktree文档和指定模块；原MuPRO资产、明确扫描值及分析修改提案形式待决保留，HDF5仍需DAT，PET后置。最终交付状态见本批closure及真实远端，旧WIP保留，P1/P2未激活。

## 2026-11-08 UTC：新 Runtime 全绿与上传 CLI 最终发布门

1. 远端4d6426fb的Runtime42531177232已success，13job全部成功；Docs实际部署/Secret成功。整个Desktop42531177137仍运行，必须整轮终态后才push本地6c481e59及交付记录；不以CPU或包job替代原生验收。
2. candidate3作者219项、root独立源码副本228项零skip，76个worker反例及11组读取边界通过；其中root九例共同后端修复已单独提交、67项回归通过。最终无覆盖发布检查仍有硬链接失败后exists/replace覆盖窗口，实际Claude同六路径修第四版。旧候选不覆盖；candidate3未集成，wheel仅离线构建未安装，最终最小安装/真实上传证据未完成。
3. 继续Mac原生诊断、文献目标OS/GPU与D1剩余合同/故障、云端项目、Synthrix正常接线和原八项/D2–D5。MuPRO真实资产/扫描/提案形式不代选，HDF5需DAT、PET后置和P1/P2未激活保持；交付见37/closure.json，保旧WIP。


## 2026-11-08 UTC：修复上传 CLI 所依赖的共同传输启动路径

1. 远端4d6426fb已启动新Desktop42531177137和Runtime42531177232；两者仍运行，Docs部署/Secret成功。继续跟踪新头原生视频诊断及跨平台回归，不能提前宣称已绿。
2. root本地6c481e59修复坏journal state为数组/对象导致整个TransferManager构造失败；保留坏字节/锁、正常queued/running原身份转interrupted与既有显式恢复/GC。九例旧8红/1绿，修后五模块67零skip通过、独立终审0发现；本地待前整个Desktop终态后push。
3. 实际Claude独立六路径继续第三版，root将早期b3的W2中断前kill/W3指数溢出两项实质发现交回修订。最终冻结、独立复核、最小安装与真实上传证据未完成；不改桌面/模型/R2/R3权限。继续D1余项、云端项目、Synthrix接线及原八项/D2–D5；MuPRO未决、HDF5需DAT、PET后置保持。

本批证据 `transfer-startup-20261108-36/`，保留旧WIP；P1/P2未启用。


## 2026-11-08 UTC：推送真实文献 CPU 界面验收与桌面回归修复

1. 前ae6整个Desktop42523800365于22:21:50Z completed/failure，六job全终态、Windows原生成功；已满足下一批push等待门。将已本地验证的99a25c36/9779efea/fe2cdb4b/9b338172及交付记录送入新CI，不能将旧头结果作为新字节证明。
2. 真实PDFium/E5 CPU界面2/2、各37点击/零滚轮；默认文献33、材料22和金样8零skip通过，21源码及五XML摘要复核一致。继续目标OS/GPU与Mac两视频诊断、20轮真实验收，不降低既有门。
3. 实际Claude在独立worktree继续六路径上传CLI第三版，root对固定早期快照并行验证worker协议/回收和只读预算；作者最终冻结、独立终审、最小安装及真实执行证据仍未交付。D1剩余合同/故障与云端项目、Synthrix正常接线及原八项/D2–D5继续；MuPRO未决、HDF5仍需DAT、PET后置保持。

最终提交、push和新CI以 `root-delivery-20261108-35/closure.json` 为准；原WIP保留，P1/P2未启用。


## 2026-11-08 UTC：真实文献 UI 验收推进，修复当前桌面回归

1. 本地main `9b338172` 已含99a25c36、9779efea、fe2cdb4b及9b338172，远端仍ae6；前整个Desktop42523800365尚运行，终态前不push。Runtime13job/Docs/Secret成功不替代整轮Desktop或本批新字节。
2. 真实PDFium/E5 CPU UI两布局2/2零skip，从默认布局各37点击/0滚轮完成自有PDF导入、解析、模型选择、检索引用、渲染替换和撤权历史链；Viewer/隐藏稿保持、21源前后相等。默认33项、材料22项、金样8项通过。资产验收目标默认关闭、缺资产失败；目标OS/GPU呈现和科研质量仍待验，不能把文献方向全部标完成。
3. 材料测试在真实ACK采用后再读模型，准入后的busy只在原截止内重观测；两处持锁延迟均旧红新绿。媒体诊断只补实际观测，保持原门，下一头继续Mac显式/隐藏暂停与真实20轮验收；当前Mac原生4/6。
4. 实际Claude继续独立六路径Hub上传CLI第三版，root提前只读复核固定早期快照；作者最终冻结、独立终审、最小安装-I来源和真实执行证据仍须补齐，不扩R2/R3或自授权限。继续D1其余合同/故障、云端项目与Synthrix正常装配，再按依赖推进D2–D5及原八项。
5. MuPRO/MuFerro首期、插件自定原生格式/MuPRO HDF5及有限S2c方向保持；真实许可资产、扫描值、分析提案形式不代选，HDF5完成仍需DAT，PET新专项后置。PR53/54无新相关头，P1/P2未激活。交付证据 `root-delivery-20261108-34/`，旧WIP保留。


## 2026-11-08 UTC：文献原生页面接线与回归推进

1. root在main本地接上文献编辑器、顶栏/Workspace入口、双语表单与精确页图高亮；已本地提交5c0b85d3，未push。完整文献33项、UI核心131项、App/AppStore19项通过且零skip；默认中英文固定布局一次点击进入、零文献RPC并保持Viewer/隐藏稿，重复复核导入13点击。修复旧批准改投新review、无帧桥重启旧动作与失效丢输入，隐藏订阅和最终候选仍做收尾。
2. 文献真实E5检索/引用/页图全链UI和目标OS验收继续，CPU表单及几何不替代这些门。workspace只存已发布有限查询/范围稿，不扩授权/协议。
3. c281整个Runtime成功；Desktop42517256870已20:59:15Z整轮failure终态，六job均结束、Windows原生job成功，推送等待门满足。Mac CPU/Metal成功，原生两视频进入新的隐藏暂停失败，已取必要JSON但缺失败瞬间状态，不沿用旧AX/Tab根因或放宽门。
4. 实际Claude在独立worktree修18的六项缺陷，RED结束后须先恢复修订版；新候选/安装态均未审定。原八项、D1剩余及云端项目、Synthrix正常接线和D2-D5不缩减；MuPRO真实资产、扫描值和提案形式不代选，PET新专项后置。PR53/54无关旧头不合入。

本地源码HEAD为5c0b85d3，远端仍c281620d；交付证据root-delivery-20261108-31/，正式资产与原四文档WIP保留。

## 2026-11-08 UTC：推进Mac原生验收修正及上传CLI

1. root提交247cca3b和70a301f4：验收使用现有窄区域tab菜单，并在完整WebArea候选唯一后证明真实选中Slider属于WebArea与最内层Group。正常事件CPU菜单往返2点击/5按键/0滚轮，状态保留；目标构建和AX CPU回归通过，下一头仍须Apple编译及真实OS/20轮，未放宽预算或像素门。
2. 前612e整个Desktop已19:32:03Z failure终态：WindowsCPU1447/1447、原生6/6与三Linuxjob成功；MacCPU/Metal成功、原生两视频失败。Runtime3.14观察失败已有fdbefeac本地候选，连同299e756b/13035ccc待新头CI；Docs/Secret成功。运行验收已记整轮终态，满足push等待门。
3. 实际Claude18在独立stk-claude/claude/hub-upload-cli-18实施六路径Hub上传CLI，root继续审阅、公共后端/契约、原生和共享构建。实现仍未集成；准确选择测试、活worker租约及安装来源是交付门，不自授desktop、不扩R2/R3。
4. 原八项、D1其余合同/故障及云端项目、文献实际点击、Synthrix正常装配和D2-D5保持。MuPRO/MuFerro、插件原生格式/HDF5及有限S2c按已定方向；真实执行资产、扫描值和提案持久形式不代选，HDF5仍需DAT，PET新专项后置。PR53/54无新相关差异，提案P1/P2未激活。

本批最终Git/CI和必要恢复事实见root-delivery-20261108-28/closure.json；保留既有WIP。


## 2026-11-08 UTC：修复测试竞态，启动Hub上传CLI实施

1. root已提交299e756b、13035ccc、fdbefeac，分别处理模型失败详情、智能体夹具日志及分析完成状态的观察竞态；17/13/36项本机回归全过，生产逻辑及预算保持。新头平台验证尚待CI。
2. 实际Claude17设计经校正成为a0f77fa3实施方案。Claude18在独立stk-claude/claude/hub-upload-cli-18从a0实施Hub上传、只读传输查看与显式恢复/取消；仅六路径，先固定候选。root负责共同后端/契约、原生、集成和共享构建，不扩R2/R3。
3. 远端612e的Runtime整轮失败：3.14 payload测试旧running快照；Desktop42509570653整轮仍live，MacCPU/Metal成功、原生4/6，两视频仍失败。先取新AX诊断和Windows终态，记录前整个Desktop终态后才push；Docs/Secret成功。提案2aea已在远端，P1/P2仍未生效。
4. 原八项、D1剩余合同/故障与云端项目、原生文献实际点击、Synthrix正常接线及D2-D5继续。MuPRO/MuFerro、插件自主格式/HDF5和有限S2c按已定方向；真实资产、扫描数值和分析修改提案形式不代选，HDF5完成需DAT，PET新专项后置。PR53/54未变且无关，不自动合入。

本批证据与最终交付状态见root-delivery-20261108-25/closure.json；保留旧WIP。


## 2026-11-08 UTC：关闭传输竞态，继续CI修复和上传设计

1. main本地2aea4a95合入root修订后的AOCI评估提案；P1/P2未启用，现行规则保持。
2. 7bfae902将Bridge状态目录锁保留至传输写调用及worker退出；旧红8/1，新七模块137项零skip通过。0e0a1246补AX父链与独立进度诊断，关闭合法丢帧误拒P2；两目标构建和CPU通过，Apple/OS待验，不放宽期限、唯一slider、像素或20轮。
3. bcec的Runtime整轮failure（3.14一个local-model错误详情时序测试）；Desktop已18:16:12Z整轮failure，MacCPU/Metal成功而原生两视频失败；WindowsCPU一个NativeAgentRuns夹具解析失败，Windows原生6/6成功。root先定位这两项CI问题及视频证据，Desktop等待门已满足，记录终态后push；不继承旧头绿灯。
4. 实际Claude在独立worktree继续17设计候选2，root已指定私有worker生命周期、完整源内容身份、取消不依赖源存在及unknown/审阅观察边界。仍仅文档，不实施Hub上传。root继续D1合同/故障、云端项目和D2-D5、原八项；原生文献与Synthrix正常入口保持待交付。
5. MuPRO/MuFerro、插件自主格式/HDF5和有限S2c按已定方向；真实执行资产、扫描值、分析修改提案形式不代选。HDF5完成仍需DAT，PET新专项后置。

具体证据与认知收尾见外部root-delivery-20261108-24/closure.json；原四文档及索引WIP保留。

## 2026-11-08 UTC：交付工作区入口，继续可恢复上传设计

1. 已集成Claude16为main2fcc7251：Hub工作区create/list/files与仅创建action观察；旧节点读回退保持有界轮询，写操作只确认收下。作者100项、root集成42项及独立最小安装42项均零skip通过；未接Hub上传、未扩授权或R2/R3。
2. root测试修正f052f06b等待owner信息后再prepare；24项通过，受控延迟旧红新绿。前691 Desktop整轮已于16:29:30Z失败终态，WindowsCPU与原生6/6成功；Mac单个联邦测试失败、Metal跳过、原生4/6。c0ff和本批新字节仍待新头平台CI。
3. 实际Claude在独立stk-claude/claude/support接17，仅设计Hub输入CLI的持久journal、单实例生命周期、人工import与显式resume；root审核具体方案后再分配实现路径。AOCI使用提案为另一独立提交，未纳入本片或改变规则。
4. root继续公共后端、Mac AX位置/超时证据、原生文献实际点击、Synthrix正常装配及D1剩余退出门；随后按依赖推进D2-D5和原八项。当前AX诊断建议未实施，不放宽2s/8s、唯一slider、像素及20轮门。
5. 首期MuPRO/MuFerro、插件自主格式/MuPRO HDF5、有限S2c方向已确认。真实执行资产、扫描数值及分析修改提案形式不代选；HDF5仍需DAT完成验证，PET新专项后置。

本批证据d1-hub-workspaces-20261108-20/root/；最终推送和CI见closure及运行验收，旧WIP保留。

## 2026-11-08 UTC：完成上传恢复有限切片，推进工作区入口

Claude15 `4d02ea3a03b8583d13bd8ab1a0a4a7fb8f771a53` 已仅三路径选择集成为 main `2cc40a0ddbe789770a43cb06c1f0f758ae48e524`，尚未push；root原生等待候选c0ff亦未push。远端691整个Desktop42495020086在16:22Z附近仍运行，须整轮终态后推送。Runtime42495020053已13job全绿，Docs/Secret成功；WindowsCPU成功，Windows原生128786216358仍live。Mac CPU1502/1503通过、531.86s，唯一失败为联邦ChineseNarrow1x的federation_register未解锁；Metal跳过。原生4/6，两视频仍失败，不能沿用旧7ef CPU/Metal结果。

1. 已集成Claude15三路径为2cc40a0d；root新模块67项及最小安装态10断言通过，保原transfer/session/偏移和人工import，不等整个D1完成。
2. Claude16仅开发Hub工作区CLI薄适配与相关文档测试，root复核后集成；不新增授权/调度状态机，不涉及R2/R3选型。
3. root跟踪新Mac联邦控件解锁失败、AX中WebArea链位置拒绝及HTML视频2秒deadline；c0ff等待候选仍待目标OS。保持原像素、连续帧、20轮和Viewer/草稿门。

root继续负责main、公共后端/契约、桌面问题、共享构建、审查集成、四状态文档/AOCI和推送。实际Claude在独立stk-claude/claude/support接CL-D1-HUB-WORKSPACES-16，基线4d02，仅cli.py、test_runtime_hub_cli.py、docs/hub.md：为Hub补工作区create/list/files及原action观察，复用既有后端，先交固定候选供审阅；本片不接Hub上传、不自授desktop、不改协议或R2/R3。当前尚未交付。任务卡 `d1-hub-workspaces-20261108-20/root/claude-task16.txt`。

继续D1剩余合同/故障和云端项目、原生文献实际点击、Synthrix正常装配及D2-D5与原八项；MuPRO/MuFerro、插件自定格式/MuPRO HDF5、有限S2c方向已确认。真实执行主机/SDK/许可/小算例、扫描数值及分析修改提案持久形式仍待输入，HDF5仍需DAT完成验证；PET新专项后置。PR53/54实际头仍c9f13994/2dd3e4ee，不合无关旧差异。原四文档和AOCI WIP保留，正式新交付/CI/治理见本批closure。


## 2026-11-08 UTC：691新头Runtime整轮已通过

691f3f12的Runtime42495020053于15:45:20Z completed/success，13个job全过；Windows3.11/3.12各5098通过、254skip、580未选，分别701.01/900.42s，旧SIGKILL收集错误已获得新头Windows验证。Linux完整矩阵和文献/peer-macos/独立联邦等亦成功；不把Windows排除server组当该组验收。Docs/Secret已成功；整个Desktop42495020086仍live，Mac已目标编译完成并进入CPU测试，WindowsCPU仍构建，原生待出。root c0ff1ac7/7f7a40d3本地未push，仍须等前整个Desktop终态；最新交付见windows-pdf-ci-42487388780/review/closure.json。下方较早“Runtime仍live”为当时快照，保原WIP。


## 2026-11-08 UTC：修正原生异步等待，继续上传恢复交付

1. root源码c0ff1ac76617769c9d266304f59d856a7485ca56已本地提交：报告验收按原截止非阻塞泵UI，拒绝晚到成功；55项与独立六探针通过，仍须Windows/Mac原生验证，未认定PDF根因已复现或修好。
2. 远端691的Desktop42495020086仍live，终态前不push；Docs/Secret成功，Runtime矩阵部分通过。跟同头整轮CI，不用局部绿代整体结果。
3. 实际Claude独立tree完成15的源码试跑10断言及提前退出红例，继续最小安装态、反例和三路径固定交付；root负责验收集成、全局状态和认知。
4. 原八项、D1剩余合同/故障/云端项目、原生文献实际点击、Synthrix正常装配与D2-D5继续。MuPRO/MuFerro首期、插件格式自主/MuPRO HDF5、有限S2c已定；真实许可资产、科学扫描值与提案持久形式不代选，HDF5仍需DAT，PET新专项后置。


## 2026-11-08 UTC：集成peer夹具，严格AX候选与上传恢复并行

1. 已选择集成实际Claude14为a1904447，root真实18项通过；Windows旧7ef本轮也全过，具体空JSON根因仍未知。
2. root AX源码79ae0adf7bfe7734a49f33fd571ecdd4e7b650bd以单祖先链和唯一WebArea消歧，保raw数/同窗/真实WK与会话绑定和原输入、DOM、像素、20轮门；Apple待新CI，HTML-video两秒deadline仍未定位。
3. 前整个Desktop42487388780于15:04:55Z failure终态，推送等待门满足；Mac原生4/6、Windows原生5/6，Windows PDF第13轮重准备像素超时另追，不当作已修复。Runtime旧Windows收集补修4399待新CI。
4. 实际Claude独立worktree执行CL-D1-UPLOAD-RESTART-15，root做公共后端、契约、审阅集成与发布；首个真实Bridge上传中断/原日志恢复候选尚未交付。
5. 继续其余D1合同/故障、云端项目语义、原生文献实际点击、Synthrix正常装配、D2-D5及原八项。MuPRO/MuFerro、插件原生格式/MuPRO HDF5、有限S2c已确认；真实许可资产、科学扫描值与提案持久形式未定，HDF5仍需DAT完成验证；PET新专项后置。


## 2026-11-08 UTC：输入传输、现有设备撤权与Windows收集补修

源码 main `4399f2fa6dfaba941922d2808ca023eba3766105` 已本地提交，尚未push；远端仍 `7ef5d21e`。前整个Desktop42487388780仍运行，终态前不推送。原四文档WIP和AOCI预存改动保留，最终交付状态见 `d1-input-transfer-20261108-18/root/closure.json` 与实际Git。

新增真实两部署输入/撤权样例：同一1048599字节公开输入，部分会话1MiB后重开同ID/offset，完成SHA校验；B blob必须经原workspace.import人工批准才导入，完整TaskSpec另经批准。两边固定程序读取冻结输入并输出相同SHA，原Runtime清单、各一task/run/marker、program和worker清扫前退出。B仅撤本次desktop设备，热/冷客户端后续11类请求均401，节点仍在线、无新增action，原Runtime任务保持。不是断网、桥日志恢复、项目/用户授权、在途请求中断、已交付字节召回或pending上传字节不变证明。

最终新模块及singleton联合28通过、零skip、14.81s；最小非system-site-packages包以-I installed复验11断言通过，场景6.045540141s、含清理8.1s，实际site-packages来源/模块SHA一致、清理干净。产品Python到7ef无差异，沿用已重建包，不把旧harness试跑当新字节；当前script46f83b43…/helpercf2b13c9…。独立终审关闭A额外queued任务假绿和迟到terminal延长局部截止，反例已入测试。暂存25040字节gitleaks零发现。

7ef的Runtime42487388719于14:14:50Z整轮failure：11job成功、两Windows矩阵因新增Linux专用singleton测试在收集阶段引用不存在的SIGKILL而报错，未执行该矩阵测试。本提交改为函数体解析信号名称，缺SIGKILL的模块红绿反例及Linux原11项通过/5.73s；仍待新Windows CI。Docs42487388755完整部署成功，Secret42487388666成功。Desktop当前Linux三job成功，Mac已越过编译/CPU阶段、WindowsCPU运行，原生最终结果待出；不能继承旧头平台验收。

root继续独占main、公共后端/契约、共享构建、审阅集成、四状态文档、认知与推送。实际Claude仍在独立stk-claude/claude/support做CL-NATIVE-PEER-14，只改peer_test.cc，候选尚未集成或目标OS验收；具体Windows空JSON根因仍未知。后续D1其余合同/故障与云端项目、文献实际点击、Synthrix正常装配、D2-D5和原八项保持；PET新专项后置。MuPRO/MuFerro、插件原生格式/MuPRO HDF5及有限S2c按已确认方向推进，真实许可/主机/小算例、扫描数值与提案持久形式仍待输入；HDF5仍需DAT完成验证。

## 2026-11-08 UTC：交付 D1 元数据与 Hub 可靠性有限切片

本地源码b517554a补任务时间/MIME验收，c5d8e503补正式Hub serve单实例，Claude13原755212b2选择集成ddd7d7c2；2c9729b8补Mac AX测试helper枚举编译错误。当前未push，远端fd；最终交付和新CI见本批closure及运行验收。

1. 主线联合271项零skip通过/74.57s；重建最小安装包后正常12、断连10、Hub丢结果重启11断言全过，原任务只启动一次且显式取消后清扫前退出。独立审阅关闭驱动摘要假绿与MIME错误原文导出；正式serve锁相关49项及14纯mock通过。收尾四状态/认知/扫描，前整个Desktop已于13:51:08Z失败终态，等待门满足后推送。
2. fd整轮Desktop已失败终态：Linux三job成功，Mac因AXValue类型错误Build失败，WindowsCPU1445/1446通过、1个PeerMouse空JSON失败，Windows原生文档6/6通过/1304.12s。两行类型化枚举补修尚待新Mac编译及原生20轮；Runtime13job/文档实际部署/Secret均成功不替新头验收。
3. 下一片输入传输与现有设备撤权，再补其他D1合同/故障和云端项目语义；不擅自引入R3项目/用户授权。原生文献实际点击、Synthrix正常装配、D2-D5及原八项继续，单机故障样例不替跨机/目标OS或真实MuPRO。
4. root负责main/公共后端/验收与发布，实际Claude独立树已交13并接CL-NATIVE-PEER-14，只改peer_test.cc；先证实空JSON路径，保点击/Viewer/隐藏稿门，待root审阅。MuPRO/MuFerro首期、插件格式自主与MuPRO HDF5、有限S2c已按所有者决定推进；真实执行资产、扫描数值和提案持久形式仍缺，不代选。PET新专项后置，旧WIP保留。

## 2026-11-08 UTC：交付断连切片，启动 Hub 丢结果恢复验证

本地源码688db5a0集成Claude12最终三路径，root联合90项零skip通过/43.90s，最小安装-I真实10断言通过；原进程取消后、清扫前退出，一任务/run/marker。原生源码d2f62622补公共AX进程测试链，主线两目标构建及43项CPU通过/2.85s，仍待目标Mac CI。本节成文时未push，新CI见本批closure。

1. 交付上述固定字节、更新状态和认知并扫描推送；前适用整个Desktop304已失败终态，b3的Runtime13job/Docs实际部署/Secret均成功。新原生候选必须看新Mac编译与20轮，不能借Linux或旧OS结果。
2. 实际Claude独立树已接CL-D1-HUB-RESTART-13，仅三条新测试样例路径：原Runtime已接受、Hub尚queued时丢首次结果，保Node/Runtime并同库重启Hub，核原action重派和一次启动。保现有节点缓存，缓存恢复不称再次Runtime.submit；root继续审阅和D1合同字段缺口核定。
3. D1尚缺全部合同/传输撤权/其余故障、Hub单实例及云端项目语义；D2-D5、原生文献实际点击、Synthrix正常装配和原八项继续按依赖推进。真实MuPRO/HDF5-only完成需资产，当前仍DAT完成验证；有限S2c不是自动开始。
4. 研究扫描数值与分析修改提案形式不代选，PET新专项继续后置。root独占main、共享构建、状态/认知/推送，Claude只改分配路径；原WIP保留。

证据 `native-ax-client-20261108-09/root-integration/`、`d1-node-disconnect-20261108-10/root-integration/`；旧候选两假绿已有独立红绿证据，初稿绿灯不代最终字节。

## 2026-11-08 UTC：收口文档 CI，继续 D1 故障和原生候选

root 本地 `9053ea5c` 修正文档依赖下载：同源固定libvips8.14.5、有界curl重试和上游摘要校验后交sharp本地入口。精确Node22.23.3/pnpm8.15.9的站点38页、搜索37页/两语言通过，锁未变；未push/部署，最终见本批closure。

1. CL-D1-DISCONNECT-12由实际Claude独立树继续修复：主动杀停前原NodeAgent必须存活且最终为SIGKILL；固定原worker身份，不能由新worker或最终清扫冒充取消成功。两P2均有独立纯桩反例，候选暂不集成；修后重新绑定source/installed证据。D1其余合同、传输撤权、Hub重启和云端项目语义仍在队列。
2. 原生辅助独立树候选补公共AX进程、真实WKWebView/session/导航及布局代次绑定、原绝对seek/子进程时限与清理。root审最终固定头，仍须实际Mac编译和原生20轮；不降低唯一slider/DOM/OS像素门。
3. 已推599整个Runtime13job成功、Secret通过；Docs两attempt仍下载超时。599不触发Desktop，最后适用整轮Desktop304已终态失败；无新的Mac/Windows原生验收。文档CI修正推送后核真实新工作流，不以本地构建当部署成功。
4. MuPRO真实执行与HDF5-only完成仍需资产；S2c仅本地准备、直连/SSH目标与人工首次批准。保原八项、原生文献点击、Synthrix正常装配和D2-D5；PET新专项后置，不代选研究扫描数值或提案形式。

root/main负责集成/共享构建/状态/认知及发布；Claude只改三分配路径，原生辅助不是Claude。旧WIP保留，最终提交/推送/CI见 `docs-libvips-20261108-11/root/closure.json`。

## 2026-11-08 UTC：D1 正常任务切片通过，继续故障与原生候选

本地源码 `6ae96999`（本节成文时未push）已集成Claude双部署样例并修最终两边界；61项联合零skip通过，root最小安装-I真实双部署9断言通过、12.1s。原MuPRO与后端产品目录到58无差异，验收以实际安装/脚本SHA绑定，不借旧源码头。

1. Claude已转CL-D1-DISCONNECT-12：在独立树仅开发节点离线/同profile重连的真实任务观察与无重复启动三新路径；原helper只读，root复核集成。当前D1尚缺更多时间字段/media_type、传输/撤权及其余故障门、云端项目语义；不能把9断言当全D1完成。
2. root原生辅助在第四worktree开发公共AX client测试候选，补后台owned child、2s kill/reap、UI持续泵及窗口/视图/session/导航/布局代次再核；唯一slider/DOM/OS像素/20轮不降。当前仅候选，未目标Mac编译/运行；root统一共享构建和最终发布。
3. 远端304的整个Runtime已success、旧24失败消失；整个Desktop于11:15:29Z失败终态，Linux GPU成功，三平台其余失败为依赖下载、两下游skip。当前推送门满足，Docs/Secret各一次重试仍失败。继续核实际新CI，不改网络策略或绕校验。
4. 真实MuPRO资产就绪后验执行/HDF5-only完成；共同后端后续项目服务、原生文献点击、Synthrix正常装配和原八项仍在范围，PET新专项后置。研究扫描数值及分析提案形式不代选。

root负责main、共同后端边界、集成/验证、状态/认知和推送；Claude与原生辅助各在独立树，仅改明确分配路径。证据及最终推送/CI见本批closure。

## 2026-11-08 UTC：回归修正已过，继续 D1 双部署与 MuPRO 试点

本地源码 `58fbd03e` 修正MuPRO遗留run.h5预检和S2c扩展后的测试前提。完整Python5698通过/151跳过/4未选、850输入SHA稳定；MuPRO联合90通过/2真实资产跳过，权限/传输联合91通过。最小extras安装态58的Hub CLI20通过。未供资产/目标OS及15个既有离屏SIG11不算通过。

1. 验收Claude独立树CL-D1-PARITY-11的真实双Runtime/Hub/节点harness；初稿两个模式均已试跑，须补明确产物内容、程序启动计数、预算与清理失败反例，再冻结提交、独立审阅和最小安装验收。当前未集成，不称D1两部署最终通过。
2. ec32整个Desktop42468258292已于10:22:29Z失败终态，推送等待门满足。Mac CPU1501/Metal254全过，但原生两个视频仍AX入口失败；另三job及Docs/Secret为下载504。本批修正的Runtime24项前提仍待新头CI。公共AX原型先补目标Mac编译、父端watchdog和身份再核，不削弱原验收。
3. 真实MuPRO主机/SDK/许可/小算例就绪后验执行及HDF5-only完成；继续共同后端项目服务、原生文献实际点击、Synthrix正常装配及原八项。PET新专项后置；扫描数值和分析提案形式不代选。

root负责main/共同后端、集成验证、共享构建和治理；Claude独占分配的三条新路径，不共写root状态文档。当前D1切片只验任务链，不含云端项目语义或新统一产品CLI。最终提交、推送及CI身份见本批closure。

## 2026-11-08 UTC：MuPRO 准备、人工首次批准与原目标执行接线

本地 main `b6b92d91` 已接通 S2c 有限切片：既有案例行、明确桌面目标/资源、prepare_muferro_run、完整计划卡片、单次批准/拒绝及原回执观察。旧冻结会话不加权限，人工既有工作流入口保持独立；没有无限自动执行或科学参数默认方案。
最终联合154项、Runtime/Hub22项、原生卡片13项通过；完整项目回归919/919通过、零跳过、722.343s；推送/同头CI以本批closure为准。固定CPU控件起点两次指针点击读计划并批准，Viewer和布局保持；不代替目标OS新UI验收。

1. 收口交接/AOCI、暂存扫描与推送（额外原生919项已通过），记录新CI；前a506整轮Desktop已失败终态，Windows原生全过，Mac视频AX两例仍待修。
2. 真实MuPRO主机/SDK/许可/小算例到位后验证真实执行及HDF5完成协议；当前仍需DAT完成验证，不将合成测试当许可或科学验收。
3. 继续D1同后端双部署、原生文献实际点击、Synthrix正常装配/桌面入口及原八项；PET新专项后置。研究扫描数值、分析修改提案持久形式保持待决。

root负责main集成、共同后端/契约和最终验证；Claude独立stk-claude/claude/support负责已分配模块及文档审阅，09模块已交，10只读复核已交无阻断报告。第三棵独立树的Codex辅助原生卡片已交root，不替代Claude。

## 2026-11-08 UTC：先收口批准组件，再接 MuPRO 工具与桌面

main本地 `afef46c5`（Claude首次启动门）和 `67670ae3`（root单次批准记录/观察）已提交，未push。冻结计划/请求/修订与首次started同事务；会话决定先落盘且只消费一次，丢回执只查询原证据。
最终联合99通过，旧MuPRO/agent合成Runtime链8通过；仍未注册新工具、派发、桥start/decline或原生UI，也未做真实许可运行。S2c方向已批准，当前发布权限尚未扩展。

1. 等a506cc69整个Desktop42459561098终态并记录目标OS结果后push；同头Runtime/Docs/Secret已成功。Linux三项、Mac CPU/Metal成功不代原生媒体或整轮完成。
2. root审查Claude新卡CL-S2C-EXECUTOR-08，将approval转交后台执行器；root继续准备工具、会话busy门、桌面明确资源/完整计划复核、桥及原生卡片和契约。入口支持既有MuPRO案例/工作流行，不仅AI新增行；未知不得重派。
3. 真实MuPRO资产到位后验证许可执行与HDF5-only完成协议；现有HDF5附加收集仍要求DAT完成验证。
4. D1同后端双部署、原生文献实际点击、Synthrix正常装配/桌面入口及原八项继续；PET新专项后置。扫描数值与分析修改提案持久形式仍不代选。

## 2026-11-08 UTC：转入 S2c 首次启动的原子边界

root本地新增 `598a069b`，为Mac AX完整空查询保留真实250ms调度间隔；Linux目标仅构建，不覆盖新增APPLE分支。它与dc5890b1的文献锁/Windows夹具/插件测试修正待新目标OS CI。
前整轮Desktop42455805095（761a9e37）07:27:11Z已失败终态，等待门满足；四job成功，Mac文献/视频及Windows原生问题仍须新头验证。
Claude只读S2c方案已审阅，CL-S2C-FIRST-CLAIM-06进入独立树实施：批准条件与首次started写入必须在同一工作流事务中，防止和编辑器并发或停止后重复启动。
root随后接工具、会话单次批准与恢复、桥和桌面；省略approval的原人工重启行为保留。本模块不是完整S2c或真实MuPRO验收，不扩自动取消/重启或模型权限。
实施选择为会话payload绑定可重算run身份、不升项目格式、桌面明确连接/资源和现有批次上限；扫描数值与分析提案持久形式不代选。D1-D5、原生文献/Synthrix入口、原八项和PET后置保持。

## 2026-11-08 UTC：试点后的 CI 修正与后续优先级

HDF5发现/收集源码89e40c89已随记录761a9e37推送，旧“未推送”段落保留为历史。
本批源码 main `dc5890b17eeb4c1b7a76aa42e0e8770abeccc924` 已本地提交，等待前整个Desktop终态后才能push。
已修Darwin文献租约目标、Windows报告测试拖动顺序及HDF5测试的模块重载污染；189通过/5跳过、文献必跑92唯一零skip、原生CPU24/24不替目标OS原生证明。

1. 跟进761a9e37的Desktop整轮与本批目标OS验证；其Runtime已失败，保留失败证据和本机红绿回归。
2. root审查Claude的CL-S2C-PLAN-05，再按路径拆出冻结计划、可信桌面人工单次批准、prepare/submit与原身份恢复实现。当前未扩发布权限。
3. 实际MuPRO/MuFerro主机、SDK/许可/算例就绪后验证真实执行及HDF5-only完成协议；不把合成容器或DAT附加收集当完成。
4. D1同后端双部署和兼容门、原生文献UI/实际点击、Synthrix正常装配及桌面入口继续按依赖推进；D2-D5与原八项不撤销，PET新专项后置。

root/main负责集成、共享构建、全局四文档、认知与push/CI；Claude在独立worktree仅做任务卡指定的文档/模块。目前S2c只读方案正在进行。
科学扫描数值与分析修改提案持久形式仍待决定；插件定义原生格式、MuPRO用HDF5、S2c扩展方向均已确认，不再当方向待决。

## 2026-11-08 UTC：MuPRO HDF5 发现与附加产物收集已提交

main本地源码 `89e40c89f946556e35ee954eb9a3fbf9c1a0dbfe`，未推送。连接器0.2.0和图索引实现2已接有界元数据发现、`hdf5:<field>` 内容绑定句柄及原任务HDF5附加文件收集。
DAT/能量入口保留；坏HDF5有独立诊断。收集仍须既有DAT完成验证；真实HDF5-only执行器与S2c并未随此完成。
最终回归419通过/5跳过、34记录输入稳定；CLI180个float32原值一致，目标OS/真实MuPRO/科学验收仍缺。
Claude模块 `c975f58d` 已由root选择集成；具体分工见[协作约定](planning/agent-collaboration.md)。
接下来：S2c冻结计划与人工单次授权、实际MuPRO资产/完成协议、D1同源双部署和跨端验证；原生文献UI及旧CI问题继续。
远端f152的Runtime失败已定位并修正其清单/测试前提；Desktop已于06:17:18Z失败终态，4个job成功、macOS及Windows原生文档失败。等待门已满足，本节记录时新源码CI未触发。
不缩减原八项，不代选科学扫描数值或分析提案持久形式，PET新专项继续后置；证据与限制见运行验收。
Claude已完成89e40c89只读复核，DAT兼容问题关闭；下一任务CL-S2C-PLAN-05已派发，仅外部实施/反例清单，不改产品树。

## 2026-11-08 UTC：HDF5 软件切片已实现，执行器链继续

读取器由 Claude 独立树 `73abd757` 交付，root 审查并接入 FileSource 和 `stk.source.mupro_hdf5@1`；源码已提交 main `56f51af70d576837426f63c12694941b0ea7cfcd`。
当前交付为版本化显式HDF5数据源：字段/步号、裁剪/采样、原值/dtype、来源SHA、规划键与读取绑定；既有DAT路径继续兼容。
305通过/3跳过（匿名文件修正后联合04）；CLI合成180值及float32一致。Windows HANDLE、性能与离屏渲染未验证，真实MuPRO未运行。
后续依次推进自动结果发现/原任务收集、受信任S2c prepare/run、D1双部署与跨端验收；本增量不等于这些能力已完成。
Claude 转只读交叉审查 CL-H5-REVIEW-02，root统一集成/状态/推送/CI；软件资产目录待所有者提供。旧八项、PET后置及其余待决不变。
本轮新代码尚无CI；前整个Desktop失败终态已核实，旧Mac文献/视频与Windows拖动失败继续保留。

补充修正 main `3579aea16ff9249fdb688012575576f1aeea8fb4`：交叉审查确认强杀worker遗留命名副本，已改匿名/关闭即删除的临时文件，共享同一读取核心；真实子进程强杀清理测试通过，CLI无缓存复验180值一致。

## 2026-11-08 UTC：试点实施队列与当前退出条件

计划和审阅后的D1门已提交 `f6a75f84`，D1两部署尚未验收。Claude的独立HDF5初稿 `760b7ae1` 正按root复现的两项读取边界修正，尚未集成。
接下来为读取模块审查通过 → 既有插件/数据引用接入 → 原任务执行与收集 → S2c冻结计划及人工单次批准 → 跨端验收。
当前旧链74通过/1真实软件skip，MuPRO配置预检退出1；真实许可链保留未验证。前整轮Desktop已失败终态，Mac文献/媒体和Windows HTML视频布局失败继续修复。
该顺序不减少旧八项或将分析提案持久形式、科学扫描参数默认为已决定；分工和写入范围见协作约定。

## 2026-11-07：首期选择 MuPRO/MuFerro 执行器（当前）

所有者选择执行器/专业软件优先，首项 MuPRO/MuFerro；原生数据格式由插件定义，MuPRO 使用 HDF5；
S2c prepare/run 权限扩展已获准开发。详见 [试点切片](design/mupro-executor-pilot.md)，不等于当前实现/发布。
下一步：真实软件/样例就绪核查 → 独立 HDF5 适配 → 既有插件/任务链 → 受信任授权下的智能体准备与执行 → 跨端验收。
保留 DAT 与旧接口兼容，电场扫描具体参数不猜测；分析修改提案持久形式仍待决。

root/main 与 Claude 独立 worktree 已从 `37d26464` 建立；D1 文档头 `9590d21b` 已经 root 审阅修正后纳入本批，D1 两部署尚未验收。
CL-MUPRO-H5-01 已派发并开始开发，限定独立读取模块/测试两文件；root 后续负责插件接入及 S2c 授权链。
现有执行链回归74通过、真实软件例1跳过；当前 MuPRO 配置预检退出1，真实许可/程序运行仍待具备资产。
当前 CI/记录与 AOCI 收口继续进行，八项既有范围与 PET 后置不变；下方旧三待决和优先顺序以本节更新为准。

## 2026-11-07：独立 worktree 与任务归属（当前）

按所有者最新决定，Codex 为 root 总负责；Claude 从共用树设计协作改为独立 worktree 的文档与指定模块开发。
root 保留 main，Claude 使用 `stk-claude` / `claude/support`；写入路径、基线、依赖与验收由任务卡划定，
最终集成、四状态文档、AOCI、推送及 CI 归 root，详见 [协作约定](planning/agent-collaboration.md)。

CL-D1-01 已定义为 ready：仅新增 D1 兼容门清单，不等于已接单、发布新协议或完成 D1。
root 继续按当前 Desktop CI、既有记录/AOCI、原生文献 UI、当前 Synthrix 装配/桌面入口、D1 的依赖顺序推进。
起始本地 5670f565 / 远端 6f4de650；该远端 Runtime/Docs/Secret 成功、Desktop 仍运行，具体见运行验收。
本轮只调整协作设置，旧八项范围、三待决和 PET 后置不变；下方分工及 Git/CI 旧快照为历史。

所有者另已设持续开发目标为 active：root 合理分配 Claude 工作，并审查、验证及合并当前计划相关 PR；
所有者数日后回复问题，期间继续不依赖待决的工作，不把未回复视为授权选择。

## 2026-11-06 UTC：总体框架、启动会与滚动试点计划（当前）

整体目标见[平台框架](design/platform-framework.md)，具体相对周数/依赖/角色/退出证据见
[平台开发与每周协作计划](planning/platform-roadmap.md)，跨仓职责和精确版本交付见
[仓库策略](planning/repository-strategy.md)。对外汇报可直接使用[讲稿](planning/research-kickoff.md)与
[投屏版](planning/research-kickoff.html)。材料提交：`325fe57dc955b4e9a69370e60d03f39ad0a6bb7b`。

W0 核定一个研究问题、投入、许可/GPU/机器和验收人；候选 W1–W12 依次为定义预检、共同后端、跨端链、单领域迁移、
真实能力、有限试点收口，W2 根据实际产能和依赖重排。人数、开始日期和演示期限尚未确认，不将周数写成交付承诺。
D3 只选一项业务切片，D4 真实资产独立留证，D5 仅做必要准备；旧八项范围和三待决不减项。

仓库候选为现有 stk + synthrix，按门槛新增或复用 stk-platform 集成发布仓；共同后端实现和协议仍由 stk 维护。
本轮未分仓、迁移代码、改 workflow 或继续功能实施。固定周会建议 60 分钟，具体星期/时间待双方确认，
会前证据、演示类型、决定与行动模板已写入路线文档。

检查为文档交叉审查、60 个相对链接/5 锚点、暂存空白/密钥扫描以及 10 页 PDF 排版核验，不是新产品功能验收。
本轮沿用已批准的设计直接证据例外，AOCI 暂缓；仅本地提交，Git/CI 与保留改动见[运行验收](runtime-validation.md)。
以下为此前设计及历史计划，不用旧“当前”标记覆盖本节。

## 2026-11-06 UTC：先完成统一后端设计（当前）

所有者确定 Core 与云端必须复用同一后端实现，前端分别为 C++ / Python 原生 Desktop 和 React Web。
设计交付 main 提交：`f541393b31b9f32b1f73bc738998075bc93e6dbd`；详细入口为
[架构与迁移](design/shared-backend-architecture.md)、[任务与数据协议](design/distributed-task-data-protocol.md)、
[跨端验收](design/distributed-workbench-acceptance.md)。本轮只完成 D0，不推进业务代码。

后续顺序：D1 同后端本地/云端装配 → D2 一条实际跨端任务链 → D3 Synthrix 对话/科研领域迁移 →
D4 原生 PDF/三维及真实许可/GPU/会话 → D5 多平台发行与分发。当前 API/项目格式仍以发布契约为准；
Python 共同服务与 Node/Fastify 现有业务之间须显式迁移，不能只换前端调用地址就宣告合并。
D1–D5 均待实现及验收；旧八项范围、三待决和 PET 后置不变。

本轮检查为文档交叉审阅、87 个相对链接目标、围栏、暂存空白和 gitleaks（零发现），无新产品运行/点击证据。
本地前源码 535b0d63 未推送且无该头 CI；远端 350534d 的 Desktop/Runtime 均失败终态，Docs/Secret 成功。
本轮文档仅本地提交。所有者已批准本轮 AOCI 直接证据例外，完整加载与维护暂缓；原既有 WIP 保留，索引对齐未声明。
详细事实及证据见[运行验收](runtime-validation.md)和[当前交接](../handoff.md)。以下旧“当前”章节为历史快照。

更新：2026-11-03 UTC。本文是后续开发的主计划；产品约定见[项目工作台设计](design/project-workbench.md)，
存储与求值方案见[项目数据模型](design/project-model.md)。设计目标不代表当前版本已经实现。
当前模块职责、归档清单与新增代码放置原则见[仓库结构说明](repository-structure.md)。

## 2026-11-03：恢复持续开发，STK 主体的分布式科研工作台（当前）

所有者恢复持续目标“继续工作完成我们所有的开发计划”，11-02 冻结转交点转为历史。
最新产品方向以 STK 为主体，融合 Synthrix AI 对话/科研管理；本地完整、Web 托管资源受成本限制，
通过授权节点共用电脑/自有云能力。轻量 CLI 可跨位置提交并持续追踪任务；对话、文件、任务与能力目录形成稳定壳，
领域功能通过可锁版本的插件深度定制。共同对象、事实归属与全部增量验收见
[分布式科研工作台](design/distributed-research-workbench.md)。

先保护并稳定现有 91 份 WIP，验证 encoder profiles、LiteratureService 最终适配与 S6 I/O；
同时沿现有 Hub/Runtime 完成 CLI 节点任务纵切面，补旧任务超出心跳列表后仍可按 ID 追踪的缺口。
之后按共同契约/节点能力 → Synthrix 本地科研闭环 → 文献/数据/Computer Use → 多节点/云配额/插件分发与发行推进。
旧八项范围、P4/S4 目标平台与真实 S6、toolkits/ABACUS 依赖、三待决和 PET 新专项后置保持。
这不是以设计文档代替功能交付；实际测试、提交和 CI 持续记入运行验收与交接。

本批进度：Qwen融合检索标识及历史encoder review恢复两个反例已修。真实E5/Qwen/PDFium联合69/69、零skip、14输入稳定；
服务三父Python各26/26、20输入稳定；公开文献Bridge最终54/54、27输入稳定，原fresh链Schema失败及实际缓存续接的范围见运行验收。
Hub CLI新增精确 `task.get` 与提交/观察/日志/产物/取消入口，9文件187项通过（控制台证据）；S6三Python各430/430、334输入稳定。
独立冻结heldout一次评价Qwen同语120/120、跨语119/120通过原门，E5 reference跨语24/120；一般段落诊断不替代原科学PDF失败。
S4撤权后旧Accept复活的最小CAS补修2红→绿；联合460pass/2个Windows-only skip，独立三Python各10/10、220输入稳定。
Linux原生整合2075/2075、零skip，1291输入稳定；Python整合02为5489pass/74skip/4deselected/1warning，5563案例、973输入稳定，pytest1207.90s。74skip包含encoder资产、Flower、离屏SIG11、Windows、MuPRO及可选依赖；真实推理69项独立证明不计入全量通过数。首轮旧editor计数/Python两失败及两文件漂移保留，修正与本轮证据见运行验收。
当前wheel新Linux隔离安装299/299、零skip，四个真实模型/PDF案例明确deselected，715输入稳定、704产品成员逐字节匹配；最终sdist未完成。
AOCI最新Root24/24交付confirmed、Challenge9/10 pass（1144条、estimated165707 tokens），29条Observed已按当前SHA确认；Entry语义维护/Dirty-Stale治理仍待最终收口。
本地HEAD仍3ef，本批无新commit/push/新头CI。原生文献UI、原科学PDF12/18/cross0/6质量失败、真实MuPRO、跨平台/网络与完整发行仍是待办。

## 2026-11-02 21:38 UTC：冻结并转交当前待办（历史）

所有者要求把待办交给另一 Agent，已冻结开发；[handoff.md](../handoff.md#当前接手顺序) 是当前接手入口，覆盖旧恢复指令。main/HEAD/local origin/main/实际远端均 `3ef4b2716d42304d708062f9715edae0afb5874f`；91份逐文件WIP（33 tracked/58 untracked）、暂存空，无新提交/push/包/新头CI。交接保留87份非状态文档WIP原字节；证据 `OWNER_NEW/handoff-20261102T2138Z/`，根见handoff。

新增E5/Qwen精确profile目录、双维Dense/Collection和worker bundle身份及专用测试已保存但未运行；LiteratureService最终双profile/显式timeout适配预计25项也未测，未接Bridge/Schema/native。旧服务三Python各21项/19输入稳定、后22项单版本、worker38项只保当时来源。S6四工作流文件已入仓；415项稳定矩阵早于FIFO修复，最新三Python各41项通过但252输入稳定性因literature.py并行变化失败，需冻结后补验。

原40QA主质量失败保留。独立公开tune：E5同语119/120、跨语12/120，Qwen FP32为119/120、115/120；INT8为115/120、101/120，质量/半耗时/RSS门失败，不采用。独立heldout未推理/评分，先冻结最终profile与严格release；旧selection/driver不可覆盖。完整八项路线、三待决、PET后置仍保持；平台/真实MuPRO/发行/AOCI/main交付未完成。官方同3ef/attempt1 Desktop失败、Runtime成功均终态，不覆盖WIP。

## 2026-11-02：恢复持续目标，推进服务和复现闭环（历史，本次转交前）

所有者已恢复按当前计划完成所有开发，上一轮handoff停止点为历史。main/HEAD/远端仍3ef、暂存空。S6新增四文件，三Python各415/415零skip、252输入稳定（`OWNER_NEW/reproduction-workflow-02/matrix-02/closure.json`）；Root随后复现FIFO读取阻塞并要求增量修复，后改代码不能借旧415结论。LiteratureService真实21项与worker38项已跑，正修独立审查的历史配置/引用rank和身份/数值类型/manifest预算问题并准备三父Python验证，尚未接Bridge/native。

原40QA全局12/18、cross0/6的质量失败保留；独立混合240段实验已冻结文章级tune/heldout，E5开发同语言119/120、cross12/120，候选本地模型正在运行，heldout尚未编码或评分。完整实验和限定在 `OWNER_NEW/retrieval-quality-independent-01/`；无产品模型/endpoint/网络设置或旧QA/语料改动。当前无新commit/push/包/新头CI，AOCI仍Dirty/Stale；稳定交付再维护。完整八项路线、三待决及PET后置保持，接手入口见[handoff](../handoff.md)。

## 2026-11-02：保存当前待办并转交（历史，本轮恢复前）

所有者最新要求将工作交另一 Agent，开发已停止；[handoff.md](../handoff.md#当前接手顺序) 是唯一当前接手快照，覆盖下方历史“继续开发/41项运行中/尚无排名”。main/HEAD/实际远端仍 `3ef4b2716d42304d708062f9715edae0afb5874f`；83 个 WIP 文件（33 tracked/50 untracked），暂存空，无新提交/push/包/新头 CI。

PDF/Store 三 Python 各92/92零skip，Runtime gate已改92唯一/68必跑/76负例；Dense/Collection最新真实E5 43/43零skip、14输入稳定。1051引用批次核验保完整结果/顺序/几何，解析循环31.489→3.248秒，不是端到端加速。首次冻结40QA/80查询已实际完成，但全局heldout hit@5 **12/18<0.85，cross 0/6<0.75**，S5不达标；保留失败，不按旧heldout调参。S6核心+图节点三版本新增97项全过，相关组各195pass/1旧可选离屏skip；制造的API→Report闭环草稿仅外部3.12初验15项，尚未入仓，不能称真实论文复现。

首要接续：修正未测试LiteratureService的可信encoder解释器、原DB UUID/授权发布和DTO守卫，再写spec/tests并接Bridge/原生引用；独立调查检索质量、接S6外部草稿并修renderer-import/prepare丢回复恢复，再继续平台、包和AOCI/main收尾。三待决与完整八项路线、通用优先/PET后置保持。官方同3ef/attempt1 Desktop失败、Runtime成功，均终态，WIP未获得新CI。当前AOCI仍Dirty/Stale；机器收尾和本机草稿/证据入口见handoff。

## 2026-11-02：持续目标恢复，按当前计划继续（历史，本次转交前）

所有者更新目标为按现在计划完成所有开发；10-31转交是历史。通用优先、PET专项后置与三待决不变。已修Runtime文献gate为72项唯一案例/48必跑，三真实XML及56负例、三Python门禁通过。Dense/Collection37项真实回归稳定通过，独立审查追加模型选择漂移/深层引用输入四反例并修复，当前41项正在验；两新格式语料库23页1051段及91冻结引用已核验，尚无embedding/排名。正在准备冻结全局两库主评估及S6独立通用比较核心，后续仍须原生引用/隐私RAG/共享、真实复现、平台、包安装及AOCI/main交付。当前头仍3ef，无新提交/push；详细证据与边界见[handoff](../handoff.md)。

## 2026-10-31 18:30 UTC：保存待办并转交（历史）

所有者要求交给另一 Agent，开发已冻结；以 [handoff.md](../handoff.md#当前接手顺序) 为接手入口，覆盖下方历史“继续开发”指令。main/HEAD/实际远端均为 `3ef4b2716d42304d708062f9715edae0afb5874f`，69 个逐文件 WIP（27 tracked/42 untracked），暂存为空；无新提交/push/包/新头 CI。

Store 最新三 Python 各72/72、零 skip，10 输入稳定；Runtime CI 仍写38，须先同步 gate。Dense28/28绑定旧Store；Collection9/9有Store漂移，后加引用分支清单未测试，当前37项闭合、两库语料build/排名均待办。Peer最新Bridge123/122/122pass、原生真实helper19/19及13/7点击证据保留其平台和起点限制。下一步依次为当前源码审查/回归、冻结QA-v2两库全局评估、性能与原生集成、包安装/治理/暂存扫描/main交付及新平台CI。八项通用路线、PET新专项后置、三待决均不变；本次只交接，不宣布完成。

## 2026-10-31 18:10 UTC：继续通用开发（历史）

持续目标已明确恢复，10:30转交是历史。Root文献Store首轮修复8红→绿，基础三Python各38/38；独立审查发现hot-journal未知库物理写入、fd关闭丢SQLite锁，P4正完善进程/跨进程门与真实反例，尚无最终Store闭合。S5 dense纯校验16/16、28项真实完整回归待Store冻结；40QA初版泄漏/不完整证据已保留，v2全篇文档隔离、Root抽查6例后冻结，真实全局两库检索正在实现，尚无语料检索指标。

Peer Bridge用最新loader三Python再验123/122/122pass、129输入稳定，19专用及两真实helper场景通过。原生实际安装helper新增发送13点击/接收7点击（各0滚轮），与原17项共19/19、971输入稳定、六组守卫通过；LinuxCPU、已认证/已有Offer起点、对端显式夹具，不代连接UI/OS/GPU/跨站。证据 `peer-bridge-loader-rebind-01/`、`peer-native-ui-02/`，根见[handoff当前节](../handoff.md)。

HEAD仍3ef、67路径WIP、无新提交/push；原Desktop失败/Runtime成功不覆盖当前改动。继续稳定Store/dense/collection、实际两语料全局评估、包安装/整合/AOCI/暂存扫描/main交付，再新头平台CI；P4/S4/S5/S6/P5-S7与八项范围不缩减，PET新专项后置、三待决不擅选。

## 2026-10-31 10:30 UTC：按所有者要求转交（历史）

已停止继续开发；完整接手顺序、代码入口、证据和限制见 [handoff.md](../handoff.md#当前接手顺序)，覆盖下方历史恢复指令。main/HEAD/远端仍 `3ef4b2716d42304d708062f9715edae0afb5874f`；67 个 WIP 路径（27 tracked/40 untracked，含四状态文档），暂存为零。本轮无新产品测试、构建、包、commit/push 或 CI 触发，参与 Agent 作业均终态。

Peer 原生页面/控制器现已接通，build08 和 17/17 CPU/鼠标测试、四组守卫通过，971 输入稳定；固定起点点击 11/20/1，Host/query 为合成 DTO，保护 Viewer 和隐藏稿。Bridge 最后 3.12 为123pass/1skip、3.11/3.14各122pass/2skip，129输入稳定；早于最新 helper loader ctime 补修。loader 三版本各38/38。PDF/FTS 基础三 Python 各30/30，但随后真实复现**未知 SQLite 被修改、跨实例恢复改写 completed receipt**两个 Store 缺陷，尚未修复，列首要待办。真实固定 E5 3.12为8/8；hybrid_search后加未测，40QA已冻结但独立审查及检索指标未做。

先修 Store、完成 dense/fusion/两语料评估，再补当前 Bridge/真实 helper UI/包/目标平台及 AOCI 整合收尾。P4/S4/S5/S6/P5-S7、八项通用路线和三待决保持；PET新专项后置。官方同3ef/attempt1 Desktop41178119889 completed/failure、Runtime41178119790 success；当前WIP没有新头CI，旧全量和旧包不能覆盖。交接核验入口 `OWNER_EVIDENCE/handoff-20261031T1030Z/`。

## 2026-10-31：继续通用开发，Bridge启动与桌面Peer接线（历史）

持续目标已明确恢复，09:00转交点为历史，PET新专项继续后置。Bridge已修复MaterialsService急切导入NumPy导致基础/子进程启动失败：无NumPy真实构造/stdio各2/2，材料接口35/35；最终Bridge三版本源绑定3.12为119pass/1Win skip，3.11/3.14各118pass/2skip（缺可选VTK的旧图测试另skip），129输入稳定、所有15专用Bridge及实际两安装helper场景均执行。`peer-bridge-02/closure.json`保留完整边界与旧失败根因。

helper六文件独立审查未增可确认缺陷；新桌面PeersEditor/稳定注册/i18n/Files导航已写入但尚待编译/交互验证。正在补准备来源/桥代次绑定、分页和必跑CI依赖，不把源码写入称平台验收。HEAD仍3ef、WIP未提交；新源稳定后再AOCI/包/全链检查。P4、S4、S5/S6/P5-S7与八项主路线、三待决保持完整范围，详见[handoff当前节](../handoff.md)。

## 2026-10-31：最新转交点（历史，09:00 UTC）

所有者要求把待办保存后交给另一 Agent；已冻结功能开发，仅收集先前已启动的验证终态。当前入口是 [handoff.md](../handoff.md#当前接手顺序)，覆盖下方历史“继续开发中”指令。main/HEAD/官方远端仍 `3ef4b2716d42304d708062f9715edae0afb5874f`；48 个未提交路径（19 tracked、29 untracked，含四状态文档），暂存为空，没有本次 commit/push/新 CI。

生产 sender/receiver 已接通、两项接收端缺陷已修；Linux helper 可重定位候选及三 Python loader 各35/35 已验证。真实安装前缀 Bridge 最终3.12为117pass/1Win skip，116输入稳定；3.11/3.14各101pass/2skip/**15fail**（13缺numpy，2旧子Bridge超时，待诊断），不称三版本通过。新 C++ PeerState 和测试目标已构建 exit0，但三项测试未执行；真正 PeersEditor、配对/分享UI、i18n、导航和点击验收尚未实现，identity.recover 也尚未接 C++ whitelist。

下一 Agent 先解决 Bridge 环境/超时、审查并完善控制器和 UI、独立审查 helper 六文件及整合包，再做新头Mac/Windows P4验证。官方同3ef/attempt1 Desktop41178119889已终态failure、Runtime41178119790成功10/10；push等待前提满足但平台未验收。后续S4信令/站点网络、S5、S6、P5/S7与八项主路线保留，PET新专项后置、三待决不擅选。新包/最终整合回归/暂存扫描和AOCI当前治理收尾仍待完成；旧全量与旧便携WIP包均不覆盖当前源码。交接机器结果见 `OWNER_EVIDENCE/handoff-current-20261031T0900Z/`。

## 2026-10-31：持续通用开发与生产文件链（历史，本次转交前）

持续目标已恢复，PET新专项后置；HEAD仍3ef，当前源码未提交。FileStore重复操作竞态/长resume租约已修复，新增生产FileSender/ReceiverAdapter与精确完成证明的显式recover。14文件peer最终源绑定：3.12为581pass/2Win skip，含真实持久身份/双方批准/生产两helper、断线重新批准续传和240MiB/4098块/Python峰值<32MiB；3.11/3.14各580pass/2Win skip（不重复大文件），81输入稳定。不是全仓、安装态、其他OS或跨站验收，详见[当前handoff](../handoff.md#当前接手顺序)。

3ef Windows原生实际5/6通过，余HTML-video停在divider方向反常、尚未观察媒体；新增有界诊断，Linux72CPU通过。Mac解析补修和Windows诊断均待新头目标OS。Mac peer CI已加纯sender/recovery必跑，Linux502pass/2Win skip及守卫负例通过，Mac执行仍pending。

现在继续helper可重定位发行/对应源码许可/被动发现与干净前缀、真实桌面PeerService/Bridge及原生配对/分享UI；网络/跨平台与跨站、S5/S6/P5-S7和八项主路线不缩减。三待决不擅选。AOCI正式1144条仍Dirty/Stale，业务最终稳定再维护；当前无新提交/push或新包全量声明。下文转交点为历史。

## 2026-10-31：转交点（历史，3ef 已推送，peer 文件链 WIP）

所有者要求保存待办交另一 Agent；已停止扩展实现、测试和构建。HEAD/main/origin/main为 `3ef4b2716d42304d708062f9715edae0afb5874f`，447/2513/3ef已推送；20个未提交产品/测试/spec路径及本次四状态文档保留，暂存为空。当前入口是[handoff首节](../handoff.md#当前接手顺序)，以下旧停止点/HEAD/“已对齐”均为历史。

S4新增持久设备身份、public pin/双方会话、冻结manifest/安全IO、接收journal和可选文件B通道，仍是工作树中间态。接收端17项通过但两已知问题未修：重复操作须最终写租约内重查、resume长前缀扫描须移出Authority租约。发送协调器尚未创建，生产FileStore/Endpoint未集成，桌面配对/分享、helper发行和跨OS/站点尚缺；不能称S4完成。当前endpoint定向301/301、早期联合408/408及纯codec三Python各286均有各自源码边界；详情见handoff/验收。

07:40:57UTC同头attempt1：Desktop41178119889 completed/failure（Mac编译、Windowsnative失败），Runtime41178119790 success10/10；前头终态push前提满足，平台未通过。Mac解析补修已在WIP且只验Linux24/24；Windows最新日志/工件待调查。无新包或当前全量结论；AOCI仍Dirty/Stale，业务最终稳定后按实时Guide维护。

下一步先修receiver两问题/接发送端并做真实helper大文件和故障撤权恢复，处理新平台失败，再完成bridge/UI/发行/网络纵向；S5/S6/P5-S7与[八项通用路线](#2026-10-24通用能力优先的后续交付)保持原范围。PET新专项后置，三待决不擅选。本次仅交接文档，没有新产品测试/提交/push/CI触发。

## 2026-10-31：通用owner交付候选（历史，源码447/2513）

**当前转交指令：** 所有者要求把待办写入handoff交下一Agent，本次停止扩展实现；本地447/2513未推送，六份记录资产未提交、暂存为空。先依[接手待办](../handoff.md#接手先做的待办)核AOCI最终机器收尾、最新`package-final-docs-02`重绑和实际暂存扫描，再提交记录/push并跟新头平台CI。整份计划仍未完成；本次未新增产品测试或CI触发。后文“持续目标恢复”为本次转交前的历史，不是要求本Agent继续开发。

持续目标已恢复，通用优先、PET新专项后置。主链 `447a19ac8199c62ba81be5aef5458b4135b04410` 和Apple重显后时间滑条补修 `2513c08817bb9036bc63ffd341503f6d85a29aaf` 已在本地main提交，源码/测试稳定。本节为推送前快照；真实远端和新头CI请先核Git/Actions，不沿用下方旧HEAD/WIP/停止状态。完整接手入口见[handoff](../handoff.md)。

Python最终4716通过/16跳过/2排除，安装585/585、额外实际owner→worker1/1；原生候选2056/2056零skip。其后CI守卫增量独立验证、2513六目标构建及72/72 CPU零skip，529输入稳定；Linux不编译Apple/Cocoa/Win32条件分支，新头OS验收仍必要。owner实现不等于P4/S4整体完成。

11份Observed的完整源码审阅和当前SHA匹配已闭合，Baseline确认已应用；正式剩余11项加四文档共15项已Apply，Verify/Check对齐、Guide complete=true/none、1144条。最后交接文字同步及最终身份在 `OWNER_EVIDENCE/handoff-final-20261031/closure.json`，旧Observed/提交扫描在`delivery-02/`（绝对根见handoff）；实际记录暂存扫描仍待下一Agent。ACK本身不创建Entry。最新文档重绑为`package-final-docs-02`，不重跑585、不扩大原sdist范围。

接续仍含新头P4/S3平台、S4持久身份/配对UI/授权文件/helper发行/跨站、S5文献两层检索/可核引用/陪读及文本结构化后续语音窗口共享、S6真实来源复现、P5/S7完整发行及三待决。不得以本批通过缩小八项原路线或宣称材料有效，PET新专项继续后置。

最新交接文档包来源重绑已通过：已测wheel整包a6e5…不变，新sdist SHA `df2d4fa3cbb177d861cb32dae66a0cff3be6195787b654d401a96672bbc29f40`；995源成员仅runtime-validation变化，未安装或重跑585。证据 `OWNER_EVIDENCE/package-final-docs-02/rebind-summary.json`。上一`package-final-docs-01`的c213…仅为此前文档快照；本计划和handoff未被包装进sdist，最后文字同步不影响包成员。

## 2026-10-31：转交点（历史，05:45 UTC）

按所有者要求保存待办并转交另一Agent，实现/构建已停止，native构建窗口释放。当前本地main/HEAD为 `447a19ac8199c62ba81be5aef5458b4135b04410`（43路径owner/bridge/桌面及契约实现），尚未推送；origin/main和官方远端仍6126。暂存为空，7个tracked修改包含四状态文档、两AOCI资产及唯一源码WIP `reports_native_window.cc`。当前状态与接手顺序见[handoff](../handoff.md#接手后的实施顺序)，下文进行中叙述均为历史快照。

最终Python4716通过/16跳过/2排除，独立安装585/585、额外真实owner→worker1/1；原生候选完整2056/2056零跳过、2816输入稳定，均有独立closure。全量后CI守卫增量已验并提交447；之后Apple rewind-after-show fixture补修未构建/测试，不纳入2056结论。官方6126 Desktop41163547328已completed/failure、Runtime41163547349成功；447无新头CI。P4/S4未整体验收。

下一步验证窄Apple补修、记录真实后续代码提交、最终包文档重绑、补P4 Observed复核并按实时Guide闭合AOCI（当前blocked/observed_pending）、最终暂存密钥扫描及main交付。S4其余配对/文件/helper/跨站、S5、S6、P5/S7和三待决仍保留，PET新专项后置。本次仅交接整理，未新增提交/push/产品测试/CI重触发。

## 2026-10-31：通用路线续接（历史）

转交后持续目标已明确要求继续推进，PET 新专项保持后置。owner typed rejection 与本地 prepare 恢复已接入原生页，candidate-08 定向20/20，四布局 Data流程各13clicks；candidate-10完整授权/两轮评估准入/独立启用回退/撤回审计四布局4/4、各50clicks，均保Viewer/隐藏稿，CPU事件不代OS/GPU。统一2056项原生回归仍待结果。审查补修了活动模型 CAS 的登记前只读预检：已知拒绝不留未知 intent，后续竞态仍保持 uncertain；新后端三 Python各112/112。当前新包逐项681/995来源核对、独立安装585/585零跳过，包含8项真实算法/Runtime/网络门；完整 Python首轮启动器120秒限已终止并保留，新python-full-02以1800秒总限和同1010输入运行，不改单测门槛，不提前标完成。

完整Python已闭合：4716通过/16跳过/2排除、零失败错误，1010输入稳定；15项旧SIG11渲染跳过全部实际通过，8项真实算法/网络必跑零跳过。额外桥/认证HTTP owner授权到实际worker、单次collect及撤回接线1/1通过。统一原生全目标构建853.95秒/2816输入稳定，2056项CTest仍运行；不提前标完整原生通过。

P4本地72CPU通过，Windows6126实际3/6，Mac/Win候选尚待新CI。`main`仍6126、全部WIP保留，未stage/commit/push；最终原生结果、四状态记录、AOCI维护及暂存扫描仍在收尾。S4其余范围、S5/S6/P5-S7和三项待决不变，详见[当前交接](../handoff.md#当前续接与下一步)。

## 2026-10-31：S4 owner WIP 转交（历史，04:20）

所有者最新要求保存待办交另一 Agent；已停止实现、构建和测试，本次仅整理四状态文档，未 stage/commit/push。HEAD/main/origin/main 与官方远端仍 `6126c6a22cc19270aedd135fb97c09b949c49f9b`，暂存为空；当前 40 个未提交路径（27 tracked、13 untracked）包含 owner/evaluation/models、Runtime/bridge/Schema、独立 Federation 编辑器和测试。此前“无产品源码、仅草案”不再代表当前状态；完整路径及接续顺序见 [handoff](../handoff.md)。

04:20:50 UTC 官方快照：Desktop41163547328 已 completed/failure（4成功/2失败，04:08:08更新），Runtime41163547349 completed/success。前头 Desktop 终态等待前提满足，P4 未验收。后端三 Python 各113/113、Runtime60/60；bridge 最后 JUnit21/21 尚无 typed rejection 新专项；原生 candidate-06 构建成功，13项8通过/5失败，后续修正未重编复验。旧4589/402覆盖已推送网络基线，不覆盖当前 WIP。

下一步先补原生 typed rejection 的原请求绑定、fresh owner info/new UUID 门与本地 prepare 确定验证失败恢复，再补 bridge/原生反例、最新 Schema 重嵌入及全链点击。随后完成 additive bridge 文档、精确 proof 契约、最终源码回归/独立安装/真实 worker 证明；稳定后才维护 AOCI 和交付。P4 Mac/Windows 当前失败继续取证，S4其余配对/文件/helper/跨站、S5/S6/P5-S7与三项待所有者决定保持，PET新专项后置。证据入口 `OWNER_EVIDENCE/handoff-20261031T042050Z/closure.json`（根路径见handoff）。

## 2026-10-31：首轮转交点（历史，当前见最新首节）

所有者最新要求保存待办并转交；本轮停止产品实现，仅更新四状态文档及必要AOCI托管资产，未提交/push或重触发CI。交接前本地main、origin/main和真实远端均 **`6126c6a22cc19270aedd135fb97c09b949c49f9b`**，工作树干净；网络源码a5510bfa、Windows10b784ba、布局b02a51cd、Mac宿主dd318ce2及记录/AOCI6126均已交付。旧WIP、待重包和待24对象维护描述保留为历史，不再当现状。

03:29:04 UTC快照：Desktop **41163547328 in_progress**，下一次代码push等待整个run终态；Runtime **41163547349 in_progress**、9项成功；Docs41163547325与Secret41163547316成功。均同head6126、attempt1，完整快照 `NETWORK_EVIDENCE/ci-6126/handoff-20261031T032904Z.json`。P4新Mac/Windows原生结果仍未完成，Linux72不替代目标平台。最终包已逐字节重绑：wheel与402项已测包相同，sdist仅测试guard及验收文档差异；未重跑402/4589。本次更新文档晚于该sdist，不能声称已入旧包。

下一实施片段先做S4 owner数据登记/同意/撤回/审计及独立线性评估、显式准入/切换/回退，再接bridge/桌面；**目前只有设计草案，没有owner/evaluation/models新源码或路由**。原请求UUID、固定grant身份、私有root、两capsule部分登记恢复和baseline generation须先闭合。详见 [handoff](../handoff.md#接手后的实施顺序)；剩余仍含S4配对/文件/helper/跨站、S5、S6、P5/S7。PET新专项后置，三待决不擅选，整份计划不标完成。本次文档/AOCI收尾实况见 `NETWORK_EVIDENCE/handoff-transfer-20261031/closure.json`。

## 2026-10-30：持续目标已恢复，S4网络及Windows裁剪源码已提交（历史交付）

所有者重新激活通用开发目标，PET新专项仍后置。S4私有Runtime/出站网络源码 `a5510bfa838e34e5555f0c6beaa4e0e6b04d190a` 已在main本地提交，25个文件、暂存差异gitleaks零发现；Windows WGC有效ContentSize裁剪 `10b784ba262fae7bbd26c5d1f2d39398019f5ec1` 已提交，实际Linux增量全目标构建成功，相关72/72零skip、三个新反例实际执行。仍须新头Windows编译/WGC和完整原生20轮，Mac媒体/Windows布局门继续按证据处理。

网络完整Python4589/31skip/2deselected、独立安装候选402/402以及最后导入guard26/26分开保留原适用范围；最终包重绑、记录提交/push/新CI和24对象AOCI维护/Verify/Check/Guide结果见 `NETWORK_EVIDENCE/delivery-closure-summary.json`（证据根见handoff）。最后Observed一项已review/ack，Guide核零pending/Recovery；不能把此前维护blocked快照继续当当前门禁。上一已推送38a9fd43的Desktop已终态失败、Runtime成功10/10，push等待门已结束。

视频原生验收布局fixture另提交 `b02a51cdea47868e4c599fdbc763ed80ddd1e3b7`：Reports右侧却要求左侧并固定负drag的问题已改为按真实左右顺序，传入/保护原Viewer，真divider事件与完整媒体/同导航暂停时间/终态草稿门不变。实际probes-ON增量构建33.882秒、exit0，相关72/72零skip、1.326秒，源码稳定；证据 `NETWORK_EVIDENCE/p4-next/layout-01/summary.json`，实际单文件暂存gitleaks零发现。Linux只证明编译和相关CPU行为，不证明Mac激活或Windows原生视频/完整20轮。此fixture不进入Python包；最后Observed复核与本批24对象维护结果见closure。

Mac验收宿主追加修正 `dd318ce287bc1d52fd8da324026c321e984dc55c`：普通未打包test executable先显式设置并核验Regular激活策略，再请求自身窗口激活；原active/key/精确窗口合取与5秒UI观察门保留。失败/超时写固定before/after/final整数/布尔快照和计数，轮询不写盘、不识别外部窗口。`p4-next/macos-activation-01/summary.json`：Linux增量全目标构建exit0、32.146秒，原72CPU用例名称集合相同且72/72零skip、1.309秒，三源SHA稳定，暂存gitleaks零发现后提交。**Linux不编译Cocoa分支、不证明真实激活/OS像素/20轮**；38a未记录policy，不能断言原运行态就是prohibited。未打包程序默认策略与setter返回值依据 [Apple activation policy](https://developer.apple.com/documentation/appkit/nsapplication/activationpolicy-swift.enum/prohibited?language=objc) / [setActivationPolicy](https://developer.apple.com/documentation/appkit/nsapplication/setactivationpolicy(_:)?language=objc)，策略成功仍不替代原激活观察。

本批之后推进S4桌面数据同意/撤回/审计、独立线性候选评估和显式准入，再做配对/文件/helper/跨站网络及S5/S6/P5-S7。联邦线性bundle不能当作现有pe_loop/capacity_fade的MLP权重激活，须按真实模型契约处理；三待决不擅选，整份计划不标完成。当前入口为 [handoff.md](../handoff.md)。

## 2026-10-30：转交检查点（历史，当前以最新首节为准）

所有者最新要求是保存待办并交给另一 Agent；本轮停止扩展实现，仅更新四状态文档，不提交、推送或重触发CI。当前 `main` / `origin/main` / 真实远端均 `38a9fd433c1924a5bcc068e4bd1643e3f7c82bbf`；25个网络业务/测试/契约文件仍已暂存，四状态和AOCI baseline未暂存，必须保留。最新接手入口为 [handoff.md](../handoff.md)，旧交接段落均为历史。

S4实际TCP/WSS与三Runtime训练链已实现：工作树联合352/352；完整Python **4589 passed / 31 skipped / 2 deselected**、1000输入稳定；独立安装候选 **402/402、零skip**。完整/安装后仅改Hub测试的可选依赖guard，另补26/26及缺依赖collection无错误验证；本次状态文档又改变sdist中的runtime-validation，交付前仍需新包逐成员绑定，不能声称最终全量重跑。Desktop41097301277现已 **completed/failure（4成功/2失败）**，Runtime41097301247成功10/10；前头push等待门已结束，P4平台仍未验收。外部Windows ContentSize裁剪候选未应用，缺Windows/WGC实测。AOCI仍因一个Observed指纹待复核而阻塞，8 missing/13 stale的正式语义收尾、最终暂存扫描/main交付均交下一Agent处理；实时结果见交接所列外部收尾目录。

先完成本批收尾与P4目标平台修复，再按下表继续S4桌面consent/审计/模型准入、配对/文件/helper/跨站网络，S5知识库、S6复现闭环、P5/S7离线整合。三待决不擅选，PET新专项后置；没有新增产品UI点击验收，整份计划仍未完成。

## 2026-10-30：S4网络训练纵向链（历史进度，状态以上方转交点为准）

持续通用目标恢复后，已完成owner-bound Hub/独立FL CAS、固定ClientApp的私有Runtime训练、出站NodeAgent、持久Node与显式coordinator/client。三个独立Linux Runtime/三个出站agent经真实loopback TCP/WSS完成FedAvg/FedProx各两轮，独立梯度参考一致；全联邦+Hub联合352/352、零skip，含4个真实dtype×strategy训练和2个真实隔离聚合。私有身份出口、原请求恢复/不重发、模型SHA绑定、取消次序及大型历史查询均有审查反例与修复。

业务尚未提交/push；最终新包安装绑定、完整Python和AOCI收尾待完成，38a9fd43同一Desktop仍未终态。S4桌面授权/审计/模型准入、配对/文件/helper发行及跨站网络验收仍缺；loopback不冒充NAT/TURN或科学有效性。具体证据、剩余顺序见 [handoff.md当前首节](../handoff.md)。P4平台、S5/S6/P5-S7、三待决及PET新专项后置不变。

## 2026-10-30：交接检查点（历史，38a9fd43，新网络草稿未验证）

所有者要求写待办并转交另一 Agent，已停止实现和轮询，保留 8 个联邦网络 WIP 文件；本次仅更新交接/状态记录，不提交或 push。已交付基础源码11844b25及记录/AOCI头38a9fd43均已推送，本地与远端一致。17:42 UTC重查：Runtime41097301247 completed/success（10 jobs，独立Flower230/230零skip），Desktop41097301277仍in_progress，下一次代码push等待门未满足。旧“真实Flower尚未跑、基础尚未push”已是历史。

当前草稿为 Hub run/设备映射、独立FL CAS/action授权、冻结训练协议和私有数值capsule/固定ClientApp worker；**尚未语法检查或测试**，NodeFederationService、NodeAgent/CLI接入、持久coordinator及新测试尚未完成。下一轮先审查草稿与私有数据隔离/训练幂等/撤回边界，再做真实Runtime和三个出站Linux节点多轮STK网络验证、桌面同意审计/模型准入；P4平台结果并行跟进。完整文件清单、接口、测试顺序、证据及AOCI待收尾见 [handoff.md当前首节](../handoff.md)。S4、S5、S6、P5/S7仍未完成，PET新专项后置，三待决保持不变。

## 2026-10-30：联邦基础续接（历史，源码11844b25，S4未完成）

转交检查点后持续目标恢复，源码 `11844b257e3a88f0db1e08611624a295e64b13c2` 已本地提交：严格数组/整轮准入、本机逐数据集逐 run consent/outbox、独立 Flower 聚合和精确依赖/指南、独立算法 CI 门禁；同批 Windows fixture 时序/句柄与原生验收候选补修。完整 Python 首次 4467 通过/31 跳过/2 排除，873 输入稳定；联邦安装联合 230/230 含真实 f32/f64、三 ClientApp 六轮/18 份审计更新及独立数值参考通过，但用的是本机 pipe，不是 S4 的 STK 出站网络。Linux 最终 all/相关69 CPU通过；新 Mac/Windows 修正待目标平台 CI，Windows WGC 只补尺寸诊断，不假定根因或降低门槛。实际记录/push/AOCI/新CI见本批 `FLOWER_EVIDENCE/delivery-closure-summary.json` 与[交接](../handoff.md)；未成功的收尾仍待完成。S4 产品/网络训练、S5、S6、P5/S7 与三待决继续，PET 新专项后置。

上方11844b25的原15个离屏SIG11 skip已在私有Xvfb/llvmpipe补验15/15、零跳过，873输入与full同摘要；原full记录不改写，软件GL不替代Mac/Windows原生验收。

## 2026-10-30：转交检查点（历史）

所有者要求保存待办并转交另一 Agent。[交接文件最新首节](../handoff.md)为当前接手入口，覆盖后文旧 CI 时态。本地与远端 main 均为 `bccb32d7`；上一 peer 代码/记录/AOCI 已推送。联邦数组/整轮校验、本机 consent/outbox 和隔离 Flower 聚合适配仍为未提交 WIP，便携联合 228 项通过，但两个真实安装态聚合测试尚未执行；候选构建/安装/依赖检查不代表训练或 S4 完成。

该头 Desktop `41082221172`、Runtime `41082221295` 已终态失败，Docs/Secret 成功。继续处理 Windows SQLite fixture（工作树已修、三版本各 21 项通过，待 Windows）、Windows 3.12 watchdog 排队时序，以及 Mac 焦点/媒体 viewport、Windows WGC 几何/viewport；不降低原生验收门槛。接手顺序为真实 Flower 子进程验证与本批审查、平台修正、联合/安装回归和 AOCI/暂存扫描/交付，再补 S4 真实 STK 网络训练与配对/文件/网络产品缺口。S5、S6、P5/S7 仍按下列完成条件推进，PET 新专项后置，三项所有者待决不变。本次仅保存交接，不提交或推送，不将 WIP 标为已交付。

## 2026-10-24：通用能力优先的后续交付

所有者要求完成本计划的主要内容，先完成通用功能，PET 等具体场景推迟开发。
以下顺序覆盖后续工作；旧段落中的“下一步”若与这里冲突，以此处为准。每项以实际验收为完成依据，
不能用当前编辑器补丁、工具配置或单个平台通过代替整份计划完成。

本批记录提交、push、AOCI逐批维护/Verify/Check/Guide及新CI的实际状态见 `PEER_EVIDENCE/delivery-closure-summary.json`，证据根见交接；旧handoff检查点保留作历史，不当作当前未推送状态。平台与S4产品缺口仍按下文完成条件验收。

**2026-10-30 S4本机后端原型已实现，整项未完成**：本批代码`51a795b9`已提交；上一交付头`cfb8c561`。新增独立peer协议、实际WebRTC helper、双方Ed25519通道绑定认证、持久项目授权/撤销和复用共享store的分页/CAS/原子回执。ACK修正前联合198/198、最终端点/协议141/141、三Python版本授权/项目/协议各143/143；最终fresh安装202 peer+1许可边界203/203，均零跳过；缺libnice运行路径导致的首轮40失败已保留，补齐环境后复验通过。完整Python首轮4231通过/31跳过/2排除、1许可路径检查失败；仅改transport说明后原门禁精准1/1通过。最终ACK方向已修，独立规范对端4项红→绿；新安装203/203、551份py/Schema与真实安装来源均核对。业务包与最终文档包分别绑定，不把旧全量写成新源全绿。[peer指南](peer.md)列出可执行入口与运行库要求。桌面配对/持久身份、Mac↔Windows原生端点、部署信令、授权文件传输、IPv6→UDP（含端口预测）→TCP→TURN443完整策略及独立Flower多节点训练尚未完成。

`cfb8c561` Desktop `41001132256`已终态失败：Windows CPU成功、发现修正已获验证；Mac静态格式/spike成功、两个视频失败且video报告pause_failed；Windowsnative六项0完整轮/0图。Runtime `41001132201` 7/8成功，仅Windows3.12字段篡改测试在无关simulate子进程20秒超时；Docs/Secret成功。当前Windows精确捕获原点/局部排队输入、Mac有界暂停核验及测试隔离修正已入上述代码提交，相关CPU最终65/65、零跳过；本机不编译Cocoa/Win32，仍待新平台CI。第3项和第5–8项继续，PET新专项后置；[交接](../handoff.md)及[验收](runtime-validation.md)为本批证据与待办入口。

**2026-10-29 S3b通用训练本机验收完成，平台待新CI**：后端`fca7fcf0`、预算补修`99bea12b`、桌面页`384c16bb`、布局补修`c236816a`已在main；同批平台修复`d64023ce`和Windows诊断`62984f28`。冻结输入、实际迁移初始化、同留出集模型比较、持久任务/曲线及桌面操作已实现。最终原生2021/2021、零跳过，Linux必跑413次/1545匹配；新30项含16实际GPU图片，四布局固定起点冻结/启动3点击。完整Python3911通过/31跳过/2排除，最后后端补修83项及15离屏补验通过。隔离安装业务候选五文件198/198通过；三版本及所有限制见[运行验收](runtime-validation.md)；[训练契约](specs/materials-training-1.md)不改变合作格式。前头9da Desktop已结束且Windows主回归成功，独立native六项仍0轮/0图；相应编译/原子替换修正与诊断待新CI。第3项平台和第5–8项继续，PET新专项后置。

**2026-10-29 本批源码**：平台/LaTeX修复 `852860ae53327ae11fec9cb1a459d64f247bc1cd`，冻结MP4 `8627d98184af62548a4b23b0d1e41e4f2856f6f3`。MP4入口及文档内视频、精确资源、隐藏暂停/重显不续播已实现，候选默认关闭；Mac/Windows真实播放与完整P4验收仍待新CI，Linux Unsupported不作播放验收。本机原生1991/1991零跳过、Linux必跑405次/1515项匹配，最后补修后编译专项5/5；Python完整3708通过后目录补修三版本各86通过/6项Windows专用跳过。隔离wheel十文件456通过/6项Windows跳过，最终文档包逐字节对照见运行验收。前头f331 Desktop与Runtime均已结束且有Windows/Mac失败，已有证据修正仍须新头复验，P4不标完成。第4–8项及三项待决定边界保持原范围。

上一批交付（LaTeX）：主链源码 `51a01af143496eeaf58b39b4a6547af45e55176d` 与来源意图门禁补修 `3d4998d613597d93c6da4b7688775a7e854df57a` 已在main；[LaTeX指南](latex-workflows.md)覆盖冻结输入、明确编译、失败日志和源码定位。完整主链Python3644/原生1956通过，最后小修后3版本专项各79、原生定向29通过，真实TeX两页PDF及隔离wheel保存/重开/导出链通过；这些范围见运行验收，不冒称最终全量或平台通过。前头3ac89623 Runtime8/8、Docs/Secret成功，Desktop已结束：Linux三job/Windows主回归成功，Mac仅PDF色条判据失败（首页已显示），Windows独立native崩溃；有界AA和RIP0诊断补修须新平台CI。P4仍有视频与完整双平台验收，第4–8项继续，PET新专项后置。

`035f7bd9` CI已结束：Runtime三个Linux版本及web/desktop/control成功，两个Windows客户端因超长pytest案例ID报错，短ID修正后三版本报告各46项通过；Desktop Linux三job/Windows主回归成功，Mac正式报告三像素失败、独立原型通过，Windows独立native四项访问冲突且零图；Docs/Secret成功。独立AI报告表单源码 `64205ba809aacef568d1d85637ee777c9ac8aa50` 已提交main，workspace v3与保存后90秒等待边界已统一构建，最终完整原生1951/1951、零失败/错误/跳过、465.52秒；含15控制器＋12中英宽窄UI共27项报告用例，Linux必跑405次核对、1481项匹配。四组各39点击/14键（含最大化1键）/6文本事件，源码暂存密钥扫描258612bytes、零发现。最终记录与认知资产随本批收尾，新平台CI仍待复验。

**第3项继续，报告模式与生成后端已完成本机验收。** 源码 `15edede30c46bc6639eeab910d739bf01fdb762b` 已随记录头 `035f7bd9` 推送 main。
新增文档与报告布局，与准备/分析布局独立记忆，保留 Viewer、隐藏草稿及旧布局兼容；固定默认起点每模式2点击。
专用报告请求冻结真实上下文、复核来源及可选快照附件；明确发送、编辑完整回复后以一次可撤销编辑保存 `stk.report/2`，
来源、原输入/回复及编辑正文均可读回与导出，普通 `/1` 不变。**完整桌面 AI 表单已提交并完成本机完整回归，平台仍待复验**；LaTeX、视频及平台验收仍在，不能标记 P4 完成。

统一构建退出0，完整原生 **1924/1924、零失败/错误/跳过、469.57秒**，Linux全部必跑核对 **1454项匹配通过**；
报告/模式/项目范围定向149/149。Python完整首轮3549通过、2失败、24跳过、2排除；两处新增接口精确清单漏项已修、相关91通过。
新生成后端46项、真实桥/worker4项通过；3.11/3.14相关各196项通过。运行器修正
`5a6f6fd1f6a1f4b66862a649bb29fdf176bcae02` 已随 `035f7bd9` 推送，三 Python 版本 Runtime 各36项与桌面相关4/4通过，
最终 wheel/sdist 离线重建和隔离安装报告/Runtime 82项通过；最终完整 Python **3562 passed、24 skipped、2 deselected、零失败、705.26秒**。

前头 `b32fd0c7` 的 Desktop `40264284403` 已结束：Linux三job成功；Mac编译/CPU/Metal/应用冒烟成功，
正式报告窗口程序止于创建测试项目前置失败，尚未证明三格式显示；Windows编译失败、原生独立job跳过。
本批修正discovery标签引号与主线程Ready等待，仍须新CI。Runtime `40264284376` 的3.11丢失worker用例失败、其余7job成功，
本机已确定复现用户程序执行先于身份发布的启动窗口并完成修正；不能由本机复现断言远端同根，仍须新CI复验。Docs/Secret成功。

正式 Markdown/HTML/PDF 文档宿主已接入，原生候选默认关闭，Linux Unsupported；Mac/Windows OS呈现、IME/跨屏DPI与浏览器内存继续验收。
独立AI报告表单的平台验证、LaTeX、视频和第4–8项继续，PET新专项后置。详见[运行验收](runtime-validation.md)。

| 顺序 | 通用交付范围 | 尚需证明的完成条件 |
|---|---|---|
| 1 | 已交付：表格／节点编辑器的记录详情、类型化参数、本地撤销重做与草稿保护 | 已有构建、完整回归、跨平台 CI 与固定起点点击记录；后续改动持续保护明确保存、运行及发送 |
| 2 | 主要功能已交付：富对象预览、填充与看板、大表查询、工作模式布局、子流程及技能版本管理 | 本机库跨平台 CI 成功；Linux 软件 GPU 真实窗口性能已测，硬件 GPU 与其他平台性能并入持续验收 |
| 3 | P4 文档报告：内嵌 Markdown／HTML／PDF、数据和资产引用、LaTeX 编译、图像及视频预览 | 真实原生窗口嵌入验证；文档与运行版本关联；编译日志、失败处理、导出和重新打开均可验证 |
| 4 | S3 通用训练（本机已验收，跨平台待验证）：数据校验、迁移学习、基模型比较、准入门槛、版本回退与桌面训练视图 | 冻结训练／评估数据与模型来源；未达门槛不替换；数据卡、进度和曲线具有真实任务证据 |
| 5 | 跨平台连接、S4 联邦与协作基础 | STK 配对、能力协商、项目操作和文件传输；WebRTC 网络自检；独立 Flower 环境完成多节点训练，对外 hub 不安装 flwr |
| 6 | S5 文献与知识库、共享会话 | 本地 PDF 解析、两层检索与可核对引用；按既定授权的陪读及结构化共享；不能以现有旧 Qt PDF 截文代替 RAG |
| 7 | S6 通用复现闭环 | 文献设置→冻结工作流→明确运行→数值／曲线对比→带来源报告；缺参数与失败保留，不伪造复现成功 |
| 8 | P5／S7 完整交付及通用模块整合 | 干净机器离线安装与 Python 环境；平台文件对话框、IME／缩放／快捷键／恢复／性能；模型更新与回退；toolkits 按职责迁移并验证兼容导入及 wheel/sdist |

平台回归贯穿各批次；通用计算引擎整理、执行目标与模块安装，以及 ABACUS 接入按依赖安排。
PET 新的业务字典、厂内专项部署、专用训练、长链／气体收敛和材料指标验证后移；保护已经交付的 PET 功能与证据，
也不把这些专项验收写成通用平台已完成。通用能力可用公开或合成数据验收，科学结论仍需独立证据。

仍待决定的 S3 合作数据格式和 MuPRO 电场扫描、S2c 权限扩展、分析修改提案的持久形式见
[当前交接](../handoff.md#三项待所有者决定)。这次优先级调整不替代这些决定；独立的通用工作继续推进。

第 1 项已推送 `4f919c7`：既有编辑器修改已构建，本机完整原生 **1592/1592、零跳过**，相关必跑 **164/164**；
Python 完整 **3025 passed、24 skipped、2 deselected**，3.11／3.14 相关各 **49 passed**。
记录详情、类型化参数、局部历史及隐藏草稿保护已完成本机回归；默认节点工具栏的“三维”入口宽度已修复，
中英文三档缩放布局通过。Runtime **8/8**、Docs、Secret 已成功；Desktop `40154110887` 已全部结束，Windows 及三项 Linux 作业成功，macOS 测试编译暴露
`auto` 混合推导问题，已由 `027798f` 修正且新 Desktop **5/5 成功**，详情见[本轮验收](runtime-validation.md#2026-10-25通用编辑器本机验收)。
第 2 项后端查询优化已推送 `027798f`：普通视图先分页，筛选／排序按字段投影读取并保留完整依赖语义；
两表各万行的实际性能与边界见[查询验收](runtime-validation.md#2026-10-25表格按需查询与平台修正)。
本批完整 Python **3040 passed、22 skipped、4 deselected**，另补深依赖链验证；原生 **1592/1592、零跳过**。
该提交 Runtime `40156836276` **8/8**、Docs、Secret 成功；Desktop `40156836215` 已全部结束并 **5/5 成功**，macOS 编译修正已获验证。
独立准备／分析布局源码提交 `85630acbb04f419ac7a13b0d5f99e08990cd91f9`，定向 **72/72**、完整原生 **1604/1604、零跳过**，每种模式 **2 次点击**；记录／索引提交 `d1493fa` 的 Desktop `40160203772` 已全部结束且 **5/5 成功**；见[本批验收](runtime-validation.md#2026-10-25工作模式布局)。
填充柄源码提交 `b2b076d669e6089fd700d4ff02097aaee60adb0b`：定向及必跑 **57/57**、完整原生 **1612/1612、零跳过**；
按可见顺序重复类型值与公式定义，一次 CAS／撤销，固定起点 **1 次选格＋1 次拖动**；`35637ea` 的 Desktop **5/5**、Runtime **8/8**、Docs／Secret 均成功，见[填充验收](runtime-validation.md#2026-10-25表格填充柄)。
看板拖动源码提交 `752d1ea9016ff6730fa7cb3df4a22e9ecfd5a811`：定向及必跑 **64/64**、完整原生 **1619/1619、零跳过**；单卡拖到单选状态列，
固定当前看板起点 **0 次额外点击＋1 次拖动**，一次修订／撤销并保留 Viewer。记录头 `b1673ee` 的 Desktop `40167186317` **5/5**、
Runtime `40167186293` **8/8**、Docs／Secret 均完成成功，见[看板验收](runtime-validation.md#2026-10-25看板拖动)。
附件详情预览源码提交 `bc2896a89f2e357d30ea8bda3a246190604cc411`：明确读取 PNG／UTF-8 文本，冻结文件核完整摘要，
已选对象格起点 **2 次点击**，不改修订、选择或 Viewer；最终原生相关及必跑 **59/59、零跳过**，Python 修正后相关 **25/25**。
首次完整回归两处测试断言失败及复验记录见[附件验收](runtime-validation.md#2026-10-25附件详情预览)，新 CI 待确认。
单文件最多 1 MiB，文本前 64 KiB；Markdown／HTML 原样显示，不代表 P4 内嵌渲染完成。
项目技能版本源码提交 `073c608a271c4dea001a49432879f174f2afab7c`，固定、升级、恢复和创建保存分析已通过本机验收：
完整原生 **1639/1639、零跳过**、技能相关及必跑 **33/33**，完整 Python **3083 passed、24 skipped、2 deselected**，
三 Python 版本相关各 **74 passed**。版本随项目数据库迁移，目录不可用时仍可恢复；不打包执行环境，也不自动运行。
详情见[技能验收](runtime-validation.md#2026-10-25项目技能版本)；记录头 `fe083a3` Desktop **5/5**、Runtime、Docs 和 Secret 均已完成成功。
前头 `c6c39f3` 的两项 Windows 换行断言失败已在本批修正，并通过上述新 CI 复验。
JPEG／WebP／GIF／BMP／TIFF 与卡片缩略图源码 `e9f5fb6e255572d204a8a44c3204fac647913123` 已推送并完成 AOCI 条目维护，原生定向及必跑 22/22、完整 1662/1662（零跳过）、Linux 必跑 832/832，三 Python 版本相关通过；Desktop **5/5**、Runtime、Docs／Secret 均已完成成功，详见[本批记录](runtime-validation.md#2026-10-25图像附件与卡片缩略图进行中)。
项目内用户分析技能已完成本机实现：创建、追加版本、恢复与复制分析保留图、参数、输出和来源；三 Python 版本相关各 145 项、真实图执行各 1 项，原生相关及必跑 28/28，完整原生 1666/1666、零跳过，Linux 必跑 836/836。源码 `fc14bc6` 的 Desktop 5/5、Runtime、Docs／Secret 均已完成成功；子流程、全局用户目录和项目工作流整体封装继续推进，见[验收](runtime-validation.md#2026-10-25用户分析技能进行中)。
分页源码 `e30150bb47c7064c945a4c561d99e02fdea5ae69` 已推送，增加结构／记录页接口、工作台直接消费记录页、单条共享选择缓存与完整审阅基线，
文件树不再隐式读取整个项目；三 Python 版本相关各 **87 passed**，原生相关及必跑 **109/109、零跳过**。
原生首次打开现已改为结构目录＋当前表最多 200 条记录，分页与并发修订用例现有 8 项；
早期扩大回归 **249/257**、后续 **262/268**，已修正旧入口的全量记录假设、结果查询响应校验和分步读取期间的修订冲突。
最新分页／仿真／跨页工作流／脚本选择定向及必跑 **16/16、零跳过**；完整原生首轮 **1619/1656**，修正异步图形夹具与旧格式替身后最终 **1656/1656、零跳过**，相关必跑 **342/342**。
完整 Python **3102 passed、1 failed**，接口清单漏项修正后相关 **32 passed**。
工作空间预读已改为目录＋所选记录页，同修订验证后原子恢复，归档仍保存完整项目；新增三项恢复测试，相关及必跑 **24/24、零跳过**，接入后的完整原生 **1659/1659、零跳过**，当前 Linux CI 必跑检查 **829/829**。
两表各万行的原生 CPU／真实桥首屏三次中位 **2.67→0.45 秒**、原生采样峰值 RSS **190.40→31.17 MiB**；不含真实系统窗口／GPU。
更早后端长文本首读测量约 **44.75→0.45 MiB**，两套基准夹具不同；真实窗口性能尚待验收。分页源码 Desktop **5/5**、Runtime **8/8**、Docs／Secret 均完成成功；源码 AOCI 已维护并通过 Verify／Check／Guide 对齐，见[验收记录](runtime-validation.md#2026-10-25大项目分页接入进行中)。
第 2–8 项继续按上表推进，不能据此标记整份计划完成。历史文档中的旧状态按下方日期区分。

**工作流技能本机验收完成，跨平台 CI 待确认。** 源码 `bc964f26fbc233381371bb55576f166a75995107` 已接入完整方法闭包、显式数据映射、一次撤销的整体创建及桌面入口；最终完整原生 **1681/1681、零跳过**，Linux 必跑 **851/851**，相关桌面 **62/62**。三 Python 版本的新专项通过，完整回归的接口清单漏项已修并复验；中英发布 4 点击，追加／实例化／打开各 1 点击。全局用户目录及真实窗口性能仍待推进，第 2 项不标整体完成；详见[本批验收](runtime-validation.md#2026-10-25工作流技能发布与实例化在研)。

工作流技能与记录头 `f9a78c2` 已推送，23 条 AOCI 维护及 Verify／Check／Guide 对齐，Runtime／Docs／Secret 成功，Desktop `40213263506` 待结束。**全局用户技能目录源码 `6fa89943b8011730146c52e8cc339f21aa05c6d4` 已本地提交、尚未推送**：本机不可变版本库、跨项目固定、显式冲突处理及发布回执；三 Python 版本相关各 128 项、最后桥端各 7 项通过；完整 Python 3221 passed、24 skipped、2 deselected，完整原生 1688/1688、零跳过，Linux 必跑858/858，最后协议补验34/34；中英固定详情起点保存到库各1点击。真实窗口性能及第 3–8 项仍未完成。

子流程批次以已推送 `fc14bc6ec945a2b5218323098a14eafa43614f18` 为基线；该头 Desktop `40199278362` **5/5**、Runtime `40199278388`、Docs／Secret 均已完成成功。
工作树已加入带显式输入／输出／参数的 `stk.workflow/2`、有界递归展开、冻结来源和按行执行，分支变化只使相关任务及下游过期。
Python 扩大回归 268 项、原生相关 90/90（零跳过）、必跑 54/54 通过；真实 GraphWorker 验证已包含在相关套件中。
桌面公开接口、默认值编辑、子流程进入／返回和父子独立草稿已进入工作树；中英文公开输出后保存为 2 次点击。JSON 默认值保真及过期检查已补测，三 Python 版本核心各 78 项通过；新增桌面及必跑 5/5、零跳过。完整 Python 3166 项通过、24 跳过、2 排除，最后修正由相关套件补验；最终完整原生 **1674/1674、零失败／错误／跳过、398.37 秒**，Linux 必跑 **844/844**。
本次子流程交付后继续工作流技能与全局用户目录；工作流技能最新进度见上。子流程源码 `3a1204f4a9fa0618d0523cdca85b8b5595d1fb5e` 已推送 main，AOCI 源码维护已对齐、暂存扫描零发现；Desktop `40208002864` 已全部结束并 **5/5 成功**；Runtime `40208002879`、Docs `40208002935`、Secret `40208003007` 均已完成成功。
后端及原生草稿支持不替代第 2 项完整完成，状态和失败历史见[验收](runtime-validation.md#2026-10-25子流程与工作流封装在研)。

## 2026-10-08：思劲平台方向（所有者已答复三轮）

**2026-10-24 开发工具接入**：官方固定版本 Serena 2.1.0、jscpd 5.4.2、Knip 6.42.1 已安装；
Serena 以 Python／C++／TypeScript 的只读语义导航补充 rg，检查器按需运行，报告不自动触发代码删除。
配置、协议实测、上下文开销及局限见[工具指南](ai-development.md)与[验收](runtime-validation.md#2026-10-24ai-开发工具配置与上下文测量)。
当前 handoff 已压缩为状态和入口，历史 AOCI 建立、停止及恢复记录统一按需查阅[开发日志](development-log.md)与[验收记录](runtime-validation.md)。
main／origin/main 仍为 `7e0e6b1`，原有 22 个产品文件保留；本轮未构建产品、提交或推送。
下一产品任务仍需先修复既有编译失败，再完成表格／节点编辑器验证；S2c、S3 等待决事项不因工具安装而解锁。

**2026-10-15–16 表格交换与可移植工作空间（`29e9fe9`／`2299b2a`／`070f81e`／`76715e4`已推送，跨平台CI全部通过）**：
CSV、Excel（XLSX）和类型化 JSON 从表格工具栏直接进入，预览绑定 SHA 与项目修订，导入一个原子编辑批次；导出当前视图的计算值。
`.stkworkspace` 保存全部窗口／标签的布局、参数与草稿，连同一致数据库、项目资源和已明确打开的外部输入，导入新目录后恢复并支持二次搬移。
各编辑器独立状态／资源 hooks；Viewer 当前数据与各窗口相机可冻结恢复，重新运行仍需明确操作。
主机凭据、模型／网络配置、依赖程序和活进程不迁移；缺失或未知路径给出完整性诊断。
表格文件不保存表达式／历史，XLSX 不保留外部工作簿样式或宏；完整项目和桌面状态使用工作空间文件。
本机完整原生1539/1539、74项必跑、Python相关三版本各103/103，新源码包解压独立103/103通过；wheel、连续迁移和PET两格式离线复核通过。
`070f81e`精确Runtime **8/8**、桌面 **5/5**、Secret／Docs均成功；Linux1539/1539、Mac CPU991/991／Metal226/226、Windows936/936，均零跳过。
Windows8项Viewer恢复全部实际执行，前两轮路径／扫描替身／标签与平台目标遗漏问题均修复，保留原失败证据。
导出提示另将内部术语“已安装窗口”改为“已打开窗口”（中英）；i18n与8张图形检查通过，前代码桌面全部结束后已推送文案修正`76715e4`；其Runtime 38956470955 **8/8**、Desktop 38956471084 **5/5**、Secret／Docs全部完成成功，Windows936/936与8项Viewer恢复再次实际通过。
指南与协议见[表格交换](project-table-io.md)、[工作空间](design/portable-workspaces.md)、[表格契约](specs/table-io-1.md)、[工作空间契约](specs/workspace-1.md)；实际结果见[验收](runtime-validation.md)。

**2026-10-15 本地科研多维表格（本轮已交付，`faf3a44` / `d03366e` 已推送，跨平台CI全部成功）**：所有者要求参考飞书多维表格，已选择先完成本地工作流。
网格占主区，内联/IME/连续录入、矩形完整 TSV、整批校验/预览/一次撤销；保存网格/看板/卡片视图，字段显隐/顺序/宽度/冻结/行高，
类型化筛选、多排序和分页前分组；新增日期/URL/单选/多选/对象字段，选择项保留 UUID。引用/公式编辑保留定义，未因 F2+Enter 转为常量。
对象链接同项目既有记录/文件/快照/分析/模拟/工作流，读取和来源检查不执行任务；文件明确送 Viewer 并保持表格选择，
CSV 预览逐列类型/单位、SHA 固定导入、当前视图导出。新格式 14 的字段选项/视图复用现有事务和撤销，旧 13 不自动升级。
多实例、旧回调、草稿、桥重连和最终 Viewer 消费均校验来源；PET 格式门禁已兼容 13/14，真实证据副本两格式离线通过。
首轮桌面 66/70 的可见记录同步、完整回归旧夹具及根叶筛选保留问题已修。完整 Python **2853 passed/24 skipped/2 deselected**，原生 **1444/1444、零跳过**，新增必跑 **77/77**；
相关三 Python 版本各127 passed，安装包冒烟通过。布尔修改/已存视图各1次点击，矩形粘贴2次+快捷键；固定起点与实际结果、提交 CI 见[验收](runtime-validation.md)。
首轮CI完整Python/三平台表格测试通过；独立PET例旧版本期望已修，Wayland退出线程已改为唤醒+join后释放，12项确定性线程测试通过；历史崩溃无栈，未冒称已证明同一根因。
修正提交Runtime **8/8**、桌面 **5/5**、文档部署与密钥扫描均完成成功；五Python矩阵新表36/36，三Linux独立PET例各7/7，诊断/打包/上传通过。
功能矩阵、官方参照、模块边界与剩余限制见[多维表格设计](design/multidimensional-tables.md)；协议增补见[发布契约](specs/project-tables-14.md)。
协作/权限/云分享、附件缩略图、填充柄/看板拖动及大表查询仍待后续，不宣称完整飞书功能对等；S2c/S3 待决定事项不因此解锁。


**2026-10-14 界面模块化（已交付，`10adde6` / `2e331ca` 已推送）**：11 个可独立构建的编辑模块，统一注册/导航/草稿协议，
共用项目、修订、选择、撤销与执行服务。新默认文件树、Viewer、分析图和表格直接可见，Python 在旁边以代码为主、输出在下。
目录展开只读有界元数据；程序载入/保存不运行，SHA 冲突保留草稿。节点主体给出打开/从模板新建/另存可编辑流程。
普通导航不遮挡 Viewer，旧隐藏标签保留原实例迁移；左右交换不重建区域，关闭/重置保护未保存编辑稿。
**减少点击是核心指标**：四个默认区域 0 次导航，Python、节点切回和左右交换各 1 次；同一起点传统菜单进入 Python 2 次、顶部 1 次。
真实事件测试覆盖中英文 900 像素逻辑宽度与 1/1.5/2 倍缩放，指标定义见[模块说明](desktop-modules.md)。
完整 Python **2812 passed、24 skipped、2 deselected**；完整原生 **1367/1367、零跳过**，新增必跑检查 **70/70**。
Windows 换行/路径夹具修正经独立复核；`2e331ca` 的 Runtime **8/8**、桌面 **5/5**、文档与密钥扫描全部成功，
Linux 原生 1367、macOS CPU 873 / Metal 200、Windows CPU 831 均通过且无跳过；完整实际结果与首轮失败见[验收](runtime-validation.md)。
富对象缩略图/专用单元格、批量粘贴、完整 IDE、二进制热插拔、每工作模式布局仍未完成；[产品约定](design/project-workbench.md#2026-10-14所有者补充的界面要求)
将这些同本轮基础模块交付区分。项目格式仍为 13，桌面桥协议 1 增补目录/程序文件接口，不改变模型/网络/运行权限。

**2026-10-14 PET 全流程 / E1d（已交付，真实软件全流程通过）**：
专项 `pet-study/1` 复用格式 13 的持久工作流、模拟、快照和分析运行；冻结协议与 Runtime 后明确启动，
完成建模、逐渐压密并释放到 1 atm、继承前一状态的降温、目标温度模量及链/O₂ 质心 MSD、分析和诊断归档。
O₂ 采用独立 IFF2021 12–6 数值与明确单位换算，不作为已验证的 PET/O₂ 阻隔模型；失败拟合保留观测和原因。
关闭/超时停止跟踪并保留已接受任务，明确恢复接续，成功阶段不重跑。`write_data` 的六位系数表示差异被识别，
下游从首个冻结模型恢复完整精度的 54 类参数。E1d full/real 结构、真实键、盒子与实际轨迹帧沿用 payload/2 和原生 GPU。
本机完整 Python **2782 passed、24 skipped**、最终协议/后端/dispatcher 三 Python 版本各 **97 passed**、3.11/3.14 相关各 **195 passed**、最后来源 guard 各 **4 passed**，
原生 **1318/1318、无跳过**；修正 O₂ 热态后从建模重新执行 **11 段真实 MD 全部成功**（4883.98 秒），每段 126 帧。
模量/O₂ 扩散拟合成功，Tg 未解析并归档观测/拒绝原因；搬迁与再次离线重开通过，独立 COM、密度、输入交接核对一致。
代码 `6aca8f8` 和 `20cc2f7` 已推送 main；后者桌面 **5/5**、Runtime **8/8**、文档和密钥扫描全部成功，实际结果见[验收](runtime-validation.md)。
代码与使用见[全流程例](../examples/pet_study/README.md)、[桌面指南](lammps-desktop.md)、[结构契约](specs/lammps-structure-1.md)。
纯 PET/O₂ 的短链有限时间软件验证不替代弹性体、酒液、长期变形、溶解度/渗透率或收敛物性的验证。

轨迹索引补正：首个代码头 Runtime 的 Windows 文件同 tick 改写反例失败，现以完整 raw SHA 复核索引和缓存，清除旧错误指纹。
三 Python 版本各 76 项、完整 Python 2782 项与桌面相关 11/11 通过；前代码头桌面 5/5 结束后才推送 `20cc2f7`。
补正后 Windows 两版本各 **2297 passed**，读取和节点测试实际执行，无延时或跳过规避。

**2026-10-12 项目方案落实**：所有者提供 PET 基弹性体研发与材料数据能力建设第 6 版方案，要求后续 STK 支持落地。
已读取 DOCX 正文及表格，形成[PET 材料数据闭环路线](design/pet-materials-data-loop.md)：以原始证据、材料/批次/样品状态、
处理/复核、候选决定和反馈为主线；八个验收节点衔接 E1 桌面 → 厂内基线 → 数据加工鉴别 → 可信证据 → PET 数据集评价 →
受控自主训练 → 多尺度实测回流 → 恢复移交。按依赖并行，多尺度/材料验证不等待自主训练；业务字典与部署设计可并行，企业内部数据接入以前必须验收厂内边界。
项目要求全部问题、聊天和派生查询留在厂内，公开标注也不豁免；现有 S1 数据准入与 S2 不准备/不开始运行的规则
尚不能覆盖该项目的完整要求，后续需要部署约束及版本化训练授权工具。本次为设计交付，未更改端点、网络、运行权限或项目格式。
方案的一年阶段与 2027 年底验收为项目目标，起算日、材料指标、预算和量化门槛待实际任务落实；不当作软件工期或已验证成果。
现有纯 PET、E1c 拟合与 S3a 合成曲线只是可复用基础，不代表 PET 基弹性体、酒液接触或客户材料预测已经验收。
路线文档 `b5fc3b7` 已推送；本地链接/格式与 gitleaks 检查通过，Runtime 8/8、密钥扫描与文档站均已结束通过，
实际证据见[验收记录](runtime-validation.md)。

**2026-10-13 开始实施，节点 1**：原生“材料仿真”支持 MuFerro/LAMMPS 导入、指定主脚本、准备、日志、收集及离线热力学查看；
批次按引擎过滤/冻结，切换清空待选成员；两种资源选项在编辑器会话内分别保留，历史运行按冻结引擎操作。
固定 Python dispatcher 校验项目/修订/引擎，保留旧 MuFerro API；文件选择和旧回调绑定打开句柄与界面代次，单成员操作也核对当前成员。
[字典草案](design/pet-data-dictionary.md)与[离线合成例](../examples/pet_data/README.md)实际用格式 13 的普通表/引用/快照，
9 张业务表、32 条记录、61 个引用、20 项冻结文件；缺测/失败为 None，不冒充 PET 实测或训练数据。
[厂内调用清单](design/inplant-execution-baseline.md)明确当前路径和未审定项；节点 2 才实施厂内强制边界，真实内部数据尚不接入。
使用与实际审查/测试/CI 见[桌面指南](lammps-desktop.md)与[验收](runtime-validation.md)。E1d/E2/E3、节点 2–8 与其他待决定事项仍按依赖推进。
本机完整 Python **2598 passed、24 skipped**，最后 runner guard 定向 **28 passed**；最终原生 **1309/1309、无跳过**，
真实 LAMMPS 原生 **2/2**，离线字典例三 Python 版本各 **7/7**；当前提交 CI 在验收记录中逐项补记。
代码 `4f54d78` 已推送 main，Runtime **8/8**、桌面 **5/5**、文档与密钥扫描均已完成成功。

所有者提出 STK 的后续方向：在 STK 中部署材料计算与数据分析智能体；与学校课题组合作，以联邦学习训练思劲的材料机器学习模型
（数据留在课题组）；文献检索、校内下载、统一知识库与 RAG；利用课题组资源复现文章中的模拟以评估文章质量；在客户本地交付并持续迁移学习；
客户端需支持节点间通信、内置智能体 harness、默认第三方 API 与一键本地部署模型、外网开关与按能力切换模型。
方案见[思劲平台方向](design/sijin-platform-2026-10.md)（建议分期 S1 模型接入与本地部署 → S2 智能体 → S3 数据集与迁移学习 →
S4 联邦学习 → S5 文献与知识库 → S6 复现验证 → S7 本地交付）。所有者 2026-10-08 答复：按 S1 → S7；联邦学习框架与节点通信先评估
（[联邦学习框架评估](design/fl-framework-evaluation-2026-10.md)、[节点跨校园网组网评估](design/node-networking-evaluation-2026-10.md)；
第二轮已定 Flower 作算法库、先做内网穿透，见下）；付费全文只留在本地（第二轮改为不跨机构分享、只“借阅”，见下）；数据默认不外发，人工标注为公开才可外发；思劲尚无材料预测模型，计划训练铁电与锂电池两个。
- **S1 模型接入（[设计](design/model-gateway.md)）**：**S1a（已交付）** 格式 12 数据标注、端点登记与密钥、网络设置、OpenAI 兼容适配器、发送前检查（网络设置与数据边界）；
  **S1b（已交付）** 桌面“公开数据”、AI 助手选择端点与模型、模型与网络设置、不能发送的原因；
  **S1c（已交付）** 本机一键部署：硬件探测与推荐、随 STK 发布的模型目录（14 项，Qwen 为默认）、llama.cpp 运行时与权重的可续传下载和哈希核对、
  离线导入、在回环地址启动并自动登记为本机端点（每次启动一个会话密钥）、自动启动与遗留进程回收、桌面“本机模型”；vLLM 只评估。
  **S1d（已交付）** 能力分档与自动切换：`suan/models/routing.py` 与 `models.route`、端点可声明档位、AI 助手默认“自动”（显示所选模型与理由，
  需要时先启动本机模型，确定没有发出时改问另一个端点上的候选）；连接阶段失败记为确定失败。限制见设计“S1d 已知限制”。
- **所有者第二轮决定（2026-10-08）**：Flower 作算法库；STK 与 Web 框架升到 Python ≥ 3.11；训练节点先只支持 Linux；首批三个课题组（北京、珠海、聊城）；
  学校不能开端口，先做内网穿透（参考 RustDesk、ZeroTier）；文献存在课题组的 Linux 服务器、直连（以后做）；中心服务与中继放在思劲服务器；
  不跨机构分享，只“借阅”；新增共享对话、作图与页面并可语音、文字交流。四份评估待所有者决定：
  [内网穿透](design/nat-traversal-evaluation-2026-10.md)、[共享会话](design/live-share-evaluation-2026-10.md)、
  [文献借阅](design/literature-lending-evaluation-2026-10.md)、[Python 3.11 与 Flower](design/python311-flower-upgrade-2026-10.md)。
- **所有者第三轮决定（2026-10-09，[方案](design/sijin-platform-2026-10.md)“所有者决定（第三轮）”）**：Flower 单独环境、hub 不装；连接层用 WebRTC/ICE
  （思劲服务器做信令、STUN、TURN，打通后直连），不做前置实测、边用边测；文献直连失败时用端到端加密、不落盘的中继兜底；共享会话先文字与结构化共享；
  私有数据单次授权；借阅先“陪读”、试点只用开放获取；Python 最低 3.11、默认 3.12；首批不启用 SecAgg+；桌面按 GPL 发布、对外试点前请律师。
  **Python 3.11（已交付，2026-10-09）**：最低 3.11、推荐 3.12；Runtime CI 测 3.11、3.12、3.14，Windows 客户端测 3.11、3.12；去掉 tomli 回退；
  Python 3.13 起符号链接环不再在 `resolve()` 时报错，`LocalFiles.open` 改为把 ELOOP 当作文件不存在。S1d 随后交付（见上）。**S1 全部完成。**
- **S2 智能体 harness（[设计](design/agent-harness.md)，2026-10-09，所有者已作答；S2a、S2b 已交付，真实模型人工验收未做）**：循环在 Python 后台服务，格式 13 加会话、哈希链事件与对象登记三张表；
  8 个工具（只读、记录、问模型、草案），改项目只经草案与人的批准，智能体不准备也不开始运行；规划轮 v1 只用本机或机构内模型，子请求按会话来源集合检查数据边界；
  分 S2a（记录、规划轮、只读工具）与 S2b（扫描提议与结果分析、草案批准、桌面、验收）。
  **S2a（已交付，2026-10-09）**：格式 13（会话、事件、对象三张表，`project_labels` 加“结构公开”）、`suan/agent/`（级别表覆盖全部脚本操作、
  对话重组与严格解析、三个工具 `project_outline`/`capture_rows`/`table_statistics`、循环与上限、审计）、`project.agent.*` 与脚本；
  只能从脚本或 Python 控制台使用。
  **S2b-1（已交付，2026-10-10）**：其余五个工具（扫描提议与提问经请求执行器各发一次子请求，按会话来源决定能否去外部端点）、
  `awaiting_user`/`observed`、桌面专用的签名批准 `project.agent.decide`、会话用量、MuFerro 验收测试。
  **S2b-2（已交付，2026-10-10）**：桌面 AI 助手“智能体（多步）”用途（规划模型、会话、步骤时间线、等待卡片、继续与取消、记录与核对、用量）、
  修改检查页经会话应用或丢弃（`decide`）与来源、工作台“需要关注”、数据页“私有 / 结构公开 / 公开”。
  **下一步**：真实本机模型的人工验收（[工作台清单](workbench-acceptance.md)“AI 智能体（多步）”）；之后按 S1 → S7 进入 S3（数据集与迁移学习），
  S2c（外部规划、智能体准备运行）视所有者决定。限制见设计“S2a、S2b-1 已知限制”。
- **多尺度计算引擎（[方案](design/multiscale-engines.md)，2026-10-10，所有者已决定；E0a、E0b、E1a、E1b 写出器与 PET 本机建模、E1c 已交付）**：为思劲的 PET 基材料设计项目，
  在相场（MuPRO）之外加入开源的 LAMMPS（分子动力学）与 ABACUS（第一性原理），做成可加载的模块，体现多尺度。顺序：
  E0 计算引擎接口（将执行一侧从 MuFerro 分离）与模块管理（可选模块，先检测已有软件，没有才用 micromamba 从 conda-forge 安装）→
  E1 LAMMPS 与分子建模模块（mBuild、foyer、Packmol 等；也可导入外部建好的模型；密度与玻璃化转变温度、模量、气体扩散）→
  E2 ABACUS（电子结构与相互作用能）→ E3 串联。
  **E0a（已交付）** 引擎模板接口与按模板分派；**E0b（已交付）** 模块管理（`suan/modules/`、`modules.*`、工作台“计算模块”）；
  **E1a（已交付，2026-10-10）** LAMMPS 引擎：计算端 `python -m suan.lammps`、`stk.lammps` 导入/准备/收集、工作流模板 `lammps/1`、
  结果表；LAMMPS 模块固定为与 MPICH 链接的版本。PET 建模链路（mBuild + foyer OPLS-AA + Packmol + GMSO → LAMMPS）已在本机走通（尚未写入 STK）。
  **E1b 独立写出器（已交付，2026-10-11）**：`suan.lammps.write_data` 从已分配参数的 ParmEd 结构写 full/real 数据，不分配或改写电荷；
  正交/三斜 540 原子 PET 与 GMSO 逐项对照并用真实 LAMMPS 核对势能与晶胞。发现 GMSO 0.17.0 三斜 data 头误写 dump 外包围边界，STK 按正确 data 约定输出。
  **E1c（已交付，2026-10-11，`6927e27`）**：三套 full/real 脚本、明确单位/窗口的 Tg、模量与扩散拟合，四个增量图节点、三个预设与技能；
  旧参数表读取/准备不迁移，旧冻结计划与既有技能哈希不变。合成已知曲线和真实 108 原子氩的运行/分析路径通过；
  不声称短轨迹已收敛，不自动判定平衡或扩散区，无 Tg 置信区间/跨行自动汇总。见[分析指南](lammps-analysis.md)与[验收](runtime-validation.md)。
  **E1c 审查修正（2026-10-11，`c17bb4b`）**：拒绝会覆盖实测值的重复/规范化重名表头，表格源实现版本升为 2 以隔离旧缓存；
  补齐三平台 CI 暴露的预设数量断言与中英文新表单基准，既有八套表单及六个技能哈希不变。
  本机完整 pytest 2483 passed、24 skipped，完整 Linux CTest 1289/1289 无跳过；修正提交的桌面 5/5、Runtime 8/8、密钥扫描与文档 CI 通过。
  **E1c 多温度来源复查（2026-10-11，`be9bdd7`）**：`density_series` 的全部日志文本摘要随 Tg 结果与诊断保存，
  所有热力学段统一拒绝重复列名；日志源实现版本升为 2。八温度合成日志汇总/拟合与真实氩三路径通过，
  完整 pytest 2485 passed、24 skipped；最终桌面 CI 5/5、Runtime 8/8、密钥扫描与文档通过，实际测试数与限制见验收记录。
  **E1b PET 建模（2026-10-12，`fbcd9f4`）**：所有者授权按文献判断并直接实施，采用完整 PET OPLS-AA/MK 2022 适配参数；
  芳环 C −0.115 e 与完整电荷/LJ 配套，末端醇氧舍入修正 −0.566→−0.565 e 明确记录。COOH/OH 默认六条四聚体为 546 原子，旧 540 夹具不改写。
  本机 `pet-model/1` 模板、`stk.lammps.create_pet_workflow` 参数表助手、隔离分子模块 worker；八项产物含完整参数与摘要，冻结后显式导入 LAMMPS。
  新增周期平面 improper→CVFF，原子顺序不变；严格拒绝不完善 Packmol 输出与周期自/互重叠，不发布部分案例，不覆盖已有目录，支持取消子进程树。
  单链长度 2–20、总量≤50000 原子是资源边界；DP2/DP4 独立势能验收及 DP8/DP20 初始构象/填充通过，不保证高分子构象或平衡成功。
  PET 纯体系未含气体参数；Tg/模量/扩散的收敛材料性质尚未验证。来源、适配差异与操作见[模型](pet-model.md)、[示例](../examples/pet_model/README.md)。
  代码 `fbcd9f4` 已推送，Runtime 8/8、桌面 5/5、密钥扫描与文档已全部结束通过；实际测试数见[验收记录](runtime-validation.md)。
  **桌面入口（2026-10-13，数据闭环节点 1）**：内置 MuFerro/LAMMPS 的导入/准备/收集/批次与离线热力学查看，见[指南](lammps-desktop.md)。
  **2026-10-14 交付**：E1d 原子与键/轨迹、PET 专项状态交接及 IFF2021 O₂ 示踪协议已实现，真实全阶段软件验收与 CI 通过，见本文开头。
  **下一步**：长链/独立构型/热历史、平稳性/分块不确定度与气体模型收敛；之后 E2/E3。厂内执行基线仍按节点 2 的独立边界推进。
- **S3 材料预测模型（[方案](design/materials-models-s3.md)，2026-10-10，所有者已决定；S3a 已交付）**：先做最简单的端到端测试——
  铁电预测 P–E 电滞回线，锂电池预测容量衰减曲线（SOH，读出循环寿命）；还没有真实数据（要与学校合作者合作后才有），
  先用标注为合成的生成器跑通“数据集 → 训练 → 评估 → 登记 → 预测”；PyTorch CPU 作可选依赖，训练在本机后台任务中运行。
  **S3a（已交付，2026-10-10）**：`suan/materials/` 与 `materials.*`、脚本 `stk.materials`。**下一步**：把 `stk.dataset/1` 的两个格式交给合作者讨论；
  迁移学习（在已登记模型上微调、与基模型对比、过门槛才替换）；桌面显示数据卡、训练进度与回线对比；确认 MuPRO 能否做电场扫描以产生相场回线。

## 2026-10-07：体验包（ADE 参考第 2 组）

所有者确认在 P3 W4 之后做体验包并要求直接开发，范围与判定见[体验包](design/ux-package-2026-10.md)；顺序 U1 → U4 → U2 → U3，归档暂不做。

- **U1 需要处理（已交付）**：`suan/project/attention.py` 只读汇总工作流运行、分析运行（不含工作流运行产生的）、仿真运行、
  待审草案与 AI 请求，按“需要处理 / 运行中 / 已完成”分组、失败优先；后台服务 `project.attention.list/viewed`（“已查看”记在服务状态目录，
  不改项目）、`stk.project.attention()`；工作台顶部“需要关注”（打开/已看/全部标为已看，打开即导航）与状态栏“需要处理 N”。
- **U4 工作流记住视图（已交付）**：工作流编辑器按（项目, 工作流）记住画布中心与缩放（`AnalysisGraphCanvas::look_at/center`，
  与窗口大小和界面缩放无关）、所选步骤与显示的运行，切换回来时恢复；最近 50 份与上次显示的工作流随布局保存（`save_state`/`load_state`），
  新打开的编辑器先显示上次那份。
- **U2 用量可见（已交付）**：`Requests.usage()`/`project.requests.usage`/`stk.project.requests.usage()` 只读合计已完成回复的
  服务商 token 回执（总计、按模型、无回执的完成数）；AI 助手配置区显示“本项目已用”（回复完成后重读，读取不占用对话的忙碌状态），
  发送按钮注明请求冻结的模型；不估算金额。
- **U3 项目内搜索（已交付）**：`suan/project/search.py` 只读、不区分大小写地查找表格/字段名称、单元格文字、工作流与分析名称、
  文件名与路径、草案标题与对话消息（每类最多 50 项）；`project.search`、`stk.project.search()`；工作台“搜索项目”按类别列出结果，
  打开时导航到所在位置（参数表与文件页选中该行）。
- **体验包四项均已交付**。所有者 2026-10-07 决定的顺序：先写归档方案，再做 MuFerro 的按行工作流运行，再做 AI 批量模拟闭环。
  归档方案见[项目对象归档](design/project-archive.md)（推荐独立的归档记录、项目格式 11，**待所有者确认后实现**）。
- **W5 MuFerro 按行工作流运行**（[工作流按行运行 · W5](design/workflow-runs.md#w5muferro-按行运行2026-10-07所有者决定实现)）：
  **W5a 服务与脚本（已交付）**：准备时冻结 Runtime 连接、端点指纹与运行选项及每行案例字段；执行器提交不阻塞（各行同时排队，
  完成的行收集并继续下游分析）、行在冻结后被改则 `row_changed`、每次尝试一个任务、进度记录与停止跟踪后的接管、取消传到 Runtime、
  最终状态作为分析输入；`stk.project.workflow_runs.prepare(connection=, options=)`。**W5b 桌面运行区（已交付）**：含 MuFerro 步骤时运行区显示运行环境与运行方式/资源
（与仿真批次共用 `SimulationTarget`），按钮注明 Runtime；任务格显示远程阶段，选中行列出仿真运行与 Runtime 任务；重算过期行沿用原运行的环境；
`STK_WORKFLOW_POLL_SECONDS` 调整读取间隔。**W5 完成**。
- **P2 AI 批量模拟闭环**（方案：[AI 批量模拟闭环](design/ai-batch-loop.md)，按推荐执行）：**L1 AI 扫描提议（已交付）**——新的提问用途
  `stk.parameter-sweep/1`，回复为基准行与扫描轴，转换时由手工扫描同样的 `plan_sweep` 展开为最多 100 个新行的草案（行 ID 由请求派生，已保存的草案以回复摘要核对、不重新编译）；
  AI 助手“提议参数扫描（新增行）”。**L2 运行新增的行（已交付）**：应用后“用工作流运行新增的 N 行”打开使用该表的工作流并只勾选新行（工作流摘要带 `table_id`）。
  **L3 结果回到对话（已交付）**：MuFerro 运行结束后“就这 N 行的结果提问”捕获结果行为上下文并打开 AI 助手。**P2 闭环三段均已交付**；
  归档方案已由所有者确认（2026-10-08）。
- **归档（[项目对象归档](design/project-archive.md)，所有者 2026-10-08 确认：独立记录/格式 11、归档即冻结（不能修改、可照原样使用，修改须恢复或复制）、搜索包含并标注、九类含草案与上下文）**：
  **A1a（已交付）**：格式 11 的 `project_archive`（只追加、不带哈希链）、`suan/project/archive.py`（归档/恢复、进行中的对象拒绝、`include_runs`、
  旧格式下读取为空）、`project.archive.set/list` 与 `project.archive.changed`、`stk.project.archive/unarchive/archived`。
  **A1b（已交付）**：八个列表方法的 `archived` 过滤（SQL 内过滤，分页与总数正确）、专门操作上的只读检查（`conflict`）、“需要关注”排除、搜索标注。
  **A2a（已交付）**：桌面 `ProjectArchive` 与共用控件；工作流编辑器的列表与运行列表默认不列已归档、“显示已归档（N）”、
  已归档工作流不能编辑、归档工作流连带其未在运行的运行（恢复同样）；顺带修复：同一修订内切换到另一个工作流时，原来不会读取它的运行列表。
  **A2b（已交付）**：保存的分析与分析运行（分析编辑器）、AI 问答历史与上下文（AI 助手、项目页“讨论”）、保存的草案（审阅页）、
  仿真运行（项目页运行区）、仿真批次（界面按归档 ID 过滤）均有归档/恢复与切换。
  **A3（已交付）**：Home“需要关注”的已看项可直接“归档”（“需要关注”在归档集合变化时重读）。
  **冻结规则调整（所有者澄清，已交付）**：归档 = 不能修改、可照原样使用。已归档的工作流与分析可以运行（含作为工作流步骤，撤回 `archived_reference`），
  批次可以照原设置准备和提交，上下文可以继续提问，问题的回复可以生成草案；原记录不重试/发送/提交，草案不直接应用或放弃；
  修改走恢复或复制（新增“复制为新工作流”，分析“保存为新分析”，草案“以当前修订另起草案并检查”）。**归档 A1–A3 完成**；限制见方案“已知限制”。
  下一步由所有者决定。

## 2026-10-06：独立使用者审视

两位不了解设计意图的审阅者分别检查界面截图和文档/CLI，结论见[审视记录](design/user-review-2026-10-06.md)：
功能模块齐全且安全，但新用户找不到起点、主流程（建扫描 → 运行 → 看结果）分散在多个编辑器与 Python 中，
内部细节外露，且没有可离线试跑的运行路径；带符号标量体的范围显示存在误导。
所有者已确认工作流提案先复用格式 6 草案，并决定先完成审视提出的可用性开发包，再做提案。进度：

1. 带符号标量体自动范围显示与以 0 为中心的发散色图：**已交付**（`96152bf`）。
2. 启动即分步引导的工作台：**已交付**（`1d1c338`）。
3. 补齐主流程：参数扫描生成器（`ca8a8b3`，见[参数扫描](project-sweeps.md)）、文件/目录“浏览…”按钮（`b1badce`）、
   含运行环境选择的“运行所选行”（`ed5bb29`，见[仿真批次](simulation-batches.md)）、分析一键“运行并显示”
   （见[分析运行](project-analysis-runs.md#准备执行与查看)）**已交付**。冻结/核验等细节的折叠并入第 4 项。
4. 统一中英文术语（[术语表](design/glossary.md)）、界面内设置 API key、默认收起内部细节（行号、本地化公式错误、技术详情面板）
   与一行说明（`hint()`，完整说明在悬停提示）**已交付**。其余页面的 ID 显示（讨论、请求列表、快照选择等）随后续改动逐步收起。
5. 可试跑路径 **已交付**：工作台“创建示例项目”与 `suan demo`（合成求解器与示例输出）、终端/Jupyter 可用的无头 `stk`、
   [Linux 快速上手](quickstart-linux.md)、文档站改为 STK。真实 MuFerro 运行仍需 Linux 运行环境与许可。

可用性开发包五项均已交付。

## 2026-10-06：P3 工作流编辑（进行中）

所有者决定 AI 批量模拟闭环后续由团队成员完成，当前先做 P3 工作流编辑。按风险拆成可单独审查的增量：

- **W1a 候选图模型（已交付）**：保存分析草稿改为在已保存图的副本上编辑（首次改动时复制，未触碰的 JSON 原样保留，
  改回原样即丢弃副本）：单输入连线、多输入有序列表、新增节点（按类型名生成不冲突的 ID）、删除节点（级联删除指向它的连线与列表项、
  引用它的图输出及请求输出、位置；图参数与其他节点的 `$param` 保留）、节点参数、`ui.positions` 与公开图输出；
  逐项列出改动供检查。只改位置不影响求值，可不经校验保存；其他图改动仍须当前候选 `graph.validate` 通过。
  后端保存不校验图（分析文档是草稿），准备运行时再次校验。
- **W1b 候选视图与面板（已交付）**：画布与“节点”“连线”面板显示候选图（改动节点描边）；新增/删除节点、多输入有序列表、
  公开/撤回图输出、改动清单；首次增删节点时固定现有节点位置；校验按钮在“连线”与“编辑图结构”中共用。
- **W1c 节点参数编辑（已交付）**：所选节点的参数按目录定义生成表单（复用属性面板表单），每次修改写入候选图；
  `$param` 绑定只读；可恢复默认；客户端 `validate_node_params` 即时提示缺失或不合规参数。
- **W2 画布交互（已交付）**：拖动节点改位置（松开时一次写入）、从输出端口拖到输入端口连线、Delete 删除所选节点；
  候选更新时保留视图缩放与平移；只改位置不使已通过的校验失效。
- **W3 项目流程层与子图导航（方案已确认 2026-10-07）**：见[项目工作流与子图导航](design/project-workflows.md)——
  新实验文档 `stk.workflow/1` 存为受管表格（不升级项目格式），步骤按 UUID 引用参数表、`muferro/1` 仿真、输入快照与保存分析，
  分析步骤的边界取自保存分析的文件绑定、图参数与图输出，编辑时跟随当前修订、执行时冻结；两层导航与面包屑。
  按 W3a 存储与校验、W3b 只读画布与导航、W3c 编辑实现。
  - **W3a 存储与校验（已交付）**：`stk.project.workflows` 与后台服务 `project.workflows.create/update/get/list/validate`，
    受管表格与保存分析共用 `suan/project/managed.py`；校验逐步解析引用、端口类型、`$field` 绑定与环，问题定位到步骤/路径；
    示例项目新增“温度扫描”工作流。用户说明见[项目工作流（实验）](project-workflows.md)。
  - **W3b 只读画布与导航（已交付）**：原生“工作流”编辑器（复用分析图画布，`workflow_graph_view` 把步骤与校验摘要转成节点视图），
    工作台“其他”入口；分析步骤在同一区域的分析图标签中打开（`Editor::navigate`、`AppShell::open_in_area_later`），
    画布上方面包屑返回原标签；另一分析有未保存修改时拒绝进入；工作台“保存的分析”页面 ID 改为 `analyses`。
  - **W3c-1 编辑模型（已交付）**：`project.workflows.choices`（可引用对象）、C++ `WorkflowDraft`（与 Python 形状规则一致的候选副本，
    增删步骤、连线、先完成、参数、标签、位置与名称；位置与名称不使候选检查失效）、`ProjectWorkflows` 的创建/保存（丢失回复时标记不确定，
    重读前不再保存）与独立的候选检查槽。草稿模型与分析草稿分开，画布与手势复用。
  - **W3c-2 编辑界面（已交付）**：工作流编辑器的“编辑工作流”面板（改名、按对象添加步骤、改动清单、候选检查、保存/放弃、新建/删除）、
    所选步骤编辑（名称、输入来源、先完成、参数的分析值/固定值/字段）、画布拖动/拖线（类型检查、拖到（等待）设先后）与 Delete；
    候选检查前用上次检查或已保存的摘要显示；其他项目编辑只移动修订时保留修改（`WorkflowDraft::rebase`）。
- **W4 按行运行、过期传播与按范围重算**（方案草案：[工作流按行运行](design/workflow-runs.md)，待所有者确认）：工作流运行记录需要项目格式 10，分析运行需要按行冻结参数覆盖值；
  示例合成求解器注册为本机模板（所有者已确认），用于离线验收。**W4a-1 已交付**：格式 10（`workflow_run_plans`/`workflow_run_events`）、
  `WorkflowRuns.prepare/get/list` 与尝试记录（只接受最新尝试、哈希链）、本机模板 `demo-synthetic/1`（参数按字段绑定）、
  分析运行的 `parameter_overrides`。**W4a-2 已交付**：后台执行器（逐行、登记输出为快照、带按行参数的分析运行、分析被改则任务失败、
  失败只停该行、再次开始只重做未成功任务、取消、恢复）、`project.workflow_runs.*` 与 `stk.project.workflow_runs`、示例工作流改为合成求解。
  **W4b 已交付**：工作流编辑器“运行”面板（勾选行、运行、行×步骤状态表、失败原因、打开该行分析运行、重试/取消/恢复、运行记录）。
  **W4c 已交付**：`project.workflow_runs.stale`（按行、按步骤比较当前定义：值改变带前后值、步骤/分析/模板/行/工作流变化与上游传播）、
  运行区的过期标记、原因与“重算过期的 N 行”（新运行，旧运行不变）。**P3 W4 完成**；下一步按所有者确认的顺序做体验包。并入 [ADE 参考](design/ade-references-2026-10.md) 第 1 组：
  步骤与“尝试”分离、提交不阻塞并显示阶段与重试、说明运行看到的快照。
- **W4 之后：体验包**（所有者已确认，进度见本文开头“体验包”）：统一的“需要处理”面板（失败最醒目）、用量可见、项目内搜索、工作流记住布局；归档暂不做。
- AI 相关做法（对话决策卡、草案批注、来源标记、对话提炼技能）交由负责 AI 批量模拟闭环的同事一并考虑。

## 2026-10-05：围绕五类内容调整交付顺序

沿用讨论确认的五类内容：**项目、文件、技能、工作流、对话**。项目组织研究目标与对象关系，技能可跨项目复用；
运行是工作流的一次独立尝试，保存当时的输入、参数、定义版本、状态和结果，不能被当前编辑覆盖。
表格、节点图、3D 与文档预览是对象的视图；五类内容不直接等于五张 SQL 表。

当前优先顺序调整为：

1. **项目工作台与关联导航**：先交付项目级入口，复用已有对话、文件、分析定义和两类运行页面。
   本轮首版新增原生“工作台”，从文件菜单或已有项目/AI/分析图页头进入，显示当前项目并直接定位各页；
   项目管理与文件/仿真运行提供独立视图，分析入口明确进入保存定义或分析运行。
   复用活跃编辑器、保护未提交输入、旧项目回调失效，不执行计算或发送模型请求。
   这一步不改变默认布局，不包含文件/技能对话附件、跨对象 UUID 深链接或新会话容器；后续逐项接入。
2. **技能目录首版（已交付只读首版）**：实验契约 `stk.skill/1` 统一方法说明、
   输入/输出、参数、执行入口、版本和依赖，见[技能目录](skills.md)。首批三个内置技能包装已有可离线验证的图预设；
   以 `id@version` 与定义及图模板的内容哈希识别，锁文件防止同版本内容漂移。桥 `skills.list/get`、
   Python `stk.skills` 与 `suan skills catalog/show` 共用同一解析结果，查询不执行入口、不准备运行或调用模型。
   坏定义、未知版本、缺少可选模块均有结构化说明；离屏渲染等运行能力只声明不探测。
   已有 `suan/skills/` 说明包与 list/export 保持不变；节点目录不冒充技能体系。
   原生 **文件 → 技能** 与工作台“技能库”（无需项目）提供有界搜索、分页、契约详情与坏定义说明；
   旧桥缺少方法时显示不可用，桥重启或更换后清空重读，见[桌面指南](desktop.md#技能目录)。
   全局可复用技能与项目引用的固定版本分开：项目引用、版本固定、迁移与备份尚未实现，本轮不改数据库格式；
   从技能直接准备/运行、对话附件与用户技能目录也留待后续。
3. **工作流编辑与 AI 编排（继续开发）**：保存分析的单输入连线编辑首版已交付（见下文）；随后接入可审查的工作流提案，
   校验、保存、准备和明确执行保持分离。完整项目流程层、子图、多输入与技能封装分别验收。

导航首版验收重点：已有标签复用、未发送问题和无效分析参数原文保留、两个运行入口分开、文件表明确选择、
满标签不替换编辑器、跨窗口活动输入保护、隐藏标签及其他窗口的单元格及表/字段名称草稿阻止文件切表，以及关闭/重开项目、切换项目、销毁编辑器/窗口后的旧回调拒绝。
“从对话引用文件/技能 → 工作流 → 运行结果 → 返回对话”的完整链路仍是后续目标；只读技能库已在技能目录首版接入。
首版本机验收：重点交互 **61/61**、完整 Linux CTest **1114/1114** 通过，无失败、错误或跳过；
中英文宽/窄 GL/Vulkan 工作台截图已检查；`b2e5632` 的[桌面 CI](https://github.com/sijintech/stk/actions/runs/37289712961) **5/5**、
[Runtime CI](https://github.com/sijintech/stk/actions/runs/37289713009) **7/7** 任务全部成功。真机交互继续按平台清单验收。
Claude 与其他开发者接手见根目录 [handoff.md](../handoff.md)。

## 当前基线

- 桌面 D1 已交付：自有 C++ 桌面、Jobs、Viewer、Properties、Probe、日志与传输；继续复用
  Python 桥、Runtime、`suan.graph` 与原生 GPU 渲染器。
- `main` 已有不透明度曲线编辑器和 [macOS / Windows 快速编译启动脚本](../desktop/QUICKSTART.md)。
  用户已反馈两个平台均能打开窗口并看到 3D 渲染；这是基本启动验收，不包含全部交互、输入法或发布包验收。
- P1 存储基础已实现：`suan/project` 与 `suan project` 支持 SQLite 项目创建/重开、稳定 ID、
  类型化表格字面量、原子编辑批次、修订冲突检查和修改历史，见[项目存储指南](project.md)。
  本机桌面桥与 C++ 客户端已支持项目生命周期、快照、修改和历史；原生“项目表格”编辑器
  支持新建/打开、字段/记录添加、类型化单元格编辑、关闭重开和桥重启恢复，共享项目状态。
  通用表格支持横向滚动条、Shift + 滚轮及触控板横向滚动，保持表头排序、记录选择和列宽调整一致。
  横向滚动条额外占用布局高度，不挤掉请求显示的数据行；变宽后恢复原高度。
  项目表格已支持每个区域独立的文字搜索和错误筛选，过滤后排序/编辑仍绑定原记录 UUID；
  被隐藏的选择保留，需选择可见记录或清除筛选后编辑。捕获上下文已有只读单元格表及原始详情。
  Python `p.selection()` / `p.select(..., expected_revision=...)` 已可读取/明确设置共享表格和记录，
  核对项目句柄、修订及对象归属，保留正在输入的文字和已有草案；同项目跨表切换保留区域筛选。
  最近项目列表跨重启保存 20 个位置；显式打开并校验项目身份，移除历史不删除文件。
  已提供只读[修改预览](project-preview.md)：内存副本复用编辑/公式引擎，返回候选状态与稳定命令；
  原生“修改检查”展示对象/单元格差异、依赖值和全部候选公式错误，支持从单元格编辑器发起或输入 JSON 命令。
  明确应用通过原修订检查并进入普通撤销历史；修改草案、关闭/切换或桥重启废弃旧候选。
  Python 可通过 `stk.project.review` 将命令送入原生检查页。格式 6 已增加[草案保存与恢复](project-drafts.md)，
  保留稳定命令、原始修订和不可重放的应用回执；重开后主动载入并重新检查。
  格式 7 增加[显式上下文和讨论记录](project-contexts.md)，原生“讨论”页与 Python 共用选定范围捕获、
  手工消息和同修订草案来源；重开不执行任何操作。
  格式 8 增加[请求记录与本地执行生命周期](project-requests.md)，原生可查看、取消意图和打开保存的回复；
  Python 与桥共用创建/查询/取消。可注入执行器的单次发送权、跨进程锁、取消竞争和重启核对已有测试；
  阿里 Token Plan 的固定端点、环境凭据、显式准备/发送、完整文字保存和遗留执行核对已接入；
  Linux 已通过一次 `qwen3.7-plus` 真实账号调用：仅发送合成的 `temperature=300 K` 单元格，
  经实际 NDJSON 桥返回 `300 K`，完成 SQLite 保存与重开核对，未改变参数或历史。
  macOS/Windows 原生界面的真实模型调用仍待验收；此结果不代表模型整体质量或套餐适用资格确认。
  原生 **AI 工作区** 首版已接入项目页头与文件菜单：在同一页捕获选中记录、准备问题（只保存）、
  核对后明确发送，并查看已保存问答及换行的普通文字回复。运行中/不确定记录按约 1 秒间隔读取本地状态，
  最多跟踪 90 秒；出错或到期暂停，明确刷新可恢复，不查询提供方或重发。
  未保存输入按项目留在编辑器内存中，该增量沿用格式 8；该轮重点测试 41/41、Linux 完整 CTest 602/602 通过，
  均无跳过，八张 AI 中英文宽/窄 GL/Vulkan 截图已检查。`852b343` 的
  [桌面 CI](https://github.com/sijintech/stk/actions/runs/36667294145) 5/5 与
  [Runtime CI](https://github.com/sijintech/stk/actions/runs/36667294040) 7/7 任务全部通过；
  原生 Linux 602、macOS CPU 369 / Metal 73、Windows CPU 329 项均无失败或跳过。
  流式回复已接入临时内存快照：仅完整校验的回复保存入库，取消立即隐藏片段，旧桥回退正式状态读取；
  传输与执行器回归 208 项、原生重点回归 14 项通过；`6123300` 的桌面 5/5 与 Runtime 7/7 CI 任务全部通过。
  参数建议已接入版本化结构化回复、显式保存草案及受保护的原生检查入口，仅支持捕获范围内的普通标量值。
  保存、预览、应用相互独立；草案与来源原子记录，完成回执不会因撤销而重新打开，见[参数提案指南](project-parameter-edits.md)。
  本机参数建议重点原生回归 29/29、完整 CTest 633/633 与 Python 1838 项通过；`bf9ccd1` 的桌面 5/5、Runtime 7/7 CI 任务全部通过。
  AI 页已接入多行、多字段选择与数值预览，使用固定修订，超限或旧修订不能捕获；保存成功才关闭，失败保留范围。
  选择器打开期间暂停准备问题，避免把尚未捕获的预览误认为保存上下文；测试验收另按对应提交记录。
  原生视图菜单已接入聚焦准备、聚焦分析和恢复分栏，复用原编辑器并保留草稿；Python 可激活编辑器或恢复分栏。
  这一步不替换分割树，不是独立保存的工作区模式；远端查询、通用工具调用和默认以 AI 为主页的完整工作模式仍待实现。
  CSV/TSV 小型参数表可按明确类型原子导入、一次撤销；可导出当前计算值，见[CSV 交换](project-csv.md)。
  格式 2 已增加稳定引用、受约束的标量公式、单位校验、依赖缓存和错误定位，桌面可编辑公式与变量绑定。
  格式 3 增加项目级持久撤销/重做，桌面提供表格/字段改名和对象删除；恢复保留 UUID 与顺序。
  已提供数据库备份及格式 1–8 → 9 的显式备份升级；完整 AI 模拟工作流、多层节点与文档预览仍待开发。
  文件索引首版复用普通表格、稳定 ID 与撤销，提供登记/刷新、项目相对路径和外部位置、系统打开与 VSCode 入口；
  选中文件可直接打开原生 Viewer，科学场文件保留文件名并选择已有分析预设，
  见[项目文件指南](project-files.md)。格式 4 支持选定文件的不可变输入副本、清单和 SHA-256 校验，
  见[输入快照](project-snapshots.md)；格式 5 将参数行、输入版本、完整执行规格和任务 ID 持久关联；原生运行表格可查看冻结参数、
  显式提交/恢复、刷新和取消，见[运行记录](project-runs.md)。
  macOS/Windows 可先运行[离线工作台演示](../examples/project_scan/OFFLINE.md)，无需 Runtime，验证项目、公式、Python 布局和三维分析。
  用户真机复核步骤统一在[工作台验收清单](workbench-acceptance.md)，与 CI 能力范围分开记录。
  [MuFerro 单次仿真](simulation-muferro.md)已接入案例导入、参数生成输入、准备与结果收集的 Python API 和原生入口；
  真实 Linux 求解器的参数变更、重开、数值和三维输出已验证；原生按钮驱动的完整单次流程及离线重开也已通过。
  `763eb0b` 的 Linux/macOS/Windows 桌面 CI 及 Windows Python 3.10/3.12 工作流 CI 全部通过。
  Windows GPU、真机输入法和实际异机 SSH 仍按平台验收清单单独复核。
  通用输入生成、完整程序环境冻结与完整项目打包仍待实现。
  Runtime 已支持可选的 `input_hashes`，校验复制到任务目录的实际内容后才排队，旧请求幂等哈希保持不变。
- P0 测试稳定性修正：Windows 进程退出测试捕获状态查询期间的 `psutil.NoSuchProcess`；
  查看器阶段缓存测试先禁用邻帧预取，避免取消预取时 worker 重启、内存缓存丢失影响断言，
  随后重新启用预取验证换步。原有阶段缓存断言保留；本次修改不改变生产取消策略。
  跨平台完整通过状态仍须以对应提交的 CI/真机验收为准。
- 现有未合并 PR 不计入交付；功能状态以 `main` 与[验收记录](runtime-validation.md)为准。
- Linux GL/Vulkan 与 macOS Metal 的五十类工作台截图按中英文逐项检查，缺失、跳过或失败均使 CI 失败；
  渲染图片与 JUnit 随 CI artifact 保存，方便复核项目、Python、离线三维、文件、快照和运行界面。
  其中 AI 工作区宽/窄、临时流式回复及参数建议宽/窄已通过跨平台 CI；多行选择宽/窄及聚焦菜单按对应提交记录。
- Python 基础后端已接入：独立持久会话、显式多行/文件执行、项目操作 facade、输出环、异常与中断，
  以及带会话身份和超时的本机反向 UI 请求扩展。原生 Python 面板、多行输入与 UI 主线程布局执行器
  已接入；可查询/编辑当前项目、配置/恢复布局。Runtime 工作区、传输、任务与日志操作已接入统一 API，
  保留幂等键和 Hub 审核结果。Viewer 打开、预设参数、求值、图层与时间步控制已接入，
  扫描示例可从下载结果直接打开三维视图；`stk.graph` 已支持 JSON 图校验/求值、结果 blob 和原场探针。
  原生分析图只读检查已接入节点画布、端口/参数表、显式校验与当前/已显示配置比较；结果哈希确认后才关联回执，
  见[分析节点图指南](analysis-graphs.md)。分析定义已可作为普通项目记录保存、重开、改名和撤销；
  Python 与桥支持明确创建/替换、分页列表及纯 Viewer 配置捕获，见[分析文档](project-analyses.md)。
  保存文档独立显示，不冻结执行来源绑定或结果回执，不自动求值；节点仍使用文档内 ID，尚未转为独立项目记录。
  保存分析的提交参数和请求输出共用独立类型化草稿：精确保留整数、浮点数、缺省、`null` 与明确空输出，联合保存只增加一次修订和撤销；
  未保存输入、过期修订和无法确认的保存回复不会自动覆盖当前项目，图与历史运行保持各自保存的定义。
  格式 9 另行接入[分析执行记录](project-analysis-runs.md)：准备时冻结完整定义与快照文件映射，明确开始后经本机图 worker 求值，
  归档结果及 blob，重开后校验读取；中断状态不自动重跑。原生保存分析侧栏与 Python 共用生命周期，导入结果须明确选择空 Viewer。
  历史运行可明确打开独立冻结图与来源表；后续修订、选择和状态变化不替换该视图，返回保存分析保留原参数与输出草稿。
  历史输入可按精确快照 ID 明确复用到空准备区，保留来源与映射，再单独准备新运行；
  复用和准备只核对元数据，开始执行才校验输入字节，不自动替换当前定义、草稿或启动计算。
  明确读取归档后可按请求顺序检查全部输出，使用分页类型化属性表浏览内联值、表格和错误详情；
  部分失败保留可用输出与失败状态，blob 内容仍通过元数据表示，属性浏览不额外读取文件或打开 Viewer。
  内联科学表格可明确打开只读行列网格，按 64 行、8 列分页，保留列顺序、原始行身份和单位，
  选中单元格可查看精确类型化值或进入复合内容；结构不一致明确报错，不补行或推断类型。
  可按原始行列索引明确跳转并从目标开始分页；输入无效时保留当前数据与选择，浏览不读取额外文件。
  macOS/Windows 可运行[离线分析验收](../examples/project_analysis/README.md)，明确创建新的 73×10 合成 CSV 项目，
  完成冻结、执行、归档与表格分页检查；保留已有项目及 Viewer，不依赖模型或服务器。
  已新增保留正负值的 `scalar-volume` 预设，明确字段、零起始分量和单位标签，见[标量体渲染](scalar-volume.md)。
  浮点显示溢出明确报错，原生 GPU 上传副本使用稳定范围映射；普通模长 `volume` 及默认打开行为保持原语义。
  三维“全部显示”和原生方向操作按当前区域宽高比取景；普通布局调整保留相机，来源与统计标签在浅色场景中保持可读。
  补全、原生图的增删节点与多输入编辑、完整相机控制与远程桌面操作仍待扩展，见[Python 指南](scripting.md)。
- Runtime SSH 管理首版已接入原生 Jobs 与 CLI：OpenSSH Host、健康检查、显式断开/重连、
  桌面退出清理和服务器任务独立寿命。本机真实 sshd + Runtime 端到端通过；跨平台真实 SSH 链路
  与通用对等端点仍待验收/开发，见[SSH 指南](ssh.md)。

## 已确定的开发方向

1. 准备和运行模拟时以 AI 对话为主要入口；分析结果时以三维及数据视图为中心，AI 保持可用。
2. 节点编辑器同时表达项目流程与可进入的分析子图；批量运行复用流程定义。
3. 输入、参数、数据检查、运行记录、文件与插件对象共用有类型的表格框架。
4. SQLite 保存项目结构与关联；表格、节点图、AI 使用同一项目模型与修改接口。
5. 参数通过稳定标识引用，支持跨表表达式；轻量派生值自动更新，昂贵操作标记待运行。
6. 文件是项目的一等对象；代码交给 VSCode，应用内支持 Markdown、HTML 报告与 PDF，
   LaTeX 编译通过外部工具链生成可查看的 PDF。
7. 将仍在使用的 `toolkits/` 功能按职责整合进 `suan/`，消除重复实现，最终取消独立顶层目录。
   保留 CLI 与 Python 导入的过渡兼容；插件能力通过注册契约提供，不以目录位置定义。
8. 在界面内提供 Python 编程入口，全部面向用户的操作逐步开放统一 API，包括页面布局配置；
   Python、手动 UI 与 AI 共用操作规则。代码编辑仍可跳转 VSCode。
9. 支持两台 STK 机器直接通信及 SSH 通信；新增跨平台轻量端点和 SSH 连接管理，保留现有 hub 路径。
   已交付 Runtime 的 STK 内 SSH 管理首版，见 [SSH 指南](ssh.md)；本机 stdio 桥和 Linux Runtime
   不等同于跨平台对等通信已完成。

本轮不冻结面板尺寸、导航样式、表达式语法、数据库 DDL 或文档渲染技术。

## 阶段与验收条件

以下 P0–P5 是本轮重排后的计划编号；按依赖推进，不以未验证的工期作为承诺。

| 阶段 | 交付内容 | 退出条件 |
|---|---|---|
| P0：稳定基线与关键验证 | 复核上述 CI 问题；保留双平台启动脚本；验证 SQLite 接入、原生 UI 中的富内容预览与跨平台文档渲染候选方案 | 相关失败有可复现案例和修复验证；记录 macOS / Windows 的构建与基本交互结果；技术验证形成选择记录，不把原型写成已发布能力 |
| P1：项目模型与表格最小闭环 | 新建/打开/保存项目；对象、字段、稳定引用、资源索引；参数表与运行记录表共用框架；字面量、直接引用、简单表达式；修改命令、版本与基础撤销 | 保存重开不丢失类型和引用；排序、改名不改变引用对象；跨表修改只使依赖项失效；循环和类型错误可定位；编辑不会启动模拟；同一对象在表格与属性视图一致 |
| P2：AI 批量模拟闭环 | AI 主工作区；将用户意图转为可编辑参数表和执行计划；批量实例化流程；复用 Runtime 提交、监控与取消；资源表与 VSCode 打开入口 | 从“运行一组模拟”到参数检查、明确执行、状态跟踪、结果关联走通；手动修改与 AI 修改结果一致；提交重试不重复启动；关闭桌面后重新打开可恢复任务关联；失败行可单独重试 |
| P3：分层流程与分析 | 项目节点图、子图导航、显式输入输出；分析节点连线；表格/图/3D 共享选择；结果表、二维图、图像；受影响项重算；AI 分析已有数据 | 从项目流程进入分析子图并返回；图端口类型错误可定位；一份流程应用于多行运行；参数变化后保留并标明旧结果，按范围重算；AI 结论能追溯到运行、数据与处理步骤 |
| P4：文档与报告 | 统一预览区；Markdown、HTML、PDF；AI 生成带数据与资产引用的报告；外部 LaTeX 编译节点、日志和 PDF 刷新；图像与视频资源预览 | 文档关联到运行与版本；报告保存后可重新打开，导出时处理所需资产；编译失败能查看日志并跳转 VSCode；macOS / Windows 均验证选定渲染方案 |
| P5：分发与完整体验验收 | 安装包、Python 环境方案、平台文件对话框、输入法/缩放/快捷键、恢复与性能；系统验收及文档 | 两个平台覆盖下述端到端场景；支持矩阵与已知限制明确；发布物在干净环境可启动，不把开发脚本等同于安装包 |

P0 的文档渲染验证只需排除集成风险，完整预览在 P4 交付。P2 先用受约束的流程模板运行批次，
不等待 P3 完整图形编辑器。P1 使用手动操作验证项目模型，P2 的 AI 再调用相同接口。
P2 先提供文件索引、路径与 VSCode 入口；富内容逐步在 P3/P4 接入共同的字段/预览协议。
平台回归贯穿所有阶段，不能等 P5 才测试 Windows 和 macOS。

## 首个端到端场景

以“按一组温度准备并运行模拟，再比较输出”为示例；温度仅是演示字段，不限定实际求解器和扫描参数。

1. 新建项目，登记输入文件与程序位置，选择现有 Runtime 连接。
2. AI 生成参数扫描表、输入准备步骤和执行计划；用户可直接修改表格。
3. 轻量表达式计算派生参数，界面显示校验错误与待运行行。检查计划本身不启动计算。
4. 用户明确要求执行后，保存输入快照并提交；记录 Runtime 任务 ID、日志和资源关联。
5. 结果返回后进入分析子图，在表格、二维图和 3D 中比较；AI 引用对应结果进行分析。
6. 改动一个输入，只标记相关结果过期；保留历史结果，执行选定项后产生新的运行记录。
7. 生成 Markdown/HTML 报告，或编译 LaTeX 并查看 PDF；关闭重开仍可追溯数据与过程。

P2 验收到第 4 步及已有查看器打开结果，P3 完成第 5–6 步，P4 完成第 7 步的报告能力。
macOS / Windows 是客户端；服务端仍按当前支持范围运行在 Linux，不隐含新增 Windows 本机求解服务。

## 紧接着的开发包

2026-09-28：首批存储、桌面生命周期、类型化表格、引用/公式、撤销、文件索引、输入版本与运行关联
已形成可运行闭环；[温度扫描示例](../examples/project_scan/README.md)已经过真实 Runtime 验证，
[离线演示](../examples/project_scan/OFFLINE.md)支持无服务器测试。两者使用合成场，不能作为物理仿真的验收。
真实 MuFerro 的项目参数驱动输入准备、运行关联、结果收集和原生入口已接通，
原生按钮驱动真实求解器的完整流程已验证，见[验收记录](runtime-validation.md)。无需重新从存储原型开始。
完整程序环境冻结、项目打包、富内容和原生文档验证仍未完成，P0/P1 不标记整体结束。

**在 STK 中完成一次完整的真实仿真**已按下列流程通过验收。首个案例复用已有
[MuFerro 适配器](runtime-mupro.md)，macOS/Windows 作为客户端，计算由 Linux Runtime 执行。
接下来扩展批次和 AI；完整 AI 页面和图形节点编辑器不作为单次仿真的前置条件。

| 步骤 | 本轮要补齐的用户操作与验收 |
|---|---|
| 输入与参数 | 在 STK 内导入已有案例，形成可编辑的类型化参数表；从选定行生成输入，校验后冻结副本；保留原始案例 |
| 准备与运行 | 选择已有直连/SSH Runtime，检查参数、输入版本和资源；明确提交，查看日志、状态并可取消；编辑或准备本身不启动求解器 |
| 结果收集 | 收集成功任务的输出，检查文件哈希与求解器完成记录；将数值摘要、文件、任务和运行关联，重复收集不增加任务或结果行 |
| 科学结果检查 | 在 STK 的结果表和三维视图中查看真实输出；以固定小案例的参考数值和独立读取检查结果，不能只以任务成功或有画面判定通过 |
| 恢复与重算 | 关闭重开仍可查到冻结输入、任务及结果；断线恢复不重复提交；修改参数后保留旧结果，新计算产生独立运行记录 |

首个案例通过后，再把准备和收集过程提炼为通用模板。求解器安装、许可和服务器环境配置属于部署前提，
在界面中呈现可操作的错误；本轮不承诺 Windows/macOS 本机运行 Linux 求解服务。

开发包按以下依赖推进；第 1 包已验收，第 2 包首版及其跨平台 CI 已通过。
第 3 项已交付 AI 准备与参数建议基础，第 6 项已交付分析图只读检查；继续补齐两者与项目流程的连接。
每个增量都应能单独审查、运行和回退：

1. **单次真实仿真闭环（已验收）**：实现上述 MuFerro 案例的输入准备、项目参数绑定、结果收集与原生工作台入口；
   首版已接入，见[使用指南](simulation-muferro.md)。真实 Runtime + Release MuFerro 已验证 298 K 和 310 K 两次运行，
   原生完整按钮链路已用实际 Release 求解器通过，包含重复准备/收集、服务器停止后的项目重开和三维载荷加载。
   `763eb0b` 的桌面及 Runtime CI 全部通过；本机和 Linux CI 桌面 526 项、macOS CPU 322 项与 Metal 59 项无跳过通过。
   自动化按钮和离屏渲染不等同于全部真机输入设备交互已验收，后者继续按平台清单跟踪。
2. **通用批次准备**：将真实案例流程和已验证的扫描脚本提炼为参数表驱动的受约束流程模板，提供输入生成和选行准备；
   复用格式 5 运行记录及原生提交面板。覆盖部分失败、重复点击、关闭重开和单行重试，不重复造调度器。
   首版 `stk.batches` 与原生“仿真批次”已接入，保存模板版本、明确行范围、连接和选项，逐行保存操作结果。
   内置 `muferro/1` 支持复制参数值、多行准备/提交/刷新/取消/收集及失败行独立重算；
   实际 298 K / 310 K 批次参考数值通过，使用和边界见[批次指南](simulation-batches.md)。
   通用协调器已与具体模板分离，更多模板、参数扫描生成器及工具包迁移尚待后续实施。
3. **草案检查与 AI 工作区基础**：确定性草案的原生差异/错误检查、基础修订、稳定命令与显式应用闭环已实现，
   见[预览指南](project-preview.md)。`stk.project.review` 已接入原生检查，固定项目句柄与基础修订，
   保留已有草案和正在输入的文本，用户明确点击后才应用。格式 6 已增加已检查草案的显式保存、列表、
   载入、丢弃与原子应用回执；过期草案需另起新草案，撤销不会重置旧回执。
   格式 7 已按[对话上下文设计](design/review-drafts-and-conversations.md)接入显式上下文快照、手工消息、
   同修订草案来源和重开查询；原生讨论页可检查缺失/省略/旧修订，保留消息输入及迟到响应保护。
   上下文只读单元格表、项目表格的搜索/错误筛选及 Python 读取/明确设置共享选择已接入。
   格式 8 请求记录、本地执行器及原生查看/取消已接入，固定输入来源，区分未发送、确定结果与结果不确定；
   单次领取、进程锁和原子回复保存避免重复发送或只保存半个结果。重开不自动恢复执行。
   阿里 Token Plan 文字适配已接入环境凭据、本机预检、原生准备/发送与本地结果核对；HTTP 受控测试不消耗额度。
   Linux 另以 `qwen3.7-plus` 完成一次合成单元格真实调用，回复、来源与文字摘要一致，关闭桥后重开数据不变；
   记录为一个请求、两条消息，无请求阶段的项目变化事件。发送前失败保留待发送，取消与关闭遵守原请求生命周期。
   原生 AI 工作区首版已实现捕获 → 准备（不发送）→ 明确发送、保存问答导航和有时限的本地状态跟踪，
   窄窗口折叠数据设置，宽窗口并排显示数据与对话；未保存输入仅在各编辑器内按项目保留。
   独立审查指出的活动输入跨项目残留、长回复裁切、首次点击准备及共享问答选择问题已修正；
   测试发现的缓存插入使 JSON 引用失效及配置键顺序导致重试失败也已修正。
   重点回归 41/41、Linux 完整 CTest 602/602 通过，均无跳过；`852b343` 桌面与 Runtime CI 全部通过。
   准备的消息保存与请求创建分两步；失败可留下消息，身份复用限于同次会话的当前相同输入。
   流式显示已接入内存快照及原生临时回复标记，取消/断流不发布半条助手消息；
   普通参数编辑提案已接入结构化回复、原子草案保存与明确检查入口；
   原生重点 29/29 与后端组合 455 项通过，`bf9ccd1` 完整及跨平台回归全部通过，详见验收记录。
   审查发现的满标签导航失败、深层回复格式化及应用后状态缓存问题均已修正并加入回归。
   macOS/Windows 原生真实模型验收仍需单独完成；
   远端观察仍单独规划，不把本地自动刷新当作远端状态查询。
   提案仍走现有检查/应用流程，单次连通性验证不作为模型质量结论。
   AI 将调用前两包已验证的准备和执行能力；应用表格修改、准备运行、提交任务保持独立。
4. **共享表格与关联视图**：普通项目表格文字搜索/错误筛选、受限值摘要和只读捕获表已接入；
   归档结果已接入可复用的只读类型化属性模型、内联科学表格网格与精确标量分页；继续大表读取、精确排序/筛选和插件字段协议；
   表格、属性和后续节点图共享稳定选择。
   先明确富内容摘要与详情预览的边界，再接入图像、链接和节点对象，避免每个单元格成为独立编辑器。
5. **P0 文档嵌入原型**：按[技术验证计划](design/document-preview-spike.md)在真实 GHOST 窗口内验证
   WKWebView/WebView2 候选；记录菜单、焦点、输入法、DPI、资源及发行结果。通过前不声明 Markdown/PDF 已支持。
6. **分析工作流与过期传播**：复用 `stk.graph/1` 和 `stk.graph` Python API，先交付当前预设与结果回执的只读节点图检查，
   明确配置变化、哈希不匹配、待求值与导入结果无原始图的边界。项目内分析定义保存与重开已接入普通表格、CAS 和撤销；
   格式 9 已连接不可变输入快照与明确执行，保存单次领取、取消意图和可重开读取的校验归档；
   保存分析的类型化参数编辑已接入，明确保存后才用于新运行；历史运行可明确打开独立的只读冻结图，
   检查来源与输入映射，保留当前分析草稿；参数与输出已能联合保存，历史输入可明确复用后准备新运行。
   归档结果已可检查全部输出、原始错误和内联科学表格；已有节点的单输入连线替换首版已接入（见下文），
   继续大表读取、精确筛选、项目流程层、子图导航与结果选择同步；
   只读画布不表示 P3 多层节点已完成。
   保留正负值的标量体渲染、明确字段/分量/单位标签已接入；`volume` 继续用于模长。
   字段自动发现、单位换算、更多数据关联方式和多结果比较仍待实现；显示编码精度及缺失值策略见[标量指南](scalar-volume.md)。

### 工作台与技能目录之后的工作流增量：保存分析的单输入连线

状态：**首版已实现**（2026-10-06，用法见[保存分析指南](project-analyses.md#编辑连线与图结构)）。
在保存分析的草稿面板“连线”中选择节点的已知单输入端口，从全部已声明的上游输出中明确指定来源；
校验结果绑定下列全部条件，含连线修改的草稿必须当前候选校验通过才能保存，只有参数/输出修改的草稿行为不变。
目录读取前或失败时输入保持只读。画布仍显示已保存定义，候选连线在面板中列出。

原定范围：先在选中节点的输入表中选择一个已有单输入端口，明确指定上游节点及输出端口，
形成可检查的本地候选；可选端口支持明确断开。节点身份沿用分析文档内的字符串 ID，与分析 UUID 一起定位，
不将它当作独立项目记录 UUID。首版不包含新增/删除节点、多输入列表编辑、拖线/位置保存或子图。

- 图连线、类型化参数和有序输出共同组成一份候选文档；保留未触碰字段及缺省/空值的区别。
  无效的参数原始文字必须保留，不能因连线操作被重置或静默解析成另一份值。
- 明确校验完整候选后才允许保存。端口联合类型、子类型、数据种类与循环检查复用 `graph.validate`，
  界面目录仅提供选择提示，不能以端口显示名称相同代替兼容性校验。
  静态校验允许的未知数据种类仍须在执行时核对实际数据，不能向用户承诺其必然兼容。
- 校验回复固定项目打开句柄、分析 UUID/读取修订、完整候选版本及桥/目录会话；任一项变化使旧回复失效。
  保存复用分析更新接口的修订检查，只产生一次修改与撤销；失败或回复不确定时保留候选，禁止自动重发。
- 验收有效替换只改变目标连线，错误类型/循环/陈旧回调被拒绝，未知或多输入端口保持只读，撤销恢复精确文档。
  当前 Viewer、已冻结运行及旧结果保持原样；校验、保存和检查候选均不执行节点，另行准备并明确开始才运行。

科学表格的后续排序/筛选应作用于完整的不可变源行索引，再分页显示；不能只排当前 64 行，也不能把全部值
转成 double 或显示字符串比较。它需另外定义混合类型、空值、精确数值比较与被过滤目标的定位行为，
保留源行列身份；大表 blob 读取先确定有界读取契约。这些工作与上述连线首版分开验收。

Python 与跨机器连接继续作为贯穿任务：补齐相机等用户操作时先明确多 Viewer 区域的目标身份；
通用对等端点先交付跨平台能力协商、配对、受限项目/文件操作与撤销授权，再考虑远程 UI/Python。
SSH 首版连接 Linux Runtime；两台 macOS/Windows STK 的直接通信不能由现有本机桥或 SSH 验证代替。

## 新增贯穿任务：Python 自动化与连接

需求、当前实现边界及候选方案见[Python 与机器间通信设计](design/scripting-and-connections.md)。
以下补充 P1–P3 的交付范围，具体子阶段按验证结果排期：

- P1：建立可供 UI/Python/AI 共用的操作目录；项目桥接口同时考虑脚本调用；
  验证 Python 控制 C++ 布局的主线程调度与保存/恢复，确定独立会话与反向调用通道。
- P1/P2：交付界面内 Python 控制台、多行执行、帮助、输出/异常、中断和运行脚本文件。
  同一编辑通过不同入口执行应得到相同校验与项目修订；逐步覆盖全部公开操作。
- P2：在现有远程 Runtime 能力上补 STK 内 SSH 隧道管理、连接状态与断线恢复，避免重复提交任务。
- P2/P3：交付可用于 Linux/macOS/Windows 的轻量通信端点、直接配对与能力协商，
  验收两台机器的项目操作和文件传输；远程 UI 操作需单独绑定授权桌面会话。

桌面布局脚本化复用现有 C++ 布局系统；新增端点不隐含将 Linux 调度服务移植到所有平台。
直接连接不承诺自动 NAT 穿透；项目副本传输不等同于多人实时协作。冻结的桥 v1 不因此自动获得反向 RPC。

## 后续重构：toolkits 整合

状态：方向已确定，尚未实施。历史定位、目标映射及兼容要求见[仓库结构说明](repository-structure.md)。
这项工作区别于已完成的历史文件归档：有用功能将迁入活跃代码并继续维护。

建议结合 P1–P3 按依赖安排，不将一次性完整搬迁作为 P1 原型的前置条件：

- P1 期间梳理调用与资源路径、确定模块边界和兼容策略；新功能优先复用 `suan/` 中的实现。
- P2 批次准备开发时整合 `sjob`/`smesh` 的相关能力；批次准备与 Runtime 调度明确分工。
- P3 分析开发时整合 `sviz` 到数据、分析、绘图和可视化模块，并整理示例与回归夹具。

每批迁移需更新 CLI 自动发现/注册、MCP、旧 Qt 与可选插件的调用，以及包映射和资源加载；
验证现有命令、Python 兼容导入、科学结果、基础安装可选依赖边界与 wheel/sdist。
最终退出条件是调用和资源迁移完成、相关测试与源码目录外的安装验收通过、兼容/退役安排明确，
随后才能取消顶层 `toolkits/`。`suan/batch/`、`suan/structure/` 是候选模块名，实施时再定稿。

## 旧里程碑与兼容性

- D1 保持已交付状态。旧文档中的 M-D2 桌面补齐项按此计划排期：平台/打包项进入 P0/P5，
  自定义颜色与等值面参数、二维图/表格结果展示进入 P3。
- AI 与节点编辑器不再作为彼此独立的后期页面开发；它们分别在 P2/P3 共享 P1 的模型与表格框架。
- 旧 Qt 的归档仍需通过原有替代能力验收门槛：Jobs 与 Viewer 对照清单中的必要能力、
  平台输入与分发验收、迁移说明。是否归档单独记录，不因新设计获认可或某个 P 阶段完成而自动删除。
  该门槛也不要求等待所有新增 AI/报告功能完成。
- 继续遵守已发布的 `stk.graph/1`、`stk.payload/2`、`stk.result/1` 和桌面桥 v1 契约。
  SQLite 项目格式与分层流程是新增设计，不回写成这些契约已经支持的功能。

## 开发与验证约定

按所有者要求，日常工作直接在 `main` 开发、提交与推送；不自动创建分支或合并无关 PR。
每个实现包更新计划状态和适用的验收/功能对照记录。文档变更检查链接与差异；运行时改动按影响范围
验证持久化、引用、缓存失效、任务幂等与界面行为。跨平台结论注明是 CI、合成事件还是真机用户反馈。

项目格式变更必须有迁移/恢复验证；公式或依赖修改必须覆盖循环、删除引用、类型/单位错误与过期传播；
批次执行必须覆盖部分失败、断线恢复和重复提交。完整 UI 布局另行评审，不在本轮文档中定稿。
