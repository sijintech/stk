# 模型请求、阿里 Token Plan 与恢复

格式 8 的 `project_requests` 保存请求意图、固定输入及执行观察。当前已接入阿里 Token Plan 的
OpenAI 兼容文字接口，使用指定地址 `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。
普通创建、查询、重开和取消不会发出新的模型请求；只有明确 **发送给模型** 或 `p.requests.start(...)` 才发送。
所有请求状态与文字回复均不修改参数修订、撤销历史、草案或仿真任务。

旧项目先明确 **备份并升级项目**，最低需要格式 8；本轮没有新增 SQLite 格式。普通打开不迁移，
规则见[项目指南](project.md#数据库备份与显式升级)。AI 工作区已接入临时流式显示；远端查询、工具提案及自动执行尚未实现。

## 配置本机凭据和模型

适配器名为 `aliyun-token-plan/1`，固定上述 HTTPS 地址、Chat Completions 协议和文字提示规则。
它只读取启动 STK 时继承的环境变量，不读取 `OPENAI_API_KEY`、通用 `DASHSCOPE_API_KEY` 或项目内的 env 文件。

| 环境变量 | 内容 |
|---|---|
| `STK_TOKEN_PLAN_API_KEY` | 你自己的 Token Plan 专属 API Key；仅保存在进程内存，不写入项目 |
| `STK_TOKEN_PLAN_MODEL` | 可选的默认模型 ID，须是你的套餐支持的文字模型；也可在原生请求页填写 |

地址与专属密钥要求见[阿里云接入说明](https://help.aliyun.com/zh/model-studio/more-tools)。
该说明也限制 Token Plan 的工具用途，列出自动化平台及自定义应用后端等不支持的场景。
**STK 的协议适配不代表阿里已确认本应用适用该套餐**；实际启用前需核对你的套餐允许范围。
2026-09-30 已用 `qwen3.7-plus` 完成一次 Linux 桌面桥的真实账户调用及 SQLite 回复保存/重开验证，
输入仅为人工构造的 `temperature = 300 K`。这不代表全部模型、科研回答质量或双平台原生按钮已验收。
自动化回归仍使用受控 HTTP 响应，不消耗套餐额度；详见[验收记录](runtime-validation.md)。

当前建议以 `qwen3.7-plus` 作为讨论和代码辅助的起点：它在[Token Plan 支持列表](https://help.aliyun.com/zh/model-studio/token-plan-personal-overview)中，
官方[文本模型指南](https://help.aliyun.com/zh/model-studio/text-generation-model)将其列为能力与成本均衡的选项。
这是截至 2026-09-30 的配置建议，程序不硬编码默认模型或自动替换已保存请求中的型号。

在仓库目录中打开终端，使用不回显的输入提示设置密钥，随后从同一个终端启动 STK。
不要把密钥写进 Python 面板、聊天、项目表格或提交到 Git。以下设置只影响当前终端及其子进程。

macOS（Bash）：

```bash
read -r -s -p 'Token Plan API key: ' STK_TOKEN_PLAN_API_KEY
printf '\n'
export STK_TOKEN_PLAN_API_KEY
export STK_TOKEN_PLAN_MODEL=qwen3.7-plus
bash desktop/setup-macos.sh
```

Windows（PowerShell）：

```powershell
$stkModelCredential = Read-Host 'Token Plan API key' -AsSecureString
$env:STK_TOKEN_PLAN_API_KEY = [System.Net.NetworkCredential]::new('', $stkModelCredential).Password
Remove-Variable stkModelCredential
$env:STK_TOKEN_PLAN_MODEL = 'qwen3.7-plus'
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1
```

已经在 Bash 的 `~/.bashrc` 中 `export` 密钥时，无需重复输入；可在同一文件中添加
`export STK_TOKEN_PLAN_MODEL=qwen3.7-plus`。打开新的交互式 Bash，或在当前交互式 Bash 中运行
`source ~/.bashrc`，再从该终端启动 STK。部分 `.bashrc` 会提前跳过非交互式 shell，
所以后台进程、桌面图标或已运行的应用不一定读到该配置；STK 本身不会执行 shell 启动文件。
macOS 使用 zsh 时应在对应 shell 中导出，Windows 则按上面的 PowerShell 设置。

已有窗口不会继承另一个终端后来修改的环境变量；配置变更后重新启动 STK。
**刷新本机配置** 和 `p.requests.provider()` 只检查桥进程的环境，不联系服务，也不能证明密钥有效、
模型可用或套餐仍有额度。模型列表不硬编码，避免把账户没有的模型当成可用模型。
此版本不自动使用系统 HTTP 代理，不支持自定义端点、证书或连接转发。

## 在原生界面中发送

可从项目页头或文件菜单打开新的 [AI 工作区](desktop.md#ai-准备工作区)，在同一页完成捕获、准备问题（只保存）、
核对及明确发送。工作区显示时，对运行中/不确定记录约每秒读取一次本地状态，最多 90 秒；出错或到期暂停，
明确刷新可继续读取。这个过程不会查询提供方、重发或核对遗留执行。
由本桥正在执行的流式请求会显示 **临时回复（尚未保存）**；每次读取替换当前片段快照，不重复拼接。
只有完整回复通过校验后才保存为正式助手消息。断流、取消或桥退出不保存半条回答；
取消时立即隐藏临时片段，但已发出的请求仍可能返回完整有效回复并保存。切换项目不会串入其他项目的片段。
其他桥进程或旧版桥不提供临时片段，仍可读取正式状态和完整回复；没有片段不代表远端未执行或已停止。
下面保留 **项目表格 → 讨论 → 请求** 页的操作步骤；该页仍需手动刷新。

1. 按[上下文指南](project-contexts.md)明确捕获行和字段，保存一条用户消息，核对所引用的上下文。
   若从列表选择历史消息，先点击 **查看选定记录**。只会发送已经保存的消息及其上下文。
2. 进入 **项目表格 → 讨论 → 请求**，在 **准备模型请求** 核对服务地址、凭据状态和模型 ID。
   面板显示当前载入的用户消息及其上下文 ID；未保存的输入、其他消息和实时表格不会自动带入。
3. 点击 **准备请求（不发送）**。这一步保存请求 ID、模型配置与固定来源，状态为 **尚未发送**。
   同一打开会话中重复准备相同消息/模型复用原请求，改变输入会形成新请求。
4. 核对请求详情中的模型、来源修订及上下文，再点击 **发送给模型**。只有尚未发送且已有本机凭据的
   已注册适配器请求可发送。发送前检查失败仍为尚未发送，不占用执行权。
5. 点击 **刷新请求记录** 读取结果；这个讨论子页不会自动轮询或显示流式片段。成功后显示 **回复已保存**，
   点击 **查看保存的回复** 打开完整文字。代码块是普通文字，不会执行。

**请求取消** 保存取消意图，并通知本桥的执行器。若尚未发出，直接取消；发出后没有远端取消协议，
不能宣称阿里已停止计费或生成。等待期间若收到完整有效回复，仍可能保存为完成，并保留取消意图。
**核对遗留执行** 只检查本机执行锁：执行器仍活跃时报忙；执行器已丢失则将已启动请求记为不确定，
不重新发送、查询阿里或变回尚未发送。普通刷新只读取数据库。

关闭项目只释放界面句柄，已经明确开始的请求继续写回原项目，不能改投当前打开的另一个项目。
退出应用或桥关闭会隔离迟到回复，并尽力把活动请求记为不确定；如果数据库不可写或进程直接被结束，
重开后可用 **核对遗留执行** 检查旧的已启动记录。重开不自动发送、恢复或应用任何操作。

## Python 接口

先按[上下文指南](project-contexts.md)保存上下文及 `user` 消息。以下 `message` 是明确保存的那条消息：

```python
from uuid import uuid4

