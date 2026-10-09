# Linux 快速上手

一页走完：安装 → 用示例项目看一遍主流程 → 在终端或 Jupyter 中使用 → 接入真实运行。
示例项目使用合成数据，不需要服务器、许可或网络。macOS/Windows 的源码构建见
[桌面快速启动](https://github.com/sijintech/stk/blob/main/desktop/QUICKSTART.md)。

## 1. 安装

需要 x86_64 Linux（glibc ≥ 2.39，例如 Ubuntu 24.04）、X11 或 Wayland 桌面，以及 OpenGL 4.3 或 Vulkan 1.2 驱动。

先准备 Python 部分（3.11–3.14 的虚拟环境，推荐 3.12，含本机分析与三维显示所需的科学依赖）：

```bash
git clone https://github.com/sijintech/stk.git ~/stk
python3 -m venv ~/.venvs/stk
~/.venvs/stk/bin/python -m pip install '~/stk[science,visualization]'
```

再任选一种方式获得桌面程序：

- **预编译包**：在 GitHub Actions 的 `desktop` 运行页面下载制品 `desktop-linux-package`
  （`stk-desktop-<版本>-linux-x86_64.tar.gz`），校验并解压后启动：

  ```bash
  sha256sum -c stk-desktop-*-linux-x86_64.tar.gz.sha256
  tar xzf stk-desktop-*-linux-x86_64.tar.gz -C ~/opt
  STK_PYTHON=~/.venvs/stk/bin/python ~/opt/stk-desktop-*-linux-x86_64/bin/stk-desktop
  ```

- **从源码编译**（不需要 sudo）：

  ```bash
  cd ~/stk
  desktop/cmake/sysroot/fetch-sysroot.sh
  cmake -S desktop -B ~/opt/stk-build/desktop -G Ninja
  ninja -C ~/opt/stk-build/desktop
  STK_PYTHON=~/.venvs/stk/bin/python ~/opt/stk-build/desktop/bin/stk-desktop
  ```

状态栏显示“后台服务：就绪”即表示 Python 部分已连接；否则查看“后台服务日志”标签。

## 2. 用示例项目看一遍主流程

程序启动后左侧是 **工作台**。点击 **1. 项目** 下的 **创建示例项目**：约十秒后在 `~/STK Projects/stk-example-…`
建好并打开一个项目（可用环境变量 `STK_PROJECTS_DIR` 改位置）。随后按工作台的步骤浏览：

1. **参数**：“编辑参数”打开项目表格。“算例”表的 300、325、350 K 由 **生成参数扫描** 生成；
   展开该面板，可以再按范围或列表追加几行，整次生成一次撤销。
2. **结果**：“结果”表记录每个算例场的平均值与最大值，第一列是对算例行的引用。
   `results/demo/case-N/` 中的 `field.vtk` 与 `metrics.json` 由本机的合成求解器写出（不是物理模拟）。
3. **分析**：工作台“保存的分析”→“温度场”→ 侧栏“运行”页。历史中已有一次完成的运行：选中后
   **读取并校验结果**，再 **在查看器中显示**；也可以在“准备运行”中映射另一个场文件，点 **运行并显示** 一步完成。
4. **工作流**：工作台“其他”→“工作流”显示示例的“温度扫描”：算例 → 合成求解（每行的温度）→ 温度场；选中分析步骤点 **进入分析**，
   再用画布上方的“‹ 温度扫描”返回。在“运行”中勾选行后点 **运行所选 3 行**，每行先合成求解再分析，进度按行 × 步骤显示，完成后可打开每行的分析运行。
5. **AI 助手**（可选）：在“API 密钥”中填写阿里 Token Plan 密钥即可提问；密钥只交给本机后台服务。

## 3. 在终端或 Jupyter 中使用

桌面 Python 控制台里的 `stk` 也可以脱离桌面使用，操作与权限范围相同（不能操作窗口与查看器）：

```bash
~/.venvs/stk/bin/suan demo                       # 只创建示例项目并打印位置
~/.venvs/stk/bin/python -m suan.scripting.headless ~/STK\ Projects/stk-example-…   # 交互控制台
```

```python
from suan.scripting.headless import connect
stk = connect(project="~/STK Projects/stk-example-…")
print(stk.project.snapshot()["project"]["revision"])
stk.close()
```

命令行的表格与扫描操作见 `suan project --help`（例如 `suan project sweep`）。

## 4. 接入真实运行

- **本机运行环境**：在“任务”页选择“本机”并启动（仅 Linux），或通过 SSH 连接一台 Linux 服务器上的 STK 运行服务，
  见[运行服务指南](https://github.com/sijintech/stk/blob/main/docs/runtime.md)。
- **MuFerro**：需要 MuPRO SDK 与许可。导入案例后，在“仿真批次”中选择行、运行环境和资源，点击 **运行所选行**，
  见[仿真批次](https://github.com/sijintech/stk/blob/main/docs/simulation-batches.md)。
- **自己的程序**：参照[温度扫描示例](https://github.com/sijintech/stk/blob/main/examples/project_scan/README.md)，
  把合成求解器换成你的程序。

更多：[桌面指南](https://github.com/sijintech/stk/blob/main/docs/desktop.md) ·
[项目表格](https://github.com/sijintech/stk/blob/main/docs/project.md) ·
[参数扫描](https://github.com/sijintech/stk/blob/main/docs/project-sweeps.md) ·
[分析运行](https://github.com/sijintech/stk/blob/main/docs/project-analysis-runs.md) ·
[术语表](https://github.com/sijintech/stk/blob/main/docs/design/glossary.md)。

## English summary

1. Install the Python part (`pip install '~/stk[science,visualization]'` in a 3.11–3.14 venv, 3.12 recommended) and either the
   prebuilt Linux tarball from the `desktop` workflow's `desktop-linux-package` artifact or a source build;
   start `stk-desktop` with `STK_PYTHON` pointing at the venv's Python.
2. On **Home**, click **Create example project** (synthetic data, no server). Browse Parameters (a scan made by
   *Generate a parameter scan*), Results (means and maxima referencing their cases), and the saved analysis
   *Temperature field* whose finished run can be read and shown, or use *Run and show*. Home → *Workflows* shows the
   example's workflow *Temperature scan* (cases → synthetic solver → analysis); *Open analysis* enters its analysis and
   the breadcrumb above the canvas leads back. Nothing runs from there.
3. Without the desktop: `suan demo`, `python -m suan.scripting.headless [PROJECT]`, or
   `from suan.scripting.headless import connect` in Jupyter — the console's `stk`, minus window and Viewer control.
4. Real runs need a Linux Runtime (local or over SSH); MuFerro also needs its SDK and licence.
