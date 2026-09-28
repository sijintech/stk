# macOS / Windows 工作台验收

这份清单用于测试 2026-09-28 新增的项目、Python、文件和运行能力。
此前两平台的主窗口/3D 启动反馈仍有效，但不能代替下面新增交互的真机验收。
自动化与 CI 记录见[开发交接](development-log.md)和[验收记录](runtime-validation.md)。

## 更新并启动

在仓库根目录执行 `git pull --ff-only`，然后运行对应的[快速启动脚本](../desktop/QUICKSTART.md)。
本次需要增量编译，不使用 `--launch-only`；已装依赖和编译缓存会复用。

```bash
# macOS
bash desktop/setup-macos.sh --demo
```

```powershell
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

选择 **文件 → Python → 运行 Python 文件**，填入仓库中 `examples/project_scan/offline.py` 的绝对路径，
明确点击“运行文件”。脚本创建新的本机项目，显示项目表格、Viewer 和 Python 三个区域。
无需服务器；输出是合成测试场。目录和布局恢复步骤见[离线演示](../examples/project_scan/OFFLINE.md)。

## 本机检查

| 操作 | 应看到的结果 |
|---|---|
| 打开 Cases / 参数 | 3 行温度 300、325、350 K；派生值 310、335、360 K |
| 拖动底部横向滚动条，或 Shift + 滚轮 | 能看到右侧派生列；表头与单元格对齐，排序/选择仍指向同一条记录 |
| 点击数字列表头排序，再选择一行 | 数值按实际大小排序；下方单元格编辑对应被选中记录，引用不因顺序变化而改变 |
| Controls 表将 Offset 10 改成 20 | Cases 派生值变为 320、345、370；原来的文件和 3D 场不自动重算 |
| 项目“撤销”，再“重做”，再“撤销” | 参数与依赖值一起恢复；结束时 Offset 回到 10 |
| 按[预览步骤](../examples/project_scan/OFFLINE.md#检查修改预览)运行两段代码 | 第一段只返回候选值，表格不变；第二段明确应用后才保存；可撤销 |
| 项目文件选中另一组 `field.vtk`，点击“在查看器中打开” | Viewer 显示所选场；即使 Viewer 标签之前隐藏，也会被激活 |
| 项目文件中打开 `README.md` 或 `solver.py` | 系统应用/VSCode 打开相应文件；应用内 Markdown/PDF 预览目前未实现 |
| 输入快照中验证文件 | 已冻结输入校验通过；修改参数不修改历史输入对象 |
| Python 执行 `stk.viewer.configure(overlays=False)`，再改回 `True` | 同一 Viewer 中的辅助显示切换，界面和脚本操作一致 |
| Python 查看 `stk.ui.layout()`，再恢复演示前布局 | 可读取结构化布局；恢复步骤使用 `offline_demo["previous_layout"]`，项目内容保留 |
| 关闭程序、重新启动，从“最近项目”打开演示项目 | 表格、引用和修改历史保留；脚本不会自动执行，Python 变量不会跨重启保留 |

另外检查中英文输入法、粘贴绝对路径、窗口缩放、跨屏 DPI、菜单和快捷键。
CI 的合成输入和截图不能确认实际键盘、输入法或触控板的全部行为。

CSV 可使用项目中的 `results-summary.csv` 测试显式类型导入，导入后应出现一个新表；
导出使用一个尚不存在的文件名。重名拒绝、数值类型和公式计算值的具体规则见[CSV 交换](project-csv.md)。

## 远程检查独立进行

本机演示通过后，可按[SSH 指南](ssh.md)连接一台 Linux Runtime，再运行[远程温度扫描](../examples/project_scan/README.md)：
准备不会启动任务；在运行面板明确提交，完成后收集并查看结果。关闭桌面后重开，应仍可读取任务关联和刷新状态。
本机中断 Python 等待不取消服务器任务；需要取消时使用明确的任务操作。

这一步验证的是 STK 客户端到 Linux Runtime 的连接。两台安装 STK 的 macOS/Windows 机器直接配对、
远程项目操作以及远程 Python/UI 仍在开发计划中，当前不把 SSH 隧道称为通用点对点通信。

## 当前自动化范围与反馈

Linux CI 覆盖 GL/Vulkan、真实 Python 桥及窗口/打包测试；macOS CI 覆盖 Metal、桥和 STK.app；
Windows CI 编译所有目标并运行 CPU/桥/客户端测试，**未执行 Windows GPU 真机渲染**。
工作台中英文截图与 JUnit 可从 desktop workflow 的对应平台 frames artifact 下载。

记录问题时附操作系统、`git rev-parse --short HEAD`、失败步骤、实际结果和 `setup.log` 中相关错误。
设计体验反馈可直接记录“希望完成什么、当前在哪一步受阻”。
