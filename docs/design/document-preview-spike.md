# 文档预览技术验证计划

状态：2026-10-25 **已实现默认关闭的原生嵌入候选源码，正在等待本机与跨平台验收，尚未完成选型**。
当前没有 macOS／Windows 的实际运行验收证据。这是 P0 的验证任务，不表示 P4 的 Markdown、HTML 报告、
PDF 阅读体验或 LaTeX 已交付。
产品范围见[项目工作台](project-workbench.md)，当前文件入口见[项目文件](../project-files.md)。

## 当前约束

STK 的新桌面由 GHOST 创建窗口，自有 UI 绘制菜单、表格和区域，三维视图使用原生 GPU。
不能把 Web 组件能在一个独立示例窗口运行，视为它能正确嵌入 STK 的可拆分区域。

代码核对结果：

- [`wm::Window`](../../desktop/engine/lib/stk_wm/include/stk/wm/window.hh) 提供 `native_window_handle()`，
  在窗口仍存活时借用 `NSWindow*`／`HWND`，并提供窗口销毁前回调。原有 `ghost_window()` 返回
  `GHOST_IWindow*`，不是平台窗口句柄。
- GHOST 的 `getOSWindow()` 位于内部 `GHOST_Window` 类，Win32 返回窗口句柄、Cocoa 返回 `NSWindow`。
  不应假定可以直接在 `GHOST_IWindow` 上调用它；现有适配集中在窗口层，编辑器不包含 GHOST 内部头文件。
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

Linux 继续运行现有桌面；当前候选的文档后端明确返回 `Unsupported`，不会创建浏览器子视图。
产品已有的系统打开入口不因此改变，原型不会自动启动外部应用。
Linux 正式预览后端需单独选型，不把 macOS/Windows 方案的通过扩展成三平台能力。

## 候选源码与有限使用

实现位于 [`desktop/spike/document_preview/`](../../desktop/spike/document_preview/)。
`STK_DESKTOP_BUILD_DOCUMENT_PREVIEW_SPIKE` 默认 `OFF`；只有明确开启时才添加候选及资源测试目标。
macOS 使用同一 GHOST 窗口中的 WKWebView，Windows 使用该窗口承载的 WebView2。
原型在同窗 Viewer 打开仓库公开的 payload 示例，不启动桌面桥，不读取用户项目，不发起模型请求。

文档资源仅为四个内存资产：`index.html`、`next.html`、`图 像#%.png` 和两页英文合成 `fixture.pdf`。
HTML 包含中文、表格、代码、静态数学文本、输入法／剪贴板输入框、滚动内容及明确点击的拒绝动作检查。
每次打开使用独立资源会话；没有 Markdown 转换、LaTeX 编译或 PDF.js。
PDF 按平台现有能力尝试显示，失败须保留可读状态。

资源只从显式清单提供；页面脚本、外部导航、下载、新窗口和通用主机桥被禁用。
这些文档请求门禁**不证明浏览器 Runtime 的更新、遥测等后台活动绝对没有网络流量**，离线部署仍需实际验证。
macOS 使用非持久网站数据，Windows 使用独立 InPrivate 预览配置；这也不是“运行过程完全不写磁盘”的承诺。
Windows 构建按固定版本和摘要取得 WebView2 SDK，运行时缺少 WebView2 Runtime 会显示错误，**不会自动安装 Runtime**；
离线构建可将 `STK_WEBVIEW2_SDK_URL` 指向同一归档的 `file://` URL，摘要校验仍保留。

菜单或弹窗与文档区域相交，以及拖动区域边界时，候选暂时隐藏原生子视图并移出焦点，随后恢复。
这是当前窗口承载方案的限制，不是已实现无缝菜单叠加。`parent_attached`／`visible` 查询核对实际平台状态，
`Ready` 表示浏览器导航完成；这些状态与窗口帧计数都不证明屏幕已呈现内容，也不替代 OS 截图、IME 或跨屏 DPI 验收。

在仓库根目录使用**已经配置并可构建桌面的目录**，保留原来的工具链、依赖和 GPU 设置。
下面以 `build-desktop` 为例；先完成构建，再运行程序或测试，不并行重链正在使用的二进制：

```sh
cmake -S desktop -B build-desktop -DSTK_DESKTOP_BUILD_DOCUMENT_PREVIEW_SPIKE=ON
cmake --build build-desktop --config RelWithDebInfo --parallel 4 --target stk-document-preview-spike stk-document-resources-tests
ctest --test-dir build-desktop -C RelWithDebInfo -R '^DocumentResources\.' --output-on-failure
```

macOS 在有真实桌面会话的机器上使用 Metal；第一条运行自动生命周期冒烟，第二条保留窗口供手工验收：

```sh
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ./build-desktop/bin/stk-document-preview-spike --gpu-backend metal --smoke --require-native --cycles 20
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ./build-desktop/bin/stk-document-preview-spike --gpu-backend metal --require-native
```

Windows 在已安装 WebView2 Runtime、具有真实桌面会话的机器上使用 OpenGL，PowerShell 命令为：

```powershell
$env:STK_TOKEN_PLAN_API_KEY = ''
Remove-Item Env:STK_TOKEN_PLAN_MODEL -ErrorAction SilentlyContinue
& .\build-desktop\bin\stk-document-preview-spike.exe --gpu-backend opengl --smoke --require-native --cycles 20
& .\build-desktop\bin\stk-document-preview-spike.exe --gpu-backend opengl --require-native
```

以上程序路径按单配置生成器示例书写；Visual Studio 等多配置生成器可能有配置子目录。
配置时还会在 `build-desktop/spike/document_preview/native-smoke-<配置>.txt` 写出该配置的准确可执行文件路径和冒烟命令，
可在该命令后增加 `--cycles 20`。`--require-native` 防止把 Linux 的不支持状态当作原生嵌入通过。
手工窗口可使用文档栏的 `HTML`、`PDF`、`Focus`，并检查下方原验收表；冒烟不会代替人工点击数、输入和 PDF 阅读验收。

只验证资源清单、路径和会话边界时，可在另一个目录关闭 Blender，不需要原生浏览器或窗口；
其余工具链和 CPU 依赖仍按桌面构建说明配置：

```sh
cmake -S desktop -B build-document-cpu -DSTK_DESKTOP_WITH_BLENDER=OFF -DSTK_DESKTOP_BUILD_DOCUMENT_PREVIEW_SPIKE=ON
cmake --build build-document-cpu --config RelWithDebInfo --parallel 4 --target stk-document-resources-tests
ctest --test-dir build-document-cpu -C RelWithDebInfo -R '^DocumentResources\.' --output-on-failure
```

CTest 资源测试入口将模型 key 置空并移除模型配置。关闭 Blender 时，文档预览部分只生成资源测试，不生成窗口候选目标。
自动打开／关闭循环末尾的 guarded STK 分配检查，只覆盖该分配器管理的对象；
它不证明 WebKit／WebView2 子进程内存没有持续增长，浏览器内存与进程释放还需独立采样。
本段是复现入口，不是任何平台已经通过的记录；实际结果另写入[运行验收](../runtime-validation.md)。

## 文档内容与资源

首轮固定使用仓库内可复现的测试文档，禁止测试时从 CDN 下载脚本或字体。
当前四资产夹具之外，以下仍是后续比较范围：

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
