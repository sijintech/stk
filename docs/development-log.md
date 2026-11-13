# 开发交接记录

## 2026-11-13 23:27 UTC · Web 全量通过，保存副本合成候选通过 Linux

Web 最终生产构建和全量 Playwright 403/403，零跳过。较早一轮在并行构建负载下出现三项定期任务读取误判与两项 Viewer 截图超时，修订与复验后通过。最新消息定向测试用静态偏移验证 Tab 和 Enter 的焦点顺序。真实 Hub 回执另用实际 PageUp、Shift+Tab 和 Enter，宽窄窗均回到末尾且保持草稿。证据 `root-delivery-20261113-193/{web-exact.xml,web-recheck.xml,live-follow-acceptance/browser-receipt.json,live-follow-acceptance/hub-receipt.json}`。

隔离保存候选 `adfd87ac1534da133dc19fef8383ca4b49a165b7` 使用含比例字体和 Markdown 测试修订的基线，重新编译通过。文件暂存 20/20、回退 9/9、原生会话与项目草稿 52/52。Linux X11 从已打开合成项目工作台起步。英文 1600×1100 四次点击到测试选择器，显式选择新名称后保存。中文 680×1000 五次点击到输入字段，键入路径后 Tab 与 Enter 确认。两窗分别合测取消、已有名称、保存，快照解析累计零、零、一次。60 字节副本摘要与冻结内容一致，原数据与修订一致。macOS ACL 与 Windows 绑定目录重命名仍待目标平台验证。证据 `root-delivery-20261113-193/{save-platform-unit.xml,save-platform-fallback.xml,save-platform-project-final.xml,native-save-chooser-platform-head/receipt.json,native-save-fallback-platform-head/receipt.json}`。

远端 `834f7bd4` Runtime 13/13 已完成。Desktop Linux 三项通过，macOS 已进入 WKWebView 原生验收，Windows CPU 仍运行，待整轮终态后推送。Claude 118 在独立 worktree 继续桌面输入卡片。PR #53 的对应主线生命周期用例 35/35，原 PR 提案与当前发布契约的忙状态语义不同，沿用当前契约。PR #54 仅旧交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43522208408) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43522208394)

## 2026-11-13 23:19 UTC · 保存会话一键回到最新消息

本地 main `9588193c1d3849e9cde0ebb9635ef9ccd5d90ff7` 让 Web 已保存会话在最后一条消息未显示时提供「跟随最新」。首次载入历史仍从原阅读位置开始。Chromium 与真实 Hub 固定起点为已打开 60 条记录的合成会话、正文在顶部、输入框有未发送草稿。1440×900 和 390×844 各一次点击到末尾，焦点在正文。按 PageUp 后，Shift+Tab、Enter 可再次回到末尾。两轮测量均零 Hub 请求、模型调用与草稿变化，32 条会话记录摘要相同。首次实现抢占了输入框前一个 Tab 位置，已把按钮移到正文之前。真实窄窗还复现快速键盘返回时 PageUp 动画覆盖跳转，最终用即时滚动处理。生产构建通过，定向 10/10。全量复验结果单独记录。证据 `root-delivery-20261113-193/{web-before.log,web-instant-build.log,web-recheck.xml,live-follow-acceptance/browser-receipt.json,live-follow-acceptance/hub-receipt.json}`。

本地 `67195f24` 修正两组导航测试对定期只读 `task.get` 的处理。保留零写请求、会话请求与精确任务文件路径断言。桌面比例字体同一构建的项目全量 1568 项，首跑 1566 项通过，缺已安装 Peer helper 路径的两项补齐既有安装后通过，零跳过。证据 `root-delivery-20261113-192/typography-all-project.xml` 和 `root-delivery-20261113-193/peer-installed.xml`。

Root 在独立 worktree 将保存副本候选重新合成到当前代码头，得到 `adfd87ac1534da133dc19fef8383ca4b49a165b7`，无冲突、gitleaks 零发现，精确候选 Linux 构建进行中。Claude 118 继续在自己的 worktree 实现输入卡片。远端 `834f7bd4` Runtime 13/13、Linux 桌面三项、Pages 与 Secret scan 成功。Desktop macOS 与 Windows 仍运行，整轮终态后再推送。PR #53 功能已在主线，#54 仅旧交接。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/43522208394) [Desktop CI](https://github.com/sijintech/stk/actions/runs/43522208408)

## 2026-11-13 23:01 UTC · Windows Markdown 原生捕获回归

Root 从 `413a2833` 的终态 Windows 日志确认，Markdown 第 13 轮超时来自 `CreateForWindow` ABI 本身耗时 120041 毫秒。HRESULT 检查和本地清理耗时均为零，首张成功样本已识别正文。此前 PDF 同类阻塞已采用随窗口生命周期持有捕获目标。主线本地 `895a6b577acb8e88dee046a4d465d6a41c1f0860` 把同一路径用于 Markdown，仍为每次像素采样新建捕获会话。Linux 原生报告测试目标编译并链接通过，Windows 实际 20 轮待下一个代码头 CI。证据 `root-delivery-20261113-192/{413-windows-api.log,windows-markdown-harness-build.log}`。 [上一轮 Windows 原生验证](https://github.com/sijintech/stk/actions/runs/43511133797/job/132206514170)

Root 补跑当前头完整 UI 标签 147/147、零跳过，含 Xvfb 和图形画廊。桌面与相关测试目标最终构建退出码为零。完整项目标签 1568 项正在执行。远端 `834f7bd4` 的 Linux 包与安装冒烟已成功，完整 Desktop 与 Runtime 尚未结束。证据 `root-delivery-20261113-192/{typography-all-ui.xml,final-build.log}`。 [当前 Desktop CI](https://github.com/sijintech/stk/actions/runs/43522208408) [当前 Runtime CI](https://github.com/sijintech/stk/actions/runs/43522208394)

## 2026-11-13 23:00 UTC · 工作台发布与桌面正文比例字体

已把 15 个提交快进推送到远端 `834f7bd4656fe197e7bc8d93a5454042a718498d`，范围 gitleaks 零发现。该头 Pages 和 Secret scan 已通过，Desktop 与 Runtime 继续运行。 [Pages](https://github.com/sijintech/stk/actions/runs/43522208435) [Desktop CI](https://github.com/sijintech/stk/actions/runs/43522208408) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43522208394)

Claude 117 在独立 worktree 交付 `4f3b650b8cc8bda942cf453109c9e622e3111e64`。Root 将其集成到本地 main `15d879b20d1eb57bb7dafea42fab13a7238b62f9`。聚焦项目问答与智能体正文用比例字体，折行、行高、滚动和键盘移动与绘制一致。角色沿用文字标签。分栏、原始回复、日志、计划与文件预览保留等宽字体。Claude 在基线上复现三项项目用例的字体断言失败，候选项目组 1566/1566。Root 主线 UI 核心 136/136，相关定向 30/30，包含实际 Xvfb 组件画廊，桌面与项目测试可执行文件均重新链接。

Linux X11 固定起点是已打开合成智能体会话甲、正文已上滚且有未发送草稿。1600×1100 英文宽窗选乙再回甲共两次点击，680×1000 中文窄窗各次经过「历史」，共四次点击。两个窗口恢复的正文区域与出发时像素一致。草稿字样及其位置一致，亮像素掩膜重合 95.8% 和 95.9%，出发时输入框保有焦点，返回时未获焦。最初按整块颜色比较受焦点背景影响，复验用实际字形判定。每轮两次 `project.agent.get`，零发送、模型调用及项目写入，数据库与两条会话链摘要一致。重新折行时仍以像素偏移恢复，宽度变化可能落在不同文字行。证据 `root-delivery-20261113-192/{typography-wide-verified/receipt.json,typography-narrow-verified/receipt.json,typography-focused.xml,typography-ui.xml,typography-build.log}`。

Claude 118 已在 `claude/native-conversation-composer-118` 从 `15d879b2` 开始桌面输入卡片，负责聚焦工作台的问答与智能体输入布局和对应回归。Root 继续处理平台验收和集成。保存副本候选仍待目标平台验证。原七份工作区修改保留。

## 2026-11-13 22:47 UTC · 上一主线 Desktop 已到终态

远端 `413a283379e032f64b857d53844612fbc1b705bc` Desktop 于 22:44:52 UTC 完成。Linux 三项及 Windows CPU 成功。macOS 必测预览 4/6，MP4 和 HTML 两项隐藏后时间回退，CPU、Metal 及独立暂停恢复用例通过。Windows 原生预览 5/6，包括 20 轮 WebView2 合成、HTML、PDF、MP4 和 HTML 视频。Markdown 第 13 轮第二次 OS 捕获在 `capture.create-for-window` 返回 `0x8007041d`，耗时约 120 秒，超出可见像素等待期限。此前样本已定位第一页正文，计数为一，要求连续两次。Runtime 13/13、Pages 和 Secret scan 均成功。证据 `root-delivery-20261113-192/413-windows-api.log`。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43511133797) [Windows 工件](https://github.com/sijintech/stk/actions/runs/43511133797/artifacts/14083665425) [macOS 工件](https://github.com/sijintech/stk/actions/runs/43511133797/artifacts/14081159332)

发布前 AOCI 0.1.0-rc21 检查返回 `stopped/blocked`，194 项计划目标、零签发候选。范围状态为 `observed_evidence_review_required`，有 94 项待复核观察，无未决恢复或第三方冲突。保留既有索引字节。证据 `root-delivery-20261113-192/release-aoci-scope.json`。前序 Desktop 门禁已到终态，独立候选仍按各自证据推进。

## 2026-11-13 22:43 UTC · 完成保存候选的 Linux 回归

候选 `b1417391f905cda31e4424057cf6caaeac0b146a` 的桌面构建、智能体运行 49/49、保存输入定向 2/2 和 UI 135/135 全部通过。英文 1600×1100 从已打开合成项目工作台实测四次点击到保存选择器，确认新名称后得到校验副本。取消、已有名称、成功的合测共六次应用点击、三个选择器结果和 Esc。两个窗口用同一构建通过，项目与快照摘要核对一致。候选仍在 Root 隔离 worktree，macOS 和 Windows 的保存路径待原生验收。证据 `root-delivery-20261113-191/{save-keyboard-project.xml,save-keyboard-targeted.xml,save-keyboard-ui.xml,native-save-chooser-keyboard-release/receipt.json,native-save-fallback-keyboard-final/receipt.json}`。

Claude 117 在独立 worktree 提交比例字体候选 `4f3b650b8cc8bda942cf453109c9e622e3111e64`，Root 已核对当前主线可干净集成，等待 Claude 的对照结果和独立回归。远端 `413a2833` 的 Windows 原生预览仍运行。范围 gitleaks 零发现，原七份工作区修改保留。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43511133797)

## 2026-11-13 22:39 UTC · 保存副本键盘复验与 macOS 工件

Root 在桌面隔离候选中复现路径字段获焦后直接输入会追加到建议名称。候选修订 `b1417391f905cda31e4424057cf6caaeac0b146a` 进入表单和路径被拒后选中当前文本，下一次输入可替换。Linux X11 680×1000 中文从已打开合成项目的工作台起步，五次点击进入保存路径。输入路径，按 Tab 和 Enter 明确确认。取消、已有名称和成功路径合测共七次点击、两次路径输入、两组 Tab 与 Enter，最后 Esc。内容解析累计零、零、一次。保存的 60 字节摘要、0600 权限、原有文件和项目数据库已核对。最终桌面构建与 UI 135/135 通过。证据 `root-delivery-20261113-191/{native-save-keyboard.log,native-save-fallback-keyboard-final/receipt.json,save-keyboard-ui.xml}`。

远端 `413a2833` 的 macOS 官方工件显示 CPU 1621/1621、Metal 254/254，必测预览 4/6。MP4 和 HTML 视频暂停且未结束，失败谓词是隐藏后播放时间相对隐藏前回退超过 50 毫秒，实际分别约 120 和 107 毫秒。安静隐藏对照两种媒体均成功，独立的原生暂停、隐藏、重新显示与继续播放测试 1/1。Linux 三项和 Windows CPU 已成功，Windows 原生预览仍在运行。证据 `root-delivery-20261113-191/413-macos-observation.json`。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/43511133797/artifacts/14081159332) [Desktop CI](https://github.com/sijintech/stk/actions/runs/43511133797)

## 2026-11-13 22:22 UTC · 会话标题对齐与桌面保存候选复核

本地 main `c7e0408985cd2835dba9775d6d982208a03392a8` 将 Web 已保存对话的可见页头简化为会话名。历史条目和标题提示仍可查短 ID，缺失会话仍保留识别提示。Chromium 连接真实 Hub，固定起点为已配对工作台、32 条合成会话。1440×900 从左栏一次点击，390×844 经「历史」两次点击，进入同一已保存会话。每窗各一次原会话历史 GET，零写请求和模型调用，Hub 会话摘要一致。Web 生产构建及 Playwright 401/401 通过，零跳过。更新 Synthrix 逐区对照的交付状态。证据 `root-delivery-20261113-191/{web-build.log,web-full.xml,live-title-final/browser-receipt.json,live-title-final/hub-receipt.json}`。

Claude 113 在独立 worktree 交付跨平台保存修订 `50b7c683c31f03c4e7114c67db89e25dad89da33`。Root 在隔离 worktree 审阅集成，补 Windows 保留名转换，包括 COM¹、CONOUT$ 及扩展名前的空格，形成候选 `d6faafff1bdee2272000c3582e6704bbb37f354d`。Linux 构建通过，文件暂存 20/20、回退 9/9、智能体运行 49/49。Claude 的 Linux 全量 2271/2272，单次历史计时失败在独立复测 5/5 和三个相关用例中通过。Mac 与 Windows 暂有接口或桩核对，原生验收待执行。

Linux X11 候选验证的固定起点为已打开合成项目的工作台，选中保存的智能体会话后由关联任务查看冻结文件。英文 1600×1100 使用测试选择器，连续取消、选择已有名称和确认新名称，应用内累计六次点击，另有三次选择器结果。干净路径到「保存副本」是四次点击，再确认新名称。中文 680×1000 使用应用内路径输入，连续取消、拒绝已有名称和保存共十一次点击、两次路径输入。干净路径是七次点击，包含路径字段与显式保存确认。两轮均以 Esc 退出，依次累计零、零、一次快照内容解析。保存的 60 字节与冻结快照摘要一致，权限 0600。原文件、修订、会话与运行记录核对一致。证据 `root-delivery-20261113-191/{save-unit.xml,save-fallback.xml,save-project.xml,native-save-chooser-final/receipt.json,native-save-fallback-final/receipt.json}`。

远端 `413a283379e032f64b857d53844612fbc1b705bc` 的 Desktop Linux 三项和 Windows CPU 已通过，macOS 及 Windows 原生预览仍运行。Runtime 13/13、Pages 与 Secret scan 已成功。待整轮 Desktop 终态后推送。Claude 117 在独立 worktree 继续验证原生会话正文。原七份工作区修改保留。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43511133797) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43511133680)

## 2026-11-13 22:01 UTC · 搜索随窗口缩放保留，补齐 macOS 视频恢复对照

本地 main `907b35b02c4c9ce156bc97f8723674b8c507ce46` 让桌面聚焦工作台的宽栏与窄窗导航共用当前搜索。切换宽窄时保留编辑中的文字、搜索结果与焦点，关闭后焦点回到当前布局的入口。Linux X11 固定起点是任务页、合成项目有 32 条已保存问答。1600×1100 起步一次点击、680×1000 起步两次点击。两轮各在输入后跨断点缩放、按 Enter 搜索、结果显示后缩回、再按 Enter 打开旧问答。每轮一次标题查询、各一次原请求与上下文和消息读取，数据库摘要及修订一致，零写入。定向 69/69、UI 核心 135/135、桌面构建成功。首轮定向测试持有跨帧 widget 指针导致断言失败，按新帧读取控件后通过。证据 `root-delivery-20261113-190/{native-wide-final/receipt.json,native-narrow-final/receipt.json,search-resize-final.xml,ui.xml}`。

上一头 `f3c666eb` 的官方 macOS 工件复核到必测 HTML 和隐藏前对照都在实际报告区缩到 286 像素后通过区域菜单恢复，随后等待视图超时。相同布局的安静隐藏对照成功，其回执显示指针留在菜单时原生交互被挡，移到视口中央后一帧恢复。`2d02ef9046699c072dbb2e3393f9fbb8db607f2e` 让所有从区域菜单返回的 Cocoa 视频测试执行同样的指针移动，并在等待失败时记录视口、覆盖层、精确媒体会话与标签路径。Linux 原生测试目标编译成功。macOS 实测待 CI，MP4 隐藏暂停时间回退仍是独立失败。证据 `root-delivery-20261113-190/{f3c-required-html.json,f3c-required-mp4.json,f3c-control-html.json,f3c-quiet-html.json,build-reveal.log}`。 [官方 macOS 工件](https://github.com/sijintech/stk/actions/runs/43500121086/artifacts/14077324907)

远端 `413a283379e032f64b857d53844612fbc1b705bc` Runtime 13/13 已于 21:53:52 UTC 完成。Desktop 的 Linux 三项通过，macOS 与 Windows 仍运行，待整轮终态后推送。Claude 113 与 117 在各自隔离 worktree 继续修订。PR #53 的功能已随等效主线提交交付，#54 是旧交接。原七份工作区修改保留。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43511133797) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43511133680)

## 2026-11-13 21:50 UTC · Web 历史固定区全量回归

`c3e823eb9b2a87de4dbb3bf2ed88cc280a57e847` 的 Web 生产构建及最终全量 Playwright 401/401 通过，零跳过。该构建包含新输入卡片和固定历史操作。Linux 包及安装冒烟通过，远端 `413a2833` 完整 Desktop 仍运行，Runtime 10/13 已成功。证据 `root-delivery-20261113-189/{web-history-build.log,web-history-full.xml,live-history/hub-receipt.json}`。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43511133797) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43511133680)

## 2026-11-13 21:49 UTC · 会话页头、输入卡片和历史操作

本地 main `ab5dcbc0685be09b698797eee1d40b8bea8bd59d` 将桌面聚焦问答与智能体会话的标题放到正文上方。问答的冻结数据来源与修订移入「请求详情」，状态、模型与适用操作留在原处。Linux X11 固定起点为已打开合成问答、详情折叠。1600×1100 和 680×1000 均一次点击展开，显示原数据来源、修订和两项可复制 ID。项目数据库摘要与修订一致，宽窗零 Bridge 请求，窄窗只有后台注意事项轮询。定向 2/2，Linux 项目 CPU 1125/1125（含两个已安装 Peer helper 用例），桌面构建通过。

Claude 116 在独立 worktree 提交 `bc28502420aeb204ea830567e4c9d5dfe6a0ef7f`。Root 核对 Synthrix 远端仍为 `caec2b9`，修正了新键盘路径和任务面板入口，并在 `5568c2f18d2ef40bab65d40539ce600b69715dbb` 合入逐区对照。`50e7d5a97cb34b7701bac05ca8c3f01e7903223e` 实现 Web 用户消息靠右、助手消息靠左及单张输入卡片。真实 Hub 与 Chromium 固定起点为 1440×900、390×844 已打开合成会话、输入框聚焦且有草稿。两窗均零点击、一次 Ctrl+Enter 发送。上滚 520 像素后回复保留阅读位置，一次点击「跟随最新」回到末尾。每窗恰一条 POST，零模型调用。布局与流程定向 6/6、Web 构建和全量 401/401 通过。

`c3e823eb9b2a87de4dbb3bf2ed88cc280a57e847` 让 Web 的「新对话」与搜索在历史滚动时一起保持可见。真实 Hub 与 Chromium 两窗从已展开、滚到底的 32 条历史起步，各一次点击，进入未保存新对话且输入框获焦。零写请求、零模型调用，Hub 会话摘要一致。定向 6/6，覆盖窄窗键盘滚动与两窗搜索。证据 `root-delivery-20261113-189/{project.xml,native-wide/receipt.json,native-narrow/receipt.json,web-full.xml,web-history-focused.xml,live/browser-receipt.json,live-history/browser-receipt.json}`。

Claude 117 已在 `claude/native-conversation-typography-117` 从 `50e7d5a9` 接手原生正文比例字体、折行和滚动回归。Claude 113 在原独立 worktree 复核 macOS 继承 ACL 和 Windows 目标目录绑定。Root 用候选 `f3131c34` 重编确定性竞态夹具，确认不支持的重命名返回失败且目标名称不存在。 [Apple 文件系统 ACL](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemDetails/FileSystemDetails.html) [Windows 重命名接口](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info)

远端 `413a2833` Linux 包与安装冒烟、Pages、Secret scan 通过，Desktop 与 Runtime 仍运行。待推范围 gitleaks 零发现，原七份工作区修改保留。开放 PR #53 的修复及契约已通过独立提交进入主线，#54 仅含旧大写交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43511133797) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43511133680)

## 2026-11-13 21:31 UTC · 统一工作台会话改动已发布

Root 在前序 Desktop 完整终态后把 16 个提交从 `f3c666eb8ad28fac9dc923065efc7e3feee6b4df` 快进推送到 `413a283379e032f64b857d53844612fbc1b705bc`，独立核对远端完整 SHA。范围 gitleaks 零发现。新头 Pages 与 Secret scan 已成功，Desktop 与 Runtime 待终态。上一头 Windows 官方原生 XML 6/6。上一头 macOS 工件确认 CPU 1618/1618、Metal 254/254、必测原生 4/6。可选 MP4 对照持续播放取到帧 1，立即暂停取到帧 0、0，两组 HTML 仍因视口裁切无帧号。证据 `root-delivery-20261113-188/{release-scan.log,f3c-windows-native.xml,f3c-ctest-native-preview.xml}`。 [新头 Desktop](https://github.com/sijintech/stk/actions/runs/43511133797) [新头 Runtime](https://github.com/sijintech/stk/actions/runs/43511133680) [Pages](https://github.com/sijintech/stk/actions/runs/43511133705) [Secret scan](https://github.com/sijintech/stk/actions/runs/43511133737) [上一头 Windows 工件](https://github.com/sijintech/stk/actions/runs/43500121086/artifacts/14078466145)

## 2026-11-13 21:28 UTC · 会话搜索键盘验收与发布门禁

本地 main `1108d4061f9cd421f134958c25400ba29c2c82d5` 支持桌面按 Enter 提交标题搜索，首批唯一匹配显示后再按 Enter 打开。多条匹配及键盘长按仍留在搜索中。Linux X11 固定起点为任务页、已打开合成项目、32 条已保存问答。1600×1100 一次点击、680×1000 两次点击，两窗各两次 Enter，打开超出近期列表的第一条问答。每窗一次标题查询和一次原请求、数据范围、消息读取，数据库摘要与修订一致，零发送或运行。定向 69/69、UI 核心 135/135，桌面构建通过。实窗夹具需等待 Bridge 的近期项目读取和首屏绘制后再点打开项目。证据 `root-delivery-20261113-188/{search-keyboard.xml,search-keyboard-ui.xml,native-keyboard-ready-wide/receipt.json,native-keyboard-ready-narrow/receipt.json}`。

上一远端 `f3c666eb8ad28fac9dc923065efc7e3feee6b4df` 的 Desktop 于 21:25:49 UTC 完成，五项成功。Linux 三项和 Windows 两项通过。macOS CPU 1618/1618，Metal 254/254，必测 WKWebView 4/6。MP4 在隐藏暂停时间边界失败，HTML 在隐藏暂停已通过后等待重新显示超时。Runtime 13/13、Pages、Secret scan 通过。证据 `root-delivery-20261113-188/f3c-macos-job.log`。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43500121086) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43500120670) [macOS 工件](https://github.com/sijintech/stk/actions/runs/43500121086/artifacts/14077324907)

更早 `13d32015` 的官方工件分段复核。MP4 持续播放对照取到帧 1，立即暂停对照取到帧 0、0，分别来自独立会话。两组 HTML 元素均为 320×180，垂直超出 385×159 的视口，无有效帧号。必测 MP4 和 HTML 隐藏时暂停保持，时间分别回退约 110、137 毫秒。尺寸属性被预览净化器移除。`4b5a6c0452ce71904d1b4a6ca1ec4f786c4de06e` 改用 75% 用户缩放为两组可选 HTML 对照腾出空间，并记录失败几何。Linux 原生报告测试目标编译通过，实际 Cocoa 取图待新头验证。证据 `root-delivery-20261113-186/macos-frame-and-hide-receipt.json`。 [上一 macOS 工件](https://github.com/sijintech/stk/actions/runs/43491122224/artifacts/14073253397)

Claude 113 在独立 worktree 交付 `f3131c344b0e5dd866038edfccf19ff88743191f`，报告 Linux 2267/2267 和旧回退竞态复现已无法留下外来最终名称。Mac 仅桩语法核对，Windows 未编译，候选待 Root 复核。Claude 116 已在 `claude/synthrix-primary-pages-116` 从 `4b5a6c04` 开始梳理 Synthrix 主页面与两端视觉、交互验收，Root 继续负责主线、集成和实测。AOCI 0.1.0-rc21 发布检查返回 `stopped/blocked`，零候选，94 条观察待复核，无 Recovery 或第三方冲突，正式索引和既有工作区修改保持原字节。

## 2026-11-13 21:00 UTC · 会话搜索最终 Bridge 投影验收

`d005cce1dbb76ec1b8526e8f903f97d57531273f` 将 SQLite 请求读取限定为标题绑定所需的身份列，新增助手回复独有词的反证。最终 Bridge、脚本、智能体、请求、归档和项目搜索联跑 177/177。远端到该提交的 12 个提交执行 gitleaks，零发现。证据 `root-delivery-20261113-188/{bridge-release.xml,combined-scan.log}`。远端 Desktop `43500121086` 的 Linux 三项、macOS CPU 已通过，macOS Metal 及 Windows CPU 正在运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43500121086)

## 2026-11-13 20:58 UTC · 搜索项目隔离、旧 Bridge 和全量回归

本地 main `ca63ea02915b0255b332b1c345e4c0a070f19809` 核对两个同时有效的项目句柄，另一项目的查询不返回当前项目的匹配，定向 1/1。`fab1ab230cf05ae5404e7665bc101fc5402e067a` 用真实 Bridge 去掉可选搜索方法，验证桌面仍显示原近期历史和分页入口，搜索入口隐藏，联合定向 2/2。Linux 项目标签全量 1565/1565，新增旧 Bridge 用例单独通过。合成 1000 条问答的本机查询测了各三次，唯一旧标题约 100–111 毫秒，广泛匹配的首批 20 条约 100 毫秒，实际合作方规模的时延待验证。证据 `root-delivery-20261113-188/{project-full.xml,bridge-scope.xml,legacy.xml,search-scale.log}`。远端 Desktop 仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43500121086)

## 2026-11-13 20:54 UTC · 桌面历史可按标题跨页查找

本地 main `e9e6ef119644703499a20412718e74e7a292f31a` 增加「搜索对话」。从左栏或窄窗历史打开，在输入后按 Enter 或点击搜索。统一的可选桌面 Bridge 读取在当前项目分页返回活跃问答及智能体会话的标题。结果明确激活前不打开正文。标题按 NFKC、Unicode 大小写折叠与分词匹配。单次查询扫描候选标题，输出分页。归档问答从既有浏览入口打开，旧 Bridge 继续显示原来的历史。Claude 115 最终稿 `f82275331b3249669f7ee4205fbe29a31f4bd759` 已审阅并整合，采用单个方法和独立历史入口的取舍已写入设计。 [Bridge 契约](specs/stk-desktop-bridge-v1.md) [设计](design/native-conversation-search.md)

