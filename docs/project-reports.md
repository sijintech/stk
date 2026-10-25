# 冻结项目报告

报告把一份 Markdown、HTML、PDF 或文本入口与选定资产保存在项目中，关闭并重新打开后仍读取同一份快照字节。
报告还可以记录当时选定的上下文及运行状态。它使用普通项目表和已有文件快照，不创建第二套运行系统。
创建、读取、预览和导出均不会执行分析、启动任务或发送模型请求。

本批提供报告存储、离线 Markdown／HTML 净化渲染接口及独立桌面报告标签。
桌面当前显示原文和 PNG；完整浏览器富文档嵌入、PDF 阅读器、AI 生成、LaTeX 和视频仍按 P4 推进。
原生渲染候选的单独验证见[文档原型](design/document-preview-spike.md)。

## 创建一份报告

先把入口与图片等资源登记为[项目文件](project-files.md)，再明确捕获同一份[输入快照](project-snapshots.md)。
快照需要项目格式至少为 4；打开旧项目不会自动升级。以下代码在 STK 的 Python 页显式运行，
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

## 打开、检查和导出

在区域的编辑器菜单中选择 **报告 / Reports**。列表只读取元数据；选择报告后显示来源与资产清单，
明确点击 **读取所选资产** 才校验并加载字节。文本按 4 KiB UTF-8 页面浏览，Markdown／HTML 标为原文；
PNG 解码限单边 4096、总计 4,194,304 像素。其他资产保留元数据和完整导出能力。
工作区保存稳定的项目、报告、清单摘要与阅读位置，恢复时不自动读取资产。
报告标签不替换当前 Viewer，也不运行或覆盖隐藏 Python 页的草稿。

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
