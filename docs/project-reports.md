# 冻结项目报告

报告把一份 Markdown、HTML、PDF、MP4 或文本入口与选定资产保存在项目中，关闭并重新打开后仍读取同一份快照字节。
报告还可以记录当时选定的上下文及运行状态。它使用普通项目表和已有文件快照，不创建第二套运行系统。
创建、读取、预览和导出均不会执行分析、启动任务或发送模型请求。

报告存储、离线 Markdown／HTML 净化渲染接口及独立桌面报告标签和创建表单已有交付。
源码 `023aa66` 已接入正式报告页的独立 Markdown／HTML／PDF 视口候选；原生后端仍默认关闭，实际验收状态见
[运行记录](runtime-validation.md)。AI 报告表单及三模式布局已接入并完成本机专项；PDF 平台阅读验收、
LaTeX 主链已完成本机与真实工具链验证，见[编译指南](latex-workflows.md)。MP4 预览正在按 P4 接入；
平台实际播放、文档显示与交互仍以验收记录为准，不能据此标记完整 P4 完成。
原生后端的复现入口及尚需验证的交互见[文档原型](design/document-preview-spike.md)。

## 创建一份报告

先把入口与图片等资源登记为[项目文件](project-files.md)，再明确捕获同一份[输入快照](project-snapshots.md)。
快照需要项目格式至少为 4；打开旧项目不会自动升级。

在 **报告 / Reports** 页展开 **创建报告**，点击 **读取输入快照**，从摘要页中选择快照。
列表每页至多 64 项，只读取摘要；选择后核对这一份完整冻结清单，不读取资产正文。
输入标题，选择文件并勾选 **加入所选文件**；需要时编辑报告内路径，再明确 **设为报告入口**。
文件列表和已选资产分别显示，入口以 ▶ 标记。按 Enter 完成文字编辑后点击 **创建报告**，
才校验冻结资产字节并提交一次项目编辑；成功后打开新报告的元数据，不自动读取或执行入口。

创建草稿随完整工作空间保存，普通布局不保存草稿。恢复草稿、项目修订变化或桥重连后，
必须明确 **核对冻结快照** 才能创建。草稿不包含主机路径、资产字节或活动句柄，关闭标签也会保护未保存草稿。
创建回执不确定时保留原报告 UUID 和清单；点击 **查询原报告 UUID** 只读核对，
即使暂未找到也不自动重新创建。只有确认了解可能已存在报告后，才可勾选并明确放弃待确认身份。

需要额外来源时，展开 **额外来源（可选）**，选择冻结上下文、仿真运行、分析运行或工作流运行，
再点击 **读取来源元数据**。列表每页 8 项；选择后点击 **加入所选来源**，总数最多 16 项。
点击 **核对所选来源** 才读取完整冻结来源，可逐页检查上下文值、省略与诊断，以及运行真实状态。
这不会执行、恢复或刷新运行，也不会读取运行产物或发送模型请求。运行状态不代表结果已通过科学验证。

草稿只保存来源类别和 UUID，恢复、换项目、桥重连或修订变化后需明确重新核对。
创建读取来源时比较完整摘要：即使项目修订未变，若当时观察已不同也会拒绝写入，需再次核对后明确创建。
比较通过后，该次来源捕获值随报告冻结；之后运行推进不会改写它，也不承诺落库时仍是最新状态。
来源过大时明确失败，不截断证据。丢失创建回执仍按原报告 UUID 和完整清单摘要核对，不自动重发。
完整富文档和 AI 报告继续按 P4 推进。

以下代码在 STK 的 Python 页显式运行，
`report.md` 和 `plot.png` 应当已经位于项目目录中：

```python
from uuid import uuid4

p = stk.project
revision = p.catalog()["project"]["revision"]
indexed = p.files.index(["report.md", "plot.png"], expected_revision=revision)
records = indexed["record_ids"]
frozen = p.snapshots.capture(records, expected_revision=indexed["revision"])
report_id = str(uuid4())
saved = p.reports.create(
    "实验报告", frozen["snapshot"]["id"], records[0],
    [{"record_id": records[0], "path": "report.md"},
     {"record_id": records[1], "path": "plot.png"}],
    report_id=report_id, expected_revision=frozen["revision"], sources=[],
)
```