Linux X11 固定起点为任务页、已打开合成项目、32 条已保存问答。英文 1600×1100 两次点击，680×1000 三次点击，含入口与选中结果，各一次 Enter 提交。进入的是超出近期列表的第一条问答。每窗一次标题查询，明确选中后各一次原请求、原数据范围及原消息读取。数据库摘要与修订不变，零发送、零执行。界面驱动另外验证草稿和 Viewer 相机保留。Python 177/177、原生定向 69/69、UI 核心 135/135，双语目录各 3013 个键，桌面构建与暂存 gitleaks 通过。证据 `root-delivery-20261113-188/{bridge-final.xml,native-layout.xml,ui.xml,i18n.log,native-final-wide/receipt.json,native-final-narrow/receipt.json}`。

Claude 113 `13bf937eec06c7c36a746a60088110bf157ffbc9` 报告隔离 Linux 2260/2260，macOS 仅桩声明语法核对，Windows 未编译。Root 用链接包装器在无替换重命名回退处确定性替换临时项，复现失败回执仍留下最终路径的外来符号链接。复现记录 `root-delivery-20261113-188/claude-113-race.cc`，后续修订已回派同一独立 worktree。远端 `f3c666eb` Runtime 13/13 与 Linux 三项 Desktop 作业通过，macOS 与 Windows 仍运行，本次代码待前序 Desktop 终态再发布。PR #53 的重试修复及契约已有等效主线提交，#54 仍为旧大写交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43500121086) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43500120670)

## 2026-11-13 20:33 UTC · 双端发送后跟随最新消息

本地 main `edfde0ef61c85fdb3292d3bb9cb8bcb8bb00fd33` 和 `88f3f038aeea0a63aa9a3cd55ece7921dd2f2538` 让 Web 与桌面智能体会话在明确发送后回到末尾。向上阅读后，后续回复保留阅读位置，可按「跟随最新」返回末尾。两端切换会话后恢复各自阅读位置。Web 首次阅读从顶部开始，原生智能体会话首次从末尾开始。 [统一工作台](design/unified-workbench.md)

真实本地 Hub 与 Chromium 1440×900、390×844，从已打开的 60 条合成消息会话顶部、输入框聚焦且已写草稿起步。零鼠标点击，按一次 Ctrl+Enter，待发送消息进入视野。回复前上滚到 520 像素，真实回执到达后仍为 520。点击一次「跟随最新」回到末尾，每窗恰好一条消息 POST，零模型调用。Web 构建与全量 401/401 通过。定向初跑受 Chromium PageUp 平滑滚动影响，最终在固定位置验收，另保留原键盘滚动回归。

Linux X11 1600×1100、680×1000，从 32 条用户消息的合成项目智能体会话、正文已翻到开头、输入框聚焦且已写两行草稿起步。零鼠标点击、一次 Ctrl+Enter，立即回到末尾，可见新消息。每窗一次 `project.agent.say`，零运行审批，项目修订号仍为 0。原生定向 54/54 含另一会话的迟到回复，UI 核心 135/135，桌面二进制构建通过，暂存 gitleaks 零发现。证据 `root-delivery-20261113-187/{web-full.xml,live/browser-receipt.json,live/hub-receipt.json,native-final.xml,ui-final.xml,native-final-wide/receipt.json,native-final-narrow/receipt.json}`。

已从 `f3c666eb` 在独立 worktree 启动 Claude 115，提交桌面跨页会话标题搜索的接口与验收方案。Root 负责代码、合入和验证。Claude 113 修订 `96a2da9e6a32f459302a6b02c53f3d26334bce28` 已提交，后续仍在运行。Root 初审发现命名临时文件的无替换回退仍依赖先按名字发布、再校验身份，候选继续留在独立 worktree。上一头 macOS 完整工件下载多次在 TLS 传输中断，官方作业日志已核对。现远端 `f3c666eb` Pages、Secret scan 与两个 Linux 打包作业通过，完整 Desktop 和 Runtime 仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43500121086) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43500120670)

## 2026-11-13 20:18 UTC · 会话快捷键、草稿保护和 Web 历史搜索已发布

Root 已从 `13d32015` 快进推送到 `f3c666eb8ad28fac9dc923065efc7e3feee6b4df`，远端完整 SHA 一致。14 个提交的发布范围经 gitleaks 零发现。新头 Pages 与 Secret scan 已通过，Desktop 与 Runtime 已启动。Claude 的保存副本修订仍在 `claude/native-conversation-file-save-113`。 [新头 Desktop CI](https://github.com/sijintech/stk/actions/runs/43500121086) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43500120670) [Pages](https://github.com/sijintech/stk/actions/runs/43500120769) [Secret scan](https://github.com/sijintech/stk/actions/runs/43500121013)

上一头 `13d32015` 的 macOS 官方作业日志确认 CPU 1617/1617、Metal 254/254，必测原生文档 4/6。两项视频均在 `hidden-tab-pause` 阶段失败。隐藏前对照 1/2、独立隐藏暂停 0/2。首轮工具栏的四个帧号采样命令均运行成功，具体帧序列待工件复核。上一头 Windows 官方原生 6/6。证据 `root-delivery-20261113-186/{previous-macos-job.log,previous-windows-native.zip}`。 [上一头 Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224)

## 2026-11-13 20:16 UTC · 上一发布头 Desktop 已结束

远端 `13d320155e2f3354f706d54d7ca581971943996b` Desktop 运行于 20:15:14 UTC 结束，六项作业中五项通过。Linux 三项、Windows CPU、Windows WebView2 原生文档通过，Windows 官方原生 XML 为 6/6。macOS CPU、Metal、打包及安装冒烟通过，必测 WKWebView 原生文档、隐藏前对照和隐藏暂停诊断失败。官方 macOS 工件已开始下载，将按实际用例复核。Runtime 13/13、Pages 与 Secret scan 已通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224) [macOS 工件](https://github.com/sijintech/stk/actions/runs/43491122224/artifacts/14073253397) [Windows 工件](https://github.com/sijintech/stk/actions/runs/43491122224/artifacts/14072498601) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43491121980)

待发布范围截至 `0317916ac666b83d2b7cab96ca19b80c2bc1edd5`，包括 Web 历史标题搜索、双端会话快捷键与原生 Esc 草稿保留。Windows 和 macOS 上的新快捷键及草稿行为待本次推送后的验证。原三份 AOCI 工作区摘要一致，四份既有状态文档工作区修改通过定向暂存保护。Claude 保存副本修订仍在隔离 worktree。 [Pages](https://github.com/sijintech/stk/actions/runs/43491121988) [Secret scan](https://github.com/sijintech/stk/actions/runs/43491121943)

## 2026-11-13 20:11 UTC · 桌面实窗验证准备和发送分开

使用 `ababc0c96462612d383d95af1f6e3b772962db22` 的 Linux X11 二进制，1600×1100 英文工作台固定起点为已选合成数据范围与模型标识、两行草稿已写、输入框聚焦。零鼠标点击。一次 Esc 保留草稿，零新增请求。随后一次 Ctrl+Enter 保存一条原文及一条 pending 请求，`executor_id` 为空，零 `project.requests.start`，项目修订仍为 1。证据 `root-delivery-20261113-186/native-question/{receipt.json,escaped.png,after.png}`。远端上一头的两个原生文档作业仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224)

## 2026-11-13 20:07 UTC · 会话改动的 Linux 项目回归完成

`ababc0c96462612d383d95af1f6e3b772962db22` 的本地项目 CTest 1563 项中首跑通过 1561 项。两项已安装 Peer 辅助程序用例需要 `STK_TEST_PEER_INSTALLATION`，指定既有完整可迁移安装后定向 2/2，共 1563 个唯一测试通过。先用仅含构建产物的暂存目录复跑时，两个用例的 Bridge 均未就绪。证据 `root-delivery-20261113-186/{escape-project-full.xml,escape-peer-retry.xml,escape-peer-installed.xml}`。Web 仍以同源码构建的 399/399 和真实 Hub 宽窄窗口回执为准。待发布范围从远端 `13d32015` 到 `95e91e11` 的 11 个提交通过 gitleaks。远端 macOS 与 Windows 原生文档作业仍在运行，保持仓库发布顺序。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224)

## 2026-11-13 20:02 UTC · 原生会话退出编辑时保留草稿

本地 main `ababc0c96462612d383d95af1f6e3b772962db22` 在智能体会话和项目问答中按 Esc 结束编辑，保留本地草稿及焦点。继续打字可编辑原草稿，也可从已聚焦的输入框用快捷键直接触发当前主操作。桌面表格和普通编辑字段维持自己的 Esc 行为。Linux X11 固定起点为 1600×1100 与 680×1000 的已打开智能体会话，焦点在含两行草稿的输入框。每窗零鼠标点击。按一次 Esc，项目修订与会话链保持原值，零发送。随后按一次 Ctrl+Enter，原样新增一条用户消息，项目修订与运行审批数保持原值。桌面 UI 核心 135/135、会话定向 53/53，桌面二进制与测试目标构建成功，暂存 gitleaks 零发现。证据 `root-delivery-20261113-186/{escape-ui.xml,escape-project.xml,native-escape-wide-b/receipt.json,native-escape-narrow-b/receipt.json}`。 [统一工作台](design/unified-workbench.md)

Claude 113 已交付 `9e6a112d97e2ee2fd294e545f50da765074539aa`，报告 Linux 定向 45/45、项目 1568/1568，基础全量在修正 Python 环境后 2244/2244。Root 审阅后把权限与路径替换修订单交给同一个 Claude 会话，现已在独立 worktree 运行。该候选等待修订与复验。远端 `13d32015` 的 Linux 三项和 Windows CPU 通过，macOS CPU、Metal、打包冒烟通过，macOS 与 Windows 原生文档作业仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224)

## 2026-11-13 19:51 UTC · Linux 实窗核对双端快捷键

`fa748646e0e885ffa137046a8d969a0e388ded1d` 补验原生项目问答在键盘准备后仍聚焦原输入框，实际项目 Bridge 定向用例 1/1，暂存 gitleaks 零发现。Linux X11 实窗使用 `b076c2a31d0a35ec2f7828b7b134c5065bd93ab7` 的桌面二进制。1600×1100 和 680×1000 都从已打开的本地智能体会话、已聚焦且写有两行草稿起步，零鼠标点击、一次 Ctrl+Enter。每窗收到一次 `project.agent.say`，仅新增一条文本完全匹配的用户消息，项目修订号为 0，零运行审批。界面显示这条消息并清空输入框。模型未配置，已有的尝试以本地提示结束。项目问答实窗和目标平台快捷键仍待补验。证据 `root-delivery-20261113-186/{native-wide-b/receipt.json,native-narrow/receipt.json,question-focus.xml}`。

远端 `13d32015` 的三个 Linux Desktop 作业和 macOS CPU 步骤已通过，macOS Metal 与后续原生实窗、Windows 作业仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224)

## 2026-11-13 19:45 UTC · 双端会话共用主操作快捷键

本地 main `b076c2a31d0a35ec2f7828b7b134c5065bd93ab7` 采用 Ctrl+Enter（macOS 为 ⌘+Enter）触发当前会话的主操作。Web 发送后回到输入框。原生智能体会话沿用原发送动作。原生项目问答只准备并保存待发送问题，保留输入区焦点，发送由用户单独触发。Enter 继续换行。已整合 Claude 114 的最终对照稿 `1ef7632212a217f742e63afa2f91b60c60508e2d`，记录本次取舍，正文跟随和原生 Esc 草稿保留待接。桌面历史继续使用近期和分页入口，跨页标题搜索待覆盖权限和分页边界。 [统一工作台](design/unified-workbench.md)

真实本机 Hub 和 Chromium 固定起点为打开合成会话、输入框聚焦并已写草稿。1440×900 和 390×844 分别零鼠标点击、一次 Ctrl+Enter，每个会话一次消息 POST，正文保留 Enter 输入的换行，清空已发送草稿后焦点留在输入框，Hub 返回无模型配置的本地响应。Web 构建成功、全量 399/399，包含组字、长按和发送期间下一份草稿的回归。 [验收提案](design/synthrix-workbench-next-acceptance.md)

Linux 原生界面驱动固定起点为已打开会话和已聚焦的草稿输入框。一次 Ctrl+Enter、零鼠标点击，项目问答经实际项目 Bridge 生成一条 pending 请求，`executor_id` 为空，零发送，随后点击同一准备按钮未生成重复请求。1600×1400 智能体夹具同样零鼠标点击、一次 Ctrl+Enter，沿已有动作记录一次 `project.agent.say`，清空草稿并保留输入焦点，零 `project.agent.run.decide`。该测试初跑 1600×1100 未点到可见区外的输入框，调整固定窗口后通过。定向 53/53、UI 核心 135/135、双语 3006/3006，桌面二进制构建成功，暂存 gitleaks 零发现。macOS、Windows 及桌面实窗快捷键待验。证据 `root-delivery-20261113-186/{web-full.xml,live/browser-receipt.json,live/hub-receipt.json,desktop-shortcuts.xml,ui.xml}`。

远端 `13d32015` Runtime 13/13，Desktop Linux 打包与干净系统安装冒烟通过，其余目标仍运行，发布等待该 Desktop 运行结束。Claude 113 首份 `dc8ab856` 在隔离 worktree，Root 复现 POSIX 权限和路径替换问题，后续修订单等待同一 Claude 会话结束现有验证后在原 worktree 启动。开放 PR #53 的相关重试契约已单独接入主线，PR #54 仍为旧交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43491121980)

## 2026-11-13 19:28 UTC · Web 历史可按会话标题查找

本地 main `90bc270e85bc48844aab32b6781c61b3ae7380e5` 增加「搜索对话」。按已载入的标题筛选，空格分隔的词均须匹配。唯一命中时 Enter 打开并聚焦正文，多条或零条时继续留在筛选区。清空恢复完整列表。没有新增后端调用或权限。桌面仍使用近期与分页历史，桌面标题搜索待接。Web 生产构建成功，定向 5/5、全量 397/397，零跳过。修复前的两窗对照因不存在搜索框失败。暂存 gitleaks 零发现。

真实本机 Hub 和 Chromium 固定起点为任务页，已有 32 条已保存会话，选中乙，较旧的甲有未发送草稿且正文已滚至 430 像素。1440×900 宽窗 1 次点击搜索，390×844 窄窗 2 次点击含打开历史。输入「科研 甲」后按一次 Enter，进入甲正文，恢复草稿和 430 像素位置。筛选阶段零请求，打开只发一次原会话 GET。前后 Hub 会话摘要一致，零 POST 与零模型调用。界面驱动另核对保留 Viewer 和任务状态。证据 `root-delivery-20261113-185/{search-final.xml,web-full.xml,live/browser-receipt.json,live/hub-receipt.json}`。 [统一工作台](design/unified-workbench.md)

远端 `13d32015` 的 Pages 和 Secret scan 已成功。Desktop Linux 打包通过，其他目标和 Runtime 仍在运行。Claude 113 和 114 在各自独立 worktree 继续进行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43491122224) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43491121980)

## 2026-11-13 19:21 UTC · 工作台改动已发布到 main

Root 从 `19998d12097685138b555904fbe880e1a91750f0` 快进推送至 `13d320155e2f3354f706d54d7ca581971943996b`，独立核对远端完整 SHA。14 个提交范围的 gitleaks 零发现。新头 Secret scan 与 Pages 通过，Desktop、Runtime 正在运行。上一头的 Windows 原生官方工件 `14069047795` 已下载并核对，必测 6/6，各 20/20 周期，五个生产报告用例均保留 Viewer 和 Python 草稿。macOS 仍以同头官方工件和本地修订记录为准。 [新头 Desktop](https://github.com/sijintech/stk/actions/runs/43491122224) [新头 Runtime](https://github.com/sijintech/stk/actions/runs/43491121980) [新头 Pages](https://github.com/sijintech/stk/actions/runs/43491121988) [Windows 工件](https://github.com/sijintech/stk/actions/runs/43481451563/artifacts/14069047795)

Claude 114 已从发布头在独立 `claude/synthrix-workbench-acceptance-114` 启动，负责对照 Synthrix 已发布主页与双端现状，提交下一项减少操作的验收方案。Claude 113 继续在另一独立工作树开发保存副本；Root 负责主线、集成与实际目标平台验证。开放 PR #53 与 #54 仍为既有冲突和旧交接头。原七份工作区修改均保留。

## 2026-11-13 19:18 UTC · 工作台发布前核验

上一远端 `19998d12097685138b555904fbe880e1a91750f0` 的 Desktop 于 19:18:35 UTC 完成，六项作业中五项通过。Linux 三项、Windows CPU、Windows WebView2 原生文档均成功。macOS CPU 两条窄窗会话测试和必测视频两项失败，具体工件与本地修订见下一节。Runtime 13/13、Pages 和 Secret scan 通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43481451563) [Windows 工件](https://github.com/sijintech/stk/actions/runs/43481451563/artifacts/14069047795) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43481451605)

本次待发布范围截至 `7a78d94916441a298e1fd00a710abe8656f2d5be`，包含双端逐级返回、固定会话详情面板、聚焦智能体会话简化，以及 macOS 测试和诊断修订。Claude 的保存候选仍留在独立 worktree。原四份状态文档与三份 AOCI 工作区改动保留。新发布头的目标平台结果待 CI。

## 2026-11-13 19:17 UTC · macOS 会话夹具修正与视频工件复核

远端 `19998d12` 的 macOS 工件 `14067998655` 中，CPU 1612/1614，两个失败均停在窄窗历史菜单，尚未打开任务面板。当前界面在历史条目变更时关闭菜单，原测试点击前只等到智能体列表，未等问答历史。Root 本地 `3ebbb4cd6fc63f2086384d5ea201a6ba07f15558` 固定为已加载历史后再起步，直接核对展开的菜单项，仍验证原 3 次与 5 次点击。Linux 连续 5 轮共 10/10，智能体和已保存会话联合 48/48。此前同批本地 project 全量 1560/1562，余两项首跑缺已安装 peer helper 路径，设置既有安装路径后定向 2/2。暂存 gitleaks 零发现。新头 macOS 待验。

同一官方 macOS 工件 Metal 254/254，必测原生 4/6。MP4 与 HTML 视频均在首轮工具栏暂停低于验收下限，分别由 0.10777 到 0.03657 秒和由 0.11394 到 0.04708 秒。可选帧号对照的 MP4 持续播放取到帧 1，暂停取到帧 0、0，来自独立会话且取图时延不同。HTML 两组都因 320×180 元素超出 385×159 视口无有效帧号。`3ebbb4cd` 仅对首次工具栏的两个 HTML 帧号夹具设置 208×117，保留必测验收和采样判据。Linux 原生报告测试目标构建通过，修正后的 macOS 截图待跑。证据 `root-delivery-20261113-184/{macos-receipt.json,settled-history-v2.log,agent-final.xml,project-full.xml,project-peer-retry.xml,marker-geometry-build.log}`。 [官方 macOS 工件](https://github.com/sijintech/stk/actions/runs/43481451563/artifacts/14067998655)

上一远端的 Linux 三项、Windows CPU 与 Runtime 通过，最后一项 Windows 原生文档仍在运行。Claude 113 保存副本候选还未提交，隔离构建的全量运行正在暴露缺 `psutil` 的本地配置，Root 继续以真实窗口与明确文件边界验收。发布前 AOCI 0.1.0-rc21 返回 `stopped/blocked`、零候选、94 条待复核观察，无 Recovery。三份既有 AOCI 改动摘要一致。 [桌面 CI](https://github.com/sijintech/stk/actions/runs/43481451563)

## 2026-11-13 19:05 UTC · 聚焦智能体会话默认收起会话管理

本地 main `e2fd284c61b41ce65d18b40604b3a0951f60c4a9` 将完整会话选择器、刷新及规划模型信息收进「智能体会话」展开区。当前会话标题与正文直接显示，模型不可用原因在输入和发送附近，用量移入「记录」。定向 48/48，桌面与项目测试目标构建通过，暂存 gitleaks 零发现。

Linux X11 固定起点为已打开合成项目的聚焦工作台和已存在的智能体会话。英文 1600×1100 从左栏一次打开，中文 680×1000 经历史两次打开。完整会话列表展开、收起各一次，零 Bridge 请求。之后从同一会话到关联任务、冻结清单各一次，按一次 Esc 关闭。各一条会话路线、会话详情、工作流和快照清单读取。项目数据库、修订和会话哈希一致。界面驱动另外核对展开与收起保留草稿和会话。证据 `root-delivery-20261113-182/native-save-baseline-agent-slim{,-narrow}/receipt.json`、`root-delivery-20261113-183/agent-layout.xml`。 [统一工作台](design/unified-workbench.md)

Claude 113 的未提交 Linux 二进制在真实 X11 加 Bridge 的英文宽窗选择器路线和中文窄窗页内路径都验证了取消及同名不覆盖，两个新目标都与 60 字节冻结源摘要一致。两条路线各只在明确新目标后解析一次快照。两份副本模式均为 0664，权限断言失败，保存候选继续修订。该轮作者全量运行也观察到其独立构建的 Python 缺 `psutil`。暂未集成。远端 `19998d12` 的 Linux 三项、Windows CPU 和 Runtime 已通过。macOS、Windows 原生文档仍在运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43481451563) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43481451605)

## 2026-11-13 18:54 UTC · 统一桌面与 Web 的会话详情面板尺寸

本地 main `6a0edca3a2bb2d8c2aefbce2735013b687656e08` 将桌面关联任务、文件清单和预览放在同一个固定边界中。宽窗为 420 逻辑像素的通高右栏，窄窗为占窗口高度 80% 的底部面板。超长内容可滚动，键盘 Tab 会把下一个控件带入可见区域。普通桌面对话框继续按内容布局。桌面与测试目标构建通过，UI 全量 135/135，原生智能体定向 36/36，暂存 gitleaks 零发现。

Linux X11 实窗固定起点为已打开合成项目的聚焦工作台，已有一个消费后智能体会话、一个冻结任务结果及 20 个文本文件。英文 1600×1100 从左栏打开第 20 个文件的预览共 4 次点击。中文 680×1000 从历史进入共 5 次。两窗逐级返回各 1 次，再按一次 Esc 关闭。三个层级在各自窗口的面板边界一致，分别为 420×1100 和 680×800。只发一次工作流详情、一次冻结清单及一次冻结字节解析，返回和关闭零读取。项目数据库、修订、会话哈希及源文件摘要一致。长内容的滚轮、键盘与裁切由 UI 测试覆盖。证据 `root-delivery-20261113-182/{ui-full.xml,project-panel.xml,native-save-preview-panel-wide/receipt.json,native-save-preview-panel-narrow/receipt.json}`。

保存副本的 Linux 真实窗口夹具已具备桌面选择器与页内路径两条路径，主线宽窄窗基线通过。Claude 113 独立候选的第一轮定向 43/43，审查复现的临时文件问题仍待修正和重新验收。远端 `19998d12` 的 Desktop Linux 三项均成功，Windows 与 macOS 仍在运行。Runtime 已 13/13 完成。开放 PR #53、#54 头未变。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43481451563) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43481451605)

## 2026-11-13 18:41 UTC · Web 与桌面文件预览统一逐级返回

本地 main `47caad379b90173d1e9c14b99dcc01292015b75f` 将 Web 预览标题与桌面对齐为「文件预览」。同一面板逐级显示关联任务、发布文件和文件预览。预览层显示「返回发布文件」与「关闭」，文件层提供「返回关联任务」。返回恢复上一级的打开控件焦点，关闭恢复会话中的入口。

Chromium 1440×900 和 390×844，固定起点为已打开合成会话、关联任务未展开、已有未发送草稿。两窗从关联任务到发布文件、再到文本预览，各 1 次点击，共 3 次。返回文件和任务各 1 次，随后 Esc 关闭。对照修复前的两窗用例均因预览仍名为「发布文件」失败。修复后宽窄窗 2/2，Web 生产构建通过，全量 395/395，零失败或跳过。逐级返回保留焦点、会话状态和草稿，无 POST。暂存 gitleaks 零发现。浏览器使用受控 Hub 响应，桌面真实 Bridge 宽窄窗验收沿用上一条。证据 `root-delivery-20261113-181/{web.xml,web-full.xml,green/}`。 [统一工作台](design/unified-workbench.md)

Claude 113 继续在独立 worktree 实现桌面保存副本。Root 用合成文件复现早期候选的两个问题：umask 0022 下临时文件为 0644，替换临时文件名后可发布符号链接。修正与重测留在候选集成前。远端仍为 `19998d12`，Desktop 的 Linux 打包与干净机冒烟通过，Linux 主回归、Windows、macOS 尚在运行。Runtime 12 项已通过，余 1 项运行中。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43481451563) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43481451605)

## 2026-11-13 18:32 UTC · 桌面文件按静态文本阅读

本地 main `2986df6ea9b8e9f8fb9b4360157bf0de1bfdf4cf` 让冻结文本预览从首行显示，去掉流式日志的「跟随最新」控件。键盘焦点有可见边界，翻页和回到开头继续可用。桌面与测试目标构建通过，文本视图、模态、智能体与工作台导航联合 59/59，暂存 gitleaks 零发现。

真实 Linux X11 以已打开合成项目的聚焦工作台及已有智能体会话为起点。英文 1600×1100 点击 4 次进入预览，中文 680×1000 点击 5 次。预览仍显示冻结 JSON 原文，两窗截图均无跟随控件。各按 Esc 一次关闭。各一次工作流、清单及预览读取，关闭零读取，项目数据库、会话哈希和两份源文件字节一致。证据 `root-delivery-20261113-180/{static-preview.xml,native-preview-en-static/receipt.json,native-preview-zh_CN-static/receipt.json}`。

远端仍为 `19998d12`。Desktop 的 Linux 打包和干净机冒烟通过，Linux 主回归、macOS 和 Windows 正在运行。Runtime 仍在运行，Pages 与 Secret scan 已通过。两条旧 PR 头未变化，保持开放。Claude 113 在独立 worktree 已有保存副本的原子发布及 UI 候选改动，继续开发验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43481451563) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43481451605)

## 2026-11-13 18:25 UTC · macOS 官方工件与桌面预览全量回归

上一远端 `57f3601a` 的 macOS 工件已取回。CPU 1597/1597、Metal 254/254、原生必测 4/6。MP4 与 HTML 视频的首次显式暂停均通过当次下限及保持，保持末尾分别为 0.05307 秒和 0.06400 秒。MP4 完成第一轮，在第二轮第一次向早段 seek 时未找到可见原生子视图，未发送该次 seek。HTML 在第一轮隐藏后的首个暂停样本由播放时 0.20708 秒降到 0.102 秒，等于此前 seek 的落点，只失败于隐藏时间下限。立即暂停的独立对照中，MP4 三个样本稳定在 0.04219 秒，HTML 稳定在 0.10863 秒。延迟对照两项通过。这些分支分别保留为取证目标。

