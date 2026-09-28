# 文档预览技术验证计划

状态：2026-09-28 已核对当前代码和官方接口；**尚未实现嵌入原型，也未完成选型**。
这是 P0 的验证任务，不表示 P4 的 Markdown、HTML、PDF 或 LaTeX 已交付。
产品范围见[项目工作台](project-workbench.md)，当前文件入口见[项目文件](../project-files.md)。

## 当前约束

STK 的新桌面由 GHOST 创建窗口，自有 UI 绘制菜单、表格和区域，三维视图使用原生 GPU。
不能把 Web 组件能在一个独立示例窗口运行，视为它能正确嵌入 STK 的可拆分区域。

代码核对结果：

- [`wm::Window`](../../desktop/engine/lib/stk_wm/include/stk/wm/window.hh) 已提供 `ghost_window()`，
  返回 `GHOST_IWindow*`，不是平台窗口句柄；还有窗口销毁回调。
- GHOST 的 `getOSWindow()` 位于内部 `GHOST_Window` 类，Win32 返回窗口句柄、Cocoa 返回 `NSWindow`。
  不应假定可以直接在 `GHOST_IWindow` 上调用它。后续适配应集中在窗口层，避免各编辑器包含 GHOST 内部头文件。
- [`DrawContext`](../../desktop/engine/lib/stk_wm/include/stk/wm/screen.hh) 提供窗口、区域像素矩形与 UI 比例，
  无窗口渲染时 `window` 为空。原生子视图需要窗口生命周期，不能复用现有离屏截图就宣称嵌入成功。
- 菜单、弹窗、拖拽分隔线和最大化都由自有 UI 处理。浏览器子窗口盖住菜单、抢走快捷键，或切换标签后仍接收输入，
  都属于阻止采用的交互问题。
- 当前图像截图和三维导出走 GPU 路径；平台浏览器视图是否进入窗口截图需另测，不能默认会被 GPU 导出捕获。

## 首轮比较

优先验证 macOS 的 WKWebView 与 Windows 的 WebView2；将 Qt WebEngine 留作可比较的替代方案。
这个优先级是根据现有原生桌面架构作出的工程判断，不是已经确定的产品依赖。

| 路线 | 已确认的接口或部署要求 | STK 必须实际验证的部分 |
|---|---|---|
| macOS WKWebView | 本地文件加载可限定可读取的文件/目录；可通过自定义 URL scheme 提供资源 | Cocoa 子视图与 Metal 区域共存，坐标翻转、Retina、输入法、菜单遮挡、关闭回调 |
| Windows WebView2 | 支持 HWND 窗口承载与可视化合成承载；需要 WebView2 Runtime；UI STA 线程及消息循环 | OpenGL 窗口中的区域裁剪、DPI 切屏、IME、焦点进出、运行时缺失和离线安装 |
| Qt WebEngine | QWebEngineView 是 QWidget；需部署 WebEngine 库、辅助进程、资源和翻译 | 同时引入 Qt 事件/窗口体系的成本，实际发行体积及双平台分发，不因仓库保留旧 Qt UI 就视为零成本 |

