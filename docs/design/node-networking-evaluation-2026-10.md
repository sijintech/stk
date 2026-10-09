# 课题组节点跨校园网组网方案评估

状态：**调研结论，待所有者决定；均未实现。** 上位方案：[思劲平台方向](sijin-platform-2026-10.md)“所有者决定”第 5、6、7 条。以下内容由调研整理，标“未核实”处没有一手来源；涉及法律的结论须法务确认。

日期：2026-10-08。性质：调研结论与建议，**均未实现**。对应平台方案 `docs/design/sijin-platform-2026-10.md` 第八节第 6、7 条的所有者决定
（评估类 P2P、虚拟组网、Shadowsocks 类代理；付费全文只留在客户本地，按内容寻址分块、由持有者按需提供）。
现有 hub 的行为以仓库 `docs/hub.md` 和 `suan/control/agent.py` 为准。

标注约定：**（未核实）** 表示没有找到一手来源或没有实测；版本号与日期取自 GitHub API（2026-10-08 查询）。
"直连"指两个节点之间不经第三方转发的数据路径；"中继"指经协调服务或中继服务器转发。

---

## 结论摘要

- **基础层用现有 hub，且必须先补"强制 HTTP 代理"这一缺口。** 出站 HTTPS/WSS 到协调服务在"只放行出站 TCP 443"时可用，但节点代理目前**有意禁用了代理**：
  `agent.py` 以 `connect(..., proxy=None)` 连接 WebSocket、以 `ProxyHandler({})` 上传 blob，`docs/hub.md` 也写明"不使用环境中的 HTTP 代理"。
  所用的 websockets 15.0 起本就支持经 HTTP CONNECT/SOCKS 代理连接（[changelog](https://github.com/python-websockets/websockets/blob/main/docs/project/changelog.rst)），
  因此补上显式代理配置（加可选的自定义 CA）是整份评估里成本最低、收益最高的一步。控制消息、智能体消息与联邦学习（FedAvg 本身是星形拓扑，聚合点就在协调服务）都走这一层。
- **文献共享需要第二条"不落盘"的传输路径。** hub 现有的转发是"存储再转发"（内容寻址 blob 存储），用于模型更新和开放获取文献没有问题；
  但付费全文"只留在客户本地"，经 blob 存储转发就在思劲侧留下副本。所以文献分块需要：直连，或**只转发、不存储**的中继。
  建议先在 hub 上加一个流式直通端点（同样走 443 与代理），再把直连作为优化。
- **机会性直连建议选 iroh 1.x**（Rust，MIT/Apache-2.0，2026-06-15 发布 1.0，当前 v1.3.0）：按公钥拨号，打洞失败时回落到经 HTTPS 443 的无状态中继，
  中继可自托管，有官方 Python 绑定与 C FFI。需要注意：Python/C 绑定目前没有暴露代理设置；默认预设用 n0 的公共中继与发现服务，必须换成自建中继；`iroh-blobs` 仍是 0.x。
  libp2p 不选作中继层：circuit relay v2 按设计只做打洞协调（go-libp2p 默认每条中继连接 2 分钟、128 KiB），而独立测量的打洞成功率约 70%±7.1%，剩下约三成的节点对会落到不适合 GB 级传输的中继上。
- **"类 BitTorrent"取其机制，不用 BitTorrent 协议。** 机制是：协调服务做 tracker 与授权，SHA-256 内容寻址分块，持有者（课题组的 Linux 常驻节点）按需提供，
  路径依次为同校局域网直连 → 跨校直连 → 不落盘的中继。libtorrent 在只放行 443 和强制代理的网络里两端都连不进来，BT 协议在校园网上也常被识别和限制，不作首选。
- **系统级虚拟组网与 Shadowsocks 不作为产品默认。** WireGuard 与 Nebula 只走 UDP；ZeroTier 的 TCP 回落是"最后手段"，且控制器自 1.16.0 起商业使用需另购许可；
  Tailscale/Headscale 与 NetBird 能经 443 中继，但要另建控制面和身份体系，TUN 模式在校方看来就是 VPN。由思劲为高校运营这类"闭合用户群"组网，还可能落入增值电信业务 B13（IP-VPN，需许可，须法务确认）。
  Shadowsocks 自述用途就是"帮助绕过防火墙"，不提供节点间组网，不采用。
- **直连默认关闭，按站点经校方同意后开启；校园节点不为其他机构转发流量。** 打洞会让校外节点的流量进入校内主机，与"阻断校外访问"的出口策略在意图上冲突。
  中继只部署在协调服务一侧，这样也不触碰高校"禁止开设代理类服务、禁止提供 VPN 服务功能"一类的规定（见合规一节北航承诺书原文）。

---

## 背景：三类流量与现状

| 流量 | 规模与形态 | 是否需要节点间直连 |
|---|---|---|
| (a) 联邦学习轮次 | 每轮每节点上传模型更新（MB–GB），下发全局模型 | 基本不需要：FedAvg/FedProx 的聚合点就是协调服务，直连省不了协调服务的流量。除非将来做分层聚合或去中心化（gossip）训练 |
| (b) 文献 PDF 共享 | 单篇 MB 级，持有者少、请求零散；受所有者决定第 7 条约束（付费全文不集中存放） | 需要"持有者 → 请求者"的路径，且不能在思劲侧落盘 |
| (c) 控制与智能体消息 | 小消息、低时延、需要可靠在线 | 不需要，星形最合适 |

现有 hub：节点**主动出站**以 WSS 连入 `suan-control`，结果以内容寻址 blob 经 HTTPS `PUT` 上传，客户端上传支持 8 MiB 分块续传，
有配对码、设备吊销、复核策略与操作记录（见 `docs/hub.md`）。节点代理的 blob 上传是整块 `PUT`，受 `--blob-max-mib`（默认 512）限制，GB 级模型更新需要扩展成分块续传。

---

## 对照表

### 表一：可达性与嵌入

| 方案 | 只放行出站 TCP 443 | 另有强制 HTTP 代理 | 有 UDP 时的直连 | 权限与嵌入方式 | 平台 |
|---|---|---|---|---|---|
| 现有 hub（WSS + HTTPS） | ✅ | ⚠️ 代码禁用了代理，改配置即可（websockets ≥15、httpx 都支持） | 无（全部经 hub） | 普通进程，Python 已在用；桌面经桥接 | 节点 Linux；客户端三平台 |
| iroh 1.x | ✅ 中继走 HTTPS/WebSocket 443 | ⚠️ Rust 有 `proxy_url`/`proxy_from_env`；Python/C 绑定未暴露 | ✅ QUIC 打洞（厂商称约九成，未独立核实） | 用户态库，无 TUN；Python wheel、C FFI、Rust | Win/macOS(arm64 wheel)/Linux |
| libp2p（go/rust/py） | ⚠️ 需自建 WSS 中继，且 v2 默认限额 | ⚠️ go 的 WebSocket 传输读 `HTTPS_PROXY`；rust/py 未核实 | ✅ DCUtR 测得约 70% | 用户态库；py-libp2p 不成熟，实际要 Go/Rust 侧车 | 三平台 |
| WebRTC 数据通道（aiortc / libdatachannel + coturn） | ✅ TURN over TLS 443 | ❌ aiortc 无代理；libdatachannel 仅在 libnice 后端支持（仅无认证 HTTP 代理） | ✅ ICE | 用户态；aiortc 纯 Python；libdatachannel C++ | 三平台 |
| libtorrent | ❌ 双方都在 NAT 后时 TCP 连不上，无中继 | ❌ 配代理后不接受入站连接，uTP 不能经 HTTP 代理 | ⚠️ 依赖入站端口或 UPnP | C++ 库，有 Python 绑定 | 三平台 |
| WireGuard（原生） | ❌ 只用 UDP | ❌ | ⚠️ 需静态端点或一端有公网入站 | 内核模块或 wireguard-go + TUN，需 root/管理员 | 三平台 |
| Tailscale 客户端 / tsnet + Headscale | ✅ DERP 经 HTTPS 443 | ✅ DERP 支持 HTTP CONNECT（含认证头） | ✅ 成熟的 NAT 穿透；对端用 UDP | tailscaled 需 TUN；tsnet（Go）用户态；libtailscale C 库，Python 包 0.0.1 | 三平台 |
| ZeroTier（自建控制器） | ⚠️ TCP 回落官方称"慢、最后手段"，可自建 TCP 中继 | 未核实 | ✅ UDP 9993 | ZeroTier One 需 TUN；libzt 用户态 | 三平台 |
| Nebula | ❌ 数据面与中继都走 UDP | ❌ | ✅ 灯塔协助打洞 | 需 TUN | 三平台 |
| NetBird | ✅ 新中继 WebSocket 回落"可经 443" | 未核实 | ✅ ICE（pion） | 守护进程需 TUN；`client/embed`（Go）用 netstack 用户态 | 三平台 |
| Shadowsocks | ✅（客户端 → 自建服务器） | 与本需求无关 | ❌ 不提供节点间组网 | 代理进程或 TUN | 三平台 |

### 表二：管理、商业与观感

| 方案 | 控制面自托管（离线/本地） | 身份、加密、访问控制、审计 | GB 级吞吐 | 闭源商业分发许可 | 成熟度 | 运维负担 | 校方观感 |
|---|---|---|---|---|---|---|---|
| 现有 hub | ✅ 本来就自托管 | TLS；配对码、设备令牌、吊销、复核策略、操作记录 | 取决于协调服务带宽；中继时每字节进出各一次 | 自有代码 | 已在用 | 低（已有） | 普通 HTTPS 应用，最好沟通 |
| iroh 1.x | ✅ 自托管无状态中继；地址交换可交给 hub | 节点密钥即身份，QUIC/TLS 端到端加密；中继有 `AccessControl`；授权与审计需自建 | QUIC，直连好；中继受中继主机带宽限制（无公开数据，未核实） | MIT/Apache-2.0（ffi 同；c-ffi Apache-2.0） | 1.0 仅四个月；公共中继限速 | 中：多一个中继服务 | 应用级连接；打洞需说明 |
| libp2p | ✅ 自建中继节点 | Peer ID 即身份，Noise/TLS；访问控制靠自写 gater | 直连好；默认中继不适合 | MIT（go/rust），py 为 MIT/Apache | go/rust 成熟（IPFS、以太坊客户端）；py "under development" | 中高：协议栈大 | 应用级；可能被识别为 P2P（未核实） |
| WebRTC | ✅ coturn 自托管，信令走 hub | DTLS；TURN 凭据；授权与审计自建 | 原生实现可用；aiortc 纯 Python 预计偏低（未实测） | aiortc BSD-3；libdatachannel/libjuice MPL-2.0；coturn BSD-3 | 成熟（视频会议） | 中：TURN 服务与证书 | 常见流量（会议类），好沟通 |
| libtorrent | ✅ 自建 tracker；可关 DHT/LSD | SSL torrent：对端证书须由种子内 CA 签发 | 多对多分发最强 | BSD 3-clause 为主；Python 绑定 BSL-1.0；个别文件带广告条款（见下） | 很成熟 | 中 | **差**：BT 常被校园网限制 |
| WireGuard | 无控制面，手工配置 | 公钥身份，无 ACL/审计 | 极好（内核约 11.8 Gb/s 量级） | 内核 GPLv2；wireguard-go MIT；Wintun 预编译 DLL 另有许可（未读原文） | 很成熟 | 高（手工密钥与地址） | VPN |
| Tailscale/Headscale | ✅ Headscale；另需 derper | 节点密钥＋用户/OIDC；ACL/grants；Headscale 日志 | 直连好；DERP 中继为 TCP 套 TCP | 客户端与 Headscale BSD-3；macOS/Windows GUI 外壳不开源 | 客户端很成熟；Headscale "单 tailnet"、面向个人与小组织 | 中高：控制面、DERP、版本兼容 | TUN 模式即 VPN；tsnet 嵌入则是应用级 |
| ZeroTier | ⚠️ 控制器商业使用需另购许可 | 网络 ID＋成员授权，规则引擎 | UDP 直连好；TCP 回落慢 | 代理端 MPL-2.0；控制器非开源；libzt 许可见下 | 成熟 | 中 | VPN |
| Nebula | ✅ 自建 CA 与灯塔 | 证书身份、组、组防火墙（模型最清晰） | 好（UDP） | MIT | 成熟（Slack 出品） | 中 | VPN |
| NetBird | ✅ 管理、信令、中继 | WireGuard 密钥＋IdP；ACL；活动日志 | 直连好 | 客户端 BSD-3；管理/信令/中继 AGPL-3.0 | 活跃（v0.80） | 中高：需 IdP | VPN（嵌入除外） |
| Shadowsocks | ✅ | 预共享密钥；无身份与访问控制 | 不适用 | rust 版 MIT；libev 版 GPL-3.0 | 成熟 | — | **高风险**：翻墙工具 |

---

## 各方案说明

### 4. 现有 hub：出站 WSS + 经协调服务中继（基础层）

- **在严格校园网下**：只要出站 443 放行、协调服务域名可解析，就能工作；不需要入站端口。节点每 3 秒发快照，hub 30 秒无消息即断开，长连接空闲超时问题不大。
- **失败模式**：
  1. **强制 HTTP 代理**：现在直接失败（代码禁用代理）。补救：节点与桌面桥接加显式 `--proxy http://user:pass@host:port`（不建议默认读环境变量，以免意外经过未知代理），
     WebSocket 用 websockets 的 `proxy=` 参数，blob 上传改用带代理的 opener 或 httpx `proxy=`。
  2. **TLS 检查（中间人）代理**：校方用自己的根证书解密 HTTPS 时，标准 TLS 校验失败。补救：提供"信任指定 CA 文件"的选项并在界面上明示，不做静默降级。
     Tailscale 的 DERP 客户端源码也只说"这种情况下一切都不保证"（[derphttp_client.go](https://github.com/tailscale/tailscale/blob/main/derp/derphttp/derphttp_client.go)）。
  3. **代理限制请求体或时长**：用分块续传（已有 8 MiB 分块的客户端上传协议），把节点的整块 `PUT` 也改成分块。
  4. **校园网出口认证（Web 认证门户）**：实验室服务器的外网访问可能需要登录且会过期（未核实，需逐校询问），应在诊断工具里能识别出来。
- **中继语义**：现在是"存储再转发"——blob 有配额、GC 与磁盘下限，适合模型更新与开放获取文献；**不适合付费全文**（所有者决定第 7 条）。需要新增一个**流式直通端点**：
  请求者与持有者各自以出站 HTTPS 连到 hub，hub 把持有者的上传流直接写给请求者，不写盘，只记录元数据（谁、哪个哈希、多少字节、何时）。
- **吞吐**：经 hub 的每个字节进出协调服务各一次；GB 级联邦学习更新反正要送到聚合点，这部分不算额外成本。
- **嵌入**：Python 已在用；C++ 桌面经现有桥接。

### iroh 1.x（建议的机会性直连层）

- **来源**：[仓库](https://github.com/n0-computer/iroh)（README：Apache-2.0 或 MIT 任选，[LICENSE-APACHE](https://github.com/n0-computer/iroh/blob/main/LICENSE-APACHE)、[LICENSE-MIT](https://github.com/n0-computer/iroh/blob/main/LICENSE-MIT)）；
  [1.0 发布说明](https://iroh.computer/blog/v1)（2026-06-15："Iroh version 1.0 asserts stability for both the wire protocol and language APIs"，官方支持 Python、Node.js、Swift、Kotlin）；最新 v1.3.0（2026-09-28）。
- **工作方式**：按公钥拨号，先试直连，必要时打洞，失败则回落到中继；中继"无状态"、"cannot read any of the traffic"（[relays 文档](https://docs.iroh.computer/concepts/relays)）。
  中继协议是 HTTP 升级为 WebSocket（[iroh-relay/src/http.rs](https://github.com/n0-computer/iroh/blob/main/iroh-relay/src/http.rs)），默认 HTTPS 端口 443，另有 QUIC 端口 7842 用于地址发现
  （[defaults.rs](https://github.com/n0-computer/iroh/blob/main/iroh-relay/src/defaults.rs)）；1.0-rc1 说明中继可挂在自己的 HTTP 服务器里，并新增 `AccessControl` 用于吊销后断开客户端
  （[rc1 博客](https://iroh.computer/blog/iroh-1-0-0-rc-1)）。
- **代理**：Rust 的 `Endpoint` 构建器有 `proxy_url()` 与 `proxy_from_env()`（[endpoint.rs](https://github.com/n0-computer/iroh/blob/main/iroh/src/endpoint.rs)），但默认预设不启用；
  [iroh-ffi 的 endpoint.rs](https://github.com/n0-computer/iroh-ffi/blob/main/src/endpoint.rs) 没有暴露代理设置，[iroh-c-ffi](https://github.com/n0-computer/iroh-c-ffi)（0.101.0，依赖 iroh 1.0.0）的 `src/*.rs` 中也没有代理代码，即 **Python 节点与 C++ 桌面目前都不能让 iroh 中继走强制代理**（以 2026-10 的 main 分支为准）。
  这正是需要 hub 直通端点兜底的原因之一。
- **默认值风险**：`preset_n0` 使用 n0 的公共中继与发现服务，公共中继"rate-limited"（1.0 发布说明）。部署时必须用 `preset_minimal`＋自建中继（RelayMap），节点地址经 hub 交换，不依赖境外服务。
- **嵌入**：Python 用 PyPI `iroh`（wheel 覆盖 Windows amd64、manylinux x86_64/aarch64、macOS arm64，[README.python.md](https://github.com/n0-computer/iroh-ffi/blob/main/README.python.md)；无 macOS x86_64）。
  C++ 桌面可用 [iroh-c-ffi](https://github.com/n0-computer/iroh-c-ffi)（Apache-2.0），或静态链接一个 Rust 小库。FFI 只覆盖 1.0 的端点/连接层，
  `iroh-blobs`（v0.103.0）"out of scope"（[iroh-ffi README](https://github.com/n0-computer/iroh-ffi)）——要么用 Rust 侧车跑 iroh-blobs，要么在 Python 里用 iroh 的 QUIC 流实现自己的分块协议（推荐后者，与 hub 的 SHA-256 寻址一致）。
- **成功率**：厂商称打洞"roughly nine times out of ten"、"95% of data … pass directly"（前者见[二手报道](https://www.techtimes.com/articles/318490/20260616/peer-peer-library-iroh-10-ships-dial-devices-key-not-ip-address.htm)，**未独立核实**）。
  独立测量只有 libp2p 的约 70%（见下），校园网的硬 NAT 比例未知，应在试点中自测。
- **失败模式**：UDP 被封 → 只能用中继；中继要强制代理而又是 Python 节点 → 走 hub 直通端点；1.x 年轻，有社区反馈回归问题（二手，未核实）。

### libp2p（go-libp2p / rust-libp2p / py-libp2p）

- **许可**：go-libp2p MIT（[README](https://github.com/libp2p/go-libp2p)，v0.50.0），rust-libp2p MIT（v0.57.0），py-libp2p MIT/Apache 双许可（v0.8.0，描述为"[under development]"，WebRTC/WebTransport 标为原型，[README](https://github.com/libp2p/py-libp2p)）。
- **打洞**：大规模测量（4.4 百万次尝试、8.5 万个网络）得到"70% ± 7.1%"，且"statistically indistinguishable success rates for both TCP and QUIC"（[arXiv 2510.27500](https://arxiv.org/abs/2510.27500)，IMC '26）。
- **中继 v2 的定位**：规范称"limited relays"用于支持打洞，"doesn't require an unlimited relay connection"（[circuit-v2 规范](https://github.com/libp2p/specs/blob/master/relay/circuit-v2.md)）；
  go-libp2p 默认 `Duration: 2 * time.Minute`、`Data: 1 << 17 // 128K`（[resources.go](https://github.com/libp2p/go-libp2p/blob/master/p2p/protocol/circuitv2/relay/resources.go)）。
  限额可设为 0（无限制），但那样就是自己运营一个通用中继，且约三成打洞失败的节点对的全部数据都会经过它。
- **代理**：go 的 WebSocket 传输"If an HTTPS_PROXY env is set, it will use that for the dial out"（[websocket.go](https://github.com/libp2p/go-libp2p/blob/master/p2p/transport/websocket/websocket.go)）；rust/py 未核实。
- **嵌入**：Python 节点实际要用 Go/Rust 侧车；C++ 桌面无官方 C 绑定（未核实）。协议栈大（multiaddr、identify、AutoNAT、DCUtR、relay、多路复用），只为点对点传文件显得重。
- **结论**：可作 iroh 的备选，不作首选。

### WebRTC 数据通道（ICE/STUN/TURN；aiortc、libdatachannel、coturn）

- **许可**：aiortc 与 aioice BSD-3-Clause（GitHub API）；libdatachannel "licensed under MPL 2.0 since version 0.18"（[README](https://github.com/paullouisageneau/libdatachannel)，v0.24.6）；
  libjuice MPL-2.0；coturn 为 BSD 三条款（[LICENSE](https://github.com/coturn/coturn/blob/master/LICENSE)）。
- **443 与代理**：aiortc 支持 `turn:`（UDP/TCP）与 `turns:`（TLS over TCP）（[rtcicetransport.py](https://github.com/aiortc/aiortc/blob/main/src/aiortc/rtcicetransport.py)），可用 coturn 在 443 上做 TURN-TLS；
  aioice 的 TURN 客户端没有 HTTP 代理支持（[turn.py](https://github.com/aiortc/aioice/blob/main/src/aioice/turn.py) 中无代理代码）。
  libdatachannel 默认 ICE 后端 libjuice "Only UDP is supported as transport protocol"（[libjuice README](https://github.com/paullouisageneau/libjuice)）；
  `TurnTcp`/`TurnTls` 与代理选项在 [configuration.hpp](https://github.com/paullouisageneau/libdatachannel/blob/master/include/rtc/configuration.hpp) 中注明"libnice only"、"only non-authenticated http supported for now"，需换 libnice 后端（libnice 许可未核实）。
- **吞吐**：SCTP over DTLS 本为实时数据设计；aiortc 是纯 Python 实现，GB 级传输的吞吐预计明显低于原生实现（**未找到数据，需 PoC 实测**）。
- **优点**：信令可直接走现有 hub；TURN-over-TLS-443 在校方看来与视频会议相同。**缺点**：Python 侧无代理、ICE/DTLS/SCTP 复杂度高、桌面要换后端才能走 TCP。
- **结论**：可行但不如 iroh 简洁；若将来需要与浏览器互通再考虑。

### libtorrent（BitTorrent）

- **许可**：主体为 BSD 三条款（[LICENSE](https://github.com/arvidn/libtorrent/blob/RC_2_0/LICENSE)），Python 绑定 `bindings/python/src/` 为 Boost Software License 1.0；
  `include/libtorrent/_aux/route.h` 含 Apple Public Source License 2.0 与带广告条款的四条款 BSD 声明——闭源分发前应确认该文件是否编入以及广告条款的义务（**未核实**）。v2.1.2（2026-09-25）。
- **访问控制**：SSL torrent 要求双方证书"signed by the CA certificate found in the .torrent file"，SNI 为 info-hash；可关闭 DHT/LSD（[manual](https://libtorrent.org/manual-ref.html)）。BitTorrent v2 用 SHA-256 merkle 树。
- **严格网络下的失败模式**：HTTP 代理类型对非 HTTP 连接使用 CONNECT，但配置代理后"this interface does not accept incoming TCP connections"，即**两个都经代理的节点无法互连**；
  uTP 只能经 SOCKS5 UDP ASSOCIATE，不能经 HTTP 代理（[settings 参考](https://www.libtorrent.org/reference-Settings.html)）。没有中继机制，双方都在 NAT 后且无入站端口时连不上。
  web seed（BEP 19）可指向 hub，但那等于在 hub 存副本，与第 7 条冲突。
- **校方观感**：P2P/BT 常被列为"原则禁止、例外开放"，例如台湾清华大学在校园骨干网限制 P2P 协议、学术需要须申请例外（[NTHU P2P 管理](https://net.nthu.edu.tw/netsys/en:network:p2p_policy)）；
  大陆高校的成文规定本次未找到原文（未核实），但上网行为管理设备通常能识别 BT 协议。
- **结论**：PDF 为 MB 级、持有者少，多对多分发的优势用不上；不作首选。只在同一机构的内网、经校方批准时可以考虑。

### WireGuard（原生）

- UDP 专用："WireGuard explicitly does not support tunneling over TCP"，混淆应在上层做（[known limitations](https://www.wireguard.com/known-limitations/)）。没有发现、打洞与控制面，需要 TUN 与管理员权限。
- 许可：wireguard-go MIT（GitHub API）；内核实现随 Linux（GPLv2）；Windows 的 Wintun 源码 GPL-2.0，预编译 DLL "released under a more permissive license"、"may be distributed with your software"（[wintun.net](https://www.wintun.net/)，许可原文在 ZIP 中，**未读**）；boringtun BSD-3（最后一次发布 2022 年）。
- 吞吐：Tailscale 测得内核 WireGuard 11.8 Gb/s、wireguard-go 加卸载后 13.0 Gb/s（裸机，[博客 2023-04](https://tailscale.com/blog/more-throughput)）。
- **结论**：只是构件。只放行 TCP 443 时不可用；校方视为 VPN。

### Tailscale（tsnet / libtailscale）＋ 自建 Headscale

- **许可**：[tailscale 仓库](https://github.com/tailscale/tailscale/blob/main/LICENSE) BSD-3-Clause；README 写明 macOS/Windows 客户端的"GUI wrappers on non-open source platforms are themselves not open source"。
  [Headscale](https://github.com/juanfont/headscale) BSD-3-Clause（v0.29.4），"implements a narrow scope, a _single_ Tailscale network (tailnet)"，面向个人与小型开源组织。
- **443 与代理**：DERP 客户端在 TLS 443 上以 `Upgrade: DERP` 或 WebSocket 连接，并可经 HTTP 代理 `CONNECT`（含 `Proxy-Authorization`）
  （[derphttp_client.go](https://github.com/tailscale/tailscale/blob/main/derp/derphttp/derphttp_client.go)）。这是各组网方案里对强制代理支持最完整的。该功能受构建标签控制，默认构建包含（`//go:build !ts_omit_useproxy`，[feature_useproxy_enabled.go](https://github.com/tailscale/tailscale/blob/main/feature/buildfeatures/feature_useproxy_enabled.go)），但钩子在 `feature/useproxy` 包初始化时才注册，tsnet 是否默认引入该包**未核实**。
  Peer relays 走 UDP（[KB 1591](https://tailscale.com/kb/1591/peer-relays)），对只放行 TCP 的网络没有帮助。
- **嵌入**：[tsnet](https://tailscale.com/kb/1244/tsnet) 是 Go 库、用户态网络栈，`ControlURL` 可指向 Headscale（[tsnet.go](https://github.com/tailscale/tailscale/blob/main/tsnet/tsnet.go)）；
  [libtailscale](https://github.com/tailscale/libtailscale)（BSD-3）以 Go c-archive 提供 C 接口，其 Python 包版本为 0.0.1。实际做法是 Go 侧车，或 `tailscaled` 用户态模式加本地 SOCKS5（[KB 1112](https://tailscale.com/kb/1112/userspace-networking)，本次抓取失败，**未核实**细节）。
- **Headscale 功能**：嵌入式 DERP、ACL/grants、OIDC（"OIDC groups cannot be used in ACLs"）、tags、peer relays 等（[features](https://headscale.net/stable/about/features/)）。
- **代价**：多一个控制面（Headscale＋数据库＋可选 OIDC）、一个 derper（STUN 用 UDP 3478）；身份体系与 STK 配对码各自独立，需要映射；还要跟进客户端与 Headscale 的版本兼容。
- **结论**：NAT 穿透最成熟。如果 iroh 试点不理想，这是最强备选，但只用 tsnet 嵌入、不装系统级 tailscaled。

### ZeroTier（自建控制器）

- **许可（以仓库文件为准）**：[LICENSE.txt](https://github.com/zerotier/ZeroTierOne/blob/dev/LICENSE.txt) 规定 node/、osdep/、service/ 等为 MPL-2.0，`nonfree/` 另行许可；
  1.16.0（2025-08-21）起"The network controller (`controller/`) is now under a commercial source-available license"（[RELEASE-NOTES](https://github.com/zerotier/ZeroTierOne/blob/dev/RELEASE-NOTES.md)）。
  [nonfree/LICENSE.md](https://github.com/zerotier/ZeroTierOne/blob/dev/nonfree/LICENSE.md)："ANY COMMERCIAL USE OF THIS SOFTWARE REQUIRES A SEPARATE COMMERCIAL LICENSE"，商业使用包括"Use in a production, staging, or development environment for business purposes"，
  且"not 'open source'"。**思劲自建控制器即属商业使用，需另购许可。**
- **libzt**：README 称"licensed under the BSL version 1.1"；[LICENSE.txt](https://github.com/zerotier/libzt/blob/master/LICENSE.txt) 的 Additional Use Grant 禁止"Link or directly include the Licensed Work in a commercial or for-profit application"（除非以 OSI 许可发布），
  Change Date 2026-01-01、Change License Apache-2.0。该日期已过，但 BSL 的转换按版本计算、libzt 又包含 ZeroTier 核心代码，**能否据此闭源商用须法务确认**；libzt 没有 GitHub release，最后提交 2026-07-30。
- **严格网络**：主要走 UDP；TCP 回落"This relay service is slow"，可自建 pylon 中继并设置 `tcpFallbackRelay`（[relay 文档](https://docs.zerotier.com/relay/)）；论坛称回落是"last resort"、切换可能要几分钟（单个用户报告）。
- **结论**：不推荐（控制器许可＋TCP 回落弱）。

### Nebula

- MIT（[仓库](https://github.com/slackhq/nebula)，v1.11.2）。证书断言节点 IP、名字与组，组防火墙"similar in style to cloud security groups"——身份与访问控制模型最清晰。
- 数据面默认 UDP 4242；中继自 1.6.0 起提供，要求"firewall rules that permit Nebula's UDP traffic inbound"（[relay 文档](https://nebula.defined.net/docs/config/relay/)），没有 TCP 回落；需要 TUN。
- **结论**：只放行 TCP 443 时不可用。其"证书＋组＋组防火墙"模型可作为我们节点授权设计的参考。

### NetBird

- **许可**：README："licensed under the BSD-3-Clause license … except for the directories management/, signal/ and relay/"，这三个目录为 AGPL-3.0（[仓库](https://github.com/netbirdio/netbird)，v0.80.0）。
  客户端可闭源嵌入；服务端若交付给本地客户，需按 AGPL 提供源码，修改也须公开给网络用户。
- **严格网络**：ICE（pion）打洞；v0.29.0 起的新中继以 QUIC 为主、WebSocket 回落，"works over port 443"（[NAT 文档](https://docs.netbird.io/about-netbird/understanding-nat-and-connectivity)）。
  但[自托管高级指南](https://docs.netbird.io/selfhosted/selfhosted-guide)仍列出中继端口 33080 与 Coturn（UDP 3478、49152–65535），文档前后不一致（未核实当前版本）。客户端是否支持强制 HTTP 代理：未核实。
- **嵌入**：`client/embed` Go 包会设置 netstack 用户态模式（[embed.go](https://github.com/netbirdio/netbird/blob/main/client/embed/embed.go)），仍是 Go，需要侧车。管理面需要 IdP（OIDC）。
- **结论**：开源组网里功能最全的之一，但 AGPL 服务端、额外的 IdP 与控制面，对一个"应用内数据通道"的需求来说太重。

### 3. Shadowsocks 类代理

- **它是什么**：shadowsocks-rust 自述"a fast tunnel proxy that helps you bypass firewalls"（[README](https://github.com/shadowsocks/shadowsocks-rust)，MIT；shadowsocks-libev GPL-3.0）。
  模式是本地 SOCKS5/HTTP/透明代理/TUN → 自建服务器；设计重点是让流量难以识别。
- **能否组网**：不能。它没有节点发现、打洞或节点间寻址，NAT 后的节点仍然无法被访问；能提供的只是"客户端经加密隧道到一台服务器"，这一点现有 hub 的 TLS 连接已经做到，而且有身份与审计。
- **合规**：设计目标就是规避网络管控，与校方出口策略、32 号文和国际联网规定的指向正面冲突；高校的开放端口承诺书也明确禁止代理类服务与 VPN 服务（见合规一节）。**不采用。**

---

## 推荐方案

```mermaid
flowchart LR
  subgraph CampusA[课题组 A（校园网）]
    NA[节点代理 + 文献库]
  end
  subgraph CampusB[课题组 B（校园网）]
    NB[节点代理 + 文献库]
  end
  subgraph Sijin[思劲或客户自建：ICP 备案域名]
    Hub[协调服务 hub：控制、聚合、索引与授权、直通中继]
    Relay[iroh-relay：无状态，443]
  end
  NA -->|L0 出站 HTTPS/WSS，可经 HTTP 代理| Hub
  NB -->|L0 出站 HTTPS/WSS，可经 HTTP 代理| Hub
  NA -.->|L1 可选：经校方同意| Relay
  NB -.->|L1 可选：经校方同意| Relay
  NA <-.->|L1 直连（QUIC 打洞）| NB
```

### L0 基础通道（必做，S4 之前）

1. **代理与证书**：节点代理与桌面桥接支持显式 HTTP CONNECT 代理（含用户名密码）与"信任指定 CA"；WebSocket 用 websockets 的 `proxy=`，HTTP 用 httpx `proxy=`。默认仍不读环境变量。
2. **连通性诊断**（例如 `suan-node doctor`）：DNS、TCP 443、TLS 证书链（识别中间人代理）、代理、WebSocket 升级、到中继的 UDP 可达性。输出给校方网管看的报告。
3. **大文件**：节点到 hub 的 blob 上传改为分块续传（复用客户端上传协议），hub 到节点的下载用 Range 续传。
4. **联邦学习走 L0**：每轮的模型更新以内容寻址 blob 上传到聚合点，全局模型以 blob 下发；轮次记录"离开本组的是什么"（摘要哈希、大小、时间）。
   若选 Flower：SuperNode 是 gRPC 客户端、只需出站连接（[网络通信文档](https://flower.ai/docs/framework/1.20/en/_sources/ref-flower-network-communication.rst.txt)），默认端口 9092 需改由 443 上的反向代理（如 nginx `grpc_pass`）提供；
   gRPC C-core 读取 `grpc_proxy`/`https_proxy`（[gRPC 文档](https://github.com/grpc/grpc/blob/master/doc/core/default_http_proxy_mapper.md)）。或者按平台方案第 5.4 节，把 Flower 消息放进 STK 已认证的出站通道。
5. **直通中继端点（为文献）**：hub 在请求者与持有者之间转发字节流，不写盘，只记元数据；带每设备并发与速率上限。这样在只有 443＋强制代理的校园也能共享，并满足第 7 条。

### L2 文献共享机制（S5，与 L0 一起即可上线）

- **索引与授权在 hub**：`sha256 → {持有节点, 文献元数据, 许可类别}`；按所有者决定第 7 条，默认只对开放获取文献与同一机构内启用，跨机构共享付费全文待法律确认。
- **持有者是课题组的 Linux 常驻节点**，不是笔记本：按需提供要求在线，桌面客户端把 PDF 交给本组节点（同一局域网或经 hub），自己只作请求方。这样 C++ 桌面不需要内置 P2P 协议栈。
- **分块与校验**：文件按固定大小（如 4 MiB）分块，清单列出每块 SHA-256 与整文件 SHA-256（与 hub 现有寻址一致）；接收方逐块校验，可从多个持有者并行取块。这就是"类 BitTorrent"的部分。
- **路径顺序**：同校局域网直连 → L1 跨校直连（若已启用）→ L0 直通中继。开放获取文献可以另外缓存在 hub 的 blob 存储里。
- **审计**：每次传输记录请求者、持有者、哈希、字节数、路径（直连/中继）与授权依据，供课题组与校方查看。

### L1 机会性直连（S5 之后，按站点启用）

- **库**：iroh 1.x。节点用 Python `iroh` 包，`preset_minimal`＋自建 RelayMap，节点 ID（公钥）登记在 hub 的设备记录里，对端地址经 hub 交换；只接受 hub 授权名单中的节点 ID。
  在 iroh 的 QUIC 流上实现上面的分块协议。`iroh-blobs` 到 1.0 且进入 FFI 后再评估是否替换。
- **中继**：自建 `iroh-relay`，独立主机名、443（经 nginx 转发 WebSocket 升级或独立监听），可选开放 UDP 7842；有访问控制，只服务已配对节点。
  Python 绑定没有代理设置，强制代理的站点直接用 L0，不必启用 L1。
- **为什么是 iroh**：应用层连接（无 TUN、无 IP 层），身份就是密钥、容易绑定到现有配对；只多一个无状态中继，而不是一整套控制面（Headscale/NetBird）；中继走 HTTPS 443，协议上没有每连接的时长与字节限额（不同于 libp2p v2 默认的 2 分钟、128 KiB；自建中继的实际吞吐仍需实测）；
  MIT/Apache 许可适合闭源分发；有官方 Python 与 C 绑定。
- **风险与备选**：1.x 只有四个月；Python 绑定无代理；硬 NAT 比例未知。试点不理想时，备选依次为 tsnet 侧车＋Headscale（只用 DERP 与直连，不装 TUN），或 go-libp2p 侧车＋自建不限额中继。
- **对 L0 的影响**：联邦学习不依赖 L1；L1 只用于文献分块与将来的节点间大文件交换。

### 需要校方网络管理批准的事项

1. 节点服务器出站 TCP 443 到协调服务域名（例如 `hub.<域名>`），该域名已办 ICP 备案；如必须经代理，提供代理地址与认证方式。
2. （仅启用 L1 时）出站 TCP 443 到中继域名（例如 `relay.<域名>`），以及可选的出站 UDP（到中继的 7842 端口和到其他合作节点的 QUIC），说明这会产生由本机发起、对端回应的 UDP 流。
3. （仅同校共享时）研究服务器在**校内**开放一个固定端口，供同校节点直连；不对校外开放。
4. 不需要：入站公网端口、TUN/VPN 虚拟网卡、管理员级网络驱动；节点**不为任何其他机构转发流量**，不提供代理或 VPN 服务。
5. 可审计：节点本地保留连接与传输日志，协调服务按法规保留日志，校方可索取；提供一页说明"离开本校的数据是什么"（模型更新、开放获取元数据、经授权的文献分块），以及按数据集逐个授权与随时退出的机制。
6. 如校园网对实验室服务器有出口认证（Web 认证门户）或流量计费，请网管为该服务器配置免认证或长期认证，并确认计费方式（各校做法不同，未核实）。

---

## 合规与校方沟通要点

- **跨境专线与 VPN**：工信部《关于清理规范互联网网络接入服务市场的通知》（工信部信管函〔2017〕32 号）："未经电信主管部门批准，不得自行建立或租用专线（含虚拟专用网络VPN）等其他信道开展跨境经营活动。"
  国际专线"仅供其内部办公专用"（[网信办转载原文](https://www.cac.gov.cn/2017-01/23/c_1120366809.htm)）。
  《计算机信息网络国际联网管理暂行规定》第六条要求直接国际联网使用国家公用电信网的国际出入口信道，"任何单位和个人不得自行建立或者使用其他信道进行国际联网"（国务院令第 195 号，1997 年修正，[网信办](https://www.cac.gov.cn/1996-02/02/c_126468621.htm)；此后是否另有修订**未核实**）。
  含义：面向中国高校的协调服务与中继建议部署在境内；节点经公共互联网以 TLS 连到思劲的服务属于普通互联网访问，不应搭建或使用跨境隧道。
- **虚拟专用网业务许可**：《电信业务分类目录（2015 年版）》B13 国内互联网虚拟专用网业务（IP-VPN）是"利用自有或租用的互联网网络资源，采用TCP/IP协议，为国内用户定制互联网闭合用户群网络的服务"，
  "主要采用IP隧道等基于TCP/IP的技术组建"（[目录全文转载](https://www.elawcn.com/telecommunication/2019/1130/498.html)）。
  思劲若为高校运营 Headscale/ZeroTier/NetBird 一类的组网控制面，可能被视为这类增值电信业务；应用自身的 TLS 连接一般不属于此类。**须法务确认。**
- **日志留存**：《网络安全法》（2025 年修正）第二十三条第（三）项要求"按照规定留存相关的网络日志不少于六个月"（[网信办全文](https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm)；修正案施行日期按检索结果为 2026-01-01，**未在该页核实**）。
  协调服务与中继作为网络运营者应满足；同时，系统级隧道会让校方出口设备看不到隧道内流量，应用级 TLS 连接到已备案域名至少保留了可记录的连接信息，这一点对校方更容易接受。
- **ICP 备案**：阿里云帮助称"中国内地服务器必须在服务器所属接入商平台完成备案"、"ICP备案不区分端口号"；境外或香港服务器无需 ICP 备案，但在内地可访问的仍须在开通后 30 天内办理公安联网备案（[阿里云帮助](https://help.aliyun.com/document_detail/61819.htm)）。协调服务和中继的域名都要备案，客户自建时由客户办理。
- **数据出境**：若协调服务在境外或有境外参与方，适用《促进和规范数据跨境流动规定》（2024-03-22 公布施行，[网信办](https://www.cac.gov.cn/2024-03/22/c_1712776611775634.htm)）。
  学术合作中产生且不含个人信息或重要数据的数据可免于申报，但需先判断模型更新与数据集是否涉及重要数据目录。
- **高校规定的实例**：北航《校园网开放主机端口安全责任承诺书》写明出口防火墙"对于非特殊需要的主机，禁止校园网外的一切访问"，开放端口的主机"禁止开设代理类服务……不得为校外用户提供代理类服务"、
  "禁止提供虚拟专用网络（VPN）服务功能"（[原文 docx](https://nic.e1.buaa.edu.cn/kaifangzhujiduankouanquanzerenchengnuoshu.docx)）。
  据此：节点不做中继、不做代理；打洞直连要事先说明并取得同意，因为它让校外节点的流量进入校内主机，与"禁止校园网外的一切访问"在意图上冲突，尽管技术上是由本机先发起。
- **沟通口径**：这是一个只做出站 HTTPS 的科研应用，连接固定的、已备案的域名；不建虚拟网卡、不转发他人流量、不规避检测；离开本校的内容可列清单、可审计、可随时停止。

---

## 不确定之处

1. **校园网实际条件**：首批课题组的出口是否只放行 443、是否有强制代理或 TLS 检查、UDP 是否限速、是否有 Web 认证门户，以及 NAT 类型（硬 NAT 比例决定直连成功率）——需要逐校询问并用诊断工具实测。CERNET 与商业运营商之间的带宽也需实测。
2. **iroh**：打洞"约九成"与"95% 数据直连"为厂商说法；1.x 稳定性；Python/C 绑定何时暴露代理设置；自建中继的吞吐与资源占用；`iroh-blobs` 何时到 1.0。
3. **aiortc 吞吐**：没有找到公开数据。
4. **许可细节**：Wintun 预编译 DLL 的许可原文；libtorrent `route.h` 的广告条款是否随二进制分发生效；libnice 的许可；libzt 在 BSL Change Date 之后能否闭源商用。均须法务或读原文确认。
5. **NetBird**：当前版本自托管时中继的实际端口，以及客户端对强制 HTTP 代理的支持。
6. **Tailscale 用户态模式**：KB 1112 本次抓取失败，`--tun=userspace-networking` 的限制与性能未核实；tsnet 用户态网络栈的吞吐无数据；tsnet 是否默认注册 HTTP 代理钩子未核实。
7. **法律**：B13 许可边界、跨机构共享付费全文、日志留存的具体范围、《网络安全法》修正案施行日期、暂行规定 1997 年之后是否另有修订——须法务确认。
8. **大陆高校对 P2P/BT 的成文规定**：本次只找到台湾高校与北航（端口开放）的原文。
9. **hub 中继成本**：直通中继与联邦学习聚合的带宽费用取决于节点数、模型大小与轮次频率，需要在 S4 方案中按首批合作规模估算。