本地 main `182506b803f94c4a5d364ff23b1fff2ce666dc6e` 在 Cocoa 原生时间轴操作失败时记录实际和预期视口、裁切、当前覆盖层、输入状态以及导航所用布局和会话是否仍有效。沿用原来的查询次数、预算、输入目标与验收门。Linux 报告测试目标构建通过，文档宿主和原生 AX CPU 15/15。Cocoa 条件 C++ 语法检查通过，真实目标平台复现仍待跑。暂存 gitleaks 零发现。证据 `root-delivery-20261113-179/{macos-57f3601a-receipt.json,report-host.xml,cocoa-syntax.log}`。 [官方 macOS 工件](https://github.com/sijintech/stk/actions/runs/43470699822/artifacts/14065611207)

Claude 112 独立交付 `be12e26dff099b45e2f0b275e74efd1b5d43b24a`。六份源码与已集成候选一致，完整项目回归 1000/1000。原生预览已在远端 `19998d12`，其 Pages 与 Secret scan 成功，Desktop 与 Runtime 仍在运行。Claude 113 继续在独立 worktree 开发显式保存副本。 [Pages](https://github.com/sijintech/stk/actions/runs/43481451519) [Desktop CI](https://github.com/sijintech/stk/actions/runs/43481451563) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43481451605)

## 2026-11-13 18:19 UTC · 发布双端会话详情与文件预览

Root 将 `main` 从 `57f3601a1c214db81e0e8a80aa26b86f85c666ed` 快进至 `19998d12097685138b555904fbe880e1a91750f0`，推送后单独核对远端。16 个提交 gitleaks 零发现。发布包含 Web 文本预览、桌面关联任务与冻结文本预览、居中会话和键盘焦点、传输重试契约以及 macOS 首次暂停帧标记诊断。仓库中原七份未提交内容保留。

新头 Secret scan 通过，Desktop、Runtime 与 Pages 正在运行。Claude 112 的定向 47/47、Root 集成 60/60、真实 Linux 宽窄窗文件路径已验。Claude 113 在独立 worktree 继续原生文件保存。旧 PR #53 的重试契约已随此批主线发布，两条旧 PR 仍开放。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43481451563) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43481451605) [Pages](https://github.com/sijintech/stk/actions/runs/43481451519) [Secret scan](https://github.com/sijintech/stk/actions/runs/43481451487)

## 2026-11-13 18:17 UTC · 原生会话冻结文件预览与发布门禁

本地 main `8894b2f5087a65d6986749383289d488cf0fae5d` 纳入 Claude 112 独立候选。在关联任务中，明确点击「查看文件」读取所选任务的冻结快照清单。明确点击「预览」后核对记录、长度、SHA-256 和实际 UTF-8 字节。预览上限 256 KiB，内容按纯文本显示。Root 保留面板初始焦点，补齐逐级返回后旧控件回调的失效校验。集成定向 60/60，双语目录各 3004 键校验通过，暂存 gitleaks 零发现。Claude 独立定向 47/47，完整项目回归仍在运行。

Linux X11、真实桌面与项目 Bridge。固定起点为已打开合成项目的聚焦工作台，已有一条已消费的智能体会话。英文 1600×1100 从左栏到文本预览 4 次点击，中文 680×1000 经历史菜单 5 次。逐级返回各 1 次，最后关闭按钮或 Esc 1 次。两窗都显示冻结的 60 字节 JSON，原文件在验收前已改写，内嵌 HTML 标签仍显示为字符。各一次工作流、快照清单及预览读取，返回与关闭零读取。会话哈希、项目修订 5、数据库、源文件和快照字节前后一致。证据 `root-delivery-20261113-178/{integration.xml,native-preview-en-integrated/receipt.json,native-preview-zh_CN-integrated/receipt.json}`。

上一远端 `57f3601a1c214db81e0e8a80aa26b86f85c666ed` 的 Desktop 于 18:17:03 UTC 完成，6 项中 5 项通过。Windows 原生 WebView2 与 Linux 三项、Windows CPU 均通过。macOS 构建、CPU、Metal、应用冒烟和首次工具栏对照通过，必测原生文档步骤失败。Windows 工件下载遇到 TLS `bad record MAC`，通过 GitHub 作业回执确认原生步骤通过。该终态满足仓库推送门禁。Claude 113 已在独立 worktree 开发显式保存副本。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43470699822) [macOS 工件](https://github.com/sijintech/stk/actions/runs/43470699822/artifacts/14065611207) [Windows 工件](https://github.com/sijintech/stk/actions/runs/43470699822/artifacts/14065485358)

## 2026-11-13 18:06 UTC · 关联任务键盘焦点与传输契约

本地 main `ed60da0db646ff41f7014c35d3457bb7a50ad07c` 将桌面关联任务面板打开时的焦点移到关闭按钮，与 Web 对齐。只允许最上层面板中的可见控件取得这个焦点。关闭后回到原卡片。UI core、原生智能体与工作台导航 51/51。Linux X11 实窗英文 1600×1100，固定起点为已打开合成项目的聚焦工作台，Viewer 预置公开网格。两次点击从左栏会话打开详情，直接按 Enter 一次关闭，零 Tab、零滚动。前后正文像素取样一致，项目数据库、会话哈希、产物摘要一致。只发一次详情读取，另有进入会话所需的 route/get。证据 `root-delivery-20261113-177/{modal.xml,native-linked-en-modal-focus/receipt.json}`。

复核 PR #53 `c9f13994` 的文档意图，按主线实际实现将重试时序补入 Bridge v1 `0cea0fe7`。已有实现会等待前一 worker 最长 5 秒，超时返回可重试 busy，等待同一 worker 的并发请求复用继任尝试。传输生命周期 35/35。原 PR 仍为冲突状态，主线代码与更新后的契约覆盖其问题。PR #54 `2dd3e4ee` 仍为旧的 `HANDOFF.md`，当前交接使用 `handoff.md`。两个提交的暂存 gitleaks 均零发现。

Claude 112 在独立工作树的文件预览定向第二轮 36/36，仍在做最终候选验证。上一远端 `57f3601a` 的 macOS、Windows 原生文档均已进入目标平台测试，整个 Desktop 仍在运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43470699822)

## 2026-11-13 17:58 UTC · macOS 首次暂停帧标记对照

本地 main `170dadb8c926eb6979e936d5e0c59e5c2ea2510c` 接通 Claude 111 取证提案的独立帧标记对照。MP4 与 HTML 各有持续播放和立即暂停两组。持续播放从首次 Play 返回后开始取图。立即暂停使用原工具栏点击和三次 DOM 采样，完成后才取图。结果包含截图请求与完成时刻、解码帧号、原导航代数和图片摘要。采集缺失或画面无法判定保留为不确定。两组属于独立会话，比较只能支持或削弱假设。六项生产原生门禁及原有二十轮不变。

Linux `stk-reports-native-window` 构建通过，文档宿主与原生 AX CPU 15/15。使用 Linux 头对 Cocoa 条件路径做 C++ 语法检查通过。四个可选用例与上传路径已和 CMake、CI 交叉核对，暂存 gitleaks 零发现。真机帧标记证据待新头 Desktop CI。证据 `root-delivery-20261113-176/{native-exact-build.log,report-host-exact.xml,cocoa-cxx-exact-syntax.log}`。

远端仍为 `57f3601a`，其 Desktop 的 macOS 构建、CPU、Metal 已通过，打包及原生媒体尚未结束，Windows 原生文档正在运行。复核开放 PR #53 和 #54 仍为原旧头，保留开放。Claude 112 在独立工作树已有文件清单、文本预览与测试改动，候选尚未交付。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43470699822) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43470699712)

## 2026-11-13 17:49 UTC · 桌面智能体会话居中与真实窗口验收

本地 main `cfaf8c1816f5e66c81ef1cab97239206eaf06aa4` 让聚焦工作台中的智能体会话复用项目问答的 880 逻辑像素居中正文列，文本按实际列宽折行。窄窗随可用宽度排列。桌面应用和项目测试目标构建完成，导航、智能体和文献入口联合 51/51，暂存 gitleaks 零发现。首轮新增布局断言未计入 7 像素滚动条，修正验收容差后通过。

Linux X11/Xvfb、llvmpipe OpenGL、缩放 1、真实桌面与项目 Bridge。固定起点为已打开合成项目的聚焦工作台，左栏或历史菜单已有一条已消费的智能体会话，Viewer 预置公开网格。英文 1600×1100 从左栏到关联任务 2 次点击，右侧面板用关闭按钮收起 1 次。中文 680×1000 从「历史」到关联任务 3 次点击，底部覆盖层用 Esc 收起 1 次。两窗都显示该项目的冻结快照及 `metrics.json`，收起前后正文取样像素一致。各一次 `project.workflow_runs.get`，另有进入会话所需的 route/get。数据库字节、项目修订 5、会话哈希链、任务状态和产物摘要一致，测量内零执行、零发送。焦点与 Viewer 状态另由同头界面驱动验证。证据 `root-delivery-20261113-175/{centered-final.xml,native-linked-en-centered/verified-receipt.json,native-linked-zh_CN-centered/verified-receipt.json}`。

Claude 111 的独立 `228af77d` 纳入 `46f405f3`，Root 在 `3cc959a4` 明确跨会话和离散采样只能支持假设。该文记录 macOS 官方工件取证与下一项帧标记对照。真实 macOS 验证待跑。Claude 112 已在独立 worktree 实现同一详情面板中的冻结文件清单和文本预览，尚未交付。下载仍待接入。

远端 `57f3601a` 的 Runtime 13/13 成功，Desktop 的 Linux 三项及 Windows CPU 通过，macOS 与 Windows 原生文档验收仍在运行。PR #53 和 #54 复核后仍分别为 DIRTY、UNSTABLE。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/43470699712) [Desktop CI](https://github.com/sijintech/stk/actions/runs/43470699822)

## 2026-11-13 17:36 UTC · 原生会话关联任务

本地 main `5ae6507372adde77bae2b495bec9ac30fb8e0772` 纳入 Claude 独立工作树的 `ca4ea773`、`a415e414`。已消费的智能体运行卡片可以打开「关联任务」。详情只读当前项目的工作流状态、冻结快照与产物名称。宽窗沿用 Web 的右侧面板，700 逻辑像素及以下为底部覆盖层。Root 补齐项目打开或关闭发出后的作用域校验、编辑器移动与重开详情后的过期回调围栏。

固定起点为桌面界面驱动中已打开合成项目、Bridge 已就绪的聚焦工作台。英文 1600×1100 从左栏会话 A 到详情共 2 次点击。中文 680×1000 从「历史」经会话 A 到详情共 3 次。两窗各一次 Esc 或点击关闭后恢复原卡片焦点。单次打开只发一个 `project.workflow_runs.get`。会话哈希链、项目修订、草稿、Viewer 相机及分栏布局保持。覆盖项目、会话、卡片变化和旧回执丢弃。原生文件预览、下载、普通问答引用和本片真实桌面窗口回放待接。

Claude 独立候选全项目 991/991、定向 27/27。Root 集成后重新构建，定向 27/27，双语各 2983 条校验通过，暂存 gitleaks 零发现。证据 `root-delivery-20261113-174/{build-exact.log,native-detail-exact.xml}` 与 Claude 110 工作树 `build/evidence/candidate-full-project-tests.log`。AOCI 收尾仍在 94 条观察证据审阅门返回 `stopped/blocked`、零候选、无 Recovery。三份既有 AOCI 改动摘要一致。

远端仍为 `57f3601a`。Pages 和 Secret scan 通过，Desktop 与 Runtime 仍在运行。PR #53 与 #54 的精确旧头未变，均保持开放。Claude 111 已在独立工作树核对 macOS 首次暂停的官方回执。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43470699822) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43470699712)

## 2026-11-13 17:21 UTC · 会话内文本预览

本地 main `1ed52816271bf24f17ec2f4128ed0fa0a3e36e6f` 为发布清单加入小型 UTF-8 文本预览。明确点击后走已发布的校验文件接口，核对大小和摘要后按纯文本显示。预览上限 256 KiB。返回后恢复文件清单的滚动及触发按钮。其他格式沿用现有下载。

最终生产构建通过，Chromium 全套 395/395，宽窄定向 4/4。测试覆盖 HTML 标记只作为文本、二进制保留下载、原清单焦点恢复。真实 loopback Hub、NodeAgent 和 Runtime 在 Chromium 1440×900 和 390×844，各从已保存会话及未发送草稿起步，1 次关联任务、1 次查看文件、1 次预览、1 次返回文件清单。两窗均显示任务发布的合成日志，焦点返回预览入口，合计各三个 GET、零 POST。任务、产物和操作列表一致，模型调用零。证据 `root-delivery-20261113-173/{web-preview,web-preview-full.log,real-preview-1440.json,real-preview-390.json,real-preview-runtime.json}`。

远端 `57f3601a` 的 Pages 部署及 Secret scan 已成功。Desktop 和 Runtime 仍在运行。Claude 110 独立构建已通过，原生详情及相关会话定向 27/27，全项目用例仍在跑。待作者冻结后由 Root 审查与集成。 [Pages](https://github.com/sijintech/stk/actions/runs/43470699724) [Desktop CI](https://github.com/sijintech/stk/actions/runs/43470699822) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43470699712)

## 2026-11-13 17:14 UTC · 发布统一首页与会话文件到 main

Root 将远端 main 从 `6ed5e920d8ecbb64a826684bd4190a0540dbbd50` 快进到 `57f3601a1c214db81e0e8a80aa26b86f85c666ed`，推送后单独核对远端完整 SHA。12 个提交扫描零发现。发布包含两端会话首页简化、Web 会话关联任务、文件清单与校验下载，以及原生报告首次暂停的附加取证。Web 395/395、Hub 95/95、桌面导航 26/26、报告宿主 14/14。原 AOCI 和状态文档工作区的既有改动保留。

新头 Desktop、Runtime、Secret scan 和 Pages 都已触发。Claude 110 原生关联任务详情仍在独立工作树验证。复核旧 PR #53 与 #54，头分别为 `c9f13994` 和 `2dd3e4ee`，继续开放。前者的当前传输生命周期及关闭回归 44/44。AOCI 观察证据审阅门仍有 94 条，未改动正式索引。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43470699822) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43470699712) [Secret scan](https://github.com/sijintech/stk/actions/runs/43470699680) [Pages](https://github.com/sijintech/stk/actions/runs/43470699724)

## 2026-11-13 17:13 UTC · 上一轮 Desktop 终态

远端 `6ed5e920d8ecbb64a826684bd4190a0540dbbd50` 的 Desktop `43458144964` 于 17:12:42 UTC 结束，5/6 作业通过。Linux 三项、Windows CPU 1537/1537、Windows 原生文档验收均通过。macOS 作业失败，CPU 与 Metal 通过，必测原生 4/6。正式 Windows 工件 `14061160879` 已发布，详细清单待核对。此终态满足仓库推送门禁。待发布提交包括会话首页、Web 会话任务与文件下载、首次暂停取证。Claude 110 的原生详情候选仍在独立验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43458144964) [Windows 工件](https://github.com/sijintech/stk/actions/runs/43458144964/artifacts/14061160879)

## 2026-11-13 17:07 UTC · 首次暂停时钟诊断

本地 main `88e9a82bcd20c101ef4a16ee098238b94e0870a6` 在原生报告测试的首次显式暂停段保存既有 DOM 探测的时钟和同一 250 ms 保持区间结束时的最后回执。保持断言失败时也保留最后样本。原有阈值、探测次数与暂停行为照常。Linux 报告原生测试目标构建通过，文档宿主 14/14。Apple 真机回执待下一轮 CI。

前一远端 `6ed5e920` 的两组单次工具栏对照均取得证据。MP4 的立即暂停样本从 0.10634 秒降到 0.03493 秒，后两次采样均为 0.03493 秒。HTML 视频立即暂停的三次样本均为 0.05946 秒。270 ms 被动等待后，两种视频均稳定在 0.24 秒以上。现有证据同时覆盖首次采样已回退与首次采样通过、随后回退两种表现，仍需解码帧证据验证实际播放位置。Windows 原生文档作业仍在运行。两条旧 PR 的头与状态不变。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43458144964) [macOS 工件](https://github.com/sijintech/stk/actions/runs/43458144964/artifacts/14059246912)

## 2026-11-13 17:01 UTC · 会话下载回归终态

最终下载构建的 Web 全量 395/395。AOCI 稳定源码维护仍停在 94 条待审观察证据，零候选且无待恢复事务，已有正式资产的工作区摘要一致。前一远端 Desktop 的 Windows 原生文档仍在运行，待整轮终态再推送。

## 2026-11-13 17:00 UTC · 会话文件下载与 macOS 原生回执

本地 main `ee765184a19a522c3ab2356d50e19828d16b8c07` 接通 Web 会话文件下载。Hub 重新读当前任务的发布清单，以明确选择的路径与 SHA-256 核对来源。沿用授权的节点读取，逐块验证偏移与长度，完整摘要匹配后才返回附件。浏览器再次核对长度和摘要再保存。文件上限 64 MiB，关闭页面或返回任务会撤销客户端读取。

Hub 全量 95/95，含真实 Runtime 下载、摘要失配、分块偏移及读取途中撤权。Web 最终定向 4/4，包含伪造字节被拒、正确字节保存和焦点恢复。真实 loopback Hub、NodeAgent、Runtime 和 Chromium 的 1440×900、390×844，从已打开合成会话及草稿起步，各一次打开关联任务、一次打开文件、一次下载、一次返回和一次 Esc。两窗均下载 22230 字节，SHA-256 与发布记录一致。每窗三个 GET、零 POST，任务、产物与操作列表不变，模型调用零。全量 Web 正在运行。证据 `root-delivery-20261113-173/{hub-final.xml,web-exact,real-files-1440.json,real-files-390.json,real-files-runtime.json}`。

远端 `6ed5e920` 的 macOS 工件 `14059246912` 已核对。CPU 1597/1597、Metal 254/254、必测原生 4/6。MP4 与 HTML 视频都在可见的首次显式暂停阶段失败，较早于此前的隐藏阶段。两个回执均收到原生暂停确认，只有 0.05 秒下限失败，观测分别由 0.10535 降到 0.03728 秒、由 0.10089 降到 0.03291 秒。普通静默 2/2、隔离静默 0/2、挂起期间追加暂停 1/1。Windows CPU 和 Linux 三项均通过，Windows 原生 20 轮仍在运行。Claude 110 独立工作树已有原生候选改动，仍在开发及验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43458144964) [macOS 工件](https://github.com/sijintech/stk/actions/runs/43458144964/artifacts/14059246912)

## 2026-11-13 16:52 UTC · 会话文件回归终态

会话文件版本 Chromium 全量 395/395。最终滚动恢复和路径显示的构建另有 4/4 定向与真实两窗回放。稳定源码的 AOCI 维护返回 `stopped/blocked`、零候选，待审观察证据仍为 94 条。原正式索引与基线的既有修改摘要一致。前一远端 Desktop 的 Windows 原生文档和 macOS 诊断仍在运行。

## 2026-11-13 16:50 UTC · 会话内发布文件清单

本地 main `cff5933bade2b4809f16367fa1cacd334841dd32` 接通 Web 的「关联任务 → 查看文件」。Hub 用保存的会话和操作 ID 解析唯一 Runtime 任务，复用节点实时读路径与回执前撤权检查。响应返回发布路径、大小与摘要，前 200 条有界。切回任务后还原面板滚动和入口焦点，离开后丢弃迟到回执。当前交付是只读清单。

真实 loopback Hub、NodeAgent、Runtime 和 Chromium 固定起点为已配对、已打开合成会话，输入区有未发送草稿，真实合成任务已成功。1440×900 与 390×844 各 1 次打开关联任务、1 次查看文件、1 次返回关联任务、1 次 Esc 关闭。两窗都显示发布的 3 个文件，回到原入口且草稿保留。各 2 个 GET、零 POST。Runtime 任务、产物与 Hub 操作列表一致，零模型调用。最终生产构建与定向 4/4，Hub 全套 94/94，最终路径校验改用 Runtime 校验器后定向 11/11。全量 Web 在进行。证据 `root-delivery-20261113-172/{real-files-1440.json,real-files-390.json,real-files-runtime.json,web-files-exact,hub-files-final.xml,hub-files-exact.xml}`。

前一远端 `6ed5e920` 的 Linux 三项和 Windows CPU 已通过。macOS 已通过构建、CPU、Metal、打包和冒烟，生产原生报告步骤仍失败，诊断在运行。Windows 原生文档验收正在运行。Claude 110 仍在独立 `claude/native-conversation-run-detail-110` 开发。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43458144964)

## 2026-11-13 16:42 UTC · Web 会话关联任务

本地 main `d137f31d4805acba997695b0c83395a5cfc23b6f` 增加会话任务详情。Hub 同事务保存回复、该回复创建的任务操作和结构化关联，节点返回同一运行工作区的有效任务 ID 后才补入关联。已配对客户端可在当前已保存会话明确打开，只读一次任务列表。旧会话保留原记录，旧 Hub 的缺失路由给出明确提示。Web 宽窗为右侧面板，窄窗为覆盖层。关闭后焦点回到入口，迟到回执丢弃。

Hub 全套 94/94，含真实合成 NodeAgent 和 Runtime 回执、拒绝、跨会话隔离、无关操作、错误工作区及撤权用例。Web 生产构建成功，最终定向 4/4。固定起点为已配对、已有已选任务、任务和会话草稿、移动过相机的 Viewer，以及打开的合成会话。Chromium 1440×900 与 390×844 各一次打开、一次关闭，分别验 Esc 和按钮。任务来源正确，草稿、选中任务和原画布保持，测量内零 POST。较早的全量运行 393/395，两条结果页用例复跑通过。更新测试的全量 395/395，最后的复核状态文案和回执解析使用独立构建通过定向。证据 `root-delivery-20261113-172/{control-final.xml,web-exact,web-final-full.log,web-rerun}`。

Claude 109 在独立工作树交付 `3e39aa9b17add5ae0be29a248a4d64849dfb9ca4`，Root 核对本地工作流与会话身份后纳入设计。Claude 110 已独立从 `d137f31d` 开发原生读取和响应式详情。文件查看与普通原生问答的任务引用仍待接。Claude 107 的 macOS 诊断说明以 `fdf5cbbc` 合入本地，核对了对应工件、CI 选择和命令语法。复现命令仍待在 macOS 运行。

远端 `6ed5e920` 的 Runtime 和 Secret scan 通过，Desktop 的 Linux 三项通过，Windows 与 macOS 仍在运行。PR 53 与 54 的精确旧头仍分别为 `c9f13994` 和 `2dd3e4ee`，状态 DIRTY 和 UNSTABLE，主线已有相应后续处理。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43458144964) [Runtime CI](https://github.com/sijintech/stk/actions/runs/43458144925)

## 2026-11-13 16:25 UTC · 双端主页的 AOCI 收尾

稳定源码上的 AOCI Maintain 返回 `stopped/blocked`，零候选。Scope 状态为 `observed_evidence_review_required`，有 94 条待审观察证据。保留原正式索引和基线文件，三份既有改动的摘要一致。后续在既有观察证据审阅完成后重开维护计划。

## 2026-11-13 16:23 UTC · 双端会话主页首片

所有者确认 Synthrix 主要页面是 STK 网站和本地客户端共同的设计参照。Root 在本地 main 提交 `6e9a6571471946cbe3c0e7b655a177e66146c77e`。Web 将空白会话提示与输入框居中，已保存会话保留正文独立滚动和底部输入框。桌面聚焦问答用同一首问文案，缺少上下文的原因在准备按钮附近显示，原有明确准备和发送流程继续使用。Root 以发布的 Synthrix `caec2b9` 主页说明及其后续本地侧栏说明为参照。实际 Claude 在独立 `claude/unified-home-acceptance-108` 交付 `2198e76045e5eb35ccf3160377b2e2bb4685f429`，Root 核对并修正了矩阵中首次启动的既有行为。会话内任务和文件详情等待可核验且经授权的引用。

Web 生产构建通过，Chromium 全量 393/393，最终布局用例再跑 2/2。固定起点为中文 1440×900 与 390×844、已配对的模拟 Hub、未发送的新对话。主页零点击可写。打开历史宽窗 1 次、窄窗 2 次，任务往返各 2 次，原草稿和 520 px 阅读位置保留。导航阶段零 POST，显式发送后只有 1 次模拟 POST。桌面 Linux 构建通过，项目导航与文献入口定向 26/26。真实 X11/OpenGL 缩放 1 的英文 1600×1000、中文 680×900 从分栏中打开合成空项目、进入工作台各 2 次点击，进入工作台后零点击显示提示、输入框和缺上下文反馈。两窗没有准备、捕获、发送或模型调用，项目 SQLite 摘要一致。证据 `root-delivery-20261113-171/{web-full.log,web-layout-final,native-project-final.xml,native-home-final-en,native-home-final-zh}`。

远端 `6ed5e920` 的 Desktop 整轮仍在运行，Linux 打包与干净机冒烟已通过。该头 Pages 构建完成，发布步骤失败。首片留在本地 main，等待 Desktop 达到终态再推送。Claude 107 的 macOS 复现说明另待集成。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/43458144964) [Pages CI](https://github.com/sijintech/stk/actions/runs/43458145095)

## 2026-11-13 15:59 UTC · macOS 生产候选与 Pages 失败位置

本地 main `bd4f3c32b3b0e0ff7dbfaa36ae4e2290113d0f62` 按字节集成 Cocoa 候选 `7d3c45bb3acff5d160a9a25ea5c3c369d364f62a`。同一个隐藏请求在本视图持有挂起且首次读到 Suspended 时追加一次原生暂停。暂停回执后沿原看门狗继续读状态，原 1 秒期限、代次校验、独立隔离对照及重显释放规则保留。Linux Reports 构建目标通过，文档模块回归 44/44。生产 Cocoa 代码尚待 macOS 编译和真机回放。上一次触发的 Desktop `42986687264` 已于 11 月 11 日 09:33:30 UTC 终态，5/6，唯一失败为已记录的 macOS 两个必测视频。中间 `c04b48a0` 只涉及 Web 与文档，未触发 Desktop。Claude 107 继续独立整理复现说明。 [上轮 Desktop CI](https://github.com/sijintech/stk/actions/runs/42986687264)

Pages `43456596160` 的重跑在 `GET /accounts/***/pages/projects/stk` 收到 HTTP 503，早于资源上传和部署创建。Wrangler 3.15.0 将无法解析的返回体报告为 malformed response。文档构建成功。证据 `root-delivery-20261113-170/pages-endpoint-summary.log`。 [Pages CI](https://github.com/sijintech/stk/actions/runs/43456596160)

## 2026-11-13 15:56 UTC · 文档发布重跑结果

主线 `c04b48a0` 的 Pages `43456596160` 第二次在 15:54:50 UTC 终态失败。两次 Build 均成功，Publish 均由 Wrangler 报 `Received a malformed response from the API`，当前远端代码已发布，文档站部署未获成功回执。证据 `root-delivery-20261113-169/pages-retry-failed.json` 与 `pages-retry-failure-excerpt.log`。 [Pages CI](https://github.com/sijintech/stk/actions/runs/43456596160)

## 2026-11-13 15:54 UTC · 主线发布与 macOS 生产候选

Root 将远端 main 从 `d4064e5124f7a81e90f257f2580af35b49c555ae` 快进到 `c04b48a02e41185a7baf97ce1798415d94c74269`，推送后独立核对完整 SHA。7 个提交范围扫描无发现。包括 Web 与桌面默认切片一致、Claude 105 进度提示的最终补充及 Claude 106 清空索引后恢复中间层。本次差异是 Web 与文档，Desktop 路径过滤未触发。Runtime `43456596317` 已排队，Secret scan `43456596165` 通过。Pages `43456596160` 首次构建成功，发布阶段收到 Cloudflare API 格式异常，已重跑失败作业。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/43456596317) [Pages](https://github.com/sijintech/stk/actions/runs/43456596160) [Secret scan](https://github.com/sijintech/stk/actions/runs/43456596165)

同一旧头 macOS 工件中，原隔离 MP4 和 HTML 视频均在重显保持中只因 paused 条件失败，退出前最新原生状态为 Playing。追加暂停对照已在同一 runner 通过；仍观察到短暂 Playing，随后转为 Paused。Root 独立候选 `7d3c45bb3acff5d160a9a25ea5c3c369d364f62a` 让生产隐藏暂停在已持有挂起且收到 Suspended 后追加一次原生 Pause，沿原请求、原看门狗及原发布握手。隔离对照继续独立。现有 Linux 文档宿主及资源回归 44/44；此本机环境无法编译或运行 Cocoa，候选仍待 macOS 真机验收。Claude 107 在独立 `claude/macos-media-diagnostics-107` 编写真实工件复现说明，Root 负责生产候选、审阅和发布。旧 PR #53/#54 头不变，状态分别为 DIRTY 与 UNSTABLE。 [旧头 macOS 工件](https://github.com/sijintech/stk/actions/runs/42986687264/artifacts/13842866183)

## 2026-11-13 15:49 UTC · 切片索引恢复中间层与上轮平台终态

本地 main `733583194a8c292cd99c0a75a99eedfed030b964` 合入 Claude 独立 worktree 的索引清空 `b4e5ea9bdeb0745d362310a6ff7e24ee2ed45692`。清空后显示「中间层」，下次明确加载由现有 Runtime 解析。明确输入 0 仍请求第 0 层，半输入状态不发构建。此前 Claude 105 最终头 `e964d48baa596a7b61b77aec00fa7008390b9f00` 相对已发布快照的改动已由 `58cc991f` 和 `6ff29429` 集成，覆盖再次点击「结果」取消在途首开，以及授权和失败时的反馈收尾。

Node 22 组合构建成功，Chromium 393/393、零跳过。1440×900 和 390×844 真实 Hub、NodeAgent 和 Runtime 从选中成功任务、空 Viewer 和两份未提交草稿开始。首开一次点击显示 Z=12，再明确加载一次第 4 层，清空本身零请求，下一次明确加载回到 Z=12。旧版同样路线清空后加载第 0 层。新候选初末网格和画布一致，全程三次明确构建、零额外清单、零模型调用。两个「结果」取消路线及两个构建中返回路线也在组合源码上通过。证据 `root-delivery-20261113-169/full.xml` 和 `root-delivery-20261111-168/clear-{baseline,candidate}`、`review-reopen`。

远端 `d4064e51` 的 Runtime `42986687285` 13/13 成功，Desktop `42986687264` 于 11 月 11 日 09:33:30 UTC 完成，5/6。Linux 2253/2253，打包及干净机冒烟通过。Windows CPU 1537/1537、原生 6/6。macOS CPU 1597/1597、Metal 254/254、必测原生 4/6，MP4 与 HTML 视频仍在隐藏阶段失败。普通静默 2/2，原隔离静默 0/2，新暂停对照 1/1。在同一 MP4 中，隐藏后 82.3 ms 收到追加暂停回执；重显后先观察到 Playing，49.4 ms 观察到 Paused，原 0.50 秒保持与明确播放均通过。该结果支持继续验证播放恢复路径，必测失败仍待解决。已校验官方 ZIP 摘要和所读成员 CRC，汇总 `root-delivery-20261113-169/platform-summary.json`。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42986687264) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42986687264/artifacts/13842866183) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42986687285)

## 2026-11-11 08:34 UTC · Web 和桌面使用同一默认 VTI 切片

本地 main `57cae4fb05bd7ebd85e9b16d94d741f127b20f59` 使 Web 的明确一步打开在未填写索引时采用桌面默认的中间网格层。省略 `view.build.options.index` 沿用已发布 Runtime 计算，按所选轴取该维度除以 2 的整数部分。显式索引含 0 保留，手动首次加载仍使用表单显示值。收到自动绘制回执后核对发布摘要、方向和实际索引。「来源」显示实际绘制的位置，后续表单编辑不会改写已显示位置。未修改运行参数、协议或模型配置。

Node 22 构建通过，Chromium 全套 385/385、零失败与跳过。回归覆盖改轴后默认中点、显式第 0 层、构建在途编辑和错误切片回执。主线与隔离提交 `c3ee5db6ef0dbe2afac8dcfa787a87f85222ec47` 的 HTML、JS、CSS 摘要一致，入口 `f6bb3353ecc1319fa469c40b4f6dc3c4b1e0cbc6ae719a95df85c9b7c4ca6983`。

真实 Hub、NodeAgent 与 Runtime 从已选成功任务、空 Viewer 和两份未提交草稿起步，1440×900、390×844 共十条通过。清单已到或在途都一次点击打开，无额外清单或重复绘制。另用精确主线构建完成两次首开回放。「来源」均显示 Z · 索引 12；与原生宽窄窗实际发送到画面的 896 个 float32 样本按相同网格坐标逐点比较，完全一致，范围 −3.4…19。实测任务及产物不变，模型调用零。使用合成 VTI。证据 `root-delivery-20261111-167/centered-vti` 的 `full.xml`、`centered-trial`、`main-exact` 与 `cross-client-samples.json`。

远端 main 仍为 `d4064e51`，Desktop `42986687264`、Runtime `42986687285` 在运行，Pages `42986687238` 与 Secret scan `42986687229` 通过。Claude 105 的独立执行句柄仍活跃，已采用的进度提示快照仍可复验。旧 PR #53/#54 的精确头不变，继续开放。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42986687264) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42986687285)

## 2026-11-11 08:24 UTC · 主线发布 Web 一步打开与进度反馈

Root 将远端 main 从 `d1eb1467d1f1b1be86b423e466ffcdff59d21612` 快进到 `d4064e5124f7a81e90f257f2580af35b49c555ae`，推送后独立核对远端完整 SHA。8 个提交范围扫描无发现。发布包含 Web 一步打开唯一 VTI、可核对的清单与构建进度、新 macOS 原生暂停对照。原 AOCI 与状态文档工作区修改保留。Claude 105 已冻结、验收并集成的两个文件与当前作者工作树的 SHA 一致，作者最终收尾仍在独立工作树。

新头 Desktop `42986687264`、Runtime `42986687285` 与 Pages `42986687238` 已启动，Secret scan `42986687229` 成功。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42986687264) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42986687285) [Pages](https://github.com/sijintech/stk/actions/runs/42986687238) [Secret scan](https://github.com/sijintech/stk/actions/runs/42986687229)

上一头 Windows 原生工件 `13840270339` 的所选成员通过 CRC，JUnit 6/6、1321 秒。PDF、MP4、HTML 视频各 20/20 轮，图像 160、161、161 张。PDF 1 次创建、427 次复用、已释放，最长初始化 76 毫秒。上轮 macOS 的两个必测媒体失败保留。终态平台汇总在 `root-delivery-20261111-163/published-platform-ci-d1eb1467/platform-terminal-summary.json`。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42978761506/artifacts/13840270339)

