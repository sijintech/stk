# STK Runtime 运行 MuPRO

STK Runtime 负责 MuPRO 作业的排队、提交、取消与恢复。MuPRO 以原生程序方式调用：
当前面向 muFerro，由计算节点上的 `python -m suan.mupro run` 启动并逐次校验。
STK 不导入 muprosdk，也不使用 muprosdk 的运行服务或 `mupro run` 适配器。
逐次校验器 `stk-mupro-1` 对照 muprosdk `tools/mupro/mupro/worker.py` 的结果检查实现；
`mupro-verify` 是 MuPRO 仓库／构建树的证据工具，不用于检查单次运行。

Runtime、控制服务与节点代理只在 Linux 运行；客户端命令 `suan mupro submit/result/verify`
可在任何系统使用，连接方式见 [runtime 使用指南](runtime.md)。

## 节点环境

以下变量放在 Runtime 服务环境中，由 worker 继承；不要写进 TaskSpec 的 `env`（其中
`STK_MUPRO_ALLOW_LOCAL_MPI` 与调度器变量 `SLURM_JOB_ID`、`PBS_JOBID` 在 `env` 中会被拒绝；
升级前已排队、`env` 中含这些变量的任务在分派前失败，需去掉后重新提交）：

| 变量 | 用途 |
|---|---|
| `MUPRO_SDK_PREFIX` | SDK 安装前缀，含 `bin/muFerro` 与 `share/mupro/skills/mupro-muferro/examples/`；与 muprosdk 客户端同名 |
| `MUPROROOT` | 许可目录路径，最多 256 字节。STK 只传递路径，不读取、打印或复制其中文件 |
| `STK_MUPRO_ENV_SCRIPTS` | 启动前依次 source 的 bash 脚本，以 `:` 分隔，例如 oneAPI 的 `mpi/latest/env/vars.sh` 与编译器运行库脚本 |
| `STK_MUPRO_ALLOW_LOCAL_MPI` | 设为 `1` 时允许在 Slurm／PBS 分配之外运行 mpiexec，见“本机多 rank 保护” |

任务参数优先：`--sdk-prefix` 优先于 `MUPRO_SDK_PREFIX`（source 脚本后读取），
`--env-script` 取代 `STK_MUPRO_ENV_SCRIPTS`，`--license-dir` 取代 `MUPROROOT`。
这些参数写入 argv，指计算节点上的路径。

设计阶段检查的 linux-intel-release 安装中，Release 版 muFerro 需要 Intel MPI（程序
RUNPATH 指向 oneAPI MPI 2021.18 的 lib，`mpiexec` 来自 `vars.sh`）和 Intel 编译器运行库
（libiomp5、libimf、libirng）；MKL 为静态链接。对应的环境脚本示例（路径以实际安装为准）：

```bash
# mupro-env.sh
. /opt/intel/oneapi/mpi/latest/env/vars.sh
export LD_LIBRARY_PATH=/opt/intel/oneapi/compiler/2025.3/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
```

环境脚本由 bash 依次 source（不带参数），输出被丢弃，合计最多 120 秒。脚本必须正常返回，不能调用
`exit`：调用 `exit` 会被拒绝（`A MuPRO environment script called exit instead of returning`），
返回非零同样按配置错误处理，错误信息给出该脚本和返回值（`MuPRO environment script … returned N`）。
oneAPI 的 `setvars.sh` 在继承了 `SETVARS_COMPLETED=1` 时（例如 Runtime 或 sbatch 的环境来自已
source 过它的登录 shell）不再执行并返回 3。`STK_MUPRO_ENV_SCRIPTS` 与 `--env-script` 无法传入
`--force`，因此请使用上例中各组件的 `env/vars.sh`，或写一个包装脚本执行
`. /opt/intel/oneapi/setvars.sh --force`。

使用 systemd 时，把 [stk-mupro.env.example](../deploy/systemd/stk-mupro.env.example) 复制为
`~/.config/stk/mupro.env`（权限 600），在 `stk-supervisor.service` 中取消 `EnvironmentFile`
一行的注释并重启服务。用 `suan server start` 启动时，这些变量取自执行该命令的 shell；
`start` 不会重启已在运行的 supervisor，修改变量后先 `suan server stop --supervisor`，再从
导出了新变量的 shell 执行 `suan server start`。已在运行的 worker 保留原来的环境。
Slurm 作业默认带上提交时的环境（sbatch 默认 `--export=ALL`，站点可另行设置）；PBS 默认
不带，需在站点配置的 `preamble` 中 `export` 或 source。并行云等使用 module 的站点也可用
`preamble` 代替环境脚本：

```json
"scheduler": {
  "job_shell": "/bin/bash",
  "preamble": ["source /public1/soft/modules/module.sh", "module load mpi/intel/VERSION",
               "export MUPRO_SDK_PREFIX=/shared/path/mupro/sdk"]
}
```

站点配置的规则见 [runtime 使用指南](runtime.md) 的“站点配置（scheduler）”。

## 提交与查看

