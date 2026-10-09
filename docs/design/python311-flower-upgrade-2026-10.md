# STK 升级到 Python ≥ 3.11 并与 Flower 同环境共存：评估

状态：**所有者已决定（2026-10-09，方案“所有者决定（第三轮）”第 7、8 项与 Flower 单独环境）：4.1 Python ≥ 3.11 已实施；Flower 放在单独的环境，hub 不装 flwr，因此 4.2“放宽 Web 栈并加入 `fl` extra”不做；其余为调研结论。** 上位方案：[思劲平台方向](sijin-platform-2026-10.md)“所有者决定（第二轮，2026-10-08）”第 2 条。以下内容由调研整理，标（未核实）处没有一手来源或没有实测；涉及法律的结论须法务确认。

日期：2026-10-09。对应的所有者决定原文：
“把 STK 及其 Web 框架升级到 Python 3.11 以上，使 Flower 与 STK 可装在同一环境”。
上一轮的[联邦学习框架评估](fl-framework-evaluation-2026-10.md)推荐方案 A1（Flower 只作算法库），本文沿用这一前提。
这里的“Web 框架”理解为控制服务（hub，`suan-control`）用的 FastAPI / Starlette / Uvicorn 这套 Python 栈；
`web/` 目录是 Node 构建的前端，与 Python 版本无关。

**怎么核实的**（数据截至 2026-10-09）：
- 依赖约束逐版本取自 PyPI JSON API 的 `requires_dist`（如 <https://pypi.org/pypi/flwr/1.39.0/json>）。
- Flower 主分支的锁定取自 <https://github.com/flwrlabs/flower/blob/main/framework/pyproject.toml>（最后一次修改是
  `4974a2fc6b`“Prepare 1.39.0 release”，2026-09-28）和 nightly 包 <https://pypi.org/pypi/flwr-nightly/json>。
- 版本说明取自各项目的 GitHub Releases；漏洞信息取自 OSV（<https://osv.dev>）。
- 在本机实验目录里用 `git archive HEAD` 导出仓库副本做实验，**没有改动仓库**：
  - 用 `uv pip compile` 做依赖解析（索引为 pypi.org）；
  - 在 Python 3.11.16 上建了四个虚拟环境：基线（STK 现有约束）、同环境（fastapi 放宽到 0.138.x 并装 `flwr==1.39.0`）、
    覆盖版（用 uv 的 override 强行保留 fastapi 0.141.1 与 cryptography 50），以及 `flwr==1.32.1` 加 fastapi 0.141.1；
  - 在基线环境和同环境里各跑一遍 STK 的非桌面测试。
- 许可证读的是装好的 wheel 里随附的 LICENSE 文件和 `METADATA`。
- 初稿完成后又做了一轮独立复核：重新查询上述来源，并补充了初稿漏掉的内容——SecAgg+ 掩码生成器的缺陷、
  flwr 默认开启的遥测与更新检查、上游已有的放宽 cryptography 的 PR、Flower 的 HTTP 化方向、grpcio 里的 MPL-2.0 文件、
  Ubuntu 22.04 上 Python 3.10 的实际补丁状态，以及 3.12 已进入只修安全问题阶段。这些内容分别并入下文各节。

---

## 结论摘要

1. **“升级 Web 框架”实际上是降级。** `flwr` 从 1.33.0（2026-08-05）到 1.39.0（2026-09-28，当前最新正式版），以及 main 分支和
   `flwr-nightly 1.40.0.dev20261008`，都把 Web 栈锁在同一组旧版本上：
   - `fastapi>=0.138.0,<0.139.0`；
   - `starlette>=1.3.1,<1.4.0`；
   - `uvicorn[standard]>=0.49.0,<0.50.0`。

   STK 的 `control` extra 锁定 `fastapi==0.141.1`，两者装不进同一个环境（uv 解析器给出的冲突原文见 1.3 节）。
   满足最新 flwr 的最高 fastapi 版本是 **0.138.2**（2026-06-29）。要同环境，需要做以下降级：

   | 包 | 降级 |
   |---|---|
   | fastapi | 0.141.1 → 0.138.2 |
   | starlette | 1.7.0 → 1.3.1 |
   | uvicorn | 0.54.0 → 0.49.0 |

2. **Python ≥ 3.11 的要求来自 flwr，不是来自 fastapi。**
   - flwr 从 1.31.0 起要求 `>=3.11`（<https://pypi.org/pypi/flwr/1.31.0/json>）；fastapi 0.138.2 仍是 `>=3.10`
     （<https://pypi.org/pypi/fastapi/0.138.2/json>）。
   - Python 3.10 上游已于 **2026-10-01 结束生命周期**（<https://peps.python.org/api/release-cycle.json>，PEP 619）。
     但 Ubuntu 22.04 自带的 python3.10 仍由 Canonical 继续发安全更新（当前为 3.10.12-1~22.04.18，
     <https://packages.ubuntu.com/jammy-updates/python3.10>；<https://changelogs.ubuntu.com/meta-release> 中 22.04.5 LTS 仍为 Supported），
     所以“3.10 已经没有补丁”只是次要理由，**决定性的理由是 flwr 的要求**。
   - 提到 3.11 的代价很小：本机在 3.11.16 上跑全部非桌面测试，结果是 **2306 passed / 22 skipped**。
3. **实测：降到 fastapi 0.138.2 后，STK 本身没有出问题。**
   - 放宽 fastapi 后，STK 全部 extras 加 `flwr==1.39.0` 在 Python 3.11、3.12、3.13、3.14 上都能解析。
   - 同环境（3.11）的非桌面测试是 **2306 passed / 22 skipped**，和同版本 Python 不装 flwr 的基线完全一致；
     其中控制服务和 hub 相关的 12 个测试文件共 146 项全部通过。
   - fastapi 0.139.0 到 0.141.1 的版本说明里没有破坏性变更。改动集中在 `app.frontend()`、SSE/JSONL 流式端点和依赖解析的性能，
     另有 `include_router`、`jsonable_encoder`、嵌套 Annotated、`response_model_*` 的几处修复（见 2.3 节），STK 都没有用到。
4. **真正的代价在 flwr 带进来的其他锁定，而不在 fastapi 本身：**
   - **cryptography 被锁在 `<47`，解析为 46.0.7。** OSV 对这个版本列出 3 条 HIGH 和 1 条 MODERATE 公告，修复分别在
     48.0.1、49.0.0、50.0.0；46.x 系列没有补丁版本。STK 现在的 server/control 环境里**根本没有 cryptography**，
     所以这是**新引入**一个已知有漏洞的版本，不是降级。
   - **hub 的运行行为会悄悄改变。** 换成 uvicorn 0.49.0 后，由于 STK 本来就锁了 `websockets==15.0.1`，`ws="auto"` 会选中
     已弃用的旧实现（legacy `websockets`），而不是现在 0.54.0 选的 `websockets-sansio`；`[standard]` extra 另外带来 httptools 和 uvloop，
     并被自动启用。
   - starlette 1.3.1 缺少 1.5.1 才加入的 `FileResponse` Range 头加固（最多 100 个 range、拒绝倒置 range），而 hub 的 blob 下载正好用
     `FileResponse`。1.3.0 已经会截断过大的后缀 range，所以 1.3.1 并非完全没有 Range 防护。
   - 另有 `protobuf<7`、`typer<0.21`、`rich<15`、`packaging<26` 等上限。
   - 环境多出 33 个包（含 flwr 本身、一个 54 MB 的 `uv` 可执行文件、grpcio、SQLAlchemy），虚拟环境从约 860 MB 增加到约 1013 MB。
   - flwr **默认开启遥测和更新检查**，会连 `telemetry.flower.ai` 和 `api.flower.ai`。本次只在测试和 CI 里关掉了，
     部署到学校节点时必须在部署配置里写死关闭（见 4.2 节）。