## 2026-11-11 08:23 UTC · 上一主线 Desktop 终态与 Web 精确主线回放

`d1eb1467d1f1b1be86b423e466ffcdff59d21612` 的 Desktop `42978761506` 于 08:22:33 UTC 整轮终止，5/6。最后结束的 Windows 原生 `130399062683` 成功，Linux 三项、Windows CPU 成功，唯一失败为已记录的 macOS。原生 Windows 的图像与 JUnit 工件 `13840270339`。上轮终态已独立核对，符合主线推送门禁。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42978761506) [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42978761506/artifacts/13840270339)

另用主线 `5856675e` 构建逐项重放前述宽窄窗十条路线，全部通过。浏览器与真实 Runtime 回执在 `root-delivery-20261111-166/web-result-progress/main-exact`。更新后的文档站 38 页构建成功并产生 Pagefind。

## 2026-11-11 08:17 UTC · Web 结果进度与上一主线 macOS 工件

Root 将 Claude 105 独立工作树的验证快照合入本地 main `5856675ef846669d9eb1d966fe5166646e54602a`。源码和测试与隔离审阅 `b215fb130f09f03516c8a8fc28eba058de0c7643` 一致。Web 沿用原状态位置，显式一步打开时显示「列出结果文件」与「正在加载视图」。来源显示实际所选文件正在加载。离开结果时隐藏进度，返回同一有效选择且原构建仍在进行时恢复。切换任务、范围或文件会使旧提示失效。复核、错误与手动加载保留既有流程。Claude 的最终提交还在独立 worktree 收尾。

Chromium 全套 379/379，零失败、跳过，证据 `root-delivery-20261111-166/web-result-progress/wip-playwright.xml`。主线 Web 构建的 HTML、JS、CSS 与审阅产物摘要一致，入口 SHA256 `95234158cb71db2892467c59783e6a4a3d91926d68527e81b365edc8259e451d`。文档站构建 38 页，Pagefind 产物存在。真实 Hub、NodeAgent、Runtime 在 1440×900、390×844 从确认成功的任务、空 Viewer 和两份未提交草稿开始，基线和候选各十条通过。点击一次开始打开，清单已到或在途均不新增清单请求。先离开清单路线零构建，已发出的构建一次完成。重访保留画面、焦点与草稿。先离开再在原构建返回前重进结果，修订候选恢复加载提示，早期冻结候选在同一路线失败。全部使用合成 VTI，模型调用为零。回放和截图见同目录 `replay.md`、`preview-summary.json`。

远端 `d1eb1467` 的 Desktop `42978761506` 已有 Linux 三项通过，Windows CPU `130383941810` 1537/1537，含 15 项 MuFerro HDF5。macOS `130383941999` 于 08:10:22 UTC 终态失败。CPU 1597/1597、Metal 254/254、必测原生 4/6。MP4 隐藏保持从 0.3376 降到 0.234 秒，HTML 视频首次隐藏读取从 0.2260 降到 0.102 秒。普通静默 2/2，隔离静默 0/2，独立挂起释放 1/1。隔离 MP4 再次在释放回执后先读到原生 Playing，随后同一导航 DOM 回执显示正在播放，断言退出前无 Paused/None。两条普通静默均观察到 Playing 转 Paused 且 DOM 保持通过。隔离 HTML 在隐藏前显式暂停阶段失败。Cocoa 新对照仍待推送后的真实运行。Windows 原生 `130399062683` 尚在运行，整轮终态前不推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42978761506) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42978761506/artifacts/13838464106)

## 2026-11-11 08:00 UTC · Web 与桌面统一唯一 VTI 的打开入口

本地 main 产品提交 `b63019c254d089e67bb765f4670c0c488dd10f61`。Claude 在独立分支交付 `d22b5873f915e4bfd1f3ab99f40b0c53994f8c77`，其单步打开和行为回归随 Root 组合进入主线。Root 复用同范围当前产物读取，保留已有画面和手动刷新。首次打开只采用当前授权及成功任务清单。支持确切任务读取时，须有确切终态。旧版 Hub 仅使用一个显式清单动作，复核或拒绝回执不能打开。画面采用前核对任务、路径和发布摘要；读取能力变动会使在途自动构建的结果失去采用资格。结果页一级导航只切页。源码与独立审阅提交 `4bbd68228fa4b6058c44752915e19da0e9b7953f` 逐字节一致。

Main 和隔离产物的 `index.html`、JavaScript 与 CSS SHA256 清单一致，入口 SHA256 `1383baaeba59ad94f610884487ed4928897ce53da108ab4bb5ac4e95e35253b4`。Node 22 构建及 Chromium 全套 325/325，零失败、跳过，含现代在途清单复用、确切终态替换的两种回执顺序、旧版复核载荷、403、授权来回切换、摘要不符、损坏清单及已有结果刷新。证据 `root-delivery-20261111-165/full-combined.xml`。

1440×900 与 390×844 的真实 Hub、NodeAgent 和 Runtime 共六条通过。固定起点是任务页已选成功任务、空 Viewer 和两份未提交草稿。清单已到或在途时一次点击「在查看器中打开」，均无新增清单请求，实际显示唯一 `scalar-0.vti`。返回和重访各一次点击。返回时恢复原入口焦点及草稿，重访刷新一次清单、零额外构建，画布像素一致。两条先离开路线在工作台保留草稿，释放原回执后零构建。Web 按既有索引 Z=0 打开，896 个切片样本范围 −1…21.4，确切发布摘要 `47e88b30…`。桌面既有默认 Z=12。真实任务及产物未变，零模型调用。证据 `root-delivery-20261111-165/final-real-summary.json`。

Claude 已在独立 `claude/workbench-result-progress-105` 从该产品提交开始整理 Web 等待清单和自动构建的状态反馈，复用既有状态位置。Root 负责审查、主线、真实环境复验、发布和 CI。任务卡 `root-delivery-20261111-165/claude-workbench-result-progress-105.txt`。

远端仍为 `d1eb1467`。Runtime `42978761563` 于 07:45:31 UTC 成功终止，13/13。Linux 3.11、3.12、3.14 分别 6898、6915、6898，PET 各 43/43，Windows 两矩阵各 5503。Desktop Linux 主回归 2253/2253、零跳过，打包和干净机冒烟通过。Desktop 整轮仍在运行，Windows 与 macOS 待终态。PR #53、#54 的头仍分别 `c9f13994`、`2dd3e4ee`，现有开放状态保留。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42978761563) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42978761506)

## 2026-11-11 07:42 UTC · Cocoa 隐藏挂起对照与 Web 产物清单复用

本地 main `c8aa0f0cff5aa80d536bef9054e01884d0888d0b` 按字节集成独立候选 `3362001000e009d69e7c13d0a5630c683a2cca18`。在同轮保留原隔离 MP4 对照，并增加一个可选诊断。生产流程确认自己持有的挂起、同一报告的隐藏暂停和原生 `Suspended` 后，在原有 1.25 秒等待内补发一次 `pauseAllMediaPlayback`。原视图、资源会话、导航、媒体和可见性均匹配且回执早于重显才计入。保留原释放、0.50 秒观察和明确 Play，成功还需原生释放回执和 Paused/None。Linux Reports 测试目标构建成功，资源、探针、宿主 44/44；Reports 测试 C++ 普通、探针与 Apple 条件分支语法检查通过。工作流的命名、选测和归档路径已核对。尚待 macOS 编译及真实运行。证据 `root-delivery-20261111-164/cocoa-suspended-pause`。WebKit 上游会在已中断的会话收到原生 Pause 时将待恢复状态置为 Paused，该代码用于提出对照假设，runner 的系统 WebKit 版本须以实测为准。 [WebKit 会话实现](https://github.com/WebKit/WebKit/blob/f6e529d2cd6c793bc85ddfb7d8c97be33cda9c35/Source/WebCore/platform/audio/PlatformMediaSession.cpp#L368-L376)

真实 Web 回放以 1440×900 和 390×844、已选成功任务、空 Viewer 和两份未提交草稿为固定起点。发布头 `d1eb1467` 的同源构建六条通过。清单已到或在途时，首次点任务「结果」只预选，第二次「加载视图」才绘制。冻结的 Claude 104 未提交中间版能一步绘制，实际宽窗仍多发一次清单请求。Root 在隔离树上验证同连接和任务的现有成功清单可由显式打开复用，保留最新终态、授权和导航检查。试验提交 `e458c0a42f2ee9579e6cd877c7ddea3317d9d129`，入口 SHA256 `6b65ac65cae219c06895106b32efe87307da6839bf998a6a5eb25d88ec9633a8`。

组合试验六条实窗通过。清单已到和仍在途各两窗，点击一次打开精确 `scalar-0.vti`，首次和重访均零新增清单、全程一次 `view.build`。一次返回原任务恢复启动按钮焦点及两份草稿，重访画布像素一致。两条离开路线先回工作台，释放真实清单后继续停在原页，查看结果仍为空且零构建。回执核对发布摘要 `47e88b30…`、Z=0 的 896 个样本和范围 −1…21.4；桌面默认 Z=12。全程零模型调用，真实任务和产物未变。证据 `root-delivery-20261111-164/web-vti-real` 的 `baseline-summary.json`、`claude-wip-ready.log`、`root-coalescing-summary.json`。仍待 Claude 104 定稿、旧 Hub 与权限和终态替换回归、组合全测及集成。

远端 main 仍为 `d1eb1467`，Desktop `42978761506` 和 Runtime `42978761563` 整轮均在运行。Linux 打包及干净机冒烟通过，Runtime 两个 Windows Python 版本各 5503 通过。当前候选留在本地，待前轮 Desktop 整轮终态再推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42978761506) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42978761563)

## 2026-11-11 07:22 UTC · 主线发布与 Web 唯一 VTI 路径

Root 将远端 main 从 `8a9da1313fd4c4cef3f01e17afef9d1285feb7d8` 快进到 `d1eb1467d1f1b1be86b423e466ffcdff59d21612`，独立复核远端完整 SHA。发布 10 个提交，范围扫描无发现。包含桌面返回原任务标签及一次打开唯一发布 VTI、Web 标准输出及错误续读、进度与原始值顺序回归。Root 定向原生 87/87，Web 269/269。既有 AOCI 与状态文档工作区修改保留。

新头 Secret scan 和 Pages 已成功。Desktop `42978761506` 与 Runtime `42978761563` 已启动，待整轮终态。上一头 Desktop 的 macOS MP4 和 HTML 视频隐藏恢复两例仍失败。旧 PR #53 和 #54 分别保持 `c9f13994` 与 `2dd3e4ee`，继续开放。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42978761506) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42978761563) [Pages](https://github.com/sijintech/stk/actions/runs/42978761468) [Secret scan](https://github.com/sijintech/stk/actions/runs/42978761425)

Claude 已从这次发布头在独立分支 `claude/workbench-web-single-vti-104` 开始处理 Web 成功任务的明确一步打开，范围为 Web 任务入口与对应回归。Root 负责两端行为审阅、真实 Runtime 浏览器验收、最终集成和 CI。当前发布的 Web 路径仍为预选后明确加载。任务卡在 `root-delivery-20261111-163/claude-web-single-vti-104.txt`。

## 2026-11-11 07:19 UTC · 原生任务一次打开唯一发布的 VTI

本地 main 产品提交 `35ff2d1d866cad4b2f0449dc6e793c9e7b315d11` 集成 Claude 独立 worktree `claude/workbench-native-task-artifact-103` 的清单解析 `2b5341dd4b4942ebc3c02e91cecc1ab547e5177a`。Root 接上 Viewer 的固定产物绑定、打开时的页面及意图检查、Bridge 重启清单失效和对应回归。成功任务清单只含一个合格 VTI 及可忽略的日志或说明文件时，「在查看器中打开」直接显示切片。多个或其它类型结果使用既有任务入口。Web 仍从任务捷径预选唯一文件，再由用户明确加载。

Main 构建桌面、Jobs 与 Viewer 目标成功。聚焦 Jobs / Viewer 回归 87/87，含选中任务及连接变化、重启和拒绝授权。隔离组合的同源目标也为 87/87。最新 main X11 二进制 SHA256 `70f345f39ed58b9e076b332bd78e9b00e2ab3034418ee99e96912b7ef3416e06`。英文 1600×1100 与中文 680×1000 从已选成功任务、已到清单、冷 Viewer、未提交表单起步。打开、返回原任务、重访分别 1、1、1 点击。回到 Tasks 后仍显示原草稿。两端尺寸下实际读取 `scalar-0.vti`，SHA256 与发布清单一致，显示 `32×28` 的 `manufactured` 切片及范围 −3.4…19，「来源」列出实际文件。重访画布相同，全程一次清单和一次图求值，零模型调用、零任务提交，Runtime 任务与产物不变。截图及回执在本机 `root-delivery-20261111-162/native-vti-window/window-main-ready-{en,zh}`。

同一份桌面产品源码的审阅构建 `ab89627a` 另做四条真实清单在途路线。两种窗口均只使用原请求，显示相应语言的「列出结果文件」。等待后继续只需原先一次点击。释放回执前切到工作台时保持工作台，零图求值，手动查看 Results 仍为空。对照见同目录 `held-reviewed-comparison.json`。样本是可复现的合成 VTI，MuPRO 许可环境中的真实算例验收仍待补齐。上一远端 Desktop `42970731524` 已终态 5/6，macOS MP4 与 HTML 隐藏恢复两例仍失败。

## 2026-11-11 07:09 UTC · 上一主线 Desktop 终态与 VTI 组合试验

发布头 `8a9da1313fd4c4cef3f01e17afef9d1285feb7d8` 的 Desktop `42970731524` 于 07:07:36 UTC 整轮结束，5/6 作业通过。Linux 主回归 2243/2243，打包及干净环境冒烟通过。Windows CPU 1537/1537，含 15 个 MuFerro HDF5 用例，原生 20 轮作业通过。macOS CPU 1597/1597、Metal 254/254，必测原生 4/6，MP4 与 HTML 视频仍在隐藏时位置下限失败。普通静默 1/2、隔离静默 0/2，独立挂起与重显 1/1。Runtime 13/13，Secret scan 与 Pages 通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42970731524) [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42970731524/job/130370432580) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42970731524/artifacts/13836306034)

macOS 隔离 MP4 的同一代次记录显示，重显后约 1.7 ms 显示、12.4 ms 原生释放确认，68.9 ms 的原生状态已是 Playing，79.3 ms 的 DOM 回执为未暂停，90.8 ms 触发暂停断言。退出前无 Paused 或 None 的释放证明，原生门仍处于关闭。普通 HTML 曾从 Playing 转为 Paused 并通过保持。普通 MP4 和隔离 HTML 在隐藏前的明确暂停阶段已失败，本轮没有隔离 HTML 的释放时序证据。平台汇总在 `root-delivery-20261111-160/published-platform-ci-8a9da131`。

原生唯一 VTI 的冻结组合试验完成实际 X11 英文宽窗及中文窄窗的六条路线。Runtime 清单已到时，两窗一次点击打开 `scalar-0.vti` 的有符号切片，返回及重访各一次点击，画布相同且全程仅一次求值。真实清单扣在生产 Bridge 回执时，两窗一次点击等待原清单，释放后精确打开该切片，无重复清单请求。另两次在回执前切到工作台，释放后保留当前页面，零图求值。源文件重哈希、切片正负范围和实际 Runtime 任务及产物均已核对。试验二进制 SHA256 `d452fcfe9662817fca11d80f89a8d9ccbdc75b03911218867977a667c2e25608`。证据 `root-delivery-20261111-162/native-vti-window` 的 `window-ready-trial-*` 与 `held-trial-comparison.json`。

Root 审阅补充 Bridge 重启时清除旧清单选取资格、匹配工作区、遵循图节点路径长度及 Runtime 小写摘要要求，并在等待时显示现有「列出结果文件」状态。初次组合的三条布局回归仍假定同步切页，现已按实际清单等待修订。调整后第一轮原生定向 79/79。新增同 Client 重启回归正在复验，Claude 103 仍在独立工作树收尾。唯一 VTI 产品改动尚未进入 main。已验收的任务返回、Web 日志续读与补充回归可以发布。

## 2026-11-11 06:53 UTC · 原生任务 VTI 的 Viewer 候选

Root 独立工作树 `stk-root-native-task-artifact-162` 的 `133a1880bbab64a1246b42dc056269043ba21f4b` 已通过定向 Viewer 22/22。冷启动按确切任务绑定和相对文件路径发一次切片请求，来源显示该文件。属性与 Python 配置保留文件绑定，整次配置在修改设置前核对路径。重访需任务范围、确切路径、发布摘要和已验证画面匹配。保留手动调整过的同文件显示。摘要用于重访匹配，实际下载沿用 Runtime 发布清单校验。独立扫描无发现，证据 `root-delivery-20261111-162/native-vti-viewer/viewer-final.xml`。

Shell 接入候选保存在同目录 `shell-adapter.patch` 和 `shell-guard-test.patch`，待与 Claude 103 的 Jobs 解析组合后构建。读取清单和延后切页之间校验原发起窗口与更新的 Viewer 打开意图，包含尚未采纳的队列请求。真实基线索引和最终实窗复验步骤在 `root-delivery-20261111-162/native-vti-window/baseline-comparison.json` 和 `replay.md`。已有生产 `slice` 预检用实际发布字节重算，制造场为 32×28，范围 −3.4 到 19。尚未交付最终桌面打开链路。

## 2026-11-11 06:45 UTC · Web 日志补充回归与原生唯一 VTI 首开

`7c144ea08120d76f41ab96b5a834f77c67f7ddae` 选取 Claude 102 最终头 `1ace97a2` 相对首版 `b70f0ede` 的单测试文件追加。宽窄窗各覆盖两条路径。真实鼠标点击固定在日志栏顶部的续读按钮后，栏内 90 px 和结果页外层位置都保留。续读挂起时，新点击的图谱探针仍显示，回文件模式可读追加日志。Root 保留已验证的 `50b66f2e` 产品字节。以该生产产物运行新增四项及完整 Chromium 回归 269/269、零失败与跳过，暂存扫描零发现。证据 `root-delivery-20261111-162/claude-log-followup/full.xml`。

原生唯一 VTI 首开的真实基线完成。Linux X11 英文 1600×1100、中文 680×1000，固定起点为聚焦任务页已选成功任务、真实清单已收到，唯一可查看产物为有正负值的 `scalar-0.vti`，另有 `notes.txt`。已发布 `8a9da131` 与本地 `b83c5da6` 各在两种窗验证。点击「在查看器中打开」前零图计算，点击一次后唯一计算使用 `muferro-domains`，实际 Bridge 报 `Polar: The dataset has no frames yet`，没有显示结果。真实 Runtime 任务及产物摘要一致，零模型调用。证据 `root-delivery-20261111-162/native-vti-window/window-red-*`。

Claude 103 已在独立 `claude/workbench-native-task-artifact-103` worktree 从 `be0a29b7` 开始原生 JobsState 的精确产物选择与延迟清单处理。Root 在另一独立工作树接入现成的切片预设、锁定任务路径、显示来源和保留确切结果的重访。原生候选仍在构建，尚未交付；最终需在真实窗口验证首开和返回各一次点击、已发布源值和摘要，以及重访零重复计算。当前用合成 VTI。

远端 `8a9da131` 的 Runtime `42970731620` 于 06:35:50 UTC 整轮 13/13。Linux Python 3.11、3.12、3.14 分别 6898、6915、6898 通过，PET 文件各 43/43。Windows 两个 Python 版本各 5503 通过。Desktop Linux 主回归 2243/2243、零跳过，打包和新环境冒烟通过。macOS 和 Windows Desktop 仍在运行，整轮达到终态后推送已验收提交。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42970731620) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42970731524)

## 2026-11-11 06:29 UTC · 返回原任务标签与 Web 日志继续读取

原生 `b83c5da6b8688ff93434f35300d9da69db2c9ea6` 在「在查看器中打开」成功后记录原任务编辑器、当前窗口和结果来源。从该结果直接点击「任务」，仍在同一任务范围时恢复原标签。普通一级导航和范围失效沿原布局选择。新增回归在旧版复现错误标签，最终 Jobs 78/78、零跳过，含窗口与 GPU 用例。

原生实窗固定起点为 Linux X11 英文 1600×1100、中文 680×1000，缩放 1，两个任务编辑器，原任务与唯一 Viewer 共用区域。原任务显示合成 stderr，任务草稿及展开项保留，外层滚动 40 px。一次点击打开第 7 步，再一次点击返回。旧头两窗回到另一任务编辑器的产物页，外层滚动归零。最终两窗均恢复原任务、stderr、草稿和 40 px，三处区域像素差为零。Tab 离开、Shift+Tab 回到原打开按钮，焦点像素也能复验。图请求由明确打开触发，包含既有邻步预取。返回期间零日志或事件订阅、零模型调用，实际 Runtime 任务和产物一致。证据 `root-delivery-20261111-161/native-task-window/comparison.json`，二进制 SHA256 `894591c07fe4840f272f67adb02fe16d6443f38f22f6042eb51a1b68b904cb84`。

Web `50b66f2e4399f70b22fd6f224e1419c28c84be7f` 集成 Claude 102 的 `b70f0ede` 和独立修订 `b4419295`。明确点击才从当前流已确认的源字节继续，保留当前任务、内容、焦点和日志与探针的操作顺序。旧 Hub 的首次回执可展示无偏移文本。独立复核复现两处错误，从字节 0 的续读错误接受了无偏移回执，跨块 UTF-8 BOM 被错误显示。定向旧版四次失败，修订 18/18，独立与 Root 各完整 Web 265/265、零失败与跳过。Node 22 的独立和 Root 组合生产产物逐文件相同，入口 SHA256 `312c3382c394b5895f7f2f05f4e18f9c5a62dd90729fabe31b37ee8806fd84aa`。文档站 38 页通过。

