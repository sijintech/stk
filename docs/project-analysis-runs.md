# 固定输入的本机分析运行

分析运行把一份[保存的分析定义](project-analyses.md)与一个[文件快照](project-snapshots.md)绑定，
先明确准备，再明确执行。每次运行冻结完整图、原始参数、输出选择、文件映射和内容哈希。
后续修改或删除原分析、文件索引或原始文件，不改变这次运行的输入。

本功能需要项目格式 **9**。旧项目通过已有“备份并升级项目”明确升级；打开旧项目不自动迁移。
它使用本机图工作进程，与[模拟运行记录](project-runs.md)中的 Runtime 任务分开，不上传文件或调用模型。

## 准备、执行与查看

1. 在项目文件表中登记需要分析的科学数据，明确捕获输入快照。模拟输出必须同样捕获，不能仅因文件属于某次任务就认定它不可变。
2. 打开“分析图”的“保存的分析”，在“分析定义”页明确选择一份文档，再切换侧栏的“运行”页。
   载入定义、读取快照或刷新运行列表都不执行节点；选择历史运行仍保留当前画布，明确点击“检查冻结流程图”才打开该运行的完整图。
3. 选择已有快照，为每个输入填写绑定名称、相对文件名和快照中的文件。
   例如图的 `data` 绑定内使用 `fields/temperature.vti`，就把该路径映射到选定的快照文件。
   文件扩展名参与读取器选择，应与实际内容对应；不会自动把 VTI 数据改成 DAT 格式。
   DAT 的字段名来自映射后的文件基本名，例如 `fields/signed.dat` 对应字段 `signed`；重命名映射时须同时核对图的字段参数。
4. 明确准备运行，核对来源修订、文件映射、参数和限制。准备本身不运行、不修改可编辑表格修订，也不新增普通撤销项。
5. 明确开始执行。运行中的轮询只读取本地记录，最多持续 90 秒；暂停跟踪后可以再次明确刷新。
6. 结果完成后，明确读取已归档结果，选择一个 payload 输出，再打开到 Viewer。共享 Viewer 已有内容或正在输入时不会替换它，
   需先处理现有内容。没有 payload 的结果仍保留完整图结果，但不能显示为三维。

导入结果不重新求值，也不伪造 Viewer 的图提交配置。执行来源保留在分析运行记录中。
所有 Viewer 区域当前共享一个结果状态，新建 Viewer 标签本身不会隔离旧配置。
需要腾空 Viewer 时，使用其区域菜单的“关闭结果”或明确调用 `stk.viewer.close()`；这会清除当前查看状态。
归档保存现有图协议的序列化输出：`dataset` 输出仅含数据集描述，不等于持久保存全部内存数组。
需要保留可显示数据或导出文件时，应在分析定义中明确选择相应的 payload 或 file 输出。

## 复用历史运行的输入

需要调整参数后重新分析同一批数据时，在“运行”页选择历史记录，明确点击“复用输入”。
程序按该记录的精确快照 ID 读取清单，核对项目、快照哈希以及每条映射的文件身份、大小和哈希，
再复制到本地准备区。即使该快照不在普通选择器显示的前 100 份中，也使用这份历史快照。
界面保留来源运行、快照与哈希，可继续检查或编辑映射。

准备区必须为空：已经选择快照或文件、填写尚未添加的路径或绑定名、已有映射时，先明确“清空输入准备”。
此操作清除准备区，不删除历史记录或快照；读取期间清空也会使迟到结果失效。正在任意窗口输入时先完成输入。
切换运行、项目或页面期间到达的旧回复不会覆盖新的编辑意图。

复用只复制输入映射，不切换当前保存分析，也不替换参数和输出草稿。先明确保存或放弃分析更改，
再“准备运行”，才会创建新 UUID，并冻结当前保存定义的新参数、输出和复用的历史输入；“开始执行”仍需单独点击。
不同分析定义也可复用同项目的输入，但须自行核对绑定名称与图需求。旧运行的计划和状态不改变，不自动重跑。

**复用和准备只核对元数据，不读取或验证快照文件字节。** 明确开始执行时才复制并校验实际输入。
原始可变文件可以已经移动或删除；若快照对象缺失或损坏，后续执行仍会失败，不能把复用成功当作输入字节验收。
复用后的准备区仅保存在当前编辑器内存，不随布局或程序重启保存。

## Python

下面的例子在当前项目中登记一个 VTI 文件，保存一份有符号标量分析并准备运行。
将文件路径、字段名和分量替换为实际数据；不要把例子中的字段名当作自动发现结果。

```python
from uuid import uuid4

p = stk.project
revision = p.snapshot()["project"]["revision"]
indexed = p.files.index(["/absolute/path/to/temperature.vti"], expected_revision=revision)
file_id = indexed["record_ids"][0]
captured = p.snapshots.capture([file_id], expected_revision=indexed["revision"])
snapshot_id = captured["snapshot"]["id"]

preset = next(item for item in stk.graph.presets() if item["id"] == "scalar-volume")
analysis_id = str(uuid4())
saved = p.analyses.create(
    "温度差分析",
    {"format": "stk.analysis-document/1", "graph": preset["graph"],
     "parameters": {"path": "fields/temperature.vti", "field": "temperature_difference",
                    "component": 0, "unit": None},
     "outputs": ["view"]},
    analysis_id=analysis_id, expected_revision=captured["revision"],
)

run_id = str(uuid4())        # 保留标识；回复丢失后按同一标识读取核对
run = p.analysis_runs.prepare(
    analysis_id, snapshot_id,
    {"data": {"fields/temperature.vti": file_id}},
    run_id=run_id, expected_revision=saved["revision"],
)
print(run["status"], run["plan_sha256"], run["bindings"])
```

