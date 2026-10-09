# 模型网关、数据边界与本地模型（S1 设计）

更新：2026-10-09。状态：**S1 开发中；已交付的部分在“进度”中标明（S1a–S1c），其余未实现。**
上位方案：[思劲平台方向](sijin-platform-2026-10.md)第 5.1 节与“所有者决定”第 2、3、8 条。

## 要做到什么

- 智能体与 AI 助手调用的模型来自一个统一的“模型网关”：已接入的阿里云 Token Plan，加上任意 OpenAI 兼容端点（本机的 llama.cpp / vLLM、
  机构内的服务器、其他第三方 API）。
- **数据默认不对外发**：只有人工标注为“公开”的数据，才可以发给外部端点；本机与机构内端点不受此限。
- 可以设置是否允许访问外网；在本机一键部署合适的模型；按能力自动切换模型。

## 分步

| 步 | 内容 |
|---|---|
| S1a | 数据标注（项目格式 12）；端点登记与网络设置；通用 OpenAI 兼容适配器；发送前检查（网络设置 + 数据边界）；脚本与后台服务接口 |
| S1b | 桌面：参数表“公开数据”标注；AI 助手选择端点与模型并说明能否发送；模型与网络设置页 |
| S1c | 本机一键部署：硬件探测、模型目录与推荐、安装运行时、下载并校验权重、启动与健康检查、自动登记为本机端点 |
| S1d | 能力分档与自动切换：端点/模型的档位与能力标签，按任务、数据边界、网络设置与可用性选择，失败回退 |

## 数据标注（项目格式 12）

- 表 `project_labels(id, kind, object_id, label, at, note)`，只追加；对象的当前标注取其最后一条，**没有记录即为私有**。
  `kind` 为 `table`（参数表）或 `file`（文件索引记录），`label` 为 `public` 或 `private`。
- 与归档一样：标注不是项目编辑，不推进修订、不进入撤销，但每次标注都留时间与备注，可追溯；旧项目经“备份并升级项目”显式升级到格式 12。
- 上下文（AI 问答的数据来源）取自一张参数表；发往外部端点前检查这张表**当前**是否为公开。用户输入的问题文字由用户本人写给模型，不属于此检查。
- 服务方法 `project.labels.set {handle, items:[{kind,id}], label, note?}`、`project.labels.list {handle, kind?}`，事件 `project.labels.changed`；
  Python `stk.project.mark_public(kind, ids, note=None)`、`stk.project.mark_private(kind, ids)`、`stk.project.labels(kind=None)`。

## 端点与网络设置（本机，存于后台服务状态目录）

- **端点**：内置 `aliyun-token-plan`（外部，适配器 `aliyun-token-plan/1`，沿用现有密钥设置）；用户添加的 OpenAI 兼容端点
  `{id, name, base_url, location, models}`，适配器标识为 `openai-compatible/1:<id>`。
- **位置**：主机为回环地址（`localhost`、`127.0.0.0/8`、`::1`）时为 `local`（本机）；其他地址默认 `external`（外部），用户可声明为
  `internal`（机构内，如课题组的 GPU 服务器）。外部端点必须用 HTTPS；本机与机构内端点可以用 HTTP。
- **密钥**：每个端点的密钥与现有做法相同——只在环境变量或状态目录中的 0600 文件，不进项目、日志与请求记录。
- **网络设置**：`offline`（只用本机端点）、`organization`（本机与机构内端点）、`internet`（全部）。默认 `internet`（保持现在可用阿里云的行为），
  数据边界与网络设置独立：即使允许外网，私有数据也不发往外部端点。
- 服务方法 `models.endpoints.list/add/remove`、`models.policy.get/set`，Python `stk.models.*`。

## 发送前检查

请求在开始发送时（`RequestExecutor.start`，领取之前）检查，不通过则拒绝并说明原因（`conflict`），请求保持待发送：
1. 端点存在且已配置；
2. 网络设置允许该端点的位置；
3. 端点位于外部时，请求所用上下文的参数表当前标注为公开。