```bash
# 上传本地案例目录（含 input.toml、material.toml），用本机后端在 Runtime 主机上运行 1 rank
suan mupro submit --profile dev --workspace WORKSPACE_ID --input ./case16 --wait
# 在 Runtime 主机上运行 SDK 自带的示例（同样是本机后端）
suan mupro submit --profile dev --workspace WORKSPACE_ID --example
# 已上传的案例经 Slurm 以 1 节点 4 rank 运行；集群作业必须给出 --walltime（秒）
suan mupro submit --profile cluster --workspace WORKSPACE_ID --case-dir case16 \
  --backend slurm --queue PARTITION --ranks 4 --walltime 1800
suan mupro result --profile cluster TASK_ID
# 检查本地的运行目录，例如下载后的 work 目录
suan mupro verify ./work --case-dir case16
```

- 本机后端（`--backend` 的默认值）在 Runtime 所在主机上直接运行 muFerro。Runtime 部署在
  集群登录节点时（[并行云站点验收清单](runtime-paratera.md) 的方案 A），每次提交都必须带
  `--backend slurm`，不要使用本机后端。
- `--input DIR`、`--case-dir REL`、`--example` 三选一。`--input` 把目录下所有文件上传到
  工作区的同名目录（或 `--remote-dir`）；`--case-dir` 使用工作区中已上传的文件。
- `--input` 必须是干净的案例目录。muFerro 会在已有的 `energy_out.dat` 与
  `mupro_progress.jsonl` 之后追加，在同一目录重跑会在用完机时后才校验失败；因此目录中已有
  `energy_out.dat`、`mupro_progress.jsonl`、`mupro_completion.json` 或场帧时，客户端在上传前
  拒绝，计算节点在启动前同样拒绝（退出码 2）。重启输入 `Polar.in` 不受影响。
- `--ranks` 是全部 rank 数，`--threads-per-rank` 与 `--nodes` 默认 1。客户端在连接 Runtime
  之前先检查布局：本机后端只能 1 个节点，PBS／Slurm 必须有 `--walltime`（集群按核时计费），
  rank 数必须是节点数的整数倍。`--input` 时客户端还按计算节点的规则读取 `input.toml`（含
  include），检查 rank 数不超过 min(nx, ny)；`--case-dir` 与 `--example` 的案例在 Runtime
  上，只在计算节点检查。
- 提交前把幂等键打印到 stderr；响应丢失后用同一个 `--key` 重试。`--wait` 等待任务结束，
  未成功时退出码为 1。Runtime 的 `/health` 不含 `ranks` 时拒绝提交，需要升级服务端。
- 生成的 TaskSpec：argv 为 `{python} -m suan.mupro run --ranks {ranks} --threads-per-rank
  {threads_per_rank}` 加上案例与节点参数，`outputs` 为 `["stk-mupro.json"]`，`env` 为空，
  `resources` 含 `ranks`、`threads_per_rank` 以及给出的 `nodes`、`walltime_seconds`、
  `memory_mb`、`queue`、`account`。Python 客户端可用 `suan.mupro.muferro_spec(...)` 生成。
- `suan mupro result TASK_ID` 下载并打印已结束任务的 `stk-mupro.json`，`--output` 另存；
  校验通过时退出码 0，否则 3。Runtime 在任务结束后才列出结果文件。
- `suan mupro verify RUN_DIR [--case-dir REL]` 只做本地校验，退出码同上。

## 计算节点命令

```bash
python -m suan.mupro run [--program muFerro] [--case-dir .] [--example] [--ranks 1] \
  [--threads-per-rank 1] [--launcher auto|none|mpiexec|srun] [--sdk-prefix DIR] \
  [--env-script FILE] [--license-dir DIR]
python -m suan.mupro verify [--work .] [--case-dir .] [--json]
python -m suan.mupro check [--sdk-prefix DIR] [--program muFerro] [--env-script FILE] \
  [--license-dir DIR] [--json]
```

`run` 在任务的 `work` 目录中执行：

1. source 环境脚本；有 `--license-dir` 时设置 `MUPROROOT`，超过 256 字节即拒绝。
2. `--example` 从 SDK 复制 `input.toml`、`material.toml` 到案例目录；目录中已有
   `input.toml` 时拒绝覆盖。
3. 读取 `input.toml`，按 MuPRO 的规则合并 `include`：一个路径或路径列表，相对写出它的文件；
   本文件优先，先列出的优先，子表逐键合并，最多嵌套 16 层。被包含的文件必须在任务 `work`
   目录内，缺失、循环或越界都按配置错误处理；案例目录之外的文件须列入任务输入
   （`suan mupro submit` 只上传或选取案例目录中的文件）。合并后：
   `[system].simulation_grid` 为三个正整数；`timestep_start` 默认 0，`timestep_total` 默认
   1000，与 muFerro 相同；`[output].interval` 必填；起始步与总步数之和不超过 999999。
4. rank 数不超过 min(nx, ny)（MuPRO 按 x／y 分块）；案例目录中已有 muFerro 输出时拒绝，
   见上文 `--input` 的说明。