确认后才执行。观察循环有自己的时限，到期只是停止读取，不取消后台运行：

```python
import time

run = p.analysis_runs.start(run_id)
deadline = time.monotonic() + 120
while run["status"] in ("running", "cancel_requested") and time.monotonic() < deadline:
    time.sleep(0.2)
    run = p.analysis_runs.get(run_id)
print(run["status"], run["error"])

if run["result"] is not None:
    archive = p.analysis_runs.result(run_id)   # 校验归档后读取，不打开 Viewer
    print(archive["result"]["outputs"].keys())
```

取消、核对中断记录以及重开后的查询分别明确调用：

```python
p.analysis_runs.cancel(run_id)
p.analysis_runs.recover(run_id)
page = p.analysis_runs.list(offset=0, limit=50)
run = p.analysis_runs.get(run_id)
```

`recover` 检查没有执行器持有该运行后，才把遗留活动状态标为 `unknown`；它不重新执行。
不需要取消或恢复时不要调用相应方法。获取 `p` 时固定项目打开会话，关闭重开后须重新取得 `stk.project`。
中断 Python 观察循环不等同于取消分析运行。

## 状态与重复调用

| 状态 | 含义 |
|---|---|
| `prepared` | 定义与输入清单已冻结，尚未领取执行 |
| `running` | 已领取，可能正在复制输入、排队、计算或归档 |
| `cancel_requested` | 已记录取消意图，等待实际执行结束 |
| `succeeded` | 图结果没有错误，并已完成归档校验与发布 |
| `failed` | 输入、计算或归档失败；图的部分失败仍可能有可读取的归档 |
| `cancelled` | 已确认取消；不是对所有插件外部副作用的回滚 |
| `unknown` | 执行中断，无法确认最终结果；不会自动重跑 |

同一 `run_id` 和完全相同的原始准备请求返回原冻结记录，即使项目之后被编辑；不同请求不能覆盖同一标识。
领取执行权只发生一次，跨进程租约保护活动执行。对终态或 `unknown` 再次调用 `start` 只返回当前状态。
需要重新计算时，使用新 UUID 明确准备新运行，不修改旧记录。

取消可能与成功完成竞争，已确认结果可以先完成；`cancel_requested_at` 仍保留意图。
读取不会自动恢复遗留状态。关闭、重连或重新打开项目也不会自动提交。
有归档不等于所有输出成功：必须检查 `status`、`error` 和图结果中的 `errors`。

## 文件映射与预算

首版限本机、一个已有文件快照、1–32 个绑定及总计 1–100 条映射。重复引用同一文件允许，但按每条映射累计字节数。
输入总量最多 **256 MiB**；固定 `desktop` 显示配置，图求值预算 **300 秒**，归档文件合计最多 **256 MiB**，
其中图结果 JSON 最多 **4 MiB**。另有从开始执行起计算的 300 秒整体超时，包含复制、排队、计算和归档；
因此排队也会消耗本次尝试的时间。工作进程停止和数据库结算仍有额外开销，300 秒不是界面完成状态的承诺。

绑定名使用小写英文字母起始，后续允许小写字母、数字和下划线，最多 64 字符，与图绑定规则一致。
相对文件名使用 `/`，最多 1024 UTF-8 字节、每段最多 255 字节；拒绝绝对路径、路径穿越、反斜线、控制字符、Windows 保留名字或字符，
以及同一绑定中大小写/Unicode 规范化重名和文件与目录冲突。
执行使用独立副本并逐个流式校验 SHA-256，不通过硬链接暴露快照对象，也不回退读取原文件。

完整参数及输出选择原样冻结，包括 JSON `null` 和明确的空输出列表。准备不保证图语义可运行，
未知节点、错误字段或缺失绑定仍可能在明确执行时失败。运行不冻结 Python、插件或驱动版本，因此不承诺跨环境位级复现。

## 保存与恢复边界

格式 9 的 `analysis_run_plans` 与 `analysis_run_events` 保存不可变计划和带校验的生命周期，独立于普通表格撤销。
输入沿用 `.stk/objects`；完成的归档位于 `.stk/analysis-runs/<运行 UUID>/result`，包含图结果和经过哈希校验的 blob。
发布归档后才保存成功或部分失败状态；读取结果会重新校验，不从缓存静默修补损坏文件。
崩溃留下的未登记归档不会自动认领或覆盖，应明确核对记录；`unknown` 不提供自动重试。

移动项目需复制完整项目目录。仅备份 SQLite 不包含快照和分析归档，恢复后可能提示缺失；当前仍没有数据库与全部资产的统一一致性打包。
普通撤销不删除这些运行来源或归档，目前没有自动垃圾回收。界面和 Python 列表分页读取，默认每页 50 条，最多 100 条。
原生输入快照选择器首版只展示返回清单的前 100 份，并提示省略数量；历史输入复用可按精确 UUID 读取被省略的快照，
也可通过 Python 按 UUID 明确绑定。
运行侧栏展示冻结的映射、参数与输出；“检查冻结流程图”将已读取计划打开到独立的只读历史视图，
保留来源身份、快照/计划哈希与输入映射。它不随运行选择、状态变化或后续保存定义编辑而改变，
不读取归档或原文件，不显示 Viewer 的执行回执；返回保存分析可继续原有参数与输出草稿。
关闭/重开项目或更换桥会话会清除历史视图，需重新明确打开。节点说明与显式校验使用当前本机环境，
不证明历史执行环境相同。完整冻结文档也可通过 `p.analysis_runs.get(run_id)["document"]` 读取，
详见[分析图检查](analysis-graphs.md#历史运行的冻结图)。
平台验证与已知限制见[验收记录](runtime-validation.md)；本机分析运行不代表远端集群或完整分层节点工作流已实现。
