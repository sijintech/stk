# STK 管理 SSH 连接

STK 可以为原生桌面和 CLI 管理访问 Linux Runtime 的 OpenSSH 隧道。Jobs 的工作区、任务、
日志、上传、下载和现有结果分析共用该连接。远端 Runtime 仍仅监听回环地址；这项能力不包含
任意两台桌面的直接配对、远程 Python 或远程页面控制。

## 准备

客户端安装 OpenSSH，并确保启动 STK 的环境能找到 `ssh`。macOS/Linux 通常已提供；Windows
使用系统的 OpenSSH Client。在终端先配置密钥或 SSH agent，确认服务器指纹并完成一次登录。
STK 使用批处理认证和严格主机密钥检查，不弹出密码框，也不自动信任新主机。
选项行为见 [OpenSSH 配置手册](https://man.openbsd.org/ssh_config)。

可以在用户 OpenSSH 配置中为 STK 准备一个 Host：

```sshconfig
Host stk-cluster
    HostName compute.example.org
    User scientist
    IdentityFile ~/.ssh/id_ed25519
    # Port 2222
    # ProxyJump login.example.org
```

STK 继承该 Host 的认证、端口、跳板机和 known_hosts 设置。建议使用专门的 Host 别名，
其中不配置额外的 LocalForward/RemoteForward。STK 禁用连接复用和 LocalCommand，
只管理自己启动的进程；已有终端 SSH 会话不受影响。SSH 服务端须允许本地转发。

服务器按 [Runtime 指南](runtime.md) 启动 API 和 supervisor，并取得 Runtime token。
SSH 身份和 Runtime token 是两层独立认证。不要把 token 写进 Host、URL 或命令行。

## 桌面使用

在 Jobs 的连接区域选择“添加 Runtime”：

1. 输入连接名称，例如 `cluster`。
2. URL 输入**服务器上的**回环地址，例如 `http://127.0.0.1:8765`，端口必须明确。
3. 勾选“由 STK 管理 SSH 隧道”，Host 填 `stk-cluster`。
4. 填写 Runtime token，或选择本机 token 文件，保存连接。

选中连接后可查看 SSH 状态、连接或断开。SSH “已连接”表示隧道建立；旁边的 Runtime
健康状态还会检查 API、token 与 supervisor，SSH 成功不代表 Runtime 已启动。
关闭“立即检查”可先保存配置；之后选中该连接或使用其操作时才尝试访问。

不勾选 SSH 时保持原有行为，可使用本机 Runtime 或用户在外部建立的隧道。

## CLI 使用

```bash
suan connect add cluster --ssh-host stk-cluster --url http://127.0.0.1:8765
# 按隐藏提示输入 Runtime token，也可加 --token-file /absolute/path/to/token.txt
suan connect check cluster
suan workspaces --profile cluster list
suan jobs --profile cluster list
```

每个 CLI 进程按需建立自己的隧道，退出时关闭。桌面桥在同一配置的多个操作之间复用隧道。
连接保存于私有 `~/.stk/connections.json`（可用 `STK_PROFILES_FILE` 覆盖）；其中保存远端 URL、
Host 和 token，临时本机端口不写入配置。连接列表和桥响应不返回 token。

## 断线与寿命

- SSH 子进程退出后，下一次操作会尝试重建隧道；启动失败短暂退避，避免轮询不断创建进程。
- 手动“断开 SSH”会禁止本桥会话中的自动重连，直到显式“连接 SSH”。重启桌面桥后重新按需连接。
- 不自动重发已经开始的 HTTP 请求。若提交响应丢失，先核对任务，复用原幂等键处理重试。
- Runtime 作业独立运行；断开隧道、关闭桌面、删除本机连接配置均不取消服务器任务。
- 桌面桥退出或崩溃导致父管道关闭时，独立守护进程清理它拥有的 SSH/跳板子进程。
- 已开始的本机图求值使用启动时的端点；隧道重建后，该次求值可能失败，需重新执行分析。

启动最长等待约 15 秒。程序等待 OpenSSH 的认证/转发初始化标记和回环监听，再发布端点，
避免把其他程序抢占的端口误认为自己的隧道；无法识别初始化标记时按启动失败处理。
该标记对应 OpenSSH 的 [client_loop](https://github.com/openssh/openssh-portable/blob/master/clientloop.c)。
当前 Linux 已通过临时本机 sshd、真实 Runtime 上传/执行/重连下载测试；Windows 模拟传输测试
及 macOS/Windows 原生客户端契约已纳入 CI，本批远端结果待跟踪。真实远程主机/跳板链仍需目标环境验收。