5. 设置 `OMP_NUM_THREADS` 与 `MKL_NUM_THREADS` 为每 rank 线程数。
6. `--program` 为路径时直接使用，否则依次查找 `<SDK>/bin/<program>` 和 PATH。
7. 选择启动器，写入 `state` 为 `running` 的 `stk-mupro.json`，在案例目录运行 muFerro；
   结束后校验并写入最终结果。

`check` 检查本节点：`env_scripts`、`sdk_prefix`、`program`、`shared_libraries`（ldd 找不到的库）、
`mpi_launcher`（PATH 上的 mpiexec）、`license_dir`（只确认是目录，不读内容）和
`example_case`。没有 `fail` 时退出码 0，否则 1。要看到计算节点的实际环境，应把它作为任务
提交，见 [并行云站点验收清单](runtime-paratera.md)。`verify` 只做下文的校验，通过时退出码 0，
否则 3。

## 进程布局、线程与启动器

- rank 数 R 与每 rank 线程数 T 作为 TaskSpec 的 MPI 资源提交，Runtime 把它们映射为 Slurm／PBS
  参数（见 [runtime 使用指南](runtime.md)），argv 中的 `{ranks}`、`{threads_per_rank}` 由 worker 替换。
- 启动器始终设置 `OMP_NUM_THREADS = MKL_NUM_THREADS = T`（默认 1），避免每个 rank 按整节点
  核数开线程造成严重超额占用。
- `auto`（默认）：1 rank 直接运行程序（MPI singleton，不打开 PMI 监听）；多 rank 使用 mpiexec，
  在 Slurm／PBS 分配内也用 mpiexec，由 Intel MPI 的 Hydra 识别分配。
- `none`：只允许 1 rank。
- `mpiexec`：使用 source 环境脚本后 PATH 上的 mpiexec，命令为 `mpiexec -n R muFerro`。
- `srun`：必须显式指定 `--launcher srun`，并且只能在 Slurm 分配内（有 `SLURM_JOB_ID`）使用；
  否则按配置错误拒绝，避免在分配外另起一个单独计费的作业。命令为
  `srun --ntasks=R --cpus-per-task=T muFerro`，并设置 `SRUN_CPUS_PER_TASK=T`。Intel MPI 经
  srun 启动还需要站点提供的 `I_MPI_PMI_LIBRARY`，可在环境脚本中设置。

## 本机多 rank 保护

在 Slurm／PBS 分配之外（既没有 `SLURM_JOB_ID` 也没有 `PBS_JOBID`）使用 mpiexec 时，除非
Runtime 服务环境设置了 `STK_MUPRO_ALLOW_LOCAL_MPI=1`，任务会以配置错误失败（退出码 2），
不启动任何命令。这包括 `auto` 的多 rank 运行，以及显式 `--launcher mpiexec`（即使只有 1 rank）。

原因：Intel MPI 的 Hydra（`hydra_pmi_proxy` 及继承其套接字的各 rank）在作业运行期间监听
`0.0.0.0` 上的随机端口。设计阶段的试验中，设置 `I_MPI_HYDRA_IFACE=lo`、
`I_MPI_HYDRA_BOOTSTRAP=fork` 或 `I_MPI_FABRICS=shm` 都没有改变这一点；1 rank 直接运行不打开
监听。在可从外部访问的主机上（绑定局域网地址并不等于隔离），这意味着作业期间有一个端口对外
开放；`I_MPI_PORT_RANGE` 只能把端口限制在防火墙规则可覆盖的范围。只在外部网络无法访问或已有
防火墙的主机上设置该变量，而且只放在 Runtime 服务环境中。

这项检查防止误在本机运行多 rank，不是访问控制。TaskSpec 的 `env` 不能设置这三个变量
（提交时返回 400），worker 也会恢复服务环境中的值；但任务选择的 `--env-script` 在检查之前
source，而且持有 Runtime 令牌的客户端本来就能运行任意命令。真正的控制是 Runtime 令牌、
只绑定回环地址和主机防火墙。

## 许可

- Release 构建在每个 rank 上检查许可，读取 `MUPROROOT` 下的文件；未设置时 MuPRO 回退到
  当前目录的 `./key`，`check` 会给出警告。
- MuPRO 用 256 字符的字段保存 `MUPROROOT`，更长的路径会被截断，因此 STK 拒绝超过 256 字节的路径。
- STK 只传路径（`--license-dir` 或继承的 `MUPROROOT`），不读取、打印或复制许可文件；
  `stk-mupro.json` 只记录路径。muFerro 自己的标准输出会列出许可文件路径，但不含内容。
- `machine.lic` 绑定单台机器。集群上每个节点的每个 rank 都会检查许可，在并行云等集群运行
  Release 构建之前，需要 MuPRO 维护方给出集群许可方案（待确认）。
- 许可无效时 muFerro 在 stderr 报 `invalid license` 并以非零码退出，STK 分类为 `solver_failed`。

## stk-mupro.json

启动器在 `work` 目录根部原子写入 `stk-mupro.json`（`schema_version` 为 1）：开始时 `state` 为
`running`，结束时写入最终结果。

