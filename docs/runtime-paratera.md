# 并行云（Paratera）站点验收清单

并行云是 STK 的首个真实站点。**目前尚无账号，本页各项均未执行。** 下面的站点信息来自
2026-09 检索的公开资料（编号见文末“来源”），实际分配的超算中心可能不同；标注“待确认”的
内容需要并行云书面答复或实测。

## 已知情况

- 调度器：并行云手册要求用 Slurm 命令提交作业，公开资料未提到 PBS；本站点只用 STK 的
  Slurm 后端。[1][2]
- 并行云聚合多家超算中心。开通后有一个“并行账号”（门户登录）和每个中心一个“超算账号”
  （Linux 用户），可用的队列分区通过邮件告知。分区名、每节点核数、module 路径、存储布局
  乃至调度命令名都取决于账号所在中心，验收必须指定具体中心和分区。[1][2]
- 天河系列中心把 Slurm 命令改名为 `yhbatch`、`yhq`、`yhacct` 等，天河二号登录节点无外网。
  STK 只调用 `sbatch`、`squeue`、`sacct`、`scancel`、`sinfo`，在这类中心无法直接使用；
  是否同时提供标准命令名待确认。[5]
- 访问：无需 VPN，经桌面客户端（WebSSH 等）或 `papp_cloud` 命令行登录。`papp_cloud` 只有
  Linux 与 macOS 版本，登录需交互输入密码，令牌有效期 12 小时；手册未说明 `-L` 端口转发或
  用作 OpenSSH ProxyCommand（待确认）。[1][2]
- 登录节点只用于编译软件和拷贝数据。在登录节点运行程序会被管理员终止，两次警告后每次违规
  禁止登录一天。公开资料没有说明是否允许常驻的低负载用户进程。[1][3]
- 分区：示例都用 `-p` 指定分区，如 BSCC-A 的 `amd_256`（每节点 64 核）；`sinfo` 只显示账号
  可用的分区；BSCC 分区的默认时限为 `infinite`。公开示例没有使用 `-A` 或 `--qos`，是否必需
  待确认。[3]
- 计费：按核时计费。按节点计费的分区即使只申请部分核也按整节点收费，按核计费的分区加
  `--exclusive` 同样按整节点收费；BSCC 只对 R 状态计费；计费中心每天凌晨 3 点更新。[1][3][4]
- module：需先 `source /public1/soft/modules/module.sh`（或 `/public3/…`）；登录后加载的
  module 不会带进作业，要写在作业脚本中。BSCC 示例在 `module load mpi/intel/19.3.0` 后直接用
  `srun` 启动 Intel MPI 程序。实际中心的 oneAPI／Intel MPI 版本待确认。[3]
- 作业历史：BSCC 普通用户可以用 `sacct` 查询，保留期与 MinJobAge 未公开。[3]
- 存储：`/public1`、`/public3`（BSCC 系列）或 `/HOME/<用户>`（广州）；配额、清理策略、
  文件系统类型以及计算节点能否使用 flock 都未公开。[1][3]
- 作业脚本必须为 LF 换行，sbatch 拒绝 CRLF 脚本；Windows 上编写的脚本需先转换。[6]

## STK 现状

本轮已实现，均只经模拟的 Slurm 命令测试：

- MPI 布局 `ranks`／`threads_per_rank`，映射为 `--nodes --ntasks --ntasks-per-node
  --cpus-per-task`；MPI 任务默认每 rank 1 线程。见 [runtime 使用指南](runtime.md)。
- `config.json` 中的站点配置 `scheduler`：默认分区／账户／QOS、`/bin/bash`、module preamble、
  额外 sbatch 参数。
- `suan server doctor --backend slurm --partition … [--account …] [--qos …] [--probe-preamble]`
  的站点探针，不提交作业。