p = stk.project
provider = p.requests.provider()
print(provider)  # 只有配置状态与环境变量名称，不含密钥。
assert provider['model'], '先设置 STK_TOKEN_PLAN_MODEL，或在代码中明确填写模型 ID'

request = p.requests.create(
    message['id'], request_id=str(uuid4()),
    configuration={'adapter': provider['adapter'], 'model': provider['model'],
                   'max_output_tokens': 4096},
)
print(request['status'])  # pending，尚未发送。
```

检查保存的请求及模型后，另行明确运行：

```python
started = p.requests.start(request['id'])  # 返回已持久保存的领取记录，不等待网络完成。
```

之后按需查询或取消：

```python
current = p.requests.get(request['id'])
print(current['status'], current['error_code'])
if current['status'] == 'completed':
    print(p.discussion.get(current['result']['message_id'])['text'])

# 只在确实要取消时执行：p.requests.cancel(request['id'])
# 只在需核对遗留执行时执行：p.requests.recover(request['id'])
print(p.requests.list(limit=20))
```

这些可选桥方法通过 `hello.methods` / `stk.operations()` 发现；`p` 固定原打开句柄。
响应丢失时先按原 ID 查询，不自动重发。对已开始或终态请求再次调用 `start` 只返回记录，不发送第二次。
若明确需要一次新的请求，使用新的 UUID；它是新调用，不保证替代或取消先前远端工作。

## 固定输入与响应规则

`configuration` 只接受必填 `adapter`、`model`，以及可选 `temperature`、`max_output_tokens`。
名称为 1–128 字符的 ASCII 标识，以字母或数字开头，其余允许 `.`、`_`、`:`、`/`、`-`，禁止 `//`。
输出 token 上限为 1–32768 的整数，默认 4096；通用存储接受 0–2 温度，阿里适配器要求 `< 2`。
配置名称不会动态导入模块，接口不接受 URL、认证字段或任意扩展参数。

