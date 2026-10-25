# STK 当前交接

更新：2026-10-25。本文件只保留当前状态、待决定事项和操作入口。历史交付与失败证据见
[开发日志](docs/development-log.md)、[运行验收](docs/runtime-validation.md)；路线图见[开发计划](docs/development-plan.md)。
开始前读取 [AGENTS.md](AGENTS.md)，核对真实 Git／CI，保护未提交修改。发布契约优先于设计目标。

## 当前工作树和下一步

- 项目技能版本源码提交 `073c608a271c4dea001a49432879f174f2afab7c`：固定完整方法定义与图模板、升级保留历史、恢复和创建保存分析，含共享 Python／桥接口、原生技能页与同项目选择恢复。本机完整原生 **1639/1639、零跳过**，技能定向及必跑 **33/33**；完整 Python **3083 passed、24 skipped、2 deselected**，三 Python 版本相关各 **74 passed**。中英文宽窄／1×与2×升级恢复及16项图形用例通过。版本不包含执行环境，创建不运行；详情见[技能验收](docs/runtime-validation.md#2026-10-25项目技能版本)。源码已提交；本批新跨平台 CI 待确认。
- 实查 `c6c39f3856189530db983d3c6f4dba4704c477e4`：Desktop `40171064126`、Docs `40171064146`、Secret `40171064141` 均已完成成功；Runtime `40171064147` 为 **6/8 成功**，两个 Windows 客户端作业失败。附件预览测试应比较原始 UTF-8 字节，不能用会规范化 CRLF 的 `read_text()` 作为预期；修正及 LF／CRLF 夹具已包含在 `073c608`，待新 Windows CI 确认。上一代码头 Desktop 等待条件已满足。
- 附件详情预览源码提交 `bc2896a89f2e357d30ea8bda3a246190604cc411`：明确读取本地 PNG／UTF-8 文本，冻结附件校验完整摘要；已选对象格起点 **2 次点击**，保留修订、选择与 Viewer。最终原生相关及必跑 **59/59、零跳过**，Python 修正后相关 **25/25**；首次完整回归的两处测试断言失败和复验见[验收](docs/runtime-validation.md#2026-10-25附件详情预览)。新 CI 待推送后确认。更多格式／缩略图、首次大表读取、子流程、技能版本管理及 P4–S7 仍待完成。
- 看板拖动源码提交 `752d1ea9016ff6730fa7cb3df4a22e9ecfd5a811`：定向及必跑 **64/64**、完整原生 **1619/1619、零跳过**。从当前看板拖入空状态列，**0 次额外点击＋1 次拖动**，一次修订／撤销，保留 Viewer 与选择；旧回调、修订变化、公式和其他编辑器草稿均受保护。记录头 `b1673ee` 的 Desktop `40167186317` **5/5**、Runtime `40167186293` **8/8**、Docs／Secret 均已完成成功，满足附件预览批次的推送等待条件；见[本批验收](docs/runtime-validation.md#2026-10-25看板拖动)。
- 表格填充柄源码提交 `b2b076d669e6089fd700d4ff02097aaee60adb0b`：定向及必跑 **57/57**、完整原生 **1612/1612、零跳过**。按可见顺序重复选区，保留类型／空值／对象／公式，一次 CAS 和撤销；固定起点 **1 次选格＋1 次拖动**，Viewer 保持。`35637ea` 的 Desktop `40163712446` **5/5**、Runtime `40163712511` **8/8**、Docs／Secret 均成功，见[本批验收](docs/runtime-validation.md#2026-10-25表格填充柄)。看板拖动已推进到上述本批；其余工作继续。
- 通用编辑器及开发工具已提交并推送到 `main`：`4f919c752a9f8472e9f736ff91234a935acf4e51`；原有工作稿已纳入该交付。
- 大表按需查询及跨平台测试编译修正已提交并推送：`027798ff0d5ca914b947401d14c47e4787430133`。普通查询先分页，筛选／排序仅读所需字段，再返回完整记录及依赖求值；不改项目格式或已发布 API。按工作模式保存布局已通过本机验收，源码提交见下。
- 模式布局源码提交 `85630acbb04f419ac7a13b0d5f99e08990cd91f9`、记录／索引提交 `d1493fa337b9768046a15b78d64a32796a1555be`：定向 **72/72**、必跑检查 **60/60**，完整原生 **1604/1604、零跳过**，中英文 1×／2× 每次切换 **2 次点击**。准备／分析模式分别记忆几何、标签及面板偏好，切换保留活编辑器；区域集合变化保留当前分栏。`d1493fa` Desktop `40160203772` 已全部结束且 **5/5 成功**，见[本批验收](docs/runtime-validation.md#2026-10-25工作模式布局)。
- 当前目标：完成开发计划的主要内容，**通用功能优先，PET 等专项后移**。交付范围和顺序见[计划顶部](docs/development-plan.md#2026-10-24通用能力优先的后续交付)，不能在编辑器补丁完成后把整个目标标为完成。
- `d1493fa` 的 Runtime `40160203774` **8/8**、Docs `40160203773`、Secret `40160203795` 均成功；下一批推送所需的前 Desktop 等待已满足。
- 表格／节点编辑器本机验收已通过：原生完整 **1592/1592、零跳过**，相关必跑 **164/164**；Python 完整 **3025 passed、24 skipped、2 deselected**。`4f919c7` 的 Runtime **8/8**、Docs、Secret 成功；Desktop `40154110887` 已全部结束，Windows 与三项 Linux 作业成功，macOS 因测试中 `auto` 混合推导 `uint64_t`／`size_t` 编译失败。`027798f` 已拆开相关声明，macOS 修正由下述新 CI 复验成功。
- 新查询的三 Python 版本相关测试各 **154 passed**，另补长依赖链用例；完整 Python **3040 passed、22 skipped、4 deselected**，原生 **1592/1592、零跳过**。两表各万行／8 列的分页、筛选与排序测量见[新验收](docs/runtime-validation.md#2026-10-25表格按需查询与平台修正)。桌面初始共享快照尚未改为分页，不能声称整个大表体验完成。
- `027798f` 的 Runtime `40156836276` **8/8**、Docs `40156836343`、Secret `40156836355` 成功；Desktop `40156836215` 已全部结束，**5/5 成功**，包含 macOS Metal、Windows CPU 和三项 Linux 作业。模式布局批次推送的前置等待已满足；后续 push 继续等待上一代码头 Desktop 结束。
- 推送 `4f919c7` 前已复核前产品头 `76715e4` 的 Desktop `38956471084` 为 **5/5 成功**；下一次代码 push 的前置等待已满足：`40154110887` 全部结束，结果见上。每次提交前扫描暂存密钥。
- AI 开发工具本机配置与复现命令见[工具指南](docs/ai-development.md)。直接安装官方固定版本已获授权，不再等待旧 ZIP；未声称复原那个未知补丁。
- Serena 早先通过独立 MCP 客户端验收；本轮宿主 Python 语言服务初始化曾报 `LanguageServerTerminatedException`，本批使用限定 `rg` 和局部读取，不能把早先独立验收当作当前宿主正常。AOCI 按实时合同建立并在源码稳定后增量维护，不能用 Serena 或历史摘要替代。

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