| 字段 | 内容 |
|---|---|
| `app`、`state` | `muFerro`；`running`、`succeeded` 或 `failed` |
| `classification`、`reason` | 失败分类与原因；成功时为 `null` 与空串 |
| `case_dir`、`case` | 案例目录；`grid`、`start_step`、`steps`、`output_interval` |
| `layout` | `ranks`、`threads_per_rank`、实际 `launcher`（`none`、`mpiexec` 或 `srun`） |
| `command`、`program` | 实际命令；程序路径与 SHA-256 |
| `sdk_prefix`、`env_scripts` | 使用的 SDK 前缀与环境脚本路径 |
| `environment` | 仅 `OMP_NUM_THREADS`、`MKL_NUM_THREADS`、`MUPROROOT`（路径）、`SRUN_CPUS_PER_TASK` |
| `exit_code`、`started_at`、`finished_at` | 求解器退出码（未运行时为 `null`）与起止时间 |
| `verification` | `verifier`（`stk-mupro-1`）、`status`（`passed`、`failed`、`not_run`）、逐项 `checks` |
| `qoi` | 校验通过时为最终 `total_energy` 与 `step`，否则为 `null` |
| `frames` | 每个场帧的 `stem`、`step`、`components`、`path`（相对 `work`），按场名和步号排序 |

失败分类：`configuration`（配置、案例或环境错误）、`launch_failed`（命令无法启动）、
`solver_failed`（求解器非零退出）、`incomplete_result`、`numerical_failure`、`invalid_result`。

`run` 的退出码：0 表示求解器正常结束且校验通过；2 表示配置或启动失败，求解器没有运行；
3 表示求解器运行后失败或未通过校验。非零退出码使 Runtime 任务为 `failed`，但
`stk-mupro.json` 仍可下载。

求解器退出码 0 不等于成功：能量出现 NaN 时 muFerro 正常退出（退出码 0），但不写
`mupro_completion.json`，能量记录也不完整。STK 因此判为失败，分类为 `invalid_result`
（完成记录检查最先失败），`run` 退出码为 3。

Runtime 取消任务时会终止启动器，`stk-mupro.json` 可能停留在 `running`；以 Runtime 的
任务状态为准。

## 校验（stk-mupro-1）

校验规则与分类对照 muprosdk `tools/mupro/mupro/worker.py` 的结果收集，所有检查都执行，
按其顺序以第一个失败项分类：

- `completion`：`mupro_completion.json` 必须恰为 `{"app": "muFerro", "completed_steps": 步数,
  "final_step": 起始步 + 步数}`；缺失或无法读取为 `invalid_result`，内容不符为 `incomplete_result`。
- `energy`：`energy_out.dat` 表头之后每步一行 `kt: … energy: …`，步号从起始步 + 1 连续到最后
  一步，每行 5 个有限值（接受 Fortran `D` 指数）；值个数不对或非有限为 `numerical_failure`，
  步号缺失、重复或过期为 `incomplete_result`。
- `progress`：`mupro_progress.jsonl` 每步一条记录，与请求的案例一致。
- `frames`：所需场帧齐全，首行头部的网格等于案例网格，分量数正确。只读首行，不解析场值。

## 输出与结果解读

- 场帧文件名为 `<Stem>.<8位步号>.dat`，场名截断为 8 个字符（如 `Eigen_St`、`Elast_St`）。
  Polar 在起始后每个输出间隔写一次，另有初始帧 `Polar.00000000.dat`；其余 14 个场
  （Charges、Displace、Eigen_St、Elas_For、Elast_En、Elast_St、Elec_For、Elec_Phi、Elect_En、
  Elefield、LandPFor、LandP_En、Strain、Stress）在 (步号 − 起始步) 除以间隔余 1 的步写出。
  SDK 示例（16³ 网格、101 步、间隔 100）共 30 个场帧。
- 输出量：muFerro 只能用 `[output].interval` 控制输出，不能按场选择。每个数值占 42 字节
  （标量 36 字节）。本机验收实测 SDK 示例（16³）：一次全场输出为每网格点约 1.9 KB（1944 字节，
  其中 Polar 以外的 14 个场 1818 字节），每次运行约 16 MB（运行目录 15,968,953 字节）。
  按此推算 128³ 网格每次全场输出约 3.8 GiB（外推，未实测），应据此规划工作区配额。
- `Polar.00000000.dat` 是极化乘以 p0，后续 Polar 帧是归一化极化，二者不能直接比较。
- 案例启用噪声时，每个 rank 用相同种子为自己的 x 分块生成噪声，因此初始场和最终结果随 rank
  数变化。只在相同 rank 数下比较结果。
- 能量与场值单位未标注；场文件不带几何信息，工作台以从 0 开始的网格索引（`grid index`）
  作坐标：坐标 x 对应 DAT 行中的 i = x + 1（y、z 同理），切片索引同样从 0 开始。
- `energy_out.dat` 是能量时间序列，不是场；在工作台中选择它会报 `Not a regular-grid field DAT`。
  工作台中查看 MuPRO 帧的方法见 [Blender 工作台指南](../blender/README.md)。