Web 实窗固定起点为中文 Chromium 1440×900、390×844，当前合成任务已选，Viewer 已显示同一文件，stderr 第一块已显示。从字节 1048576 一次点击补齐 35 个源字节，再一次点击从 1048611 收到空终态，显示「已读完」并保留焦点。每次对应一个 Hub 动作与一次真实 Runtime 读取，最终 DOM UTF-8 摘要和源文件一致。旧版只有首块，跨块字符显示替换符。两窗一次点击回任务后原入口恢复焦点，滚动、任务和画布保留。被动重开结果不触发续读。实际本机 Hub、NodeAgent 和 Runtime，任务、工作区文件和产物无变化，零模型调用。证据 `root-delivery-20261111-161/web-log-real` 的 `baseline`、`integrated` 及 `web-root-full.xml`。

两项已集成本地 main。远端仍为 `8a9da131`，其 Secret scan、Pages、Linux 打包和干净环境冒烟通过，Runtime 和 Desktop 主回归仍在运行。等待该 Desktop 整轮终态再推送。复核旧 PR #53 和 #54 的精确头，分别为 `c9f13994` 与 `2dd3e4ee`，两项继续开放。原四份状态文档和 AOCI 的既有工作区修改保留。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42970731524) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42970731620)

## 2026-11-11 06:12 UTC · 双端工作台更新发布到 main

远端 `main` 从 `09efc0d1b783d7abf7171fc1004beea0b5145901` 快进到 `8a9da1313fd4c4cef3f01e17afef9d1285feb7d8`。推送后独立核对完整远端 SHA，12 个提交范围扫描零发现。包含桌面任务日志续读、Web 等值面输入保留、MuPRO 试点文档、桌面已收集 DAT 的发起窗口与冷启动，以及 Cocoa 重显对照取证。Root 组合桌面、项目测试和 Reports 原生窗口目标已构建。既有 AOCI 与四份状态文档工作区改动保留。

该精确头 Secret scan `42970731604` 已通过。Desktop `42970731524`、Runtime `42970731620` 和 Pages `42970731615` 已启动。上个头的 macOS 两项原生视频仍未通过，新轮核对独立重显对照的释放轨迹。旧 PR #53、#54 的确切头和状态已复核，仍开放。Claude 102 在独立 worktree 的 Web 日志续读处于开发中。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42970731524) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42970731620) [Pages](https://github.com/sijintech/stk/actions/runs/42970731615) [Secret scan](https://github.com/sijintech/stk/actions/runs/42970731604)

上一发布头 `09efc0d1` 的 Windows 原生官方工件已核对选定成员 CRC，6/6、1276 秒、零跳过。PDF、MP4、HTML 视频各 20/20，分别有 160、161、161 张图。PDF 捕获目标创建一次、复用 425 次并回收，匹配 426 次捕获请求，最长启动 101 ms。第 5、20 轮抽样图摘要与报告一致。终态索引 `root-delivery-20261111-159/published-platform-ci-09efc0d1/platform-terminal-summary.json`。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42963571163/artifacts/13833710221)

## 2026-11-11 06:10 UTC · 上一主线 Desktop 终态与 DAT 等待取证

远端 `09efc0d1b783d7abf7171fc1004beea0b5145901` 的 Desktop `42963571163` 于 06:09:56 UTC 达到整轮终态，5/6 作业通过。Linux 2237/2237，打包及新环境冒烟通过。Windows CPU 1537/1537，原生 20 轮验收作业通过。macOS CPU 1597/1597、Metal 254/254，必测原生 4/6。MP4 和 HTML 视频各在隐藏后位置下限失败，首轮分别从 0.347071917 到 0.234 秒、从 0.205410 到 0.102 秒。普通静默 2/2，隔离静默 0/2，单独挂起和重显 1/1。Runtime 整轮 13/13，Secret scan 与 Pages 均通过。上一 Desktop 整轮已终止。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42963571163) [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42963571163/job/130349707275) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42963571163/artifacts/13832491939)

`ed4538d6` 按字节集成独立候选 `384b7cd8` 的单文件诊断。静默普通和隔离对照在既有重显保持检查结束时记录已挂接的同代次 show、释放确认、最后一条原生播放状态，及既有 DOM 回调和首次断言失败时点。缺失和代次不符有独立状态。沿用原探测次数、等待与断言。Linux 普通、探针启用与 Apple 条件分支语法检查通过，实际 Cocoa 需新平台回执。证据 `root-delivery-20261111-160/cocoa-hold-exit`。

补充 `f096a67d` 的真实 X11 预设等待验收。沿用上节 DAT 固定起点和受测二进制，两窗一次点击打开，延迟真实 Bridge 的图目录回执。发起窗口接受打开后，再一次点击「工作台」离开 Viewer。释放回执后两窗继续显示工作台，零图计算，SQLite 摘要一致。保留同一分栏中的 Viewer 可见时，换用旁边的 Python 标签仍可让原请求完成。证据 `root-delivery-20261111-160/dat-origin-window/workbench-during-metadata-en`、`workbench-during-metadata-zh2`。

## 2026-11-11 06:08 UTC · 已收集 MuFerro DAT 在发起窗口打开

原生 `4717b298` 集成独立 `df94b58e` 的发起窗口与项目运行校验。一次性标记只用于按钮发起的内部回调，Python 历史保留可重新执行的普通命令。`1e55d490` 接通 Viewer 尚未加载预设的首次明确打开，等准确预设后使用原文件校验和图请求。`f096a67d` 区分被动元数据回执与 Viewer 操作。运行、发起页或目标 Viewer 的范围失效时，取消待采纳画面。文档站 38 页构建通过。

Linux X11 英文 1600×1100、中文 680×1000，固定起点是项目区最大化、选中已收集合成 DAT 的第 8 版项目、Viewer 尚未加载预设。最终头两窗均一次点击「查看收集结果」，实际严格 Bridge 读取准确预设并显示第 2 步，随后既有相邻帧预取读取第 0 步。将同一次已验证的回执延迟到点击 Python 之后，两窗均保留 Python 草稿与空白 Viewer，零图求值。旧头同一回执会启动第 2 步图及预取，空白 Viewer 被改写。测量无项目写入、任务操作或模型调用，SQLite 摘要一致。证据 `root-delivery-20261111-160/dat-origin-window/guard-*`，原生二进制 SHA256 `5bbe370434ff6ebabdd95a5c1adaf473d70161d401944ebf67edecb87f06e2aa`。

最终原生 DAT、HDF5、Python Viewer 与相邻仿真 11/11，零跳过。Python 工作流与 Bridge 39 通过、1 项有许可才运行的用例跳过。测试包含另一窗口起发、求值挂起后隐藏目标、旧画面及草稿保留、正常点击以及历史命令。证据 `root-delivery-20261111-160/dAT-collection-origin`。真实 MuPRO 许可与目标系统窗口仍待验证。

Claude 102 已在独立 `claude/workbench-web-log-continuation-102` worktree 从 `1e55d490` 开始 Web 任务日志续读。范围为既有日志栏、相关样式及定向回归，复用 `task.logs` 的源字节偏移。Root 负责补丁审阅、真实 Runtime 验收、主线集成与 CI。

发布头 `09efc0d1` 的 macOS 已结束。CPU 1597/1597、Metal 254/254，必测原生 4/6，MP4 与 HTML 视频仍在隐藏期间的位置保持断言失败。独立静默对照两例在重显后只触发播放状态断言，约 105 和 79 毫秒时 DOM 已从暂停变为播放，其余四项断言通过。现有平台记录只证明了隐藏时的原生暂停回执。Windows 原生作业仍在运行，推送等待 Desktop 整轮终态。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42963571163/artifacts/13832491939) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42963571163)

## 2026-11-11 05:39 UTC · 真实 Runtime 重连、等值面参数及 MuPRO 试点文档

原生 `48e6d422` 使用实际本机 Runtime 与生产 Bridge 再验证一键续读。固定起点为 Linux X11 英文 1600×1100、中文 680×1000 的聚焦任务页，已选同一运行中合成任务，stdout 已接受 27 源字节且包含半行。实际停止隔离 API 并保留 supervisor，原订阅先收到非最终错误。随后终止所测试桌面拥有的 Bridge 子进程，第二代实际提交携带 stdout 偏移 27 的自动重订阅，因本机 API 停止收到可重试拒绝。重启 API 后同一任务产出剩余 stdout、stderr 并退出。两窗一次点击「重试日志」即完成，测量中唯一请求为该任务的日志订阅，精确从 stdout 27 和 stderr 0 开始，半行及诊断各出现一次。旧版中文窄窗同一场景仍显示「实时」，无法续读。连接与队列走各自的「刷新」入口。实测未替换 Bridge 响应，证据 `root-delivery-20261111-160/local-runtime-reconnect`。

Web `31fccd2416b475e407a2c38f3d8ffa03bfb9a3f2` 按字节集成隔离 `34738217f8ac229861040d276077847d488c18a2`。等值面回执保留用户输入和在途时编辑的值。切片和向量继续为未编辑的当前文件初始化中点。定向宽窄 12/12，完整 Web 253/253、零跳过，旧包四条定向用例复现覆盖输入。Root 组合构建与独立产物逐文件相同。

Web 固定起点为中文 Chromium 1440×900 与 390×844，成功任务已选，`scalar-0.vti` 的第一张等值面已用明确值 3.25 绘制。旧版再点击一次「加载视图」时实际提交约 7.9，两帧画布摘要不同。集成版一次点击仍提交 3.25，两帧画布摘要相同。真实本机 Hub、NodeAgent、Runtime 的两条动作和返回载荷逐一核对实际参数、任务与产物，零模型调用，Runtime 任务与产物未变化。证据 `root-delivery-20261111-160/web-iso-window/baseline-visual`、`root` 与 `web-iso-level/full.xml`。

`ee2e42ed65a38a46a2bc31ee8c39524b20af40c7` 集成 Claude 101 的单文档交付。按已发布的 `09efc0d1` 校对 HDF5 分量与原始体素，保留旧 H1 点击基线及合成输出。电场扫描列出场方向、幅度与单位、升降顺序、场点、每点步数和采样、初始状态、预循环及参考值。真实执行另需主机、SDK、许可和小算例。实际科学输入、HDF5-only 完成与目标 OS 的实窗流程仍待验。文档站构建 38 页，暂存扫描无发现。 [MuPRO 试点](design/mupro-executor-pilot.md)

发布头 `09efc0d1` 的 Runtime `42963571022` 于 05:32:04 UTC 整轮 13/13。Linux 3.11/3.12/3.14 分别 6898/6915/6898 通过，PET 文件各 43/43；Windows 3.11/3.12 各 5503 通过。Desktop Linux 主回归和两项打包已结束并通过，macOS 与 Windows 仍运行。原生日志恢复、试点文档及等值面修正已在本地主线，等待该 Desktop 整轮终态。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42963571022) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42963571163)

## 2026-11-11 05:21 UTC · 原生任务日志明确恢复

`48e6d42231fd7fb57529388d73d323493dc39dae` 集成 Claude 100 的任务日志补丁。Claude 在独立工作树交付源码和回归，Root 另建隔离工作树复现、构建和审查。旧版用例实测仍显示「实时」且缺重试按钮。初版两条回归把 JSON 键序当成值，Root 改为核对两流偏移；另修订撤权测试的快照测量起点，先等已排队的任务状态和产物读请求抵达。

日志订阅最终失败后，详情在日志区显示原因，保留接受的文本和分流半行。可恢复错误的一次点击只重新订阅当前任务两流。读取偏移采用源 `next_offset`。按钮和回调同时绑定失败代次，旧失败的按钮无法重试新失败。窄窗单独排版长原因，重试按钮保留点击宽度。Bridge 自身的非最终错误与自动恢复沿用原路径。

真实 X11 英文 1600×1100、中文 680×1000，固定起点为聚焦「任务」选中唯一失败的合成任务，已显示第一行。用真实 Runtime 与生产 Bridge 注入已发布的可重试最终错误。在同一任务区一次点击恢复。UTF-8 替换后首批显示字节为 29，重新订阅从 stdout 源字节 27、stderr 0 继续，合并视图补全原半行并显示 stderr 诊断，各一份。每窗总计两次日志订阅、一次事件订阅，测量中的第二次日志订阅是唯一请求，任务记录未变化。该取证覆盖最终回执路径，真实长时间失联和目标平台还需各自证据。验收 `root-delivery-20261111-158/native-task-log-window/integrated-en`、`integrated-zh`。

隔离 `7d3762b1` 和 Root 集成各通过原生 Jobs 66/66、零跳过。六条新用例在独立工作树各重复五次通过，i18n 2/2，文档站 38 页。测试及补丁证据在 `root-delivery-20261111-159/native-log-retry`。合入本地 main，待发布头 `09efc0d1` 的 Desktop 整轮终态后推送。该头 Secret scan、Pages 已通过，Desktop 与 Runtime 仍运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42963571163) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42963571022)

Claude 新任务在 `claude/mupro-pilot-verification-doc-101` 独立工作树，基线 `48e6d422`。范围是核对 MuPRO 试点文档的当前分量、体素和真实验收要求，保留旧合成试验为历史。Root 继续持有 main、审阅、验证和发布。

## 2026-11-11 05:07 UTC · 统一工作台发布到 main

远端 `main` 从 `a184cd213477896a5dd89cb5b0b93c1ca783dccf` 快进到 `09efc0d1b783d7abf7171fc1004beea0b5145901`，发布后独立核对完整 SHA，12 个提交范围扫描无发现。包含原生 MuPRO HDF5 分量、Web 标准错误与探针顺序、同标签页任务环境恢复、原生引用页取景及 macOS 隔离对照失败取证。组合桌面、文献/UI、Reports 原生窗口目标均已构建。工作区既有 AOCI 与状态文档修改已保护。

该精确头 Desktop `42963571163`、Runtime `42963571022`、Pages `42963571030` 已启动。Secret scan `42963571143` 已通过。macOS 必测仍需目标平台重测，新的隔离对照失败字段用于区分失败条件。旧 PR #53、#54 仍为已复核头，未合入。Claude 的桌面日志恢复候选在独立工作树进入 Root 验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42963571163) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42963571022) [Pages](https://github.com/sijintech/stk/actions/runs/42963571030) [Secret scan](https://github.com/sijintech/stk/actions/runs/42963571143)

## 2026-11-11 05:06 UTC · 组合原生验证及 macOS 保持取证

Root 组合桌面、文献与 UI 目标完成构建，文献 34/34、UI 132/132，零失败或跳过。`e4f4ecdc` 的原生取景验收补充于前节。Web `c29bd628` 的组合生产产物与隔离构建相同，真实 Runtime 两种窗口验收已绑定组合提交。

`12b341e0034314ed3b11149b8c45c5c0ca3a9938` 按字节集成 `c929d0798c7b79647f9a79531d1f32967bf62ae9` 的单文件候选。仅在隔离静默对照的重显暂停保持断言首次拒绝时，记已有样本、五项判定、导航基准和时间差。保持 0.50 秒观察期、0.10 秒容差与原探测次数，未加 CI 用例。Linux 普通、Linux 开启探针、Apple 条件分支三种语法检查通过。实际 Cocoa 运行待目标 CI。外部证据 `root-delivery-20261111-159/cocoa-reshown-hold`。

正式 Windows 原生工件的选定成员通过 CRC 核验，6/6、1179 秒、零跳过。PDF、MP4、HTML 视频各 20/20，验收图 160、161、161 张。PDF 的捕获目标创建 1 次、复用 428 次并回收，已接受帧最长启动 53 ms。macOS 普通静默 HTML 重显暂停与明确播放的两张官方 PNG 摘要已核，隔离对照的失败样本仍缺。汇总 `root-delivery-20261111-158/published-platform-ci-a184cd21/platform-terminal-summary.json`。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42955953031/artifacts/13829259510) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42955953031/artifacts/13830325253)

## 2026-11-11 05:03 UTC · 同标签任务环境与桌面文献页取景

Web `c29bd628eb1d1d7abd8aec9233b92e428ce1d2ee` 集成隔离 `abb7122a4896c2395ec13f377e4c266acb121238` 的两个路径。已配对标签页只保存执行节点和项目选择，正常启动列表返回后同时恢复当前仍列出的确切节点与工作区。断开、清空及失效范围回到环境设置。首次网络故障等待原刷新流程。旧任务、Viewer 和提交状态都不恢复。生产构建与隔离产物逐文件相同，完整 Playwright 247/247、零跳过，覆盖撤销、工作区变更、明确断开和首次列表失败。

Web 固定起点为同一已配对中文标签页重载到「工作台」，此前明确选择两个项目中的乙，队列各含一个真实 Runtime 合成任务。Chromium 1440×900 与 390×844，旧版从固定起点点击「任务」后还需点击并选择节点和项目各一次。集成版两种宽度均一次点击「任务」即在滚动零的位置看到乙的队列，自动收起运行环境。真实本机 Hub、NodeAgent 与 Runtime 回执记录两种版本同样的五个启动 GET，零 POST、零模型调用，任务状态未变。证据 `root-delivery-20261111-159/web-environment-window` 的 `baseline`、`root`，配合 `web-environment-restore/full.xml`。

桌面 `e4f4ecdc3f33b511de6a4d6e62a6460803a6cf40` 集成隔离 `900253b267534f41f1414bc268e182bcba1340b4` 的四路径。打开另一已核验引用页时恢复完整页取景，同页重绘和标签回程保留原缩放和平移。定向回归旧版仅在第二页继承旧几何的断言失败，候选三次通过；独立可移植文献 34/34、UI 132/132。测试使用冻结缓存页和合成第二页，经严格桥与生产编辑器运行，未测新检索模型。

桌面固定起点是阅读页已打开第一条引用并缩放、平移。Linux X11 英文 1600×1100 与中文 680×1000、比例 1。从起点点第二条引用，旧版继承放大平移，需在图像内双击重置才能看完整页，共三个鼠标点击。候选直接完整显示，共一次点击。两窗候选屏幕截图的 SHA 均与旧版人工复位后的相应图完全相同。各次总计 1 搜索、2 定位、2 页图渲染，取景恢复不增加桥请求。真实窗口回执在外部 `root-delivery-20261111-159/literature-window`，原生选测基线合计 100/100 在本轮开头通过。文档站构建 38 页通过。

Claude 已交回桌面日志恢复的八路径未暂存补丁。Claude 沙箱拒绝本机构建命令及外部构建目录写入，未取得红绿结果。Root 已冻结原补丁，在第三个独立 worktree 启动基线编译，继续核对失败态、授权边界、UTF-8 源偏移与实际窗口回程。真实桌面宽窄窗用相同已发布的可重试终态 DTO 再次复现旧版显示「实时」。其候选尚未合入本批。

## 2026-11-11 04:57 UTC · 上一主线 Desktop 整轮终态

远端 `a184cd213477896a5dd89cb5b0b93c1ca783dccf` 的 Desktop `42955953031` 在 04:57:14 UTC 结束，5/6 作业通过。Linux 主回归 2236/2236，Linux 打包和干净机冒烟通过。Windows CPU 1536/1536、零跳过，Windows 原生 20 轮作业通过。此头 Runtime 13/13，Secret scan 和 Pages 通过。已达到上一 Desktop 整轮终态的推送条件。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42955953031) [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42955953031/artifacts/13829259510) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42955953032)