- sbatch 明确拒绝（无效分区／账户／QOS、违反账户或 QOS 策略等）时任务直接失败。
- MuPRO 启动、线程设置与逐次校验；`suan mupro submit` 的集群作业必须带 `--walltime`。
  见 [MuPRO 指南](runtime-mupro.md)。

尚未实现：

- `yh*` 命令映射，以及经 SSH 在远端提交的站点后端（下文方案 B）。
- 批量轮询：每个未结束的 Slurm 任务每 `scheduler_interval`（默认 10 秒）调用一次 `squeue`，
  不在队列时再调用一次 `sacct`。
- 按作业名取消状态为 `unknown` 的提交；计算节点 flock 不可用时的明确诊断（worker 取锁失败
  直接退出，不写 `finished.json`）；上传 CRLF 脚本的检查。
- 站点级强制时限：`suan jobs submit --spec` 的任务需要自己写 `walltime_seconds`，
  `examples/runtime/run_demo.py` 不设时限。
- 本机并发按任务计数，不按 rank × 线程计数。
- 按站点禁止本机后端任务（例如在 `config.json` 中只允许 `slurm`）。方案 A 目前只能靠每次
  提交都带 `--backend slurm`。
- `suan-node` 从本机 runtime 的 `config.json` 读取端口和令牌，目前只能与 runtime 同机运行。

## 部署方案

STK 没有远端提交路径：调度命令作为本地子进程运行，supervisor 从本地任务目录读取
`finished.json`，同一个 `python` 配置既用于 runtime 主机也用于计算节点。因此 runtime 必须运行在
能直接调用 Slurm 命令、并挂载共享文件系统的主机上。

- 方案 A：runtime 常驻并行云登录节点，使用本地 sbatch 与共享文件系统，STK 基本可以直接使用。
  风险：登录节点禁止运行程序，常驻进程需要书面许可；本机后端任务会直接在登录节点上运行程序，
  而本机后端是 `suan mupro submit`、`suan jobs submit` 的默认值，也是不写 `backend` 的 `--spec`
  与模板的默认值，漏写一次 `--backend slurm` 就会违反站点规定；有多个登录节点时 PID 与 SQLite
  只在一台上有效；SQLite 需要本地磁盘；可能没有 systemd `--user` 与 linger，维护后需手动重启；
  客户端需要 `ssh -L`；登录节点上的其他用户也能访问回环端口，只靠令牌保护。
- 方案 B：runtime 运行在用户自己的 Linux 服务器上，经 SSH 在登录节点提交。需要新写远端站点
  后端（远端暂存、批量轮询、读取远端 `finished.json`、拉取结果、独立的远端 Python 配置）；
  无人值守认证目前受 `papp_cloud` 交互密码与 12 小时令牌限制；凭据须为 0600 权限且不入仓库。
- 方案 C：把 runtime 放在长时间运行的 Slurm 作业中。持续计费且受时限约束，不推荐。

无论哪种方案，控制服务、节点代理和可视化都不放在登录节点：节点代理的 `view.build`／
`view.probe` 会在本机加载最多 1 GiB 的场数据，本机后端也会在 runtime 主机上直接运行程序。
建议：只有取得并行云书面许可、登录节点固定且有本地磁盘时，首次验收才采用方案 A，并通过
SSH 隧道与 `suan connect` 使用 CLI；若并行云提供非交互 SSH，把方案 B 作为长期目标。

## 待确认的问题

需要用户决定或提供：

1. 账号绑定哪个超算中心（中心简称）和哪些分区？
2. 该中心是标准 Slurm（哪个版本），还是天河 `yh*` 命令？
3. 是否允许在登录节点常驻 STK runtime（绑定 127.0.0.1 的 HTTP API，加上每 10–60 秒调用
   `squeue`／`sacct` 的 supervisor）？需要并行云书面答复，并据此在方案 A 与 B 之间选择；
   若选 B，由哪台主机运行（开发服务器可从外部访问，凭据须为 0600 且不入仓库）？