## 运行中的进度与结果查看

在 STK Runtime 下（worker 设置了 `STK_MONITOR_PATH`），`python -m suan.mupro run` 是事件文件唯一的
写入者（[监控事件 v1](specs/stk-events-v1.md) §6 的适配模式）：它从 muFerro 的环境中去掉该变量，
启动求解器前写 `run.started {app: "muFerro", total_steps, ranks, host, pid}`，运行期间由一个线程每
2 秒检查一次案例目录：

| muFerro 原生输出 | 事件 |
|---|---|
| `mupro_progress.jsonl` 新增的完整行 | `progress {step, completed_steps, total_steps, fraction}`：每次检查取最新一行，最多每秒写一次，最后一次总会写出 |
| `energy_out.dat` 表头 | `metric.declare` 五个：`elastic_energy`、`electric_energy`、`landau_energy`、`gradient_energy`、`total_energy`，单位 `normalized`，标签取自表头 |
| `energy_out.dat` 的 `kt: N energy: …` 行 | `metrics {step: N, values}`；非有限值写成 `"NaN"`／`"Inf"`／`"-Inf"`，另写 `message {warning, code: "nonfinite_energy"}` |
| `<Stem>.<8位步号>.dat` | 大小与修改时间在连续两次检查中不变且进度已到该步，或求解器以 0 退出后：`frame {dataset, step, path, reader: "mupro.dat@1", components, size}`，`path` 相对 `work`；求解器非零退出时只发布不晚于最后进度步的帧 |
| `mupro_completion.json` 出现 | `message {info, code: "native_completion"}` |
| 求解器退出、`stk-mupro-1` 校验后 | `verification {verifier, status, failed_checks}`（`stk-mupro.json` 中校验为 `not_run` 时写 `skipped`；求解器未启动时不写）与 `run.completed {status, classification, reason}` |

格式不对的进度或能量行记为 `message {warning}`（`malformed_progress`、`malformed_energy_row`），每种
最多 5 条，之后只提示一次已省略。适配器的错误只写到 stderr：有无监控，`run` 的退出码和
`stk-mupro.json` 都相同；不在 Runtime 下运行时不写事件。

查看运行中的任务：