检查的结果不写入请求记录；请求冻结的配置（适配器、模型）已能说明发往了哪个端点。

## 本机一键部署（S1c）

- **硬件与推荐**（`models.local.recommendations`，只读）：操作系统与架构、CPU 核数、内存总量与可用量、模型目录所在磁盘的剩余空间、GPU
  （NVIDIA 经 `nvidia-smi` 读型号、显存与驱动，按整 GB 计；Apple Silicon 按 Metal 默认可用的统一内存——36 GB 及以下约三分之二、以上四分之三，
  且不超过当前可用内存）、这里的 llama.cpp 能否用 GPU（`llama_gpu`：Linux x86_64 的 Vulkan 版需系统装有 Vulkan 加载器，Apple 为 Metal，
  Windows 与 Linux arm64 随附的是 CPU 版，管理员用 `STK_LLAMA_SERVER` 指定自己的版本时视为能用），以及目录中每项能否放下（`fits`）、
  用 GPU 还是 CPU、放不下的原因（`disk`、`memory`、`gpu_memory`、`needs_linux_nvidia`）和是否推荐。已下载的部分（含未完成的部分文件）不再计入所需磁盘空间。
  不探测已安装的 vLLM；不安装、不启动任何东西。
- **模型目录**（随 STK 发布的 `suan/models/catalog.json`，格式 `stk.model-catalog/1`；`STK_MODEL_CATALOG` 可换用别的目录）：每项给出模型、档位
  （tiny/small/medium/large）、运行时（llama.cpp 或 vLLM）、量化、文件名与大小及 SHA-256、来源（先 ModelScope、再按固定修订的 Hugging Face）、
  所需内存或显存、上下文长度与启动时的上下文（`serve_context`）、许可与能否商用、说明；`recommend_on` 限定在哪种设备上推荐（`[]` 表示备选，不作默认）。
  目录只收许可允许商用的模型（Apache-2.0、MIT），大小与哈希取自发布者仓库在固定修订下的 API（ModelScope 的同名文件一致），2026-10-08 核对。
  首版 14 项：Qwen3.5-4B、Qwen3.5-9B、Qwen3.8-27B（稠密）、Qwen3.6-35B-A3B（MoE，每个 token 激活 3B）各有 Q4_K_M 与 Q8_0 的 GGUF
  （另有 Qwen3.5-4B Q4_K_M 的 8K 上下文版，同一文件），
  Gemma 4 E4B/12B 的谷歌官方 QAT Q4_0 作备选；vLLM 档为 Qwen3.8-27B、Qwen3.5-122B-A10B 的 BF16 与 GLM-5.3-Flash（发布者原生 FP8）。
  Qwen3.5 起官方不再发布 GGUF：4B/9B 用 LM Studio 社区转换，27B/35B 用 llama.cpp 维护者（ggml-org）的转换。
- **推荐规则**：只推荐 llama.cpp 档，在能放下（llama.cpp 能用的单块 GPU，或可用内存的九成）的项中依次比较：档位高者优先；同档中能整个放进 GPU 的优先；
  再比模型大小；同一模型的 8 位版只在余量达到所需量四成以上时推荐，否则推荐 4 位版。Qwen 为各档默认（Gemma 只作备选，`recommend_on: []`）；
  中档的稠密 27B 只在 GPU 上推荐，35B-A3B 只在 CPU 上推荐（每个 token 只算 3B，CPU 上快得多）；8 GB 内存的笔记本推荐 4B 的 8K 上下文版。
  vLLM 档只评估能否放下（需要 Linux 与 NVIDIA，按总显存），不推荐：STK 还不能启动 vLLM。推荐只是建议，用户明确点“安装”才下载。