请求保存项目、消息、上下文、来源修订、规范化配置、`stk.text/1` 输入版本与完整输入摘要。
每次读取验证来源链；后续表格、选择或字段变化不会改变请求依据。助手消息 UUID 从项目与请求身份派生，
手工消息不能占用它。相同请求 UUID 和相同内容返回原记录，改变内容复用 UUID 会冲突。

阿里适配器在领取执行权前验证输入并将凭据、请求体绑定到本次调用。它以普通 HTTPS 发出一次
`POST /compatible-mode/v1/chat/completions`，执行器使用 `stream=true`、`stream_options.include_usage=true`、
`enable_thinking=false` 和 `max_tokens`；适配器保留原非流式调用接口供已有调用方使用。
不发送工具、不跟随重定向、不自动重试。请求体只包含固定系统说明、保存的上下文及用户文字，
不会读其他文件、查询当前表格或附带完整讨论历史。参数依据见[阿里 Chat Completions 文档](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)。

保存输入限 1 MiB，重新编码的请求体限 2 MiB，HTTP 回复限 1 MiB，最终文字限 64 KiB UTF-8。
不会静默裁剪超限内容；目前没有本地模型 token 计数器，实际上下文长度和输出预算仍由服务校验。
网络步骤共用 60 秒超时预算；取消不强制中止已发出的 HTTP 读取。
流式回复须是一条助手文字，先收到 `finish_reason=stop`，再收到 `[DONE]`，并正常结束 HTTP 消息体；
截断、工具调用、无效 JSON、超限或仅推理内容不能冒充完整回复。协议依据见[阿里流式文档](https://help.aliyun.com/zh/model-studio/stream)。
同一执行器最多保留 8 条仍在执行的请求；满额时新请求保持尚未发送，可在已有执行结束后明确发送。
`p.requests.progress(id)` 只读返回正式 `request` 和可空的临时 `progress`，片段不进入 SQLite。
临时快照包含执行器身份、序列号、累计文字和 UTF-8 字节数；取消、不确定、终态和执行器关闭时不返回片段。

HTTP 明确拒绝保存为 `failed/adapter_failed`；非法完整响应为 `failed/response_invalid`。
流式结束证据到齐前断流、连接中断、超时、重定向或不确定服务器状态保留 `uncertain/transport_uncertain`。
错误响应正文、异常原文、认证头和密钥不写入项目。`result` 仅含助手消息 ID、文字摘要及受限观察：
模型、远端请求 ID、非负 64 位输入/输出 token 数。完整消息和完成标记原子保存，失败全部回滚。

## 状态与执行器

| 状态 | 含义 |
|---|---|
| `pending` | 尚未领取发送权；预检失败或重开不自动开始 |
| `running` | 领取已保存，可能已经发送；不证明执行器仍活跃 |
| `completed` | 完整文字和助手消息关联已原子保存 |
| `failed` | 确定失败，如明确拒绝或回复校验失败 |
| `cancelled` | 发送前取消，或已获得明确的取消完成证据 |
| `uncertain` | 可能已发送，缺少完整确定结果；不能自动重发 |

`suan.project.request_executor.RequestExecutor` 默认不注册适配器，桥显式注册 `aliyun-token-plan/1`。
可选 `prepare(frozen_input)` 只做本机检查，返回绑定配置的发送对象；随后才领取一次发送权。
适配器提供 `send(frozen_input, cancel_event)`，返回文字或 `TextResponse`。
`DefinitiveFailure` 表示确定拒绝，`InvalidResponse` 表示回复无效，`ConfirmedCancellation` 只用于确定取消。

执行前取得 `.stk/request-locks/<请求 UUID>.lock` 的非阻塞系统锁，再在 SQLite 事务内领取执行权；
发送期间不持有 SQLite 事务。锁文件保留，实际所有权由打开的系统锁决定，持有到 worker 退出。
保证限于本机提供正确文件锁语义的项目文件系统，不是跨机器协调。

`shutdown(wait=False)` 立即设置关闭标记，后台尽力保存不确定状态，避免应用退出等待数据库锁。
工作线程先退出时也会尽力补记观察；不能因此提前释放仍在执行的 worker 的锁。
完成前发生本地保存失败时保留 `uncertain/local_save_failed`；当前没有输出暂存或远端查询，
已丢失的文字不能自动恢复。更多阶段见[后续模型集成](design/review-drafts-and-conversations.md#后续模型集成)。