- `suan jobs --profile cluster show TASK_ID`：任务记录中的 `monitor.last_progress` 为最近的进度。
- `GET /v1/tasks/{id}/events`、`RuntimeClient.events`、MCP `get_task_events`、控制服务操作
  `task.events`：逐条读取进度、能量指标和帧事件，见 [runtime 使用指南](runtime.md#监控事件)。
- 网页“图谱”模式在绑定的任务运行时显示进度行，并在有比已算结果更新的帧时提示。
- 进度不等于成功：以 Runtime 任务状态和 `stk-mupro.json` 的 `verification.status` 为准。

任务结束后用节点图查看结果（[可视化指南](visualization.md)）。Runtime 在任务结束后才列出结果文件，
所以任务绑定只能用于已结束的任务。`muferro-domains` 预设把 Polar 分为 26 个立方取向变体，画出
各变体的平滑曲面、图例、外框与坐标轴，并给出变体分数与能量曲线；`energy-plot` 只画五项能量。

```bash
# 经已保存的连接直接绑定任务（--example 与 --input 提交的任务都可以）
suan graph run muferro-domains --connection cluster --bind run=task:TASK_ID --out ./domains
# 或在 Runtime 主机上绑定任务的 work 目录
R=/shared/user/stk-workspaces/WORKSPACE_ID/runs/TASK_ID
suan graph run muferro-domains --bind run="$R/work" --out ./domains --param step=all
suan graph run energy-plot --bind run="$R/work" --out ./energy
```

- `stk.source.muferro_run@1` 的 `case_dir` 默认为 `auto`：读取绑定根目录下 `stk-mupro.json` 记录的
  案例目录（`--input case16` 时为 `case16`），没有记录或路径不安全时为 `.`。因此预设与网页“图谱”
  模式对 `--example` 与 `--input` 提交的任务都适用；需要其他目录时在图中显式设置 `case_dir`。
- `step=all` 包含初始帧 `Polar.00000000.dat`，它是极化乘以 p0，与后续归一化帧的幅值尺度不同，
  同一个 `min_magnitude` 对它的分类结果不能与后续帧直接比较。
- 报告时写明 `min_magnitude`（默认 0.1，单位与场相同，即 `unspecified`）、`max_angle_deg`、是否启用
  薄膜检测和实际步号；分数的分母只含已分类点（排除 −1 未分类／无数据与 0 衬底），`fractions.json`
  的 `attrs` 给出分母与排除点数。能量单位为 `normalized`，长度为网格索引。

## 本机验收流程

在 Linux 开发机上用真实 muFerro 验收一次：只绑定回环地址、只用临时目录，共两次单 rank 运行，
每次约 3 秒；不使用 `--ranks` 大于 1（可从外部访问的主机上 Hydra 会监听 0.0.0.0）。先在
`.[server,science,control,visualization,test]` 环境中确认完整回归通过：
`PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -m "not desktop"`。

0. 临时目录与环境。`STK_SRC` 为本仓库，`MUPRO_SRC` 为已构建并安装 linux-intel-release 的
   muprosdk 源码目录：

   ```bash
   export PYTHONDONTWRITEBYTECODE=1
   A=/path/to/scratch/accept-mupro-$(date +%Y%m%d%H%M%S)
   mkdir -p "$A" && cd "$A"
   python3.12 -m venv venv && venv/bin/pip install --no-cache-dir "$STK_SRC[server,science,control,visualization]"
   export PATH="$A/venv/bin:$PATH"
   git -C "$STK_SRC" status --short > repo.before
   git -C "$MUPRO_SRC" status --short > sdk.before
   L="$MUPRO_SRC/out/build/linux-intel-release/test_license/key"
   stat -c '%n %Y %s' "$L"/* > license.before   # 只记录元数据，不读取许可文件
   ```

   按“节点环境”中的示例写 `$A/mupro-env.sh`，然后设置 Runtime 环境：

   ```bash
   export MUPRO_SDK_PREFIX="$MUPRO_SRC/out/install/linux-intel-release"
   export MUPROROOT="$L" STK_MUPRO_ENV_SCRIPTS="$A/mupro-env.sh" STK_STATE_DIR="$A/state"
   unset STK_MUPRO_ALLOW_LOCAL_MPI STK_RUNTIME_URL STK_RUNTIME_TOKEN
   ```

1. 工具链：`python -m suan.mupro check --json > check.json`，期望 `ok` 为 true，`program`、
   `license_dir`、`example_case` 通过，`shared_libraries` 没有找不到的库。
2. Runtime：

   ```bash
   suan server init --workspace-root "$A/shared" --port 0 --concurrency 1
   nice -n 10 suan server start
   trap 'suan server stop --supervisor' EXIT
   suan server status > status.json
   ```

   `init` 不打印令牌。`status.json` 中 `api_running` 与 `supervisor_running` 为 true，`url` 为
   `http://127.0.0.1:<端口>`；`ss -ltnp | grep ":<端口> "` 只显示 127.0.0.1；
   `suan server doctor --json > doctor.json` 报告 `ok` 为 true。这里是临时 runtime，且节点代理
   在进程内按 `status` 的地址连接，所以可以用 `--port 0`；常驻 runtime 和 `suan-node` 必须用固定端口。
3. 案例与工作区：

   ```bash
   mkdir case16 && cp "$MUPRO_SDK_PREFIX"/share/mupro/skills/mupro-muferro/examples/{input.toml,material.toml} case16/
   WS=$(suan workspaces create mupro-accept | python -c 'import json,sys;print(json.load(sys.stdin)["id"])')
   ```

4. CLI 提交（本机后端）：

   ```bash
   suan mupro submit --workspace "$WS" --input case16 --ranks 1 --walltime 600 --memory-mb 2048 \
     --name accept-np1 --key accept-np1-0001 --wait --timeout 300 > submit.json
   ```

   期望 `state` 为 `succeeded`，记下任务 ID 为 `TASK`。运行期间用 `ss -ltnp` 采样，不应出现
   新的监听（单 rank 不启动 mpiexec）；主机上其他进程也可能打开 Hydra 监听，按本次进程名或 PID 过滤。
5. 结果：`suan mupro result "$TASK" > result.json` 退出码 0，期望：
   - `verification.status` 为 `passed`，`verifier` 为 `stk-mupro-1`；
   - `case` 的 `grid` 为 [16,16,16]，`steps` 为 101，`output_interval` 为 100；
   - `layout` 为 1 rank、1 线程、`launcher` 为 `none`；
   - 30 个场帧，包括 (Polar,0)、(Polar,100)、(Strain,1)、(Strain,101)；
   - `qoi.total_energy` 为 −727.9144455（step 101）：这是不经 STK 直接运行 muFerro 1 rank 的参考值，
     2026-09-24 本机验收的两次 STK 运行与之完全相同；结果随 rank 数变化；
   - `environment` 中 OMP 与 MKL 均为 `"1"`，`MUPROROOT` 只有路径，`program` 记录了 SHA-256。
6. 服务端证据，`R=$A/shared/$WS/runs/$TASK`：
   - `$R/environment.json` 的 `threads` 为 `{"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}`，
     argv 含 `"--ranks", "1", "--threads-per-rank", "1"`；
   - `suan mupro verify "$R/work" --case-dir case16` 通过（退出码 0）。
7. 幂等：用同一 `--key` 重复第 4 步，返回同一任务 ID，`runs/` 下没有新目录。
8. 节点代理路径的无界面视图。在仓库外的临时脚本 `$A/view_check.py` 中：
   - 用 `NodeAgent(suan.runtime.cli.get_client(None, "$A/state"), "$A/agent-cache")` 对
     `case16/Polar.00000100.dat` 执行 `view.build`，选项
     `{mode: slice, axis: 2, index: 8, component: "magnitude"}`；manifest 的 field 为 `Polar`、
     timestep 为 100、coordinate_units 为 `grid index`、dimensions 为 [16,16,16]；
   - 以 value_range 中点的等值面和向量箭头都能生成；
   - `view.probe` 在 [3,4,5] 的结果等于从 `$R/work/case16/Polar.00000100.dat` 直接解析的
     `4 5 6 c v` 各行；
   - `case16/energy_out.dat` 报 `Not a regular-grid field DAT`。
9. Blender 原生模板链路，无界面、在进程内完成，不开新端口。在 `$A/template_check.py` 中：
   - 用 `create_app("$A/control", <仅保存在内存中的随机 40 字符 owner token>,
     load_templates(["muferro-example"]))` 建立应用，经 fastapi TestClient 访问，并配对一个节点；
   - 建立 `Bridge("$A/desktop", connection)`，`$A/desktop/client.json` 为
     `{"template": "muferro-example"}`；
   - 执行与 C++ 按钮相同的命令 `{kind: "task.submit", payload: {template: "demo-field",
     workspace_id: WS}}`，存储的操作中 `payload.template` 为 `muferro-example`，状态为 `queued`；
   - 节点代理在真实 Runtime 上执行它（第二次真实运行，SDK 示例），等待成功；
   - 桥接执行 `task.artifacts`，选择 `Polar.00000100.dat` 并 `view.build`，
     `$A/desktop/scene.json` 通过 `validate_scene`，manifest 的 timestep 为 100。
10. 关闭与清理：
    - `suan server stop --supervisor` 后 `suan server status` 两项均为 false；
    - 记录的 API、supervisor 进程以及各任务 `worker.json`、`program.json` 中的 PID 都已退出；
      除验收脚本自身及其子进程外，没有命令行或工作目录（`/proc/<PID>/cwd`）在 `$A` 下的进程。
      muFerro 的命令行是 SDK 路径，只能按工作目录识别，因此也确认没有工作目录在 `$A` 下的
      muFerro、mpiexec 或 hydra_pmi_proxy。不要用 `pgrep -af "$A"`：它会匹配命令行含 `$A` 的
      验收脚本和观察进程。`ss -ltnp` 中没有本次运行的套接字；
    - `repo.before`、`sdk.before` 与新的 `git status --short` 一致，`license.before` 与新的 `stat` 一致；
    - `du -sh "$A/shared"` 约 31M（两次运行，每次约 16 MB）。
11. 记录：在 `$A/acceptance.json` 写入日期、主机、STK 提交、`MUPRO_SDK_PREFIX`、muFerro SHA-256、
    耗时、任务 ID、校验摘要和 qoi，不含令牌和许可内容；再把结果追加到
    [runtime 验收记录](runtime-validation.md) 并填入下方“结果”。

仅当 Release 许可检查失败（stderr 含 `invalid license`）时，改用
`MUPRO_SDK_PREFIX="$MUPRO_SRC/out/install/linux-intel-debug"` 与 `--program muFerrod`
（开发构建，不检查许可）重做第 4–9 步，并记录实际使用的程序。第 9 步的内置模板不带
`--program`，需用 `--template-file` 注册带 `--program muFerrod` 的变体。

### 结果

2026-09-24 04:09–04:13（UTC+8，全程 279.6 秒）在 r730xd 测试主机（`mnemora-test`，Linux
7.0.0-30-generic x86_64，48 个逻辑 CPU，Python 3.12.14）按上述流程执行一次，**通过**：两次真实
muFerro 单 rank 运行都成功，并通过 `stk-mupro-1` 校验。

- STK：`feature/independent-runtime-mupro` 分支上基于 217bd86 的未提交工作树（`acceptance.json`
  记录工作树摘要 `6b9fe3bcdb1bd651…`），以非可编辑方式安装到临时 venv（suan_toolkits 0.1.0a1，
  pip 用时 246 秒）。
- 程序：Release 构建 `out/install/linux-intel-release/bin/muFerro`（muprosdk b2adf41，SHA-256
  `c0c1f3454f5ff5384c76e70455b0441bb8ebeeb40b711b2360f2f0f1d099683a`）。`MUPROROOT` 为构建树中的
  测试许可目录，只传路径。Release 许可检查通过，没有改用 muFerrod。
- 第 1 步 `check.json`：`ok` 为 true。`env_scripts`、`sdk_prefix`、`program`、`shared_libraries`
  （全部库可解析）、`mpi_launcher`（找到 oneAPI MPI 2021.18 的 mpiexec，未使用）、`license_dir`
  （只确认是目录）和 `example_case` 全部通过。
- 第 2 步：`init` 输出不含令牌，`config.json` 权限为 600。API 监听 `127.0.0.1:33909`，
  `ss -ltnpH '( sport = :33909 )'` 只显示 127.0.0.1，supervisor 没有监听。`doctor` 的 8 项全部通过。
- 第 4 步 CLI 提交：任务 `b19c4c0fdbbd41708acf4373e6a3f383`（工作区
  `c0056c9be1104fff9d02e1ed4cbcf2fe`，键 `accept-np1-0001`）成功，`--wait` 墙钟 5.24 秒，求解器 3.02 秒。
  运行期间 psutil 每 0.1 秒采样一次，共 34 次；`ss -ltnpH` 采样 21 次。本次运行只有 API 的
  127.0.0.1:33909 一个监听；进程中有 muFerro，没有 mpiexec 或 hydra。
- 第 5 步 `result.json`：`verification` 为 `passed`（`stk-mupro-1`：completion 101 步，energy 101 行
  有限值，progress 101 条，frames 30 个且网格为 [16,16,16]）。`case` 为 [16,16,16]、起始步 0、101 步、
  间隔 100。`layout` 为 1 rank、1 线程，`launcher` 为 `none`，`command` 只有 muFerro 本身（MPI
  singleton）。30 个场帧包括 (Polar,0)、(Polar,100)、(Strain,1)、(Strain,101)。`qoi.total_energy` 为
  −727.9144455（step 101），与直接运行 muFerro 的 1 rank 参考值相同（差 0.0）。`environment` 中 OMP 与 MKL
  为 `"1"`，`MUPROROOT` 只有路径。`program` 的 SHA-256 与重新计算的一致，`exit_code` 为 0。
- 第 6 步：`environment.json` 的 `threads` 中 OMP 与 MKL 均为 `"1"`，`layout` 为 1 节点、1 rank、
  1 线程，`env_overrides` 为空，argv 含 `--ranks 1 --threads-per-rank 1 --case-dir case16`。
  `suan mupro verify` 退出码 0。stderr 为 2 字节，日志中没有许可拒绝。
- 第 7 步幂等：同一 `--key` 返回同一任务 ID，`runs/` 目录数与 Runtime 任务数都保持为 1。
- 第 8 步视图（0.89 秒）：slice（axis 2、index 8、magnitude）通过 `validate_scene`，field 为 `Polar`、
  timestep 100、`grid index`、[16,16,16]、3 分量、256 点，value_range 为 [0.59141, 0.60907]。中点
  0.600240 的等值面有 2875 点、5251 个三角形；向量箭头有 4536 点、3888 个三角形。`view.probe` 在
  [3,4,5] 得到 [0.60334241, −0.0075543507, 0.027026171]，与直接解析 `4 5 6` 各行的值完全相同。
  `energy_out.dat` 报 `Not a regular-grid field DAT`。
- 第 9 步模板链路：与 C++ 按钮相同的 `demo-field` 命令存为操作 `ac45b078da604d1ea50261591e725c0d`，
  状态为 `queued`，`payload.template` 为 `muferro-example`，spec 为内置模板加上 `workspace_id` 与
  `name`。节点代理执行的第二次真实运行 `89213f88715844a7941a3f7601711a0c` 在派发后 4.57 秒成功
  （求解器 2.83 秒），校验通过，qoi 相同，30 个场帧，程序 SHA-256 相同。`task.artifacts` 列出 36 个
  文件；`view.build` 写出的 `scene.json` 通过 `validate_scene`（Polar、timestep 100、`grid index`、16³）。
- 第 10 步：`suan server stop --supervisor` 退出码 0，`status` 两项为 false，33909 不再监听，API 与
  supervisor 进程已退出。没有残留的 suan.runtime、muFerro、mpiexec 或 hydra 进程，也没有本次运行的
  套接字。muprosdk 的 `git status` 前后均为空。许可目录及其 4 个文件的 stat（名称、类型、大小、权限、
  inode、mtime、ctime）前后一致，STK 与验收脚本没有读取或复制这些文件。`/dev/shm` 没有新条目。
  `du -sh "$A/shared"` 为 31M。本次运行没有在 STK 仓库中提交或暂存，也没有产生构建产物或被忽略文件。
  证据保存在临时验收目录，没有纳入仓库。

发现的问题（不影响本次结论）：

- 内置 `muferro-example` 模板只声明 `walltime_seconds` 与 `memory_mb`，没有 `ranks`／
  `threads_per_rank`，worker 因此走非 MPI 路径，模板运行的 `environment.json` 中 `MKL_NUM_THREADS`
  为 null。求解器本身仍以 OMP 与 MKL 均为 1 运行（见 `stk-mupro.json`），因为 `run` 按
  `--threads-per-rank`（默认 1）设置这两个变量。（验收后已修复：模板改为与 `suan mupro submit
  --example` 相同的 1 rank、每 rank 1 线程。）
- 用 `--port 0` 初始化时，停止后 `suan server status` 的 `url` 显示 `http://127.0.0.1:0`（回退到配置的
  端口），这不是实际地址。（验收后已修复：此时 `url` 为 `null`。）

未覆盖：多 rank（mpiexec／srun 与 Hydra 监听）；真实集群与并行云（Slurm／PBS、module、共享文件系统、
集群许可）；GPU／Blender C++ 界面构建（没有编译或启动 Blender，C++ 按钮只用等价命令在进程内检验）。
控制服务经 TestClient 在进程内访问，没有单独启动 `suan-control serve` 或 `suan-node`。
