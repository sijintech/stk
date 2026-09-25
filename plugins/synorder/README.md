# STK 的 Synorder 插件

> 状态：暂缓。STK 独立发展，桌面主线为 [STK 桌面程序 stk-desktop](../../docs/desktop.md)；
> STK 的基础安装、桌面程序与 Runtime 均不需要本插件或 Synorder。本插件与 `suan-synorder-node` 作为今后的可选集成保留。

本插件是可选集成：在 **Synorder Blender 宿主** 中加载 `synorder-stk` 插件。
在该集成中，插件不实现窗口、控件、面板或三维绘制代码；桌面与网页分别消费同一份 `ViewSpec v1`。
独立 Runtime 继续提供 Local / PBS / Slurm，关闭任何 GUI 不影响任务。

## 安装与启动

在安装了插件 SDK 的 Synorder 服务环境中安装两个包（已验证宿主提交 `3c29694`，SDK 位于 `2874d0a`）：

```bash
python -m pip install '/path/to/stk[server,science]'
python -m pip install '/path/to/stk/plugins/synorder[science]'
synorder pack install --workspace /path/to/workspace synorder.stk
```

安装命令只更新指定 Workspace 的插件声明和 `synorder.lock`。安装或修改 Python
包后必须显式复核并更新锁；发现插件时不执行入口代码，Hub 在核对锁后加载。
**本次开发未修改实际 Mnemora Workspace 或 NAS 配置。**

连接现有本地 Runtime 的管理员配置文件示例（文件中只放凭据环境变量名称）：

```json
{"url":"http://127.0.0.1:8765","token_env":"STK_RUNTIME_TOKEN","backends":["local"],"max_cpus":4}
```

```bash
synorder hub connect --workspace /path/to/workspace --connection-id stk-local \
  --space YOUR_SPACE --kind stk --config /path/to/stk-connection.json
synorder hub serve --workspace /path/to/workspace --origin https://YOUR_HUB
```

服务账号、权限、HTTPS 反向代理沿用 Synorder 的部署文档。实际 Runtime 端口以
`suan server status` 为准。桌面安装 Synorder 原生客户端及其定制 Blender 后启动：

```bash
python -m suan.workbench --server https://YOUR_HUB --state-dir /path/to/private-client-cache \
  --blender /path/to/synorder-blender
# 等价：synorder-native --workbench stk.workbench ...
```

Synorder 宿主只经上面的 `python -m suan.workbench` 启动；`suan-workbench` 后来启动的 STK 自有 Blender 工作台
已归档于标签 `archive/blender-workbench-2026-09`，该命令随之移除。

用网页生成的一次性配对码连接桌面。网页和手机 PWA 在导航中选择“STK 科学工作台”。
客户端缓存必须是独立目录；不接管旧客户端缓存、不复制旧服务令牌。

## 主动连接的执行节点

Hub 的绑定配置改为：

```json
{"transport":"node","node_id":"compute-01","token_env":"SYNORDER_NODE_TOKEN","backends":["local","pbs","slurm"]}
```

通过管理员已有的凭据分发方式，让 Hub 与该节点各自配置相同的节点凭据环境变量。
Runtime 的本机令牌只留在节点，不经过 Hub。节点独立于 GUI 运行：

```bash
python -m pip install '/path/to/stk[server,control]'  # 节点需要 WebSocket 依赖
suan-synorder-node --server https://YOUR_HUB --node-id compute-01 \
  --token-env SYNORDER_NODE_TOKEN --runtime-config /path/to/runtime/config.json
```

远程使用 WSS；明文 WS 仅允许回环开发环境。首版 Hub 使用单个进程承载节点连接，
持久任务仍由数据库和 Runtime 记录；重启服务或节点后按原请求核对，不重提不确定的提交。
连接停用后允许原节点继续提供取消与对账，拒绝新任务。

## 插件范围

- `stk.configuration.save` / `stk.submit`：固定解析场模板、参数扫描、后端与资源上限校验。
- `stk.attach`：按现有 Runtime 任务编号收录历史或运行中的任务，不上传脚本、不重新提交。
- `stk.visualize` / `stk.accept`：结果图表和带证据的人工验收。
- `stk.scene` / `stk.probe`：服务器端 STK/VTK 后处理；原始数据探针使用双精度三线性插值。
- `stk.workbench`：任务列表、参数、标量切片、等值面、向量显示入口；手机减少行数和显示网格预算。

当前内置模板是 `f(x,y,z)=A(x+2y+3z)` 的确定性 I/O 验证，**不是物理求解器**。
真实专业求解器（如 MuPRO）由 STK Runtime 运行；STK 的新 GUI 工作流在自有 Blender 工作台中开发，
本插件在恢复 Synorder 集成时再补充对应的 Action/Query/ViewSpec。
结果文件逐个版本引用；VTI 的单位、坐标、时间步取原始元数据。源文件缺少这些元数据时保持未标注，
不通过改变标签制造时间序列。首版经 Hub 下载的单个源文件预算为 16 MiB；更大场先在执行节点缩减。

## 停用、升级和回退

```bash
synorder pack disable --workspace /path/to/workspace synorder.stk
# 重启 Hub：隐藏新操作和视图，保留已锁定方法用于已接受任务的对账和取消。
synorder pack enable --workspace /path/to/workspace synorder.stk
# 无未完成任务时才可 remove 或批准新的包版本/哈希。
```

插件配置变化后，旧 Hub 实例拒绝新提议与确认，要求重新加载；已接受任务的监控不依赖 GUI。
包升级和移除检查正在执行的版本引用。不要用包管理器强删尚有任务的版本。
既有 Synorder `research` 示例与历史资源保留；新插件使用独立 Action、View 和 Method ID，可并行运行。

STK 桌面程序 `stk-desktop`、控制服务与节点代理是 STK 的桌面主线，不是待删除的迁移遗留；此前的 STK 自有
Blender 工作台（`suan-workbench`，兼容名 `suan-blender`）已归档于标签 `archive/blender-workbench-2026-09`；Qt 界面保留为旧客户端。两条路径的数据不会自动导入或重放。
Rust/egui 原型不再扩展。

## 验证

在安装了 Synorder Hub、该插件和 STK 科学依赖的开发环境中：

```bash
python -m pytest plugins/synorder/tests/test_plugin.py
python plugins/synorder/tests/browser_smoke.py --output /tmp/stk-plugin-browser \
  --runtime-python /path/to/stk-python
```

浏览器用 Playwright Chromium，数据、账号与服务都位于临时目录；导出的是合成数据截图。
结果与平台边界见 [validation.md](validation.md)。本次未调用云端模型或创建 API 密钥。