macOS CPU 1596/1596、Metal 254/254。必测原生 4/6，MP4 和 HTML 视频均在隐藏后的位置保持失败，首轮分别为 0.350357→0.234 秒、0.221098→0.102 秒。普通静默对照 2/2，隔离暂停静默对照 0/2，独立挂起/释放对照 1/1。两条 HTML 真菜单回程都通过一次指针移动解除工具提示，原生交互阻挡在一帧内解除。普通 HTML 完成重显和明确播放，隔离 MP4 和 HTML 均到达重显保持阶段后失败。下一轮诊断需区分隐藏时的时间回退与隔离方案重显后的保持行为。原必测门槛保留。 [macOS 官方工件](https://github.com/sijintech/stk/actions/runs/42955953031/artifacts/13830325253)

## 2026-11-11 04:40 UTC · 桌面任务日志失效基线与 Claude 分工

Root 已在 Linux X11 英文宽窗 1600×1100 和中文窄窗 680×1000 的真实桌面复现：从聚焦「任务」点选唯一的合成失败任务，已有一行日志可见。真实 loopback Runtime 和生产 Bridge 的首次读取接受 27 源字节，替换非法 UTF-8 后显示对应的 29 字节文本。随后注入同一订阅的最终错误。页头报告错误，任务日志区仍显示「实时」，没有重试入口。两窗各发一次日志订阅与一次事件订阅，无任务写入。固定起点截图与请求回执在外部 `root-delivery-20261111-158/native-task-log-window/red-en` 和 `red-zh`。

Claude 已在独立 `claude/workbench-task-log-retry-100` worktree（基线 `22a4d5ef8c1175c22cbcdabb77a0b2878cd8dfa6`）实现可恢复错误的本地提示和一次明确重试，候选尚未交回。验收目标从已确认的源字节位置继续同一任务两流，保留已显示文字与半行，发一次日志订阅。Root 持有真实窗口、审阅、整合和推送。

远端 `a184cd21` 的 Windows CPU 正式工件已独立核对 1536/1536、零跳过，含 15 项 MuFerro HDF5 用例。Desktop 仍在执行 Windows 原生 20 轮和 macOS 打包及原生验收。本地已提交 HDF5 分量和 Web 日志两项交付，等待该头 Desktop 整轮终态。 [Windows CPU 工件](https://github.com/sijintech/stk/actions/runs/42955953031/artifacts/13829150908) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42955953031)

## 2026-11-11 04:36 UTC · 工作台读取所选 HDF5 分量与任务标准错误

桌面 `1ef5de308dbe2bf3aed81ed9da2cc76a3cac9cd0` 在已收集的 MuPRO HDF5 多分量场中接受明确的零起点分量索引。同一索引用于图计算、Viewer 来源和原始体素。单分量场直接打开。缺失、越界及过长输入保持打开按钮不可用，编辑输入期间无图请求。隔离候选和 root 集成各通过原生定向 19/19，覆盖原始 uint64 值、显示范围、选择生命周期和旧 Viewer 保护。

桌面固定起点为项目表格最大化、已选合成运行和 `/t00000002/Polar` 第 2 步，Linux X11 英文 1600×1100、中文 680×1000，比例 1、无需滚动。旧头 `55534fc0` 一次点击可打开分量 0，同坐标 X=2、Y=1、Z=0 读得 float32 42，界面没有分量选择。集成头从同一状态先点分量输入、填 `1` 并按 Enter，再点打开，共两次点击、一个数字和一次确认键。查看来源后执行体素查询读得 float32 43，来源显示步 2 和分量 1。两窗各一次字段读取、一次显示计算、一次原始体素查询，项目数据库与文件摘要均保持一致。

Web `333a0e6930104f964d67555ac7f3c93227fa7f56` 由 Claude 在独立 `claude/workbench-task-stderr-99` worktree 交付，root 审阅后修复挂起时的键盘焦点和日志与探针的回执顺序。结果区按用户操作顺序呈现最近确认的读数或日志。失败与过期回执保留已确认内容，继续复用 `task.logs`，每次明确读取一个流。生产构建与 240/240 Playwright 全量通过，含宽窄窗的 8 个日志及探针用例。旧版缺少流入口，Claude 初版上的四条 root 回归复现焦点和探针问题。文档站 38 页构建通过。

Web 固定起点为中文 Tasks 已选合成失败任务、滚动为零，Viewer 已打开同一任务的 `scalar-0.vti`。真实本机 Hub、节点和 Runtime 上，Chromium 1440×900 与 390×844 均用两次点击「读取日志 → 标准错误」读取诊断。第一条请求沿用默认 stdout，第二条明确请求 stderr。Runtime stdout 为空、stderr 为 46 字节，界面逐字显示诊断。再点一次「任务」回到原按钮，保持原 Canvas、任务和滚动。模型调用零，任务记录未改变。旧版一次点击只读取空 stdout，无法从该栏切换到 stderr。当前 Web 每次读取流起点的单块内容。

验收回执、截图和测试日志在外部 `root-delivery-20261111-158` 的 `native-hdf5-window`、`native-hdf5-component`、`task-log-window` 和 `web-task-stderr`。本轮使用合成任务与数据。MuPRO 真实主机、SDK/许可、合作方小算例与扫描参数仍待落实，现有收集继续核验 DAT 完成信号。

远端主线仍为 `a184cd213477896a5dd89cb5b0b93c1ca783dccf`。该头 Runtime 13/13、Secret scan 与 Pages 通过。Desktop Linux 主回归 2236/2236，打包与干净机冒烟通过，Windows 和 macOS 仍运行，整轮达到终态后再推送。旧 PR #53、#54 的头未变，均未合入。原四份状态文档的工作区改动和 AOCI 暂存资产已保留。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42955953031) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42955953032) [Pages](https://github.com/sijintech/stk/actions/runs/42955953035) [Secret scan](https://github.com/sijintech/stk/actions/runs/42955953004)

## 2026-11-11 03:57 UTC · 统一工作台新片已发布到 main

远端 `main` 从 `abdc57f7a8cdc648920b34fe53e54c219719d720` 快进至 `a184cd213477896a5dd89cb5b0b93c1ca783dccf`。已独立核对远端完整 SHA，13 个提交范围扫描零发现。包含新工作区直接呈现首个任务表单、Web 任务草稿目标一致性、成功任务单文件预选、中英文指南和 macOS 静默重显对照。原 AOCI 与状态文档工作区改动已保留。

新头 Desktop `42955953031`、Runtime `42955953032`、Pages `42955953035` 已启动。Secret scan `42955953004` 已通过。目标 macOS 将验证菜单指针修订后的静默对照，必测位置问题继续单独跟踪。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42955953031) [Runtime CI](https://github.com/sijintech/stk/actions/runs/42955953032) [Pages](https://github.com/sijintech/stk/actions/runs/42955953035) [Secret scan](https://github.com/sijintech/stk/actions/runs/42955953004)

上一发布头 `abdc57f7` 的 Windows 原生官方工件经逐成员 CRC 核对，6/6、1164 秒、零跳过。PDF、MP4、HTML 视频各 20/20，分别保留 160、161、161 张验收图。PDF 捕获目标创建 1 次、复用 438 次并回收，已接受帧最长捕获启动 58 ms，第 5 和第 20 轮关键图摘要与报告一致。正式平台终态索引在外部 `root-delivery-20261111-155/published-platform-ci/platform-terminal-summary.json`。 [Windows 工件](https://github.com/sijintech/stk/actions/runs/42948501049/artifacts/13826463628)

## 2026-11-11 03:55 UTC · 上一轮 Desktop 达到整轮终态

远端 `abdc57f7a8cdc648920b34fe53e54c219719d720` 的 Desktop `42948501049` 于 03:55:05 UTC 结束，5/6 作业通过。Linux 主回归 2233/2233、打包和新环境冒烟通过。Windows CPU 1536/1536，原生 20 轮验收作业也通过。macOS CPU 1596/1596、Metal 254/254，必测原生 4/6，仍有 MP4 和 HTML 视频隐藏位置下限失败。两条静默对照的重显阻挡和本地诊断修订见下节。Windows 官方工件已发布，逐成员详情另行核对。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42948501049) [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42948501049/artifacts/13826463628) [macOS 原生工件](https://github.com/sijintech/stk/actions/runs/42948501049/artifacts/13825909265)

同一发布头 Runtime 12/13、Secret scan 与 Pages 通过。Windows Python 3.11 和 3.12 均通过，唯一 Runtime 失败为 Linux 3.12 的 PET 桥接等待，独立 43/43 与受控锁取证见下节。已满足上一 Desktop 整轮终态的推送条件。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42948501059)

## 2026-11-11 03:50 UTC · 单文件结果预选与 macOS 重显对照

`4f9e47c0` 集成 Claude 独立 Web 候选，并复用成功任务范围判断，防止失败任务的残留产物被预选。Root 新增用例在原候选确实收到失败任务的一个发布文件并被自动选中，最终版保留可手选列表和空选择。用户显式点击成功任务的「结果」捷径，当次列表确切采纳、仅有一个可查看文件、文件选择未编辑且 Viewer 尚无显示时预选该文件，加载使用原按钮。主导航、图谱、多个文件、已编辑选择、已显示画面以及迟到回执覆盖在内。现代只读和旧版 action 路径均验证。Claude 独立全量 231/231，定向 21 项各重复十次，Root 最终生产构建和 Web 全量 232/232，零跳过。最终入口摘要 `703be6a20b4d286580cd0d2730867b6ff298053b05464b0c23c89cac7969824d`。

固定起点沿用上节已选成功任务与一个合成 VTI、一份日志。真实 Chromium、Hub、NodeAgent 和本机 Runtime 在 1440×900 与 390×844 实测，旧版三次点击加两次按键，最终两次点击，无需单独选择。两端窗口初次各读一次列表，显式点击前零构建，点击后一次精确任务/文件构建。回任务页再打开，仍显示原文件、来源与同一个画布节点，增加一次列表读取、零构建。任务与产物摘要一致，零模型调用。外部证据为 `root-delivery-20261111-157/result-window/comparison.json` 和 `web-single-result/full.xml`。`7266b9ba` 更新统一工作台设计和双语指南，Astro 38 页构建与两页生成文本校验通过。

远端 `abdc57f7` 的 Windows CPU 1536/1536，零跳过，包含 15 项 HDF5 定向用例。macOS CPU 1596/1596、Metal 254/254，必测原生 4/6。MP4 和 HTML 的首轮隐藏位置分别从 0.346192 到 0.234 秒、0.219783 到 0.102 秒，两者导航相同、挂起回执已到，仍未通过时间下限。两条 HTML 静默对照在 286 px 菜单路径重显时各等待约 45 秒。新取证证实原资源活跃、视口完整，工具提示是唯一在场的界面阻挡，原生视图尚未开始重显。独立挂起/释放可选对照 1/1。Windows 原生继续运行。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42948501049) [macOS 工件](https://github.com/sijintech/stk/actions/runs/42948501049/artifacts/13825909265)

`4d54da84` 按字节集成隔离候选 `9cbf55d1`，只在两条 Apple HTML 静默对照的真实菜单返回后，通过原有移动指针方法离开工具提示并记录阻挡状态。保留实际导航、同画面、位置下限、显式播放与必测门槛。独立三种条件编译和 Root 原生窗口目标通过，各次暂存扫描零发现。实际 macOS 重显待新头，上一轮 Windows 原生终态后推送。

## 2026-11-11 03:32 UTC · 单文件结果基线与 PET 取证

当前 `decfa288` 的 Web 入口复用上轮生产包，摘要 `bd6ed9e93dd69a344a8eaed9c48dbdf341a32993c40db99c3c5b8232e6ac34b3`。固定起点为任务页已选成功任务、结果文件模式、尚无显示画面，真实 Runtime 发布一个合成 `scalar-0.vti` 和一份日志。Chromium 1440×900 与 390×844，经真实 Hub 和外连 NodeAgent 实测均为任务「结果」一次、点击文件选择器并按两键选中唯一文件、点击「加载视图」一次。测量内三次点击、一次文件选择，零滚轮。每轮一次文件列表读取，显式加载前零构建，点击后按同一任务和发布路径构建一次并显示画布。Runtime 任务及发布文件不变，零模型请求。证据在外部 `root-delivery-20261111-157/result-window/baseline-live`。

单文件选择简化已分派 Claude 的独立 `stk-claude-workbench-single-result-98`，只在任务行结果捷径、当次读取与当前任务范围均匹配且原选择未编辑时预选，明确加载仍用原按钮。另用现代与旧版合成 Hub 复核了相同基线。当前桌面已通过显式入口直接打开任务结果，同一已核对来源可保留已有 Viewer，Root 结果相关定向 4/4。候选尚未交付。

Linux 3.12 失败作业的隔离同头 PET 文件 43/43，134.197 秒，零跳过。目标用例 5.589 秒，预算结束后最慢桥接读取 41.22 ms，8 秒诊断观察点未触发。受控实验只让后台 Runtime 读取在项目锁内暂停 600 ms，线程栈确认前台工作流读取在同一锁上等待 621.79 ms 后返回，原预算和接受任务断言通过。CI 的 60 秒停顿未复现，现有超时和产品行为保留。证据在外部 `root-delivery-20261111-156/pet-runtime-lock-probe`。 [Runtime 失败作业](https://github.com/sijintech/stk/actions/runs/42948501059/job/130286957429)

远端 `abdc57f7` 的 Linux Desktop 主回归于 03:26:51 UTC 通过 2233/2233，595.02 秒，打包和新环境冒烟也通过。Windows CPU 与 macOS 原生文档验收仍在运行。本地代码继续等待上一轮 Desktop 整体终态。开放 PR #53 与 #54 已核对现有头，未出现新的差异。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42948501049)

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

Linux X11 英文 1600×1100、中文 680×1000、缩放 1。固定起点为聚焦结果页，真实本地 Runtime 合成任务第 7 步已显示，原任务保有草稿。两端打开来源各 1 次点击。英文 Tab 后 Esc 关闭，中文点关闭 1 次。两端按 Enter 从归还的焦点重开，再按 Esc。弹窗期间注入滚轮，英文另测 Ctrl+Space 和小键盘 1。关闭前后画布区域逐像素一致，英文小键盘 1 在关闭后能改变画布，证明快捷键实际生效。含准备与任务返回全路线 8/9 次点击。保持原任务、日志与草稿。打开和关闭无服务读取、重复计算、模型调用或 Runtime 写入。收据在外部目录 `root-delivery-20261110-135/native-source-window/window-final-*`，二进制 SHA256 为 `8d7ef36927914c9caabc603bd99a8bbed5706daf1b5c9bcd0834d7b88e3cbf72`。

`e3e69af9` 集成实际 Claude89 `9483afc3`。Web「来源」分行展示节点、项目、任务名称与完整 ID，并区分当前显示和待加载文件。图谱在各自面板绑定来源。结果正文里的长摘要限制行数，完整值在可滚动详情中可用。Tab 离开、打开历史或切页会收起详情，Esc 和明确关闭归还焦点；离开字段时清理该字段自动选中的文本。Root 整合版 Chromium 103/103，零跳过。

中文 Chromium 1440×900 与 390×844，模拟 Hub。固定起点为已选合成任务、已载入一个结果文件并改选另一个的结果页。任务打开结果 1 次点击，详情打开和关闭各 1 次。测试完整已显示与待加载路径、不可见字符、超长名称、键盘 Tab 和 Esc、窄屏历史、40 px 滚动偏移、Viewer 像素与任务日志。独立的来源打开/关闭测量期间零 API 请求和剪贴板调用。请求、点击和截图收据在外部目录 `root-delivery-20261110-135/web-source-reviewed/playwright`。

远端 `693e7ea4` Runtime 13/13，Linux Desktop 2195/2195 和两个 Linux 打包作业通过。Windows CPU 1505/1505，逐项确认上一轮的六项默认窗口快照已通过，必测 Python 校验匹配 1197 项。macOS fmt 下载 HTTP 429 在构建前失败。截至本记录，Desktop 仍在运行，Windows 原生内容是唯一进行中的作业。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [Windows CPU 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021210081) · [Windows 原生作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130049729774)

Claude90 已排队，从 Root `e3e69af9` 接手 Web 文件与图谱互切时的 Viewer 保留，等待 Claude89 在独立 worktree 完成交接。Root 负责双端集成和 CI 门禁。

## 2026-11-10 18:43 UTC · 窄窗结果取景与 Web 结果来源

`4e4bf6e9` 在聚焦任务明确打开新结果时为窄窗的默认预设首次取景，依据当前视口使用已发布的 View All 计算。作者数值相机、非默认缩放、工作区相机和显式预设沿用原优先级。原生交互分类图例加对比底色，导出图像沿用原图例绘制。Jobs 53/53、相机 10/10，OpenGL 与 Vulkan 各 5 个 Viewer 验收组均通过。定向 GPU 回归确认交互图像出现底色、相同相机的导出像素一致。

Linux X11 固定起点为已选公开合成 Runtime 任务的聚焦任务页，比例 1。英文 1600×1100 与中文 680×1000，各 5 次设置点击、一次输入和 Return。各 1 次点击打开第 7 步结果，1 次返回任务，选中任务、日志和表单草稿保留。窄窗在 632×884 画布内左右留 32、19 像素，四个图例标签可读；旧版初开边距均为 0，需额外点击一次「全部显示」取得相同取景。英文宽窗模型区 1124448 像素与基线一致。另测一次中键旋转后 Tasks→Results，画布逐像素一致。中文另测 680×1000→1600×1100→680×1000 两次调整尺寸，零额外点击，恢复后完整截图逐字节一致。返回与尺寸往返未新增 graph.evaluate，各路线均无模型调用或 Runtime 写入。原始收据在外部目录 `root-delivery-20261110-134/task-result-framing` 与 `task-result-framing-resize`，二进制 SHA256 为 `59b2ac19ab448bad62f024b4adc6328e890b7cf7af5b48b859d35c7510beed48`。

`9d8891c4` 集成实际 Claude88 `625ce3c2`（独立测试 95/95）。Web 结果页显示所选任务的节点、项目与名称，以及 Viewer 当前显示的文件。选中另一文件时保留旧画面及其来源，明确加载成功后才更换。探针、构建回执、错误与复核提示按已显示场景或有效请求绑定；过期的排队轮询停止，认证错误仍断开会话。回执携带来源时核对任务和文件，兼容无来源字段的旧回执。任务日志与文件、图谱探针分别保留。进入另一种结果模式清除原图谱的探针输出。Root 集成版 Chromium 99/99，零跳过。

Web 固定起点为中文模拟 Hub 已选合成任务的任务页，1440×900 与 390×844。每端从任务页打开结果各 1 次点击，编辑文件选择使用程序化下拉。在待加载、历史切页和范围变更路线检查画布位置与原结果，并用迟到成功、HTTP 502、来源不符与旧版无来源回执验证状态。明示的加载和探针通过现有 Hub 操作，切页无模型调用或修改。图谱与文件模式之间的画布重建、超长待选路径的完整窄屏查看仍需后续验收。截图与请求收据位于外部目录 `root-delivery-20261110-134/web-result-final/playwright`。

远端 `693e7ea4` Runtime 13/13，Secret scan、Pages 及两个 Linux 打包作业均通过。Linux Desktop 2195/2195，逐项确认上一轮 6 个默认窗口和 2 个任务页快照修复。macOS 作业 130021209994 因依赖 fmt 补丁下载 HTTP 429 在构建前失败。截至本记录，Desktop 仍在运行，Windows CPU 测试进行中，原生内容作业待该构建包。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [Linux 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021210004) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42870793242)

Claude89 已在独立 worktree 启动，基线为 `9d8891c4`，负责 Web 结果来源的按需详情与键盘、触屏可用性。Root 负责统一原生入口、集成和平台验收。

## 2026-11-10 18:22 UTC · 聚焦任务结果、Web 队列和平台诊断

`e210227d` 从原生聚焦任务页直接打开所选任务的结果，复用该窗口的 Viewer 与一级导航。回调核对窗口、编辑器、连接、节点、工作区和任务身份及代次。激活成功才打开结果，较早排队的打开请求由当前点击取代。传统分栏仍使用原入口。Jobs 53/53，新增回归覆盖创建工作区期间失效的请求及打开结果的顺序。项目导航回归 36/36，零跳过。

Linux X11，英文 1600×1100、中文 680×1000，比例 1。固定起点为聚焦任务页、选中真实本地 Runtime 上已完成的公开合成任务，展开新建表单并保有草稿。5 次设置点击，加一次文本输入和 Return。点击所选结果、返回任务各 1 次。结果显示精确任务与第 7 步，返回保留选中项、日志和草稿。额外英文宽窗将实际结果回执延迟到返回后，完成前后任务页截图逐字节一致。3 条路线均无模型调用或修改请求，Runtime 工作区、任务和产物校验不变。窄屏 Viewer 可见同一结果，但模型两侧裁切、部分图例覆盖网格。原始收据在外部目录 `root-delivery-20261110-133/tasks-results-window-reviewed`，二进制 SHA256 为 `807c20c9c417597936b9cc329eaadf82db77bd5a7778c228537ce3ea88f76f68`。

`2de31dc0` 集成独立 Claude87 末版 `4ad74e25`。Web 任务页先显示队列、已选任务、快捷操作和待复核项，运行环境与新建任务收进详情。运行环境首次展开便于选节点，手动折叠随页面切换保留。Root 加入独立滚动上限，200 条任务仍可看到已选任务状态及运行环境入口。提交与审批沿用现有明确操作，任务、TaskSpec 草稿和 Viewer 在切页时保留。构建与整合版浏览器回归 87/87，零跳过。

Chromium 模拟 Hub，中文 1440×900 与 390×844。已进入选定工作区的任务页直接看到队列，新建任务及手动折叠后的运行环境各 1 次点击展开。完整短队列测量路线中，从已连接的新页面出发 5 次点击另有 2 次程序化下拉选择，已选任务复查 7 次点击，断开与恢复路线 3 次点击。测量包含各自的展开、切页和复查步骤，未调用模型。200 条合成任务的补充路线验证首条单击、尾条可获焦及无写入。JSON 计数和截图在外部目录 `root-delivery-20261110-133/web-queue-integrated/playwright-full`。

`a9cefe9e` 合入隔离 Windows 捕获诊断 `d41795d5`，分别记录 CreateForWindow 的原始调用、HRESULT 转换和退出清理耗时。旧聚合字段、输出上限及验收规则保留。便携计时夹具及证据门 12/12 通过，Windows SDK 构建与实际捕获仍待目标 CI。本轮本地待发提交与远端 `693e7ea4` 分开记录。截至本记录，Desktop 仍在运行，Runtime 仍在运行，13 个作业中 11 个已通过。macOS 作业 130021209994 在 vcpkg 下载 fmt 补丁时多次返回 HTTP 429，配置、构建、CPU、Metal 和原生验收均跳过。Secret scan 与 Pages 通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42870791136) · [macOS 作业](https://github.com/sijintech/stk/actions/runs/42870791136/job/130021209994) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42870793242)

Claude88 已在独立 worktree 从 `4ad74e25` 接手 Web 结果的来源展示和探针绑定。Root 负责集成、双端验收和 CI 门禁。PR #53 的对应主线续传回归定向 3/3，旧补丁仍冲突。PR #54 仍是九月的旧交接快照。

## 2026-11-10 18:00 UTC · 原生智能体会话历史与 Desktop 门禁

`9bc9b771` 将原生工作台历史分成普通问答和智能体会话。工作台、任务与结果共用入口，按对应账本的精确 ID 读取。相同 ID 文本、迟到的读取回执和旧窗口回调由定向回归覆盖。读取失败可点击同一条记录重试，已有发送或待确认回执时禁用历史选择。Root 在独立 worktree 的 Claude86 修订 `dd91cf9f` 上整合界面、同条重试与导航回归。Claude 的控制器定向 20/20 通过，旧基线全量 2159/2167，8 项为已定位的旧布局快照。Root 整合版原生定向 82/82 通过，零跳过。

Linux 实窗固定起点为已打开合成项目、已选任务并保有普通问答与智能体草稿。英文 1600×1100 与中文 680×1000，缩放 1。分别从任务页打开 Agent Alpha、从结果页打开 Agent Bravo，宽屏各 1 点击，窄屏各 2 点击（历史、会话行）。普通问答返回同为 1/2 点击。各次只读对应记录，保留两种草稿。Viewer 回到公开样例第 1000 步，中文画布像素一致，英文差异限于中心体积着色。含设置、切页和复查共 11/15 次点击，每端各输入两次草稿。项目 SQLite 和 Runtime 任务与工作区相同，无模型请求、运行启动、目标修改或项目写入。截图与点击收据位于外部目录 `root-delivery-20261110-132/agent-rail-window`，二进制 SHA256 为 `db0321707bf0d9c945d57303c1da6e44459b6a8fd78a422dd073c7843be2880c`。

上一远端源码头 `79ea12f4` 的 Desktop CI 于 17:54:33 UTC 全部结束，6 个作业中 2 个打包通过、4 个失败。Linux 2174/2182、macOS CPU 1547/1553、Windows CPU 1487/1493，失败分别为 Linux 6 个窗口与 2 个任务快照、macOS 与 Windows 各 6 个相同窗口快照。本地 `15a5830a` 与 `bb812b60` 修正对应快照，定向通过 51/51 与 88/88。macOS 的 Metal 原来随 CPU 失败跳过，导致报告检查缺少 XML。`dc48679b` 在成功构建后独立运行 Metal，保留已有 CPU、Metal 与报告校验失败判据。Runtime 13/13，Secret Scanning 和 Pages 均通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

同一轮 macOS 原生内容 4/6，MP4 隐藏保持与 HTML video 首次明确暂停的时钟超差。可选隐藏探针 0/2，帧时钟探针 1/2。`0c239b42` 调整可选诊断，下一轮实机待验。Windows 原生内容 5/6，PDF 第 20 轮重新准备第一页时捕获启动失败。序列 433 的 `capture.create-for-window` 返回 `0x8007041d`，启动调用总耗时 120059 ms，像素验收随之超时。PDF 19/20 轮完成，两个视频通过。原生内容均零跳过。本地 Linux 回归和实窗完成，macOS 和 Windows 原生结果仍需按新源码头确认。 [macOS 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/129975239887) · [Windows 作业](https://github.com/sijintech/stk/actions/runs/42857730640/job/130004878783)

Claude87 已在独立 worktree 接手 Web 任务页队列优先，将运行环境和新任务放入按需展开区。Root 负责统一入口、点击数、状态保留和双端集成验收。PR #53 与 #54 仍分别是冲突的旧补丁和旧交接。

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

实际 Claude85 在独立 worktree 提交 `d5ce6399`，正在完成测试复核。独立审阅发现旧 POST 回执先到时可能压掉含较新消息的历史读取，已确认会话缺失时仍有旧创建授权，以及先发下一条会覆盖待重试消息。从该冻结候选另建隔离修订，完成前暂缓集成。Claude86 任务已排队，待前一 CLI 终态和精确 worktree 检查后处理原生智能体会话读取代次。

远端 `79ea12f4` 的 Desktop 仍运行，两个 Linux 打包作业已过。Runtime 已有 11 个作业成功，整轮仍运行。本批代码已提交到本地，待上一 Desktop 整轮终态再推送。PR #53 仍冲突，#54 仍是旧交接。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42857730640) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 16:52 UTC · 原生近期问答导航

`159a21a6` 集成 `e88fd9f6` 的原生只读近期问答缓存及导航。支持当前项目和新桥接口时，宽屏左栏显示最近保存的未归档问答，窄窗用历史菜单。从任务、结果或工作台选择即打开原问答。列表变化时旧弹出菜单关闭。同项目打开期间共享一次在途读取，旧项目回执不能替换当前列表。Root 定向原生回归 62/62，零跳过，覆盖归档更新、旧回执与原编辑器复用。

Linux X11/OpenGL，比例 1，英文 1600×1100 和中文 680×1000。固定任务页与结果页均已打开同一合成项目，含一条待处理和一条已完成问答，并预先输入草稿。英文两条路径各用 1 次点击，中文各用 2 次点击，先打开历史再选对应问题。另有 6 次设置、切页与回到结果的点击，每端各输入一次草稿，零键盘快捷键、滚轮或缩放。核对精确问题、保存来源、已完成回复和草稿。两端返回结果后，公开 `example.stkp` 第 1000 步的Viewer 画布逐像素一致。项目数据库字节一致，无任务、工作区、写入、发送或模型启动。较长标题在宽栏截短，悬停可读完整标签。新界面的 macOS 与 Windows 实窗待验证。证据见 `root-delivery-20261110-129/rail-native.xml` 与 `rail-window-proof/window-{en-wide,zh-narrow}/window-receipt.json`。

Claude85 正在独立 worktree 从 `86671b81` 修订 Web 历史回执和重试。后续仍需接入智能体会话并验证不同会话身份，桌面任务页的运行设置和表单也待整理。已安排独立原生诊断候选复用现有 macOS 可选 CI 槽位，比对首次可见暂停的工具栏触发时序。强制原生门禁沿用原测试。

前一批已推送 `79ea12f4`。推送前核对 `3c4f9bf9` 整轮终态，Desktop 5/6 作业通过。Linux 2177/2177、Windows CPU 1488/1488、Windows 原生 6/6。macOS 原生 4/6，首次可见暂停失败见上一节。`79ea12f4` 的 Secret scan 与文档部署通过，Desktop 仍运行，Runtime 排队。本节的近期问答提交仅在本地，待 `79ea12f4` 的 Desktop 整轮终态后推送。PR #53/#54 的原头分别为旧冲突补丁与旧交接，均未集成。 [新头 Desktop](https://github.com/sijintech/stk/actions/runs/42857730640) · [新头 Runtime](https://github.com/sijintech/stk/actions/runs/42857730952)

## 2026-11-10 16:43 UTC · 上一远端头 Desktop 终态

远端 `3c4f9bf9` 的 Desktop 于 16:43:32 UTC 整轮结束，6 个作业均到终态。Linux 三个作业、Windows CPU 与 Windows 原生通过，macOS 原生必验失败。macOS CPU 1548/1548、Metal 254/254。原生必验 4/6，MP4 与 HTML 均在首次可见暂停低于 0.05 秒下限。两份 270–290 ms 被动延迟对照均在观察窗口内取得稳定暂停。Runtime 13/13 已通过。本次终态满足推送前提，随后推送截至 `4442342e` 的已验证批次及本记录。新头的桌面平台验证以其自身 CI 为准。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42845291750) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42845291916) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42845291750/artifacts/13783327194)

## 2026-11-10 16:38 UTC · 聚焦会话详情与精确问答返回

`a8d80a9a` 将原生聚焦工作台的数据范围与模型设置收在按需展开面板。问答和输入框优先显示。空项目入口使用按文字内容计算的按钮宽度。`6e18a3b1` 集成候选 `1338781b`，从项目首页的问答提醒读取对应请求，保留未发送草稿与新问题的数据范围。“已查看”由独立按钮处理。Root 原生集成回归 53/53，零跳过。

`1fa0baec` 集成 `f2c721cf` 的本地只读 Bridge `project.requests.recent`。接口按保存顺序从新到旧返回未归档问答，默认 8 条，最多 20 条。旧列表仍按原顺序分页。Root Bridge、请求、归档、智能体与脚本回归 179/179，零跳过。原生侧栏接入仍在后续。

Linux X11/OpenGL，比例 1，英文 1600×1100 和中文 680×1000。会话验证先用 2 次点击打开合成项目并进入工作台，固定起点已显示一条原问答。各用 5 次点击展开和收起数据与模型、聚焦输入框、进入结果并返回，另输入一次草稿。返回后同一原问答、草稿与折叠状态仍可见，结果页显示公开样例第 1000 步。中文窄屏展开面板后需要滚动查看输入框下缘。

精确返回固定起点为已打开同一合成项目的首页，含待处理和已完成两条问答。每端 7 次设置点击包含一次显式数据范围捕获，另输入一次草稿。固定起点后两次各 1 点击从对应提醒打开原问答，各 1 点击返回首页，共 4 次点击，零滚轮或快捷键。两端保留草稿，英文宽窗直接显示新问题范围仍为原数据，中文窄窗保留面板折叠。两端项目数据库字节、项目修订、提醒状态和消息摘要保持一致，实际方法观察中模型启动、发送、新建请求和标为已查看均为零。证据见外部目录 `root-delivery-20261110-128` 的 `attention-native.xml`、`recent-root.xml`、`window-proof/window-{en-wide,zh-narrow}/window-receipt.json` 及 `attention-window-proof/window-{en-wide,zh-narrow}/window-receipt.json`。macOS 与 Windows 的新布局实窗待验收。

实际 Claude84 以 `86671b81` 正常结束，Web 构建和 46 项回归通过，补齐初次读取确认之前的发送限制。Root 审阅发现真实 Hub 会先保存问题再交付回执，现有 mock 缺少此时序。暂缓集成。实际 Claude85 从 `86671b81` 在独立 worktree 接同 ID 重试、旧回执合并、历史去重、缺失会话草稿和窄屏遮罩焦点。Root 下一步接入原生近期问答侧栏，继续使用已有的精确返回护栏。

## 2026-11-10 16:19 UTC · 聚焦工作台收起技术页头

`7282342a` 将编辑器选择、技术标签和区域菜单移出原生聚焦工作台的页头。工作台保留首页与项目，任务保留提交与刷新，结果保留打开、叠加层、全部显示和导出。通过分栏视图恢复专业工具。原生定向回归 50/50，零跳过。

Linux X11/OpenGL，比例 1。固定起点为文件、Viewer、文献/Python 与项目表格四区，Viewer 已加载公开 `example.stkp`。英文 1600×1100 和中文 680×1000 各依次点工作台、任务、结果、工作台、分栏，合计 5 次点击，零键盘、滚轮或缩放。聚焦页头单行显示且操作按钮宽度正常。回到原区域几何与高级控件，结果仍为第 1000 步。两个流程的任务、工作区和项目修订增量均为零。页头操作通过画面与组件回归核对，本轮实点覆盖导航。外部证据目录 `root-delivery-20261110-127`，具名测试 `header-final-native.xml`，窗口收据 `window-proof/window-{en-wide,zh-narrow}-release/window-receipt.json`。macOS 与 Windows 实窗仍待验收。

Claude84 在独立 worktree 继续 Web 会话历史及每会话草稿。Root 审阅时发现原生项目首页的问答提醒已带 `request_id`，入口仍只传页面名。已安排独立候选修复精确返回，原生历史侧栏和跨端来源返回仍待集成。

## 2026-11-10 16:10 UTC · 双端左栏、首次启动与只读会话历史

`67a6fd3f` 增加 Hub 只读会话历史。存在时返回原会话及消息，缺失返回 404，旧会话入口和显式发送兼容。Hub 定向 52/52。`82fc9d43` 集成 Claude82/83 的三页 Web 导航。结果和日志捷径一次显示对应内容，晚回执沿原任务更新，保留当前页和 Viewer。Root 构建与 Chromium/Node 全套 22/22。

`6a562d2e` 原生宽屏用左栏，700 逻辑像素及以下用横栏。保留当前项目名、显式分栏入口及原编辑器。

`1a3ef021` 无保存布局时打开工作台。聚焦布局重开保留当前页，显式 `--open` 在新工作台和已保存的聚焦工作台直接显示结果。旧普通最大化和显式分栏照原状态恢复。原生导航、工作模式、工作区和传输回归 50/50，零跳过。

Linux X11/OpenGL，比例 1，原生固定起点为文件、Viewer、文献与项目表格四区，Viewer 载入公开 `example.stkp`。英文 1600×1100 左栏和中文 680×1000 横栏各走工作台、任务、结果、工作台、分栏五次点击，零滚轮或键盘。英文任务页调整到 800×1000、680×1000、再回原宽度，选中任务页保持。结果步 1000 和原四区回到画面，任务、工作区和项目修订均为 0。窄分栏的 Viewer 图例重叠在起点与回程均可见。

另验六次启动，全部正常退出。英文新配置零点击进入工作台，一次点任务后保存，重开保持任务。对同一保存布局显式传入公开结果，零点击进入 Results 并显示第 1000 步。中文窄屏首次打开结果，无参数重开保留结果页和尺寸，需重新打开载荷。显式旧布局保留普通最大化，原布局文件不变。启动证据见 `startup-release/startup-receipt.json`。完整点击收据和截图在 `root-delivery-20261110-126/window-proof`，具名测试 XML 为 `startup-final.xml`。新界面的 macOS 与 Windows 实窗仍待对应环境验收。