入口正文可以用 `![结果](plot.png)` 引用该图片。`path` 是导出包内的虚拟相对路径，
不能是绝对路径、包含 `..`、反斜杠或跨平台重名；资源后缀须与原文件的 MIME 一致。
单份报告从一份快照中选择资产，每个文件记录只能出现一次，入口必须恰好被选中。
新报告使用新 UUID；相同名称可创建多份，重复 UUID 会冲突。创建是一次可撤销的项目编辑。

可选 `sources` 只选择已有对象，如 `{"kind": "context", "id": context_id}`、
`simulation_run`、`analysis_run` 或 `workflow_run`。上下文保存当时的选择、值、省略及诊断；
运行保存计划摘要和捕获时的状态，包括未开始、失败和未完成状态。之后运行推进不会改写报告。
这不是重新计算，也不保证科学结果有效；运行计划摘要和输出文件摘要含义不同。

Python 调用方可用 `reviewed = p.reports.review_sources(sources, expected_revision=revision)` 显式读取
完整来源，并在 `create(..., sources=sources, expected_sources_sha256=reviewed["sources_sha256"])`
中绑定该次复核。`sources_sha256` 只标识有序来源数组；不等于报告的 `source_sha256` 或资产摘要。
省略该可选参数时保留既有行为，创建时捕获最新已保存的观察。

## 从已完成的模型回复保存报告

桌面表单、Python 和桥共用专用 `stk.report-draft/1` 请求与 `stk.report/2`。
普通文件报告保持 `/1`。生成报告把编辑后的正文保存在报告记录中，额外图片等资源仍来自真实文件快照，
不把生成正文伪装成文件索引或输入快照。版本与预算见[生成报告契约](specs/report-2.md)。

在 **报告 / Reports** 页展开 **生成报告**，在 **报告证据** 中读取并添加已保存的上下文及需要的运行来源，
至少包含一个上下文。需要图片或 MP4 时，展开 **可选冻结图片与视频**，读取快照、选择资产并核对报告内路径；
没有图片时无需选择快照。点击 **核对所选来源** 后可分页检查完整证据，再选其中一个作为 **主上下文**。

选择现有端点和模型，输入 **报告要求**。Enter 换行，Ctrl+Enter（macOS 为 Command+Enter）完成文本编辑。
点击 **准备请求** 只保存要求并冻结证据，不发送；核对后再点击 **发送一次并生成**。
收到完整回复后，可编辑标题、Markdown／HTML 入口路径和 **可编辑报告原文**，再明确点击 **保存冻结报告**。
保存后列表选择新报告的元数据，不自动读取资产或预览；**完整冻结请求证据** 和 **原始完整回复** 分别保留，
编辑正文不会替换原始回复。需要另一份报告时点击 **新建报告草稿**。

每个报告标签保留独立草稿；完整工作空间保存选择、文本和原请求身份，普通布局不保存生成草稿。
恢复后不会复核来源、发送、恢复任务或读取资产。未准备的输入需要重新核对；已准备的请求先点击
**查询原请求或保存结果**，核对后才能继续操作。丢失发送或保存回执时也只查询原身份，不自动重发或创建副本。
取消和恢复均需明确点击；取消不证明远端已停止，恢复不会再次发送。放弃待确认稿前须明确确认对应提示，
放弃本地草稿不会取消其远端操作。

### Python 接口

先明确选择一个已有冻结上下文，并用 `p.discussion.add` 保存问题；另外选择的上下文、仿真、分析和工作流运行
须用 `review_sources` 完整复核。准备请求时传入：

```python
selection = {
    "expected_revision": revision,
    "sources": sources,
    "expected_sources_sha256": reviewed["sources_sha256"],
    "snapshot_id": snapshot_id,  # 无额外文件时为 None，assets 必须为空。
    "assets": assets,           # [{"record_id": ..., "path": "images/plot.png"}]
}
request = p.requests.create(
    message_id, request_id=request_id,
    configuration={"adapter": existing_adapter, "model": existing_model},
    prompt_version="stk.report-draft/1", report_selection=selection,
)
```

这里的上下文、问题、修订、来源、资产和已有端点由调用方明确选择；代码只准备请求，尚未发送。
准备会重新比较复核摘要，运行观察改变时要求重审。全部来源含主上下文最多 16 项，合并来源与资产元数据最多
192 KiB；额外资产最多 63 个，保留正文所需空间。请求只向模型提供选定上下文、运行状态及资产元数据，
不隐式读取运行结果或文件正文，也不把计划摘要当科学结果。含任何运行来源时须选择本机或机构内模型；
外部模型还会在实际发送前重新核对所有上下文表和文件的当前公开标签，结构公开不等于公开数据值。

