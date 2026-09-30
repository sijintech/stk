# 离线分析与表格验收

此示例适用于使用仓库启动脚本编译的 macOS、Windows 和 Linux 桌面。数据为 **73 行、10 列的合成 CSV**，
只检查软件流程，**不是物理模拟**。它使用本机图工作进程，需要启动脚本准备的科学 Python 环境（CSV 读取需要 NumPy），
不需要 Runtime 服务器、SSH、网络、模型服务或 token。

## 运行

1. 更新代码并重新启动桌面，选择 **文件 → Python**。
2. 展开“运行 Python 文件”，填写仓库中 `examples/project_analysis/offline.py` 的绝对路径，明确点击“运行文件”。
   拖入脚本只填写路径，不会自动执行。
3. 脚本创建新的 `~/STK Projects/offline-analysis-时间戳-随机标识`。目的目录必须不存在，即使已有目录为空也拒绝使用。
   所有样例文件均独占创建，不覆盖现有文件。
4. 控制台显示新项目目录、分析 UUID、运行 UUID、输入快照 UUID及最终状态。它不会切换当前项目，不关闭已有项目，
   不改变布局，也不打开或清空 Viewer。请先完成当前工作，再明确打开这个新项目。

运行此脚本会明确创建项目、捕获 CSV 文件快照、保存分析定义、准备并启动 **一次** 本机分析。
准备后、开始前，脚本先将标识写入并刷新到 `demo.json`，方便中断后查找；它不自动重试、恢复或取消运行。
每次重新运行文件都会使用新目录，创建另一次独立示例。

默认观察最多 60 秒；单次本地接口调用的等待可能使返回稍晚。**观察超时不等于取消分析**，后台可能仍在处理。
不要为了查看状态反复运行脚本，按 `demo.json` 中的运行 UUID刷新历史记录即可。中断 Python 同样不代表取消分析。
若明确要取消，在运行界面另行点击取消。失败时保留新项目及已经生成的文件，不自动删除或回滚。

## 在界面中检查

打开新项目后，进入 **分析图（Node Graph）→ 保存的分析 → 分析定义**，刷新并载入 **Synthetic CSV / 合成 CSV**，
再切换侧栏的 **运行** 页，刷新列表并选择控制台记录的 UUID。执行完成应为成功。

- 点击“读取并校验结果”，选择返回的 `table` 输出。此读操作校验归档；之后的属性或表格浏览使用内存中的结果。
- 在“表格视图”中查看来源列顺序、单位及单元值，分别翻行页和列页，来源索引从 0 开始，确认第 73 行（索引 72）和第 10 列（索引 9）都可到达。
  首三行 `temperature_difference` 为浮点数 `-9.5`、`0.0`、`14.5`，单位 `K`，表示合成温差，**不是负的绝对温度**。
  `step` 与 `sample_1` 至 `sample_7` 是整数；`case` 为 `synthetic-000` 等字符串。
- 选择一行，再明确选择该页的一列，查看精确值、类型、列名与单位。长文本有精确分页，短预览不等于完整数据。
- 返回“属性”可检查原始 `column_names`、`columns`、`units` 和运行问题。未支持表格视图的旧版本只能使用属性浏览；
  要验收新网格请重新编译当前代码。
- 明确点击“检查冻结流程图”，确认运行的冻结图、来源修订和输入映射。该历史图不会随保存定义修改而改变。

也可手动验证后续编辑：回到保存定义，检查 `path` 参数和请求输出 `table`；本地修改只有明确保存后才写入。
需要再次执行时，先清空输入准备，再从旧运行明确“复用输入”，核对映射，另行“准备运行”得到新 UUID，再明确开始。
编辑、保存、复用和读取都不会自动重跑旧记录。请勿把修改参数后的旧结果当作新计算。

## 文件和 Python

新目录中包含 `synthetic.csv`、`analysis-document.json`、`README.md` 与 `demo.json`；项目数据库、冻结输入和归档
由已有项目接口管理。`demo.json` 只保存身份与准备信息，**不是不断刷新的运行状态文件**。

本次控制台变量 `offline_analysis_demo` 保存目录和标识。也可在已有 Python 会话中明确指定一个全新目录：

```python
import runpy

# 按绝对路径加载函数；默认名称不是 __main__，此行不创建项目或启动分析。
example = runpy.run_path("/absolute/STK/examples/project_analysis/offline.py")
demo = example["create_demo"](stk, "/absolute/new/directory", wait_seconds=60)
```

上述绝对路径用法不要求当前 Python 工作目录位于仓库，也不要求 examples 已安装。
目的目录不能是已有项目或现有文件夹。示例不会调用 `stk.ui.open_project`，从而避免脚本观察期间覆盖用户切换到的项目。
没有页面、侧栏或布局自动导航；用户按上述步骤进入新项目。

重启或重置 Python 后，用 `demo.json` 恢复标识并只读查询：

```python
import json
from pathlib import Path

saved = json.loads(Path("/absolute/demo/project/demo.json").read_text(encoding="utf-8"))
p = stk.projects.open(saved["directory"], expected_id=saved["project_id"])
run = p.analysis_runs.get(saved["run_id"])
print(run["status"], run["error"])
# 仅已有归档时再明确读取；这不导入 Viewer，也不执行节点。
if run["result"] is not None:
    archive = p.analysis_runs.result(saved["run_id"])
    print(archive["result"]["outputs"].keys())
```

脚本中的成功校验会读取一次归档，核对全部列的顺序、73 行内容、JSON 类型与温差单位；它没有创建 Runtime 任务、
图像或三维 payload。有关通用边界，见[本机分析运行](../../docs/project-analysis-runs.md)。