长日志修订 `8a80dc8c` 集成实际 Claude83 后续 `45fc1059`。点击时给日志预留有界空间，迟到日志原位更新。宽窄屏各验证离开再回到结果页与用户滚动后的稳定性。Root 最终 Web 28/28，含 17 项 Chromium 合成回归和 11 项 Node 测试。

实际 Claude84 从 `8a80dc8c` 在独立 `claude/unified-workbench-web-history-84` 接会话历史侧栏、每会话草稿及异步回执保护。Web 当前会话读取仍沿用旧入口，新历史界面接入只读路径待集成。原生项目会话历史、精确来源返回及收起技术标签仍是后续。

## 2026-11-10 15:42 UTC · 统一工作台首片验证

本地 `058b1555` 复用 AI、Jobs 和 Viewer。点工作台进入聚焦导航，依次显示工作台、任务、结果。分栏视图恢复原区域树。普通最大化和读取已保存布局沿用原入口。工作台导航已在原生顶部验证，左侧项目与会话导航、默认布局和按需详情仍为双端下一片。

原生工作区及模块回归 27/27，零跳过。新增检查实际结果载荷、Viewer 和会话编辑器复用、相机重置代次和原分栏。Linux X11/OpenGL 在 1600×1100 英文和 1000×1200 中文、比例 1 的固定文件/Viewer/文献/项目表格布局下，各点工作台、任务、结果、工作台、分栏视图，共 5 次，零滚轮和键盘。公开 `example.stkp` 回到 Viewer，任务数 0，项目修订 0。前一抓屏驱动继承终端输入并吞掉后续命令，已用隔离 stdin 的驱动重验两组。截图和输入收据在 `root-delivery-20261109-124/window-{en,zh}-focus-final`，具名 XML 在 `root-delivery-20261110-125/unified-native-final.xml`。

实际 Claude82 `0e17ecea` 的 Web 候选使用同序三入口、宽屏左栏、窄屏横栏。两种 Chromium 合成窗口检查通过，验证隐藏面板持续挂载、草稿及 Scene v1 回到原任务。Root 审阅发现明确的结果和日志动作要直接展示内容，延迟视图回执应保留当前页面。实际 Claude83 在独立 worktree 修订，待审阅集成。

## 2026-11-10 15:30 UTC · 原生执行预检、CI 夹具与统一工作台方向

`9216d7cb` 在项目的材料仿真中增加默认折叠的执行环境检查。一次明确点击保存请求，再向所选 Runtime 提交单 CPU 诊断。面板可见时读取原任务，重开从本机记录恢复。晚回执按项目、连接、编辑器与父子面板代次核对。指南由实际 Claude80 的 `ae5a82e0` 经 root 审阅集成。 [桌面指南](mupro-desktop-preflight.md)

`e5bfaa7f` 集成实际 Claude81 `ef3dfb05`。补齐跳过构造的测试夹具所需预检状态与锁，保留生产关闭逻辑。旧夹具本机 5 败、4 过。修复后作者三版本各 9/9，Python 3.12 联测 263/263。root 的关闭、journal、严格 RPC 联测 60/60。新头远端结果待验。

所有者要求简化 STK 并统一 Web 与本地客户端。以 Synthrix `caec2b9` 的统一主页面和 Codex 的会话工作方式为参照。首片共用工作台、任务、结果的顺序，保留现有会话、任务与 Viewer 实例。Root 负责原生聚焦及分栏恢复。实际 Claude82 已在独立 `claude/unified-workbench-web-82` 接 Web 导航，候选待跨端审阅。项目与会话侧栏、默认布局和详情的统一继续实施。 [统一工作台](design/unified-workbench.md)

预检入口的折叠和实际窗口静止时的定时读取已修正。 [验收](runtime-validation.md)

## 2026-11-10 03:29 UTC · 诊断请求持久化、严格 Bridge 与前一 CI 终态

`5e377de0` 集成实际 Claude78 `81185683` 的共享预检客户端/未注册适配器，以及独立 `669b523b`、`f046d791` 的诊断 journal，并发布五个 Bridge 方法 describe/list/reserve/retry/refresh。记录在项目外持久化，固定原运行环境、工作区选择、资源和请求键。reserve 纯本机保存 prepared；原生调用方必须先得到持久确认，再在原视图仍有效时发送明确执行请求。丢 reserve 回执不会留下排队执行。重开、列出和刷新均不重提，未知回执只允许沿原 ID/原键明确恢复；已知任务 retry 零 POST。新工作区创建也使用稳定派生键。坏 journal 仅让预检不可用，不删除数据，不阻止其他 Bridge 模块启动。未增 Agent 工具、项目格式或放置权限。 [桌面诊断契约](specs/mupro-preflight-desktop-1.md)

`b7aa88fa` 集成实际 Claude79 `d00d3493` 的严格 stdio Bridge/真实 HTTP Runtime 回归。root 预检、CLI、journal 和 RPC 联测 254/254、零跳过。其中新 RPC 22 项含 SIGKILL 重开、工作区/任务已接受后挂起或丢答复、同键同体恢复、严格 Schema、冻结目标、失败检查产物、零自动回放和坏存储隔离；作者 Python 3.11 同组 22/22。root 另有协议定向 6/6、最终 hello 1/1，以及严格 NDJSON/两种 Schema validator 的 reservation/reopen/坏存储隔离实测。合成 worker PID、原 TaskSpec、产物摘要和环境脚本单次执行均核对；未验证真实 MuPRO、许可、SSH/调度站点或目标 OS 的新界面。

前远端 `37e48356` Desktop `42732315824` 于 2026-11-10 01:58:24 UTC 终态 failure，六个作业全部结束、四成功。Linux 主测 2170/2170、两个打包作业成功；Windows CPU 1488/1488、零跳过，工作区 18/18 和 guarded 7/7 全部具名通过，上一轮四项路径失败已恢复。macOS CPU 1548/1548、Metal 254/254，主原生仍 4/6；独立 Windows 原生实际 5/6，不能沿用前头全过。同头 Runtime `42732316049` 终态 13/13，Secret scan/文档部署成功。整轮结束满足本批已验证后端提交的推送前提；本节随本批交付，新的精确头 CI 结果待验。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42732315824) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42732316049)

本头 Windows 原生仅 PDF 失败：实际完成 7/20，第八轮 reprepared-page1 的捕获构造失败，阶段 capture.create-for-window、HRESULT 0x8007041d；启动及回退/释放混合段约 120,053 ms，尚无 poll 或采样，通用 45 秒结果期限正确拒绝晚结果，却不能抢占同步 COM 构造。其余五项各 20/20。捕获底层代码在前两头相同，当前证据不支持归为本批产品回归或单纯 runner 故障。Mac 原片 MP4 在隐藏暂停阶段失败，HTML 视频更早在初始显式暂停失败。新增 270 ms 可见对照两项有效：MP4 请求/实际派发 273.302/273.341 ms，HTML 275.847/275.898 ms，均在 270–290 ms，期间 DOM/OS 捕获计数未变。两次 DOM 各稳定在 0.470061750/0.344736125 秒，native 验证通过且资源活跃。它是有界对照证据，不能替代原强制门或认定原因已解决。

原生面板仍为未提交候选：root 增加独立 workspace 选择与事件/目标代次，直接调用 Bridge，不复用 Jobs 的选择或 Script 执行。独立真实回归已证明旧候选在折叠及折叠再展开、未绘制下一帧时会误发一次 retry；root 已补事件即时 panel epoch、原 ID 绑定及新建工作区自有选择，等待最终新 ABI 定向与真实窗口验收，不称界面已交付。当前无本地 CI 观察器，后续按同 run 的官方状态复读。实际 Claude80 已从 `b7aa88fa` 在独立 worktree 写一份用户指南，root 保留 UI/契约/集成/推送职责。PR #53/#54 头仍 c9f13994/2dd3e4ee，原冲突未合入。真实软件/研究参数、HDF5-only 完成、H2 和分析提案持久形式等待决保持。

## 2026-11-10 01:32 UTC · 显式执行环境预检与原任务回执

本地 `8d3752ff` 与 `1c8c2dcf` 完成显式 Runtime 执行环境预检。客户端提交固定单 CPU、空输入及空环境覆盖的诊断任务，在 worker/调度环境使用该端自己的配置；不启动 MuPRO/MPI 或签出许可。`preflight-result` 只读原任务，按固定规格、连接、终态/退出码、唯一产物大小/SHA-256和严格内层格式核验。失败检查仍有 failed/1 的有效观察，取消、执行故障、错接规格与未知状态不冒充成功；丢提交答复只允许明确同键同请求重试，零自动重提。本机 `check` 原含义、运行/收集链及 Agent 权限保持。 [任务回执契约](specs/mupro-preflight-task-1.md)

实际 Claude77 `ae980be9` 在独立 worktree 交计算侧规格、观察器及测试。root 捕获 summary 数组/对象产生 TypeError 的解析缺口，两个实际红例后补字符串门。独立 `88fba9e1` 的 CLI 回归另证明旧候选会把别的工作区合法预检当本次提交/读取成功；root 增加提交答复和最终结果的原始规格绑定。三项 CLI 红例均实际失败，最终 31/31；夹具最初错误替换 os.environ 导致三个 worker 配置失败已单独保留，不作为产品反例。

root 最终联测 211 过、2 跳过；两跳过仍为真实 muFerro 样例条件及 Windows 目录联接。Python 3.11/3.14 的计算/本机观察各 111/111、CLI 各 31/31，零跳过。真实回环核对 worker PID、相反客户端配置、环境脚本单次执行、失败产物、冷客户端重读、同键恢复、取消和畸形回执。独立基础依赖 wheel 无 NumPy/h5py，实际安装控制台→HTTP Runtime→worker 的三配置均通过；重开客户端和同键重试保持同一任务/字节，三个任务仅采集三次。四个安装模块与当前主线源码摘要一致。该证据只覆盖本地 Linux 回环和合成前置条件，不是跨机 SSH、PBS/Slurm、真实软件或许可证明。

已推送远端 `37e48356`。截至 2026-11-10T01:31:10+00:00，同头 Runtime `42732316049` 已终态 13/13；Desktop `42732315824` 仍运行，Linux 主测 2170/2170，工作区 18 项及 guarded 7 项均具名通过，两个打包作业成功；macOS 和 Windows CPU 尚未终态。Secret scan、文档部署已成功。上述两个新的远端预检实现提交仅本地，等待 `37e48356` 整个 Desktop 终态后再推送。当前远端 CI 只含上一批本机预检和 UI/路径修正，不把它当新增远端诊断代码的验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42732315824) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42732316049)

实际 Claude78 已从冻结 `1c8c2dcf` 在独立 `claude/mupro-preflight-bridge-78` 接下一模块：共享纯客户端读取/提交逻辑及未注册的桌面 Bridge 适配器。root 负责方法注册/契约、原生仿真面板、目标切换/未知回执状态、最终回归和推送。该适配器与原生按钮尚未交付，不称桌面已可检查。新流程未做产品窗口点击验收；既有文献双布局 8→6 点击回执保持。真实 MuPRO 资产/科学参数、HDF5-only 完成证明、H2和分析提案持久形式仍按原待决；PR #53/#54 原冲突差异未合入，Cocoa 视频问题继续以原强制门禁验收。

## 2026-11-10 00:57 UTC · MuPRO 本机预检与前一 Desktop 终态

`000bb6ff` 新增显式本机 `suan mupro check --json`，发布 `stk.mupro-preflight/1`：复用既有采集一次，输出固定检查项、保守总结、进程/组件版本与采集时间，排除路径和原始诊断。所有总结均保留软件版本未观察、许可未签出、求解器未运行。原 `python -m suan.mupro check` 诊断和退出码保持。命令会 source 已配置的受信任脚本，不能作为被动 health/graph.meta 读取或所选远端机器的就绪证明。

本机预检及旧链联测 87 过、2 跳过；跳过分别为真实 muFerro 样例条件和 Windows 目录联接，含新增 18 项。Python 3.11、3.14 各 18/18。独立 wheel 仅装基础依赖、无 NumPy/h5py，实际控制台三项观察均符合契约：脚本程序 incomplete/0、原生占位程序 passed/0、缺程序 failed/1。两个安装模块摘要与主线一致，受控夹具零求解器/MPI 调用。占位程序不是 MuPRO，不能据此认定软件身份、许可或科学结果。

实际 Claude74 的 `c124e58b` 经 root 修订为 `bd861dd0`，新增原生文献用户指南及入口链接，明确桥解释器与宿主解析/编码 worker 的环境可以分开配置。实际 Claude76 从冻结 `5fe4e6d7` 在独立 worktree 交 `98663411`，root 以 `e3b80fd8` 集成一份试点文档，核对 50 个本地链接，区分已实现的本机观察与拟议节点传递/读取器投影。 [试点说明](design/mupro-executor-pilot.md)

`5fe4e6d7` 修正 Windows 回归夹具的期望路径，使用词法规范化及 UTF-8 转换，并为新来源等待超时加入状态诊断；不改产品路径行为。旧头 Windows CPU 共 1488 项，1484 过、4 失败、零跳过。三项日志直接证明同一路径的分隔符比较错误；第四项同样使用该谓词并超时，旧回执不能证明其最终来源状态。本地相关 18/18，实际 Windows 修正结果待本批新头 CI。

`ae5090dc` 集成实际 Claude75 `239fc81e` 的可选原片时延对照：保持同一 seek/可见历史，只在 play 返回后普通非阻塞事件泵等待固定 270 ms，期间不作 DOM/媒体采样或 OS 截图。root 增补实际暂停请求和原生派发均落在 270–290 ms 的有效性门，超界保留原始观察但不计有效对照。原强制六项门禁、执行器及看门狗阈值不变。Linux 构建、探针开/关及 Linux/Apple 宏四种语法检查、相邻轮询 CTest 1/1 通过；两个夹具摘要未变。Apple 宏检查不是 Apple SDK 或 Cocoa 运行，目标结果待新 CI。

远端前头 `ba03ac8d` Desktop `42722834184` 于 2026-11-10 00:52:20 UTC 终态 failure，6 个作业全部结束、4 成功。Linux 主测 2169/2169、两个打包作业成功。Windows CPU 结果及修正见上；独立原生 6/6、零跳过，六源各 20/20 轮，PDF 八阶段各 20 次记录且 Viewer/草稿保护通过。macOS CPU 1547/1547、Metal 254/254，主原生仍 4/6。整轮终态满足本批推送前提。同头 Runtime 13/13：Linux 3.11/3.14 各 6634 过、166 跳过，3.12 为 6651 过、149 跳过，均另排除 4；Windows 3.11/3.12 各 5311 过、275 跳过、936 排除。原固定派发来源断言在三个 Linux 版本具名进度均通过。本节随已验证的文献单击打开、Python 面板回归、本机预检及修正提交交付，新的精确头 CI 仍待验证。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42722834184) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42722834173) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42722834184/artifacts/13724407825)

本头 HTML 原片的隐藏/可见配对均观察到 DOM 时间回到 0.102 秒，可见组原生已验证暂停；MP4 对照在初始显式暂停失败，不能当作完成了新鲜配对。独立帧号夹具两源均 no_clock_reset_observed，8 张 PNG 的摘要及帧号核验通过，但夹具与捕获时延共同变化，仍未解决原产品 4/6。本批 CLI 与诊断未新增产品 UI 交互，文献实际双布局 8→6 点击的既有验收保持。真实 MuPRO 主机/SDK/许可/研究参数、HDF5-only 完成证明、目标 OS 文献交互和分析提案持久形式仍待；H2 未代选。PR #53/#54 已重查，头仍为 c9f13994/2dd3e4ee，原冲突差异未合入。root 继续负责审阅、集成、推送和 CI，Claude 按独立 worktree 的限定任务配合。

## 2026-11-10 00:02 UTC · 文献命中单击打开与 Python 面板回归

本地 `26644456` 把文献检索命中明确标为“打开引用页”。一次点击按原引用身份顺序解析、渲染和显示精确高亮，仍可单独明确重试解析或渲染。临时连续读取绑定解析操作、页代次、查询/范围、桥进程与编辑器生命周期，失效或隐藏后不继续旧读取，重显不恢复操作。后端方法与写操作复核沿用已有契约。

原生便携文献测试 33/33。真实本地 PDFium/E5 资产回归最终 6/6、零跳过：两布局正向全链保留再次渲染、撤权同步清纹理及 Viewer/隐藏 Python 稿保护；已成功解析但挂起的 wire 回执在英文改查询、中文改范围、两布局隐藏重显后均零旧页渲染，重新明确搜索/打开仍校验真实 PNG 和高亮。这批测试集成 `4ed31a87`，120 个公开头文件、源码和独立归档摘要绑定经过 root 复核。

实际 Linux X11/OpenGL llvmpipe 窗口从默认英文 1600×1100、中文 1000×1200、scale 1 起步，各使用新预置的自有合成 PDF 资料库/索引和既有本地模型，Viewer 已显示公开网格。到引用页均为 6 次点击、零滚轮，原为 8 次；从已有搜索命中到页图均由 3 次降为 1 次。随后撤权并返回另 5 次，清稿退出另 1 次，总计各 12 次。引用/来源摘要、PNG、30 个高亮、实际像素、撤权清页及 Viewer 像素相等均核验。完整真实资产 CPU 导入至历史链两布局各从 37 降至 35 次点击。英文页底仍受原视口裁切，不宣称完整页展示；目标 macOS/Windows 新交互待验。

`17685b5a` 选择集成实际 Claude73 `e6a01cca` 的 Python 面板回归：真实严格 Bridge、图 worker 与 AppShell 主线程操作验证候选失败保留 A 草稿、错误返回和恢复字节后明确重开 B。root 去掉“首次轮询必须尚未完成”的竞态假设，仍核对每次观察的打开身份与对应来源状态。root 当前定向 4/4；作者原候选在基线 `6333178e` 完整项目测试 939/939。不把作者旧基线全测当本批全部回归；该合成执行链未涉及许可求解器，Windows 科学依赖条件仍排除该用例。

已推送远端 `ba03ac8d`，包含 `6333178e` Viewer 保护与 `83302698` Runtime 旧断言修正。截至 2026-11-10T00:00:46+00:00，新 Desktop `42722834184` 仍运行，两个 Linux 打包作业成功；Runtime `42722834173` 已有 10/13 作业成功，其余矩阵仍运行，暂无失败。Secret scan 和文档部署已成功。上述新文献与面板回归提交仅在本地，等待 `ba03ac8d` 的整个 Desktop 终态后再推送。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42722834184) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42722834173)

实际 Claude74 已从冻结 `17685b5a` 在独立 `claude/literature-guide-74` 编写文献桌面使用指南，仅新指南文件；待 root 审阅。root 继续负责公共实现、验收、集成和推送。PR #53/#54 仍为 c9f13994/2dd3e4ee，旧冲突差异未合入；原路线和 MuPRO 实际许可/科学参数等剩余条件继续保留。

## 2026-11-09 23:44 UTC · 前一 Desktop 终态与 Cocoa 帧号回执

远端 `5cb7cdb9` Desktop `42712877920` 于 23:39:58 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2162/2162，两个打包作业成功；Windows CPU 1481/1481，独立原生 6/6 且每项 20/20 轮、零跳过。macOS CPU 1540/1540、Metal 254/254，主原生 4/6。整轮终态满足本批推送前提。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42712877920/artifacts/13720252143)

本头旧 MP4 首次暂停从 0.356866 到 0.366517 秒，下界通过；约 95 毫秒的 hold 后回到 0.234 秒，仅时间差上界失败，native 查询尚无回答。HTML 隐藏暂停从 0.214776 回到 0.102 秒，下界失败。这些是本头阶段，不能沿用更早头的 MP4 初始暂停失败描述。

新帧号诊断两项均通过，四张必需裁剪图/源共八图经过 ZIP、摘要及独立 PNG 帧号重读核验。MP4 可见播放帧 2→3、暂停 4/4；HTML 播放 1→2、暂停 2/2。最终两次 DOM 分别稳定在 0.4069555、0.353200833 秒，两源均为 `no_clock_reset_observed`。root 已独立查看两源的最后播放和暂停截图。此控制同时采用独立夹具和约 269/268 毫秒的播放捕获延后；DOM 比较使用更早的播放快照，不能排除未捕获间隙，更不能据此称原失败原因已解决。实际产品门禁继续为 4/6。

本批推送包含已本地验证的 `6333178e` Viewer 失败保护与 `83302698` 固定派发来源证明断言修正。同头 Runtime 的 10/13 终态及旧断言失败已记录于上一节；修正后的三版本结果仍待下一远端头验证。实际 Claude73 在独立 worktree 补 Python 面板集成回归。root 同时开发文献命中单击打开，现有真实资产回归中两布局各由 37 降为 35 次点击，命中至页图 3→1；窗口验证和迟到回复回归仍在进行，产品改动尚未提交。

## 2026-11-09 23:23 UTC · 受约束打开保留 Viewer 与草稿

本地 `6333178e` 在已有 Viewer 时先验证带 `source_proof` 的候选来源，成功后才替换。失败、取消或被新操作取代时保留旧来源、画面、相机和未提交参数，自动求值与播放暂停。候选提交直接采用已解码帧，不再发起一次求值。格式错误的新打开在同步校验阶段拒绝，不取消已接受候选。

原生状态与 Python facade 增补可选 `opening` 请求身份和状态。`wait()` 只跟随等待开始时的同一候选，允许成功时切换来源；失败即返回，即使旧来源仍有未提交草稿。取消、替换或其他来源变化会中止等待。无此字段的旧桌面保留既有行为。说明已同步到 Viewer 指南与桌面 Bridge v1 增补。

集成实际 Claude72 `c8286623` 的真实严格 Python Bridge、图 worker 与离屏 GPU 回归，以及 `5be16fc5` 的已完成 Future 延迟回调测试、`3a9217e0` 的等待回归。root 追加同步拒绝不取消候选，并修正未加载翻译目录时错误原因丢失的问题。最终原生工作区 18/18、既有 Viewer 状态及表单 31/31；Vulkan、OpenGL 各 6/6，具名 GTest XML 均包含新用例。Python 3.12 联测 50/50，3.11 与 3.14 定向各 21/21，零跳过。暂存差异和 gitleaks 检查通过。

`83302698` 更新 MuFerro 固定派发测试，核对传入的完整来源证明。相关文件单独 30/30，最终已包含在上述联测。远端 `5cb7cdb9` Runtime `42712878022` 终态为 10/13 成功；三个 Linux 作业均仅在这一旧断言失败。3.11/3.14 各 6618 过、166 跳过，3.12 为 6635 过、149 跳过；均另有 1 失败和 4 排除。两个 Windows 客户端各 5296 过、275 跳过、936 排除。本地修正仍需下一远端头复验。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42712878022)

截至 2026-11-09T23:22:58+00:00，同头 Desktop `42712877920` 仍运行，4/6 作业成功。Linux 主测 2162/2162、两个打包作业与 Windows CPU 已成功；macOS CPU、Metal 及构建已通过，主原生步骤失败后仍继续诊断，新增帧号结果待工件。独立 Windows 原生仍运行。本地新提交尚未推送，继续等待整轮 Desktop 终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920)

实际 Claude73 已从冻结 `6333178e` 在独立 worktree 接 `CL-MUPRO-GUARDED-SCRIPT-73`，仅补 `script_test.cc` 的真实 Python 面板到原生 UI 操作验证；候选待交付与 root 审阅。root 继续负责实现、公共契约、集成、回归、推送和 CI。

本批 GPU 使用 Linux llvmpipe 与合成目录，不是目标 OS 窗口或真实许可 MuPRO 算例。程序入口和状态机验证未测用户窗口点击次数。实际许可、目标平台窗口与后续试点仍按原计划验收。PR #53/#54 头保持 c9f13994/2dd3e4ee，未合入旧 worker 语义或冲突交接路径。

## 2026-11-09 22:32 UTC · Cocoa 帧号诊断与前一 Desktop 终态

远端 `5cb7cdb9` 已推送，新 Desktop `42712877920` 与 Runtime `42712878022` 已启动。新查看来源校验、探针代次和帧编号诊断的目标平台结果随这两个精确头回执核对。 [当前 Desktop CI](https://github.com/sijintech/stk/actions/runs/42712877920) · [当前 Runtime CI](https://github.com/sijintech/stk/actions/runs/42712878022)

`dbc0ebbb` 集成 Claude71 最终 `0d0de6a1` 的独立合成帧编号视频和可选 Cocoa 诊断。先取得两张递增的播放画面，再取得两张相同帧号的暂停画面，并记录已有 DOM 采样。root 补充了历史 DOM 时间回退判据，以及结论所用四张截图的持久化和摘要核对。缺少必要截图或时间证据时报告不确定。独立 MP4 与 HTML 嵌入视频两项诊断已接入 macOS CI，保存具名 JUnit 和裁剪截图。

最终新视频 44,339 字节，SHA-256 `c2bbcb873b7628c22b512051443adde6ff2e6c8688c6d84f0307d6bab2a34eef`。60 帧、10 fps、六种缩放与关键帧 [0,30] 均验证。精确 C++ 逻辑通过 1080 次解码位置、16 项分类、12 项审计和 5 项记录失败检查。真实 PNG 编解码及最终路径冲突证明无法用较早截图替代丢失的必需截图。Linux 编译、普通及 Apple 宏分支的 GCC 语法检查通过。这些检查尚不能证明 Apple SDK 编译或 Cocoa 截图时延，实际目标执行待新头 CI。

前头 `75b20fc6` Desktop `42702711687` 于 22:24:01 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2159/2159，两个打包作业成功。Windows CPU 1478/1478，独立原生 6/6 且每项 20/20 轮，零跳过。macOS CPU 1537/1537、Metal 254/254、原生主测 4/6。当前 MP4 在首次显式暂停下界失败，HTML 在隐藏暂停下界失败。同头 Runtime `42702712232` 全部 13/13。整轮终态满足本批推送前提。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42702711687/artifacts/13715432852) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232)

本头 MP4 的 fresh-hidden 与 fresh-visible 形成完整配对，已有播放 DOM 时间分别为 0.350154 与 0.367201 秒，两次暂停采样都回到 0.234 秒。隐藏原生报 Playing，持续可见时报 Paused。两组独立会话的视口高度相差 1 CSS 像素。当前 HTML 可见组在初始暂停阶段失败，缺少本头完整配对。该原视频回执仍未证明可见画面帧倒退，新帧号视频用于下一步独立观察。

Claude72 已从冻结基线 2b45ed81 在独立 `claude/guarded-viewer-open-72` 补受约束打开失败时保留原 Viewer 及参数草稿的回归，root 负责审阅和产品实现。现有异步打开在最终字节验证前清理旧来源，该路径继续验证。

## 2026-11-09 22:12 UTC · 探针代次与原生 MuPRO 查看回归

`3f36d736` 让探针请求编号跨清除选点和关闭来源继续递增。已完成但排在主循环队列中的旧回调，即使无法取消，也无法覆盖新选点或新来源的探针结果。新请求仍按原路径完成。

集成 `8f84451c` 的两个确定性反例。测试先确认旧请求 Future 已成功完成，暂扣其回调，再清除重选或关闭重开，暂扣新回调后只释放旧回调。旧头两个反例各重复 5 次，10/10 在探针状态被覆盖处失败。修复后工作区 11/11、既有 Viewer 状态及表单 31/31，零跳过。

新增 C++ ViewerState 接真实严格 Python Bridge、图 worker 和 llvmpipe 离屏渲染的来源回归。Vulkan、OpenGL 两后端各 5/5，通过已缓存帧改写拒绝、保留上一份已验证画面、工作区恢复后显式求值与探针再次拒绝、恢复原文件后的画面和采样核对。每个后端均实际执行新增用例。该测试使用合成目录，实际目标 OS 窗口交互与许可算例继续验收。

远端 `75b20fc6` Runtime `42702712232` 已终态 13/13。Desktop `42702711687` 仍运行，3 个 Linux 作业与 Windows CPU 已成功，macOS 和独立 Windows 原生仍运行。本地新提交等待整轮终态再推送。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687)