确认后才另行明确调用 `p.requests.start(request_id)`。取消、不确定回复或重新打开都不会自动再发。
通过 `details = p.reports.generation_request(request_id)` 读取原冻结输入和已保存回复；仅
`details["request"]["status"] == "completed"` 时才有可用完整回复。编辑 `details["response"]["text"]`
得到正文，并单独保存：

```python
saved = p.reports.create_generated(
    "结果报告", request_id, edited_body,
    report_id=report_id, expected_revision=current_revision,
    expected_input_sha256=details["request"]["input_sha256"],
    expected_response_sha256=details["request"]["result"]["text_sha256"],
    entry_path="report.md",  # HTML 使用 .html；正文最多 64 KiB UTF-8。
)
```

保存只产生一次可撤销编辑，不再问模型。清单冻结原始配置、输入与回复摘要、来源和编辑标记；
之后运行推进也不更换这些观察。保存回执丢失时只按原 `report_id` 查询，不自动再建一份。
读取、净化预览和 ZIP 导出沿用下方接口；ZIP 额外保存 `stk-generation-input.json` 和
`stk-generation-response.txt`，可核对原输入、原回复与编辑后正文。两个证据路径不允许分配给附件。
冻结来源仍依赖项目中原有请求日志；ZIP 是可检查的来源包，不是自动导入项目或已渲染网页。

## 打开、检查和导出

在区域的编辑器菜单中选择 **报告 / Reports**。列表只读取元数据；选择报告后显示来源与资产清单，
明确点击 **读取所选资产** 才校验并加载字节。文本按 4 KiB UTF-8 页面浏览，Markdown／HTML 标为原文；
PNG 解码限单边 4096、总计 4,194,304 像素。其他资产保留元数据和完整导出能力。
工作区保存稳定的项目、报告、清单摘要与阅读位置，恢复时不自动读取资产。
报告标签不替换当前 Viewer，也不运行或覆盖隐藏 Python 页的草稿。

### 文档阅读视图

选择可读的 Markdown／HTML／PDF／MP4 报告后，明确点击 **预览报告**。
Markdown／HTML 先准备净化入口，再串行读取并校验选定图片与 MP4；PDF 通过既有预览接口读取最多 4 MiB 的完整二进制，
分别核对来源与显示的 MIME、大小和实际 SHA，作为单入口交付，不读取其他附件。
完整集合通过后才交给本标签的文档宿主；桥能力按入口类型发现，旧桥有 PDF 预览能力不代表支持 HTML 图片集合。
阅读视图提供 **原文与资产**、**重新准备**、**关闭预览**、**进入文档**和**返回控件**。
返回原文保留原先已读取的文本或 PNG，不再次读取资产；关闭预览则撤销文档资源，之后需要明确重新准备。

文档占独立视口，工具栏保留在 STK 中；视口不能完整放入区域时提示扩大区域。
弹层、拖动、标签隐藏或布局失效时同步隐藏原生页面并撤焦，新布局确认后才恢复。
移动标签到另一区域、移除区域、关闭项目、项目修订或桥会话变化会撤销旧资源，迟到的准备回复不能重新打开页面。
完整工作空间不保存浏览器、活动资源会话或待聚焦动作，恢复时不会自动准备或显示文档。

