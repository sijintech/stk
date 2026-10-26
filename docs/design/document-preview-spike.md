# 文档预览技术验证计划

状态：2026-10-25 **原生候选仍默认关闭，正式报告视口候选源码 `023aa66` 已接入，尚未完成双平台选型验收**。
前头 `43e5652` 的 macOS 原型已通过 20 轮／161 张自身窗口 OS 图、关闭与引擎静态析构后 guarded 0 块／0 字节门禁；
Windows 编译与 CPU 已过，独立原生预检因运行器仅提供 OpenGL 1.1 而失败，尚无实际显示验收。
这些 P0 原型结果不表示正式 P4 报告、PDF 阅读体验或 LaTeX 已交付。
产品范围见[项目工作台](project-workbench.md)，当前文件入口见[项目文件](../project-files.md)。

## Windows 测试用软件渲染路径（待 CI 验证）

`43e5652` 的 Windows 运行器仅提供 OpenGL 1.1，尚未到达 WebView2／OS 图像检查。
本工作树的独立验收 job 将固定 SHA／大小的 pal1000 Mesa 26.2.4 MSVC 归档中两个 x64 DLL
放到验收 exe 目录，显式请求 llvmpipe；这是该发行者的构建，不是 Mesa 官方二进制。
只解包指定 DLL，记录归档目录与 DLL 摘要，不运行安装脚本，不替换系统驱动、DXGI 或 D3D。
本机下载超时，真实包目录与依赖仍待 CI 实际检查，失败即终止。

测试源在 legacy 和真实 4.3 core context 中分别记录 GL vendor／renderer／version 和实际加载的
`opengl32.dll` 完整路径；显式软件模式必须确为 llvmpipe，拒绝 GL／GLSL／GLES 版本覆盖。
WGC 自有窗口捕获显式选择 WARP，记录实际 DXGI software adapter 与 feature level，无硬件失败后的自动回退。
仍须平台支持、准确客户区、独立 OS 帧、20 轮／关闭和最终 guarded 门禁全部通过；软件路径不作硬件性能或浏览器内存结论。