Claude71 已在独立 worktree 提交可选可见帧编号诊断候选 `1525f17b`，仍在完成交付。root 正审阅诊断分类和截图证据落盘，候选尚未集成，实际 Cocoa 执行待下一头。

## 2026-11-09 21:54 UTC · MuPRO 查看源校验与 Windows 回归

`89ffacbd` 把收集结果中算例文件的路径与 SHA-256 清单带入 Viewer 来源。来源与可编辑预设参数分开保存，打开、步进、预取、探针和工作区恢复后显式求值沿用该清单。图节点缓存命中前仍检查当前内容，读入经过项目目录约束和摘要校验的私有快照。本机缓存显示和探针网格缓存均不能绕过这次读取。

集成 Claude69 `2e3c4940` 与 Claude70 `9bd6d96a` 的回归。真实合成任务在 Viewer 调用处遭同大小、同 mtime 改写时拒绝冷、暖缓存结果，恢复原文件后回到原帧和原畴比例，零新增任务。严格子进程 Bridge 和图 worker 的求值、探针、清单范围及本机来源拒绝转发 Hub 四项通过。普通目录探针仍可携带未使用的失效绑定。

Python 3.12 联测 101/101，独立字节码目录的核心回归 52/52，最终严格 Bridge 4/4。既有 MuFerro 流程与 HDF5 收集兼容 41 过、1 项真实许可条件跳过。Python 3.14 定向 51/51，隔离 wheel 安装态 46/46，8 个安装成员与最终源码一致。Linux 原生 CPU 状态及工作区测试 40/40，包含来源传递、重复显式求值、探针和惰性恢复。这些原生状态测试使用测试桥，实际目标平台界面与真实 MuPRO 许可场景待验。

已推送的 `75b20fc6` Runtime `42702712232` 全部 13/13 作业通过。Windows Python 3.11、3.12 客户端分别 5246 过、275 跳过、934 排除。两组的同 inode 同大小恢复 mtime 文件签名、真实 NTFS 联接的严格 Bridge 拒绝和原生 ChangeTime 三项目标均由官方逐文件进度、精确源码收集顺序及完整跳过记录映射确认通过。该工作流未生成具名 JUnit，映射经独立复核。同头 Desktop `42702711687` 仍运行，本地查看链路修复等待整轮终态再推送。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42702712232) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42702711687)

实际 Claude71 在独立 `claude/cocoa-frame-clock-71` 从冻结基线 77c83814 开发可选可见帧编号诊断。独立合成视频和 OS 截图用于区分播放时钟回退与可见画面回退。旧固定视频和既有验收下界继续作为原验收依据，新的诊断仍待 root 审阅及目标 macOS 执行。

## 2026-11-09 21:27 UTC · 前一 Desktop 终态与 Cocoa 配对对照

远端 `a7fce899` Desktop `42692999966` 于 21:26:05 UTC 终态 failure，6 个作业全部结束，5 个成功。Linux 主测 2159/2159，两个打包作业成功。Windows CPU 1478/1478，独立原生 6/6 且零跳过。macOS CPU 1537/1537、Metal 254/254，主原生 4/6，视频与 HTML 的隐藏暂停下界失败。同头 Runtime 13/13。前头整轮终态已满足本批推送前提，当前 Viewer 修改继续作为未提交开发。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42692999966/artifacts/13711373511) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

同头 fresh-visible 的 MP4 与 HTML 均暂停成功，DOM current_time 退回上一次 seek 位置。HTML 与 fresh-hidden 配对，两组前置历史和四个 OS 捕获阶段一致。隐藏时原生仍报 Playing、DOM 位置停在 seek，最终触发 watchdog。fresh-hidden MP4 在初始暂停阶段失败，缺少完整同头配对。时钟回退在持续可见时已复现，画面截图尚不能证明百毫秒级的解码帧回退。

## 2026-11-09 21:19 UTC · Project Runs 精确刷新与 MuPRO 文件身份

`0e5112ed` 通过 Hub 精确查询刷新已接受的 Project Runs 任务。旧节点缺精确读取能力时返回 unsupported 并保留最后观察，恢复现代节点能力后读回同一任务。底层 task.get 的旧节点兼容读取继续可用。真实严格 Bridge、Hub、NodeAgent 与 Runtime 复现了旧版缓存回退和错误的 not_found。持久回归在旧头失败，修复后 Python 3.11 联测 63/63。

`3ae33035` 让受约束的 MuPRO 文件登记、发布及 HDF5 读取复用描述符原生变化时间。Windows 取 ChangeTime，POSIX 取同一描述符的 ctime。覆盖同 inode、同大小且恢复 mtime 后的改写。集成 Claude68 `7241d850` 的严格 Bridge 回归，分别验证登记和发布拒绝链接目录，显式外部文件登记可用，换回真实目录后两条受约束入口可用。

Linux Python 3.11 联测 190 过、1 项 Windows 专属跳过。客户端矩阵定向 38/38，Python 3.14 定向 6 过、1 项 Windows 专属跳过，无 NumPy 回归 3/3。Linux 使用真实目录符号链接。Windows 的 NTFS 联接和原生 ChangeTime 仍待新头目标 CI。文件在末次服务端观察后仍可变更，真实 MuPRO 许可场景待验。

Claude69 已从 0e5112ed 在独立 worktree 开始 DAT Viewer 持久反例。已在合成运行中复现 Viewer 调用后用同大小、同 mtime 的改写改变图求值。待核对源证明在打开、后续步进和工作区恢复中的传递。

远端 `a7fce899` Desktop `42692999966` 仍在运行，4/6 作业通过。Windows CPU 1478/1478，macOS 原生对照及独立 Windows 原生仍运行。本地提交等待整轮终态。同头 Runtime `42692999627` 已终态 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

## 2026-11-09 21:03 UTC · MuPRO Bridge 发布结果校验

`f69edbe4` 把 MuPRO 结果行的最后复核移到 Bridge 发布请求。沿用结果单元格已有的路径和摘要，额外传原任务文件大小。服务端核对该运行、原生目录清单和内容，扫描目录后再次核对已读文件身份，最后按原句柄和修订提交。

集成 Claude67 `611b5e35` 的真实回环。旧头在发布调用处改写 HDF5 或替换成字节相同的目录链接时仍发布，两个反例按预期失败。修复后拒绝，恢复原文件即可重试同一任务。独立反例证明目录扫描期间的替换也被末次身份复核拦截。Python 3.11 联测 90 过、1 项真实许可条件跳过。Python 3.14 定向 12/12，隔离 wheel 4/4，5 个安装成员与候选字节一致。

真实本地项目发布 10,000 个合成文件，Bridge 请求约 1.66 MB。受控并发编辑与关闭分别得到修订冲突与句柄失效。调用方在校验后改写内存命令时，服务端提交原校验副本。文件在最后一次服务端观察后仍可变更，Windows 重解析点待目标平台实测。

远端 `a7fce899` Desktop `42692999966` 仍在运行，3 个作业通过。本地提交等待整轮终态。同头 Runtime `42692999627` 已终态 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

## 2026-11-09 20:45 UTC · MuPRO 收集文件登记一致性

`537b774b` 以原任务大小和 SHA-256 清单校验每批 MuPRO 结果文件。严格 Bridge 只登记规范项目内路径，在写入该批前拒绝链接、重解析点、大小或摘要不符。普通 Files 仍支持元数据登记和显式外部文件。全部批次后、结果行写入前再次复核清单。W5 二次登记保持项目内路径约束，冻结沿用原摘要校验。

集成并扩展 Claude66 `9f58670a` 的真实合成 Runtime 回归。旧头五个故障用例按预期失败。修复后同大小同 mtime 改写、换文件、父目录链接、登记后改写与 W5 重定向均被拒绝。恢复原文件后可显式重试同一任务，零重复提交或取消。Python 3.11 联测 86 过、1 项真实许可条件跳过。Python 3.14 定向与隔离 wheel 各 8/8。

校验期间其他项目操作可继续。受控并发编辑得到修订冲突，关闭得到句柄失效，两例均零索引行。观察之后文件仍可被修改。结果行校验在客户端发布调用前完成，未冻结本地文件。Windows 重解析点路径待目标平台实测。

远端 `a7fce899` Desktop `42692999966` 仍在运行，2 个作业通过，本地提交等待整轮终态。同头 Runtime `42692999627` 当前 10/13 作业通过。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42692999966) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42692999627)

## 2026-11-09 20:25 UTC · CLI 续读游标与前一 Desktop 终态

Claude65 的 `92c94ffd` 经 root 复验合入为 `4169e528`。CLI 中断时报告已经输出的字节位置，轮询仍用 Runtime 原游标。直连与 Hub 旧版红例各自报告 7，修复后从 6 续读，中文字符完整，正常 EOF 的残缺字符按替换字符输出并推进到末尾。若恰在输出写入中断，续读可能重放该段。

root 隔离候选的 Python 3.11 联测 120/120，Python 3.14 定向 4/4，均零跳过。此前旧 Runtime 末段重读的两项对照保持通过。

远端 `fa2ff5e2` Desktop `42679509572` 于 20:23:30 UTC 终态，5/6 作业通过，唯一失败是 macOS 主原生 4/6。Linux 主测 2156/2156，两个打包作业成功。macOS CPU 1537/1537、Metal 254/254，同 seek 保持可见对照随本批进入下一头。Windows CPU 1478/1478，Windows 原生 6/6 且每项 20 轮，零跳过。同头 Runtime 13/13。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42679509572/artifacts/13707666795) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

下一片为 MuPRO 结果收集在验证和登记之间的文件一致性。真实合成 Runtime 与 Bridge 回环已复现，待以相同原任务做拒绝和恢复对照。

## 2026-11-09 20:18 UTC · X7 单机链路切断样例

Claude64 的 `47e3cdde` 由 root 审阅修订后集成为 `127b0316`。`disconnect.py --scenario socket-partition` 在真实 NodeAgent 与 Hub 间主动关闭 TCP 隧道。两端保持运行，Runtime 在断线期间完成原任务，恢复后的首个精确答复返回同一任务成功。固定 stdout 和制品经真实 HubBackend 读取、下载并校验，只启动一次且 Hub 动作账本一致。

root 修复 pending connect 导致的排空与清理假成功，阻止切断前的连接跨越重开。失败回执清空 verified。三条回归在作者版按预期失败，在集成候选通过。另以真实断链只注入离线查询回退旧缓存，恰好 P4、P9 拒绝，其余 13 项通过，清理完整。

源码场景 15/15，约 36.49 秒。隔离 wheel 安装态场景 15/15，约 38.37 秒，12 个导入文件与主线摘要匹配。显式启用场景的最终联测 455/455，零跳过。单机主动关闭与静默丢包是不同故障，跨主机与原生桌面界面待验。严格 Bridge 子进程范围另见 19:54 UTC 诊断。

Claude65 已从 `ed08a0c9` 在独立 `claude/cli-log-resume-65` 修复另一处 CLI 中断续读问题。真实 Click 入口在读取 UTF-8 首字节后被中断，未输出字符却把游标从 7 报到 8。

远端 `fa2ff5e2` Desktop `42679509572` 的 Windows 原生 `129402349100` 仍在运行，本地提交等待整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572)

## 2026-11-09 20:04 UTC · Runtime 日志末段与 Cocoa 对照

`0458516a` 先读取 Runtime 任务状态再读日志，避免把末段写入前的空读取标成终态。CLI `logs --follow` 在连续两次收到空的终态响应后退出，兼容旧 Runtime。字节偏移与增量 UTF-8 解码保持原义，调度器更晚写入的日志仍可从最后游标续读。

用实际 worker 在 HTTP 读完空块后才放行写出末段并终止。旧服务把该读标成终态。另经真实直连和配对 Hub 注入旧版首次空终态答复，两组旧 CLI 都提前退出。修复后三项回归通过，跨块中文完整输出、游标按字节推进，当前 Hub 读取路径没有新增动作。最终 Python 3.11 Runtime、CLI、事件及桥接联测 118/118，Python 3.14 三项回归 3/3。

远端 `fa2ff5e2` 的 macOS CPU 1537/1537、Metal 254/254，主原生验收 4/6。新鲜隐藏诊断两项采样均完成。MP4 和 HTML 首次原生回复分别约 193、181 ms，均为 Playing。两次 DOM 采样均暂停并分别稳定在末次 seek 的 0.234、0.102 秒，比播放样本回退约 115、121 ms。两组均由一秒看门狗关闭。已在本地提交 `ded55b8a` 的同 seek 保持可见组等待下一轮目标平台对照。 [macOS 工件](https://github.com/sijintech/stk/actions/runs/42679509572/artifacts/13706450140)

同一 Desktop 轮次的 Windows CPU 1478/1478，零跳过，3 个 Linux 作业通过。独立 Windows 原生作业 `129402349100` 仍在运行，本地提交等待整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572)

Claude64 仍在独立 worktree 开发单机链路切断场景。root 已独立审阅本轮日志改动。

## 2026-11-09 19:54 UTC · Runtime 单实例与 X7 链路切断

`a5239e05` 为 D1 C-11 增加 Linux 真实 API 双进程回归。两个进程均请求临时端口，目录别名启动的第二实例被拒绝，首个 PID 记录与工作区仍可读取。SIGKILL 后在同一锁 inode 上恢复原工作区。部署与 Hub 单实例联测 17/17，外部副本禁用 flock 后第二实例持续运行，回归按预期失败。

Claude63 的 `ed59d42a` 由 root 审阅并修订为 `16dcd349`。MuPRO 试点文档补齐已发布的原生 HDF5 列出、显式选择和打开，以及只读查找重试。50 个本地链接检查通过。Linux 合成实窗验收与 Windows 客户端读取 CI 分开记录，真实许可输出、HDF5-only 完成与研究参考仍待验证。 [试点设计](design/mupro-executor-pilot.md)

在 `62b94d1a` 上用真实严格 Bridge、NodeAgent、Hub 与 Runtime 做了 X7 单机传输诊断。仅切断节点到 Hub 的 TCP 连接，Hub 在 18.82 秒后报告离线。三次精确读取均返回 unavailable，原任务在断线期间完成。恢复同一链路后的首个精确答复为同一任务成功，固定日志与产物摘要核对通过。只有一次程序启动，Hub 动作记录一致，零协议违规，子进程均已回收。跨主机分区与产品观察界面待验。

Claude64 已在独立 `claude/x7-socket-partition-64` 开始固化 opt-in Linux 场景及拒绝假绿的回归。root 负责审阅、独立复跑和集成。

远端 `fa2ff5e2` Desktop `42679509572` 仍在运行。3 个 Linux 作业通过，macOS CPU 和 Metal 通过，主原生 WKWebView 步骤失败且诊断继续，Windows CPU 测试运行中。同头 Runtime `42679509438` 终态 13/13。本地提交等待 Desktop 整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

PR #53 的原分支仍与当前 worker 退场逻辑冲突。PR #54 仍包含与现行路径冲突的交接文件。两个 PR 继续保留审阅状态。 [PR #53](https://github.com/sijintech/stk/pull/53) · [PR #54](https://github.com/sijintech/stk/pull/54)

## 2026-11-09 19:42 UTC · 切换任务后的制品打开复核

`91b9d860` 保留派发时的制品条目。用户切换任务后，迟到回执仍可履行原来的显式打开，并在打开前使用原制品摘要复核本地文件。缺少原摘要时使用同一传输回执，两份摘要冲突时拒绝打开。复核沿用 256 MiB 本地检查上限，读取固定长度的普通文件。

严格 Bridge 与真实 Runtime 回环用两个任务的同名 `result.txt` 核对完成事件先到、切到另一任务、原排队回执最后到。干净文件触发一次打开回调。同长度改写一个字节时，旧版仍发出打开回调，候选显示摘要校验失败且打开回调为零。两个分支均保留原传输终态及当前任务的制品行，零额外 RPC 和零契约违规。

同一任务的两次 PNG 另存为用不同目标。较晚的请求先得到回执，随后较早回执到达时保留最新制品行和预览，两份文件独立校验。另以实际旧任务错误回执验证当前任务的同名制品行和预览保持一致。

Jobs 定向 50/50，零跳过。新增的回执倒序与打开复核用例各连续通过 5 轮。精确文件读取的两个核心测试通过，覆盖拥有字节、链接和 FIFO。

Claude62 已在独立 worktree 完成初始派发回执探针及审阅报告。Claude63 已启动，负责在独立 `claude/mupro-pilot-doc-63` 更新一份 MuPRO 试点说明，对齐已发布的 HDF5 原生流程和真实许可验收边界。

远端 `fa2ff5e2` Desktop `42679509572` 仍在运行，3 个 Linux 作业通过。macOS CPU 和 Metal 通过后继续原生阶段，Windows 在执行 CPU 测试。同头 Runtime `42679509438` 终态 13/13。Linux Python 3.11、3.12、3.14 分别通过 6493、6510、6493 项，两个 Windows 客户端各通过 5250 项。本地提交等待 Desktop 整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

## 2026-11-09 19:27 UTC · 初始传输回执与 Cocoa 可见对照

`74ba6ff5` 将同一传输的后续观测用于迟到的上传和下载开始回执。回执仍绑定原用户操作，完成状态保留。上传文件列表刷新按原尝试去重，下载保留一次已授权的打开或制品校验。制品行按详情代次和最新请求标识绑定。

Claude62 在独立 worktree 的真实严格 Bridge 与 Runtime 回环复现了四个迟到场景。旧版把完成行退回排队，上传错误阻塞任务提交，普通文件没有触发打开，PNG 制品仍待校验。root 用同一探针复验候选，新文件和缓存命中的 PNG 均校验并生成一次预览纹理，普通输入触发一次系统打开回调，上传只刷新一次文件列表，显式任务提交发出一次。正常回执顺序的对照通过，严格桥零契约违规。重复终态事件保持同样的计数，完成事件后改写一个 PNG 字节会被制品校验拒绝。另跑了 120 次不延迟回执的真实回环。

Jobs 定向 48/48，零跳过。新增持久用例连续 10 轮通过，覆盖迟到回执下的上传、输入打开、制品校验与提交。

`ded55b8a` 为 MP4 和 HTML 视频增加同一 seek 历史的保持可见对照。可见组通过现有测试钩子调用同一原生暂停执行路径，隐藏组沿用实际切标签。两组先接收原生回复，首个 DOM 样本最早在原生派发 200 ms 后，第二个在首个回调 400 ms 后，回调均受原有一秒上限约束。记录两次采样分别相对暂停前和末次 seek 的差，以及样本之间的差。

Linux 构建及相邻 CTest 44/44，零跳过。独立核对两组的 C++ Apple 条件分支、四个用例的 CTest 注册和 macOS CI 证据归档。Apple SDK、Metal 和 WKWebView 实跑待目标 CI，诊断为非门禁。

远端 `fa2ff5e2` Desktop `42679509572` 正在运行，2 个作业已通过。Runtime `42679509438` 整轮 13/13 通过。本地提交等待当前 Desktop 的整轮终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42679509572) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42679509438)

## 2026-11-09 18:55 UTC · 传输完成状态与迟到回执

`d7fbc3f1` 按原传输 ID 记录桌面已采纳的观测。迟到的继续、取消回执或刷新快照保留请求后已采纳的变化。刷新列表若先观察到已知在途传输完成，复用已有完成处理，随后同一完成事件只更新显示。

Linux X11/Xvfb 1440×1600，软件 OpenGL、英文、缩放 1。固定起点为 Transfers 已打开、选中真实 Runtime 的已取消下载、Viewer 为空。两次点击刷新、继续，零滚动、零键入，只有列表和原 ID 的继续请求。真实桥依次交付运行、完成、原排队回执和原取消列表。旧版从完成 100% 退到排队 76%，再退到已取消 76%。新版在两份迟到快照后仍显示完成 100%。两版均校验同一文件的 2,755,000 字节，Runtime 工作区和 Viewer 保持一致。

另以 Jobs 和 Transfers 可见、已选工作区、另存对话框已打开、Viewer 为空为起点。三次点击、一组快捷键和绝对路径输入，零滚动。真实桥先返回已完成列表，1.531 秒后交付原完成事件。新版收到列表时即显示“已下载并校验”，后续事件保持该状态，两版的 1,570 字节 PNG 均通过摘要校验。两组旧版和最终候选进程均正常退出。

Jobs 原生定向 47/47、零跳过。持久用例覆盖两份旧快照和先完成列表两种顺序，并核对已知上传完成后仅刷新一次工作区文件。隔离 Python 3.11 全量 `7cdaece6` 为 6477 通过、180 跳过、4 排除、零失败。随后加入的晚到 Hub 拒绝修复已由此前 141 项定向联测覆盖。`c5b87b91` 显式取消新增 HDF5 夹具子进程的模型变量，以空模型 API key 重跑仿真与 HDF5 原生定向 20/20、零跳过。

Claude60 的独立 Linux 全量项目测试 937/937 通过。root 集成 Claude61 的 `c0a4c75c` 为 `9ac67dde`。查找重试持久用例在缺少按钮的旧版复现失败，当前一次重试只重读同一行。合并后的仿真与 HDF5 原生定向 20/20、零跳过。Claude62 已从传输修复头在独立 worktree 开始核查初始派发回执乱序。

远端 `15dff6ac` Desktop `42669507898` 于 18:59:02 UTC 结束，5/6 个作业通过。Linux 主作业 2142/2142，Windows CPU 1466/1466，Linux 打包和冷环境通过。macOS CPU 和 Metal 步骤通过，主原生验收的 MP4 和 HTML 视频仍失败。新的 Cocoa 诊断 2/2，分别在约 183 和 182 ms 收到 WebKit Playing，各两次 DOM 采样均为暂停，位置分别停在先前 seek 的 0.234 和 0.102 秒。两组都在原一秒窗口内确认了位置回退。下一步用同一 seek 历史做保持可见的暂停对照。Windows 原生 6/6，零跳过，18:59:01 UTC 结束。 [Windows 原生工件](https://github.com/sijintech/stk/actions/runs/42669507898/artifacts/13701368078) [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898) · [macOS 原生工件](https://github.com/sijintech/stk/actions/runs/42669507898/artifacts/13701990267)

## 2026-11-09 18:25 UTC · 原传输继续与 HDF5 回执回归

`7cdaece6` 将已取消的传输纳入桌面继续操作。直连下载使用原传输 ID。Hub 上传仅在核对原导入确已拒绝后推进审阅编号，并在派发前持久化下一次尝试。若批准先到，继续跟踪原动作。`abaf0a31` 覆盖原动作在查询与同 ID 重放之间才被拒绝的时序。

严格桥、Hub 和 Runtime 回环覆盖正常拒绝、拒绝已提交但回复丢失、拒绝在重放前到达、批准先到和旧尝试摘要。旧版本定向复现首次重试仍失败。最终联测 141/141 通过。另以实际 CLI 回环核对查询断连或 404 时保留原编号，派发回执丢失后复用冻结的新动作 ID。

Linux X11/Xvfb 1440×1600，软件 OpenGL、英文、缩放 1。固定起点为 Transfers 已打开、真实 Runtime 下载已取消且原行已选中，Viewer 为空。旧版点击继续零请求，仍为已取消。新版一次点击、零滚动、零键入，只发出原 ID 的 `transfer.resume`。原行最终显示 100%，本地文件 2,755,000 字节与 Runtime 登记 SHA-256 一致。已完成行的对照点击零请求。Viewer 像素、日志 ID 集合及远端工作区文件保持一致，两版进程正常退出。

`a6681a6f` 将禁用 NumPy 和 h5py 时的图源注册测试改为核对七个必需的版本化 ID，相关三模块 48/48。隔离 Python 3.11 全量 `49140b04` 为 6473 通过、180 跳过、4 排除、1 失败，唯一失败为原六项断言。包含修复和首版传输变更的隔离 Python 3.11 全量 `7cdaece6` 已启动。

root 从 Claude60 的独立 worktree 选择集成 `f1fc18b6` 为 `fa2ef209`。其 12 项请求与回执测试已由 root 用实际 CMake 目标注册和复验。加上 Transfers、Hub 上传和 MuFerro 按钮共 24/24，零跳过。 Claude61 的任务卡和启动器已备好，等待 Claude60 的独立全量原生测试和进程收尾后启动。

远端 `15dff6ac` Runtime `42669507521` 已结束，8/13 个作业通过。Linux 三个矩阵和 Windows 两个矩阵的唯一失败均为六图源旧断言。两项 Windows 作业各 5249 通过、273 跳过、872 排除、1 失败，后续客户端检查未运行。Linux 3.11 和 3.14 各 6488 通过、165 跳过，3.12 为 6505 通过、148 跳过。三个 Linux 作业各 4 排除、1 失败。Desktop `42669507898` 仍在运行，本地交付等待整轮终态。 [Runtime CI](https://github.com/sijintech/stk/actions/runs/42669507521) · [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898)

PR #53 的原分支与当前 worker 退场机制冲突。这里按现有桥契约独立修复可复现的取消重试。PR #54 的交接文件与当前路径存在大小写冲突，两个 PR 仍开着。 [PR #53](https://github.com/sijintech/stk/pull/53) · [PR #54](https://github.com/sijintech/stk/pull/54)

## 2026-11-09 18:07 UTC · MuFerro HDF5 查找重试与旧项目复验

`0b9b1c90` 在已收集的 MuFerro 运行记录查找失败时提供显式重试。点击后重新读取该运行的结果行，列表与打开仍由用户分别触发。仿真指南同步补充操作入口。

Linux X11/Xvfb 1440×1600，软件 OpenGL。固定起点为最大化 Project、已展开仿真运行记录、已选中原成功任务，Viewer 为空。通过严格桥在第一次真实结果行查询后返回可重试错误。旧版在刷新并重新展开后仍只有第一次查询。候选版一次重试仅补一次结果行查询。随后四次点击列出、展开选项、选择 Polar 第 2 步并打开，Viewer 显示 24 个体素，值域为 [0, 69]。两版均正常退出，项目修订 8，项目与 Runtime 记录和文件哈希保持一致。

同一显示环境以 `15dff6ac` 实窗复验。冷启动重开已收集项目，选中原成功运行后，HDF5 项目在空 Viewer 起点四次点击、零滚动打开原任务的 Polar 第 2 步。旧 DAT-only 项目在相同起点一次点击、零滚动打开普通畴 Viewer 的原末帧第 2 步。在同一会话从 HDF5 项目切到 DAT 项目再切回，之前的 HDF5 选择清空。显式重新列出时恢复四个选项，期间 Viewer、未发送草稿、项目修订和原 Runtime 任务保持原状。

原生构建及相邻 CTest 34/34 通过，零跳过。 `49140b04` 的隔离 Python 3.11 全量仍在运行。

Claude60 在独立 worktree 编写原生 HDF5 请求与回执回归。root 已验证本次用户流程并负责后续审阅与发布。

远端 `15dff6ac` Desktop `42669507898` 仍在运行，1 个作业已通过。Runtime `42669507521` 已通过 8/13 个作业。本地修复等待前一 Desktop 运行的完整终态。 [Desktop CI](https://github.com/sijintech/stk/actions/runs/42669507898) · [Runtime CI](https://github.com/sijintech/stk/actions/runs/42669507521)

复查 PR #53 和 #54。#53 旧实现与当前 worker 退场、重试归并机制冲突。独立回环发现已取消的 Runtime 下载可立即按原 ID 重试。审阅中取消的 Hub 上传第一次重试仍会复用已拒绝的导入动作，第二次才发起新审阅。桌面开放全部已取消传输的重试前，需先修复该动作轮换。#54 的归档标签和快速启动入口已核对，其新增文件与现有交接文件在大小写不敏感文件系统上冲突。 [PR #53](https://github.com/sijintech/stk/pull/53) · [PR #54](https://github.com/sijintech/stk/pull/54)

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