4. MuPRO Release 许可如何在计算节点使用？`machine.lic` 绑定单台机器，而每个节点的每个 rank
   都会检查许可，需要 MuPRO 维护方给出方案，并确定在并行云使用哪个构建和许可目录。

需要并行云书面答复：

- 每个分区的每节点核数与内存、按节点还是按核计费、价格、默认与最大时限、每用户提交／运行
  作业上限（QOS）。
- 是否支持 `sbatch --parsable`、`sbatch --test-only`、`squeue --me` 与 sacct 的 `JobIDRaw`；
  是否必须 `-A`／`--qos`；按节点计费的分区是否接受 `--mem`。
- 普通用户能否查询 sacct 历史，保留期与 MinJobAge。
- 登录节点有无自动清理进程、cgroup CPU 时间或空闲限制；`nohup`／`setsid`／`tmux` 进程在登出后
  是否保留；是否提供 systemd `--user` 与 linger。
- 登录节点数量、网关是否总是落到同一台；有无允许常驻服务的数据传输或服务节点；可用于
  SQLite 的本地非网络磁盘路径及其清理策略。
- 共享文件系统的路径与类型、字节与 inode 配额、清理策略；登录节点和计算节点是否支持 flock。
- 能否从固定 IP 用 OpenSSH 公钥非交互登录；`papp_cloud` 是否支持 `-L` 或用作 ProxyCommand；
  有无更长期的服务令牌或作业／文件 API。
- 登录节点与计算节点是否允许出站 HTTPS／WSS。
- 已安装的 oneAPI／Intel MPI 版本与推荐的启动方式（srun 用哪种 `--mpi` 插件或
  `I_MPI_PMI_LIBRARY`，还是 mpirun／Hydra）；能否在站点编译 MuPRO（Intel 编译器、MKL、
  CMake）；计算节点的操作系统与 glibc 版本。
- 验收可用的预算或试用额度（公开资料提到 2000 核时或 200 元）；有无适合 1 核演练的按核计费分区。[4]

## 验收清单

每项记录命令、输出摘录或校验值，以及通过与否。E 项每个作业不超过 1 核、5 分钟；F 项的规模
见该项。优先用按核计费的分区演练，避免按整节点收费。

### A. 账号与中心

- 并行账号与超算账号已绑定；记录 `papp_cloud acct` 与 `papp_cloud lsc` 的输出（中心简称）。
- 登录主机名、`cat /etc/os-release`、`ldd --version`。
- 并行云对上面问题的书面答复。

### B. 只读调度探针（登录节点）

```bash
which sbatch squeue sacct scancel sinfo    # 天河系列中心改查 yh* 命令
scontrol show config | grep -E 'SLURM_VERSION|MinJobAge|MpiDefault|MessageTimeout'
sinfo -h -o '%P|%a|%l|%D|%c|%m'
suan server --state-dir LOCAL_STATE doctor --backend slurm --partition PARTITION \
  --account ACCOUNT --qos QOS --json > doctor.json    # 无需账户或 QOS 时省略这两项
```

doctor 需要已由 D 项 `init` 的 state 目录；API 尚未启动时 `api` 检查失败，不影响下列检查。
Slurm 相关检查项为 `scheduler_profile`、`scheduler_commands`、`slurm_version`、
`slurm_partition`、`slurm_submit_test`、`slurm_accounting`、`compute_nodes`，配置了 preamble
时还有 `scheduler_preamble`。`slurm_submit_test` 只运行 `sbatch --test-only`，不提交作业[7]，
可据此判断是否必须 `--account` 或 `--qos`；`slurm_accounting` 为警告表示 sacct 历史不可用，
supervisor 重启后的核对能力下降。`sinfo` 不在必需命令中，缺失时 `slurm_partition` 报告无法运行。
同时记录各分区按节点还是按核计费。

### C. 环境

