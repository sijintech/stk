# AI 开发工具：配置与实测

2026-10-24，在 Linux 当前工作树完成本地接入；基线提交 `7e0e6b1`。
本轮没有修改产品代码、提交或推送，也没有调用产品模型。工具可运行不代表产品回归通过。

## 已配置内容

| 工具 | 固定版本／配置 | 本机验证 |
|---|---|---|
| AOCI | 服务 `0.1.0-rc21`，既有 Volumes v1 | 完整加载、交付确认与 Challenge；受管修改按实时 Guide 收尾 |
| Serena | `serena-agent==2.1.0`，隔离 Python 3.13 | health 通过；Python、C++、TypeScript 定义及引用 MCP 调用通过 |
| jscpd | `5.4.2`，`tools/ai/package-lock.json` | 531 个文件，27 组重复，484 重复行；报告仅供审查 |
| Knip | `6.42.1`，同一独立锁文件 | web 扫描完成，23 项未使用导出、11 项未使用类型导出；exit 1 表示发现问题 |

Serena 项目设置在 `.serena/project.yml`：LSP 后端、三种语言、只读、遵循 Git ignore。
排除归档、vendored Blender、pyqode、生成资源、依赖目录、AOCI 资产、本地环境和编辑器配置。
只暴露 `get_symbols_overview`、`find_symbol`、`find_referencing_symbols`、`find_declaration`、
`get_diagnostics_for_file`、`initial_instructions` 六个工具，不创建另一套全仓库记忆。
Serena 仍会写本地日志和缓存；“只读”指不提供产品源码编辑能力。

本版本默认 REPL 不直接暴露旧式符号 MCP 工具，所以显式设置 `agent_interface: tools`。
采用 `ide` 单项目 context，使项目的六工具名单在启动时生效；实测 `codex` 多项目 context
启动会公开额外工具。本选择依据已安装 2.1.0 的行为，不从旧教程复制配置。

Codex 的本机 `.codex/config.toml` 已生成并忽略提交，含解析后的 Serena 命令、仓库 cwd、
180 秒启动／120 秒调用上限。Cursor 和 VS Code 的 Serena 项改为可移植命令；其他服务项保留。
当前聊天的工具清单没有 Serena，**独立 MCP 客户端成功不等于当前聊天已热加载**；重载项目后再检查六个工具。
Cursor／VS Code GUI 以及 Windows／macOS 尚未现场验收。两份编辑器配置中的旧 `stk-toolkit`
服务仍是另一项产品 Runtime 接入，不在本轮成功声明内。

## 安装和使用

在仓库根目录运行；需要已有 `uv`、Node/npm 和 `rg`。脚本仅在明确选择 action 时执行。

```bash
python3 tools/ai/dev.py install-serena
python3 tools/ai/dev.py install-checks
npm ci --prefix web --no-audit --no-fund
python3 tools/ai/dev.py configure-codex
python3 tools/ai/dev.py compile-db --build-dir /path/to/configured/cmake-build
python3 tools/ai/dev.py health
```

`configure-codex` 遇到已有配置会拒绝覆盖；在新机器合并 Serena 项，或保留旧文件后再生成。
移动仓库后需要更新本机路径。`compile-db` 校验数据库是否含本 checkout 的分析编辑器，
本次从 `/home/mnemora/opt/stk-build/merge-check` 复制 791 条编译命令到已忽略的根文件。
CMake 必须启用 `CMAKE_EXPORT_COMPILE_COMMANDS`；重新配置编译器、路径或选项后显式刷新，
已有不同内容会拒绝覆盖，检查旧文件后再移走。不要提交含本机绝对路径的编译数据库。

首次 LSP 启动可能下载语言服务器。此次 clangd 自动下载超时，后来从上游发布资产取得
`clangd-linux-19.1.2.zip`，按 Serena 已安装代码中的 SHA-256 校验后解压：
`7c09614eff857d590e4502ef516f035ff94cfb8b795de14ece5afbc53a206caf`。
下载成功和摘要匹配后才继续查询，未将损坏 ZIP 当作成功安装。
本机 Python／TypeScript 服务器也已启动。启动器关闭 dashboard 和 Serena usage reporting，
清空产品 key；测试脚本同时移除 `STK_TOKEN_PLAN_MODEL`，不读取凭据。

默认按需解析，不在每次启动时全量预热。可选 `python3 tools/ai/dev.py index` 会遍历更广范围：
本次 1039 个候选文件的预热运行约 4 分钟时只完成约三分之二，剩余 C++ 解析估计超过 20 分钟，
已主动中断；**未宣称全仓库索引完成**。定向三语言查询已独立通过，不以全量预热为使用前提。

## 查询习惯与测量

