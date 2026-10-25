# STK 当前交接

更新：2026-10-25。本文件只保留当前状态、待决定事项和操作入口。历史交付与失败证据见
[开发日志](docs/development-log.md)、[运行验收](docs/runtime-validation.md)；路线图见[开发计划](docs/development-plan.md)。
开始前读取 [AGENTS.md](AGENTS.md)，核对真实 Git／CI，保护未提交修改。发布契约优先于设计目标。

## 当前工作树和下一步

- **前头 CI 基线**：`78f51b2` 的 Desktop `40234644345` 已全部结束，**4/5 成功**：Linux、macOS、打包及干净容器成功；Windows **1107/1108**，唯一失败是工作模式旧菜单测试析构时 SEH、没有栈。Runtime `40234644378`、Docs `40234644456`、Secret `40234644394` 成功。已修复该夹具提前释放共享状态的确定生命周期缺陷，相关 45/45；尚不宣称已复现或解决同一 Windows 崩溃，须新 CI 确认。前头已结束，推送等待条件满足。
- **报告预览资源接口本机验收完成，源码 `31c1e06` 已提交 main**：新增两段只读准备，净化 Markdown／HTML 入口与图片描述符，宿主须逐项验证图片后再原子建会话；排除次级原始文档，保持总量 32 MiB。完整 Python **3483 passed、24 skipped、2 deselected**，完整原生 **1748/1748、零跳过**，必跑 **1278**；随后 Windows 夹具清理修正的相关 **45/45**、三 Python 版本与 wheel 隔离读回通过。新头 CI 待确认，见[本批验收](docs/runtime-validation.md#2026-10-25报告预览资源准备本机验收完成)。本批没有接入浏览器 UI，下一步仍是 P4 原生嵌入验证和真实报告显示。
- **桌面报告创建本机验收完成，源码 `a10025587fb0b85d386c31f7980f10b2fa2cf01b` 已提交 main**：快照摘要分页、明确选资产／路径／入口及一次创建；恢复草稿须重审，不确定回执只查原 UUID。专项原生 17/17、图形 24/24；完整原生 1747/1747、零跳过，必跑 1277 项，完整 Python 3468 passed、24 skipped、2 deselected。固定起点创建 8 次实际点击，隐藏稿与 Viewer 保持，发行包隔离读回和暂存扫描通过。实际证据见[创建验收](docs/runtime-validation.md#2026-10-25桌面创建冻结报告本机验收完成)。表单暂不选择额外上下文／运行来源；下一步继续 P4 富文档与预览。
- **P4 冻结报告基础本机验收完成，源码 `3f4af5e898e8f739591bb6fb05d46e872cce0452`**。已有报告普通表、快照资产与来源、六个桥／脚本方法、Markdown/HTML 净化接口、独立报告标签、原文分页／PNG 和显式 ZIP 导出。最终完整 Python 3.12 **3434 passed、24 skipped、2 deselected**，相关 217 项；3.11／3.14 新专项各 **204 passed**。完整原生 **1732/1732、零跳过**，Linux CI 必跑 **1262/1262**；报告原生 **10/10**、GPU 中英宽窄文本／PNG **16/16**。最终源码包／wheel 冻结读回冒烟和暂存密钥扫描通过，本批新头跨平台 CI 待确认；实际结果和限制见[最新验收](docs/runtime-validation.md#2026-10-25冻结报告存储与桌面读取本机验收完成)。创建表单最新本机验收见上一条；随后推进完整浏览器嵌入、PDF 阅读器、AI 生成、LaTeX 和视频，P4 与整个目标继续推进。
- **通用第 1 项已交付，第 2 项主要功能已交付**：表格／节点编辑、准备／分析布局、填充与看板、附件预览、分页、分析与工作流技能及本机方法库。方法库源码 `6fa8994` 的完整 Python **3221 passed、24 skipped、2 deselected**，完整原生 **1688/1688、零跳过**；精确提交、点击和跨平台结果见[验收](docs/runtime-validation.md)。
- **真实窗口性能已完成本机验收**：两表各万行，X11／Wayland × OpenGL／Vulkan，共 24 次；分页的绘制及交换调用返回中位 **2.90–3.07→0.69–0.85 秒**，原生采样峰值 RSS **356–392→196–229 MiB**。本机只有软件 GPU 证据，不代表屏幕呈现时刻、硬件或其他平台性能。最终显示回归及必跑 **12/12、零跳过**，Python 定向 **15 passed**，最终 CPU／窗口小样本冒烟通过。入口 `tools/benchmark_project_open.py`，限制与证据见[最新验收](docs/runtime-validation.md#2026-10-25真实窗口大项目性能本机验收完成)。
- **第 3 项 P4/P0 原型已实现，仍未完成选型**：默认关闭的独立构建选项接入 WKWebView／WebView2，内存清单绑定项目／资源／版本／会话；Linux 明确 Unsupported。本机资源、四显示组合和既有窗口回归 **28/28、零跳过**，无 Blender 的资源构建及 **14/14** 通过。macOS／Windows 候选已在上述 CI 编译，尚无实际嵌入运行证据；菜单相交时暂时隐藏文档，IME／PDF／DPI／浏览器内存仍待实机验证，见[原型入口](docs/design/document-preview-spike.md)及[验收](docs/runtime-validation.md#2026-10-25原生文档嵌入候选本机验证)。随后按计划推进训练、连接／联邦、知识库、复现和完整发行；PET 新专项后置，整个目标仍未完成。
- 工作空间恢复须先按同一打开句柄／修订验证目录与精确选中记录，再原子采用桌面；来源变化、缺失记录与草稿冲突不能部分采用。导出保存完整项目，分页缓存不是完整归档。
- AI 工具按需入口见[工具指南](docs/ai-development.md)。Serena 历史成功不证明当前服务可用；已知位置优先限定 rg 和局部读取。本批 AOCI 全量 22 块交付已确认、Challenge 10/10，随后按最终稳定源码维护增量索引；早期截断记录不证明当前失败，机器对齐也不替代实机验收。
- 旧批次的“等待 CI／未推送”仅是历史记录。默认 main 交付，保护无关未提交内容；新代码推送前重新核对前头 Desktop 的终态。

核对命令：

```bash
git status --short --branch
git log -5 --oneline
git fetch origin main && git log --oneline HEAD..origin/main
gh run list --branch main --limit 6
```

默认直接在 main 交付；不自动合并或删除无关旧 PR／分支。

## 已交付产品基线

| 方向 | 状态 | 入口 |
|---|---|---|
| 桌面与项目基线 | 原生桌面（GHOST/OpenGL/Vulkan/Metal）、项目格式 **14**（旧 13 可读、升级先备份；SQLite + 文件）、表格/参数扫描、保存分析、项目工作流（按行运行 MuFerro 与 LAMMPS）、归档、技能目录、工作台 | [开发计划](docs/development-plan.md)“当前基线”；`suan/project/`、`desktop/engine/lib/stk_app/` |
| S1 模型接入 | 全部交付：端点与密钥、数据标注与网络设置、本机一键部署（llama.cpp）、能力分档与自动切换 | [model-gateway.md](docs/design/model-gateway.md)；`suan/models/` |
| S2 智能体 | S2a、S2b 交付（格式 13 会话/事件/对象、8 个工具、签名批准、桌面“智能体（多步）”）；**真实模型的 GUI 人工验收未做** | [agent-harness.md](docs/design/agent-harness.md)；`suan/agent/` |
| S3 材料模型 | S3a 交付（P–E 回线、容量衰减；合成数据；PyTorch CPU 可选） | [materials-models-s3.md](docs/design/materials-models-s3.md)；`suan/materials/` |
| 多尺度引擎 | E0a、E0b、E1a、**E1b 写出器与 PET 本机建模、E1c 分析模板已交付**；PET 参数已按所有者新授权选择 | [方案](docs/design/multiscale-engines.md)、[写出器](docs/lammps-data.md)、[分析](docs/lammps-analysis.md) |
| PET 数据闭环节点 1 | MuFerro/LAMMPS 桌面导入、按冻结引擎处理运行及批次、离线热力学摘要；字典草案和全合成离线数据演练 | [桌面指南](docs/lammps-desktop.md)、[字典](docs/design/pet-data-dictionary.md)、[示例](examples/pet_data/README.md)、[厂内清单](docs/design/inplant-execution-baseline.md) |
| PET 专项研究 / E1d（已交付） | 冻结建模→压密→逐温降温→模量/O₂ 或 PET 链 COM MSD→保存分析；明确启动、取消、恢复、成功阶段复用；full/real 原子/真实键/盒子与实际轨迹帧。11 段真实软件验收通过，物性未验证收敛 | [全流程例](examples/pet_study/README.md)、[结构契约](docs/specs/lammps-structure-1.md)、[参数/限制](docs/pet-model.md) |

## 待所有者决定（决定前不要按某个选项实现）

历史等待期限已结束，但时间经过不构成批准。

所有者 2026-10-12 明确授权根据文献与公开资料判断并直接执行 PET，因此 PET 电荷不再待决定。
采用完整 PET OPLS-AA/MK 2022 适配方案：芳环 C −0.115 e，配套全部电荷/LJ；唯一末端醇氧的 +0.001 e 舍入修正明确记录，
不采用历史 0.0 推断。COOH/OH 六条四聚体为 546 原子，来源与限制见[PET 模型](docs/pet-model.md)。其他事项仍待决定。

1. **S3 下一步**：`stk.dataset/1` 两个数据格式要先交给合作方讨论；MuPRO 能否做电场扫描以产生相场回线待确认。
2. **S2c**（外部规划模型、智能体准备运行）视所有者决定。
3. **保存分析修改提案的持久形式**（较早的 P3 项，[建议](docs/design/review-drafts-and-conversations.md#保存分析修改提案的持久形式建议待所有者确认2026-10-06)）：仍待确认，目前未排期。

## 所有者已经确定的方向

- UI 主要管理 **项目、文件、技能、工作流、对话**。运行记录保存某次执行的冻结输入、参数、状态和产物，
  有独立身份；重新计算产生新运行，编辑流程不能改写旧结果。
- 准备模拟时以 AI 对话为中心，结果分析时以 3D/数据视图为中心。已有 Viewer/节点/表格/文件树组合默认布局；准备／分析独立布局已完成本机回归，源码提交与 CI 状态见上。报告模式仍待实现。
- 节点有项目流程与分析子流程两个层级。表格是通用查看/编辑框架，目标支持类型、引用、公式与富内容，
  参考多维表格和 Houdini 参数化；不要为每个 UI 页面另造一份业务状态。
- 项目采用“目录 + SQLite + 普通资源文件”。稳定 ID 用于持久关联，打开句柄只表示当前会话；
  大数据与图像等不必逐单元格写入 SQLite。表达式/依赖由应用服务求值，SQLite 本身不会执行所有计算。
- STK 内使用 Python 控制公开操作和布局；UI、Python、AI 复用共享服务和校验。2026-10-14 明确应用内基础代码编辑与运行，VSCode 保留为可选外部 IDE。
- Markdown/HTML/PDF、AI 报告、LaTeX 编译与嵌入预览仍是后续目标。
- 需要直接连接与 SSH；已有 Linux Runtime 连接/SSH 隧道和本机 stdio 桥，**通用 Mac↔Windows STK 点对点端点尚未实现**。
- `toolkits/` 最终按功能迁入 `suan/`，保留必要兼容；不是整目录改名。当前还有真实调用，不能提前删除。


## 代码导航

- 当前模块边界：[仓库结构](docs/repository-structure.md)、[桌面模块](docs/desktop-modules.md)。`archive/` 不进入导入、构建或测试发现。
- 表格：`suan/project/table_workbench.py`、`field_types.py`、`table_io.py`；原生 `desktop/engine/lib/stk_app/src/table_workbench.cc`、`project_table_editor.cc`。
- 分析／工作流：`suan/project/workflows.py`、`analysis_runs.py`；原生 `src/editors/analysis_graph_editor.cc`、`workflow_editor.cc`，共享候选历史在 `analysis_parameter_draft.cc`、`workflow_draft.cc`。
- 科学链路：[LAMMPS 桌面指南](docs/lammps-desktop.md)、[PET 模型](docs/pet-model.md)、[PET 全流程](examples/pet_study/README.md)。软件验收不证明材料性质收敛。
- 新增工具按任务读取[工具指南](docs/ai-development.md)，不要每轮加载完整历史日志或全仓库扫描报告。

## 构建、启动和测试

### 当前 Linux 工作机

以下路径在交接时实际存在，仅适用于当前机器：

| 用途 | 路径 |
|---|---|
| 仓库 | `/home/mnemora/xcheng/sijin/stk` |
| Python | `/home/mnemora/opt/stk-venv/bin/python` |
| CMake 构建目录 | `/home/mnemora/opt/stk-build/merge-check`（Ninja / RelWithDebInfo） |
| 用户 sysroot | `/home/mnemora/opt/stk-sysroot` |
| 原生程序 | `/home/mnemora/opt/stk-build/merge-check/bin/stk-desktop` |
| 离屏图 | `/home/mnemora/opt/stk-build/merge-check/tests/app/out/` |

一次只运行一个原生编译；编译成功退出后再运行测试，不让测试读取仍在重链的二进制。
以下命令在仓库根目录运行；`&&` 保证构建失败时不测试旧程序。

```bash
cmake --build /home/mnemora/opt/stk-build/merge-check --parallel 4 && \
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  --parallel 4 --timeout 600 --output-on-failure \
  --output-junit /tmp/stk-claude-full.xml
```

工作台/技能/布局/分析草稿定向回归（相关修改时使用；不需要每次文档修改都跑完整套件）：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir /home/mnemora/opt/stk-build/merge-check \
  -R '^(SkillCatalog\.|SkillsCatalogPython\.|ProjectSkillsPython\.|project_skills|WorkspaceNavigation(Python)?\.|AnalysisParametersEditorPython\.|FocusNavigation\.|ScriptPython\.)' \
  --parallel 4 --output-on-failure --output-junit /tmp/stk-claude-focused.xml
python3 desktop/tests/check_required_tests.py /tmp/stk-claude-focused.xml 'SkillCatalog\..*' 'SkillsCatalogPython\..*' 'ProjectSkillsPython\..*' \
  'WorkspaceNavigation(Python)?\..*' 'AnalysisParametersEditorPython\..*' 'FocusNavigation\..*' 'ScriptPython\..*'
python3 desktop/app/i18n/check_i18n.py
git diff --check
```

Python 测试按改动选取，例如技能相关可从 `tests/test_skill_catalog.py`、`tests/test_skills.py` 与 `tests/test_graph_schema.py` 开始，
用上述 venv 的 `python -m pytest`；完整平台组合与依赖以 [desktop.yml](.github/workflows/desktop.yml)
和 [runtime.yml](.github/workflows/runtime.yml) 为准。新必跑场景要接入 `check_required_tests.py`，跳过不算验收成功。

其他 Linux 机器按 [desktop/README.md](desktop/README.md#build-linux) 重新配置，不能照搬此机 CMake 缓存。
完整测试需要 Python 的科学/控制/可视化/测试依赖及 Xvfb/Weston；sysroot 下载入口支持 `--with-test-servers`。
配置时将 `STK_BRIDGE_TEST_PYTHON` 和 `STK_APP_TEST_PYTHON` 指向实际 venv，避免缺依赖导致测试跳过。

### Python 测试与密钥扫描

完整 Python 套件约 7.5 分钟（没有安装 xdist，不要加 `-n`）；LAMMPS 相关可先跑定向：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python -m pytest -q -m "not perf" -p no:cacheprovider
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= /home/mnemora/opt/stk-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_lammps.py tests/test_workflow_lammps.py tests/test_project_workflows.py tests/test_workflow_batches.py tests/test_modules.py
```

Python 3.11 与 3.14 的环境在 `/home/mnemora/opt/stk-venv311`、`/home/mnemora/opt/stk-venv314`（CI 测 3.11、3.12、3.14）。
新增内置模板时，`test_project_workflows.py` 与 `test_workflow_batches.py` 中固定的模板列表要一起更新。
提交前对暂存的改动做密钥扫描（gitleaks，规则在 `.gitleaks.toml`；本机没有全局安装时自行下载固定版本），CI 也会扫描：

```bash
git diff --cached | gitleaks stdin --config .gitleaks.toml --redact --no-banner
```

### macOS / Windows 启动

这两个脚本已存在并供用户测试，不要再建一套。完整工具链要求见[快速启动](desktop/QUICKSTART.md)。

```bash
# macOS，完整 Xcode；仅 CommandLineTools 会导致 xcodebuild 报错
bash desktop/setup-macos.sh --demo
```

```powershell
# Windows x64，VS2022/Build Tools C++ 工作负载、SDK、Git、x64 Python
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --check
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

更新代码后用正常命令重新编译；`--launch-only` 会跳过编译，不能用它验证新功能。
这些脚本只构建主程序，不运行完整测试，也不自动启动 Runtime。进入界面后从 **文件 → 工作台** 检查本次入口。
无服务器演示：[参数扫描/三维](examples/project_scan/OFFLINE.md)、[保存分析/结果表格](examples/project_analysis/README.md)。

## 每次交付约束

不读取、打印或保存密钥。测试清空 `STK_TOKEN_PLAN_API_KEY`、取消 `STK_TOKEN_PLAN_MODEL`；刷新、重开和测试不发收费模型请求。
端点、密钥和产品网络策略只能由桌面显式配置；私有项目数据不发外部模型。公开文档统一称“合作方”。
保持明确运行／保存／发送动作，保护 Viewer、隐藏页草稿和文字输入。UI 交付记录固定起点、实际点击数及结果；本轮工具配置没有 UI 点击验收。
交付同步四份状态文档，按最终稳定内容维护 AOCI；提交前扫描暂存密钥，推送前等待前代码头 Desktop CI 完成。