- **安装**（`models.local.install`，桌面明确操作，不进脚本目录）：要求网络设置为“允许外网”；llama.cpp 运行时取官方 GitHub 发布的预编译包
  （b11429，即 v0.6.0；Linux x86_64 用 Vulkan 版——没有 `libvulkan.so.1` 时其 GPU 后端不加载，退回 CPU；Linux arm64 与 macOS x86_64 为 CPU 版，
  macOS arm64 含 Metal，Windows 为 CPU 版），同一运行时只下载一次；权重按来源顺序尝试，断点续传（部分文件以内容哈希命名，换版本时清除），
  下载完逐文件核对大小与 SHA-256，核对通过才改为正式文件名，不一致即丢弃并试下一个来源。进度以事件 `models.local.progress` 报告（节流），可取消，
  取消后保留已下载的字节；网络设置改为离线或机构内时，正在进行的下载被取消。
- **离线导入**（`models.local.import`）：在没有外网的电脑上，从本地文件或文件夹导入 llama.cpp 档的权重与运行时压缩包，同样复制后核对大小与哈希，
  在后台进行。解包运行时拒绝越出目标目录的成员，tar 包用 Python 的 `data` 过滤器（不支持时拒绝链接）。
- **启动**（`models.local.start/stop`）：在 `127.0.0.1` 的空闲端口启动 `llama-server`（`--jinja`、`--alias <目录项>`、`-c <serve_context>`、
  `--no-slots`、`--reasoning off`；不指定 `-ngl`，由 llama.cpp 按当前空闲显存决定放多少层到 GPU），健康检查通过（最多 10 分钟）后登记为本机端点 `local-<目录项>`；
  服务器自行退出、启动失败或根本无法启动（例如运行时已被删除）时报告失败、不再自动启动；正在运行的模型随后台服务退出而停止（同一进程组），下次桌面连上后台服务后按记录自动启动；
  后台服务异常退出留下的服务器进程在下次启动时按记录的 PID 与创建时间结束。发往受管本机端点的问题在其服务器未运行时被拒绝并说明原因。
  日志写入状态目录 `models/local/logs/`。管理员可用 `STK_LLAMA_SERVER`（路径或 JSON 命令列表）指定自己编译的 llama-server。
- **本机服务器的保护**：llama-server 默认允许所有 CORS 来源，没有密钥时浏览器里的任何网页都能调用它，并从 `/slots` 读到之前的提示（含私有数据）。
  因此每次启动生成一个随机密钥，经环境变量 `LLAMA_API_KEY` 传入（不出现在命令行），只在后台服务内存中作为该端点的受管密钥（优先于
  `STK_MODEL_KEY_<ID>` 等其他来源），停止或失败时清除；并关闭 `/slots`。服务器进程的环境去掉名称含 KEY、TOKEN、SECRET、PASS、CREDENTIAL、
  CREDS、AUTH、PROXY 的变量（如 Token Plan 密钥、带口令的代理），它只在回环地址监听、读本地文件。
  这类端点在 `models.list` 中标为 `managed`：不能在设置中改密钥或单独移除，随模型一起移除；`local-` 开头的端点 ID 留给本机模型，不能手动添加。
- **不思考**：与 Token Plan 一致（请求带 `enable_thinking: false`），本机服务器以 `--reasoning off` 启动。实测 Qwen3.5-4B 在 48 核 CPU 上
  开着思考时一个两句话的回答要生成 2,335 个 token、用 188.6 秒，关掉后 14.9 秒。
- **期限与取消**（OpenAI 兼容端点）：建立连接（含 TLS 握手）仍限 60 秒；之后本机与机构内端点每次请求最长 30 分钟（大模型在 CPU 上每秒只有几个 token），
  等待中取消会立即关闭连接——本机端点记为“已取消”（回复只在这台电脑上），机构内端点记为“不确定”；外部端点 5 分钟、不能在途取消
  （与 Token Plan 相同，后者仍为 60 秒）。
- **移除**（`models.local.remove`）：停止服务器、删除权重与端点，运行时保留。
- **范围**：S1c 完整支持 llama.cpp；vLLM 档只评估能否放下，STK 不下载也不启动（桌面不提供安装），权重下载与启动由用户按说明自己完成，
  再添加为端点；自动下载、安装与启动 vLLM 为后续步骤。

## 进度