原生候选目前仅针对 macOS WKWebView 和 Windows WebView2；默认构建及 Linux 返回不支持提示，
仍可检查原文、PNG 或导出 ZIP。开启候选的构建方法见[验证入口](design/document-preview-spike.md#候选源码与有限使用)。
编译成功、净化资源和无窗口视口测试均不能证明实际浏览器显示、输入法或跨屏缩放通过；以逐平台证据为准。

### 视频预览

把 MP4 登记、冻结后，可直接设为报告入口；也可与 Markdown／HTML 入口一起加入报告，使用报告内路径引用：

```html
<video src="media/clip.mp4"></video>
```

单个 MP4 仍限 4 MiB，报告及显示集合分别限 32 MiB。请在系统视频控件中明确点击播放和拖动进度，
或使用 STK 的 **暂停视频**。隐藏预览会暂停，重新显示不会自动续播；切换项目或来源会关闭旧会话。
MP4 单独入口使用独立播放器页面，不把原始视频当成 HTML。视频不发送给模型，报告生成请求只保存附件元数据。
容器后缀不保证编码可播放；系统缺少相应解码能力时，保留原文件和 ZIP 导出。当前原生候选仍默认关闭，
Linux 不提供内嵌播放；无窗口测试和独立 FFmpeg 解码都不代替 macOS／Windows 的实际播放验收。

Python 可以按当前选择读取或导出：

```python
opened = p.reports.get(report_id)
report = opened["report"]
assert report["state"] == "readable", report["error"]
bound = {"expected_revision": opened["revision"],
         "expected_source_sha256": report["source_sha256"]}
asset = p.reports.asset(report_id, report["manifest"]["entry_path"], **bound)
preview = p.reports.preview(report_id, **bound)
# 使用一个尚不存在的绝对目标路径。
receipt = p.reports.export_file(report_id, "/absolute/new-report.zip", **bound)
```

`asset.data` 是完整原始字节的 base64，`content_sha256` 校验这些字节。
`source_sha256` 标识整份清单，包含资产选择与来源；预览的 `content_sha256` 标识实际显示字节，
原入口的摘要另存为 `source_content_sha256`。Markdown／HTML 交付净化后的页面；其他支持的 MIME 原样交付，
此时显示字节与原入口的内容摘要相同。清单摘要和字节摘要不可互换。
预览接口只交付字节与新会话身份，不会创建浏览器。Markdown／HTML 渲染需安装 `documents` extra，
例如在源码目录执行 `python -m pip install ".[documents]"`；缺依赖会明确失败。

面向原生资源会话的调用方还可显式使用 `p.reports.preview_resources(report_id, **bound)`，
返回 `{preview, resources, total_size}`。接受 Markdown／HTML 或 MP4 入口：`preview.source_path` 绑定原入口，
`resources` 是原清单中 PNG／JPEG／GIF／WebP／MP4 的 `{record_id, path, mime, sha256, size}`。
含视频时使用 `stk.report-renderer/2`；无媒体仍为 `/1`，兼容旧版没有 `source_path` 的 `/1` 回复。
MP4 独立入口的 `preview.path` 为 `_stk-preview/{session_id}/player.html`，资源仅包含该原始 MP4，
显示字节摘要与原始视频摘要独立核对。播放器不依赖 Markdown／nh3，也不会自动播放。
次级 HTML、Markdown、CSS、文本和 PDF 不进入资源清单或页面相对链接映射，避免从净化入口进入未净化文档。

此步骤只读取入口，不读取其他图片或视频正文。调用方仍须按同一修订和清单摘要逐项调用 `asset`，核对身份、
路径、MIME、大小和实际字节哈希，全部成功后才能一次建立原生会话；不能把其他原始 HTML 加入会话。
返回的 `total_size` 按实际显示入口字节与资源声明大小计算，上限仍为 32 MiB。
资源元数据不代表副本已通过内容校验或媒体解码。关闭、切换项目或句柄／桥会话变化时应废弃准备结果，
并关闭旧资源会话，使旧 URL 失效。这个接口本身不创建浏览器，也不表示完整富文档 UI 已交付。

ZIP 包含 `stk-report.json` 和选定的完整原始资产，逐项验摘要后才发布新文件，不覆盖已有目标。
它是来源包；HTML 原文未被改造成无需其他处理即可独立展示的渲染页面。
导出不改变项目修订，也不进入项目撤销；丢失导出回复时应先检查目标，不自动重复操作。
项目发生编辑后，旧修订绑定失效，需要明确重新读取报告。关闭项目后的旧 Python 句柄不能复用。

元数据列表不检查资产当前是否仍存在。显式读取或导出时，缺失或损坏的冻结对象会报错，
不会改读实时工作文件。只备份 SQLite 不包含 `.stk/objects`；完整搬迁使用[工作空间](design/portable-workspaces.md)。

## 首版边界

- 每份 1–64 个资产，单项最多 4 MiB，总计 32 MiB；最多 16 个来源。
- 报告元数据最多 384 KiB；报告集合最多 64 条、4 MiB。来源过大时明确拒绝，不静默裁掉证据。
- Markdown／HTML 渲染输入最多 1 MiB，显示输出最多 4 MiB；使用表格、代码块及受限 HTML。
- 渲染移除脚本、表单、嵌入页面、任意 CSS 与外链，只保留命中选定资产的相对引用。
  CSP 和资源回执不等于已证明浏览器后台完全无网络；原生候选仍需实机验收。
- 报告记录可经通用表格编辑；每次读取重新验证，损坏记录单独标为 `invalid`。
  摘要用于一致性校验，不是作者认证或防篡改签名。

发布格式和桥方法见[报告契约](specs/report-1.md)。
