# 模型网关、数据边界与本地模型（S1 设计）

更新：2026-10-08。状态：**S1 开发中，下文为设计；已交付的部分在“进度”中标明，其余未实现。**
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

## 进度

- **S1a（已交付）**：格式 12 的 `project_labels` 与 `suan/project/labels.py`、`project.labels.set/list` 与 `project.labels.changed`、
  `stk.project.mark_public/mark_private/labels`；`suan/models/`（端点登记、端点密钥、网络设置、`OpenAICompatibleAdapter`、`ModelGateway`），
  `RequestExecutor` 的发送前检查（`PolicyDenied` → `conflict`，请求保持待发送）；后台服务 `models.list`、`models.endpoints.add/remove`、
  `models.keys.set/clear`、`models.policy.set` 与 `models.changed`，脚本只有 `models.list`（`stk.models.list()`）。
  阿里云适配器的载荷检查、单次发送与回复解析参数化后共用；顺带修复其读取器在服务器关闭连接（HTTP/1.0 或 `Connection: close`）时
  读完正文后再用已关闭套接字的问题（本机服务器会这样回复）。
- **S1b（已交付）**：桌面 `ModelSettings`、`ProjectDataLabels`；数据页“公开数据”；AI 助手选择端点与模型、添加端点的密钥、
  “模型与网络”（网络设置、添加与移除端点）；AI 助手与“讨论”页说明不能发送的原因（`model_gate.hh`）。
- S1c 本机一键部署、S1d 能力分档与自动切换：未实现。

已知限制：发送前检查不写入请求记录；上下文只来自一张参数表，标注以表为单位（不细到字段或行）；文件标注目前没有用到（为文献与数据集预留）。