- **S1a（已交付）**：格式 12 的 `project_labels` 与 `suan/project/labels.py`、`project.labels.set/list` 与 `project.labels.changed`、
  `stk.project.mark_public/mark_private/labels`；`suan/models/`（端点登记、端点密钥、网络设置、`OpenAICompatibleAdapter`、`ModelGateway`），
  `RequestExecutor` 的发送前检查（`PolicyDenied` → `conflict`，请求保持待发送）；后台服务 `models.list`、`models.endpoints.add/remove`、
  `models.keys.set/clear`、`models.policy.set` 与 `models.changed`，脚本只有 `models.list`（`stk.models.list()`）。
  阿里云适配器的载荷检查、单次发送与回复解析参数化后共用；顺带修复其读取器在服务器关闭连接（HTTP/1.0 或 `Connection: close`）时
  读完正文后再用已关闭套接字的问题（本机服务器会这样回复）。
- **S1b（已交付）**：桌面 `ModelSettings`、`ProjectDataLabels`；数据页“公开数据”；AI 助手选择端点与模型、添加端点的密钥、
  “模型与网络”（网络设置、添加与移除端点）；AI 助手与“讨论”页说明不能发送的原因（`model_gate.hh`）。
- **S1c（已交付）**：`suan/models/local.py`（目录读取与校验、硬件探测、评估与推荐、可续传并核对的下载、安全解包、`LocalModels`
  安装/导入/取消/启动/停止/移除、服务器监护与自动启动、遗留进程回收）、`suan/models/catalog.json`（14 项与 5 个平台的 llama.cpp 构建）；
  后台服务 `models.local.list/recommendations/install/import/cancel/start/stop/remove` 与事件 `models.local.progress`，脚本只有 `models.local.list`；
  发往受管本机端点前检查其服务器在运行。桌面“模型与网络”页的“本机模型”：硬件概况、各项能否放下与推荐、安装进度、启动/停止/移除/取消、
  从本地文件导入。
- S1d 能力分档与自动切换：未实现。

S1c 已知限制：
- vLLM 档 STK 不下载也不启动；不带 CUDA 版 llama.cpp（Linux x86_64 用 Vulkan 版，Windows 与 Linux arm64 用 CPU 版，推荐时这两者按内存而不按显存判断），
  需要 CUDA 时用 `STK_LLAMA_SERVER` 指定自己编译的版本。Linux 上用 GPU 还要求系统装有 Vulkan 加载器（`libvulkan1`）与显卡驱动；
  没有加载器时按内存推荐，装有加载器但驱动不支持 Vulkan 时 llama.cpp 会用 CPU 而推荐仍按显存判断。
- 预编译的 Linux 版 llama.cpp 需要 glibc 2.34、GLIBCXX_3.4.30、`libssl.so.3` 与 `libgomp.so.1`（Ubuntu 22.04+、Debian 12+）；
  CentOS 7、RHEL/Rocky 8 与 9 上不能运行，需要自行编译后用 `STK_LLAMA_SERVER`。启动前不做这项检查，失败时在日志与状态中报告。
- 运行时从 GitHub 下载，校园网可能很慢或不通；可离线导入，后续由思劲提供镜像。ModelScope 的来源不固定修订，文件更新后哈希不符会退到 Hugging Face。
- 内存需求按公式估算（权重 + 32768 个 token 的 f16 KV 缓存 + 1.5 GB），没有逐项实测；推荐按 GiB 计，比公式略保守。
- 中断的下载可以续传，但界面上还不能删除未完成的部分文件（移除只对已安装的项）。
- 只收纯文本模型（不含视觉投影文件），每个 llama.cpp 档一个 GGUF 文件；目录随 STK 版本更新，不在线更新。
- 本机模型统一不思考（`--reasoning off`），还不能按任务开启（留给 S1d）；工具调用要到 S2 才用到。
- `STK_LLAMA_SERVER` 指定的构建须支持 `--reasoning` 与 `--no-slots`（2026 年的 llama.cpp）。

已知限制：发送前检查不写入请求记录；上下文只来自一张参数表，标注以表为单位（不细到字段或行）；文件标注目前没有用到（为文献与数据集预留）。