上述接口来源：[Apple 本地内容加载](https://developer.apple.com/documentation/webkit/wkwebview/loadfileurl(_:allowingreadaccessto:))、
[Apple 自定义资源协议](https://developer.apple.com/documentation/webkit/wkurlschemehandler)、
[WebView2 承载方式](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/windowed-vs-visual-hosting)、
[WebView2 线程模型](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/threading-model)、
[WebView2 分发](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)、
[Qt 视图](https://doc.qt.io/qt-6/qwebengineview.html)、
[Qt 分发](https://doc.qt.io/qt-6/qtwebengine-deploying.html)。

Windows 先测窗口承载，其输入和焦点支持可减少原型代码；如果无法满足菜单覆盖和裁剪，再验证合成承载。
合成承载需要处理更多输入与图形集成，不能只换一个创建函数就认为解决了遮挡。
不在原型前承诺安装包大小或最低内存；分别测量启动、空闲、打开文档和关闭后的进程及资源占用。

Linux 继续运行现有桌面；首轮原型允许文档区明确显示暂不支持并提供已有系统打开入口。
Linux 正式预览后端需单独选型，不把 macOS/Windows 方案的通过扩展成三平台能力。

## 文档内容与资源

首轮固定使用仓库内可复现的测试文档，禁止测试时从 CDN 下载脚本或字体。候选流程是：

1. Markdown 转成受约束的 HTML，覆盖中英文、代码块、表格、数学内容与项目图片。
2. HTML 报告显示保存的页面和资产；项目表格仅显示标题、类型、版本和缩略摘要。
3. PDF 比较平台现有预览与随应用打包的 PDF.js，逐项检查页码、缩放、搜索、复制与链接。
4. 文档区把加载失败、资源缺失和格式不支持作为可读状态，不替换掉项目或执行关联程序。

PDF.js 提供可复用的 viewer，但其官方说明指出 `file://` 下 worker 不启用；
不能只双击 HTML 验收正式加载路径。是否采用自定义资源协议、平台虚拟主机映射或受限本机服务，
须通过字体、worker、中文路径和 PDF 资源读取测试后选择。
来源：[PDF.js 入门](https://mozilla.github.io/pdf.js/getting_started/)、
[WebView2 本地内容](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/working-with-local-content)。

资源协议必须区分以下身份：项目 UUID、资源记录 UUID、当前文件或明确输入版本、此次预览会话。
不得因为打开了一个报告就把整个项目目录、`.stk` 输入历史或用户主目录授权给页面。
优先由资源清单确定可读内容；关闭/切换项目使旧请求失效。路径规范化及符号链接边界使用与文件索引一致的规则，
外部资源须明确解析，不能把任意相对 URL 当作本机路径。

首轮只显示内容，不给页面注入 Python、数据库编辑、Runtime 提交或通用 shell 对象。
链接跳转、下载、新窗口和网络请求分别受控；默认文档测试应能完全离线运行。
如果后续交互报告需要调用项目操作，应独立定义经过校验的能力，不复用内部桌面 stdio 桥。
这落实工作台既有资源访问约束，不新增用户审批流程。

## 可独立验收的原型包

原型使用单独构建选项，默认发行构建不增加浏览器依赖。先连接真实的 GHOST 主窗口和一个可缩放区域，
验证成功后再接文件索引；不能把浏览器放在另一个独立窗口当作“嵌入完成”。

| 检查 | 必须保留的证据 |
|---|---|
| 区域布局 | 分隔线拖拽、最大化/恢复、标签切换、关闭区块后没有残留子窗口；与 Viewer 同时可见的截图 |
| 输入 | 中英文输入法、复制/搜索、Tab 进出、全局快捷键；文档内快捷键不误触项目操作 |
| 菜单与弹窗 | 菜单横跨文档区仍可见可点击，弹窗和拖拽提示不被子窗口遮挡 |
| 缩放 | 100/150/200% 与跨屏 DPI，内容与区域边界不漂移；缩放不改变项目数据 |
| 资源 | 空格/中文/`#`/`%` 文件名、缺失图片、关闭后异步回调、不同项目同名文件不串用 |
| HTML | 离线资产、禁止的外链/新窗口、脚本错误，刷新后保持来源和版本 |
| PDF | 多页、搜索/复制中文、缩放、旋转、字体和透明图；大文件取消后及时释放 |
| 分发 | 干净 macOS/Windows 环境；Windows Runtime 缺失提示；移动应用目录后可加载内置资源 |
| 性能 | 开启和关闭 20 次无持续增长；大型文档加载期间表格/Viewer 保持响应；报告测试文件及测量方法 |

许可证、第三方 notices、固定资源版本、浏览器更新责任和离线部署机制在采用前记录，
本调研不作法律结论或把尚未测量的依赖体积写成数字。

P0 的退出结果应是“选定一个经过双平台嵌入验证的方案”或“记录阻断原因并转入下一候选”。
P4 再交付项目关联、持久报告、导出资产、LaTeX 编译节点和完整文档体验；不能以本文件代替运行原型。