- module 初始化路径（`source /public?/soft/modules/module.sh`）与 `module avail intel mpi anaconda`。
- 共享文件系统上的 Python 3.10–3.14 环境，安装 `psutil` 与 STK `.[server,science]`，计算节点能运行它。
- `df -hT` 查看家目录、`/public*` 与候选 state 目录，记录文件系统类型与配额。为 SQLite 选择本地
  非网络磁盘并了解其清理策略；doctor 的 `state_filesystem` 在 lustre、gpfs、nfs 等上报告失败。
- 计算节点上的共享目录可见性与 flock，由 E 项确认 worker 能写 `finished.json`。

### D. STK 配置

```bash
suan server --state-dir LOCAL_STATE init --workspace-root SHARED/stk-workspaces --port FIXED_PORT
```

- 端口使用固定、未被占用的非默认端口（先用 `ss -ltn` 检查），不要用 `--port 0`：常驻 runtime、
  SSH 隧道、已保存的连接和 `suan-node` 都依赖固定端口。`config.json` 保持 0600 权限。
- 停止服务后在 `config.json` 加入站点配置：`queue` 为分配的分区，`job_shell` 为 `/bin/bash`，
  `preamble` 为 module 初始化、Intel MPI 模块和 MuPRO 变量的 `export`，按需加 `account`、`qos`。
  站点示例作业头中的 `#SBATCH` 参数不能写进 `preamble`，需要时写到 `submit_args`。
  示例见 [MuPRO 指南](runtime-mupro.md)，规则见 [runtime 使用指南](runtime.md)。
- 可把 `scheduler_interval` 调大（如 30 秒），减少对共享调度器的查询。
- 取得常驻许可后才 `suan server --state-dir LOCAL_STATE start`；再运行 B 项的 doctor 并加
  `--probe-preamble`，报告应为 `ok`。
- 每个作业都设置时限：`suan mupro submit` 的集群作业必须带 `--walltime`；`--spec` 任务写
  `walltime_seconds`；`run_demo.py` 不设时限，演练时需要盯住并在超时后手动取消。
- 采用方案 A 时，所有提交都带 `--backend slurm`（`--spec` 与模板写 `"backend": "slurm"`），
  不使用本机后端，否则程序直接在登录节点上运行。
- 采用方案 A 时，记录 runtime 1 小时内的 CPU 占用与 RSS，交给并行云确认。

### E. 通用 Slurm 演练

- `python examples/runtime/run_demo.py --profile paratera --backend slurm --queue PARTITION
  --output ./stk-slurm` 报告 `verified=true`。
- 排队中取消和运行中取消都以 `cancelled` 结束，`sacct` 显示 CANCELLED。
- `walltime_seconds` 为 60 的 `sleep 300` 任务以失败（TIMEOUT）结束。
- 运行中重启 supervisor，任务按 `finished.json` 核对；停止 supervisor 超过 MinJobAge 后再启动，
  任务按 sacct 核对。
- 不确定提交：在 supervisor 的 PATH 前放一个先调用真实 sbatch、再等待超过 20 秒（STK 的提交
  超时）的包装脚本。任务应先为 `unknown`，再按作业名核对，不重复提交。
- 无效分区的提交立即失败，而不是 `unknown`。
- 计算节点上的 worker 能写 `finished.json`（共享目录可见、flock 可用）。

### F. MuPRO

- 在站点重新编译 MuPRO。开发服务器上构建的 muFerro 需要 GLIBC 2.34 与 GLIBCXX 3.4.32，
  RUNPATH 固定为 `/opt/intel/oneapi/mpi/2021.18/lib`，并需要 Intel 编译器运行库，不能直接拷到
  常见的 CentOS／Rocky 集群；用站点的 Intel 工具链编译，或基于较旧的 sysroot 构建。
