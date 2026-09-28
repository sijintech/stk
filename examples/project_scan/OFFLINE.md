# 无需服务器的工作台演示

在 macOS、Windows 或 Linux 桌面中测试项目表格、Python 和本机三维视图，不需要 Runtime、SSH 或 Hub。
数据是三组合成高斯场，用于检查软件流程，**不是物理模拟**。桌面快速启动脚本会准备所需的 Python
科学/可视化依赖；已有环境请先更新 `main` 并重新编译。

1. 启动桌面，选择 **文件 → Python**。
2. 展开“运行 Python 文件”，填写本仓库 `examples/project_scan/offline.py` 的绝对路径，点击“运行文件”。
   拖入文件只填路径，需要明确点击运行。
3. 完成后会看到三个区域：左侧项目表格，右上三维 Viewer，右下 Python 控制台。
   每次运行都创建新的 `~/STK Projects/offline-workbench-时间戳`，已有项目不会被覆盖。

脚本通过公开 `stk` API 完成以下操作：

- 从 CSV 创建 300、325、350 K 的参数表；公共参数表提供 10 K 偏移，跨表公式得到 310、335、360 K。
- 本机标准库程序写出三个 `field.vtk`、`metrics.json` 和 `slice.png`。
- 显式连接文件读取 → 统计两个分析节点，独立核对每个场的点数、平均值和最大值。
- 创建结果表、文件索引，冻结程序、配置、参数 CSV 和分析图的输入副本。
- 使用 Python 打开项目，配置三个区域的布局，把第三组结果加载到同一个 Viewer。

## 建议检查

- 在“Controls / 公共参数”表把 Offset 从 10 改为 20，回到 Cases 表应看到派生温度变成 320、345、370 K。
  修改表格只更新依赖单元格，已有生成文件与三维结果保持原值；此示例不会自动重算场数据。
- 用“撤销”恢复 Offset，派生值也应恢复。选择 Results 表可比较已经生成的平均值/最大值。
- 在 Python 输入 `stk.viewer.configure(overlays=False)` 隐藏辅助显示，再改回 `True`。
  `stk.viewer.status()["layers"]` 可查看实际图层 ID，再用 `stk.viewer.layer(id, visible=False)` 隐藏指定图层。
- 打开“项目文件”中的 `README.md`、输入配置或程序，用系统应用/VSCode 查看。应用内 Markdown/PDF 预览仍待开发。
- 在“输入快照”验证冻结文件。关闭桌面再启动，通过“最近项目”选中该项目重开。
  数据和引用会保留，Python 变量需重新创建；输入脚本不会自动执行。

本次控制台中的 `offline_demo` 保存了目录、表/字段 ID 和先前布局。可明确切换到另一结果或恢复布局：

```python
stk.viewer.open(offline_demo["folders"][0], preset="volume",
                parameters={"path": "field.vtk", "range": [0, 400]})
stk.viewer.wait()
stk.ui.apply_layout(offline_demo["previous_layout"])
```

先前布局还保存为项目内 `layout-before-demo.json`。如果关闭/重置过 Python，会话变量不再存在，
可从该文件读取后调用 `stk.ui.apply_layout`。恢复布局不会运行文件里的 Python 源码。

脚本失败时保留已经创建的项目与文件，错误显示在控制台；可以检查错误和路径，不会自动回滚文件。
不创建假的 Runtime 任务或运行记录，也不演示远程任务恢复。完整远程流程见 [温度扫描示例](README.md)。

## 自动化使用

```python
from examples.project_scan.offline import create_demo
# 已有 stk 会话、全新的目录；仅创建数据而不改变桌面布局：
demo = create_demo(stk, directory, show_ui=False)
```

`analyze=False` 可测试基础项目/文件生成而不加载 VTK；需要同时设置 `show_ui=False`，否则 Viewer
仍需要可视化依赖。正式桌面测试使用默认值，包含实际分析和三维加载。