依据：[Mesa LLVMpipe 的 Windows 局部部署](https://docs.mesa3d.org/drivers/llvmpipe.html)、
[Microsoft WARP 创建](https://learn.microsoft.com/en-us/windows/win32/direct3d11/overviews-direct3d-11-devices-create-warp)、
[WGC 能力与捕获流程](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture)。
WARP 可创建 D3D 设备不单独证明当前 Hyper-V 会话可捕获，实际像素检查仍是门禁。

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

生产资源协议和平台适配位于 [`desktop/engine/lib/stk_document/`](../../desktop/engine/lib/stk_document/)，
原型夹具和 OS 捕获保留在 [`desktop/spike/document_preview/`](../../desktop/spike/document_preview/)，二者消费同一平台实现。
`STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW` 默认 `OFF`，显式开启才选择 macOS／Windows 原生后端；
`STK_DESKTOP_BUILD_DOCUMENT_PREVIEW_SPIKE` 也默认 `OFF`，单独控制原型及像素证据目标。
纯 CPU 生产资源测试不再依赖开启原型，关闭 Blender 仍可构建。
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
cmake -S desktop -B build-desktop -DSTK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW=ON -DSTK_DESKTOP_BUILD_DOCUMENT_PREVIEW_SPIKE=ON
cmake --build build-desktop --config RelWithDebInfo --parallel 4 --target stk-document-preview-spike stk-document-resources-tests
ctest --test-dir build-desktop -C RelWithDebInfo -R '^(DocumentResources|DocumentEvidence)\.' --output-on-failure
```

macOS 在有真实桌面会话的机器上使用 Metal；第一条运行自动生命周期冒烟，第二条保留窗口供手工验收：

```sh
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ./build-desktop/bin/stk-document-preview-spike --gpu-backend metal --smoke --require-native --cycles 20 --evidence-dir ./native-evidence-macos
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ./build-desktop/bin/stk-document-preview-spike --gpu-backend metal --require-native
```

Windows 在已安装 WebView2 Runtime、具有真实桌面会话的机器上使用 OpenGL，PowerShell 命令为：

```powershell
$env:STK_TOKEN_PLAN_API_KEY = ''
Remove-Item Env:STK_TOKEN_PLAN_MODEL -ErrorAction SilentlyContinue
& .\build-desktop\bin\stk-document-preview-spike.exe --gpu-backend opengl --smoke --require-native --cycles 20 --evidence-dir .\native-evidence-windows
& .\build-desktop\bin\stk-document-preview-spike.exe --gpu-backend opengl --require-native
```

以上程序路径按单配置生成器示例书写；Visual Studio 等多配置生成器可能有配置子目录。
配置时还会在 `build-desktop/spike/document_preview/native-smoke-<配置>.txt` 写出该配置的准确可执行文件路径和冒烟命令，
该命令已包含 20 轮和证据目录。自动原生验收必须同时提供 `--smoke --require-native --cycles 20 --evidence-dir DIR`；
人工 `--require-native` 仍可运行交互窗口。`--require-native` 防止把 Linux 的不支持状态当作原生嵌入通过。
手工窗口可使用文档栏的 `HTML`、`PDF`、`Focus`，并检查下方原验收表；冒烟不会代替人工点击数、输入和 PDF 阅读验收。

只验证资源清单、路径和会话边界时，可在另一个目录关闭 Blender，不需要原生浏览器或窗口；
其余工具链和 CPU 依赖仍按桌面构建说明配置：

```sh
cmake -S desktop -B build-document-cpu -DSTK_DESKTOP_WITH_BLENDER=OFF -DSTK_DESKTOP_BUILD_DOCUMENT_PREVIEW_SPIKE=ON
cmake --build build-document-cpu --config RelWithDebInfo --parallel 4 --target stk-document-resources-tests stk-document-evidence-tests
ctest --test-dir build-document-cpu -C RelWithDebInfo -R '^(DocumentResources|DocumentEvidence)\.' --output-on-failure
```

CTest 资源测试入口将模型 key 置空并移除模型配置。关闭 Blender 时，文档预览部分只生成资源与像素判据测试，不生成窗口候选目标。
guarded STK 分配检查在引擎的函数局部静态对象析构后执行：在 Runtime 初始化分配器之后、首次启动引擎之前登记退出检查，
只有最终零块／零字节与完整生命周期及图像证据都成立，才保存成功 JSON。Runtime 作用域结束时的计数只作诊断，
不能把 Metal 仍活着的懒静态对象提前判为泄漏；最终真实泄漏仍失败，先前运行错误也不能被最终零计数覆盖。
启用原型且保留 Blender 时，可在没有显示设备的环境验证这三个严格退出码自检：

```sh
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir build-desktop -C RelWithDebInfo -R '^document_preview_memory_' --output-on-failure
```

正例实际持有晚析构的 guarded 分配；反例分别故意泄漏与提前失败，包装器要求准确退出码与诊断，崩溃或超时不能算通过。
该检查只覆盖 guarded 分配器管理的对象；
它不证明 WebKit／WebView2 子进程内存没有持续增长，浏览器内存与进程释放还需独立采样。
本段是复现入口，不是任何平台已经通过的记录；实际结果另写入[运行验收](../runtime-validation.md)。

## 布局与视图生命周期

候选通过 `Screen::observe_layout` 在完整 UI 布局结束后同步本区域，不再依赖主循环外侧逐个轮询宿主。
订阅为可取消的 RAII 句柄；切换标签、最大化、几何或布局替换先立即撤销原生可见性，完成新布局后再解析当前所有者。
隐藏编辑器仍接收布局通知；没有 UI／窗口时隐藏，关闭编辑器或父窗口先取消订阅、关闭子视图并失效资源。
订阅不跟随布局树迁入另一 Screen，宿主需要重新绑定；回调不得保留 Widget／Layout 指针或直接改树。
普通重绘不触发失效，避免每帧撤焦。所有模态框隐藏子视图，其他相交浮层也暂时隐藏。
原型仍占整个 main 区域。正式 ReportsEditor 另使用 `NativeViewport`，在最终布局核对视口、区域和窗口裁剪，
部分可见则隐藏，不能把缩小子窗口当作原布局的裁剪。
UI 在弹层和捕获变更前同步通知原生宿主；区域移除及跨 Screen 迁移前撤销会话，项目范围变化不等下一帧处理。
这仍不能拦截已经派发到 OS 子视图的输入，也不证明全局快捷键、IME 或跨屏 DPI 已验收。

## 自动原生显示证据

自动验收直接捕获原型自己的 STK 窗口：macOS 使用 ScreenCaptureKit 的当前进程窗口与单窗口过滤，
Windows 使用 Windows Graphics Capture 的指定 HWND；不读取整张桌面或其他应用窗口。
macOS 的证据工具运行时要求 14.4，产品最低 13.3 与普通候选运行不因此改变。
Windows 在创建 GHOST 窗口前核对 DPI 和 OpenGL 4.3；没有能力时记录失败，避免驱动错误对话框阻塞 CI。
不自动安装浏览器 Runtime、显示驱动或修改截屏权限。

两份 HTML 含顺序不同的六色色条，宿主 GPU 不绘制这些标记。每阶段需要两次独立 OS 捕获匹配，
显示时在文档矩形内找到正确标记，隐藏时在整个客户区均不能找到两种标记，并要求宿主存在非空彩色采样。
固定 20 轮覆盖显示、切换 Python、恢复、最大化 Viewer、恢复、导航第二页、缩放窗口和关闭标签；
最后在导航期间关闭父窗口。全部成功产生 161 张最终 PNG、对应 SHA256 与 `result.json`。
关闭时同时核对实际子视图状态和旧资源 URL 的 410；异常保留失败 JSON 和已有图像。

macOS CI 实际执行原生测试；Windows 独立验证作业消费同头编译的候选包并实际执行。
权限、显示设备、OpenGL、Runtime 缺失或像素不匹配均失败，不计为跳过或嵌入成功。
这套证据入口仍须以具体提交的 CI／实机结果判定；编译和 CPU 像素测试不能证明 OS 捕获通过。
OS 合成截图不证明物理屏幕扫描输出、PDF／IME／跨屏 DPI 验收或浏览器子进程内存稳定。
仍按下方验收表记录人工输入、截图检查和浏览器进程占用。

依据：[Apple 当前进程窗口](https://developer.apple.com/documentation/screencapturekit/scshareablecontent/getcurrentprocessshareablecontent(completionhandler:))、
[Windows 指定窗口捕获](https://learn.microsoft.com/en-us/windows/win32/api/windows.graphics.capture.interop/nf-windows-graphics-capture-interop-igraphicscaptureiteminterop-createforwindow)、
[Windows DPI 初始化](https://learn.microsoft.com/en-us/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process)。

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