5. **比 cryptography 更关键：SecAgg+ 的掩码不是用密码学安全的随机数生成的。** 这与选哪种环境方案无关。
   - Flower issue [#7522](https://github.com/flwrlabs/flower/issues/7522)（2026-07-02 起一直 open）指出：`pseudo_rand_gen` 先把 ECDH 共享密钥
     或 `rd_seed` 用异或压缩成 32 位，再交给 `np.random.RandomState`（Mersenne Twister）生成私有掩码和成对掩码。
     flwr 1.39.0 的 `flwr/common/secure_aggregation/secaggplus_utils.py` 第 83–92 行确实如此，main 分支相同，
     本机实验目录里装的 1.32.1 也是同一段代码。
   - 修复用的 [PR #7570](https://github.com/flwrlabs/flower/pull/7570) 还没合并；修复后掩码值会变，所有节点和协调进程必须同时升级。
   - A1 方案的安全聚合正是建在 `SecAggPlusWorkflow` 和 `secaggplus_mod` 上。两两掩码只剩约 32 位熵，被暴力恢复后，
     单个节点的模型更新就可能暴露，直接削弱“数据留在组内”的承诺（可利用性未核实）。
   - 下文的 ECDH、HKDF、Fernet、Shamir 自检测不出这个问题；OSV 上也没有 flwr 的公告，靠 OSV 扫描会漏掉。
   - 对策：在 PR #7570 合并之前，不把 SecAgg+ 当作对合作方的隐私保证；若首批测试就要用 SecAgg+，按 4.6 节方案 E 的思路
     自带一个修正后的掩码生成器（见 2.5 节和 4.4 节 R9）。
6. **Flower 近期不太会放宽这组锁定。**
   - FastAPI 和 Uvicorn 是在 [PR #7502](https://github.com/flwrlabs/flower/pull/7502)（2026-06-28 合并）中移进核心依赖的；
     PR 正文为空，“有意为之”只能从标题和改动看出来。截至 2026-10-09，main 分支和 nightly 仍是同一组锁定，
     也没找到要求放宽 fastapi、starlette、uvicorn 的 issue。
   - cryptography 倒是已有两个放宽的 PR：dependabot 的 [#7763](https://github.com/flwrlabs/flower/pull/7763)（升到 50.0.0，2026-08-05 创建）
     和社区的 [#7071](https://github.com/flwrlabs/flower/pull/7071)。两者都开着，评论都是 0 条，两个多月没人处理。
   - 历史上 flwr 1.29 到 1.32.1 一直锁着 `starlette<0.51`，而 Starlette 1.0 在 2026-03 就已发布。
   - Flower 的方向是**加重**对 Web 栈的依赖：1.33 之后 Runtime API 改成了 HTTP（[#7936](https://github.com/flwrlabs/flower/pull/7936)、
     [#7924](https://github.com/flwrlabs/flower/pull/7924)），Control API 也在 HTTP 化（[#8055](https://github.com/flwrlabs/flower/pull/8055)、
     [#8093](https://github.com/flwrlabs/flower/pull/8093)）。SuperLink 和 SuperNode 运行时真的会用到 fastapi 和 uvicorn。
   - 所以 STK 一旦和 Flower 同环境，**每次升级 flwr 都等于一次 Web 栈变更，方向可能是降级。**
7. **一个关键发现：A1 方案用到的 Flower 接口根本不导入 fastapi、starlette、uvicorn 和 SQLAlchemy。**
   - 实测导入 `Grid`、`ClientApp`、`FedAvg`、`FedProx`、`SecAggPlusWorkflow`、`secaggplus_mod`、serde 后，新加载的第三方模块是
     numpy、cryptography、pycryptodome、grpc、grpc_health、protobuf、httpx、idna、typer、rich、click、shellingham、pygments、
     typing_extensions 和 iterators。**其中没有 fastapi、starlette、uvicorn 和 SQLAlchemy。** 复核时在 Python 3.11 虚拟环境里重做，同样没有这四个包。
   - 也就是说，对“只当算法库用”的 A1 而言，这个冲突纯粹出在打包元数据上。据此有两个可选方向：
     1. 请 Flower 上游把服务端依赖挪进一个 extra——鉴于上一条的 HTTP 化方向，成功率很低；
     2. 用 uv 的 override 强行共存（实测只能导入和跑通密码学原语，`pip check` 报 4 处不兼容，属于不受支持的配置）。
   - 如果 STK 以后要运行 `flower-superlink` 或 `flower-supernode` 进程，而不只是把 Flower 当算法库用，这些进程就会跑在
     uvicorn 0.49 加 fastapi 0.138 上，这个发现也就不再成立。
8. **备选：`flwr==1.32.1`。** 它要求 Python ≥ 3.11，**但没有 fastapi 依赖**，可以和 fastapi 0.141.1 共存。实测 A1 需要的接口
   它都有：`Grid` 的抽象方法与 1.39 相同，还有 `FedAvg`、`FedProx`、`SecAggPlusWorkflow`、`secaggplus_mod`、
   `ClientApp.__call__` 和 serde。代价是：版本停在 2026-07-01，同样锁 `cryptography<47`，同样有上面第 5 条的 SecAgg+ 掩码问题，
   而且跟不上 Flower 后续的修复。
9. **STK 的 Python 3.10 痕迹不多，下面是全部改动点（逐项见第 3 节）：**
   - `pyproject.toml`；
   - `runtime.yml` 里的两个测试矩阵；
   - 三处版本门槛：Runtime doctor、`suan graph doctor`、`desktop/setup.py`；
   - 四处 `tomli` 回退导入；
   - 六份文档。

   不受影响的部分：
   - 桌面包（Linux tarball、STK.app）**不带 Python**；Windows 安装包还没开始做。
   - 桌面 CI 现在用的是 3.12 或 3.14。
   - `poetry.lock` 早已过期（Poetry 1.7.1 生成、`python >=3.9,<3.12`、缺 fastapi），没有任何在用的 CI 读它。

---

## 详细分析

### 1. Flower 的依赖约束（问题 1）

#### 1.1 逐版本对照（PyPI `requires_dist`）

数据来源为 `https://pypi.org/pypi/flwr/<版本>/json`，例如 <https://pypi.org/pypi/flwr/1.39.0/json>、
<https://pypi.org/pypi/flwr/1.33.0/json>、<https://pypi.org/pypi/flwr/1.32.1/json>、<https://pypi.org/pypi/flwr/1.30.0/json>。
标“extra”的是可选依赖，不装对应 extra 就不生效。

| flwr | 发布日期 | Python | fastapi | starlette | uvicorn | cryptography | protobuf | typer | rich | packaging |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.29.0 | 2026-04-12 | ≥3.10 | 无 | 0.50.x（extra `rest`） | 0.40.x（extra `rest`） | ≥46.0.5,<47 | ≥5.28,<7 | ≥0.13,<0.21 | ≥13.5,<14 | ≥24,<26 |
| 1.30.0 | 2026-05-20 | ≥3.10 | 无 | 同上 | 同上 | 同上 | 同上 | 同上 | 同上 | 同上 |
| 1.31.0 | 2026-06-08 | **≥3.11** | 无 | 同上 | 同上 | ≥46.0.7,<47 | 同上 | 同上 | <14 | 同上 |
| 1.32.0 / 1.32.1 | 06-25 / 07-01 | ≥3.11 | **无** | 同上 | 同上 | 同上 | 同上 | 同上 | ≥14,<15 | 同上 |
| 1.33.0 | 2026-08-05 | ≥3.11 | **≥0.138.0,<0.139.0（核心）** | **≥1.3.1,<1.4.0（核心）** | **[standard] ≥0.49.0,<0.50.0（核心）** | 同上 | 同上 | 同上 | 同上 | 同上 |
| 1.34.0–1.39.0 | 08-19 至 09-28 | ≥3.11 | 同 1.33 | 同 1.33 | 同 1.33 | 同上 | 同上 | 同上 | 同上 | 同上 |
| main 分支 / nightly 1.40.0.dev20261008 | 2026-10-08 | ≥3.11 | 同 1.33 | 同 1.33 | 同 1.33 | 同上 | 同上 | 同上 | 同上 | 同上 |

1.39.0 的其他核心约束：
- 通信与序列化：`grpcio>=1.70,<2`、`grpcio-health-checking>=1.70,<2`、`numpy>=1.26,<3`；
- 密码学：`pycryptodome>=3.18,<4`；
- 工具与配置：`iterators>=0.0.2,<0.0.3`、`uv>=0.11.15,<0.12`、`tomli>=2.0.1,<3`、`tomli-w>=1,<2`、`pathspec>=1.0.4,<2`、
  `prompt-toolkit>=3.0.52,<4`、`pyyaml>=6.0.2,<7`；
- 网络与命令行：`requests>=2.33,<3`、`httpx>=0.28.1,<1`、`click>=8,<9`；
- 状态库：`sqlalchemy[asyncio]>=2.0.45,<3`、`alembic>=1.18.1,<2`。

**flwr 不直接约束 pydantic。** pydantic 经 fastapi 间接引入（`pydantic>=2.9.0`），实际解析为 2.14.0，与 STK 现状相同。

FastAPI 和 Uvicorn 的来历：[PR #7502 “Move FastAPI and Uvicorn to core dependencies”](https://github.com/flwrlabs/flower/pull/7502)
于 2026-06-28 合并，1.33.0 起生效。它的改动把 `uvicorn[standard]>=0.49.0,<0.50.0` 和 `fastapi>=0.138.0,<0.139.0` 从 `rest` extra 移到核心依赖，
`rest` 里只剩 starlette；PR 正文为空，没有写明理由。
starlette 后来也成了核心依赖（1.33.0 的元数据和 main 分支的 pyproject 都是如此），所以仍开着的
[PR #7511 “Make Starlette a core dependency”](https://github.com/flwrlabs/flower/pull/7511) 实际上已经过时，不是一项待定的变更。

上游有没有人要求放宽：
- fastapi、starlette、uvicorn：在 GitHub 上搜 `repo:flwrlabs/flower is:open fastapi` 只有 3 个功能 PR（#8037、#7798、#7678），
  **没有要求放宽这三者锁定的 issue 或 PR**。
- cryptography：已有两个放宽的 PR 开着——dependabot 的 [#7763 “Bump cryptography from 46.0.7 to 50.0.0”](https://github.com/flwrlabs/flower/pull/7763)
  （2026-08-05 创建）和社区的 [#7071 “Feature/cryptography 47 upgrade”](https://github.com/flwrlabs/flower/pull/7071)，评论都是 0 条。
- Flower 的方向是继续加重对 Web 栈的依赖：1.33 之后 Runtime API 由 gRPC 改为 HTTP
  （[#7936 “Switch RuntimeAPI to HTTP from gRPC”](https://github.com/flwrlabs/flower/pull/7936)、[#7924 “Add HTTP Grid for the Runtime API”](https://github.com/flwrlabs/flower/pull/7924)），
  Control API 也有 HTTP 化的改动（[#8055](https://github.com/flwrlabs/flower/pull/8055)、[#8093](https://github.com/flwrlabs/flower/pull/8093)）。

#### 1.2 回答：有没有 flwr 版本能和 fastapi 0.141.x 共存？

- **有，但只有不依赖 fastapi 的旧版本**：
  - ≤ 1.30.0 可以在 Python 3.10 上用；
  - 1.31.0 到 1.32.1 需要 Python ≥ 3.11。

  1.33.0 及以后的所有版本（包括 nightly）都不行。
- **满足最新 flwr 的最高 fastapi 版本是 0.138.2**（2026-06-29，<https://pypi.org/pypi/fastapi/0.138.2/json>）。
  fastapi 当前最新是 0.143.0（2026-10-08）。所以对 STK 来说，“跟上 Flower”意味着把 fastapi 从 0.141.1 **降 3 个小版本**。
- **1.39.0 之后有没有放宽**：截至 2026-10-09 没有新的正式版。nightly `1.40.0.dev20261008` 和 main 分支的 `framework/pyproject.toml`
  里仍是 `fastapi>=0.138.0,<0.139.0`、`starlette>=1.3.1,<1.4.0`、`uvicorn[standard]>=0.49.0,<0.50.0`，
  `cryptography>=46.0.7,<47.0.0` 也没变（main 分支的 version 已是 1.40.0）。

#### 1.3 依赖解析实验（`uv pip compile`，pypi.org，在仓库副本上进行）

| 输入 | Python | 结果 |
|---|---|---|
| STK `[server,science,control,visualization,test]` + `flwr==1.39.0`，pyproject 不改 | 3.11、3.12 | **无解**，见下方报错原文 |
| 同上，flwr 不指定版本 | 3.10 | 选中 flwr **1.30.0**，fastapi 0.141.1 不变 |
| 同上，flwr 不指定版本 | 3.11 | 选中 flwr **1.32.1**，fastapi 0.141.1 不变 |
| 把 fastapi 改为 `>=0.138.2,<0.139`，加 `flwr==1.39.0` | 3.11、3.12、3.13、3.14 | 都有解，76 个包 |
| 全部 extras（再加 `mcp`、`ai`、`desktop`）+ `flwr==1.39.0` | 3.11、3.12 | 有解，134 个包；mcp 1.30.0、sentence-transformers 5.7.0、torch 2.14.1、PySide6 6.12.0 都没有冲突 |

第一行的报错原文：

> Because flwr>=1.39.0 depends on fastapi>=0.138.0,<0.139.0 and suan-toolkits[control]==0.1.0a1 depends on fastapi==0.141.1,
> we can conclude that flwr>=1.39.0 and suan-toolkits[control]==0.1.0a1 are incompatible.

用 CI 同款 extras（`server,science,control,visualization,test`）在 Python 3.11 上对比基线与同环境，有变化的包如下：

| 类别 | 包 |
|---|---|
| **降级** | fastapi 0.141.1 → 0.138.2；starlette 1.7.0 → 1.3.1；uvicorn 0.54.0 → 0.49.0；packaging 26.3 → 25.0 |
| **新增**（基线里没有） | cryptography 46.0.7、cffi、pycparser、protobuf 6.33.6、grpcio 1.84.0、grpcio-health-checking 1.81.1、pycryptodome、SQLAlchemy 2.1.4、alembic、mako、greenlet、typer 0.20.1、rich 14.3.4、shellingham、prompt-toolkit、wcwidth、markdown-it-py、mdurl、markupsafe、iterators、uv 0.11.33、uvloop、httptools、watchfiles、python-dotenv、pyyaml、requests、urllib3、charset-normalizer、pathspec 1.1.1、tomli、tomli-w，以及 flwr 本身 |
| **不变** | pydantic 2.14.0、websockets 15.0.1、httpx 0.28.1、numpy（3.11 上为 2.4.6） |

#### 1.4 国内镜像

2026-10-09 查阿里云（<https://mirrors.aliyun.com/pypi/simple/>）和清华（<https://pypi.tuna.tsinghua.edu.cn/simple/>）的索引页，
fastapi 0.138.2、starlette 1.3.1、uvicorn 0.49.0、flwr 1.39.0、cryptography 46.0.7 两边都有。
STK 的 `pyproject.toml` 把阿里云配成主源。只确认了文件在列表里，没有测下载速度。

### 2. STK 自己的约束与 FastAPI 使用面（问题 2）

#### 2.1 与 flwr 冲突的锁定

逐条对照 `pyproject.toml` 第 33–64 行：

- **冲突的只有一条**：`fastapi = { version = "==0.141.1", optional = true }`（第 61 行）。
- **不冲突，但会被拉到 flwr 允许的范围内**：

  | STK 约束 | 解析结果 |
  |---|---|
  | `uvicorn>=0.34,<1` | 0.49.0 |
  | `packaging>=23,<27` | 25.0 |
  | `pathspec>=0.12,<2` | 1.1.1 |
  | `requests>=2.31,<3` | ≥2.33 |
  | `httpx>=0.28,<1` | 0.28.1 |
  | `click>=8,<9` | 8.5.0 |
  | `numpy>=1.24,<3` | — |

- **不冲突**：
  - `websockets==15.0.1`：uvicorn[standard] 只要求 `websockets>=10.4`，见 <https://pypi.org/pypi/uvicorn/0.49.0/json>。
  - `mcp>=1,<2`：mcp 1.30.0 要求 `starlette>=0.27`、`pydantic>=2.11`、`uvicorn>=0.31.1`，`[cli]` 要求 `typer>=0.16`，
    见 <https://pypi.org/pypi/mcp/1.30.0/json>。
  - `tomli` 带 `python<3.11` 标记，在 3.11 及以上根本不安装。
- **fastapi 锁定的来历**：
  - 精确锁定是在 `bc91bed`（2026-09-11，“feat: add persistent runtime and Synorder scientific workbench plugin”）里随 `websockets==15.0.1` 一起加进来的，
    提交说明和文档都没有写理由。
  - 当时 0.141.1（2026-07-29）是最新版，0.142.0 直到 2026-09-29 才发布。推断是“锁定当时测过的版本”（未核实）。
- **`poetry.lock` 不构成约束**：
  - 文件头写明由 Poetry 1.7.1 生成，`python-versions = ">=3.9,<3.12"`，没有 fastapi 和 websockets 的条目。
  - `docs/runtime.md` 第 502 行已经说明它“尚未随本轮依赖重新生成……安装以 `pyproject.toml` 为准”。
  - 唯一用到 Poetry 的是手动触发的旧 Qt 发布流程（`release_stk_app.yml` 的 `windows_build` 任务）。它先运行 `poetry lock` 再安装，
    所以提交在仓库里的锁文件不会生效。

#### 2.2 STK 在哪里用到 FastAPI / Starlette / pydantic / Uvicorn

- `suan/control/app.py`（686 行）：
  - 用到的 FastAPI 接口：`FastAPI(docs_url=None, redoc_url=None)`、`Depends`、`Header`、`HTTPException`、`Request`、
    `WebSocket` / `WebSocketDisconnect`；
  - 响应类型：`FileResponse`（blob 下载）、`JSONResponse`、`StreamingResponse`（手写的 `text/event-stream` SSE，**没有用** FastAPI 自带的 SSE 功能）；
  - 前端：`StaticFiles(html=True)` 挂在根路径（**没有用** `app.frontend()`）；
  - 请求模型：pydantic `BaseModel` 和 `Field(min_length / max_length / pattern / default)`。
- `suan/control/cli.py` 第 117 行：`uvicorn.run(app, host=host, port=port, ws_max_size=FRAME_LIMIT, access_log=False)`。
  没有显式指定 `http`、`loop`、`ws` 用哪种实现。
- `suan/control/agent.py` 和 `suan/runtime/synorder_node.py`：作为客户端调用 `websockets.asyncio.client.connect`。
- `suan/control/model.py`：使用 httpx。
- 测试：10 个文件用 `fastapi.testclient.TestClient`。另有 `test_control_blobs.py`、`test_control_graph.py`、`test_hub_security.py`、
  `test_hub_desktop_bridge.py`、`test_desktop_bridge_hub.py` 启动了真实的 `uvicorn.Server`，走真实的 HTTP 和 WebSocket。

#### 2.3 从 0.141.1 降到 0.138.2 会不会出问题（逐版对照 Release Notes）

- **FastAPI 0.139.0 → 0.141.1**（<https://github.com/fastapi/fastapi/releases>），全部版本说明里没有 “Breaking” 一节：

  | 版本 | 改动 | 是否影响 STK |
  |---|---|---|
  | 0.139.0、0.139.1、0.141.0、0.141.1 | `app.frontend()` 的依赖、点号路径、`check_dir`、后台任务 | 不影响，STK 不用 `app.frontend()` |
  | 0.139.2 | 路由构建改为线程安全 | 不影响 |
  | 0.140.0 – 0.140.7 | 依赖展开与内存占用优化 | 不影响 |
  | 0.140.8 – 0.140.13 | 修复 `include_router` 的流类型、`jsonable_encoder` 的 `exclude_defaults`、嵌套 Annotated、`response_model_*` 对 Iterable 的处理、SSE 行切分与 `status_code` | 不影响：STK 没有用 `include_router`、`response_model` 或 FastAPI 的 SSE |

- **Starlette 1.4.0 → 1.7.0**（<https://github.com/Kludex/starlette/releases>）：

  | 版本 | 改动 | 对 STK 的影响 |
  |---|---|---|
  | 1.4.x、1.5.0 | GZip 改进 | 无，STK 不用 GZip |
  | **1.5.1** | `FileResponse` 最多接受 100 个 range，并拒绝倒置的 range（<https://github.com/Kludex/starlette/releases/tag/1.5.1>） | hub 的 `GET /api/v1/blobs/{sha256}` 用的就是 `FileResponse`，**降到 1.3.1 后失去这项加固**。1.3.0 已有“截断过大的后缀 range”，所以 1.3.1 并非完全没有 Range 防护。OSV 上 starlette 1.3.1 没有对应公告 |
  | 1.6.0 | 加入 `max_body_size` | 无，STK 自己实现了请求体限制 |
  | 1.7.0 | 断开的 WebSocket 改抛 `WebSocketDisconnected`（`RuntimeError` 的子类）；还加了 OpenTelemetry、`QUERY` 方法等 | STK 已经同时捕获 `WebSocketDisconnect` 和 `RuntimeError`（`app.py` 第 500、669 行），降级不受影响 |

- **Uvicorn 0.50.0 → 0.54.0**（<https://github.com/Kludex/uvicorn/releases>）：
  - **0.50.0**：弃用旧的 websockets 实现，并把 `ws="auto"` 的默认值改为 `websockets-sansio`。
  - 0.52.1：修复 `websockets-sansio` 的关闭握手与写流控。
  - **0.53.0**：“Keep upgraded WebSockets alive”（[PR #3107](https://github.com/Kludex/uvicorn/pull/3107)）。修复的是：在同一连接上，
    一个普通请求后紧跟 WebSocket 升级时，HTTP keep-alive 计时器没有解除，会误伤长连接。
- **实测：同环境下 hub 实际用的 HTTP、事件循环和 WebSocket 实现与现在不同。** 直接读装好的源码：
  - uvicorn 0.49.0 的 `protocols/websockets/auto.py` 只要能 `import websockets` 就选旧实现 `websockets_impl.WebSocketProtocol`；
    0.54.0 选 `websockets_sansio_impl`。STK 本来就锁了 `websockets==15.0.1`，所以退回旧实现的直接原因是这个锁定，
    并不是装了 `[standard]`（<https://github.com/Kludex/uvicorn/releases/tag/0.50.0>，#2985）。
  - uvicorn[standard] 会带来 httptools 和 uvloop，`http="auto"`、`loop="auto"` 时会自动选中它们。基线环境没有这两个包，用的是 h11 加 asyncio。
  - 测试仍然全部通过，但同环境多了 12 条弃用警告，都是“websockets.legacy is deprecated”和“remove second argument of ws_handler”这类。
  - 好在 0.49.0 已经支持 `ws="websockets-sansio"`、`http="h11"`、`loop="asyncio"` 这些显式选项（见 `uvicorn/config.py`），
    可以把行为钉死，见第 4 节。

#### 2.4 实测结果（本机，Linux x86_64，48 核）

| 环境 | 关键版本 | 控制服务 / hub 相关的 12 个测试文件 | 全部非桌面测试（`-m "not desktop and not perf"`） |
|---|---|---|---|
| 基线：Python 3.11.16，STK 现有约束 | fastapi 0.141.1、starlette 1.7.0、uvicorn 0.54.0 | 未单独运行，包含在全量里 | **2306 passed / 22 skipped / 4 deselected**，1 条警告，348.9 秒 |
| 同环境：Python 3.11.16，fastapi `>=0.138.2,<0.139`，加 `flwr==1.39.0` | fastapi 0.138.2、starlette 1.3.1、uvicorn 0.49.0、cryptography 46.0.7 | **146 passed**（`test_control*`、`test_hub_*`、`test_desktop_bridge_hub`、`test_workbench_mupro`、`test_integration_mupro`、`test_policy`、`test_visualization`） | **2306 passed / 22 skipped / 4 deselected**，13 条警告，345.3 秒 |

- **两边跳过的 22 项完全相同**：
  - 15 项需要离屏渲染，本机的探测子进程在 3.11 虚拟环境里段错误；
  - 2 项是性能基准；
  - 2 项需要 MCP extra；
  - 3 项需要真实的 MuPRO。

  也就是说，**render 测试在本机没有覆盖**，CI 有 EGL，可以覆盖。
- 同环境里另外验证了：
  - `import flwr, fastapi, starlette`，并导入 `Grid`、`ClientApp`、`SecAggPlusWorkflow`、`secaggplus_mod`、`suan.control.app`；
  - `Grid` 的抽象方法是 `create_message`、`get_node_ids`、`pull_messages`、`push_messages`、`run`、`send_and_receive`、`set_run`；
  - SecAgg 用的 ECDH + HKDF + Fernet 加解密往返和 Shamir 秘密分享的拆分与还原都正常。
- 实验环境装的是 `pip install` 风格的非 editable 安装，与 CI 的 `python -m pip install ".[...]"` 一致。
  运行时设置了 `FLWR_TELEMETRY_ENABLED=0` 和 `FLWR_DISABLE_UPDATE_CHECK=1`。
- 注意这两个变量只在实验和 CI 里设了。flwr 1.39.0 wheel 里：
  - `flwr/supercore/telemetry.py` 中 `FLWR_TELEMETRY_ENABLED` 默认是 `"1"`，上报到 `https://telemetry.flower.ai/api/v1/event`，
    并在 `~/.flwr/source` 写入一个持久的 UUID（[联邦学习框架评估](fl-framework-evaluation-2026-10.md)第 2.1 节已记录默认开启）；
  - `flwr/supercore/constant.py` 中更新检查的地址是 `https://api.flower.ai/v1/update-check/flwr`，用 `FLWR_DISABLE_UPDATE_CHECK=1` 关闭。

  部署到学校节点时，如果不在 systemd 单元或部署配置里写死这两个变量，节点就会向境外服务器发起连接：校园代理能看到，
  也会带来数据出境方面的合规疑问，需要事先和校方 IT 说明。部署要求见 4.2 节。

#### 2.5 flwr 引入的安全与许可证问题

- **SecAgg+ 掩码生成器不是密码学安全的（最重要，与环境方案无关）**：
  - Flower issue [#7522](https://github.com/flwrlabs/flower/issues/7522)（2026-07-02 起一直 open）。flwr 1.39.0 的
    `flwr/common/secure_aggregation/secaggplus_utils.py` 第 83–92 行（节选）：

    ```python
    seed32 = 0
    for i in range(0, len(seed), 4):
        seed32 ^= int.from_bytes(seed[i : i + 4], "little")
    gen = np.random.RandomState(seed32)
    ```

    也就是把 ECDH 共享密钥或 `rd_seed` 用异或压缩成 32 位，再交给 Mersenne Twister 生成私有掩码和成对掩码。
    main 分支相同；本机实验目录里装的 flwr 1.32.1 中同一文件第 90、92 行也是这段代码，所以 4.6 节的方案 B 同样受影响。
  - 修复 PR [#7570](https://github.com/flwrlabs/flower/pull/7570) 尚未合并。修复后掩码值会变，三个课题组的节点和协调进程必须同时升级，
    否则聚合结果对不上。
  - 影响：A1 的安全聚合就建在 `SecAggPlusWorkflow` 和 `secaggplus_mod` 上。两两掩码只剩约 32 位熵，一旦被暴力恢复，
    单个节点的模型更新就可能暴露，“数据留在组内”的承诺随之削弱（可利用性未核实）。这比下面几条 cryptography 公告更关键。
  - 2.4 节的 ECDH、HKDF、Fernet、Shamir 自检测不出这个问题；OSV 上查不到 flwr 的公告，靠 OSV 扫描会漏掉。
  - 对策（见“需要所有者决定”第 4 条）：等上游合并 #7570 后再启用 SecAgg+；或在 STK 里自带一个修正后的掩码生成器
    （即 4.6 节方案 E 的一小部分）。在这之前不应把 SecAgg+ 当作对合作方的隐私保证来宣称。
- **cryptography 46.0.7 的公告**（来自 OSV，2026-10-09 查询；46.x 没有补丁版本，46.0.7 之后直接是 47.0.0）：

  | 公告 | 级别 | 内容 | 修复版本 |
  |---|---|---|---|
  | [GHSA-537c-gmf6-5ccf](https://osv.dev/vulnerability/GHSA-537c-gmf6-5ccf) | HIGH | wheel 里静态链接的 OpenSSL 有漏洞，见 <https://openssl-library.org/news/secadv/20260609.txt> | 48.0.1 |
  | [GHSA-jwv3-5hgf-82ww](https://osv.dev/vulnerability/GHSA-jwv3-5hgf-82ww) | HIGH | 重复的自签中间证书导致指数级的路径构建 | 49.0.0 |
  | [GHSA-m2h6-j472-rp4c](https://osv.dev/vulnerability/GHSA-m2h6-j472-rp4c) | MODERATE | 证书验证器接受通配 DNS 名，可绕过 permittedSubtrees | 49.0.0 |
  | [GHSA-g6cj-pr64-35w5](https://osv.dev/vulnerability/GHSA-g6cj-pr64-35w5) | HIGH | PKCS#7 EnvelopedData 解密存在 Bleichenbacher 预言机 | 50.0.0 |

  在 flwr 1.39.0 源码里 grep，没有发现 PKCS#7 或 `x509` 验证的调用。它从 cryptography 用到的只有 `ec`、`ed25519`、`HKDF`、`Fernet`、
  `hashes.SHA256` 和密钥序列化：PEM 格式的 `load_pem_private_key`、`load_pem_public_key`（`flwr/supercore/primitives/asymmetric.py`
  第 47、63 行，`asymmetric_ed25519.py` 第 70、107 行），以及 ssh 格式的 `load_ssh_private_key`、`load_ssh_public_key`。
  其中 SecAgg+ 会用 `load_pem_public_key` 解析其他参与方发来的公钥（`secaggplus_mod.py` 第 392、475 行，`secaggplus_workflow.py` 第 626 行），
  所以对外来数据做 ASN.1/DER 解析确实在 SecAgg+ 的路径上。
  - 后三条因此**推断**不在 flwr 的代码路径上（只基于 grep，未核实）。
  - 第一条（GHSA-537c）复核时读了 OpenSSL 公告：secadv 20260609 里唯一的 High 是 CVE-2026-45447（`PKCS7_verify` 释放后使用），
    其余 Moderate 和 Low 分布在 CMS、QUIC、OCSP、AES-OCB、ASN.1 等处。flwr 不用 pkcs7，所以这条 High 不在它的调用路径上。
    两点保留：上面说的 PEM 公钥解析会处理外来数据，几条 Low 级的 ASN.1 解析问题会不会碰到这条路径：未核实；
    公告只针对 PyPI wheel 里静态链接的 OpenSSL，从 sdist 构建、链接系统 OpenSSL 时结论不同。
  - 补上 PEM 密钥解析这一点不改变结论：唯一的 High（`PKCS7_verify`）不在 flwr 的调用路径上，另外三条 x509、PKCS#7 公告仍按上面的推断不在。

  另外，同环境里如果装了 `mcp`，`pyjwt[crypto]` 也会用到这份 cryptography。
- **对照组**：同一工具查得 fastapi 0.138.2、starlette 1.3.1、uvicorn 0.49.0、protobuf 6.33.6、grpcio 1.84.0、flwr 1.39.0、
  pycryptodome 3.24.0、sqlalchemy 2.1.4 在 OSV 上都没有公告。
- **新增依赖的许可证**：读的是 wheel 随附的 LICENSE 文件或 `METADATA` 里的 License-Expression。
  - 宽松许可，闭源分发只需保留版权与许可声明：

    | 许可证 | 包 |
    |---|---|
    | Apache-2.0 | flwr、grpcio（主体，另见下方 MPL-2.0 一条）、grpcio-health-checking、requests |
    | Apache-2.0 OR BSD-3-Clause | cryptography |
    | BSD-3-Clause | protobuf、pycparser、markupsafe、python-dotenv、prompt-toolkit |
    | BSD-2-Clause 加部分公有领域 | pycryptodome |
    | MIT | SQLAlchemy、alembic、mako、typer、rich、tomli、tomli-w、uvloop、httptools、watchfiles、pyyaml、urllib3、charset-normalizer、markdown-it-py、mdurl、wcwidth |
    | MIT AND PSF-2.0 | greenlet |
    | MIT-0 | cffi |
    | ISC | shellingham |
    | MIT OR Apache-2.0 | uv |
    | MIT（`METADATA` 写 UNKNOWN，但 LICENSE 文件是 MIT，[仓库 LICENSE](https://github.com/leangaurav/pypi_iterator/blob/master/LICENSE)） | iterators 0.0.2 |

  - **pathspec 1.1.1 是 MPL-2.0**（wheel 里的 LICENSE 首行为 “Mozilla Public License Version 2.0”）。它原本就在 STK 的 `desktop` extra 里，
    现在也会进入 hub 和节点的环境。不修改它的源码时，按文件级弱 copyleft 处理：分发时要提供 pathspec 的源码获取方式。
    这条需要法务确认。
  - **grpcio 1.84.0 里也有一个 MPL-2.0 文件**，所以 grpcio 不是纯 Apache-2.0。wheel 随附的 `dist-info/licenses/LICENSE` 共 623 行：
    除了 Apache-2.0，还有一节 BSD-3-Clause（只涉及 Objective-C 的 podspec 文件），以及一节
    “Following applies to: ./etc/roots.pem — Mozilla Public License Version 2.0”（第 249–251 行）。wheel 里确实带着
    `grpc/_cython/_credentials/roots.pem`（612,920 字节，见 `RECORD`）。闭源分发时要和 pathspec 一并处理，同样交给法务确认。
  - 供应链提示：iterators 由单个作者维护，约 10 个 star，最后推送于 2024-07，却是 flwr 的核心依赖。
  - flwr 本身是 Apache-2.0，[联邦学习框架评估](fl-framework-evaluation-2026-10.md)已逐个读过 <https://github.com/flwrlabs/flower/blob/main/LICENSE>。

### 3. STK 的 Python 3.10 痕迹（问题 3）

| 位置 | 现状 | 改为 |
|---|---|---|
| `pyproject.toml:34` | `python = ">=3.10,<3.15"` | `">=3.11,<3.15"` |
| `pyproject.toml:38` | `tomli = { …, python = "<3.11" }` | 删除（3.11 以上永远不会安装） |
| `.github/workflows/runtime.yml:12`（runtime，Linux） | `['3.10', '3.12']` | 见第 4 节的矩阵 |
| `.github/workflows/runtime.yml:41`（client-windows） | `['3.10', '3.12']` | `['3.11', '3.12']` |
| `suan/runtime/diagnostics.py:221` | `(3, 10) <= sys.version_info[:2] < (3, 15)` | `(3, 11)` |
| `suan/graph/cli.py:469` | doctor 检查 `>= (3, 10)` | `(3, 11)` |
| `desktop/setup.py:271-272` | `(3, 10)` 门槛，提示“Use Python 3.10–3.14” | `(3, 11)`，提示“3.11–3.14” |
| `suan/mupro/run.py:33-36`、`suan/connectors/mupro/inputs.py:17-20`、`tests/test_connectors_muferro.py:18-21`、`tests/mupro_fake.py:110-113` | `try: import tomllib` / `except: import tomli` | 直接 `import tomllib` |
| `suan/mupro/__init__.py:2-3`、`suan/connectors/mupro/inputs.py:1`、`suan/connectors/api.py:10` | 文档字符串提到 tomli 或 3.11 之前 | 同步修改 |
| `suan/README.md:7`、`docs/desktop.md:238`、`docs/runtime.md:32`、`docs/quickstart-linux.md:11`、`docs/runtime-paratera.md:149`、`desktop/QUICKSTART.md:9` | “3.10–3.14” | “3.11–3.14（推荐 3.12）” |
| `docs/runtime-validation.md`、`docs/development-log.md` | 历史上的 3.10 CI 记录 | **不改**，属于历史记录 |

可选的顺手清理：
- `suan/control/app.py:494,669` 的 `asyncio.TimeoutError`：3.11 起它就是 `TimeoutError` 的别名，不改也不影响行为。
- `suan/skills/__init__.py:105` 的注释（“`Traversable.joinpath` 在 3.10 只接受一段路径”）。
- `suan/project/parameter_edits.py:33` 的整数位数上限：保留，它仍然有意义。

不受影响或已经满足的部分：
- **桌面打包不带 Python。**
  - `desktop/packaging/packaging.cmake:19` 写的是“The Python side (suan.desktop_bridge) is not bundled”；
  - `desktop.yml` 第 272 行写的是“the tarball has no Python”；
  - `desktop/QUICKSTART.md:108` 写明 Windows 安装包和内置 Python 属于后续里程碑。

  因此没有需要升级的内置解释器。
- **桌面 CI 用的 Python 都已经 ≥ 3.12**：

  | 任务 | Python |
  |---|---|
  | Linux（Ubuntu 26.04 容器的 `python3`） | 3.14.3（<https://packages.ubuntu.com/resolute/python3>） |
  | linux-package-smoke（Ubuntu 24.04） | 3.12.3（<https://packages.ubuntu.com/noble/python3>） |
  | macOS | setup-python 3.12 |
  | windows-2022 | runner 默认 3.12.10（[runner-images 说明](https://github.com/actions/runner-images/blob/main/images/windows/Windows2022-Readme.md)） |
  | runtime.yml 的 desktop 和 control 任务 | 3.12 |

- **旧 Qt 发布流程**（`release_stk_app.yml`）：
  - Ubuntu 和 macOS 任务写的是 3.9，但已经 `if: false` 停用；
  - Windows 任务用自托管机器的系统 Python，版本未核实，可能早就不满足 `>=3.10`。

  这个流程按 `docs/repository-structure.md` 的说法要随旧 Qt 一起退役，本次不改。
- `plugins/synorder/pyproject.toml` 已经要求 `>=3.11`。
- **3.11 到 3.13 的行为变化**：
  - 在 `suan`、`toolkits`、`tests` 里 grep PEP 594 已移除的模块（distutils、imp、cgi、crypt、telnetlib、asyncore 等），没有发现；
  - CI 已经长期在 3.12 上通过；本机在 3.11.16 上全量通过；
  - 3.13 和 3.14 只做了依赖解析，没有跑测试。
- **部署侧的 Python 来源**：
  - Ubuntu 22.04 自带的是 Python 3.10：<https://packages.ubuntu.com/jammy/python3> 上的 3.10.6 只是 python3-defaults 元包的版本号，
    实际的解释器包 python3.10 在 jammy-updates 里是 3.10.12-1~22.04.18（<https://packages.ubuntu.com/jammy-updates/python3.10>），
    `python3 --version` 显示的是 3.10.12。Canonical 仍在为它发安全更新（22.04.5 LTS 在
    <https://changelogs.ubuntu.com/meta-release> 中仍为 Supported），所以在 22.04 上，提到 3.11 的理由是 flwr 的要求，而不是 3.10 没有补丁。
  - 如果北京、珠海、聊城三个课题组的服务器是 22.04，需要另装解释器，例如 uv 管理的 CPython、conda、Miniforge 或 deadsnakes；
    国内下载渠道未核实。**不要用** jammy-updates universe 里的 `python3.11`：那里唯一的版本是 3.11.0~rc1-1~22.04.1
    （<https://packages.ubuntu.com/jammy-updates/python3.11>），只是发布候选版，不能用于生产。
  - 并行云清单（`docs/runtime-paratera.md:149`）要求共享文件系统上有“3.10–3.14”的环境，要同步改成 3.11 起。
  - 各版本的上游生命周期（<https://peps.python.org/api/release-cycle.json>）：

    | 版本 | 状态 | 结束 |
    |---|---|---|
    | 3.10 | end-of-life | 2026-10-01 |
    | 3.11 | security | 2027-10 |
    | 3.12 | security | 2028-10 |
    | 3.13 | security | 2029-10 |
    | 3.14 | bugfix | 2030-10 |

    3.12 已经处于 security 阶段：只发源码形式的安全修复，python.org 不再提供二进制安装包，这对 Windows 客户端的安装方式有影响。
    所以下文“推荐 3.12”是权衡后的选择（CI 长期在 3.12 上通过、参考主机也是 3.12），不是“最新且受完整支持”。
    3.13 支持到 2029-10，但本次只做了依赖解析、没有跑测试；torch 等依赖在 3.13 上的 wheel 可用性未核实。

### 4. 迁移方案（问题 4）

整体思路：拆成两个提交。先单独把 Python 下限提到 3.11，这一步与 Flower 无关、风险低；
再在一个提交里放宽 Web 栈、增加 `fl` extra、把 hub 的运行行为钉死，并补上 CI。

#### 4.1 第一个提交：Python ≥ 3.11

改第 3 节表格里的全部文件，并在 `handoff.md`、`docs/development-plan.md` 里记一笔。

- **CI**：
  - `runtime`（Linux）矩阵改为 `['3.11', '3.12', '3.14']`：3.11 是下限，3.12 是推荐版本和参考主机的版本，3.14 是上限；
  - `client-windows` 矩阵改为 `['3.11', '3.12']`；
  - 其他任务不动。
- **验收**：Runtime CI 全部通过，Linux 三个版本的 passed 数一致；本机在 3.11 上跑一遍全量测试。

#### 4.2 第二个提交：放宽 Web 栈并加入 `fl` extra

- **`pyproject.toml`**：
  - `fastapi = { version = ">=0.138.2,<0.142", optional = true }`：两端都实测过，单独安装 STK 时取 0.141.1，和 flwr 一起安装时取 0.138.2。
    上限定在 `<0.142`，是因为 0.142.x 和 0.143.0 没有测过，而且 0.143.0 新增了 `opentelemetry-api>=1.44.0` 依赖
    （<https://pypi.org/pypi/fastapi/0.143.0/json>）；
  - 新增 `flwr = { version = "==1.39.0", optional = true }` 和 extra `fl = ["flwr", "numpy"]`；
  - `uvicorn`、`websockets` 的约束保持不变。

  **不要**精确锁死 `fastapi==0.138.2`，否则只用 hub 的安装也会被 Flower 的锁定绑住。
- **`suan/control/cli.py:117`**：改为

  ```python
  uvicorn.run(app, host=host, port=port, ws_max_size=FRAME_LIMIT, access_log=False,
              http="h11", loop="asyncio", ws="websockets-sansio")
  ```

  这样无论装没装 flwr（也就是有没有 uvicorn[standard]），hub 都用同一套 HTTP、事件循环和 WebSocket 实现，与现在的行为一致。
  `tests/test_hub_security.py` 第 323 行附近已经截获了 `uvicorn.run` 的参数，在那里补上这三个参数的断言即可。
- **新增 `tests/test_fl_compat.py`**（没装 flwr 时跳过）：
  - 检查 A1 用到的导入面；
  - 检查 `Grid` 抽象方法集合等于上述 7 个；
  - 用 `message_to_proto` / `message_from_proto` 做一次往返；
  - 做一次 SecAgg 原语自检（ECDH、HKDF、Fernet、Shamir）；
  - 断言导入 A1 接口后 `sys.modules` 里**没有** fastapi 和 sqlalchemy，以便在 Flower 改变导入结构时第一时间发现；
  - 记录 `pseudo_rand_gen` 当前的 32 位种子行为（例如两个按 4 字节异或后相同的种子会生成相同的掩码）。
    上面的原语自检测不出 2.5 节的掩码问题；这一项在上游合并 #7570 后会失败，提醒所有节点和协调进程必须同时升级。

  这正是[联邦学习框架评估](fl-framework-evaluation-2026-10.md)“实施顺序建议”第 5 步要的升级守护测试。
- **`.github/workflows/runtime.yml`**：
  - 在 runtime 矩阵里用 `include` 加一个变量 `extras`，让 Python 3.11 这一条装 `server,science,control,visualization,test,fl`，
    另外两条不装 `fl`。这样同一次 CI 就覆盖了 fastapi 0.138.2 和 0.141.1 两端。
  - 每一条都加 `python -m pip check`。
  - 设环境变量 `FLWR_TELEMETRY_ENABLED=0` 和 `FLWR_DISABLE_UPDATE_CHECK=1`。
  - `control-and-blender-protocol` 任务可以也加一条装 `fl` 的。
- **部署配置**：凡是装了 `fl` 的进程（训练节点上的 Runtime 与 `fl.train`、FL 协调进程），都在 systemd 单元或部署配置里写死
  `FLWR_TELEMETRY_ENABLED=0` 和 `FLWR_DISABLE_UPDATE_CHECK=1`，不依赖用户自己设环境变量（理由见 2.4 节）。
  部署前把“节点不会主动连 Flower 的境外服务”写进给校方 IT 的说明。
- **文档**：
  - [`docs/hub.md`](../hub.md) 写明两种安装形态：hub 默认不装 `fl`；FL 协调进程和训练节点装 `fl`。
  - `docs/runtime.md` 写明 Python 下限，以及 flwr 带来的版本降级、cryptography、遥测关闭方法与 SecAgg+ 掩码问题的说明。
  - 更新[联邦学习框架评估](fl-framework-evaluation-2026-10.md)里“FL 用独立虚拟环境”的结论（待所有者决定后再改）。

#### 4.3 锁文件

STK 现在的约定是“以 `pyproject.toml` 的范围为准，不提供锁文件”（`docs/runtime.md:502`）。建议：

- **不在这次重生成 `poetry.lock`。**
  - 它只服务于旧 Qt 发布流程，而且那个流程会自己运行 `poetry lock`。
  - Poetry 是把所有 extras 合在一起解析的（Poetry 2.x 的具体行为未核实）。一旦 `fl` 进了 extras，生成的锁文件会把 fastapi 定在 0.138.x，
    反而误导只装 hub 的部署。
  - 等旧 Qt 退役时直接删除这个文件。
- 如果需要可复现的部署，用 `uv pip compile --python-version 3.12` 为两种形态（hub；节点加 `fl`）各生成一个 constraints 文件放在 `deploy/` 下，
  安装时用 `pip install -c <constraints文件> ".[...]"`，镜像用阿里云或清华。这一项由所有者决定，见“需要所有者决定”。

#### 4.4 风险与应对

| 风险 | 说明 | 应对 |
|---|---|---|
| R1 cryptography 46.0.7 有已知公告 | 装了 flwr 的环境必然是 46.0.7 | 首批测试先接受并在文档里写明；面向互联网的 hub 不装 `fl`；在上游已有的放宽 PR（#7763、#7071）下推动，而不是另开 issue；备选是用 uv override 强制 ≥50（见 4.6 方案 D，不受支持） |
| R2 hub 运行时实现改变 | 换成 uvicorn 0.49 后，因为 STK 锁了 `websockets==15.0.1`，WebSocket 退回旧实现；`[standard]` 带来的 httptools、uvloop 会替换 HTTP 解析和事件循环 | 按 4.2 显式指定 `http`、`loop`、`ws`，并加断言测试 |
| R3 失去 Starlette 1.5.1 的 Range 加固 | blob 下载走 `FileResponse`；1.3.1 仍有 1.3.0 的“截断过大后缀 range” | hub 不装 `fl` 时不受影响；装了的话，在反向代理上限制 Range 的数量（nginx 的 `max_ranges` 指令，对代理响应是否生效未核实） |
| R4 Web 栈被 Flower 牵着走 | 每次升级 flwr 都可能改变 fastapi、starlette、uvicorn 的版本；Flower 正在把 Runtime/Control API 改成 HTTP，依赖只会更重 | flwr 精确锁定；升级必须经过守护测试和双端 CI；fastapi 用区间约束，不要精确锁定 |
| R5 Python 3.11 的来源与寿命 | Ubuntu 22.04 只自带 3.10（Canonical 仍在打补丁），jammy-updates 里的 3.11 只是 rc1；3.11 于 2027-10 结束生命周期；3.12 已只发源码形式的安全修复 | 推荐部署用 3.12；为学校服务器提供安装 3.12 的说明或脚本；首批部署前可补一次 3.13 的全量测试 |
| R6 依赖体积、供应链与许可证 | 多 33 个包（含 flwr）、约 150 MB，含 54 MB 的 `uv` 可执行文件；iterators 由单人维护；pathspec 和 grpcio 的 `roots.pem` 是 MPL-2.0 | 写进离线打包（S7）的 wheel 清单；许可证清单加上 pathspec 与 grpcio `roots.pem`（MPL-2.0），交法务确认 |
| R7 uvicorn 0.49 的 keep-alive 缺陷（#3107） | 只有在同一连接上先发普通请求、紧跟 WebSocket 升级时才会触发；节点的 WSS 连接经过反向代理，触发概率低（未核实） | 在测试环境做长连接浸泡测试 |
| R8 仍在用 3.10 的现有安装 | 新版本 STK 无法再装进 3.10 | 参考主机是 3.12，并行云验收还没开始，影响很小；在 `handoff.md` 里说明 |
| **R9 SecAgg+ 掩码只有约 32 位种子**（#7522） | 已确认 flwr 1.32.1、1.39.0 和 main 分支都用 32 位种子的 `np.random.RandomState` 生成掩码；可能暴露单个节点的模型更新（可利用性未核实）；修复 PR #7570 未合并，合并后所有节点须同时升级 | 修复前不把 SecAgg+ 当作对合作方的隐私保证；首批若要用，自带修正后的掩码生成器（方案 E 的一小部分）；守护测试跟踪上游修复 |
| R10 flwr 默认遥测与更新检查 | 默认连 `telemetry.flower.ai` 和 `api.flower.ai`，并写持久 UUID；校园代理可见，有数据出境合规疑问 | 按 4.2 在部署配置里写死关闭；事先向校方 IT 说明 |

#### 4.5 测试策略

1. 本地：在 3.11 和 3.14 上，分别以“带 `fl`”和“不带 `fl`”跑全量非桌面测试，passed 数必须一致（本次实测 3.11 两种都是 2306）。
2. CI：Runtime 三个 Python 版本（其中一个带 `fl`）加 `pip check`，Windows 客户端两个版本，桌面 CI 照旧。
3. 守护：`tests/test_fl_compat.py` 加 uvicorn 参数断言；以后升级 flwr 必须先跑这两项。注意密码学原语自检通过
   不代表 SecAgg+ 安全：2.5 节的掩码问题只能靠跟踪上游 #7522/#7570（或自带修正版）解决。
4. 集成：用三个模拟节点做出站 WSS 和 blob 的 FL 原型（[联邦学习框架评估](fl-framework-evaluation-2026-10.md)“实施顺序建议”第 1、2 步），
   在“hub 不带 `fl`、协调进程带 `fl`”的形态下跑通多轮。
5. 部署前：在北京、珠海、聊城三个课题组的服务器上确认能装到 Python 3.12，并能从镜像拿到全部 wheel；确认部署配置里遥测与更新检查已关闭。
   如果考虑用 3.13 作默认版本，先在 3.13 上补跑一次全量非桌面测试。

#### 4.6 做不到同环境共存时的备选

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A 独立的 FL 虚拟环境**（[联邦学习框架评估](fl-framework-evaluation-2026-10.md)原来的推荐） | hub 和节点保持 fastapi 0.141.1；`fl.train` 任务和协调进程用单独的虚拟环境装 flwr | hub 完全不受 cryptography 和 uvicorn 变化的影响 | 要维护两个环境，不符合所有者第 2 条决定的本意 |
| **B 固定 `flwr==1.32.1`** | 在 Python ≥ 3.11 上与 fastapi 0.141.1 共存，实测有解 | A1 需要的接口已验证存在；STK 的 Web 栈不受影响 | 停在 2026-07-01，享受不到 1.33 以后的修复（如 RDP 记账、Runtime/Control API 改为 HTTP）；仍然锁 cryptography<47；同样有 SecAgg+ 32 位种子问题（已在 1.32.1 中确认） |
| **C 等上游放宽** | 向 Flower 提 issue 或 PR，把 fastapi、starlette、uvicorn、sqlalchemy 挪进 `superlink` 一类的 extra；cryptography 则推动已有的 #7763、#7071 | A1 的导入面本来就不用这些包（已实测）；对 Flower 自身也有好处 | 时间不由我们决定；PR #7502 和后来的 Runtime/Control API HTTP 化（#7936、#7924、#8055、#8093）方向正好相反，挪进 extra 的成功率很低；cryptography 的两个 PR 两个多月无人处理 |
| **D 用 uv 的 override 强行共存** | `uv pip install --override`，指定 fastapi 0.141.1、starlette 1.7.0、uvicorn 0.54.0、cryptography 50.0.2 | 实测可解析、可安装，A1 接口能导入，ECDH、HKDF、Fernet 和 Shamir 自检通过 | `pip check` 报 4 处不兼容；pip 用户没法复现；Flower 不支持；没有跑过完整的 SecAgg+ 轮次 |
| **E vendoring** | 只把 A1 用到的 Flower 代码（策略、SecAgg+ 工作流与原语、serde）连同 Apache-2.0 声明一起复制进 STK | 彻底摆脱 Flower 的锁定；可以顺带换掉 SecAgg+ 的 32 位种子掩码生成器（2.5 节），不必等 #7570；和所有者“以后自研 FL 框架”（第 3 条）方向一致 | 要自己跟进上游的安全修复，工作量最大；protobuf 消息定义也要一起带上；换掉掩码生成器后与原版 Flower 节点不互通，所有参与方都要用 STK 的版本 |

---

## 推荐

1. **先把 Python 下限提到 3.11**（4.1，单独一个提交）。决定性的理由是 flwr 要求 3.11；3.10 上游已结束生命周期是次要理由
   （Ubuntu 22.04 的 3.10 仍有 Canonical 的补丁）。改动小，本机 3.11 的全量测试已经通过。
   部署和文档里推荐用 **3.12**（权衡后的选择：3.12 已只发源码形式的安全修复；3.13 支持更久，但还没跑过测试）。
2. **按 4.2 让 STK 能和 flwr 1.39.0 装进同一个环境**，但用的是 fastapi **区间** `>=0.138.2,<0.142`，不是精确降级：
   - 加 `fl` extra，并精确锁定 flwr；
   - 把 hub 的 uvicorn 实现显式钉死；
   - CI 同时覆盖“带 `fl`”和“不带 `fl`”两种安装。

   这样满足了所有者“同环境”的要求，又不让只装 hub 的部署被 Flower 的锁定和 cryptography 46 拖住。
3. **首批测试的部署形态**：
   - 北京、珠海、聊城三个课题组的训练节点（`suan-node`、Runtime、`fl.train`）装带 `fl` 的同一环境；
   - 思劲服务器上的 hub 不装 `fl`（继续用 fastapi 0.141.1，没有 cryptography）；
   - FL 协调进程用同一个 STK 版本的带 `fl` 安装，与 hub 同机运行，但用单独的虚拟环境或单独的进程；
   - 所有装了 `fl` 的进程都在部署配置里写死 `FLWR_TELEMETRY_ENABLED=0` 和 `FLWR_DISABLE_UPDATE_CHECK=1`，并事先向校方 IT 说明。

   等 Flower 放宽 cryptography 的锁定后，再考虑让 hub 也装 `fl`。
4. **SecAgg+ 在上游修复前不作为隐私保证**：首批测试如果要用安全聚合，自带一个修正后的掩码生成器（方案 E 的一小部分），
   所有节点和协调进程用同一版本；否则等 PR #7570 合并、各方同时升级后再启用。对合作方的说明里不要在此之前宣称 SecAgg+ 提供的保护。
5. **向 Flower 上游反映**（成本低）：
   - cryptography：在已有的 PR #7763、#7071 下留言推动，附上 OSV 的三条 HIGH 公告，而不是另开 issue；
   - SecAgg+：在 #7522 / #7570 下表明有实际用户在等修复；
   - 把服务端依赖挪进 extra：可以提，说明 A1 这类“只当算法库用”的场景不导入 fastapi、starlette、uvicorn、sqlalchemy，
     但 Flower 正在把 Runtime/Control API 改成 HTTP，不要寄望于此。
6. **`poetry.lock` 这次不动**，随旧 Qt 发布流程一起退役。是否在 `deploy/` 下放 constraints 文件，由所有者决定。

## 需要所有者决定

1. **接不接受“同环境”的实际代价**：装了 flwr 的环境里，fastapi、starlette、uvicorn 分别降到 0.138.2、1.3.1、0.49.0，
   并且引入 cryptography 46.0.7（有 3 条 HIGH 公告）。
   **建议**：接受，但仅限训练节点和 FL 协调进程；fastapi 用区间约束，不精确锁死。
2. **面向互联网的 hub 要不要也装 flwr**。
   **建议**：首批测试中不装；FL 协调进程单独跑，等 Flower 放宽 cryptography 后再合并。
3. **cryptography 46.0.7 怎么处理**：接受并记录；或者用 uv override 强制 ≥50（不受支持，pip 无法复现）；或者从源码构建 cryptography 46.0.7，
   链接系统 OpenSSL（只能修掉 OpenSSL 那一条）。
   **建议**：首批测试接受并记录，同时在上游已有的放宽 PR（#7763、#7071）下推动。
4. **SecAgg+ 掩码生成器的缺陷怎么处理**（2.5 节，#7522）：等上游 PR #7570 合并后再启用 SecAgg+；
   或在 STK 里自带修正后的掩码生成器（所有节点和协调进程必须用同一版本）；或照原样使用并记录风险。
   **建议**：修复前不把 SecAgg+ 当作对合作方的隐私保证；首批测试若需要安全聚合，自带修正版；否则先不启用，等上游合并后各方同时升级。
5. **Python 下限定 3.11 还是 3.12**。
   **建议**：下限 3.11（满足所有者决定和 flwr），推荐和默认部署用 3.12（寿命到 2028-10）。这是权衡：3.12 已只发源码形式的安全修复，
   python.org 不再提供二进制安装包；3.13 支持到 2029-10，若想改用 3.13，需先补跑一次全量测试并确认 torch 等依赖的 wheel。
6. **CI 矩阵**。
   **建议**：runtime 用 `['3.11', '3.12', '3.14']`，其中 3.11 这一条装 `fl`；client-windows 用 `['3.11', '3.12']`。
7. **锁文件**。
   **建议**：不重生成 `poetry.lock`，随旧 Qt 退役删除；为 hub 和节点两种形态在 `deploy/` 下各放一个由 `uv pip compile` 生成的 constraints 文件
   （可选，便于三个课题组得到一致的环境）。
8. **要不要向 Flower 上游反映**（cryptography 的放宽、SecAgg+ 的修复、服务端依赖挪进 extra）。
   **建议**：反映。cryptography 在已有 PR #7763、#7071 下推动；SecAgg+ 在 #7522、#7570 下推动；挪进 extra 可以提，但成功率很低。
9. **学校服务器上的 Python 3.12 从哪里来**（Ubuntu 22.04 只带 3.10；jammy-updates 里的 3.11 只是 rc1，不能用）。
   **建议**：STK 文档提供用 uv、Miniforge 或 deadsnakes 安装 3.12 的步骤，配国内镜像。具体镜像要在北京、珠海、聊城三个课题组的网络里实测。
10. **遥测与更新检查**：flwr 默认会连 Flower 的境外服务。
    **建议**：所有装 `fl` 的进程在部署配置里写死关闭，并在部署前向校方 IT 书面说明。

## 不确定之处

- **SecAgg+ 掩码问题的可利用性**：32 位种子在实际部署中能否被暴力恢复、恢复后能暴露多少单个节点的更新：未核实。
  issue #7522 和 PR #7570 的合并时间不明。1.32.1、1.39.0、main 之外的 flwr 版本是否同样如此：未逐一核实。
- **cryptography 公告的实际影响**：
  - GHSA-537c：复核时读了 secadv 20260609，唯一的 High（CVE-2026-45447，`PKCS7_verify`）不在 flwr 的调用路径上；
    但 SecAgg+ 会用 `load_pem_public_key` 解析其他参与方发来的公钥，几条 Low 级 ASN.1 解析问题会不会碰到这条路径：未核实。
  - 另外三条“不在 flwr 代码路径上”的判断，只基于对 flwr 1.39.0 源码的 grep：未核实。
- **方案 D（override）**：只验证了能解析、能安装，A1 接口能导入，密码学原语自检通过；没有跑过完整的 SecAgg+ 多轮训练。
- **测试覆盖**：
  - 本机 render 测试（15 项）因为离屏探测段错误被跳过，3.11 加 fastapi 0.138.2 下的渲染路径没有在本机验证（CI 有 EGL）。
  - Windows 客户端在 3.11 上没有在本机测试。
  - 3.13 和 3.14 只做了依赖解析，没有跑测试；torch 等依赖在 3.13 上的 wheel 可用性未核实。
- **uvicorn 0.49 的 keep-alive 缺陷**（#3107）在反向代理后面能不能触发：未核实。
- **Starlette 1.3.1 缺少 Range 加固是否构成可利用的拒绝服务**：OSV 没有公告；nginx 的 `max_ranges` 对代理响应是否生效：未核实。
- **Flower 今后的打算**：没有找到路线图。已知的是 Runtime/Control API 正在 HTTP 化，所以把服务端依赖挪进 extra 的可能性很低；
  cryptography 的放宽 PR（#7763、#7071）开着但两个多月无人处理，何时合并不明。PR #7511 虽然仍开着，但 starlette 已是核心依赖，它实际上已经过时。
- **fastapi==0.141.1 为什么被精确锁定**：没有记录，“锁定当时最新的测试版本”是推断。
- **Poetry 2.x 对 extras 的合并解析行为**：没有实测，是依据 Poetry 的常规行为判断的。
- **旧 Qt 发布流程里自托管 Windows 机器的 Python 版本**：未核实。
- **国内镜像**：只确认了索引里有相应文件，没有测速；uv 管理的 CPython 在国内怎么下载：未核实。
- **首批三个课题组（北京、珠海、聊城）服务器的操作系统和已有 Python**：未知，要在部署前收集。
- **pathspec 1.1.1 和 grpcio 的 `roots.pem` 的 MPL-2.0 义务**：需要法务确认。
- **遥测关闭后是否还有其他对外连接**：只核对了遥测和更新检查两处地址，flwr 其他代码路径有没有对外请求：未核实。