- 许可：见“待确认的问题”第 4 项，未解决前不运行 Release 构建。
- 把 `python -m suan.mupro check --json` 作为计算节点任务运行，从日志读取结果：

  ```json
  {"workspace_id": "WORKSPACE_ID", "argv": ["{python}", "-m", "suan.mupro", "check", "--json"],
   "backend": "slurm", "resources": {"walltime_seconds": 300, "queue": "PARTITION"}}
  ```

  ```bash
  suan jobs --profile paratera submit --spec check.json
  suan jobs --profile paratera logs TASK_ID
  ```

- 1 节点 × 4 rank，分别用默认的 mpiexec 和 `--launcher srun`（需要站点的 `I_MPI_PMI_LIBRARY`）：

  ```bash
  suan mupro submit --profile paratera --workspace WORKSPACE_ID --case-dir case16 \
    --backend slurm --queue PARTITION --ranks 4 --walltime 600 --env-script /shared/path/mupro-env.sh
  ```

  在环境脚本中加入 `export I_MPI_DEBUG=4` 以查看进程放置与绑核（`--env-script` 会取代
  `STK_MUPRO_ENV_SCRIPTS`，需列出全部脚本）。比较两种方式的墙钟时间，确认 `environment.json`
  与 `stk-mupro.json` 中 OMP、MKL 均为 1。再扩展到整节点和 2 个整节点；rank 数不能超过
  min(nx, ny)，16³ 的示例最多 16 rank，整节点需要更大的案例，并注意按节点计费。
- 结果只与相同 rank 数的运行比较（启用噪声时结果随 rank 数变化）。
- 下载 DAT 场帧，记录传输速度；每次全场输出约为每网格点 1.9 KB（1944 字节，见 [MuPRO 指南](runtime-mupro.md)）。

### G. 费用与运维

- 次日凌晨 3 点后，在计费中心对比核时与预期（按节点计费的分区按整节点收费；只有 R 状态计费）。
- 记录登录节点维护后的手动重启步骤。
- 令牌文件为 0600；令牌不出现在日志、`job.sh` 或作业环境中。sbatch 默认把提交环境带进作业，
  启动 runtime 的 shell 中不要设置 `STK_RUNTIME_TOKEN`。
- 从 Linux（`papp_cloud` 或 OpenSSH）和 Windows（桌面客户端，或经允许的 OpenSSH）测试客户端隧道。

## 来源

1. 《并行®超算云服务 简明使用手册（2022 夏季版）》第 3、8、16、20 页；第三方镜像：
   https://git.opencomputing.cn/yumoqing/kboss/raw/commit/0d73cba8bfb9e066a48a9d7f1208346c16eff83d/docs/%E8%9E%8D%E5%90%88%E4%BA%91%E8%B5%84%E6%96%99/%E5%B9%B6%E8%A1%8C%E8%B6%85%E7%AE%97%E4%BA%91%E6%9C%8D%E5%8A%A1%E7%AE%80%E6%98%8E%E4%BD%BF%E7%94%A8%E6%89%8B%E5%86%8C-2022%E5%A4%8F%E5%AD%A3%E7%89%88.pdf
2. papp_cloud 使用手册 v4.1.0（2026-03-27 更新）：https://papp-cloud.paratera.com/
3. 北京超级云计算中心《超算云 Q&A》（2023-05-16）第 3–14 页：
   https://hpc.xatu.edu.cn/__local/D/ED/44/7F1999A5ECF872EE333BEF83B43_1395FA68_196194.pdf
4. 并行科技平台与算力说明：https://www.paratera.com/Platform.html 、https://www.paratera.com/power.html
5. 天河系统的 `yh*` 命令与网络限制：https://molakirlee.github.io/2020/08/31/slurm_tianhe2/ 、
   https://itlanyan.com/tianhe-ii-guide/
6. 作业脚本换行：https://doc.geovbox.com/latest/clac/index.html 、
   https://www.cnblogs.com/AIteaser/p/15218683.html
7. Slurm sbatch 手册（`--test-only`）：https://slurm.schedmd.com/sbatch.html

并行云官方详细手册 https://handbook.stg.paratera.com/ 需要登录，未能读取。