已知文本／路径先用限定目录的 `rg`，再只读相关行。需要类、方法、调用关系时，
先 `get_symbols_overview` 或不带正文的 `find_symbol`，定位后才取正文／引用；设置
`relative_path`、`max_matches`、`max_answer_chars`，超限就缩小问题。
声明与定义的名称路径可能不同：本次 C++ 定义为 `stk/app/AnalysisParameterDraft::undo`，
引用查询使用头文件声明 `stk/app/AnalysisParameterDraft/undo`。从定义查询曾错误返回空集；
空结果不能当作无人调用或删除依据。

复现实测（使用 Serena 安装环境中配套的 MCP SDK；本机 SDK 为 2.2.0）：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  /home/mnemora/.local/share/uv/tools/serena-agent/bin/python tools/ai/benchmark.py
```

脚本比较三个已知文件中的定义和引用，正文与显式源码范围逐字核对；源码变化后先复核行范围。
每例 rg 两次＋一次局部读取，Serena 两次调用；一次采样，磁盘缓存已热，C++ 全量预热同时在运行。
以下为 **UTF-8 返回文本字节**，不是模型 token、账单或整轮上下文节省率。

| 查询 | rg＋局部读取：定义／合计字节 | Serena：定义／合计字节 | rg／Serena 秒 |
|---|---:|---:|---:|
| Python `TaskSpec.to_dict` | 390／3962 | 409／7947 | 0.015／4.43 |
| C++ `AnalysisParameterDraft::undo` | 255／2769 | 361／7886 | 0.012／13.47 |
| TypeScript `cameraSignature` | 448／737 | 522／1278 | 0.011／1.95 |

三例正文匹配；Python 引用含 Runtime 客户端、服务和项目计划，C++ 含分析编辑器及测试，
TypeScript 含 `PayloadViewer` 导入和调用。已抽查源码确认这些引用。引用结果带所属符号及上下文，
rg 只提供候选匹配行，范围和语义不同，不能把大小差直接解释为同等信息量的效率比。
MCP 冷进程初始化约 1.40 秒，六工具定义序列化为 11033 字节，初始说明 6239 字节；
响应信封另有 JSON／structured-content 开销，完整值在本地报告中。宿主实际注入方式未测。

结论：本次三个已知小函数上，Serena 没有比熟练的局部读取节省返回文本；
它提供语义关系和结构化定位，适合跨模块调查。避免整文件输出确实有帮助，但 rg 也能做到。
不设“省 70% token”等未经测量的目标。

`handoff.md` 从 48045 字节缩为 12788 字节，减少 73.4%；开发计划从 85489 缩为 78018 字节。
两份合计少读 42728 字节（32.0%）；历史验证仍在开发日志和运行验收中按需查阅，压缩前本机副本在 `.ai-tools/`。
AOCI 一次完整正文约 430 KB、21 块；工具估算 143015 tokens，**不是宿主 tokenizer 实测**。
本轮上下文压缩触发过重复全量加载，因此当前 AOCI 规则有显著固定开销，不能笼统认定越多索引越省上下文。
保留仓库现行合同和完整覆盖；除合同要求的压缩刷新外，可靠认知持续复用，局部问题读取当前源码。

## 按需检查

```bash
python3 tools/ai/dev.py duplicates
python3 tools/ai/dev.py knip-web > .ai-tools/reports/knip-web.json
python3 tools/ai/dev.py knip-docs > .ai-tools/reports/knip-docs.json
```

jscpd 范围为 `suan`、原生 lib/app、web/src；包含 `cpp-header`，排除第三方、生成钩子等。
阈值 100 tokens／10 行，不启用 semantic／embedding 模式；`--fail-on-empty` 防止错路径得到空成功。
输出固定到仓库 `.ai-tools/reports/duplicates/`。不生成债务基线、不自动重构、不加入每轮启动。
跨语言相同契约、生成结构及刻意独立实现都需人工判断，重复率不是可直接删除比例。

Knip web 配置显式包括 Vite、Playwright 与动态注册的 `public/sw.js`；首轮将 Service Worker
误报为未用文件，补入口后消失。抽查 `accessorInfo`、`viewCamera`、`FRAME`，均仍在本模块使用：
“未使用导出”最多提示可审查 export 边界，不能删除函数／常量。
docs 的扫描也运行并返回问题，但本机未安装文档站完整依赖，缺失工具及动态组件发现仍有限，
其报告仅作线索。正式复核先按 `docs/README.md` 使用 Node 22.23.3、pnpm 8.15.9 冻结安装；
本轮工具环境 Node 24.20.0 不冒充文档站构建环境。

只把摘要和选定候选送入上下文，完整扫描结果留本地；缓存、报告、依赖和本机 Codex 配置均不提交。
官方入口：[Serena 安装](https://oraios.github.io/serena/02-usage/010_installation.html)、
[Serena 配置](https://oraios.github.io/serena/02-usage/050_configuration.html)、
[Codex MCP](https://developers.openai.com/codex/mcp)、
[Knip 工作原理](https://knip.dev/explanations/how-knip-works)、
[jscpd 配置](https://jscpd.dev/start/configuration)。
